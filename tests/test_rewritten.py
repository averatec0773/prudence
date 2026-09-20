"""Rewritten commits: the printed hash is gone, the work is not.

The rule under test lives in `store/rewritten.py`: a reachable commit nobody holds
`in_session`, dated inside the five minutes after a `git commit` call whose printed
hash no longer resolves, whose added lines overlap the lines that session wrote, is
that session's commit.
"""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace, commit, git, prompt, tool_call, write_transcript

from prudence.cli import main
from prudence.store import db

REWRITER = "cccccccc-1111-4111-8111-111111111111"

# Seven lines, so the five-line overlap guard has room on both sides of the line.
BIG = "".join(f"value_{index} = compute_{index}({index})\n" for index in range(1, 8))
ONE_LINE = "value_1 = compute_1(1)\n"
HALF = "".join(f"value_{index} = compute_{index}({index})\n" for index in range(1, 6))


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _ingest(lab: Workspace, level: str = "full") -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", level])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def _session(
    lab: Workspace,
    wrote: str,
    calls: list[tuple[str, str]],
    wrote_at: str = "2026-09-15T11:50:00.000Z",
    session_id: str = REWRITER,
) -> None:
    """One session that writes `wrote` into the file and then runs `git commit`.

    Each entry of `calls` is a short hash git printed and the moment of the call. The
    hashes are deliberately ones that resolve to nothing, which is what a rebase or a
    squash merge leaves behind.
    """
    records = [prompt(session_id, str(lab.repo), "Write it and commit.", at=wrote_at)]
    records += tool_call(
        session_id,
        str(lab.repo),
        f"toolu_{session_id[:4]}_w",
        "Write",
        {"file_path": f"{lab.repo}/src/app.py", "content": wrote},
        at=wrote_at,
    )
    for index, (printed, at) in enumerate(calls):
        records += tool_call(
            session_id,
            str(lab.repo),
            f"toolu_{session_id[:4]}_c{index}",
            "Bash",
            {"command": "git commit -am 'the work'"},
            result={"stdout": f"[master {printed}] the work\n 1 file changed", "stderr": ""},
            at=at,
        )
    write_transcript(lab.project, session_id, records)


def _commit_big(lab: Workspace, at: str = "2026-09-15T12:00:02+00:00") -> str:
    (lab.repo / "src").mkdir(exist_ok=True)
    (lab.repo / "src" / "app.py").write_text(BIG)
    return commit(lab.repo, at, "the work")


def test_a_rewritten_commit_is_re_identified_and_its_dead_hash_kept(lab: Workspace) -> None:
    made = _commit_big(lab)
    _session(lab, BIG, [("abc1234", "2026-09-15T12:00:00.000Z")])
    _ingest(lab)

    attributed = _rows(
        "SELECT session_id, method_note, confidence, lines_matched FROM attribution"
        f" WHERE commit_hash = '{made}' AND method = 'in_session'"
    )
    assert attributed == [(REWRITER, "rewritten", "fact", 7)]
    assert _rows("SELECT printed_hash, commit_hash, session_id FROM commit_alias") == [
        ("abc1234", made, REWRITER)
    ]

    status = CliRunner().invoke(main, ["status"])
    assert status.exit_code == 0, status.output
    assert "1 were re-identified after a rewrite" in status.output
    assert "commit hashes printed in a session: 1" in status.output


def test_the_re_identification_survives_a_rebuild(lab: Workspace) -> None:
    _commit_big(lab)
    _session(lab, BIG, [("abc1234", "2026-09-15T12:00:00.000Z")])
    _ingest(lab)
    before = sorted(_rows("SELECT * FROM commit_alias")), sorted(_rows("SELECT * FROM attribution"))
    assert before[0], "there is an alias to reproduce"

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    after = sorted(_rows("SELECT * FROM commit_alias")), sorted(_rows("SELECT * FROM attribution"))
    assert after == before


def test_one_matching_line_out_of_seven_is_not_enough(lab: Workspace) -> None:
    """The guard against coincidence: timing alone never re-identifies anything."""
    made = _commit_big(lab)
    _session(lab, ONE_LINE, [("abc1234", "2026-09-15T12:00:00.000Z")])
    _ingest(lab)

    assert _rows("SELECT COUNT(*) FROM commit_alias") == [(0,)]
    assert _rows(
        f"SELECT COUNT(*) FROM attribution WHERE commit_hash = '{made}' AND method = 'in_session'"
    ) == [(0,)]
    assert _rows(f"SELECT confidence FROM attribution WHERE commit_hash = '{made}'") == [
        ("uncertain",)
    ], "the line match keeps it as a candidate, and says it is unsure"


