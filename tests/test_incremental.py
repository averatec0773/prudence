"""The guard on everything incremental: an ingest leaves the store a rebuild would.

`prudence ingest` keeps what did not change (the rows of every session whose inputs did
not move, the commits already harvested, and the outcome marks already measured) and
`prudence rebuild` throws every derived table away. The two must agree. Each scenario
here runs a sequence of ingests over a changing machine, dumps every table the pipeline
writes, rebuilds from the same archive, and compares the two dumps table by table and
row by row, order-independent.

A table is compared unless it is named in `NOT_DERIVED`, with the reason, so a table a
later step adds is covered the day it appears.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner
from conftest import Workspace, commit, git, prompt, tool_call, write_transcript
from test_forks import (
    FIRST_SITTING,
    FORK,
    PARENT,
    SECOND_SITTING,
    _answer,
    _copied_history,
    _first_sitting,
    _fork_only,
    _parent_only,
    _prompt,
    _re_stamped,
    _second_sitting_only,
)
from test_outcomes import REPLACEMENT, SEVEN, _session, _write

from prudence.cli import main
from prudence.store import db

# Tables the pipeline does not rebuild, and why they are left out of the comparison.
NOT_DERIVED = {
    "archive_file": "the archive itself; `last_seen` moves on every ingest by design",
    "archive_chunk": "the archive itself",
    "meta": "facts about the store, including when the last run happened",
    "review": "the user's own history of reviews, never rebuilt",
    "suggestion": "the user's own history of suggestions, never rebuilt",
    "label": "typed by the founder, never rebuilt",
    "question": "the user's own questions, never rebuilt",
}
# Bookkeeping that says what was parsed and measured, not what the archive means.
BOOKKEEPING_PREFIXES = ("parse_", "outcome_mark")

SESSION_ONE = "11111111-1111-4111-8111-111111111111"
SESSION_TWO = "22222222-2222-4222-8222-222222222222"
NEW_SESSION = "66666666-6666-4666-8666-666666666666"


def _enable() -> None:
    result = CliRunner().invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    assert result.exit_code == 0, result.output


def _ingest() -> dict:
    result = CliRunner().invoke(main, ["ingest", "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _ingest_incrementally() -> dict:
    """An ingest that must have kept some rows rather than parsing everything again."""
    parsed = _ingest()["parsed"]
    assert parsed["mode"] == "incremental", parsed["full_reason"]
    return parsed


def _rebuild() -> None:
    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output


def _compared_tables(connection: sqlite3.Connection) -> list[str]:
    names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    return [
        name
        for name in names
        if name not in NOT_DERIVED and not name.startswith(BOOKKEEPING_PREFIXES)
    ]


def dump_store() -> dict[str, list[tuple]]:
    """Every table the pipeline writes, each as a sorted list of rows."""
    connection = db.connect()
    try:
        return {
            table: sorted(
                (tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')),
                key=repr,
            )
            for table in _compared_tables(connection)
        }
    finally:
        connection.close()


def assert_equal_to_a_rebuild() -> None:
    """The store as the ingests left it, against a rebuild of the same archive."""
    after_ingests = dump_store()
    assert after_ingests["session"], "there is something to compare"
    _rebuild()
    rebuilt = dump_store()
    assert sorted(after_ingests) == sorted(rebuilt), "the same tables exist"
    for table in rebuilt:
        assert after_ingests[table] == rebuilt[table], f"{table} differs from a rebuild"


def _append(path, records: list[dict]) -> None:
    with path.open("a") as handle:
        handle.write("".join(json.dumps(record) + "\n" for record in records))


def _new_session_records(cwd: str) -> list[dict]:
    return [
        prompt(NEW_SESSION, cwd, "Add a helper.", at="2026-09-18T10:00:00.000Z"),
        *tool_call(
            NEW_SESSION,
            cwd,
            "toolu_n1",
            "Write",
            {"file_path": f"{cwd}/src/helper.py", "content": "def helper():\n    return 2\n"},
            at="2026-09-18T10:01:00.000Z",
        ),
        *tool_call(
            NEW_SESSION,
            cwd,
            "toolu_n2",
            "Bash",
            {"command": "pytest -q"},
            result={"stdout": "1 passed", "stderr": ""},
            at="2026-09-18T10:02:00.000Z",
        ),
    ]


def test_a_new_session_between_two_ingests(workspace: Workspace) -> None:
    _enable()
    _ingest()
    write_transcript(workspace.project, NEW_SESSION, _new_session_records(str(workspace.repo)))
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_only_the_transcript_that_grew_is_read_again(lab: Workspace) -> None:
    """Two unrelated sessions; one grows; the other's rows are kept as they were."""
    cwd = str(lab.repo)
    write_transcript(lab.project, NEW_SESSION, _new_session_records(cwd))
    write_transcript(lab.project, PARENT, _copied_history(cwd))
    _enable()
    first = _ingest()["parsed"]
    assert (first["mode"], first["files_parsed"]) == ("full", 2)
    _append(
        lab.project / f"{NEW_SESSION}.jsonl",
        tool_call(
            NEW_SESSION,
            cwd,
            "toolu_grow",
            "Bash",
            {"command": "ls"},
            result={"stdout": "src", "stderr": ""},
            at="2026-09-18T11:01:00.000Z",
        ),
    )
    second = _ingest()["parsed"]
    assert second["mode"] == "incremental", second["full_reason"]
    assert (second["sessions_parsed"], second["files_parsed"], second["files_skipped"]) == (
        1,
        1,
        1,
    )
    assert_equal_to_a_rebuild()


