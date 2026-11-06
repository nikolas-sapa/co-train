"""Synthetic structural declarations only, never genuine frontier evidence.

Uses actual stdlib hashing and public module API. Guard-loss doubles below
deliberately break one private guard at a time, not any production consumer.
"""

from __future__ import annotations

import builtins
from dataclasses import fields, is_dataclass, replace, FrozenInstanceError
import hashlib
import importlib
import inspect
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest


def _sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def api():
    return importlib.import_module("train.frontier_bindings")


def _limits(api):
    return api.BindingLimits(1024, 4096, 12289, 12289, 1 << 20, 16 << 20, 256, 10)


def _fixture(api, n=8, g=4, excluded=1):
    tasks = tuple(
        api.TaskBinding(f"task-{i}", _sha(f"task{i}".encode()), _sha(f"db{i}".encode()))
        for i in range(n)
    )
    eligible = tuple(task.task_id for i, task in enumerate(tasks) if i != excluded)
    exclusions = (() if excluded is None else (
        api.PreparationExclusion(tasks[excluded].task_id, "preparation-excluded"),
    ))
    plan = api.MeasurementPlan(
        plan_id="p" * 32, execution_id="execution", policy_revision="a" * 40,
        checkpoint_sha256=_sha(b"x"), adapter_sha256=None,
        runtime_id="runtime", provider_id="provider", route_id="route",
        generation_sha256=_sha(b"generation"), prompt_sha256=_sha(b"prompt"),
        template_sha256=_sha(b"template"), tool_sha256=_sha(b"tool"),
        instrument_sha256=_sha(b"instrument"), source_sha256=_sha(b"source"),
        draw_sha256=_sha(b"draw"), supplement_sha256=_sha(b"supplement"),
        tasks=tasks, eligible_ids=eligible, exclusions=exclusions, g=g,
        dead_ceiling=0.6,
        scorer=api.ScorerBinding(_sha(b"extract"), _sha(b"scorer"), "set", 30.0, 500000),
        resource_limits_id="opaque-resource", grant_reference="unverified-grant",
    )
    expected = [api.ExpectedEvidence(
        "checkpoint", "checkpoint", plan.plan_id, plan.execution_id,
        None, None, None, None, None, 1, _sha(b"x"),
    )]
    blobs = [api.EvidenceBlob("checkpoint", b"x")]
    samples = []
    for task_id in eligible:
        for index in range(g):
            attempt = f"{task_id}-attempt-{index}"
            generation = f"{task_id}-generation-{index}"
            scoring = f"{task_id}-scoring-{index}"
            prediction = _sha(attempt.encode())
            for evidence_id, purpose, reference in (
                (generation, "generation", None), (scoring, "scoring", generation),
            ):
                expected.append(api.ExpectedEvidence(
                    evidence_id, purpose, plan.plan_id, plan.execution_id,
                    task_id, index, attempt, reference, prediction, 1, _sha(b"x"),
                ))
                blobs.append(api.EvidenceBlob(evidence_id, b"x"))
            samples.append(api.SampleRecord(
                task_id, index, attempt, "scored", index % 2,
                generation, scoring, prediction,
            ))
    return SimpleNamespace(
        plan=plan, expected=tuple(expected),
        candidate=api.EvidenceBatch(plan, tuple(blobs), tuple(samples)),
        limits=_limits(api),
    )


@pytest.fixture
def synthetic(api):
    return _fixture(api)


def _validate(api, fixture, **overrides):
    values = dict(
        plan=fixture.plan, expected_evidence=fixture.expected,
        candidate=fixture.candidate, limits=fixture.limits,
    )
    values.update(overrides)
    return api.validate_frontier_bindings(**values)


def _authority(report):
    assert report.provenance == "unverified", "provenance guard lost"
    assert report.attested_facts == ()
    assert report.genuine_measurement_accepted is False
    assert report.training_authorized is False
    assert report.reason == "external provenance/attestation verification unavailable"


def _refuses(api, fixture, message="expected opaque refusal", **overrides):
    try:
        _validate(api, fixture, **overrides)
    except api.BindingError as exc:
        assert type(exc) is api.BindingError
        assert len(str(exc)) <= 80
        assert str(exc) == "invalid frontier bindings"
        assert exc.__suppress_context__ is True
        return
    raise AssertionError(message)


def _payload_size(value):
    if type(value) is str:
        return len(value.encode("utf-8"))
    if type(value) is bytes:
        return len(value)
    if type(value) is tuple:
        return sum(_payload_size(item) for item in value)
    if is_dataclass(value):
        return sum(_payload_size(getattr(value, field.name)) for field in fields(value))
    return 0


