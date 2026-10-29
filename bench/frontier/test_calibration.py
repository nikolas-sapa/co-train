"""Offline calibration contracts, independent of SQL, probes and generation.

Output keys are intentionally public here. ``strata`` contains taskwise records;
each uses the same count keys as the aggregate. ``invalid_sample_count`` counts
all samples in unusable groups, not just the individually invalid members.
``status_counts`` still counts every original status, including those members.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import math
from collections import Counter

import pytest


def _api():
    """Missing implementation must be a collected RED test, not an import error."""
    try:
        return importlib.import_module("bench.frontier.calibration")
    except ModuleNotFoundError as exc:
        if exc.name != "bench.frontier.calibration":
            raise
        pytest.fail("bench.frontier.calibration implementation is absent", pytrace=False)


def _group(api, group_id, scores=(0, 1, 0, 1), **changes):
    fields = dict(
        task_id="task-a",
        task_fingerprint="fingerprint-a",
        arm="ptc",
        phase="screen",
        corpus_id="fixture",
        split_id="train",
        run_id="run-1",
        policy_revision="scripted-v1",
        scorer_id="execution-v1",
        status="ok",
        valid=True,
    )
    fields.update(changes)
    return [
        api.SampleEvidence(
            sample_id=f"{group_id}:{index}", group_id=group_id, score=score, **fields
        )
        for index, score in enumerate(scores)
    ]


def _summary(api, samples, *, group_g=4, evaluation_task_ids=()):
    return api.summarize_groups(
        samples, group_g=group_g, evaluation_task_ids=evaluation_task_ids
    )


def _only_stratum(result):
    assert len(result["strata"]) == 1
    return result["strata"][0]


def _counts(record, *, all_groups, usable_groups, invalid_groups,
            all_samples, usable_samples, invalid_samples, successes):
    assert record["all_group_count"] == all_groups
    assert record["usable_group_count"] == usable_groups
    assert record["invalid_group_count"] == invalid_groups
    assert record["all_sample_count"] == all_samples
    assert record["usable_sample_count"] == usable_samples
    assert record["invalid_sample_count"] == invalid_samples
    assert record["valid_successes"] == successes


def test_exact_screen_reference_numbers_and_declared_assumption():
    result = _api().exact_screen(0.10)
    assert result["p"] == 0.10
    assert result["screen_n"] == result["group_g"] == 4
    assert result["ceiling"] == 0.60
    assert result["true_dead_probability"] == pytest.approx(.6562, abs=1e-12, rel=0)
    assert result["acceptance_probability"] == pytest.approx(.3438, abs=1e-12, rel=0)
    assert result["conditional_plugin_dead_estimate"] == pytest.approx(
        .2927028795811518, abs=1e-12, rel=0
    )
    assumption = result["assumption"].lower()
    assert "bernoulli" in assumption
    assert "iid" in assumption or "i.i.d." in assumption
    assert "hypothetical" in assumption


@pytest.mark.parametrize(
    "screen_n,group_g,acceptance,conditional",
    [(2, 4, .18, .125), (4, 2, .0486, .5)],
)
def test_screen_count_and_future_group_size_are_distinct(
    screen_n, group_g, acceptance, conditional
):
    result = _api().exact_screen(.1, screen_n=screen_n, group_g=group_g)
    assert result["screen_n"] == screen_n
    assert result["group_g"] == group_g
    assert result["true_dead_probability"] == pytest.approx(.1**group_g + .9**group_g)
    assert result["acceptance_probability"] == pytest.approx(acceptance)
    assert result["conditional_plugin_dead_estimate"] == pytest.approx(conditional)


@pytest.mark.parametrize("p", [0, 1])
def test_probability_endpoints_have_no_conditional_estimate(p):
    result = _api().exact_screen(p)
    assert result["true_dead_probability"] == 1
    assert result["acceptance_probability"] == 0
    assert result["conditional_plugin_dead_estimate"] is None


def test_no_screen_outcome_passes_returns_none():
    result = _api().exact_screen(.5, screen_n=1)
    assert result["acceptance_probability"] == 0
    assert result["conditional_plugin_dead_estimate"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"p": True}, {"p": False}, {"p": "0.1"}, {"p": None},
        {"p": -.1}, {"p": 1.1}, {"p": math.nan}, {"p": math.inf},
        {"p": -math.inf}, {"ceiling": True}, {"ceiling": "0.6"},
        {"ceiling": None}, {"ceiling": 0}, {"ceiling": 1},
        {"ceiling": -.1}, {"ceiling": math.nan}, {"ceiling": math.inf},
        {"screen_n": True}, {"screen_n": 4.0}, {"screen_n": "4"},
        {"screen_n": None}, {"screen_n": 0}, {"screen_n": -1},
        {"screen_n": 257}, {"screen_n": 10**9},
        {"group_g": True}, {"group_g": 4.0}, {"group_g": "4"},
        {"group_g": None}, {"group_g": 1}, {"group_g": 0},
        {"group_g": -1}, {"group_g": 257}, {"group_g": 10**9},
    ],
)
def test_exact_screen_rejects_invalid_numeric_types_and_resource_counts(kwargs):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        api.exact_screen(**({"p": .1} | kwargs))


def test_upper_operational_bounds_use_binomial_counts():
    # 256 counts are cheap; enumerating 2**256 sequences cannot complete.
    result = _api().exact_screen(.5, screen_n=256, group_g=256)
    assert 0 < result["true_dead_probability"] < 1
    assert 0 <= result["acceptance_probability"] <= 1
    assert result["conditional_plugin_dead_estimate"] is not None
    assert 0 <= result["conditional_plugin_dead_estimate"] <= 1
    json.dumps(result, allow_nan=False)


def test_sample_evidence_is_a_frozen_dataclass_with_explicit_fields():
    api = _api()
    sample = _group(api, "g")[0]
    assert dataclasses.is_dataclass(sample)
    assert {field.name for field in dataclasses.fields(sample)} == {
        "sample_id", "group_id", "task_id", "task_fingerprint", "arm", "phase",
        "corpus_id", "split_id", "run_id", "policy_revision", "scorer_id",
        "score", "status", "valid",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.score = 1


@pytest.mark.parametrize(
    "field",
    ["sample_id", "group_id", "task_id", "task_fingerprint", "corpus_id",
     "split_id", "run_id", "policy_revision", "scorer_id"],
)
@pytest.mark.parametrize("bad", ["", "   ", None, 42, True])
def test_identity_fields_are_nonempty_strings(field, bad):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        samples = _group(api, "g")
        samples[0] = dataclasses.replace(samples[0], **{field: bad})
        _summary(api, samples)


@pytest.mark.parametrize(
    "changes",
    [
        {"arm": "python"}, {"arm": ""}, {"arm": None},
        {"phase": "eval"}, {"phase": ""}, {"phase": None},
        {"valid": 1}, {"valid": 0}, {"valid": "true"}, {"valid": None},
        {"score": True}, {"score": False}, {"score": None},
        {"score": .5}, {"score": 2}, {"score": -1}, {"score": "1"},
        {"score": math.nan}, {"score": math.inf}, {"score": -math.inf},
        {"valid": False, "score": True},
        {"valid": False, "score": .5},
        {"valid": False, "score": math.nan},
        {"valid": False, "score": math.inf},
    ],
)
def test_sample_evidence_rejects_invalid_configuration_and_rewards(changes):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        samples = _group(api, "g")
        samples[0] = dataclasses.replace(samples[0], **changes)
        _summary(api, samples)


@pytest.mark.parametrize("score", [0, 1, 0.0, 1.0])
def test_finite_binary_numeric_scores_are_accepted(score):
    api = _api()
    result = _summary(api, _group(api, "g", (score,) * 4))
    assert _only_stratum(result)["valid_successes"] == 4 * score


@pytest.mark.parametrize("score", [None, 0, 1, 0.0, 1.0])
def test_invalid_binary_or_absent_scores_remain_unusable(score):
    api = _api()
    samples = _group(api, "g")
    samples[0] = dataclasses.replace(
        samples[0], valid=False, score=score, status="invalid_gold"
    )
    result = _summary(api, samples)
    stratum = _only_stratum(result)
    _counts(stratum, all_groups=1, usable_groups=0, invalid_groups=1,
            all_samples=4, usable_samples=0, invalid_samples=4, successes=0)
    assert stratum["empirical_dead_group_fraction"] is None
    assert stratum["plugin_dead_estimate"] is None
    assert result["groups"][0]["usable"] is False
    assert result["groups"][0]["dead"] is None


@pytest.mark.parametrize("size", [1, 3, 5])
def test_each_present_group_requires_exactly_g_distinct_samples(size):
    api = _api()
    samples = _group(api, "g", (0,) * size)
    with pytest.raises((TypeError, ValueError)):
        _summary(api, samples)


@pytest.mark.parametrize("group_g", [True, 4.0, "4", None, 0, 1, -1, 257])
def test_summary_rejects_invalid_group_size(group_g):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        _summary(api, _group(api, "g"), group_g=group_g)


def test_duplicate_sample_in_one_group_is_rejected():
    api = _api()
    samples = _group(api, "g")
    samples[1] = dataclasses.replace(samples[1], sample_id=samples[0].sample_id)
    with pytest.raises((TypeError, ValueError)):
        _summary(api, samples)


@pytest.mark.parametrize("phase", ["screen", "confirmation"])
def test_sample_ids_are_globally_unique_even_across_phases(phase):
    api = _api()
    first = _group(api, "first")
    second = _group(api, "second", phase=phase)
    second[0] = dataclasses.replace(second[0], sample_id=first[0].sample_id)
    with pytest.raises((TypeError, ValueError)):
        _summary(api, first + second)


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "task-b"), ("task_fingerprint", "fingerprint-b"),
        ("arm", "bash"), ("phase", "confirmation"), ("corpus_id", "other"),
        ("split_id", "dev"), ("run_id", "run-2"),
        ("policy_revision", "scripted-v2"), ("scorer_id", "execution-v2"),
    ],
)
def test_group_cannot_mix_identity_or_configuration(field, value):
    api = _api()
    samples = _group(api, "g")
    samples[0] = dataclasses.replace(samples[0], **{field: value})
    with pytest.raises((TypeError, ValueError)):
        _summary(api, samples)


def test_group_id_is_global_not_scoped_by_task():
    api = _api()
    first = _group(api, "g")
    second = _group(api, "other", task_id="task-b", task_fingerprint="fingerprint-b")
    second = [dataclasses.replace(sample, group_id="g") for sample in second]
    with pytest.raises((TypeError, ValueError)):
        _summary(api, first + second)


@pytest.mark.parametrize("phase", ["screen", "confirmation"])
def test_evaluation_task_overlap_is_rejected_in_every_phase(phase):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        _summary(api, _group(api, "g", phase=phase), evaluation_task_ids={"task-a"})


def test_disjoint_evaluation_ids_are_not_automatic_task_filters():
    api = _api()
    result = _summary(api, _group(api, "g"), evaluation_task_ids={"evaluation-only"})
    assert result["all_group_count"] == 1
    assert _only_stratum(result)["task_id"] == "task-a"


def test_equal_marginals_do_not_replace_empirical_group_classification():
    api = _api()
    balanced = _summary(api, _group(api, "a") + _group(api, "b"))
    saturated = _summary(
        api, _group(api, "c", (0, 0, 0, 0)) + _group(api, "d", (1, 1, 1, 1))
    )
    for result, empirical in [(balanced, 0), (saturated, 1)]:
        stratum = _only_stratum(result)
        _counts(stratum, all_groups=2, usable_groups=2, invalid_groups=0,
                all_samples=8, usable_samples=8, invalid_samples=0, successes=4)
        assert stratum["empirical_dead_group_fraction"] == empirical
        assert stratum["plugin_dead_estimate"] == pytest.approx(.125)
        assert [group["dead"] for group in result["groups"]] == [bool(empirical)] * 2


def test_taskwise_reduction_is_not_a_pooled_marginal_estimate():
    api = _api()
    samples = _group(api, "a", (0, 0, 0, 0))
    samples += _group(
        api, "b", (1, 1, 1, 1), task_id="task-b", task_fingerprint="fingerprint-b"
    )
    result = _summary(api, samples)
    assert len(result["strata"]) == 2
    assert {stratum["task_id"] for stratum in result["strata"]} == {"task-a", "task-b"}
    for stratum in result["strata"]:
        assert stratum["empirical_dead_group_fraction"] == 1
        assert stratum["plugin_dead_estimate"] == 1  # A pooled .5 would give .125.


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_fingerprint", "fingerprint-b"), ("arm", "bash"),
        ("phase", "confirmation"), ("corpus_id", "other"), ("split_id", "dev"),
        ("run_id", "run-2"), ("policy_revision", "scripted-v2"),
        ("scorer_id", "execution-v2"),
    ],
)
def test_taskwise_strata_preserve_every_configuration_dimension(field, value):
    api = _api()
    result = _summary(
        api, _group(api, "a", (0, 0, 0, 0)) + _group(api, "b", **{field: value})
    )
    assert len(result["strata"]) == 2
    by_value = {stratum[field]: stratum for stratum in result["strata"]}
    assert value in by_value
    assert by_value[value]["empirical_dead_group_fraction"] == 0
    assert by_value[value]["plugin_dead_estimate"] == pytest.approx(.125)
    assert all(stratum["all_group_count"] == 1 for stratum in result["strata"])


def test_invalid_group_preserves_ids_statuses_without_diluting_denominators():
    api = _api()
    usable = _group(api, "usable", (1, 1, 1, 1))
    invalid = _group(api, "invalid", (0, 0, 0, 0))
    invalid[0] = dataclasses.replace(
        invalid[0], score=None, valid=False, status="invalid_gold"
    )
    invalid[1] = dataclasses.replace(invalid[1], status="wrong_answer")
    result = _summary(api, usable + invalid)
    for record in [result, _only_stratum(result)]:
        _counts(record, all_groups=2, usable_groups=1, invalid_groups=1,
                all_samples=8, usable_samples=4, invalid_samples=4, successes=4)
        assert record["status_counts"] == {"ok": 6, "invalid_gold": 1, "wrong_answer": 1}
    stratum = _only_stratum(result)
    assert stratum["empirical_dead_group_fraction"] == 1
    assert stratum["plugin_dead_estimate"] == 1
    groups = {group["group_id"]: group for group in result["groups"]}
    assert set(groups) == {"usable", "invalid"}
    assert set(groups["invalid"]["sample_ids"]) == {sample.sample_id for sample in invalid}
    assert Counter(groups["invalid"]["statuses"]) == Counter(
        sample.status for sample in invalid
    )
    assert dict(zip(groups["invalid"]["sample_ids"], groups["invalid"]["statuses"])) == {
        sample.sample_id: sample.status for sample in invalid
    }
    assert groups["invalid"]["usable"] is False
    assert groups["invalid"]["dead"] is None


def test_empty_collection_has_explicit_zero_counts_and_no_strata():
    api = _api()
    result = _summary(api, [])
    assert result["schema_version"] == 1
    assert result["groups"] == []
    assert result["strata"] == []
    assert result["status_counts"] == {}
    _counts(result, all_groups=0, usable_groups=0, invalid_groups=0,
            all_samples=0, usable_samples=0, invalid_samples=0, successes=0)
    json.dumps(result, allow_nan=False)


def test_summary_does_not_mutate_inputs_and_outputs_are_json_safe_and_detached():
    api = _api()
    samples = _group(api, "g")
    before = tuple(dataclasses.asdict(sample) for sample in samples)
    evaluation_ids = {"not-training"}
    result = _summary(api, samples, evaluation_task_ids=evaluation_ids)
    assert result["schema_version"] == 1
    assert tuple(dataclasses.asdict(sample) for sample in samples) == before
    assert evaluation_ids == {"not-training"}
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    result["groups"][0]["sample_ids"].append("caller-mutation")
    again = _summary(api, tuple(samples), evaluation_task_ids=evaluation_ids)
    assert "caller-mutation" not in again["groups"][0]["sample_ids"]
    assert tuple(dataclasses.asdict(sample) for sample in samples) == before


@pytest.mark.parametrize("status", ["", "   ", None, True, 1, [], {}])
def test_status_requires_a_nonempty_string_without_inventing_a_vocabulary(status):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        samples = _group(api, "g", status=status)
        _summary(api, samples)


@pytest.mark.parametrize("bad", [None, "task-a", b"task-a", {"task-a": True}, 1])
def test_evaluation_membership_requires_an_explicit_collection(bad):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        _summary(api, [], evaluation_task_ids=bad)


@pytest.mark.parametrize("bad", [None, "", "   ", 1, True])
def test_evaluation_ids_are_validated_even_when_no_samples_exist(bad):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        _summary(api, [], evaluation_task_ids=[bad])


@pytest.mark.parametrize("bad", [None, "samples", b"samples", {}, [object()], [None]])
def test_summary_requires_a_collection_of_sample_evidence(bad):
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        _summary(api, bad)


def test_group_records_preserve_all_declared_evidence_including_invalid_scores():
    api = _api()
    samples = _group(api, "g")
    samples[0] = dataclasses.replace(
        samples[0], valid=False, score=1, status="caller-specific-invalid-status"
    )
    result = _summary(api, samples)
    group = result["groups"][0]
    for field in (
        "group_id", "task_id", "task_fingerprint", "arm", "phase", "corpus_id",
        "split_id", "run_id", "policy_revision", "scorer_id",
    ):
        assert group[field] == getattr(samples[0], field)
    by_id = dict(zip(group["sample_ids"], zip(
        group["scores"], group["statuses"], group["validities"]
    )))
    assert by_id == {
        sample.sample_id: (sample.score, sample.status, sample.valid)
        for sample in samples
    }
    assert group["dead"] is None
    assert result["valid_successes"] == 0
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_binomial_probability_survives_intermediate_power_underflow():
    result = _api().exact_screen(.001, screen_n=256, group_g=2, ceiling=.5001)
    # Accepted k=127..129 have p**k == 0.0 in naive power multiplication,
    # but multiplication by binomial coefficients gives representable mass.
    assert .001**127 == 0
    assert 0 < result["acceptance_probability"] < 1e-300
    assert .5 <= result["conditional_plugin_dead_estimate"] <= .5001


def test_unrepresentable_acceptance_is_zero_with_no_conditional_estimate():
    result = _api().exact_screen(1e-20, screen_n=256, group_g=2, ceiling=.5001)
    assert result["acceptance_probability"] == 0
    assert result["conditional_plugin_dead_estimate"] is None
    json.dumps(result, allow_nan=False)


def test_exact_rational_boundary_admits_both_complementary_screen_outcomes():
    from fractions import Fraction

    result = _api().exact_screen(.5, screen_n=3, group_g=4, ceiling=Fraction(17, 81))
    assert result["acceptance_probability"] == pytest.approx(.75, abs=1e-12, rel=0)
    assert result["conditional_plugin_dead_estimate"] == pytest.approx(17 / 81)
    assert result["ceiling_exact"] == "17/81"


def test_decimal_interior_near_one_preserves_representable_acceptance_tail():
    from decimal import Decimal

    result = _api().exact_screen(Decimal("0.99999999999999999999"))
    assert result["acceptance_probability"] == pytest.approx(4e-20, abs=0, rel=1e-12)
    assert result["conditional_plugin_dead_estimate"] == pytest.approx(.3203125)
    assert result["p_exact"] == "99999999999999999999/100000000000000000000"


def test_input_underflow_does_not_erase_a_representable_binomial_tail():
    from decimal import Decimal

    result = _api().exact_screen(Decimal("1e-324"))
    assert result["acceptance_probability"] == float.fromhex("0x0.0000000000001p-1022")
    assert result["conditional_plugin_dead_estimate"] == pytest.approx(.3203125)
    assert result["p_exact"] == f"1/{10**324}"


@pytest.mark.parametrize("ceiling,acceptance", [
    ("0.99999999999999999999", .875), ("1e-1000", 0),
])
def test_decimal_interior_ceiling_is_not_rejected_as_a_rounded_endpoint(ceiling, acceptance):
    from decimal import Decimal

    result = _api().exact_screen(.5, ceiling=Decimal(ceiling))
    assert result["acceptance_probability"] == pytest.approx(acceptance)


@pytest.mark.parametrize("field", ["p", "ceiling"])
def test_large_exact_rational_display_keeps_global_integer_safety_limit(field):
    import sys
    from decimal import Decimal

    limit = sys.get_int_max_str_digits()
    kwargs = {"p": .5, field: Decimal("1e-5000")}
    result = _api().exact_screen(**kwargs)
    assert result[f"{field}_exact"] == "1/1" + "0" * 5000
    assert result["acceptance_probability"] == 0
    assert result["conditional_plugin_dead_estimate"] is None
    assert sys.get_int_max_str_digits() == limit


@pytest.mark.parametrize("field", ["p", "ceiling"])
def test_compact_huge_decimal_rejected_before_denominator_allocation(field, monkeypatch):
    from decimal import Decimal

    api = _api()
    original = api.Fraction
    expanded = []

    def guarded_fraction(value=0, *args):
        if isinstance(value, Decimal):
            expanded.append(value)
            raise AssertionError("attempted unsafe Decimal expansion")
        return original(value, *args)

    monkeypatch.setattr(api, "Fraction", guarded_fraction)
    kwargs = {"p": .5, field: Decimal("1e-1000000000")}
    with pytest.raises(ValueError):
        api.exact_screen(**kwargs)
    assert expanded == []


@pytest.mark.parametrize("field", ["p", "ceiling"])
@pytest.mark.parametrize("kind", ["exponent", "coefficient", "rational"])
def test_oversized_numeric_representations_are_rejected(field, kind):
    from decimal import Decimal
    from fractions import Fraction

    values = {
        "exponent": Decimal("1e-8193"),
        "coefficient": Decimal("0." + "1" * 8193),
        "rational": Fraction(1, 1 << 32769),
    }
    with pytest.raises(ValueError):
        _api().exact_screen(**{"p": .5, field: values[kind]})


def test_invalid_counts_rejected_before_any_numeric_expansion(monkeypatch):
    api = _api()

    def forbidden(*args):
        raise AssertionError("numeric conversion before count validation")

    monkeypatch.setattr(api, "_ratio", forbidden)
    with pytest.raises(ValueError):
        api.exact_screen(.5, screen_n=0)
