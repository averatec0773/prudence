"""Derived tables: what the archive means, as far as this version of the parser knows.

Everything here is disposable. It is built only from the archive, never from the
original files, so a parser change is a rebuild rather than a migration, and every
row carries the `parser_version` that produced it. Tables are built under `__new`
names and swapped in one transaction so a reader never sees a table disappear.

This module knows no agent's file format. It reads the events a source adapter yields
(`sources/base.py`) and builds tables from those alone, so that a second agent is a new
adapter rather than a second set of branches in here. Nothing here names Claude Code,
and a test asserts that (`tests/test_sources.py`).

Nothing here is allowed to fail on a surprise either: an adapter reports a record type
it does not recognise rather than raising, and such a record is counted in
`unknown_record_type` and otherwise treated as a plain record.

What is deliberately not stored: message text, in any table, at any capture level. An
adapter may read text, and does, but this is the one module that decides what becomes a
count, a keyed hash or nothing at all, so the capture level means the same thing for
every source. `metadata-only` stores no file paths, no working directory, no command
text and no line hashes, so an employer's repository leaves nothing but shape and
counts. A keyed line hash is not readable, but it is still a fingerprint of their code,
and the promise made for that level is shape only.

Parser version 4 (M2) added two columns a behaviour fact needed and the archive did not
yet expose: `tool_call.error_hash`, a keyed digest of a failed tool result's content, at
`full` capture only, for `facts.repeated_errors` to count identical failures without
reading the text itself; and `session.replayed_records`, promoting a count `_flush_session`
already computed out of the free-text `notes` column and into one `facts.context_resets`
can query directly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from prudence import sources
from prudence.sources import base
from prudence.store import archive, repos
from prudence.store import commits as commits_module
from prudence.store import edits as edits_module
from prudence.store import lines as lines_module

PARSER_VERSION = 4

TABLES = (
    "session",
    "record",
    "turn",
    "tool_call",
    "edit",
    "edit_line",
    "command",
    "usage",
    "unknown_record_type",
)

SCHEMA = {
    "session": """
        CREATE TABLE {name}(
            session_id TEXT PRIMARY KEY,
            repo_key TEXT,
            source TEXT,
            entrypoint TEXT,
            cwd TEXT,
            first_at TEXT,
            last_at TEXT,
            record_count INTEGER NOT NULL DEFAULT 0,
            capture_level TEXT,
            parser_version INTEGER NOT NULL,
            notes TEXT,
            replayed_records INTEGER NOT NULL DEFAULT 0
        )""",
    "record": """
        CREATE TABLE {name}(
            record_id TEXT PRIMARY KEY,
            session_id TEXT,
            parent_id TEXT,
            type TEXT,
            subtype TEXT,
            timestamp TEXT,
            is_sidechain INTEGER,
            agent_id TEXT,
            prompt_id TEXT,
            parser_version INTEGER NOT NULL
        )""",
    "turn": """
        CREATE TABLE {name}(
            turn_id TEXT PRIMARY KEY,
            session_id TEXT,
            started_at TEXT,
            ended_at TEXT,
            user_prompt_chars INTEGER NOT NULL DEFAULT 0,
            parser_version INTEGER NOT NULL
        )""",
    "tool_call": """
        CREATE TABLE {name}(
            tool_use_id TEXT PRIMARY KEY,
            session_id TEXT,
            record_id TEXT,
            turn_id TEXT,
            tool_name TEXT,
            started_at TEXT,
            file_path TEXT,
            input_bytes INTEGER NOT NULL DEFAULT 0,
            result_bytes INTEGER,
            is_error INTEGER,
            parser_version INTEGER NOT NULL,
            error_hash TEXT
        )""",
    "edit": """
        CREATE TABLE {name}(
            tool_use_id TEXT PRIMARY KEY,
            session_id TEXT,
            turn_id TEXT,
            repo_key TEXT,
            tool_name TEXT,
            file_path TEXT,
            rel_path TEXT,
            edited_at TEXT,
            lines_added INTEGER NOT NULL DEFAULT 0,
            lines_removed INTEGER NOT NULL DEFAULT 0,
            is_new_file INTEGER NOT NULL DEFAULT 0,
            parser_version INTEGER NOT NULL
        )""",
    "edit_line": """
        CREATE TABLE {name}(
            tool_use_id TEXT NOT NULL,
            side TEXT NOT NULL,
            line_hash TEXT NOT NULL,
            PRIMARY KEY(tool_use_id, side, line_hash)
        ) WITHOUT ROWID""",
    "command": """
        CREATE TABLE {name}(
            tool_use_id TEXT PRIMARY KEY,
            session_id TEXT,
            turn_id TEXT,
            command_class TEXT,
            exit_code INTEGER,
            commit_hash TEXT,
            command_text TEXT,
            parser_version INTEGER NOT NULL
        )""",
    "usage": """
        CREATE TABLE {name}(
            record_id TEXT PRIMARY KEY,
            session_id TEXT,
            turn_id TEXT,
            request_id TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_creation_tokens INTEGER,
            parser_version INTEGER NOT NULL
        )""",
    "unknown_record_type": """
        CREATE TABLE {name}(
            type TEXT NOT NULL,
            claude_version TEXT,
            count INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT,
            PRIMARY KEY(type, claude_version)
        )""",
}

INDEXES = (
    "CREATE INDEX IF NOT EXISTS record_session ON record(session_id)",
    "CREATE INDEX IF NOT EXISTS record_prompt ON record(prompt_id)",
    "CREATE INDEX IF NOT EXISTS turn_session ON turn(session_id)",
    "CREATE INDEX IF NOT EXISTS tool_call_session ON tool_call(session_id)",
    "CREATE INDEX IF NOT EXISTS tool_call_name ON tool_call(tool_name)",
    "CREATE INDEX IF NOT EXISTS tool_call_error ON tool_call(session_id, error_hash)",
    "CREATE INDEX IF NOT EXISTS edit_session ON edit(session_id)",
    "CREATE INDEX IF NOT EXISTS edit_repo_path ON edit(repo_key, rel_path)",
    "CREATE INDEX IF NOT EXISTS edit_line_hash ON edit_line(line_hash)",
    "CREATE INDEX IF NOT EXISTS command_session ON command(session_id, command_class)",
    "CREATE INDEX IF NOT EXISTS command_commit ON command(commit_hash)",
    "CREATE INDEX IF NOT EXISTS usage_session ON usage(session_id)",
    "CREATE INDEX IF NOT EXISTS usage_model ON usage(model)",
)


@dataclass
class BuildStats:
    sessions: int = 0
    records: int = 0
    turns: int = 0
    tool_calls: int = 0
    edits: int = 0
    edit_lines: int = 0
    commands: int = 0
    usage_rows: int = 0
    usage_tokens: int = 0
    unknown_types: int = 0
    replayed_records: int = 0
    unassigned_sessions: int = 0
    elapsed: float = 0.0
    mapping_methods: Counter[str] = field(default_factory=Counter)
    command_classes: Counter[str] = field(default_factory=Counter)


@dataclass
class _ToolCall:
    """One tool use and its result, which arrive in two records some distance apart."""

    session_id: str
    record_id: str | None = None
    turn_id: str | None = None
    tool_name: str | None = None
    started_at: str | None = None
    file_path: str | None = None
    input_bytes: int = 0
    result_bytes: int | None = None
    is_error: int | None = None
    error_hash: str | None = None
    edit: edits_module.EditFacts | None = None
    command: edits_module.CommandFacts | None = None


@dataclass
class _Session:
    """One session under construction, across its transcript and its subagent files."""

    session_id: str
    repo_key: str | None
    capture_level: str
    mapping_method: str = "cwd"
    entrypoint: str | None = None
    cwd: str | None = None
    first_at: str | None = None
    last_at: str | None = None
    record_count: int = 0
    replayed: int = 0
    resumed: bool = False
    ordinal: int = 0
    records: list[tuple] = field(default_factory=list)
    turns: dict[str, list] = field(default_factory=dict)
    tool_calls: dict[str, _ToolCall] = field(default_factory=dict)
    usage: list[tuple] = field(default_factory=list)
    request_ids: set[str] = field(default_factory=set)


def build(
    connection: sqlite3.Connection,
    levels: dict[str, str],
    resolver: repos.Resolver | None = None,
) -> BuildStats:
    """Rebuild every derived table from the archive. Idempotent; safe to run at any time."""
    started = time.monotonic()
    stats = BuildStats()
    _create_new_tables(connection)
    resolver = resolver if resolver is not None else repos.resolver(connection)
    adapter = sources.source()
    key = lines_module.load_key()
    seen_records: set[str] = set()
    unknown: dict[tuple[str, str | None], list] = {}

    for row, head in _transcripts_in_order(connection, adapter):
        match = resolver.resolve(head.cwd, head.git_branch)
        repo_key = match.repo_key or row["repo_key"]
        stats.mapping_methods[match.method] += 1
        if repo_key is None:
            stats.unassigned_sessions += 1
        session = _Session(
            session_id=row["session_id"] or row["path"],
            repo_key=repo_key,
            capture_level=levels.get(repo_key, "full"),
            mapping_method=match.method,
        )
        for path, agent_id in _files_of(connection, row):
            _read_file(connection, adapter, path, session, agent_id, seen_records, unknown, key)
        _flush_session(connection, session, stats, resolver, key, adapter.kind)

    _flush_unknown(connection, unknown, stats)
    _swap(connection)
    repos.save_discoveries(connection, resolver)
    stats.elapsed = time.monotonic() - started
    return stats


def _files_of(connection: sqlite3.Connection, row: sqlite3.Row) -> list[tuple[str, str | None]]:
    """A session's own file first, then each subagent file with the agent id it carries."""
    files: list[tuple[str, str | None]] = [(row["path"], None)]
    files += [
        (sub["path"], sub["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0])
        for sub in connection.execute(
            "SELECT path FROM archive_file WHERE session_id = ? AND source = ? ORDER BY path",
            (row["session_id"], base.SUBAGENT),
        )
    ]
    return files


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts per derived table, or -1 when the table has not been built yet."""
    result: dict[str, int] = {}
    for table in TABLES:
        try:
            result[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            result[table] = -1
    return result


def _transcripts_in_order(
    connection: sqlite3.Connection, adapter: base.Source
) -> list[tuple[sqlite3.Row, base.FileHead]]:
    """Transcripts oldest first, so a resumed session is the one that carries the note."""
    rows = [
        (row, adapter.head(archive.head_lines(connection, row["path"])))
        for row in connection.execute(
            "SELECT path, session_id, repo_key FROM archive_file WHERE source = ?",
            (base.SESSION,),
        )
    ]
    return sorted(rows, key=lambda item: (item[1].first_at or "", item[0]["path"]))


def _read_file(
    connection: sqlite3.Connection,
    adapter: base.Source,
    path: str,
    session: _Session,
    agent_id: str | None,
    seen_records: set[str],
    unknown: dict[tuple[str, str | None], list],
    key: bytes,
) -> None:
    """Fold one archived file's events into the session it belongs to."""
    lines = archive.iter_lines(connection, path)
    for event in adapter.events(lines, path, session.session_id, agent_id):
        if not event.known_type:
            entry = unknown.setdefault((event.record_type, event.source_version), [0, None])
            entry[0] += 1
            if entry[1] is None:
                entry[1] = event.timestamp or datetime.now(UTC).isoformat()
        if event.record_id in seen_records:
            session.replayed += 1
            session.resumed = True
            continue
        seen_records.add(event.record_id)
        _fold_event(session, event, key)


def _fold_event(session: _Session, event: base.Event, key: bytes) -> None:
    """One record: its own row, its turn, and whatever payloads it carried."""
    stamp = event.timestamp
    if stamp:
        if session.first_at is None or stamp < session.first_at:
            session.first_at = stamp
        if session.last_at is None or stamp > session.last_at:
            session.last_at = stamp
    if session.entrypoint is None and event.entrypoint is not None:
        session.entrypoint = event.entrypoint
    if session.cwd is None and event.cwd is not None:
        session.cwd = event.cwd

    turn_id = _turn_id(event, session)
    session.record_count += 1
    session.records.append(
        (
            event.record_id,
            session.session_id,
            event.parent_id,
            event.record_type,
            event.subtype,
            stamp,
            1 if event.sidechain else 0,
            event.agent_id,
            event.prompt_id,
            PARSER_VERSION,
        )
    )
    _note_turn(session, turn_id, stamp, event)
    for payload in event.payloads:
        if isinstance(payload, base.Usage):
            _note_usage(session, turn_id, event.record_id, payload)
        elif isinstance(payload, base.ToolCall):
            _note_call(session, turn_id, event.record_id, stamp, payload)
        elif isinstance(payload, base.ToolResult):
            _note_result(session, payload, key)


def _turn_id(event: base.Event, session: _Session) -> str:
    if event.prompt_id is not None:
        return event.prompt_id
    if any(isinstance(payload, base.Prompt) for payload in event.payloads):
        session.ordinal += 1
    return f"{session.session_id}:{session.ordinal}"


def _note_turn(session: _Session, turn_id: str, stamp: str | None, event: base.Event) -> None:
    turn = session.turns.setdefault(turn_id, [None, None, 0])
    if stamp:
        if turn[0] is None or stamp < turn[0]:
            turn[0] = stamp
        if turn[1] is None or stamp > turn[1]:
            turn[1] = stamp
    for payload in event.payloads:
        if isinstance(payload, base.Prompt):
            turn[2] += payload.chars


def _note_usage(session: _Session, turn_id: str, record_id: str, usage: base.Usage) -> None:
    """What one API response cost, counted once however many records reported it.

    An agent writes several records for one response (a text block and a tool call each
    get their own) and repeats the same usage on all of them under one request id, so
    the first record of a request is counted and the rest are skipped; on the founder's
    store that is 157,868 records for 71,763 responses, so counting records would
    inflate the total by more than half.
    """
    if usage.request_id is not None:
        if usage.request_id in session.request_ids:
            return
        session.request_ids.add(usage.request_id)
    session.usage.append(
        (
            record_id,
            session.session_id,
            turn_id,
            usage.request_id,
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_creation_tokens,
            PARSER_VERSION,
        )
    )


def _note_call(
    session: _Session, turn_id: str, record_id: str, stamp: str | None, call: base.ToolCall
) -> None:
    """A tool the agent invoked, waiting for the result that arrives records later."""
    held = session.tool_calls.setdefault(call.call_id, _ToolCall(session.session_id))
    held.record_id = record_id
    held.turn_id = turn_id
    held.tool_name = call.tool_name
    held.started_at = stamp
    held.file_path = call.file_path
    held.input_bytes = call.input_bytes
    held.edit = call.edit
    held.command = call.command


def _note_result(session: _Session, result: base.ToolResult, key: bytes) -> None:
    """The result of a call, folded into it: the real patch, the exit code, the commit.

    The pairing is by call id and belongs here rather than in an adapter, because a call
    and its result can be records apart and even files apart. An error cancels the
    edit the call's own input suggested; otherwise the result's reading of the change
    wins over the input's, with anything it leaves out filled in from the call.
    """
    held = session.tool_calls.setdefault(result.call_id, _ToolCall(session.session_id))
    held.is_error = 1 if result.is_error else 0
    held.result_bytes = result.result_bytes
    if session.capture_level == "full" and result.error_content is not None:
        held.error_hash = _hash_error(key, result.error_content)
    if result.is_error:
        held.edit = None
    elif result.edit is not None:
        better = result.edit
        better.file_path = better.file_path or (held.edit.file_path if held.edit else None)
        better.is_new_file = better.is_new_file or bool(held.edit and held.edit.is_new_file)
        held.edit = better
    if held.command is None:
        return
    held.command.exit_code = result.exit_code
    if held.command.command_class == "git_commit":
        held.command.commit_hash = result.commit_hash


def _hash_error(key: bytes, content: object) -> str:
    """A keyed digest of a failed tool result, so `facts.repeated_errors` can count
    identical failures without a fact ever reading the error text itself."""
    text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    digest = hmac.new(key, text.encode("utf-8", "surrogatepass"), hashlib.sha256)
    return digest.hexdigest()[:16]


def _flush_session(
    connection: sqlite3.Connection,
    session: _Session,
    stats: BuildStats,
    resolver: repos.Resolver,
    key: bytes,
    kind: str,
) -> None:
    if session.record_count == 0 and not session.records:
        return
    full = session.capture_level == "full"
    notes = []
    if session.resumed:
        notes.append("resumed")
        notes.append(f"replayed {session.replayed} records")
    if session.mapping_method != "cwd":
        notes.append(f"repository by {session.mapping_method}")
    connection.executemany(
        "INSERT OR IGNORE INTO record__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        session.records,
    )
    stats.records += len(session.records)
    connection.executemany(
        "INSERT OR REPLACE INTO turn__new VALUES (?, ?, ?, ?, ?, ?)",
        [
            (turn_id, session.session_id, started, ended, chars, PARSER_VERSION)
            for turn_id, (started, ended, chars) in sorted(session.turns.items())
        ],
    )
    stats.turns += len(session.turns)
    connection.executemany(
        "INSERT OR REPLACE INTO tool_call__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                tool_use_id,
                call.session_id,
                call.record_id,
                call.turn_id,
                call.tool_name,
                call.started_at,
                call.file_path if full else None,
                call.input_bytes,
                call.result_bytes,
                call.is_error,
                PARSER_VERSION,
                call.error_hash,
            )
            for tool_use_id, call in sorted(session.tool_calls.items())
        ],
    )
    stats.tool_calls += len(session.tool_calls)
    connection.executemany(
        "INSERT OR REPLACE INTO usage__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", session.usage
    )
    stats.usage_rows += len(session.usage)
    stats.usage_tokens += sum(sum(value or 0 for value in row[5:9]) for row in session.usage)
    _flush_edits(connection, session, stats, resolver, key)
    _flush_commands(connection, session, stats)
    connection.execute(
        "INSERT OR REPLACE INTO session__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session.session_id,
            session.repo_key,
            kind,
            session.entrypoint,
            session.cwd if full else None,
            session.first_at,
            session.last_at,
            session.record_count,
            session.capture_level,
            PARSER_VERSION,
            "; ".join(notes) or None,
            session.replayed,
        ),
    )
    stats.sessions += 1
    stats.replayed_records += session.replayed


