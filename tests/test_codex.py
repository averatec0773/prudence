"""Codex rollout shapes at the source boundary."""

import json
from pathlib import Path

from prudence.sources.base import Prompt, ToolCall, ToolResult, Usage
from prudence.sources.codex import Codex


def read(records, *, name="rollout-2026-09-23T10-00-00-session.jsonl"):
    lines = [(i * 100, json.dumps(record).encode()) for i, record in enumerate(records)]
    return list(Codex().events(lines, name, "session", None))


def payloads(events, cls):
    return [payload for event in events for payload in event.payloads if isinstance(payload, cls)]


def test_discovery_and_metadata(tmp_path):
    home = tmp_path / "codex"
    for folder in ("sessions/2026/09/23", "archived_sessions"):
        directory = home / folder
        directory.mkdir(parents=True)
        path = directory / f"rollout-2026-09-23T10-00-00-{folder.split('/')[0]}.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(x)
                for x in [
                    {
                        "timestamp": "2026-09-23T10:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": folder.split("/")[0],
                            "cwd": "/repo",
                            "cli_version": "1.0",
                        },
                    },
                    {
                        "timestamp": "2026-09-23T10:01:00Z",
                        "type": "turn_context",
                        "payload": {"cwd": "/repo2", "model": "codex"},
                    },
                ]
            )
            + "\n"
        )
    sessions = Codex(home).session_files()
    assert len(sessions) == 2
    assert {s.session_id for s in sessions} == {"codex:sessions", "codex:archived_sessions"}
    assert all(s.cwd == "/repo" and s.entrypoint is None for s in sessions)
    assert all(s.last_at.isoformat().startswith("2026-09-23T10:01") for s in sessions)
    assert Codex(home).companion_files(sessions[0]) == []


def test_prompts_models_and_response_usage():
    events = read(
        [
            {
                "type": "session_meta",
                "payload": {"id": "session", "cwd": "/one", "cli_version": "0.1"},
            },
            {
                "type": "turn_context",
                "payload": {"turn_id": "t1", "cwd": "/two", "model": "model-A"},
            },
            {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
            {
                "type": "token_usage_record",
                "payload": {
                    "response_id": "r1",
                    "turn_id": "t1",
                    "session_id": "session",
                    "usage": {
                        "input_tokens": 120,
                        "cached_input_tokens": 40,
                        "cache_write_input_tokens": 5,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 8,
                    },
                },
            },
            {
                "type": "turn_context",
                "payload": {"turn_id": "t2", "cwd": "/three", "model": "model-B"},
            },
            {
                "type": "token_usage_record",
                "payload": {
                    "response_id": "r2",
                    "turn_id": "t2",
                    "usage": {"input_tokens": 30, "output_tokens": 10},
                },
            },
        ]
    )
    assert payloads(events, Prompt) == [Prompt(chars=5)]
    usage = payloads(events, Usage)
    assert [
        (
            u.request_id,
            u.model,
            u.total_input_tokens,
            u.input_tokens,
            u.cache_read_tokens,
            u.cache_creation_tokens,
            u.reasoning_output_tokens,
        )
        for u in usage
    ] == [
        ("codex:session:r1", "model-A", 120, 75, 40, 5, 8),
        ("codex:session:r2", "model-B", 30, None, None, None, None),
    ]
    assert events[3].message_id == "codex:session:r1"
    assert events[4].cwd == "/three"


def test_legacy_usage_deltas_and_modern_precedence():
    events = read(
        [
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 30,
                            "output_tokens": 10,
                        },
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 30,
                            "output_tokens": 10,
                        },
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 30,
                            "output_tokens": 10,
                        },
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 30,
                            "output_tokens": 10,
                        },
                    },
                },
            },
            {
                "type": "token_usage_record",
                "payload": {
                    "response_id": "r1",
                    "usage": {"input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 10},
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 130,
                            "cached_input_tokens": 35,
                            "output_tokens": 13,
                        },
                        "last_token_usage": {
                            "input_tokens": 30,
                            "cached_input_tokens": 5,
                            "output_tokens": 3,
                        },
                    },
                },
            },
        ]
    )
    assert len(payloads(events, Usage)) == 2
    assert [u.total_input_tokens for u in payloads(events, Usage)] == [100, 30]


