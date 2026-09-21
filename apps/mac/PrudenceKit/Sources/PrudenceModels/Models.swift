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

/// Sessions, edits and commits started today, local time.
///
/// The two numbers contract 1 could not give this line are here at contract 2, and both are
/// read rather than derived. `commits` comes from `app_commits_by_day`, where a commit is
/// counted once: summing `app_session_list` over a day counts a commit twice when two
/// sessions share it, which is what the dropdown used to do and why it was an upper bound.
/// `edits` is the sum of `app_session_list.edits`, and stays nil when no session today
/// carries one, because a missing count is not a zero (rule 10).
public struct TodayModel: Equatable, Sendable {
    public let sessions: Int
    public let commits: Int
    public let edits: Int?

    public init(sessions: Int, commits: Int, edits: Int? = nil) {
        self.sessions = sessions
        self.commits = commits
        self.edits = edits
    }

    public init(sessions: [AppSessionListRow], commits: [AppCommitsByDayRow]) {
        let counted = sessions.compactMap(\.edits)
        self.init(
            sessions: sessions.count,
            commits: commits.reduce(0) { $0 + $1.commits },
            edits: counted.isEmpty ? nil : counted.reduce(0, +)
        )
    }

    /// `2 sessions, 17 edits, 3 commits`. Edits are left out when nothing measured any.
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
    /// Every purpose the week measured, not only the three that are named. The dropdown's
    /// mini stacked bar draws all of them, so that the legend's three plus "the rest" add up
    /// to the bar the reader is looking at.
    public let all: [Slice]
    public let total: Int
    /// The week's active minutes, summed straight off `active_minutes`. A sum of one view
    /// column, which is the only arithmetic rule 2 allows a screen.
    public let activeMinutes: Double

    public init(top: [Slice], total: Int, all: [Slice]? = nil, activeMinutes: Double = 0) {
        self.top = top
        self.all = all ?? top
        self.total = total
        self.activeMinutes = activeMinutes
    }

    public static let topCount = 3

    public init(rows: [AppUsageByPurposeDayRow], limit: Int = WeekUsageModel.topCount) {
        var totals: [String: Int] = [:]
        for row in rows {
            totals[row.purpose, default: 0] += row.totalTokens ?? 0
        }
        let minutes = rows.reduce(0.0) { $0 + ($1.activeMinutes ?? 0) }
        let grand = totals.values.reduce(0, +)
        guard grand > 0 else {
            self.init(top: [], total: 0, all: [], activeMinutes: minutes)
            return
        }
        // Ties break on the purpose name so the order is the same on every refresh.
        let ranked = totals.sorted { left, right in
            left.value == right.value ? left.key < right.key : left.value > right.value
        }
        let slices = ranked.map {
            Slice(purpose: $0.key, tokens: $0.value, share: Double($0.value) / Double(grand))
        }
        self.init(
            top: Array(slices.prefix(limit)),
            total: grand,
            all: slices,
            activeMinutes: minutes
        )
    }

    /// `development 88%, research 12%`, the prototype's line.
    public var line: String {
        guard !top.isEmpty else { return "no tokens yet" }
        return top.map { "\($0.purpose) \(Formatting.percent($0.share))" }.joined(separator: ", ")
    }
}

// MARK: - the latest observation

/// One observation ready to print: the engine's own sentence, and the caveat that travels
/// with it.
///
/// The sentence is read from `app_observation.sentence`, never built here. At contract 1 the
/// app carried a copy of the phrase table in `store/observations.py` and a test pinned it
/// word for word; contract 2 stores the prose, so the copy is gone and there is nothing left
/// to drift. The caveat is the only text assembled in Swift, and it is three numbers from the
/// same row in a fixed shape, which principle 3 requires to sit beside the sentence.
public struct ObservationModel: Equatable, Sendable, Identifiable {
    public let id: Int
    public let project: String?
    public let isPooled: Bool
    public let sentence: String
    public let caveat: String
    public let coverage: Double?
    public let factCommits: Int
    public let inferredCommits: Int
    public let withN: Int
    public let withoutN: Int
    public let withValue: Double
    public let withoutValue: Double
    public let outcome: String

    public init(row: AppObservationRow) {
        id = row.observationId
        project = row.project
        isPooled = row.isPooled
        sentence = row.sentence ?? Self.missingSentence(row)
        caveat = Self.caveat(for: row)
        coverage = row.coverage
        factCommits = row.factCommits
        inferredCommits = row.inferredCommits
        withN = row.withN
        withoutN = row.withoutN
        withValue = row.withValue
        withoutValue = row.withoutValue
        outcome = row.outcome
    }

