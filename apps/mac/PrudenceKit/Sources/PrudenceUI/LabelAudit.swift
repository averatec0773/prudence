import AppKit
import SwiftUI

/// Does the label still reach the screen once the material has been put on the control?
///
/// This exists because of one bug and the shape of it (batch 3). The three frosted buttons in
/// the menu bar popover rendered as **blank rectangles** on macOS 26: the material was drawn by
/// `glassEffect` on an empty `Color.clear` handed to `.background(...)`, and inside a
/// `GlassEffectContainer` the container's merged glass pass carried no label with it and came
/// out over the text. Every automatic check the app had was green. The strings were right, the
/// layout was right, `swift test` passed, and the render harness drew readable labels. Only the
/// founder's eyes knew.
///
/// Three ways of catching it were tried before this one, and the two that failed are worth
/// writing down so nobody spends the afternoon again:
///
/// 1. **The accessibility tree, in process.** `NSHostingView.accessibilityChildren()` is empty
///    for a SwiftUI view in a window that no assistive client has asked about, and asking
///    through `AXUIElementCreateApplication(getpid())` answers with nothing either. AppKit
///    builds that tree for an external client and not for the process itself, so there is no
///    label in it to assert on — not after the fix, and not before it.
/// 2. **Comparing the bitmap with a stored one.** The labels *are* in the bitmap the harness
///    makes, before the fix as well as after, because `cacheDisplay(in:to:)` has no backdrop
///    to sample and draws `glassEffect` as a no-op.
///
/// What is left is the property itself, asked directly: **render the control twice, once with
/// its label and once without, and require the two pictures to differ.** A control whose label
/// has been covered by anything at all — a material, an overlay, a foreground style that
/// resolved to the fill — renders identically with and without its text, and that is exactly
/// what the founder photographed. It needs no fixtures, no thresholds and no stored images.
///
/// **What it covers, and what it does not — measured, not assumed.** The original bug was
/// re-applied on purpose and this audit was run against it in three forms:
///
/// | Form | Caught the original bug? |
/// |---|---|
/// | off screen, `cacheDisplay` (`swift test`, every `shots.sh`) | no |
/// | on screen, an ordinary window through the window server | no |
/// | on screen, a real `NSPopover` through the window server | no |
///
/// So this is **not** a reproduction of that bug. What it is, is a guard against the class it
/// belongs to: an opaque overlay put over a label makes every one of those forms fail, which
/// was checked the same way. The macOS 26 popover case needs the shipping app, a menu bar and
/// an active application, and the only thing that shows it is a picture of the real thing:
/// `PRUDENCE_OPEN_POPOVER=1 PRUDENCE_FORCE_APPEARANCE=dark` and `screencapture`, written down
/// in `apps/mac/README.md`. **That procedure is the check for anything about the material**,
/// and this audit is the cheap net underneath it, not a replacement for it.
///
/// `PRUDENCE_SHOTS_ONSCREEN=1` still buys something real: the picture is taken through the
/// window server, where macOS 26's glass is actually composited rather than drawn as a no-op,
/// so a material that covers a label in a plain window is caught there and nowhere else. It
/// needs a window server and the screen-recording permission, so it is opt-in.
public enum LabelAudit {

