"""The one path from a command to a model, so that "what was sent" is never skipped.

Three commands call a model (`review --explain`, `explain`, `ask`). Each of them has to
print the receipt before the call, turn an unavailable backend into a readable message
rather than a traceback, and print what the answer cost afterwards. Writing that three
times would mean three chances to forget the receipt, so it is written here and the
commands call `run`.

The receipt is printed before the request is made, not after. A user who does not want
the call to happen can read the line and press Ctrl-C, which they cannot do if the
sentence arrives with the answer.
"""

from __future__ import annotations

import click

from prudence.model import (
    Completion,
    Model,
    ModelFailed,
    ModelUnavailable,
    Request,
    prices,
    select_model,
)


def choose(config: object, model_id: str | None = None) -> Model:
    """The model for this command: the `--model-id` override over the config over the env."""
    return select_model(config, model_id=model_id)


def announce(model: Model, request: Request) -> str:
    """The line printed before every model call, with the pre-call cost estimate."""
    return request.sent.line(
        model.id,
        prices.estimate(model.id, request.size, request.max_tokens),
        max_tokens=request.max_tokens,
        caching=getattr(model, "caches_system_prompt", False),
    )


def run(model: Model, request: Request, echo: bool = True) -> Completion:
    """Print the receipt, make the call, print what it cost. Raises a click error on failure."""
    if echo:
        click.echo(announce(model, request))
    try:
        completion = model.complete(request)
    except ModelUnavailable as error:
        raise click.ClickException(str(error)) from error
    except ModelFailed as error:
        raise click.ClickException(str(error)) from error
    if echo:
        click.echo(completion.receipt())
    return completion
