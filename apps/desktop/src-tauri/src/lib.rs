//! The shell: a status item, a panel that hangs under it, a window with the screens in it,
//! and a read-only view of the store.
//!
//! Phase 1, batch 1. The window's screens are placeholders; what this batch is really for
//! is whether the compositor holds. See `docs/reports/desktop/02-window-shell.md`.

mod activity;
mod applog;
mod contract;
mod engine;
mod installer;
mod model;
mod panel;
mod platform;
mod readiness;
mod repositories;
mod runlog;
mod sources;
mod store;
mod timer;
mod ui_state;
mod watcher;
mod window;

/// Everything that exists only so a script can drive the app. Absent from a release
/// build, which is the point: a shipped binary that evaluates JavaScript against its own
/// window when an environment variable is set is a sentence nobody wants in a security
/// policy. `harness::` is the whole surface, and every call to it is behind this feature.
#[cfg(feature = "harness")]
mod harness;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::Serialize;
use serde_json::Value;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tauri_plugin_autostart::ManagerExt;

use ui_state::Memory;

/// The two windows. The frontend never names either; `panel.rs` and `window.rs` do.
pub const PANEL: &str = "panel";
// Why every command below that waits is `spawn_blocking` and not `command(async)`.
//
// `#[tauri::command(async)]` over a synchronous body spawns a tokio task on the shared
// multi-thread runtime. It is **not** `spawn_blocking`, so a body that blocks occupies a
// worker for as long as it blocks: an ingest for minutes, a `--version` for up to twenty
// seconds, the picker for as long as it is open. `store_read` draws from the same pool,
// so on a machine with few cores an ingest plus one redraw can exhaust it and the page's
// read never resolves. The window looks frozen and nothing is wrong and nothing is
// logged, which is the worst shape a bug can have.
//
// A borrowed `State` cannot cross into another thread, so each of these copies what the
// work needs first. That copy is the reason the pattern looks repetitive rather than
// factored: the alternative is a helper that takes a closure over `Shell`, which would
// have to hold the lock across the blocking call.

pub const MAIN: &str = "main";
/// The screenshot backdrop. Built only by the harness; see `harness.rs`.
#[cfg(feature = "harness")]
pub const BACKDROP: &str = "backdrop";

pub struct Shell {
    pub database: PathBuf,
    pub started: std::time::Instant,
    pub material: Mutex<platform::MaterialReport>,
    pub tray_highlight_works: Mutex<bool>,
    pub memory: Memory,
    /// The timed ingest's schedule. Held here rather than in a static so that the thread
    /// and the commands are talking to one object whose lifetime is the app's.
    pub timer: Arc<timer::Timer>,
    /// The folder the last `prudence diagnose` from this app wrote, which is the one
    /// `Reveal` shows. Held here so the page can ask for it by name.
    pub bundle: Mutex<Option<PathBuf>>,
}

/// What the General tab sets, in one answer.
///
/// `language` and `appearance` are the **settings** (`system`, `en`, `zh-Hans` and
/// `system`, `light`, `dark`), not what they resolve to: a control ticked from a resolved
/// value would move on its own when the machine's own setting changed.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSettings {
    language: String,
    appearance: String,
    /// Zero is off.
    ingest_every_minutes: u32,
    open_at_login: bool,
    /// Why open-at-login could not be read or set, in the plugin's own words. English,
    /// like every other message from something that is not this app; the page puts its own
    /// sentence above it.
    login_error: Option<String>,
}

/// Read the three remembered settings, and ask the platform about the fourth.
///
/// Open-at-login is the one setting this app does not store: the system stores it, and a
/// copy kept here would disagree with it the first time somebody turned it off in System
/// Settings. So it is asked every time.
fn app_settings(app: &AppHandle, memory: &Memory) -> AppSettings {
    let state = memory.read();
    let (open_at_login, login_error) = match app.autolaunch().is_enabled() {
        Ok(enabled) => (enabled, None),
        Err(error) => (false, Some(error.to_string())),
    };
    AppSettings {
        language: state.usable_language().to_string(),
        appearance: state.usable_appearance().to_string(),
        ingest_every_minutes: state.usable_ingest_minutes(),
        open_at_login,
        login_error,
    }
}

#[derive(Serialize)]
pub struct ShellInfo {
    version: String,
    database: String,
    /// Where the engine's run log and this app's own log are, for the Engine tab's note.
    logs: String,
    material: platform::MaterialReport,
    tray_highlight: bool,
    platform: Vec<(String, String)>,
    supported_contract: Vec<u32>,
    /// The language the pages are to draw in, or null to follow the machine. It is the
    /// screenshot hook's forced value first, then the General tab's setting; `system` is
    /// sent as null, because "follow the machine" is what the page does with no answer.
    language: Option<String>,
    /// The General tab's own settings, so the first draw already has them and Settings
    /// does not have to ask separately.
    settings: AppSettings,
    /// The section the window last had, or null when this build no longer has it.
    section: Option<String>,
    /// Which of the panel's four ranges was last chosen, remembered like the section and
    /// restored the same way. Always one of `ui_state::PANEL_RANGES`: a stored value this
    /// build no longer offers already fell back to the default inside `usable_panel_range`.
    panel_range: String,
    /// Whether this build carries the automation hooks. The page exposes its own test
    /// entry point only when it does.
    harness: bool,
    /// How far down a script wants the screen scrolled before it is photographed.
    /// Always null in a release build.
    scroll: Option<u32>,
    /// A button a script wants pressed once the page has drawn. Never set in a release.
    press: Option<String>,
    /// Whether the page should time itself once it has drawn. Never true in a release.
    measure: bool,
}

