import AppKit
import PrudenceModels
import PrudenceStore
import PrudenceUI
import SwiftUI

// Renders the shipping SwiftUI views to PNG, off-screen, in light and dark, English and
// Simplified Chinese, and — for the two surfaces that have a material — Standard and Glass.
//
// This needs no permission of any kind. Nothing is ever ordered on screen, no window server
// capture happens, and no Apple events are sent, so it runs in CI, over SSH and inside an
// agent's sandbox alike, and it renders the same code the app runs. That is the whole reason
// it exists: the founder judges screenshots, not diffs.
//
// Three traps, two from the research note (section 7) and one from batch 1: render through
// `cacheDisplay(in:to:)` rather than `displayIgnoringOpacity`, which draws SwiftUI `Text`
// invisibly; pin the appearance, the scale and the frame, because a window's own title bar is
// a different height on a CI VM than on a real Mac; and force the language around the whole of
// building *and* laying out a view, because a SwiftUI body is evaluated during layout rather
// than at construction, so a language set and put back too early renders the other one.

@MainActor
func renderEverything() {
    let environment = ProcessInfo.processInfo.environment
    let fixture =
        environment["PRUDENCE_SHOTS_FIXTURE"]
        ?? "PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db"
    let outputDirectory = environment["PRUDENCE_SHOTS_DIR"] ?? "shots"

    let application = NSApplication.shared
    application.setActivationPolicy(.prohibited)

    // A fixed moment by default, so a shot of the fixture never changes because time passed.
    // `PRUDENCE_SHOTS_NOW=now` renders against the clock instead, which is what an agent wants
    // when pointing the harness at a copy of a real store.
    let renderedAt: Date
    switch environment["PRUDENCE_SHOTS_NOW"] {
    case "now": renderedAt = Date()
    case let stamp?: renderedAt = Formatting.timestamp(stamp) ?? Date()
    case nil: renderedAt = Formatting.timestamp("2026-09-15T18:04:00") ?? Date()
    }

    let snapshot: Snapshot
    var data: WindowData
    do {
        let store = try Store(url: URL(fileURLWithPath: fixture))
        snapshot = try Snapshot.read(from: store, now: renderedAt)
        data = try WindowData.read(from: store, now: renderedAt)
    } catch {
        FileHandle.standardError.write(Data("could not read \(fixture): \(error)\n".utf8))
        exit(1)
    }

    // `PRUDENCE_SHOTS_REVIEW` puts a different `sections` payload on the newest review row
    // before the Review screen is drawn. `Scripts/shots.sh` points it at
    // `Fixtures/review-sections.json`, one real payload copied off the founder's own store.
    //
    // It exists because of a gap between the two fixtures: `tests/mac_fixture.py` writes a
    // review with two sections and one purpose row, which is enough for the decoding tests and
    // far too thin to photograph — the donut would have one slice and the comparison, the
    // observations and the suggestions would not appear at all, so a shot of it could not show
    // the sections batch 2 drew. The row's own columns (the ranges, the scope, the coverage,
    // the model segment) are still the fixture's; only the body is this payload. The screen is
    // the shipping screen either way.
    if let payload = environment["PRUDENCE_SHOTS_REVIEW"],
        let text = try? String(contentsOfFile: payload, encoding: .utf8)
    {
        data.reviews = data.reviews.enumerated().map { index, row in
            index == 0 ? (replacingSections(of: row, with: text) ?? row) : row
        }
    }

    let model = MenuViewModel.preview(
        snapshot: snapshot,
        engineVersion: "prudence, version 0.3.0",
        actionMessage: nil
    )

    let settings = AppSettings(
        defaults: UserDefaults(suiteName: "dev.prudence.render") ?? .standard)
    settings.enginePath = ""
    settings.databasePath = ""
    settings.timedIngestEnabled = true
    let launchAtLogin = FakeLaunchAtLogin(state: .requiresApproval)

    // `PRUDENCE_SHOTS_DUMP=1` prints the three Overview cards for the default scope, so the
    // numbers on the screenshot can be put beside `prudence usage` for the same range without
    // anybody having to read them off a PNG.
    if environment["PRUDENCE_SHOTS_DUMP"] != nil {
        dumpCards(data: data, now: renderedAt)
    }

    /// One `WindowModel` per screen, because the section is a property of the model and the
    /// shots are taken in one pass. All of them read the same rows.
    func window(_ section: MainSection) -> AnyView {
        AnyView(
            MainWindowContentView(
                model: WindowModel.preview(data: data, section: section, settings: settings),
                settings: settings,
                launchAtLogin: launchAtLogin
            )
        )
    }

    func settingsView(_ tab: SettingsView.Tab) -> AnyView {
        AnyView(
            SettingsView(
                settings: settings,
                launchAtLogin: launchAtLogin,
                status: { data.status.map(StatusModel.init(row:)) },
                initialTab: tab
            ))
    }

    // Tall enough for the whole screen rather than for a window. Batch 2 put three charts on
    // the Overview and a chart on every section of the Review, and a screen the founder has to
    // scroll is a screen a PNG cannot show: these shots are for judging a layout, so they are
    // the layout's own height. `window` stays at the 900x600 floor, which is where the layout
    // is under the most pressure and is the thing that shot is for.
    let overviewSize = CGSize(width: 1200, height: 1500)
    let reviewSize = CGSize(width: 1200, height: 2600)
    let observationsSize = CGSize(width: 1200, height: 1500)

    /// The six screens. `materials` says which of them have one: the popover and the window
    /// are the control and navigation layer, so they are photographed under both Standard and
    /// Glass; the three screens inside the window and the standalone Settings sheet are drawn
    /// on content surfaces, which are opaque under either.
    let shots:
        [(name: String, size: CGSize?, bothMaterials: Bool, view: () -> AnyView)] = [
            (
                "menu", nil, true,
                { AnyView(MenuContentView(model: model, actions: MenuActions())) }
            ),
            // The window at the floor `MainWindowController` sets, which is where the layout
            // is under the most pressure.
            ("window", CGSize(width: 900, height: 600), true, { window(.overview) }),
            ("overview", overviewSize, false, { window(.overview) }),
            ("review", reviewSize, false, { window(.review) }),
            ("observations", observationsSize, false, { window(.observations) }),
            // Both tabs of Settings B. The Data tab holds the two path rows and the line the
            // store says about itself, which is half the screen; a shot of General alone would
            // leave the founder judging the half that has no numbers in it.
            ("settings", CGSize(width: 620, height: 470), false, { settingsView(.general) }),
            ("settings-data", CGSize(width: 620, height: 470), false, { settingsView(.data) }),
        ]

    let appearances: [(String, NSAppearance.Name)] = [("light", .aqua), ("dark", .darkAqua)]
    let languages: [(String, Language)] = [("en", .english), ("zh", .chineseSimplified)]

    let directory = URL(fileURLWithPath: outputDirectory)
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

    for shot in shots {
        for (appearanceSuffix, appearanceName) in appearances {
            for (languageSuffix, language) in languages {
                guard let appearance = NSAppearance(named: appearanceName) else { continue }
                var materials: [(String, Theme.Material)] = [("", .standard)]
                if shot.bothMaterials { materials.append(("-glass", .glass)) }
                for (materialSuffix, material) in materials {
                    let name =
                        "\(shot.name)-\(appearanceSuffix)-\(languageSuffix)"
                        + "\(materialSuffix).png"
                    let url = directory.appendingPathComponent(name)
                    // The language is forced around the whole render, not around building the
                    // view: SwiftUI evaluates a body during layout, and `Str` resolves its
                    // locale there.
                    Localization.withLanguage(language) {
                        render(
                            shot.view().prudenceTheme(
                                Theme(material: material, reduceTransparency: false)),
                            size: shot.size,
                            appearance: appearance,
                            to: url
                        )
                    }
                    print("wrote \(url.path)")
                }
            }
        }
    }

    auditLabels()
}

