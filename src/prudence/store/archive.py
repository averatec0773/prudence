"""The archive: the agent's own bytes, kept unmodified.

Everything Prudence derives can be wrong and thrown away; the archive is what makes
that safe. So this module does as little as possible to the data: it compresses each
run's new bytes and stores them against the file path and the byte offset they began
at, and it never rewrites a chunk it has already written.

Two facts about the sources shape the design. Desktop transcripts never end, so a
file grows between runs and only the appended bytes are read. And a file can be
replaced (Claude Code rewrites a transcript on compaction, and the operating system
reuses names), so the stored prefix is verified before bytes are treated as an
append; when it does not match, the file is archived again from offset zero and the
earlier chunks are marked superseded rather than deleted.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from prudence.paths import claude_file_history_dir, claude_projects_dir, spool_file
from prudence.sources import claude_code
from prudence.store.identity import identify
from prudence.store.repos import Resolver

CHUNK_BYTES = 4 * 1024 * 1024
READ_BLOCK = 1024 * 1024
COMPRESSION = "zlib"


@dataclass(frozen=True)
class Target:
    """One file to archive, and what it belongs to."""

    path: Path
    source: str  # transcript, subagent, tool-result, file-history, spool
    session_id: str | None
    repo_key: str | None


@dataclass
class IngestStats:
    files_seen: int = 0
    new_files: int = 0
    new_bytes: int = 0
    unchanged_files: int = 0
    rearchived_files: int = 0
    missing_files: int = 0
    elapsed: float = 0.0


def collect_targets(
    enabled_keys: set[str],
    projects_dir: Path | None = None,
    file_history_dir: Path | None = None,
    resolver: Resolver | None = None,
) -> list[Target]:
    """Every file belonging to an enabled repository: transcript, subagents, spills, history.

    A session's repository comes from the first record's working directory. When that
    directory no longer exists, which is the normal case for a Claude Desktop worktree,
    `store.repos` maps it back by prefix or pattern and the session is archived like any
    other. Without a resolver only the directory itself is consulted.
    """
    root = projects_dir or claude_projects_dir()
    history_root = file_history_dir or claude_file_history_dir()
    targets: list[Target] = []
    for path in claude_code.list_session_files(root):
        session = claude_code.read_session_file(path)
        key = _repo_key(session, resolver)
        if key is None or key not in enabled_keys:
            continue
        targets.append(Target(path, "transcript", session.session_id, key))
        session_dir = path.parent / session.session_id
        targets.extend(_files_in(session_dir / "subagents", "subagent", session.session_id, key))
        targets.extend(
            _files_in(session_dir / "tool-results", "tool-result", session.session_id, key)
        )
        targets.extend(
            _files_in(history_root / session.session_id, "file-history", session.session_id, key)
        )
    return targets


def spool_targets(path: Path | None = None) -> list[Target]:
    """Prudence's own hook spool, archived like anything else.

    Rule 1 is not only about Claude Code's bytes. The spool is append-only and is never
    truncated, so it is read incrementally by offset exactly like a growing transcript,
    and `hook_event` is rebuilt from the archived copy rather than from the live file.
    A session and a repository are resolved later, from the `cwd` on each line, so the
    file itself belongs to neither.
    """
    target = path or spool_file()
    return [Target(target, "spool", None, None)] if target.is_file() else []


def archive(connection: sqlite3.Connection, targets: list[Target]) -> IngestStats:
    """Store whatever of each target is not stored yet. Safe to run at any moment."""
    started = time.monotonic()
    stats = IngestStats()
    now = datetime.now(UTC).isoformat()
    for target in targets:
        stats.files_seen += 1
        try:
            info = target.path.stat()
        except OSError:
            stats.missing_files += 1
            continue
        row = connection.execute(
            "SELECT size, mtime, sha256, generation FROM archive_file WHERE path = ?",
            (str(target.path),),
        ).fetchone()
        if row is None:
            _store(connection, target, 0, generation=0, now=now, first_seen=now, stats=stats)
            stats.new_files += 1
            continue
        if info.st_size == row["size"] and info.st_mtime == row["mtime"]:
            connection.execute(
                "UPDATE archive_file SET last_seen = ? WHERE path = ?", (now, str(target.path))
            )
            stats.unchanged_files += 1
            continue
        prefix_ok = info.st_size >= row["size"] and _prefix_matches(
            target.path, row["size"], row["sha256"]
        )
        if not prefix_ok:
            connection.execute(
                "UPDATE archive_chunk SET superseded = 1 WHERE path = ? AND generation = ?",
                (str(target.path), row["generation"]),
            )
            _store(
                connection,
                target,
                0,
                generation=row["generation"] + 1,
                now=now,
                first_seen=None,
                stats=stats,
            )
            stats.rearchived_files += 1
            continue
        if info.st_size == row["size"]:
            connection.execute(
                "UPDATE archive_file SET mtime = ?, last_seen = ? WHERE path = ?",
                (info.st_mtime, now, str(target.path)),
            )
            stats.unchanged_files += 1
            continue
        _store(
            connection,
            target,
            row["size"],
            generation=row["generation"],
            now=now,
            first_seen=None,
            stats=stats,
        )
    stats.elapsed = time.monotonic() - started
    return stats


def read_file(connection: sqlite3.Connection, path: str) -> bytes:
    """The archived bytes of one file, reassembled. Used by the derived-table build."""
    return b"".join(chunk for _, chunk in iter_chunks(connection, path))


def iter_chunks(connection: sqlite3.Connection, path: str) -> Iterator[tuple[int, bytes]]:
    """Live chunks of one file in order, as (offset, decompressed bytes)."""
    rows = connection.execute(
        'SELECT "offset", data FROM archive_chunk '
        'WHERE path = ? AND superseded = 0 ORDER BY "offset"',
        (path,),
    )
    for row in rows:
        yield row["offset"], zlib.decompress(row["data"])


def iter_lines(connection: sqlite3.Connection, path: str) -> Iterator[tuple[int, bytes]]:
    """Whole lines of one archived file as (byte offset of the line, line without newline).

    Chunk boundaries fall wherever the file happened to stop growing, so a line can be
    split across two chunks and the tail of a file can be a line still being written.
    """
    buffer = b""
    line_offset = 0
    for _, chunk in iter_chunks(connection, path):
        buffer += chunk
        while True:
            index = buffer.find(b"\n")
            if index < 0:
                break
            line = buffer[:index]
            yield line_offset, line
            line_offset += index + 1
            buffer = buffer[index + 1 :]
    if buffer.strip():
        yield line_offset, buffer


def head_lines(connection: sqlite3.Connection, path: str) -> list[bytes]:
    """The lines of a file's first chunk. Enough to learn when a session started."""
    row = connection.execute(
        'SELECT data FROM archive_chunk WHERE path = ? AND superseded = 0 ORDER BY "offset"'
        " LIMIT 1",
        (path,),
    ).fetchone()
    return zlib.decompress(row["data"]).split(b"\n") if row else []


