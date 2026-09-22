//! Installing and updating the engine, with uv.
//!
//! The Engine tab has one button for this: **Install prudence-core** when nothing was
//! found, **Update** when something was. Both run uv, and uv is found the same way
//! `prudence` is, because it is installed the same way.
//!
//! ## Nothing from the page reaches the shell
//!
//! The page sends one boolean: install, or update. Every word of both command lines is a
//! constant in this file, and [`arguments`] is a function of that boolean and nothing
//! else. There is no string from the page anywhere in a `Command`, no shell between this
//! process and uv, and no way for a value the page invented to become an argument.
//! `a_command_line_is_two_constants_and_a_boolean` is the test.
//!
//! ## Failing is the normal case today
//!
//! `prudence-core` is not on PyPI yet, so the ordinary outcome of pressing the button on
//! this machine is uv saying it cannot find the package. That is not an error state to
//! hide: the same status area then shows the manual route, which is the two commands a
//! reader would type, with the README link under them. The button is worth having before
//! the package exists because the manual route is the thing a reader actually needs, and
//! this is where they will look for it.

use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::{channel, Sender};

use serde::Serialize;

use crate::engine::EngineError;

/// uv's own executable name. `Command` resolves `uv.exe` from a bare name on Windows, but
/// the directory probe has to name the file, the same way the engine's locator does.
#[cfg(windows)]
pub const UV: &str = "uv.exe";
#[cfg(not(windows))]
pub const UV: &str = "uv";

/// A first install: the engine with the two extras the app's own features need.
///
/// `--python 3.12` is pinned rather than left to uv's default, because the engine is
/// tested against it and an interpreter chosen by whatever happens to be newest is an
/// interpreter nobody chose.
pub const INSTALL: &[&str] = &[
    "tool",
    "install",
    "--python",
    "3.12",
    "prudence-core[mcp,model]",
];

/// An update in place. No extras: `uv tool upgrade` keeps the ones the install asked for,
/// and naming them again would be this file deciding what an existing installation has.
pub const UPGRADE: &[&str] = &["tool", "upgrade", "prudence-core"];

/// How many lines of uv's output are kept and shown. Enough to read what went wrong,
/// bounded because a resolver that walks a hundred candidates prints a hundred lines.
const TAIL: usize = 12;

/// The command line for one press of the button, and nothing else can produce one.
pub fn arguments(upgrade: bool) -> &'static [&'static str] {
    if upgrade {
        UPGRADE
    } else {
        INSTALL
    }
}

/// Where uv is, looked for in the same directories the engine is looked for in.
///
/// No login-shell probe. The engine's locator has one because the engine is the thing the
/// whole app depends on and is worth a shell start-up; uv is a convenience, and a machine
/// where uv is only on a shell's PATH gets the manual route, which is the same two lines a
/// reader would run there anyway.
pub fn locate(search_path: &[PathBuf], is_executable: &dyn Fn(&Path) -> bool) -> Option<PathBuf> {
    search_path
        .iter()
        .map(|directory| directory.join(UV))
        .find(|candidate| is_executable(candidate))
}

/// What one press of the button did.
#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstallOutcome {
    pub ok: bool,
    /// `noUv` when uv is not on this machine, `launch` when it would not start, `failed`
    /// when it ran and stopped with an error. A word, which the page turns into a
    /// sentence in the reader's language.
    pub error_kind: Option<String>,
    pub status: Option<i32>,
    /// The last lines uv printed, as it printed them.
    pub lines: Vec<String>,
    /// The two commands the manual route needs, in the order they are run. Shown whenever
    /// this did not end in `ok`, which today is every time.
    pub manual: Vec<String>,
}

/// Every line so far, sent to the page while uv is still working.
#[derive(Debug, Clone, Serialize)]
pub struct InstallProgress {
    pub lines: Vec<String>,
}

/// The event the page listens for. One name, like `store-changed`.
pub const INSTALL_PROGRESS: &str = "engine-install";

/// Run uv and report every line as it arrives.
///
/// Both pipes are read on their own threads and merged onto one channel, so the order the
/// reader sees is the order the two streams actually interleaved, and a child that fills
/// stderr cannot wedge the reader. The tail is what is kept; everything is passed to
/// `on_lines` as it happens and nothing is buffered to the end.
pub fn install(
    uv: &Path,
    upgrade: bool,
    on_lines: &dyn Fn(&[String]),
) -> Result<InstallOutcome, EngineError> {
    let arguments = arguments(upgrade);
    eprintln!("[install] {} {}", uv.display(), arguments.join(" "));

    let mut child = Command::new(uv)
        .args(arguments)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| EngineError::Launch(error.to_string()))?;

    let (lines_out, lines_in) = channel::<String>();
    // One thread per pipe, merged onto one channel, so the order the reader sees is the
    // order the two streams actually interleaved and a child that fills stderr cannot
    // wedge the reader. They are two statements rather than a loop because `ChildStdout`
    // and `ChildStderr` are different types.
    let out_sink = lines_out.clone();
    let out_pipe = child.stdout.take();
    let out_reader = std::thread::spawn(move || {
        if let Some(pipe) = out_pipe {
            forward(BufReader::new(pipe), &out_sink);
        }
    });
    let err_pipe = child.stderr.take();
    let err_reader = std::thread::spawn(move || {
        if let Some(pipe) = err_pipe {
            forward(BufReader::new(pipe), &lines_out);
        }
    });

    let mut tail: Vec<String> = Vec::new();
    for line in lines_in {
        tail.push(line);
        if tail.len() > TAIL {
            tail.remove(0);
        }
        on_lines(&tail);
    }
    let _ = out_reader.join();
    let _ = err_reader.join();

    let exit = child
        .wait()
        .map_err(|error| EngineError::Launch(error.to_string()))?;
    let status = exit.code().unwrap_or(-1);
    Ok(InstallOutcome {
        ok: exit.success(),
        error_kind: (!exit.success()).then(|| "failed".to_string()),
        status: Some(status),
        lines: tail,
        manual: if exit.success() { Vec::new() } else { manual() },
    })
}

