"""Configured PTC QA activation: one scoped reporting run over the stock PTC loop.

`ReportingPTCConfig`/`ReportingPTCHarness` are the canonical id-resolved pair.
Config-only loading is inert: `setup`/`launch` refuse unless the harness was
bound by `run_configured_ptc_qa`, which claims the exact base Agent, admits the
supported config/task subset, snapshots every admitted reference, binds a marked
harness carrying a protected factory, and revokes/restores on every exit path.
The old PTC loop keeps the actual channel type, claim, quotas and receipt.
"""

from __future__ import annotations

import functools
import inspect
import math
import threading
from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal, NoReturn

from verifiers.v1.agent import Agent
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.agent import AgentConfig, TimeoutConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.configs.task import TaskConfig
from verifiers.v1.harness import Harness
from verifiers.v1.runtimes import ProgramResult, Runtime, SubprocessConfig
from verifiers.v1.session import RolloutLimits
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.utils.decorators import discover_decorated

from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_qa import QaChannel

__all__ = ["ReportingPTCHarness"]

_CONFIG_ID = "cotrain_ptc_qa"
_MARKER = "_qa_required"
_OWNER_ATTR = "_cotrain_ptc_qa_owner"

_REFUSED = "cotrain_ptc_qa activation refused"
_UNBOUND = "cotrain_ptc_qa requires run_configured_ptc_qa"

_CLAIM_LOCK = threading.Lock()
_ACTIVE: ContextVar["_Record | None"] = ContextVar(
    "cotrain_ptc_qa_active", default=None
)
_TOOLSETS_FUNC = getattr(Task.toolsets, "__func__", None)
_TOKEN_FIELDS = ("max_input_tokens", "max_output_tokens", "max_total_tokens")
_TIMEOUT_FIELDS = ("setup", "rollout", "finalize", "scoring")


def _refuse() -> NoReturn:
    raise ValueError(_REFUSED)


def _dump(value: object) -> str:
    try:
        return value.model_dump_json()
    except Exception:
        raise ValueError(_REFUSED) from None


def _tool_free(task: Task) -> bool:
    declaration = inspect.getattr_static(task, "toolsets", None)
    return (
        type(declaration) is classmethod
        and declaration.__func__ is _TOOLSETS_FUNC
    )


def _interceptors(task: Task) -> bool:
    try:
        return bool(discover_decorated(task, "intercept"))
    except Exception:
        raise ValueError(_REFUSED) from None


def _inspect_task(task: Task) -> None:
    if (
        getattr(task, "NEEDS_CONTAINER", True) != False
        or getattr(task.data, "compaction", None) is not None
        or getattr(task.config, "compaction", None) is not None
        or getattr(task, "compaction", None) is not None
        or not _tool_free(task)
        or _interceptors(task)
    ):
        _refuse()


class ReportingPTCConfig(PTCHarnessConfig):
    id: Literal["cotrain_ptc_qa"] = "cotrain_ptc_qa"


class _Binding:
    """Runner-owned token stored on a bound harness; nothing else mints one."""

    __slots__ = ("_record",)

    def __init__(self, record: "_Record") -> None:
        self._record = record