    /// How far apart the two sides are, which is what the screens sort on.
    public var gap: Double { abs(withValue - withoutValue) }

    /// `(coverage: 90%, method: 4 fact, 3 inferred)`, as the CLI prints it.
    public static func caveat(for row: AppObservationRow) -> String {
        let coverage = row.coverage.map { Formatting.percent($0) } ?? "-"
        return
            "(coverage: \(coverage), method: \(row.factCommits) fact, \(row.inferredCommits) inferred)"
    }

    /// A row whose `sentence` is NULL. Not a crash and not an invented sentence: the numbers
    /// are there, the prose is not, and the screen says which row is missing it.
    static func missingSentence(_ row: AppObservationRow) -> String {
        "\(row.fact) against \(row.outcome): this store has the numbers but not the sentence."
    }
}

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
        let model = ObservationModel(row: row)
        self.init(sentence: model.sentence, caveat: model.caveat)
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

    public init(row: AppReviewRow) {
        let payload = ReviewPayload.decode(row.sections)
        self.init(
            id: row.id,
            rangeStart: String(row.rangeStart.prefix(10)),
            rangeEnd: String(row.rangeEnd.prefix(10)),
            // `project` on the view is the name a person uses; the payload carries the same
            // name and is the fallback, exactly as `reviews/render._scope` reads it.
            project: row.project ?? payload?.projectName,
            firstSection: payload?.sections.first.map { $0.title ?? $0.key }
        )
    }

    /// `Review 3, 6 to 20 Sep, prudence: What you did`.
    public var headline: String {
        var text = "Review \(id), \(rangeStart) to \(rangeEnd)"
        if let project { text += ", \(project)" }
        if let firstSection { text += ": \(firstSection)" }
        return text
    }

    /// The title of the first section of a stored payload, or nil when it cannot be read. An
    /// unreadable payload is a missing value, never a crash (ARCHITECTURE rule 3).
    static func firstSectionTitle(of sections: String) -> String? {
        guard let first = ReviewPayload.decode(sections)?.sections.first else { return nil }
        return first.title ?? first.key
    }
}

// MARK: - everything the dropdown shows, read in one pass

public struct Snapshot: Sendable {
    public var status: StatusModel?
    public var today: TodayModel
    public var week: WeekUsageModel
    public var observation: LatestObservationModel?
    /// The same row, unformatted.
    ///
    /// The dropdown needs the columns rather than the engine's finished English, because it
    /// composes the sentence in the interface language (`PrudenceUI/ObservationText`). The
    /// stored `sentence` stays on the row as the thing that composition is checked against.
    public var observationRow: AppObservationRow?
    public var review: LatestReviewModel?
    /// The store's own complaint, if it had one: a contract mismatch or a missing file.
    public var storeError: String?
    public var readAt: Date

    public init(
        status: StatusModel? = nil,
        today: TodayModel = TodayModel(sessions: 0, commits: 0),
        week: WeekUsageModel = WeekUsageModel(top: [], total: 0),
        observation: LatestObservationModel? = nil,
        observationRow: AppObservationRow? = nil,
        review: LatestReviewModel? = nil,
        storeError: String? = nil,
        readAt: Date = Date()
    ) {
        self.status = status
        self.today = today
        self.week = week
        self.observation = observation
        self.observationRow = observationRow
        self.review = review
        self.storeError = storeError
        self.readAt = readAt
    }

    /// One read of the store, for the whole dropdown. Six statements, all indexed, all well
    /// under a frame on the founder's 740 MB store.
    public static func read(from store: Store, now: Date = Date()) throws -> Snapshot {
        let bounds = Formatting.localDayBoundsUTC(now)
        let today = Formatting.day(now)
        let weekStart =
            Calendar.current.date(byAdding: .day, value: -6, to: now) ?? now
        let statusRow = try store.status()
        let todayRows = try store.sessions(startedBetween: bounds.start, and: bounds.end)
        // The local day, from the view that counts a commit once.
        let todayCommits = try store.commitsByDay(since: today).filter { $0.day == today }
        let usageRows = try store.usageByPurposeDay(since: Formatting.day(weekStart))
        let observationRows = try store.observations()
        let reviewRow = try store.latestReview()
        return Snapshot(
            status: statusRow.map(StatusModel.init(row:)),
            today: TodayModel(sessions: todayRows, commits: todayCommits),
            week: WeekUsageModel(rows: usageRows),
            observation: LatestObservationModel(rows: observationRows),
            observationRow: observationRows.first,
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
