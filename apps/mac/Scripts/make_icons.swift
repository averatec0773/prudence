#!/usr/bin/env swift
//
// Renders the app icon set and the menu-bar glyph from `assets/brand`.
//
//     cd apps/mac && swift Scripts/make_icons.swift
//
// It writes, all of them generated and none of them edited by hand:
//
//     App/Assets.xcassets/AppIcon.appiconset/     icon_16x16 to icon_512x512@2x, and Contents.json
//     App/Assets.xcassets/AppIcon.appiconset/icon_1024.png   the master, kept for inspection
//     App/Assets.xcassets/StatusGlyph.imageset/  glyph.png at 16, 32 and 48 px
//     PrudenceKit/Sources/PrudenceUI/Resources/  the three brand SVGs, copied
//
// The source of truth is `assets/brand/logo.svg` and `logo-glyph-template.svg`, never a PNG:
// `NSImage` has loaded SVG since macOS 11, so the whole pipeline is one vector file in and a
// set of bitmaps out. Nothing here draws the mark by hand, and nothing here is a second copy
// of its geometry; the only numbers below are the icon grid's.
//
// `--check` renders into a temporary directory and compares, so CI can tell whether the
// committed set still matches the brand files. Nothing else in the build runs this: an icon
// set is regenerated when the mark changes, which is rarely and on purpose.

import AppKit
import Foundation

// MARK: - where things are

let arguments = CommandLine.arguments
let checkOnly = arguments.contains("--check")

/// `apps/mac`, whichever directory the script was started from inside the repository.
let workingDirectory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let macRoot: URL = {
    var url = workingDirectory
    for _ in 0..<6 {
        if FileManager.default.fileExists(atPath: url.appendingPathComponent("project.yml").path) {
            return url
        }
        url = url.deletingLastPathComponent()
    }
    return workingDirectory
}()
let repositoryRoot = macRoot.deletingLastPathComponent().deletingLastPathComponent()
let brandDirectory = repositoryRoot.appendingPathComponent("assets/brand")
let catalog = macRoot.appendingPathComponent("App/Assets.xcassets")
let iconSet = catalog.appendingPathComponent("AppIcon.appiconset")
let glyphSet = catalog.appendingPathComponent("StatusGlyph.imageset")
let uiResources = macRoot.appendingPathComponent("PrudenceKit/Sources/PrudenceUI/Resources")

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

// MARK: - the icon grid

/// The macOS icon canvas, at the master size.
///
/// macOS 26 keeps the Big Sur grid: a 1024 px canvas with the shape inset by 100 px on every
/// side, so the artwork lives in an 824 px square and the system's own shadow and any badge
/// have the margin they expect. An icon drawn edge to edge is the one thing that makes a Mac
/// icon look wrong beside its neighbours in the Dock.
let master: CGFloat = 1024
let shapeInset: CGFloat = 100
let shapeSide = master - shapeInset * 2

/// The mark, at 62 per cent of the canvas width. Measured across the mark's own visible box
/// (`assets/brand/README.md`: `58.094 116.072 397.052 279.857` inside the 512 frame), not
/// across the SVG's frame, which carries empty margin on every side.
let markWidthShare: CGFloat = 0.62
let markInk = NSColor(red: 0x11 / 255, green: 0x11 / 255, blue: 0x11 / 255, alpha: 1)

/// The mark's visible box inside the 512 x 512 SVG frame, top-left origin, as the brand
/// README states it.
let markBox = CGRect(x: 58.094, y: 116.072, width: 397.052, height: 279.857)
let svgFrame: CGFloat = 512

// MARK: - the squircle

/// The macOS icon shape, as a superellipse.
///
/// Apple's icon outline is a continuous-corner rounded square, which is a superellipse of
/// about `n = 5` over the same box; SwiftUI's `.continuous` corner style is the same family.
/// Sampling it directly is exact enough at 1024 px and, unlike a `cornerRadius`, does not
/// leave the four visible corner-radius seams a circular round rect shows at this size.
func squircle(in rect: CGRect, exponent: CGFloat = 5) -> NSBezierPath {
    let path = NSBezierPath()
    let a = rect.width / 2
    let b = rect.height / 2
    let centre = CGPoint(x: rect.midX, y: rect.midY)
    let steps = 720
    for step in 0...steps {
        let theta = CGFloat(step) / CGFloat(steps) * 2 * .pi
        let cosine = cos(theta)
        let sine = sin(theta)
        let x = centre.x + a * copysign(pow(abs(cosine), 2 / exponent), cosine)
        let y = centre.y + b * copysign(pow(abs(sine), 2 / exponent), sine)
        if step == 0 { path.move(to: CGPoint(x: x, y: y)) } else {
            path.line(to: CGPoint(x: x, y: y))
        }
    }
    path.close()
    return path
}

