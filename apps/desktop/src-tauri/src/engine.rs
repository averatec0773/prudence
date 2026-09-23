//! Finding the `prudence` executable, and running it.
//!
//! ## Why finding it is work
//!
//! An app launched from Finder, the Dock or Spotlight is started by the per-user
//! `launchd` and inherits `launchd`'s environment. It never reads `.zshrc` or
//! `.zprofile`, so the PATH that has `prudence` on it in Terminal is simply not there.
//! Asking `PATH` and giving up is therefore the one thing that cannot work. The order
//! below is the one `apps/mac/.../EngineLocator.swift` settled on, ported as a rule:
//!
//! 1. a path the user chose, verified before it is trusted;
//! 2. uv's documented order for tool binaries (`UV_TOOL_BIN_DIR`, `XDG_BIN_HOME`,
//!    `$XDG_DATA_HOME/../bin`, `~/.local/bin`), then `/opt/homebrew/bin`, then
//!    `/usr/local/bin`;
//! 3. one login-shell probe, off the main thread, with a timeout, cached for the session;
//! 4. nothing, and the interface says "engine not found" with a way to fix it.
//!
//! Every filesystem question is a [`FileProbe`] call and the shell is a [`LoginShell`]
//! call, so the whole order is tested against a fake filesystem with no `prudence`
//! anywhere near the machine running the test.
//!
//! ## What "found" means here
//!
//! **Found means verified.** A path is only reported as the engine once it has answered
//! `--version` with something that looks like a version. A file named `prudence` that
//! cannot say what it is has no business being handed an `ingest`, and a user who
//! chose the wrong file in the picker should be told so rather than have it remembered.
//!
//! ## The arrows go one way
//!
//! The app reads the store and asks the engine to work. Every action is the same command
//! the founder runs by hand with `--json` appended, so the answer is decoded rather than
//! scraped, and `PRUDENCE_INTERNAL=1` is in the child's environment so the capture hooks
//! stay quiet around Prudence's own subprocesses and a user can guard their own rc files
//! against the shell probe.
//!
//! The child inherits this process's environment, which is how `PRUDENCE_DATA_DIR` and
//! `PRUDENCE_CONFIG_DIR` reach it: an app pointed at a copy of the store can never have
//! the engine ingest into the real one.

use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

/// The executable's name. `Command` resolves `prudence.exe` from a bare name on Windows,
/// but a directory probe has to name the file, so the name is written once.
#[cfg(windows)]
pub const EXECUTABLE: &str = "prudence.exe";
#[cfg(not(windows))]
pub const EXECUTABLE: &str = "prudence";

/// How long the login shell gets. An rc file that waits on the network would otherwise
/// hang the answer for as long as the network takes; at the deadline the child is killed
/// and the answer is "not found", which is recoverable because the user can still choose
/// the file themselves.
pub const SHELL_TIMEOUT: Duration = Duration::from_secs(10);

/* --- the tilde ---------------------------------------------------------------------- */

/// A leading `~/` replaced by the home directory, and nothing else touched.
///
/// The engine's `paths.py` does `Path(value).expanduser()`. Anywhere a shell is not the
/// one setting a value (a plist, a launchd `EnvironmentVariables`, a runner reading a
/// file) it arrives with the tilde intact, and a literal directory called `~` is a
/// different directory from the user's home. `store.rs` needs the same rule for
/// `PRUDENCE_DATA_DIR` and calls this, so the two cannot disagree about which path is
/// which.
pub fn expand_tilde(path: PathBuf, home: &Path) -> PathBuf {
    let Some(text) = path.to_str() else {
        return path;
    };
    if text == "~" {
        return home.to_path_buf();
    }
    match text.strip_prefix("~/") {
        Some(rest) => home.join(rest),
        None => path,
    }
}

/* --- the two seams ------------------------------------------------------------------ */

/// The filesystem, as the locator needs it. One question, so a test can answer it from a
/// list instead of from a disk.
pub trait FileProbe: Send + Sync {
    /// True when this path is a file this process could execute.
    fn is_executable(&self, path: &Path) -> bool;
}

/// The real filesystem.
pub struct RealFiles;

impl FileProbe for RealFiles {
    fn is_executable(&self, path: &Path) -> bool {
        // `metadata` follows symlinks, which matters: `uv tool install` puts a symlink in
        // `~/.local/bin` pointing into its own tool directory.
        let Ok(meta) = std::fs::metadata(path) else {
            return false;
        };
        if !meta.is_file() {
            return false;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            meta.permissions().mode() & 0o111 != 0
        }
        #[cfg(not(unix))]
        {
            true
        }
    }
}

/// The login-shell fallback, behind a trait so a test never spawns a shell.
pub trait LoginShell: Send + Sync {
    /// The absolute path a login shell resolves `prudence` to, or nothing.
    fn locate(&self, timeout: Duration) -> Option<PathBuf>;
}

/// `zsh -ilc 'command -v prudence'`, the way VS Code harvests the login environment.
///
/// Interactive **and** login, because either file may be where the user's PATH is set.
///
/// This is a platform difference living outside `platform/`, deliberately: the seam is
/// the [`LoginShell`] trait, not the folder. A Windows answer is a second implementation
/// of this trait, never a branch inside the locator.
pub struct ZshLogin;

impl LoginShell for ZshLogin {
    fn locate(&self, timeout: Duration) -> Option<PathBuf> {
        #[cfg(target_os = "macos")]
        {
            probe_login_shell(timeout)
        }
        // There is no zsh to ask. The user chooses the file, which is step 1 of the order.
        #[cfg(not(target_os = "macos"))]
        {
            let _ = timeout;
            None
        }
    }
}

#[cfg(target_os = "macos")]
fn probe_login_shell(timeout: Duration) -> Option<PathBuf> {
    let mut child = Command::new("/bin/zsh")
        .args(["-ilc", "command -v prudence"])
        .env("PRUDENCE_INTERNAL", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let mut pipe = child.stdout.take()?;

    // The deadline is on the pipe, not on a clock we sleep against: the reader thread
    // blocks on the real read and the child is killed only if the deadline wins.
    let child = Arc::new(Mutex::new(child));
    let (answer_out, answer_in) = mpsc::channel();
    std::thread::spawn(move || {
        let mut text = String::new();
        let _ = pipe.read_to_string(&mut text);
        let _ = answer_out.send(text);
    });

    let answer = answer_in.recv_timeout(timeout);
    let mut process = child.lock().unwrap();
    if answer.is_err() {
        eprintln!("[engine] the login shell did not answer in {timeout:?}; killed");
        let _ = process.kill();
    }
    let _ = process.wait();
    drop(process);

    first_absolute_line(&answer.ok()?)
}

/// The first line of a shell's output that is an absolute path.
///
/// Not "the first line", which is what the Swift version took: an rc file that prints a
/// banner puts that banner on stdout ahead of `command -v`'s answer, and the path is
/// still in there. Whatever comes back is probed for being executable anyway.
fn first_absolute_line(text: &str) -> Option<PathBuf> {
    text.lines()
        .map(str::trim)
        .find(|line| line.starts_with('/'))
        .map(PathBuf::from)
}

/* --- the order ---------------------------------------------------------------------- */

/// How the executable in hand was found, for the interface and for the report.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum Source {
    /// A path the user chose.
    Settings,
    /// One of the directories the search walks.
    Directory { directory: String },
    /// The login shell knew where it is.
    LoginShell,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Found {
    pub path: PathBuf,
    pub source: Source,
}

/// The search order, with the filesystem and the shell injected.
pub struct Locator {
    files: Box<dyn FileProbe>,
    login: Box<dyn LoginShell>,
    environment: HashMap<String, String>,
    home: PathBuf,
    /// `Some(None)` means the shell was asked and did not know. One probe per launch,
    /// however many times a screen refreshes: a shell that does not know `prudence` will
    /// not learn it in sixty seconds, and each probe costs a whole shell start-up.
    shell_answer: Mutex<Option<Option<PathBuf>>>,
}

impl Locator {
    pub fn new(
        files: Box<dyn FileProbe>,
        login: Box<dyn LoginShell>,
        environment: HashMap<String, String>,
        home: PathBuf,
    ) -> Self {
        Self {
            files,
            login,
            environment,
            home,
            shell_answer: Mutex::new(None),
        }
    }

    /// The real filesystem, the real shell, this process's environment.
    pub fn real() -> Self {
        let environment: HashMap<String, String> = std::env::vars().collect();
        let home = environment
            .get("HOME")
            .or_else(|| environment.get("USERPROFILE"))
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."));
        Self::new(Box::new(RealFiles), Box::new(ZshLogin), environment, home)
    }

    /// The directories probed before the shell, in order, deduplicated.
    ///
    /// uv's documented resolution for `uv tool install` binaries first, because that is
    /// how the engine is installed, then the two Homebrew prefixes, Apple silicon first.
    pub fn search_path(&self) -> Vec<PathBuf> {
        let mut directories: Vec<PathBuf> = Vec::new();
        let mut add = |value: PathBuf| {
            if value.as_os_str().is_empty() {
                return;
            }
            if !directories.contains(&value) {
                directories.push(value);
            }
        };

        if let Some(dir) = self.variable("UV_TOOL_BIN_DIR") {
            add(dir);
        }
        if let Some(dir) = self.variable("XDG_BIN_HOME") {
            add(dir);
        }
        // uv's own fallback: the sibling `bin` of `XDG_DATA_HOME`.
        if let Some(data) = self.variable("XDG_DATA_HOME") {
            if let Some(parent) = data.parent() {
                add(parent.join("bin"));
            }
        }
        add(self.home.join(".local").join("bin"));
        add(PathBuf::from("/opt/homebrew/bin"));
        add(PathBuf::from("/usr/local/bin"));
        directories
    }

    /// Settings, then the known directories. Cheap, synchronous, no process spawned, so
    /// it is safe anywhere.
    pub fn locate_without_shell(&self, settings: Option<&str>) -> Option<Found> {
        if let Some(chosen) = settings.map(str::trim).filter(|value| !value.is_empty()) {
            let path = expand_tilde(PathBuf::from(chosen), &self.home);
            if self.files.is_executable(&path) {
                return Some(Found {
                    path,
                    source: Source::Settings,
                });
            }
            // A remembered path that has gone away is not a reason to stop looking: the
            // engine may well have been reinstalled somewhere the search knows about.
        }
        for directory in self.search_path() {
            let candidate = directory.join(EXECUTABLE);
            if self.files.is_executable(&candidate) {
                return Some(Found {
                    path: candidate,
                    source: Source::Directory {
                        directory: directory.display().to_string(),
                    },
                });
            }
        }
        None
    }

    /// The whole order, shell probe included. Spawns a shell, so keep it off the main
    /// thread: every command that calls it is `#[tauri::command(async)]`.
    pub fn locate(&self, settings: Option<&str>, timeout: Duration) -> Option<Found> {
        if let Some(found) = self.locate_without_shell(settings) {
            return Some(found);
        }
        let answer = self.asked_the_shell_once(timeout)?;
        self.files.is_executable(&answer).then_some(Found {
            path: answer,
            source: Source::LoginShell,
        })
    }

    fn asked_the_shell_once(&self, timeout: Duration) -> Option<PathBuf> {
        let mut cached = self.shell_answer.lock().unwrap();
        if let Some(answer) = cached.as_ref() {
            return answer.clone();
        }
        // The lock is held across the probe on purpose: two screens refreshing at once
        // would otherwise start two shells, and the second one's answer is the first
        // one's answer.
        let answer = self.login.locate(timeout);
        *cached = Some(answer.clone());
        answer
    }

    fn variable(&self, key: &str) -> Option<PathBuf> {
        self.environment
            .get(key)
            .filter(|value| !value.is_empty())
            .map(|value| expand_tilde(PathBuf::from(value), &self.home))
    }
}

/* --- running it --------------------------------------------------------------------- */

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EngineError {
    /// Nothing was found to run.
    NotFound,
    /// The file is there and could not be started.
    Launch(String),
    /// It ran and stopped with an error, and said nothing a screen can decode.
    Failed { status: i32, message: String },
    /// It answered `--version` with something that is not a version.
    NoVersion(String),
    /// A run is already going.
    Busy,
}

impl EngineError {
    /// Which failure this is, as a word the page turns into a sentence in the reader's
    /// language. The shell writes no user-visible English of its own here.
    pub fn kind(&self) -> &'static str {
        match self {
            Self::NotFound => "notFound",
            Self::Launch(_) => "launch",
            Self::Failed { .. } => "failed",
            Self::NoVersion(_) => "noVersion",
            Self::Busy => "busy",
        }
    }

    /// The engine's own words, under the localised line. Empty when the engine never
    /// spoke, because inventing a sentence for it would be putting words in its mouth.
    pub fn detail(&self) -> String {
        match self {
            Self::NotFound | Self::Busy => String::new(),
            Self::Launch(text) => text.clone(),
            Self::Failed { status, message } => {
                let trimmed = message.trim();
                if trimmed.is_empty() {
                    format!("exit {status}")
                } else {
                    trimmed.to_string()
                }
            }
            Self::NoVersion(text) => clipped(text),
        }
    }
}

