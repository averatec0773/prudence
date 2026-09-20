"""Prompts per hour of active time, where active time is the sum of the sittings.

`turn` rows are Prudence's count of prompts (the same one `prudence sessions`' prompts
column shows). Active time is not wall-clock time: a session left open overnight is one
sitting only across its actual bursts of activity, each bounded by the same 60-minute
gap rule as the `sittings` fact, and a burst of one record contributes no duration. A
session with no measurable active time (every burst a single instant, or no records at
all) has no rate to report: NULL, not a division by zero.

Fact version 2 added a floor. Under `MIN_ACTIVE` of measured activity the rate is not a
slow measurement but no measurement: four prompts inside two minutes divides out to 120
an hour, a number that says nothing about how anybody works and everything about the
denominator. Such a session is left unmeasured (NULL), exactly as a session with no
active time at all is, rather than reported as an absurd rate.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from prudence.facts.base import Case, Fact

FACT_VERSION = 2
GAP = timedelta(minutes=60)

# Below this much active time the rate is not measured at all, rather than absurd.
MIN_ACTIVE = timedelta(minutes=10)


def compute(connection: sqlite3.Connection, session_id: str) -> float | None:
    (prompts,) = connection.execute(
        "SELECT COUNT(*) FROM turn WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not prompts:
        return None
    active_seconds = 0.0
    segment_start: datetime | None = None
    previous: datetime | None = None
    for (raw,) in connection.execute(
        "SELECT timestamp FROM record WHERE session_id = ? AND timestamp IS NOT NULL"
        " ORDER BY timestamp",
        (session_id,),
    ):
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if previous is None:
            segment_start = moment
        elif moment - previous > GAP:
            active_seconds += (previous - segment_start).total_seconds()
            segment_start = moment
        previous = moment
    if previous is not None and segment_start is not None:
        active_seconds += (previous - segment_start).total_seconds()
    if active_seconds < MIN_ACTIVE.total_seconds():
        return None
    return prompts / (active_seconds / 3600)


def _record(session_id: str, record_id: str, timestamp: str) -> dict:
    return {"record_id": record_id, "session_id": session_id, "timestamp": timestamp}


def _turn(session_id: str, turn_id: str) -> dict:
    return {"turn_id": turn_id, "session_id": session_id}


CASES = (
    Case(
        name="one 30-minute sitting, three prompts: six an hour",
        session_id="s1",
        expected=6.0,
        rows={
            "record": [
                _record("s1", "r1", "2026-09-15T09:00:00Z"),
                _record("s1", "r2", "2026-09-15T09:30:00Z"),
            ],
            "turn": [_turn("s1", "t1"), _turn("s1", "t2"), _turn("s1", "t3")],
        },
    ),
    Case(
        name="two sittings, four prompts: 45 minutes active in total",
        session_id="s2",
        expected=4 / 0.75,
        rows={
            "record": [
                _record("s2", "r1", "2026-09-15T09:00:00Z"),
                _record("s2", "r2", "2026-09-15T09:30:00Z"),
                _record("s2", "r3", "2026-09-15T11:00:00Z"),
                _record("s2", "r4", "2026-09-15T11:15:00Z"),
            ],
            "turn": [_turn("s2", "t1"), _turn("s2", "t2"), _turn("s2", "t3"), _turn("s2", "t4")],
        },
    ),
    Case(
        name="four prompts in four minutes: under the floor, unmeasured rather than 60 an hour",
        session_id="s5",
        expected=None,
        rows={
            "record": [
                _record("s5", "r1", "2026-09-15T09:00:00Z"),
                _record("s5", "r2", "2026-09-15T09:04:00Z"),
            ],
            "turn": [_turn("s5", "t1"), _turn("s5", "t2"), _turn("s5", "t3"), _turn("s5", "t4")],
        },
    ),
    Case(
        name="exactly ten minutes active: measured, the floor is not exclusive",
        session_id="s6",
        expected=12.0,
        rows={
            "record": [
                _record("s6", "r1", "2026-09-15T09:00:00Z"),
                _record("s6", "r2", "2026-09-15T09:10:00Z"),
            ],
            "turn": [_turn("s6", "t1"), _turn("s6", "t2")],
        },
    ),
    Case(
        name="a single instant has no duration: absent",
        session_id="s3",
        expected=None,
        rows={
            "record": [_record("s3", "r1", "2026-09-15T09:00:00Z")],
            "turn": [_turn("s3", "t1")],
        },
    ),
    Case(name="no prompts at all: absent", session_id="s4", expected=None, rows={}),
)

FACT = Fact(
    name="prompts_per_active_hour",
    version=FACT_VERSION,
    trust="medium",
    compute=compute,
    cases=CASES,
)
