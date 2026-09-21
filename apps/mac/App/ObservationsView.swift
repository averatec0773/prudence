import PrudenceModels
import PrudenceStore
import PrudenceUI
import SwiftUI

/// The observation rows, biggest gap first.
///
/// One row is one sentence and the line that has to travel with it: the coverage, and how
/// many of the commits behind it were established as fact rather than inferred. Principle 3
/// puts them in the same block, never a section away, and nothing on this screen is a share
/// without the two counts it was taken over.
///
/// The sentence is **composed here from the row's columns**, in the interface language
/// (`PrudenceUI/ObservationText`). At contract 1 the app restated the phrase table from
/// `store/observations.py` in Swift and a test pinned it word for word; contract 2 stored the
/// prose and the restatement went away; batch 1 brings a composer back, deliberately, because
/// a Chinese interface cannot show an English sentence. The difference from contract 1 is the
/// check: the engine's own sentence is still on the row, and a test asserts the composer's
/// English equals it for every row of the fixture.
///
/// Batch 1 gave this screen the tokens. The paired bars it is really meant to have are batch 2
/// (`apps/mac/DESIGN.md`).
struct ObservationsView: View {

    @ObservedObject var model: WindowModel

    private var rows: [AppObservationRow] { model.observationRows }

    var body: some View {
        if rows.isEmpty {
            EmptyState(symbol: "lightbulb", title: emptyTitle, detail: emptyDetail)
        } else {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text(scopeLine)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(rows, id: \.observationId) { row in
                    ObservationRow(row: row)
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

/// One observation: the sentence, then the evidence under it.
struct ObservationRow: View {

    let row: AppObservationRow

    private var sentence: String { ObservationText.sentence(row: row) }
    private var caveat: String { ObservationText.caveat(row: row) }

    var body: some View {
        Card(padding: Space.s4) {
            VStack(alignment: .leading, spacing: Space.s2) {
                HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
                    Text(sentence)
                        .font(Type.footnote)
                        .foregroundStyle(Ink.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: Space.s3)
                    // The distance between the two medians, and the list is sorted on it.
                    // Neutral by construction: a bigger gap is not a better one.
                    DeltaChip(Str.observationGapPoints.plural(Fmt.pointsValue(row.gap)))
                }
                HStack(spacing: Space.s2) {
                    CoverageChip(caveat)
                    MethodLine(
                        Str.observationSessionsDidDidNot(
                            Fmt.sessions(row.withN), Fmt.count(row.withoutN)))
                    if row.isPooled {
                        CoverageChip(Str.observationPooledTag.text)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
        .help("\(sentence)\n\(caveat)")
    }
}
