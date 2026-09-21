import Foundation

/// The read contract, copied from `src/prudence/store/app_views.py` (`APP_VIEWS`).
///
/// The app owns no numbers (M3 rule 8, ARCHITECTURE rule 14). Every figure on a screen comes
/// from one of these seven views or from a stored row; a screen that needs something else gets
/// a new view in Python, never a join in Swift. The column lists below are the compiled form
/// of that promise: a test reads `PRAGMA table_info` on a fixture store and asserts each view
/// still answers with exactly these names, in this order, so a change on the Python side that
/// forgets to bump the contract version fails here rather than in front of the user.
///
/// Contract 2 is what the main window needs and contract 1 could not give it, each addition
/// answering one of the three requests `apps/mac/README.md` recorded at contract 1 plus the
/// review screen's:
///
/// - `app_session_list.edits`, so the dropdown's "today" line can say edits without the app
///   counting the `edit` table itself.
/// - `app_commits_by_day`, so a day's commits are counted once. Summing `app_session_list`
///   double counts a commit credited to two sessions.
/// - `app_observation.sentence`, the prose the CLI prints, so no surface restates the phrase
///   table in `store/observations.py`. `observation_id` comes with it, so a row has an
///   identity a screen can select on.
/// - `app_review`, the stored reviews as a view, with the sections and the numbers as the JSON
///   `reviews/build.py` wrote and the model segment beside them.
public enum Contract {

    /// The only `meta.app_contract_version` this build knows how to render.
    public static let version = "2"

    /// The key the engine writes that version under, in the shared `meta` table.
    public static let versionKey = "app_contract_version"

    public enum View: String, CaseIterable, Sendable {
        case status = "app_status"
        case usageByPurposeDay = "app_usage_by_purpose_day"
        case outcomesByWeek = "app_outcomes_by_week"
        case observation = "app_observation"
        case sessionList = "app_session_list"
        case commitsByDay = "app_commits_by_day"
        case review = "app_review"

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
            "observation_id",
            "sentence",
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
            "edits",
        ],
        .commitsByDay: [
            "day",
            "repo_key",
            "project",
            "commits",
            "commits_fact",
            "commits_inferred",
        ],
        .review: [
            "id",
            "created_at",
            "range_start",
            "range_end",
            "outcome_range_start",
            "outcome_range_end",
            "repo_key",
            "project",
            "headline",
            "sections",
            "numbers",
            "coverage",
            "segment_text",
            "segment_model",
            "segment_created_at",
        ],
    ]
}
