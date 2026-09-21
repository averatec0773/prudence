import AppKit
import PrudenceModels
import PrudenceUI
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
/// activation-policy toggle `AppDelegate` owns (M3 plan, open question 1). `onClose` is how it
/// hears about it.
///
/// The size **and the position** are remembered by `setFrameAutosaveName`, which writes the
/// frame into `UserDefaults` under `NSWindow Frame PrudenceMainWindow` and restores it on the
/// next launch. `contentMinSize` rather than `minSize`, so the 900 x 600 floor is the floor of
/// the content and does not shrink by the height of the title bar.
///
/// The order below is the part that is easy to get wrong and that batch 3 fixed: `center()`
/// first, then `setFrameAutosaveName`, then **`setFrameUsingName`**. Setting the autosave name
/// registers the window for *saving*; it restores the saved frame only if one is already
/// there when the name is set, and a window whose content view is installed afterwards is
/// resized by its content and loses it either way. Asking for the frame explicitly, after the
/// content is in, is what makes the window actually come back where it was left. Which screen
/// the window was on comes back with the frame, and `constrainFrameRect` puts a window whose
/// display has gone back onto one that exists.
///
/// The sidebar item and the two pickers are remembered as well, by `WindowModel.Memory`.
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
        window.title = Product.name
        window.isReleasedWhenClosed = false
        window.contentMinSize = Self.minimumSize
        window.center()
        window.setFrameAutosaveName(Self.frameAutosaveName)
        window.contentViewController = NSHostingController(
            rootView: MainWindowContentView(
                model: model,
                settings: settings,
                launchAtLogin: launchAtLogin,
                onSettingsChange: onSettingsChange
            )
            .prudenceTheme(.system)
        )
        // After the content view is in, or the hosting controller's own sizing pass throws
        // the restored frame away and the window opens centred at its minimum every time.
        window.setFrameUsingName(Self.frameAutosaveName)
        window.delegate = self
    }

    static let frameAutosaveName = NSWindow.FrameAutosaveName("PrudenceMainWindow")

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
///
/// The sidebar and the strip of controls above each screen are the navigation and control
/// layer, so they carry the glass. The screens below them do not: every card, table and chart
/// keeps an opaque surface (`PrudenceUI/Glass.swift`).
struct MainWindowContentView: View {

    @ObservedObject var model: WindowModel
    @ObservedObject var settings: AppSettings
    var launchAtLogin: any LaunchAtLoginControlling
    var onSettingsChange: () -> Void = {}

    var body: some View {
        NavigationSplitView {
            List(MainSection.allCases, selection: $model.section) { section in
                Label(sectionTitle(section), systemImage: section.symbol).tag(section)
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 260)
            .prudenceGlass(.sidebar)
        } detail: {
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(Surface.canvas)
        }
        .frame(
            minWidth: MainWindowController.minimumSize.width,
            minHeight: MainWindowController.minimumSize.height
        )
        .background(shortcuts)
    }

    /// The keyboard, as four hidden buttons rather than as a `Commands` scene.
    ///
    /// This app has no SwiftUI `App` and no menu bar of its own — it is an `LSUIElement`
    /// accessory whose windows are hand-built `NSWindow`s (`apps/mac/README.md`, convention
    /// 1) — so `.commands { }`, which is the documented home for `keyboardShortcut`, has
    /// nowhere to attach. A zero-size, hidden `Button` with a shortcut on it is the shape that
    /// works in a plain hosting view: SwiftUI registers the shortcut with the window's own
    /// key-equivalent handling, and a hidden button is still reachable that way.
    ///
    ///     Cmd-1  Overview        Cmd-R  Review now
    ///     Cmd-2  Review          Cmd-,  Settings
    ///     Cmd-3  Observations
    ///     Cmd-4  Settings
    ///
    /// Esc belongs to the popover, not here: it is a status item away in `StatusItem.swift`.
    private var shortcuts: some View {
        ZStack {
            ForEach(Array(MainSection.allCases.enumerated()), id: \.element) { index, section in
                Button("") { model.section = section }
                    .keyboardShortcut(
                        KeyEquivalent(Character("\(index + 1)")), modifiers: .command)
            }
            Button("") { model.reviewNow() }
                .keyboardShortcut("r", modifiers: .command)
                .disabled(model.isBusy)
            Button("") { model.section = .settings }
                .keyboardShortcut(",", modifiers: .command)
        }
        .frame(width: 0, height: 0)
        .opacity(0)
        .accessibilityHidden(true)
    }

    private func sectionTitle(_ section: MainSection) -> String {
        switch section {
        case .overview: return Str.sectionOverview.text
        case .review: return Str.sectionReview.text
        case .observations: return Str.sectionObservations.text
        case .settings: return Str.sectionSettings.text
        }
    }