/// `async` so that a slow disk cannot freeze the panel: a non-async command runs on the
/// main thread, and this one issues seven selects. They take about 60 ms on the founder's
/// 815 MB store today, which is fine, and the failure mode if that ever changes is a
/// frozen window rather than a slow one.
/// Run something that waits, on the pool meant for waiting, and say so if it cannot run.
///
/// The error is not a user-visible sentence: a task that fails to schedule means the
/// runtime is going away, which the page can only report as an unexpected failure.
async fn scheduled<T, F>(work: F) -> Result<T, String>
where
    F: FnOnce() -> T + Send + 'static,
    T: Send + 'static,
{
    tauri::async_runtime::spawn_blocking(work)
        .await
        .map_err(|error| format!("the shell could not schedule the work: {error}"))
}

/// The store's answer, from the one copy the shell keeps.
///
/// Both pages ask, and they ask together: the panel and the window load at the same
/// moment and both re-read on every announcement. `store::snapshot` reads the file only
/// when the watcher says it moved, so two pages cost one read, and the `revision` it
/// carries is what lets a page skip a redraw that would draw the same figures.
#[tauri::command]
async fn store_read(shell: State<'_, Shell>) -> Result<Value, String> {
    let database = shell.database.clone();
    scheduled(move || store::snapshot(&database).map_err(|error| error.to_string())).await?
}

#[tauri::command]
fn shell_info(app: AppHandle, shell: State<'_, Shell>) -> ShellInfo {
    let settings = app_settings(&app, &shell.memory);
    ShellInfo {
        version: env!("CARGO_PKG_VERSION").into(),
        database: shell.database.display().to_string(),
        logs: store::logs_dir().display().to_string(),
        material: shell.material.lock().unwrap().clone(),
        tray_highlight: *shell.tray_highlight_works.lock().unwrap(),
        platform: platform::describe(),
        supported_contract: store::supported_contract(),
        language: forced_language().or_else(|| chosen_language(&settings.language)),
        settings,
        section: scripted_section()
            .or_else(|| shell.memory.read().usable_section().map(str::to_string)),
        panel_range: shell.memory.read().usable_panel_range().to_string(),
        harness: cfg!(feature = "harness"),
        scroll: scripted_scroll(),
        press: scripted_press(),
        measure: scripted_measure(),
    }
}

/// Harness only, like every other automation hook.
#[cfg(feature = "harness")]
fn scripted_press() -> Option<String> {
    harness::press()
}

#[cfg(not(feature = "harness"))]
fn scripted_press() -> Option<String> {
    None
}

#[cfg(feature = "harness")]
fn scripted_measure() -> bool {
    harness::measuring()
}

#[cfg(not(feature = "harness"))]
fn scripted_measure() -> bool {
    false
}

fn scripted_scroll() -> Option<u32> {
    #[cfg(feature = "harness")]
    {
        harness::scroll_to()
    }
    #[cfg(not(feature = "harness"))]
    {
        None
    }
}

/// The page reports how tall its content is; the shell decides what to do about it.
#[tauri::command]
fn panel_fit(app: AppHandle, width: f64, height: f64) {
    panel::fit(&app, width, height);
}

#[tauri::command]
fn panel_hide(app: AppHandle) {
    panel::hide(&app);
}

#[tauri::command]
fn window_open(app: AppHandle) {
    window::open(&app);
}

#[tauri::command]
fn window_close(app: AppHandle) {
    window::close(&app);
}

/// The screen a screenshot run asked for, and nothing in a release build.
#[cfg(feature = "harness")]
fn scripted_section() -> Option<String> {
    harness::section()
}

#[cfg(not(feature = "harness"))]
fn scripted_section() -> Option<String> {
    None
}

/// The window's current section, so the next launch opens on it.
#[tauri::command]
fn section_set(shell: State<'_, Shell>, section: String) {
    shell.memory.set_section(&section);
}

/// The panel's current range choice, so the next launch opens on it. A value outside
/// `ui_state::PANEL_RANGES` is refused rather than stored; the page never sends one, since
/// it only ever offers the four the picker draws.
#[tauri::command]
fn panel_range_set(shell: State<'_, Shell>, range: String) {
    shell.memory.set_panel_range(&range);
}

/* --- the engine ---------------------------------------------------------------------- */

/// Where the `prudence` executable is and what version it is.
///
/// `async` because it runs a login shell and a process: `engine.rs` states the order and
/// why a shell is needed at all. Not cached here, so that a user who has just installed
/// the engine or just chosen a path gets the new answer without a relaunch; the one thing
/// that is cached is the login-shell probe, inside the locator.
#[tauri::command]
async fn engine_status(shell: State<'_, Shell>) -> Result<engine::EngineStatus, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || engine::shared().status(remembered.as_deref())).await
}

/// What a run is doing, while it is still doing it.
///
/// Unlike `store-changed` and `settings-changed`, this one carries its payload: the point
/// of a progress line is that it is true for a moment, and asking for it again would mean
/// asking a run that has already moved on. It is the same reasoning as
/// `installer::INSTALL_PROGRESS`, and the same shape.
const ENGINE_PROGRESS: &str = "engine-progress";

