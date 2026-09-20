"""Every behaviour fact Prudence computes, in one explicit list. No entry points.

`build` is the pipeline's last step (`store/pipeline.py`): it runs after every derived
table, `commit` and `attribution` exist, because several facts read across them, and it
follows the same swap pattern every other derived table uses (rule 1: a fact's own
table is rebuilt, never migrated). A fact that returns `None` for a session leaves no
row, exactly like `usage` leaves no row for a session with none: absence is the honest
answer, not a fabricated zero.

Adding a fact means one new module beside these, and one line in `FACTS` below
(ARCHITECTURE.md: "A new derived fact computed from those tables: one function in
`facts/` with a version and its test cases as data").
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from prudence.facts import (
    commit_attempts_per_commit,
    compactions,
    context_resets,
    files_edited_unread,
    formatter_runs,
    prompts_per_active_hour,
    repeated_errors,
    sittings,
    subagent_used,
    test_runs,
    tests_before_commit,
)
from prudence.facts.base import Fact

TABLE = "session_fact"

SCHEMA = """
CREATE TABLE {name}(
    session_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    value REAL,
    trust TEXT NOT NULL,
    fact_version INTEGER NOT NULL,
    PRIMARY KEY(session_id, fact)
)
"""

INDEXES = ("CREATE INDEX IF NOT EXISTS session_fact_fact ON session_fact(fact)",)

# The order here is the order `prudence facts` prints its columns in.
FACTS: tuple[Fact, ...] = (
    sittings.FACT,
    files_edited_unread.FACT,
    formatter_runs.FACT,
    test_runs.FACT,
    tests_before_commit.FACT,
    commit_attempts_per_commit.FACT,
    repeated_errors.FACT,
    subagent_used.FACT,
    compactions.FACT,
    context_resets.FACT,
    prompts_per_active_hour.FACT,
)


@dataclass
class BuildStats:
    sessions: int = 0
    rows: int = 0
    elapsed: float = 0.0


def build(connection: sqlite3.Connection) -> BuildStats:
    """Rebuild `session_fact` for every session the store has. Idempotent."""
    started = time.monotonic()
    stats = BuildStats()
    connection.execute(f"DROP TABLE IF EXISTS {TABLE}__new")
    connection.execute(SCHEMA.format(name=f"{TABLE}__new"))

    session_ids = [row[0] for row in connection.execute("SELECT session_id FROM session")]
    stats.sessions = len(session_ids)
    rows: list[tuple] = []
    for session_id in session_ids:
        for fact in FACTS:
            value = fact.compute(connection, session_id)
            if value is None:
                continue
            rows.append((session_id, fact.name, float(value), fact.trust, fact.version))
    connection.executemany(f"INSERT INTO {TABLE}__new VALUES (?, ?, ?, ?, ?)", rows)
    stats.rows = len(rows)

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
    stats.elapsed = time.monotonic() - started
    return stats
