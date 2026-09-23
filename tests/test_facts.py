"""Behaviour facts: one parametrised test per fact's own `CASES`, plus the pipeline and
the CLI that read what they produce."""

from __future__ import annotations

import json
import sqlite3

import pytest
from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.facts import registry
from prudence.facts.base import Case, Fact, Label
from prudence.store import attribution, db, derived, hand_edits, spool


def _facts_db() -> sqlite3.Connection:
    """An in-memory store with every table a fact is allowed to read, empty."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in derived.TABLES:
        connection.execute(derived.SCHEMA[table].format(name=table))
    connection.executescript(attribution.SCHEMA)
    connection.execute(spool.SCHEMA.format(name=spool.TABLE))
    connection.execute(hand_edits.TURN_TREE_SCHEMA.format(name=hand_edits.TURN_TREE_TABLE))
    connection.execute(hand_edits.HAND_EDIT_SCHEMA.format(name=hand_edits.HAND_EDIT_TABLE))
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


def _collapsed(rows: dict[str, list[dict]], session_id: str) -> dict[str, list[dict]]:
    """The same rows with every turn id replaced by `<session>:0`, which is where parser
    version 5 put every assistant record and so every tool call."""
    return {
        table: [
            {**row, "turn_id": f"{session_id}:0"} if "turn_id" in row else dict(row)
            for row in table_rows
        ]
        for table, table_rows in rows.items()
    }


def _compute(fact: Fact, rows: dict[str, list[dict]], session_id: str) -> float | None:
    connection = _facts_db()
    try:
        for table, table_rows in rows.items():
            _insert(connection, table, table_rows)
        return fact.compute(connection, session_id)
    finally:
        connection.close()


def _by_name(name: str) -> Fact:
    return next(fact for fact in registry.FACTS if fact.name == name)


_SPREAD_ERRORS = {
    "session": [{"session_id": "s1", "capture_level": "full"}],
    "tool_call": [
        {"tool_use_id": f"t{n}", "session_id": "s1", "turn_id": f"p{n}", "error_hash": "h1"}
        for n in range(3)
    ],
}

_SPREAD_MARKERS = {
    "record": [
        {
            "record_id": f"r{n}",
            "session_id": "s1",
            "type": "system",
            "subtype": "compact_boundary",
            "prompt_id": f"p{n}",
        }
        for n in range(2)
    ],
}


@pytest.mark.parametrize(
    "name,rows,expected",
    [
        pytest.param("repeated_errors", _SPREAD_ERRORS, 1, id="repeated_errors"),
        pytest.param("compactions", _SPREAD_MARKERS, 2, id="compactions"),
    ],
)
def test_session_wide_facts_do_not_depend_on_turn_ids(
    name: str, rows: dict[str, list[dict]], expected: int
) -> None:
    """`repeated_errors` and `compactions` count over the whole session and read no turn
    id, so parser version 6's fix of the `<session>:0` collapse cannot move them: errors
    and markers spread over several turns give the same answer with the turns kept apart
    and with them collapsed. No test of these two could have failed on the collapse; the
    turn facts built on the fix carry their own collapse cases in `CASES`."""
    fact = _by_name(name)
    assert _compute(fact, rows, "s1") == expected
    assert _compute(fact, _collapsed(rows, "s1"), "s1") == expected


def test_turn_facts_have_a_case_the_collapse_would_break() -> None:
    """Each fact that groups by turn has at least one case whose answer changes when every
    turn id is collapsed to `<session>:0`, so a regression to that link fails here."""
    for name in ("test_fix_loops", "reread_files", "giant_turns"):
        fact = _by_name(name)
        broken = [
            case
            for case in fact.cases
            if case.expected is not None
            and _compute(fact, _collapsed(case.rows, case.session_id), case.session_id)
            != pytest.approx(case.expected)
        ]
        assert broken, f"{name}: no case notices the turn ids collapsing"


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


def test_facts_cli_shows_the_waste_columns_and_json_has_raw_values(lab: Workspace) -> None:
    record_one_session(lab)
    table = CliRunner().invoke(main, ["facts", "--last", "90d"])
    assert table.exit_code == 0, table.output
    header = table.output.splitlines()[0].split()
    for column in ("loops", "loop_tok", "reread", "giant", "chg_cmp"):
        assert column in header, column
    assert "giant_tok" not in header, "giant_turn_tokens is left to --json"

    raw = CliRunner().invoke(main, ["facts", "--last", "90d", "--json"])
    assert raw.exit_code == 0, raw.output
    data = json.loads(raw.output)
    (session,) = [row for row in data["sessions"] if row["session_id"] == SAMPLE_SESSION]
    # The sample session wrote no usage fields: its loops are a real count and every
    # token fact is absent rather than zero, as is its token total.
    assert session["facts"]["test_fix_loops"] == 0
    assert "giant_turn_tokens" not in session["facts"]
    assert "test_fix_loop_tokens" not in session["facts"]
    assert session["total_tokens"] is None
    assert data["trust"]["giant_turns"] == "high"


def test_loop_tokens_print_as_a_share_of_the_session() -> None:
    from prudence.cli.facts import _format

    assert _format("test_fix_loop_tokens", 250.0, 1000) == "25%"
    assert _format("test_fix_loop_tokens", 0.0, None) == "-"


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


def test_sessions_print_the_bucket_mix_and_show_keeps_the_purpose(lab: Workspace) -> None:
    """The purpose label stays in the store for one release; the list prints the mix."""
    record_one_session(lab)
    listed = CliRunner().invoke(main, ["sessions", "--last", "90d"])
    assert listed.exit_code == 0, listed.output
    assert "chg/run/rd/tlk" in listed.output
    assert "development" not in listed.output, "the purpose word is off the table"
    assert "not from reading the conversation" in listed.output.replace("\n", " ")
    as_json = json.loads(CliRunner().invoke(main, ["sessions", "--last", "90d", "--json"]).output)
    row = as_json["sessions"][0]
    assert row["purpose"] == "development", "kept in --json for comparison"
    assert row["bucket_shares"] is None, "the sample session's records carry no usage"

    shown = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION[:8]])
    assert shown.exit_code == 0, shown.output
    assert "session purpose" in shown.output
    assert "rule version 1" in shown.output


def test_usage_renders_tokens_by_bucket_project_and_week(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["usage", "--last", "90d"])
    assert result.exit_code == 0, result.output
    output = result.output
    assert "tokens by what each response did" in output
    for column in ("input", "output", "cache rd", "cache wr", "share", "responses"):
        assert column in output, column
    assert "by project" in output and "by week" in output
    assert "alpha" in output, "the project is named in the second table"
    assert "2026-W" in output, "the week table carries an ISO week"
    assert "change" in output and "run" in output, "a Write and a git commit"
    assert "development" not in output
    flat = output.replace("\n", " ")
    assert "bucket rule version 1" in flat
    assert "Nothing in the conversation is read." in flat


def test_usage_accepts_a_project_and_says_when_a_window_is_empty(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["usage", "--project", "alpha", "--last", "90d"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output

    empty = CliRunner().invoke(main, ["usage", "--last", "1h"])
    assert empty.exit_code == 0, empty.output
    assert "No response of the model in the last 1h." in empty.output


def test_status_prints_the_bucket_rule_version_and_the_coverage_gap(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0, result.output
    assert "buckets: no token counts recorded over 2 responses" in result.output
    assert "bucket rule version 1" in result.output
    assert "coverage gap: 0 tokens" in result.output
    assert "purpose:" not in result.output, "the label is stored, no longer printed"


def test_classify_with_a_model_says_it_is_not_implemented(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["classify", "--model"])
    assert result.exit_code != 0
    assert "not implemented" in result.output

    without = CliRunner().invoke(main, ["classify"])
    assert without.exit_code != 0
    assert "--model" in without.output
