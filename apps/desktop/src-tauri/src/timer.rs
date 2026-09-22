//! The timed ingest: the shell running `prudence ingest` on its own, on an interval the
//! General tab sets.
//!
//! ## Why it is in the shell and not on the page
//!
//! The window can be closed. A menu bar app spends most of its life with no window at
//! all, and that is exactly the time the setting is for: the hooks spool events all day
//! and something has to turn them into rows. A `setInterval` in a page that is not on
//! screen is a timer that stops when the reader closes the window, which is the opposite
//! of what was asked for. So the schedule is a thread in the shell, started once at
//! launch, and the page only says what the interval should be.
//!
//! ## What "never overlapping" means
//!
//! Two runs of `prudence ingest` at once would have two processes rebuilding the `app_*`
//! views against one store. [`Engine`](crate::engine::Engine) already refuses the second
//! one, but refusing is not the same as not asking: a refusal would put "a run is already
//! going" on the page for something the reader never pressed. So the timer asks whether a
//! run is in flight **before** it starts one, and if there is, it does nothing and waits
//! for the next tick.
//!
//! A run that the reader started by hand counts: [`Timer::ran`] is called whenever any
//! run finishes, so pressing Ingest now resets the clock rather than leaving a timed run
//! a minute behind it.
//!
//! ## What is tested and what is not
//!
//! The decision is [`is_due`], which is a pure function of three values and has a test per
//! branch. The thread around it is a wait on a condition variable, which is the part no
//! test can assert without becoming a test of the clock.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

use crate::engine::{self, Action};

/// How long the thread waits before looking again when nothing is due sooner. It is not
/// the interval: the interval is compared against a monotonic clock, and this is only how
/// often the comparison is made when the next one is further away than this.
///
/// Thirty seconds, because the shortest interval offered is fifteen minutes and a timed
/// ingest starting half a minute late is a timed ingest that ran.
const TICK: Duration = Duration::from_secs(30);

/// Should a run start now?
///
/// `interval` is `None` when the setting is off. `since` is how long it has been since
/// the clock was last reset, which is either the last run of any kind or the moment the
/// interval was set. `running` is whether the engine is busy.
pub fn is_due(interval: Option<Duration>, since: Duration, running: bool) -> bool {
    match interval {
        None => false,
        Some(every) => !running && since >= every,
    }
}

/// How long to wait before asking again.
///
/// The next check is either when the interval is up or one tick from now, whichever comes
/// first. Never zero: a zero wait on a condition variable is a spin.
pub fn wait_for(interval: Option<Duration>, since: Duration) -> Duration {
    match interval {
        None => TICK,
        Some(every) => every.saturating_sub(since).clamp(TICK / 30, TICK),
    }
}

struct Schedule {
    /// `None` is off.
    every: Option<Duration>,
    /// When the clock was last reset: a run finishing, or the interval changing.
    since: Instant,
}

/// The schedule, and the way to wake the thread that is waiting on it.
pub struct Timer {
    schedule: Mutex<Schedule>,
    wake: Condvar,
    stopped: AtomicBool,
}

impl Timer {
    pub fn new(minutes: u32) -> Self {
        Self {
            schedule: Mutex::new(Schedule {
                every: interval_of(minutes),
                since: Instant::now(),
            }),
            wake: Condvar::new(),
            stopped: AtomicBool::new(false),
        }
    }

    /// Set the interval, in minutes, and restart the clock.
    ///
    /// The clock restarts on purpose: a reader who switches from six hours to fifteen
    /// minutes wants the next run in fifteen minutes, not immediately because five hours
    /// have already passed.
    pub fn set(&self, minutes: u32) {
        let mut schedule = self.schedule.lock().unwrap();
        schedule.every = interval_of(minutes);
        schedule.since = Instant::now();
        drop(schedule);
        self.wake.notify_all();
    }

    /// A run has just finished, whoever started it.
    pub fn ran(&self) {
        self.schedule.lock().unwrap().since = Instant::now();
    }

    /// Let the waiting thread end. Only the tests use it; the app's timer lives as long as
    /// the app does.
    #[cfg(test)]
    fn stop(&self) {
        self.stopped.store(true, Ordering::SeqCst);
        self.wake.notify_all();
    }

