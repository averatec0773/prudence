"""What became of the lines: commits credited to a session, and the fate of what they added."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from typing import Any

from prudence.store import attribution as attribution_module
from prudence.store.views.common import _batched
from prudence.store.views.sessions import repository_names, session_facts, session_row
from prudence.store.views.usage import purpose_of, purpose_rule_version

# Every counter one aggregate holds. The `measured_*` counters are the denominators:
# a mark that has not happened yet is NULL in `line_fate`, so the share of lines alive
# at 90 days is over the lines whose 90-day mark exists, not over all of them.
FATE_KEYS = (
    "lines",
    "measured_7d",
    "alive_7d",
    "measured_30d",
    "alive_30d",
    "measured_90d",
    "alive_90d",
    "alive_head",
    "alive_head_anywhere",
    "blame_head",
    "reworked",
)


# --- commits per session, counted by the confidence rule ------------------------------


def credited_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Commits per session split by confidence, and the mean coverage over the counted ones.

    One commit can carry two rows for the same session (it ran `git commit` and it wrote
    the lines), so each commit is counted once, at its best label. `uncertain` is
    reported and never added to `commits`, which is what principle 3 asks for.
    """
    order = {label: index for index, label in enumerate(attribution_module.CONFIDENCES)}
    best: dict[str, dict[str, tuple[str, float | None]]] = defaultdict(dict)
    for row in _batched(
        connection,
        "SELECT session_id, commit_hash, confidence, coverage FROM attribution",
        ids,
        "",
    ):
        seen = best[row["session_id"]].get(row["commit_hash"])
        if seen is None or order[row["confidence"]] < order[seen[0]]:
            best[row["session_id"]][row["commit_hash"]] = (row["confidence"], row["coverage"])

    result: dict[str, dict[str, Any]] = {}
    for session_id, commits in best.items():
        counted = Counter(label for label, _ in commits.values())
        coverages = [
            coverage
            for label, coverage in commits.values()
            if label in attribution_module.COUNTED and coverage is not None
        ]
        result[session_id] = {
            "fact": counted[attribution_module.FACT],
            "inferred": counted[attribution_module.INFERRED],
            "uncertain": counted[attribution_module.UNCERTAIN],
            "commits": counted[attribution_module.FACT] + counted[attribution_module.INFERRED],
            "coverage": (sum(coverages) / len(coverages)) if coverages else None,
        }
    return result


def credited(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    """The same counts for one session, zeroed when it is credited with nothing."""
    return credited_map(connection, [session_id]).get(
        session_id, {"fact": 0, "inferred": 0, "uncertain": 0, "commits": 0, "coverage": None}
    )


# --- what became of the lines, aggregated from `line_fate` ----------------------------


def empty_fate() -> dict[str, int]:
    return dict.fromkeys(FATE_KEYS, 0)


def fate_by_commit(connection: sqlite3.Connection, hashes: list[str]) -> dict[str, dict[str, int]]:
    """One aggregate per commit, so a session and a repository can both be summed from it."""
    result: dict[str, dict[str, int]] = {}
    marks = ", ".join(
        f"SUM(CASE WHEN alive_{days}d IS NOT NULL THEN 1 ELSE 0 END) AS measured_{days}d,"
        f" SUM(COALESCE(alive_{days}d, 0)) AS alive_{days}d"
        for days in (7, 30, 90)
    )
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        try:
            rows = connection.execute(
                f"SELECT commit_hash, COUNT(*) AS lines, {marks},"
                " SUM(COALESCE(alive_head, 0)) AS alive_head,"
                " SUM(COALESCE(alive_head_anywhere, 0)) AS alive_head_anywhere,"
                " SUM(COALESCE(blame_head, 0)) AS blame_head,"
                " SUM(CASE WHEN reworked_by IS NOT NULL THEN 1 ELSE 0 END) AS reworked"
                f" FROM line_fate WHERE commit_hash IN ({placeholders}) GROUP BY commit_hash",
                batch,
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        for row in rows:
            result[row["commit_hash"]] = {key: row[key] or 0 for key in FATE_KEYS}
    return result


def counted_pairs(connection: sqlite3.Connection, ids: list[str]) -> list[tuple[str, str]]:
    """The (session, commit) pairs a statistic may be built from: `fact` and `inferred`.

    One commit can carry two rows for one session, so the pairs are distinct: a session
    that both ran `git commit` and wrote the lines is credited with one commit, not two.
    """
    return sorted(
        {
            (row["session_id"], row["commit_hash"])
            for row in _batched(
                connection,
                "SELECT DISTINCT session_id, commit_hash FROM attribution"
                f" WHERE confidence IN ('{attribution_module.FACT}',"
                f" '{attribution_module.INFERRED}')",
                ids,
                "",
            )
        }
    )


def outcomes_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, int]]:
    """What became of each session's counted lines, summed over its counted commits."""
    pairs = counted_pairs(connection, ids)
    if not pairs:
        return {}
    fates = fate_by_commit(connection, sorted({commit for _, commit in pairs}))
    result: dict[str, dict[str, int]] = {}
    for session_id, commit_hash in pairs:
        fate = fates.get(commit_hash)
        if fate is None:
            continue
        totals = result.setdefault(session_id, empty_fate())
        for name in FATE_KEYS:
            totals[name] += fate[name]
    return result


