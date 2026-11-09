"""Plan-only tests for train.engineering_budget. UNRUN until parent validates."""

import importlib
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

NOW = 1_762_000_000
FRESH = NOW - 3600
SOURCE = "modal-official-pricing-observation-2026-10"


def api():
    module = importlib.import_module("train.engineering_budget")
    for name in (
        "RateObservation", "ResourceRates", "GpuWorkload", "PreparationAccount",
        "AncillaryEstimates", "BudgetTerms", "EngineeringBudgetPlan",
        "planned_ceiling_usd", "plan_engineering_budget",
    ):
        assert getattr(module, name, None) is not None, f"missing budget API: {name}"
    return module


def fixture():
    m = api()
    observation = m.RateObservation
    kwargs = dict(
        terms=m.BudgetTerms(Decimal("30"), Decimal("5")),
        rates=m.ResourceRates(
            "sandbox",
            observation(Decimal("0.000542"), "USD/gpu-second", SOURCE, FRESH),
            observation(Decimal("0.00003942"), "USD/physical-core-second", SOURCE, FRESH),
            observation(Decimal("0.00000667"), "USD/GiB-second", SOURCE, FRESH),
        ),
        workload=m.GpuWorkload(1, 8, Decimal("32"), 1800),
        preparation=m.PreparationAccount(Decimal("10"), Decimal("2"), Decimal("3")),
        ancillary=m.AncillaryEstimates(Decimal("1"), Decimal("0.5"), Decimal("0.25")),
        now_seconds=NOW,
    )
    return m, kwargs


def test_baseline_exact_rate_arithmetic():
    m, kw = fixture()
    result = m.plan_engineering_budget(**kw)
    entries = dict(result.breakdown)
    assert entries["gpu"] == Decimal("0.9756")
    assert entries["cpu"] == Decimal("0.567648")
    assert entries["ram"] == Decimal("0.384192")
    assert entries["preparation_remaining"] == Decimal("3")
    assert entries["transfer"] == Decimal("1")
    assert entries["storage"] == Decimal("0.5")
    assert entries["termination_reserve"] == Decimal("0.25")
    assert result.planned_ceiling_usd == Decimal("25")
    assert result.incurred_preparation_gross_usd == Decimal("12")
    assert result.remaining_estimate_usd == Decimal("6.67744")
    assert result.total_estimated_gross_usd == Decimal("18.67744")
    assert result.remaining_plan_allowance_usd == Decimal("6.32256")
    assert result.planned_gpu_deadline_seconds == NOW + 1800


def test_planned_ceiling_is_total_minus_reserve():
    m, _ = fixture()
    assert m.planned_ceiling_usd(Decimal("30"), Decimal("5")) == Decimal("25")
    assert m.planned_ceiling_usd(Decimal("30"), Decimal("0")) == Decimal("30")
    for total, reserve in (
        (Decimal("30"), Decimal("30")),
        (Decimal("30"), Decimal("31")),
        (Decimal("30"), Decimal("-5")),
        (Decimal("0"), Decimal("0")),
        (Decimal("-30"), Decimal("5")),
        (30, Decimal("5")),
        (Decimal("30"), 5),
    ):
        with pytest.raises(ValueError):
            m.planned_ceiling_usd(total, reserve)


def test_duration_1800_accepted_1801_rejected():
    m, kw = fixture()
    accepted = m.plan_engineering_budget(**kw)
    assert accepted.total_estimated_gross_usd == Decimal("18.67744")
    over = replace(kw["workload"], duration_seconds=1801)
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "workload": over})


def test_one_cent_over_available_planned_funds_rejected():
    m, kw = fixture()
    exact = replace(kw["preparation"], remaining_estimate_usd=Decimal("9.32256"))
    result = m.plan_engineering_budget(**{**kw, "preparation": exact})
    assert result.total_estimated_gross_usd == Decimal("25")
    assert result.remaining_plan_allowance_usd == Decimal("0")
    over = replace(exact, remaining_estimate_usd=Decimal("9.33256"))
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "preparation": over})


def test_exhausted_headroom_rejected():
    m, kw = fixture()
    for cash, credits in (("20", "5"), ("25", "0"), ("0", "25")):
        prep = m.PreparationAccount(Decimal(cash), Decimal(credits), Decimal("0"))
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, "preparation": prep})
    thin = m.PreparationAccount(Decimal("24.99"), Decimal("0"), Decimal("0"))
    short = m.GpuWorkload(1, 8, Decimal("32"), 1)
    zeroed = m.AncillaryEstimates(Decimal("0"), Decimal("0"), Decimal("0"))
    result = m.plan_engineering_budget(
        **{**kw, "preparation": thin, "workload": short, "ancillary": zeroed}
    )
    assert result.remaining_estimate_usd == Decimal("0.0010708")
    assert result.total_estimated_gross_usd == Decimal("24.9910708")


