"""One-use original SDK PTC composition. Source custody is not qualification."""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.episode import Episode
from verifiers.v1.trace import Trace

from bench import paired_bird
from bench.bird_sdk_driver import SqlScoreReceipt
from ptc import sql_arms, sql_isolation as core
from train import sql_capture, sql_episodes, sql_experiment_runner, sql_live_reuse

if TYPE_CHECKING:
    from train.sql_scientific_readiness import SqlScientificPlan


class SqlScientificError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise SqlScientificError(message)


class SqlSdkScientificDriver:
    def __init__(
        self, plan: paired_bird.PairedBirdPlan, live_plan: sql_live_reuse.SqlLivePlan,
        config: EvalConfig, *, executor: core.PilotExecutor,
        instrument: paired_bird.Instrument,
        settings: sql_episodes.InstrumentSettings,
        expected_policy: sql_live_reuse.SqlLivePolicy,
        policy_identity: str, capture: sql_live_reuse.SqlLiveCapture,
        allow_execution: bool = False, allow_model_requests: bool = False,
    ):
        paired_bird._require_plan(plan)
        paired_bird._check_instrument(instrument)
        _require(allow_execution is True and allow_model_requests is True,
                 "explicit execution and model-request opt-ins required")
        _require(type(capture) is sql_live_reuse.SqlLiveCapture
                 and type(policy_identity) is str and bool(policy_identity.strip())
                 and capture.policy_id == policy_identity,
                 "explicit matching policy/capture identity required")
        _require(type(config) is EvalConfig
                 and {"model", "client"} <= config.model_fields_set
                 and type(config.model) is str and bool(config.model.strip())
                 and type(config.num_rollouts) is int and config.num_rollouts == 1,
                 "explicit original model and client configuration required")
        self.plan, self.live_plan, self.config = plan, live_plan, config
        self.executor, self.instrument, self.settings = executor, instrument, settings
        self.expected_policy, self.policy_identity = expected_policy, policy_identity
        self.capture = capture
        self._client = (config.env.agent.client if config.env.agent.client is not None
                        else config.client)
        self._check_client()
        self._validator = sql_live_reuse._Scope(
            live_plan, config, executor, settings, expected_policy, None, capture)
        self._objects = (plan, live_plan, config, executor, instrument, settings,
                         expected_policy, capture)
        self._instrument_state = core.canonical_json_bytes(instrument)
        self._plan_state = core.canonical_json_bytes(plan)
        self._profile = executor.profile
        self._profile_digest = core.execution_profile_sha256(executor.profile)
        self._state_dir = executor.state_dir
        self._execution_binding = sql_capture._execution_binding(executor)
        self._approval = None
        self._active = self._composition_started = self._dispatched = False
        self._live_result = None
        self._evidence = {}
        self._check()

    def _check_client(self):
        client = (self.config.env.agent.client
                  if self.config.env.agent.client is not None else self.config.client)
        _require(client is self._client
                 and {"base_url", "api_key_var"} <= client.model_fields_set
                 and type(client.base_url) is str and bool(client.base_url.strip())
                 and type(client.api_key_var) is str and bool(client.api_key_var.strip())
                 and client.api_key_var != "PRIME_API_KEY",
                 "explicit effective endpoint and non-Prime credential source required")

    def _check(self):
        _require(all(actual is original for actual, original in zip(
            (self.plan, self.live_plan, self.config, self.executor, self.instrument,
             self.settings, self.expected_policy, self.capture), self._objects)),
            "scientific driver binding replaced")
        self._check_client()
        self._validator.check()
        _require(core.canonical_json_bytes(self.instrument) == self._instrument_state
                 and core.canonical_json_bytes(self.plan) == self._plan_state
                 and self.executor.profile is self._profile
                 and core.execution_profile_sha256(self.executor.profile) == self._profile_digest
                 and self.executor.state_dir is self._state_dir,
                 "scientific plan/instrument changed")
        inputs, tasks = self.live_plan.inputs, self.plan.draw.eligible
        _require(len(inputs) == len(tasks)
                 and all(row.task is task and row.reuse_case is None
                         for row, task in zip(inputs, tasks)),
                 "whole ordered original task membership required")
        databases = {row.db_id: row.sha256 for row in self.plan.draw.databases}
        _require(all(row.db_sha256 == databases.get(row.task.db_id) for row in inputs),
                 "retained draw database membership differs")
        settings, instrument = self.settings, self.instrument
        _require(settings.action_cap == instrument.budget.max_turns
                 and settings.action_max_rows == instrument.action_max_rows
                 and settings.program_timeout_s == instrument.budget.program_timeout == 5
                 and settings.wrapper_timeout_s == instrument.query_timeout_s
                 == sql_arms.WRAPPER_TIMEOUT
                 and settings.scorer_timeout_s == self.plan.draw.timeout_s
                 and settings.scorer_max_rows == self.plan.draw.max_rows
                 and settings.compare == self.plan.draw.comparison
                 and self.config.env.agent.timeout.rollout
                 == instrument.budget.rollout_timeout,
                 "actual scientific execution budgets differ")
        _require(self.policy_identity == self.capture.policy_id
                 and (settings.source_paths, settings.source_sha256)
                 == sql_capture._owned_sources(),
                 "scientific policy/source identity differs")

    def _check_approval(self):
        request = self._approval
        _require(self._active and type(request) is sql_experiment_runner.ScientificRequest
                 and request.plan_id == self.plan.plan_id
                 and request.eligible_count == len(self.plan.draw.eligible)
                 and request.instrument is self.instrument
                 and request.policy_identity == self.policy_identity
                 and request.arms == ("bash", "ptc")
                 and type(request.num_rollouts) is int and request.num_rollouts == 1,
                 "original scientific wrapper approval required")
        self._check()

    def _check_request(self, request, arm):
        self._check_approval()
        _require(type(request) is paired_bird.ArmRequest and request.arm == arm
                 and request.plan_id == self.plan.plan_id
                 and request.tasks is self.plan.draw.eligible
                 and request.instrument is self.instrument
                 and request.policy_identity == self.policy_identity
                 and type(request.num_rollouts) is int and request.num_rollouts == 1,
                 "exact original scientific arm request required")

    async def run_arm(self, request: paired_bird.ArmRequest) -> AsyncIterator[paired_bird.TaskOutcome]:
        self._check_request(request, "ptc")
        _require(not self._dispatched, "PTC scientific arm already consumed")
        self._dispatched = True
        for row in self.live_plan.inputs:
            sql_episodes._check_database(row.task, row.db_sha256)
            _require(sql_arms.schema_text(row.task.db_path) == row.schema,
                     "actual database schema differs")
            sql_episodes._check_database(row.task, row.db_sha256)
        self._check_approval()
        result = await sql_live_reuse.run_sql_live(
            self.live_plan, self.config, executor=self.executor,
            instrument=self.settings, expected_policy=self.expected_policy,
            capture=self.capture, allow_execution=True, allow_model_requests=True)
        self._check_approval()
        self._live_result = result
        rows = self._retain(result)
        for row in rows:
            self._check_approval()
            yield row

    def _retain(self, result):
        _require(type(result) is sql_live_reuse.SqlLiveResult
                 and len(result.episodes) == len(result.receipts)
                 == len(result.captures) == len(result._associations)
                 == len(self.live_plan.inputs), "whole original result coverage differs")
        rows, seen = [], set()
        for item, episode, receipt, capture, association in zip(
                self.live_plan.inputs, result.episodes, result.receipts,
                result.captures, result._associations):
            _require(type(association) is sql_live_reuse._Association
                     and association.scope.plan is self.live_plan
                     and association.scope.config is self.config
                     and type(episode) is Episode and episode.ok is True
                     and not episode.errors and len(episode.traces) == 1
                     and episode.task.data.name == item.task.name
                     and association.scope.completed.get(item.task.name) is episode
                     and association.row is item and association.receipt is receipt
                     and association.capture is capture
                     and episode.task.data is association.task.data,
                     "original completed episode custody differs")
            trace = episode.traces[0]
            association.check_trace(trace)
            _require(type(trace) is Trace and trace is association.trace
                     and type(receipt) is SqlScoreReceipt and receipt.trace is trace
                     and receipt.result is association.result
                     and trace.ok is True and trace.is_completed is True and not trace.errors,
                     "original trace/EX receipt custody differs")
            sql_live_reuse._valid_result(receipt.result)
            reward = trace.rewards.get("execution_accuracy")
            _require(set(trace.rewards) == {"execution_accuracy"}
                     and reward is not None and reward.score == receipt.result.score
                     and reward.weight == 1, "original EX reward differs")
            _require(type(capture) is sql_capture.SqlCapture
                     and capture.result is receipt.result
                     and capture.ids == sql_episodes.EpisodeIds(
                         self.capture.corpus_id, self.capture.split_id, self.capture.run_id,
                         episode.id, self.policy_identity, self.capture.policy_revision)
                     and capture.task_id == item.task.name
                     and capture.task_fingerprint == sql_episodes._fingerprint(
                         sql_episodes._task_payload(item.task))
                     and capture.db_sha256 == item.db_sha256 and capture.schema == item.schema
                     and capture.prompt == episode.task.data.prompt
                     and capture.instrument is self.settings
                     and capture.execution_binding == self._execution_binding
                     and capture.terminal_label == "final_submitted"
                     and capture.execution_abort is None
                     and capture.final_answer == (trace.last_reply or ""),
                     "actual completed capture binding differs")
            sql_capture.encode_capture(capture)
            _require(episode.id not in seen and trace.id not in seen
                     and bool(episode.id) and bool(trace.id),
                     "duplicate original episode/trace IDs")
            seen.update((episode.id, trace.id))
            row = paired_bird.TaskOutcome(
                self.plan.plan_id, "ptc", item.task.name, True, True, receipt.result.status,
                (paired_bird.Metric("execution_accuracy", receipt.result.score),),
                f"sdk:{self.config.run.id}#episode={episode.id}")
            rows.append(row)
            self._evidence[id(row)] = (
                row, sql_experiment_runner.CompletedEvidence(episode, receipt, capture))
        return tuple(rows)

    def evidence_for(self, row):
        retained = self._evidence.get(id(row))
        _require(retained is not None and retained[0] is row,
                 "original PTC outcome identity required")
        return retained[1]


