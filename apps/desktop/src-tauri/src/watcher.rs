//! The window follows the store.
//!
//! Prudence is a recorder: `prudence ingest` runs while the app is open, and before this
//! the panel went on showing whatever the store said when the page loaded. On a product
//! whose whole claim is "it follows your work", a figure that is quietly an hour old is
//! the wrong kind of wrong.
//!
//! Three things make this harder than watching a file:
//!
//! 1. **SQLite does not write one file.** An ingest touches `prudence.db`, `-wal` and
//!    `-shm`, and a `VACUUM INTO` or a restore replaces the database outright. So the
//!    *directory* is watched and the events are filtered by name.
//! 2. **An ingest is many events.** A burst has to become one refresh, or the page
//!    redraws twenty times while the engine works.
//! 3. **The store is not readable in the middle of a write.** The only honest test for
//!    "the engine has finished" is that a read succeeds, so that is the test: the
//!    refresh is announced only after the shell has read the store cleanly.

use std::path::{Path, PathBuf};
use std::sync::mpsc::{channel, RecvTimeoutError};
use std::time::{Duration, Instant};

use notify::{Event, RecursiveMode, Watcher};
use tauri::{AppHandle, Emitter};

/// The event the pages listen for. They re-read through the bridge; the payload is
/// deliberately empty, so there is one way to get the store's contents and not two.
pub const STORE_CHANGED: &str = "store-changed";

/// How long the store has to be quiet before a read is attempted. An ingest writes in
/// bursts; this is long enough to let one finish and short enough that a person who ran
/// `prudence ingest` in a terminal sees the panel catch up while they are still looking
/// at it.
const QUIET: Duration = Duration::from_millis(750);

/// If the read fails the engine is probably still writing. Try again, a few times, and
/// then wait for the next event rather than spinning.
const RETRIES: u32 = 8;

/// Is this event about the store?
///
/// The engine keeps its config and its line-hash key in the same directory, and the
/// directory is what is watched, because SQLite writes `-wal` beside the database and a
/// restore replaces the database outright.
///
/// **Two names, not a prefix.** `-shm` is deliberately excluded: it is the shared-memory
/// index, and *a reader writes it*. A read-only connection to a WAL database stamps its
/// read mark into `-shm` on every read transaction, so treating it as evidence of a
/// change makes this watcher react to its own probe and to both pages' reads, forever.
/// A prefix would also match `prudence.db.bak` and `prudence.db.tmp`, which a backup or a
/// `VACUUM INTO` puts in this directory and which no figure depends on.
fn concerns_the_store(paths: &[PathBuf], database: &str) -> bool {
    if database.is_empty() {
        return false;
    }
    let wal = format!("{database}-wal");
    paths.iter().any(|path| {
        path.file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name == database || name == wal)
    })
}

/// What the store's own files look like right now: the size and modification time of the
/// database and of its write-ahead log, or `None` for one that is not there.
///
/// This is the answer to "did anything actually change", and it is asked because a file
/// event is not that answer. Measured on 2026-09-21: three read-only reads of a WAL store
/// left both files byte-identical, size and mtime, while one write changed them. So a
/// fingerprint that does not move means no ingest happened, whatever the file system said.
type Fingerprint = [Option<(u64, std::time::SystemTime)>; 2];

fn fingerprint(database: &Path) -> Fingerprint {
    let wal = database.with_file_name(format!(
        "{}-wal",
        database
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default()
    ));
    [database, wal.as_path()].map(|path| {
        std::fs::metadata(path)
            .ok()
            .and_then(|meta| Some((meta.len(), meta.modified().ok()?)))
    })
}

