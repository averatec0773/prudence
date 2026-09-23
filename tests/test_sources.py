"""The boundary between an agent's format and the store, and the events that cross it."""

from __future__ import annotations

import json
from pathlib import Path

from prudence import sources
from prudence.sources import base
from prudence.sources.claude_code import events as claude_events

STORE = Path(__file__).resolve().parents[1] / "src" / "prudence" / "store"


def _lines(records: list[dict]) -> list[tuple[int, bytes]]:
    return [(index, json.dumps(record).encode()) for index, record in enumerate(records)]


def test_no_store_module_imports_an_agent() -> None:
    """The store builds tables from events; which agent wrote them is the registry's business.

    The check is on imports rather than on the word, because a column name
    (`unknown_record_type.claude_version`) and a directory layout
    (`store/repos.py`'s Claude Desktop worktrees) legitimately name the agent that
    produced them. Reaching into an agent's module is what must not happen.
    """
    importers = [
        path.name
        for path in sorted(STORE.rglob("*.py"))
        if "sources.claude_code" in path.read_text()
        or "sources import claude_code" in path.read_text()
    ]
    assert importers == [], f"these store modules import an agent: {importers}"


def test_the_registry_answers_with_one_adapter_today() -> None:
    assert sources.source().kind == sources.DEFAULT_KIND
    assert list(sources.SOURCES) == [sources.DEFAULT_KIND]


def test_an_event_carries_the_session_the_record_declares_not_the_file_it_was_read_from() -> None:
    """A fork copies its parent's records, parent's `sessionId` and all."""
    records = [
        {"type": "user", "uuid": "p1", "sessionId": "parent", "timestamp": "2026-09-01T10:00:00Z"},
        {"type": "user", "uuid": "f1", "sessionId": "fork", "timestamp": "2026-09-02T10:00:00Z"},
    ]
    read = list(claude_events.events(_lines(records), "/tmp/fork.jsonl", "fork", None))
    assert [event.session_id for event in read] == ["parent", "fork"]
    assert all(event.stable_id for event in read)


def test_a_record_with_no_identifier_of_its_own_gets_one_and_says_so() -> None:
    records = [{"type": "file-history-snapshot", "sessionId": "s1"}]
    read = list(claude_events.events(_lines(records), "/tmp/s1.jsonl", "s1", None))
    assert read[0].stable_id is False, "an id derived from the file position is not stable"
    assert read[0].record_id, "but there is always an id"
    assert read[0].known_type is False, "and the adapter says it did not recognise the type"


def test_a_prompt_crosses_as_its_length_and_a_tool_call_as_its_shape() -> None:
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s1",
            "message": {"role": "user", "content": [{"type": "text", "text": "fix the parser"}]},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "sessionId": "s1",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 11, "output_tokens": 3},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                    }
                ],
            },
        },
    ]
    read = list(claude_events.events(_lines(records), "/tmp/s1.jsonl", "s1", None))
    assert read[0].payloads == (base.Prompt(chars=len("fix the parser")),)
    usage, call = read[1].payloads
    assert isinstance(usage, base.Usage)
    assert (usage.input_tokens, usage.output_tokens) == (11, 3)
    assert usage.cache_read_tokens is None, "a count the format omits is absent, not zero"
    assert isinstance(call, base.ToolCall)
    assert call.tool_name == "Bash"
    assert call.command is not None and call.command.command_class == "test"
    assert call.shell_command == "pytest -q", "the whole command, for the bucket rule"
    assert read[1].message_id == "a1", "a reply with no id of its own is its own record"
    assert read[0].message_id is None, "a prompt is not part of a reply"


def test_the_adapter_says_which_subagent_files_are_logs_and_what_is_beside_them() -> None:
    root = "/p/s1/subagents"
    paths = [
        f"{root}/agent-a1.jsonl",
        f"{root}/agent-a1.meta.json",
        f"{root}/33333333-3333-4333-8333-333333333333.jsonl",
        f"{root}/workflows/wf_1/agent-a2.jsonl",
        f"{root}/workflows/wf_1/journal.jsonl",
    ]
    logs = sources.source().agent_logs(paths)
    assert [(log.agent_id, log.sidecar) for log in logs] == [
        ("33333333-3333-4333-8333-333333333333", None),
        ("a1", f"{root}/agent-a1.meta.json"),
        ("a2", None),
    ], "sidecars and a workflow's journal are not logs; the id loses its file prefix"


def test_a_subagent_is_linked_to_the_call_that_started_it() -> None:
    """By its sidecar, by the result's structured field, or by the result's last line."""
    sidecar = json.dumps({"agentType": "general-purpose", "toolUseId": "toolu_spawn"}).encode()
    child = [{"type": "assistant", "uuid": "c1", "message": {"id": "msg_c1", "content": []}}]
    read = list(claude_events.events(_lines(child), "/tmp/agent-a1.jsonl", "s1", "a1", sidecar))
    assert read[0].dispatch_id == "toolu_spawn"
    assert read[0].message_id == "msg_c1"

    parent = [
        _call("toolu_a", "Agent", {}),
        _result("toolu_a", "done", {"agentId": "a2", "status": "completed"}),
        _call("toolu_b", "Agent", {}),
        _result("toolu_b", "Done.\nagentId: a3333333333333333 (use SendMessage to continue)"),
        _call("toolu_s", "SendMessage", {"to": "a3333333333333333"}),
    ]
    read = list(claude_events.events(_lines(parent), "/tmp/s1.jsonl", "s1", None))
    started = [p.started_agent for e in read for p in e.payloads if isinstance(p, base.ToolResult)]
    assert started == ["a2", "a3333333333333333"]
    sent = [p.sends_to_agent for e in read for p in e.payloads if isinstance(p, base.ToolCall)]
    assert sent == [None, None, "a3333333333333333"]


def test_a_line_that_will_not_parse_is_counted_with_the_tokens_it_shows() -> None:
    """The coverage gap: kept, counted, and never given a bucket."""
    cut = b'{"type":"assistant","message":{"usage":{"input_tokens":7,"output_tokens":90'
    read = list(claude_events.events([(0, cut), (80, b"   ")], "/tmp/s1.jsonl", "s1", None))
    assert len(read) == 1, "a blank line is not a record"
    assert read[0].record_type == "unreadable" and read[0].known_type is False
    assert read[0].message_id is None
    (usage,) = read[0].payloads
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (7, 90, None)


def _call(call_id: str, name: str, payload: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": f"use-{call_id}",
        "message": {
            "id": f"msg-{call_id}",
            "content": [{"type": "tool_use", "id": call_id, "name": name, "input": payload}],
        },
    }


def _result(call_id: str, text: str, outcome: dict | None = None) -> dict:
    record: dict = {
        "type": "user",
        "uuid": f"result-{call_id}",
        "message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": text}]},
    }
    if outcome is not None:
        record["toolUseResult"] = outcome
    return record
