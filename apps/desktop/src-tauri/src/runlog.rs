//! What the engine wrote about its own runs, read: `<data dir>/logs/runs.jsonl`.
//!
//! ## The file
//!
//! `src/prudence/store/runlog.py` writes one JSON object per line per run of `ingest`,
//! `rebuild`, `review` and the other commands that change something: the command, the
//! versions, the machine, each step's seconds and counts, the warnings (a kind, a count and
//! a sample that is shape only), the self-checks with the numbers they compared, and the
//! error. A record is written when the run starts with `ended_at` null and completed when
//! it ends, so a record that stays null is a run that never finished.
//!
//! An engine older than the run log writes no file, and then there is nothing to read and
//! nothing to say: the answer is empty, not an error.
//!
//! ## How it is read
//!
//! **From the end, a block at a time**, until enough runs are in hand. The file grows with
//! every run and the app only ever wants the last few, so it is never loaded whole.
//!
//! **The newest line for a run wins.** Whether the engine completes a record by rewriting
//! the file or by appending a second line with the same `run_id`, reading newest first and
//! keeping the first line seen for each id gives the same answer.
//!
//! **A line that does not parse is counted, not guessed at.** One that ends in a newline is
//! a record the engine finished writing and this build cannot read; it is counted in
//! `unreadable` and said in the app log by position only. The last line, when nothing
//! follows it, is the one exception: it is the engine's write in progress, or one it was
//! cut off in the middle of, and neither is a record yet.
//!
//! Every field is the engine's own name and its own value. The app computes nothing here;
//! `src/store/runs.js` sums a count and tells a failed check from a passing one.

use std::collections::HashSet;
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The run log's name inside `<data dir>/logs`.
pub const FILE: &str = "runs.jsonl";

/// How much is read at a time, from the end backwards.
const BLOCK: u64 = 64 * 1024;

/// The most runs the page may ask for at once. The Engine tab lists ten; the status row
/// looks further back for the last ingest among reviews and scans.
pub const MOST: usize = 200;

