// swift-tools-version:5.9
//
// PrudenceKit holds everything the app thinks with, so that almost all of the work can be
// checked by `swift test` in seconds without generating an Xcode project. The app target is
// thin on purpose: SwiftUI views and AppKit glue, no decisions.
//
// Four products, one direction of dependency:
//   PrudenceStore  reads the `app_*` views, read-only, through GRDB.
//   PrudenceEngine finds and runs the `prudence` CLI, which is the only writer.
//   PrudenceModels turns rows into the strings a screen shows. Depends on both.
//   PrudenceUI     the design system: tokens, components, the glass layer, and every
//                  user-facing string. Depends on PrudenceModels.
//
// `defaultLocalization` is what lets `Sources/PrudenceUI/Resources/Localizable.xcstrings`
// be compiled into `en.lproj` and `zh-Hans.lproj` inside the target's resource bundle.

import PackageDescription

let package = Package(
    name: "PrudenceKit",
    defaultLocalization: "en",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "PrudenceStore", targets: ["PrudenceStore"]),
        .library(name: "PrudenceEngine", targets: ["PrudenceEngine"]),
        .library(name: "PrudenceModels", targets: ["PrudenceModels"]),
        .library(name: "PrudenceUI", targets: ["PrudenceUI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift", from: "7.11.1"),
    ],
    targets: [
        .target(
            name: "PrudenceStore",
            dependencies: [.product(name: "GRDB", package: "GRDB.swift")]
        ),
        .target(name: "PrudenceEngine"),
        .target(name: "PrudenceModels", dependencies: ["PrudenceStore", "PrudenceEngine"]),
        .target(
            name: "PrudenceUI",
            dependencies: ["PrudenceModels"],
            resources: [.process("Resources")]
        ),
        .testTarget(
            name: "PrudenceKitTests",
            dependencies: ["PrudenceStore", "PrudenceEngine", "PrudenceModels", "PrudenceUI"],
            path: "Tests/PrudenceKitTests",
            resources: [.copy("Fixtures")]
        ),
    ]
)
