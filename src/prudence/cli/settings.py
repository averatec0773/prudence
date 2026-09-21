"""`prudence config`: show and set the settings that are not the consent record.

The repository blocks in `config.toml` are the consent record and are written by `init`
and `forget`; this command owns the rest. So far that is the `[model]` block and the
`[review]` block, and the design constraint is the same for both: a setting is a value in
a file the user can read and edit, and this command is a convenience over that file, never
the only way to change it.

The key is never shown, never written and never asked for. `api_key_env` names an
environment variable; the command says whether that variable is set, and that is as close
to the secret as it goes.
"""

from __future__ import annotations

import os

import click

from prudence import config as config_module
from prudence.model import BACKENDS


@click.group()
def config() -> None:
    """Show and change the settings in `config.toml`."""


@config.command("model")
@click.option(
    "--backend",
    type=click.Choice(BACKENDS),
    help="Which backend writes the optional prose.",
)
@click.option("--model-id", "model_id", metavar="ID", help="The model id to send to.")
@click.option("--key-env", "key_env", metavar="NAME", help="Environment variable holding the key.")
@click.option("--max-tokens", "max_tokens", type=int, help="Cap on one call's output.")
def model(
    backend: str | None,
    model_id: str | None,
    key_env: str | None,
    max_tokens: int | None,
) -> None:
    """Show the model settings, or change them. With no options, shows."""
    current = config_module.load()
    changing = any(value is not None for value in (backend, model_id, key_env, max_tokens))
    if changing:
        current.model = config_module.ModelSettings(
            backend=backend or current.model.backend,
            model_id=model_id or current.model.model_id,
            api_key_env=key_env or current.model.api_key_env,
            max_tokens=max_tokens or current.model.max_tokens,
        )
        config_module.save(current)

    settings = current.model
    variable = settings.api_key_env
    has_key = bool(os.environ.get(variable))
    click.echo(f"backend      {settings.backend}")
    click.echo(f"model id     {settings.model_id}")
    click.echo(f"key variable {variable} ({'set' if has_key else 'not set'})")
    click.echo(f"max tokens   {settings.max_tokens}")
    click.echo(f"explain      {'on' if current.review.explain else 'off'} (review.explain)")
    click.echo(f"written to   {current.path}")
    if settings.backend == "anthropic" and not has_key:
        click.echo(
            f"{variable} is not set, so no model call can be made. Everything else works "
            "without one."
        )
    if not changing:
        click.echo("Change it with `prudence config model --backend ... --model-id ...`.")
