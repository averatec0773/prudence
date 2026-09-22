//! The read side of the contract.
//!
//! The app owns no numbers. This module opens the store read-only, refuses a contract
//! version it does not understand, selects from `app_*` views and nothing else, and hands
//! the page one JSON payload. A median, a threshold or an attribution would be a new view
//! in `src/prudence/store/app_views.py`, never a function here.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};

use rusqlite::{types::ValueRef, Connection, OpenFlags};
use serde::Serialize;
use serde_json::{json, Map, Value};

use crate::contract;

/// The contract versions this build renders. The list, and the column tables behind it,
/// are in `contract.rs`.
pub fn supported_contract() -> Vec<u32> {
    contract::SUPPORTED.to_vec()
}

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
        contract::SUPPORTED
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

/// An override from the environment, with `~` expanded.
///
/// The engine's `paths.py` does `Path(override).expanduser()`. Anywhere a shell is not
/// the one setting the variable (a plist, a launchd `EnvironmentVariables`, a runner
/// reading a file) the value arrives with the tilde intact, and without this the engine
/// ingests into `/Users/someone/stores/copy` while the app reports no store at a literal
/// directory called `~`. The whole reason this variable is honoured is that the two can
/// never disagree about which store is which.
fn env_path(key: &str) -> Option<PathBuf> {
    std::env::var_os(key)
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
        .map(expand_tilde)
}

/// One rule, in one place: `engine.rs` needs the same expansion for the path a user
/// chooses for the executable and for the directories it searches.
fn expand_tilde(path: PathBuf) -> PathBuf {
    crate::engine::expand_tilde(path, &raw_home())
}

/// The home directory, read without going back through [`env_path`], which would recurse.
fn raw_home() -> PathBuf {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("."))
}

fn home() -> PathBuf {
    raw_home()
}

/// A view's answer as the page wants it: the column names once, then the rows.
/// `derive.js` turns this back into objects, which is how the mockups already read it.
#[derive(Serialize)]
struct Block {
    columns: Vec<String>,
    rows: Vec<Vec<Value>>,
}

/// Can the store be read right now?
///
/// The watcher's question. It used to be answered by calling [`read`] and dropping the
/// result, which pulled seven views across and threw them away before each page pulled
/// the same thing again, so it became "ask the contract row" instead.
///
/// **That was not the same question, and the difference is visible during an ingest.**
/// The engine drops and recreates the `app_*` views while it rebuilds them, and
/// `meta.app_contract_version` is a row in a table that survives the whole operation. So
/// the probe passed, the watcher announced a change, every page re-read, and every page
/// showed "The store could not be read: no such table: app_status". Seen by pressing
/// Ingest now in a running app for the first time, on 2026-09-21.
///
/// So it asks both: the contract row, and that every view the contract names exists. That
/// is one query against `sqlite_master` and it is the condition the pages actually need.
pub fn readable(path: &Path) -> Result<u32, StoreError> {
    if !path.exists() {
        return Err(StoreError::Missing(path.to_path_buf()));
    }
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|error| StoreError::Open(error.to_string()))?;
    let contract = contract_version(&connection)?;

    let present: std::collections::HashSet<String> = connection
        .prepare("SELECT name FROM sqlite_master WHERE name LIKE 'app\\_%' ESCAPE '\\'")
        .and_then(|mut statement| {
            statement
                .query_map([], |row| row.get::<_, String>(0))?
                .collect::<Result<_, _>>()
        })
        .map_err(read_error)?;

    if let Some(view) = contract::VIEWS
        .iter()
        .find(|view| !present.contains(view.name))
    {
        return Err(StoreError::Read(format!(
            "the store is mid-rebuild: {} is not there yet",
            view.name
        )));
    }
    Ok(contract)
}

/* --- one copy of the store's answer ---------------------------------------------------
 *
 * ## What this replaced
 *
 * Every page asked the shell for the store on its own, and a page's only way to update
 * was to rebuild itself whole. On the founder's 851 MB store that cost, measured on
 * 2026-09-22 with `PRUDENCE_MEASURE=1`:
 *
 * - **1,225 ms twice at launch.** The panel and the window load together and both ask, so
 *   the seven views were computed twice against one file, concurrently, for one answer.
 * - **440 ms twice, plus two whole-page rebuilds, for nothing.** Asking the engine whether
 *   a review is ready opens the store read-write; SQLite checkpoints the write-ahead log
 *   when that connection closes; the checkpoint moves the size and modification time of
 *   `prudence.db` and `-wal`, which is exactly what `watcher.rs` fingerprints. The watcher
 *   announces, both pages re-read, and every figure they then draw is the one already on
 *   screen.
 *
 * ## The rule
 *
 * The shell reads the store **once per change**, and says which answer this is. A page
 * that is handed the revision it already drew draws nothing (`src/store/drawn.js`).
 *
 * The invalidation is the watcher's, and it is the only one, because the watcher is
 * already the app's whole notion of the store having moved: nothing redraws without it.
 * Marking stale **before** the read rather than after is what makes a write landing
 * mid-read count: the flag is set again by the watcher and the next ask re-reads. A read
 * that fails is not remembered at all, so a store caught mid-rebuild is retried rather
 * than cached as an error.
 */

