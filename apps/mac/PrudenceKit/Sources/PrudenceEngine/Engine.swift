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

    public init(
        locator: EngineLocator = EngineLocator(),
        environment: [String: String] = ProcessInfo.processInfo.environment,
        settingsOverride: @escaping () -> String? = { nil }
    ) {
        self.locator = locator
        self.environment = environment
        self.settingsOverride = settingsOverride
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
