//! Everything that is true of one operating system and not the other.
//!
//! The frontend never asks which platform it is on and the rest of the shell calls these
//! four functions unconditionally. A difference that cannot be held here is a difference
//! that will end up in the page, which is what closes the door on Windows.

use serde::Serialize;

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "macos")]
use macos as imp;

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
use windows as imp;

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
mod other;
#[cfg(not(any(target_os = "macos", target_os = "windows")))]
use other as imp;

/// What the window actually got, in the words of the API that gave it. The page reads
/// `kind` to decide whether to draw its own frost or let the native material show, and
/// the spike reads `detail` to find out why something did not happen.
#[derive(Debug, Clone, Serialize)]
pub struct MaterialReport {
    /// `liquid-glass`, `vibrancy`, `mica`, `acrylic` or `none`.
    pub kind: String,
    /// Every attempt in order, with its result. Written to the log and shown by `--probe`.
    pub attempts: Vec<Attempt>,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Attempt {
    pub api: String,
    pub ok: bool,
    pub detail: String,
}

impl MaterialReport {
    pub fn none(detail: impl Into<String>) -> Self {
        Self {
            kind: "none".into(),
            attempts: Vec::new(),
            detail: detail.into(),
        }
    }
}

/// Frost the panel with the best material this machine has, and say which one that was.
pub fn apply_material(window: &tauri::WebviewWindow) -> MaterialReport {
    imp::apply_material(window)
}

/// Where the status item is, in top-left logical screen coordinates, so a panel can hang
/// under it on the first show as well as on a tray click. `None` where the platform has no
/// answer, and the caller falls back to the positioner plugin's tray event.
pub fn tray_anchor() -> Option<TrayAnchor> {
    imp::tray_anchor()
}

/// The horizontal centre of the status item, the edge the panel hangs from, and the
/// screen's usable span so a panel near a corner is pulled back on screen.
#[derive(Debug, Clone, Copy)]
pub struct TrayAnchor {
    pub center_x: f64,
    pub bottom: f64,
    pub min_x: f64,
    pub max_x: f64,
}

/// The grey capsule the system draws behind a menu-bar icon while its panel is open.
/// Returns whether the shell was able to set it, which is a spike question of its own.
pub fn set_tray_highlight(app: &tauri::AppHandle, on: bool) -> bool {
    imp::set_tray_highlight(app, on)
}

/// Hide the application itself, not just the window. On macOS a hidden panel whose app is
/// still active lingers in Mission Control and keeps the previous app from coming forward.
pub fn hide_app(app: &tauri::AppHandle) {
    imp::hide_app(app);
}

/// One line per platform fact the spike has to report, gathered where the answer lives.
pub fn describe() -> Vec<(String, String)> {
    imp::describe()
}