def test_a_commit_outside_the_window_is_left_alone(lab: Workspace) -> None:
    made = _commit_big(lab, at="2026-09-15T12:30:00+00:00")
    _session(lab, BIG, [("abc1234", "2026-09-15T12:00:00.000Z")])
    _ingest(lab)

    assert _rows("SELECT COUNT(*) FROM commit_alias") == [(0,)]
    assert _rows(
        f"SELECT COUNT(*) FROM attribution WHERE commit_hash = '{made}' AND method = 'in_session'"
    ) == [(0,)]
    status = CliRunner().invoke(main, ["status"])
    assert "0 were re-identified after a rewrite, 1 are gone" in status.output


def test_an_amend_leaves_the_last_printed_hash_as_the_surviving_one(lab: Workspace) -> None:
    made = _commit_big(lab, at="2026-09-15T12:01:05+00:00")
    _session(
        lab,
        BIG,
        [("abc1234", "2026-09-15T12:00:00.000Z"), ("def5678", "2026-09-15T12:01:00.000Z")],
    )
    _ingest(lab)

    assert _rows("SELECT printed_hash, commit_hash FROM commit_alias") == [("def5678", made)]
    printed = _rows("SELECT COUNT(DISTINCT commit_hash) FROM command WHERE commit_hash IS NOT NULL")
    assert printed == [(2,)], "both hashes were printed; only one commit survived"


def test_a_resolvable_hash_is_still_read_straight_off_the_transcript(lab: Workspace) -> None:
    """Nothing here changes the ordinary case: a hash that resolves needs no inference."""
    made = _commit_big(lab)
    _session(lab, BIG, [(made[:7], "2026-09-15T12:00:00.000Z")])
    _ingest(lab)

    assert _rows("SELECT COUNT(*) FROM commit_alias") == [(0,)]
    assert _rows(
        f"SELECT method_note FROM attribution WHERE commit_hash = '{made}'"
        " AND method = 'in_session'"
    ) == [(None,)]
    status = CliRunner().invoke(main, ["status"])
    assert "1 still resolve" in status.output


def test_one_dead_hash_claims_only_one_commit(lab: Workspace) -> None:
    """It named exactly one commit when it was printed, so the best overlap keeps it."""
    (lab.repo / "src").mkdir()
    (lab.repo / "src" / "app.py").write_text(BIG)
    (lab.repo / "src" / "copy.py").write_text(HALF)
    git(lab.repo, "add", "src/app.py")
    git(
        lab.repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "the work",
        at="2026-09-15T12:00:02+00:00",
    )
    seven = git(lab.repo, "rev-parse", "HEAD")
    five = commit(lab.repo, "2026-09-15T12:00:05+00:00", "the copy")

    records = [prompt(REWRITER, str(lab.repo), "Write both and commit.")]
    for name, content in (("app.py", BIG), ("copy.py", HALF)):
        records += tool_call(
            REWRITER,
            str(lab.repo),
            f"toolu_w_{name}",
            "Write",
            {"file_path": f"{lab.repo}/src/{name}", "content": content},
            at="2026-09-15T11:50:00.000Z",
        )
    records += tool_call(
        REWRITER,
        str(lab.repo),
        "toolu_c0",
        "Bash",
        {"command": "git commit -am 'the work'"},
        result={"stdout": "[master abc1234] the work", "stderr": ""},
        at="2026-09-15T12:00:00.000Z",
    )
    write_transcript(lab.project, REWRITER, records)
    _ingest(lab)

    assert _rows("SELECT printed_hash, commit_hash FROM commit_alias") == [("abc1234", seven)]
    assert _rows(
        f"SELECT COUNT(*) FROM attribution WHERE commit_hash = '{five}' AND method = 'in_session'"
    ) == [(0,)], "the second commit keeps only what the lines say"


def test_metadata_only_re_identifies_nothing(lab: Workspace) -> None:
    """No line hashes means no overlap to measure, so the rule never fires."""
    _commit_big(lab)
    _session(lab, BIG, [("abc1234", "2026-09-15T12:00:00.000Z")])
    _ingest(lab, level="metadata-only")
    assert _rows("SELECT COUNT(*) FROM commit_alias") == [(0,)]