// MARK: - the check the founder's eyes had to do

/// Every button style, under every material, asked whether its label still reaches the screen.
///
/// `PrudenceUI/LabelAudit` explains the method and its limits: off-screen this covers Standard,
/// reduced transparency and the `NSVisualEffectView` fallback, and `PRUDENCE_SHOTS_ONSCREEN=1`
/// makes it cover macOS 26's real glass too, by ordering the window in and taking the picture
/// through the window server instead of through `cacheDisplay`, which draws `glassEffect` as a
/// no-op. It runs on every `shots.sh`, because a harness that photographs a blank button and
/// says nothing is a harness that already failed once.
@MainActor
func auditLabels() {
    let onScreen = ProcessInfo.processInfo.environment["PRUDENCE_SHOTS_ONSCREEN"] != nil
    let size = CGSize(width: 200, height: 40)
    var blank: [String] = []
    let styles: [(String, PrudenceButtonStyle)] = [
        ("prudencePrimaryWide", .prudencePrimaryWide),
        ("prudenceWide", .prudenceWide),
        ("prudence", .prudence),
        ("prudencePlain", .prudencePlain),
    ]
    for (name, style) in styles {
        for material in Theme.Material.allCases {
            for (appearanceName, dark) in [("light", false), ("dark", true)] {
                let theme = Theme(material: material, reduceTransparency: false)
                let visible = LabelAudit.labelIsVisible(
                    "Review now",
                    size: size,
                    appearance: NSAppearance(named: dark ? .darkAqua : .aqua),
                    onScreen: onScreen
                ) { label in
                    Button(label) {}
                        .buttonStyle(style)
                        .prudenceTheme(theme)
                        .frame(width: size.width, height: size.height)
                }
                if !visible {
                    blank.append("\(name) \(material.rawValue) \(appearanceName)")
                }
            }
        }
    }

    // And the popover's own footer, in a real `NSPopover`, inside the `GlassEffectContainer`
    // it really sits in. **This is the case that matters.** A single button was never the bug
    // and neither was an ordinary window: the same broken code drew perfectly readable labels
    // in both, even photographed through the window server. It took the popover's own backing
    // material under the cluster's merged glass pass to make the labels disappear, which is
    // why the founder saw it and nothing else did.
    let footerSize = CGSize(width: 328, height: 110)
    if onScreen {
        for (appearanceName, dark) in [("light", false), ("dark", true)] {
            let visible = LabelAudit.labelIsVisibleInAPopover(
                "Review now",
                size: footerSize,
                appearance: NSAppearance(named: dark ? .darkAqua : .aqua)
            ) { label in
                VStack(spacing: Space.s2) {
                    Button(label) {}.buttonStyle(.prudencePrimaryWide)
                    HStack(spacing: Space.s2) {
                        Button(label) {}
                        Button(label) {}
                    }
                    .buttonStyle(.prudenceWide)
                }
                .prudenceGlassCluster(spacing: Space.s2)
                .padding(Space.popoverPadding)
                .frame(width: footerSize.width)
                // The nesting the real popover has: glass on the whole content, and glass
                // again on each control inside it.
                .prudenceGlass(.popover, cornerRadius: 0)
                .prudenceTheme(Theme(material: .glass))
            }
            if !visible {
                blank.append("the popover's footer cluster, in an NSPopover, \(appearanceName)")
            }
        }
    }
    let how = onScreen ? "on screen, through the window server" : "off screen"
    guard blank.isEmpty else {
        FileHandle.standardError.write(
            Data(
                ("label audit (\(how)) failed: these render identically with a label and "
                    + "without one, so something is drawn over the text:\n  "
                    + blank.joined(separator: "\n  ") + "\n").utf8))
        exit(2)
    }
    let count = styles.count * 4 + (onScreen ? 2 : 0)
    print("label audit (\(how)): \(count) renders, every label visible")
}

