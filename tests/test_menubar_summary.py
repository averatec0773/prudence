"""`menubar.summary`: the numbers the menu bar shows, computed from the store alone.

No `rumps` import anywhere in this file, so it runs on any platform. Timestamps are
built from the local day under test (`_at`), the same conversion `summary._day_bounds`
uses, so the test passes regardless of the machine's own timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from click.testing import CliRunner
from conftest import Workspace, commit, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.menubar.summary import today_summary
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
