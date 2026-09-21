import SwiftUI

/// The control styles.
///
/// NOTES.md's Material section, in Swift: a button is a flat frosted 8 pt rounded rect, 30 pt
/// tall in a window and 28 in the popover, 15 pt of horizontal padding, a semibold 13 pt
/// label, one hairline edge and a top inner highlight that is barely there. No specular
/// sweep, no bottom shading, **no drop shadow**: a control's only shadow is its ring, while
/// the popover and the window keep theirs. Hover brightens the tint by a few per cent, press
/// darkens it and **nothing moves**, and focus is the system's own accent ring. The prominent
/// action is the accent at 92 per cent behind the same frost with a white label and no
/// gradient.
///
/// **Everything else shaped like a control is a system control and is not redrawn.** The
/// segmented control is `Picker(...).pickerStyle(.segmented)`, the project and review pickers
/// are `.pickerStyle(.menu)`, the switches are `Toggle`, the path rows are `TextField` plus a
/// `Button` opening `NSOpenPanel`. On macOS 26 those already draw themselves in the system
/// material; asking for `.buttonStyle(.glass)` or `.glassProminent` on top of a system control
/// would be a second material over the first. The two styles below exist only because the
/// popover's actions have to look identical on macOS 14, where there is no glass at all.

public struct PrudenceButtonStyle: ButtonStyle {

    public enum Emphasis: Sendable { case normal, prominent, plain }

    var emphasis: Emphasis
    var height: CGFloat
    /// True when the drawn control should take the whole width it is offered.
    ///
    /// Batch 3. A `.frame(maxWidth: .infinity)` at the call site widens the *button*, not the
    /// shape a `ButtonStyle` draws: before this flag existed the pill kept its label's width
    /// and floated in the middle of its cell, which is what the founder read as "the buttons
    /// are not aligned". Off by default, because the same style is used in toolbar strips and
    /// in message rows where a greedy button would push everything else out.
    var fills: Bool

    public init(emphasis: Emphasis = .normal, height: CGFloat = 28, fills: Bool = false) {
        self.emphasis = emphasis
        self.height = height
        self.fills = fills
    }

    public func makeBody(configuration: Configuration) -> some View {
        PrudenceButtonBody(
            configuration: configuration, emphasis: emphasis, height: height, fills: fills)
    }
}

extension ButtonStyle where Self == PrudenceButtonStyle {
    /// The one prominent action per surface.
    public static var prudencePrimary: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .prominent)
    }
    /// The same, filling the width it is offered. The popover's `Open Prudence`.
    public static var prudencePrimaryWide: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .prominent, fills: true)
    }
    /// Everything else with a frame around it.
    public static var prudence: PrudenceButtonStyle { PrudenceButtonStyle() }
    /// The same, filling its cell. The popover's `Review now` and `Ingest now`.
    public static var prudenceWide: PrudenceButtonStyle {
        PrudenceButtonStyle(fills: true)
    }
    /// Quit, and anything else that should not look like an action.
    public static var prudencePlain: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .plain)
    }
}

/// A `View` rather than the style's own body, because a `ButtonStyle` cannot hold `@State`
/// and hover is a state.
private struct PrudenceButtonBody: View {

    let configuration: ButtonStyle.Configuration
    let emphasis: PrudenceButtonStyle.Emphasis
    let height: CGFloat
    let fills: Bool

