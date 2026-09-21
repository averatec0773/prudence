import SwiftUI

/// The entry point, and almost nothing else.
///
/// There is no `MenuBarExtra` scene and no `Settings` scene here; the status item, the window
/// and the settings panel are all built in AppKit by `AppDelegate`, for the reasons written at
/// the top of `StatusItem.swift`. SwiftUI's job in this app starts inside the popover.
///
/// `Settings {}` would be the obvious way to get the standard Cmd-, menu item, but a `Settings`
/// scene in an `LSUIElement` app is one of the documented broken cases (research note, section
/// 2), so the window is opened by hand instead.
@main
struct PrudenceApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        // An app with no windows of its own. Every surface is created by the delegate.
        Settings {
            EmptyView()
        }
    }
}
