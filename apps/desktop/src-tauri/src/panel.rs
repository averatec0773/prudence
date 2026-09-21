//! The panel: a frameless transparent window that behaves like a popover.
//!
//! There is no popover here. There is a window positioned under the status item, shown
//! and hidden rather than created and destroyed, so the page keeps its state and the
//! second open is instant.

use tauri::{AppHandle, LogicalPosition, Manager};
use tauri_plugin_positioner::{Position, WindowExt};

use crate::{platform, Shell, PANEL};

/// The gap between the menu bar and the top of the panel, as the mockups draw it.
const TRAY_GAP: f64 = 6.0;

pub fn toggle(app: &AppHandle) {
    let Some(window) = app.get_webview_window(PANEL) else {
        return;
    };
    if window.is_visible().unwrap_or(false) {
        hide(app);
    } else {
        show(app);
    }
}

pub fn show(app: &AppHandle) {
    let Some(window) = app.get_webview_window(PANEL) else {
        return;
    };

    position(&window);
    let _ = window.show();
    let _ = window.set_focus();

    let highlighted = platform::set_tray_highlight(app, true);
    *app.state::<Shell>().tray_highlight_works.lock().unwrap() = highlighted;

    eprintln!(
        "[shown] {} ms after launch, position={:?} size={:?} highlight={highlighted}",
        app.state::<Shell>().started.elapsed().as_millis(),
        window.outer_position(),
        window.outer_size()
    );
}

/// Under the status item, and wholly on the screen the status item is on.
///
/// The platform's own answer is preferred because it is available on the first show; the
/// positioner plugin knows where the tray is only after a tray event has reached it, which
/// is why a panel opened any other way lands in a corner.
pub fn position(window: &tauri::WebviewWindow) {
    if let Some(anchor) = platform::tray_anchor() {
        let width = window
            .outer_size()
            .ok()
            .and_then(|size| {
                window
                    .scale_factor()
                    .ok()
                    .map(|scale| size.width as f64 / scale)
            })
            .unwrap_or(360.0);

        let x = anchored_x(&anchor, width);

        if window
            .set_position(LogicalPosition::new(x, anchor.bottom + TRAY_GAP))
            .is_ok()
        {
            return;
        }
    }

    if window
        .move_window_constrained(Position::TrayBottomCenter)
        .is_err()
    {
        let _ = window.move_window(Position::TrayBottomCenter);
    }
}

/// The page has measured its content. Resize, then anchor again: AppKit keeps a window's
/// bottom-left corner when its frame changes, so a taller panel grows upwards through the
/// menu bar unless it is put back.
pub fn fit(app: &AppHandle, width: f64, height: f64) {
    let Some(window) = app.get_webview_window(PANEL) else {
        return;
    };
    let _ = window.set_size(tauri::LogicalSize::new(width, height));
    position(&window);
}

/// Centred under the status item, and pulled back on screen where that would hang it off
/// an edge. Separated out because a second display is the one case a spike on a laptop
/// cannot photograph, so the arithmetic is asserted instead of looked at.
fn anchored_x(anchor: &platform::TrayAnchor, width: f64) -> f64 {
    let centred = anchor.center_x - width / 2.0;
    // `min` before `max`: on a screen narrower than the panel the left edge wins, which
    // keeps the beginning of every line readable rather than the end.
    centred.min(anchor.max_x - width).max(anchor.min_x)
}

pub fn hide(app: &AppHandle) {
    let Some(window) = app.get_webview_window(PANEL) else {
        return;
    };
    let _ = window.hide();
    platform::set_tray_highlight(app, false);
    // Hiding the window is not enough on macOS: an app that stays active keeps the
    // previous application from coming forward and leaves a ghost in Mission Control.
    platform::hide_app(app);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::platform::TrayAnchor;

    /// A second display sits to the right of the built-in one, so its coordinates do not
    /// start at zero; a panel placed as if they did lands on the wrong screen.
    fn secondary(center_x: f64) -> TrayAnchor {
        TrayAnchor {
            center_x,
            bottom: 24.0,
            min_x: 1512.0,
            max_x: 1512.0 + 1920.0,
        }
    }

    #[test]
    fn the_panel_is_centred_under_the_status_item() {
        assert_eq!(anchored_x(&secondary(2000.0), 360.0), 1820.0);
    }

    #[test]
    fn a_status_item_near_the_right_edge_pulls_the_panel_back_on_screen() {
        let anchor = secondary(3420.0);
        let x = anchored_x(&anchor, 360.0);
        assert_eq!(x, anchor.max_x - 360.0);
        assert!(x + 360.0 <= anchor.max_x);
    }

    #[test]
    fn a_status_item_near_the_left_edge_does_not_slide_onto_the_screen_before_it() {
        let anchor = secondary(1520.0);
        assert_eq!(anchored_x(&anchor, 360.0), anchor.min_x);
    }

    #[test]
    fn a_screen_narrower_than_the_panel_keeps_the_left_edge() {
        let anchor = TrayAnchor {
            center_x: 100.0,
            bottom: 24.0,
            min_x: 0.0,
            max_x: 200.0,
        };
        assert_eq!(anchored_x(&anchor, 360.0), 0.0);
    }
}
