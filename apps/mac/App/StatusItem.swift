import AppKit
import PrudenceModels
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

    init(model: MenuViewModel, actions: MenuActions) {
        self.model = model
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        super.init()

        if let button = item.button {
            // A template image, so the glyph follows the menu bar in light and dark and while
            // a Space's wallpaper changes under it.
            let image = NSImage(named: "StatusGlyph") ?? NSImage(
                systemSymbolName: "chart.bar.doc.horizontal",
                accessibilityDescription: "Prudence")
            image?.isTemplate = true
            button.image = image
            button.imagePosition = .imageOnly
            button.toolTip = "Prudence"
            button.target = self
            button.action = #selector(togglePopover)
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        var actions = actions
        actions.willAct = { [weak self] in self?.closePopover() }
        popover.behavior = .transient
        popover.animates = false
        popover.delegate = self
        popover.contentViewController = NSHostingController(
            rootView: MenuContentView(model: model, actions: actions)
        )
    }

    @objc private func togglePopover() {
        if popover.isShown {
            closePopover()
        } else {
            showPopover()
        }
    }

    private func showPopover() {
        guard let button = item.button else { return }
        // The numbers are re-read every time the dropdown opens, which is the behaviour
        // `MenuBarExtra` cannot give us.
        model.refresh()
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    func closePopover() {
        if popover.isShown { popover.performClose(nil) }
    }
}
