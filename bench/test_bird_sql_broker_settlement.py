"""Five frozen broker composition groups. No listener or controller replacement."""

import asyncio
import json
import sys
import time

import pytest

from bench.test_bird_sql_broker import api, broker, cancel_before_body, observed, request
from bench.test_bird_sql_worker_controller_integration import rig, wait_log
from bench.test_bird_sql_worker_settlement import (
    Late, isolated_observers, observe_gated, pids_joined, required,
)


async def late_broker(r, monkeypatch, *, prebody=False):
    late = Late(r, monkeypatch, prebody=prebody)
    b = broker(r, config=late.config)
    required(b)
    with pytest.raises(api().SqlBrokerRetirementPending):
        await b.query("SELECT 1")
    await wait_log(r, "create")
    assert b.revoked and not b.closed and b._active is not None
    return b, b._active, late


@pytest.mark.parametrize("prebody", [False, True])
def test_06_public_composition_late_controller(rig, monkeypatch, prebody):
    async def scenario():
        b, c, late = await late_broker(rig, monkeypatch, prebody=prebody)
        calls, seen = [], set()
        original_trace, guard = sys.gettrace(), sys.getprofile()
        def trace(frame, event, arg):
            if (event == "call" and frame.f_code.co_qualname ==
                    "QueryWorkerController.wait_local_settlement" and id(frame) not in seen):
                seen.add(id(frame))
                calls.append((frame.f_locals["self"], frame.f_locals["timeout_s"]))
            return None
        sys.settrace(trace)
        try:
            await observe_gated(b, c, late)
        finally:
            sys.settrace(original_trace)
        assert sys.getprofile() is guard
        assert len(calls) == 1 and calls[0][0] is c and 0 < calls[0][1] <= 1.2
        assert b.revoked and not b.closed
        assert all(t.done() for t in b._owned_tasks())
        with pytest.raises(api().SqlBrokerRetirementPending):
            await b.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["timeout", "repeated", "concurrent", "absolute"])
def test_07_observer_isolation(rig, monkeypatch, mode):
    async def scenario():
        if mode == "absolute":
            late = Late(rig, monkeypatch)
            late.close_gate = asyncio.Event()
            b = broker(rig, config=late.config, close=0.02)
            required(b)
            with pytest.raises(api().SqlBrokerRetirementPending):
                await b.query("SELECT 1")
            await wait_log(rig, "create")
            c = b._active
            deadline, failure = b._close_deadline, b._failure
            timer = asyncio.get_running_loop().call_later(0.16, late.close_gate.set)
            started = time.monotonic()
            try:
                with pytest.raises(api().SqlBrokerRetirementPending):
                    await b.wait_local_settlement(timeout_s=0.2)
                elapsed = time.monotonic()-started
                (rig.root/"observation.json").write_text(json.dumps(dict(
                    allowance_s=0.2, elapsed_s=elapsed, tolerance_s=0.1,
                    collector_gate_s=0.16))+"\n")
                assert elapsed <= 0.3, "nested controller observation renewed allowance"
            finally:
                timer.cancel()
                late.close_gate.set()
                await late.complete(c)
            await b.wait_local_settlement(timeout_s=1.2)
            assert b._close_deadline == deadline and b._failure is failure and not b.closed
            return
        b, c, late = await late_broker(rig, monkeypatch)
        deadline, failure = b._close_deadline, b._failure
        await isolated_observers(b, c, late, mode, api().SqlBrokerRetirementPending)
        assert b._close_deadline == deadline and b._failure is failure and not b.closed
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["body", "prebody_dispatcher", "prebody_collector", "closed"])
def test_08_broker_owned_closure(rig, monkeypatch, mode):
    async def scenario():
        b = broker(rig)
        required(b)
        if mode == "body":
            external_gate = asyncio.Event()
            req, _, handler = await request(b, eof=False)
            async def external():
                response = await handler(req)
                await external_gate.wait()
                return response
            caller = asyncio.create_task(external())
            await observed(lambda: bool(b._requests))
            with pytest.raises(api().SqlBrokerError):
                await b.aclose()
            await b.wait_local_settlement(timeout_s=1)
            assert not caller.done(), "observer must not wait for external caller tasks"
            external_gate.set()
            assert (await caller).status == 503
        elif mode == "prebody_dispatcher":
            seen = cancel_before_body(monkeypatch, "TaskSqlBroker._dispatch")
            with pytest.raises(api().SqlBrokerError):
                await b.query("SELECT 1")
            await b.wait_local_settlement(timeout_s=1)
            assert seen == [b._dispatcher] and b._dispatcher.cancelled()
        elif mode == "prebody_collector":
            seen = cancel_before_body(monkeypatch, "TaskSqlBroker._collect_close")
            await b.aclose()
            await b.wait_local_settlement(timeout_s=1)
            assert seen == [b._close_collector] and b._close_collector.cancelled()
        else:
            assert (await b.query("SELECT 1")).rows == ((1,),)
            await b.aclose()
            await b.wait_local_settlement(timeout_s=1)
            assert b.closed
        assert all(t.done() for t in b._owned_tasks())
        assert not rig.registry()
        pids_joined(rig)
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["remove", "database"])
def test_09_sticky_failure_no_reopen(rig, fault):
    async def scenario():
        b = broker(rig)
        required(b)
        if fault == "remove":
            rig.settings(remove_fail=True)
            error = api().SqlBrokerRetirementPending
        else:
            with rig.toy.open("ab") as f:
                f.write(b"drift")
            error = api().SqlBrokerError
        with pytest.raises(error):
            await b.query("SELECT 1")
        count, failure = len(rig.log()), b._failure
        await b.wait_local_settlement(timeout_s=1)
        assert b._failure is failure and b.revoked and not b.closed
        with pytest.raises(error):
            await b.aclose()
        with pytest.raises(api().SqlBrokerError):
            await b.query("SELECT 2")
        assert len(rig.log()) == count and all(t.done() for t in b._owned_tasks())
        pids_joined(rig)
    asyncio.run(scenario())


def test_10_validation_inert(rig):
    b = broker(rig)
    required(b)
    async def valid_loop():
        with pytest.raises(api().SqlBrokerError):
            await b.wait_local_settlement(timeout_s=1)
        assert b._loop is None and not b.revoked
        await b.aclose()
        for value in (True, False, 0, -1, float("nan"), float("inf"), 10**400, None):
            with pytest.raises(api().SqlBrokerError):
                await b.wait_local_settlement(timeout_s=value)
        await b.wait_local_settlement(timeout_s=1)
        assert b.closed
    with asyncio.Runner() as owner:
        owner.run(valid_loop())
        with asyncio.Runner() as other:
            with pytest.raises(api().SqlBrokerError):
                other.run(b.wait_local_settlement(timeout_s=1))
    assert rig.log() == [] and not rig.registry()
