"""Bounded original-SDK generation-failure COMPOSITION spike, never native proof.

PROVES: exhausted original ScriptedClient, admitted scorer retention, original
Agent/Env cleanup and JSONL failure. SHORTCUT: six siblings use the inherited
explicit native-result MOCK; target has zero score calls. MISSING: native
ACK/SAFE, actual-owned actors, setup failure, separate writer-barrier bypass.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from ptc.test_owned_sql_sdk_integration import (
    _prepare, _rows, _successful, framework,  # noqa: F401
)


def _assert_generation_fault(control):
    # ONE-edge fault-routing bypass must fail HERE, not at a timeout.
    assert len(control.errors) == 1, "SDK_GENERATION_FAILURE_REQUIRED"


def _original_scripted_origin(error, client_type):
    """No reconstructed exception: original code identity and AST raise site."""
    code = client_type.get_response.__code__
    path = Path(code.co_filename).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ScriptedClient"]
    method, = [node for node in cls.body
               if isinstance(node, ast.AsyncFunctionDef)
               and node.name == "get_response"]
    guard, = [node for node in method.body
              if isinstance(node, ast.If)
              and ast.dump(node.test) == ast.dump(ast.parse(
                  "self.calls > len(self.steps)", mode="eval").body)]
    raised, = guard.body
    assert isinstance(raised, ast.Raise)
    assert isinstance(raised.exc, ast.Call) and raised.exc.func.id == "RuntimeError"
    tb = error.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is code
    assert Path(tb.tb_frame.f_code.co_filename).resolve() == path
    assert tb.tb_lineno == raised.lineno


def _target_rows(f, control):
    return [row for row in _rows(f.config)
            if any(trace["id"] == control.target.scope.trace.id
                   for trace in row.get("traces", []))]


async def _checkpoint(f, control, caller):
    # Watch actual writer output too, not only a possibly absent cleanup event.
    while True:
        rows = _target_rows(f, control) if control.target is not None else []
        if rows or control.close_entered.is_set():
            return rows
        if caller.done():
            await caller
            pytest.fail("generation evaluation ended without public-close checkpoint")
        await asyncio.sleep(0.001)


def _generation_probe(request, monkeypatch, *, fault_bypass=False):
    from ptc.test_bash_qa_activation_integration import ScriptedClient
    from verifiers.v1.clients.client import Client
    from verifiers.v1.agent import Agent
    from verifiers.v1.env import Env
    from verifiers.v1.rollout import Rollout

    f = _prepare(request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    # Read-only original root identities; construction observers already installed
    # by the existing framework are not execution-hook replacements.
    hooks = f.api._HOOKS
    originals = (Agent.run, Env.run_episode, Rollout.open, Rollout.step, Rollout.close,
                 f.api.run_eval, f.api.OwnedSqlEnv.run,
                 f.api.OwnedSqlTask.setup, f.api.OwnedSqlHarness.launch)
    control = SimpleNamespace(
        items=[], target=None, close_entered=asyncio.Event(),
        release_close=asyncio.Event(), errors=[], caught=None, routed=[],
        failed_policy=ScriptedClient([]), bypass_hits=0)
    scorer_type = f.api.OwnedSqlScorer
    original_admit, original_close = scorer_type.admit, scorer_type.aclose
    good_policy = f.policy

    def admitted(self):
        result = original_admit(self)  # ORIGINAL successful filesystem admit.
        scope = f.api._rollout.get()  # Observation only, never authority mutation.
        assert scope.scorer is self and scope.setup_started and scope.live
        assert scope.trace.task.data is scope.task.data is scope.data
        assert scope.agent_task is not None
        assert any(resource is self for resource, _ in scope.closes._entries)
        record = f.by_scorer[self]
        assert record.events == ["admit"] and record.kwargs["task"] is scope.private
        item = SimpleNamespace(scope=scope, record=record, scorer=self,
                               close_task=None, closed=False)
        control.items.append(item)
        if scope.data is f.public_data[0]:  # EXACT supplied Data, no name matching.
            assert control.target is None
            control.target = item
        return result

    async def close(self):
        item, = [item for item in control.items if item.scorer is self]
        assert item.close_task is None
        item.close_task = asyncio.current_task()
        if item is control.target:
            control.close_entered.set()
            await control.release_close.wait()  # Test gate, NOT native ACK/unknown.
        assert await original_close(self) is None  # Actual empty-job cleanup.
        item.closed = True

    class RoutingClient(Client):
        async def get_response(self, dialect, body, sampling, session_id=None,
                               turn=None, headers=None):
            item, = [item for item in control.items
                     if item.scope.trace.id == session_id]
            scope = item.scope
            assert scope.trace.task.data is scope.task.data is scope.data
            assert item.record.events == ["admit"] and scope.scorer is item.scorer
            assert scope.scorer._database is not None  # ORIGINAL admitted identity.
            assert scope.harness_setup and scope.launched and not scope.finalized
            control.routed.append((scope.data, session_id))
            target = scope.data is f.public_data[0]
            # Intentional ONE edge only: selecting the ordinary original client
            # removes the natural exhausted-script fault. No SDK/source mutation.
            if target and fault_bypass:
                control.bypass_hits += 1
            policy = (control.failed_policy if target and not fault_bypass
                      else good_policy)
            try:
                return await policy.get_response(
                    dialect, body, sampling, session_id=session_id,
                    turn=turn, headers=headers)
            except RuntimeError as error:
                assert target and policy is control.failed_policy
                assert control.caught is None
                control.caught = error
                control.errors.append(error)
                raise  # Exact ORIGINAL exception, never reconstruct or replace.

    monkeypatch.setattr(scorer_type, "admit", admitted)
    monkeypatch.setattr(scorer_type, "aclose", close)
    f.state.policy = RoutingClient()  # Existing delegated server-owned client seam.

    async def scenario():
        f.release_scores.set()  # No sibling MOCK-result gates remain parked.
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            rows = await _checkpoint(f, control, caller)
            _assert_generation_fault(control)
            target = control.target
            scope, trace = target.scope, target.scope.trace
            error, = control.errors
            assert error is control.caught and type(error) is RuntimeError
            assert error.args == ("scripted model exceeded its 0-step script (call 1)",)
            _original_scripted_origin(error, ScriptedClient)
            assert control.failed_policy.calls == len(control.failed_policy.bodies) == 1
            assert control.bypass_hits == 0
            assert rows == [], "SDK_GENERATION_WRITER_BEFORE_DRAIN"
            assert trace.rewards == {} and not trace.ok and trace.last_error is not None
            call, = trace.calls
            assert call.error.type == "RuntimeError" and call.error.message == str(error)
            assert str(error) in call.error.traceback
            assert target.record.events == ["admit"]
            assert scope.scorer._jobs == [] and scope.result is None
            assert scope.task_score is scope.harness_score is None
            assert scope.failed and not scope.authority and not scope.published
            assert scope.live and scope.token is scope.issued_token
            assert scope.agent_task.done() and scope.agent_task.exception() is None
            assert scope.cleanup_task is not None and not scope.cleanup_task.done()
            assert target.close_task is not None and not target.close_task.done()
            assert target.close_task.cancelling() == 0 and not target.closed
            assert not caller.done() and not control.release_close.is_set()
            scorer_entry, = [entry for entry in scope.closes._entries
                              if entry[0] is target.scorer]
            assert scorer_entry[1] is target.close_task
            lease, = [resource for resource, _ in scope.closes._entries
                       if type(resource) is f.api._ProgramLease]
            assert lease._close_task.done() and lease._close_task.result() is None
            assert lease._actual._closed and lease._actual._jobs == []
            assert f.api._HOOKS is hooks
            f.api._check_hooks()

            control.release_close.set()  # ONLY test-owned gate, original drain next.
            episodes = await caller
            assert len(episodes) == len(control.items) == len(f.scorers) == 7
            assert len(f.programs) == len(f.state.agents) == len(f.state.runtimes) == 7
            assert len(control.routed) == 7 and len(f.entered) == good_policy.calls == 6
            assert all(data is expected for (data, _), expected in zip(
                sorted(control.routed, key=lambda pair: next(
                    i for i, row in enumerate(f.public_data) if row is pair[0])),
                f.public_data, strict=True))
            assert sum(episode.ok for episode in episodes) == 6
            retained = [caller]
            for item in control.items:
                current = item.scope
                episode, = [episode for episode in episodes
                            if episode.task.data is current.data]
                actual_trace, = episode.traces
                assert actual_trace is current.trace
                assert item.closed and item.close_task.done()
                assert item.close_task.result() is None and not item.close_task.cancelling()
                assert item.scorer._closed and item.scorer._jobs == []
                assert not current.live and current.token is None
                assert not current.authority and not current.admission.active
                for resource, task in current.closes._entries:
                    assert task.done() and task.result() is None
                    if type(resource) is f.api._ProgramLease:
                        assert resource._actual._closed and resource._actual._jobs == []
                    retained.append(task)
                for task in (current.agent_task, current.task_score,
                             current.harness_score, current.cleanup_task):
                    if task is not None:
                        assert task.done() and task.exception() is None
                        retained.append(task)
                if item is target:
                    assert not episode.ok and not actual_trace.ok
                    assert actual_trace.rewards == {} and current.result is None
                    assert item.record.events == ["admit", "close", "closed"]
                    assert current.failed and not current.finalized
                    assert error is control.errors[0] is control.caught
                else:
                    assert episode.ok and actual_trace.ok
                    assert current.result is item.record.result  # Declared MOCK only.
                    assert set(actual_trace.rewards) == {"execution_accuracy"}
                    assert actual_trace.rewards["execution_accuracy"].score == 1.0
                    assert item.record.events == ["admit", "score", "close", "closed"]
            assert not any(task in asyncio.all_tasks() for task in retained)
            rows = _rows(f.config, completed=True)
            assert len(rows) == 7 and sum(_successful(row) for row in rows) == 6
            failed, = _target_rows(f, control)
            assert not failed["ok"] and not _successful(failed)
            assert all(not trace.get("rewards") for trace in failed["traces"])
            assert all(agent.harness is harness
                       and type(harness) is f.api.OwnedSqlHarness
                       for agent, harness in f.state.agents)
            assert f.forbidden == f.state.external == f.state.channels == []
            assert not f.executor.state_dir.exists()
            assert not f.profile.shared_state_dir.exists()
            assert f.api._HOOKS is hooks
            f.api._check_hooks()
            assert originals == (
                Agent.run, Env.run_episode, Rollout.open, Rollout.step, Rollout.close,
                f.api.run_eval, f.api.OwnedSqlEnv.run,
                f.api.OwnedSqlTask.setup, f.api.OwnedSqlHarness.launch)
        finally:
            # Red control also releases ONLY test gates then original cleanup.
            # No blanket unknown-task cancellation, no fabricated close events.
            control.release_close.set()
            f.release_scores.set()
            await asyncio.gather(caller, return_exceptions=True)
            retained = [task for item in control.items
                        for task in (item.close_task, item.scope.agent_task,
                                     item.scope.task_score, item.scope.harness_score,
                                     item.scope.cleanup_task) if task is not None]
            await asyncio.gather(*retained, return_exceptions=True)
            assert caller.done() and not caller.cancelled()
            assert caller.exception() is None
            control.episodes = caller.result()
            control.rows = _rows(f.config, completed=True)
            assert len(control.episodes) == len(control.rows) == 7
            assert all(task.done() for task in retained)
            assert not any(task in asyncio.all_tasks() for task in retained)
            assert all(not item.scope.live and item.scope.token is None
                       and not item.scope.authority and not item.scope.admission.active
                       and item.closed and item.scorer._closed
                       for item in control.items)
            assert f.forbidden == f.state.external == f.state.channels == []

    asyncio.run(asyncio.wait_for(scenario(), 3.0))
    return control


def test_original_sdk_generation_failure_after_admission(request, monkeypatch):
    _generation_probe(request, monkeypatch)


def test_generation_fault_routing_bypass_is_red(request, monkeypatch):
    with pytest.raises(AssertionError, match="^SDK_GENERATION_FAILURE_REQUIRED") as caught:
        _generation_probe(request, monkeypatch, fault_bypass=True)
    tb = caught.value.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is _assert_generation_fault.__code__
    assert tb.tb_lineno == inspect.getsourcelines(_assert_generation_fault)[1] + 2
    control = tb.tb_frame.f_locals["control"]
    assert control.bypass_hits == 1 and control.errors == [] and control.caught is None
    assert control.failed_policy.calls == 0
    assert all(episode.ok for episode in control.episodes)
    assert all(_successful(row) for row in control.rows)
    scope = control.target.scope
    assert scope.published and not scope.failed and scope.result is control.target.record.result
    assert scope.trace.ok and scope.trace.rewards["execution_accuracy"].score == 1.0


def test_original_sdk_generation_failure_restored(request, monkeypatch):
    _generation_probe(request, monkeypatch)
