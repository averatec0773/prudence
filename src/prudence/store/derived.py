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

Parser version 5 settled who owns a record. A file is not a session: an agent that can
fork a session writes the parent's whole history into the new file before the new
session's own records, so reading one file as one session gave a fork its parent's start
time, counted the parent's turns again, and made the owner of a shared record depend on
which file was read first. Two rules decide ownership, and both are agent-agnostic.

1. **A record belongs to the session it declares.** That is `_read_file`'s rule, and it
   is the reason for the two `session` columns `forked_from` and `fork_point`. It covers
   every copy that keeps the original's session id, which is what Claude Code's fork
   writes.
2. **When two sessions each declare the same record as their own, the session whose
   transcript begins earlier owns it, and a tie breaks on the archive path.** That is
   `_transcripts_in_order`'s rule: the files are read in that order and the first claim
   wins, with the later session counting the record in `replayed_records`. It covers the
   copies rule 1 cannot see, where the agent re-stamped the copied lines with the new
   session's id and nothing in the file says where they came from. Both halves of the key
   are read out of the files themselves, so the order files were ingested in cannot
   change the answer. What it assumes, and what happens when the assumption is false, is
   written down as a known compromise in ARCHITECTURE.md (rule 17).

Parser version 5 also made `unknown_record_type.first_seen` a fact about the archive
rather than about the build. A record type whose first record carries no timestamp used
to be stamped with `datetime.now()`, so two rebuilds of one archive disagreed on that
column and the promise that every derived table is reproducible was quietly broken. It
now falls back to when Prudence first stored the file the record sits in.

Parser version 6 added the `response` table, one row per reply of the model with the
bucket `store/buckets.py` gives it, and fixed five links it depends on, all found on the
founder's store on 2026-09-22:

1. **A record without a prompt id belongs to the turn the last prompt opened.** Only the
   person's prompts carry the turn's id, so every assistant record fell to
   `<session>:0` and 135 of 2,538 turns had a tool call by that link. `_turn_id` now
   carries the open turn forward through the session's own transcript.
2. **A reply's tokens are those of its last record.** One reply is written as several
   records, and in a subagent's log the first carries a partial output count (3.8M
   recorded against 17.1M real). `usage` keeps one row per reply and overwrites its
   counts with each later record's.
3. **A subagent's replies belong to the turn that dispatched it.** The subagent's own
   records carry the parent's prompt id at the time they were written, which moves on
   when the person types again while an agent runs (3,445 replies, 544M tokens, landed
   on a later turn). The link is now the dispatching call: named by the file beside the
   agent's log when there is one, else by the agent id the call's result reports, and
   moved to a later turn by a call that hands the running agent more work. The agent's
   own prompt id is only the fallback. Resolved in `_AgentTurns` once every file of the
   session has been read, because the call and the reply are in different files.
4. **A reply is counted once, by the session that declared it first.** Records carry
   the reply's id as well as their own, so a copy that got new record ids is still
   recognised as the same reply and skipped like any replayed record.
5. **A turn's tokens are the sum of the replies in it.** Nothing attaches usage to a
   turn by time any more: `response.turn_id` and `usage.turn_id` are the links above.

