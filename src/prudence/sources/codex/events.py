"""Normalize Codex rollout records into the source event contract."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Iterable, Iterator

from prudence.sources.base import (
    UNREADABLE,
    Event,
    FileHead,
    Prompt,
    ToolCall,
    ToolResult,
    Usage,
    key_shape,
)
from prudence.store.edits import CommandFacts, EditFacts, classify_command

KNOWN = frozenset(
    {
        "session_meta",
        "turn_context",
        "response_item",
        "event_msg",
        "token_usage_record",
        "compacted",
        "world_state",
        "inter_agent_communication_metadata",
    }
)
KNOWN_EVENT_MSG = frozenset(
    {
        "item_completed",
        "token_count",
        "task_started",
        "task_complete",
        "turn_aborted",
        "user_message",
        "agent_message",
        "thread_settings_applied",
    }
)
KNOWN_ITEMS = frozenset(
    {
        "UserMessage",
        "AgentMessage",
        "Reasoning",
        "WebSearch",
        "CommandExecution",
        "FileChange",
        "McpToolCall",
        "DynamicToolCall",
        "ContextCompaction",
        "ImageView",
        "Extension",
        "SubAgentActivity",
        "CollabAgentToolCall",
    }
)
KNOWN_RESPONSE_ITEMS = frozenset(
    {
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "web_search_call",
        "tool_search_call",
        "tool_search_output",
        "agent_message",
    }
)
WRAPPERS = frozenset(
    {
        "functions.exec",
        "functions.wait",
        "exec",
        "wait",
        "write_stdin",
        "mcp__codex_app__read_thread_terminal",
    }
)
COMMANDS = frozenset({"exec_command", "functions.exec_command", "shell_command"})
_HUNK = re.compile(r"^@@")


def session_id(native: str) -> str:
    return native if native.startswith("codex:") else f"codex:{native}"


def scoped(native: object, session: str) -> str | None:
    if not isinstance(native, str) or not native:
        return None
    return native if native.startswith("codex:") else f"{session}:{native}"


def _derived_id(session: str, offset: int) -> str:
    return hashlib.sha256(f"{session}:{offset}".encode()).hexdigest()


def parse(line: bytes) -> dict | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def head(lines: Iterable[bytes]) -> FileHead:
    found = FileHead()
    for line in lines:
        record = parse(line)
        if record is None:
            continue
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        found.first_at = found.first_at or _str(record.get("timestamp"))
        found.cwd = found.cwd or _str(payload.get("cwd"))
        if found.first_at and found.cwd:
            break
    return found


def events(
    lines: Iterable[tuple[int, bytes]],
    path: str,
    file_session_id: str,
    agent_id: str | None,
    sidecar: bytes | None = None,
) -> Iterator[Event]:
    session = session_id(file_session_id)
    rows = [(offset, bool(line.strip()), parse(line)) for offset, line in lines]
    modern_records = []
    row_turns = []
    scan_turn = None
    for _, _, record in rows:
        if record is None:
            row_turns.append(scan_turn)
            continue
        payload = _dict(record.get("payload"))
        if record.get("type") == "turn_context":
            scan_turn = _str(payload.get("turn_id")) or scan_turn
        row_turns.append(scan_turn)
        if record.get("type") == "token_usage_record":
            modern_records.append(
                (
                    len(row_turns) - 1,
                    _str(payload.get("turn_id")) or scan_turn,
                    _dict(payload.get("usage")),
                    scoped(payload.get("response_id"), session)
                    or _derived_id(session, rows[len(row_turns) - 1][0]),
                )
            )
    legacy_usages, matched_legacy = _legacy_usage_by_index(rows, row_turns, modern_records, session)
    response_for = {}
    next_response = None
    next_turn = None
    for index in range(len(rows) - 1, -1, -1):
        record = rows[index][2]
        row_turn = row_turns[index]
        if row_turn != next_turn:
            next_response = None
            next_turn = row_turn
        if record is not None and record.get("type") == "token_usage_record":
            payload = _dict(record.get("payload"))
            next_response = scoped(payload.get("response_id"), session) or _derived_id(
                session, rows[index][0]
            )
        elif index in matched_legacy:
            next_response = matched_legacy[index]
        elif index in legacy_usages:
            next_response = legacy_usages[index].request_id
        response_for[index] = next_response
    direct_calls = {}
    for _, _, record in rows:
        if record is None or record.get("type") != "response_item":
            continue
        payload = _dict(record.get("payload"))
        if payload.get("type") not in {"function_call", "custom_tool_call"}:
            continue
        name = _str(payload.get("name"))
        call_id = scoped(payload.get("call_id"), session)
        if name and call_id and name not in WRAPPERS:
            raw = (
                payload.get("arguments")
                if payload.get("type") == "function_call"
                else payload.get("input")
            )
            args = _dict(raw) if isinstance(raw, dict) else _dict(_json(raw))
            direct_calls[call_id] = (
                name,
                _command_text(args.get("cmd") or args.get("command")),
                _str(payload.get("namespace")),
                raw if isinstance(raw, str) else None,
            )
    suppressed_raw, suppressed_call_ids = _paired_raw(rows, row_turns, session)
    unobserved_wrappers = _unobserved_wrappers(rows, row_turns)
    cwd = model = turn = native_session = version = None
    for index, (offset, nonempty, record) in enumerate(rows):
        rid = _derived_id(session, offset)
        if record is None:
            if nonempty:
                yield Event(
                    rid,
                    False,
                    session,
                    None,
                    None,
                    UNREADABLE,
                    False,
                    agent_id=agent_id,
                    offset=offset,
                )
            continue
        typ = record.get("type") if isinstance(record.get("type"), str) else "unknown"
        payload = _dict(record.get("payload"))
        stamp = _str(record.get("timestamp"))
        outputs = []
        response = None
        if typ == "session_meta":
            native_session = _str(payload.get("id")) or _str(payload.get("session_id"))
            cwd = _str(payload.get("cwd")) or cwd
            version = _str(payload.get("cli_version")) or version
        elif typ == "turn_context":
            turn = _str(payload.get("turn_id")) or turn
            cwd = _str(payload.get("cwd")) or cwd
            model = _str(payload.get("model")) or model
        elif typ == "token_usage_record":
            usage = _usage(
                _dict(payload.get("usage")), scoped(payload.get("response_id"), session), model
            )
            if usage is not None:
                outputs.append(usage)
                response = usage.request_id or rid
        elif typ == "event_msg":
            subtype = payload.get("type")
            if subtype == "user_message" and isinstance(payload.get("message"), str):
                outputs.append(Prompt(len(payload["message"])))
            elif subtype == "item_completed":
                item = _dict(payload.get("item"))
                if item.get("type") == "UserMessage":
                    chars = _content_chars(item.get("content"))
                    if chars is not None:
                        outputs.append(Prompt(chars))
                else:
                    outputs.extend(_completed(item, rid, session))
            elif subtype == "token_count":
                usage = legacy_usages.get(index)
                if usage is not None:
                    outputs.append(usage)
                    response = usage.request_id
                elif index in matched_legacy:
                    response = matched_legacy[index]
        elif typ == "response_item":
            outputs.extend(
                _response_item(
                    payload,
                    rid,
                    session,
                    index,
                    suppressed_raw,
                    suppressed_call_ids,
                    direct_calls,
                )
            )
        if response is None and any(isinstance(value, (ToolCall, ToolResult)) for value in outputs):
            response = response_for[index]
        if index in unobserved_wrappers:
            response = response_for[index]
        known = _known(typ, payload)
        yield Event(
            record_id=rid,
            stable_id=False,
            session_id=session_id(native_session) if native_session else session,
            parent_id=None,
            timestamp=stamp,
            record_type=typ,
            known_type=known,
            subtype=_str(payload.get("type")),
            source_version=version,
            agent_id=agent_id,
            prompt_id=(
                scoped(_str(payload.get("turn_id")) or turn, session)
                if any(isinstance(value, Prompt) for value in outputs)
                else None
            ),
            cwd=cwd,
            message_id=response,
            payloads=tuple(outputs),
            offset=offset,
            key_shape=() if known else key_shape(record),
            response_gap=index in unobserved_wrappers and response is not None,
        )


def _response_item(
    payload: dict,
    rid: str,
    session: str,
    index: int,
    suppressed_raw: set[int],
    suppressed_call_ids: set[str],
    direct_calls: dict[str, tuple[str, object, str | None, str | None]],
) -> list:
    typ = payload.get("type")
    if typ in {"function_call", "custom_tool_call"}:
        name = _str(payload.get("name"))
        if not name or name in WRAPPERS or index in suppressed_raw:
            return []
        raw = payload.get("arguments") if typ == "function_call" else payload.get("input")
        args = _dict(raw) if isinstance(raw, dict) else _dict(_json(raw))
        call_id = scoped(payload.get("call_id"), session) or rid
        if name in COMMANDS:
            command = _command_text(args.get("cmd") or args.get("command"))
            if not command:
                return []
            fact = CommandFacts(classify_command(command), command_text=command[:2000])
            return [
                ToolCall(
                    call_id, "CommandExecution", None, len(str(raw).encode()), None, fact, command
                )
            ]
        return [ToolCall(call_id, name, None, len(str(raw).encode()), None, None)]
    if typ in {"function_call_output", "custom_tool_call_output"}:
        call_id = scoped(payload.get("call_id"), session)
        details = direct_calls.get(call_id) if call_id else None
        if not details:
            return []
        name, _, _, raw = details
        if call_id in suppressed_call_ids:
            return []
        output = payload.get("output")
        structured = _dict(output) if isinstance(output, dict) else _dict(_json(output))
        exit_code = _result_exit_code(output, structured)
        failed = structured.get("isError") is True or (exit_code is not None and exit_code != 0)
        edits = (
            tuple(_patch_edits(raw))
            if name in {"apply_patch", "functions.apply_patch"}
            and raw is not None
            and not failed
            and _patch_succeeded(output, exit_code)
            else ()
        )
        return [
            ToolResult(
                call_id,
                failed,
                len(str(output).encode()),
                output if failed else None,
                None,
                exit_code,
                None,
                edits=edits,
            )
        ]
    return []


def _completed(item: dict, rid: str, session: str) -> list:
    typ = item.get("type")
    status = item.get("status")
    call_id = scoped(item.get("id"), session) or rid
    if typ == "CommandExecution":
        command = _command_text(item.get("command"))
        if not command or status not in ("completed", "failed"):
            return []
        exit_code = _number(item.get("exit_code"))
        call = ToolCall(
            call_id,
            typ,
            None,
            0,
            None,
            CommandFacts(classify_command(command), command_text=command[:2000]),
            command,
        )
        result = ToolResult(
            call_id,
            status == "failed" or (exit_code is not None and exit_code != 0),
            0,
            None,
            None,
            exit_code,
            None,
        )
        return [call, result]
    if typ == "FileChange":
        if status != "completed":
            return []
        edits = tuple(_edits(_dict(item.get("changes"))))
        if not edits:
            return []
        return [
            ToolCall(call_id, typ, None, 0, None, None, edits=edits),
            ToolResult(call_id, False, 0, None, None, None, None, edits=edits),
        ]
    if typ in {"McpToolCall", "DynamicToolCall"}:
        name = _str(item.get("tool"))
        if not name:
            return []
        return [
            ToolCall(call_id, name, None, 0, None, None),
            ToolResult(
                call_id,
                status not in (None, "completed") or item.get("success") is False,
                0,
                None,
                None,
                None,
                None,
            ),
        ]
    return []


def _edits(changes: dict) -> Iterator[EditFacts]:
    for path, change in changes.items():
        if not isinstance(path, str) or not isinstance(change, dict):
            continue
        kind = change.get("type")
        target = _str(change.get("move_path"))
        facts = EditFacts(file_path=path, is_new_file=kind == "add")
        if kind == "add" and isinstance(change.get("content"), str):
            facts.added = change["content"].splitlines()
        elif kind == "delete" and isinstance(change.get("content"), str):
            facts.removed = change["content"].splitlines()
        elif kind == "update" and isinstance(change.get("unified_diff"), str):
            for line in change["unified_diff"].splitlines():
                if line.startswith(("+++", "---")) or _HUNK.match(line):
                    continue
                if line.startswith("+"):
                    facts.added.append(line[1:])
                elif line.startswith("-"):
                    facts.removed.append(line[1:])
        if target:
            yield EditFacts(removed=facts.removed, file_path=path)
            yield EditFacts(added=facts.added, file_path=target)
        else:
            yield facts


def _patch_edits(patch: str) -> Iterator[EditFacts]:
    if not patch.startswith("*** Begin Patch"):
        return
    kind = path = move = None
    added: list[str] = []
    removed: list[str] = []

    def completed() -> Iterator[EditFacts]:
        if path is None:
            return
        if move:
            yield EditFacts(removed=removed, file_path=path)
            yield EditFacts(added=added, file_path=move)
        else:
            yield EditFacts(added=added, removed=removed, is_new_file=kind == "add", file_path=path)

    for line in patch.splitlines()[1:]:
        marker = next(
            (
                name
                for name in ("Add File", "Update File", "Delete File")
                if line.startswith(f"*** {name}: ")
            ),
            None,
        )
        if marker:
            yield from completed()
            kind = marker.split()[0].lower()
            path = line.split(": ", 1)[1]
            move = None
            added = []
            removed = []
        elif line.startswith("*** Move to: "):
            move = line.removeprefix("*** Move to: ")
        elif line == "*** End Patch":
            break
        elif path is not None and not line.startswith(("***", "@@")):
            if line.startswith("+"):
                added.append(line[1:])
            elif line.startswith("-"):
                removed.append(line[1:])
    yield from completed()


def _result_exit_code(output: object, structured: dict) -> int | None:
    metadata = _dict(structured.get("metadata"))
    for value in (metadata.get("exit_code"), structured.get("exit_code")):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    if isinstance(output, str):
        match = re.match(r"^Exit code: (-?\d+)\b", output)
        if match:
            return int(match.group(1))
    return None


def _patch_succeeded(output: object, exit_code: int | None) -> bool:
    return exit_code == 0 or (
        exit_code is None and isinstance(output, str) and output.startswith("Success.")
    )


def _usage(raw: dict, request: str | None, model: str | None) -> Usage | None:
    total = _number(raw.get("input_tokens"))
    output = _number(raw.get("output_tokens"))
    cached = _number(raw.get("cached_input_tokens"))
    created = _number(raw.get("cache_write_input_tokens"))
    reasoning = _number(raw.get("reasoning_output_tokens"))
    if total is None and output is None:
        return None
    uncached = (
        total - cached - created
        if total is not None
        and cached is not None
        and created is not None
        and total >= cached + created
        else None
    )
    return Usage(request, model, uncached, output, cached, created, total, reasoning)


def _usage_fingerprint(raw: dict) -> tuple:
    return tuple(
        _number(raw.get(key))
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
    )


def _usage_matches(modern: dict, legacy: dict) -> bool:
    if any(
        _number(modern.get(key)) != _number(legacy.get(key))
        for key in ("input_tokens", "output_tokens")
    ):
        return False
    return not any(
        _number(modern.get(key)) != _number(legacy.get(key))
        for key in ("cached_input_tokens", "cache_write_input_tokens")
        if _number(modern.get(key)) is not None and _number(legacy.get(key)) is not None
    )


def _counter_delta(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return current
    if any(
        _number(value) is not None
        and _number(previous.get(key)) is not None
        and value < previous[key]
        for key, value in current.items()
    ):
        return current
    return {
        key: value - previous[key]
        for key, value in current.items()
        if _number(value) is not None and _number(previous.get(key)) is not None
    }


def _legacy_usage_by_index(
    rows: list[tuple[int, bool, dict | None]],
    row_turns: list[str | None],
    modern_records: list[tuple[int, str | None, dict, str]],
    session: str,
) -> tuple[dict[int, Usage], dict[int, str]]:
    candidates = []
    previous_total = None
    model = None
    for index, (offset, _, record) in enumerate(rows):
        if record is None:
            continue
        payload = _dict(record.get("payload"))
        if record.get("type") == "turn_context":
            model = _str(payload.get("model")) or model
        if record.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        total = _dict(_dict(payload.get("info")).get("total_token_usage"))
        if not total:
            continue
        delta = _counter_delta(previous_total, total)
        previous_total = total
        if not any(delta.values()):
            continue
        turn = _str(payload.get("turn_id")) or row_turns[index]
        candidates.append((index, offset, turn, model, delta))
    matched = {}
    for modern_index, modern_turn, modern_usage, response_id in modern_records:
        options = [
            candidate
            for candidate in candidates
            if candidate[0] not in matched
            and candidate[2] == modern_turn
            and _usage_matches(modern_usage, candidate[4])
        ]
        if options:
            closest = min(
                options,
                key=lambda candidate: (
                    abs(candidate[0] - modern_index),
                    candidate[0] > modern_index,
                ),
            )
            matched[closest[0]] = response_id
    usages = {}
    for index, offset, _, model, delta in candidates:
        if index in matched:
            continue
        usage = _usage(delta, scoped(f"legacy:{offset}", session), model)
        if usage is not None:
            usages[index] = usage
    return usages, matched


def _unobserved_wrappers(
    rows: list[tuple[int, bool, dict | None]], row_turns: list[str | None]
) -> set[int]:
    output_at = {}
    for index, (_, _, record) in enumerate(rows):
        if record is None or record.get("type") != "response_item":
            continue
        payload = _dict(record.get("payload"))
        if payload.get("type") in {"function_call_output", "custom_tool_call_output"}:
            call_id = _str(payload.get("call_id"))
            if call_id:
                output_at[call_id] = index
    gaps = set()
    for index, (_, _, record) in enumerate(rows):
        if record is None or record.get("type") != "response_item":
            continue
        payload = _dict(record.get("payload"))
        if payload.get("type") not in {"function_call", "custom_tool_call"}:
            continue
        if payload.get("name") not in {"functions.exec", "exec"}:
            continue
        end = output_at.get(_str(payload.get("call_id")), len(rows))
        observed = False
        for inner_index in range(index + 1, end):
            inner = rows[inner_index][2]
            if inner is None or row_turns[inner_index] != row_turns[index]:
                break
            inner_payload = _dict(inner.get("payload"))
            item = _dict(inner_payload.get("item"))
            if (
                inner.get("type") == "event_msg"
                and inner_payload.get("type") == "item_completed"
                and item.get("type")
                in {"CommandExecution", "FileChange", "McpToolCall", "DynamicToolCall"}
            ):
                observed = True
                break
        if not observed:
            gaps.add(index)
    return gaps


def _content_chars(content: object) -> int | None:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return None


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _json(value: object) -> object:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _command_text(value: object) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list) and value and all(isinstance(part, str) for part in value):
        if len(value) >= 3 and value[-2] in {"-c", "-lc"}:
            return value[-1]
        return shlex.join(value)
    return None


def _normalize_tool(name: str) -> str:
    return name.replace(" ", "_").replace(".", "_")


def _known(typ: str, payload: dict) -> bool:
    if typ not in KNOWN:
        return False
    if typ == "session_meta" and ("history_base" in payload or "forked_from_id" in payload):
        return False
    if typ == "token_usage_record":
        return _usage(_dict(payload.get("usage")), None, None) is not None
    if typ == "event_msg":
        subtype = payload.get("type")
        if subtype not in KNOWN_EVENT_MSG:
            return False
        if subtype == "token_count":
            total = _dict(_dict(payload.get("info")).get("total_token_usage"))
            return _usage(total, None, None) is not None
        if subtype == "item_completed":
            item = _dict(payload.get("item"))
            if item.get("type") not in KNOWN_ITEMS:
                return False
            if item.get("type") == "UserMessage":
                return _content_chars(item.get("content")) is not None
            if item.get("type") == "CommandExecution":
                return (
                    item.get("status") in {"completed", "failed"}
                    and _command_text(item.get("command")) is not None
                )
            if item.get("type") == "FileChange":
                return item.get("status") in {"declined", "failed"} or (
                    item.get("status") == "completed" and isinstance(item.get("changes"), dict)
                )
            if item.get("type") in {"McpToolCall", "DynamicToolCall"}:
                return (
                    item.get("status") in {"completed", "failed"}
                    and _str(item.get("tool")) is not None
                )
        return True
    if typ == "response_item":
        return payload.get("type") in KNOWN_RESPONSE_ITEMS
    return True


def _raw_tool_key(payload: dict) -> str | None:
    name = _str(payload.get("name"))
    if not name:
        return None
    namespace = _str(payload.get("namespace"))
    if namespace and namespace.startswith("mcp__"):
        parts = namespace.removeprefix("mcp__").strip("_").split("__")
        if len(parts) > 1:
            return _normalize_tool(f"{parts[-1]}{name}")
    return _normalize_tool(name)


def _paired_raw(
    rows: list[tuple[int, bool, dict | None]], row_turns: list[str | None], session: str
) -> tuple[set[int], set[str]]:
    candidates = []
    completed = []
    for index, (_, _, record) in enumerate(rows):
        if record is None:
            continue
        payload = _dict(record.get("payload"))
        if record.get("type") == "response_item" and payload.get("type") in {
            "function_call",
            "custom_tool_call",
        }:
            name = _str(payload.get("name"))
            if not name or name in WRAPPERS:
                continue
            raw = (
                payload.get("arguments")
                if payload.get("type") == "function_call"
                else payload.get("input")
            )
            args = _dict(raw) if isinstance(raw, dict) else _dict(_json(raw))
            if name in COMMANDS:
                kind, key = "command", _command_text(args.get("cmd") or args.get("command"))
            elif name in {"apply_patch", "functions.apply_patch"}:
                kind, key = "edit", None
            else:
                kind, key = "tool", _raw_tool_key(payload)
            if kind != "edit" and not key:
                continue
            candidates.append(
                (index, row_turns[index], kind, key, scoped(payload.get("call_id"), session))
            )
        elif record.get("type") == "event_msg" and payload.get("type") == "item_completed":
            item = _dict(payload.get("item"))
            typ = item.get("type")
            if typ == "CommandExecution" and item.get("status") in {"completed", "failed"}:
                kind, key = "command", _command_text(item.get("command"))
            elif typ == "FileChange" and item.get("status") == "completed":
                kind, key = "edit", None
            elif typ in {"McpToolCall", "DynamicToolCall"}:
                kind, key = "tool", _normalize_tool(_str(item.get("tool")) or "")
            else:
                continue
            if kind != "edit" and not key:
                continue
            completed.append((index, row_turns[index], kind, key, scoped(item.get("id"), session)))
    suppressed = set()
    suppressed_ids = set()
    for completion_index, turn, kind, key, completion_id in completed:
        matching = [
            candidate
            for candidate in candidates
            if candidate[0] < completion_index
            and candidate[0] not in suppressed
            and candidate[1] == turn
            and candidate[2:4] == (kind, key)
            and (
                turn is not None
                or candidate[4] == completion_id
                or completion_index - candidate[0] <= 100
            )
        ]
        if not matching:
            continue
        exact = [candidate for candidate in matching if candidate[4] == completion_id]
        chosen = exact[-1] if exact else matching[-1]
        suppressed.add(chosen[0])
        if chosen[4]:
            suppressed_ids.add(chosen[4])
    return suppressed, suppressed_ids


def _number(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
