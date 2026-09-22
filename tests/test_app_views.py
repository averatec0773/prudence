"""`store/app_views.py`: the `app_*` contract, and the `--json` output built beside it.

The app compiles against the column lists in `APP_VIEWS` and against nothing else, so
the first test here is the contract itself: every view answers with exactly those
columns, in that order. The rest check that the views say what the Python view functions
say, because two implementations of one number are two chances to be wrong.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence import config as config_module
from prudence.cli import main
from prudence.store import app_views, db, meta, pipeline, views
from prudence.store import observations as observations_module


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


def test_the_session_list_counts_edits(lab: Workspace) -> None:
    """Contract 2: the dropdown's "today" line reads `edits` off this view."""
    record_one_session(lab)
    connection = db.connect()
    try:
        listed = {
            row["session_id"]: row["edits"]
            for row in connection.execute("SELECT session_id, edits FROM app_session_list")
        }
        counted = {
            row["session_id"]: row["n"]
            for row in connection.execute(
                "SELECT session_id, COUNT(*) AS n FROM edit GROUP BY session_id"
            )
        }
    finally:
        connection.close()

    assert listed, "there is a session to count edits for"
    for session_id, edits in listed.items():
        assert edits == counted.get(session_id, 0), session_id
    assert sum(listed.values()) > 0, "the sample session edits a file"


def test_commits_by_day_agrees_with_credited_by_commit(lab: Workspace) -> None:
    """Contract 2: one commit, one day, one label, and the same label the CLI gives it."""
    record_one_session(lab)
    connection = db.connect()
    try:
        rows = list(connection.execute("SELECT * FROM app_commits_by_day"))
        hashes = [
            row["commit_hash"]
            for row in connection.execute(
                'SELECT commit_hash FROM "commit" WHERE is_merge = 0 AND committer_at IS NOT NULL'
            )
        ]
        best = views.credited_by_commit(connection, hashes)
        days = {
            row["commit_hash"]: row["day"]
            for row in connection.execute(
                "SELECT commit_hash, date(committer_at, 'localtime') AS day FROM \"commit\""
            )
        }
    finally:
        connection.close()

    assert rows, "the sample session commits"
    expected: dict[str, dict[str, int]] = {}
    for commit_hash, (confidence, _coverage) in best.items():
        cell = expected.setdefault(days[commit_hash], {"fact": 0, "inferred": 0})
        cell[confidence] += 1

    assert {row["day"] for row in rows} == set(expected)
    for row in rows:
        cell = expected[row["day"]]
        assert row["commits"] == cell["fact"] + cell["inferred"], row["day"]
        assert row["commits_fact"] == cell["fact"], row["day"]
        assert row["commits_inferred"] == cell["inferred"], row["day"]
    assert sum(row["commits"] for row in rows) == len(best), "each commit counted once"


def test_every_observation_sentence_is_the_one_the_cli_prints(lab: Workspace) -> None:
    """Contract 2: the app shows the sentence rather than rebuilding it in Swift."""
    record_one_session(lab)
    connection = db.connect()
    try:
        _observation(connection, lab.repo_key(), "test_runs", "rework")
        _observation(connection, lab.repo_key(), "sittings", "alive_head")
        _observation(connection, "*", "subagent_used", "rework")
        app_views.install_app_views(connection)

        rows = list(connection.execute("SELECT * FROM app_observation"))
        expected = views.observations(connection)
        names = views.repository_names(connection)
    finally:
        connection.close()

    assert len(rows) == len(expected) == 3
    for row, source in zip(rows, expected, strict=True):
        assert row["fact"] == source["fact"], "the view's order is the CLI's order"
        assert row["sentence"] == observations_module.sentence(
            source, names.get(source["repo_key"])
        )
    assert [row["observation_id"] for row in rows] == [1, 2, 3]
    assert rows[-1]["pooled"] == 1, "a pooled row is last and says so"


