"""PROVES: public factory retention of real inert owned PROGRAM runners.

SHORTCUT: scripted unit transport, no SDK evaluation and no PROGRAM actions.
MISSING: active invocation/ACK proof, actual SDK cancellation and writer barrier.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from ptc.harness import ProgramInfrastructureError
from ptc.test_sql_owned_program import _build, _fixture, no_native  # noqa: F401


class RetainedRunner:
    """Public protocol proxy, without inspecting actual runner jobs/closures."""

    def __init__(self, actual, *, omit_close=False):
        self.actual = actual
        self.omit_close = omit_close
        self.close_task = None
        self.close_calls = 0
        self.validations = []
        self.executing = False

    def validate_program_timeout(self, timeout):
        self.validations.append(timeout)
        return self.actual.validate_program_timeout(timeout)

    async def run_program(self, code, *, timeout):
        if self.close_task is not None or self.executing:
            raise ProgramInfrastructureError("retained runner lease unavailable")
        self.executing = True
        try:
            return await self.actual.run_program(code, timeout=timeout)
        finally:
            self.executing = False

    def start_close(self):
        if self.close_task is None:
            if self.omit_close:
                # SHORTCUT: deliberate negative only, never actual cleanup proof.
                async def omitted():
                    return None
                work = omitted()
            else:
                self.close_calls += 1
                work = self.actual.aclose()
            self.close_task = asyncio.create_task(work)
        return self.close_task

    async def aclose(self):
        task = self.start_close()
        cancelled = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                if cancelled is None:
                    cancelled = exc
            except Exception:
                break
        result = task.result()
        assert result is None
        if cancelled is not None:
            raise cancelled


def _install(harness, retained, *, omit_close=False):
    original = harness.program_runner_factory

    def factory(data, compiled):
        actual = original(data, compiled)
        lease = RetainedRunner(actual, omit_close=omit_close)
        retained.append(lease)  # Before timeout validation or any await.
        return lease

    harness.program_runner_factory = factory
    return original


def _assert_actually_closed(lease):
    try:
        lease.actual.validate_program_timeout(5)
    except ProgramInfrastructureError as exc:
        assert str(exc) == "owned SQL runner is closed"
    else:
        raise AssertionError("PROGRAM_RUNNER_NOT_CLOSED")


async def _exercise(root, *, omit_close=False):
    retained, policies, launches = [], [], []
    for index in range(2):
        directory = root / str(index)
        directory.mkdir(parents=True)
        fixture = _fixture(directory)
        harness = _build(fixture)
        _install(harness, retained, omit_close=omit_close)
        policy = fixture.dep.Policy(fixture.dep.assistant(None))
        harness.transport = policy.transport()
        policies.append(policy)
        launches.append(fixture.dep.launch(harness, fixture.data))
    results = await asyncio.gather(*launches)
    assert len(retained) == 2
    assert retained[0].actual is not retained[1].actual
    # SHORTCUT: harness launches already closed these inert runners. Scope
    # reuses completed close tasks, not overlapping live outer-close initiation.
    tasks = [lease.start_close() for lease in retained]
    await asyncio.gather(*(lease.aclose() for lease in retained))
    for lease in retained:
        _assert_actually_closed(lease)
    assert all(lease.close_calls == 1 for lease in retained)
    assert all(lease.validations == [5.0] for lease in retained)
    assert len(set(tasks)) == 2 and all(task.done() for task in tasks)
    assert all(result.exit_code == 0 for result in results)
    assert all(len(policy.requests) == 1 for policy in policies)
    for lease, task in zip(retained, tasks, strict=True):
        await lease.aclose()
        assert lease.close_task is task and lease.close_calls == 1
        with pytest.raises(ProgramInfrastructureError, match="lease unavailable"):
            await lease.run_program("print(42)", timeout=5)


def test_real_public_factory_shares_one_actual_close_per_runner(tmp_path):
    asyncio.run(asyncio.wait_for(_exercise(tmp_path), 5))


def test_timeout_validation_remains_original_and_premodel(tmp_path):
    async def probe():
        fixture = _fixture(tmp_path)
        fixture.config = fixture.config.model_copy(update={"program_timeout": 8.0})
        harness = _build(fixture)
        retained = []
        _install(harness, retained)
        policy = fixture.dep.Policy(fixture.dep.assistant(None))
        harness.transport = policy.transport()
        with pytest.raises(ProgramInfrastructureError, match="native program timeout"):
            await fixture.dep.launch(harness, fixture.data)
        assert len(retained) == 1
        lease, = retained
        assert lease.validations == [8.0] and policy.requests == []
        await lease.aclose()
        _assert_actually_closed(lease)
        assert lease.close_calls == 1 and lease.close_task.done()
    asyncio.run(asyncio.wait_for(probe(), 5))


def test_omitted_actual_close_hits_named_gate_then_restored_passes(tmp_path):
    with pytest.raises(AssertionError, match="^PROGRAM_RUNNER_NOT_CLOSED$"):
        asyncio.run(asyncio.wait_for(_exercise(tmp_path / "negative", omit_close=True), 5))
    # Fresh fixtures, two actual original runners and a fresh loop.
    asyncio.run(asyncio.wait_for(_exercise(tmp_path / "restored"), 5))
