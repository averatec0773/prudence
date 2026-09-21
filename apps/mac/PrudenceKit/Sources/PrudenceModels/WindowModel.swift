import Foundation
import PrudenceEngine
import PrudenceStore

/// Where every store read and every CLI run the main window makes happens.
private let windowQueue = DispatchQueue(label: "dev.prudence.app.window", qos: .userInitiated)

/// The four things in the sidebar.
public enum MainSection: String, CaseIterable, Identifiable, Sendable {
    case overview
    case review
    case observations
    case settings

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .overview: return "Overview"
        case .review: return "Review"
        case .observations: return "Observations"
        case .settings: return "Settings"
        }
    }

    public var symbol: String {
        switch self {
        case .overview: return "chart.bar"
        case .review: return "doc.text"
        case .observations: return "lightbulb"
        case .settings: return "gearshape"
        }
    }
}

/// Every row the window draws from, read in one pass.
///
/// All of it, not a range of it. These are view-grained rows — one per session, one per
/// project-week, one per day — so the founder's 148-session store is a few hundred rows in
/// total, and reading the lot once means the project and range pickers are instant and can
/// never disagree with each other about what was read when.
public struct WindowData: Sendable {
    public var sessions: [AppSessionListRow]
    public var usage: [AppUsageByPurposeDayRow]
    public var outcomes: [AppOutcomesByWeekRow]
    public var commits: [AppCommitsByDayRow]
    public var observations: [AppObservationRow]
    public var reviews: [AppReviewRow]
    public var status: AppStatusRow?
    public var readAt: Date

    public init(
        sessions: [AppSessionListRow] = [],
        usage: [AppUsageByPurposeDayRow] = [],
        outcomes: [AppOutcomesByWeekRow] = [],
        commits: [AppCommitsByDayRow] = [],
        observations: [AppObservationRow] = [],
        reviews: [AppReviewRow] = [],
        status: AppStatusRow? = nil,
        readAt: Date = Date()
    ) {
        self.sessions = sessions
        self.usage = usage
        self.outcomes = outcomes
        self.commits = commits
        self.observations = observations
        self.reviews = reviews
        self.status = status
        self.readAt = readAt
    }

    public static let empty = WindowData()

    public var isEmpty: Bool {
        sessions.isEmpty && usage.isEmpty && outcomes.isEmpty && reviews.isEmpty
    }

    public static func read(from store: Store, now: Date = Date()) throws -> WindowData {
        WindowData(
            sessions: try store.sessions(),
            usage: try store.usageByPurposeDay(since: "0000-01-01"),
            outcomes: try store.outcomesByWeek(),
            commits: try store.commitsByDay(),
            observations: try store.observations(),
            reviews: try store.reviews(),
            status: try store.status(),
            readAt: now
        )
    }
}

/// One project and one range, applied to everything the window read.
///
/// A filter, not a computation: it decides which rows a screen sees and nothing about what
/// they say. The range is a first local day and the week that day falls in, because the
/// day-grained views and the week-grained one are cut on different boundaries and a chart
/// whose bars stopped a week before its lines would be a lie about both.
public struct WindowFilter: Sendable {
    public let project: String?
    public let range: ChartRange
    public let firstDay: String?
    public let firstWeek: String?

    public init(project: String?, range: ChartRange, now: Date, calendar: Calendar = .current) {
        self.project = project
        self.range = range
        let first = range.firstDay(now: now, calendar: calendar)
        firstDay = first
        firstWeek = first.flatMap { Formatting.isoWeekStart(of: $0, calendar: calendar) }
    }

    public func apply(to data: WindowData) -> WindowData {
        var filtered = data
        filtered.usage = data.usage.filter { row in
            matches(row.project) && (firstDay.map { row.day >= $0 } ?? true)
        }
        filtered.commits = data.commits.filter { row in
            matches(row.project) && (firstDay.map { row.day >= $0 } ?? true)
        }
        filtered.outcomes = data.outcomes.filter { row in
            matches(row.project) && (firstWeek.map { row.weekStart >= $0 } ?? true)
        }
        filtered.sessions = data.sessions.filter { row in
            guard matches(row.project) else { return false }
            guard let firstDay else { return true }
            guard let started = row.startedAt else { return false }
            // The session list is stamped in UTC and the range is in local days; comparing
            // the first ten characters would drop a session started after local midnight
            // west of Greenwich, so the stamp is parsed and the day taken locally.
            guard let date = Formatting.timestamp(started) else { return false }
            return Formatting.day(date) >= firstDay
        }
        return filtered
    }

    private func matches(_ name: String) -> Bool {
        guard let project else { return true }
        return name == project
    }
}

