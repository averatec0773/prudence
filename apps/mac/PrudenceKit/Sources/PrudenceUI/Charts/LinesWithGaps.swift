import Charts
import SwiftUI

/// Over time, with holes in it: lines that stop at a gap and start again after it.
///
/// `lines` in `charts.js`. The whole point of this chart is the thing it refuses to draw. A
/// week whose 30-day mark has not arrived has no measurement, and a line drawn through it would
/// say the work died. So a point carries an **optional** value, and a nil cuts the line.
///
/// Swift Charts joins consecutive marks of the same series and has no conformance that lets a
/// `LineMark` take a nil y (checked against the macOS 27 SDK, not against memory:
/// `LineMark.init(x:y:)` wants two `Plottable`s and `Optional` is not one). So the break is
/// made where the framework does allow it: `runs(of:)` cuts each series at every nil and hands
/// each run its own `series:` value, which is a different line as far as Charts is concerned
/// and therefore cannot be joined to the one before the hole. The optional is the input; the
/// runs are the mechanism.
///
/// A coverage series is the same shape drawn as one wide translucent line behind the rest, so
/// the reader can see how much of the week the shares above it speak for.
public struct LinesWithGaps: View {

    public struct Point: Equatable, Sendable {
        /// The axis label, which is also this point's identity along x.
        public let label: String
        /// nil is "not measured", which is a hole and never a zero.
        public let value: Double?
        /// What the readout says about this point, already carrying its denominator.
        public let detail: String?

        public init(label: String, value: Double?, detail: String? = nil) {
            self.label = label
            self.value = value
            self.detail = detail
        }
    }

    public struct Series: Equatable, Sendable, Identifiable {
        public let id: String
        public let label: String
        public let colour: Color
        /// Rework is the same colour as survival in the project's own hue and differs by line
        /// style, because the two are two readings of the same lines (NOTES.md).
        public let dashed: Bool
        /// The coverage band: one wide translucent line, no points, drawn first.
        public let wide: Bool
        public let points: [Point]

        public init(
            id: String, label: String, colour: Color, dashed: Bool = false, wide: Bool = false,
            points: [Point]
        ) {
            self.id = id
            self.label = label
            self.colour = colour
            self.dashed = dashed
            self.wide = wide
            self.points = points
        }
    }

    /// Consecutive measured points, each run on its own. A nil ends a run and starts the next.
    ///
    /// A run of one point is kept: Charts draws nothing for a single `LineMark`, which is why
    /// the caller also gets a `PointMark` per point, so one measured week between two holes is
    /// a dot rather than nothing at all.
    public static func runs(of points: [Point]) -> [[Point]] {
        var runs: [[Point]] = []
        var current: [Point] = []
        for point in points {
            guard point.value != nil else {
                if !current.isEmpty { runs.append(current) }
                current = []
                continue
            }
            current.append(point)
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }

    /// How many holes a series has: one fewer than its runs, and never below zero.
    public static func gaps(in points: [Point]) -> Int {
        max(0, runs(of: points).count - 1)
    }

    let series: [Series]
    /// Every label on the axis, in order, including the ones nothing measured, so the axis
    /// spans the range rather than only the weeks that happen to have a number.
    let labels: [String]
    let hint: String
    var height: CGFloat

    @State private var hovered: String?

    public init(
        series: [Series], labels: [String], hint: String, height: CGFloat = 196
    ) {
        self.series = series
        self.labels = labels
        self.hint = hint
        self.height = height
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            chart
            readout
        }
    }

