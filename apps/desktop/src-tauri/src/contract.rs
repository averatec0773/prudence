//! The read contract, as data.
//!
//! `src/prudence/store/app_views.py` says it plainly: *"These lists are what the app
//! compiles against and what the tests assert; a view's SELECT may be rewritten freely
//! as long as it still answers with these columns, and changing one of them is what
//! bumps `meta.APP_CONTRACT_VERSION`."* This is the other side of that sentence.
//!
//! **This build reads contract 5 and nothing else.** Source provenance and model names
//! are part of the session list, and source membership has its own view.
//!
//! A test asserts that each view still answers with exactly these columns in this order,
//! so a Python change that forgets to bump the version fails here rather than in front
//! of the user.

/// The contract versions this build renders.
pub const SUPPORTED: &[u32] = &[5];

/// One view: its name, and the columns it must answer with, in order.
pub struct View {
    pub name: &'static str,
    pub columns: &'static [&'static str],
}

/// The nine views. `app_session_time` and `app_observation_text` are
/// helper tables that `app_views.py` marks explicitly as "not contract".
pub const VIEWS: &[View] = &[
    View {
        name: "app_status",
        columns: &[
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
            // Contract 4.
            "bucket_rule_version",
            "coverage_gap_tokens",
        ],
    },
    View {
        name: "app_usage_by_bucket_day",
        columns: &[
            "day",
            "repo_key",
            "project",
            "bucket",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
            "total_tokens",
            "responses",
            "heuristic_tokens",
            "sessions",
        ],
    },
    View {
        name: "app_activity_by_day",
        columns: &[
            "day",
            "repo_key",
            "project",
            "active_minutes",
            "sessions",
            "measured_sessions",
        ],
    },
    View {
        name: "app_outcomes_by_week",
        columns: &[
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
    },
    View {
        name: "app_commits_by_day",
        columns: &[
            "day",
            "repo_key",
            "project",
            "commits",
            "commits_fact",
            "commits_inferred",
        ],
    },
    View {
        name: "app_observation",
        columns: &[
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
            // Contract 2, appended rather than inserted.
            "observation_id",
            "sentence",
            // Contract 3.
            "threshold_value",
            "threshold_op",
        ],
    },
    View {
        name: "app_session_sources",
        columns: &["session_id", "source_id", "kind", "label", "home"],
    },
    View {
        name: "app_session_list",
        columns: &[
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
            // Contract 2.
            "edits",
            // Contract 4.
            "change_share",
            "run_share",
            "read_share",
            "talk_share",
            "source",
            "source_ids",
            "source_labels",
            "models",
        ],
    },
    View {
        name: "app_review",
        columns: &[
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
            // Contract 3.
            "segment_language",
        ],
    },
];
