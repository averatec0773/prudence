"""A command's run, in the run log: the one place a click command meets `store/runlog.py`.

`with recorded() as run:` around the body of a command writes the start line, lets the
body add its steps (or attach a pipeline result), and writes the end line with the exit
code the command is about to leave with, however it leaves: returning, `ctx.exit(n)`, a
`ClickException`, Ctrl-C or anything else raised. What it cannot see is a process killed
outright, and that is the point of the start line: such a run stays in the log with no
end, and `prudence logs` shows it as interrupted.

The command and its arguments are read back from click's parsed parameters rather than
from `sys.argv`, which inside a test or a host process is somebody else's.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import click

from prudence.store import runlog


@contextmanager
def recorded() -> Iterator[runlog.Run]:
    """Record the current command from here to wherever it leaves."""
    run = runlog.start(command_line(click.get_current_context()))
    try:
        yield run
    except click.exceptions.Exit as done:
        runlog.finish(run, done.exit_code)
        raise
    except click.ClickException as error:
        runlog.finish(run, error.exit_code, error)
        raise
    except KeyboardInterrupt as error:
        runlog.finish(run, 130, error)
        raise
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
        runlog.finish(run, code, error if code else None)
        raise
    except BaseException as error:
        runlog.finish(run, 1, error)
        raise
    runlog.finish(run, 0)


def command_line(ctx: click.Context) -> list[str]:
    """`["ingest", "--strict", "--workers", "7"]`: the subcommands, then every option set."""
    names: list[str] = []
    node: click.Context | None = ctx
    while node is not None and node.parent is not None:
        names.append(node.info_name or "")
        node = node.parent
    words = names[::-1]
    for parameter in ctx.command.params:
        value = ctx.params.get(parameter.name or "")
        if isinstance(parameter, click.Argument):
            words.extend(str(item) for item in _values(value))
            continue
        if not isinstance(parameter, click.Option) or value is None:
            continue
        if parameter.is_flag and isinstance(value, bool):
            if value and parameter.opts:
                words.append(parameter.opts[0])
            elif not value and parameter.secondary_opts:
                words.append(parameter.secondary_opts[0])
            continue
        for item in _values(value) if parameter.multiple else [value]:
            words.extend([parameter.opts[0], str(item)])
    return words


def _values(value: object) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, list | tuple) else [value]
