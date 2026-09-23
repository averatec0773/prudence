"""Reading archived files into events, several at a time, in the order they are asked for.

The expensive part of a parse is per file and independent of every other file:
decompressing the archived chunks, splitting them into lines and letting the source
adapter turn each line into an `Event`. What the events mean (who owns a record, which
turn a reply belongs to) depends on every file read before, so that part stays in the
main process, in one order (`store/derived.py`). This module does the first part and
nothing else: it never writes to the store, and it hands the files back in exactly the
order they were asked for, so the fold cannot tell whether one process read them or
eight.

`workers=1` reads in the calling process, with no pool at all. Anything more starts a
pool of that many processes with the `spawn` start method, which is the only one every
platform has: nothing here relies on a child inheriting the parent's memory, so a worker
opens its own read-only connection to the database file and asks the adapter registry
for its own adapter. `spawn` starts each worker by importing the calling program's main
module, so a script that parses with more than one worker must keep its work under
`if __name__ == "__main__":`; the `prudence` console script does.

At most `LOOKAHEAD` files per worker are read ahead of the one the fold is on, because a
worker that runs ahead of a slow fold would otherwise hold every file's events in memory
at once.
"""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
from collections import deque
from collections.abc import Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from prudence import sources
from prudence.sources import base
from prudence.store import archive

# Files read ahead of the fold, per worker.
LOOKAHEAD = 2

# The default pool: every core but one, so the machine stays usable, and never more than
# this many, past which the fold in the main process is the bottleneck anyway.
MAX_DEFAULT_WORKERS = 8


@dataclass(frozen=True)
class FileTask:
    """One archived file to read, and what the adapter needs to know about it."""

    path: str
    session_id: str
    agent_id: str | None
    sidecar: str | None


def default_workers() -> int:
    """Cores minus one, at least one, at most `MAX_DEFAULT_WORKERS`."""
    return max(1, min((os.cpu_count() or 2) - 1, MAX_DEFAULT_WORKERS))


def read_all(
    database: Path, tasks: list[FileTask], workers: int, kind: str = sources.DEFAULT_KIND
) -> Iterator[list[base.Event]]:
    """Each task's events, in task order, read by `workers` processes."""
    if workers <= 1 or len(tasks) <= 1:
        connection = _open(database)
        try:
            for task in tasks:
                yield _events(connection, task, kind)
        finally:
            connection.close()
        return
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=context,
        initializer=_start_worker,
        initargs=(str(database), kind),
    ) as pool:
        pending: deque[Future] = deque()
        queue = iter(tasks)
        for task in queue:
            pending.append(pool.submit(_read_in_worker, task))
            if len(pending) >= workers * LOOKAHEAD:
                break
        while pending:
            events = pending.popleft().result()
            following = next(queue, None)
            if following is not None:
                pending.append(pool.submit(_read_in_worker, following))
            yield events


def _open(database: Path) -> sqlite3.Connection:
    """A read-only connection: a worker must not be able to write to the store."""
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _events(connection: sqlite3.Connection, task: FileTask, kind: str) -> list[base.Event]:
    adapter = sources.source(kind)
    lines = archive.iter_lines(connection, task.path)
    sidecar = archive.read_file(connection, task.sidecar) if task.sidecar else None
    return list(adapter.events(lines, task.path, task.session_id, task.agent_id, sidecar))


# One connection per worker process, opened by the pool's initializer.
_worker: dict[str, object] = {}


def _start_worker(database: str, kind: str) -> None:
    _worker["connection"] = _open(Path(database))
    _worker["kind"] = kind


def _read_in_worker(task: FileTask) -> list[base.Event]:
    connection = _worker["connection"]
    assert isinstance(connection, sqlite3.Connection)
    kind = _worker["kind"]
    assert isinstance(kind, str)
    return _events(connection, task, kind)
