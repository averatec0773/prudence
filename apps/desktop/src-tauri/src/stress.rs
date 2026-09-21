//! The compositor question, asked in a way a screenshot can answer.
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
