"""Shared edit and usage facts across source adapters."""

from __future__ import annotations

import sqlite3

from prudence.facts import files_edited_unread, purpose, reread_files
from prudence.sources.base import Event, ToolCall, ToolResult
from prudence.store import derived, edits, repos
from prudence.store.views import usage as usage_views


def _store() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in ("edit", "edit_line", "usage", "response"):
        connection.execute(derived.SCHEMA[table].format(name=f"{table}__new"))
    return connection


def _edit(path: str, line: str) -> edits.EditFacts:
    return edits.EditFacts(file_path=path, added=[line])


def test_one_call_keeps_three_file_edits_and_their_line_hashes() -> None:
    connection = _store()
    session = derived._Session("s", None, "full")
    proposed = (_edit("/repo/a.py", "a"), _edit("/repo/b.py", "b"))
    call = ToolCall("c", "apply_patch", None, 20, None, None, edits=proposed)
    derived._note_call(session, "t", None, "r", "2026-09-23T00:00:00Z", call)
    completed = (
        _edit("/repo/a.py", "new a"),
        _edit("/repo/b.py", "new b"),
        _edit("/repo/c.py", "new c"),
    )
    result = ToolResult("c", False, 10, None, None, None, None, edits=completed)
    derived._note_result(session, result, b"key")
    derived._flush_edits(connection, session, repos.Resolver([]), b"key")

    rows = connection.execute(
        "SELECT tool_use_id, edit_index, file_path, lines_added FROM edit__new ORDER BY edit_index"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("c", 0, "/repo/a.py", 1),
        ("c", 1, "/repo/b.py", 1),
        ("c", 2, "/repo/c.py", 1),
    ]
    hashes = connection.execute(
        "SELECT edit_index, COUNT(*) FROM edit_line__new GROUP BY edit_index ORDER BY edit_index"
    ).fetchall()
    assert [tuple(row) for row in hashes] == [(0, 1), (1, 1), (2, 1)]


def test_failed_result_clears_all_proposed_edits() -> None:
    connection = _store()
    session = derived._Session("s", None, "full")
    call = ToolCall("c", "apply_patch", None, 20, None, None, edits=(_edit("a", "x"),))
    derived._note_call(session, "t", None, "r", None, call)
    derived._note_result(session, ToolResult("c", True, 10, None, None, None, None), b"key")
    derived._flush_edits(connection, session, repos.Resolver([]), b"key")
    assert connection.execute("SELECT COUNT(*) FROM edit__new").fetchone()[0] == 0


def test_explicit_input_total_is_used_without_adding_cache_twice() -> None:
    connection = _store()
    connection.execute("ALTER TABLE usage__new RENAME TO usage")
    connection.execute(
        "INSERT INTO usage (record_id, session_id, input_tokens, output_tokens,"
        " cache_read_tokens, total_input_tokens, reasoning_output_tokens, parser_version)"
        " VALUES ('r', 's', 40, 20, 60, 100, 5, 7)"
    )
    assert usage_views.usage_of_session(connection, "s")["total_tokens"] == 120
    assert usage_views.usage_map(connection, ["s"]) == {"s": 120}


def test_missing_usage_subsets_stay_null() -> None:
    connection = _store()
    connection.execute("ALTER TABLE usage__new RENAME TO usage")
    connection.execute(
        "INSERT INTO usage (record_id, session_id, total_input_tokens, output_tokens,"
        " parser_version) VALUES ('r', 's', 100, 20, 7)"
    )
    row = connection.execute(
        "SELECT input_tokens, cache_read_tokens, cache_creation_tokens,"
        " reasoning_output_tokens FROM usage"
    ).fetchone()
    assert tuple(row) == (None, None, None, None)
    session = usage_views.usage_of_session(connection, "s")
    assert session["total_tokens"] == 120
    assert session["input_tokens"] is None
    assert session["cache_read_tokens"] is None
    assert session["by_model"]["?"]["cache_creation_tokens"] is None
    assert usage_views.usage_totals(connection)["cache_read_tokens"] is None
    assert usage_views.usage_by_kind_map(connection, ["s"])["s"]["input_tokens"] is None


def test_response_bucket_total_counts_explicit_input_once() -> None:
    connection = _store()
    connection.execute("ALTER TABLE response__new RENAME TO response")
    connection.execute(derived.SCHEMA["session"].format(name="session"))
    connection.execute("INSERT INTO session (session_id, parser_version) VALUES ('s', 7)")
    connection.execute(
        "INSERT INTO response (response_id, session_id, bucket, bucket_rule_version,"
        " input_tokens, output_tokens, cache_read_tokens, total_input_tokens,"
        " reasoning_output_tokens, started_at, parser_version)"
        " VALUES ('r', 's', 'run', 2, 40, 20, 60, 100, 5, '2026-09-23T00:00:00Z', 7)"
    )
    assert usage_views.bucket_totals(connection)["total_tokens"] == 120
    row = usage_views.bucket_usage(connection, "2026-09-23")[0]
    assert row["total_tokens"] == 120
    assert row["cache_read_tokens"] == 60


