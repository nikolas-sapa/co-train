"""Fresh-interpreter, pure-unit adapter sensitivity controls, not actor proof."""
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
    REPO / "ptc/sql_owned_program.py",
    REPO / "ptc/sql_isolation.py",
    REPO / "ptc/harness.py",
)
CASES = {
    "retained-close": "owned invocation close omitted",
    "fatal-propagation": "owned abort dispatched another policy request",
    "db-preflight": "DB preflight dispatched a policy request",
}
CHILD_TIMEOUT = 20.0
MAX_RECEIPT_BYTES = 32768


def _hashes():
    return {str(path.relative_to(REPO)): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in SOURCES}


class _Discard:
    """Never retain SDK output, task values, request bodies or exception text."""

    def write(self, value):
        return len(value)

    def flush(self):
        pass


def _guards(stack, core, attempts):
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("forbidden control operation")

    for name in (
            "_stage_sources", "_stage_database", "_secure_directory",
            "_activate_staged_import_root", "_spawn_owned_guardian",
            "_owned_boundary_io", "_run_isolated", "_native_call",
            "_guardian", "_owned_guardian"):
        stack.enter_context(patch.object(core, name, deny))
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


async def _scenario(case, bypass, root, core, adapter, unit, receipt):
    # Caller installs all DENY guards before this fixture or any body work.
    fixture = unit._fixture(root)
    harness = unit._build(fixture)
    dep = fixture.dep
    turns = ([dep.assistant(None)] if case == "db-preflight" else
             [dep.assistant("print(1)"), dep.assistant(None)])
    policy = dep.Policy(*turns)
    harness.transport = policy.transport()
    runners, runner_closes, owners, jobs, completions = [], [], [], [], []
    original_factory = harness.program_runner_factory
    original_owned = core.PilotExecutor.owned_program
    original_execute = core.OwnedSqlInvocation.execute
    original_close = core.OwnedSqlInvocation.aclose
    original_run = adapter._Runner.run_program
    original_read = os.read
    original_fstat = os.fstat
    dropped = set()
    safety_draining = False
    receipt.update(
        policy_requests=0, owners=0, actual_close_calls=0, runner_closes=0,
        independent_owner_drains=0, bypass_hits=0, api_error_expected=False,
        owner_ack_identity_valid=False, actor_free=False,
        retained_close_valid=False, safety_complete=False,
        fatal_bypass_error_expected=False, api_returned_cleanly=False,
    )

    def capture_runner(data, catalog):
        runner = original_factory(data, catalog)
        assert type(runner) is adapter._Runner, "actual adapter runner missing"
        runners.append(runner)
        close = runner.aclose

        async def observed_runner_close():
            runner_closes.append(runner)
            return await close()

        runner.aclose = observed_runner_close
        return runner

    def cancelled_owner(executor, *args, **kwargs):
        owner = original_owned(executor, *args, **kwargs)
        owners.append(owner)  # Retain before any assertion or cancellation.
        assert type(owner) is core.OwnedSqlInvocation, "actual owner missing"
        owner.request_cancel("runner_closed")
        return owner

    async def observed_execute(owner):
        if safety_draining:
            return await original_execute(owner)
        if not any(job.invocation is owner for job in jobs):
            job, = runners[0]._jobs
            assert job.invocation is owner, "owner not retained before execute"
            jobs.append(job)
        completion = await original_execute(owner)
        if not any(item is completion for item in completions):
            completions.append(completion)
        return completion

    async def observed_close(owner):
        receipt["actual_close_calls"] += 1
        job, = [job for job in jobs if job.invocation is owner]
        assert job.close_task is asyncio.current_task(), (
            "public close task not retained before await")
        return await original_close(owner)

    async def omit_close(runner, job):
        # Deliberately remove lifetime bookkeeping so generic runner shutdown
        # cannot rescue the missing public close. Execute already sealed its
        # real NOT_STARTED terminal completion, with no actor ever created.
        if id(job) not in dropped:
            dropped.add(id(job))
            receipt["bypass_hits"] += 1
        runner._jobs[:] = [item for item in runner._jobs if item is not job]
        return None

    async def swallow_fatal(runner, code, *, timeout):
        try:
            return await original_run(runner, code, timeout=timeout)
        except dep.Fatal as exc:
            receipt["bypass_hits"] += 1
            receipt["fatal_bypass_error_expected"] = (
                type(exc) is dep.Fatal
                and str(exc) == "owned SQL program did not complete")
            # Declared mutant feedback only, never an ACK or completion.
            return "CONTROL infrastructure feedback"

    old_bytes = fixture.path.read_bytes()
    db_stat = fixture.path.stat()
    db_descriptor = (db_stat.st_dev, db_stat.st_ino)

    def stale_database_read(fd, size):
        chunk = original_read(fd, size)  # Always advance the actual descriptor.
        if chunk:
            record = original_fstat(fd)
            if ((record.st_dev, record.st_ino) == db_descriptor
                    and receipt["bypass_hits"] == 0):
                receipt["bypass_hits"] += 1
                return old_bytes
        return chunk

    harness.program_runner_factory = capture_runner
    with ExitStack() as mutations:
        mutations.enter_context(patch.object(
            core.PilotExecutor, "owned_program", cancelled_owner))
        mutations.enter_context(patch.object(
            core.OwnedSqlInvocation, "execute", observed_execute))
        mutations.enter_context(patch.object(
            core.OwnedSqlInvocation, "aclose", observed_close))
        if case == "db-preflight":
            assert 0 < len(old_bytes) < 65536, "control DB exceeds one read"
            assert hashlib.sha256(old_bytes).hexdigest() == fixture.digest, (
                "fixture digest mismatch")
            # Actual DB bytes change before launch, without repinning anything.
            fixture.path.write_bytes(bytes([old_bytes[0] ^ 1]) + old_bytes[1:])
            if bypass:
                mutations.enter_context(patch.object(
                    os, "read", stale_database_read))
        elif bypass and case == "retained-close":
            mutations.enter_context(patch.object(
                adapter._Runner, "_close_job", omit_close))
        elif bypass:
            mutations.enter_context(patch.object(
                adapter._Runner, "run_program", swallow_fatal))

        error = None
        result = None
        try:
            try:
                result = await dep.launch(harness, fixture.data)
            except dep.Fatal as exc:
                error = exc
            # Freeze API observations BEFORE safety teardown. Teardown never
            # turns a missing adapter close or successful bad launch into a pass.
            receipt["policy_requests"] = len(policy.requests)
            receipt["owners"] = len(owners)
            receipt["runner_closes"] = len(runner_closes)
            expected_message = ("owned SQL admission failed"
                                if case == "db-preflight" else
                                "owned SQL program did not complete")
            receipt["api_error_expected"] = (
                type(error) is dep.Fatal and str(error) == expected_message)
            receipt["api_returned_cleanly"] = (
                error is None and result is not None and result.exit_code == 0)
            receipt["retained_close_valid"] = bool(
                len(jobs) == 1 and jobs[0].close_task is not None
                and jobs[0].close_task.done()
                and not jobs[0].close_task.cancelled()
                and jobs[0].close_task.exception() is None
                and jobs[0].ack is jobs[0].completion.cleanup_ack
                and jobs[0].close_task.result() is jobs[0].ack)

            # These must be the FIRST assertions after capturing the decision
            # in the propagation/preflight cases. Do not use pytest.raises.
            if case == "fatal-propagation":
                assert len(policy.requests) == 1, CASES[case]
            elif case == "db-preflight":
                assert len(policy.requests) == 0, CASES[case]
            assert receipt["api_error_expected"], "unexpected API error decision"
            assert len(runners) == 1, "runner count mismatch"
            assert runner_closes == runners, "runner close count mismatch"
            if case == "db-preflight":
                assert not owners and not jobs and not runners[0]._jobs, (
                    "DB preflight allocated an owner")
            else:
                assert len(policy.requests) == 1, "abort policy count mismatch"
                assert len(owners) == len(jobs) == len(completions) == 1, (
                    "owner allocation count mismatch")
                assert receipt["actual_close_calls"] == 1, (
                    "owned invocation close omitted")
                assert receipt["retained_close_valid"], (
                    "retained close task or ACK identity invalid")
                assert runners[0]._jobs == jobs, "retained job omitted"
        finally:
            # Independent original public close for EVERY real allocation,
            # including partial failures. Mutant safety is not API success.
            safety_draining = True
            safety_errors = []
            for owner in owners:
                try:
                    completion = owner._completion
                    snapshot = owner.snapshot()
                    actor_free_before_drain = (
                        owner._thread is None and not owner._children
                        and not owner._resources and not owner._endpoints)
                    # Drain even when the captured pre-drain proof is invalid.
                    drained_ack = await original_close(owner)
                    receipt["independent_owner_drains"] += 1
                    assert type(completion) is core.InvocationCompletion, (
                        "owner was not terminal before safety drain")
                    ack = completion.cleanup_ack
                    assert (
                        type(ack) is core.CleanupCompleteAck
                        and ack.not_started is True and ack.released is True
                        and ack.terminal_ack_sha256 is None
                        and ack._authority.owner is owner
                        and ack._authority.ack is ack
                        and ack.invocation_id == snapshot.invocation_id
                        and ack.role == snapshot.role == "program"
                        and ack.request_sha256 == snapshot.request_sha256
                        and ack.profile_sha256 == snapshot.profile_sha256
                        and completion.abort.kind == "cancelled"
                    ), "actual NOT_STARTED ACK identity invalid"
                    assert (
                        actor_free_before_drain
                        and owner._thread is None and not owner._children
                        and not owner._resources and not owner._endpoints
                    ), "unit owner acquired actor resources"
                    assert drained_ack is ack and owner._completion is completion, (
                        "independent drain changed completion identity")
                except BaseException as exc:
                    safety_errors.append(exc)
            receipt["owner_ack_identity_valid"] = not safety_errors
            receipt["actor_free"] = not safety_errors
            receipt["safety_complete"] = (
                not safety_errors
                and receipt["independent_owner_drains"] == len(owners))
            if safety_errors:
                raise AssertionError("independent owner safety drain failed")