async def run_sql_sdk_scientific(
    driver: SqlSdkScientificDriver | SqlScientificPlan, *,
    operation: sql_experiment_runner.ScientificOperation,
    approve: Callable[[sql_experiment_runner.ScientificRequest], bool] | None,
    bash_run_arm: Callable[[paired_bird.ArmRequest], AsyncIterator[paired_bird.TaskOutcome]],
    bash_evidence_for: Callable[[paired_bird.TaskOutcome], sql_experiment_runner.CompletedEvidence],
    output_dir: Path, historical_baseline: Mapping[str, Path] | None = None,
    executor_factory: Callable[
        [sql_experiment_runner.ScientificRequest], core.PilotExecutor] | None = None,
    allow_execution: bool = False, allow_model_requests: bool = False,
) -> sql_experiment_runner.ExperimentResult:
    from train import sql_scientific_readiness as readiness

    deferred = driver if type(driver) is readiness.SqlScientificPlan else None
    _require((deferred is not None or type(driver) is SqlSdkScientificDriver)
             and callable(bash_run_arm) and callable(bash_evidence_for),
             "explicit original PTC driver and separately supplied Bash evidence required")
    if deferred is None:
        _require(executor_factory is None, "executor factory requires a deferred plan")
        _require(not driver._composition_started, "scientific composition already consumed")
        driver._composition_started = True
        driver._check()
        plan, instrument, policy_identity = driver.plan, driver.instrument, driver.policy_identity
    else:
        _require(allow_execution is True and allow_model_requests is True,
                 "explicit execution and model-request opt-ins required")
        deferred.consume()
        _require(deferred.stage == "paired_bird" and callable(executor_factory),
                 "paired scientific stage and deferred executor factory required")
        plan, instrument = deferred.paired_plan, deferred.instrument
        policy_identity = deferred.policy_identity
        driver = None

    def admission(request):
        nonlocal driver
        _require(type(request) is sql_experiment_runner.ScientificRequest
                 and request.operation is operation and request.instrument is instrument
                 and request.plan_id == plan.plan_id
                 and request.eligible_count == len(plan.draw.eligible)
                 and request.arms == ("bash", "ptc")
                 and type(request.num_rollouts) is int and request.num_rollouts == 1
                 and request.policy_identity == policy_identity
                 and callable(approve), "original scientific admission request required")
        if deferred is not None:
            deferred.check()
        operation_state = core.canonical_json_bytes(operation)
        request_state = core.canonical_json_bytes(request)
        accepted = approve(request)
        if accepted is True:
            _require(core.canonical_json_bytes(request) == request_state
                     and request.operation is operation and request.instrument is instrument
                     and core.canonical_json_bytes(operation) == operation_state,
                     "scientific operation changed during approval")
            if deferred is not None:
                deferred.check()
                _require((deferred.settings.source_paths, deferred.settings.source_sha256)
                         == sql_capture._owned_sources(),
                         "current V2 owned capture source binding differs")
                executor = executor_factory(request)
                deferred.check()
                driver = SqlSdkScientificDriver(
                    plan, deferred.live_plan, deferred.config, executor=executor,
                    instrument=instrument, settings=deferred.settings,
                    expected_policy=deferred.expected_policy, policy_identity=policy_identity,
                    capture=deferred.capture, allow_execution=True, allow_model_requests=True)
                driver._composition_started = True
            driver._approval = request
            driver._active = True
            driver._check_approval()
        return accepted

    def run_arm(request):
        driver._check_request(request, request.arm)
        _require(request.arm in ("bash", "ptc"), "unknown scientific arm")
        return driver.run_arm(request) if request.arm == "ptc" else bash_run_arm(request)

    def evidence_for(row):
        return driver.evidence_for(row) if row.arm == "ptc" else bash_evidence_for(row)

    try:
        return await sql_experiment_runner.run_sql_experiment(
            plan, instrument=instrument, policy_identity=policy_identity,
            operation=operation, approve=admission, run_arm=run_arm,
            evidence_for=evidence_for, output_dir=output_dir,
            historical_baseline=historical_baseline)
    finally:
        if driver is not None:
            driver._active = False
            driver._approval = None
