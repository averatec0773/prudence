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
   `parse_plan.transcripts_in_order`'s rule: the files are read in that order and the
   first claim wins, with the later session counting the record in `replayed_records`.
   It covers the
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
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from prudence import config, sources
from prudence.sources import base
from prudence.store import buckets, parse_plan, parse_pool, parse_state, repos, run_warnings, tokens
from prudence.store import commits as commits_module
from prudence.store import edits as edits_module
from prudence.store import lines as lines_module
from prudence.store import meta as meta_module
from prudence.store import progress as progress_module
from prudence.store.agent_turns import AgentTurns, Call, Link

PARSER_VERSION = 7

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
            tool_use_id TEXT NOT NULL,
            edit_index INTEGER NOT NULL DEFAULT 0,
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
            parser_version INTEGER NOT NULL,
            PRIMARY KEY(tool_use_id, edit_index)
        )""",
    "edit_line": """
        CREATE TABLE {name}(
            tool_use_id TEXT NOT NULL,
            edit_index INTEGER NOT NULL DEFAULT 0,
            side TEXT NOT NULL,
            line_hash TEXT NOT NULL,
            PRIMARY KEY(tool_use_id, edit_index, side, line_hash)
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
            total_input_tokens INTEGER,
            reasoning_output_tokens INTEGER,
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
            total_input_tokens INTEGER,
            reasoning_output_tokens INTEGER,
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
    # How this parse went about it. `mode` is "full" or "incremental", and `full_reason`
    # says why a parse read everything. The counts are of files read and not read, and of
    # the sessions read; the table counts above are what the tables hold afterwards.
    mode: str = "full"
    full_reason: str | None = None
    workers: int = 1
    files_total: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    sessions_parsed: int = 0


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
    edits: tuple[edits_module.EditFacts, ...] = ()
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
    # The calls whose kind is only a guess from the tool's name, for the run log.
    guessed: list[tuple[str | None, str]] = field(default_factory=list)
    call_ids: list[str] = field(default_factory=list)
    commands: int = 0


@dataclass
class _Session:
    """One session under construction, from every file that carries a record of it."""

    session_id: str
    repo_key: str | None
    capture_level: str
    kind: str = sources.DEFAULT_KIND
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
    incremental: bool = False,
    workers: int = 1,
    warnings: run_warnings.Warnings | None = None,
) -> BuildStats:
    """Build the session tables from the archive. Idempotent; safe to run at any time.

    `incremental=False` (what `rebuild` asks for) reads every archived file and swaps
    every table whole. `incremental=True` (what `ingest` asks for) reads only the
    sessions `parse_plan.to_parse` cannot prove unchanged and replaces their rows,
    keeping every other session's rows as they are; the two leave the same tables
    behind, which `tests/test_incremental.py` asserts after sequences of ingests.

    Either way the whole parse is one transaction, from the first row written to the
    swap or the replacement, so a reader sees the tables from before or from after and
    nothing between. It is also what makes the parse fast: written one statement at a
    time, it committed two thousand times, and those commits were most of its cost on
    the founder's store (216 s of it against 62 s in one transaction, one worker). The
    write lock is held for as long, which is seconds for an ingest.

    What the parse met and could not fully read goes to `warnings`, from the files it
    read: a pass an incremental parse throws away (`outcome.discard`) reports nothing.
    """
    started = time.monotonic()
    stats = BuildStats(workers=max(1, workers))
    progress = progress or progress_module.silent()
    resolver = resolver if resolver is not None else repos.resolver(connection)
    adapter = sources.source()
    key = lines_module.load_key()
    current_key = parse_state.parser_key(key, ",".join(config.SOURCE_KINDS), PARSER_VERSION)
    planned = parse_plan.plan(connection, adapter, resolver, levels)
    stats.mapping_methods = Counter(item.mapping_method for item in planned)
    stats.unassigned_sessions = sum(1 for item in planned if item.repo_key is None)
    roots = parse_plan.roots(resolver)
    previous = parse_state.load(connection) if incremental else None
    reparsed, reason = (
        parse_plan.to_parse(connection, previous, planned, current_key, roots)
        if incremental
        else (None, "rebuild")
    )
    stats.files_total = sum(len(item.archived) for item in planned)
    if reparsed is None:
        stats.mode, stats.full_reason = "full", reason
        with _transaction(connection):
            fold = _parse(connection, planned, None, set(), key, resolver, adapter, progress, stats)
            _write_full(connection, fold, planned, current_key, roots)
    else:
        assert previous is not None
        stats.mode = "incremental"
        while True:
            stored = set(previous.sessions) - reparsed
            with _transaction(connection) as outcome:
                fold = _parse(
                    connection, planned, reparsed, stored, key, resolver, adapter, progress, stats
                )
                missed = (fold.cascade | _collisions(connection, fold.written())) - reparsed
                if missed:
                    # What this pass wrote is discarded, and the parse runs again with the
                    # sessions it found it depends on.
                    outcome.discard = True
                else:
                    _write_incremental(connection, fold, planned, previous, roots)
            if not missed:
                break
            reparsed = previous.closure(reparsed | missed)
    if warnings is not None:
        _report(fold, warnings)
    repos.save_discoveries(connection, resolver)
    _count_tables(connection, stats)
    stats.elapsed = time.monotonic() - started
    return stats