def _flush_edits(
    connection: sqlite3.Connection,
    session: _Session,
    stats: BuildStats,
    resolver: repos.Resolver,
    key: bytes,
) -> None:
    """One row per edit, plus its keyed line hashes, which are the attribution's left side."""
    full = session.capture_level == "full"
    rows: list[tuple] = []
    line_rows: list[tuple] = []
    for tool_use_id, call in sorted(session.tool_calls.items()):
        facts = call.edit
        if facts is None:
            continue
        repo_key, rel_path = resolver.repo_of_path(facts.file_path)
        rows.append(
            (
                tool_use_id,
                call.session_id,
                call.turn_id,
                repo_key or session.repo_key,
                call.tool_name,
                facts.file_path if full else None,
                rel_path if full else None,
                commits_module.utc(call.started_at),
                len(facts.added),
                len(facts.removed),
                1 if facts.is_new_file else 0,
                edits_module.EDIT_FACT_VERSION,
            )
        )
        if not full:
            continue
        for side, block in (("added", facts.added), ("removed", facts.removed)):
            line_rows.extend(
                (tool_use_id, side, digest) for digest in lines_module.hash_lines(key, block)
            )
    connection.executemany(
        "INSERT OR REPLACE INTO edit__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.executemany("INSERT OR REPLACE INTO edit_line__new VALUES (?, ?, ?)", line_rows)
    stats.edits += len(rows)
    stats.edit_lines += len(line_rows)


def _flush_commands(connection: sqlite3.Connection, session: _Session, stats: BuildStats) -> None:
    """One row per shell call: what it was for, and what git said if it committed.

    The command text is the one string the founder asked to be able to read back, so it
    is kept at `full` capture and dropped entirely at `metadata-only`.
    """
    full = session.capture_level == "full"
    rows: list[tuple] = []
    for tool_use_id, call in sorted(session.tool_calls.items()):
        facts = call.command
        if facts is None:
            continue
        rows.append(
            (
                tool_use_id,
                call.session_id,
                call.turn_id,
                facts.command_class,
                facts.exit_code,
                facts.commit_hash,
                facts.command_text if full else None,
                edits_module.COMMAND_FACT_VERSION,
            )
        )
        stats.command_classes[facts.command_class] += 1
    connection.executemany(
        "INSERT OR REPLACE INTO command__new VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    stats.commands += len(rows)


def _flush_unknown(
    connection: sqlite3.Connection,
    unknown: dict[tuple[str, str | None], list],
    stats: BuildStats,
) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO unknown_record_type__new VALUES (?, ?, ?, ?)",
        [
            (record_type, version, count, first_seen)
            for (record_type, version), (count, first_seen) in sorted(
                unknown.items(), key=lambda item: (item[0][0], item[0][1] or "")
            )
        ],
    )
    stats.unknown_types = len(unknown)


def _create_new_tables(connection: sqlite3.Connection) -> None:
    for table in TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table}__new")
        connection.execute(SCHEMA[table].format(name=f"{table}__new"))


def _swap(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    for statement in INDEXES:
        connection.execute(statement)
