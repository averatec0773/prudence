import PrudenceModels
import PrudenceUI
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

/// The dropdown: **menu bar variant C, with every block keeping its small caption**, which is
/// what the founder settled on after the M4 mockups (`docs/design/mockups/NOTES.md`).
///
/// C is chart-first: today as a headline, then the week as a one-row stacked bar with the top
/// three purposes as a legend under it, the latest observation with its caveat, and the two
/// stamps. A's captions come back on every block, because a value with no label answers a
/// question the reader has to guess.
///
///     Today               2 sessions, 17 edits, 3 commits
///     This week           [====  ==  = ]   development 71%, research 18%, debugging 11%
///                         1.2M tokens · 9.4 hours
///     Latest observation  In prudence, your 7 sessions that ran tests reworked 12% ...
///                         coverage 90%, method: 4 fact, 3 inferred
///     Last ingest         20 Sep 18:04 (4 minutes ago)
///     Last review         Review 1, 8 Sep 2026 to 15 Sep 2026: What you did
///
/// Not one of those numbers is computed here. Each comes from an `app_*` view through
/// `PrudenceModels` (M3 rule 8, ARCHITECTURE rule 14). The observation's sentence is the one
/// piece of prose the app writes, and it writes it in the interface language from the row's
/// own columns rather than translating the engine's English; `ObservationText` is that rule
/// and a test pins its English output to `app_observation.sentence` word for word.
///
/// The popover is the control and navigation layer, so it is the one surface here that is
/// made of glass. Nothing inside it is: the observation card, the chips and the bar all keep
/// their opaque surface, because a figure read against a wallpaper is a figure the reader
/// cannot check.
struct MenuContentView: View {

    @ObservedObject var model: MenuViewModel
    var actions: MenuActions

