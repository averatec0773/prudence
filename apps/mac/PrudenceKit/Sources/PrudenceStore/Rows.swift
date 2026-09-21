import Foundation
import GRDB

/// One struct per `app_*` view, with the column names copied from `APP_VIEWS`.
///
/// Every column the Python side can answer with NULL is optional here, and nothing is given a
/// default: a missing number stays missing all the way to the screen, where it prints as "-"
/// rather than as a zero somebody could mistake for a measurement (ARCHITECTURE rule 10).

public struct AppStatusRow: Codable, FetchableRecord, Equatable, Sendable {
    public let engineVersion: String
    public let lastIngestAt: String?
    public let sessions: Int
    public let projects: Int
    public let appContractVersion: String
    public let parserVersion: Int?
    public let purposeRuleVersion: Int?
    public let commitFactVersion: Int?
    public let attributionFactVersion: Int?
    public let outcomeFactVersion: Int?
    public let observationFactVersion: Int?
    public let hookFactVersion: Int?

    enum CodingKeys: String, CodingKey {
        case engineVersion = "engine_version"
        case lastIngestAt = "last_ingest_at"
        case sessions
        case projects
        case appContractVersion = "app_contract_version"
        case parserVersion = "parser_version"
        case purposeRuleVersion = "purpose_rule_version"
        case commitFactVersion = "commit_fact_version"
        case attributionFactVersion = "attribution_fact_version"
        case outcomeFactVersion = "outcome_fact_version"
        case observationFactVersion = "observation_fact_version"
        case hookFactVersion = "hook_fact_version"
    }
}

public struct AppUsageByPurposeDayRow: Codable, FetchableRecord, Equatable, Sendable {
    public let day: String
    public let repoKey: String?
    public let project: String
    public let purpose: String
    public let inputTokens: Int?
    public let outputTokens: Int?
    public let cacheReadTokens: Int?
    public let cacheCreationTokens: Int?
    public let totalTokens: Int?
    public let activeMinutes: Double?
    public let sessions: Int
    public let measuredSessions: Int

    enum CodingKeys: String, CodingKey {
        case day
        case repoKey = "repo_key"
        case project
        case purpose
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case cacheReadTokens = "cache_read_tokens"
        case cacheCreationTokens = "cache_creation_tokens"
        case totalTokens = "total_tokens"
        case activeMinutes = "active_minutes"
        case sessions
        case measuredSessions = "measured_sessions"
    }
}

public struct AppOutcomesByWeekRow: Codable, FetchableRecord, Equatable, Sendable {
    public let repoKey: String?
    public let project: String
    public let weekStart: String
    public let commits: Int
    public let commitsFact: Int?
    public let commitsInferred: Int?
    public let lines: Int?
    public let measured7d: Int?
    public let alive7d: Int?
    public let measured30d: Int?
    public let alive30d: Int?
    public let measured90d: Int?
    public let alive90d: Int?
    public let aliveHead: Int?
    public let aliveHeadAnywhere: Int?
    public let blameHead: Int?
    public let reworked: Int?
    public let coverage: Double?

    enum CodingKeys: String, CodingKey {
        case repoKey = "repo_key"
        case project
        case weekStart = "week_start"
        case commits
        case commitsFact = "commits_fact"
        case commitsInferred = "commits_inferred"
        case lines
        case measured7d = "measured_7d"
        case alive7d = "alive_7d"
        case measured30d = "measured_30d"
        case alive30d = "alive_30d"
        case measured90d = "measured_90d"
        case alive90d = "alive_90d"
        case aliveHead = "alive_head"
        case aliveHeadAnywhere = "alive_head_anywhere"
        case blameHead = "blame_head"
        case reworked
        case coverage
    }
}

public struct AppObservationRow: Codable, FetchableRecord, Equatable, Sendable {
    public let observationId: Int
    public let repoKey: String
    public let project: String?
    public let pooled: Int
    public let fact: String
    public let thresholdText: String
    /// The threshold as a number and a rule, at contract 3. `thresholdText` is the engine's
    /// English for the same split and stays as the fallback; both are nil-tolerant, because a
    /// contract 2 store has neither column.
    public let thresholdValue: Double?
    /// `">="`, `">"`, `"=="`, or nil where the split has no comparison to print.
    public let thresholdOp: String?
    public let outcome: String
    public let direction: String
    public let withN: Int
    public let withoutN: Int
    public let withValue: Double
    public let withoutValue: Double
    public let coverage: Double?
    public let factCommits: Int
    public let inferredCommits: Int
    public let factVersion: Int
    /// The sentence the CLI prints for this row, stored rather than restated in Swift.
    /// Contract 1 had no such column and the app kept a copy of `store/observations.SPLITS`;
    /// contract 2 carries it, and that copy is gone.
    public let sentence: String?

