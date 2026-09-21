import PrudenceModels
import PrudenceUI
import SwiftUI

/// One stored review, section by section: **variant B**, charts with their tables open under
/// them.
///
/// The founder's choice on 2026-09-20, and the reason is principle 2: a review has to be
/// checkable. The chart carries the shape and the table under it lets a figure be held beside
/// `prudence usage` without a disclosure having to be opened first. Nothing is hidden behind a
/// triangle and nothing is redrawn.
///
/// The screen prints the texts `reviews/build.py` already wrote and nothing else numeric,
/// exactly as `reviews/render.py` does for the terminal, which is what makes the window and
/// `prudence show --review <id>` incapable of disagreeing. Where a chart needs a magnitude
/// rather than a printed cell it takes `ReviewNumber.value`, the unrounded figure the engine
/// stored beside the text for exactly that purpose (`PrudenceModels/ReviewCharts.swift`).
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
                        title: Str.reviewUnreadableTitle.text,
                        detail: Str.reviewUnreadableDetail.text
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
                    title: Str.reviewEmptyTitle.text,
                    detail: Str.reviewEmptyDetail.text
                )
            }
        }
    }

    // MARK: - the head of the page

    /// The headline, the two ranges, and the four things every figure below is qualified by.
    ///
    /// `coverage` is read off the row rather than off a section: contract 2 stores it on
    /// `app_review`, which is what batch 1 added and what lets this tag exist for a review
    /// whose outcome window had not yet matured. `written` is localised through `Locale`, both
    /// the date and how long ago it was.
    private func header(_ review: ReviewModel) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(verbatim: review.headline).font(Type.title3)
                .fixedSize(horizontal: false, vertical: true)
            Text(verbatim: review.rangeLine).font(Type.footnote).foregroundStyle(Ink.secondary)
            if let outcomeLine = review.outcomeLine {
                Text(verbatim: outcomeLine).font(Type.caption).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(alignment: .top, spacing: 18) {
                tag(Str.reviewTagScope.text, ReviewText.scope(review.project))
                tag(Str.reviewTagCoverage.text, review.coverageText)
                    .help(Str.reviewCoverageHelp.text)
                tag(Str.reviewTagWritten.text, ReviewText.written(review.createdAt, now: model.now))
                tag(Str.reviewTagFigures.text, Fmt.count(review.numbers.count))
                    .help(Str.reviewFiguresHelp.text)
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
            Text(verbatim: label).font(Type.caption2).foregroundStyle(Ink.tertiary)
            Text(verbatim: value).font(Type.figure(13, weight: .regular))
                .foregroundStyle(Ink.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func provenance(_ review: ReviewModel) -> some View {
        Text(verbatim: Str.reviewProvenance(Fmt.count(review.numbers.count)))
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
                Text(.reviewNotReadyTitle).font(Type.footnoteStrong)
                Text(verbatim: reason).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            Button(Str.reviewWriteAnyway.text) { model.reviewNow(force: true) }
                .buttonStyle(.prudence)
                .disabled(model.isBusy)
            Button(Str.commonDismiss.text) { model.dismissMessage() }
                .buttonStyle(.prudencePlain)
        }
        .padding(Space.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Outcome.rework.opacity(0.12), in: RoundedRectangle(cornerRadius: Radius.card))
    }

    private func banner(_ message: String) -> some View {
        HStack(spacing: 10) {
            if model.isBusy { ProgressView().controlSize(.small) }
            Text(verbatim: message).font(Type.footnote).foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 12)
            Button(Str.commonDismiss.text) { model.dismissMessage() }
                .buttonStyle(.prudencePlain)
        }
        .padding(Space.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Surface.secondary, in: RoundedRectangle(cornerRadius: Radius.card))
    }
}

// MARK: - one section

struct SectionView: View {

    let section: ReviewSection
    /// The review's own coverage, shown where a section's rows do not carry one.
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

    // MARK: - what you did

