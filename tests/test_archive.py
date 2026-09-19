"""The archive must add bytes and never add them twice, whatever the file did meanwhile."""

from __future__ import annotations

import stat

from click.testing import CliRunner
from conftest import Workspace

from prudence import config as config_module
from prudence.cli import main
from prudence.paths import database_file
from prudence.store import archive, db


def _enable(level: str = "full") -> None:
    result = CliRunner().invoke(main, ["init", "--enable", "alpha", "--level", level])
    assert result.exit_code == 0, result.output


def _ingest_once() -> archive.IngestStats:
    config = config_module.load()
    connection = db.connect()
    try:
        targets = archive.collect_targets(set(config.repositories))
        return archive.archive(connection, targets)
    finally:
        connection.close()


def test_a_second_ingest_adds_nothing(workspace: Workspace) -> None:
    _enable()
    first = _ingest_once()
    assert first.files_seen == 4, "three transcripts plus one subagent file"
    assert first.new_files == 4
    assert first.new_bytes > 0

    second = _ingest_once()
    assert second.new_bytes == 0
    assert second.new_files == 0
    assert second.unchanged_files == 4


def test_an_appended_transcript_contributes_exactly_the_appended_bytes(
    workspace: Workspace,
) -> None:
    _enable()
    _ingest_once()
    transcript = workspace.transcripts[0]
    addition = b'{"type": "assistant", "uuid": "z01", "timestamp": "2026-09-13T10:00:00Z"}\n'
    with transcript.open("ab") as handle:
        handle.write(addition)

    stats = _ingest_once()

    assert stats.new_bytes == len(addition)
    assert stats.rearchived_files == 0
    connection = db.connect()
    try:
        assert archive.read_file(connection, str(transcript)) == transcript.read_bytes()
    finally:
        connection.close()


def test_a_rewritten_transcript_is_archived_again_and_the_old_chunks_are_superseded(
    workspace: Workspace,
) -> None:
    _enable()
    _ingest_once()
    transcript = workspace.transcripts[0]
    transcript.write_text(
        f'{{"type": "user", "uuid": "fresh", "cwd": "{workspace.repo}",'
        ' "timestamp": "2026-09-14T10:00:00Z"}\n'
    )

    stats = _ingest_once()

    assert stats.rearchived_files == 1
    connection = db.connect()
    try:
        assert archive.read_file(connection, str(transcript)) == transcript.read_bytes()
        superseded = connection.execute(
            "SELECT COUNT(*) FROM archive_chunk WHERE path = ? AND superseded = 1",
            (str(transcript),),
        ).fetchone()[0]
        assert superseded >= 1, "the earlier bytes are kept, only marked superseded"
    finally:
        connection.close()


def test_the_database_is_readable_by_its_owner_alone(workspace: Workspace) -> None:
    _enable()
    _ingest_once()
    mode = stat.S_IMODE(database_file().stat().st_mode)
    assert mode == 0o600, f"the archive holds unmodified transcripts; mode was {mode:o}"


def test_a_second_ingest_will_not_start_while_one_is_running(workspace: Workspace) -> None:
    _enable()
    with db.ingest_lock():
        result = CliRunner().invoke(main, ["ingest"])
    assert result.exit_code != 0
    assert "another prudence ingest is running" in result.output


def test_ingest_reports_what_it_did(workspace: Workspace) -> None:
    _enable()
    runner = CliRunner()
    first = runner.invoke(main, ["ingest"])
    assert first.exit_code == 0, first.output
    assert "4 files seen" in first.output
    second = runner.invoke(main, ["ingest"])
    assert "(0 bytes)" in second.output
