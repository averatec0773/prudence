"""The spool, folded into `hook_event`: archived like any other bytes, deduped by line."""

from __future__ import annotations

import json

from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.paths import spool_file
from prudence.store import db


def _line(lab: Workspace, event: str, ts: str, head: str = "a" * 40, dirty: int = 0) -> str:
    return json.dumps(
        {
            "event": event,
            "ts": ts,
            "session_id": SAMPLE_SESSION,
            "prompt_id": "prompt_0001",
            "tool_use_id": "toolu_s2" if event.endswith("ToolUse") else "",
            "cwd": str(lab.repo),
            "head": head,
            "branch": "master",
            "dirty_fingerprint": "e3b0c44298fc1c14",
            "dirty_count": dirty,
            "elapsed_ms": 41,
        }
    )


def _append(text: str) -> None:
    path = spool_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(text)


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def test_the_spool_becomes_hook_events_and_a_repeated_line_becomes_one_row(
    lab: Workspace,
) -> None:
    first = _line(lab, "UserPromptSubmit", "2026-09-15T11:55:00.100Z")
    _append(first + "\n")
    _append(first + "\n")  # the same line twice: one event, however it got there
    _append(_line(lab, "PostToolUse", "2026-09-15T12:00:02.300Z", head="b" * 40, dirty=2) + "\n")
    record_one_session(lab)

    rows = _rows(
        "SELECT event, session_id, prompt_id, cwd, repo_key, head, dirty_count, elapsed_ms,"
        " parser_version FROM hook_event ORDER BY ts"
    )
    assert len(rows) == 2, "the duplicate line is deduped on its own hash"
    assert rows[0][0] == "UserPromptSubmit" and rows[1][0] == "PostToolUse"
    assert rows[0][1] == SAMPLE_SESSION
    assert rows[0][3] == str(lab.repo)
    assert rows[0][4] == lab.repo_key(), "the cwd is resolved to the repository like any other"
    assert rows[1][5] == "b" * 40 and rows[1][6] == 2
    assert rows[0][7] == 41 and rows[0][8] == 1

    archived = _rows("SELECT source, session_id, repo_key FROM archive_file WHERE source = 'spool'")
    assert len(archived) == 1, "the spool is archived, because raw bytes are the truth"
    assert archived[0][1] is None and archived[0][2] is None
    assert spool_file().exists(), "and it is never truncated"


def test_a_second_ingest_adds_only_the_lines_the_hooks_appended_since(lab: Workspace) -> None:
    _append(_line(lab, "SessionStart", "2026-09-15T11:54:00.000Z") + "\n")
    record_one_session(lab)
    assert len(_rows("SELECT * FROM hook_event")) == 1

    runner = CliRunner()
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    assert len(_rows("SELECT * FROM hook_event")) == 1, "nothing new, nothing doubled"

    _append(_line(lab, "Stop", "2026-09-15T12:05:00.000Z") + "\n")
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output
    assert "Hook events: 2" in result.output
    assert len(_rows("SELECT * FROM hook_event")) == 2


def test_a_rebuild_reproduces_the_hook_events_from_the_archive(lab: Workspace) -> None:
    _append(_line(lab, "SessionStart", "2026-09-15T11:54:00.000Z") + "\n")
    _append("this is not a hook line at all\n")
    record_one_session(lab)
    before = _rows("SELECT * FROM hook_event")

    spool_file().unlink()
    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    assert _rows("SELECT * FROM hook_event") == before, "rebuilt from the archived bytes"


def test_show_and_status_report_the_hook_timeline(lab: Workspace) -> None:
    _append(_line(lab, "UserPromptSubmit", "2026-09-15T11:55:00.100Z", head="a" * 40) + "\n")
    _append(_line(lab, "PostToolUse", "2026-09-15T12:00:02.300Z", head="c" * 40, dirty=3) + "\n")
    record_one_session(lab)

    runner = CliRunner()
    shown = runner.invoke(main, ["show", "--session", SAMPLE_SESSION])
    assert shown.exit_code == 0, shown.output
    assert "hook timeline" in shown.output
    assert "prompt_0001" in shown.output
    assert "aaaaaaaaaa" in shown.output and "cccccccccc" in shown.output, "head before and after"

    status = runner.invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "hook events: 2 over 1 sessions" in status.output


def test_a_store_with_no_hooks_says_so_rather_than_nothing(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert "hook events: none" in runner.invoke(main, ["status"]).output
    assert "hook timeline" not in runner.invoke(main, ["show", "--session", "dddd"]).output
