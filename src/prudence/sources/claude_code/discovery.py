"""Where Claude Code keeps its files, and what a scan needs to read from one.

A scan reads only the head and tail of each transcript (working directory, first and
last timestamp) plus file size. It never reads message content and never writes.

The transcript format is internal to Claude Code and changes between releases, so
everything here is lenient: missing or odd fields are skipped, never fatal.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from prudence.paths import claude_file_history_dir, claude_projects_dir, claude_settings_file
from prudence.sources.base import (
    FILE_HISTORY,
    SUBAGENT,
    TOOL_RESULT,
    CompanionFile,
    SessionFile,
)

DEFAULT_CLEANUP_PERIOD_DAYS = 30
HEAD_RECORDS = 40  # records to inspect at the start of a file for cwd and first timestamp
TAIL_BYTES = 64 * 1024  # bytes to read from the end of a file for the last timestamp

# Where the files beside a transcript live, relative to the session's own directory.
# `file-history` is the exception: Claude Code keeps it under its own root, one
# directory per session, rather than beside the transcript.
COMPANION_DIRS = (("subagents", SUBAGENT), ("tool-results", TOOL_RESULT))


def list_session_files(projects_dir: Path | None = None) -> list[Path]:
    """Top-level session transcripts; subagent transcripts (in subdirectories) are skipped."""
    root = projects_dir or claude_projects_dir()
    if not root.is_dir():
        return []
    files: list[Path] = []
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        files.extend(sorted(p for p in project_dir.glob("*.jsonl") if p.is_file()))
    return files


def read_session_file(path: Path) -> SessionFile:
    """Read the metadata a scan needs from one transcript, tolerating any format drift."""
    cwd: str | None = None
    first_at: datetime | None = None
    entrypoint: str | None = None
    git_branch: str | None = None
    with path.open("rb") as fh:
        for _ in range(HEAD_RECORDS):
            line = fh.readline()
            if not line:
                break
            record = _parse_line(line)
            if record is None:
                continue
            if cwd is None and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            if first_at is None:
                first_at = _timestamp(record)
            if entrypoint is None and isinstance(record.get("entrypoint"), str):
                entrypoint = record["entrypoint"]
            if git_branch is None and isinstance(record.get("gitBranch"), str):
                git_branch = record["gitBranch"]
            if cwd and first_at and entrypoint and git_branch:
                break
    last_at = _last_timestamp(path)
    return SessionFile(
        path=path,
        session_id=path.stem,
        cwd=cwd,
        first_at=first_at,
        last_at=last_at or first_at,
        size_bytes=path.stat().st_size,
        entrypoint=entrypoint,
        git_branch=git_branch,
    )


def companion_files(
    session: SessionFile, file_history_dir: Path | None = None
) -> list[CompanionFile]:
    """Subagent transcripts, spilled tool results and pre-edit snapshots of one session."""
    history_root = file_history_dir or claude_file_history_dir()
    session_dir = session.path.parent / session.session_id
    found = [
        CompanionFile(path, kind)
        for name, kind in COMPANION_DIRS
        for path in _files_in(session_dir / name)
    ]
    found += [
        CompanionFile(path, FILE_HISTORY) for path in _files_in(history_root / session.session_id)
    ]
    return found


def cleanup_period_days(settings_file: Path | None = None) -> int:
    """How many days Claude Code keeps transcripts before deleting them (default 30)."""
    path = settings_file or claude_settings_file()
    try:
        settings = json.loads(path.read_text())
    except (OSError, ValueError):
        return DEFAULT_CLEANUP_PERIOD_DAYS
    value = settings.get("cleanupPeriodDays") if isinstance(settings, dict) else None
    return value if isinstance(value, int) and value > 0 else DEFAULT_CLEANUP_PERIOD_DAYS


def _files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [path for path in sorted(directory.rglob("*")) if path.is_file()]


def _parse_line(line: bytes) -> dict | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _timestamp(record: dict) -> datetime | None:
    raw = record.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _last_timestamp(path: Path) -> datetime | None:
    """Timestamp of the last record that has one, read from the tail of the file."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - TAIL_BYTES), os.SEEK_SET)
        tail = fh.read()
    for line in reversed(tail.splitlines()):
        record = _parse_line(line)
        if record is None:
            continue
        stamp = _timestamp(record)
        if stamp is not None:
            return stamp
    return None
