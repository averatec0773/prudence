import AppKit
import PrudenceModels
import SwiftUI

/// The main window, built by hand.
///
/// `NSHostingController` inside an `NSWindow`, `isReleasedWhenClosed = false` so reopening
/// reuses the same window, and `NSApp.activate(ignoringOtherApps:)` before
/// `makeKeyAndOrderFront`. The SwiftUI route (a `Window` scene plus `openWindow`) is where
/// accessory apps hit the classic symptoms of a window that opens behind everything else or
/// without focus; this is the shape Decaf uses and it is boring on purpose.
///
/// The Dock icon appears while this window is up and goes away when it closes, which is the
/// activation-policy toggle `AppDelegate` owns (M3 plan, open question 1, accepted default).
/// `onClose` is how it hears about it.
///
/// The size is remembered by `setFrameAutosaveName`, which writes the frame into
/// `UserDefaults` under `NSWindow Frame PrudenceMainWindow` and restores it on the next
/// launch. `contentMinSize` rather than `minSize`, so the 900 x 600 floor is the floor of the
/// content and does not shrink by the height of the title bar.
@MainActor
final class MainWindowController: NSObject, NSWindowDelegate {

    static let minimumSize = NSSize(width: 900, height: 600)

    private let window: NSWindow
    private let model: WindowModel
    private let onClose: () -> Void

    init(
        model: WindowModel,
        settings: AppSettings,
        launchAtLogin: any LaunchAtLoginControlling,
        onSettingsChange: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.model = model
        self.onClose = onClose
        window = NSWindow(
            contentRect: NSRect(origin: .zero, size: Self.minimumSize),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "Prudence"
        window.isReleasedWhenClosed = false
        window.contentMinSize = Self.minimumSize
        window.center()
        // Set after `center()`, so a remembered frame wins over the centred one.
        window.setFrameAutosaveName("PrudenceMainWindow")
        window.contentViewController = NSHostingController(
            rootView: MainWindowContentView(
                model: model,
                settings: settings,
                launchAtLogin: launchAtLogin,
                onSettingsChange: onSettingsChange
            )
        )
        window.delegate = self
    }

    func show() {
        model.refresh()
        window.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        // The policy flip has to happen after this window is really gone, or the count of
        // visible windows still includes it.
        DispatchQueue.main.async { [onClose] in onClose() }
    }
}

// MARK: - the window's content

/// A sidebar and one screen at a time.
///
/// `NavigationSplitView` in its two-column form, which on macOS is the standard source-list
/// layout and gives the sidebar its own translucency, its collapse button and its width
/// memory for nothing. The header controls above each screen are the project and the range,
/// shared by Overview and Observations because they are the same question asked of two views;
/// Review has its own picker instead, because a review is a document with its own range
/// printed on it and a range control over it would promise a filter that cannot exist.
struct MainWindowContentView: View {

    @ObservedObject var model: WindowModel
    @ObservedObject var settings: AppSettings
    var launchAtLogin: any LaunchAtLoginControlling
    var onSettingsChange: () -> Void = {}

    var body: some View {
        NavigationSplitView {
            List(MainSection.allCases, selection: $model.section) { section in
                Label(section.title, systemImage: section.symbol).tag(section)
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 260)
        } detail: {
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(
            minWidth: MainWindowController.minimumSize.width,
            minHeight: MainWindowController.minimumSize.height
        )
    }

    @ViewBuilder
    private var detail: some View {
        if let problem = model.storeError {
            ContractMismatchView(message: problem, onRetry: { model.refresh() })
        } else {
            switch model.section {
            case .overview:
                ScreenScaffold(title: "Overview", subtitle: rangeSubtitle) {
                    ScopeControls(model: model)
                } content: {
                    OverviewView(model: model)
                }
            case .review:
                ScreenScaffold(title: "Review", subtitle: reviewSubtitle) {
                    ReviewPicker(model: model)
                } content: {
                    ReviewView(model: model)
                }
            case .observations:
                ScreenScaffold(title: "Observations", subtitle: observationsSubtitle) {
                    ScopeControls(model: model)
                } content: {
                    ObservationsView(model: model)
                }
            case .settings:
                SettingsView(
                    settings: settings, launchAtLogin: launchAtLogin, onChange: onSettingsChange
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
    }

    private var rangeSubtitle: String {
        let scope = model.project ?? ProjectFilter.allProjectsLabel
        return "\(scope), \(model.range.describe(now: model.now))."
    }

    private var reviewSubtitle: String {
        guard let review = model.review else { return "No review has been written yet." }
        return "\(review.scope), written \(review.createdAt)."
    }

    private var observationsSubtitle: String {
        model.project == nil
            ? "Pooled across your projects. Choose a project for its own."
            : "In \(model.project ?? "")."
    }
}

// MARK: - the shared chrome

/// Every screen the same way round: a title, one line saying what is being shown, the
/// controls that change it, then the screen.
struct ScreenScaffold<Controls: View, Content: View>: View {

    let title: String
    let subtitle: String
    @ViewBuilder var controls: Controls
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).font(.title2.bold())
                        Text(subtitle).font(.callout).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 16)
                    controls
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .padding(.bottom, 14)

            Divider()

            ScrollView {
                content
                    .padding(.horizontal, 24)
                    .padding(.vertical, 20)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

/// The project and range pickers, shared by Overview and Observations.
struct ScopeControls: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        HStack(spacing: 12) {
            Picker("Project", selection: $model.project) {
                Text(ProjectFilter.allProjectsLabel).tag(String?.none)
                ForEach(model.projects, id: \.self) { project in
                    Text(project).tag(String?.some(project))
                }
            }
            .labelsHidden()
            .frame(width: 180)
            .help("Every figure below is for this project alone.")

            Picker("Range", selection: $model.range) {
                ForEach(ChartRange.allCases) { range in
                    Text(range.label).tag(range)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 210)
            .help("How far back the charts look. Eight weeks is the default.")
        }
    }
}

/// Which stored review to read, newest first.
struct ReviewPicker: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        HStack(spacing: 12) {
            if model.reviews.isEmpty {
                Text("none stored").font(.callout).foregroundStyle(.secondary)
            } else {
                // Bound through the resolved review rather than straight to `selectedReview`,
                // because that property is nil for "the newest one" and a picker with no tag
                // matching its selection draws an empty box. Writing to it still selects.
                Picker(
                    "Review",
                    selection: Binding(
                        get: { model.review?.id },
                        set: { model.selectedReview = $0 }
                    )
                ) {
                    ForEach(model.reviews) { review in
                        Text("Review \(review.id) - \(review.rangeEnd)")
                            .tag(Int?.some(review.id))
                    }
                }
                .labelsHidden()
                .frame(width: 220)
                .help("Every review this store has kept, newest first.")
            }
            Button(model.isBusy ? "Writing..." : "Review now") { model.reviewNow() }
                .disabled(model.isBusy)
        }
    }
}

// MARK: - the two states every screen has

/// Nothing to draw, and why. Never an empty rectangle: an empty screen that says nothing is
/// indistinguishable from a broken one.
struct EmptyStateView: View {

