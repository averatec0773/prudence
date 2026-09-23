//! Anything that is neither macOS nor Windows: the shell runs, with no material.

use tauri::{AppHandle, WebviewWindow};

use super::{MaterialReport, Surface, TrayAnchor};

pub fn apply_material(_window: &WebviewWindow, _surface: Surface) -> MaterialReport {
    MaterialReport::none("materials are a macOS and Windows feature")
}

/// The notification area gives no frame for an icon without Shell_NotifyIconGetRect and
/// an icon identifier, so the positioner plugin's tray event stays the answer here.
pub fn tray_anchor() -> Option<TrayAnchor> {
    None
}

pub fn set_tray_highlight(_app: &AppHandle, _on: bool) -> bool {
    false
}

/// Windows has no equivalent of the accessory policy; the taskbar button is controlled by
/// the window's own `skipTaskbar`, which the panel sets and the main window does not.
pub fn set_dock_visible(_app: &AppHandle, _visible: bool) {}

pub fn hide_app(_app: &AppHandle) {}

/// The line a reader types to install uv. See the macOS implementation for why the app
/// prints this rather than running it.
pub fn install_uv_command() -> &'static str {
    "curl -LsSf https://astral.sh/uv/install.sh | sh"
}

pub fn describe() -> Vec<(String, String)> {
    vec![("platform".into(), std::env::consts::OS.to_string())]
}

/// Linux keeps `flock` and `fcntl` locks apart, so the question cannot be asked without
/// taking the lock. See `platform::lock_held`.
pub fn lock_held(_lock: &std::path::Path) -> bool {
    false
}
