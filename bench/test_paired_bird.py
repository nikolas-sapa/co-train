"""Track B's proposed in-memory contract. No SDK, corpus acquisition or models.

These tests precede implementation. An absent module/dependency is a blocker,
NOT the required intended call-phase RED. Host requests deliberately contain
private SqlTasks: this seam does not establish policy-input safety.
"""

import asyncio
import dataclasses
import importlib

import pytest

from bench import prepare
from bench.test_validated_draw_databases import _artifacts
from ptc.paired import paired
from ptc.sql_arms import Budget


def _api():
    try:
        return importlib.import_module("bench.paired_bird")
    except ModuleNotFoundError as exc:
        if exc.name != "bench.paired_bird":
            raise
        pytest.fail("PAIRED_BIRD_API_ABSENT: admitted coordinator not implemented")


def _plan(tmp_path, api=None):
    api = _api() if api is None else api
    root, draw, draw_sha, supp, supp_sha = _artifacts(
        tmp_path, excluded_only=True)
    return api.prepare_paired_bird(
        root, draw, supp, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha, fixture=True)


def _instrument(api):
    # Declared settings only. The coordinator cannot authenticate a policy or
    # prove that an arbitrary trusted host callback enforces these limits.
    return api.Instrument(
        identity="local-fixture-instrument",
        budget=Budget(max_turns=8, max_retries=0, retry_on=(),
                      rollout_timeout=600.0, program_timeout=5.0),
        action_max_rows=200, query_timeout_s=30.0,
        sampling_identity="scripted-fixture-no-model")


def _outcome(api, request, task, score=1.0, **changes):
    fields = dict(
        plan_id=request.plan_id, arm=request.arm, task_id=task.name,
        completed=True, valid=True, status="match" if score else "mismatch",
        metrics=(api.Metric(name="execution_accuracy", score=score),),
        output_ref="memory:fixture/" + request.arm + "/" + task.name)
    fields.update(changes)
    return api.TaskOutcome(**fields)


def _run(api, plan, driver, *, num_rollouts=1):
    return asyncio.run(api.run_paired_bird(
        plan, run_arm=driver, instrument=_instrument(api),
        policy_identity="scripted-fixture-policy", num_rollouts=num_rollouts))


def _assert_void(result):
    assert result.status == "void", "VOID_STATUS_BECAME_COMPLETE"
    assert result.comparison is None, "VOID_BECAME_PAIRED_ESTIMATE"
    assert result.diagnostics


