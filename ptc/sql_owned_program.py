"""Explicit, inert host binding for the owned SQL PROGRAM execution path.

This adapter does not establish task provenance or activate a native profile.
Only public TaskData and sealed execution scalars survive construction.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any

from verifiers.v1.task import TaskData

from bench.task import SqlTask
from ptc import sql_arms
from ptc import sql_isolation as core
from ptc.harness import PTCHarness, PTCHarnessConfig, ProgramInfrastructureError
from ptc.runtime import Catalog


def _finite_numbers(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite host number")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_numbers(key)
            _finite_numbers(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _finite_numbers(item)


def _json_digest(value: Any, *, bounded: bool = False) -> str:
    try:
        # JSON-mode serializers can normalize NaN/inf to null. Reject the
        # original numbers first, rather than seal a lossy fingerprint.
        _finite_numbers(value.model_dump(mode="python"))
        raw = json.dumps(
            value.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
            allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")
    except Exception:
        raise ValueError("owned SQL binding requires finite UTF-8 JSON") from None
    if bounded and len(raw) > core.MAX_MESSAGES_TOOLS_BYTES:
        raise ValueError("owned SQL host data exceeds bound")
    return hashlib.sha256(raw).hexdigest()


def _data_digest(data: TaskData) -> str:
    if not isinstance(data, TaskData) or getattr(data, "image", None) is not None:
        raise ValueError("owned SQL requires plaintext TaskData")
    return _json_digest(data, bounded=True)


class _Binding:
    """Live public references, expected fingerprints, no private SqlTask."""

    def __init__(self, config, data, executor, db_path, db_sha256, max_rows, catalog):
        self.config = config
        self.data = data
        self.name = data.name
        self.data_digest = _data_digest(data)
        self.config_digest = _json_digest(config)
        self.executor = executor
        self.profile = executor.profile
        self.profile_digest = core.execution_profile_sha256(executor.profile)
        self.state_dir = executor.state_dir
        self.db_path = db_path
        self.db_sha256 = db_sha256
        self.max_rows = max_rows
        self.catalog = catalog
        self.callbacks = dict(catalog.tools)
        self.harness: PTCHarness | None = None

    def check(self, data, compiled, print_callback):
        try:
            if (data is not self.data or data.name != self.name
                    or _data_digest(data) != self.data_digest
                    or type(self.config) is not PTCHarnessConfig
                    or _json_digest(self.config) != self.config_digest
                    or type(self.executor) is not core.PilotExecutor
                    or self.executor.profile is not self.profile
                    or core.execution_profile_sha256(self.executor.profile) != self.profile_digest
                    or self.executor.state_dir != self.state_dir
                    or self.harness is None
                    or self.harness.config is not self.config
                    or self.harness.catalog is not self.catalog
                    or set(self.catalog.tools) != set(self.callbacks)
                    or set(compiled.tools) != set(self.callbacks) | {"print"}
                    or not callable(print_callback)
                    or compiled.tools["print"] is not print_callback
                    or any(self.catalog.tools[name] is not callback
                           or compiled.tools[name] is not callback
                           for name, callback in self.callbacks.items())):
                raise ValueError("binding changed")
        except Exception:
            raise ProgramInfrastructureError("owned SQL binding changed") from None


@dataclass
class _Job:
    invocation: core.OwnedSqlInvocation
    snapshot: core.InvocationSnapshot
    close_task: asyncio.Task | None = None
    ack: core.CleanupCompleteAck | None = None
    completion: core.InvocationCompletion | None = None


class _Runner:
    def __init__(self, binding: _Binding, data: TaskData, catalog: Catalog):
        self._binding = binding
        self._data = data
        self._catalog = catalog
        self._print = catalog.tools["print"]
        self._database: core.ProgramDatabaseIdentity | None = None
        self._jobs: list[_Job] = []
        self._closed = False

    def _check(self):
        self._binding.check(self._data, self._catalog, self._print)

    @staticmethod
    def _timeout(timeout):
        if type(timeout) not in (int, float) or timeout != 5:
            raise ProgramInfrastructureError("owned SQL requires the native program timeout")

    def _admit(self):
        binding = self._binding
        try:
            identity = binding.executor.admit_program(
                db_path=binding.db_path, db_sha256=binding.db_sha256)
            if type(identity) is not core.ProgramDatabaseIdentity:
                raise ValueError("invalid admission identity")
            if self._database is not None and self._database != identity:
                raise ValueError("database changed")
            return identity
        except Exception:
            raise ProgramInfrastructureError("owned SQL admission failed") from None

    def validate_program_timeout(self, timeout):
        self._timeout(timeout)
        self._check()
        if self._closed:
            raise ProgramInfrastructureError("owned SQL runner is closed")
        self._database = self._admit()

    def _check_ack(self, job, ack):
        owner = job.invocation
        snapshot = owner.snapshot()
        expected = job.snapshot
        if (type(ack) is not core.CleanupCompleteAck
                or ack.invocation_id != expected.invocation_id
                or ack.role != "program" or ack.role != expected.role
                or ack.request_sha256 != expected.request_sha256
                or ack.profile_sha256 != expected.profile_sha256
                or ack.profile_sha256 != self._binding.profile_digest
                or ack.released is not True
                or snapshot.invocation_id != expected.invocation_id
                or snapshot.role != expected.role
                or snapshot.request_sha256 != expected.request_sha256
                or snapshot.profile_sha256 != expected.profile_sha256
                or ack._authority.owner is not owner
                or ack._authority.ack is not ack):
            raise ProgramInfrastructureError("owned SQL cleanup acknowledgment mismatch")
        for completion in (job.completion, owner._completion):
            if completion is not None:
                if (type(completion) is not core.InvocationCompletion
                        or completion.cleanup_ack is not ack):
                    raise ProgramInfrastructureError("owned SQL completion acknowledgment mismatch")

    async def _close_job(self, job):
        # Retain exactly one actual public close task before its first await.
        if job.close_task is None:
            job.close_task = asyncio.create_task(job.invocation.aclose())
        task = job.close_task
        cancelled = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                if cancelled is None:
                    cancelled = exc
            except Exception:
                break
        try:
            ack = task.result()
            self._check_ack(job, ack)
            job.ack = ack
        except (Exception, asyncio.CancelledError):
            raise ProgramInfrastructureError("owned SQL cleanup failed") from None
        if cancelled is not None:
            raise cancelled

    async def run_program(self, code: str, *, timeout: float) -> str:
        self._timeout(timeout)
        self._check()
        if self._closed or self._database is None:
            raise ProgramInfrastructureError("owned SQL runner is not admitted")
        self._admit()
        binding = self._binding
        try:
            invocation = binding.executor.owned_program(
                code, db_path=binding.db_path, db_sha256=binding.db_sha256,
                max_rows=binding.max_rows)
        except Exception:
            raise ProgramInfrastructureError("owned SQL program allocation failed") from None
        # No await separates allocation, registration and actual execute.
        job = _Job(invocation, invocation.snapshot())
        self._jobs.append(job)
        body_cancel = None
        try:
            if (type(invocation) is not core.OwnedSqlInvocation
                    or invocation.executor is not binding.executor
                    or invocation.db_path != core.Path(binding.db_path)
                    or invocation.request != core.ProgramRequest(
                        code, binding.max_rows, binding.db_sha256)
                    or job.snapshot.role != "program"
                    or job.snapshot.request_sha256 != core.request_sha256(invocation.request)
                    or job.snapshot.profile_sha256 != binding.profile_digest):
                raise ProgramInfrastructureError("owned SQL invocation binding mismatch")
            completion = await invocation.execute()
            job.completion = completion
            if type(completion) is not core.InvocationCompletion:
                raise ProgramInfrastructureError("owned SQL malformed completion")
            completion.__post_init__()
            self._check_ack(job, completion.cleanup_ack)
            outcome = completion.outcome
            if (completion.abort is not None or type(outcome) is not core.ProgramOutcome
                    or outcome.abort is not None or type(outcome.observation) is not str):
                raise ProgramInfrastructureError("owned SQL program did not complete")
            outcome.__post_init__()
            return outcome.observation
        except asyncio.CancelledError as exc:
            body_cancel = exc
            raise
        except ProgramInfrastructureError:
            raise
        except Exception:
            raise ProgramInfrastructureError("owned SQL program execution failed") from None
        finally:
            try:
                await self._close_job(job)
            except asyncio.CancelledError:
                if body_cancel is not None:
                    raise body_cancel
                raise

    async def aclose(self) -> None:
        self._closed = True
        cancelled = None
        failure = None
        for job in self._jobs:
            try:
                await self._close_job(job)
            except asyncio.CancelledError as exc:
                if cancelled is None:
                    cancelled = exc
            except Exception as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise ProgramInfrastructureError("owned SQL cleanup failed") from failure
        if cancelled is not None:
            raise cancelled


def build_owned_sql_program_harness(
    config: PTCHarnessConfig, *, data: TaskData, task: SqlTask,
    executor: core.PilotExecutor, db_sha256: str, max_rows: int,
) -> PTCHarness:
    """Bind one caller-associated public task, without file or native IO."""
    if (type(config) is not PTCHarnessConfig or type(task) is not SqlTask
            or type(executor) is not core.PilotExecutor
            or not isinstance(data, TaskData)
            or type(data.name) is not str or not data.name
            or type(task.name) is not str or task.name != data.name):
        raise ValueError("invalid owned SQL task binding")
    core._digest(db_sha256)
    core._integer(max_rows, minimum=1)
    if (type(task.db_path) is not str or not task.db_path
            or "\x00" in task.db_path or not os.path.isabs(task.db_path)
            or os.path.normpath(task.db_path) != task.db_path):
        raise ValueError("canonical absolute database path required")
    _data_digest(data)
    catalog = sql_arms.sql_catalog(task.db_path, max_rows=max_rows)
    if (set(catalog.tools) != {"execute_sql", *sql_arms.SQL_PRIMITIVES}
            or "print" in catalog.tools
            or not all(callable(callback) for callback in catalog.tools.values())
            or any(catalog.tools[name] is not callback
                   for name, callback in sql_arms.SQL_PRIMITIVES.items())):
        raise ValueError("invalid canonical SQL catalog")
    binding = _Binding(
        config, data, executor, task.db_path, db_sha256, max_rows, catalog)

    def factory(actual_data, compiled):
        try:
            print_callback = compiled.tools["print"]
        except Exception:
            raise ProgramInfrastructureError("owned SQL compiled catalog invalid") from None
        binding.check(actual_data, compiled, print_callback)
        return _Runner(binding, actual_data, compiled)

    harness = PTCHarness(config, catalog=catalog, program_runner_factory=factory)
    binding.harness = harness
    return harness
