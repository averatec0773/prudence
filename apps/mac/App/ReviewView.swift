import PrudenceModels
import PrudenceUI
import SwiftUI

/// One stored review, section by section.
///
/// The screen prints the texts `reviews/build.py` already wrote and nothing else numeric,
/// exactly as `reviews/render.py` does for the terminal. That is what makes the window and
/// `prudence show --review <id>` incapable of disagreeing: there is one arithmetic, it
/// happened in Python, and both surfaces are layout over the same strings.
///
/// Five section kinds are laid out by hand. Anything else the engine grows later is drawn as
/// the table it brought with it, or as labelled fields when it brought no headers, so a new
/// section appears on this screen the day it appears in the CLI rather than crashing it or
/// being silently dropped.
struct ReviewView: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        if let review = model.review {
            VStack(alignment: .leading, spacing: Space.cardGap) {
                header(review)
                if let reason = model.notReadyReason { notReady(reason) }
                else if let message = model.actionMessage { banner(message) }
                if review.payloadUnreadable {
                    EmptyState(
                        symbol: "doc.questionmark",
                        title: "This review's sections cannot be read",
                        detail:
                            "The stored JSON is not in a shape this build understands. The row "
                            + "above is still true; only its body is unreadable."
                    )
                } else {
                    ForEach(review.sections) { section in
                        SectionView(section: section, coverage: review.coverageText)
                    }
                }
                if let segment = review.segment { SegmentCard(segment: segment) }
                provenance(review)
            }
        } else {
            VStack(alignment: .leading, spacing: Space.cardGap) {
                if let reason = model.notReadyReason { notReady(reason) }
                else if let message = model.actionMessage { banner(message) }
                EmptyState(
                    symbol: "doc.text",
                    title: "No review yet",
                    detail:
                        "A review is written on demand and kept. Press Review now, or run "
                        + "`prudence review` in a terminal; it needs a few new sessions and one "
                        + "commit that has crossed seven days."
                )
            }
        }
    }

    // MARK: - the head of the page

    private func header(_ review: ReviewModel) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(review.headline).font(Type.title3)
                .fixedSize(horizontal: false, vertical: true)
            Text(review.rangeLine).font(Type.footnote).foregroundStyle(Ink.secondary)
            if let outcomeLine = review.outcomeLine {
                Text(outcomeLine).font(Type.caption).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 14) {
                tag("scope", review.scope)
                tag("coverage", review.coverageText)
                    .help(
                        "The mean share of a counted commit's added lines the session itself "
                        + "wrote, over the commits in the outcome window.")
                tag("written", review.createdAt)
                tag("figures", "\(review.numbers.count)")
                    .help("Every number on this page, each one re-derivable from the CLI.")
            }
        }
        .padding(Space.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Surface.plain, in: RoundedRectangle(cornerRadius: Radius.panel))
        .overlay(
            RoundedRectangle(cornerRadius: Radius.panel, style: .continuous)
                .strokeBorder(Surface.hairline, lineWidth: 0.5))
    }

    private func tag(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(Type.caption2).foregroundStyle(Ink.tertiary)
            Text(value).font(Type.figure(13, weight: .regular)).foregroundStyle(Ink.primary)
        }
    }

    private func provenance(_ review: ReviewModel) -> some View {
        Text(
            "Every figure above is computed from your own record: \(review.numbers.count) "
            + "numbers, each re-derivable with `prudence usage`, `prudence outcomes` or "
            + "`prudence observations` over the same range."
        )
        .font(Type.caption)
        .foregroundStyle(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - what the button said

    /// `prudence review` declined, and why. The reason is the engine's own sentence; the
    /// button beside it runs the same command with `--force`, which is the only way past the
    /// readiness rule and is the user's decision to make, not the app's.
    private func notReady(_ reason: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: "clock.badge.exclamationmark").foregroundStyle(Outcome.rework)
            VStack(alignment: .leading, spacing: 4) {
                Text("Not ready for a review yet").font(Type.footnoteStrong)
                Text(reason).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            Button("Write anyway") { model.reviewNow(force: true) }
                .buttonStyle(.prudence)
                .disabled(model.isBusy)
            Button("Dismiss") { model.dismissMessage() }
                .buttonStyle(.prudencePlain)
        }
        .padding(Space.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Outcome.rework.opacity(0.12), in: RoundedRectangle(cornerRadius: Radius.card))
    }

    private func banner(_ message: String) -> some View {
        HStack(spacing: 10) {
            if model.isBusy { ProgressView().controlSize(.small) }
            Text(message).font(Type.footnote).foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 12)
            Button("Dismiss") { model.dismissMessage() }.buttonStyle(.prudencePlain)
        }
        .padding(Space.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Surface.secondary, in: RoundedRectangle(cornerRadius: Radius.card))
    }
}