/// The answer, and which answer it is.
struct Snapshot {
    /// Bumped only when the payload actually differs from the one before it. A checkpoint
    /// that moved the files without changing a figure keeps the number it had.
    revision: u64,
    payload: Value,
}

fn cache() -> &'static Mutex<Option<Snapshot>> {
    static CACHE: OnceLock<Mutex<Option<Snapshot>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(None))
}

/// Whether the next ask has to go to the file. True to begin with: nothing has been read.
static STALE: AtomicBool = AtomicBool::new(true);

/// The store moved. Called by `watcher.rs` immediately before it announces.
pub fn invalidate() {
    STALE.store(true, Ordering::SeqCst);
}

/// The store's answer, read from the file only when it has moved since the last one.
///
/// The payload carries `revision`, which is what a page compares against what it drew.
pub fn snapshot(path: &Path) -> Result<Value, StoreError> {
    let mut held = cache().lock().unwrap();
    if !STALE.load(Ordering::SeqCst) {
        if let Some(found) = held.as_ref() {
            return Ok(found.payload.clone());
        }
    }
    // Before the read, not after it: a write that lands while this one is going sets the
    // flag again, and the next ask re-reads rather than trusting what was half-written.
    STALE.store(false, Ordering::SeqCst);

    let fresh = match read(path) {
        Ok(value) => value,
        Err(error) => {
            // Not remembered. A store caught mid-rebuild answers with an error, and an
            // error kept in this cache would be handed to every page until the next file
            // event rather than being retried.
            STALE.store(true, Ordering::SeqCst);
            return Err(error);
        }
    };

    let revision = match held.as_ref() {
        // The same figures as last time. The revision does not move, so no page redraws.
        Some(previous) if same(&previous.payload, &fresh) => previous.revision,
        Some(previous) => previous.revision + 1,
        None => 1,
    };
    let mut payload = fresh;
    if let Some(object) = payload.as_object_mut() {
        object.insert("revision".into(), json!(revision));
    }
    *held = Some(Snapshot {
        revision,
        payload: payload.clone(),
    });
    Ok(payload)
}

/// Are these the same figures? The stored payload carries `revision` and the fresh one
/// does not yet, so that key is the one thing not compared.
fn same(stored: &Value, fresh: &Value) -> bool {
    let (Some(stored), Some(fresh)) = (stored.as_object(), fresh.as_object()) else {
        return stored == fresh;
    };
    stored.len() == fresh.len() + 1
        && fresh
            .iter()
            .all(|(key, value)| stored.get(key).is_some_and(|had| had == value))
}

/// Forget what was read. For the tests, and for nothing else: the app has one store.
#[cfg(test)]
fn forget() {
    *cache().lock().unwrap() = None;
    STALE.store(true, Ordering::SeqCst);
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

    // Every view, with the columns its contract version has. Generated from the
    // contract rather than hand-written, so a column added in Python and listed in
    // `contract.rs` is selected here without a second edit, and so the two cannot drift.
    let mut blocks = Map::new();
    for view in contract::VIEWS {
        let columns = contract::columns_at(view.name, contract);
        let sql = format!("SELECT {} FROM {}", columns.join(", "), view.name);
        blocks.insert(
            view.name.to_string(),
            serde_json::to_value(block(&connection, &sql)?).unwrap(),
        );
    }

    // `app_status` is one row, and every page reads it as an object rather than as a
    // block of one.
    let status = blocks
        .get("app_status")
        .and_then(first_object)
        .unwrap_or(Value::Null);

    // The projects a surface can pick between, which is a distinct over one view rather
    // than a view of its own.
    let projects = rows(
        &connection,
        "SELECT DISTINCT repo_key AS key, project AS name FROM app_usage_by_purpose_day \
         ORDER BY project",
    )?;

    let engine_version = status
        .get("engine_version")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    Ok(json!({
        "source": path.display().to_string(),
        "engine_version": engine_version,
        "app_contract_version": contract,
        "status": status,
        "projects": projects,
        "usage": blocks.get("app_usage_by_purpose_day"),
        "outcomes": blocks.get("app_outcomes_by_week"),
        "commits": blocks.get("app_commits_by_day"),
        "sessions": blocks.get("app_session_list"),
        "observations": blocks.get("app_observation"),
        "reviews": blocks.get("app_review"),
    }))
}