/// Enough of a wall of output to recognise, and not enough to fill a screen with.
fn clipped(text: &str) -> String {
    let trimmed = text.trim();
    match trimmed.char_indices().nth(200) {
        Some((at, _)) => format!("{}...", &trimmed[..at]),
        None => trimmed.to_string(),
    }
}

/// One run of the CLI, as it answered.
#[derive(Debug, Clone)]
pub struct Answer {
    pub json: Option<Value>,
    pub stdout: String,
    pub stderr: String,
    pub status: i32,
}

/* --- what a run says while it is going ----------------------------------------------
 *
 * `prudence ingest --progress` writes one JSON object per line to standard error and
 * nothing else. Every line is therefore one of two things, and the two are kept apart
 * here rather than in the page:
 *
 * - a progress event, which is reported as it arrives and then forgotten;
 * - anything else, which is the engine speaking and is kept, because it is what the
 *   failure text is made of.
 *
 * A line that does not parse is the second kind **by definition**. Guessing at a
 * half-written object would be the app inventing what the engine meant, and a malformed
 * line must not end a run that the engine is still completing.
 */

/// One `--progress` line, read.
///
/// Only `event` is required, and it is the engine's own marker for these lines. The rest
/// default, so a step that reports no total yet is still a step being reported: the page
/// draws the label and no fill, which is the truth. Every field is the engine's own; the
/// interface translates `step` and `unit` and computes only the fraction of the bar.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    pub step: String,
    pub step_index: u64,
    pub steps: u64,
    pub current: u64,
    pub total: u64,
    pub unit: String,
    pub label: String,
}

/// Who a run tells about its progress. Borrowed rather than owned, so the caller can keep
/// whatever the report needs (an app handle, in production) without this module knowing
/// what any of it is.
pub type Reporter<'a> = dyn Fn(&Progress) + Sync + 'a;

/// The engine's word for this step of the run, as the [`Progress`] fields' own marker.
const PROGRESS_EVENT: &str = "progress";

/// One line of standard error, read as a progress event or not at all.
pub fn parse_progress(line: &str) -> Option<Progress> {
    let json = serde_json::from_str::<Value>(line).ok()?;
    if json.get("event").and_then(Value::as_str) != Some(PROGRESS_EVENT) {
        return None;
    }
    let number = |key: &str| json.get(key).and_then(Value::as_u64).unwrap_or_default();
    let text = |key: &str| {
        json.get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    };
    Some(Progress {
        step: text("step"),
        step_index: number("step_index"),
        steps: number("steps"),
        current: number("current"),
        total: number("total"),
        unit: text("unit"),
        label: text("label"),
    })
}

/// How much of one stderr line is read before the rest of it is dropped.
///
/// A line is only bounded by the next newline, and the picker can point this module at any
/// executable: one that writes megabytes with no newline in them would otherwise be
/// buffered whole, which is the defect [`OUTPUT_CAP`] exists to stop on the other pipe.
const LINE_CAP: usize = 64 * 1024;

/// Read standard error a line at a time: report the progress lines, keep the rest.
///
/// Chunked rather than `BufRead::lines`, for the same reason [`capped`] is: a child that
/// prints forever without a newline must not grow this process.
fn progress_reader<R: Read>(mut source: R, report: Option<&Reporter>) -> String {
    let mut kept: Vec<u8> = Vec::new();
    let mut pending: Vec<u8> = Vec::new();
    let mut chunk = [0_u8; 64 * 1024];
    loop {
        match source.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(read) => {
                for &byte in &chunk[..read] {
                    if byte == b'\n' {
                        take_line(&mut pending, &mut kept, report);
                    } else if pending.len() < LINE_CAP {
                        pending.push(byte);
                    }
                }
            }
        }
    }
    // Whatever the child wrote without a closing newline is still something it said.
    take_line(&mut pending, &mut kept, report);
    String::from_utf8_lossy(&kept).to_string()
}

fn take_line(pending: &mut Vec<u8>, kept: &mut Vec<u8>, report: Option<&Reporter>) {
    if pending.is_empty() {
        return;
    }
    let line = String::from_utf8_lossy(pending).to_string();
    pending.clear();
    if let Some(progress) = parse_progress(line.trim()) {
        if let Some(report) = report {
            report(&progress);
        }
        // Dropped whether or not anybody was listening: a progress line is not something
        // the engine said about a failure, and keeping it would put a hundred JSON objects
        // in front of the one sentence that says what went wrong.
        return;
    }
    if kept.len() < OUTPUT_CAP {
        kept.extend_from_slice(line.as_bytes());
        kept.push(b'\n');
    }
}

/// `<executable> <arguments>`, with the child's environment set.
///
/// A non-zero exit is not automatically something to shout about: `prudence review` says
/// "not ready" through a JSON body and exits 0, but a future version that exits non-zero
/// with the same body still has the reason the caller wants. So a non-zero exit whose
/// stdout parses as JSON comes back as an answer; anything else is an error.
///
/// `environment` is what the caller wants the child to have **on top of** this process's
/// own. Production passes nothing, because inheriting is exactly how `PRUDENCE_DATA_DIR`
/// reaches the engine. A test passes the copy of the store it is allowed to write to, so
/// that nothing a test spawns can reach the real one.
/// How much of a child's output is kept. Enough for any answer the engine gives and for
/// a stack trace; bounded because the reader is not always the engine.
///
/// `Command::output()` reads to EOF with no limit, and the picker can point this module at
/// any executable: `/usr/bin/yes --version` ignores the argument and prints forever, which
/// grew the app until the system killed it.
const OUTPUT_CAP: usize = 4 * 1024 * 1024;

/// How long a `--version` may take. It is not a run: it is one interpreter start-up, and
/// it is reachable from the picker with a file that might block forever. A real run has no
/// deadline on purpose, and that compromise is registered; its justification is that an
/// ingest takes minutes, which is not true of a version probe.
const VERSION_TIMEOUT: Duration = Duration::from_secs(20);

/// Read a pipe, keeping at most [`OUTPUT_CAP`] bytes.
///
/// Reading continues past the cap without keeping anything: closing the pipe early would
/// hand the child a broken pipe, and a child killed by SIGPIPE part-way through writing is
/// the interruption this module exists to avoid.
fn capped<R: Read>(mut source: R) -> String {
    let mut buffer = Vec::new();
    let mut chunk = [0_u8; 64 * 1024];
    loop {
        match source.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(read) => {
                if buffer.len() < OUTPUT_CAP {
                    let room = OUTPUT_CAP - buffer.len();
                    buffer.extend_from_slice(&chunk[..read.min(room)]);
                }
            }
        }
    }
    String::from_utf8_lossy(&buffer).to_string()
}

pub fn run(
    executable: &Path,
    arguments: &[&str],
    environment: &[(&str, &str)],
) -> Result<Answer, EngineError> {
    run_bounded(executable, arguments, environment, None, None)
}

/// [`run`], telling `report` about every progress line the child writes while it runs.
pub fn run_reporting(
    executable: &Path,
    arguments: &[&str],
    environment: &[(&str, &str)],
    report: &Reporter,
) -> Result<Answer, EngineError> {
    run_bounded(executable, arguments, environment, None, Some(report))
}

