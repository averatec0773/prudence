"""What the menu bar shows, computed from the store alone.

No `rumps` import here and no analysis logic beyond counting rows already derived
elsewhere, so this module runs on any platform and is tested without a GUI. The menu
bar's "today" is the viewer's local calendar day, converted to the UTC-ish strings the
derived tables already sort by (the same comparison `cli.sessions` uses for its own
window).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from prudence.store import observations as observations_module
from prudence.store import views


@dataclass(frozen=True)
class Summary:
    sessions: int
    edits: int
    commits: int
    last_ingest: str | None


@dataclass(frozen=True)
class WeekSummary:
    """This ISO week's tokens by purpose, and the store's most current observation."""

    top_purposes: tuple[tuple[str, float], ...]
    latest_observation: str | None


def today_summary(connection: sqlite3.Connection, day: date) -> Summary:
    """Sessions started today, edits made today, commits credited to today's sessions."""
    start, end = _day_bounds(day)
    return Summary(
        sessions=_scalar(
            connection,
            "SELECT COUNT(*) FROM session WHERE first_at >= ? AND first_at < ?",
            start,
            end,
        ),
        edits=_scalar(
            connection,
            "SELECT COUNT(*) FROM edit WHERE edited_at >= ? AND edited_at < ?",
            start,
            end,
        ),
        commits=_scalar(
            connection,
            "SELECT COUNT(DISTINCT a.commit_hash) FROM attribution a"
            " JOIN session s ON s.session_id = a.session_id"
            " WHERE a.rank = 1 AND a.method IN ('in_session', 'line_match')"
            " AND s.first_at >= ? AND s.first_at < ?",
            start,
            end,
        ),
        last_ingest=_last_ingest(connection),
    )


def week_summary(connection: sqlite3.Connection, today: date) -> WeekSummary:
    """This ISO week's tokens by purpose (the top two, each with its share of the
    week's total) and the latest observation's own sentence, or None when the store
    holds none yet.
    """
    start, end = _week_bounds(today)
    usage = views.usage_summary(connection, start, until=end)
    return WeekSummary(
        top_purposes=_top_purposes(usage["by_purpose"]),
        latest_observation=_latest_observation(connection),
    )


def _week_bounds(today: date) -> tuple[str, str]:
    """The current ISO week's local Monday and the following Monday, as UTC ISO strings."""
    monday = today - timedelta(days=today.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    return _day_bounds(monday)[0], _day_bounds(sunday)[1]


def _top_purposes(by_purpose: dict[str, dict]) -> tuple[tuple[str, float], ...]:
    """The two purposes with the most tokens, each with its share of the week's total."""
    totals = {
        label: sum(cell[column] for column in views.TOKEN_COLUMNS)
        for label, cell in by_purpose.items()
    }
    grand = sum(totals.values())
    if not grand:
        return ()
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return tuple((label, value / grand) for label, value in ranked[:2])


def _latest_observation(connection: sqlite3.Connection) -> str | None:
    """One observation's own sentence, or None when the store holds none yet.

    Observation rows carry no timestamp of their own (the whole set is recomputed at
    every `prudence rebuild`, never appended to), so "latest" here is the first row in
    `views.observations`'s own fixed order, which puts a project's own rows ahead of
    the pooled ones that speak for every project at once.
    """
    rows = views.observations(connection)
    if not rows:
        return None
    row = rows[0]
    names = views.repository_names(connection)
    return observations_module.sentence(row, names.get(row["repo_key"]))


def _day_bounds(day: date) -> tuple[str, str]:
    """The viewer's local midnight and the following one, as UTC ISO strings."""
    local_start = datetime.combine(day, time.min).astimezone()
    local_end = local_start + timedelta(days=1)
    stamp = "%Y-%m-%dT%H:%M:%S"
    return local_start.astimezone(UTC).strftime(stamp), local_end.astimezone(UTC).strftime(stamp)


def _last_ingest(connection: sqlite3.Connection) -> str | None:
    """The most recent time any archived file was seen, or None before the first ingest."""
    try:
        row = connection.execute("SELECT MAX(last_seen) FROM archive_file").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _scalar(connection: sqlite3.Connection, query: str, *parameters: str) -> int:
    """A COUNT query, or 0 when the table it reads has not been built yet."""
    try:
        row = connection.execute(query, parameters).fetchone()
    except sqlite3.OperationalError:
        return 0
    return row[0] if row and row[0] is not None else 0
