"""Five frozen groups, real owned processes and late pipe/reap closure."""

import asyncio
from dataclasses import replace
import json
import os
import time

import pytest

from bench.test_bird_sql_worker_controller_integration import (
    assert_joined, controller_api, rig, wait_log,
)


def required(owner):
    assert callable(getattr(owner, "wait_local_settlement", None)), (
        "CALL: public wait_local_settlement API absent")


def pids_joined(r):
    pids = {v[k] for v in r.log() for k in ("pid", "child_pid") if k in v}
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    return sorted(pids)


class Late:
    """Deliver a REAL Process late; gate ORIGINAL drain coroutine completion.

    No controller methods/lifecycle facts are replaced. Gates only schedule
    original coroutine work; cancellation is recorded, never hidden from tests.
    """
    def __init__(self, r, monkeypatch, *, prebody=False):
        self.r = r
        self.deliver = asyncio.Event()
        self.pipes = asyncio.Event()
        self.created = asyncio.Event()
        self.drained = asyncio.Event()
        self.proc = None
        self.cancellations = []
        self.kills = []
        self.prebody = []
        self.close_gate = None
        self.config = replace(r.config, worker=replace(r.config.worker, setup_timeout_s=0.06),
                              process_join_timeout_s=0.03)
        r.settings(create_effect=False, create_flood=True)
        spawn = asyncio.create_subprocess_exec
        create = asyncio.create_task
        kill = os.killpg

        async def delayed(*args, **kwargs):
            self.proc = await spawn(*args, **kwargs)
            self.created.set()
            while not self.deliver.is_set():
                try:
                    await self.deliver.wait()
                except asyncio.CancelledError as exc:
                    self.cancellations.append(exc.args)
            return self.proc

        def task(coro, *args, **kwargs):
            name = coro.cr_code.co_qualname
            if name == "TaskSqlBroker._collect_close" and self.close_gate is not None:
                async def collector():
                    await self.close_gate.wait()
                    return await coro
                result = create(collector(), *args, **kwargs)
            elif name == "QueryWorkerController._discard_after":
                async def drain():
                    result = await coro
                    self.drained.set()
                    await self.pipes.wait()
                    return result
                result = create(drain(), *args, **kwargs)
            else:
                result = create(coro, *args, **kwargs)
            if prebody and name == "QueryWorkerController._reclaim_local":
                self.prebody.append(result)
                result.cancel("prebody-reclamation-collector")
            return result

        def owned_kill(pid, sig):
            self.kills.append((pid, int(sig)))
            return kill(pid, sig)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed)
        monkeypatch.setattr(asyncio, "create_task", task)
        monkeypatch.setattr(os, "killpg", owned_kill)

    async def controller(self):
        c = self.r.controller(self.config)
        required(c)
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.execute("SELECT 1")
        await wait_log(self.r, "create")
        assert self.created.is_set() and not self.deliver.is_set()
        assert c._local_uncertain and c.state.phase != "CLOSED"
        assert len(c._records) == 1 and not c._records[0].tasks
        return c

    async def complete(self, c):
        # Release fixture scheduling gates and join ORIGINAL acknowledgements.
        # This also keeps assertion-RED controls failure-safe, without rescue,
        # extra kills, private state writes or invented lifecycle observations.
        self.deliver.set()
        self.pipes.set()
        record = c._records[0]
        done, _ = await asyncio.wait({record.reclaim_done}, timeout=1.2)
        assert done, "original late-reap acknowledgement missing"
        if record.reclaim_task is not None:
            done, _ = await asyncio.wait({record.reclaim_task}, timeout=1.2)
            assert done
        assert_joined(c)
        assert record.process is self.proc and self.proc.returncode is not None
        assert self.proc.stdout.at_eof() and self.proc.stderr.at_eof()
        assert self.proc.stdin.is_closing()
        pids = pids_joined(self.r)
        assert not self.r.registry() and len(self.kills) == 1
        assert self.kills[0][0] == self.proc.pid
        assert [v["command"] for v in self.r.log()] == ["create"]
        (self.r.root/"settlement.json").write_text(json.dumps(dict(
            pid=self.proc.pid, joined_pids=pids, kills=self.kills,
            cancelled_owners=self.cancellations, dynamic_tasks=len(record.tasks),
            reclaim_done=record.reclaim_done.done(), local_uncertain=c._local_uncertain,
            phase=c.state.phase, registry=self.r.registry()), indent=2)+"\n")


async def observe_gated(owner, c, late):
    observation = asyncio.create_task(owner.wait_local_settlement(timeout_s=1.2))
    try:
        await asyncio.sleep(0.005)
        early_handle = observation.done()
        late.deliver.set()
        await asyncio.wait_for(late.drained.wait(), 1.2)
        early_pipes = observation.done()
        late.pipes.set()
        await observation
    finally:
        await late.complete(c)
    assert not early_handle, "settlement returned before real late Process delivery"
    assert not early_pipes, "settlement missed dynamically added pipe/reap work"


