"""Behaviour facts: one parametrised test per fact's own `CASES`, plus the pipeline and
the CLI that read what they produce."""

from __future__ import annotations

import sqlite3

import pytest
from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.facts import registry
from prudence.facts.base import Case, Fact, Label
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
    for fact in registry.FACTS + registry.LABELS
    for case in fact.cases
]


@pytest.mark.parametrize("fact,case", _PARAMS)
def test_fact_case(fact: Fact | Label, case: Case) -> None:
    connection = _facts_db()
    try:
        for table, rows in case.rows.items():
            _insert(connection, table, rows)
        got = fact.compute(connection, case.session_id)
    finally:
        connection.close()
    if case.expected is None:
        assert got is None
    elif isinstance(case.expected, str):
        assert got == case.expected
    else:
        assert got == pytest.approx(case.expected)


def test_every_fact_has_cases_and_a_unique_name() -> None:
    names = [fact.name for fact in registry.FACTS + registry.LABELS]
    assert len(names) == len(set(names)), "two facts share a name"
    for fact in registry.FACTS + registry.LABELS:
        assert fact.cases, f"{fact.name} has no test cases"


def test_every_purpose_has_a_case_and_the_words_are_closed() -> None:
    """The rule is only checkable if every word it may answer with is exercised."""
    label = registry.LABELS[0]
    assert label.name == "purpose"
    covered = {case.expected for case in label.cases}
    assert covered == set(label.values), f"no case produces {set(label.values) - covered}"


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


# --- the purpose label and the usage table it groups -----------------------------------


def _labels() -> list[tuple]:
    connection = db.connect()
    try:
        return sorted(tuple(row) for row in connection.execute("SELECT * FROM session_label"))
    finally:
        connection.close()


def test_a_session_that_writes_and_commits_is_labelled_development(lab: Workspace) -> None:
    record_one_session(lab)
    assert _labels() == [(SAMPLE_SESSION, "purpose", "development", 1)]


def test_rebuild_reproduces_session_label(lab: Workspace) -> None:
    record_one_session(lab)
    before = _labels()
    assert before, "the sample session should carry a purpose"

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    assert _labels() == before


def test_sessions_and_show_print_the_purpose_as_a_label(lab: Workspace) -> None:
    record_one_session(lab)
    listed = CliRunner().invoke(main, ["sessions", "--last", "90d"])
    assert listed.exit_code == 0, listed.output
    assert "purpose" in listed.output and "development" in listed.output
    assert "not from reading the conversation" in listed.output.replace("\n", " ")

    shown = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION[:8]])
    assert shown.exit_code == 0, shown.output
    assert "session purpose" in shown.output
    assert "rule version 1" in shown.output


def test_usage_renders_tokens_and_hours_by_purpose_project_and_week(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["usage", "--last", "90d"])
    assert result.exit_code == 0, result.output
    output = result.output
    assert "tokens and active hours by purpose" in output
    for column in ("input", "output", "cache rd", "cache wr", "share", "active h"):
        assert column in output, column
    assert "by project" in output and "by week" in output
    assert "alpha" in output, "the project is named in the second table"
    assert "2026-W" in output, "the week table carries an ISO week"
    assert "development" in output
    flat = output.replace("\n", " ")
    assert "purpose rule version 1" in flat
    assert "Nothing in the conversation is read to produce it." in flat


def test_usage_accepts_a_project_and_says_when_a_window_is_empty(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["usage", "--project", "alpha", "--last", "90d"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output

    empty = CliRunner().invoke(main, ["usage", "--last", "1h"])
    assert empty.exit_code == 0, empty.output
    assert "No session in the last 1h." in empty.output


def test_status_prints_the_purpose_distribution_with_its_rule_version(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0, result.output
    assert "purpose: 1 development" in result.output
    assert "rule version 1" in result.output


def test_classify_with_a_model_says_it_is_not_implemented(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["classify", "--model"])
    assert result.exit_code != 0
    assert "not implemented" in result.output

    without = CliRunner().invoke(main, ["classify"])
    assert without.exit_code != 0
    assert "--model" in without.output
