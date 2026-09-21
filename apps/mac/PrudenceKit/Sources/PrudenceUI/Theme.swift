import SwiftUI

/// The design tokens, one Swift declaration per custom property in
/// `docs/design/mockups/tokens.css`.
///
/// Every value here was read off that file rather than invented, and `apps/mac/DESIGN.md`
/// prints the same table, so the mockups, the app and the document cannot drift apart
/// without one of them being edited on purpose. Nothing in this file computes anything: it
/// is a table of constants and a few `Color`s built from them.
///
/// Light and dark are the same token with two values, resolved by `NSColor` at draw time
/// rather than by a `colorScheme` check in a view, so a screen that is half in one appearance
/// (a popover over a dark wallpaper) still gets the right ink.

// MARK: - the one place a hex string becomes a colour

extension Color {
    /// `#RRGGBB`. A malformed string is magenta rather than a crash, which makes a typo
    /// visible in a screenshot instead of silent.
    static func hex(_ value: String) -> Color {
        var text = value
        if text.hasPrefix("#") { text.removeFirst() }
        guard text.count == 6, let number = UInt32(text, radix: 16) else { return .pink }
        return Color(
            .sRGB,
            red: Double((number >> 16) & 0xFF) / 255,
            green: Double((number >> 8) & 0xFF) / 255,
            blue: Double(number & 0xFF) / 255,
            opacity: 1
        )
    }

    /// One token, two values. `NSColor(name:dynamicProvider:)` is what makes a token follow
    /// the appearance of the view it is drawn in rather than of the process.
    static func dynamic(light: String, dark: String) -> Color {
        Color(
            nsColor: NSColor(name: nil) { appearance in
                let isDark =
                    appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
                return NSColor(Color.hex(isDark ? dark : light))
            }
        )
    }

    /// The sRGB components of a token in one appearance, as `#RRGGBB` plus its alpha.
    ///
    /// A dynamic `Color` is a provider, not a value, so two of them built from the same pair
    /// of hex strings are never `==`. A test that wants to know what a token actually draws
    /// has to resolve it, and this is how. Nothing in the app calls it.
    public func prudenceHex(dark: Bool) -> (hex: String, alpha: Double)? {
        guard let appearance = NSAppearance(named: dark ? .darkAqua : .aqua) else { return nil }
        var resolved: NSColor?
        appearance.performAsCurrentDrawingAppearance {
            resolved = NSColor(self).usingColorSpace(.sRGB)
        }
        guard let resolved else { return nil }
        let hex = String(
            format: "#%02X%02X%02X",
            Int((resolved.redComponent * 255).rounded()),
            Int((resolved.greenComponent * 255).rounded()),
            Int((resolved.blueComponent * 255).rounded())
        )
        return (hex, Double(resolved.alphaComponent))
    }

    /// The same, for a token that is an alpha over black or white rather than a hue.
    static func dynamicAlpha(
        light: (white: Double, alpha: Double), dark: (white: Double, alpha: Double)
    ) -> Color {
        Color(
            nsColor: NSColor(name: nil) { appearance in
                let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
                let pair = isDark ? dark : light
                return NSColor(white: pair.white, alpha: pair.alpha)
            }
        )
    }
}

// MARK: - purpose

/// One colour per purpose, identical in every chart on every screen, in one fixed order.
///
/// A fixed table rather than Swift Charts' automatic scale, because the automatic one assigns
/// colours in the order the series happen to arrive: a week where nobody did research would
/// silently move every other purpose one colour along, and two screenshots taken a week apart
/// would not be comparable. The keys are the engine's own labels from `facts/purpose.py`;
/// `unknown` is shown as "other" and is grey, because an absent label is not a colour.
public enum Purpose {

    /// The stacking and legend order. Never sorted by size: a chart whose colours move is a
    /// chart two screenshots cannot be compared across.
    public static let order = [
        "development", "research", "debugging", "conversation", "mixed", "unknown",
    ]

    private static let table: [String: (light: String, dark: String)] = [
        "development": ("#007AFF", "#0A84FF"),
        "research": ("#30B0C7", "#40C8E0"),
        "debugging": ("#FF9500", "#FF9F0A"),
        "conversation": ("#AF52DE", "#BF5AF2"),
        "mixed": ("#5856D6", "#7D7AFF"),
        "unknown": ("#8E8E93", "#98989D"),
    ]