    private var snapshot: Snapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.popoverGap) {
            header
            blocks
            if let problem = problemText {
                Divider().opacity(0.6)
                problemLine(problem)
            }
            Divider().opacity(0.6)
            buttons
            if let message = model.actionMessage {
                Text(message)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(Space.popoverPadding)
        .frame(width: 380)
        .background(Surface.canvas.opacity(materialBackdropOpacity))
        .prudenceGlass(.popover, cornerRadius: 0)
    }

    /// The glass path samples the wallpaper on its own; the standard path needs a fill under
    /// the content or the popover would be the system's default grey.
    @Environment(\.prudenceTheme) private var theme
    private var materialBackdropOpacity: Double { theme.wantsTranslucency ? 0 : 1 }

    // MARK: - the head

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
            BrandMark(size: 16)
            Text(Product.name)
                .font(Type.headline)
                .foregroundStyle(Ink.primary)
            Spacer(minLength: Space.s2)
            Text(engineText)
                .font(Type.caption.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
        }
    }

    // MARK: - the five blocks

    private var blocks: some View {
        VStack(alignment: .leading, spacing: Space.popoverGap) {
            // The caption size, not a 20 pt headline. Variant C put today at headline weight
            // and the founder read it as heavy (M4 plan, "Batch 2 inputs"): "no session
            // recorded today" set in a title is a statement about the day rather than a line
            // in a status glance. Every block in this popover now reads at the same weight,
            // which is what the caption on each of them was for.
            StatRow(Str.menuToday.text) {
                Text(verbatim: todayLine)
                    .font(Type.footnote.monospacedDigit())
                    .foregroundStyle(Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            StatRow(Str.menuThisWeek.text) { week }

            Divider().opacity(0.6)

            StatRow(Str.menuLatestObservation.text) { observation }

            Divider().opacity(0.6)

            StatRow(Str.menuLastIngest.text) {
                Text(ingestText)
                    .font(Type.footnote.monospacedDigit())
                    .foregroundStyle(Ink.primary)
            }
            StatRow(Str.menuLastReview.text) {
                Text(reviewText)
                    .font(Type.footnote)
                    .foregroundStyle(Ink.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// `2 sessions, 17 edits, 3 commits`. Edits are left out when nothing measured any: a
    /// missing count is not a zero (ARCHITECTURE rule 10).
    private var todayLine: String {
        let today = snapshot.today
        guard today.sessions > 0 || today.commits > 0 else {
            return Str.menuNoSessionsToday.text
        }
        var parts = [Fmt.sessions(today.sessions)]
        if let edits = today.edits { parts.append(Fmt.edits(edits)) }
        parts.append(Fmt.commits(today.commits))
        return Fmt.list(parts)
    }

    /// The week as a bar, its top three as a legend, and the two totals the bar is over.
    private var week: some View {
        let usage = snapshot.week
        return VStack(alignment: .leading, spacing: 6) {
            MiniStack(
                slices: usage.all.map { MiniStack.Slice(purpose: $0.purpose, tokens: $0.tokens) }
            )
            if usage.top.isEmpty {
                Text(.menuNoTokensThisWeek)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
            } else {
                PurposeLegend(
                    purposes: usage.top.map(\.purpose),
                    shares: Dictionary(
                        usage.top.map { ($0.purpose, $0.share) }, uniquingKeysWith: { first, _ in
                            first
                        })
                )
                HStack(spacing: Space.s3) {
                    Text(Fmt.tokenPhrase(usage.total))
                    Text(Fmt.hourPhrase(usage.activeMinutes / 60))
                    Spacer(minLength: 0)
                }
                .font(Type.caption.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
            }
        }
    }

    @ViewBuilder
    private var observation: some View {
        if let row = snapshot.observationRow {
            VStack(alignment: .leading, spacing: 5) {
                Text(ObservationText.sentence(row: row))
                    .font(Type.footnote)
                    .foregroundStyle(Ink.primary)
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)
                CoverageChip(ObservationText.caveat(row: row))
            }
        } else {
            Text(.menuNoObservation)
                .font(Type.footnote)
                .foregroundStyle(Ink.secondary)
        }
    }

    private var ingestText: String {
        guard let date = snapshot.status?.lastIngest else { return Str.menuNever.text }
        return Str.menuStamped(Fmt.stamp(date), Fmt.relative(date, now: snapshot.readAt))
    }

    private var reviewText: String {
        guard let review = snapshot.review else { return Str.menuNoReview.text }
        return ReviewText.headline(review)
    }

    // MARK: - the foot

    /// C's layout: the one prominent action full width, then the two that change the record,
    /// then Settings and Quit with Quit pushed to the right, where the hand already is.
    private var buttons: some View {
        VStack(spacing: Space.s2) {
            Button(Str.menuOpenPrudence.text) { act(actions.openMain) }
                .buttonStyle(.prudencePrimary)
                .frame(maxWidth: .infinity)
            HStack(spacing: Space.s2) {
                Button(Str.menuReviewNow.text) { act(model.reviewNow) }
                    .frame(maxWidth: .infinity)
                Button(Str.menuIngestNow.text) { act(model.ingestNow) }
                    .frame(maxWidth: .infinity)
                    .disabled(model.isBusy)
            }
            .buttonStyle(.prudence)
            HStack(spacing: Space.s2) {
                Button(Str.menuSettings.text) { act(actions.openSettings) }
                    .buttonStyle(.prudence)
                Spacer(minLength: 0)
                Button(Str.menuQuit.text) { act(actions.quit) }
                    .buttonStyle(.prudencePlain)
            }
        }
        .prudenceGlassCluster(spacing: Space.s2)
    }

    /// The engine's own version, or why there is not one.
    private var engineText: String {
        if let version = model.engineVersion { return version }
        if model.engineError != nil { return Str.menuEngineMissing.text }
        return Str.menuEngineChecking.text
    }

    /// The one banner: a contract mismatch, a missing store, or a missing engine. The store's
    /// complaint comes first, because a mismatch is the thing the user must act on.
    private var problemText: String? {
        if let storeError = snapshot.storeError { return storeError }
        if let engineError = model.engineError { return engineError }
        return nil
    }

    private func problemLine(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.triangle")
            .font(Type.caption)
            .foregroundStyle(Outcome.rework)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// Close the popover, then do the thing. An action that left it open would sit over the
    /// window it just opened.
    private func act(_ action: @escaping () -> Void) {
        actions.willAct()
        action()
    }
}
