"""SOURCE-ONLY physical qualifiers. Parent source/security review precedes runs.

Frozen numeric acceptance BEFORE implementation, one original 19.5s HOST cap:
1. sdk-retire-partial-setup: full-seven config and retained 8/7/1 metadata, then
   first-party framework yield and partial SDK setup. At least one real started
   InterceptionServer, ScratchRuntime, AsyncClient and HTTP transport; one
   guarded loopback 404 request (no authenticated/provider route), one original
   runtime.write using the original-loop default executor, then ONE explicit
   setup exception. Actual resource stop tasks joined, listeners/clients/
   transports/runtime workdir/workers/helper absent, undo once, SAFE true,
   acceptance false, actual outer Popen.wait. Not a zero-resource first-yield
   test and not a claim that Agent/eval started in this setup-only case.
2. sdk-retire-overlap: unchanged full-seven SDK selection, two actual original
   SCORER owners/controllers held before admission, then ONE acceptance fault.
   Public cancellation receipts precede gate release; original controllers
   delegate their real pre-admission branch. Exactly two original public owner
   closes, two identical-authority NOT_STARTED ACKs, zero guardian/role/CLI
   creations. All actual SDK tasks and original-loop workers/helpers joined.
3. sdk-retire-post-actor: full-seven selection, two held owners, first allowed
   through the canonical guardian/role/CLI protocol. ONE decoded static match
   ExResult with original completion/ACK, public close and ONE original SDK
   reward, then ONE acceptance fault before releasing owner two. Waiting for
   that reward prevents a publication/retirement race from introducing another
   assertion. Exactly one real guardian slot owes nested
   SAFE even after exit, creator wait, reader join and actual FD closure.
   Owner two cancels via the real NOT_STARTED branch; both public closes join.

Every implemented case requires phase-specific current-object qualification,
faultHits=1, preserved exact primary exception, async/framework/executor/undo
each once, actual closed sockets/resources and zero live workers/helpers.
Parent artifacts precede the cap. Safe retirement is never successful API
evaluation. No result/candidate/ACK fabrication, no SQL/native VM/provider/model,
new manifest, profile selection, SDK source changes or cap relaxation.

Remaining frozen SOURCE-FIRST gates (not runtime-qualified by writing them):
4. sdk-retire-framework-finalizer: two held controllers, zero guardians/results/
   rewards. Return a retirement checkpoint, not evaluation success. After all
   original stops/quiesce finish, a delegating generator adds ONE inert PATH
   entry only to ONE stopped runtime.env dict. The ORIGINAL framework assertion
   fails once, verified against its AST-derived source/code location. Preserve
   that exact built-in AssertionError as primary; restore local env in finally
   before executor/undo. Armed/caught/restored=1 each, two original NOT_STARTED
   ACKs/public closes, async/framework/executor/undo=1 each.
5. sdk-retire-watchdog-race: exact-phase anonymous pipe retained before the
   EXISTING supervisor starts; one write/read/fault before END-3.75. Two actual
   held controllers and real default workers alive. Supervisor latches primary,
   requests shared quiesce and claims native cleanup; main records native entry,
   waits outside ALL locks for that claim, then joins native_done outside locks.
   Supervisor releases cleanup lock before waiting for main entry. Original
   LOOP is stopped and drive lock unheld through main native entry/exit/waits.
   Native entries=2, claims=1, completed callers=2, finish claim=1, async action=1,
   stages=1 each, two NOT_STARTED ACKs, zero guardians/results/rewards. Wake FDs
   closed, actual supervisor joined, one main-owned SAFE/actual outer wait.
6. sdk-retire-two-slot-verification: release controller two ONLY after first
   original close/ACK/result/reward. Hold policy calls >2; both original decoded
   results/ACKs/closes/rewards and identity-matched EVIDENCE precede a retirement
   checkpoint. AFTER first actual nested SAFE check succeeds, one callback
   fault. Real attempt-all must still check slot two and attempt both actual
   creators/controllers/readers/FD sets/streams. Two of each actor/result/ACK/
   reward/SAFE/wait/reader, zero NOT_STARTED ACKs, ten closed slot FDs. Independent
   current native proof remains true, acceptance false. Writer rows may exist.

Pure regressions below/in the retirement unit module use mocked kernel objects,
not actor/ACK evidence: two native lock-entry/exit cases (success/failure); one
original-assert/local-env restoration case with executor/undo continuation; one
exact-phase pipe ownership/isolation case; one extracted actual native attempt
loop checking two slots and all later categories after the first callback fault.
Missing physical proof remains the existing PURE UNIT negative only. Never
launch an intentionally unretirable HOST merely to test absence of SAFE.
"""

