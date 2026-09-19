"""Mapping a session to a repository when its working directory no longer exists."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db

NORMAL = "aaaaaaaa-1111-4111-8111-111111111111"
VANISHED = "bbbbbbbb-2222-4222-8222-222222222222"
STRANGER = "cccccccc-3333-4333-8333-333333333333"


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _build(lab: Workspace) -> str:
    """One session in the repository, one in a Desktop worktree that is already gone."""
    worktree = f"{lab.repo}/.claude/worktrees/gentle-hopper-ab12cd"
    write_transcript(
        lab.project,
        NORMAL,
        [
            prompt(NORMAL, str(lab.repo), "Start the parser."),
            *tool_call(
                NORMAL,
                str(lab.repo),
                "toolu_n1",
                "Write",
                {"file_path": f"{lab.repo}/src/app.py", "content": "alpha_value = 1\n"},
            ),
        ],
    )
    write_transcript(
        lab.project,
        VANISHED,
        [
            prompt(VANISHED, worktree, "Work in the worktree."),
            *tool_call(
                VANISHED,
                worktree,
                "toolu_v1",
                "Write",
                {"file_path": f"{worktree}/src/other.py", "content": "beta_value = 2\n"},
            ),
        ],
    )
    write_transcript(
        lab.project,
        STRANGER,
        [prompt(STRANGER, f"{lab.root}/elsewhere", "Somewhere else entirely.")],
    )
    return worktree


def test_a_session_in_a_vanished_worktree_is_mapped_by_its_path(lab: Workspace) -> None:
    worktree = _build(lab)
    assert not (lab.repo / ".claude" / "worktrees").exists(), "the worktree is gone, as in life"
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha"]).exit_code == 0
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output

    sessions = {row[0]: row for row in _rows("SELECT session_id, repo_key, notes FROM session")}
    assert set(sessions) == {NORMAL, VANISHED}, "the stranger belongs to no enabled repository"
    assert sessions[VANISHED][1] == sessions[NORMAL][1], "both are the same repository"
    assert "repository by worktree-pattern" in sessions[VANISHED][2]
    assert sessions[NORMAL][2] is None, "a directory that still exists needs no note"

    edits = {row[0]: row for row in _rows("SELECT tool_use_id, repo_key, rel_path FROM edit")}
    assert edits["toolu_v1"][1] == sessions[NORMAL][1]
    assert edits["toolu_v1"][2] == "src/other.py", "made relative to the worktree it was edited in"
    assert edits["toolu_n1"][2] == "src/app.py"

    worktrees = _rows("SELECT worktrees FROM repository")[0][0]
    assert worktree in worktrees, "the learned root is kept for the next run"


def test_the_fallback_is_visible_in_status(lab: Workspace) -> None:
    _build(lab)
    runner = CliRunner()
    runner.invoke(main, ["init", "--enable", "alpha"])
    runner.invoke(main, ["ingest"])
    status = runner.invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "1 by worktree-pattern" in status.output
    assert "sessions with no repository: 0" in status.output
