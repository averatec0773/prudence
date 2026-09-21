import Foundation

/// Launch at login, behind a protocol, the way Decaf does it.
///
/// `SMAppService` is not testable and not renderable: it needs a real bundle, it talks to a
/// system daemon, and it has a third state most implementations forget, where the service is
/// registered but parked until the user approves it in System Settings. Keeping the decision
/// behind this protocol means the Settings screen can be rendered off-screen with a fake, and
/// the real conformance (`SMAppServiceLaunchAtLogin`, in the app target) stays four lines long.
public enum LaunchAtLoginState: Equatable, Sendable {
    case enabled
    case disabled
    /// Registered, but waiting for the user to allow it in System Settings > Login Items.
    case requiresApproval
    case notAvailable

    public var isOn: Bool { self == .enabled || self == .requiresApproval }

    public var note: String? {
        switch self {
        case .requiresApproval:
            return "Allow Prudence in System Settings > General > Login Items."
        case .notAvailable:
            return "Not available for this build (run the app from a signed bundle)."
        case .enabled, .disabled:
            return nil
        }
    }
}

@MainActor
public protocol LaunchAtLoginControlling: AnyObject {
    var state: LaunchAtLoginState { get }
    func setEnabled(_ enabled: Bool)
}

/// What the render harness and the tests use: a value that remembers what it was told.
@MainActor
public final class FakeLaunchAtLogin: LaunchAtLoginControlling {
    public private(set) var state: LaunchAtLoginState

    public init(state: LaunchAtLoginState = .disabled) {
        self.state = state
    }

    public func setEnabled(_ enabled: Bool) {
        state = enabled ? .enabled : .disabled
    }
}
