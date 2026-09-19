from click.testing import CliRunner

from prudence.cli import main


def test_status_runs_before_anything_is_enabled() -> None:
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert "No repository is enabled" in result.output


def test_init_without_a_terminal_explains_the_non_interactive_form() -> None:
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code == 0, result.output
    assert "--enable" in result.output


def test_ingest_refuses_while_nothing_is_enabled() -> None:
    result = CliRunner().invoke(main, ["ingest"])
    assert result.exit_code != 0
    assert "No repository is enabled" in result.output
