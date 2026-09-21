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
    private lazy var launchAtLogin = SMAppServiceLaunchAtLogin()
    private var statusItem: StatusItemController?
    private var mainWindow: MainWindowController?
    private var settingsWindow: SettingsWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = StatusItemController(
            model: model,
            actions: MenuActions(
                openMain: { [weak self] in self?.openMainWindow() },
                openSettings: { [weak self] in self?.openSettings() },
                quit: { NSApp.terminate(nil) }
            )
        )
        model.start()
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
                model: model,
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
