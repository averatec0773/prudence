"""Which turn a subagent's work belongs to: the turn whose call dispatched it.

A turn is one prompt of the person and everything done because of it. A subagent's
replies are done because of the tool call that started the agent, which sits in the
parent's transcript (or, for an agent started by another agent, in that agent's log),
in whichever turn was open when the call was made. Its records do carry a prompt id of
their own, but that is the parent's current turn at the moment each record was written,
and it moves on whenever the person types again while an agent runs in the background:
on the founder's store 3,445 subagent replies (544M tokens) landed on a later turn by
that link. So the prompt id is only the fallback here.

The links, in the order they are trusted:

1. the call that started the agent, named by the file the agent keeps beside its log
   (`Event.dispatch_id`), else by the agent id the call's own result reports
   (`ToolResult.started_agent`);
2. each later call that handed the running agent more work (`ToolCall.sends_to_agent`),
   which moves the replies written after it to that call's turn;
3. the prompt id on the agent's own record.

A record takes the latest of the linking calls made at or before it, or the earliest one
when it predates them all (clocks in two files can disagree by a moment). This module
knows no agent's format: it is handed ids and times by `store/derived.py`, which
resolves a session's subagent records here once every file of the session has been read,
because the call and the reply are in different files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# Why a subagent's replies could not be placed by a call, for the run log's
# `unattached_subagent` warning: nothing named a dispatching call, a call was named and is
# in none of the session's files, or the calls found are themselves in no turn.
NO_CALL_NAMED = "no_dispatching_call_named"
CALL_NOT_FOUND = "dispatching_call_not_found"
CALL_WITHOUT_TURN = "dispatching_call_has_no_turn"


@dataclass(frozen=True)
class Link:
    """What a subagent's record needs to find its turn once the whole session is read.

    `agent_id` is the agent whose log it is in, `at` the record's own time, and
    `prompt_id` the prompt id the record carries, the fallback when no call is found.
    """

    agent_id: str
    at: str | None
    prompt_id: str | None


@dataclass(frozen=True)
class Call:
    """A tool call as the resolution sees it: when it was made and where it sits.

    Exactly one of `turn_id` (a call in the session's own transcript) and `link` (a call
    in a subagent's log, whose turn is that agent's) is set.
    """

    at: str | None
    turn_id: str | None
    link: Link | None


class AgentTurns:
    """The turn of every subagent record in one session, from the calls that linked it."""

    def __init__(
        self,
        calls: Mapping[str, Call],
        dispatched_by_sidecar: Mapping[str, str],
        dispatched_by_result: Mapping[str, str],
        sends: Mapping[str, Sequence[str]],
    ) -> None:
        self._calls = calls
        self._dispatch = {**dispatched_by_result, **dispatched_by_sidecar}
        self._sends = sends
        # Agent id -> (time, turn) of every call that linked it, oldest first. None while
        # it is being worked out, which is what stops an agent that (impossibly) started
        # itself from recursing for ever.
        self._timelines: dict[str, list[tuple[str, str]] | None] = {}

    def turn_of(self, link: Link) -> str | None:
        """The turn one subagent record belongs to, or None when nothing links it."""
        timeline = self._timeline(link.agent_id)
        if not timeline:
            return link.prompt_id
        at = link.at or ""
        chosen = timeline[0][1]
        for when, turn_id in timeline:
            if when <= at:
                chosen = turn_id
        return chosen

    def _timeline(self, agent_id: str) -> list[tuple[str, str]]:
        if agent_id in self._timelines:
            return self._timelines[agent_id] or []
        self._timelines[agent_id] = None
        linking = [self._dispatch.get(agent_id), *self._sends.get(agent_id, ())]
        found = []
        for call_id in linking:
            call = self._calls.get(call_id) if call_id else None
            if call is None:
                continue
            turn_id = call.turn_id if call.link is None else self.turn_of(call.link)
            if turn_id is not None:
                found.append((call.at or "", turn_id))
        found.sort()
        self._timelines[agent_id] = found
        return found

    def unattached(self, agent_ids: Iterable[str]) -> list[tuple[str, str]]:
        """The agents among `agent_ids` that no call placed, each with the reason.

        Their records fell back to the prompt id they carry (`turn_of`), which is the
        link the module docstring says is not to be trusted, so each is worth a warning.
        """
        found = []
        for agent_id in sorted(set(agent_ids)):
            if self._timeline(agent_id):
                continue
            named = [self._dispatch.get(agent_id), *self._sends.get(agent_id, ())]
            named = [call_id for call_id in named if call_id]
            if not named:
                reason = NO_CALL_NAMED
            elif not any(call_id in self._calls for call_id in named):
                reason = CALL_NOT_FOUND
            else:
                reason = CALL_WITHOUT_TURN
            found.append((agent_id, reason))
        return found
