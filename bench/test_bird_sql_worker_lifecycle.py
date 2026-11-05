"""Pure event traces, not real resource absence/retirement evidence."""

from dataclasses import FrozenInstanceError, replace
import importlib
import importlib.util
import itertools
from uuid import uuid4

import pytest


@pytest.fixture
def api():
    assert importlib.util.find_spec("ptc.bird_sql_worker_lifecycle") is not None, "lifecycle API required"
    return importlib.import_module("ptc.bird_sql_worker_lifecycle")


def event(api, state, kind, **kwargs):
    kwargs.setdefault("operation_id", uuid4().hex)
    return api.WorkerEvent(state.owner_id, state.resource_name, api.EventKind(kind), **kwargs)


def send(api, state, kind, **kwargs):
    return api.transition_worker(state, event(api, state, kind, **kwargs))


def observe(api, state, effect, success=True, absent=None):
    return send(api, state, "OBSERVATION", operation_id=effect.operation_id,
                success=success, absent=absent)


def initial(api):
    state = api.new_worker_state(owner_id="owner-a", resource_name="toy-a")
    assert state.phase == "NEW"
    transition = send(api, state, "BEGIN")
    assert transition.state.resource_name == "toy-a"
    assert transition.state.phase == "CREATING"
    assert [e.kind.value for e in transition.effects] == ["CREATE"]
    return transition


def assert_not_closed(state):
    assert state.phase != "CLOSED", "unresolved operation must retain ownership"


def finish_retirement(api, transition):
    assert [e.kind.value for e in transition.effects] == ["REMOVE"]
    removed = observe(api, transition.state, transition.effects[0])
    assert [e.kind.value for e in removed.effects] == ["VERIFY_ABSENT"]
    assert_not_closed(removed.state)
    verified = observe(api, removed.state, removed.effects[0], absent=True)
    assert verified.state.phase == "CLOSED"
    assert verified.state.resource_name == "toy-a"
    assert verified.effects == ()
    return verified


@pytest.mark.parametrize("reason", ["CANCEL", "TIMEOUT", "CLOSE"])
@pytest.mark.parametrize("create_success", [True, False])
def test_09_pending_create_retained(api, reason, create_success):
    creating = initial(api)
    cancelled = send(api, creating.state, reason)
    assert_not_closed(cancelled.state)
    assert cancelled.effects == ()
    for _ in range(3):
        repeat = send(api, cancelled.state, reason)
        assert repeat.state == cancelled.state and repeat.effects == ()
    late = observe(api, cancelled.state, creating.effects[0], success=create_success)
    assert all(e.kind.value != "START" for e in late.effects)
    finish_retirement(api, late)


def test_09_failed_create_requires_remove_and_absence(api):
    creating = initial(api)
    failed = observe(api, creating.state, creating.effects[0], success=False)
    assert_not_closed(failed.state)
    finish_retirement(api, failed)


@pytest.mark.parametrize("reason", ["CANCEL", "TIMEOUT", "CLOSE"])
@pytest.mark.parametrize("start_success", [True, False])
@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_09_start_and_drain_join_before_remove(api, reason, start_success, order):
    creating = initial(api)
    created = observe(api, creating.state, creating.effects[0])
    assert created.state.phase == "CREATED"
    starting = send(api, created.state, "START")
    assert [e.kind.value for e in starting.effects] == ["START", "DRAIN"]
    cancelled = send(api, starting.state, reason)
    assert_not_closed(cancelled.state)
    state = cancelled.state
    for index in order:
        effect = starting.effects[index]
        joined = observe(api, state, effect,
                         success=start_success if effect.kind.value == "START" else True)
        state = joined.state
        if index == order[0]:
            assert_not_closed(state)
            assert joined.effects == ()
        assert all(e.kind.value != "START" for e in joined.effects)
    finish_retirement(api, joined)