/// Tell both pages what the run is doing.
///
/// Both, not the one that pressed the button: the panel and the window can be open
/// together, and a timed ingest belongs to neither. A page that is not drawing a run
/// ignores it.
pub fn announce_progress(app: &AppHandle, progress: &engine::Progress) {
    if let Err(error) = app.emit(ENGINE_PROGRESS, progress) {
        eprintln!("[engine] could not report progress: {error}");
    }
}

/// Whether a run is going and how the last one ended, whoever started it.
///
/// Carries its payload, unlike `store-changed`: the window's toolbar and status row draw
/// straight from it, and `engine_activity` answers the same thing for a page drawn in the
/// middle of a run. `activity.rs` holds the answer and says when it changes.
const ENGINE_ACTIVITY: &str = "engine-activity";

/// Tell both pages what the engine is doing now, and say so on standard error: a run from
/// a terminal is otherwise invisible to anybody reading the shell's log.
pub fn announce_activity(app: &AppHandle, activity: &activity::Activity) {
    eprintln!(
        "[engine] activity: running={} outside={} outcome={}",
        activity.running.as_deref().unwrap_or("none"),
        activity.outside,
        activity
            .outcome
            .as_ref()
            .map(|outcome| outcome.error_kind.as_deref().unwrap_or("ok"))
            .unwrap_or("none")
    );
    if let Err(error) = app.emit(ENGINE_ACTIVITY, activity) {
        eprintln!("[engine] could not report activity: {error}");
    }
}

/// What the engine is doing right now, for a page that has just been drawn.
#[tauri::command]
fn engine_activity() -> activity::Activity {
    activity::now()
}

/// Run `prudence ingest` or `prudence review`, and answer with what the engine said.
///
/// The page waits on this promise for the answer it reports in detail; what a run is doing
/// meanwhile reaches both pages over [`ENGINE_ACTIVITY`] and [`ENGINE_PROGRESS`], through
/// `activity::run`, which the timed ingest goes through as well. Nothing else is plumbed
/// into the screens: `watcher.rs` already refreshes every page when the store changes, so
/// a successful run's new figures arrive on their own.
#[tauri::command]
async fn engine_run(
    app: AppHandle,
    shell: State<'_, Shell>,
    action: String,
    force: bool,
) -> Result<engine::RunOutcome, String> {
    let Some(action) = engine::Action::parse(&action) else {
        // Not a user-visible sentence: the page can only send one of two words, so
        // anything else is a defect in the bridge rather than something to translate.
        return Err(format!("no such engine action: {action}"));
    };
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    let timer = shell.timer.clone();
    let outcome =
        scheduled(move || activity::run(&app, remembered.as_deref(), action, force)).await;
    // The timed ingest's clock starts again from any run, not only from its own. Without
    // this a reader who presses Ingest now a minute before the interval is up gets a
    // second ingest a minute later, for nothing.
    timer.ran();
    outcome
}

/// The user picks the executable, and it is verified before it is trusted.
///
/// Opened from the shell rather than from the page, because everything that makes the
/// choice safe is on this side: whether the file is executable, whether it answers
/// `--version`, and where the answer is remembered.
#[tauri::command]
async fn engine_choose(app: AppHandle, shell: State<'_, Shell>) -> Result<engine::Choice, String> {
    // The picker and the verification both wait, so both happen on the blocking pool.
    // What comes back is an answer, and the remembering happens here, where the state is.
    let picked = scheduled(move || {
        // A picker takes the focus, and the panel dismisses itself when it loses focus.
        // The guard is held for as long as the dialog is up and clears itself on every
        // path out, cancellation included.
        let _dialog = engine::DialogGuard::open();
        let chosen = engine::pick_file(&app)?;
        let verdict = engine::shared().verify(&chosen);
        Some((chosen, verdict))
    })
    .await?;

    let Some((chosen, verdict)) = picked else {
        return Ok(engine::Choice::cancelled());
    };
    match verdict {
        Ok(version) => {
            shell.memory.set_engine(Some(&chosen.display().to_string()));
            // Written now rather than at quit: a path the user just chose and then lost
            // to a crash is a path they have to find again. The result is propagated
            // rather than dropped: the page is told the path was taken, so a silent
            // failure here means it is forgotten at the next launch with nobody told why.
            shell.memory.save()?;
            setting_written("engine path", None);
            Ok(engine::Choice::accepted(chosen, version))
        }
        Err(error) => Ok(engine::Choice::rejected(chosen, &error)),
    }
}

/// Forget the chosen path and put the search back in charge.
#[tauri::command]
fn engine_forget(shell: State<'_, Shell>) {
    shell.memory.set_engine(None);
    // Forgetting is idempotent: if the write fails the path is still forgotten for this
    // launch, and the next `Choose` writes again. The failure is still on the record.
    match shell.memory.save() {
        Ok(()) => setting_written("engine path", Some("forgotten")),
        Err(error) => {
            tracing::error!(target: "settings", setting = "engine path", error = %error, "setting not saved")
        }
    }
}