def test_completed_inner_actions_override_wrappers_and_failed_edits():
    events = read(
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "functions.exec",
                    "call_id": "outer",
                    "arguments": "{}",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "CommandExecution",
                        "id": "cmd",
                        "command": "pytest -q",
                        "cwd": "/repo",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "FileChange",
                        "id": "edit",
                        "status": "completed",
                        "changes": {
                            "a.py": {"type": "add", "content": "one\ntwo\n"},
                            "b.py": {"type": "update", "unified_diff": "@@ -1 +1 @@\n-old\n+new\n"},
                            "c.py": {"type": "delete", "content": "gone\n"},
                            "d.py": {
                                "type": "update",
                                "move_path": "e.py",
                                "unified_diff": "@@ -1 +1 @@\n-x\n+y\n",
                            },
                        },
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "FileChange",
                        "id": "failed",
                        "status": "declined",
                        "changes": {"bad.py": {"type": "add", "content": "bad"}},
                    },
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "outer", "output": "done"},
            },
        ]
    )
    calls = payloads(events, ToolCall)
    assert len(calls) == 2
    assert [c.tool_name for c in calls] == ["CommandExecution", "FileChange"]
    assert calls[0].command.command_class == "test"
    assert [(e.file_path, e.added, e.removed, e.is_new_file) for e in calls[1].edits] == [
        ("a.py", ["one", "two"], [], True),
        ("b.py", ["new"], ["old"], False),
        ("c.py", [], ["gone"], False),
        ("d.py", [], ["x"], False),
        ("e.py", ["y"], [], False),
    ]
    assert len(payloads(events, ToolResult)) == 2


def test_raw_calls_outputs_and_delayed_command_completion():
    events = read(
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git status"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Process running with session ID 123",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "c2",
                    "name": "write_stdin",
                    "arguments": json.dumps({"session_id": 123, "chars": ""}),
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "CommandExecution",
                        "id": "inner1",
                        "command": "git status",
                        "process_id": 123,
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
            },
        ]
    )
    assert len(payloads(events, ToolCall)) == 1
    assert payloads(events, ToolCall)[0].command.command_class == "git_other"
    assert len(payloads(events, ToolResult)) == 1


def test_unknown_and_unreadable_remain_visible():
    source = Codex()
    events = list(
        source.events([(0, b"{broken"), (7, b'{"type":"new","payload":{"x":1}}')], "f", "s", None)
    )
    assert [e.record_type for e in events] == ["unreadable", "new"]
    assert all(not e.known_type for e in events)
    assert all(e.record_id and not e.stable_id for e in events)
    assert events[1].key_shape == ("payload", "payload.x", "type")
    nested = read(
        [{"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "NewTool"}}}]
    )
    assert nested[0].known_type is False
    assert "payload.item" in nested[0].key_shape


def test_copied_session_ids_do_not_depend_on_home_and_mcp_completion_is_counted_once():
    records = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "namespace": "mcp__codex_apps__google_drive",
                "name": "_search",
                "call_id": "raw",
                "arguments": "{}",
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "McpToolCall",
                    "id": "inner",
                    "server": "codex_apps",
                    "tool": "google drive_search",
                    "status": "completed",
                },
            },
        },
    ]
    lines = [(index * 100, json.dumps(row).encode()) for index, row in enumerate(records)]
    left = list(Codex().events(lines, "/home/a/rollout.jsonl", "codex:session", None))
    right = list(Codex().events(lines, "/home/b/rollout.jsonl", "codex:session", None))
    assert [event.record_id for event in left] == [event.record_id for event in right]
    assert len(payloads(left, ToolCall)) == 1


def test_command_argv_and_usage_response_association():
    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t", "model": "m"}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "CommandExecution",
                        "id": "c",
                        "command": ["bash", "-lc", "pytest -q"],
                        "status": "completed",
                        "exit_code": 0,
                    },
                },
            },
            {
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t",
                    "response_id": "r",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            },
        ]
    )
    assert payloads(events, ToolCall)[0].command.command_class == "test"
    assert events[1].message_id == "codex:session:r"


