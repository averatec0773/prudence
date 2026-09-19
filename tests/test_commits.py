"""Harvesting commits: what is counted, what is skipped, and what a merge looks like."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, commit, git, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db

SESSION = "dddddddd-4444-4444-8444-444444444444"
LOCK_LINES = "locked-alpha = 1\nlocked-beta = 2\nlocked-gamma = 3\n"
APP = "alpha_value = compute_alpha(7)\n"


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _history(lab: Workspace) -> dict[str, str]:
    """A real history: a normal commit, a generated file, a branch and a merge."""
    (lab.repo / "src").mkdir()
    (lab.repo / "src" / "app.py").write_text(APP)
    (lab.repo / "uv.lock").write_text(LOCK_LINES)
    first = commit(lab.repo, "2026-09-15T10:00:00+00:00", "add the app and the lock file")

    trunk = git(lab.repo, "rev-parse", "--abbrev-ref", "HEAD")
    git(lab.repo, "checkout", "-q", "-b", "side")
    (lab.repo / "src" / "side.py").write_text("side_value = compute_side(3)\n")
    side = commit(lab.repo, "2026-09-15T11:00:00+00:00", "add the side module")
    git(lab.repo, "checkout", "-q", trunk)
    git(
        lab.repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "merge",
        "--no-ff",
        "-q",
        "-m",
        "merge side",
        "side",
        at="2026-09-15T12:00:00+00:00",
    )
    merge = git(lab.repo, "rev-parse", "HEAD")
    return {"first": first, "side": side, "merge": merge}


def _ingest(lab: Workspace) -> None:
    write_transcript(
        lab.project,
        SESSION,
        [
            prompt(SESSION, str(lab.repo), "Write the app."),
            *tool_call(
                SESSION,
                str(lab.repo),
                "toolu_h1",
                "Write",
                {"file_path": f"{lab.repo}/src/app.py", "content": APP},
            ),
        ],
    )
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha"]).exit_code == 0
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def test_every_reachable_commit_is_harvested_including_the_branch(lab: Workspace) -> None:
    history = _history(lab)
    _ingest(lab)
    harvested = {
        row[0]: row for row in _rows('SELECT commit_hash, is_merge, added_lines FROM "commit"')
    }
    assert history["first"] in harvested
    assert history["side"] in harvested, "a commit only on a branch is still work"
    assert harvested[history["merge"]][1] == 1
    assert harvested[history["merge"]][2] == 0, "a merge adds no lines of its own"
    assert harvested[history["first"]][1] == 0


def test_generated_paths_are_excluded_from_the_lines(lab: Workspace) -> None:
    history = _history(lab)
    _ingest(lab)
    paths = {row[0] for row in _rows("SELECT DISTINCT path FROM commit_line")}
    assert "src/app.py" in paths
    assert "uv.lock" not in paths, "a lock file would drown every coverage figure"
    added = _rows(
        'SELECT added_lines, files_changed FROM "commit"'
        f" WHERE commit_hash = '{history['first']}'"
    )
    assert added[0] == (1, 1), "one real line in one real file"


def test_each_commit_carries_a_patch_id_and_a_tree(lab: Workspace) -> None:
    history = _history(lab)
    _ingest(lab)
    row = _rows(
        'SELECT patch_id, tree, committer_at, author_email_hash FROM "commit"'
        f" WHERE commit_hash = '{history['first']}'"
    )[0]
    assert row[0] and len(row[0]) == 40, "a rewritten commit can be recognised by its patch"
    assert row[1] and len(row[1]) == 40
    assert row[2] == "2026-09-15T10:00:00", "committer date in UTC, to the second"
    assert row[3] and len(row[3]) == 64, "the author's address is hashed, never stored"