from __future__ import annotations

import asyncio
import ast
from collections import Counter, defaultdict
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest


_PHYSICAL_PHASES = (
    "sdk-retire-partial-setup",
    "sdk-retire-overlap",
    "sdk-retire-post-actor",
    "sdk-retire-framework-finalizer",
    "sdk-retire-watchdog-race",
    "sdk-retire-two-slot-verification",
)


class _SdkPhysicalFault(AssertionError):
    """Exactly one immutable fixture fault, never a synthetic lifecycle result."""


class _SdkRetirementCheckpoint:
    """No Episode, result or evaluation success: main must retire the SDK."""


def _framework_path_assert_location(path, name="framework", first_line=None):
    module = ast.parse(path.read_bytes())
    functions = [
        node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
        and node.name == name and (first_line is None or
            min([node.lineno, *[item.lineno for item in node.decorator_list]])
            <= first_line <= node.end_lineno)]
    function, = functions
    target, = [
        node for node in ast.walk(function) if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Constant) and node.test.left.value == "PATH"
        and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.NotIn)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Attribute)
        and node.test.comparators[0].attr == "env"
        and isinstance(node.test.comparators[0].value, ast.Name)
        and node.test.comparators[0].value.id == "runtime"]
    return dict(file=path.name, line=target.lineno)


def _sdk_framework_finalizer(original, probe):
    """Delegate BOTH advancements; only the ORIGINAL assertion supplies fault."""
    code = original.gi_code
    origin = _framework_path_assert_location(
        Path(code.co_filename), code.co_name, code.co_firstlineno)
    probe.finalizer_original = original  # Before original first advancement.
    state = next(original)
    yield state
    retirement = probe.actor.retirement
    assert not retirement.loop.is_running()
    assert retirement.async_done.is_set() and retirement.retire_task.done()
    assert all(task.done() for task in retirement.tasks | retirement.stop_tasks)
    assert all(row.task is not None and row.task.done()
               and not row.task.cancelled() and row.task.exception() is None
               and row.verify() for row in retirement.resources)
    assert retirement.primary is None
    runtime = next(actual for actual in state.runtimes
                   if actual.stopped and type(actual.env) is dict and "PATH" not in actual.env)
    env = runtime.env
    assert env is not os.environ and env is not getattr(
        getattr(runtime, "config", None), "env", None)
    probe.finalizer_runtime, probe.finalizer_env = runtime, env
    probe.finalizer_env_before = dict(env)
    probe.finalizer_primary_unset = retirement.primary is None
    probe.finalizer_origin = origin
    probe.finalizer_process_path = os.environ.get("PATH")
    env["PATH"] = "inert-retirement-only"
    probe.finalizer_armed += 1
    try:
        probe.finalizer_advances += 1
        next(original)
    except AssertionError as exc:
        tb = exc.__traceback__
        while tb.tb_next is not None:
            tb = tb.tb_next
        if (type(exc) is AssertionError and tb.tb_frame.f_code is code
                and tb.tb_lineno == origin["line"]):
            probe.finalizer_origin_verified = True
            probe.finalizer_caught += 1
            probe.latch(exc)
        raise  # Same actual built-in exception, never a replacement assertion.
    finally:
        del env["PATH"]
        probe.finalizer_restored += 1


