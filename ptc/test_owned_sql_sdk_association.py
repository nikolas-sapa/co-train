"""COMPOSITION ONLY: live cross-scope PROGRAM-adapter association refusal.

Seven original registered Tasks, one rollout, stock Agent/eval/writer, retained
8/7/1 fixture draw, real inert PROGRAM builder/catalog/preflight and empty-job
closes. SCORER ExResults remain the explicitly declared _prepare MOCK, not
decoded native results. This is NOT active PROGRAM/native/SQL/ACK proof.

The real ScriptedClient.get_response calls its public on_call hook before
returning its response. Hold its first TWO requests there. Copy live contexts
only inside delegated ordinary PROGRAM factory callbacks; return the exact
original runner, never a proxy. Public timeout/close observers delegate.

Root scope.program is the ordinary harness, NOT the lease. Read its actual
retained _CloseSet bookkeeping to find the unique _ProgramLease by original
runner identity. Never manufacture a lease or alter ownership/context tokens.
Both leases must be open, idle and admitted before the cross-context probe.

The owned_program observer delegates ONLY to _prepare's existing denial guard,
never an actual allocator. Even a routing-predicate mutant cannot allocate an
owner, execute SQL, spawn or signal. Capture a probe error before the named
dispatch gate so a denied mutant attempt fails that gate, not an incidental
exception-type assertion. No protected lifecycle/SDK/writer/hook patches.

Source review precedes execution. Cooperative40s, parent independent60s.
No AST controller, production changes or broader native qualification here.
"""
from __future__ import annotations

import asyncio
from contextvars import copy_context
from types import SimpleNamespace

import pytest

from ptc.test_owned_sql_sdk_integration import (
    _prepare, _rows, _successful, framework,  # noqa: F401
)


SAFETY_SECONDS = 40.0
INERT_PROGRAM = "print('unit-only association probe must not execute')"
REFUSAL = "owned SQL admission or association refused"

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning")


def _observe(f, monkeypatch):
    original_builder = f.api.build_owned_sql_program_harness
    # Captured AFTER _prepare installed its native-denial guard.
    original_guard = f.api.core.PilotExecutor.owned_program
    original_on_call = f.policy.on_call
    control = SimpleNamespace(
        records=[], admission=None, dispatch_attempts=[], policy_tasks=[],
        held_requests=[], both_held=asyncio.Event(),
        release_policy=asyncio.Event(), probes=[], hooks=f.api._HOOKS)

    def observed_builder(*args, **kwargs):
        ordinary = original_builder(*args, **kwargs)
        original_factory = ordinary.program_runner_factory
        program_record, = [record for record in f.programs
                           if record.harness is ordinary]

        def observed_factory(data, compiled):
            scope = f.api._rollout.get()  # READ ONLY.
            assert scope is not None and scope.live and scope.authority
            assert not scope.failed and scope.token is scope.issued_token
            assert scope.program is ordinary
            assert scope.task.data is scope.data is data is scope.trace.task.data
            assert scope.agent.harness is scope.harness
            assert type(scope.harness) is f.api.OwnedSqlHarness
            assert program_record.kwargs["task"] is scope.private
            assert program_record.kwargs["data"] is data
            assert not any(record.scope is scope for record in control.records)
            actual = original_factory(data, compiled)
            captured = copy_context()  # Original factory execution context only.
            assert captured.get(f.api._rollout) is scope
            if control.admission is None:
                control.admission = scope.admission
            assert scope.admission is control.admission
            record = SimpleNamespace(
                scope=scope, context=captured, runner=actual, lease=None,
                ordinary=ordinary, program_record=program_record,
                launch_task=asyncio.current_task(), validations=[],
                close_calls=0, close_task=None, closed=False)
            control.records.append(record)
            original_validate = actual.validate_program_timeout
            original_close = actual.aclose

            def observed_validate(timeout):
                result = original_validate(timeout)
                record.validations.append(timeout)
                return result

            async def observed_close():
                record.close_calls += 1
                assert record.close_calls == 1
                record.close_task = asyncio.current_task()
                result = await original_close()
                assert result is None  # Real empty-job close, not an ACK.
                record.closed = True
                return result

            monkeypatch.setattr(actual, "validate_program_timeout", observed_validate)
            monkeypatch.setattr(actual, "aclose", observed_close)
            return actual  # Same original object and delegated protocol.

        monkeypatch.setattr(ordinary, "program_runner_factory", observed_factory)
        return ordinary

    async def held_policy(n):
        if original_on_call is not None:
            await original_on_call(n)
        task = asyncio.current_task()
        if not any(task is old for old in control.policy_tasks):
            control.policy_tasks.append(task)
        if n <= 2:
            control.held_requests.append(n)
            if len(control.held_requests) == 2:
                control.both_held.set()
            await control.release_policy.wait()

    def observed_dispatch(self, *args, **kwargs):
        control.dispatch_attempts.append(SimpleNamespace(
            executor=self, args=args, kwargs=dict(kwargs),
            scope=f.api._rollout.get()))
        return original_guard(self, *args, **kwargs)  # DENY, never allocate.

    monkeypatch.setattr(f.api, "build_owned_sql_program_harness", observed_builder)
    monkeypatch.setattr(f.policy, "on_call", held_policy)
    monkeypatch.setattr(f.api.core.PilotExecutor, "owned_program", observed_dispatch)
    return control


