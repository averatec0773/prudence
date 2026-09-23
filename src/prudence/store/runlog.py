"""The run log: what every command that changes something did, kept for later reading.

`<data dir>/logs/runs.jsonl` holds one JSON object per line. A command writes a line when
it starts, with `ended_at` null, and a second line with the same `run_id` when it ends,
complete. A reader folds the two (`read`), so a run whose second line never came, because
the process was killed or the machine slept for good, is a record with `ended_at` null:
interrupted, or still running if its process is (`state`). The first line is appended
rather than rewritten in place because several processes write this file (an ingest
started by the app, a review from a terminal, the app's own install step), and a rewrite
is a read, an edit and a replace: a line another process appended in between would be
lost. An append of one line is one `write` on a file opened with `O_APPEND`, which the
operating system positions at the end atomically, so two runs never overwrite each other.

The file is renamed to `runs.1.jsonl` when it has reached `ROTATE_BYTES`, replacing the
one before, so two files are kept; a run is rotated only when it starts, and a reader
reads both, so a run whose start line was rotated away from its end line is still one
record.

What a record holds (`start`, `finish`): the command and its arguments, the times, the
process id, the engine's versions (engine, parser, bucket rule, app contract), the
machine (operating system, architecture, Python, cores), the size of the store, then per
step its seconds and counts, the warnings (`store/run_warnings.py`), the self-checks
(`store/checks.py`), the error with its type, message and traceback when there was one,
and the exit code. No text read from a transcript is ever in it: counts, ids, names,
keys, offsets and timings only, and every string is written with the home directory
replaced by `~` (`strip_user`), so a record can be handed to someone else as it is. The
one free-form string is an error's message, which is written by Prudence or a library
and is cut at `MESSAGE_LIMIT`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import platform
import time
import traceback
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from prudence import __version__
from prudence.paths import database_file, runs_log_file
from prudence.store import buckets, derived, meta
from prudence.store.run_warnings import name

ROTATE_BYTES = 8 * 1024 * 1024
MESSAGE_LIMIT = 500

# String fields of a step's statistics worth keeping: the engine's own words for how the
# parse went about it. Every other string a step's statistics may hold is left out.
_WORD_FIELDS = frozenset({"mode", "full_reason"})

# A run's states, as `prudence logs` shows them.
FINISHED = "finished"
FAILED = "failed"
RUNNING = "running"
INTERRUPTED = "interrupted"


class Pipeline(Protocol):
    """What the log reads off a `pipeline.Result`, named here so the log imports no step."""

    steps: dict[str, float]
    failed_step: str | None
    checks: list
    warnings: Any

    def step_counts(self) -> dict[str, object]: ...


class Run:
    """One command's record while it runs: its steps are added as the command learns them."""

    def __init__(self, record: dict, started: float) -> None:
        self.record = record
        self._started = started
        self._steps: list[dict] = []
        self._pipeline: Pipeline | None = None

    @property
    def run_id(self) -> str:
        return self.record["run_id"]

    def attach(self, result: Pipeline) -> None:
        """Take the steps, warnings and checks from a pipeline run, when it ends or fails."""
        self._pipeline = result

    def step(self, step_name: str, seconds: float, counts: Mapping | None = None) -> None:
        """One step of a command that is not the pipeline, with the counts it reports."""
        self._steps.append(
            {"name": step_name, "seconds": round(seconds, 3), "counts": _counts(counts or {})}
        )

    def _collect(self) -> None:
        steps = list(self._steps)
        warnings: list[dict] = []
        checks: list[dict] = []
        pipeline = self._pipeline
        if pipeline is not None:
            counted = pipeline.step_counts()
            for step_name, seconds in pipeline.steps.items():
                steps.append(
                    {
                        "name": step_name,
                        "seconds": seconds,
                        "counts": _counts(counted.get(step_name)),
                    }
                )
            if pipeline.failed_step is not None:
                steps.append(
                    {"name": pipeline.failed_step, "seconds": None, "counts": {}, "failed": True}
                )
            warnings = pipeline.warnings.as_list()
            checks = [check.as_dict() for check in pipeline.checks]
        self.record["steps"] = steps
        self.record["warnings"] = warnings
        self.record["checks"] = checks


def start(command: list[str]) -> Run:
    """Write a run's first line, rotating the log first when it has grown too large."""
    record = {
        "run_id": uuid.uuid4().hex,
        "command": command,
        "started_at": _now(),
        "ended_at": None,
        "seconds": None,
        "pid": os.getpid(),
        "engine_version": __version__,
        "parser_version": derived.PARSER_VERSION,
        "bucket_rule_version": buckets.BUCKET_RULE_VERSION,
        "app_contract_version": meta.APP_CONTRACT_VERSION,
        "machine": machine(),
        "store_bytes": store_bytes(),
        "steps": [],
        "warnings": [],
        "checks": [],
        "error": None,
        "exit": None,
    }
    path = runs_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= ROTATE_BYTES:
        os.replace(path, rotated_file(path))
    _append(path, record)
    return Run(record, time.monotonic())