class ReportingPTCHarness(PTCHarness, Harness[ReportingPTCConfig]):
    SUPPORTS_MCP = False

    def __init__(
        self, config: ReportingPTCConfig, *, _binding: _Binding | None = None
    ) -> None:
        if type(config) is not ReportingPTCConfig or config.id != _CONFIG_ID:
            raise TypeError(_REFUSED)
        if _binding is None:
            if getattr(config, _MARKER, False):
                # A marked config was admitted for reporting; rebuilding it
                # without the runner's binding must not silently drop that.
                raise RuntimeError(_REFUSED)
            super().__init__(config)
            self._binding = None
            return
        record = _binding._record if isinstance(_binding, _Binding) else None
        if record is None or getattr(config, _MARKER, False) is not True:
            raise RuntimeError(_REFUSED)
        super().__init__(config, qa_factory=record.protected_factory)
        self._binding = _binding

    async def setup(self, runtime: Runtime) -> None:
        record = self._record()
        try:
            record._begin_setup(self, runtime)
            await super().setup(runtime)
            record._finish_setup(self, runtime)
        except BaseException:
            record._failed()
            raise

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
    ) -> ProgramResult:
        record = self._record()
        try:
            record._begin_launch(self, ctx, trace, runtime, mcp_urls, data)
            result = await super().launch(
                ctx, trace, runtime, endpoint, secret, mcp_urls, data
            )
            record._finish_launch(self)
        except BaseException:
            record._failed()
            raise
        return result

    def _record(self) -> "_Record":
        binding = self._binding
        record = binding._record if isinstance(binding, _Binding) else None
        if record is None:
            raise RuntimeError(_UNBOUND)
        return record


def _limits_fields(limits: RolloutLimits) -> tuple:
    return (
        limits.max_turns,
        limits.max_input_tokens,
        limits.max_output_tokens,
        limits.max_total_tokens,
    )


def _valid_limits(limits: RolloutLimits) -> bool:
    if type(limits.max_turns) is not int or limits.max_turns <= 0:
        return False
    return all(
        value is None or (type(value) is int and value > 0)
        for value in _limits_fields(limits)[1:]
    )


