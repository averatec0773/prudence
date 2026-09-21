//! Anything that is neither macOS nor Windows: the shell runs, with no material.

use tauri::{AppHandle, WebviewWindow};

use super::{MaterialReport, TrayAnchor};

pub fn apply_material(_window: &WebviewWindow) -> MaterialReport {
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

pub fn hide_app(_app: &AppHandle) {}

pub fn describe() -> Vec<(String, String)> {
    vec![("platform".into(), std::env::consts::OS.to_string())]
}
