"""Collection choices survive restarts without changing repository consent."""

from dataclasses import replace
from pathlib import Path

import pytest

from prudence import config, sources
from prudence.store import archive, db


def test_default_locations_and_typed_extra_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    cfg = config.load(tmp_path / "config.toml")
    assert [(s.id, s.kind) for s in cfg.sources.values()] == [
        ("claude", "claude_code"),
        ("codex", "codex"),
    ]
    assert cfg.sources["claude"].enabled
    assert not cfg.sources["codex"].enabled
    extra = config.add_source(cfg, "claude_code", "Work", tmp_path / "work")
    cfg.sources[extra.id] = replace(extra, enabled=False)
    config.save(cfg)
    again = config.load(cfg.path)
    assert again.sources == cfg.sources
    assert again.repositories == {}
    with pytest.raises(ValueError, match="already"):
        config.add_source(again, "claude_code", "Duplicate", tmp_path / "work")
    with pytest.raises(ValueError, match="kind"):
        config.add_source(again, "other", "Bad", tmp_path / "bad")


def test_configured_claude_reads_its_own_companions(tmp_path):
    home = tmp_path / "claude-extra"
    transcript = home / "projects" / "repo" / "s.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"type":"user","cwd":"/repo"}\n')
    history = home / "file-history" / "s" / "before"
    history.parent.mkdir(parents=True)
    history.write_text("old")
    adapter = sources.source("claude_code", home)
    sessions = adapter.session_files()
    assert [s.path for s in sessions] == [transcript]
    assert [c.path for c in adapter.companion_files(sessions[0])] == [history]


