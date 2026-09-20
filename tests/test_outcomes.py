"""What became of the lines: presence, blame, rework, and the two guards.

The rule under test lives in `store/outcomes.py`. Every scenario here is built out of
real commits in a real repository, because the whole point of the table is that it
answers with git rather than with a model of git.
"""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, commit, git, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db

WRITER = "eeeeeeee-2222-4222-8222-222222222222"

# Seven distinctive lines, so the coverage floor and the overlap guard both have room.
SEVEN = "".join(f"value_{index} = compute_{index}({index})\n" for index in range(1, 8))
REPLACEMENT = "".join(f"other_{index} = elsewhere_{index}({index})\n" for index in range(1, 8))


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _ingest(level: str = "full") -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", level])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def _session(
    lab: Workspace,
    path: str,
    content: str,
    printed: str,
    wrote_at: str = "2026-09-01T11:50:00.000Z",
    called_at: str = "2026-09-01T12:00:00.000Z",
    session_id: str = WRITER,
    quiet: bool = False,
) -> None:
    """A session that writes one file and commits it, printing the hash or nothing."""
    records = [prompt(session_id, str(lab.repo), "Write it and commit.", at=wrote_at)]
    records += tool_call(
        session_id,
        str(lab.repo),
        f"toolu_{session_id[:4]}_w",
        "Write",
        {"file_path": f"{lab.repo}/{path}", "content": content},
        at=wrote_at,
    )
    stdout = "" if quiet else f"[master {printed[:7]}] the work\n 1 file changed"
    records += tool_call(
        session_id,
        str(lab.repo),
        f"toolu_{session_id[:4]}_c",
        "Bash",
        {"command": "git commit -q -am 'the work'" if quiet else "git commit -am 'the work'"},
        result={"stdout": stdout, "stderr": "", "exitCode": 0},
        at=called_at,
    )
    write_transcript(lab.project, session_id, records)


def _write(lab: Workspace, path: str, content: str) -> None:
    target = lab.repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def test_a_line_the_same_author_removes_later_is_reworked_and_dead_at_head(
    lab: Workspace,
) -> None:
    """The central case: the session's own lines, taken back out by the session's author."""
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    _write(lab, "src/app.py", REPLACEMENT)
    undone = commit(lab.repo, "2026-09-05T09:00:00+00:00", "rewrite it")
    _session(lab, "src/app.py", SEVEN, made)
    _ingest()

    fate = _rows(
        "SELECT alive_7d, alive_head, alive_head_anywhere, blame_head, reworked_by"
        f" FROM line_fate WHERE commit_hash = '{made}'"
    )
    assert len(fate) == 7, "seven distinct added lines were followed"
    assert {row[:4] for row in fate} == {(0, 0, 0, 0)}, "gone at every mark and in blame"
    assert {row[4] for row in fate} == {undone}, "the later commit of the same author"


def test_a_line_moved_to_another_file_is_alive_anywhere_but_not_at_its_own_path(
    lab: Workspace,
) -> None:
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    (lab.repo / "src" / "app.py").unlink()
    _write(lab, "src/moved.py", SEVEN)
    commit(lab.repo, "2026-09-05T09:00:00+00:00", "move it")
    _session(lab, "src/app.py", SEVEN, made)
    _ingest()

    fate = _rows(
        "SELECT DISTINCT alive_head, alive_head_anywhere FROM line_fate"
        f" WHERE commit_hash = '{made}' AND path = 'src/app.py'"
    )
    assert fate == [(0, 1)], "not at its own path any more, but still somewhere at head"


def test_an_uncertain_attribution_contributes_no_line_at_all(lab: Workspace) -> None:
    """A commit nobody is credited with above the floor has no fate row (principle 3)."""
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    # The session wrote one of the seven lines and printed a hash that resolves to
    # nothing, so line matching keeps it as a candidate and calls it uncertain.
    _session(lab, "src/app.py", "value_1 = compute_1(1)\n", "abc1234")
    _ingest()

    assert _rows(f"SELECT DISTINCT confidence FROM attribution WHERE commit_hash = '{made}'") == [
        ("uncertain",)
    ]
    assert _rows(f"SELECT COUNT(*) FROM line_fate WHERE commit_hash = '{made}'") == [(0,)]

    outcomes = CliRunner().invoke(main, ["outcomes", "--last", "90d"])
    assert outcomes.exit_code == 0, outcomes.output
    assert "credited with a line that could be followed" in outcomes.output


