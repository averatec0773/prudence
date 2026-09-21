import SwiftUI

/// The control styles.
///
/// **Three styles and no fourth**, all on one 8 pt rounded rect, all 28 pt tall, all carrying
/// a semibold 13 pt label, and none of them beveled, gradient-filled or shadowed:
///
/// | Style | Fill | Edge | Label |
/// |---|---|---|---|
/// | primary | the accent at 92 % behind the same frost | 0.5 pt `Surface.hairline` | white |
/// | secondary | a flat quiet fill (`Surface.control`), or the popover's own frost at control strength under Glass | 0.5 pt `Surface.separator` | `Ink.primary` |
/// | plain | none | none | `Ink.secondary`, the accent under the pointer |
///
/// The founder read the old set as retro, and the two things that made it so are gone: the top
/// inner highlight (a bevel by another name) and the second prominent variant. Hover raises the
/// fill by a few per cent, press lowers it, **nothing moves**, a plain button changes only its
/// ink, and focus is the system's own accent ring.
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
    /// The one prominent action per surface: the accent at 92 % behind the frost.
    public static var prudencePrimary: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .prominent)
    }
    /// The same, filling the width it is offered. The popover's `Open Prudence`.
    public static var prudencePrimaryWide: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .prominent, fills: true)
    }
    /// The secondary action: `Review now`, `Ingest now`, `Choose...`, `Write anyway`.
    public static var prudence: PrudenceButtonStyle { PrudenceButtonStyle() }
    /// The same, filling its cell. The popover's `Review now` and `Ingest now`.
    public static var prudenceWide: PrudenceButtonStyle {
        PrudenceButtonStyle(fills: true)
    }
    /// `Settings...`, `Quit`, `Dismiss`: a label on the grid line and nothing else.
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
    }

    /// The label, sized, with the hover and press wash behind it.
    ///
    /// A plain button has **no** horizontal padding of its own: it is a label on the grid
    /// line, so its glyphs start exactly on the edge the rows above it start on, and it keeps
    /// the same 28 pt row height so its baseline lands where the filled rows' baselines do.
    private var core: some View {
        configuration.label
            .font(Type.footnoteStrong)
            .foregroundStyle(foreground)
            .padding(.horizontal, emphasis == .plain ? 0 : 15)
            .frame(maxWidth: fills ? .infinity : nil)
            .frame(height: height)
            .background(shape.fill(overlayTint).allowsHitTesting(false))
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
            // No fill, no edge, no material: the ink is the whole of it.
            core
        case .normal:
            if theme.wantsTranslucency {
                // Under Glass the fill is the frost the popover itself uses, at control
                // strength, so a secondary button and the surface behind it are one material.
                core.prudenceGlass(.control).overlay(edge)
            } else {
                // Opaque: one flat quiet fill, whose alpha is the only thing hover and press
                // move. No highlight, no bevel, no shadow.
                core.background(shape.fill(quietFill)).overlay(edge)
            }
        case .prominent:
            // The accent at 92 per cent over the same frost, a white label, one hairline
            // edge, no gradient. NOTES.md's own words, and the founder's choice.
            core
                .background(
                    shape.fill(Ink.accent.opacity(0.92))
                        .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
                )
                .prudenceGlass(.control)
        }
    }

    /// The one hairline a secondary control carries, in the separator colour.
    private var edge: some View {
        shape.strokeBorder(Surface.separator, lineWidth: 0.5)
    }

    private var foreground: Color {
        switch emphasis {
        case .prominent: return Ink.onAccent
        case .normal: return Ink.primary
        // A plain button has no fill to brighten, so the pointer moves its ink to the accent
        // instead. No underline: a link is not a control.
        case .plain: return hovering ? Ink.accent : Ink.secondary
        }
    }

    /// The flat fill of a secondary control on an opaque surface. Hover raises it by a few
    /// per cent, press lowers it, and nothing moves.
    private var quietFill: Color {
        if configuration.isPressed { return Surface.controlPressed }
        if hovering { return Surface.controlHover }
        return Surface.control
    }

    /// Hover and press as a wash above the fill, for the two styles whose fill cannot carry
    /// the state itself: the accent slab, and a secondary control whose fill is the frost.
    /// Empty everywhere else, so a plain button never grows a background.
    private var overlayTint: Color {
        switch emphasis {
        case .plain: return .clear
        case .normal:
            guard theme.wantsTranslucency else { return .clear }
            if configuration.isPressed { return Color.black.opacity(0.06) }
            if hovering { return Color.white.opacity(0.08) }
            return .clear
        case .prominent:
            if configuration.isPressed { return Color.black.opacity(0.10) }
            if hovering { return Color.white.opacity(0.08) }
            return .clear
        }
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
