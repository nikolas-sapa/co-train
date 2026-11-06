import asyncio
import contextvars
import sys
from dataclasses import FrozenInstanceError

import pytest

import bench.paired_bird as api
from bench.prepare import ValidatedDraw
from bench.task import SqlTask
from ptc.sql_arms import Budget


SYNTHETIC_CREDENTIALS = (
    "postgresql://test-user:test-password@example.invalid/db",
    "token=test-only-token",
    "Authorization: Bearer test-only-bearer",
)


def _credential_error(label):
    return f"PRIVATE_{label} " + " ".join(SYNTHETIC_CREDENTIALS)


def _assert_no_synthetic_credentials(diagnostics):
    for credential in SYNTHETIC_CREDENTIALS:
        assert all(credential not in item for item in diagnostics)


def _plan(monkeypatch):
    tasks = tuple(
        SqlTask(
            name=f"test-only-task-{index}",
            question="test-only question",
            evidence="",
            gold_sql="SELECT 1",
            db_id=f"test-only-db-{index}",
            db_path="test-only-memory-db",
            tier="simple",
            tier_source="annotated",
            shape=f"test-only-shape-{index}",
            coarse_shape="test-only-shape",
            source="fixture",
        )
        for index in (1, 2)
    )
    draw = ValidatedDraw(
        planned=tasks,
        eligible=tasks,
        exclusions=(),
        draw_sha256="test-only-draw-digest",
        supplement_sha256="test-only-supplement-digest",
        fixture=True,
        timeout_s=30.0,
        max_rows=500_000,
        comparison="set",
        databases=(),
    )
    monkeypatch.setattr(
        api.prepare, "load_validated_draw", lambda *args, **kwargs: draw)
    return api.prepare_paired_bird(
        "test-only-root",
        "test-only-draw",
        "test-only-supplement",
        expected_draw_sha256="test-only-draw-digest",
        expected_supplement_sha256="test-only-supplement-digest",
        fixture=True,
    )


def _instrument():
    return api.Instrument(
        identity="test-only-instrument",
        budget=Budget(
            max_turns=8,
            max_retries=0,
            retry_on=(),
            rollout_timeout=600.0,
            program_timeout=5.0,
        ),
        action_max_rows=2,
        query_timeout_s=30.0,
        sampling_identity="test-only-sampling",
    )


def _outcome(request, task):
    return api.TaskOutcome(
        plan_id=request.plan_id,
        arm=request.arm,
        task_id=task.name,
        completed=True,
        valid=True,
        status="match",
        metrics=(api.Metric("execution_accuracy", 1.0),),
        output_ref=f"test-only-output:{request.arm}:{task.name}",
    )


def _run(plan, driver):
    return asyncio.run(api.run_paired_bird(
        plan,
        run_arm=driver,
        instrument=_instrument(),
        policy_identity="test-only-policy",
        num_rollouts=1,
    ))


def _assert_void(result):
    assert result.status == "void", "VOID_STATUS_BECAME_COMPLETE"
    assert result.comparison is None, "VOID_BECAME_PAIRED_ESTIMATE"
    assert result.diagnostics
    _assert_no_synthetic_credentials(result.diagnostics)


