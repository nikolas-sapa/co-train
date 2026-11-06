"""Source-authored offline projection contracts. Execution is parent-owned."""

from __future__ import annotations

import builtins
import dataclasses
import io
import sqlite3
from pathlib import Path

import pytest

from bench.score import ExResult
from ptc import runtime, sql_arms
from train import sql_episodes
from train.harness_swap_accounting import project_harness_swap
from train.sql_episodes import EpisodeIds, InstrumentSettings, SqlEpisode
from train.sql_reporting import ReportingConfig, snapshot_from_dict


PLANNED = ("task-0", "task-1", "task-2", "task-3", "task-4", "task-5", "task-6")


def _episode(task_id, backend):
    return SqlEpisode(
        schema_version=1, origin="scripted",
        ids=EpisodeIds("declared-corpus", "declared-split", "declared-run",
                       task_id, "declared-policy", "declared-revision"),
        arm="ptc", task_id=task_id, task_fingerprint="a" * 64,
        db_sha256="b" * 64, schema="declared schema", prompt="declared prompt",
        backend=backend,
        instrument=InstrumentSettings(
            action_cap=8, action_max_rows=200, scorer_max_rows=500_000,
            compare="set", scorer_timeout_s=30.0, program_timeout_s=5.0,
            wrapper_timeout_s=30.0, python_version="declared-python",
            sqlite_version="declared-sqlite", source_paths=("ptc/sql_arms.py",),
            source_sha256="c" * 64,
        ),
        steps=(), final_answer="", extracted_sql="", terminal_label="scripted_final",
        result=ExResult(0.0, "pred_empty", True),
    )


def _collections():
    return ([_episode(task_id, "declared-left") for task_id in PLANNED],
            [_episode(task_id, "declared-right") for task_id in PLANNED])


def _counts(projection):
    return dict(projection.field_mismatch_counts)


def test_seven_planned_ids_exact_coverage():
    left, right = _collections()
    projection = project_harness_swap(PLANNED, left, right[::-1])
    assert projection.planned_count == projection.planned_unique_count == 7
    assert projection.left_count == projection.right_count == 7
    assert projection.paired_count == projection.overlap_count == 7
    assert projection.coverage_complete
    assert projection.invariant_mismatch_count == 0
    assert sum(_counts(projection).values()) == 0
    for name in ("left_missing_count", "right_missing_count", "missing_both_count",
                 "left_duplicate_count", "right_duplicate_count",
                 "planned_duplicate_count", "left_unexpected_count",
                 "right_unexpected_count"):
        assert getattr(projection, name) == 0


@pytest.mark.parametrize("side", ("left", "right", "both"))
def test_missing_either_or_both(side):
    left, right = _collections()
    if side in ("left", "both"):
        left.pop()
    if side in ("right", "both"):
        right.pop()
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.left_missing_count == int(side in ("left", "both"))
    assert projection.right_missing_count == int(side in ("right", "both"))
    assert projection.missing_both_count == int(side == "both")
    assert projection.paired_count == 6
    assert not projection.coverage_complete
    assert not projection.recorded_declarations_compatible


@pytest.mark.parametrize("side", ("left", "right"))
@pytest.mark.parametrize("change", ("duplicate", "extra", "substitute"))
def test_duplicates_extras_and_substitution(side, change):
    left, right = _collections()
    target = left if side == "left" else right
    if change == "duplicate":
        target.append(target[0])
    elif change == "extra":
        target.append(dataclasses.replace(target[0], task_id="unexpected"))
    else:
        target[0] = dataclasses.replace(target[0], task_id="substituted")
    projection = project_harness_swap(PLANNED, left, right)
    assert not projection.coverage_complete
    assert not projection.recorded_declarations_compatible
    assert getattr(projection, side + "_duplicate_count") == int(change == "duplicate")
    assert getattr(projection, side + "_unexpected_count") == int(change != "duplicate")
    assert getattr(projection, side + "_missing_count") == int(change == "substitute")
    assert projection.paired_count == (7 if change == "extra" else 6)


def test_duplicate_plan_refuses_completeness():
    left, right = _collections()
    projection = project_harness_swap(PLANNED + (PLANNED[0],), left, right)
    assert projection.planned_count == 8
    assert projection.planned_unique_count == 7
    assert projection.planned_duplicate_count == 1
    assert not projection.coverage_complete