/// The contract check, and the one place a table rather than a view is read: it is the
/// question "may I read the views at all", which the views themselves cannot answer for a
/// store older than the column that carries it.
fn contract_version(connection: &Connection) -> Result<u32, StoreError> {
    // `QueryReturnedNoRows` is a contract answer: this store predates the column. Any
    // other error is the file being unreadable, and telling somebody to upgrade their
    // engine because the database is corrupt sends them to fix the wrong thing.
    let found: Option<String> = match connection.query_row(
        "SELECT value FROM meta WHERE key = 'app_contract_version'",
        [],
        |row| row.get(0),
    ) {
        Ok(value) => Some(value),
        Err(rusqlite::Error::QueryReturnedNoRows) => None,
        Err(error) => return Err(StoreError::Read(error.to_string())),
    };

    let Some(found) = found else {
        return Err(StoreError::Contract {
            found: "none".into(),
            supported: StoreError::supported_list(),
        });
    };

    let parsed = found.trim().parse::<u32>().ok();
    match parsed {
        Some(version) if contract::SUPPORTED.contains(&version) => Ok(version),
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

/// The first row of a `{columns, rows}` block, as an object. `app_status` is one row and
/// every page reads it as an object rather than as a block of one.
fn first_object(value: &Value) -> Option<Value> {
    let columns = value.get("columns")?.as_array()?;
    let row = value.get("rows")?.as_array()?.first()?.as_array()?;
    let mut object = Map::new();
    for (name, cell) in columns.iter().zip(row) {
        object.insert(name.as_str()?.to_string(), cell.clone());
    }
    Some(Value::Object(object))
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

    /// The fixture the engine wrote (`tests/mac_fixture.py`), so the shell is judged
    /// against the engine's own output.
    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/store.db")
    }

    #[test]
    fn the_fixture_is_a_contract_this_build_reads() {
        let connection = Connection::open_with_flags(
            fixture(),
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .expect("fixture opens");
        let version = contract_version(&connection).expect("a supported contract");
        assert!(contract::SUPPORTED.contains(&version));
    }

    #[test]
    fn every_block_the_page_reads_answers() {
        let payload = read(&fixture()).expect("the fixture reads");
        // Not `.is_some()`: `json!` serialises a missing block to `Value::Null` and
        // **still inserts the key**, so that assertion held for every key whatever
        // happened. Rename a view in `contract.rs` and it stayed green while the screen
        // went blank. The shape is the thing the page needs.
        for key in [
            "usage",
            "outcomes",
            "commits",
            "sessions",
            "observations",
            "reviews",
        ] {
            let block = &payload[key];
            assert!(
                block["columns"].is_array() && block["rows"].is_array(),
                "payload block {key} is {block}"
            );
        }
        assert!(payload["status"].is_object(), "status is not an object");
        assert!(payload["projects"].is_array(), "projects is not an array");
        assert!(
            !payload["usage"]["rows"].as_array().unwrap().is_empty(),
            "the fixture has usage rows"
        );
    }

    #[test]
    fn a_store_override_expands_a_leading_tilde() {
        // The engine's `paths.py` expands it, so a value that arrives from a plist or a
        // launchd environment must land in the same directory for both.
        let home = super::raw_home();
        assert_eq!(super::expand_tilde(PathBuf::from("~")), home);
        assert_eq!(
            super::expand_tilde(PathBuf::from("~/stores/copy")),
            home.join("stores/copy")
        );
        // Only a leading `~/`, and never inside a name.
        assert_eq!(
            super::expand_tilde(PathBuf::from("/tmp/~/copy")),
            PathBuf::from("/tmp/~/copy")
        );
        assert_eq!(
            super::expand_tilde(PathBuf::from("~copy")),
            PathBuf::from("~copy")
        );
    }

    /// The columns a **contract 2** store answers with, written out here rather than
    /// derived from `contract::ADDED_AT_3`.
    ///
    /// That is the whole point of the test below. Asserting `columns_at(name, 2)` against
    /// the constant it is implemented from proves only that the constant is itself, and
    /// until now nothing opened a contract-2 database at all: the fixture is contract 3,
    /// so `columns_at(name, 2)` was dead code everywhere except in an assertion about
    /// itself. If `ADDED_AT_3` were missing an entry, the first person to find out would
    /// be a user on an older engine.
    ///
    /// These two lists are the independent statement. They come from `app_views.py` at
    /// the commit that introduced contract 3, reading what the columns were *before* it.
    const OBSERVATION_AT_2: &[&str] = &[
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
    ];
    const REVIEW_AT_2: &[&str] = &[
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
    ];

    /// A contract-2 store, built rather than committed: a binary fixture would drift and
    /// nobody would notice until it mattered.
    fn contract_two_store(directory: &Path) -> PathBuf {
        let path = directory.join("prudence.db");
        let connection = Connection::open(&path).expect("a new database");
        connection
            .execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)", [])
            .expect("meta");
        connection
            .execute("INSERT INTO meta VALUES ('app_contract_version', '2')", [])
            .expect("the version");

        for view in contract::VIEWS {
            let columns: Vec<&str> = match view.name {
                "app_observation" => OBSERVATION_AT_2.to_vec(),
                "app_review" => REVIEW_AT_2.to_vec(),
                other => contract::view(other).unwrap().columns.to_vec(),
            };
            let spec = columns
                .iter()
                .map(|column| format!("\"{column}\" TEXT"))
                .collect::<Vec<_>>()
                .join(", ");
            connection
                .execute(&format!("CREATE TABLE {} ({spec})", view.name), [])
                .expect("a view");
            let values = columns.iter().map(|_| "'x'").collect::<Vec<_>>().join(", ");
            connection
                .execute(&format!("INSERT INTO {} VALUES ({values})", view.name), [])
                .expect("a row");
        }
        path
    }

    /// The probe must fail while the engine is rebuilding the views, because the pages
    /// will fail if it does not.
    ///
    /// Pressing Ingest now in a running app for the first time showed every page reading
    /// "The store could not be read: no such table: app_status". The watcher had
    /// announced a change because the probe only asked the contract row, and
    /// `meta.app_contract_version` is a row in a table that survives a view rebuild.
    #[test]
    fn a_store_whose_views_are_mid_rebuild_is_not_readable() {
        let directory =
            std::env::temp_dir().join(format!("prudence-rebuild-{}", std::process::id()));
        std::fs::create_dir_all(&directory).expect("a scratch directory");
        let path = contract_two_store(&directory);

        // It reads to begin with: `contract_two_store` builds every view.
        assert!(readable(&path).is_ok(), "the built store does not read");

        // Now drop one, which is what an ingest does to all of them for a moment.
        let connection = Connection::open(&path).expect("open for writing");
        connection
            .execute("DROP TABLE app_status", [])
            .expect("drop a view");
        drop(connection);

        let error = readable(&path).expect_err("a store with no app_status must not read");
        let message = format!("{error}");
        assert!(
            message.contains("app_status"),
            "the error does not name the missing view: {message}"
        );
        // And the contract row is still there, which is exactly why asking only for it
        // was not enough.
        let connection = Connection::open(&path).expect("open again");
        assert_eq!(contract_version(&connection).ok(), Some(2));

        std::fs::remove_dir_all(&directory).ok();
    }

    /// The contract-2 path, exercised against an actual database.
    #[test]
    fn a_contract_two_store_reads_without_the_columns_it_does_not_have() {
        let directory =
            std::env::temp_dir().join(format!("prudence-contract-2-{}", std::process::id()));
        std::fs::create_dir_all(&directory).expect("a scratch directory");
        let path = contract_two_store(&directory);

        let payload = read(&path).expect("a contract 2 store reads");
        assert_eq!(payload["app_contract_version"], 2);

        let columns = |block: &str| -> Vec<String> {
            payload[block]["columns"]
                .as_array()
                .unwrap()
                .iter()
                .map(|value| value.as_str().unwrap().to_string())
                .collect()
        };
        assert_eq!(columns("observations"), OBSERVATION_AT_2);
        assert_eq!(columns("reviews"), REVIEW_AT_2);
        // And the three that arrived at contract 3 really are the ones left out.
        for (view, column) in contract::ADDED_AT_3 {
            let block = match *view {
                "app_observation" => "observations",
                "app_review" => "reviews",
                other => panic!("no block for {other}"),
            };
            assert!(
                !columns(block).iter().any(|have| have == column),
                "{column} should not be selected from a contract 2 store"
            );
        }

        std::fs::remove_dir_all(&directory).ok();
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

    /// The whole point of the contract being a list: a Python change that adds, removes
    /// or reorders a column and forgets to bump `meta.APP_CONTRACT_VERSION` fails here
    /// rather than in front of the user.
    #[test]
    fn every_view_answers_with_exactly_the_columns_the_contract_lists() {
        let connection = Connection::open_with_flags(
            fixture(),
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .unwrap();
        for view in contract::VIEWS {
            let statement = connection
                .prepare(&format!("SELECT * FROM {}", view.name))
                .unwrap_or_else(|error| panic!("{}: {error}", view.name));
            let actual: Vec<String> = statement
                .column_names()
                .into_iter()
                .map(str::to_string)
                .collect();
            let expected: Vec<String> = view.columns.iter().map(|c| c.to_string()).collect();
            assert_eq!(actual, expected, "{} answers with other columns", view.name);
        }
    }

    /// Contract 3 is additive, so a contract-2 store is read by selecting the columns
    /// that existed then. If this list is wrong, a 2 store fails at the first select.
    #[test]
    fn a_contract_two_store_is_selected_without_the_columns_three_added() {
        let at_two = contract::columns_at("app_observation", 2);
        let at_three = contract::columns_at("app_observation", 3);
        assert!(!at_two.contains(&"threshold_value"));
        assert!(at_three.contains(&"threshold_value"));
        assert_eq!(at_three.len(), at_two.len() + 2);
        assert!(!contract::columns_at("app_review", 2).contains(&"segment_language"));
    }

    /// Seven, not the eleven an earlier note claimed: `app_session_time` and
    /// `app_observation_text` are helper tables and `app_views.py` says they are not
    /// contract.
    #[test]
    fn the_contract_is_the_seven_views_the_engine_publishes() {
        assert_eq!(contract::VIEWS.len(), 7);
        for view in contract::VIEWS {
            assert!(view.name.starts_with("app_"));
            assert!(!view.columns.is_empty());
        }
    }

    #[test]
    fn a_missing_store_says_so_rather_than_panicking() {
        let error = read(Path::new("/nonexistent/prudence.db")).unwrap_err();
        assert!(matches!(error, StoreError::Missing(_)));
    }

    /* --- the one copy of the answer ---------------------------------------------------
     *
     * These share one process-wide cache, so they are one test: `cargo test` runs the
     * module's tests on several threads and two of these interleaved would be asserting
     * against each other's snapshot rather than against the store.
     */

    /// The whole rule, in the order it has to hold.
    ///
    /// Each step is the defect it exists to stop, and the middle one is the measured one:
    /// asking the engine whether a review is ready checkpoints the write-ahead log, which
    /// moves the two files `watcher.rs` fingerprints, so the watcher announces a change to
    /// a store whose figures are identical. Before this the announcement cost two 440 ms
    /// reads and two whole-page rebuilds for figures already on the screen.
    #[test]
    fn the_store_is_read_once_per_change_and_says_which_answer_it_is() {
        let directory =
            std::env::temp_dir().join(format!("prudence-snapshot-{}", std::process::id()));
        std::fs::create_dir_all(&directory).expect("a scratch directory");
        let path = contract_two_store(&directory);
        forget();

        // One read, and the answer says it is the first.
        let first = snapshot(&path).expect("the store reads");
        assert_eq!(first["revision"], 1);

        // A second ask with nothing changed is the same answer, and did not touch the
        // file: the proof is that a store deleted from under it still answers.
        std::fs::rename(&path, directory.join("moved.db")).expect("move the store aside");
        let again = snapshot(&path).expect("the snapshot answers without the file");
        assert_eq!(again, first);
        std::fs::rename(directory.join("moved.db"), &path).expect("put it back");

        // The watcher announced. The file is read again, and because nothing in it
        // changed the revision does not move, so no page redraws.
        invalidate();
        let unchanged = snapshot(&path).expect("the store reads");
        assert_eq!(unchanged["revision"], 1, "a checkpoint is not a change");
        assert_eq!(unchanged, first);

        // Something really changed. The revision moves, and that is what makes a page draw.
        let connection = Connection::open(&path).expect("open for writing");
        connection
            .execute("UPDATE app_status SET sessions = '99'", [])
            .expect("change a figure");
        drop(connection);
        invalidate();
        let moved = snapshot(&path).expect("the store reads");
        assert_eq!(moved["revision"], 2);
        assert_eq!(moved["status"]["sessions"], "99");

        // A store that will not read is not remembered as an error: the next ask tries
        // again, which is what a store caught mid-rebuild needs.
        std::fs::remove_file(&path).expect("remove the store");
        invalidate();
        assert!(snapshot(&path).is_err(), "a missing store must not answer");
        assert!(
            STALE.load(Ordering::SeqCst),
            "a failed read left the snapshot looking fresh, so the error would be cached"
        );

        std::fs::remove_dir_all(&directory).ok();
    }
}
