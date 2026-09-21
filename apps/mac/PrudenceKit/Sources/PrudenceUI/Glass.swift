import AppKit
import SwiftUI

/// The material layer.
///
/// Apple's rule is the whole of the design here: **Liquid Glass is the control and navigation
/// layer, never the content layer.** A figure that has to be read against a moving backdrop
/// is a figure the reader cannot check, and principle 3 is about figures the reader can check.
/// So `prudenceGlass` goes on the popover, the sidebar, the toolbar strip and the buttons, and
/// nothing else. Cards, tables and charts keep `Surface.plain` and stay fully opaque.
///
/// Two paths, one call site:
///
/// - **macOS 26 and later**: SwiftUI's own `glassEffect(_:in:)`, with `GlassEffectContainer`
///   around a cluster so neighbouring pieces share one sampling pass and blend at the edges.
///   The names were checked against the macOS 27 SDK that Xcode 27 ships:
///   `SwiftUICore.View.glassEffect(_ glass: Glass = .regular, in shape: some Shape)` and
///   `SwiftUICore.GlassEffectContainer(spacing:content:)`, both `@available(macOS 26.0, *)`.
///   `.buttonStyle(.glass)` and `.buttonStyle(.glassProminent)` exist under the same floor.
/// - **macOS 14 and 15**: `NSVisualEffectView` through a small `NSViewRepresentable`, with
///   `.popover`, `.sidebar` and `.hudWindow` as the three materials NOTES.md names.
///
/// Both paths go opaque when `NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency`
/// is on, which `Theme.system` reads once and every surface then honours through the
/// environment. That is the AppKit reading of the same preference the mockups honour with
/// `prefers-reduced-transparency`, and the fallback cannot drift from the thing it falls back
/// from because it is the same `Theme` flag on both sides.

// MARK: - which surface is being made of glass

public enum GlassSurface: Sendable {
    /// The menu-bar popover's content.
    case popover
    /// The window's source list.
    case sidebar
    /// A floating strip of controls above a screen.
    case toolbar
    /// A single control: a button, a segment, a pop-up.
    case control

    var appKitMaterial: NSVisualEffectView.Material {
        switch self {
        case .popover: return .popover
        case .sidebar: return .sidebar
        case .toolbar, .control: return .hudWindow
        }
    }

    var cornerRadius: CGFloat {
        switch self {
        case .popover: return Radius.glassPanel
        case .sidebar: return 0
        case .toolbar: return Radius.glassPanel
        case .control: return Radius.glassControl
        }
    }

    /// What the surface falls back to when translucency is refused or unavailable.
    var opaqueFill: Color {
        switch self {
        case .popover, .toolbar: return Surface.plain
        case .sidebar: return Surface.sidebar
        case .control: return Surface.secondary
        }
    }
}

// MARK: - the modifier

extension View {

    /// Frost this view, or leave it opaque, according to the theme in the environment.
    public func prudenceGlass(
        _ surface: GlassSurface, cornerRadius: CGFloat? = nil
    ) -> some View {
        modifier(GlassModifier(surface: surface, cornerRadius: cornerRadius))
    }

    /// Wrap a cluster of glass pieces so that on macOS 26 they sample the backdrop once and
    /// blend where they touch. A no-op everywhere else, which is why it takes the same shape
    /// on both paths.
    @ViewBuilder
    public func prudenceGlassCluster(spacing: CGFloat? = nil) -> some View {
        if #available(macOS 26, *) {
            GlassEffectContainer(spacing: spacing) { self }
        } else {
            self
        }
    }
}

struct GlassModifier: ViewModifier {

    let surface: GlassSurface
    let cornerRadius: CGFloat?

    @Environment(\.prudenceTheme) private var theme

    private var radius: CGFloat { cornerRadius ?? surface.cornerRadius }

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        if theme.wantsTranslucency {
            if #available(macOS 26, *) {
                content
                    .glassEffect(.regular, in: shape)
            } else {
                content
                    .background(VisualEffectSurface(material: surface.appKitMaterial))
                    .clipShape(shape)
                    .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
            }
        } else {
            content
                .background(surface.opaqueFill, in: shape)
                .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
        }
    }
}

// MARK: - the pre-26 path

/// `NSVisualEffectView` as a SwiftUI background.
///
/// `behindWindow` so it samples the wallpaper and the windows underneath rather than its own
/// siblings, and `followsWindowActiveState` so an inactive window desaturates the way every
/// other macOS window does.
public struct VisualEffectSurface: NSViewRepresentable {

    public let material: NSVisualEffectView.Material
    public var blending: NSVisualEffectView.BlendingMode = .behindWindow

    public init(
        material: NSVisualEffectView.Material,
        blending: NSVisualEffectView.BlendingMode = .behindWindow
    ) {
        self.material = material
        self.blending = blending
    }

    public func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blending
        view.state = .followsWindowActiveState
        return view
    }

    public func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
        view.blendingMode = blending
    }
}
