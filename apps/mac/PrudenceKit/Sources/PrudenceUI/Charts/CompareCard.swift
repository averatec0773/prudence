import Charts
import SwiftUI

/// This period against the last one: a stat card, the previous value, a neutral delta chip and
/// two mini bars.
///
/// The compare card in `charts.js`'s table. Three of its four parts are the engine's own text,
/// printed: the figure, the previous figure and the change, all three written by
/// `reviews/build._compared` so that this card and `prudence show --review` cannot disagree.
///
/// **The chip is never coloured by its sign** (`DeltaChip`): more sessions is not better and
/// less rework is not a score. The sign is in the characters, where the engine put it.
///
/// The twin bars are the one thing here that is not a stored string, and they are a *rendering*
/// of one: `numeric(_:)` reads the leading figure out of the cell the engine printed and the
/// two bars are drawn in proportion to each other. No new number is computed, nothing is
/// summed, and the bars carry no label of their own, so the figures a reader checks are still
/// exactly the ones the engine wrote. Where the engine has the raw value (`ReviewNumber.value`)
/// the caller passes it and no parsing happens at all. A cell that will not parse gets no bars
/// rather than bars of zero.
public struct CompareCard: View {

    let title: String
    /// The engine's own text for this period, the previous one, and the change.
    let value: String
    let previous: String
    let change: String
    /// The two magnitudes the bars are drawn from, when they are known.
    let nowValue: Double?
    let previousValue: Double?

    public init(
        title: String,
        value: String,
        previous: String,
        change: String,
        nowValue: Double? = nil,
        previousValue: Double? = nil
    ) {
        self.title = title
        self.value = value
        self.previous = previous
        self.change = change
        self.nowValue = nowValue ?? CompareCard.numeric(value)
        self.previousValue = previousValue ?? CompareCard.numeric(previous)
    }

    /// The leading figure of a cell the engine printed: `4.3`, `71% (1180)`, `43k`, `-`.
    ///
    /// A `k` suffix is thousands, because that is how `reviews/build._k` writes a token count.
    /// Anything with no digits in it at all, which is what `NOT_MEASURED` is, answers nil.
    public static func numeric(_ text: String) -> Double? {
        var digits = ""
        for character in text {
            if character.isNumber || character == "." { digits.append(character) }
            else if character == "-" && digits.isEmpty { digits.append(character) }
            else if !digits.isEmpty { break }
        }
        guard let value = Double(digits), value.isFinite else { return nil }
        // `43k` is 43 000. The suffix is the engine's, not a locale's.
        if let index = text.firstIndex(of: "k"), text.distance(from: text.startIndex, to: index) > 0 {
            return value * 1000
        }
        return value
    }

    public var body: some View {
        Card(padding: Space.s4) {
            VStack(alignment: .leading, spacing: Space.s1) {
                Text(verbatim: title)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(verbatim: value)
                    .font(Type.figure(24, weight: .medium))
                    .foregroundStyle(Ink.primary)
                HStack(alignment: .center, spacing: Space.s2) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(verbatim: Str.comparePrevious(previous))
                            .font(Type.caption2.monospacedDigit())
                            .foregroundStyle(Ink.tertiary)
                            .fixedSize(horizontal: false, vertical: true)
                        DeltaChip(change)
                    }
                    Spacer(minLength: Space.s2)
                    twin
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            Fmt.list([title, value, Str.comparePrevious(previous), Str.compareChange(change)]))
    }

    /// Two vertical bars, the previous period in grey and this one in the accent. They are a
    /// shape, not a figure: no axis, no labels, nothing to misread as a measurement.
    @ViewBuilder
    private var twin: some View {
        if let now = nowValue, let before = previousValue {
            let top = max(abs(now), abs(before), 1)
            Chart {
                BarMark(
                    x: .value(Str.chartSide.text, Str.comparePreviousShort.text),
                    y: .value(Str.chartValue.text, abs(before)),
                    width: .fixed(9)
                )
                .foregroundStyle(Ink.tertiary)
                .cornerRadius(2)
                BarMark(
                    x: .value(Str.chartSide.text, Str.compareNowShort.text),
                    y: .value(Str.chartValue.text, abs(now)),
                    width: .fixed(9)
                )
                .foregroundStyle(Ink.accent)
                .cornerRadius(2)
            }
            .chartYScale(domain: 0...top)
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
            .frame(width: 40, height: 28)
        }
    }
}
