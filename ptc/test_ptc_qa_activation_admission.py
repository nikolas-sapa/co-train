"""Adversarial admission checks, actual SDK objects and a declared run spy."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace

import pytest

from verifiers.v1.agent import Agent
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.runtimes import ProgramResult

from cotrain_ptc_qa import run_configured_ptc_qa
from ptc.harness import PTCHarness
from ptc.runtime import Catalog
from ptc.sql_qa import QaChannel
from ptc.test_bash_qa import _runtime, _trace
from ptc.test_harness import ENDPOINT, SECRET


def _agent():
    return Agent(AgentConfig.model_validate({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "harness": {"id": "cotrain_ptc_qa", "max_turns": 4, "program_timeout": 2},
        "runtime": {"type": "subprocess"},
        "max_turns": 4,
        "retries": {"max_retries": 0},
        "timeout": {"setup": 5, "rollout": 15, "finalize": 5, "scoring": 5},
    }))


def _refused_before_run(agent, task):
    original = agent.harness
    calls = []

    async def unexpected_run(task):
        calls.append("run")
        raise AssertionError("admission reached SDK runtime provisioning boundary")

    def factory(data):
        calls.append("factory")
        return QaChannel()

    agent.run = unexpected_run
    with pytest.raises(ValueError, match="activation refused"):
        asyncio.run(run_configured_ptc_qa(agent, task, qa_factory=factory))
    assert calls == []
    assert agent.harness is original
    assert getattr(agent, "_cotrain_ptc_qa_owner", None) is None
    assert not getattr(original.config, "_qa_required", False)


@pytest.mark.parametrize("replacement", [None, 7.0])
def test_task_inspection_cannot_change_validated_timeout(replacement):
    agent = _agent()

    class MutatingTask(Task):
        @property
        def compaction(self):
            agent.timeout.setup = replacement
            return None

    _refused_before_run(agent, MutatingTask(TaskData(prompt="fixture")))


@pytest.mark.parametrize("field,value", [
    ("max_turns", 4.0),
    ("max_turns", True),
    ("max_input_tokens", 1.0),
    ("max_input_tokens", True),
    ("max_output_tokens", 1.0),
    ("max_total_tokens", True),
])
def test_live_limits_require_exact_integer_types(field, value):
    agent = _agent()
    declared = 1 if field != "max_turns" or type(value) is bool else 4
    setattr(agent.config, field, declared)
    agent.limits = replace(agent.limits, **{field: value})
    _refused_before_run(agent, Task(TaskData(prompt="fixture")))


def test_inspection_cannot_replace_original_harness():
    agent = _agent()

    class ReplacingTask(Task):
        @property
        def compaction(self):
            agent.harness = copy.copy(agent.harness)
            return None

    _refused_before_run(agent, ReplacingTask(TaskData(prompt="fixture")))


@pytest.mark.parametrize("mutation", ["config", "transport", "catalog", "factory"])
def test_inspect_bound_wiring_after_factory(tmp_path, monkeypatch, mutation):
    """Declared launch delegate counts reaching policy, not real model requests."""
    agent = _agent()
    original = agent.harness
    armed = False
    calls = []

    class MutatingTask(Task):
        @property
        def compaction(self):
            if armed:
                bound = agent.harness
                if mutation == "config":
                    bound.config.max_turns = 9
                elif mutation == "transport":
                    bound.transport = object()
                elif mutation == "catalog":
                    bound.catalog = Catalog(tools={"rogue": lambda: None})
                else:
                    bound.qa_factory = lambda data: QaChannel()
            return None

    task = MutatingTask(TaskData(prompt="fixture"))
    runtime = _runtime(tmp_path / "rt")

    def factory(data):
        nonlocal armed
        calls.append("factory")
        armed = True
        return QaChannel()

    async def delegate(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        self.qa_factory(data)
        calls.append("policy")
        return ProgramResult(exit_code=0, stdout="", stderr="")

    async def run(task):
        trace = _trace(task, agent)
        bound = agent.harness
        await bound.setup(runtime)
        await bound.launch(agent.ctx, trace, runtime, ENDPOINT, SECRET, {}, task.data)
        return trace

    monkeypatch.setattr(PTCHarness, "launch", delegate)
    agent.run = run
    with pytest.raises(ValueError, match="activation refused"):
        asyncio.run(run_configured_ptc_qa(agent, task, qa_factory=factory))
    assert calls == ["factory"], "inspection must refuse before policy dispatch"
    assert agent.harness is original
