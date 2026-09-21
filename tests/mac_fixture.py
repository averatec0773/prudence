"""Builds the fixture store the Swift tests read. Not collected by the normal run.

The Mac app's tests decode real `app_*` rows rather than SQL retyped in Swift, which means
they need a store the engine itself wrote. This file makes one out of the same synthetic
machine `conftest.py` gives every other test, adds a few rows the small scenario cannot
produce on its own (observations need five sessions a side, a review needs a range), and
vacuums the result into the Swift test bundle at about 350 KB.

The name has no `test_` prefix on purpose, so `pytest` does not collect it with the suite.
Run it by naming it, which is how the fixture is regenerated when the contract changes:

    MAC_FIXTURE_TARGET=apps/mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db \\
        uv run pytest tests/mac_fixture.py -q
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from conftest import Workspace, record_one_session

from prudence.paths import database_file
from prudence.reviews import schema
from prudence.store import app_views, db

TARGET = os.environ.get("MAC_FIXTURE_TARGET")


@pytest.mark.skipif(not TARGET, reason="set MAC_FIXTURE_TARGET to regenerate the fixture")
def test_make_fixture(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        repo_key = lab.repo_key()
        _usage_session(connection, "synthetic-a", repo_key, "2026-09-15T09:00:00", "development")
        _usage_session(connection, "synthetic-b", repo_key, "2026-09-15T10:00:00", "research")
        _usage_session(connection, "synthetic-c", repo_key, "2026-09-14T09:00:00", "debugging")
        for row in (
            (repo_key, "test_runs", "more than 0", "rework", 7, 9, 0.12, 0.31, "lower", 0.86, 5, 2),
            (
                repo_key,
                "sittings",
                "3 or more",
                "alive_head",
                6,
                11,
                0.71,
                0.54,
                "higher",
                0.9,
                4,
                3,
            ),
            ("*", "subagent_used", "more than 0", "rework", 8, 14, 0.22, 0.4, "lower", 0.77, 6, 5),
        ):
            connection.execute(
                "INSERT OR REPLACE INTO observation (repo_key, fact, threshold_text, outcome,"
                " with_n, without_n, with_value, without_value, direction, coverage,"
                " fact_commits, inferred_commits, fact_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                row,
            )
        schema.insert_review(
            connection,
            created_at="2026-09-15T18:00:00",
            range_start="2026-09-08T00:00:00",
            range_end="2026-09-15T00:00:00",
            project=None,
            outcome_range_start="2026-09-01T00:00:00",
            outcome_range_end="2026-09-08T00:00:00",
            sections={
                "review_version": 1,
                "sections": [
                    {"key": "did", "title": "What you did", "headers": [], "rows": []},
                    {"key": "became", "title": "What became of earlier work"},
                ],
                "numbers": [],
            },
            coverage=0.82,
            fact_version=1,
            parser_version=2,
        )
        app_views.install_app_views(connection)
        connection.commit()
    finally:
        connection.close()

    target = Path(TARGET)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(database_file())
    try:
        source.execute("VACUUM INTO ?", (str(target),))
    finally:
        source.close()
    shutil.rmtree(target.parent / "__pycache__", ignore_errors=True)
    assert target.stat().st_size < 1_000_000, target.stat().st_size


def _usage_session(
    connection: sqlite3.Connection, session_id: str, repo_key: str, first_at: str, purpose: str
) -> None:
    connection.execute(
        "INSERT INTO session (session_id, repo_key, source, entrypoint, cwd, first_at,"
        " last_at, record_count, capture_level, parser_version, notes)"
        " VALUES (?, ?, 'claude_code', 'cli', NULL, ?, ?, 1, 'full', 2, NULL)",
        (session_id, repo_key, first_at, first_at),
    )
    tokens = {"development": (4000, 900, 120, 60), "research": (700, 150, 20, 5)}.get(
        purpose, (200, 40, 0, 0)
    )
    connection.execute(
        "INSERT INTO usage (record_id, session_id, turn_id, request_id, model, input_tokens,"
        " output_tokens, cache_read_tokens, cache_creation_tokens, parser_version)"
        " VALUES (?, ?, NULL, ?, 'claude-x', ?, ?, ?, ?, 2)",
        (f"{session_id}-u1", session_id, f"{session_id}-req1", *tokens),
    )
    connection.execute(
        "INSERT INTO session_label (session_id, name, label, rule_version)"
        " VALUES (?, 'purpose', ?, 1)",
        (session_id, purpose),
    )
