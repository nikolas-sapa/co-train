"""Pure lifecycle intentions/observations, never proof of real Docker absence.

Events must come from a future trusted owner. This reducer does not authenticate
observations, join processes, retire resources or issue ACK/SAFE authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4


class EventKind(str, Enum):
    BEGIN = "BEGIN"
    START = "START"
    CANCEL = "CANCEL"
    TIMEOUT = "TIMEOUT"
    CLOSE = "CLOSE"
    OBSERVATION = "OBSERVATION"


class EffectKind(str, Enum):
    CREATE = "CREATE"
    START = "START"
    DRAIN = "DRAIN"
    REMOVE = "REMOVE"
    VERIFY_ABSENT = "VERIFY_ABSENT"


@dataclass(frozen=True)
class WorkerEvent:
    owner_id: str
    resource_name: str
    kind: EventKind
    operation_id: str
    success: bool | None = None
    absent: bool | None = None


@dataclass(frozen=True)
class WorkerEffect:
    owner_id: str
    resource_name: str
    operation_id: str
    kind: EffectKind


@dataclass(frozen=True)
class WorkerState:
    owner_id: str
    resource_name: str
    generation_id: str
    phase: str = "NEW"
    revoked: bool = False
    sequence: int = 0
    pending: tuple[WorkerEffect, ...] = ()
    resource_possible: bool = False
    retirement_dispatched: bool = False


@dataclass(frozen=True)
class WorkerTransition:
    state: WorkerState
    effects: tuple[WorkerEffect, ...] = ()


def new_worker_state(*, owner_id: str, resource_name: str) -> WorkerState:
    for value in (owner_id, resource_name):
        if type(value) is not str or not value or any(ord(c) < 32 for c in value):
            raise ValueError("nonempty owner and resource identity required")
    return WorkerState(owner_id, resource_name, uuid4().hex)


def _dispatch(state, *kinds):
    effects = tuple(
        WorkerEffect(
            state.owner_id, state.resource_name,
            f"{len(state.owner_id)}:{state.owner_id}:{len(state.resource_name)}:"
            f"{state.resource_name}:{state.generation_id}:{state.sequence + index + 1}", kind,
        ) for index, kind in enumerate(kinds)
    )
    return WorkerTransition(replace(
        state, sequence=state.sequence + len(effects), pending=state.pending + effects,
    ), effects)


def _retire_when_settled(state):
    if state.revoked and not state.pending and not state.retirement_dispatched:
        if not state.resource_possible:
            return WorkerTransition(replace(state, phase="CLOSED"))
        return _dispatch(replace(state, phase="RETIRING", retirement_dispatched=True),
                         EffectKind.REMOVE)
    return WorkerTransition(state)


def transition_worker(state: WorkerState, event: WorkerEvent) -> WorkerTransition:
    """Ignore stale/foreign observations; uncertainty stays RETIRING forever.

    A failed create/start can have effects. Removal only follows settlement of
    create, start and I/O drain; an independent absence observation follows remove.
    Failed/uncertain retirement requires a future owner recovery policy, not a
    repeated cancellation or a late duplicate rewriting the original observation.
    """
    unchanged = WorkerTransition(state)
    if event.owner_id != state.owner_id or event.resource_name != state.resource_name:
        return unchanged
    if state.phase == "CLOSED" or type(event.kind) is not EventKind:
        return unchanged
    if type(event.operation_id) is not str or not event.operation_id:
        return unchanged
    if event.kind in (EventKind.CANCEL, EventKind.TIMEOUT, EventKind.CLOSE):
        if state.revoked:
            return unchanged
        return _retire_when_settled(replace(state, revoked=True, phase="RETIRING"))
    if event.kind is EventKind.BEGIN:
        if state.phase != "NEW" or state.revoked:
            return unchanged
        # Retain name/resource possibility before publishing CREATE.
        return _dispatch(replace(state, phase="CREATING", resource_possible=True),
                         EffectKind.CREATE)
    if event.kind is EventKind.START:
        if state.phase != "CREATED" or state.revoked:
            return unchanged
        return _dispatch(replace(state, phase="STARTING"), EffectKind.START, EffectKind.DRAIN)
    if event.kind is not EventKind.OBSERVATION or type(event.success) is not bool:
        return unchanged
    effect = next((p for p in state.pending if p.operation_id == event.operation_id), None)
    if effect is None:
        return unchanged
    if effect.kind is EffectKind.VERIFY_ABSENT and type(event.absent) is not bool:
        return unchanged
    settled = replace(state, pending=tuple(p for p in state.pending if p != effect))
    if effect.kind is EffectKind.CREATE:
        if event.success and not state.revoked:
            return WorkerTransition(replace(settled, phase="CREATED"))
        settled = replace(settled, revoked=True, phase="RETIRING")
    elif effect.kind is EffectKind.START:
        if event.success and not state.revoked:
            settled = replace(settled, phase="RUNNING")
        else:
            settled = replace(settled, revoked=True, phase="RETIRING")
    elif effect.kind is EffectKind.DRAIN:
        if not event.success:
            settled = replace(settled, revoked=True, phase="RETIRING")
    elif effect.kind is EffectKind.REMOVE:
        if event.success:
            return _dispatch(settled, EffectKind.VERIFY_ABSENT)
        return WorkerTransition(settled)
    elif effect.kind is EffectKind.VERIFY_ABSENT:
        if event.success and event.absent and not settled.pending:
            return WorkerTransition(replace(settled, phase="CLOSED"))
        return WorkerTransition(settled)
    return _retire_when_settled(settled)
