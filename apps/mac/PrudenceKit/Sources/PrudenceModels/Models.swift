import Foundation
import PrudenceStore

/// The view models: one struct per line of the dropdown, each built from rows and nothing else.
///
/// They are values, not objects, so a test can build one by hand and the render harness can
/// draw a screen without a database. Everything they do to a number is formatting or a share
/// of two numbers the engine already gave; no model here computes a fact.

// MARK: - status

public struct StatusModel: Equatable, Sendable {
    public let engineVersion: String
    public let contractVersion: String
    public let lastIngest: Date?
    public let sessions: Int
    public let projects: Int

    public init(
        engineVersion: String, contractVersion: String, lastIngest: Date?, sessions: Int,
        projects: Int
    ) {
        self.engineVersion = engineVersion
        self.contractVersion = contractVersion
        self.lastIngest = lastIngest
        self.sessions = sessions
        self.projects = projects
    }

    public init(row: AppStatusRow) {
        self.init(
            engineVersion: row.engineVersion,
            contractVersion: row.appContractVersion,
            lastIngest: Formatting.timestamp(row.lastIngestAt),
            sessions: row.sessions,
            projects: row.projects
        )
    }

    /// `20 Sep 18:04 (4 minutes ago)`, or `never`.
    public func lastIngestText(now: Date = Date()) -> String {
        guard let lastIngest else { return "never" }
        return "\(Formatting.localTime(lastIngest)) (\(Formatting.relative(lastIngest, now: now)))"
    }
}

// MARK: - today

/// Sessions and commits started today, local time.
///
/// `edits` is deliberately optional and is nil against contract 1: no `app_*` view carries
/// edits per day, so the app shows what it has rather than inventing a join (rule 8). The
/// rumps prototype counted the `edit` table directly, which is exactly what the app may not do.
public struct TodayModel: Equatable, Sendable {
    public let sessions: Int
    public let commits: Int
    public let edits: Int?

    public init(sessions: Int, commits: Int, edits: Int? = nil) {
        self.sessions = sessions
        self.commits = commits
        self.edits = edits
    }

    public init(rows: [AppSessionListRow]) {
        self.init(
            sessions: rows.count,
            commits: rows.reduce(0) { $0 + $1.countedCommits },
            edits: nil
        )
    }

    /// `2 sessions, 3 commits`. Edits join the line the day a view carries them.
    public var line: String {
        var parts = ["\(sessions) sessions"]
        if let edits { parts.append("\(edits) edits") }
        parts.append("\(commits) commits")
        return parts.joined(separator: ", ")
    }
}

// MARK: - this week by purpose

/// The last seven local days of tokens, by purpose, top three.
///
/// Seven days back from today inclusive, which is `prudence usage --last 7d`'s window, not the
/// ISO week the rumps prototype used. The shares are of the seven days' total, so they add up
/// to at most 100 and the reader can see how much the top three leave out.
public struct WeekUsageModel: Equatable, Sendable {

    public struct Slice: Equatable, Sendable {
        public let purpose: String
        public let tokens: Int
        public let share: Double

        public init(purpose: String, tokens: Int, share: Double) {
            self.purpose = purpose
            self.tokens = tokens
            self.share = share
        }
    }

    public let top: [Slice]
    public let total: Int

    public init(top: [Slice], total: Int) {
        self.top = top
        self.total = total
    }

    public static let topCount = 3

    public init(rows: [AppUsageByPurposeDayRow], limit: Int = WeekUsageModel.topCount) {
        var totals: [String: Int] = [:]
        for row in rows {
            totals[row.purpose, default: 0] += row.totalTokens ?? 0
        }
        let grand = totals.values.reduce(0, +)
        guard grand > 0 else {
            self.init(top: [], total: 0)
            return
        }
        // Ties break on the purpose name so the order is the same on every refresh.
        let ranked = totals.sorted { left, right in
            left.value == right.value ? left.key < right.key : left.value > right.value
        }
        self.init(
            top: ranked.prefix(limit).map {
                Slice(purpose: $0.key, tokens: $0.value, share: Double($0.value) / Double(grand))
            },
            total: grand
        )
    }

    /// `development 88%, research 12%`, the prototype's line.
    public var line: String {
        guard !top.isEmpty else { return "no tokens yet" }
        return top.map { "\($0.purpose) \(Formatting.percent($0.share))" }.joined(separator: ", ")
    }
}

// MARK: - the latest observation

public struct LatestObservationModel: Equatable, Sendable {
    public let sentence: String
    public let caveat: String

    public init(sentence: String, caveat: String) {
        self.sentence = sentence
        self.caveat = caveat
    }

