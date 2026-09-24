"""`mcp/server.py`: the tool functions, called directly against a fixture store.

There is no MCP client to drive here and there would be nothing to learn from driving
one: the protocol is FastMCP's and it is tested where it lives. What is ours is what each
tool returns, so each is called as the plain function `@mcp.tool()` leaves behind.

The two promises this file exists to hold: `latest_review` hands back the stored review
rather than a fresh computation of one, and `ask` returns evidence and never an answer,
because the caller of an MCP tool is already a model (M3 task 9, rule 7).
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.store import db

server = pytest.importorskip("prudence.mcp.server", reason="the mcp extra is not installed")


def _review() -> int:
    """One review written the way the user writes one, so the row is the engine's own."""
    result = CliRunner().invoke(main, ["review", "--last", "3650d", "--force"])
    assert result.exit_code == 0, result.output
    connection = db.connect()
    try:
        return connection.execute("SELECT MAX(id) FROM review").fetchone()[0]
    finally:
        connection.close()


def test_latest_review_returns_the_stored_row_and_its_page(lab: Workspace) -> None:
    record_one_session(lab)
    review_id = _review()

    payload = server.latest_review()
    assert payload["id"] == review_id
    assert payload["headline"].startswith(f"Review {review_id}")
    assert payload["range"]["start"] and payload["range"]["end"]
    assert payload["outcome_range"]["start"] and payload["outcome_range"]["end"]
    assert payload["sections"], "a review is its sections"
    assert isinstance(payload["numbers"], list)
    assert payload["segment"] is None, "no model was called, so there is no segment"
    assert payload["markdown"].startswith(f"# Review {review_id}")
    assert "Nothing above this line was written by a model" in payload["markdown"]

    # Every figure on the page is one the review already stored (rule 15).
    texts = {number["text"] for number in payload["numbers"]}
    assert texts, "the inventory is not empty"


def test_latest_review_says_so_when_there_is_none(lab: Workspace) -> None:
    record_one_session(lab)
    assert "No review has been written" in server.latest_review()["message"]
    assert "not-a-repository" in server.latest_review(project="not-a-repository")["message"]


def test_ask_returns_evidence_and_never_an_answer(lab: Workspace) -> None:
    record_one_session(lab)
    payload = server.ask("what did I do lately")

    assert payload["model"] is None
    assert "answer" not in payload, "an MCP caller is the model; the tool writes no prose"
    assert "calls no model" in payload["note"]
    assert SAMPLE_SESSION in [row["session_id"] for row in payload["sessions"]]
    assert SAMPLE_SESSION[:8] in payload["text"]
    assert "Question: what did I do lately" in payload["text"]


def test_ask_reports_an_unknown_project_rather_than_answering_nothing(lab: Workspace) -> None:
    record_one_session(lab)
    payload = server.ask("anything", project="not-a-repository")
    assert "not-a-repository" in payload["message"]


def test_ask_writes_nothing_to_the_store(lab: Workspace) -> None:
    """The CLI stores a `question` row; a read-only surface leaves the store alone."""
    record_one_session(lab)
    server.ask("what did I do lately")

    connection = db.connect()
    try:
        rows = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'question'"
        ).fetchone()[0]
        stored = connection.execute("SELECT COUNT(*) FROM question").fetchone()[0] if rows else 0
    finally:
        connection.close()
    assert stored == 0


def test_source_filter_and_readonly_connection(lab):
    import sqlite3

    record_one_session(lab)
    found = server.search_sessions(source="claude_code")
    assert found["total"] == 1
    assert found["results"][0]["source"] == "claude_code"
    assert server.search_sessions(source="codex")["total"] == 0
    assert server.search_sessions(source_id="claude")["total"] == 1
    assert server.search_sessions(source_id="missing")["total"] == 0
    connection = server._connect()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM session")
    finally:
        connection.close()
