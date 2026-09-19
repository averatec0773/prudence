"""The precision sample: the hard quarter, drawn for a person to label, and the score.

Spike round two could not tell whether line matching beats the time-window baselines,
because its only ground truth is commits the agent committed itself, where the
committing session is trivially the most recently active one. This module draws the
population that ground truth could not reach: commits the transcript does not already
name a session for (`in_session` never fired), in periods busy enough that a guess and
a line match can actually disagree, that is, where two or more sessions of the same
repository edited something in the 24 hours before the commit. `prudence sample` shows
that draw to the founder, records what they say, and scores every method against it.

Nothing here decides who is right. It draws, it records candidates and the two
baselines' picks alongside whatever line matching already computed, and it counts,
against the label, how often each method answered and how often it was correct. The
draw is deterministic for a given seed so a sample can be handed to someone and
reproduced.
"""

from __future__ import annotations

import random
import sqlite3
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from prudence.store import labels as labels_module

HARD_QUARTER_WINDOW = timedelta(hours=24)
NEAR_WINDOW = timedelta(hours=4)
METHOD_NAMES = ("line_match", "window_4h", "window_24h")
_STAMP = "%Y-%m-%dT%H:%M:%S"


@dataclass
class Candidate:
    """One session that could plausibly have made the commit: it edited the repository
    within 24 hours before it. `line_match_rank`/`lines_matched` are None when that
    session never won or placed in the line match for this commit."""

    session_id: str
    first_at: str | None
    last_at: str | None
    edits: int
    line_match_rank: int | None = None
    lines_matched: int | None = None


@dataclass
class SampleItem:
    """One hard-quarter commit: its candidates, and what the two time-window baselines
    would have picked, so every method can be scored against whatever label it gets."""

    commit_hash: str
    repo_key: str
    repo_name: str
    committer_at: str
    added_lines: int
    files_changed: int
    candidates: list[Candidate] = field(default_factory=list)
    pick_4h: str | None = None
    pick_24h: str | None = None


@dataclass
class MethodScore:
    """Precision, recall and abstention for one method, over labelled commits only."""

    labelled: int = 0
    answered: int = 0
    correct: int = 0

    @property
    def precision(self) -> float | None:
        return self.correct / self.answered if self.answered else None

    @property
    def recall(self) -> float | None:
        return self.answered / self.labelled if self.labelled else None

    @property
    def abstention_rate(self) -> float | None:
        return 1 - (self.answered / self.labelled) if self.labelled else None


def draw_sample(
    connection: sqlite3.Connection, n: int = 50, seed: int | None = None
) -> list[SampleItem]:
    """The hard quarter: commits `in_session` never named, where two or more sessions of
    the repository edited something in the 24 hours before the commit. Deterministic
    given the seed; without one, a fresh draw each time.
    """
    names = {
        row["repo_key"]: row["name"]
        for row in connection.execute("SELECT repo_key, name FROM repository")
    }
    in_session = {
        row[0]
        for row in connection.execute(
            "SELECT commit_hash FROM attribution WHERE method = 'in_session'"
        )
    }
    repo_keys = [
        row[0]
        for row in connection.execute(
            'SELECT DISTINCT repo_key FROM "commit" WHERE repo_key IS NOT NULL'
        )
    ]

    pool: list[SampleItem] = []
    for repo_key in repo_keys:
        times, sessions = _edits(connection, repo_key)
        line_match = _line_match_by_commit(connection, repo_key)
        for row in connection.execute(
            'SELECT commit_hash, committer_at, added_lines, files_changed FROM "commit"'
            " WHERE repo_key = ? AND is_merge = 0 AND committer_at IS NOT NULL",
            (repo_key,),
        ):
            commit_hash = row["commit_hash"]
            if commit_hash in in_session:
                continue
            moment = _parse(row["committer_at"])
            if moment is None:
                continue
            active = _active_sessions(times, sessions, moment, HARD_QUARTER_WINDOW)
            if len(active) < 2:
                continue
            winners = line_match.get(commit_hash, {})
            candidates = [
                Candidate(
                    session_id=session_id,
                    first_at=first_at,
                    last_at=last_at,
                    edits=count,
                    line_match_rank=winners.get(session_id, (None, None))[0],
                    lines_matched=winners.get(session_id, (None, None))[1],
                )
                for session_id, (first_at, last_at, count) in sorted(active.items())
            ]
            pool.append(
                SampleItem(
                    commit_hash=commit_hash,
                    repo_key=repo_key,
                    repo_name=names.get(repo_key, repo_key),
                    committer_at=row["committer_at"],
                    added_lines=row["added_lines"],
                    files_changed=row["files_changed"],
                    candidates=candidates,
                    pick_4h=_pick(times, sessions, moment, NEAR_WINDOW),
                    pick_24h=_pick(times, sessions, moment, HARD_QUARTER_WINDOW),
                )
            )

    pool.sort(key=lambda item: item.commit_hash)
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(n, len(pool)))
    chosen.sort(key=lambda item: (item.committer_at, item.commit_hash))
    return chosen