def _finite_positive(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


class _Record:
    """One activation's scoped state; after revoke it is a tombstone."""

    def __init__(
        self, agent: Agent, task: Task, factory: Callable, owner: object
    ) -> None:
        self.lock = threading.Lock()
        self.state = "unstarted"
        self.active = False
        self.failed = False
        self.owner = owner
        self.binding = _Binding(self)
        self.protected_factory = self._protected()
        self.factory_consumed = False
        self.agent = agent
        self.task = task
        self.data = task.data
        self.task_config = task.config
        self.agent_config = agent.config
        self.harness_config = agent.harness.config
        self.config_refs = {
            name: getattr(agent.config, name)
            for name in ("harness", "runtime", "timeout", "retries", "client", "sampling")
        }
        self.original_harness = agent.harness
        self.runtime_config = agent.runtime_config
        self.limits = agent.limits
        self.timeout = agent.timeout
        self.ctx = agent.ctx
        self.client = agent.ctx.client
        self.sampling = agent.ctx.sampling
        self.task_timeout = task.data.timeout
        self.interception = agent.interception
        self.caller_factory = factory
        self.bound = None
        self.bound_catalog = None
        self.bound_config = None
        self.runtime = None
        self.trace = None
        self.snapshots = {
            "config": _dump(agent.config),
            "harness": _dump(self.harness_config),
            "runtime": _dump(agent.runtime_config),
            "timeout": _dump(agent.timeout),
            "limits": _limits_fields(agent.limits),
            "model": agent.ctx.model,
            "client": _dump(agent.ctx.client),
            "sampling": _dump(agent.ctx.sampling),
            "data": _dump(task.data),
            "task_config": _dump(task.config),
        }

    def _protected(self) -> Callable:
        def factory(data: TaskData) -> QaChannel:
            return self._call_factory(data)

        return factory

    # All checks run under self.lock; error strings stay fixed and generic so
    # they can never render snapshots, raw data, config values, factory errors,
    # endpoint secrets or channels.
    def _check(self, harness: "ReportingPTCHarness | None") -> None:
        if (
            not self.active
            or self.failed
            or self.state == "revoked"
            or _ACTIVE.get() is not self
        ):
            _refuse()
        agent, task, bound, snap = (
            self.agent, self.task, self.bound, self.snapshots
        )
        if task is None or bound is None or harness is not bound:
            _refuse()
        _inspect_task(task)
        if (
            bound is None
            or agent is None
            or task is None
            or snap is None
            or harness is not bound
            or agent.harness is not bound
            or bound._binding is not self.binding
            or self.binding._record is not self
            or bound.config is not self.bound_config
            or type(bound.config) is not ReportingPTCConfig
            or _dump(bound.config) != snap["harness"]
            or self.original_harness.config is not self.harness_config
            or type(self.harness_config) is not ReportingPTCConfig
            or getattr(self.harness_config, _MARKER, False)
            or _dump(self.harness_config) != snap["harness"]
            or getattr(bound.config, _MARKER, False) is not True
            or bound.qa_factory is not self.protected_factory
            or bound.transport is not None
            or bound.catalog is not self.bound_catalog
            or getattr(bound.catalog, "tools", None)
        ):
            _refuse()
        self._check_inputs()

    def _check_admission(self) -> None:
        if (
            self.agent.harness is not self.original_harness
            or self.original_harness.config is not self.harness_config
            or _dump(self.harness_config) != self.snapshots["harness"]
            or getattr(self.harness_config, _MARKER, False)
        ):
            _refuse()
        self._check_inputs()

    def _check_inputs(self) -> None:
        agent, task, snap = self.agent, self.task, self.snapshots
        if (
            agent.config is not self.agent_config
            or type(agent.config) is not AgentConfig
            or getattr(agent.config.harness, _MARKER, False)
            or _dump(agent.config) != snap["config"]
            or any(
                getattr(agent.config, name) is not value
                for name, value in self.config_refs.items()
            )
            or agent.runtime_config is not self.runtime_config
            or _dump(agent.runtime_config) != snap["runtime"]
            or agent.timeout is not self.timeout
            or _dump(agent.timeout) != snap["timeout"]
            or agent.limits is not self.limits
            or not _valid_limits(agent.limits)
            or _limits_fields(agent.limits) != snap["limits"]
            or agent.ctx is not self.ctx
            or agent.ctx.model != snap["model"]
            or agent.ctx.client is not self.client
            or agent.ctx.sampling is not self.sampling
            or _dump(agent.ctx.client) != snap["client"]
            or _dump(agent.ctx.sampling) != snap["sampling"]
            or agent.interception is not self.interception
            or agent._entered
            or agent._closed
            or agent._server is not None
            or agent._gate is not None
            or getattr(agent, _OWNER_ATTR, None) is not self.owner
        ):
            _refuse()
        if (
            task.data is not self.data
            or task.data.timeout is not self.task_timeout
            or _dump(task.data) != snap["data"]
            or task.config is not self.task_config
            or _dump(task.config) != snap["task_config"]
        ):
            _refuse()
        if self.trace is not None and self.trace.task.data is not self.data:
            _refuse()

    def _begin_setup(self, harness, runtime: Runtime) -> None:
        with self.lock:
            if self.failed or self.state != "unstarted":
                _refuse()
            self._check(harness)
            self.state = "setup-started"
            self.runtime = runtime

    def _finish_setup(self, harness, runtime: Runtime) -> None:
        with self.lock:
            if (
                self.failed
                or self.state != "setup-started"
                or runtime is not self.runtime
            ):
                _refuse()
            self._check(harness)
            self.state = "ready"

    def _begin_launch(
        self, harness, ctx, trace, runtime, mcp_urls, data
    ) -> None:
        with self.lock:
            if (
                self.failed
                or self.state != "ready"
                or ctx is not self.ctx
                or runtime is not self.runtime
                or data is not self.data
                or mcp_urls
                or getattr(trace.task, "data", None) is not self.data
            ):
                _refuse()
            self._check(harness)
            self.state = "launch-consumed"
            self.trace = trace

    def _finish_launch(self, harness) -> None:
        with self.lock:
            if self.failed or self.state != "launch-consumed":
                _refuse()
            self._check(harness)
            self.state = "finished"

    def _call_factory(self, data: TaskData) -> QaChannel:
        with self.lock:
            if (
                self.failed
                or self.factory_consumed
                or self.state != "launch-consumed"
                or data is not self.data
            ):
                _refuse()
            self._check(self.bound)
            self.factory_consumed = True
            factory = self.caller_factory
        result = factory(data)
        if inspect.iscoroutine(result):
            result.close()
        with self.lock:
            self._check(self.bound)
        if type(result) is not QaChannel:
            raise TypeError(_REFUSED)
        return result

    def _failed(self) -> None:
        with self.lock:
            self.failed = True

    def _activate(self) -> None:
        bound = _bind_harness(self.harness_config, self.binding)
        with self.lock:
            self.active = True
            self.bound = bound
            self.bound_catalog = bound.catalog
            self.bound_config = bound.config
        self.agent.harness = bound

    def _revoke(self) -> None:
        agent, original, owner = self.agent, self.original_harness, self.owner
        with self.lock:
            self.active = False
            self.state = "revoked"
        try:
            if agent is not None and original is not None:
                agent.harness = original
        finally:
            try:
                if agent is not None and owner is not None:
                    _release(agent, owner)
            finally:
                with self.lock:
                    self.caller_factory = None
                    self.agent = self.task = self.data = None
                    self.task_config = self.agent_config = None
                    self.harness_config = self.original_harness = None
                    self.bound = self.bound_catalog = None
                    self.bound_config = self.config_refs = None
                    self.runtime = self.trace = None
                    self.runtime_config = self.limits = self.timeout = None
                    self.ctx = self.interception = None
                    self.client = self.sampling = self.task_timeout = None
                    self.snapshots = None
                    self.owner = None


def _claim(agent: Agent) -> object:
    owner = object()
    with _CLAIM_LOCK:
        if getattr(agent, _OWNER_ATTR, None) is not None:
            _refuse()
        setattr(agent, _OWNER_ATTR, owner)
    return owner


def _release(agent: Agent, owner: object) -> None:
    with _CLAIM_LOCK:
        if getattr(agent, _OWNER_ATTR, None) is owner:
            try:
                delattr(agent, _OWNER_ATTR)
            except AttributeError:
                pass


def _screen(agent: Agent, task: Task, qa_factory: Callable) -> None:
    if type(agent) is not Agent or not isinstance(task, Task):
        _refuse()
    if not callable(qa_factory):
        raise TypeError(_REFUSED)
    if (
        isinstance(qa_factory, functools.partial)
        or inspect.iscoroutinefunction(qa_factory)
        or inspect.isasyncgenfunction(qa_factory)
        or inspect.isgeneratorfunction(qa_factory)
        or inspect.iscoroutinefunction(getattr(qa_factory, "__call__", None))
        or inspect.isasyncgenfunction(getattr(qa_factory, "__call__", None))
        or inspect.isgeneratorfunction(getattr(qa_factory, "__call__", None))
    ):
        raise TypeError(_REFUSED)


def _validate(agent: Agent, task: Task, *, inspect_task: bool = True) -> None:
    cfg = agent.config
    harness = agent.harness
    if type(cfg) is not AgentConfig:
        _refuse()
    if (
        agent._entered
        or agent._closed
        or agent._server is not None
        or agent._gate is not None
    ):
        _refuse()
    if type(harness) is not ReportingPTCHarness or harness._binding is not None:
        _refuse()
    hcfg = harness.config
    if (
        type(hcfg) is not ReportingPTCConfig
        or hcfg.id != _CONFIG_ID
        or getattr(hcfg, _MARKER, False)
    ):
        _refuse()
    dcfg = cfg.harness
    if (
        type(dcfg) is not ReportingPTCConfig
        or dcfg.id != _CONFIG_ID
        or getattr(dcfg, _MARKER, False)
        or dcfg != hcfg
    ):
        _refuse()
    if (
        harness.qa_factory is not None
        or harness.transport is not None
        or getattr(harness.catalog, "tools", None)
    ):
        _refuse()
    if (
        type(cfg.runtime) is not SubprocessConfig
        or agent.runtime_config is not cfg.runtime
    ):
        _refuse()
    if type(cfg.max_turns) is not int or cfg.max_turns <= 0:
        _refuse()
    for name in _TOKEN_FIELDS:
        value = getattr(cfg, name)
        if value is not None and (type(value) is not int or value <= 0):
            _refuse()
    if (
        type(agent.limits) is not RolloutLimits
        or not _valid_limits(agent.limits)
        or _limits_fields(agent.limits)
        != (
            cfg.max_turns,
            cfg.max_input_tokens,
            cfg.max_output_tokens,
            cfg.max_total_tokens,
        )
    ):
        _refuse()
    if (
        type(cfg.timeout) is not TimeoutConfig
        or agent.timeout is not cfg.timeout
        or not all(
            _finite_positive(getattr(cfg.timeout, name))
            for name in _TIMEOUT_FIELDS
        )
    ):
        _refuse()
    if (
        type(cfg.retries) is not RetryConfig
        or type(cfg.retries.max_retries) is not int
        or cfg.retries.max_retries != 0
    ):
        _refuse()
    if (
        not isinstance(cfg.model, str)
        or not cfg.model.strip()
        or cfg.client is None
    ):
        _refuse()
    ctx = agent.ctx
    if (
        type(ctx) is not ModelContext
        or ctx.model != cfg.model
        or ctx.client != cfg.client
        or ctx.sampling != cfg.sampling
    ):
        _refuse()
    if (
        hcfg.skills
        or type(hcfg.max_turns) is not int
        or hcfg.max_turns <= 0
        or not _finite_positive(hcfg.program_timeout)
        or not _finite_positive(hcfg.tool_timeout)
    ):
        _refuse()
    data = task.data
    if not isinstance(data, TaskData) or not isinstance(task.config, TaskConfig):
        _refuse()
    if (
        not isinstance(data.prompt, str)
        or (
            data.system_prompt is not None
            and not isinstance(data.system_prompt, str)
        )
        or data.timeout.setup is not None
        or data.timeout.agent is not None
        or data.timeout.finalize is not None
        or data.timeout.scoring is not None
        or data.skills
        or data.image is not None
        or data.workdir is not None
    ):
        _refuse()
    if inspect_task:
        _inspect_task(task)


def _bind_harness(
    config: ReportingPTCConfig, binding: _Binding
) -> ReportingPTCHarness:
    """Create the bound canonical harness (the activation-control boundary)."""
    if type(config) is not ReportingPTCConfig or config.id != _CONFIG_ID:
        _refuse()
    copied = config.model_copy(deep=True)
    object.__setattr__(copied, _MARKER, True)
    return ReportingPTCHarness(copied, _binding=binding)


def _admit(agent: Agent, task: Task, qa_factory: Callable) -> _Record:
    if type(agent) is not Agent or not isinstance(task, Task):
        _refuse()
    owner = _claim(agent)
    try:
        _validate(agent, task, inspect_task=False)
        return _Record(agent, task, qa_factory, owner)
    except BaseException:
        _release(agent, owner)
        raise


async def run_configured_ptc_qa(
    agent: Agent,
    task: Task,
    *,
    qa_factory: Callable[[TaskData], QaChannel],
) -> Trace:
    if _ACTIVE.get() is not None:
        _refuse()
    record = _admit(agent, task, qa_factory)
    token = _ACTIVE.set(record)
    try:
        _screen(agent, task, qa_factory)
        _validate(agent, task)
        _validate(agent, task, inspect_task=False)
        record._check_admission()
        record._activate()
        return await agent.run(task)
    finally:
        try:
            record._revoke()
        finally:
            _ACTIVE.reset(token)