def test_a_transcript_that_grew_is_read_again_with_its_resume(workspace: Workspace) -> None:
    """The fixture's `44444444` resumes `11111111` and lost its copied records to it, so
    when `11111111` grows the resume is read again too (`parse_state`, winner to loser).
    """
    _enable()
    _ingest()
    cwd = str(workspace.repo)
    _append(
        workspace.project / f"{SESSION_ONE}.jsonl",
        [
            prompt(SESSION_ONE, cwd, "One more thing.", at="2026-09-10T11:00:00.000Z"),
            *tool_call(
                SESSION_ONE,
                cwd,
                "toolu_grow",
                "Bash",
                {"command": "git status"},
                result={"stdout": "clean", "stderr": ""},
                at="2026-09-10T11:01:00.000Z",
            ),
        ],
    )
    second = _ingest()["parsed"]
    assert second["mode"] == "incremental", second["full_reason"]
    assert (second["sessions_parsed"], second["files_parsed"]) == (2, 2)
    assert_equal_to_a_rebuild()


def test_a_subagent_log_that_arrived_after_its_session_was_parsed(workspace: Workspace) -> None:
    _enable()
    _ingest()
    cwd = str(workspace.repo)
    agent = "77777777-7777-4777-8777-777777777777"
    log = workspace.project / SESSION_TWO / "subagents" / f"agent-{agent}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    records = tool_call(
        SESSION_TWO,
        cwd,
        "toolu_late_agent",
        "Read",
        {"file_path": f"{cwd}/README.md"},
        at="2026-09-12T14:30:00.000Z",
    )
    write_transcript(log.parent, f"agent-{agent}", [{**r, "isSidechain": True} for r in records])
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_fork_that_arrived_after_its_parent(lab: Workspace) -> None:
    cwd = str(lab.repo)
    write_transcript(lab.project, PARENT, _copied_history(cwd) + _parent_only(cwd))
    _enable()
    _ingest()
    write_transcript(lab.project, FORK, _copied_history(cwd) + _fork_only(cwd))
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_parent_that_arrived_after_its_fork_had_carried_it(lab: Workspace) -> None:
    """The parent was an orphan built from the fork's copy; then its own file appears."""
    cwd = str(lab.repo)
    write_transcript(lab.project, FORK, _copied_history(cwd) + _fork_only(cwd))
    _enable()
    _ingest()
    write_transcript(lab.project, PARENT, _copied_history(cwd) + _parent_only(cwd))
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_parent_that_grew_after_its_fork_was_taken(lab: Workspace) -> None:
    cwd = str(lab.repo)
    write_transcript(lab.project, PARENT, _copied_history(cwd))
    write_transcript(lab.project, FORK, _copied_history(cwd) + _fork_only(cwd))
    _enable()
    _ingest()
    _append(lab.project / f"{PARENT}.jsonl", _parent_only(cwd))
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_second_fork_of_a_deleted_parent_that_arrived_later(lab: Workspace) -> None:
    """The parent exists only as the copies its forks carry; a new copy changes it."""
    cwd = str(lab.repo)
    write_transcript(lab.project, FORK, _copied_history(cwd) + _fork_only(cwd))
    _enable()
    _ingest()
    later = "eeeeeeee-5555-4555-8555-eeeeeeeeeeee"
    write_transcript(
        lab.project,
        later,
        _copied_history(cwd)
        + [_prompt(later, "g1", "2026-09-15T12:00:00.000Z", cwd, "turn-g1", "Once more.")],
    )
    parsed = _ingest_incrementally()
    assert parsed["sessions_parsed"] == 2, "the new fork, and the fork already carrying it"
    assert_equal_to_a_rebuild()


