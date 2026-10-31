"""Ordinary HTTP/SSE harness acceptance tests for the optional owner seam."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from verifiers.v1.clients import EvalClientConfig, ModelContext
from verifiers.v1.task import TaskData

from ptc.harness import PTCHarness, PTCHarnessConfig, ProgramInfrastructureError
from ptc.runtime import Catalog, ProgramRejected
from ptc.test_harness import ENDPOINT, SECRET, Policy, _assistant


class Runner:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.closed = 0

    async def run_program(self, code, *, timeout):
        self.calls.append((code, timeout))
        outcome = self.outcomes.pop(0) if self.outcomes else ""
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def aclose(self):
        self.closed += 1


def _launch(harness, data=None, *, mcp_urls=None):
    return harness.launch(
        ModelContext(model="test-model", client=EvalClientConfig()),
        trace=None, runtime=None, endpoint=ENDPOINT, secret=SECRET,
        mcp_urls=mcp_urls or {}, data=data or TaskData(prompt="fixture"),
    )


def _harness(policy, factory, **kwargs):
    return PTCHarness(
        PTCHarnessConfig(program_timeout=1.25),
        transport=policy.transport(), program_runner_factory=factory, **kwargs,
    )


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


def test_exact_dispatch_observations_and_compiled_catalog_identity():
    async def case():
        codes = ["print(note(value=21))", "print('second')"]
        observations = ["  first\nverbatim\n", ""]
        policy = Policy(*map(_assistant, codes), _assistant(None))
        data = TaskData(prompt="original")
        def note(*, value):
            return value * 2
        base = Catalog(tools={"note": note})
        owner = Runner(*observations)
        bindings, loop_catalogs = [], []

        def factory(actual_data, catalog):
            assert policy.requests == [], "factory must precede model dispatch"
            assert actual_data is data
            assert catalog is not base
            assert catalog.names() == {"note", "print"}
            assert catalog.tools["note"] is note
            assert callable(catalog.tools["print"])
            bindings.append((actual_data, catalog))
            return owner

        class ObservedHarness(PTCHarness):
            async def _loop(self, *args, **kwargs):
                loop_catalogs.append(args[4])
                return await super()._loop(*args, **kwargs)

        harness = ObservedHarness(
            PTCHarnessConfig(program_timeout=1.25), catalog=base,
            transport=policy.transport(), program_runner_factory=factory,
        )
        result = await _launch(harness, data)
        assert result.exit_code == 0
        assert owner.calls == [(code, 1.25) for code in codes]
        assert len(bindings) == 1 and bindings[0][1] is loop_catalogs[0]
        assert len(policy.requests) == 3
        for body, expected in zip(policy.bodies[1:], observations):
            assert body["messages"][-1]["content"] == expected
            assert [tool["function"]["name"] for tool in body["tools"]] == [
                "run_program",
            ]
        assert owner.closed == 1
        assert base.names() == {"note"}
    _run(case())


def test_shared_harness_creates_fresh_launch_owners():
    async def case():
        policy = Policy(_assistant("one"), _assistant(None),
                        _assistant("two"), _assistant(None))
        owners, bindings = [], []

        def factory(data, catalog):
            bindings.append((data, catalog))
            owner = Runner(data.prompt)
            owners.append(owner)
            return owner

        harness = _harness(policy, factory)
        first, second = TaskData(prompt="first"), TaskData(prompt="second")
        await _launch(harness, first)
        await _launch(harness, second)
        assert [binding[0] for binding in bindings] == [first, second]
        assert bindings[0][0] is first and bindings[1][0] is second
        assert bindings[0][1] is not bindings[1][1]
        assert len(owners) == 2 and owners[0] is not owners[1]
        assert [owner.calls for owner in owners] == [
            [("one", 1.25)], [("two", 1.25)],
        ]
        assert [owner.closed for owner in owners] == [1, 1]
    _run(case())


@pytest.mark.parametrize("kind", ["infra", "unexpected", "nonstring"])
def test_infrastructure_failure_has_no_next_request(kind):
    async def case():
        outcome = {
            "infra": ProgramInfrastructureError("explicit owner failure"),
            "unexpected": RuntimeError("unexpected owner failure"),
            "nonstring": {"not": "observation text"},
        }[kind]
        policy = Policy(_assistant("submitted once"), _assistant(None))
        owner = Runner(outcome)
        error = None
        try:
            await _launch(_harness(policy, lambda data, catalog: owner))
        except ProgramInfrastructureError as exc:
            error = exc
        # Keep this assertion before the error assertion: the directed bypass
        # must fail specifically because infrastructure became retry feedback.
        assert len(policy.requests) == 1, (
            "infrastructure failure dispatched a second policy request"
        )
        assert error is not None, "owner failure must be infrastructure-fatal"
        assert owner.calls == [("submitted once", 1.25)]
        assert owner.closed == 1
    _run(case())


def test_program_rejected_remains_tool_data_and_closes_once():
    async def case():
        owner = Runner(ProgramRejected("fixture refusal"))
        policy = Policy(_assistant("bad"), _assistant(None))
        await _launch(_harness(policy, lambda data, catalog: owner))
        assert len(policy.requests) == 2
        assert policy.bodies[1]["messages"][-1]["content"] == (
            "rejected: fixture refusal"
        )
        assert owner.closed == 1
    _run(case())


@pytest.mark.parametrize("mode", ["exception", "self-cancel"])
def test_cleanup_failure_is_fatal(mode):
    class BrokenClose(Runner):
        async def aclose(self):
            self.closed += 1
            if mode == "self-cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("cleanup failed")

    async def case():
        owner = BrokenClose()
        policy = Policy(_assistant(None))
        with pytest.raises(ProgramInfrastructureError):
            await _launch(_harness(policy, lambda data, catalog: owner))
        assert owner.closed == 1 and len(policy.requests) == 1
    _run(case())


def test_model_transport_failure_still_closes_once():
    async def case():
        import httpx
        owner = Runner()

        def broken(request):
            raise httpx.ConnectError("fixture transport failure", request=request)

        harness = PTCHarness(
            PTCHarnessConfig(), transport=httpx.MockTransport(broken),
            program_runner_factory=lambda data, catalog: owner,
        )
        with pytest.raises(httpx.ConnectError):
            await _launch(harness)
        assert owner.closed == 1
    _run(case())


@pytest.mark.parametrize("acknowledgment", [False, True, "cleanup pending"])
def test_cleanup_requires_none_acknowledgment(acknowledgment):
    class BadAcknowledgment(Runner):
        async def aclose(self):
            self.closed += 1
            return acknowledgment

    async def case():
        owner = BadAcknowledgment()
        policy = Policy(_assistant(None))
        with pytest.raises(ProgramInfrastructureError, match="acknowledge with None"):
            await _launch(_harness(policy, lambda data, catalog: owner))
        assert owner.closed == 1 and len(policy.requests) == 1
    _run(case())


def test_injected_timeout_is_captured_before_factory():
    async def case():
        policy = Policy(_assistant("submitted"), _assistant(None))
        owner = Runner("42")

        def factory(data, catalog):
            # Deliberate fixture mutation, not supported factory behavior.
            harness.config.program_timeout = float("inf")
            return owner

        harness = _harness(policy, factory)
        await _launch(harness)
        assert owner.calls == [("submitted", 1.25)]
        assert owner.closed == 1
    _run(case())


def test_factory_can_refuse_actual_catalog_before_model_dispatch():
    async def case():
        policy, bindings = Policy(_assistant(None)), []

        def factory(data, catalog):
            bindings.append((data, catalog))
            assert catalog.names() == {"unsupported", "print"}
            raise ValueError("fixture catalog unsupported")

        with pytest.raises(ValueError, match="fixture catalog unsupported"):
            await _launch(_harness(
                policy, factory, catalog=Catalog(tools={"unsupported": lambda: 1}),
            ))
        assert len(bindings) == 1 and policy.requests == []
    _run(case())


@pytest.mark.parametrize("kind", [
    "noncallable", "async", "asyncgen", "awaitable-result",
    "missing-run", "sync-run", "missing-close", "sync-close",
])
def test_invalid_factories_and_methods_dispatch_zero_requests(kind):
    async def case():
        policy, calls, results = Policy(_assistant(None)), [], []

        async def async_factory(data, catalog):
            calls.append("async body")
            return Runner()

        async def asyncgen_factory(data, catalog):
            calls.append("asyncgen body")
            yield Runner()

        def factory(data, catalog):
            calls.append("factory")
            if kind == "awaitable-result":
                result = async_factory(data, catalog)
            else:
                result = Runner()
                method = "run_program" if kind.endswith("run") else "aclose"
                setattr(result, method, None if kind.startswith("missing") else lambda: None)
            results.append(result)
            return result

        selected = {"noncallable": 17, "async": async_factory,
                    "asyncgen": asyncgen_factory}.get(kind, factory)
        with pytest.raises((TypeError, ValueError)):
            await _launch(_harness(policy, selected))
        assert policy.requests == []
        if kind in {"noncallable", "async", "asyncgen"}:
            assert calls == []
        elif kind == "awaitable-result":
            assert calls == ["factory"]
            assert inspect.getcoroutinestate(results[0]) == inspect.CORO_CLOSED
        else:
            assert calls == ["factory"] and results[0].closed == 0
    _run(case())


@pytest.mark.parametrize("timeout", [True, False, 0, -1, float("inf"),
                                    float("nan"), "1", None])
def test_invalid_resolved_timeout_dispatches_zero_requests(timeout):
    async def case():
        policy, calls = Policy(_assistant(None)), []
        # Bypass Pydantic coercion deliberately: assert the injected seam checks
        # the resolved value, including bool, rather than trusting annotations.
        config = PTCHarnessConfig().model_copy(update={"program_timeout": timeout})
        with pytest.raises((TypeError, ValueError)):
            harness = PTCHarness(
                config, transport=policy.transport(),
                program_runner_factory=lambda data, catalog: calls.append(data),
            )
            await _launch(harness)
        assert calls == policy.requests == []
    _run(case())


@pytest.mark.parametrize("combination", ["qa", "mcp"])
def test_unsupported_combinations_refuse_before_discovery(monkeypatch, combination):
    async def case():
        policy, factories, discoveries = Policy(_assistant(None)), [], []

        async def discovery(*args, **kwargs):
            discoveries.append(True)
            raise AssertionError("unsupported combination reached discovery")

        monkeypatch.setattr("ptc.harness._mcp_catalog", discovery)
        kwargs = {}
        if combination == "qa":
            kwargs["qa_factory"] = lambda data: factories.append("qa")
        with pytest.raises((TypeError, ValueError)):
            harness = _harness(
                policy, lambda data, catalog: factories.append("owner"), **kwargs,
            )
            await _launch(harness, mcp_urls=(
                {"fixture": "http://127.0.0.1:1"} if combination == "mcp" else {}
            ))
        assert factories == discoveries == policy.requests == []
    _run(case())


class HeldClose(Runner):
    """Finite fixture gates. Retain cleanup handle even under the bypass control."""
    def __init__(self):
        super().__init__()
        self.running = asyncio.Event()
        self.closing = asyncio.Event()
        self.release = asyncio.Event()
        self.completed = asyncio.Event()
        self.close_task = None

    async def run_program(self, code, *, timeout):
        self.running.set()
        await asyncio.wait_for(asyncio.Event().wait(), 2.0)
        return "unreachable"

    async def aclose(self):
        self.close_task = asyncio.current_task()
        self.closed += 1
        self.closing.set()
        await asyncio.wait_for(self.release.wait(), 2.0)
        self.completed.set()


async def _cancel_case(*, ordinary_close):
    owner = HeldClose()
    policy = Policy(_assistant(None if ordinary_close else "blocked"))
    caller = asyncio.create_task(
        _launch(_harness(policy, lambda data, catalog: owner))
    )
    try:
        if not ordinary_close:
            await asyncio.wait_for(owner.running.wait(), 1.0)
            caller.cancel()
        await asyncio.wait_for(owner.closing.wait(), 1.0)
        caller.cancel()
        # Allow cancellation delivery without releasing the owner. Unlike
        # asyncio.run's executor cleanup, this assertion observes launch itself.
        await asyncio.wait({caller}, timeout=0.03)
        if not ordinary_close:
            caller.cancel()
            await asyncio.wait({caller}, timeout=0.03)
        assert not caller.done(), "caller returned before owned close acknowledgment"
        assert not owner.completed.is_set()
        owner.release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert owner.completed.is_set() and owner.closed == 1
        assert len(policy.requests) == 1
    finally:
        owner.release.set()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
        if owner.close_task is not None:
            await asyncio.gather(owner.close_task, return_exceptions=True)


def test_repeated_cancellation_joins_owned_close():
    _run(_cancel_case(ordinary_close=False))


def test_new_cancellation_during_normal_close_propagates_after_join():
    _run(_cancel_case(ordinary_close=True))