async def isolated_observers(owner, c, late, mode, pending):
    captured = []
    async def observe():
        try:
            await owner.wait_local_settlement(timeout_s=1.2)
        except asyncio.CancelledError as exc:
            captured.append(exc)
            raise
    try:
        if mode == "timeout":
            started = time.monotonic()
            with pytest.raises(pending):
                await owner.wait_local_settlement(timeout_s=0.02)
            elapsed = time.monotonic()-started
            (late.r.root/"observation.json").write_text(json.dumps(dict(
                allowance_s=0.02, elapsed_s=elapsed, tolerance_s=0.1))+"\n")
            assert elapsed <= 0.12, f"observation allowance renewed: {elapsed}"
            assert late.cancellations == []
        else:
            first = asyncio.create_task(observe())
            second = (asyncio.create_task(owner.wait_local_settlement(timeout_s=1.2))
                      if mode == "concurrent" else None)
            if mode != "prebody":
                await asyncio.sleep(0.005)
            first.cancel("original-observer")
            await asyncio.sleep(0.005)
            if mode in ("repeated", "concurrent"):
                first.cancel("repeated-observer")
            late.deliver.set()
            late.pipes.set()
            cancelled = None
            try:
                await first
            except asyncio.CancelledError as exc:
                cancelled = exc
            if second is not None:
                await second
            # All original work settles before the intentional mutant assertion.
            await late.complete(c)
            assert late.cancellations == [], "observer cancellation reached owned spawn"
            assert isinstance(cancelled, asyncio.CancelledError)
            if mode != "prebody":
                assert len(captured) == 1 and cancelled is captured[0]
                assert cancelled.args == ("original-observer",)
        late.deliver.set()
        late.pipes.set()
        await owner.wait_local_settlement(timeout_s=1.2)
    finally:
        await late.complete(c)
    assert late.cancellations == []


@pytest.mark.parametrize("prebody", [False, True])
def test_01_late_handle_and_dynamic_closure(rig, monkeypatch, prebody):
    async def scenario():
        late = Late(rig, monkeypatch, prebody=prebody)
        c = await late.controller()
        state = c.state
        await observe_gated(c, c, late)
        assert c.state is state and c._local_uncertain
        if prebody:
            assert len(late.prebody) == 1 and late.prebody[0].cancelled()
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["timeout", "prebody", "during", "repeated", "concurrent"])
def test_02_timeout_and_cancellation(rig, monkeypatch, mode):
    async def scenario():
        late = Late(rig, monkeypatch)
        c = await late.controller()
        await isolated_observers(c, c, late, mode, controller_api().QueryWorkerRetirementPending)
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["create", "remove", "unknown"])
def test_03_remote_pending_and_no_reopen(rig, fault, monkeypatch):
    async def scenario():
        c = rig.controller()
        required(c)
        if fault == "unknown":
            from bench.test_bird_sql_broker import cancel_before_body
            cancelled = cancel_before_body(monkeypatch, "create_subprocess_exec")
            with pytest.raises(asyncio.CancelledError) as caught:
                await c.execute("SELECT 1")
            assert caught.value is c._owner_cancel and c._local_uncertain
            state = c.state
            with pytest.raises(controller_api().QueryWorkerRetirementPending):
                await c.wait_local_settlement(timeout_s=1)
            assert c.state is state and rig.log() == []
            assert cancelled and cancelled[0].cancelled()
            assert_joined(c)
            return
        rig.settings(**({"create_nonzero": True, "create_effect": False}
                        if fault == "create" else {"remove_fail": True}))
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.execute("SELECT 1")
        count, state = len(rig.log()), c.state
        await c.wait_local_settlement(timeout_s=1)
        assert c.state is state and c.state.phase != "CLOSED"
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.aclose()
        with pytest.raises(controller_api().QueryWorkerControllerError):
            await c.execute("SELECT 2")
        assert len(rig.log()) == count
        assert_joined(c)
        pids_joined(rig)
    asyncio.run(scenario())


def test_04_validation_inert(rig):
    c = rig.controller()
    required(c)
    api = controller_api()
    async def valid_loop():
        with pytest.raises(api.QueryWorkerControllerError):
            await c.wait_local_settlement(timeout_s=1)
        assert c._loop is None and not c._revoked
        await c.aclose()
        for value in (True, False, 0, -1, float("nan"), float("inf"), 10**400, None):
            with pytest.raises(api.QueryWorkerControllerError):
                await c.wait_local_settlement(timeout_s=value)
        await c.wait_local_settlement(timeout_s=1)
    with asyncio.Runner() as owner:
        owner.run(valid_loop())
        with asyncio.Runner() as other:
            with pytest.raises(api.QueryWorkerControllerError):
                other.run(c.wait_local_settlement(timeout_s=1))
    assert rig.log() == [] and not rig.registry()


def test_05_original_source_expectation_refuses(rig):
    old = "ac027fa522d188f8d9e838e0ad09188d29ae78397dbf46b47e7835a058e97aaf"
    expected = tuple((p, old if p == "ptc/bird_sql_worker_controller.py" else h)
                     for p, h in rig.config.expected_source_sha256)
    async def scenario():
        c = rig.controller(replace(rig.config, expected_source_sha256=expected))
        required(c)
        with pytest.raises(controller_api().QueryWorkerControllerError):
            await c.execute("SELECT 1")
        await c.wait_local_settlement(timeout_s=1)
        assert rig.log() == [] and c.state.phase == "CLOSED"
    asyncio.run(scenario())
