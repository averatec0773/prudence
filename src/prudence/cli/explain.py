"""`prudence explain <id>`: add the model segment to a review that was written without one.

The segment is separable from the review by design (rule 10), which makes this command
possible rather than redundant: a review written last week with no key set, or one whose
first segment was refused for inventing a number, can be given one now without recomputing
a single figure. Nothing is rebuilt; the stored sections JSON is the input.
"""

from __future__ import annotations

import sqlite3

import click

from prudence import config as config_module
from prudence.cli.review import add_segment
from prudence.model import LANGUAGES
from prudence.paths import database_file
from prudence.reviews import render, schema


@click.command()
@click.argument("review_id", type=int, metavar="ID")
@click.option("--model-id", "model_id", metavar="ID", help="Override the configured model id.")
@click.option("--force", is_flag=True, help="Replace a segment this review already has.")
@click.option(
    "--language",
    "language",
    type=click.Choice(LANGUAGES),
    help="Language for the segment only; the page stays English (config: model.language).",
)
def explain(review_id: int, model_id: str | None, force: bool, language: str | None) -> None:
    """Write the "what this means" segment for a review that was stored earlier."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db_connect()
    try:
        row = schema.review_by_id(connection, review_id)
        if row is None:
            known = ", ".join(str(other["id"]) for other in schema.reviews(connection, limit=5))
            raise click.UsageError(
                f"There is no review {review_id}. Stored reviews: {known or 'none yet'}."
            )
        if schema.segment_of(row) is not None and not force:
            raise click.ClickException(
                f"Review {review_id} already has a segment. Pass --force to write another "
                "over it, or read the one it has with `prudence show --review "
                f"{review_id}`."
            )
        payload = schema.sections_of(row)
        if not payload.get("numbers"):
            raise click.ClickException(
                f"Review {review_id} carries no numbers, so there is nothing for a model to "
                "explain."
            )
        created_at = schema.now_text()
        add_segment(
            connection,
            review_id,
            payload,
            config_module.load(),
            model_id,
            created_at,
            language,
        )
        written = schema.review_by_id(connection, review_id)
        if written is not None:
            click.echo("")
            click.echo(render.render(written))
    finally:
        connection.close()


def db_connect() -> sqlite3.Connection:
    from prudence.store import db

    return db.connect()
