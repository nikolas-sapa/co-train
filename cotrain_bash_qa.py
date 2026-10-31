"""Configured activation for the Bash defect-report channel.

This flat module is the canonical harness plugin ID `cotrain_bash_qa`: the
verifiers loader resolves it by name and builds `ReportingBashHarness(config)`
with NO live factory or binding -- that unbound construction exists only so an
`AgentConfig` carrying the canonical ID can stand up an Agent. The ID itself
requires reporting: an unbound harness refuses neutrally at `setup` and at
`launch`, naming `run_configured_bash_qa`, and never silently degrades into
the disabled-Bash path the reference spike used.

Activation is the runner's job, not config's:

* `run_configured_bash_qa(agent, make_task, qa_factory=...)` requires an
  Agent whose harness is the exact unbound, unmarked `ReportingBashHarness`
  on the exact `ReportingBashConfig`, with `agent.config.harness` holding the
  same canonical ID and identical public fields. Anything else -- wrong type,
  wrong ID, a bound harness, a forged or mismatched config -- refuses before
  any builder, factory, policy or tool action.
* The Agent is claimed for the call's duration on the Agent object itself
  with a private attribute plus a unique owner identity (no global
  registry), a fresh `BashQaBinding` is created, and the synchronous builder
  is called exactly once. Its result must be a real Task already mixing
  `BashQaTaskMixin` and paired to that binding -- no automatic wrapping.
* A pre-callback snapshot of the public config is re-checked afterward, so a
  callback that mutated the aliased config or swapped the harness cannot
  slip a reconfiguration past activation.
* The bound harness is constructed from the same canonical config with the
  supplied factory and the fresh binding, assigned to `agent.harness` only,
  and the existing `ptc.bash_qa.run_bash_qa` drives the rollout with all of
  its admission, channel-claim, occurrence, PATH/runtime and cleanup guards
  unchanged. The finally restores the exact original harness object and
  releases only this invocation's claim, on callback failure, admission
  refusal, exception and cancellation alike.

The factory is invoked only inside the existing launch, once, on the exact
original TaskData, and must return a fresh exact `QaChannel`. Channels are
caller-owned; nothing serializes a factory, binding, channel or credential.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import partial
from typing import Any, Literal

from verifiers.v1.agent import Agent
from verifiers.v1.clients import ModelContext
from verifiers.v1.harness import Harness
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import Trace

from ptc.bash_qa import (
    BashQaBinding,
    BashQaTaskMixin,
    QaBashHarness,
    QaBashHarnessConfig,
    run_bash_qa,
)
from ptc.sql_qa import QaChannel

__all__ = ["ReportingBashHarness"]

CANONICAL_ID = "cotrain_bash_qa"
"""The flat module name IS the plugin ID; dotted IDs fail find_spec."""

_AGENT_OWNER_ATTR = "_cotrain_qa_run_owner"
"""Private Agent attribute holding the active runner's owner identity."""


class ReportingBashConfig(QaBashHarnessConfig):
    """The canonical-ID config: `id` changes, nothing else does.

    Every inherited default and the inherited extra-field policy stay exactly
    as `QaBashHarnessConfig` declares them; supported non-default values
    (`edit=False`, `search=False`, ...) are caller-selected, never normalized
    away here. No serialized factory, binding or marker field is added.
    """

    id: Literal["cotrain_bash_qa"] = "cotrain_bash_qa"


class ReportingBashHarness(QaBashHarness, Harness[ReportingBashConfig]):
    """The canonical-ID harness, in two states.

    Bound (`qa_factory` + `qa_binding`) delegates to the existing QA
    constructor and every execution check it already enforces. Unbound --
    unmarked config, neither dependency, the shape the plugin loader builds --
    is constructible so an Agent can be made from canonical JSON, but both
    `setup` and `launch` refuse before the first action. Marked-without-
    dependencies and partial pairings refuse at construction, as before.
    """

    def __init__(
        self,
        config: ReportingBashConfig,
        *,
        qa_factory: Any = None,
        qa_binding: BashQaBinding | None = None,
    ) -> None:
        if type(config) is not ReportingBashConfig:
            raise TypeError(
                "ReportingBashHarness requires an exact ReportingBashConfig, "
                f"got {type(config).__name__}"
            )
        if config.id != CANONICAL_ID:
            raise ValueError(
                f"ReportingBashHarness requires harness id {CANONICAL_ID!r}, "
                f"got {config.id!r}"
            )
        if qa_factory is None or qa_binding is None:
            if qa_factory is not None or qa_binding is not None:
                raise ValueError(
                    "qa_factory and qa_binding must be supplied together"
                )
            # Loader shape: unmarked config builds an unbound (refusing)
            # harness; a marked config without dependencies keeps the
            # existing clone refusal inside the QA constructor.
            super().__init__(config)
            return
        super().__init__(
            config, qa_factory=qa_factory, qa_binding=qa_binding
        )

    def _require_bound(self, what: str) -> None:
        if self._qa_binding is None:
            raise ValueError(
                f"an unbound ReportingBashHarness cannot {what}; activate "
                "through run_configured_bash_qa"
            )

    async def setup(self, runtime: Runtime) -> None:
        self._require_bound("set up")
        await super().setup(runtime)

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
        tool_interception_url: str | None = None,
    ) -> ProgramResult:
        self._require_bound("launch")
        return await super().launch(
            ctx, trace, runtime, endpoint, secret, mcp_urls, data,
            tool_interception_url=tool_interception_url,
        )


