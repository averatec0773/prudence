import PrudenceModels
import SwiftUI

/// The observation rows, biggest gap first.
///
/// One row is one sentence and the line that has to travel with it: the coverage, and how
/// many of the commits behind it were established as fact rather than inferred. Principle 3
/// puts them in the same block, never a section away, and nothing on this screen is a share
/// without the two counts it was taken over.
///
/// The sentence is read from `app_observation.sentence`. At contract 1 the app restated the
/// phrase table from `store/observations.py` in Swift and a test pinned it word for word;
/// contract 2 stores the prose the CLI prints, so the restatement is gone and the two
/// surfaces cannot word the same finding differently.
struct ObservationsView: View {

    @ObservedObject var model: WindowModel

    private var rows: [ObservationModel] { model.observations }

    var body: some View {
        if rows.isEmpty {
            EmptyStateView(
                symbol: "lightbulb",
                title: emptyTitle,
                detail: emptyDetail
            )
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Text(scopeLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(rows) { row in
                    ObservationRow(observation: row)
                }
                Text(
                    "An observation splits your own sessions in two at one threshold and takes "
                    + "each side's median. These are descriptions of what happened, not advice."
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var scopeLine: String {
        model.project == nil
            ? "Pooled rows only: these are computed across your projects, for behaviours no "
                + "single project had the sessions to answer, and are not a finding about any "
                + "one of them."
            : "Rows computed from this project's own sessions alone."
    }

    private var emptyTitle: String {
        model.project == nil ? "No pooled observations" : "No observations for this project"
    }

    private var emptyDetail: String {
        model.project == nil
            ? "Nothing yet holds across your projects. Choose a project above to see the rows "
                + "computed from its own sessions."
            : "No behaviour here clears both floors: at least five sessions on each side of the "
                + "split, and enough distance between the two medians to be worth printing."
    }
}

/// One observation: the sentence, then the evidence under it.
struct ObservationRow: View {

    let observation: ObservationModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(observation.sentence)
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 12)
                Text(Formatting.percent(observation.gap))
                    .font(.callout.monospacedDigit().weight(.medium))
                    .foregroundStyle(.secondary)
                    .help("The distance between the two medians. The list is sorted on it.")
            }
            HStack(spacing: 10) {
                Text(observation.caveat)
                Text("|").foregroundStyle(.tertiary)
                Text("\(observation.withN) sessions did, \(observation.withoutN) did not")
                if observation.isPooled {
                    Text("|").foregroundStyle(.tertiary)
                    Text("across your projects")
                }
                Spacer(minLength: 0)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 10))
        .help(
            "\(observation.sentence)\n\(observation.caveat)"
        )
    }
}