/// Install or update `prudence-core` with uv.
///
/// The page sends one boolean and nothing else; every word of both command lines is a
/// constant in `installer.rs`, which says why. uv's output is streamed to the page as it
/// arrives, over [`installer::INSTALL_PROGRESS`], and the same lines come back at the end
/// with the outcome, so a page that missed an event still has them.
///
/// When uv is not on this machine there is nothing to run and nothing failed: the answer
/// carries the manual route, which is the two commands a reader types.
#[tauri::command]
async fn engine_install(
    app: AppHandle,
    upgrade: bool,
) -> Result<installer::InstallOutcome, String> {
    scheduled(move || {
        let Some(uv) = engine::shared().locate_uv() else {
            tracing::error!(target: "install", upgrade, "no uv to install with");
            return installer::InstallOutcome {
                error_kind: Some("noUv".into()),
                manual: installer::manual(),
                ..installer::InstallOutcome::default()
            };
        };
        let report = app.clone();
        let outcome = installer::install(&uv, upgrade, &move |lines| {
            let _ = report.emit(
                installer::INSTALL_PROGRESS,
                installer::InstallProgress {
                    lines: lines.to_vec(),
                },
            );
        });
        // uv's lines are shown to the reader and stay out of the log, all but the last one
        // of a failure, which is uv's own reason.
        match &outcome {
            Ok(done) if done.ok => {
                tracing::info!(target: "install", upgrade, exit = ?done.status, "installed")
            }
            Ok(done) => tracing::error!(
                target: "install",
                upgrade,
                exit = ?done.status,
                detail = ?done.lines.last().map(String::as_str).unwrap_or(""),
                "install failed"
            ),
            Err(error) => tracing::error!(
                target: "install",
                upgrade,
                kind = error.kind(),
                detail = ?error.detail(),
                "install could not start"
            ),
        }
        match outcome {
            Ok(done) => done,
            Err(error) => installer::InstallOutcome {
                error_kind: Some(error.kind().into()),
                lines: vec![error.detail()]
                    .into_iter()
                    .filter(|l| !l.is_empty())
                    .collect(),
                manual: installer::manual(),
                ..installer::InstallOutcome::default()
            },
        }
    })
    .await
}

/* --- the repositories, and whether a review is ready -----------------------------------
 *
 * Both are questions for the engine rather than for the store: which repositories exist on
 * disk and which are enabled is what `prudence init --scan` knows, and whether there is
 * enough new work for a review is a rule `prudence status` states. The app decodes and
 * draws; `repositories.rs` and `readiness.rs` hold the reading.
 */

/// Every repository the engine found, and which of them it is recording.
#[tauri::command]
async fn engine_repositories(
    shell: State<'_, Shell>,
) -> Result<Vec<repositories::Repository>, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        engine::shared()
            .read(remembered.as_deref(), &["init", "--scan", "--json"])
            .map_err(|error| error.kind().to_string())
            .and_then(|printed| repositories::parse(&printed))
    })
    .await?
}

/// Record one repository at one level, or stop recording it.
///
/// The answer is **the whole scan, read again**, not the change that was asked for: the
/// engine decides what a repository's level is, and a control drawn from the click rather
/// than from the answer is a control that lies the first time the engine refuses.
#[tauri::command]
async fn engine_repository_level(
    shell: State<'_, Shell>,
    key: String,
    level: String,
) -> Result<Vec<repositories::Repository>, String> {
    let Some(arguments) = repositories::arguments(&key, &level) else {
        // Not a user-visible sentence: the page can only send one of three words and a key
        // out of the scan, so anything else is a defect in the bridge.
        return Err(format!("no such capture level: {level}"));
    };
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        let engine = engine::shared();
        let borrowed: Vec<&str> = arguments.iter().map(String::as_str).collect();
        engine
            .read(remembered.as_deref(), &borrowed)
            .and_then(|_| engine.read(remembered.as_deref(), &["init", "--scan", "--json"]))
            .map_err(|error| error.kind().to_string())
            .and_then(|printed| repositories::parse(&printed))
    })
    .await?
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceUpdate {
    sources: Vec<sources::Source>,
    repositories: Vec<repositories::Repository>,
}

#[tauri::command]
async fn engine_sources(shell: State<'_, Shell>) -> Result<Vec<sources::Source>, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        engine::shared()
            .read(remembered.as_deref(), &["sources", "--json"])
            .map_err(source_engine_error)
            .and_then(|printed| sources::parse(&printed))
    })
    .await?
}

#[tauri::command]
async fn engine_source_add(
    shell: State<'_, Shell>,
    kind: String,
    name: String,
    home: String,
) -> Result<SourceUpdate, String> {
    let args = sources::add_arguments(&kind, &name, &home).ok_or("invalid source details")?;
    source_change(shell, args).await
}

#[tauri::command]
async fn engine_source_set(
    shell: State<'_, Shell>,
    id: String,
    enabled: bool,
    name: Option<String>,
    home: Option<String>,
) -> Result<SourceUpdate, String> {
    let args = sources::set_arguments(&id, enabled, name.as_deref(), home.as_deref())
        .ok_or("invalid source details")?;
    source_change(shell, args).await
}

