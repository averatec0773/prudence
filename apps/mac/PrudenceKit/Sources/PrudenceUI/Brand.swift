import AppKit
import SwiftUI

/// The mark, from the brand files themselves.
///
/// `Resources/logo.svg`, `logo-white.svg` and `logo-glyph-template.svg` are copies of
/// `assets/brand/`, which is the source of truth; `Scripts/make_icons.swift --refresh-resources`
/// copies them across, and the app icon set is rendered from the same originals. They are
/// SVGs rather than PNGs because `NSImage` has loaded SVG since macOS 11, so one file covers
/// 14 pt in a title bar and 56 pt on an about page with no rasterisation at either.
///
/// The mark is drawn as a **template** image: AppKit takes only its alpha and the surface
/// supplies the colour, which is how `Ink.brand` (`#111111` on light, white on dark) reaches
/// it without the view having to pick between the two files. `logo-white.svg` is kept for the
/// places that need the white artwork itself rather than a tint.
public enum Brand {

    public enum Asset: String, Sendable {
        case mark = "logo"
        case markWhite = "logo-white"
        case glyph = "logo-glyph-template"
    }

    /// The artwork, as a template image. Nil only if the resource bundle is missing, which is
    /// a build problem rather than a runtime one; every caller draws nothing instead.
    public static func image(_ asset: Asset, size: CGFloat) -> NSImage? {
        guard
            let url = Bundle.module.url(forResource: asset.rawValue, withExtension: "svg"),
            let image = NSImage(contentsOf: url)
        else { return nil }
        image.size = NSSize(width: size, height: size)
        image.isTemplate = asset != .markWhite
        return image
    }
}

/// The mark beside the product name: 16 to 18 pt in the popover's header, 14 in a title bar.
public struct BrandMark: View {

    let size: CGFloat
    var tint: Color

    public init(size: CGFloat = 18, tint: Color = Ink.brand) {
        self.size = size
        self.tint = tint
    }

    public var body: some View {
        Group {
            if let image = Brand.image(.mark, size: size) {
                Image(nsImage: image)
                    .renderingMode(.template)
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(tint)
            } else {
                Color.clear
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
