"""Private deferred plans, not runtime receipts or scientific authorization.

Plans retain original host objects. No database/source inspection, allocation,
policy projection, execution or statistical design happens here. A host approval
is still cooperative authority, not a provider budget or hostile-Python boundary.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.utils.generic import deep_merge

from bench import paired_bird
from ptc import sql_arms, sql_isolation as core
from train import harness_swap_accounting, sql_episodes, sql_experiment_runner
from train import sql_live_reuse as live
from train import sql_skills
from train.sql_skill_pilot import ApprovedSkill

_LOCK = threading.Lock()


class ScienceReadinessError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ScienceReadinessError(message)


def require_science_approval(accepted):
    _require(accepted is True, "separate explicit scientific approval required")


def check_operation(operation):
    _require(type(operation) is sql_experiment_runner.ScientificOperation
             and type(operation.operation_id) is str and bool(operation.operation_id.strip())
             and type(operation.gross_budget_usd_micros) is int
             and operation.gross_budget_usd_micros > 0,
             "explicit scientific operation and positive gross budget required")


@dataclass(frozen=True, repr=False)
class SqlReuseRequest:
    operation: sql_experiment_runner.ScientificOperation
    execution_plan: SqlScientificPlan
    eligible_count: int
    policy_identity: str
    num_rollouts: int = 1


@dataclass(frozen=True, eq=False, repr=False)
class SqlScientificPlan:
    stage: str
    live_plan: live.SqlLivePlan
    config: EvalConfig
    settings: sql_episodes.InstrumentSettings
    expected_policy: live.SqlLivePolicy
    policy_identity: str
    capture: live.SqlLiveCapture | None = None
    approved_skill: ApprovedSkill | None = None
    paired_plan: paired_bird.PairedBirdPlan | None = None
    instrument: paired_bird.Instrument | None = None
    swap: harness_swap_accounting.HarnessSwapProjection | None = None
    _used: bool = field(default=False, init=False, repr=False)
    _snapshot: tuple = field(init=False, repr=False)
    _objects: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._prerequisites()
        object.__setattr__(self, "_objects", self._bindings())
        object.__setattr__(self, "_snapshot", self._state())

    def _bindings(self):
        return (self.live_plan, self.live_plan.inputs, self.config, self.settings,
                self.expected_policy, self.expected_policy.agent,
                self.expected_policy.context, self.capture, self.approved_skill,
                self.paired_plan, self.instrument, self.swap,
                self.config.client, self.config.env.agent,
                self.expected_policy.agent.client, self.expected_policy.context.client,
                self.expected_policy.context.sampling, self.config.env.agent.client)

    def _state(self):
        skill = self.approved_skill
        return (
            self.stage, self.policy_identity,
            core.canonical_json_bytes(self.live_plan),
            live._json_digest(self.config), core.canonical_json_bytes(self.settings),
            live._json_digest(self.expected_policy.agent),
            live._context_state(self.expected_policy.context),
            core.canonical_json_bytes(self.capture),
            core.canonical_json_bytes(self.paired_plan),
            core.canonical_json_bytes(self.instrument),
            core.canonical_json_bytes(self.swap),
            None if skill is None else (
                sql_skills.encode_candidate(skill.candidate),
                sql_skills.encode_promotion(skill.promotion),
                skill.promotion_sha256, str(skill.approval_path), skill.approval_sha256),
        )

    def check(self):
        _require(all(a is b for a, b in zip(self._bindings(), self._objects))
                 and self._state() == self._snapshot, "scientific inputs changed")
        self._prerequisites()

    def consume(self):
        with _LOCK:
            _require(not self._used, "scientific execution plan already consumed")
            object.__setattr__(self, "_used", True)
        self.check()
        _require(self.stage in ("paired_bird", "promoted_skill_reuse"),
                 "cross-harness/co-training requires qualified second SDK backend, "
                 "checkpoint/seed/cohort authority and separately approved training operation")

    def _prerequisites(self):
        from bench.bird_sdk_live import BirdSqlEnvConfig

        _require(self.stage in ("paired_bird", "promoted_skill_reuse",
                                "cross_harness_cotraining"), "unknown scientific stage")
        _require(type(self.live_plan) is live.SqlLivePlan
                 and type(self.live_plan.inputs) is tuple and bool(self.live_plan.inputs)
                 and all(type(row) is live.SqlLiveInput for row in self.live_plan.inputs),
                 "nonempty immutable original live inputs required")
        _require(all(type(row.task) is live.SqlTask
                     and type(row.schema) is str and bool(row.schema)
                     for row in self.live_plan.inputs), "original public input metadata required")
        for row in self.live_plan.inputs:
            core._digest(row.db_sha256)
        _require(type(self.settings) is sql_episodes.InstrumentSettings
                 and type(self.expected_policy) is live.SqlLivePolicy
                 and type(self.expected_policy.agent) is live.AgentConfig,
                 "original instrument and independent policy required")
        sql_episodes._validate_instrument(self.settings)
        _require(type(self.config) is EvalConfig
                 and type(self.config.env) is BirdSqlEnvConfig
                 and type(self.config.env.taskset) is live.TasksetConfig
                 and type(self.config.env.taskset.task) is live.TaskConfig
                 and {"model", "client"} <= self.config.model_fields_set
                 and type(self.config.model) is str and bool(self.config.model.strip())
                 and type(self.config.num_rollouts) is int and self.config.num_rollouts == 1,
                 "explicit original model/client and one rollout required")
        _require(type(self.policy_identity) is str and bool(self.policy_identity.strip()),
                 "explicit policy identity required")
        agent = self.config.env.agent
        client = agent.client if agent.client is not None else self.config.client
        _require({"base_url", "api_key_var"} <= client.model_fields_set
                 and type(client.base_url) is str and bool(client.base_url.strip())
                 and type(client.api_key_var) is str and bool(client.api_key_var.strip())
                 and client.api_key_var != "PRIME_API_KEY",
                 "explicit effective endpoint and non-Prime credential source required")
        sampling = self.config.sampling
        if agent.sampling is not None:
            sampling = sampling.model_copy(update=deep_merge(
                sampling.model_dump(exclude_unset=True),
                agent.sampling.model_dump(exclude_unset=True)))
        resolved = agent.model_copy(update={
            "harness": agent.harness or live.PTCHarnessConfig(id=live._HARNESS),
            "model": agent.model if agent.model is not None else self.config.model,
            "client": client, "sampling": sampling})
        _require(type(resolved.model) is str and bool(resolved.model.strip())
                 and live._json_digest(resolved) == live._json_digest(self.expected_policy.agent)
                 and live._context_state(live.ModelContext(
                     resolved.model, client, sampling))
                 == live._context_state(self.expected_policy.context),
                 "independent policy settings differ")
        names = tuple(row.task.name for row in self.live_plan.inputs)
        _require(len(set(names)) == len(names), "duplicate live task membership")
        config = self.config
        _require(config.env.id == config.env.taskset.id == live._PLUGIN
                 and config.num_tasks in (None, len(names))
                 and not config.resume and not config.clean and not config.push
                 and not config.dry_run and not config.run.attach and not config.shuffle
                 and config.env.retries.max_retries == agent.retries.max_retries == 0
                 and config.env.taskset.system_prompt is None
                 and config.env.taskset.task == live.TaskConfig(),
                 "private SQL evaluation settings unsupported")
        harness = resolved.harness
        _require(type(harness) is live.PTCHarnessConfig and harness.id == live._HARNESS
                 and not harness.skills and harness.program_timeout == 5
                 and harness.max_turns == self.settings.action_cap
                 and self.settings.program_timeout_s == 5,
                 "private SQL harness policy differs")
        if self.capture is not None:
            _require(type(self.capture) is live.SqlLiveCapture
                     and self.capture.policy_id == self.policy_identity,
                     "capture policy identity differs")
        if self.stage == "paired_bird":
            _require(self.approved_skill is None and self.capture is not None,
                     "paired baseline requires capture and no promoted skill")
            paired_bird._require_plan(self.paired_plan)
            paired_bird._check_instrument(self.instrument)
            self._paired_membership()
            databases = {row.db_id: row.sha256 for row in self.paired_plan.draw.databases}
            _require(all(row.db_sha256 == databases.get(row.task.db_id)
                         for row in self.live_plan.inputs),
                     "retained draw database membership differs")
            budget = self.instrument.budget
            _require(self.settings.action_cap == budget.max_turns
                     and self.settings.action_max_rows == self.instrument.action_max_rows
                     and self.settings.program_timeout_s == budget.program_timeout == 5
                     and self.settings.wrapper_timeout_s == self.instrument.query_timeout_s
                     == sql_arms.WRAPPER_TIMEOUT
                     and self.settings.scorer_timeout_s == self.paired_plan.draw.timeout_s
                     and self.settings.scorer_max_rows == self.paired_plan.draw.max_rows
                     and self.settings.compare == self.paired_plan.draw.comparison
                     and agent.timeout.rollout == budget.rollout_timeout,
                     "scientific execution budgets differ")
        elif self.stage == "promoted_skill_reuse":
            _require(self.paired_plan is None and self.instrument is None
                     and type(self.approved_skill) is ApprovedSkill,
                     "separate original promoted skill approval required")
            self._reuse_membership()
        else:
            _require(self.swap is None
                     or type(self.swap) is harness_swap_accounting.HarnessSwapProjection,
                     "original cross-harness projection required")

    def _paired_membership(self):
        inputs, tasks = self.live_plan.inputs, self.paired_plan.draw.eligible
        _require(len(inputs) == len(tasks)
                 and all(row.task is task and row.reuse_case is None
                         for row, task in zip(inputs, tasks)),
                 "whole ordered original paired task membership required")

    def _reuse_membership(self):
        skill = self.approved_skill
        candidate, promotion = skill.candidate, skill.promotion
        _require(sql_skills._sha(sql_skills.encode_promotion(promotion))
                 == skill.promotion_sha256
                 and sql_skills._sha(sql_skills.encode_candidate(candidate))
                 == promotion.candidate_sha256
                 and candidate.scope == promotion.scope and candidate.source == promotion.source
                 and promotion.schema_version == 2
                 and self.policy_identity == candidate.source.ids.policy_id
                 and self.settings == promotion.binding.instrument,
                 "candidate/source/approved promotion binding differs")
        # Existing owned-capture projection requires _owned_sources(), whereas
        # admit_promoted_reuse binds _current_binding().instrument (capture
        # sources). Neither pin may be rewritten to make these compare equal.
        _require(self.capture is None,
                 "promoted reuse capture requires an owned-capture instrument bridge; "
                 "capture-off reuse retains original SDK episodes and EX receipts")
        references = (promotion.source,) + promotion.qualifications
        identities = set()
        for row in self.live_plan.inputs:
            case = row.reuse_case
            _require(type(case) is live.SkillCase and case.task is row.task
                     and case.role == "reuse" and case.expected_db_sha256 == row.db_sha256,
                     "ordered original reuse case binding differs")
            scope = sql_skills.SkillScope(row.task.source, row.task.shape, row.task.coarse_shape)
            fingerprint = sql_episodes._fingerprint(sql_episodes._task_payload(row.task))
            _require(scope == candidate.scope
                     and sql_skills._provenance(case.ids)
                     == sql_skills._provenance(candidate.source.ids)
                     and case.ids.split_id not in {ref.ids.split_id for ref in references}
                     and fingerprint not in {ref.task_fingerprint for ref in references}
                     and row.db_sha256 not in {ref.db_sha256 for ref in references}
                     and sql_skills._identity(case.ids) not in identities,
                     "reuse source/qualification leakage or policy identity differs")
            identities.add(sql_skills._identity(case.ids))


def cross_harness_readiness(planned_task_ids, left, right):
    """Carry existing diagnostics, never upgrade scripted declarations to science."""
    projection = harness_swap_accounting.project_harness_swap(planned_task_ids, left, right)
    return projection, (
        "qualified_second_sdk_backend_unavailable",
        "independent_checkpoint_seed_cohort_authority_unavailable",
        "separate_scientific_training_authorization_required",
    )
