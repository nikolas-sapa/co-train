"""Pure-unit SCORER sensitivity controls. Source delivery is not actor proof."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
SOURCES = (
    REPO / "ptc/sql_owned_score.py",
    REPO / "ptc/sql_isolation.py",
    REPO / "ptc/harness.py",
    REPO / "ptc/sql_owned_program.py",
)
CASES = {
    "retained-close": "SCORER_RETAINED_CLOSE_OMITTED",
    "abort-to-zero": "SCORER_INFRASTRUCTURE_BECAME_ZERO_RESULT",
}
EXPECTED_ERROR = "owned SQL scorer did not complete"
CHILD_TIMEOUT = 20.0
MAX_RECEIPT_BYTES = 32768


def _hashes():
    return {str(path.relative_to(REPO)): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in SOURCES}


class _Discard:
    """Discard incidental output without retaining private values or logs."""

    def write(self, value):
        return len(value)

    def flush(self):
        pass


def _guards(stack, core, attempts):
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("forbidden scorer control operation")

    for name in (
            "_stage_sources", "_stage_database", "_secure_directory",
            "_activate_staged_import_root", "_spawn_owned_guardian",
            "_owned_boundary_io", "_run_isolated", "_native_call",
            "_guardian", "_owned_guardian"):
        stack.enter_context(patch.object(core, name, deny))
    for name in ("score_sql", "run_program", "owned_program"):
        stack.enter_context(patch.object(core.PilotExecutor, name, deny))
    stack.enter_context(patch.object(core._OwnedBoundaryIO, "__init__", deny))
    stack.enter_context(patch.object(core.OwnedSqlInvocation, "_spawn", deny))
    stack.enter_context(patch.object(core._CreatorPopen, "__init__", deny))
    stack.enter_context(patch.object(subprocess, "Popen", deny))
    stack.enter_context(patch.object(threading.Thread, "start", deny))
    stack.enter_context(patch.object(sqlite3, "connect", deny))
    for name in ("connect", "connect_ex", "bind"):
        stack.enter_context(patch.object(socket.socket, name, deny))
    for name in (
            "getaddrinfo", "gethostbyname", "gethostbyname_ex",
            "gethostbyaddr", "getnameinfo", "create_connection"):
        stack.enter_context(patch.object(socket, name, deny))
    for name in ("kill", "killpg"):
        stack.enter_context(patch.object(os, name, deny))


def _retained_close_valid(jobs, core):
    if len(jobs) != 1:
        return False
    job, = jobs
    task = job.close_task
    return bool(
        isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
        and task.exception() is None
        and type(job.completion) is core.InvocationCompletion
        and job.ack is job.completion.cleanup_ack
        and task.result() is job.ack)


async def _scenario(case, bypass, root, core, api, unit, ExResult, receipt):
    # Worker installs DENY guards before this fixture, also for positives.
    fixture = unit._fixture(root)
    scorer = api.build_owned_sql_scorer(
        task=fixture.task, executor=fixture.executor,
        db_sha256=fixture.digest, instrument=fixture.instrument)
    assert type(scorer) is api.OwnedSqlScorer, "actual scorer missing"
    original_owned = core.PilotExecutor.owned_score
    original_execute = core.OwnedSqlInvocation.execute
    original_close = core.OwnedSqlInvocation.aclose
    original_score = api.OwnedSqlScorer.score_sql
    original_admit = core.PilotExecutor.admit_program
    owners, jobs, completions, mutant_results = [], [], [], []
    dropped = set()
    safety_draining = False
    receipt.update(
        bypass_hits=0, admissions=0, owners=0, actual_close_calls=0,
        adapter_close_calls=0, adapter_close_acknowledged=False,
        execution_completions=0, independent_owner_drains=0,
        api_error_expected=False, result_is_none=False,
        api_returned_cleanly=False, mutant_error_expected=False,
        manufactured_result_exact=False, retained_close_valid=False,
        retained_job_valid=False, owner_ack_identity_valid=False,
        actor_free=False, safety_complete=False,
    )

    def observed_admit(executor, **kwargs):
        identity = original_admit(executor, **kwargs)
        receipt["admissions"] += 1
        return identity

    def cancelled_owner(executor, *args, **kwargs):
        owner = original_owned(executor, *args, **kwargs)
        owners.append(owner)  # Immediately retain the real allocation.
        owner.request_cancel("runner_closed")
        assert type(owner) is core.OwnedSqlInvocation, "actual owner missing"
        return owner

    async def observed_execute(owner):
        if safety_draining:
            return await original_execute(owner)
        if not any(job.invocation is owner for job in jobs):
            job, = scorer._jobs
            assert job.invocation is owner, "scorer owner not retained before execute"
            assert job.snapshot.state == "ABORT_LATCHED", (
                "scorer owner was not cancelled before dispatch")
            jobs.append(job)
        completion = await original_execute(owner)
        if not any(item is completion for item in completions):
            completions.append(completion)
        return completion

    async def observed_close(owner):
        receipt["actual_close_calls"] += 1
        job, = [job for job in jobs if job.invocation is owner]
        assert job.close_task is asyncio.current_task(), (
            "scorer public close task not retained before await")
        return await original_close(owner)

    async def omit_close(actual_scorer, job):
        # Deliberate negative: drop lifetime bookkeeping before explicit
        # shutdown, so its all-starts loop cannot rescue the omitted close.
        if id(job) not in dropped:
            dropped.add(id(job))
            receipt["bypass_hits"] += 1
        actual_scorer._jobs[:] = [
            item for item in actual_scorer._jobs if item is not job]
        return None

    async def abort_to_zero(actual_scorer, predicted_sql):
        try:
            return await original_score(actual_scorer, predicted_sql)
        except api.ScoreInfrastructureError as exc:
            receipt["bypass_hits"] += 1
            receipt["mutant_error_expected"] = (
                type(exc) is api.ScoreInfrastructureError
                and str(exc) == EXPECTED_ERROR)
            # Explicit manufactured RESULT, negative fault only. Never a
            # completion, ACK, reward record or positive-path resource proof.
            mutant_result = ExResult(
                0.0, "pred_error", True, "CONTROL abort-to-zero", 0, 0)
            mutant_results.append(mutant_result)
            return mutant_result

    with ExitStack() as mutations:
        mutations.enter_context(patch.object(
            core.PilotExecutor, "owned_score", cancelled_owner))
        mutations.enter_context(patch.object(
            core.PilotExecutor, "admit_program", observed_admit))
        mutations.enter_context(patch.object(
            core.OwnedSqlInvocation, "execute", observed_execute))
        mutations.enter_context(patch.object(
            core.OwnedSqlInvocation, "aclose", observed_close))
        if bypass:
            name = "_join_close" if case == "retained-close" else "score_sql"
            replacement = omit_close if case == "retained-close" else abort_to_zero
            mutations.enter_context(patch.object(
                api.OwnedSqlScorer, name, replacement))

        result = error = None
        try:
            try:
                assert scorer.admit() is None, "explicit admission did not acknowledge"
                try:
                    result = await scorer.score_sql(unit.PREDICTION)
                except api.ScoreInfrastructureError as exc:
                    error = exc
            finally:
                receipt["adapter_close_calls"] += 1
                close_result = await scorer.aclose()
                receipt["adapter_close_acknowledged"] = close_result is None

            # Freeze operation/shutdown decisions before assertions or safety.
            # No independent drain can upgrade these observations.
            receipt["owners"] = len(owners)
            receipt["execution_completions"] = len(completions)
            receipt["api_error_expected"] = (
                type(error) is api.ScoreInfrastructureError
                and str(error) == EXPECTED_ERROR)
            receipt["result_is_none"] = result is None
            receipt["api_returned_cleanly"] = error is None
            receipt["manufactured_result_exact"] = bool(
                len(mutant_results) == 1 and result is mutant_results[0]
                and type(result) is ExResult
                and (result.score, result.status, result.valid, result.detail,
                     result.n_pred_rows, result.n_gold_rows)
                == (0.0, "pred_error", True, "CONTROL abort-to-zero", 0, 0))
            receipt["retained_close_valid"] = _retained_close_valid(jobs, core)
            receipt["retained_job_valid"] = (
                len(jobs) == len(scorer._jobs) == 1
                and scorer._jobs[0] is jobs[0])

            # FIRST assertions after API decision plus explicit shutdown.
            # No pytest.raises: only the exact intended assertion can qualify.
            if case == "retained-close":
                assert receipt["actual_close_calls"] == 1, CASES[case]
            else:
                assert result is None, CASES[case]
            assert receipt["api_error_expected"], "unexpected scorer API decision"
            assert receipt["result_is_none"], "scorer returned an unexpected result"
            assert receipt["adapter_close_acknowledged"], "adapter close result invalid"
            assert receipt["admissions"] == 2, "fresh admission count mismatch"
            assert len(owners) == len(jobs) == len(completions) == 1, (
                "scorer owner or completion count mismatch")
            assert receipt["actual_close_calls"] == 1, "public close count mismatch"
            assert receipt["retained_close_valid"], "retained close task or ACK invalid"
            assert receipt["retained_job_valid"], "retained scorer job omitted"
        finally:
            # Every actual owner is drained using ORIGINAL public aclose,
            # regardless of the assertion/API decision. Observation wrappers
            # cannot obstruct partial-owner safety by demanding a retained job.
            safety_draining = True
            safety_errors = []
            for owner in owners:
                try:
                    completion = owner._completion
                    snapshot = owner.snapshot()
                    actor_free_before = (
                        owner._thread is None and not owner._children
                        and not owner._resources and not owner._endpoints
                        and owner._host_read is None
                        and owner._seal_lock_fd is None)
                    # Drain first, then evaluate the captured pre-drain proof.
                    drained_ack = await original_close(owner)
                    receipt["independent_owner_drains"] += 1
                    assert type(completion) is core.InvocationCompletion, (
                        "scorer owner was not terminal before safety drain")
                    ack = completion.cleanup_ack
                    assert (
                        type(ack) is core.CleanupCompleteAck
                        and type(ack._authority) is core._AckAuthority
                        and ack._authority is owner._authority
                        and ack._authority.owner is owner
                        and ack._authority.ack is ack
                        and ack.not_started is True and ack.released is True
                        and ack.terminal_ack_sha256 is None
                        and not ack.guardian_reaps
                        and ack.child_waits is False and ack.thread_joins is False
                        and ack.invocation_id == snapshot.invocation_id
                        and ack.role == snapshot.role == owner.role == "scorer"
                        and ack.request_sha256 == snapshot.request_sha256
                        == core.request_sha256(owner.request)
                        and ack.profile_sha256 == snapshot.profile_sha256
                        == core.execution_profile_sha256(fixture.executor.profile)
                        and snapshot.state == "HOST_SEALED"
                        and snapshot.incomplete is False
                        and snapshot.intent.reason == "runner_closed"
                        and completion.outcome is None
                        and type(completion.abort) is core.OutcomeAbort
                        and completion.abort.kind == "cancelled"
                        and completion.abort.invocation_id == ack.invocation_id
                        and completion.abort.role == "scorer"
                        and completion is owner._completion
                        and drained_ack is ack
                    ), "actual scorer NOT_STARTED completion or ACK invalid"
                    assert (
                        len(jobs) == 1 and jobs[0].invocation is owner
                        and jobs[0].completion is completion
                        and jobs[0].snapshot.invocation_id == ack.invocation_id
                        and jobs[0].snapshot.request_sha256 == ack.request_sha256
                        and jobs[0].snapshot.profile_sha256 == ack.profile_sha256
                    ), "actual scorer job completion identity invalid"
                    assert (
                        actor_free_before and owner._thread is None
                        and not owner._children and not owner._resources
                        and not owner._endpoints and owner._host_read is None
                        and owner._seal_lock_fd is None
                    ), "scorer unit owner acquired actor resources"
                except BaseException as exc:
                    safety_errors.append(exc)
            receipt["owner_ack_identity_valid"] = not safety_errors
            receipt["actor_free"] = not safety_errors
            receipt["safety_complete"] = (
                not safety_errors
                and receipt["independent_owner_drains"] == len(owners))
            if safety_errors:
                raise AssertionError("independent scorer owner safety drain failed")


def _worker(case, bypass):
    receipt = {
        "case": case, "bypass": bypass, "accepted": False,
        "named_assertion": None, "unexpected_failure": False,
        "no_pending_tasks": False, "patches_restored": False,
    }
    before = _hashes()
    attempts = []
    loop = None
    try:
        sys.path.insert(0, str(REPO))
        from bench.score import ExResult
        from ptc import sql_isolation as core
        from ptc import sql_owned_score as api
        from ptc import test_sql_owned_score as unit

        # No TaskData, harness launch, SDK client or policy/model is needed.
        originals = (
            api.OwnedSqlScorer._join_close, api.OwnedSqlScorer.score_sql,
            core.PilotExecutor.owned_score, core.PilotExecutor.admit_program,
            core.OwnedSqlInvocation.execute, core.OwnedSqlInvocation.aclose,
        )
        # Create only asyncio's anonymous self-pipe before network DENY guards.
        loop = asyncio.new_event_loop()
        with ExitStack() as guards:
            _guards(guards, core, attempts)
            with tempfile.TemporaryDirectory(
                    prefix="owned-scorer-unit-") as directory:
                try:
                    task = loop.create_task(_scenario(
                        case, bypass, Path(directory).resolve(),
                        core, api, unit, ExResult, receipt))
                    _, pending = loop.run_until_complete(
                        asyncio.wait({task}, timeout=5.0))
                    if pending:
                        raise AssertionError("scorer control observation deadline exceeded")
                    task.result()
                except AssertionError as exc:
                    if type(exc) is AssertionError and str(exc) == CASES[case]:
                        receipt["named_assertion"] = CASES[case]
                    else:
                        receipt["unexpected_failure"] = True
                except BaseException:
                    receipt["unexpected_failure"] = True
                finally:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        _, pending = loop.run_until_complete(
                            asyncio.wait(pending, timeout=0.25))
                    receipt["no_pending_tasks"] = not pending
                    loop.close()
                    loop = None
        receipt["patches_restored"] = originals == (
            api.OwnedSqlScorer._join_close, api.OwnedSqlScorer.score_sql,
            core.PilotExecutor.owned_score, core.PilotExecutor.admit_program,
            core.OwnedSqlInvocation.execute, core.OwnedSqlInvocation.aclose,
        )
    except BaseException:
        receipt["unexpected_failure"] = True
    finally:
        if loop is not None:
            loop.close()
    after = _hashes()
    receipt.update(
        forbidden_attempts=len(attempts), source_hashes_before=before,
        source_hashes_after=after, source_unchanged=before == after,
    )
    omitted = bypass and case == "retained-close"
    fabricated = bypass and case == "abort-to-zero"
    receipt["accepted"] = bool(
        not receipt["unexpected_failure"] and not attempts and before == after
        and receipt["no_pending_tasks"] and receipt["patches_restored"]
        and receipt.get("safety_complete") and receipt.get("actor_free")
        and receipt.get("owner_ack_identity_valid")
        and receipt.get("bypass_hits") == int(bypass)
        and receipt.get("admissions") == 2 and receipt.get("owners") == 1
        and receipt.get("execution_completions") == 1
        and receipt.get("independent_owner_drains") == 1
        and receipt.get("adapter_close_calls") == 1
        and receipt.get("adapter_close_acknowledged") is True
        and receipt.get("actual_close_calls") == (0 if omitted else 1)
        and receipt.get("retained_close_valid") == (not omitted)
        and receipt.get("retained_job_valid") == (not omitted)
        and receipt.get("api_error_expected") == (not fabricated)
        and receipt.get("result_is_none") == (not fabricated)
        and receipt.get("api_returned_cleanly") == fabricated
        and receipt.get("mutant_error_expected") == fabricated
        and receipt.get("manufactured_result_exact") == fabricated
        and receipt["named_assertion"] == (CASES[case] if bypass else None)
    )
    return receipt


def _write_receipt(directory, name, receipt):
    with (directory / name).open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")


def _launcher(artifacts):
    before = _hashes()
    runs = []
    for case in CASES:
        for bypass in (True, False):
            label = case + ("-bypass" if bypass else "-restored")
            command = [
                sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                "--artifacts-dir", str(artifacts), "--worker", case,
            ]
            if bypass:
                command.append("--bypass")
            run = {"case": case, "bypass": bypass, "accepted": False}
            try:
                # Launcher only: one directly owned interpreter at a time.
                # Timeout uses direct-child kill/wait, never process groups.
                with tempfile.TemporaryFile() as output:
                    result = subprocess.run(
                        command, cwd=REPO, stdin=subprocess.DEVNULL,
                        stdout=output, stderr=subprocess.DEVNULL,
                        timeout=CHILD_TIMEOUT, check=False, shell=False,
                    )
                    output.seek(0)
                    raw = output.read(MAX_RECEIPT_BYTES + 1)
                if len(raw) > MAX_RECEIPT_BYTES:
                    raise ValueError("oversized child receipt")
                child = json.loads(raw)
                if not isinstance(child, dict):
                    raise ValueError("invalid child receipt")
                run.update(
                    child_receipt=child, exit_code=result.returncode,
                    accepted=(
                        result.returncode == 0 and child.get("accepted") is True
                        and child.get("case") == case
                        and child.get("bypass") is bypass
                        and child.get("source_hashes_before") == before
                        and child.get("source_hashes_after") == before),
                )
            except subprocess.TimeoutExpired:
                run["timeout"] = True
            except (ValueError, OSError):
                run["invalid_child_receipt"] = True
            _write_receipt(artifacts, label + ".json", run)
            runs.append(run)
    after = _hashes()
    receipt = {
        "accepted": len(runs) == 4 and all(
            run["accepted"] for run in runs) and before == after,
        "runs": [{"case": run["case"], "bypass": run["bypass"],
                  "accepted": run["accepted"]} for run in runs],
        "source_hashes_before": before, "source_hashes_after": after,
        "source_unchanged": before == after,
    }
    _write_receipt(artifacts, "controls.json", receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["accepted"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--worker", choices=CASES)
    parser.add_argument("--bypass", action="store_true")
    args = parser.parse_args()
    if not args.artifacts_dir.is_absolute():
        parser.error("--artifacts-dir must be absolute")
    if args.bypass and args.worker is None:
        parser.error("--bypass requires --worker")
    artifacts = args.artifacts_dir.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    if args.worker:
        with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            receipt = _worker(args.worker, args.bypass)
        encoded = json.dumps(receipt, sort_keys=True)
        if len(encoded.encode("utf-8")) > MAX_RECEIPT_BYTES:
            print('{"accepted": false, "oversized_receipt": true}')
            return 1
        print(encoded)
        return 0 if receipt["accepted"] else 1
    return _launcher(artifacts)


if __name__ == "__main__":
    raise SystemExit(main())
