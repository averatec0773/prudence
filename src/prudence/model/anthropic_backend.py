"""The Anthropic API backend (T6). One file, one vendor, no vendor anywhere else.

Principle 1 says the record depends on no AI vendor. This file is the whole dependency:
the `anthropic` package is an optional extra, nothing outside this module imports it,
and every other backend in the package satisfies the same protocol, so removing this
file removes the vendor without touching a caller.

Five choices worth stating, because each one is a promise to the user rather than a
default:

- **The system prompt is cached.** It is the long, constant half of every call (a prompt
  version, the rules about numbers). Caching it is what makes a second review cheap.
- **`max_tokens` is a cap, not a target.** It bounds the spend of a single call, and the
  cost estimate printed beforehand assumes the model uses all of it.
- **Thinking is off.** The segment is a paraphrase of numbers that were already computed;
  there is nothing to reason about, and a thinking budget would be spend with no product.
- **One retry, on transient failures only.** A 429 or a 5xx is worth trying again; a 400
  or a bad key is not, and retrying it would only hide the message that says what to fix.
- **Text blocks only.** Whatever else a response carries is not the segment.

The key is read from the environment and never printed, never stored on a row and never
written into an error message.
"""

from __future__ import annotations

import os
import time

from prudence.model import prices
from prudence.model.base import Completion, ModelFailed, ModelUnavailable, Request

DEFAULT_MODEL_ID = "claude-sonnet-5"
DEFAULT_KEY_ENV = "ANTHROPIC_API_KEY"
TIMEOUT_SECONDS = 60.0
RETRIES = 1
# `disabled` rather than an absent key: on the models that think by default, omitting
# the parameter buys reasoning nobody asked for and pays for it.
THINKING = {"type": "disabled"}
MINIMUM_SDK = "0.40"


class AnthropicModel:
    """One completion per call, against the Messages API."""

    caches_system_prompt = True

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        api_key: str | None = None,
        timeout: float = TIMEOUT_SECONDS,
        client: object | None = None,
    ) -> None:
        self.id = model_id
        self.timeout = timeout
        self._client = client if client is not None else _client(api_key, timeout)

    def complete(self, request: Request) -> Completion:
        started = time.monotonic()
        response = self._call(self._payload(request))
        text = "\n".join(
            block.text for block in getattr(response, "content", []) if _is_text(block)
        ).strip()
        if not text:
            raise ModelFailed(
                f"{self.id} returned no text (stop reason "
                f"{getattr(response, 'stop_reason', 'unknown')!r}). Nothing was stored."
            )
        usage = getattr(response, "usage", None)
        input_tokens = _count(usage, "input_tokens")
        output_tokens = _count(usage, "output_tokens")
        cached = _count(usage, "cache_read_input_tokens")
        created = _count(usage, "cache_creation_input_tokens")
        return Completion(
            text=text,
            model=str(getattr(response, "model", self.id)),
            input_tokens=input_tokens + created,
            output_tokens=output_tokens,
            cached_tokens=cached,
            cost=prices.cost(self.id, input_tokens + created, output_tokens, cached),
            latency=time.monotonic() - started,
        )

    def _payload(self, request: Request) -> dict:
        """The request body, with the system prompt marked cacheable."""
        return {
            "model": self.id,
            "max_tokens": request.max_tokens,
            "thinking": dict(THINKING),
            "system": [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": request.user}],
        }

    def _call(self, payload: dict):
        """One call, retried once on a failure that may not happen again.

        One extra retry that is not about flakiness: model families disagree about how
        thinking is turned off, and some reject `{"type": "disabled"}` outright. Rather
        than keep a table of which id accepts which spelling (a table that would be
        wrong within a release), the request drops the parameter and goes again. Not
        asking for thinking is the same outcome on every model that defaults to none,
        and the alternative is a command that fails on a model id nobody tested.
        """
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                return self._client.messages.create(**payload)
            except Exception as error:  # noqa: BLE001 - classified immediately below
                if _rejects_thinking(error) and "thinking" in payload:
                    payload = {key: value for key, value in payload.items() if key != "thinking"}
                    continue
                if not _transient(error) or attempt == RETRIES:
                    raise ModelFailed(_message(error)) from error
                last = error
                time.sleep(1.0 + attempt)
        raise ModelFailed(_message(last) if last else "the model call failed")


def _client(api_key: str | None, timeout: float):
    try:
        import anthropic
    except ImportError as error:  # pragma: no cover - exercised by the extra being absent
        raise ModelUnavailable(
            "the `anthropic` package is not installed. Install the extra: "
            f"`pip install 'prudence-core[model]'` (needs anthropic>={MINIMUM_SDK})."
        ) from error
    key = api_key or os.environ.get(DEFAULT_KEY_ENV)
    if not key:
        raise ModelUnavailable(
            f"no API key: {DEFAULT_KEY_ENV} is not set and the config names no other "
            "variable. Set it, or run `prudence config model --backend none`."
        )
    return anthropic.Anthropic(api_key=key, timeout=timeout)


def _is_text(block: object) -> bool:
    return getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str)


def _count(usage: object, name: str) -> int:
    value = getattr(usage, name, 0)
    return int(value) if isinstance(value, int) else 0


def _rejects_thinking(error: Exception) -> bool:
    """A 400 that names the thinking parameter. Anything else is a real error."""
    if getattr(error, "status_code", None) != 400:
        return False
    return "thinking" in str(getattr(error, "message", "") or error).lower()


def _transient(error: Exception) -> bool:
    """A rate limit, a server error or a dropped connection. Anything else is final."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return type(error).__name__ in {"APIConnectionError", "APITimeoutError"}


def _message(error: Exception) -> str:
    """What to tell the user, with nothing from the environment in it.

    The SDK's exception text carries the request body on some errors, which is the
    prompt rather than the key, but this stays a short sentence anyway: a stack trace
    of somebody else's JSON is not an error message.
    """
    status = getattr(error, "status_code", None)
    detail = str(getattr(error, "message", "") or error).strip().splitlines()
    head = detail[0][:200] if detail else type(error).__name__
    where = f"{type(error).__name__}{f', HTTP {status}' if status else ''}"
    return f"the model call failed ({where}): {head}"
