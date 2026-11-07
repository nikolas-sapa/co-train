"""Explicit private-task binding for creator-owned SQL SCORER invocations.

Construction is inert. Admission checks existing expected pins and DB identity;
instrument metadata fingerprints do not establish independent provenance.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path

from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_isolation as core
from train.sql_episodes import InstrumentSettings, _validate_instrument

__all__ = [
    "build_owned_sql_scorer", "OwnedSqlScorer", "ScoreInfrastructureError",
]


class ScoreInfrastructureError(RuntimeError):
    """An owned scoring failure, never a fabricated EX result or reward."""


def _fingerprint(record: SqlTask | InstrumentSettings) -> str:
    return hashlib.sha256(core.canonical_json_bytes(record)).hexdigest()


def _request(task: SqlTask, predicted_sql: str, db_sha256: str,
             instrument: InstrumentSettings) -> core.ScoreRequest:
    return core.ScoreRequest(
        replace(task, db_path="/db.sqlite"), predicted_sql,
        instrument.scorer_timeout_s, instrument.scorer_max_rows,
        instrument.compare, db_sha256)


def _validate_binding(task, executor, db_sha256, instrument) -> None:
    if (type(task) is not SqlTask or type(executor) is not core.PilotExecutor
            or type(instrument) is not InstrumentSettings):
        raise ValueError("concrete scorer binding required")
    _validate_instrument(instrument)
    core._digest(db_sha256)
    if (type(task.db_path) is not str or not task.db_path
            or "\x00" in task.db_path or not os.path.isabs(task.db_path)
            or os.path.normpath(task.db_path) != task.db_path):
        raise ValueError("canonical absolute scorer database path required")
    # Validate all task fields and native score scalar rules, not PROGRAM's
    # code/nonempty or fixed-five-second rules. No file inspection occurs.
    _request(task, "", db_sha256, instrument)


@dataclass
class _Job:
    invocation: core.OwnedSqlInvocation
    request_sha256: str
    snapshot: core.InvocationSnapshot | None = None
    close_task: asyncio.Task | None = None
    ack: core.CleanupCompleteAck | None = None
    completion: core.InvocationCompletion | None = None
    _close_failed: bool = False


class OwnedSqlScorer:
    """One explicitly admitted binding, retaining every invocation and proof.

    Gold is necessarily retained privately and belongs only in SCORER requests.
    Unknown execution/cleanup remains owned and pending, without an outer timer.
    """

    def __init__(self, *, task: SqlTask, executor: core.PilotExecutor,
                 db_sha256: str, instrument: InstrumentSettings):
        try:
            _validate_binding(task, executor, db_sha256, instrument)
            task_digest = _fingerprint(task)
            instrument_digest = _fingerprint(instrument)
            profile_digest = core.execution_profile_sha256(executor.profile)
        except Exception:
            raise ScoreInfrastructureError("invalid owned SQL scorer binding") from None
        self._task = task
        self._executor = executor
        self._instrument = instrument
        self._db_path = task.db_path
        self._db_sha256 = db_sha256
        self._task_digest = task_digest
        self._instrument_digest = instrument_digest
        self._profile = executor.profile
        self._profile_digest = profile_digest
        self._state_dir = executor.state_dir
        self._database: core.ProgramDatabaseIdentity | None = None
        self._jobs: list[_Job] = []
        self._closed = False

    def _check_binding(self) -> None:
        try:
            _validate_binding(
                self._task, self._executor, self._db_sha256, self._instrument)
            if (_fingerprint(self._task) != self._task_digest
                    or _fingerprint(self._instrument) != self._instrument_digest
                    or self._executor.profile is not self._profile
                    or core.execution_profile_sha256(self._executor.profile) != self._profile_digest
                    or self._executor.state_dir is not self._state_dir):
                raise ValueError("scorer binding changed")
        except Exception:
            raise ScoreInfrastructureError("owned SQL scorer binding changed") from None

    def _fresh_admission(self) -> core.ProgramDatabaseIdentity:
        try:
            identity = self._executor.admit_program(
                db_path=self._db_path, db_sha256=self._db_sha256)
            if (type(identity) is not core.ProgramDatabaseIdentity
                    or identity.path != self._db_path
                    or identity.sha256 != self._db_sha256
                    or self._database is not None and identity != self._database):
                raise ValueError("scorer database changed")
            return identity
        except Exception:
            raise ScoreInfrastructureError("owned SQL scorer admission failed") from None

    def admit(self) -> None:
        """Explicitly seal initial admission; subsequent calls never reseal."""
        if self._closed:
            raise ScoreInfrastructureError("owned SQL scorer is closed")
        self._check_binding()
        identity = self._fresh_admission()
        if self._database is None:
            self._database = identity

    def _check_invocation(self, job: _Job) -> None:
        owner = job.invocation
        snapshot = job.snapshot
        if (type(owner) is not core.OwnedSqlInvocation
                or type(snapshot) is not core.InvocationSnapshot
                or owner.executor is not self._executor
                or owner.db_path != Path(self._db_path)
                or type(owner.request) is not core.ScoreRequest
                or owner.role != "scorer" or snapshot.role != "scorer"
                or snapshot.invocation_id != owner.invocation_id
                or snapshot.request_sha256 != job.request_sha256
                or owner.request_digest != job.request_sha256
                or core.request_sha256(owner.request) != job.request_sha256
                or snapshot.profile_sha256 != self._profile_digest
                or owner.profile_digest != self._profile_digest):
            raise ScoreInfrastructureError("owned SQL scorer invocation mismatch")

    def _check_ack(self, job: _Job, ack: core.CleanupCompleteAck) -> None:
        self._check_invocation(job)
        owner = job.invocation
        expected = job.snapshot
        current = owner.snapshot()
        if (type(ack) is not core.CleanupCompleteAck
                or type(ack._authority) is not core._AckAuthority
                or ack._authority is not owner._authority
                or ack._authority.owner is not owner
                or ack._authority.ack is not ack
                or ack.invocation_id != expected.invocation_id
                or ack.role != "scorer"
                or ack.request_sha256 != job.request_sha256
                or ack.profile_sha256 != self._profile_digest
                or ack.released is not True
                or type(ack.not_started) is not bool
                or any(type(value) is not int for value in (
                    ack.cleanup_trigger_ns, ack.completed_ns, ack.cleanup_deadline_ns))
                or not 0 <= ack.cleanup_trigger_ns <= ack.completed_ns <= ack.cleanup_deadline_ns
                or type(current) is not core.InvocationSnapshot
                or current.state != "HOST_SEALED" or current.incomplete
                or current.invocation_id != expected.invocation_id
                or current.role != expected.role
                or current.request_sha256 != expected.request_sha256
                or current.profile_sha256 != expected.profile_sha256):
            raise ScoreInfrastructureError("owned SQL scorer cleanup acknowledgment mismatch")
        if ack.not_started:
            if ack.terminal_ack_sha256 is not None or ack.guardian_reaps:
                raise ScoreInfrastructureError("owned SQL scorer cleanup evidence mismatch")
        elif (not ack.guardian_reaps or ack.child_waits is not True
              or ack.thread_joins is not True or ack.terminal_ack_sha256 is None):
            raise ScoreInfrastructureError("owned SQL scorer cleanup evidence mismatch")
        actual = owner._completion
        if (type(actual) is not core.InvocationCompletion
                or actual.cleanup_ack is not ack
                or job.completion is not None and job.completion is not actual):
            raise ScoreInfrastructureError("owned SQL scorer completion acknowledgment mismatch")
        core.InvocationCompletion.__post_init__(actual)

    @staticmethod
    def _ensure_close_task(job: _Job) -> asyncio.Task:
        # Synchronous registration: shutdown can start *all* owners before
        # joining one, and operation-finally joins exactly these same tasks.
        if job.close_task is None:
            job.close_task = asyncio.create_task(job.invocation.aclose())
        return job.close_task

    async def _join_close(self, job: _Job) -> None:
        task = self._ensure_close_task(job)
        cancellations = []
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancellations.append(exc)
            except Exception:
                break
        try:
            ack = task.result()
            if job._close_failed:
                raise ScoreInfrastructureError("owned SQL scorer cleanup previously failed")
            self._check_ack(job, ack)
        except (Exception, asyncio.CancelledError) as exc:
            job._close_failed = True
            job.ack = None
            error = ScoreInfrastructureError("owned SQL scorer cleanup failed")
            for cancellation in cancellations:
                error.add_note(f"secondary cleanup cancellation: {cancellation!r}")
            raise error from exc
        job.ack = ack
        if cancellations:
            for cancellation in cancellations[1:]:
                cancellations[0].add_note(f"secondary cleanup cancellation: {cancellation!r}")
            raise cancellations[0]

    async def score_sql(self, predicted_sql: str) -> ExResult:
        if self._closed or self._database is None:
            raise ScoreInfrastructureError("owned SQL scorer is not admitted")
        self._check_binding()
        self._fresh_admission()
        try:
            expected = _request(
                self._task, predicted_sql, self._db_sha256, self._instrument)
            digest = core.request_sha256(expected)
            invocation = self._executor.owned_score(
                predicted_sql, self._task, db_sha256=self._db_sha256,
                instrument=self._instrument)
        except Exception:
            raise ScoreInfrastructureError("owned SQL scorer allocation failed") from None
        # Retain the actual allocation even if its subsequent inspection fails.
        # No await occurs between allocation, registration and execute.
        job = _Job(invocation, digest)
        self._jobs.append(job)
        body_error = None
        cancelled_completion_error = None
        try:
            job.snapshot = invocation.snapshot()
            self._check_invocation(job)
            if invocation.request != expected:
                raise ScoreInfrastructureError("owned SQL scorer request mismatch")
            completion = await invocation.execute()
            job.completion = completion
            if type(completion) is not core.InvocationCompletion:
                raise ScoreInfrastructureError("owned SQL scorer malformed completion")
            core.InvocationCompletion.__post_init__(completion)
            self._check_ack(job, completion.cleanup_ack)
            outcome = completion.outcome
            if (completion.abort is not None or type(outcome) is not core.ScoreOutcome
                    or outcome.abort is not None or type(outcome.result) is not ExResult):
                error = ScoreInfrastructureError("owned SQL scorer did not complete")
                if completion.abort is not None and completion.abort.kind == "cancelled":
                    cancelled_completion_error = error
                raise error
            core.ScoreOutcome.__post_init__(outcome)
            # Includes native invalid-task results. No copy, reward conversion,
            # extraction or reconstructed result crosses this boundary.
            return outcome.result
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            try:
                await self._join_close(job)
            except BaseException as secondary:
                if (isinstance(secondary, asyncio.CancelledError)
                        and body_error is cancelled_completion_error
                        and cancelled_completion_error is not None):
                    raise
                if body_error is not None:
                    raise body_error from secondary
                raise

    async def aclose(self) -> None:
        self._closed = True
        # Never let an unresolved first owner prevent cancellation of another.
        for job in self._jobs:
            self._ensure_close_task(job)
        cancelled = None
        failed = False
        for job in self._jobs:
            try:
                await self._join_close(job)
            except asyncio.CancelledError as exc:
                if cancelled is None:
                    cancelled = exc
            except Exception:
                failed = True
        if failed:
            raise ScoreInfrastructureError("owned SQL scorer cleanup failed") from None
        if cancelled is not None:
            raise cancelled


def build_owned_sql_scorer(
    *, task: SqlTask, executor: core.PilotExecutor,
    db_sha256: str, instrument: InstrumentSettings,
) -> OwnedSqlScorer:
    """Construct an inert private scorer; call admit explicitly before scoring."""
    return OwnedSqlScorer(
        task=task, executor=executor, db_sha256=db_sha256, instrument=instrument)