def test_missing_response_subsets_stay_null_in_bucket_summary() -> None:
    connection = _store()
    connection.execute("ALTER TABLE response__new RENAME TO response")
    connection.execute(derived.SCHEMA["session"].format(name="session"))
    connection.execute("INSERT INTO session (session_id, parser_version) VALUES ('s', 7)")
    connection.execute(
        "INSERT INTO response (response_id, session_id, bucket, bucket_rule_version,"
        " total_input_tokens, output_tokens, started_at, parser_version)"
        " VALUES ('r', 's', 'run', 2, 100, 20, '2026-09-23T00:00:00Z', 7)"
    )
    row = usage_views.bucket_usage(connection, "2026-09-23")[0]
    assert row["total_tokens"] == 120
    assert row["input_tokens"] is None
    assert row["cache_read_tokens"] is None
    assert row["cache_creation_tokens"] is None


def test_unread_edits_considers_every_file_of_one_call() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in ("session", "tool_call", "edit"):
        connection.execute(derived.SCHEMA[table].format(name=table))
    connection.execute(
        "INSERT INTO session (session_id, capture_level, parser_version) VALUES ('s', 'full', 7)"
    )
    connection.execute(
        "INSERT INTO tool_call (tool_use_id, session_id, tool_name, file_path, started_at,"
        " parser_version) VALUES ('read', 's', 'Read', '/repo/a.py', '2026-09-23T00:00:00Z', 7)"
    )
    connection.execute(
        "INSERT INTO tool_call (tool_use_id, session_id, tool_name, started_at,"
        " parser_version) VALUES ('edit', 's', 'FileChange', '2026-09-23T00:01:00Z', 7)"
    )
    connection.executemany(
        "INSERT INTO edit (tool_use_id, edit_index, session_id, file_path, parser_version)"
        " VALUES ('edit', ?, 's', ?, 1)",
        [(0, "/repo/a.py"), (1, "/repo/b.py"), (2, "/repo/c.py")],
    )
    assert files_edited_unread.compute(connection, "s") == 2


def test_tool_without_usage_keeps_a_bucket_with_null_tokens() -> None:
    session = derived._Session("s", None, "full")
    call = ToolCall("c", "CommandExecution", None, 5, None, None, "git status")
    event = Event("r", True, "s", None, "2026-09-23T00:00:00Z", "tool", True, payloads=(call,))
    derived._fold_event(session, event, b"key", None)
    assert "r" in session.replies
    reply = session.replies["r"]
    assert reply.usage is None
    assert reply.kinds == [("read", False)]


def test_failed_edit_is_not_counted_as_unread_file() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in ("session", "tool_call", "edit"):
        connection.execute(derived.SCHEMA[table].format(name=table))
    connection.execute(
        "INSERT INTO session (session_id, capture_level, parser_version) VALUES ('s', 'full', 7)"
    )
    connection.execute(
        "INSERT INTO tool_call (tool_use_id, session_id, tool_name, file_path, is_error,"
        " parser_version) VALUES ('e', 's', 'Edit', '/repo/a.py', 1, 7)"
    )
    assert files_edited_unread.compute(connection, "s") == 0


def test_codex_shell_reads_do_not_create_false_file_read_facts() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for table in ("session", "record", "turn", "tool_call", "command", "edit"):
        connection.execute(derived.SCHEMA[table].format(name=table))
    connection.execute(
        "INSERT INTO session (session_id, source, capture_level, parser_version)"
        " VALUES ('codex:s', 'codex', 'full', 7)"
    )
    connection.execute(
        "INSERT INTO record (record_id, session_id, parser_version) VALUES ('r', 'codex:s', 7)"
    )
    for index in range(3):
        call_id = f"cat-{index}"
        connection.execute(
            "INSERT INTO tool_call (tool_use_id, session_id, tool_name, turn_id,"
            " started_at, parser_version) VALUES (?, 'codex:s', 'CommandExecution',"
            " 'turn', ?, 7)",
            (call_id, f"2026-09-23T00:0{index}:00Z"),
        )
        connection.execute(
            "INSERT INTO command (tool_use_id, session_id, command_class, command_text,"
            " parser_version) VALUES (?, 'codex:s', 'other', 'cat a.py', 1)",
            (call_id,),
        )
    connection.execute(
        "INSERT INTO tool_call (tool_use_id, session_id, tool_name, turn_id,"
        " started_at, parser_version) VALUES ('edit', 'codex:s', 'FileChange',"
        " 'turn', '2026-09-23T00:04:00Z', 7)"
    )
    connection.execute(
        "INSERT INTO edit (tool_use_id, session_id, file_path, parser_version)"
        " VALUES ('edit', 'codex:s', 'a.py', 2)"
    )
    assert files_edited_unread.compute(connection, "codex:s") is None
    assert reread_files.compute(connection, "codex:s") is None
    assert purpose.compute(connection, "codex:s") == purpose.UNKNOWN


def test_unknown_inner_action_marks_the_existing_reply_as_a_coverage_gap():
    session = derived._Session("s", None, "full")
    known = Event("one", True, "s", None, None, "assistant", True, message_id="r")
    reply = derived._reply_of(session, known, "t", None)
    assert reply is not None and not reply.gap
    unknown = Event(
        "two", True, "s", None, None, "assistant", True, message_id="r", response_gap=True
    )
    assert derived._reply_of(session, unknown, "t", None) is reply
    assert reply.gap
