"""Which session produced which commit, by three methods of decreasing trust.

The spikes settled the shape of this. Round two measured that seven commits in ten were
made by the agent inside a session, where the transcript already contains git's own
reply and no inference is needed at all; that line matching, on the only labelled data
available, is right 92.6% of the time when it answers and abstains rather than guesses
when it cannot; and that the hard population, commits the developer made outside a
session, is exactly the one no available ground truth can label. So the method is
recorded on every row, the tiers are never mixed, and every candidate is stored, not
only the winner, because ambiguity the user cannot see is ambiguity nobody can check.

1. `in_session`: the session ran `git commit` and git printed this commit's hash. Exact.
2. `git_ai_note`: another tool already wrote the answer into `refs/notes/ai` under the
   published git-ai standard. Exact when it parses, counted as unknown when it does not.
3. `line_match`: the session wrote lines this commit added, into the same path, before
   the commit was made. Top-1 by lines matched wins; the rest are kept with their rank.

Coverage is stored beside every row, because a session that explains four lines of a
four-hundred-line commit has not explained the commit, and a number without its
coverage is the kind of claim this project exists not to make.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from prudence.store.repos import Repository

FACT_VERSION = 1

METHODS = ("in_session", "git_ai_note", "line_match")
TOLERANCE = timedelta(seconds=120)
NOTES_REF = "refs/notes/ai"

SCHEMA = """
CREATE TABLE IF NOT EXISTS attribution(
    commit_hash TEXT NOT NULL,
    session_id TEXT NOT NULL,
    method TEXT NOT NULL,
    rank INTEGER NOT NULL,
    lines_matched INTEGER NOT NULL DEFAULT 0,
    coverage REAL,
    fact_version INTEGER NOT NULL,
    PRIMARY KEY (commit_hash, session_id, method)
);
CREATE INDEX IF NOT EXISTS attribution_session ON attribution(session_id, method, rank);
"""


@dataclass
class AttributionStats:
    in_session: int = 0
    git_ai_note: int = 0
    line_match_winners: int = 0
    line_match_candidates: int = 0
    commits_attributed: int = 0
    unresolved_hashes: int = 0
    unreadable_notes: int = 0
    elapsed: float = 0.0
    per_repo: dict[str, int] = field(default_factory=dict)


def build(connection: sqlite3.Connection, repositories: list[Repository]) -> AttributionStats:
    """Rebuild every attribution row. Reads the derived tables and the repositories only."""
    started = time.monotonic()
    stats = AttributionStats()
    connection.executescript(SCHEMA)
    connection.execute("DELETE FROM attribution")
    added = _added_lines(connection)
    rows: list[tuple] = []
    attributed: set[str] = set()

    for repository in repositories:
        matched = _line_match(connection, repository.repo_key)
        for commit_hash, ranked in matched.items():
            for rank, (session_id, count) in enumerate(ranked, start=1):
                rows.append(
                    _row(commit_hash, session_id, "line_match", rank, count, added.get(commit_hash))
                )
                stats.line_match_candidates += 1
                if rank == 1:
                    stats.line_match_winners += 1
                    attributed.add(commit_hash)
        stats.per_repo[repository.repo_key] = len(matched)
        for commit_hash, session_id in _in_session(connection, repository, stats):
            count = _count_for(matched, commit_hash, session_id)
            rows.append(
                _row(commit_hash, session_id, "in_session", 1, count, added.get(commit_hash))
            )
            stats.in_session += 1
            attributed.add(commit_hash)
        for commit_hash, session_id in _notes(connection, repository, stats):
            count = _count_for(matched, commit_hash, session_id)
            rows.append(
                _row(commit_hash, session_id, "git_ai_note", 1, count, added.get(commit_hash))
            )
            stats.git_ai_note += 1
            attributed.add(commit_hash)

    connection.executemany("INSERT OR REPLACE INTO attribution VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    stats.commits_attributed = len(attributed)
    stats.elapsed = time.monotonic() - started
    return stats


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Attribution rows per method, or an empty mapping before the first run."""
    try:
        rows = connection.execute(
            "SELECT method, COUNT(*) FROM attribution WHERE rank = 1 GROUP BY method"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row[0]: row[1] for row in rows}


def _row(
    commit_hash: str, session_id: str, method: str, rank: int, matched: int, added: int | None
) -> tuple:
    """Coverage is NULL, not zero, when no line evidence exists: it is unmeasured, not nil.

    An `in_session` commit in a `metadata-only` repository is the clear case. We know
    exactly which session made it and we have deliberately stored nothing to measure
    coverage with, which is a different statement from "that session explains none of it".
    """
    coverage = (matched / added) if (added and matched) else None
    return (commit_hash, session_id, method, rank, matched, coverage, FACT_VERSION)


def _added_lines(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        row[0]: row[1]
        for row in connection.execute('SELECT commit_hash, added_lines FROM "commit"')
    }


def _count_for(matched: dict[str, list[tuple[str, int]]], commit_hash: str, session_id: str) -> int:
    for candidate, count in matched.get(commit_hash, []):
        if candidate == session_id:
            return count
    return 0


