"""The join: how the user's own outcomes differ between sessions with and without a habit.

This is the table the product exists for. `facts/` says what happened in a session and
`outcomes.py` says what became of its lines; neither on its own answers the only
question worth asking, which is whether a habit cost this person anything in their own
work. An observation is that join and nothing more: one behaviour fact, a threshold that
splits the sessions credited with followed lines into two sides, and the median of one
outcome on each side, with the counts behind both.

The rules, all of them constants so a surface can print them and a test can pin them:

- **Only sessions with followed lines.** A session credited with no line at `fact` or
  `inferred` confidence has no outcome to compare, so it is on neither side. A
  repository whose outcomes are suppressed (`outcomes.py`) has no `line_fate` rows at
  all and therefore contributes nothing here either, which is the intended behaviour
  rather than a special case.
- **A documented threshold per fact** (`SPLITS`), stored on the row as `threshold_text`
  so the reader can check the split rather than trust it. Three shapes only: at least a
  value, above a value, or above the median of the set being compared. A purpose label
  is compared one label against every other label; sessions with no label are on neither
  side.
- **Two outcomes**, both per session and then taken as the median of each side: the
  share of the session's lines a later commit of the user's own removed (`rework`), and
  the share still present at HEAD (`alive_head`). The median rather than the mean,
  because one 19,000-line session would otherwise be the whole answer.
- **Two floors**: `MIN_SESSIONS` on each side and `MIN_GAP` between the two medians.
  Below either, no row exists. Small samples mislead, and a finding that appears at four
  sessions and vanishes at five was never a finding (M2 plan, risks).
- **Per repository first** (principle 2: a finding about one project never appears in
  another). A whole-store row, `repo_key = '*'`, is computed for a fact and outcome only
  when no single repository could answer it and the pooled sessions can. Those rows say
  "across your projects" in their own words and every surface keeps them in their own
  block, because they are not a finding about any one project.
- **Descriptive only.** A row says what the two sides did. It carries no advice, no
  ranking, no adjective, and no score (principle 3). `direction` is `higher` or `lower`
  and means the with-side against the without-side, not better or worse.

Every row carries the coverage and the method mix of the sessions behind it, as the M2
plan's design-for-change rule 6 requires of an observation as much as of an outcome: a
surface that cannot show the caveat does not show the number.

Nothing here reads message text, and nothing here calls a model. The wording functions
live in this module rather than in a surface because the phrasing of a fact belongs with
the threshold that defines it; the layout around them is the surface's business.
"""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from prudence.store import views

FACT_VERSION = 1

# Sessions required on each side before a split is compared at all.
MIN_SESSIONS = 5

# The smallest difference between the two medians that is kept, as a share (10 points).
MIN_GAP = 0.10

# The repository key of a row pooled over every project.
POOLED = "*"

