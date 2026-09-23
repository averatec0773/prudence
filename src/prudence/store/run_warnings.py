"""What a run noticed and kept going past, as data for the run log.

A step that meets something it cannot fully read (a record type it does not know, a line
that is not a record, a subagent nobody dispatched, a tool it can only guess the bucket
of) or a self-check that does not hold says so here, through the one `Warnings` object
the pipeline hands it, and carries on. Nothing here prints: the run log
(`store/runlog.py`) writes the list at the end of the run, and the only line a person
sees during the run is the summary each command already prints.

Every warning is a kind, a count and a sample, and the sample holds shapes only: ids,
names, counts, offsets, timestamps and sorted key lists. A value read from a transcript
never reaches it. The one thing a transcript can put here is a name (a record type, a
key, a tool), and `name` below replaces any that does not look like an identifier, so a
key that happens to be a sentence or a path is written as `<other>`.

Five kinds, each counted once per thing it is about:

- `unknown_record_type`: one per record type the parser does not know, with the records
  of it this run read, the versions that wrote them, the first time one was seen and the
  union of their keys (`sources.base.key_shape`), the first `KEY_LIMIT` of them sorted;
- `unreadable_line`: one per line that is not a record, by session, file id and offset;
- `unattached_subagent`: one per subagent whose replies no dispatching call could place;
- `heuristic_bucket`: one per tool whose calls were bucketed by the name heuristic, with
  the calls and the tokens of the replies whose bucket rests on that guess;
- `check_failed`: one per self-check (`store/checks.py`) that did not hold.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

UNKNOWN_RECORD_TYPE = "unknown_record_type"
UNREADABLE_LINE = "unreadable_line"
UNATTACHED_SUBAGENT = "unattached_subagent"
HEURISTIC_BUCKET = "heuristic_bucket"
CHECK_FAILED = "check_failed"

KINDS = (UNKNOWN_RECORD_TYPE, UNREADABLE_LINE, UNATTACHED_SUBAGENT, HEURISTIC_BUCKET, CHECK_FAILED)

# Items kept in a kind's sample; the count is always of all of them.
SAMPLE_LIMIT = 20
# Keys kept in one record type's key shape. An object keyed by ids rather than by names
# (on the founder's store, one keyed by artifact ids) would otherwise grow without end.
KEY_LIMIT = 64

# What a record type, a key or a tool name may look like to be written as it is.
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:@-]{0,127}$")
OTHER = "<other>"


def name(value: str | None) -> str | None:
    """A name from a transcript as the log may hold it: itself if an identifier, else `<other>`."""
    if value is None:
        return None
    return value if NAME.match(value) else OTHER


def file_id(path: str) -> str:
    """An archived file named without its path, which carries a project directory's name.

    The first 16 hex digits of the path's SHA-256; `archive_file.path` hashed the same way
    finds the file again on the machine that wrote the log.
    """
    return hashlib.sha256(path.encode("utf-8", "surrogatepass")).hexdigest()[:16]


@dataclass
class _UnknownType:
    count: int = 0
    first_seen: str | None = None
    versions: set[str] = field(default_factory=set)
    keys: set[str] = field(default_factory=set)
    shapes: set[tuple[str, ...]] = field(default_factory=set)


class Warnings:
    """Every warning of one run, by kind, in the order they were met."""

    def __init__(self) -> None:
        self._unknown: dict[str, _UnknownType] = {}
        self._items: dict[str, list[dict]] = {kind: [] for kind in KINDS}
        self._heuristic: dict[str, list[int]] = {}

    def unknown_record_type(
        self,
        record_type: str,
        version: str | None,
        count: int,
        first_seen: str | None,
        shapes: set[tuple[str, ...]],
    ) -> None:
        """`count` records of a type the parser does not know, with the key shapes seen."""
        entry = self._unknown.setdefault(name(record_type) or OTHER, _UnknownType())
        entry.count += count
        if first_seen is not None and (entry.first_seen is None or first_seen < entry.first_seen):
            entry.first_seen = first_seen
        if version is not None:
            entry.versions.add(name(version) or OTHER)
        for shape in shapes:
            cleaned = tuple(sorted({_key(key) for key in shape}))
            entry.shapes.add(cleaned)
            entry.keys.update(cleaned)

    def unreadable_line(self, session_id: str | None, path: str, offset: int | None) -> None:
        """One line of an archived file that is not a record."""
        self._items[UNREADABLE_LINE].append(
            {"session": name(session_id), "file": file_id(path), "offset": offset}
        )

    def unattached_subagent(self, agent_id: str, session_id: str, reason: str) -> None:
        """A subagent whose replies no dispatching call placed in a turn, and why."""
        self._items[UNATTACHED_SUBAGENT].append(
            {"agent": name(agent_id), "session": name(session_id), "reason": reason}
        )

    def heuristic_bucket(self, tool_name: str | None, calls: int, tokens: int) -> None:
        """Calls of one tool bucketed by the name heuristic, and the tokens resting on it."""
        entry = self._heuristic.setdefault(name(tool_name) or OTHER, [0, 0])
        entry[0] += calls
        entry[1] += tokens

    def check_failed(self, check: str, numbers: dict) -> None:
        """A self-check that did not hold, with the numbers it compared."""
        self._items[CHECK_FAILED].append({"check": check, "numbers": numbers})

    def as_list(self) -> list[dict]:
        """Each kind that occurred: `{"kind", "count", "sample"}`, in `KINDS` order."""
        found: list[dict] = []
        for kind in KINDS:
            items = self._items_of(kind)
            if items:
                found.append({"kind": kind, "count": len(items), "sample": items[:SAMPLE_LIMIT]})
        return found

    def count(self) -> int:
        """How many warnings there are, of every kind together."""
        return sum(len(self._items_of(kind)) for kind in KINDS)

    def _items_of(self, kind: str) -> list[dict]:
        if kind == UNKNOWN_RECORD_TYPE:
            return [
                {
                    "type": record_type,
                    "count": entry.count,
                    "first_seen": entry.first_seen,
                    "versions": sorted(entry.versions),
                    "key_shape": sorted(entry.keys)[:KEY_LIMIT],
                    "keys": len(entry.keys),
                    "shapes": len(entry.shapes),
                }
                for record_type, entry in sorted(
                    self._unknown.items(), key=lambda item: (-item[1].count, item[0])
                )
            ]
        if kind == HEURISTIC_BUCKET:
            return [
                {"tool": tool, "count": calls, "tokens": tokens}
                for tool, (calls, tokens) in sorted(
                    self._heuristic.items(), key=lambda item: (-item[1][1], item[0])
                )
            ]
        return self._items[kind]


def _key(key: str) -> str:
    """One dotted key path, each part through `name`."""
    return ".".join(name(part) or OTHER for part in key.split("."))
