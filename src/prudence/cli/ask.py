"""`prudence ask "<question>"`: the evidence, and then an answer over it.

The order the command prints in is the argument it makes: the evidence tables come
first and the prose comes second, so a reader sees what the answer was built from before
they read it, and `--no-model` is the same output with the last part missing rather than
a different command.

`--with-content` is the only way transcript text reaches a model, it is never on by
default, it is refused for a project not recorded at `full`, and the "Sending" line says
how many excerpts went (principle 1, journey decision D2).
"""

from __future__ import annotations

import json
import sqlite3

import click

from prudence import config as config_module
from prudence.ask import answer as answer_module
from prudence.cli import modelio
from prudence.paths import database_file
from prudence.store import db, views


@click.command()
@click.argument("question", metavar="QUESTION")
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
@click.option("--no-model", "no_model", is_flag=True, help="Print the evidence and stop.")
@click.option(
    "--with-content",
    "with_content",
    is_flag=True,
    help="Also send short transcript excerpts. Full-capture projects only; never by default.",
)
@click.option("--model-id", "model_id", metavar="ID", help="Override the configured model id.")
@click.option("--json", "as_json", is_flag=True, help="The evidence and the answer as JSON.")
def ask(
    question: str,
    project: str | None,
    no_model: bool,
    with_content: bool,
    model_id: str | None,
    as_json: bool,
) -> None:
    """Answer a question about your recent work from the record."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    settings = config_module.load()
    connection = db.connect()
    try:
        model = None if no_model else modelio.choose(settings, model_id)
        try:
            result = answer_module.ask(
                connection,
                question,
                model=model,
                project=project,
                with_content=with_content,
                levels=settings.levels,
                max_tokens=settings.model.max_tokens,
                call=_call,
            )
        except LookupError as error:
            raise click.UsageError(str(error)) from error

        names = views.repository_names(connection)
        question_id = answer_module.store(connection, result, _now())
        if not result.ok:
            # The evidence is printed; the draft is not. It failed the guards twice
            # (once on its own, once after being told exactly what was wrong), which
            # makes it a model's impression carrying figures nobody computed. Showing it
            # under a disclaimer would still leave those figures with the reader, who
            # remembers "about 40%" long after the disclaimer over it.
            click.echo(answer_module.render(result, names, include_answer=False))
            raise click.ClickException(
                "No answer was written, and the text it returned was discarded unread: "
                + "; ".join(result.verdict.reasons())
                + ". The evidence above stands on its own; `prudence ask ... --no-model` "
                "prints it without calling a model at all. The question is stored as "
                f"{question_id} with no answer."
            )

        if as_json:
            click.echo(
                json.dumps(
                    {"id": question_id, **result.as_dict()},
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return
        click.echo(answer_module.render(result, names))
        if result.text is None:
            click.echo("")
            click.echo(
                "No model was called (--no-model). Ask again without it for prose over these rows."
            )
        click.echo("")
        click.echo(f"Stored as question {question_id}; `prudence show --question {question_id}`.")
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def _call(model, request):
    """The receipt, the call, and the cost, exactly as `review --explain` prints them."""
    return modelio.run(model, request)


def _now() -> str:
    from prudence.reviews import schema as review_schema

    return review_schema.now_text()