def test_b_complete14_single_use_and_immutable_records(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)
    requests = []
    rows = []

    async def driver(request):
        requests.append(request)
        for task in request.tasks:
            row = _outcome(api, request, task)
            rows.append(row)
            yield row

    result = _run(api, plan, driver)
    assert [r.arm for r in requests] == ["bash", "ptc"]
    assert len(rows) == len({(r.arm, r.task_id) for r in rows}) == 14
    for request in requests:
        assert request.tasks is plan.draw.eligible
        assert request.plan_id == plan.plan_id
        assert request.num_rollouts == 1
        assert request.policy_identity == "scripted-fixture-policy"
    assert requests[0].instrument is requests[1].instrument
    assert requests[0].instrument == _instrument(api)
    assert result.status == "complete" and result.comparison.n == 7
    assert result.arm_a == tuple(rows[:7])
    assert result.arm_b == tuple(rows[7:])
    adjudicated = api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b)
    assert adjudicated.comparison == result.comparison
    narrowed = api.adjudicate_paired_bird(
        plan, result.arm_a[:-1], result.arm_b[:-1])
    _assert_void(narrowed)
    for record, field in (
        (plan, "plan_id"), (requests[0], "arm"),
        (requests[0].instrument, "identity"), (rows[0], "completed"),
        (rows[0].metrics[0], "score"), (result, "status"),
        (result.comparison, "n"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, field, getattr(record, field))
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(api, plan, driver)
    assert len(requests) == 2, "REUSED_PLAN_DISPATCHED"


@pytest.mark.parametrize("num_rollouts", [0, 2, True, 1.0, 1.5])
def test_b_unsupported_multisample_zero_dispatch(tmp_path, num_rollouts):
    api = _api()
    plan = _plan(tmp_path, api)
    calls = []

    async def driver(request):
        calls.append(request)
        yield _outcome(api, request, request.tasks[0])

    with pytest.raises(api.PairedBirdError, match="rollout"):
        _run(api, plan, driver, num_rollouts=num_rollouts)
    assert calls == []


@pytest.mark.parametrize("fault", [
    "remove", "duplicate", "substitute", "relabel", "add", "both-remove",
])
def test_b_coverage_failures_never_narrow_denominator(tmp_path, fault):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        rows = [_outcome(api, request, task) for task in request.tasks]
        if request.arm == "bash" or fault == "both-remove":
            if fault in ("remove", "both-remove"):
                rows.pop()
            elif fault == "duplicate":
                rows[1] = rows[0]
            elif fault == "substitute":
                rows[0] = dataclasses.replace(rows[0], task_id="not-admitted")
            elif fault == "relabel":
                rows[0] = dataclasses.replace(rows[0], arm="ptc")
            elif fault == "add":
                rows.append(dataclasses.replace(rows[0], task_id="not-admitted"))
        for row in rows:
            yield row

    result = _run(api, plan, driver)
    _assert_void(result)
    assert result.arm_a, "COVERAGE_FAILURE_DISCARDED_DIAGNOSTICS"


@pytest.mark.parametrize("fault", [
    "infrastructure", "invalid-gold", "incomplete", "missing-ex",
    "missing-output", "wrong-plan",
])
def test_b_void_not_zero_preserves_partial_rows(tmp_path, fault):
    api = _api()
    plan = _plan(tmp_path, api)
    observed = []

    async def driver(request):
        for index, task in enumerate(request.tasks):
            if request.arm == "bash" and index == 1 and fault == "infrastructure":
                raise OSError("PRIVATE_DRIVER_SENTINEL")
            changes = {}
            if request.arm == "bash" and index == 1:
                changes = {
                    "invalid-gold": {"valid": False, "status": "gold_error"},
                    "incomplete": {"completed": False},
                    "missing-ex": {"metrics": ()},
                    "missing-output": {"output_ref": None},
                    "wrong-plan": {"plan_id": "different-plan"},
                }.get(fault, {})
            row = _outcome(api, request, task, **changes)
            observed.append(row)
            yield row

    result = _run(api, plan, driver)
    _assert_void(result)
    assert result.arm_a[0] is observed[0]
    assert result.arm_a[0].metrics[0].score == 1.0
    if fault == "infrastructure":
        assert len(observed) == len(result.arm_a) == 1
        assert result.arm_b == ()
    assert all("PRIVATE_DRIVER_SENTINEL" not in d for d in result.diagnostics)


def test_b_cancellation_propagates_with_partial_diagnostics(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)
    observed = []

    async def driver(request):
        row = _outcome(api, request, request.tasks[0])
        observed.append(row)
        yield row
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError) as caught:
        _run(api, plan, driver)
    # Preserve cancellation semantics, but attach an immutable partial result.
    result = caught.value.paired_bird_result
    _assert_void(result)
    assert result.arm_a == tuple(observed) and result.arm_b == ()
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(api, plan, driver)
    assert len(observed) == 1


@pytest.mark.parametrize("value", [
    float("nan"), float("inf"), -float("inf"), True, False, 0.5, -1, 2,
])
def test_b_metric_ex_only_rejects_nonbinary_or_bool(tmp_path, value):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        for index, task in enumerate(request.tasks):
            yield _outcome(api, request, task, score=value if index == 0 else 1.0)

    _assert_void(_run(api, plan, driver))


@pytest.mark.parametrize("duplicate", [False, True])
def test_b_ex_is_one_named_component_not_reward_sum(tmp_path, duplicate):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        for task in request.tasks:
            metrics = (api.Metric("execution_accuracy", 0.0),
                       api.Metric("unrelated_reward", 9000.0))
            if duplicate:
                metrics += (api.Metric("execution_accuracy", 1.0),)
            yield _outcome(api, request, task, metrics=metrics, status="mismatch")

    result = _run(api, plan, driver)
    if duplicate:
        _assert_void(result)
    else:
        assert result.status == "complete"
        assert result.comparison.mean_a == result.comparison.mean_b == 0.0
        assert result.comparison.delta == 0.0