def _project(resolver: repos.Resolver, repo_key: str | None) -> str:
    """A repository's own name, for the progress label. Not every session has one."""
    repository = resolver.repositories.get(repo_key) if repo_key else None
    return repository.name if repository else "an unassigned session"


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts per derived table, or -1 when the table has not been built yet."""
    result: dict[str, int] = {}
    for table in TABLES:
        try:
            result[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            result[table] = -1
    return result


class _Fold:
    """What one parse carries from session to session, beyond the session in hand.

    `claims` and `replies` are the second ownership rule: the session that claimed each
    record and each reply first. In an incremental parse, a record or reply first claimed
    by a session whose rows are kept is looked up in the stored tables instead
    (`prefetch`); such a claim still wins when that session comes earlier in the reading
    order, and when it does not, the session is sent to `cascade` to be read again too.

    `links` is what `parse_state` stores for the next parse, and `unknown` is the record
    types this parse did not know, per file, so that the next parse can add the files it
    did not read back in.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        own_files: set[str],
        positions: dict[str, tuple[str, str]],
        reparsed: set[str] | None,
        stored_sessions: set[str],
    ) -> None:
        self.connection = connection
        self.own_files = own_files
        self.positions = positions
        self.incremental = reparsed is not None
        self.reparsed = reparsed or set()
        self.stored_sessions = stored_sessions
        self.claims: dict[str, str] = {}
        self.replies: dict[str, str] = {}
        self.orphans: dict[str, _Session] = {}
        self.links: set[tuple[str, str]] = set()
        self.cascade: set[str] = set()
        self.unknown: dict[str, dict[tuple[str, str | None], list]] = {}
        # For the run log only (`_report`): the key shapes of the unknown records, the
        # lines that were not records, the subagents no call placed, and the calls whose
        # bucket is a guess (tool name -> calls, tokens resting on the guess).
        self.shapes: dict[str, set[tuple[str, ...]]] = {}
        self.unreadable: list[tuple[str, str, int | None]] = []
        self.unattached: list[tuple[str, str, str]] = []
        self.heuristic: dict[str | None, list[int]] = {}
        self.produced: dict[tuple[str, str], str] = {}
        self.read: set[str] = set()
        self._stored_records: dict[str, str] = {}
        self._stored_replies: dict[str, str] = {}

    def written(self) -> set[str]:
        """Every session whose rows this parse replaces."""
        return self.reparsed | self.read | set(self.orphans)

    def prefetch(self, events: list[base.Event]) -> None:
        """Who holds the claims these events will ask about, among the rows kept."""
        if not self.incremental:
            return
        records = [event.record_id for event in events if event.record_id not in self.claims]
        replies = [event.message_id for event in events if event.message_id is not None]
        for query, ids, into in (
            (
                "SELECT record_id, session_id FROM record WHERE record_id IN",
                records,
                self._stored_records,
            ),
            (
                "SELECT reply_id, session_id FROM parse_reply WHERE reply_id IN",
                replies,
                self._stored_replies,
            ),
        ):
            for start in range(0, len(ids), 500):
                batch = ids[start : start + 500]
                marks = ", ".join("?" * len(batch))
                for found, owner in self.connection.execute(f"{query} ({marks})", batch):
                    if owner not in self.reparsed:
                        into[found] = owner

    def record_claimant(self, record_id: str) -> tuple[str | None, bool]:
        """The session that claimed a record first, and whether that is a kept claim."""
        claimant = self.claims.get(record_id)
        if claimant is not None:
            return claimant, False
        stored = self._stored_records.get(record_id)
        return stored, stored is not None

    def reply_claimant(self, reply_id: str, owner: str) -> tuple[str | None, bool]:
        """Who claimed this reply if not `owner`; claims it for `owner` if nobody has."""
        claimant = self.replies.get(reply_id)
        if claimant is None:
            stored = self._stored_replies.get(reply_id)
            if stored is not None:
                return stored, True
            self.replies[reply_id] = owner
            return None, False
        return (None, False) if claimant == owner else (claimant, False)

    def lost(self, claimant: str, reader: str, stored: bool) -> None:
        """`reader` carries a record or reply `claimant` owns. Remember it; check it."""
        self.links.add((claimant, reader))
        if not stored:
            return
        position = self.positions.get(claimant) if claimant in self.own_files else None
        if position is None or position >= self.positions[reader]:
            self.cascade.add(claimant)

    def orphan(self, declared: str, reader: _Session) -> _Session:
        """The session a record declares when that session has no file of its own."""
        self.links.add((declared, reader.session_id))
        self.links.add((reader.session_id, declared))
        if declared in self.stored_sessions:
            self.cascade.add(declared)
        return self.orphans.setdefault(
            declared,
            _Session(
                session_id=declared,
                repo_key=reader.repo_key,
                capture_level=reader.capture_level,
                kind=reader.kind,
                mapping_method=reader.mapping_method,
            ),
        )

    def produce(self, table: str, key: str, session_id: str) -> None:
        """A primary key written; two sessions writing one are linked both ways."""
        other = self.produced.setdefault((table, key), session_id)
        if other != session_id:
            self.links.add((other, session_id))
            self.links.add((session_id, other))