def _sdk_watchdog_wake(phase, retirement, cleanup_lock, spawn_lock):
    if phase != "sdk-retire-watchdog-race":
        return None
    return _SdkWatchdogRace(retirement, cleanup_lock, spawn_lock)


class _SdkWatchdogRace:
    """Existing-supervisor wake/hand-off observations, never a LOOP driver."""

    def __init__(self, retirement, cleanup_lock, spawn_lock):
        self.retirement, self.cleanup_lock, self.spawn_lock = (
            retirement, cleanup_lock, spawn_lock)
        self.main, self.supervisor = threading.current_thread(), None
        self.main_entered, self.supervisor_claimed = threading.Event(), threading.Event()
        self.supervisor_native_returned = threading.Event()
        self.calls, self.waits = [], []
        self.fds, self.writes, self.reads, self.stop_calls = (), 0, 0, 0
        self.probe = self.trigger_time = None
        # Register this actual partial owner BEFORE allocating either endpoint.
        retirement.retain_resource("watchdog-wake", self, self.stop, self.verify)
        self.fds = os.pipe()

    def signal(self, probe):
        assert threading.current_thread() is self.main and self.writes == 0
        assert probe.phase == "sdk-retire-watchdog-race" and len(probe.held) == 2
        self.probe = probe
        written = os.write(self.fds[1], b"R")
        self.writes += 1
        assert written == 1

    def read_fault(self, ordinary_deadline):
        assert threading.current_thread() is self.supervisor and self.reads == 0
        assert os.read(self.fds[0], 1) == b"R"
        self.reads += 1
        self.trigger_time = time.monotonic()
        assert self.trigger_time < ordinary_deadline
        error = _SdkPhysicalFault("sdk-retire-watchdog-race")
        self.probe.latch(error)
        self.retirement.fail("watchdog-trigger", error)

    async def stop(self):
        self.stop_calls += 1
        self.retirement.attempt_each("wake-fd", self.fds, os.close)

    def verify(self):
        for fd in self.fds:
            try:
                os.fstat(fd)
            except OSError as exc:
                if exc.errno == 9:
                    continue
            return False
        return self.stop_calls == 1

    def native_enter(self):
        thread = threading.current_thread()
        assert thread is self.main or thread is self.supervisor
        row = SimpleNamespace(
            thread=thread, claimed=None, done=False, proof=None,
            entry_running=self.retirement.loop.is_running(),
            entry_drive_locked=self.retirement.loop_drive_lock.locked(),
            exit_running=None, exit_drive_locked=None)
        self.calls.append(row)
        if thread is self.main:
            assert not self.retirement.loop.is_running()
            assert not self.retirement.loop_drive_lock.locked()
            # No lock scope surrounds this wait. Supervisor publishes the
            # claim only AFTER releasing the short native cleanup lock.
            before = self.retirement.loop_drive_lock.locked()
            assert self.supervisor_claimed.wait(self.retirement.remaining())
            after = self.retirement.loop_drive_lock.locked()
            self.waits.append((thread, "claim", before, after))
            assert not any((before, after, self.retirement.lock.locked(),
                            self.cleanup_lock.locked(), self.spawn_lock.locked()))
            self.main_entered.set()
        return row

    def native_claim(self, row, claimed):
        row.claimed = claimed
        if row.thread is self.supervisor:
            assert claimed
            self.supervisor_claimed.set()
            # Caller owns NO lock here. The original active LOOP may still be
            # owned by MAIN until its run_until_complete exits. main_entered
            # specifically proves the stopped-LOOP, unlocked native hand-off.
            assert self.main_entered.wait(self.retirement.remaining())
            self.waits.append((row.thread, "entry", None,
                               self.retirement.loop_drive_lock.locked()))
            assert not self.retirement.loop.is_running()
            assert not self.retirement.loop_drive_lock.locked()
        else:
            assert not claimed

    def native_exit(self, row, proof):
        row.exit_running = self.retirement.loop.is_running()
        row.exit_drive_locked = self.retirement.loop_drive_lock.locked()
        assert not row.exit_running and not row.exit_drive_locked
        row.proof, row.done = proof, True
        if row.thread is self.supervisor:
            self.supervisor_native_returned.set()

    def join_supervisor_native(self):
        # native_done is published by the original finally. Join the actual
        # supervisor's last native proof/observation before main drives LOOP.
        assert self.supervisor_native_returned.wait(self.retirement.remaining())

    def qualify(self):
        assert self.writes == self.reads == self.stop_calls == 1 and self.verify()
        assert self.supervisor is not None and not self.supervisor.is_alive()
        assert len(self.calls) == 2 and sum(row.claimed is True for row in self.calls) == 1
        assert all(row.done and row.proof is True for row in self.calls)
        assert all(not row.exit_running and not row.exit_drive_locked for row in self.calls)
        main_call, = [row for row in self.calls if row.thread is self.main]
        assert not main_call.entry_running and not main_call.entry_drive_locked
        assert self.main is threading.main_thread()
        assert {row.thread for row in self.calls} == {self.main, self.supervisor}
        assert len(self.waits) == 2
        assert (self.main, "claim", False, False) in self.waits
        assert (self.supervisor, "entry", None, False) in self.waits
        requests = self.retirement.request_threads
        assert any(thread is self.main for thread, _ in requests)
        assert sum(thread is self.supervisor and stop for thread, stop in requests) == 1
        assert self.retirement.finish_claims == 1
        assert self.retirement.safe_emissions == 1
        return dict(writes=self.writes, reads=self.reads, closed_wake_fds=len(self.fds),
                    native_entries=len(self.calls), native_claims=1, native_callers_done=2,
                    main_native_drive_unheld=not (
                        main_call.entry_drive_locked or main_call.exit_drive_locked),
                    supervisor_joined=not self.supervisor.is_alive(),
                    safe_emissions=self.retirement.safe_emissions)


