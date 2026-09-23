"""`prudence show`: the whole record of one session, and what it withholds."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main


def test_show_lists_every_fact_group_with_its_version(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION[:8]])
    assert result.exit_code == 0, result.output
    output = result.output

    assert f"session {SAMPLE_SESSION}" in output
    for group in (
        "identity",
        "counts",
        "token usage",
        "files edited",
        "commits attributed",
        "archive files",
    ):
        assert group in output, group
    assert "parser version 6" in output, "each group names the version that produced it"
    assert "trust high" in output and "trust medium" in output

    assert "capture level        full" in output
    assert "sittings             1" in output
    assert "tool calls by name: Bash 1, Write 1" in output
    assert "1 edits, 3 lines added, 0 lines removed" in output
    assert "by class: git_commit 1" in output
    assert "src/app.py" in output, "the edited file, relative to the repository"
    assert "in_session" in output, "the commit the session made, with its method"
    assert "transcript" in output, "the archive file the bytes came from"
    assert "No message text is recorded" in output


def test_show_withholds_paths_at_metadata_only(lab: Workspace) -> None:
    record_one_session(lab, level="metadata-only")
    result = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION])
    assert result.exit_code == 0, result.output
    assert "file paths withheld at metadata-only" in result.output
    assert "src/app.py" not in result.output
    assert "counts" in result.output, "the shape is still shown"
    assert "1 edits" in result.output


def test_an_ambiguous_prefix_is_an_error_not_a_guess(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["show", "--session", "nothing-like-this"]).exit_code != 0
    result = runner.invoke(main, ["show", "--session", "d"])
    assert result.exit_code == 0, "one session, so one letter is still unique"
    assert SAMPLE_SESSION in result.output
