"""`store/views.py`: the read queries `prudence show` and the MCP server share.

`cli/show.py`'s own tests (`tests/test_show.py`) already cover the text rendering built
on these functions; this file covers the data shapes directly, and the search and
status queries that only the MCP server calls.
"""

from __future__ import annotations

import json
import sqlite3

from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.store import db, views


def test_session_summary_has_the_shape_show_session_promises(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        summary = views.session_summary(connection, SAMPLE_SESSION)
    finally:
        connection.close()

    assert summary is not None
    assert summary["session_id"] == SAMPLE_SESSION
    assert summary["identity"]["capture_level"] == "full"
    assert summary["identity"]["repository"] == "alpha"
    assert summary["identity"]["cwd"], "full capture keeps the working directory"
    assert summary["identity"]["sittings"] == 1
    assert summary["counts"]["edits"] == 1
    assert summary["counts"]["lines_added"] == 3
    assert summary["counts"]["lines_removed"] == 0
    assert summary["counts"]["tool_calls_by_name"] == {"Bash": 1, "Write": 1}
    assert summary["files"]["withheld"] is False
    assert [f["path"] for f in summary["files"]["edits"]] == ["src/app.py"]

    # The session both ran `git commit` (in_session) and wrote the lines the commit
    # added (line_match, rank 1); attribution never mixes methods into one row, so both
    # are present, the same as `prudence show --session` prints them.
    methods = {commit["method"] for commit in summary["commits"]}
    assert methods == {"in_session", "line_match"}
    for commit in summary["commits"]:
        assert len(commit["commit_hash"]) == 40, "the full hash, not a shortened one"

    blob = json.dumps(summary)
    assert "Write the app" not in blob, "no message text anywhere in the JSON"
    assert "commit it" not in blob


def test_session_summary_reports_usage_and_the_three_confidence_counts(lab: Workspace) -> None:
    """The sample session's own transcript carries no usage fields, so usage is None."""
    record_one_session(lab)
    connection = db.connect()
    try:
        summary = views.session_summary(connection, SAMPLE_SESSION)
        found = views.search_sessions(connection)
    finally:
        connection.close()

    assert summary["usage"] is None, "absent usage is None, never zero"
    assert summary["commits_fact"] == 1, "it ran git commit and git printed the hash"
    assert summary["commits_inferred"] == 0
    assert summary["commits_uncertain"] == 0
    # Two rows, one commit: it ran `git commit` and it wrote the lines. The rows keep
    # their own labels; the counts above take the commit at its best one, once.
    assert {commit["confidence"] for commit in summary["commits"]} == {"fact", "inferred"}

    result = found["results"][0]
    assert result["tokens"] is None
    assert (result["commits_fact"], result["commits_inferred"], result["commits_uncertain"]) == (
        1,
        0,
        0,
    )
    assert result["commits_attributed"] == 1, "fact and inferred together, never uncertain"


def test_status_summary_carries_the_token_and_hash_counts(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        summary = views.status_summary(connection)
    finally:
        connection.close()

    assert summary["usage"] == {
        "requests": 0,
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }
    assert summary["commits"]["by_confidence"] == {"fact": 1, "inferred": 0, "uncertain": 0}
    assert summary["commits"]["printed_hashes"] == {
        "printed": 1,
        "resolved": 1,
        "reidentified": 0,
        "unresolved": 0,
    }


def test_session_summary_withholds_paths_at_metadata_only(lab: Workspace) -> None:
    record_one_session(lab, level="metadata-only")
    connection = db.connect()
    try:
        summary = views.session_summary(connection, SAMPLE_SESSION)
    finally:
        connection.close()

    assert summary["files"]["withheld"] is True
    assert summary["files"]["edits"] == []
    assert summary["identity"]["cwd"] is None
    assert summary["counts"]["edits"] == 1, "the shape survives; only the paths are gone"


def test_session_summary_is_none_for_an_unknown_id(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        assert views.session_summary(connection, "no-such-session") is None
    finally:
        connection.close()


def test_search_sessions_filters_by_query_repo_and_date(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        repo_key = lab.repo_key()

        by_path = views.search_sessions(connection, query="app.py", repo_key=repo_key)
        assert by_path["total"] == 1
        assert by_path["results"][0]["session_id"] == SAMPLE_SESSION
        assert by_path["results"][0]["repository"] == "alpha"
        assert by_path["results"][0]["commits_attributed"] == 1

        by_class = views.search_sessions(connection, query="git_commit")
        assert by_class["total"] == 1

        assert views.search_sessions(connection, query="nothing-like-this")["total"] == 0
        assert views.search_sessions(connection, repo_key="not-a-real-key")["total"] == 0
        assert views.search_sessions(connection, since="2099-01-01")["total"] == 0
        assert views.search_sessions(connection, until="2000-01-01")["total"] == 0
    finally:
        connection.close()


def test_search_sessions_caps_the_limit_regardless_of_what_is_asked(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        _insert_bare_sessions(connection, 150)

        over_the_cap = views.search_sessions(connection, limit=1000)
        assert over_the_cap["total"] == 151
        assert len(over_the_cap["results"]) == views.MAX_LIMIT
        assert over_the_cap["truncated"] is True

        default = views.search_sessions(connection)
        assert len(default["results"]) == views.DEFAULT_LIMIT
        assert default["truncated"] is True

        small = views.search_sessions(connection, limit=5)
        assert len(small["results"]) == 5
        assert small["truncated"] is True
    finally:
        connection.close()


def test_resolve_date_understands_shorthand_and_iso() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    assert views.resolve_date("7d", now) == "2026-09-12T12:00:00"
    assert views.resolve_date("30d", now) == "2026-08-20T12:00:00"
    assert views.resolve_date("2026-01-01", now) == "2026-01-01T00:00:00"
    assert views.resolve_date("2026-01-01T05:00:00", now) == "2026-01-01T05:00:00"


def test_status_summary_before_and_after_ingest(lab: Workspace) -> None:
    assert views.status_summary(None) == {"repositories": [], "database_built": False}

    record_one_session(lab)
    connection = db.connect()
    try:
        summary = views.status_summary(connection)
    finally:
        connection.close()

    assert summary["built"] is True
    assert summary["repositories"] == [
        {
            "repo_key": lab.repo_key(),
            "name": "alpha",
            "level": "full",
            "files": summary["repositories"][0]["files"],
            "archived_bytes": summary["repositories"][0]["archived_bytes"],
            "sessions": 1,
            "edits": 1,
            "commits": 2,  # the fixture repository's root commit plus the recorded one
        }
    ]
    assert summary["commits"]["harvested"] >= 1
    assert summary["commits"]["by_method"].get("in_session") == 1
    assert summary["unknown_record_types"] == []


def _insert_bare_sessions(connection: sqlite3.Connection, count: int) -> None:
    """Synthetic `session` rows, enough to exercise the limit cap without a full ingest."""
    for i in range(count):
        connection.execute(
            "INSERT INTO session (session_id, repo_key, source, entrypoint, cwd, first_at,"
            " last_at, record_count, capture_level, parser_version, notes)"
            " VALUES (?, NULL, 'claude_code', 'cli', NULL, ?, ?, 0, 'full', 2, NULL)",
            (
                f"synthetic-{i:04d}",
                f"2026-01-{(i % 28) + 1:02d}T00:00:00",
                f"2026-01-{(i % 28) + 1:02d}T00:00:00",
            ),
        )
