"""`--progress`: what a client watching an ingest is told, and when.

Two levels. The pipeline is run with a recording callback, which is where the promises
about the sequence live: every step in order, a total before the work, a counter that
only goes up, and a last event that has arrived. Then the command, which only has to put
those events on stderr as JSON without disturbing the summary on stdout.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from conftest import Workspace, record_one_session

from prudence import config as config_module
from prudence.cli import main
from prudence.store import db, pipeline
from prudence.store import progress as progress_module


def _record(workspace: Workspace, with_archive: bool) -> list[progress_module.Event]:
    record_one_session(workspace)
    events: list[progress_module.Event] = []
    connection = db.connect()
    try:
        pipeline.run(
            connection, config_module.load(), with_archive=with_archive, progress=events.append
        )
    finally:
        connection.close()
    return events


def _in_order(events: list[progress_module.Event]) -> list[str]:
    """Each step once, in the order its first event arrived."""
    order: list[str] = []
    for event in events:
        if not order or order[-1] != event.step:
            order.append(event.step)
    return order


def test_an_ingest_reports_all_eleven_steps_in_pipeline_order(lab: Workspace) -> None:
    events = _record(lab, with_archive=True)

    assert _in_order(events) == list(pipeline.STEPS)
    assert {event.steps for event in events} == {11}


def test_a_rebuild_reports_ten_steps_and_never_the_archive(lab: Workspace) -> None:
    """The archive is the one step a rebuild skips, so it is not one of its ten."""
    events = _record(lab, with_archive=False)

    assert _in_order(events) == [name for name in pipeline.STEPS if name != pipeline.ARCHIVE]
    assert {event.steps for event in events} == {10}
    assert pipeline.ARCHIVE not in {event.step for event in events}


def test_every_step_knows_its_total_first_and_reaches_it_last(lab: Workspace) -> None:
    """The promise a progress bar rests on: a total up front and a counter that only rises."""
    events = _record(lab, with_archive=True)

    for index, name in enumerate(pipeline.STEPS, start=1):
        readings = [event for event in events if event.step == name]
        assert readings, name
        assert readings[0].total is not None, f"{name} counted its targets before starting"
        assert readings[0].current == 0, name
        currents = [event.current for event in readings]
        assert currents == sorted(currents), name
        assert readings[-1].current == readings[-1].total, name
        assert {event.step_index for event in readings} == {index}, name
        assert all(event.unit and event.label for event in readings), name


def test_a_step_that_raises_never_says_it_finished() -> None:
    """`done` is the step's own word for having got there; a step that died has not."""
    seen: list[progress_module.Event] = []
    run = progress_module.Run(seen.append, pipeline.STEPS, pipeline.LABELS)
    try:
        with run.step("parse") as step:
            step.start(4, "sessions")
            step.advance()
            raise RuntimeError("the parser died")
    except RuntimeError:
        pass

    assert [event.current for event in seen] == [0], "only the start reached the client"


def test_ingest_progress_is_json_on_stderr_and_leaves_stdout_alone(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()

    plain = runner.invoke(main, ["ingest", "--json"])
    watched = runner.invoke(main, ["ingest", "--json", "--progress"])

    assert plain.exit_code == 0, plain.output
    assert watched.exit_code == 0, watched.output
    assert plain.stderr == "", "without --progress stderr stays silent"
    assert json.loads(plain.stdout).keys() == json.loads(watched.stdout).keys()

    events = [json.loads(line) for line in watched.stderr.splitlines()]
    assert events, "something was reported"
    assert {event["event"] for event in events} == {"progress"}
    assert {event["step"] for event in events} == set(pipeline.STEPS)
    assert {event["steps"] for event in events} == {11}
    assert set(events[0]) == {
        "event",
        "step",
        "step_index",
        "steps",
        "current",
        "total",
        "unit",
        "label",
    }


def test_rebuild_reports_the_same_way(lab: Workspace) -> None:
    record_one_session(lab)

    watched = CliRunner().invoke(main, ["rebuild", "--progress"])

    assert watched.exit_code == 0, watched.output
    events = [json.loads(line) for line in watched.stderr.splitlines()]
    assert {event["steps"] for event in events} == {10}
    assert "Rebuilt at parser version" in watched.stdout