/// The two commands a reader runs when the button cannot do it for them: uv first,
/// because the second one needs it, then the engine.
///
/// The first line is a platform difference and lives where those live. The second is the
/// same everywhere and is this file's own constant, written out as a reader would type it
/// with the extras quoted, because a shell reads the brackets otherwise.
pub fn manual() -> Vec<String> {
    vec![
        crate::platform::install_uv_command().to_string(),
        "uv tool install --python 3.12 \"prudence-core[mcp,model]\"".to_string(),
    ]
}

/// One line at a time onto the channel. A line too long to be a line is still a line: uv
/// prints progress with carriage returns and no newline, and dropping those would leave
/// the status area empty for the whole of a long resolve.
fn forward<R: Read>(source: BufReader<R>, sink: &Sender<String>) {
    for piece in source.split(b'\n') {
        let Ok(bytes) = piece else { return };
        let text = String::from_utf8_lossy(&bytes);
        for part in text.split('\r') {
            let trimmed = part.trim_end();
            if trimmed.is_empty() {
                continue;
            }
            if sink.send(trimmed.to_string()).is_err() {
                return;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The rule at the top of this file, asserted rather than claimed: a press of the
    /// button can produce exactly two command lines, both written here.
    #[test]
    fn a_command_line_is_two_constants_and_a_boolean() {
        assert_eq!(
            arguments(false),
            &[
                "tool",
                "install",
                "--python",
                "3.12",
                "prudence-core[mcp,model]"
            ]
        );
        assert_eq!(arguments(true), &["tool", "upgrade", "prudence-core"]);
    }

    /// The interpreter is pinned, and the extras the app's own features need are asked
    /// for. Both were decisions; neither is a default.
    #[test]
    fn the_install_pins_an_interpreter_and_asks_for_the_two_extras() {
        let install = arguments(false).join(" ");
        assert!(install.contains("--python 3.12"));
        assert!(install.contains("[mcp,model]"));
        // And the upgrade names no extras: uv keeps the ones the install asked for, and
        // repeating them here would be this file deciding what is already installed.
        assert!(!arguments(true).join(" ").contains('['));
    }

    /// The manual route is uv first and the engine second, because the second needs the
    /// first. A reader who runs them in the other order gets "command not found".
    #[test]
    fn the_manual_route_installs_uv_before_it_installs_the_engine() {
        let lines = manual();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("astral.sh/uv"), "{}", lines[0]);
        assert!(lines[1].starts_with("uv tool install"));
        // Quoted, or a shell expands the brackets and the install asks for a package
        // called `prudence-core`.
        assert!(lines[1].contains("\"prudence-core[mcp,model]\""));
    }

    #[cfg(unix)]
    #[test]
    fn uv_is_looked_for_in_the_directories_the_engine_is_looked_for_in() {
        let directories = [PathBuf::from("/uv/bin"), PathBuf::from("/opt/homebrew/bin")];
        let present = |path: &Path| path == Path::new("/opt/homebrew/bin/uv");
        assert_eq!(
            locate(&directories, &present),
            Some(PathBuf::from("/opt/homebrew/bin/uv"))
        );
        assert_eq!(locate(&directories, &|_: &Path| false), None);
    }

    /// The first directory that has it wins, which is the same order the engine's own
    /// search uses: uv's own bin directory before Homebrew's.
    #[cfg(unix)]
    #[test]
    fn the_first_directory_with_uv_in_it_wins() {
        let directories = [PathBuf::from("/uv/bin"), PathBuf::from("/opt/homebrew/bin")];
        assert_eq!(
            locate(&directories, &|_: &Path| true),
            Some(PathBuf::from("/uv/bin/uv"))
        );
    }

    /// uv prints its resolve progress with carriage returns and no newline. Splitting on
    /// newlines alone left the status area showing one enormous line; splitting on both
    /// makes each state of the progress its own line, and the tail keeps the last few.
    #[test]
    fn a_carriage_return_is_a_line_break_too() {
        let (out, back) = channel();
        forward(
            BufReader::new(&b"resolving\rresolved 12\nbuilding\n"[..]),
            &out,
        );
        drop(out);
        assert_eq!(
            back.iter().collect::<Vec<_>>(),
            vec!["resolving", "resolved 12", "building"]
        );
    }

    #[test]
    fn a_blank_line_is_not_a_line() {
        let (out, back) = channel();
        forward(BufReader::new(&b"one\n\n   \ntwo\n"[..]), &out);
        drop(out);
        assert_eq!(back.iter().collect::<Vec<_>>(), vec!["one", "two"]);
    }
}
