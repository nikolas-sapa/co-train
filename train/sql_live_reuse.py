"""Explicit private PTC evaluation custody, not policy/native qualification."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from verifiers.v1.agent import Agent, _EpisodeAgent
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.task import TaskConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.episode import Episode
from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.utils.generic import deep_merge

from bench.bird_sdk_driver import SqlScoreReceipt
from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_isolation as core
from ptc.bash_owned_runtime import join_owned
from ptc.harness import PTCHarness, PTCHarnessConfig, _close_program_runner
from ptc.sql_owned_program import _ProgramRetention, _json_digest
from ptc.sql_owned_score import OwnedSqlScorer, build_owned_sql_scorer
from train import sql_capture
from train.sql_episodes import InstrumentSettings, _validate_instrument
from train.sql_skill_eval import SkillCase
from train.sql_skill_pilot import ApprovedSkill

if TYPE_CHECKING:
    from bench.bird_bash_live import BashTaskResources
    from train.sql_scientific_readiness import SqlReuseRequest, SqlScientificPlan
    from train.sql_experiment_runner import ScientificOperation
    from collections.abc import Callable

_PLUGIN = "cotrain_bird_sql_live"
_HARNESS = "cotrain_bird_sql_harness"
_TASK_SCORE = Task.score
_AGENT_RUNS = (Agent.run, _EpisodeAgent.run)
_ACTIVE_SCOPE: ContextVar[_Scope | None] = ContextVar("private_sql_live_scope", default=None)
_ACTIVE_ASSOCIATION: ContextVar[_Association | None] = ContextVar(
    "private_sql_live_episode", default=None)


class SqlLiveError(ValueError):
    """An inadmissible or incomplete private evaluation, never a guessed reward."""


def _require(condition, message):
    if not condition:
        raise SqlLiveError(message)


@dataclass(frozen=True)
class SqlLiveInput:
    task: SqlTask
    schema: str
    db_sha256: str
    reuse_case: SkillCase | None = None


@dataclass(frozen=True)
class SqlLivePlan:
    inputs: tuple[SqlLiveInput, ...]


@dataclass(frozen=True)
class SqlLivePolicy:
    agent: AgentConfig
    context: ModelContext


@dataclass(frozen=True)
class SqlLiveCapture:
    corpus_id: str
    split_id: str
    run_id: str
    policy_id: str
    policy_revision: str

    def __post_init__(self):
        for value in (self.corpus_id, self.split_id, self.run_id,
                      self.policy_id, self.policy_revision):
            _require(type(value) is str and bool(value.strip()),
                     "explicit capture identity required")


@dataclass(frozen=True)
class SqlLiveResult:
    episodes: tuple[Episode, ...]
    receipts: tuple[SqlScoreReceipt, ...]
    captures: tuple[sql_capture.SqlCapture, ...] = ()
    _associations: tuple[_Association, ...] = field(default=(), repr=False, compare=False)


def _context_state(ctx):
    _require(type(ctx) is ModelContext, "original model context required")
    return ctx.model, type(ctx.client), _json_digest(ctx.client), _json_digest(ctx.sampling)


def _valid_result(result):
    _require(type(result) is ExResult and result.valid is True
             and type(result.score) in (int, float) and result.score in (0, 1)
             and result.status in {
                 "match", "mismatch", "pred_error", "pred_timeout",
                 "pred_truncated", "pred_empty"}
             and result.score == (1 if result.status == "match" else 0)
             and type(result.detail) is str
             and all(type(n) is int and n >= 0
                     for n in (result.n_pred_rows, result.n_gold_rows)),
             "invalid original EX result")


def _scope():
    scope = _ACTIVE_SCOPE.get()
    _require(type(scope) is _Scope, "private SQL host scope required")
    scope.check()
    return scope


class _Scope:
    def __init__(self, plan, config, executor, instrument, expected_policy, approved_skill,
                 capture=None, bash_resources=None):
        from bench.bird_sdk_live import BirdSqlEnvConfig

        _require(type(plan) is SqlLivePlan and type(plan.inputs) is tuple
                 and bool(plan.inputs), "nonempty private SQL plan required")
        _require(type(config) is EvalConfig and type(config.env) is BirdSqlEnvConfig
                 and type(config.env.taskset) is TasksetConfig
                 and type(config.env.taskset.task) is TaskConfig,
                 "original product configuration required")
        _require(type(executor) is core.PilotExecutor
                 and type(instrument) is InstrumentSettings,
                 "concrete SQL executor and instrument required")
        _validate_instrument(instrument)
        _require(type(expected_policy) is SqlLivePolicy
                 and type(expected_policy.agent) is AgentConfig,
                 "independent expected policy required")
        _require(approved_skill is None or type(approved_skill) is ApprovedSkill,
                  "original host approval required")
        _require(capture is None or type(capture) is SqlLiveCapture,
                 "explicit original capture settings required")
        self.bash_resources = self._bash_resources = bash_resources
        self._bash_states = ()
        if bash_resources is not None:
            from bench.bird_bash_live import BashTaskResources

            _require(type(bash_resources) is tuple
                     and len(bash_resources) == len(plan.inputs)
                     and capture is None and approved_skill is None,
                     "Bash capture and approval unsupported")
            for row, resources in zip(plan.inputs, bash_resources):
                _require(type(resources) is BashTaskResources and resources.input is row
                         and row.reuse_case is None, "ordered Bash input binding differs")
                resources.check()
            _require(len({str(item.scratch) for item in bash_resources}) == len(bash_resources),
                     "unique Bash physical custody required")
            self._bash_states = tuple(self._bash_state(item) for item in bash_resources)
        if capture is not None:
            _require((instrument.source_paths, instrument.source_sha256)
                     == sql_capture._owned_sources(), "actual capture source binding differs")
        self.capture = self._capture = capture
        self._capture_state = core.canonical_json_bytes(capture)
        self.plan, self.config = plan, config
        self.executor, self.instrument = executor, instrument
        self.expected_policy, self.approved_skill = expected_policy, approved_skill
        self._host_objects = (plan, config, executor, instrument, expected_policy)
        self._inputs, self._approval = plan.inputs, approved_skill
        self.private = {}
        for row in plan.inputs:
            _require(type(row) is SqlLiveInput and type(row.task) is SqlTask
                     and type(row.schema) is str and bool(row.schema)
                     and row.task.name not in self.private,
                     "private SQL membership invalid")
            core._digest(row.db_sha256)
            _require((approved_skill is None and row.reuse_case is None)
                     or (type(row.reuse_case) is SkillCase
                         and row.reuse_case.task is row.task
                         and row.reuse_case.role == "reuse"
                         and row.reuse_case.expected_db_sha256 == row.db_sha256),
                     "private reuse case differs")
            self.private[row.task.name] = row
        self._private = dict(self.private)
        self._sql_tasks = {name: row.task for name, row in self.private.items()}
        self._input_state = core.canonical_json_bytes(plan)
        self._instrument_state = core.canonical_json_bytes(instrument)
        self._config_state = _json_digest(config)
        self._expected_agent = _json_digest(expected_policy.agent)
        self._expected_context = _context_state(expected_policy.context)
        self._policy_objects = (
            expected_policy.agent, expected_policy.context, expected_policy.agent.client,
            expected_policy.context.client, expected_policy.context.sampling)
        self.tasks, self.data_states, self.associations, self.completed = {}, {}, {}, {}
        self.taskset = None
        self.live = True
        self.check()

    def check(self):
        config = self.config
        _require(self.bash_resources is self._bash_resources,
                 "Bash resource tuple changed")
        if self.bash_resources is not None:
            for row, item, state in zip(self._inputs, self.bash_resources, self._bash_states):
                _require(item.input is row and self._bash_state(item) == state,
                         "Bash resource custody changed")
                item.check()
        if self.capture is not None:
            _require((self.instrument.source_paths, self.instrument.source_sha256)
                     == sql_capture._owned_sources(), "actual capture source binding differs")
        _require(self.live and self.plan.inputs is self._inputs
                 and all(actual is original for actual, original in zip(
                     (self.plan, self.config, self.executor, self.instrument, self.expected_policy),
                     self._host_objects))
                 and self.approved_skill is self._approval
                 and self.capture is self._capture
                 and core.canonical_json_bytes(self.capture) == self._capture_state
                 and core.canonical_json_bytes(self.plan) == self._input_state
                 and core.canonical_json_bytes(self.instrument) == self._instrument_state
                 and set(self.private) == set(self._private)
                 and all(self.private[name] is row and row.task is self._sql_tasks[name]
                         for name, row in self._private.items())
                 and _json_digest(config) == self._config_state
                 and ((self.capture is None and self.bash_resources is None)
                      or all(actual is original for actual, original in zip(
                     (self.expected_policy.agent, self.expected_policy.context,
                      self.expected_policy.agent.client, self.expected_policy.context.client,
                      self.expected_policy.context.sampling), self._policy_objects)))
                 and _json_digest(self.expected_policy.agent) == self._expected_agent
                 and _context_state(self.expected_policy.context) == self._expected_context,
                 "private SQL scope changed or revoked")
        _require(config.env.id == config.env.taskset.id == _PLUGIN
                 and config.num_rollouts == 1
                 and config.num_tasks in (None, len(self.private))
                 and not config.resume and not config.clean and not config.push
                 and not config.dry_run and not config.run.attach
                 and not config.shuffle
                 and config.env.retries.max_retries == 0
                 and config.env.agent.retries.max_retries == 0
                 and config.env.taskset.system_prompt is None
                 and config.env.taskset.task == TaskConfig(),
                 "private SQL evaluation settings unsupported")
        spec = config.env.agent
        sampling = config.sampling
        if spec.sampling is not None:
            sampling = sampling.model_copy(update=deep_merge(
                sampling.model_dump(exclude_unset=True),
                spec.sampling.model_dump(exclude_unset=True)))
        resolved = spec.model_copy(update={
            "harness": spec.harness or PTCHarnessConfig(id=_HARNESS),
            "model": spec.model if spec.model is not None else config.model,
            "client": spec.client if spec.client is not None else config.client,
            "sampling": sampling})
        if self.capture is not None or self.bash_resources is not None:
            client = resolved.client
            _require({"base_url", "api_key_var"} <= client.model_fields_set
                     and type(client.base_url) is str and bool(client.base_url.strip())
                     and type(client.api_key_var) is str and bool(client.api_key_var.strip())
                     and client.api_key_var != "PRIME_API_KEY",
                     "explicit effective endpoint and non-Prime credential source required")
        _require(_json_digest(resolved) == self._expected_agent
                 and _context_state(ModelContext(
                     resolved.model, resolved.client, resolved.sampling))
                 == self._expected_context,
                 "independent policy settings differ")
        harness = resolved.harness
        if self.bash_resources is None:
            _require(type(harness) is PTCHarnessConfig and harness.id == _HARNESS
                     and not harness.skills and harness.program_timeout == 5
                     and harness.max_turns == self.instrument.action_cap
                     and self.instrument.program_timeout_s == 5,
                     "private SQL harness policy differs")
        else:
            _require(type(harness) is BashHarnessConfig and harness.id == "bash"
                     and {"id", "edit", "search"} <= harness.model_fields_set
                     and harness.edit is False and harness.search is False
                     and not harness.skills and spec.harness is harness,
                     "explicit skill-free Bash profile required")
            _require(all(_json_digest(item.runtime_config) == _json_digest(resolved.runtime)
                         for item in self.bash_resources),
                     "explicit Bash runtime configuration differs")
        if self.approved_skill is not None:
            from train import sql_skill_eval, sql_skills

            sql_skills._require_current_workflow_sources(
                self.approved_skill.promotion.binding, sql_skill_eval._ROOT,
            )

    @staticmethod
    def _bash_state(item):
        return (
            id(item), id(item.input), id(item.runtime_config), _json_digest(item.runtime_config),
            id(item.broker_config), core.canonical_json_bytes(item.broker_config),
            item.db_size_bytes, item.interpreter, str(item.scratch), item.engine_binary,
            id(item.limits), core.canonical_json_bytes(item.limits), item.source_pins)

    def register(self, task):
        from bench.bird_sdk_live import BirdBashTask, BirdSqlTask

        self.check()
        task_cls = BirdSqlTask if self.bash_resources is None else BirdBashTask
        _require(type(task) is task_cls, "original SQL task identity differs")
        name = task.data.name
        _require(name in self.private and name not in self.tasks,
                 "original SQL task already registered or unknown")
        self.tasks[name] = task
        self.data_states[name] = (
            task.data, _json_digest(task.data), task.config,
            task.execution_accuracy.__func__,
            tuple(getattr(task, method).__func__ for method in (
                ("setup", "finalize") if self.bash_resources is None else (
                    "setup", "finalize", "_bash_association",
                    "check_bash_request", "register_bash_response"))))

    def check_task(self, task):
        from bench.bird_sdk_live import BirdBashTask, BirdSqlTask

        self.check()
        name = task.data.name
        task_cls = BirdSqlTask if self.bash_resources is None else BirdBashTask
        _require(type(task) is task_cls and self.tasks.get(name) is task,
                 "original SQL task identity differs")
        data, snapshot, config, reward_method, lifecycle = self.data_states[name]
        _require(type(task.data) is TaskData and task.data is data
                 and _json_digest(data) == snapshot and not data.skills
                 and task.config is config and config == TaskConfig()
                 and not task.scoring_deferred
                 and task.score.__self__ is task and task.score.__func__ is _TASK_SCORE
                 and task.execution_accuracy.__self__ is task
                 and task.execution_accuracy.__func__ is reward_method
                 and reward_method is task_cls.execution_accuracy,
                  "original SQL task behavior differs")
        methods = (("setup", "finalize") if self.bash_resources is None else (
            "setup", "finalize", "_bash_association",
            "check_bash_request", "register_bash_response"))
        _require(len(lifecycle) == len(methods), "original SQL lifecycle binding differs")
        for method, original in zip(methods, lifecycle):
            bound = getattr(task, method)
            _require(bound.__self__ is task and bound.__func__ is original
                     and original is getattr(task_cls, method),
                     "original SQL lifecycle method differs")

    def finish(self, episodes):
        self.check()
        _require(set(self.tasks) == set(self.private)
                 and set(self.completed) == set(self.private)
                 and len(episodes) == len(self.private),
                  "whole SQL episode coverage differs")
        _require(tuple(episode.task.data.name for episode in episodes)
                 == tuple(self.private), "whole SQL task order differs")
        receipts, seen = [], set()
        for episode in episodes:
            name = episode.task.data.name
            _require(name not in seen and self.completed.get(name) is episode
                     and type(episode) is Episode and episode.ok and not episode.errors,
                     "original whole SQL episode differs")
            seen.add(name)
            association = self.associations[name]
            association.check(retired=True)
            association.check_trace(association.trace)
            receipt = association.receipt
            _require(len(episode.traces) == 1 and episode.traces[0] is association.trace
                     and type(receipt) is SqlScoreReceipt
                     and receipt.trace is association.trace
                     and receipt.result is association.result,
                     "original SQL trace receipt join differs")
            _valid_result(receipt.result)
            trace = receipt.trace
            reward = trace.rewards.get("execution_accuracy")
            _require(trace.ok and not trace.errors and set(trace.rewards) == {"execution_accuracy"}
                     and reward is not None and reward.score == receipt.result.score
                     and reward.weight == 1,
                     "original SQL reward differs")
            receipts.append(receipt)
        captures = (() if self.capture is None else tuple(
            self.associations[episode.task.data.name].capture for episode in episodes))
        _require(all(type(capture) is sql_capture.SqlCapture for capture in captures),
                 "whole SQL capture coverage differs")
        return SqlLiveResult(
            tuple(episodes), tuple(receipts), captures,
            () if self.capture is None else tuple(
                self.associations[episode.task.data.name] for episode in episodes))


class _Association:
    def __init__(self, scope, task, agent):
        scope.check_task(task)
        _require(type(agent) in (Agent, _EpisodeAgent), "original SDK agent required")
        self.scope, self.task, self.agent = scope, task, agent
        self.row = scope.private[task.data.name]
        self.config, self.ctx, self.harness = agent.config, agent.ctx, agent.harness
        bash = scope.bash_resources is not None
        _require(type(self.config) is AgentConfig
                 and type(self.harness) is (BashHarness if bash else PTCHarness)
                 and type(self.harness.config) is (
                     BashHarnessConfig if bash else PTCHarnessConfig)
                 and self.harness.config is self.config.harness
                 and not self.harness.config.skills and not task.data.skills,
                 "original skill-free harness required")
        self.client, self.sampling = self.ctx.client, self.ctx.sampling
        self.harness_config = self.harness.config
        self.runtime, self.timeout, self.limits = agent.runtime_config, agent.timeout, agent.limits
        self.run_method = agent.run.__func__
        self.scorer = build_owned_sql_scorer(
            task=self.row.task, executor=scope.executor,
            db_sha256=self.row.db_sha256, instrument=scope.instrument)
        self.original_scorer = self.scorer
        self._scorer_methods = tuple(getattr(self.scorer, name).__func__ for name in (
            "admit", "score_sql", "aclose", "_check_binding"))
        self.executor, self.instrument = scope.executor, scope.instrument
        self.trace = self.receipt = self.result = None
        self.original_trace = None
        self.retention = (None if scope.capture is None else _ProgramRetention(
            scope.instrument.action_cap))
        self._retention = self.retention
        self.capture = None
        self.bash_resources = self._bash_bound = None
        self._bash_objects = None
        self.runtime_view = self._runtime_view = None
        self.score_ready = False
        self._controller = None
        self._owner_config = self._owner_info = None
        self.live = True
        self.callback = self.check
        self.host_authority = self._host_authority = self._check_host
        self.check()

    def check(self, *, retired=False):
        self.scope.check_task(self.task)
        agent, scope = self.agent, self.scope
        _require((self.live or retired)
                 and self.retention is self._retention
                 and (self.retention is None
                      or self.retention.action_cap == scope.instrument.action_cap)
                 and scope.executor is self.executor and scope.instrument is self.instrument
                 and scope.private[self.task.data.name] is self.row
                 and agent.config is self.config and agent.ctx is self.ctx
                 and agent.harness is self.harness
                 and self.harness.config is self.config.harness is self.harness_config
                 and self.ctx.client is self.client and self.ctx.sampling is self.sampling
                 and agent.runtime_config is self.runtime and agent.timeout is self.timeout
                 and agent.limits is self.limits
                 and agent.run.__self__ is agent and agent.run.__func__ is self.run_method
                 and self.run_method in _AGENT_RUNS
                 and _json_digest(self.config) == scope._expected_agent
                 and _context_state(self.ctx) == scope._expected_context
                 and not self.harness.config.skills
                 and type(self.scorer) is OwnedSqlScorer
                 and self.scorer is self.original_scorer
                 and self.scorer._task is self.row.task
                 and self.scorer._executor is self.executor
                 and self.scorer._instrument is self.instrument,
                 "actual SQL episode association differs")
        self.scorer._check_binding()
        _require(all(getattr(self.scorer, name).__self__ is self.scorer
                     and getattr(self.scorer, name).__func__ is original
                     and getattr(OwnedSqlScorer, name) is original
                     for name, original in zip(
                         ("admit", "score_sql", "aclose", "_check_binding"),
                         self._scorer_methods)),
                 "original SQL scorer methods differ")
        if self.trace is not None:
            self.check_trace(self.trace)
        if type(self.harness) is PTCHarness and self.harness._owned_bound:
            _require(self.harness.host_authority is self.callback,
                     "actual SQL host callback differs")
        if self.bash_resources is not None:
            bound = self.bash_resources
            _require(bound is self._bash_bound
                     and all(actual is original for actual, original in zip(
                         (bound.spec, bound.task, bound.agent, bound.harness,
                          bound.binding, bound.owner), self._bash_objects))
                     and bound.spec is scope.bash_resources[tuple(scope.private).index(
                         self.task.data.name)]
                     and bound.task is self.task and bound.agent is self.agent
                     and bound.harness is self.harness
                     and bound.owner.harness is self.harness
                     and bound.owner.binding is bound.binding
                     and bound.owner.config is self._owner_config
                     and bound.owner.info is self._owner_info
                     and _json_digest(bound.owner.config) == _json_digest(
                         bound.spec.runtime_config)
                     and bound.owner.interpreter == bound.spec.interpreter
                     and bound.owner.engine_binary == bound.spec.engine_binary
                     and bound.owner.scratch == bound.spec.scratch
                     and bound.owner.limits is bound.spec.limits
                     and bound.binding._task is self.task
                     and bound.binding._harness is self.harness
                     and bound.binding.host_authority is self.host_authority
                     and self.host_authority is self._host_authority
                     and (self._controller is None
                          or bound.owner.controller is self._controller),
                     "actual Bash resource association differs")
            if self.runtime_view is not None:
                self._check_runtime_view(self.runtime_view)

    def _check_host(self):
        _require(_ACTIVE_SCOPE.get() is self.scope
                 and _ACTIVE_ASSOCIATION.get() in (None, self)
                 and self.scope.associations.get(self.task.data.name) is self,
                 "actual Bash host context differs")
        # Deliberately excludes binding/runtime validation: both call back here.
        self.check(retired=not self.live)

    async def prepare_execution(self):
        self.check()
        if self.scope.bash_resources is None:
            return
        from bench.bird_bash_live import _bind_resources, require_production_bash_runtime

        _require(self.bash_resources is None, "Bash owner already allocated")
        require_production_bash_runtime(None)
        spec = self.scope.bash_resources[tuple(self.scope.private).index(self.task.data.name)]
        self.bash_resources = self._bash_bound = _bind_resources(self, spec)
        self._bash_objects = (
            spec, self.task, self.agent, self.harness,
            self.bash_resources.binding, self.bash_resources.owner)
        owner = self.bash_resources.owner
        self._owner_config, self._owner_info = owner.config, owner.info
        require_production_bash_runtime(owner)
        self.check()
        await owner.start()
        self._controller = owner.controller
        _require(self._controller is not None and self._controller.runtime is owner,
                 "original Bash controller owner required")
        self.check()

    def _check_runtime_view(self, view):
        owner = self.bash_resources.owner
        _require(view is self.runtime_view is self._runtime_view
                 and view is not owner and type(view) is type(owner)
                 and view.__dict__ is owner.__dict__
                 and view.env is not owner.env
                 and view.config is owner.config and view.info is owner.info
                 and view.binding is self.bash_resources.binding
                 and view.harness is self.harness
                 and view.controller is self._controller
                 and self._controller.runtime is owner,
                 "actual borrowed Bash view differs")

    def attach_runtime_view(self, view):
        if self.scope.bash_resources is None:
            return
        _require(self.bash_resources is not None and self.runtime_view is None,
                 "one original borrowed Bash view required")
        self.runtime_view = self._runtime_view = view
        self._check_runtime_view(view)

    def check_request(self, trace):
        self.host_authority()
        self.check_trace(trace)
        if self.bash_resources is not None:
            self._check_runtime_view(self.runtime_view)
            self.bash_resources.binding.check_binding()
            self.bash_resources.owner.controller.check()

    def register_response(self, response, trace):
        self.check_request(trace)
        if self.bash_resources is not None:
            self.bash_resources.owner.controller.register_response(response)
            self.check_request(trace)

    async def finalize_execution(self, trace, view):
        self.check()
        self.check_trace(trace)
        if self.bash_resources is None:
            return
        self._check_runtime_view(view)
        await self.bash_resources.owner.controller.aclose()
        self.host_authority()
        await view.teardown()
        self.host_authority()
        view.require_valid()
        self.bash_resources.owner.require_valid()
        self.score_ready = True

    def require_score_ready(self):
        self.check()
        if self.scope.bash_resources is not None:
            _require(self.score_ready is True, "Bash retirement must precede scoring")
            self._check_runtime_view(self.runtime_view)
            self.runtime_view.require_valid()
            self.bash_resources.owner.require_valid()

    async def aclose(self):
        errors = []
        if self._bash_objects is not None:
            binding, owner = self._bash_objects[-2:]
            for target, name in ((self._controller, "aclose"),
                                 (binding, "aclose"), (owner, "stop")):
                if target is None:
                    continue
                try:
                    operation = getattr(target, name)
                    await join_owned(asyncio.create_task(operation()))
                except BaseException as error:
                    errors.append(error)
        try:
            await _close_program_runner(self.original_scorer)
        except BaseException as error:
            errors.append(error)
        if errors:
            if self._bash_objects is not None:
                errors[0]._sql_live_association = self
            for secondary in errors[1:]:
                errors[0].add_note(f"secondary cleanup: {type(secondary).__name__}")
            raise errors[0]

    def check_trace(self, trace):
        _require(type(trace) is Trace and trace is self.trace is self.original_trace
                 and trace.task.data is self.task.data
                 and trace.task.type == type(self.task).__name__
                 and trace.task.key == self.task.key and trace.task.hash == self.task.hash
                 and trace.agent.config is self.config
                 and _json_digest(trace.agent.config) == self.scope._expected_agent,
                  "actual SQL trace identity differs")


async def run_sql_live(
    plan: SqlLivePlan, config: EvalConfig, *, executor: core.PilotExecutor,
    instrument: InstrumentSettings, expected_policy: SqlLivePolicy,
    approved_skill: ApprovedSkill | None = None,
    allow_execution: bool = False, allow_model_requests: bool = False,
    capture: SqlLiveCapture | None = None,
    bash_resources: tuple[BashTaskResources, ...] | None = None,
) -> SqlLiveResult:
    _require(allow_execution is True and allow_model_requests is True,
             "explicit execution and model-request opt-ins required")
    _require(_ACTIVE_SCOPE.get() is None, "nested private SQL scope refused")
    if bash_resources is not None:
        from bench.bird_bash_live import require_production_bash_runtime

        require_production_bash_runtime(None)
    scope = _Scope(
        plan, config, executor, instrument, expected_policy, approved_skill,
        capture, bash_resources)
    token = _ACTIVE_SCOPE.set(scope)
    try:
        episodes = await run_eval(config)
        return scope.finish(episodes)
    finally:
        scope.live = False
        _ACTIVE_SCOPE.reset(token)


async def run_sql_live_plan(
    plan: SqlScientificPlan, *, operation: ScientificOperation,
    approve: Callable[[SqlReuseRequest], bool] | None,
    executor_factory: Callable[[SqlReuseRequest], core.PilotExecutor],
    allow_execution: bool = False, allow_model_requests: bool = False,
) -> SqlLiveResult:
    """Admit one promoted-reuse operation before constructing its executor.

    Capture-off retains original SDK episodes and the single final EX receipt.
    Capture-on promotion needs a separate instrument bridge, not rewritten pins.
    No scripted proposal/qualification is counted as live reference invocation.
    """
    from train import sql_scientific_readiness as readiness
    from train.sql_skill_pilot import validate_approval

    _require(type(plan) is readiness.SqlScientificPlan,
             "original deferred scientific plan required")
    _require(allow_execution is True and allow_model_requests is True,
             "explicit execution and model-request opt-ins required")
    plan.consume()
    _require(plan.stage == "promoted_skill_reuse",
             "promoted reuse stage required; paired operations use scientific coordinator")
    readiness.check_operation(operation)
    _require(callable(approve) and callable(executor_factory),
             "separate scientific approval and deferred executor factory required")
    request = readiness.SqlReuseRequest(
        operation, plan, len(plan.live_plan.inputs), plan.policy_identity)
    operation_state = core.canonical_json_bytes(operation)
    readiness.require_science_approval(approve(request))
    plan.check()
    _require(request.operation is operation and request.execution_plan is plan
             and request.eligible_count == len(plan.live_plan.inputs)
             and request.policy_identity == plan.policy_identity
             and type(request.num_rollouts) is int and request.num_rollouts == 1
             and core.canonical_json_bytes(operation) == operation_state,
             "scientific operation changed during approval")
    validate_approval(plan.approved_skill)
    from train import sql_skill_eval, sql_skills

    # Current controller bytes must match the retained approved binding before
    # allocating any executor. Never reissue an old approval under new sources.
    sql_skills._require_current_workflow_sources(
        plan.approved_skill.promotion.binding, sql_skill_eval._ROOT,
    )
    plan.check()
    executor = executor_factory(request)
    _require(type(executor) is core.PilotExecutor, "concrete SQL executor required")
    plan.check()
    return await run_sql_live(
        plan.live_plan, plan.config, executor=executor, instrument=plan.settings,
        expected_policy=plan.expected_policy, approved_skill=plan.approved_skill,
        capture=plan.capture, allow_execution=True, allow_model_requests=True)
