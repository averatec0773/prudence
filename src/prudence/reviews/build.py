"""The sections of a review, computed from the existing views and nothing else.

Every figure on the page comes from a function in `store/views` that a command already
prints: `usage_summary` is what `prudence usage` sums, `fate_by_commit` and
`outcome_shares` are what `prudence outcomes` prints, `observations` is what
`prudence observations` reads. Nothing is recomputed here, so a number in a review can
be re-derived by running one of those commands with the same range, which is the only
way principle 2 is checkable rather than claimed.

Two things are stored beside the sections.

**The numbers list.** Every figure that appears on the page, with the key it was
computed under, its raw value, its coverage where it has one, and the exact text it is
printed as. `render.py` prints those texts and nothing else numeric, so the list is a
complete inventory of the page's arithmetic. Design-for-change rule 10 needs it: when a
model later writes a "what this means" segment, a test asserts every number in its text
appears in this list.

**The section list as data.** `SECTIONS` is a tuple of specs, each a key, a title and
the function that fills it. Adding, removing or reordering a section is an edit to that
tuple and a bump of `REVIEW_VERSION`; nothing downstream hard-codes a section's place.

A section that has nothing to say says so in one sentence and carries no rows. An
absent measurement is a dash, never a zero (architecture rule 10).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from prudence.facts import purpose as purpose_module
from prudence.reviews import REVIEW_VERSION, schema
from prudence.reviews import suggestions as suggestions_module
from prudence.reviews.ranges import MATURITY_DAYS, Window
from prudence.reviews.schema import observation_key
from prudence.store import derived, views
from prudence.store import observations as observations_module
from prudence.store import outcomes as outcomes_module

NOT_MEASURED = "-"


@dataclass(frozen=True)
class Number:
    """One figure on the page: where it came from, what it is, and how it is printed."""

    key: str
    label: str
    text: str
    value: float | None = None
    coverage: float | None = None


@dataclass
class Section:
    """One block of the page: a table, some sentences, and the figures in them."""

    key: str
    title: str
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    numbers: list[Number] = field(default_factory=list)
    empty: str | None = None


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: str
    compute: Callable[[Context], Section]


@dataclass
class Context:
    """What every section is allowed to read: the store, the window, the names."""

    connection: sqlite3.Connection
    window: Window
    names: dict[str, str]
    now: datetime | None = None

    @property
    def project_name(self) -> str | None:
        key = self.window.project
        return None if key is None else self.names.get(key, key)


# --- the sections ------------------------------------------------------------------------


def _did(context: Context) -> Section:
    """What you did: the sessions of the window, by purpose, exactly as `usage` sums them."""
    section = Section(key="did", title="What you did")
    summary = views.usage_summary(
        context.connection,
        since=context.window.start,
        until=context.window.end,
        repo_key=context.window.project,
    )
    if not summary["sessions"]:
        section.empty = "No session started in this range."
        return section

    ids = _session_ids(context)
    credited = views.credited_map(context.connection, ids)
    commits = sum(counted["commits"] for counted in credited.values())
    coverages = [
        counted["coverage"] for counted in credited.values() if counted["coverage"] is not None
    ]
    coverage = (sum(coverages) / len(coverages)) if coverages else None

    section.headers = ["purpose", "sessions", "tokens", "active h"]
    order = purpose_module.PURPOSES
    cells = sorted(
        summary["by_purpose"].items(),
        key=lambda item: (-_tokens(item[1]), order.index(item[0]) if item[0] in order else 99),
    )
    for label, cell in cells:
        tokens = _thousands(cell)
        hours = f"{cell['hours']:.1f}"
        section.rows.append([label, str(cell["sessions"]), tokens, hours])
        section.numbers.append(
            Number(
                f"did.sessions.{label}",
                f"sessions labelled {label}",
                str(cell["sessions"]),
                float(cell["sessions"]),
            )
        )
        section.numbers.append(
            Number(f"did.tokens.{label}", f"tokens in {label} sessions", tokens, _tokens(cell))
        )
        section.numbers.append(
            Number(f"did.hours.{label}", f"active hours in {label} sessions", hours, cell["hours"])
        )

    total_sessions = str(summary["sessions"])
    total_hours = f"{sum(cell['hours'] for cell in summary['by_purpose'].values()):.1f}"
    total_tokens = _thousands(_merge(summary["by_purpose"].values()))
    section.rows.append(["all purposes", total_sessions, total_tokens, total_hours])
    section.numbers += [
        Number("did.sessions", "sessions in the range", total_sessions, float(summary["sessions"])),
        Number("did.tokens", "tokens in the range", total_tokens),
        Number("did.hours", "active hours in the range", total_hours),
        Number("did.commits", "commits credited to those sessions", str(commits), float(commits)),
        Number(
            "did.coverage",
            "mean coverage of those commits",
            _percent(coverage),
            coverage,
            coverage,
        ),
    ]
    section.notes = [
        f"{total_sessions} sessions, {commits} commits credited to them at fact or inferred "
        f"confidence, mean coverage {_percent(coverage)}.",
        "Token counts are in thousands and active hours are the sum of each session's "
        "sittings, the same way `prudence usage` counts them; a dash means that Claude Code "
        "version wrote no usage fields, which is not zero tokens.",
        "The purpose label comes from rules over the tool mix (purpose rule version "
        f"{summary['purpose_rule_version']}); no message text is read to produce it.",
    ]
    return section


def _became(context: Context) -> Section:
    """What became of earlier work: the commits whose seven-day mark fell in the window."""
    section = Section(key="became", title="What became of earlier work")
    totals = outcome_totals(
        context.connection,
        context.window.outcome_start,
        context.window.outcome_end,
        context.window.project,
    )
    section.notes.append(
        f"Commits made between {_day(context.window.outcome_start)} and "
        f"{_day(context.window.outcome_end)}, which is every commit whose "
        f"{MATURITY_DAYS}-day mark fell inside this review's range."
    )
    # A repository where other people commit has no `line_fate` rows at all, so it would
    # otherwise read as an empty window rather than as a withheld figure (rule 11).
    withheld = views.suppression_notes(context.connection)
    if context.window.project in withheld:
        section.empty = (
            f"No outcome facts for this project, because {withheld[context.window.project]}. "
            "Survival here would be about somebody else's code as much as yours."
        )
        return section
    if totals is None:
        section.empty = (
            "No commit in that span is credited with a line that could be followed, so there "
            "is no outcome to report."
        )
        return section

    shares = totals["shares"]
    coverage = _percent(totals["coverage"])
    section.headers = ["figure", "value", "coverage", "method"]
    method = f"{totals['fact']} fact, {totals['inferred']} inferred"
    figures = [
        ("lines followed", str(shares["lines"]), float(shares["lines"])),
        (
            "alive at 7 days",
            _cell(shares["alive_7d"], shares["measured_7d"]),
            shares["survival_7d"],
        ),
        (
            "alive at 30 days",
            _cell(shares["alive_30d"], shares["measured_30d"]),
            shares["survival_30d"],
        ),
        (
            "alive at 90 days",
            _cell(shares["alive_90d"], shares["measured_90d"]),
            shares["survival_90d"],
        ),
        ("alive at head", _cell(shares["alive_head"], shares["lines"]), shares["survival_head"]),
        (
            "reworked by you later",
            _cell(shares["reworked"], shares["lines"]),
            shares["reworked_share"],
        ),
    ]
    for label, text, value in figures:
        section.rows.append([label, text, coverage, method])
        section.numbers.append(
            Number(f"became.{label.replace(' ', '_')}", label, text, value, totals["coverage"])
        )
    section.numbers.append(
        Number(
            "became.commits",
            "commits in the outcome window",
            str(totals["commits"]),
            float(totals["commits"]),
        )
    )
    section.numbers.append(
        Number(
            "became.coverage",
            "mean coverage of those commits",
            coverage,
            totals["coverage"],
            totals["coverage"],
        )
    )
    section.notes += [
        f"{totals['commits']} commits, {method}. Coverage is the mean share of a counted "
        "commit's added lines the session itself wrote; every figure above is over the "
        "lines that coverage speaks for.",
        "A share is printed with the denominator it is over. A mark still in the future is a "
        "dash, not a death.",
        "Rework means a later commit of one of your own identities removed that line from "
        f"that path (line_fate fact version {outcomes_module.FACT_VERSION}).",
    ]
    return section


def _observations(context: Context) -> Section:
    """The join, in the same words `prudence observations` prints, with the same caveats."""
    section = Section(key="observations", title="Observations")
    # With a project scope the view returns that project's rows alone, so a pooled row
    # never appears inside a project's review (principle 2); without one it returns
    # every row with the pooled ones last, and the sentences say which is which.
    rows = views.observations(context.connection, context.window.project)
    if not rows:
        section.empty = observations_module.NOTHING
        return section

    section.headers = ["what your own sessions did", "coverage and method"]
    for row in rows:
        sentence = observations_module.sentence(row, context.names.get(row["repo_key"]))
        caveat = observations_module.caveat(row)
        section.rows.append([sentence, caveat])
        key = observation_key(row)
        section.numbers.append(
            Number(
                f"observation.{key}.with",
                f"{row['fact']} {row['outcome']} on the side that did",
                _percent(row["with_value"]),
                row["with_value"],
                row["coverage"],
            )
        )
        section.numbers.append(
            Number(
                f"observation.{key}.without",
                f"{row['fact']} {row['outcome']} on the side that did not",
                _percent(row["without_value"]),
                row["without_value"],
                row["coverage"],
            )
        )
    pooled = sum(1 for row in rows if row["repo_key"] == observations_module.POOLED)
    section.notes = [
        f"{len(rows)} observations, {pooled} of them pooled over every project. A pooled row "
        "is computed only for a behaviour no single project had the sessions to answer and is "
        "not a finding about any one of them.",
        "An observation splits your own sessions that are credited with followed lines in two "
        f"at one threshold and takes each side's median. It is kept only with at least "
        f"{observations_module.MIN_SESSIONS} sessions on each side and at least "
        f"{observations_module.MIN_GAP * 100:.0f} points between the medians.",
        "These are descriptions, not advice (observation fact version "
        f"{observations_module.FACT_VERSION}).",
    ]
    return section


def _compared(context: Context) -> Section:
    """The same range length, one period earlier, and the change between the two."""
    previous = context.window.previous()
    section = Section(key="compared", title="Compared with the previous period")
    section.notes.append(
        f"The previous period of the same length: {_day(previous.start)} to "
        f"{_day(previous.end)} ({context.window.days:.0f} days)."
    )
    here = views.usage_summary(
        context.connection,
        since=context.window.start,
        until=context.window.end,
        repo_key=context.window.project,
    )
    there = views.usage_summary(
        context.connection,
        since=previous.start,
        until=previous.end,
        repo_key=previous.project,
    )
    now_outcomes = outcome_totals(
        context.connection,
        context.window.outcome_start,
        context.window.outcome_end,
        context.window.project,
    )
    then_outcomes = outcome_totals(
        context.connection, previous.outcome_start, previous.outcome_end, previous.project
    )
    if not here["sessions"] and not there["sessions"]:
        section.empty = "Neither period holds a session."
        return section

    section.headers = ["figure", "this period", "previous period", "change"]
    pairs: list[tuple[str, str, str, str]] = []

    this_sessions, that_sessions = here["sessions"], there["sessions"]
    pairs.append(
        (
            "sessions",
            str(this_sessions),
            str(that_sessions),
            _delta_count(this_sessions, that_sessions),
        )
    )
    this_hours = sum(cell["hours"] for cell in here["by_purpose"].values())
    that_hours = sum(cell["hours"] for cell in there["by_purpose"].values())
    pairs.append(
        (
            "active hours",
            f"{this_hours:.1f}",
            f"{that_hours:.1f}",
            _delta_count(this_hours, that_hours, decimals=1),
        )
    )
    this_tokens = _merge(here["by_purpose"].values())
    that_tokens = _merge(there["by_purpose"].values())
    both_measured = this_tokens["measured"] and that_tokens["measured"]
    pairs.append(
        (
            "tokens",
            _thousands(this_tokens),
            _thousands(that_tokens),
            _delta_count(_tokens(this_tokens), _tokens(that_tokens), unit="k", scale=1000)
            if both_measured
            else NOT_MEASURED,
        )
    )
    for label, key in (("rework share", "reworked_share"), ("alive at 7 days", "survival_7d")):
        here_value = now_outcomes["shares"][key] if now_outcomes else None
        there_value = then_outcomes["shares"][key] if then_outcomes else None
        pairs.append(
            (
                label,
                _percent(here_value),
                _percent(there_value),
                _delta_points(here_value, there_value),
            )
        )

    for label, this_text, that_text, change in pairs:
        section.rows.append([label, this_text, that_text, change])
        key = label.replace(" ", "_")
        section.numbers.append(Number(f"compared.{key}.now", f"{label}, this period", this_text))
        section.numbers.append(
            Number(f"compared.{key}.previous", f"{label}, previous period", that_text)
        )
        section.numbers.append(Number(f"compared.{key}.change", f"{label}, change", change))
    section.notes.append(
        "The outcome rows compare the two periods' own outcome windows, each seven days "
        "behind its activity window, so both sides are commits that had reached the same age."
    )
    if now_outcomes is None or then_outcomes is None:
        section.notes.append(
            "One of the two periods has no commit with followed lines, so its outcome cells "
            "are dashes rather than zeroes."
        )
    return section


def _suggestions(context: Context) -> Section:
    """What became of the suggestions the last review left open."""
    section = Section(key="suggestions", title="Last time's suggestions")
    open_rows = schema.open_suggestions(context.connection)
    if context.window.project is not None:
        # A finding about one project never appears in another (principle 2), and a
        # key is `project|behaviour|outcome`, so the scope filter is the first field.
        scope = f"{context.window.project}|"
        open_rows = [row for row in open_rows if row["observation_key"].startswith(scope)]
    if not open_rows:
        section.empty = "No suggestion is open from an earlier review."
        return section

    section.headers = ["suggestion", "then", "since", "sessions"]
    for row in open_rows:
        moved = suggestions_module.follow_up(
            context.connection, row["observation_key"], context.window.start
        )
        section.rows.append(
            [
                f"#{row['id']} {row['text']}",
                moved["before_text"],
                moved["since_text"],
                f"{moved['before_n']} then, {moved['since_n']} since",
            ]
        )
        section.numbers.append(
            Number(
                f"suggestion.{row['id']}.before",
                f"suggestion {row['id']}: the outcome before",
                moved["before_text"],
                moved["before_value"],
            )
        )
        section.numbers.append(
            Number(
                f"suggestion.{row['id']}.since",
                f"suggestion {row['id']}: the outcome since",
                moved["since_text"],
                moved["since_value"],
            )
        )
    section.notes = [
        "Then is the sessions that started before this review's range, since is the ones "
        f"inside it. A side with fewer than {observations_module.MIN_SESSIONS} sessions is a "
        "dash: the floor the observations use holds here too.",
        "Dismiss one with `prudence suggestions dismiss <id>`; it is not raised again.",
    ]
    return section


# The page, in order. Adding, removing or reordering one is an edit here and a bump of
# `REVIEW_VERSION`; nothing downstream knows a section's position.
SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("did", "What you did", _did),
    SectionSpec("became", "What became of earlier work", _became),
    SectionSpec("observations", "Observations", _observations),
    SectionSpec("compared", "Compared with the previous period", _compared),
    SectionSpec("suggestions", "Last time's suggestions", _suggestions),
)


def build(
    connection: sqlite3.Connection, window: Window, now: datetime | None = None
) -> dict[str, Any]:
    """Every section and every figure in them, as the JSON a `review` row stores.

    A section that raises is recorded as unavailable rather than taken down with the
    page: an unknown state is kept, counted and skipped, never fatal (rule 3).
    """
    context = Context(
        connection=connection, window=window, names=views.repository_names(connection), now=now
    )
    sections: list[dict[str, Any]] = []
    numbers: list[dict[str, Any]] = []
    for spec in SECTIONS:
        try:
            section = spec.compute(context)
        except sqlite3.OperationalError as error:
            section = Section(
                key=spec.key,
                title=spec.title,
                empty=f"Not available: {error}. Run `prudence ingest`.",
            )
        sections.append(asdict(section))
        numbers.extend(asdict(number) for number in section.numbers)
    return {
        "review_version": REVIEW_VERSION,
        "window": asdict(window),
        "project_name": context.project_name,
        "sections": sections,
        "numbers": numbers,
        "versions": {
            "parser": derived.PARSER_VERSION,
            "line_fate_fact": outcomes_module.FACT_VERSION,
            "observation_fact": observations_module.FACT_VERSION,
        },
    }


def coverage_of(payload: dict[str, Any]) -> float | None:
    """The review row's coverage column: the outcome section's, which is the one that matters."""
    for number in payload.get("numbers", []):
        if number.get("key") == "became.coverage":
            return number.get("coverage")
    return None


# --- the shared reads ----------------------------------------------------------------------


def outcome_totals(
    connection: sqlite3.Connection, start: str, end: str, repo_key: str | None
) -> dict[str, Any] | None:
    """The fate of the lines of every credited commit made in `[start, end)`.

    `views.fate_by_commit` and `views.outcome_shares` do the arithmetic, the same two
    functions `prudence outcomes` prints from; this only decides which commits are in
    the window and sums their aggregates. None when no commit in the window is credited
    with a line that could be followed.
    """
    hashes = _commits_between(connection, start, end, repo_key)
    if not hashes:
        return None
    labelled = views.credited_by_commit(connection, hashes)
    counted = [commit for commit in hashes if commit in labelled]
    if not counted:
        return None
    fates = views.fate_by_commit(connection, counted)
    if not fates:
        return None
    totals = views.empty_fate()
    for fate in fates.values():
        for name in views.FATE_KEYS:
            totals[name] += fate[name]
    shares = views.outcome_shares(totals)
    if shares is None:
        return None
    coverages = [
        coverage
        for commit, (_, coverage) in labelled.items()
        if commit in fates and coverage is not None
    ]
    mix = {"fact": 0, "inferred": 0}
    for commit, (label, _) in labelled.items():
        if commit in fates and label in mix:
            mix[label] += 1
    return {
        "shares": shares,
        "commits": len(fates),
        "coverage": (sum(coverages) / len(coverages)) if coverages else None,
        **mix,
    }


def _commits_between(
    connection: sqlite3.Connection, start: str, end: str, repo_key: str | None
) -> list[str]:
    query = 'SELECT commit_hash FROM "commit" WHERE committer_at >= ? AND committer_at < ?'
    parameters: list[str] = [start, end]
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    try:
        return [row["commit_hash"] for row in connection.execute(query, parameters)]
    except sqlite3.OperationalError:
        return []


def _session_ids(context: Context) -> list[str]:
    query = "SELECT session_id FROM session WHERE first_at >= ? AND first_at < ?"
    parameters = [context.window.start, context.window.end]
    if context.window.project is not None:
        query += " AND repo_key = ?"
        parameters.append(context.window.project)
    try:
        return [row["session_id"] for row in context.connection.execute(query, parameters)]
    except sqlite3.OperationalError:
        return []


# --- the words numbers are printed in -------------------------------------------------------


def _tokens(cell: dict[str, Any]) -> float:
    return float(sum(cell.get(column, 0) for column in views.TOKEN_COLUMNS))


def _merge(cells: Any) -> dict[str, Any]:
    total = {"measured": 0, **dict.fromkeys(views.TOKEN_COLUMNS, 0)}
    for cell in cells:
        total["measured"] += cell.get("measured", 0)
        for column in views.TOKEN_COLUMNS:
            total[column] += cell.get(column, 0)
    return total


def _thousands(cell: dict[str, Any]) -> str:
    """A token count in thousands, or a dash when no session in the group measured any."""
    if not cell.get("measured"):
        return NOT_MEASURED
    return _k(int(round(_tokens(cell))))


def _k(count: int) -> str:
    """A token count in thousands, the same way `cli/render.thousands` prints one.

    Inlined rather than imported: the engine must not depend on a surface, and one
    format string is a smaller price than `reviews` importing `cli`.
    """
    return str(count) if count < 1000 else f"{count / 1000:.0f}k"


def _percent(value: float | None) -> str:
    return NOT_MEASURED if value is None else f"{value * 100:.0f}%"


def _cell(alive: int, measured: int) -> str:
    """`82% (1204)`: the share and the number of lines it is over, as `outcomes` prints it."""
    if not measured:
        return NOT_MEASURED
    return f"{alive / measured * 100:.0f}% ({measured})"


def _delta_count(
    here: float, there: float, decimals: int = 0, unit: str = "", scale: float = 1
) -> str:
    """The change between two cells, over the values as they are printed (see below)."""
    change = round(here / scale, decimals) - round(there / scale, decimals)
    return f"{change:+.{decimals}f}{unit}"


def _delta_points(here: float | None, there: float | None) -> str:
    """The change in points, over the two shares as they are printed, not as they are held.

    A reader subtracts the two cells they can see. Taking the difference of the raw
    floats and rounding that instead produces a row whose three numbers do not add up,
    which reads as an error whether or not it is one.
    """
    if here is None or there is None:
        return NOT_MEASURED
    return f"{round(here * 100) - round(there * 100):+d} points"


def _day(value: str) -> str:
    return value[:10]
