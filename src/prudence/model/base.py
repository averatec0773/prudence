"""What a model is, from the engine's point of view: one call, one answer, one receipt.

The protocol is deliberately one method. Everything Prudence asks a model to do is a
single completion over text the engine already computed: no tools, no conversation, no
state. A backend that needs more than `complete` is doing something the design does not
ask for, and a new backend is a new file in this package rather than a branch inside one.

`Sent` is the receipt. It exists because the user has to be able to see what left their
machine before it leaves, and "trust me" is not a feature (journey decision D2, trust row
of the M3 feature map). Every surface prints `Sent.line(...)` before the call, not after,
so the sentence is a warning rather than a report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# The two shapes of trouble a caller has to tell apart: a backend that cannot run at all
# (no key, no package, nothing configured) and a call that failed once and may not the
# next time. The first is a `ClickException` at the surface; the second is retried once.
class ModelUnavailable(RuntimeError):
    """No model can run. The message says what to do about it, in one sentence."""


class ModelFailed(RuntimeError):
    """The call was made and did not come back with text. Nothing was stored."""


@dataclass(frozen=True)
class Sent:
    """What is about to leave the machine, in the words the user is shown."""

    sections: tuple[str, ...] = ()
    numbers: int = 0
    content: bool = False
    excerpts: int = 0
    bytes: int = 0

    def line(
        self,
        model_id: str,
        estimate: float | None = None,
        max_tokens: int | None = None,
        caching: bool | None = None,
    ) -> str:
        """The one line every surface prints before a model call.

        It describes the whole request, not only its content: what went, how much may
        come back, and whether the long half of it is cached. The cap is what bounds the
        cost of the reply, and the caching flag is why a second review is cheaper than
        the first; a user deciding whether to press on needs both.
        """
        parts = [f"Sending to {model_id}:"]
        parts.append(f"sections {', '.join(self.sections) if self.sections else 'none'};")
        parts.append(f"{self.numbers} numbers;")
        if self.content:
            parts.append(f"{self.excerpts} transcript excerpts;")
        else:
            parts.append("no transcript content;")
        parts.append(f"{_kilobytes(self.bytes)};")
        parts.append(f"at most {max_tokens if max_tokens is not None else '?'} tokens back;")
        if caching is None:
            parts.append("caching unknown.")
        else:
            parts.append("the system prompt is cached." if caching else "no prompt caching.")
        if estimate is not None:
            parts.append(f"Estimated cost: ${estimate:.4f}")
        return " ".join(parts)


@dataclass(frozen=True)
class Request:
    """One completion: a cacheable system prompt, the user text, a cap, and the receipt."""

    system: str
    user: str
    max_tokens: int = 1024
    sent: Sent = field(default_factory=Sent)

    @property
    def size(self) -> int:
        return len(self.system.encode()) + len(self.user.encode())


@dataclass(frozen=True)
class Completion:
    """What came back, and what it cost. `cost` is None when the price is not known."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost: float | None = None
    latency: float = 0.0

    def receipt(self) -> str:
        spend = "cost unknown" if self.cost is None else f"${self.cost:.4f}"
        return (
            f"{self.model}: {self.input_tokens} input tokens "
            f"({self.cached_tokens} from cache), {self.output_tokens} output, "
            f"{self.latency:.1f}s, {spend}."
        )


@runtime_checkable
class Model(Protocol):
    """One call, one answer. Every backend in this package satisfies exactly this.

    `caches_system_prompt` is not an implementation detail: it appears in the line the
    user reads before a call, so it belongs to the protocol rather than to one backend.
    """

    id: str
    caches_system_prompt: bool

    def complete(self, request: Request) -> Completion: ...


def _kilobytes(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    return f"{count / 1024:.1f} KB"
