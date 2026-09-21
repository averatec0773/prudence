import Foundation

/// The read contract, copied from `src/prudence/store/app_views.py` (`APP_VIEWS`).
///
/// The app owns no numbers (M3 rule 8, ARCHITECTURE rule 14). Every figure on a screen comes
/// from one of these five views or from a stored row; a screen that needs something else gets
/// a new view in Python, never a join in Swift. The column lists below are the compiled form
/// of that promise: a test reads `PRAGMA table_info` on a fixture store and asserts each view
/// still answers with exactly these names, in this order, so a change on the Python side that
/// forgets to bump the contract version fails here rather than in front of the user.
public enum Contract {

    /// The only `meta.app_contract_version` this build knows how to render.
    public static let version = "1"

    /// The key the engine writes that version under, in the shared `meta` table.
    public static let versionKey = "app_contract_version"

    public enum View: String, CaseIterable, Sendable {
        case status = "app_status"
        case usageByPurposeDay = "app_usage_by_purpose_day"
        case outcomesByWeek = "app_outcomes_by_week"
        case observation = "app_observation"
        case sessionList = "app_session_list"

        public var columns: [String] { Contract.columns[self] ?? [] }
    }

    public static let columns: [View: [String]] = [
        .status: [
            "engine_version",
            "last_ingest_at",
            "sessions",
            "projects",
            "app_contract_version",
            "parser_version",
            "purpose_rule_version",
            "commit_fact_version",
            "attribution_fact_version",
            "outcome_fact_version",
            "observation_fact_version",
            "hook_fact_version",
        ],
        .usageByPurposeDay: [
            "day",
            "repo_key",
            "project",
            "purpose",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
            "total_tokens",
            "active_minutes",
            "sessions",
            "measured_sessions",
        ],
        .outcomesByWeek: [
            "repo_key",
            "project",
            "week_start",
            "commits",
            "commits_fact",
            "commits_inferred",
            "lines",
            "measured_7d",
            "alive_7d",
            "measured_30d",
            "alive_30d",
            "measured_90d",
            "alive_90d",
            "alive_head",
            "alive_head_anywhere",
            "blame_head",
            "reworked",
            "coverage",
        ],
        .observation: [
            "repo_key",
            "project",
            "pooled",
            "fact",
            "threshold_text",
            "outcome",
            "direction",
            "with_n",
            "without_n",
            "with_value",
            "without_value",
            "coverage",
            "fact_commits",
            "inferred_commits",
            "fact_version",
        ],
        .sessionList: [
            "session_id",
            "repo_key",
            "project",
            "started_at",
            "ended_at",
            "purpose",
            "total_tokens",
            "commits_fact",
            "commits_inferred",
            "commits_uncertain",
            "coverage",
            "sittings",
            "capture_level",
            "content_archived",
        ],
    ]
}
