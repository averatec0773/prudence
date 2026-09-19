from click.testing import CliRunner

from prudence.cli import main


def test_status_runs() -> None:
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert "prudence" in result.output


def test_init_without_scan_explains() -> None:
    result = CliRunner().invoke(main, ["init"])
    assert result.exit_code != 0
    assert "--scan" in result.output