/// [`run`], with an optional deadline and an optional listener.
pub fn run_bounded(
    executable: &Path,
    arguments: &[&str],
    environment: &[(&str, &str)],
    deadline: Option<Duration>,
    report: Option<&Reporter>,
) -> Result<Answer, EngineError> {
    let mut command = Command::new(executable);
    command
        .args(arguments)
        .env("PRUDENCE_INTERNAL", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for (key, value) in environment {
        command.env(key, value);
    }

    // **Its own process group**, so that quitting the app does not abort an ingest.
    //
    // An ingest rebuilds the `app_*` views: it drops them and creates them again. A child
    // in the app's process group receives the same terminate the app gets, so closing the
    // window part-way through left the store with no views at all and the app could not
    // read it until another ingest finished. Reproduced on 2026-09-21 by pressing Ingest
    // now and quitting: two `app_*` objects left out of nine.
    //
    // Detaching does not make the engine's rebuild atomic, which is the other half of
    // that story and is the engine's to fix. It does mean the app cannot be the thing
    // that interrupts it.
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }

    let began = Instant::now();
    let mut child = command.spawn().map_err(|error| {
        let error = EngineError::Launch(error.to_string());
        invoked(arguments, began, Err(&error));
        error
    })?;

    // Both pipes drained on their own threads, so a child that fills stderr cannot wedge
    // the reader, and each is capped. **Scoped** threads, so the stderr reader may borrow
    // the caller's listener: a run reports while it is going, which is the whole point,
    // and an owned `'static` closure would mean the app handle being cloned into a thread
    // this function has no way to name.
    let out_pipe = child.stdout.take();
    let err_pipe = child.stderr.take();
    let (stdout, stderr, exit) = std::thread::scope(|threads| {
        let out_reader = threads.spawn(move || out_pipe.map(capped).unwrap_or_default());
        let err_reader = threads.spawn(move || {
            err_pipe
                .map(|pipe| progress_reader(pipe, report))
                .unwrap_or_default()
        });

        let exit = match deadline {
            None => child
                .wait()
                .map_err(|error| EngineError::Launch(error.to_string())),
            Some(limit) => {
                let started = Instant::now();
                loop {
                    match child.try_wait() {
                        Err(error) => break Err(EngineError::Launch(error.to_string())),
                        Ok(Some(status)) => break Ok(status),
                        Ok(None) => {}
                    }
                    if started.elapsed() >= limit {
                        // Killed rather than left behind: this is the probe, not a run, and
                        // a file that will not answer `--version` is not the engine.
                        let _ = child.kill();
                        let _ = child.wait();
                        break Err(EngineError::NoVersion(String::new()));
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
            }
        };

        // Joined whichever way the wait ended: a killed child closes its pipes, so the
        // readers finish, and leaving them unjoined would leak the scope's own threads.
        (
            out_reader.join().unwrap_or_default(),
            err_reader.join().unwrap_or_default(),
            exit,
        )
    });
    let exit = exit.inspect_err(|error| invoked(arguments, began, Err(error)))?;

    let json = serde_json::from_str::<Value>(&stdout).ok();
    let status = exit.code().unwrap_or(-1);
    invoked(arguments, began, Ok(status));

    if !exit.success() && json.is_none() {
        return Err(EngineError::Failed {
            status,
            message: if stderr.trim().is_empty() {
                stdout
            } else {
                stderr
            },
        });
    }

    Ok(Answer {
        json,
        stdout,
        stderr,
        status,
    })
}

/// One invocation, in the app log: the arguments, how it ended and how long it took.
///
/// **Never the output.** Not the executable's path either, which carries the user's name
/// and says nothing the arguments do not; a failure's words are logged by whoever shows
/// them (`Engine::run`, `Engine::read`), so they are logged once.
fn invoked(arguments: &[&str], began: Instant, ended: Result<i32, &EngineError>) {
    let command = arguments.join(" ");
    let seconds = format!("{:.2}", began.elapsed().as_secs_f64());
    match ended {
        Ok(exit) => {
            tracing::info!(target: "engine", command, exit, seconds = %seconds, "engine ran")
        }
        Err(error) => tracing::error!(
            target: "engine",
            command,
            kind = error.kind(),
            seconds = %seconds,
            "engine did not run to an exit"
        ),
    }
}

/// The version string the executable reports, and nothing derived from it.
///
/// `prudence --version` prints `prudence, version 0.4.0`, which is click's own format for
/// a `version_option` with a `prog_name`. Only the number comes back, because the store
/// reports `0.4.0` and the two have to be comparable side by side.
///
/// **The line has to name the tool.** This is the whole of "verified before it is
/// trusted": a picker pointed at the wrong file gets an answer from whatever it pointed
/// at, and `python --version` ends in a version number too. Remembering that as the
/// engine would break every action afterwards, with a version on screen to say it should
/// have worked.
pub fn parse_version(text: &str) -> Option<String> {
    let line = text.lines().find(|line| !line.trim().is_empty())?.trim();
    if !line.to_ascii_lowercase().contains("prudence") {
        return None;
    }
    let token = line
        .split_whitespace()
        .next_back()?
        .trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '.');
    // And a version starts with a digit: `zsh: command not found: prudence` names the
    // tool and ends in a word, and printing that as a version would be the app inventing
    // a fact.
    token
        .starts_with(|c: char| c.is_ascii_digit())
        .then(|| token.to_string())
}

/// The two things the app may ask the engine to do.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Ingest,
    Review,
}

impl Action {
    pub fn parse(name: &str) -> Option<Self> {
        match name {
            "ingest" => Some(Self::Ingest),
            "review" => Some(Self::Review),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Ingest => "ingest",
            Self::Review => "review",
        }
    }

    /// The command line, `--json` included so the answer is decoded rather than scraped.
    ///
    /// `--no-explain` on a review is a product decision, not a convenience: the model
    /// segment needs an API key this app never asks for and never holds, and a button
    /// that fails on a machine without one would be a button that fails for most people.
    /// The review is complete without a segment; `prudence explain <id>` adds one later.
    ///
    /// `--progress` on an ingest is asked for every time rather than when somebody is
    /// listening. It changes nothing about what the run does and nothing about stdout; it
    /// is the only way the app can say what a run that takes minutes is doing, and a flag
    /// the app sometimes passes is a flag whose absence is another state to test.
    pub fn arguments(self, force: bool) -> Vec<&'static str> {
        match self {
            Self::Ingest => vec!["ingest", "--json", "--progress"],
            Self::Review if force => vec!["review", "--json", "--no-explain", "--force"],
            Self::Review => vec!["review", "--json", "--no-explain"],
        }
    }
}

/// What a run did, for the interface. Every figure in it is one the engine printed.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunOutcome {
    pub action: String,
    pub ok: bool,
    /// The engine declined: not enough new work for a review yet, and nothing was
    /// written. Not a failure, and the reason is the point of the button in that case.
    pub not_ready: bool,
    /// The engine's own sentence for why it declined, printed as it came.
    pub reason: Option<String>,
    /// The review's id, as the engine reported it.
    pub review_id: Option<i64>,
    /// The session count in the engine's own ingest summary.
    pub sessions: Option<i64>,
    pub error_kind: Option<String>,
    pub error: Option<String>,
}

impl RunOutcome {
    fn of(action: Action) -> Self {
        Self {
            action: action.name().to_string(),
            ..Self::default()
        }
    }

    fn failed(action: Action, error: &EngineError) -> Self {
        Self {
            error_kind: Some(error.kind().to_string()),
            error: Some(error.detail()).filter(|text| !text.is_empty()),
            ..Self::of(action)
        }
    }
}

/// `prudence review --json`, read.
///
/// Three shapes: `ready: false` with the reason and nothing written; a stored review with
/// its `id`; or output this build cannot place, which is still a review that was written,
/// because the command only prints that body after the row exists.
pub fn describe_review(json: Option<&Value>) -> RunOutcome {
    let mut outcome = RunOutcome::of(Action::Review);
    // Not `ok`: no output is no evidence that a review was written. See `Engine::run`.
    let Some(json) = json else {
        return outcome;
    };
    if json.get("ready").and_then(Value::as_bool) == Some(false) {
        outcome.not_ready = true;
        outcome.reason = json
            .get("reason")
            .and_then(Value::as_str)
            .map(str::to_string);
        return outcome;
    }
    outcome.ok = true;
    outcome.review_id = json.get("id").and_then(Value::as_i64);
    outcome
}

/// `prudence ingest --json`, read.
///
/// The session count is `parsed.sessions`, which is the pipeline's own statistic for how
/// many sessions the store holds after the run. **Nested, not top level**: the frozen
/// Swift app read `json["sessions"]`, which `ingest --json` has never carried, so its
/// "Ingest finished: N sessions" line could not fire and it always said the shorter one.
pub fn describe_ingest(json: Option<&Value>) -> RunOutcome {
    let mut outcome = RunOutcome::of(Action::Ingest);
    // Only with an answer to read. `Engine::run` refuses before reaching here, and this
    // says the same thing so that the function cannot be read as claiming otherwise.
    if json.is_none() {
        return outcome;
    }
    outcome.ok = true;
    outcome.sessions = json
        .and_then(|json| json.get("parsed"))
        .and_then(|parsed| parsed.get("sessions"))
        .and_then(Value::as_i64);
    outcome
}

/* --- what the commands talk to ------------------------------------------------------ */

/// Where the engine is and what version it is, for the interface.
#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineStatus {
    /// Found **and** verified: it answered `--version` with a version.
    pub found: bool,
    pub path: Option<String>,
    pub source: Option<Source>,
    pub version: Option<String>,
    /// Why there is no version, when something was found and could not say what it is.
    pub error_kind: Option<String>,
    pub error: Option<String>,
    /// Whether a path is remembered, so the interface can offer to forget it.
    pub remembered: bool,
}

/// The locator and the one-run-at-a-time rule, in one place.
///
/// Process-wide, because which `prudence` this machine has is a property of the machine
/// and not of a window, and because the login-shell probe must happen once per launch
/// however many surfaces ask.
pub struct Engine {
    locator: Locator,
    running: AtomicBool,
}

static SHARED: OnceLock<Engine> = OnceLock::new();

pub fn shared() -> &'static Engine {
    SHARED.get_or_init(|| Engine {
        locator: Locator::real(),
        running: AtomicBool::new(false),
    })
}

/// Is a run going right now?
///
/// The timed ingest asks before it starts one. [`Engine::run`] would refuse the second
/// run anyway, but refusing is not the same as not asking: a refusal puts "a run is
/// already going" on the page for something the reader never pressed.
pub fn is_running() -> bool {
    shared().running.load(Ordering::SeqCst)
}

