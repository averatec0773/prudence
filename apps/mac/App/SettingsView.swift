import AppKit
import PrudenceModels
import ServiceManagement
import SwiftUI

/// Settings: two paths, one timer, one login item.
///
/// Both paths are overrides, and the screen says so, because the environment variables
/// `src/prudence/paths.py` honours still win over them. That order is what lets an agent run
/// this app against a copy of the store while the founder's own launch reads the real one.
struct SettingsView: View {

    @ObservedObject var settings: AppSettings
    /// `SMAppService` behind a protocol, the way Decaf does it, so this screen can be rendered
    /// off-screen with a fake and the awkward "registered but waiting for approval" state can
    /// be shown without waiting for a human to approve anything.
    var launchAtLogin: any LaunchAtLoginControlling
    /// Called when a setting that a timer depends on changes.
    var onChange: () -> Void = {}

    @State private var launchState: LaunchAtLoginState = .disabled

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Settings").font(.title2.bold())

            pathField(
                title: "Prudence engine",
                text: $settings.enginePath,
                placeholder: "found automatically",
                note: engineNote,
                chooseDirectories: false
            )

            pathField(
                title: "Database",
                text: $settings.databasePath,
                placeholder: "found automatically",
                note: databaseNote,
                chooseDirectories: false
            )

            VStack(alignment: .leading, spacing: 6) {
                Toggle("Ingest every 30 minutes", isOn: $settings.timedIngestEnabled)
                    .onChange(of: settings.timedIngestEnabled) { _, _ in onChange() }
                Text("Runs `prudence ingest` in the background. The hooks already spool events; this is what turns them into rows.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(alignment: .leading, spacing: 6) {
                Toggle(
                    "Open at login",
                    isOn: Binding(
                        get: { launchState.isOn },
                        set: { enabled in
                            launchAtLogin.setEnabled(enabled)
                            launchState = launchAtLogin.state
                        }
                    )
                )
                .disabled(launchState == .notAvailable)
                if let note = launchState.note {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer()
        }
        .padding(24)
        .frame(width: 520, height: 420, alignment: .topLeading)
        .onAppear { launchState = launchAtLogin.state }
    }

    private var engineNote: String {
        settings.enginePath.isEmpty
            ? "Looked for in uv's bin directories, then Homebrew, then your login shell."
            : "Overriding the search."
    }

    private var databaseNote: String {
        let located = settings.resolvedStore
        return "Reading \(located.url.path) (\(located.source.label))."
    }

    private func pathField(
        title: String,
        text: Binding<String>,
        placeholder: String,
        note: String,
        chooseDirectories: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.headline)
            HStack(spacing: 8) {
                TextField(placeholder, text: text)
                    .textFieldStyle(.roundedBorder)
                Button("Choose...") { choose(into: text, directories: chooseDirectories) }
                Button("Clear") { text.wrappedValue = "" }
                    .disabled(text.wrappedValue.isEmpty)
            }
            Text(note)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func choose(into text: Binding<String>, directories: Bool) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = !directories
        panel.canChooseDirectories = directories
        panel.allowsMultipleSelection = false
        panel.showsHiddenFiles = true
        if panel.runModal() == .OK, let url = panel.url {
            text.wrappedValue = url.path
        }
    }
}

/// The real login item. Four lines, and the third state most implementations forget.
@MainActor
final class SMAppServiceLaunchAtLogin: LaunchAtLoginControlling {

    var state: LaunchAtLoginState {
        switch SMAppService.mainApp.status {
        case .enabled: return .enabled
        case .requiresApproval: return .requiresApproval
        case .notRegistered: return .disabled
        case .notFound: return .notAvailable
        @unknown default: return .notAvailable
        }
    }

    func setEnabled(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            NSLog("launch at login: %@", String(describing: error))
        }
    }
}

/// A plain window for the settings screen. `Settings` as a SwiftUI scene is unreliable in an
/// `LSUIElement` app (research note, section 2), so this is the same hand-built window the
/// main screen uses.
@MainActor
final class SettingsWindowController: NSObject, NSWindowDelegate {

    private let window: NSWindow
    private let onClose: () -> Void

    init(
        settings: AppSettings,
        launchAtLogin: any LaunchAtLoginControlling,
        onChange: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.onClose = onClose
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 420),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "Prudence Settings"
        window.isReleasedWhenClosed = false
        window.center()
        window.contentViewController = NSHostingController(
            rootView: SettingsView(
                settings: settings, launchAtLogin: launchAtLogin, onChange: onChange))
        window.delegate = self
    }

    func show() { window.makeKeyAndOrderFront(nil) }

    func windowWillClose(_ notification: Notification) {
        DispatchQueue.main.async { [onClose] in onClose() }
    }
}