    private var chart: some View {
        Chart {
            // The coverage bands first, so the shares are drawn over them and stay readable.
            ForEach(series.filter(\.wide)) { line in
                marks(for: line, width: 6, opacity: 0.30, withPoints: false)
            }
            ForEach(series.filter { !$0.wide }) { line in
                marks(for: line, width: 2, opacity: 1, withPoints: true)
            }
        }
        .chartXScale(domain: labels)
        .chartYScale(domain: 0...1)
        .chartYAxis {
            AxisMarks { value in
                AxisGridLine().foregroundStyle(Surface.grid)
                AxisValueLabel {
                    if let share = value.as(Double.self) {
                        Text(verbatim: Fmt.percent(share))
                            .font(Type.caption2.monospacedDigit())
                            .foregroundStyle(Ink.tertiary)
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel(orientation: .horizontal) } }
        .chartLegend(.hidden)
        .frame(height: height)
        .chartOverlay { proxy in interaction(proxy) }
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    @ChartContentBuilder
    private func marks(
        for line: Series, width: CGFloat, opacity: Double, withPoints: Bool
    ) -> some ChartContent {
        ForEach(Array(Self.runs(of: line.points).enumerated()), id: \.offset) { index, run in
            ForEach(Array(run.enumerated()), id: \.offset) { _, point in
                LineMark(
                    x: .value(Str.chartPeriod.text, point.label),
                    y: .value(Str.chartValue.text, point.value ?? 0),
                    // One run, one series: Charts will not join two of these across the hole
                    // between them, which is the entire behaviour this chart exists for.
                    series: .value(Str.chartSeries.text, "\(line.id)#\(index)")
                )
                .foregroundStyle(line.colour.opacity(opacity))
                .lineStyle(
                    StrokeStyle(
                        lineWidth: width,
                        lineCap: line.wide ? .round : .butt,
                        dash: line.dashed ? [4, 3] : []
                    )
                )
                if withPoints {
                    PointMark(
                        x: .value(Str.chartPeriod.text, point.label),
                        y: .value(Str.chartValue.text, point.value ?? 0)
                    )
                    .foregroundStyle(line.colour)
                    .symbolSize(line.dashed ? 26 : 40)
                }
            }
        }
    }

    private func interaction(_ proxy: ChartProxy) -> some View {
        GeometryReader { geometry in
            if let anchor = proxy.plotFrame {
                let plot = geometry[anchor]
                Rectangle()
                    .fill(.clear)
                    .contentShape(Rectangle())
                    .frame(width: plot.width, height: plot.height)
                    .position(x: plot.midX, y: plot.midY)
                    .onContinuousHover { phase in
                        switch phase {
                        case let .active(point): hovered = proxy.value(atX: point.x)
                        case .ended: hovered = nil
                        }
                    }
            }
        }
    }

    // MARK: - the line under the chart

    @ViewBuilder
    private var readout: some View {
        VStack(alignment: .leading, spacing: Space.s1) {
            if let hovered, !rows(at: hovered).isEmpty {
                Text(verbatim: Str.overviewWeekOf(hovered))
                    .font(Type.captionStrong)
                    .foregroundStyle(Ink.primary)
                ForEach(rows(at: hovered), id: \.0) { label, detail in
                    HStack(spacing: 6) {
                        Text(verbatim: label)
                            .font(Type.caption)
                            .foregroundStyle(Ink.secondary)
                        Spacer(minLength: Space.s3)
                        Text(verbatim: detail)
                            .font(Type.figure(12, weight: .regular))
                            .foregroundStyle(Ink.primary)
                    }
                }
            } else {
                Text(verbatim: hint)
                    .font(Type.caption)
                    .foregroundStyle(Ink.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(minHeight: 46, alignment: .top)
    }

    /// Only the measured series at that label: a hole has nothing to say and says nothing,
    /// rather than saying zero.
    private func rows(at label: String) -> [(String, String)] {
        series.compactMap { line in
            guard
                let point = line.points.first(where: { $0.label == label }),
                point.value != nil
            else { return nil }
            return (line.label, point.detail ?? Fmt.percent(point.value))
        }
    }

    private var accessibilityText: String {
        let parts = series.flatMap { line in
            line.points.compactMap { point -> String? in
                guard point.value != nil else { return nil }
                return "\(line.label) \(point.label) \(point.detail ?? Fmt.percent(point.value))"
            }
        }
        return parts.isEmpty ? hint : parts.joined(separator: "; ")
    }
}
