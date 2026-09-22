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

/* --- the debounce, as a thing a test can drive -------------------------------------- */

/// What to do when the quiet period has elapsed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Step {
    /// Nothing to do: either nothing was pending, or nothing actually moved.
    Wait,
    /// The store changed and reads cleanly. Tell the pages.
    Announce,
    /// The store changed and will not read yet. Wait another quiet period.
    Retry,
    /// It has not read cleanly in [`RETRIES`] tries. Stop asking, and wait for the next
    /// file event.
    GiveUp,
}

/// The debounce's own state: whether a quiet period is pending, and how many reads of the
/// changed store have failed so far.
///
/// **It is a struct so that "does it re-arm" is a test rather than a claim.** The rule is
/// that every path out of [`Self::elapsed`] leaves this able to react to the next event,
/// including the two that end badly. Before this the whole loop was inline in a spawned
/// thread and the only way to ask the question was to run the app and watch a log.
#[derive(Debug, Default)]
pub struct Debounce {
    pending: bool,
    tries: u32,
}

impl Debounce {
    pub fn new() -> Self {
        Self::default()
    }

    /// A file event about the store arrived. The quiet period starts again from here, and
    /// the retry count with it: this is a new burst, not a continuation of an old one.
    pub fn touched(&mut self) {
        self.pending = true;
        self.tries = 0;
    }

    /// Is a quiet period running? The loop waits on it rather than on a fixed timeout.
    pub fn pending(&self) -> bool {
        self.pending
    }

