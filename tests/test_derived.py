"""What the parser makes of the archive, including everything it does not understand."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace

from prudence.cli import main
from prudence.store import db

SESSION_ONE = "11111111-1111-4111-8111-111111111111"
SESSION_TWO = "22222222-2222-4222-8222-222222222222"
SESSION_RESUMED = "44444444-4444-4444-8444-444444444444"


def _ingest(level: str = "full") -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", level])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def test_sessions_records_turns_and_tool_calls_are_built(workspace: Workspace) -> None:
    _ingest()
    sessions = {row[0]: row for row in _rows("SELECT session_id, cwd, record_count FROM session")}
    assert set(sessions) == {SESSION_ONE, SESSION_TWO, SESSION_RESUMED}
    assert sessions[SESSION_ONE][1] == str(workspace.repo), "full capture keeps the directory"
    assert sessions[SESSION_TWO][2] == 15, "the subagent's records belong to its parent session"

    tools = _rows("SELECT tool_use_id, tool_name, file_path, is_error FROM tool_call")
    by_id = {row[0]: row for row in tools}
    assert len(tools) == 8
    assert by_id["toolu_a1"][1:3] == ("Edit", "/repo/src/parser.py")
    assert by_id["toolu_a3"][3] == 1, "a failed Bash call is recorded as an error"
    assert by_id["toolu_c1"][1] == "Write", "a subagent's tool call is recorded too"
    assert by_id["toolu_b3"][2] is None, "a Bash call has no file path"

    turns = _rows("SELECT turn_id, session_id FROM turn")
    turn_ids = {row[0] for row in turns}
    assert {"prompt-aaa", "prompt-bbb"} <= turn_ids, "promptId is the turn key when present"
    assert f"{SESSION_ONE}:1" in turn_ids, "without promptId a turn is numbered per session"
    chars = _rows("SELECT user_prompt_chars FROM turn WHERE turn_id = 'prompt-aaa'")
    assert chars[0][0] == len("Look at the config loader.")

    sidechain = _rows("SELECT COUNT(*) FROM record WHERE is_sidechain = 1")
    assert sidechain[0][0] == 3
    agents = _rows("SELECT DISTINCT agent_id FROM record WHERE agent_id IS NOT NULL")
    assert len(agents) == 1, "subagent records carry the agent's own file id"


def test_unknown_record_types_are_counted_not_fatal(workspace: Workspace) -> None:
    _ingest()
    unknown = {
        row[0]: row for row in _rows("SELECT type, claude_version, count FROM unknown_record_type")
    }
    assert set(unknown) == {"last-prompt", "custom-title", "file-history-snapshot", "cost-state"}
    assert unknown["last-prompt"][1] == "2.1.278"
    assert unknown["last-prompt"][2] == 1
    kept = _rows("SELECT COUNT(*) FROM record WHERE type = 'last-prompt'")
    assert kept[0][0] == 1, "an unknown record is still a record"

    status = CliRunner().invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "last-prompt" in status.output


def test_a_resumed_session_is_noted_and_its_replayed_records_are_not_counted_twice(
    workspace: Workspace,
) -> None:
    _ingest()
    notes = dict(_rows("SELECT session_id, notes FROM session"))
    assert notes[SESSION_ONE] is None
    assert notes[SESSION_RESUMED] is not None
    assert "resumed" in notes[SESSION_RESUMED]
    assert "replayed 10 records" in notes[SESSION_RESUMED]
    counts = dict(_rows("SELECT session_id, record_count FROM session"))
    assert counts[SESSION_ONE] == 12
    assert counts[SESSION_RESUMED] == 4, "only the records this session added"
    owner = _rows("SELECT session_id FROM record WHERE record_id = 'u01'")
    assert owner[0][0] == SESSION_ONE, "the first session to claim a uuid keeps it"


def test_metadata_only_stores_no_paths_and_no_working_directory(workspace: Workspace) -> None:
    _ingest(level="metadata-only")
    assert _rows("SELECT COUNT(*) FROM tool_call WHERE file_path IS NOT NULL") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM session WHERE cwd IS NOT NULL") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM tool_call")[0][0] == 8, "the shape is still recorded"
    assert _rows("SELECT DISTINCT capture_level FROM session") == [("metadata-only",)]
    files = _rows("SELECT COUNT(*) FROM archive_file")
    assert files[0][0] == 4, "the archive keeps the same bytes at either level"


def test_rebuild_reproduces_the_same_tables(workspace: Workspace) -> None:
    _ingest()
    before_sessions = sorted(_rows("SELECT * FROM session"))
    before_tools = sorted(_rows("SELECT * FROM tool_call"))

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output

    assert sorted(_rows("SELECT * FROM session")) == before_sessions
    assert sorted(_rows("SELECT * FROM tool_call")) == before_tools
