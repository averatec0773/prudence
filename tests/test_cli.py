from click.testing import CliRunner

from prudence.cli import main


def test_status_exits_ok_and_prints_prudence() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["status"])

    assert result.exit_code == 0
    assert "prudence" in result.output