def archive_totals(connection: sqlite3.Connection) -> tuple[int, int, int]:
    """Files archived, their total original size, and the compressed bytes stored."""
    row = connection.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file"
    ).fetchone()
    stored = connection.execute(
        "SELECT COALESCE(SUM(LENGTH(data)), 0) AS stored FROM archive_chunk WHERE superseded = 0"
    ).fetchone()
    return row["files"], row["size"], stored["stored"]


def _repo_key(session: claude_code.SessionFile, resolver: Resolver | None) -> str | None:
    if resolver is not None:
        return resolver.resolve(session.cwd, session.git_branch).repo_key
    identity = identify(session.cwd) if session.cwd else None
    return identity.key if identity else None


def _files_in(directory: Path, source: str, session_id: str, repo_key: str) -> list[Target]:
    if not directory.is_dir():
        return []
    return [
        Target(path, source, session_id, repo_key)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def _prefix_matches(path: Path, size: int, expected_sha: str | None) -> bool:
    """Is the file still the file we archived, or did something rewrite it under us?"""
    if expected_sha is None:
        return False
    digest = hashlib.sha256()
    remaining = size
    with path.open("rb") as handle:
        while remaining > 0:
            block = handle.read(min(READ_BLOCK, remaining))
            if not block:
                return False
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest() == expected_sha


def _store(
    connection: sqlite3.Connection,
    target: Target,
    start: int,
    generation: int,
    now: str,
    first_seen: str | None,
    stats: IngestStats,
) -> None:
    """Read from `start` to the end of the file, storing compressed chunks as we go."""
    digest = hashlib.sha256()
    offset = 0
    pending = bytearray()
    pending_offset = start
    written = 0
    with target.path.open("rb") as handle:
        while True:
            block = handle.read(READ_BLOCK)
            if not block:
                break
            digest.update(block)
            if offset + len(block) > start:
                wanted = block[max(0, start - offset) :]
                pending.extend(wanted)
                while len(pending) >= CHUNK_BYTES:
                    written += _write_chunk(
                        connection,
                        target.path,
                        pending_offset,
                        bytes(pending[:CHUNK_BYTES]),
                        generation,
                    )
                    pending_offset += CHUNK_BYTES
                    del pending[:CHUNK_BYTES]
            offset += len(block)
    if pending:
        written += _write_chunk(connection, target.path, pending_offset, bytes(pending), generation)
    stats.new_bytes += written
    info = target.path.stat()
    connection.execute(
        "INSERT INTO archive_file"
        "(path, source, session_id, repo_key, size, mtime, sha256, first_seen, last_seen,"
        " generation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET source = excluded.source,"
        " session_id = excluded.session_id, repo_key = excluded.repo_key,"
        " size = excluded.size, mtime = excluded.mtime, sha256 = excluded.sha256,"
        " last_seen = excluded.last_seen, generation = excluded.generation",
        (
            str(target.path),
            target.source,
            target.session_id,
            target.repo_key,
            offset,
            info.st_mtime,
            digest.hexdigest(),
            first_seen or now,
            now,
            generation,
        ),
    )


def _write_chunk(
    connection: sqlite3.Connection, path: Path, offset: int, data: bytes, generation: int
) -> int:
    connection.execute(
        'INSERT INTO archive_chunk(path, "offset", length, compression, data, generation,'
        " superseded) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (str(path), offset, len(data), COMPRESSION, zlib.compress(data, 6), generation),
    )
    return len(data)