/// Holds the "a run is going" flag and clears it however the run ends, panic included.
/// A flag cleared at the end of a happy path is a flag that stays set the first time
/// something throws, and then the buttons never come back.
struct RunGuard<'a>(&'a AtomicBool);

impl Drop for RunGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

impl Engine {
    /// Where the engine is, verified. Spawns a shell and a process; call it off the main
    /// thread.
    pub fn status(&self, remembered: Option<&str>) -> EngineStatus {
        let mut status = EngineStatus {
            remembered: remembered.is_some_and(|value| !value.trim().is_empty()),
            ..EngineStatus::default()
        };
        let Some(found) = self.locator.locate(remembered, SHELL_TIMEOUT) else {
            status.error_kind = Some(EngineError::NotFound.kind().to_string());
            return status;
        };
        status.path = Some(found.path.display().to_string());
        status.source = Some(found.source);
        match version_of(&found.path) {
            Ok(version) => {
                status.found = true;
                status.version = Some(version);
            }
            Err(error) => {
                status.error_kind = Some(error.kind().to_string());
                status.error = Some(error.detail()).filter(|text| !text.is_empty());
            }
        }
        status
    }

    /// Where uv is, if it is in one of the directories the engine is looked for in.
    ///
    /// The Engine tab's Install button needs it. The search order is the engine's own,
    /// because the engine is installed with uv and the two therefore live together; the
    /// login-shell probe is deliberately not repeated for uv, and `installer.rs` says why.
    pub fn locate_uv(&self) -> Option<PathBuf> {
        crate::installer::locate(&self.locator.search_path(), &|path| {
            self.locator.files.is_executable(path)
        })
    }

    /// Ask the engine something and hand back what it printed.
    ///
    /// For `prudence config model`, which has no `--json` and is therefore read rather
    /// than decoded. The arguments are constants at every call site; nothing from a page
    /// reaches this. The executable is verified first, on the same rule as [`Self::run`]:
    /// a remembered path that is no longer the engine is not handed a command.
    ///
    /// No deadline, for the reason registered in `DESIGN.md`: the engine exits. The
    /// verification above it does have one, so a file that hangs never gets this far.
    pub fn read(
        &self,
        remembered: Option<&str>,
        arguments: &[&str],
    ) -> Result<String, EngineError> {
        let Some(found) = self.locator.locate(remembered, SHELL_TIMEOUT) else {
            return Err(EngineError::NotFound);
        };
        // The invocation itself is logged by `run_bounded`; what is logged here is a
        // failure, with the engine's own words, because the command that asked turns it
        // into one word for the page and the words would otherwise be nowhere.
        version_of(&found.path)
            .and_then(|_| run(&found.path, arguments, &[]))
            .map(|answer| answer.stdout)
            .inspect_err(|error| {
                tracing::error!(
                    target: "engine",
                    command = arguments.join(" "),
                    kind = error.kind(),
                    detail = ?error.detail(),
                    "engine failed"
                );
            })
    }

    /// Is this path an engine? The picker's answer, and the reason a chosen path is
    /// verified before it is remembered.
    pub fn verify(&self, path: &Path) -> Result<String, EngineError> {
        if !self.locator.files.is_executable(path) {
            return Err(EngineError::NotFound);
        }
        version_of(path)
    }

    /// Run one action. Blocks until the engine is done, which is minutes for an ingest,
    /// so this is only ever called from an async command.
    ///
    /// `started` is called once this run holds the one-run-at-a-time flag, and never for
    /// a run refused as busy: whoever keeps a record of what is running must not have the
    /// running one's record overwritten by a click that was turned away. `report` is told
    /// about every progress line while the run is going. A review writes none, and a caller
    /// with nothing to report to passes a closure that does nothing; neither changes what
    /// is run.
    pub fn run(
        &self,
        remembered: Option<&str>,
        action: Action,
        force: bool,
        started: &dyn Fn(),
        report: &Reporter,
    ) -> RunOutcome {
        let outcome = self.attempt(remembered, action, force, started, report);
        // Every way a run fails ends here, in the words the run report shows the reader.
        if let Some(kind) = &outcome.error_kind {
            tracing::error!(
                target: "engine",
                action = action.name(),
                kind = %kind,
                detail = ?outcome.error.as_deref().unwrap_or(""),
                "run failed"
            );
        }
        outcome
    }

    fn attempt(
        &self,
        remembered: Option<&str>,
        action: Action,
        force: bool,
        started: &dyn Fn(),
        report: &Reporter,
    ) -> RunOutcome {
        if self
            .running
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return RunOutcome::failed(action, &EngineError::Busy);
        }
        let _guard = RunGuard(&self.running);
        started();

        let Some(found) = self.locator.locate(remembered, SHELL_TIMEOUT) else {
            return RunOutcome::failed(action, &EngineError::NotFound);
        };

        // **Verified here, not only in `status`.** `locate` gates on the exec bit alone,
        // and this module claims "found means verified" a few lines from the top. That was
        // true of what the screen *displayed* and not of what the shell *executed*: the
        // Review screen's button calls `run` without ever consulting `status`, so a
        // remembered path that had since become something else was handed an `ingest` on
        // a click.
        //
        // Be exact about what this buys, because a first version of the test below
        // asserted more than it delivers: **identifying an executable means running it**,
        // so an unidentified file is still spawned once, with `--version`. What it can no
        // longer be handed is an action. It never writes the store, never runs for
        // minutes, and is never detached from the app. Narrowing the blast radius is the
        // whole of it; the picker exists so the user can name an executable, and nothing
        // here can make naming one free.
        if let Err(error) = version_of(&found.path) {
            return RunOutcome::failed(action, &error);
        }

        let arguments = action.arguments(force);
        match run_reporting(&found.path, &arguments, &[], report) {
            Ok(answer) => {
                // What the engine said besides its answer, on standard error only: output
                // is never written to the app log, whose tail leaves the machine.
                if !answer.stderr.trim().is_empty() {
                    eprintln!("[engine] stderr: {}", clipped(&answer.stderr));
                }
                // **No answer is not success.** Both `describe_*` reported success
                // without looking at the exit status, and `describe_review` reported it
                // from *absent* output, on the argument that `review` prints its body
                // only after the row exists. That is a fact about the real engine, and it
                // was applied to whatever binary actually ran: anything exiting 0 with
                // nothing on stdout produced "Review written" on no evidence at all.
                if answer.json.is_none() {
                    return RunOutcome::failed(
                        action,
                        &EngineError::Failed {
                            status: answer.status,
                            message: if !answer.stderr.trim().is_empty() {
                                answer.stderr.clone()
                            } else if !answer.stdout.trim().is_empty() {
                                answer.stdout.clone()
                            } else {
                                String::from("the engine printed no answer")
                            },
                        },
                    );
                }
                match action {
                    Action::Ingest => describe_ingest(answer.json.as_ref()),
                    Action::Review => describe_review(answer.json.as_ref()),
                }
            }
            Err(error) => RunOutcome::failed(action, &error),
        }
    }
}

/// What a file is, beyond its name: enough of its metadata to notice it being replaced.
///
/// Size and modification time, because those are what a reinstall, an upgrade or a
/// `uv tool install` moves, and because reading them is a `stat` rather than a process.
type Identity = (u64, Option<std::time::SystemTime>);

fn identity(executable: &Path) -> Option<Identity> {
    let meta = std::fs::metadata(executable).ok()?;
    Some((meta.len(), meta.modified().ok()))
}

/// What one file was, and what it said it was.
type Verdict = (Identity, Result<String, EngineError>);

/// What each file this launch has asked said it was.
///
/// Keyed by path rather than holding one entry, because the picker verifies whatever file
/// the user points at and a single entry would let a rejected candidate evict the engine's
/// own answer. It grows by one per distinct path asked in a launch, which is the engine
/// plus whatever the user chose in the picker, and it is not kept across a launch.
fn verified() -> &'static Mutex<HashMap<PathBuf, Verdict>> {
    static VERIFIED: OnceLock<Mutex<HashMap<PathBuf, Verdict>>> = OnceLock::new();
    VERIFIED.get_or_init(|| Mutex::new(HashMap::new()))
}

/// What version this executable says it is.
///
/// ## Why the answer is remembered, and what it is remembered against
///
/// "Found means verified" was implemented as **verify on every call**, and every question
/// the app asks the engine goes through one: `status`, `read` and `run` each spawn a
/// `--version` before they spawn anything else. Measured on 2026-09-22, one launch of the
/// app against a copy of the founder's store spawned `prudence` eighteen times, and ten of
/// those were `--version`. Opening the Settings screen costs two more; asking whether a
/// review is ready costs two more again, from each of the two pages.
///
/// The property being defended is that a remembered path which has since become something
/// else is never handed an action. That is a fact about **the file**, not about how
/// recently it was asked, so the answer is kept against the file's own identity: its path,
/// its length and its modification time. Replace, upgrade or move the executable and the
/// identity changes and it is verified again. Nothing is remembered across a launch.
///
fn version_of(executable: &Path) -> Result<String, EngineError> {
    let now = identity(executable);
    let mut held = verified().lock().unwrap();
    if let (Some(now), Some((before, answer))) = (now.as_ref(), held.get(executable)) {
        if before == now {
            return answer.clone();
        }
    }
    // The lock is held across the spawn on purpose, on the same rule as the login-shell
    // probe above it: two surfaces asking at once would otherwise start two processes,
    // and the second one's answer is the first one's answer.
    let answer = run_bounded(executable, &["--version"], &[], Some(VERSION_TIMEOUT), None)
        .and_then(|answer| {
            parse_version(&answer.stdout).ok_or(EngineError::NoVersion(answer.stdout))
        });
    // A file that could not be stat-ed is not remembered: there is nothing to notice it
    // changing by, so the next ask runs it again.
    if let Some(now) = now {
        held.insert(executable.to_path_buf(), (now, answer.clone()));
    }
    answer
}

/// Forget what this file was said to be. For the tests, and for nothing else.
#[cfg(test)]
fn forget_the_version(executable: &Path) {
    verified().lock().unwrap().remove(executable);
}

/* --- the picker --------------------------------------------------------------------- */

