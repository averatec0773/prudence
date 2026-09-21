import Charts
import PrudenceModels
import PrudenceUI
import SwiftUI

/// The Overview: three cards, then two charts.
///
/// Every number is a sum or a ratio of columns of one `app_*` view, computed in
/// `PrudenceModels/Overview.swift` and only drawn here. Swift Charts throughout, one chart per
/// view, which is the rule task 8 set: the bars read `app_usage_by_purpose_day`, the lines
/// read `app_outcomes_by_week`, the cards read those two plus `app_session_list` and
/// `app_commits_by_day`. Nothing joins anything.
///
/// Batch 1 gave this screen the tokens: the same palette, spacing, card and type scale as the
/// popover, so the two do not look like two apps. The charts themselves are batch 2 work
/// (`apps/mac/DESIGN.md`, "What batch 2 still owes").
struct OverviewView: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        VStack(alignment: .leading, spacing: Space.cardGap) {
            cards
            UsageByWeekChart(model: model.weeklyUsage, range: model.range)
            OutcomesByWeekChart(model: model.outcomes)
        }
    }

    private var cards: some View {
        let cards = model.cards
        let scope = model.project ?? Str.scopeAllProjects.text
        return HStack(alignment: .top, spacing: Space.cardGap) {
            StatCard(
                title: Str.overviewSessionsInRange.text,
                value: Fmt.count(cards.sessions),
                detail: cards.edits.map { Fmt.edits($0) } ?? Str.overviewEditsNotMeasured.text,
                help: "Rows of app_session_list started in this range, \(scope)."
            )
            StatCard(
                title: Str.overviewActiveHours.text,
                value: Fmt.hours(cards.activeMinutes / 60),
                detail: Str.overviewSittingsNote.text,
                help:
                    "The sum of active_minutes on app_usage_by_purpose_day over this range, the "
                    + "same way `prudence usage` counts them."
            )
            StatCard(
                title: Str.overviewCommitsInRange.text,
                value: Fmt.count(cards.commits),
                detail: Str.overviewFactInferred(
                    Fmt.count(cards.commitsFact), Fmt.count(cards.commitsInferred)),
                help:
                    "From app_commits_by_day, where a commit is counted once at its best "
                    + "confidence. Uncertain commits are reported by the engine and never "
                    + "folded into these two."
            )
        }
    }
}

// MARK: - tokens by purpose, per ISO week

/// Stacked bars, one per ISO week, split by purpose.
///
/// The week is a category on the x axis rather than a date, which buys two things: the bars
/// are evenly spaced whether or not a week had any work, and `chartXSelection` hands back the
/// exact week under the pointer instead of a moment that has to be snapped to one. On macOS
/// that selection is driven by hover, which is the right gesture for a desktop chart.
struct UsageByWeekChart: View {

    let model: WeeklyUsageModel
    let range: ChartRange

    @State private var hovered: String?

    private var scale: (domain: [String], range: [Color]) {
        Purpose.scale(for: model.purposes)
    }

    private var selected: UsageWeek? {
        guard let hovered else { return nil }
        return model.weeks.first { $0.label == hovered }
    }

    var body: some View {
        Panel(
            title: Str.overviewTokensByPurpose.text,
            note: Str.overviewTokensByPurposeNote.text
        ) {
            if model.isEmpty {
                EmptyState(
                    symbol: "chart.bar",
                    title: Str.overviewNoTokensTitle.text,
                    detail: Str.overviewNoTokensDetail.text
                )
            } else {
                chart
                PurposeLegend(purposes: scale.domain)
            }
        }
    }

    private var chart: some View {
        Chart {
            ForEach(model.weeks) { week in
                ForEach(week.slices) { slice in
                    BarMark(
                        x: .value("Week", week.label),
                        y: .value("Tokens", slice.tokens)
                    )
                    .foregroundStyle(by: .value("Purpose", slice.purpose))
                    .opacity(hovered == nil || hovered == week.label ? 1 : 0.45)
                }
            }
        }
        .chartForegroundStyleScale(domain: scale.domain, range: scale.range)
        .chartLegend(.hidden)
        .chartXSelection(value: $hovered)
        .chartYAxis {
            AxisMarks { value in
                AxisGridLine()
                AxisValueLabel {
                    if let tokens = value.as(Int.self) {
                        Text(Fmt.tokens(tokens)).font(Type.caption2.monospacedDigit())
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel(orientation: .horizontal) } }
        .frame(height: 186)
        .overlay(alignment: .topTrailing) { hoverCard }
        .accessibilityLabel("Tokens by purpose for each week in the chosen range")
    }

    /// What the hovered week holds, per purpose. The totals, not a share: a share of a week
    /// would need a denominator beside it and the whole point of the card is the raw numbers.
    @ViewBuilder
    private var hoverCard: some View {
        if let selected {
            Card(padding: Space.s3, radius: Radius.control) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Str.overviewWeekOf(Fmt.shortDay(selected.label)))
                        .font(Type.captionStrong)
                        .foregroundStyle(Ink.primary)
                    ForEach(selected.slices) { slice in
                        HStack(spacing: 6) {
                            Circle()
                                .fill(Purpose.colour(slice.purpose))
                                .frame(width: 7, height: 7)
                            Text(Fmt.purpose(slice.purpose)).font(Type.caption)
                            Spacer(minLength: 10)
                            Text(Fmt.tokens(slice.tokens))
                                .font(Type.figure(12, weight: .regular))
                        }
                    }
                    Divider()
                    HStack(spacing: 6) {
                        Text(.overviewAllPurposes).font(Type.captionStrong)
                        Spacer(minLength: 10)
                        Text(Fmt.tokens(selected.total)).font(Type.figure(12, weight: .semibold))
                    }
                }
                .foregroundStyle(Ink.primary)
            }
            .frame(minWidth: 170)
            .fixedSize()
            .padding(6)
        }
    }
}