def _parse(
    connection: sqlite3.Connection,
    planned: list[parse_plan.Planned],
    reparsed: set[str] | None,
    stored_sessions: set[str],
    key: bytes,
    resolver: repos.Resolver,
    adapter: base.Source,
    progress: progress_module.Step,
    stats: BuildStats,
) -> _Fold:
    """Read the sessions to be parsed, in order, into the `__new` tables.

    `reparsed` None reads every session. Files are read into events by `parse_pool`,
    in as many processes as `stats.workers`, and folded here in reading order.
    """
    _create_new_tables(connection)
    fold = _Fold(
        connection,
        {item.session_id for item in planned},
        {item.session_id: item.position for item in planned},
        reparsed,
        stored_sessions,
    )
    chosen = [item for item in planned if reparsed is None or item.session_id in reparsed]
    tasks = [
        parse_pool.FileTask(
            archived.path, item.session_id, archived.agent_id, archived.sidecar, item.kind
        )
        for item in chosen
        for archived in item.files
    ]
    fold.read = {item.session_id for item in chosen}
    stats.sessions_parsed = len(chosen)
    stats.files_parsed = sum(len(item.archived) for item in chosen)
    progress.start(len(chosen), "sessions")
    with closing(parse_pool.read_all(_database(connection), tasks, stats.workers)) as reader:
        for item in chosen:
            progress.advance(label=f"Parsing {_project(resolver, item.repo_key)}")
            session = _Session(
                session_id=item.session_id,
                repo_key=item.repo_key,
                capture_level=item.capture_level,
                kind=item.kind,
                mapping_method=item.mapping_method,
            )
            for archived in item.files:
                _read_file(fold, session, archived, next(reader), key)
            _flush_session(connection, session, fold, resolver, key, item.kind)
    for session_id in sorted(fold.orphans):
        orphan = fold.orphans[session_id]
        _flush_session(connection, orphan, fold, resolver, key, orphan.kind)
    return fold


def _database(connection: sqlite3.Connection) -> Path:
    """The file behind a connection, for the worker processes to open on their own."""
    for row in connection.execute("PRAGMA database_list"):
        if row["name"] == "main":
            return Path(row["file"])
    raise RuntimeError("the store has no main database file")