def finish(run: Run, exit_code: int, error: BaseException | None = None) -> dict:
    """Write a run's second line: everything the first had, completed. Returns the record."""
    run._collect()
    record = run.record
    record["ended_at"] = _now()
    record["seconds"] = round(time.monotonic() - run._started, 3)
    record["store_bytes"] = store_bytes()
    record["error"] = describe(error) if error is not None else None
    record["exit"] = exit_code
    _append(runs_log_file(), record)
    return record


def read() -> tuple[list[dict], int]:
    """Every run in the log, newest first, and how many lines could not be read.

    The rotated file is read first, so a run's end line wins over its start line wherever
    each of them is.
    """
    records: dict[str, dict] = {}
    unreadable = 0
    current = runs_log_file()
    for path in (rotated_file(current), current):
        if not path.exists():
            continue
        with path.open("rb") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    unreadable += 1
                    continue
                if not isinstance(record, dict) or not isinstance(record.get("run_id"), str):
                    unreadable += 1
                    continue
                records[record["run_id"]] = record
    ordered = sorted(records.values(), key=lambda record: record.get("started_at") or "")
    return ordered[::-1], unreadable


def state(record: dict) -> str:
    """Finished, failed, running, or interrupted: a run with no end whose process is gone."""
    if record.get("ended_at") is None:
        return RUNNING if _alive(record.get("pid")) else INTERRUPTED
    return FINISHED if record.get("exit") == 0 else FAILED


def rotated_file(path: Path) -> Path:
    return path.with_name(f"{path.stem}.1{path.suffix}")


def machine() -> dict:
    """The machine a run ran on, without anything that names it or its owner."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cores": os.cpu_count(),
    }


def store_bytes() -> int:
    """The store's size on disk, with its write-ahead log."""
    database = database_file()
    return sum(path.stat().st_size for path in (database, Path(f"{database}-wal")) if path.exists())


def describe(error: BaseException) -> dict:
    """An error's type, message and where it was raised, as file, line and function."""
    frames = [
        f"{_source(frame.filename)}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(error.__traceback__)
    ]
    described = {
        "type": type(error).__name__,
        "message": str(error)[:MESSAGE_LIMIT],
        "traceback": frames,
    }
    cause = error.__cause__ or error.__context__
    if cause is not None:
        described["cause"] = {"type": type(cause).__name__, "message": str(cause)[:MESSAGE_LIMIT]}
    return described


def strip_user(value: Any) -> Any:
    """Every string in `value` with the home directory written as `~`."""
    homes = sorted({str(Path.home()), os.path.realpath(Path.home())}, key=len, reverse=True)
    return _strip(value, homes)


def _strip(value: Any, homes: list[str]) -> Any:
    if isinstance(value, str):
        for home in homes:
            value = value.replace(home, "~")
        return value
    if isinstance(value, Mapping):
        return {key: _strip(item, homes) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_strip(item, homes) for item in value]
    return value


def _append(path: Path, record: dict) -> None:
    """One line, in one write, at the end of the file whoever else is writing to it."""
    line = json.dumps(strip_user(record), ensure_ascii=False, default=str) + "\n"
    handle = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(handle, line.encode("utf-8"))
    finally:
        os.close(handle)


def _counts(stats: object) -> dict:
    """A step's statistics as counts: numbers, and mappings of names to numbers."""
    if stats is None:
        return {}
    if dataclasses.is_dataclass(stats) and not isinstance(stats, type):
        items = {item.name: getattr(stats, item.name) for item in dataclasses.fields(stats)}
    elif isinstance(stats, Mapping):
        items = dict(stats)
    else:
        return {}
    kept: dict[str, object] = {}
    for key, value in items.items():
        if isinstance(value, bool | int | float):
            kept[key] = value
        elif isinstance(value, str) and key in _WORD_FIELDS:
            kept[key] = value
        elif isinstance(value, Mapping) and all(
            isinstance(item, int | float) for item in value.values()
        ):
            kept[key] = {name(str(sub)): item for sub, item in value.items()}
    return kept


def _source(filename: str) -> str:
    """A traceback's file as a path inside its package, never a path on this machine."""
    parts = Path(filename).parts
    for anchor in ("prudence", "site-packages"):
        if anchor in parts:
            index = len(parts) - 1 - parts[::-1].index(anchor)
            return "/".join(parts[index + (anchor == "site-packages") :])
    return Path(filename).name


def _alive(pid: object) -> bool:
    """Whether a process with this id is running on this machine now."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
