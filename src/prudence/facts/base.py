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
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

TRUST_LEVELS = ("high", "medium", "low")

ComputeFn = Callable[[sqlite3.Connection, str], "int | float | None"]


@dataclass(frozen=True)
class Case:
    """One synthetic session: rows to insert per derived table, and the expected value.

    `rows` maps a table name to a list of column-keyed dicts. `parser_version` and
    `fact_version` are filled in automatically when a row omits them, since every
    derived table requires one and no fact's logic depends on their value.
    """

    name: str
    session_id: str
    expected: int | float | None
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