class _SdkPhysicalProbe:
    """TEST-ONLY retained observations. Qualification runs AFTER retirement."""

    def __init__(self, phase, actor):
        assert phase in _PHYSICAL_PHASES
        self.phase, self.actor = phase, actor
        self.fault_hits, self.fault_error = 0, None
        self.released = []
        self.live_workers, self.held = (), ()
        self.resources_at_fault = ()
        self.http_status = None
        self.finalizer_armed = self.finalizer_caught = self.finalizer_restored = 0
        self.finalizer_advances = 0
        self.finalizer_primary_unset = self.finalizer_origin_verified = False
        self.checkpoint_returned = self.checkpoint_primary_unset = False
        self.slot_checks, self.native_attempts = [], defaultdict(list)

    def bind(
            self, *, config, known, state, owners, closes, results,
            programs, scorers, rewards):
        self.config, self.known, self.state = config, known, state
        self.owners, self.closes, self.results = owners, closes, results
        self.programs, self.scorers = programs, scorers
        self.rewards = rewards

    async def observe_live_executor(self):
        # Use original SDK work, not a substitute executor or a ledger-only
        # worker. Never resurrect an already retired runtime's workdir.
        loop = self.actor.retirement.loop
        executor = getattr(loop, "_default_executor", None)
        if executor is None or not any(t.is_alive() for t in executor._threads):
            runtime = next(runtime for runtime in self.state.runtimes
                           if runtime.workdir is not None
                           and runtime.workdir.exists() and not runtime.stopped)
            await runtime.write("retirement-physical-probe", b"retirement only\n")
        self.actor.retirement.capture_executor()
        self.live_workers = tuple(loop._default_executor._threads)
        assert self.live_workers and all(t.is_alive() for t in self.live_workers)

    def checkpoint(self):
        retirement = self.actor.retirement
        self.resources_at_fault = tuple(retirement.resources)
        counts = Counter(row.kind for row in self.resources_at_fault)
        assert all(counts[kind] >= 1 for kind in (
            "server", "runtime", "client", "transport"))
        assert all(row.task is None for row in self.resources_at_fault)
        if self.phase != "sdk-retire-partial-setup":
            self.held = tuple(row.actual for row in self.owners)
            assert len(self.held) == 2 and len(self.actor.owners) == 2
            assert all(owner._thread.is_alive() and not owner._thread.daemon
                       and owner.snapshot().intent is None for owner in self.held)
            assert not self.actor.slots and not self.actor.trace.fence()

    def latch(self, error):
        assert self.fault_hits == 0
        assert self.actor.retirement.primary is None
        self.fault_hits += 1
        self.fault_error = error

    def inject(self):
        self.latch(_SdkPhysicalFault(self.phase))
        raise self.fault_error

    def note_native_attempt(self, stage, actual):
        self.native_attempts[stage].append(actual)

    def after_slot_safe(self, slot):
        # Called only AFTER the actual native helper's original wait succeeds.
        assert slot["safe"].is_set()
        self.slot_checks.append(slot)
        if slot is self.actor.slots[0]:
            self.inject()

    def qualify(self):
        """Current objects and original API identities, not reported counts."""
        retirement, actor = self.actor.retirement, self.actor
        assert self.fault_hits == 1 and retirement.primary is self.fault_error
        if self.phase == "sdk-retire-framework-finalizer":
            assert type(self.fault_error) is AssertionError
            assert self.finalizer_origin_verified and self.finalizer_primary_unset
            assert self.finalizer_original.gi_frame is None
            assert self.finalizer_origin == _framework_path_assert_location(
                Path(__file__).with_name("test_bash_qa_eval_integration.py"))
            assert (self.finalizer_armed, self.finalizer_caught, self.finalizer_restored,
                    self.finalizer_advances) == (1, 1, 1, 1)
            assert self.finalizer_runtime.env is self.finalizer_env
            assert self.finalizer_env == self.finalizer_env_before
            assert "PATH" not in self.finalizer_env
            assert os.environ.get("PATH") == self.finalizer_process_path
        else:
            assert type(self.fault_error) is _SdkPhysicalFault
            assert str(self.fault_error) == self.phase
        if self.phase in ("sdk-retire-framework-finalizer", "sdk-retire-two-slot-verification"):
            assert self.checkpoint_returned and self.checkpoint_primary_unset
            assert retirement.outcome["decision"] == "retirement-checkpoint"
        assert retirement.finalized and retirement.undone
        assert actor.native_proof() is True and retirement.finish_claims == 1
        assert retirement.stages == {
            "async": 1, "framework": 1, "executor": 1, "undo": 1}
        assert all(error is self.fault_error or isinstance(error, asyncio.CancelledError)
                   for _, error in retirement.errors)
        assert (len(self.known.planned), len(self.known.eligible),
                len(self.known.exclusions), len(self.known.databases)) == (8, 7, 1, 2)
        assert self.config.num_tasks in (None, 7)
        assert self.config.num_rollouts == 1 and self.config.max_concurrent == 2
        assert self.live_workers and all(t in retirement.workers and not t.is_alive()
                                         for t in self.live_workers)
        assert retirement.executor_helpers
        assert all(not t.is_alive() for t in (
            retirement.workers | retirement.executor_helpers))
        assert all(t.done() for t in (
            retirement.tasks | retirement.stop_tasks | retirement.internal_tasks))
        assert all(row.stop_calls == 1 and row.task is not None and row.task.done()
                   and not row.task.cancelled() and row.task.exception() is None
                   and row.verify() for row in retirement.resources)
        assert all(any(row is retained for retained in retirement.resources)
                   for row in self.resources_at_fault)
        assert actor.bound_sockets and all(s.fileno() == -1 for s in actor.bound_sockets)
        counts = Counter(row.kind for row in retirement.resources)
        assert all(counts[kind] >= 1 for kind in (
            "server", "runtime", "client", "transport"))
        assert not self.state.external and not actor.forbidden_calls
        assert all(agent.harness is original for agent, original in self.state.agents)
        # Original scope-driven public closes, with the actual retained task
        # and object identity. Never inspect a production scope/private job
        # list, invoke another close, or claim active PROGRAM qualification.
        for row in self.scorers:
            task, = row.closes
            assert row.actual._closed and task.done() and not task.cancelled()
            assert task.exception() is None
        for row in self.programs:
            assert len(row.runners) == len(row.closes)
            for runner in row.runners:
                close, = [item for item in row.closes if item[0] is runner]
                task = close[1]
                assert runner._closed and task.done() and not task.cancelled()
                assert task.exception() is None
        entries = actor.trace.fence()
        if self.phase == "sdk-retire-partial-setup":
            assert self.http_status == 404 and self.runtime.stopped
            assert not self.runtime.workdir.exists() and self.client.is_closed
            assert not self.server.runner.sites and not self.server.sessions
            assert not self.owners and not actor.owners and not self.closes
            assert not self.results and not self.state.agents
            assert not actor.slots and not entries
            not_started, actors = 0, 0
        else:
            assert len(self.owners) == len(actor.owners) == len(self.closes) == 2
            assert len(self.scorers) >= 2 and len(self.programs) >= 2
            assert len(self.held) == 2
            assert all(row.actual is actual for row, actual in zip(
                self.owners, actor.owners, strict=True))
            assert len({id(row.actual) for row in self.closes}) == 2
            not_started = 0
            for row in self.owners:
                actual = row.actual
                assert any(actual is held for held in self.held)
                assert actual._thread.ident is not None and not actual._thread.is_alive()
                close, = [item for item in self.closes if item.actual is actual]
                assert close.task.done() and not close.task.cancelled()
                assert close.task.exception() is None
                completion = actual._completion
                assert close.ack is completion.cleanup_ack is actual._authority.ack
                assert close.ack._authority.owner is actual and close.ack.role == "scorer"
                assert close.ack.released
                assert close.ack.invocation_id == actual.invocation_id
                assert close.ack.request_sha256 == actual.request_digest
                assert close.ack.profile_sha256 == actual.profile_digest
                assert not actual._resources and actual._host_read is None
                if close.ack.not_started:
                    not_started += 1
                    assert completion.abort is not None and completion.outcome is None
                    assert completion.abort.kind == completion.abort.detail_code == "cancelled"
                    assert not close.ack.guardian_reaps and not actual._children
                    assert not close.ack.child_waits and not close.ack.thread_joins
                    assert row.scorer.result is None
                    released, = [item for item in self.released if item[0] is actual]
                    _, intent, receipts = released
                    assert intent is actual.snapshot().intent and intent is not None
                    assert any(owner is actual and receipt.intent is intent
                               for owner, receipt in receipts)
                else:
                    assert completion.abort is None
                    result = row.scorer.result
                    assert sum(item is result for item in self.results) == 1
                    from bench.score import ExResult
                    assert type(result) is ExResult and completion.outcome.result is result
                    assert result.status == "match" and result.valid is True
                    assert result.score == 1.0
                    assert (result.n_pred_rows, result.n_gold_rows) == (7, 11)
                    assert len(close.ack.guardian_reaps) == 1
                    assert close.ack.child_waits and close.ack.thread_joins
            actors = {"sdk-retire-post-actor": 1,
                      "sdk-retire-two-slot-verification": 2}.get(self.phase, 0)
            assert not_started == 2 - actors
            assert len(self.results) == len(actor.slots) == len(entries) == actors
            assert len({id(result) for result in self.results}) == actors
        assert len(self.rewards) == actors
        assert len({id(actual) for actual, _, _ in self.rewards}) == actors
        for actual, trace, scorer in self.rewards:
            owner, = [row for row in self.owners if row.actual is actual]
            assert scorer is owner.scorer
            assert sum(result is scorer.result for result in self.results) == 1
            assert trace.task.data is owner.sdk_task.data
            assert set(trace.rewards) == {"execution_accuracy"}
            assert trace.rewards["execution_accuracy"].score == 1.0
        for slot in actor.slots:
            assert slot["safe"].is_set() and not slot["reader"].is_alive()
            safe, = [item for item in slot["messages"] if item["kind"] == "SAFE"]
            assert safe["independent"] is True
            evidence, = [item for item in slot["messages"] if item["kind"] == "EVIDENCE"]
            assert not evidence["hits"] and not evidence["forbidden"] and evidence["released"]
            children = evidence["actual"]
            assert sum(row["actor"] == "role" for row in children) == 1
            assert sum(row["actor"] == "cli" for row in children) >= 2
            assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                       and type(row["returncode"]) is int for row in children)
            entry, = [entry for entry in entries if entry["process"] is slot["process"]]
            process = entry["process"]
            assert process._creator_waited and not process._creator_ambiguous
            assert type(process.returncode) is int
            owner = slot["invocation"]
            assert owner._completion.cleanup_ack.guardian_reaps == (
                (process.pid, process.returncode),)
            assert len(owner._children) == 1 and owner._children[0] is process
            assert all(stream is None or stream.closed
                       for stream in (process.stdin, process.stdout, process.stderr))
            for fd in slot["fds"]:
                with pytest.raises(OSError) as caught:
                    os.fstat(fd)
                assert caught.value.errno == 9
        extra = {}
        if self.phase == "sdk-retire-framework-finalizer":
            extra.update(
                original_assert_origin_verified=self.finalizer_origin_verified,
                original_assert_origin=self.finalizer_origin,
                finalizer_armed=self.finalizer_armed, finalizer_caught=self.finalizer_caught,
                finalizer_restored=self.finalizer_restored,
                original_finalizer_advances=self.finalizer_advances)
        if self.phase == "sdk-retire-watchdog-race":
            race = actor.watchdog_race
            assert race.probe is self and race.trigger_time < actor.end - 3.75
            extra["watchdog_race"] = race.qualify()
        if self.phase == "sdk-retire-two-slot-verification":
            def same_refs(actuals, expected):
                assert len(actuals) == len(expected)
                assert all(actual is other for actual, other in zip(actuals, expected, strict=True))
            same_refs(self.slot_checks, actor.slots)
            same_refs(self.native_attempts["guardian-safe"], actor.slots)
            same_refs(self.native_attempts["creator-reap"], entries)
            same_refs(self.native_attempts["controller"], actor.owners)
            same_refs(self.native_attempts["reader"], actor.slots)
            same_refs(self.native_attempts["creator-streams"], entries)
            streams = [stream for entry in entries for stream in (
                entry["process"].stdin, entry["process"].stdout, entry["process"].stderr)
                       if stream is not None]
            same_refs(self.native_attempts["creator-stream"], streams)
            fds = [fd for slot in actor.slots for fd in slot["fds"]]
            assert self.native_attempts["slot-fd"] == fds and len(set(fds)) == 10
            assert sum(stage == "guardian-safe" and error is self.fault_error
                       for stage, error in retirement.errors) == 1
            extra.update(
                slot_checks=len(self.slot_checks), slot_callback_faults=self.fault_hits,
                attempted_creators=len(self.native_attempts["creator-reap"]),
                attempted_controllers=len(self.native_attempts["controller"]),
                attempted_readers=len(self.native_attempts["reader"]),
                attempted_slot_fds=len(self.native_attempts["slot-fd"]),
                attempted_streams=len(self.native_attempts["creator-stream"]))
        return dict(
            verified=True, phase=self.phase, fault_hits=self.fault_hits,
            primary_preserved=True, selected_tasks=7, selected_rollouts=1,
            resources={kind: counts[kind] for kind in (
                "server", "runtime", "client", "transport")},
            held_controllers=len(self.held), owner_closes=len(self.closes),
            not_started_acks=not_started, decoded_results=len(self.results),
            sdk_rewards=len(self.rewards),
            guardians=actors, nested_safe=actors, creators_waited=len(entries),
            readers_joined=len(actor.slots),
            closed_slot_fds=sum(len(slot["fds"]) for slot in actor.slots),
            closed_sockets=len(actor.bound_sockets),
            scoped_scorers_closed=len(self.scorers),
            inert_program_runners_closed=sum(len(row.runners) for row in self.programs),
            joined_sdk_tasks=len(retirement.tasks), http_status=self.http_status,
            current_native_proof=True, resource_stops_once=len(retirement.resources),
            checkpoint_returned=self.checkpoint_returned,
            **extra,
        )


