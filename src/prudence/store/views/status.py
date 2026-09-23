"""`prudence status`, as JSON."""

from __future__ import annotations

import sqlite3
from typing import Any

from prudence.store.views.usage import (
    bucket_totals,
    purpose_counts,
    purpose_rule_version,
    usage_totals,
)


def status_summary(connection: sqlite3.Connection | None) -> dict[str, Any]:
    """What `prudence status` prints, as JSON. Ids, counts and versions only."""
    from prudence import config as config_module
    from prudence.store import (
        archive,
        attribution,
        commits,
        derived,
        observations,
        outcomes,
        rewritten,
        spool,
    )

    config = config_module.load()
    repositories = []
    for repo in sorted(config.repositories.values(), key=lambda r: r.name):
        files, archived_bytes = 0, 0
        counted = {"sessions": 0, "edits": 0, "commits": 0}
        if connection is not None:
            row = connection.execute(
                "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file"
                " WHERE repo_key = ?",
                (repo.key,),
            ).fetchone()
            files, archived_bytes = row["files"], row["size"]
            for name, statement in (
                ("sessions", "SELECT COUNT(*) FROM session WHERE repo_key = ?"),
                ("edits", "SELECT COUNT(*) FROM edit WHERE repo_key = ?"),
                ("commits", 'SELECT COUNT(*) FROM "commit" WHERE repo_key = ?'),
            ):
                try:
                    counted[name] = connection.execute(statement, (repo.key,)).fetchone()[0]
                except sqlite3.OperationalError:
                    counted[name] = 0
        repositories.append(
            {
                "repo_key": repo.key,
                "name": repo.name,
                "level": repo.level,
                "files": files,
                "archived_bytes": archived_bytes,
                **counted,
            }
        )

    result: dict[str, Any] = {
        "repositories": repositories,
        "database_built": connection is not None,
    }
    if connection is None:
        return result

    files, original, stored = archive.archive_totals(connection)
    result["archive"] = {"files": files, "original_bytes": original, "stored_bytes": stored}
    counts = derived.counts(connection)
    result["built"] = counts["session"] >= 0
    if not result["built"]:
        return result
    result["derived"] = {**counts, "parser_version": derived.PARSER_VERSION}
    result["usage"] = usage_totals(connection)
    result["buckets"] = bucket_totals(connection)
    result["purposes"] = {
        "by_label": purpose_counts(connection),
        "rule_version": purpose_rule_version(connection),
    }
    result["commands_by_class"] = {
        row["command_class"]: row["n"]
        for row in connection.execute(
            "SELECT command_class, COUNT(*) AS n FROM command"
            " GROUP BY command_class ORDER BY n DESC"
        )
    }
    result["observations"] = {
        **observations.counts(connection),
        "min_sessions": observations.MIN_SESSIONS,
        "min_gap": observations.MIN_GAP,
        "fact_version": observations.FACT_VERSION,
    }

    harvested, commit_lines = commits.counts(connection)
    result["commits"] = {
        "harvested": harvested,
        "added_lines_hashed": commit_lines,
        "fact_version": commits.FACT_VERSION,
        "by_method": attribution.counts(connection),
        "by_confidence": attribution.confidence_counts(connection),
        "printed_hashes": rewritten.resolution(connection),
        "silent_matched": rewritten.silent_matches(connection),
        "attribution_fact_version": attribution.FACT_VERSION,
        "commit_alias_fact_version": rewritten.FACT_VERSION,
    }
    result["outcomes"] = {
        **outcomes.counts(connection),
        "suppressed": outcomes.suppressed_repositories(connection),
        "suppressed_reasons": outcomes.suppression_notes(connection),
        "bot_commits": connection.execute(
            'SELECT COUNT(*) FROM "commit" WHERE is_bot = 1'
        ).fetchone()[0],
        "fact_version": outcomes.FACT_VERSION,
    }
    events, hook_sessions = spool.counts(connection)
    result["hook_events"] = {
        "events": events,
        "sessions": hook_sessions,
        "fact_version": spool.FACT_VERSION,
    }
    result["unassigned_sessions"] = connection.execute(
        "SELECT COUNT(*) FROM session WHERE repo_key IS NULL"
    ).fetchone()[0]
    result["mapped_by_fallback"] = mapped_by_fallback(connection)
    result["resumed_sessions"] = connection.execute(
        "SELECT COUNT(*) FROM session WHERE notes LIKE '%resumed%'"
    ).fetchone()[0]
    result["unknown_record_types"] = [
        dict(row)
        for row in connection.execute(
            "SELECT type, claude_version, count FROM unknown_record_type ORDER BY count DESC, type"
        )
    ]
    return result


def mapped_by_fallback(connection: sqlite3.Connection) -> dict[str, int]:
    """How many sessions needed each fallback rule to find their repository.

    The rule that found it is written into `session.notes` by `derived.build`, which is
    where `cli/status.py` reads it from too; there is no column for it.
    """
    found: dict[str, int] = {}
    for row in connection.execute(
        "SELECT notes, COUNT(*) AS n FROM session WHERE notes LIKE '%repository by%' GROUP BY notes"
    ):
        for part in row["notes"].split("; "):
            if part.startswith("repository by "):
                method = part[len("repository by ") :]
                found[method] = found.get(method, 0) + row["n"]
    return found
