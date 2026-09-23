"""What the last parse read, and who depends on whom, so the next one can read less.

`store/derived.py` builds the session tables from the archive. Most of the archive does
not change between two ingests, so most sessions' rows would come out exactly as they
are. This module keeps the record that lets `derived.build` prove which ones: for every
file it read, the archived generation, size and hash it read it at and under which parser;
for every session, the inputs that are not in its files (its repository, the rule that
found it, its capture level) and its place in the reading order; and the links between
sessions along which a change in one can change another's rows.

It holds bookkeeping only. No row here is a fact about the developer's work, nothing on
a surface reads it, and a store without it is simply parsed in full. The tables are
built beside the session tables and swapped with them (a full parse), or rewritten in
the same transaction as them (an incremental one), so they always describe the rows
that are there.

The links, each stored as "when `source` is parsed again, so is `target`":

- **An orphan and its readers, both ways.** A session with no file of its own is built
  from the copies its forks carry, in reading order; any change to one of them changes it.
- **A key two sessions wrote, both ways.** Turn, tool call and response ids are primary
  keys; if two sessions produce the same one, the later write wins, so neither can be
  rebuilt without the other.
- **A claim won and a claim lost, winner to loser.** When two sessions carry the same
  record or reply, the earlier one owns it and the later counts it as replayed. If the
  winner is parsed again it may stop claiming it, and then the loser owns it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import deque
from dataclasses import dataclass, field

from prudence.store import buckets
from prudence.store import edits as edits_module
from prudence.store import meta as meta_module

PARSE_KEY = "parse_key"
ROOTS_KEY = "parse_roots"

TABLES = ("parse_file", "parse_session", "parse_link", "parse_reply", "parse_unknown")

SCHEMA = {
    "parse_file": """
        CREATE TABLE {name}(
            path TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT,
            parser_key TEXT NOT NULL,
            sort_at TEXT NOT NULL,
            sort_path TEXT NOT NULL,
            file_index INTEGER NOT NULL
        )""",
    "parse_session": """
        CREATE TABLE {name}(
            session_id TEXT PRIMARY KEY,
            own_file INTEGER NOT NULL,
            sort_at TEXT,
            sort_path TEXT,
            repo_key TEXT,
            mapping_method TEXT,
            capture_level TEXT
        )""",
    "parse_link": """
        CREATE TABLE {name}(
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            PRIMARY KEY(source, target)
        ) WITHOUT ROWID""",
    "parse_reply": """
        CREATE TABLE {name}(
            reply_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL
        ) WITHOUT ROWID""",
    "parse_unknown": """
        CREATE TABLE {name}(
            path TEXT NOT NULL,
            type TEXT NOT NULL,
            claude_version TEXT,
            count INTEGER NOT NULL,
            first_seen TEXT
        )""",
}

INDEXES = (
    "CREATE INDEX IF NOT EXISTS parse_file_session ON parse_file(session_id)",
    "CREATE INDEX IF NOT EXISTS parse_link_target ON parse_link(target)",
    "CREATE INDEX IF NOT EXISTS parse_reply_session ON parse_reply(session_id)",
    "CREATE INDEX IF NOT EXISTS parse_unknown_path ON parse_unknown(path)",
)


def parser_key(line_key: bytes, kind: str, parser_version: int) -> str:
    """Every version a session's rows depend on, and which line-hash key hashed them.

    Any of these changing changes rows that nothing else would flag, so any of them
    changing is a full parse. The key itself is never stored, only a digest of it.
    """
    digest = hashlib.sha256(line_key).hexdigest()[:12]
    return (
        f"parser {parser_version}; edits {edits_module.EDIT_FACT_VERSION}; "
        f"commands {edits_module.COMMAND_FACT_VERSION}; "
        f"buckets {buckets.BUCKET_RULE_VERSION}; source {kind}; key {digest}"
    )


@dataclass(frozen=True)
class FileState:
    """One file as a parse read it."""

    session_id: str
    generation: int
    size: int
    sha256: str | None
    parser_key: str


@dataclass(frozen=True)
class SessionState:
    """One session's inputs that are not in its files, and its place in the order."""

    own_file: bool
    position: tuple[str, str] | None
    repo_key: str | None
    mapping_method: str | None
    capture_level: str | None


@dataclass
class Previous:
    """The last parse's bookkeeping, as read back."""

    parser_key: str | None
    roots: list[list[str]]
    files: dict[str, FileState] = field(default_factory=dict)
    sessions: dict[str, SessionState] = field(default_factory=dict)
    links: dict[str, set[str]] = field(default_factory=dict)

    def closure(self, sessions: set[str]) -> set[str]:
        """Every session that has to be parsed again when these are."""
        found = set(sessions)
        queue = deque(sessions)
        while queue:
            for target in self.links.get(queue.popleft(), ()):
                if target not in found:
                    found.add(target)
                    queue.append(target)
        return found


def load(connection: sqlite3.Connection) -> Previous | None:
    """The last parse's bookkeeping, or None when there is none to trust."""
    try:
        files = {
            row["path"]: FileState(
                row["session_id"],
                row["generation"],
                row["size"],
                row["sha256"],
                row["parser_key"],
            )
            for row in connection.execute("SELECT * FROM parse_file")
        }
        sessions = {
            row["session_id"]: SessionState(
                bool(row["own_file"]),
                (row["sort_at"], row["sort_path"]) if row["own_file"] else None,
                row["repo_key"],
                row["mapping_method"],
                row["capture_level"],
            )
            for row in connection.execute("SELECT * FROM parse_session")
        }
        links: dict[str, set[str]] = {}
        for row in connection.execute("SELECT source, target FROM parse_link"):
            links.setdefault(row["source"], set()).add(row["target"])
    except sqlite3.OperationalError:
        return None
    roots = json.loads(meta_module.get_meta(connection, ROOTS_KEY) or "[]")
    return Previous(
        parser_key=meta_module.get_meta(connection, PARSE_KEY),
        roots=roots,
        files=files,
        sessions=sessions,
        links=links,
    )


def create_new_tables(connection: sqlite3.Connection) -> None:
    for table in TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table}__new")
        connection.execute(SCHEMA[table].format(name=f"{table}__new"))


def unknown_rows(connection: sqlite3.Connection, paths: set[str]) -> list[tuple]:
    """The stored per-file unknown record types of files that were not read again."""
    rows = []
    for row in connection.execute("SELECT * FROM parse_unknown"):
        if row["path"] in paths:
            rows.append(
                (row["path"], row["type"], row["claude_version"], row["count"], row["first_seen"])
            )
    return rows
