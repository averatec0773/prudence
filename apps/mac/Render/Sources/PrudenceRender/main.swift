import AppKit
import PrudenceModels
import PrudenceStore
import SwiftUI

// Renders the shipping SwiftUI views to PNG, off-screen, in light and dark.
//
// This needs no permission of any kind. Nothing is ever ordered on screen, no window server
// capture happens, and no Apple events are sent, so it runs in CI, over SSH and inside an
// agent's sandbox alike, and it renders the same code the app runs. That is the whole reason
// it exists: the founder judges screenshots, not diffs.
//
// Two traps, both from the research note (section 7): render through `cacheDisplay(in:to:)`
// rather than `displayIgnoringOpacity`, which draws SwiftUI `Text` invisibly; and pin the
// appearance, the scale and the frame, because a window's own title bar is a different height
// on a CI VM than on a real Mac.

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
    let data: WindowData
    do {
        let store = try Store(url: URL(fileURLWithPath: fixture))
        snapshot = try Snapshot.read(from: store, now: renderedAt)
        data = try WindowData.read(from: store, now: renderedAt)
    } catch {
        FileHandle.standardError.write(Data("could not read \(fixture): \(error)\n".utf8))
        exit(1)
    }

    let model = MenuViewModel.preview(
        snapshot: snapshot,
        engineVersion: "prudence, version 0.2.0",
        actionMessage: "Review 1 written."
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
    /// shots are taken in one pass. All three read the same rows.
    func window(_ section: MainSection) -> AnyView {
        AnyView(
            MainWindowContentView(
                model: WindowModel.preview(data: data, section: section, settings: settings),
                settings: settings,
                launchAtLogin: launchAtLogin
            )
        )
    }

    let big = CGSize(width: 1200, height: 800)
    let shots: [(name: String, size: CGSize?, view: AnyView)] = [
        ("menu", nil, AnyView(MenuContentView(model: model, actions: MenuActions()))),
        // The window at the floor `MainWindowController` sets, which is where the layout is
        // under the most pressure.
        ("window", CGSize(width: 900, height: 600), window(.overview)),
        ("overview", big, window(.overview)),
        ("review", big, window(.review)),
        ("observations", big, window(.observations)),
        (
            "settings", CGSize(width: 520, height: 420),
            AnyView(SettingsView(settings: settings, launchAtLogin: launchAtLogin))
        ),
    ]

    let appearances: [(String, NSAppearance.Name)] = [("light", .aqua), ("dark", .darkAqua)]

    let directory = URL(fileURLWithPath: outputDirectory)
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

    for shot in shots {
        for (suffix, appearanceName) in appearances {
            guard let appearance = NSAppearance(named: appearanceName) else { continue }
            let url = directory.appendingPathComponent("\(shot.name)-\(suffix).png")
            render(shot.view, size: shot.size, appearance: appearance, to: url)
            print("wrote \(url.path)")
        }
    }
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

/// One view, one appearance, one PNG at 1x.
@MainActor
func render(_ view: AnyView, size: CGSize?, appearance: NSAppearance, to url: URL) {
    let hosting = NSHostingView(
        rootView:
            ZStack {
                Color(nsColor: .windowBackgroundColor)
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

MainActor.assumeIsolated { renderEverything() }
