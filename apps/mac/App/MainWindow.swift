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
/// activation-policy toggle `AppDelegate` owns. `onClose` is how it hears about it.
@MainActor
final class MainWindowController: NSObject, NSWindowDelegate {

    private let window: NSWindow
    private let onClose: () -> Void

    init(model: MenuViewModel, onClose: @escaping () -> Void) {
        self.onClose = onClose
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 900, height: 600),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        super.init()
        window.title = "Prudence"
        window.isReleasedWhenClosed = false
        window.center()
        window.setFrameAutosaveName("PrudenceMainWindow")
        window.contentViewController = NSHostingController(
            rootView: MainWindowContentView(model: model))
        window.delegate = self
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        // The policy flip has to happen after this window is really gone, or the count of
        // visible windows still includes it.
        DispatchQueue.main.async { [onClose] in onClose() }
    }
}

/// The window's content for this batch: the same numbers the dropdown shows, and a line
/// saying what comes next. The charts are M3 task 8; this exists so that "Open Prudence"
/// opens something real, with the activation policy and the window lifetime already proven.
struct MainWindowContentView: View {

    @ObservedObject var model: MenuViewModel

    private var snapshot: Snapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Prudence").font(.largeTitle.bold())
                Text(subtitle).font(.callout).foregroundStyle(.secondary)
            }

            HStack(alignment: .top, spacing: 14) {
                card("Today", snapshot.today.line)
                card("This week", snapshot.week.line)
                card("Last ingest", snapshot.status?.lastIngestText(now: snapshot.readAt) ?? "never")
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Latest observation").font(.caption).foregroundStyle(.secondary)
                Text(snapshot.observation?.sentence ?? "none yet")
                    .font(.body)
                    .fixedSize(horizontal: false, vertical: true)
                if let caveat = snapshot.observation?.caveat {
                    Text(caveat).font(.caption).foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Last review").font(.caption).foregroundStyle(.secondary)
                Text(snapshot.review?.headline ?? "no review yet").font(.body)
            }

            Spacer()

            HStack(spacing: 8) {
                Image(systemName: "rectangle.on.rectangle")
                Text("Overview arrives in the next batch.")
            }
            .font(.callout)
            .foregroundStyle(.secondary)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
        }
        .padding(28)
        .frame(minWidth: 720, minHeight: 480, alignment: .topLeading)
    }

    private var subtitle: String {
        if let error = snapshot.storeError { return error }
        guard let status = snapshot.status else { return "Nothing ingested yet." }
        return
            "\(status.sessions) sessions across \(status.projects) projects, engine \(status.engineVersion), contract \(status.contractVersion)."
    }

    private func card(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
    }
}