The same version stopped reading a subagent's sidecar (`agent-<id>.meta.json`) and a
workflow's journal as if they were transcripts, which put 2,634 records of type
`unknown`, `started` and `result` into `record` and `unknown_record_type`: the adapter
now says which companion files are agent logs (`Source.agent_logs`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field

from prudence import sources
from prudence.sources import base
from prudence.store import archive, buckets, repos
from prudence.store import commits as commits_module
from prudence.store import edits as edits_module
from prudence.store import lines as lines_module
from prudence.store import progress as progress_module
from prudence.store.agent_turns import AgentTurns, Call, Link

PARSER_VERSION = 6

TABLES = (
    "session",
    "record",
    "turn",
    "tool_call",
    "edit",
    "edit_line",
    "command",
    "usage",
    "response",
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
            replayed_records INTEGER NOT NULL DEFAULT 0,
            forked_from TEXT,
            fork_point TEXT
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
    "response": """
        CREATE TABLE {name}(
            response_id TEXT PRIMARY KEY,
            session_id TEXT,
            turn_id TEXT,
            agent_id TEXT,
            started_at TEXT,
            bucket TEXT,
            bucket_rule_version INTEGER NOT NULL,
            heuristic INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_creation_tokens INTEGER,
            tool_calls INTEGER NOT NULL DEFAULT 0,
            change_calls INTEGER NOT NULL DEFAULT 0,
            run_calls INTEGER NOT NULL DEFAULT 0,
            read_calls INTEGER NOT NULL DEFAULT 0,
            talk_calls INTEGER NOT NULL DEFAULT 0,
            files_changed INTEGER NOT NULL DEFAULT 0,
            commands INTEGER NOT NULL DEFAULT 0,
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
    "CREATE INDEX IF NOT EXISTS response_session ON response(session_id)",
    "CREATE INDEX IF NOT EXISTS response_turn ON response(turn_id)",
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
    responses: int = 0
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
    link: Link | None = None
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
class _Reply:
    """One reply of the model, from every record that carries its id.

    `usage` is the last record's, because the first can carry a partial output count.
    `kinds` holds each tool call's bucket and whether the bucket is only a guess. A reply
    whose record could not be read at all has no tool calls to judge by and is a gap:
    its tokens are counted and it has no bucket.
    """

    session_id: str
    turn_id: str | None
    link: Link | None
    agent_id: str | None
    started_at: str | None
    gap: bool = False
    usage: base.Usage | None = None
    usage_record: str | None = None  # the first record that reported the usage
    kinds: list[tuple[str, bool]] = field(default_factory=list)
    files: set[str] = field(default_factory=set)
    commands: int = 0


@dataclass
class _Session:
    """One session under construction, from every file that carries a record of it."""

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
    forked_from: str | None = None
    fork_point: str | None = None
    ordinal: int = 0
    current_turn: str | None = None
    records: list[tuple] = field(default_factory=list)
    turns: dict[str, list] = field(default_factory=dict)
    tool_calls: dict[str, _ToolCall] = field(default_factory=dict)
    replies: dict[str, _Reply] = field(default_factory=dict)
    # Subagent id -> the call that started it, from the file beside the agent's log and,
    # as the fallback, from the agent id the call's result reports.
    dispatched_by_sidecar: dict[str, str] = field(default_factory=dict)
    dispatched_by_result: dict[str, str] = field(default_factory=dict)
    # Subagent id -> the calls that handed it more work while it ran.
    sends: dict[str, list[str]] = field(default_factory=dict)
    # Subagent id -> the last prompt id its own log carried.
    agent_prompts: dict[str, str] = field(default_factory=dict)


def build(
    connection: sqlite3.Connection,
    levels: dict[str, str],
    resolver: repos.Resolver | None = None,
    progress: progress_module.Step | None = None,
) -> BuildStats:
    """Rebuild every derived table from the archive. Idempotent; safe to run at any time."""
    started = time.monotonic()
    stats = BuildStats()
    progress = progress or progress_module.silent()
    _create_new_tables(connection)
    resolver = resolver if resolver is not None else repos.resolver(connection)
    adapter = sources.source()
    key = lines_module.load_key()
    seen_records: set[str] = set()
    unknown: dict[tuple[str, str | None], list] = {}
    transcripts = _transcripts_in_order(connection, adapter)
    # Sessions with no file of their own, known only from the copy a fork carries, live in
    # `orphans`; they outlive the loop because two forks of one deleted parent each carry
    # part of it.
    ownership = _Ownership({_session_id(row) for row, _ in transcripts}, {}, {})
    orphans = ownership.orphans

    progress.start(len(transcripts), "sessions")
    for row, head in transcripts:
        match = resolver.resolve(head.cwd, head.git_branch)
        repo_key = match.repo_key or row["repo_key"]
        progress.advance(label=f"Parsing {_project(resolver, repo_key)}")
        stats.mapping_methods[match.method] += 1
        if repo_key is None:
            stats.unassigned_sessions += 1
        session = _Session(
            session_id=_session_id(row),
            repo_key=repo_key,
            capture_level=levels.get(repo_key, "full"),
            mapping_method=match.method,
        )
        for archived in _files_of(connection, adapter, row):
            _read_file(
                connection,
                adapter,
                archived,
                session,
                ownership,
                seen_records,
                unknown,
                key,
            )
        _flush_session(connection, session, stats, resolver, key, adapter.kind)

    for session_id in sorted(orphans):
        _flush_session(connection, orphans[session_id], stats, resolver, key, adapter.kind)
    _flush_unknown(connection, unknown, stats)
    _swap(connection)
    repos.save_discoveries(connection, resolver)
    stats.elapsed = time.monotonic() - started
    return stats


def _session_id(row: sqlite3.Row) -> str:
    """A transcript's session, or its path when the file carries no session id at all."""
    return row["session_id"] or row["path"]


def _project(resolver: repos.Resolver, repo_key: str | None) -> str:
    """A repository's own name, for the progress label. Not every session has one."""
    repository = resolver.repositories.get(repo_key) if repo_key else None
    return repository.name if repository else "an unassigned session"


@dataclass(frozen=True)
class _File:
    """One archived file of a session, and what reading it needs besides its bytes."""

    path: str
    agent_id: str | None  # the subagent whose file this is; None for the session's own
    archived_at: str  # `archive_file.first_seen`: when Prudence first stored these bytes
    sidecar: str | None = None  # the archived file beside a subagent's log, if any


def _files_of(
    connection: sqlite3.Connection, adapter: base.Source, row: sqlite3.Row
) -> list[_File]:
    """A session's own file first, then each subagent log the adapter recognises.

    Which of the archived subagent files are logs, and which agent each belongs to, is
    the adapter's reading of its own layout; the rest of them are archived and not read.
    """
    stored = {
        sub["path"]: sub["first_seen"]
        for sub in connection.execute(
            "SELECT path, first_seen FROM archive_file WHERE session_id = ? AND source = ?",
            (row["session_id"], base.SUBAGENT),
        )
    }
    files = [_File(row["path"], None, row["first_seen"])]
    files += [
        _File(log.path, log.agent_id, stored[log.path], log.sidecar)
        for log in adapter.agent_logs(sorted(stored))
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
    """Transcripts oldest first: the second ownership rule, in the shape of a sort.

    When two sessions each declare the same record as their own, the session whose
    transcript begins earlier owns it and the later one counts it in
    `replayed_records`. Reading the files in this order and letting the first claim win
    is that rule: no session is ever compared with another, and no second pass is needed.

    Both halves of the key come out of the files themselves, the first timestamp from the
    file's own head and the path from the archive, so the order the files were ingested in
    cannot change the answer. A rebuild of one archive therefore always produces the same
    tables, which `tests/test_derived.py` and `tests/test_forks.py` both assert.
    """
    rows = [
        (row, adapter.head(archive.head_lines(connection, row["path"])))
        for row in connection.execute(
            "SELECT path, session_id, repo_key, first_seen FROM archive_file WHERE source = ?",
            (base.SESSION,),
        )
    ]
    return sorted(rows, key=lambda item: (item[1].first_at or "", item[0]["path"]))


@dataclass(frozen=True)
class _Ownership:
    """What the ownership rule needs to know beyond the file it is reading.

    `own_files` is every session that has a transcript of its own in the archive;
    `orphans` collects the sessions that do not, built from the copy a fork carries;
    `replies` names the session that claimed each reply id first, so a copy of a reply
    under new record ids is recognised as the same reply.
    """

    own_files: set[str]
    orphans: dict[str, _Session]
    replies: dict[str, str]


def _read_file(
    connection: sqlite3.Connection,
    adapter: base.Source,
    archived: _File,
    session: _Session,
    ownership: _Ownership,
    seen_records: set[str],
    unknown: dict[tuple[str, str | None], list],
    key: bytes,
) -> None:
    """Fold one archived file's events into the sessions those events declare.

    A record belongs to the session it names, which is not always the session whose file
    it was read from. An agent that can fork a session copies the parent's history into
    the new file with the parent's own id still on every copied line, so a file whose own
    session is F contributes to F only the records that declare F. Records that declare
    another session P are history copied from P: they are read from P's own file instead
    and skipped here, or, when P has no file left (the agent deletes transcripts after
    `cleanupPeriodDays`), kept under P so that its history survives in the copy.

    Some record types declare no session at all. The copy is a prefix, so such a record
    belongs to whatever the last record that did name a session belonged to, which
    `declared` carries forward. For an agent that never writes a foreign session id,
    every record here is the file's own and none of this does anything.
    """
    declared = session.session_id
    lines = archive.iter_lines(connection, archived.path)
    sidecar = archive.read_file(connection, archived.sidecar) if archived.sidecar else None
    for event in adapter.events(
        lines, archived.path, session.session_id, archived.agent_id, sidecar
    ):
        if not event.known_type:
            entry = unknown.setdefault((event.record_type, event.source_version), [0, None])
            entry[0] += 1
            if entry[1] is None:
                # When the record carries no time of its own, the moment Prudence first
                # stored the file is the earliest time the record is known to have
                # existed. It is chosen over the session's or the file's first timestamp
                # because `archive_file.first_seen` is NOT NULL and so is always there,
                # and because it is stored rather than recomputed, which is what makes
                # two rebuilds of one archive identical.
                entry[1] = event.timestamp or archived.archived_at
        if event.session_id is not None:
            declared = event.session_id
        owner = session
        if declared != session.session_id:
            session.forked_from = declared
            if event.stable_id:
                # A derived id names the same record differently in every file that
                # copies it, so it could not be looked up in the parent's own records.
                session.fork_point = event.record_id
            if declared in ownership.own_files:
                session.replayed += 1
                session.resumed = True
                continue
            owner = ownership.orphans.setdefault(
                declared,
                _Session(
                    session_id=declared,
                    repo_key=session.repo_key,
                    capture_level=session.capture_level,
                    mapping_method=session.mapping_method,
                ),
            )
        if event.record_id in seen_records or _replayed_reply(event, owner, ownership):
            # The second ownership rule: a record two sessions each claim as their own
            # stays with the one that claimed it first, and the files are read oldest
            # first (`_transcripts_in_order`), so that is the session that began earlier.
            # A copied reply is recognised by its reply id too, whatever its record id.
            session.replayed += 1
            session.resumed = True
            continue
        seen_records.add(event.record_id)
        _fold_event(owner, event, key, archived.agent_id)


def _replayed_reply(event: base.Event, owner: _Session, ownership: _Ownership) -> bool:
    """Whether this record is part of a reply another session already claimed."""
    if event.message_id is None:
        return False
    return ownership.replies.setdefault(event.message_id, owner.session_id) != owner.session_id


def _fold_event(session: _Session, event: base.Event, key: bytes, agent: str | None) -> None:
    """One record: its own row, its turn, its reply, and whatever payloads it carried.

    `agent` names the subagent whose log the record was read from, None for the
    session's own transcript. A subagent's record gets its turn later (`Link`), when
    the call that dispatched the agent can be looked up in whichever file it is in.
    """
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
    turn_id: str | None = None
    link: Link | None = None
    if agent is None:
        turn_id = _turn_id(event, session)
        _note_turn(session, turn_id, stamp, event)
    else:
        # Only some of an agent's records carry a prompt id; the rest are in the same
        # turn as the last one that did, which is the fallback link.
        if event.prompt_id is not None:
            session.agent_prompts[agent] = event.prompt_id
        link = Link(agent, stamp, session.agent_prompts.get(agent))
        if event.dispatch_id is not None:
            session.dispatched_by_sidecar[agent] = event.dispatch_id
    reply = _reply_of(session, event, turn_id, link)
    for payload in event.payloads:
        if isinstance(payload, base.Usage):
            if reply is not None:
                reply.usage = payload
                reply.usage_record = reply.usage_record or event.record_id
        elif isinstance(payload, base.ToolCall):
            _note_call(session, turn_id, link, event.record_id, stamp, payload)
            if reply is not None:
                _note_reply_call(reply, payload)
        elif isinstance(payload, base.ToolResult):
            _note_result(session, payload, key)


def _turn_id(event: base.Event, session: _Session) -> str:
    """The turn a record of the session's own transcript belongs to.

    A record carrying a prompt id opens or continues that turn; a prompt without one (an
    old format) opens the next numbered turn; every other record belongs to the turn open
    when it was written. Records before the first prompt belong to `<session>:0`.
    """
    if event.prompt_id is not None:
        session.current_turn = event.prompt_id
    elif any(isinstance(payload, base.Prompt) for payload in event.payloads):
        session.ordinal += 1
        session.current_turn = f"{session.session_id}:{session.ordinal}"
    return session.current_turn or f"{session.session_id}:0"


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


def _reply_of(
    session: _Session, event: base.Event, turn_id: str | None, link: Link | None
) -> _Reply | None:
    """The reply this record is part of, opened by its first record.

    A record with no reply id is not part of a reply, unless it carries usage: that is a
    record the adapter could not read, and it becomes a reply of its own with no bucket,
    so its tokens are counted as a coverage gap rather than lost.
    """
    reply_id = event.message_id
    gap = reply_id is None
    if gap:
        if not any(isinstance(payload, base.Usage) for payload in event.payloads):
            return None
        reply_id = event.record_id
    reply = session.replies.get(reply_id)
    if reply is None:
        reply = _Reply(
            session_id=session.session_id,
            turn_id=turn_id,
            link=link,
            agent_id=link.agent_id if link else None,
            started_at=event.timestamp,
            gap=gap,
        )
        session.replies[reply_id] = reply
    return reply


def _note_reply_call(reply: _Reply, call: base.ToolCall) -> None:
    """One tool call's part in its reply's bucket, and the two counts beside it."""
    kind = buckets.call_kind(call.tool_name, call.shell_command)
    reply.kinds.append(kind)
    if kind[0] == buckets.CHANGE and call.file_path:
        reply.files.add(call.file_path)
    if call.shell_command is not None:
        reply.commands += 1


def _note_call(
    session: _Session,
    turn_id: str | None,
    link: Link | None,
    record_id: str,
    stamp: str | None,
    call: base.ToolCall,
) -> None:
    """A tool the agent invoked, waiting for the result that arrives records later."""
    held = session.tool_calls.setdefault(call.call_id, _ToolCall(session.session_id))
    held.record_id = record_id
    held.turn_id = turn_id
    held.link = link
    if call.sends_to_agent is not None:
        session.sends.setdefault(call.sends_to_agent, []).append(call.call_id)
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
    if result.started_agent is not None:
        session.dispatched_by_result.setdefault(result.started_agent, result.call_id)
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
    _resolve_agent_turns(session)
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
    _flush_replies(connection, session, stats)
    _flush_edits(connection, session, stats, resolver, key)
    _flush_commands(connection, session, stats)
    connection.execute(
        "INSERT OR REPLACE INTO session__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            session.forked_from,
            session.fork_point,
        ),
    )
    stats.sessions += 1
    stats.replayed_records += session.replayed


def _resolve_agent_turns(session: _Session) -> None:
    """Give every subagent record's call and reply the turn of the call that started it.

    Done once the session's every file is read, because the dispatching call is in the
    parent's transcript (or another agent's log) and the replies are in the agent's own.
    """
    turns = AgentTurns(
        {
            call_id: Call(call.started_at, call.turn_id, call.link)
            for call_id, call in session.tool_calls.items()
        },
        session.dispatched_by_sidecar,
        session.dispatched_by_result,
        session.sends,
    )
    for call in session.tool_calls.values():
        if call.link is not None:
            call.turn_id = turns.turn_of(call.link)
    for reply in session.replies.values():
        if reply.link is not None:
            reply.turn_id = turns.turn_of(reply.link)


def _flush_replies(connection: sqlite3.Connection, session: _Session, stats: BuildStats) -> None:
    """One `usage` row and one `response` row per reply of the model.

    `usage` keeps its shape (the first record that reported the usage names the row) but
    now holds the reply's final counts; `response` adds the bucket, the turn and the
    counts of calls by kind. A reply with no usage at all (a format that wrote none) has
    no `usage` row and NULL tokens on its `response` row, which is not zero.
    """
    usage_rows: list[tuple] = []
    response_rows: list[tuple] = []
    for reply_id, reply in sorted(session.replies.items()):
        usage = reply.usage
        counts = (
            (
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_creation_tokens,
            )
            if usage is not None
            else (None, None, None, None)
        )
        if usage is not None:
            usage_rows.append(
                (
                    reply.usage_record,
                    session.session_id,
                    reply.turn_id,
                    usage.request_id,
                    usage.model,
                    *counts,
                    PARSER_VERSION,
                )
            )
        if reply.gap:
            bucket, guessed = None, False
        else:
            bucket, guessed = buckets.bucket_of(reply.kinds)
        by_kind = Counter(kind for kind, _ in reply.kinds)
        response_rows.append(
            (
                reply_id,
                session.session_id,
                reply.turn_id,
                reply.agent_id,
                reply.started_at,
                bucket,
                buckets.BUCKET_RULE_VERSION,
                1 if guessed else 0,
                *counts,
                len(reply.kinds),
                *(by_kind[name] for name in buckets.BUCKETS),
                len(reply.files),
                reply.commands,
                PARSER_VERSION,
            )
        )
    connection.executemany(
        "INSERT OR REPLACE INTO usage__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", usage_rows
    )
    connection.executemany(
        "INSERT OR REPLACE INTO response__new VALUES"
        " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        response_rows,
    )
    stats.usage_rows += len(usage_rows)
    stats.usage_tokens += sum(sum(value or 0 for value in row[5:9]) for row in usage_rows)
    stats.responses += len(response_rows)


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