/// What the picker ended in. The page asks for the status again afterwards; this only
/// says whether the file was taken, refused, or never chosen.
#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Choice {
    /// The picker was closed without choosing. Not a failure, and nothing to report.
    pub cancelled: bool,
    pub path: Option<String>,
    pub version: Option<String>,
    /// Why the file was refused, as a word the page turns into a sentence.
    pub error_kind: Option<String>,
    pub error: Option<String>,
}

impl Choice {
    pub fn cancelled() -> Self {
        Self {
            cancelled: true,
            ..Self::default()
        }
    }

    pub fn accepted(path: PathBuf, version: String) -> Self {
        Self {
            path: Some(path.display().to_string()),
            version: Some(version),
            ..Self::default()
        }
    }

    pub fn rejected(path: PathBuf, error: &EngineError) -> Self {
        Self {
            path: Some(path.display().to_string()),
            error_kind: Some(error.kind().to_string()),
            error: Some(error.detail()).filter(|text| !text.is_empty()),
            ..Self::default()
        }
    }
}

/// One file, chosen by the user. Blocks until the picker closes, so it belongs on a
/// worker thread; every caller is an `async` command.
///
/// No title and no filter are set. The system's own open panel says "Open", which is
/// already in the reader's language, and an executable has no extension to filter on.
pub fn pick_file(app: &tauri::AppHandle) -> Option<PathBuf> {
    use tauri_plugin_dialog::DialogExt;
    app.dialog()
        .file()
        .blocking_pick_file()
        .and_then(|chosen| chosen.into_path().ok())
}

/* --- the dialog holds the panel open ------------------------------------------------ */

/// Is a file picker open right now?
///
/// The panel dismisses itself when it loses focus, and a picker takes focus, so without
/// this the panel would disappear out from under the user the instant they went looking
/// for the executable. `harness.rs` already has the notion of "something is driving the
/// app, do not auto-dismiss"; this is the same notion for a dialog, and unlike the
/// harness it is in a release build because a user can open a picker.
static DIALOG_OPEN: AtomicBool = AtomicBool::new(false);

pub fn dialog_is_open() -> bool {
    DIALOG_OPEN.load(Ordering::SeqCst)
}

/// Marks a dialog as open and clears it however the scope ends. There is no `set(false)`
/// call anywhere: an early return on a cancelled picker would have skipped it.
pub struct DialogGuard;

impl DialogGuard {
    pub fn open() -> Self {
        DIALOG_OPEN.store(true, Ordering::SeqCst);
        Self
    }
}

