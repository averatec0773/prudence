import Foundation

/// A stored review's sections, read as the shapes the charts draw.
///
/// **Nothing here computes a figure.** Every value is a column of the payload
/// `reviews/build.py` wrote: `ReviewNumber.text` is what a screen prints, and
/// `ReviewNumber.value` is the same figure unrounded, kept on the row precisely so a bar can
/// be drawn in proportion to it without anybody parsing the string back. Where the engine
/// stored no `value` — the comparison section does not — the screen draws no bar rather than
/// inventing one.
///
/// It lives in `PrudenceModels` rather than in a view so that a test can read a real payload
/// and check the pairing, which is the part that can silently go wrong: a section's rows and
/// its numbers are two lists that have to line up, and the engine is free to reorder either.
/// Everything below pairs by **label or key**, never by position alone.
public enum ReviewCharts {

    // MARK: - what you did

    /// One purpose's row in the `did` section: the table cells the engine printed, plus the
    /// unrounded token count it kept beside them.
    public struct PurposeSlice: Equatable, Sendable, Identifiable {
        public let purpose: String
        /// The tokens, unrounded, from `did.tokens.<purpose>`.
        public let tokens: Double
        /// `43k`, the way the engine printed it.
        public let tokensText: String
        public let sessionsText: String
        public let hoursText: String

        public var id: String { purpose }

        public init(
            purpose: String, tokens: Double, tokensText: String, sessionsText: String,
            hoursText: String
        ) {
            self.purpose = purpose
            self.tokens = tokens
            self.tokensText = tokensText
            self.sessionsText = sessionsText
            self.hoursText = hoursText
        }
    }

    /// The token key the engine writes for one purpose.
    public static func tokensKey(_ purpose: String) -> String { "did.tokens.\(purpose)" }

    /// The purpose rows of a `did` section, one per row that has a token figure of its own.
    ///
    /// The table's last row is the engine's own "all purposes" total and has no
    /// `did.tokens.<label>` number, which is how it is told apart from a purpose: by the
    /// absence of its own figure rather than by its English name or by its position.
    public static func purposeSlices(of section: ReviewSection) -> [PurposeSlice] {
        section.rows.compactMap { row -> PurposeSlice? in
            guard let purpose = row.first else { return nil }
            guard let number = section.numbers.first(where: { $0.key == tokensKey(purpose) })
            else { return nil }
            return PurposeSlice(
                purpose: purpose,
                tokens: number.value ?? 0,
                tokensText: row.count > 2 ? row[2] : number.text,
                sessionsText: row.count > 1 ? row[1] : "",
                hoursText: row.count > 3 ? row[3] : ""
            )
        }
    }

    // MARK: - what became of earlier work

    /// One figure of the `became` section, with whether it is a share and can be a bar.
    public struct ShareRow: Equatable, Sendable, Identifiable {
        /// The engine's own key, e.g. `became.alive_at_30_days`. Stable English, which is what
        /// makes `isRework` a key test rather than a string search in a translated label.
        public let key: String
        /// The label the engine printed, which is the first cell of the row.
        public let label: String
        /// `71% (1180)`, the share with the number it is over, as stored.
        public let valueText: String
        public let coverageText: String
        public let methodText: String
        /// The unrounded share, when this row is one. Nil for a count such as "lines followed".
        public let value: Double?
        public let coverage: Double?

        public var id: String { key }

        /// True when the row is a share and a bar can be drawn for it.
        public var isShare: Bool {
            guard let value else { return false }
            return valueText.contains("%") && value >= 0 && value <= 1
        }

        /// Rework rather than survival, by the engine's own key. The two are drawn in the
        /// `Outcome` pair, which is a warm-cool pair and **not** a verdict.
        public var isRework: Bool { key.contains("rework") }

        public init(
            key: String, label: String, valueText: String, coverageText: String,
            methodText: String, value: Double?, coverage: Double?
        ) {
            self.key = key
            self.label = label
            self.valueText = valueText
            self.coverageText = coverageText
            self.methodText = methodText
            self.value = value
            self.coverage = coverage
        }
    }

    /// The rows of a `became` section, each paired with the number the engine stored for it.
    ///
    /// Paired on the label, because `reviews/build._became` writes
    /// `Number(f"became.{label.replace(' ', '_')}", label, ...)`: the number's `label` is the
    /// row's first cell, character for character.
    public static func shareRows(of section: ReviewSection) -> [ShareRow] {
        section.rows.compactMap { row -> ShareRow? in
            guard let label = row.first else { return nil }
            let number = section.numbers.first { $0.label == label }
            return ShareRow(
                key: number?.key ?? "became.\(label.replacingOccurrences(of: " ", with: "_"))",
                label: label,
                valueText: row.count > 1 ? row[1] : (number?.text ?? ""),
                coverageText: row.count > 2 ? row[2] : "",
                methodText: row.count > 3 ? row[3] : "",
                value: number?.value,
                coverage: number?.coverage
            )
        }
    }

    // MARK: - observations

