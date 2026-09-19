"""The precision sample: the hard quarter, drawn deterministically, and scored against a label."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, commit, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db, labels, sampling

WRITER = "11111111-1111-4111-8111-111111111111"
NEAR = "22222222-2222-4222-8222-222222222222"

APP = "alpha_value = compute_alpha(7)\nbeta_value = compute_beta(11)\n"
OTHER = "unrelated_value = compute_other(3)\n"


def _scenario(lab: Workspace) -> str:
    """One session writes the lines a hand commit ends up containing, twenty hours
    before it; another session touches something unrelated, one hour before it. The
    time window is fooled by recency; line matching is not, because it never saw
    NEAR's lines in the commit at all."""
    (lab.repo / "src").mkdir()
    write_transcript(
        lab.project,
        WRITER,
        [
            prompt(WRITER, str(lab.repo), "Write the app."),
            *tool_call(
                WRITER,
                str(lab.repo),
                "toolu_w1",
                "Write",
                {"file_path": f"{lab.repo}/src/app.py", "content": APP},
                at="2026-09-14T12:00:00.000Z",
            ),
        ],
    )
    write_transcript(
        lab.project,
        NEAR,
        [
            prompt(NEAR, str(lab.repo), "Touch something unrelated."),
            *tool_call(
                NEAR,
                str(lab.repo),
                "toolu_n1",
                "Write",
                {"file_path": f"{lab.repo}/src/other.py", "content": OTHER},
                at="2026-09-15T07:00:00.000Z",
            ),
        ],
    )
    (lab.repo / "src" / "app.py").write_text(APP)
    return commit(lab.repo, "2026-09-15T08:00:00+00:00", "add the app by hand")


def _ingest(lab: Workspace) -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def test_draw_sample_finds_the_hand_commit_as_hard_quarter(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    connection = db.connect()
    try:
        items = sampling.draw_sample(connection, n=50, seed=1)
        item = next(i for i in items if i.commit_hash == commit_hash)
        by_session = {c.session_id: c for c in item.candidates}
        assert set(by_session) == {WRITER, NEAR}
        assert by_session[WRITER].line_match_rank == 1
        assert by_session[NEAR].line_match_rank is None, "NEAR's lines never appear in the commit"
        assert item.pick_4h == NEAR, "only NEAR is active within 4 hours"
        assert item.pick_24h == NEAR, "NEAR is also the more recent of the two within 24 hours"
    finally:
        connection.close()


def test_draw_sample_is_deterministic_given_the_seed(lab: Workspace) -> None:
    _scenario(lab)
    _ingest(lab)
    connection = db.connect()
    try:
        first = [item.commit_hash for item in sampling.draw_sample(connection, n=50, seed=7)]
        second = [item.commit_hash for item in sampling.draw_sample(connection, n=50, seed=7)]
        assert first == second
    finally:
        connection.close()


def test_report_scores_line_match_right_and_the_4h_window_wrong(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    connection = db.connect()
    try:
        labels.write(connection, commit_hash, WRITER)
        scores = sampling.score(connection)
    finally:
        connection.close()

    assert scores["line_match"].labelled == 1
    assert scores["line_match"].answered == 1
    assert scores["line_match"].correct == 1
    assert scores["line_match"].precision == 1.0

    assert scores["window_4h"].answered == 1
    assert scores["window_4h"].correct == 0, "the 4h window can only see NEAR, and NEAR is wrong"
    assert scores["window_4h"].precision == 0.0

    assert scores["window_24h"].answered == 1
    assert scores["window_24h"].correct == 0, "NEAR is also the more recent session within 24h"


def test_sample_command_prints_and_exits_without_labelling_on_eof(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    result = CliRunner().invoke(main, ["sample", "--commits", "50", "--seed", "1"], input="")
    assert result.exit_code == 0, result.output
    assert commit_hash[:10] in result.output
    connection = db.connect()
    try:
        assert labels.labelled_hashes(connection) == set()
    finally:
        connection.close()


def test_sample_label_flag_writes_a_label_without_the_interactive_loop(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    result = CliRunner().invoke(main, ["sample", "--label", commit_hash, WRITER])
    assert result.exit_code == 0, result.output
    connection = db.connect()
    try:
        stored = labels.get(connection, commit_hash)
        assert stored is not None
        assert stored.session_id == WRITER
    finally:
        connection.close()

    none_result = CliRunner().invoke(main, ["sample", "--label", commit_hash, "none"])
    assert none_result.exit_code == 0, none_result.output
    connection = db.connect()
    try:
        stored = labels.get(connection, commit_hash)
        assert stored is not None
        assert stored.session_id is None
    finally:
        connection.close()


def test_sample_report_shows_a_table_and_the_labelled_count(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    CliRunner().invoke(main, ["sample", "--label", commit_hash, WRITER])
    result = CliRunner().invoke(main, ["sample", "--report"])
    assert result.exit_code == 0, result.output
    assert "line_match" in result.output
    assert "window_4h" in result.output
    assert "window_24h" in result.output
    assert "1 commits labelled so far." in result.output


def test_label_survives_rebuild(lab: Workspace) -> None:
    commit_hash = _scenario(lab)
    _ingest(lab)
    connection = db.connect()
    try:
        labels.write(connection, commit_hash, WRITER)
    finally:
        connection.close()

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output

    connection = db.connect()
    try:
        stored = labels.get(connection, commit_hash)
        assert stored is not None
        assert stored.session_id == WRITER, "rebuild must never touch a user-authored table"
    finally:
        connection.close()