async fn source_change(shell: State<'_, Shell>, args: Vec<String>) -> Result<SourceUpdate, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        let engine = engine::shared();
        let borrowed: Vec<&str> = args.iter().map(String::as_str).collect();
        let sources = engine
            .read(remembered.as_deref(), &borrowed)
            .map_err(source_engine_error)
            .and_then(|printed| sources::parse(&printed))?;
        let repositories = engine
            .read(remembered.as_deref(), &["init", "--scan", "--json"])
            .map_err(source_engine_error)
            .and_then(|printed| repositories::parse(&printed))?;
        Ok(SourceUpdate {
            sources,
            repositories,
        })
    })
    .await?
}

fn source_engine_error(error: engine::EngineError) -> String {
    let detail = error.detail();
    if detail.is_empty() {
        error.kind().to_string()
    } else {
        detail
    }
}

/// Whether a review is ready, with the engine's own sentence when it is.
#[tauri::command]
async fn engine_readiness(shell: State<'_, Shell>) -> Result<Option<readiness::Readiness>, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        let engine = engine::shared();
        let printed = engine
            .read(remembered.as_deref(), &["status", "--json"])
            .map_err(|error| error.kind().to_string())?;
        let Some(mut found) = readiness::parse(&printed) else {
            // An engine that does not answer this question yet. Nothing is said rather
            // than "not ready", which would be this app inventing a verdict.
            return Ok(None);
        };
        // The sentence is only read where it is printed. A store that is not ready gets a
        // line composed in the reader's own language from the numbers above, so a second
        // status would be a second subprocess for something nothing shows.
        if found.ready {
            found.sentence = engine
                .read(remembered.as_deref(), &["status"])
                .ok()
                .and_then(|text| readiness::review_line(&text));
        }
        Ok(Some(found))
    })
    .await?
}

/* --- what the engine recorded about its runs ------------------------------------------
 *
 * `runs.jsonl` is a file the engine writes and this app reads, beside the store, so it is
 * read here rather than asked of the engine: `runlog.rs` says how. `prudence diagnose` is
 * the one thing the page may start from the Engine tab, and like every command it is a
 * constant on this side.
 */

/// The last `count` runs the engine recorded, newest first, and how many finished lines
/// of the log could not be read. An engine older than the log answers with none.
#[tauri::command]
async fn engine_runs(count: usize) -> Result<runlog::Runs, String> {
    let wanted = count.min(runlog::MOST);
    scheduled(move || {
        runlog::read(&runlog::file(&store::logs_dir()), wanted).map_err(|error| {
            tracing::error!(target: "runs", error = %error, "the run log could not be read");
            error.to_string()
        })
    })
    .await?
}

/// Run `prudence diagnose`, and say which folder it wrote.
#[tauri::command]
async fn engine_diagnose(shell: State<'_, Shell>) -> Result<runlog::Diagnosis, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    let diagnosis = scheduled(move || {
        let directory = runlog::bundles_dir(&store::data_dir());
        let before = runlog::bundles(&directory);
        match engine::shared().read(remembered.as_deref(), runlog::DIAGNOSE) {
            Err(error) => runlog::Diagnosis::failed(&error),
            Ok(_) => runlog::Diagnosis::found(runlog::made(&before, &runlog::bundles(&directory))),
        }
    })
    .await?;
    if let Some(path) = &diagnosis.path {
        *shell.bundle.lock().unwrap() = Some(PathBuf::from(path));
    }
    Ok(diagnosis)
}

/// Show a folder in the file manager, **by name**, on the rule `open_link` keeps: the page
/// never hands the shell a path. `logs` is the engine's log directory; `diagnose` is the
/// bundle the last diagnosis from this app wrote.
#[tauri::command]
fn reveal(app: AppHandle, shell: State<'_, Shell>, name: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let path = match name.as_str() {
        "logs" => store::logs_dir(),
        "diagnose" => shell
            .bundle
            .lock()
            .unwrap()
            .clone()
            .ok_or_else(|| String::from("no diagnosis has been written from this app yet"))?,
        _ => return Err(format!("no such place: {name}")),
    };
    app.opener()
        .reveal_item_in_dir(&path)
        .map_err(|error| error.to_string())
}

/* --- the model settings --------------------------------------------------------------
 *
 * The app never calls a model. These two read what `prudence config model` prints and set
 * the one field the Model tab offers, which is the language the engine writes its optional
 * prose in. `model.rs` holds the parsing and the three words the language may be.
 */

#[tauri::command]
async fn model_read(shell: State<'_, Shell>) -> Result<model::ModelSettings, String> {
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        engine::shared()
            .read(remembered.as_deref(), &["config", "model"])
            .map(|printed| model::parse(&printed))
            .map_err(|error| error.kind().to_string())
    })
    .await?
}

/// `prudence config model --language <code>`, for one of three codes.
///
/// The word is checked against `model::LANGUAGES` **here**, before anything is spawned, so
/// a page that sent something else reaches no command line at all. The answer is the
/// settings as they are after the change, read back from the engine rather than assumed.
#[tauri::command]
async fn model_set_language(
    shell: State<'_, Shell>,
    language: String,
) -> Result<model::ModelSettings, String> {
    let Some(arguments) = model::language_arguments(&language) else {
        // Not a user-visible sentence: the page can only send one of three words, so
        // anything else is a defect in the bridge rather than something to translate.
        return Err(format!("no such model language: {language}"));
    };
    let remembered = shell.memory.read().usable_engine().map(str::to_string);
    scheduled(move || {
        let engine = engine::shared();
        engine
            .read(remembered.as_deref(), &arguments)
            .inspect(|_| setting_written("model language", Some(&language)))
            .and_then(|_| engine.read(remembered.as_deref(), &["config", "model"]))
            .map(|printed| model::parse(&printed))
            .map_err(|error| error.kind().to_string())
    })
    .await?
}

