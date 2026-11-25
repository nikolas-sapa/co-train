"""Registered, host-admitted owned SQL evaluation.

Loading these plugins grants no authority. The host supplies independently
retained preparation pins and public TaskData to the builder, then consumes
that binding once through the wrapper. Native ownership and ACK validation
remain entirely in the existing PROGRAM and SCORER adapters.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.task import TaskConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.episode import Episode
from verifiers.v1.harness import Harness
from verifiers.v1.interception import InterceptionServerConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.trace import Trace

from bench.prepare import load_validated_draw
from bench.score import ExResult, INVALID_STATUSES, extract_sql
from bench.task import SqlTask
from ptc import sql_isolation as core
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_owned_program import build_owned_sql_program_harness
from ptc.sql_owned_score import (
    OwnedSqlScorer, ScoreInfrastructureError, build_owned_sql_scorer,
)
from train.sql_episodes import InstrumentSettings, _validate_instrument

__all__ = ["OwnedSqlHarness", "OwnedSqlTaskset", "OwnedSqlEnv"]

_ID = "cotrain_owned_sql"


def _refuse() -> None:
    raise RuntimeError("owned SQL admission or association refused")


def _fingerprint(value) -> str:
    return hashlib.sha256(core.canonical_json_bytes(value)).hexdigest()


def _finite(value) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("owned SQL requires finite public JSON")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(key)
            _finite(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _finite(item)


def _wire_digest(value, *, public=False) -> str:
    try:
        if public and (
            not isinstance(value, TaskData)
            or type(value.prompt) is not str
            or value.image is not None
            or value.skills
        ):
            raise ValueError
        _finite(value.model_dump(mode="python"))
        raw = json.dumps(
            value.model_dump(mode="json"), sort_keys=True,
            ensure_ascii=False, allow_nan=False,
            separators=(",", ":")).encode("utf-8", "strict")
        if public and len(raw) > 128 * 1024:
            raise ValueError
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        raise ValueError("owned SQL requires bounded finite public JSON") from None


async def _settle(task: asyncio.Task):
    """Retain the first delivered caller cancellation until actual completion."""
    interrupted = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            if interrupted is None:
                interrupted = exc
        except Exception:
            # Inspect the retained task only after it has actually resolved.
            break
    if task.cancelled():
        raise RuntimeError("owned SQL retained cleanup was cancelled") from None
    result = task.result()
    if interrupted is not None:
        raise interrupted
    return result


async def _close_resource(resource):
    # Invoke the public method inside the retained task. A synchronous protocol
    # error must not prevent start_all from creating the other close tasks.
    return await resource.aclose()


class _ProgramLease:
    """One active PROGRAM call; one shared public runner close task."""

    def __init__(self, actual, check):
        self._actual = actual
        self._check = check
        self._active = False
        self._failed = False
        self._close_task = None

    def _available(self):
        if self._failed or self._close_task is not None or self._active:
            raise RuntimeError("owned SQL program lease unavailable")
        self._check()

    def validate_program_timeout(self, timeout):
        try:
            self._available()
            return self._actual.validate_program_timeout(timeout)
        except BaseException:
            self._failed = True
            raise

    async def run_program(self, code, *, timeout):
        # Refusing overlap does not cancel the already-owned first call.
        try:
            self._available()
        except BaseException:
            self._failed = True
            raise
        self._active = True
        try:
            return await self._actual.run_program(code, timeout=timeout)
        except BaseException:
            self._failed = True
            raise
        finally:
            self._active = False

    def start_close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(_close_resource(self._actual))
        return self._close_task

    async def aclose(self):
        task = self.start_close()
        try:
            result = await _settle(task)
            if result is not None:
                raise RuntimeError("owned SQL program cleanup failed")
        except asyncio.CancelledError:
            # Cancellation cannot conceal a malformed successful close result.
            if task.done() and not task.cancelled() and task.result() is not None:
                self._failed = True
                raise RuntimeError("owned SQL program cleanup failed") from None
            raise
        except BaseException:
            self._failed = True
            raise


class _CloseSet:
    """Identity bookkeeping only, not ownership or acknowledgment authority."""

    def __init__(self):
        self._entries = []
        self._sealed = False

    def retain(self, resource):
        if any(item[0] is resource for item in self._entries):
            return
        if self._sealed:
            raise RuntimeError("owned SQL cleanup set sealed")
        self._entries.append([resource, None])

    def start(self, resource):
        entry = next((item for item in self._entries
                      if item[0] is resource), None)
        if entry is None:
            self.retain(resource)
            entry = self._entries[-1]
        if entry[1] is None:
            # A PROGRAM lease's harness caller and outer scope must use the
            # actual same task, not two wrappers around the same public close.
            if type(resource) is _ProgramLease:
                entry[1] = resource.start_close()
            else:
                entry[1] = asyncio.create_task(_close_resource(resource))
        return entry[1]

    def start_all(self):
        self._sealed = True
        return tuple(self.start(item[0]) for item in self._entries)

    async def join_all(self):
        tasks = self.start_all()
        failure = None
        interrupted = None
        for task in tasks:
            try:
                result = await _settle(task)
                if result is not None:
                    raise RuntimeError("owned SQL cleanup returned invalid result")
            except asyncio.CancelledError as exc:
                if interrupted is None:
                    interrupted = exc
                # _settle resolves the close before propagating cancellation.
                if task.result() is not None and failure is None:
                    failure = RuntimeError("owned SQL cleanup returned invalid result")
            except BaseException as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise failure
        if interrupted is not None:
            raise interrupted


@dataclass(frozen=True)
class OwnedSqlDrawInput:
    root: Path
    draw_path: Path
    supplement_path: Path
    expected_draw_sha256: str
    expected_supplement_sha256: str
    fixture: bool = False


class RegisteredOwnedSqlBinding:
    """Opaque issued holder. Type membership is not an admission credential."""

    __slots__ = ("__state",)

    def __new__(cls):
        raise TypeError("use build_registered_owned_sql_binding")


class _BoundDraw:
    def __init__(self, holder, draw, executor, instrument, data):
        self.holder = holder
        self.draw = draw
        self.executor = executor
        self.instrument = instrument
        self.data = data
        self.draw_digest = _fingerprint(draw)
        self.instrument_digest = _fingerprint(instrument)
        self.data_digests = tuple(_wire_digest(row, public=True) for row in data)
        self.profile = executor.profile
        self.profile_digest = core.execution_profile_sha256(self.profile)
        self.state_dir = executor.state_dir
        self.used = False

    def check(self):
        try:
            _validate_instrument(self.instrument)
            if (
                _fingerprint(self.draw) != self.draw_digest
                or _fingerprint(self.instrument) != self.instrument_digest
                or tuple(_wire_digest(row, public=True) for row in self.data)
                != self.data_digests
                or type(self.executor) is not core.PilotExecutor
                or self.executor.profile is not self.profile
                or core.execution_profile_sha256(self.profile) != self.profile_digest
                or self.executor.state_dir is not self.state_dir
            ):
                _refuse()
        except Exception:
            _refuse()

    def database_digest(self, private):
        records = [row for row in self.draw.databases
                   if row.db_id == private.db_id]
        if len(records) != 1:
            _refuse()
        return records[0].sha256


def build_registered_owned_sql_binding(
    *, draw: OwnedSqlDrawInput, executor: core.PilotExecutor,
    instrument: InstrumentSettings, public_data: tuple[TaskData, ...],
) -> RegisteredOwnedSqlBinding:
    """Consume the real retained draw, without SQL, policy, or native work."""
    if (type(draw) is not OwnedSqlDrawInput
            or type(draw.fixture) is not bool
            or type(executor) is not core.PilotExecutor
            or type(instrument) is not InstrumentSettings
            or type(public_data) is not tuple):
        raise ValueError("invalid owned SQL host inputs")
    _validate_instrument(instrument)
    admitted = load_validated_draw(
        root=draw.root, draw_path=draw.draw_path,
        supplement_path=draw.supplement_path,
        expected_draw_sha256=draw.expected_draw_sha256,
        expected_supplement_sha256=draw.expected_supplement_sha256,
        fixture=draw.fixture)
    if (
        instrument.scorer_timeout_s != admitted.timeout_s
        or instrument.scorer_max_rows != admitted.max_rows
        or instrument.compare != admitted.comparison
        or instrument.program_timeout_s != 5
        or len(public_data) != len(admitted.eligible)
    ):
        raise ValueError("owned SQL admitted bounds or membership mismatch")
    for private, data in zip(admitted.eligible, public_data, strict=True):
        if (type(private) is not SqlTask or not isinstance(data, TaskData)
                or data.name != private.name):
            raise ValueError("owned SQL public association mismatch")
        _wire_digest(data, public=True)
    if len({id(row) for row in public_data}) != len(public_data):
        raise ValueError("owned SQL public associations must be distinct")
    holder = object.__new__(RegisteredOwnedSqlBinding)
    holder._RegisteredOwnedSqlBinding__state = _BoundDraw(
        holder, admitted, executor, instrument, public_data)
    return holder


class OwnedSqlHarnessConfig(PTCHarnessConfig):
    id: Literal["cotrain_owned_sql"] = _ID


class OwnedSqlTasksetConfig(TasksetConfig):
    id: Literal["cotrain_owned_sql"] = _ID


class OwnedSqlEnvConfig(SingleAgentEnvConfig):
    id: Literal["cotrain_owned_sql"] = _ID


class _Admission:
    def __init__(self, config, bound):
        self.active = True
        self.config = config
        self.env_config = config.env
        self.taskset_config = config.env.taskset
        self.task_config = config.env.taskset.task
        self.harness_config = config.env.agent.harness
        self.digest = _wire_digest(config)
        self.bound = bound
        self.env = None
        self.taskset = None
        self.views = []
        self.tasks = ()
        self.starts = []
        self.scopes = []

    def check(self):
        if (not self.active or _admission.get() is not self
                or self.config.env is not self.env_config
                or self.env_config.taskset is not self.taskset_config
                or self.taskset_config.task is not self.task_config
                or self.env_config.agent.harness is not self.harness_config):
            _refuse()
        self.bound.check()
        _supported(self.config, self.bound)
        if _wire_digest(self.config) != self.digest:
            _refuse()
        if self.taskset is not None and (
                self.taskset.config is not self.taskset_config
                or self.taskset.transform is not None
                or self.taskset.system_prompt is not None):
            _refuse()
        for view, transform in self.views:
            if (view.config is not self.taskset_config
                    or view.transform is not transform
                    or view.system_prompt is not None):
                _refuse()


_admission: ContextVar[_Admission | None] = ContextVar(
    "cotrain_owned_sql_admission", default=None)
_rollout: ContextVar[_Scope | None] = ContextVar(
    "cotrain_owned_sql_rollout", default=None)


class _Scope:
    def __init__(self, admission, task, harness, agent):
        self.admission = admission
        self.task = task
        self.data = task.data
        self.index = next(i for i, row in enumerate(admission.tasks) if row is task)
        self.private = admission.bound.draw.eligible[self.index]
        self.harness = harness
        self.agent = agent
        self.token = object()
        self.issued_token = self.token
        self.live = True
        self.authority = True
        self.failed = False
        self.trace = None
        self.runtime = None
        self._setup_pair = None
        self.setup_started = False
        self.harness_setup = False
        self.launched = False
        self.finalized = False
        self.task_score = None
        self.harness_score = None
        self.harness_success = False
        self.harness_done = asyncio.Event()
        self.scorer = None
        self.result = None
        self.published = False
        self.closes = _CloseSet()
        self.cleanup_task = None
        self.agent_task = None
        self.program = None

    def fail(self):
        self.failed = True
        self.authority = False

    def check(self, *, task=None, harness=None, trace=None, runtime=None):
        try:
            self.admission.check()
        except BaseException:
            self.fail()
            raise
        if (
            _rollout.get() is not self or not self.live or not self.authority
            or self.failed or self.token is not self.issued_token
            or self.agent.harness is not self.harness
            or self.task.data is not self.data
            or self.data is not self.admission.bound.data[self.index]
            or self.task._private is not self.private
            or self.private is not self.admission.bound.draw.eligible[self.index]
            or self.task.scoring_deferred is not False
            or self.task.config is not self.admission.config.env.taskset.task
            or self.harness.config is not self.admission.config.env.agent.harness
            or not any(candidate is self.task for candidate in self.admission.tasks)
            or task is not None and task is not self.task
            or harness is not None and harness is not self.harness
            or trace is not None and trace is not self.trace
            or runtime is not None and runtime is not self.runtime
            or self.trace is not None and self.trace.task.data is not self.data
            or not any(candidate is self for candidate in self.admission.scopes)
            or self._setup_pair is not None and (
                self.trace is not self._setup_pair[0]
                or self.runtime is not self._setup_pair[1])
        ):
            self.fail()
            _refuse()
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            self.fail()
            raise asyncio.CancelledError
        return self


def _scope(**kwargs):
    current = _rollout.get()
    if type(current) is not _Scope:
        _refuse()
    return current.check(**kwargs)


class OwnedSqlTask(Task):
    async def setup(self, trace, runtime):
        scope = _scope(task=self)
        if scope.setup_started or type(trace) is not Trace or trace.task.data is not self.data:
            scope.fail()
            _refuse()
        scope.setup_started = True
        scope.trace = trace
        scope.runtime = runtime
        scope._setup_pair = (trace, runtime)
        try:
            bound = scope.admission.bound
            private = scope.private
            scorer = build_owned_sql_scorer(
                task=private, executor=bound.executor,
                db_sha256=bound.database_digest(private), instrument=bound.instrument)
            # Retain BEFORE admit, including its synchronous failure paths.
            scope.scorer = scorer
            scope.closes.retain(scorer)
            if type(scorer) is not OwnedSqlScorer:
                _refuse()
            scorer.admit()
            await super().setup(trace, runtime)
            scope.check(task=self, trace=trace, runtime=runtime)
        except BaseException:
            scope.fail()
            raise

    async def finalize(self, trace, runtime):
        scope = _scope(task=self, trace=trace, runtime=runtime)
        if scope.finalized or not scope.launched:
            scope.fail()
            _refuse()
        scope.finalized = True
        try:
            # Stock SDK finalizes before scoring. Never close SCORER here.
            await super().finalize(trace, runtime)
        except BaseException:
            scope.fail()
            raise

    async def score(self, trace, runtime=None):
        scope = _scope(task=self, trace=trace, runtime=runtime)
        if scope.task_score is not None or not scope.finalized or scope.scorer is None:
            scope.fail()
            _refuse()
        scope.task_score = asyncio.current_task()
        body_cancel = None
        try:
            predicted = extract_sql(trace.last_reply or "")
            scope.check(task=self, trace=trace, runtime=runtime)
            result = await scope.scorer.score_sql(predicted)
            scope.result = result  # Retain the actual decoded ExResult unchanged.
            await _join_resource(scope, scope.scorer)
            await scope.harness_done.wait()
            if not scope.harness_success:
                _refuse()
            scope.check(task=self, trace=trace, runtime=runtime)
            if (type(result) is not ExResult or result.valid is not True
                    or result.status in INVALID_STATUSES):
                raise ScoreInfrastructureError("owned SQL task is not valid for scoring")
            if (result.status not in {
                    "match", "mismatch", "pred_error", "pred_timeout",
                    "pred_truncated", "pred_empty"}
                    or type(result.score) not in (int, float)
                    or result.score not in (0, 1)
                    or not math.isfinite(result.score)):
                raise ScoreInfrastructureError("owned SQL scoring result refused")
            scope.check(task=self, trace=trace, runtime=runtime)
            if scope.published or trace.rewards:
                _refuse()
            trace.record_reward("execution_accuracy", result.score)
            scope.published = True
        except asyncio.CancelledError as exc:
            body_cancel = exc
            scope.fail()
            raise
        except BaseException:
            scope.fail()
            raise
        finally:
            # Every failure, including extraction, retains the same public close.
            try:
                await _join_resource(scope, scope.scorer)
            except asyncio.CancelledError:
                scope.fail()
                if body_cancel is not None:
                    raise body_cancel
                raise
            except BaseException:
                scope.fail()
                raise


async def _join_resource(scope, resource):
    task = scope.closes.start(resource)
    result = await _settle(task)
    if result is not None:
        raise RuntimeError("owned SQL resource cleanup failed")


class OwnedSqlTaskset(Taskset[OwnedSqlTask, OwnedSqlTasksetConfig]):
    def __init__(self, config):
        if type(config) is not OwnedSqlTasksetConfig or config.system_prompt is not None:
            _refuse()
        super().__init__(config)
        admission = _admission.get()
        self._admitted = admission
        if admission is not None:
            admission.check()
            if config is not admission.config.env.taskset or admission.taskset is not None:
                _refuse()
            admission.taskset = self
            tasks = []
            for private, data in zip(
                    admission.bound.draw.eligible, admission.bound.data, strict=True):
                task = OwnedSqlTask(data, config.task)
                task._private = private
                tasks.append(task)
            admission.tasks = tuple(tasks)
            admission.starts = [0] * len(tasks)

    def load(self):
        admission = self._admitted
        if admission is None:
            _refuse()
        admission.check()
        if (not (admission.taskset is self or any(
                    view is self for view, _ in admission.views))
                or self.config is not admission.config.env.taskset
                or self.system_prompt is not None):
            _refuse()
        return admission.tasks

    def head(self, num_tasks):
        admission = self._admitted
        if admission is None:
            _refuse()
        admission.check()
        if (self is not admission.taskset or type(num_tasks) is not int
                or num_tasks != len(admission.tasks)):
            _refuse()
        # Preserve stock head/islice, including its shallow view, while admitting
        # only the complete selection. The view yields the same original Tasks.
        view = super().head(num_tasks)
        admission.views.append((view, view.transform))
        return view


class OwnedSqlHarness(PTCHarness, Harness[OwnedSqlHarnessConfig]):
    async def setup(self, runtime):
        scope = _scope(harness=self, runtime=runtime)
        if scope.harness_setup or scope.scorer is None:
            scope.fail()
            _refuse()
        scope.harness_setup = True
        try:
            await super().setup(runtime)
        except BaseException:
            scope.fail()
            raise

    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        scope = _scope(harness=self, trace=trace, runtime=runtime)
        if (not scope.harness_setup or scope.launched or data is not scope.data
                or mcp_urls or self.qa_factory is not None
                or self.program_runner_factory is not None or self.catalog.tools):
            scope.fail()
            _refuse()
        scope.launched = True
        try:
            bound = scope.admission.bound
            # Explicit conversion: never hand the registered subclass to the
            # ordinary builder, which requires exactly PTCHarnessConfig.
            fields = self.config.model_dump(mode="python")
            fields["id"] = PTCHarnessConfig().id
            ordinary = PTCHarnessConfig(**fields)
            program = build_owned_sql_program_harness(
                ordinary, data=data, task=scope.private,
                executor=bound.executor,
                db_sha256=bound.database_digest(scope.private),
                max_rows=bound.instrument.action_max_rows)
            scope.program = program
            original = program.program_runner_factory

            def factory(actual_data, compiled):
                scope.check(harness=self, trace=trace, runtime=runtime)
                if actual_data is not scope.data:
                    _refuse()
                actual = original(actual_data, compiled)
                # Retain factory output before protocol validation or awaiting.
                lease = _ProgramLease(
                    actual, lambda: scope.check(
                        harness=self, trace=trace, runtime=runtime))
                scope.closes.retain(lease)
                return lease

            program.program_runner_factory = factory
            program.transport = self.transport
            return await program.launch(
                ctx, trace, runtime, endpoint, secret, mcp_urls, data)
        except BaseException:
            scope.fail()
            raise

    async def score(self, trace, runtime):
        scope = _scope(harness=self, trace=trace, runtime=runtime)
        if scope.harness_score is not None or not scope.finalized:
            scope.fail()
            _refuse()
        scope.harness_score = asyncio.current_task()
        try:
            await super().score(trace, runtime)
            scope.check(harness=self, trace=trace, runtime=runtime)
            scope.harness_success = True
        except BaseException:
            scope.fail()
            raise
        finally:
            scope.harness_done.set()


async def _drain_scope(scope):
    # Caller already stopped dispatch/reward and started ALL public closes.
    children = tuple(child for child in (
        scope.agent_task, scope.task_score, scope.harness_score)
                     if child is not None)
    for child in children:
        if not child.done():
            child.cancel()
    failure = None
    try:
        await scope.closes.join_all()
    except BaseException as exc:
        failure = exc
    # No failed close may detach another stock gather child.
    results = await asyncio.gather(*children, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError):
            if failure is None:
                failure = RuntimeError("owned SQL scoring child failed")
    if failure is not None:
        scope.fail()
        raise RuntimeError("owned SQL scope cleanup failed") from None


class OwnedSqlEnv(Env[OwnedSqlEnvConfig]):
    def __init__(self, config):
        if type(config) is not OwnedSqlEnvConfig or config.id != _ID:
            _refuse()
        admission = _admission.get()
        if admission is not None:
            admission.check()
            if config is not admission.config.env or admission.env is not None:
                _refuse()
            # Claim synchronously before loading the taskset or harness.
            admission.env = self
        super().__init__(config)

    async def run(self, task, agents):
        admission = _admission.get()
        if admission is None:
            _refuse()
        admission.check()
        _check_hooks()
        if (admission.env is not self or self.config is not admission.config.env
                or self.taskset is not admission.taskset
                or type(task) is not OwnedSqlTask):
            _refuse()
        index = next((i for i, row in enumerate(admission.tasks) if row is task), None)
        if index is None or admission.starts[index] >= admission.config.num_rollouts:
            _refuse()
        agent = agents.agent
        harness = agent.harness
        if (type(harness) is not OwnedSqlHarness
                or harness.config is not admission.config.env.agent.harness
                or task.data is not admission.bound.data[index]
                or task._private is not admission.bound.draw.eligible[index]):
            _refuse()
        admission.starts[index] += 1
        scope = _Scope(admission, task, harness, agent)
        admission.scopes.append(scope)
        token = _rollout.set(scope)
        body_error = None
        try:
            # Preserve the original Agent, harness and stock scoring lifecycle.
            # Retain its actual driver so a caller interruption reaches this
            # scope immediately, even while the owned runner is already joining
            # held cleanup inside Agent. Start all public closes before asking
            # that driver to unwind; never replace its harness or scoring loop.
            scope.agent_task = asyncio.create_task(agent.run(task))
            await asyncio.shield(scope.agent_task)
            if agent.harness is not harness:
                _refuse()
        except BaseException as exc:
            body_error = exc
            scope.fail()
            raise
        finally:
            scope.authority = False
            scope.closes.start_all()
            scope.cleanup_task = asyncio.create_task(_drain_scope(scope))
            try:
                await _settle(scope.cleanup_task)
            except asyncio.CancelledError:
                scope.fail()
                if scope.trace is not None:
                    scope.trace.ok = False
                if isinstance(body_error, asyncio.CancelledError):
                    raise body_error
                raise
            except BaseException:
                scope.fail()
                if scope.trace is not None:
                    scope.trace.ok = False
                raise
            finally:
                # _settle never returns while the cleanup task is unresolved.
                if scope.cleanup_task.done():
                    if (body_error is not None or scope.failed) and scope.trace is not None:
                        scope.trace.ok = False
                    scope.live = False
                    scope.token = None
                    _rollout.reset(token)


def _method(cls, name):
    value = inspect.getattr_static(cls, name)
    return value.__func__ if isinstance(value, (classmethod, staticmethod)) else value


def _check_hooks():
    for cls, name, original in _HOOKS:
        if _method(cls, name) is not original:
            _refuse()
    if OwnedSqlTask.scoring_deferred is not False:
        _refuse()
    for cls in (OwnedSqlTask, OwnedSqlHarness, OwnedSqlTaskset, OwnedSqlEnv):
        for base in cls.__mro__:
            for value in vars(base).values():
                if callable(value) and any(
                        hasattr(value, kind)
                        for kind in ("metric", "reward", "stop", "intercept")):
                    _refuse()


def _supported(config, bound):
    _check_hooks()
    if type(config) is not EvalConfig or type(config.env) is not OwnedSqlEnvConfig:
        _refuse()
    env = config.env
    agent = env.agent
    if (type(agent) is not AgentConfig
            or type(env.taskset) is not OwnedSqlTasksetConfig
            or type(agent.harness) is not OwnedSqlHarnessConfig
            or env.id != _ID or env.taskset.id != _ID or agent.harness.id != _ID):
        _refuse()
    if (any(getattr(config, flag) is not False for flag in ("resume", "push", "clean"))
            or config.dry_run is not False or config.run.attach is not None
            or type(config.num_rollouts) is not int or config.num_rollouts < 1
            or config.shuffle is not False
            or config.num_tasks is not None and (
                type(config.num_tasks) is not int
                or config.num_tasks != len(bound.data))):
        _refuse()
    if (type(config.max_concurrent) is not int or config.max_concurrent < 1
            or type(env.retries.max_retries) is not int
            or env.retries.max_retries != 0
            or type(agent.retries.max_retries) is not int
            or agent.retries.max_retries != 0
            or type(env.interception) is not InterceptionServerConfig
            or env.taskset.system_prompt is not None):
        _refuse()
    task_config = env.taskset.task
    if (type(task_config) is not TaskConfig or task_config.judges
            or task_config.metrics or task_config.rewards or task_config.stops):
        _refuse()
    harness = agent.harness
    if (type(harness.max_turns) is not int
            or harness.max_turns != bound.instrument.action_cap
            or type(harness.program_timeout) not in (int, float)
            or harness.program_timeout != 5
            or type(agent.max_turns) is not int
            or agent.max_turns != bound.instrument.action_cap
            or harness.mcp_header_env or harness.skills or harness.env
            or harness.forward_env or harness.disabled_tools is not None):
        _refuse()


# Original hook identities are admission invariants, never invoked to check a
# substituted hook. Base methods are included to refuse inherited rewrites too.
_HOOKS = tuple(
    (cls, name, _method(cls, name))
    for cls, names in (
        (OwnedSqlTask, ("setup", "finalize", "score", "toolsets", "hooks",
                        "stage_verifier", "runtime_env", "with_system_prompt")),
        (OwnedSqlTaskset, ("__init__", "load", "head", "view", "shuffle",
                           "task_type", "toolsets", "__iter__")),
        (OwnedSqlHarness, ("__init__", "setup", "launch", "score", "session", "cleanup")),
        (OwnedSqlEnv, ("__init__", "run", "setup", "finalize", "complete")),
        (Task, ("setup", "finalize", "score", "toolsets")),
        (Harness, ("setup", "score", "cleanup")),
        (PTCHarness, ("launch",)),
        (Taskset, ("head", "view", "shuffle", "__iter__")),
    )
    for name in names
)


async def run_registered_owned_sql_eval(
    config: EvalConfig, *, binding: RegisteredOwnedSqlBinding,
) -> list[Episode]:
    """Single-use admission around the unchanged evaluator and JSONL writer.

    Returned eligible-task rewards are not planned-denominator BIRD accuracy.
    No policy, model, profile, provider or corpus is selected here.
    """
    if type(binding) is not RegisteredOwnedSqlBinding or _admission.get() is not None:
        _refuse()
    bound = getattr(binding, "_RegisteredOwnedSqlBinding__state", None)
    if type(bound) is not _BoundDraw or bound.holder is not binding or bound.used:
        _refuse()
    bound.check()
    _supported(config, bound)
    bound.used = True
    admission = _Admission(config, bound)
    token = _admission.set(admission)
    try:
        episodes = await run_eval(config)
        admission.check()
        if (type(episodes) is not list
                or len(episodes) != len(bound.data) * config.num_rollouts):
            _refuse()
        for task, data in zip(admission.tasks, bound.data, strict=True):
            samples = [episode for episode in episodes if episode.task.data is data]
            if (len(samples) != config.num_rollouts
                    or any(type(episode) is not Episode
                           or episode.task.type != type(task).__name__
                           or episode.task.key != task.key
                           or episode.task.hash != task.hash for episode in samples)):
                _refuse()
        if len(admission.tasks) != len(bound.data):
            _refuse()
        # Failed/unscored episodes need not reach Env.run (SDK setup can fail
        # earlier). Successful records must correspond to a fully drained scope.
        for episode in episodes:
            if episode.ok or any(trace.ok for trace in episode.traces):
                matches = [scope for scope in admission.scopes
                           if scope.data is episode.task.data
                           and any(scope.trace is trace for trace in episode.traces)]
                if (len(matches) != 1 or matches[0].live or matches[0].failed
                        or not matches[0].published
                        or matches[0].cleanup_task is None
                        or not matches[0].cleanup_task.done()):
                    _refuse()
        return episodes
    finally:
        admission.active = False
        _admission.reset(token)