def test_b_disclosure_no_planned_denominator_accuracy(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        for task in request.tasks:
            yield _outcome(api, request, task, score=0.0)

    result = _run(api, plan, driver)
    disclosure = result.disclosure
    assert (disclosure.planned, disclosure.eligible, disclosure.excluded) == (8, 7, 1)
    assert (disclosure.measured_a, disclosure.measured_b) == (7, 7)
    assert disclosure.exclusions is plan.draw.exclusions
    assert disclosure.databases is plan.draw.databases
    assert disclosure.exclusions[0].status == "gold_error"
    assert disclosure.exclusions[0].category == "gold_execution_rejection"
    excluded = {e.id for e in disclosure.exclusions}
    assert excluded.isdisjoint(r.task_id for r in result.arm_a + result.arm_b)
    for tasks, counts in (
        (plan.draw.planned, disclosure.shapes_planned),
        (plan.draw.eligible, disclosure.shapes_eligible),
    ):
        assert counts == (len({t.shape for t in tasks}),
                          len({t.coarse_shape for t in tasks}))
    assert "two" in disclosure.tier_limitation.lower()
    assert "three" in disclosure.tier_limitation.lower()
    assert result.fixture is True and result.measurement is False
    assert result.cost is None and result.usage is None
    assert not hasattr(result, "bird_accuracy")


def test_b_paired4_matches_existing_estimator(tmp_path):
    api = _api()
    from bench import fixture
    from bench.test_prepare import _write_corpus

    records = fixture.records()
    # Four real admitted synthetic BIRD tasks, all three tiers represented.
    chosen = [next(r for r in records if r["difficulty"] == tier)
              for tier in ("simple", "moderate", "challenging")]
    chosen.append(next(r for r in records
                       if r["difficulty"] == "moderate" and r not in chosen))
    root = _write_corpus(tmp_path / "corpus", chosen)
    draw, supp = tmp_path / "draw.json", tmp_path / "supp.json"
    draw_sha = prepare.freeze_draw(
        root, draw, seed=0, per_tier={"simple": 1, "moderate": 2, "challenging": 1},
        fixture=True)
    supp_sha = prepare.validate_draw(
        root, draw, supp, expected_draw_sha256=draw_sha)
    plan = api.prepare_paired_bird(
        root, draw, supp, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha, fixture=True)
    scores = {"bash": (1, 1, 0, 1), "ptc": (1, 0, 0, 0)}

    async def driver(request):
        for task, score in zip(request.tasks, scores[request.arm], strict=True):
            yield _outcome(api, request, task, score=float(score))

    result = _run(api, plan, driver)
    estimate = result.comparison
    expected = paired(
        {t.name: s for t, s in zip(plan.draw.eligible, scores["bash"], strict=True)},
        {t.name: s for t, s in zip(plan.draw.eligible, scores["ptc"], strict=True)})
    assert (estimate.n, estimate.delta, estimate.a_only,
            estimate.b_only, estimate.ties, estimate.p) == (4, .5, 2, 0, 2, .5)
    for key in ("n", "mean_a", "mean_b", "delta", "ci",
                "a_only", "b_only", "ties", "p"):
        assert getattr(estimate, key) == expected[key]


@pytest.mark.parametrize("changes", [
    {"completed": 1}, {"valid": 1}, {"status": "exit0"},
    {"status": None}, {"output_ref": ""}, {"output_ref": True},
    {"arm": True}, {"task_id": True}, {"plan_id": True},
    {"status": "mismatch"},  # score1 cannot describe a mismatch
])
def test_b_exact_outcome_metadata_and_status_gate(tmp_path, changes):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        for index, task in enumerate(request.tasks):
            yield _outcome(api, request, task, **(changes if index == 0 else {}))

    _assert_void(_run(api, plan, driver))


@pytest.mark.parametrize("status", [
    "mismatch", "pred_empty", "pred_error", "pred_timeout", "pred_truncated",
])
def test_b_existing_valid_prediction_failures_are_genuine_zero(tmp_path, status):
    api = _api()
    plan = _plan(tmp_path, api)

    async def driver(request):
        for task in request.tasks:
            yield _outcome(api, request, task, score=0.0, status=status)

    result = _run(api, plan, driver)
    assert result.status == "complete"
    assert result.comparison.mean_a == result.comparison.mean_b == 0.0


@pytest.mark.parametrize("fault", ["failure", "cancellation", "non-outcome"])
def test_b_second_arm_failure_preserves_both_partial_sequences(tmp_path, fault):
    api = _api()
    plan = _plan(tmp_path, api)
    seen = {"bash": [], "ptc": []}

    async def driver(request):
        for index, task in enumerate(request.tasks):
            if request.arm == "ptc" and index == 1:
                if fault == "cancellation":
                    raise asyncio.CancelledError()
                if fault == "non-outcome":
                    yield object()
                    return
                raise RuntimeError("PRIVATE_SECOND_ARM_SENTINEL")
            row = _outcome(api, request, task)
            seen[request.arm].append(row)
            yield row

    if fault == "cancellation":
        with pytest.raises(asyncio.CancelledError) as caught:
            _run(api, plan, driver)
        result = caught.value.paired_bird_result
    else:
        result = _run(api, plan, driver)
    _assert_void(result)
    assert result.arm_a == tuple(seen["bash"]) and len(result.arm_a) == 7
    assert result.arm_b == tuple(seen["ptc"]) and len(result.arm_b) == 1
    assert all("PRIVATE_SECOND_ARM_SENTINEL" not in d for d in result.diagnostics)
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(api, plan, driver)


def test_b_foreign_plan_outcomes_refused_by_direct_adjudication(tmp_path):
    api = _api()
    first = _plan(tmp_path / "first", api)
    second = _plan(tmp_path / "second", api)

    async def driver(request):
        for task in request.tasks:
            yield _outcome(api, request, task)

    result = _run(api, first, driver)
    _assert_void(api.adjudicate_paired_bird(second, result.arm_a, result.arm_b))


def test_b_overlapping_consumption_dispatches_only_one_pair(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)
    calls = []

    async def driver(request):
        calls.append(request.arm)
        await asyncio.sleep(0)  # scheduling barrier, no external IO
        for task in request.tasks:
            yield _outcome(api, request, task)

    async def overlap():
        return await asyncio.gather(*(
            api.run_paired_bird(
                plan, run_arm=driver, instrument=_instrument(api),
                policy_identity="fixture", num_rollouts=1) for _ in range(2)),
            return_exceptions=True)

    results = asyncio.run(overlap())
    assert sum(isinstance(r, api.PairedBirdError) for r in results) == 1
    assert sum(isinstance(r, api.PairedBirdResult) and r.status == "complete"
               for r in results) == 1
    assert calls == ["bash", "ptc"]


def test_b_review_retained_generator_closed_before_live_loop_return(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)

    async def scenario():
        retained, closed = [], []

        async def rows(request):
            try:
                yield _outcome(api, request, request.tasks[0])
                yield object()
            finally:
                closed.append(request.arm)

        def driver(request):
            iterator = rows(request)
            retained.append(iterator)  # prevent collection/shutdown hiding cleanup
            return iterator

        try:
            result = await api.run_paired_bird(
                plan, run_arm=driver, instrument=_instrument(api),
                policy_identity="fixture", num_rollouts=1)
            _assert_void(result)
            assert closed == ["bash"], "RETAINED_ITERATOR_NOT_CLOSED_BEFORE_RETURN"
            assert len(result.arm_a) == 1 and result.arm_b == ()
        finally:
            for iterator in retained:
                await iterator.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_during_close", [False, True])
def test_b_review_return_waits_for_retained_generator_cleanup(tmp_path, cancel_during_close):
    api = _api()
    plan = _plan(tmp_path, api)

    async def scenario():
        entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        retained = []

        async def rows(request):
            try:
                yield _outcome(api, request, request.tasks[0])
                yield object()
            finally:
                entered.set()
                await release.wait()
                finished.set()

        def driver(request):
            iterator = rows(request)
            retained.append(iterator)
            return iterator

        running = asyncio.create_task(api.run_paired_bird(
            plan, run_arm=driver, instrument=_instrument(api),
            policy_identity="fixture", num_rollouts=1))
        cleanup = asyncio.create_task(entered.wait())
        try:
            await asyncio.wait((running, cleanup), timeout=1,
                               return_when=asyncio.FIRST_COMPLETED)
            assert entered.is_set(), "COORDINATOR_DID_NOT_START_ITERATOR_CLEANUP"
            assert not running.done(), "COORDINATOR_RETURNED_BEFORE_CLEANUP_RELEASE"
            if cancel_during_close:
                running.cancel("PRIVATE_CLEANUP_CANCEL_SENTINEL")
                await asyncio.sleep(0)
                assert not running.done(), "CANCEL_BYPASSED_PENDING_CLEANUP"
            release.set()
            if cancel_during_close:
                with pytest.raises(asyncio.CancelledError) as caught:
                    await asyncio.wait_for(running, 1)
                result = caught.value.paired_bird_result
            else:
                result = await asyncio.wait_for(running, 1)
            assert finished.is_set(), "COORDINATOR_RETURNED_BEFORE_CLEANUP_FINISHED"
            _assert_void(result)
        finally:
            release.set()
            await asyncio.gather(running, return_exceptions=True)
            for iterator in retained:
                await iterator.aclose()
            cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)

    asyncio.run(scenario())


