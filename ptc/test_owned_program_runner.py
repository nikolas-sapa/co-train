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


class ReferenceRunner(Runner):
    """Protocol-only unit double; never supplies a concrete invocation ACK."""
    def __init__(self, *outcomes, public=None):
        super().__init__(*outcomes)
        from ptc.test_sql_skill_reuse_integration import descriptor
        self.public = descriptor() if public is None else public
        self.selections, self.guards = [], 0

    def reference_descriptor(self):
        return self.public

    def validate_launch(self):
        self.guards += 1

    async def run_reference(self, skill_id, promotion_sha256, *, timeout):
        from ptc.runtime import ProgramRejected
        if (skill_id != self.public["skill_id"]
                or promotion_sha256 != self.public["promotion_sha256"]):
            raise ProgramRejected("unknown reference")
        self.selections.append((skill_id, promotion_sha256, timeout))
        outcome = self.outcomes.pop(0) if self.outcomes else "reference observation"
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _reference_turn(**updates):
    import json
    values = dict(skill_id="fixture-count", promotion_sha256="a" * 64)
    values.update(updates)
    return _assistant(None, raw_args=json.dumps(values))


def _reference_harness(policy, owner, *, cap=8):
    return PTCHarness(
        PTCHarnessConfig(program_timeout=5, max_turns=cap),
        transport=policy.transport(), program_runner_factory=lambda data, catalog: owner)


