import Foundation

/// Finding the `prudence` executable, which is harder than it sounds.
///
/// An app launched from Finder, the Dock or Spotlight is started by the per-user `launchd` and
/// inherits `launchd`'s environment. It never reads `.zshrc` or `.zprofile`, so the PATH that
/// has `prudence` on it in Terminal is simply not there. The research note (section 5) settles
/// the order; this file is that order, written once:
///
/// 1. a path the user set in Settings, verified before it is trusted;
/// 2. uv's own documented resolution order for tool binaries, then Homebrew's two prefixes;
/// 3. one login-shell probe, off the main thread, with a timeout, cached for the session;
/// 4. nothing, and the dropdown says "engine not found" with a Settings button.
///
/// Every step is a `FileProbing` call, so the whole order is testable against a fake filesystem
/// with no `prudence` anywhere near the machine running the test.
public protocol FileProbing: Sendable {
    /// True when `path` is a file this process could execute.
    func isExecutableFile(atPath path: String) -> Bool
}

public struct DefaultFileProbe: FileProbing {
    public init() {}
    public func isExecutableFile(atPath path: String) -> Bool {
        FileManager.default.isExecutableFile(atPath: path)
    }
}

/// The login-shell fallback, behind a protocol so tests never spawn a shell.
public protocol LoginShellProbing: Sendable {
    /// The absolute path a login shell would resolve `prudence` to, or nil.
    func locate(timeout: TimeInterval) -> String?
}

/// `zsh -ilc 'command -v prudence'`, the way VS Code harvests the login environment.
///
/// Interactive *and* login, because either file may be where the user's PATH is set. The
/// timeout matters: an rc file that waits on the network would otherwise hang the app, so the
/// process is killed at the deadline and the answer is simply "not found". `PRUDENCE_INTERNAL`
/// is set so a user can guard their own rc files against this probe, as VS Code's
/// `VSCODE_RESOLVING_ENVIRONMENT` lets them.
public struct LoginShellProbe: LoginShellProbing {
    public init() {}

    public func locate(timeout: TimeInterval = 10) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-ilc", "command -v prudence"]
        process.environment = ProcessInfo.processInfo.environment.merging(
            ["PRUDENCE_INTERNAL": "1"], uniquingKeysWith: { _, new in new })
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }

        let deadline = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: deadline)
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        deadline.cancel()

        let output = String(decoding: data, as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !output.isEmpty, output.hasPrefix("/") else { return nil }
        return output.components(separatedBy: "\n").first
    }
}

public final class EngineLocator: @unchecked Sendable {

    /// How the executable in hand was found, for the Settings screen and for the report.
    public enum Source: Equatable, Sendable {
        case settings
        case knownDirectory(String)
        case loginShell
    }

    public struct Found: Equatable, Sendable {
        public let path: String
        public let source: Source
    }

    private let probe: FileProbing
    private let shell: LoginShellProbing
    private let environment: [String: String]
    private let home: String
    private let lock = NSLock()
    private var cachedShellAnswer: String??

    public init(
        probe: FileProbing = DefaultFileProbe(),
        shell: LoginShellProbing = LoginShellProbe(),
        environment: [String: String] = ProcessInfo.processInfo.environment,
        home: String = FileManager.default.homeDirectoryForCurrentUser.path
    ) {
        self.probe = probe
        self.shell = shell
        self.environment = environment
        self.home = home
    }

    /// The directories probed before the shell, in order. Public so the README and the
    /// Settings screen can show the same list the code walks.
    public var searchPath: [String] {
        var directories: [String] = []
        func add(_ path: String?) {
            guard let path, !path.isEmpty else { return }
            let expanded = expand(path)
            if !directories.contains(expanded) { directories.append(expanded) }
        }
        // uv's documented order for `uv tool install` binaries.
        add(environment["UV_TOOL_BIN_DIR"])
        add(environment["XDG_BIN_HOME"])
        if let data = environment["XDG_DATA_HOME"], !data.isEmpty {
            add((expand(data) as NSString).deletingLastPathComponent + "/bin")
        }
        add("\(home)/.local/bin")
        // Then the two Homebrew prefixes, Apple silicon first.
        add("/opt/homebrew/bin")
        add("/usr/local/bin")
        return directories
    }

    /// Settings, then the known directories. Cheap, synchronous, no side effects.
    /// It never runs a shell, so it is safe to call on the main thread.
    public func locateWithoutShell(settingsOverride: String? = nil) -> Found? {
        if let override = settingsOverride?.trimmingCharacters(in: .whitespacesAndNewlines),
            !override.isEmpty,
            probe.isExecutableFile(atPath: expand(override))
        {
            return Found(path: expand(override), source: .settings)
        }
        for directory in searchPath {
            let candidate = directory + "/prudence"
            if probe.isExecutableFile(atPath: candidate) {
                return Found(path: candidate, source: .knownDirectory(directory))
            }
        }
        return nil
    }

    /// The whole order, shell probe included. Call this off the main thread.
    public func locate(settingsOverride: String? = nil, timeout: TimeInterval = 10) -> Found? {
        if let found = locateWithoutShell(settingsOverride: settingsOverride) { return found }
        if let answer = cachedShellAnswer(timeout: timeout),
            probe.isExecutableFile(atPath: answer)
        {
            return Found(path: answer, source: .loginShell)
        }
        return nil
    }

    /// One probe per launch, however many times the dropdown refreshes. A nil answer is
    /// cached too: a shell that does not know `prudence` will not learn it in 60 seconds.
    private func cachedShellAnswer(timeout: TimeInterval) -> String? {
        lock.lock()
        if let cached = cachedShellAnswer {
            lock.unlock()
            return cached
        }
        lock.unlock()
        let answer = shell.locate(timeout: timeout)
        lock.lock()
        cachedShellAnswer = .some(answer)
        lock.unlock()
        return answer
    }

    private func expand(_ path: String) -> String {
        if path == "~" { return home }
        if path.hasPrefix("~/") { return home + String(path.dropFirst(1)) }
        return path
    }
}