/// The same row with another `sections` payload on it.
///
/// A JSON round trip rather than a second initialiser on `AppReviewRow`: the row is `Codable`
/// with the view's own column names, so encoding it, replacing one value and decoding it back
/// cannot get a key wrong, and nothing in the shipping store layer grows an entry point that
/// exists only for a screenshot.
func replacingSections(of row: AppReviewRow, with sections: String) -> AppReviewRow? {
    guard
        let data = try? JSONEncoder().encode(row),
        var fields = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    else { return nil }
    fields["sections"] = sections
    // `app_review.numbers` is the same list flattened; dropping it makes the screen read the
    // numbers out of the payload, which is where this one's are.
    fields.removeValue(forKey: "numbers")
    guard let patched = try? JSONSerialization.data(withJSONObject: fields) else { return nil }
    return try? JSONDecoder().decode(AppReviewRow.self, from: patched)
}

/// The three Overview cards, in the default scope, on standard output.
///
/// Not a test and not part of a shot: a line an agent or the founder can hold beside
/// `prudence usage --last 60d` for the same store, so the window's arithmetic is checked
/// against the CLI's rather than against a screenshot of itself.
@MainActor
func dumpCards(data: WindowData, now: Date) {
    for range in ChartRange.allCases {
        let filtered = WindowFilter(project: nil, range: range, now: now).apply(to: data)
        let cards = SummaryCards(
            sessions: filtered.sessions, usage: filtered.usage, commits: filtered.commits)
        let weeks = WeeklyUsageModel(rows: filtered.usage)
        print(
            "cards[\(range.label), All projects, \(range.describe(now: now))]: "
                + "sessions=\(cards.sessions) "
                + "active_hours=\(cards.activeHoursText) "
                + "commits=\(cards.commits) (\(cards.methodText)) "
                + "edits=\(cards.edits.map(String.init) ?? "-") "
                + "tokens=\(weeks.weeks.reduce(0) { $0 + $1.total }) "
                + "weeks=\(weeks.weeks.count)"
        )
        for week in weeks.weeks {
            let slices = week.slices.map { "\($0.purpose)=\($0.tokens)" }.joined(separator: " ")
            print("  week \(week.weekStart): total=\(week.total) \(slices)")
        }
    }
}

