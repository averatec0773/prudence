// swift-tools-version:5.9
//
// The screenshot harness. It is a separate package, not a target of PrudenceKit, because it
// compiles the *app's own* view files: `Scripts/shots.sh` copies them into `Sources/
// PrudenceRender/Views/` (gitignored) and builds, which is how Decaf's `docs/assets/render`
// works and why the PNGs show the code that ships rather than a copy of it that drifted.

import PackageDescription

let package = Package(
    name: "PrudenceRender",
    platforms: [.macOS(.v14)],
    dependencies: [.package(path: "../PrudenceKit")],
    targets: [
        .executableTarget(
            name: "PrudenceRender",
            dependencies: [
                .product(name: "PrudenceStore", package: "PrudenceKit"),
                .product(name: "PrudenceEngine", package: "PrudenceKit"),
                .product(name: "PrudenceModels", package: "PrudenceKit"),
                .product(name: "PrudenceUI", package: "PrudenceKit"),
            ]
        )
    ]
)
