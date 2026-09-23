"""A session carried into a second file, in the two shapes the agent writes.

A fork (and a resume into a new file) repeats the first session's whole history record
for record before the new session's own records. Which shape it is decides which
ownership rule answers it, so both are here, each with its own fixture, small enough to
count by hand.

- **The fork.** Every copied line keeps the parent's own `sessionId`, so the record says
  where it came from and the first rule settles it: a record belongs to the session it
  declares. `PARENT` and `FORK` below.
- **The re-stamped resume.** The copied lines carry the *new* session's id, so nothing in
  the file says they are copies: the repeated `uuid` is the only trace. The second rule
  settles it: the session whose transcript begins earlier owns the record.
  `FIRST_SITTING` and `SECOND_SITTING` below.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import Workspace, write_transcript

from prudence.cli import main
from prudence.store import db, derived

PARENT = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
FORK = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
FIRST_SITTING = "cccccccc-3333-4333-8333-cccccccccccc"
SECOND_SITTING = "dddddddd-4444-4444-8444-dddddddddddd"


def _record(
    session_id: str | None,
    uuid: str | None,
    record_type: str,
    at: str,
    cwd: str,
    prompt_id: str | None = None,
    message: dict | None = None,
) -> dict:
    record = {
        "type": record_type,
        "cwd": cwd,
        "gitBranch": "master",
        "version": "2.1.278",
        "isSidechain": False,
        "entrypoint": "cli",
        "timestamp": at,
    }
    if session_id is not None:
        record["sessionId"] = session_id
    if uuid is not None:
        record["uuid"] = uuid
    if prompt_id is not None:
        record["promptId"] = prompt_id
    if message is not None:
        record["message"] = message
    return record


def _prompt(session_id: str, uuid: str, at: str, cwd: str, prompt_id: str, text: str) -> dict:
    return _record(
        session_id,
        uuid,
        "user",
        at,
        cwd,
        prompt_id,
        {"role": "user", "content": [{"type": "text", "text": text}]},
    )


def _answer(session_id: str, uuid: str, at: str, cwd: str, prompt_id: str, request_id: str) -> dict:
    record = _record(
        session_id,
        uuid,
        "assistant",
        at,
        cwd,
        prompt_id,
        {
            "role": "assistant",
            "model": "claude-opus-5",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "content": [{"type": "text", "text": "hidden"}],
        },
    )
    record["requestId"] = request_id
    return record


def _snapshot(at: str, cwd: str) -> dict:
    """A record Claude Code writes with neither a session id nor a uuid of its own."""
    return _record(None, None, "file-history-snapshot", at, cwd)


def _copied_history(cwd: str) -> list[dict]:
    """The parent's history, as both files carry it: the parent's ids on every line."""
    return [
        _prompt(PARENT, "p1", "2026-09-15T09:00:00.000Z", cwd, "turn-1", "Look at the loader."),
        _answer(PARENT, "a1", "2026-09-15T09:01:00.000Z", cwd, "turn-1", "req_1"),
        _snapshot("2026-09-15T09:02:00.000Z", cwd),
        _prompt(PARENT, "p2", "2026-09-15T09:03:00.000Z", cwd, "turn-2", "Now fix it."),
        _answer(PARENT, "a2", "2026-09-15T09:04:00.000Z", cwd, "turn-2", "req_2"),
    ]


def _parent_only(cwd: str) -> list[dict]:
    """What the parent wrote after the fork was taken off it."""
    return [
        _prompt(PARENT, "p3", "2026-09-15T10:00:00.000Z", cwd, "turn-3", "And the tests."),
        _answer(PARENT, "a3", "2026-09-15T10:01:00.000Z", cwd, "turn-3", "req_3"),
    ]


def _fork_only(cwd: str) -> list[dict]:
    """What the fork wrote, under its own id."""
    return [
        _prompt(FORK, "f1", "2026-09-15T11:00:00.000Z", cwd, "turn-f1", "Try it another way."),
        _answer(FORK, "f2", "2026-09-15T11:01:00.000Z", cwd, "turn-f1", "req_f1"),
        _snapshot("2026-09-15T11:02:00.000Z", cwd),
    ]


def _write(lab: Workspace, with_parent: bool = True) -> None:
    cwd = str(lab.repo)
    if with_parent:
        write_transcript(lab.project, PARENT, _copied_history(cwd) + _parent_only(cwd))
    write_transcript(lab.project, FORK, _copied_history(cwd) + _fork_only(cwd))


def _ingest() -> None:
    runner = CliRunner()
    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    assert enabled.exit_code == 0, enabled.output
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _dump() -> dict[str, list[tuple]]:
    """Every derived table, ordered, so two builds can be compared as a whole."""
    connection = db.connect()
    try:
        dumped = {}
        for table in derived.TABLES:
            columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
            order = ", ".join(f'"{name}"' for name in columns)
            dumped[table] = [
                tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}")
            ]
        return dumped
    finally:
        connection.close()


def test_a_fork_starts_when_it_was_forked_not_when_its_parent_started(lab: Workspace) -> None:
    _write(lab)
    _ingest()
    started = dict(_rows("SELECT session_id, first_at FROM session"))
    assert started[PARENT] == "2026-09-15T09:00:00.000Z"
    assert started[FORK] == "2026-09-15T11:00:00.000Z", "its first own record, not the copied one"
    ended = dict(_rows("SELECT session_id, last_at FROM session"))
    assert ended[PARENT] == "2026-09-15T10:01:00.000Z"
    assert ended[FORK] == "2026-09-15T11:02:00.000Z"


def test_a_forks_turns_are_its_own_and_the_parent_keeps_all_of_its(lab: Workspace) -> None:
    _write(lab)
    _ingest()
    turns = _rows("SELECT session_id, turn_id FROM turn")
    by_session: dict[str, set[str]] = {}
    for session_id, turn_id in turns:
        by_session.setdefault(session_id, set()).add(turn_id)
    # A record carrying no `promptId` belongs to the turn open when it was written, and to
    # `<id>:0` only before the session's first prompt (parser version 6), so the snapshot
    # record no longer makes a turn of its own.
    assert by_session[PARENT] == {"turn-1", "turn-2", "turn-3"}
    assert by_session[FORK] == {"turn-f1"}, "the copied turns belong to the parent"
    counts = dict(_rows("SELECT session_id, record_count FROM session"))
    assert counts[PARENT] == 7, "five of its own history plus the two it wrote afterwards"
    assert counts[FORK] == 3, "only the records it added"


def test_every_response_is_counted_once_under_the_session_that_made_it(lab: Workspace) -> None:
    _write(lab)
    _ingest()
    usage = _rows("SELECT session_id, record_id, request_id FROM usage ORDER BY record_id")
    assert [row[1] for row in usage] == ["a1", "a2", "a3", "f2"]
    assert dict((row[1], row[0]) for row in usage) == {
        "a1": PARENT,
        "a2": PARENT,
        "a3": PARENT,
        "f2": FORK,
    }
    assert len(usage) == 4, "as many rows as there are records that carried usage"


def test_a_fork_records_what_it_was_forked_from_and_where(lab: Workspace) -> None:
    _write(lab)
    _ingest()
    rows = dict(
        (row[0], row[1:])
        for row in _rows("SELECT session_id, source, forked_from, fork_point FROM session")
    )
    assert rows[PARENT] == ("claude_code", None, None), "a session nobody forked from"
    assert rows[FORK] == ("claude_code", PARENT, "a2"), "the last copied record with a real id"


def test_the_same_tables_come_out_whichever_file_is_read_first(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which session owns a record must not depend on the order the files are read in.

    The build reads the archived transcripts in one sorted order (`_transcripts_in_order`),
    so reversing that sort is exactly what ingesting the files in the other order would do.
    """
    _write(lab)
    _ingest()
    forwards = _dump()

    in_order = derived._transcripts_in_order
    monkeypatch.setattr(
        derived,
        "_transcripts_in_order",
        lambda connection, adapter: list(reversed(in_order(connection, adapter))),
    )
    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output

    assert _dump() == forwards