    @ViewBuilder
    private var detail: some View {
        if let problem = model.storeError {
            ContractMismatchState(message: problem) { model.refresh() }
        } else {
            switch model.section {
            case .overview:
                ScreenScaffold(title: Str.sectionOverview.text, subtitle: rangeSubtitle) {
                    ScopeControls(model: model)
                } content: {
                    OverviewView(model: model)
                }
            case .review:
                ScreenScaffold(title: Str.sectionReview.text, subtitle: reviewSubtitle) {
                    ReviewPicker(model: model)
                } content: {
                    ReviewView(model: model)
                }
            case .observations:
                ScreenScaffold(
                    title: Str.sectionObservations.text, subtitle: observationsSubtitle
                ) {
                    ScopeControls(model: model)
                } content: {
                    ObservationsView(model: model)
                }
            case .settings:
                SettingsView(
                    settings: settings,
                    launchAtLogin: launchAtLogin,
                    onChange: onSettingsChange,
                    status: { model.data.status.map(StatusModel.init(row:)) }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
    }

    private var rangeSubtitle: String {
        let scope = model.project ?? Str.scopeAllProjects.text
        return Str.scopeSubtitle(
            scope, Fmt.rangeDescription(model.range, now: model.now))
    }

    private var reviewSubtitle: String {
        guard let review = model.review else { return Str.reviewNoneYet.text }
        // Both halves through the interface layer: `ReviewModel.scope` is the app's own
        // English for "every project" and `createdAt` is a stored `yyyy-MM-dd` that a reader
        // writes their own way (M4 plan, "Batch 2 inputs").
        return Str.reviewScopeWritten(
            ReviewText.scope(review.project), ReviewText.written(review.createdAt, now: model.now))
    }

    private var observationsSubtitle: String {
        model.project == nil
            ? Str.observationsSubtitlePooled.text
            : Str.observationsSubtitleProject(model.project ?? "")
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
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Type.title2).foregroundStyle(Ink.primary)
                    Text(subtitle).font(Type.footnote).foregroundStyle(Ink.secondary)
                }
                Spacer(minLength: Space.s4)
                ControlStrip(spacing: Space.s3) { controls }
            }
            .padding(.horizontal, Space.s6)
            .padding(.top, Space.s5)
            .padding(.bottom, Space.s4)
            .prudenceGlass(.toolbar, cornerRadius: 0)

            ScrollView {
                content
                    .padding(.horizontal, Space.s6)
                    .padding(.vertical, Space.s5)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

/// The project and range pickers, shared by Overview and Observations. System controls: a
/// pop-up button and a segmented control, neither of them redrawn.
struct ScopeControls: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        Picker(Str.scopeProject.text, selection: $model.project) {
            Text(Str.scopeAllProjects.text).tag(String?.none)
            ForEach(model.projects, id: \.self) { project in
                Text(project).tag(String?.some(project))
            }
        }
        .pickerStyle(.menu)
        .labelsHidden()
        .frame(width: 180, height: ReviewPicker.controlHeight)
        .help(Str.scopeProjectHelp.text)

        Picker(Str.scopeRange.text, selection: $model.range) {
            ForEach(ChartRange.allCases) { range in
                Text(Fmt.range(range)).tag(range)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 210, height: ReviewPicker.controlHeight)
        .help(Str.scopeRangeHelp.text)
    }
}

/// Which stored review to read, newest first.
///
/// The picker and the button share one baseline and one height, which is the popover's grid
/// discipline applied to the window's own header: a 28 pt pop-up button beside a 28 pt push
/// button, centred in a `ControlStrip` that lays them on the same line. Before batch 3 the
/// button was 28 pt and the picker took whatever height AppKit gave it, so the two sat a
/// couple of points out from each other.
struct ReviewPicker: View {

    /// The one control height in a header, so nothing in a strip is taller than its neighbour.
    static let controlHeight: CGFloat = 28

    @ObservedObject var model: WindowModel

    var body: some View {
        if model.reviews.isEmpty {
            Text(.reviewNoneStored).font(Type.footnote).foregroundStyle(Ink.secondary)
        } else {
            // Bound through the resolved review rather than straight to `selectedReview`,
            // because that property is nil for "the newest one" and a picker with no tag
            // matching its selection draws an empty box. Writing to it still selects.
            Picker(
                Str.sectionReview.text,
                selection: Binding(
                    get: { model.review?.id },
                    set: { model.selectedReview = $0 }
                )
            ) {
                ForEach(model.reviews) { review in
                    Text(ReviewText.option(id: review.id, rangeEnd: review.rangeEnd))
                        .tag(Int?.some(review.id))
                }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(width: 240, height: Self.controlHeight)
        }
        Button(model.isBusy ? Str.reviewWriting.text : Str.menuReviewNow.text) {
            model.reviewNow()
        }
        .buttonStyle(.prudencePrimary)
        .disabled(model.isBusy)
    }
}

// MARK: - a table of already-formatted strings

/// Nothing in it is computed here: the cells are the texts `reviews/build.py` wrote, which is
/// what keeps this screen and `prudence show` incapable of printing different numbers.
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
        HStack(alignment: .top, spacing: Space.s3) {
            ForEach(Array(cells.enumerated()), id: \.offset) { index, cell in
                Text(cell)
                    .font(isHeader ? Type.captionStrong : Type.footnote.monospacedDigit())
                    .foregroundStyle(isHeader ? Ink.secondary : Ink.primary)
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