    /// One view, rendered off-screen at a pinned appearance and scale, as raw pixels.
    ///
    /// The same route `Render/main.swift` takes for a shot: `cacheDisplay(in:to:)` rather than
    /// `displayIgnoringOpacity`, which draws SwiftUI `Text` invisibly, and a bitmap built by
    /// hand at one pixel per point so two renders on different Macs are comparable.
    @MainActor
    public static func pixels<Content: View>(
        of view: Content,
        size: CGSize,
        appearance: NSAppearance?,
        onScreen: Bool = false
    ) -> Data? {
        let hosting = NSHostingView(rootView: view)
        if let appearance { hosting.appearance = appearance }
        hosting.frame = NSRect(origin: .zero, size: size)
        hosting.layoutSubtreeIfNeeded()
        let window = NSWindow(
            contentRect: hosting.frame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        if let appearance { window.appearance = appearance }
        window.contentView = hosting
        hosting.layoutSubtreeIfNeeded()
        if onScreen { return throughTheWindowServer(window) }
        guard
            let representation = NSBitmapImageRep(
                bitmapDataPlanes: nil,
                pixelsWide: Int(size.width.rounded()),
                pixelsHigh: Int(size.height.rounded()),
                bitsPerSample: 8,
                samplesPerPixel: 4,
                hasAlpha: true,
                isPlanar: false,
                colorSpaceName: .deviceRGB,
                bytesPerRow: 0,
                bitsPerPixel: 0
            )
        else { return nil }
        representation.size = size
        hosting.cacheDisplay(in: hosting.bounds, to: representation)
        return representation.representation(using: .png, properties: [:])
    }

    /// True when a control drawn with `label` looks different from the same control drawn with
    /// nothing in it — which is to say, when its label reaches the screen.
    ///
    /// `build` takes the text so the caller decides what the control is; everything else about
    /// the two renders is identical, so any difference between them is the label and nothing
    /// else.
    @MainActor
    public static func labelIsVisible<Content: View>(
        _ label: String,
        size: CGSize,
        appearance: NSAppearance? = nil,
        onScreen: Bool = false,
        build: (String) -> Content
    ) -> Bool {
        guard
            let withLabel = pixels(
                of: build(label), size: size, appearance: appearance, onScreen: onScreen),
            let without = pixels(
                of: build(""), size: size, appearance: appearance, onScreen: onScreen)
        else { return false }
        return withLabel != without
    }

    /// The same window, ordered in and photographed by the window server.
    ///
    /// This is the only route on which macOS 26's `glassEffect` is really composited: the
    /// material samples what is behind the window, and an off-screen bitmap context has no
    /// behind. The window is put at the far corner of the screen, kept for a turn of the run
    /// loop so the compositor has drawn it, captured, and ordered straight back out.
    ///
    /// It needs a window server and the screen-recording permission, so it is opt-in
    /// (`PRUDENCE_SHOTS_ONSCREEN=1`). A capture that is refused answers nil, and the caller
    /// reports that as a failed audit rather than as a pass, because "the picture could not be
    /// taken" is not "the label was there".
    @MainActor
    private static func throughTheWindowServer(_ window: NSWindow) -> Data? {
        let screen = NSScreen.main ?? NSScreen.screens.first
        if let screen {
            window.setFrameOrigin(
                NSPoint(x: screen.frame.maxX - window.frame.width - 1, y: screen.frame.minY + 1))
        }
        window.level = .statusBar
        window.orderFrontRegardless()
        defer { window.orderOut(nil) }
        RunLoop.current.run(until: Date().addingTimeInterval(0.12))
        return capture(window)
    }

    @MainActor
    private static func capture(_ window: NSWindow) -> Data? {
        let id = CGWindowID(window.windowNumber)
        // Deprecated in favour of ScreenCaptureKit, and kept deliberately: this is a
        // synchronous one-window grab inside a command line tool that has no run loop of its
        // own to await an `SCStream` on, and the replacement's asynchronous session would be
        // a great deal of machinery for a picture that is thrown away two lines later. It
        // still works on macOS 26. If a later system removes it, this is the one call to move.
        guard
            let image = CGWindowListCreateImage(
                .null, .optionIncludingWindow, id, [.boundsIgnoreFraming, .bestResolution])
        else { return nil }
        let representation = NSBitmapImageRep(cgImage: image)
        return representation.representation(using: .png, properties: [:])
    }

    /// The same comparison, but inside a **real `NSPopover`**.
    ///
    /// This is the surface the bug was on, and it turned out to matter: the same buttons in an
    /// ordinary borderless window, photographed the same way through the window server, drew
    /// their labels perfectly well with the broken code. An `NSPopover` brings its own backing
    /// material, and a `glassEffect` inside that is what the merged pass landed over.
    ///
    /// It needs a window server and the screen-recording permission, like the other on-screen
    /// route, so it runs only under `PRUDENCE_SHOTS_ONSCREEN=1`. A capture that is refused
    /// answers nil, which the caller reports as a failure: "the picture could not be taken" is
    /// not "the label was there".
    @MainActor
    public static func labelIsVisibleInAPopover<Content: View>(
        _ label: String,
        size: CGSize,
        appearance: NSAppearance?,
        build: (String) -> Content
    ) -> Bool {
        guard
            let withLabel = popoverPixels(
                of: build(label), size: size, appearance: appearance),
            let without = popoverPixels(of: build(""), size: size, appearance: appearance)
        else { return false }
        return withLabel != without
    }

    @MainActor
    private static func popoverPixels<Content: View>(
        of view: Content, size: CGSize, appearance: NSAppearance?
    ) -> Data? {
        let screen = NSScreen.main ?? NSScreen.screens.first
        let origin = NSPoint(
            x: (screen?.frame.maxX ?? 800) - 200, y: (screen?.frame.maxY ?? 600) - 20)
        let anchor = NSWindow(
            contentRect: NSRect(origin: origin, size: NSSize(width: 1, height: 1)),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        anchor.isOpaque = false
        anchor.backgroundColor = .clear
        anchor.level = .statusBar
        if let appearance { anchor.appearance = appearance }
        anchor.orderFrontRegardless()
        defer { anchor.orderOut(nil) }

        let popover = NSPopover()
        popover.behavior = .applicationDefined
        popover.animates = false
        let controller = NSHostingController(rootView: view)
        controller.preferredContentSize = size
        popover.contentViewController = controller
        if let appearance { popover.appearance = appearance }
        guard let anchorView = anchor.contentView else { return nil }
        popover.show(relativeTo: anchorView.bounds, of: anchorView, preferredEdge: .minY)
        defer { popover.performClose(nil) }
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        guard let window = popover.contentViewController?.view.window else { return nil }
        return capture(window)
    }
}
