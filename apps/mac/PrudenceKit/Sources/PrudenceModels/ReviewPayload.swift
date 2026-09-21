import Foundation
import PrudenceStore

/// The JSON a review row stores, as Swift types.
///
/// `reviews/build.py` writes one dictionary per review: a window, a project name, a list of
/// sections and a flat list of every figure on the page. Nothing here recomputes any of it.
/// A section carries `headers` and `rows` of already-formatted strings, the notes that explain
/// them, and the numbers behind them; `render.py` prints exactly those texts and nothing else
/// numeric, and so does this app. That is what makes the window and `prudence show --review`
/// incapable of disagreeing.
///
/// Two rules of design-for-change govern the decoding, and both are about a review written by
/// a newer engine than the app:
///
/// 1. **Unknown keys are ignored.** Every property is optional or defaulted, so a section that
///    grows a field still decodes.
/// 2. **An unknown section kind still renders.** `ReviewSection.kind` falls back to
///    `.other(key)`, and the screen draws those as a plain table of whatever headers and rows
///    they carry. A new section in `SECTIONS` is a new block on the page, never a crash and
///    never a silent omission.

public struct ReviewPayload: Decodable, Equatable, Sendable {
    public let reviewVersion: Int?
    public let window: ReviewWindow?
    public let projectName: String?
    public let sections: [ReviewSection]
    public let numbers: [ReviewNumber]
    public let versions: [String: Int]?

    enum CodingKeys: String, CodingKey {
        case reviewVersion = "review_version"
        case window
        case projectName = "project_name"
        case sections
        case numbers
        case versions
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        reviewVersion = try container.decodeIfPresent(Int.self, forKey: .reviewVersion)
        window = try container.decodeIfPresent(ReviewWindow.self, forKey: .window)
        projectName = try container.decodeIfPresent(String.self, forKey: .projectName)
        sections = try container.decodeIfPresent([ReviewSection].self, forKey: .sections) ?? []
        numbers = try container.decodeIfPresent([ReviewNumber].self, forKey: .numbers) ?? []
        versions = try container.decodeIfPresent([String: Int].self, forKey: .versions)
    }

    public init(
        reviewVersion: Int? = nil,
        window: ReviewWindow? = nil,
        projectName: String? = nil,
        sections: [ReviewSection] = [],
        numbers: [ReviewNumber] = [],
        versions: [String: Int]? = nil
    ) {
        self.reviewVersion = reviewVersion
        self.window = window
        self.projectName = projectName
        self.sections = sections
        self.numbers = numbers
        self.versions = versions
    }

    /// The stored text, decoded, or nil when it is not the JSON this build understands.
    ///
    /// Two shapes arrive here and both are the engine's own. The `review` table stores the
    /// whole dictionary `reviews/build.py` wrote, window and project name and all;
    /// `app_review.sections` is `json_extract(sections, '$.sections')`, which is the section
    /// list on its own, with the numbers beside it in a column of their own. A bare list is
    /// therefore a payload that carries nothing but its sections, not an unreadable one, and
    /// the only thing the app loses by reading the view is `window.source`.
    ///
    /// A payload that will not decode is a missing value, not a crash: the row still says
    /// which range it covered and the screen prints that much (ARCHITECTURE rule 3).
    public static func decode(_ text: String) -> ReviewPayload? {
        guard let data = text.data(using: .utf8) else { return nil }
        if let whole = try? JSONDecoder().decode(ReviewPayload.self, from: data) { return whole }
        guard let sections = try? JSONDecoder().decode([ReviewSection].self, from: data) else {
            return nil
        }
        return ReviewPayload(sections: sections)
    }

    /// The numbers list on its own, which `app_review.numbers` stores separately.
    public static func decodeNumbers(_ text: String?) -> [ReviewNumber] {
        guard let text, let data = text.data(using: .utf8) else { return [] }
        return (try? JSONDecoder().decode([ReviewNumber].self, from: data)) ?? []
    }

    public func section(_ kind: ReviewSectionKind) -> ReviewSection? {
        sections.first { $0.kind == kind }
    }
}

public struct ReviewWindow: Decodable, Equatable, Sendable {
    public let start: String?
    public let end: String?
    public let project: String?
    public let outcomeStart: String?
    public let outcomeEnd: String?
    /// How the range was chosen, e.g. `the last 14d`. Printed in brackets after the range.
    public let source: String?

    enum CodingKeys: String, CodingKey {
        case start, end, project, source
        case outcomeStart = "outcome_start"
        case outcomeEnd = "outcome_end"
    }
}

/// One figure, with the key it was computed under and the text it is printed as.
///
/// `text` is what a screen shows. `value` and `coverage` are the raw numbers behind it, kept
/// so a card can show the coverage beside the figure without parsing the string back.
public struct ReviewNumber: Decodable, Equatable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let text: String
    public let value: Double?
    public let coverage: Double?

    public var id: String { key }

    public init(key: String, label: String, text: String, value: Double?, coverage: Double?) {
        self.key = key
        self.label = label
        self.text = text
        self.value = value
        self.coverage = coverage
    }

    enum CodingKeys: String, CodingKey {
        case key, label, text, value, coverage
    }

    /// Rule 1 above, applied to a figure: every property is optional or defaulted, so one
    /// number written without a label does not throw away the whole list on the way to the
    /// screen. The key is the fallback label because it is what the engine names the figure.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = try container.decodeIfPresent(String.self, forKey: .key) ?? ""
        label = try container.decodeIfPresent(String.self, forKey: .label) ?? key
        text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
        value = try container.decodeIfPresent(Double.self, forKey: .value)
        coverage = try container.decodeIfPresent(Double.self, forKey: .coverage)
    }
}

