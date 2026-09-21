import Charts
import SwiftUI

/// Composition of a whole, over time: one stacked bar per period.
///
/// `stackedBars` in `docs/design/mockups/charts.js`, in Swift Charts. The mockup's three
/// promises are kept here and each of them is a rule rather than a decoration:
///
/// - **A fixed purpose order and a fixed palette.** The slices are put into `Purpose.order`
///   whatever order they arrived in, so two screenshots taken a week apart show the same colour
///   in the same place and can be compared. Sorting by size would move every colour the week
///   somebody stopped doing research.
/// - **A value readout under the chart**, never a floating tooltip that a screenshot cannot
///   catch. Pointing at a bar prints that period's total and its per-purpose breakdown on a
///   line of its own, in the layout rather than inside the chart, which is also where type
///   stays at its real size (NOTES.md).
/// - **Clicking selects**, and clicking the selected bar again clears. Selection is a binding,
///   because the screen around the chart is what a selection filters.
///
/// Hover and click are both driven from one `chartOverlay` rather than from
/// `chartXSelection`: the overlay has to exist for the click anyway, and one source for both
/// means the bar under the pointer and the bar a click lands on can never be two different
/// bars.
public struct StackedBarsChart: View {

    /// One purpose's share of one period. The unit is whatever the caller is counting; the
    /// chart never formats it itself, `valueText` does.
    public struct Slice: Equatable, Sendable, Identifiable {
        public let purpose: String
        public let value: Int
        public var id: String { purpose }

        public init(purpose: String, value: Int) {
            self.purpose = purpose
            self.value = value
        }
    }

    /// One bar. `key` is its identity and what a selection carries; `label` is what the axis
    /// prints; `detail` is the extra line the readout adds under the totals.
    public struct Column: Equatable, Sendable, Identifiable {
        public let key: String
        public let label: String
        public let slices: [Slice]
        public let detail: String?

        public var id: String { key }
        public var total: Int { slices.reduce(0) { $0 + $1.value } }

        public init(key: String, label: String, slices: [Slice], detail: String? = nil) {
            self.key = key
            self.label = label
            self.slices = Column.ordered(slices)
            self.detail = detail
        }

        /// The fixed purpose order, whatever order the slices arrived in, with the empty ones
        /// dropped. A zero slice is not a colour with no height; it is a purpose that did not
        /// happen, and it stays out of the legend too.
        public static func ordered(_ slices: [Slice]) -> [Slice] {
            let positive = slices.filter { $0.value > 0 }
            return Purpose.ordered(positive.map(\.purpose)).compactMap { purpose in
                positive.first { $0.purpose == purpose }
            }
        }
    }

    let columns: [Column]
    /// How a value is printed, in the axis and in the readout. Supplied by the screen so that
    /// tokens, minutes and counts can all use this chart.
    let valueText: (Int) -> String
    /// What the readout says when nothing is under the pointer.
    let hint: String
    var height: CGFloat
    @Binding var selection: String?

    @State private var hovered: String?

    public init(
        columns: [Column],
        valueText: @escaping (Int) -> String,
        hint: String,
        height: CGFloat = 196,
        selection: Binding<String?>
    ) {
        self.columns = columns
        self.valueText = valueText
        self.hint = hint
        self.height = height
        _selection = selection
    }

    /// The bar the readout is about: the one under the pointer, else the selected one.
    private var active: Column? {
        let key = hovered ?? selection
        return columns.first { $0.key == key }
    }

    /// Every purpose anywhere in the range, so the scale and the legend do not change as the
    /// pointer moves.
    private var purposes: [String] {
        Purpose.ordered(Array(Set(columns.flatMap { $0.slices.map(\.purpose) })))
    }

    private var scale: (domain: [String], range: [Color]) { Purpose.scale(for: purposes) }

    /// `charts.js` caps a bar at 56 pt and otherwise gives it 62 % of its slot. Swift Charts
    /// decides the plot width itself, so the slot is approximated from a 900 pt plot, which is
    /// the window's own floor: three weeks get a bar rather than a block, and thirty weeks get
    /// a bar rather than an overlap.
    static let widestBar: CGFloat = 46
    static let assumedPlotWidth: CGFloat = 900