impl Drop for DialogGuard {
    fn drop(&mut self) {
        DIALOG_OPEN.store(false, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    /// A filesystem that is a list of paths, so the whole order can be asserted on a
    /// machine that has no `prudence` anywhere.
    struct Fake(Vec<String>);

    #[cfg(unix)]
    impl FileProbe for Fake {
        fn is_executable(&self, path: &Path) -> bool {
            self.0.iter().any(|have| Path::new(have) == path)
        }
    }

    #[cfg(unix)]
    struct NoShell;

    #[cfg(unix)]
    impl LoginShell for NoShell {
        fn locate(&self, _timeout: Duration) -> Option<PathBuf> {
            None
        }
    }

    #[cfg(unix)]
    /// A shell that answers once, and counts how many times it was asked.
    struct CountingShell {
        answer: Option<PathBuf>,
        asked: Arc<Mutex<u32>>,
    }

    #[cfg(unix)]
    impl LoginShell for CountingShell {
        fn locate(&self, _timeout: Duration) -> Option<PathBuf> {
            *self.asked.lock().unwrap() += 1;
            self.answer.clone()
        }
    }

    #[cfg(unix)]
    fn locator(present: &[&str], environment: &[(&str, &str)]) -> Locator {
        Locator::new(
            Box::new(Fake(present.iter().map(|p| p.to_string()).collect())),
            Box::new(NoShell),
            environment
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
            PathBuf::from("/Users/someone"),
        )
    }

    #[cfg(unix)]
    #[test]
    fn the_search_path_is_uvs_order_then_homebrew() {
        let found = locator(
            &[],
            &[
                ("UV_TOOL_BIN_DIR", "/uv/bin"),
                ("XDG_BIN_HOME", "/xdg/bin"),
                // uv's fallback is the sibling `bin` of this, which here is `/xdg/bin`
                // again: the same directory is never probed twice.
                ("XDG_DATA_HOME", "/xdg/share"),
            ],
        )
        .search_path();
        assert_eq!(
            found,
            vec![
                PathBuf::from("/uv/bin"),
                PathBuf::from("/xdg/bin"),
                PathBuf::from("/Users/someone/.local/bin"),
                PathBuf::from("/opt/homebrew/bin"),
                PathBuf::from("/usr/local/bin"),
            ]
        );

        // And the fallback really is read, where it is a directory of its own.
        let separate = locator(&[], &[("XDG_DATA_HOME", "/elsewhere/share")]).search_path();
        assert_eq!(separate.first(), Some(&PathBuf::from("/elsewhere/bin")));
    }

    #[cfg(unix)]
    #[test]
    fn an_empty_variable_is_not_a_directory() {
        // An exported-but-empty `UV_TOOL_BIN_DIR` would otherwise probe `/prudence`.
        let found = locator(&[], &[("UV_TOOL_BIN_DIR", "")]).search_path();
        assert_eq!(
            found.first(),
            Some(&PathBuf::from("/Users/someone/.local/bin"))
        );
    }

    #[cfg(unix)]
    #[test]
    fn a_directory_variable_expands_a_leading_tilde() {
        let found = locator(&[], &[("UV_TOOL_BIN_DIR", "~/tools/bin")]).search_path();
        assert_eq!(
            found.first(),
            Some(&PathBuf::from("/Users/someone/tools/bin"))
        );
    }

    #[cfg(unix)]
    #[test]
    fn nothing_anywhere_is_nothing_found() {
        assert_eq!(locator(&[], &[]).locate_without_shell(None), None);
    }

    #[cfg(unix)]
    #[test]
    fn the_home_local_bin_is_where_uv_tool_install_puts_it() {
        let found = locator(&["/Users/someone/.local/bin/prudence"], &[])
            .locate_without_shell(None)
            .expect("found");
        assert_eq!(
            found.path,
            PathBuf::from("/Users/someone/.local/bin/prudence")
        );
        assert_eq!(
            found.source,
            Source::Directory {
                directory: "/Users/someone/.local/bin".into()
            }
        );
    }

    /// The order, not just the membership: a machine with both answers with uv's.
    #[cfg(unix)]
    #[test]
    fn uvs_directory_wins_over_homebrew() {
        let found = locator(
            &["/uv/bin/prudence", "/opt/homebrew/bin/prudence"],
            &[("UV_TOOL_BIN_DIR", "/uv/bin")],
        )
        .locate_without_shell(None)
        .expect("found");
        assert_eq!(found.path, PathBuf::from("/uv/bin/prudence"));
    }

    #[cfg(unix)]
    #[test]
    fn homebrew_on_apple_silicon_comes_before_the_intel_prefix() {
        let found = locator(
            &["/opt/homebrew/bin/prudence", "/usr/local/bin/prudence"],
            &[],
        )
        .locate_without_shell(None)
        .expect("found");
        assert_eq!(found.path, PathBuf::from("/opt/homebrew/bin/prudence"));
    }

    #[cfg(unix)]
    #[test]
    fn a_chosen_path_wins_over_every_directory() {
        let found = locator(&["/elsewhere/prudence", "/opt/homebrew/bin/prudence"], &[])
            .locate_without_shell(Some("/elsewhere/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/elsewhere/prudence"));
        assert_eq!(found.source, Source::Settings);
    }

    #[cfg(unix)]
    #[test]
    fn a_chosen_path_expands_a_leading_tilde() {
        let found = locator(&["/Users/someone/tools/prudence"], &[])
            .locate_without_shell(Some("~/tools/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/Users/someone/tools/prudence"));
    }

    /// Verified before it is trusted: a remembered path that is no longer executable is
    /// not returned, and the search carries on rather than reporting nothing.
    #[cfg(unix)]
    #[test]
    fn a_chosen_path_that_is_gone_falls_back_to_the_search() {
        let found = locator(&["/opt/homebrew/bin/prudence"], &[])
            .locate_without_shell(Some("/gone/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/opt/homebrew/bin/prudence"));
    }

    #[cfg(unix)]
    #[test]
    fn a_blank_chosen_path_is_no_choice_at_all() {
        let found = locator(&["/opt/homebrew/bin/prudence"], &[])
            .locate_without_shell(Some("   "))
            .expect("found");
        assert_eq!(
            found.source,
            Source::Directory {
                directory: "/opt/homebrew/bin".into()
            }
        );
    }

    #[cfg(unix)]
    #[test]
    fn the_login_shell_is_the_last_resort_and_its_answer_is_probed() {
        let asked = Arc::new(Mutex::new(0));
        let locator = Locator::new(
            Box::new(Fake(vec!["/opt/weird/prudence".into()])),
            Box::new(CountingShell {
                answer: Some(PathBuf::from("/opt/weird/prudence")),
                asked: asked.clone(),
            }),
            HashMap::new(),
            PathBuf::from("/Users/someone"),
        );
        let found = locator.locate(None, Duration::from_secs(1)).expect("found");
        assert_eq!(found.source, Source::LoginShell);
        assert_eq!(*asked.lock().unwrap(), 1);

        // Once per launch, however many times a screen refreshes.
        locator.locate(None, Duration::from_secs(1));
        locator.locate(None, Duration::from_secs(1));
        assert_eq!(*asked.lock().unwrap(), 1);
    }

    /// A shell that names a path which is not executable is not an answer, and asking it
    /// again would not change that.
    #[cfg(unix)]
    #[test]
    fn a_shell_answer_that_is_not_executable_is_not_found() {
        let asked = Arc::new(Mutex::new(0));
        let locator = Locator::new(
            Box::new(Fake(vec![])),
            Box::new(CountingShell {
                answer: Some(PathBuf::from("/opt/weird/prudence")),
                asked: asked.clone(),
            }),
            HashMap::new(),
            PathBuf::from("/Users/someone"),
        );
        assert_eq!(locator.locate(None, Duration::from_secs(1)), None);
        locator.locate(None, Duration::from_secs(1));
        assert_eq!(*asked.lock().unwrap(), 1, "a nil answer is cached too");
    }

    #[cfg(unix)]
    #[test]
    fn the_shell_is_not_asked_when_a_directory_already_answered() {
        let asked = Arc::new(Mutex::new(0));
        let locator = Locator::new(
            Box::new(Fake(vec!["/usr/local/bin/prudence".into()])),
            Box::new(CountingShell {
                answer: None,
                asked: asked.clone(),
            }),
            HashMap::new(),
            PathBuf::from("/Users/someone"),
        );
        assert!(locator.locate(None, Duration::from_secs(1)).is_some());
        assert_eq!(*asked.lock().unwrap(), 0);
    }

    #[cfg(unix)]
    #[test]
    fn the_shells_answer_is_the_first_absolute_line() {
        assert_eq!(
            first_absolute_line("/Users/someone/.local/bin/prudence\n"),
            Some(PathBuf::from("/Users/someone/.local/bin/prudence"))
        );
        // An rc file that prints a banner puts it on stdout ahead of the answer.
        assert_eq!(
            first_absolute_line("welcome back!\n/opt/homebrew/bin/prudence\n"),
            Some(PathBuf::from("/opt/homebrew/bin/prudence"))
        );
        assert_eq!(first_absolute_line("prudence not found\n"), None);
        assert_eq!(first_absolute_line(""), None);
    }

    /* --- the version ---------------------------------------------------------------- */

    #[test]
    fn the_version_is_the_number_click_prints() {
        // What `prudence --version` printed on 2026-09-21, copied from a terminal.
        assert_eq!(
            parse_version("prudence, version 0.4.0\n").as_deref(),
            Some("0.4.0")
        );
    }

    #[test]
    fn a_shorter_format_still_reads_as_long_as_it_names_the_tool() {
        assert_eq!(
            parse_version("prudence 1.2.3rc1").as_deref(),
            Some("1.2.3rc1")
        );
        assert_eq!(
            parse_version("Prudence, version 0.5.0").as_deref(),
            Some("0.5.0")
        );
    }

    /// The two halves of the rule, each on its own. The middle cases are what makes the
    /// picker safe: another program's `--version` is a version, and is not this one.
    #[test]
    fn something_that_is_not_the_engine_answering_is_not_a_version() {
        assert_eq!(parse_version("zsh: command not found: prudence"), None);
        assert_eq!(parse_version("Python 3.12.1"), None);
        assert_eq!(parse_version("git version 2.51.0"), None);
        // No name at all. A file that answers with a bare number could be anything.
        assert_eq!(parse_version("0.4.0"), None);
        assert_eq!(parse_version(""), None);
        assert_eq!(parse_version("\n\n"), None);
    }

    /* --- reading an answer ---------------------------------------------------------- */

    #[test]
    fn a_review_that_was_written_carries_the_engines_own_id() {
        let json = serde_json::json!({ "id": 7, "coverage": 0.4 });
        let outcome = describe_review(Some(&json));
        assert!(outcome.ok && !outcome.not_ready);
        assert_eq!(outcome.review_id, Some(7));
    }

    #[test]
    fn a_review_that_is_not_ready_is_not_a_failure_and_keeps_the_reason() {
        let json = serde_json::json!({
            "ready": false,
            "reason": "not ready: 2 new sessions so far (needs 5)."
        });
        let outcome = describe_review(Some(&json));
        assert!(!outcome.ok);
        assert!(outcome.not_ready);
        assert_eq!(
            outcome.reason.as_deref(),
            Some("not ready: 2 new sessions so far (needs 5).")
        );
        assert_eq!(outcome.error_kind, None, "declining is not an error");
    }

    /// No answer is not a review.
    ///
    /// This used to assert the opposite, on the argument that `review` prints its body
    /// only after the row exists, so output this build could not place still meant a row.
    /// That is a fact about the real engine and it was being applied to whatever binary
    /// actually ran: anything exiting 0 with nothing on stdout reported "Review written"
    /// on no evidence. `Engine::run` refuses before reaching here, and this says the same
    /// thing so the function cannot be read as claiming otherwise.
    #[test]
    fn no_answer_is_not_a_review_that_was_written() {
        let outcome = describe_review(None);
        assert!(
            !outcome.ok,
            "a review was claimed with nothing to show for it"
        );
        assert_eq!(outcome.review_id, None);
    }

    /// The same rule for an ingest, which claimed success unconditionally.
    #[test]
    fn no_answer_is_not_an_ingest_that_ran() {
        let outcome = describe_ingest(None);
        assert!(
            !outcome.ok,
            "an ingest was claimed with nothing to show for it"
        );
        assert_eq!(outcome.sessions, None);
    }

    /// `parsed.sessions`, nested, which is where `ingest --json` actually carries it.
    #[test]
    fn an_ingest_reports_the_session_count_the_pipeline_printed() {
        let json = serde_json::json!({
            "archived": { "new_files": 2 },
            "parsed": { "sessions": 150, "records": 234138 }
        });
        assert_eq!(describe_ingest(Some(&json)).sessions, Some(150));
    }

    #[test]
    fn an_ingest_that_said_nothing_countable_still_finished() {
        let outcome = describe_ingest(Some(&serde_json::json!({ "parsed": {} })));
        assert!(outcome.ok);
        assert_eq!(outcome.sessions, None);
        // The shape the Swift app looked for, which this command has never printed.
        let flat = serde_json::json!({ "sessions": 9 });
        assert_eq!(describe_ingest(Some(&flat)).sessions, None);
    }

    #[test]
    fn every_failure_has_a_word_for_the_page_and_the_engines_own_words_under_it() {
        let cases = [
            (EngineError::NotFound, "notFound", ""),
            (EngineError::Busy, "busy", ""),
            (
                EngineError::Launch("permission denied".into()),
                "launch",
                "permission denied",
            ),
            (
                EngineError::Failed {
                    status: 2,
                    message: "  no repository is enabled\n".into(),
                },
                "failed",
                "no repository is enabled",
            ),
            (
                EngineError::Failed {
                    status: 1,
                    message: "   ".into(),
                },
                "failed",
                "exit 1",
            ),
            (
                EngineError::NoVersion("Python 3.12".into()),
                "noVersion",
                "Python 3.12",
            ),
        ];
        for (error, kind, detail) in cases {
            assert_eq!(error.kind(), kind);
            assert_eq!(error.detail(), detail);
        }
    }

    #[test]
    fn a_wall_of_output_is_clipped_rather_than_shown_whole() {
        let long = "x".repeat(500);
        let detail = EngineError::NoVersion(long).detail();
        assert!(detail.ends_with("..."));
        assert_eq!(detail.chars().count(), 203);
    }

    /* --- the command lines ---------------------------------------------------------- */

    #[test]
    fn every_action_asks_for_json_so_the_answer_is_decoded_and_not_scraped() {
        for action in [Action::Ingest, Action::Review] {
            assert!(action.arguments(false).contains(&"--json"));
        }
    }

    /// The model segment needs an API key this app never holds, so a review written from
    /// a button is written without one.
    #[test]
    fn a_review_from_a_button_never_calls_a_model() {
        assert_eq!(
            Action::Review.arguments(false),
            vec!["review", "--json", "--no-explain"]
        );
        assert_eq!(
            Action::Review.arguments(true),
            vec!["review", "--json", "--no-explain", "--force"]
        );
    }

    #[test]
    fn force_is_only_for_a_review() {
        // `ingest` has no `--force`, and passing one would make the button exit 2.
        assert!(!Action::Ingest.arguments(true).contains(&"--force"));
    }

    #[test]
    fn only_the_two_actions_the_app_offers_are_actions() {
        assert_eq!(Action::parse("ingest"), Some(Action::Ingest));
        assert_eq!(Action::parse("review"), Some(Action::Review));
        for other in ["forget", "rebuild", "", "ingest --force", "INGEST"] {
            assert_eq!(Action::parse(other), None, "{other} is not an action");
        }
    }

    /* --- the tilde, shared with store.rs -------------------------------------------- */

    #[cfg(unix)]
    #[test]
    fn only_a_leading_tilde_is_a_home_directory() {
        let home = Path::new("/Users/someone");
        assert_eq!(expand_tilde(PathBuf::from("~"), home), home);
        assert_eq!(
            expand_tilde(PathBuf::from("~/bin/prudence"), home),
            PathBuf::from("/Users/someone/bin/prudence")
        );
        assert_eq!(
            expand_tilde(PathBuf::from("/tmp/~/x"), home),
            PathBuf::from("/tmp/~/x")
        );
        assert_eq!(
            expand_tilde(PathBuf::from("~copy"), home),
            PathBuf::from("~copy")
        );
    }

    /* --- the spawn path, against an engine a test owns ------------------------------ */

    #[cfg(unix)]
    fn scratch(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("prudence-engine-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("a scratch directory");
        dir
    }

    #[cfg(unix)]
    /// A `prudence` that is a shell script.
    ///
    /// The spawn path, the environment and the JSON decoding are exercised without the
    /// real engine, so the test says the same thing on a machine that has never installed
    /// it, and nothing a test starts can reach a real store.
    fn fake_engine(directory: &str, body: &str) -> PathBuf {
        let path = scratch(directory).join(EXECUTABLE);
        std::fs::write(&path, format!("#!/bin/sh\n{body}\n")).expect("the script");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))
                .expect("executable");
        }
        path
    }

    /// A file that answers `--version` forever does not grow the process without bound.
    ///
    /// The picker takes any file. `/usr/bin/yes --version` ignores the argument and prints
    /// forever, and `Command::output()` buffers to EOF with no limit, so choosing it grew
    /// the app until the system killed it. The cap keeps what is useful and the deadline
    /// ends the probe.
    #[cfg(unix)]
    #[test]
    fn a_child_that_never_stops_printing_is_capped_and_then_killed() {
        let executable = fake_engine(
            "endless",
            r#"while :; do printf 'x%.0s' $(seq 1 1000); done"#,
        );
        let started = Instant::now();
        let answer = run_bounded(
            &executable,
            &["--version"],
            &[],
            Some(Duration::from_secs(2)),
            None,
        );

        assert!(answer.is_err(), "an endless child was treated as an answer");
        assert!(
            started.elapsed() < Duration::from_secs(20),
            "the probe ran for {:?}, so the deadline did not end it",
            started.elapsed()
        );
    }