    @Environment(\.prudenceTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovering = false

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: Radius.glassControl, style: .continuous)
    }

    var body: some View {
        skinned
            .contentShape(shape)
            .opacity(isEnabled ? 1 : 0.45)
            .onHover { hovering = $0 }
            // Press darkens the tint; nothing moves, so the label never jumps under the
            // pointer. That is the one thing a flat control must get right.
            .animation(Motion.hover, value: hovering)
            .animation(Motion.hover, value: configuration.isPressed)
            // A plain button is text on a grid line, so its own padding is taken back out
            // again: the hover wash keeps its breathing room and the glyphs start exactly on
            // the edge the rows above them start on.
            .padding(.horizontal, emphasis == .plain ? -Space.s2 : 0)
    }

    /// The label, sized, with the hover and press washes behind it.
    private var core: some View {
        configuration.label
            .font(Type.footnoteStrong)
            .foregroundStyle(foreground)
            .padding(.horizontal, emphasis == .plain ? Space.s2 : 15)
            .frame(maxWidth: fills ? .infinity : nil)
            .frame(height: height)
            .background(washes)
    }

    /// **The material goes behind the label, never in front of it.**
    ///
    /// This is the batch 3 bug, and the whole of its fix. The frosted emphasis used to draw
    /// its material as `.background(Color.clear.prudenceGlass(.control))`, which asks macOS 26
    /// for a `glassEffect` on an *empty* view and then hands that view to the background slot.
    /// Inside a `GlassEffectContainer` the container gathers its descendants' glass shapes and
    /// composites them in one pass of its own, and a shape whose only content is `Color.clear`
    /// carries no label into that pass: on a real screen the merged glass landed over the
    /// labels and the three `.prudence` buttons in the popover came out as blank frosted
    /// rectangles, while `.prudencePrimary` and `.prudencePlain`, which never call
    /// `glassEffect`, kept their text. The off-screen harness could not show it, because
    /// `cacheDisplay(in:to:)` has no backdrop to sample and draws the effect as a no-op.
    ///
    /// `glassEffect(_:in:)` is documented as putting the material **behind the view it is
    /// applied to**, so applying it to the labelled view is both the fix and the intended use,
    /// and it is the same one call on the `NSVisualEffectView` path and the opaque one.
    /// `UITests.everyPopoverButtonLabelSurvivesTheMaterial` renders the popover through this
    /// path and fails if a label stops reaching the view tree.
    @ViewBuilder
    private var skinned: some View {
        switch emphasis {
        case .plain:
            // Borderless: a hover wash and nothing else, and no material at all.
            core.background(shape.fill(hovering ? Surface.sunken : Color.clear))
        case .normal:
            core.prudenceGlass(.control)
        case .prominent:
            switch theme.primary {
            case .accent:
                // Variant A: the accent at 92 per cent over the same frost, a white label,
                // one hairline edge, no gradient. NOTES.md's own words.
                core
                    .background(
                        shape.fill(Ink.accent.opacity(0.92))
                            .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
                    )
                    .prudenceGlass(.control)
            case .tinted:
                // Variant B: the quieter one the founder asked to see beside A. The same
                // frost, a soft accent wash instead of a fill, and the label in the accent.
                core
                    .background(
                        shape.fill(Ink.accentSoft)
                            .overlay(shape.strokeBorder(Ink.accent.opacity(0.35), lineWidth: 1))
                    )
                    .prudenceGlass(.control)
            }
        }
    }

    private var foreground: Color {
        switch emphasis {
        case .prominent: return theme.primary == .accent ? Ink.onAccent : Ink.accent
        case .normal: return Ink.primary
        case .plain: return Ink.secondary
        }
    }

    /// Hover, press, and the faint top inner highlight, in one layer behind the label.
    ///
    /// The prominent action has **no gradient** (NOTES.md), which is what made the founder
    /// read the old one as a pill from an earlier era, so the highlight is drawn for the
    /// frosted emphases only.
    @ViewBuilder
    private var washes: some View {
        ZStack {
            shape.fill(overlayTint)
            if emphasis == .normal || theme.primary == .tinted { topHighlight }
        }
        .allowsHitTesting(false)
    }

    /// Hover brightens by a few per cent, press darkens. Both are a wash over the tint, never
    /// a second material.
    private var overlayTint: Color {
        if configuration.isPressed { return Color.black.opacity(0.10) }
        if hovering { return Color.white.opacity(0.08) }
        return .clear
    }

    /// The faint top inner highlight. One gradient, a third of the height, and gone.
    private var topHighlight: some View {
        LinearGradient(
            colors: [Color.white.opacity(0.22), Color.white.opacity(0)],
            startPoint: .top,
            endPoint: .bottom
        )
        .frame(height: height / 3)
        .frame(maxHeight: .infinity, alignment: .top)
        .clipShape(shape)
    }
}

// MARK: - the frosted strip a cluster of controls sits on

/// The toolbar strip above a screen, and the popover's own footer: glass on the control layer,
/// one sampling pass for the whole cluster.
public struct ControlStrip<Content: View>: View {

    var spacing: CGFloat
    var alignment: VerticalAlignment
    @ViewBuilder var content: Content

    public init(
        spacing: CGFloat = Space.s2,
        alignment: VerticalAlignment = .center,
        @ViewBuilder content: () -> Content
    ) {
        self.spacing = spacing
        self.alignment = alignment
        self.content = content()
    }

    public var body: some View {
        HStack(alignment: alignment, spacing: spacing) { content }
            .prudenceGlassCluster(spacing: spacing)
    }
}
