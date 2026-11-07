"""UNRUN source tests. Real SDK loop, synthetic HTTP/actor outcomes, no native proof."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace

import httpx
import pytest

from verifiers.v1.agent import _EpisodeAgent
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.clients import ModelContext
from verifiers.v1.clients.eval import EvalClient
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.episode import Episode
from verifiers.v1.task import TaskData, task_key
from verifiers.v1.trace import AgentInfo, Reward, Trace, TraceTask, VersionInfo
from verifiers.v1.utils import loaders

from bench import paired_bird
from bench.bird_sdk_driver import SqlScoreReceipt
from bench.bird_sdk_live import BirdSqlEnv, BirdSqlTaskset
from bench.score import ExResult
from bench.test_bird_sdk_live_product import _case, _execution_fixture
from bench.test_paired_bird import _instrument, _plan
from ptc import sql_arms, sql_isolation as core, sql_owned_program
from ptc import harness as ptc_harness
from ptc.harness import PTCHarness, ProgramInfrastructureError
from ptc.runtime import Catalog
from ptc.sql_owned_score import OwnedSqlScorer, ScoreInfrastructureError
from train import sql_capture, sql_episodes, sql_experiment_runner as experiment
from train import sql_live_reuse as live
from train import sql_sdk_scientific as scientific


@pytest.fixture(autouse=True)
def restore_vf_run_id():
    present, value = "VF_RUN_ID" in os.environ, os.environ.get("VF_RUN_ID")
    try:
        yield
    finally:
        if present:
            os.environ["VF_RUN_ID"] = value
        else:
            os.environ.pop("VF_RUN_ID", None)


def _driver(tmp_path, **changes):
    case = _case(tmp_path)
    plan = _plan(tmp_path)
    instrument = _instrument(paired_bird)
    config = case.config
    config.num_tasks = len(plan.draw.eligible)
    config.env.agent.harness.max_turns = instrument.budget.max_turns
    config.env.agent.timeout.rollout = instrument.budget.rollout_timeout
    paths, digest = sql_capture._owned_sources()
    settings = replace(
        case.instrument, action_cap=instrument.budget.max_turns,
        action_max_rows=instrument.action_max_rows,
        scorer_timeout_s=plan.draw.timeout_s, scorer_max_rows=plan.draw.max_rows,
        compare=plan.draw.comparison, source_paths=paths, source_sha256=digest)
    databases = {row.db_id: row.sha256 for row in plan.draw.databases}
    case.plan = live.SqlLivePlan(tuple(
        live.SqlLiveInput(task, sql_arms.schema_text(task.db_path), databases[task.db_id])
        for task in plan.draw.eligible))
    expected = config.env.agent.model_copy(deep=True, update={
        "model": config.model, "client": config.client.model_copy(deep=True),
        "sampling": config.sampling.model_copy(deep=True)})
    case.policy = live.SqlLivePolicy(expected, ModelContext(
        config.model, config.client.model_copy(deep=True),
        config.sampling.model_copy(deep=True)))
    case.instrument = settings
    arguments = dict(
        executor=case.fixture.executor, instrument=instrument, settings=settings,
        expected_policy=case.policy, policy_identity="synthetic-policy",
        capture=live.SqlLiveCapture("fixture", "dev", "fixture-run",
                                    "synthetic-policy", "fixture-revision"),
        allow_execution=True, allow_model_requests=True)
    arguments.update(changes)
    driver = scientific.SqlSdkScientificDriver(plan, case.plan, config, **arguments)
    return case, driver


def _request(driver, **changes):
    request = paired_bird.ArmRequest(
        driver.plan.plan_id, "ptc", driver.plan.draw.eligible,
        driver.instrument, driver.policy_identity, 1)
    return replace(request, **changes)


def _admit_for_unit(driver):
    # Direct private activation is confined to unit tests, not public admission.
    driver._active = True
    driver._approval = experiment.ScientificRequest(
        experiment.ScientificOperation("synthetic-unit", 1),
        driver.plan.plan_id, len(driver.plan.draw.eligible),
        driver.instrument, driver.policy_identity)


async def _collect(iterator):
    return tuple([row async for row in iterator])


def _synthetic_execution(case, monkeypatch, tmp_path, *, score=1.0, invalid=False,
                         program=True, rejected=False):
    original_score = OwnedSqlScorer.score_sql
    state = _execution_fixture(case, monkeypatch, tmp_path)
    monkeypatch.setattr(OwnedSqlScorer, "score_sql", original_score)
    state.owners, state.completions, state.results = [], [], []
    state.programs = []
    def client_init(client, config):
        client.base_url, client.api_key, client.headers = config.base_url, "synthetic", {}
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    def respond(request):
        body = json.loads(request.content)
        state.requests.append(body)
        tool_seen = any(message["role"] == "tool" for message in body["messages"])
        if program and not tool_seen:
            delta = {"tool_calls": [{
                "index": 0, "id": "fixture-program", "type": "function",
                "function": {"name": "run_program", "arguments": '{"code":"print(1)"}'}}]}
        else:
            delta = {"content": "SELECT 1"}
        chunk = {"id": "fixture-v38", "object": "chat.completion.chunk",
                 "created": 1, "model": "synthetic-policy",
                 "choices": [{"index": 0, "delta": delta, "finish_reason": "stop"}]}
        raw = "data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n"
        return httpx.Response(200, content=raw.encode(),
                              headers={"content-type": "text/event-stream"})

    async def execute(owner):
        # Deliberately synthetic outcome. Original owner issues/seals the ACK;
        # this bypasses native execution and MUST NOT establish qualification.
        if owner._completion is not None:
            return owner._completion
        state.owners.append(owner)
        receipt = core.RuntimeReceipt(
            owner.role, owner.request_digest, case.instrument.python_version,
            case.instrument.sqlite_version, "b" * 64, "c" * 64)
        if owner.role == "program":
            outcome = core.ProgramOutcome(
                "rejected: synthetic rejection" if rejected else "1", None,
                receipt, rejected=rejected)
            state.programs.append(outcome)
        else:
            association = live._ACTIVE_ASSOCIATION.get()
            state.associations.append(association)
            state.traces.append(association.trace)
            result = ExResult(
                0.0 if invalid else score,
                "gold_error" if invalid else "match" if score else "mismatch",
                not invalid)
            state.results.append(result)
            state.scores.append(owner)
            outcome = core.ScoreOutcome(result, None, receipt)
        completion = owner._seal(outcome, None, not_started=True)
        state.completions.append(completion)
        return completion

    monkeypatch.setattr(EvalClient, "__init__", client_init)
    monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)

    def forbidden_legacy(*args, **kwargs):
        raise AssertionError("second execution or rescore")

    monkeypatch.setattr(core.PilotExecutor, "run_program", forbidden_legacy)
    monkeypatch.setattr(core.PilotExecutor, "score_sql", forbidden_legacy)
    monkeypatch.setattr(sql_capture, "rescore_capture", forbidden_legacy)
    return state


@pytest.mark.parametrize("approval", [None, False, 1, "yes", "raises"])
def test_approval_dispatch_gate(tmp_path, monkeypatch, approval):
    _, driver = _driver(tmp_path)
    calls = []

    async def forbidden(request):
        calls.append(request)
        raise AssertionError("unapproved policy dispatch")
        yield

    def approve(request):
        if approval == "raises":
            raise RuntimeError("synthetic refusal")
        return approval

    monkeypatch.setattr(live, "run_sql_live", forbidden)
    with pytest.raises(experiment.ExperimentAdmissionError):
        asyncio.run(scientific.run_sql_sdk_scientific(
            driver, operation=experiment.ScientificOperation("unrun", 1),
            approve=None if approval is None else approve,
            bash_run_arm=forbidden, bash_evidence_for=lambda row: None,
            output_dir=tmp_path / "not-created"))
    assert calls == []
    assert not driver._active and driver._approval is None


def test_direct_dispatch_without_wrapper_approval(tmp_path, monkeypatch):
    _, driver = _driver(tmp_path)
    dispatches = []

    async def delegated(*args, **kwargs):
        dispatches.append(args)
        return live.SqlLiveResult((), ())

    monkeypatch.setattr(live, "run_sql_live", delegated)
    monkeypatch.setattr(driver, "_retain", lambda result: ())
    with pytest.raises(scientific.SqlScientificError, match="wrapper approval"):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert dispatches == []


@pytest.mark.parametrize("field,value", [
    ("arm", "bash"), ("plan_id", "wrong"), ("policy_identity", "wrong"),
    ("num_rollouts", True), ("num_rollouts", 2),
    ("tasks", ()), ("instrument", None),
])
def test_request_binding_rejects(tmp_path, monkeypatch, field, value):
    _, driver = _driver(tmp_path)
    _admit_for_unit(driver)
    dispatches = []

    async def forbidden(*args, **kwargs):
        dispatches.append(args)
        raise AssertionError("wrong request reached original delegate")

    monkeypatch.setattr(live, "run_sql_live", forbidden)
    with pytest.raises(scientific.SqlScientificError):
        asyncio.run(_collect(driver.run_arm(_request(driver, **{field: value}))))
    assert dispatches == []


@pytest.mark.parametrize("fault", ["order", "task_copy", "schema", "db", "policy", "config"])
def test_membership_and_binding_rejects(tmp_path, monkeypatch, fault):
    _, driver = _driver(tmp_path)
    _admit_for_unit(driver)
    calls = []
    if fault == "order":
        driver.live_plan = live.SqlLivePlan(tuple(reversed(driver.live_plan.inputs)))
    elif fault == "task_copy":
        row = driver.live_plan.inputs[0]
        driver.live_plan = live.SqlLivePlan(
            (replace(row, task=replace(row.task)),) + driver.live_plan.inputs[1:])
    elif fault in ("schema", "db"):
        row = driver.live_plan.inputs[0]
        driver.live_plan = live.SqlLivePlan(
            (replace(row, **{"schema" if fault == "schema" else "db_sha256":
                             "wrong" if fault == "schema" else "0" * 64}),)
            + driver.live_plan.inputs[1:])
    elif fault == "policy":
        driver.expected_policy.agent.model = "wrong"
    else:
        driver.config.shuffle = True

    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("mutated binding reached policy")

    monkeypatch.setattr(live, "run_sql_live", forbidden)
    with pytest.raises((scientific.SqlScientificError, live.SqlLiveError)):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert calls == []


def test_installed_sdk_contract():
    assert live.run_eval is run_eval
    assert loaders.harness_class("cotrain_bird_sql_harness") is PTCHarness
    assert loaders.environment_class("cotrain_bird_sql_live") is BirdSqlEnv
    assert loaders.taskset_class("cotrain_bird_sql_live") is BirdSqlTaskset


@pytest.mark.parametrize("score,rejected", [(1.0, False), (0.0, True)])
def test_original_delegate_and_identity(tmp_path, monkeypatch, score, rejected):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path, score=score, rejected=rejected)
    original_live, original_eval = live.run_sql_live, live.run_eval
    delegates, evaluator_calls = [], []

    async def delegate(plan, config, **kwargs):
        delegates.append((plan, config, kwargs))
        return await original_live(plan, config, **kwargs)

    async def evaluator(config):
        evaluator_calls.append(config)
        return await original_eval(config)

    monkeypatch.setattr(live, "run_sql_live", delegate)
    monkeypatch.setattr(live, "run_eval", evaluator)
    _admit_for_unit(driver)
    rows = asyncio.run(_collect(driver.run_arm(_request(driver))))
    count = len(driver.plan.draw.eligible)
    assert len(delegates) == len(evaluator_calls) == 1
    assert delegates[0][0] is driver.live_plan and delegates[0][1] is driver.config
    assert delegates[0][2]["instrument"] is driver.settings
    assert delegates[0][2]["expected_policy"] is driver.expected_policy
    assert len(rows) == len(state.results) == len(state.programs) == count
    assert len(state.owners) == len(state.completions) == 2 * count
    assert len(state.requests) == 2 * count
    for index, row in enumerate(rows):
        actual = driver.evidence_for(row)
        association = driver._live_result._associations[index]
        assert type(actual.episode) is Episode
        assert actual.episode is driver._live_result.episodes[index]
        assert actual.receipt is driver._live_result.receipts[index]
        assert type(actual.receipt) is SqlScoreReceipt
        assert actual.receipt.trace is actual.episode.traces[0] is association.original_trace
        assert actual.receipt.result is state.results[index] is actual.capture.result
        assert actual.capture.ids.episode_id == actual.episode.id
        assert actual.capture.steps == (sql_episodes.ActionObservation("print(1)", state.programs[index].observation),)
        retained, = association.retention.completed()
        assert retained[1] is state.programs[index]
        assert retained[1].rejected is rejected
        assert actual.capture.runtime_receipts[0] is retained[1].receipt
        assert row.metrics[0].score == score
        with pytest.raises(scientific.SqlScientificError):
            driver.evidence_for(replace(row))
    with pytest.raises(scientific.SqlScientificError, match="consumed"):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert len(delegates) == 1


def test_invalid_ex_never_zero(tmp_path, monkeypatch):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path, invalid=True)
    _admit_for_unit(driver)
    with pytest.raises(live.SqlLiveError):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert driver._live_result is None and driver._evidence == {}
    assert state.results and all(result.valid is False for result in state.results)
    assert all(association.receipt is association.result is association.capture is None
               for association in state.associations)
    assert all(trace.rewards.get("execution_accuracy") is None for trace in state.traces)


@pytest.mark.parametrize("fault", [
    "episode_copy", "order", "receipt_copy", "capture_ids", "capture_db",
    "capture_schema", "capture_result",
])
def test_completed_custody_rejects(tmp_path, monkeypatch, fault):
    case, driver = _driver(tmp_path)
    _synthetic_execution(case, monkeypatch, tmp_path)
    _admit_for_unit(driver)
    asyncio.run(_collect(driver.run_arm(_request(driver))))
    result = driver._live_result
    if fault == "episode_copy":
        candidate = replace(result, episodes=(result.episodes[0].model_copy(),) + result.episodes[1:])
    elif fault == "order":
        candidate = replace(result, episodes=tuple(reversed(result.episodes)))
    elif fault == "receipt_copy":
        candidate = replace(result, receipts=(replace(result.receipts[0]),) + result.receipts[1:])
    else:
        capture = result.captures[0]
        changes = {
            "capture_ids": {"ids": replace(capture.ids, episode_id="wrong")},
            "capture_db": {"db_sha256": "0" * 64},
            "capture_schema": {"schema": "wrong"},
            "capture_result": {"result": replace(capture.result)},
        }[fault]
        candidate = replace(result, captures=(replace(capture, **changes),) + result.captures[1:])
    with pytest.raises(scientific.SqlScientificError):
        driver._retain(candidate)


def test_original_scientific_wrapper_and_explicit_bash(tmp_path, monkeypatch):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    approvals, bash_calls, records = [], [], {}
    original = experiment.run_sql_experiment
    wrappers = []

    async def wrapper(*args, **kwargs):
        wrappers.append(kwargs)
        return await original(*args, **kwargs)

    def approve(request):
        assert bash_calls == state.requests == []
        approvals.append(request)
        return True

    async def bash(request):
        bash_calls.append(request)
        for task in request.tasks:
            data = TaskData(name=task.name, prompt="synthetic Bash public prompt")
            key = task_key(data.model_dump(mode="json", exclude_none=True))
            public = TraceTask(type="SyntheticBash", data=data, key=key, hash=key)
            trace = Trace(
                task=public, agent=AgentInfo(config=AgentConfig()),
                verifiers=VersionInfo(version="synthetic-offline"),
                ok=True, is_completed=True,
                rewards={"execution_accuracy": Reward(score=1.0)})
            episode = Episode(task=public, traces=[trace], ok=True)
            receipt = SqlScoreReceipt(trace, ExResult(1.0, "match", True))
            row = paired_bird.TaskOutcome(
                request.plan_id, "bash", task.name, True, True, "match",
                (paired_bird.Metric("execution_accuracy", 1.0),),
                f"synthetic-bash#episode={episode.id}")
            records[id(row)] = experiment.CompletedEvidence(episode, receipt)
            yield row

    monkeypatch.setattr(experiment, "run_sql_experiment", wrapper)
    result = asyncio.run(scientific.run_sql_sdk_scientific(
        driver, operation=experiment.ScientificOperation("synthetic-unrun-paid", 1),
        approve=approve, bash_run_arm=bash, bash_evidence_for=lambda row: records[id(row)],
        output_dir=tmp_path / "scientific-archive"))
    count = len(driver.plan.draw.eligible)
    assert len(wrappers) == len(approvals) == len(bash_calls) == 1
    assert approvals[0].instrument is bash_calls[0].instrument is driver.instrument
    assert approvals[0].num_rollouts == 1
    assert result.archive_complete and len(result.archives) == 2 * count
    assert result.scientifically_qualified is False
    assert result.scientific_limitations
    assert not driver._active and driver._approval is None
    with pytest.raises(scientific.SqlScientificError, match="consumed"):
        asyncio.run(scientific.run_sql_sdk_scientific(
            driver, operation=experiment.ScientificOperation("second-refused", 1),
            approve=approve, bash_run_arm=bash, bash_evidence_for=lambda row: records[id(row)],
            output_dir=tmp_path / "second-not-created"))
    assert len(wrappers) == 1


@pytest.mark.parametrize("missing", ["driver", "evidence"])
def test_no_default_bash_fallback(tmp_path, missing):
    _, driver = _driver(tmp_path)

    async def bash(request):
        raise AssertionError("Bash cannot dispatch")
        yield

    with pytest.raises(scientific.SqlScientificError, match="separately supplied Bash"):
        asyncio.run(scientific.run_sql_sdk_scientific(
            driver, operation=experiment.ScientificOperation("unrun", 1), approve=lambda req: True,
            bash_run_arm=None if missing == "driver" else bash,
            bash_evidence_for=None if missing == "evidence" else lambda row: None,
            output_dir=tmp_path / "not-created"))


@pytest.mark.parametrize("budget", [0, -1, True])
def test_positive_operation_budget_required(tmp_path, budget):
    _, driver = _driver(tmp_path)
    calls = []

    async def bash(request):
        calls.append(request)
        yield

    with pytest.raises(experiment.ExperimentAdmissionError):
        asyncio.run(scientific.run_sql_sdk_scientific(
            driver, operation=experiment.ScientificOperation("unrun", budget),
            approve=lambda req: calls.append(req) or True, bash_run_arm=bash,
            bash_evidence_for=lambda row: None, output_dir=tmp_path / "not-created"))
    assert calls == []


def test_generator_close_joins_completed_capture(tmp_path, monkeypatch):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    _admit_for_unit(driver)

    async def exercise():
        iterator = driver.run_arm(_request(driver))
        row = await anext(iterator)
        before = len(state.requests), len(state.owners)
        await iterator.aclose()
        assert before == (len(state.requests), len(state.owners))
        assert driver.evidence_for(row).capture.ids.episode_id
        assert all(association.retention.runner._closed and association.scorer._closed
                   for association in driver._live_result._associations)

    asyncio.run(exercise())


def test_capture_disabled_preserves_default(tmp_path, monkeypatch):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path)
    result = asyncio.run(live.run_sql_live(
        case.plan, case.config, executor=case.fixture.executor, instrument=case.instrument,
        expected_policy=case.policy, allow_execution=True, allow_model_requests=True))
    assert result.captures == result._associations == ()
    assert all(association.retention is None and association.capture is None
               for association in state.associations)


def test_capture_bound_fault_never_becomes_model_feedback(tmp_path, monkeypatch):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path)

    def bound_failure(retention, code, outcome):
        raise ValueError("synthetic evidence bound failure")

    monkeypatch.setattr(sql_owned_program._ProgramRetention, "_retain_size", bound_failure)
    _admit_for_unit(driver)
    with pytest.raises(live.SqlLiveError):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert 1 <= len(state.requests) <= len(driver.plan.draw.eligible)
    assert state.results == []
    assert all(not any(message["role"] == "tool" for message in body["messages"])
               for body in state.requests)
    assert all(owner._completion is not None for owner in state.owners)
    assert driver._evidence == {}


def test_capture_cancellation_joins_cleanup_preserves_primary(tmp_path, monkeypatch):
    case, driver = _driver(tmp_path)
    _synthetic_execution(case, monkeypatch, tmp_path)
    scope = live._Scope(
        case.plan, case.config, case.fixture.executor, case.instrument,
        case.policy, None, driver.capture)
    primary = asyncio.CancelledError("original-body-capture")
    real_close = OwnedSqlScorer.aclose

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def cancelled_score(scorer, predicted_sql):
            raise primary

        async def held_close(scorer):
            started.set()
            await release.wait()
            await real_close(scorer)

        monkeypatch.setattr(OwnedSqlScorer, "score_sql", cancelled_score)
        monkeypatch.setattr(OwnedSqlScorer, "aclose", held_close)

        async def invoke():
            token = live._ACTIVE_SCOPE.set(scope)
            try:
                env = loaders.load_environment(case.config.env)
                task = next(iter(env.taskset))
                agent = _EpisodeAgent(
                    case.policy.agent.model_copy(deep=True), interception=None,
                    name="agent", shared_tools={}, task_cls=type(task), gate=None,
                    completed=[], on_trace=None, on_discard=None, warned_resources=set())
                await env.run(task, type("Agents", (), {"agent": agent})())
            finally:
                scope.live = False
                live._ACTIVE_SCOPE.reset(token)

        caller = asyncio.create_task(invoke())
        try:
            await started.wait()
            for index in range(2):
                assert caller.cancel("secondary-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done()
            release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await caller
            assert caught.value is primary
            association, = scope.associations.values()
            assert association.scorer._closed
            assert association.retention.runner._closed
            assert len(association.retention.completed()) == 1
            assert association.capture is association.receipt is None
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)

    asyncio.run(asyncio.wait_for(exercise(), 5))


def _completion_close_boundary(tmp_path, monkeypatch, role, fault, cancel_count):
    case, driver = _driver(tmp_path)
    real_execute = core.OwnedSqlInvocation.execute
    real_close = core.OwnedSqlInvocation.aclose
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    row = case.plan.inputs[0]
    error_type = ProgramInfrastructureError if role == "program" else ScoreInfrastructureError
    primary = error_type("ordinary-primary")
    if role == "program":
        data = TaskData(name=row.task.name, prompt="completion boundary")
        harness = sql_owned_program.build_owned_sql_program_harness(
            case.config.env.agent.harness, data=data, task=row.task,
            executor=case.fixture.executor, db_sha256=row.db_sha256,
            max_rows=case.instrument.action_max_rows,
            existing_harness=PTCHarness(case.config.env.agent.harness))
        adapter = harness.program_runner_factory(
            data, Catalog(tools={**harness.catalog.tools, "print": print}))
        adapter.validate_program_timeout(5)
    else:
        adapter = OwnedSqlScorer(
            task=row.task, executor=case.fixture.executor,
            db_sha256=row.db_sha256, instrument=case.instrument)
        adapter.admit()
    factory_name = "owned_program" if role == "program" else "owned_score"
    real_factory = getattr(core.PilotExecutor, factory_name)
    original_shield = asyncio.shield
    owners, completions, closes, completed = [], [], [], []
    cancellations, accepted, forbidden, validation_errors = [], [], [], []

    def allocate(executor, *args, **kwargs):
        owner = real_factory(executor, *args, **kwargs)
        owners.append(owner)
        owner.request_cancel("runner_closed")
        return owner

    def deny(*args, **kwargs):
        forbidden.append(True)
        raise AssertionError("predispatch cancellation reached native dispatch")

    async def observed_shield(awaitable):
        try:
            return await original_shield(awaitable)
        except asyncio.CancelledError as exc:
            cancellations.append(exc)
            raise

    real_check_ack = adapter._check_ack

    def check_ack(job, ack):
        try:
            return real_check_ack(job, ack)
        except BaseException as exc:
            validation_errors.append(exc)
            raise

    async def execute(owner):
        completion = await real_execute(owner)
        if owner is not owners[0] or completions:
            return completion
        completions.append(completion)
        if fault == "ordinary":
            raise primary
        if fault == "missing":
            return None
        if fault == "invalid":
            malformed = replace(completion)
            object.__setattr__(malformed, "outcome", object())
            return malformed
        if fault == "foreign":
            if role == "program":
                foreign = real_factory(
                    case.fixture.executor, "print(1)", db_path=row.task.db_path,
                    db_sha256=row.db_sha256, max_rows=case.instrument.action_max_rows)
            else:
                foreign = real_factory(
                    case.fixture.executor, "SELECT 1", row.task,
                    db_sha256=row.db_sha256, instrument=case.instrument)
            foreign.request_cancel("runner_closed")
            foreign_completion = await real_execute(foreign)
            assert await real_close(foreign) is foreign_completion.cleanup_ack
            return foreign_completion
        return completion

    monkeypatch.setattr(core.PilotExecutor, factory_name, allocate)
    monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
    monkeypatch.setattr(adapter, "_check_ack", check_ack)
    monkeypatch.setattr(asyncio, "shield", observed_shield)
    for name in ("_stage_sources", "_stage_database", "_secure_directory",
                 "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated"):
        monkeypatch.setattr(core, name, deny)

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def held_close(owner):
            closes.append(owner)
            started.set()
            await release.wait()
            # The faulty return was already rejected. Keep cleanup independently
            # valid so actual cleanup cancellation, not another fault, competes.
            job, = adapter._jobs
            job.completion = owner._completion
            ack = await real_close(owner)
            completed.append(owner)
            return ack

        monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", held_close)

        async def invoke():
            result = (await adapter.run_program("print(1)", timeout=5)
                      if role == "program" else await adapter.score_sql("SELECT 1"))
            accepted.append(result)

        caller = asyncio.create_task(invoke())
        try:
            await started.wait()
            owner, = owners
            completion, = completions
            job, = adapter._jobs
            assert type(owner) is core.OwnedSqlInvocation
            assert completion is owner._completion
            assert completion.outcome is None and completion.abort.kind == "cancelled"
            assert completion.cleanup_ack.not_started is True
            if fault == "cancelled":
                assert job.completion is completion
            for index in range(cancel_count):
                assert caller.cancel("held-close-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done() and not job.close_task.done()
            release.set()
            with pytest.raises(BaseException) as caught:
                await caller
            assert len(cancellations) == cancel_count
            if fault == "cancelled" and cancel_count:
                assert caught.value is cancellations[0]
                assert caught.value.args == ("held-close-0",)
            elif fault == "ordinary":
                assert caught.value is primary
            elif fault == "invalid" and role == "scorer":
                assert type(caught.value) is ValueError
                assert "exactly one outcome/abort" in str(caught.value)
            else:
                assert type(caught.value) is error_type
                message = {"cancelled": "did not complete", "missing": "malformed completion",
                           "invalid": "execution failed", "foreign": "acknowledgment mismatch"}
                assert message[fault] in str(caught.value)
                if fault == "foreign":
                    assert caught.value is validation_errors[0]
            if role == "scorer" and fault != "cancelled":
                assert caught.value.__cause__ is cancellations[0]
            assert closes == completed == [owner]
            assert job.close_task.done() and job.close_task.result() is completion.cleanup_ack
            assert job.ack is completion.cleanup_ack
            assert len(owners) == len(completions) == 1
            assert accepted == forbidden == state.results == []
            assert driver._evidence == {} and driver._live_result is None
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
            await adapter.aclose()

    asyncio.run(asyncio.wait_for(exercise(), 5))


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("cancel_count", [0, 3])
def test_validated_cancelled_completion_close_boundary(
        tmp_path, monkeypatch, role, cancel_count):
    _completion_close_boundary(tmp_path, monkeypatch, role, "cancelled", cancel_count)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["missing", "invalid", "foreign", "ordinary"])
def test_primary_failure_not_masked_by_close_cancel(tmp_path, monkeypatch, role, fault):
    _completion_close_boundary(tmp_path, monkeypatch, role, fault, 3)


@pytest.mark.parametrize("field", ["allow_execution", "allow_model_requests"])
@pytest.mark.parametrize("value", [False, 0, 1, "yes"])
def test_no_implicit_execution_opt_in(tmp_path, field, value):
    with pytest.raises(scientific.SqlScientificError, match="opt-ins"):
        _driver(tmp_path, **{field: value})


@pytest.mark.parametrize("fault", ["order", "task_copy", "db"])
def test_initial_membership_rejected(tmp_path, fault):
    _, original = _driver(tmp_path)
    inputs = original.live_plan.inputs
    if fault == "order":
        inputs = tuple(reversed(inputs))
    elif fault == "task_copy":
        inputs = (replace(inputs[0], task=replace(inputs[0].task)),) + inputs[1:]
    else:
        inputs = (replace(inputs[0], db_sha256="0" * 64),) + inputs[1:]
    with pytest.raises(scientific.SqlScientificError):
        scientific.SqlSdkScientificDriver(
            original.plan, live.SqlLivePlan(inputs), original.config,
            executor=original.executor, instrument=original.instrument,
            settings=original.settings, expected_policy=original.expected_policy,
            policy_identity=original.policy_identity, capture=original.capture,
            allow_execution=True, allow_model_requests=True)


def test_actual_schema_rejected_before_policy(tmp_path, monkeypatch):
    _, original = _driver(tmp_path)
    inputs = original.live_plan.inputs
    plan = live.SqlLivePlan((replace(inputs[0], schema="wrong schema"),) + inputs[1:])
    driver = scientific.SqlSdkScientificDriver(
        original.plan, plan, original.config, executor=original.executor,
        instrument=original.instrument, settings=original.settings,
        expected_policy=original.expected_policy, policy_identity=original.policy_identity,
        capture=original.capture, allow_execution=True, allow_model_requests=True)
    _admit_for_unit(driver)
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("wrong schema reached policy")

    monkeypatch.setattr(live, "run_sql_live", forbidden)
    with pytest.raises(scientific.SqlScientificError, match="schema"):
        asyncio.run(_collect(driver.run_arm(_request(driver))))
    assert calls == []


def test_retention_is_one_runner_and_bounded(tmp_path):
    case = _case(tmp_path)
    row, = case.plan.inputs
    retention = sql_owned_program._ProgramRetention(case.config.env.agent.harness.max_turns)
    data = TaskData(name=row.task.name, prompt="public")
    harness = sql_owned_program.build_owned_sql_program_harness(
        case.config.env.agent.harness, data=data,
        task=row.task, executor=case.fixture.executor, db_sha256=row.db_sha256,
        max_rows=case.instrument.action_max_rows, retention=retention)
    assert retention.runner is None
    compiled = Catalog(tools={**harness.catalog.tools, "print": print})
    runner = harness.program_runner_factory(data, compiled)
    assert retention.runner is runner
    with pytest.raises(ProgramInfrastructureError):
        harness.program_runner_factory(data, compiled)
    with pytest.raises(ProgramInfrastructureError, match="did not close"):
        retention.completed()
    asyncio.run(runner.aclose())
    assert retention.completed() == ()
    receipt = core.RuntimeReceipt("program", "a" * 64, "fixture", "fixture",
                                  "b" * 64, "c" * 64)
    outcome = core.ProgramOutcome("x", None, receipt)
    retention._retain_size("a" * (8 * 1024 * 1024 - 1), outcome)
    assert retention._bytes == 8 * 1024 * 1024
    with pytest.raises(ProgramInfrastructureError, match="8 MiB"):
        retention._retain_size("", outcome)


@pytest.mark.parametrize("fault", ["model", "client", "policy"])
def test_no_default_policy_or_provider(tmp_path, fault):
    _, original = _driver(tmp_path)
    policy = original.expected_policy
    if fault == "model":
        original.config.model = ""
    elif fault == "client":
        original.config.model_fields_set.discard("client")
    else:
        policy = None
    with pytest.raises((scientific.SqlScientificError, live.SqlLiveError)):
        scientific.SqlSdkScientificDriver(
            original.plan, original.live_plan, original.config, executor=original.executor,
            instrument=original.instrument, settings=original.settings,
            expected_policy=policy, policy_identity=original.policy_identity,
            capture=original.capture, allow_execution=True, allow_model_requests=True)


@pytest.mark.parametrize("location", ["run", "agent"])
@pytest.mark.parametrize("payload", [
    {}, {"type": "eval"},
    {"base_url": "http://synthetic.invalid/v1"},
    {"api_key_var": "UNUSED_SYNTHETIC_V39"},
    {"base_url": "", "api_key_var": "UNUSED_SYNTHETIC_V39"},
    {"base_url": "http://synthetic.invalid/v1", "api_key_var": ""},
    {"base_url": "http://synthetic.invalid/v1", "api_key_var": "PRIME_API_KEY"},
])
def test_effective_provider_requires_independent_intent(
        tmp_path, monkeypatch, location, payload):
    _, original = _driver(tmp_path)
    client = type(original.config.client).model_validate(payload)
    if location == "run":
        original.config.client = client
    else:
        original.config.env.agent.client = client
    expected = original.expected_policy.agent.model_copy(deep=True, update={
        "client": client.model_copy(deep=True)})
    policy = live.SqlLivePolicy(expected, ModelContext(
        expected.model, client.model_copy(deep=True), expected.sampling.model_copy(deep=True)))
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("default client reached policy")

    monkeypatch.setattr(live, "run_sql_live", forbidden)
    with pytest.raises(scientific.SqlScientificError, match="effective endpoint"):
        scientific.SqlSdkScientificDriver(
            original.plan, original.live_plan, original.config, executor=original.executor,
            instrument=original.instrument, settings=original.settings, expected_policy=policy,
            policy_identity=original.policy_identity, capture=original.capture,
            allow_execution=True, allow_model_requests=True)
    assert calls == []


@pytest.mark.parametrize("override", [False, True])
def test_explicit_effective_client_retains_independent_identity(tmp_path, override):
    _, original = _driver(tmp_path)
    client = original.config.client
    if override:
        client = client.model_copy(deep=True, update={
            "base_url": "http://agent-fixture.invalid/v1",
            "api_key_var": "UNUSED_AGENT_SYNTHETIC_V39"})
        original.config.env.agent.client = client
        original.config.client = type(client).model_validate({})
    expected = original.expected_policy.agent.model_copy(deep=True, update={
        "client": client.model_copy(deep=True)})
    context = ModelContext(
        expected.model, client.model_copy(deep=True), expected.sampling.model_copy(deep=True))
    policy = live.SqlLivePolicy(expected, context)
    driver = scientific.SqlSdkScientificDriver(
        original.plan, original.live_plan, original.config, executor=original.executor,
        instrument=original.instrument, settings=original.settings, expected_policy=policy,
        policy_identity=original.policy_identity, capture=original.capture,
        allow_execution=True, allow_model_requests=True)
    driver._check()
    assert driver._client is client
    assert driver.expected_policy is policy and policy.agent is expected
    assert policy.context is context and context.client is not client
    replacement = client.model_copy(deep=True)
    if override:
        original.config.env.agent.client = replacement
    else:
        original.config.client = replacement
    with pytest.raises(scientific.SqlScientificError, match="effective endpoint"):
        driver._check()


@pytest.mark.parametrize("capture_enabled", [False, True])
def test_live_source_drift_during_policy_await(tmp_path, monkeypatch, capture_enabled):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    selected = sql_capture._owned_sources()

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        original_stream = ptc_harness._stream_message
        policy_calls = []

        async def held_stream(*args, **kwargs):
            policy_calls.append(1)
            response = await original_stream(*args, **kwargs)
            if len(policy_calls) == 1:
                started.set()
                await release.wait()
            return response

        monkeypatch.setattr(ptc_harness, "_stream_message", held_stream)
        caller = asyncio.create_task(live.run_sql_live(
            case.plan, case.config, executor=case.fixture.executor,
            instrument=case.instrument, expected_policy=case.policy,
            capture=driver.capture if capture_enabled else None,
            allow_execution=True, allow_model_requests=True))
        try:
            await started.wait()
            before = len(state.requests), len(state.owners), len(state.results)
            monkeypatch.setattr(sql_capture, "_owned_sources",
                                lambda: (selected[0], "0" * 64))
            release.set()
            if capture_enabled:
                with pytest.raises(live.SqlLiveError):
                    await caller
                assert (len(state.requests), len(state.owners), len(state.results)) == before
                assert before == (1, 0, 0)
                assert all(not association.capture for association in state.associations)
            else:
                result = await caller
                assert len(result.episodes) == len(case.plan.inputs)
                assert result.captures == result._associations == ()
            assert driver._evidence == {}
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)

    asyncio.run(asyncio.wait_for(exercise(), 5))


@pytest.mark.parametrize("boundary", [
    "program", "scorer", "program_close", "scorer_close", "finalize", "finish",
])
def test_live_source_drift_rejected_at_host_boundaries(tmp_path, monkeypatch, boundary):
    case, driver = _driver(tmp_path)
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    selected = sql_capture._owned_sources()
    drifted = []

    def drift():
        if not drifted:
            drifted.append((len(state.requests), len(state.owners), len(state.results)))
            monkeypatch.setattr(sql_capture, "_owned_sources",
                                lambda: (selected[0], "0" * 64))

    if boundary in ("program", "scorer"):
        original = core.OwnedSqlInvocation.execute

        async def execute(owner):
            result = await original(owner)
            if owner.role == boundary:
                drift()
            return result

        monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
    elif boundary in ("program_close", "scorer_close"):
        owner_class = sql_owned_program._Runner if boundary == "program_close" else OwnedSqlScorer
        original = owner_class.aclose

        async def close(owner):
            await original(owner)
            drift()

        monkeypatch.setattr(owner_class, "aclose", close)
    elif boundary == "finalize":
        original = BirdSqlEnv.finalize

        async def finalize(env, task, episode):
            drift()
            await original(env, task, episode)

        monkeypatch.setattr(BirdSqlEnv, "finalize", finalize)
    else:
        original = live._Scope.finish

        def finish(scope, episodes):
            drift()
            return original(scope, episodes)

        monkeypatch.setattr(live._Scope, "finish", finish)

    _admit_for_unit(driver)
    with pytest.raises(live.SqlLiveError):
        asyncio.run(asyncio.wait_for(_collect(driver.run_arm(_request(driver))), 5))
    assert len(drifted) == 1
    assert (len(state.requests), len(state.owners), len(state.results)) == drifted[0]
    assert driver._live_result is None and driver._evidence == {}
    assert all(owner._completion is not None for owner in state.owners)


@pytest.mark.parametrize("body_kind", ["cancelled", "ordinary", "none"])
def test_original_harness_launch_primary_survives_cleanup_fault(
        tmp_path, monkeypatch, body_kind):
    case, driver = _driver(tmp_path)
    _synthetic_execution(case, monkeypatch, tmp_path)
    primary = (asyncio.CancelledError("harness-body") if body_kind == "cancelled"
               else RuntimeError("harness-body") if body_kind == "ordinary" else None)
    cleanup_error = RuntimeError("harness-cleanup")
    real_close = sql_owned_program._Runner.aclose
    row = case.plan.inputs[0]
    retention = sql_owned_program._ProgramRetention(case.instrument.action_cap)
    data = TaskData(name=row.task.name, prompt="synthetic harness cancellation")
    harness = sql_owned_program.build_owned_sql_program_harness(
        case.config.env.agent.harness, data=data, task=row.task,
        executor=case.fixture.executor, db_sha256=row.db_sha256,
        max_rows=case.instrument.action_max_rows, retention=retention,
        existing_harness=PTCHarness(case.config.env.agent.harness))
    requests, closes, completed, accepted = [], [], [], []

    async def respond(request):
        requests.append(request)
        if primary is not None:
            raise primary
        chunk = {"choices": [{"delta": {"content": "SELECT 1"}}]}
        return httpx.Response(
            200, content=("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())

    harness.transport = httpx.MockTransport(respond)

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def held_close(runner):
            closes.append(runner)
            started.set()
            await release.wait()
            await real_close(runner)
            completed.append(runner)
            raise cleanup_error

        monkeypatch.setattr(sql_owned_program._Runner, "aclose", held_close)

        async def invoke():
            accepted.append(await harness.launch(
                case.policy.context, trace=None, runtime=None,
                endpoint="http://harness-fixture.invalid/v1", secret="synthetic",
                mcp_urls={}, data=data))

        caller = asyncio.create_task(invoke())
        try:
            await started.wait()
            for index in range(2):
                assert caller.cancel("secondary-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done()
            release.set()
            with pytest.raises(BaseException) as caught:
                await caller
            failure = caught.value if primary is None else caught.value.__cause__
            if primary is not None:
                assert caught.value is primary
            assert type(failure) is ProgramInfrastructureError
            assert failure.__cause__ is cleanup_error
            assert len(failure.__notes__) == 2
            assert all("secondary-" + str(index) in failure.__notes__[index]
                       for index in range(2))
            assert closes == completed == [retention.runner]
            assert retention.runner._closed and retention.completed() == ()
            assert len(requests) == 1 and accepted == []
            assert driver._evidence == {} and driver._live_result is None
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)

    asyncio.run(asyncio.wait_for(exercise(), 5))


@pytest.mark.parametrize("body_kind", ["cancelled", "ordinary", "none"])
def test_original_scorer_primary_survives_cleanup_fault(tmp_path, monkeypatch, body_kind):
    case, driver = _driver(tmp_path)
    real_execute, real_close = core.OwnedSqlInvocation.execute, core.OwnedSqlInvocation.aclose
    state = _synthetic_execution(case, monkeypatch, tmp_path)
    primary = (asyncio.CancelledError("scorer-body") if body_kind == "cancelled"
               else RuntimeError("scorer-body") if body_kind == "ordinary" else None)
    cleanup_error = RuntimeError("scorer-cleanup")
    row = case.plan.inputs[0]
    scorer = OwnedSqlScorer(
        task=row.task, executor=case.fixture.executor,
        db_sha256=row.db_sha256, instrument=case.instrument)
    scorer.admit()
    owners, closes, completed, accepted = [], [], [], []

    async def execute(owner):
        owners.append(owner)
        if primary is not None:
            raise primary
        # This success case only needs a real sealed synthetic outcome, not a live association.
        outcome = core.ScoreOutcome(ExResult(1.0, "match", True), None, core.RuntimeReceipt(
            "scorer", owner.request_digest, case.instrument.python_version,
            case.instrument.sqlite_version, "b" * 64, "c" * 64))
        return owner._seal(outcome, None, not_started=True)

    monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def held_close(owner):
            closes.append(owner)
            started.set()
            await release.wait()
            monkeypatch.setattr(owner, "execute", real_execute.__get__(owner))
            await real_close(owner)
            completed.append(owner)
            raise cleanup_error

        monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", held_close)

        async def invoke():
            accepted.append(await scorer.score_sql("SELECT 1"))

        caller = asyncio.create_task(invoke())
        try:
            await started.wait()
            for index in range(2):
                assert caller.cancel("secondary-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done()
            release.set()
            with pytest.raises(BaseException) as caught:
                await caller
            failure = caught.value if primary is None else caught.value.__cause__
            if primary is not None:
                assert caught.value is primary
            assert type(failure) is ScoreInfrastructureError
            assert failure.__cause__ is cleanup_error
            assert len(failure.__notes__) == 2
            assert all("secondary-" + str(index) in failure.__notes__[index]
                       for index in range(2))
            owner, = owners
            assert owner.role == "scorer" and closes == completed == [owner]
            assert owner._completion.cleanup_ack.not_started is True
            job, = scorer._jobs
            assert job.invocation is owner and job.close_task.done()
            assert job.ack is None and job._close_failed
            assert accepted == [] and driver._evidence == {} and state.results == []
            with pytest.raises(ScoreInfrastructureError):
                await scorer.aclose()
            assert closes == completed == [owner]
        finally:
            release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)

    asyncio.run(asyncio.wait_for(exercise(), 5))
