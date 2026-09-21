"""Is there enough new work to be worth a review? One function, two thresholds.

Journey decision B asks for a rule rather than a date, so that the CLI hint at the end
of `ingest` and the menu-bar timer later agree without either of them owning the
decision. The rule: since the last review with the same project scope (or since the
store began, when there is none), at least `MIN_NEW_SESSIONS` sessions have started and
at least `MIN_MATURED_COMMITS` commit crossed its seven-day mark. A review written
before both have happened either repeats the last one or reports "too early" in every
outcome column, and a coach that says nothing twice is worse than one that waits.

Both numbers are constants so that a surface can print them and a test can pin them.
`--force` is the escape hatch: the rule warns, it never refuses.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from prudence.reviews import schema
from prudence.reviews.ranges import MATURITY_DAYS, STAMP, parse

# Sessions that must have started since the last review before another one is worth it.
MIN_NEW_SESSIONS = 5

# Commits that must have crossed their seven-day mark in the same span.
MIN_MATURED_COMMITS = 1


@dataclass(frozen=True)
class Readiness:
    """Ready or not, the counts behind it, and the sentence a surface prints."""

    ready: bool
    reason: str
    new_sessions: int
    matured_commits: int
    since: str | None
    project: str | None

    @property
    def hint(self) -> str:
        """The one line `ingest` prints when a review is worth writing."""
        return f"{self.reason} Run `prudence review` for a written review."


def readiness(
    connection: sqlite3.Connection,
    project: str | None = None,
    now: datetime | None = None,
    name: str | None = None,
) -> Readiness:
    """Whether a review of this scope would have anything new to say.

    `project` is the repository key the counts are filtered by; `name` is what the
    reason calls it, because a reader knows their project by its name and a repository
    key is a hash of its root commit.
    """
    moment = now or datetime.now(UTC)
    previous = schema.last_review(connection, project)
    since = previous["range_end"] if previous is not None else None
    sessions = _new_sessions(connection, since, project)
    matured = _matured_commits(connection, since, moment, project)
    where = f" in {name or project}" if project else ""
    seen = f"since {_day(since)}" if since else "so far"

    if sessions < MIN_NEW_SESSIONS:
        return Readiness(
            ready=False,
            reason=(
                f"not ready: {sessions} new sessions{where} {seen} (needs {MIN_NEW_SESSIONS})."
            ),
            new_sessions=sessions,
            matured_commits=matured,
            since=since,
            project=project,
        )
    if matured < MIN_MATURED_COMMITS:
        return Readiness(
            ready=False,
            reason=(
                f"not ready: {sessions} new sessions{where} {seen}, but no commit crossed its "
                f"{MATURITY_DAYS}-day mark in that span, so there is no outcome to report "
                "yet."
            ),
            new_sessions=sessions,
            matured_commits=matured,
            since=since,
            project=project,
        )
    return Readiness(
        ready=True,
        reason=(
            f"A review is ready: {sessions} new sessions{where} {seen} and {matured} commits "
            f"crossed their {MATURITY_DAYS}-day mark."
        ),
        new_sessions=sessions,
        matured_commits=matured,
        since=since,
        project=project,
    )


def _new_sessions(connection: sqlite3.Connection, since: str | None, project: str | None) -> int:
    query = "SELECT COUNT(*) FROM session WHERE 1 = 1"
    parameters: list[str] = []
    if since:
        query += " AND first_at >= ?"
        parameters.append(since)
    if project:
        query += " AND repo_key = ?"
        parameters.append(project)
    try:
        return int(connection.execute(query, parameters).fetchone()[0] or 0)
    except sqlite3.OperationalError:
        return 0


def _matured_commits(
    connection: sqlite3.Connection, since: str | None, now: datetime, project: str | None
) -> int:
    """Commits credited to a session whose seven-day mark fell in the span.

    Only commits a session is credited with at `fact` or `inferred` confidence are
    counted, because they are the only ones a review has an outcome for; an uncertain
    attribution enters no statistic (architecture rule 10).
    """
    mark = timedelta(days=MATURITY_DAYS)
    end = (now - mark).strftime(STAMP)
    query = (
        'SELECT COUNT(DISTINCT c.commit_hash) FROM "commit" c'
        " JOIN attribution a ON a.commit_hash = c.commit_hash"
        " WHERE a.confidence IN ('fact', 'inferred') AND c.committer_at < ?"
    )
    parameters: list[str] = [end]
    if since:
        query += " AND c.committer_at >= ?"
        parameters.append((parse(since) - mark).strftime(STAMP))
    if project:
        query += " AND c.repo_key = ?"
        parameters.append(project)
    try:
        return int(connection.execute(query, parameters).fetchone()[0] or 0)
    except sqlite3.OperationalError:
        return 0


def _day(value: str | None) -> str:
    return (value or "")[:10] or "?"