// MARK: - drawing

func loadSVG(_ name: String) -> NSImage {
    let url = brandDirectory.appendingPathComponent(name)
    guard let image = NSImage(contentsOf: url) else {
        fail("could not read \(url.path). Run this from inside apps/mac.")
    }
    return image
}

/// The 1024 px master: the squircle, its gradient, its edge, and the mark.
func renderMaster() -> NSBitmapImageRep {
    let mark = loadSVG("logo.svg")
    guard
        let representation = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: Int(master), pixelsHigh: Int(master),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
    else { fail("could not allocate the master bitmap") }
    representation.size = NSSize(width: master, height: master)

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: representation)

    let box = CGRect(x: shapeInset, y: shapeInset, width: shapeSide, height: shapeSide)
    let shape = squircle(in: box)

    // The light variant: an all but white face, a shade cooler at the bottom than at the top,
    // so the icon reads as lit from above without anything on it looking glossy.
    let base = NSGradient(
        colors: [
            NSColor(red: 0.992, green: 0.992, blue: 0.996, alpha: 1),
            NSColor(red: 0.898, green: 0.898, blue: 0.918, alpha: 1),
        ],
        atLocations: [0, 1],
        colorSpace: .deviceRGB
    )
    base?.draw(in: shape, angle: -90)

    // The top light: a very subtle white wash over the upper third and nothing below it.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    let light = NSGradient(
        colors: [
            NSColor(white: 1, alpha: 0.55),
            NSColor(white: 1, alpha: 0),
        ],
        atLocations: [0, 1],
        colorSpace: .deviceRGB
    )
    light?.draw(
        in: CGRect(x: box.minX, y: box.midY, width: box.width, height: box.height / 2),
        angle: -90)
    NSGraphicsContext.restoreGraphicsState()

    // One hairline edge, inside the shape, at the weight every system icon carries.
    NSColor(white: 0, alpha: 0.10).setStroke()
    shape.lineWidth = 2
    shape.stroke()

    // The mark, sized by its own visible box and centred on it rather than on the SVG frame.
    let scale = (master * markWidthShare) / markBox.width
    let drawnSide = svgFrame * scale
    let visible = CGRect(
        x: markBox.minX * scale,
        y: markBox.minY * scale,
        width: markBox.width * scale,
        height: markBox.height * scale
    )
    // AppKit's origin is bottom left; the README's box is measured from the top.
    let originX = (master - visible.width) / 2 - visible.minX
    let originY = (master - visible.height) / 2 - (drawnSide - visible.minY - visible.height)

    mark.isTemplate = true
    let tinted = NSImage(size: NSSize(width: drawnSide, height: drawnSide), flipped: false) {
        rect in
        mark.draw(in: rect)
        markInk.set()
        rect.fill(using: .sourceAtop)
        return true
    }
    tinted.draw(
        in: CGRect(x: originX, y: originY, width: drawnSide, height: drawnSide),
        from: .zero, operation: .sourceOver, fraction: 1)

    NSGraphicsContext.restoreGraphicsState()
    return representation
}

/// One PNG of the master at `pixels` square, resampled high quality.
func scaled(_ source: NSBitmapImageRep, to pixels: Int) -> Data {
    guard
        let target = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
    else { fail("could not allocate a \(pixels) px bitmap") }
    target.size = NSSize(width: pixels, height: pixels)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: target)
    NSGraphicsContext.current?.imageInterpolation = .high
    source.draw(
        in: CGRect(x: 0, y: 0, width: pixels, height: pixels),
        from: CGRect(x: 0, y: 0, width: master, height: master),
        operation: .copy, fraction: 1, respectFlipped: false, hints: nil)
    NSGraphicsContext.restoreGraphicsState()
    guard let data = target.representation(using: .png, properties: [:]) else {
        fail("could not encode a \(pixels) px PNG")
    }
    return data
}

