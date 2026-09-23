"""`prudence usage`: where the tokens went, by what each response did, by project and by week.

This is the founder's own question from the first conversation, and principle 3 names it
as welcome: factual feedback on the data, including usage broken down by purpose. So the
tables are a breakdown and nothing else. No budget, no target, no judgement about which
bucket deserves the tokens, and no total across buckets pretending to be a score.

The unit is the response of the model, and its bucket is what it did, from its tool calls
alone (`store/buckets.py`): `change` wrote a file, `run` ran something, `read` only
looked, `talk` did neither. A session, a project and a week are sums of responses, so one
session's tokens can sit in all four buckets. This replaced a word per session chosen by
thresholds, which put almost everything under one word and moved whenever a threshold
did.

Three things are kept honest here.

The four token counts are printed separately, because they are not interchangeable: a
cache read is cheap and a cache write is not, and a single total hides which of them a
week was made of. They are shown in thousands, which is the unit the numbers live at.

The tokens that rest on a guess are named: a tool the rule's lists do not know is
bucketed by the words in its name, and a response whose record could not be read is in no
bucket at all. Both totals are printed under the tables, and they are zero when nothing
was guessed or lost.

A dash is not a zero. A response whose Claude Code version wrote no usage fields has no
token counts, and a group made only of such responses prints dashes.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any

import click

from prudence import config as config_module
from prudence.cli.render import thousands
from prudence.paths import database_file
from prudence.store import buckets, db, views

DEFAULT_WINDOW = "30d"

# The order the buckets are printed in: precedence order, so two runs of the same store
# never disagree about the order of two rows.
ORDER = buckets.BUCKETS

TOKEN_COLUMNS = views.TOKEN_COLUMNS


@click.command()
@click.option(
    "--last",
    "window",
    default=DEFAULT_WINDOW,
    show_default=True,
    metavar="7d|30d|90d",
    help="How far back to look, by when each response began.",
)
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
@click.option("--json", "as_json", is_flag=True, help="Print the same numbers as JSON.")
def usage(window: str, project: str | None, as_json: bool) -> None:
    """Show tokens by what each response did (change, run, read, talk), by project and week."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        data = summary(connection, window, repo_key)
        click.echo(json.dumps(data, indent=2) if as_json else render(data))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def summary(connection: sqlite3.Connection, window: str, repo_key: str | None) -> dict[str, Any]:
    """The numbers the three tables are made of, before anything is formatted.

    `render` below turns this into the page and `--json` prints it as it is, so the two
    cannot disagree: there is one query and one set of sums. Token counts stay raw and
    `measured` travels with them, because a group none of whose responses recorded usage
    is a dash rather than a zero and only the caller knows how to draw a dash.
    """
    since = views.resolve_date(window)
    rows = views.bucket_usage(connection, since, repo_key=repo_key)
    names = views.repository_names(connection)

    by_bucket: dict[str, dict[str, float]] = defaultdict(_empty)
    by_project: dict[tuple[str, str], dict[str, float]] = defaultdict(_empty)
    by_week: dict[tuple[str, str], dict[str, float]] = defaultdict(_empty)
    gap = _empty()
    for row in rows:
        cell = {key: float(row[key] or 0) for key in _empty()}
        if row["bucket"] is None:
            _add(gap, cell)
            continue
        project = names.get(row["repo_key"], row["repo_key"] or "unassigned")
        _add(by_bucket[row["bucket"]], cell)
        _add(by_project[(project, row["bucket"])], cell)
        _add(by_week[(_week(row["day"]), row["bucket"])], cell)

    total = _empty()
    for cell in by_bucket.values():
        _add(total, cell)

    return {
        "window": window,
        "since": since,
        "repo_key": repo_key,
        "sessions": views.bucket_sessions(connection, since, repo_key=repo_key),
        "responses": int(total["responses"]),
        "total": _cell(total, total),
        "by_bucket": [
            {"bucket": bucket, **_cell(by_bucket[bucket], total)}
            for bucket in ORDER
            if bucket in by_bucket
        ],
        "by_project": [
            {"project": project, "bucket": bucket, **_cell(cell, total)}
            for (project, bucket), cell in sorted(
                by_project.items(), key=lambda item: (item[0][0], ORDER.index(item[0][1]))
            )
        ],
        "by_week": [
            {"week": week, "bucket": bucket, **_cell(cell, total)}
            for (week, bucket), cell in sorted(
                by_week.items(), key=lambda item: (item[0][0], ORDER.index(item[0][1]))
            )
        ],
        "bucket_rule_version": buckets.BUCKET_RULE_VERSION,
        "heuristic_tokens": int(total["heuristic_tokens"]),
        "coverage_gap_tokens": int(_sum(gap)),
        "notes": _footer(window, total, gap),
    }


