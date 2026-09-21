//! Everything that exists so a script can drive the app, and nothing a user can reach.
//!
//! Compiled only with `--features harness`, so a release build has none of it: no
//! environment variable can make the shipped app open a window by itself, put a backdrop
//! on the screen, or evaluate JavaScript against its own page. `Scripts/shot.py` and
//! `Scripts/stress.py` build with the feature.
//!
//! ## The compositor question, asked in a way a screenshot can answer
//!
//! Wry issue 1848 (opened 2026-09-16, still open) reports the macOS 26 WKWebView
//! compositor intermittently ceasing to present new frames: the DOM keeps updating and
//! JavaScript keeps running, but the screen holds a stale image. Tauri 2.11.6 resolves
//! wry 0.55.1, which is the version it was filed against.
//!
//! That shape of failure defeats every check that asks the page how it is, because the
//! page is fine. So the harness ends with a **paint probe**: the page is told to fill a
//! known rectangle with a colour derived from a token, and the checker reads that
//! rectangle out of a screenshot. A stale compositor keeps the old colour while the DOM
//! reports the new one, and only the screenshot can tell the difference.
//!
//! None of this is reachable by anything a user does.

use tauri::{AppHandle, Manager};

use crate::{panel, window, MAIN};

/// Is a script driving the app right now? The panel must not dismiss itself on focus
/// loss while one is, or every screenshot is of an empty desktop.
pub fn driving() -> bool {
    panel_stays_open() || window_opens_at_launch() || plan().is_some()
}

fn flag(name: &str) -> bool {
    std::env::var(name).is_ok_and(|value| !value.is_empty() && value != "0")
}

fn panel_stays_open() -> bool {
    flag("PRUDENCE_PANEL_OPEN")
}

fn window_opens_at_launch() -> bool {
    flag("PRUDENCE_WINDOW_OPEN")
}

fn backdrop_wanted() -> bool {
    flag("PRUDENCE_BACKDROP")
}

/// Open whatever the script asked for, once the status item is laid out.
pub fn start(app: &AppHandle) {
    if !(driving() || backdrop_wanted()) {
        return;
    }
    let handle = app.clone();
    std::thread::spawn(move || {
        if backdrop_wanted() {
            let backdrop = handle.clone();
            let _ = handle
                .clone()
                .run_on_main_thread(move || window::open_backdrop(&backdrop));
        }

        wait_for_the_status_item(&handle);

        if window_opens_at_launch() {
            let open = handle.clone();
            let _ = handle
                .clone()
                .run_on_main_thread(move || window::open(&open));
        }
        if panel_stays_open() {
            let open = handle.clone();
            let _ = handle
                .clone()
                .run_on_main_thread(move || panel::show(&open));
        }
        if let Some(plan) = plan() {
            run(&handle, plan);
        }
    });
}

