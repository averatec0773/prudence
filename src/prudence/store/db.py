"""The one SQLite file: how it is opened, protected and migrated.

Only the archive tables are migrated. Derived tables are never migrated because they
are never precious: changing how they are built is a rebuild from the archive, which
is the point of rule 1. `PRAGMA user_version` therefore tracks the archive schema
alone, and `store.derived` creates and swaps its own tables.

The file is created at mode 0600 before SQLite ever sees it: the archive holds the
user's unmodified transcripts, which contain secrets by design.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from prudence.paths import database_file, lock_file

ARCHIVE_SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 5000
FILE_MODE = 0o600

ARCHIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_file(
    path TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    session_id TEXT,
    repo_key TEXT,
    size INTEGER NOT NULL,
    mtime REAL,
    sha256 TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0,
    agent_kind TEXT NOT NULL DEFAULT 'claude_code'
);
CREATE INDEX IF NOT EXISTS archive_file_repo ON archive_file(repo_key, source);
CREATE INDEX IF NOT EXISTS archive_file_session ON archive_file(session_id);

CREATE TABLE IF NOT EXISTS collection_source(
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    home TEXT NOT NULL,
    enabled INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_origin(
    path TEXT NOT NULL REFERENCES archive_file(path) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    PRIMARY KEY(path, source_id)
);
CREATE TABLE IF NOT EXISTS archive_chunk(
    path TEXT NOT NULL,
    "offset" INTEGER NOT NULL,
    length INTEGER NOT NULL,
    compression TEXT NOT NULL,
    data BLOB NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0,
    superseded INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(path, generation, "offset")
);
"""


class Locked(RuntimeError):
    """Another ingest holds the lock."""


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database, creating it private, in WAL mode, with the archive schema."""
    target = path or database_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        os.close(os.open(target, os.O_CREAT | os.O_RDWR, FILE_MODE))
    connection = sqlite3.connect(target, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    migrate(connection)
    _protect(target)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Bring the archive tables up to date. Derived tables are rebuilt, never migrated."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version >= ARCHIVE_SCHEMA_VERSION:
        return
    connection.executescript(ARCHIVE_SCHEMA)
    columns = {r[1] for r in connection.execute("PRAGMA table_info(archive_file)")}
    if "agent_kind" not in columns:
        connection.execute(
            "ALTER TABLE archive_file ADD COLUMN agent_kind TEXT NOT NULL DEFAULT 'claude_code'"
        )
    connection.execute(
        "INSERT OR IGNORE INTO archive_origin SELECT path, 'claude' FROM archive_file"
        " WHERE agent_kind = 'claude_code' AND source != 'spool'"
    )
    connection.execute(f"PRAGMA user_version={ARCHIVE_SCHEMA_VERSION}")


@contextmanager
def ingest_lock(path: Path | None = None) -> Iterator[Path]:
    """Hold the advisory lock, or raise `Locked` at once if another ingest has it."""
    target = path or lock_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(target, os.O_CREAT | os.O_RDWR, FILE_MODE)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(handle)
        raise Locked(f"another prudence ingest is running (lock: {target})") from error
    try:
        yield target
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _protect(target: Path) -> None:
    """Keep the database and its write-ahead files readable by the owner alone."""
    for candidate in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
        try:
            candidate.chmod(FILE_MODE)
        except OSError:
            pass
