"""The primitives more than one view module needs: the sitting rule and batched queries."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

SITTING_GAP = timedelta(minutes=60)


def _batched(
    connection: sqlite3.Connection, query: str, ids: list[str], suffix: str
) -> list[sqlite3.Row]:
    """Run a query over a list of sessions, in batches SQLite will accept as parameters."""
    rows: list[sqlite3.Row] = []
    joiner = " AND " if " WHERE " in query else " WHERE "
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        rows.extend(
            connection.execute(f"{query}{joiner}session_id IN ({placeholders}){suffix}", batch)
        )
    return rows
