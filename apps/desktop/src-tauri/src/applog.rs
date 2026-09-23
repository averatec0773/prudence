//! The app's own log: `<data dir>/logs/app.log`, beside the engine's `runs.jsonl`.
//!
//! ## Why a file and not only standard error
//!
//! The shell has always said what it did on standard error, and nobody reads the standard
//! error of a menu bar app launched from Finder. The founder cannot read logs either; an
//! agent can, and `prudence diagnose` bundles this file's tail for one. So the events an
//! agent needs to reconstruct a failure go to a file the engine's own data directory
//! already holds, and to standard error as before for whoever is running the app from a
//! terminal.
//!
//! ## What is logged, and what never is
//!
//! At info: the app starting, every engine invocation (its arguments, exit code and
//! seconds), every store announcement, every contract check, and every settings write.
//! At error: every failure, in the words already shown to the reader. **Never** what the
//! engine printed on success, never a transcript, and never the value of a setting that is
//! a path: the tail of this file leaves the machine in a diagnose bundle.
//!
//! ## One line per event
//!
//! `time level target message key=value`, which is `tracing-subscriber`'s own format
//! without colour. A field that could carry a newline (the engine's own words) is logged
//! with `?`, which quotes it and escapes the newline, so an event is always one line.
//!
//! ## Rotation
//!
//! By size: at [`LIMIT`] the file becomes `app.log.1`, the one before becomes `app.log.2`,
//! and [`KEEP`] old files are kept. The writer is ours because `tracing-appender` rotates
//! by the clock only, and a log that grows for a whole day of timed ingests is the wrong
//! shape for a bundle that carries its tail.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::fmt::MakeWriter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::Layer;

/// The file's name inside `<data dir>/logs`.
pub const FILE: &str = "app.log";

/// Rotate before a write would take the file past this.
pub const LIMIT: u64 = 4 * 1024 * 1024;

/// How many rotated files are kept beside the live one.
pub const KEEP: usize = 2;

/// A file that rotates by size, written one event at a time.
///
/// `tracing-subscriber` formats an event into a buffer and hands it over in one
/// `write_all`, and [`Line::write`] writes everything it is given before returning, so a
/// rotation can only ever fall between two events and never inside one.
pub struct Rotating {
    path: PathBuf,
    limit: u64,
    keep: usize,
    /// The open file and how long it is. `None` after a rotation that could not reopen
    /// the file, so the next event tries again rather than the log stopping for good.
    open: Mutex<Option<(File, u64)>>,
}

impl Rotating {
    pub fn new(path: PathBuf, limit: u64, keep: usize) -> io::Result<Self> {
        let opened = open(&path)?;
        Ok(Self {
            path,
            limit,
            keep,
            open: Mutex::new(Some(opened)),
        })
    }

    /// `app.log.1`, `app.log.2`: the name of the `index`th older file.
    fn rotated(&self, index: usize) -> PathBuf {
        let mut name = self.path.as_os_str().to_owned();
        name.push(format!(".{index}"));
        PathBuf::from(name)
    }

    fn write_event(&self, bytes: &[u8]) -> io::Result<()> {
        let mut held = self.open.lock().unwrap();
        let size = match held.as_ref() {
            Some((_, size)) => *size,
            None => {
                *held = Some(open(&self.path)?);
                held.as_ref().map(|(_, size)| *size).unwrap_or(0)
            }
        };
        // A file with nothing in it is written to whatever the event's size: an event
        // longer than the limit would otherwise rotate an empty file forever.
        if size > 0 && size + bytes.len() as u64 > self.limit {
            *held = None;
            self.rotate()?;
            *held = Some(open(&self.path)?);
        }
        let (file, size) = held.as_mut().expect("opened above");
        file.write_all(bytes)?;
        *size += bytes.len() as u64;
        Ok(())
    }

    /// Shift every kept file one along, dropping the oldest, and move the live one to `.1`.
    fn rotate(&self) -> io::Result<()> {
        if self.keep == 0 {
            return std::fs::remove_file(&self.path);
        }
        for index in (1..self.keep).rev() {
            let from = self.rotated(index);
            if from.exists() {
                std::fs::rename(&from, self.rotated(index + 1))?;
            }
        }
        std::fs::rename(&self.path, self.rotated(1))
    }
}

fn open(path: &Path) -> io::Result<(File, u64)> {
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    let size = file.metadata()?.len();
    Ok((file, size))
}

/// One event's worth of writing, as `tracing-subscriber` asks for it.
pub struct Line<'a>(&'a Rotating);

