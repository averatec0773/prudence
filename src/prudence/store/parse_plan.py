"""Which sessions a parse reads, in which order, and, for an ingest, which it can keep.

`store/derived.py` folds events into tables; this module decides what it folds. Every
archived transcript becomes one `Planned` session, in reading order (the order is the
second ownership rule, see `transcripts_in_order`), with its repository, the rule that
found it, its capture level and the files it is read from, before a byte of any of them
is read. For an incremental parse, `to_parse` compares that plan with what the last
parse recorded (`store/parse_state.py`) and names the sessions whose inputs moved, with
every session linked to them; everything else keeps its rows.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from prudence.sources import base
from prudence.store import archive, parse_state, repos


def _session_id(row: sqlite3.Row) -> str:
    """A transcript's session, or its path when the file carries no session id at all."""
    return row["session_id"] or row["path"]


@dataclass(frozen=True)
class ArchivedFile:
    """One archived file of a session, and what reading it needs besides its bytes."""

    path: str
    agent_id: str | None  # the subagent whose file this is; None for the session's own
    archived_at: str  # `archive_file.first_seen`: when Prudence first stored these bytes
    sidecar: str | None = None  # the archived file beside a subagent's log, if any


@dataclass(frozen=True)
class Planned:
    """One transcript session as this parse sees it, before a byte of it is read.

    `archived` is every file the parse reads for it (its own transcript, its subagent
    logs and the sidecars beside them) with the generation, size and hash the archive
    holds now, which is what `parse_state` compares with what the last parse read.
    """

    session_id: str
    path: str
    position: tuple[str, str]
    repo_key: str | None
    mapping_method: str
    capture_level: str
    files: tuple[ArchivedFile, ...]
    archived: dict[str, tuple[int, int, str | None]]


def plan(
    connection: sqlite3.Connection,
    adapter: base.Source,
    resolver: repos.Resolver,
    levels: dict[str, str],
) -> list[Planned]:
    """Every transcript session in reading order, with its repository already decided.

    Every session is resolved before any is parsed. Resolving can teach the resolver a
    worktree root (`repos.Resolver._by_pattern`), and an edit's repository is read off
    those roots when its session's rows are written; resolving all of them first means
    every edit is written against the same roots, whichever session taught them, so a
    parse of one archive does not depend on the order it learned things in.
    """
    planned = []
    for row, head in transcripts_in_order(connection, adapter):
        match = resolver.resolve(head.cwd, head.git_branch)
        repo_key = match.repo_key or row["repo_key"]
        files, archived = _files_of(connection, adapter, row)
        planned.append(
            Planned(
                session_id=_session_id(row),
                path=row["path"],
                position=(head.first_at or "", row["path"]),
                repo_key=repo_key,
                mapping_method=match.method,
                capture_level=levels.get(repo_key, "full"),
                files=tuple(files),
                archived=archived,
            )
        )
    return planned


def _files_of(
    connection: sqlite3.Connection, adapter: base.Source, row: sqlite3.Row
) -> tuple[list[ArchivedFile], dict[str, tuple[int, int, str | None]]]:
    """A session's own file first, then each subagent log the adapter recognises.

    Which of the archived subagent files are logs, and which agent each belongs to, is
    the adapter's reading of its own layout; the rest of them are archived and not read.
    Returned beside them: the archive's generation, size and hash of every file read.
    """
    stored = {
        sub["path"]: sub
        for sub in connection.execute(
            "SELECT path, first_seen, generation, size, sha256 FROM archive_file"
            " WHERE session_id = ? AND source = ?",
            (row["session_id"], base.SUBAGENT),
        )
    }
    files = [ArchivedFile(row["path"], None, row["first_seen"])]
    files += [
        ArchivedFile(log.path, log.agent_id, stored[log.path]["first_seen"], log.sidecar)
        for log in adapter.agent_logs(sorted(stored))
    ]
    archived = {row["path"]: (row["generation"], row["size"], row["sha256"])}
    for item in files[1:]:
        for path in (item.path, item.sidecar):
            if path is not None:
                sub = stored[path]
                archived[path] = (sub["generation"], sub["size"], sub["sha256"])
    return files, archived


