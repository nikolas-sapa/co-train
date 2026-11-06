"""Source-only accounting tests. Execution, including canary, is parent-owned."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from bench.paired_bird import (
    Comparison, Disclosure, Metric, PairedBirdResult, TaskOutcome,
)
from bench.prepare import DrawExclusion
from bench.seed_accounting import SeedAccountingError, account_three_seeds
from ptc.paired import paired


def _result():
    """Caller-constructed records, not admitted runs or measurement receipts."""
    scores_a = {"fixture-a": 1.0, "fixture-b": 0.0}
    scores_b = {"fixture-a": 0.0, "fixture-b": 0.0}
    estimate = paired(scores_a, scores_b)
    comparison = Comparison(**{field.name: estimate[field.name]
                               for field in fields(Comparison)})

    def outcomes(arm, scores):
        return tuple(TaskOutcome(
            "fixture-plan", arm, task, True, True,
            "match" if score else "mismatch",
            (Metric("execution_accuracy", score),), "memory:fixture")
            for task, score in scores.items())

    disclosure = Disclosure(
        3, 2, 1, 2, 2,
        (DrawExclusion("fixture-excluded", "gold_error",
                       "gold_execution_rejection"),),
        (), (2, 1), (2, 1), "fixture, not a measured trial")
    return PairedBirdResult(
        "complete", comparison, outcomes("bash", scores_a),
        outcomes("ptc", scores_b), (), disclosure, True, False)


def _submissions():
    return [(7, _result()), (11, _result()), (13, _result())]


def _assert_no_authority(report):
    for name in (
        "measurement_accepted", "scientific_accepted",
        "completed_training_accepted", "backend_accepted", "runtime_accepted",
        "rng_provenance_verified", "checkpoint_provenance_verified",
    ):
        assert getattr(report, name) is False, name


def test_exact_three_distinct_labels():
    submitted = _submissions()
    report = account_three_seeds([13, 7, 11], submitted)
    assert tuple(seed.seed for seed in report.seeds) == (13, 7, 11)
    assert len(report.seeds) == report.present_count == report.complete_count == 3
    assert report.missing_count == report.void_count == 0
    assert report.structural_three_seed_complete is True
    for seed, index in zip(report.seeds, (2, 0, 1), strict=True):
        assert seed.present is True
        assert seed.declared_status == seed.structural_status == "complete"
        assert seed.comparison is submitted[index][1].comparison
        assert seed.fixture_declared is True
        assert seed.measurement_declared is False


class _IntSubclass(int):
    pass


@pytest.mark.parametrize("expected", [
    (7, 11), (7, 11, 13, 17), (7, 7, 13), (True, 11, 13),
    (7.0, 11, 13), ("7", 11, 13), (_IntSubclass(7), 11, 13),
])
def test_expected_labels_refuse(expected):
    with pytest.raises(SeedAccountingError):
        account_three_seeds(expected, [])


def test_missing_stays_missing_without_aggregate():
    submitted = _submissions()[:2]
    report = account_three_seeds((7, 11, 13), submitted)
    assert len(report.seeds) == 3
    assert report.present_count == report.complete_count == 2
    assert report.missing_count == 1
    assert report.structural_three_seed_complete is False
    missing = report.seeds[2]
    assert missing.present is False
    assert missing.structural_status == "missing"
    assert missing.declared_status is missing.comparison is None
    assert missing.fixture_declared is missing.measurement_declared is None
    assert not hasattr(report, "comparison")
    assert not hasattr(report, "pooled_effect")


def test_empty_submission():
    report = account_three_seeds((7, 11, 13), [])
    assert report.missing_count == len(report.seeds) == 3
    assert report.present_count == report.complete_count == report.void_count == 0
    assert report.structural_three_seed_complete is False
    assert all(seed.structural_status == "missing" for seed in report.seeds)


def _void_report():
    submitted = _submissions()
    submitted[2] = (13, replace(
        submitted[2][1], status="void", comparison=None,
        diagnostics=("ptc:eligible_coverage_mismatch",)))
    return account_three_seeds((7, 11, 13), submitted)


def _assert_void_blocks_completeness(report):
    assert report.present_count == 3
    assert report.complete_count == 2
    assert report.void_count == 1
    assert report.structural_three_seed_complete is False, "VOID_COUNTED_AS_COMPLETE"


def test_one_void_blocks_completeness():
    report = _void_report()
    _assert_void_blocks_completeness(report)
    assert report.seeds[2].present is True
    assert report.seeds[2].declared_status == "void"
    assert report.seeds[2].structural_status == "void"
    assert report.seeds[2].comparison is None


@pytest.mark.parametrize("label", [7, 17, True, 7.0, "private-sentinel"])
def test_submission_labels_refuse(label):
    submitted = _submissions()
    submitted.append((label, _result()))
    with pytest.raises(SeedAccountingError):
        account_three_seeds((7, 11, 13), submitted)


def test_result_alias_refused():
    result = _result()
    with pytest.raises(SeedAccountingError):
        account_three_seeds((7, 11, 13), [(7, result), (11, result)])
    other = replace(result)
    assert other == result and other is not result
    report = account_three_seeds((7, 11, 13), [(7, result), (11, other)])
    assert report.present_count == 2


def test_complete_fixtures_never_grant_acceptance():
    report = account_three_seeds((7, 11, 13), _submissions())
    assert report.complete_count == 3
    assert report.structural_three_seed_complete is True
    _assert_no_authority(report)


def test_declarations_do_not_prove_provenance():
    labels = (-7, 0, 10 ** 1000)
    submitted = [(label, replace(_result(), fixture=False, measurement=True))
                 for label in labels]
    report = account_three_seeds(labels, submitted)
    assert tuple(seed.seed for seed in report.seeds) == labels
    assert report.complete_count == 3
    assert all(seed.measurement_declared is True for seed in report.seeds)
    assert all(seed.fixture_declared is False for seed in report.seeds)
    _assert_no_authority(report)


def test_original_records_and_containers_unchanged():
    submitted = _submissions()
    expected = [13, 7, 11]
    before = tuple(submitted)
    values_before = deepcopy(submitted)
    snapshots = [tuple(getattr(result, field.name)
                       for field in fields(PairedBirdResult))
                 for _, result in submitted]
    report = account_three_seeds(expected, submitted)
    assert expected == [13, 7, 11]
    assert tuple(submitted) == before
    assert submitted == values_before
    for index, (_, result) in enumerate(submitted):
        assert result is before[index][1]
        for field, original in zip(fields(PairedBirdResult), snapshots[index],
                                   strict=True):
            assert getattr(result, field.name) is original
        assert result.disclosure.exclusions[0].id == "fixture-excluded"
        assert result.arm_a[0].metrics == (Metric("execution_accuracy", 1.0),)
        assert result.measurement is False
    assert report.seeds[0].comparison is submitted[2][1].comparison


def test_reports_frozen():
    expected = [7, 11, 13]
    submitted = _submissions()
    report = account_three_seeds(expected, submitted)
    for record, field, value in (
        (report, "seeds", ()),
        (report.seeds[0], "structural_status", "complete"),
        (report.seeds[0].comparison, "delta", 99.0),
        (report, "measurement_accepted", True),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, value)
    expected.reverse()
    submitted.clear()
    assert tuple(seed.seed for seed in report.seeds) == (7, 11, 13)
    assert report.present_count == 3


@pytest.mark.parametrize("fault", [
    "expected-none", "expected-string", "results-none", "results-mapping",
    "pair-short", "pair-string", "result-object", "status", "complete-none",
    "void-comparison", "fixture", "measurement", "comparison-ci",
    "comparison-value", "comparison-count",
])
def test_malformed_inputs_refuse_generically(fault):
    expected = (7, 11, 13)
    result = _result()
    submitted = [(7, result)]
    if fault == "expected-none":
        expected = None
    elif fault == "expected-string":
        expected = "private-sentinel"
    elif fault == "results-none":
        submitted = None
    elif fault == "results-mapping":
        submitted = {7: result}
    elif fault == "pair-short":
        submitted = [(7,)]
    elif fault == "pair-string":
        submitted = ["private-sentinel"]
    elif fault == "result-object":
        submitted = [(7, object())]
    else:
        changes = {
            "status": {"status": "private-sentinel"},
            "complete-none": {"comparison": None},
            "void-comparison": {"status": "void"},
            "fixture": {"fixture": 1},
            "measurement": {"measurement": "private-sentinel"},
            "comparison-ci": {"comparison": replace(
                result.comparison, ci=[0.0, 1.0])},
            "comparison-value": {"comparison": replace(
                result.comparison, delta=["private-sentinel"])},
            "comparison-count": {"comparison": replace(
                result.comparison, n=True)},
        }
        submitted = [(7, replace(result, **changes[fault]))]
    with pytest.raises(SeedAccountingError) as caught:
        account_three_seeds(expected, submitted)
    assert len(str(caught.value)) <= 100
    assert "private-sentinel" not in str(caught.value)


def test_wrong_guard_canary_reaches_completeness_assertion():
    report = _void_report()
    _assert_void_blocks_completeness(report)

    class PresenceOnlyWrongGuard:
        present_count = report.present_count
        complete_count = report.complete_count
        void_count = report.void_count
        structural_three_seed_complete = report.present_count == 3

    with pytest.raises(AssertionError) as caught:
        _assert_void_blocks_completeness(PresenceOnlyWrongGuard())
    assert str(caught.value).partition("\n")[0] == "VOID_COUNTED_AS_COMPLETE"


@pytest.mark.parametrize("status", ["complete", "void"])
@pytest.mark.parametrize("field", ["status", "comparison", "fixture", "measurement"])
def test_missing_required_result_fields_refuse_generically(status, field):
    result = _result()
    if status == "void":
        result = replace(result, status="void", comparison=None)
    assert type(result) is PairedBirdResult
    assert hasattr(result, field)
    object.__delattr__(result, field)
    assert field not in vars(result)
    assert not hasattr(result, field)
    with pytest.raises(SeedAccountingError) as caught:
        account_three_seeds((7, 11, 13), [(7, result)])
    assert type(caught.value) is SeedAccountingError
    assert str(caught.value) == "result fields are missing"
    assert len(str(caught.value)) <= 100
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize("field", [
    "n", "mean_a", "mean_b", "delta", "ci", "a_only", "b_only", "ties", "p",
])
def test_missing_required_comparison_fields_refuse_generically(field):
    result = _result()
    comparison = result.comparison
    assert type(comparison) is Comparison
    assert hasattr(comparison, field)
    object.__delattr__(comparison, field)
    assert field not in vars(comparison)
    assert not hasattr(comparison, field)
    with pytest.raises(SeedAccountingError) as caught:
        account_three_seeds((7, 11, 13), [(7, result)])
    assert type(caught.value) is SeedAccountingError
    assert str(caught.value) == "comparison fields are missing"
    assert len(str(caught.value)) <= 100
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