/* --- the General tab ------------------------------------------------------------------
 *
 * Four settings, four commands, and one event. Each command answers with the whole
 * settings block rather than with nothing, so the page draws what is in force instead of
 * what it just asked for: open-at-login in particular can refuse, and a control that ticks
 * itself on a refusal is a control that lies.
 */

/// Told to both pages whenever a setting changes, so the panel follows a language chosen
/// in the window. The payload is empty, on the same rule as `store-changed`: there is one
/// way to get the settings and it is `shell_info`.
const SETTINGS_CHANGED: &str = "settings-changed";

#[tauri::command]
fn settings_read(app: AppHandle, shell: State<'_, Shell>) -> AppSettings {
    app_settings(&app, &shell.memory)
}

#[tauri::command]
fn settings_language(
    app: AppHandle,
    shell: State<'_, Shell>,
    language: String,
) -> Result<AppSettings, String> {
    if !shell.memory.set_language(&language) {
        return Err(format!("no such language: {language}"));
    }
    shell.memory.save()?;
    setting_written("language", Some(&language));
    Ok(announce_settings(&app, &shell.memory))
}

/// The appearance, set on the app's own windows as well as remembered.
///
/// **Two halves, and both are needed.** The window theme is what makes the titlebar, the
/// scrollbars and the system's own material change; the page's `data-theme` is what makes
/// the content change, and the page reads the setting out of `shell_info` rather than
/// being told separately. Neither half alone gives a dark window: setting only the theme
/// leaves a light page inside a dark frame.
#[tauri::command]
fn settings_appearance(
    app: AppHandle,
    shell: State<'_, Shell>,
    appearance: String,
) -> Result<AppSettings, String> {
    if !shell.memory.set_appearance(&appearance) {
        return Err(format!("no such appearance: {appearance}"));
    }
    shell.memory.save()?;
    setting_written("appearance", Some(&appearance));
    apply_appearance(&app, &appearance);
    Ok(announce_settings(&app, &shell.memory))
}

#[tauri::command]
fn settings_timed_ingest(
    app: AppHandle,
    shell: State<'_, Shell>,
    minutes: u32,
) -> Result<AppSettings, String> {
    if !shell.memory.set_ingest_minutes(minutes) {
        return Err(format!("no such interval: {minutes}"));
    }
    shell.memory.save()?;
    shell.timer.set(minutes);
    setting_written("timed ingest", Some(&minutes.to_string()));
    Ok(announce_settings(&app, &shell.memory))
}

/// Register, or unregister, this copy of the app as a login item.
///
/// The answer is read back from the system rather than assumed: macOS can refuse a login
/// item for a copy that is not where it expects one, and the page shows what is actually
/// in force with the plugin's own reason under it.
#[tauri::command]
fn settings_open_at_login(
    app: AppHandle,
    shell: State<'_, Shell>,
    enabled: bool,
) -> Result<AppSettings, String> {
    let asked = if enabled {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    };
    match asked {
        Ok(()) => setting_written("open at login", Some(if enabled { "on" } else { "off" })),
        // The plugin's own words, which the General tab shows under the control.
        Err(error) => {
            tracing::error!(target: "settings", setting = "open at login", error = %error, "setting refused")
        }
    }
    Ok(announce_settings(&app, &shell.memory))
}

/// A setting was written, in the app log: which one, and its value unless the value is a
/// path, which carries the user's name and leaves the machine with the log's tail.
fn setting_written(setting: &str, value: Option<&str>) {
    match value {
        Some(value) => tracing::info!(target: "settings", setting, value, "setting written"),
        None => tracing::info!(target: "settings", setting, "setting written"),
    }
}

/// The settings as they now are, told to both pages.
fn announce_settings(app: &AppHandle, memory: &Memory) -> AppSettings {
    let settings = app_settings(app, memory);
    if let Err(error) = app.emit(SETTINGS_CHANGED, ()) {
        eprintln!("[settings] could not announce: {error}");
    }
    settings
}

/// The links the About tab offers, by name.
///
/// **The page asks by name and the shell owns the address.** A command that took a URL
/// would be a command that opens whatever it is handed, and the whole reason the frontend
/// talks to the shell through one door is that the door decides.
const LINKS: &[(&str, &str)] = &[
    ("project", "https://github.com/averatec0773/prudence"),
    ("developer", "https://github.com/averatec0773"),
    // The anchors are GitHub's own, taken from the headings in the repository's README:
    // "## Install" and "## What it records and what it never records".
    (
        "install",
        "https://github.com/averatec0773/prudence#install",
    ),
    (
        "recorded",
        "https://github.com/averatec0773/prudence#what-it-records-and-what-it-never-records",
    ),
];

#[tauri::command]
fn open_link(app: AppHandle, name: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let Some((_, url)) = LINKS.iter().find(|(key, _)| *key == name) else {
        return Err(format!("no such link: {name}"));
    };
    app.opener()
        .open_url(*url, None::<&str>)
        .map_err(|error| error.to_string())
}