def test_b_review_external_cancellation_waits_and_preserves_exception(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)

    async def scenario():
        suspended, entered = asyncio.Event(), asyncio.Event()
        release, finished = asyncio.Event(), asyncio.Event()
        retained, cancellations = [], []

        async def rows(request):
            try:
                yield _outcome(api, request, request.tasks[0])
                suspended.set()
                await asyncio.Event().wait()
            except asyncio.CancelledError as exc:
                cancellations.append(exc)
                raise
            finally:
                entered.set()
                await release.wait()
                finished.set()

        def driver(request):
            iterator = rows(request)
            retained.append(iterator)
            return iterator

        running = asyncio.create_task(api.run_paired_bird(
            plan, run_arm=driver, instrument=_instrument(api),
            policy_identity="fixture", num_rollouts=1))
        try:
            await asyncio.wait_for(suspended.wait(), 1)
            running.cancel("PRIVATE_EXTERNAL_CANCEL_SENTINEL")
            await asyncio.wait_for(entered.wait(), 1)
            assert not running.done(), "CANCELLATION_RESOLVED_BEFORE_CLEANUP"
            release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await running
            # Cancellation is independently delivered across coordinator and
            # advancement Tasks. The review02 test observes and checks exact
            # first-coordinator identity; driver-owned exception tests retain
            # their separate exact-identity contract.
            assert caught.value.args == cancellations[0].args == (
                "PRIVATE_EXTERNAL_CANCEL_SENTINEL",)
            assert finished.is_set()
            result = caught.value.paired_bird_result
            _assert_void(result)
            assert len(result.arm_a) == 1 and result.arm_b == ()
            assert all("PRIVATE_EXTERNAL_CANCEL_SENTINEL" not in d
                       for d in result.diagnostics)
            with pytest.raises(dataclasses.FrozenInstanceError):
                result.status = "complete"
        finally:
            release.set()
            await asyncio.gather(running, return_exceptions=True)
            for iterator in retained:
                await iterator.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_b_review_explicit_aclose_failure_cannot_complete(tmp_path, cancel):
    api = _api()
    plan = _plan(tmp_path, api)
    calls, closed = [], []
    failure = (asyncio.CancelledError("PRIVATE_CLOSE_SENTINEL") if cancel
               else RuntimeError("PRIVATE_CLOSE_SENTINEL"))

    class Rows:
        def __init__(self, request):
            self.request = request
            self.tasks = iter(request.tasks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            task = next(self.tasks, None)
            if task is None:
                raise StopAsyncIteration
            return _outcome(api, self.request, task)

        async def aclose(self):
            closed.append(self.request.arm)
            raise failure

    def driver(request):
        calls.append(request.arm)
        return Rows(request)

    if cancel:
        with pytest.raises(asyncio.CancelledError) as caught:
            _run(api, plan, driver)
        assert caught.value is failure
        result = caught.value.paired_bird_result
    else:
        result = _run(api, plan, driver)
    assert closed == ["bash"], "SUPPORTED_ACLOSE_NOT_AWAITED"
    assert calls == ["bash"]
    _assert_void(result)
    assert len(result.arm_a) == 7 and result.arm_b == ()
    assert all("PRIVATE_CLOSE_SENTINEL" not in d for d in result.diagnostics)


@pytest.mark.parametrize("close_cancel", [False, True])
def test_b_review_primary_cancellation_survives_cleanup_failure(tmp_path, close_cancel):
    api = _api()
    plan = _plan(tmp_path, api)
    primary = asyncio.CancelledError("PRIVATE_PRIMARY_CANCEL")
    secondary = (asyncio.CancelledError("PRIVATE_SECONDARY_CANCEL") if close_cancel
                 else RuntimeError("PRIVATE_SECONDARY_ERROR"))
    closed = []

    class Rows:
        def __init__(self, request):
            self.request = request
            self.yielded = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.yielded:
                raise primary
            self.yielded = True
            return _outcome(api, self.request, self.request.tasks[0])

        async def aclose(self):
            closed.append(self.request.arm)
            raise secondary

    with pytest.raises(asyncio.CancelledError) as caught:
        _run(api, plan, Rows)
    assert caught.value is primary, "PRIMARY_CANCELLATION_REPLACED_DURING_CLOSE"
    assert closed == ["bash"], "CANCELLED_ITERATOR_CLOSE_SKIPPED"
    result = caught.value.paired_bird_result
    _assert_void(result)
    assert len(result.arm_a) == 1 and result.arm_b == ()
    assert all("PRIVATE_" not in d for d in result.diagnostics)


@pytest.mark.parametrize("cancel", [False, True])
def test_b_review_all_rows_terminal_failure_stays_void_on_readjudication(tmp_path, cancel):
    api = _api()
    plan = _plan(tmp_path, api)
    calls = []
    failure = (asyncio.CancelledError("PRIVATE_TERMINAL_SENTINEL") if cancel
               else RuntimeError("PRIVATE_TERMINAL_SENTINEL"))

    async def driver(request):
        calls.append(request.arm)
        for task in request.tasks:
            yield _outcome(api, request, task)
        if request.arm == "ptc":
            raise failure

    if cancel:
        with pytest.raises(asyncio.CancelledError) as caught:
            _run(api, plan, driver)
        assert caught.value is failure
        result = caught.value.paired_bird_result
    else:
        result = _run(api, plan, driver)
    _assert_void(result)
    assert len(result.arm_a) == len(result.arm_b) == 7
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(api, plan, driver)
    assert calls == ["bash", "ptc"]
    again = api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b)
    assert again.status == "void", "TERMINAL_FAILURE_LOST_ON_READJUDICATION"
    assert again.comparison is None and again.diagnostics
    assert all("PRIVATE_TERMINAL_SENTINEL" not in d for d in again.diagnostics)


