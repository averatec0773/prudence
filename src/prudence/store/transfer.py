"""Export and import: the whole store as one file you can read without Prudence.

The format is deliberately the dullest thing that works: a gzip-compressed tar holding
`manifest.json`, a copy of `config.toml`, and one JSON Lines file per table, one object
per row keyed by column name. A user can untar it and read every recorded fact with
`less`; a future version can read it without this code existing, which is the point of
an export that is also a backup.

The archive tables are left out unless asked for, because they are the bulk (the
founder's store is 1.6 GB of agent data against a few megabytes of derived rows) and
because they hold the unmodified transcripts, which is the one part of the store that
should not be copied around without a decision. With `--archive` they are included and
the compressed chunks are base64-encoded, since JSON has no bytes.

Import is deliberately narrow: into an empty store only. Merging two stores means
deciding what happens when the same session id carries different rows under different
parser versions, which is a real design question and not one to answer by accident, so
`--merge` refuses and says so.
"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import tarfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from prudence import __version__
from prudence.facts import registry as facts_registry
from prudence.store import (
    attribution,
    commits,
    db,
    derived,
    edits,
    observations,
    outcomes,
    repos,
    rewritten,
    spool,
)

MANIFEST = "manifest.json"
CONFIG_MEMBER = "config.toml"
TABLE_DIR = "tables"
FORMAT_VERSION = 1

# Derived and harvested tables, in an order an import can follow without care.
DERIVED_TABLES = derived.TABLES + (
    "hook_event",
    facts_registry.TABLE,
    facts_registry.LABEL_TABLE,
)
HARVESTED_TABLES = (
    "repository",
    "commit",
    "commit_line",
    "attribution",
    "commit_alias",
    "line_fate",
    "observation",
)
ARCHIVE_TABLES = ("archive_file", "archive_chunk")

BLOB_COLUMNS = {("archive_chunk", "data")}


@dataclass
class TransferStats:
    path: Path | None = None
    tables: dict[str, int] = field(default_factory=dict)
    bytes_written: int = 0
    with_archive: bool = False
    elapsed: float = 0.0

    @property
    def rows(self) -> int:
        return sum(self.tables.values())


class Refused(RuntimeError):
    """The store is not in a state where this transfer is safe. Nothing was changed."""


def versions() -> dict[str, int]:
    """Every version constant that produced a row in this store, for the manifest."""
    return {
        "format": FORMAT_VERSION,
        "archive_schema": db.ARCHIVE_SCHEMA_VERSION,
        "parser": derived.PARSER_VERSION,
        "edit_fact": edits.EDIT_FACT_VERSION,
        "command_fact": edits.COMMAND_FACT_VERSION,
        "repository_fact": repos.FACT_VERSION,
        "commit_fact": commits.FACT_VERSION,
        "attribution_fact": attribution.FACT_VERSION,
        "line_fate_fact": outcomes.FACT_VERSION,
        "observation_fact": observations.FACT_VERSION,
        "commit_alias_fact": rewritten.FACT_VERSION,
        "hook_event_fact": spool.FACT_VERSION,
    }


def export(
    connection: sqlite3.Connection,
    target: Path,
    config_path: Path | None = None,
    with_archive: bool = False,
) -> TransferStats:
    """Write the whole store to one `.tar.gz`. Reads only; changes nothing."""
    started = time.monotonic()
    stats = TransferStats(path=target, with_archive=with_archive)
    tables = list(DERIVED_TABLES) + list(HARVESTED_TABLES)
    if with_archive:
        tables += list(ARCHIVE_TABLES)

    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as bundle:
        for table in tables:
            body, count = _dump(connection, table)
            stats.tables[table] = count
            _add(bundle, f"{TABLE_DIR}/{table}.jsonl", body)
        if config_path is not None and config_path.exists():
            _add(bundle, CONFIG_MEMBER, config_path.read_bytes())
        manifest = {
            "prudence": __version__,
            "exported_at": datetime.now(UTC).isoformat(),
            "versions": versions(),
            "with_archive": with_archive,
            "tables": stats.tables,
        }
        _add(bundle, MANIFEST, json.dumps(manifest, indent=2).encode())
    stats.bytes_written = target.stat().st_size
    stats.elapsed = time.monotonic() - started
    return stats


def read_manifest(source: Path) -> dict:
    with tarfile.open(source, "r:gz") as bundle:
        handle = bundle.extractfile(MANIFEST)
        if handle is None:
            raise Refused(f"{source} carries no {MANIFEST}; it is not a Prudence export.")
        return json.loads(handle.read())


def import_bundle(
    connection: sqlite3.Connection,
    source: Path,
    config_path: Path | None = None,
    merge: bool = False,
) -> TransferStats:
    """Restore an export into an empty store. Refuses anything else."""
    started = time.monotonic()
    if merge:
        raise Refused(
            "--merge is not implemented. Merging two stores has to decide what happens when "
            "the same session carries rows from two parser versions, and guessing that would "
            "be worse than refusing. Import into an empty data directory instead "
            "(PRUDENCE_DATA_DIR=... prudence import FILE)."
        )
    if not source.is_file():
        raise Refused(f"{source} does not exist.")
    manifest = read_manifest(source)
    ensure_tables(connection)
    occupied = _occupied(connection)
    if occupied:
        detail = ", ".join(f"{table} {count}" for table, count in sorted(occupied.items()))
        raise Refused(
            f"This store already holds rows ({detail}). Import only into an empty data "
            "directory, so an import can never half-overwrite a record."
        )

    stats = TransferStats(path=source, with_archive=bool(manifest.get("with_archive")))
    with tarfile.open(source, "r:gz") as bundle:
        # One transaction for the whole restore. The connection is in autocommit mode,
        # which would otherwise make each of half a million rows its own transaction and
        # its own fsync: 46 s against 3 s measured on the founder's store.
        connection.execute("BEGIN")
        try:
            for member in bundle.getmembers():
                if not member.name.startswith(f"{TABLE_DIR}/"):
                    continue
                if not member.name.endswith(".jsonl"):
                    continue
                table = Path(member.name).stem
                handle = bundle.extractfile(member)
                if handle is None:
                    continue
                stats.tables[table] = _load(connection, table, handle.read())
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        if config_path is not None and not config_path.exists():
            try:
                config = bundle.extractfile(CONFIG_MEMBER)
            except KeyError:
                config = None
            if config is not None:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_bytes(config.read())
    stats.elapsed = time.monotonic() - started
    return stats


def ensure_tables(connection: sqlite3.Connection) -> None:
    """Create every table an export can carry, without touching one that already exists."""
    connection.executescript(db.ARCHIVE_SCHEMA)
    for table in derived.TABLES:
        statement = derived.SCHEMA[table].format(name=table)
        connection.execute(statement.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
    connection.execute(spool.SCHEMA.format(name=spool.TABLE))
    for schema, name in (
        (facts_registry.SCHEMA, facts_registry.TABLE),
        (facts_registry.LABEL_SCHEMA, facts_registry.LABEL_TABLE),
    ):
        connection.execute(
            schema.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1).format(name=name)
        )
    connection.execute(repos.SCHEMA)
    connection.executescript(commits.SCHEMA)
    connection.executescript(attribution.SCHEMA)
    connection.executescript(rewritten.SCHEMA)
    connection.executescript(outcomes.SCHEMA)
    connection.executescript(observations.SCHEMA)


def _occupied(connection: sqlite3.Connection) -> dict[str, int]:
    counted: dict[str, int] = {}
    for table in list(DERIVED_TABLES) + list(HARVESTED_TABLES) + list(ARCHIVE_TABLES):
        try:
            count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if count:
            counted[table] = count
    return counted


def _dump(connection: sqlite3.Connection, table: str) -> tuple[bytes, int]:
    """One table as JSON Lines, one object per row, keyed by column name."""
    buffer = io.BytesIO()
    count = 0
    try:
        cursor = connection.execute(f'SELECT * FROM "{table}"')
    except sqlite3.OperationalError:
        return b"", 0
    columns = [description[0] for description in cursor.description]
    for row in cursor:
        record = {
            column: _encode(table, column, value)
            for column, value in zip(columns, row, strict=True)
        }
        buffer.write(json.dumps(record, ensure_ascii=False).encode() + b"\n")
        count += 1
    return buffer.getvalue(), count


def _load(connection: sqlite3.Connection, table: str, body: bytes) -> int:
    """Insert a table's rows, batched by their column list so one statement covers many.

    Every row of one export has the same columns, but an export written by another
    version need not, so the batch is keyed on the column tuple rather than assumed.
    """
    batches: dict[tuple[str, ...], list[list]] = {}
    count = 0
    for line in body.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        columns = tuple(record)
        values = [_decode(table, column, record[column]) for column in columns]
        batches.setdefault(columns, []).append(values)
        count += 1
    for columns, rows in batches.items():
        marks = ", ".join("?" * len(columns))
        names = ", ".join(f'"{column}"' for column in columns)
        connection.executemany(f'INSERT OR IGNORE INTO "{table}" ({names}) VALUES ({marks})', rows)
    return count


def _encode(table: str, column: str, value: object) -> object:
    if (table, column) in BLOB_COLUMNS and isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return value


def _decode(table: str, column: str, value: object) -> object:
    if (table, column) in BLOB_COLUMNS and isinstance(value, str):
        return base64.b64decode(value)
    return value


def _add(bundle: tarfile.TarFile, name: str, body: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(body)
    info.mtime = int(time.time())
    info.mode = 0o600
    bundle.addfile(info, io.BytesIO(body))
