"""US dollars per million tokens, per model id. Used for the estimate line and nothing else.

A price is not a fact about the user's work: it ages, it is published by somebody else,
and it is wrong the day after a change. So it lives here as a dated table with its own
version, is never stored on a row, and every figure computed from it is called an
estimate in the text the user reads. When a model id is not in the table the estimate is
`None` and the line says the cost is unknown rather than guessing one.

Matching is by longest prefix, so a dated snapshot (`claude-haiku-4-5-20251001`) is
priced by its family (`claude-haiku-4-5`) without a row of its own.
"""

from __future__ import annotations

# Bump when a price changes, so a reader can tell which table a printed estimate used.
PRICE_VERSION = 1
PRICED_AT = "2026-06-24"

# model id prefix -> (input $/1M, output $/1M, cache read $/1M)
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5": (10.00, 50.00, 1.00),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-opus-4-7": (5.00, 25.00, 0.50),
    "claude-opus-4-6": (5.00, 25.00, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}


def rates(model_id: str) -> tuple[float, float, float] | None:
    """The three rates for a model id, matched by the longest prefix, or None."""
    best: str | None = None
    for prefix in PRICES:
        if model_id.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return PRICES[best] if best else None


def cost(
    model_id: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> float | None:
    """What one call cost, or None when the model id is not in the table."""
    found = rates(model_id)
    if found is None:
        return None
    per_input, per_output, per_cached = found
    return (
        input_tokens * per_input + output_tokens * per_output + cached_tokens * per_cached
    ) / 1_000_000


def estimate(model_id: str, request_bytes: int, max_tokens: int) -> float | None:
    """A cost estimate before the call, from the request size and the output cap.

    Four bytes to the token is the rough English ratio; the output side assumes the
    model uses its whole cap, which makes the estimate an upper bound rather than a
    number that turns out too low once the bill arrives.
    """
    found = rates(model_id)
    if found is None:
        return None
    per_input, per_output, _ = found
    return (request_bytes / 4 * per_input + max_tokens * per_output) / 1_000_000
