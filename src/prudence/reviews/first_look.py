"""The first look: three to five facts about the history just read, chosen by rules.

Journey decision A2. The surprise that made M0 worth building is the user's own
history read back to them, and today it sits behind commands a new user does not know
to run. So the first `ingest` that completes on a store with no `first_look_shown_at`
marker ends with a few facts and, under each, the command that shows more.

The rules, not a model, choose which facts. `CANDIDATES` is a list of data: each entry
has a key, a function that computes one figure from the existing views, the minimum
coverage below which it is not printed at all, a "worth printing" test, and the command
that shows more. They are ranked, the ones that qualify are taken in order, and between
`MIN_FACTS` and `MAX_FACTS` are printed. Nothing is computed twice: every figure comes
from `store/views` or from a stored `observation` row.

This module lives with the reviews rather than in `facts/` because the ranking is the
review's evidence selector too (M3 plan, task 3's note): one module, two callers.

Under the floors the page says less. With fewer than `THIN_SESSIONS` sessions, or with
no commit past its seven-day mark, the thin-data variant says what is missing and when
to come back, which is what principle 3 asks of a small sample.

Later ingests print at most two lines: the observations that appeared since the last
one, or a hint that a review is ready.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from prudence.reviews import readiness as readiness_module
from prudence.reviews import schema
from prudence.reviews.build import outcome_totals
from prudence.reviews.ranges import MATURITY_DAYS, STAMP
from prudence.store import observations as observations_module
from prudence.store import views

# The marker that says the first look has been shown. Its value is when.
FIRST_LOOK_MARKER = "first_look_shown_at"

# The observation keys the last ingest already told the user about.
OBSERVATIONS_MARKER = "first_look_observations_seen"

# Below this many sessions the store cannot say much, and says so instead.
THIN_SESSIONS = 20

# How many facts a first look prints: at least the first, at most five.
MIN_FACTS = 3
MAX_FACTS = 5

# No outcome figure is printed below this coverage. The same idea as the observations'
# floors: a share over lines the session barely wrote is not about the session.
MIN_COVERAGE = 0.4

# Nor below this many lines: a share of forty lines is a coincidence.
MIN_LINES = 100

CLOSING = "For a written review: `prudence review`."


@dataclass(frozen=True)
class Figure:
    """One computed fact: the sentence, the value behind it, and its coverage."""

    text: str
    value: float | None = None
    coverage: float | None = None


@dataclass(frozen=True)
class Candidate:
    """One fact that may be worth printing, and the rules that decide whether it is."""

    key: str
    rank: int
    compute: Callable[[Look], Figure | None]
    worth: Callable[[Figure], bool]
    command: str
    min_coverage: float | None = None


@dataclass
class Look:
    """Everything the candidates may read, gathered once."""

    connection: sqlite3.Connection
    now: datetime
    sessions: int = 0
    projects: int = 0
    first_at: str | None = None
    last_at: str | None = None
    outcomes: dict[str, Any] | None = None
    observations: list[dict[str, Any]] = None  # type: ignore[assignment]
    purposes: dict[str, int] = None  # type: ignore[assignment]
    no_code: int = 0

    def observation(self, fact: str) -> dict[str, Any] | None:
        """The first observation about one behaviour, a project's before a pooled one."""
        for row in self.observations or []:
            if row["fact"] == fact and row["outcome"] == "rework":
                return row
        return None


# --- the candidate facts, as data ------------------------------------------------------


def _scope(look: Look) -> Figure | None:
    if not look.sessions:
        return None
    span = ""
    if look.first_at and look.last_at:
        span = f", {look.first_at[:10]} to {look.last_at[:10]}"
    projects = "project" if look.projects == 1 else "projects"
    return Figure(
        f"{look.sessions} sessions in {look.projects} {projects}{span}.",
        float(look.sessions),
    )


def _rework(look: Look) -> Figure | None:
    """The share of the followed lines that were gone by their 30-day mark."""
    if look.outcomes is None:
        return None
    shares = look.outcomes["shares"]
    if not shares["measured_30d"]:
        return None
    gone = 1 - (shares["alive_30d"] / shares["measured_30d"])
    return Figure(
        f"{gone * 100:.0f}% of the lines Prudence could follow were gone again by their "
        f"30-day mark ({shares['measured_30d']} lines measured, coverage "
        f"{_percent(look.outcomes['coverage'])}).",
        gone,
        look.outcomes["coverage"],
    )


