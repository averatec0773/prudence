"""Derived tables: what the archive means, as far as this version of the parser knows.

Everything here is disposable. It is built only from the archive, never from the
original files, so a parser change is a rebuild rather than a migration, and every
row carries the `parser_version` that produced it. Tables are built under `__new`
names and swapped in one transaction so a reader never sees a table disappear.

The transcript format is internal to Claude Code and changed 24 times in five months
on the founder's machine, so nothing here is allowed to fail on a surprise: a record
type the parser does not know is counted in `unknown_record_type` and otherwise
treated as a plain record.

What is deliberately not stored: message text, in any table, at any capture level.
`metadata-only` additionally stores no file paths, no working directory, no command
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

from prudence.store import archive, repos
from prudence.store import commits as commits_module
from prudence.store import edits as edits_module
from prudence.store import lines as lines_module

PARSER_VERSION = 4

# Record types this version understands. Anything else is counted and kept as a record.
KNOWN_RECORD_TYPES = frozenset({"user", "assistant", "system", "attachment"})

# Tool inputs whose file path is a fact worth keeping (at `full` capture only).
PATH_TOOLS = frozenset({"Edit", "Write", "Read", "NotebookEdit"})

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
    key = lines_module.load_key()
    seen_records: set[str] = set()
    unknown: dict[tuple[str, str | None], list] = {}

    for row, head in _transcripts_in_order(connection):
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
        files = [(row["path"], None)]
        files += [
            (sub["path"], sub["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0])
            for sub in connection.execute(
                "SELECT path FROM archive_file WHERE session_id = ? AND source = 'subagent'"
                " ORDER BY path",
                (row["session_id"],),
            )
        ]
        for path, agent_id in files:
            _read_file(connection, path, session, agent_id, seen_records, unknown, key)
        _flush_session(connection, session, stats, resolver, key)

    _flush_unknown(connection, unknown, stats)
    _swap(connection)
    repos.save_discoveries(connection, resolver)
    stats.elapsed = time.monotonic() - started
    return stats


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts per derived table, or -1 when the table has not been built yet."""
    result: dict[str, int] = {}
    for table in TABLES:
        try:
            result[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            result[table] = -1
    return result


@dataclass
class _Head:
    """What the first records of a transcript say about when and where it ran."""

    first_at: str | None = None
    cwd: str | None = None
    git_branch: str | None = None


def _transcripts_in_order(
    connection: sqlite3.Connection,
) -> list[tuple[sqlite3.Row, _Head]]:
    """Transcripts oldest first, so a resumed session is the one that carries the note."""
    rows = [
        (row, _head(connection, row["path"]))
        for row in connection.execute(
            "SELECT path, session_id, repo_key FROM archive_file WHERE source = 'transcript'"
        )
    ]
    return sorted(rows, key=lambda item: (item[1].first_at or "", item[0]["path"]))


def _head(connection: sqlite3.Connection, path: str) -> _Head:
    """When a transcript starts and where it ran, from its first chunk alone."""
    head = _Head()
    for line in archive.head_lines(connection, path):
        record = _parse(line)
        if record is None:
            continue
        if head.first_at is None and isinstance(record.get("timestamp"), str):
            head.first_at = record["timestamp"]
        if head.cwd is None and isinstance(record.get("cwd"), str):
            head.cwd = record["cwd"]
        if head.git_branch is None and isinstance(record.get("gitBranch"), str):
            head.git_branch = record["gitBranch"]
        if head.first_at and head.cwd and head.git_branch:
            break
    return head


def _read_file(
    connection: sqlite3.Connection,
    path: str,
    session: _Session,
    agent_id: str | None,
    seen_records: set[str],
    unknown: dict[tuple[str, str | None], list],
    key: bytes,
) -> None:
    full = session.capture_level == "full"
    for offset, line in archive.iter_lines(connection, path):
        record = _parse(line)
        if record is None:
            continue
        record_type = record.get("type")
        if not isinstance(record_type, str):
            record_type = "unknown"
        version = record.get("version") if isinstance(record.get("version"), str) else None
        if record_type not in KNOWN_RECORD_TYPES:
            entry = unknown.setdefault((record_type, version), [0, None])
            entry[0] += 1
            if entry[1] is None:
                entry[1] = _timestamp(record) or datetime.now(UTC).isoformat()

        record_id = record.get("uuid")
        if not isinstance(record_id, str) or not record_id:
            record_id = hashlib.sha256(f"{path}:{offset}".encode()).hexdigest()
        if record_id in seen_records:
            session.replayed += 1
            session.resumed = True
            continue
        seen_records.add(record_id)

        stamp = _timestamp(record)
        if stamp:
            if session.first_at is None or stamp < session.first_at:
                session.first_at = stamp
            if session.last_at is None or stamp > session.last_at:
                session.last_at = stamp
        if session.entrypoint is None and isinstance(record.get("entrypoint"), str):
            session.entrypoint = record["entrypoint"]
        if full and session.cwd is None and isinstance(record.get("cwd"), str):
            session.cwd = record["cwd"]

        turn_id = _turn_id(record, session)
        session.record_count += 1
        session.records.append(
            (
                record_id,
                session.session_id,
                record.get("parentUuid") if isinstance(record.get("parentUuid"), str) else None,
                record_type,
                _subtype(record),
                stamp,
                1 if record.get("isSidechain") else 0,
                agent_id or _text_or_none(record.get("agentId")),
                _text_or_none(record.get("promptId")),
                PARSER_VERSION,
            )
        )
        _note_turn(session, turn_id, stamp, record)
        _note_usage(session, turn_id, record_id, record)
        _note_tools(
            session, turn_id, record_id, turn_stamp=stamp, record=record, full=full, key=key
        )


def _turn_id(record: dict, session: _Session) -> str:
    prompt_id = record.get("promptId")
    if isinstance(prompt_id, str) and prompt_id:
        return prompt_id
    if _is_user_prompt(record):
        session.ordinal += 1
    return f"{session.session_id}:{session.ordinal}"


def _note_turn(session: _Session, turn_id: str, stamp: str | None, record: dict) -> None:
    turn = session.turns.setdefault(turn_id, [None, None, 0])
    if stamp:
        if turn[0] is None or stamp < turn[0]:
            turn[0] = stamp
        if turn[1] is None or stamp > turn[1]:
            turn[1] = stamp
    if _is_user_prompt(record):
        turn[2] += _prompt_chars(record)


def _note_usage(session: _Session, turn_id: str, record_id: str, record: dict) -> None:
    """What one API response cost, from the assistant record that carries `message.usage`.

    Two things make this less obvious than it looks. Claude Code writes several records
    for one response (a text block and a tool call each get their own) and repeats the
    same usage on all of them under one `requestId`, so the first record of a request is
    counted and the rest are skipped; on the founder's store that is 157,868 records for
    71,763 responses, so counting records would inflate the total by more than half.
    And a version that writes no usage at all is not an error: it simply produces no row,
    and every surface shows the absence rather than a zero.
    """
    if record.get("type") != "assistant":
        return
    message = record.get("message")
    if not isinstance(message, dict):
        return
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return
    request_id = _text_or_none(record.get("requestId"))
    if request_id is not None:
        if request_id in session.request_ids:
            return
        session.request_ids.add(request_id)
    session.usage.append(
        (
            record_id,
            session.session_id,
            turn_id,
            request_id,
            _text_or_none(message.get("model")),
            _token_count(usage, "input_tokens"),
            _token_count(usage, "output_tokens"),
            _token_count(usage, "cache_read_input_tokens"),
            _token_count(usage, "cache_creation_input_tokens"),
            PARSER_VERSION,
        )
    )


def _token_count(usage: dict, key: str) -> int | None:
    """A token count, or NULL when this version of the format does not carry that key."""
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _note_tools(
    session: _Session,
    turn_id: str,
    record_id: str,
    turn_stamp: str | None,
    record: dict,
    full: bool,
    key: bytes,
) -> None:
    """Fold a tool use, and later its result, into one call, an edit and a command.

    Edits are read as soon as the call is seen, from the input alone, and read again
    from the result's `structuredPatch` when one arrives, because the spike measured
    that a quarter of edit results never arrive at all. Keeping only the hashes means
    no file content is held between the two records.
    """
    outcome = record.get("toolUseResult")
    for block in _content_blocks(record):
        kind = block.get("type")
        if kind == "tool_use":
            tool_use_id = block.get("id")
            if not isinstance(tool_use_id, str):
                continue
            payload = block.get("input") if isinstance(block.get("input"), dict) else {}
            name = block.get("name") if isinstance(block.get("name"), str) else None
            call = session.tool_calls.setdefault(tool_use_id, _ToolCall(session.session_id))
            call.record_id = record_id
            call.turn_id = turn_id
            call.tool_name = name
            call.started_at = turn_stamp
            call.file_path = _file_path(name, payload) if full else None
            call.input_bytes = len(json.dumps(payload, ensure_ascii=False).encode())
            call.edit = edits_module.extract_edit(name, payload, None)
            call.command = edits_module.extract_command(name, payload, full)
        elif kind == "tool_result":
            tool_use_id = block.get("tool_use_id")
            if not isinstance(tool_use_id, str):
                continue
            call = session.tool_calls.setdefault(tool_use_id, _ToolCall(session.session_id))
            call.is_error = 1 if block.get("is_error") else 0
            content = block.get("content")
            call.result_bytes = (
                len(json.dumps(content, ensure_ascii=False).encode()) if content else 0
            )
            if full and call.is_error and content is not None:
                call.error_hash = _hash_error(key, content)
            _fold_result(call, outcome)


def _hash_error(key: bytes, content: object) -> str:
    """A keyed digest of a failed tool result, so `facts.repeated_errors` can count
    identical failures without a fact ever reading the error text itself."""
    text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    digest = hmac.new(key, text.encode("utf-8", "surrogatepass"), hashlib.sha256)
    return digest.hexdigest()[:16]


def _fold_result(call: _ToolCall, outcome: object) -> None:
    """What the result adds: the real patch, the exit code, the commit git announced."""
    if call.is_error:
        call.edit = None
    elif isinstance(outcome, dict):
        better = edits_module.extract_edit(call.tool_name, {}, outcome)
        if better is not None:
            better.file_path = better.file_path or (call.edit.file_path if call.edit else None)
            better.is_new_file = better.is_new_file or bool(call.edit and call.edit.is_new_file)
            call.edit = better
    if call.command is None:
        return
    exit_code, commit_hash = edits_module.read_result(outcome)
    call.command.exit_code = exit_code
    if call.command.command_class == "git_commit":
        call.command.commit_hash = commit_hash


def _flush_session(
    connection: sqlite3.Connection,
    session: _Session,
    stats: BuildStats,
    resolver: repos.Resolver,
    key: bytes,
) -> None:
    if session.record_count == 0 and not session.records:
        return
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
                call.file_path,
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
            "claude_code",
            session.entrypoint,
            session.cwd,
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
    """One row per shell call: what it was for, and what git said if it committed."""
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
                facts.command_text,
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


def _parse(line: bytes) -> dict | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _timestamp(record: dict) -> str | None:
    raw = record.get("timestamp")
    return raw if isinstance(raw, str) else None


def _text_or_none(value: object) -> str | None:
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
    """A record the user typed, as opposed to a tool result wearing the user role."""
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