def test_09_created_cancel_never_starts(api):
    creating = initial(api)
    created = observe(api, creating.state, creating.effects[0])
    retiring = send(api, created.state, "CANCEL")
    for kind in ("START", "BEGIN", "CANCEL", "CLOSE", "TIMEOUT"):
        repeated = send(api, retiring.state, kind)
        assert repeated.effects == ()
        assert repeated.state == retiring.state
    finish_retirement(api, retiring)


def test_09_running_failed_start_drain_and_retirement_uncertainty(api):
    for start_success in (True, False):
        creating = initial(api)
        created = observe(api, creating.state, creating.effects[0])
        starting = send(api, created.state, "START")
        started = observe(api, starting.state, starting.effects[0], success=start_success)
        assert started.state.phase == ("RUNNING" if start_success else "RETIRING")
        cancelled = send(api, started.state, "CLOSE")
        drained = observe(api, cancelled.state, starting.effects[1], success=False)
        assert [e.kind.value for e in drained.effects] == ["REMOVE"]
        failed_remove = observe(api, drained.state, drained.effects[0], success=False)
        assert_not_closed(failed_remove.state)
        assert failed_remove.effects == ()
        removed = observe(api, drained.state, drained.effects[0])
        uncertain = observe(api, removed.state, removed.effects[0], absent=False)
        assert_not_closed(uncertain.state)
        assert uncertain.effects == ()
        # A duplicate later success cannot rewrite a settled uncertain observation.
        late = observe(api, uncertain.state, removed.effects[0], absent=True)
        assert late.state == uncertain.state and late.effects == ()


def test_09_foreign_stale_duplicate_observations(api):
    creating = initial(api)
    state, effect = creating.state, creating.effects[0]
    base = event(api, state, "OBSERVATION", operation_id=effect.operation_id, success=True)
    for foreign in (
        replace(base, owner_id="other"), replace(base, resource_name="other"),
        replace(base, operation_id="unknown"), replace(base, operation_id=None),
    ):
        out = api.transition_worker(state, foreign)
        assert out.state == state and out.effects == ()
    created = observe(api, state, effect)
    duplicate = observe(api, created.state, effect)
    assert duplicate.state == created.state and duplicate.effects == ()
    assert effect.owner_id == state.owner_id and effect.resource_name == state.resource_name
    with pytest.raises(FrozenInstanceError):
        state.phase = "CLOSED"
    # Even reusing the same owner/name cannot accept an old generation's receipt.
    fresh = initial(api)
    stale = observe(api, fresh.state, effect)
    assert stale.state == fresh.state and stale.effects == ()
    assert fresh.effects[0].operation_id != effect.operation_id


def test_09_cancel_new_and_terminal_repetition(api):
    state = api.new_worker_state(owner_id="owner-a", resource_name="toy-a")
    closed = send(api, state, "CANCEL")
    assert closed.state.phase == "CLOSED" and closed.effects == ()
    for kind in ("BEGIN", "START", "CANCEL", "TIMEOUT", "CLOSE"):
        out = send(api, closed.state, kind)
        assert out.state == closed.state and out.effects == ()


def test_09_bounded_state_trace_permutations(api):
    # 24 permutations, revoke/late-create/duplicate/start intents. Zero START
    # dispatches after revoke and zero premature CLOSED in every trace.
    for intents in itertools.permutations(("CANCEL", "LATE", "START", "CLOSE")):
        creating = initial(api)
        state = creating.state
        revoked = False
        seen_create = False
        dispatched = [creating.effects[0]]
        for intent in intents:
            if intent == "LATE":
                out = observe(api, state, creating.effects[0])
                seen_create = True
            else:
                out = send(api, state, intent)
                revoked = revoked or intent in ("CANCEL", "CLOSE")
            if revoked:
                assert all(e.kind.value != "START" for e in out.effects)
            state = out.state
            dispatched.extend(out.effects)
            if not seen_create or state.pending:
                assert_not_closed(state)
        ids = [e.operation_id for e in dispatched]
        assert len(ids) == len(set(ids))