def _line_match(connection: sqlite3.Connection, repo_key: str) -> dict[str, list[tuple[str, int]]]:
    """Rank the sessions that wrote a commit's added lines into the same path, first.

    Done in Python rather than in one join because the comparison is a dictionary
    lookup per commit line, which is linear, where the equivalent SQL join over two
    hash columns is not.
    """
    index: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for row in connection.execute(
        "SELECT e.session_id, e.rel_path, el.line_hash, MIN(e.edited_at) AS at"
        " FROM edit e JOIN edit_line el ON el.tool_use_id = e.tool_use_id AND el.side = 'added'"
        " WHERE e.repo_key = ? AND e.rel_path IS NOT NULL AND e.edited_at IS NOT NULL"
        " GROUP BY e.session_id, e.rel_path, el.line_hash",
        (repo_key,),
    ):
        sessions = index[(row["rel_path"], row["line_hash"])]
        earliest = sessions.get(row["session_id"])
        if earliest is None or row["at"] < earliest:
            sessions[row["session_id"]] = row["at"]
    if not index:
        return {}

    deadlines = {
        row["commit_hash"]: _deadline(row["committer_at"])
        for row in connection.execute(
            'SELECT commit_hash, committer_at FROM "commit" WHERE repo_key = ? AND is_merge = 0',
            (repo_key,),
        )
    }
    tally: Counter[tuple[str, str]] = Counter()
    for row in connection.execute(
        "SELECT cl.commit_hash, cl.path, cl.line_hash FROM commit_line cl"
        ' JOIN "commit" c ON c.commit_hash = cl.commit_hash WHERE c.repo_key = ?',
        (repo_key,),
    ):
        sessions = index.get((row["path"], row["line_hash"]))
        if not sessions:
            continue
        deadline = deadlines.get(row["commit_hash"])
        if deadline is None:
            continue
        for session_id, edited_at in sessions.items():
            if edited_at <= deadline:
                tally[(row["commit_hash"], session_id)] += 1

    ranked: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (commit_hash, session_id), count in tally.items():
        ranked[commit_hash].append((session_id, count))
    for candidates in ranked.values():
        candidates.sort(key=lambda item: (-item[1], item[0]))
    return dict(ranked)


def _deadline(committer_at: str | None) -> str:
    """The commit's own moment plus the tolerance the spike settled on, in UTC."""
    if not committer_at:
        return "9999"
    try:
        moment = datetime.fromisoformat(committer_at)
    except ValueError:
        return "9999"
    return (moment + TOLERANCE).strftime("%Y-%m-%dT%H:%M:%S")


def _in_session(
    connection: sqlite3.Connection, repository: Repository, stats: AttributionStats
) -> list[tuple[str, str]]:
    """Commits whose hash git printed inside a session, resolved to a full hash."""
    if not repository.toplevel:
        return []
    known = {
        row[0]
        for row in connection.execute(
            'SELECT commit_hash FROM "commit" WHERE repo_key = ?', (repository.repo_key,)
        )
    }
    resolved: dict[str, str | None] = {}
    pairs: list[tuple[str, str]] = []
    for row in connection.execute(
        "SELECT c.commit_hash AS short, c.session_id AS session_id FROM command c"
        " JOIN session s ON s.session_id = c.session_id"
        " WHERE c.command_class = 'git_commit' AND c.commit_hash IS NOT NULL"
        " AND s.repo_key = ?",
        (repository.repo_key,),
    ):
        short = row["short"]
        if short not in resolved:
            resolved[short] = _rev_parse(repository.toplevel, short)
        full = resolved[short]
        if full is None or full not in known:
            stats.unresolved_hashes += 1
            continue
        pairs.append((full, row["session_id"]))
    return sorted(set(pairs))


def _notes(
    connection: sqlite3.Connection, repository: Repository, stats: AttributionStats
) -> list[tuple[str, str]]:
    """Attribution another tool already wrote, read from `refs/notes/ai` when it exists."""
    if not repository.toplevel:
        return []
    if _git(repository.toplevel, "rev-parse", "--verify", "--quiet", NOTES_REF) is None:
        return []
    listing = _git(repository.toplevel, "notes", f"--ref={NOTES_REF}", "list") or ""
    sessions = {
        row[0]
        for row in connection.execute(
            "SELECT session_id FROM session WHERE repo_key = ?", (repository.repo_key,)
        )
    }
    known = {
        row[0]
        for row in connection.execute(
            'SELECT commit_hash FROM "commit" WHERE repo_key = ?', (repository.repo_key,)
        )
    }
    pairs: list[tuple[str, str]] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[1] not in known:
            continue
        note = _git(repository.toplevel, "notes", f"--ref={NOTES_REF}", "show", parts[1])
        named = parse_note(note)
        if named is None:
            stats.unreadable_notes += 1
            continue
        for session_id in named:
            if session_id in sessions:
                pairs.append((parts[1], session_id))
    return sorted(set(pairs))


def parse_note(note: str | None) -> set[str] | None:
    """Session ids named by a git-ai note, or None when it is not the format we expect.

    The standard puts attestation lines first, then a line containing exactly `---`,
    then a JSON object whose `sessions` map carries the agent's own conversation id.
    Anything else is counted as unknown rather than guessed at.
    """
    if not note:
        return None
    _, separator, payload = note.partition("\n---\n")
    if not separator:
        return None
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("sessions"), dict):
        return None
    named: set[str] = set()
    for entry in parsed["sessions"].values():
        agent = entry.get("agent_id") if isinstance(entry, dict) else None
        if isinstance(agent, dict) and isinstance(agent.get("id"), str):
            named.add(agent["id"])
    return named


def _rev_parse(directory: str, short: str) -> str | None:
    if not short or len(short) < 4:
        return None
    return _git(directory, "rev-parse", "--verify", "--quiet", f"{short}^{{commit}}")


def _git(directory: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