def test_the_threshold_columns_are_the_split_the_row_was_made_by(lab: Workspace) -> None:
    """Contract 3: every split as a number and an operator, for a chart to draw the line.

    One row per entry in `SPLITS`, so a split added with a rule nothing here maps would
    fail at the first regeneration rather than reach the app as a silent NULL.
    """
    record_one_session(lab)
    connection = db.connect()
    try:
        repo_key = lab.repo_key()
        for split in observations_module.SPLITS:
            _observation(connection, repo_key, split.fact, "rework", _threshold_text(split))
        _observation(connection, repo_key, "purpose:development", "rework", "purpose = development")
        _observation(connection, repo_key, "a_fact_this_build_forgot", "rework", "nothing to read")
        app_views.install_app_views(connection)
        rows = {row["fact"]: row for row in connection.execute("SELECT * FROM app_observation")}
    finally:
        connection.close()

    assert len(rows) == len(observations_module.SPLITS) + 2
    for split in observations_module.SPLITS:
        row = rows[split.fact]
        assert row["threshold_op"] == observations_module.THRESHOLD_OPS[split.rule], split.fact
        if split.rule == "above_median":
            # The median belongs to the row rather than to the split: it is the median of
            # the sessions that were compared, which `_threshold_text` made 3.5.
            assert row["threshold_value"] == 3.5, split.fact
        else:
            assert row["threshold_value"] == float(split.value), split.fact
        assert f"{row['threshold_value']:g}" in row["threshold_text"], split.fact
    label = rows["purpose:development"]
    assert (label["threshold_value"], label["threshold_op"]) == (
        None,
        observations_module.LABEL_OP,
    ), "a label is matched, not measured"
    unknown = rows["a_fact_this_build_forgot"]
    assert (unknown["threshold_value"], unknown["threshold_op"]) == (None, None)


def test_app_review_is_one_row_per_review_newest_first(lab: Workspace) -> None:
    """Contract 2: the review screen reads the stored row, not a fresh computation."""
    record_one_session(lab)
    runner = CliRunner()
    for _ in range(2):
        assert runner.invoke(main, ["review", "--last", "3650d", "--force"]).exit_code == 0

    connection = db.connect()
    try:
        rows = list(connection.execute("SELECT * FROM app_review"))
        stored = {row["id"]: row for row in connection.execute("SELECT * FROM review")}
    finally:
        connection.close()

    assert [row["id"] for row in rows] == [2, 1], "newest first"
    for row in rows:
        source = stored[row["id"]]
        assert row["headline"] == (
            f"Review {row['id']}: all projects, "
            f"{source['range_start'][:10]} to {source['range_end'][:10]}"
        )
        assert row["repo_key"] is None
        assert row["project"] == "all projects"
        assert row["range_start"] == source["range_start"]
        assert row["outcome_range_end"] == source["outcome_range_end"]
        assert json.loads(row["sections"]) == json.loads(source["sections"])["sections"]
        assert json.loads(row["numbers"]) == json.loads(source["sections"])["numbers"]
        assert row["segment_text"] is None, "no model was called"


def test_app_review_exists_before_any_review_has_been_written(lab: Workspace) -> None:
    """A store that has never had a review still answers the contract, with no rows."""
    record_one_session(lab)
    connection = db.connect()
    try:
        assert app_views.columns(connection, "app_review") == app_views.APP_VIEWS["app_review"]
        assert connection.execute("SELECT COUNT(*) FROM app_review").fetchone()[0] == 0
    finally:
        connection.close()


def test_a_week_begins_on_the_local_monday_not_the_utc_one(lab: Workspace) -> None:
    """Two commits either side of a UTC midnight fall in the week their author lived in.

    The timezone is fixed for the length of the test, because the whole question is what
    `localtime` answers and a suite that passed in London and failed in Shanghai would be
    a test keyed on somebody's machine. In Shanghai (UTC+8) a commit made at 20:00 UTC on
    Sunday 13 September was made at 04:00 on Monday 14 September, so it belongs to the
    week beginning that Monday, not to the one that ended the evening before.
    """
    record_one_session(lab)
    with _timezone("Asia/Shanghai"):
        connection = db.connect()
        try:
            repo_key = lab.repo_key()
            _followed_commit(connection, "sunday-evening", repo_key, "2026-09-13T20:00:00")
            _followed_commit(connection, "monday-morning", repo_key, "2026-09-14T09:00:00")
            app_views.install_app_views(connection)
            weeks = {
                row["week_start"]: row["commits"]
                for row in connection.execute(
                    "SELECT week_start, commits FROM app_outcomes_by_week WHERE repo_key = ?",
                    (repo_key,),
                )
            }
        finally:
            connection.close()

    assert set(weeks) == {"2026-09-14"}, "the UTC rule would have made a week of its own"
    assert weeks["2026-09-14"] == 3, "both commits above, plus the sample session's own"


