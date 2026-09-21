import SwiftUI

/// The component set. Everything on every screen is built from these, so that two screens
/// cannot disagree about what a card or a caveat looks like.
///
/// None of them is glass: a card, a table and a chart stay opaque (`Surface.plain`), because a
/// figure read against a moving backdrop is a figure the reader cannot check. The glass layer
/// is `prudenceGlass`, and it goes on the popover, the sidebar, the toolbar strip and the
/// buttons and nowhere else.
///
/// Every figure in here uses `Type.figure`, which is `.monospacedDigit()`: a value that
/// changes must not reflow the row it sits in.

// MARK: - surfaces

/// The one card shape: a rounded rectangle, an opaque surface, and a 0.5 pt hairline ring
/// instead of a shadow.
public struct Card<Content: View>: View {

    var padding: CGFloat
    var radius: CGFloat
    var fill: Color
    @ViewBuilder var content: Content

    public init(
        padding: CGFloat = Space.cardPadding,
        radius: CGFloat = Radius.card,
        fill: Color = Surface.plain,
        @ViewBuilder content: () -> Content
    ) {
        self.padding = padding
        self.radius = radius
        self.fill = fill
        self.content = content()
    }

    public var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(fill, in: shape)
            .overlay(shape.strokeBorder(Surface.hairline, lineWidth: 0.5))
    }
}

/// A block of a page: a heading, an optional line under it, and whatever it holds.
public struct Panel<Content: View>: View {

    let title: String
    var note: String?
    @ViewBuilder var content: Content

    public init(title: String, note: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.note = note
        self.content = content()
    }

    public var body: some View {
        Card(padding: Space.cardPadding, radius: Radius.panel) {
            VStack(alignment: .leading, spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Type.headline).foregroundStyle(Ink.primary)
                    if let note {
                        Text(note)
                            .font(Type.caption)
                            .foregroundStyle(Ink.tertiary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                content
            }
        }
    }
}

// MARK: - figures

/// A caption above its content, the popover's own block shape.
///
/// One column, not two. The caption is a line of its own in caption type and the content
/// runs the full width under it, because a caption column beside the values gives the
/// popover a two-column shape, which is the one thing variant C is not.
public struct StatBlock<Content: View>: View {

    let caption: String
    @ViewBuilder var content: Content