/// One run, as the engine recorded it. Only what a surface draws is carried: the machine,
/// the store's size and an error's traceback stay in the file for `prudence diagnose`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Run {
    pub run_id: Option<String>,
    pub command: Vec<String>,
    pub started_at: Option<String>,
    /// Null while the run goes, and for good when it was interrupted.
    pub ended_at: Option<String>,
    pub engine_version: Option<Value>,
    pub steps: Vec<Step>,
    pub warnings: Vec<Warning>,
    pub checks: Vec<Check>,
    pub error: Option<RunError>,
    pub exit: Option<i64>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Step {
    pub name: String,
    pub seconds: Option<f64>,
    pub counts: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Warning {
    pub kind: String,
    pub count: i64,
    /// Shape only, as the engine wrote it: key names, a type, a line number.
    pub sample: Value,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Check {
    pub name: String,
    /// Absent is not a failure: a check the engine did not say the verdict of is not one
    /// this app may call failed.
    pub ok: Option<bool>,
    pub numbers: Map<String, Value>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RunError {
    #[serde(rename = "type")]
    pub kind: String,
    pub message: String,
}

/// The last runs, newest first, and how many finished lines could not be read on the way.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Runs {
    pub runs: Vec<Run>,
    pub unreadable: usize,
}

/// The run log beside the app log, in the engine's `logs` directory.
pub fn file(logs: &Path) -> PathBuf {
    logs.join(FILE)
}

/// The last `wanted` runs in the file, newest first.
pub fn read(path: &Path, wanted: usize) -> io::Result<Runs> {
    let mut found = Runs::default();
    let mut file = match File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(found),
        Err(error) => return Err(error),
    };
    let mut seen = HashSet::new();
    let mut position = file.metadata()?.len();
    // The bytes read but not yet handed out as lines. Its start may be the middle of a
    // line, which is why only what follows its last newline is ever taken from it.
    let mut pending: Vec<u8> = Vec::new();
    // Whether the next line taken ended in a newline. The first one taken is whatever
    // follows the file's last newline, so it did not.
    let mut terminated = false;

    while found.runs.len() < wanted {
        if let Some(at) = pending.iter().rposition(|&byte| byte == b'\n') {
            let line = pending.split_off(at + 1);
            pending.pop();
            take(&line, terminated, wanted, &mut found, &mut seen);
            terminated = true;
            continue;
        }
        if position == 0 {
            // The file's first line, with nothing before it to find.
            take(&pending, terminated, wanted, &mut found, &mut seen);
            break;
        }
        let step = BLOCK.min(position);
        position -= step;
        file.seek(SeekFrom::Start(position))?;
        let mut block = vec![0; step as usize];
        file.read_exact(&mut block)?;
        block.extend_from_slice(&pending);
        pending = block;
    }
    Ok(found)
}

fn take(
    line: &[u8],
    terminated: bool,
    wanted: usize,
    found: &mut Runs,
    seen: &mut HashSet<String>,
) {
    let text = String::from_utf8_lossy(line);
    let text = text.trim();
    if text.is_empty() || found.runs.len() >= wanted {
        return;
    }
    match serde_json::from_str::<Run>(text) {
        Ok(run) => {
            // An older line for a run already in hand is that run before it ended.
            if let Some(id) = &run.run_id {
                if !seen.insert(id.clone()) {
                    return;
                }
            }
            found.runs.push(run);
        }
        Err(error) if terminated => {
            found.unreadable += 1;
            // Where and what kind of failure, never the line: the app log leaves the
            // machine in a diagnose bundle, and the error's own text can quote a value.
            tracing::warn!(
                target: "runs",
                category = ?error.classify(),
                column = error.column(),
                "a finished line of the run log could not be read"
            );
        }
        // The last line, still being written or cut off mid-write. Not a record yet, and
        // not a fault of the file: see the note at the top.
        Err(_) => {}
    }
}

/* --- prudence diagnose ------------------------------------------------------------------
 *
 * The bundle an agent reads when something went wrong on a machine it cannot look at:
 * the last run records, `status --json`, the config with the user's name taken out, this
 * app's log tail and a line about the machine, in `<data dir>/diagnose/<timestamp>/`.
 *
 * Which folder the run made is read off the disk rather than out of what the command
 * printed: the folder that is there after the run and was not there before it is the
 * bundle, whatever the engine chose to say about it.
 */

/// The command line. A constant, like every other one the app runs: the page asks for a
/// diagnosis and never builds a command.
pub const DIAGNOSE: &[&str] = &["diagnose"];

/// Where the engine puts the bundles.
pub fn bundles_dir(data: &Path) -> PathBuf {
    data.join("diagnose")
}

/// The bundles there now. A directory that does not exist yet holds none.
pub fn bundles(directory: &Path) -> HashSet<PathBuf> {
    std::fs::read_dir(directory)
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .map(|entry| entry.path())
                .filter(|path| path.is_dir())
                .collect()
        })
        .unwrap_or_default()
}

/// The bundle a run made: the newest of the folders that were not there before it. The
/// names are timestamps, so the newest is the greatest.
pub fn made(before: &HashSet<PathBuf>, after: &HashSet<PathBuf>) -> Option<PathBuf> {
    after.difference(before).max().cloned()
}

/// How a diagnosis ended, for the Engine tab: the folder, or why there is none.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Diagnosis {
    pub path: Option<String>,
    /// One of `EngineError::kind()`'s words, or `noBundle` for an engine that exited well
    /// and left no new folder behind, which is an engine older than the command.
    pub error_kind: Option<String>,
    /// The engine's own words, as a run's failure carries them.
    pub error: Option<String>,
}