def test_credits_are_gross_not_discounted():
    m, kw = fixture()
    cash_only = replace(kw["preparation"], incurred_cash_usd=Decimal("12"),
                        incurred_credits_usd=Decimal("0"))
    credit_only = replace(kw["preparation"], incurred_cash_usd=Decimal("0"),
                          incurred_credits_usd=Decimal("12"))
    a = m.plan_engineering_budget(**{**kw, "preparation": cash_only})
    b = m.plan_engineering_budget(**{**kw, "preparation": credit_only})
    assert a.total_estimated_gross_usd == b.total_estimated_gross_usd == Decimal("18.67744")
    heavy = m.PreparationAccount(Decimal("22"), Decimal("3"), Decimal("0"))
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "preparation": heavy})


def test_sandbox_and_function_cpu_ram_rates_differ():
    m, kw = fixture()
    sandbox = m.plan_engineering_budget(**kw)
    function_rates = m.ResourceRates(
        "function",
        kw["rates"].gpu,
        m.RateObservation(Decimal("0.0000131"), "USD/physical-core-second", SOURCE, FRESH),
        m.RateObservation(Decimal("0.00000222"), "USD/GiB-second", SOURCE, FRESH),
    )
    result = m.plan_engineering_budget(**{**kw, "rates": function_rates})
    entries = dict(result.breakdown)
    assert entries["cpu"] == Decimal("0.18864")
    assert entries["ram"] == Decimal("0.127872")
    assert result.remaining_estimate_usd == Decimal("6.042112")
    assert result.total_estimated_gross_usd == Decimal("18.042112")
    assert entries["cpu"] != dict(sandbox.breakdown)["cpu"]
    assert dict(sandbox.breakdown)["cpu"] == Decimal("0.567648")


def test_gpu_rate_observations_exact():
    m, kw = fixture()
    for rate, expected in (
        ("0.000542", "0.9756"),
        ("0.000694", "1.2492"),
        ("0.001097", "1.9746"),
    ):
        gpu = m.RateObservation(Decimal(rate), "USD/gpu-second", SOURCE, FRESH)
        result = m.plan_engineering_budget(**{**kw, "rates": replace(kw["rates"], gpu=gpu)})
        assert dict(result.breakdown)["gpu"] == Decimal(expected)


def test_negative_inputs_rejected():
    m, kw = fixture()
    for overrides in (
        {"preparation": m.PreparationAccount(Decimal("-1"), Decimal("2"), Decimal("3"))},
        {"preparation": replace(kw["preparation"], remaining_estimate_usd=Decimal("-0.01"))},
        {"preparation": replace(kw["preparation"], incurred_credits_usd=Decimal("-2"))},
        {"ancillary": m.AncillaryEstimates(Decimal("-1"), Decimal("0.5"), Decimal("0.25"))},
        {"ancillary": replace(kw["ancillary"], termination_reserve_usd=Decimal("-0.25"))},
        {"terms": m.BudgetTerms(Decimal("-30"), Decimal("5"))},
        {"terms": m.BudgetTerms(Decimal("30"), Decimal("-5"))},
        {"rates": replace(kw["rates"], gpu=m.RateObservation(
            Decimal("-0.000542"), "USD/gpu-second", SOURCE, FRESH))},
        {"workload": m.GpuWorkload(1, 8, Decimal("-32"), 1800)},
    ):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, **overrides})


def test_nonfinite_decimals_rejected():
    m, kw = fixture()
    for bad in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(
                **{**kw, "ancillary": replace(kw["ancillary"], storage_usd=bad)})
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, "rates": replace(
                kw["rates"],
                ram=m.RateObservation(bad, "USD/GiB-second", SOURCE, FRESH))})


def test_bool_inputs_rejected():
    m, kw = fixture()
    for overrides in (
        {"workload": m.GpuWorkload(True, 8, Decimal("32"), 1800)},
        {"workload": m.GpuWorkload(1, True, Decimal("32"), 1800)},
        {"workload": m.GpuWorkload(1, 8, Decimal("32"), True)},
        {"now_seconds": True},
        {"preparation": m.PreparationAccount(True, Decimal("2"), Decimal("3"))},
        {"max_observation_age_seconds": True},
    ):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, **overrides})


def test_wrong_numeric_types_rejected():
    m, kw = fixture()
    for overrides in (
        {"preparation": m.PreparationAccount(5, Decimal("2"), Decimal("3"))},
        {"preparation": m.PreparationAccount(Decimal("10"), Decimal("2"), 3.0)},
        {"ancillary": m.AncillaryEstimates(1.5, Decimal("0.5"), Decimal("0.25"))},
        {"ancillary": m.AncillaryEstimates(Decimal("1"), "0.5", Decimal("0.25"))},
        {"workload": m.GpuWorkload(1, 8.0, Decimal("32"), 1800)},
        {"workload": m.GpuWorkload(1, 8, 32, 1800)},
        {"now_seconds": float(NOW)},
        {"terms": m.BudgetTerms(30, Decimal("5"))},
        {"rates": replace(kw["rates"], cpu=m.RateObservation(
            0.00003942, "USD/physical-core-second", SOURCE, FRESH))},
        {"rates": replace(kw["rates"], cpu=m.RateObservation(
            Decimal("0.00003942"), "USD/physical-core-second", SOURCE, float(FRESH)))},
    ):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, **overrides})


