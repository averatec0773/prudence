"""The backend for a machine with no model. It refuses, and says what to do instead.

Every feature that uses a model is optional: a review is complete without a segment
(design-for-change rule 10) and `prudence ask --no-model` prints the evidence. So the
absence of a model is a normal state, not a broken install, and this class exists so
that the message a user sees is written once rather than at each call site.
"""

from __future__ import annotations

from prudence.model.base import Completion, ModelUnavailable, Request

REASON = (
    "no model configured; set ANTHROPIC_API_KEY or run `prudence config model "
    "--backend anthropic`. Everything else works without one: `prudence review` writes "
    "the whole page from computed numbers, and `prudence ask --no-model` prints the "
    "evidence tables."
)


class NoModel:
    """A `Model` that never completes. `id` is printed in the "what was sent" line."""

    id = "none"
    caches_system_prompt = False

    def __init__(self, reason: str = REASON) -> None:
        self.reason = reason

    def complete(self, request: Request) -> Completion:
        raise ModelUnavailable(self.reason)
