"""What every source hands the store, and nothing about any particular agent.

One agent writes JSONL records with a `uuid` on each line; another writes rollout
items with no per-record id at all, tool calls under a different name and token
counts in their own event. The store must not care. So a source adapter turns one
agent's files into a stream of `Event`s, and `store/derived.py` builds its tables
from that stream alone.

An `Event` is one record of the agent's own log: the identity and time the record
carries, plus the payloads it happens to hold. A record usually holds none (it is
bookkeeping) or one; an assistant record that both answers and calls a tool holds
several, which is why `payloads` is a tuple rather than a single field. Keeping a
record whole is what lets the store write one `record` row per record and settle
ownership and duplicates once per record rather than once per payload.

Two fields carry the whole fork problem between them. `Event.session_id` is the
session the record *declares it belongs to*, which is not always the session whose
file it was read from: Claude Code's fork copies a parent's history into the new
file record for record, parent's `sessionId` and all. `Event.stable_id` says whether
`record_id` is the agent's own identifier or one the adapter had to derive from the
file position, because a derived id names the same record differently in every file
that copies it. `store/derived.py` reads both; no adapter has to know what they are for.

What is deliberately not here: message text. An adapter may read it, and does (a
prompt's length, an edit's lines, a command's text), but nothing text-shaped reaches a
table: `store/derived.py` is the one place that decides what becomes a count, a keyed
hash or nothing at all, so that the capture level means the same thing for every source.
And nothing is in `Event` that no derived table uses; assistant text, for one, is read
by nothing today and so is not carried.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from prudence.store.edits import CommandFacts, EditFacts

# What a file beside a session's own transcript is. The store stores these words on
# `archive_file.source` and asks for them back by name, so they are the shared
# vocabulary rather than one agent's directory layout.
SESSION = "transcript"
SUBAGENT = "subagent"
TOOL_RESULT = "tool-result"
FILE_HISTORY = "file-history"

# The record type an adapter gives a line that is not a record at all (not JSON, or cut
# short). The store counts it like any type it does not know, and the run log reports it
# as an unreadable line rather than as a new record type.
UNREADABLE = "unreadable"

# How deep `key_shape` looks into a record: its own keys and the keys of each object
# directly under them.
KEY_SHAPE_DEPTH = 2


@dataclass(frozen=True)
class SessionFile:
    """One session's own file on disk, as a scan sees it.

    Read from the head and the tail of the file only: no message content, no writes.
    """

    path: Path
    session_id: str
    cwd: str | None
    first_at: datetime | None
    last_at: datetime | None
    size_bytes: int
    entrypoint: str | None
    git_branch: str | None = None


@dataclass(frozen=True)
class CompanionFile:
    """A file that belongs to a session but is not its transcript."""

    path: Path
    kind: str  # one of SUBAGENT, TOOL_RESULT, FILE_HISTORY


@dataclass
class FileHead:
    """What the first records of an archived file say about when and where it ran.

    Enough to sort the files and to ask `store/repos.py` which repository they belong
    to, without decompressing more than the first chunk.
    """

    first_at: str | None = None
    cwd: str | None = None
    git_branch: str | None = None


@dataclass(frozen=True)
class Prompt:
    """Something the person typed. Its length crosses; the text never does."""

    chars: int


@dataclass(frozen=True)
class Usage:
    """What one response to the model cost, as the agent reports it.

    `request_id` is the agent's own id for the request. Agents write several records
    for one response and repeat the usage on each, and the first of them can carry a
    partial output count; the store keeps one row per response (`Event.message_id`) with
    the counts of its last record. Any count the format does not carry is None, never zero.
    """

    request_id: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    total_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None


@dataclass(frozen=True)
class ToolCall:
    """A tool the agent invoked, read from the call itself.

    `shell_command` is the whole command of a shell call, for the bucket rule
    (`store/buckets.py`) to read in memory; unlike `command.command_text` it is never
    stored, which is why it is not truncated. `sends_to_agent` names the running subagent
    a call hands more work to, whose later replies then belong to this call's turn.
    """

    call_id: str
    tool_name: str | None
    file_path: str | None
    input_bytes: int
    edit: EditFacts | None
    command: CommandFacts | None
    shell_command: str | None = None
    sends_to_agent: str | None = None
    edits: tuple[EditFacts, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    """How that tool call came back, which the agent reports in a later record.

    `error_content` is the failure as the agent wrote it, and it is here only because
    `facts.repeated_errors` counts identical failures: the store keys a digest of it and
    stores that, never the content. It is None unless the call failed.

    `started_agent` is the subagent a dispatching call reports having started, the
    fallback link from that agent's replies to the turn that asked for them when no file
    beside the agent's log names the call (`Event.dispatch_id`).
    """

    call_id: str
    is_error: bool
    result_bytes: int
    error_content: object | None
    edit: EditFacts | None
    exit_code: int | None
    commit_hash: str | None
    started_agent: str | None = None
    edits: tuple[EditFacts, ...] = ()


Payload = Prompt | Usage | ToolCall | ToolResult


@dataclass(frozen=True)
class Event:
    """One record of an agent's log, normalised.

    `session_id` is the session the record declares, which for a record copied into a
    fork is the parent's. None when the format puts no session on this record at all.

    `message_id` names the reply of the model this record is part of: one reply is often
    written as several records, and they share this id. None for a record that is not
    part of a reply (a prompt, a tool result, bookkeeping). An adapter falls back to
    whatever id the format gives the request, then to the record's own id, so every reply
    has one.

    `dispatch_id` is set on every event of a subagent's log when the agent wrote down
    which tool call started it: the id of that call in the parent's log.

    `offset` is where the record's line starts in its file. `key_shape` is set only on a
    record of a type the adapter does not know: the record's keys (`key_shape` below),
    never a value, so that a format change can be described without reading it.
    """

    record_id: str
    stable_id: bool
    session_id: str | None
    parent_id: str | None
    timestamp: str | None
    record_type: str
    known_type: bool
    subtype: str | None = None
    source_version: str | None = None
    sidechain: bool = False
    agent_id: str | None = None
    prompt_id: str | None = None
    cwd: str | None = None
    entrypoint: str | None = None
    message_id: str | None = None
    dispatch_id: str | None = None
    payloads: tuple[Payload, ...] = field(default_factory=tuple)
    offset: int | None = None
    key_shape: tuple[str, ...] = ()
    response_gap: bool = False


def key_shape(record: dict, depth: int = KEY_SHAPE_DEPTH) -> tuple[str, ...]:
    """A record's keys, and the keys of the objects under them, as sorted dotted paths.

    `{"type": "x", "data": {"a": 1}}` is `("data", "data.a", "type")`. Keys only: no
    value is read beyond asking whether it is an object.
    """
    found: set[str] = set()

    def walk(value: dict, prefix: str, level: int) -> None:
        for key, item in value.items():
            path = f"{prefix}{key}"
            found.add(path)
            if level < depth and isinstance(item, dict):
                walk(item, f"{path}.", level + 1)

    walk(record, "", 1)
    return tuple(sorted(found))


@dataclass(frozen=True)
class AgentLog:
    """One subagent's own log among a session's archived companion files.

    `agent_id` is the id the agent's records and its parent's calls know it by, and
    `sidecar` is the file the agent keeps beside its log to say who started it, when
    there is one. Both are the adapter's reading of its own layout; the store only reads
    the files it is pointed at.
    """

    path: str
    agent_id: str
    sidecar: str | None = None


class Source(Protocol):
    """One agent's files, turned into events. Implemented once per agent.

    Every method is lenient by contract: an agent's log format is internal to it and
    changes between releases, so a missing or odd field is skipped and never fatal.
    """

    kind: str

    def session_files(self) -> list[SessionFile]:
        """Every session this agent has left on this machine, one entry per session."""
        ...

    def companion_files(self, session: SessionFile) -> list[CompanionFile]:
        """The files beside one session's own: subagent logs, spilled results, history.

        Empty for an agent that keeps everything in the one file.
        """
        ...

    def head(self, lines: Iterable[bytes]) -> FileHead:
        """When and where a file's first records say the session ran."""
        ...

    def agent_logs(self, paths: Sequence[str]) -> list[AgentLog]:
        """Which of a session's archived subagent files are agent logs, in path order.

        Everything else among them (a sidecar, a workflow's journal) is archived like any
        other file and read by nothing.
        """
        ...

    def events(
        self,
        lines: Iterable[tuple[int, bytes]],
        path: str,
        file_session_id: str,
        agent_id: str | None,
        sidecar: bytes | None = None,
    ) -> Iterator[Event]:
        """One event per record of one archived file, in file order.

        `lines` is (byte offset, line) as the archive stored them. `path` and
        `file_session_id` identify the file itself, for an adapter that has to derive a
        record id; `agent_id` names the subagent whose file this is, or is None for a
        session's own transcript; `sidecar` is the bytes of that agent's `AgentLog.sidecar`.
        """
        ...
