import json

from click.testing import CliRunner
from conftest import Workspace, record_one_session

from prudence.cli import main
from prudence.reviews import readiness
from prudence.store import db

READINESS_KEYS = {
    "ready",
    "new_sessions",
    "required_sessions",
    "matured_commits",
    "required_commits",
    "since",
    "project",
}


def test_status_runs_before_anything_is_enabled() -> None:
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert "No repository is enabled" in result.output


def test_status_json_says_whether_a_review_is_ready_over_all_and_per_project(
    lab: Workspace,
) -> None:
    """Journey decision B's rule, answered once for everything and once per project.

    The counts are the rule's own, not a second count taken here: the numbers are
    compared against `reviews.readiness` itself, and the human line is its very sentence.
    """
    record_one_session(lab)
    runner = CliRunner()

    data = json.loads(runner.invoke(main, ["status", "--json"]).output)["readiness"]
    text = runner.invoke(main, ["status"]).output

    connection = db.connect()
    try:
        verdict = readiness.readiness(connection)
    finally:
        connection.close()

    assert set(data) == READINESS_KEYS | {"projects"}
    assert data["project"] is None
    assert data["ready"] is verdict.ready is False, "one session is not five"
    assert data["new_sessions"] == verdict.new_sessions == 1
    assert data["matured_commits"] == verdict.matured_commits
    assert data["since"] is None, "no review has been written yet"
    assert data["required_sessions"] == readiness.MIN_NEW_SESSIONS
    assert data["required_commits"] == readiness.MIN_MATURED_COMMITS
    assert verdict.reason in text, "the line a person reads is the rule's own words"

    [project] = data["projects"]
    assert set(project) == READINESS_KEYS
    assert project["project"] == lab.repo_key()
    assert project["new_sessions"] == 1


def test_status_json_answers_readiness_before_anything_is_ingested() -> None:
    """A store that does not exist yet is an empty one, not a missing key (rule 3)."""
    data = json.loads(CliRunner().invoke(main, ["status", "--json"]).output)["readiness"]

    assert data["ready"] is False
    assert (data["new_sessions"], data["matured_commits"]) == (0, 0)
    assert data["projects"] == []


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