@pytest.mark.parametrize("phase", _PHYSICAL_PHASES)
def test_owned_sql_sdk_physical_retirement_fault(tmp_path, phase):
    from bench.test_validated_draw_databases import _artifacts
    from ptc.test_sql_lifecycle_process import _owned_guest_case

    # All artifact/SQLite preparation is parent-only, BEFORE the existing cap.
    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)
    result = _owned_guest_case(
        tmp_path, "scorer", phase, expected_ok=False,
        prepared=(corpus, draw, supplement, draw_sha, supplement_sha))
    proof = result["physical_qualification"]
    assert result["outer_actual_wait"] is True
    assert proof["selected_tasks"] == 7 and proof["selected_rollouts"] == 1
    assert all(proof["resources"][kind] >= 1 for kind in (
        "server", "runtime", "client", "transport"))
    assert proof["closed_sockets"] >= 1 and proof["joined_sdk_tasks"] >= 1
    partial = phase == "sdk-retire-partial-setup"
    actors = {"sdk-retire-post-actor": 1,
              "sdk-retire-two-slot-verification": 2}.get(phase, 0)
    assert proof["held_controllers"] == proof["owner_closes"] == (0 if partial else 2)
    assert proof["not_started_acks"] == (0 if partial else 2 - actors)
    assert proof["decoded_results"] == proof["guardians"] == actors
    assert proof["sdk_rewards"] == actors
    assert proof["nested_safe"] == proof["creators_waited"] == actors
    assert proof["readers_joined"] == actors
    assert proof["closed_slot_fds"] == 5 * actors
    assert proof["http_status"] == (404 if partial else None)
    assert proof["scoped_scorers_closed"] >= (0 if partial else 2)
    assert proof["inert_program_runners_closed"] >= (0 if partial else 2)
    assert proof["current_native_proof"] is True
    if phase == "sdk-retire-framework-finalizer":
        assert result["decision"] == "retirement-checkpoint"
        assert proof["finalizer_armed"] == proof["finalizer_caught"] == proof["finalizer_restored"] == 1
        assert proof["original_finalizer_advances"] == 1
    if phase == "sdk-retire-watchdog-race":
        race = proof["watchdog_race"]
        assert race["writes"] == race["reads"] == race["native_claims"] == 1
        assert race["native_entries"] == race["native_callers_done"] == race["closed_wake_fds"] == 2
        assert race["main_native_drive_unheld"] is race["supervisor_joined"] is True
        assert race["safe_emissions"] == 1
    if phase == "sdk-retire-two-slot-verification":
        assert result["decision"] == "retirement-checkpoint"
        assert proof["slot_checks"] == proof["attempted_creators"] == proof["attempted_controllers"] == 2
        assert proof["attempted_readers"] == 2 and proof["attempted_slot_fds"] == 10
        assert proof["attempted_streams"] >= 2 and proof["slot_callback_faults"] == 1
