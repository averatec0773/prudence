//! The shell: a status item, a panel that hangs under it, and a read-only view of the store.
//!
//! Spike scope. Nothing here writes to the store, runs the CLI, updates itself or signs
//! anything; see `docs/reports/desktop/00-spike.md` for what was proved and what was not.

mod panel;
mod platform;
mod store;

use std::path::PathBuf;
use std::sync::Mutex;

use serde::Serialize;
use serde_json::Value;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, State, WebviewWindow};

/// The one window. The frontend never names it; `panel.rs` does.
pub const PANEL: &str = "panel";

pub struct Shell {
    pub database: PathBuf,
    pub started: std::time::Instant,
    pub material: Mutex<platform::MaterialReport>,
    pub tray_highlight_works: Mutex<bool>,
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
    /// keeps the frontend's default. Proper language selection is not in the spike.
    language: Option<String>,
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

/// The page's own report of what it ended up drawing, on the shell's standard error.
/// An agent cannot open the web inspector of a window it did not click, and a spike that
/// cannot say what the page computed is a spike that guesses.
#[tauri::command]
fn page_log(app: AppHandle, line: String) {
    let elapsed = app.state::<Shell>().started.elapsed().as_millis();
    let geometry = app
        .get_webview_window(PANEL)
        .map(|window| {
            format!(
                "visible={:?} position={:?} size={:?} scale={:?}",
                window.is_visible(),
                window.outer_position(),
                window.outer_size(),
                window.scale_factor()
            )
        })
        .unwrap_or_else(|| "no panel window".into());
    eprintln!("[page] {elapsed} ms: {line}\n[panel] {geometry}");
}

#[tauri::command]
fn app_quit(app: AppHandle) {
    app.exit(0);
}

/// An agent cannot click a menu-bar icon and there is no supported way to script one, so
/// the two hooks the Swift app grew for screenshots exist here too. Neither is reachable
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

/// `PRUDENCE_PANEL_STRESS=n` opens and closes the panel n times and leaves it open.
///
/// Wry issue 1848 reports the macOS 26 WKWebView compositor giving up after a dozen or so
/// interactions. This is the only repeated interaction the spike's panel has, so it is the
/// only form of that question the spike can answer; the screenshot after it is the check.
fn stress_rounds() -> u32 {
    std::env::var("PRUDENCE_PANEL_STRESS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(0)
}

fn panel_stays_open() -> bool {
    std::env::var("PRUDENCE_PANEL_OPEN").is_ok_and(|value| !value.is_empty() && value != "0")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let started = std::time::Instant::now();
    let database = std::env::var_os("PRUDENCE_DB")
        .map(PathBuf::from)
        .unwrap_or_else(store::database_file);

    tauri::Builder::default()
        .plugin(tauri_plugin_positioner::init())
        .manage(Shell {
            database,
            started,
            material: Mutex::new(platform::MaterialReport::none("not applied yet")),
            tray_highlight_works: Mutex::new(false),
        })
        .invoke_handler(tauri::generate_handler![
            store_read, shell_info, page_log, panel_fit, panel_hide, app_quit
        ])
        .setup(|app| {
            // No Dock icon and no app switcher entry: this is a menu-bar app, and the
            // policy is set before the first window is shown so nothing flashes.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let window = app
                .get_webview_window(PANEL)
                .expect("the panel window is declared in tauri.conf.json");

            screenshot_hooks(&window);

            let report = platform::apply_material(&window);
            eprintln!("[prudence] material: {}", report.kind);
            for attempt in &report.attempts {
                eprintln!(
                    "[prudence]   {} -> {} ({})",
                    attempt.api,
                    if attempt.ok { "ok" } else { "no" },
                    attempt.detail
                );
            }
            *app.state::<Shell>().material.lock().unwrap() = report;

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
                    "quit" => app.exit(0),
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

            if panel_stays_open() {
                // The status item is not laid out for a moment after launch, and a panel
                // shown before that cannot be anchored under it. A user's first click is
                // always later than this; the screenshot hook has to wait on purpose.
                let handle = app.handle().clone();
                let rounds = stress_rounds();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(1200));
                    for round in 0..rounds {
                        for open in [true, false] {
                            let handle = handle.clone();
                            let _ = handle.clone().run_on_main_thread(move || {
                                if open {
                                    panel::show(&handle)
                                } else {
                                    panel::hide(&handle)
                                }
                            });
                            std::thread::sleep(std::time::Duration::from_millis(220));
                        }
                        eprintln!("[stress] round {} of {rounds}", round + 1);
                    }
                    let _ = handle
                        .clone()
                        .run_on_main_thread(move || panel::show(&handle));
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != PANEL {
                return;
            }
            if let tauri::WindowEvent::Focused(false) = event {
                if !panel_stays_open() {
                    panel::hide(window.app_handle());
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("the Prudence shell failed to start");
}
