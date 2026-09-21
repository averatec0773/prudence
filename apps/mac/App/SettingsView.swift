import AppKit
import PrudenceModels
import PrudenceUI
import ServiceManagement
import SwiftUI

/// Settings: **variant B**, the founder's choice from the M4 mockups. Two tabs, General and
/// Data, each a grouped box of label-and-control rows with the note under the control.
///
/// General is what the app does: the timer, the login item, the language. Data is where it
/// reads from: the engine, the database, and one line of what the store says about itself.
/// Both paths are overrides, and the screen says so, because the environment variables
/// `src/prudence/paths.py` honours still win over them. That order is what lets an agent run
/// this app against a copy of the store while the founder's own launch reads the real one.
///
/// The tab strip is a `Picker(.segmented)` and the language is a `Picker(.menu)`: system
/// controls, not redrawn. On macOS 26 they already draw themselves in the system material, so
/// the strip carries the glass and the controls on it do not (`PrudenceUI/Controls.swift`).
struct SettingsView: View {

    enum Tab: String, CaseIterable, Identifiable {
        case general, data
        var id: String { rawValue }
        var title: String {
            self == .general ? Str.settingsGeneral.text : Str.settingsData.text
        }
    }

    @ObservedObject var settings: AppSettings
    /// `SMAppService` behind a protocol, the way Decaf does it, so this screen can be rendered
    /// off-screen with a fake and the awkward "registered but waiting for approval" state can
    /// be shown without waiting for a human to approve anything.
    var launchAtLogin: any LaunchAtLoginControlling
    /// Called when a setting that a timer depends on changes.
    var onChange: () -> Void = {}
    /// What the store says about itself, for the one line of it the Data tab prints. A
    /// closure rather than a value, because this screen outlives one read and the settings
    /// object must not learn how to open a database.
    var status: () -> StatusModel? = { nil }
    /// Which tab the render harness wants. The app starts on General.
    var initialTab: Tab = .general

    @State private var tab: Tab = .general
    @State private var launchState: LaunchAtLoginState = .disabled
    /// True once the language has been changed in this launch, which is when the relaunch
    /// note and the button have something to say.
    @State private var languageChanged = false

    var body: some View {
        VStack(spacing: 0) {
            ControlStrip {
                Picker("", selection: $tab) {
                    ForEach(Tab.allCases) { tab in Text(tab.title).tag(tab) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 240)
            }
            .padding(.vertical, Space.s2)
            .frame(maxWidth: .infinity)

            ScrollView {
                VStack(alignment: .leading, spacing: Space.s6) {
                    switch tab {
                    case .general: generalGroup
                    case .data: dataGroup
                    }
                }
                .padding(Space.s6)
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
        }
        .background(Surface.canvas)
        .frame(minWidth: 560, minHeight: 440, alignment: .topLeading)
        .onAppear {
            tab = initialTab
            launchState = launchAtLogin.state
        }
    }

    // MARK: - General

    private var generalGroup: some View {
        Group(label: Str.settingsGeneral.text) {
            Setting(label: Str.settingsTimedIngest.text, note: Str.settingsTimedIngestNote.text) {
                Toggle("", isOn: $settings.timedIngestEnabled)
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .onChange(of: settings.timedIngestEnabled) { _, _ in onChange() }
            }
            Setting(label: Str.settingsOpenAtLogin.text, note: launchNote) {
                Toggle(
                    "",
                    isOn: Binding(
                        get: { launchState.isOn },
                        set: { enabled in
                            launchAtLogin.setEnabled(enabled)
                            launchState = launchAtLogin.state
                        }
                    )
                )
                .toggleStyle(.switch)
                .labelsHidden()
                .disabled(launchState == .notAvailable)
            }
            Setting(label: Str.settingsLanguage.text, note: languageNote) {
                HStack(spacing: Space.s2) {
                    Picker("", selection: languageBinding) {
                        ForEach(Language.allCases) { language in
                            Text(language.label).tag(language)
                        }
                    }
                    .pickerStyle(.menu)
                    .labelsHidden()
                    .frame(width: 160)
                    if languageChanged {
                        Button(Str.settingsLanguageRelaunchNow.text) { relaunch() }
                            .buttonStyle(.prudence)
                    }
                }
            }
        }
    }

    /// The setting is stored and `AppleLanguages` is written beside it; Cocoa reads that at
    /// launch, which is the macOS convention for a per-app language and why this takes effect
    /// on the next one rather than immediately.
    private var languageBinding: Binding<Language> {
        Binding(
            get: { Localization.stored(in: settings.defaults) },
            set: { language in
                Localization.store(language, in: settings.defaults)
                languageChanged = true
            }
        )
    }

    private var languageNote: String {
        var note = Str.settingsLanguageNote.text + " " + Str.settingsLanguageSystemSettings.text
        if languageChanged { note = Str.settingsLanguageRelaunch.text + " " + note }
        return note
    }

    private var launchNote: String? {
        switch launchState {
        case .requiresApproval: return Str.loginRequiresApproval.text
        case .notAvailable: return Str.loginNotAvailable.text
        default: return nil
        }
    }

    // MARK: - Data

    private var dataGroup: some View {
        Group(label: Str.settingsData.text) {
            Setting(label: Str.settingsEnginePath.text, note: engineNote) {
                PathField(text: $settings.enginePath)
            }
            Setting(label: Str.settingsDatabasePath.text, note: databaseNote) {
                PathField(text: $settings.databasePath)
            }
            Setting(label: Str.settingsStore.text, note: nil) {
                MethodLine(storeLine)
            }
        }
    }

    private var engineNote: String {
        settings.enginePath.isEmpty
            ? Str.settingsEnginePathNote.text : Str.settingsEnginePathOverride.text
    }

    private var databaseNote: String {
        let located = settings.resolvedStore
        // `Fmt.storeSource`, not `Source.label`: the enum's English is the value a log line
        // carries, and this is a sentence on a settings page (M4 plan, "Batch 2 inputs").
        return Str.settingsDatabasePathNote(located.url.path, Fmt.storeSource(located.source))
    }

    /// What the store says about itself, read from `app_status` and not computed here.
    private var storeLine: String {
        guard let status = status() else { return Str.settingsStoreUnread.text }
        return Str.settingsStoreLine(
            status.engineVersion,
            status.contractVersion,
            Fmt.sessions(status.sessions),
            Fmt.projects(status.projects)
        )
    }

    /// Quit and come back, which is what an `AppleLanguages` change needs.
    private func relaunch() {
        let url = Bundle.main.bundleURL
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
    }
}

// MARK: - the two shapes a settings screen is made of

/// A grouped box with its caption above it, the System Settings shape.
private struct Group<Content: View>: View {

    let label: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            Text(label)
                .font(Type.captionStrong)
                .foregroundStyle(Ink.secondary)
                .padding(.leading, Space.s1)
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) { content }
            }
        }
    }
}

