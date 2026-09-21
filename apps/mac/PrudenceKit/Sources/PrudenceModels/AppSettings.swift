import Foundation
import PrudenceStore

/// The four things the user can change, kept in `UserDefaults`.
///
/// Two of them are paths, and both are overrides rather than the truth: the environment
/// variables `paths.py` honours still win, so an agent can launch the app against a copy of
/// the store without editing anyone's preferences, and the founder's own launch is unaffected.
/// The Settings screen says which of the three sources is in force.
@MainActor
public final class AppSettings: ObservableObject {

    public enum Key {
        public static let enginePath = "enginePath"
        public static let databasePath = "databasePath"
        public static let timedIngest = "timedIngestEnabled"
        /// The interface language. Written by `PrudenceUI.Localization.store`, which owns the
        /// picker and the `AppleLanguages` override beside it; this module only reads it, to
        /// hand the CLI a `--language` for the prose it writes. The two constants are the same
        /// string and a test in `PrudenceKitTests` asserts they stay that way: `PrudenceUI`
        /// depends on this target, so the constant cannot simply be imported from there.
        public static let language = "language"
    }

    /// Open question 2 of the M3 plan, accepted default: on, every 30 minutes.
    public static let ingestInterval: TimeInterval = 30 * 60
    /// The dropdown re-reads the store this often while it is open.
    public static let refreshInterval: TimeInterval = 60

    /// Immutable, and `UserDefaults` is documented as thread-safe, so the engine runner can
    /// read the current path from the background queue it runs on rather than hopping to the
    /// main actor for a string. `nonisolated(unsafe)` is the compiler's way of being told that.
    public nonisolated(unsafe) let defaults: UserDefaults

    @Published public var enginePath: String {
        didSet { defaults.set(enginePath, forKey: Key.enginePath) }
    }

    @Published public var databasePath: String {
        didSet { defaults.set(databasePath, forKey: Key.databasePath) }
    }

    @Published public var timedIngestEnabled: Bool {
        didSet { defaults.set(timedIngestEnabled, forKey: Key.timedIngest) }
    }

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        enginePath = defaults.string(forKey: Key.enginePath) ?? ""
        databasePath = defaults.string(forKey: Key.databasePath) ?? ""
        timedIngestEnabled = defaults.object(forKey: Key.timedIngest) as? Bool ?? true
    }

    public var engineOverride: String? { enginePath.isEmpty ? nil : enginePath }
    public var databaseOverride: String? { databasePath.isEmpty ? nil : databasePath }

    /// The same value, readable from any thread.
    public nonisolated func storedEngineOverride() -> String? {
        let value = defaults.string(forKey: Key.enginePath) ?? ""
        return value.isEmpty ? nil : value
    }

    /// The language code to hand the CLI for the prose it writes: `system`, `en` or `zh-Hans`,
    /// exactly the three values `prudence review --language` accepts.
    ///
    /// `system` is passed on rather than resolved here, because that is the CLI's own word for
    /// "use `model.language` from the config". A user who has not chosen a language in the app
    /// keeps whatever they configured for the terminal; one who has chosen overrides it.
    public nonisolated func storedLanguageCode() -> String {
        let value = defaults.string(forKey: Key.language) ?? ""
        return value.isEmpty ? "system" : value
    }

    /// Where the app will actually read, and why, for the Settings screen to print.
    public var resolvedStore: StoreLocation.Located {
        StoreLocation.locate(settingsOverride: databaseOverride)
    }
}
