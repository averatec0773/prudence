//! The main window: the one with the sidebar and the screens.
//!
//! It is created up front and hidden, like the panel, because showing a window that is
//! already drawn is instant and creating one is not. Closing it hides it and takes the
//! Dock icon away; the app stays in the menu bar, which is where it lives.

#[cfg(feature = "harness")]
use tauri::WebviewWindowBuilder;
use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, WebviewWindow};

use crate::ui_state::{Frame, MIN_HEIGHT, MIN_WIDTH};
#[cfg(feature = "harness")]
use crate::BACKDROP;
use crate::{platform, Shell, MAIN};

pub fn open(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else {
        return;
    };

    if !window.is_visible().unwrap_or(false) {
        restore_frame(&window, app);
    }

    // The Dock icon appears while the window is open, which is the M3 answer to "how does
    // a menu bar app get a window into the app switcher".
    platform::set_dock_visible(app, true);

    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
    raise_for_a_screenshot(&window);
}

/// While a script is driving the app, put its window above everything else.
///
/// `Scripts/shot.py` refuses to capture unless our own window is the frontmost thing over
/// the rectangle it is about to photograph, which is the rule that stops it photographing
/// somebody else's screen. Activating by PID is not always enough: an application that
/// takes the focus back, or one whose window the system keeps in front, leaves the check
/// failing and nothing is written. Observed on 2026-09-22, where every shot was refused
/// with "'Claude' window 'Claude' is in front".
///
/// Raising our own window makes the check pass **by being true**, which is the only
/// acceptable way to make it pass. It is harness only and only while
/// `harness::driving()`: an ordinary launch, and every release build, is untouched.
#[cfg(feature = "harness")]
fn raise_for_a_screenshot(window: &WebviewWindow) {
    if crate::harness::driving() {
        let _ = window.set_always_on_top(true);
    }
}

#[cfg(not(feature = "harness"))]
fn raise_for_a_screenshot(_window: &WebviewWindow) {}

pub fn close(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else {
        return;
    };
    remember_frame(&window, app);
    let _ = window.hide();
    platform::set_dock_visible(app, false);
    // A lost frame is a default frame at the next launch.
    let _ = app.state::<Shell>().memory.save();
}

/// Called on every move and resize. It only updates memory; the file is written when the
/// window closes, so dragging a window does not write a file per frame.
pub fn remember_frame(window: &WebviewWindow, app: &AppHandle) {
    let Ok(scale) = window.scale_factor() else {
        return;
    };
    let (Ok(position), Ok(size)) = (window.outer_position(), window.inner_size()) else {
        return;
    };
    let position = position.to_logical::<f64>(scale);
    let size = size.to_logical::<f64>(scale);
    app.state::<Shell>().memory.set_frame(Frame {
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
    });
}

/// A plain full-screen window of the app's own, under everything else.
///
/// Every picture in a report is taken over this. Without it a shot of a frosted surface
/// carries whatever was on the screen behind it: not reproducible, and not the founder's
/// to publish. The Swift render harness draws a `desktopBackdrop` for the same reason.
///
/// Built only by the harness, so a user never pays for a third webview and a release
/// build has no way to put a full-screen window on the screen by itself.
#[cfg(feature = "harness")]
pub fn open_backdrop(app: &AppHandle) {
    if app.get_webview_window(BACKDROP).is_some() {
        return;
    }
    let Some(monitor) = app.primary_monitor().ok().flatten() else {
        return;
    };
    let scale = monitor.scale_factor();
    let size = monitor.size().to_logical::<f64>(scale);
    let position = monitor.position().to_logical::<f64>(scale);

    let built = WebviewWindowBuilder::new(
        app,
        BACKDROP,
        tauri::WebviewUrl::App("backdrop.html".into()),
    )
    .title("Prudence backdrop")
    .decorations(false)
    .shadow(false)
    .skip_taskbar(true)
    .focused(false)
    .resizable(false)
    .inner_size(size.width, size.height)
    .position(position.x, position.y)
    .build();

    match built {
        Ok(window) => {
            // Above the desktop and whatever else is on it, for the same reason
            // `raise_for_a_screenshot` exists: the backdrop is what makes a shot of a
            // frosted surface reproducible, and a backdrop under somebody else's window
            // is a backdrop that is not behind ours. The panel and the main window are
            // raised too and are ordered in front of it.
            let _ = window.set_always_on_top(true);
            let _ = window.show();
        }
        Err(error) => eprintln!("[prudence] no backdrop: {error}"),
    }
}

fn restore_frame(window: &WebviewWindow, app: &AppHandle) {
    let Some(frame) = app.state::<Shell>().memory.read().usable_frame() else {
        return;
    };
    let _ = window.set_size(LogicalSize::new(
        frame.width.max(MIN_WIDTH),
        frame.height.max(MIN_HEIGHT),
    ));
    let _ = window.set_position(LogicalPosition::new(frame.x, frame.y));
}