def test_two_sessions_that_write_the_same_turn_id_are_read_together(lab: Workspace) -> None:
    """A turn id both sessions carry is one row, and the later session's write wins; so
    when the earlier one is read again, the later one has to be read again after it."""
    cwd = str(lab.repo)
    other = "ffffffff-6666-4666-8666-ffffffffffff"
    write_transcript(
        lab.project,
        FIRST_SITTING,
        [_prompt(FIRST_SITTING, "k1", "2026-09-16T09:00:00.000Z", cwd, "same-turn", "One.")],
    )
    write_transcript(
        lab.project,
        other,
        [_prompt(other, "k2", "2026-09-16T10:00:00.000Z", cwd, "same-turn", "Two words.")],
    )
    _enable()
    _ingest()
    _append(
        lab.project / f"{FIRST_SITTING}.jsonl",
        [_answer(FIRST_SITTING, "k3", "2026-09-16T09:01:00.000Z", cwd, "same-turn", "req_k3")],
    )
    parsed = _ingest_incrementally()
    assert parsed["sessions_parsed"] == 2
    assert_equal_to_a_rebuild()


def test_an_earlier_sitting_that_arrived_after_its_re_stamped_copy(lab: Workspace) -> None:
    """The new file sorts first, so it takes records the later session owned until now."""
    cwd = str(lab.repo)
    write_transcript(lab.project, SECOND_SITTING, _re_stamped(cwd) + _second_sitting_only(cwd))
    _enable()
    _ingest()
    write_transcript(lab.project, FIRST_SITTING, _first_sitting(cwd))
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_first_sitting_that_grew_after_it_was_resumed(lab: Workspace) -> None:
    """The copy's owner grows; the copy keeps losing what it copied, and nothing else."""
    cwd = str(lab.repo)
    write_transcript(lab.project, FIRST_SITTING, _first_sitting(cwd)[:2])
    write_transcript(lab.project, SECOND_SITTING, _re_stamped(cwd) + _second_sitting_only(cwd))
    _enable()
    _ingest()
    _append(lab.project / f"{FIRST_SITTING}.jsonl", _first_sitting(cwd)[2:])
    _ingest_incrementally()
    assert_equal_to_a_rebuild()


def test_a_capture_level_changed_between_two_ingests(workspace: Workspace) -> None:
    _enable()
    _ingest()
    result = CliRunner().invoke(main, ["init", "--enable", "alpha", "--level", "metadata-only"])
    assert result.exit_code == 0, result.output
    parsed = _ingest_incrementally()
    assert parsed["sessions_parsed"] == 3, "every session of the repository is read again"
    assert_equal_to_a_rebuild()


