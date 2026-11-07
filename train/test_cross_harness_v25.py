"""Synthetic declaration controls only. Runtime verification is parent-owned."""

from dataclasses import fields, replace
import hashlib
import importlib

import pytest


def _api(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        pytest.fail(f"required existing API absent: {name}", pytrace=False)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _frontier():
    api = _api("train.frontier_bindings")
    tasks = tuple(api.TaskBinding(name, _sha(name.encode()), _sha(b"database"))
                  for name in ("original-b", "original-a"))
    plan = api.MeasurementPlan(
        plan_id="declared-plan", execution_id="declared-execution",
        policy_revision="a" * 40, checkpoint_sha256=_sha(b"checkpoint"),
        adapter_sha256=None, runtime_id="declared-runtime",
        provider_id="declared-provider", route_id="declared-route",
        generation_sha256=_sha(b"generation"), prompt_sha256=_sha(b"prompt"),
        template_sha256=_sha(b"template"), tool_sha256=_sha(b"tool"),
        instrument_sha256=_sha(b"instrument"), source_sha256=_sha(b"source"),
        draw_sha256=_sha(b"draw"), supplement_sha256=_sha(b"supplement"),
        tasks=tasks, eligible_ids=tuple(task.task_id for task in tasks),
        exclusions=(), g=2, dead_ceiling=.6,
        scorer=api.ScorerBinding(_sha(b"extract"), _sha(b"scorer"), "set", 30, 100),
        resource_limits_id="declared-limits", grant_reference="not-approval",
    )
    expected = [api.ExpectedEvidence(
        "checkpoint", "checkpoint", plan.plan_id, plan.execution_id,
        None, None, None, None, None, len(b"checkpoint"), _sha(b"checkpoint"),
    )]
    blobs = [api.EvidenceBlob("checkpoint", b"checkpoint")]
    samples = []
    for task in tasks:
        for slot in range(2):
            attempt = f"{task.task_id}-{slot}"
            generation, scoring = attempt + "-generation", attempt + "-scoring"
            prediction = _sha(attempt.encode())
            for evidence_id, purpose, reference in (
                (generation, "generation", None), (scoring, "scoring", generation),
            ):
                payload = evidence_id.encode()
                expected.append(api.ExpectedEvidence(
                    evidence_id, purpose, plan.plan_id, plan.execution_id,
                    task.task_id, slot, attempt, reference, prediction,
                    len(payload), _sha(payload),
                ))
                blobs.append(api.EvidenceBlob(evidence_id, payload))
            samples.append(api.SampleRecord(
                task.task_id, slot, attempt, "scored", slot,
                generation, scoring, prediction,
            ))
    limits = api.BindingLimits(2, 4, 9, 9, 1024, 65536, 256, 10)
    return api, plan, tuple(expected), api.EvidenceBatch(
        plan, tuple(blobs), tuple(samples),
    ), limits


def _validate(fixture, candidate=None):
    api, plan, expected, batch, limits = fixture
    return api.validate_frontier_bindings(
        plan, expected, batch if candidate is None else candidate, limits=limits,
    )


def _no_authority(report):
    assert report.provenance == "unverified"
    assert report.attested_facts == ()
    assert report.genuine_measurement_accepted is False
    assert report.training_authorized is False


@pytest.mark.parametrize("field", (
    "checkpoint_sha256", "policy_revision", "draw_sha256",
    "tasks", "scorer", "source_sha256",
))
def test_frontier_one_field_plan_mutation(field):
    fixture = _frontier()
    _, plan, _, batch, _ = fixture
    control = _validate(fixture)
    assert control.all_samples_validly_scored
    assert control.valid_declared_scores == 4
    _no_authority(control)
    if field == "tasks":
        value = (replace(plan.tasks[0], task_sha256=_sha(b"other-task")), plan.tasks[1])
    elif field == "scorer":
        value = replace(plan.scorer, scorer_source_sha256=_sha(b"other-scorer"))
    elif field == "policy_revision":
        value = "b" * 40
    else:
        value = _sha(b"other-declaration")
    candidate = replace(batch, plan=replace(plan, **{field: value}))
    report = _validate(fixture, candidate)
    assert report.diagnostics == (("plan_mismatch", None, None),)
    assert report.valid_declared_scores == 0
    assert report.schedule_complete
    assert not report.bindings_consistent
    assert not report.all_samples_validly_scored
    _no_authority(report)


def test_frontier_partial_schedule_keeps_original_order():
    fixture = _frontier()
    batch = fixture[3]
    candidate = replace(batch, samples=tuple(reversed(batch.samples[:-1])))
    report = _validate(fixture, candidate)
    assert report.scheduled_slots == 4
    assert report.observed_slots == report.valid_declared_scores == 3
    assert [(slot.task_ordinal, slot.slot_index) for slot in report.slots] == [
        (0, 0), (0, 1), (1, 0), (1, 1),
    ]
    assert dict(report.disposition_counts)["missing"] == 1
    assert report.slots[-1].disposition == "missing"
    assert not report.slots[-1].validly_scored
    assert not report.schedule_complete
    assert not report.all_samples_validly_scored
    _no_authority(report)


def test_frontier_duplicate_attempt_refuses_before_selection():
    fixture = _frontier()
    api, _, _, batch, _ = fixture
    assert _validate(fixture).valid_declared_scores == 4
    samples = list(batch.samples)
    samples[1] = replace(samples[1], attempt_id=samples[0].attempt_id)
    with pytest.raises(api.BindingError, match="^invalid frontier bindings$"):
        _validate(fixture, replace(batch, samples=tuple(samples)))


def test_frontier_changed_bytes_do_not_autorepin():
    fixture = _frontier()
    _, _, expected, batch, _ = fixture
    assert _validate(fixture).valid_declared_scores == 4
    original_pin = expected[1].sha256
    blobs = list(batch.blobs)
    blobs[1] = replace(blobs[1], payload=b"changed-generation")
    report = _validate(fixture, replace(batch, blobs=tuple(blobs)))
    assert report.diagnostics == (("evidence_bytes", None, None),)
    assert report.valid_declared_scores == 3
    assert not report.all_samples_validly_scored
    assert expected[1].sha256 == original_pin
    assert expected[1].sha256 != _sha(blobs[1].payload)
    _no_authority(report)


def _episode(task_id, backend):
    api = _api("train.sql_episodes")
    score = _api("bench.score")
    return api.SqlEpisode(
        schema_version=1, origin="scripted",
        ids=api.EpisodeIds("synthetic-corpus", "synthetic-split", "synthetic-run",
                           task_id, "synthetic-policy", "synthetic-revision"),
        arm="ptc", task_id=task_id, task_fingerprint=_sha(task_id.encode()),
        db_sha256=_sha(b"database"), schema="synthetic-schema",
        prompt="synthetic-prompt", backend=backend,
        instrument=api.InstrumentSettings(
            action_cap=8, action_max_rows=200, scorer_max_rows=500000,
            compare="set", scorer_timeout_s=30., program_timeout_s=5.,
            wrapper_timeout_s=30., python_version="declared-python",
            sqlite_version="declared-sqlite", source_paths=("ptc/sql_arms.py",),
            source_sha256=_sha(b"source"),
        ),
        steps=(), final_answer="", extracted_sql="", terminal_label="scripted_final",
        result=score.ExResult(0., "pred_empty", True),
    )


def test_swap_mixed_matching_cohorts_remain_declarations_only():
    api = _api("train.harness_swap_accounting")
    left = [_episode("original-b", "left"), _episode("original-a", "left")]
    left[1] = replace(
        left[1], ids=replace(left[1].ids, corpus_id="other-corpus",
                             policy_revision="other-policy"),
        instrument=replace(left[1].instrument, source_sha256=_sha(b"other-source")),
    )
    right = [replace(episode, backend="right") for episode in reversed(left)]
    report = api.project_harness_swap(("original-b", "original-a"), left, right)
    assert report.paired_count == 2
    assert report.invariant_mismatch_count == 0
    assert report.recorded_declarations_compatible
    names = {field.name for field in fields(report)}
    assert names.isdisjoint({
        "learning_improvement", "savings", "native_qualified", "training_authorized",
        "checkpoint_sha256", "seed", "statistics", "score",
    })
    right[0] = replace(right[0], ids=replace(right[0].ids, policy_revision="mismatch"))
    changed = api.project_harness_swap(("original-b", "original-a"), left, right)
    assert dict(changed.field_mismatch_counts)["policy_revision"] == 1
    assert changed.invariant_mismatch_count == 1
    assert not changed.recorded_declarations_compatible


def _capture_paths(tmp_path):
    api = _api("train.sql_capture")
    score = _api("bench.score")
    paths = ({}, {})
    for arm, mapping in enumerate(paths):
        for task_id in ("original-a", "original-b"):
            episode = _episode(task_id, "same-declared-backend")
            capture = api.SqlCapture(
                schema_version=1, origin="incremental_execution",
                ids=replace(episode.ids, run_id=f"declared-arm-{arm}"),
                arm=episode.arm, task_id=task_id,
                task_fingerprint=episode.task_fingerprint,
                db_sha256=episode.db_sha256, schema=episode.schema,
                prompt=episode.prompt, backend=episode.backend,
                instrument=episode.instrument, steps=(), refusals=(),
                final_answer="SELECT 1", extracted_sql="SELECT 1",
                terminal_label="final_submitted",
                result=score.ExResult(0., "mismatch", True),
            )
            path = tmp_path / f"{arm}-{task_id}.json"
            path.write_bytes(api.encode_capture(capture))
            mapping[task_id] = path
    return paths


def test_capture_missing_baseline_is_not_observed_zero(tmp_path):
    api = _api("train.sql_capture_comparison")
    baseline, treatment = _capture_paths(tmp_path)
    planned = ("original-b", "original-a")
    control = api.compare_capture_files(planned, baseline, treatment)
    assert control.admissible
    assert control.statistics.n == 2
    assert control.statistics.delta == 0
    baseline.pop("original-b")
    report = api.compare_capture_files(planned, baseline, treatment)
    assert report.denominator == 2
    assert tuple(row.case_id for row in report.cases) == planned
    assert report.cases[0].baseline.score is None
    assert report.cases[0].baseline.state == "missing_capture"
    assert report.cases[1].baseline.score == 0
    assert report.cases[1].baseline.state == "observed_failure"
    assert report.cases[0].change == "unavailable"
    assert not report.complete and not report.admissible
    assert report.statistics is None
    assert report.improvements == report.regressions == ()


def test_capture_scorer_mismatch_refuses_quality_delta(tmp_path):
    api = _api("train.sql_capture_comparison")
    captures = _api("train.sql_capture")
    baseline, treatment = _capture_paths(tmp_path)
    planned = ("original-b", "original-a")
    assert api.compare_capture_files(planned, baseline, treatment).admissible
    path = treatment["original-b"]
    capture = captures.decode_capture(path.read_bytes())
    changed = replace(
        capture, instrument=replace(capture.instrument, compare="multiset"),
    )
    path.write_bytes(captures.encode_capture(changed))
    report = api.compare_capture_files(planned, baseline, treatment)
    assert report.complete and not report.admissible
    assert report.cases[0].refusal_reasons == ("instrument_mismatch",)
    assert report.cases[0].change == "unavailable"
    assert report.statistics is None


def _group(api, task_id, scores):
    return [
        api.SampleEvidence(
            sample_id=f"{task_id}-{index}", group_id=task_id, task_id=task_id,
            task_fingerprint=_sha(task_id.encode()), arm="ptc", phase="screen",
            corpus_id="synthetic-corpus", split_id="synthetic-split",
            run_id="synthetic-run", policy_revision="synthetic-policy",
            scorer_id="synthetic-scorer", score=score,
            status="match" if score else "mismatch", valid=True,
        )
        for index, score in enumerate(scores)
    ]


def _summary(api, samples):
    return api.summarize_groups(samples, group_g=2, evaluation_task_ids=())


def test_calibration_partial_group_is_not_pooled():
    api = _api("bench.frontier.calibration")
    first = _group(api, "original-b", (0, 1))
    second = _group(api, "original-a", (1, 0))
    assert _summary(api, first + second)["usable_sample_count"] == 4
    with pytest.raises(ValueError, match="must have exactly 2 members"):
        _summary(api, first + second[:1])


def test_calibration_mixed_policy_group_refuses():
    api = _api("bench.frontier.calibration")
    samples = _group(api, "original-b", (0, 1))
    assert _summary(api, samples)["usable_group_count"] == 1
    samples[1] = replace(samples[1], policy_revision="other-policy")
    with pytest.raises(ValueError, match="mixed identity/configuration"):
        _summary(api, samples)


def test_calibration_duplicate_across_phases_refuses():
    api = _api("bench.frontier.calibration")
    samples = _group(api, "original-b", (0, 1))
    fresh = [
        replace(sample, sample_id=sample.sample_id + "-fresh",
                group_id="confirmation", phase="confirmation")
        for sample in samples
    ]
    assert _summary(api, samples + fresh)["usable_group_count"] == 2
    fresh[0] = replace(fresh[0], sample_id=samples[0].sample_id)
    with pytest.raises(ValueError, match="duplicate sample_id"):
        _summary(api, samples + fresh)


def test_calibration_invalid_group_preserves_null_and_task_strata():
    api = _api("bench.frontier.calibration")
    first = _group(api, "original-b", (0, 1))
    second = _group(api, "original-a", (1, 0))
    control = _summary(api, first + second)
    assert control["usable_sample_count"] == 4
    second[0] = replace(second[0], score=None, status="gold_error", valid=False)
    report = _summary(api, first + second)
    assert report["all_sample_count"] == 4
    assert report["usable_sample_count"] == report["invalid_sample_count"] == 2
    assert report["usable_group_count"] == report["invalid_group_count"] == 1
    assert report["valid_successes"] == 1
    assert len(report["strata"]) == 2
    assert [group["task_id"] for group in report["groups"]] == [
        "original-b", "original-a",
    ]
    assert report["groups"][1]["scores"] == [None, 0]
    assert report["groups"][1]["dead"] is None
    assert report["strata"][1]["empirical_dead_group_fraction"] is None
    assert report["strata"][1]["plugin_dead_estimate"] is None
    assert set(report).isdisjoint({
        "empirical_dead_group_fraction", "plugin_dead_estimate",
        "learning_improvement", "savings", "native_qualified", "training_authorized",
    })