// MARK: - survival and rework, per week, per project

/// Two lines per project over the weeks, with the coverage as a translucent band beneath.
///
/// The gaps are the point. A week whose `measured_30d` is zero has not reached its 30-day
/// mark, and drawing it as zero would say the work died; `OutcomeChartModel` cuts each
/// project's line into runs of measured weeks and each run is its own series, so Swift Charts
/// cannot join across the hole.
struct OutcomesByWeekChart: View {

    let model: OutcomeChartModel

    @State private var hovered: String?

    var body: some View {
        Panel(
            title: Str.overviewWhatBecame.text,
            note: Str.overviewWhatBecameNote.text
        ) {
            if model.isEmpty {
                EmptyState(
                    symbol: "chart.xyaxis.line",
                    title: Str.overviewNoOutcomesTitle.text,
                    detail: Str.overviewNoOutcomesDetail.text
                )
            } else {
                chart
                legend
            }
        }
    }

    private var chart: some View {
        Chart {
            // The coverage, as a faint second line rather than a filled band. A band from
            // zero to the coverage is a lot of ink at the one height the eye should be
            // reading the two shares at, and with more than one project the overlapping
            // fills stop being readable as either.
            ForEach(model.bands) { band in
                ForEach(band.points) { point in
                    LineMark(
                        x: .value("Week", point.label),
                        y: .value("Coverage", point.value),
                        series: .value("Series", "coverage|\(band.project)")
                    )
                    .foregroundStyle(projectColour(band.project).opacity(0.30))
                    .lineStyle(StrokeStyle(lineWidth: 6, lineCap: .round))
                }
            }
            ForEach(model.series) { series in
                ForEach(Array(series.segments.enumerated()), id: \.offset) { index, segment in
                    ForEach(segment) { point in
                        LineMark(
                            x: .value("Week", point.label),
                            y: .value("Share", point.value),
                            series: .value("Series", "\(series.id)#\(index)")
                        )
                        .foregroundStyle(projectColour(series.project))
                        .lineStyle(
                            StrokeStyle(
                                lineWidth: 2,
                                dash: series.metric == .rework ? [4, 3] : []
                            )
                        )
                        PointMark(
                            x: .value("Week", point.label),
                            y: .value("Share", point.value)
                        )
                        .foregroundStyle(projectColour(series.project))
                        .symbolSize(series.metric == .rework ? 26 : 40)
                    }
                }
            }
        }
        .chartYScale(domain: 0...1)
        .chartYAxis {
            AxisMarks { value in
                AxisGridLine()
                AxisValueLabel {
                    if let share = value.as(Double.self) {
                        Text(Fmt.percent(share)).font(Type.caption2.monospacedDigit())
                    }
                }
            }
        }
        .chartXSelection(value: $hovered)
        .frame(height: 186)
        .overlay(alignment: .topTrailing) { hoverCard }
        .accessibilityLabel("Survival at thirty days and rework share for each week")
    }

    /// Every share with the number it is over, which principle 3 requires and which a
    /// percentage alone would break.
    @ViewBuilder
    private var hoverCard: some View {
        if let hovered, !rows(at: hovered).isEmpty {
            Card(padding: Space.s3, radius: Radius.control) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Str.overviewWeekOf(Fmt.shortDay(hovered)))
                        .font(Type.captionStrong)
                    ForEach(rows(at: hovered), id: \.0) { label, point in
                        HStack(spacing: 6) {
                            Text(label).font(Type.caption)
                            Spacer(minLength: 12)
                            Text(point.withDenominator).font(Type.figure(12, weight: .regular))
                        }
                    }
                }
                .foregroundStyle(Ink.primary)
            }
            .frame(minWidth: 210)
            .fixedSize()
            .padding(6)
        }
    }

    private func rows(at label: String) -> [(String, OutcomePoint)] {
        model.series.compactMap { series in
            guard let point = series.points.first(where: { $0.label == label }) else { return nil }
            return ("\(series.project), \(series.metric.label)", point)
        }
    }

    private var legend: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: Space.s3) {
                ForEach(model.projects, id: \.self) { project in
                    HStack(spacing: 5) {
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(projectColour(project))
                            .frame(width: 9, height: 9)
                        Text(project).font(Type.caption).foregroundStyle(Ink.secondary)
                    }
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: Space.s3) {
                Text(.overviewLegendAlive)
                Text(.overviewLegendRework)
                Text(.overviewLegendCoverage)
                Spacer(minLength: 0)
            }
            .font(Type.caption)
            .foregroundStyle(Ink.tertiary)
        }
    }

    /// Stable per project, so two screenshots of different ranges agree about which line is
    /// which. Index into a fixed palette by the project's place in the sorted list.
    ///
    /// Not the purpose palette: these are projects, and a project drawn in the colour of
    /// "development" would read as a purpose. Batch 2 replaces this with a project scale of
    /// its own.
    private func projectColour(_ project: String) -> Color {
        let palette: [Color] = [
            Ink.accent, Outcome.alive, Purpose.colour("debugging"),
            Purpose.colour("conversation"), Purpose.colour("research"),
            Purpose.colour("mixed"), Outcome.rework,
        ]
        guard let index = model.projects.firstIndex(of: project) else {
            return Purpose.colour("unknown")
        }
        return palette[index % palette.count]
    }
}