    /// The colour of a purpose. A label this build has never heard of is grey and is still
    /// drawn, because a bar the engine sent and the app dropped is worse than a grey bar.
    public static func colour(_ purpose: String) -> Color {
        guard let pair = table[purpose] else { return colour("unknown") }
        return .dynamic(light: pair.light, dark: pair.dark)
    }

    /// True when the table has a colour of its own for this key. The token test uses it.
    public static func isKnown(_ purpose: String) -> Bool { table[purpose] != nil }

    /// The domain and range for `chartForegroundStyleScale`, over the purposes actually
    /// present plus any the table does not know, so the scale covers every mark drawn.
    public static func scale(for purposes: [String]) -> (domain: [String], range: [Color]) {
        let known = order.filter { purposes.contains($0) }
        let rest = purposes.filter { !order.contains($0) }.sorted()
        let domain = known + rest
        return (domain, domain.map(colour))
    }

    /// The purposes of a set of slices, put back into the fixed order.
    public static func ordered(_ purposes: [String]) -> [String] {
        scale(for: purposes).domain
    }
}

/// Survival and rework are two readings of the same lines, so they share a warm-cool pair
/// everywhere and differ by line style in a time chart. **Colour never means good or bad.**
public enum Outcome {
    public static let alive = Color.dynamic(light: "#0A7D45", dark: "#3AC07A")
    public static let rework = Color.dynamic(light: "#8A5A00", dark: "#E0A33A")
}

// MARK: - surfaces and text

/// The interface colours. Elevation is a 0.5 pt hairline ring, not a shadow; only the
/// popover and the window frame cast a real one, at the system's own weight.
public enum Surface {
    public static let canvas = Color.dynamic(light: "#F2F2F4", dark: "#1C1C1E")
    public static let plain = Color.dynamic(light: "#FFFFFF", dark: "#2C2C2E")
    public static let secondary = Color.dynamic(light: "#F7F7F9", dark: "#242426")
    /// Chart tracks: the groove a bar or a share is drawn into.
    public static let sunken = Color.dynamic(light: "#EBEBEF", dark: "#171719")
    public static let sidebar = Color.dynamic(light: "#F6F6F8", dark: "#232325")
    public static let separator = Color.dynamicAlpha(
        light: (0, 0.08), dark: (1, 0.10))
    public static let hairline = Color.dynamicAlpha(
        light: (0, 0.13), dark: (1, 0.16))
    /// The pale underlay behind a share, carrying its coverage.
    public static let coverage = Color.dynamicAlpha(
        light: (0, 0.16), dark: (1, 0.24))
    public static let grid = Color.dynamicAlpha(
        light: (0, 0.07), dark: (1, 0.09))
}

/// Three levels of ink and one accent. `Ink.primary` is the token, not `.primary`, because a
/// popover drawn over a wallpaper does not always inherit the appearance a view expects.
public enum Ink {
    public static let primary = Color.dynamic(light: "#1C1C1E", dark: "#F2F2F7")
    public static let secondary = Color.dynamic(light: "#636366", dark: "#AEAEB2")
    public static let tertiary = Color.dynamic(light: "#8E8E93", dark: "#8E8E93")
    public static let accent = Color.dynamic(light: "#007AFF", dark: "#0A84FF")
    public static let onAccent = Color.white
    public static let accentSoft = Color(
        nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            return NSColor(Color.hex(isDark ? "#0A84FF" : "#007AFF")).withAlphaComponent(
                isDark ? 0.22 : 0.12)
        })
    /// The mark's own ink: `#111111` on light, white on dark.
    public static let brand = Color.dynamic(light: "#111111", dark: "#FFFFFF")
}

// MARK: - spacing, type, radii, motion

/// Base 4. Card padding 20, card gap 16, section gap 20 to 24.
public enum Space {
    public static let s1: CGFloat = 4
    public static let s2: CGFloat = 8
    public static let s3: CGFloat = 12
    public static let s4: CGFloat = 16
    public static let s5: CGFloat = 20
    public static let s6: CGFloat = 24
    public static let s7: CGFloat = 32
    public static let s8: CGFloat = 40

