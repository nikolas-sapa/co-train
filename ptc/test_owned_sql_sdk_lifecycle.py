"""COMPOSITION ONLY: stock SDK cancellation around event-held public closes.

Reuse the real retained 8/7/1 admission, registered plugins, original Agent,
scoring gather/wait_for, PROGRAM catalog/preflight and original JSONL writer.
The inherited score_sql seam returns an explicitly MOCK ExResult. Each real
OwnedSqlScorer has ZERO native jobs; its public aclose is event-held, then
delegated to the existing observer and actual empty-job close exactly once.
Events and Python task completion are NOT native cleanup acknowledgments.

No root lifecycle hook, _HOOKS snapshot, SDK source, writer, Task or harness is
replaced. Read-only scope observations originate in public scorer callbacks;
they are never inserted into ContextVars or used to grant execution authority.
A delegated asyncio.shield observer acknowledges delivered CancelledErrors,
without issuing cancellations, changing deadlines or releasing any hold.

BLOCKED, not skipped or simulated: late Harness.score sibling failure. The
registered harness scores through protected base Harness.score; the ordinary
PROGRAM harness returned by the public builder is only launch-delegated.
Changing its score cannot exercise that sibling. Custom metrics/toolsets are
forbidden, and patching protected methods or _HOOKS is not authorized.

No actual SQL/native dispatch, ACK, 12s deadline, 19.5s SAFE teardown, accuracy,
association mutation or independent writer-bypass sensitivity is proved here.
Source review precedes execution. Cooperative watchdog: 40s per test; parent
must independently impose 60s wall-clock termination per case.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ptc.test_owned_sql_sdk_integration import (
    _prepare, _rows, _successful, framework,  # noqa: F401
)


SAFETY_SECONDS = 40.0
pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning")


async def _until(caller, awaitable):
    """Fail on real early evaluation exit; always join the test-owned waiter."""
    waiter = asyncio.create_task(awaitable)
    try:
        done, _ = await asyncio.wait(
            (caller, waiter), return_when=asyncio.FIRST_COMPLETED)
        if caller in done:
            await caller
            pytest.fail("COMPOSITION_BARRIER: evaluation escaped a held close")
        return await waiter
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


def _observe_public_closes(f, monkeypatch):
    """Observe actual scorer objects, never manufacture a replacement owner."""
    scorer_type = f.api.OwnedSqlScorer
    original_score = scorer_type.score_sql  # Existing declared result MOCK.
    original_close = scorer_type.aclose  # Delegates actual empty-job close.
    original_shield = asyncio.shield
    control = SimpleNamespace(
        observations=[], close_entries=asyncio.Queue(),
        interruptions=asyncio.Queue(), releasing=False,
        hook_snapshot=f.api._HOOKS)

    def observation(scorer):
        found = next((item for item in control.observations
                      if item.scorer is scorer), None)
        if found is not None:
            return found
        record = f.by_scorer[scorer]
        # Observation ONLY. Neither ContextVar nor any scope field is written.
        scope = f.api._rollout.get()
        assert scope is not None and scope.live and scope.scorer is scorer
        assert scope.task.data is scope.data is scope.trace.task.data
        assert any(data is scope.data for data in f.public_data)
        assert record.kwargs["task"] is scope.private
        assert scope.task_score is asyncio.current_task()
        assert scope.agent_task is not None
        assert any(agent is scope.agent and original is scope.harness
                   for agent, original in f.state.agents)
        originals = tuple(scope.admission.taskset.load())
        again = tuple(scope.admission.taskset.load())
        assert len(originals) == len(again) == 7
        assert all(first is second
                   for first, second in zip(originals, again, strict=True))
        assert all(task.data is data for task, data in
                   zip(originals, f.public_data, strict=True))
        found = SimpleNamespace(
            scorer=scorer, record=record, scope=scope,
            trace=scope.trace, task=scope.task,
            driver_task=scope.agent_task, score_task=asyncio.current_task(),
            score_calls=0, close_calls=0, close_task=None,
            close_entered=asyncio.Event(), close_finished=asyncio.Event(),
            release_close=asyncio.Event(), score_cancelled=asyncio.Event(),
            score_body_cancelled=asyncio.Event(), score_interruptions=[],
            caller_interruptions=[])
        control.observations.append(found)
        return found

    async def observed_score(self, predicted_sql):
        item = observation(self)
        item.score_calls += 1
        assert item.score_calls == 1
        try:
            return await original_score(self, predicted_sql)
        except asyncio.CancelledError:
            item.score_body_cancelled.set()
            raise

    async def held_close(self):
        # A score callback must have observed this exact admitted scorer first.
        item, = [item for item in control.observations if item.scorer is self]
        item.close_calls += 1
        assert item.close_calls == 1, "COMPOSITION_CLOSE: public close replayed"
        item.close_task = asyncio.current_task()
        item.close_entered.set()
        control.close_entries.put_nowait(item)
        if control.releasing:
            item.release_close.set()
        await item.release_close.wait()
        assert await original_close(self) is None
        item.close_finished.set()

    async def observed_shield(awaitable):
        try:
            return await original_shield(awaitable)
        except asyncio.CancelledError as exc:
            current = asyncio.current_task()
            for item in control.observations:
                if current is item.score_task and awaitable is item.close_task:
                    item.score_interruptions.append(exc)
                    item.score_cancelled.set()
                if awaitable is item.driver_task or (
                        item.scope.cleanup_task is not None
                        and awaitable is item.scope.cleanup_task):
                    # Actual interruption caught after shield delivered it to
                    # the unchanged Env.run or its retained-cleanup join.
                    note = SimpleNamespace(
                        item=item, current=current, target=awaitable, error=exc)
                    item.caller_interruptions.append(note)
                    control.interruptions.put_nowait(note)
            raise

    monkeypatch.setattr(scorer_type, "score_sql", observed_score)
    monkeypatch.setattr(scorer_type, "aclose", held_close)
    monkeypatch.setattr(asyncio, "shield", observed_shield)
    return control


def _assert_held(f, caller, item):
    assert not caller.done()
    assert item.close_calls == 1 and item.close_entered.is_set()
    assert not item.release_close.is_set()
    assert not item.close_finished.is_set()
    assert item.close_task is not None and not item.close_task.done()
    assert item.close_task.cancelling() == 0
    assert not item.score_task.done()
    assert item.scope.live and item.scope.token is not None
    assert item.scope.agent_task is item.driver_task
    assert item.scope.task_score is item.score_task
    assert item.scope.task is item.task
    assert item.scope.trace is item.trace
    assert item.trace.rewards == {}, "COMPOSITION_REWARD: reward before close"
    rows = _rows(f.config)
    assert not any(_successful(row) for row in rows)
    assert not any(trace["id"] == item.trace.id
                   for row in rows for trace in row.get("traces", [])), (
        "COMPOSITION_WRITER: live scope written before its held close")


def _retained_tasks(control):
    tasks = []
    for item in control.observations:
        for task in (
                item.driver_task, item.score_task, item.close_task,
                item.scope.harness_score, item.scope.cleanup_task):
            if task is not None and not any(task is seen for seen in tasks):
                tasks.append(task)
    return tasks


async def _release_and_drain(f, control, caller):
    # Failure hygiene, not an acceptance substitute. Any newly entered close
    # releases itself too, so a failed assertion cannot strand another hold.
    control.releasing = True
    for item in control.observations:
        item.release_close.set()
    f.release_scores.set()
    if not caller.done():
        caller.cancel()
    await asyncio.gather(caller, return_exceptions=True)
    await asyncio.gather(*_retained_tasks(control), return_exceptions=True)


def _assert_drained(f, control):
    assert f.api._HOOKS is control.hook_snapshot
    assert f.forbidden == [] and f.state.external == []
    assert f.state.channels == []
    assert not f.executor.state_dir.exists()
    assert not f.profile.shared_state_dir.exists()
    assert len(f.public_data) == 7 and f.config.num_tasks == 7
    assert f.config.num_rollouts == 1 and f.config.shuffle is False
    for agent, original in f.state.agents:
        assert agent.harness is original
        assert type(original) is f.api.OwnedSqlHarness
    assert len(control.observations) == len(f.scorers)
    for item in control.observations:
        assert item.score_calls == item.close_calls == 1
        assert item.close_finished.is_set()
        assert item.close_task.done() and not item.close_task.cancelled()
        assert item.close_task.result() is None
        assert item.record.events == ["admit", "score", "close", "closed"]
        assert item.trace.rewards == {} and not item.trace.ok
        assert not item.scope.live and item.scope.token is None
        assert not item.scope.authority
        assert not item.scope.admission.active
    tasks = _retained_tasks(control)
    assert tasks and all(task.done() for task in tasks)
    assert not any(task in asyncio.all_tasks() for task in tasks)
    rows = _rows(f.config)
    assert not any(_successful(row) for row in rows)
    assert all(not trace.get("rewards")
               for row in rows for trace in row.get("traces", []))


def test_registered_sdk_composition_scoring_timeout_holds_public_close(
        request, monkeypatch):
    """7/7 stock 0.1s timeouts; 0 premature rewards/rows; 7 joined closes."""
    f = _prepare(
        request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    timeout = f.config.env.agent.timeout.model_copy(update={"scoring": 0.1})
    agent = f.config.env.agent.model_copy(update={"timeout": timeout})
    env = f.config.env.model_copy(update={"agent": agent})
    f.config = f.config.model_copy(update={"env": env})
    f.state.config = f.config
    assert f.config.env.agent.timeout.scoring == 0.1
    control = _observe_public_closes(f, monkeypatch)

    async def scenario():
        # _evaluate's positive controller releases its two score holds. Here
        # every MOCK result returns immediately: the hold under test is public
        # aclose, so each stock wait_for must cancel an actual close join.
        f.release_scores.set()
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            seen = []
            for _ in range(7):
                item = await _until(caller, control.close_entries.get())
                assert not any(item is previous for previous in seen)
                seen.append(item)
                await _until(caller, item.score_cancelled.wait())
                assert item.score_interruptions
                assert not item.score_body_cancelled.is_set()
                assert item.score_task.cancelling() > 0
                _assert_held(f, caller, item)
                if len(seen) == 1:
                    assert _rows(f.config) == []
                # Previous failure rows may now exist; this scope still may
                # neither publish a reward nor cross the original writer.
                item.release_close.set()
                # Completion is now permitted, including final evaluation
                # completion in this same scheduler turn. Join the actual
                # retained close rather than racing it against caller.done().
                assert await asyncio.shield(item.close_task) is None
                assert item.close_finished.is_set()
            episodes = await caller
            assert len(episodes) == len(seen) == len(f.scorers) == 7
            assert len(f.programs) == f.policy.calls == 7
            assert all(not episode.ok for episode in episodes)
            for episode in episodes:
                trace, = episode.traces
                assert not trace.ok and trace.rewards == {}
                assert trace.last_error is not None
                assert "scoring timed out" in trace.last_error.message
            rows = _rows(f.config, completed=True)
            assert len(rows) == 7
            _assert_drained(f, control)
        finally:
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))


def test_registered_sdk_composition_three_caller_cancels_drain_held_closes(
        request, monkeypatch):
    """3 issued/delivered cancels, 2 during held cleanup; 0 early publication."""
    f = _prepare(
        request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    control = _observe_public_closes(f, monkeypatch)

    async def scenario():
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            await _until(caller, f.both_entered.wait())
            assert len(control.observations) == len(f.entered) == 2
            first, second = control.observations
            assert first.scorer is not second.scorer
            assert first.task is not second.task
            assert first.trace is not second.trace
            assert not f.release_scores.is_set()
            assert _rows(f.config) == []
            delivered = []
            cleanup_task = None
            env_task = None
            for index in range(3):
                marker = "COMPOSITION_ONLY_CALLER_CANCEL_" + str(index + 1)
                assert caller.cancel(marker)
                while True:
                    note = await _until(caller, control.interruptions.get())
                    if note.item is first and note.error.args == (marker,):
                        break
                delivered.append(note)
                if index == 0:
                    assert note.target is first.driver_task
                    env_task = note.current
                    await _until(caller, first.close_entered.wait())
                    await _until(caller, second.close_entered.wait())
                    await _until(caller, first.score_body_cancelled.wait())
                    await _until(caller, second.score_body_cancelled.wait())
                    cleanup_task = first.scope.cleanup_task
                    assert cleanup_task is not None
                else:
                    assert note.current is env_task
                    assert note.target is cleanup_task
                assert first.scope.cleanup_task is cleanup_task
                assert not cleanup_task.done()
                assert first.scope.failed and not first.scope.authority
                _assert_held(f, caller, first)
                _assert_held(f, caller, second)
                assert _rows(f.config) == []
            assert len(delivered) == 3
            assert len({id(note.error) for note in delivered}) == 3
            assert sum(note.target is cleanup_task for note in delivered) == 2
            # BOTH actual public close bodies entered while BOTH gates were
            # still held. Completed-close reuse is not this observation.
            assert first.close_task is not second.close_task
            assert not first.close_finished.is_set()
            assert not second.close_finished.is_set()
            first.release_close.set()
            second.release_close.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            _assert_drained(f, control)
        finally:
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))