def _lease(f, record):
    leases = [resource for resource, _ in record.scope.closes._entries
              if type(resource) is f.api._ProgramLease
              and resource._actual is record.runner]
    lease, = leases
    if record.lease is not None:
        assert record.lease is lease
    record.lease = lease
    return lease


def _assert_open(f, control, record):
    scope = record.scope
    lease = _lease(f, record)
    assert scope.admission is control.admission and scope.admission.active
    assert scope.live and scope.authority and not scope.failed
    assert scope.token is not None and scope.token is scope.issued_token
    assert scope.program is record.ordinary
    assert scope.task is control.admission.tasks[scope.index]
    assert scope.private is control.admission.bound.draw.eligible[scope.index]
    assert scope.data is f.public_data[scope.index]
    assert scope.task.data is scope.data is scope.trace.task.data
    assert scope.agent.harness is scope.harness
    assert any(agent is scope.agent and original is scope.harness
               for agent, original in f.state.agents)
    assert record.context.get(f.api._rollout) is scope
    assert record.validations == [5.0]  # Delegated real preflight completed.
    assert record.close_calls == 0 and not record.closed
    assert lease._close_task is None and not lease._active and not lease._failed
    assert not scope.closes._sealed
    assert all(task is None for _, task in scope.closes._entries)
    assert scope.cleanup_task is None
    assert scope.agent_task is not None and not scope.agent_task.done()
    assert record.launch_task is not None and not record.launch_task.done()
    assert scope.task_score is None and scope.harness_score is None


async def _until(caller, awaitable):
    waiter = asyncio.create_task(awaitable)
    try:
        done, _ = await asyncio.wait(
            (caller, waiter), return_when=asyncio.FIRST_COMPLETED)
        if caller in done:
            await caller
            pytest.fail("evaluation ended before two original policy responses held")
        return await waiter
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


def _retained(f, control):
    tasks = []

    def retain(task):
        if task is not None and not any(task is old for old in tasks):
            tasks.append(task)

    for task in (*control.probes, *control.policy_tasks):
        retain(task)
    for record in control.records:
        retain(record.launch_task)
        retain(record.close_task)
    if control.admission is not None:
        for scope in control.admission.scopes:
            for task in (scope.agent_task, scope.task_score,
                         scope.harness_score, scope.cleanup_task):
                retain(task)
            for resource, task in scope.closes._entries:
                retain(task)
                if type(resource) is f.api._ProgramLease:
                    retain(resource._close_task)
    return tasks


async def _release_and_drain(f, control, caller):
    control.release_policy.set()
    f.release_scores.set()
    if not caller.done():
        caller.cancel()
    await asyncio.gather(caller, return_exceptions=True)
    # Includes actual SDK drivers, launch/score/cleanup tasks, actual public
    # close tasks, probes and HTTP policy observers, even on mutant gate failure.
    await asyncio.gather(*_retained(f, control), return_exceptions=True)


