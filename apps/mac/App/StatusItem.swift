import AppKit
import PrudenceModels
import PrudenceUI
import SwiftUI

/// The menu bar item: `NSStatusItem` and `NSPopover`, deliberately not `MenuBarExtra`.
///
/// Why not `MenuBarExtra`, so that nobody re-litigates it next session (research note,
/// section 2; this is a convention, see `apps/mac/README.md`):
///
/// - SwiftUI still has no first-party way to close a `.window` popup from a control inside
///   it (FB11984872, open since February 2023). Every button in this dropdown has to close it.
/// - There is no way to be told the user opened the popup, so a dropdown of "today's numbers"
///   shows whatever it last computed. This one refreshes on open, which is the whole point.
/// - The underlying `NSStatusItem` and the popup's window are unreachable, so the glyph, the
///   right-click behaviour and the popover's edge are not ours to set.
/// - Decaf, whose shape this app otherwise copies, ships a `StatusItemBridge.swift` whose only
///   job is to walk the window list and hijack what `MenuBarExtra` created. That file is the
///   argument against `MenuBarExtra`, written by somebody who tried it.
///
/// The cost is about eighty lines of AppKit, all of it here. Everything inside the popover is
/// ordinary SwiftUI.
@MainActor
final class StatusItemController: NSObject, NSPopoverDelegate {

    private let item: NSStatusItem
    private let popover = NSPopover()
    private let model: MenuViewModel
    private var globalClicks: Any?
    private var localKeys: Any?
    private var resignObserver: (any NSObjectProtocol)?

