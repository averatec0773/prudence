//! The shell: a status item, a panel that hangs under it, a window with the screens in it,
//! and a read-only view of the store.
//!
//! Phase 1, batch 1. The window's screens are placeholders; what this batch is really for
//! is whether the compositor holds. See `docs/reports/desktop/02-window-shell.md`.

mod contract;
mod panel;
mod platform;
mod store;
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
use std::sync::Mutex;

use serde::Serialize;
use serde_json::Value;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, State, WebviewWindow};

use ui_state::Memory;

/// The two windows. The frontend never names either; `panel.rs` and `window.rs` do.
pub const PANEL: &str = "panel";
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
}

#[derive(Serialize)]
pub struct ShellInfo {
    version: String,
    database: String,
    material: platform::MaterialReport,
    tray_highlight: bool,
    platform: Vec<(String, String)>,
    supported_contract: Vec<u32>,
    /// `en` or `zh-Hans` when the screenshot hook forced one, otherwise null and the page
    /// keeps the frontend's default. Proper language selection is batch 8.
    language: Option<String>,
    /// The section the window last had, or null when this build no longer has it.
    section: Option<String>,
    /// Whether this build carries the automation hooks. The page exposes its own test
    /// entry point only when it does.
    harness: bool,
    /// How far down a script wants the screen scrolled before it is photographed.
    /// Always null in a release build.
    scroll: Option<u32>,
}

/// `async` so that a slow disk cannot freeze the panel: a non-async command runs on the
/// main thread, and this one issues seven selects. They take about 60 ms on the founder's
/// 815 MB store today, which is fine, and the failure mode if that ever changes is a
/// frozen window rather than a slow one.
#[tauri::command(async)]
fn store_read(shell: State<'_, Shell>) -> Result<Value, String> {
    store::read(&shell.database).map_err(|error| error.to_string())
}

#[tauri::command]
fn shell_info(shell: State<'_, Shell>) -> ShellInfo {
    ShellInfo {
        version: env!("CARGO_PKG_VERSION").into(),
        database: shell.database.display().to_string(),
        material: shell.material.lock().unwrap().clone(),
        tray_highlight: *shell.tray_highlight_works.lock().unwrap(),
        platform: platform::describe(),
        supported_contract: store::supported_contract(),
        language: forced_language(),
        section: shell.memory.read().usable_section().map(str::to_string),
        harness: cfg!(feature = "harness"),
        scroll: scripted_scroll(),
    }
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

/// The window's current section, so the next launch opens on it.
#[tauri::command]
fn section_set(shell: State<'_, Shell>, section: String) {
    shell.memory.set_section(&section);
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
    app.state::<Shell>().memory.save();
    app.exit(0);
}

/// The language and the appearance are settings that batch 8 will read from the store's
/// own configuration. Until then they are read from the environment, which is why these
/// two are **not** behind the `harness` feature: they are the setting, early.
fn forced_language() -> Option<String> {
    match std::env::var("PRUDENCE_FORCE_LANGUAGE").ok()?.as_str() {
        "en" => Some("en".into()),
        "zh-Hans" | "zh" => Some("zh-Hans".into()),
        _ => None,
    }
}

fn forced_appearance(window: &WebviewWindow) {
    let Ok(appearance) = std::env::var("PRUDENCE_FORCE_APPEARANCE") else {
        return;
    };
    let theme = match appearance.as_str() {
        "dark" => Some(tauri::Theme::Dark),
        "light" => Some(tauri::Theme::Light),
        _ => return,
    };
    let _ = window.set_theme(theme);
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
        .invoke_handler(tauri::generate_handler![
            store_read,
            shell_info,
            page_log,
            panel_fit,
            panel_hide,
            window_open,
            window_close,
            section_set,
            app_quit
        ])
        .setup(move |app| {
            app.manage(Shell {
                database,
                started,
                material: Mutex::new(platform::MaterialReport::none("not applied yet")),
                tray_highlight_works: Mutex::new(false),
                memory: Memory::load(app.handle()),
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

            forced_appearance(&panel_window);
            forced_appearance(&main_window);

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
                        app.state::<Shell>().memory.save();
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

            #[cfg(feature = "harness")]
            harness::start(app.handle());

            Ok(())
        })
        .on_window_event(|window, event| {
            let app = window.app_handle();
            match (window.label(), event) {
                // Not `Focused(false)` alone: a script driving the app needs a panel
                // that stays put while something else has the focus.
                (PANEL, tauri::WindowEvent::Focused(false)) if !scripted() => {
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
                app.state::<Shell>().memory.save();
            }
        });
}
