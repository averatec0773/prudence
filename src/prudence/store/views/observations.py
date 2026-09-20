"""The observation rows, as `prudence observations` and the MCP tool of that name read them."""

from __future__ import annotations

import sqlite3
from typing import Any


def observations(
    connection: sqlite3.Connection, repo_key: str | None = None
) -> list[dict[str, Any]]:
    """The observation rows, in one project or in all of them, pooled rows last.

    With a `repo_key` the answer holds that project's rows alone: a pooled row speaks
    for every project at once and principle 2 keeps it out of a project's view. With
    none, every row comes back and the surface separates them itself. Empty before
    `prudence rebuild` has built the table.
    """
    from prudence.store import observations as observations_module

    try:
        if repo_key is not None:
            rows = connection.execute(
                "SELECT * FROM observation WHERE repo_key = ? ORDER BY fact, outcome",
                (repo_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM observation ORDER BY CASE WHEN repo_key = ? THEN 1 ELSE 0 END,"
                " repo_key, fact, outcome",
                (observations_module.POOLED,),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]
