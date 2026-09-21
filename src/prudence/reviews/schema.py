"""The two tables a review leaves behind, and the key/value markers a surface writes.

Both tables are created `IF NOT EXISTS` and nothing in the codebase drops them.
`prudence rebuild` throws away the derived tables and builds them again from the
archive; these rows were not built from the archive and could not be rebuilt from it,
so they are outside that promise, exactly as `store/labels.py` is. They travel in
`export` and come back in `import` (`store/transfer.py`).

`meta` is the small key/value table the surfaces share. Only the keys this package owns
are written here (the first look's marker); the DDL is `IF NOT EXISTS` so that whoever
creates the table first wins and the other side finds it already there.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

REVIEW_TABLE = "review"
SUGGESTION_TABLE = "suggestion"
TABLES = (REVIEW_TABLE, SUGGESTION_TABLE)

# A suggestion's life: it is made open, the user takes it or dismisses it, or the
# evidence it stood on stops existing and it expires on its own.
OPEN = "open"
TAKEN = "taken"
DISMISSED = "dismissed"
EXPIRED = "expired"
STATUSES = (OPEN, TAKEN, DISMISSED, EXPIRED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS review(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    range_start TEXT NOT NULL,
    range_end TEXT NOT NULL,
    project TEXT,
    outcome_range_start TEXT NOT NULL,
    outcome_range_end TEXT NOT NULL,
    sections TEXT NOT NULL,
    coverage REAL,
    fact_version INTEGER NOT NULL,
    parser_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS review_scope ON review(project, range_end);

CREATE TABLE IF NOT EXISTS suggestion(
    id INTEGER PRIMARY KEY,
    review_id INTEGER NOT NULL,
    observation_key TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS suggestion_status ON suggestion(status, observation_key);
"""

META_SCHEMA = "CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"


def ensure(connection: sqlite3.Connection) -> None:
    """Create both tables if they are not there. Never drops, never migrates."""
    connection.executescript(SCHEMA)


def ensure_meta(connection: sqlite3.Connection) -> None:
    """Create the shared key/value table if nobody has yet."""
    connection.execute(META_SCHEMA)


def marker(connection: sqlite3.Connection, key: str) -> str | None:
    """One `meta` value, or None when the table or the key does not exist."""
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["value"] if row is not None else None


def set_marker(connection: sqlite3.Connection, key: str, value: str) -> None:
    ensure_meta(connection)
    connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def now_text(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%S")


def observation_key(row: Any) -> str:
    """The identity of one observation across reviews: project, behaviour, outcome.

    It lives here rather than with the sections because both the builder and the
    suggestion rows key on it, and a shared key belongs with the table it is stored in.
    """
    return f"{row['repo_key']}|{row['fact']}|{row['outcome']}"


# --- reviews ---------------------------------------------------------------------------


def insert_review(
    connection: sqlite3.Connection,
    *,
    created_at: str,
    range_start: str,
    range_end: str,
    project: str | None,
    outcome_range_start: str,
    outcome_range_end: str,
    sections: dict[str, Any],
    coverage: float | None,
    fact_version: int,
    parser_version: int,
) -> int:
    """Store one review and hand back its id."""
    ensure(connection)
    cursor = connection.execute(
        "INSERT INTO review (created_at, range_start, range_end, project,"
        " outcome_range_start, outcome_range_end, sections, coverage, fact_version,"
        " parser_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            created_at,
            range_start,
            range_end,
            project,
            outcome_range_start,
            outcome_range_end,
            json.dumps(sections, ensure_ascii=False),
            coverage,
            fact_version,
            parser_version,
        ),
    )
    return int(cursor.lastrowid or 0)


def last_review(connection: sqlite3.Connection, project: str | None) -> sqlite3.Row | None:
    """The newest review with exactly this project scope, or None.

    Scope is matched, not overlapped: a review of everything is not the previous review
    of one project, because its range says nothing about what that project did.
    """
    try:
        if project is None:
            return connection.execute(
                "SELECT * FROM review WHERE project IS NULL ORDER BY range_end DESC, id DESC"
                " LIMIT 1"
            ).fetchone()
        return connection.execute(
            "SELECT * FROM review WHERE project = ? ORDER BY range_end DESC, id DESC LIMIT 1",
            (project,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None


def review_by_id(connection: sqlite3.Connection, review_id: int) -> sqlite3.Row | None:
    try:
        return connection.execute("SELECT * FROM review WHERE id = ?", (review_id,)).fetchone()
    except sqlite3.OperationalError:
        return None


def reviews(connection: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    try:
        return connection.execute(
            "SELECT * FROM review ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def sections_of(row: sqlite3.Row) -> dict[str, Any]:
    """The stored JSON, or an empty payload when it cannot be read.

    An unreadable payload is not fatal (architecture rule 3): the row still says which
    range it covered, and a surface prints that rather than failing.
    """
    try:
        payload = json.loads(row["sections"])
    except (TypeError, ValueError):
        return {"review_version": None, "sections": [], "numbers": []}
    if not isinstance(payload, dict):
        return {"review_version": None, "sections": [], "numbers": []}
    return payload


# --- suggestions -----------------------------------------------------------------------


def insert_suggestion(
    connection: sqlite3.Connection,
    *,
    review_id: int,
    observation_key: str,
    text: str,
    created_at: str,
) -> int:
    ensure(connection)
    cursor = connection.execute(
        "INSERT INTO suggestion (review_id, observation_key, text, status, created_at,"
        " resolved_at) VALUES (?, ?, ?, ?, ?, NULL)",
        (review_id, observation_key, text, OPEN, created_at),
    )
    return int(cursor.lastrowid or 0)


def open_suggestions(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    try:
        return connection.execute(
            "SELECT * FROM suggestion WHERE status = ? ORDER BY id", (OPEN,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def all_suggestions(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    try:
        return connection.execute("SELECT * FROM suggestion ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        return []


def suggestion_by_id(connection: sqlite3.Connection, suggestion_id: int) -> sqlite3.Row | None:
    try:
        return connection.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None


def set_status(
    connection: sqlite3.Connection, suggestion_id: int, status: str, resolved_at: str
) -> None:
    """Move one suggestion along its lifecycle. `open` clears the resolution date."""
    if status not in STATUSES:
        raise ValueError(f"{status!r} is not one of {', '.join(STATUSES)}")
    connection.execute(
        "UPDATE suggestion SET status = ?, resolved_at = ? WHERE id = ?",
        (status, None if status == OPEN else resolved_at, suggestion_id),
    )