def test_public_api_exact_fields(api):
    expected = {
        "BindingLimits": (
            "max_planned_tasks", "max_scheduled_slots", "max_expected_evidence",
            "max_raw_evidence", "max_item_bytes", "max_aggregate_bytes",
            "max_identifier_bytes", "max_diagnostics",
        ),
        "TaskBinding": ("task_id", "task_sha256", "database_sha256"),
        "PreparationExclusion": ("task_id", "reason"),
        "ScorerBinding": (
            "extraction_source_sha256", "scorer_source_sha256", "comparison",
            "timeout_s", "max_rows",
        ),
        "MeasurementPlan": (
            "plan_id", "execution_id", "policy_revision", "checkpoint_sha256",
            "adapter_sha256", "runtime_id", "provider_id", "route_id",
            "generation_sha256", "prompt_sha256", "template_sha256", "tool_sha256",
            "instrument_sha256", "source_sha256", "draw_sha256", "supplement_sha256",
            "tasks", "eligible_ids", "exclusions", "g", "dead_ceiling", "scorer",
            "resource_limits_id", "grant_reference",
        ),
        "ExpectedEvidence": (
            "evidence_id", "purpose", "plan_id", "execution_id", "task_id",
            "slot_index", "attempt_id", "generation_evidence_id",
            "prediction_sha256", "byte_count", "sha256",
        ),
        "EvidenceBlob": ("evidence_id", "payload"),
        "SampleRecord": (
            "task_id", "slot_index", "attempt_id", "status", "score",
            "generation_evidence_id", "scoring_evidence_id", "prediction_sha256",
        ),
        "EvidenceBatch": ("plan", "blobs", "samples"),
        "SlotDisposition": (
            "task_ordinal", "slot_index", "disposition",
            "bindings_consistent", "validly_scored",
        ),
        "BindingReport": (
            "planned_tasks", "eligible_tasks", "excluded_tasks", "scheduled_slots",
            "observed_slots", "declared_attempts", "matched_evidence",
            "valid_declared_scores", "disposition_counts", "slots", "diagnostics",
            "total_issues", "diagnostics_truncated", "bindings_consistent",
            "schedule_complete", "all_samples_validly_scored",
        ),
    }
    assert set(api.__all__) == set(expected) | {"BindingError", "validate_frontier_bindings"}
    for name, names in expected.items():
        cls = getattr(api, name)
        assert tuple(field.name for field in fields(cls)) == names
        assert cls.__dataclass_params__.frozen is True
        assert "__slots__" in cls.__dict__
    signature = inspect.signature(api.validate_frontier_bindings)
    assert list(signature.parameters) == ["plan", "expected_evidence", "candidate", "limits"]
    assert signature.parameters["limits"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["limits"].default is inspect.Parameter.empty


def test_complete_schedule(api, synthetic):
    report = _validate(api, synthetic)
    assert (report.planned_tasks, report.excluded_tasks, report.eligible_tasks) == (8, 1, 7)
    assert report.scheduled_slots == report.observed_slots == report.declared_attempts == 28
    assert report.matched_evidence == 57
    assert report.valid_declared_scores == 28
    assert report.bindings_consistent and report.schedule_complete
    assert report.all_samples_validly_scored
    assert report.total_issues == 0 and report.diagnostics == ()
    assert [(slot.task_ordinal, slot.slot_index) for slot in report.slots] == [
        (ordinal, index) for ordinal in (0, 2, 3, 4, 5, 6, 7) for index in range(4)
    ]
    assert all(slot.disposition == "scored" and slot.validly_scored for slot in report.slots)
    assert dict(report.disposition_counts)["missing"] == 0
    _authority(report)


@pytest.mark.parametrize("whole_task", [False, True])
def test_missing_dispositions(api, synthetic, whole_task):
    samples = synthetic.candidate.samples
    kept = samples[4:] if whole_task else samples[1:]
    report = _validate(api, synthetic, candidate=replace(synthetic.candidate, samples=kept))
    assert report.observed_slots == (24 if whole_task else 27)
    assert dict(report.disposition_counts)["missing"] == (4 if whole_task else 1)
    assert report.schedule_complete is False
    assert report.bindings_consistent is False and report.all_samples_validly_scored is False
    _authority(report)


def _non_scored(api, status):
    fixture = _fixture(api, n=1, g=2, excluded=None)
    first = fixture.candidate.samples[0]
    score_id = first.scoring_evidence_id
    failure = status == "generation_failed"
    keep_scoring = status == "invalid_gold"
    changed = replace(
        first, status=status, score=None,
        scoring_evidence_id=score_id if keep_scoring else None,
        prediction_sha256=None if failure else first.prediction_sha256,
    )
    expected = tuple(
        replace(item, prediction_sha256=None)
        if failure and item.evidence_id == first.generation_evidence_id else item
        for item in fixture.expected
        if keep_scoring or item.evidence_id != score_id
    )
    blobs = tuple(item for item in fixture.candidate.blobs
                  if keep_scoring or item.evidence_id != score_id)
    fixture.expected = expected
    fixture.candidate = replace(
        fixture.candidate, blobs=blobs, samples=(changed, fixture.candidate.samples[1]),
    )
    return fixture


@pytest.mark.parametrize("status", ["generation_failed", "invalid_gold", "pending", "unknown"])
def test_non_scored_dispositions_stay_distinct(api, status):
    fixture = _non_scored(api, status)
    report = _validate(api, fixture)
    assert report.bindings_consistent is True and report.schedule_complete is True
    assert report.all_samples_validly_scored is False
    assert report.valid_declared_scores == 1
    assert report.excluded_tasks == 0  # Measurement invalidity is not preparation exclusion.
    assert dict(report.disposition_counts)[status] == 1
    assert report.slots[0].disposition == status and not report.slots[0].validly_scored
    assert report.total_issues >= 1
    _authority(report)


def test_failure_plus_zero_is_not_a_valid_score(api):
    fixture = _non_scored(api, "generation_failed")
    first = replace(fixture.candidate.samples[0], score=0)
    report = _validate(
        api, fixture, candidate=replace(fixture.candidate, samples=(first,)),
    )
    assert dict(report.disposition_counts)["generation_failed"] == 1
    assert report.valid_declared_scores == 0 and not report.bindings_consistent
    assert not report.all_samples_validly_scored


@pytest.mark.parametrize("field", [
    "plan_id", "execution_id", "policy_revision", "checkpoint_sha256", "adapter_sha256",
    "runtime_id", "provider_id", "route_id", "generation_sha256", "prompt_sha256",
    "template_sha256", "tool_sha256", "instrument_sha256", "source_sha256",
    "draw_sha256", "supplement_sha256", "g", "dead_ceiling", "resource_limits_id",
    "grant_reference", "tasks",
])
def test_complete_plan_projection_mutations(api, synthetic, field):
    if field == "tasks":
        value = (replace(synthetic.plan.tasks[0], database_sha256=_sha(b"other")),) + (
            synthetic.plan.tasks[1:]
        )
    elif field == "g":
        value = 5
    elif field == "dead_ceiling":
        value = 0.5
    elif field == "policy_revision":
        value = "b" * 40
    elif field.endswith("sha256"):
        value = _sha(b"other")
    else:
        value = "other"
    changed = replace(synthetic.plan, **{field: value})
    report = _validate(api, synthetic, candidate=replace(synthetic.candidate, plan=changed))
    assert not report.bindings_consistent
    _authority(report)


@pytest.mark.parametrize("field,value", [
    ("extraction_source_sha256", "b" * 64), ("scorer_source_sha256", "b" * 64),
    ("comparison", "multiset"), ("timeout_s", 60.0), ("max_rows", 17),
])
def test_scorer_projection_mutations(api, synthetic, field, value):
    plan = replace(synthetic.plan, scorer=replace(synthetic.plan.scorer, **{field: value}))
    report = _validate(api, synthetic, candidate=replace(synthetic.candidate, plan=plan))
    assert not report.bindings_consistent


@pytest.mark.parametrize("field,value", [
    ("plan_id", "wrong"), ("execution_id", "wrong"), ("purpose", "scoring"),
    ("task_id", "wrong"), ("slot_index", 1), ("attempt_id", "wrong"),
    ("generation_evidence_id", "wrong"), ("prediction_sha256", "b" * 64),
    ("byte_count", 2), ("sha256", "b" * 64),
])
def test_independent_expected_binding_mutations(api, synthetic, field, value):
    expected = list(synthetic.expected)
    expected[1] = replace(expected[1], **{field: value})
    report = _validate(api, synthetic, expected_evidence=tuple(expected))
    assert not report.bindings_consistent


@pytest.mark.parametrize("field,value", [
    ("task_id", "outside"), ("slot_index", 4), ("attempt_id", "changed"),
    ("prediction_sha256", "b" * 64), ("generation_evidence_id", "missing"),
    ("scoring_evidence_id", "missing"),
])
def test_sample_and_score_generation_association(api, synthetic, field, value):
    first = replace(synthetic.candidate.samples[0], **{field: value})
    candidate = replace(synthetic.candidate, samples=(first,) + synthetic.candidate.samples[1:])
    assert not _validate(api, synthetic, candidate=candidate).bindings_consistent


def test_scoring_cannot_reference_another_prediction(api, synthetic):
    expected = list(synthetic.expected)
    expected[2] = replace(
        expected[2], generation_evidence_id=synthetic.candidate.samples[1].generation_evidence_id,
    )
    assert not _validate(api, synthetic, expected_evidence=tuple(expected)).bindings_consistent


@pytest.mark.parametrize("kind", ["missing", "extra", "payload", "unreferenced", "checkpoint"])
def test_raw_evidence_and_checkpoint_coverage(api, synthetic, kind):
    candidate, expected = synthetic.candidate, synthetic.expected
    if kind == "missing":
        candidate = replace(candidate, blobs=candidate.blobs[1:])
    elif kind == "extra":
        candidate = replace(candidate, blobs=candidate.blobs + (api.EvidenceBlob("extra", b"x"),))
    elif kind == "payload":
        candidate = replace(candidate, blobs=(replace(candidate.blobs[0], payload=b"y"),)
                            + candidate.blobs[1:])
    elif kind == "unreferenced":
        expected += (replace(expected[1], evidence_id="extra"),)
        candidate = replace(candidate, blobs=candidate.blobs + (api.EvidenceBlob("extra", b"x"),))
    else:
        expected = (replace(expected[0], task_id="task-0"),) + expected[1:]
    assert not _validate(api, synthetic, candidate=candidate, expected_evidence=expected).bindings_consistent


@pytest.mark.parametrize("kind", [
    "planned", "eligible", "excluded", "expected", "raw", "attempt", "slot", "receipt",
])
def test_duplicate_identities_refuse(api, synthetic, kind):
    plan, expected, candidate = synthetic.plan, synthetic.expected, synthetic.candidate
    if kind in ("planned", "eligible", "excluded"):
        name = {"planned": "tasks", "eligible": "eligible_ids", "excluded": "exclusions"}[kind]
        values = getattr(plan, name)
        plan = replace(plan, **{name: values + values[:1]})
    elif kind == "expected":
        expected += expected[:1]
    elif kind == "raw":
        candidate = replace(candidate, blobs=candidate.blobs + candidate.blobs[:1])
    else:
        first, second = candidate.samples[:2]
        changed = {
            "attempt": replace(second, attempt_id=first.attempt_id),
            "slot": first,
            "receipt": replace(second, generation_evidence_id=first.generation_evidence_id),
        }[kind]
        candidate = replace(candidate, samples=(first, changed) + candidate.samples[2:])
    _refuses(api, synthetic, plan=plan, expected_evidence=expected, candidate=candidate)


def test_inventory_bytes_are_not_a_separately_pinned_checkpoint_receipt(api, synthetic):
    assert _validate(api, synthetic).bindings_consistent
    receipt = b"separate checkpoint observation, not the unchanged inventory bytes"
    declaration = replace(
        synthetic.expected[0], byte_count=len(receipt), sha256=_sha(receipt),
    )
    candidate = replace(synthetic.candidate, blobs=(
        replace(synthetic.candidate.blobs[0], payload=receipt),
        *synthetic.candidate.blobs[1:],
    ))
    report = _validate(
        api, synthetic, expected_evidence=(declaration, *synthetic.expected[1:]),
        candidate=candidate,
    )
    assert report.matched_evidence == len(synthetic.expected)
    assert report.schedule_complete
    assert ("checkpoint_inventory", None, None) in report.diagnostics
    assert not report.bindings_consistent
    assert not report.all_samples_validly_scored
    _authority(report)
    assert _validate(api, synthetic).bindings_consistent


def test_fabricated_matching_pins_and_replay_never_authenticate(api, synthetic):
    first = _validate(api, synthetic)
    second = _validate(api, synthetic)
    assert first == second and first.bindings_consistent
    _authority(first)
    _authority(second)
    changed = replace(synthetic.plan, execution_id="another-execution")
    assert not _validate(api, synthetic, plan=changed).bindings_consistent
    # Pins in fixture were fabricated/self-derived with real hashing, not attested.
    for field in ("provenance", "attested_facts", "genuine_measurement_accepted", "training_authorized"):
        with pytest.raises(TypeError):
            replace(first, **{field: True})


@pytest.mark.parametrize("case", [
    "plan-object", "tasks-iterator", "expected-list", "candidate-mapping", "raw-bytearray",
    "bool-g", "huge-g", "nan-ceiling", "infinite-timeout", "huge-rows", "nan-score",
    "bool-score", "invalid-status", "invalid-purpose", "invalid-mode", "surrogate",
    "missing-plan-field", "missing-task-field", "missing-expected-field",
    "missing-candidate-field", "record-subclass", "str-subclass", "tuple-subclass",
])
def test_exact_types_and_missing_slots(api, synthetic, case):
    plan, candidate, expected = synthetic.plan, synthetic.candidate, synthetic.expected
    if case == "plan-object":
        plan = object()
    elif case == "tasks-iterator":
        plan = replace(plan, tasks=iter(plan.tasks))
    elif case == "expected-list":
        expected = list(expected)
    elif case == "candidate-mapping":
        candidate = {"plan": plan}
    elif case == "raw-bytearray":
        candidate = replace(candidate, blobs=(replace(candidate.blobs[0], payload=bytearray(b"x")),))
    elif case == "bool-g":
        plan = replace(plan, g=True)
    elif case == "huge-g":
        plan = replace(plan, g=1 << 100000)
    elif case == "nan-ceiling":
        plan = replace(plan, dead_ceiling=float("nan"))
    elif case == "infinite-timeout":
        plan = replace(plan, scorer=replace(plan.scorer, timeout_s=float("inf")))
    elif case == "huge-rows":
        plan = replace(plan, scorer=replace(plan.scorer, max_rows=1 << 100000))
    elif case in ("nan-score", "bool-score", "invalid-status"):
        first = replace(candidate.samples[0], **(
            {"status": "not-a-status"} if case == "invalid-status" else
            {"score": True if case == "bool-score" else float("nan")}
        ))
        candidate = replace(candidate, samples=(first,) + candidate.samples[1:])
    elif case == "invalid-purpose":
        expected = (replace(expected[0], purpose="not-a-purpose"),) + expected[1:]
    elif case == "invalid-mode":
        plan = replace(plan, scorer=replace(plan.scorer, comparison="ordered"))
    elif case == "surrogate":
        plan = replace(plan, plan_id="\ud800")
    elif case.startswith("missing-"):
        cls = {
            "missing-plan-field": api.MeasurementPlan,
            "missing-task-field": api.TaskBinding,
            "missing-expected-field": api.ExpectedEvidence,
            "missing-candidate-field": api.EvidenceBatch,
        }[case]
        broken = object.__new__(cls)
        if cls is api.MeasurementPlan:
            plan = broken
        elif cls is api.TaskBinding:
            plan = replace(plan, tasks=(broken,))
        elif cls is api.ExpectedEvidence:
            expected = (broken,)
        else:
            candidate = broken
    elif case == "record-subclass":
        class Subclass(api.TaskBinding):
            __slots__ = ()
        plan = replace(plan, tasks=(Subclass("x", "a" * 64, "b" * 64),))
    elif case == "str-subclass":
        class Text(str):
            pass
        plan = replace(plan, plan_id=Text("x"))
    else:
        class Items(tuple):
            pass
        expected = Items(expected)
    _refuses(api, synthetic, plan=plan, candidate=candidate, expected_evidence=expected)


def test_hostile_values_are_never_called(api, synthetic):
    touched = []

    class Hostile:
        def __getattribute__(self, name):
            touched.append(name)
            raise AssertionError("SECRET hostile descriptor")

        def __eq__(self, other):
            touched.append("eq")
            raise AssertionError("SECRET equality")

        def __iter__(self):
            touched.append("iter")
            raise AssertionError("SECRET iterator")

        def __repr__(self):
            touched.append("repr")
            raise AssertionError("SECRET repr")

    hostile = Hostile()
    for changed in (
        replace(synthetic.plan, plan_id=hostile),
        replace(synthetic.plan, tasks=hostile),
        replace(synthetic.plan, g=hostile),
        replace(synthetic.plan, scorer=hostile),
    ):
        _refuses(api, synthetic, plan=changed)
    _refuses(api, synthetic, expected_evidence=hostile)
    assert touched == []


@pytest.mark.parametrize("field,bound", [
    ("max_planned_tasks", 8), ("max_scheduled_slots", 28),
    ("max_expected_evidence", 57), ("max_raw_evidence", 57),
    ("max_item_bytes", 1), ("max_identifier_bytes", 32),
])
def test_small_limit_boundaries_before_hashing(api, synthetic, monkeypatch, field, bound):
    limits = replace(synthetic.limits, **{field: bound})
    assert _validate(api, synthetic, limits=limits).bindings_consistent
    hashed = []

    def forbidden(*args, **kwargs):
        hashed.append(True)
        raise AssertionError("hashing before bounds")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    _refuses(api, synthetic, limits=replace(limits, **{field: bound - 1}))
    assert hashed == []


def test_aggregate_budget_charges_every_repeated_payload_before_hashing(api, synthetic, monkeypatch):
    size = sum(_payload_size(value) for value in (
        synthetic.plan, synthetic.expected, synthetic.candidate,
    ))
    limits = replace(synthetic.limits, max_aggregate_bytes=size)
    assert _validate(api, synthetic, limits=limits).bindings_consistent
    hashed = []

    def forbidden(*args, **kwargs):
        hashed.append(True)
        raise AssertionError("aggregate checked too late")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    _refuses(api, synthetic, limits=replace(limits, max_aggregate_bytes=size - 1))
    assert hashed == []


@pytest.mark.parametrize("field,ceiling", [
    ("max_planned_tasks", 1024), ("max_scheduled_slots", 4096),
    ("max_expected_evidence", 12289), ("max_raw_evidence", 12289),
    ("max_item_bytes", 1 << 20), ("max_aggregate_bytes", 16 << 20),
    ("max_identifier_bytes", 256), ("max_diagnostics", 10),
])
def test_implementation_limit_ceilings(api, synthetic, field, ceiling):
    assert _validate(api, synthetic, limits=replace(synthetic.limits, **{field: ceiling})).bindings_consistent
    _refuses(api, synthetic, limits=replace(synthetic.limits, **{field: ceiling + 1}))
    _refuses(api, synthetic, limits=replace(synthetic.limits, **{field: True}))


def test_product_bound_precedes_hashing_and_expansion(api, synthetic, monkeypatch):
    changed = replace(synthetic.plan, g=4096)
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("product checked too late")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    _refuses(api, synthetic, plan=changed)
    assert touched == []


def test_hash_each_blob_once_and_only_after_valid_shape(api, synthetic, monkeypatch):
    real = hashlib.sha256
    seen = []

    def tracked(payload):
        seen.append(payload)
        return real(payload)

    monkeypatch.setattr(api.hashlib, "sha256", tracked)
    assert _validate(api, synthetic).matched_evidence == 57
    assert len(seen) == 57


def test_diagnostic_truncation_never_becomes_acceptance(api, synthetic):
    expected = tuple(replace(item, sha256="b" * 64) for item in synthetic.expected)
    report = _validate(
        api, synthetic, expected_evidence=expected,
        limits=replace(synthetic.limits, max_diagnostics=2),
    )
    assert report.total_issues >= 57
    assert len(report.diagnostics) == 2 and report.diagnostics_truncated
    assert not report.bindings_consistent and not report.all_samples_validly_scored


def test_immutable_opaque_reports_and_errors(api, synthetic):
    report = _validate(api, synthetic)
    before = repr(report)
    for raw in ("task-0", "execution", "unverified-grant", "checkpoint", "p" * 32):
        assert raw not in before
    assert "b'x'" not in before
    with pytest.raises(FrozenInstanceError):
        report.observed_slots = 999
    with pytest.raises(FrozenInstanceError):
        report.slots[0].disposition = "verified"
    assert type(report.slots) is type(report.diagnostics) is type(report.disposition_counts) is tuple
    object.__setattr__(synthetic.plan.tasks[0], "task_id", "SECRET SELECT 1 /never-open")
    object.__setattr__(synthetic.candidate.samples[0], "attempt_id", "SECRET")
    assert repr(report) == before
    broken = replace(synthetic.plan, plan_id="SECRET" * 100)
    _refuses(api, synthetic, plan=broken)
    assert "SECRET" not in repr(report)


def test_no_side_effects_and_opaque_path_identifiers(api, synthetic, monkeypatch, capsys):
    task = replace(synthetic.plan.tasks[0], task_id="https://invalid.test/never-open")
    tasks = (task,) + synthetic.plan.tasks[1:]
    old = synthetic.plan.tasks[0].task_id
    plan = replace(synthetic.plan, tasks=tasks, eligible_ids=(task.task_id,) + synthetic.plan.eligible_ids[1:])
    expected = tuple(replace(item, task_id=task.task_id) if item.task_id == old else item
                     for item in synthetic.expected)
    samples = tuple(replace(item, task_id=task.task_id) if item.task_id == old else item
                    for item in synthetic.candidate.samples)
    candidate = replace(synthetic.candidate, plan=plan, samples=samples)
    touched = []
    real_import = builtins.__import__

    def deny(*args, **kwargs):
        touched.append("side-effect")
        raise AssertionError("validator performed external work")

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {
            "torch", "trl", "transformers", "unsloth", "datasets", "vllm",
            "bench", "sqlite3", "socket", "subprocess",
        }:
            deny()
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as guarded_scope:
        guarded_scope.setattr(builtins, "__import__", guarded)
        guarded_scope.setattr(builtins, "open", deny)
        guarded_scope.setattr(Path, "open", deny)
        guarded_scope.setattr(Path, "resolve", deny)
        guarded_scope.setattr(sqlite3, "connect", deny)
        guarded_scope.setattr(socket, "socket", deny)
        guarded_scope.setattr(subprocess, "Popen", deny)
        report = _validate(api, synthetic, plan=plan, expected_evidence=expected, candidate=candidate)
        assert report.bindings_consistent
    assert touched == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("guard", ["expectation", "association", "uniqueness", "coverage", "bounds", "provenance"])
def test_guard_loss_controls_fail_at_intended_call_phase(api, synthetic, monkeypatch, guard):
    assert _validate(api, synthetic).bindings_consistent
    kwargs = {}
    expected = synthetic.expected
    if guard == "expectation":
        expected = (expected[0], replace(expected[1], sha256="b" * 64)) + expected[2:]
        kwargs["expected_evidence"] = expected
        helper = "_pins_match"
    elif guard == "association":
        expected = (expected[0], replace(expected[1], task_id="wrong")) + expected[2:]
        kwargs["expected_evidence"] = expected
        helper = "_association_matches"
    elif guard == "uniqueness":
        kwargs["candidate"] = replace(
            synthetic.candidate, blobs=synthetic.candidate.blobs + synthetic.candidate.blobs[:1],
        )
        helper = "_unique"
    elif guard == "coverage":
        kwargs["candidate"] = replace(synthetic.candidate, samples=synthetic.candidate.samples[1:])
        helper = "_coverage_complete"
    elif guard == "bounds":
        size = sum(_payload_size(v) for v in (synthetic.plan, expected, synthetic.candidate))
        kwargs["limits"] = replace(synthetic.limits, max_aggregate_bytes=size - 1)
        helper = None
    else:
        helper = None

    def oracle():
        if guard in ("uniqueness", "bounds"):
            _refuses(api, synthetic, message=guard + " guard lost", **kwargs)
        elif guard == "coverage":
            assert not _validate(api, synthetic, **kwargs).schedule_complete, "coverage guard lost"
        elif guard == "provenance":
            _authority(_validate(api, synthetic))
        else:
            assert not _validate(api, synthetic, **kwargs).bindings_consistent, guard + " guard lost"

    oracle()  # Original guard refuses the specific invalid data, setup is valid.
    with monkeypatch.context() as mutant:
        if helper is not None:
            mutant.setattr(api, helper, lambda *args: True if guard != "uniqueness" else None)
        elif guard == "bounds":
            mutant.setattr(api._Budget, "charge", lambda self, amount: None)
        else:
            mutant.setattr(api.BindingReport, "provenance", property(lambda self: "verified"))
        with pytest.raises(AssertionError) as caught:
            oracle()
        assert str(caught.value).splitlines()[0] == guard + " guard lost"
    oracle()
    assert _validate(api, synthetic).bindings_consistent
    _authority(_validate(api, synthetic))


def test_fresh_stdlib_audit_no_external_work():
    repo = Path(__file__).resolve().parents[1]
    child = (
        "import builtins, hashlib, sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "from train import frontier_bindings as a\n"
        "h = hashlib.sha256(b'x').hexdigest()\n"
        "p = a.MeasurementPlan('p','e','a'*40,h,None,'r','v','route',h,h,h,h,h,h,h,h,\n"
        "    (a.TaskBinding('/never/open',h,h),),('/never/open',),(),2,0.6,\n"
        "    a.ScorerBinding(h,h,'set',1.0,1),'resource','unverified-grant')\n"
        "x = [a.ExpectedEvidence('c','checkpoint','p','e',None,None,None,None,None,1,h)]\n"
        "b = [a.EvidenceBlob('c',b'x')]\n"
        "s = []\n"
        "for i in range(2):\n"
        "    g,z,t = 'g'+str(i),'s'+str(i),'a'+str(i)\n"
        "    x.extend((a.ExpectedEvidence(g,'generation','p','e','/never/open',i,t,None,h,1,h),\n"
        "              a.ExpectedEvidence(z,'scoring','p','e','/never/open',i,t,g,h,1,h)))\n"
        "    b.extend((a.EvidenceBlob(g,b'x'),a.EvidenceBlob(z,b'x')))\n"
        "    s.append(a.SampleRecord('/never/open',i,t,'scored',0,g,z,h))\n"
        "batch = a.EvidenceBatch(p,tuple(b),tuple(s))\n"
        "limits = a.BindingLimits(1,2,5,5,1,16384,64,2)\n"
        "events = []\n"
        "def audit(event,args):\n"
        "    if event == 'open' or event.startswith(('socket.','subprocess.','os.')):\n"
        "        events.append(event)\n"
        "        raise AssertionError('external effect')\n"
        "sys.addaudithook(audit)\n"
        "original = builtins.__import__\n"
        "def guarded(name,*args,**kwargs):\n"
        "    if name.split('.')[0] not in {'math','hashlib','dataclasses','typing'}:\n"
        "        events.append('import')\n"
        "        raise AssertionError('unexpected runtime import')\n"
        "    return original(name,*args,**kwargs)\n"
        "builtins.__import__ = guarded\n"
        "r = a.validate_frontier_bindings(p,tuple(x),batch,limits=limits)\n"
        "assert r.bindings_consistent and r.provenance == 'unverified'\n"
        "assert not r.training_authorized and not events\n"
        "print('OFFLINE_BINDINGS_AUDIT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child], capture_output=True, text=True, timeout=12,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OFFLINE_BINDINGS_AUDIT_OK"


def test_checkpoint_inventory_pin_not_just_projection(api, synthetic):
    changed = replace(synthetic.plan, checkpoint_sha256=_sha(b"another inventory"))
    report = _validate(
        api, synthetic, plan=changed, candidate=replace(synthetic.candidate, plan=changed),
    )
    assert not report.bindings_consistent and report.valid_declared_scores == 0


@pytest.mark.parametrize("field", ["task_sha256", "database_sha256", "exclusion_reason"])
def test_remaining_task_projection_fields(api, synthetic, field):
    if field == "exclusion_reason":
        plan = replace(synthetic.plan, exclusions=(
            replace(synthetic.plan.exclusions[0], reason="other-reason"),
        ))
    else:
        tasks = (replace(synthetic.plan.tasks[0], **{field: "b" * 64}),) + synthetic.plan.tasks[1:]
        plan = replace(synthetic.plan, tasks=tasks)
    assert not _validate(
        api, synthetic, candidate=replace(synthetic.candidate, plan=plan),
    ).bindings_consistent


@pytest.mark.parametrize("case", ["order", "partition", "excluded-eligible"])
def test_plan_membership_is_an_ordered_partition(api, synthetic, case):
    plan = synthetic.plan
    if case == "order":
        plan = replace(plan, eligible_ids=tuple(reversed(plan.eligible_ids)))
    elif case == "partition":
        plan = replace(plan, eligible_ids=plan.eligible_ids[1:])
    else:
        plan = replace(plan, exclusions=(replace(plan.exclusions[0], task_id="task-0"),))
    _refuses(api, synthetic, plan=plan)


@pytest.mark.parametrize("status,score", [
    ("scored", None), ("invalid_gold", 0), ("pending", 0), ("unknown", 1),
    ("generation_failed", 0),
])
def test_status_score_combinations_never_become_zero_filled_success(api, synthetic, status, score):
    first = replace(synthetic.candidate.samples[0], status=status, score=score)
    report = _validate(
        api, synthetic,
        candidate=replace(synthetic.candidate, samples=(first,) + synthetic.candidate.samples[1:]),
    )
    assert not report.bindings_consistent and not report.all_samples_validly_scored
    assert not report.slots[0].validly_scored
    assert report.slots[0].disposition == status
    assert report.valid_declared_scores == 27


def test_multibyte_identifier_limit_and_invalid_unicode_are_bounded(api, synthetic):
    identifier = "é" * 128
    plan = replace(synthetic.plan, plan_id=identifier)
    expected = tuple(replace(item, plan_id=identifier) for item in synthetic.expected)
    candidate = replace(synthetic.candidate, plan=plan)
    assert _validate(
        api, synthetic, plan=plan, expected_evidence=expected, candidate=candidate,
    ).bindings_consistent
    _refuses(api, synthetic, plan=replace(plan, plan_id=identifier + "é"))


def test_raw_item_ceiling_checked_before_hashing(api, synthetic, monkeypatch):
    data = b"x" * (1 << 20)
    digest = _sha(data)
    plan = replace(synthetic.plan, checkpoint_sha256=digest)
    expected = (replace(synthetic.expected[0], byte_count=len(data), sha256=digest),) + synthetic.expected[1:]
    candidate = replace(
        synthetic.candidate, plan=plan,
        blobs=(replace(synthetic.candidate.blobs[0], payload=data),) + synthetic.candidate.blobs[1:],
    )
    assert _validate(api, synthetic, plan=plan, expected_evidence=expected, candidate=candidate).bindings_consistent
    over = replace(candidate, blobs=(replace(candidate.blobs[0], payload=data + b"x"),) + candidate.blobs[1:])
    touched = []

    def forbidden(*args):
        touched.append(True)
        raise AssertionError("item ceiling checked after hash")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    _refuses(api, synthetic, plan=plan, expected_evidence=expected, candidate=over)
    assert touched == []


def test_exact_aggregate_ceiling_and_one_byte_over_before_hashing(api, synthetic, monkeypatch):
    target = 16 << 20
    size = sum(_payload_size(v) for v in (synthetic.plan, synthetic.expected, synthetic.candidate))
    remaining = target - size
    blobs, expected = list(synthetic.candidate.blobs), list(synthetic.expected)
    for index in range(len(blobs)):
        amount = min((1 << 20) - 1, remaining)
        data = b"x" * (1 + amount)
        blobs[index] = replace(blobs[index], payload=data)
        expected[index] = replace(expected[index], byte_count=len(data), sha256=_sha(data))
        remaining -= amount
    assert remaining == 0
    plan = replace(synthetic.plan, checkpoint_sha256=expected[0].sha256)
    expected = tuple(expected)
    candidate = replace(synthetic.candidate, plan=plan, blobs=tuple(blobs))
    assert sum(_payload_size(v) for v in (plan, expected, candidate)) == target
    assert _validate(api, synthetic, plan=plan, expected_evidence=expected, candidate=candidate).bindings_consistent
    over = replace(candidate, blobs=candidate.blobs[:-1] + (
        replace(candidate.blobs[-1], payload=candidate.blobs[-1].payload + b"x"),
    ))
    touched = []

    def forbidden(*args):
        touched.append(True)
        raise AssertionError("aggregate ceiling checked after hash")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    _refuses(api, synthetic, plan=plan, expected_evidence=expected, candidate=over)
    assert touched == []


@pytest.mark.parametrize("name", [
    "BindingLimits", "ScorerBinding", "PreparationExclusion", "EvidenceBlob", "SampleRecord",
])
def test_other_missing_record_fields_remain_opaque(api, synthetic, name):
    broken = object.__new__(getattr(api, name))
    if name == "BindingLimits":
        _refuses(api, synthetic, limits=broken)
    elif name == "ScorerBinding":
        _refuses(api, synthetic, plan=replace(synthetic.plan, scorer=broken))
    elif name == "PreparationExclusion":
        _refuses(api, synthetic, plan=replace(synthetic.plan, exclusions=(broken,)))
    else:
        field = "blobs" if name == "EvidenceBlob" else "samples"
        _refuses(api, synthetic, candidate=replace(synthetic.candidate, **{field: (broken,)}))


def test_other_builtin_subclasses_and_callable_never_admitted(api, synthetic):
    class Integer(int):
        pass

    class Number(float):
        pass

    class Raw(bytes):
        pass

    _refuses(api, synthetic, plan=replace(synthetic.plan, g=Integer(4)))
    _refuses(api, synthetic, plan=replace(synthetic.plan, dead_ceiling=Number(0.6)))
    _refuses(api, synthetic, candidate=replace(synthetic.candidate, blobs=(
        replace(synthetic.candidate.blobs[0], payload=Raw(b"x")),
    )))
    touched = []

    def callback():
        touched.append(True)
        raise AssertionError("caller callback executed")

    _refuses(api, synthetic, plan=replace(synthetic.plan, plan_id=callback))
    assert touched == []


def test_late_invalid_sample_precedes_every_blob_hash(api, synthetic, monkeypatch):
    touched = []
    last = replace(synthetic.candidate.samples[-1], score=0.5)
    candidate = replace(synthetic.candidate, samples=synthetic.candidate.samples[:-1] + (last,))

    def forbidden(*args):
        touched.append(True)
        raise AssertionError("hash before complete scalar validation")

    monkeypatch.setattr(api.hashlib, "sha256", forbidden)
    monkeypatch.setattr(api, "_unique", forbidden)
    _refuses(api, synthetic, candidate=candidate)
    assert touched == []


@pytest.mark.parametrize("field,value", [
    ("g", 1), ("g", 4.0), ("dead_ceiling", 0), ("dead_ceiling", 1),
    ("plan_id", ""),
])
def test_scalar_endpoints_and_nonempty_identifiers(api, synthetic, field, value):
    _refuses(api, synthetic, plan=replace(synthetic.plan, **{field: value}))