/// One row of a group: a right-aligned label in a fixed column, the control, and the note
/// under the control.
///
/// The 180 pt label column stands in for what `Form(.formStyle(.grouped))` aligns by itself.
/// It is here rather than a real `Form` because this screen is also hosted inside the window's
/// sidebar, where a grouped form draws its own background and would be a second card inside
/// this one.
private struct Setting<Control: View>: View {

    let label: String
    let note: String?
    @ViewBuilder var control: Control

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: Space.s4) {
                Text(label)
                    .font(Type.footnote)
                    .foregroundStyle(Ink.primary)
                    .frame(width: 180, alignment: .trailing)
                VStack(alignment: .leading, spacing: Space.s2) {
                    control
                    if let note {
                        Text(note)
                            .font(Type.caption)
                            .foregroundStyle(Ink.tertiary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, Space.s4)
            .padding(.vertical, Space.s3)
            Divider().opacity(0.6)
        }
    }
}

/// A path row: a text field, a Choose button opening `NSOpenPanel`, and a Clear button.
private struct PathField: View {

    @Binding var text: String

    var body: some View {
        HStack(spacing: Space.s2) {
            TextField(Str.settingsFoundAutomatically.text, text: $text)
                .textFieldStyle(.roundedBorder)
                .font(Type.footnote)
            Button(Str.commonChoose.text) { choose() }
            Button(Str.commonClear.text) { text = "" }
                .disabled(text.isEmpty)
        }
        .buttonStyle(.prudence)
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.showsHiddenFiles = true
        if panel.runModal() == .OK, let url = panel.url { text = url.path }
    }
}

// MARK: - the real login item

/// Four lines, and the third state most implementations forget.
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
        status: @escaping () -> StatusModel? = { nil },
        onChange: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.onClose = onClose
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 470),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "\(Product.name) \(Str.settingsTitle.text)"
        window.isReleasedWhenClosed = false
        window.center()
        window.contentViewController = NSHostingController(
            rootView: SettingsView(
                settings: settings, launchAtLogin: launchAtLogin, onChange: onChange,
                status: status
            )
            .prudenceTheme(.system)
        )
        window.delegate = self
    }

    func show() { window.makeKeyAndOrderFront(nil) }

    func windowWillClose(_ notification: Notification) {
        DispatchQueue.main.async { [onClose] in onClose() }
    }
}