pub fn watch(app: &AppHandle, database: PathBuf) {
    let Some(directory) = database.parent().map(Path::to_path_buf) else {
        return;
    };
    let app = app.clone();

    std::thread::spawn(move || {
        let (tx, rx) = channel::<notify::Result<Event>>();
        let mut watcher = match notify::recommended_watcher(tx) {
            Ok(watcher) => watcher,
            Err(error) => {
                eprintln!("[watch] no watcher: {error}");
                return;
            }
        };
        if let Err(error) = watcher.watch(&directory, RecursiveMode::NonRecursive) {
            eprintln!("[watch] cannot watch {}: {error}", directory.display());
            return;
        }
        eprintln!("[watch] following {}", database.display());

        let name = database
            .file_name()
            .map(|n| n.to_owned())
            .unwrap_or_default();
        let mut due: Option<Instant> = None;
        let mut tries = 0;
        // What the store looks like once it has been opened the way we will keep opening
        // it. The open matters: a read-only connection to a WAL store *creates* `-wal` if
        // it is absent, so fingerprinting before the first open would record a state the
        // very next read destroys, and the app would announce a change nobody made.
        // Anything equal to this is not news, which is what stops it chasing its own reads.
        let _ = crate::store::readable(&database);
        let mut last = fingerprint(&database);

        loop {
            let timeout = due
                .map(|at| at.saturating_duration_since(Instant::now()))
                .unwrap_or(Duration::from_secs(3600));

            match rx.recv_timeout(timeout) {
                Ok(Ok(event)) => {
                    // The database and its journal files, and nothing else in a
                    // directory the engine also keeps a config and a key in.
                    if concerns_the_store(&event.paths, name.to_str().unwrap_or("")) {
                        due = Some(Instant::now() + QUIET);
                        tries = 0;
                    }
                }
                Ok(Err(error)) => eprintln!("[watch] {error}"),
                Err(RecvTimeoutError::Timeout) => {
                    if due.take().is_none() {
                        continue;
                    }
                    // Nothing actually moved: the event was somebody reading, including
                    // very possibly us. Say nothing, and do not read the store to find out.
                    let now = fingerprint(&database);
                    if now == last {
                        tries = 0;
                        continue;
                    }

                    // The read is the test. A store mid-write answers with an error, and
                    // announcing a refresh then would make every page draw the failure.
                    // It is the cheap read: the pages fetch the payload themselves, and
                    // pulling all seven views here only to drop them tripled the work.
                    match crate::store::readable(&database) {
                        Ok(_) => {
                            last = now;
                            tries = 0;
                            if let Err(error) = app.emit(STORE_CHANGED, ()) {
                                eprintln!("[watch] could not announce: {error}");
                            } else {
                                eprintln!("[watch] the store changed; the pages will re-read");
                            }
                        }
                        Err(error) => {
                            tries += 1;
                            if tries < RETRIES {
                                due = Some(Instant::now() + QUIET);
                            } else {
                                eprintln!("[watch] gave up after {tries} tries: {error}");
                            }
                        }
                    }
                }
                Err(RecvTimeoutError::Disconnected) => return,
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn paths(names: &[&str]) -> Vec<PathBuf> {
        names
            .iter()
            .map(|name| PathBuf::from("/store").join(name))
            .collect()
    }

    #[test]
    fn the_database_and_its_write_ahead_log_are_the_store() {
        assert!(concerns_the_store(&paths(&["prudence.db"]), "prudence.db"));
        assert!(concerns_the_store(
            &paths(&["prudence.db-wal"]),
            "prudence.db"
        ));
    }

    /// A reader writes `-shm`. Reacting to it made the app refresh every 750 ms forever
    /// against any WAL store, which is every store the engine produces.
    #[test]
    fn the_shared_memory_index_is_not_evidence_of_a_change() {
        assert!(!concerns_the_store(
            &paths(&["prudence.db-shm"]),
            "prudence.db"
        ));
    }

    /// A backup, a `VACUUM INTO` or a restore staging a temp file beside the target.
    #[test]
    fn a_file_that_merely_starts_with_the_name_is_not_the_store() {
        for name in [
            "prudence.db.bak",
            "prudence.db.tmp",
            "prudence.db2",
            "prudence.db-journal",
        ] {
            assert!(
                !concerns_the_store(&paths(&[name]), "prudence.db"),
                "{name} should not be the store"
            );
        }
    }

    /// The engine keeps its config and its line-hash key in the same directory. A
    /// refresh on either would redraw the page for something no figure depends on, and
    /// the key in particular is a file nothing in this app may react to.
    #[test]
    fn the_engines_other_files_are_not() {
        assert!(!concerns_the_store(&paths(&["config.toml"]), "prudence.db"));
        assert!(!concerns_the_store(
            &paths(&["line-hash.key"]),
            "prudence.db"
        ));
        assert!(!concerns_the_store(
            &paths(&["desktop-ui.json"]),
            "prudence.db"
        ));
    }

    #[test]
    fn one_matching_path_in_a_batch_is_enough() {
        assert!(concerns_the_store(
            &paths(&["config.toml", "prudence.db-wal"]),
            "prudence.db"
        ));
    }

    #[test]
    fn a_store_with_no_name_matches_nothing() {
        assert!(!concerns_the_store(&paths(&["prudence.db"]), ""));
    }
}
