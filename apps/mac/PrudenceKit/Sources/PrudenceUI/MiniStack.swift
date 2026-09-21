import Charts
import SwiftUI

/// One row of a composition: the popover's "this week" bar.
///
/// `miniStack` in `charts.js`, in Swift Charts: a single horizontal stacked `BarMark` with the
/// legend hidden, both axes hidden and a fixed 8 pt height, over a sunken track so a week with
/// no tokens still draws as an empty groove rather than as nothing at all.
///
/// The slices are put into the fixed purpose order before they are drawn, never sorted by
/// size, so two screenshots a week apart show the same colour in the same place. The
/// accessibility label carries the same numbers the bar does, which is the rule every chart in
/// this app follows.
public struct MiniStack: View {

    public struct Slice: Identifiable, Equatable, Sendable {
        public let purpose: String
        public let tokens: Int
        public var id: String { purpose }

        public init(purpose: String, tokens: Int) {
            self.purpose = purpose
            self.tokens = tokens
        }
    }

    let slices: [Slice]
    var height: CGFloat

    public init(slices: [Slice], height: CGFloat = 8) {
        self.slices = slices
        self.height = height
    }

    /// The slices worth drawing, in the fixed order.
    private var drawn: [Slice] {
        let positive = slices.filter { $0.tokens > 0 }
        let order = Purpose.ordered(positive.map(\.purpose))
        return order.compactMap { purpose in positive.first { $0.purpose == purpose } }
    }

    private var total: Int { drawn.reduce(0) { $0 + $1.tokens } }

    private var scale: (domain: [String], range: [Color]) {
        Purpose.scale(for: drawn.map(\.purpose))
    }

    public var body: some View {
        Group {
            if drawn.isEmpty {
                Capsule().fill(Surface.sunken)
            } else {
                Chart(drawn) { slice in
                    BarMark(
                        x: .value("Tokens", slice.tokens),
                        y: .value("Week", "week"),
                        height: .fixed(height)
                    )
                    .foregroundStyle(by: .value("Purpose", slice.purpose))
                }
                .chartForegroundStyleScale(domain: scale.domain, range: scale.range)
                .chartLegend(.hidden)
                .chartXAxis(.hidden)
                .chartYAxis(.hidden)
                .chartPlotStyle { plot in plot.frame(height: height) }
                .clipShape(Capsule())
                .background(Surface.sunken, in: Capsule())
            }
        }
        .frame(height: height)
        .accessibilityElement()
        .accessibilityLabel(accessibilityText)
    }

    /// Every purpose with its share and its token count, which is what the bar shows.
    private var accessibilityText: String {
        guard total > 0 else { return Str.menuNoTokensThisWeek.text }
        return drawn.map { slice in
            "\(Fmt.purpose(slice.purpose)) \(Fmt.percent(Double(slice.tokens) / Double(total)))"
                + ", \(Fmt.tokenPhrase(slice.tokens))"
        }
        .joined(separator: ", ")
    }
}
