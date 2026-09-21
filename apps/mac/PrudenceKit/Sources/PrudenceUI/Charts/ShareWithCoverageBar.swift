import Charts
import SwiftUI

/// A share with the coverage it is worth, in one row.
///
/// `shareWithCoverage` in `charts.js`. Two bars in one horizontal chart: the coverage is drawn
/// first, taller and pale (`Surface.coverage`), and the share is drawn over it. The two are not
/// the same measurement and are never added; the underlay is there so that a 71 % over a
/// coverage of 40 % cannot be read as the same claim as a 71 % over a coverage of 95 %.
///
/// **The denominator is printed beside the bar, always.** A share on its own is the one thing
/// principle 3 forbids, and there is no hover on a printed page or in a screenshot.
public struct ShareWithCoverageBar: View {

    let label: String
    let value: Double
    /// The mean share of a counted commit's added lines the session itself wrote. Nil where
    /// the row has none, and then no underlay is drawn rather than an underlay of zero.
    let coverage: Double?
    /// `71% (1180)` or whatever the engine printed, kept as its text.
    let valueText: String
    /// The number the share is over, already worded, e.g. `over 1180 lines`.
    let denominator: String?
    let tint: Color
    var labelWidth: CGFloat

    public init(
        label: String,
        value: Double,
        coverage: Double?,
        valueText: String,
        denominator: String? = nil,
        tint: Color,
        labelWidth: CGFloat = 170
    ) {
        self.label = label
        self.value = value
        self.coverage = coverage
        self.valueText = valueText
        self.denominator = denominator
        self.tint = tint
        self.labelWidth = labelWidth
    }

    /// A share outside 0...1 is a store or a parse that went wrong; the bar is clamped so it
    /// stays inside its track, and the text beside it still prints what was really stored.
    public static func clamp(_ share: Double) -> Double { min(max(share, 0), 1) }

    public var hasCoverage: Bool { coverage != nil }

    public var body: some View {
        HStack(alignment: .center, spacing: Space.s2) {
            Text(verbatim: label)
                .font(Type.caption)
                .foregroundStyle(Ink.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: labelWidth, alignment: .leading)
            chart
            HStack(spacing: 6) {
                Text(verbatim: valueText)
                    .font(Type.figure(13, weight: .medium))
                    .foregroundStyle(Ink.primary)
                if let denominator {
                    Text(verbatim: denominator)
                        .font(Type.caption.monospacedDigit())
                        .foregroundStyle(Ink.tertiary)
                }
            }
            .frame(width: 150, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    private var chart: some View {
        Chart {
            if let coverage {
                BarMark(
                    xStart: .value(Str.chartValue.text, 0),
                    xEnd: .value(Str.chartValue.text, Self.clamp(coverage)),
                    y: .value(Str.chartSide.text, "row"),
                    height: .fixed(24)
                )
                .foregroundStyle(Surface.coverage)
                .cornerRadius(3)
            }
            BarMark(
                xStart: .value(Str.chartValue.text, 0),
                xEnd: .value(Str.chartValue.text, Self.clamp(value)),
                y: .value(Str.chartSide.text, "row"),
                height: .fixed(14)
            )
            .foregroundStyle(tint)
            .cornerRadius(3)
        }
        .chartXScale(domain: 0...1)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(height: 24)
        .background(
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(Surface.sunken)
                .frame(height: 14)
        )
    }

    private var accessibilityText: String {
        var parts = [label, valueText]
        if let denominator { parts.append(denominator) }
        if let coverage { parts.append(Str.chartCoverageIs(Fmt.percent(coverage))) }
        return Fmt.list(parts)
    }
}
