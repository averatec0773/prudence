"""Attribution: which session a commit is credited to, by which method, at what coverage."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, commit, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db

WRITER = "eeeeeeee-5555-4555-8555-555555555555"
ECHO = "ffffffff-6666-4666-8666-666666666666"
COMMITTER = "aaaaaaaa-7777-4777-8777-777777777777"

APP = (
    "alpha_value = compute_alpha(7)\n"
    "beta_value = compute_beta(11)\n"
    "gamma_value = compute_gamma(13)\n"
    "delta_value = compute_delta(17)\n"
)
TOOL = "tool_value = compute_tool(23)\n"


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _scenario(lab: Workspace) -> dict[str, str]:
    """Two sessions write, a third commits, and the repository ends up with two commits."""
    (lab.repo / "src").mkdir()
    (lab.repo / "src" / "app.py").write_text(APP)
    first = commit(lab.repo, "2026-09-15T10:00:00+00:00", "add the app")
    (lab.repo / "src" / "tool.py").write_text(TOOL)
    second = commit(lab.repo, "2026-09-15T12:00:00+00:00", "add the tool")
    short = second[:7]

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
                at="2026-09-15T09:00:00.000Z",
            ),
        ],
    )
    write_transcript(
        lab.project,
        ECHO,
        [
            prompt(ECHO, str(lab.repo), "Touch one line of the app."),
            *tool_call(
                ECHO,
                str(lab.repo),
                "toolu_e1",
                "Edit",
                {
                    "file_path": f"{lab.repo}/src/app.py",
                    "old_string": "beta_value = 0\n",
                    "new_string": "beta_value = compute_beta(11)\n",
                },
                at="2026-09-15T09:30:00.000Z",
            ),
        ],
    )
    write_transcript(
        lab.project,
        COMMITTER,
        [
            prompt(COMMITTER, str(lab.repo), "Add the tool and commit it."),
            *tool_call(
                COMMITTER,
                str(lab.repo),
                "toolu_c1",
                "Write",
                {"file_path": f"{lab.repo}/src/tool.py", "content": TOOL},
                at="2026-09-15T11:50:00.000Z",
            ),
            *tool_call(
                COMMITTER,
                str(lab.repo),
                "toolu_c2",
                "Bash",
                {"command": "git commit -am 'add the tool'"},
                result={"stdout": f"[master {short}] add the tool\n 1 file changed", "stderr": ""},
                at="2026-09-15T12:00:01.000Z",
            ),
        ],
    )
    return {"app": first, "tool": second}


def _ingest(lab: Workspace, level: str = "full") -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", level])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def test_line_matching_ranks_the_session_that_wrote_the_lines_first(lab: Workspace) -> None:
    history = _scenario(lab)
    _ingest(lab)
    ranked = _rows(
        "SELECT rank, session_id, lines_matched, coverage FROM attribution"
        f" WHERE commit_hash = '{history['app']}' AND method = 'line_match' ORDER BY rank"
    )
    assert [row[1] for row in ranked] == [WRITER, ECHO], "both candidates are kept, in order"
    assert ranked[0][2] == 4, "the writer wrote all four lines"
    assert ranked[0][3] == 1.0, "and so explains the whole commit"
    assert ranked[1][2] == 1
    assert abs(ranked[1][3] - 0.25) < 1e-9, "coverage says how little the second explains"


def test_an_in_session_commit_is_attributed_by_its_own_method(lab: Workspace) -> None:
    history = _scenario(lab)
    _ingest(lab)
    rows = _rows(
        "SELECT method, session_id, rank FROM attribution"
        f" WHERE commit_hash = '{history['tool']}' ORDER BY method"
    )
    methods = {row[0]: row[1] for row in rows}
    assert methods["in_session"] == COMMITTER, "git printed the hash inside that session"
    assert methods["line_match"] == COMMITTER, "and the lines agree, which is the happy case"
    assert all(row[2] == 1 for row in rows)


def test_a_commit_nobody_wrote_gets_no_attribution(lab: Workspace) -> None:
    _scenario(lab)
    (lab.repo / "src" / "hand.py").write_text("hand_value = compute_hand(31)\n")
    by_hand = commit(lab.repo, "2026-09-15T13:00:00+00:00", "written by hand")
    _ingest(lab)
    assert _rows(f"SELECT COUNT(*) FROM attribution WHERE commit_hash = '{by_hand}'") == [(0,)]


def test_an_edit_made_after_the_commit_is_not_credited_for_it(lab: Workspace) -> None:
    """The tolerance is two minutes, not two hours: later work cannot explain earlier work."""
    history = _scenario(lab)
    late = "gggggggg-8888-4888-8888-888888888888"
    write_transcript(
        lab.project,
        late,
        [
            prompt(late, str(lab.repo), "Rewrite the app much later."),
            *tool_call(
                late,
                str(lab.repo),
                "toolu_l1",
                "Write",
                {"file_path": f"{lab.repo}/src/app.py", "content": APP},
                at="2026-09-15T18:00:00.000Z",
            ),
        ],
    )
    _ingest(lab)
    credited = {
        row[0]
        for row in _rows(
            f"SELECT session_id FROM attribution WHERE commit_hash = '{history['app']}'"
        )
    }
    assert late not in credited


def test_rebuild_reproduces_the_attribution_rows(lab: Workspace) -> None:
    _scenario(lab)
    _ingest(lab)
    before = sorted(_rows("SELECT * FROM attribution"))
    assert before, "there is something to reproduce"
    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    assert sorted(_rows("SELECT * FROM attribution")) == before


def test_metadata_only_keeps_no_paths_no_lines_and_no_command_text(lab: Workspace) -> None:
    _scenario(lab)
    _ingest(lab, level="metadata-only")
    assert _rows("SELECT COUNT(*) FROM edit WHERE file_path IS NOT NULL") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM edit WHERE rel_path IS NOT NULL") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM edit_line") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM command WHERE command_text IS NOT NULL") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM edit")[0][0] == 3, "the shape is still recorded"
    classes = dict(_rows("SELECT command_class, COUNT(*) FROM command GROUP BY command_class"))
    assert classes == {"git_commit": 1}
    assert _rows("SELECT COUNT(*) FROM commit_line") == [(0,)], "nor the repository's own lines"
    assert _rows('SELECT COUNT(*) FROM "commit"')[0][0] == 3, "the commits are still counted"
    assert _rows("SELECT COUNT(*) FROM attribution WHERE method = 'line_match'") == [(0,)]
    in_session = _rows("SELECT session_id FROM attribution WHERE method = 'in_session'")
    assert in_session == [(COMMITTER,)], "the commit hash is a fact about the repository"


def test_sessions_lists_what_each_session_did(lab: Workspace) -> None:
    _scenario(lab)
    _ingest(lab)
    result = CliRunner().invoke(main, ["sessions", "--last", "90d"])
    assert result.exit_code == 0, result.output
    assert WRITER[:8] in result.output
    assert "alpha" in result.output
    body = [line for line in result.output.splitlines() if line.startswith(WRITER[:8])][0]
    assert "100%" in body, "the writer explains its commit entirely"

    scoped = CliRunner().invoke(main, ["sessions", "--last", "90d", "--project", "alpha"])
    assert scoped.exit_code == 0, scoped.output
    assert COMMITTER[:8] in scoped.output
    empty = CliRunner().invoke(main, ["sessions", "--last", "1h"])
    assert "No session in the last 1h" in empty.output
