"""Host-protocol regressions, not real policy, scorer custody or native proof."""
from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace

import pytest


def _api():
    harness = importlib.import_module("ptc.harness")
    clients = importlib.import_module("verifiers.v1.clients")
    tasks = importlib.import_module("verifiers.v1.task")
    runtime = importlib.import_module("ptc.runtime")
    httpx = importlib.import_module("httpx")
    assert callable(getattr(harness, "PTCHarness", None)), "original harness missing"
    return SimpleNamespace(h=harness, clients=clients, tasks=tasks,
                           runtime=runtime, httpx=httpx)


def _reply(kind):
    if kind == "final":
        delta = {"content": "done"}
    else:
        arguments = ({"code": "print('fixture')"} if kind == "direct" else
                     {"skill_id": "fixture", "promotion_sha256": "a" * 64})
        delta = {"tool_calls": [{
            "index": 0, "id": "fixture-call", "type": "function",
            "function": {"name": "run_program", "arguments": json.dumps(arguments)},
        }]}
    events = [{"choices": [{"delta": delta}]},
              {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 3}}]
    return ("".join("data: " + json.dumps(event) + "\n\n" for event in events)
            + "data: [DONE]\n\n").encode()


def _rig(*turns, enabled=True):
    a = _api()
    state = SimpleNamespace(
        events=[], bodies=[], calls=[], closed=0, drift=False, reject=False,
        on_action=None, on_response=None, close_started=asyncio.Event(),
        close_release=None, close_error=False, response_started=asyncio.Event(),
        response_release=None, bindings=[],
    )

    class Runner:
        async def run_program(self, code, *, timeout):
            return self.action("direct", code, timeout)

        def action(self, kind, value, timeout):
            state.events.append("action")
            state.calls.append((kind, value, timeout))
            if state.on_action is not None:
                state.on_action()
            if state.reject:
                raise a.runtime.ProgramRejected("synthetic reference refusal")
            return "synthetic observation"

        async def aclose(self):
            state.closed += 1
            state.close_started.set()
            if state.close_release is not None:
                await state.close_release.wait()
            if state.close_error:
                raise RuntimeError("synthetic close failure")
            state.events.append("closed")

    runner = Runner()
    if enabled:
        def descriptor():
            return dict(skill_id="fixture", promotion_sha256="a" * 64,
                        scope="synthetic-only",
                        instruction="Select this approved skill by ID and promotion digest.")

        def validate():
            state.events.append("validate")
            if state.drift:
                raise ValueError("synthetic authority drift")

        async def reference(skill_id, promotion_sha256, *, timeout):
            return runner.action("reference", (skill_id, promotion_sha256), timeout)

        runner.reference_descriptor = descriptor
        runner.validate_launch = validate
        runner.run_reference = reference

    async def respond(request):
        state.events.append("request")
        state.bodies.append(json.loads(request.content))
        state.response_started.set()
        if state.response_release is not None:
            await state.response_release.wait()
        if state.on_response is not None:
            state.on_response(len(state.bodies))
        index = len(state.bodies) - 1
        kind = turns[index] if index < len(turns) else "final"
        return a.httpx.Response(
            200, content=_reply(kind),
            headers={"content-type": "text/event-stream"},
        )

    def factory(data, catalog):
        state.bindings.append((data, catalog))
        return runner

    state.data = a.tasks.TaskData(name="synthetic", prompt="synthetic protocol fixture")
    harness = a.h.PTCHarness(
        a.h.PTCHarnessConfig(max_turns=3, program_timeout=5),
        catalog=a.runtime.Catalog(tools={}),
        transport=a.httpx.MockTransport(respond), program_runner_factory=factory,
    )

    async def launch():
        return await harness.launch(
            a.clients.ModelContext(model="synthetic-policy", client=a.clients.EvalClientConfig()),
            trace=None, runtime=None, endpoint="http://fixture.invalid/v1",
            secret="synthetic-not-a-credential", mcp_urls={}, data=state.data,
        )

    state.launch = launch
    state.error = a.h.ProgramInfrastructureError
    return state


