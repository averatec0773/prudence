"""Every behaviour fact and label Prudence computes, in one explicit list. No entry points.

`build` is the pipeline's last step (`store/pipeline.py`): it runs after every derived
table, `commit` and `attribution` exist, because several facts read across them, and it
follows the same swap pattern every other derived table uses (rule 1: a fact's own
table is rebuilt, never migrated). A fact that returns `None` for a session leaves no
row, exactly like `usage` leaves no row for a session with none: absence is the honest
answer, not a fabricated zero.

Two tables, because the two kinds of answer are not the same kind of thing.
`session_fact.value` is REAL and everything that reads it does arithmetic on it;
`session_label` holds a word and the version of the rule that chose it, and nothing
sums a word. Keeping them apart is what lets `prudence facts` stay a numeric table and
`prudence usage` group by a label without either having to filter the other's rows out.

Adding a fact means one new module beside these, and one line in `FACTS` below
(ARCHITECTURE.md: "A new derived fact computed from those tables: one function in
`facts/` with a version and its test cases as data"); adding a label is the same with
`LABELS`.
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
    purpose,
    repeated_errors,
    sittings,
    subagent_used,
    test_runs,
    tests_before_commit,
)
from prudence.facts.base import Fact, Label

TABLE = "session_fact"
LABEL_TABLE = "session_label"

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

LABEL_SCHEMA = """
CREATE TABLE {name}(
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    rule_version INTEGER NOT NULL,
    PRIMARY KEY(session_id, name)
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS session_fact_fact ON session_fact(fact)",
    "CREATE INDEX IF NOT EXISTS session_label_name ON session_label(name, label)",
)

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

# Classifications, in the same explicit form. One so far.
LABELS: tuple[Label, ...] = (purpose.LABEL,)


@dataclass
class BuildStats:
    sessions: int = 0
    rows: int = 0
    labels: int = 0
    elapsed: float = 0.0


def build(connection: sqlite3.Connection) -> BuildStats:
    """Rebuild `session_fact` and `session_label` for every session the store has.

    Idempotent, and deliberately so: the same store at the same versions produces the
    same rows, which is what makes `prudence rebuild` a safe thing to run at any time.
    """
    started = time.monotonic()
    stats = BuildStats()
    connection.execute(f"DROP TABLE IF EXISTS {TABLE}__new")
    connection.execute(SCHEMA.format(name=f"{TABLE}__new"))
    connection.execute(f"DROP TABLE IF EXISTS {LABEL_TABLE}__new")
    connection.execute(LABEL_SCHEMA.format(name=f"{LABEL_TABLE}__new"))

    session_ids = [row[0] for row in connection.execute("SELECT session_id FROM session")]
    stats.sessions = len(session_ids)
    rows: list[tuple] = []
    labels: list[tuple] = []
    for session_id in session_ids:
        for fact in FACTS:
            value = fact.compute(connection, session_id)
            if value is None:
                continue
            rows.append((session_id, fact.name, float(value), fact.trust, fact.version))
        for label in LABELS:
            chosen = label.compute(connection, session_id)
            if chosen is None:
                continue
            if chosen not in label.values:
                raise ValueError(f"{label.name}: {chosen!r} is not one of {label.values}")
            labels.append((session_id, label.name, chosen, label.version))
    connection.executemany(f"INSERT INTO {TABLE}__new VALUES (?, ?, ?, ?, ?)", rows)
    connection.executemany(f"INSERT INTO {LABEL_TABLE}__new VALUES (?, ?, ?, ?)", labels)
    stats.rows = len(rows)
    stats.labels = len(labels)

    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in (TABLE, LABEL_TABLE):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    for statement in INDEXES:
        connection.execute(statement)
    stats.elapsed = time.monotonic() - started
    return stats
