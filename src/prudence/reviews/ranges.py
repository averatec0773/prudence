"""Which range a review covers, and which commits its outcome section may speak about.

Two ranges, not one, and they do not overlap by accident.

The **activity window** is what the user did: sessions whose first record falls in
`[start, end)`. It comes from `--last`, `--since`/`--until`, `--month`, or, by default,
from the end of the last review with the same project scope, falling back to the last
seven days when there is no such review.

The **outcome window** is what became of earlier work, and it is a different set of
commits on purpose. A commit made yesterday has no outcome yet: survival is read at its
seven-day mark. So the outcome window holds the commits whose seven-day mark fell
inside the activity window, which is the commits made in
`[start - 7 days, end - 7 days)`. For the default seven-day window that is the commits
made 14 to 7 days before the end; for a 23-day window it is 30 to 7 days before the end.
Nothing older is included, because a review is about the period it names and a commit
whose mark passed two months ago was already answered by an earlier review.

**A day is the user's own calendar day, and a stored timestamp is UTC.** The two are not
in conflict: a date the user writes or names (`--month 2026-09`, `--since 2026-09-08`) is
read as local midnight and immediately converted to UTC, so the boundary lands where
their own day begins and the stamp on the row is still the UTC string every other table
sorts by. This is the one date convention in the codebase: `app_usage_by_bucket_day`
puts a response on `date(started_at, 'localtime')` for exactly the same reason, and a
review of September now covers precisely the days that view calls September. Before M3's
third batch this module read those dates as UTC, which put a review's edges up to a
working day away from the chart's.

Everything here is a pure function of the arguments, the `review` table and the machine's
time zone; no figure is computed and no session is read.
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import click

from prudence.reviews import schema

# The age at which a commit's first outcome can be read. The same seven days
# `line_fate.alive_7d` is measured at, and the same mark the readiness rule waits for.
MATURITY_DAYS = 7

# The default activity window when no review has been written yet for this scope.
DEFAULT_DAYS = 7

STAMP = "%Y-%m-%dT%H:%M:%S"

_WINDOW = re.compile(r"^(\d+)\s*([dw])$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True)
class Window:
    """One review's two ranges, its project scope, and how the range was chosen."""

    start: str
    end: str
    project: str | None
    outcome_start: str
    outcome_end: str
    source: str

    @property
    def days(self) -> float:
        return (parse(self.end) - parse(self.start)).total_seconds() / 86400

    def previous(self) -> Window:
        """The period of the same length ending where this one starts."""
        length = parse(self.end) - parse(self.start)
        start = parse(self.start) - length
        return _window(start, parse(self.start), self.project, "the previous period")


class Unreadable(ValueError):
    """The range arguments do not describe a range. Nothing was computed."""


def resolve(
    connection: sqlite3.Connection | None,
    *,
    last: str | None = None,
    since: str | None = None,
    until: str | None = None,
    month: str | None = None,
    project: str | None = None,
    now: datetime | None = None,
) -> Window:
    """The window a `prudence review` invocation asks for, by the first rule that applies."""
    moment = now or datetime.now(UTC)
    given = [name for name, value in (("--month", month), ("--last", last)) if value]
    if since or until:
        given.append("--since/--until")
    if len(given) > 1:
        raise Unreadable(f"{' and '.join(given)} describe two different ranges; pass one.")

    if month:
        matched = _MONTH.match(month.strip())
        if not matched:
            raise Unreadable(f"{month!r} is not a month; write it as YYYY-MM.")
        year, number = int(matched.group(1)), int(matched.group(2))
        if not 1 <= number <= 12:
            raise Unreadable(f"{month!r} is not a month; the month part is 1 to 12.")
        first = datetime(year, number, 1)
        start = local_midnight(first)
        end = local_midnight(first + timedelta(days=calendar.monthrange(year, number)[1]))
        return _window(start, end, project, f"the month {month}")

    if since or until:
        start = parse_local(_date(since)) if since else parse_local(_date("1970-01-01"))
        end = parse_local(_date(until)) if until else moment
        if end <= start:
            raise Unreadable("--until is not after --since; nothing would be in the range.")
        return _window(start, end, project, "--since/--until")

    if last:
        return _window(moment - _span(last), moment, project, f"the last {last.strip()}")

    previous = schema.last_review(connection, project) if connection is not None else None
    if previous is not None and previous["range_end"]:
        start = parse(previous["range_end"])
        if start < moment:
            return _window(start, moment, project, f"since review {previous['id']}")
    return _window(
        moment - timedelta(days=DEFAULT_DAYS), moment, project, f"the last {DEFAULT_DAYS} days"
    )


def _window(start: datetime, end: datetime, project: str | None, source: str) -> Window:
    maturity = timedelta(days=MATURITY_DAYS)
    return Window(
        start=start.strftime(STAMP),
        end=end.strftime(STAMP),
        project=project,
        outcome_start=(start - maturity).strftime(STAMP),
        outcome_end=(end - maturity).strftime(STAMP),
        source=source,
    )


def _span(value: str) -> timedelta:
    matched = _WINDOW.match(value.strip().lower())
    if not matched:
        raise Unreadable(f"{value!r} is not a window; write it as 7d, 14d or 2w.")
    amount = int(matched.group(1))
    if amount <= 0:
        raise Unreadable(f"{value!r} is not a window; it has to be more than zero.")
    return timedelta(days=amount * (7 if matched.group(2) == "w" else 1))


def _date(value: str) -> str:
    text = value.strip()
    return f"{text}T00:00:00" if len(text) == 10 else text


def parse(value: str) -> datetime:
    """One stored timestamp as an aware datetime. Naive stamps are read as UTC.

    For what is already in the store: every stamp Prudence writes is UTC, including the
    two on a `review` row. A date a person typed goes through `parse_local` instead.
    """
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unreadable(f"{value!r} is not a date; write it as YYYY-MM-DD.") from error
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def parse_local(value: str) -> datetime:
    """One date the user wrote, read on their own calendar and returned as UTC."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unreadable(f"{value!r} is not a date; write it as YYYY-MM-DD.") from error
    return moment.astimezone(UTC) if moment.tzinfo else local_midnight(moment)


def local_midnight(naive: datetime) -> datetime:
    """A wall-clock moment on this machine's calendar, as an aware UTC datetime."""
    return naive.astimezone(UTC)


def option_error(error: Unreadable) -> click.UsageError:
    """The same wording whichever surface asked for the range."""
    return click.UsageError(str(error))
