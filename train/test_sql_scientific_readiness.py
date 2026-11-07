"""UNRUN memory contracts. Synthetic declarations are not policy/science evidence."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.cli.eval import EvalConfig

from bench import paired_bird
from bench.prepare import DrawDatabase, ValidatedDraw
from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_arms, sql_isolation as core
from train import sql_episodes as episodes, sql_experiment_runner as experiment
from train import sql_live_reuse as live, sql_sdk_scientific as scientific
from train import sql_scientific_readiness as readiness, sql_skill_pilot, sql_skills as skills
from train.sql_skill_eval import SkillCase


def _ids(split, episode):
    return episodes.EpisodeIds("memory", split, "memory-run", episode, "memory-policy", "revision")


def _task(index):
    return SqlTask(
        "memory-task-" + str(index), "PUBLIC_SYNTHETIC_QUESTION", "PRIVATE_SYNTHETIC_HINT",
        "PRIVATE_SYNTHETIC_GOLD", "memory-db-" + str(index),
        "/never-open-memory-" + str(index) + ".sqlite", "simple", "annotated",
        "memory-shape", "memory-coarse", "fixture")


def _base():
    config = EvalConfig.model_validate({
        "model": "memory-policy",
        "client": {"type": "eval", "base_url": "http://memory.invalid/v1",
                   "api_key_var": "NEVER_READ_MEMORY_KEY"},
        "env": {"id": "cotrain_bird_sql_live",
                "taskset": {"id": "cotrain_bird_sql_live"},
                "agent": {"harness": {"id": "cotrain_bird_sql_harness",
                                      "max_turns": 2, "program_timeout": 5},
                          "timeout": {"rollout": 600},
                          "runtime": {"type": "subprocess"},
                          "retries": {"max_retries": 0}},
                "retries": {"max_retries": 0}},
        "num_tasks": None, "num_rollouts": 1, "max_concurrent": 1, "push": False,
        "resume": False, "clean": False, "rich": None,
        "output_dir": "/never-create-memory-output", "run": {"dir": "run"},
    })
    agent = config.env.agent.model_copy(deep=True, update={
        "model": config.model, "client": config.client.model_copy(deep=True),
        "sampling": config.sampling.model_copy(deep=True)})
    policy = live.SqlLivePolicy(agent, ModelContext(
        config.model, config.client.model_copy(deep=True),
        config.sampling.model_copy(deep=True)))
    settings = episodes.InstrumentSettings(
        2, 7, 7, "set", 30.0, 5.0, 30.0, "memory-python", "memory-sqlite",
        ("synthetic/source.py",), "a" * 64)
    return config, policy, settings


def _binding():
    # Real record constructors, synthetic pins; no source/image/runtime inspection.
    pins = (core.SourcePin("synthetic/source.py", "a" * 64),)
    def role(name):
        return core.RoleBinding(
            name, core.IMAGE_MANIFEST_SHA256, core.IMAGE_CONFIG_SHA256,
            "linux/arm64", pins, "b" * 64, core.limits_for(name))
    return core.ExecutionBinding(
        program=role("program"), scorer=role("scorer"),
        controller_sources=pins, policy_sha256="c" * 64)


def _reuse():
    config, policy, settings = _base()
    source = skills.SourceRef(
        "b" * 64, _ids("source", "source"), "source-task", "c" * 64, "d" * 64,
        settings)
    candidate = skills.SkillCandidate(
        1, "memory-skill", "print('synthetic')",
        skills.SkillScope("fixture", "memory-shape", "memory-coarse"), source)
    qualifications = tuple(skills.QualificationRef(
        "qualification", _ids("qualification", "qualification-" + str(i)),
        "qualification-task-" + str(i), str(i + 1) * 64, str(i + 5) * 64,
        "e" * 64, ExResult(1.0, "match", True)) for i in range(4))
    promotion = skills.SkillPromotion(
        2, skills._sha(skills.encode_candidate(candidate)), candidate.scope, source,
        _ids("approval", "approval"),
        skills.SkillBinding(settings, skills.SOURCE_PATHS, "f" * 64, _binding()),
        qualifications)
    approved = sql_skill_pilot.ApprovedSkill(
        candidate, promotion, skills._sha(skills.encode_promotion(promotion)),
        Path("/never-read-memory-approval.json"), "a" * 64)
    task = _task(10)
    case = SkillCase("reuse", task, _ids("heldout", "planned-not-sdk-episode"),
                     expected_db_sha256="9" * 64)
    return readiness.SqlScientificPlan(
        "promoted_skill_reuse", live.SqlLivePlan((
            live.SqlLiveInput(task, "PUBLIC_SYNTHETIC_SCHEMA", "9" * 64, case),)),
        config, settings, policy, "memory-policy", approved_skill=approved)


def _paired(monkeypatch):
    config, policy, settings = _base()
    tasks = (_task(0), _task(1))
    databases = tuple(DrawDatabase(task.db_id, str(i + 1) * 64, 1)
                      for i, task in enumerate(tasks))
    draw = ValidatedDraw(tasks, tasks, (), "a" * 64, "b" * 64,
                         True, 30.0, 7, "set", databases)
    plan = paired_bird.PairedBirdPlan("memory-pair", draw)
    # Deliberate unit-only authority injection, never retained-draw admission.
    monkeypatch.setitem(paired_bird._admissions, plan, (False, ()))
    instrument = paired_bird.Instrument(
        "memory-instrument", sql_arms.Budget(
            max_turns=2, max_retries=0, retry_on=(), rollout_timeout=600,
            program_timeout=5), 7, 30.0, "memory-sampling")
    inputs = tuple(live.SqlLiveInput(task, "PUBLIC_SYNTHETIC_SCHEMA", database.sha256)
                   for task, database in zip(tasks, databases))
    return readiness.SqlScientificPlan(
        "paired_bird", live.SqlLivePlan(inputs), config, settings, policy,
        "memory-policy", live.SqlLiveCapture(
            "memory", "heldout", "memory-run", "memory-policy", "revision"),
        paired_plan=plan, instrument=instrument)


def _reuse_call(plan, approve, factory, **kwargs):
    return asyncio.run(live.run_sql_live_plan(
        plan, operation=experiment.ScientificOperation("memory-operation", 1),
        approve=approve, executor_factory=factory,
        allow_execution=True, allow_model_requests=True, **kwargs))


def _paired_call(plan, approve, factory):
    async def forbidden(request):
        raise AssertionError("unexpected arm dispatch")
        yield
    return asyncio.run(scientific.run_sql_sdk_scientific(
        plan, operation=experiment.ScientificOperation("memory-operation", 1),
        approve=approve, executor_factory=factory, bash_run_arm=forbidden,
        bash_evidence_for=lambda row: None, output_dir=Path("/never-create-memory-pair"),
        allow_execution=True, allow_model_requests=True))


def _delegates(monkeypatch):
    calls, approvals, allocations = [], [], []
    result = live.SqlLiveResult((), ())
    executor = object.__new__(core.PilotExecutor)  # allocation marker, never initialized/run
    monkeypatch.setattr(sql_skill_pilot, "validate_approval", approvals.append)
    # These original routing tests use synthetic pins, not current source proof.
    monkeypatch.setattr(skills, "_require_current_workflow_sources", lambda binding, root: None)
    async def original_delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return result
    monkeypatch.setattr(live, "run_sql_live", original_delegate)
    def factory(request):
        allocations.append(request)
        return executor
    return calls, approvals, allocations, result, executor, factory


def test_reuse_missing_science_approval_allocates_zero(monkeypatch):
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    with pytest.raises(live.SqlLiveError, match="scientific approval"):
        _reuse_call(_reuse(), None, factory)
    assert calls == approvals == allocations == []


@pytest.mark.parametrize("accepted", [False, 1, None])
def test_reuse_nonliteral_science_approval_allocates_zero(monkeypatch, accepted):
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    with pytest.raises(readiness.ScienceReadinessError):
        _reuse_call(_reuse(), lambda request: accepted, factory)
    assert calls == approvals == allocations == []


def test_native_engineering_receipt_is_not_science_approval(monkeypatch):
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    engineering_declaration = {"native_engineering_passed": True, "science_authorized": False}
    with pytest.raises(readiness.ScienceReadinessError):
        _reuse_call(_reuse(), lambda request: engineering_declaration, factory)
    assert calls == approvals == allocations == []


def test_reuse_propagates_original_request_and_evidence_objects(monkeypatch):
    plan = _reuse()
    calls, approvals, allocations, result, executor, factory = _delegates(monkeypatch)
    requests = []
    def approve(request):
        requests.append(request)
        assert type(request) is readiness.SqlReuseRequest
        assert request.execution_plan is plan and request.eligible_count == 1
        assert request.policy_identity == "memory-policy" and request.num_rollouts == 1
        return True
    assert _reuse_call(plan, approve, factory) is result
    assert requests == allocations and len(requests) == 1
    assert approvals == [plan.approved_skill] and len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] is plan.live_plan and args[1] is plan.config
    assert kwargs["executor"] is executor and kwargs["instrument"] is plan.settings
    assert kwargs["approved_skill"] is plan.approved_skill
    assert kwargs["expected_policy"] is plan.expected_policy and kwargs["capture"] is None
    assert result.episodes == result.receipts == result.captures == ()


def test_reuse_approval_config_mutation_refuses_before_allocation(monkeypatch):
    plan = _reuse()
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    def approve(request):
        plan.config.model = "substituted-policy"
        return True
    with pytest.raises(readiness.ScienceReadinessError, match="inputs changed"):
        _reuse_call(plan, approve, factory)
    assert calls == approvals == allocations == []


def test_reuse_request_mutation_refuses_before_allocation(monkeypatch):
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    def approve(request):
        object.__setattr__(request, "eligible_count", 0)
        return True
    with pytest.raises(live.SqlLiveError, match="operation changed"):
        _reuse_call(_reuse(), approve, factory)
    assert calls == approvals == allocations == []


def test_reuse_plan_is_one_use_even_after_denial(monkeypatch):
    plan = _reuse()
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    with pytest.raises(readiness.ScienceReadinessError):
        _reuse_call(plan, lambda request: False, factory)
    with pytest.raises(readiness.ScienceReadinessError, match="already consumed"):
        _reuse_call(plan, lambda request: True, factory)
    assert calls == approvals == allocations == []


@pytest.mark.parametrize("execution,model", [(False, False), (True, False), (False, True)])
def test_reuse_requires_both_explicit_optins(monkeypatch, execution, model):
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    with pytest.raises(live.SqlLiveError, match="opt-ins"):
        asyncio.run(live.run_sql_live_plan(
            _reuse(), operation=experiment.ScientificOperation("memory-operation", 1),
            approve=lambda request: True, executor_factory=factory,
            allow_execution=execution, allow_model_requests=model))
    assert calls == approvals == allocations == []


@pytest.mark.parametrize("execution,model", [(False, False), (True, False), (False, True)])
def test_deferred_paired_requires_both_explicit_optins(monkeypatch, execution, model):
    allocations = []
    async def forbidden(request):
        raise AssertionError("unexpected arm dispatch")
        yield
    with pytest.raises(scientific.SqlScientificError, match="opt-ins"):
        asyncio.run(scientific.run_sql_sdk_scientific(
            _paired(monkeypatch),
            operation=experiment.ScientificOperation("memory-operation", 1),
            approve=lambda request: True, executor_factory=allocations.append,
            bash_run_arm=forbidden, bash_evidence_for=lambda row: None,
            output_dir=Path("/never-create-memory-output"),
            allow_execution=execution, allow_model_requests=model))
    assert allocations == []


@pytest.mark.parametrize("field", ["base_url", "api_key_var"])
def test_explicit_effective_endpoint_and_key_source_required(field):
    plan = _reuse()
    config = plan.config.model_copy(deep=True)
    client = config.client
    setattr(client, field, "")
    with pytest.raises(readiness.ScienceReadinessError, match="endpoint"):
        replace(plan, config=config)


def test_no_prime_provider_fallback():
    plan = _reuse()
    config = plan.config.model_copy(deep=True)
    config.client.api_key_var = "PRIME_API_KEY"
    with pytest.raises(readiness.ScienceReadinessError, match="non-Prime"):
        replace(plan, config=config)


def test_reuse_candidate_source_substitution_rejected():
    plan = _reuse()
    candidate = replace(plan.approved_skill.candidate,
                        source=replace(plan.approved_skill.candidate.source, task_id="substitute"))
    approved = replace(plan.approved_skill, candidate=candidate)
    with pytest.raises(readiness.ScienceReadinessError, match="promotion binding"):
        replace(plan, approved_skill=approved)


def test_reuse_policy_revision_substitution_rejected():
    plan = _reuse()
    row, = plan.live_plan.inputs
    row = replace(row, reuse_case=replace(
        row.reuse_case, ids=replace(row.reuse_case.ids, policy_revision="other-revision")))
    with pytest.raises(readiness.ScienceReadinessError, match="policy identity"):
        replace(plan, live_plan=live.SqlLivePlan((row,)))


def test_reuse_policy_identity_matches_promoted_source():
    with pytest.raises(readiness.ScienceReadinessError, match="promotion binding"):
        replace(_reuse(), policy_identity="substituted-policy")


def test_reuse_promotion_instrument_substitution_rejected():
    plan = _reuse()
    with pytest.raises(readiness.ScienceReadinessError, match="promotion binding"):
        replace(plan, settings=replace(plan.settings, scorer_max_rows=8))


@pytest.mark.parametrize("kind", ["source-db", "qualification-db", "fingerprint", "split"])
def test_reuse_source_qualification_leakage_rejected(kind):
    plan = _reuse()
    row, = plan.live_plan.inputs
    promotion = plan.approved_skill.promotion
    if kind in ("source-db", "qualification-db"):
        digest = (promotion.source.db_sha256 if kind == "source-db"
                  else promotion.qualifications[0].db_sha256)
        row = replace(row, db_sha256=digest,
                      reuse_case=replace(row.reuse_case, expected_db_sha256=digest))
    elif kind == "split":
        row = replace(row, reuse_case=replace(
            row.reuse_case, ids=replace(row.reuse_case.ids, split_id="qualification")))
    else:
        source = replace(promotion.source, task_fingerprint=episodes._fingerprint(
            episodes._task_payload(row.task)))
        candidate = replace(plan.approved_skill.candidate, source=source)
        promotion = replace(promotion, source=source,
                            candidate_sha256=skills._sha(skills.encode_candidate(candidate)))
        approved = replace(plan.approved_skill, candidate=candidate, promotion=promotion,
                           promotion_sha256=skills._sha(skills.encode_promotion(promotion)))
        plan = replace(plan, approved_skill=approved, stage="cross_harness_cotraining")
    with pytest.raises(readiness.ScienceReadinessError, match="leakage"):
        replace(plan, stage="promoted_skill_reuse", live_plan=live.SqlLivePlan((row,)))


def test_reuse_capture_on_refuses_missing_instrument_bridge():
    plan = _reuse()
    with pytest.raises(readiness.ScienceReadinessError, match="instrument bridge"):
        replace(plan, capture=live.SqlLiveCapture(
            "memory", "heldout", "memory-run", "memory-policy", "revision"))


def test_paired_membership_order_and_original_identity(monkeypatch):
    plan = _paired(monkeypatch)
    for inputs in (tuple(reversed(plan.live_plan.inputs)),
                   (replace(plan.live_plan.inputs[0],
                            task=replace(plan.live_plan.inputs[0].task)),
                    plan.live_plan.inputs[1])):
        with pytest.raises(readiness.ScienceReadinessError, match="ordered original"):
            replace(plan, live_plan=live.SqlLivePlan(inputs))


def test_paired_policy_capture_identity_rejected(monkeypatch):
    plan = _paired(monkeypatch)
    with pytest.raises(readiness.ScienceReadinessError, match="capture policy"):
        replace(plan, policy_identity="substituted-policy")


def test_paired_missing_approval_zero_factory_and_zero_archive(monkeypatch):
    plan = _paired(monkeypatch)
    allocations = []
    monkeypatch.setattr(experiment.assets, "safe_path", lambda path: path)
    with pytest.raises(experiment.ExperimentAdmissionError):
        _paired_call(plan, None, allocations.append)
    assert allocations == []


def test_paired_original_scientific_request_precedes_executor_factory(monkeypatch):
    plan = _paired(monkeypatch)
    from train import sql_capture

    # Routing fixture only, no claim that its synthetic instrument pins bytes.
    monkeypatch.setattr(sql_capture, "_owned_sources", lambda: (
        plan.settings.source_paths, plan.settings.source_sha256,
    ))
    requests, allocations, constructions = [], [], []
    result = object()
    executor = object.__new__(core.PilotExecutor)
    def factory(request):
        allocations.append(request)
        assert requests == [request]
        return executor
    def initialize(driver, paired, live_plan, config, **kwargs):
        constructions.append((driver, paired, live_plan, config, kwargs))
        driver._active = False
        driver._approval = None
    monkeypatch.setattr(scientific.SqlSdkScientificDriver, "__init__", initialize)
    monkeypatch.setattr(scientific.SqlSdkScientificDriver, "_check_approval", lambda driver: None)
    async def original_runner(paired, **kwargs):
        assert paired is plan.paired_plan
        request = experiment.ScientificRequest(
            kwargs["operation"], paired.plan_id, 2, kwargs["instrument"],
            kwargs["policy_identity"])
        assert kwargs["approve"](request) is True
        assert allocations == [request]
        assert constructions[0][0]._approval is request
        return result
    monkeypatch.setattr(experiment, "run_sql_experiment", original_runner)
    def approve(request):
        requests.append(request)
        assert type(request) is experiment.ScientificRequest and allocations == []
        return True
    assert _paired_call(plan, approve, factory) is result
    assert len(constructions) == len(allocations) == len(requests) == 1
    driver, paired, live_plan, config, kwargs = constructions[0]
    assert paired is plan.paired_plan and live_plan is plan.live_plan and config is plan.config
    assert kwargs["executor"] is executor and kwargs["capture"] is plan.capture
    assert not driver._active and driver._approval is None


def test_paired_approval_mutation_refuses_before_executor(monkeypatch):
    plan = _paired(monkeypatch)
    allocations = []
    monkeypatch.setattr(experiment.assets, "safe_path", lambda path: path)
    def approve(request):
        plan.config.model = "mutated"
        return True
    with pytest.raises(experiment.ExperimentAdmissionError):
        _paired_call(plan, approve, allocations.append)
    assert allocations == []


def test_missing_measurements_stay_none_not_zero(monkeypatch):
    plan = _paired(monkeypatch)
    result = paired_bird.adjudicate_paired_bird(plan.paired_plan, (), ())
    assert result.comparison is result.cost is result.usage is None
    assert result.measurement is False and result.status == "void"


def _scripted(task_id, backend):
    _, _, settings = _base()
    return episodes.SqlEpisode(
        1, "scripted", _ids("heldout", task_id), "ptc", task_id,
        "a" * 64, "b" * 64, "synthetic schema", "synthetic prompt", backend,
        settings, (), "", "", "scripted_final", ExResult(0.0, "pred_empty", True))


def test_cross_harness_compatible_scripted_projection_cannot_authorize(monkeypatch):
    projection, blockers = readiness.cross_harness_readiness(
        ("task-0", "task-1"),
        tuple(_scripted(name, "declared-left") for name in ("task-0", "task-1")),
        tuple(_scripted(name, "declared-right") for name in ("task-0", "task-1")))
    assert projection.paired_count == 2 and projection.recorded_declarations_compatible
    assert len(projection.unrepresented_invariants) == 4 and len(blockers) == 3
    plan = replace(_reuse(), stage="cross_harness_cotraining", swap=projection)
    calls, approvals, allocations, _, _, factory = _delegates(monkeypatch)
    with pytest.raises(readiness.ScienceReadinessError, match="second SDK backend"):
        _reuse_call(plan, lambda request: True, factory)
    assert calls == approvals == allocations == []


def test_cotraining_missing_checkpoint_seed_authority_blocks_paired_entry(monkeypatch):
    plan = replace(_paired(monkeypatch), stage="cross_harness_cotraining")
    allocations = []
    with pytest.raises(readiness.ScienceReadinessError, match="checkpoint/seed/cohort"):
        _paired_call(plan, lambda request: True, allocations.append)
    assert allocations == []


def test_denial_does_not_read_sources_or_mutate_inputs(monkeypatch):
    plan = _reuse()
    before = plan._state()
    def forbidden(*args, **kwargs):
        raise AssertionError("source/file access or executor initialization")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(core.PilotExecutor, "__init__", forbidden)
    with pytest.raises(readiness.ScienceReadinessError):
        _reuse_call(plan, lambda request: False, forbidden)
    assert plan._state() == before


def test_composed_capture_tuple_covers_reviewed_science_admission_module():
    """UNRUN production tuple contract; original assertion retained."""
    from train import sql_capture

    assert "train/sql_scientific_readiness.py" in sql_capture._OWNED_SOURCE_PATHS, (
        "composed owned capture omits reviewed scientific admission source"
    )
    assert len(sql_capture._OWNED_SOURCE_PATHS) == len(set(sql_capture._OWNED_SOURCE_PATHS))


def test_composed_missing_science_module_refuses_owned_source_capture(monkeypatch):
    """UNRUN blocker contract; no expected hash is invented or refreshed."""
    from train import sql_capture

    missing = "train/sql_scientific_readiness.py"
    reads = []

    def synthetic_bytes(path):
        reads.append(path.as_posix())
        if path.as_posix().endswith("/" + missing):
            raise FileNotFoundError("synthetic missing reviewed admission module")
        return b"SYNTHETIC reviewed source buffer\n"

    monkeypatch.setattr(Path, "read_bytes", synthetic_bytes)
    refused = False
    try:
        sql_capture._owned_sources()
    except FileNotFoundError:
        refused = True
    assert refused, "missing reviewed science module escaped actual source capture"
    assert sum(name.endswith("/" + missing) for name in reads) == 1


@pytest.mark.parametrize("entry", ["reuse", "paired"])
def test_memory_v2_missing_readiness_source_refuses_before_allocation(monkeypatch, entry):
    from train import sql_capture, sql_skill_eval

    plan = _reuse() if entry == "reuse" else _paired(monkeypatch)
    source_root = sql_capture._ROOT
    inventory = {source_root / name: b"SYNTHETIC reviewed V2 source\n"
                 for name in sql_capture.OWNED_SOURCE_PATHS_V2}
    monkeypatch.setattr(Path, "read_bytes", lambda path: inventory[path])
    # New, explicitly synthetic V2 fixtures, never reissue a historical approval.
    if entry == "reuse":
        paths, digest = skills._workflow_sources(source_root)
        binding = replace(plan.approved_skill.promotion.binding,
                          source_paths=paths, source_sha256=digest)
        promotion = replace(plan.approved_skill.promotion, binding=binding)
        approved = replace(plan.approved_skill, promotion=promotion,
                           promotion_sha256=skills._sha(skills.encode_promotion(promotion)))
        plan = replace(plan, approved_skill=approved)
        monkeypatch.setattr(sql_skill_eval, "_ROOT", source_root)
        monkeypatch.setattr(sql_skill_pilot, "validate_approval", lambda approved: None)
    else:
        paths, digest = sql_capture._owned_sources()
        plan = replace(plan, settings=replace(plan.settings, source_paths=paths, source_sha256=digest))

    effects = []
    missing = source_root / "train/sql_scientific_readiness.py"
    del inventory[missing]

    def retained_bytes(path):
        if path not in inventory:
            raise FileNotFoundError("missing frozen V2 source")
        return inventory[path]

    def forbidden(*args, **kwargs):
        effects.append("allocation-or-dispatch")
        raise AssertionError("missing source reached allocation or model dispatch")

    monkeypatch.setattr(Path, "read_bytes", retained_bytes)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(live, "run_sql_live", forbidden)
    monkeypatch.setattr(experiment.assets, "safe_path", lambda path: path)
    error = ValueError if entry == "reuse" else experiment.ExperimentAdmissionError
    with pytest.raises(error, match="selected skill workflow|scientific admission"):
        (_reuse_call if entry == "reuse" else _paired_call)(plan, lambda request: True, forbidden)
    assert effects == []


@pytest.mark.parametrize("entry", ["reuse", "paired"])
def test_composed_denied_science_has_zero_factories_and_source_reads(monkeypatch, entry):
    plan = _reuse() if entry == "reuse" else _paired(monkeypatch)
    effects = []

    def forbidden(*args, **kwargs):
        effects.append("factory-or-read")
        raise AssertionError("denied science touched source or factory")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(core.PilotExecutor, "__init__", forbidden)
    monkeypatch.setattr(experiment.assets, "safe_path", lambda path: path)
    call = _reuse_call if entry == "reuse" else _paired_call
    error = readiness.ScienceReadinessError if entry == "reuse" else experiment.ExperimentAdmissionError
    with pytest.raises(error, match="scientific"):
        call(plan, lambda request: False, forbidden)
    assert effects == []


@pytest.mark.parametrize("entry", ["reuse", "paired"])
def test_composed_engineering_truthy_result_never_unlocks_science(monkeypatch, entry):
    from types import SimpleNamespace

    plan = _reuse() if entry == "reuse" else _paired(monkeypatch)
    engineering = SimpleNamespace(
        native_qualification=False, phase_returncodes=(0, 0),
        service_handle=object(), scope="engineering_observation_not_qualification",
    )
    allocations = []
    monkeypatch.setattr(experiment.assets, "safe_path", lambda path: path)
    call = _reuse_call if entry == "reuse" else _paired_call
    error = readiness.ScienceReadinessError if entry == "reuse" else experiment.ExperimentAdmissionError
    with pytest.raises(error, match="scientific"):
        call(plan, lambda request: engineering, allocations.append)
    assert allocations == [] and engineering.native_qualification is False


def test_guard_loss_science_approval_assertion_witness_and_restore(monkeypatch):
    _, _, allocations, _, _, factory = _delegates(monkeypatch)
    def witness():
        allocations.clear()
        try:
            _reuse_call(_reuse(), lambda request: False, factory)
        except readiness.ScienceReadinessError:
            pass
        assert allocations == [], "unapproved executor allocation"
    witness()
    with monkeypatch.context() as mutation:
        mutation.setattr(readiness, "require_science_approval", lambda accepted: None)
        with pytest.raises(AssertionError, match="unapproved executor allocation"):
            witness()
    witness()


def test_guard_loss_ordered_membership_assertion_witness_and_restore(monkeypatch):
    plan = _paired(monkeypatch)
    def witness():
        refused = False
        try:
            replace(plan, live_plan=live.SqlLivePlan(tuple(reversed(plan.live_plan.inputs))))
        except readiness.ScienceReadinessError:
            refused = True
        assert refused, "reordered paired membership admitted"
    witness()
    with monkeypatch.context() as mutation:
        mutation.setattr(readiness.SqlScientificPlan, "_paired_membership", lambda plan: None)
        with pytest.raises(AssertionError, match="reordered paired membership admitted"):
            witness()
    witness()
