"""The archive must add bytes and never add them twice, whatever the file did meanwhile."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
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


class _Counted:
    """A file object that adds up how many bytes were read through it."""

    def __init__(self, handle, counts: dict[str, int], name: str) -> None:
        self._handle = handle
        self._counts = counts
        self._name = name

    def read(self, *args):
        data = self._handle.read(*args)
        self._counts[self._name] = self._counts.get(self._name, 0) + len(data)
        return data

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self._handle.close()


def _count_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts: dict[str, int] = {}
    original = Path.open

    def counted_open(self, *args, **kwargs):
        return _Counted(original(self, *args, **kwargs), counts, str(self))

    monkeypatch.setattr(Path, "open", counted_open)
    return counts


def _archive(targets: list[archive.Target]) -> archive.IngestStats:
    connection = db.connect()
    try:
        return archive.archive(connection, targets)
    finally:
        connection.close()


def _big_transcript(workspace: Workspace) -> Path:
    """A transcript of a few megabytes, so reading all of it would show."""
    transcript = workspace.transcripts[0]
    filler = "".join(
        f'{{"type": "system", "uuid": "fill-{index}", "timestamp": "2026-09-13T10:00:00Z",'
        f' "content": "{"x" * 400}"}}\n'
        for index in range(8000)
    )
    with transcript.open("a") as handle:
        handle.write(filler)
    return transcript


def test_a_grown_file_is_checked_by_a_few_windows_not_read_whole(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable()
    transcript = _big_transcript(workspace)
    targets = archive.collect_targets(set(config_module.load().repositories))
    _archive(targets)
    addition = b'{"type": "assistant", "uuid": "z02", "timestamp": "2026-09-13T11:00:00Z"}\n'
    with transcript.open("ab") as handle:
        handle.write(addition)
    size = transcript.stat().st_size
    assert size > 3_000_000

    counts = _count_reads(monkeypatch)
    stats = _archive(targets)

    assert (stats.new_bytes, stats.rearchived_files) == (len(addition), 0)
    assert counts[str(transcript)] <= len(addition) + 3 * archive.PREFIX_WINDOW
    assert all(counts.get(str(target.path), 0) == 0 for target in targets[1:]), (
        "an unchanged file is a stat, and nothing is read from it"
    )
    connection = db.connect()
    try:
        assert archive.read_file(connection, str(transcript)) == transcript.read_bytes()
    finally:
        connection.close()


def test_a_file_rewritten_under_the_same_first_line_is_still_archived_again(
    workspace: Workspace,
) -> None:
    """Compaction keeps the session's opening lines and rewrites what follows them."""
    _enable()
    transcript = _big_transcript(workspace)
    targets = archive.collect_targets(set(config_module.load().repositories))
    _archive(targets)
    first_line = transcript.read_bytes().split(b"\n", 1)[0]
    transcript.write_bytes(
        first_line
        + b"\n"
        + b"".join(
            b'{"type": "system", "uuid": "compacted-%d", "timestamp": "2026-09-14T10:00:00Z"}\n'
            % index
            for index in range(60000)
        )
    )
    stats = _archive(targets)
    assert stats.rearchived_files == 1
    connection = db.connect()
    try:
        assert archive.read_file(connection, str(transcript)) == transcript.read_bytes()
    finally:
        connection.close()


def test_a_file_changed_in_place_at_the_same_size_is_archived_again(
    workspace: Workspace,
) -> None:
    """Same size, a new modification time and one byte different in the middle."""
    _enable()
    transcript = _big_transcript(workspace)
    targets = archive.collect_targets(set(config_module.load().repositories))
    _archive(targets)
    data = bytearray(transcript.read_bytes())
    middle = len(data) // 3
    data[middle] = ord("y") if data[middle] != ord("y") else ord("z")
    transcript.write_bytes(bytes(data))
    stats = _archive(targets)
    assert stats.rearchived_files == 1
    connection = db.connect()
    try:
        assert archive.read_file(connection, str(transcript)) == transcript.read_bytes()
    finally:
        connection.close()


def test_lines_come_back_whole_across_chunk_boundaries(tmp_path: Path) -> None:
    """A line split between two appends, and a last line still being written."""
    path = tmp_path / "grows.jsonl"
    target = archive.Target(path, "transcript", "s", None)
    pieces = [b'{"a": 1}\n{"b": ', b'2}\n{"c": 3}\n', b'{"d": 4}\n{"e": 5', b'}\n{"f"']
    connection = db.connect()
    try:
        for piece in pieces:
            with path.open("ab") as handle:
                handle.write(piece)
            archive.archive(connection, [target])
        whole = path.read_bytes()
        expected, offset = [], 0
        for line in whole.split(b"\n"):
            if line.strip():
                expected.append((offset, line))
            offset += len(line) + 1
        assert list(archive.iter_lines(connection, str(path))) == expected
        chunks = connection.execute(
            "SELECT COUNT(*) FROM archive_chunk WHERE path = ?", (str(path),)
        ).fetchone()[0]
        assert chunks == len(pieces), "one chunk per append"
    finally:
        connection.close()
