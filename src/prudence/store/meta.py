"""One key/value table for the few facts about the store that are not derived from it.

Everything else under `store/` is either the archive or a table rebuilt from it, and a
rebuild swaps tables away (`derived._swap`). A version number that says how to read the
store must outlive that swap, so it lives in its own table, created with
`CREATE TABLE IF NOT EXISTS` and named by no rebuild step.

One key so far. `app_contract_version` is the version of the `app_*` view contract in
`store/app_views.py`: the Mac app reads it before it renders anything and says which
side to update when it does not know the number. It changes when a view's columns
change, never when a view's numbers do.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

APP_CONTRACT_VERSION_KEY = "app_contract_version"

# 2 (M3 batch 3): `app_session_list.edits`, `app_observation.observation_id` and
# `.sentence`, and the two new views `app_commits_by_day` and `app_review`. Nothing was
# removed or renamed, so the bump is what tells an older app that there is more to read,
# not that what it already reads has moved.
#
# 3 (M4 batch 3): `app_observation.threshold_value` and `.threshold_op`, the split as a
# number and an operator beside the words already in `threshold_text`, and
# `app_review.segment_language`. Appended at the end of each list for the same reason.
APP_CONTRACT_VERSION = "3"


def ensure_meta(connection: sqlite3.Connection) -> None:
    """Create the table if it is not there. Safe to call on every ingest and rebuild."""
    connection.execute(SCHEMA)


def get_meta(connection: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """One value, or `default` when the key or the table is missing.

    A store written by an older version has no `meta` table at all, which is a missing
    value and not an error (architecture rule 3).
    """
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return row["value"] if row is not None else default


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    """Write one value, creating the table first so a caller never has to remember to."""
    ensure_meta(connection)
    connection.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