    /// One observation of a stored review: the sentence, the caveat and the two medians.
    public struct ObservationPair: Equatable, Sendable, Identifiable {
        /// `<repo_key>|<fact>|<outcome>`, the engine's own observation key
        /// (`reviews/schema.observation_key`).
        public let key: String
        public let sentence: String
        public let caveat: String
        public let withValue: Double
        public let withoutValue: Double
        public let coverage: Double?
        /// The sessions on each side, at contract 3. Nil on a payload written before the
        /// engine stored them, where the bars print the share alone.
        public let withN: Int?
        public let withoutN: Int?

        public var id: String { key }

        /// The outcome the two medians are of, which is the last field of the key.
        public var outcome: String { key.split(separator: "|").last.map(String.init) ?? "" }
        public var isRework: Bool { outcome == "rework" }

        public init(
            key: String, sentence: String, caveat: String, withValue: Double,
            withoutValue: Double, coverage: Double?, withN: Int? = nil, withoutN: Int? = nil
        ) {
            self.key = key
            self.sentence = sentence
            self.caveat = caveat
            self.withValue = withValue
            self.withoutValue = withoutValue
            self.coverage = coverage
            self.withN = withN
            self.withoutN = withoutN
        }
    }

    static let withSuffix = ".with"
    static let withoutSuffix = ".without"
    static let observationPrefix = "observation."

    /// The observations of a review, built from the `observation.<key>.with` and `.without`
    /// numbers and the row that carries the same observation's prose.
    ///
    /// Grouped on the key rather than on position, then matched with the rows in the order the
    /// engine wrote both, which is the same order: `_observations` appends one row and two
    /// numbers per observation in one loop. A row with no pair of numbers, or a pair with no
    /// row, is left out rather than half-drawn.
    ///
    /// **The counts behind the two sides arrived at contract 3.** Until then
    /// `reviews/build._observations` stored the sentence, the caveat and the two medians only,
    /// `with_n` and `without_n` lived on `app_observation` and not in the review's payload,
    /// and the bars on this screen carried no `n`; reading them off the live observation rows
    /// instead would have put this range's prose beside another range's counts. They are read
    /// off the `.with` and `.without` numbers now, and stay nil for a review an older engine
    /// wrote, where the bars print the share alone exactly as they did.
    public static func observationPairs(of section: ReviewSection) -> [ObservationPair] {
        var keys: [String] = []
        var withs: [String: ReviewNumber] = [:]
        var withouts: [String: ReviewNumber] = [:]
        for number in section.numbers {
            guard number.key.hasPrefix(observationPrefix) else { continue }
            let stem = String(number.key.dropFirst(observationPrefix.count))
            if stem.hasSuffix(withSuffix) {
                let key = String(stem.dropLast(withSuffix.count))
                if withs[key] == nil { keys.append(key) }
                withs[key] = number
            } else if stem.hasSuffix(withoutSuffix) {
                withouts[String(stem.dropLast(withoutSuffix.count))] = number
            }
        }
        var pairs: [ObservationPair] = []
        for (index, key) in keys.enumerated() {
            guard let with = withs[key], let without = withouts[key] else { continue }
            guard index < section.rows.count else { continue }
            let row = section.rows[index]
            pairs.append(
                ObservationPair(
                    key: key,
                    sentence: row.first ?? "",
                    caveat: row.count > 1 ? row[1] : "",
                    withValue: with.value ?? 0,
                    withoutValue: without.value ?? 0,
                    coverage: with.coverage ?? without.coverage,
                    withN: with.withN,
                    withoutN: without.withoutN ?? without.withN
                )
            )
        }
        return pairs
    }

    // MARK: - compared with the previous period

    /// One row of the `compared` section: four strings, all of them the engine's own, and at
    /// contract 3 the two magnitudes behind two of them.
    ///
    /// Until contract 3 `reviews/build._compared` wrote `Number(key, label, text)` with no
    /// fourth argument, so the comparison's figures were stored as text alone and the card
    /// sized its twin bars with `CompareCard.numeric`, which reads the leading figure out of
    /// the printed cell. Contract 3 stores `value` and `previous_value`, so the bars are drawn
    /// from figures rather than from a reading of a string. `numeric` stays as the fallback
    /// for an older review, and **a null is still a null**: the engine writes one where the
    /// page prints a dash, and a row with no value gets no bars rather than bars of zero.
    public struct CompareRow: Equatable, Sendable, Identifiable {
        public let label: String
        public let now: String
        public let previous: String
        public let change: String
        public let value: Double?
        public let previousValue: Double?

        public var id: String { label }

        public init(
            label: String, now: String, previous: String, change: String,
            value: Double? = nil, previousValue: Double? = nil
        ) {
            self.label = label
            self.now = now
            self.previous = previous
            self.change = change
            self.value = value
            self.previousValue = previousValue
        }
    }

    /// Paired on the label, the way `shareRows` is: `_compared` writes the number's `label`
    /// as the row's first cell, character for character.
    public static func compareRows(of section: ReviewSection) -> [CompareRow] {
        section.rows.compactMap { row in
            guard let label = row.first, row.count >= 4 else { return nil }
            let number = section.numbers.first { $0.label == label }
            return CompareRow(
                label: label,
                now: row[1],
                previous: row[2],
                change: row[3],
                value: number?.value,
                previousValue: number?.previousValue
            )
        }
    }
}