def test_b_review02_repeated_cancel_joins_actual_generator_unwind(tmp_path, monkeypatch):
    import sys

    api = _api()
    plan = _plan(tmp_path, api)
    original_mark = api._mark_terminal

    async def scenario():
        suspended, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        second_seen, abandoned = asyncio.Event(), asyncio.Event()
        calls, retained, generator_cancels, coordinator_cancels = [], [], [], []
        starts, finishes, generator_tasks = [], [], []
        running = None

        def observe_terminal(actual_plan, diagnostic):
            # Observe the actual coordinator exception boundary, without
            # substituting either Task.cancel delivery or iterator advancement.
            exc = sys.exception()
            if (asyncio.current_task() is running
                    and diagnostic == "bash:cancelled"
                    and isinstance(exc, asyncio.CancelledError)):
                coordinator_cancels.append(exc)
                if exc.args == ("PRIVATE_SECOND_CANCEL",):
                    second_seen.set()
            original_mark(actual_plan, diagnostic)

        async def rows(request):
            generator_tasks.append(asyncio.current_task())
            try:
                yield _outcome(api, request, request.tasks[0])
                suspended.set()
                await asyncio.Event().wait()
            except asyncio.CancelledError as exc:
                generator_cancels.append(exc)
                raise
            finally:
                starts.append(request.arm)
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    abandoned.set()
                    raise
                finishes.append(request.arm)

        def driver(request):
            calls.append(request.arm)
            iterator = rows(request)
            retained.append(iterator)
            return iterator

        monkeypatch.setattr(api, "_mark_terminal", observe_terminal)
        running = asyncio.create_task(api.run_paired_bird(
            plan, run_arm=driver, instrument=_instrument(api),
            policy_identity="fixture", num_rollouts=1))
        try:
            await asyncio.wait_for(suspended.wait(), 1)
            running.cancel("PRIVATE_FIRST_CANCEL")
            await asyncio.wait_for(entered.wait(), 1)
            running.cancel("PRIVATE_SECOND_CANCEL")
            await asyncio.wait_for(second_seen.wait(), 1)
            assert not abandoned.is_set(), "REPEAT_CANCEL_ABANDONED_ACTUAL_UNWIND"
            assert not running.done(), "REPEAT_CANCEL_RESOLVED_BEFORE_UNWIND_RELEASE"
            assert starts == ["bash"] and finishes == []
            release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await running
            assert caught.value is coordinator_cancels[0], \
                "FIRST_COORDINATOR_CANCELLATION_REPLACED"
            assert caught.value.args == ("PRIVATE_FIRST_CANCEL",)
            assert len(generator_cancels) == 1, "ADVANCE_CANCELLED_MORE_THAN_ONCE"
            assert generator_cancels[0].args == ("PRIVATE_FIRST_CANCEL",)
            # Distinct task boundaries receive independent cancellation objects.
            # Only the first COORDINATOR object must survive to the caller.
            assert generator_tasks[0] is not running
            assert starts == finishes == ["bash"]
            assert calls == ["bash"]
            result = caught.value.paired_bird_result
            _assert_void(result)
            assert len(result.arm_a) == 1 and result.arm_b == ()
            assert all("PRIVATE_" not in d for d in result.diagnostics)
            with pytest.raises(dataclasses.FrozenInstanceError):
                result.status = "complete"
            _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
            with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
                await api.run_paired_bird(
                    plan, run_arm=driver, instrument=_instrument(api),
                    policy_identity="fixture", num_rollouts=1)
            assert calls == ["bash"]
        finally:
            release.set()
            await asyncio.gather(running, return_exceptions=True)
            for iterator in retained:
                await iterator.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("overflow_arm", ["bash", "ptc"])
