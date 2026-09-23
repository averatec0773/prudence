//! Windows: Mica on 11, Acrylic before it. Untested on real hardware; see the spike report.

use tauri::{AppHandle, WebviewWindow};
use window_vibrancy::{apply_acrylic, apply_mica};

use super::{Attempt, MaterialReport, Surface, TrayAnchor};

pub fn apply_material(window: &WebviewWindow, _surface: Surface) -> MaterialReport {
    let mut attempts = Vec::new();

    match apply_mica(window, None) {
        Ok(()) => {
            attempts.push(Attempt {
                api: "window_vibrancy::apply_mica".into(),
                ok: true,
                detail: "DWM Mica".into(),
            });
            return MaterialReport {
                kind: "mica".into(),
                attempts,
                detail: "Windows 11".into(),
            };
        }
        Err(error) => attempts.push(Attempt {
            api: "window_vibrancy::apply_mica".into(),
            ok: false,
            detail: error.to_string(),
        }),
    }

    match apply_acrylic(window, None) {
        Ok(()) => {
            attempts.push(Attempt {
                api: "window_vibrancy::apply_acrylic".into(),
                ok: true,
                detail: "DWM Acrylic".into(),
            });
            MaterialReport {
                kind: "acrylic".into(),
                attempts,
                detail: "Windows 10 v1809 or newer".into(),
            }
        }
        Err(error) => {
            attempts.push(Attempt {
                api: "window_vibrancy::apply_acrylic".into(),
                ok: false,
                detail: error.to_string(),
            });
            MaterialReport {
                kind: "none".into(),
                attempts,
                detail: "no material available".into(),
            }
        }
    }
}

/// Windows draws no selected state behind a notification-area icon, so there is nothing
/// to set and nothing to fake: the answer is honestly "this platform has no such state".
/// The notification area gives no frame for an icon without Shell_NotifyIconGetRect and
/// an icon identifier, so the positioner plugin's tray event stays the answer here.
pub fn tray_anchor() -> Option<TrayAnchor> {
    None
}

pub fn set_tray_highlight(_app: &AppHandle, _on: bool) -> bool {
    false
}

/// The taskbar is already skipped by the window's own flag, so hiding the window is all
/// there is to hide.
/// Windows has no equivalent of the accessory policy; the taskbar button is controlled by
/// the window's own `skipTaskbar`, which the panel sets and the main window does not.
pub fn set_dock_visible(_app: &AppHandle, _visible: bool) {}

pub fn hide_app(_app: &AppHandle) {}

/// The line a reader types to install uv. See the macOS implementation for why the app
/// prints this rather than running it.
pub fn install_uv_command() -> &'static str {
    "powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""
}

pub fn describe() -> Vec<(String, String)> {
    vec![("platform".into(), "windows".into())]
}

/// The engine's lock is `fcntl.flock`, which Windows does not have. See
/// `platform::lock_held`.
pub fn lock_held(_lock: &std::path::Path) -> bool {
    false
}