    /// Output past the cap is dropped, and the child still finishes on its own.
    #[cfg(unix)]
    #[test]
    fn output_past_the_cap_is_dropped_rather_than_kept() {
        // Five megabytes against a four megabyte cap.
        let executable = fake_engine(
            "loud",
            r#"i=0; while [ $i -lt 5 ]; do dd if=/dev/zero bs=1048576 count=1 2>/dev/null | tr '\0' 'x'; i=$((i+1)); done"#,
        );
        let answer = run(&executable, &["--version"], &[]).expect("the child finished");
        assert!(
            answer.stdout.len() <= OUTPUT_CAP,
            "kept {} bytes against a cap of {OUTPUT_CAP}",
            answer.stdout.len()
        );
        assert!(answer.stdout.len() > 1024, "nothing was kept at all");
    }

    /// A click turned away because a run is already going must not be told it started:
    /// `activity.rs` records what is running from this call, and a refused run that called
    /// it would overwrite the running one's record with its own action.
    #[cfg(unix)]
    #[test]
    fn a_run_refused_as_busy_is_never_told_it_started() {
        let engine = Engine {
            locator: Locator::new(
                Box::new(RealFiles),
                Box::new(NoShell),
                HashMap::new(),
                scratch("busy"),
            ),
            running: AtomicBool::new(true),
        };
        let told = AtomicBool::new(false);
        let outcome = engine.run(
            None,
            Action::Review,
            false,
            &|| told.store(true, Ordering::SeqCst),
            &|_| {},
        );
        assert_eq!(outcome.error_kind.as_deref(), Some("busy"));
        assert!(
            !told.load(Ordering::SeqCst),
            "a busy run was told it started"
        );
    }

    /// A run that takes the flag is told so before anything else happens, even one that
    /// then finds no engine: whoever was told it started is always told how it ended.
    #[cfg(unix)]
    #[test]
    fn a_run_that_takes_the_flag_is_told_it_started() {
        let engine = Engine {
            locator: Locator::new(
                Box::new(RealFiles),
                Box::new(NoShell),
                HashMap::new(),
                scratch("started"),
            ),
            running: AtomicBool::new(false),
        };
        let told = AtomicBool::new(false);
        let outcome = engine.run(
            Some("/nonexistent/prudence"),
            Action::Ingest,
            false,
            &|| told.store(true, Ordering::SeqCst),
            &|_| {},
        );
        assert!(
            told.load(Ordering::SeqCst),
            "a run that took the flag was not told"
        );
        assert!(!outcome.ok);
    }

    /// The run path verifies, not only the status path.
    ///
    /// `locate` gates on the exec bit alone. A remembered path that is executable and is
    /// not the engine was spawned on a click, because only `status` ever asked
    /// `--version` and the Review screen's button does not call `status`.
    #[cfg(unix)]
    #[test]
    fn a_remembered_file_that_is_not_the_engine_is_refused_before_it_is_run() {
        // It answers `--version` with a version, and it is not the engine: the check is
        // that the answer names `prudence`, which this does not. The script records every
        // argument list it is called with, because the point is not that it is never run
        // (asking `--version` runs it) but that it is never handed an action.
        let log = scratch("imposter").join("argv.log");
        let executable = fake_engine(
            "imposter",
            &format!(
                r#"printf '%s\n' "$*" >> "{}"; printf 'Python 3.12.1'; exit 0"#,
                log.display()
            ),
        );
        let _ = std::fs::remove_file(&log);
        let engine = Engine {
            locator: Locator::new(
                Box::new(RealFiles),
                Box::new(NoShell),
                HashMap::new(),
                scratch("imposter"),
            ),
            running: AtomicBool::new(false),
        };

        let outcome = engine.run(
            Some(&executable.display().to_string()),
            Action::Ingest,
            false,
            &|| {},
            &|_| {},
        );

        assert!(
            !outcome.ok,
            "a file that is not the engine was run and reported success"
        );
        assert_eq!(
            outcome.error_kind.as_deref(),
            Some("noVersion"),
            "the refusal did not say why: {outcome:?}"
        );

        // Spawned for `--version`, which is unavoidable, and never for the action.
        let called = std::fs::read_to_string(&log).unwrap_or_default();
        let calls: Vec<&str> = called.lines().map(str::trim).collect();
        assert_eq!(
            calls,
            vec!["--version"],
            "the imposter was handed an action"
        );
    }

    /// The child is in its own process group, which is what stops the app from aborting an
    /// ingest when it quits. That defect left the founder's store copy with two `app_*`
    /// objects out of nine, and it had no test.
    #[cfg(unix)]
    #[test]
    fn the_child_runs_in_its_own_process_group() {
        let executable = fake_engine(
            "pgid",
            r#"printf '{"pgid":"%s","own":"%s"}' "$(ps -o pgid= -p $$ | tr -d ' ')" "$$""#,
        );
        let answer = run(&executable, &["ingest"], &[]).expect("the child ran");
        let json = answer
            .json
            .clone()
            .expect("the child printed its own group");
        let group = json
            .get("pgid")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let own = json
            .get("own")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();

        assert_eq!(
            group, own,
            "the child is not the leader of its own group: {answer:?}"
        );
        let ours = std::process::id().to_string();
        assert_ne!(group, ours, "the child shares this process's group");
    }

    #[cfg(unix)]
    #[test]
    fn a_run_reaches_the_engine_with_its_arguments_and_the_store_it_was_pointed_at() {
        let executable = fake_engine(
            "argv",
            r#"printf '{"argv":"%s","internal":"%s","data":"%s","config":"%s"}' \
                "$*" "$PRUDENCE_INTERNAL" "$PRUDENCE_DATA_DIR" "$PRUDENCE_CONFIG_DIR""#,
        );
        let copy = scratch("argv").join("store").display().to_string();
        let answer = run(
            &executable,
            &Action::Ingest.arguments(false),
            &[
                ("PRUDENCE_DATA_DIR", copy.as_str()),
                ("PRUDENCE_CONFIG_DIR", copy.as_str()),
            ],
        )
        .expect("it ran");

        let json = answer.json.expect("the fake answered with JSON");
        assert_eq!(json["argv"], "ingest --json --progress");
        // The marker the capture hooks and a user's rc files can guard against.
        assert_eq!(json["internal"], "1");
        // Both, every time: an ingest writes, and one pointed at a real store would
        // modify somebody's data.
        assert_eq!(json["data"], copy);
        assert_eq!(json["config"], copy);
    }

    /// The child gets this process's environment, which is the whole isolation story.
    ///
    /// The module header says an app pointed at a copy of the store "can never have the
    /// engine ingest into the real one", and that claim rests entirely on `Command`
    /// inheriting the parent's environment: production passes no extra variables at all.
    /// Nothing asserted it. The test above passes `PRUDENCE_DATA_DIR` explicitly, which
    /// would keep passing if inheritance were lost tomorrow, and then an app launched
    /// against a scratch directory would quietly ingest into the founder's own store.
    ///
    /// The variable is set on this process for the length of the test and removed after.
    /// It is not one anything else in the suite reads.
    #[cfg(unix)]
    #[test]
    fn the_child_inherits_this_process_environment_with_nothing_passed() {
        let executable = fake_engine(
            "inherited",
            r#"printf '{"data":"%s","config":"%s"}' "$PRUDENCE_DATA_DIR" "$PRUDENCE_CONFIG_DIR""#,
        );
        let copy = scratch("inherited").join("store").display().to_string();
        // Safety: this process is the test binary and the variable is read by the child
        // through `Command`'s inherited environment, which is the thing under test.
        unsafe {
            std::env::set_var("PRUDENCE_DATA_DIR", &copy);
            std::env::set_var("PRUDENCE_CONFIG_DIR", &copy);
        }
        let answer = run(&executable, &Action::Ingest.arguments(false), &[]);
        unsafe {
            std::env::remove_var("PRUDENCE_DATA_DIR");
            std::env::remove_var("PRUDENCE_CONFIG_DIR");
        }

        let json = answer.expect("it ran").json.expect("the fake answered");
        assert_eq!(json["data"], copy, "the child did not inherit the store");
        assert_eq!(json["config"], copy, "the child did not inherit the config");
    }

    /// A non-zero exit whose stdout is still JSON is an answer, not an error: the reason
    /// the caller wants is in that body.
    #[cfg(unix)]
    #[test]
    fn a_json_body_is_an_answer_even_on_a_non_zero_exit() {
        let executable = fake_engine(
            "declined",
            r#"printf '{"ready": false, "reason": "not ready: 2 new sessions."}'; exit 1"#,
        );
        let answer = run(&executable, &["review", "--json"], &[]).expect("an answer");
        assert_eq!(answer.status, 1);
        let outcome = describe_review(answer.json.as_ref());
        assert!(outcome.not_ready);
        assert_eq!(
            outcome.reason.as_deref(),
            Some("not ready: 2 new sessions.")
        );
    }

    #[cfg(unix)]
    #[test]
    fn a_failure_carries_the_engines_own_words_from_its_standard_error() {
        let executable = fake_engine("angry", "echo 'No repository is enabled.' >&2; exit 2");
        let error = run(&executable, &["ingest", "--json"], &[]).unwrap_err();
        assert_eq!(error.kind(), "failed");
        assert_eq!(error.detail(), "No repository is enabled.");
    }

    #[test]
    fn something_that_cannot_be_started_says_so_rather_than_panicking() {
        let error = run(Path::new("/nonexistent/prudence"), &["--version"], &[]).unwrap_err();
        assert_eq!(error.kind(), "launch");
        assert!(!error.detail().is_empty(), "the reason the launch failed");
    }

    /// Found means verified: the picker and the search both go through this.
    #[cfg(unix)]
    #[test]
    fn a_file_that_cannot_say_what_version_it_is_is_not_the_engine() {
        let engine = fake_engine("real", "echo 'prudence, version 0.4.0'");
        assert_eq!(version_of(&engine).as_deref(), Ok("0.4.0"));

        // A real thing a picker can land on, and the reason the line has to name the tool.
        let other = fake_engine("python", "echo 'Python 3.12.1'");
        assert_eq!(version_of(&other).unwrap_err().kind(), "noVersion");
    }