def _run(case):
    return asyncio.run(asyncio.wait_for(case(), 5))


def _assert_second_request_guard(state):
    first_action = state.events.index("action")
    second_request = state.events.index("request", state.events.index("request") + 1)
    assert "validate" in state.events[first_action + 1:second_request], (
        "authority not revalidated after action and before second policy request")
    assert len(state.bodies) == 2 and len(state.calls) == 1
    assert state.closed == 1


def test_live_reference_authority_precedes_each_request():
    async def case():
        state = _rig("reference", "final")
        await state.launch()
        _assert_second_request_guard(state)
    _run(case)


def test_live_direct_authority_precedes_each_request():
    async def case():
        state = _rig("direct", "final")
        await state.launch()
        _assert_second_request_guard(state)
    _run(case)


def test_live_rejected_reference_revalidates_before_next_request():
    async def case():
        state = _rig("reference", "final")
        state.reject = True
        await state.launch()
        _assert_second_request_guard(state)
        assert state.bodies[1]["messages"][-1]["content"].startswith("rejected:")
    _run(case)


def test_live_approval_drift_after_action_blocks_next_request():
    async def case():
        state = _rig("direct", "final")
        state.on_action = lambda: setattr(state, "drift", True)
        error = None
        try:
            await state.launch()
        except state.error as exc:
            error = exc
        assert len(state.bodies) == 1, "stale authority dispatched a second policy request"
        assert error is not None and len(state.calls) == 1 and state.closed == 1
    _run(case)


def test_live_approval_drift_after_response_blocks_dispatch():
    async def case():
        state = _rig("reference", "final")
        state.on_response = lambda count: setattr(state, "drift", True)
        with pytest.raises(state.error):
            await state.launch()
        assert len(state.bodies) == 1 and state.calls == [] and state.closed == 1
    _run(case)


def test_live_approval_drift_on_final_response_blocks_return():
    async def case():
        state = _rig("reference", "final")
        state.on_response = lambda count: setattr(state, "drift", count == 2)
        with pytest.raises(state.error):
            await state.launch()
        assert len(state.bodies) == 2 and len(state.calls) == 1 and state.closed == 1
    _run(case)


def test_live_opt_in_preserves_taskdata_identity():
    async def case():
        state = _rig("reference", "final")
        await state.launch()
        assert len(state.bindings) == 1 and state.bindings[0][0] is state.data
        assert [call[0] for call in state.calls] == ["reference"]
        assert state.closed == 1
    _run(case)


def test_live_disabled_path_does_not_advertise_reference():
    async def case():
        state = _rig("direct", "final", enabled=False)
        await state.launch()
        assert [call[0] for call in state.calls] == ["direct"]
        assert state.closed == 1 and "validate" not in state.events
        for body in state.bodies:
            assert "Approved skill reference:" not in body["messages"][0]["content"]
            assert "skill_id" not in json.dumps(body["tools"])
    _run(case)


def test_live_policy_cancellation_waits_for_cleanup():
    async def case():
        state = _rig("reference")
        state.response_release = asyncio.Event()
        state.close_release = asyncio.Event()
        task = asyncio.create_task(state.launch())
        try:
            await asyncio.wait_for(state.response_started.wait(), 1)
            task.cancel("first")
            await asyncio.wait_for(state.close_started.wait(), 1)
            task.cancel("second")
            await asyncio.sleep(0)
            assert not task.done(), "cancellation escaped before runner cleanup joined"
            state.close_release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert caught.value.args == ("first",)
            assert state.closed == 1 and state.calls == []
            assert state.events[-1] == "closed"
        finally:
            state.response_release.set()
            state.close_release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    _run(case)


def test_live_cleanup_failure_is_fatal():
    async def case():
        state = _rig("final")
        state.close_error = True
        with pytest.raises(state.error):
            await state.launch()
        assert len(state.bodies) == 1 and state.closed == 1 and state.calls == []
    _run(case)