def outcomes_by_repository(
    connection: sqlite3.Connection, ids: list[str]
) -> dict[str, dict[str, Any]]:
    """The same totals per repository, over each commit once however many sessions share it.

    The credit columns are counted the same way: one commit is one commit, at its best
    label, whether one session or three are credited with it.
    """
    pairs = counted_pairs(connection, ids)
    hashes = sorted({commit for _, commit in pairs})
    if not hashes:
        return {}
    fates = fate_by_commit(connection, hashes)
    labelled = credited_by_commit(connection, hashes)
    repos: dict[str, str] = {}
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        for row in connection.execute(
            f'SELECT commit_hash, repo_key FROM "commit" WHERE commit_hash IN ({placeholders})',
            batch,
        ):
            repos[row["commit_hash"]] = row["repo_key"]
    result: dict[str, dict[str, Any]] = {}
    coverages: dict[str, list[float]] = defaultdict(list)
    for commit_hash, fate in fates.items():
        repo_key = repos.get(commit_hash) or "unassigned"
        totals = result.setdefault(
            repo_key, {**empty_fate(), "fact": 0, "inferred": 0, "coverage": None}
        )
        for name in FATE_KEYS:
            totals[name] += fate[name]
        label, coverage = labelled.get(commit_hash, (None, None))
        if label is not None:
            totals[label] += 1
        if coverage is not None:
            coverages[repo_key].append(coverage)
    for repo_key, values in coverages.items():
        result[repo_key]["coverage"] = sum(values) / len(values)
    return result


def credited_by_commit(
    connection: sqlite3.Connection, hashes: list[str]
) -> dict[str, tuple[str, float | None]]:
    """The best confidence label and its coverage for each commit, whoever is credited."""
    order = {label: index for index, label in enumerate(attribution_module.CONFIDENCES)}
    best: dict[str, tuple[str, float | None]] = {}
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        for row in connection.execute(
            "SELECT commit_hash, confidence, coverage FROM attribution"
            f" WHERE commit_hash IN ({placeholders})",
            batch,
        ):
            held = best.get(row["commit_hash"])
            if held is None or order[row["confidence"]] < order[held[0]]:
                best[row["commit_hash"]] = (row["confidence"], row["coverage"])
    return {
        commit: value for commit, value in best.items() if value[0] in attribution_module.COUNTED
    }


def outcomes_of(connection: sqlite3.Connection, session_id: str) -> dict[str, int] | None:
    """One session's outcome totals, or None when it is credited with no counted line."""
    return outcomes_map(connection, [session_id]).get(session_id)


def outcome_shares(totals: dict[str, int] | None) -> dict[str, Any] | None:
    """The counts plus the shares a surface prints, each with the denominator it is over.

    None all the way through when nothing was measured, never zero: a commit whose
    ninety-day mark is still in the future has not lost its lines.
    """
    if not totals or not totals["lines"]:
        return None
    return {
        **totals,
        "survival_7d": share(totals["alive_7d"], totals["measured_7d"]),
        "survival_30d": share(totals["alive_30d"], totals["measured_30d"]),
        "survival_90d": share(totals["alive_90d"], totals["measured_90d"]),
        "survival_head": share(totals["alive_head"], totals["lines"]),
        "survival_head_anywhere": share(totals["alive_head_anywhere"], totals["lines"]),
        "blame_head": share(totals["blame_head"], totals["lines"]),
        "reworked_share": share(totals["reworked"], totals["lines"]),
        "fact_version": _outcome_fact_version(),
    }


def _outcome_fact_version() -> int:
    from prudence.store import outcomes as outcomes_module

    return outcomes_module.FACT_VERSION


def share(alive: int, measured: int) -> float | None:
    """A survival share, or None when nothing was measured. Never zero by default."""
    return (alive / measured) if measured else None


def suppressed_repositories(connection: sqlite3.Connection) -> set[str]:
    """Repositories whose outcome facts are withheld because other authors dominate."""
    return set(suppression_notes(connection))


def suppression_notes(connection: sqlite3.Connection) -> dict[str, str]:
    """Why each withheld repository was withheld, with the counts behind the decision."""
    try:
        return {
            row["repo_key"]: row["outcomes_suppressed_note"] or ""
            for row in connection.execute(
                "SELECT repo_key, outcomes_suppressed_note FROM repository"
                " WHERE outcomes_suppressed = 1"
            )
        }
    except sqlite3.OperationalError:
        return {}


def session_outcomes(connection: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """One session's outcomes, the MCP tool of the same name and nothing else needs.

    Survival at 7, 30 and 90 days and at head with the denominator each share is over
    (`outcomes`, None when the repository's outcomes are suppressed or nothing was
    measured), the share reworked, the coverage and method mix behind the counted
    commits, the session's purpose and its behaviour facts with their trust level. None
    when the id does not match a session. No message text, because none is stored.
    """
    row = session_row(connection, session_id)
    if row is None:
        return None
    counted = credited(connection, session_id)
    return {
        "session_id": session_id,
        "repository": repository_names(connection).get(row["repo_key"], row["repo_key"]),
        "outcomes": outcome_shares(outcomes_of(connection, session_id)),
        "outcomes_suppressed": row["repo_key"] in suppressed_repositories(connection),
        "outcomes_suppressed_reason": suppression_notes(connection).get(row["repo_key"]),
        "commits_fact": counted["fact"],
        "commits_inferred": counted["inferred"],
        "commits_uncertain": counted["uncertain"],
        "coverage": counted["coverage"],
        "purpose": purpose_of(connection, session_id),
        "purpose_rule_version": purpose_rule_version(connection),
        "behaviour_facts": session_facts(connection, session_id),
    }