def test_a_fork_whose_parent_was_deleted_still_yields_the_parents_history_once(
    lab: Workspace,
) -> None:
    """Claude Code deletes transcripts after `cleanupPeriodDays`; the copy outlives them."""
    _write(lab, with_parent=False)
    assert not (lab.project / f"{PARENT}.jsonl").exists()
    _ingest()

    sessions = dict(
        (row[0], row[1:])
        for row in _rows("SELECT session_id, first_at, record_count, forked_from FROM session")
    )
    assert set(sessions) == {PARENT, FORK}
    assert sessions[PARENT] == ("2026-09-15T09:00:00.000Z", 5, None), "its history, kept once"
    assert sessions[FORK] == ("2026-09-15T11:00:00.000Z", 3, PARENT)
    usage = _rows("SELECT session_id, record_id FROM usage ORDER BY record_id")
    assert usage == [(PARENT, "a1"), (PARENT, "a2"), (FORK, "f2")]


def test_a_record_that_declares_no_session_belongs_to_the_side_of_the_fork_it_sits_on(
    lab: Workspace,
) -> None:
    """Some record types carry neither a session id nor a uuid. Position decides.

    The copied history is a prefix: a record with no session id of its own belongs to
    whatever the last record that did name one belonged to.
    """
    _write(lab)
    _ingest()
    rows = _rows(
        "SELECT session_id, timestamp FROM record WHERE type = 'file-history-snapshot'"
        " ORDER BY timestamp"
    )
    assert rows == [
        (PARENT, "2026-09-15T09:02:00.000Z"),
        (FORK, "2026-09-15T11:02:00.000Z"),
    ], "the copied snapshot is the parent's, the one after the fork point is the fork's"


