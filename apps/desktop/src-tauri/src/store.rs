//! The read side of the contract.
//!
//! The app owns no numbers. This module opens the store read-only, refuses a contract
//! version it does not understand, selects from `app_*` views and nothing else, and hands
//! the page one JSON payload. A median, a threshold or an attribution would be a new view
//! in `src/prudence/store/app_views.py`, never a function here.

use std::path::{Path, PathBuf};

use rusqlite::{types::ValueRef, Connection, OpenFlags};
use serde::Serialize;
use serde_json::{json, Map, Value};

/// The contract versions this build renders. Version 3 is additive over 2, so both are
/// drawn from one code path and every column 3 added is read as optional.
pub const SUPPORTED_CONTRACT: &[i64] = &[2, 3];

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("No store at {0}. Run `prudence ingest` first.")]
    Missing(PathBuf),
    #[error("The store could not be opened: {0}")]
    Open(String),
    #[error(
        "This store is at contract version {found}; this app reads {supported}. \
         Update whichever of the two is older."
    )]
    Contract { found: String, supported: String },
    #[error("The store could not be read: {0}")]
    Read(String),
}

impl StoreError {
    fn supported_list() -> String {
        SUPPORTED_CONTRACT
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(" or ")
    }
}

/// Where the store lives, honouring the same environment variable `src/prudence/paths.py`
/// honours, so an app pointed at a copy can never read the real one.
pub fn database_file() -> PathBuf {
    data_dir().join("prudence.db")
}

fn data_dir() -> PathBuf {
    if let Some(dir) = env_path("PRUDENCE_DATA_DIR") {
        return dir;
    }
    #[cfg(target_os = "macos")]
    {
        home()
            .join("Library")
            .join("Application Support")
            .join("prudence")
    }
    #[cfg(target_os = "windows")]
    {
        // The engine has no Windows branch yet (`paths.py` falls through to the XDG one),
        // so this is the shell's guess and has to be agreed with the engine before the
        // Windows batches. It is written here rather than hidden in a default.
        std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home().join("AppData").join("Roaming"))
            .join("prudence")
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        env_path("XDG_DATA_HOME")
            .unwrap_or_else(|| home().join(".local").join("share"))
            .join("prudence")
    }
}

fn env_path(key: &str) -> Option<PathBuf> {
    std::env::var_os(key)
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
}

fn home() -> PathBuf {
    env_path("HOME")
        .or_else(|| env_path("USERPROFILE"))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// A view's answer as the page wants it: the column names once, then the rows.
/// `derive.js` turns this back into objects, which is how the mockups already read it.
#[derive(Serialize)]
struct Block {
    columns: Vec<String>,
    rows: Vec<Vec<Value>>,
}

pub fn read(path: &Path) -> Result<Value, StoreError> {
    if !path.exists() {
        return Err(StoreError::Missing(path.to_path_buf()));
    }

    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|error| StoreError::Open(error.to_string()))?;

    let contract = contract_version(&connection)?;

    let status = one_row(&connection, "SELECT * FROM app_status")?;
    let usage = block(
        &connection,
        "SELECT day, project, purpose, total_tokens, active_minutes, sessions, \
         measured_sessions FROM app_usage_by_purpose_day",
    )?;
    let outcomes = block(
        &connection,
        "SELECT project, week_start, commits, commits_fact, commits_inferred, lines, \
         measured_7d, alive_7d, measured_30d, alive_30d, measured_90d, alive_90d, \
         alive_head, reworked, coverage FROM app_outcomes_by_week",
    )?;
    let commits = block(
        &connection,
        "SELECT day, project, commits, commits_fact, commits_inferred FROM app_commits_by_day",
    )?;
    let projects = rows(
        &connection,
        "SELECT DISTINCT repo_key AS key, project AS name FROM app_usage_by_purpose_day \
         ORDER BY project",
    )?;
    // The view's own order, not one this shell invented: the dropdown shows the first
    // row, and `Snapshot.read` in the Swift app takes `observationRows.first` off the same
    // unordered select. A re-sort here would make the two apps disagree about which
    // observation is the latest one.
    let observations = rows(
        &connection,
        "SELECT observation_id AS id, project, pooled, fact, threshold_text, outcome, \
         direction, with_n, without_n, with_value, without_value, coverage, fact_commits, \
         inferred_commits, sentence AS sentence_en_engine FROM app_observation",
    )?;
    // Sessions are counted as rows of this view, never as a sum of
    // `app_usage_by_purpose_day.sessions`, which is per purpose per day.
    let sessions = block(
        &connection,
        "SELECT session_id, project, started_at, purpose, total_tokens, edits \
         FROM app_session_list",
    )?;
    let reviews = rows(
        &connection,
        "SELECT id, created_at, range_start, range_end, project, headline, coverage \
         FROM app_review ORDER BY created_at DESC",
    )?;

    let engine_version = status
        .get("engine_version")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    Ok(json!({
        "source": path.display().to_string(),
        "engine_version": engine_version,
        "app_contract_version": contract.to_string(),
        "status": status,
        "projects": projects,
        "usage": usage,
        "outcomes": outcomes,
        "commits": commits,
        "sessions": sessions,
        "observations": observations,
        "reviews": reviews,
    }))
}