def test_a_worktree_learned_later_moves_an_earlier_sessions_edit(lab: Workspace) -> None:
    """An edit is made relative to the longest root above it, and roots are learned.

    The first session edits a file inside a Desktop worktree while working from the
    repository itself; the worktree becomes a known root only when a later session runs
    in it, and from then on the edit's path is relative to the worktree. An incremental
    parse must read the first session again, because a rebuild would write it that way.
    """
    cwd = str(lab.repo)
    tree = f"{cwd}/.claude/worktrees/brave-hopper-1a2b3c"
    write_transcript(
        lab.project,
        PARENT,
        [
            prompt(PARENT, cwd, "Edit the worktree copy.", at="2026-09-18T09:00:00.000Z"),
            *tool_call(
                PARENT,
                cwd,
                "toolu_tree",
                "Write",
                {"file_path": f"{tree}/src/tree.py", "content": "value = 1\n"},
                at="2026-09-18T09:01:00.000Z",
            ),
        ],
    )
    _enable()
    _ingest()
    before = ".claude/worktrees/brave-hopper-1a2b3c/src/tree.py"
    assert _edit_paths() == [("toolu_tree", before)]
    write_transcript(
        lab.project,
        FORK,
        [prompt(FORK, tree, "Work in the tree.", at="2026-09-18T10:00:00.000Z")],
    )
    _ingest_incrementally()
    assert _edit_paths() == [("toolu_tree", "src/tree.py")]
    assert_equal_to_a_rebuild()


def _edit_paths() -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute("SELECT tool_use_id, rel_path FROM edit")]
    finally:
        connection.close()


def test_reading_in_worker_processes_changes_nothing(workspace: Workspace) -> None:
    """The fold is in one process, in one order, however many processes read the files."""
    _enable()
    result = CliRunner().invoke(main, ["ingest", "--workers", "1"])
    assert result.exit_code == 0, result.output
    in_process = dump_store()
    result = CliRunner().invoke(main, ["rebuild", "--workers", "3"])
    assert result.exit_code == 0, result.output
    assert dump_store() == in_process


@pytest.mark.parametrize("rounds", [3])
def test_several_ingests_in_a_row_with_nothing_new(workspace: Workspace, rounds: int) -> None:
    """After the first, an ingest with nothing new reads no file at all."""
    _enable()
    first = _ingest()["parsed"]
    assert first["files_parsed"] == first["files_total"] > 0
    for _ in range(rounds - 1):
        again = _ingest()["parsed"]
        assert again["mode"] == "incremental", again["full_reason"]
        assert (again["files_parsed"], again["files_skipped"]) == (0, first["files_total"])
    assert_equal_to_a_rebuild()


# Outcomes: a mark at a moment that has passed is kept once measured; HEAD never is.


def _days_ago(days: int, second: int = 0) -> datetime:
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days) + timedelta(seconds=second)


def _one_attributed_commit(lab: Workspace) -> str:
    """Seven lines committed ten days ago by a session that printed the hash.

    Its 7-day mark has passed and its 30 and 90-day marks have not, whatever today is.
    """
    _write(lab, "src/app.py", SEVEN)
    made = commit(lab.repo, _days_ago(10, 2).isoformat(), "the work")
    stamp = "%Y-%m-%dT%H:%M:%S.000Z"
    _session(
        lab,
        "src/app.py",
        SEVEN,
        made,
        wrote_at=_days_ago(10, -600).strftime(stamp),
        called_at=_days_ago(10).strftime(stamp),
    )
    return made


def _fates(made: str) -> set[tuple]:
    connection = db.connect()
    try:
        return {
            tuple(row)
            for row in connection.execute(
                "SELECT alive_7d, alive_30d, alive_head, blame_head, reworked_by"
                " FROM line_fate WHERE commit_hash = ?",
                (made,),
            )
        }
    finally:
        connection.close()


def _set_marks(assignment: str) -> None:
    connection = db.connect()
    try:
        connection.execute(f"UPDATE outcome_mark SET {assignment}")
    finally:
        connection.close()