/// What the main window knows and the one thing it can do.
///
/// The same shape as `MenuViewModel`: every read and every CLI run happens off the main
/// thread and the main actor only ever receives a finished value. The store is opened per
/// read rather than kept open, so an `ingest` that replaced the views is picked up by the
/// next refresh with no special case.
@MainActor
public final class WindowModel: ObservableObject {

    @Published public var section: MainSection = .overview
    @Published public var range: ChartRange = .eightWeeks {
        didSet { if range != oldValue { selectedWeek = nil } }
    }
    /// nil is "All projects".
    @Published public var project: String? {
        didSet { if project != oldValue { selectedWeek = nil } }
    }
    /// The ISO week a bar on the Overview's stacked chart was clicked on, or nil for the whole
    /// range. Cleared whenever the scope changes, because a week that is no longer in the
    /// range would filter the cards down to nothing with no visible reason.
    @Published public var selectedWeek: String?
    /// Which stored review the Review screen is showing. nil is the newest.
    @Published public var selectedReview: Int?

    @Published public private(set) var data: WindowData = .empty
    @Published public private(set) var storeError: String?
    @Published public private(set) var isBusy = false
    @Published public private(set) var actionMessage: String?
    /// Why `prudence review` declined, when it did. The screen shows it with the button that
    /// runs the same command again with `--force`.
    @Published public private(set) var notReadyReason: String?

    public let settings: AppSettings
    private let engine: Engine
    private let clock: () -> Date

    public init(
        settings: AppSettings,
        engine: Engine? = nil,
        clock: @escaping () -> Date = Date.init
    ) {
        self.settings = settings
        self.clock = clock
        self.engine = engine ?? Engine(settingsOverride: settings.storedEngineOverride)
    }

    // MARK: - what the screens read

    public var now: Date { data.readAt }

    public var filter: WindowFilter {
        WindowFilter(project: project, range: range, now: now)
    }

    public var filtered: WindowData { filter.apply(to: data) }

    /// The filtered rows narrowed to the week a bar was clicked on, when one was.
    ///
    /// The charts read `filtered` so that clicking a bar does not reduce the chart to one bar;
    /// the cards read this, so that the three totals answer for the week the reader picked.
    public var scoped: WindowData { WeekSlice.apply(selectedWeek, to: filtered) }

    /// Every project with a session, plus the "All projects" entry the picker starts on.
    public var projects: [String] { ProjectFilter.projects(in: data.sessions) }

    public var weeklyUsage: WeeklyUsageModel { WeeklyUsageModel(rows: filtered.usage) }

    public var outcomes: OutcomeChartModel { OutcomeChartModel(rows: filtered.outcomes) }

    /// Active hours per day, as whole weeks of seven. Reads the whole range whatever week is
    /// selected: the strip is the shape of the range, and a one-week strip is not a shape.
    public var heat: ActiveHoursHeat { ActiveHoursHeat(rows: filtered.usage) }

    public var cards: SummaryCards {
        let rows = scoped
        return SummaryCards(sessions: rows.sessions, usage: rows.usage, commits: rows.commits)
    }

    /// The tokens the cards' scope measured, a sum of one view column.
    public var scopedTokens: Int {
        scoped.usage.reduce(0) { $0 + ($1.totalTokens ?? 0) }
    }

    /// The observation rows for the chosen scope, biggest gap first.
    ///
    /// Under "All projects" only the pooled rows are shown, because a row about one project
    /// shown under a heading that says every project would be read as a statement about all
    /// of them, which is exactly what principle 2 forbids. Choose a project to see its own.
    public var observations: [ObservationModel] {
        observationRows.map(ObservationModel.init(row:))
    }

    /// The same rows, unformatted and in the same order.
    ///
    /// The screen composes each sentence in the interface language from these columns
    /// (`PrudenceUI/ObservationText`), so it needs the row rather than the finished English
    /// `ObservationModel` carries.
    public var observationRows: [AppObservationRow] {
        data.observations
            .filter { project == nil ? $0.isPooled : (!$0.isPooled && $0.project == project) }
            .sorted {
                $0.gap == $1.gap ? $0.observationId < $1.observationId : $0.gap > $1.gap
            }
    }

    /// Every stored review, newest first, whatever the project picker says. A review is a
    /// document with its own scope printed on it; filtering the list by the picker would hide
    /// the review of everything the moment a project was chosen.
    public var reviews: [ReviewModel] { data.reviews.map(ReviewModel.init(row:)) }

    public var review: ReviewModel? {
        guard let selectedReview else { return reviews.first }
        return reviews.first { $0.id == selectedReview } ?? reviews.first
    }

