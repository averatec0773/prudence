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
/// Batch 3 rebuilt it as C. Batches 1 and 2 had shipped A's shape — five label-and-value rows
/// at one weight — carrying C's content, which is not the variant the founder chose. C is
/// chart-first, and the order below is `dropdown.html`'s `variantC` with the `captions`
/// branch on, which is the amendment: every block keeps its small caption, because a value
/// with no label answers a question the reader has to guess.
///
///     Today                                                      <- the caption, on its own line
///     2 sessions, 17 edits, 3 commits                            <- the one headline
///     20 September 2026
///     This week
///     development 71%, research 18%, debugging 11%
///     [==================  =======  ====                      ]
///     1.2M tokens   8 sessions   9.4 hours
///     ▪ development  ▪ research  ▪ debugging
///     -------------------------------------------------------
///     Latest observation
///     In prudence, your 7 sessions that ran tests reworked 12% ...
///     coverage 90%, method: 4 fact, 3 inferred
///     -------------------------------------------------------
///     Last ingest
///     20 Sep 18:04 (4 minutes ago)
///     Last review
///     Review 1, 8 Sep 2026 to 15 Sep 2026: What you did
///     =======================================================
///     [ Open Prudence                                        ]   <- .pop-foot
///     [ Review now            ] [ Ingest now                 ]
///      Settings...                                      Quit
///
/// **One column, the full width.** Batch 3 shipped the captions in a 96 pt column with the
/// content beside them, and the founder rejected that shape twice: C puts everything in the
/// centre, not a title on the left and a value on the right. So each caption is a line of its
/// own above its block, and every figure, sentence and bar starts on the same left edge and
/// runs to the same right one.
///
/// The widths and the paddings are `tokens.css`'s own: 360 pt wide, 16 pt of side padding,
/// 12 pt between blocks, and the footer on `Surface.secondary` under one hairline.
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
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, Space.popoverPadding)
                .padding(.top, Space.popoverPadding)
                .padding(.bottom, Space.s2)
            blocks
                .padding(.horizontal, Space.popoverPadding)
                .padding(.bottom, Space.s3)
            foot
        }
        .frame(width: Space.popoverWidth)
        .background(Surface.canvas.opacity(materialBackdropOpacity))
        .prudenceGlass(.popover, cornerRadius: 0)
    }

    /// The glass path samples the wallpaper on its own; the standard path needs a fill under
    /// the content or the popover would be the system's default grey.
    @Environment(\.prudenceTheme) private var theme
    private var materialBackdropOpacity: Double { theme.wantsTranslucency ? 0 : 1 }

    // MARK: - the head

    /// `.pop-head` from `tokens.css`: the mark at 18, the name at headline weight, and the
    /// engine's own version pushed to the right in the smallest type on the surface.
    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
            BrandMark(size: 18)
            Text(Product.name)
                .font(Type.headline)
                .foregroundStyle(Ink.primary)
            Spacer(minLength: Space.s2)
            Text(engineText)
                .font(Type.caption2.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
        }
    }

    // MARK: - the five blocks

    private var blocks: some View {
        VStack(alignment: .leading, spacing: Space.popoverGap) {
            StatBlock(Str.menuToday.text) { todayBlock }

            StatBlock(Str.menuThisWeek.text) { week }

            separator

            StatBlock(Str.menuLatestObservation.text) { observation }

            separator

            StatBlock(Str.menuLastIngest.text) {
                Text(ingestText)
                    .font(Type.caption.monospacedDigit())
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            StatBlock(Str.menuLastReview.text) {
                Text(reviewText)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let problem = problemText {
                separator
                problemLine(problem)
            }
            if let message = model.actionMessage {
                Text(message)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// `.pop-sep`: a 0.5 pt separator with 8 pt of air on each side.
    private var separator: some View {
        Rectangle()
            .fill(Surface.separator)
            .frame(height: 0.5)
            .padding(.vertical, Space.s2 - Space.popoverGap / 2)
    }

    /// Today, variant C's way: the day's counts as the one headline on the surface, with the
    /// date under it in the smallest type.
    ///
    /// Batch 2 pulled this back to caption size because "今天还没有记录到会话" set in a title
    /// read as a statement about the day rather than a line in a glance (M4 plan, "Batch 2
    /// inputs"), and batch 3 put C's headline back at the founder's request. Both notes are
    /// honoured: **counts get the headline, the empty sentence does not.** A number is a
    /// figure worth the size; "no session recorded today" is a caption.
    @ViewBuilder
    private var todayBlock: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let counts = todayCounts {
                Text(verbatim: counts)
                    .font(Type.figure(20, weight: .semibold))
                    .foregroundStyle(Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text(.menuNoSessionsToday)
                    .font(Type.footnote)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(verbatim: Fmt.day(Formatting.day(snapshot.readAt)))
                .font(Type.caption2.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
        }
    }

    /// `2 sessions, 17 edits, 3 commits`, or nil when nothing was recorded today. Edits are
    /// left out when nothing measured any: a missing count is not a zero (ARCHITECTURE
    /// rule 10).
    private var todayCounts: String? {
        let today = snapshot.today
        guard today.sessions > 0 || today.commits > 0 else { return nil }
        var parts = [Fmt.sessions(today.sessions)]
        if let edits = today.edits { parts.append(Fmt.edits(edits)) }
        parts.append(Fmt.commits(today.commits))
        return Fmt.list(parts)
    }

    /// The week, variant C's way: the shares as a sentence, the single stacked bar, the
    /// totals the bar is over, and the legend that says which colour is which.
    ///
    /// The shares are printed once, in the text line. The mockup repeats them in the legend
    /// as well; a share said twice a centimetre apart is a figure a reader has to check
    /// against itself, so the legend here carries the swatch and the name and nothing else.
    private var week: some View {
        let usage = snapshot.week
        return VStack(alignment: .leading, spacing: 6) {
            if usage.all.isEmpty {
                Text(.menuNoTokensThisWeek)
                    .font(Type.footnote)
                    .foregroundStyle(Ink.secondary)
            } else {
                Text(verbatim: shareLine(usage))
                    .font(Type.footnote.monospacedDigit())
                    .foregroundStyle(Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            MiniStack(
                slices: usage.all.map { MiniStack.Slice(purpose: $0.purpose, tokens: $0.tokens) }
            )
            if !usage.all.isEmpty {
                // A wrapping row, not an `HStack`: "1,169.9M tokens" on a real store is wide
                // enough that a fixed row truncated the token count to "1,169.9M to...",
                // and the three figures still have to fit inside 328 pt of content.
                FlowLayout(spacing: Space.s3, lineSpacing: 2) {
                    Text(Fmt.tokenPhrase(usage.total))
                    if let sessions = usage.sessions { Text(Fmt.sessions(sessions)) }
                    Text(Fmt.hourPhrase(usage.activeMinutes / 60))
                }
                .font(Type.caption.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
                .frame(maxWidth: .infinity, alignment: .leading)
                PurposeLegend(purposes: usage.all.map(\.purpose))
            }
        }
    }

    /// `development 88%, research 8%, debugging 4%`, every purpose the week measured.
    private func shareLine(_ usage: WeekUsageModel) -> String {
        Fmt.list(usage.all.map { "\(Fmt.purpose($0.purpose)) \(Fmt.percent($0.share))" })
    }

    @ViewBuilder
    private var observation: some View {
        if let row = snapshot.observationRow {
            VStack(alignment: .leading, spacing: 5) {
                Text(ObservationText.sentence(row: row))
                    .font(Type.body)
                    .foregroundStyle(Ink.primary)
                    .lineLimit(5)
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

    /// C's layout, on **one grid** (batch 3).
    ///
    /// The founder's note on the first real screenshot was that the buttons were not aligned,
    /// and they were not: every row was a different width, because `.frame(maxWidth:
    /// .infinity)` at a call site widens the button and not the shape a `ButtonStyle` draws.
    /// The grid is three rows sharing the popover's own content column, on the same left and
    /// right edges as every block above them, which is what `Space.popoverPadding` already
    /// sets:
    ///
    ///     | Open Prudence                                  |   full width
    ///     | Review now          |  gutter  |  Ingest now    |   two equal cells, one 8 pt gap
    ///     | Settings...                              Quit   |   one baseline, both edges
    ///
    /// The two plain buttons carry no horizontal padding of their own (`PrudenceButtonStyle`),
    /// so their glyphs start on the grid's edges rather than inside them, and they keep the
    /// same 28 pt row height as the filled rows above, so all three baselines line up.
    /// `.pop-foot`: the actions on their own surface, under one hairline.
    ///
    /// Opaque `Surface.secondary` under Standard, and a thin wash of it under Glass: a solid
    /// footer inside a frosted popover would cut a slab out of the material, and the point of
    /// the different surface is only to say "this part is controls, the part above is what
    /// was measured".
    private var foot: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Surface.separator).frame(height: 0.5)
            buttons
                .padding(.horizontal, Space.popoverPadding)
                .padding(.top, Space.s3)
                .padding(.bottom, Space.popoverPadding)
        }
        .background(Surface.secondary.opacity(theme.wantsTranslucency ? 0.3 : 1))
    }

    private var buttons: some View {
        VStack(spacing: Space.s2) {
            Button(Str.menuOpenPrudence.text) { act(actions.openMain) }
                .buttonStyle(.prudencePrimaryWide)
            HStack(spacing: Space.s2) {
                Button(Str.menuReviewNow.text) { act(model.reviewNow) }
                Button(Str.menuIngestNow.text) { act(model.ingestNow) }
                    .disabled(model.isBusy)
            }
            .buttonStyle(.prudenceWide)
            HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
                Button(Str.menuSettings.text) { act(actions.openSettings) }
                Spacer(minLength: Space.s2)
                Button(Str.menuQuit.text) { act(actions.quit) }
            }
            .buttonStyle(.prudencePlain)
        }
        .frame(maxWidth: .infinity)
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
