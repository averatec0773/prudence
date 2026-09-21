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
    public let repoKey: String
    public let project: String?
    public let pooled: Int
    public let fact: String
    public let thresholdText: String
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

    enum CodingKeys: String, CodingKey {
        case repoKey = "repo_key"
        case project
        case pooled
        case fact
        case thresholdText = "threshold_text"
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
    }

    public var isPooled: Bool { pooled != 0 }
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
    }

    /// Commits this session is credited with at a confidence the CLI counts.
    /// `uncertain` is reported separately by the engine and never folded in.
    public var countedCommits: Int { commitsFact + commitsInferred }
}

/// The newest `review` row, read for its headline alone.
///
/// This is the one read that is not an `app_*` view, because there is no `app_review` view in
/// contract 1 (see the contract requests in `apps/mac/README.md`). It stays a headline: the id,
/// the range, the scope and the title of the first section, never the sections themselves. The
/// review screen in M3 task 8 needs the whole row and should get a view first.
public struct ReviewHeadlineRow: Codable, FetchableRecord, Equatable, Sendable {
    public let id: Int
    public let createdAt: String
    public let rangeStart: String
    public let rangeEnd: String
    public let project: String?
    public let sections: String

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case rangeStart = "range_start"
        case rangeEnd = "range_end"
        case project
        case sections
    }
}
