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
use std::time::Duration;

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
pub fn run(
    executable: &Path,
    arguments: &[&str],
    environment: &[(&str, &str)],
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

    let output = command
        .output()
        .map_err(|error| EngineError::Launch(error.to_string()))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let json = serde_json::from_str::<Value>(&stdout).ok();
    let status = output.status.code().unwrap_or(-1);

    if !output.status.success() && json.is_none() {
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
    pub fn arguments(self, force: bool) -> Vec<&'static str> {
        match self {
            Self::Ingest => vec!["ingest", "--json"],
            Self::Review if force => vec!["review", "--json", "--no-explain", "--force"],
            Self::Review => vec!["review", "--json", "--no-explain"],
        }
    }
}

/// What a run did, for the interface. Every figure in it is one the engine printed.
#[derive(Debug, Clone, Default, Serialize)]
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
    let Some(json) = json else {
        outcome.ok = true;
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
    pub fn run(&self, remembered: Option<&str>, action: Action, force: bool) -> RunOutcome {
        if self
            .running
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return RunOutcome::failed(action, &EngineError::Busy);
        }
        let _guard = RunGuard(&self.running);

        let Some(found) = self.locator.locate(remembered, SHELL_TIMEOUT) else {
            return RunOutcome::failed(action, &EngineError::NotFound);
        };
        let arguments = action.arguments(force);
        eprintln!("[engine] {} {}", found.path.display(), arguments.join(" "));
        match run(&found.path, &arguments, &[]) {
            Ok(answer) => {
                eprintln!("[engine] {} exit {}", action.name(), answer.status);
                if !answer.stderr.trim().is_empty() {
                    eprintln!("[engine] stderr: {}", clipped(&answer.stderr));
                }
                match action {
                    Action::Ingest => describe_ingest(answer.json.as_ref()),
                    Action::Review => describe_review(answer.json.as_ref()),
                }
            }
            Err(error) => {
                eprintln!("[engine] {} failed: {}", action.name(), error.detail());
                RunOutcome::failed(action, &error)
            }
        }
    }
}

fn version_of(executable: &Path) -> Result<String, EngineError> {
    let answer = run(executable, &["--version"], &[])?;
    parse_version(&answer.stdout).ok_or(EngineError::NoVersion(answer.stdout))
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

    /// A filesystem that is a list of paths, so the whole order can be asserted on a
    /// machine that has no `prudence` anywhere.
    struct Fake(Vec<String>);

    impl FileProbe for Fake {
        fn is_executable(&self, path: &Path) -> bool {
            self.0.iter().any(|have| Path::new(have) == path)
        }
    }

    struct NoShell;

    impl LoginShell for NoShell {
        fn locate(&self, _timeout: Duration) -> Option<PathBuf> {
            None
        }
    }

    /// A shell that answers once, and counts how many times it was asked.
    struct CountingShell {
        answer: Option<PathBuf>,
        asked: Arc<Mutex<u32>>,
    }

    impl LoginShell for CountingShell {
        fn locate(&self, _timeout: Duration) -> Option<PathBuf> {
            *self.asked.lock().unwrap() += 1;
            self.answer.clone()
        }
    }

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

    #[test]
    fn an_empty_variable_is_not_a_directory() {
        // An exported-but-empty `UV_TOOL_BIN_DIR` would otherwise probe `/prudence`.
        let found = locator(&[], &[("UV_TOOL_BIN_DIR", "")]).search_path();
        assert_eq!(
            found.first(),
            Some(&PathBuf::from("/Users/someone/.local/bin"))
        );
    }

    #[test]
    fn a_directory_variable_expands_a_leading_tilde() {
        let found = locator(&[], &[("UV_TOOL_BIN_DIR", "~/tools/bin")]).search_path();
        assert_eq!(
            found.first(),
            Some(&PathBuf::from("/Users/someone/tools/bin"))
        );
    }

    #[test]
    fn nothing_anywhere_is_nothing_found() {
        assert_eq!(locator(&[], &[]).locate_without_shell(None), None);
    }

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

    #[test]
    fn a_chosen_path_wins_over_every_directory() {
        let found = locator(&["/elsewhere/prudence", "/opt/homebrew/bin/prudence"], &[])
            .locate_without_shell(Some("/elsewhere/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/elsewhere/prudence"));
        assert_eq!(found.source, Source::Settings);
    }

    #[test]
    fn a_chosen_path_expands_a_leading_tilde() {
        let found = locator(&["/Users/someone/tools/prudence"], &[])
            .locate_without_shell(Some("~/tools/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/Users/someone/tools/prudence"));
    }

    /// Verified before it is trusted: a remembered path that is no longer executable is
    /// not returned, and the search carries on rather than reporting nothing.
    #[test]
    fn a_chosen_path_that_is_gone_falls_back_to_the_search() {
        let found = locator(&["/opt/homebrew/bin/prudence"], &[])
            .locate_without_shell(Some("/gone/prudence"))
            .expect("found");
        assert_eq!(found.path, PathBuf::from("/opt/homebrew/bin/prudence"));
    }

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

    /// `review` prints its body only after the row exists, so output this build cannot
    /// place is still a review that was written.
    #[test]
    fn a_review_answer_this_build_cannot_place_still_counts_as_written() {
        let outcome = describe_review(None);
        assert!(outcome.ok);
        assert_eq!(outcome.review_id, None);
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

    fn scratch(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("prudence-engine-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("a scratch directory");
        dir
    }

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
        assert_eq!(json["argv"], "ingest --json");
        // The marker the capture hooks and a user's rc files can guard against.
        assert_eq!(json["internal"], "1");
        // Both, every time: an ingest writes, and one pointed at a real store would
        // modify somebody's data.
        assert_eq!(json["data"], copy);
        assert_eq!(json["config"], copy);
    }

    /// A non-zero exit whose stdout is still JSON is an answer, not an error: the reason
    /// the caller wants is in that body.
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
    #[test]
    fn a_file_that_cannot_say_what_version_it_is_is_not_the_engine() {
        let engine = fake_engine("real", "echo 'prudence, version 0.4.0'");
        assert_eq!(version_of(&engine).as_deref(), Ok("0.4.0"));

        // A real thing a picker can land on, and the reason the line has to name the tool.
        let other = fake_engine("python", "echo 'Python 3.12.1'");
        assert_eq!(version_of(&other).unwrap_err().kind(), "noVersion");
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
