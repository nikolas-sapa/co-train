"""Synthetic host controls, not real BIRD measurements or provenance proof."""

import asyncio
import dataclasses

import pytest

from bench.test_paired_bird import _api, _instrument, _outcome, _plan


class _Harness:
    def __init__(self, api, plan, instrument, outcome, admissions):
        self.api = api
        self.plan = plan
        self.instrument = instrument
        self.outcome = outcome
        self.admissions = admissions
        self.requests = []
        self.closed = []
        self.observed = {"bash": [], "ptc": []}

    def canonical(self, arm):
        request = self.api.ArmRequest(
            self.plan.plan_id, arm, self.plan.draw.eligible,
            self.instrument, "v25-synthetic-policy", 1)
        return tuple(self.outcome(self.api, request, task) for task in request.tasks)

    def run(self, *, edit=None, fail_arm=None, failure=None,
            short_arm=None, close_arm=None):
        harness = self

        class Rows:
            def __init__(self, request):
                self.request = request
                self.index = 0
                self.rows = [
                    harness.outcome(harness.api, request, task)
                    for task in request.tasks]
                if edit is not None:
                    edit(request, self.rows)
                if request.arm == short_arm:
                    self.rows.pop()

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.request.arm == fail_arm and self.index == 1:
                    raise failure
                if self.index == len(self.rows):
                    raise StopAsyncIteration
                row = self.rows[self.index]
                self.index += 1
                harness.observed[self.request.arm].append(row)
                return row

            async def aclose(self):
                harness.closed.append(self.request.arm)
                if self.request.arm == close_arm:
                    raise RuntimeError("V25_PRIVATE_CLOSE_SENTINEL")

        def driver(request):
            self.requests.append(request)
            assert request.tasks is self.plan.draw.eligible
            assert request.instrument is self.instrument
            assert request.plan_id == self.plan.plan_id
            assert request.policy_identity == "v25-synthetic-policy"
            assert request.num_rollouts == 1
            return Rows(request)

        return asyncio.run(self.api.run_paired_bird(
            self.plan, run_arm=driver, instrument=self.instrument,
            policy_identity="v25-synthetic-policy", num_rollouts=1))

    def check(self, result, measured, *, complete=False):
        assert result.status == ("complete" if complete else "void")
        assert (result.comparison is not None) is complete
        assert bool(result.diagnostics) is not complete
        assert (result.disclosure.planned, result.disclosure.eligible,
                result.disclosure.excluded) == (8, 7, 1)
        assert (result.disclosure.measured_a,
                result.disclosure.measured_b) == measured
        assert result.fixture is True and result.measurement is False
        assert result.cost is None and result.usage is None
        assert all("V25_PRIVATE" not in item for item in result.diagnostics)
        for arm, rows in (("bash", result.arm_a), ("ptc", result.arm_b)):
            assert len(rows) == len(self.observed[arm])
            assert all(actual is observed for actual, observed in zip(
                rows, self.observed[arm], strict=True))
        assert self.closed == [request.arm for request in self.requests]
        assert len(self.admissions) == 1
        assert self.plan.draw is self.admissions[0]

    def consumed(self):
        before = (len(self.requests), len(self.closed), len(self.admissions))
        with pytest.raises(self.api.PairedBirdError, match="consumed|single.use"):
            self.run()
        assert (len(self.requests), len(self.closed), len(self.admissions)) == before


@pytest.fixture
def host(tmp_path, monkeypatch):
    api = _api()
    original = api.prepare.load_validated_draw
    admissions = []

    def observe(*args, **kwargs):
        draw = original(*args, **kwargs)
        admissions.append(draw)
        return draw

    monkeypatch.setattr(api.prepare, "load_validated_draw", observe)
    plan = _plan(tmp_path, api)
    assert len(plan.draw.eligible) == 7
    assert len(admissions) == 1
    return _Harness(api, plan, _instrument(api), _outcome, admissions)


@pytest.mark.parametrize("fault", ["nan", "bool", "negative", "none", "absent"])
def test_v25_invalid_metric_is_missing_not_zero(host, fault):
    def edit(request, rows):
        if request.arm == "ptc":
            value = {"nan": float("nan"), "bool": True,
                     "negative": -1, "none": None, "absent": None}[fault]
            metrics = () if fault == "absent" else (
                host.api.Metric("execution_accuracy", value),)
            rows[0] = dataclasses.replace(rows[0], metrics=metrics)

    result = host.run(edit=edit)
    host.check(result, (7, 6))
    assert len(host.requests) == len(host.closed) == 2
    assert len(result.arm_a) == len(result.arm_b) == 7
    assert "ptc:row[0]:invalid_execution_accuracy" in result.diagnostics
    if fault == "absent":
        assert result.arm_b[0].metrics == ()
    else:
        score = result.arm_b[0].metrics[0].score
        if fault == "nan":
            assert score != score
        elif fault == "none":
            assert score is None
        elif fault == "bool":
            assert score is True
        else:
            assert type(score) is int and score == -1
    host.consumed()