def test_the_fixture_is_the_shape_this_module_claims(lab: Workspace) -> None:
    """A guard on the fixture itself: the copied lines are the parent's, byte for byte."""
    cwd = str(lab.repo)
    _write(lab)
    fork_lines = (lab.project / f"{FORK}.jsonl").read_text().splitlines()
    parent_lines = (lab.project / f"{PARENT}.jsonl").read_text().splitlines()
    assert fork_lines[: len(_copied_history(cwd))] == parent_lines[: len(_copied_history(cwd))]
    assert Path(lab.project / f"{FORK}.jsonl").stat().st_size > 0


# The re-stamped resume: the same records under the new session's id, so only the repeated
# `uuid` shows that they are copies.


def _first_sitting(cwd: str) -> list[dict]:
    return [
        _prompt(FIRST_SITTING, "s1", "2026-09-16T09:00:00.000Z", cwd, "sit-1", "Start the work."),
        _answer(FIRST_SITTING, "s2", "2026-09-16T09:01:00.000Z", cwd, "sit-1", "req_s1"),
        _prompt(FIRST_SITTING, "s3", "2026-09-16T09:02:00.000Z", cwd, "sit-2", "Keep going."),
        _answer(FIRST_SITTING, "s4", "2026-09-16T09:03:00.000Z", cwd, "sit-2", "req_s2"),
    ]


def _re_stamped(cwd: str) -> list[dict]:
    """The first sitting's records with the second sitting's id written over them."""
    return [{**record, "sessionId": SECOND_SITTING} for record in _first_sitting(cwd)]


def _second_sitting_only(cwd: str) -> list[dict]:
    return [
        _prompt(SECOND_SITTING, "t1", "2026-09-16T14:00:00.000Z", cwd, "sit-3", "Pick it up."),
        _answer(SECOND_SITTING, "t2", "2026-09-16T14:01:00.000Z", cwd, "sit-3", "req_t1"),
    ]


def _write_sittings(lab: Workspace) -> None:
    cwd = str(lab.repo)
    write_transcript(lab.project, FIRST_SITTING, _first_sitting(cwd))
    write_transcript(lab.project, SECOND_SITTING, _re_stamped(cwd) + _second_sitting_only(cwd))


def test_the_transcript_that_begins_earlier_owns_a_record_both_sessions_claim(
    lab: Workspace,
) -> None:
    """Nothing in a re-stamped copy says it is one, so the earlier session keeps it."""
    _write_sittings(lab)
    _ingest()
    owners = dict(
        _rows(
            "SELECT record_id, session_id FROM record WHERE record_id IN"
            " ('s1', 's2', 's3', 's4', 't1', 't2')"
        )
    )
    assert owners == {
        "s1": FIRST_SITTING,
        "s2": FIRST_SITTING,
        "s3": FIRST_SITTING,
        "s4": FIRST_SITTING,
        "t1": SECOND_SITTING,
        "t2": SECOND_SITTING,
    }
    usage = _rows("SELECT session_id, record_id FROM usage ORDER BY record_id")
    assert usage == [(FIRST_SITTING, "s2"), (FIRST_SITTING, "s4"), (SECOND_SITTING, "t2")]


def test_the_later_sitting_counts_the_copies_as_replayed_and_is_not_a_fork(
    lab: Workspace,
) -> None:
    """`forked_from` is for a copy that names its origin. A re-stamped one names none."""
    _write_sittings(lab)
    _ingest()
    rows = dict(
        (row[0], row[1:])
        for row in _rows(
            "SELECT session_id, record_count, replayed_records, forked_from, notes FROM session"
        )
    )
    assert rows[FIRST_SITTING] == (4, 0, None, None)
    second_count, second_replayed, second_forked, second_notes = rows[SECOND_SITTING]
    assert (second_count, second_replayed) == (2, 4), "its own two records, four replayed"
    assert second_forked is None, "the file gives nothing to point `forked_from` at"
    assert second_notes is not None and "replayed 4 records" in second_notes


def test_the_order_the_files_were_ingested_in_does_not_change_the_tables(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read order is the files' own: their first timestamp, then the archive path.

    So archiving the later transcript first, in its own earlier ingest, must produce the
    same tables as archiving both at once. This is the invariant. Reversing the sort
    itself is not one: the sort *is* the ownership rule, so turning it round asks a
    different question.
    """
    cwd = str(lab.repo)
    write_transcript(lab.project, SECOND_SITTING, _re_stamped(cwd) + _second_sitting_only(cwd))
    _ingest()
    write_transcript(lab.project, FIRST_SITTING, _first_sitting(cwd))
    result = CliRunner().invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output
    later_file_first = _dump()
    assert len(later_file_first["session"]) == 2, "both sittings were built"

    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(lab.root / "both-at-once"))
    _ingest()

    assert _dump() == later_file_first
