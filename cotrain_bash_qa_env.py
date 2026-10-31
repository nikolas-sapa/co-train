"""Scoped evaluation admission for the configured Bash defect-report channel.

This flat module is the canonical env plugin ID `cotrain_bash_qa_env`: the
verifiers loader resolves it by name and constructs `ReportingBashEnv(config)`
inside the actual `run_eval` lifecycle. Loading alone authorizes nothing --
`run_bash_qa_eval` is the only entry point that admits execution, and it
delegates to the SDK's `run_eval` exactly once after refusing every
unsupported mode before any output, listener or platform work. A bare stock
CLI or direct SDK run lacks the admission record and must refuse reported
rollouts; the project wrapper is the supported API, not `vf-eval`.

Admission is a scoped ContextVar record owned by the wrapper: a mutable
`active` flag, the exact admitted `EvalConfig.env` (by identity) and the one
`ReportingBashEnv` that claimed it at construction -- synchronously, before
the taskset's arbitrary constructor work runs. No channel or binding ever
lives on the record, the seed or the env. A bare constructor remains usable
for loading; `Env.run` requires the active record, `config is` the admitted
config and `record.env is self`. The wrapper sets `active = False` before
resetting its token on every exit -- success, refusal, exception and
cancellation alike -- so a child context that inherited the record keeps a
revoked one, never authority.

Each episode's `run` validates the seed's synchronous `build_bash_qa_task`
with the existing `_check_sync_callable`, then wraps it once: unsupported
result shapes still reach the existing runner's own close/refusal (an owned
native coroutine is never orphaned), while a returned Task must additionally
be an instance of the seed's type carrying the seed's own `data` and `config`
-- no automatic wrapping of arbitrary tasks. A per-run factory creates one
fresh caller-owned `QaChannel` on the exact seed TaskData; a second call
fails loudly. When the runner returns a trace -- ok or failed -- `_attach_qa`
writes the bounded `channel.export()` under the fixed key `cotrain_bash_qa`
in `trace.info`; an existing key (even an equal one), an export failure or an
attachment failure refuses rather than overwriting, merging or fabricating a
channel. If the factory was never called, nothing is attached.

The env declares no retries of its own, no second writer, no `complete`
override and no shared resources: episode creation, scoring, output, run
identity and `VF_RUN_ID` stay exactly the SDK's.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Literal

from verifiers.v1.agent import Agents
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.episode import Episode
from verifiers.v1.runtimes import SubprocessConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.trace import Trace
from verifiers.v1.utils.loaders import taskset_class

from cotrain_bash_qa import (
    _canonical_config,
    _check_sync_callable,
    run_configured_bash_qa,
)
from ptc.bash_qa import BashQaBinding
from ptc.sql_qa import QaChannel

__all__ = ["ReportingBashEnv"]

CANONICAL_ENV_ID = "cotrain_bash_qa_env"
"""The flat module name IS the env plugin ID; dotted IDs fail find_spec."""

_QA_INFO_KEY = "cotrain_bash_qa"
"""The fixed `trace.info` key the bounded collector export lands under."""


class _Admission:
    """The wrapper's scoped admission: one claimed Env may run reported.

    `active` revokes before the ContextVar token resets; `config` is the
    exact admitted `EvalConfig.env` compared by identity, never equality;
    `env` is the single Env instance that claimed it at construction.
    Deliberately holds no channel, binding or other per-run state.
    """

    __slots__ = ("active", "config", "env")

    def __init__(self, config: "ReportingBashEnvConfig") -> None:
        self.active = True
        self.config = config
        self.env: "ReportingBashEnv | None" = None


_admission: ContextVar[_Admission | None] = ContextVar(
    "cotrain_bash_qa_env_admission", default=None)


class ReportingBashEnvConfig(SingleAgentEnvConfig):
    """The canonical env ID; every inherited default stays exactly as declared.

    Supported non-default seat values (`subprocess` runtime, finite positive
    `max_turns`, canonical harness with `edit=False`/`search=False`) are
    caller-selected, never invented or normalized away here.
    """

    id: Literal["cotrain_bash_qa_env"] = "cotrain_bash_qa_env"


def _canonical_env_config(config: Any, where: str) -> ReportingBashEnvConfig:
    """Exact canonical env config type AND id, including forged copies."""
    if type(config) is not ReportingBashEnvConfig:
        raise TypeError(
            f"{where} requires an exact ReportingBashEnvConfig, got "
            f"{type(config).__name__}"
        )
    if config.id != CANONICAL_ENV_ID:
        raise ValueError(
            f"{where} requires env id {CANONICAL_ENV_ID!r}, got {config.id!r}"
        )
    return config


def _require_positive(value: Any, name: str) -> None:
    """A wrapper-required finite positive count; nothing is defaulted in."""
    if type(value) is not int or value <= 0:
        raise ValueError(
            f"run_bash_qa_eval requires a finite positive {name}, got {value!r}"
        )


def _require_supported_seat(agent: Any) -> None:
    """Reject every seat the enforced QA composition cannot run, up front."""
    if not isinstance(agent, AgentConfig):
        raise TypeError("qa eval requires an AgentConfig seat")
    harness = _canonical_config(
        getattr(agent, "harness", None), "env.agent.harness")
    if getattr(harness, "_qa_required", False):
        raise ValueError("qa eval requires an unmarked reporting harness config")
    if not isinstance(agent.runtime, SubprocessConfig):
        raise TypeError(
            "qa eval supports only the subprocess runtime, got "
            f"{type(agent.runtime).__name__}"
        )
    if type(agent.max_turns) is not int or agent.max_turns <= 0:
        raise ValueError(
            "qa eval requires a finite positive env.agent.max_turns"
        )
    if type(agent.retries.max_retries) is not int or agent.retries.max_retries != 0:
        raise ValueError("qa eval refuses env.agent rollout retries")
    if harness.edit is not False:
        raise ValueError("qa eval requires env.agent.harness.edit = False")
    if harness.search is not False:
        raise ValueError("qa eval requires env.agent.harness.search = False")
    if harness.skills:
        raise ValueError("qa eval refuses env.agent.harness skills")
    if harness.compaction is not None:
        raise ValueError("qa eval refuses env.agent.harness compaction")


def _wrap_builder(seed: Task):
    """Wrap the seed's validated builder with the env's additional pairing.

    Non-Task results are returned untouched so the existing runner closes and
    refuses them (native coroutines included); a real Task must be an instance
    of the seed's own type sharing the seed's `data` and `config` identity.
    """
    original = seed.build_bash_qa_task

    def make_task(binding: BashQaBinding) -> Task:
        built = original(binding)
        if isinstance(built, Task):
            if getattr(type(built).toolsets, "__func__", None) is not Task.toolsets.__func__:
                raise ValueError(
                    "pre-start toolset refusal: custom paired Task toolsets"
                )
            if not isinstance(built, type(seed)):
                raise TypeError(
                    "build_bash_qa_task must return a "
                    f"{type(seed).__name__}, got {type(built).__name__}"
                )
            if built.data is not seed.data or built.config is not seed.config:
                raise ValueError(
                    "the paired task must carry the seed's own data and "
                    "config objects"
                )
        return built

    return make_task


def _attach_qa(trace: Trace, channel: QaChannel) -> None:
    """Attach the bounded collector export under the fixed telemetry key.

    Refuses an existing key rather than overwriting or merging; an export or
    attachment failure propagates as the env's own failure.
    """
    if _QA_INFO_KEY in trace.info:
        raise ValueError(
            f"trace.info already carries {_QA_INFO_KEY!r}; refusing to "
            "overwrite or merge qa telemetry"
        )
    trace.info[_QA_INFO_KEY] = json.loads(channel.export())


def _check_tool_free(cls: type[Taskset]) -> None:
    """Reject custom resource declarations before SDK serving starts them."""
    if not isinstance(cls, type) or not issubclass(cls, Taskset):
        raise TypeError("pre-start toolset refusal: invalid Taskset type")
    if getattr(cls.task_type, "__func__", None) is not Taskset.task_type.__func__:
        raise ValueError("pre-start toolset refusal: custom task-type selector")
    if getattr(cls.toolsets, "__func__", None) is not Taskset.toolsets.__func__:
        raise ValueError("pre-start toolset refusal: custom Taskset toolsets")
    seed = cls.task_type()
    if not isinstance(seed, type) or not issubclass(seed, Task):
        raise TypeError("pre-start toolset refusal: invalid declared Task type")
    if getattr(seed.toolsets, "__func__", None) is not Task.toolsets.__func__:
        raise ValueError("pre-start toolset refusal: custom Task toolsets")


class ReportingBashEnv(Env[ReportingBashEnvConfig]):
    """The admitted single-seat env driving `run_configured_bash_qa`.

    Constructible without admission (the loader builds it to resolve config
    and declare resources); `run` refuses unless this exact instance claimed
    the active wrapper admission carrying this exact config object.
    """

    def __init__(self, config: ReportingBashEnvConfig) -> None:
        _canonical_env_config(config, "ReportingBashEnv")
        # Claim BEFORE super().__init__ loads the taskset: that constructor
        # runs arbitrary plugin code which must not be able to take the
        # admission first. Only the admitted config object itself can claim.
        record = _admission.get()
        if (
            record is not None
            and record.active
            and config is record.config
        ):
            if record.env is not None:
                raise ValueError(
                    "a second ReportingBashEnv cannot claim one admission"
                )
            record.env = self
        # Base Env construction already invokes task_type(). Check the class
        # before that point, without constructing a second Taskset instance.
        _check_tool_free(taskset_class(config.taskset.id))
        super().__init__(config)

    async def run(self, task: Task, agents: Agents) -> None:
        record = _admission.get()
        if record is None or not record.active:
            raise ValueError(
                "ReportingBashEnv.run requires an active run_bash_qa_eval "
                "admission; loading alone does not authorize execution"
            )
        if self.config is not record.config:
            raise ValueError(
                "this env's config is not the admitted EvalConfig env"
            )
        if record.env is not self:
            raise ValueError(
                "this env is not the instance that claimed the admission"
            )
        _check_sync_callable(
            getattr(task, "build_bash_qa_task", None),
            f"{type(task).__name__}.build_bash_qa_task",
        )
        if getattr(type(task).toolsets, "__func__", None) is not Task.toolsets.__func__:
            raise ValueError("pre-start toolset refusal: custom seed Task toolsets")
        channels: list[QaChannel] = []

        def qa_factory(data: TaskData) -> QaChannel:
            if channels:
                raise ValueError(
                    "the per-run qa factory was invoked more than once"
                )
            if data is not task.data:
                raise ValueError(
                    "the qa factory received data that is not the seed's"
                )
            channel = QaChannel()
            channels.append(channel)
            return channel

        trace = await run_configured_bash_qa(
            agents.agent, _wrap_builder(task), qa_factory=qa_factory
        )
        if channels:
            _attach_qa(trace, channels[0])


async def run_bash_qa_eval(config: EvalConfig) -> list[Episode]:
    """Run one admitted reporting evaluation through the actual SDK `run_eval`.

    Every unsupported flag, config field or seat refuses BEFORE `run_eval` is
    called -- no run directory, listener or platform work happens. Values are
    checked, never invented: the caller must select each supported setting
    explicitly. The SDK owns the entire episode lifecycle, output, run id and
    `VF_RUN_ID` assignment.
    """
    if not isinstance(config, EvalConfig):
        raise TypeError(
            f"config must be an EvalConfig, got {type(config).__name__}"
        )
    if _admission.get() is not None:
        raise ValueError(
            "run_bash_qa_eval does not compose: an admission record is "
            "already present in this context"
        )
    env = _canonical_env_config(config.env, "config.env")
    if config.resume is not False:
        raise ValueError("qa eval refuses resume")
    if config.clean is not False:
        raise ValueError("qa eval refuses clean")
    if config.push is not False:
        raise ValueError("qa eval requires push = False")
    if config.run.attach is not None:
        raise ValueError("qa eval refuses run.attach")
    if type(env.retries.max_retries) is not int or env.retries.max_retries != 0:
        raise ValueError("qa eval refuses env-level retries")
    _require_supported_seat(env.agent)
    if not isinstance(config.model, str) or not config.model.strip():
        raise ValueError("qa eval requires an explicit model")
    _require_positive(config.num_tasks, "num_tasks")
    _require_positive(config.num_rollouts, "num_rollouts")
    _require_positive(config.max_concurrent, "max_concurrent")
    admission = _Admission(env)
    token = _admission.set(admission)
    try:
        return await run_eval(config)
    finally:
        # Revoke BEFORE resetting: a context inheriting the record keeps the
        # revoked object and can never run reported work.
        admission.active = False
        _admission.reset(token)