/// One view, one appearance, one language, one material, one PNG at 1x.
@MainActor
func render<Content: View>(
    _ view: Content, size: CGSize?, appearance: NSAppearance, to url: URL
) {
    let hosting = NSHostingView(
        rootView:
            ZStack {
                // The wallpaper a translucent surface has to be translucent about. Standard
                // draws its own opaque background over this, so both materials are
                // photographed over the same thing and only the material differs.
                RenderBackdrop()
                view
            }
            .environment(\.colorScheme, appearance.name == .darkAqua ? .dark : .light)
    )
    hosting.appearance = appearance

    let measured = size ?? hosting.fittingSize
    hosting.frame = NSRect(origin: .zero, size: measured)
    hosting.layoutSubtreeIfNeeded()

    // A window that is never shown and never ordered in. It exists because SwiftUI wants one
    // for its environment; nothing is drawn through the window server.
    let window = NSWindow(
        contentRect: hosting.frame,
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    window.appearance = appearance
    window.contentView = hosting
    hosting.layoutSubtreeIfNeeded()
    // One turn of the run loop, so SwiftUI has resolved its layout before the bitmap is taken.
    RunLoop.current.run(until: Date().addingTimeInterval(0.05))

    // Built by hand at exactly one pixel per point, rather than through
    // `bitmapImageRepForCachingDisplay`, which follows the machine's own backing scale and so
    // writes a 2x PNG on a Retina Mac and a 1x one on a CI VM. Pinning it here is what makes
    // two runs of this harness comparable.
    guard
        let representation = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: Int(measured.width.rounded()),
            pixelsHigh: Int(measured.height.rounded()),
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: 0,
            bitsPerPixel: 0
        )
    else {
        FileHandle.standardError.write(Data("could not allocate a bitmap for \(url.path)\n".utf8))
        exit(1)
    }
    representation.size = measured
    hosting.cacheDisplay(in: hosting.bounds, to: representation)

    guard let data = representation.representation(using: .png, properties: [:]) else {
        FileHandle.standardError.write(Data("could not encode \(url.path)\n".utf8))
        exit(1)
    }
    do {
        try data.write(to: url)
    } catch {
        FileHandle.standardError.write(Data("could not write \(url.path): \(error)\n".utf8))
        exit(1)
    }
}

/// Three soft blobs, the same idea as the mockups' `--wallpaper`.
///
/// It exists so that a Glass shot has something behind it to sample; a frosted surface over a
/// flat grey is indistinguishable from an opaque one, and a pair of shots that cannot be told
/// apart is not a verification. The Standard shots draw over it and hide it entirely, which is
/// the honest Standard look.
struct RenderBackdrop: View {
    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
            LinearGradient(
                colors: [
                    Color(.sRGB, red: 0.55, green: 0.66, blue: 0.92, opacity: 0.55),
                    Color(.sRGB, red: 0.86, green: 0.62, blue: 0.80, opacity: 0.40),
                    Color(.sRGB, red: 0.48, green: 0.80, blue: 0.84, opacity: 0.45),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .blur(radius: 60)
        }
        .ignoresSafeArea()
    }
}

MainActor.assumeIsolated { renderEverything() }