def test_a_measured_mark_is_kept_and_head_is_read_again(lab: Workspace) -> None:
    made = _one_attributed_commit(lab)
    _enable()
    first = _ingest()["outcomes"]
    assert (first["marks_measured"], first["marks_kept"]) == (1, 0), "the 7-day mark only"
    assert _fates(made) == {(1, None, 1, 1, None)}

    again = _ingest()["outcomes"]
    assert (again["marks_measured"], again["marks_kept"]) == (0, 1)
    assert again["blamed_paths"] == 1, "blame at HEAD is read on every run"

    _write(lab, "src/app.py", REPLACEMENT)
    undone = commit(lab.repo, _days_ago(1).isoformat(), "rewrite it")
    after = _ingest()["outcomes"]
    assert (after["marks_measured"], after["marks_kept"]) == (0, 1)
    assert _fates(made) == {(1, None, 0, 0, undone)}, "alive at 7 days, gone at HEAD now"
    assert_equal_to_a_rebuild()


def test_an_ingest_reuses_the_kept_mark_and_a_rebuild_measures_it_again(
    lab: Workspace,
) -> None:
    """Shown by planting a false answer in the cache: an ingest trusts it, a rebuild does not.

    This is the whole difference between the two commands for outcomes, and why the
    comparison in this module holds only while history before a mark is not rewritten.
    """
    made = _one_attributed_commit(lab)
    _enable()
    _ingest()
    _set_marks("alive_7d = 0")
    _ingest()
    assert _fates(made) == {(0, None, 1, 1, None)}, "the kept answer, not git's"
    _rebuild()
    assert _fates(made) == {(1, None, 1, 1, None)}, "measured again from git"


def test_a_commit_whose_attribution_changed_is_measured_again(lab: Workspace) -> None:
    made = _one_attributed_commit(lab)
    _enable()
    _ingest()
    _set_marks("alive_7d = 0, attribution = 'counted by other rows'")
    again = _ingest()["outcomes"]
    assert (again["marks_measured"], again["marks_kept"]) == (1, 0)
    assert _fates(made) == {(1, None, 1, 1, None)}


def test_commits_are_read_once_and_a_rewritten_one_leaves_the_store(lab: Workspace) -> None:
    """A stored commit is kept; a new one is read; one no longer reachable is dropped."""
    made = _one_attributed_commit(lab)
    _enable()
    first = _ingest()["harvested"]
    assert (first["commits"], first["kept"]) == (2, 0), "the root commit and the work"

    again = _ingest()["harvested"]
    assert (again["commits"], again["merges"], again["kept"], again["dropped"]) == (0, 0, 2, 0)

    _write(lab, "src/other.py", "other = 1\n")
    rewritten = commit(lab.repo, _days_ago(9).isoformat(), "another")
    after = _ingest()["harvested"]
    assert (after["commits"], after["kept"], after["dropped"]) == (1, 2, 0)

    git(lab.repo, "reset", "-q", "--hard", made)
    git(lab.repo, "reflog", "expire", "--expire=now", "--all")
    dropped = _ingest()["harvested"]
    assert (dropped["commits"], dropped["kept"], dropped["dropped"]) == (0, 2, 1)
    connection = db.connect()
    try:
        assert not connection.execute(
            'SELECT 1 FROM "commit" WHERE commit_hash = ?', (rewritten,)
        ).fetchall()
    finally:
        connection.close()
    assert_equal_to_a_rebuild()


def test_status_says_what_the_last_ingest_read_and_how_long_each_step_took(
    workspace: Workspace,
) -> None:
    _enable()
    _ingest()
    _ingest()
    result = CliRunner().invoke(main, ["status", "--json"])
    assert result.exit_code == 0, result.output
    last = json.loads(result.output)["last_ingest"]
    assert (last["parse_mode"], last["files_parsed"], last["files_skipped"]) == (
        "incremental",
        0,
        4,
    )
    assert list(last["steps"]) == [
        "repositories",
        "archive",
        "parse",
        "hooks",
        "turn_trees",
        "commits",
        "attribution",
        "outcomes",
        "facts",
        "observations",
        "views",
        "checks",
    ], "the self-checks' own time follows the steps'"
    assert json.loads(result.output)["last_rebuild"] is None

    text = CliRunner().invoke(main, ["status"])
    assert "last ingest:" in text.output
    assert "parse incremental: 0 files parsed, 4 skipped" in text.output