// MARK: - one section

struct SectionView: View {

    let section: ReviewSection
    /// The review's own coverage, shown on the outcome section's cards.
    let coverage: String

    var body: some View {
        Panel(title: section.heading) {
            switch section.kind {
            case .did: didBody
            case .became: becameBody
            case .observations: observationsBody
            case .compared: comparedBody
            case .suggestions: suggestionsBody
            case .other: genericBody
            }
            notes
        }
    }

    // What you did: the purpose table, and the whole-range figures as cards above it.
    private var didBody: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !cards.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(cards) { number in
                        StatCard(
                            title: number.label,
                            value: number.text,
                            detail: number.coverage.map { "coverage \(Fmt.percent($0))" },
                            help: helpFor(number),
                            compact: true
                        )
                    }
                }
            }
            if section.hasTable {
                StringTable(headers: section.headers, rows: section.rows)
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The four whole-range figures, not the per-purpose ones that are already in the table.
    private var cards: [ReviewNumber] {
        let wanted = ["did.sessions", "did.hours", "did.commits", "did.coverage"]
        return wanted.compactMap { key in section.numbers.first { $0.key == key } }
    }

    // What became of earlier work: one card per figure, each carrying its own coverage.
    private var becameBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if section.hasTable {
                let columns = [GridItem(.adaptive(minimum: 138), spacing: 10)]
                LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                    ForEach(Array(section.rows.enumerated()), id: \.offset) { _, row in
                        StatCard(
                            title: row.first ?? "",
                            value: row.count > 1 ? row[1] : "-",
                            detail: row.count > 2 ? "coverage \(row[2])" : "coverage \(coverage)",
                            help: row.count > 3
                                ? "Method: \(row[3]). The share is printed with the number of "
                                    + "lines it is over."
                                : nil,
                            compact: true
                        )
                    }
                }
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // Observations: the sentence, then the small line of coverage and method under it.
    private var observationsBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            if section.hasTable {
                ForEach(Array(section.rows.enumerated()), id: \.offset) { index, row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.first ?? "").font(Type.footnote)
                            .fixedSize(horizontal: false, vertical: true)
                        if row.count > 1 {
                            Text(row[1]).font(Type.caption).foregroundStyle(Ink.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if index < section.rows.count - 1 { Divider().opacity(0.4) }
                }
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // Compared with the previous period: the table, with the change column picked out.
    private var comparedBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            if section.hasTable {
                VStack(alignment: .leading, spacing: 0) {
                    comparedRow(section.headers, isHeader: true)
                    Divider()
                    ForEach(Array(section.rows.enumerated()), id: \.offset) { index, row in
                        comparedRow(row, isHeader: false)
                        if index < section.rows.count - 1 { Divider().opacity(0.4) }
                    }
                }
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func comparedRow(_ cells: [String], isHeader: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            ForEach(Array(cells.enumerated()), id: \.offset) { index, cell in
                Text(cell)
                    .font(
                        isHeader
                            ? .caption.weight(.semibold)
                            : (index == 3 ? .callout.monospacedDigit().weight(.medium)
                                : .callout.monospacedDigit())
                    )
                    .foregroundStyle(cellStyle(cell, index: index, isHeader: isHeader))
                    .frame(maxWidth: index == 0 ? .infinity : 140, alignment: .leading)
            }
        }
        .padding(.vertical, 5)
    }

    /// **The change column is never coloured by its sign.**
    ///
    /// It used to read green up and red down. That is the one thing principle 3 forbids: more
    /// sessions is not better and less rework is not a score, and a colour that says otherwise
    /// is a grade the engine never computed. The sign stays in the text, where it came from,
    /// and the ink is `DeltaChip.tint` whichever way the number went (`PrudenceUI`'s delta
    /// rule; a test pins it).
    private func cellStyle(_ cell: String, index: Int, isHeader: Bool) -> Color {
        if isHeader { return Ink.secondary }
        return index == 3 ? DeltaChip.tint : Ink.primary
    }

    // Last time's suggestions: one row each, with what moved under it.
    private var suggestionsBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            if section.hasTable {
                ForEach(Array(section.rows.enumerated()), id: \.offset) { index, row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.first ?? "").font(Type.footnote)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(trailing(of: row)).font(Type.caption).foregroundStyle(Ink.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if index < section.rows.count - 1 { Divider().opacity(0.4) }
                }
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// `then 31%, since 19% (9 then, 7 since)`, built from the headers the section brought so
    /// a renamed column still labels itself.
    private func trailing(of row: [String]) -> String {
        zip(section.headers.dropFirst(), row.dropFirst())
            .map { "\($0) \($1)" }
            .joined(separator: ", ")
    }

    // A section this build has never heard of. Drawn, not dropped.
    private var genericBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("A section this version of the app does not lay out; here it is as stored.")
                .font(Type.caption)
                .foregroundStyle(Ink.secondary)
            if section.hasTable {
                StringTable(headers: section.headers, rows: section.rows)
            } else if !section.rows.isEmpty {
                ForEach(Array(section.rows.enumerated()), id: \.offset) { _, row in
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(section.pairs(of: row).enumerated()), id: \.offset) {
                            _, pair in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(pair.0).font(Type.caption).foregroundStyle(Ink.secondary)
                                    .frame(width: 130, alignment: .leading)
                                Text(pair.1).font(Type.footnote)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else if let empty = section.empty {
                Text(empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private var notes: some View {
        if !section.notes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(section.notes.enumerated()), id: \.offset) { _, note in
                    Text(note).font(Type.caption).foregroundStyle(Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.top, 2)
        }
    }

    private func helpFor(_ number: ReviewNumber) -> String {
        guard let coverage = number.coverage else { return number.label }
        return "\(number.label), at coverage \(Fmt.percent(coverage))."
    }
}

// MARK: - the model segment

/// The one part of the page a model wrote, last and under its own credit line.
///
/// Last on purpose: a reader reaches it having already seen every number it may use, and a
/// review that stops before it is still a whole review (M3 rule 10). Every number in it was
/// checked against the review's own numbers list before it was stored.
struct SegmentCard: View {

    let segment: ReviewSegment

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("What this means", systemImage: "text.quote")
                .font(Type.headline)
            Text(segment.text)
                .font(Type.body)
                .fixedSize(horizontal: false, vertical: true)
            Text(credit)
                .font(Type.caption)
                .foregroundStyle(Ink.secondary)
        }
        .padding(Space.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Surface.secondary, in: RoundedRectangle(cornerRadius: Radius.panel))
        .overlay(
            RoundedRectangle(cornerRadius: Radius.panel, style: .continuous)
                .strokeBorder(Ink.accent.opacity(0.35), lineWidth: 1)
        )
    }

    private var credit: String {
        guard let createdAt = segment.createdAt else { return segment.credit + "." }
        return "\(segment.credit), \(createdAt). Every number in it was checked against the "
            + "review's own figures."
    }
}