def test_the_multi_author_guard_suppresses_a_repository_and_says_why(lab: Workspace) -> None:
    """More than a fifth of the window's commits by somebody else, so no outcome facts."""
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    for index in range(3):
        _write(lab, f"src/other{index}.py", f"colleague_{index} = other_{index}({index})\n")
        git(lab.repo, "add", "-A")
        git(
            lab.repo,
            "-c",
            "user.email=colleague@example.com",
            "-c",
            "user.name=colleague",
            "commit",
            "-q",
            "-m",
            "theirs",
            at="2026-09-02T09:00:00+00:00",
        )
    _session(lab, "src/app.py", SEVEN, made)
    _ingest()

    assert _rows("SELECT outcomes_suppressed FROM repository") == [(1,)]
    assert _rows("SELECT COUNT(*) FROM line_fate") == [(0,)]

    status = CliRunner().invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "outcomes suppressed for alpha" in status.output
    assert "by another author" in status.output


def test_a_silent_commit_is_matched_by_timing_and_overlap(lab: Workspace) -> None:
    """The follow-up from task 2: `git commit -q` prints no hash, and still counts."""
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    _session(lab, "src/app.py", SEVEN, made, quiet=True)
    _ingest()

    assert _rows(
        "SELECT session_id, method_note, confidence FROM attribution"
        f" WHERE commit_hash = '{made}' AND method = 'in_session'"
    ) == [(WRITER, "silent", "fact")]
    assert _rows("SELECT COUNT(*) FROM commit_alias") == [(0,)], "no hash was printed to alias"

    status = CliRunner().invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "silent commits matched: 1" in status.output
    assert "commit hashes printed in a session: 0" in status.output


def test_a_silent_call_claims_the_commit_nearest_in_time(lab: Workspace) -> None:
    """Two calls could claim one commit; the nearer one wins, and claims only one."""
    _write(lab, "src/app.py", SEVEN)
    first = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    _write(lab, "src/app.py", SEVEN + REPLACEMENT)
    second = commit(lab.repo, "2026-09-01T12:04:00+00:00", "more of it")

    records = [prompt(WRITER, str(lab.repo), "Write it and commit twice.")]
    records += tool_call(
        WRITER,
        str(lab.repo),
        "toolu_w",
        "Write",
        {"file_path": f"{lab.repo}/src/app.py", "content": SEVEN + REPLACEMENT},
        at="2026-09-01T11:50:00.000Z",
    )
    for index, at in enumerate(("2026-09-01T12:00:00.000Z", "2026-09-01T12:03:30.000Z")):
        records += tool_call(
            WRITER,
            str(lab.repo),
            f"toolu_c{index}",
            "Bash",
            {"command": "git commit -q -am 'the work'"},
            result={"stdout": "", "stderr": "", "exitCode": 0},
            at=at,
        )
    write_transcript(lab.project, WRITER, records)
    _ingest()

    matched = _rows(
        "SELECT commit_hash FROM attribution WHERE method = 'in_session'"
        " AND method_note = 'silent' ORDER BY commit_hash"
    )
    assert sorted(row[0] for row in matched) == sorted([first, second]), (
        "one commit per call, each to the call nearest it in time"
    )


def test_the_fates_survive_a_rebuild_unchanged(lab: Workspace) -> None:
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    _session(lab, "src/app.py", SEVEN, made)
    _ingest()
    before = sorted(_rows("SELECT * FROM line_fate"))
    assert before, "there is a fate to reproduce"

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    assert sorted(_rows("SELECT * FROM line_fate")) == before


def test_outcomes_prints_the_denominators_the_totals_and_the_definitions(
    lab: Workspace,
) -> None:
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, "2026-09-01T12:00:02+00:00", "the work")
    _session(lab, "src/app.py", SEVEN, made)
    _ingest()

    result = CliRunner().invoke(main, ["outcomes", "--project", "alpha", "--last", "90d"])
    assert result.exit_code == 0, result.output
    assert "alive 7d" in result.output
    assert "(7)" in result.output, "the share is printed with the lines it is over"
    assert "per repository" in result.output
    assert "a mark still in the future is a dash" in result.output.replace("\n", " ")

    listed = CliRunner().invoke(main, ["sessions", "--last", "90d"])
    assert listed.exit_code == 0, listed.output
    assert "alive 30d" in listed.output

    shown = CliRunner().invoke(main, ["show", "--session", WRITER[:8]])
    assert shown.exit_code == 0, shown.output
    assert "what became of the lines" in shown.output
    assert "attributed lines" in shown.output
    assert "alive at head            100% of 7" in shown.output
