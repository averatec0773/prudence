"""`prudence suggestions`: the rows a review left open, and the two words about them.

Principle 4: a suggestion is never an order, and an ignored one stops repeating.
`dismiss` is how a user says no once and is not asked again; `take` is how they say
they are trying it, so the next review's follow-up has a date to compare across.
"""

from __future__ import annotations

import sqlite3

import click

from prudence.paths import database_file
from prudence.reviews import schema
from prudence.store import db


@click.group(invoke_without_command=True)
@click.pass_context
def suggestions(context: click.Context) -> None:
    """List the open suggestions, or take or dismiss one."""
    if context.invoked_subcommand is None:
        context.invoke(list_suggestions)


@suggestions.command("list")
@click.option("--all", "everything", is_flag=True, help="Include taken, dismissed and expired.")
def list_suggestions(everything: bool = False) -> None:
    """Show the suggestions, open ones by default."""
    connection = _connect()
    try:
        rows = schema.all_suggestions(connection) if everything else _open(connection)
        click.echo(render(rows, everything))
    finally:
        connection.close()


@suggestions.command("dismiss")
@click.argument("suggestion_id", type=int)
def dismiss(suggestion_id: int) -> None:
    """Say no to one suggestion. It is not raised again."""
    _move(suggestion_id, schema.DISMISSED, "dismissed; it will not be raised again")


@suggestions.command("take")
@click.argument("suggestion_id", type=int)
def take(suggestion_id: int) -> None:
    """Say you are trying one, so the next review can follow it up."""
    _move(suggestion_id, schema.TAKEN, "taken; the next review will say whether anything moved")


def render(rows: list[sqlite3.Row], everything: bool = False) -> str:
    """The table, or one sentence when there is nothing to show."""
    if not rows:
        return (
            "No suggestion yet. Run `prudence review`; suggestions come from the observations "
            "it finds."
        )
    lines = [f"{'id':>4} {'status':<10} {'review':>6} {'made':<11} what the data showed"]
    for row in rows:
        lines.append(
            f"{row['id']:>4} {row['status']:<10} {row['review_id']:>6} "
            f"{(row['created_at'] or '')[:10]:<11} {row['text']}"
        )
    lines.append("")
    lines.append(
        "A suggestion is an observation that cleared the sample and gap floors, kept as a row "
        "so the next review can say whether anything moved. `prudence suggestions dismiss <id>` "
        "says no once and for all; `take <id>` says you are trying it."
    )
    if not everything:
        lines.append("Open ones only; add --all for the taken, dismissed and expired.")
    return "\n".join(lines)


def _open(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return schema.open_suggestions(connection)


def _connect() -> sqlite3.Connection:
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    return db.connect()


def _move(suggestion_id: int, status: str, said: str) -> None:
    connection = _connect()
    try:
        row = schema.suggestion_by_id(connection, suggestion_id)
        if row is None:
            raise click.UsageError(f"There is no suggestion {suggestion_id}.")
        schema.set_status(connection, suggestion_id, status, schema.now_text())
        click.echo(f"Suggestion {suggestion_id} {said}.")
    finally:
        connection.close()
