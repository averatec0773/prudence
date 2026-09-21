import Charts
import PrudenceModels
import SwiftUI

/// The Overview: three cards, then two charts.
///
/// Every number is a sum or a ratio of columns of one `app_*` view, computed in
/// `PrudenceModels/Overview.swift` and only drawn here. Swift Charts throughout, one chart per
/// view, which is the rule task 8 set: the bars read `app_usage_by_purpose_day`, the lines
/// read `app_outcomes_by_week`, the cards read those two plus `app_session_list` and
/// `app_commits_by_day`. Nothing joins anything.
struct OverviewView: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            cards
            UsageByWeekChart(model: model.weeklyUsage, range: model.range)
            OutcomesByWeekChart(model: model.outcomes)
        }
    }

    private var cards: some View {
        let cards = model.cards
        let scope = model.project ?? ProjectFilter.allProjectsLabel
        return HStack(alignment: .top, spacing: 14) {
            SummaryCard(
                title: "Sessions in range",
                value: "\(cards.sessions)",
                detail: cards.edits.map { "\($0) edits" } ?? "edits not measured",
                help: "Rows of app_session_list started in this range, \(scope)."
            )
            SummaryCard(
                title: "Active hours",
                value: cards.activeHoursText,
                detail: "sum of each session's sittings",
                help:
                    "The sum of active_minutes on app_usage_by_purpose_day over this range, the "
                    + "same way `prudence usage` counts them."
            )
            SummaryCard(
                title: "Commits in range",
                value: "\(cards.commits)",
                detail: cards.methodText,
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
        PurposeColour.scale(for: model.purposes)
    }

    private var selected: UsageWeek? {
        guard let hovered else { return nil }
        return model.weeks.first { $0.label == hovered }
    }

    var body: some View {
        Panel(
            title: "Tokens by purpose, per week",
            note:
                "Summed from app_usage_by_purpose_day into the ISO week each local day falls in. "
                + "A session's tokens are counted on the day its first record was written."
        ) {
            if model.isEmpty {
                EmptyStateView(
                    symbol: "chart.bar",
                    title: "No tokens in this range",
                    detail:
                        "Nothing here measured any tokens. A Claude Code version that wrote no "
                        + "usage fields is not zero tokens; it is no measurement at all."
                )
            } else {
                chart
                legend
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
                        Text(Formatting.tokens(tokens))
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
            VStack(alignment: .leading, spacing: 3) {
                Text("Week of \(selected.label)").font(.caption.weight(.semibold))
                ForEach(selected.slices) { slice in
                    HStack(spacing: 6) {
                        Circle().fill(PurposeColour.colour(slice.purpose)).frame(width: 7, height: 7)
                        Text(slice.purpose).font(.caption)
                        Spacer(minLength: 10)
                        Text(Formatting.tokens(slice.tokens)).font(.caption.monospacedDigit())
                    }
                }
                Divider()
                HStack(spacing: 6) {
                    Text("all purposes").font(.caption.weight(.semibold))
                    Spacer(minLength: 10)
                    Text(Formatting.tokens(selected.total))
                        .font(.caption.monospacedDigit().weight(.semibold))
                }
            }
            .padding(9)
            .frame(minWidth: 170)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            .padding(6)
        }
    }

    /// Built by hand. Swift Charts' own legend has long-standing alignment and wrapping
    /// complaints (research note, section 3), and a legend that reflows differently between
    /// light and dark would make the two screenshots hard to compare.
    private var legend: some View {
        HStack(spacing: 14) {
            ForEach(scale.domain, id: \.self) { purpose in
                HStack(spacing: 5) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(PurposeColour.colour(purpose))
                        .frame(width: 10, height: 10)
                    Text(purpose).font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
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
            title: "What became of each week's work",
            note:
                "alive_30d / measured_30d and reworked / lines, both from app_outcomes_by_week. "
                + "A week whose 30-day mark has not arrived is a gap, never a zero. The pale "
                + "wide line is that week's mean coverage: the share of a counted commit's "
                + "added lines the session itself wrote."
        ) {
            if model.isEmpty {
                EmptyStateView(
                    symbol: "chart.xyaxis.line",
                    title: "No outcomes to follow yet",
                    detail:
                        "No commit in this range is credited with a line that could be followed. "
                        + "A repository where other people commit has its outcomes withheld "
                        + "rather than guessed."
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
                    if let share = value.as(Double.self) { Text(Formatting.percent(share)) }
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
            VStack(alignment: .leading, spacing: 3) {
                Text("Week of \(hovered)").font(.caption.weight(.semibold))
                ForEach(rows(at: hovered), id: \.0) { label, point in
                    HStack(spacing: 6) {
                        Text(label).font(.caption)
                        Spacer(minLength: 12)
                        Text(point.withDenominator).font(.caption.monospacedDigit())
                    }
                }
            }
            .padding(9)
            .frame(minWidth: 210)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
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
            HStack(spacing: 14) {
                ForEach(model.projects, id: \.self) { project in
                    HStack(spacing: 5) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(projectColour(project))
                            .frame(width: 10, height: 10)
                        Text(project).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 14) {
                Text("solid: alive at 30 days")
                Text("dashed: reworked later")
                Text("pale wide: coverage")
                Spacer(minLength: 0)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }

    /// Stable per project, so two screenshots of different ranges agree about which line is
    /// which. Index into a fixed palette by the project's place in the sorted list.
    private func projectColour(_ project: String) -> Color {
        let palette: [Color] = [.blue, .green, .orange, .pink, .teal, .purple, .brown]
        guard let index = model.projects.firstIndex(of: project) else { return .gray }
        return palette[index % palette.count]
    }
}