    public static let cardPadding: CGFloat = 20
    public static let cardGap: CGFloat = 16
    public static let sectionGap: CGFloat = 24
    /// The popover is tighter than a window: 14 pt of padding, 10 between blocks.
    public static let popoverPadding: CGFloat = 14
    public static let popoverGap: CGFloat = 10
}

/// SF Pro through the system font, `PingFang SC` picked up automatically for Chinese.
/// Every figure on every screen uses `.monospacedDigit()`; `Type.figure` is the shorthand.
public enum Type {
    public static let caption2 = Font.system(size: 11)
    public static let caption = Font.system(size: 12)
    /// The working body size.
    public static let footnote = Font.system(size: 13)
    public static let body = Font.system(size: 15)
    public static let headline = Font.system(size: 17, weight: .semibold)
    public static let title3 = Font.system(size: 20, weight: .semibold)
    public static let title2 = Font.system(size: 24, weight: .semibold)
    public static let title1 = Font.system(size: 28, weight: .bold)

    public static let captionStrong = Font.system(size: 12, weight: .semibold)
    public static let footnoteStrong = Font.system(size: 13, weight: .semibold)

    /// Any number on any screen. Tabular digits, so a value that changes does not reflow the
    /// row it is in.
    public static func figure(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        Font.system(size: size, weight: weight).monospacedDigit()
    }
}

public enum Radius {
    public static let control: CGFloat = 6
    public static let card: CGFloat = 10
    public static let panel: CGFloat = 12
    public static let popover: CGFloat = 12
    public static let chip: CGFloat = 999
    /// Glass surfaces take radii one step larger (NOTES.md, Material section).
    public static let glassControl: CGFloat = 8
    public static let glassPanel: CGFloat = 16
}

/// State changes only, 150 to 240 ms, ease-out. Nothing animates on load.
public enum Motion {
    public static let fast: Double = 0.150
    public static let normal: Double = 0.200
    public static let slow: Double = 0.240
    public static let curve = UnitCurve.easeOut

    public static var hover: Animation { .timingCurve(0.22, 0.61, 0.36, 1, duration: fast) }
    public static var state: Animation { .timingCurve(0.22, 0.61, 0.36, 1, duration: normal) }
}

// MARK: - the theme as an environment value

/// One value carrying the choices a view cannot read off a constant: the material, and
/// whether the reader has asked for less transparency.
///
/// It is an environment value rather than a singleton so that the render harness can draw the
/// same screen twice, once per material, in one process.
public struct Theme: Equatable, Sendable {

    public enum Material: String, Sendable, CaseIterable {
        /// Opaque surfaces everywhere. The honest look on macOS 14 and 15, and what
        /// `accessibilityDisplayShouldReduceTransparency` forces on every system.
        case standard
        /// Glass on the control and navigation layer. `glassEffect` on macOS 26 and later,
        /// `NSVisualEffectView` before it.
        case glass
    }

    public var material: Material
    /// When true, both glass paths draw an opaque surface instead.
    public var reduceTransparency: Bool

    public init(material: Material = .glass, reduceTransparency: Bool = false) {
        self.material = material
        self.reduceTransparency = reduceTransparency
    }

    /// True when a surface should really be translucent: glass asked for, and not refused.
    public var wantsTranslucency: Bool { material == .glass && !reduceTransparency }

    /// The app's own theme: glass where the reader allows it.
    @MainActor
    public static var system: Theme {
        Theme(
            material: .glass,
            reduceTransparency: NSWorkspace.shared
                .accessibilityDisplayShouldReduceTransparency
        )
    }
}

private struct ThemeKey: EnvironmentKey {
    static let defaultValue = Theme(material: .standard, reduceTransparency: false)
}

extension EnvironmentValues {
    public var prudenceTheme: Theme {
        get { self[ThemeKey.self] }
        set { self[ThemeKey.self] = newValue }
    }
}

extension View {
    public func prudenceTheme(_ theme: Theme) -> some View {
        environment(\.prudenceTheme, theme)
    }
}
