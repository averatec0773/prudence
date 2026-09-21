//! The shell: a status item, a panel that hangs under it, a window with the screens in it,
//! and a read-only view of the store.
//!
//! Phase 1, batch 1. The window's screens are placeholders; what this batch is really for
//! is whether the compositor holds. See `docs/reports/desktop/02-window-shell.md`.

mod panel;
mod platform;
mod store;
mod stress;
mod ui_state;
mod window;

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
/// The screenshot backdrop, built only when the hook asks for it.
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
    supported_contract: Vec<i64>,
    /// `en` or `zh-Hans` when the screenshot hook forced one, otherwise null and the page
    /// keeps the frontend's default. Proper language selection is batch 8.
    language: Option<String>,
    /// The section the window last had, or null when this build no longer has it.
    section: Option<String>,
}

#[tauri::command]
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
        supported_contract: store::SUPPORTED_CONTRACT.to_vec(),
        language: forced_language(),
        section: shell.memory.read().usable_section().map(str::to_string),
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

/// An agent cannot click a menu-bar icon and there is no supported way to script one, so
/// the hooks the Swift app grew for screenshots exist here too. None of them is reachable
/// by anything a user does.
fn screenshot_hooks(window: &WebviewWindow) {
    if let Ok(appearance) = std::env::var("PRUDENCE_FORCE_APPEARANCE") {
        let theme = match appearance.as_str() {
            "dark" => Some(tauri::Theme::Dark),
            "light" => Some(tauri::Theme::Light),
            _ => None,
        };
        if theme.is_some() {
            let _ = window.set_theme(theme);
        }
    }
}

fn forced_language() -> Option<String> {
    match std::env::var("PRUDENCE_FORCE_LANGUAGE").ok()?.as_str() {
        "en" => Some("en".into()),
        "zh-Hans" | "zh" => Some("zh-Hans".into()),
        _ => None,
    }
}

fn panel_stays_open() -> bool {
    std::env::var("PRUDENCE_PANEL_OPEN").is_ok_and(|value| !value.is_empty() && value != "0")
}

fn backdrop_wanted() -> bool {
    std::env::var("PRUDENCE_BACKDROP").is_ok_and(|value| !value.is_empty() && value != "0")
}

fn window_opens_at_launch() -> bool {
    std::env::var("PRUDENCE_WINDOW_OPEN").is_ok_and(|value| !value.is_empty() && value != "0")
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

            screenshot_hooks(&panel_window);
            screenshot_hooks(&main_window);

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

            // The status item is not laid out for a moment after launch, and a panel shown
            // before that cannot be anchored under it. A user's first click is always later
            // than this; the screenshot hooks have to wait on purpose.
            if panel_stays_open()
                || window_opens_at_launch()
                || stress::plan().is_some()
                || backdrop_wanted()
            {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    if backdrop_wanted() {
                        let backdrop = handle.clone();
                        let _ = handle
                            .clone()
                            .run_on_main_thread(move || window::open_backdrop(&backdrop));
                    }
                    std::thread::sleep(std::time::Duration::from_millis(1200));
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
                    if let Some(plan) = stress::plan() {
                        stress::run(&handle, plan);
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            let app = window.app_handle();
            match (window.label(), event) {
                // Not `Focused(false)` alone: the screenshot hooks and the stress run
                // both need a panel that stays put while something else has the focus.
                (PANEL, tauri::WindowEvent::Focused(false))
                    if !panel_stays_open() && stress::plan().is_none() =>
                {
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
        .run(tauri::generate_context!())
        .expect("the Prudence shell failed to start");
}