/// The section kinds this build draws specially. Anything else is `.other`, which is drawn as
/// whatever table it brought with it rather than dropped.
public enum ReviewSectionKind: Equatable, Sendable {
    case did
    case became
    case observations
    case compared
    case suggestions
    case other(String)

    public init(key: String) {
        switch key {
        case "did": self = .did
        case "became": self = .became
        case "observations": self = .observations
        case "compared": self = .compared
        case "suggestions": self = .suggestions
        default: self = .other(key)
        }
    }

    public var isKnown: Bool {
        if case .other = self { return false }
        return true
    }
}

public struct ReviewSection: Decodable, Equatable, Sendable, Identifiable {
    public let key: String
    public let title: String?
    public let headers: [String]
    public let rows: [[String]]
    public let notes: [String]
    public let numbers: [ReviewNumber]
    /// The one sentence a section with nothing to say prints instead of a table.
    public let empty: String?

    public var id: String { key }
    public var kind: ReviewSectionKind { ReviewSectionKind(key: key) }
    public var heading: String { title ?? key }
    public var hasTable: Bool { !headers.isEmpty && !rows.isEmpty }

    enum CodingKeys: String, CodingKey {
        case key, title, headers, rows, notes, numbers, empty
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = try container.decodeIfPresent(String.self, forKey: .key) ?? ""
        title = try container.decodeIfPresent(String.self, forKey: .title)
        headers = try container.decodeIfPresent([String].self, forKey: .headers) ?? []
        rows = try container.decodeIfPresent([[String]].self, forKey: .rows) ?? []
        notes = try container.decodeIfPresent([String].self, forKey: .notes) ?? []
        numbers = try container.decodeIfPresent([ReviewNumber].self, forKey: .numbers) ?? []
        empty = try container.decodeIfPresent(String.self, forKey: .empty)
    }

    public init(
        key: String, title: String?, headers: [String] = [], rows: [[String]] = [],
        notes: [String] = [], numbers: [ReviewNumber] = [], empty: String? = nil
    ) {
        self.key = key
        self.title = title
        self.headers = headers
        self.rows = rows
        self.notes = notes
        self.numbers = numbers
        self.empty = empty
    }

    /// One row as label/value pairs against the headers, which is how an unknown section is
    /// drawn: whatever columns it brought, named by whatever headers came with them.
    public func pairs(of row: [String]) -> [(String, String)] {
        row.enumerated().map { index, cell in
            (index < headers.count ? headers[index] : "field \(index + 1)", cell)
        }
    }
}

/// One whole review, ready for the screen: the row, its payload, and its segment.
public struct ReviewModel: Equatable, Sendable, Identifiable {
    public let id: Int
    public let headline: String
    public let createdAt: String
    public let rangeStart: String
    public let rangeEnd: String
    public let outcomeRangeStart: String?
    public let outcomeRangeEnd: String?
    public let project: String?
    public let coverage: Double?
    public let payload: ReviewPayload?
    public let numbers: [ReviewNumber]
    public let segment: ReviewSegment?
    /// True when the stored JSON would not decode. The header still renders; the body says so.
    public let payloadUnreadable: Bool

    public init(row: AppReviewRow) {
        let payload = ReviewPayload.decode(row.sections)
        id = row.id
        createdAt = String(row.createdAt.prefix(10))
        rangeStart = String(row.rangeStart.prefix(10))
        rangeEnd = String(row.rangeEnd.prefix(10))
        outcomeRangeStart = row.outcomeRangeStart.map { String($0.prefix(10)) }
        outcomeRangeEnd = row.outcomeRangeEnd.map { String($0.prefix(10)) }
        project = row.project ?? payload?.projectName
        coverage = row.coverage
        self.payload = payload
        // The view stores the numbers twice, once inside `sections` and once on their own.
        // Prefer the column; fall back to the payload, so an older row still shows them.
        let separate = ReviewPayload.decodeNumbers(row.numbers)
        numbers = separate.isEmpty ? (payload?.numbers ?? []) : separate
        segment = ReviewSegment(row: row)
        payloadUnreadable = payload == nil
        headline = row.headline ?? "Review \(row.id), \(rangeStart) to \(rangeEnd)"
    }

    public var sections: [ReviewSection] { payload?.sections ?? [] }

    public var scope: String { project ?? "every project" }

    /// `Range 2026-09-08 to 2026-09-15 (the last 7d).`
    public var rangeLine: String {
        var text = "Range \(rangeStart) to \(rangeEnd)"
        if let source = payload?.window?.source { text += " (\(source))" }
        return text + "."
    }

    /// The outcome window, which is a different span and says why.
    public var outcomeLine: String? {
        guard let outcomeRangeStart, let outcomeRangeEnd else { return nil }
        return
            "Outcomes are the commits made between \(outcomeRangeStart) and \(outcomeRangeEnd), "
            + "which is every commit whose seven-day mark fell inside that range."
    }

    public var coverageText: String {
        coverage.map { Formatting.percent($0) } ?? "-"
    }
}

/// The optional model segment, with the credit line that must travel with it.
public struct ReviewSegment: Equatable, Sendable {
    public let text: String
    public let model: String
    public let createdAt: String?

    public init?(row: AppReviewRow) {
        guard let text = row.segmentText, !text.isEmpty else { return nil }
        self.text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        model = row.segmentModel ?? "a model"
        createdAt = row.segmentCreatedAt.map { String($0.prefix(10)) }
    }

    public var credit: String { "Written by \(model)" }
}