    /// The engine is asked what it is once per **file**, not once per question.
    ///
    /// Every question the app asks the engine verifies the executable first, and one launch
    /// spawned `prudence --version` ten times for it. The property being kept is that a
    /// path which has become something else is never handed an action, and that is a fact
    /// about the file, so the answer is remembered against the file's own identity and a
    /// replacement is verified again.
    #[cfg(unix)]
    #[test]
    fn the_engine_is_asked_what_it_is_once_per_file_rather_than_once_per_question() {
        let counter = scratch("counted").join("spawns");
        let executable = fake_engine(
            "counted",
            &format!(
                "echo x >> {}\necho 'prudence, version 0.4.0'",
                counter.display()
            ),
        );
        let spawns = || {
            std::fs::read_to_string(&counter)
                .map(|text| text.lines().count())
                .unwrap_or(0)
        };
        forget_the_version(&executable);

        assert_eq!(version_of(&executable).as_deref(), Ok("0.4.0"));
        assert_eq!(spawns(), 1);

        // Four more questions of the same file. None of them is a process.
        for _ in 0..4 {
            assert_eq!(version_of(&executable).as_deref(), Ok("0.4.0"));
        }
        assert_eq!(spawns(), 1, "the same file was run again to ask what it is");

        // Replaced under the app, which is what an upgrade or a reinstall is. It has to
        // be asked again, because the guard this memory could weaken is exactly this case.
        // The sleep is the file system's resolution, not a wait for the app: a rewrite
        // inside one second can land on the same modification time, and then the only
        // thing left to notice it by is the length.
        std::thread::sleep(Duration::from_millis(1100));
        let replaced = fake_engine(
            "counted",
            &format!(
                "echo x >> {}\necho 'prudence, version 9.9.9'",
                counter.display()
            ),
        );
        assert_eq!(version_of(&replaced).as_deref(), Ok("9.9.9"));
        assert_eq!(spawns(), 2, "a replaced engine was not asked again");
        forget_the_version(&replaced);
    }

    /* --- the real engine, against a copy and nothing else --------------------------- */

    /// Ignored by default, because it needs `prudence` installed on this machine and a
    /// copy of a store to point it at. It is the one check that the whole path really
    /// runs: locate, verify, spawn, decode.
    ///
    ///     PRUDENCE_DATA_DIR=<a copy> PRUDENCE_CONFIG_DIR=<a copy> \
    ///       cargo test -- --ignored --nocapture
    ///
    /// Both variables are required rather than defaulted, so the test cannot run against
    /// whatever store this machine happens to have in its standard location.
    #[test]
    #[ignore = "needs the real prudence and a copy of a store to point it at"]
    fn the_real_engine_locates_answers_and_writes_only_where_it_was_pointed() {
        let data = std::env::var("PRUDENCE_DATA_DIR").expect("point this at a copy of a store");
        let config = std::env::var("PRUDENCE_CONFIG_DIR").expect("point this at a copy");

        let found = Locator::real()
            .locate(None, SHELL_TIMEOUT)
            .expect("no prudence on this machine");
        let version = version_of(&found.path).expect("a version");
        eprintln!(
            "[test] {} ({:?}) says {version}",
            found.path.display(),
            found.source
        );

        let answer = run(
            &found.path,
            &Action::Review.arguments(false),
            &[
                ("PRUDENCE_DATA_DIR", data.as_str()),
                ("PRUDENCE_CONFIG_DIR", config.as_str()),
            ],
        )
        .expect("review ran");
        let outcome = describe_review(answer.json.as_ref());
        eprintln!(
            "[test] review: ok={} not_ready={} id={:?} reason={:?}",
            outcome.ok, outcome.not_ready, outcome.review_id, outcome.reason
        );
        assert!(
            outcome.ok || outcome.not_ready,
            "review neither wrote nor declined: {outcome:?}"
        );
    }

    /* --- what a run says while it is going ------------------------------------------
     *
     * The fixture is a **recording**, not a hand-written stream: `fixtures/`'s
     * `ingest-progress.jsonl` is the standard error of one real
     * `prudence ingest --json --progress` against a copy of the founder's store on
     * 2026-09-22. A stream somebody wrote by hand would agree with whatever this module
     * expects, which is the thing under test.
     */

    fn recorded_stream() -> String {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/ingest-progress.jsonl");
        std::fs::read_to_string(&path).expect("the recorded progress stream")
    }

    /// The eleven steps `prudence ingest --progress` walks, in the order it walks them.
    const STEPS: [&str; 11] = [
        "repositories",
        "archive",
        "parse",
        "hooks",
        "turn_trees",
        "commits",
        "attribution",
        "outcomes",
        "facts",
        "observations",
        "views",
    ];

    #[test]
    fn a_recorded_run_reads_as_the_engines_own_sequence_of_steps() {
        let events: Vec<Progress> = recorded_stream()
            .lines()
            .map(|line| parse_progress(line).unwrap_or_else(|| panic!("not progress: {line}")))
            .collect();
        assert_eq!(events.len(), 116, "the recording is not the one committed");

        // The steps, in order, each one entered once and never returned to.
        let mut walked: Vec<&str> = Vec::new();
        for event in &events {
            if walked.last() != Some(&event.step.as_str()) {
                walked.push(&event.step);
            }
        }
        assert_eq!(walked, STEPS);

        for event in &events {
            assert_eq!(event.steps, 11, "{event:?}");
            assert_eq!(
                event.step_index,
                (STEPS.iter().position(|step| *step == event.step).unwrap() + 1) as u64,
                "{event:?}"
            );
            assert!(
                event.current <= event.total,
                "past its own total: {event:?}"
            );
            assert!(
                !event.unit.is_empty() && !event.label.is_empty(),
                "{event:?}"
            );
        }

        // The first and the last, in full: what the panel draws when a run starts and what
        // it draws just before the outcome sentence replaces it.
        assert_eq!(
            events[0],
            Progress {
                step: "repositories".into(),
                step_index: 1,
                steps: 11,
                current: 0,
                total: 3,
                unit: "repositories".into(),
                label: "Reading repositories".into(),
            }
        );
        assert_eq!(events[events.len() - 1].step, "views");
        assert_eq!(events[events.len() - 1].current, 9);
        assert_eq!(events[events.len() - 1].total, 9);
    }

    /// Anything that is not one of the engine's progress objects is something the engine
    /// said, and is kept as the failure text. This is the whole of the rule: a malformed
    /// line must neither be drawn as progress nor end the run.
    #[test]
    fn a_line_that_is_not_progress_is_kept_as_what_the_engine_said() {
        assert_eq!(parse_progress("Traceback (most recent call last):"), None);
        assert_eq!(parse_progress(""), None);
        // Valid JSON, and not an event of this kind.
        assert_eq!(
            parse_progress(r#"{"event": "finished", "step": "views"}"#),
            None
        );
        assert_eq!(parse_progress(r#"{"step": "archive", "current": 1}"#), None);
        // Half an object, which is what a line torn in two by a buffer looks like.
        assert_eq!(
            parse_progress(r#"{"event": "progress", "step": "arch"#),
            None
        );
    }

    #[test]
    fn the_reader_reports_the_progress_lines_and_keeps_the_rest() {
        let recorded = recorded_stream();
        let mixed = format!(
            "{}Traceback (most recent call last):\n  File \"ingest.py\", line 3\nValueError: no\n",
            recorded
        );
        let seen = Mutex::new(Vec::new());
        let report = |progress: &Progress| seen.lock().unwrap().push(progress.clone());

        let kept = progress_reader(mixed.as_bytes(), Some(&report));

        assert_eq!(
            seen.lock().unwrap().len(),
            116,
            "the events were not reported"
        );
        assert_eq!(
            kept,
            "Traceback (most recent call last):\n  File \"ingest.py\", line 3\nValueError: no\n",
            "the failure text is not the engine's own words alone"
        );
    }

    /// Nobody listening is not a reason to keep a hundred JSON objects as the failure
    /// text: `run` is called with no reporter from the version probe and from a test.
    #[test]
    fn progress_lines_are_dropped_even_with_nothing_listening() {
        let kept = progress_reader(recorded_stream().as_bytes(), None);
        assert_eq!(kept, "");
    }

    /// A child that writes no newline for ever does not grow this process.
    #[test]
    fn one_endless_line_is_capped_rather_than_buffered_whole() {
        let long = "x".repeat(LINE_CAP * 3);
        let kept = progress_reader(long.as_bytes(), None);
        assert_eq!(kept.trim_end().len(), LINE_CAP);
    }

    /// The run path, end to end, against an engine the test owns: the events arrive while
    /// it is running, stdout is still the answer, and stderr is only what it said.
    #[cfg(unix)]
    #[test]
    fn a_run_reports_every_progress_line_and_still_answers() {
        let executable = fake_engine(
            "reporting",
            r#"printf '{"event": "progress", "step": "archive", "step_index": 2, "steps": 11, "current": 17, "total": 494, "unit": "files", "label": "Archiving beatos"}\n' >&2
printf 'a warning nobody translated\n' >&2
printf '{"event": "progress", "step": "views", "step_index": 11, "steps": 11, "current": 9, "total": 9, "unit": "tables", "label": "Rebuilding the app views"}\n' >&2
printf '{"parsed": {"sessions": 151}}'"#,
        );
        let seen = Mutex::new(Vec::new());
        let report = |progress: &Progress| seen.lock().unwrap().push(progress.clone());

        let answer = run_reporting(
            &executable,
            &["ingest", "--json", "--progress"],
            &[],
            &report,
        )
        .expect("it ran");

        let events = seen.lock().unwrap().clone();
        assert_eq!(events.len(), 2, "the run reported {events:?}");
        assert_eq!(events[0].step, "archive");
        assert_eq!(events[0].current, 17);
        assert_eq!(events[0].total, 494);
        assert_eq!(events[1].step_index, 11);
        assert_eq!(answer.stderr, "a warning nobody translated\n");
        assert_eq!(describe_ingest(answer.json.as_ref()).sessions, Some(151));
    }

    /* --- the dialog guard ----------------------------------------------------------- */

    #[test]
    fn a_dialog_guard_clears_itself_however_the_scope_ends() {
        assert!(!dialog_is_open());
        {
            let _open = DialogGuard::open();
            assert!(dialog_is_open());
        }
        assert!(
            !dialog_is_open(),
            "a cancelled picker still clears the flag"
        );

        // And a panic on the way out, which is the case a `set(false)` call would miss.
        let _ = std::panic::catch_unwind(|| {
            let _open = DialogGuard::open();
            panic!("the picker blew up");
        });
        assert!(!dialog_is_open());
    }
}
