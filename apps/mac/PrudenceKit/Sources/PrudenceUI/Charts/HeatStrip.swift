import Charts
import SwiftUI

/// Where the hours went: one cell per day, seven rows, shade by active hours.
///
/// `heatStrip` in `charts.js`, as `RectangleMark`. Seven rows because a week has seven days and
/// the shape of somebody's week is the thing worth seeing; a single-hue scale because this is
/// one quantity and two hues would invite the reader to find a boundary in it.
///
/// **A day nobody worked and a day nobody recorded are the same empty cell here**, and the
/// caption says so: `app_usage_by_purpose_day` has no row for a day with no session, so the
/// strip cannot tell the two apart and does not pretend to. It is the one chart in the app
/// whose empty cell carries no claim.
public struct HeatStrip: View {

    public struct Day: Equatable, Sendable {
        public let day: String
        /// Active minutes, summed over that day's rows. Nil when the day has no row at all.
        public let minutes: Double?

        public init(day: String, minutes: Double?) {
            self.day = day
            self.minutes = minutes
        }
    }

    public struct Week: Equatable, Sendable, Identifiable {
        public let weekStart: String
        public let label: String
        /// Exactly seven, Monday first.
        public let days: [Day]
        public var id: String { weekStart }

        public init(weekStart: String, label: String, days: [Day]) {
            self.weekStart = weekStart
            self.label = label
            self.days = days
        }
    }

    /// Monday first, the same order `Formatting.isoWeekStart` puts a week in.
    public static let weekdayKeys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    let weeks: [Week]
    /// The busiest day in the range, which the scale tops out at.
    let peakMinutes: Double
    var cell: CGFloat

    public init(weeks: [Week], peakMinutes: Double, cell: CGFloat = 15) {
        self.weeks = weeks
        self.peakMinutes = peakMinutes
        self.cell = cell
    }

    private var rowLabels: [String] { Self.weekdayKeys.map { Str.weekday($0) } }

    private var top: Double { max(peakMinutes, 1) }

    private struct Cell: Identifiable {
        let id: String
        let week: String
        let weekday: String
        let minutes: Double
        let measured: Bool
    }

    private var cells: [Cell] {
        weeks.flatMap { week in
            week.days.enumerated().map { index, day in
                Cell(
                    id: day.day,
                    week: week.label,
                    weekday: rowLabels[min(index, rowLabels.count - 1)],
                    minutes: day.minutes ?? 0,
                    measured: (day.minutes ?? 0) > 0
                )
            }
        }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            chart
            legend
        }
    }

    private var chart: some View {
        Chart(cells) { item in
            RectangleMark(
                x: .value(Str.chartPeriod.text, item.week),
                y: .value(Str.chartWeekday.text, item.weekday),
                width: .fixed(cell),
                height: .fixed(cell)
            )
            .foregroundStyle(by: .value(Str.chartHours.text, item.minutes))
            .cornerRadius(3)
        }
        .chartForegroundStyleScale(
            domain: 0...top,
            range: Gradient(colors: [Surface.sunken, Ink.accent])
        )
        // The domain as written, which Charts lays out top to bottom, so Monday is the top row
        // and the week reads the way a calendar does.
        .chartYScale(domain: rowLabels)
        .chartLegend(.hidden)
        .chartXAxis { AxisMarks { AxisValueLabel(orientation: .horizontal) } }
        .chartYAxis {
            AxisMarks(position: .leading) { AxisValueLabel() }
        }
        // Room for seven fixed-height cells plus the gaps between them and the axis under
        // them. Too little and the marks, whose height is fixed, spill over their rows.
        .frame(height: 7 * (cell + 8) + 28)
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    /// The scale, spelled out: nothing at one end and the busiest day at the other.
    private var legend: some View {
        HStack(spacing: 5) {
            Text(verbatim: Fmt.hourPhrase(0))
                .font(Type.caption2.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
            ForEach([0.0, 0.25, 0.5, 0.75, 1.0], id: \.self) { step in
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(Ink.accent.opacity(0.10 + 0.90 * step))
                    .frame(width: 14, height: 9)
            }
            Text(verbatim: Fmt.hourPhrase(top / 60))
                .font(Type.caption2.monospacedDigit())
                .foregroundStyle(Ink.tertiary)
            Spacer(minLength: 0)
        }
    }

    private var accessibilityText: String {
        let parts = weeks.flatMap { week in
            week.days.compactMap { day -> String? in
                guard let minutes = day.minutes, minutes > 0 else { return nil }
                return "\(Fmt.day(day.day)) \(Fmt.hourPhrase(minutes / 60))"
            }
        }
        return parts.isEmpty ? Str.overviewNoHoursTitle.text : parts.joined(separator: "; ")
    }
}