# The outcomes compared, as attributes of `_Session`. Both are shares of the session's
# own followed lines, so both sides of a split are on the same scale.
OUTCOMES = ("rework", "alive_head")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation(
    repo_key TEXT NOT NULL,
    fact TEXT NOT NULL,
    threshold_text TEXT NOT NULL,
    outcome TEXT NOT NULL,
    with_n INTEGER NOT NULL,
    without_n INTEGER NOT NULL,
    with_value REAL NOT NULL,
    without_value REAL NOT NULL,
    direction TEXT NOT NULL,
    coverage REAL,
    fact_commits INTEGER NOT NULL,
    inferred_commits INTEGER NOT NULL,
    fact_version INTEGER NOT NULL,
    PRIMARY KEY (repo_key, fact, outcome)
) WITHOUT ROWID;
"""


@dataclass(frozen=True)
class Split:
    """One behaviour fact, the line that divides the sessions, and the words for it.

    `rule` is one of `at_least` (value or more), `above` (strictly more than value) or
    `above_median` (strictly more than the median of the set being compared, so the
    threshold is a property of the user's own work rather than a number invented here).
    `did` is how a sentence names the with-side; `did_not` names the other side.
    """

    fact: str
    rule: str
    value: float | None
    did: str
    did_not: str = "that did not"


# One entry per fact in `facts/registry.FACTS`, in the same order. A test pins that.
SPLITS: tuple[Split, ...] = (
    Split("sittings", "at_least", 3, "that ran over three or more sittings"),
    Split(
        "files_edited_unread",
        "above_median",
        None,
        "that edited more files before reading them than your median here",
    ),
    Split("formatter_runs", "above", 0, "that ran a formatter"),
    Split("test_runs", "above", 0, "that ran tests"),
    Split(
        "tests_before_commit",
        "at_least",
        0.5,
        "that ran tests before at least half of their commits",
    ),
    Split(
        "commit_attempts_per_commit",
        "above",
        2,
        "that attempted more than two commits for each commit counted",
    ),
    Split("repeated_errors", "above", 0, "that hit the same error three times or more"),
    Split("subagent_used", "above", 0, "that dispatched a subagent"),
    Split("compactions", "above", 0, "that compacted their context"),
    Split("context_resets", "above", 0, "that replayed an earlier session's records"),
    Split(
        "prompts_per_active_hour",
        "above_median",
        None,
        "that prompted more often per active hour than your median here",
    ),
)

_BY_FACT = {split.fact: split for split in SPLITS}

# A label is not a number, so it gets no threshold: one label against every other one.
PURPOSE_PREFIX = "purpose:"

NOTHING = (
    f"No observation clears the sample floor ({MIN_SESSIONS} sessions each side) and the "
    f"gap floor ({MIN_GAP * 100:.0f} points) yet."
)


@dataclass
class ObservationStats:
    sessions: int = 0
    repositories: int = 0
    rows: int = 0
    pooled: int = 0
    elapsed: float = 0.0


@dataclass
class Observation:
    """One row, in the order the table holds its columns."""

    repo_key: str
    fact: str
    threshold_text: str
    outcome: str
    with_n: int
    without_n: int
    with_value: float
    without_value: float
    direction: str
    coverage: float | None
    fact_commits: int
    inferred_commits: int
    fact_version: int = FACT_VERSION

    def as_row(self) -> tuple:
        return (
            self.repo_key,
            self.fact,
            self.threshold_text,
            self.outcome,
            self.with_n,
            self.without_n,
            self.with_value,
            self.without_value,
            self.direction,
            self.coverage,
            self.fact_commits,
            self.inferred_commits,
            self.fact_version,
        )


@dataclass
class _Session:
    """One session on one side of a split: its outcomes, its facts and its caveats."""

    session_id: str
    repo_key: str
    rework: float
    alive_head: float
    coverage: float | None
    fact_commits: int
    inferred_commits: int
    values: dict[str, float] = field(default_factory=dict)
    purpose: str | None = None


def build(connection: sqlite3.Connection) -> ObservationStats:
    """Recompute every observation. Dropped and rebuilt, never migrated (rule 1)."""
    started = time.monotonic()
    stats = ObservationStats()
    connection.execute("DROP TABLE IF EXISTS observation")
    connection.executescript(SCHEMA)

    sessions = _sessions(connection)
    stats.sessions = len(sessions)
    by_repo: dict[str, list[_Session]] = defaultdict(list)
    for session in sessions:
        by_repo[session.repo_key].append(session)

    found: list[Observation] = []
    answered: set[tuple[str, str]] = set()
    for repo_key in sorted(by_repo):
        rows = _observe(repo_key, by_repo[repo_key])
        found.extend(rows)
        answered.update((row.fact, row.outcome) for row in rows)
    stats.rows = len(found)
    stats.repositories = len({row.repo_key for row in found})

    for row in _observe(POOLED, sessions):
        if (row.fact, row.outcome) in answered:
            continue
        found.append(row)
        stats.pooled += 1

    connection.executemany(
        "INSERT OR REPLACE INTO observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [row.as_row() for row in found],
    )
    stats.elapsed = time.monotonic() - started
    return stats


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Rows in a project and rows pooled, or zeroes before the first run."""
    try:
        rows = connection.execute(
            "SELECT SUM(CASE WHEN repo_key = ? THEN 0 ELSE 1 END) AS projects,"
            " SUM(CASE WHEN repo_key = ? THEN 1 ELSE 0 END) AS pooled FROM observation",
            (POOLED, POOLED),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"projects": 0, "pooled": 0}
    return {"projects": rows["projects"] or 0, "pooled": rows["pooled"] or 0}


# --- the split ---------------------------------------------------------------------------


def _sessions(connection: sqlite3.Connection) -> list[_Session]:
    """Every session credited with lines that could be followed, with its two outcomes."""
    try:
        rows = connection.execute(
            "SELECT session_id, repo_key FROM session WHERE repo_key IS NOT NULL"
            " ORDER BY session_id"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    ids = [row["session_id"] for row in rows]
    if not ids:
        return []
    fates = views.outcomes_map(connection, ids)
    credited = views.credited_map(connection, ids)
    purposes = views.purpose_map(connection, ids)
    values = _fact_values(connection, ids)

    found: list[_Session] = []
    for row in rows:
        totals = fates.get(row["session_id"])
        if not totals or not totals["lines"]:
            continue
        counted = credited.get(row["session_id"], {})
        found.append(
            _Session(
                session_id=row["session_id"],
                repo_key=row["repo_key"],
                rework=totals["reworked"] / totals["lines"],
                alive_head=totals["alive_head"] / totals["lines"],
                coverage=counted.get("coverage"),
                fact_commits=counted.get("fact", 0),
                inferred_commits=counted.get("inferred", 0),
                values=values.get(row["session_id"], {}),
                purpose=purposes.get(row["session_id"]),
            )
        )
    return found


def _fact_values(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, float]]:
    """Every behaviour fact of every session asked about. A missing fact is simply absent."""
    result: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        for start in range(0, len(ids), 400):
            batch = ids[start : start + 400]
            placeholders = ", ".join("?" * len(batch))
            for row in connection.execute(
                "SELECT session_id, fact, value FROM session_fact"
                f" WHERE session_id IN ({placeholders}) AND value IS NOT NULL",
                batch,
            ):
                result[row["session_id"]][row["fact"]] = row["value"]
    except sqlite3.OperationalError:
        return {}
    return dict(result)


def _observe(where: str, sessions: list[_Session]) -> list[Observation]:
    """Every observation one set of sessions supports, facts first and then labels."""
    found: list[Observation] = []
    for split in SPLITS:
        held = [session for session in sessions if split.fact in session.values]
        if not held:
            continue
        line, text = _threshold(split, held)
        with_side: list[_Session] = []
        without_side: list[_Session] = []
        for session in held:
            matched = _above(split.rule, session.values[split.fact], line)
            (with_side if matched else without_side).append(session)
        found.extend(_compare(where, split.fact, text, with_side, without_side))

    labelled = [session for session in sessions if session.purpose]
    for label in sorted({session.purpose for session in labelled if session.purpose}):
        with_side = [session for session in labelled if session.purpose == label]
        without_side = [session for session in labelled if session.purpose != label]
        found.extend(
            _compare(
                where,
                f"{PURPOSE_PREFIX}{label}",
                f"purpose = {label}",
                with_side,
                without_side,
            )
        )
    return found


def _threshold(split: Split, held: list[_Session]) -> tuple[float, str]:
    """The number that divides the sessions, and the text every row carries with it."""
    if split.rule == "above_median":
        line = float(median(session.values[split.fact] for session in held))
        return line, f"{split.fact} > {line:g} (the median here)"
    line = float(split.value or 0)
    sign = ">=" if split.rule == "at_least" else ">"
    return line, f"{split.fact} {sign} {line:g}"


def _above(rule: str, value: float, line: float) -> bool:
    return value >= line if rule == "at_least" else value > line


def _compare(
    where: str,
    fact: str,
    threshold_text: str,
    with_side: list[_Session],
    without_side: list[_Session],
) -> list[Observation]:
    """The two medians per outcome, kept only when both floors are cleared."""
    if len(with_side) < MIN_SESSIONS or len(without_side) < MIN_SESSIONS:
        return []
    both = with_side + without_side
    coverages = [session.coverage for session in both if session.coverage is not None]
    found: list[Observation] = []
    for outcome in OUTCOMES:
        with_value = float(median(getattr(session, outcome) for session in with_side))
        without_value = float(median(getattr(session, outcome) for session in without_side))
        if abs(with_value - without_value) < MIN_GAP:
            continue
        found.append(
            Observation(
                repo_key=where,
                fact=fact,
                threshold_text=threshold_text,
                outcome=outcome,
                with_n=len(with_side),
                without_n=len(without_side),
                with_value=with_value,
                without_value=without_value,
                direction="higher" if with_value > without_value else "lower",
                coverage=(sum(coverages) / len(coverages)) if coverages else None,
                fact_commits=sum(session.fact_commits for session in both),
                inferred_commits=sum(session.inferred_commits for session in both),
            )
        )
    return found


# --- the words ---------------------------------------------------------------------------


def sentence(row: Any, name: str | None = None) -> str:
    """One observation in plain words, with its numbers and no adjective at all."""
    if row["repo_key"] == POOLED:
        where = "Across your projects"
    else:
        where = f"In {name or row['repo_key']}"
    did, did_not = phrases(row["fact"])
    return (
        f"{where}, your {row['with_n']} sessions {did} "
        f"{_outcome_words(row['outcome'], row['with_value'])}; "
        f"the {row['without_n']} {did_not}, {_percent(row['without_value'])}."
    )


def caveat(row: Any) -> str:
    """The coverage and the method mix of the sessions the sentence is built from."""
    coverage = "-" if row["coverage"] is None else f"{row['coverage'] * 100:.0f}%"
    return (
        f"(coverage: {coverage}, method: {row['fact_commits']} fact, "
        f"{row['inferred_commits']} inferred)"
    )


def phrases(fact: str) -> tuple[str, str]:
    """How the two sides of one split are named in a sentence."""
    if fact.startswith(PURPOSE_PREFIX):
        return f"labelled {fact[len(PURPOSE_PREFIX) :]}", "labelled otherwise"
    split = _BY_FACT.get(fact)
    if split is None:
        return f"with {fact}", "without it"
    return split.did, split.did_not


def _outcome_words(outcome: str, value: float) -> str:
    if outcome == "rework":
        return f"reworked {_percent(value)} of their lines (median)"
    return f"still have {_percent(value)} of their lines at head (median)"


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"