    let symbol: String
    let title: String
    let detail: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: symbol)
                .font(.system(size: 30, weight: .light))
                .foregroundStyle(.tertiary)
            Text(title).font(.headline)
            Text(detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
    }
}

/// The store said no. The same sentence `StoreError` writes, which already names both
/// contract versions and says which side to update, plus the one button worth offering.
struct ContractMismatchView: View {

    let message: String
    var onRetry: () -> Void = {}

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(.orange)
            Text("Prudence cannot read this store").font(.title3.bold())
            Text(message)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 480)
            Text("Nothing is drawn from a schema this build does not understand.")
                .font(.caption)
                .foregroundStyle(.tertiary)
            Button("Try again", action: onRetry)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
    }
}

// MARK: - the pieces the screens share

/// One figure with its name above it and, where it has one, the number it is over on hover.
struct SummaryCard: View {

    let title: String
    let value: String
    var detail: String?
    var help: String?
    /// The review's own cards, of which there can be six in a row, are smaller than the
    /// Overview's three.
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 2 : 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(value)
                .font(
                    compact
                        ? .system(.title3, design: .rounded).weight(.medium)
                        : .system(.title, design: .rounded).weight(.medium)
                )
            if let detail {
                Text(detail).font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(compact ? 10 : 14)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
        .help(help ?? title)
    }
}

/// A block of the page: a heading, an optional line under it, and whatever it holds.
struct Panel<Content: View>: View {

    let title: String
    var note: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                if let note {
                    Text(note).font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 12))
    }
}

/// A plain table of already-formatted strings. Nothing in it is computed here: the cells are
/// the texts `reviews/build.py` wrote, which is what keeps this screen and `prudence show`
/// incapable of printing different numbers.
struct StringTable: View {

    let headers: [String]
    let rows: [[String]]
    /// Which column gets the remaining width. The first, unless a table is mostly prose.
    var wideColumn: Int = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !headers.isEmpty {
                row(headers, isHeader: true)
                Divider()
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { index, cells in
                row(cells, isHeader: false)
                if index < rows.count - 1 { Divider().opacity(0.4) }
            }
        }
    }

    private func row(_ cells: [String], isHeader: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ForEach(Array(cells.enumerated()), id: \.offset) { index, cell in
                Text(cell)
                    .font(isHeader ? .caption.weight(.semibold) : .callout)
                    .foregroundStyle(isHeader ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
                    .frame(
                        maxWidth: index == wideColumn ? .infinity : 150,
                        alignment: .leading
                    )
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 5)
    }
}

/// The colour of a purpose, everywhere it appears.
///
/// A fixed table rather than Swift Charts' automatic scale, because the automatic one assigns
/// colours by the order the series happen to arrive: a week where nobody did research would
/// silently move every other purpose one colour along, and two screenshots taken a week apart
/// would not be comparable. The purposes are the six `facts/purpose.PURPOSES` names; anything
/// else the engine grows later falls to grey and is still drawn.
enum PurposeColour {

    static let order = ["development", "debugging", "research", "conversation", "mixed", "unknown"]

    private static let table: [String: Color] = [
        "development": .blue,
        "debugging": .orange,
        "research": .teal,
        "conversation": .purple,
        "mixed": .indigo,
        "unknown": .gray,
    ]

    static func colour(_ purpose: String) -> Color { table[purpose] ?? .gray }

    /// The domain and range for `chartForegroundStyleScale`, over the purposes actually here
    /// plus any the table does not know, so the scale covers every bar that will be drawn.
    static func scale(for purposes: [String]) -> (domain: [String], range: [Color]) {
        let known = order.filter { purposes.contains($0) }
        let unknown = purposes.filter { !order.contains($0) }.sorted()
        let domain = known + unknown
        return (domain, domain.map(colour))
    }
}