/// The page's own report of what it ended up drawing, on the shell's standard error.
/// An agent cannot open the web inspector of a window it did not click, and a spike that
/// cannot say what the page computed is a spike that guesses.
#[tauri::command]
fn page_log(app: AppHandle, line: String) {
    let elapsed = app.state::<Shell>().started.elapsed().as_millis();
    eprintln!("[page] {elapsed} ms: {line}");
}

#[tauri::command]
fn app_quit(app: AppHandle) {
    // A lost frame is a default frame at the next launch.
    let _ = app.state::<Shell>().memory.save();
    app.exit(0);
}

/// A language forced for one launch, for a screenshot run. It beats the setting, because
/// a picture has to be of the language the caller asked for and not of whatever this
/// machine last remembered.
///
/// **Not** behind the `harness` feature, unlike the other hooks: `shot.py` sets it on a
/// harness build, and it was here before the setting existed. It stays because a forced
/// language changes nothing a user can reach and is how every screenshot is taken.
fn forced_language() -> Option<String> {
    match std::env::var("PRUDENCE_FORCE_LANGUAGE").ok()?.as_str() {
        "en" => Some("en".into()),
        "zh-Hans" | "zh" => Some("zh-Hans".into()),
        _ => None,
    }
}

/// The General tab's language, as a language the page can draw in. `system` is null: the
/// page follows the machine when it is told nothing.
fn chosen_language(setting: &str) -> Option<String> {
    (setting != "system").then(|| setting.to_string())
}

/// The appearance a screenshot run forced, or the one the General tab remembered.
fn appearance_now(memory: &Memory) -> String {
    std::env::var("PRUDENCE_FORCE_APPEARANCE")
        .ok()
        .filter(|value| value == "light" || value == "dark")
        .unwrap_or_else(|| memory.read().usable_appearance().to_string())
}

/// Pin both windows to an appearance, or hand them back to the system.
///
/// `set_theme(None)` is what "follow the system" is: a window pinned to light stays light
/// through a system change until it is told otherwise.
fn apply_appearance(app: &AppHandle, appearance: &str) {
    let theme = match appearance {
        "dark" => Some(tauri::Theme::Dark),
        "light" => Some(tauri::Theme::Light),
        _ => None,
    };
    for label in [PANEL, MAIN] {
        if let Some(window) = app.get_webview_window(label) {
            set_theme(&window, theme);
        }
    }
}

fn set_theme(window: &WebviewWindow, theme: Option<tauri::Theme>) {
    if let Err(error) = window.set_theme(theme) {
        eprintln!("[prudence] the window would not take the theme: {error}");
    }
}

/// May the panel dismiss itself because it lost the focus?
///
/// Not while something else is legitimately holding it. Two things do: a script driving
/// the app, which is absent from a release build, and a file picker, which is not, because
/// a user can open one. Without this the panel disappears the instant the picker appears,
/// taking the interface that asked for the file with it.
fn may_dismiss_on_focus_loss() -> bool {
    !scripted() && !engine::dialog_is_open()
}