impl Write for Line<'_> {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        self.0.write_event(buf)?;
        Ok(buf.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

impl<'a> MakeWriter<'a> for Rotating {
    type Writer = Line<'a>;

    fn make_writer(&'a self) -> Self::Writer {
        Line(self)
    }
}

/// Start logging to `<logs>/app.log` and to standard error. Called once, first thing.
///
/// A log that cannot be opened is said on standard error and the app goes on without the
/// file: the reader has an app to use, and a missing log is not a reason to refuse them
/// it. The failure is never silent, which is the part that matters.
pub fn start(logs: &Path) {
    let file = std::fs::create_dir_all(logs)
        .and_then(|()| Rotating::new(logs.join(FILE), LIMIT, KEEP))
        .map_err(|error| eprintln!("[log] no app log in {}: {error}", logs.display()))
        .ok();
    let to_file = file.map(|writer| {
        tracing_subscriber::fmt::layer()
            .with_ansi(false)
            .with_writer(writer)
            .with_filter(LevelFilter::INFO)
    });
    let to_stderr = tracing_subscriber::fmt::layer()
        .with_ansi(false)
        .with_writer(io::stderr)
        .with_filter(LevelFilter::INFO);
    let subscriber = tracing_subscriber::registry().with(to_file).with(to_stderr);
    if let Err(error) = tracing::subscriber::set_global_default(subscriber) {
        eprintln!("[log] the app log could not be installed: {error}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let directory =
            std::env::temp_dir().join(format!("prudence-applog-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&directory);
        std::fs::create_dir_all(&directory).expect("a scratch directory");
        directory
    }

    fn size(path: &Path) -> u64 {
        std::fs::metadata(path).map(|meta| meta.len()).unwrap_or(0)
    }

    /// The task's own check: five megabytes through the writer at the real limit.
    #[test]
    fn five_megabytes_rotate_once_at_four_and_nothing_is_lost() {
        let directory = scratch("five");
        let path = directory.join(FILE);
        let writer = Rotating::new(path.clone(), LIMIT, KEEP).expect("the log opens");
        let event = [b'x'; 1023]
            .iter()
            .copied()
            .chain(std::iter::once(b'\n'))
            .collect::<Vec<u8>>();
        for _ in 0..(5 * 1024) {
            writer.make_writer().write_all(&event).expect("written");
        }
        let rotated = writer.rotated(1);
        assert!(rotated.exists(), "nothing was rotated at 4 MB");
        assert_eq!(
            size(&rotated),
            LIMIT,
            "the rotated file is not the 4 MB before it"
        );
        assert_eq!(
            size(&path),
            1024 * 1024,
            "the live file is not the last megabyte"
        );
        assert!(!writer.rotated(2).exists());
        std::fs::remove_dir_all(&directory).ok();
    }

    /// Two old files and no third, however many times it rotates.
    #[test]
    fn two_old_files_are_kept_and_the_oldest_goes() {
        let directory = scratch("keep");
        let path = directory.join(FILE);
        let writer = Rotating::new(path.clone(), 10, KEEP).expect("the log opens");
        for round in 0..5u8 {
            let event = vec![b'a' + round; 10];
            writer.make_writer().write_all(&event).expect("written");
        }
        assert_eq!(std::fs::read(&path).unwrap(), vec![b'e'; 10]);
        assert_eq!(std::fs::read(writer.rotated(1)).unwrap(), vec![b'd'; 10]);
        assert_eq!(std::fs::read(writer.rotated(2)).unwrap(), vec![b'c'; 10]);
        assert!(!writer.rotated(3).exists(), "a third old file was kept");
        std::fs::remove_dir_all(&directory).ok();
    }

    /// A rotation falls between events, never inside one: every line of every file is
    /// whole.
    #[test]
    fn an_event_is_never_split_across_two_files() {
        let directory = scratch("whole");
        let path = directory.join(FILE);
        let writer = Rotating::new(path.clone(), 100, KEEP).expect("the log opens");
        for index in 0..40 {
            let event = format!("event number {index:03} with some words\n");
            writer
                .make_writer()
                .write_all(event.as_bytes())
                .expect("written");
        }
        for file in [path.clone(), writer.rotated(1), writer.rotated(2)] {
            let text = std::fs::read_to_string(&file).unwrap();
            assert!(
                text.ends_with('\n'),
                "{} ends inside an event",
                file.display()
            );
            for line in text.lines() {
                assert!(line.starts_with("event number "), "a split line: {line}");
            }
        }
        std::fs::remove_dir_all(&directory).ok();
    }

    /// An app relaunched onto a log already near the limit counts what is there.
    #[test]
    fn a_reopened_log_counts_what_it_already_holds() {
        let directory = scratch("reopen");
        let path = directory.join(FILE);
        std::fs::write(&path, vec![b'o'; 90]).unwrap();
        let writer = Rotating::new(path.clone(), 100, KEEP).expect("the log opens");
        writer.make_writer().write_all(&[b'n'; 20]).unwrap();
        assert_eq!(size(&writer.rotated(1)), 90);
        assert_eq!(size(&path), 20);
        std::fs::remove_dir_all(&directory).ok();
    }

    /// The format a reader greps: time, level, target, message, then the fields, on one
    /// line even when a field carries the engine's multi-line words.
    #[test]
    fn an_event_is_one_line_of_time_level_target_message_and_fields() {
        let directory = scratch("format");
        let path = directory.join(FILE);
        let writer = Rotating::new(path.clone(), LIMIT, KEEP).expect("the log opens");
        let subscriber = tracing_subscriber::registry().with(
            tracing_subscriber::fmt::layer()
                .with_ansi(false)
                .with_writer(writer)
                .with_filter(LevelFilter::INFO),
        );
        tracing::subscriber::with_default(subscriber, || {
            tracing::info!(target: "engine", command = "ingest --json", exit = 0, "engine ran");
            tracing::error!(target: "engine", detail = ?"Traceback\nKeyError: 'x'", "run failed");
            tracing::debug!(target: "engine", "not at info, so not written");
        });
        let text = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 2, "{text}");
        let (time, rest) = lines[0].split_once(' ').expect("a time first");
        assert!(time.contains('T') && time.ends_with('Z'), "{}", lines[0]);
        assert_eq!(
            rest.trim_start(),
            "INFO engine: engine ran command=\"ingest --json\" exit=0"
        );
        assert!(lines[1].contains("ERROR engine: run failed detail=\"Traceback\\nKeyError: 'x'\""));
        std::fs::remove_dir_all(&directory).ok();
    }
}