def test_v25_zero_is_a_measured_failure(host):
    def edit(request, rows):
        if request.arm == "ptc":
            rows[:] = [dataclasses.replace(
                row, status="mismatch",
                metrics=(host.api.Metric("execution_accuracy", 0.0),))
                for row in rows]

    result = host.run(edit=edit)
    host.check(result, (7, 7), complete=True)
    assert len(host.requests) == len(host.closed) == 2
    assert result.comparison.n == 7
    assert (result.comparison.mean_a, result.comparison.mean_b) == (1.0, 0.0)
    host.consumed()


def test_v25_duplicate_cannot_replace_missing_task(host):
    def edit(request, rows):
        if request.arm == "ptc":
            rows[1] = rows[0]

    result = host.run(edit=edit)
    host.check(result, (7, 6))
    assert len(host.requests) == 2
    assert len(result.arm_a) == len(result.arm_b) == 7
    assert "ptc:row[1]:duplicate_task" in result.diagnostics
    host.consumed()


@pytest.mark.parametrize("reorder", ["bash", "ptc", "both"])
def test_v25_reordered_cohort_is_void(host, reorder):
    canonical = host.api.adjudicate_paired_bird(
        host.plan, host.canonical("bash"), host.canonical("ptc"))
    assert canonical.status == "complete" and canonical.comparison.n == 7

    def edit(request, rows):
        if reorder == "both" or request.arm == reorder:
            rows.reverse()

    result = host.run(edit=edit)
    host.check(result, (7, 7))
    assert len(host.requests) == 2
    assert len(result.arm_a) == len(result.arm_b) == 7
    for arm in ("bash", "ptc"):
        if reorder == "both" or reorder == arm:
            assert f"{arm}:eligible_coverage_mismatch" in result.diagnostics
    again = host.api.adjudicate_paired_bird(
        host.plan, result.arm_a, result.arm_b)
    assert again.status == "void" and again.comparison is None
    host.consumed()


@pytest.mark.parametrize("field", ["plan_id", "arm"])
def test_v25_per_arm_association_is_required(host, field):
    def edit(request, rows):
        if request.arm == "ptc":
            value = "other-synthetic-plan" if field == "plan_id" else "bash"
            rows[0] = dataclasses.replace(rows[0], **{field: value})

    result = host.run(edit=edit)
    host.check(result, (7, 6))
    assert len(host.requests) == 2
    assert "ptc:row[0]:outcome_association" in result.diagnostics
    host.consumed()


@pytest.mark.parametrize("arm", ["bash", "ptc"])
def test_v25_partial_arm_failure_is_terminal(host, arm):
    result = host.run(
        fail_arm=arm, failure=RuntimeError("V25_PRIVATE_ITERATOR_SENTINEL"))
    host.check(result, (1, 0) if arm == "bash" else (7, 1))
    assert [request.arm for request in host.requests] == (
        ["bash"] if arm == "bash" else ["bash", "ptc"])
    assert (len(result.arm_a), len(result.arm_b)) == (
        (1, 0) if arm == "bash" else (7, 1))
    assert f"{arm}:driver_failure" in result.diagnostics
    repaired = host.api.adjudicate_paired_bird(
        host.plan, host.canonical("bash"), host.canonical("ptc"))
    assert repaired.status == "void" and repaired.comparison is None
    assert f"{arm}:driver_failure" in repaired.diagnostics
    host.consumed()


@pytest.mark.parametrize("arm", ["bash", "ptc"])
def test_v25_cancellation_preserves_identity_and_cleanup(host, arm):
    cancellation = asyncio.CancelledError("V25_PRIVATE_CANCEL_SENTINEL")
    with pytest.raises(asyncio.CancelledError) as caught:
        host.run(fail_arm=arm, failure=cancellation)
    assert caught.value is cancellation
    result = caught.value.paired_bird_result
    host.check(result, (1, 0) if arm == "bash" else (7, 1))
    assert [request.arm for request in host.requests] == (
        ["bash"] if arm == "bash" else ["bash", "ptc"])
    assert (len(result.arm_a), len(result.arm_b)) == (
        (1, 0) if arm == "bash" else (7, 1))
    assert f"{arm}:cancelled" in result.diagnostics
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = "complete"
    host.consumed()


def test_v25_complete_rows_cleanup_failure_is_terminal(host):
    result = host.run(close_arm="ptc")
    host.check(result, (7, 7))
    assert len(host.requests) == 2
    assert len(result.arm_a) == len(result.arm_b) == 7
    assert "ptc:cleanup_failure" in result.diagnostics
    repaired = host.api.adjudicate_paired_bird(
        host.plan, host.canonical("bash"), host.canonical("ptc"))
    assert repaired.status == "void" and repaired.comparison is None
    assert "ptc:cleanup_failure" in repaired.diagnostics
    host.consumed()


def test_v25_short_cohort_never_narrows_denominator(host):
    result = host.run(short_arm="ptc")
    host.check(result, (7, 6))
    assert len(host.requests) == 2
    assert (len(result.arm_a), len(result.arm_b)) == (7, 6)
    assert "ptc:eligible_coverage_mismatch" in result.diagnostics
    host.consumed()