/// The contract check, and the one place a table rather than a view is read: it is the
/// question "may I read the views at all", which the views themselves cannot answer for a
/// store older than the column that carries it.
fn contract_version(connection: &Connection) -> Result<i64, StoreError> {
    let found: Option<String> = connection
        .query_row(
            "SELECT value FROM meta WHERE key = 'app_contract_version'",
            [],
            |row| row.get(0),
        )
        .ok();

    let Some(found) = found else {
        return Err(StoreError::Contract {
            found: "none".into(),
            supported: StoreError::supported_list(),
        });
    };

    let parsed = found.trim().parse::<i64>().ok();
    match parsed {
        Some(version) if SUPPORTED_CONTRACT.contains(&version) => Ok(version),
        _ => Err(StoreError::Contract {
            found,
            supported: StoreError::supported_list(),
        }),
    }
}

fn block(connection: &Connection, sql: &str) -> Result<Block, StoreError> {
    let mut statement = connection.prepare(sql).map_err(read_error)?;
    let columns: Vec<String> = statement
        .column_names()
        .into_iter()
        .map(str::to_string)
        .collect();
    let width = columns.len();

    let mut collected = Vec::new();
    let mut cursor = statement.query([]).map_err(read_error)?;
    while let Some(row) = cursor.next().map_err(read_error)? {
        let mut out = Vec::with_capacity(width);
        for index in 0..width {
            out.push(cell(row, index)?);
        }
        collected.push(out);
    }

    Ok(Block {
        columns,
        rows: collected,
    })
}

fn rows(connection: &Connection, sql: &str) -> Result<Vec<Value>, StoreError> {
    let table = block(connection, sql)?;
    Ok(table
        .rows
        .into_iter()
        .map(|row| {
            let mut object = Map::new();
            for (name, value) in table.columns.iter().zip(row) {
                object.insert(name.clone(), value);
            }
            Value::Object(object)
        })
        .collect())
}

fn one_row(connection: &Connection, sql: &str) -> Result<Value, StoreError> {
    Ok(rows(connection, sql)?
        .into_iter()
        .next()
        .unwrap_or(Value::Null))
}

fn cell(row: &rusqlite::Row<'_>, index: usize) -> Result<Value, StoreError> {
    let raw = row.get_ref(index).map_err(read_error)?;
    Ok(match raw {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(value) => json!(value),
        ValueRef::Real(value) => json!(value),
        ValueRef::Text(value) => json!(String::from_utf8_lossy(value).to_string()),
        // No `app_*` column is a blob today. If one ever is, it is a payload the page has
        // no business decoding, so it arrives as null rather than as mangled text.
        ValueRef::Blob(_) => Value::Null,
    })
}

fn read_error(error: rusqlite::Error) -> StoreError {
    StoreError::Read(error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The fixture the Swift tests read, so both stacks are judged against one store.
    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db")
    }

    #[test]
    fn the_fixture_is_a_contract_this_build_reads() {
        let connection = Connection::open_with_flags(
            fixture(),
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .expect("fixture opens");
        let version = contract_version(&connection).expect("a supported contract");
        assert!(SUPPORTED_CONTRACT.contains(&version));
    }

    #[test]
    fn every_block_the_page_reads_answers() {
        let payload = read(&fixture()).expect("the fixture reads");
        for key in [
            "status",
            "projects",
            "usage",
            "outcomes",
            "commits",
            "sessions",
            "observations",
            "reviews",
        ] {
            assert!(payload.get(key).is_some(), "payload has no {key}");
        }
        assert!(
            !payload["usage"]["rows"].as_array().unwrap().is_empty(),
            "the fixture has usage rows"
        );
    }

    /// No figure on a screen may be one this shell invented: the payload's status block is
    /// the view's own row, column for column.
    #[test]
    fn the_status_block_is_the_views_own_row() {
        let payload = read(&fixture()).expect("the fixture reads");
        let status = &payload["status"];
        let connection = Connection::open_with_flags(
            fixture(),
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .unwrap();
        let sessions: i64 = connection
            .query_row("SELECT sessions FROM app_status", [], |row| row.get(0))
            .unwrap();
        assert_eq!(status["sessions"].as_i64(), Some(sessions));
    }

    #[test]
    fn a_missing_store_says_so_rather_than_panicking() {
        let error = read(Path::new("/nonexistent/prudence.db")).unwrap_err();
        assert!(matches!(error, StoreError::Missing(_)));
    }
}
