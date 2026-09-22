//! What the window remembers between launches.
//!
//! The Swift app keeps this in `UserDefaults`; here it is one small JSON file in the app's
//! own configuration directory, which is `~/Library/Application Support/<identifier>/` on
//! macOS and the equivalent on Windows. It is **not** written beside the store: nothing
//! this app remembers is the engine's business, and the engine's directory is somewhere an
//! agent may be pointing at a copy.
//!
//! A remembered value this build no longer understands is ignored rather than forced.

use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

/// The four sections the window has. A stored value outside this list is dropped.
pub const SECTIONS: &[&str] = &["overview", "review", "observations", "settings"];

/// The window's floor, from `MainWindowController` in the Swift app.
pub const MIN_WIDTH: f64 = 900.0;
pub const MIN_HEIGHT: f64 = 600.0;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct Frame {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UiState {
    #[serde(default)]
    pub window: Option<Frame>,
    #[serde(default)]
    pub section: Option<String>,
    /// Where the user said the `prudence` executable is, when the search could not find
    /// it. Remembered here and not beside the store, like everything else on this page:
    /// which engine this machine has is the app's business, not the engine's.
    #[serde(default)]
    pub engine: Option<String>,
}

impl UiState {
    /// The remembered frame, or nothing when it is absent or no longer plausible. A frame
    /// smaller than the window's own floor came from a build with a different floor, and a
    /// frame with a non-finite number came from a crash; both are dropped rather than
    /// clamped, because a window in the wrong place is worse than a window in the default
    /// place.
    pub fn usable_frame(&self) -> Option<Frame> {
        let frame = self.window?;
        let finite = [frame.x, frame.y, frame.width, frame.height]
            .iter()
            .all(|value| value.is_finite());
        if !finite || frame.width < MIN_WIDTH || frame.height < MIN_HEIGHT {
            return None;
        }
        Some(frame)
    }

    /// The remembered section, or nothing when this build does not have it.
    pub fn usable_section(&self) -> Option<&str> {
        let section = self.section.as_deref()?;
        SECTIONS.contains(&section).then_some(section)
    }

    /// The remembered engine path, or nothing.
    ///
    /// Trimmed, and a blank value is nothing: a remembered empty string would be offered
    /// to the locator as an override and silently shadow the search. Whether the path is
    /// still an engine is not asked here, because the answer can change between launches;
    /// `engine.rs` verifies it every time it is used.
    pub fn usable_engine(&self) -> Option<&str> {
        self.engine
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
    }
}

/// Holds the state in memory and writes it out at the moments worth writing at, rather
/// than on every frame of a window drag.
pub struct Memory {
    path: Option<PathBuf>,
    state: Mutex<UiState>,
    enabled: bool,
}

/// Compiled in only for the harness; a release build always remembers.
#[cfg(feature = "harness")]
fn memory_is_off() -> bool {
    std::env::var("PRUDENCE_UI_MEMORY").as_deref() == Ok("off")
}

#[cfg(not(feature = "harness"))]
fn memory_is_off() -> bool {
    false
}

impl Memory {
    /// `PRUDENCE_UI_MEMORY=off` starts with nothing remembered and writes nothing, so a
    /// screenshot is of the state the caller asked for and not of whatever the machine last
    /// left behind. The Swift render harness does the same with `restoringMemory: false`.
    ///
    /// **Behind the `harness` feature**, like every other automation hook. It is what the
    /// screenshot runs set, and the rule is that automation is compiled out of a release
    /// build; this one shipped in one until the delivery A review noticed. The shots are
    /// taken with a bundle built `--features harness`, so the gate costs nothing.
    pub fn load(app: &AppHandle) -> Self {
        let enabled = !memory_is_off();
        let path = app
            .path()
            .app_config_dir()
            .ok()
            .map(|dir| dir.join("ui.json"));

        let state = if enabled {
            path.as_ref()
                .and_then(|path| std::fs::read_to_string(path).ok())
                .and_then(|text| serde_json::from_str::<UiState>(&text).ok())
                .unwrap_or_default()
        } else {
            UiState::default()
        };

        Self {
            path,
            state: Mutex::new(state),
            enabled,
        }
    }

    pub fn read(&self) -> UiState {
        self.state.lock().unwrap().clone()
    }

    pub fn set_frame(&self, frame: Frame) {
        self.state.lock().unwrap().window = Some(frame);
    }

    /// Remember, or forget, where the engine is. `None` forgets, which puts the search
    /// back in charge.
    pub fn set_engine(&self, path: Option<&str>) {
        self.state.lock().unwrap().engine = path
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string);
    }

    pub fn set_section(&self, section: &str) {
        if SECTIONS.contains(&section) {
            self.state.lock().unwrap().section = Some(section.to_string());
        }
    }

    pub fn save(&self) {
        if !self.enabled {
            return;
        }
        let Some(path) = &self.path else {
            return;
        };
        let state = self.state.lock().unwrap().clone();
        let Ok(text) = serde_json::to_string_pretty(&state) else {
            return;
        };
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(path, text);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(width: f64, height: f64) -> UiState {
        UiState {
            window: Some(Frame {
                x: 100.0,
                y: 100.0,
                width,
                height,
            }),
            section: None,
            engine: None,
        }
    }

    #[test]
    fn a_remembered_frame_comes_back() {
        let state = frame(1000.0, 700.0);
        assert_eq!(state.usable_frame().unwrap().width, 1000.0);
    }

    #[test]
    fn a_frame_below_this_builds_floor_is_dropped_rather_than_clamped() {
        assert!(frame(400.0, 700.0).usable_frame().is_none());
        assert!(frame(1000.0, 200.0).usable_frame().is_none());
    }

    #[test]
    fn a_frame_with_a_non_finite_number_is_dropped() {
        assert!(frame(f64::NAN, 700.0).usable_frame().is_none());
        assert!(frame(f64::INFINITY, 700.0).usable_frame().is_none());
    }

    #[test]
    fn nothing_remembered_is_nothing_restored() {
        assert!(UiState::default().usable_frame().is_none());
        assert!(UiState::default().usable_section().is_none());
    }

    #[test]
    fn a_remembered_engine_path_comes_back_trimmed_and_a_blank_one_does_not() {
        let remembered = |value: Option<&str>| UiState {
            window: None,
            section: None,
            engine: value.map(str::to_string),
        };
        assert_eq!(
            remembered(Some("  /opt/homebrew/bin/prudence  ")).usable_engine(),
            Some("/opt/homebrew/bin/prudence")
        );
        // A blank value offered to the locator would shadow the search with nothing.
        assert_eq!(remembered(Some("   ")).usable_engine(), None);
        assert_eq!(remembered(Some("")).usable_engine(), None);
        assert_eq!(remembered(None).usable_engine(), None);
    }

    /// The rule the Swift app states as "a remembered value this build no longer
    /// understands is ignored rather than forced".
    #[test]
    fn a_section_this_build_does_not_have_is_ignored() {
        let state = UiState {
            window: None,
            section: Some("suggestions".into()),
            engine: None,
        };
        assert!(state.usable_section().is_none());
    }

    #[test]
    fn every_section_this_build_has_round_trips() {
        for section in SECTIONS {
            let state = UiState {
                window: None,
                section: Some((*section).to_string()),
                engine: None,
            };
            assert_eq!(state.usable_section(), Some(*section));
        }
    }

    #[test]
    fn an_unreadable_file_is_the_same_as_no_file() {
        let state: Result<UiState, _> = serde_json::from_str("{ not json");
        assert!(state.is_err());
        let partial: UiState = serde_json::from_str("{}").unwrap();
        assert!(partial.usable_frame().is_none());
    }
}
