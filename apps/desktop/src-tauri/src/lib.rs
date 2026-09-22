//! The shell: a status item, a panel that hangs under it, a window with the screens in it,
//! and a read-only view of the store.
//!
//! Phase 1, batch 1. The window's screens are placeholders; what this batch is really for
//! is whether the compositor holds. See `docs/reports/desktop/02-window-shell.md`.

mod contract;
mod engine;
mod installer;
mod model;
mod panel;
mod platform;
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
    /// Whether this build carries the automation hooks. The page exposes its own test
    /// entry point only when it does.
    harness: bool,
    /// How far down a script wants the screen scrolled before it is photographed.
    /// Always null in a release build.
    scroll: Option<u32>,
    /// A button a script wants pressed once the page has drawn. Never set in a release.
    press: Option<String>,
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

#[tauri::command]
async fn store_read(shell: State<'_, Shell>) -> Result<Value, String> {
    let database = shell.database.clone();
    scheduled(move || store::read(&database).map_err(|error| error.to_string())).await?
}

#[tauri::command]
fn shell_info(app: AppHandle, shell: State<'_, Shell>) -> ShellInfo {
    let settings = app_settings(&app, &shell.memory);
    ShellInfo {
        version: env!("CARGO_PKG_VERSION").into(),
        database: shell.database.display().to_string(),
        material: shell.material.lock().unwrap().clone(),
        tray_highlight: *shell.tray_highlight_works.lock().unwrap(),
        platform: platform::describe(),
        supported_contract: store::supported_contract(),
        language: forced_language().or_else(|| chosen_language(&settings.language)),
        settings,
        section: scripted_section()
            .or_else(|| shell.memory.read().usable_section().map(str::to_string)),
        harness: cfg!(feature = "harness"),
        scroll: scripted_scroll(),
        press: scripted_press(),
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

/// Run `prudence ingest` or `prudence review`, and answer with what the engine said.
///
/// The page waits on this promise, which is how it knows a run is still going. Nothing is
/// plumbed into the screens: `watcher.rs` already refreshes every page when the store
/// changes, so a successful run's new figures arrive on their own.
#[tauri::command]
async fn engine_run(
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
        scheduled(move || engine::shared().run(remembered.as_deref(), action, force)).await;
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
    // launch, and the next `Choose` writes again.
    let _ = shell.memory.save();
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
    if let Err(error) = asked {
        eprintln!("[settings] open at login: {error}");
    }
    Ok(announce_settings(&app, &shell.memory))
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
            engine_status,
            engine_run,
            engine_choose,
            engine_forget,
            engine_install,
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
