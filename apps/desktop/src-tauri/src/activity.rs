//! What the engine is doing right now, whoever started it.
//!
//! ## Why the shell keeps this and not a page
//!
//! A run can begin in four places: the window's toolbar, the panel, the timed ingest and a
//! terminal. The window's status row and its toolbar have to say what is going on in every
//! one of those cases, and before this the page knew about a run only if it had pressed the
//! button itself: it waited on the command's promise, and a timed ingest or a panel run
//! reached the window as progress lines with no beginning and no end.
//!
//! So the shell holds one answer, [`Activity`], and tells both pages whenever it changes
//! (`ENGINE_ACTIVITY` in `lib.rs`). A page drawn in the middle of a run asks for it once
//! through `engine_activity`, which is also where it finds the last progress line.
//!
//! ## A run this app did not start
//!
//! `prudence ingest` holds an advisory lock on `ingest.lock`, beside the store, for exactly
//! as long as it runs (`src/prudence/store/db.py`, `ingest_lock`). The watcher looks at that
//! lock whenever the store's files move, and every [`LOCK_POLL`] while it is held, without
//! ever taking it: `platform::lock_held` asks who holds it and nothing more, so a probe can
//! never be the reason an ingest in a terminal is refused. `prudence rebuild` takes the
//! same lock and is reported the same way, because from here the two cannot be told apart.
//!
//! ## What is tested
//!
//! The transitions are [`Activity`]'s own methods and each has a test. The one piece of
//! ordering that is not a pure function is the lock probe racing the end of a run this app
//! started, and [`observe_lock`] closes it by probing under the same mutex [`finished`]
//! takes: the engine's child has released the lock before `finished` can run, so a probe
//! after it sees a free lock and a probe before it sees a run of the app's own.

use std::path::Path;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;

use crate::engine::{self, Action, Progress, RunOutcome};

/// How often the lock is looked at again while a run this app did not start is holding it.
/// The end of such a run makes no file event of its own: the last write to the store comes
/// before the lock is let go, so nothing but a second look can see it end.
pub const LOCK_POLL: Duration = Duration::from_secs(2);

/// What the engine is doing, as both pages are told it.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Activity {
    /// `ingest` or `review` while a run is going, and nothing when none is.
    pub running: Option<String>,
    /// True for a run this app did not start. It is always an ingest, because only an
    /// ingest (or a rebuild) holds the lock, and it carries no progress: the engine writes
    /// progress lines only for the process that asked for them.
    pub outside: bool,
    /// The last progress line of the run in hand, so a page drawn half way through it
    /// draws the step it is on rather than nothing until the next line arrives.
    pub progress: Option<Progress>,
    /// How the last run this app started ended. Nothing after a run from outside, whose
    /// answer went to whoever started it.
    pub outcome: Option<RunOutcome>,
}

impl Activity {
    /// A run this app started, from its first moment.
    pub fn start(action: Action) -> Self {
        Self {
            running: Some(action.name().to_string()),
            ..Self::default()
        }
    }

    /// The same run, one progress line further on.
    pub fn progressed(&self, progress: &Progress) -> Self {
        Self {
            progress: Some(progress.clone()),
            ..self.clone()
        }
    }

    /// A run this app started, ended, with the engine's own answer.
    pub fn finish(outcome: RunOutcome) -> Self {
        Self {
            outcome: Some(outcome),
            ..Self::default()
        }
    }

    /// What the lock says, read against what this app already knows.
    ///
    /// A run of the app's own owns the answer while it lasts: its child holds the lock, and
    /// that is not news. Otherwise a held lock is a run from outside and a free one ends
    /// it; anything else is no change at all, so an idle store with a free lock keeps the
    /// outcome of the last run on it until the page has said it.
    pub fn lock(&self, held: bool) -> Self {
        if self.running.is_some() && !self.outside {
            return self.clone();
        }
        match (held, self.outside) {
            (true, false) => Self {
                running: Some(Action::Ingest.name().to_string()),
                outside: true,
                ..Self::default()
            },
            (false, true) => Self::default(),
            _ => self.clone(),
        }
    }

    /// Whether this is a change a page draws. A progress line is not: it has its own
    /// event, one per line, and announcing the whole state as well would be every line
    /// twice.
    fn differs_from(&self, other: &Self) -> bool {
        self.running != other.running
            || self.outside != other.outside
            || self.outcome != other.outcome
    }
}

fn state() -> &'static Mutex<Activity> {
    static STATE: OnceLock<Mutex<Activity>> = OnceLock::new();
    STATE.get_or_init(|| Mutex::new(Activity::default()))
}

/// The answer as it stands, for a page that has just been drawn.
pub fn now() -> Activity {
    state().lock().unwrap().clone()
}

/// Replace the answer, and tell both pages if what they draw has changed.
fn set(app: &AppHandle, next: Activity, held: &mut Activity) {
    let announce = next.differs_from(held);
    *held = next;
    if announce {
        crate::announce_activity(app, held);
    }
}

