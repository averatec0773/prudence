//! The read contract, as data.
//!
//! `src/prudence/store/app_views.py` says it plainly: *"These lists are what the app
//! compiles against and what the tests assert; a view's SELECT may be rewritten freely
//! as long as it still answers with these columns, and changing one of them is what
//! bumps `meta.APP_CONTRACT_VERSION`."* This is the other side of that sentence.
//!
//! **Contract 3 is additive over 2**, so both are drawn from one code path: every column
//! 3 added is read as an optional and used only where it is present, and the app and the
//! engine can be upgraded in either order.
//!
//! A test asserts that each view still answers with exactly these columns in this order,
//! so a Python change that forgets to bump the version fails here rather than in front
//! of the user.

/// The contract versions this build renders.
pub const SUPPORTED: &[u32] = &[2, 3];

/// One view: its name, and the columns it must answer with, in order.
pub struct View {
    pub name: &'static str,
    pub columns: &'static [&'static str],
}

/// The seven views. Not eleven: `app_session_time` and `app_observation_text` are
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
        ],
    },
    View {
        name: "app_usage_by_purpose_day",
        columns: &[
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

/// The columns a contract-2 store does not have. Everything here is read as an optional
/// and a null stays a null, which is what "additive" has to mean in practice.
pub const ADDED_AT_3: &[(&str, &str)] = &[
    ("app_observation", "threshold_value"),
    ("app_observation", "threshold_op"),
    ("app_review", "segment_language"),
];

pub fn view(name: &str) -> Option<&'static View> {
    VIEWS.iter().find(|view| view.name == name)
}

/// The columns to select from a view at a given contract version: all of them at 3, and
/// at 2 the ones that existed then.
pub fn columns_at(name: &str, version: u32) -> Vec<&'static str> {
    let Some(view) = view(name) else {
        return Vec::new();
    };
    view.columns
        .iter()
        .copied()
        .filter(|column| version >= 3 || !ADDED_AT_3.iter().any(|(v, c)| *v == name && c == column))
        .collect()
}