def _assert_complete(f, control, episodes, target):
    assert len(episodes) == len(control.records) == len(f.programs) == len(f.scorers) == 7
    assert f.config.num_tasks == 7 and f.config.num_rollouts == 1
    assert f.config.max_concurrent == 2 and f.config.shuffle is False
    actual, = f.loads
    assert (len(actual.planned), len(actual.eligible), len(actual.exclusions)) == (8, 7, 1)
    assert len(actual.databases) == 2
    assert f.policy.calls == len(f.policy.bodies) == 7
    assert control.held_requests == [1, 2]
    assert all(not any(message.get("role") == "tool" for message in body["messages"])
               for body in f.policy.bodies)
    assert control.dispatch_attempts == [] and f.forbidden == []
    assert f.state.external == [] and f.state.channels == []
    assert not f.executor.state_dir.exists()
    assert not f.profile.shared_state_dir.exists()
    assert f.api._HOOKS is control.hooks
    assert sum(episode.ok for episode in episodes) == 6
    for record in control.records:
        scope = record.scope
        lease = _lease(f, record)
        episode, = [episode for episode in episodes if episode.task.data is scope.data]
        trace, = episode.traces
        assert trace is scope.trace and trace.task.data is scope.task.data is scope.data
        assert record.program_record.kwargs["task"] is scope.private
        assert scope.private is actual.eligible[scope.index]
        assert scope.data is f.public_data[scope.index]
        assert not scope.live and not scope.authority and scope.token is None
        assert not scope.admission.active
        assert scope.cleanup_task.done()
        assert record.validations == [5.0]
        assert record.close_calls == 1 and record.closed
        assert lease._close_task is record.close_task
        assert record.close_task.done() and record.close_task.result() is None
        entry, = [entry for entry in scope.closes._entries if entry[0] is lease]
        assert entry[1] is record.close_task
        assert not lease._active
        scorer = f.by_scorer[scope.scorer]
        if record is target:
            assert scope.failed and not episode.ok and not trace.ok
            assert not scope.published and scope.result is None and trace.rewards == {}
            assert scorer.events == ["admit", "close", "closed"]
        else:
            assert not scope.failed and episode.ok and trace.ok
            assert scope.result is scorer.result
            assert set(trace.rewards) == {"execution_accuracy"}
            assert trace.rewards["execution_accuracy"].score == 1.0
            assert scorer.events == ["admit", "score", "close", "closed"]
    for agent, original in f.state.agents:
        assert agent.harness is original
        assert type(original) is f.api.OwnedSqlHarness
    rows = _rows(f.config, completed=True)
    assert len(rows) == 7 and sum(_successful(row) for row in rows) == 6
    assert {trace["id"] for row in rows for trace in row["traces"]} == {
        record.scope.trace.id for record in control.records}
    target_row, = [row for row in rows if any(
        trace["id"] == target.scope.trace.id for trace in row["traces"])]
    assert not target_row["ok"] and not _successful(target_row)
    assert all(not trace.get("rewards") for trace in target_row["traces"])
    retained = _retained(f, control)
    assert all(task.done() for task in retained)
    assert not any(task in asyncio.all_tasks() for task in retained)


def test_registered_sdk_composition_cross_scope_program_refuses_dispatch(
        request, monkeypatch):
    """2 open leases, 0 foreign/stale dispatch attempts; 7 episodes, 6 good/1 bad."""
    f = _prepare(request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    control = _observe(f, monkeypatch)

    async def scenario():
        f.release_scores.set()
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            await _until(caller, control.both_held.wait())
            assert len(control.records) == f.policy.calls == 2
            assert len(control.policy_tasks) == 2
            assert all(not task.done() for task in control.policy_tasks)
            first, second = control.admission.scopes
            a, = [record for record in control.records if record.scope is first]
            b, = [record for record in control.records if record.scope is second]
            assert a.scope is not b.scope and a.scope.task is not b.scope.task
            assert a.scope.data is not b.scope.data
            assert a.scope.harness is not b.scope.harness
            assert a.scope.trace is not b.scope.trace
            assert a.runner is not b.runner and a.context is not b.context
            _assert_open(f, control, a)
            _assert_open(f, control, b)
            assert a.lease is not b.lease
            assert not control.release_policy.is_set()
            assert _rows(f.config) == []
            probe = asyncio.create_task(
                a.lease.run_program(INERT_PROGRAM, timeout=5),
                context=b.context)
            control.probes.append(probe)
            error = None
            try:
                await probe
            except Exception as exc:
                # Allocation denial can be wrapped by the real adapter. Keep
                # it until AFTER the named zero-attempt gate, without masking
                # cancellation or pretending every exception is a valid refusal.
                error = exc
            assert control.dispatch_attempts == [], (
                "SDK_SCOPE_ASSOCIATION_DISPATCH: foreign scope reached owned dispatch")
            assert type(error) is RuntimeError and str(error) == REFUSAL
            assert f.forbidden == []
            assert a.scope.failed and not a.scope.authority
            assert not b.scope.failed and b.scope.authority and b.scope.live
            assert a.lease._close_task is None and b.lease._close_task is None
            control.release_policy.set()
            episodes = await caller
            _assert_complete(f, control, episodes, a)

            # Formerly healthy B is now genuinely CLOSED, not merely already
            # failed by the foreign probe. Stale copied context grants nothing.
            assert not b.lease._failed and b.lease._close_task.done()
            assert not b.scope.live and b.scope.token is None
            stale = asyncio.create_task(
                b.lease.run_program(INERT_PROGRAM, timeout=5),
                context=b.context)
            control.probes.append(stale)
            stale_error = None
            try:
                await stale
            except Exception as exc:
                stale_error = exc
            assert control.dispatch_attempts == [], "stale closed lease reached dispatch"
            assert type(stale_error) is RuntimeError
            assert str(stale_error) == "owned SQL program lease unavailable"
            assert b.close_calls == 1 and not b.scope.failed
            assert f.forbidden == []
        finally:
            # Release real HTTP responses and drain actual retained work before
            # pytest restores any public observer, also on expected mutant red.
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))
