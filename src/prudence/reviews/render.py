"""One stored review as Markdown. Layout only; not one number is computed here.

The rendering reads the `sections` JSON and prints the texts the build already wrote,
so the page and the stored numbers list can never disagree: every figure in the file is
a `text` from that list, and a test asserts it.

Plain pipe tables, because the two readers are a terminal and a text file, and because
a table the founder can copy into a spreadsheet is worth more than alignment. Principle
3 decides one thing about the layout: the coverage sits in the same row as every
outcome figure, never a section away.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from prudence.reviews import schema


def render(row: sqlite3.Row) -> str:
    """The whole review: its heading, its sections, and what the words mean."""
    payload = schema.sections_of(row)
    window = payload.get("window") or {}
    lines = [f"# Review {row['id']}: {_scope(row, payload)}", ""]
    lines.append(
        f"Range {_day(row['range_start'])} to {_day(row['range_end'])}"
        f"{_source(window)}. Outcomes are the commits made between "
        f"{_day(row['outcome_range_start'])} and {_day(row['outcome_range_end'])}, which is "
        "every commit whose seven-day mark fell inside that range."
    )
    lines.append("")
    lines.append(
        f"Written {_day(row['created_at'])} at line_fate fact version {row['fact_version']}, "
        f"parser version {row['parser_version']}."
    )

    for section in payload.get("sections", []):
        lines.extend(_section(section))

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"Every figure above is computed from your own record: {len(payload.get('numbers', []))} "
        "numbers, each re-derivable with `prudence usage`, `prudence outcomes` or "
        "`prudence observations` over the same range. Nothing above this line was written "
        "by a model."
    )
    lines.extend(_segment(row))
    return "\n".join(lines)


def _segment(row: sqlite3.Row) -> list[str]:
    """The optional model segment, last, under its own heading and its own credit line.

    Last on purpose: a reader reaches it having already seen every number it may use,
    and a review that stops before it is still a whole review (rule 10).
    """
    segment = schema.segment_of(row)
    if segment is None:
        return []
    return [
        "",
        "## What this means",
        "",
        str(segment["text"]).strip(),
        "",
        f"Written by {segment['model']}; every number checked against the review's "
        f"{len(segment['numbers'])} numbers.",
    ]


def headline(row: sqlite3.Row) -> str:
    """One line for a dropdown or a hint: the scope, the range and what was found."""
    payload = schema.sections_of(row)
    observations = 0
    for section in payload.get("sections", []):
        if section.get("key") == "observations":
            observations = len(section.get("rows") or [])
    return (
        f"Review {row['id']} for {_day(row['range_start'])} to {_day(row['range_end'])}"
        f" ({_scope(row, payload)}): {observations} observations."
    )


def _section(section: dict[str, Any]) -> list[str]:
    lines = ["", f"## {section.get('title') or section.get('key')}", ""]
    headers = section.get("headers") or []
    rows = section.get("rows") or []
    notes = section.get("notes") or []
    if headers and rows:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in rows:
            lines.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
        lines.append("")
        lines.extend(notes)
        return lines
    # A section with nothing to show says what it looked at first, then that it found
    # nothing there: the other order reads as a failure rather than as an empty window.
    lines.extend(notes)
    if section.get("empty"):
        if notes:
            lines.append("")
        lines.append(section["empty"])
    return lines


def _cell(value: Any) -> str:
    """A cell, with the pipe escaped so one sentence cannot break the table."""
    return str(value).replace("|", "\\|")


def _scope(row: sqlite3.Row, payload: dict[str, Any]) -> str:
    name = payload.get("project_name") or row["project"]
    return name or "every project"


def _source(window: dict[str, Any]) -> str:
    source = window.get("source")
    return f" ({source})" if source else ""


def _day(value: str | None) -> str:
    return (value or "")[:10] or "?"
