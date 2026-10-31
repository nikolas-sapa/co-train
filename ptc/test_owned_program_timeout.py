"""Owned timeout preflight gates, specified before production implementation.

Unit owners are inert. The actual SDK case replaces the qualified fixture's
factory before evaluation: even a missing preflight cannot spawn program work.
This is hook-routing evidence, not native SQL or process cleanup qualification.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from ptc.harness import PTCHarness, PTCHarnessConfig, ProgramInfrastructureError
from ptc.runtime import Catalog, ProgramRejected
from ptc.test_owned_program_runner import (
    Policy, Runner, _assistant, _harness, _launch, _run,
)
from ptc.test_owned_program_runner_integration import (
    _config, _eval, _fixture, _policy, framework,  # noqa: F401
)


async def _refusal(harness, policy, owner):
    """Check the directed bypass failure before checking exception shape."""
    error = None
    try:
        await _launch(harness)
    except Exception as exc:
        error = exc
    assert policy.requests == [], (
        "intended pre-model refusal dispatched a policy request"
    )
    assert owner.calls == [], "preflight refusal dispatched a program"
    assert owner.closed == 1
    return error


def test_captured_timeout_identity_validated_once_before_two_programs():
    async def case():
        captured = float("8.125")
        config = PTCHarnessConfig().model_copy(
            update={"program_timeout": captured},
        )
        policy = Policy(_assistant("first"), _assistant("second"), _assistant(None))
        owner = Runner("one", "two")
        validations, factories = [], []

        def validate(timeout):
            assert policy.requests == owner.calls == []
            assert timeout is captured
            validations.append(timeout)
            harness.config.program_timeout = float("nan")
            return None

        owner.validate_program_timeout = validate

        def factory(data, catalog):
            factories.append((data, catalog))
            assert policy.requests == validations == []
            harness.config.program_timeout = 99.0
            return owner

        harness = PTCHarness(
            config, transport=policy.transport(), program_runner_factory=factory,
        )
        result = await _launch(harness)
        assert validations == [captured], "captured timeout was not validated once"
        assert result.exit_code == 0 and len(factories) == 1
        assert owner.calls == [("first", captured), ("second", captured)]
        assert all(timeout is captured for _, timeout in owner.calls)
        assert len(policy.requests) == 3 and owner.closed == 1
        assert [
            body["messages"][-1]["content"] for body in policy.bodies[1:]
        ] == ["one", "two"]
    _run(case())


@pytest.mark.parametrize("timeout", [5.0, 8.0])
def test_legacy_runner_without_hook_has_no_sql_only_timeout_restriction(timeout):
    async def case():
        owner = Runner("  legacy\n")
        assert not hasattr(owner, "validate_program_timeout")
        policy = Policy(_assistant("legacy"), _assistant(None))
        config = PTCHarnessConfig().model_copy(
            update={"program_timeout": timeout},
        )
        result = await _launch(PTCHarness(
            config, transport=policy.transport(),
            program_runner_factory=lambda data, catalog: owner,
        ))
        assert result.exit_code == 0
        assert owner.calls == [("legacy", timeout)] and owner.closed == 1
        assert len(policy.requests) == 2
        assert policy.bodies[1]["messages"][-1]["content"] == "  legacy\n"
    _run(case())


def test_synchronous_callable_object_hook_accepts_none():
    async def case():
        policy = Policy(_assistant("one"), _assistant(None))
        owner, validations = Runner("accepted"), []

        class Validator:
            def __call__(self, timeout):
                assert policy.requests == []
                validations.append(timeout)
                return None

        owner.validate_program_timeout = Validator()
        result = await _launch(_harness(policy, lambda data, catalog: owner))
        assert validations == [1.25]
        assert result.exit_code == 0 and len(policy.requests) == 2
        assert owner.calls == [("one", 1.25)] and owner.closed == 1
    _run(case())


@pytest.mark.parametrize("exception_type", [ValueError, ProgramRejected, RuntimeError])
def test_preflight_exception_is_fatal_not_tool_feedback(exception_type):
    async def case():
        policy = Policy(_assistant("must not run"), _assistant(None))
        owner, validations = Runner(), []

        def validate(timeout):
            validations.append(timeout)
            raise exception_type("timeout refused before model")

        owner.validate_program_timeout = validate
        error = await _refusal(
            _harness(policy, lambda data, catalog: owner), policy, owner,
        )
        assert validations == [1.25]
        assert isinstance(error, exception_type)
        assert str(error) == "timeout refused before model"
        assert policy.bodies == [], "preflight exception became model feedback"
    _run(case())


@pytest.mark.parametrize("kind", [
    "none", "noncallable", "async-function", "asyncgen-function", "async-object",
])
def test_malformed_validator_refuses_before_model_and_closes(kind):
    async def case():
        policy = Policy(_assistant("must not run"), _assistant(None))
        owner, bodies = Runner(), []

        async def async_validator(timeout):
            bodies.append(timeout)

        async def asyncgen_validator(timeout):
            bodies.append(timeout)
            yield None

        class AsyncValidator:
            async def __call__(self, timeout):
                bodies.append(timeout)

        owner.validate_program_timeout = {
            "none": None,
            "noncallable": 17,
            "async-function": async_validator,
            "asyncgen-function": asyncgen_validator,
            "async-object": AsyncValidator(),
        }[kind]
        error = await _refusal(
            _harness(policy, lambda data, catalog: owner), policy, owner,
        )
        assert isinstance(error, TypeError)
        assert bodies == [], "asynchronous validation body was executed"
    _run(case())


@pytest.mark.parametrize("kind", [
    "false", "zero", "value", "awaitable", "asyncgen", "coroutine",
])
def test_validator_result_requires_exact_none_without_driving_result(kind, recwarn):
    async def case():
        policy = Policy(_assistant("must not run"), _assistant(None))
        owner, validations, effects, results = Runner(), [], [], []

        class Awaitable:
            def __await__(self):
                effects.append("awaited")
                if False:
                    yield
                return None

            def cancel(self):
                effects.append("cancelled")

        async def coroutine():
            effects.append("coroutine body")

        async def asyncgen():
            effects.append("asyncgen body")
            yield None

        def validate(timeout):
            validations.append(timeout)
            if kind == "awaitable":
                result = Awaitable()
            elif kind == "asyncgen":
                result = asyncgen()
            elif kind == "coroutine":
                result = coroutine()
            else:
                result = {"false": False, "zero": 0, "value": "accepted"}[kind]
            results.append(result)
            return result

        owner.validate_program_timeout = validate
        try:
            error = await _refusal(
                _harness(policy, lambda data, catalog: owner), policy, owner,
            )
            assert validations == [1.25]
            assert isinstance(error, TypeError)
            assert effects == [], "invalid validation result was driven or cancelled"
            if kind == "coroutine":
                assert inspect.getcoroutinestate(results[0]) == inspect.CORO_CLOSED
            if kind == "asyncgen":
                assert results[0].ag_frame is not None
        finally:
            # Test owns these inert objects, including under a broken candidate.
            # Check production's close above, before this leak-safe teardown.
            for result in results:
                if inspect.iscoroutine(result):
                    result.close()
                elif inspect.isasyncgen(result):
                    await result.aclose()
    _run(case())
    assert not [warning for warning in recwarn
                if issubclass(warning.category, RuntimeWarning)]


def test_validator_property_lookup_failure_retains_one_close():
    async def case():
        policy, lookups = Policy(_assistant("must not run"), _assistant(None)), []

        class LookupFailure(Runner):
            @property
            def validate_program_timeout(self):
                lookups.append(True)
                raise RuntimeError("validator property failed")

        owner = LookupFailure()
        error = await _refusal(
            _harness(policy, lambda data, catalog: owner), policy, owner,
        )
        assert lookups == [True]
        assert isinstance(error, RuntimeError)
        assert str(error) == "validator property failed"
    _run(case())


@pytest.mark.parametrize("close_mode", ["raises", "non-none"])
def test_validation_failure_cannot_hide_fatal_cleanup(close_mode):
    async def case():
        policy = Policy(_assistant("must not run"), _assistant(None))
        validations = []

        class FailedClose(Runner):
            def validate_program_timeout(self, timeout):
                validations.append(timeout)
                raise ValueError("preflight refused")

            async def aclose(self):
                self.closed += 1
                if close_mode == "raises":
                    raise RuntimeError("retained cleanup failed")
                return False

        owner = FailedClose()
        error = await _refusal(
            _harness(policy, lambda data, catalog: owner), policy, owner,
        )
        assert validations == [1.25]
        assert isinstance(error, ProgramInfrastructureError)
        if close_mode == "raises":
            assert "cleanup failed" in str(error)
            assert isinstance(error.__cause__, RuntimeError)
        else:
            assert "acknowledge with None" in str(error)
    _run(case())


def test_three_caller_cancellations_cannot_detach_preflight_failure_close():
    async def case():
        policy = Policy(_assistant(None))
        validations = []

        class HeldClose(Runner):
            def __init__(self):
                super().__init__()
                self.closing = asyncio.Event()
                self.release = asyncio.Event()
                self.completed = asyncio.Event()
                self.close_task = None

            def validate_program_timeout(self, timeout):
                validations.append(timeout)
                raise ValueError("preflight refused before held cleanup")

            async def aclose(self):
                self.closed += 1
                self.close_task = asyncio.current_task()
                self.closing.set()
                await asyncio.wait_for(self.release.wait(), 2.0)
                self.completed.set()

        owner = HeldClose()
        caller = asyncio.create_task(
            _launch(_harness(policy, lambda data, catalog: owner)),
        )
        try:
            await asyncio.wait_for(owner.closing.wait(), 1.0)
            for _ in range(3):
                assert caller.cancel()
                await asyncio.wait({caller}, timeout=0.03)
                assert not caller.done(), "caller escaped held close acknowledgment"
                assert not owner.completed.is_set()
            owner.release.set()
            # Existing close semantics propagate cancellation after joining.
            # No claim about retaining the first exception's identity.
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert owner.completed.is_set() and owner.closed == 1
            assert validations == [1.25]
            assert policy.requests == owner.calls == []
        finally:
            owner.release.set()
            await asyncio.gather(caller, return_exceptions=True)
            if owner.close_task is not None:
                await asyncio.gather(owner.close_task, return_exceptions=True)
    _run(case())


@pytest.mark.parametrize("timeout", [True, 0, float("inf"), "8"])
def test_invalid_launch_timeout_still_constructs_zero_owners(timeout):
    async def case():
        policy, owners = Policy(_assistant(None)), []

        def factory(data, catalog):
            owner = Runner()
            owners.append(owner)
            return owner

        config = PTCHarnessConfig().model_copy(
            update={"program_timeout": timeout},
        )
        with pytest.raises((TypeError, ValueError)):
            await _launch(PTCHarness(
                config, transport=policy.transport(), program_runner_factory=factory,
            ))
        assert owners == policy.requests == []
    _run(case())


def test_actual_sdk_timeout_refusal_precedes_model_and_inert_program_guard(
    monkeypatch, framework,
):
    state = framework
    module, host = _fixture(monkeypatch, state)
    config = _config(state, "timeout-preflight")
    state.policy = policy = _policy()
    validations = []

    class InertOwner(Runner):
        def validate_program_timeout(self, timeout):
            validations.append(timeout)
            assert policy.calls == 0 and self.calls == []
            assert timeout == 8.0
            raise ValueError("inert owner refuses timeout 8.0 before model")

        async def run_program(self, code, *, timeout):
            self.calls.append((code, timeout))
            raise AssertionError(
                "inert SDK preflight guard reached: program dispatch forbidden"
            )

    def inert_factory(data, catalog):
        assert data is host.tasks[-1].data
        assert isinstance(catalog, Catalog)
        assert catalog.names() == host.catalog.names() | {"print"}
        assert policy.calls == 0
        host.bindings.append((data, catalog))
        owner = InertOwner()
        host.owners.append(owner)
        return owner

    # Replace the process-capable factory BEFORE the normal SDK lifecycle.
    # Neither missing validation nor a failing assertion can spawn program work.
    host.factory = inert_factory
    scoring = []

    def deny_scoring(*args, **kwargs):
        scoring.append(True)
        raise AssertionError("SDK preflight refusal must not execute SQL scoring")

    # Fail before SQL if a future SDK unexpectedly scores a failed launch.
    # Keep the original Task method and lifecycle, never synthesize a reward.
    monkeypatch.setattr(module, "execution_accuracy", deny_scoring)

    async def case():
        episode, = await _eval(module, host, config)
        assert policy.calls == 0, (
            "intended pre-model refusal dispatched an actual SDK policy request"
        )
        assert policy.bodies == []
        owner, = host.owners
        assert type(owner) is InertOwner
        assert owner.calls == [] and owner.closed == 1
        assert validations == [8.0] and len(host.bindings) == 1
        assert not episode.ok
        trace, = episode.traces
        assert not trace.ok
        assert "inert owner refuses timeout 8.0 before model" in str(trace.last_error)
        task, = host.tasks
        assert type(task) is module.OriginalTask
        assert trace.task.data is task.data
        assert host.scores == scoring == []
        assert not any(kind == "score" for kind, _ in host.events)
        record, = host.records
        assert record.setup and record.launched and not record.live
        assert host.traces == [trace]

    asyncio.run(asyncio.wait_for(case(), 15.0))