    enum CodingKeys: String, CodingKey {
        case observationId = "observation_id"
        case repoKey = "repo_key"
        case project
        case pooled
        case fact
        case thresholdText = "threshold_text"
        case thresholdValue = "threshold_value"
        case thresholdOp = "threshold_op"
        case outcome
        case direction
        case withN = "with_n"
        case withoutN = "without_n"
        case withValue = "with_value"
        case withoutValue = "without_value"
        case coverage
        case factCommits = "fact_commits"
        case inferredCommits = "inferred_commits"
        case factVersion = "fact_version"
        case sentence
    }

    public var isPooled: Bool { pooled != 0 }

    /// How far apart the two sides are. The screens sort on it, because a bigger gap is what
    /// makes an observation worth reading first; it is a difference of two view columns and
    /// nothing else.
    public var gap: Double { abs(withValue - withoutValue) }
}

/// Commits on one local day, counted once at their best confidence label.
///
/// This is the view that exists because summing `app_session_list` over a day counts a commit
/// twice when two sessions are both credited with it. `commits` is the count, and
/// `commits_fact` plus `commits_inferred` is the same count split by how it was established.
public struct AppCommitsByDayRow: Codable, FetchableRecord, Equatable, Sendable {
    public let day: String
    public let repoKey: String?
    public let project: String
    public let commits: Int
    public let commitsFact: Int
    public let commitsInferred: Int

    enum CodingKeys: String, CodingKey {
        case day
        case repoKey = "repo_key"
        case project
        case commits
        case commitsFact = "commits_fact"
        case commitsInferred = "commits_inferred"
    }
}

public struct AppSessionListRow: Codable, FetchableRecord, Equatable, Sendable {
    public let sessionId: String
    public let repoKey: String?
    public let project: String
    public let startedAt: String?
    public let endedAt: String?
    public let purpose: String?
    public let totalTokens: Int?
    public let commitsFact: Int
    public let commitsInferred: Int
    public let commitsUncertain: Int
    public let coverage: Double?
    public let sittings: Int
    public let captureLevel: String?
    public let contentArchived: Int
    /// Edits this session made. Optional because a session the hooks did not see has none,
    /// and a missing count is not a zero (ARCHITECTURE rule 10).
    public let edits: Int?

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case repoKey = "repo_key"
        case project
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case purpose
        case totalTokens = "total_tokens"
        case commitsFact = "commits_fact"
        case commitsInferred = "commits_inferred"
        case commitsUncertain = "commits_uncertain"
        case coverage
        case sittings
        case captureLevel = "capture_level"
        case contentArchived = "content_archived"
        case edits
    }

    /// Commits this session is credited with at a confidence the CLI counts.
    /// `uncertain` is reported separately by the engine and never folded in.
    public var countedCommits: Int { commitsFact + commitsInferred }
}

/// One stored review, through `app_review`.
///
/// At contract 1 the app read the raw `review` table for a headline and nothing else, because
/// there was no view; contract 2 has one, and the review screen reads the whole row from it.
/// `sections` and `numbers` are the JSON `reviews/build.py` stored, decoded by
/// `PrudenceModels/ReviewPayload.swift` rather than here: a row is a row, and what is inside a
/// text column is the model layer's problem.
///
/// `repoKey` is the hash the row was scoped by; `project` is the name a person uses for it.
/// Both are nil for a review of every project.
public struct AppReviewRow: Codable, FetchableRecord, Equatable, Sendable {
    public let id: Int
    public let createdAt: String
    public let rangeStart: String
    public let rangeEnd: String
    public let outcomeRangeStart: String?
    public let outcomeRangeEnd: String?
    public let repoKey: String?
    public let project: String?
    public let headline: String?
    public let sections: String
    public let numbers: String?
    public let coverage: Double?
    public let segmentText: String?
    public let segmentModel: String?
    public let segmentCreatedAt: String?
    /// The language `--language` asked the model to write in, at contract 3. Nil on a
    /// contract 2 store and on a row written before the column existed, where
    /// `ReviewText.segmentLanguage` reads it off the prose instead.
    public let segmentLanguage: String?

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case rangeStart = "range_start"
        case rangeEnd = "range_end"
        case outcomeRangeStart = "outcome_range_start"
        case outcomeRangeEnd = "outcome_range_end"
        case repoKey = "repo_key"
        case project
        case headline
        case sections
        case numbers
        case coverage
        case segmentText = "segment_text"
        case segmentModel = "segment_model"
        case segmentCreatedAt = "segment_created_at"
        case segmentLanguage = "segment_language"
    }
}
