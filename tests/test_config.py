"""Enabling a repository is the whole consent record, so it has to survive a round trip."""

from __future__ import annotations

from click.testing import CliRunner
from conftest import Workspace

from prudence import config as config_module
from prudence.cli import main


def test_enable_and_disable_round_trip_through_the_file(workspace: Workspace) -> None:
    runner = CliRunner()

    enabled = runner.invoke(main, ["init", "--enable", "alpha", "--level", "metadata-only"])
    assert enabled.exit_code == 0, enabled.output
    assert "Enabled alpha at level metadata-only" in enabled.output

    config = config_module.load()
    repo = config.find("alpha")
    assert repo is not None
    assert repo.level == "metadata-only"
    assert repo.key == workspace.repo_key()
    assert repo.root_commits, "the identifiers are stored so the config survives a move"
    assert repo.common_dir is not None
    assert repo.enabled_at
    assert config.find(repo.key) is repo, "a repository is reachable by key as well as by name"

    text = config.path.read_text()
    assert 'level = "metadata-only"' in text
    assert config_module.load().repositories == config.repositories

    disabled = runner.invoke(main, ["init", "--disable", "alpha"])
    assert disabled.exit_code == 0, disabled.output
    assert config_module.load().repositories == {}


def test_enable_is_off_by_default_and_rejects_unknown_names(workspace: Workspace) -> None:
    assert config_module.load().repositories == {}, "nothing is enabled until asked"
    result = CliRunner().invoke(main, ["init", "--enable", "not-a-repository"])
    assert result.exit_code != 0
    assert "No repository called" in result.output


def test_status_shows_the_levels_and_the_paths(workspace: Workspace) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "full" in result.output
    assert "config:" in result.output and "data:" in result.output


def test_writer_escapes_what_toml_needs_escaped(tmp_path) -> None:
    config = config_module.Config(path=tmp_path / "config.toml")
    config_module.enable(
        config, key='root:a"b\\c', name="odd\tname", level="full", root_commits=("x", "y")
    )
    config_module.save(config)
    again = config_module.load(config.path)
    assert list(again.repositories) == ['root:a"b\\c']
    assert again.repositories['root:a"b\\c'].name == "odd\tname"
    assert again.repositories['root:a"b\\c'].root_commits == ("x", "y")
