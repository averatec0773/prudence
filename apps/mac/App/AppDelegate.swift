import AppKit
import PrudenceModels
import SwiftUI

/// Owns the one status item, the one window and the one view model.
///
/// The activation policy starts at `.accessory`: no Dock icon, no menu bar of our own, which
/// is what `LSUIElement` in the Info.plist asks for and what a menu bar app should be. It
/// becomes `.regular` only while the main window is open, so that Cmd-Tab and the Dock icon
/// work while there is something to switch to (M3 plan, open question 1, accepted default).
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {

    private let settings = AppSettings()
    private lazy var model = MenuViewModel(settings: settings)
    /// The window has its own model. It reads far more than the dropdown does and it reads it
    /// only while it is open, so sharing one would make the dropdown pay for charts nobody
    /// is looking at.
    private lazy var windowModel = WindowModel(settings: settings)
    private lazy var launchAtLogin = SMAppServiceLaunchAtLogin()
    private var statusItem: StatusItemController?
    private var mainWindow: MainWindowController?
    private var settingsWindow: SettingsWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        Self.applyForcedAppearance()
        statusItem = StatusItemController(
            model: model,
            actions: MenuActions(
                openMain: { [weak self] in self?.openMainWindow() },
                openSettings: { [weak self] in self?.openSettings() },
                quit: { NSApp.terminate(nil) }
            )
        )
        model.start()
        // An agent verifying a build against a copy of the store cannot click a menu bar
        // item, and there is no supported way to script one. `PRUDENCE_OPEN_WINDOW=1` asks
        // for the window at launch instead. Nothing a user does sets it.
        if ProcessInfo.processInfo.environment["PRUDENCE_OPEN_WINDOW"] != nil {
            openMainWindow()
        }
        // The same problem one step worse: a menu bar popover cannot be opened by script at
        // all, and the popover is the surface whose material bug batch 3 had to photograph.
        // `PRUDENCE_OPEN_POPOVER=1` shows it at launch so `screencapture` has something to
        // take a picture of. Nothing a user does sets it.
        if let mode = ProcessInfo.processInfo.environment["PRUDENCE_OPEN_POPOVER"] {
            statusItem?.openPopover(watching: mode == "dismissable")
        }
    }

    /// `PRUDENCE_FORCE_APPEARANCE=dark` (or `light`) pins the whole process's appearance.
    ///
    /// `defaults write -g AppleInterfaceStyle` changes the Mac, and `defaults write -app`
    /// needs an installed, launch-services-known app, so neither is available to an agent
    /// checking a build out of `build/dd`. This is the one hook that makes "the real app, in
    /// dark" reproducible from a terminal. Unset, the app follows the system as before.
    private static func applyForcedAppearance() {
        switch ProcessInfo.processInfo.environment["PRUDENCE_FORCE_APPEARANCE"] {
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        default: break
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.stop()
    }

    /// Clicking the Dock icon while the window is shut should bring it back, not do nothing.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if !hasVisibleWindows { openMainWindow() }
        return true
    }

    func openMainWindow() {
        statusItem?.closePopover()
        if mainWindow == nil {
            mainWindow = MainWindowController(
                model: windowModel,
                settings: settings,
                launchAtLogin: launchAtLogin,
                onSettingsChange: { [weak self] in self?.model.startIngestTimer() },
                onClose: { [weak self] in self?.windowClosed() }
            )
        }
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        mainWindow?.show()
    }

    func openSettings() {
        statusItem?.closePopover()
        if settingsWindow == nil {
            settingsWindow = SettingsWindowController(
                settings: settings,
                launchAtLogin: launchAtLogin,
                status: { [weak self] in self?.model.snapshot.status },
                onChange: { [weak self] in self?.model.startIngestTimer() },
                onClose: { [weak self] in self?.windowClosed() }
            )
        }
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow?.show()
    }

    /// Back to an accessory app once the last window of our own has gone.
    private func windowClosed() {
        let stillOpen = NSApp.windows.contains { $0.isVisible && $0.canBecomeMain }
        if !stillOpen { NSApp.setActivationPolicy(.accessory) }
    }
}
