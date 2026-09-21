// swift-tools-version:5.9
//
// PrudenceKit holds everything the app thinks with, so that almost all of the work can be
// checked by `swift test` in seconds without generating an Xcode project. The app target is
// thin on purpose: SwiftUI views and AppKit glue, no decisions.
//
// Three products, one direction of dependency:
//   PrudenceStore  reads the `app_*` views, read-only, through GRDB.
//   PrudenceEngine finds and runs the `prudence` CLI, which is the only writer.
//   PrudenceModels turns rows into the strings a screen shows. Depends on both.

import PackageDescription

let package = Package(
    name: "PrudenceKit",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "PrudenceStore", targets: ["PrudenceStore"]),
        .library(name: "PrudenceEngine", targets: ["PrudenceEngine"]),
        .library(name: "PrudenceModels", targets: ["PrudenceModels"]),
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
        .testTarget(
            name: "PrudenceKitTests",
            dependencies: ["PrudenceStore", "PrudenceEngine", "PrudenceModels"],
            path: "Tests/PrudenceKitTests",
            resources: [.copy("Fixtures")]
        ),
    ]
)