    /// The first row of `app_observation`, which is already in the engine's own order: a
    /// project's own rows before the pooled ones that speak for every project at once.
    public init?(rows: [AppObservationRow]) {
        guard let row = rows.first else { return nil }
        self.init(
            sentence: ObservationSentence.sentence(for: row),
            caveat: ObservationSentence.caveat(for: row)
        )
    }

    public var short: String { Formatting.truncate(sentence) }
}

// MARK: - the latest review

public struct LatestReviewModel: Equatable, Sendable {
    public let id: Int
    public let rangeStart: String
    public let rangeEnd: String
    public let project: String?
    public let firstSection: String?

    public init(
        id: Int, rangeStart: String, rangeEnd: String, project: String?, firstSection: String?
    ) {
        self.id = id
        self.rangeStart = rangeStart
        self.rangeEnd = rangeEnd
        self.project = project
        self.firstSection = firstSection
    }

    public init(row: ReviewHeadlineRow) {
        let payload = Self.payload(of: row.sections)
        self.init(
            id: row.id,
            rangeStart: String(row.rangeStart.prefix(10)),
            rangeEnd: String(row.rangeEnd.prefix(10)),
            // The row's `project` column is the repository key, which is a hash; the name the
            // person uses is on the payload, exactly as `reviews/render._scope` reads it.
            project: (payload?["project_name"] as? String) ?? row.project,
            firstSection: Self.firstSectionTitle(in: payload)
        )
    }

    /// `Review 3, 6 to 20 Sep, prudence: What you did`.
    public var headline: String {
        var text = "Review \(id), \(rangeStart) to \(rangeEnd)"
        if let project { text += ", \(project)" }
        if let firstSection { text += ": \(firstSection)" }
        return text
    }

    /// The stored JSON, or nil when it cannot be read. An unreadable payload is a missing
    /// value, never a crash (ARCHITECTURE rule 3): the row still says which range it covered.
    static func payload(of sections: String) -> [String: Any]? {
        guard let data = sections.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    /// The title of the first section, which is the review's own opening line.
    static func firstSectionTitle(in payload: [String: Any]?) -> String? {
        guard let list = payload?["sections"] as? [[String: Any]], let first = list.first
        else { return nil }
        return (first["title"] as? String) ?? (first["key"] as? String)
    }

    static func firstSectionTitle(of sections: String) -> String? {
        firstSectionTitle(in: payload(of: sections))
    }
}

// MARK: - everything the dropdown shows, read in one pass

public struct Snapshot: Sendable {
    public var status: StatusModel?
    public var today: TodayModel
    public var week: WeekUsageModel
    public var observation: LatestObservationModel?
    public var review: LatestReviewModel?
    /// The store's own complaint, if it had one: a contract mismatch or a missing file.
    public var storeError: String?
    public var readAt: Date

    public init(
        status: StatusModel? = nil,
        today: TodayModel = TodayModel(sessions: 0, commits: 0),
        week: WeekUsageModel = WeekUsageModel(top: [], total: 0),
        observation: LatestObservationModel? = nil,
        review: LatestReviewModel? = nil,
        storeError: String? = nil,
        readAt: Date = Date()
    ) {
        self.status = status
        self.today = today
        self.week = week
        self.observation = observation
        self.review = review
        self.storeError = storeError
        self.readAt = readAt
    }

    /// One read of the store, for the whole dropdown. Five statements, all indexed, all well
    /// under a frame on the founder's 740 MB store.
    public static func read(from store: Store, now: Date = Date()) throws -> Snapshot {
        let bounds = Formatting.localDayBoundsUTC(now)
        let weekStart =
            Calendar.current.date(byAdding: .day, value: -6, to: now) ?? now
        let statusRow = try store.status()
        let todayRows = try store.sessions(startedBetween: bounds.start, and: bounds.end)
        let usageRows = try store.usageByPurposeDay(since: Formatting.day(weekStart))
        let observationRows = try store.observations()
        let reviewRow = try store.latestReview()
        return Snapshot(
            status: statusRow.map(StatusModel.init(row:)),
            today: TodayModel(rows: todayRows),
            week: WeekUsageModel(rows: usageRows),
            observation: LatestObservationModel(rows: observationRows),
            review: reviewRow.map(LatestReviewModel.init(row:)),
            storeError: nil,
            readAt: now
        )
    }

    /// The snapshot for a store that would not open: everything empty, the reason kept.
    public static func failed(_ error: StoreError, now: Date = Date()) -> Snapshot {
        Snapshot(storeError: error.message, readAt: now)
    }
}
