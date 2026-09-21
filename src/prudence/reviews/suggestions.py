"""Suggestions as records, and what became of them (journey decision C2).

Principle 4 says advice is accountable and that ignored suggestions stop repeating.
Neither is possible while a suggestion is a sentence in a page nobody stored, so each
one is a row: which observation it stands on, its text, its status, and the dates it
changed.

The gate is the one the observations already pass. `store/observations.py` writes a row
only when both sides hold at least `MIN_SESSIONS` sessions and the medians are at least
`MIN_GAP` apart; a suggestion is created from an observation row and therefore inherits
exactly those floors. Nothing here loosens them and nothing here invents a finding of
its own.

The lifecycle:

- **open** when a review first meets that observation. One row per observation key
  (project, behaviour, outcome), never a second while the first is open.
- **taken** or **dismissed** when the user says so. A dismissed key is not raised again.
- **expired** when the observation it stands on no longer exists, because the evidence
  moved and the suggestion is now about nothing.

The follow-up is the comparison the next review prints: for each open suggestion, how
often the behaviour happened and what the outcome was, before the review's range and
since it began. Both sides respect the observations' own session floor; a side below it
is a dash, not a small number dressed up as a trend.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from statistics import median
from typing import Any

from prudence.reviews import schema
from prudence.reviews.schema import observation_key
from prudence.store import observations as observations_module
from prudence.store import views

NOT_MEASURED = "-"


@dataclass
class RefreshStats:
    opened: int = 0
    expired: int = 0
    kept: int = 0


def refresh(
    connection: sqlite3.Connection,
    review_id: int,
    repo_key: str | None,
    created_at: str,
) -> RefreshStats:
    """Open a row for every observation this review met, and expire the ones left behind.

    A key that is already open, taken or dismissed is left alone: the second is the
    user's answer and the third is their refusal, and principle 4 says a refusal is not
    re-argued.
    """
    schema.ensure(connection)
    rows = views.observations(connection, repo_key)
    live = {observation_key(row): row for row in rows}
    stats = RefreshStats()

    known = {row["observation_key"]: row for row in schema.all_suggestions(connection)}
    for key, row in live.items():
        held = known.get(key)
        if held is not None and held["status"] in (schema.OPEN, schema.TAKEN, schema.DISMISSED):
            stats.kept += 1
            continue
        schema.insert_suggestion(
            connection,
            review_id=review_id,
            observation_key=key,
            text=text_for(connection, row),
            created_at=created_at,
        )
        stats.opened += 1

    for held in schema.open_suggestions(connection):
        if held["observation_key"] not in live and held["observation_key"] in known:
            schema.set_status(connection, held["id"], schema.EXPIRED, created_at)
            stats.expired += 1
    return stats


def text_for(connection: sqlite3.Connection, row: dict[str, Any]) -> str:
    """The suggestion's words: the observation's own sentence, with its caveat.

    The sentence is `store/observations.sentence`, which every surface prints, so a
    suggestion never says more than the observation it stands on (principle 3: no
    adjective, no ranking, no advice beyond what the numbers show).
    """
    names = views.repository_names(connection)
    return (
        f"{observations_module.sentence(row, names.get(row['repo_key']))} "
        f"{observations_module.caveat(row)}"
    )


def follow_up(connection: sqlite3.Connection, key: str, boundary: str) -> dict[str, Any]:
    """How often the behaviour happened and what the outcome was, before and since.

    `boundary` is the start of the review's range: sessions that started before it are
    "then", the rest are "since". The sides are the same sides the observation splits
    on, computed by the same functions, so the figure is comparable with the one the
    observation printed.
    """
    empty = {
        "before_text": NOT_MEASURED,
        "since_text": NOT_MEASURED,
        "before_value": None,
        "since_value": None,
        "before_n": 0,
        "since_n": 0,
    }
    repo_key, fact, outcome = _parse_key(key)
    if outcome not in observations_module.OUTCOMES:
        return empty

    sessions = observations_module.sessions_with_outcomes(connection)
    if repo_key != observations_module.POOLED:
        sessions = [session for session in sessions if session.repo_key == repo_key]
    if not sessions:
        return empty
    with_side, _ = observations_module.split_on(fact, sessions)
    if not with_side:
        return empty

    started = _started(connection, [session.session_id for session in with_side])
    before = [s for s in with_side if (started.get(s.session_id) or "") < boundary]
    since = [s for s in with_side if (started.get(s.session_id) or "") >= boundary]
    return {
        "before_text": _median_text(before, outcome),
        "since_text": _median_text(since, outcome),
        "before_value": _median_value(before, outcome),
        "since_value": _median_value(since, outcome),
        "before_n": len(before),
        "since_n": len(since),
    }


def _median_value(sessions: list, outcome: str) -> float | None:
    """The median outcome of one side, or None below the observations' own floor."""
    if len(sessions) < observations_module.MIN_SESSIONS:
        return None
    return float(median(getattr(session, outcome) for session in sessions))


def _median_text(sessions: list, outcome: str) -> str:
    value = _median_value(sessions, outcome)
    return NOT_MEASURED if value is None else f"{value * 100:.0f}%"


def _started(connection: sqlite3.Connection, ids: list[str]) -> dict[str, str]:
    return {
        row["session_id"]: row["first_at"] or ""
        for row in views._batched(connection, "SELECT session_id, first_at FROM session", ids, "")
    }


def _parse_key(key: str) -> tuple[str, str, str]:
    parts = key.split("|")
    if len(parts) != 3:
        return ("", "", "")
    return (parts[0], parts[1], parts[2])
