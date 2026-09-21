import PrudenceModels
import PrudenceUI
import SwiftUI

/// The Overview, **variant A**: one column, cards first.
///
/// The founder's choice on 2026-09-20. The three totals set the scale, then each chart takes
/// the full width in turn: the composition of the weeks, what became of them, and where the
/// hours went. Nothing is two-up, because a 900 pt window is one column's worth of room once a
/// chart has an axis and a legend.
///
/// Every number is a sum or a ratio of columns of one `app_*` view, computed in
/// `PrudenceModels/Overview.swift` and only drawn here (M3 rule 8). The bars read
/// `app_usage_by_purpose_day`, the lines read `app_outcomes_by_week`, the strip reads
/// `active_minutes` off the usage view, and the cards read those two plus `app_session_list`
/// and `app_commits_by_day`. Nothing joins anything.
///
/// **Clicking a bar filters the cards to that week** and says so above them, with one button to
/// put it back. The charts themselves keep the whole range: a chart reduced to the bar you
/// clicked has stopped being a comparison.
struct OverviewView: View {

    @ObservedObject var model: WindowModel

    var body: some View {
        VStack(alignment: .leading, spacing: Space.cardGap) {
            if model.selectedWeek != nil { weekFilter }
            cards
            UsageByWeekChart(model: model)
            OutcomesByWeekChart(model: model.outcomes, projects: model.projects)
            ActiveHoursCard(heat: model.heat)
        }
    }

    // MARK: - the week a bar was clicked on

    /// What the cards below are now about, and the one button that puts the range back.
    private var weekFilter: some View {
        HStack(spacing: Space.s3) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .foregroundStyle(Ink.accent)
            Text(verbatim: Str.overviewWeekFilter(
                Fmt.shortDay(model.selectedWeek ?? ""), Fmt.tokens(model.scopedTokens)))
                .font(Type.footnote.monospacedDigit())
                .foregroundStyle(Ink.primary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Space.s3)
            Button(Str.overviewShowAllWeeks.text) {
                withAnimation(Motion.state) { model.selectedWeek = nil }
            }
            .buttonStyle(.prudence)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Ink.accentSoft, in: RoundedRectangle(cornerRadius: Radius.card))
    }

    // MARK: - the three cards

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

/// `StackedBarsChart` over `app_usage_by_purpose_day`, summed into ISO weeks by purpose.
///
/// The week is a category on the x axis rather than a date, which buys two things: the bars are
/// evenly spaced whether or not a week had any work, and the value under the pointer is the
/// exact week rather than a moment that has to be snapped to one.
struct UsageByWeekChart: View {

    @ObservedObject var model: WindowModel

    private var usage: WeeklyUsageModel { model.weeklyUsage }

    private var columns: [StackedBarsChart.Column] {
        usage.weeks.map { week in
            StackedBarsChart.Column(
                key: week.weekStart,
                // `Fmt.shortDay`, not `UsageWeek.label`: the model's own formatter is the
                // engine-facing one and answers in `Locale.current`, which prints an English
                // axis inside a Chinese window.
                label: Fmt.shortDay(week.weekStart),
                slices: week.slices.map {
                    StackedBarsChart.Slice(purpose: $0.purpose, value: $0.tokens)
                }
            )
        }
    }

    var body: some View {
        Panel(
            title: Str.overviewTokensByPurpose.text,
            note: Str.overviewTokensByPurposeNote.text
        ) {
            if usage.isEmpty {
                EmptyState(
                    symbol: "chart.bar",
                    title: Str.overviewNoTokensTitle.text,
                    detail: Str.overviewNoTokensDetail.text
                )
            } else {
                StackedBarsChart(
                    columns: columns,
                    valueText: { Fmt.tokens($0) },
                    hint: Str.chartHintWeeks.text,
                    selection: $model.selectedWeek
                )
            }
        }
    }
}

// MARK: - survival and rework, per week, per project

