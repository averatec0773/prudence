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

    public init(emphasis: Emphasis = .normal, height: CGFloat = 28) {
        self.emphasis = emphasis
        self.height = height
    }

    public func makeBody(configuration: Configuration) -> some View {
        PrudenceButtonBody(
            configuration: configuration, emphasis: emphasis, height: height)
    }
}

extension ButtonStyle where Self == PrudenceButtonStyle {
    /// The one prominent action per surface.
    public static var prudencePrimary: PrudenceButtonStyle {
        PrudenceButtonStyle(emphasis: .prominent)
    }
    /// Everything else with a frame around it.
    public static var prudence: PrudenceButtonStyle { PrudenceButtonStyle() }
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

    @Environment(\.prudenceTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovering = false

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: Radius.glassControl, style: .continuous)
    }

    var body: some View {
        configuration.label
            .font(Type.footnoteStrong)
            .foregroundStyle(foreground)
            .padding(.horizontal, emphasis == .plain ? Space.s2 : 15)
            .frame(height: height)
            .background(background)
            .contentShape(shape)
            .opacity(isEnabled ? 1 : 0.45)
            .onHover { hovering = $0 }
            // Press darkens the tint; nothing moves, so the label never jumps under the
            // pointer. That is the one thing a flat control must get right.
            .animation(Motion.hover, value: hovering)
            .animation(Motion.hover, value: configuration.isPressed)
    }

    private var foreground: Color {
        switch emphasis {
        case .prominent: return Ink.onAccent
        case .normal: return Ink.primary
        case .plain: return Ink.secondary
        }
    }

    @ViewBuilder
    private var background: some View {
        switch emphasis {
        case .plain:
            // Borderless: a hover wash and nothing else.
            shape.fill(hovering ? Surface.sunken : Color.clear)
        case .prominent:
            shape
                .fill(Ink.accent.opacity(0.92))
                .overlay(shape.fill(overlayTint))
                .overlay(topHighlight)
                .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
        case .normal:
            Color.clear
                .prudenceGlass(.control)
                .overlay(shape.fill(overlayTint))
                .overlay(topHighlight)
        }
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
        .allowsHitTesting(false)
    }
}

// MARK: - the frosted strip a cluster of controls sits on

/// The toolbar strip above a screen, and the popover's own footer: glass on the control layer,
/// one sampling pass for the whole cluster.
public struct ControlStrip<Content: View>: View {

    var spacing: CGFloat
    @ViewBuilder var content: Content

    public init(spacing: CGFloat = Space.s2, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.content = content()
    }

    public var body: some View {
        HStack(spacing: spacing) { content }
            .prudenceGlassCluster(spacing: spacing)
    }
}
