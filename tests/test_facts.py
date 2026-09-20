"""Behaviour facts: one parametrised test per fact's own `CASES`, plus the pipeline and
the CLI that read what they produce."""

from __future__ import annotations

import sqlite3

import pytest
from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.facts import registry
from prudence.facts.base import Case, Fact
from prudence.store import attribution, db, derived


def _facts_db() -> sqlite3.Connection:
    """An in-memory store with every table a fact is allowed to read, empty."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in derived.TABLES:
        connection.execute(derived.SCHEMA[table].format(name=table))
    connection.executescript(attribution.SCHEMA)
    return connection


def _insert(connection: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    """Insert one case's rows, filling in the version columns every derived table
    requires but no fact's logic depends on."""
    known = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    for row in rows:
        data = dict(row)
        data.setdefault("parser_version", 1)
        data.setdefault("fact_version", 1)
        columns = [column for column in data if column in known]
        placeholders = ", ".join("?" * len(columns))
        names = ", ".join(columns)
        connection.execute(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
            [data[column] for column in columns],
        )


_PARAMS = [
    pytest.param(fact, case, id=f"{fact.name}: {case.name}")
    for fact in registry.FACTS
    for case in fact.cases
]


@pytest.mark.parametrize("fact,case", _PARAMS)
def test_fact_case(fact: Fact, case: Case) -> None:
    connection = _facts_db()
    try:
        for table, rows in case.rows.items():
            _insert(connection, table, rows)
        got = fact.compute(connection, case.session_id)
    finally:
        connection.close()
    if case.expected is None:
        assert got is None
    else:
        assert got == pytest.approx(case.expected)


def test_every_fact_has_cases_and_a_unique_name() -> None:
    names = [fact.name for fact in registry.FACTS]
    assert len(names) == len(set(names)), "two facts share a name"
    for fact in registry.FACTS:
        assert fact.cases, f"{fact.name} has no test cases"


def test_rebuild_reproduces_session_fact(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        before = sorted(tuple(row) for row in connection.execute("SELECT * FROM session_fact"))
        assert before, "the sample session should produce at least one fact"
    finally:
        connection.close()

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output

    connection = db.connect()
    try:
        after = sorted(tuple(row) for row in connection.execute("SELECT * FROM session_fact"))
    finally:
        connection.close()
    assert after == before


def test_facts_cli_renders_a_table_with_a_trust_footer(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["facts", "--last", "90d"])
    assert result.exit_code == 0, result.output
    output = result.output
    assert SAMPLE_SESSION[:8] in output
    assert "sit" in output and "fmt" in output and "test" in output
    assert "trust:" in output
    assert "high" in output and "medium" in output
    assert "sessions in the last 90d" in output


def test_show_session_lists_behaviour_facts_with_trust(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION[:8]])
    assert result.exit_code == 0, result.output
    assert "behaviour facts" in result.output
    assert "trust high" in result.output or "trust medium" in result.output