def _reworked_by_you(look: Look) -> Figure | None:
    """The share a later commit of the user's own removed, which is the sharper figure."""
    if look.outcomes is None:
        return None
    shares = look.outcomes["shares"]
    if not shares["lines"] or shares["reworked_share"] is None:
        return None
    return Figure(
        f"{shares['reworked_share'] * 100:.0f}% of the lines Prudence could follow were "
        f"removed again by one of your own later commits ({shares['reworked']} of "
        f"{shares['lines']} lines, coverage {_percent(look.outcomes['coverage'])}).",
        shares["reworked_share"],
        look.outcomes["coverage"],
    )


def _long_sittings(look: Look) -> Figure | None:
    row = look.observation("sittings")
    if row is None:
        return None
    names = views.repository_names(look.connection)
    return Figure(
        f"{observations_module.sentence(row, names.get(row['repo_key']))} "
        f"{observations_module.caveat(row)}",
        row["with_value"],
        row["coverage"],
    )


def _no_code(look: Look) -> Figure | None:
    if not look.sessions:
        return None
    share = look.no_code / look.sessions
    return Figure(
        f"{share * 100:.0f}% of your sessions produced no code at all ({look.no_code} of "
        f"{look.sessions}).",
        share,
    )


def _top_purpose(look: Look) -> Figure | None:
    if not look.purposes or not look.sessions:
        return None
    label, count = max(look.purposes.items(), key=lambda item: (item[1], item[0]))
    share = count / look.sessions
    return Figure(
        f"Most of your sessions are labelled {label}: {share * 100:.0f}% of them ({count} of "
        f"{look.sessions}), by rules over the tool mix rather than by reading anything.",
        share,
    )


def _compaction(look: Look) -> Figure | None:
    row = look.observation("compactions")
    if row is None:
        return None
    names = views.repository_names(look.connection)
    return Figure(
        f"{observations_module.sentence(row, names.get(row['repo_key']))} "
        f"{observations_module.caveat(row)}",
        row["with_value"],
        row["coverage"],
    )


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("scope", 1, _scope, lambda figure: True, "prudence sessions"),
    Candidate(
        "rework_30d",
        2,
        _rework,
        lambda figure: (figure.value or 0) >= 0.05,
        "prudence outcomes",
        min_coverage=MIN_COVERAGE,
    ),
    Candidate(
        "long_sittings",
        3,
        _long_sittings,
        lambda figure: True,
        "prudence observations",
        min_coverage=MIN_COVERAGE,
    ),
    Candidate(
        "compaction",
        4,
        _compaction,
        lambda figure: True,
        "prudence observations",
        min_coverage=MIN_COVERAGE,
    ),
    Candidate(
        "no_code", 5, _no_code, lambda figure: (figure.value or 0) >= 0.10, "prudence sessions"
    ),
    Candidate(
        "reworked_by_you",
        6,
        _reworked_by_you,
        lambda figure: (figure.value or 0) >= 0.05,
        "prudence outcomes",
        min_coverage=MIN_COVERAGE,
    ),
    Candidate(
        "top_purpose",
        7,
        _top_purpose,
        lambda figure: (figure.value or 0) >= 0.25,
        "prudence usage",
    ),
)


# --- the page --------------------------------------------------------------------------


def after_ingest(connection: sqlite3.Connection, now: datetime | None = None) -> list[str]:
    """The lines `prudence ingest` prints at the end. The only entry point it calls.

    First time: the first look, and the marker is set so it never appears again. Every
    time after: at most two lines about what is new, plus the readiness hint when a
    review is worth writing.
    """
    moment = now or datetime.now(UTC)
    try:
        schema.ensure_meta(connection)
    except sqlite3.OperationalError:
        return []
    if schema.marker(connection, FIRST_LOOK_MARKER) is None:
        lines = first_look(connection, moment)
        schema.set_marker(connection, FIRST_LOOK_MARKER, schema.now_text(moment))
        _remember_observations(connection)
        return lines

    lines = new_observations(connection)
    _remember_observations(connection)
    ready = readiness_module.readiness(connection, None, moment)
    if ready.ready:
        lines.append(ready.hint)
    return lines