    public init(_ caption: String, @ViewBuilder content: () -> Content) {
        self.caption = caption
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(caption)
                .font(Type.caption)
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One figure with its name above it and, where it has one, the detail under it.
public struct StatCard: View {

    let title: String
    let value: String
    var detail: String?
    var help: String?
    /// The review's own cards, of which there can be six in a row, are smaller than the
    /// Overview's three.
    var compact = false

    public init(
        title: String, value: String, detail: String? = nil, help: String? = nil,
        compact: Bool = false
    ) {
        self.title = title
        self.value = value
        self.detail = detail
        self.help = help
        self.compact = compact
    }

    public var body: some View {
        Card(padding: compact ? Space.s3 : Space.s4) {
            VStack(alignment: .leading, spacing: compact ? 2 : Space.s1) {
                Text(title)
                    .font(Type.caption)
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(value)
                    .font(Type.figure(compact ? 20 : 28, weight: .medium))
                    .foregroundStyle(Ink.primary)
                if let detail {
                    Text(detail)
                        .font(Type.caption2)
                        .foregroundStyle(Ink.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .help(help ?? title)
    }
}

/// The coverage and the method mix that travel with any share. Never a section away from the
/// number they qualify (principle 3).
public struct CoverageChip: View {

    let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text)
            .font(Type.caption2.monospacedDigit())
            .foregroundStyle(Ink.secondary)
            // A caveat that truncates is a caveat that stopped qualifying anything, and in
            // the popover's 220 pt value column "coverage 93%, method: 642 fact, 25 inferred"
            // does not fit on one line. Two lines in a rounded rectangle rather than one in a
            // capsule, because a capsule with two lines of text in it is a lozenge.
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, Space.s2)
            .padding(.vertical, 3)
            .background(
                Surface.sunken,
                in: RoundedRectangle(cornerRadius: Radius.control, style: .continuous))
    }
}

/// The distance between two figures, and **never a colour by sign**.
///
/// More sessions is not better and less rework is not a score, so there is no green-for-up and
/// no red-for-down anywhere in this app. The chip prints the sign as a character and takes its
/// ink from `Ink.secondary` whatever the number does; `DeltaChip.tint` is a constant, and a
/// test asserts it is the same value for a rise, a fall and no change at all.
public struct DeltaChip: View {

    let text: String

    /// The one ink a delta ever uses. Not a function of the value: see the note above.
    public static let tint = Ink.secondary

    public init(_ text: String) { self.text = text }

    /// `+12`, `-4`, `0`. The sign is information; the colour would be a judgement.
    public static func label(points value: Double) -> String {
        let points = (value * 100).rounded()
        if points == 0 { return "0" }
        return String(format: "%+.0f", points)
    }

    public var body: some View {
        Text(text)
            .font(Type.figure(12, weight: .medium))
            .foregroundStyle(Self.tint)
            .padding(.horizontal, Space.s2)
            .padding(.vertical, 3)
            .background(Surface.sunken, in: Capsule())
    }
}

/// How a figure was established, in the smallest type on the screen.
public struct MethodLine: View {

    let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text)
            .font(Type.caption.monospacedDigit())
            .foregroundStyle(Ink.tertiary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - the two states every screen has

/// Nothing to draw, and why. Never an empty rectangle: an empty screen that says nothing is
/// indistinguishable from a broken one.
public struct EmptyState: View {

    let symbol: String
    let title: String
    let detail: String

    public init(symbol: String, title: String, detail: String) {
        self.symbol = symbol
        self.title = title
        self.detail = detail
    }

    public var body: some View {
        VStack(spacing: Space.s3) {
            Image(systemName: symbol)
                .font(.system(size: 30, weight: .light))
                .foregroundStyle(Ink.tertiary)
            Text(title).font(Type.headline).foregroundStyle(Ink.primary)
            Text(detail)
                .font(Type.footnote)
                .foregroundStyle(Ink.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
    }
}

/// The store said no. The sentence `StoreError` writes already names both contract versions
/// and says which side to update, so this screen prints it rather than restating it.
public struct ContractMismatchState: View {

    let message: String
    var onRetry: (() -> Void)?

    public init(message: String, onRetry: (() -> Void)? = nil) {
        self.message = message
        self.onRetry = onRetry
    }

    public var body: some View {
        VStack(spacing: Space.s4) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(Outcome.rework)
            Text(.contractTitle).font(Type.title3).foregroundStyle(Ink.primary)
            Text(message)
                .font(Type.footnote)
                .foregroundStyle(Ink.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 480)
            Text(.contractNote).font(Type.caption).foregroundStyle(Ink.tertiary)
            if let onRetry {
                Button(Str.commonTryAgain.text, action: onRetry)
                    .buttonStyle(.prudence)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(Space.s7)
    }
}

// MARK: - the legend every purpose chart shares

/// The swatch and the label of one purpose, in the fixed order, built by hand.
///
/// Swift Charts' own legend has long-standing alignment and wrapping complaints, and a legend
/// that reflows differently between light and dark would make the two screenshots hard to
/// compare.
public struct PurposeLegend: View {

    let purposes: [String]
    /// The share beside each label, when there is one worth printing.
    var shares: [String: Double]?

    public init(purposes: [String], shares: [String: Double]? = nil) {
        self.purposes = purposes
        self.shares = shares
    }

    public var body: some View {
        // A wrapping row rather than an `HStack`: three purposes with their shares are about
        // 250 pt in English and the popover's value column is 240, so a fixed row breaks a
        // word in half. `FlowLayout` puts the fourth key on a second line instead.
        FlowLayout(spacing: Space.s3, lineSpacing: Space.s1) {
            ForEach(Purpose.ordered(purposes), id: \.self) { purpose in
                HStack(spacing: 5) {
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(Purpose.colour(purpose))
                        .frame(width: 9, height: 9)
                    Text(label(for: purpose))
                        .font(Type.caption.monospacedDigit())
                        .foregroundStyle(Ink.secondary)
                        .lineLimit(1)
                        .fixedSize()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func label(for purpose: String) -> String {
        guard let share = shares?[purpose] else { return Fmt.purpose(purpose) }
        return "\(Fmt.purpose(purpose)) \(Fmt.percent(share))"
    }
}