def _read_file(
    fold: _Fold,
    session: _Session,
    archived: parse_plan.ArchivedFile,
    events: list[base.Event],
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
    unknown = fold.unknown.setdefault(archived.path, {})
    fold.prefetch(events)
    for event in events:
        if not event.known_type:
            if event.record_type == base.UNREADABLE:
                fold.unreadable.append((session.session_id, archived.path, event.offset))
            else:
                fold.shapes.setdefault(event.record_type, set()).add(event.key_shape)
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
            if declared in fold.own_files:
                session.replayed += 1
                session.resumed = True
                continue
            owner = fold.orphan(declared, session)
        # The second ownership rule: a record two sessions each claim as their own stays
        # with the one that claimed it first, and the files are read oldest first
        # (`parse_plan.transcripts_in_order`), so that is the session that began earlier. A copied
        # reply is recognised by its reply id too, whatever its record id.
        claimant, stored = fold.record_claimant(event.record_id)
        if claimant is None and event.message_id is not None:
            claimant, stored = fold.reply_claimant(event.message_id, owner.session_id)
        if claimant is not None:
            fold.lost(claimant, session.session_id, stored)
            session.replayed += 1
            session.resumed = True
            continue
        fold.claims[event.record_id] = owner.session_id
        _fold_event(owner, event, key, archived.agent_id)


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

    A record with no reply id is not part of a reply, unless it carries usage or a
    tool call. Usage alone is an unreadable coverage gap. A tool call whose source
    reports no usage remains a bucketed reply with NULL token counts.
    """
    reply_id = event.message_id
    gap = reply_id is None
    if gap:
        has_tool = any(isinstance(payload, base.ToolCall) for payload in event.payloads)
        if not has_tool and not any(isinstance(payload, base.Usage) for payload in event.payloads):
            return None
        reply_id = event.record_id
        gap = not has_tool
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
    reply.gap = reply.gap or event.response_gap
    return reply


def _note_reply_call(reply: _Reply, call: base.ToolCall) -> None:
    """One tool call's part in its reply's bucket, and the two counts beside it."""
    kind = buckets.call_kind(call.tool_name, call.shell_command)
    reply.kinds.append(kind)
    reply.call_ids.append(call.call_id)
    if kind[1]:
        reply.guessed.append((call.tool_name, kind[0]))
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
    held.edits = call.edits or ((call.edit,) if call.edit is not None else ())
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
        held.edits = ()
    elif result.edits or result.edit is not None:
        completed = result.edits or (result.edit,)
        proposed = {facts.file_path: facts for facts in held.edits}
        for better in completed:
            previous = proposed.get(better.file_path)
            if previous is None and len(held.edits) == 1:
                previous = held.edits[0]
            if previous is not None:
                better.file_path = better.file_path or previous.file_path
                better.is_new_file = better.is_new_file or previous.is_new_file
        held.edits = tuple(completed)
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
    fold: _Fold,
    resolver: repos.Resolver,
    key: bytes,
    kind: str,
) -> None:
    if session.record_count == 0 and not session.records:
        return
    for table, keys in (
        ("turn", session.turns),
        ("tool_call", session.tool_calls),
        ("response", session.replies),
    ):
        for row_key in keys:
            fold.produce(table, row_key, session.session_id)
    full = session.capture_level == "full"
    notes = []
    if session.resumed:
        notes.append("resumed")
        notes.append(f"replayed {session.replayed} records")
    if session.mapping_method != "cwd":
        notes.append(f"repository by {session.mapping_method}")
    _resolve_agent_turns(session, fold)
    connection.executemany(
        "INSERT OR IGNORE INTO record__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        session.records,
    )
    connection.executemany(
        "INSERT OR REPLACE INTO turn__new VALUES (?, ?, ?, ?, ?, ?)",
        [
            (turn_id, session.session_id, started, ended, chars, PARSER_VERSION)
            for turn_id, (started, ended, chars) in sorted(session.turns.items())
        ],
    )
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
    _flush_replies(connection, session, fold)
    _flush_edits(connection, session, resolver, key)
    _flush_commands(connection, session)
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


def _resolve_agent_turns(session: _Session, fold: _Fold) -> None:
    """Give every subagent record's call and reply the turn of the call that started it.

    Done once the session's every file is read, because the dispatching call is in the
    parent's transcript (or another agent's log) and the replies are in the agent's own.
    An agent no call places is noted on `fold` for the run log.
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
    agents = [reply.link.agent_id for reply in session.replies.values() if reply.link]
    for agent_id, reason in turns.unattached(agents):
        fold.unattached.append((agent_id, session.session_id, reason))