    init(model: MenuViewModel, actions: MenuActions) {
        self.model = model
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        super.init()

        if let button = item.button {
            // The real mark, from `assets/brand/logo-glyph-template.svg`: the mark with its
            // two bowl pieces merged, because at 16 pt its own 20-unit gaps fall under a
            // point and read as noise. A template image, so the glyph follows the menu bar in
            // light and dark and while a Space's wallpaper changes under it. The asset
            // catalog's copy is preferred; the package's own is the fallback for the render
            // harness, which has no catalog.
            let image =
                NSImage(named: "StatusGlyph")
                ?? Brand.image(.glyph, size: 16)
                ?? NSImage(
                    systemSymbolName: "chart.bar.doc.horizontal",
                    accessibilityDescription: Product.name)
            image?.isTemplate = true
            image?.size = NSSize(width: 16, height: 16)
            button.image = image
            button.imagePosition = .imageOnly
            button.toolTip = Product.name
            button.target = self
            button.action = #selector(togglePopover)
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        var actions = actions
        actions.willAct = { [weak self] in self?.closePopover() }
        popover.behavior = .transient
        popover.animates = false
        popover.delegate = self
        // The popover is the control layer, so it is the one surface made of glass. The theme
        // is read once here rather than per view, so that reduced transparency is answered
        // the same way by every piece inside it.
        popover.contentViewController = NSHostingController(
            rootView: MenuContentView(model: model, actions: actions)
                .prudenceTheme(.system)
        )
    }

    @objc private func togglePopover() {
        if popover.isShown {
            closePopover()
        } else {
            showPopover()
        }
    }

    /// Show the dropdown without a click. `PRUDENCE_OPEN_POPOVER=1` is the only caller.
    ///
    /// Two things have to be undone for a screenshot to be possible at all, and both are
    /// confined to this method so the shipping behaviour is untouched:
    ///
    /// - **The behaviour is pinned to `.applicationDefined`.** A `.transient` popover closes
    ///   the instant another app is frontmost, and an agent running `screencapture` from a
    ///   terminal is always another app.
    /// - **The popover hangs off an anchor window rather than off the status item.** A second
    ///   copy of the app with the same bundle identifier, or a menu bar with no room left in
    ///   it, gets a status item that is never shown, and `NSPopover` cannot hang off a button
    ///   nobody can see. The anchor is a 1 pt borderless window at the top right of the main
    ///   screen: the popover, its hosting controller and `MenuContentView` are the shipping
    ///   ones, so what the picture shows is what a user sees.
    /// - **Nothing watches for a dismissal unless `watching` says so.** A screenshot needs the
    ///   popover to stay up; `PRUDENCE_OPEN_POPOVER=dismissable` asks for the real monitors
    ///   instead, which is how the outside-click fix is checked without a human clicking.
    func openPopover(watching: Bool = false) {
        popover.behavior = watching ? .transient : .applicationDefined
        model.refresh()
        let anchor = anchorWindow()
        guard let view = anchor.contentView else { return }
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
        if watching { startWatchingForDismissal() }
    }

    private var anchor: NSWindow?

    private func anchorWindow() -> NSWindow {
        if let anchor { return anchor }
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let origin = NSPoint(
            x: screen.frame.maxX - 200, y: screen.frame.maxY - screen.frame.height * 0.02)
        let window = NSWindow(
            contentRect: NSRect(origin: origin, size: NSSize(width: 1, height: 1)),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .statusBar
        window.orderFrontRegardless()
        anchor = window
        return window
    }

    private func showPopover() {
        guard let button = item.button else { return }
        // The numbers are re-read every time the dropdown opens, which is the behaviour
        // `MenuBarExtra` cannot give us.
        model.refresh()
        // Before `show`, not after: `.transient` dismisses on an event the popover's own
        // window receives, and an `.accessory` app that never became active does not receive
        // one. Activating first is what makes the popover a window the click can land in.
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
        startWatchingForDismissal()
    }

    func closePopover() {
        stopWatchingForDismissal()
        if popover.isShown { popover.performClose(nil) }
    }

    /// The popover is closed by `performClose` above, by the delegate below, or by the user
    /// clicking the status item again; every one of those has to take the monitors down.
    func popoverDidClose(_ notification: Notification) {
        stopWatchingForDismissal()
    }

    // MARK: - closing it the four ways a user expects

    /// Why this exists at all, since `NSPopover.behavior = .transient` is supposed to be it.
    ///
    /// `.transient` closes on the next event **its own window sees**. An `LSUIElement` app is
    /// `.accessory`, so the app is frequently not active when the dropdown opens, and a click
    /// in another application is then delivered to that application and never to us: the
    /// popover stayed up and the only way to dismiss it was to click the status item again,
    /// which is what the founder hit. `NSApp.activate(ignoringOtherApps:)` in `showPopover`
    /// fixes the common case, and these three monitors cover the rest:
    ///
    /// - a **global** mouse-down monitor, which sees clicks that go to other applications and
    ///   never sees our own, so it cannot close the popover out from under its own buttons;
    /// - a **local** key-down monitor for Esc, which the popover's own window receives;
    /// - `didResignActiveNotification`, for Cmd-Tab and the Mission Control cases where no
    ///   click of ours is involved at all.
    ///
    /// All three are torn down the moment the popover closes, because a global event monitor
    /// that outlives the thing it was watching is a leak that keeps waking the process.
    private func startWatchingForDismissal() {
        stopWatchingForDismissal()
        globalClicks = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown]
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.closePopover() }
        }
        localKeys = NSEvent.addLocalMonitorForEvents(matching: [.keyDown]) { [weak self] event in
            // 53 is Esc. Swallowed rather than passed on, so the key that closed the dropdown
            // does not also reach whatever is behind it.
            guard event.keyCode == 53 else { return event }
            MainActor.assumeIsolated { self?.closePopover() }
            return nil
        }
        resignObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didResignActiveNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.closePopover() }
        }
    }

    private func stopWatchingForDismissal() {
        if let globalClicks { NSEvent.removeMonitor(globalClicks) }
        if let localKeys { NSEvent.removeMonitor(localKeys) }
        if let resignObserver { NotificationCenter.default.removeObserver(resignObserver) }
        globalClicks = nil
        localKeys = nil
        resignObserver = nil
    }
}
