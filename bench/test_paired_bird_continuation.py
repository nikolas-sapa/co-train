from dataclasses import replace

import pytest

import bench.paired_bird as api
from bench.test_paired_bird_adversarial import _outcome, _plan, _run


def _rows(plan, arm):
    request = api.ArmRequest(plan.plan_id, arm, plan.draw.eligible, None, "test-only-policy", 1)
    return tuple(_outcome(request, task) for task in request.tasks)


@pytest.mark.parametrize("affected", [("bash",), ("ptc",), ("bash", "ptc")])
@pytest.mark.parametrize("mode", ["replacement", "addition"])
def test_unadmitted_task_never_counts_as_measured(monkeypatch, affected, mode):
    plan = _plan(monkeypatch)
    arms = {arm: _rows(plan, arm) for arm in ("bash", "ptc")}
    for arm in affected:
        unknown = replace(arms[arm][0], task_id="PRIVATE_UNADMITTED_TASK")
        arms[arm] = ((unknown,) + arms[arm][1:] if mode == "replacement"
                     else arms[arm] + (unknown,))
    result = api.adjudicate_paired_bird(plan, arms["bash"], arms["ptc"])
    assert result.status == "void" and result.comparison is None
    expected = tuple(1 if arm in affected and mode == "replacement" else 2
                     for arm in ("bash", "ptc"))
    assert (result.disclosure.measured_a, result.disclosure.measured_b) == expected
    assert result.arm_a is arms["bash"] and result.arm_b is arms["ptc"]
    for arm in affected:
        assert any(item.endswith(":outcome_association") and item.startswith(arm + ":")
                   for item in result.diagnostics)
    assert all("PRIVATE_UNADMITTED_TASK" not in item for item in result.diagnostics)
    assert result.measurement is False and result.cost is result.usage is None


def test_run_unadmitted_task_never_counts_as_measured(monkeypatch):
    plan = _plan(monkeypatch)
    retained = []

    async def driver(request):
        for index, task in enumerate(request.tasks):
            row = _outcome(request, task)
            if request.arm == "bash" and index == 0:
                row = replace(row, task_id="test-only-unadmitted")
            retained.append(row)
            yield row

    result = _run(plan, driver)
    assert result.status == "void" and result.comparison is None
    assert (result.disclosure.measured_a, result.disclosure.measured_b) == (1, 2)
    assert result.arm_a[0] is retained[0]
    assert len(result.arm_a) == len(result.arm_b) == 2


@pytest.mark.parametrize("value", [
    None, "0", True, False, float("nan"), float("inf"), -float("inf"),
    -1, 2, 0.5, 10 ** 400,
], ids=["missing", "string", "true", "false", "nan", "inf", "neg-inf",
        "negative", "above-one", "fraction", "huge-int"])
def test_malformed_execution_accuracy_remains_missing(monkeypatch, value):
    plan = _plan(monkeypatch)
    a, b = _rows(plan, "bash"), _rows(plan, "ptc")
    bad = replace(a[0], status="mismatch", metrics=(api.Metric("execution_accuracy", value),))
    result = api.adjudicate_paired_bird(plan, (bad, a[1]), b)
    assert result.status == "void" and result.comparison is None
    assert (result.disclosure.measured_a, result.disclosure.measured_b) == (1, 2)
    assert "bash:row[0]:invalid_execution_accuracy" in result.diagnostics
    assert result.arm_a[0] is bad


@pytest.mark.parametrize("malformed_first", [False, True])
def test_duplicate_association_cannot_complete(monkeypatch, malformed_first):
    plan = _plan(monkeypatch)
    a, b = _rows(plan, "bash"), _rows(plan, "ptc")
    first = replace(a[0], metrics=()) if malformed_first else a[0]
    result = api.adjudicate_paired_bird(plan, (first, a[0]), b)
    assert result.status == "void" and result.comparison is None
    assert "bash:eligible_coverage_mismatch" in result.diagnostics
    assert len(result.arm_a) == len(result.arm_b) == 2
    assert result.arm_a[0] is first and result.arm_a[1] is a[0]


def test_missing_is_not_zero(monkeypatch):
    plan = _plan(monkeypatch)
    a = tuple(replace(row, status="mismatch", metrics=(api.Metric("execution_accuracy", 0),))
              for row in _rows(plan, "bash"))
    b = _rows(plan, "ptc")
    missing = api.adjudicate_paired_bird(plan, a[:1], b)
    assert missing.status == "void" and missing.comparison is None
    assert (missing.disclosure.measured_a, missing.disclosure.measured_b) == (1, 2)
    restored = api.adjudicate_paired_bird(plan, a, b)
    assert restored.status == "complete" and restored.diagnostics == ()
    assert restored.comparison.n == 2 and restored.comparison.mean_a == 0.0
    assert (restored.disclosure.measured_a, restored.disclosure.measured_b) == (2, 2)


@pytest.mark.parametrize("extra", [False, True])
def test_retention_boundary_n_and_n_plus_one(monkeypatch, extra):
    plan = _plan(monkeypatch)
    dispatched, closed = [], []

    async def driver(request):
        dispatched.append(request.arm)
        try:
            for task in request.tasks:
                yield _outcome(request, task)
            if extra:
                yield _outcome(request, request.tasks[0])
        finally:
            closed.append(request.arm)

    result = _run(plan, driver)
    assert len(result.arm_a) == 2
    if extra:
        assert result.status == "void" and result.comparison is None
        assert result.arm_b == () and dispatched == closed == ["bash"]
        assert "bash:outcome_overflow" in result.diagnostics
    else:
        assert result.status == "complete" and result.comparison.n == 2
        assert len(result.arm_b) == 2 and dispatched == closed == ["bash", "ptc"]
