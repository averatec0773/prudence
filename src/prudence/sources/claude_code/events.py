"""Claude Code's transcript lines, read as events. The only module that knows the format.

One line of a transcript is one JSON record. What the store needs out of it is here and
nowhere else: which record it is, which session it says it belongs to, what type it
carries, and whichever of a prompt, a response's token usage, a tool call and a tool
result it happens to hold.

Three of Claude Code's habits shape this module.

A record's identity is its `uuid`, but many record types carry none (about a quarter of
the founder's lines), so those get an id derived from the file and the byte offset and
are marked `stable_id=False`: unique, but a different name for the same record in every
file that copies it.

A tool call and its result are two records some distance apart, and only the call names
the tool. The result's own reading of what changed (`structuredPatch`) is the better one,
and reading it needs the tool name, so the names seen in this file are remembered while
it is read. The store still owns the pairing, because a call and its result can be in
different files.

The format is internal to Claude Code and changed 24 times in five months on the
founder's machine, so nothing here fails on a surprise: an unparseable line is skipped,
an unknown record type is reported as `known_type=False` and otherwise treated as a
plain record, and a field of the wrong shape is simply absent.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator

from prudence.sources.base import (
    Event,
    FileHead,
    Payload,
    Prompt,
    ToolCall,
    ToolResult,
    Usage,
)
from prudence.store import edits as edits_module

# Record types this version understands. Anything else is reported as unknown, counted
# by the store, and otherwise treated as a plain record.
KNOWN_RECORD_TYPES = frozenset({"user", "assistant", "system", "attachment"})

# What a line that is not a JSON object becomes: a record type of its own, which the store
# counts like any other type it does not know.
UNREADABLE = "unreadable"

# The usage keys of a reply, and the `Usage` field each one fills.
_USAGE_KEYS = {
    "input_tokens": b"input_tokens",
    "output_tokens": b"output_tokens",
    "cache_read_tokens": b"cache_read_input_tokens",
    "cache_creation_tokens": b"cache_creation_input_tokens",
}
_UNREADABLE_COUNTS = re.compile(
    rb'"(input_tokens|output_tokens|cache_read_input_tokens|cache_creation_input_tokens)":(\d+)'
)

# The tools that start a subagent, and the one that hands a running one more work.
DISPATCH_TOOLS = frozenset({"Agent", "Task"})
SEND_TOOL = "SendMessage"
# The line a dispatching call's result ends with when the structured field is missing.
_AGENT_LINE = re.compile(r"agentId:\s*([0-9A-Za-z-]{6,64})")

# Tool inputs whose file path is a fact worth keeping. Whether it is stored is the
# store's decision, not this module's: `metadata-only` keeps no paths.
PATH_TOOLS = frozenset({"Edit", "Write", "Read", "NotebookEdit"})


def head(lines: Iterable[bytes]) -> FileHead:
    """When a transcript starts and where it ran, from its first records alone."""
    found = FileHead()
    for line in lines:
        record = parse(line)
        if record is None:
            continue
        if found.first_at is None:
            found.first_at = _string_or_none(record.get("timestamp"))
        if found.cwd is None:
            found.cwd = _string_or_none(record.get("cwd"))
        if found.git_branch is None:
            found.git_branch = _string_or_none(record.get("gitBranch"))
        if found.first_at and found.cwd and found.git_branch:
            break
    return found


def events(
    lines: Iterable[tuple[int, bytes]],
    path: str,
    file_session_id: str,
    agent_id: str | None,
    sidecar: bytes | None = None,
) -> Iterator[Event]:
    """One event per record of one archived transcript, in file order.

    A line that is not a JSON object is reported as a record of type `unreadable`,
    carrying the token counts that can still be read off its bytes, so that the tokens it
    spent are counted and shown as a gap rather than silently lost.
    """
    tool_names: dict[str, str] = {}
    dispatch_id = _dispatch(sidecar)
    for offset, line in lines:
        record = parse(line)
        if record is None:
            if line.strip():
                yield _unreadable(line, path, offset, agent_id)
            continue
        record_type = record.get("type")
        if not isinstance(record_type, str):
            record_type = "unknown"
        uuid = record.get("uuid")
        stable_id = isinstance(uuid, str) and bool(uuid)
        record_id = uuid if stable_id else _derived_id(path, offset)
        yield Event(
            record_id=record_id,
            stable_id=stable_id,
            session_id=_text_or_none(record.get("sessionId")),
            parent_id=_string_or_none(record.get("parentUuid")),
            timestamp=_string_or_none(record.get("timestamp")),
            record_type=record_type,
            known_type=record_type in KNOWN_RECORD_TYPES,
            subtype=_subtype(record),
            source_version=_string_or_none(record.get("version")),
            sidechain=bool(record.get("isSidechain")),
            agent_id=agent_id or _text_or_none(record.get("agentId")),
            prompt_id=_text_or_none(record.get("promptId")),
            cwd=_string_or_none(record.get("cwd")),
            entrypoint=_string_or_none(record.get("entrypoint")),
            message_id=_message_id(record, record_id),
            dispatch_id=dispatch_id,
            payloads=_payloads(record, tool_names),
        )


def parse(line: bytes) -> dict | None:
    """One line as a record, or None when it is not a JSON object at all."""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _payloads(record: dict, tool_names: dict[str, str]) -> tuple[Payload, ...]:
    found: list[Payload] = []
    if _is_user_prompt(record):
        found.append(Prompt(chars=_prompt_chars(record)))
    usage = _usage(record)
    if usage is not None:
        found.append(usage)
    found.extend(_tool_payloads(record, tool_names))
    return tuple(found)


def _derived_id(path: str, offset: int) -> str:
    return hashlib.sha256(f"{path}:{offset}".encode()).hexdigest()


def _message_id(record: dict, record_id: str) -> str | None:
    """The reply an assistant record is part of: `message.id`, else `requestId`, else itself.

    Claude Code writes one record per content block of a reply (a text block, each tool
    call), all under one `message.id`; an old version wrote no id at all, and then the
    record is a reply of its own.
    """
    if record.get("type") != "assistant":
        return None
    message = record.get("message")
    found = message.get("id") if isinstance(message, dict) else None
    return _text_or_none(found) or _text_or_none(record.get("requestId")) or record_id


def _dispatch(sidecar: bytes | None) -> str | None:
    """The tool call that started a subagent, from the `meta.json` beside its log."""
    if sidecar is None:
        return None
    meta = parse(sidecar)
    return _text_or_none(meta.get("toolUseId")) if meta is not None else None


def _unreadable(line: bytes, path: str, offset: int, agent_id: str | None) -> Event:
    """A line that would not parse: counted, with whatever token counts its bytes show.

    Reading numbers off an unparsed line is a guess about a record nobody can read, so
    the counts go no further than the coverage gap every surface reports.
    """
    counts = dict(_UNREADABLE_COUNTS.findall(line))
    usage = None
    if counts:
        usage = Usage(
            request_id=None,
            model=None,
            **{
                field: int(counts[key]) if key in counts else None
                for field, key in _USAGE_KEYS.items()
            },
        )
    return Event(
        record_id=_derived_id(path, offset),
        stable_id=False,
        session_id=None,
        parent_id=None,
        timestamp=None,
        record_type=UNREADABLE,
        known_type=False,
        agent_id=agent_id,
        payloads=(usage,) if usage is not None else (),
    )


def _usage(record: dict) -> Usage | None:
    """What one API response cost, from the assistant record that carries `message.usage`.

    A version that writes no usage at all is not an error: it simply yields no payload,
    and every surface shows the absence rather than a zero.
    """
    if record.get("type") != "assistant":
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return Usage(
        request_id=_text_or_none(record.get("requestId")),
        model=_text_or_none(message.get("model")),
        input_tokens=_token_count(usage, "input_tokens"),
        output_tokens=_token_count(usage, "output_tokens"),
        cache_read_tokens=_token_count(usage, "cache_read_input_tokens"),
        cache_creation_tokens=_token_count(usage, "cache_creation_input_tokens"),
    )


def _token_count(usage: dict, key: str) -> int | None:
    """A token count, or None when this version of the format does not carry that key."""
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _tool_payloads(record: dict, tool_names: dict[str, str]) -> list[Payload]:
    """The tool calls and tool results one record's content blocks hold.

    An edit is read from the call's input as soon as the call is seen, and read again
    from the result's `structuredPatch` when one arrives, because the attribution spike
    measured that a quarter of edit results never arrive at all.
    """
    outcome = record.get("toolUseResult")
    found: list[Payload] = []
    for block in _content_blocks(record):
        kind = block.get("type")
        if kind == "tool_use":
            call_id = block.get("id")
            if not isinstance(call_id, str):
                continue
            payload = block.get("input") if isinstance(block.get("input"), dict) else {}
            name = _string_or_none(block.get("name"))
            if name is not None:
                tool_names[call_id] = name
            found.append(
                ToolCall(
                    call_id=call_id,
                    tool_name=name,
                    file_path=_file_path(name, payload),
                    input_bytes=len(json.dumps(payload, ensure_ascii=False).encode()),
                    edit=edits_module.extract_edit(name, payload, None),
                    # The text is reported; `store/derived.py` decides whether it is kept.
                    command=edits_module.extract_command(name, payload, full=True),
                    shell_command=(
                        _string_or_none(payload.get("command"))
                        if name in edits_module.COMMAND_TOOLS
                        else None
                    ),
                    sends_to_agent=(
                        _text_or_none(payload.get("to")) if name == SEND_TOOL else None
                    ),
                )
            )
        elif kind == "tool_result":
            call_id = block.get("tool_use_id")
            if not isinstance(call_id, str):
                continue
            is_error = bool(block.get("is_error"))
            content = block.get("content")
            exit_code, commit_hash = edits_module.read_result(outcome)
            found.append(
                ToolResult(
                    call_id=call_id,
                    is_error=is_error,
                    result_bytes=(
                        len(json.dumps(content, ensure_ascii=False).encode()) if content else 0
                    ),
                    error_content=content if is_error and content is not None else None,
                    edit=edits_module.extract_edit(tool_names.get(call_id), {}, outcome),
                    exit_code=exit_code,
                    commit_hash=commit_hash,
                    started_agent=(
                        _started_agent(outcome, content)
                        if tool_names.get(call_id) in DISPATCH_TOOLS
                        else None
                    ),
                )
            )
    return found


def _started_agent(outcome: object, content: object) -> str | None:
    """The subagent a dispatching call's result names: the structured field, else the line.

    Recent versions put `agentId` on `toolUseResult`; the text of the result ends with an
    `agentId: ...` line in versions that do not.
    """
    if isinstance(outcome, dict) and _text_or_none(outcome.get("agentId")):
        return outcome["agentId"]
    if isinstance(content, list):
        content = " ".join(
            block.get("text") or ""
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    found = _AGENT_LINE.search(content) if isinstance(content, str) else None
    return found.group(1) if found else None


def _string_or_none(value: object) -> str | None:
    """The value when the format wrote a string there, empty string included."""
    return value if isinstance(value, str) else None


def _text_or_none(value: object) -> str | None:
    """The value when the format wrote a string with something in it: an id or a name."""
    return value if isinstance(value, str) and value else None


def _subtype(record: dict) -> str | None:
    subtype = record.get("subtype")
    if isinstance(subtype, str):
        return subtype
    message = record.get("message")
    if isinstance(message, dict) and isinstance(message.get("role"), str):
        return message["role"]
    return None


def _content_blocks(record: dict) -> list[dict]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _is_user_prompt(record: dict) -> bool:
    """A record the person typed, as opposed to a tool result wearing the user role."""
    if record.get("type") != "user":
        return False
    message = record.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    return any(block.get("type") == "text" for block in _content_blocks(record))


def _prompt_chars(record: dict) -> int:
    """How long the prompt was. A length is a measure; the text itself is never stored."""
    message = record.get("message")
    if not isinstance(message, dict):
        return 0
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    return sum(
        len(block.get("text", ""))
        for block in _content_blocks(record)
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    )


def _file_path(tool_name: str | None, payload: dict) -> str | None:
    if tool_name not in PATH_TOOLS:
        return None
    for key in ("file_path", "notebook_path", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
