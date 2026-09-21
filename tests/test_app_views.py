"""`store/app_views.py`: the `app_*` contract, and the `--json` output built beside it.

The app compiles against the column lists in `APP_VIEWS` and against nothing else, so
the first test here is the contract itself: every view answers with exactly those
columns, in that order. The rest check that the views say what the Python view functions
say, because two implementations of one number are two chances to be wrong.
"""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner
from conftest import Workspace, record_one_session

from prudence.cli import main
from prudence.store import app_views, db, meta, views


def test_every_view_answers_with_the_contract_columns(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        for name, expected in app_views.APP_VIEWS.items():
            assert app_views.columns(connection, name) == expected, name
            connection.execute(f"SELECT * FROM {name}").fetchall()
        assert meta.get_meta(connection, meta.APP_CONTRACT_VERSION_KEY) == meta.APP_CONTRACT_VERSION
    finally:
        connection.close()


def test_app_status_is_one_row_naming_every_version_behind_it(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        rows = connection.execute("SELECT * FROM app_status").fetchall()
    finally:
        connection.close()

    assert len(rows) == 1, "the app reads one row and renders it; there is never a second"
    row = rows[0]
    assert row["sessions"] == 1
    assert row["projects"] == 1
    assert row["app_contract_version"] == meta.APP_CONTRACT_VERSION
    assert row["last_ingest_at"], "the archive knows when it last saw a file"
    for column in ("parser_version", "commit_fact_version", "outcome_fact_version"):
        assert row[column] >= 1, column


def test_the_usage_view_totals_agree_with_usage_totals(lab: Workspace) -> None:
    """Same tokens, same active time, same session count as the functions the CLI uses."""
    record_one_session(lab)
    connection = db.connect()
    try:
        repo_key = lab.repo_key()
        _usage_session(connection, "synthetic-a", repo_key, "2026-09-10T09:00:00", "development")
        _usage_session(connection, "synthetic-b", repo_key, "2026-09-11T09:00:00", "research")

        expected = views.usage_totals(connection)
        ids = [row["session_id"] for row in connection.execute("SELECT session_id FROM session")]
        active = views.active_seconds_map(connection, ids)
        row = connection.execute(
            "SELECT SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,"
            " SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cache_creation_tokens) AS cache_creation_tokens,"
            " SUM(total_tokens) AS total_tokens, SUM(sessions) AS sessions,"
            " SUM(measured_sessions) AS measured_sessions,"
            " SUM(active_minutes) AS active_minutes FROM app_usage_by_purpose_day"
        ).fetchone()
        purposes = {
            r["purpose"]: r["total_tokens"]
            for r in connection.execute(
                "SELECT purpose, SUM(total_tokens) AS total_tokens"
                " FROM app_usage_by_purpose_day GROUP BY purpose"
            )
        }
    finally:
        connection.close()

    for column in views.TOKEN_COLUMNS:
        assert row[column] == expected[column], column
    assert row["total_tokens"] == expected["total_tokens"]
    assert row["sessions"] == len(ids)
    assert row["measured_sessions"] == expected["sessions"]
    assert abs(row["active_minutes"] - sum(active.values()) / 60) < 0.001
    assert purposes["development"] == 165
    assert purposes["research"] == 30


def test_the_session_list_agrees_with_search_sessions(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        found = views.search_sessions(connection, limit=views.MAX_LIMIT)
        listed = {
            row["session_id"]: row for row in connection.execute("SELECT * FROM app_session_list")
        }
    finally:
        connection.close()

    assert len(listed) == found["total"]
    for result in found["results"]:
        row = listed[result["session_id"]]
        assert row["project"] == result["repository"]
        assert row["started_at"] == result["started_at"]
        assert row["purpose"] == result["purpose"]
        assert row["sittings"] == result["sittings"]
        assert row["total_tokens"] == result["tokens"]
        assert row["commits_fact"] == result["commits_fact"]
        assert row["commits_inferred"] == result["commits_inferred"]
        assert row["commits_uncertain"] == result["commits_uncertain"]
        assert row["coverage"] == result["coverage"]
        assert row["content_archived"] == (1 if result["capture_notes"] != "metadata-only" else 0)


def test_a_rebuild_leaves_the_views_in_place(lab: Workspace) -> None:
    """A rebuild swaps the tables under the views; the contract has to come back up."""
    record_one_session(lab)
    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output

    connection = db.connect()
    try:
        for name, expected in app_views.APP_VIEWS.items():
            assert app_views.columns(connection, name) == expected, name
        assert connection.execute("SELECT COUNT(*) FROM app_session_list").fetchone()[0] == 1
        assert meta.get_meta(connection, meta.APP_CONTRACT_VERSION_KEY) == meta.APP_CONTRACT_VERSION
    finally:
        connection.close()


def test_meta_answers_a_missing_key_rather_than_failing() -> None:
    """A store older than this table is a missing value, not an error (rule 3)."""
    connection = db.connect()
    try:
        assert meta.get_meta(connection, "nothing-wrote-this") is None
        assert meta.get_meta(connection, "nothing-wrote-this", "fallback") == "fallback"
        meta.set_meta(connection, "a", "1")
        meta.set_meta(connection, "a", "2")
        assert meta.get_meta(connection, "a") == "2", "one row per key, rewritten in place"
    finally:
        connection.close()


def test_every_command_the_app_calls_prints_json(lab: Workspace) -> None:
    """`--json` on each of the six, parsed, with the keys a surface reads off it."""
    record_one_session(lab)
    runner = CliRunner()
    expected = {
        "status": ("engine_version", "repositories", "derived", "usage", "observations"),
        "usage": ("window", "sessions", "by_purpose", "by_project", "by_week", "total"),
        "outcomes": ("window", "sessions", "by_session", "by_project", "observations"),
        "observations": ("observations", "pooled", "min_sessions", "fact_version"),
        "sessions": ("window", "sessions", "notes"),
        "ingest": ("parsed", "harvested", "attributed", "outcomes", "observations"),
    }
    for command, keys in expected.items():
        result = runner.invoke(main, [command, "--json"])
        assert result.exit_code == 0, f"{command}: {result.output}"
        data = json.loads(result.output)
        assert set(keys) <= set(data), command


def test_the_json_and_the_text_carry_the_same_totals(lab: Workspace) -> None:
    """One dictionary, two renderings: the page cannot drift from the JSON beside it."""
    record_one_session(lab)
    connection = db.connect()
    try:
        repo_key = lab.repo_key()
        _usage_session(connection, "synthetic-a", repo_key, "2026-09-10T09:00:00", "development")
    finally:
        connection.close()

    runner = CliRunner()
    as_json = json.loads(runner.invoke(main, ["usage", "--last", "3650d", "--json"]).output)
    text = runner.invoke(main, ["usage", "--last", "3650d"]).output
    assert as_json["total"]["total_tokens"] == 165
    assert as_json["sessions"] == 2
    assert "all purposes" in text
    assert f"{as_json['sessions']} sessions in the last 3650d" in text


def _usage_session(
    connection: sqlite3.Connection, session_id: str, repo_key: str, first_at: str, purpose: str
) -> None:
    """A synthetic session with one usage row and one purpose label, nothing else."""
    connection.execute(
        "INSERT INTO session (session_id, repo_key, source, entrypoint, cwd, first_at,"
        " last_at, record_count, capture_level, parser_version, notes)"
        " VALUES (?, ?, 'claude_code', 'cli', NULL, ?, ?, 1, 'full', 2, NULL)",
        (session_id, repo_key, first_at, first_at),
    )
    tokens = (100, 50, 10, 5) if purpose == "development" else (20, 10, 0, 0)
    connection.execute(
        "INSERT INTO usage (record_id, session_id, turn_id, request_id, model, input_tokens,"
        " output_tokens, cache_read_tokens, cache_creation_tokens, parser_version)"
        " VALUES (?, ?, NULL, ?, 'claude-x', ?, ?, ?, ?, 2)",
        (f"{session_id}-u1", session_id, f"{session_id}-req1", *tokens),
    )
    connection.execute(
        "INSERT INTO session_label (session_id, name, label, rule_version)"
        " VALUES (?, 'purpose', ?, 1)",
        (session_id, purpose),
    )