/// True while a script is driving the app, so the panel does not dismiss itself out from
/// under a screenshot. Always false in a release build.
fn scripted() -> bool {
    #[cfg(feature = "harness")]
    {
        harness::driving()
    }
    #[cfg(not(feature = "harness"))]
    {
        false
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let started = std::time::Instant::now();
    // Before anything else, so the first thing the app does is on the record.
    applog::start(&store::logs_dir());
    tracing::info!(
        target: "app",
        version = env!("CARGO_PKG_VERSION"),
        contract = ?contract::SUPPORTED,
        os = std::env::consts::OS,
        arch = std::env::consts::ARCH,
        "app started"
    );
    // The store is found the way `src/prudence/paths.py` finds it and no other way. There
    // was a `PRUDENCE_DB` override here in the spike; it is gone, because the engine does
    // not honour that name and a guessed variable of exactly that shape is how an agent
    // once wrote to the founder's real store.
    let database = store::database_file();

    tauri::Builder::default()
        .plugin(tauri_plugin_positioner::init())
        .plugin(tauri_plugin_dialog::init())
        // Opening a link in the system browser, for the three the About tab offers. The
        // page asks by name and `LINKS` holds the addresses, so no webview capability is
        // granted and no URL crosses the bridge.
        .plugin(tauri_plugin_opener::init())
        // Open at login. `LaunchAgent` rather than the newer API because it is the one
        // that works for an app that is not in /Applications, which is where this app is
        // while it is being built.
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            store_read,
            shell_info,
            page_log,
            panel_fit,
            panel_hide,
            window_open,
            window_close,
            section_set,
            panel_range_set,
            engine_status,
            engine_activity,
            engine_run,
            engine_choose,
            engine_forget,
            engine_install,
            engine_repositories,
            engine_repository_level,
            engine_sources,
            engine_source_add,
            engine_source_set,
            engine_readiness,
            engine_runs,
            engine_diagnose,
            reveal,
            model_read,
            model_set_language,
            settings_read,
            settings_language,
            settings_appearance,
            settings_timed_ingest,
            settings_open_at_login,
            open_link,
            app_quit
        ])
        .setup(move |app| {
            let memory = Memory::load(app.handle());
            let timer = Arc::new(timer::Timer::new(memory.read().usable_ingest_minutes()));
            app.manage(Shell {
                database,
                started,
                material: Mutex::new(platform::MaterialReport::none("not applied yet")),
                tray_highlight_works: Mutex::new(false),
                memory,
                timer: timer.clone(),
                bundle: Mutex::new(None),
            });

            // No Dock icon and no app switcher entry until a window is open. Set before
            // the first window is shown so nothing flashes.
            platform::set_dock_visible(app.handle(), false);

            let panel_window = app
                .get_webview_window(PANEL)
                .expect("the panel window is declared in tauri.conf.json");
            let main_window = app
                .get_webview_window(MAIN)
                .expect("the main window is declared in tauri.conf.json");

            // The setting, or what a screenshot run forced. Applied before the first
            // material is, so a window never flashes the system's appearance first.
            apply_appearance(app.handle(), &appearance_now(&app.state::<Shell>().memory));

            let report = platform::apply_material(&panel_window, platform::Surface::Panel);
            eprintln!("[prudence] panel material: {}", report.kind);
            for attempt in &report.attempts {
                eprintln!(
                    "[prudence]   {} -> {} ({})",
                    attempt.api,
                    if attempt.ok { "ok" } else { "no" },
                    attempt.detail
                );
            }
            *app.state::<Shell>().material.lock().unwrap() = report;

            // The window carries the same material: the sidebar and the toolbar are the
            // navigation layer, and the screens inside them are opaque in CSS.
            let window_report = platform::apply_material(&main_window, platform::Surface::Window);
            eprintln!("[prudence] window material: {}", window_report.kind);

            let quit = MenuItem::with_id(app, "quit", "Quit Prudence", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Open Panel", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            TrayIconBuilder::with_id("prudence")
                .icon(tauri::image::Image::from_bytes(include_bytes!(
                    "../icons/tray-template.png"
                ))?)
                // The macOS convention: a black-and-transparent image the system recolours
                // for light, dark and selected. Ignored on Windows, which wants colour.
                .icon_as_template(true)
                .tooltip("Prudence")
                // Left click is ours, right click opens the menu.
                .show_menu_on_left_click(false)
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        // A lost frame is a default frame at the next launch.
                        let _ = app.state::<Shell>().memory.save();
                        app.exit(0)
                    }
                    "show" => panel::show(app),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    let app = tray.app_handle();
                    // Without this the panel lands in the top-left corner instead of under
                    // the icon: the plugin learns where the tray is only from this call.
                    tauri_plugin_positioner::on_tray_event(app, &event);
                    // Every tray event, so that one human click can be held against what
                    // the shell actually received. An agent cannot click a menu bar.
                    if !matches!(event, TrayIconEvent::Move { .. }) {
                        eprintln!("[tray] {event:?}");
                    }
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        panel::toggle(app);
                    }
                })
                .build(app)?;

            // The store, read before anybody asks for it.
            //
            // Both pages ask as soon as their JavaScript runs, and on the founder's 851 MB
            // store the seven views take 1,225 ms from cold and 68 ms once the file is in
            // the page cache. Those pages are about two seconds away from asking, and the
            // shell has nothing else to do with that time, so it spends it on the one
            // thing it is certain to be asked for. Nothing waits on this thread: a page
            // that gets in first simply does the read itself, and the second one is served
            // from the same snapshot either way.
            let warm = app.state::<Shell>().database.clone();
            std::thread::spawn(move || {
                let began = std::time::Instant::now();
                match store::snapshot(&warm) {
                    Ok(_) => eprintln!(
                        "[store] read at launch in {} ms",
                        began.elapsed().as_millis()
                    ),
                    // Not a failure of the app: the page asks again and reports whatever it
                    // is told. This line is so the reason is on the record either way.
                    Err(error) => eprintln!("[store] could not read at launch: {error}"),
                }
            });

            // The window follows the store: an ingest that lands while the app is open
            // refreshes the pages instead of leaving them an hour behind.
            watcher::watch(app.handle(), app.state::<Shell>().database.clone());

            // The timed ingest. One thread, started here and not when a window opens: the
            // setting exists precisely for the hours this app spends with no window.
            timer::start(app.handle(), timer);

            #[cfg(feature = "harness")]
            harness::start(app.handle());

            Ok(())
        })
        .on_window_event(|window, event| {
            let app = window.app_handle();
            match (window.label(), event) {
                // Not `Focused(false)` alone: a script driving the app needs a panel
                // that stays put while something else has the focus.
                (PANEL, tauri::WindowEvent::Focused(false)) if may_dismiss_on_focus_loss() => {
                    panel::hide(app);
                }
                (MAIN, tauri::WindowEvent::Moved(_) | tauri::WindowEvent::Resized(_)) => {
                    if let Some(main) = app.get_webview_window(MAIN) {
                        if main.is_visible().unwrap_or(false) {
                            crate::window::remember_frame(&main, app);
                        }
                    }
                }
                (MAIN, tauri::WindowEvent::CloseRequested { api, .. }) => {
                    // A menu bar app does not quit when its window closes.
                    api.prevent_close();
                    crate::window::close(app);
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("the Prudence shell failed to start")
        .run(|app, event| {
            // Cmd-Q goes through Tauri's default application menu and through none of the
            // three places that used to save, so the window's position and section were
            // lost on the most ordinary way of quitting.
            if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
                // A lost frame is a default frame at the next launch.
                let _ = app.state::<Shell>().memory.save();
            }
        });
}
