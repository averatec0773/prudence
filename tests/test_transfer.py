"""`prudence export` and `prudence import`: the store as one file, and back again."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import Workspace, record_one_session

from prudence.cli import main


def _sessions(runner: CliRunner) -> str:
    result = runner.invoke(main, ["sessions", "--last", "90d"])
    assert result.exit_code == 0, result.output
    return result.output


def test_an_export_round_trips_into_a_fresh_data_directory(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    runner = CliRunner()
    before = _sessions(runner)
    assert "alpha" in before

    bundle = lab.root / "bundle.tar.gz"
    result = runner.invoke(main, ["export", "--out", str(bundle)])
    assert result.exit_code == 0, result.output
    assert bundle.exists() and bundle.stat().st_size > 0

    with tarfile.open(bundle) as opened:
        names = set(opened.getnames())
        manifest = json.loads(opened.extractfile("manifest.json").read())
    assert "config.toml" in names
    assert "tables/session.jsonl" in names and "tables/hook_event.jsonl" in names
    assert manifest["versions"]["parser"] == 3
    assert manifest["with_archive"] is False

    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(lab.root / "restored"))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(lab.root / "restored-config"))
    result = runner.invoke(main, ["import", str(bundle)])
    assert result.exit_code == 0, result.output
    assert _sessions(runner) == before, "the same table, from the same rows"


def test_importing_into_a_store_that_holds_rows_is_refused(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    bundle = lab.root / "bundle.tar.gz"
    assert runner.invoke(main, ["export", "--out", str(bundle)]).exit_code == 0

    result = runner.invoke(main, ["import", str(bundle)])
    assert result.exit_code != 0
    assert "already holds rows" in result.output

    merged = runner.invoke(main, ["import", str(bundle), "--merge"])
    assert merged.exit_code != 0
    assert "--merge is not implemented" in merged.output


def test_the_archive_is_carried_only_when_asked(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    plain = lab.root / "plain.tar.gz"
    whole = lab.root / "whole.tar.gz"
    assert runner.invoke(main, ["export", "--out", str(plain)]).exit_code == 0
    assert runner.invoke(main, ["export", "--out", str(whole), "--archive"]).exit_code == 0

    with tarfile.open(plain) as opened:
        assert "tables/archive_chunk.jsonl" not in opened.getnames()
    with tarfile.open(whole) as opened:
        rows = opened.extractfile("tables/archive_chunk.jsonl").read().splitlines()
        assert rows, "the compressed chunks travel too"
        assert isinstance(json.loads(rows[0])["data"], str), "bytes ride as base64"


def test_a_file_that_is_not_an_export_is_refused(lab: Workspace) -> None:
    record_one_session(lab)
    stranger = Path(lab.root / "stranger.tar.gz")
    with tarfile.open(stranger, "w:gz") as opened:
        opened.add(lab.repo / "src" / "app.py", arcname="app.py")
    result = CliRunner().invoke(main, ["import", str(stranger)])
    assert result.exit_code != 0
