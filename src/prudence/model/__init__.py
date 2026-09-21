"""Which model runs, chosen in one place from settings rather than at each call site.

A backend is a file in this package and a name in `BACKENDS`; adding one is a new file
and one line of the table below, never a branch inside a command (design-for-change: a
new backend is a new file). `select_model` is the only function a surface calls, so the
rule about what happens when no key is set is written once and is the same everywhere.

The order of precedence is the order a person expects: the environment beats the config,
because `PRUDENCE_MODEL=recorded` and `PRUDENCE_MODEL=none` are how a test and a
cautious user turn the vendor off for one command without editing a file.

Nothing here reads a key. `AnthropicModel` does that, and only to hand it to the SDK.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prudence.model.base import (
    Completion,
    Model,
    ModelFailed,
    ModelUnavailable,
    Request,
    Sent,
)
from prudence.model.guard import Verdict, complete_checked, judge
from prudence.model.language import CODES as LANGUAGES
from prudence.model.language import DEFAULT as DEFAULT_LANGUAGE
from prudence.model.language import LANGUAGE_VERSION
from prudence.model.language import SYSTEM as SYSTEM_LANGUAGE
from prudence.model.language import resolve as resolve_language
from prudence.model.none import NoModel
from prudence.model.numbers import check_numbers, numbers_in
from prudence.model.tone import TONE_VERSION, check_tone

BACKEND_ENV = "PRUDENCE_MODEL"
FIXTURES_ENV = "PRUDENCE_MODEL_FIXTURES"

ANTHROPIC = "anthropic"
NONE = "none"
RECORDED = "recorded"

# The two a user may set in config. `recorded` is deliberately not one of them: it is a
# replay of something already paid for and belongs to a test or a `PRUDENCE_MODEL` run,
# not to a machine's standing configuration.
BACKENDS = (ANTHROPIC, NONE)
ALL_BACKENDS = (ANTHROPIC, NONE, RECORDED)

__all__ = [
    "ALL_BACKENDS",
    "ANTHROPIC",
    "BACKENDS",
    "BACKEND_ENV",
    "DEFAULT_LANGUAGE",
    "FIXTURES_ENV",
    "LANGUAGES",
    "LANGUAGE_VERSION",
    "NONE",
    "RECORDED",
    "SYSTEM_LANGUAGE",
    "TONE_VERSION",
    "Completion",
    "Model",
    "ModelFailed",
    "ModelUnavailable",
    "NoModel",
    "Request",
    "Sent",
    "Verdict",
    "check_numbers",
    "check_tone",
    "complete_checked",
    "judge",
    "numbers_in",
    "resolve_language",
    "select_model",
]


def select_model(config: Any = None, model_id: str | None = None) -> Model:
    """The model this machine should use, or a `NoModel` that says why there is none.

    `model_id` is the per-command override (`--model-id`), which beats the config so the
    founder can send one review to a cheaper model without changing anything.
    """
    settings = getattr(config, "model", None)
    backend = (os.environ.get(BACKEND_ENV) or getattr(settings, "backend", ANTHROPIC)).strip()
    chosen = model_id or getattr(settings, "model_id", None)

    if backend == RECORDED:
        from prudence.model.recorded import RecordedModel

        directory = os.environ.get(FIXTURES_ENV)
        if not directory:
            return NoModel(
                f"{BACKEND_ENV}=recorded needs {FIXTURES_ENV} pointing at a directory of "
                "recorded completions."
            )
        # Only an explicit `--model-id` renames a replay. The config's `model_id` is the
        # default for the vendor backend, and using it here would make a replay claim to
        # be a model that was never called.
        return RecordedModel(Path(directory), model_id=model_id or RECORDED)

    if backend == NONE:
        return NoModel()

    if backend != ANTHROPIC:
        return NoModel(
            f"unknown model backend {backend!r}; use one of {', '.join(BACKENDS)}. "
            "Run `prudence config model --backend anthropic` to set it."
        )

    from prudence.model.anthropic_backend import (
        DEFAULT_KEY_ENV,
        DEFAULT_MODEL_ID,
        AnthropicModel,
    )

    variable = getattr(settings, "api_key_env", None) or DEFAULT_KEY_ENV
    key = os.environ.get(variable)
    if not key:
        return NoModel(
            f"no model configured; set {variable} or run `prudence config model`. "
            "Everything else works without one: `prudence review` writes the whole page "
            "from computed numbers, and `prudence ask --no-model` prints the evidence."
        )
    try:
        return AnthropicModel(model_id=chosen or DEFAULT_MODEL_ID, api_key=key)
    except ModelUnavailable as error:
        return NoModel(str(error))