def test_b_review_outcome_retention_and_consumption_bounded_by_schedule(tmp_path, overflow_arm):
    api = _api()
    plan = _plan(tmp_path, api)

    async def scenario():
        retained, calls, closed = [], [], []
        consumed = {"bash": 0, "ptc": 0}

        async def rows(request):
            try:
                # Finite overproducer safely reproduces an unbounded-list defect
                # against the old coordinator, without launching an infinite loop.
                count = 20 if request.arm == overflow_arm else len(request.tasks)
                for index in range(count):
                    consumed[request.arm] += 1
                    yield _outcome(
                        api, request, request.tasks[index % len(request.tasks)])
            finally:
                closed.append(request.arm)

        def driver(request):
            calls.append(request.arm)
            iterator = rows(request)
            retained.append(iterator)
            return iterator

        try:
            result = await api.run_paired_bird(
                plan, run_arm=driver, instrument=_instrument(api),
                policy_identity="fixture", num_rollouts=1)
            assert len(result.arm_a) <= 7 and len(result.arm_b) <= 7, \
                "OUTCOME_RETENTION_EXCEEDED_ADMITTED_N"
            assert consumed[overflow_arm] == 8, "OVERFLOW_CONSUMED_BEYOND_N_PLUS_ONE"
            assert calls == (["bash"] if overflow_arm == "bash" else ["bash", "ptc"])
            assert closed == calls, "OVERFLOW_ITERATOR_NOT_CLOSED_BEFORE_RETURN"
            _assert_void(result)
            assert f"{overflow_arm}:outcome_overflow" in result.diagnostics
            _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
        finally:
            for iterator in retained:
                await iterator.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["malformed", "overflow"])