@pytest.mark.parametrize("field,value", (
    ("policy_id", "different-policy"), ("policy_revision", "different-revision"),
    ("corpus_id", "different-corpus"), ("split_id", "different-split"),
    ("task_fingerprint", "d" * 64), ("db_sha256", "e" * 64),
    ("schema", "different-schema"), ("prompt", "different-prompt"), ("arm", "bash"),
))
def test_each_invariant_mutation(field, value):
    left, right = _collections()
    if field in ("policy_id", "policy_revision", "corpus_id", "split_id"):
        right[0] = dataclasses.replace(
            right[0], ids=dataclasses.replace(right[0].ids, **{field: value}),
        )
    else:
        right[0] = dataclasses.replace(right[0], **{field: value})
    projection = project_harness_swap(PLANNED, left, right)
    assert _counts(projection)[field] == 1
    assert projection.invariant_mismatch_count == 1
    assert projection.coverage_complete
    assert not projection.recorded_declarations_compatible


@pytest.mark.parametrize("field,value", (
    ("action_cap", 9), ("action_max_rows", 201), ("scorer_max_rows", 500_001),
    ("compare", "multiset"), ("scorer_timeout_s", 31.0),
    ("program_timeout_s", 6.0), ("wrapper_timeout_s", 31.0),
    ("python_version", "other-python"), ("sqlite_version", "other-sqlite"),
    ("source_paths", ("bench/score.py",)), ("source_sha256", "d" * 64),
))
def test_each_instrument_setting_mutation(field, value):
    left, right = _collections()
    right[0] = dataclasses.replace(
        right[0], instrument=dataclasses.replace(right[0].instrument, **{field: value}),
    )
    projection = project_harness_swap(PLANNED, left, right)
    assert _counts(projection)["instrument"] == 1
    assert projection.invariant_mismatch_count == 1
    assert not projection.recorded_declarations_compatible


def test_reporting_configuration_and_version_mutation():
    snapshot = snapshot_from_dict({
        "version": 1, "total_events": 0,
        "arms": {arm: {"dropped": 0, "dropped_saturated": False,
                       "events": [], "reports": 0} for arm in ("bash", "ptc")},
    })
    left, right = _collections()
    right[0] = dataclasses.replace(
        right[0], schema_version=2, reporting=ReportingConfig(), telemetry=snapshot,
    )
    projection = project_harness_swap(PLANNED, left, right)
    assert _counts(projection)["schema_version"] == 1
    assert _counts(projection)["reporting"] == 1
    left[0] = dataclasses.replace(
        left[0], schema_version=2, reporting=ReportingConfig(), telemetry=snapshot,
    )
    right[0] = dataclasses.replace(
        right[0], reporting=ReportingConfig(shortcut_ids=("declared_shortcut",)),
    )
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.invariant_mismatch_count == 1
    assert _counts(projection)["reporting"] == 1


def test_same_backend_is_not_swap():
    left, right = _collections()
    right = [dataclasses.replace(episode, backend="declared-left") for episode in right]
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.same_backend_pair_count == 7
    assert projection.distinct_backend_pair_count == 0
    assert not projection.recorded_declarations_compatible


def test_backend_only_difference_and_outputs_ignored():
    left, right = _collections()
    right = [dataclasses.replace(
        episode, ids=dataclasses.replace(episode.ids, run_id="other-run",
                                         episode_id="other-" + episode.task_id),
        final_answer="unexecuted alternative", extracted_sql="unexecuted SQL",
        steps=(sql_episodes.ActionObservation("unexecuted", "unobserved"),),
        result=ExResult(0.0, "pred_error", True),
    ) for episode in right]
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.invariant_mismatch_count == 0
    assert projection.distinct_backend_pair_count == 7
    assert projection.recorded_declarations_compatible
    assert projection.unrepresented_invariants == (
        "Budget.max_turns", "Budget.max_retries", "Budget.retry_on",
        "Budget.rollout_timeout",
    )
    for name in ("backend_qualified", "measured_swap", "checkpoint_proven",
                 "training_accepted", "runtime_accepted"):
        assert not hasattr(projection, name)