/// Run `ingest` or `review` and keep the answer while it goes.
///
/// The one door every run the shell starts goes through: the page's command and the timed
/// ingest both call this, so a run from the panel, the toolbar or the timer is announced
/// the same way. `started` is called by the engine only once it has taken its own
/// one-run-at-a-time flag, so a run refused as busy never touches the answer the running
/// one is keeping.
pub fn run(app: &AppHandle, remembered: Option<&str>, action: Action, force: bool) -> RunOutcome {
    let began = std::sync::atomic::AtomicBool::new(false);
    let outcome = engine::shared().run(
        remembered,
        action,
        force,
        &|| {
            began.store(true, std::sync::atomic::Ordering::SeqCst);
            let mut held = state().lock().unwrap();
            set(app, Activity::start(action), &mut held);
        },
        &|progress| {
            {
                let mut held = state().lock().unwrap();
                *held = held.progressed(progress);
            }
            crate::announce_progress(app, progress);
        },
    );
    if began.load(std::sync::atomic::Ordering::SeqCst) {
        finished(app, &outcome);
    }
    outcome
}

fn finished(app: &AppHandle, outcome: &RunOutcome) {
    let mut held = state().lock().unwrap();
    set(app, Activity::finish(outcome.clone()), &mut held);
}

/// Look at the engine's lock and say whether a run from outside is still holding it.
///
/// Probed under the mutex, for the reason at the top of the file. The answer is what the
/// watcher uses to decide whether to look again in [`LOCK_POLL`].
pub fn observe_lock(app: &AppHandle, lock: &Path) -> bool {
    let mut held = state().lock().unwrap();
    let next = held.lock(crate::platform::lock_held(lock));
    set(app, next, &mut held);
    held.outside
}

/// Where the engine keeps its lock: beside the store, under the name
/// `src/prudence/paths.py` gives it.
pub fn lock_file(database: &Path) -> std::path::PathBuf {
    database.with_file_name("ingest.lock")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn outcome(action: &str) -> RunOutcome {
        RunOutcome {
            action: action.into(),
            ok: true,
            ..RunOutcome::default()
        }
    }

    #[test]
    fn a_run_of_the_apps_own_is_running_from_its_first_moment() {
        let started = Activity::start(Action::Review);
        assert_eq!(started.running.as_deref(), Some("review"));
        assert!(!started.outside);
        assert_eq!(started.outcome, None);
    }

    /// The outcome of the run before is not the outcome of this one.
    #[test]
    fn starting_a_run_forgets_the_last_outcome() {
        let before = Activity::finish(outcome("ingest"));
        assert!(before.outcome.is_some());
        assert_eq!(Activity::start(Action::Ingest).outcome, None);
    }

    #[test]
    fn a_finished_run_is_idle_and_keeps_its_answer() {
        let done = Activity::finish(outcome("ingest"));
        assert_eq!(done.running, None);
        assert_eq!(done.outcome, Some(outcome("ingest")));
    }

    #[test]
    fn a_progress_line_is_kept_and_is_not_a_change_a_page_draws() {
        let started = Activity::start(Action::Ingest);
        let line = Progress {
            step: "parse".into(),
            current: 3,
            total: 9,
            ..Progress::default()
        };
        let later = started.progressed(&line);
        assert_eq!(later.progress, Some(line));
        assert!(!later.differs_from(&started));
    }

    /// The case this module exists for: an ingest in a terminal.
    #[test]
    fn a_held_lock_on_an_idle_store_is_a_run_from_outside() {
        let seen = Activity::default().lock(true);
        assert_eq!(seen.running.as_deref(), Some("ingest"));
        assert!(seen.outside);
        assert!(seen.differs_from(&Activity::default()));
    }

    #[test]
    fn a_free_lock_ends_a_run_from_outside_with_no_outcome() {
        let outside = Activity::default().lock(true);
        let ended = outside.lock(false);
        assert_eq!(ended, Activity::default());
    }

    /// The app's own child holds the lock while it ingests. That is not a second run.
    #[test]
    fn the_lock_held_by_a_run_of_the_apps_own_is_not_news() {
        let ours = Activity::start(Action::Ingest);
        assert_eq!(ours.lock(true), ours);
        assert_eq!(ours.lock(false), ours);
    }

    /// A free lock after a run of the app's own leaves its answer on the store, so the page
    /// can still say how it ended.
    #[test]
    fn a_free_lock_after_a_run_keeps_its_outcome() {
        let done = Activity::finish(outcome("review"));
        assert_eq!(done.lock(false), done);
    }

    #[test]
    fn the_lock_is_the_engines_own_file_beside_the_store() {
        assert_eq!(
            lock_file(Path::new("/data/prudence/prudence.db")),
            Path::new("/data/prudence/ingest.lock")
        );
    }
}
