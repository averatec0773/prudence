import PrudenceModels
import SwiftUI

/// What the four buttons do. Closures rather than a delegate, so the view can be rendered
/// off-screen by `Render/` with nothing behind them.
struct MenuActions {
    var openMain: () -> Void = {}
    var openSettings: () -> Void = {}
    var quit: () -> Void = {}
    /// Called before any of the above, to put the popover away first.
    var willAct: () -> Void = {}
}

/// The dropdown.
///
/// Line for line the rumps prototype it replaces, so the founder can hold the two side by side
/// and compare them with `prudence status` and `prudence usage --last 7d`:
///
///     Today: 2 sessions, 3 commits
///     This week: development 88%, research 12%
///     Latest observation: In prudence, your 7 sessions that ran tests reworked 12% ...
///     Last ingest: 20 Sep 18:04 (4 minutes ago)
///     Last review: Review 1, 2026-09-08 to 2026-09-15: What you did
///
/// Not one of those numbers is computed here. Each comes from an `app_*` view through
/// `PrudenceModels` (M3 rule 8), and the two lines that could not (edits per day; the
/// observation's own sentence) are named as contract requests in `apps/mac/README.md` rather
/// than quietly joined in Swift.
struct MenuContentView: View {

    @ObservedObject var model: MenuViewModel
    var actions: MenuActions

    private var snapshot: Snapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().padding(.vertical, 8)
            lines
            if let problem = problemText {
                Divider().padding(.vertical, 8)
                Label(problem, systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Divider().padding(.vertical, 8)
            buttons
            if let message = model.actionMessage {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
            }
        }
        .padding(14)
        .frame(width: 380)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Prudence").font(.headline)
            Spacer()
            Text(engineText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var lines: some View {
        VStack(alignment: .leading, spacing: 6) {
            row("Today", snapshot.today.line)
            row("This week", snapshot.week.line)
            row(
                "Latest observation",
                snapshot.observation?.short ?? "none yet",
                help: snapshot.observation.map { "\($0.sentence)\n\($0.caveat)" }
            )
            row("Last ingest", snapshot.status?.lastIngestText(now: snapshot.readAt) ?? "never")
            row("Last review", snapshot.review?.headline ?? "no review yet")
        }
    }

    private func row(_ label: String, _ value: String, help: String? = nil) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 108, alignment: .leading)
            Text(value)
                .font(.callout)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .help(help ?? value)
    }

    private var buttons: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Button("Open Prudence") { act(actions.openMain) }
                Button("Review now") { act(model.reviewNow) }
                Button("Ingest now") { act(model.ingestNow) }
                    .disabled(model.isBusy)
            }
            HStack(spacing: 8) {
                Button("Settings...") { act(actions.openSettings) }
                Spacer()
                Button("Quit") { act(actions.quit) }
            }
        }
    }

    /// The engine's own version, or why there is not one.
    private var engineText: String {
        if let version = model.engineVersion { return version }
        if model.engineError != nil { return "engine not found" }
        return "checking..."
    }

    /// The one banner: a contract mismatch, a missing store, or a missing engine. The store's
    /// complaint comes first, because a mismatch is the thing the user must act on.
    private var problemText: String? {
        if let storeError = snapshot.storeError { return storeError }
        if let engineError = model.engineError { return engineError }
        return nil
    }

    /// Close the popover, then do the thing. An action that left it open would sit over the
    /// window it just opened.
    private func act(_ action: @escaping () -> Void) {
        actions.willAct()
        action()
    }
}