def render(data: dict[str, Any]) -> str:
    """The three tables and the footer, from `summary` and nothing else."""
    window = data["window"]
    if not data["responses"]:
        return f"No response of the model in the last {window}."

    lines = [f"tokens by what each response did, last {window}", _header("bucket")]
    for cell in data["by_bucket"]:
        lines.append(_row(cell["bucket"], cell))
    lines.append(_row("all buckets", data["total"]))

    lines.append("")
    lines.append("by project (share of the project's tokens)")
    lines.extend(_pivot("project", data["by_project"], width=22))

    lines.append("")
    lines.append("by week (share of the week's tokens)")
    lines.extend(_pivot("week", data["by_week"], width=10))

    lines.append("")
    lines.extend(data["notes"])
    return "\n".join(lines)


def _pivot(key: str, cells: list[dict[str, Any]], width: int) -> list[str]:
    """One line per project or week: its tokens, then the share each bucket has of them."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for cell in cells:
        grouped.setdefault(cell[key], {})[cell["bucket"]] = cell
    lines = [
        f"{key:<{width}} {'tokens':>9} {'responses':>9} "
        + " ".join(f"{bucket:>7}" for bucket in ORDER)
    ]
    for name, row in grouped.items():
        tokens = sum(cell["total_tokens"] for cell in row.values())
        measured = any(cell["measured"] for cell in row.values())
        responses = sum(cell["responses"] for cell in row.values())
        shares = " ".join(
            f"{_share(row[bucket]['total_tokens'] if bucket in row else 0, tokens):>7}"
            for bucket in ORDER
        )
        total = _k(tokens) if measured else "-"
        lines.append(f"{name[:width]:<{width}} {total:>9} {responses:>9} {shares}")
    return lines


def _cell(cell: dict[str, float], total: dict[str, float]) -> dict[str, Any]:
    """One group's numbers, with the share of the page's total it is."""
    grand = _sum(total)
    return {
        "responses": int(cell["responses"]),
        "measured": int(cell["measured"]),
        **{column: int(cell[column]) for column in TOKEN_COLUMNS},
        "total_tokens": int(_sum(cell)),
        "heuristic_tokens": int(cell["heuristic_tokens"]),
        "share": (_sum(cell) / grand) if grand else None,
    }


def _empty() -> dict[str, float]:
    return {
        "responses": 0.0,
        "measured": 0.0,
        **dict.fromkeys(TOKEN_COLUMNS, 0.0),
        "heuristic_tokens": 0.0,
    }


def _add(totals: dict[str, float], cell: dict[str, float]) -> None:
    for key, value in cell.items():
        totals[key] += value


def _sum(cell: dict[str, float]) -> float:
    return sum(cell[column] for column in TOKEN_COLUMNS)


def _header(first: str) -> str:
    return (
        f"{first:<14} {'responses':>9} {'input':>8} {'output':>8} {'cache rd':>9} {'cache wr':>9} "
        f"{'total':>9} {'share':>6}"
    )


def _row(label: str, cell: dict[str, Any]) -> str:
    """One row. A group none of whose responses recorded usage is dashes, not zeroes."""
    share = "-" if cell["share"] is None else f"{cell['share'] * 100:.0f}%"
    measured = bool(cell["measured"])
    return (
        f"{label:<14} {cell['responses']:>9} "
        + " ".join(
            f"{(_k(cell[column]) if measured else '-'):>{width}}"
            for column, width in zip(TOKEN_COLUMNS, (8, 8, 9, 9), strict=True)
        )
        + f" {(_k(cell['total_tokens']) if measured else '-'):>9} {share:>6}"
    )


def _share(part: float, whole: float) -> str:
    return "-" if not whole else f"{part / whole * 100:.0f}%"


def _k(value: float) -> str:
    """A token count in thousands. A real zero is printed as zero, not as a dash."""
    return thousands(int(round(value)))


def _week(day: str | None) -> str:
    """The ISO week a UTC day falls in, as `2026-W38`."""
    try:
        year, week, _ = date.fromisoformat(day or "").isocalendar()
    except ValueError:
        return "?"
    return f"{year}-W{week:02d}"


def _footer(window: str, total: dict[str, float], gap: dict[str, float]) -> list[str]:
    return [
        f"{int(total['responses'])} responses in the last {window}, by when each began (UTC). "
        "Token counts are in thousands, split into input, output, cache read and cache write "
        "because they do not cost the same; a dash means that Claude Code version wrote no "
        "usage fields, which is not zero tokens.",
        "A response's bucket is what it did, from its tool calls alone (bucket rule version "
        f"{buckets.BUCKET_RULE_VERSION}): change wrote a file, run ran a command or a tool "
        "that acts, read only looked, talk did neither. When a response did several, the first "
        "of change, run, read, talk wins. Nothing in the conversation is read.",
        f"Resting on a guess from a tool's name: {_k(total['heuristic_tokens'])} tokens. "
        f"In responses no bucket could be given (a record that could not be read): "
        f"{_k(_sum(gap))} tokens.",
    ]


def _repo_key(connection: sqlite3.Connection, project: str | None) -> str | None:
    if project is None:
        return None
    resolved = views.repo_key_for(connection, project)
    if resolved is not None:
        return resolved
    repo = config_module.load().find(project)
    if repo is None:
        raise click.UsageError(f"No enabled repository called {project!r}.")
    return repo.key