    public var contractProblem: String? { storeError }

    // MARK: - reading

    public func refresh() {
        let override = settings.databaseOverride
        let now = clock()
        Task { [weak self] in
            let outcome = await Self.background { Self.read(override: override, now: now) }
            switch outcome {
            case let .success(data):
                self?.data = data
                self?.storeError = nil
            case let .failure(error):
                self?.data = .empty
                self?.storeError = error.message
            }
        }
    }

    // MARK: - the one button

    /// `prudence review --json`, and then whatever it answered.
    ///
    /// A "not ready" answer is not a failure: the command says so in its JSON body with the
    /// reason, and the screen shows the reason with a button that runs it again with
    /// `--force`. That is the whole of the readiness rule as far as the app is concerned; the
    /// engine owns it.
    ///
    /// `--language` is appended when this machine's `prudence` understands it, so the model
    /// segment is written in the language the reader chose in Settings. The probe and the
    /// reason for it are in `PrudenceEngine.Engine.supportsLanguage`.
    public func reviewNow(force: Bool = false) {
        guard !isBusy else { return }
        isBusy = true
        notReadyReason = nil
        actionMessage = force ? "Writing a review anyway..." : "Writing a review..."
        let engine = self.engine
        let language = settings.storedLanguageCode()
        let arguments = force ? ["review", "--force"] : ["review"]
        Task { [weak self] in
            let answer = await Self.background { () -> ReviewAnswer in
                do {
                    return ReviewAnswer(
                        result: try engine.runJSON(arguments, language: language))
                } catch let
                    error as EngineError
                {
                    return ReviewAnswer(failure: error.message)
                } catch {
                    return ReviewAnswer(failure: String(describing: error))
                }
            }
            self?.isBusy = false
            self?.actionMessage = answer.message
            self?.notReadyReason = answer.notReadyReason
            if answer.wrote {
                self?.selectedReview = nil
                self?.refresh()
            }
        }
    }

    public func dismissMessage() {
        actionMessage = nil
        notReadyReason = nil
    }

    // MARK: - for the render harness

    /// A model with its rows already in it and nothing running. Nothing in the app calls it.
    public static func preview(
        data: WindowData,
        section: MainSection = .overview,
        project: String? = nil,
        range: ChartRange = .eightWeeks,
        selectedWeek: String? = nil,
        storeError: String? = nil,
        actionMessage: String? = nil,
        notReadyReason: String? = nil,
        settings: AppSettings? = nil
    ) -> WindowModel {
        let model = WindowModel(
            settings: settings
                ?? AppSettings(defaults: UserDefaults(suiteName: "dev.prudence.preview") ?? .standard)
        )
        model.data = data
        model.section = section
        model.project = project
        model.range = range
        // After the range and the project, because both clear a week selection.
        model.selectedWeek = selectedWeek
        model.storeError = storeError
        model.actionMessage = actionMessage
        model.notReadyReason = notReadyReason
        return model
    }

    // MARK: - off the main thread

    nonisolated private static func read(override: String?, now: Date)
        -> Result<WindowData, StoreError>
    {
        do {
            let store = try Store(settingsOverride: override)
            return .success(try WindowData.read(from: store, now: now))
        } catch let error as StoreError {
            return .failure(error)
        } catch {
            return .failure(.unreadable(String(describing: error)))
        }
    }

    nonisolated private static func background<T: Sendable>(_ body: @escaping @Sendable () -> T)
        async -> T
    {
        await withCheckedContinuation { continuation in
            windowQueue.async { continuation.resume(returning: body()) }
        }
    }
}

/// What `prudence review --json` said, in the three shapes the screen cares about.
struct ReviewAnswer: Sendable {
    let message: String
    let notReadyReason: String?
    let wrote: Bool

    init(result: EngineResult) {
        guard let json = result.json else {
            self.init(message: "Review written.", notReadyReason: nil, wrote: true)
            return
        }
        if let ready = json["ready"] as? Bool, ready == false {
            let reason = (json["reason"] as? String) ?? "Not enough new work for a review yet."
            self.init(message: reason, notReadyReason: reason, wrote: false)
            return
        }
        if let id = json["id"] as? Int {
            self.init(message: "Review \(id) written.", notReadyReason: nil, wrote: true)
            return
        }
        self.init(message: "Review written.", notReadyReason: nil, wrote: true)
    }

    init(failure: String) {
        self.init(message: failure, notReadyReason: nil, wrote: false)
    }

    private init(message: String, notReadyReason: String?, wrote: Bool) {
        self.message = message
        self.notReadyReason = notReadyReason
        self.wrote = wrote
    }
}