impl Diagnosis {
    pub fn failed(error: &crate::engine::EngineError) -> Self {
        // `Engine::read` has logged the failure with the engine's words already.
        Self {
            error_kind: Some(error.kind().to_string()),
            error: Some(error.detail()).filter(|text| !text.is_empty()),
            ..Self::default()
        }
    }

    pub fn found(bundle: Option<PathBuf>) -> Self {
        match bundle {
            Some(path) => {
                // The folder's own name, which is its timestamp; the whole path carries
                // the user's name and this line can leave the machine.
                tracing::info!(
                    target: "diagnose",
                    bundle = %path.file_name().unwrap_or_default().to_string_lossy(),
                    "diagnose bundle written"
                );
                Self {
                    path: Some(path.display().to_string()),
                    ..Self::default()
                }
            }
            None => {
                tracing::error!(target: "diagnose", "the engine finished and wrote no bundle");
                Self {
                    error_kind: Some("noBundle".into()),
                    ..Self::default()
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/runs.jsonl")
    }

    fn scratch(name: &str) -> PathBuf {
        let directory =
            std::env::temp_dir().join(format!("prudence-runlog-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&directory);
        std::fs::create_dir_all(&directory).expect("a scratch directory");
        directory
    }

    fn ids(runs: &Runs) -> Vec<&str> {
        runs.runs
            .iter()
            .map(|run| run.run_id.as_deref().unwrap_or("?"))
            .collect()
    }

    /// The fixture: a finished ingest with two warnings and a failed check, an ingest that
    /// never finished, a clean review, and half a line the engine was writing.
    #[test]
    fn the_last_runs_are_read_newest_first_and_the_half_written_line_is_not_one() {
        let runs = read(&fixture(), 10).expect("the fixture reads");
        assert_eq!(ids(&runs), ["r3", "r2", "r1"]);
        assert_eq!(
            runs.unreadable, 0,
            "a line still being written is not unreadable"
        );

        let interrupted = &runs.runs[1];
        assert_eq!(interrupted.ended_at, None);
        assert_eq!(interrupted.exit, None);

        let ingest = &runs.runs[2];
        assert_eq!(ingest.command, ["ingest", "--json", "--progress"]);
        assert_eq!(
            ingest
                .warnings
                .iter()
                .map(|warning| (warning.kind.as_str(), warning.count))
                .collect::<Vec<_>>(),
            [("unreadable_line", 2), ("unknown_record_type", 1)]
        );
        assert_eq!(
            ingest
                .checks
                .iter()
                .map(|check| check.ok)
                .collect::<Vec<_>>(),
            [Some(true), Some(false)]
        );
        assert_eq!(ingest.steps[1].counts["files_skipped"], 480);
    }

    #[test]
    fn asking_for_fewer_stops_early() {
        let runs = read(&fixture(), 2).expect("the fixture reads");
        assert_eq!(ids(&runs), ["r3", "r2"]);
    }

    /// An older engine writes no run log, and that is nothing to report.
    #[test]
    fn no_file_is_no_runs() {
        let runs = read(Path::new("/nonexistent/prudence/logs/runs.jsonl"), 10).unwrap();
        assert_eq!(runs, Runs::default());
    }

    /// Lines longer than a block, so the reader has to join blocks to find one line.
    #[test]
    fn a_line_longer_than_a_block_is_still_one_line() {
        let directory = scratch("long");
        let path = directory.join(FILE);
        let long = "x".repeat(BLOCK as usize * 2 + 17);
        let mut text = String::new();
        for id in ["a", "b", "c"] {
            text.push_str(&format!(
                "{{\"run_id\": \"{id}\", \"command\": [\"ingest\"], \"error\": {{\"type\": \"E\", \"message\": \"{long}\"}}}}\n"
            ));
        }
        std::fs::write(&path, text).unwrap();
        let runs = read(&path, 10).unwrap();
        assert_eq!(ids(&runs), ["c", "b", "a"]);
        assert_eq!(
            runs.runs[0].error.as_ref().unwrap().message.len(),
            long.len()
        );
        std::fs::remove_dir_all(&directory).ok();
    }

    /// However the engine completes a record, the newest line for a run is the run.
    #[test]
    fn a_run_completed_by_a_second_line_is_one_run_as_it_ended() {
        let directory = scratch("twice");
        let path = directory.join(FILE);
        std::fs::write(
            &path,
            "{\"run_id\": \"a\", \"command\": [\"ingest\"], \"ended_at\": null}\n\
             {\"run_id\": \"b\", \"command\": [\"review\"], \"ended_at\": null}\n\
             {\"run_id\": \"a\", \"command\": [\"ingest\"], \"ended_at\": \"2026-09-23T08:00:00+00:00\"}\n",
        )
        .unwrap();
        let runs = read(&path, 10).unwrap();
        assert_eq!(ids(&runs), ["a", "b"]);
        assert!(runs.runs[0].ended_at.is_some());
        std::fs::remove_dir_all(&directory).ok();
    }

    /// A finished line this build cannot read is counted, and the lines around it still
    /// read.
    #[test]
    fn a_finished_line_that_does_not_parse_is_counted_and_skipped() {
        let directory = scratch("broken");
        let path = directory.join(FILE);
        std::fs::write(
            &path,
            "{\"run_id\": \"a\"}\nnot json at all\n{\"run_id\": \"b\", \"command\": \"ingest\"}\n{\"run_id\": \"c\"}\n",
        )
        .unwrap();
        let runs = read(&path, 10).unwrap();
        assert_eq!(ids(&runs), ["c", "a"]);
        assert_eq!(
            runs.unreadable, 2,
            "the non-JSON line and the one of the wrong shape"
        );
        std::fs::remove_dir_all(&directory).ok();
    }

    /// A file of one line with no newline is the engine's first write, in progress.
    #[test]
    fn a_file_that_is_one_unfinished_line_holds_no_runs() {
        let directory = scratch("one");
        let path = directory.join(FILE);
        std::fs::write(&path, "{\"run_id\": \"a\", \"comm").unwrap();
        assert_eq!(read(&path, 10).unwrap(), Runs::default());
        std::fs::write(&path, "{\"run_id\": \"a\"}").unwrap();
        assert_eq!(
            ids(&read(&path, 10).unwrap()),
            ["a"],
            "a whole record is one"
        );
        std::fs::remove_dir_all(&directory).ok();
    }

    #[test]
    fn the_diagnosis_is_one_constant_command() {
        assert_eq!(DIAGNOSE, ["diagnose"]);
    }

    #[test]
    fn the_bundle_is_the_newest_folder_the_run_added() {
        let set = |names: &[&str]| -> HashSet<PathBuf> {
            names
                .iter()
                .map(|name| PathBuf::from("/d").join(name))
                .collect()
        };
        let before = set(&["20260922T100000"]);
        assert_eq!(made(&before, &before), None, "nothing new is no bundle");
        assert_eq!(
            made(&before, &set(&["20260922T100000", "20260923T090000"])),
            Some(PathBuf::from("/d/20260923T090000"))
        );
        assert_eq!(
            made(
                &HashSet::new(),
                &set(&["20260923T090001", "20260923T090000"])
            ),
            Some(PathBuf::from("/d/20260923T090001"))
        );
    }

    #[test]
    fn the_bundles_are_the_folders_in_the_diagnose_directory() {
        let directory = scratch("bundles");
        assert!(
            bundles(&bundles_dir(&directory)).is_empty(),
            "no directory is none"
        );
        let inside = bundles_dir(&directory);
        std::fs::create_dir_all(inside.join("20260923T090000")).unwrap();
        std::fs::write(inside.join("stray.txt"), "").unwrap();
        assert_eq!(
            bundles(&inside),
            HashSet::from([inside.join("20260923T090000")])
        );
        std::fs::remove_dir_all(&directory).ok();
    }
}