def test_b_review03_context_token_lifecycle_has_one_arm_owner(tmp_path, fault):
    import contextvars

    api = _api()
    plan = _plan(tmp_path, api)
    context = contextvars.ContextVar("paired_bird_review03", default="unset")

    async def scenario():
        caller_token = context.set("caller")
        factories, advancing, closing, reset, errors, calls = [], [], [], [], [], []
        retained = []

        async def rows(request):
            advancing.append(asyncio.current_task())
            token = context.set("arm")
            try:
                count = 8 if fault == "overflow" else 1
                for index in range(count):
                    yield _outcome(api, request, request.tasks[index % 7])
                if fault == "malformed":
                    yield object()
            finally:
                closing.append(asyncio.current_task())
                try:
                    context.reset(token)
                except ValueError:
                    errors.append("token-context-mismatch")
                    raise
                reset.append(request.arm)

        def driver(request):
            calls.append(request.arm)
            factories.append(asyncio.current_task())
            assert context.get() == "caller"
            iterator = rows(request)
            retained.append(iterator)
            return iterator

        try:
            result = await api.run_paired_bird(
                plan, run_arm=driver, instrument=_instrument(api),
                policy_identity="fixture", num_rollouts=1)
            _assert_void(result)
            assert reset == ["bash"] and errors == [], \
                "ARM_CONTEXT_TOKEN_RESET_INCOMPLETE"
            assert factories == advancing == closing, \
                "DRIVER_ITERATION_AND_FINALIZATION_CHANGED_OWNER"
            assert factories[0] is not asyncio.current_task()
            assert context.get() == "caller", "CALLER_CONTEXT_WAS_MUTATED"
            assert calls == ["bash"]
            assert len(result.arm_a) == (7 if fault == "overflow" else 1)
            _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
        finally:
            for iterator in retained:
                await iterator.aclose()
            context.reset(caller_token)

    asyncio.run(scenario())


def _review03_prestart_cancel_child(tmp_path, caller_cancel):
    """Child-only probe. The parent subprocess watchdog bounds old busy loops."""
    import sys

    api = _api()
    plan = _plan(tmp_path, api)

    async def scenario():
        original_create, original_mark = asyncio.create_task, api._mark_terminal
        calls, managed, observed = [], [], []
        coordinator = asyncio.current_task()

        def observe_terminal(actual_plan, diagnostic):
            exc = sys.exception()
            if (asyncio.current_task() is coordinator
                    and isinstance(exc, asyncio.CancelledError)
                    and exc.args == ("PRIVATE_FIRST_CALLER_CANCEL",)):
                observed.append(exc)
            original_mark(actual_plan, diagnostic)

        def create_and_cancel_before_start(coro, **kwargs):
            task = original_create(coro, **kwargs)
            # Exercise the old separate cleanup task and the approved unified
            # arm owner at the same real pre-first-execution cancellation seam.
            if coro.cr_code.co_name in ("_close_iterator", "_run_arm"):
                managed.append(task)
                task.cancel("PRIVATE_PRESTART_TASK_CANCEL")
                if caller_cancel:
                    coordinator.cancel("PRIVATE_FIRST_CALLER_CANCEL")
            return task

        async def driver(request):
            calls.append(request.arm)
            yield _outcome(api, request, request.tasks[0])
            yield object()

        asyncio.create_task, api._mark_terminal = create_and_cancel_before_start, observe_terminal
        try:
            try:
                result = await api.run_paired_bird(
                    plan, run_arm=driver, instrument=_instrument(api),
                    policy_identity="fixture", num_rollouts=1)
            except asyncio.CancelledError as exc:
                assert caller_cancel, "OWNER_CANCEL_LEAKED_AS_CALLER_CANCEL"
                assert observed and exc is observed[0], "FIRST_CALLER_CANCEL_CHANGED"
                assert exc.args == ("PRIVATE_FIRST_CALLER_CANCEL",)
                result = exc.paired_bird_result
            else:
                assert not caller_cancel, "FIRST_CALLER_CANCEL_SWALLOWED"
            assert len(managed) == 1 and managed[0].cancelled()
            assert "ptc" not in calls, "NEXT_ARM_DISPATCHED_AFTER_OWNER_CANCEL"
            _assert_void(result)
            assert "bash:cleanup_failure" in result.diagnostics
            assert all("PRIVATE_" not in d for d in result.diagnostics)
            _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
            with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
                await api.run_paired_bird(
                    plan, run_arm=driver, instrument=_instrument(api),
                    policy_identity="fixture", num_rollouts=1)
        finally:
            asyncio.create_task, api._mark_terminal = original_create, original_mark

    asyncio.run(scenario())
    print("REVIEW03_PRESTART_TERMINATED_STICKY_VOID")