def _worker(case, bypass):
    receipt = {
        "case": case, "bypass": bypass, "accepted": False,
        "named_assertion": None, "unexpected_failure": False,
        "forbidden_attempts": 0, "no_pending_tasks": False,
        "patches_restored": False,
    }
    before = _hashes()
    attempts = []
    loop = None
    # Imports are inert, as established by existing unit coverage. Neither SDK
    # import nor MockTransport is claimed as SDK/native execution evidence.
    try:
        sys.path.insert(0, str(REPO))
        from ptc import sql_isolation as core
        from ptc import sql_owned_program as adapter
        from ptc import test_sql_owned_program as unit

        # Force lazy SDK/helper imports before guards; no fixture/body yet.
        unit._deps()
        originals = (
            adapter._Runner._close_job, adapter._Runner.run_program,
            core.PilotExecutor.owned_program, core.OwnedSqlInvocation.execute,
            core.OwnedSqlInvocation.aclose, os.read,
        )
        # Asyncio's anonymous self-pipe is created before socket guards.
        loop = asyncio.new_event_loop()
        with ExitStack() as guards:
            _guards(guards, core, attempts)
            try:
                with tempfile.TemporaryDirectory(
                        prefix="owned-sql-unit-") as directory:
                    root = Path(directory).resolve()
                    task = loop.create_task(_scenario(
                        case, bypass, root, core, adapter, unit, receipt))
                    _, pending = loop.run_until_complete(
                        asyncio.wait({task}, timeout=5.0))
                    if pending:
                        raise AssertionError("control body deadline exceeded")
                    task.result()
            except AssertionError as exc:
                if str(exc) == CASES[case]:
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
            adapter._Runner._close_job, adapter._Runner.run_program,
            core.PilotExecutor.owned_program, core.OwnedSqlInvocation.execute,
            core.OwnedSqlInvocation.aclose, os.read,
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
    expected_owners = 0 if case == "db-preflight" else 1
    expected_requests = (
        (1 if bypass else 0) if case == "db-preflight" else
        (2 if bypass and case == "fatal-propagation" else 1))
    expected_closes = (
        0 if case == "db-preflight" or (bypass and case == "retained-close")
        else 1)
    receipt["accepted"] = bool(
        not receipt["unexpected_failure"] and before == after
        and not attempts and receipt["no_pending_tasks"]
        and receipt["patches_restored"] and receipt.get("safety_complete")
        and receipt.get("owner_ack_identity_valid") and receipt.get("actor_free")
        and receipt.get("bypass_hits") == int(bypass)
        and receipt.get("owners") == expected_owners
        and receipt.get("independent_owner_drains") == expected_owners
        and receipt.get("policy_requests") == expected_requests
        and receipt.get("runner_closes") == 1
        and receipt.get("actual_close_calls") == expected_closes
        and receipt["named_assertion"] == (CASES[case] if bypass else None)
        and receipt.get("api_error_expected") == (
            not bypass or case == "retained-close")
        and receipt.get("api_returned_cleanly") == (
            bypass and case != "retained-close")
        and receipt.get("fatal_bypass_error_expected") == (
            bypass and case == "fatal-propagation")
        and receipt.get("retained_close_valid") == (
            case != "db-preflight" and not (
                bypass and case == "retained-close"))
    )
    return receipt


def _write_receipt(directory, name, receipt):
    # Never overwrite existing evidence. Artifacts contain JSON receipts only.
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
                # Only the launcher creates a finite, directly owned child.
                # subprocess.run timeout kills/waits that child, never a group.
                # File-backed capture avoids unbounded PIPE/log retention.
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
        "accepted": all(run["accepted"] for run in runs) and before == after,
        "runs": [{"case": run["case"], "bypass": run["bypass"],
                  "accepted": run["accepted"]} for run in runs],
        "source_hashes_before": before, "source_hashes_after": after,
        "source_unchanged": before == after,
        "scope": "pure-unit NOT_STARTED owners only",
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
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["accepted"] else 1
    return _launcher(artifacts)


if __name__ == "__main__":
    raise SystemExit(main())
