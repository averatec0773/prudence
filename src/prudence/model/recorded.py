"""A model that replays recorded answers from disk, keyed by a hash of what was sent.

Tests must be able to exercise the whole path (prompt, call, number check, storage,
rendering) without a network and without a key, and a fixture keyed by the input hash
makes that possible without a mock: the same prompt always yields the same text, and a
prompt that changed by one word no longer finds its fixture, which is exactly the
failure a test should see when a prompt is edited without its fixture.

It is also a real backend, not a test double: `PRUDENCE_MODEL=recorded` runs it, which
is how the founder replays a stored answer without spending anything.

A fixture is one JSON file named `<hash>.json`, holding at least `text`; `model`,
`input_tokens` and `output_tokens` are optional and default to something plausible.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prudence.model.base import Completion, ModelFailed, Request

SUFFIX = ".json"


def input_hash(request: Request) -> str:
    """The identity of one prompt: its system text and its user text, nothing else.

    The cap and the receipt are left out on purpose. They describe how the call is made
    and what the user was told, not what the model was asked, so changing the cap must
    not orphan every fixture.
    """
    digest = hashlib.sha256()
    digest.update(request.system.encode())
    digest.update(b"\n--\n")
    digest.update(request.user.encode())
    return digest.hexdigest()[:16]


class RecordedModel:
    """Replays `<directory>/<input hash>.json`. Never touches the network."""

    id = "recorded"
    caches_system_prompt = False

    def __init__(self, directory: Path, model_id: str = "recorded") -> None:
        self.directory = Path(directory)
        self.id = model_id

    def complete(self, request: Request) -> Completion:
        key = input_hash(request)
        path = self.directory / f"{key}{SUFFIX}"
        if not path.is_file():
            known = sorted(p.name for p in self.directory.glob(f"*{SUFFIX}"))
            raise ModelFailed(
                f"No recorded completion for input hash {key} in {self.directory}. "
                f"Recorded: {', '.join(known) or 'none'}. A prompt that changed needs its "
                "fixture re-recorded."
            )
        payload = json.loads(path.read_text())
        return Completion(
            text=str(payload.get("text", "")),
            model=str(payload.get("model", self.id)),
            input_tokens=int(payload.get("input_tokens", 0)),
            output_tokens=int(payload.get("output_tokens", 0)),
            cached_tokens=int(payload.get("cached_tokens", 0)),
            cost=payload.get("cost"),
            latency=float(payload.get("latency", 0.0)),
        )

    def record(self, request: Request, completion: Completion) -> Path:
        """Write a fixture for this request. Used to make a recording, never at runtime."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{input_hash(request)}{SUFFIX}"
        path.write_text(
            json.dumps(
                {
                    "text": completion.text,
                    "model": completion.model,
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        return path