def _flush_replies(connection: sqlite3.Connection, session: _Session, fold: _Fold) -> None:
    """One `usage` row and one `response` row per reply of the model.

    `usage` keeps its shape (the first record that reported the usage names the row) but
    now holds the reply's final counts; `response` adds the bucket, the turn and the
    counts of calls by kind. A reply with no usage at all (a format that wrote none) has
    no `usage` row and NULL tokens on its `response` row, which is not zero.

    Every call bucketed by a guess is counted on `fold` under its tool, and a reply whose
    bucket rests on the guess adds its tokens under each tool that made the guess.
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
                usage.total_input_tokens,
                usage.reasoning_output_tokens,
            )
            if usage is not None
            else (None, None, None, None, None, None)
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
        _note_guesses(fold, reply, bucket if guessed else None, counts)
        files = {
            facts.file_path
            for call_id in reply.call_ids
            for facts in session.tool_calls[call_id].edits
            if facts.file_path
        }
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
                len(files),
                reply.commands,
                PARSER_VERSION,
            )
        )
    connection.executemany(
        "INSERT OR REPLACE INTO usage__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", usage_rows
    )
    connection.executemany(
        "INSERT OR REPLACE INTO response__new VALUES (" + ", ".join("?" for _ in range(22)) + ")",
        response_rows,
    )


def _note_guesses(fold: _Fold, reply: _Reply, guessed_bucket: str | None, counts: tuple) -> None:
    """One reply's calls bucketed by the name heuristic, onto `fold.heuristic`."""
    input_tokens, output_tokens, cache_read, cache_creation, total_input, _ = counts
    tokens = (
        total_input
        if total_input is not None
        else sum(count or 0 for count in (input_tokens, cache_read, cache_creation))
    ) + (output_tokens or 0)
    for tool_name, _ in reply.guessed:
        fold.heuristic.setdefault(tool_name, [0, 0])[0] += 1
    for tool_name in {tool for tool, kind in reply.guessed if kind == guessed_bucket}:
        fold.heuristic[tool_name][1] += tokens


def _report(fold: _Fold, warnings: run_warnings.Warnings) -> None:
    """What this parse met and could not fully read, onto the run's warnings."""
    for found in fold.unknown.values():
        for (record_type, version), (count, first_seen) in found.items():
            if record_type == base.UNREADABLE:
                continue
            warnings.unknown_record_type(
                record_type, version, count, first_seen, fold.shapes.get(record_type, set())
            )
    for session_id, path, offset in fold.unreadable:
        warnings.unreadable_line(session_id, path, offset)
    for agent_id, session_id, reason in fold.unattached:
        warnings.unattached_subagent(agent_id, session_id, reason)
    for tool_name, (calls, token_count) in sorted(
        fold.heuristic.items(), key=lambda item: item[0] or ""
    ):
        warnings.heuristic_bucket(tool_name, calls, token_count)


