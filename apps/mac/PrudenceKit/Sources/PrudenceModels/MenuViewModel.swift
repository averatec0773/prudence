import Foundation
import PrudenceStore
import PrudenceEngine

/// Where every store read and every CLI run happens. At file scope rather than inside the
/// class, because the class is main-actor isolated and this queue is exactly the thing that
/// is not.
private let workQueue = DispatchQueue(label: "dev.prudence.app.work", qos: .userInitiated)

/// What the dropdown knows, and the four things it can do.
///
/// Every read of the store and every run of the CLI happens off the main thread; the main
/// actor only ever receives a finished value. The store is opened per read rather than kept
/// open: it costs a few milliseconds, and it means an `ingest` that replaced the views, or a
/// store that appeared for the first time, is picked up by the next refresh with no special
/// case for either.
@MainActor
public final class MenuViewModel: ObservableObject {

    @Published public private(set) var snapshot = Snapshot()
    @Published public private(set) var engineVersion: String?
    @Published public private(set) var engineError: String?
    /// What the last button did, shown under the buttons until the next action.
    @Published public private(set) var actionMessage: String?
    @Published public private(set) var isBusy = false

    public let settings: AppSettings
    private let engine: Engine
    private let clock: () -> Date
    private var refreshTimer: Timer?
    private var ingestTimer: Timer?

    public init(
        settings: AppSettings,
        engine: Engine? = nil,
        clock: @escaping () -> Date = Date.init
    ) {
        self.settings = settings
        self.clock = clock
        self.engine = engine ?? Engine(settingsOverride: settings.storedEngineOverride)
    }

    // MARK: - the lines

    /// One read of everything the dropdown shows.
    public func refresh() {
        let override = settings.databaseOverride
        let now = clock()
        Task { [weak self] in
            let snapshot = await Self.background { Self.read(override: override, now: now) }
            self?.snapshot = snapshot
        }
    }

    /// `prudence --version`, once per launch unless it failed.
    public func resolveEngine() {
        guard engineVersion == nil else { return }
        let engine = self.engine
        Task { [weak self] in
            let outcome = await Self.background { () -> Result<String, EngineError> in
                do { return .success(try engine.version()) } catch let error as EngineError {
                    return .failure(error)
                } catch { return .failure(.launchFailed(String(describing: error))) }
            }
            switch outcome {
            case let .success(version):
                self?.engineVersion = version
                self?.engineError = nil
            case let .failure(error):
                self?.engineVersion = nil
                self?.engineError = error.message
            }
        }
    }

    /// True when the engine and the store disagree about the contract, or the store refused.
    public var contractProblem: String? { snapshot.storeError }

    // MARK: - the buttons

    public func ingestNow() {
        run(["ingest"], startedMessage: "Ingesting...") { result in
            guard let json = result.json else { return "Ingest finished." }
            if let sessions = json["sessions"] as? Int {
                return "Ingest finished: \(sessions) sessions."
            }
            return "Ingest finished."
        }
    }

    /// The dropdown's Review now. Same command and same `--language` guard as the window's
    /// button (`WindowModel.reviewNow`), so a review written from either place is written in
    /// the language the reader chose.
    public func reviewNow() {
        run(["review"], language: settings.storedLanguageCode(), startedMessage: "Writing a review...") { result in
            guard let json = result.json else { return "Review written." }
            // `prudence review` answers `ready: false` with the reason rather than failing,
            // and the reason is the whole point of the button in that case.
            if let ready = json["ready"] as? Bool, ready == false {
                return (json["reason"] as? String) ?? "Not enough new work for a review yet."
            }
            if let id = json["id"] as? Int { return "Review \(id) written." }
            return "Review written."
        }
    }

    private func run(
        _ arguments: [String],
        language: String? = nil,
        startedMessage: String,
        describe: @escaping (EngineResult) -> String
    ) {
        guard !isBusy else { return }
        isBusy = true
        actionMessage = startedMessage
        let engine = self.engine
        Task { [weak self] in
            let message = await Self.background { () -> String in
                do { return describe(try engine.runJSON(arguments, language: language)) }
                catch let error as EngineError
                {
                    return error.message
                } catch { return String(describing: error) }
            }
            self?.isBusy = false
            self?.actionMessage = message
            self?.refresh()
        }
    }

    // MARK: - timers

    /// Called when the popover opens, and once at launch.
    public func start() {
        resolveEngine()
        refresh()
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(
            withTimeInterval: AppSettings.refreshInterval, repeats: true
        ) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        startIngestTimer()
    }

    /// The 30-minute ingest, on unless the user turned it off (open question 2's default).
    public func startIngestTimer() {
        ingestTimer?.invalidate()
        guard settings.timedIngestEnabled else { return }
        ingestTimer = Timer.scheduledTimer(
            withTimeInterval: AppSettings.ingestInterval, repeats: true
        ) { [weak self] _ in
            Task { @MainActor in self?.ingestNow() }
        }
    }

    public func stop() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        ingestTimer?.invalidate()
        ingestTimer = nil
    }

    // MARK: - for the render harness

    /// A model with its lines already filled and no timers running.
    ///
    /// The render harness draws the shipping views, which means it needs a real
    /// `MenuViewModel`; this is how it gets one without the view deciding to run an ingest
    /// while a PNG is being written. Nothing in the app calls it.
    public static func preview(
        snapshot: Snapshot,
        engineVersion: String? = nil,
        engineError: String? = nil,
        actionMessage: String? = nil,
        settings: AppSettings? = nil
    ) -> MenuViewModel {
        let model = MenuViewModel(
            settings: settings
                ?? AppSettings(defaults: UserDefaults(suiteName: "dev.prudence.preview") ?? .standard)
        )
        model.snapshot = snapshot
        model.engineVersion = engineVersion
        model.engineError = engineError
        model.actionMessage = actionMessage
        return model
    }

    // MARK: - off the main thread

    nonisolated private static func read(override: String?, now: Date) -> Snapshot {
        do {
            let store = try Store(settingsOverride: override)
            return try Snapshot.read(from: store, now: now)
        } catch let error as StoreError {
            return Snapshot.failed(error, now: now)
        } catch {
            return Snapshot.failed(.unreadable(String(describing: error)), now: now)
        }
    }

    nonisolated private static func background<T: Sendable>(_ body: @escaping @Sendable () -> T)
        async -> T
    {
        await withCheckedContinuation { continuation in
            workQueue.async { continuation.resume(returning: body()) }
        }
    }
}
