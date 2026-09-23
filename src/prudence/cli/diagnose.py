"""`prudence diagnose`: everything an agent needs to find a problem, in one folder.

The founder does not read logs; an agent does, on this machine or another one. This
command gathers what the `diagnose` skill reads first into `<data dir>/diagnose/<time>/`
(or under `--out`): the last run records, `status --json`, the config, the machine, the
tail of the app's log and a README saying what is there. Every text in it goes through
`runlog.strip_user`, so paths name `~` rather than the user.

What it never holds is the record itself: no transcript, no archived byte, no row of the
store. The config and the app's log are the only files it copies, and a file it would
copy that is the store, the hook spool or anything under the agent's own directory is
refused (`refuse_archive`), whatever a path setting says.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import click

from prudence import __version__
from prudence.cli import status as status_command
from prudence.paths import (
    app_log_file,
    claude_config_dir,
    config_file,
    data_dir,
    database_file,
    diagnose_dir,
    spool_file,
)
from prudence.store import buckets, derived, meta, runlog

# Run records the bundle carries, newest last.
RECORDS = 20
# Lines of the app's log the bundle carries, from its end.
APP_LOG_LINES = 500

README = """\
A Prudence diagnose bundle, written by `prudence diagnose` at {written}.

runs.jsonl    the last {records} run records of `prudence logs --json`, oldest first:
              command, versions, machine, per-step seconds and counts, warnings, self-checks,
              error and exit code for each ingest, rebuild, review, init, hooks, export, import
status.json   `prudence status --json`: counts, versions and the last ingest and rebuild
config.toml   the config, with the home directory written as ~ {config_note}
machine.txt   operating system, architecture, Python, cores and the engine's versions
app.log       the last {app_lines} lines of the desktop app's log {app_note}

No transcript text is present: the run log holds counts, ids, names, keys, offsets and
timings only, and nothing here was read from the archive or from the agent's own files.
"""


class Refused(click.ClickException):
    """A file the bundle would have copied is part of the record."""


@click.command()
@click.option(
    "--out",
    "parent",
    type=click.Path(file_okay=False, path_type=Path),
    help="Where to write the bundle's folder. Defaults to <data dir>/diagnose.",
)
def diagnose(parent: Path | None) -> None:
    """Write a folder of logs, status and config for an agent to diagnose a problem."""
    written = datetime.now(UTC)
    target = (parent or diagnose_dir()) / written.strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, exist_ok=False)

    records, _ = runlog.read()
    newest = records[:RECORDS][::-1]
    _write(
        target / "runs.jsonl",
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in newest),
    )
    _write(target / "status.json", json.dumps(status_command.summary(), indent=2) + "\n")
    config = config_file()
    if config.exists():
        _write(target / "config.toml", _copied(config))
    _write(target / "machine.txt", _machine())
    log = app_log_file()
    if log.exists():
        _write(target / "app.log", "".join(_copied(log).splitlines(True)[-APP_LOG_LINES:]))
    _write(
        target / "README",
        README.format(
            written=written.isoformat(timespec="seconds"),
            records=RECORDS,
            app_lines=APP_LOG_LINES,
            config_note="" if config.exists() else "(absent: there is no config yet)",
            app_note="" if log.exists() else "(absent: the app has not written one)",
        ),
    )
    click.echo(runlog.strip_user(str(target)))


def refuse_archive(path: Path) -> None:
    """Raise `Refused` for a file that is the store, the spool or the agent's own record."""
    resolved = path.resolve()
    record = {database_file().resolve(), spool_file().resolve()}
    record |= {Path(f"{database_file()}{suffix}").resolve() for suffix in ("-wal", "-shm")}
    agent = claude_config_dir().resolve()
    if resolved in record or resolved.is_relative_to(agent):
        raise Refused(
            f"{runlog.strip_user(str(path))} is part of the record; a diagnose bundle never "
            "carries the archive or the agent's files."
        )


def _copied(path: Path) -> str:
    """A file's text for the bundle, refused if it is part of the record."""
    refuse_archive(path)
    return runlog.strip_user(path.read_text(errors="replace"))


def _machine() -> str:
    machine = runlog.machine()
    lines = [f"{key}: {value}" for key, value in machine.items()]
    lines += [
        f"engine_version: {__version__}",
        f"parser_version: {derived.PARSER_VERSION}",
        f"bucket_rule_version: {buckets.BUCKET_RULE_VERSION}",
        f"app_contract_version: {meta.APP_CONTRACT_VERSION}",
        f"data_dir: {runlog.strip_user(str(data_dir()))}",
        f"store_bytes: {runlog.store_bytes()}",
    ]
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    """One file of the bundle, readable by its owner alone like the rest of the data."""
    path.write_text(runlog.strip_user(text))
    os.chmod(path, 0o600)