def test_the_local_week_starts_on_the_same_day_the_local_day_view_does(lab: Workspace) -> None:
    """One rule, two views: a commit's week contains the day `app_commits_by_day` gives it."""
    record_one_session(lab)
    with _timezone("Asia/Shanghai"):
        connection = db.connect()
        try:
            repo_key = lab.repo_key()
            _followed_commit(connection, "sunday-evening", repo_key, "2026-09-13T20:00:00")
            app_views.install_app_views(connection)
            days = [row["day"] for row in connection.execute("SELECT day FROM app_commits_by_day")]
            weeks = [
                row["week_start"]
                for row in connection.execute("SELECT week_start FROM app_outcomes_by_week")
            ]
        finally:
            connection.close()

    for day in days:
        assert any(week <= day < _plus_seven(week) for week in weeks), day


def test_an_interrupted_ingest_leaves_the_previous_views_in_place(
    lab: Workspace, monkeypatch
) -> None:
    """A step that dies mid-pipeline must not take the app's read contract with it.

    The views used to come down before the first step and go back up after the last, so
    an ingest that failed anywhere between the two left a store with no `app_*` views at
    all and every surface refusing to render.
    """
    record_one_session(lab)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the harvest died halfway through")

    monkeypatch.setattr("prudence.store.commits.harvest", explode)
    connection = db.connect()
    try:
        with pytest.raises(RuntimeError):
            pipeline.run(connection, config_module.load(), with_archive=True)
        for name, expected in app_views.APP_VIEWS.items():
            assert app_views.columns(connection, name) == expected, name
            connection.execute(f"SELECT * FROM {name}").fetchall()
        assert connection.execute("SELECT COUNT(*) FROM app_session_list").fetchone()[0] == 1
    finally:
        connection.close()


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


def _observation(
    connection: sqlite3.Connection,
    repo_key: str,
    fact: str,
    outcome: str,
    threshold_text: str = "more than 0",
) -> None:
    """One observation row with plausible numbers; the sentence is built from them."""
    connection.execute(
        "INSERT OR REPLACE INTO observation (repo_key, fact, threshold_text, outcome,"
        " with_n, without_n, with_value, without_value, direction, coverage,"
        " fact_commits, inferred_commits, fact_version)"
        " VALUES (?, ?, ?, ?, 7, 9, 0.12, 0.31, 'lower', 0.86, 5, 2, 1)",
        (repo_key, fact, threshold_text, outcome),
    )


def _threshold_text(split: observations_module.Split) -> str:
    """The very text `observations.build` would have stored for this split.

    Written by the module rather than retyped here, so the test reads the real wording,
    including the median a rule computes from the sessions in front of it (0 to 7 here,
    whose median is 3.5).
    """
    held = [
        observations_module._Session(
            session_id=f"synthetic-{index}",
            repo_key="repo",
            rework=0.1,
            alive_head=0.9,
            coverage=0.9,
            fact_commits=1,
            inferred_commits=0,
            values={split.fact: float(index)},
        )
        for index in range(8)
    ]
    return observations_module._threshold(split, held)[1]


@contextmanager
def _timezone(name: str):
    """Run the body in one fixed timezone, which is what `localtime` reads."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = previous
        time.tzset()


def _plus_seven(day: str) -> str:
    return (datetime.fromisoformat(day) + timedelta(days=7)).strftime("%Y-%m-%d")


def _followed_commit(
    connection: sqlite3.Connection, commit_hash: str, repo_key: str, committer_at: str
) -> None:
    """One commit credited to a session with one line whose fate is known.

    The three rows are what `app_outcomes_by_week` joins: the commit for its date, the
    attribution for the confidence it is counted at, and the fate for the lines.
    """
    connection.execute(
        'INSERT OR REPLACE INTO "commit" (commit_hash, repo_key, committer_at, author_at,'
        " added_lines, files_changed, is_merge, fact_version) VALUES (?, ?, ?, ?, 1, 1, 0, 1)",
        (commit_hash, repo_key, committer_at, committer_at),
    )
    connection.execute(
        "INSERT OR REPLACE INTO attribution (commit_hash, session_id, method, rank,"
        " lines_matched, coverage, confidence, fact_version)"
        " VALUES (?, ?, 'in_session', 1, 1, 1.0, 'fact', 1)",
        (commit_hash, SAMPLE_SESSION),
    )
    connection.execute(
        "INSERT OR REPLACE INTO line_fate (commit_hash, path, line_hash, alive_7d, alive_30d,"
        " alive_90d, alive_head, alive_head_anywhere, blame_head, reworked_by, fact_version)"
        " VALUES (?, 'src/app.py', ?, 1, 1, NULL, 1, 1, 1, NULL, 1)",
        (commit_hash, f"{commit_hash}-line"),
    )


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
