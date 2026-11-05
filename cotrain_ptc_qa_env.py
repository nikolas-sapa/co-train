"""Project-only admitted PTC evaluation over the original SDK lifecycle.

Scoped trusted in-process routing, not hostile-Python containment. No channel
or permit is serialized; only bounded returned-Trace telemetry reaches the
original SDK writer. Bare SDK/stock CLI execution has no admission.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from contextvars import ContextVar
from typing import Literal

from verifiers.v1.agent import Agents, _EpisodeAgent
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.agent import AgentConfig, TimeoutConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.episode import Episode
from verifiers.v1.runtimes import SubprocessConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.trace import Trace
from verifiers.v1.utils.loaders import taskset_class

from cotrain_ptc_qa import (
    ReportingPTCConfig, _ACTIVE, _MARKER, _TIMEOUT_FIELDS, _TOKEN_FIELDS,
    _finite_positive, _run_episode_ptc_qa,
)
from ptc.sql_qa import MAX_EXPORT_BYTES, QaChannel

__all__ = ["ReportingPTCEnv"]
CANONICAL_ENV_ID = "cotrain_ptc_qa_env"
_QA_INFO_KEY = "cotrain_ptc_qa"


def _refuse() -> None:
    raise ValueError("cotrain_ptc_qa eval admission refused")


class ReportingPTCEnvConfig(SingleAgentEnvConfig):
    id: Literal["cotrain_ptc_qa_env"] = "cotrain_ptc_qa_env"


class _Admission:
    __slots__ = ("active", "config", "snapshot", "env")

    def __init__(self, config):
        self.active = True
        self.config = config
        self.snapshot = config.model_dump_json()
        self.env = None


_admission: ContextVar[_Admission | None] = ContextVar(
    "cotrain_ptc_qa_eval_admission", default=None)
_episode: ContextVar["_EpisodeScope | None"] = ContextVar(
    "cotrain_ptc_qa_eval_episode", default=None)


def _canonical(config):
    if type(config) is not ReportingPTCEnvConfig or config.id != CANONICAL_ENV_ID:
        _refuse()
    return config


def _positive(value):
    if type(value) is not int or value <= 0:
        _refuse()


def _zero_retry(config):
    if (
        type(config) is not RetryConfig
        or type(config.max_retries) is not int
        or config.max_retries != 0
    ):
        _refuse()


def _supported_env(config):
    _canonical(config)
    _zero_retry(config.retries)
    _positive(config.max_concurrent_agents)
    for name in ("episode", "finalize"):
        value = getattr(config.timeout, name)
        if value is not None and not _finite_positive(value):
            _refuse()
    agent = config.agent
    if type(agent) is not AgentConfig or type(agent.runtime) is not SubprocessConfig:
        _refuse()
    if agent.model is not None and (
        not isinstance(agent.model, str) or not agent.model.strip()
    ):
        _refuse()
    _zero_retry(agent.retries)
    _positive(agent.max_turns)
    for name in _TOKEN_FIELDS:
        value = getattr(agent, name)
        if value is not None:
            _positive(value)
    if type(agent.timeout) is not TimeoutConfig or not all(
        _finite_positive(getattr(agent.timeout, name)) for name in _TIMEOUT_FIELDS
    ):
        _refuse()
    harness = agent.harness
    if (
        type(harness) is not ReportingPTCConfig
        or harness.id != "cotrain_ptc_qa"
        or getattr(harness, _MARKER, False)
        or harness.skills
        or not _finite_positive(harness.program_timeout)
        or not _finite_positive(harness.tool_timeout)
    ):
        _refuse()
    _positive(harness.max_turns)


def _descriptor(cls, name, base):
    declaration = inspect.getattr_static(cls, name, None)
    original = inspect.getattr_static(base, name)
    if (
        type(declaration) is not classmethod
        or declaration.__func__ is not original.__func__
    ):
        raise ValueError("cotrain_ptc_qa resource declaration refused")


def _check_tool_free(cls):
    if not isinstance(cls, type) or not issubclass(cls, Taskset):
        _refuse()
    # Static lookup rejects inherited/stateful overrides without invoking them.
    _descriptor(cls, "task_type", Taskset)
    _descriptor(cls, "toolsets", Taskset)
    task = Taskset.task_type.__func__(cls)
    if not isinstance(task, type) or not issubclass(task, Task):
        _refuse()
    _descriptor(task, "toolsets", Task)


def _require_owner(env):
    record = _admission.get()
    if (
        record is None
        or not record.active
        or type(env) is not ReportingPTCEnv
        or record.env is not env
        or env.config is not record.config
        or env.config.model_dump_json() != record.snapshot
    ):
        _refuse()
    return record


class _EpisodeScope:
    """Local seat/serving associations retained across setup, launch and close."""

    def __init__(self, env, task, agents):
        self.active = True
        self.owner = _require_owner(env)
        self.env, self.task, self.agents = env, task, agents
        if type(agents) is not Agents or set(agents._agents) != {"agent"}:
            _refuse()
        agent = agents.agent
        if (
            type(agent) is not _EpisodeAgent
            or type(agent._gate) is not asyncio.Semaphore
            or env._interception is None
            or env._shared_tools
            or env._agent_specs.get("agent") is not env.config.agent
            or agent._name != "agent"
            or agent._task_cls is not env._task_cls
            or not isinstance(task, env._task_cls)
            or agent._shared_tools is not env._shared_tools
            or agent.interception is not env._interception
            or agent._warned_resources is not env._warned_resources
            or type(agent._completed) is not list
            or agent._completed
        ):
            _refuse()
        self.agent, self.config, self.gate = agent, agent.config, agent._gate
        self.refs = {
            name: getattr(agent, name) for name in (
                "_completed", "_on_trace", "_on_discard", "_shared_tools",
                "_task_cls", "_warned_resources", "interception",
            )
        }

    def check(self, agent, task):
        if (
            not self.active
            or _episode.get() is not self
            or _require_owner(self.env) is not self.owner
            or agent is not self.agent
            or type(agent) is not _EpisodeAgent
            or type(self.agents) is not Agents
            or set(self.agents._agents) != {"agent"}
            or self.agents.agent is not agent
            or task is not self.task
            or agent.config is not self.config
            or agent._gate is not self.gate
            or agent._name != "agent"
            or agent.interception is not self.env._interception
            or agent._shared_tools is not self.env._shared_tools
            or agent._task_cls is not self.env._task_cls
            or agent._warned_resources is not self.env._warned_resources
            or any(getattr(agent, name) is not value for name, value in self.refs.items())
        ):
            _refuse()


def _current_episode(agent, task):
    scope = _episode.get()
    if scope is None:
        _refuse()
    scope.check(agent, task)
    return scope


def _attach_qa(trace: Trace, channel: QaChannel) -> None:
    if _QA_INFO_KEY in trace.info:
        raise ValueError("cotrain_ptc_qa telemetry collision")
    payload = channel.export()
    if type(payload) is not bytes or len(payload) > MAX_EXPORT_BYTES:
        raise ValueError("cotrain_ptc_qa telemetry overflow")
    trace.info[_QA_INFO_KEY] = json.loads(payload)


class ReportingPTCEnv(Env[ReportingPTCEnvConfig]):
    def __init__(self, config):
        _canonical(config)
        record = _admission.get()
        if record is not None and record.active and config is record.config:
            if record.env is not None:
                _refuse()
            record.env = self  # Before callback-capable Taskset construction.
        _supported_env(config)
        _check_tool_free(taskset_class(config.taskset.id))
        super().__init__(config)

    async def run(self, task: Task, agents: Agents) -> None:
        _require_owner(self)
        if _episode.get() is not None:
            _refuse()
        scope = _EpisodeScope(self, task, agents)
        token = _episode.set(scope)
        channels = []

        def qa_factory(data: TaskData) -> QaChannel:
            scope.check(agents.agent, task)
            if channels or data is not task.data:
                _refuse()
            channel = QaChannel()
            channels.append(channel)
            return channel

        try:
            trace = await _run_episode_ptc_qa(agents.agent, task, qa_factory=qa_factory)
            scope.check(agents.agent, task)
            if channels:
                _attach_qa(trace, channels[0])
        finally:
            scope.active = False
            _episode.reset(token)


async def run_ptc_qa_eval(config: EvalConfig) -> list[Episode]:
    if (
        type(config) is not EvalConfig
        or _admission.get() is not None
        or _ACTIVE.get() is not None
    ):
        _refuse()
    env = _canonical(config.env)
    if (
        config.push is not False
        or config.resume is not False
        or config.clean is not False
        or config.dry_run is not False
        or config.run.attach is not None
        or not isinstance(config.model, str)
        or not config.model.strip()
    ):
        _refuse()
    for value in (config.num_tasks, config.num_rollouts, config.max_concurrent):
        _positive(value)
    _supported_env(env)
    _check_tool_free(taskset_class(env.taskset.id))
    record = _Admission(env)
    token = _admission.set(record)
    try:
        return await run_eval(config)
    finally:
        record.active = False
        _admission.reset(token)
