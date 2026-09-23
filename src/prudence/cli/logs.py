"""`prudence logs`: the run log, one line per run, newest first.

The log itself is `store/runlog.py`'s; this command only reads it. A line says when the
run started, what was run, how long it took or that it never finished, what the parse
read, and how many warnings, failed self-checks and which error it ended with, so the
line that is wrong can be quoted without opening the file. `--json` prints the records.
"""

from __future__ import annotations

import json
from datetime import datetime

import click

from prudence.store import runlog


@click.command()
@click.option("--last", "last", type=click.IntRange(min=1), help="Only the newest N runs.")
@click.option("--json", "as_json", is_flag=True, help="Print the records as JSON.")
@click.option(
    "--interrupted",
    "only_interrupted",
    is_flag=True,
    help="Only the runs that started and never finished.",
)
def logs(last: int | None, as_json: bool, only_interrupted: bool) -> None:
    """Show what each ingest, rebuild, review and other change did."""
    records, unreadable = runlog.read()
    if only_interrupted:
        records = [record for record in records if runlog.state(record) == runlog.INTERRUPTED]
    if last is not None:
        records = records[:last]
    if as_json:
        click.echo(json.dumps(records, indent=2, ensure_ascii=False))
        return
    if not records:
        click.echo("No runs recorded yet." if not only_interrupted else "No interrupted runs.")
    for record in records:
        click.echo(line(record))
    if unreadable:
        click.echo(f"{unreadable} lines of the log could not be read and were left out.")


def line(record: dict) -> str:
    """One run as one line."""
    state = runlog.state(record)
    if state in (runlog.RUNNING, runlog.INTERRUPTED):
        took = state
    else:
        took = f"{record.get('seconds') or 0:.1f} s"
    parts = [_local(record.get("started_at")), " ".join(record.get("command") or []), took]
    parse = next((step for step in record.get("steps") or [] if step.get("name") == "parse"), None)
    if parse is not None:
        counts = parse.get("counts") or {}
        parsed, skipped = counts.get("files_parsed", 0), counts.get("files_skipped", 0)
        parts.append(f"files {parsed} parsed, {skipped} skipped")
    warnings = sum(entry.get("count", 0) for entry in record.get("warnings") or [])
    failed = sum(1 for check in record.get("checks") or [] if not check.get("passed"))
    parts.append(f"warnings {warnings}")
    parts.append(f"checks failed {failed}")
    error = record.get("error")
    if error:
        parts.append(f"error {error.get('type')}")
    if state == runlog.FAILED:
        parts.append(f"exit {record.get('exit')}")
    return "  ".join(parts)


def _local(stamp: str | None) -> str:
    """A stored UTC time as this machine's local time, to the second."""
    if not stamp:
        return "?"
    return datetime.fromisoformat(stamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
