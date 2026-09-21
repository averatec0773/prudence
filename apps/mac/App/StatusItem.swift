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
