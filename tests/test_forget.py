"""`prudence forget`: what is removed, and what stops being recorded afterwards."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence import config as config_module
from prudence.cli import main
from prudence.store import db


def _counts() -> dict[str, int]:
    connection = db.connect()
    try:
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in (
                "session",
                "record",
                "turn",
                "tool_call",
                "edit",
                "edit_line",
                "command",
                "attribution",
                "archive_file",
                "archive_chunk",
                "commit",
                "repository",
            )
        }
    finally:
        connection.close()


def test_forgetting_a_session_removes_its_rows_and_its_bytes(lab: Workspace) -> None:
    record_one_session(lab)
    before = _counts()
    assert before["session"] == 1 and before["archive_chunk"] > 0

    result = CliRunner().invoke(main, ["forget", "--session", SAMPLE_SESSION[:8], "--yes"])
    assert result.exit_code == 0, result.output
    assert "Rows deleted:" in result.output
    assert "VACUUM" in result.output, "the command says why the file did not shrink"

    after = _counts()
    for table in ("session", "record", "turn", "tool_call", "edit", "edit_line", "command"):
        assert after[table] == 0, table
    assert after["archive_file"] == 0 and after["archive_chunk"] == 0
    assert after["commit"] == before["commit"], "the repository's commits are not the session's"


def test_a_confirmation_that_is_declined_changes_nothing(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["forget", "--session", SAMPLE_SESSION], input="n\n")
    assert result.exit_code != 0
    assert _counts()["session"] == 1


def test_forgetting_a_project_also_stops_recording_it(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    result = runner.invoke(main, ["forget", "--project", "alpha", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Disabled alpha" in result.output

    after = _counts()
    assert after["session"] == 0 and after["commit"] == 0 and after["repository"] == 0
    assert after["archive_file"] == 0
    assert not config_module.load().repositories, "the consent record is gone too"

    again = runner.invoke(main, ["ingest"])
    assert again.exit_code != 0, "with nothing enabled, ingest has nothing to do"
    assert _counts()["session"] == 0, "a forgotten project does not come back"


def test_vacuum_is_only_run_when_asked(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert "VACUUM" in runner.invoke(main, ["forget", "--session", "dddd", "--yes"]).output
    result = runner.invoke(main, ["forget", "--vacuum"])
    assert result.exit_code == 0, result.output
    assert "Vacuuming" in result.output and "Freed" in result.output
