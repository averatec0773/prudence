"""The two tables a review leaves behind, and the key/value markers a surface writes.

Both tables are created `IF NOT EXISTS` and nothing in the codebase drops them.
`prudence rebuild` throws away the derived tables and builds them again from the
archive; these rows were not built from the archive and could not be rebuilt from it,
so they are outside that promise, exactly as `store/labels.py` is. They travel in
`export` and come back in `import` (`store/transfer.py`).

`meta` is the small key/value table the surfaces share. It belongs to `store/meta.py`;
this module only writes the keys it owns (the first look's marker) through that module's
helpers. It used to carry its own `CREATE TABLE IF NOT EXISTS` for the same table, which
worked and was still a second definition of one schema; the duplicate is gone.

The `review` table grows columns rather than being rebuilt. A review row is the user's
own history of what they were told, so `rebuild` never drops it and there is nothing to
recreate a missing column from: `ensure` therefore adds a column when it is absent
(`_add_missing`), which is the one place in the codebase where a table is migrated, for
the one table that cannot be built again.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from prudence.store.meta import ensure_meta as _ensure_meta
from prudence.store.meta import get_meta, set_meta

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

# The model segment, stored beside the numbers it was allowed to use (rule 10). Added
# after the table shipped, so they are columns a `review` row may not have yet.
SEGMENT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("segment_text", "TEXT"),
    ("segment_prompt_version", "INTEGER"),
    ("segment_model", "TEXT"),
    ("segment_input_hash", "TEXT"),
    ("segment_numbers", "TEXT"),
    ("segment_created_at", "TEXT"),
)


def ensure(connection: sqlite3.Connection) -> None:
    """Create both tables if they are not there, and add any column they are missing."""
    connection.executescript(SCHEMA)
    _add_missing(connection, REVIEW_TABLE, SEGMENT_COLUMNS)


def _add_missing(
    connection: sqlite3.Connection, table: str, columns: tuple[tuple[str, str], ...]
) -> list[str]:
    """Add each column the table does not have. Returns the ones that were added.

    `PRAGMA table_info` first rather than catching the error from `ADD COLUMN`, because
    a caught error is indistinguishable from a real one and this runs inside a
    transaction the caller may still need.
    """
    present = {row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    added: list[str] = []
    for name, kind in columns:
        if name in present:
            continue
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN {name} {kind}')
        added.append(name)
    return added


def ensure_meta(connection: sqlite3.Connection) -> None:
    """Create the shared key/value table. One definition, in `store/meta.py`.

    Kept as a name here because the callers in this package read markers through this
    module; it is now a forward to the single DDL rather than a second copy of it.
    """
    _ensure_meta(connection)


def marker(connection: sqlite3.Connection, key: str) -> str | None:
    """One `meta` value, or None when the table or the key does not exist."""
    return get_meta(connection, key)


def set_marker(connection: sqlite3.Connection, key: str, value: str) -> None:
    set_meta(connection, key, value)


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


def store_segment(
    connection: sqlite3.Connection,
    review_id: int,
    *,
    text: str,
    prompt_version: int,
    model: str,
    input_hash: str,
    numbers: list[dict[str, Any]],
    created_at: str,
) -> None:
    """Attach a model-written segment to a review, with everything needed to judge it.

    The prompt version, the model id, the hash of what was sent and the list of numbers
    the model was given are stored with the text, so that a segment written months ago
    can still be checked against the figures it was allowed to use (rule 10).
    """
    ensure(connection)
    connection.execute(
        "UPDATE review SET segment_text = ?, segment_prompt_version = ?, segment_model = ?,"
        " segment_input_hash = ?, segment_numbers = ?, segment_created_at = ? WHERE id = ?",
        (
            text,
            prompt_version,
            model,
            input_hash,
            json.dumps(numbers, ensure_ascii=False),
            created_at,
            review_id,
        ),
    )


def segment_of(row: sqlite3.Row) -> dict[str, Any] | None:
    """The stored segment of one review row, or None when it has none.

    A row from a store written before the columns existed raises on the lookup rather
    than returning NULL, and a review without a segment is the normal case, so both are
    the same answer here: there is no segment.
    """
    try:
        text = row["segment_text"]
    except (IndexError, KeyError):
        return None
    if not text:
        return None
    try:
        numbers = json.loads(row["segment_numbers"] or "[]")
    except (TypeError, ValueError):
        numbers = []
    return {
        "text": text,
        "prompt_version": row["segment_prompt_version"],
        "model": row["segment_model"],
        "input_hash": row["segment_input_hash"],
        "numbers": numbers if isinstance(numbers, list) else [],
        "created_at": row["segment_created_at"],
    }


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