/// `LinesWithGaps` over `app_outcomes_by_week`: two lines per project, with that week's mean
/// coverage as a wide translucent line beneath them.
///
/// The gaps are the point. A week whose `measured_30d` is zero has not reached its 30-day mark,
/// and drawing it as zero would say the work died; `OutcomeMetric.share` answers nil for such a
/// week and `LinesWithGaps` cuts the line there.
struct OutcomesByWeekChart: View {

    let model: OutcomeChartModel
    /// Every project the window knows about, so a colour does not move when the range picker
    /// changes which projects have an outcome row.
    let projects: [String]

    private var series: [LinesWithGaps.Series] {
        var built: [LinesWithGaps.Series] = []
        for band in model.bands where !band.points.isEmpty {
            built.append(
                LinesWithGaps.Series(
                    id: "coverage|\(band.project)",
                    label: "\(band.project), \(Str.overviewLegendCoverageName.text)",
                    colour: colour(band.project),
                    wide: true,
                    points: points(of: band.points)
                )
            )
        }
        for line in model.series where !line.isEmpty {
            built.append(
                LinesWithGaps.Series(
                    id: line.id,
                    label: "\(line.project), \(metricLabel(line.metric))",
                    colour: colour(line.project),
                    dashed: line.metric == .rework,
                    points: points(of: line.points)
                )
            )
        }
        return built
    }

    /// Every week of the range on the axis, measured or not, with the unmeasured ones carrying
    /// a nil so the line breaks over them.
    private func points(of measured: [OutcomePoint]) -> [LinesWithGaps.Point] {
        let byWeek = Dictionary(measured.map { ($0.weekStart, $0) }) { first, _ in first }
        return model.weeks.map { week in
            guard let point = byWeek[week] else {
                return LinesWithGaps.Point(label: Fmt.shortDay(week), value: nil)
            }
            return LinesWithGaps.Point(
                label: Fmt.shortDay(week),
                value: point.value,
                detail: Str.chartShareOver(Fmt.percent(point.value), Fmt.count(point.over))
            )
        }
    }

    private var labels: [String] { model.weeks.map { Fmt.shortDay($0) } }

    private func colour(_ project: String) -> Color {
        ProjectPalette.colour(project, in: projects.isEmpty ? model.projects : projects)
    }

    private func metricLabel(_ metric: OutcomeMetric) -> String {
        switch metric {
        case .aliveAt30Days: return Str.overviewLegendAliveName.text
        case .rework: return Str.overviewLegendReworkName.text
        }
    }

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
                LinesWithGaps(
                    series: series, labels: labels, hint: Str.chartHintLines.text)
                legend
            }
        }
    }

    private var legend: some View {
        VStack(alignment: .leading, spacing: 6) {
            FlowLayout(spacing: Space.s3, lineSpacing: Space.s1) {
                ForEach(model.projects, id: \.self) { project in
                    HStack(spacing: 5) {
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(colour(project))
                            .frame(width: 9, height: 9)
                        Text(verbatim: project)
                            .font(Type.caption)
                            .foregroundStyle(Ink.secondary)
                            .fixedSize()
                    }
                }
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
}

// MARK: - where the hours went

/// `HeatStrip` over the same usage view's `active_minutes`, one cell per day.
struct ActiveHoursCard: View {

    let heat: ActiveHoursHeat

    var body: some View {
        Panel(title: Str.overviewWhereTime.text, note: Str.overviewWhereTimeNote.text) {
            if heat.isEmpty {
                EmptyState(
                    symbol: "calendar",
                    title: Str.overviewNoHoursTitle.text,
                    detail: Str.overviewNoHoursDetail.text
                )
            } else {
                HeatStrip(
                    weeks: heat.weeks.map { week in
                        HeatStrip.Week(
                            weekStart: week.weekStart,
                            label: Fmt.shortDay(week.weekStart),
                            days: week.days.map {
                                HeatStrip.Day(day: $0.day, minutes: $0.minutes)
                            }
                        )
                    },
                    peakMinutes: heat.peakMinutes
                )
            }
        }
    }
}
