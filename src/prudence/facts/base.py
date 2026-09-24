"""The fact interface: a versioned function over the derived tables, with its own tests.

A fact reads `record`, `turn`, `tool_call`, `command`, `edit`, `attribution` and
`session`, never the archive and never message text, and returns one number for one
session, or `None` when the fact does not apply to it (a session at `metadata-only`
capture, or one with no commits to attempt). An absent measurement is left out of
`session_fact` rather than stored as a fabricated zero, matching how `usage` and every
other derived table already treat a missing capability.

`Fact` is a plain dataclass, so a new fact is one module plus one line in
`facts/registry.py` (rule of three in ARCHITECTURE.md: the interface is extracted now
because more than three facts exist). Each fact module also carries its own `CASES`: a
short table of synthetic session shapes (rows to insert per table) and the value the
fact should produce for them. `tests/test_facts.py` runs every case for every fact
through one parametrised test, so a fact's tests live beside its logic instead of in a
separate suite that can drift from it.

`Label` is the same shape for a fact that is a word rather than a number, such as a
session's purpose. It is separate from `Fact` because the two are stored separately:
`session_fact.value` is REAL and every surface that reads it does arithmetic on it,
while a label goes to `session_label` with the version of the rule that produced it.
A label is never averaged, summed or compared, and no finding rests on one alone
(M2 plan, design-for-change rule 7: a purpose is a label, not a number).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

TRUST_LEVELS = ("high", "medium", "low")

ComputeFn = Callable[[sqlite3.Connection, str], "int | float | None"]
LabelFn = Callable[[sqlite3.Connection, str], "str | None"]


def observes_file_reads(connection: sqlite3.Connection, session_id: str) -> bool:
    """Whether this source supplies reliable file paths for read operations."""
    row = connection.execute(
        "SELECT source FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row is not None and row[0] in (None, "claude_code")


@dataclass(frozen=True)
class Case:
    """One synthetic session: rows to insert per derived table, and the expected value.

    `rows` maps a table name to a list of column-keyed dicts. `parser_version` and
    `fact_version` are filled in automatically when a row omits them, since every
    derived table requires one and no fact's logic depends on their value. `expected`
    is a number for a `Fact` and one of the allowed words for a `Label`.
    """

    name: str
    session_id: str
    expected: int | float | str | None
    rows: dict[str, list[dict[str, object]]] = field(default_factory=dict)


@dataclass(frozen=True)
class Fact:
    """One behaviour fact: a name, a version, a trust level, how to compute it, and its
    own test cases."""

    name: str
    version: int
    trust: str
    compute: ComputeFn
    cases: tuple[Case, ...] = ()

    def __post_init__(self) -> None:
        if self.trust not in TRUST_LEVELS:
            raise ValueError(
                f"{self.name}: trust must be one of {TRUST_LEVELS}, got {self.trust!r}"
            )


@dataclass(frozen=True)
class Label:
    """One classification: a name, the version of the rule, the words it may answer with,
    how to compute it, and its own test cases.

    `values` is closed on purpose. A label a surface has never heard of is worse than no
    label, and a rule that grows a category silently is a rule nobody can check; adding
    one is a `version` bump like any other change to the rule.
    """

    name: str
    version: int
    values: tuple[str, ...]
    compute: LabelFn
    cases: tuple[Case, ...] = ()