def test_mixed_backends_and_empty_plan_refuse():
    left, right = _collections()
    right[0] = dataclasses.replace(right[0], backend="third-declared-backend")
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.right_backend_count == 2
    assert not projection.recorded_declarations_compatible
    empty = project_harness_swap((), (), ())
    assert empty.planned_count == 0
    assert not empty.coverage_complete
    assert not empty.recorded_declarations_compatible


def test_original_records_and_frozen_projection():
    left, right = _collections()
    before = dataclasses.asdict(left[0]), tuple(left), tuple(right)
    projection = project_harness_swap(PLANNED, left, right)
    assert before == (dataclasses.asdict(left[0]), tuple(left), tuple(right))
    assert left[0] is before[1][0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.paired_count = 0


def test_field_counts_are_complete_and_bounded():
    left, right = _collections()
    right = [dataclasses.replace(episode, prompt="sensitive-prompt-" * 100)
             for episode in right]
    projection = project_harness_swap(PLANNED, left, right)
    assert projection.invariant_mismatch_count == 7
    assert _counts(projection)["prompt"] == 7
    assert "sensitive-prompt" not in repr(projection)
    assert len(projection.field_mismatch_counts) == 13


def test_no_runtime_action_or_file_callbacks(monkeypatch):
    left, right = _collections()
    calls = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in (
            "torch", "transformers", "trl", "unsloth", "vllm", "verifiers",
            "datasets", "huggingface_hub", "httpx", "pydantic",
        ) or name == "ptc.harness":
            calls.append(1)
            raise AssertionError("projection imported a runtime/framework")
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("projection dispatched a forbidden callback")

    for module, names in (
        (sql_episodes, ("record_scripted", "rescore_sql", "reexecute_sql",
                        "execution_accuracy")),
        (sql_arms, ("build_sql_arms", "run_ptc_program", "run_bash_sql",
                    "schema_text")),
        (runtime, ("run",)),
        (sqlite3, ("connect",)),
        (builtins, ("open",)),
        (io, ("open",)),
        (Path, ("open", "read_bytes", "read_text", "write_bytes", "write_text")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(sql_arms.ArmPair, "run", forbidden)
    for name in ("catalog", "run_ptc", "run_bash", "model_tools", "arm_ids"):
        monkeypatch.setattr(type(sql_arms.PTC_V1), name, forbidden)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert project_harness_swap(PLANNED, left, right).paired_count == 7
    assert not project_harness_swap(PLANNED, left[:-1], right[:-1]).coverage_complete
    assert len(calls) == 0


@pytest.mark.parametrize("case", (
    "plan-container", "episode-container", "plan-id", "episode-type",
    "forged-origin", "forged-prompt", "forged-missing-field",
))
def test_malformed_input_is_generic(case):
    left, right = _collections()
    plan = PLANNED
    if case == "plan-container":
        plan = "sensitive-marker"
    elif case == "episode-container":
        left = {"sensitive-marker": left[0]}
    elif case == "plan-id":
        plan = (object(),)
    elif case == "episode-type":
        left = [object()]
    elif case == "forged-missing-field":
        left = [object.__new__(SqlEpisode)]
    else:
        bad = dataclasses.replace(left[0])
        field = "origin" if case == "forged-origin" else "prompt"
        value = "sensitive-marker" if field == "origin" else ["sensitive-marker"]
        object.__setattr__(bad, field, value)
        left = [bad]
    with pytest.raises(ValueError) as caught:
        project_harness_swap(plan, left, right)
    assert str(caught.value) == "invalid harness-swap declarations"
    assert caught.value.__suppress_context__
    assert "sensitive-marker" not in str(caught.value)


def _assert_incomplete(projection):
    assert not projection.coverage_complete, "scheduled missing-both must refuse completeness"


def test_missing_both_wrong_guard_canary():
    left, right = _collections()
    left.pop()
    right.pop()
    actual = project_harness_swap(PLANNED, left, right)
    assert actual.missing_both_count == 1
    _assert_incomplete(actual)

    def wrong_guard(first, second):
        observed_plan = tuple(episode.task_id for episode in first)
        return project_harness_swap(observed_plan, first, second)

    bypassed = wrong_guard(left, right)
    assert bypassed.paired_count == 6
    failures = 0
    with pytest.raises(AssertionError, match="scheduled missing-both must refuse completeness"):
        failures += 1
        _assert_incomplete(bypassed)
    assert failures == 1