def test_factory_failure_is_consumed_and_private(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched = []

    def driver(request):
        dispatched.append(request.arm)
        raise RuntimeError(_credential_error("FACTORY_SENTINEL"))

    result = _run(plan, driver)
    _assert_void(result)
    assert dispatched == ["bash"]
    assert result.arm_a == result.arm_b == ()
    assert any("bash:driver_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(plan, driver)
    assert dispatched == ["bash"]


def test_aiter_startup_failure_is_consumed_and_private(monkeypatch):
    plan = _plan(monkeypatch)
    factory_calls, startup_calls, dispatched = [], [], []

    class StartupFault:
        def __aiter__(self):
            startup_calls.append(asyncio.current_task())
            raise RuntimeError(_credential_error("AITER_SENTINEL"))

    def driver(request):
        dispatched.append(request.arm)
        factory_calls.append(asyncio.current_task())
        return StartupFault()

    result = _run(plan, driver)
    _assert_void(result)
    assert dispatched == ["bash"]
    assert len(factory_calls) == len(startup_calls) == 1
    assert result.arm_a == result.arm_b == ()
    assert any("bash:driver_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(plan, driver)
    assert dispatched == ["bash"]


def test_factory_cancellation_preserves_original_identity(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched = []
    driver_cancel = asyncio.CancelledError("PRIVATE_CREDENTIAL_FACTORY_CANCEL")

    def driver(request):
        dispatched.append(request.arm)
        raise driver_cancel

    with pytest.raises(asyncio.CancelledError) as caught:
        _run(plan, driver)
    assert caught.value is driver_cancel
    result = caught.value.paired_bird_result
    _assert_void(result)
    assert result.arm_a == result.arm_b == ()
    assert dispatched == ["bash"]
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(plan, driver)
    assert dispatched == ["bash"]


def test_second_aiter_failure_closes_owned_iterator(monkeypatch):
    plan = _plan(monkeypatch)
    context = contextvars.ContextVar("paired_bird_second_aiter", default="unset")
    context_token = context.set("caller-context")
    lifecycle = {}
    dispatched = []

    class SecondAiterFault:
        def __init__(self):
            self.aiter_calls = 0

        def __aiter__(self):
            self.aiter_calls += 1
            if self.aiter_calls == 1:
                return self
            raise RuntimeError(_credential_error("SECOND_AITER"))

        async def __anext__(self):
            raise AssertionError("ITERATION_STARTED_AFTER_AITER_FAILURE")

        async def aclose(self):
            lifecycle["close_task"] = asyncio.current_task()
            lifecycle["close_context"] = context.get()

    iterator = SecondAiterFault()

    def driver(request):
        dispatched.append(request.arm)
        lifecycle["factory_task"] = asyncio.current_task()
        context.set("owned-context")
        lifecycle["factory_context"] = context.get()
        return iterator

    try:
        result = _run(plan, driver)
        assert context.get() == "caller-context"
    finally:
        context.reset(context_token)

    _assert_void(result)
    assert iterator.aiter_calls == 2
    assert dispatched == ["bash"]
    assert lifecycle["factory_task"] is lifecycle["close_task"]
    assert lifecycle["factory_context"] == lifecycle["close_context"] == "owned-context"
    assert result.arm_a == result.arm_b == ()


def test_iteration_and_close_failures_retain_frozen_evidence(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched, yielded, closed = [], [], []

    class FailingRows:
        def __init__(self, request):
            self.request = request
            self.yielded = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.yielded:
                self.yielded = True
                row = _outcome(self.request, self.request.tasks[0])
                yielded.append(row)
                return row
            raise RuntimeError(_credential_error("ITERATION"))

        async def aclose(self):
            closed.append(self.request.arm)
            raise RuntimeError(_credential_error("CLOSE"))

    def driver(request):
        dispatched.append(request.arm)
        return FailingRows(request)

    result = _run(plan, driver)
    _assert_void(result)
    assert dispatched == closed == ["bash"]
    assert len(yielded) == len(result.arm_a) == 1
    assert result.arm_a[0] is yielded[0]
    assert result.arm_b == ()
    assert any("bash:driver_failure" in item for item in result.diagnostics)
    assert any("bash:cleanup_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "status", "complete")
    with pytest.raises(FrozenInstanceError):
        setattr(result.arm_a[0], "completed", False)
    with pytest.raises(FrozenInstanceError):
        setattr(result.arm_a[0].metrics[0], "score", 0.0)


def test_iteration_failure_then_close_cancellation(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched, yielded, closed = [], [], []
    close_cancel = asyncio.CancelledError("PRIVATE_CREDENTIAL_CLOSE_CANCEL")

    class FailingRows:
        def __init__(self, request):
            self.request = request
            self.yielded = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.yielded:
                self.yielded = True
                row = _outcome(self.request, self.request.tasks[0])
                yielded.append(row)
                return row
            raise RuntimeError(_credential_error("ITERATION"))

        async def aclose(self):
            closed.append(self.request.arm)
            raise close_cancel

    def driver(request):
        dispatched.append(request.arm)
        return FailingRows(request)

    with pytest.raises(asyncio.CancelledError) as caught:
        _run(plan, driver)
    assert caught.value is close_cancel
    result = caught.value.paired_bird_result
    _assert_void(result)
    assert dispatched == closed == ["bash"]
    assert len(yielded) == len(result.arm_a) == 1
    assert result.arm_a[0] is yielded[0]
    assert result.arm_b == ()
    assert any("bash:driver_failure" in item for item in result.diagnostics)
    assert any("bash:cleanup_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(plan, driver)
    assert dispatched == ["bash"]


class _CompleteRows:
    def __init__(self, request, observed, closed, close_failure=None):
        self.request = request
        self.observed = observed
        self.closed = closed
        self.close_failure = close_failure
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index == len(self.request.tasks):
            raise StopAsyncIteration
        task = self.request.tasks[self.index]
        self.index += 1
        row = _outcome(self.request, task)
        self.observed[self.request.arm].append(row)
        return row

    async def aclose(self):
        self.closed.append(self.request.arm)
        if self.close_failure is not None:
            raise self.close_failure


def test_second_arm_complete_rows_close_failure_stays_void(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched, closed = [], []
    observed = {"bash": [], "ptc": []}
    close_failure = RuntimeError(_credential_error("PTC_CLOSE"))

    def driver(request):
        dispatched.append(request.arm)
        failure = close_failure if request.arm == "ptc" else None
        return _CompleteRows(request, observed, closed, failure)

    result = _run(plan, driver)
    _assert_void(result)
    assert dispatched == closed == ["bash", "ptc"]
    assert len(result.arm_a) == len(result.arm_b) == 2
    assert all(actual is expected for actual, expected in
               zip(result.arm_a, observed["bash"], strict=True))
    assert all(actual is expected for actual, expected in
               zip(result.arm_b, observed["ptc"], strict=True))
    assert any("ptc:cleanup_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))


def test_second_arm_complete_rows_close_cancellation_stays_void(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched, closed = [], []
    observed = {"bash": [], "ptc": []}
    close_cancel = asyncio.CancelledError("PRIVATE_CREDENTIAL_PTC_CLOSE_CANCEL")

    def driver(request):
        dispatched.append(request.arm)
        failure = close_cancel if request.arm == "ptc" else None
        return _CompleteRows(request, observed, closed, failure)

    with pytest.raises(asyncio.CancelledError) as caught:
        _run(plan, driver)
    assert caught.value is close_cancel
    result = caught.value.paired_bird_result
    _assert_void(result)
    assert dispatched == closed == ["bash", "ptc"]
    assert len(result.arm_a) == len(result.arm_b) == 2
    assert all(actual is expected for actual, expected in
               zip(result.arm_a, observed["bash"], strict=True))
    assert all(actual is expected for actual, expected in
               zip(result.arm_b, observed["ptc"], strict=True))
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "status", "complete")
    _assert_void(api.adjudicate_paired_bird(plan, result.arm_a, result.arm_b))
    with pytest.raises(api.PairedBirdError, match="consumed|single.use"):
        _run(plan, driver)
    assert dispatched == ["bash", "ptc"]


def test_concurrent_plans_keep_context_and_terminal_state_independent(monkeypatch):
    failing_plan = _plan(monkeypatch)
    healthy_plan = _plan(monkeypatch)
    labels = {
        failing_plan.plan_id: "failing",
        healthy_plan.plan_id: "healthy",
    }

    async def scenario():
        context = contextvars.ContextVar("paired_bird_concurrent", default="unset")
        context.set("parent-context")
        both_bash_started = asyncio.Event()
        bash_factory_count = 0
        records = {}
        requests = []
        observed = {}
        resets = []

        class Owner:
            def __init__(self, request, label, key, token):
                self.request = request
                self.label = label
                self.key = key
                self.token = token
                self.index = 0

            def _record(self, stage):
                records[self.key][stage].append(
                    (asyncio.current_task(), context.get()))

            def __aiter__(self):
                self._record("aiter")
                return self

            async def __anext__(self):
                self._record("advance")
                if self.request.arm == "bash" and self.index == 0:
                    await asyncio.wait_for(both_bash_started.wait(), 1)
                if self.label == "failing" and self.index == 1:
                    raise RuntimeError(_credential_error("CONCURRENT_ITERATION"))
                if self.index == len(self.request.tasks):
                    raise StopAsyncIteration
                task = self.request.tasks[self.index]
                self.index += 1
                row = _outcome(self.request, task)
                observed[self.key].append(row)
                return row

            async def aclose(self):
                self._record("close")
                context.reset(self.token)
                resets.append((self.key, context.get()))

        def driver(request):
            nonlocal bash_factory_count
            label = labels[request.plan_id]
            key = (label, request.arm)
            requests.append(key)
            assert context.get() == f"caller:{label}"
            token = context.set(f"owner:{label}:{request.arm}")
            records[key] = {
                "factory": [(asyncio.current_task(), context.get())],
                "aiter": [],
                "advance": [],
                "close": [],
            }
            observed[key] = []
            if request.arm == "bash":
                bash_factory_count += 1
                if bash_factory_count == 2:
                    both_bash_started.set()
            return Owner(request, label, key, token)

        async def invoke(plan, label):
            context.set(f"caller:{label}")
            result = await api.run_paired_bird(
                plan,
                run_arm=driver,
                instrument=_instrument(),
                policy_identity="test-only-policy",
                num_rollouts=1,
            )
            return result, context.get()

        failing_task = asyncio.create_task(invoke(failing_plan, "failing"))
        healthy_task = asyncio.create_task(invoke(healthy_plan, "healthy"))
        (failing_result, failing_context), (healthy_result, healthy_context) = (
            await asyncio.wait_for(
                asyncio.gather(failing_task, healthy_task), 1))
        assert context.get() == "parent-context"
        assert len(resets) == 3
        assert set(resets) == {
            (("failing", "bash"), "caller:failing"),
            (("healthy", "bash"), "caller:healthy"),
            (("healthy", "ptc"), "caller:healthy"),
        }
        return (
            failing_result,
            failing_context,
            healthy_result,
            healthy_context,
            records,
            requests,
            observed,
        )

    (
        failing_result,
        failing_context,
        healthy_result,
        healthy_context,
        records,
        requests,
        observed,
    ) = asyncio.run(scenario())
    _assert_void(failing_result)
    assert failing_context == "caller:failing"
    assert len(failing_result.arm_a) == 1 and failing_result.arm_b == ()
    assert any("bash:driver_failure" in item for item in failing_result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in failing_result.diagnostics)
    assert healthy_context == "caller:healthy"
    assert healthy_result.status == "complete"
    assert healthy_result.comparison.n == 2
    _assert_no_synthetic_credentials(healthy_result.diagnostics)
    assert [arm for label, arm in requests if label == "failing"] == ["bash"]
    assert [arm for label, arm in requests if label == "healthy"] == ["bash", "ptc"]
    assert set(records) == {
        ("failing", "bash"),
        ("healthy", "bash"),
        ("healthy", "ptc"),
    }
    assert len({value["factory"][0][0] for value in records.values()}) == 3
    for key, value in records.items():
        owner_task = value["factory"][0][0]
        assert len(value["factory"]) == len(value["close"]) == 1
        assert value["aiter"] and value["advance"]
        assert all(task is owner_task for stage in ("aiter", "advance", "close")
                   for task, _ in value[stage])
        expected_context = f"owner:{key[0]}:{key[1]}"
        assert all(context_value == expected_context
                   for stage in ("factory", "aiter", "advance", "close")
                   for _, context_value in value[stage])
    assert len(observed[("failing", "bash")]) == 1
    assert all(
        row.plan_id == (failing_plan.plan_id if label == "failing"
                        else healthy_plan.plan_id)
        and row.arm == arm
        for (label, arm), rows in observed.items()
        for row in rows
    )
    assert failing_result.arm_a[0] is observed[("failing", "bash")][0]
    assert healthy_result.arm_a == tuple(observed[("healthy", "bash")])
    assert healthy_result.arm_b == tuple(observed[("healthy", "ptc")])


def test_repeated_observer_cancel_joins_explicit_close_after_driver_cancel(monkeypatch):
    plan = _plan(monkeypatch)
    driver_cancel = asyncio.CancelledError("PRIVATE_DRIVER_CANCEL")
    original_mark = api._mark_terminal

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        first_seen, second_seen = asyncio.Event(), asyncio.Event()
        observer_cancels, owner_close_cancels = [], []
        dispatched, yielded, closed, close_tasks = [], [], [], []
        finished = []
        running = None

        def observe_terminal(actual_plan, diagnostic):
            exception = sys.exception()
            if (asyncio.current_task() is running
                    and diagnostic == "bash:cancelled"
                    and isinstance(exception, asyncio.CancelledError)):
                observer_cancels.append(exception)
                if exception.args == ("PRIVATE_FIRST_OBSERVER_CANCEL",):
                    first_seen.set()
                if exception.args == ("PRIVATE_SECOND_OBSERVER_CANCEL",):
                    second_seen.set()
            original_mark(actual_plan, diagnostic)

        class DriverRows:
            def __init__(self, request):
                self.request = request
                self.yielded = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.yielded:
                    raise driver_cancel
                self.yielded = True
                row = _outcome(self.request, self.request.tasks[0])
                yielded.append(row)
                return row

            async def aclose(self):
                closed.append(self.request.arm)
                close_tasks.append(asyncio.current_task())
                entered.set()
                try:
                    await release.wait()
                    finished.append(self.request.arm)
                except asyncio.CancelledError as exception:
                    owner_close_cancels.append(exception)
                    raise

        def driver(request):
            dispatched.append(request.arm)
            return DriverRows(request)

        monkeypatch.setattr(api, "_mark_terminal", observe_terminal)
        running = asyncio.create_task(api.run_paired_bird(
            plan,
            run_arm=driver,
            instrument=_instrument(),
            policy_identity="test-only-policy",
            num_rollouts=1,
        ))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            running.cancel("PRIVATE_FIRST_OBSERVER_CANCEL")
            await asyncio.wait_for(first_seen.wait(), 1)
            running.cancel("PRIVATE_SECOND_OBSERVER_CANCEL")
            await asyncio.wait_for(second_seen.wait(), 1)
            assert len(observer_cancels) == 2
            assert not running.done(), "CANCELLATION_RESOLVED_BEFORE_CLOSE_RELEASE"
            assert owner_close_cancels == []
            release.set()

            async def receive_cancellation():
                try:
                    await running
                except asyncio.CancelledError as exception:
                    return exception
                return None

            received = await asyncio.wait_for(receive_cancellation(), 1)
            assert received is observer_cancels[0]
            assert received is not observer_cancels[1]
            assert received is not driver_cancel
            result = received.paired_bird_result
            _assert_void(result)
            assert dispatched == closed == ["bash"]
            assert finished == ["bash"]
            assert len(close_tasks) == len(yielded) == len(result.arm_a) == 1
            assert close_tasks[0] is not running
            assert result.arm_a[0] is yielded[0]
            assert result.arm_b == ()
            assert all(
                "PRIVATE_" not in item for item in result.diagnostics)
        finally:
            release.set()
            try:
                await asyncio.wait_for(
                    asyncio.gather(running, return_exceptions=True), 1)
            except asyncio.TimeoutError:
                running.cancel("test-only-cleanup")
                await asyncio.wait_for(
                    asyncio.gather(running, return_exceptions=True), 1)

    asyncio.run(scenario())


def test_aclose_lookup_failure_is_private(monkeypatch):
    plan = _plan(monkeypatch)
    dispatched, yielded = [], []

    class LookupFailure:
        def __init__(self, request):
            self.request = request
            self.yielded = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.yielded:
                self.yielded = True
                row = _outcome(self.request, self.request.tasks[0])
                yielded.append(row)
                return row
            raise RuntimeError(_credential_error("ITERATION"))

        @property
        def aclose(self):
            raise RuntimeError(_credential_error("ACLOSE_LOOKUP"))

    def driver(request):
        dispatched.append(request.arm)
        return LookupFailure(request)

    result = _run(plan, driver)
    _assert_void(result)
    assert dispatched == ["bash"]
    assert len(yielded) == len(result.arm_a) == 1
    assert result.arm_a[0] is yielded[0]
    assert result.arm_b == ()
    assert any("bash:driver_failure" in item for item in result.diagnostics)
    assert any("bash:cleanup_failure" in item for item in result.diagnostics)
    assert all("PRIVATE_CREDENTIAL" not in item for item in result.diagnostics)
