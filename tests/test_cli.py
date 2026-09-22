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


def test_menubar_says_where_the_menu_bar_went_and_succeeds() -> None:
    """The rumps prototype is gone; the command that ran it is a signpost, not an error."""
    result = CliRunner().invoke(main, ["menubar"])
    assert result.exit_code == 0, result.output
    assert "replaced by the Prudence desktop app" in result.output
    assert "apps/desktop/README.md" in result.output


def test_nothing_in_the_package_imports_rumps() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "prudence"
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "import rumps" in path.read_text()
    ]
    assert offenders == [], offenders
