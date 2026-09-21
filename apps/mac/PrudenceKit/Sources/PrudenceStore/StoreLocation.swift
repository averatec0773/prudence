import Foundation

/// Where `prudence.db` is, resolved the same way `src/prudence/paths.py` resolves it.
///
/// Three sources in one order, so that an agent, the founder and a user who moved their data
/// all end up at the same file:
///
/// 1. `PRUDENCE_DATA_DIR`, the environment variable `paths.data_dir()` honours. It is what
///    lets the app be launched against a copy of the store without touching the real one.
/// 2. A path the user picked in Settings, stored as a plain string in `UserDefaults`.
/// 3. `~/Library/Application Support/prudence/prudence.db`, which is what `paths.data_dir()`
///    returns on macOS with no override.
///
/// `PRUDENCE_CONFIG_DIR` is read only to pass it on to the CLI; nothing the app renders comes
/// out of `config.toml`.
public enum StoreLocation {

    public static let dataDirectoryVariable = "PRUDENCE_DATA_DIR"
    public static let configDirectoryVariable = "PRUDENCE_CONFIG_DIR"
    public static let databaseName = "prudence.db"

    /// How the path in hand was arrived at, so the Settings screen can say so.
    public enum Source: Equatable, Sendable, CaseIterable {
        case environment
        case settings
        case standard

        /// The English wording, and the fallback for anything that has no interface layer.
        ///
        /// The **screen does not print this**: `PrudenceUI.Fmt.storeSource` turns the case into
        /// the reader's own language, because a store target is a sentence on a settings page
        /// and not a figure that has to match the CLI. This stays as the value a log line, a
        /// test or a crash report can carry, and as the thing the translation is checked
        /// against. Batch 1 left it on screen in English inside a Chinese window (M4 plan,
        /// "Batch 2 inputs"); batch 2 moved the wording and kept the case.
        public var label: String {
            switch self {
            case .environment: return "from \(StoreLocation.dataDirectoryVariable)"
            case .settings: return "from Settings"
            case .standard: return "the standard location"
            }
        }
    }

    public struct Located: Equatable, Sendable {
        public let url: URL
        public let source: Source

        public init(url: URL, source: Source) {
            self.url = url
            self.source = source
        }
    }

    /// The database path, without checking whether a file is there.
    public static func locate(
        settingsOverride: String? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        home: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> Located {
        if let directory = environment[dataDirectoryVariable], !directory.isEmpty {
            let expanded = expand(directory, home: home)
            return Located(url: expanded.appendingPathComponent(databaseName), source: .environment)
        }
        if let override = settingsOverride?.trimmingCharacters(in: .whitespacesAndNewlines),
            !override.isEmpty
        {
            return Located(url: expand(override, home: home), source: .settings)
        }
        let standard =
            home
            .appendingPathComponent("Library/Application Support/prudence")
            .appendingPathComponent(databaseName)
        return Located(url: standard, source: .standard)
    }

    /// The configuration directory, for handing to the CLI. `nil` means "let it decide".
    public static func configDirectory(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> String? {
        let value = environment[configDirectoryVariable]
        return (value?.isEmpty ?? true) ? nil : value
    }

    static func expand(_ path: String, home: URL) -> URL {
        if path == "~" { return home }
        if path.hasPrefix("~/") {
            return home.appendingPathComponent(String(path.dropFirst(2)))
        }
        return URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
    }
}