def transcripts_in_order(
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
        (row, _head(connection, adapter, row["path"]))
        for row in connection.execute(
            "SELECT path, session_id, repo_key, first_seen, generation, size, sha256"
            " FROM archive_file WHERE source = ?",
            (base.SESSION,),
        )
    ]
    return sorted(rows, key=lambda item: (item[1].first_at or "", item[0]["path"]))


def _head(connection: sqlite3.Connection, adapter: base.Source, path: str) -> base.FileHead:
    """What a transcript's first records say, reading as little of it as answers that.

    The head is the first value of each of three fields in file order, so the lines of a
    prefix give the same answer as the whole first chunk whenever all three are found in
    it. When one is missing, the whole first chunk is read, which is what the head is
    defined over.
    """
    head = adapter.head(archive.head_lines(connection, path, archive.HEAD_PREFIX_BYTES))
    if head.first_at and head.cwd and head.git_branch:
        return head
    return adapter.head(archive.head_lines(connection, path))


def roots(resolver: repos.Resolver) -> list[list[str]]:
    """Every (repository, root) pair an edit's repository can be read off, sorted."""
    return sorted(
        [repository.repo_key, root]
        for repository in resolver.repositories.values()
        for root in repository.roots
    )


def to_parse(
    connection: sqlite3.Connection,
    previous: parse_state.Previous | None,
    planned: list[Planned],
    current_key: str,
    known_roots: list[list[str]],
) -> tuple[set[str] | None, str | None]:
    """The sessions to read again, with every session their rows depend on, or None.

    None means a full parse, with the reason: there is no bookkeeping, the parser or a
    version under it changed, a file that was read has left the archive (only `forget`
    does that), or the bookkeeping no longer names the sessions the tables hold. Anything
    else is read again when its inputs moved: a file's bytes (new, grown or rewritten),
    the set of its files, its repository, the rule that found it, its capture level, or
    the roots its edits were made relative to. `parse_state.Previous.closure` then adds
    every session linked to one of those.
    """
    if previous is None:
        return None, "no record of an earlier parse"
    if previous.parser_key != current_key or any(
        state.parser_key != current_key for state in previous.files.values()
    ):
        return None, "the parser changed"
    now = {path: item.session_id for item in planned for path in item.archived}
    if any(path not in now for path in previous.files):
        return None, "a file that was parsed has left the archive"
    held = {row[0] for row in connection.execute("SELECT session_id FROM session")}
    if held - set(previous.sessions):
        return None, "the bookkeeping does not describe the session table"

    by_session: dict[str, dict[str, parse_state.FileState]] = {}
    for path, state in previous.files.items():
        by_session.setdefault(state.session_id, {})[path] = state
    changed: set[str] = set()
    for item in planned:
        state = previous.sessions.get(item.session_id)
        read = by_session.get(item.session_id, {})
        if (
            state is None
            or not state.own_file
            or state.position != item.position
            or (state.repo_key, state.mapping_method, state.capture_level)
            != (item.repo_key, item.mapping_method, item.capture_level)
            or set(read) != set(item.archived)
            or any(
                (read[path].generation, read[path].size, read[path].sha256) != archived
                for path, archived in item.archived.items()
            )
        ):
            changed.add(item.session_id)
    if known_roots != previous.roots:
        changed |= _sessions_under(connection, known_roots, previous.roots)
    return previous.closure(changed), None


def _sessions_under(
    connection: sqlite3.Connection, roots: list[list[str]], before: list[list[str]]
) -> set[str]:
    """Sessions with an edit whose repository could be read off a root that moved.

    An edit's repository and relative path come from the longest known root above its
    file, so a root that appeared or went away can only change the edits under it. At
    `metadata-only` no path is stored to test, so every such session with an edit is
    read again.
    """
    moved = {root for _, root in {tuple(pair) for pair in roots} ^ {tuple(p) for p in before}}
    found = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT edit.session_id FROM edit JOIN session USING (session_id)"
            " WHERE session.capture_level != 'full'"
        )
    }
    for root in moved:
        prefix = root.rstrip("/") + "/"
        found.update(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT session_id FROM edit"
                " WHERE file_path = ? OR substr(file_path, 1, ?) = ?",
                (root, len(prefix), prefix),
            )
        )
    return found


def file_order(planned: list[Planned]) -> dict[str, tuple[str, str, int]]:
    """Each file's place in the reading order: its session's position, then its own."""
    return {
        archived.path: (*item.position, index)
        for item in planned
        for index, archived in enumerate(item.files)
    }