def test_archive_migration_preserves_bytes_and_defaults_to_claude(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE archive_file(path TEXT PRIMARY KEY,source TEXT NOT NULL,
    session_id TEXT,repo_key TEXT,size INTEGER NOT NULL,mtime REAL,sha256 TEXT,
    first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,generation INTEGER NOT NULL DEFAULT 0);
    INSERT INTO archive_file VALUES ('old','transcript','s','r',3,0,NULL,'a','b',0);
    PRAGMA user_version=1;""")
    con.close()
    con = db.connect(path)
    row = con.execute("SELECT * FROM archive_file").fetchone()
    assert row["agent_kind"] == "claude_code"
    assert row["size"] == 3
    assert con.execute("SELECT source_id FROM archive_origin").fetchone()[0] == "claude"
    con.close()


def test_archive_keeps_multiple_location_origins_on_unchanged_file(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text("{}\n")
    con = db.connect(tmp_path / "archive.db")
    a = archive.Target(path, "transcript", "s", "r", "claude_code", "claude")
    b = replace(a, source_id="extra")
    archive.archive(con, [a])
    archive.archive(con, [b])
    assert con.execute("SELECT COUNT(*) FROM archive_file").fetchone()[0] == 1
    assert {r[0] for r in con.execute("SELECT source_id FROM archive_origin")} == {
        "claude",
        "extra",
    }
    assert archive.read_file(con, str(path)) == b"{}\n"
    con.close()


def test_sources_cli_keeps_capture_and_extra_location_settings(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from prudence.cli import main

    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(tmp_path / "data"))
    runner = CliRunner()
    initial = runner.invoke(main, ["sources", "--json"])
    assert initial.exit_code == 0, initial.output
    assert [r["id"] for r in json.loads(initial.output)] == ["claude", "codex"]
    changed = runner.invoke(main, ["sources", "set", "codex", "--enabled", "--json"])
    assert changed.exit_code == 0, changed.output
    assert config.load().sources["codex"].enabled
    extra = runner.invoke(
        main,
        [
            "sources",
            "add",
            "--kind",
            "claude_code",
            "--name",
            "Work",
            "--home",
            str(tmp_path / "work"),
            "--json",
        ],
    )
    assert extra.exit_code == 0, extra.output
    rows = json.loads(extra.output)
    assert len(rows) == 3 and rows[-1]["label"] == "Work"
    paused = runner.invoke(main, ["sources", "set", rows[-1]["id"], "--paused"])
    assert paused.exit_code == 0, paused.output
    assert not config.load().sources[rows[-1]["id"]].enabled


def test_duplicate_home_is_one_session_with_two_origins(workspace):
    import shutil

    from click.testing import CliRunner

    from prudence.cli import main
    from prudence.store import app_views

    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha"]).exit_code == 0
    first = runner.invoke(main, ["ingest", "--workers", "1"])
    assert first.exit_code == 0, first.output
    con = db.connect()
    before = tuple(con.execute("SELECT COUNT(*), SUM(input_tokens) FROM usage").fetchone())
    count = con.execute("SELECT COUNT(*) FROM session").fetchone()[0]
    con.close()
    cfg = config.load()
    extra = workspace.root / "extra-home"
    shutil.copytree(Path(cfg.sources["claude"].home), extra)
    added = config.add_source(cfg, "claude_code", "Extra", extra)
    config.save(cfg)
    result = runner.invoke(main, ["ingest", "--workers", "1"])
    assert result.exit_code == 0, result.output
    con = db.connect()
    try:
        assert con.execute("SELECT COUNT(*) FROM session").fetchone()[0] == count
        assert (
            tuple(con.execute("SELECT COUNT(*), SUM(input_tokens) FROM usage").fetchone()) == before
        )
        assert {r[0] for r in con.execute("SELECT source_id FROM app_session_sources")} == {
            "claude",
            added.id,
        }
        row = con.execute("SELECT source, source_labels FROM app_session_list").fetchone()
        assert row["source"] == "claude_code"
        assert "Extra" in row["source_labels"]
        assert app_views.columns(con, "app_session_list") == app_views.APP_VIEWS["app_session_list"]
    finally:
        con.close()


def test_mixed_agent_import_pause_and_parallel_noop(workspace):
    import json

    from click.testing import CliRunner

    from prudence.cli import main
    from prudence.store import meta
    from prudence.store.views.search import search_sessions

    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha"]).exit_code == 0
    cfg = config.load()
    home = workspace.root / "codex"
    (home / "sessions").mkdir(parents=True)
    native = workspace.transcripts[0].stem
    cfg.sources["codex"] = replace(cfg.sources["codex"], home=str(home), enabled=True)
    config.save(cfg)
    data = [
        {"type": "session_meta", "payload": {"id": native, "cwd": str(workspace.repo)}},
        {"type": "turn_context", "payload": {"turn_id": "t", "model": "test-codex"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "change files"}},
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "turn_id": "t",
                "item": {
                    "type": "FileChange",
                    "id": "patch",
                    "status": "completed",
                    "changes": {
                        str(workspace.repo / name): {"type": "add", "content": "new line\n"}
                        for name in ("a.py", "b.py", "README.md")
                    },
                },
            },
        },
        {
            "type": "token_usage_record",
            "payload": {
                "response_id": "r",
                "turn_id": "t",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 60,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 8,
                },
            },
        },
    ]
    for row in data:
        row["timestamp"] = "2026-09-23T10:00:00Z"
    transcript = home / "sessions" / "rollout.jsonl"
    transcript.write_text("".join(json.dumps(row) + "\n" for row in data))
    first = runner.invoke(main, ["ingest", "--workers", "2"])
    assert first.exit_code == 0, first.output
    con = db.connect()
    sid = "codex:" + native
    try:
        assert (
            con.execute(
                "SELECT total_tokens FROM app_session_list WHERE session_id=?", (sid,)
            ).fetchone()[0]
            == 120
        )
        assert (
            con.execute("SELECT COUNT(*) FROM tool_call WHERE session_id=?", (sid,)).fetchone()[0]
            == 1
        )
        assert (
            con.execute("SELECT COUNT(*) FROM edit WHERE session_id=?", (sid,)).fetchone()[0] == 3
        )
        assert search_sessions(con, source="codex")["total"] == 1
        assert search_sessions(con, source_id="codex", model="test-codex")["total"] == 1
        assert (
            con.execute("SELECT source FROM session WHERE session_id=?", (native,)).fetchone()[0]
            == "claude_code"
        )
        assert meta.get_meta(con, meta.APP_CONTRACT_VERSION_KEY) == "5"
        snapshot = [tuple(r) for r in con.execute("SELECT * FROM usage ORDER BY record_id")]
    finally:
        con.close()
    paused = runner.invoke(main, ["sources", "set", "codex", "--paused"])
    assert paused.exit_code == 0, paused.output
    with transcript.open("a") as file:
        file.write(
            json.dumps({**data[-1], "payload": {**data[-1]["payload"], "response_id": "new"}})
            + "\n"
        )
    again = runner.invoke(main, ["ingest", "--workers", "1"])
    assert again.exit_code == 0, again.output
    assert "Kept" in again.output or "0 sessions" in again.output
    con = db.connect()
    try:
        assert [tuple(r) for r in con.execute("SELECT * FROM usage ORDER BY record_id")] == snapshot
    finally:
        con.close()
