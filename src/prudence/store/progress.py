"""How far along an ingest is, in a shape a client can draw a bar from.

`prudence ingest --progress` writes one of these events per line to stderr and nothing
else there; a menu bar or a desktop app reads them while the ingest runs. The rule that
makes them worth reading is that a step counts its targets before it works through any
of them, so `total` is on the step's very first event and a bar never has to guess.

Nothing under `store/` prints. The pipeline hands each step one `Step` from here, the
step says what it is about to do (`start`) and then says when each unit begins
(`advance`), and this module alone decides how often that reaches the client
(`INTERVAL`) and what the event looks like on the wire. A step that nobody is listening
to gets a silent `Step` rather than `None`, so the counting code is the same either way.

`advance` is called as a unit begins, not when it ends, which is what lets a loop with a
`continue` in it stay counted and what makes `label` name the work in flight. `current`
therefore reaches `total` only on the step's last event, which `Step.done` emits.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

# How much elapsed work may pass between two events of one step, in seconds.
INTERVAL = 0.25


@dataclass(frozen=True)
class Event:
    """One reading of one step: where the pipeline is, and what it is working on."""

    step: str
    step_index: int
    steps: int
    current: int
    total: int | None
    unit: str
    label: str

    def as_dict(self) -> dict:
        """The wire shape, in the order a reader expects to find it."""
        return {
            "event": "progress",
            "step": self.step,
            "step_index": self.step_index,
            "steps": self.steps,
            "current": self.current,
            "total": self.total,
            "unit": self.unit,
            "label": self.label,
        }


Sink = Callable[[Event], None]


class Step:
    """One step's counter. Emits at the start, every `INTERVAL` of work, and at the end."""

    def __init__(
        self,
        sink: Sink | None,
        name: str = "",
        index: int = 0,
        steps: int = 0,
        label: str = "",
    ) -> None:
        self._sink = sink
        self._name = name
        self._index = index
        self._steps = steps
        self._label = label or name
        self._unit = "steps"
        self._total: int | None = None
        self._current = 0
        self._last = 0.0

    def start(self, total: int | None, unit: str, label: str | None = None) -> None:
        """Say what there is to work through, before working through any of it.

        `total` is `None` only where a step genuinely cannot count its targets ahead of
        time; every step in `store/pipeline.py` can, so none of them passes `None`.
        """
        self._total = total
        self._unit = unit
        if label:
            self._label = label
        self._current = 0
        self._emit()

    def advance(self, count: int = 1, label: str | None = None) -> None:
        """One more unit begins. Reaches the client at most every `INTERVAL` seconds."""
        self._current += count
        if label:
            self._label = label
        if time.monotonic() - self._last >= INTERVAL:
            self._emit()

    def at(self, label: str) -> None:
        """Same position, new label: a step whose one unit is several minutes of work.

        `outcomes` follows a whole repository as one unit and spends a minute inside it,
        so without this a client would watch nothing move. The counter stays honest,
        because a phase of a unit is not a unit.
        """
        self._label = label
        if time.monotonic() - self._last >= INTERVAL:
            self._emit()

    def done(self) -> None:
        """The step's last event, with `current` at the total it announced."""
        if self._total is not None:
            self._current = self._total
        self._emit()

    def _emit(self) -> None:
        if self._sink is None:
            return
        self._last = time.monotonic()
        self._sink(
            Event(
                step=self._name,
                step_index=self._index,
                steps=self._steps,
                current=self._current,
                total=self._total,
                unit=self._unit,
                label=self._label,
            )
        )


class Run:
    """The steps of one pipeline run, numbered as the client will number them.

    `steps` is the run's own list, so a `rebuild` that skips the archive reports ten
    steps numbered one to ten rather than eleven with a hole in the middle. `elapsed`
    holds each finished step's wall-clock seconds, for `prudence status` to show later,
    and is the caller's own dictionary when it passes one, so that it is there to read
    even when a step raises. `current` is the step in progress, None between steps.
    """

    def __init__(
        self,
        sink: Sink | None,
        steps: tuple[str, ...],
        labels: dict[str, str] | None = None,
        elapsed: dict[str, float] | None = None,
    ) -> None:
        self._sink = sink
        self._steps = steps
        self._labels = labels or {}
        self.elapsed: dict[str, float] = elapsed if elapsed is not None else {}
        self.current: str | None = None

    @contextmanager
    def step(self, name: str) -> Iterator[Step]:
        """The handle for one step, which reports it finished when the body returns.

        A step that raises does not emit its last event, because it did not get there.
        """
        handle = Step(
            self._sink,
            name=name,
            index=self._steps.index(name) + 1,
            steps=len(self._steps),
            label=self._labels.get(name, name),
        )
        started = time.monotonic()
        self.current = name
        yield handle
        handle.done()
        self.elapsed[name] = round(time.monotonic() - started, 3)
        self.current = None


def silent() -> Step:
    """A counter nobody is listening to, for a step called outside the pipeline."""
    return Step(None)