@pytest.mark.parametrize("kind", (
    "empty", "unknown", "malformed", "wrong", "missing", "id-type", "pin-type",
    "code-plus-reference", "incomplete", "extra", "duplicate", "tool-name",
))
def test_live_reference_invalid_shapes_never_dispatch(kind):
    import json
    values = dict(skill_id="fixture-count", promotion_sha256="a" * 64)
    if kind == "empty":
        values["skill_id"] = ""
    elif kind == "unknown":
        values["skill_id"] = "not-advertised"
    elif kind in ("malformed", "wrong"):
        values["promotion_sha256"] = "bad" if kind == "malformed" else "b" * 64
    elif kind == "missing":
        values.pop("promotion_sha256")
    elif kind == "id-type":
        values["skill_id"] = 1
    elif kind == "pin-type":
        values["promotion_sha256"] = None
    elif kind == "code-plus-reference":
        values["code"] = "print(0)"
    elif kind == "incomplete":
        values.pop("skill_id")
    elif kind == "extra":
        values["extra"] = True
    raw = json.dumps(values)
    if kind == "duplicate":
        raw = '{"skill_id":"fixture-count","skill_id":"fixture-count","promotion_sha256":"' + "a"*64 + '"}'
    turn = _assistant(None, raw_args=raw)
    if kind == "tool-name":
        turn["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "other_tool"

    async def case():
        owner = ReferenceRunner()
        policy = Policy(turn, _assistant(None))
        await _launch(_reference_harness(policy, owner))
        assert owner.calls == owner.selections == [], "invalid reference dispatched"
        assert len(policy.requests) == 2 and owner.closed == 1
        assert policy.bodies[1]["messages"][-1]["content"].startswith("rejected:")
    _run(case())


@pytest.mark.parametrize("enabled", (False, True))
@pytest.mark.parametrize("code", ("", " \t\n", "print('caf\u00e9')"))
def test_live_reference_preserves_legacy_direct_bytes(enabled, code):
    async def case():
        owner = ReferenceRunner("exact observation") if enabled else Runner("exact observation")
        policy = Policy(_assistant(code), _assistant(None))
        await _launch(_reference_harness(policy, owner))
        assert owner.calls == [(code, 5)]
        assert getattr(owner, "selections", []) == []
        assert policy.bodies[1]["messages"][-1]["content"] == "exact observation"
        assert owner.closed == 1
    _run(case())


@pytest.mark.parametrize("enabled", (False, True))
def test_live_candidate_identical_direct_is_not_reference(enabled):
    from train.test_sql_skills import PROGRAM

    async def case():
        owner = ReferenceRunner() if enabled else Runner()
        policy = Policy(_assistant(PROGRAM), _assistant(None))
        await _launch(_reference_harness(policy, owner))
        assert owner.calls == [(PROGRAM, 5)]
        assert getattr(owner, "selections", []) == []
        if enabled:
            assert owner.guards == 3, "initial and both post-request guards required"
    _run(case())


def _bounded_descriptor(field, size, *, multibyte=False):
    from ptc.test_sql_skill_reuse_integration import descriptor, canonical
    if field != "total":
        unit = "\u00e9" if multibyte else "x"
        value = unit * (size // len(unit.encode("utf-8"))) + "x" * (size % len(unit.encode("utf-8")))
        return descriptor(**{field: value})
    # JSON escaping increases serialized bytes without violating field bounds.
    for escaped in range(1025):
        for plain in range(7):
            public = descriptor(scope="\x01" * escaped + "x" * plain)
            if len(public["scope"].encode("utf-8")) <= 1024 and len(canonical(public)) == size:
                return public
    raise AssertionError("exact descriptor boundary fixture not representable")


@pytest.mark.parametrize("field,size,multibyte,accepted", (
    ("skill_id", 256, False, True), ("skill_id", 257, False, False),
    ("skill_id", 256, True, True), ("skill_id", 257, True, False),
    ("scope", 1024, False, True), ("scope", 1025, False, False),
    ("scope", 1024, True, True), ("scope", 1025, True, False),
    ("total", 2048, False, True), ("total", 2049, False, False),
))
def test_live_reference_descriptor_utf8_boundaries(field, size, multibyte, accepted):
    public = _bounded_descriptor(field, size, multibyte=multibyte)

    async def case():
        owner = ReferenceRunner(public=public)
        policy = Policy(_assistant(None))
        error = None
        try:
            await _launch(_reference_harness(policy, owner))
        except (ValueError, TypeError, ProgramInfrastructureError) as exc:
            error = exc
        assert len(policy.requests) == int(accepted), "descriptor admitted before byte bounds"
        assert (error is None) is accepted
        assert owner.calls == owner.selections == [] and owner.closed == 1
    _run(case())


@pytest.mark.parametrize("pin", ("A"*64, "a"*63, "g"*64, "a"*65))
def test_live_reference_descriptor_digest_rejected_before_request(pin):
    from ptc.test_sql_skill_reuse_integration import descriptor

    async def case():
        owner = ReferenceRunner(public=descriptor(promotion_sha256=pin))
        policy = Policy(_assistant(None))
        with pytest.raises((ValueError, TypeError, ProgramInfrastructureError)):
            await _launch(_reference_harness(policy, owner))
        assert policy.requests == [] and owner.closed == 1
        assert owner.calls == owner.selections == []
    _run(case())


def test_live_reference_public_projection_is_private_and_local():
    import copy
    import json
    from ptc import harness as module
    from ptc.test_sql_skill_reuse_integration import INSTRUCTION

    async def case():
        baseline = copy.deepcopy(module.TOOLS)
        owner = ReferenceRunner()
        policy = Policy(_reference_turn(), _assistant(None))
        await _launch(_reference_harness(policy, owner))
        assert owner.calls == [] and len(owner.selections) == 1
        assert owner.public["instruction"] == INSTRUCTION
        assert len(INSTRUCTION.encode("utf-8")) <= 256
        assert set(owner.public) == {"skill_id", "promotion_sha256", "scope", "instruction"}
        wire = json.dumps(policy.bodies)
        assert INSTRUCTION in wire and "fixture-count" in wire
        assert "program" not in owner.public and "approval_path" not in wire
        assert module.TOOLS == baseline
        for body in policy.bodies:
            assert [item["function"]["name"] for item in body["tools"]] == ["run_program"]
            assert body["stream_options"]["include_usage"] is True
        assert owner.guards == 3 and owner.closed == 1
    _run(case())


@pytest.mark.parametrize("member", ("reference_descriptor", "validate_launch", "run_reference"))
@pytest.mark.parametrize("fault", ("missing", "noncallable", "wrong-async"))
def test_live_reference_optional_protocol_cleanup(member, fault):
    async def case():
        owner = ReferenceRunner()
        if fault == "missing":
            # Shadow the class member with an absent attribute on this instance.
            class Missing(ReferenceRunner):
                def __getattribute__(self, name):
                    if name == member:
                        raise AttributeError(name)
                    return super().__getattribute__(name)
            owner = Missing()
        elif fault == "noncallable":
            setattr(owner, member, 7)
        elif member == "run_reference":
            setattr(owner, member, lambda *args, **kwargs: "not async")
        else:
            async def wrong():
                return None
            setattr(owner, member, wrong)
        policy = Policy(_assistant(None))
        with pytest.raises((ValueError, TypeError, ProgramInfrastructureError)):
            await _launch(_reference_harness(policy, owner))
        assert owner.closed == 1 and policy.requests == []
    _run(case())


def test_live_reference_disabled_import_io_and_schema_are_inert(monkeypatch):
    import builtins
    import copy
    from pathlib import Path
    from ptc import harness as module

    attempts = []
    original_import, original_read = builtins.__import__, Path.read_bytes

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("train.sql_skill", "train.sql_pilot")):
            attempts.append(("import", name))
            raise AssertionError("disabled harness imported skill authority")
        return original_import(name, *args, **kwargs)

    def guarded_read(path):
        attempts.append(("read", str(path)))
        raise AssertionError("disabled harness read skill files")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    async def case():
        schema, system = copy.deepcopy(module.TOOLS), module.SYSTEM
        owners, policies = [], []
        for turn in (_assistant("direct"), _reference_turn()):
            owner = Runner("direct observation")
            policy = Policy(turn, _assistant(None))
            await _launch(_reference_harness(policy, owner))
            owners.append(owner)
            policies.append(policy)
            assert policy.bodies[0]["tools"] == schema
            assert owner.closed == 1
        assert owners[0].calls == [("direct", 5)]
        assert owners[1].calls == [], "disabled reference became blank direct code"
        assert policies[1].bodies[1]["messages"][-1]["content"].startswith("rejected:")
        assert policies[0].bodies[0]["messages"][0] == policies[1].bodies[0]["messages"][0]
        assert module.TOOLS == schema and module.SYSTEM == system
        assert attempts == []
    _run(case())


@pytest.mark.parametrize("kind", ("rejected", "infrastructure", "unexpected", "cancel"))
def test_live_reference_original_exception_and_cancel_identity(kind):
    async def case():
        from ptc.runtime import ProgramRejected
        errors = {
            "rejected": ProgramRejected("original rejection"),
            "infrastructure": ProgramInfrastructureError("original infrastructure"),
            "unexpected": RuntimeError("original unexpected"),
            "cancel": asyncio.CancelledError("original cancel"),
        }
        error = errors[kind]
        entered, release = asyncio.Event(), asyncio.Event()

        class Held(ReferenceRunner):
            async def aclose(self):
                self.closed += 1
                entered.set()
                await release.wait()

        owner = Held(error)
        policy = Policy(_reference_turn(), _assistant(None))
        call = asyncio.create_task(_launch(_reference_harness(policy, owner)))
        try:
            if kind == "cancel":
                await asyncio.wait_for(entered.wait(), 1)
                for _ in range(3):
                    call.cancel()
                    await asyncio.sleep(0)
                assert not call.done(), "cancel escaped before joined close"
            else:
                release.set()
            if kind == "rejected":
                await call
                assert len(policy.requests) == 2
                assert policy.bodies[1]["messages"][-1]["content"] == "rejected: original rejection"
            else:
                release.set()
                with pytest.raises(BaseException) as caught:
                    await call
                if kind == "cancel":
                    assert caught.value is error
                elif kind == "infrastructure":
                    assert caught.value is error
                else:
                    assert isinstance(caught.value, ProgramInfrastructureError)
                    assert caught.value.__cause__ is error
                assert len(policy.requests) == 1
            assert owner.closed == 1 and len(owner.selections) == 1
        finally:
            release.set()
            await asyncio.gather(call, return_exceptions=True)
    _run(case())