def _check_sync_callable(fn: Any, name: str) -> None:
    """Require an identifiable synchronous callable before any invocation."""
    if not callable(fn):
        raise TypeError(
            f"{name} must be callable, got {type(fn).__name__}"
        )
    # inspect unwraps partial(async_fn), but not partial(async_callable_object).
    while isinstance(fn, partial):
        fn = fn.func
    call = getattr(fn, "__call__", None)
    if any(
        inspect.iscoroutinefunction(candidate)
        or inspect.isasyncgenfunction(candidate)
        for candidate in (fn, call)
    ):
        raise TypeError(f"{name} must be a synchronous callable")


def _require_task(built: Any, binding: BashQaBinding) -> Task:
    """The builder's product must be a Task already paired to this binding."""
    if inspect.iscoroutine(built):
        # An owned native coroutine is closed before the refusal so no
        # never-awaited warning escapes the refusal path.
        built.close()
        raise TypeError("the task builder returned a coroutine")
    if inspect.isawaitable(built) or inspect.isasyncgen(built):
        raise TypeError(
            "the task builder must return a Task synchronously, got "
            f"{type(built).__name__}"
        )
    if not isinstance(built, Task):
        raise TypeError(
            f"the task builder must return a Task, got {type(built).__name__}"
        )
    if not isinstance(built, BashQaTaskMixin):
        raise TypeError(
            "the task builder must return a Task mixing in "
            f"BashQaTaskMixin, got {type(built).__name__}"
        )
    if built._qa_binding is not binding:
        raise ValueError(
            "the returned task is paired to a different BashQaBinding"
        )
    return built


def _claim_agent(agent: Agent) -> object:
    """Take exclusive ownership of this Agent for one runner call.

    Private attribute plus a unique owner identity on the Agent itself --
    coordinates THIS runner only; arbitrary external mutation or concurrent
    use is unsupported and not made safe by the claim. Existing claim refuses.
    """
    owner = object()
    if getattr(agent, _AGENT_OWNER_ATTR, None) is not None:
        raise ValueError("this agent already has an in-flight qa run")
    setattr(agent, _AGENT_OWNER_ATTR, owner)
    return owner


def _release_agent(agent: Agent, owner: object) -> None:
    """Release the claim only while this invocation still owns it."""
    if getattr(agent, _AGENT_OWNER_ATTR, None) is owner:
        delattr(agent, _AGENT_OWNER_ATTR)


def _canonical_config(config: Any, where: str) -> ReportingBashConfig:
    """Exact canonical type AND id, including unvalidated model_copy edits."""
    if type(config) is not ReportingBashConfig:
        raise TypeError(
            f"{where} requires an exact ReportingBashConfig, got "
            f"{type(config).__name__}"
        )
    if config.id != CANONICAL_ID:
        raise ValueError(
            f"{where} requires harness id {CANONICAL_ID!r}, got {config.id!r}"
        )
    return config


async def run_configured_bash_qa(
    agent: Agent,
    make_task: Callable[[BashQaBinding], Task],
    *,
    qa_factory: Callable[[TaskData], QaChannel],
) -> Trace:
    """Activate and run one reporting Bash rollout on a configured Agent.

    Admission, callback validation, Agent claim, fresh binding, bound-harness
    assignment, `run_bash_qa`, and unconditional restore+release.
    Configuration and callback-shape checks precede the builder; task and
    execution admission still precede every policy/tool action.
    """
    if not isinstance(agent, Agent):
        raise TypeError(
            f"agent must be a verifiers Agent, got {type(agent).__name__}")
    original = agent.harness
    if type(original) is not ReportingBashHarness:
        raise TypeError(
            "agent.harness must be an exact unbound ReportingBashHarness, "
            f"got {type(original).__name__}"
        )
    if original._qa_factory is not None or original._qa_binding is not None:
        raise ValueError("the agent's reporting harness is already bound")
    if getattr(original.config, "_qa_required", False):
        raise ValueError(
            "the agent's reporting harness config is already marked"
        )
    harness_config = _canonical_config(original.config, "agent.harness")
    agent_config = _canonical_config(
        getattr(agent.config, "harness", None), "agent.config.harness")
    if agent_config.model_dump(mode="json") != harness_config.model_dump(
            mode="json"):
        raise ValueError(
            "agent.config.harness does not match the live harness's "
            "canonical public config"
        )
    _check_sync_callable(make_task, "make_task")
    _check_sync_callable(qa_factory, "qa_factory")
    owner = _claim_agent(agent)
    try:
        binding = BashQaBinding()
        # Snapshot BEFORE the callback so a mutation of either aliased config
        # object (or a swapped harness) is caught against the run's admitted
        # state, not merely mutual post-callback equality.
        config_snapshot = harness_config.model_dump(mode="json")
        agent_snapshot = agent_config.model_dump(mode="json")
        task = _require_task(make_task(binding), binding)
        if agent.harness is not original:
            raise ValueError(
                "the task builder replaced the agent's harness"
            )
        if (original.config is not harness_config
                or harness_config.model_dump(mode="json") != config_snapshot
                or getattr(agent.config, "harness", None) is not agent_config
                or agent_config.model_dump(mode="json") != agent_snapshot):
            raise ValueError(
                "the task builder mutated the agent's reporting config"
            )
        bound = ReportingBashHarness(
            harness_config, qa_factory=qa_factory, qa_binding=binding)
        agent.harness = bound
        return await run_bash_qa(agent, task)
    finally:
        try:
            agent.harness = original
        finally:
            _release_agent(agent, owner)
