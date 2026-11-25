"""Registered SDK lifecycle feasibility reference, not production binding.

PROVES: original Agent/eval/writer ordering with cooperative retained score tasks,
stock timeout, and separately acknowledged repeated cleanup interruptions.
SHORTCUT: scripted text-only policy, empty catalog, cooperative event resource.
MISSING: actual owned invocation/ACK, retained-draw authority, concurrent samples,
native SQL accuracy and Env-writer-barrier bypass sensitivity.

Run explicitly with qualified Python: see adjacent README.md. No real provider,
model, native profile, corpus or spend activation is authorized by this reference.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.cli.eval import EvalConfig
from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
from ptc.test_bash_qa_eval_integration import framework  # noqa: F401

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)
SAFETY_SECONDS = 25.0

# This source becomes a genuine importable on-disk plugin, not a sys.modules
# substitute. Exactly one exported subclass per SDK plugin/config kind.
PLUGIN_SOURCE = r'''
import asyncio
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Literal

from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.harness import Harness
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from ptc.harness import PTCHarness, PTCHarnessConfig

__all__ = ["Config", "Adapter", "SetConfig", "FixtureSet",
           "EnvConfig", "FixtureEnv"]
ACTIVE = ContextVar("__PLUGIN___scope", default=None)


async def settle(target, record, label):
    """Join an actual task, retaining cancellation until its work finishes."""
    interrupted = None
    while not target.done():
        try:
            await asyncio.shield(target)
        except asyncio.CancelledError as exc:
            record.cancel_observations.append(label)
            record.host.cleanup_interrupted.set()
            if interrupted is None:
                interrupted = exc
    result = target.result()
    if interrupted is not None:
        raise interrupted
    return result


class CooperativeResource:
    """Protocol-only resource. No process, PID, owner, SQL or native ACK."""
    def __init__(self, host):
        self.host = host
        self.close_task = None
        self.close_calls = 0
        self.complete = False

    def start_close(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self.aclose())
        return self.close_task

    async def aclose(self):
        self.close_calls += 1
        assert self.close_calls == 1
        self.host.close_started.set()
        await self.host.release_close.wait()
        self.complete = True
        self.host.close_finished.set()


def bound(*, task=None, trace=None, adapter=None):
    record = ACTIVE.get()
    assert record is not None and record.live
    if task is not None:
        assert task is record.task and task.data is record.data
    if trace is not None:
        assert trace is record.trace and trace.task.data is record.data
    if adapter is not None:
        assert adapter is record.adapter
    return record


class Config(PTCHarnessConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"


class Adapter(PTCHarness, Harness[Config]):
    async def setup(self, runtime):
        record = bound(adapter=self)
        assert not record.harness_setup
        record.harness_setup = True
        await super().setup(runtime)

    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        record = bound(trace=trace, adapter=self)
        assert record.harness_setup and not record.launched
        assert data is record.data and not mcp_urls
        assert self.program_runner_factory is None and self.qa_factory is None
        assert self.catalog.names() == set()
        record.launched = True
        # Ordinary PTCHarness loop, one text completion, no program invocation.
        return await super().launch(
            ctx, trace, runtime, endpoint, secret, mcp_urls, data)

    async def score(self, trace, runtime):
        record = bound(trace=trace, adapter=self)
        current = asyncio.current_task()
        record.harness_score_task = current
        record.score_tasks.append(current)
        await record.host.score_entered.wait()
        if record.host.fail_harness:
            record.host.harness_failed.set()
            raise ValueError("synthetic harness-score sibling failure")
        await super().score(trace, runtime)


class FixtureTask(Task):
    async def setup(self, trace, runtime):
        record = bound(task=self)
        assert record.trace is None and trace.task.data is self.data
        record.trace = trace
        record.setup_count += 1
        assert record.setup_count == 1
        await super().setup(trace, runtime)

    async def finalize(self, trace, runtime):
        record = bound(task=self, trace=trace)
        record.finalize_count += 1
        assert record.finalize_count == 1
        assert all(resource.close_task is None for resource in record.resources)
        # Finalize deliberately does not close the scoring resource.
        await super().finalize(trace, runtime)

    async def score(self, trace, runtime=None):
        record = bound(task=self, trace=trace)
        current = asyncio.current_task()
        assert record.task_score_task is None
        record.task_score_task = current
        record.score_tasks.append(current)
        record.host.score_entered.set()
        try:
            # Event-controlled cooperative work, not elapsed-time ACK inference.
            await record.host.finish_score.wait()
        except asyncio.CancelledError:
            record.cancelled = True
            record.authority = False
            record.host.score_cancelled.set()
            raise
        finally:
            resource, = record.resources
            actual_close = resource.start_close()
            record.score_close_task = actual_close
            if record.host.fault_remaining:
                # One-hit negative fault: bypass the REAL close-before-publication
                # await, not a counter/report mutation. Env barrier stays intact.
                record.host.fault_remaining -= 1
                record.host.fault_hits += 1
            else:
                await settle(actual_close, record, "task-score-close")
        if (record.live and record.authority and not record.cancelled
                and current.cancelling() == 0):
            trace.record_reward("cooperative_protocol", 1.0)
        record.host.score_returned.set()


class SetConfig(TasksetConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"


class FixtureSet(Taskset[FixtureTask, SetConfig]):
    def load(self):
        host = ACTIVE.get()
        task = FixtureTask(TaskData(name="scope-protocol",
                                   prompt="Reply with the text done."),
                           self.config.task)
        host.tasks.append(task)
        yield task


class EnvConfig(SingleAgentEnvConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"


async def cleanup_scope(record):
    # Stop reward authority first. Start ALL closes before awaiting ANY close.
    record.authority = False
    closes = [resource.start_close() for resource in record.resources]
    record.scope_close_tasks = list(closes)
    for task in record.score_tasks:
        if not task.done():
            task.cancel()
    record.host.scope_cleanup_entered.set()
    await asyncio.gather(*closes)
    # These are the actual stock gather children, not synthetic wrapper tasks.
    await asyncio.gather(*record.score_tasks, return_exceptions=True)
    assert all(task.done() for task in record.score_tasks)
    assert all(resource.complete for resource in record.resources)
    record.host.scope_drained.set()


class FixtureEnv(Env[EnvConfig]):
    async def run(self, task, agents):
        host = ACTIVE.get()
        adapter = agents.agent.harness
        assert type(adapter) is Adapter and type(task) is FixtureTask
        record = SimpleNamespace(
            host=host, task=task, data=task.data, adapter=adapter, trace=None,
            live=True, authority=True, cancelled=False, harness_setup=False,
            launched=False, setup_count=0, finalize_count=0, score_tasks=[],
            task_score_task=None, harness_score_task=None, score_close_task=None,
            scope_close_tasks=[], cleanup_task=None, cancel_observations=[],
            resources=[CooperativeResource(host)])
        host.records.append(record)
        token = ACTIVE.set(record)
        try:
            # ORIGINAL Agent/_EpisodeAgent and ORIGINAL stock lifecycle.
            await agents.agent.run(task)
            assert agents.agent.harness is adapter
        finally:
            # Authority changes synchronously, before creating/awaiting cleanup.
            record.authority = False
            record.cleanup_task = asyncio.create_task(cleanup_scope(record))
            try:
                await settle(record.cleanup_task, record, "env-scope-cleanup")
            finally:
                # Fail closed: never revoke a still-live cleanup/scoring scope.
                assert record.cleanup_task.done()
                assert all(t.done() for t in record.score_tasks)
                assert all(r.complete for r in record.resources)
                record.live = False
                ACTIVE.reset(token)
                host.scope_revoked.set()
'''


def _prepare(monkeypatch, state, label, *, fail_harness=False, fault=False,
             scoring_timeout=5.0):
    assert importlib.metadata.version("verifiers") == "0.3.2.dev137"
    name = "sdk_scope_spike_" + uuid.uuid4().hex
    path = state.root / (name + ".py")
    path.write_text(PLUGIN_SOURCE.replace("__PLUGIN__", name))
    monkeypatch.syspath_prepend(str(state.root))
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve() == path.resolve()
    config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": name, "taskset": {"id": name},
            "interception": {"type": "server"},
            "agent": {
                "harness": {"id": name},
                "runtime": {"type": "subprocess"}, "max_turns": 2,
                "timeout": {"setup": 3.0, "rollout": 10.0,
                            "finalize": 2.0, "scoring": scoring_timeout},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(state.root / label), "run": {"dir": "run"},
    }))
    assert type(config.env) is module.EnvConfig
    assert type(config.env.taskset) is module.SetConfig
    assert type(config.env.agent.harness) is module.Config
    assert config.env.agent.timeout.scoring == scoring_timeout
    state.config = config
    state.policy = ScriptedClient([_text_step("done")])
    host = SimpleNamespace(
        tasks=[], records=[], fail_harness=fail_harness,
        fault_remaining=int(fault), fault_hits=0,
        score_entered=asyncio.Event(), finish_score=asyncio.Event(),
        score_cancelled=asyncio.Event(), score_returned=asyncio.Event(),
        close_started=asyncio.Event(), release_close=asyncio.Event(),
        close_finished=asyncio.Event(), harness_failed=asyncio.Event(),
        scope_cleanup_entered=asyncio.Event(), scope_drained=asyncio.Event(),
        scope_revoked=asyncio.Event(),
        cleanup_interrupted=asyncio.Event(),
    )
    return module, host, config, state.policy


async def _eval(module, host, config):
    token = module.ACTIVE.set(host)
    try:
        return await run_eval(config)
    finally:
        module.ACTIVE.reset(token)


def _rows(config):
    # Observation ONLY. Never patch/call the writer or invent completed rows.
    files = list(Path(config.output_dir).rglob("*.jsonl"))
    return [json.loads(line) for path in files
            for line in path.read_text().splitlines() if line.strip()]


def _successful_rows(config):
    return [row for row in _rows(config)
            if row.get("ok") or any(t.get("ok") for t in row.get("traces", []))]


async def _checkpoint():
    # Scheduling rendezvous only, not evidence of cleanup or native ACK.
    event = asyncio.Event()
    asyncio.get_running_loop().call_soon(event.set)
    await event.wait()


def _held(host, caller, config):
    record, = host.records
    resource, = record.resources
    assert host.close_started.is_set() and not resource.complete
    assert resource.close_task is record.score_close_task
    assert not resource.close_task.done() and not host.release_close.is_set()
    assert record.live and not host.scope_revoked.is_set()
    assert record.trace.rewards == {}, "PUBLICATION_BARRIER: reward before close"
    assert not _successful_rows(config), "PUBLICATION_BARRIER: writer before close"
    assert _rows(config) == [], "PUBLICATION_BARRIER: failure writer before close"
    assert not caller.done(), "PUBLICATION_BARRIER: caller escaped held close"
    return record, resource


def _drained(module, host, policy, config, *, reward=False):
    record, = host.records
    resource, = record.resources
    assert record.task is host.tasks[0] and record.data is record.task.data
    assert record.trace.task.data is record.data
    assert record.setup_count == record.finalize_count == 1
    assert record.launched and type(record.adapter) is module.Adapter
    assert len(record.score_tasks) == 2
    assert set(record.score_tasks) == {
        record.task_score_task, record.harness_score_task,
    }
    assert record.score_close_task is resource.close_task
    assert record.scope_close_tasks == [resource.close_task]
    assert resource.close_calls == 1 and resource.complete
    assert resource.close_task.done() and record.cleanup_task.done()
    assert all(task.done() for task in record.score_tasks)
    assert not (set(record.score_tasks) & asyncio.all_tasks())
    assert host.scope_drained.is_set() and host.scope_revoked.is_set()
    assert not record.live and not record.authority
    assert module.ACTIVE.get() is None
    assert policy.calls == 1
    if reward:
        assert set(record.trace.rewards) == {"cooperative_protocol"}
        row, = _rows(config)
        assert row["ok"] and row["traces"][0]["ok"]
        assert row["task"]["hash"] == record.task.hash
        assert row["traces"][0]["rewards"]["cooperative_protocol"]["score"] == 1.0
    else:
        assert record.trace.rewards == {}
        assert not _successful_rows(config)
        assert all(not t.get("rewards") for row in _rows(config)
                   for t in row.get("traces", []))


async def _release_and_join(host, caller):
    # Failure-path fixture hygiene, never an acceptance substitute.
    host.release_close.set()
    host.finish_score.set()
    if not caller.done():
        caller.cancel()
    await asyncio.gather(caller, return_exceptions=True)


def _run(case):
    # Only outer safety watchdog; stock scoring wait_for remains untouched.
    asyncio.run(asyncio.wait_for(case, SAFETY_SECONDS))


def test_scoring_three_caller_cancels_hold_original_writer(monkeypatch, framework):
    module, host, config, policy = _prepare(monkeypatch, framework, "cancel")

    async def case():
        caller = asyncio.create_task(_eval(module, host, config))
        try:
            await host.score_entered.wait()
            record, = host.records
            assert record.task_score_task in asyncio.all_tasks()
            assert caller.cancel()  # Actual call 1, during stock scoring.
            await host.score_cancelled.wait()
            await host.close_started.wait()
            _held(host, caller, config)
            observed = len(record.cancel_observations)
            host.cleanup_interrupted.clear()
            assert caller.cancel()  # Actual call 2, close still event-held.
            await host.cleanup_interrupted.wait()
            assert len(record.cancel_observations) > observed
            _held(host, caller, config)
            observed = len(record.cancel_observations)
            host.cleanup_interrupted.clear()
            assert caller.cancel()  # Actual call 3, close still event-held.
            await host.cleanup_interrupted.wait()
            assert len(record.cancel_observations) > observed
            _held(host, caller, config)
            host.release_close.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            _drained(module, host, policy, config)
        finally:
            await _release_and_join(host, caller)
    _run(case())


def test_stock_scoring_wait_for_timeout_holds_original_writer(monkeypatch, framework):
    # Configure the real supported SDK timeout, never replace/remove wait_for.
    module, host, config, policy = _prepare(
        monkeypatch, framework, "timeout", scoring_timeout=0.1)

    async def case():
        caller = asyncio.create_task(_eval(module, host, config))
        try:
            await host.score_entered.wait()
            # No test-issued cancel: only unchanged stock wait_for cancels score.
            await host.score_cancelled.wait()
            await host.close_started.wait()
            record, _ = _held(host, caller, config)
            assert record.cancelled and not record.authority
            host.release_close.set()
            episode, = await caller
            assert not episode.ok and len(episode.traces) == 1
            assert "scoring timed out" in episode.traces[0].last_error.message
            _drained(module, host, policy, config)
        finally:
            await _release_and_join(host, caller)
    _run(case())


def test_harness_score_failure_joins_actual_sibling(monkeypatch, framework):
    module, host, config, policy = _prepare(
        monkeypatch, framework, "sibling", fail_harness=True)

    async def case():
        caller = asyncio.create_task(_eval(module, host, config))
        try:
            await host.harness_failed.wait()
            await host.scope_cleanup_entered.wait()
            await host.score_cancelled.wait()
            await host.close_started.wait()
            record, _ = _held(host, caller, config)
            assert record.harness_score_task.done()
            assert not record.task_score_task.done()
            assert not record.authority
            host.release_close.set()
            episode, = await caller
            assert not episode.ok
            assert "synthetic harness-score sibling failure" in (
                episode.traces[0].last_error.message)
            _drained(module, host, policy, config)
            # Even reopening cooperative work after scope exit cannot publish.
            host.finish_score.set()
            await _checkpoint()
            assert record.trace.rewards == {} and not _successful_rows(config)
        finally:
            await _release_and_join(host, caller)
    _run(case())


async def _positive_publication(module, host, config, policy):
    host.finish_score.set()
    caller = asyncio.create_task(_eval(module, host, config))
    try:
        await host.close_started.wait()
        _held(host, caller, config)
        host.release_close.set()
        episode, = await caller
        assert episode.ok and len(episode.traces) == 1
        _drained(module, host, policy, config, reward=True)
    finally:
        await _release_and_join(host, caller)


def test_publication_barrier_one_hit_negative_fault(monkeypatch, framework):
    module, host, config, policy = _prepare(
        monkeypatch, framework, "negative", fault=True)

    async def case():
        with pytest.raises(AssertionError, match="PUBLICATION_BARRIER: reward"):
            await _positive_publication(module, host, config, policy)
        assert host.fault_hits == 1 and host.fault_remaining == 0
        record, = host.records
        assert record.cleanup_task.done()
        assert all(task.done() for task in record.score_tasks)
        assert host.scope_revoked.is_set()
    _run(case())


def test_publication_barrier_fresh_restored_positive(monkeypatch, framework):
    # Independently selectable fresh plugin/host/config, not a reused fault run.
    module, host, config, policy = _prepare(monkeypatch, framework, "positive")
    _run(_positive_publication(module, host, config, policy))
    assert host.fault_hits == host.fault_remaining == 0