def first_look(connection: sqlite3.Connection, now: datetime | None = None) -> list[str]:
    """Three to five facts about the history just read, each with the command for more."""
    look = gather(connection, now or datetime.now(UTC))
    if not look.sessions:
        return []
    if look.sessions < THIN_SESSIONS or look.outcomes is None:
        return ["", "A first look at what was recorded", "", *thin(look), "", CLOSING]

    chosen: list[tuple[Candidate, Figure]] = []
    for candidate in sorted(CANDIDATES, key=lambda item: item.rank):
        if len(chosen) >= MAX_FACTS:
            break
        figure = _qualified(candidate, look)
        if figure is not None:
            chosen.append((candidate, figure))
    if len(chosen) < MIN_FACTS:
        return ["", "A first look at what was recorded", "", *thin(look), "", CLOSING]

    lines = ["", "A first look at what was recorded", ""]
    for candidate, figure in chosen:
        lines.append(figure.text)
        lines.append(f"  more: {candidate.command}")
    lines.append("")
    lines.append(CLOSING)
    return lines


def thin(look: Look) -> list[str]:
    """What the store can say when it cannot say much, and when to come back."""
    lines: list[str] = []
    scope = _scope(look)
    if scope is not None:
        lines.append(scope.text)
    if look.outcomes is None:
        lines.append(
            f"Outcomes need commits older than {MATURITY_DAYS} days; none of yours has "
            "reached that mark yet, so nothing can be said about what became of the code."
        )
    else:
        shares = look.outcomes["shares"]
        lines.append(
            f"{look.outcomes['commits']} commits have passed the {MATURITY_DAYS}-day mark so "
            f"far ({shares['lines']} lines followed, coverage "
            f"{_percent(look.outcomes['coverage'])})."
        )
    if look.sessions < THIN_SESSIONS:
        lines.append(
            f"Comparisons between your own sessions need at least "
            f"{observations_module.MIN_SESSIONS} on each side, and this store holds "
            f"{look.sessions} sessions; come back after about "
            f"{THIN_SESSIONS - look.sessions} more."
        )
    lines.append("  more: prudence sessions, prudence outcomes")
    return lines


def new_observations(connection: sqlite3.Connection) -> list[str]:
    """What appeared since the last ingest, in at most two lines."""
    rows = views.observations(connection)
    seen = _seen(connection)
    if seen is None:
        return []
    fresh = [row for row in rows if _key(row) not in seen]
    if not fresh:
        return []
    names = views.repository_names(connection)
    if len(fresh) <= 2:
        return [
            f"New observation: {observations_module.sentence(row, names.get(row['repo_key']))}"
            for row in fresh
        ]
    return [f"{len(fresh)} new observations since the last ingest; run `prudence observations`."]


def gather(connection: sqlite3.Connection, now: datetime) -> Look:
    """Read everything the candidates need, once, from the existing views."""
    look = Look(connection=connection, now=now, observations=[], purposes={})
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS sessions, COUNT(DISTINCT repo_key) AS projects,"
            " MIN(first_at) AS first_at, MAX(last_at) AS last_at FROM session"
        ).fetchone()
    except sqlite3.OperationalError:
        return look
    look.sessions = row["sessions"] or 0
    look.projects = row["projects"] or 0
    look.first_at = row["first_at"]
    look.last_at = row["last_at"]
    if not look.sessions:
        return look

    look.outcomes = outcome_totals(
        connection,
        "0000-01-01T00:00:00",
        (now - timedelta(days=MATURITY_DAYS)).strftime(STAMP),
        None,
    )
    look.observations = views.observations(connection)
    look.purposes = views.purpose_counts(connection)
    look.no_code = _sessions_without_edits(connection)
    return look


def _qualified(candidate: Candidate, look: Look) -> Figure | None:
    """The figure this candidate would print, or None when a rule says not to."""
    try:
        figure = candidate.compute(look)
    except sqlite3.OperationalError:
        return None
    if figure is None:
        return None
    if candidate.min_coverage is not None:
        if figure.coverage is None or figure.coverage < candidate.min_coverage:
            return None
    if not candidate.worth(figure):
        return None
    return figure


def _sessions_without_edits(connection: sqlite3.Connection) -> int:
    try:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM session WHERE session_id NOT IN (SELECT session_id FROM edit)"
            ).fetchone()[0]
            or 0
        )
    except sqlite3.OperationalError:
        return 0


def _remember_observations(connection: sqlite3.Connection) -> None:
    keys = sorted(_key(row) for row in views.observations(connection))
    schema.set_marker(connection, OBSERVATIONS_MARKER, json.dumps(keys))


def _seen(connection: sqlite3.Connection) -> set[str] | None:
    raw = schema.marker(connection, OBSERVATIONS_MARKER)
    if raw is None:
        return None
    try:
        return set(json.loads(raw))
    except ValueError:
        return set()


def _key(row: dict[str, Any]) -> str:
    return f"{row['repo_key']}|{row['fact']}|{row['outcome']}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"
