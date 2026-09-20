"""`menubar.summary`: the numbers the menu bar shows, computed from the store alone.

No `rumps` import anywhere in this file, so it runs on any platform. Timestamps are
built from the local day under test (`_at`), the same conversion `summary._day_bounds`
uses, so the test passes regardless of the machine's own timezone.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, time

from click.testing import CliRunner
from conftest import Workspace, commit, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.menubar.summary import today_summary, week_summary
from prudence.store import db

TODAY = date(2026, 9, 19)
YESTERDAY = date(2026, 9, 18)

TODAY_SESSION = "10000000-0000-4000-8000-000000000001"
YESTERDAY_SESSION = "20000000-0000-4000-8000-000000000002"


def _at(day: date, hour: int) -> str:
    """Local `hour`:00 of `day`, as the UTC-stamped string the fixtures use."""
    moment = datetime.combine(day, time(hour, 0)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _commit_at(day: date, hour: int) -> str:
    moment = datetime.combine(day, time(hour, 0)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_and_commit(lab: Workspace, session_id: str, day: date, path: str, content: str) -> None:
    """One session: writes a file, then commits it itself, on the given day."""
    target = lab.repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    commit_hash = commit(lab.repo, _commit_at(day, 10), f"change {path}")
    short = commit_hash[:7]
    write_transcript(
        lab.project,
        session_id,
        [
            prompt(session_id, str(lab.repo), "Write and commit.", at=_at(day, 9)),
            *tool_call(
                session_id,
                str(lab.repo),
                f"toolu_{session_id[:8]}_w",
                "Write",
                {"file_path": f"{lab.repo}/{path}", "content": content},
                at=_at(day, 9),
            ),
            *tool_call(
                session_id,
                str(lab.repo),
                f"toolu_{session_id[:8]}_c",
                "Bash",
                {"command": "git commit -am 'change'"},
                result={"stdout": f"[master {short}] change\n 1 file changed", "stderr": ""},
                at=_at(day, 10),
            ),
        ],
    )


def _ingest(lab: Workspace) -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def test_today_summary_counts_only_todays_sessions_edits_and_commits(lab: Workspace) -> None:
    _write_and_commit(lab, TODAY_SESSION, TODAY, "src/today.py", "today = 1\n")
    _write_and_commit(lab, YESTERDAY_SESSION, YESTERDAY, "src/yesterday.py", "yesterday = 1\n")
    _ingest(lab)

    connection = db.connect()
    try:
        today = today_summary(connection, TODAY)
        yesterday = today_summary(connection, YESTERDAY)
    finally:
        connection.close()

    assert today.sessions == 1
    assert today.edits == 1
    assert today.commits == 1
    assert today.last_ingest is not None

    assert yesterday.sessions == 1
    assert yesterday.edits == 1
    assert yesterday.commits == 1


def test_a_day_with_nothing_is_all_zeroes(lab: Workspace) -> None:
    _write_and_commit(lab, TODAY_SESSION, TODAY, "src/today.py", "today = 1\n")
    _ingest(lab)

    connection = db.connect()
    try:
        empty = today_summary(connection, date(2026, 1, 1))
    finally:
        connection.close()

    assert empty.sessions == 0
    assert empty.edits == 0
    assert empty.commits == 0
    assert empty.last_ingest is not None, "an ingest happened, even if nothing happened today"


def test_week_summary_before_any_token_or_observation_is_empty(lab: Workspace) -> None:
    _write_and_commit(lab, TODAY_SESSION, TODAY, "src/today.py", "today = 1\n")
    _ingest(lab)

    connection = db.connect()
    try:
        week = week_summary(connection, TODAY)
    finally:
        connection.close()

    assert week.top_purposes == (), "the recorded session carried no usage fields"
    assert week.latest_observation is None, "five sessions on a side are needed for one"


def test_week_summary_reports_the_top_two_purposes_and_the_latest_observation(
    lab: Workspace,
) -> None:
    _write_and_commit(lab, TODAY_SESSION, TODAY, "src/today.py", "today = 1\n")
    _ingest(lab)

    connection = db.connect()
    try:
        repo_key = lab.repo_key()
        _insert_usage_session(
            connection, "synthetic-week-dev", repo_key, _at(TODAY, 8), "development", 300
        )
        _insert_usage_session(
            connection, "synthetic-week-research", repo_key, _at(TODAY, 8), "research", 100
        )
        _insert_usage_session(
            connection, "synthetic-week-conversation", repo_key, _at(TODAY, 8), "conversation", 10
        )
        connection.execute(
            "INSERT INTO observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                repo_key,
                "formatter_runs",
                "formatter_runs > 0",
                "rework",
                6,
                6,
                0.05,
                0.20,
                "lower",
                0.9,
                10,
                2,
                1,
            ),
        )
        week = week_summary(connection, TODAY)
    finally:
        connection.close()

    assert [label for label, _share in week.top_purposes] == ["development", "research"]
    shares = dict(week.top_purposes)
    assert 0.7 < shares["development"] < 0.8, "300 of 410 tokens"
    assert 0.2 < shares["research"] < 0.3, "100 of 410 tokens"

    assert week.latest_observation is not None
    assert "%" in week.latest_observation
    assert "formatter_runs" not in week.latest_observation, "the wording, not the fact's own name"


def _insert_usage_session(
    connection: sqlite3.Connection,
    session_id: str,
    repo_key: str,
    first_at: str,
    purpose: str,
    input_tokens: int,
) -> None:
    """A synthetic session with one usage row and one purpose label, nothing else."""
    connection.execute(
        "INSERT INTO session (session_id, repo_key, source, entrypoint, cwd, first_at,"
        " last_at, record_count, capture_level, parser_version, notes)"
        " VALUES (?, ?, 'claude_code', 'cli', NULL, ?, ?, 1, 'full', 2, NULL)",
        (session_id, repo_key, first_at, first_at),
    )
    connection.execute(
        "INSERT INTO usage (record_id, session_id, turn_id, request_id, model, input_tokens,"
        " output_tokens, cache_read_tokens, cache_creation_tokens, parser_version)"
        " VALUES (?, ?, NULL, ?, 'claude-x', ?, 0, 0, 0, 2)",
        (f"{session_id}-u1", session_id, f"{session_id}-req1", input_tokens),
    )
    connection.execute(
        "INSERT INTO session_label (session_id, name, label, rule_version)"
        " VALUES (?, 'purpose', ?, 1)",
        (session_id, purpose),
    )


def test_before_the_first_ingest_everything_is_zero_and_last_ingest_is_none(lab: Workspace) -> None:
    connection = db.connect()
    try:
        summary = today_summary(connection, TODAY)
    finally:
        connection.close()

    assert summary.sessions == 0
    assert summary.edits == 0
    assert summary.commits == 0
    assert summary.last_ingest is None