/// AppKit lays the status item out a moment after launch, and a panel anchored before
/// that lands off the bottom of the screen.
///
/// This used to be `sleep(1200 ms)`, which is a guess: too long on a fast launch and too
/// short on a loaded CI runner, where the anchor silently falls back to a screen corner
/// and the script photographs a panel in the wrong place. `tray_anchor` already returns
/// `None` for exactly this condition, so it is asked rather than waited out.
fn wait_for_the_status_item(app: &AppHandle) {
    use std::sync::mpsc::channel;

    for _ in 0..60 {
        let (tx, rx) = channel();
        let _ = app.run_on_main_thread(move || {
            let _ = tx.send(crate::platform::tray_anchor().is_some());
        });
        if rx
            .recv_timeout(std::time::Duration::from_millis(500))
            .unwrap_or(false)
        {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    eprintln!("[harness] the status item never laid out; the panel will fall back to a corner");
}

pub struct Plan {
    pub rounds: u32,
    pub panel_every: u32,
}

/// `PRUDENCE_STRESS=screens:400` or `PRUDENCE_STRESS=panel:30`.
pub fn plan() -> Option<Plan> {
    let value = std::env::var("PRUDENCE_STRESS").ok()?;
    let (kind, count) = value.split_once(':')?;
    let rounds: u32 = count.parse().ok()?;
    match kind {
        // Screens and scrolling, with the panel opened and closed along the way: the panel
        // and the window share one process and one compositor, so exercising them apart
        // would not be exercising the thing that is shipped.
        "screens" => Some(Plan {
            rounds,
            panel_every: 5,
        }),
        // The spike's original run: the panel alone.
        "panel" => Some(Plan {
            rounds,
            panel_every: 1,
        }),
        _ => None,
    }
}

pub fn run(app: &AppHandle, plan: Plan) {
    let screens = plan.panel_every != 1;
    if screens {
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || window::open(&handle));
        std::thread::sleep(std::time::Duration::from_millis(600));
    }

    for round in 0..plan.rounds {
        if screens {
            eval(
                app,
                &format!("window.Stress && window.Stress.step({round})"),
            );
        }
        if round % plan.panel_every == 0 {
            toggle_panel(app);
        }
        std::thread::sleep(std::time::Duration::from_millis(40));
        if (round + 1) % 50 == 0 {
            eprintln!("[stress] round {} of {}", round + 1, plan.rounds);
        }
    }

    // A known screen at a known scroll offset, so the screenshot can be held against the
    // same state reached in three moves.
    if screens {
        eval(app, "window.Stress && window.Stress.finish()");
    }
    // The panel is left closed: the pictures after this are of the window, and a panel
    // sitting over it would be in every one of them.
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || panel::hide(&handle));

    // The timings below are a contract with `Scripts/stress.sh`, which sleeps in step and
    // takes one picture in each window. Keep them together.
    std::thread::sleep(std::time::Duration::from_millis(1500));
    eprintln!("[stress] settled after {} rounds", plan.rounds);
    std::thread::sleep(std::time::Duration::from_secs(4));

    probe(app, "after-stress", (214, 45, 130));

    if let Some(seconds) = idle_seconds() {
        eprintln!("[stress] idling for {seconds} s");
        std::thread::sleep(std::time::Duration::from_secs(seconds));
        // Nothing says the stall needs activity, so the same question is asked again of a
        // process that has done nothing at all for ten minutes.
        probe(app, "after-idle", (36, 168, 92));
    }

    eprintln!("[stress] done");
}

/// `PRUDENCE_STRESS_IDLE=600`.
fn idle_seconds() -> Option<u64> {
    std::env::var("PRUDENCE_STRESS_IDLE")
        .ok()
        .and_then(|value| value.parse().ok())
        .filter(|seconds| *seconds > 0)
}

/// Fill the window's screen area with one colour and say which, so a checker can read the
/// answer off a screenshot instead of off the page. This is the only check in the batch
/// that a stale compositor cannot pass by lying.
fn probe(app: &AppHandle, label: &str, (r, g, b): (u8, u8, u8)) {
    eval(
        app,
        &format!("window.Stress && window.Stress.probe('rgb({r},{g},{b})')"),
    );
    std::thread::sleep(std::time::Duration::from_millis(400));
    eprintln!("[probe] {label} expects rgb({r},{g},{b}) filling the window's screen area");
    std::thread::sleep(std::time::Duration::from_secs(4));
}

fn toggle_panel(app: &AppHandle) {
    for open in [true, false] {
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            if open {
                panel::show(&handle)
            } else {
                panel::hide(&handle)
            }
        });
        std::thread::sleep(std::time::Duration::from_millis(30));
    }
}

fn eval(app: &AppHandle, script: &str) {
    if let Some(window) = app.get_webview_window(MAIN) {
        if let Err(error) = window.eval(script) {
            eprintln!("[stress] eval failed: {error}");
        }
    }
}
