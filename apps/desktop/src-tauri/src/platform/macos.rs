//! macOS: the material, the status item's highlight, and hiding the app.

use objc2::rc::Retained;
use objc2::runtime::NSObjectProtocol;
use objc2::{ClassType, MainThreadMarker, Message};
use objc2_app_kit::{NSApplication, NSButton, NSScreen, NSView, NSWindow};
use tauri::{AppHandle, WebviewWindow};
use window_vibrancy::{
    apply_liquid_glass, apply_vibrancy, LiquidGlassOptions, NSGlassEffectViewStyle,
    NSVisualEffectMaterial, NSVisualEffectState,
};

use super::{Attempt, MaterialReport, Surface, TrayAnchor};

#[cfg(feature = "harness")]
fn glass_override() -> Option<bool> {
    let value = std::env::var("PRUDENCE_GLASS_OPAQUE").ok()?;
    Some(!value.is_empty() && value != "0")
}

#[cfg(not(feature = "harness"))]
fn glass_override() -> Option<bool> {
    None
}

/// `apply_liquid_glass` refuses below this, and the crate reads the same number off
/// `NSAppKitVersionNumber`. Kept here so the log can say which side said no.
const APPKIT_MACOS_26: f64 = 2685.0;

/// The panel's corner radius. `tokens.css` sets `--r-popover: 12px` and the glass layer
/// takes one step larger, which is the rule in DESIGN.md.
const PANEL_RADIUS: f64 = 16.0;

pub fn apply_material(window: &WebviewWindow, surface: Surface) -> MaterialReport {
    let mut attempts = Vec::new();

    // The WKWebView, so the glass view can take it as its own content view rather than
    // sitting behind an opaque sibling. Without this the crate adds the glass below every
    // subview, which on a transparent window still shows but does not refract the way
    // NSGlassEffectView does when it owns its content.
    let webview = webview_view(window);
    if webview.is_none() {
        attempts.push(Attempt {
            api: "find the WKWebView".into(),
            ok: false,
            detail: "the WKWebView pointer was not reachable; glass will sit behind it".into(),
        });
    }

    let appkit = unsafe { objc2_app_kit::NSAppKitVersionNumber };
    if appkit >= APPKIT_MACOS_26 {
        // `opaque` puts an `NSBox` filled with `windowBackgroundColor` behind the glass,
        // so a surface keeps its own tone instead of taking the tone of whatever is
        // behind it. The panel wants that: it is navigation layer all the way down, and
        // pure glass over a dark editor makes a light panel read grey, which is a figure
        // read against a moving backdrop and is what design rule 1 is about. The window
        // does not: its screens are the content layer and are already opaque in CSS, so
        // a filled backing would frost a solid colour and the sidebar would stop being
        // glass at all. Only the harness can override it, because the choice is a design
        // decision and not a preference.
        let opaque = glass_override().unwrap_or(surface == Surface::Panel);
        // A decorated window is rounded by the system; only the frameless panel has to
        // round its own layer.
        let radius = match surface {
            Surface::Panel => PANEL_RADIUS,
            Surface::Window => 0.0,
        };
        let mut options = LiquidGlassOptions::new(NSGlassEffectViewStyle::Regular)
            .radius(radius)
            .opaque(opaque);
        if let Some(view) = webview.as_deref() {
            options = options.content_view(view);
        }
        match apply_liquid_glass(window, options) {
            Ok(()) => {
                attempts.push(Attempt {
                    api: "window_vibrancy::apply_liquid_glass".into(),
                    ok: true,
                    detail: format!(
                        "NSGlassEffectView, style Regular, radius {radius}, opaque {opaque}"
                    ),
                });
                return MaterialReport {
                    kind: "liquid-glass".into(),
                    attempts,
                    detail: format!("NSAppKitVersionNumber {appkit}"),
                };
            }
            Err(error) => attempts.push(Attempt {
                api: "window_vibrancy::apply_liquid_glass".into(),
                ok: false,
                detail: error.to_string(),
            }),
        }
    } else {
        attempts.push(Attempt {
            api: "window_vibrancy::apply_liquid_glass".into(),
            ok: false,
            detail: format!("NSAppKitVersionNumber {appkit} is below macOS 26 ({APPKIT_MACOS_26})"),
        });
    }

    // The fallback every macOS since 10.10 has: the material AppKit would give each of
    // these surfaces natively, which is `.popover` for a popover and `.sidebar` for the
    // navigation side of a split view.
    let fallback = match surface {
        Surface::Panel => NSVisualEffectMaterial::Popover,
        Surface::Window => NSVisualEffectMaterial::Sidebar,
    };
    match apply_vibrancy(
        window,
        fallback,
        Some(NSVisualEffectState::Active),
        Some(match surface {
            Surface::Panel => PANEL_RADIUS,
            Surface::Window => 0.0,
        }),
    ) {
        Ok(()) => {
            attempts.push(Attempt {
                api: "window_vibrancy::apply_vibrancy".into(),
                ok: true,
                detail: "NSVisualEffectView, material Popover".into(),
            });
            MaterialReport {
                kind: "vibrancy".into(),
                attempts,
                detail: format!("NSAppKitVersionNumber {appkit}"),
            }
        }
        Err(error) => {
            attempts.push(Attempt {
                api: "window_vibrancy::apply_vibrancy".into(),
                ok: false,
                detail: error.to_string(),
            });
            MaterialReport {
                kind: "none".into(),
                attempts,
                detail: format!("NSAppKitVersionNumber {appkit}"),
            }
        }
    }
}

