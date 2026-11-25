"""Declared UNIT resources for retained SDK protocol bookkeeping.

Events below coordinate Python tasks only. They are not native ACKs, public
OwnedSqlInvocation completions, association authority, or SDK integration proof.
Existing real inert factory coverage lives in test_sql_owned_program.py.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
from contextlib import asynccontextmanager

import pytest


def _module():
    # Resolve only from test bodies: missing implementation is a call-phase RED.
    assert importlib.util.find_spec("cotrain_owned_sql") is not None, (
        "retained owned SQL SDK module missing")
    module = importlib.import_module("cotrain_owned_sql")
    for name in ("_ProgramLease", "_CloseSet"):
        assert callable(getattr(module, name, None)), name + " missing"
    return module


@pytest.fixture
def no_native(monkeypatch):
    # Reuse the first-party guard, but never import its dependency tree during
    # collection or before the missing-module assertion in a test body.
    from ptc.test_sql_owned_program import no_native as existing_guard
    yield from existing_guard.__wrapped__(monkeypatch)


def _unit(request):
    module = _module()
    request.getfixturevalue("no_native")
    return module


def _run(coroutine):
    # Sole deadline: finite test safety, never a synthetic cleanup deadline.
    async def bounded():
        return await asyncio.wait_for(coroutine, 3.0)
    return asyncio.run(bounded())


async def _turn():
    # Scheduler checkpoint without timing/sleep-based ordering assertions.
    future = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


class _UnitResource:
    """Public protocol recorder, deliberately no invocation/ACK/job internals."""

    def __init__(self, *, held_run=False, held_close=False,
                 run_error=None, close_error=None, close_result=None):
        self.validations = []
        self.runs = []
        self.run_error = run_error
        self.close_error = close_error
        self.close_result = close_result
        self.run_entered = asyncio.Event()
        self.run_release = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_finished = asyncio.Event()
        self.close_tasks = []
        self.run_cancel = None
        if not held_run:
            self.run_release.set()
        if not held_close:
            self.close_release.set()

    def validate_program_timeout(self, timeout):
        self.validations.append(timeout)

    async def run_program(self, code, *, timeout):
        self.runs.append((code, timeout))
        self.run_entered.set()
        try:
            await self.run_release.wait()
        except asyncio.CancelledError as exc:
            self.run_cancel = exc
            raise
        if self.run_error is not None:
            raise self.run_error
        return "unit protocol observation"

    async def aclose(self):
        self.close_tasks.append(asyncio.current_task())
        self.close_entered.set()
        await self.close_release.wait()
        self.close_finished.set()
        if self.close_error is not None:
            raise self.close_error
        return self.close_result


class _EqualUnitResource(_UnitResource):
    def __eq__(self, other):
        return isinstance(other, _EqualUnitResource)

    __hash__ = None


@asynccontextmanager
async def _resources(*resources):
    # Every failure path releases ALL holds and observes all newly created
    # actual tasks, including a close task not yet entered at assertion time.
    before = asyncio.all_tasks()
    try:
        yield
    finally:
        for resource in resources:
            resource.run_release.set()
            resource.close_release.set()
        current = asyncio.current_task()
        while True:
            pending = [task for task in asyncio.all_tasks()
                       if task not in before and task is not current]
            if not pending:
                break
            await asyncio.gather(*pending, return_exceptions=True)
        # all_tasks excludes completed tasks; consume recorded close failures.
        await asyncio.gather(
            *(task for resource in resources for task in resource.close_tasks),
            return_exceptions=True)


def _checked(counter):
    def check():
        counter.append("scope")
    return check


@pytest.mark.parametrize("timeout", (5, 5.0), ids=("int", "float"))
def test_timeout_validator_is_original_synchronous_exact_delegation(
        request, timeout):
    module = _unit(request)
    actual = _UnitResource()
    original = actual.validate_program_timeout
    lease = module._ProgramLease(actual, lambda: None)
    assert lease.validate_program_timeout(timeout) is None
    assert actual.validate_program_timeout == original
    assert len(actual.validations) == 1
    assert actual.validations[0] is timeout
    assert actual.runs == [] and actual.close_tasks == []


def test_timeout_validator_preserves_original_exception(request):
    module = _unit(request)
    actual = _UnitResource()
    failure = ValueError("declared unit timeout refusal")

    def validate(timeout):
        actual.validations.append(timeout)
        raise failure

    actual.validate_program_timeout = validate
    lease = module._ProgramLease(actual, lambda: None)
    with pytest.raises(ValueError) as caught:
        lease.validate_program_timeout(5)
    assert caught.value is failure
    assert actual.validate_program_timeout is validate
    assert actual.validations == [5]


def test_program_forwards_original_methods_code_timeout_and_sequential_calls(
        request):
    module = _unit(request)

    async def case():
        actual = _UnitResource()
        methods = (actual.run_program, actual.aclose)
        checks = []
        lease = module._ProgramLease(actual, _checked(checks))
        code = "declared unit text, not executed"
        timeout = 5.0
        async with _resources(actual):
            for _ in range(2):
                assert await lease.run_program(code, timeout=timeout) == (
                    "unit protocol observation")
            assert len(actual.runs) == 2 and checks == ["scope", "scope"]
            assert all(c is code and t is timeout for c, t in actual.runs)
            assert (actual.run_program, actual.aclose) == methods
            assert await lease.aclose() is None
            assert len(actual.close_tasks) == 1

    _run(case())


def test_overlapping_program_refuses_before_second_delegate(request):
    module = _unit(request)

    async def case():
        actual = _UnitResource(held_run=True)
        lease = module._ProgramLease(actual, lambda: None)
        async with _resources(actual):
            first = asyncio.create_task(lease.run_program("first", timeout=5))
            await actual.run_entered.wait()
            with pytest.raises(RuntimeError):
                await lease.run_program("overlap", timeout=5)
            assert actual.runs == [("first", 5)]
            assert not first.done()
            actual.run_release.set()
            await first
            await lease.aclose()

    _run(case())


def test_scope_guard_runs_before_delegate_and_refusal_dispatches_zero(request):
    module = _unit(request)

    async def case():
        actual = _UnitResource()
        checks = []

        def refuse():
            checks.append("refused")
            raise RuntimeError("declared unit revoked scope")

        lease = module._ProgramLease(actual, refuse)
        async with _resources(actual):
            with pytest.raises(RuntimeError):
                await lease.run_program("forbidden", timeout=5)
            assert checks == ["refused"] and actual.runs == []
            await lease.aclose()
            assert len(actual.close_tasks) == 1

    _run(case())


def test_program_failure_is_sticky_even_after_actual_runner_recovers(request):
    module = _unit(request)

    async def case():
        failure = RuntimeError("declared unit execution failure")
        actual = _UnitResource(run_error=failure)
        lease = module._ProgramLease(actual, lambda: None)
        async with _resources(actual):
            with pytest.raises(RuntimeError):
                await lease.run_program("first", timeout=5)
            actual.run_error = None
            with pytest.raises(RuntimeError):
                await lease.run_program("must not replay", timeout=5)
            assert actual.runs == [("first", 5)]
            await lease.aclose()

    _run(case())


def test_program_actual_cancellation_is_sticky_and_preserves_exception(request):
    module = _unit(request)

    async def case():
        actual = _UnitResource(held_run=True)
        lease = module._ProgramLease(actual, lambda: None)
        async with _resources(actual):
            caller = asyncio.create_task(lease.run_program("first", timeout=5))
            await actual.run_entered.wait()
            assert caller.cancel("unit body cancellation")
            with pytest.raises(asyncio.CancelledError) as caught:
                await caller
            assert caught.value is actual.run_cancel
            actual.run_release.set()
            with pytest.raises(RuntimeError):
                await lease.run_program("after cancellation", timeout=5)
            assert actual.runs == [("first", 5)]
            await lease.aclose()

    _run(case())


def test_harness_scope_and_concurrent_proxy_callers_share_one_actual_close(
        request):
    module = _unit(request)
    from ptc.harness import _close_program_runner

    async def case():
        actual = _UnitResource(held_close=True)
        lease = module._ProgramLease(actual, lambda: None)
        closes = module._CloseSet()
        closes.retain(lease)
        async with _resources(actual):
            retained = lease.start_close()
            assert isinstance(retained, asyncio.Task)
            assert lease.start_close() is retained
            harness = asyncio.create_task(_close_program_runner(lease))
            scope = asyncio.create_task(closes.join_all())
            sibling = asyncio.create_task(lease.aclose())
            await actual.close_entered.wait()
            await _turn()
            assert actual.close_tasks == [retained]
            assert not any(t.done() for t in (harness, scope, sibling))
            assert lease.start_close() is retained
            actual.close_release.set()
            assert await asyncio.gather(harness, scope, sibling) == [None] * 3
            assert await lease.aclose() is None
            assert lease.start_close() is retained
            assert len(actual.close_tasks) == 1

    _run(case())


@pytest.mark.parametrize("close_fails", (False, True), ids=("cancel", "failure"))
def test_three_close_cancel_requests_drain_and_first_cancel_or_failure_wins(
        request, monkeypatch, close_fails):
    module = _unit(request)

    async def case():
        actual = _UnitResource(
            held_close=True,
            close_error=RuntimeError("unit close failure") if close_fails else None)
        lease = module._ProgramLease(actual, lambda: None)
        delivered = asyncio.Queue()
        original = asyncio.shield

        async def observed_shield(awaitable):
            try:
                return await original(awaitable)
            except asyncio.CancelledError as exc:
                delivered.put_nowait(exc)
                raise

        # This observes delivered Python interruptions, NOT native ACKs.
        monkeypatch.setattr(asyncio, "shield", observed_shield)
        async with _resources(actual):
            caller = asyncio.create_task(lease.aclose())
            await actual.close_entered.wait()
            first = None
            for index in range(3):
                assert caller.cancel("unit close request " + str(index))
                interruption = await delivered.get()
                if first is None:
                    first = interruption
                await _turn()
                assert not caller.done(), "caller escaped held actual close"
                assert len(actual.close_tasks) == 1
                assert not actual.close_tasks[0].cancelled()
                assert not actual.close_finished.is_set()
            actual.close_release.set()
            if close_fails:
                with pytest.raises(RuntimeError):
                    await caller
            else:
                with pytest.raises(asyncio.CancelledError) as caught:
                    await caller
                assert caught.value is first
            assert actual.close_finished.is_set()
            assert actual.close_tasks[0].done()

    _run(case())


@pytest.mark.parametrize("completed", (False, True), ids=("closing", "closed"))
def test_program_rejects_new_execution_after_close_starts(request, completed):
    module = _unit(request)

    async def case():
        actual = _UnitResource(held_close=True)
        lease = module._ProgramLease(actual, lambda: None)
        async with _resources(actual):
            close = lease.start_close()
            await actual.close_entered.wait()
            if completed:
                actual.close_release.set()
                await lease.aclose()
            with pytest.raises(RuntimeError):
                await lease.run_program("after close", timeout=5)
            assert actual.runs == [] and lease.start_close() is close
            actual.close_release.set()
            await lease.aclose()

    _run(case())


@pytest.mark.parametrize("kind", ("non-none", "exception"))
def test_program_invalid_close_latches_failure_without_replay(request, kind):
    module = _unit(request)

    async def case():
        actual = _UnitResource(
            close_result="not public None" if kind == "non-none" else None,
            close_error=ValueError("unit close refusal")
            if kind == "exception" else None)
        lease = module._ProgramLease(actual, lambda: None)
        async with _resources(actual):
            retained = lease.start_close()
            for _ in range(2):
                with pytest.raises((RuntimeError, ValueError)):
                    await lease.aclose()
                assert lease.start_close() is retained
            with pytest.raises(RuntimeError):
                await lease.run_program("after failed close", timeout=5)
            assert actual.runs == [] and actual.close_tasks == [retained]

    _run(case())


def test_close_set_repeat_retention_and_start_reuse_exact_task(request):
    module = _unit(request)

    async def case():
        actual = _UnitResource()
        closes = module._CloseSet()
        async with _resources(actual):
            closes.retain(actual)
            closes.retain(actual)
            task = closes.start(actual)
            assert isinstance(task, asyncio.Task)
            assert closes.start(actual) is task
            assert closes.start_all() == (task,)
            assert await closes.join_all() is None
            assert closes.start(actual) is task
            assert actual.close_tasks == [task]

    _run(case())


def test_close_set_retains_equal_nonidentical_unhashable_resources(request):
    module = _unit(request)

    async def case():
        first, second = _EqualUnitResource(), _EqualUnitResource()
        assert first == second and first is not second
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            tasks = closes.start_all()
            assert len(tasks) == 2 and tasks[0] is not tasks[1]
            assert closes.start(first) in tasks
            assert closes.start(second) in tasks
            assert closes.start(first) is not closes.start(second)
            await closes.join_all()
            assert len(first.close_tasks) == len(second.close_tasks) == 1

    _run(case())


def test_close_set_start_all_creates_every_task_before_any_await(request):
    module = _unit(request)

    async def case():
        first = _UnitResource(held_close=True)
        second = _UnitResource(held_close=True)
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            tasks = closes.start_all()
            assert len(tasks) == 2
            assert all(isinstance(task, asyncio.Task) for task in tasks)
            assert tasks[0] is not tasks[1]
            assert all(not task.done() for task in tasks)
            assert not first.close_entered.is_set()
            assert not second.close_entered.is_set()
            await first.close_entered.wait()
            await second.close_entered.wait()
            assert first.close_tasks[0] in tasks
            assert second.close_tasks[0] in tasks
            assert not first.close_finished.is_set()
            assert not second.close_finished.is_set()
            first.close_release.set()
            second.close_release.set()
            await closes.join_all()

    _run(case())


def test_close_set_unknown_first_never_prevents_second_actual_body_entry(
        request):
    module = _unit(request)

    async def case():
        first = _UnitResource(held_close=True)
        second = _UnitResource(held_close=True)
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            caller = asyncio.create_task(closes.join_all())
            await first.close_entered.wait()
            await second.close_entered.wait()
            assert not first.close_release.is_set()
            assert not first.close_finished.is_set()
            assert not caller.done()
            second.close_release.set()
            await second.close_finished.wait()
            await _turn()
            assert not caller.done(), "unknown first close became success"
            first.close_release.set()
            assert await caller is None

    _run(case())


@pytest.mark.parametrize("kind", ("exception", "non-none"))
def test_close_set_first_failure_still_drains_held_second_before_reporting(
        request, kind):
    module = _unit(request)

    async def case():
        first = _UnitResource(
            close_error=ValueError("unit first close failure")
            if kind == "exception" else None,
            close_result="invalid close" if kind == "non-none" else None)
        second = _UnitResource(held_close=True)
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            caller = asyncio.create_task(closes.join_all())
            await first.close_finished.wait()
            await second.close_entered.wait()
            await _turn()
            assert not caller.done(), "failure detached another retained close"
            assert not second.close_finished.is_set()
            second.close_release.set()
            with pytest.raises((RuntimeError, ValueError)):
                await caller
            assert second.close_finished.is_set()
            tasks = closes.start_all()
            assert len(tasks) == 2 and all(task.done() for task in tasks)
            with pytest.raises((RuntimeError, ValueError)):
                await closes.join_all()
            assert closes.start_all() == tasks
            assert len(first.close_tasks) == len(second.close_tasks) == 1

    _run(case())


def test_close_set_repeated_concurrent_joiners_share_actual_tasks(request):
    module = _unit(request)

    async def case():
        first = _UnitResource(held_close=True)
        second = _UnitResource(held_close=True)
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            callers = [asyncio.create_task(closes.join_all()) for _ in range(3)]
            await first.close_entered.wait()
            await second.close_entered.wait()
            tasks = closes.start_all()
            await _turn()
            assert all(not caller.done() for caller in callers)
            assert first.close_tasks == [closes.start(first)]
            assert second.close_tasks == [closes.start(second)]
            first.close_release.set()
            second.close_release.set()
            assert await asyncio.gather(*callers) == [None] * 3
            assert await closes.join_all() is None
            assert closes.start_all() == tasks
            assert len(first.close_tasks) == len(second.close_tasks) == 1

    _run(case())


def test_close_set_cancelling_joiner_never_cancels_retained_closes(request):
    module = _unit(request)

    async def case():
        first = _UnitResource(held_close=True)
        second = _UnitResource(held_close=True)
        closes = module._CloseSet()
        async with _resources(first, second):
            closes.retain(first)
            closes.retain(second)
            caller = asyncio.create_task(closes.join_all())
            await first.close_entered.wait()
            await second.close_entered.wait()
            tasks = closes.start_all()
            assert caller.cancel("unit join cancellation request")
            await _turn()
            assert not caller.done()
            assert all(not task.done() for task in tasks)
            first.close_release.set()
            second.close_release.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert all(task.done() and not task.cancelled() for task in tasks)
            assert await closes.join_all() is None
            assert closes.start_all() == tasks
            assert len(first.close_tasks) == len(second.close_tasks) == 1

    _run(case())


def test_close_set_seals_new_resources_but_allows_existing_identity(request):
    module = _unit(request)

    async def case():
        actual, late = _UnitResource(), _UnitResource()
        closes = module._CloseSet()
        async with _resources(actual, late):
            closes.retain(actual)
            task, = closes.start_all()
            closes.retain(actual)
            assert closes.start(actual) is task
            with pytest.raises(RuntimeError):
                closes.retain(late)
            assert late.close_tasks == []
            assert closes.start_all() == (task,)
            await closes.join_all()
            assert late.close_tasks == []

    _run(case())


def test_close_set_empty_join_is_none_and_seals_new_resources(request):
    module = _unit(request)

    async def case():
        closes = module._CloseSet()
        actual = _UnitResource()
        assert await closes.join_all() is None
        assert closes.start_all() == ()
        with pytest.raises(RuntimeError):
            closes.retain(actual)
        assert actual.close_tasks == []

    _run(case())
