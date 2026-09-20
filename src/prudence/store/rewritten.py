"""Commits the agent made and git then rewrote, found again by time and by lines.

Round two of the attribution spike measured that a quarter of the short hashes the
agent printed name no object at all any more, and two thirds in the worst repository:
a rebase, a squash merge or a reset writes a new commit and garbage collection removes
the old one. The M2 plan proposed recognising those commits by patch id. That cannot
work, and this module does something else instead: a patch id is computed from a commit
object, and the printed hash's commit object is exactly what no longer exists. There is
nothing left to compute an id from, and the surviving commit's own patch id has nothing
to be compared against. The plan's idea is therefore replaced here, not implemented.

What survives a rewrite is the work, and two facts about it that Prudence already
holds: when the session ran `git commit`, and which lines that session had written.
So the rule is:

    A reachable commit that no session is credited with `in_session`, whose committer
    date falls inside the five minutes after an in-session `git commit` call whose own
    printed hash no longer resolves, and whose added lines overlap the lines that
    session wrote, is that session's commit. It is recorded as `in_session` with
    `method_note = 'rewritten'`, and the printed hash is kept in `commit_alias`.

The guard against coincidence is the overlap: at least five of the commit's added lines
must be lines that session wrote, or, for a commit with fewer than five added lines in
the store, all of them. A repository at `metadata-only` stores no lines at all, so
nothing is ever re-identified there; a timing coincidence alone is not evidence.

`git commit --amend` inside a session prints a second, different hash for the same
work, and both printed hashes are then dead. Only the latest call inside the window is
kept, because the last hash printed is the one the amended commit actually carries.

The mapping is one to one in both directions. A dead hash named exactly one commit when
it was printed, so when two surviving commits both fit one printed hash, the one that
overlaps the session's lines most keeps it and the other is left to line matching. On
the founder's store that happened once in nine.
"""

from __future__ import annotations

import bisect
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from prudence.store.commits import utc

FACT_VERSION = 1

# How long after a `git commit` call the commit it made may be dated.
WINDOW = timedelta(minutes=5)

# Added lines of the commit that the session must have written, unless the commit has
# fewer than this many added lines in the store, in which case it must have all of them.
MIN_OVERLAP = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS commit_alias(
    printed_hash TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    session_id TEXT NOT NULL,
    fact_version INTEGER NOT NULL,
    PRIMARY KEY (printed_hash, commit_hash, session_id)
);
CREATE INDEX IF NOT EXISTS commit_alias_commit ON commit_alias(commit_hash);
CREATE INDEX IF NOT EXISTS commit_alias_session ON commit_alias(session_id);
"""


@dataclass(frozen=True)
class Call:
    """One in-session `git commit` whose printed short hash no longer resolves."""

    printed_hash: str
    session_id: str
    called_at: str | None


@dataclass(frozen=True)
class Alias:
    """One rewritten commit, found again: the dead hash, the live commit, the session."""

    printed_hash: str
    commit_hash: str
    session_id: str
    lines_matched: int


def reidentify(
    connection: sqlite3.Connection,
    repo_key: str,
    calls: list[Call],
    matched: dict[str, list[tuple[str, int]]],
    already: set[str],
) -> list[Alias]:
    """Rewritten commits of one repository, at most one call per commit.

    `matched` is the line-match tally attribution has already computed, so this costs
    one pass over the repository's commits and no git call at all.
    """
    if not calls:
        return []
    found: list[Alias] = []
    for row in connection.execute(
        'SELECT commit_hash, committer_at, added_lines FROM "commit"'
        " WHERE repo_key = ? AND is_merge = 0",
        (repo_key,),
    ):
        if row["commit_hash"] in already:
            continue
        counts = dict(matched.get(row["commit_hash"], []))
        if not counts:
            continue
        best: tuple[Call, int] | None = None
        for call in calls:
            overlap = counts.get(call.session_id, 0)
            if not _overlaps(overlap, row["added_lines"]):
                continue
            if not _in_window(call.called_at, row["committer_at"]):
                continue
            if best is None or (call.called_at or "") > (best[0].called_at or ""):
                best = (call, overlap)
        if best is not None:
            found.append(
                Alias(
                    printed_hash=best[0].printed_hash,
                    commit_hash=row["commit_hash"],
                    session_id=best[0].session_id,
                    lines_matched=best[1],
                )
            )
    return _one_per_printed_hash(found)


def _one_per_printed_hash(found: list[Alias]) -> list[Alias]:
    """A dead hash named one commit, so it may claim only one here: the best overlap."""
    kept: dict[str, Alias] = {}
    for alias in found:
        held = kept.get(alias.printed_hash)
        better = held is None or alias.lines_matched > held.lines_matched
        # A tie is settled by the hash, so a rebuild makes the same choice every time.
        tied = held is not None and alias.lines_matched == held.lines_matched
        if better or (tied and alias.commit_hash < held.commit_hash):
            kept[alias.printed_hash] = alias
    return sorted(kept.values(), key=lambda alias: (alias.commit_hash, alias.printed_hash))


def save(connection: sqlite3.Connection, aliases: list[Alias]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO commit_alias VALUES (?, ?, ?, ?)",
        [(a.printed_hash, a.commit_hash, a.session_id, FACT_VERSION) for a in aliases],
    )


def resolution(connection: sqlite3.Connection) -> dict[str, int]:
    """What became of every short hash a session printed: the four counts `status` shows.

    Read back from the store rather than remembered from the last build, so the answer
    is the same whether it is asked a second after an ingest or a month later.
    """
    try:
        printed = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT commit_hash FROM command"
                    " WHERE command_class = 'git_commit' AND commit_hash IS NOT NULL"
                )
                if isinstance(row[0], str) and row[0]
            }
        )
        known = sorted(row[0] for row in connection.execute('SELECT commit_hash FROM "commit"'))
        aliased = {
            row[0] for row in connection.execute("SELECT DISTINCT printed_hash FROM commit_alias")
        }
    except sqlite3.OperationalError:
        return {"printed": 0, "resolved": 0, "reidentified": 0, "unresolved": 0}

    resolved = sum(1 for short in printed if _has_prefix(known, short))
    reidentified = sum(1 for short in printed if short in aliased and not _has_prefix(known, short))
    return {
        "printed": len(printed),
        "resolved": resolved,
        "reidentified": reidentified,
        "unresolved": len(printed) - resolved - reidentified,
    }


def _overlaps(matched: int, added_lines: int | None) -> bool:
    required = min(MIN_OVERLAP, added_lines) if added_lines else MIN_OVERLAP
    return matched >= max(1, required)


def _in_window(called_at: str | None, committer_at: str | None) -> bool:
    """The commit was made while the call was running, or within the five minutes after."""
    call = utc(called_at)
    made = utc(committer_at)
    if call is None or made is None:
        return False
    start = datetime.fromisoformat(call)
    return start <= datetime.fromisoformat(made) <= start + WINDOW


def _has_prefix(known: list[str], short: str) -> bool:
    """Whether a stored commit hash starts with this short one, over a sorted list."""
    position = bisect.bisect_left(known, short)
    return position < len(known) and known[position].startswith(short)