/// The WKWebView, found by walking the window rather than through `with_webview`, whose
/// closure has to be `Send` and cannot carry an AppKit object back out. Everything here
/// runs in `setup`, which is already the main thread.
fn webview_view(window: &WebviewWindow) -> Option<Retained<NSView>> {
    let pointer = window.ns_window().ok()? as *mut NSWindow;
    if pointer.is_null() {
        return None;
    }
    let ns_window: &NSWindow = unsafe { &*pointer };
    let content = ns_window.contentView()?;
    // wry's view is a `WKWebView` subclass it calls `WryWebView`; matching on the name
    // rather than on the class keeps this working if either end renames.
    first_view_named(&content, "WebView")
}

fn first_view_named(view: &NSView, needle: &str) -> Option<Retained<NSView>> {
    for sub in view.subviews().iter() {
        if sub.class().name().to_string_lossy().contains(needle) {
            return Some(sub.retain());
        }
        if let Some(found) = first_view_named(&sub, needle) {
            return Some(found);
        }
    }
    None
}

/// The status item's own frame, converted from AppKit's bottom-left screen space into the
/// top-left one every window API here speaks. The positioner plugin can only answer this
/// after a tray event has been delivered, which has not happened on the first show.
pub fn tray_anchor() -> Option<TrayAnchor> {
    let mtm = MainThreadMarker::new()?;
    let button = status_bar_button(mtm)?;
    let item_window = button.window()?;
    let frame = item_window.frame();

    // AppKit has not laid the status item out yet during `setup`, and reports a zero-height
    // frame at the origin. Answering with that would put the panel off the bottom of the
    // screen, so say nothing and let the caller fall back.
    if frame.size.width <= 0.0 || frame.size.height <= 0.0 {
        eprintln!(
            "[anchor] status item not laid out yet: {:?} ({})",
            frame,
            item_window.class().name().to_string_lossy()
        );
        return None;
    }

    // Global coordinates are measured from the bottom-left of the primary screen, which is
    // the first one in the list regardless of which screen anything is on.
    let screens = NSScreen::screens(mtm);
    let primary = screens.iter().next()?;
    let flipped_bottom = primary.frame().size.height - frame.origin.y;

    // The screen the item is actually on decides how far the panel may slide.
    let visible = screens
        .iter()
        .find(|screen| {
            let f = screen.frame();
            frame.origin.x >= f.origin.x && frame.origin.x < f.origin.x + f.size.width
        })
        .map(|screen| screen.visibleFrame())
        .unwrap_or_else(|| primary.visibleFrame());

    Some(TrayAnchor {
        center_x: frame.origin.x + frame.size.width / 2.0,
        bottom: flipped_bottom,
        min_x: visible.origin.x,
        max_x: visible.origin.x + visible.size.width,
    })
}

/// Tauri does not expose the `NSStatusItem` its tray builder created (`TrayIcon.inner` is
/// private), and `tray-icon` clears the highlight on mouse-up, so the capsule lasts only
/// while the button is held. The status item's button is reachable the other way round:
/// it is the content view of the one window AppKit calls a status bar window.
pub fn set_tray_highlight(_app: &AppHandle, on: bool) -> bool {
    let Some(mtm) = MainThreadMarker::new() else {
        return false;
    };
    let Some(button) = status_bar_button(mtm) else {
        return false;
    };
    button.highlight(on);
    true
}

fn status_bar_button(mtm: MainThreadMarker) -> Option<Retained<NSButton>> {
    let app = NSApplication::sharedApplication(mtm);
    for window in app.windows().iter() {
        let class = window.class().name().to_string_lossy().into_owned();
        if !class.contains("StatusBar") {
            continue;
        }
        let Some(content) = window.contentView() else {
            continue;
        };
        if let Some(button) = first_button(&content) {
            return Some(button);
        }
    }
    None
}

fn first_button(view: &NSView) -> Option<Retained<NSButton>> {
    if view.isKindOfClass(NSButton::class()) {
        return Retained::downcast::<NSButton>(view.retain()).ok();
    }
    for sub in view.subviews().iter() {
        if let Some(button) = first_button(&sub) {
            return Some(button);
        }
    }
    None
}

/// `Regular` puts the app in the Dock and the app switcher; `Accessory` takes it out.
/// Toggled at runtime rather than fixed at launch, so "show in Dock" needs no restart.
pub fn set_dock_visible(app: &AppHandle, visible: bool) {
    let policy = if visible {
        tauri::ActivationPolicy::Regular
    } else {
        tauri::ActivationPolicy::Accessory
    };
    if let Err(error) = app.set_activation_policy(policy) {
        eprintln!("[prudence] could not set the activation policy: {error}");
    }
}

pub fn hide_app(app: &AppHandle) {
    let _ = app.hide();
}

pub fn describe() -> Vec<(String, String)> {
    let appkit = unsafe { objc2_app_kit::NSAppKitVersionNumber };
    vec![
        ("platform".into(), "macos".into()),
        ("NSAppKitVersionNumber".into(), appkit.to_string()),
        (
            "liquid glass floor".into(),
            format!("{APPKIT_MACOS_26} (macOS 26.0)"),
        ),
    ]
}
