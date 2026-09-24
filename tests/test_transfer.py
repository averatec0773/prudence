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
    assert manifest["versions"]["parser"] == 7
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


@pytest.mark.parametrize("with_archive", [False, True])
def test_restored_named_source_can_be_filtered_and_forgotten(lab, monkeypatch, with_archive):
    from prudence import paths
    from prudence.store import app_views, db, erase, views

    record_one_session(lab)
    con = db.connect(paths.database_file())
    con.execute("UPDATE collection_source SET label='Work Claude' WHERE id='claude'")
    app_views.replace_app_views(con)
    expected = [tuple(row) for row in con.execute("SELECT * FROM app_session_sources")]
    assert expected and expected[0][3] == "Work Claude"
    con.close()
    runner = CliRunner()
    bundle = lab.root / "named.tar.gz"
    args = ["export", "--out", str(bundle)] + (["--archive"] if with_archive else [])
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(lab.root / "restored"))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(lab.root / "restored-config"))
    result = runner.invoke(main, ["import", str(bundle)])
    assert result.exit_code == 0, result.output
    con = db.connect(paths.database_file())
    assert [tuple(row) for row in con.execute("SELECT * FROM app_session_sources")] == expected
    assert views.search_sessions(con, source_id="claude")["total"] == 1
    app_views.replace_app_views(con)
    assert [tuple(row) for row in con.execute("SELECT * FROM app_session_sources")] == expected
    sid = expected[0][0]
    con.execute(
        "INSERT INTO collection_source VALUES ('extra', 'claude_code', 'New home', '/new', 1)"
    )
    con.execute(
        "INSERT INTO archive_file(path,source,session_id,size,first_seen,last_seen,agent_kind)"
        " VALUES ('/new/s.jsonl','transcript',?,0,'now','now','claude_code')",
        (sid,),
    )
    con.execute("INSERT INTO archive_origin VALUES ('/new/s.jsonl','extra')")
    app_views.replace_app_views(con)
    assert {row[1] for row in con.execute("SELECT * FROM app_session_sources")} == {
        "claude",
        "extra",
    }
    assert views.search_sessions(con, source_id="claude")["total"] == 1
    erase.forget_sessions(con, [sid])
    assert con.execute("SELECT COUNT(*) FROM session_source").fetchone()[0] == 0
    con.close()