    /// The quiet period is up. `changed` is whether the store's own files moved, and
    /// `readable` whether it could then be read.
    ///
    /// The fingerprint is asked before the read because a file event is not evidence that
    /// anything happened: a reader writes `-shm`, and the shell's own reads would
    /// otherwise make this chase itself forever.
    pub fn elapsed(&mut self, changed: bool, readable: bool) -> Step {
        if !self.pending {
            return Step::Wait;
        }
        self.pending = false;
        if !changed {
            self.tries = 0;
            return Step::Wait;
        }
        if readable {
            self.tries = 0;
            return Step::Announce;
        }
        self.tries += 1;
        if self.tries < RETRIES {
            self.pending = true;
            Step::Retry
        } else {
            Step::GiveUp
        }
    }
}

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
        let mut debounce = Debounce::new();
        let mut due: Option<Instant> = None;
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
                        debounce.touched();
                        due = Some(Instant::now() + QUIET);
                    }
                }
                Ok(Err(error)) => eprintln!("[watch] {error}"),
                Err(RecvTimeoutError::Timeout) => {
                    due = None;
                    if !debounce.pending() {
                        continue;
                    }
                    // Nothing actually moved: the event was somebody reading, including
                    // very possibly us. Say nothing, and do not read the store to find out.
                    let now = fingerprint(&database);
                    let changed = now != last;
                    // The read is the test. A store mid-write answers with an error, and
                    // announcing a refresh then would make every page draw the failure.
                    // It is the cheap read: the pages fetch the payload themselves, and
                    // pulling all seven views here only to drop them tripled the work.
                    let read = changed.then(|| crate::store::readable(&database));
                    let readable = matches!(read, Some(Ok(_)));

                    match debounce.elapsed(changed, readable) {
                        Step::Wait => {}
                        Step::Announce => {
                            // Sampled **after** the read, not before it. Opening a WAL
                            // store can move `-wal`, and recording the earlier state would
                            // make our own read look like somebody else's write at the
                            // next event.
                            last = fingerprint(&database);
                            // Before the announcement, never after: a page that re-read
                            // between the two would be handed the answer this event is
                            // about to invalidate. This is the only invalidation there
                            // is, which is why it sits on the one line that says the
                            // store moved.
                            crate::store::invalidate();
                            if let Err(error) = app.emit(STORE_CHANGED, ()) {
                                eprintln!("[watch] could not announce: {error}");
                            } else {
                                eprintln!("[watch] the store changed; the pages will re-read");
                            }
                        }
                        Step::Retry => due = Some(Instant::now() + QUIET),
                        Step::GiveUp => {
                            let why = match read {
                                Some(Err(error)) => error.to_string(),
                                _ => String::new(),
                            };
                            eprintln!("[watch] gave up after {RETRIES} tries: {why}");
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

    /* --- the debounce, and whether it re-arms --------------------------------------- */

    /// One ingest from a terminal, start to finish.
    fn one_ingest(debounce: &mut Debounce) -> Step {
        debounce.touched();
        debounce.elapsed(true, true)
    }

    #[test]
    fn a_change_that_reads_cleanly_is_announced() {
        let mut debounce = Debounce::new();
        assert_eq!(one_ingest(&mut debounce), Step::Announce);
    }

    /// **The question this batch was asked.** An ingest the app did not start is one the
    /// app hears about only through the watcher, so a watcher that announces once and then
    /// stops leaves every figure frozen until the next relaunch, with nothing on screen
    /// saying so.
    ///
    /// Three in a row, because a bug that leaves a flag set usually survives one.
    #[test]
    fn the_watcher_re_arms_after_an_ingest_it_did_not_start() {
        let mut debounce = Debounce::new();
        for round in 1..=3 {
            assert_eq!(
                one_ingest(&mut debounce),
                Step::Announce,
                "the store changed for the {round}th time and nothing was announced"
            );
            assert!(!debounce.pending(), "a quiet period was left running");
        }
    }

    /// A store caught mid-write is retried, and the retry is still one burst: the count
    /// carries across the tries and is cleared the moment one succeeds.
    #[test]
    fn a_store_that_is_not_readable_yet_is_retried_and_then_announced() {
        let mut debounce = Debounce::new();
        debounce.touched();
        for _ in 0..(RETRIES - 1) {
            assert_eq!(debounce.elapsed(true, false), Step::Retry);
            assert!(
                debounce.pending(),
                "a retry has to leave the period running"
            );
        }
        assert_eq!(debounce.elapsed(true, true), Step::Announce);
        // And the next ingest is a fresh burst with its own full allowance.
        assert_eq!(one_ingest(&mut debounce), Step::Announce);
    }

    /// Giving up is not giving up for good. The whole allowance is spent, and the next
    /// file event still starts a new burst: the shell's log records the give-up, and the
    /// app has to be able to catch up when the next ingest lands.
    #[test]
    fn giving_up_still_re_arms_for_the_next_event() {
        let mut debounce = Debounce::new();
        debounce.touched();
        for _ in 0..(RETRIES - 1) {
            assert_eq!(debounce.elapsed(true, false), Step::Retry);
        }
        assert_eq!(debounce.elapsed(true, false), Step::GiveUp);
        assert!(!debounce.pending(), "a give-up left a period running");
        assert_eq!(one_ingest(&mut debounce), Step::Announce);
    }

    /// The shell's own reads. `-shm` is already filtered out by name, but a rename or a
    /// touch of the database can still produce an event with nothing behind it, and
    /// announcing then would make both pages re-read for nothing, forever.
    #[test]
    fn an_event_with_nothing_behind_it_is_not_announced_and_costs_nothing() {
        let mut debounce = Debounce::new();
        debounce.touched();
        assert_eq!(debounce.elapsed(false, true), Step::Wait);
        assert!(!debounce.pending());
        // And the allowance was not spent by it.
        debounce.touched();
        assert_eq!(debounce.elapsed(true, false), Step::Retry);
    }

    /// A quiet period that elapses with nothing pending is the loop's own 3600 second
    /// timeout coming round. It must not announce.
    #[test]
    fn nothing_pending_is_nothing_to_do() {
        assert_eq!(Debounce::new().elapsed(true, true), Step::Wait);
    }
}