def test_repeated_identical_commands_pair_one_to_one_with_structured_completion():
    records = []
    for call_id in ("one", "two", "three"):
        records.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "pytest -q"}),
                },
            }
        )
        if call_id == "two":
            records.append(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "item_completed",
                        "item": {
                            "type": "CommandExecution",
                            "id": "two",
                            "command": "pytest -q",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    },
                }
            )
    events = read(records)
    assert len(payloads(events, ToolCall)) == 3
    assert [call.call_id for call in payloads(events, ToolCall)] == [
        "codex:session:one",
        "codex:session:two",
        "codex:session:three",
    ]


def test_repeated_identical_mcp_calls_pair_one_to_one():
    records = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "call_id": call_id,
                "namespace": "mcp__node_repl__",
                "name": "js",
                "arguments": "{}",
            },
        }
        for call_id in ("first", "second", "third")
    ]
    records.insert(
        2,
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "McpToolCall",
                    "id": "second",
                    "server": "node_repl",
                    "tool": "js",
                    "status": "completed",
                },
            },
        },
    )
    events = read(records)
    assert len(payloads(events, ToolCall)) == 3


def test_modern_usage_suppresses_only_its_matching_legacy_delta():
    def legacy(total):
        return {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"input_tokens": total, "output_tokens": total // 10}
                },
            },
        }

    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t", "model": "m"}},
            legacy(100),
            {
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t",
                    "response_id": "r1",
                    "usage": {"input_tokens": 100, "output_tokens": 10},
                },
            },
            legacy(150),
        ]
    )
    assert [usage.total_input_tokens for usage in payloads(events, Usage)] == [100, 50]


def test_successful_raw_patch_yields_edits_only_after_confirmed_result():
    patch = (
        "*** Begin Patch\n*** Add File: one.py\n+hello\n"
        "*** Update File: two.py\n@@\n-old\n+new\n*** End Patch"
    )
    records = [
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "ok",
                "input": patch,
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "ok",
                "output": "Exit code: 0\nOutput:\nSuccess.",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "bad",
                "input": patch,
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "bad",
                "output": "Exit code: 1\nOutput:\nFailed.",
            },
        },
    ]
    events = read(records)
    assert all(not call.edits for call in payloads(events, ToolCall))
    good, bad = payloads(events, ToolResult)
    assert [(edit.file_path, edit.added, edit.removed) for edit in good.edits] == [
        ("one.py", ["hello"], []),
        ("two.py", ["new"], ["old"]),
    ]
    assert bad.is_error and not bad.edits


def test_raw_patch_json_metadata_confirms_success():
    patch = "*** Begin Patch\n*** Add File: empty.py\n*** End Patch"
    events = read(
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "call_id": "c",
                    "input": patch,
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "c",
                    "output": json.dumps({"metadata": {"exit_code": 0}, "output": "Success."}),
                },
            },
        ]
    )
    assert [(edit.file_path, edit.added) for edit in payloads(events, ToolResult)[0].edits] == [
        ("empty.py", [])
    ]


def test_completed_empty_add_delete_and_move_keep_both_paths():
    events = read(
        [
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "FileChange",
                        "id": "edit",
                        "status": "completed",
                        "changes": {
                            "empty.py": {"type": "add", "content": ""},
                            "gone.py": {"type": "delete"},
                            "old.py": {
                                "type": "update",
                                "move_path": "new.py",
                                "unified_diff": "@@ -1 +1 @@\n-old\n+new",
                            },
                        },
                    },
                },
            }
        ]
    )
    edits = payloads(events, ToolCall)[0].edits
    assert [edit.file_path for edit in edits] == ["empty.py", "gone.py", "old.py", "new.py"]
    assert edits[2].removed == ["old"] and edits[3].added == ["new"]


def test_missing_response_id_uses_same_fallback_for_tools_and_usage():
    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t"}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "CommandExecution",
                        "id": "c",
                        "command": "pytest",
                        "status": "completed",
                    },
                },
            },
            {
                "type": "token_usage_record",
                "payload": {"turn_id": "t", "usage": {"input_tokens": 10, "output_tokens": 2}},
            },
        ]
    )
    assert events[1].message_id == events[2].message_id
    assert events[2].message_id


