import Charts
import SwiftUI

/// Two groups compared: **the core Prudence chart**.
///
/// One behaviour, two sides of the reader's own sessions, one outcome each. `pairedBars` in
/// `charts.js`. Everything about it is in service of one sentence being checkable:
///
/// - **The median value sits on each bar**, not on an axis somebody has to read across to.
/// - **`n` sits on each bar too.** A comparison whose two sides are 6 sessions and 94 is a
///   different claim from one whose sides are 40 and 40, and the picture must not hide which
///   it is. The engine's floor is five a side (`store/observations.MIN_SESSIONS`); the number
///   is printed anyway.
/// - **The gap in points goes underneath**, taken over the two shares *as they are printed*
///   rather than as they are held, so the reader who subtracts the two cells they can see gets
///   the number the app shows. That is `reviews/build._delta_points`' rule, kept here.
/// - **Colour never means good or bad.** The with-side takes the outcome's own colour
///   (`Outcome.alive` or `Outcome.rework`, which are a warm-cool pair and not a verdict) and
///   the without-side is grey. Neither says which side anybody should want to be on.
public struct PairedBarsChart: View {

    public struct Side: Equatable, Sendable {
        public let label: String
        public let value: Double
        /// The sessions behind this side. Optional because one surface has the numbers on the
        /// row and another (a stored review's observation section) does not carry them yet.
        public let n: Int?

        public init(label: String, value: Double, n: Int?) {
            self.label = label
            self.value = value
            self.n = n
        }
    }

    let with: Side
    let without: Side
    /// The with-side's colour. The without-side is always `Ink.tertiary`.
    let tint: Color
    var labelWidth: CGFloat
    var barHeight: CGFloat

    public init(
        with: Side,
        without: Side,
        tint: Color,
        labelWidth: CGFloat = 150,
        barHeight: CGFloat = 16
    ) {
        self.with = with
        self.without = without
        self.tint = tint
        self.labelWidth = labelWidth
        self.barHeight = barHeight
    }

    /// The axis top: a quarter, a half, three quarters or the whole, whichever first holds the
    /// taller bar. A scale that fitted itself to the data would make two observations with
    /// different values look identical.
    public static func niceMaxShare(_ value: Double) -> Double {
        if value <= 0.25 { return 0.25 }
        if value <= 0.5 { return 0.5 }
        if value <= 0.75 { return 0.75 }
        return 1
    }

    /// The distance between the two sides in whole points, over the values **as printed**.
    public static func gapPoints(_ first: Double, _ second: Double) -> Int {
        abs(Int((first * 100).rounded()) - Int((second * 100).rounded()))
    }

    private var domainMax: Double {
        Self.niceMaxShare(max(with.value, without.value, 0.01))
    }

    private var rows: [(side: Side, colour: Color)] {
        [(with, tint), (without, Ink.tertiary)]
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                bar(row.side, colour: row.colour)
            }
            HStack(spacing: Space.s2) {
                Color.clear.frame(width: labelWidth, height: 1)
                Text(verbatim: Str.observationGapPoints.plural(
                    Self.gapPoints(with.value, without.value)))
                    .font(Type.caption.monospacedDigit())
                    .foregroundStyle(Ink.tertiary)
                Spacer(minLength: 0)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    private func bar(_ side: Side, colour: Color) -> some View {
        HStack(alignment: .center, spacing: Space.s2) {
            Text(verbatim: side.label)
                .font(Type.caption)
                .foregroundStyle(Ink.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: labelWidth, alignment: .leading)
            Chart {
                BarMark(
                    xStart: .value(Str.chartValue.text, 0),
                    xEnd: .value(Str.chartValue.text, min(side.value, domainMax)),
                    y: .value(Str.chartSide.text, side.label),
                    height: .fixed(barHeight)
                )
                .foregroundStyle(colour)
                .cornerRadius(3)
            }
            .chartXScale(domain: 0...domainMax)
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
            .frame(height: barHeight)
            .background(
                RoundedRectangle(cornerRadius: 3, style: .continuous).fill(Surface.sunken)
            )
            Text(verbatim: valueText(side))
                .font(Type.figure(12, weight: .medium))
                .foregroundStyle(Ink.primary)
                .frame(width: 92, alignment: .leading)
        }
    }

    /// `71% · n=8`, or the share alone where the surface has no count to show.
    private func valueText(_ side: Side) -> String {
        guard let n = side.n else { return Fmt.percent(side.value) }
        return "\(Fmt.percent(side.value)) · \(Str.chartSampleSize(Fmt.count(n)))"
    }

    private var accessibilityText: String {
        let parts = rows.map { "\($0.side.label) \(valueText($0.side))" }
        return Fmt.list(
            parts + [Str.observationGapPoints.plural(
                Self.gapPoints(with.value, without.value))])
    }
}
