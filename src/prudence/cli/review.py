"""`prudence review`: the store turned into a page, stored as a row first.

The command is thin on purpose. It resolves the range, asks the readiness rule whether
another review is worth writing, calls `reviews.build` for the sections, stores the row,
opens the suggestions that row leaves behind, and prints the Markdown rendering. Every
figure was computed by `store/views` before this file ran; nothing here does arithmetic.

The page is printed and also written to `reports/review-<id>.md`, because a review is
something a person comes back to and a terminal scrollback is not (journey decision E1,
now the secondary rendering of the stored row).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import click

from prudence.cli.observations import repo_key_for
from prudence.paths import database_file, reports_dir
from prudence.reviews import build as build_module
from prudence.reviews import ranges, readiness, render, schema
from prudence.reviews import suggestions as suggestions_module
from prudence.store import db, derived, views
from prudence.store import outcomes as outcomes_module


@click.command()
@click.option("--last", "last", metavar="7d|14d|2w", help="How far back the range reaches.")
@click.option("--since", "since", metavar="YYYY-MM-DD", help="The first day of the range.")
@click.option("--until", "until", metavar="YYYY-MM-DD", help="The day the range stops before.")
@click.option("--month", "month", metavar="YYYY-MM", help="One calendar month.")
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
@click.option("--force", is_flag=True, help="Write the review even when the rule says wait.")
@click.option("--json", "as_json", is_flag=True, help="The stored row as JSON, not Markdown.")
def review(
    last: str | None,
    since: str | None,
    until: str | None,
    month: str | None,
    project: str | None,
    force: bool,
    as_json: bool,
) -> None:
    """Write a review of one range: what you did, what became of it, and what changed."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = repo_key_for(connection, project)
        try:
            window = ranges.resolve(
                connection,
                last=last,
                since=since,
                until=until,
                month=month,
                project=repo_key,
            )
        except ranges.Unreadable as error:
            raise ranges.option_error(error) from error

        names = views.repository_names(connection)
        ready = readiness.readiness(
            connection, repo_key, name=names.get(repo_key) if repo_key else None
        )
        if not ready.ready and not force:
            if as_json:
                click.echo(json.dumps({"ready": False, "reason": ready.reason}, indent=2))
            else:
                click.echo(ready.reason)
                click.echo("Run `prudence review --force` to write one anyway.")
            return

        for line in write(connection, window, as_json=as_json, forced=force and not ready.ready):
            click.echo(line)
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def write(
    connection: sqlite3.Connection,
    window: ranges.Window,
    as_json: bool = False,
    forced: bool = False,
    now: datetime | None = None,
) -> list[str]:
    """Compute, store and render one review. Returns the lines the command prints."""
    moment = now or datetime.now(UTC)
    created_at = schema.now_text(moment)
    payload = build_module.build(connection, window, now=moment)
    review_id = schema.insert_review(
        connection,
        created_at=created_at,
        range_start=window.start,
        range_end=window.end,
        project=window.project,
        outcome_range_start=window.outcome_start,
        outcome_range_end=window.outcome_end,
        sections=payload,
        coverage=build_module.coverage_of(payload),
        fact_version=outcomes_module.FACT_VERSION,
        parser_version=derived.PARSER_VERSION,
    )
    stats = suggestions_module.refresh(connection, review_id, window.project, created_at)
    row = schema.review_by_id(connection, review_id)
    if row is None:
        raise click.ClickException("The review row was not stored; nothing was written.")

    text = render.render(row)
    path = reports_dir() / f"review-{review_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")

    if as_json:
        return [
            json.dumps(
                {
                    "id": review_id,
                    "created_at": created_at,
                    "project": window.project,
                    "range_start": window.start,
                    "range_end": window.end,
                    "outcome_range_start": window.outcome_start,
                    "outcome_range_end": window.outcome_end,
                    "coverage": row["coverage"],
                    "report": str(path),
                    "suggestions": {
                        "opened": stats.opened,
                        "kept": stats.kept,
                        "expired": stats.expired,
                    },
                    **payload,
                },
                indent=2,
                ensure_ascii=False,
            )
        ]
    lines = [text, "", f"Written to {path}."]
    if stats.opened or stats.expired:
        lines.append(
            f"{stats.opened} suggestions opened, {stats.kept} still open from before, "
            f"{stats.expired} expired; see `prudence suggestions`."
        )
    if forced:
        lines.append(
            "Written with --force: the readiness rule said there was not enough new work yet."
        )
    return lines
