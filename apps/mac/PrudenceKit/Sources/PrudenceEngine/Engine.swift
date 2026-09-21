import Foundation

/// Running the CLI: the app's only way to change anything.
///
/// The app reads the store and asks the engine to work; the arrows go one way. Every action
/// is the same command the founder runs by hand, with `--json` appended so the result can be
/// decoded rather than scraped, and `PRUDENCE_INTERNAL=1` in the environment so the capture
/// hooks stay quiet around Prudence's own subprocesses (the rumps prototype set the same
/// variable for the same reason).
///
/// `PRUDENCE_DATA_DIR` and `PRUDENCE_CONFIG_DIR` are passed through when the app itself was
/// launched with them, so an agent verifying against a copy of the store never has the app
/// quietly ingest into the real one.
public enum EngineError: Error, Equatable, Sendable {
    case notFound
    case failed(status: Int32, message: String)
    case notJSON(String)
    case launchFailed(String)

    public var message: String {
        switch self {
        case .notFound:
            return "prudence not found. Set its path in Settings."
        case let .failed(status, message):
            let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty ? "prudence exited \(status)." : text
        case let .notJSON(text):
            return "prudence answered with something that is not JSON: \(text.prefix(120))"
        case let .launchFailed(text):
            return "prudence could not be started: \(text)"
        }
    }
}

public struct EngineResult: Sendable {
    public let json: [String: Any]?
    public let stdout: String
    public let stderr: String

    public init(json: [String: Any]?, stdout: String, stderr: String) {
        self.json = json
        self.stdout = stdout
        self.stderr = stderr
    }
}

public final class Engine: @unchecked Sendable {

    private let locator: EngineLocator
    private let settingsOverride: () -> String?
    private let environment: [String: String]
    private let lock = NSLock()
    private var languageSupport: Bool?

    public init(
        locator: EngineLocator = EngineLocator(),
        environment: [String: String] = ProcessInfo.processInfo.environment,
        settingsOverride: @escaping () -> String? = { nil }
    ) {
        self.locator = locator
        self.environment = environment
        self.settingsOverride = settingsOverride
    }

    // MARK: - the language flag

    /// The flag every command that writes prose takes: `review`, its `--explain` segment, and
    /// `ask`. `system|en|zh-Hans`, the same three values the app's own picker offers.
    public static let languageFlag = "--language"

    /// Whether the `prudence` on this machine understands `--language`, asked once.
    ///
    /// The app ships separately from the engine and a user can have an older one, so the flag
    /// is **probed rather than assumed**: `prudence review --help` is run once and its text is
    /// searched for the flag. An engine that has never heard of it would exit 2 on an unknown
    /// option, which would turn "write me a review" into an error about a word the user never
    /// typed. A probe that cannot run at all answers false, which is the safe direction: the
    /// review is written, in the engine's configured language.
    ///
    /// The answer is cached for the life of the process. Upgrading the CLI under a running app
    /// therefore needs a relaunch before the flag is used, which is the same thing an
    /// `AppleLanguages` change needs and is written down in `apps/mac/DESIGN.md`.
    public func supportsLanguage() -> Bool {
        lock.lock()
        if let cached = languageSupport {
            lock.unlock()
            return cached
        }
        lock.unlock()
        let answer: Bool
        do {
            let help = try run(arguments: ["review", "--help"], appendJSON: false)
            answer = Self.helpMentionsLanguage(help.stdout + help.stderr)
        } catch {
            answer = false
        }
        lock.lock()
        languageSupport = answer
        lock.unlock()
        return answer
    }

    /// The one string test the probe is. Split out so a test can pin it against real help text
    /// without running anything.
    public static func helpMentionsLanguage(_ help: String) -> Bool {
        help.contains(languageFlag)
    }

    /// `["--language", "zh-Hans"]`, or nothing at all.
    ///
    /// Nothing when the code is nil, when it is empty, or when this engine has never heard of
    /// the flag. `system` is passed through rather than swallowed: it is a value the CLI
    /// accepts and it means "use `model.language` from the config", so a user who has not
    /// chosen a language in the app keeps whatever they configured for the CLI.
    public func languageArguments(_ code: String?) -> [String] {
        guard let code, !code.isEmpty, supportsLanguage() else { return [] }
        return [Self.languageFlag, code]
    }

    /// The same command with the language flag appended when it is available.
    public func runJSON(_ arguments: [String], language: String?) throws -> EngineResult {
        try runJSON(arguments + languageArguments(language))
    }

    /// The executable path, or nil. Runs the login-shell probe, so keep it off the main thread.
    public func executablePath() -> String? {
        locator.locate(settingsOverride: settingsOverride())?.path
    }

    /// `prudence --version`, trimmed. The version string, not a check.
    public func version() throws -> String {
        let result = try run(arguments: ["--version"], appendJSON: false)
        return result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// `prudence <arguments> --json`, decoded.
    ///
    /// A non-zero exit is not automatically an error to shout about: `prudence review` says
    /// "not ready" through a JSON body with `ready: false`, and the caller wants that reason
    /// rather than an exception. So a non-zero exit whose stdout still parses as JSON comes
    /// back as a result; anything else throws.
    public func runJSON(_ arguments: [String]) throws -> EngineResult {
        try run(arguments: arguments, appendJSON: true)
    }

    private func run(arguments: [String], appendJSON: Bool) throws -> EngineResult {
        guard let executable = executablePath() else { throw EngineError.notFound }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = appendJSON ? arguments + ["--json"] : arguments
        process.environment = subprocessEnvironment()

        let out = Pipe()
        let error = Pipe()
        process.standardOutput = out
        process.standardError = error
        do { try process.run() } catch {
            throw EngineError.launchFailed(String(describing: error))
        }
        let outData = out.fileHandleForReading.readDataToEndOfFile()
        let errorData = error.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        let stdout = String(decoding: outData, as: UTF8.self)
        let stderr = String(decoding: errorData, as: UTF8.self)
        let json =
            (try? JSONSerialization.jsonObject(with: outData)) as? [String: Any]

        if process.terminationStatus != 0 && json == nil {
            throw EngineError.failed(
                status: process.terminationStatus,
                message: stderr.isEmpty ? stdout : stderr
            )
        }
        if appendJSON && json == nil {
            throw EngineError.notJSON(stdout)
        }
        return EngineResult(json: json, stdout: stdout, stderr: stderr)
    }

    /// The child's environment: ours, plus the internal marker, plus whichever store the app
    /// itself was pointed at.
    private func subprocessEnvironment() -> [String: String] {
        var child = environment
        child["PRUDENCE_INTERNAL"] = "1"
        return child
    }
}