def test_new_inner_usage_shape_and_unknown_status_are_visible():
    events = read(
        [
            {
                "type": "token_usage_record",
                "payload": {"turn_id": "t", "tokens": {"input_tokens": 10}},
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {"type": "FileChange", "status": "mysterious", "changes": {}},
                },
            },
        ]
    )
    assert all(not event.known_type and event.key_shape for event in events)


def test_discovery_reads_bounded_head_and_tail(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    path = home / "sessions" / "2026" / "09" / "23" / "rollout-large.jsonl"
    path.parent.mkdir(parents=True)
    head = (
        json.dumps(
            {
                "type": "session_meta",
                "timestamp": "2026-09-23T00:00:00Z",
                "payload": {"id": "large", "cwd": "/repo"},
            }
        ).encode()
        + b"\n"
    )
    tail = (
        b'{"timestamp":"2026-09-23T01:00:00Z","type":"event_msg",'
        b'"payload":{"type":"task_complete"}}\n'
    )
    path.write_bytes(head + b" " * (2 * 1024 * 1024) + b"\n" + tail)
    import prudence.sources.codex as codex_module

    real_open = Path.open
    read_bytes = 0

    class CountingFile:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def read(self, size=-1):
            nonlocal read_bytes
            data = self.handle.read(size)
            read_bytes += len(data)
            return data

        def __getattr__(self, name):
            return getattr(self.handle, name)

    monkeypatch.setattr(
        Path, "open", lambda self, *a, **kw: CountingFile(real_open(self, *a, **kw))
    )
    found = codex_module.Codex(home).session_files()
    assert found[0].session_id == "codex:large"
    assert found[0].last_at.hour == 1
    assert read_bytes <= 128 * 1024


def test_legacy_usage_is_response_boundary_for_preceding_tool():
    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t", "model": "m"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c",
                    "arguments": json.dumps({"cmd": "pytest"}),
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 20, "output_tokens": 2}},
                },
            },
        ]
    )
    assert events[1].message_id == events[2].message_id
    assert events[1].message_id == "codex:session:legacy:200"


def test_wrapper_without_observed_inner_action_marks_response_gap():
    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "functions.exec",
                    "call_id": "w",
                    "arguments": "{}",
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "w", "output": "done"},
            },
            {
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t",
                    "response_id": "r",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            },
        ]
    )
    assert not payloads(events, ToolCall)
    assert events[1].response_gap
    assert events[1].message_id == events[3].message_id


def test_fork_metadata_exposes_unresolved_lineage():
    events = read(
        [{"type": "session_meta", "payload": {"id": "child", "forked_from_id": "parent"}}]
    )
    assert not events[0].known_type
    assert "payload.forked_from_id" in events[0].key_shape
    assert events[0].parent_id is None


def test_legacy_counter_reset_counts_new_segment_from_zero():
    def count(total, output, cached):
        usage = {"input_tokens": total, "output_tokens": output, "cached_input_tokens": cached}
        return {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": usage, "last_token_usage": usage},
            },
        }

    events = read([count(1853972, 12468, 1711104), count(146268, 1562, 140032)])
    assert [u.total_input_tokens for u in payloads(events, Usage)] == [1853972, 146268]
    assert [u.output_tokens for u in payloads(events, Usage)] == [12468, 1562]


def test_equal_usage_tuples_match_nearest_legacy_response():
    def command(call_id, text):
        return {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": call_id,
                "arguments": json.dumps({"cmd": text}),
            },
        }

    def count(total):
        return {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"input_tokens": total, "output_tokens": total // 10}
                },
            },
        }

    events = read(
        [
            {"type": "turn_context", "payload": {"turn_id": "t"}},
            command("first", "pytest"),
            count(100),
            command("second", "git commit -m x"),
            count(200),
            {
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t",
                    "response_id": "second",
                    "usage": {"input_tokens": 100, "output_tokens": 10},
                },
            },
        ]
    )
    assert [u.total_input_tokens for u in payloads(events, Usage)] == [100, 100]
    assert events[1].message_id == events[2].message_id == "codex:session:legacy:200"
    assert events[3].message_id == events[4].message_id == events[5].message_id
    assert events[5].message_id == "codex:session:second"
