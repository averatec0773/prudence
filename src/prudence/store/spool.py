"""The spool: what the hooks saw, folded into a derived table.

The hooks write one JSON line each into `spool.jsonl` and never read it again. Ingest
treats that file exactly like a transcript: the bytes go into the archive unmodified
and are read back from there, incrementally by offset, so the spool is never truncated
and a `hook_event` row can always be rebuilt from bytes rather than trusted. Rule 1
applies to Prudence's own output as much as to Claude Code's.

Two things follow from that. The primary key is the SHA-256 of the line, so a line
archived twice (a rewritten generation, a copied data directory) produces one row, and
a line the hook wrote while the tree was being read produces a row on the next run
instead of a gap. And a line this version does not understand is counted, not fatal:
the hook and the parser are shipped together today, but a user upgrades one at a time.

What the hooks add that the transcript never has is git state: HEAD and branch at the
instant of each event, and a fingerprint plus a count of `git status --porcelain`. No
file name and no message text ever reaches this table.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass

from prudence.store import archive
from prudence.store.repos import Resolver

FACT_VERSION = 1

TABLE = "hook_event"

SCHEMA = """
CREATE TABLE IF NOT EXISTS {name}(
    event_id TEXT PRIMARY KEY,
    event TEXT,
    ts TEXT,
    session_id TEXT,
    prompt_id TEXT,
    tool_use_id TEXT,
    cwd TEXT,
    repo_key TEXT,
    head TEXT,
    branch TEXT,
    dirty_fingerprint TEXT,
    dirty_count INTEGER,
    elapsed_ms INTEGER,
    parser_version INTEGER NOT NULL
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS hook_event_session ON hook_event(session_id, ts)",
    "CREATE INDEX IF NOT EXISTS hook_event_prompt ON hook_event(prompt_id)",
)

FIELDS = (
    "event",
    "ts",
    "session_id",
    "prompt_id",
    "tool_use_id",
    "cwd",
    "head",
    "branch",
    "dirty_fingerprint",
    "dirty_count",
    "elapsed_ms",
)


@dataclass
class SpoolStats:
    files: int = 0
    events: int = 0
    duplicates: int = 0
    unreadable: int = 0
    elapsed: float = 0.0


def build(connection: sqlite3.Connection, resolver: Resolver | None = None) -> SpoolStats:
    """Rebuild `hook_event` from every archived spool file. Idempotent."""
    started = time.monotonic()
    stats = SpoolStats()
    connection.execute(f"DROP TABLE IF EXISTS {TABLE}__new")
    connection.execute(SCHEMA.format(name=f"{TABLE}__new"))

    rows: list[tuple] = []
    seen: set[str] = set()
    for row in connection.execute(
        "SELECT path FROM archive_file WHERE source = 'spool' ORDER BY path"
    ):
        stats.files += 1
        for _, line in archive.iter_lines(connection, row["path"]):
            if not line.strip():
                continue
            event_id = hashlib.sha256(line).hexdigest()
            if event_id in seen:
                stats.duplicates += 1
                continue
            parsed = _parse(line)
            if parsed is None:
                stats.unreadable += 1
                continue
            seen.add(event_id)
            cwd = parsed.get("cwd")
            repo_key = resolver.resolve(cwd).repo_key if resolver and cwd else None
            rows.append(
                (
                    event_id,
                    *(parsed.get(field) for field in FIELDS),
                    repo_key,
                    FACT_VERSION,
                )
            )
    connection.executemany(
        f"INSERT OR IGNORE INTO {TABLE}__new(event_id, {', '.join(FIELDS)}, repo_key,"
        f" parser_version) VALUES ({', '.join('?' * (len(FIELDS) + 3))})",
        rows,
    )
    stats.events = len(rows)
    _swap(connection)
    stats.elapsed = time.monotonic() - started
    return stats


def counts(connection: sqlite3.Connection) -> tuple[int, int]:
    """Hook events recorded, and how many sessions they cover."""
    try:
        row = connection.execute(
            f"SELECT COUNT(*) AS events, COUNT(DISTINCT session_id) AS sessions FROM {TABLE}"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0, 0
    return row["events"], row["sessions"]


def _swap(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(f"DROP TABLE IF EXISTS {TABLE}")
        connection.execute(f"ALTER TABLE {TABLE}__new RENAME TO {TABLE}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    for statement in INDEXES:
        connection.execute(statement)


def _parse(line: bytes) -> dict | None:
    """One spool line, or None when the hook wrote something this version cannot read."""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict) or not record.get("event"):
        return None
    return record
