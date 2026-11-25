"""Source audit and native-forbidden Env writer-barrier composition probes."""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from ptc.test_owned_sql_sdk_integration import (
    _prepare, _rows, _successful, framework,  # noqa: F401
)


def _probe():
    path = (Path(__file__).resolve().parents[1]
            / "spec/spikes/reference/sql-sdk-writer-barrier/probe.py")
    spec = importlib.util.spec_from_file_location("writer_barrier_source_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_original_source_feasibility_not_runtime_qualification():
    result = _probe().audit()
    assert result["source_files"] == 10
    assert result["kind"] == "SOURCE_ONLY_NOT_RUNTIME_QUALIFICATION"
    assert result["late_sibling"] == "BLOCKED_NO_ALLOWED_ORIGINAL_HARNESS_SUSPENSION"
    assert result["writer"] == (
        "ORIGINAL_ENV_SETTLE_EDGE_EXISTS_RUNTIME_SENSITIVITY_UNMEASURED")


def test_empty_gather_has_zero_scheduler_turns():
    assert asyncio.run(_probe().empty_gather_semantics()) == {
        "done_before_await": True, "scheduler_turns_during_await": 0}


def test_source_edge_detector_rejects_one_removed_env_await():
    # PROVES source detector sensitivity ONLY, not original writer RED/GREEN.
    probe = _probe()
    tree = ast.parse((probe.ROOT / "cotrain_owned_sql.py").read_text())
    assert probe._writer_edge(tree)
    run = probe._function(tree, "run", "OwnedSqlEnv")
    matches = [node for node in ast.walk(run)
               if isinstance(node, ast.Await)
               and ast.unparse(node.value) == "_settle(scope.cleanup_task)"]
    target, = matches
    target.value = ast.Constant(None)  # In-memory AST only. Never compile/execute.
    assert not probe._writer_edge(tree)


def test_source_fingerprints_do_not_expose_host_paths():
    receipts = _probe().audit()["sources"]
    assert len(receipts) == 10
    for key, receipt in receipts.items():
        assert set(receipt) == {"path", "sha256"}
        path = Path(receipt["path"])
        assert not path.is_absolute(), "PRIVATE_SOURCE_PATH_DISCLOSURE"
        assert ".." not in path.parts
        if key == "root":
            assert path.as_posix() == "cotrain_owned_sql.py"
        else:
            assert path.parts[:2] == ("verifiers", "v1")
        digest = receipt["sha256"]
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


# Six ordinary siblings use explicit native-result MOCKs. Target never scores.
# Only an exact original Env settle callback is bypassed by sensitivity tests.


def _assert_writer_barrier(rows):
    assert rows == [], "SDK_WRITER_BEFORE_ENV_DRAIN"


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


async def _checkpoint(f, control, caller, *, writer_bypass):
    # The mutant must expose an ACTUAL original-writer row, never a fake event.
    while True:
        rows = _target_rows(f, control) if control.target is not None else []
        if control.env_edge.is_set() and control.close_entered.is_set():
            if rows or not writer_bypass:
                return rows
        if caller.done():
            await caller
            if rows:
                return rows
            pytest.fail("evaluation ended without writer-barrier checkpoint")
        await asyncio.sleep(0.001)


def _writer_probe(request, monkeypatch, *, writer_bypass=False):
    from ptc.test_bash_qa_activation_integration import ScriptedClient
    from verifiers.v1.clients.client import Client
    from verifiers.v1.agent import Agent
    from verifiers.v1.env import Env
    from verifiers.v1.rollout import Rollout
    from verifiers.v1.cli import output as sdk_output

    f = _prepare(request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    # Read-only original root identities; construction observers already installed
    # by the existing framework are not execution-hook replacements.
    hooks = f.api._HOOKS
    def identities():
        return (Agent.run, Env.run_episode, Rollout.open, Rollout.step, Rollout.close,
                f.api.run_eval, f.api.OwnedSqlEnv.run,
                f.api.OwnedSqlTask.score, f.api.OwnedSqlHarness.score,
                f.api.OwnedSqlTask.setup, f.api.OwnedSqlHarness.launch,
                sdk_output.write_episode, sdk_output.append_episode)
    originals = identities()
    control = SimpleNamespace(
        items=[], target=None, close_entered=asyncio.Event(),
        release_close=asyncio.Event(), errors=[], caught=None, routed=[],
        failed_policy=ScriptedClient([]), bypass_hits=0,
        env_edge=asyncio.Event(), env_task=None, delegations=0, early_rows=[])
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
            policy = control.failed_policy if target else good_policy
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

    env_code = f.api.OwnedSqlEnv.run.__code__
    env_tree = ast.parse(inspect.getsource(f.api))
    env_class, = [node for node in env_tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlEnv"]
    env_run, = [node for node in env_class.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "run"]
    edge, = [node for node in ast.walk(env_run)
             if isinstance(node, ast.Await)
             and ast.unparse(node.value) == "_settle(scope.cleanup_task)"]
    original_settle = f.api._settle

    async def observed_settle(task):
        frame = inspect.currentframe().f_back
        target = control.target
        exact = (frame.f_code is env_code and frame.f_lineno == edge.lineno
                 and target is not None and task is target.scope.cleanup_task)
        if exact:
            scope = target.scope
            assert frame.f_locals["scope"] is scope
            current = asyncio.current_task()
            assert current.get_coro().cr_code is not None
            assert control.env_task is None or control.env_task is current
            control.env_task = current
            assert scope.agent_task.done() and not task.done()
            control.env_edge.set()
            if writer_bypass:
                control.bypass_hits += 1
                del frame
                return None  # ONLY this original target Env await is skipped.
        del frame
        control.delegations += 1
        return await original_settle(task)

    monkeypatch.setattr(f.api, "_settle", observed_settle)
    async def scenario():
        f.release_scores.set()  # No sibling MOCK-result gates remain parked.
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            rows = await _checkpoint(f, control, caller, writer_bypass=writer_bypass)
            assert len(control.errors) == 1, "ORIGINAL_GENERATION_FAULT_REQUIRED"
            target = control.target
            scope, trace = target.scope, target.scope.trace
            error, = control.errors
            assert error is control.caught and type(error) is RuntimeError
            assert error.args == ("scripted model exceeded its 0-step script (call 1)",)
            _original_scripted_origin(error, ScriptedClient)
            assert control.failed_policy.calls == len(control.failed_policy.bodies) == 1
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
            assert not control.release_close.is_set()
            if not writer_bypass:
                assert not caller.done()
            scorer_entry, = [entry for entry in scope.closes._entries
                              if entry[0] is target.scorer]
            assert scorer_entry[1] is target.close_task
            lease, = [resource for resource, _ in scope.closes._entries
                       if type(resource) is f.api._ProgramLease]
            assert lease._close_task.done() and lease._close_task.result() is None
            assert lease._actual._closed and lease._actual._jobs == []
            assert f.api._HOOKS is hooks
            f.api._check_hooks()

            assert control.env_edge.is_set() and control.env_task is not None
            assert control.env_task.get_coro().cr_code is not None
            assert control.bypass_hits == int(writer_bypass)
            assert control.delegations > 0
            assert identities() == originals
            f.api._check_hooks()
            if writer_bypass:
                failed, = rows
                assert not failed["ok"] and not _successful(failed)
                assert all(not trace.get("rewards") for trace in failed["traces"])
                assert not scope.cleanup_task.done() and not target.closed
                assert scope.live and scope.token is scope.issued_token
                control.early_rows = rows
            _assert_writer_barrier(rows)
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
            assert identities() == originals
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
            for item in control.items:
                scope = item.scope
                if writer_bypass and item is control.target:
                    assert scope.live and scope.token is scope.issued_token
                else:
                    assert not scope.live and scope.token is None
                assert not scope.authority and not scope.admission.active
                assert item.closed and item.scorer._closed and item.scorer._jobs == []
                for resource, task in scope.closes._entries:
                    assert task.done() and task.result() is None
                    if type(resource) is f.api._ProgramLease:
                        assert resource._actual._closed and resource._actual._jobs == []
            assert len(control.errors) == control.failed_policy.calls == 1
            assert len(control.routed) == 7 and len(f.entered) == good_policy.calls == 6
            assert sum(episode.ok for episode in control.episodes) == 6
            assert sum(_successful(row) for row in control.rows) == 6
            target = control.target
            assert target.record.events == ["admit", "close", "closed"]
            assert target.scope.trace.rewards == {} and target.scope.result is None
            assert target.scope.task_score is target.scope.harness_score is None
            assert not target.scope.published and target.scope.failed
            assert len(_target_rows(f, control)) == 1
            assert not _successful(_target_rows(f, control)[0])
            assert all(item.record.events == ["admit", "score", "close", "closed"]
                       for item in control.items if item is not target)
            assert not f.executor.state_dir.exists()
            assert not f.profile.shared_state_dir.exists()
            assert identities() == originals
            assert f.api._HOOKS is hooks
            f.api._check_hooks()
            assert f.forbidden == f.state.external == f.state.channels == []

    asyncio.run(asyncio.wait_for(scenario(), 3.0))
    return control


def test_original_env_writer_barrier(request, monkeypatch):
    _writer_probe(request, monkeypatch)


def test_exact_env_writer_barrier_bypass_is_red(request, monkeypatch):
    with pytest.raises(AssertionError, match="^SDK_WRITER_BEFORE_ENV_DRAIN") as caught:
        _writer_probe(request, monkeypatch, writer_bypass=True)
    tb = caught.value.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is _assert_writer_barrier.__code__
    oracle = ast.parse(inspect.getsource(_assert_writer_barrier))
    raised, = [node for node in ast.walk(oracle) if isinstance(node, ast.Assert)]
    assert tb.tb_lineno == inspect.getsourcelines(_assert_writer_barrier)[1] + raised.lineno - 1
    rows = tb.tb_frame.f_locals["rows"]
    failed, = rows
    assert not _successful(failed) and not failed["ok"]
    # The scenario's finally has already joined original cleanup, never repaired
    # the mutant scope's skipped revocation. Its exact residual state is checked
    # there, together with the unchanged generation fault and all seven rows.


def test_original_env_writer_barrier_restored(request, monkeypatch):
    _writer_probe(request, monkeypatch)