@pytest.mark.parametrize("caller_cancel", [False, True])
def test_b_review03_prestart_owner_cancel_terminates_under_process_watchdog(tmp_path, caller_cancel):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    code = (
        "import socket, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve()\n"
        "sys.path.insert(0, str(root))\n"
        "attempts = []\n"
        "def deny(*args, **kwargs):\n"
        "    attempts.append('network')\n"
        "    raise AssertionError('OFFLINE_WATCHDOG_NETWORK_ATTEMPT')\n"
        "socket.getaddrinfo = deny\n"
        "socket.create_connection = deny\n"
        "socket.socket.connect = deny\n"
        "socket.socket.connect_ex = deny\n"
        "socket.socket.sendto = deny\n"
        "socket.gethostbyname = deny\n"
        "socket.gethostbyname_ex = deny\n"
        "import bench.test_paired_bird as target\n"
        "assert Path(target.__file__).resolve() == root / 'bench/test_paired_bird.py'\n"
        "assert Path(target._api().__file__).resolve() == root / 'bench/paired_bird.py'\n"
        "target._review03_prestart_cancel_child(Path(sys.argv[2]), sys.argv[3] == 'true')\n"
        "assert not attempts, 'WATCHDOG_CHILD_ATTEMPTED_NETWORK'\n"
        "print('REVIEW04_ACTUAL_CHECKOUT', root)\n"
        "print('REVIEW04_NETWORK_ATTEMPTS=0')\n"
    )
    try:
        child = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(root), str(tmp_path / "child"),
             "true" if caller_cancel else "false"],
            cwd=root,
            capture_output=True, text=True, timeout=4)
    except subprocess.TimeoutExpired:
        pytest.fail("PRESTART_CANCEL_BUSY_LOOP_EXCEEDED_4S_PROCESS_WATCHDOG")
    assert child.returncode == 0, child.stdout + child.stderr
    assert "REVIEW03_PRESTART_TERMINATED_STICKY_VOID" in child.stdout
    assert f"REVIEW04_ACTUAL_CHECKOUT {root}" in child.stdout
    assert "REVIEW04_NETWORK_ATTEMPTS=0" in child.stdout


def test_b_review03_already_pending_caller_cancel_is_not_owner_termination(tmp_path, monkeypatch):
    import sys

    api = _api()
    plan = _plan(tmp_path, api)
    original_mark = api._mark_terminal

    async def scenario():
        caller, calls, observed = asyncio.current_task(), [], []

        def observe_terminal(actual_plan, diagnostic):
            exc = sys.exception()
            if (asyncio.current_task() is caller
                    and isinstance(exc, asyncio.CancelledError)):
                observed.append(exc)
            original_mark(actual_plan, diagnostic)

        async def driver(request):
            calls.append(request.arm)
            yield _outcome(api, request, request.tasks[0])
            yield object()

        monkeypatch.setattr(api, "_mark_terminal", observe_terminal)
        caller.cancel("PRIVATE_ALREADY_PENDING_CALLER_CANCEL")
        try:
            await api.run_paired_bird(
                plan, run_arm=driver, instrument=_instrument(api),
                policy_identity="fixture", num_rollouts=1)
        except asyncio.CancelledError as exc:
            assert observed and exc is observed[0]
            assert exc.args == ("PRIVATE_ALREADY_PENDING_CALLER_CANCEL",)
            result = exc.paired_bird_result
            _assert_void(result)
            _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
            assert "ptc" not in calls
        else:
            pytest.fail("PENDING_CALLER_CANCEL_MISCLASSIFIED_AS_OWNER_TERMINATION")

    asyncio.run(scenario())