    /// Wait until something is due or the interval changes, and say whether to run.
    ///
    /// The wait is on a condition variable rather than a sleep so that changing the
    /// setting takes effect at once instead of at the end of whatever wait was already
    /// under way.
    fn wait_until_due(&self, running: &dyn Fn() -> bool) -> bool {
        let mut schedule = self.schedule.lock().unwrap();
        loop {
            if self.stopped.load(Ordering::SeqCst) {
                return false;
            }
            let since = schedule.since.elapsed();
            if is_due(schedule.every, since, running()) {
                schedule.since = Instant::now();
                return true;
            }
            // `wait_timeout` consumes the guard, so how long to wait is worked out from
            // the schedule before it is handed over.
            let wait = wait_for(schedule.every, since);
            let (next, _) = self.wake.wait_timeout(schedule, wait).unwrap();
            schedule = next;
        }
    }
}

fn interval_of(minutes: u32) -> Option<Duration> {
    (minutes > 0).then(|| Duration::from_secs(u64::from(minutes) * 60))
}

/// Start the one thread that runs the timed ingest.
///
/// Called once, from `setup`. It outlives every window, which is the whole point.
pub fn start(app: &AppHandle, timer: Arc<Timer>) {
    let app = app.clone();
    std::thread::spawn(move || loop {
        if !timer.wait_until_due(&engine::is_running) {
            return;
        }
        let remembered = app
            .state::<crate::Shell>()
            .memory
            .read()
            .usable_engine()
            .map(str::to_string);
        eprintln!("[timer] the interval is up; running an ingest");
        // An ingest nobody pressed still reports: a window open while the interval comes
        // up shows what it is doing, on the same strip a pressed run uses.
        let outcome =
            engine::shared().run(remembered.as_deref(), Action::Ingest, false, &|progress| {
                crate::announce_progress(&app, progress)
            });
        match &outcome.error_kind {
            Some(kind) => eprintln!("[timer] the ingest did not finish: {kind}"),
            None => eprintln!("[timer] the ingest finished"),
        }
        // Whatever it did, the clock starts from the end of it rather than from the start:
        // an ingest that takes four minutes on a six-hour interval should not shorten the
        // next wait by four minutes.
        timer.ran();
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIFTEEN: Option<Duration> = Some(Duration::from_secs(15 * 60));

    #[test]
    fn off_is_off_however_long_it_has_been() {
        assert!(!is_due(None, Duration::from_secs(86_400), false));
    }

    #[test]
    fn nothing_runs_until_the_interval_is_up() {
        assert!(!is_due(FIFTEEN, Duration::from_secs(0), false));
        assert!(!is_due(FIFTEEN, Duration::from_secs(15 * 60 - 1), false));
        assert!(is_due(FIFTEEN, Duration::from_secs(15 * 60), false));
        assert!(is_due(FIFTEEN, Duration::from_secs(60 * 60), false));
    }

    /// The rule the whole module exists for: two ingests against one store at once is two
    /// processes rebuilding the same views.
    #[test]
    fn a_run_already_in_flight_is_never_joined_by_a_timed_one() {
        assert!(!is_due(FIFTEEN, Duration::from_secs(60 * 60), true));
    }

    /// Never zero, or the wait on the condition variable becomes a spin, and never longer
    /// than a tick, or a setting changed on another thread waits out the old interval.
    #[test]
    fn the_wait_is_bounded_at_both_ends() {
        assert_eq!(wait_for(None, Duration::from_secs(0)), TICK);
        assert_eq!(wait_for(FIFTEEN, Duration::from_secs(0)), TICK);
        // Past due, which happens when the engine was busy at the last look.
        assert!(wait_for(FIFTEEN, Duration::from_secs(60 * 60)) > Duration::ZERO);
        // Nearly due: the wait is what is left, not a whole tick past it.
        assert_eq!(
            wait_for(FIFTEEN, Duration::from_secs(15 * 60 - 5)),
            Duration::from_secs(5)
        );
    }

    /// Zero minutes is off, and every interval the General tab offers is a real one.
    #[test]
    fn the_intervals_the_general_tab_offers_are_minutes() {
        assert_eq!(interval_of(0), None);
        assert_eq!(interval_of(15), Some(Duration::from_secs(900)));
        assert_eq!(interval_of(360), Some(Duration::from_secs(21_600)));
    }

    /// Setting the interval restarts the clock, so a reader moving from six hours to
    /// fifteen minutes waits fifteen minutes rather than being ingested at once.
    #[test]
    fn changing_the_interval_restarts_the_clock() {
        let timer = Timer::new(15);
        timer.schedule.lock().unwrap().since = Instant::now() - Duration::from_secs(60 * 60);
        timer.set(15);
        assert!(timer.schedule.lock().unwrap().since.elapsed() < Duration::from_secs(1));
        timer.stop();
    }
}
