"""The `question` table: what was asked, what it was answered from, and what was said.

An answer is kept for the same reason a review is: it is the user's own history of what
they were told, it was not built from the archive and `rebuild` could not produce it
again, so it lives outside the derived tables and travels in `export` and `import`
(`store/transfer.USER_TABLES`).

The evidence hash matters more than it looks. It is the digest of the rows the answer was
written from, so a year later a reader can tell whether two answers stood on the same
evidence, and whether an answer that looks wrong was written from evidence that has since
changed. The evidence itself is not stored: it is a view of rows that are still there.

No question text is transcript text. The question is what the user typed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

QUESTION_TABLE = "question"
TABLES = (QUESTION_TABLE,)

SCHEMA = """
CREATE TABLE IF NOT EXISTS question(
    id INTEGER PRIMARY KEY,
    asked_at TEXT NOT NULL,
    question TEXT NOT NULL,
    project TEXT,
    evidence_hash TEXT NOT NULL,
    model TEXT,
    answer TEXT,
    refused_numbers TEXT,
    language TEXT
);
CREATE INDEX IF NOT EXISTS question_asked ON question(asked_at DESC);
"""

# Columns added after the table shipped. A question row is the user's own history and
# `rebuild` could not produce it again, so it is grown rather than recreated, the same
# way `reviews/schema.py` grows the review table.
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (("language", "TEXT"),)


def ensure(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    present = {row["name"] for row in connection.execute(f'PRAGMA table_info("{QUESTION_TABLE}")')}
    for name, kind in ADDED_COLUMNS:
        if name not in present:
            connection.execute(f'ALTER TABLE "{QUESTION_TABLE}" ADD COLUMN {name} {kind}')


def evidence_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def insert(
    connection: sqlite3.Connection,
    *,
    asked_at: str,
    question: str,
    project: str | None,
    evidence_hash: str,
    model: str | None,
    answer: str | None,
    refused_numbers: str | None = None,
    language: str | None = None,
) -> int:
    ensure(connection)
    cursor = connection.execute(
        "INSERT INTO question (asked_at, question, project, evidence_hash, model, answer,"
        " refused_numbers, language) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (asked_at, question, project, evidence_hash, model, answer, refused_numbers, language),
    )
    return int(cursor.lastrowid or 0)


def by_id(connection: sqlite3.Connection, question_id: int) -> sqlite3.Row | None:
    try:
        return connection.execute("SELECT * FROM question WHERE id = ?", (question_id,)).fetchone()
    except sqlite3.OperationalError:
        return None


def recent(connection: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    try:
        return connection.execute(
            "SELECT * FROM question ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def render(row: sqlite3.Row) -> str:
    """One stored question and its answer, as `prudence show --question` prints it."""
    lines = [
        f"question {row['id']}",
        f"  asked     {row['asked_at']}",
        f"  question  {row['question']}",
        f"  project   {row['project'] or 'every project'}",
        f"  evidence  {row['evidence_hash']}",
        f"  model     {row['model'] or 'none (--no-model)'}",
        f"  language  {_column(row, 'language') or 'en'}",
        "",
    ]
    refused = _refused(row)
    if row["answer"]:
        lines.append(row["answer"])
    elif refused:
        # The words are not here because they were never written down: a text that
        # failed the guards is discarded, and only the reason it failed is kept.
        lines.append(f"No answer was stored. The model's draft was refused ({refused})")
        lines.append("and discarded; run the question again, or with --no-model.")
    else:
        lines.append("No answer was stored: the evidence was printed alone (--no-model).")
    lines.append("")
    lines.append(
        "The evidence itself is not stored with the answer; it is the rows "
        "`prudence sessions`, `prudence usage` and `prudence observations` still print."
    )
    return "\n".join(lines)


def _refused(row: sqlite3.Row) -> str | None:
    """The refusal note, or None. Absent on a row written before the column existed."""
    return _column(row, "refused_numbers")


def _column(row: sqlite3.Row, name: str) -> Any:
    """One column of a row that may predate it. Absent is None, never an exception."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
