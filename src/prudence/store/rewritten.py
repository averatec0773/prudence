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

The same rule answers a second question, added in M2 batch 2. Round two of the spike
measured that 8.6% of in-session `git commit` calls print no hash at all: the command
was quiet, or a hook's output followed git's and the `[branch hash]` line never
appeared. There is then no hash to be dead, but the two facts the rule really rests on
are both still there. So a reachable commit dated inside the five minutes after such a
call, whose added lines overlap that session's, is recorded as `in_session` with
`method_note = 'silent'` and no alias row, because no hash was printed to alias.

The two kinds differ in one place only, the tiebreak. A printed hash is evidence of a
particular commit, so when a call printed two dead hashes the last one wins (the amend
rule above). A silent call is evidence of a moment, so the commit nearest that moment
wins, and one call claims at most one commit. A printed hash is preferred over a silent
call whenever both fit the same commit: a hash git actually printed is the better fact.
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


REWRITTEN = "rewritten"
SILENT = "silent"


@dataclass(frozen=True)
class Call:
    """One in-session `git commit` that left no usable hash behind.

    Either it printed a short hash that no longer resolves (`printed_hash`), or it
    printed none at all and only the tool call itself names it (`call_id`). Exactly one
    of the two is set, and `key` is whichever it is.
    """

    printed_hash: str | None
    session_id: str
    called_at: str | None
    call_id: str | None = None

    @property
    def key(self) -> str:
        return self.printed_hash or self.call_id or ""

    @property
    def note(self) -> str:
        return REWRITTEN if self.printed_hash else SILENT


@dataclass(frozen=True)
class Alias:
    """One commit found again: the call that made it, the live commit, the session."""

    printed_hash: str | None
    commit_hash: str
    session_id: str
    lines_matched: int
    method_note: str = REWRITTEN
    key: str = ""
    gap: int = 0


def reidentify(
    connection: sqlite3.Connection,
    repo_key: str,
    calls: list[Call],
    matched: dict[str, list[tuple[str, int]]],
    already: set[str],
    silent: list[Call] | None = None,
) -> list[Alias]:
    """Commits of one repository found again, at most one call per commit.

    `matched` is the line-match tally attribution has already computed, so this costs
    one pass over the repository's commits and no git call at all.
    """
    silent = silent or []
    if not calls and not silent:
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
        # A printed hash is evidence of this commit; a silent call only of the moment.
        claim = _claim(calls, counts, row, nearest=False) or _claim(
            silent, counts, row, nearest=True
        )
        if claim is not None:
            call, overlap, gap = claim
            found.append(
                Alias(
                    printed_hash=call.printed_hash,
                    commit_hash=row["commit_hash"],
                    session_id=call.session_id,
                    lines_matched=overlap,
                    method_note=call.note,
                    key=call.key,
                    gap=gap,
                )
            )
    return _one_per_call(found)


def _claim(
    calls: list[Call], counts: dict[str, int], row: sqlite3.Row, nearest: bool
) -> tuple[Call, int, int] | None:
    """The call that best fits one commit, with its overlap and its gap in seconds.

    `nearest` picks the call closest in time, which is what a silent call needs; the
    printed case keeps the last call, because that is what an amend leaves behind.
    """
    best: tuple[Call, int, int] | None = None
    for call in calls:
        overlap = counts.get(call.session_id, 0)
        if not _overlaps(overlap, row["added_lines"]):
            continue
        gap = _gap(call.called_at, row["committer_at"])
        if gap is None:
            continue
        if best is None:
            best = (call, overlap, gap)
        elif nearest and (gap, call.key) < (best[2], best[0].key):
            best = (call, overlap, gap)
        elif not nearest and (call.called_at or "", call.key) > (
            best[0].called_at or "",
            best[0].key,
        ):
            best = (call, overlap, gap)
    return best


def _one_per_call(found: list[Alias]) -> list[Alias]:
    """One commit per call: a dead hash named one, and a silent call made one.

    Both tiebreaks end in the commit hash, so a rebuild makes the same choice every time.
    """
    kept: dict[str, Alias] = {}
    for alias in found:
        held = kept.get(alias.key)
        if held is None or _better(alias, held):
            kept[alias.key] = alias
    return sorted(kept.values(), key=lambda alias: (alias.commit_hash, alias.key))


def _better(alias: Alias, held: Alias) -> bool:
    """Whether this claim beats the one already held for the same call."""
    if alias.method_note == SILENT:
        return (alias.gap, -alias.lines_matched, alias.commit_hash) < (
            held.gap,
            -held.lines_matched,
            held.commit_hash,
        )
    return (-alias.lines_matched, alias.commit_hash) < (-held.lines_matched, held.commit_hash)


def save(connection: sqlite3.Connection, aliases: list[Alias]) -> None:
    """Store the printed hashes. A silent call printed none, so it has nothing to alias."""
    connection.executemany(
        "INSERT OR REPLACE INTO commit_alias VALUES (?, ?, ?, ?)",
        [
            (a.printed_hash, a.commit_hash, a.session_id, FACT_VERSION)
            for a in aliases
            if a.printed_hash
        ],
    )


def silent_matches(connection: sqlite3.Connection) -> int:
    """Commits matched to a `git commit` that printed no hash, read back from the store."""
    try:
        return connection.execute(
            "SELECT COUNT(DISTINCT commit_hash) FROM attribution"
            " WHERE method = 'in_session' AND method_note = ?",
            (SILENT,),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


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


def _gap(called_at: str | None, committer_at: str | None) -> int | None:
    """Seconds from the call to the commit, or None when the commit is outside the window.

    The commit was made while the call was running, or within the five minutes after.
    """
    call = utc(called_at)
    made = utc(committer_at)
    if call is None or made is None:
        return None
    start = datetime.fromisoformat(call)
    delta = datetime.fromisoformat(made) - start
    if delta < timedelta(0) or delta > WINDOW:
        return None
    return int(delta.total_seconds())


def _has_prefix(known: list[str], short: str) -> bool:
    """Whether a stored commit hash starts with this short one, over a sorted list."""
    position = bisect.bisect_left(known, short)
    return position < len(known) and known[position].startswith(short)