    /// Four cards, a donut of the tokens by purpose, and the engine's own table under it.
    private var didBody: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !cards.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(cards) { number in
                        StatCard(
                            title: cardTitle(number),
                            value: number.text,
                            detail: number.coverage.map { Str.chartCoverageIs(Fmt.percent($0)) },
                            help: helpFor(number),
                            compact: true
                        )
                    }
                }
            }
            if !slices.isEmpty {
                DonutChart(
                    // The engine's own text beside each share: this page prints `713938k`
                    // in the table under the ring and must not print `713.9M` in the ring's
                    // legend for the same figure.
                    slices: slices.map {
                        DonutChart.Slice(
                            purpose: $0.purpose, value: $0.tokens, text: $0.tokensText)
                    },
                    centreValue: sessionsText,
                    centreLabel: Str.chartSessionsShort.text,
                    valueText: { Fmt.tokens(Int($0.rounded())) }
                )
            }
            if section.hasTable {
                StringTable(headers: section.headers, rows: section.rows)
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var slices: [ReviewCharts.PurposeSlice] { ReviewCharts.purposeSlices(of: section) }

    /// The sessions figure the donut's middle is over, as the engine printed it, or nil.
    ///
    /// `did.sessions` first; failing that, the sessions cell of the engine's own total row,
    /// which is the row `purposeSlices` leaves out because it has no token number of its own.
    /// Failing both, the middle of the ring stays empty: a review written by an engine that
    /// stored no session count has no figure here, and `0` would be a number nobody measured.
    private var sessionsText: String? {
        if let stored = section.numbers.first(where: { $0.key == "did.sessions" }) {
            return stored.text
        }
        let purposes = Set(slices.map(\.purpose))
        guard
            let total = section.rows.first(where: { row in
                guard let label = row.first else { return false }
                return !purposes.contains(label) && row.count > 1
            })
        else { return nil }
        return total[1]
    }

    /// The four whole-range figures, not the per-purpose ones that are already in the table.
    private var cards: [ReviewNumber] {
        let wanted = ["did.sessions", "did.hours", "did.commits", "did.coverage"]
        return wanted.compactMap { key in section.numbers.first { $0.key == key } }
    }

    /// The four cards' own headings, in the reader's language. The engine's `label` stays as
    /// the detail under the figure, because it is the sentence that says what was counted.
    private func cardTitle(_ number: ReviewNumber) -> String {
        switch number.key {
        case "did.sessions": return Str.overviewSessionsInRange.text
        case "did.hours": return Str.overviewActiveHours.text
        case "did.commits": return Str.overviewCommitsInRange.text
        // Sentence case, like the other three. The header's own `coverage` tag is lower case
        // because it is a tag; a card heading is a heading.
        case "did.coverage": return Str.reviewCardCoverage.text
        default: return number.label
        }
    }

    // MARK: - what became of earlier work

    /// One `ShareWithCoverageBar` per share, with the engine's own table under them.
    ///
    /// A row that is a count rather than a share ("lines followed") gets no bar: a bar needs a
    /// denominator to be a fraction of, and that row is the denominator.
    private var becameBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if section.hasTable {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(shares) { row in
                        ShareWithCoverageBar(
                            label: row.label,
                            value: row.value ?? 0,
                            coverage: row.coverage,
                            valueText: row.valueText,
                            denominator: row.coverageText.isEmpty
                                ? nil : Str.chartCoverageIs(row.coverageText),
                            tint: row.isRework ? Outcome.rework : Outcome.alive
                        )
                    }
                }
                Text(.reviewCoverageUnderlay)
                    .font(Type.caption)
                    .foregroundStyle(Ink.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
                StringTable(headers: section.headers, rows: section.rows)
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(verbatim: Str.reviewCoverageOfRow(coverage))
                    .font(Type.caption).foregroundStyle(Ink.tertiary)
            }
        }
    }

    private var shares: [ReviewCharts.ShareRow] {
        ReviewCharts.shareRows(of: section).filter(\.isShare)
    }

    // MARK: - observations

    /// The sentence, the two medians as paired bars, and the coverage and method line.
    ///
    /// The bars carry `n` from contract 3 on, read off this review's own `observation.*.with`
    /// and `.without` numbers rather than off the live observation rows, which would have put
    /// this range's prose beside another range's counts. A review an older engine wrote has no
    /// such numbers and the bars print the share alone, as they did before.
    private var observationsBody: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !pairs.isEmpty {
                ForEach(pairs) { pair in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(verbatim: pair.sentence)
                            .font(Type.footnote)
                            .foregroundStyle(Ink.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        PairedBarsChart(
                            with: .init(
                                label: Str.observationSideDid.text, value: pair.withValue,
                                n: pair.withN),
                            without: .init(
                                label: Str.observationSideDidNot.text, value: pair.withoutValue,
                                n: pair.withoutN),
                            tint: pair.isRework ? Outcome.rework : Outcome.alive,
                            labelWidth: 130
                        )
                        MethodLine(pair.caveat)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            if section.hasTable {
                StringTable(headers: section.headers, rows: section.rows)
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var pairs: [ReviewCharts.ObservationPair] {
        ReviewCharts.observationPairs(of: section)
    }

    // MARK: - compared with the previous period

    /// One `CompareCard` per figure, and the engine's own table under them.
    private var comparedBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            if section.hasTable {
                let columns = [GridItem(.adaptive(minimum: 196), spacing: 12)]
                LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                    ForEach(ReviewCharts.compareRows(of: section)) { row in
                        CompareCard(
                            title: row.label,
                            value: row.now,
                            previous: row.previous,
                            change: row.change,
                            // Contract 3's stored figures where the engine wrote them; the
                            // card falls back to reading the printed cell where it did not.
                            nowValue: row.value,
                            previousValue: row.previousValue
                        )
                    }
                }
                StringTable(headers: section.headers, rows: section.rows)
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - last time's suggestions

    /// One row each, with what moved under it.
    private var suggestionsBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            if section.hasTable {
                ForEach(Array(section.rows.enumerated()), id: \.offset) { index, row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(verbatim: row.first ?? "").font(Type.footnote)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(verbatim: trailing(of: row)).font(Type.caption)
                            .foregroundStyle(Ink.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    if index < section.rows.count - 1 { Divider().opacity(0.4) }
                }
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
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
            Text(.reviewUnknownSection)
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
                                Text(verbatim: pair.0).font(Type.caption)
                                    .foregroundStyle(Ink.secondary)
                                    .frame(width: 130, alignment: .leading)
                                Text(verbatim: pair.1).font(Type.footnote)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else if let empty = section.empty {
                Text(verbatim: empty).font(Type.footnote).foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private var notes: some View {
        if !section.notes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(section.notes.enumerated()), id: \.offset) { _, note in
                    Text(verbatim: note).font(Type.caption).foregroundStyle(Ink.secondary)
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
///
/// The credit names the model, the day, and **the language the segment is in**, which
/// `ReviewText.segmentLanguage` reads off the prose because `app_review` has no column for it.
struct SegmentCard: View {

    let segment: ReviewSegment

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(Str.reviewWhatThisMeans.text, systemImage: "text.quote")
                .font(Type.headline)
            Text(verbatim: segment.text)
                .font(Type.body)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Space.s2) {
                Text(verbatim: ReviewText.credit(model: segment.model))
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                if let createdAt = segment.createdAt {
                    Text(verbatim: Fmt.day(createdAt))
                        .font(Type.caption.monospacedDigit())
                        .foregroundStyle(Ink.tertiary)
                }
                CoverageChip(
                    ReviewText.segmentLanguage(
                        stored: segment.language, of: segment.text
                    ).label)
                Spacer(minLength: 0)
            }
            Text(.reviewSegmentChecked)
                .font(Type.caption2)
                .foregroundStyle(Ink.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(Space.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Surface.secondary, in: RoundedRectangle(cornerRadius: Radius.panel))
        .overlay(
            RoundedRectangle(cornerRadius: Radius.panel, style: .continuous)
                .strokeBorder(Ink.accent.opacity(0.35), lineWidth: 1)
        )
    }
}