def _flush_edits(
    connection: sqlite3.Connection,
    session: _Session,
    resolver: repos.Resolver,
    key: bytes,
) -> None:
    """One row per edit, plus its keyed line hashes, which are the attribution's left side."""
    full = session.capture_level == "full"
    rows: list[tuple] = []
    line_rows: list[tuple] = []
    for tool_use_id, call in sorted(session.tool_calls.items()):
        for edit_index, facts in enumerate(call.edits):
            repo_key, rel_path = resolver.repo_of_path(facts.file_path)
            rows.append(
                (
                    tool_use_id,
                    edit_index,
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
                    (tool_use_id, edit_index, side, digest)
                    for digest in lines_module.hash_lines(key, block)
                )
    connection.executemany(
        "INSERT OR REPLACE INTO edit__new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.executemany("INSERT OR REPLACE INTO edit_line__new VALUES (?, ?, ?, ?)", line_rows)


def _flush_commands(connection: sqlite3.Connection, session: _Session) -> None:
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
    connection.executemany(
        "INSERT OR REPLACE INTO command__new VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
    )


def _unknown_totals(
    per_file: list[tuple[tuple, str, str | None, int, str | None]],
) -> list[tuple[str, str | None, int, str | None]]:
    """One row per unknown record type and version, over every file in reading order.

    The count is the sum over files; `first_seen` is the first file's, which is what a
    single pass over every file in reading order records.
    """
    totals: dict[tuple[str, str | None], list] = {}
    for _, record_type, version, count, first_seen in sorted(per_file, key=lambda row: row[0]):
        entry = totals.setdefault((record_type, version), [0, first_seen])
        entry[0] += count
    return [
        (record_type, version, count, first_seen)
        for (record_type, version), (count, first_seen) in sorted(
            totals.items(), key=lambda item: (item[0][0], item[0][1] or "")
        )
    ]


def _new_unknown(fold: _Fold, order: dict[str, tuple[str, str, int]]) -> list[tuple]:
    return [
        (order[path], record_type, version, count, first_seen)
        for path, found in fold.unknown.items()
        for (record_type, version), (count, first_seen) in found.items()
    ]


def _bookkeeping(
    fold: _Fold, planned: list[parse_plan.Planned], current_key: str
) -> dict[str, list[tuple]]:
    """The `parse_state` rows for every session this parse wrote."""
    written = fold.written()
    order = parse_plan.file_order(planned)
    files = []
    sessions = []
    for item in planned:
        if item.session_id not in written:
            continue
        sessions.append(
            (
                item.session_id,
                1,
                *item.position,
                item.repo_key,
                item.mapping_method,
                item.capture_level,
            )
        )
        for path, (generation, size, sha256) in item.archived.items():
            position = order.get(path)
            files.append(
                (
                    path,
                    item.session_id,
                    generation,
                    size,
                    sha256,
                    current_key,
                    *item.position,
                    position[2] if position else -1,
                )
            )
    own = {item.session_id for item in planned}
    for session_id, orphan in sorted(fold.orphans.items()):
        if session_id not in own:
            sessions.append(
                (
                    session_id,
                    0,
                    None,
                    None,
                    orphan.repo_key,
                    orphan.mapping_method,
                    orphan.capture_level,
                )
            )
    return {
        "parse_file": files,
        "parse_session": sessions,
        "parse_link": sorted(link for link in fold.links if link[0] != link[1]),
        "parse_reply": sorted(
            (reply_id, owner) for reply_id, owner in fold.replies.items() if owner in written
        ),
        "parse_unknown": [
            (path, record_type, version, count, first_seen)
            for path, found in sorted(fold.unknown.items())
            for (record_type, version), (count, first_seen) in found.items()
        ],
    }


def _write_bookkeeping(connection: sqlite3.Connection, rows: dict[str, list[tuple]], suffix: str):
    for table, values in rows.items():
        if values:
            marks = ", ".join("?" * len(values[0]))
            connection.executemany(f"INSERT INTO {table}{suffix} VALUES ({marks})", values)


def _write_full(
    connection: sqlite3.Connection,
    fold: _Fold,
    planned: list[parse_plan.Planned],
    current_key: str,
    roots: list[list[str]],
) -> None:
    """Every table swapped whole, with the bookkeeping that describes it, at once."""
    connection.executemany(
        "INSERT INTO unknown_record_type__new VALUES (?, ?, ?, ?)",
        _unknown_totals(_new_unknown(fold, parse_plan.file_order(planned))),
    )
    _write_bookkeeping(connection, _bookkeeping(fold, planned, current_key), "__new")
    for table in (*TABLES, *parse_state.TABLES):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
    meta_module.set_meta(connection, parse_state.PARSE_KEY, current_key)
    meta_module.set_meta(connection, parse_state.ROOTS_KEY, json.dumps(roots))
    _create_indexes(connection)


def _collisions(connection: sqlite3.Connection, written: set[str]) -> set[str]:
    """Kept sessions holding a turn, tool call or response id this parse just wrote.

    The later write of a primary key wins, so a session that shares one with a session
    being parsed has to be parsed with it; the next parse knows it from `parse_link`.
    """
    found: set[str] = set()
    names = json.dumps(sorted(written))
    for table, column in (
        ("turn", "turn_id"),
        ("tool_call", "tool_use_id"),
        ("response", "response_id"),
    ):
        found.update(
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT kept.session_id FROM {table} kept"
                f" JOIN {table}__new fresh ON fresh.{column} = kept.{column}"
                " WHERE kept.session_id NOT IN (SELECT value FROM json_each(?))",
                (names,),
            )
        )
    return found


def _write_incremental(
    connection: sqlite3.Connection,
    fold: _Fold,
    planned: list[parse_plan.Planned],
    previous: parse_state.Previous,
    roots: list[list[str]],
) -> None:
    """Replace the rows of the sessions read again, and nothing else, in one transaction.

    Chosen over building every table under a new name and swapping it in, which is what a
    full parse does: that would copy every kept row on every ingest. A reader sees the
    rows from before or the rows from after, never a session half replaced, because this
    runs inside the parse's one transaction (`build`).
    """
    written = fold.written()
    names = json.dumps(sorted(written))
    read_files = {path for item in planned if item.session_id in written for path in item.archived}
    order = parse_plan.file_order(planned)
    unknown = _new_unknown(fold, order) + [
        (order[path], record_type, version, count, first_seen)
        for path, record_type, version, count, first_seen in parse_state.unknown_rows(
            connection, set(order) - read_files
        )
    ]
    bookkeeping = _bookkeeping(fold, planned, previous.parser_key or "")
    in_written = "(SELECT value FROM json_each(?))"
    connection.execute(
        "DELETE FROM edit_line WHERE tool_use_id IN"
        f" (SELECT tool_use_id FROM edit WHERE session_id IN {in_written})",
        (names,),
    )
    for table in TABLES:
        if table in ("edit_line", "unknown_record_type"):
            continue
        connection.execute(f"DELETE FROM {table} WHERE session_id IN {in_written}", (names,))
    for table in TABLES:
        if table == "unknown_record_type":
            continue
        verb = "INSERT OR IGNORE" if table == "record" else "INSERT OR REPLACE"
        connection.execute(f"{verb} INTO {table} SELECT * FROM {table}__new")
    connection.execute("DELETE FROM unknown_record_type")
    connection.executemany(
        "INSERT INTO unknown_record_type VALUES (?, ?, ?, ?)", _unknown_totals(unknown)
    )
    connection.execute(f"DELETE FROM parse_file WHERE session_id IN {in_written}", (names,))
    connection.execute(f"DELETE FROM parse_session WHERE session_id IN {in_written}", (names,))
    connection.execute(
        f"DELETE FROM parse_link WHERE source IN {in_written} OR target IN {in_written}",
        (names, names),
    )
    connection.execute(f"DELETE FROM parse_reply WHERE session_id IN {in_written}", (names,))
    connection.execute(
        "DELETE FROM parse_unknown WHERE path IN (SELECT value FROM json_each(?))",
        (json.dumps(sorted(read_files)),),
    )
    _write_bookkeeping(connection, bookkeeping, "")
    meta_module.set_meta(connection, parse_state.ROOTS_KEY, json.dumps(roots))
    _drop_new_tables(connection)


def _count_tables(connection: sqlite3.Connection, stats: BuildStats) -> None:
    """What the tables hold now, whichever sessions this parse read."""
    one = lambda query: connection.execute(query).fetchone()[0] or 0  # noqa: E731
    stats.sessions = one("SELECT COUNT(*) FROM session")
    stats.records = one("SELECT COUNT(*) FROM record")
    stats.turns = one("SELECT COUNT(*) FROM turn")
    stats.tool_calls = one("SELECT COUNT(*) FROM tool_call")
    stats.edits = one("SELECT COUNT(*) FROM edit")
    stats.edit_lines = one("SELECT COUNT(*) FROM edit_line")
    stats.commands = one("SELECT COUNT(*) FROM command")
    stats.usage_rows = one("SELECT COUNT(*) FROM usage")
    stats.usage_tokens = one(f"SELECT SUM({tokens.total_sql()}) FROM usage")
    stats.responses = one("SELECT COUNT(*) FROM response")
    stats.unknown_types = one("SELECT COUNT(*) FROM unknown_record_type")
    stats.replayed_records = one("SELECT SUM(replayed_records) FROM session")
    stats.command_classes = Counter(
        {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT command_class, COUNT(*) FROM command GROUP BY command_class"
            )
        }
    )
    stats.files_skipped = stats.files_total - stats.files_parsed


class _Outcome:
    """Set `discard` inside `_transaction` to roll back what the block wrote."""

    discard = False


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[_Outcome]:
    """One `BEGIN IMMEDIATE`, committed when the block ends, rolled back when it raises."""
    outcome = _Outcome()
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield outcome
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("ROLLBACK" if outcome.discard else "COMMIT")


def _create_new_tables(connection: sqlite3.Connection) -> None:
    for table in TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table}__new")
        connection.execute(SCHEMA[table].format(name=f"{table}__new"))
    parse_state.create_new_tables(connection)


def _drop_new_tables(connection: sqlite3.Connection) -> None:
    for table in (*TABLES, *parse_state.TABLES):
        connection.execute(f"DROP TABLE IF EXISTS {table}__new")


def _create_indexes(connection: sqlite3.Connection) -> None:
    for statement in (*INDEXES, *parse_state.INDEXES):
        connection.execute(statement)
