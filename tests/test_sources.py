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
