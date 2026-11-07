"""Explicit private PTC evaluation custody, not policy/native qualification."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

from verifiers.v1.agent import Agent, _EpisodeAgent
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.task import TaskConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.episode import Episode
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.utils.generic import deep_merge

from bench.bird_sdk_driver import SqlScoreReceipt
from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_isolation as core
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_owned_program import _ProgramRetention, _json_digest
from ptc.sql_owned_score import OwnedSqlScorer, build_owned_sql_scorer
from train import sql_capture
from train.sql_episodes import InstrumentSettings, _validate_instrument
from train.sql_skill_eval import SkillCase
from train.sql_skill_pilot import ApprovedSkill

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
                 capture=None):
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
                 and (self.capture is None or all(actual is original for actual, original in zip(
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
        if self.capture is not None:
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
        _require(type(harness) is PTCHarnessConfig and harness.id == _HARNESS
                 and not harness.skills and harness.program_timeout == 5
                 and harness.max_turns == self.instrument.action_cap
                 and self.instrument.program_timeout_s == 5,
                 "private SQL harness policy differs")

    def register(self, task):
        self.check()
        name = task.data.name
        _require(name in self.private and name not in self.tasks,
                 "original SQL task already registered or unknown")
        self.tasks[name] = task
        self.data_states[name] = (
            task.data, _json_digest(task.data), task.config,
            task.execution_accuracy.__func__)

    def check_task(self, task):
        from bench.bird_sdk_live import BirdSqlTask

        self.check()
        name = task.data.name
        _require(type(task) is BirdSqlTask and self.tasks.get(name) is task,
                 "original SQL task identity differs")
        data, snapshot, config, reward_method = self.data_states[name]
        _require(type(task.data) is TaskData and task.data is data
                 and _json_digest(data) == snapshot and not data.skills
                 and task.config is config and config == TaskConfig()
                 and not task.scoring_deferred
                 and task.score.__self__ is task and task.score.__func__ is _TASK_SCORE
                 and task.execution_accuracy.__self__ is task
                 and task.execution_accuracy.__func__ is reward_method
                 and reward_method is BirdSqlTask.execution_accuracy,
                 "original SQL task behavior differs")

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
        _require(type(self.config) is AgentConfig and type(self.harness) is PTCHarness
                 and type(self.harness.config) is PTCHarnessConfig
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
        self.executor, self.instrument = scope.executor, scope.instrument
        self.trace = self.receipt = self.result = None
        self.original_trace = None
        self.retention = (None if scope.capture is None else _ProgramRetention(
            scope.instrument.action_cap))
        self._retention = self.retention
        self.capture = None
        self.live = True
        self.callback = self.check
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
        if self.trace is not None:
            self.check_trace(self.trace)
        if self.harness._owned_bound:
            _require(self.harness.host_authority is self.callback,
                     "actual SQL host callback differs")

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
) -> SqlLiveResult:
    _require(allow_execution is True and allow_model_requests is True,
             "explicit execution and model-request opt-ins required")
    _require(_ACTIVE_SCOPE.get() is None, "nested private SQL scope refused")
    scope = _Scope(plan, config, executor, instrument, expected_policy, approved_skill, capture)
    token = _ACTIVE_SCOPE.set(scope)
    try:
        episodes = await run_eval(config)
        return scope.finish(episodes)
    finally:
        scope.live = False
        _ACTIVE_SCOPE.reset(token)