def test_unknown_context_or_identity_rejected():
    m, kw = fixture()
    for context in ("container", "", None, "SANDBOX"):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(
                **{**kw, "rates": replace(kw["rates"], runtime_context=context)})
    for source in ("", 7, None):
        anonymous = m.RateObservation(Decimal("0.000542"), "USD/gpu-second", source, FRESH)
        with pytest.raises(ValueError):
            m.plan_engineering_budget(
                **{**kw, "rates": replace(kw["rates"], gpu=anonymous)})


def test_mismatched_rate_units_rejected():
    m, kw = fixture()
    for role, unit in (
        ("gpu", "USD/physical-core-second"),
        ("cpu", "USD/GiB-second"),
        ("ram", "USD/gpu-second"),
        ("gpu", "USD/item"),
    ):
        swapped = replace(getattr(kw["rates"], role), rate_unit=unit)
        with pytest.raises(ValueError):
            m.plan_engineering_budget(
                **{**kw, "rates": replace(kw["rates"], **{role: swapped})})


def test_gpu_count_must_be_exactly_one():
    m, kw = fixture()
    for count in (0, 2, -1, 10):
        workload = m.GpuWorkload(count, 8, Decimal("32"), 1800)
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, "workload": workload})


def test_stale_observation_boundary():
    m, kw = fixture()
    edge = m.RateObservation(Decimal("0.000542"), "USD/gpu-second", SOURCE, NOW - 2_592_000)
    result = m.plan_engineering_budget(**{**kw, "rates": replace(kw["rates"], gpu=edge)})
    assert result.total_estimated_gross_usd == Decimal("18.67744")
    stale = replace(edge, observed_at_seconds=NOW - 2_592_001)
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "rates": replace(kw["rates"], gpu=stale)})
    tight = replace(edge, observed_at_seconds=NOW - 61)
    with pytest.raises(ValueError):
        m.plan_engineering_budget(
            **{**kw, "rates": replace(kw["rates"], gpu=tight)},
            max_observation_age_seconds=60)


def test_backward_timestamps_rejected():
    m, kw = fixture()
    future = replace(kw["rates"].cpu, observed_at_seconds=NOW + 1)
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "rates": replace(kw["rates"], cpu=future)})
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "now_seconds": -1})


def test_nonpositive_workload_rejected():
    m, kw = fixture()
    for workload in (
        m.GpuWorkload(1, 8, Decimal("32"), 0),
        m.GpuWorkload(1, 0, Decimal("32"), 1800),
        m.GpuWorkload(1, -8, Decimal("32"), 1800),
        m.GpuWorkload(1, 8, Decimal("0"), 1800),
    ):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(**{**kw, "workload": workload})


def test_deadline_is_now_plus_duration():
    m, kw = fixture()
    for duration in (1, 900, 1799, 1800):
        workload = replace(kw["workload"], duration_seconds=duration)
        result = m.plan_engineering_budget(**{**kw, "workload": workload})
        assert result.planned_gpu_deadline_seconds == NOW + duration
        assert result.planned_gpu_deadline_seconds > NOW


def test_plan_is_immutable_estimate_not_authority():
    m, kw = fixture()
    result = m.plan_engineering_budget(**kw)
    with pytest.raises(FrozenInstanceError):
        result.total_estimated_gross_usd = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        result.planned_gpu_deadline_seconds = NOW
    with pytest.raises(FrozenInstanceError):
        kw["rates"].gpu.rate_usd = Decimal("0")
    assert result.scope == "planning_estimate_only_no_approval_no_provider_cap_no_billing_proof"
    assert type(result.breakdown) is tuple
    assert all(type(entry) is tuple and len(entry) == 2 for entry in result.breakdown)


def test_wrong_dto_types_rejected():
    m, kw = fixture()
    for name in ("terms", "rates", "workload", "preparation", "ancillary"):
        for bad in (None, {}, Decimal("1"), "terms"):
            with pytest.raises(ValueError):
                m.plan_engineering_budget(**{**kw, name: bad})
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "rates": kw["rates"].gpu})
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "terms": kw["preparation"]})


def test_oversized_decimal_rejected():
    m, kw = fixture()
    for bad in (Decimal("1E+97"), Decimal("1E-97"), Decimal("1" * 97)):
        with pytest.raises(ValueError):
            m.plan_engineering_budget(
                **{**kw, "ancillary": replace(kw["ancillary"], storage_usd=bad)})


def test_zero_rate_rejected():
    m, kw = fixture()
    zero = m.RateObservation(Decimal("0"), "USD/gpu-second", SOURCE, FRESH)
    with pytest.raises(ValueError):
        m.plan_engineering_budget(**{**kw, "rates": replace(kw["rates"], gpu=zero)})
