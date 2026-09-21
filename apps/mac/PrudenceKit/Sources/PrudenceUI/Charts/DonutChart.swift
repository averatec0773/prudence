import Charts
import SwiftUI

/// Composition of a whole, one period: a ring with the count in the middle and the
/// percentages listed beside it.
///
/// `donut` in `charts.js`, as `SectorMark`. The ring carries the shape and the list beside it
/// carries the numbers, because a share painted on a slice is a share nobody can read at 9 pt
/// and a share with no denominator is the thing principle 3 forbids. The list therefore prints
/// the percentage **and** the value it is a percentage of, and the middle of the ring holds the
/// count the whole is over.
///
/// Same palette and same fixed order as every other purpose chart in the app.
public struct DonutChart: View {

    public struct Slice: Equatable, Sendable, Identifiable {
        public let purpose: String
        public let value: Double
        /// How this slice's own value is printed, when the caller already has the text.
        ///
        /// A stored review's figures were formatted by the engine (`713938k`), and the same
        /// number formatted again by the app (`713.9M`) on the same screen as the table it
        /// came from reads as two different figures. The text wins wherever there is one.
        public let text: String?
        public var id: String { purpose }

        public init(purpose: String, value: Double, text: String? = nil) {
            self.purpose = purpose
            self.value = value
            self.text = text
        }
    }

    let slices: [Slice]
    /// The figure in the middle, already formatted, and the word under it.
    ///
    /// **Nil leaves the middle empty.** A review written by an engine that stored no session
    /// count has no figure for it, and a confident `0` over a full ring is worse than a hole:
    /// it is a number nobody measured (ARCHITECTURE rule 10).
    let centreValue: String?
    let centreLabel: String
    /// How a slice's own value is printed beside its percentage.
    let valueText: (Double) -> String
    var size: CGFloat

    public init(
        slices: [Slice],
        centreValue: String?,
        centreLabel: String,
        valueText: @escaping (Double) -> String,
        size: CGFloat = 168
    ) {
        self.slices = DonutChart.ordered(slices)
        self.centreValue = centreValue
        self.centreLabel = centreLabel
        self.valueText = valueText
        self.size = size
    }

    /// The fixed purpose order, with the empty slices dropped. The counterpart of
    /// `StackedBarsChart.Column.ordered`, and for the same reason.
    public static func ordered(_ slices: [Slice]) -> [Slice] {
        let positive = slices.filter { $0.value > 0 }
        return Purpose.ordered(positive.map(\.purpose)).compactMap { purpose in
            positive.first { $0.purpose == purpose }
        }
    }

    public var total: Double { slices.reduce(0) { $0 + $1.value } }

    /// One slice's share of the whole. Zero when nothing was measured, never a division by it.
    public func share(of slice: Slice) -> Double {
        total > 0 ? slice.value / total : 0
    }

    private var scale: (domain: [String], range: [Color]) {
        Purpose.scale(for: slices.map(\.purpose))
    }

    public var body: some View {
        HStack(alignment: .center, spacing: Space.s5) {
            ring
            list
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    @ViewBuilder
    private var ring: some View {
        if slices.isEmpty {
            Circle()
                .strokeBorder(Surface.sunken, lineWidth: 22)
                .frame(width: size, height: size)
                .overlay { centre }
        } else {
            Chart(slices) { slice in
                SectorMark(
                    angle: .value(Str.chartValue.text, slice.value),
                    innerRadius: .ratio(0.62),
                    angularInset: 1
                )
                .foregroundStyle(by: .value(Str.chartPurpose.text, slice.purpose))
            }
            .chartForegroundStyleScale(domain: scale.domain, range: scale.range)
            .chartLegend(.hidden)
            .frame(width: size, height: size)
            .overlay { centre }
        }
    }

    @ViewBuilder
    private var centre: some View {
        if let centreValue {
            VStack(spacing: 1) {
                Text(verbatim: centreValue)
                    .font(Type.figure(20, weight: .semibold))
                    .foregroundStyle(Ink.primary)
                Text(verbatim: centreLabel)
                    .font(Type.caption2)
                    .foregroundStyle(Ink.tertiary)
            }
        }
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(slices) { slice in
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(Purpose.colour(slice.purpose))
                        .frame(width: 9, height: 9)
                    Text(verbatim: Fmt.purpose(slice.purpose))
                        .font(Type.caption)
                        .foregroundStyle(Ink.secondary)
                    Spacer(minLength: Space.s3)
                    Text(verbatim: Fmt.percent(share(of: slice)))
                        .font(Type.figure(12, weight: .medium))
                        .foregroundStyle(Ink.primary)
                    Text(verbatim: printed(slice))
                        .font(Type.figure(12, weight: .regular))
                        .foregroundStyle(Ink.tertiary)
                        .fixedSize()
                        .frame(minWidth: 58, alignment: .trailing)
                }
            }
        }
        .frame(minWidth: 210, alignment: .leading)
    }

    /// One slice's value, the caller's own text where there is one.
    private func printed(_ slice: Slice) -> String { slice.text ?? valueText(slice.value) }

    private var accessibilityText: String {
        let middle = centreValue.map { "\($0) \(centreLabel). " } ?? ""
        guard !slices.isEmpty else { return middle }
        let parts = slices.map { slice in
            "\(Fmt.purpose(slice.purpose)) \(Fmt.percent(share(of: slice))), "
                + printed(slice)
        }
        return middle + parts.joined(separator: "; ")
    }
}