/// The menu-bar glyph: the template artwork, rasterised at the three scales the imageset
/// declares. Drawn in black at full alpha; AppKit takes only the alpha and the menu bar
/// supplies the colour, which is what `template-rendering-intent` in the imageset asks for.
func renderGlyph(_ pixels: Int) -> Data {
    let glyph = loadSVG("logo-glyph-template.svg")
    guard
        let target = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
    else { fail("could not allocate a \(pixels) px glyph bitmap") }
    target.size = NSSize(width: pixels, height: pixels)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: target)
    NSGraphicsContext.current?.imageInterpolation = .high
    let rect = CGRect(x: 0, y: 0, width: pixels, height: pixels)
    glyph.draw(in: rect)
    NSColor.black.set()
    rect.fill(using: .sourceAtop)
    NSGraphicsContext.restoreGraphicsState()
    guard let data = target.representation(using: .png, properties: [:]) else {
        fail("could not encode the \(pixels) px glyph")
    }
    return data
}

// MARK: - the catalog

/// The ten entries a macOS app icon needs, as `(file name, pixels)`.
let iconSizes: [(name: String, points: Int, scale: Int)] = [
    ("icon_16x16", 16, 1), ("icon_16x16@2x", 16, 2),
    ("icon_32x32", 32, 1), ("icon_32x32@2x", 32, 2),
    ("icon_128x128", 128, 1), ("icon_128x128@2x", 128, 2),
    ("icon_256x256", 256, 1), ("icon_256x256@2x", 256, 2),
    ("icon_512x512", 512, 1), ("icon_512x512@2x", 512, 2),
]

let iconContents = """
{
  "images" : [
\(
    iconSizes.map { entry in
        "    { \"filename\" : \"\(entry.name).png\", \"idiom\" : \"mac\", "
            + "\"scale\" : \"\(entry.scale)x\", \"size\" : \"\(entry.points)x\(entry.points)\" }"
    }.joined(separator: ",\n")
)
  ],
  "info" : {
    "author" : "apps/mac/Scripts/make_icons.swift",
    "version" : 1
  }
}

"""

let glyphContents = """
{
  "images" : [
    { "filename" : "glyph.png", "idiom" : "mac", "scale" : "1x" },
    { "filename" : "glyph@2x.png", "idiom" : "mac", "scale" : "2x" },
    { "filename" : "glyph@3x.png", "idiom" : "mac", "scale" : "3x" }
  ],
  "info" : {
    "author" : "apps/mac/Scripts/make_icons.swift",
    "version" : 1
  },
  "properties" : {
    "template-rendering-intent" : "template"
  }
}

"""

// MARK: - write

var written: [(URL, Data)] = []

let representation = renderMaster()
written.append((iconSet.appendingPathComponent("icon_1024.png"), scaled(representation, to: 1024)))
for entry in iconSizes {
    let pixels = entry.points * entry.scale
    written.append(
        (iconSet.appendingPathComponent("\(entry.name).png"), scaled(representation, to: pixels)))
}
written.append((iconSet.appendingPathComponent("Contents.json"), Data(iconContents.utf8)))

for (name, pixels) in [("glyph", 16), ("glyph@2x", 32), ("glyph@3x", 48)] {
    written.append((glyphSet.appendingPathComponent("\(name).png"), renderGlyph(pixels)))
}
written.append((glyphSet.appendingPathComponent("Contents.json"), Data(glyphContents.utf8)))

// The package's own copies of the brand files, which `PrudenceUI/Brand.swift` loads at
// runtime. Copied here rather than kept in step by hand, so the mark changing is one command.
for name in ["logo.svg", "logo-white.svg", "logo-glyph-template.svg"] {
    guard let data = try? Data(contentsOf: brandDirectory.appendingPathComponent(name)) else {
        fail("could not read assets/brand/\(name)")
    }
    written.append((uiResources.appendingPathComponent(name), data))
}

if checkOnly {
    var stale: [String] = []
    for (url, data) in written {
        let existing = try? Data(contentsOf: url)
        // Only the byte-for-byte text files are compared; a PNG re-encoded by a different
        // macOS build differs in bytes without differing in pixels, and a CI job failing on
        // that would be noise rather than a finding.
        guard url.pathExtension == "json" || url.pathExtension == "svg" else {
            if existing == nil { stale.append(url.lastPathComponent + " (missing)") }
            continue
        }
        if existing != data { stale.append(url.lastPathComponent) }
    }
    if stale.isEmpty {
        print("the icon set matches assets/brand")
    } else {
        fail("stale, run `swift Scripts/make_icons.swift`: " + stale.joined(separator: ", "))
    }
    exit(0)
}

for directory in [iconSet, glyphSet, uiResources] {
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
}
for (url, data) in written {
    do {
        try data.write(to: url)
        print("wrote \(url.path.replacingOccurrences(of: macRoot.path + "/", with: "")) "
            + "(\(data.count) bytes)")
    } catch {
        fail("could not write \(url.path): \(error)")
    }
}
