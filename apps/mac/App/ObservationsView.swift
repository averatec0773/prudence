import PrudenceModels
import PrudenceStore
import PrudenceUI
import SwiftUI

/// The observations, **variant C**: grouped by behaviour.
///
/// The founder's choice on 2026-09-20. One card per behaviour fact, with the threshold that
/// made the split at the top of it and both of that split's outcomes inside: survival at head
/// and rework are two readings of the same two groups of sessions, and putting them in two
/// cards makes them look like two findings.
///
/// Every card is `PairedBarsChart`, which is the chart this product exists for: one behaviour,
/// two sides of the reader's own sessions, one median each, **`n` on both bars**, and the gap
/// in points underneath. The coverage and the method mix sit in the same block as the numbers
/// they qualify, never a section away (principle 3).
///
/// The sentence above the bars is **composed here from the row's columns**, in the interface
/// language (`PrudenceUI/ObservationText`). At contract 1 the app restated the phrase table
/// from `store/observations.py` in Swift and a test pinned it word for word; contract 2 stored
/// the prose and the restatement went away; batch 1 brought a composer back, deliberately,
/// because a Chinese interface cannot show an English sentence. The difference from contract 1
/// is the check: the engine's own sentence is still on the row, and a test asserts the
/// composer's English equals it for every row of the fixture.
///
/// **The founder's reservation, kept open on purpose (M4 plan, "Open").** With many projects,
/// which projects to observe and how to classify the observations consistently is an unsolved
/// design question. The screen sorts by the largest absolute gap and shows everything above the
/// engine's floors, which is honest at two projects and will not be at twenty: at that size the
/// list becomes a ranking, and a ranking is a score by another name. Revisit with full real
/// data before adding any filter, cut-off or "top N" here — a cheap fix would decide the
/// question by accident.
struct ObservationsView: View {

    @ObservedObject var model: WindowModel

    /// The rows for the chosen scope, already filtered pooled-or-project by `WindowModel`.
    private var rows: [AppObservationRow] { model.observationRows }

    /// One card per behaviour, biggest gap first.
    ///
    /// Grouped on `repo_key|fact` rather than on the fact alone, so that under "All projects"
    /// two pooled rows about the same behaviour meet and a project's own row never joins a
    /// pooled one. The group's place in the list is its **largest** gap, not the mean of its
    /// rows: a card is as interesting as its most interesting bar.
    private var groups: [ObservationGroup] {
        var order: [String] = []
        var byKey: [String: [AppObservationRow]] = [:]
        for row in rows {
            let key = "\(row.repoKey)|\(row.fact)"
            if byKey[key] == nil { order.append(key) }
            byKey[key, default: []].append(row)
        }
        return order.map { key in
            ObservationGroup(key: key, rows: byKey[key] ?? [])
        }
        .sorted { left, right in
            left.gap == right.gap ? left.key < right.key : left.gap > right.gap
        }
    }

    var body: some View {
        if rows.isEmpty {
            EmptyState(symbol: "lightbulb", title: emptyTitle, detail: emptyDetail)
        } else {
            VStack(alignment: .leading, spacing: Space.cardGap) {
                Text(verbatim: scopeLine)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(groups) { group in
                    ObservationCard(group: group)
                }
                Text(.observationFloor)
                    .font(Type.caption)
                    .foregroundStyle(Ink.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var scopeLine: String {
        model.project == nil
            ? Str.observationScopePooled.text : Str.observationScopeProject.text
    }

    private var emptyTitle: String {
        model.project == nil
            ? Str.observationsEmptyPooledTitle.text : Str.observationsEmptyProjectTitle.text
    }

    private var emptyDetail: String {
        model.project == nil
            ? Str.observationsEmptyPooledDetail.text : Str.observationsEmptyProjectDetail.text
    }
}

/// One behaviour's rows: the split, and the one or two outcomes measured over it.
struct ObservationGroup: Identifiable {

    let key: String
    /// Sorted by gap, so the row that earns the card its place is the first one drawn.
    let rows: [AppObservationRow]

    var id: String { key }

    init(key: String, rows: [AppObservationRow]) {
        self.key = key
        self.rows = rows.sorted {
            $0.gap == $1.gap ? $0.outcome < $1.outcome : $0.gap > $1.gap
        }
    }

    var first: AppObservationRow? { rows.first }
    /// The card's place in the list: its largest gap.
    var gap: Double { rows.map(\.gap).max() ?? 0 }
    var isPooled: Bool { first?.isPooled ?? false }
    var fact: String { first?.fact ?? "" }
    var project: String? { first?.project }
    var thresholdText: String { first?.thresholdText ?? "" }
}

/// One behaviour, its threshold, and one paired-bars row per outcome.
struct ObservationCard: View {

    let group: ObservationGroup

    var body: some View {
        Card(padding: Space.cardPadding) {
            VStack(alignment: .leading, spacing: Space.s4) {
                header
                ForEach(group.rows, id: \.observationId) { row in
                    OutcomeRow(row: row)
                }
            }
        }
    }

    /// The behaviour in two or three words, who it is about, and the line that made the split.
    ///
    /// A pooled row is labelled **across your projects** and nothing else: it is computed only
    /// for a behaviour no single project had the sessions to answer, and it is not a finding
    /// about any one of them (principle 2).
    private var header: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
                Text(verbatim: ObservationText.shortLabel(for: group.fact))
                    .font(Type.headline)
                    .foregroundStyle(Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
                CoverageChip(
                    group.isPooled
                        ? Str.observationPooledTag.text
                        : (group.project ?? Str.scopeAllProjects.text))
                Spacer(minLength: 0)
            }
            MethodLine(Str.observationThreshold(group.thresholdText))
        }
    }
}

/// One outcome of one split: the sentence, the two bars with their counts, and the caveat.
struct OutcomeRow: View {

    let row: AppObservationRow

    private var sentence: String { ObservationText.sentence(row: row) }
    private var caveat: String { ObservationText.caveat(row: row) }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            // The outcome names the row; the gap is printed once, under the bars, by
            // `PairedBarsChart` itself. A chip here as well would say it twice.
            Text(verbatim: ObservationText.outcomeLabel(row.outcome))
                .font(Type.footnoteStrong)
                .foregroundStyle(Ink.primary)
            Text(verbatim: sentence)
                .font(Type.footnote)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            PairedBarsChart(
                with: .init(
                    label: ObservationText.shortLabel(for: row.fact),
                    value: row.withValue,
                    n: row.withN),
                without: .init(
                    label: Str.observationSideDidNot.text,
                    value: row.withoutValue,
                    n: row.withoutN),
                tint: row.outcome == "rework" ? Outcome.rework : Outcome.alive
            )
            HStack(spacing: Space.s2) {
                CoverageChip(caveat)
                MethodLine(
                    Str.observationSessionsDidDidNot(
                        Fmt.sessions(row.withN), Fmt.count(row.withoutN)))
                Spacer(minLength: 0)
            }
        }
        .help("\(sentence)\n\(caveat)")
    }
}