def score(connection: sqlite3.Connection) -> dict[str, MethodScore]:
    """Precision, recall and abstention for line matching and the two time windows,
    over every labelled commit, whatever sample it came from."""
    scores = {name: MethodScore() for name in METHOD_NAMES}
    labels_module.ensure_schema(connection)
    label_rows = list(connection.execute("SELECT commit_hash, session_id FROM label"))
    if not label_rows:
        return scores

    commit_info: dict[str, sqlite3.Row] = {}
    hashes = [row["commit_hash"] for row in label_rows]
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        for row in connection.execute(
            'SELECT commit_hash, repo_key, committer_at FROM "commit"'
            f" WHERE commit_hash IN ({placeholders})",
            batch,
        ):
            commit_info[row["commit_hash"]] = row

    line_match_top1 = {
        row["commit_hash"]: row["session_id"]
        for row in connection.execute(
            "SELECT commit_hash, session_id FROM attribution"
            " WHERE method = 'line_match' AND rank = 1"
        )
    }
    edits_cache: dict[str, tuple[list[str], list[str]]] = {}

    for label_row in label_rows:
        commit_hash = label_row["commit_hash"]
        true_session = label_row["session_id"]
        info = commit_info.get(commit_hash)
        if info is None or info["committer_at"] is None:
            continue
        moment = _parse(info["committer_at"])
        if moment is None:
            continue
        repo_key = info["repo_key"]
        if repo_key not in edits_cache:
            edits_cache[repo_key] = _edits(connection, repo_key)
        times, sessions = edits_cache[repo_key]
        guesses = {
            "line_match": line_match_top1.get(commit_hash),
            "window_4h": _pick(times, sessions, moment, NEAR_WINDOW),
            "window_24h": _pick(times, sessions, moment, HARD_QUARTER_WINDOW),
        }
        for method, guess in guesses.items():
            stat = scores[method]
            stat.labelled += 1
            if guess is not None:
                stat.answered += 1
                if true_session is not None and guess == true_session:
                    stat.correct += 1
    return scores


def _edits(connection: sqlite3.Connection, repo_key: str) -> tuple[list[str], list[str]]:
    """Every edit's timestamp and session in one repository, oldest first."""
    rows = connection.execute(
        "SELECT edited_at, session_id FROM edit WHERE repo_key = ? AND edited_at IS NOT NULL"
        " ORDER BY edited_at",
        (repo_key,),
    ).fetchall()
    return [row["edited_at"] for row in rows], [row["session_id"] for row in rows]


def _line_match_by_commit(
    connection: sqlite3.Connection, repo_key: str
) -> dict[str, dict[str, tuple[int, int]]]:
    result: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for row in connection.execute(
        "SELECT a.commit_hash, a.session_id, a.rank, a.lines_matched FROM attribution a"
        ' JOIN "commit" c ON c.commit_hash = a.commit_hash'
        " WHERE c.repo_key = ? AND a.method = 'line_match'",
        (repo_key,),
    ):
        result[row["commit_hash"]][row["session_id"]] = (row["rank"], row["lines_matched"])
    return dict(result)


def _bounds(moment: datetime, window: timedelta) -> tuple[str, str]:
    return (moment - window).strftime(_STAMP), moment.strftime(_STAMP)


def _window(times: list[str], sessions: list[str], start: str, end: str) -> list[tuple[str, str]]:
    lo = bisect_left(times, start)
    hi = bisect_right(times, end)
    return list(zip(times[lo:hi], sessions[lo:hi], strict=True))


def _active_sessions(
    times: list[str], sessions: list[str], moment: datetime, window: timedelta
) -> dict[str, tuple[str, str, int]]:
    """Sessions with at least one edit in the window before the commit: first, last, count."""
    start, end = _bounds(moment, window)
    info: dict[str, list] = {}
    for at, session_id in _window(times, sessions, start, end):
        entry = info.setdefault(session_id, [at, at, 0])
        entry[0] = min(entry[0], at)
        entry[1] = max(entry[1], at)
        entry[2] += 1
    return {session_id: (entry[0], entry[1], entry[2]) for session_id, entry in info.items()}


def _pick(times: list[str], sessions: list[str], moment: datetime, window: timedelta) -> str | None:
    """The time-window baseline: the most recently active session in the window, or None."""
    start, end = _bounds(moment, window)
    pairs = _window(times, sessions, start, end)
    if not pairs:
        return None
    pairs.sort(key=lambda pair: (pair[0], pair[1]))
    return pairs[-1][1]


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None