    private var barWidth: CGFloat {
        let slot = Self.assumedPlotWidth / CGFloat(max(columns.count, 1))
        return min(Self.widestBar, max(4, slot * 0.62))
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            chart
            readout
            PurposeLegend(purposes: scale.domain)
        }
    }

    private var chart: some View {
        Chart {
            ForEach(columns) { column in
                ForEach(column.slices) { slice in
                    BarMark(
                        x: .value(Str.chartPeriod.text, column.label),
                        y: .value(Str.chartValue.text, slice.value),
                        width: .fixed(barWidth)
                    )
                    .foregroundStyle(by: .value(Str.chartPurpose.text, slice.purpose))
                    .opacity(dim(column) ? 0.35 : 1)
                }
            }
        }
        .chartForegroundStyleScale(domain: scale.domain, range: scale.range)
        .chartLegend(.hidden)
        .chartYAxis {
            AxisMarks { value in
                AxisGridLine().foregroundStyle(Surface.grid)
                AxisValueLabel {
                    if let amount = value.as(Int.self) {
                        Text(verbatim: valueText(amount))
                            .font(Type.caption2.monospacedDigit())
                            .foregroundStyle(Ink.tertiary)
                    }
                }
            }
        }
        .chartXAxis { AxisMarks { AxisValueLabel(orientation: .horizontal) } }
        .frame(height: height)
        .chartOverlay { proxy in interaction(proxy) }
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    /// Everything a pointer does, in one transparent rectangle over the plot area.
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
                        case let .active(point): hovered = key(at: point.x, proxy: proxy)
                        case .ended: hovered = nil
                        }
                    }
                    .onTapGesture { point in
                        guard let key = key(at: point.x, proxy: proxy) else { return }
                        // Clicking the selected bar again clears it: a filter you cannot take
                        // off is a filter that reads as broken data.
                        withAnimation(Motion.state) {
                            selection = (selection == key) ? nil : key
                        }
                    }
            }
        }
    }

    /// The column key under an x offset inside the plot area, through the axis label the
    /// chart draws, which is the one string the proxy and the data both know.
    private func key(at x: CGFloat, proxy: ChartProxy) -> String? {
        guard let label: String = proxy.value(atX: x) else { return nil }
        return columns.first { $0.label == label }?.key
    }

    private func dim(_ column: Column) -> Bool {
        guard let active else { return false }
        return active.key != column.key
    }

    // MARK: - the line under the chart

    @ViewBuilder
    private var readout: some View {
        VStack(alignment: .leading, spacing: Space.s1) {
            Text(verbatim: headline)
                .font(Type.caption.monospacedDigit())
                .foregroundStyle(active == nil ? Ink.tertiary : Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let active, !active.slices.isEmpty {
                FlowLayout(spacing: Space.s3, lineSpacing: Space.s1) {
                    ForEach(active.slices) { slice in
                        HStack(spacing: 5) {
                            RoundedRectangle(cornerRadius: 2, style: .continuous)
                                .fill(Purpose.colour(slice.purpose))
                                .frame(width: 9, height: 9)
                            Text(verbatim: pair(slice, of: active.total))
                                .font(Type.caption.monospacedDigit())
                                .foregroundStyle(Ink.secondary)
                                .fixedSize()
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        // Reserve the second line so that selecting a bar does not move the cards below it.
        .frame(minHeight: 34, alignment: .top)
    }

    private var headline: String {
        guard let active else { return hint }
        var parts = [Str.overviewWeekOf(active.label), valueText(active.total)]
        if let detail = active.detail { parts.append(detail) }
        return Fmt.list(parts)
    }

    private func pair(_ slice: Slice, of total: Int) -> String {
        let share = total > 0 ? Double(slice.value) / Double(total) : 0
        return "\(Fmt.purpose(slice.purpose)) \(valueText(slice.value)) (\(Fmt.percent(share)))"
    }

    /// Every bar with its total and its slices, which is what the picture says.
    private var accessibilityText: String {
        guard !columns.isEmpty else { return hint }
        return columns.map { column in
            let slices = column.slices
                .map { "\(Fmt.purpose($0.purpose)) \(valueText($0.value))" }
                .joined(separator: ", ")
            return "\(column.label) \(valueText(column.total)): \(slices)"
        }
        .joined(separator: "; ")
    }
}
