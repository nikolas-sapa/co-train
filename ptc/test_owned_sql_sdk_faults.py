"""COMPOSITION ONLY: sibling cleanup, score/reward and Env writer gates.

Real retained 8/7/1 admission, registered Tasks/Agent/evaluator/original writer,
real owned PROGRAM catalog/preflight and empty-job scorer admission/close.
The inherited ExResult is explicitly a native-result MOCK, not decoded native
output. Event-held public close completion proves no native ACK or SQL accuracy.
Existing fixture guards forbid native dispatch, SQL, subprocesses and signals.

Public scorer methods and the delegating project _settle helper are observed.
Two cases additionally inject ONE declared test-only sibling fault through
project _Scope.check, ALWAYS after its original check succeeds. The real
retained harness task is the current stock gather child, not a fake inner
task. Its synchronous post-base check runs after the mock result is retained
and while the task-score child awaits public close.

This proves sibling-failure cleanup, NOT a fast-completed-close followed by a
late sibling-failure race. That stronger race remains UNQUALIFIED. No protected
Task/Harness/Env method, _HOOKS, SDK scheduling, writer or ContextVar is
replaced. No AST controller or production source is changed.

Source review precedes execution. Cooperative watchdog 40s; parent must impose
an independent 60s per-case limit. No native/ACK/deadline/SAFE qualification.
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
    waiter = asyncio.create_task(awaitable)
    try:
        done, _ = await asyncio.wait(
            (caller, waiter), return_when=asyncio.FIRST_COMPLETED)
        if caller in done:
            await caller
            pytest.fail("composition evaluation ended before its held checkpoint")
        return await waiter
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


def _score_close_observer(f, monkeypatch, *, harness_fault=False):
    scorer_type = f.api.OwnedSqlScorer
    original_score = scorer_type.score_sql  # Already-declared ExResult MOCK.
    original_close = scorer_type.aclose  # Delegates actual empty-job close.
    original_settle = f.api._settle
    original_check = f.api._Scope.check
    control = SimpleNamespace(
        target_scope=None, target=None, items=[],
        target_ready=asyncio.Event(), join_entered=asyncio.Event(),
        close_entered=asyncio.Event(), release_close=asyncio.Event(),
        env_join_entered=asyncio.Event(), env_join_task=None,
        fault_entered=asyncio.Event(), fault_hits=0, fault_task=None,
        releasing=False, hooks=f.api._HOOKS)

    async def observed_score(self, predicted_sql):
        # Read-only observation from the actual public callback, never grant
        # authority from task names, guessed metadata or a fabricated scope.
        scope = f.api._rollout.get()
        assert scope is not None and scope.live and scope.scorer is self
        assert scope.task_score is asyncio.current_task()
        assert scope.task.data is scope.data is scope.trace.task.data
        record = f.by_scorer[self]
        assert record.kwargs["task"] is scope.private
        assert not any(item.scorer is self for item in control.items)
        if control.target_scope is None:
            # FIRST actual scope, not whichever task/name scores first.
            control.target_scope = scope.admission.scopes[0]
        item = SimpleNamespace(
            scope=scope, scorer=self, record=record, trace=scope.trace,
            task=scope.task, driver=scope.agent_task,
            score_task=asyncio.current_task(), close_task=None,
            close_calls=0, closed=False, result=None, joins=[])
        control.items.append(item)
        if scope is control.target_scope:
            control.target = item
            control.target_ready.set()
        result = await original_score(self, predicted_sql)
        item.result = result
        return result

    async def observed_close(self):
        item, = [item for item in control.items if item.scorer is self]
        item.close_calls += 1
        assert item.close_calls == 1
        item.close_task = asyncio.current_task()
        if item.scope is control.target_scope:
            control.close_entered.set()
            if control.releasing:
                control.release_close.set()
            await control.release_close.wait()
        assert await original_close(self) is None
        item.closed = True

    async def observed_settle(task):
        scope = f.api._rollout.get()
        if (control.target is not None
                and scope is control.target_scope
                and asyncio.current_task() is control.target.score_task):
            # BEFORE the real join. Baseline reaches its pre-reward join;
            # the planned one-site mutant reaches the unchanged finally join
            # AFTER reward publication instead. Never omit either real await.
            control.target.joins.append(task)
            control.join_entered.set()
        if (control.target is not None
                and scope is control.target_scope
                and scope.cleanup_task is not None
                and task is scope.cleanup_task):
            # Real baseline Env join entry, BEFORE its original await. The
            # writer mutant omits this call, so controllers must also watch
            # actual writer rows rather than waiting solely on this event.
            control.env_join_task = asyncio.current_task()
            control.env_join_entered.set()
        return await original_settle(task)

    def checked_sibling_fault(scope, *args, **kwargs):
        result = original_check(scope, *args, **kwargs)
        # No alternate authority: original association/cancellation checks must
        # succeed first. This is the actual project harness gather child at its
        # post-base check. The result-MOCK gate is open before evaluation, so
        # Task.score retains its result and yields at close before this child.
        if (harness_fault and control.fault_hits == 0
                and scope is control.target_scope
                and asyncio.current_task() is scope.harness_score
                and scope.harness_success is False
                and scope.result is not None):
            assert control.target is not None
            assert scope.result is control.target.result is control.target.record.result
            control.fault_hits += 1
            control.fault_task = asyncio.current_task()
            control.fault_entered.set()
            raise RuntimeError("COMPOSITION_ONLY_HARNESS_SIBLING_FAILURE")
        return result

    monkeypatch.setattr(scorer_type, "score_sql", observed_score)
    monkeypatch.setattr(scorer_type, "aclose", observed_close)
    monkeypatch.setattr(f.api, "_settle", observed_settle)
    if harness_fault:
        monkeypatch.setattr(f.api._Scope, "check", checked_sibling_fault)
    return control


def _tasks(control):
    retained = []
    for item in control.items:
        for task in (
                item.driver, item.score_task, item.close_task,
                item.scope.harness_score, item.scope.cleanup_task):
            if task is not None and not any(task is old for old in retained):
                retained.append(task)
    return retained


async def _release_and_drain(f, control, caller):
    # Also handles the expected future named mutant assertion failure, without
    # restoring project observers while a retained task still uses them.
    control.releasing = True
    control.release_close.set()
    f.release_scores.set()
    if not caller.done():
        caller.cancel()
    await asyncio.gather(caller, return_exceptions=True)
    await asyncio.gather(*_tasks(control), return_exceptions=True)


def _assert_complete(f, control, episodes, *, failed_target=False):
    assert len(episodes) == len(control.items) == len(f.scorers) == 7
    assert len(f.programs) == f.policy.calls == 7
    assert f.config.num_tasks == 7 and f.config.num_rollouts == 1
    assert f.config.max_concurrent == 2 and f.config.shuffle is False
    actual, = f.loads
    assert (len(actual.planned), len(actual.eligible), len(actual.exclusions)) == (8, 7, 1)
    assert len(actual.databases) == 2
    assert f.api._HOOKS is control.hooks
    assert f.forbidden == [] and f.state.external == []
    assert f.state.channels == []
    assert not f.executor.state_dir.exists()
    assert not f.profile.shared_state_dir.exists()
    assert sum(episode.ok for episode in episodes) == (6 if failed_target else 7)
    assert control.fault_hits == (1 if failed_target else 0)
    for private, data in zip(actual.eligible, f.public_data, strict=True):
        item, = [item for item in control.items
                 if item.record.kwargs["task"] is private]
        episode, = [episode for episode in episodes if episode.task.data is data]
        trace, = episode.traces
        assert trace is item.trace and trace.task.data is data
        assert item.task.data is data
        assert item.result is item.record.result is item.scope.result
        assert item.close_calls == 1 and item.closed
        assert item.close_task.done() and item.close_task.result() is None
        assert item.record.events == ["admit", "score", "close", "closed"]
        if failed_target and item is control.target:
            assert not episode.ok and not trace.ok and trace.rewards == {}
            assert item.scope.failed and not item.scope.harness_success
            assert item.scope.harness_done.is_set()
            assert control.fault_task is item.scope.harness_score
            assert trace.last_error is not None
        else:
            assert episode.ok and trace.ok
            assert set(trace.rewards) == {"execution_accuracy"}
            assert trace.rewards["execution_accuracy"].score == 1.0
        assert not item.scope.live and item.scope.token is None
        assert not item.scope.authority and not item.scope.admission.active
    for agent, original in f.state.agents:
        assert agent.harness is original
        assert type(original) is f.api.OwnedSqlHarness
    retained = _tasks(control)
    assert all(task.done() for task in retained)
    assert not any(task in asyncio.all_tasks() for task in retained)
    rows = _rows(f.config, completed=True)
    assert len(rows) == 7
    assert sum(_successful(row) for row in rows) == (6 if failed_target else 7)
    assert {trace["id"] for row in rows for trace in row["traces"]} == {
        item.trace.id for item in control.items}
    for row in rows:
        if failed_target and any(
                trace["id"] == control.target.trace.id for trace in row["traces"]):
            assert not row["ok"] and not _successful(row)
            assert all(not trace["ok"] and not trace.get("rewards")
                       for trace in row["traces"])
        else:
            assert row["ok"] and all(
                trace["ok"] and set(trace["rewards"]) == {"execution_accuracy"}
                and trace["rewards"]["execution_accuracy"]["score"] == 1.0
                for trace in row["traces"])


def _target_rows(f, control):
    target = control.target
    if target is None:
        return []
    # Failed rows count too. Never reduce this to Episode.ok or Trace.ok.
    return [row for row in _rows(f.config)
            if any(trace["id"] == target.trace.id
                   for trace in row.get("traces", []))]


async def _await_writer_checkpoint(f, control, caller):
    """Observe the real Env join OR real writer output, even if join is omitted."""
    while True:
        rows = _target_rows(f, control)
        if rows:
            return rows
        if (control.env_join_entered.is_set()
                and control.close_entered.is_set()):
            return rows
        if caller.done():
            # Preserve an unrelated refusal/error as itself, never relabel it
            # SDK_WRITER_BARRIER. Writer output is inspected before this branch.
            await caller
            rows = _target_rows(f, control)
            if rows:
                return rows
            pytest.fail("evaluation ended without target writer row or Env join")
        # Finite pacing under the enclosing 40s cooperative watchdog. No
        # manufactured checkpoint, writer callback or arbitrary long delay.
        await asyncio.sleep(0.001)


async def _await_score_cancellation(caller, target):
    while target.score_task.cancelling() == 0:
        if caller.done():
            await caller
            pytest.fail("evaluation ended before its retained score child cancelled")
        if target.score_task.done():
            pytest.fail("target score child escaped its held public close")
        await asyncio.sleep(0.001)


def _assert_sibling_held(f, control, caller):
    target = control.target
    assert control.fault_hits == 1 and control.fault_entered.is_set()
    assert control.fault_task is target.scope.harness_score
    assert target.result is target.record.result is target.scope.result
    assert target.trace.rewards == {}
    assert target.scope.harness_done.is_set() and not target.scope.harness_success
    assert target.scope.harness_score.done()
    assert not target.scope.harness_score.cancelled()
    fault = target.scope.harness_score.exception()
    assert isinstance(fault, RuntimeError)
    assert str(fault) == "COMPOSITION_ONLY_HARNESS_SIBLING_FAILURE"
    assert target.driver.done() and not target.driver.cancelled()
    assert target.driver.exception() is None  # Agent returned a failed Trace normally.
    assert not target.trace.ok
    assert target.scope.failed and not target.scope.authority
    assert target.scope.live and target.scope.token is not None
    assert target.scope.cleanup_task is not None
    assert not target.scope.cleanup_task.done()
    assert control.env_join_entered.is_set()
    assert control.env_join_task is not None
    assert control.env_join_task is not target.driver
    assert control.env_join_task is not target.scope.cleanup_task
    assert target.close_calls == 1 and not target.closed
    assert target.close_task is not None and not target.close_task.done()
    assert target.close_task.cancelling() == 0
    assert not target.score_task.done() and target.score_task.cancelling() > 0
    assert not control.release_close.is_set()
    assert not caller.done()
    assert _target_rows(f, control) == []


def test_registered_sdk_composition_score_close_reward_barrier(
        request, monkeypatch):
    """0 target rewards while close held; then 7 successes/7 single closes."""
    f = _prepare(
        request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    control = _score_close_observer(f, monkeypatch)

    async def scenario():
        # No score-result barrier: the sole held operation is target public
        # aclose. Other six scopes follow the original normal composition.
        f.release_scores.set()
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            await _until(caller, control.target_ready.wait())
            await _until(caller, control.join_entered.wait())
            await _until(caller, control.close_entered.wait())
            target = control.target
            # Keep this as the first acceptance gate after the actual join/
            # close checkpoint. The independent AST controller checks this
            # assertion's origin, not a fabricated return code or row.
            assert target.trace.rewards == {}, (
                "SDK_SCORE_CLOSE_REWARD_BARRIER: reward before public close")
            assert target.scope is control.target_scope
            assert target.scope is target.scope.admission.scopes[0]
            assert target.scope.live and target.scope.token is not None
            assert not target.score_task.done()
            assert target.close_calls == 1 and not target.closed
            assert target.close_task is not None and not target.close_task.done()
            assert target.close_task.cancelling() == 0
            assert target.joins[0] is target.close_task
            assert target.result is target.record.result
            assert not control.release_close.is_set()
            assert not any(trace["id"] == target.trace.id
                           for row in _rows(f.config)
                           for trace in row.get("traces", []))
            control.release_close.set()
            episodes = await caller
            _assert_complete(f, control, episodes)
        finally:
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))


def test_registered_sdk_composition_harness_failure_drains_score(
        request, monkeypatch):
    """1 real gather-sibling fault; held score child joined; 6 good/1 bad rows."""
    f = _prepare(
        request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    control = _score_close_observer(f, monkeypatch, harness_fault=True)

    async def scenario():
        # The mock result returns inline; Root retains it before yielding at
        # public close. No harness/SDK scheduling replacement creates this order.
        f.release_scores.set()
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            rows = await _await_writer_checkpoint(f, control, caller)
            assert rows == [], "sibling failure wrote target before cleanup"
            target = control.target
            assert target is not None
            assert target.scope is control.target_scope
            assert target.scope is target.scope.admission.scopes[0]
            await _await_score_cancellation(caller, target)
            _assert_sibling_held(f, control, caller)
            control.release_close.set()
            episodes = await caller
            _assert_complete(f, control, episodes, failed_target=True)
        finally:
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))


def test_registered_sdk_composition_env_writer_barrier(
        request, monkeypatch):
    """Reject ANY target writer row while failed-scope cleanup remains held."""
    f = _prepare(
        request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    control = _score_close_observer(f, monkeypatch, harness_fault=True)

    async def scenario():
        f.release_scores.set()
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            # Do not first await env_join_entered: the independent one-site
            # mutant omits exactly that Env _settle call. Poll actual rows too.
            rows = await _await_writer_checkpoint(f, control, caller)
            assert rows == [], "SDK_WRITER_BARRIER: row before scope cleanup"
            target = control.target
            assert target is not None
            assert target.scope is control.target_scope
            assert target.scope is target.scope.admission.scopes[0]
            await _await_score_cancellation(caller, target)
            _assert_sibling_held(f, control, caller)
            control.release_close.set()
            episodes = await caller
            _assert_complete(f, control, episodes, failed_target=True)
        finally:
            # A writer mutant may already have completed or later refuse its
            # unresolved scope. Preserve the named assertion, then release and
            # observe EVERY retained child/cleanup failure without fake success.
            await _release_and_drain(f, control, caller)

    asyncio.run(asyncio.wait_for(scenario(), SAFETY_SECONDS))
