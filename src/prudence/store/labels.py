"""The `label` table: the founder's own verdict on a sampled commit.

Everything else in `store/` is disposable: derived tables are rebuilt from the archive,
and commits and attribution are rebuilt from the repository, so a bad parser or a bad
matching rule costs nothing but a rebuild. A label is different. It is typed by a
person who remembers what they did, which nothing in the store can regenerate, so it
is never dropped or rebuilt: `rebuild` and `derived.build` do not name this table, and
they must not start to.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

FACT_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS label(
    commit_hash TEXT PRIMARY KEY,
    session_id TEXT,
    labelled_at TEXT NOT NULL,
    note TEXT,
    fact_version INTEGER NOT NULL
)
"""


@dataclass
class Label:
    """One verdict. `session_id` is NULL for "none of these" or "I don't know"."""

    commit_hash: str
    session_id: str | None
    labelled_at: str
    note: str | None
    fact_version: int


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(SCHEMA)


def write(
    connection: sqlite3.Connection,
    commit_hash: str,
    session_id: str | None,
    note: str | None = None,
    now: datetime | None = None,
) -> None:
    """Record the founder's verdict. Labelling a commit again replaces the earlier verdict."""
    ensure_schema(connection)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%S")
    connection.execute(
        "INSERT OR REPLACE INTO label VALUES (?, ?, ?, ?, ?)",
        (commit_hash, session_id, stamp, note, FACT_VERSION),
    )


def get(connection: sqlite3.Connection, commit_hash: str) -> Label | None:
    ensure_schema(connection)
    row = connection.execute("SELECT * FROM label WHERE commit_hash = ?", (commit_hash,)).fetchone()
    return _row(row) if row is not None else None


def labelled_hashes(connection: sqlite3.Connection) -> set[str]:
    ensure_schema(connection)
    return {row[0] for row in connection.execute("SELECT commit_hash FROM label")}


def all_labels(connection: sqlite3.Connection) -> list[Label]:
    ensure_schema(connection)
    return [_row(row) for row in connection.execute("SELECT * FROM label ORDER BY labelled_at")]


def _row(row: sqlite3.Row) -> Label:
    return Label(
        row["commit_hash"], row["session_id"], row["labelled_at"], row["note"], row["fact_version"]
    )
