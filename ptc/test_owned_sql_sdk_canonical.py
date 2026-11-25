"""SOURCE-ONLY canonical positive bridge, execution requires parent clearance.

Frozen acceptance before implementation:
1. Original registered SDK Agent/evaluator/writer covers all 7 eligible Tasks
   in order, once or twice each (7/14 scopes), from retained 8/7/1 artifacts.
2. Each scope has one distinct actual scorer, Trace and decoded static match
   ExResult, one actual SCORER dispatch, one public owner close and identical
   actual completion/authority ACK. No replacement native result or ACK.
3. Two allocated live controllers overlap before admission: distinct original
   Tasks for one rollout; the same original Task for two samples. Shared
   profile admission still serializes dispatched guardians.
4. Exact original private Task/public Data associations, no private gold SQL
   or host DB paths in policy/public rows, one reward per successful trace,
   and the original JSONL contains exactly 7/14 successful rows.
5. One shared 19.5s deadline starts AFTER parent artifact preparation. Every
   actual guardian owes nested SAFE even after exit, every actual process
   owes creator wait, and SDK transports/servers finish before host SAFE.

New bounded spike, test_sdk_one_program_full_seven (SOURCE, not executed):
6. Three direct positive/sentinel-expected-failure/restored cases, each with
   7 Tasks, 1 rollout, concurrency 2, 8 policy requests, 1 PROGRAM + 7 SCORER
   dispatches, 8 original public closes/identical ACKs, 7 rewards/writer rows,
   7 ordinary runners/5s synchronous validations/original runner closes.
7. Action cap 2, PROGRAM rows 3, unchanged SCORER settings. Original SDK tool
   invokes PROGRAM; read-only original scope/tool-call ID associates both
   delegated runner observation and subsequent policy tool message.
8. One late SDK_PROGRAM_OBSERVATION_VERBATIM assertion checks exact whitespace
   only after full completion/association/ACK/privacy/writer gates. Mutant
   changes one wire observation only; actual decoded SentinelHit is 0/1/0.
9. Expected negative requires exact built-in HOST and parent AssertionError
   identities/code/unique AST lines, actual counts and finalized current
   8-slot SAFE/creator/resource/thread proof, then same-dict outer actual wait,
   closed streams and removal from both ledgers. No rendered-error matching.
SHORTCUT: static native frames, not SQL execution. MISSING: parent execution,
review and measured tool-wire feasibility; prior positives do not qualify it.

Next frozen SOURCE spike, test_sdk_program_three_cancels:
10. Full 8/7/1 selection, 7 Tasks/1 rollout/concurrency 2. First 2 ordinary
    PROGRAM tool calls produce 2 distinct scopes/owners, 1 real dispatch,
    2 original public closes, 1 active ACK + 1 authentic NOT_STARTED ACK,
    0 SCORER invocations. No third owner or substituted Env cancellation.
11. Three exact-marker eval-caller cancellations must be actually delivered;
    later 2 reach the SAME retained target Env cleanup shield join while both
    public owner closes hold after real request_cancel and before delegation.
    Authorized compatibility history is EXACTLY 4 builtin CancelledErrors on
    the SAME Env: marker1/AGENT, EMPTY/cleanup, marker2/SAME cleanup,
    marker3/SAME cleanup. Await EMPTY before marker2; recheck after caller drain.
    EMPTY is compatible with the reported stock SDK wave, not callsite proof.
    Exact invocation-matched host/guardian CONSUMED intent times never change.
12. Two original resource-close tasks per scope exist before its first
    post-cancel shield join; all 4 runner/scorer public close bodies enter
    before releasing either owner hold. Scopes/token remain live, authority
    stopped, no reward/successful row or target trace writer row while held.
13. Original code alone drains/revokes; actual eval caller ends cancelled.
    All retained tasks finish; current 1-slot nested SAFE/creator/FD/worker/
    helper/resource proof and outer actual wait remain mandatory.
SOURCE only, qualification pending parent review/execution. Public-return holds
are not claims of continuous native ownership. Original 12s intent/19.5s HOST
caps remain; unknown-at-cap is BLOCKED by all-task-done retirement. Stock SDK
marker delivery failure is BLOCKED, never replaced by direct Env cancellation.

Non-goals: SQL correctness, SCORER cancellation, unknown
proof, invalid statuses, mutations, providers/models/native activation,
installs/repins or production/SDK changes. Prior scorer-only PROGRAM remains
text-only with real builder/catalog/preflight/inert close. Passing positives cannot qualify those
remaining gates. No runtime is authorized by this source file.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import inspect
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest


ID = "cotrain_owned_sql"
PREDICTION = "fixture-score-status:match"
PROGRAM_PHASE = "sdk-program-one"
PROGRAM_CODE = "print('adapter ordinary fixture')"
PROGRAM_EXPECTED = "  ordinary fixture\nverbatim  \n"
PROGRAM_SENTINEL = "directed PROGRAM observation sentinel\n"
PROGRAM_GATE = "SDK_PROGRAM_OBSERVATION_VERBATIM"


def _program_gate_origin():
    """Independently derive the unique literal gate from trusted source."""
    import ast
    source = Path(__file__).resolve()
    tree = ast.parse(source.read_text(), filename=str(source))
    function, = [node for node in tree.body
                 if isinstance(node, ast.AsyncFunctionDef)
                 and node.name == "_sdk_acceptance"]
    gate, = [node for node in ast.walk(function)
             if isinstance(node, ast.Assert) and isinstance(node.msg, ast.Constant)
             and node.msg.value == PROGRAM_GATE]
    assert Path(_sdk_acceptance.__code__.co_filename).resolve() == source
    return dict(file="ptc/test_owned_sql_sdk_canonical.py",
                function="_sdk_acceptance", line=gate.lineno)


def _program_acceptance_failure(exc, retirement):
    """Only the actual original late gate may acquire a safe failure receipt."""
    if type(exc) is not AssertionError or exc.args != (PROGRAM_GATE,):
        return None
    if retirement.primary is not exc:
        return None
    origin = exc.__traceback__
    if origin is None:
        return None
    while origin.tb_next is not None:
        origin = origin.tb_next
    expected = _program_gate_origin()
    if (origin.tb_frame.f_code is not _sdk_acceptance.__code__
            or Path(origin.tb_frame.f_code.co_filename).resolve() != Path(__file__).resolve()
            or origin.tb_lineno != expected["line"]):
        return None
    hits = retirement.outcome.get("SentinelHit")
    if type(hits) is not int or hits != 1:
        return None
    return dict(type="AssertionError", gate=PROGRAM_GATE, origin=expected,
                primary_preserved=retirement.primary is exc, SentinelHit=hits)


class _SdkRetirement:
    """TEST-ONLY physical retirement. Never owns or manufactures API ACKs.

    Registered by HOST before bridge/framework construction. Short state locks
    only claim work; original-loop driving has one separate main-thread lock.
    Acceptance errors are sticky, independent of the current physical proof.
    """

    def __init__(self, *, loop, deadline, disable, cooperative_cutoff=None):
        self.loop, self.deadline, self.disable = loop, deadline, disable
        self.cooperative_cutoff = cooperative_cutoff
        self.fallback_requested = threading.Event()
        self._cooperative_waiter = None
        # Scheduling only: neither readiness nor supervisor completion is an
        # API ACK or physical proof. No wait holds this short phase lock.
        self._native_handoff_lock = threading.Lock()
        self._native_handoff_ready = threading.Event()
        self._native_handoff_done = threading.Event()
        self._native_handoff_done.set()
        self._native_handoff_pending = 0
        self._native_handoff_closed = False
        self._native_handoff_ready_at = None
        self._native_handoff_missing = False
        self.release = lambda: None
        self.lock, self.loop_drive_lock = threading.Lock(), threading.Lock()
        self.requested, self.started = threading.Event(), threading.Event()
        self.async_done, self.complete = threading.Event(), threading.Event()
        self.main_finishing = threading.Event()
        self.async_started = asyncio.Event()
        self.retire_task = None
        self.tasks, self.internal_tasks, self.stop_tasks = set(), set(), set()
        self.task_roles, self.role_conflicts = {}, set()
        self.cancelled_drivers = set()
        self.emit_diagnostic = lambda report: None
        self.resources, self.errors = [], []
        self.stages = Counter()
        self.patch = self.framework = self.state = None
        self.executor = self.shutdown_task = None
        self.workers, self.executor_helpers = set(), set()
        self.baseline_threads = set(threading.enumerate())
        self.permitted_threads = lambda: set()
        self.outcome, self.primary = None, None
        self.finalized = self.undo_attempted = self.undone = False
        self.safe_emissions = 0
        self.stop_loop = False
        self._scheduled = self._finished = False
        self._observed_task_errors = set()
        self.finish_claims, self.request_threads = 0, []

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def fail(self, stage, error):
        with self.lock:
            if self.primary is None:
                self.primary = error
            self.errors.append((stage, error))
            self.outcome = dict(self.outcome or {}, ok=False,
                                error=type(self.primary).__name__)

    def record_outcome(self, outcome):
        with self.lock:
            self.outcome = dict(outcome)
            if self.primary is not None:
                self.outcome.update(ok=False, error=type(self.primary).__name__)

    def attempt_each(self, stage, items, action):
        values = []
        for item in tuple(items):
            try:
                values.append(action(item))
            except BaseException as exc:
                self.fail(stage, exc)
        return values

    def retain_resource(self, kind, actual, stop, verify):
        record = SimpleNamespace(
            kind=kind, actual=actual, stop=stop, verify=verify, task=None, stop_calls=0)
        self.resources.append(record)  # Before constructor or first await.
        return record

    def retain_task(self, task):
        with self.lock:
            self.tasks.add(task)
        return task

    def _retain_role(self, task, role, kind=None):
        with self.lock:
            self.tasks.add(task)
            previous = self.task_roles.get(task)
            conflict = previous is not None and previous != (role, kind)
            late_driver = (previous is None and role == "driver"
                           and self.requested.is_set())
            if conflict:
                self.role_conflicts.add(task)
            else:
                self.task_roles[task] = (role, kind)
        # Never cancel or report while holding the bookkeeping lock.
        if conflict:
            self.fail("task-role", AssertionError("SDK_TASK_ROLE_CONFLICT"))
        if late_driver:
            self.fail("late-driver", AssertionError("SDK_UNEXPECTED_LATE_DRIVER"))
            self.loop.call_soon_threadsafe(self._cancel_drivers)
        return task

    def retain_driver(self, task):
        return self._retain_role(task, "driver")

    def retain_cleanup(self, task, kind):
        assert kind in ("owner-close", "resource-close", "scope-drain")
        return self._retain_role(task, "cleanup", kind)

    def _cancel_drivers(self):
        # Original-loop callback only. Unclassified is NOT a driver default.
        with self.lock:
            drivers = tuple(
                task for task, (role, _) in self.task_roles.items()
                if role == "driver" and task not in self.role_conflicts
                and task not in self.cancelled_drivers and not task.done())
            self.cancelled_drivers.update(drivers)
        for task in drivers:
            # Creation/entry order puts the HOST driver before its eval driver.
            # Its cancellation may already propagate to that awaited driver.
            # Do not stack another interruption on an original unwind.
            if not task.cancelling():
                task.cancel()  # At most one retirement request per explicit driver.

    def diagnostic(self):
        """Closed, bounded inventory, never names, frames, locals or errors."""
        self._snapshot_tasks()
        with self.lock:
            tasks = tuple(self.tasks | self.stop_tasks | self.internal_tasks)
            roles = dict(self.task_roles)
            errors = tuple(self.errors)
        allowed_sources = {
            ("cotrain_owned_sql.py", "_close_resource"),
            ("cotrain_owned_sql.py", "_drain_scope"),
            ("cotrain_owned_sql.py", "run"),
            ("test_owned_sql_sdk_canonical.py", "_run_sdk_host_case"),
            ("test_owned_sql_sdk_canonical.py", "_sdk_acceptance"),
            ("test_owned_sql_sdk_canonical.py", "observed_close"),
            ("test_owned_sql_sdk_canonical.py", "observed_runner_close"),
            ("test_owned_sql_sdk_canonical.py", "observed_scorer_close"),
            ("test_owned_sql_sdk_program_cancellation.py", "close_owner"),
            ("test_owned_sql_sdk_program_cancellation.py", "observed_shield"),
        }
        allowed_stages = {
            "async", "release", "task-drain", "native", "native-proof",
            "resource-proof", "framework", "executor", "undo", "physical-proof",
            "task", "disable", "start-async", "join-async", "worker-join", "finish",
        }
        rows = []
        for task in tasks[:32]:
            code = getattr(task.get_coro(), "cr_code", None)
            source = ("OTHER", "OTHER")
            if code is not None:
                candidate = (Path(code.co_filename).name, code.co_name)
                if candidate in allowed_sources:
                    source = candidate
            rows.append(dict(
                role=roles.get(task, ("unclassified", None))[0],
                done=task.done(), cancelled=task.cancelled(),
                source=dict(file=source[0], function=source[1])))
        stages = [stage if type(stage) is str and stage in allowed_stages else "OTHER"
                  for stage, _ in errors[:16]]
        report = dict(
            tasks=rows, tasks_total=len(tasks), tasks_omitted=len(tasks)-len(rows),
            pending_tasks=sum(not task.done() for task in tasks),
            stages=stages, stages_total=len(errors),
            stages_omitted=len(errors)-len(stages))
        # Reserve room for the HOST's fixed diagnostic envelope.
        while len(json.dumps(report, separators=(",", ":")).encode("utf-8")) > 8064:
            if rows:
                rows.pop()
                report["tasks_omitted"] += 1
            elif stages:
                stages.pop()
                report["stages_omitted"] += 1
            else:
                break
        return report

    def _diagnose_refusal(self):
        try:
            self.emit_diagnostic(self.diagnostic())
        except BaseException:
            pass  # Diagnostic I/O can never interrupt physical retirement.

    def request(self, *, stop_loop=False):
        # No future.result(), event.wait() or loop-driving under this lock.
        with self.lock:
            self.request_threads.append((threading.current_thread(), stop_loop))
            self.stop_loop |= stop_loop
            self.requested.set()
            schedule = not self._scheduled
            self._scheduled = True
        if schedule:
            try:
                self.disable()
            except BaseException as exc:
                self.fail("disable", exc)
            self.loop.call_soon_threadsafe(self._begin)

    def request_fallback(self):
        """Supervisor notification only. NEVER drive LOOP or wait for main."""
        self.fallback_requested.set()  # Sticky, including before waiter install.
        try:
            self.loop.call_soon_threadsafe(self._wake_cooperation)
        except RuntimeError:
            if not self.loop.is_closed():
                raise

    def _wake_cooperation(self):
        # Only original LOOP reads/completes its private wake future. The
        # supervisor sets the thread-safe flag and enqueues this callback.
        waiter = self._cooperative_waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    def request_native_handoff(self):
        """Register before requesting fallback; closed phases admit no work."""
        with self._native_handoff_lock:
            if self._native_handoff_closed:
                return "ALREADY_RETIRED"
            self._native_handoff_pending += 1
            self._native_handoff_done.clear()
        self.request_fallback()  # Notification outside all bookkeeping locks.
        return "REGISTERED"

    def wait_native_handoff(self, deadline):
        """Supervisor waits only to the original absolute guardian reserve."""
        ready = self._native_handoff_ready.wait(
            timeout=max(0.0, deadline - time.monotonic()))
        with self._native_handoff_lock:
            # A delayed MAIN publication cannot authorize a timed-out waiter,
            # even if Event.wait observes that publication at the boundary.
            timely = (ready and self._native_handoff_ready_at is not None
                      and self._native_handoff_ready_at <= deadline)
            missing = not timely and not self._native_handoff_missing
            if missing:
                self._native_handoff_missing = True
        if missing:
            self.fail("native-handoff", AssertionError("SDK_NATIVE_HANDOFF_MISSING"))
        return bool(timely)

    def publish_native_handoff(self):
        """MAIN alone publishes after LOOP has stopped and drive is released."""
        assert not self.loop.is_running(), "SDK_LOOP_STILL_OWNED"
        assert not self.loop_drive_lock.locked(), "SDK_NATIVE_HANDOFF_DRIVE_LOCKED"
        with self._native_handoff_lock:
            assert not self._native_handoff_closed, "SDK_NATIVE_HANDOFF_ALREADY_CLOSED"
            if self._native_handoff_ready_at is None:
                self._native_handoff_ready_at = time.monotonic()
                self._native_handoff_ready.set()

    def supervisor_native_finished(self):
        """Unconditional registered-supervisor finally, including wait failure."""
        with self._native_handoff_lock:
            assert self._native_handoff_pending > 0, "SDK_NATIVE_HANDOFF_UNREGISTERED"
            self._native_handoff_pending -= 1
            if not self._native_handoff_pending:
                self._native_handoff_done.set()

    def close_native_handoff(self, deadline):
        """Freeze registration, then account ALL admitted callers outside locks."""
        with self._native_handoff_lock:
            self._native_handoff_closed = True
        # No registration can clear done after phase closure. A registration
        # linearized before closure cleared it and owes its finally notification.
        return self._native_handoff_done.wait(
            timeout=max(0.0, deadline - time.monotonic()))

    def _begin(self):
        with self.lock:
            if self.retire_task is not None:
                return
            self.stages["async"] += 1
            self.retire_task = self.loop.create_task(self._quiesce())
            self.internal_tasks.add(self.retire_task)
            self.started.set()

    def _snapshot_tasks(self):
        current = asyncio.all_tasks(self.loop) - self.internal_tasks
        with self.lock:
            self.tasks.update(current)
            return {task for task in self.tasks if not task.done()}

    def capture_executor(self):
        actual = getattr(self.loop, "_default_executor", None)
        if actual is not None:
            if self.executor is not None and self.executor is not actual:
                self.fail("executor", AssertionError("SDK_EXECUTOR_CHANGED"))
            self.executor = actual
            self.workers.update(tuple(actual._threads))

    def check_drained_tasks(self):
        assert not self._snapshot_tasks(), "SDK_TASKS_STILL_LIVE"

    def _observe_task_errors(self):
        with self.lock:
            tasks = tuple(self.tasks | self.stop_tasks)
        for task in tasks:
            if task.done() and not task.cancelled():
                error = task.exception()
                if error is not None:
                    with self.lock:
                        first = task not in self._observed_task_errors
                        self._observed_task_errors.add(task)
                    if first:
                        self.fail("task", error)

    async def _stop_resource(self, record):
        record.stop_calls += 1
        await record.stop()

    async def _quiesce(self):
        try:
            self._snapshot_tasks()  # Retain ALL, including unclassified cleanup.
            self._cancel_drivers()
            self.attempt_each("release", (None,), lambda _: self.release())
            # Start ALL independent stops before joining any cancellation.
            for record in tuple(self.resources):
                try:
                    record.task = self.loop.create_task(self._stop_resource(record))
                    self.retain_cleanup(record.task, "resource-close")
                    self.stop_tasks.add(record.task)
                    self.internal_tasks.add(record.task)
                except BaseException as exc:
                    self.fail("start-" + record.kind, exc)
            self.async_started.set()
            while True:
                pending = self._snapshot_tasks()
                pending.update(task for task in self.stop_tasks if not task.done())
                if not pending or not self.remaining():
                    break
                await asyncio.wait(pending, timeout=self.remaining(),
                                   return_when=asyncio.FIRST_COMPLETED)
            # Assertions are outcome checks, never retirement control flow.
            try:
                self.check_drained_tasks()
            except BaseException as exc:
                self.fail("task-drain", exc)
            self._observe_task_errors()
            self.capture_executor()
        except BaseException as exc:
            self.fail("async-retirement", exc)
        finally:
            self.async_started.set()
            self.async_done.set()
            if self.stop_loop:
                # Recheck at callback execution: main may already own driving.
                self.loop.call_soon(
                    lambda: None if self.main_finishing.is_set() else self.loop.stop())

    def _drive(self, awaitable):
        """Bounded original-loop drive; caller holds loop_drive_lock only."""
        task = self.loop.create_task(awaitable)
        self.internal_tasks.add(task)

        async def bounded():
            done, _ = await asyncio.wait((task,), timeout=self.remaining())
            if task not in done:
                raise AssertionError("SDK_RETIREMENT_ABSOLUTE_DEADLINE")
            return task.result()
        waiter = self.loop.create_task(bounded())
        self.internal_tasks.add(waiter)
        return self.loop.run_until_complete(waiter)

    async def _cooperate(self):
        """MAIN drives originals up to the absolute cutoff or fallback flag.

        asyncio.wait does not cancel pending public tasks. The private future
        is merely a notification, never a replacement cleanup or an ACK.
        """
        if self.cooperative_cutoff is None or self.fallback_requested.is_set():
            return
        await self.async_started.wait()  # Intents/gates and ALL stops started.
        wake = self.loop.create_future()
        self._cooperative_waiter = wake
        try:
            while not self.fallback_requested.is_set():
                left = min(self.cooperative_cutoff, self.deadline) - time.monotonic()
                if left <= 0:
                    break
                self._cancel_drivers()
                pending = self._snapshot_tasks()
                pending.update(task for task in self.stop_tasks if not task.done())
                if not pending:
                    break
                await asyncio.wait(pending | {wake}, timeout=left,
                                   return_when=asyncio.FIRST_COMPLETED)
        finally:
            self._cooperative_waiter = None
            if not wake.done():
                wake.set_result(None)  # No parked notification future.

    async def _join_async(self):
        if self.retire_task is not None:
            await asyncio.shield(self.retire_task)
        # Work registered after the first quiesce snapshot still owes a join.
        # No descendant role inheritance and no pending-task proof exemption.
        while True:
            self._cancel_drivers()
            pending = self._snapshot_tasks()
            pending.update(task for task in self.stop_tasks if not task.done())
            if not pending or not self.remaining():
                break
            await asyncio.wait(pending, timeout=self.remaining(),
                               return_when=asyncio.FIRST_COMPLETED)
        self._observe_task_errors()  # Include original late-close failures too.

    def _advance_framework(self):
        self.stages["framework"] += 1
        assert not self.loop.is_running(), "FRAMEWORK_FINALIZER_REQUIRES_STOPPED_LOOP"
        if self.framework is not None:
            try:
                next(self.framework)  # Exactly one post-yield advancement.
            except StopIteration:
                pass
            else:
                raise AssertionError("FRAMEWORK_YIELDED_TWICE")

    def _undo_patch(self):
        self.stages["undo"] += 1
        self.undo_attempted = True
        if self.patch is not None:
            self.patch.undo()
        self.undone = True

    def _shutdown_executor(self):
        self.stages["executor"] += 1
        self.capture_executor()
        assert not self._snapshot_tasks() and all(
            task.done() for task in self.internal_tasks), (
                "SDK_ASYNC_WORK_STILL_CAN_SUBMIT_TO_EXECUTOR")
        # Capture the real shutdown helper BEFORE Thread.start creates its OS
        # thread. Never submit shutdown to the executor being shut down.
        original_start = threading.Thread.start

        def retain_helper(actual, *args, **kwargs):
            self.executor_helpers.add(actual)
            return original_start(actual, *args, **kwargs)
        threading.Thread.start = retain_helper
        try:
            assert "timeout" in inspect.signature(
                self.loop.shutdown_default_executor).parameters, (
                    "BOUNDED_DEFAULT_EXECUTOR_SHUTDOWN_UNSUPPORTED")
            self.shutdown_task = self.loop.create_task(
                self.loop.shutdown_default_executor(timeout=self.remaining()))
            self.internal_tasks.add(self.shutdown_task)
            self._drive(self._join_shutdown())
        finally:
            threading.Thread.start = original_start
            self.capture_executor()
            self.attempt_each("worker-join", self.workers | self.executor_helpers,
                              lambda actual: actual.join(timeout=self.remaining()))

    async def _join_shutdown(self):
        await asyncio.shield(self.shutdown_task)

    def finish(self, *, native_retire, verify_native):
        """Main-thread stages, after original run_until_complete exits."""
        with self.lock:
            if self._finished:
                return self.finalized
            self._finished = True
            self.finish_claims += 1
        self.main_finishing.set()
        try:
            self.request()
            with self.loop_drive_lock:
                assert not self.loop.is_running(), "SDK_LOOP_STILL_OWNED"
                # Fence/drivers/intents/observed gates/independent stops first.
                self.attempt_each("start-async", (None,),
                                  lambda _: self._drive(self.async_started.wait()))
                # Original public cleanup gets the original LOOP BEFORE native
                # teardown can destroy its authentic completion path. None is
                # retained only for legacy pure cases; HOST passes END-3.75.
                if (self.cooperative_cutoff is not None
                        and not self.fallback_requested.is_set()):
                    self.attempt_each("join-async", (None,),
                                      lambda _: self._drive(self._cooperate()))
                assert not self.loop.is_running(), "SDK_LOOP_STILL_OWNED"
            # No loop/state/native lock across native joins or the watchdog
            # handshake. The single finish claim owns main-thread driving;
            # queued LOOP callbacks cannot run while this original LOOP stops.
            self.publish_native_handoff()
            self.attempt_each("native", (None,), lambda _: native_retire())
            if not self.close_native_handoff(self.deadline):
                # Native attempts have run, but an admitted supervisor may still
                # be inside them. Do NOT resume LOOP/finalizers/executor while it
                # remains in flight. Independent guardian safety is unchanged.
                self.fail("native-handoff",
                          AssertionError("SDK_NATIVE_HANDOFF_INCOMPLETE"))
                self._diagnose_refusal()
                return False
            with self.loop_drive_lock:
                assert not self.loop.is_running(), "SDK_LOOP_STILL_OWNED"
                self.attempt_each("join-async", (None,),
                                  lambda _: self._drive(self._join_async()))
                self.attempt_each("framework", (None,), lambda _: self._advance_framework())
                # Finalizer-created original cleanup also precedes executor
                # shutdown. Same remaining budget, never replacement closes.
                self.attempt_each("join-async", (None,),
                                  lambda _: self._drive(self._join_async()))
                # One failing acceptance/finalizer cannot skip D or undo.
                self.attempt_each("executor", (None,), lambda _: self._shutdown_executor())
                self.attempt_each("undo", (None,), lambda _: self._undo_patch())
                checks = []
                self.attempt_each("native-proof", (None,),
                                  lambda _: checks.append(bool(verify_native())))
                for record in self.resources:
                    self.attempt_each("resource-proof", (record,),
                                      lambda row: checks.append(bool(row.verify())))
                # Include children created while cancellation/stops unwound,
                # including work created during a failed earlier drain check.
                self._snapshot_tasks()
                checks.extend((
                    self.async_done.is_set(),
                    self.retire_task is not None and self.retire_task.done(),
                    all(task.done() for task in self.tasks | self.stop_tasks |
                        self.internal_tasks),
                    self.shutdown_task is not None and self.shutdown_task.done()
                    and not self.shutdown_task.cancelled()
                    and self.shutdown_task.exception() is None,
                    all(not thread.is_alive() for thread in
                        self.workers | self.executor_helpers),
                    self.undo_attempted and self.undone,
                    not (set(threading.enumerate()) - self.baseline_threads -
                         set(self.permitted_threads())),
                    time.monotonic() <= self.deadline,
                ))
                self.finalized = (
                    len(checks) == 9 + len(self.resources) and all(checks))
                if not self.finalized:
                    self.fail("physical-proof",
                              AssertionError("SDK_PHYSICAL_PROOF_MISSING"))
                    self._diagnose_refusal()
        except BaseException as exc:
            self.fail("finish", exc)
            self._diagnose_refusal()
        finally:
            self.complete.set()
        return self.finalized

    def prove_safe(self):
        with self.lock:
            assert self.finalized, "SDK_PHYSICAL_PROOF_MISSING"
            if self.safe_emissions:
                return False
            self.safe_emissions += 1
            return True


def _capture_fixture_constructors(retirement, patch):
    """Retain actual partial resources BEFORE their delegating constructors."""
    import httpx
    from ptc.test_bash_qa_integration import ScratchRuntime
    from verifiers.v1.interception.server import InterceptionServer

    server_init, server_stop = InterceptionServer.__init__, InterceptionServer.stop
    runtime_init, runtime_stop = ScratchRuntime.__init__, ScratchRuntime.stop
    client_init = httpx.AsyncClient.__init__
    transport_init = httpx.AsyncHTTPTransport.__init__

    def allowed():
        assert not retirement.requested.is_set(), "SDK_RESOURCE_ALLOCATION_RETIRED"

    def observe_server(actual, *args, **kwargs):
        allowed()
        http_servers, transports = [], []

        async def stop():
            errors = []
            runner = getattr(actual, "runner", None)
            http_server = getattr(runner, "_server", None)
            if http_server is not None:
                http_servers.append(http_server)
                for handler in tuple(http_server.connections):
                    transport = getattr(handler, "transport", None)
                    if transport is not None:
                        transports.append(transport)
                    task = getattr(handler, "_task_handler", None)
                    if task is not None:
                        retirement.retain_task(task)
            # Source-reviewed SDK stack and runner: independently try both,
            # including failure before start pushed runner.cleanup onto stack.
            if hasattr(actual, "stack"):
                try:
                    await server_stop(actual)
                except BaseException as exc:
                    errors.append(exc)
            runner = getattr(actual, "runner", None)
            if runner is not None:
                try:
                    await runner.cleanup()
                except BaseException as exc:
                    errors.append(exc)
            if errors:
                raise errors[0]

        def verify():
            runner = getattr(actual, "runner", None)
            stack = getattr(actual, "stack", None)
            return ((runner is None or (
                not runner.sites and getattr(runner, "_server", None) is None))
                and (stack is None or not stack._exit_callbacks)
                and all(not server.connections for server in http_servers)
                and all(transport.is_closing() for transport in transports))

        retirement.retain_resource("server", actual, stop, verify)
        server_init(actual, *args, **kwargs)

    def observe_runtime(actual, *args, **kwargs):
        allowed()

        async def stop():
            # This text-only lane must not have SDK subprocesses to signal.
            assert not getattr(actual, "_background", ())
            assert not getattr(actual, "_owned_foreground", ())
            if hasattr(actual, "_owned_foreground"):
                await runtime_stop(actual)
            else:
                # ScratchRuntime failed before its own fields were installed.
                # No start could have run before the constructor returned.
                assert getattr(actual, "workdir", None) is None

        def verify():
            workdir = getattr(actual, "workdir", None)
            return (not getattr(actual, "_background", ())
                    and not getattr(actual, "_owned_foreground", ())
                    and (workdir is None or not Path(workdir).exists()))

        retirement.retain_resource("runtime", actual, stop, verify)
        runtime_init(actual, *args, **kwargs)

    def observe_client(actual, *args, **kwargs):
        allowed()

        async def stop():
            if hasattr(actual, "_state"):
                await actual.aclose()
            else:
                assert not hasattr(actual, "_transport") and not hasattr(actual, "_mounts")

        def verify():
            return (actual.is_closed if hasattr(actual, "_state") else
                    not hasattr(actual, "_transport") and not hasattr(actual, "_mounts"))

        retirement.retain_resource("client", actual, stop, verify)
        client_init(actual, *args, **kwargs)

    def observe_transport(actual, *args, **kwargs):
        allowed()

        async def stop():
            if hasattr(actual, "_pool"):
                await actual.aclose()

        def verify():
            pool = getattr(actual, "_pool", None)
            return pool is None or (
                not pool.connections and not getattr(pool, "_requests", ()))

        retirement.retain_resource("transport", actual, stop, verify)
        transport_init(actual, *args, **kwargs)

    for cls, replacement in (
        (InterceptionServer, observe_server), (ScratchRuntime, observe_runtime),
        (httpx.AsyncClient, observe_client),
        (httpx.AsyncHTTPTransport, observe_transport),
    ):
        patch.setattr(cls, "__init__", replacement)


def _rows(config):
    files = list(Path(config.output_dir).rglob("*.jsonl"))
    return [json.loads(line) for path in files
            for line in path.read_text().splitlines() if line.strip()]


def _config(root, api, instrument, rollouts):
    from verifiers.v1.configs.cli.eval import EvalConfig
    config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": ID, "taskset": {"id": ID},
            "interception": {"type": "server"},
            "agent": {
                "harness": {
                    "id": ID, "max_turns": instrument.action_cap,
                    "program_timeout": instrument.program_timeout_s,
                },
                "runtime": {"type": "subprocess"},
                "max_turns": instrument.action_cap,
                "timeout": {"setup": 5.0, "rollout": 15.0,
                            "finalize": 5.0, "scoring": 15.0},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": None if rollouts == 1 else 7,
        "num_rollouts": rollouts, "shuffle": False, "max_concurrent": 2,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(root / "canonical-sdk-output"),
        "run": {"dir": "run"},
    }))
    assert type(config.env) is api.OwnedSqlEnvConfig
    assert type(config.env.taskset) is api.OwnedSqlTasksetConfig
    assert type(config.env.agent.harness) is api.OwnedSqlHarnessConfig
    return config


class _SdkInvalidStatus:
    """Fixture-only observers, never result/ACK or retirement authority."""

    def __init__(self, *, api, retirement, status, scope, owner, result):
        self.api, self.retirement, self.status = api, retirement, status
        self.scope, self.owner, self.result = scope, owner, result
        self.owner_held, self.owner_release = asyncio.Event(), asyncio.Event()
        self.env_held, self.env_release = asyncio.Event(), asyncio.Event()
        self.settled_result = self.settled_error = None
        self._owner_claimed = self._env_claimed = False
        self._score_task = scope.task_score
        self._harness_task = scope.harness_score
        self._cleanup_task = None
        self.public_task = self.env_task = None
        previous = retirement.release

        def release_all():
            try:
                previous()
            finally:
                self.release()
        retirement.release = release_all

    def release(self):
        self.owner_release.set()
        self.env_release.set()

    async def close_owner(self, actual, delegate):
        assert actual is self.owner and not self._owner_claimed
        self._owner_claimed = True
        score = self.scope.task_score
        assert isinstance(score, asyncio.Task)
        assert self._score_task is None or self._score_task is score
        self._score_task = score
        self.retirement.retain_task(score)
        self.public_task = asyncio.current_task()
        self.retirement.retain_cleanup(self.public_task, "owner-close")
        self.owner_held.set()
        await self.owner_release.wait()
        return await delegate(actual)

    async def settle_cleanup(self, task, delegate):
        if task is not self.scope.cleanup_task:
            return await delegate(task)
        assert not self._env_claimed
        self._env_claimed = True
        assert isinstance(task, asyncio.Task)
        self._cleanup_task = task
        self.env_task = asyncio.current_task()
        self.retirement.retain_task(self.env_task)
        self.retirement.retain_cleanup(task, "scope-drain")
        try:
            result = await delegate(task)
        except BaseException as error:
            self.settled_error = error
            self.env_held.set()
            await self.env_release.wait()
            raise
        else:
            self.settled_result = result
            self.env_held.set()
            await self.env_release.wait()
            return result

    def _original_failure(self, task, *, score):
        import ast
        path = Path(__file__).resolve().parents[1] / "cotrain_owned_sql.py"
        code = (self.api.OwnedSqlTask.score.__code__ if score
                else self.api._drain_scope.__code__)
        assert Path(code.co_filename).resolve() == path
        tree = ast.parse(path.read_text(), filename=str(path))
        if score:
            cls, = [node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlTask"]
            function, = [node for node in cls.body
                         if isinstance(node, ast.AsyncFunctionDef) and node.name == "score"]
            message = "owned SQL task is not valid for scoring"
        else:
            function, = [node for node in tree.body
                         if isinstance(node, ast.AsyncFunctionDef) and node.name == "_drain_scope"]
            message = "owned SQL scope cleanup failed"
        gate, = [node for node in ast.walk(function) if isinstance(node, ast.Raise)
                 and isinstance(node.exc, ast.Call)
                 and any(isinstance(arg, ast.Constant) and arg.value == message
                         for arg in node.exc.args)]
        assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
        error = task.exception()
        assert type(error) is (self.api.ScoreInfrastructureError if score else RuntimeError)
        tb = error.__traceback__
        assert tb is not None
        while tb.tb_next is not None:
            tb = tb.tb_next
        assert tb.tb_frame.f_code is code and tb.tb_lineno == gate.lineno
        assert tb.tb_frame.f_locals["scope"] is self.scope
        if score:
            assert tb.tb_frame.f_locals["result"] is self.result
        return error

    def check_provenance(self):
        scope = self.scope
        assert self.status in ("gold_error", "gold_timeout", "gold_truncated", "db_missing")
        assert type(self.result) is self.api.ExResult
        assert self.result.status == self.status and self.result.valid is False
        assert scope.result is self.result is self.owner._completion.outcome.result
        assert scope.task_score is self._score_task
        assert scope.cleanup_task is self._cleanup_task
        if self._harness_task is not None:
            assert scope.harness_score is self._harness_task
        for task in (scope.task_score, scope.harness_score, scope.cleanup_task):
            assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
        if scope.agent_task is not None:
            assert scope.agent_task.done() and not scope.agent_task.cancelled()
        assert scope.harness_score.exception() is None
        for _, task in scope.closes._entries:
            assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
            assert task.exception() is None and task.result() is None
        score_error = self._original_failure(scope.task_score, score=True)
        cleanup_error = self._original_failure(scope.cleanup_task, score=False)
        assert score_error is not cleanup_error
        assert self.settled_error is cleanup_error and self.settled_result is None
        assert scope.failed and not scope.published

    def check_ledger(self):
        self.check_provenance()
        expected = (self.scope.task_score.exception(), self.scope.cleanup_task.exception())
        errors = tuple(self.retirement.errors)  # Fresh identity set on EVERY call.
        assert expected[0] is not expected[1]
        assert any(self.retirement.primary is error for error in expected)
        assert all(stage == "task" and any(error is value for value in expected)
                   for stage, error in errors)
        assert all(any(error is value for _, error in errors) for value in expected)

    def check_target(self, *, episodes, rows, target_rewards):
        target, = [episode for episode in episodes
                   if episode.task.data is self.scope.data]
        traces = list(target.traces)
        target_rows = [row for row in rows if any(
            trace["id"] == self.scope.trace.id for trace in row["traces"])]
        # ANY reward, including a legitimate 0.0, is forbidden for this target.
        # Keep this literal gate BEFORE status/provenance/target-success checks.
        assert (not target_rewards and not self.scope.trace.rewards
                and not any(trace.rewards for trace in traces)
                and not any(trace["rewards"] for row in target_rows
                            for trace in row["traces"]
                            if trace["id"] == self.scope.trace.id)), "SDK_INVALID_TARGET_NO_REWARD"
        assert not target.ok and not self.scope.trace.ok
        assert traces and all(not trace.ok for trace in traces)
        assert len(target_rows) == 1 and not target_rows[0]["ok"]
        assert all(not trace["ok"] for row in target_rows for trace in row["traces"]
                   if trace["id"] == self.scope.trace.id)

    def oracle_failure(self, error):
        """Recognize only the late literal gate's original exception object."""
        import ast
        assert type(error) is AssertionError
        assert error.args == ("SDK_INVALID_TARGET_NO_REWARD",)
        code = type(self).check_target.__code__
        path = Path(__file__).resolve()
        assert Path(code.co_filename).resolve() == path
        tree = ast.parse(path.read_text(), filename=str(path))
        cls, = [node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "_SdkInvalidStatus"]
        method, = [node for node in cls.body
                   if isinstance(node, ast.FunctionDef) and node.name == "check_target"]
        gate, = [node for node in ast.walk(method) if isinstance(node, ast.Assert)
                 and isinstance(node.msg, ast.Constant)
                 and node.msg.value == "SDK_INVALID_TARGET_NO_REWARD"]
        tb = error.__traceback__
        assert tb is not None
        while tb.tb_next is not None:
            tb = tb.tb_next
        assert tb.tb_frame.f_code is code and tb.tb_lineno == gate.lineno
        assert tb.tb_frame.f_locals["self"] is self
        return dict(file=path.name, line=gate.lineno)

    def qualify(self, physical):
        """Post-retirement only. Fresh ledger/current physical proof, no repair."""
        retirement = self.retirement
        checkpoint = retirement.invalid_checkpoint
        assert retirement.finalized and retirement.outcome["ok"] is False
        assert retirement.stages == Counter({
            "async": 1, "framework": 1, "executor": 1, "undo": 1})
        assert retirement.workers and retirement.executor_helpers
        assert not any(thread.is_alive() for thread in (
            *retirement.workers, *retirement.executor_helpers))
        assert physical["native_proof"] is True
        assert physical["slots"] == physical["nested_safe"] == 7
        assert physical["creators"] == physical["creator_waits"] == 7
        assert all(physical[key] == 0 for key in (
            "ambiguous_creators", "live_readers", "open_slot_fds", "resource_errors"))
        assert physical["resource_stop_calls"] and all(
            type(count) is int and count == 1 for count in physical["resource_stop_calls"])
        assert all(checkpoint[key] == value for key, value in dict(
            scopes=7, dispatches=7, acks=7, owner_closes=7, program_dispatches=0,
            scorer_dispatches=7, policy_requests=7, runners=7, runner_closes=7,
            validations=7, episodes=7, rows=7, overlap=2,
            planned_tasks=8, selected_tasks=7, excluded_tasks=1).items())
        assert checkpoint["owner_barrier"] is True and checkpoint["env_barrier"] is True
        assert self._owner_claimed and self._env_claimed
        assert self.owner_release.is_set() and self.env_release.is_set()
        assert all(task in retirement.tasks and task.done() and not task.cancelled()
                   for task in (self.public_task, self.env_task))
        files = list(Path(self.output_dir).rglob("*.jsonl"))
        assert len(files) == 1
        rows = [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]
        assert len(rows) == len(self.episodes) == 7
        resource_tasks = [task for row in self.program_records
                          for _, task in row.scope.closes._entries]
        assert len(resource_tasks) == len({id(task) for task in resource_tasks}) == 14
        assert all(task.done() and not task.cancelled() and task.exception() is None
                   and task.result() is None for task in resource_tasks)
        scope = self.scope
        assert scope.result is self.result is self.owner._completion.outcome.result
        if retirement.invalid_control:
            assert self.status == "gold_error" and checkpoint["decoded_control_hits"] == 1
            assert self.result.status == "mismatch" and self.result.valid is True
            assert self.result.score == 0.0 and self.target_rewards == [("execution_accuracy", 0.0)]
            assert scope.published and not scope.failed
            assert set(scope.trace.rewards) == {"execution_accuracy"}
            assert scope.trace.rewards["execution_accuracy"].score == 0.0
            for task in (scope.task_score, scope.harness_score, scope.cleanup_task):
                assert task.done() and not task.cancelled() and task.exception() is None
            assert self._cleanup_task is scope.cleanup_task
            assert self.settled_error is None and self.settled_result is None
            assert all(episode.ok for episode in self.episodes)
            assert all(row["ok"] for row in rows)
            target, = [episode for episode in self.episodes if episode.task.data is scope.data]
            trace, = target.traces
            assert trace is scope.trace and trace.ok
            row, = [row for row in rows if any(
                trace["id"] == scope.trace.id for trace in row["traces"])]
            persisted, = row["traces"]
            assert persisted["id"] == scope.trace.id and persisted["ok"]
            assert set(persisted["rewards"]) == {"execution_accuracy"}
            assert persisted["rewards"]["execution_accuracy"]["score"] == 0.0
            assert checkpoint["successful_episodes"] == checkpoint["successful_rows"] == 7
            assert checkpoint["target_successful_rows"] == checkpoint["target_rewards"] == 1
            assert checkpoint["failed_episodes"] == 0 and checkpoint["rewards"] == 7
            error = retirement.primary
            origin = self.oracle_failure(error)
            errors = tuple(retirement.errors)
            assert errors and all(actual is error and stage in ("acceptance", "host", "task")
                                  for stage, actual in errors)
            assert {"acceptance", "host"} <= {stage for stage, _ in errors}
            return dict(
                verified=True, status=self.status, gate="SDK_INVALID_TARGET_NO_REWARD",
                origin=origin, primary_preserved=True, single_error_identity=True,
                decoded_control_hits=1, target_reward_score=0.0, episodes=7,
                successful_episodes=7, failed_episodes=0, successful_rows=7,
                target_rewards=1, target_successful_rows=1, acks=7, resource_tasks=14,
                owner_barrier=True, env_barrier=True)
        self.check_target(episodes=self.episodes, rows=rows, target_rewards=self.target_rewards)
        self.check_ledger()
        assert checkpoint["decoded_control_hits"] == 0
        assert checkpoint["successful_episodes"] == checkpoint["successful_rows"] == 6
        assert checkpoint["failed_episodes"] == 1 and checkpoint["rewards"] == 6
        assert sum(bool(row["ok"]) for row in rows) == 6

        def origin(error):
            tb = error.__traceback__
            while tb.tb_next is not None:
                tb = tb.tb_next
            return dict(file=Path(tb.tb_frame.f_code.co_filename).name, line=tb.tb_lineno)
        return dict(
            verified=True, status=self.status, episodes=7, successful_episodes=6,
            failed_episodes=1, successful_rows=6, target_rewards=0, target_successful_rows=0,
            distinct_expected_errors=2, error_identity_set_match=True, primary_member=True,
            score_origin=origin(scope.task_score.exception()),
            cleanup_origin=origin(scope.cleanup_task.exception()), acks=7, resource_tasks=14,
            owner_barrier=True, env_barrier=True)


class _SdkScoringTimeout:
    """Observe stock scoring cancellation, never manufacture a timeout/ACK."""

    @staticmethod
    def configure(config, *, draw, public_data, instrument):
        assert (len(draw.planned), len(draw.eligible), len(draw.exclusions)) == (8, 7, 1)
        assert len(public_data) == 7
        assert all(data.name == task.name and data.prompt == task.question
                   for data, task in zip(public_data, draw.eligible, strict=True))
        assert config.num_tasks in (None, 7) and config.num_rollouts == 1
        assert config.shuffle is False and config.max_concurrent == 2
        assert config.env.agent.harness.program_timeout == instrument.program_timeout_s == 5.0
        timeout = config.env.agent.timeout.model_copy(update={"scoring": 0.1})
        agent = config.env.agent.model_copy(update={"timeout": timeout})
        env = config.env.model_copy(update={"agent": agent})
        return config.model_copy(update={"env": env, "num_tasks": 7})

    def __init__(self, *, api, retirement, scope, owner):
        self.api, self.retirement, self.scope, self.owner = api, retirement, scope, owner
        self._task, self._trace, self._data = scope.task, scope.trace, scope.data
        self._score, self._harness, self._agent = None, None, None
        self._cleanup = self._checkpoint = self._reported = None
        self.receipt = self.request_task = self.score_cancel = self.error = None
        self.public_task = self.env_task = None
        self.settled_result = self.settled_error = None
        self.owner_held, self.owner_release = asyncio.Event(), asyncio.Event()
        self.env_held, self.env_release = asyncio.Event(), asyncio.Event()
        self._public_claimed = self._env_claimed = False
        self.observer_wake = asyncio.Event()
        previous = retirement.release

        def release_all():
            try:
                previous()
            finally:
                self.release()
        retirement.release = release_all
        if retirement.requested.is_set():
            self.release()

    def release(self):
        self.owner_release.set()
        self.env_release.set()
        self.observer_wake.set()

    def _retain_children(self):
        for field, name in (("_score", "task_score"), ("_harness", "harness_score"),
                            ("_agent", "agent_task")):
            task = getattr(self.scope, name)
            if task is not None:
                assert isinstance(task, asyncio.Task)
                previous = getattr(self, field)
                assert previous is None or previous is task
                setattr(self, field, task)
                self.retirement.retain_task(task)

    def request_cancel(self, actual, reason, delegate, release_controller):
        receipt = delegate(actual, reason)  # ORIGINAL public intent FIRST.
        if reason != "caller_cancelled":
            return receipt
        from ptc import sql_isolation as core
        assert actual is self.owner and type(receipt) is core.CancelReceipt
        assert receipt.status in ("accepted", "repeated")
        intent = receipt.intent
        assert type(intent) is core.CancelIntent and intent is actual._intent
        try:
            core.CancelIntent.__post_init__(intent)
            core.CancelReceipt.__post_init__(receipt)
        except (TypeError, ValueError):
            raise AssertionError("SDK_TIMEOUT_INVALID_PUBLIC_INTENT") from None
        assert intent.reason == reason and intent.invocation_id == actual.invocation_id
        assert 0 <= intent.requested_ns <= time.monotonic_ns()
        assert intent.deadline_ns == intent.requested_ns + 12_000_000_000
        current = asyncio.current_task()
        assert current is self.scope.task_score
        self._retain_children()
        if self.receipt is None:
            self.receipt, self.request_task = receipt, current
            release_controller()  # SAME receipt/task retained BEFORE controller gate.
        else:
            assert self.receipt.intent is intent and self.request_task is current
        return receipt

    def score_cancelled(self, scope, task, error):
        assert scope is self.scope and task is scope.task_score is asyncio.current_task()
        assert type(error) is asyncio.CancelledError
        assert self.score_cancel is None or self.score_cancel is error
        self._retain_children()
        self.score_cancel = error

    async def close_owner(self, actual, delegate):
        assert actual is self.owner and not self._public_claimed
        assert self.receipt is not None and self.receipt.intent is actual._intent
        self._public_claimed = True
        self._retain_children()
        self.public_task = asyncio.current_task()
        self.retirement.retain_cleanup(self.public_task, "owner-close")
        self.owner_held.set()
        self.observer_wake.set()
        await self.owner_release.wait()
        return await delegate(actual)

    def record_error(self, trace, error, delegate):
        assert trace is self._trace is self.scope.trace
        assert trace.task.data is self._data and self._reported is None
        self.error = self._reported = error
        return delegate(trace, error)

    async def settle_cleanup(self, task, delegate):
        if task is not self.scope.cleanup_task:
            return await delegate(task)
        assert not self._env_claimed and isinstance(task, asyncio.Task)
        self._env_claimed = True
        self._cleanup, self.env_task = task, asyncio.current_task()
        self.retirement.retain_cleanup(task, "scope-drain")
        self.retirement.retain_task(self.env_task)
        try:
            result = await delegate(task)
        except BaseException as error:
            self.settled_error = error
            self.env_held.set()
            await self.env_release.wait()
            raise
        else:
            self.settled_result = result
            self.env_held.set()
            await self.env_release.wait()
            return result

    def checkpoint(self, *, rows):
        assert self._checkpoint is None and self.public_task is not None
        scope = self.scope
        self._checkpoint = dict(
            public_pending=not self.public_task.done(),
            public_uncancelled=not self.public_task.cancelled() and self.public_task.cancelling() == 0,
            score_pending=not scope.task_score.done(), agent_pending=not scope.agent_task.done(),
            timeout_reported=self.error is not None or bool(scope.trace.errors),
            target_writer=any(trace["id"] == scope.trace.id for row in rows for trace in row["traces"]),
            target_rewards=len(scope.trace.rewards))
        return dict(self._checkpoint)

    def check_public_return(self):
        facts = self._checkpoint
        assert (facts is not None and facts["public_pending"] is True and facts["public_uncancelled"] is True and facts["score_pending"] is True and facts["agent_pending"] is True and facts["timeout_reported"] is False and facts["target_writer"] is False and facts["target_rewards"] == 0), "SDK_TIMEOUT_PUBLIC_RETURN_BARRIER"

    def _check_scope(self):
        import ast
        from verifiers.v1.errors import TaskError, boundary
        from verifiers.v1.rollout import Rollout
        scope = self.scope
        assert scope.task is self._task and scope.trace is self._trace
        assert scope.task.data is scope.data is scope.trace.task.data is self._data
        assert scope.task_score is self._score and scope.harness_score is self._harness
        assert scope.agent_task is self._agent and scope.cleanup_task is self._cleanup
        assert isinstance(self._score, asyncio.Task) and self._score.done() and self._score.cancelled()
        for task in (self._harness, self._agent, self._cleanup):
            assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
            assert task.exception() is None
        assert self._harness.result() is None and self._cleanup.result() is None
        assert self.settled_error is None and self.settled_result is None
        assert scope.result is None and not scope.published and not scope.trace.rewards
        assert len(scope.closes._entries) == 2
        for _, task in scope.closes._entries:
            assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
            assert task in self.retirement.tasks and task.exception() is None and task.result() is None
        error = self.error
        assert error is self._reported and type(error) is TaskError
        timeout = error.__cause__
        assert type(timeout) is TimeoutError and type(timeout.__cause__) is asyncio.CancelledError
        assert timeout.__cause__ is self.score_cancel
        code = boundary.__wrapped__.__code__
        path = Path(code.co_filename).resolve()
        assert path == Path(inspect.getfile(TaskError)).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        function, = [node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "boundary"]
        handler, = [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)
                    and isinstance(node.type, ast.Name) and node.type.id == "TimeoutError"]
        gate, = [node for node in handler.body if isinstance(node, ast.Raise)]
        tb = error.__traceback__
        assert tb is not None
        while tb.tb_next is not None:
            tb = tb.tb_next
        assert tb.tb_frame.f_code is code and tb.tb_lineno == gate.lineno
        assert handler.name == "e" and isinstance(gate.cause, ast.Name)
        assert gate.cause.id == handler.name
        assert tb.tb_frame.f_locals["error_cls"] is TaskError
        assert tb.tb_frame.f_locals["what"] == "scoring"
        close_code = Rollout.close.__code__
        path = Path(close_code.co_filename).resolve()
        assert path == Path(inspect.getfile(Rollout)).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        cls, = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Rollout"]
        function, = [node for node in cls.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "close"]
        gate, = [node for node in ast.walk(function) if isinstance(node, ast.Await)
                 and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                 and node.value.func.attr == "wait_for"]
        frames = []
        tb = timeout.__traceback__
        while tb is not None:
            frames.append(tb)
            tb = tb.tb_next
        close_frames = [tb for tb in frames if tb.tb_frame.f_code is close_code]
        assert len(close_frames) == 1
        close, = close_frames
        assert close.tb_lineno == gate.lineno
        actual = close.tb_frame.f_locals["self"]
        assert actual.task is scope.task and actual.trace is scope.trace
        assert actual.harness is scope.harness and actual.runtime is scope.runtime
        assert actual._failure is error and actual._timeouts.scoring == 0.1
        waiter_frames = [tb for tb in frames
                         if tb.tb_frame.f_code is asyncio.wait_for.__code__]
        assert len(waiter_frames) == 1
        waiter, = waiter_frames
        path = Path(asyncio.wait_for.__code__.co_filename).resolve()
        assert path == Path(asyncio.tasks.__file__).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        function, = [node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "wait_for"]
        gate, = [node for node in function.body if isinstance(node, ast.AsyncWith)]
        assert waiter.tb_lineno == gate.lineno and waiter.tb_frame.f_locals["timeout"] == 0.1
        children = waiter.tb_frame.f_locals["fut"]._children
        assert len(children) == 2 and children[0] is self._score and children[1] is self._harness

    def check_provenance(self):
        self._check_scope()
        assert self.retirement.primary is None and self.retirement.errors == []


def _sdk_timeout_completed(bundle):
    """Original seven failed episodes, no native dispatch or result conversion."""
    from ptc import sql_isolation as core
    b = bundle
    retirement = b.actor.retirement
    assert len(b.episodes) == len(b.programs) == len(b.scorers) == len(b.owners) == 7
    assert len(b.controllers) == len(b.drivers) == len(b.closes) == len(b.actor.owners) == 7
    assert len(b.sdk_tasks) == len({id(task) for task in b.sdk_tasks}) == 7
    assert all(task.data is data for task, data in zip(b.sdk_tasks, b.public_data, strict=True))
    assert all(episode.task.data is data for episode, data in zip(
        b.episodes, b.public_data, strict=True))
    assert all(not episode.ok for episode in b.episodes)
    assert b.results == b.rewards == b.program_calls == []
    assert b.actor.slots == [] and b.actor.trace.fence() == ()
    assert all(actual.role == "scorer" for actual in b.actor.owners)
    assert b.policy.calls == len(b.policy.bodies) == len(b.policy_scopes) == 7
    assert len({id(scope) for _, scope in b.policy_scopes}) == 7
    assert {id(scope) for _, scope in b.policy_scopes} == {id(row.scope) for row in b.owners}
    assert all(not any(message.get("role") == "tool" for message in body["messages"])
               for body in b.policy.bodies)
    assert (b.config.num_tasks, b.config.num_rollouts, b.config.shuffle,
            b.config.max_concurrent, b.config.env.agent.timeout.scoring) == (7, 1, False, 2, 0.1)
    assert b.instrument.scorer_timeout_s == b.admitted.timeout_s
    assert b.instrument.scorer_max_rows == b.admitted.max_rows
    assert b.instrument.compare == b.admitted.comparison
    assert len(b.admissions) >= 14 and all(actual is b.executor for actual, _, _ in b.admissions)
    assert all(task.done() and not task.cancelled() and task.result() is None for task in b.drivers)
    traces = [trace for episode in b.episodes for trace in episode.traces]
    assert len(traces) == len({id(trace) for trace in traces}) == len({trace.id for trace in traces}) == 7
    for private, data in zip(b.admitted.eligible, b.public_data, strict=True):
        owner, = [row for row in b.owners if row.sdk_task.data is data]
        runner, = [row for row in b.programs if row.kwargs["data"] is data]
        scorer, = [row for row in b.scorers if row.scope is owner.scope]
        controller, scope, actual = owner.timeout, owner.scope, owner.actual
        assert controller in b.controllers and controller.scope is scope
        assert scope.task is owner.sdk_task and scope.private is owner.task is private
        assert scope.trace.task.data is scope.data is data
        assert scope.program is runner.harness and runner.scope is scope
        assert runner.context.get(b.api._rollout) is scope
        assert scope.scorer is scorer.actual and scorer.kwargs["task"] is private
        assert scorer.kwargs["executor"] is runner.kwargs["executor"] is b.executor
        assert scorer.kwargs["instrument"] is b.instrument
        db, = [db for db in b.admitted.databases if db.db_id == private.db_id]
        assert runner.kwargs["task"] is private
        assert runner.kwargs["db_sha256"] == scorer.kwargs["db_sha256"] == db.sha256
        assert runner.kwargs["max_rows"] == b.instrument.action_max_rows == 3
        assert runner.kwargs["config"].program_timeout == b.instrument.program_timeout_s == 5.0
        assert runner.kwargs["config"].max_turns == b.instrument.action_cap == 2
        assert len(runner.runners) == len(runner.validations) == len(runner.closes) == 1
        assert runner.validations[0] == (runner.runners[0], 5.0)
        assert runner.closes[0][0] is runner.runners[0] and len(scorer.closes) == 1
        assert scorer.result is scope.result is None and not scope.published
        assert scorer.cancel_error is controller.score_cancel
        assert not scope.live and not scope.authority and scope.token is None
        assert any(trace is scope.trace for trace in traces)
        assert not scope.trace.ok and not scope.trace.rewards and len(scope.trace.errors) == 1
        controller.check_provenance()
        assert controller.public_task.done() and controller.public_task.cancelling() == 0
        assert controller.env_task.done() and not controller.env_task.cancelled()
        assert controller.env_task.exception() is None
        assert scope.harness_success and scope.harness_done.is_set()
        resource_tasks = [task for _, task in scope.closes._entries]
        assert len({id(task) for task in resource_tasks}) == 2
        assert any(task is runner.closes[0][1] for task in resource_tasks)
        assert any(task is scorer.closes[0] for task in resource_tasks)
        assert actual.db_path == Path(private.db_path)
        request = actual.request
        assert type(request) is core.ScoreRequest and request.predicted_sql == PREDICTION
        assert request.timeout_s == b.instrument.scorer_timeout_s
        assert request.max_rows == b.instrument.scorer_max_rows and request.compare == b.instrument.compare
        assert request.task.gold_sql == private.gold_sql and request.task.db_path == "/db.sqlite"
        assert request.db_sha256 == db.sha256
        completion = actual._completion
        assert completion.outcome is None and completion.abort.kind == "cancelled"
        close, = [row for row in b.closes if row.actual is actual]
        ack = completion.cleanup_ack
        assert ack is close.ack is actual._authority.ack is controller.public_task.result()
        assert ack._authority.owner is actual and ack.role == "scorer" and ack.not_started
        assert ack.released and not ack.guardian_reaps and ack.terminal_ack_sha256 is None
        assert ack.request_sha256 == core.request_sha256(request)
        assert ack.profile_sha256 == core.execution_profile_sha256(b.profile)
        intent = controller.receipt.intent
        assert intent is actual._intent and intent.reason == "caller_cancelled"
        assert controller.request_task is scope.task_score
        assert ack.cleanup_trigger_ns == intent.requested_ns
        assert ack.cleanup_deadline_ns == intent.deadline_ns == intent.requested_ns + 12_000_000_000
        assert not actual._thread.is_alive() and not actual._children and not actual._endpoints
        assert actual._host_read is None and actual._seal_lock_fd is None
        job, = scorer.actual._jobs
        assert job.invocation is actual and job.close_task is controller.public_task and job.ack is ack
    assert len(b.state.agents) == len(b.state.runtimes) == 7
    assert not b.state.external and not b.state.channels and not b.actor.forbidden_calls
    assert all(agent.harness is original and type(original) is b.api.OwnedSqlHarness
               for agent, original in b.state.agents)
    rows = _rows(b.config)
    assert len(list(Path(b.config.output_dir).rglob("*.jsonl"))) == 1 and len(rows) == 7
    assert all(not row["ok"] for row in rows)
    assert Counter(row["task"]["hash"] for row in rows) == Counter(
        episode.task.hash for episode in b.episodes)
    assert {trace["id"] for row in rows for trace in row["traces"]} == {trace.id for trace in traces}
    for row in rows:
        trace, = row["traces"]
        assert not trace["ok"] and not trace["rewards"]
        assert trace["task"]["data"] == row["task"]["data"]
        assert trace["task"]["hash"] == row["task"]["hash"]
    public_wire = json.dumps([b.policy.bodies, rows])
    assert "gold_sql" not in public_wire and "db_path" not in public_wire
    assert all(value not in public_wire for private in b.admitted.planned
               for value in (private.gold_sql, private.db_path))
    assert b.early_hits == int(b.mutant == "timeout-early-public-release")
    checkpoint = dict(
        decision="scoring-timeout-observed", planned_tasks=8, selected_tasks=7, excluded_tasks=1,
        scoring_timeout=b.config.env.agent.timeout.scoring,
        scopes=7, policy_requests=7, allocations=7, owner_closes=7, acks=7, not_started_acks=7,
        dispatches=0, program_dispatches=0, scorer_dispatches=0, native_endpoints=0,
        returned_results=0, rewards=0, successful_rows=0, episodes=7, failed_episodes=7, rows=7,
        runners=7, runner_closes=7, validations=7, resource_tasks=14,
        cancelled_score_children=7, successful_harness_children=7, original_timeout_chains=7,
        held_checkpoints=sum(controller._checkpoint["public_pending"] is True
                             for controller in b.controllers), early_release_hits=b.early_hits)
    b.checkpoint = checkpoint
    retirement.timeout_bundle = b
    retirement.record_outcome(checkpoint)
    # All original output/drains are complete BEFORE this sole control gate.
    for data in b.public_data:
        controller, = [controller for controller in b.controllers if controller.scope.data is data]
        controller.check_public_return()
    return dict(checkpoint, decision="scoring-timeout-qualified")


def _sdk_timeout_oracle_origin(error, bundle):
    import ast
    assert type(error) is AssertionError and error.args == ("SDK_TIMEOUT_PUBLIC_RETURN_BARRIER",)
    code = _SdkScoringTimeout.check_public_return.__code__
    path = Path(__file__).resolve()
    assert Path(code.co_filename).resolve() == path
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkScoringTimeout"]
    method, = [node for node in cls.body
               if isinstance(node, ast.FunctionDef) and node.name == "check_public_return"]
    gate, = [node for node in ast.walk(method) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant) and node.msg.value == "SDK_TIMEOUT_PUBLIC_RETURN_BARRIER"]
    tb = error.__traceback__
    assert tb is not None
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is code and tb.tb_lineno == gate.lineno
    target, = [controller for controller in bundle.controllers
               if controller.scope.data is bundle.public_data[0]]
    assert tb.tb_frame.f_locals["self"] is target
    assert target._checkpoint["public_pending"] is False and bundle.early_hits == 1
    return dict(file=path.name, line=gate.lineno)


def _sdk_timeout_qualification(retirement, physical):
    """Current physical proof and fresh original ledger, AFTER all retirement."""
    b = retirement.timeout_bundle
    assert retirement.finalized and physical["native_proof"] is True
    assert retirement.stages == Counter({"async": 1, "framework": 1, "executor": 1, "undo": 1})
    assert retirement.workers and retirement.executor_helpers
    assert not any(thread.is_alive() for thread in (*retirement.workers, *retirement.executor_helpers))
    assert all(physical[key] == 0 for key in (
        "slots", "nested_safe", "creators", "creator_waits", "ambiguous_creators",
        "live_readers", "open_slot_fds", "resource_errors", "nonprimary_errors"))
    assert physical["resource_stop_calls"] and all(
        type(count) is int and count == 1 for count in physical["resource_stop_calls"])
    assert b.actor.slots == [] and b.actor.trace.fence() == ()
    assert len(b.controllers) == 7
    for controller in b.controllers:
        controller._check_scope()
        assert controller.public_task.done() and controller.env_task.done()
        assert controller.owner_release.is_set() and controller.env_release.is_set()
        actual = controller.owner
        assert actual._completion.cleanup_ack is actual._authority.ack
        assert actual._authority.ack.not_started and not actual._thread.is_alive()
        assert not actual._children and not actual._endpoints
    rows = _rows(b.config)
    assert len(rows) == 7 and all(not row["ok"] for row in rows)
    assert all(not trace["ok"] and not trace["rewards"] for row in rows for trace in row["traces"])
    assert {trace["id"] for row in rows for trace in row["traces"]} == {
        controller.scope.trace.id for controller in b.controllers}
    proof = dict(
        verified=True, scoring_timeout=b.config.env.agent.timeout.scoring,
        original_timeout_chains=7, not_started_acks=7, resource_tasks=14,
        cancelled_score_children=7, successful_harness_children=7, failed_episodes=7,
        failed_rows=7, dispatches=0, rewards=0, returned_results=0,
        held_checkpoints=b.checkpoint["held_checkpoints"], early_release_hits=b.early_hits)
    if b.mutant == "timeout-early-public-release":
        assert b.early_hits == 1 and proof["held_checkpoints"] == 6
        error = retirement.primary
        origin = _sdk_timeout_oracle_origin(error, b)
        errors = tuple(retirement.errors)
        assert errors and all(actual is error and stage in ("acceptance", "host", "task")
                              for stage, actual in errors)
        assert {"acceptance", "host"} <= {stage for stage, _ in errors}
        assert retirement.outcome["ok"] is False
        return dict(proof, gate="SDK_TIMEOUT_PUBLIC_RETURN_BARRIER",
                    origin=origin, primary_preserved=True, single_error_identity=True)
    assert b.mutant == "none" and b.early_hits == 0 and proof["held_checkpoints"] == 7
    assert retirement.primary is None and retirement.errors == [] and retirement.outcome["ok"] is True
    for controller in b.controllers:
        controller.check_provenance()
        controller.check_public_return()
    return proof


def _sdk_timeout_error_diagnostic(retirement, refs):
    """Bounded read-only FINAL ledger; diagnostic data, never outcome proof."""
    with retirement.lock:
        primary = retirement.primary
        total = len(retirement.errors)
        sample = retirement.errors[:16]

    import ast
    import json
    from pathlib import Path
    from types import CodeType

    labels = (
        "_sdk_timeout_completed", "_SdkScoringTimeout._check_scope",
        "_sdk_timeout_qualification", "_sdk_acceptance", "_run_sdk_host_case",
        "_sdk_acceptance.observe_timeout_scope",
    )
    types = (
        (AssertionError, "AssertionError"), (AttributeError, "AttributeError"),
        (RuntimeError, "RuntimeError"), (TypeError, "TypeError"),
        (ValueError, "ValueError"), (TimeoutError, "TimeoutError"),
    )
    registered = []
    if type(refs) is tuple and len(refs) == len(labels):
        for label, pair in zip(labels, refs):
            if (type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str
                    and pair[0] == label and type(pair[1]) is CodeType):
                registered.append((label, pair[1]))
    source_loaded, tree, statements = False, None, {}

    def allowed_lines(label, code):
        nonlocal source_loaded, tree
        if not source_loaded:
            source_loaded = True
            # ONLY the trusted canonical source, never any traceback metadata.
            path = Path(__file__).resolve()
            tree = ast.parse(path.read_text())
        if label not in statements:
            body = tree.body
            function = None
            for name in label.split("."):
                candidates = [node for node in body
                              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                              and node.name == name]
                if len(candidates) != 1:
                    function = None
                    break
                function, = candidates
                body = function.body
            lines = set()
            if (isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and function.lineno == code.co_firstlineno):
                pending = list(function.body)
                while pending:
                    node = pending.pop()
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                        continue  # Nested bodies are NOT this function's origins.
                    if isinstance(node, (ast.Assert, ast.Raise)):
                        lines.add(node.lineno)
                    elif (label == "_sdk_timeout_qualification" and isinstance(node, ast.Assign)
                          and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                          and node.targets[0].id == "b"
                          and isinstance(node.value, ast.Attribute)
                          and node.value.attr == "timeout_bundle"
                          and isinstance(node.value.value, ast.Name)
                          and node.value.value.id == "retirement"):
                        lines.add(node.lineno)
                    pending.extend(ast.iter_child_nodes(node))
            statements[label] = lines
        return statements[label]

    def describe(error):
        error_type = type(error)
        type_label = "OTHER"
        for expected, label in types:
            if error_type is expected:
                type_label = label
                break
        if type_label == "OTHER":
            return type_label, "OTHER"  # No arbitrary object/subclass attributes.
        tb, leaf = error.__traceback__, None
        for _ in range(32):
            if tb is None:
                break
            leaf, tb = tb, tb.tb_next
        if tb is not None or leaf is None:
            return type_label, "OTHER"
        actual, line = leaf.tb_frame.f_code, leaf.tb_lineno
        for label, code in registered:
            if actual is code:  # Code objects compare structurally; NEVER use ==/hash.
                if type(line) is int and line in allowed_lines(label, code):
                    return type_label, dict(
                        file="test_owned_sql_sdk_canonical.py", function=label, line=line)
                break
        return type_label, "OTHER"

    objects, descriptions = [], []

    def token(error):
        for index, actual in enumerate(objects):
            if error is actual:
                return index + 1
        objects.append(error)
        descriptions.append(describe(error))
        return len(objects)

    present = primary is not None
    if present:
        primary_token = token(primary)  # Reserve ordinal 1, even outside sample.
        primary_type, primary_origin = descriptions[0]
    else:
        primary_token, primary_type, primary_origin = None, "NONE", "OTHER"
    entries, primary_seen = [], False
    for index, row in enumerate(sample):
        if type(row) is tuple and len(row) == 2:
            stage, error = row
        else:
            stage, error = None, row
        stage_label = (stage if type(stage) is str
                       and stage in ("acceptance", "host", "task", "timeout-qualifier") else "OTHER")
        error_token = token(error)
        error_type, error_origin = descriptions[error_token - 1]
        is_primary = present and error is primary
        primary_seen = primary_seen or is_primary
        entries.append(dict(
            ledger_index=index, error_token=error_token, is_primary=is_primary,
            stage=stage_label, type=error_type, origin=error_origin))
    payload = dict(
        ledger_total=total, ledger_omitted=total - len(entries),
        primary_present=present, primary_token=primary_token,
        primary_type=primary_type, primary_origin=primary_origin,
        primary_seen_in_sample=primary_seen, entries=entries)
    wire = (json.dumps(dict(kind="SDK_TIMEOUT_FINAL_LEDGER", diagnostic=payload),
                       separators=(",", ":")) + "\n").encode("utf-8")
    if len(wire) > 8192:
        raise ValueError("SDK_TIMEOUT_FINAL_LEDGER_UNAVAILABLE")
    return payload


class _SdkSiblingScoreFailure:
    """Observe one original Harness failure and its pending scoring sibling."""

    def __init__(self, *, api, actor, scope, target_data, omit_fault):
        admission = scope.admission
        config = admission.config
        bound = admission.bound
        admitted = bound.draw
        instrument = bound.instrument
        public_data = bound.data
        tasks = admission.tasks
        assert type(config.num_tasks) is int and config.num_tasks == 7
        assert type(config.num_rollouts) is int and config.num_rollouts == 1
        assert type(config.max_concurrent) is int and config.max_concurrent == 2
        assert config.shuffle is False
        assert len(admitted.planned) == 8
        assert len(admitted.eligible) == 7
        assert len(admitted.exclusions) == 1
        assert type(public_data) is tuple and len(public_data) == 7
        assert type(tasks) is tuple and len(tasks) == 7
        assert len({id(data) for data in public_data}) == 7
        assert len({id(task) for task in tasks}) == 7
        for task, data, private in zip(tasks, public_data, admitted.eligible, strict=True):
            assert task.data is data and task._private is private
            assert data.name == private.name
        assert scope.index == 0 and scope.task is tasks[0]
        assert scope.data is target_data is public_data[0]
        assert scope.private is admitted.eligible[0] and scope.task._private is scope.private
        assert scope.scorer._task is scope.private
        assert scope.scorer._executor is bound.executor
        assert scope.scorer._instrument is instrument
        assert instrument.scorer_timeout_s == admitted.timeout_s
        assert instrument.scorer_max_rows == admitted.max_rows
        assert instrument.compare == admitted.comparison and instrument.program_timeout_s == 5
        assert type(omit_fault) is bool
        current = asyncio.current_task()
        assert isinstance(current, asyncio.Task) and current is scope.task_score
        assert current.get_coro().cr_code is api.OwnedSqlTask.score.__code__
        from ptc import sql_isolation as core
        self.api, self.actor, self.retirement, self.scope = api, actor, actor.retirement, scope
        self.target_data, self.target_private, self.scorer = target_data, scope.private, scope.scorer
        self.score_task, self.harness_task, self.cleanup_task, self.agent_task = current, None, None, None
        self._task, self._trace, self._harness, self._runtime = (
            scope.task, scope.trace, scope.harness, scope.runtime)
        self._scoring_timeout = config.env.agent.timeout.scoring
        self.owner = self.owner_record = self.controller_delegate = None
        self.public_task = self.env_task = None
        self.receipt = self.request_task = self.request_code = self.request_line = None
        self.cancel_error = self.settled_result = self.settled_error = None
        self.owner_checkpoint = self.env_checkpoint = self._oracle_error = None
        self.fault = RuntimeError("SDK_SIBLING_HARNESS_SCORE_FAILURE")
        self.omit_fault = omit_fault
        self.postbase_hits = self.fault_hits = self.omitted_fault_hits = 0
        self.owner_calls = self.owner_delegations = self.env_calls = 0
        self._owner_claimed = self._env_claimed = False
        self.controller_gate, self.controller_entered = threading.Event(), threading.Event()
        self.postbase_seen, self.intent_seen, self.observer_wake = (
            asyncio.Event(), asyncio.Event(), asyncio.Event())
        self.owner_entered, self.owner_held, self.owner_release = (
            asyncio.Event(), asyncio.Event(), asyncio.Event())
        self.env_held, self.env_release = asyncio.Event(), asyncio.Event()
        self.hooks = api._HOOKS
        self.codes = dict(
            scope_check=getattr(api._Scope.check, "__wrapped__", api._Scope.check).__code__,
            task_score=api.OwnedSqlTask.score.__code__,
            harness_score=api.OwnedSqlHarness.score.__code__,
            cleanup=api._drain_scope.__code__, execute=core.OwnedSqlInvocation.execute.__code__,
            aclose=getattr(core.OwnedSqlInvocation.aclose, "__wrapped__",
                           core.OwnedSqlInvocation.aclose).__code__,
            request_cancel=getattr(core.OwnedSqlInvocation.request_cancel, "__wrapped__",
                                   core.OwnedSqlInvocation.request_cancel).__code__,
            injection=type(self).check_scope.__code__, oracle=type(self).check_fault_origin.__code__)
        self.retirement.retain_task(current)
        with actor.spawn_lock:
            assert not actor.stopping.is_set()
            actor.gates.append(self.controller_gate)
        previous = self.retirement.release

        def release_all():
            try:
                previous()
            finally:
                self.release()
        self.retirement.release = release_all
        if self.retirement.requested.is_set():
            self.release()

    def _retain_children(self):
        scope = self.scope
        assert scope.task_score is self.score_task
        for task in (scope.harness_score, scope.agent_task):
            if task is not None:
                assert isinstance(task, asyncio.Task)
                self.retirement.retain_task(task)
        if scope.harness_score is not None:
            assert self.harness_task is None or self.harness_task is scope.harness_score
            self.harness_task = scope.harness_score
        if scope.agent_task is not None:
            assert self.agent_task is None or self.agent_task is scope.agent_task
            self.agent_task = scope.agent_task

    def _observed_fault(self):
        task = self.harness_task
        return (self.fault_hits == 1 and isinstance(task, asyncio.Task)
                and task is self.scope.harness_score and task.done()
                and not task.cancelled() and task.exception() is self.fault)

    def retain_owner(self, actual):
        assert self.owner is None and self.owner_record is None
        assert not self.controller_gate.is_set() or self.retirement.requested.is_set()
        assert any(owner is actual for owner in self.actor.owners)
        self.owner = actual  # BEFORE the original owner constructor.

    def bind_owner(self, record):
        assert record.actual is self.owner and self.owner_record is None
        assert record.scope is self.scope and record.sdk_task is self._task
        assert record.task is self.target_private and record.scorer.actual is self.scorer
        assert record.scorer.scope is self.scope and record.scorer.score_task is self.score_task
        assert self.owner.role == "scorer" and self.owner._thread is None
        assert self.owner._completion is None and self.owner._candidate is None
        assert not self.controller_gate.is_set() or self.retirement.requested.is_set()
        self.owner_record, self.controller_delegate = record, self.owner._controller
        self.owner._controller = self.run_controller

    def run_controller(self, binding):
        self.controller_entered.set()
        self.actor.emit("SDK_CONTROLLER_HELD", index=self.scope.index)
        assert self.controller_gate.wait(max(0, self.actor.end - 3.75 - time.monotonic())), (
            "SDK_CONTROLLER_PRE_ADMISSION_DEADLINE")
        if self.actor.stopping.is_set() or self.retirement.requested.is_set():
            assert self.owner.snapshot().intent is not None
        return self.controller_delegate(binding)

    def check_scope(self, scope, *args, delegate, **kwargs):
        result = delegate(scope, *args, **kwargs)  # ORIGINAL check FIRST, including refusals.
        if scope is not self.scope or asyncio.current_task() is not scope.harness_score:
            return result
        self._retain_children()
        assert self.harness_task.get_coro().cr_code is self.codes["harness_score"]
        assert scope.task is self._task and scope.trace is self._trace
        assert scope.harness is self._harness and scope.runtime is self._runtime
        assert scope.task_score is self.score_task and not self.score_task.done()
        assert scope.scorer is self.scorer and scope.data is self.target_data
        assert scope.private is self.target_private and scope.trace.task.data is self.target_data
        assert self.owner is not None and self.owner_record.actual is self.owner
        assert self.owner_record.scope is scope and self.controller_delegate is not None
        assert not self.controller_gate.is_set() and self.owner._candidate is None
        assert self.owner._completion is None
        assert not any(slot["invocation"] is self.owner for slot in self.actor.slots)
        assert scope.result is None and not scope.published and not scope.trace.rewards
        assert scope.harness_success is False and self.postbase_hits == 0
        self.postbase_hits += 1
        self.postbase_seen.set()
        if self.omit_fault:
            self.omitted_fault_hits += 1
            return result
        self.fault_hits += 1
        raise self.fault

    def request_cancel(self, actual, reason, delegate, *, caller_code, caller_line, caller_task):
        receipt = delegate(actual, reason)  # ORIGINAL public receipt, before any observation.
        if reason != "caller_cancelled":
            return receipt
        if self.retirement.requested.is_set() or not self._observed_fault():
            if actual is self.owner:
                self.controller_gate.set()  # Cleanup only, NEVER qualifying observation.
                self.observer_wake.set()
            return receipt
        import ast
        from ptc import sql_isolation as core
        assert actual is self.owner and type(receipt) is core.CancelReceipt
        assert caller_code is self.codes["execute"] is core.OwnedSqlInvocation.execute.__code__
        assert caller_task is self.score_task is self.scope.task_score is asyncio.current_task()
        path = Path(caller_code.co_filename).resolve()
        assert path == Path(core.__file__).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == "OwnedSqlInvocation"]
        execute, = [node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "execute"]
        handler, = [node for node in ast.walk(execute) if isinstance(node, ast.ExceptHandler)
                    and any(isinstance(child, ast.Constant) and child.value == "caller_cancelled"
                            for child in ast.walk(node))]
        call, = [node for node in ast.walk(handler) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "request_cancel"]
        assert caller_line == call.lineno
        assert receipt.status in ("accepted", "repeated")
        intent = receipt.intent
        assert type(intent) is core.CancelIntent and intent is actual._intent
        try:
            core.CancelIntent.__post_init__(intent)
            core.CancelReceipt.__post_init__(receipt)
        except (TypeError, ValueError):
            raise AssertionError("SDK_SIBLING_INVALID_PUBLIC_INTENT") from None
        assert intent.reason == reason and intent.invocation_id == actual.invocation_id
        assert 0 <= intent.requested_ns <= time.monotonic_ns()
        assert intent.deadline_ns == intent.requested_ns + 12_000_000_000
        if self.receipt is None:
            assert not self.controller_gate.is_set()
            self.receipt, self.request_task = receipt, caller_task
            self.request_code, self.request_line = caller_code, caller_line
            self.intent_seen.set()
            self.controller_gate.set()
            self.observer_wake.set()
        else:
            assert self.receipt.intent is intent and self.request_task is caller_task
            assert self.request_code is caller_code and self.request_line == caller_line
        return receipt

    def score_cancelled(self, scope, task, error):
        assert scope is self.scope and task is self.score_task is scope.task_score
        assert task is asyncio.current_task() and type(error) is asyncio.CancelledError
        assert self.cancel_error is None or self.cancel_error is error
        self._retain_children()
        self.cancel_error = error

    async def close_owner(self, actual, delegate):
        assert actual is self.owner and not self._owner_claimed
        self._owner_claimed = True
        self.owner_calls += 1
        self._retain_children()
        self.public_task = asyncio.current_task()
        self.retirement.retain_cleanup(self.public_task, "owner-close")
        if self._observed_fault() and not self.retirement.requested.is_set():
            self.owner_entered.set()
            while self.receipt is None and not self.retirement.requested.is_set():
                self.observer_wake.clear()
                await self.observer_wake.wait()
            if not self.retirement.requested.is_set():
                assert self.intent_seen.is_set() and self.receipt.intent is actual._intent
                self.owner_held.set()
                self.observer_wake.set()
                await self.owner_release.wait()
        self.owner_delegations += 1
        try:
            return await delegate(actual)
        finally:
            self.observer_wake.set()

    async def settle_cleanup(self, task, delegate):
        if task is not self.scope.cleanup_task:
            return await delegate(task)
        assert not self._env_claimed and isinstance(task, asyncio.Task)
        self._env_claimed = True
        self.env_calls += 1
        self._retain_children()
        self.cleanup_task, self.env_task = task, asyncio.current_task()
        self.retirement.retain_cleanup(task, "scope-drain")
        self.retirement.retain_task(self.env_task)
        try:
            result = await delegate(task)
        except BaseException as error:
            self.settled_error = error
            if self._observed_fault() and not self.retirement.requested.is_set():
                self.env_held.set()
                self.observer_wake.set()
                await self.env_release.wait()
            raise  # SAME original exception; no except-as local used after this block.
        else:
            self.settled_result = result
            if self._observed_fault() and not self.retirement.requested.is_set():
                self.env_held.set()
                self.observer_wake.set()
                await self.env_release.wait()
            return result

    def checkpoint_owner(self, *, rows):
        assert self.owner_checkpoint is None and self.owner_held.is_set()
        scope = self.scope
        facts = dict(
            intent_observed=self.intent_seen.is_set() and self.receipt.intent is self.owner._intent,
            original_execute_callsite=self.request_code is self.codes["execute"],
            controller_released_after_intent=self.controller_gate.is_set() and self.receipt is not None,
            public_pending=not self.public_task.done(),
            public_uncancelled=not self.public_task.cancelled() and self.public_task.cancelling() == 0,
            score_pending=not self.score_task.done(), score_cancelling=self.score_task.cancelling() > 0,
            cleanup_pending=isinstance(scope.cleanup_task, asyncio.Task) and not scope.cleanup_task.done(),
            scope_live=scope.live, token_retained=scope.token is not None,
            authority=scope.authority, result_absent=scope.result is None,
            published=scope.published, target_rewards=len(scope.trace.rewards),
            target_rows=sum(any(trace["id"] == scope.trace.id for trace in row["traces"])
                            for row in rows))
        assert all(value is True for key, value in facts.items()
                   if key not in ("authority", "published", "target_rewards", "target_rows"))
        assert facts["authority"] is facts["published"] is False
        assert facts["target_rewards"] == facts["target_rows"] == 0
        self.owner_checkpoint = facts

    def checkpoint_env(self, *, rows):
        assert self.env_checkpoint is None and self.env_held.is_set()
        scope = self.scope
        facts = dict(
            cleanup_done=self.cleanup_task.done() and not self.cleanup_task.cancelled(),
            score_cancelled=self.score_task.done() and self.score_task.cancelled(),
            harness_fault_identity=self._observed_fault(),
            cleanup_error_identity=self.cleanup_task.exception() is self.settled_error
                and self.settled_error is not None,
            resources_done=all(task.done() and not task.cancelled() and task.exception() is None
                               and task.result() is None for _, task in scope.closes._entries),
            env_pending=not self.env_task.done(), scope_live=scope.live,
            token_retained=scope.token is not None, authority=scope.authority,
            result_absent=scope.result is None, published=scope.published,
            target_rewards=len(scope.trace.rewards),
            target_rows=sum(any(trace["id"] == scope.trace.id for trace in row["traces"])
                            for row in rows))
        assert all(value is True for key, value in facts.items()
                   if key not in ("authority", "published", "target_rewards", "target_rows"))
        assert facts["authority"] is facts["published"] is False
        assert facts["target_rewards"] == facts["target_rows"] == 0
        self.env_checkpoint = facts

    def release(self):
        self.controller_gate.set()
        self.owner_release.set()
        self.env_release.set()
        self.observer_wake.set()

    def check_fault_origin(self):
        try:
            assert self.postbase_hits == self.fault_hits == 1 and self.omitted_fault_hits == 0 and self._observed_fault(), "SDK_SIBLING_FAULT_ORIGIN"
        except AssertionError as error:
            self._oracle_error = error
            raise

    @staticmethod
    def _locations(api):
        import ast
        path = Path(api.__file__).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == "OwnedSqlHarness"]
        method, = [node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
                   and node.name == "score"]
        body, = [node for node in method.body if isinstance(node, ast.Try)]
        postbase = body.body[1]
        assert ast.dump(postbase.value.func) == ast.dump(ast.parse("scope.check", mode="eval").body)
        cleanup, = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "_drain_scope"]
        drain, = [node for node in ast.walk(cleanup) if isinstance(node, ast.Raise)]
        origins = dict(harness_postbase=dict(file=path.name, line=postbase.lineno),
                       cleanup=dict(file=path.name, line=drain.lineno))
        path = Path(__file__).resolve()
        tree = ast.parse(path.read_text(), filename=str(path))
        cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == "_SdkSiblingScoreFailure"]
        check, = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "check_scope"]
        raised, = [node for node in ast.walk(check) if isinstance(node, ast.Raise)
                   and isinstance(node.exc, ast.Attribute) and node.exc.attr == "fault"]
        oracle, = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                   and node.name == "check_fault_origin"]
        gate, = [node for node in ast.walk(oracle) if isinstance(node, ast.Assert)
                 and isinstance(node.msg, ast.Constant) and node.msg.value == "SDK_SIBLING_FAULT_ORIGIN"]
        origins.update(injection=dict(file=path.name, line=raised.lineno),
                       oracle=dict(file=path.name, line=gate.lineno))
        return origins

    @staticmethod
    def _frames(error):
        frames, tb = [], error.__traceback__
        while tb is not None:
            frames.append(tb)
            tb = tb.tb_next
        assert frames
        return frames

    def check_provenance(self):
        from ptc import sql_isolation as core
        scope = self.scope
        assert self.api._HOOKS is self.hooks
        self.api._check_hooks()
        assert self.codes["task_score"] is self.api.OwnedSqlTask.score.__code__
        assert self.codes["harness_score"] is self.api.OwnedSqlHarness.score.__code__
        assert self.codes["cleanup"] is self.api._drain_scope.__code__
        assert self.codes["execute"] is core.OwnedSqlInvocation.execute.__code__
        assert self.codes["scope_check"] is getattr(
            self.api._Scope.check, "__wrapped__", self.api._Scope.check).__code__
        assert self.codes["aclose"] is getattr(
            core.OwnedSqlInvocation.aclose, "__wrapped__", core.OwnedSqlInvocation.aclose).__code__
        assert self.codes["request_cancel"] is getattr(
            core.OwnedSqlInvocation.request_cancel, "__wrapped__",
            core.OwnedSqlInvocation.request_cancel).__code__
        assert self.codes["injection"] is type(self).check_scope.__code__
        assert self.codes["oracle"] is type(self).check_fault_origin.__code__
        assert scope.task is self._task and scope.trace is self._trace
        assert scope.harness is self._harness and scope.runtime is self._runtime
        assert scope.data is self.target_data is self._task.data is scope.trace.task.data
        assert scope.private is self.target_private is self._task._private
        assert scope.scorer is self.scorer and self.scorer._task is self.target_private
        assert scope.task_score is self.score_task and isinstance(self.score_task, asyncio.Task)
        assert self.score_task.done() and self.score_task.cancelled()
        assert scope.harness_score is self.harness_task and self._observed_fault()
        assert self.harness_task.get_coro().cr_code is self.codes["harness_score"]
        assert isinstance(scope.cleanup_task, asyncio.Task) and scope.cleanup_task is self.cleanup_task
        assert self.cleanup_task.done() and not self.cleanup_task.cancelled()
        assert self.cleanup_task.get_coro().cr_code is self.codes["cleanup"]
        assert scope.agent_task is self.agent_task and self.agent_task.done()
        assert not self.agent_task.cancelled()
        assert type(self.fault) is RuntimeError and self.fault.args == ("SDK_SIBLING_HARNESS_SCORE_FAILURE",)
        cleanup = self.cleanup_task.exception()
        assert type(cleanup) is RuntimeError and cleanup is not self.fault
        assert cleanup.args == ("owned SQL scope cleanup failed",)
        assert self.settled_error is cleanup and self.settled_result is None
        origins = self._locations(self.api)
        frames = self._frames(self.fault)
        harness_frames = [tb for tb in frames if tb.tb_frame.f_code is self.codes["harness_score"]]
        assert len(harness_frames) == 1
        harness = harness_frames[0]
        assert harness.tb_lineno == origins["harness_postbase"]["line"]
        assert harness.tb_frame.f_locals["scope"] is scope
        leaf = frames[-1]
        assert leaf.tb_frame.f_code is self.codes["injection"]
        assert leaf.tb_lineno == origins["injection"]["line"] and leaf.tb_frame.f_locals["self"] is self
        leaf = self._frames(cleanup)[-1]
        assert leaf.tb_frame.f_code is self.codes["cleanup"]
        assert leaf.tb_lineno == origins["cleanup"]["line"] and leaf.tb_frame.f_locals["scope"] is scope
        assert type(self.cancel_error) is asyncio.CancelledError
        cancel_codes = [tb.tb_frame.f_code for tb in self._frames(self.cancel_error)]
        assert any(code is self.codes["task_score"] for code in cancel_codes)
        assert any(code is self.codes["execute"] for code in cancel_codes)
        assert self.request_task is self.score_task and self.request_code is self.codes["execute"]
        assert self.receipt is not None and self.receipt.intent is self.owner._intent
        assert self.receipt.intent.deadline_ns == self.receipt.intent.requested_ns + 12_000_000_000
        assert scope.result is None and not scope.published and not scope.trace.rewards
        assert len(scope.closes._entries) == 2
        for task in (self.score_task, self.harness_task, self.cleanup_task, self.agent_task):
            assert task in self.retirement.tasks
        for _, task in scope.closes._entries:
            assert isinstance(task, asyncio.Task) and task in self.retirement.tasks
            assert task.done() and not task.cancelled() and task.exception() is None
            assert task.result() is None and task.cancelling() == 0

    def check_ledger(self):
        self.check_provenance()
        with self.retirement.lock:
            errors, primary = tuple(self.retirement.errors), self.retirement.primary
        expected = {id(self.fault), id(self.settled_error)}
        assert len(expected) == 2 and {id(error) for _, error in errors} == expected
        assert all(stage == "task" for stage, _ in errors)
        assert primary is self.fault or primary is self.settled_error


def _sdk_sibling_origins(bundle):
    assert bundle.codes is bundle.controller.codes and bundle.hooks is bundle.controller.hooks
    return _SdkSiblingScoreFailure._locations(bundle.api)


def _sdk_sibling_oracle_origin(error, bundle):
    controller = bundle.controller
    assert type(error) is AssertionError and error is controller._oracle_error
    assert error.args == ("SDK_SIBLING_FAULT_ORIGIN",)
    assert bundle.codes["oracle"] is _SdkSiblingScoreFailure.check_fault_origin.__code__
    origin = _sdk_sibling_origins(bundle)["oracle"]
    leaf = controller._frames(error)[-1]
    assert leaf.tb_frame.f_code is bundle.codes["oracle"] and leaf.tb_lineno == origin["line"]
    assert leaf.tb_frame.f_locals["self"] is controller
    assert controller.fault_hits == 0 and controller.omitted_fault_hits == 1
    assert controller.fault.__traceback__ is None
    return origin


def _sdk_sibling_qualification(retirement, physical):
    """Fresh ledger, original final state and current physical proof, never SAFE alone."""
    b = retirement.sibling_bundle
    c, checkpoint = b.controller, b.checkpoint
    assert retirement.finalized and physical["native_proof"] is True
    assert retirement.stages == Counter({"async": 1, "framework": 1, "executor": 1, "undo": 1})
    assert retirement.workers and retirement.executor_helpers
    assert not any(thread.is_alive() for thread in (*retirement.workers, *retirement.executor_helpers))
    assert all(task.done() for task in retirement.tasks)
    assert all(physical[key] == 0 for key in (
        "ambiguous_creators", "live_readers", "open_slot_fds", "resource_errors"))
    assert physical["resource_stop_calls"] and all(
        type(count) is int and count == 1 for count in physical["resource_stop_calls"])
    assert retirement.outcome["ok"] is False
    control = c.fault_hits == 0 and c.omitted_fault_hits == 1
    count = 7 if control else 6
    assert len(b.actor.slots) == len(b.actor.trace.fence()) == count
    assert all(type(physical[key]) is int and physical[key] == count
               for key in ("slots", "nested_safe", "creators", "creator_waits"))
    assert len(b.episodes) == len(b.owners) == len(b.closes) == len(b.programs) == len(b.scorers) == 7
    assert sum(bool(episode.ok) for episode in b.episodes) == count
    assert len(b.results) == len(b.rewards) == count and not b.program_calls
    rows = _rows(b.config)
    assert len(rows) == 7 and sum(bool(row["ok"]) for row in rows) == count
    scopes = [record.scope for record in b.owners]
    assert len({id(scope) for scope in scopes}) == 7
    assert {trace["id"] for row in rows for trace in row["traces"]} == {
        scope.trace.id for scope in scopes}
    assert len(b.sdk_tasks) == len(b.public_data) == 7
    assert len({id(task) for task in b.sdk_tasks}) == len({id(data) for data in b.public_data}) == 7
    assert all(episode.task.data is data for episode, data in zip(
        b.episodes, b.public_data, strict=True))
    for row in rows:
        trace, = row["traces"]
        scope, = [scope for scope in scopes if scope.trace.id == trace["id"]]
        assert row["ok"] is trace["ok"] is scope.trace.ok
        if row["ok"]:
            assert set(trace["rewards"]) == {"execution_accuracy"}
            assert trace["rewards"]["execution_accuracy"]["score"] == 1.0
        else:
            assert not trace["rewards"]
    assert len({id(task) for scope in scopes for _, task in scope.closes._entries}) == 14
    for record in b.owners:
        scope, actual = record.scope, record.actual
        assert not scope.live and not scope.authority and scope.token is None
        assert scope.task is record.sdk_task and scope.private is record.task
        assert scope.scorer is record.scorer.actual and scope.task.data is scope.data
        for task in (scope.agent_task, scope.task_score, scope.harness_score, scope.cleanup_task):
            assert isinstance(task, asyncio.Task) and task.done() and task in retirement.tasks
        assert not scope.harness_score.cancelled() and not scope.cleanup_task.cancelled()
        assert len(scope.closes._entries) == 2
        assert all(task.done() and not task.cancelled() and task.exception() is None
                   and task.result() is None for _, task in scope.closes._entries)
        close, = [row for row in b.closes if row.actual is actual]
        assert close.task.done() and not close.task.cancelled() and close.task.cancelling() == 0
        assert close.ack is close.task.result() is actual._completion.cleanup_ack is actual._authority.ack
        assert actual._authority.owner is actual and actual.role == "scorer"
        assert actual._thread is not None and not actual._thread.is_alive()
        assert all(endpoint.fd is None for endpoint in actual._endpoints)
        assert actual._host_read is None and actual._seal_lock_fd is None
        assert not actual._resources
        assert all(stream is None or stream.closed
                   for child in actual._children
                   for stream in (child.stdin, child.stdout, child.stderr))
        ack = close.ack
        slots = [slot for slot in b.actor.slots if slot["invocation"] is actual]
        if ack.not_started:
            assert not actual._children and not actual._endpoints
            assert not slots and not ack.guardian_reaps
            assert ack.terminal_ack_sha256 is None
        else:
            assert len(actual._children) == len(slots) == len(ack.guardian_reaps) == 1
            child, = actual._children
            assert type(child.pid) is int and child.pid > 0
            assert type(child.returncode) is int
            assert child._creator_waited is True and child._creator_ambiguous is False
            assert ack.guardian_reaps == tuple((child.pid, child.returncode)
                                              for child in actual._children)
            slot, = slots
            assert slot["invocation"] is actual and slot["process"] is child
            entries = [entry for entry in b.actor.trace.fence() if entry["process"] is child]
            assert len(entries) == 1
            entry, = entries
            assert entry["process"] is child and entry["registry"] is actual._children
            assert entry["kind"] == "guardian"
        if scope is c.scope and not control:
            assert close.ack.not_started is True and scope.task_score.cancelled()
        else:
            assert close.ack.not_started is False and not scope.task_score.cancelled()
            assert scope.harness_score.exception() is None and scope.harness_success is True
            assert scope.cleanup_task.exception() is None
            assert scope.result is record.scorer.result is actual._completion.outcome.result
            assert scope.published and set(scope.trace.rewards) == {"execution_accuracy"}
            assert scope.trace.rewards["execution_accuracy"].score == 1.0
    assert checkpoint["decision"] == "sibling-score-failure-observed" and checkpoint["overlap"] == 2
    assert set(checkpoint) == set((
        "decision planned_tasks selected_tasks excluded_tasks scopes policy_requests overlap "
        "allocations program_allocations scorer_allocations dispatches program_dispatches "
        "scorer_dispatches target_dispatches acks not_started_acks owner_closes resource_tasks "
        "runners runner_closes validations returned_results target_returned_results rewards "
        "target_rewards episodes successful_episodes failed_episodes rows successful_rows "
        "failed_rows target_successful_rows fault_hits omitted_fault_hits cancelled_score_children "
        "failed_harness_children successful_harness_children owner_barrier env_barrier").split())
    assert all(type(value) is int for key, value in checkpoint.items()
               if key not in ("decision", "owner_barrier", "env_barrier"))
    assert type(checkpoint["owner_barrier"]) is type(checkpoint["env_barrier"]) is bool
    counts = dict(
        planned_tasks=8, selected_tasks=7, excluded_tasks=1, scopes=7, policy_requests=7,
        allocations=7, program_allocations=0, scorer_allocations=7, program_dispatches=0,
        scorer_dispatches=count, target_dispatches=int(control), not_started_acks=int(not control),
        owner_closes=7, runners=7, runner_closes=7, validations=7, episodes=7, rows=7,
        target_returned_results=int(control), failed_episodes=int(not control),
        failed_rows=int(not control), target_successful_rows=int(control),
        fault_hits=int(not control), omitted_fault_hits=int(control),
        cancelled_score_children=int(not control), failed_harness_children=int(not control),
        successful_harness_children=count)
    assert all(checkpoint[key] == value for key, value in counts.items())
    assert checkpoint["owner_barrier"] is checkpoint["env_barrier"] is (not control)
    assert checkpoint["dispatches"] == checkpoint["returned_results"] == checkpoint["rewards"] == count
    assert checkpoint["acks"] == 7 and checkpoint["resource_tasks"] == 14
    assert checkpoint["successful_rows"] == checkpoint["successful_episodes"] == count
    assert checkpoint["target_rewards"] == int(control)
    if control:
        assert c.owner_checkpoint is c.env_checkpoint is None
        assert not any(event.is_set() for event in (c.intent_seen, c.owner_held, c.env_held))
        assert physical["nonprimary_errors"] == 0
        error = retirement.primary
        origin = _sdk_sibling_oracle_origin(error, b)
        with retirement.lock:
            errors, primary = tuple(retirement.errors), retirement.primary
        assert primary is error and errors
        assert all(actual is error and stage in ("acceptance", "host", "task")
                   for stage, actual in errors)
        assert {"acceptance", "host"} <= {stage for stage, _ in errors}
        return dict(
            verified=True, gate="SDK_SIBLING_FAULT_ORIGIN", origin=origin,
            omitted_fault_hits=1, dispatches=7, acks=7, resource_tasks=14,
            successful_episodes=7, successful_rows=7, returned_results=7, rewards=7,
            primary_preserved=True, single_error_identity=True)
    c.check_fault_origin()
    c.check_ledger()  # Fresh, all stages and distinct identity SET, no length/order whitelist.
    assert c.owner_checkpoint is not None and c.env_checkpoint is not None
    assert c.owner_calls == c.owner_delegations == c.env_calls == 1
    assert c.public_task.done() and c.env_task.done()
    assert c.owner_release.is_set() and c.env_release.is_set()
    origins = _sdk_sibling_origins(b)
    return dict(
        verified=True, episodes=7, successful_episodes=6, failed_episodes=1,
        successful_rows=6, failed_rows=1, dispatches=6, acks=7, not_started_acks=1,
        resource_tasks=14, returned_results=6, rewards=6, target_rewards=0,
        owner_barrier=True, env_barrier=True, distinct_expected_errors=2,
        error_identity_set_match=True, primary_member=True,
        harness_postbase_origin=origins["harness_postbase"],
        injection_origin=origins["injection"], cleanup_origin=origins["cleanup"])


def _sdk_sibling_completed(bundle):
    """Validate actual decoded results, issued ACKs and original SDK writer output."""
    from bench.score import ExResult
    from ptc import sql_isolation as core
    from ptc.harness import PTCHarness, PTCHarnessConfig
    b, c = bundle, bundle.controller
    retirement = b.actor.retirement
    assert b.api._HOOKS is b.hooks is c.hooks and b.codes is c.codes
    b.api._check_hooks()
    assert (len(b.admitted.planned), len(b.admitted.eligible), len(b.admitted.exclusions)) == (8, 7, 1)
    assert (b.config.num_tasks, b.config.num_rollouts, b.config.max_concurrent,
            b.config.shuffle) == (7, 1, 2, False)
    assert b.config.env.agent.timeout.scoring == c._scoring_timeout
    assert b.instrument.scorer_timeout_s == b.admitted.timeout_s
    assert b.instrument.scorer_max_rows == b.admitted.max_rows
    assert b.instrument.compare == b.admitted.comparison
    assert len(b.episodes) == len(b.programs) == len(b.scorers) == len(b.owners) == 7
    assert len(b.closes) == len(b.actor.owners) == len(b.public_data) == len(b.sdk_tasks) == 7
    assert len({id(task) for task in b.sdk_tasks}) == len({id(data) for data in b.public_data}) == 7
    assert all(task.data is data for task, data in zip(b.sdk_tasks, b.public_data, strict=True))
    assert all(episode.task.data is task.data and episode.task.hash == task.hash
               for episode, task in zip(b.episodes, b.sdk_tasks, strict=True))
    assert b.policy.calls == len(b.policy.bodies) == len(b.policy_scopes) == 7
    assert not b.program_calls and all(actual.role == "scorer" for actual in b.actor.owners)
    assert len({id(row.actual) for row in b.scorers}) == 7
    assert {id(scope) for _, scope in b.policy_scopes} == {id(row.scope) for row in b.owners}
    assert len({id(row.scope) for row in b.owners}) == 7
    assert all(not any(message.get("role") == "tool" for message in body["messages"])
               for body in b.policy.bodies)
    traces = [trace for episode in b.episodes for trace in episode.traces]
    assert len(traces) == len({id(trace) for trace in traces}) == len({trace.id for trace in traces}) == 7
    resource_tasks = []
    for index, (private, data, sdk_task) in enumerate(zip(
            b.admitted.eligible, b.public_data, b.sdk_tasks, strict=True)):
        owner, = [row for row in b.owners if row.sdk_task is sdk_task]
        program, = [row for row in b.programs if row.kwargs["data"] is data]
        scorer, = [row for row in b.scorers if row.scope is owner.scope]
        actual, scope = owner.actual, owner.scope
        assert type(actual) is core.OwnedSqlInvocation and actual.role == "scorer"
        assert any(item is actual for item in b.actor.owners)
        assert scope.index == index and scope.task is sdk_task and owner.task is scope.private is private
        assert sdk_task._private is private and scope.data is data is scope.trace.task.data
        assert scope.trace.task.data is sdk_task.data and any(trace is scope.trace for trace in traces)
        assert scope.scorer is scorer.actual and owner.scorer is scorer
        assert scope.program is program.harness and type(program.harness) is PTCHarness
        assert program.scope is scope and program.context.get(b.api._rollout) is scope
        assert scope.scorer._task is private and scope.scorer._executor is b.executor
        assert scope.scorer._instrument is b.instrument
        assert scorer.kwargs["task"] is program.kwargs["task"] is private
        assert scorer.kwargs["executor"] is program.kwargs["executor"] is b.executor
        assert scorer.kwargs["instrument"] is b.instrument
        db, = [row for row in b.admitted.databases if row.db_id == private.db_id]
        assert scorer.kwargs["db_sha256"] == program.kwargs["db_sha256"] == db.sha256
        assert program.kwargs["max_rows"] == b.instrument.action_max_rows == 3
        assert type(program.kwargs["config"]) is PTCHarnessConfig
        assert program.kwargs["config"].id == PTCHarnessConfig().id
        assert program.kwargs["config"].max_turns == b.instrument.action_cap == 2
        assert program.kwargs["config"].program_timeout == b.instrument.program_timeout_s == 5.0
        assert len(program.runners) == len(program.validations) == len(program.closes) == len(scorer.closes) == 1
        assert program.validations[0] == (program.runners[0], 5.0)
        assert program.closes[0][0] is program.runners[0]
        assert len(scope.closes._entries) == 2
        tasks = [task for _, task in scope.closes._entries]
        assert any(task is program.closes[0][1] for task in tasks)
        assert any(task is scorer.closes[0] for task in tasks)
        for task in tasks:
            assert isinstance(task, asyncio.Task) and task in retirement.tasks
            assert task.done() and not task.cancelled() and task.cancelling() == 0
            assert task.exception() is None and task.result() is None
        resource_tasks.extend(tasks)
        for task in (scope.task_score, scope.harness_score, scope.agent_task, scope.cleanup_task):
            assert isinstance(task, asyncio.Task) and task.done()
            retirement.retain_task(task)  # Original tasks, plain observation, no driver exemption.
        assert scope.task_score is scorer.score_task
        assert scope.task_score.get_coro().cr_code is b.codes["task_score"]
        assert scope.harness_score.get_coro().cr_code is b.codes["harness_score"]
        assert scope.cleanup_task.get_coro().cr_code is b.codes["cleanup"]
        assert scope.harness_done.is_set() and not scope.harness_score.cancelled()
        assert not scope.live and not scope.authority and scope.token is None
        close, = [row for row in b.closes if row.actual is actual]
        assert close.task.done() and not close.task.cancelled() and close.task.cancelling() == 0
        completion = actual._completion
        assert type(completion) is core.InvocationCompletion
        completion.__post_init__()  # Original concrete outcome/abort and sealed ACK associations.
        ack = completion.cleanup_ack
        assert type(ack) is core.CleanupCompleteAck
        assert ack is actual._authority.ack is close.ack is close.task.result()
        assert ack._authority is actual._authority and ack._authority.owner is actual
        assert ack.invocation_id == actual.invocation_id and ack.role == "scorer" and ack.released
        assert 0 <= ack.cleanup_trigger_ns <= ack.completed_ns <= ack.cleanup_deadline_ns
        assert ack.completed_ns <= time.monotonic_ns()
        assert ack.request_sha256 == core.request_sha256(actual.request)
        assert ack.profile_sha256 == core.execution_profile_sha256(b.profile)
        assert actual.db_path == Path(private.db_path)
        request = actual.request
        assert type(request) is core.ScoreRequest
        assert request.predicted_sql == owner.prediction == scope.trace.last_reply == "fixture-score-status:match"
        assert request.db_sha256 == db.sha256 and request.task.gold_sql == private.gold_sql
        assert request.task.db_path == "/db.sqlite"
        assert request.timeout_s == b.instrument.scorer_timeout_s
        assert request.max_rows == b.instrument.scorer_max_rows and request.compare == b.instrument.compare
        assert actual._thread is not None and not actual._thread.is_alive()
        assert all(endpoint.fd is None for endpoint in actual._endpoints)
        assert actual._host_read is None and actual._seal_lock_fd is None
        assert not actual._resources
        assert all(stream is None or stream.closed
                   for child in actual._children
                   for stream in (child.stdin, child.stdout, child.stderr))
        slots = [slot for slot in b.actor.slots if slot["invocation"] is actual]
        if ack.not_started:
            assert not actual._children and not actual._endpoints
            assert not slots and not ack.guardian_reaps
            assert ack.terminal_ack_sha256 is None
        else:
            assert len(actual._children) == len(slots) == len(ack.guardian_reaps) == 1
            child, = actual._children
            assert type(child.pid) is int and child.pid > 0
            assert type(child.returncode) is int
            assert child._creator_waited is True and child._creator_ambiguous is False
            assert ack.guardian_reaps == tuple((child.pid, child.returncode)
                                              for child in actual._children)
            slot, = slots
            assert slot["invocation"] is actual and slot["process"] is child
            entries = [entry for entry in b.actor.trace.fence() if entry["process"] is child]
            assert len(entries) == 1
            entry, = entries
            assert entry["process"] is child and entry["registry"] is actual._children
            assert entry["kind"] == "guardian"
        job, = scorer.actual._jobs
        assert job.invocation is actual and job.close_task is close.task and job.ack is ack
        slots = [slot for slot in b.actor.slots if slot["invocation"] is actual]
        if completion.outcome is None:
            assert completion.abort.kind == "cancelled" and scope.result is scorer.result is None
            assert scope.task_score.cancelled() and not scope.published and not scope.trace.rewards
            assert ack.not_started and not slots and not ack.guardian_reaps
            assert ack.terminal_ack_sha256 is None
            intent = actual._intent
            assert type(intent) is core.CancelIntent and intent.reason == "caller_cancelled"
            assert ack.cleanup_trigger_ns == intent.requested_ns
            assert ack.cleanup_deadline_ns == intent.deadline_ns == intent.requested_ns + 12_000_000_000
        else:
            result = completion.outcome.result
            assert type(result) is ExResult and result is scorer.result is scope.result
            assert any(value is result for value in b.results)
            assert result.status == "match" and result.valid is True and result.score == 1.0
            assert (result.n_pred_rows, result.n_gold_rows) == (7, 11)
            assert completion.abort is None and actual._intent is None
            assert not ack.not_started and ack.child_waits and ack.thread_joins
            assert len(ack.guardian_reaps) == len(slots) == 1 and ack.terminal_ack_sha256 is not None
            assert scope.harness_success and scope.harness_score.exception() is None
            assert not scope.task_score.cancelled() and scope.task_score.exception() is None
            assert scope.cleanup_task.exception() is None and scope.published and scope.trace.ok
            assert set(scope.trace.rewards) == {"execution_accuracy"}
            assert scope.trace.rewards["execution_accuracy"].score == 1.0
            reward, = [row for row in b.rewards if row[0] is actual]
            assert reward[1] is scope.trace and reward[2] is scorer
    assert len(resource_tasks) == len({id(task) for task in resource_tasks}) == 14
    assert len(b.results) == len({id(result) for result in b.results})
    assert len(b.results) == len(b.rewards)
    assert len(b.state.agents) == len(b.state.runtimes) == 7
    assert all(agent.harness is original and type(original) is b.api.OwnedSqlHarness
               for agent, original in b.state.agents)
    assert not b.state.external and not b.state.channels and not b.actor.forbidden_calls
    assert len(b.admissions) >= 14 and all(actual is b.executor for actual, _, _ in b.admissions)
    assert len(b.actor.trace.fence()) == len(b.actor.slots)
    assert all(row["process"]._creator_waited and not row["process"]._creator_ambiguous
               for row in b.actor.trace.fence())
    for slot in b.actor.slots:
        evidence, = [item for item in slot["messages"] if item["kind"] == "EVIDENCE"]
        assert not evidence["forbidden"] and not evidence["hits"] and evidence["released"]
        assert sum(row["actor"] == "role" for row in evidence["actual"]) == 1
        assert sum(row["actor"] == "cli" for row in evidence["actual"]) >= 2
        assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                   and type(row["returncode"]) is int for row in evidence["actual"])
    rows = _rows(b.config)
    assert len(list(Path(b.config.output_dir).rglob("*.jsonl"))) == 1 and len(rows) == 7
    assert Counter(row["task"]["hash"] for row in rows) == Counter(
        episode.task.hash for episode in b.episodes)
    assert {trace["id"] for row in rows for trace in row["traces"]} == {trace.id for trace in traces}
    for row in rows:
        wire, = row["traces"]
        trace, = [trace for trace in traces if trace.id == wire["id"]]
        assert wire["task"]["hash"] == row["task"]["hash"] == trace.task.hash
        assert wire["task"]["data"] == row["task"]["data"]
        assert row["ok"] is wire["ok"] is trace.ok
        assert wire["rewards"] == ({
            "execution_accuracy": wire["rewards"]["execution_accuracy"]} if trace.rewards else {})
        if trace.rewards:
            assert wire["rewards"]["execution_accuracy"]["score"] == 1.0
    public_wire = json.dumps([b.policy.bodies, rows])
    assert "gold_sql" not in public_wire and "db_path" not in public_wire
    assert all(value not in public_wire for private in b.admitted.planned
               for value in (private.gold_sql, private.db_path))
    scopes = [row.scope for row in b.owners]
    checkpoint = dict(
        decision="sibling-score-failure-observed",
        planned_tasks=len(b.admitted.planned), selected_tasks=len(b.admitted.eligible),
        excluded_tasks=len(b.admitted.exclusions), scopes=len(scopes), policy_requests=b.policy.calls,
        overlap=b.checkpoint["overlap"], allocations=len(b.actor.owners),
        program_allocations=sum(owner.role == "program" for owner in b.actor.owners),
        scorer_allocations=sum(owner.role == "scorer" for owner in b.actor.owners),
        dispatches=len(b.actor.slots),
        program_dispatches=sum(slot["invocation"].role == "program" for slot in b.actor.slots),
        scorer_dispatches=sum(slot["invocation"].role == "scorer" for slot in b.actor.slots),
        target_dispatches=sum(slot["invocation"] is c.owner for slot in b.actor.slots),
        acks=sum(row.ack is not None for row in b.closes),
        not_started_acks=sum(row.ack.not_started for row in b.closes), owner_closes=len(b.closes),
        resource_tasks=len(resource_tasks), runners=sum(len(row.runners) for row in b.programs),
        runner_closes=sum(len(row.closes) for row in b.programs),
        validations=sum(len(row.validations) for row in b.programs),
        returned_results=len(b.results), target_returned_results=int(c.scope.result is not None),
        rewards=len(b.rewards), target_rewards=len(c.scope.trace.rewards), episodes=len(b.episodes),
        successful_episodes=sum(bool(episode.ok) for episode in b.episodes),
        failed_episodes=sum(not episode.ok for episode in b.episodes), rows=len(rows),
        successful_rows=sum(bool(row["ok"]) for row in rows), failed_rows=sum(not row["ok"] for row in rows),
        target_successful_rows=sum(bool(row["ok"]) for row in rows if any(
            trace["id"] == c.scope.trace.id for trace in row["traces"])),
        fault_hits=c.fault_hits, omitted_fault_hits=c.omitted_fault_hits,
        cancelled_score_children=sum(scope.task_score.cancelled() for scope in scopes),
        failed_harness_children=sum(scope.harness_score.exception() is not None for scope in scopes),
        successful_harness_children=sum(scope.harness_score.exception() is None for scope in scopes),
        owner_barrier=c.owner_checkpoint is not None, env_barrier=c.env_checkpoint is not None)
    b.checkpoint = checkpoint
    retirement.sibling_bundle = b
    retirement.record_outcome(checkpoint)
    # First fault-specific gate. Control's seven original successes already drained.
    c.check_fault_origin()
    c.check_provenance()
    retirement._observe_task_errors()  # Original recorder, original completed Tasks only.
    c.check_ledger()
    assert checkpoint["overlap"] == 2
    assert checkpoint["dispatches"] == checkpoint["returned_results"] == checkpoint["rewards"] == 6
    assert checkpoint["target_dispatches"] == checkpoint["target_returned_results"] == 0
    assert checkpoint["not_started_acks"] == checkpoint["cancelled_score_children"] == 1
    assert checkpoint["failed_harness_children"] == checkpoint["failed_episodes"] == checkpoint["failed_rows"] == 1
    assert checkpoint["successful_harness_children"] == checkpoint["successful_episodes"] == checkpoint["successful_rows"] == 6
    assert checkpoint["target_rewards"] == checkpoint["target_successful_rows"] == 0
    assert checkpoint["owner_barrier"] is checkpoint["env_barrier"] is True
    return checkpoint


def _sdk_sibling_diagnostic_refs():
    """Immutable ORIGINAL code roots, captured before acceptance is invoked."""
    from types import CodeType
    acceptance = _sdk_acceptance.__code__
    nested = (
        "observe_sibling_scope", "release_sibling_dispatch",
        "sibling_harness_done", "observed_scope_check")
    refs = [("_sdk_sibling_completed", _sdk_sibling_completed.__code__)]
    for name in nested:
        code, = [value for value in acceptance.co_consts
                 if type(value) is CodeType and value.co_name == name]
        refs.append(("_sdk_acceptance." + name, code))
    refs.extend((("_sdk_acceptance", acceptance),
                 ("_run_sdk_host_case", _run_sdk_host_case.__code__)))
    for name in (
            "checkpoint_owner", "checkpoint_env", "check_fault_origin",
            "check_provenance", "check_ledger", "_locations", "_frames"):
        refs.append(("_SdkSiblingScoreFailure." + name,
                     getattr(_SdkSiblingScoreFailure, name).__code__))
    refs.extend((
        ("_sdk_sibling_qualification", _sdk_sibling_qualification.__code__),
        ("_sdk_sibling_origins", _sdk_sibling_origins.__code__),
        ("_sdk_sibling_oracle_origin", _sdk_sibling_oracle_origin.__code__),
        ("_SdkSiblingScoreFailure.check_scope", _SdkSiblingScoreFailure.check_scope.__code__)))
    return tuple(refs)


def _sdk_sibling_error_diagnostic(retirement, refs):
    """Closed read-only final ledger. Never acceptance or physical proof."""
    with retirement.lock:
        primary = retirement.primary
        total = len(retirement.errors)
        sample = retirement.errors[:16]

    import ast
    import json
    from pathlib import Path
    from types import CodeType

    labels = (
        "_sdk_sibling_completed", "_sdk_acceptance.observe_sibling_scope",
        "_sdk_acceptance.release_sibling_dispatch", "_sdk_acceptance.sibling_harness_done",
        "_sdk_acceptance.observed_scope_check", "_sdk_acceptance", "_run_sdk_host_case",
        "_SdkSiblingScoreFailure.checkpoint_owner", "_SdkSiblingScoreFailure.checkpoint_env",
        "_SdkSiblingScoreFailure.check_fault_origin", "_SdkSiblingScoreFailure.check_provenance",
        "_SdkSiblingScoreFailure.check_ledger", "_SdkSiblingScoreFailure._locations",
        "_SdkSiblingScoreFailure._frames", "_sdk_sibling_qualification",
        "_sdk_sibling_origins", "_sdk_sibling_oracle_origin", "_SdkSiblingScoreFailure.check_scope")
    types = (
        (AssertionError, "AssertionError"), (AttributeError, "AttributeError"),
        (RuntimeError, "RuntimeError"), (TypeError, "TypeError"),
        (ValueError, "ValueError"), (TimeoutError, "TimeoutError"))
    scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    eligible = (ast.Assert, ast.Raise, ast.Assign, ast.AnnAssign, ast.AugAssign)
    comprehensions = (
        (ast.GeneratorExp, "<genexpr>", "genexpr"),
        (ast.ListComp, "<listcomp>", "listcomp"),
        (ast.SetComp, "<setcomp>", "setcomp"),
        (ast.DictComp, "<dictcomp>", "dictcomp"))
    registered = []
    # Load ONLY trusted canonical source. Never a traceback-provided pathname.
    tree = ast.parse(Path(__file__).resolve().read_text())

    def add(label, code, node, leaf, owner=None):
        if len(registered) >= 256:
            raise ValueError("SDK_SIBLING_FINAL_LEDGER_UNAVAILABLE")
        statements, children = [], []

        def visit(current, statement):
            if isinstance(current, scopes):
                return
            if isinstance(current, eligible):
                statement = current
                statements.append(current)
            for kind, name, kind_label in comprehensions:
                if isinstance(current, kind):
                    children.append((current, statement, name, kind_label))
                    return  # Its descendants belong to its own code ancestry.
            for child in ast.iter_child_nodes(current):
                visit(child, statement)

        if leaf == "function":
            for child in node.body:
                visit(child, None)
        else:
            for child in ast.iter_child_nodes(node):
                visit(child, owner)
        registered.append((label, code, leaf, statements, owner))
        for child_code in code.co_consts:
            if type(child_code) is not CodeType:
                continue
            matches = [(child, statement, kind_label)
                       for child, statement, name, kind_label in children
                       if child_code.co_name == name
                       and child_code.co_firstlineno == child.lineno]
            # Multiple comprehensions on one line cannot be safely paired.
            siblings = [value for value in code.co_consts
                        if type(value) is CodeType and value.co_name == child_code.co_name
                        and value.co_firstlineno == child_code.co_firstlineno]
            if len(matches) == len(siblings) == 1:
                child, statement, kind_label = matches[0]
                if statement is not None:
                    add(label, child_code, child, kind_label, statement)

    if type(refs) is tuple and len(refs) == len(labels):
        for expected, pair in zip(labels, refs):
            if not (type(pair) is tuple and len(pair) == 2
                    and type(pair[0]) is str and pair[0] == expected
                    and type(pair[1]) is CodeType):
                continue
            label, code = pair
            body, function = tree.body, None
            for name in label.split("."):
                matches = [node for node in body
                           if isinstance(node, scopes[:3]) and node.name == name]
                if len(matches) != 1:
                    function = None
                    break
                function = matches[0]
                body = function.body
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            first = min([function.lineno] + [n.lineno for n in function.decorator_list])
            if code.co_name == function.name and code.co_firstlineno == first:
                add(label, code, function, "function")

    def describe(error):
        type_label = "OTHER"
        for expected, label in types:
            if type(error) is expected:
                type_label = label
                break
        if type_label == "OTHER":
            return type_label, "OTHER", "UNINSPECTED_TYPE"  # No unknown attribute access.
        tb, deepest = error.__traceback__, None
        if tb is None:
            # Current absence only: an earlier traceback may have been cleared.
            return type_label, "OTHER", "NO_TRACEBACK"
        for _ in range(32):
            if tb is None:
                break
            deepest, tb = tb, tb.tb_next
        if tb is not None:
            return type_label, "OTHER", "LIMIT_EXCEEDED"
        actual, line = deepest.tb_frame.f_code, deepest.tb_lineno
        for label, code, leaf, statements, owner in registered:
            if actual is not code:  # Never structural code equality/hash.
                continue
            if leaf == "function":
                matches = [node for node in statements
                           if node.lineno <= line <= node.end_lineno]
            else:
                matches = [owner] if owner.lineno <= line <= owner.end_lineno else []
            if len(matches) == 1:
                statement = matches[0]
                site = ("assert" if isinstance(statement, ast.Assert) else
                        "raise" if isinstance(statement, ast.Raise) else "assign")
                return type_label, dict(
                    file="test_owned_sql_sdk_canonical.py", function=label,
                    line=statement.lineno, site=site, leaf=leaf), "RESOLVED"
            return type_label, "OTHER", "UNRESOLVED_SITE"
        return type_label, "OTHER", "UNREGISTERED_LEAF"

    objects, descriptions = [], []
    def token(error):
        for index, actual in enumerate(objects):
            if error is actual:
                return index + 1
        objects.append(error)
        descriptions.append(describe(error))
        return len(objects)

    present = primary is not None
    if present:
        primary_token = token(primary)  # Reserve ordinal 1 even outside sample.
        primary_type, primary_origin, _ = descriptions[0]
    else:
        primary_token, primary_type, primary_origin = None, "NONE", "OTHER"
    entries, primary_seen = [], False
    for index, row in enumerate(sample):
        if type(row) is tuple and len(row) == 2:
            stage, error = row
        else:
            stage, error = None, row
        stage = (stage if type(stage) is str and stage in (
            "acceptance", "host", "task", "sibling-dispatch", "sibling-qualifier",
            "task-role", "late-driver") else "OTHER")
        ordinal = token(error)
        error_type, origin, traceback_state = descriptions[ordinal - 1]
        is_primary = present and error is primary
        primary_seen = primary_seen or is_primary
        entries.append(dict(
            ledger_index=index, error_token=ordinal, is_primary=is_primary,
            stage=stage, type=error_type, origin=origin, traceback_state=traceback_state))
    payload = dict(
        ledger_total=total, ledger_omitted=total - len(entries),
        primary_present=present, primary_token=primary_token, primary_type=primary_type,
        primary_origin=primary_origin, primary_seen_in_sample=primary_seen, entries=entries)
    wire = (json.dumps(dict(kind="SDK_SIBLING_FINAL_LEDGER", diagnostic=payload),
                       separators=(",", ":")) + "\n").encode("utf-8")
    if len(wire) > 8192:
        raise ValueError("SDK_SIBLING_FINAL_LEDGER_UNAVAILABLE")
    return payload


def _sdk_sibling_persist_host_result(result, *, destination):
    """Best effort, fully validated original HOST dict, exclusive caller path."""
    import json
    import os

    def integer(value):
        return type(value) is int and 0 <= value <= 2**63 - 1

    def shape(value, fields):
        return (type(value) is dict and len(value) == len(fields)
                and all(type(key) is str and key in fields for key in value)
                and all(check(value[key]) for key, check in fields.items()))

    def origin(value):
        return shape(value, dict(
            file=lambda v: type(v) is str and v in (
                "test_owned_sql_sdk_canonical.py", "cotrain_owned_sql.py"),
            line=lambda v: integer(v) and v > 0))

    def qualification(value):
        if shape(value, dict(verified=lambda v: v is False)):
            return True
        fields = dict.fromkeys((
            "episodes successful_episodes failed_episodes successful_rows failed_rows "
            "dispatches acks not_started_acks resource_tasks returned_results rewards "
            "target_rewards distinct_expected_errors").split(), integer)
        fields.update(dict.fromkeys((
            "verified owner_barrier env_barrier error_identity_set_match primary_member"
        ).split(), lambda v: type(v) is bool))
        fields.update(dict.fromkeys((
            "harness_postbase_origin injection_origin cleanup_origin").split(), origin))
        return shape(value, fields) and value["verified"] is True

    def physical(value):
        fields = dict.fromkeys((
            "slots nested_safe creators creator_waits ambiguous_creators live_readers "
            "open_slot_fds resource_errors nonprimary_errors").split(), integer)
        fields.update(
            native_proof=lambda v: type(v) is bool,
            resource_stop_calls=lambda v: type(v) is list and len(v) <= 64
            and all(integer(count) for count in v))
        # Preserve existing fields, but partial failed receipts are permitted.
        return (type(value) is dict and all(
            type(key) is str and key in fields and fields[key](item)
            for key, item in value.items()))

    counters = (
        "planned_tasks selected_tasks excluded_tasks scopes policy_requests overlap "
        "allocations program_allocations scorer_allocations dispatches program_dispatches "
        "scorer_dispatches target_dispatches acks not_started_acks owner_closes resource_tasks "
        "runners runner_closes validations returned_results target_returned_results rewards "
        "target_rewards episodes successful_episodes failed_episodes rows successful_rows "
        "failed_rows target_successful_rows fault_hits omitted_fault_hits cancelled_score_children "
        "failed_harness_children successful_harness_children mutation_hits hook_hits "
        "retirement_errors executor_workers live_executor_workers executor_helpers "
        "live_executor_helpers").split()
    fields = dict.fromkeys(counters, integer)
    fields.update(dict.fromkeys((
        "owner_barrier env_barrier safe ok physical_finalized outer_actual_wait").split(),
        lambda v: type(v) is bool))
    fields.update(
        decision=lambda v: type(v) is str and v == "sibling-score-failure-observed",
        error=lambda v: type(v) is str and v in (
            "AssertionError", "AttributeError", "RuntimeError", "TypeError", "ValueError",
            "TimeoutError", "KeyError", "IndexError"),
        host_faults=lambda v: type(v) is list and not v,
        retirement_stages=lambda v: type(v) is dict and all(
            type(key) is str and key in ("async", "framework", "executor", "undo")
            and integer(count) for key, count in v.items()),
        program_physical=physical, sibling_qualification=qualification,
        outer_retirement=lambda v: shape(v, dict(
            actual_wait=lambda x: type(x) is bool, returncode=integer,
            streams_closed=lambda x: type(x) is bool,
            ledger_released=lambda x: type(x) is bool)))
    fd = None
    try:
        if not (type(result) is dict and all(
                type(key) is str and key in fields and fields[key](value)
                for key, value in result.items())):
            return False
        raw = (json.dumps(result, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
        if len(raw) > 32768:
            return False
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        complete = os.write(fd, raw) == len(raw)
        closing, fd = fd, None
        os.close(closing)
        return complete
    except BaseException:
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except BaseException:
                pass


async def _run_sdk_host_case(
        *, loop, root, prepared, phase, mutant, profile, executor, actor):
    """Record acceptance only; HOST owns every physical retirement stage."""
    retirement = actor.retirement
    retirement.retain_driver(asyncio.current_task())
    if phase == "sdk-sibling-score-failure":
        try:
            retirement.sibling_diagnostic_refs = _sdk_sibling_diagnostic_refs()
        except BaseException:
            pass  # Diagnostic registry failure is never an acceptance failure.
    try:
        if phase.startswith("sdk-retire-"):
            from ptc.test_owned_sql_sdk_retirement_physical import (
                _SdkPhysicalProbe, _SdkRetirementCheckpoint)
            retirement.physical_probe = _SdkPhysicalProbe(phase, actor)
        result = await _sdk_acceptance(
            loop=loop, root=root, prepared=prepared, phase=phase,
            mutant=mutant, profile=profile, executor=executor, actor=actor)
        if phase.startswith("sdk-retire-") and isinstance(result, _SdkRetirementCheckpoint):
            probe = retirement.physical_probe
            assert phase in ("sdk-retire-framework-finalizer", "sdk-retire-two-slot-verification")
            assert retirement.primary is None
            probe.checkpoint_returned = True
            probe.checkpoint_primary_unset = retirement.primary is None
            result = dict(decision="retirement-checkpoint")
            retirement.record_outcome(dict(ok=False, **result))
            return result
        retirement.record_outcome(dict(ok=True, **result))
        return result
    except BaseException as exc:
        retirement.fail("acceptance", exc)
        raise
    finally:
        retirement.request()  # No assertion-bearing teardown in this frame.


async def _sdk_acceptance(
        *, loop, root, prepared, phase, mutant, profile, executor, actor):
    """HOST-only delegate; actor holds fixture resources, never ACK authority."""
    try:
        _timeline = getattr(actor, "_sdk_timeline", None)
        if _timeline is not None:
            _timeline.note(2)
    except BaseException:
        pass
    import cotrain_owned_sql as api
    from bench import prepare
    from bench.score import ExResult
    from ptc import sql_isolation as core, sql_owned_program, sql_owned_score
    from ptc.harness import PTCHarness, PTCHarnessConfig
    from ptc.test_bash_qa_eval_integration import framework
    from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
    from train.sql_episodes import InstrumentSettings
    from verifiers.v1.task import TaskData
    from verifiers.v1.trace import Trace
    from verifiers.v1.utils import loaders

    probe = getattr(actor.retirement, "physical_probe", None)
    sibling_case = phase == "sdk-sibling-score-failure"
    timeout_case = phase == "sdk-scoring-timeout"
    invalid_status = phase.removeprefix("sdk-invalid-") if phase.startswith("sdk-invalid-") else None
    invalid_case = invalid_status is not None
    if invalid_case:
        assert invalid_status in ("gold_error", "gold_timeout", "gold_truncated", "db_missing")
    cancel_program = phase == "sdk-cancel-program"
    cancel_scorer = phase == "sdk-cancel-scorer"
    cancel_case = cancel_program or cancel_scorer
    program_case = phase == PROGRAM_PHASE or cancel_program
    if program_case:
        from ptc.test_ptc_qa_activation_integration import _program_call
    assert (phase in ("sdk-positive-one", "sdk-positive-two", PROGRAM_PHASE,
                     "sdk-cancel-program", "sdk-cancel-scorer")
            or invalid_case or timeout_case or sibling_case or (probe is not None and probe.phase == phase))
    assert mutant == "none" or (
        phase == PROGRAM_PHASE and mutant == "program-observation-sentinel") or (
        phase == "sdk-invalid-gold_error" and mutant == "invalid-target-zero") or (
        timeout_case and mutant == "timeout-early-public-release") or (
        sibling_case and mutant == "omit-sibling-fault")
    assert asyncio.get_running_loop() is loop and executor.profile is profile
    rollouts = 2 if phase == "sdk-positive-two" else 1
    expected = 7 * rollouts
    expected_owners = expected + int(program_case)
    corpus, draw, supplement = map(Path, prepared[:3])
    draw_sha, supplement_sha = prepared[3:]
    retained_documents = draw.read_bytes(), supplement.read_bytes()
    # This is the real first-party generator with a PRIVATE patch context.
    # Its OriginalSocket captures the strict host guard, not external access.
    patch = pytest.MonkeyPatch()
    actor.retirement.patch = patch
    _capture_fixture_constructors(actor.retirement, patch)
    framework_owner = framework.__wrapped__(patch, root)
    if phase == "sdk-retire-framework-finalizer":
        from ptc.test_owned_sql_sdk_retirement_physical import _sdk_framework_finalizer
        framework_owner = _sdk_framework_finalizer(framework_owner, probe)
    actor.retirement.framework = framework_owner
    state = next(framework_owner)
    actor.retirement.state = state
    programs, scorers, admissions, loads, load_calls = [], [], [], [], []
    owners, closes, results, rewards, score_tasks = [], [], [], [], {}
    controller_gates, entered = [], []
    cancel_release_events = []
    dispatch_turn = [0]
    released_first = [False]
    original_init = core.OwnedSqlInvocation.__init__
    original_allocate = core.PilotExecutor.owned_score
    original_allocate_program = core.PilotExecutor.owned_program
    original_close = core.OwnedSqlInvocation.aclose
    original_request_cancel = core.OwnedSqlInvocation.request_cancel
    original_program = sql_owned_program.build_owned_sql_program_harness
    original_scorer = sql_owned_score.build_owned_sql_scorer
    original_load = prepare.load_validated_draw
    original_admit = core.PilotExecutor.admit_program
    original_score = sql_owned_score.OwnedSqlScorer.score_sql
    original_scorer_close = sql_owned_score.OwnedSqlScorer.aclose
    original_reward = Trace.record_reward
    original_record_error = Trace.record_error
    original_task_init = api.OwnedSqlTask.__init__
    sdk_tasks = []
    caller = None
    program_calls, policy_scopes = [], []
    target_scope = []
    sentinel_hits = [0]
    invalid_controller, invalid_target_rewards = [], []
    invalid_hits, invalid_barriers = [0], {}
    timeout_controllers, timeout_drivers = [], []
    timeout_early_hits = [0]
    original_create_task = asyncio.create_task
    original_settle = api._settle
    original_scope_check = api._Scope.check
    sibling_controller, sibling_observers = [], []
    sibling_queue, sibling_callbacks = [], set()
    sibling_active, sibling_overlap = [None], [0]

    def release_sibling_dispatch():
        if not sibling_case or actor.retirement.requested.is_set() or actor.stopping.is_set():
            return
        if sibling_active[0] is not None:
            return  # Only the ORIGINAL public ACK may advance this entry.
        for record in sibling_queue:
            scope = record.scope
            child = scope.harness_score
            if (record.controller_gate.is_set() or child is None or not child.done()
                    or child.cancelled() or child.exception() is not None
                    or not scope.harness_success or not scope.authority or not scope.live):
                continue
            assert child.get_coro().cr_code is api.OwnedSqlHarness.score.__code__
            sibling_active[0] = record
            record.controller_gate.set()
            return

    def sibling_harness_done(task):
        actor.retirement.retain_task(task)
        try:
            release_sibling_dispatch()
        except BaseException as error:
            actor.retirement.fail("sibling-dispatch", error)
            actor.retirement.request()

    def observed_scope_check(scope, *args, **kwargs):
        controller = sibling_controller[0] if sibling_controller else None
        try:
            if controller is not None:
                return controller.check_scope(scope, *args, delegate=original_scope_check, **kwargs)
            return original_scope_check(scope, *args, **kwargs)
        finally:
            child = scope.harness_score
            if child is not None and child is asyncio.current_task() and child not in sibling_callbacks:
                assert child.get_coro().cr_code is api.OwnedSqlHarness.score.__code__
                sibling_callbacks.add(child)
                actor.retirement.retain_task(child)
                child.add_done_callback(sibling_harness_done)
            live = len({id(row.scope) for row in programs
                        if hasattr(row, "scope") and row.scope.live})
            sibling_overlap[0] = max(sibling_overlap[0], live)

    async def observe_sibling_scope(controller):
        try:
            while not controller.owner_held.is_set():
                await controller.observer_wake.wait()
                if actor.retirement.requested.is_set():
                    return
                if controller.public_task is not None and not controller._observed_fault():
                    return  # Actual ordinary close, no fixture barrier.
                controller.observer_wake.clear()
            assert not caller.done() and controller.scope.live
            assert sibling_overlap[0] == 2
            controller.checkpoint_owner(rows=_rows(config))
            controller.owner_release.set()
            while not controller.env_held.is_set():
                controller.observer_wake.clear()
                if actor.retirement.requested.is_set():
                    return
                await controller.observer_wake.wait()
            assert not caller.done()
            controller.checkpoint_env(rows=_rows(config))
            controller.env_release.set()
        finally:
            controller.release()  # Release gates only; never fabricate a checkpoint.

    async def observed_settle(task):
        if sibling_controller:
            return await sibling_controller[0].settle_cleanup(task, original_settle)
        if timeout_case:
            selected = [controller for controller in timeout_controllers
                        if task is controller.scope.cleanup_task]
            if selected:
                controller, = selected
                return await controller.settle_cleanup(task, original_settle)
        if invalid_controller:
            return await invalid_controller[0].settle_cleanup(task, original_settle)
        return await original_settle(task)

    if invalid_case or timeout_case or sibling_case:
        # Verify the ORIGINAL method seal first. Free _settle is not sealed.
        api._check_hooks()
        assert all(original is not original_settle for _, _, original in api._HOOKS)
        patch.setattr(api, "_settle", observed_settle)
    if sibling_case:
        observed_scope_check.__wrapped__ = original_scope_check
        patch.setattr(api._Scope, "check", observed_scope_check)

    def observed_cleanup_task(coroutine, *args, **kwargs):
        # Identify ORIGINAL coroutines by code only, never frames or closures.
        code = getattr(coroutine, "cr_code", None)
        kind = ("resource-close" if code is api._close_resource.__code__ else
                "scope-drain" if code is api._drain_scope.__code__ else None)
        actual = original_create_task(coroutine, *args, **kwargs)
        if kind is not None:
            actor.retirement.retain_cleanup(actual, kind)  # Before yielding.
        return actual

    patch.setattr(asyncio, "create_task", observed_cleanup_task)

    async def observe_timeout_scope(record):
        controller = record.timeout
        scope = record.scope
        await controller.observer_wake.wait()
        if not controller.owner_held.is_set():
            assert actor.retirement.requested.is_set()
            return  # Retirement woke an unentered hold, not an observed checkpoint.
        assert controller.receipt.intent is record.actual._intent
        assert controller.request_task is scope.task_score
        assert not caller.done() and scope.live and scope.result is None
        if mutant == "timeout-early-public-release" and scope.data is public_data[0]:
            controller.owner_release.set()
            ack = await controller.public_task  # ORIGINAL public close BEFORE checkpoint.
            assert ack is record.actual._authority.ack and ack.not_started
            timeout_early_hits[0] += 1
        facts = controller.checkpoint(rows=_rows(config))
        if scope.data is not public_data[0] or mutant == "none":
            assert facts == dict(
                public_pending=True, public_uncancelled=True, score_pending=True,
                agent_pending=True, timeout_reported=False, target_writer=False, target_rewards=0)
        else:
            assert facts["public_pending"] is False and facts["public_uncancelled"] is True
        controller.owner_release.set()
        await controller.env_held.wait()
        assert not caller.done() and scope.live and scope.token is not None
        assert not scope.authority and not controller.env_task.done()
        assert scope.cleanup_task.done() and scope.cleanup_task.exception() is None
        assert all(task.done() and not task.cancelled() and task.exception() is None
                   and task.result() is None for _, task in scope.closes._entries)
        assert not any(trace["id"] == scope.trace.id
                       for row in _rows(config) for trace in row["traces"])
        controller.env_release.set()

    if timeout_case:
        actor.retirement.timeout_diagnostic_refs = (
            ("_sdk_timeout_completed", _sdk_timeout_completed.__code__),
            ("_SdkScoringTimeout._check_scope", _SdkScoringTimeout._check_scope.__code__),
            ("_sdk_timeout_qualification", _sdk_timeout_qualification.__code__),
            ("_sdk_acceptance", _sdk_acceptance.__code__),
            ("_run_sdk_host_case", _run_sdk_host_case.__code__),
            ("_sdk_acceptance.observe_timeout_scope", observe_timeout_scope.__code__),
        )

    def observed_request_cancel(actual, reason):
        if sibling_case:
            import sys
            frame = sys._getframe(1)
            if sibling_controller and actual is sibling_controller[0].owner:
                return sibling_controller[0].request_cancel(
                    actual, reason, original_request_cancel,
                    caller_code=frame.f_code, caller_line=frame.f_lineno,
                    caller_task=asyncio.current_task())
            return original_request_cancel(actual, reason)
        record = next((row for row in owners if row.actual is actual), None)
        if record is None:
            return original_request_cancel(actual, reason)
        return record.timeout.request_cancel(
            actual, reason, original_request_cancel, record.controller_gate.set)

    def observed_error(trace, error):
        selected = [controller for controller in timeout_controllers
                    if controller.scope.trace is trace]
        if not selected:
            return original_record_error(trace, error)
        controller, = selected
        return controller.record_error(trace, error, original_record_error)
    cancellation = None
    if cancel_case:
        from ptc.test_owned_sql_sdk_program_cancellation import _SdkProgramCancellation
        cancellation = _SdkProgramCancellation(
            api=api, core=core, actor=actor, profile=profile, executor=executor,
            owners=owners, closes=closes, programs=programs, scorers=scorers,
            rewards=rewards, results=results, sdk_tasks=sdk_tasks,
            controller_gates=controller_gates,
            role="scorer" if cancel_scorer else "program")
        cancellation.install(patch)

    def aliases(module, original, replacement):
        for name, value in tuple(vars(module).items()):
            if value is original:
                patch.setattr(module, name, replacement)

    def observed_load(*args, **kwargs):
        call = inspect.signature(original_load).bind(*args, **kwargs)
        actual = original_load(*args, **kwargs)
        load_calls.append(dict(call.arguments))
        loads.append(actual)
        return actual

    def observed_init(actual, *args, **kwargs):
        with actor.spawn_lock:
            assert not actor.stopping.is_set()
            actor.owners.append(actual)  # BEFORE any canonical allocation.
            sibling_retained = False
            if sibling_case and sibling_controller and api._rollout.get() is sibling_controller[0].scope:
                sibling_controller[0].retain_owner(actual)
                sibling_retained = True
            original_init(actual, *args, **kwargs)
            original_start = actual._start
            actor.fence_owned_start(actual, actor.spawn_lock, actor.stopping)
            fenced_start = actual._start

            def start_or_join():
                # execute()/aclose() re-enter _start after cancellation. The
                # original first branch is a no-op for these retained states.
                # Hold its actual RLock through that original branch so this
                # can NEVER become a new dispatch outside the startup fence.
                with actual._lock:
                    if (actual._thread is not None or actual._completion is not None
                            or actual._incomplete):
                        return original_start()
                return fenced_start()

            actual._start = start_or_join
            if not sibling_retained:
                if not cancel_release_events:
                    event = threading.Event()
                    actor.gates.append(event)
                    cancel_release_events.append(event)
                actual._sdk_cancel_release_event = cancel_release_events[0]

    def observed_task_init(actual, *args, **kwargs):
        original_task_init(actual, *args, **kwargs)
        sdk_tasks.append(actual)  # Delegating constructor, no lifecycle rewrite.

    def observed_allocate(actual_executor, prediction, task, **kwargs):
        assert not cancel_program, "SDK_CANCEL_UNEXPECTED_SCORER_INVOCATION"
        assert actual_executor is executor
        scorer = score_tasks[asyncio.current_task()]
        expected_prediction = ("fixture-score-status:" + invalid_status
                               if invalid_case and scorer.scope.data is public_data[0]
                               else PREDICTION)
        assert prediction == expected_prediction
        if invalid_case or timeout_case or sibling_case:
            scope = api._rollout.get()
            assert scope is scorer.scope and scope.task_score is scorer.score_task
            assert asyncio.current_task() is scorer.score_task
            assert scope.scorer is scorer.actual and scope.private is task
            assert scorer.kwargs["task"] is task
            assert kwargs["instrument"] is scorer.kwargs["instrument"] is instrument
            assert scope.trace.last_reply == expected_prediction and not program_calls
        if cancel_scorer:
            scope = api._rollout.get()  # Exact requesting scope, READ ONLY.
            assert len(owners) < 2 and any(scope is target for target in target_scope)
            assert scope is scorer.scope and scope.task_score is scorer.score_task
            assert asyncio.current_task() is scorer.score_task
            assert scope.scorer is scorer.actual and scope.private is task
            assert scorer.kwargs["task"] is task and scorer.kwargs["executor"] is actual_executor
            assert kwargs["instrument"] is scorer.kwargs["instrument"] is instrument
            assert scope.trace.last_reply == PREDICTION
            assert not program_calls
        actual = original_allocate(actual_executor, prediction, task, **kwargs)
        assert actor.owners[-1] is actual
        assert type(actual) is core.OwnedSqlInvocation and actual.role == "scorer"
        position, = [index for index, private in enumerate(admitted.eligible)
                     if private is task]
        sdk_task, = [actual_task for actual_task in sdk_tasks
                     if actual_task.data is public_data[position]]
        record = SimpleNamespace(
            actual=actual, task=task, kwargs=kwargs, prediction=prediction,
            scorer=scorer, sdk_task=sdk_task)
        if cancel_scorer or invalid_case or timeout_case or sibling_case:
            assert sdk_task is scope.task and sdk_task.data is scope.data
            record.scope = scope
        return retain_owner(record)

    def observed_allocate_program(actual_executor, code, **kwargs):
        assert program_case and actual_executor is executor and code == PROGRAM_CODE
        scope = api._rollout.get()  # Original requesting scope, READ ONLY.
        call, = [call for call in program_calls if call.scope is scope
                 and call.owner is None]
        assert scope.program is call.program.harness
        if cancel_program:
            assert len(owners) < 2 and any(scope is target for target in target_scope)
        else:
            assert target_scope == [scope]
        actual = original_allocate_program(actual_executor, code, **kwargs)
        call.owner = actual  # Original allocation retained before first await.
        assert actor.owners[-1] is actual and actual.role == "program"
        return retain_owner(SimpleNamespace(
            actual=actual, task=scope.private, kwargs=kwargs, prediction=None,
            scorer=None, sdk_task=scope.task, scope=scope))

    def retain_owner(record):
        actual = record.actual
        index = len(owners)
        owners.append(record)
        if not timeout_case and sibling_case and sibling_controller and record.scope is sibling_controller[0].scope:
            controller = sibling_controller[0]
            record.controller_gate = controller.controller_gate
            controller_gates.append(controller.controller_gate)
            controller.bind_owner(record)
            sibling_queue.append(record)
            release_sibling_dispatch()
            return actual
        gate = threading.Event()
        if timeout_case:
            record.controller_gate = gate
            record.timeout = _SdkScoringTimeout(
                api=api, retirement=actor.retirement, scope=record.scope, owner=actual)
            timeout_controllers.append(record.timeout)
            observer = loop.create_task(observe_timeout_scope(record))
            actor.retirement.retain_task(observer)
            timeout_drivers.append(observer)
        controller_gates.append(gate)
        with actor.spawn_lock:
            assert not actor.stopping.is_set()
            actor.gates.append(gate)
        controller = actual._controller

        def held_controller(binding):
            # Retain the actual controller/thread BEFORE original admission.
            # Do not bypass/replace the profile lock: one actual dispatch at
            # a time, released only after the preceding public close ACK.
            actor.emit("SDK_CONTROLLER_HELD", index=index)
            admitted = gate.wait(max(0, actor.end - 3.75 - time.monotonic()))
            if not admitted:
                try:
                    assert admitted, "SDK_CONTROLLER_PRE_ADMISSION_DEADLINE"
                except AssertionError as error:
                    actor.retirement.fail("controller-gate", error)
                    event = getattr(actual, "_sdk_cancel_release_event", None)
                    if event is None:
                        raise
                    notified = event.wait(max(
                        0, actor.retirement.deadline - time.monotonic()))
                    if (not notified or not actor.stopping.is_set()
                            or time.monotonic() >= actor.retirement.deadline):
                        raise
                    intent = actual.snapshot().intent
                    if (type(intent) is not core.CancelIntent
                            or time.monotonic_ns() >= intent.deadline_ns):
                        raise
                    if not any(
                            retained is actual and type(receipt) is core.CancelReceipt
                            and receipt.status in ("accepted", "repeated")
                            and receipt.intent is intent
                            for retained, receipt in actor.retirement.cancel_receipts):
                        raise
                    # Validation itself may consume the last absolute budget.
                    if (time.monotonic() >= actor.retirement.deadline
                            or time.monotonic_ns() >= intent.deadline_ns):
                        raise
                    return controller(binding)
            if actor.stopping.is_set():
                # Retirement first delivers the REAL public cancellation.
                # Delegate to the original controller's pre-admission branch,
                # rather than silently returning with no candidate forever.
                intent = actual.snapshot().intent
                if probe is not None:
                    probe.released.append((
                        actual, intent, tuple(actor.retirement.cancel_receipts)))
                assert intent is not None
            return controller(binding)

        actual._controller = held_controller
        if not timeout_case and sibling_case:
            record.controller_gate = gate
            sibling_queue.append(record)
            release_sibling_dispatch()
            return actual
        if (not timeout_case and cancellation is None and probe is None
                and released_first[0] and dispatch_turn[0] == index):
            gate.set()
            try:
                _timeline = getattr(actor, "_sdk_timeline", None)
                if _timeline is not None:
                    _timeline.note(4, actual, owners)
            except BaseException:
                pass
        return actual

    async def observed_close(actual):
        actor.retirement.retain_cleanup(asyncio.current_task(), "owner-close")
        record = SimpleNamespace(actual=actual, task=asyncio.current_task(), ack=None)
        closes.append(record)
        if sibling_case:
            controller = sibling_controller[0] if sibling_controller else None
            ack = (await controller.close_owner(actual, original_close)
                   if controller is not None and actual is controller.owner
                   else await original_close(actual))
            record.ack = ack
            assert ack is actual._completion.cleanup_ack is actual._authority.ack
            if sibling_active[0] is not None and sibling_active[0].actual is actual:
                sibling_active[0] = None
            release_sibling_dispatch()
            return ack
        if cancellation is not None:
            return await cancellation.close_owner(actual, record, original_close)
        if timeout_case:
            retained, = [row for row in owners if row.actual is actual]
            ack = await retained.timeout.close_owner(actual, original_close)
            record.ack = ack
            assert ack is actual._completion.cleanup_ack is actual._authority.ack
            assert ack.not_started and ack._authority.owner is actual
            return ack
        target = next((row for row in owners if row.actual is actual
                       and invalid_case and row.sdk_task.data is public_data[0]), None)
        if target is not None:
            assert not invalid_controller and target.scope is target_scope[0]
            result = actual._completion.outcome.result  # Actual decoded native object.
            assert type(result) is ExResult and target.scope.result is None
            controller = _SdkInvalidStatus(
                api=api, retirement=actor.retirement, status=invalid_status,
                scope=target.scope, owner=actual, result=result)
            invalid_controller.append(controller)
            actor.retirement.invalid_controller = controller
            actor.emit("SDK_INVALID_OWNER_BOUND")
            ack = await controller.close_owner(actual, original_close)
        else:
            ack = await original_close(actual)
        record.ack = ack
        assert actual._completion.cleanup_ack is actual._authority.ack is ack
        try:
            _timeline = getattr(actor, "_sdk_timeline", None)
            if _timeline is not None:
                _timeline.note(5, actual, owners)
        except BaseException:
            pass
        if not actor.stopping.is_set() and not actor.retirement.requested.is_set():
            if probe is None or not actor.retirement.requested.is_set():
                assert owners[dispatch_turn[0]].actual is actual
                dispatch_turn[0] += 1
            # Fault cases release remaining controllers ONLY after real public
            # cancellation, never as an ACK observer side effect.
            if probe is None and dispatch_turn[0] < len(controller_gates):
                controller_gates[dispatch_turn[0]].set()
                try:
                    _timeline = getattr(actor, "_sdk_timeline", None)
                    if _timeline is not None:
                        _timeline.note(6, owners[dispatch_turn[0]].actual, owners)
                except BaseException:
                    pass
        return ack

    def observed_program(*args, **kwargs):
        actual = original_program(*args, **kwargs)
        call = inspect.signature(original_program).bind(*args, **kwargs)
        assert type(actual) is PTCHarness
        assert type(call.arguments["config"]) is PTCHarnessConfig
        record = SimpleNamespace(
            harness=actual, kwargs=dict(call.arguments), runners=[],
            validations=[], closes=[])
        programs.append(record)
        factory = actual.program_runner_factory

        def observed_factory(data, compiled):
            runner = factory(data, compiled)
            record.runners.append(runner)
            if program_case or cancel_scorer or invalid_case or timeout_case or sibling_case:
                from contextvars import copy_context
                scope = api._rollout.get()  # Never set/reset fixture context.
                assert scope is not None and scope.program is actual
                assert scope.private is record.kwargs["task"]
                assert scope.data is data is scope.task.data is scope.trace.task.data
                record.scope, record.context = scope, copy_context()
                if cancel_case:
                    record.token = scope.token
                assert record.context.get(api._rollout) is scope
            validate, close = runner.validate_program_timeout, runner.aclose
            run = runner.run_program

            async def observed_run(code, *, timeout):
                assert not invalid_case, "SDK_INVALID_UNEXPECTED_PROGRAM_INVOCATION"
                assert not timeout_case, "SDK_TIMEOUT_UNEXPECTED_PROGRAM_INVOCATION"
                assert not sibling_case, "SDK_SIBLING_UNEXPECTED_PROGRAM_INVOCATION"
                scope = api._rollout.get()
                assert scope is record.scope and record.context.get(api._rollout) is scope
                call = SimpleNamespace(
                    scope=scope, program=record, runner=runner, code=code,
                    tool_call_id=None, owner=None, observation=None)
                program_calls.append(call)
                observation = await run(code, timeout=timeout)
                call.observation = observation
                assert call.owner is not None and call.owner.role == "program"
                if observation == PROGRAM_SENTINEL:
                    sentinel_hits[0] += 1  # Actual delegated decoder return only.
                return observation  # SAME original object, never synthesize.

            def observed_validate(timeout):
                record.validations.append((runner, timeout))
                return validate(timeout)

            async def observed_runner_close():
                actor.retirement.retain_cleanup(asyncio.current_task(), "resource-close")
                record.closes.append((runner, asyncio.current_task()))
                if cancellation is not None:
                    cancellation.resource_body("runner", record)
                return await close()

            patch.setattr(runner, "validate_program_timeout", observed_validate)
            patch.setattr(runner, "aclose", observed_runner_close)
            if program_case or cancel_scorer or invalid_case or timeout_case or sibling_case:
                patch.setattr(runner, "run_program", observed_run)
            return runner

        patch.setattr(actual, "program_runner_factory", observed_factory)
        return actual

    def observed_scorer(*args, **kwargs):
        actual = original_scorer(*args, **kwargs)
        assert type(actual) is sql_owned_score.OwnedSqlScorer
        call = inspect.signature(original_scorer).bind(*args, **kwargs)
        scorers.append(SimpleNamespace(
            actual=actual, kwargs=dict(call.arguments), closes=[], result=None))
        return actual

    def scorer_record(actual):
        record, = [record for record in scorers if record.actual is actual]
        return record

    async def observed_score(actual, prediction):
        record = scorer_record(actual)
        current = asyncio.current_task()
        assert current not in score_tasks and record.result is None
        score_tasks[current] = record
        if cancel_scorer or invalid_case or timeout_case or sibling_case:
            scope = api._rollout.get()  # Observe original Task.score before await.
            assert scope is not None and scope.task_score is current
            assert scope.scorer is actual and record.kwargs["task"] is scope.private
            assert scope.task.data is scope.data is scope.trace.task.data
            record.scope, record.score_task, record.cancel_error = scope, current, None
            actor.retirement.retain_task(current)
            if cancellation is not None:
                cancellation.retained.add(current)
            if sibling_case and scope.data is public_data[0]:
                assert not sibling_controller
                controller = _SdkSiblingScoreFailure(
                    api=api, actor=actor, scope=scope, target_data=public_data[0],
                    omit_fault=mutant == "omit-sibling-fault")
                sibling_controller.append(controller)
                observer = loop.create_task(observe_sibling_scope(controller))
                actor.retirement.retain_task(observer)
                sibling_observers.append(observer)
        try:
            result = await original_score(actual, prediction)  # REAL decoder/owner.
        except asyncio.CancelledError as exc:
            if sibling_case:
                record.cancel_error = exc
                if sibling_controller and record.scope is sibling_controller[0].scope:
                    sibling_controller[0].score_cancelled(record.scope, current, exc)
            if timeout_case:
                record.cancel_error = exc
                retained, = [row for row in owners if row.scorer is record]
                retained.timeout.score_cancelled(record.scope, current, exc)
            if cancel_scorer:
                record.cancel_error = exc  # Actual callback exception, not a substitute.
                cancellation.progress()
            raise
        record.result = result
        results.append(result)
        if invalid_case and record.scope.data is public_data[0]:
            assert invalid_controller[0].result is result
            if mutant == "invalid-target-zero":
                assert result.status == "mismatch" and result.valid is True and result.score == 0.0
                invalid_hits[0] += 1  # Original decoder return, never wire intent.
        if probe is not None:
            actor.emit("SDK_RESULT_RETURNED")
        return result

    async def observed_scorer_close(actual):
        actor.retirement.retain_cleanup(asyncio.current_task(), "resource-close")
        record = scorer_record(actual)
        record.closes.append(asyncio.current_task())
        if cancellation is not None:
            cancellation.resource_body("scorer", record)
        return await original_scorer_close(actual)

    def observed_reward(trace, name, score, *args, **kwargs):
        if timeout_case:
            rewards.append((None, trace, None))  # Record AND delegate any unexpected reward.
            return original_reward(trace, name, score, *args, **kwargs)
        assert not actor.retirement.requested.is_set(), "SDK_PUBLICATION_RETIRED"
        record = score_tasks[asyncio.current_task()]
        owner_record, = [row for row in owners if row.scorer is record]
        actual = owner_record.actual
        assert trace.task.data is owner_record.sdk_task.data
        close, = [item for item in closes if item.actual is actual]
        assert close.ack is actual._completion.cleanup_ack is actual._authority.ack
        assert record.result is actual._completion.outcome.result
        assert len(record.closes) == 1
        assert not actual._thread.is_alive() and close.ack.completed_ns <= time.monotonic_ns()
        rewards.append((actual, trace, record))
        if invalid_case and trace.task.data is public_data[0]:
            invalid_target_rewards.append((name, score))
            return original_reward(trace, name, score, *args, **kwargs)
        assert name == "execution_accuracy" and score == 1.0
        value = original_reward(trace, name, score, *args, **kwargs)
        if probe is not None:
            actor.emit("SDK_REWARD_RECORDED")
        return value

    def observed_admit(actual_executor, **kwargs):
        identity = original_admit(actual_executor, **kwargs)
        admissions.append((actual_executor, dict(kwargs), identity))
        return identity

    try:
        if sibling_case:
            observed_request_cancel.__wrapped__ = original_request_cancel
            observed_close.__wrapped__ = original_close
        for cls, name, replacement in (
            (core.OwnedSqlInvocation, "__init__", observed_init),
            (core.OwnedSqlInvocation, "aclose", observed_close),
            (core.PilotExecutor, "owned_score", observed_allocate),
            (core.PilotExecutor, "admit_program", observed_admit),
            (sql_owned_score.OwnedSqlScorer, "score_sql", observed_score),
            (sql_owned_score.OwnedSqlScorer, "aclose", observed_scorer_close),
            (Trace, "record_reward", observed_reward),
            (api.OwnedSqlTask, "__init__", observed_task_init),
        ):
            patch.setattr(cls, name, replacement)
        for module, original, replacement in (
            (prepare, original_load, observed_load),
            (sql_owned_program, original_program, observed_program),
            (sql_owned_score, original_scorer, observed_scorer),
        ):
            aliases(module, original, replacement)
            aliases(api, original, replacement)
        if timeout_case or sibling_case:
            patch.setattr(core.OwnedSqlInvocation, "request_cancel", observed_request_cancel)
        if timeout_case:
            patch.setattr(Trace, "record_error", observed_error)
        if program_case or cancel_scorer or invalid_case or timeout_case or sibling_case:
            patch.setattr(core.PilotExecutor, "owned_program", observed_allocate_program)
        assert loaders.harness_class(ID) is api.OwnedSqlHarness
        assert loaders.taskset_class(ID) is api.OwnedSqlTaskset
        assert loaders.environment_class(ID, ID) is api.OwnedSqlEnv
        # An independent metadata load supplies public Data/settings only.
        # Builder must perform its own original load with retained parent pins.
        known = original_load(
            root=corpus, draw_path=draw, supplement_path=supplement,
            expected_draw_sha256=draw_sha,
            expected_supplement_sha256=supplement_sha, fixture=True)
        public_data = tuple(TaskData(name=task.name, prompt=task.question)
                            for task in known.eligible)
        instrument = InstrumentSettings(
            action_cap=2, action_max_rows=3, scorer_max_rows=known.max_rows,
            compare=known.comparison, scorer_timeout_s=known.timeout_s,
            program_timeout_s=5.0, wrapper_timeout_s=1.25,
            python_version="fixture-python", sqlite_version="fixture-sqlite",
            source_paths=("ptc/sql_isolation.py",), source_sha256="a" * 64)
        config = _config(root, api, instrument, rollouts)
        if timeout_case:
            config = _SdkScoringTimeout.configure(
                config, draw=known, public_data=public_data, instrument=instrument)
        if program_case or cancel_scorer or invalid_case or sibling_case:
            config.num_tasks = 7
            assert (config.num_tasks, config.num_rollouts, config.shuffle,
                    config.max_concurrent) == (7, 1, False, 2)
        state.config = config
        policy_hold = asyncio.Event()

        async def hold_later_policy(number):
            if number > 2:
                await policy_hold.wait()  # Original SDK cancellation retires it.

        program_step = _program_call(PROGRAM_CODE) if program_case else None

        async def observe_program_policy(number):
            body = policy.bodies[-1]
            prompt, = [message["content"] for message in body["messages"]
                       if message.get("role") == "user"]
            record, = [record for record in programs
                       if record.kwargs["data"].prompt == prompt]
            scope = record.scope
            policy_scopes.append((body, scope))
            if invalid_case:
                assert scope.data is record.kwargs["data"] is scope.task.data
                if scope.data is public_data[0]:
                    assert not target_scope
                    target_scope.append(scope)  # Exact admitted Data, not request ordinal.
                    policy.steps[number-1] = _text_step("fixture-score-status:" + invalid_status)
            elif timeout_case or sibling_case:
                assert scope.data is record.kwargs["data"] is scope.task.data
            elif cancel_case:
                assert number <= 2, "SDK_CANCEL_UNEXPECTED_THIRD_POLICY_REQUEST"
                target_scope.append(scope)
            elif number == 1:
                target_scope.append(scope)  # First actual request, never later ordinal.

        state.policy = policy = ScriptedClient(
            ([_program_call(PROGRAM_CODE, "call_cancel_program_1"),
              _program_call(PROGRAM_CODE, "call_cancel_program_2")] if cancel_program else
             [program_step] if program_case else [])
            + [_text_step(PREDICTION) for _ in range(expected)],
            on_call=(observe_program_policy if program_case or cancel_scorer or invalid_case or timeout_case or sibling_case else
                     hold_later_policy if probe is not None else None))
        binding = api.build_registered_owned_sql_binding(
            draw=api.OwnedSqlDrawInput(
                root=corpus, draw_path=draw, supplement_path=supplement,
                expected_draw_sha256=draw_sha,
                expected_supplement_sha256=supplement_sha, fixture=True),
            executor=executor, instrument=instrument, public_data=public_data)
        admitted, = loads
        call, = load_calls
        assert call == dict(
            root=corpus, draw_path=draw, supplement_path=supplement,
            expected_draw_sha256=draw_sha,
            expected_supplement_sha256=supplement_sha, fixture=True)
        assert admitted is not known and admitted == known
        assert (len(admitted.planned), len(admitted.eligible),
                len(admitted.exclusions), len(admitted.databases)) == (8, 7, 1, 2)
        assert "excluded-only" in {db.db_id for db in admitted.databases}
        if probe is not None:
            probe.bind(config=config, known=admitted, state=state,
                       owners=owners, closes=closes, results=results,
                       programs=programs, scorers=scorers, rewards=rewards)
        if phase == "sdk-retire-partial-setup":
            import httpx
            from verifiers.v1 import env as env_mod, rollout as rollout_mod

            # Actual first-party seams and constructor observers, not classes
            # or fake resources. Deliberately no registered Agent/eval yet.
            probe.server = env_mod.make_interception(
                config.env.interception, requires_tunnel=False)
            await probe.server.start()
            assert probe.server.runner.sites
            probe.runtime = rollout_mod.make_runtime(config.env.agent.runtime)
            await probe.runtime.start()
            probe.client = httpx.AsyncClient(timeout=actor.retirement.remaining())
            response = await probe.client.get(
                probe.server.base_url + "/__retirement_physical_probe__")
            probe.http_status = response.status_code
            assert probe.http_status == 404 and not probe.client.is_closed
            assert probe.client._transport._pool.connections
            # The original runtime.write submits real SDK filesystem work to
            # the original loop's actual default executor, with no subprocess.
            await probe.runtime.write("retirement-physical-probe", b"retirement only\n")
            await probe.observe_live_executor()
            probe.checkpoint()
            probe.inject()
        caller = loop.create_task(api.run_registered_owned_sql_eval(
            config, binding=binding))
        actor.retirement.retain_driver(caller)
        if sibling_case:
            episodes = await caller
            await asyncio.gather(*sibling_observers)
            controller, = sibling_controller
            for slot in actor.slots:
                if not any(item["kind"] == "EVIDENCE" for item in slot["messages"]):
                    await actor.next_event(
                        lambda item: item["kind"] == "EVIDENCE"
                        and item["invocation_id"] == slot["invocation_id"])
            assert retained_documents == (draw.read_bytes(), supplement.read_bytes())
            bundle = SimpleNamespace(
                actor=actor, api=api, config=config, admitted=admitted, public_data=public_data,
                sdk_tasks=sdk_tasks, owners=owners, closes=closes, programs=programs, scorers=scorers,
                results=results, rewards=rewards, program_calls=program_calls, policy=policy,
                policy_scopes=policy_scopes, episodes=episodes, state=state, instrument=instrument,
                executor=executor, profile=profile, admissions=admissions, controller=controller,
                hooks=controller.hooks, codes=controller.codes, retained_documents=retained_documents,
                checkpoint=dict(overlap=sibling_overlap[0]))
            return _sdk_sibling_completed(bundle)
        if timeout_case:
            episodes = await caller  # No first-two live-controller/positive-phase assumption.
            await asyncio.gather(*timeout_drivers)
            bundle = SimpleNamespace(
                actor=actor, api=api, config=config, admitted=admitted, public_data=public_data,
                sdk_tasks=sdk_tasks, owners=owners, closes=closes, programs=programs,
                scorers=scorers, results=results, rewards=rewards, program_calls=program_calls,
                policy=policy, policy_scopes=policy_scopes, episodes=episodes, state=state,
                instrument=instrument, executor=executor, profile=profile, admissions=admissions,
                controllers=timeout_controllers, drivers=timeout_drivers,
                early_hits=timeout_early_hits[0], mutant=mutant)
            assert retained_documents == (draw.read_bytes(), supplement.read_bytes())
            return _sdk_timeout_completed(bundle)
        for _ in range(2):
            item = await actor.next_event(
                lambda item: item["kind"] == "SDK_CONTROLLER_HELD")
            entered.append(item["index"])
        assert sorted(entered) == [0, 1] and len(owners) == 2
        first, second = owners
        assert (first.task is second.task) is (rollouts == 2)
        assert (first.sdk_task is second.sdk_task) is (rollouts == 2)
        if not cancel_program:
            assert first.scorer is not second.scorer
        assert all(row.actual._thread.is_alive() for row in owners)
        assert not actor.slots and not actor.trace.fence()
        assert not caller.done() and _rows(config) == []
        if cancellation is not None:
            return await cancellation.qualify(
                caller=caller, config=config, admitted=admitted,
                public_data=public_data, policy=policy, instrument=instrument,
                state=state, entered=entered, read_rows=lambda: _rows(config),
                documents=((draw, retained_documents[0]),
                           (supplement, retained_documents[1])),
                program_calls=program_calls)
        if probe is not None:
            await probe.observe_live_executor()
            probe.checkpoint()
            if phase == "sdk-retire-overlap":
                probe.inject()
            if phase == "sdk-retire-framework-finalizer":
                from ptc.test_owned_sql_sdk_retirement_physical import _SdkRetirementCheckpoint
                return _SdkRetirementCheckpoint()
            if phase == "sdk-retire-watchdog-race":
                actor.watchdog_race.signal(probe)
                # The ACTUAL existing supervisor supplies the primary fault.
                # Its shared retirement cancels this real bridge/SDK driver.
                await asyncio.Event().wait()
        released_first[0] = True
        controller_gates[0].set()
        try:
            _timeline = getattr(actor, "_sdk_timeline", None)
            if _timeline is not None:
                _timeline.note(3, owners[0].actual, owners)
        except BaseException:
            pass
        if invalid_case:
            await actor.next_event(lambda item: item["kind"] == "SDK_INVALID_OWNER_BOUND")
            controller, = invalid_controller
            await controller.owner_held.wait()
            scope = controller.scope
            assert scope is target_scope[0] and scope.data is public_data[0]
            assert scope.task_score in actor.retirement.tasks and not scope.task_score.done()
            public, = [row.task for row in closes if row.actual is controller.owner]
            assert public in actor.retirement.tasks and not public.done()
            assert public is controller.public_task and scope.result is None
            assert controller.owner._completion.outcome.result is controller.result
            assert scope.live and scope.cleanup_task is None
            assert not scope.trace.rewards and not invalid_target_rewards
            assert not any(trace["id"] == scope.trace.id
                           for row in _rows(config) for trace in row["traces"])
            assert not scope.agent_task.done() and not caller.done()
            invalid_barriers["owner"] = True
            controller.owner_release.set()
            await controller.env_held.wait()
            assert scope.live and scope.token is not None and not scope.authority
            assert controller.env_task in actor.retirement.tasks and not controller.env_task.done()
            assert scope.cleanup_task.done() and scope.cleanup_task in actor.retirement.tasks
            assert scope.task_score.done() and scope.harness_score.done() and scope.agent_task.done()
            assert all(task is not None and task.done() and not task.cancelled()
                       and task.exception() is None and task.result() is None
                       for _, task in scope.closes._entries)
            assert len(scope.closes._entries) == 2 and not caller.done()
            if mutant == "none":
                assert not scope.trace.rewards and not invalid_target_rewards
                assert controller.settled_error is scope.cleanup_task.exception()
            else:
                assert controller.settled_error is None and controller.settled_result is None
            assert not any(trace["id"] == scope.trace.id
                           for row in _rows(config) for trace in row["traces"])
            invalid_barriers["env"] = True
            controller.env_release.set()
        if phase in ("sdk-retire-post-actor", "sdk-retire-two-slot-verification"):
            async def joined_actor(count):
                while len(results) < count:
                    await actor.next_event(lambda item: item["kind"] == "SDK_RESULT_RETURNED")
                while len(rewards) < count:
                    await actor.next_event(lambda item: item["kind"] == "SDK_REWARD_RECORDED")
                assert len(results) == len(closes) == len(actor.slots) == len(rewards) == count
                for row in owners[:count]:
                    close, = [item for item in closes if item.actual is row.actual]
                    assert close.ack is row.actual._completion.cleanup_ack
                    assert any(result is row.scorer.result for result in results)
                    assert any(actual is row.actual for actual, _, _ in rewards)
                    slot, = [item for item in actor.slots if item["invocation"] is row.actual]
                    if not any(item["kind"] == "EVIDENCE" for item in slot["messages"]):
                        await actor.next_event(
                            lambda item: item["kind"] == "EVIDENCE"
                            and item["invocation_id"] == slot["invocation_id"])

            await joined_actor(1)
            assert not controller_gates[1].is_set() and second.actual._thread.is_alive()
            assert not caller.done() and not actor.retirement.requested.is_set()
            if phase == "sdk-retire-post-actor":
                probe.inject()
            controller_gates[1].set()  # First actual ACK/reward preceded this release.
            await joined_actor(2)
            assert len(owners) == 2 and not caller.done() and actor.retirement.primary is None
            from ptc.test_owned_sql_sdk_retirement_physical import _SdkRetirementCheckpoint
            return _SdkRetirementCheckpoint()
        episodes = await caller
        assert len(episodes) == len(programs) == len(scorers) == expected
        assert len(owners) == len(closes) == len(actor.owners) == expected_owners
        normal_rewards = [item for item in rewards if not invalid_case
                          or item[1].task.data is not public_data[0]]
        assert len(results) == expected and len(normal_rewards) == expected - int(invalid_case)
        assert Counter(actual.role for actual in actor.owners) == (
            Counter(scorer=expected, program=1) if program_case else Counter(scorer=expected))
        assert dispatch_turn[0] == expected_owners
        assert len({id(row.actual) for row in scorers}) == expected
        assert len(sdk_tasks) == 7 and len({id(task) for task in sdk_tasks}) == 7
        assert all(task.data is data for task, data in zip(
            sdk_tasks, public_data, strict=True))
        assert len({id(value) for value in results}) == expected
        assert policy.calls == len(policy.bodies) == expected_owners
        if not program_case:
            assert all(not any(message.get("role") == "tool" for message in body["messages"])
                       for body in policy.bodies)
        expected_data = [data for data in public_data for _ in range(rollouts)]
        assert all(episode.task.data is data for episode, data in zip(
            episodes, expected_data, strict=True))
        traces = [trace for episode in episodes for trace in episode.traces]
        assert len(traces) == len({id(trace) for trace in traces}) == expected
        assert len({trace.id for trace in traces}) == expected
        normal_traces = [trace for trace in traces if not invalid_case
                         or trace.task.data is not public_data[0]]
        assert {id(trace) for _, trace, _ in normal_rewards} == {id(trace) for trace in normal_traces}
        assert all(episode.ok for episode in episodes
                   if not invalid_case or episode.task.data is not public_data[0])
        assert all(trace.ok and set(trace.rewards) == {"execution_accuracy"}
                   and trace.rewards["execution_accuracy"].score == 1.0 for trace in normal_traces)
        for private, data in zip(admitted.eligible, public_data, strict=True):
            selected_programs = [row for row in programs if row.kwargs["task"] is private]
            selected_scorers = [row for row in scorers if row.kwargs["task"] is private]
            selected_owners = [row for row in owners if row.task is private
                               and row.actual.role == "scorer"]
            assert len(selected_programs) == len(selected_scorers) == len(selected_owners) == rollouts
            db, = [db for db in admitted.databases if db.db_id == private.db_id]
            for row in selected_programs:
                assert row.kwargs["data"] is data
                assert row.kwargs["executor"] is executor
                assert row.kwargs["max_rows"] == instrument.action_max_rows
                assert row.kwargs["db_sha256"] == db.sha256
                assert row.kwargs["config"].id == PTCHarnessConfig().id
                assert row.kwargs["config"].max_turns == instrument.action_cap
                assert row.kwargs["config"].program_timeout == 5.0
                assert len(row.runners) == len(row.validations) == len(row.closes) == 1
                assert row.validations[0] == (row.runners[0], 5.0)
                assert row.closes[0][0] is row.runners[0]
            for row in selected_scorers:
                assert row.kwargs["executor"] is executor and row.kwargs["instrument"] is instrument
                assert row.kwargs["db_sha256"] == db.sha256 and len(row.closes) == 1
                assert type(row.result) is ExResult
                if not invalid_case or data is not public_data[0]:
                    assert row.result.status == "match"
                    assert row.result.valid is True and row.result.score == 1.0
                if invalid_case:
                    assert row.scope.result is row.result and row.scope.data is data
                assert row.result.n_pred_rows == 7 and row.result.n_gold_rows == 11
            for row in selected_owners:
                actual = row.actual
                assert actual.db_path == Path(private.db_path)
                assert actual.request.db_sha256 == db.sha256
                assert actual.request.task.gold_sql == private.gold_sql
                assert actual.request.task.db_path == "/db.sqlite"
                assert actual.request.max_rows == instrument.scorer_max_rows
                completion = actual._completion
                assert completion.abort is None and completion.outcome.abort is None
                ack = completion.cleanup_ack
                if invalid_case:
                    close, = [item for item in closes if item.actual is actual]
                    assert close.ack is ack and row.scorer.result is completion.outcome.result
                    assert row.scope is row.scorer.scope
                assert ack is actual._authority.ack and ack._authority.owner is actual
                assert ack.role == "scorer" and not ack.not_started
                assert ack.child_waits and ack.thread_joins and ack.released
                assert ack.request_sha256 == core.request_sha256(actual.request)
                assert ack.profile_sha256 == core.execution_profile_sha256(profile)
                assert len(ack.guardian_reaps) == 1
                assert not actual._thread.is_alive()
        assert all(row["process"]._creator_waited and not row["process"]._creator_ambiguous
                   for row in actor.trace.fence())
        assert len(actor.trace.fence()) == len(actor.slots) == expected_owners
        for slot in actor.slots:
            evidence = next((item for item in slot["messages"]
                             if item["kind"] == "EVIDENCE"), None)
            if evidence is None:
                evidence = await actor.next_event(
                    lambda item: item["kind"] == "EVIDENCE"
                    and item["invocation_id"] == slot["invocation_id"])
            assert not evidence["forbidden"] and not evidence["hits"] and evidence["released"]
            actual = evidence["actual"]
            assert sum(row["actor"] == "role" for row in actual) == 1
            assert sum(row["actor"] == "cli" for row in actual) >= 2
            assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                       and type(row["returncode"]) is int for row in actual)
        assert len(state.agents) == len(state.runtimes) == expected
        assert not state.external and not state.channels and not actor.forbidden_calls
        for agent, original in state.agents:
            assert agent.harness is original and type(original) is api.OwnedSqlHarness
        assert len(admissions) >= 2 * expected
        assert all(actual_executor is executor for actual_executor, _, _ in admissions)
        rows = _rows(config)
        assert len(list(Path(config.output_dir).rglob("*.jsonl"))) == 1
        assert len(rows) == expected
        assert all(row["ok"] for row in rows if not invalid_case or all(
            trace["id"] != invalid_controller[0].scope.trace.id for trace in row["traces"]))
        assert Counter(row["task"]["hash"] for row in rows) == Counter(
            episode.task.hash for episode in episodes)
        assert {trace["id"] for row in rows for trace in row["traces"]} == {
            trace.id for trace in traces}
        for row in rows:
            trace, = row["traces"]
            assert trace["task"]["data"] == row["task"]["data"]
            assert trace["task"]["hash"] == row["task"]["hash"]
            if not invalid_case or trace["id"] != invalid_controller[0].scope.trace.id:
                assert trace["ok"] and set(trace["rewards"]) == {"execution_accuracy"}
                assert trace["rewards"]["execution_accuracy"]["score"] == 1.0
        public_wire = json.dumps([
            policy.bodies, [row["task"]["data"] for row in rows],
            [trace["task"]["data"] for row in rows for trace in row["traces"]]])
        assert "gold_sql" not in public_wire and "db_path" not in public_wire
        assert all(value not in public_wire for private in admitted.planned
                   for value in (private.gold_sql, private.db_path))
        assert retained_documents == (draw.read_bytes(), supplement.read_bytes())
        if invalid_case:
            controller, = invalid_controller
            invalid_public_wire = json.dumps([policy.bodies, rows])
            assert "gold_sql" not in invalid_public_wire and "db_path" not in invalid_public_wire
            assert all(value not in invalid_public_wire for private in admitted.planned
                       for value in (private.gold_sql, private.db_path))
            assert invalid_barriers == dict(owner=True, env=True) and not program_calls
            assert len(policy_scopes) == 7 and len({id(scope) for _, scope in policy_scopes}) == 7
            assert {id(scope) for _, scope in policy_scopes} == {id(row.scope) for row in programs}
            for row in programs:
                scope = row.scope
                scorer, = [item for item in scorers if item.scope is scope]
                owner, = [item for item in owners if item.scope is scope]
                assert scope.program is row.harness and row.context.get(api._rollout) is scope
                assert scope.task is owner.sdk_task and scope.private is row.kwargs["task"]
                assert scope.trace.task.data is scope.data is row.kwargs["data"]
                assert any(trace is scope.trace for trace in traces)
                assert not scope.live and not scope.authority and scope.token is None
                assert scope.result is scorer.result is owner.actual._completion.outcome.result
                for task in (scope.task_score, scope.harness_score, scope.agent_task):
                    assert isinstance(task, asyncio.Task) and task.done() and not task.cancelled()
                    actor.retirement.retain_task(task)
                assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
                assert scope.cleanup_task in actor.retirement.tasks
                assert len(scope.closes._entries) == 2
                resource_tasks = [task for _, task in scope.closes._entries]
                assert any(task is scorer.closes[0] for task in resource_tasks)
                assert any(task is row.closes[0][1] for task in resource_tasks)
                assert len({id(task) for task in resource_tasks}) == 2
                assert all(task in actor.retirement.tasks and task.done()
                           and not task.cancelled() and task.exception() is None
                           and task.result() is None for task in resource_tasks)
            checkpoint = dict(
                decision="invalid-observed", status=invalid_status, scopes=7,
                planned_tasks=len(admitted.planned), selected_tasks=len(admitted.eligible),
                excluded_tasks=len(admitted.exclusions),
                dispatches=len(actor.slots), acks=len(closes), owner_closes=len(closes),
                rewards=len(rewards), rows=len(rows), overlap=len(entered),
                program_dispatches=0, scorer_dispatches=7, policy_requests=policy.calls,
                runners=sum(len(row.runners) for row in programs),
                runner_closes=sum(len(row.closes) for row in programs),
                validations=sum(len(row.validations) for row in programs),
                episodes=len(episodes), successful_episodes=sum(bool(e.ok) for e in episodes),
                failed_episodes=sum(not e.ok for e in episodes),
                successful_rows=sum(bool(row["ok"]) for row in rows),
                target_rewards=len(invalid_target_rewards), decoded_control_hits=invalid_hits[0],
                target_successful_rows=sum(bool(row["ok"]) for row in rows if any(
                    trace["id"] == controller.scope.trace.id for trace in row["traces"])),
                owner_barrier=True, env_barrier=True)
            actor.retirement.invalid_checkpoint = checkpoint
            actor.retirement.invalid_control = mutant == "invalid-target-zero"
            controller.episodes, controller.output_dir = episodes, config.output_dir
            controller.target_rewards, controller.program_records = invalid_target_rewards, programs
            actor.retirement.record_outcome(checkpoint)
            # Deliberately late: original SDK output and legitimate zero reward
            # already exist. No earlier score==1 / invalid-provenance gate.
            controller.check_target(episodes=episodes, rows=rows,
                                    target_rewards=invalid_target_rewards)
            assert invalid_hits[0] == 0
            controller.check_provenance()
            assert checkpoint["successful_episodes"] == checkpoint["successful_rows"] == 6
            assert checkpoint["failed_episodes"] == 1 and len(rewards) == 6
            return checkpoint
        if program_case:
            call, = program_calls
            owner, = [row for row in owners if row.actual.role == "program"]
            assert call.owner is owner.actual and call.scope is owner.scope is target_scope[0]
            assert call.scope.task is owner.sdk_task
            assert call.scope.private is call.program.kwargs["task"] is owner.task
            assert call.scope.program is call.program.harness
            assert call.program.context.get(api._rollout) is call.scope
            assert call.runner is call.program.runners[0] and call.code == PROGRAM_CODE
            assert any(trace is call.scope.trace for trace in traces)
            assert any(row.actual is call.owner for row in (first, second))
            assert first.task is not second.task
            actual = call.owner
            completion = actual._completion
            ack = completion.cleanup_ack
            close, = [row for row in closes if row.actual is actual]
            assert ack is close.ack is actual._authority.ack and ack._authority.owner is actual
            assert ack.role == "program" and not ack.not_started
            assert ack.child_waits and ack.thread_joins and ack.released
            assert len(ack.guardian_reaps) == 1 and not actual._thread.is_alive()
            assert ack.request_sha256 == core.request_sha256(actual.request)
            assert ack.profile_sha256 == core.execution_profile_sha256(profile)
            assert completion.abort is None and completion.outcome.abort is None
            assert completion.outcome.rejected is False
            assert call.observation is completion.outcome.observation
            db, = [db for db in admitted.databases if db.db_id == owner.task.db_id]
            assert actual.db_path == Path(owner.task.db_path)
            assert actual.request.db_sha256 == db.sha256
            assert actual.request.program == PROGRAM_CODE and actual.request.max_rows == 3
            # Read the actual SDK assistant call ID in this original scope,
            # then select its subsequent tool observation by that ID.
            (tool_body, tool_call), = [
                (body, tool_call) for body, scope in policy_scopes
                if scope is call.scope for item in body["messages"]
                if item.get("role") == "assistant"
                for tool_call in item.get("tool_calls") or []]
            call.tool_call_id = tool_call["id"]
            assert call.tool_call_id == program_step["call_id"]
            assert tool_call["function"]["name"] == program_step["name"]
            assert json.loads(tool_call["function"]["arguments"]) == program_step["arguments"]
            all_tool_messages = [(body, scope, message)
                             for body, scope in policy_scopes for message in body["messages"]
                             if message.get("role") == "tool"]
            assert len(all_tool_messages) == 1
            (body, scope, message), = [
                item for item in all_tool_messages
                if item[2].get("tool_call_id") == call.tool_call_id]
            assert scope is call.scope and body is not policy.bodies[0]
            assert body is tool_body
            assert message["tool_call_id"] == call.tool_call_id
            assert message["name"] == "run_program"
            assert len(policy_scopes) == len(policy.bodies)
            assert Counter(id(scope) for _, scope in policy_scopes) == Counter(
                {id(row.scope): 2 if row.scope is call.scope else 1 for row in programs})
            actual_program_observation = call.observation
            actual_policy_tool_observation = message["content"]
            # Retain measurements BEFORE the sole content gate/retirement.
            checkpoint = dict(
                decision="ack", scopes=len(programs), dispatches=len(actor.slots),
                acks=sum(row.ack is row.actual._authority.ack for row in closes),
                owner_closes=len(closes), rewards=len(rewards), rows=len(rows),
                overlap=len(entered), program_dispatches=sum(
                    row.actual.role == "program" for row in owners),
                scorer_dispatches=sum(row.actual.role == "scorer" for row in owners),
                policy_requests=policy.calls, runners=sum(len(row.runners) for row in programs),
                validations=sum(len(row.validations) for row in programs),
                runner_closes=sum(len(row.closes) for row in programs),
                SentinelHit=sentinel_hits[0])
            actor.retirement.record_outcome(checkpoint)
            assert (actual_program_observation, actual_policy_tool_observation) == (PROGRAM_EXPECTED, PROGRAM_EXPECTED), "SDK_PROGRAM_OBSERVATION_VERBATIM"
            assert sentinel_hits[0] == 0
            return checkpoint
        return dict(decision="ack", scopes=expected, dispatches=expected,
                    acks=expected, owner_closes=expected, rewards=expected,
                    overlap=2, program_dispatches=0, rows=len(rows))
    finally:
        pass  # HOST retirement owns failures before this try/first yield too.


@pytest.mark.parametrize("rollouts", (1, 2), ids=(
    "all-seven-distinct-tasks", "all-seven-two-samples"))
def test_registered_sdk_canonical_positive(tmp_path, rollouts):
    from bench.test_validated_draw_databases import _artifacts
    from ptc.test_sql_lifecycle_process import _owned_guest_case

    # Real SQLite preparation is parent-only, BEFORE the guards/deadline.
    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)
    prepared = (corpus, draw, supplement, draw_sha, supplement_sha)
    phase = "sdk-positive-one" if rollouts == 1 else "sdk-positive-two"
    result = _owned_guest_case(tmp_path, "scorer", phase, prepared=prepared)
    expected = 7 * rollouts
    assert result["decision"] == "ack" and result["hook_hits"] == 0
    assert result["scopes"] == result["dispatches"] == result["acks"] == expected
    assert result["owner_closes"] == result["rewards"] == result["rows"] == expected
    assert result["overlap"] == 2 and result["program_dispatches"] == 0
    assert result["physical_finalized"] is True and result["retirement_errors"] == 0
    assert result["retirement_stages"] == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1
    assert result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0


def _program_driver_refusal_origin(driver):
    """Derive the phase-bound explicit refusal, safe from assert rewriting."""
    import ast
    source = Path(__file__).with_name("test_sql_lifecycle_process.py").resolve()
    assert Path(driver.__code__.co_filename).resolve() == source
    tree = ast.parse(source.read_text(), filename=str(source))
    function, = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_owned_guest_case"]
    expected = ast.parse(
        'if phase == "sdk-program-one" and not ('
        'result.get("ok") is True and process.returncode == 0):\n'
        '    raise AssertionError(result)').body[0]
    branch, = [node for node in ast.walk(function) if isinstance(node, ast.If)
               and ast.dump(node.test) == ast.dump(expected.test)]
    gate, = branch.body
    assert isinstance(gate, ast.Raise)
    assert ast.dump(gate) == ast.dump(expected.body[0])
    return gate.lineno


def test_program_refusal_dict_identity_under_pytest():
    """Explicit refusal retains one dictionary and completed-finally updates."""
    receipt = {}

    def refuse():
        try:
            raise AssertionError(receipt)
        finally:
            receipt["finally_completed"] = True

    with pytest.raises(AssertionError) as caught:
        refuse()
    assert type(caught.value) is AssertionError and len(caught.value.args) == 1
    assert caught.value.args[0] is receipt
    assert caught.value.args[0]["finally_completed"] is True


@pytest.mark.parametrize("case", (
    "positive", "sentinel-expected-failure", "restored"))
def test_sdk_one_program_full_seven(tmp_path, case):
    from bench.test_validated_draw_databases import _artifacts
    from ptc.test_sql_lifecycle_process import _owned_guest_case

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # BEFORE the original 19.5s deadline.
    prepared = (corpus, draw, supplement, draw_sha, supplement_sha)
    negative = case == "sentinel-expected-failure"
    driver = _owned_guest_case  # Original code identity retained before call.
    if negative:
        driver_line = _program_driver_refusal_origin(driver)
        with pytest.raises(AssertionError) as caught:
            driver(tmp_path, "scorer", PROGRAM_PHASE, prepared=prepared,
                   mutant="program-observation-sentinel", expected_ok=True)
        exc = caught.value
        assert type(exc) is AssertionError and len(exc.args) == 1
        result, = exc.args
        assert type(result) is dict
        origin = exc.__traceback__
        assert origin is not None
        while origin.tb_next is not None:
            origin = origin.tb_next
        assert origin.tb_frame.f_code is driver.__code__
        assert Path(origin.tb_frame.f_code.co_filename).resolve() == Path(
            __file__).with_name("test_sql_lifecycle_process.py").resolve()
        assert origin.tb_lineno == driver_line
        failure = result["acceptance_failure"]
        assert type(failure) is dict and set(failure) == {
            "type", "gate", "origin", "primary_preserved", "SentinelHit"}
        assert failure == dict(
            type="AssertionError", gate=PROGRAM_GATE, origin=_program_gate_origin(),
            primary_preserved=True, SentinelHit=1)
        assert failure["primary_preserved"] is True
        assert type(failure["SentinelHit"]) is int
        assert type(failure["origin"]) is dict
        assert set(failure["origin"]) == {"file", "function", "line"}
        assert type(failure["origin"]["line"]) is int
        assert result["ok"] is False and result["error"] == "AssertionError"
        # Exception keeps the SAME dictionary, enriched only by driver finally.
        assert exc.args[0] is result
    else:
        result = driver(tmp_path, "scorer", PROGRAM_PHASE,
                        prepared=prepared, expected_ok=True)
        assert result["ok"] is True and "acceptance_failure" not in result
        assert result["retirement_errors"] == 0
    assert result["safe"] is True and result["physical_finalized"] is True
    counts = dict(
        scopes=7, dispatches=8, acks=8, owner_closes=8, rewards=7, rows=7,
        overlap=2, program_dispatches=1, scorer_dispatches=7, policy_requests=8,
        runners=7, validations=7, runner_closes=7, SentinelHit=int(negative))
    assert all(type(result[key]) is int and result[key] == value
               for key, value in counts.items())
    assert result["hook_hits"] == result["mutation_hits"] == 0
    assert result["retirement_stages"] == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    proof = result["program_physical"]
    assert proof["native_proof"] is True
    assert proof["slots"] == proof["nested_safe"] == 8
    assert proof["creators"] == proof["creator_waits"] == 8
    assert proof["ambiguous_creators"] == proof["live_readers"] == proof["open_slot_fds"] == 0
    assert proof["resource_errors"] == proof["nonprimary_errors"] == 0
    assert proof["resource_stop_calls"] and all(
        type(calls) is int and calls == 1 for calls in proof["resource_stop_calls"])
    receipt = result["outer_retirement"]
    assert set(receipt) == {"actual_wait", "returncode", "streams_closed", "ledger_released"}
    assert receipt["actual_wait"] is True and receipt["streams_closed"] is True
    assert receipt["ledger_released"] is True
    assert type(receipt["returncode"]) is int and receipt["returncode"] == int(negative)


def test_sdk_program_three_cancels(tmp_path):
    """Qualification success is cancelled evaluation, never a successful run."""
    from bench.test_validated_draw_databases import _artifacts
    from ptc.test_sql_lifecycle_process import _owned_guest_case

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # BEFORE the unchanged 19.5s HOST deadline.
    result = _owned_guest_case(
        tmp_path, "program", "sdk-cancel-program",
        prepared=(corpus, draw, supplement, draw_sha, supplement_sha),
        expected_ok=True)
    assert result["ok"] is True and result["safe"] is True
    assert result["decision"] == "cancellation-qualified"
    assert result["evaluation_cancelled"] is True
    assert "acceptance_failure" not in result and result["retirement_errors"] == 0
    counts = dict(
        selected_tasks=7, scopes=2, allocations=2, dispatches=1,
        program_dispatches=1, scorer_dispatches=0, acks=2, not_started_acks=1,
        owner_closes=2, resource_tasks=4, resource_close_bodies=4,
        start_all_scopes=2, caller_cancellations=3, delivered_cancellations=4,
        empty_cleanup_deliveries=1, cleanup_join_deliveries=3,
        same_cleanup_join_cancellations=2, consumed_lanes=2, revoked_scopes=2,
        live_retained_tasks=0, rewards=0, successful_rows=0, policy_requests=2)
    assert all(type(result[key]) is int and result[key] == value
               for key, value in counts.items())
    assert result["retained_tasks"] >= 9
    assert result["physical_finalized"] is True
    assert result["retirement_stages"] == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    proof = result["program_physical"]
    assert proof["native_proof"] is True
    assert proof["slots"] == proof["nested_safe"] == 1
    assert proof["creators"] == proof["creator_waits"] == 1
    assert proof["ambiguous_creators"] == proof["live_readers"] == proof["open_slot_fds"] == 0
    assert proof["resource_errors"] == proof["nonprimary_errors"] == 0
    assert proof["resource_stop_calls"] and all(
        type(calls) is int and calls == 1 for calls in proof["resource_stop_calls"])
    receipt = result["outer_retirement"]
    assert receipt["actual_wait"] is True and receipt["returncode"] == 0
    assert receipt["streams_closed"] is True and receipt["ledger_released"] is True


def test_sdk_scorer_three_cancels(tmp_path):
    """Two terminal replies, 0 PROGRAM calls, 1 SCORER SLOT, exact4 deliveries."""
    from bench.test_validated_draw_databases import _artifacts
    from ptc.test_sql_lifecycle_process import _owned_guest_case

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # BEFORE the unchanged 19.5s HOST deadline.
    result = _owned_guest_case(
        tmp_path, "scorer", "sdk-cancel-scorer",
        prepared=(corpus, draw, supplement, draw_sha, supplement_sha),
        expected_ok=True)
    assert result["ok"] is True and result["safe"] is True
    assert result["decision"] == "cancellation-qualified"
    assert result["evaluation_cancelled"] is True
    assert "acceptance_failure" not in result and result["retirement_errors"] == 0
    counts = dict(
        selected_tasks=7, scopes=2, allocations=2, dispatches=1,
        program_calls=0, program_dispatches=0, scorer_dispatches=1,
        acks=2, not_started_acks=1, owner_closes=2,
        resource_tasks=4, resource_close_bodies=4, start_all_scopes=2,
        score_children=4, observed_score_cancellations=2,
        caller_cancellations=3, delivered_cancellations=4,
        empty_cleanup_deliveries=1, cleanup_join_deliveries=3,
        same_cleanup_join_cancellations=2, consumed_lanes=2, revoked_scopes=2,
        live_retained_tasks=0, rewards=0, returned_results=0,
        successful_rows=0, policy_requests=2)
    assert all(type(result[key]) is int and result[key] == value
               for key, value in counts.items())
    assert result["cancelled_score_children"] >= 2
    assert result["cancelled_score_children"] + result["completed_score_children"] == 4
    assert result["retained_tasks"] >= 13
    assert result["physical_finalized"] is True
    assert result["retirement_stages"] == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    # Existing common current-native receipt, kept under its established key.
    proof = result["program_physical"]
    assert proof["native_proof"] is True
    assert proof["slots"] == proof["nested_safe"] == 1
    assert proof["creators"] == proof["creator_waits"] == 1
    assert proof["ambiguous_creators"] == proof["live_readers"] == proof["open_slot_fds"] == 0
    assert proof["resource_errors"] == proof["nonprimary_errors"] == 0
    assert proof["resource_stop_calls"] and all(
        type(calls) is int and calls == 1 for calls in proof["resource_stop_calls"])
    receipt = result["outer_retirement"]
    assert set(receipt) == {"actual_wait", "returncode", "streams_closed", "ledger_released"}
    assert receipt["actual_wait"] is True and receipt["returncode"] == 0
    assert receipt["streams_closed"] is True and receipt["ledger_released"] is True


def _invalid_driver_refusal_origin(driver):
    """Independent AST for the unchanged positive predicate's explicit refusal."""
    import ast
    path = Path(__file__).with_name("test_sql_lifecycle_process.py").resolve()
    assert Path(driver.__code__.co_filename).resolve() == path
    tree = ast.parse(path.read_text(), filename=str(path))
    function, = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_owned_guest_case"]
    expected = ast.parse(
        'if phase in ("sdk-invalid-gold_error", "sdk-invalid-gold_timeout", '
        '"sdk-invalid-gold_truncated", "sdk-invalid-db_missing") and not ('
        'result.get("ok") is True and process.returncode == 0):\n'
        '    raise AssertionError(result)').body[0]
    branch, = [node for node in ast.walk(function) if isinstance(node, ast.If)
               and ast.dump(node.test) == ast.dump(expected.test)]
    gate, = branch.body
    assert ast.dump(gate) == ast.dump(expected.body[0])
    return gate.lineno


def _invalid_expected_origins():
    """Parent derives source origins independently of the guest's controller."""
    import ast
    path = Path(__file__).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkInvalidStatus"]
    method, = [node for node in cls.body
               if isinstance(node, ast.FunctionDef) and node.name == "check_target"]
    gate, = [node for node in ast.walk(method) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant)
             and node.msg.value == "SDK_INVALID_TARGET_NO_REWARD"]
    origins = dict(oracle=dict(file=path.name, line=gate.lineno))
    path = path.parents[1] / "cotrain_owned_sql.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlTask"]
    score, = [node for node in cls.body
              if isinstance(node, ast.AsyncFunctionDef) and node.name == "score"]
    cleanup, = [node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "_drain_scope"]
    for kind, method, message in (
            ("score", score, "owned SQL task is not valid for scoring"),
            ("cleanup", cleanup, "owned SQL scope cleanup failed")):
        gate, = [node for node in ast.walk(method) if isinstance(node, ast.Raise)
                 and isinstance(node.exc, ast.Call)
                 and any(isinstance(arg, ast.Constant) and arg.value == message
                         for arg in node.exc.args)]
        origins[kind] = dict(file=path.name, line=gate.lineno)
    return origins


def _invalid_actor_case(tmp_path, status, *, control=False):
    from bench.test_validated_draw_databases import _artifacts
    from ptc import test_sql_lifecycle_process as lifecycle

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # Parent-only SQL, before the 19.5s deadline.
    driver = lifecycle._owned_guest_case
    code, line = driver.__code__, _invalid_driver_refusal_origin(driver)
    with pytest.raises(AssertionError) as caught:
        driver(tmp_path, "scorer", "sdk-invalid-" + status,
               prepared=(corpus, draw, supplement, draw_sha, supplement_sha),
               mutant="invalid-target-zero" if control else "none", expected_ok=True)
    error = caught.value
    assert type(error) is AssertionError and len(error.args) == 1
    result, = error.args
    assert type(result) is dict and driver.__code__ is code
    tb = error.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is code and tb.tb_lineno == line
    assert Path(code.co_filename).resolve() == Path(lifecycle.__file__).resolve()
    assert tb.tb_frame.f_locals["result"] is result  # SAME actual dict after finally.
    process = tb.tb_frame.f_locals["process"]
    assert process.actual_wait and process.returncode == 1
    assert all(stream is None or stream.closed for stream in (
        process.stdin, process.stdout, process.stderr))
    assert process not in tb.tb_frame.f_locals["registry"]
    assert process not in lifecycle._OWNED_GUEST_OUTER_OWNERS
    assert result["outer_retirement"] == dict(
        actual_wait=True, returncode=1, streams_closed=True, ledger_released=True)
    assert result["safe"] is True and result["ok"] is False
    assert result["physical_finalized"] is True
    assert result["retirement_stages"] == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    counts = dict(
        planned_tasks=8, selected_tasks=7, excluded_tasks=1, scopes=7, dispatches=7,
        acks=7, owner_closes=7, rows=7, overlap=2, program_dispatches=0,
        scorer_dispatches=7, policy_requests=7, runners=7, runner_closes=7, validations=7,
        episodes=7, successful_episodes=7 if control else 6,
        failed_episodes=0 if control else 1, successful_rows=7 if control else 6,
        rewards=7 if control else 6, target_rewards=int(control),
        target_successful_rows=int(control), decoded_control_hits=int(control))
    assert result["decision"] == "invalid-observed" and result["status"] == status
    assert all(type(result[key]) is int and result[key] == value for key, value in counts.items())
    assert result["owner_barrier"] is True and result["env_barrier"] is True
    assert result["hook_hits"] == result["mutation_hits"] == 0
    physical = result["program_physical"]
    assert physical["native_proof"] is True
    assert physical["slots"] == physical["nested_safe"] == 7
    assert physical["creators"] == physical["creator_waits"] == 7
    assert all(physical[key] == 0 for key in (
        "ambiguous_creators", "live_readers", "open_slot_fds", "resource_errors"))
    assert physical["resource_stop_calls"] and all(
        type(count) is int and count == 1 for count in physical["resource_stop_calls"])
    origins = _invalid_expected_origins()
    common = dict(
        verified=True, status=status, episodes=7, successful_episodes=7 if control else 6,
        failed_episodes=0 if control else 1, successful_rows=7 if control else 6,
        target_rewards=int(control), target_successful_rows=int(control),
        acks=7, resource_tasks=14, owner_barrier=True, env_barrier=True)
    if control:
        assert result["error"] == "AssertionError" and result["retirement_errors"] >= 1
        assert physical["nonprimary_errors"] == 0
        assert result["invalid_qualification"] == dict(verified=False, status=status)
        assert result["invalid_control_qualification"] == dict(
            common, gate="SDK_INVALID_TARGET_NO_REWARD", origin=origins["oracle"],
            primary_preserved=True, single_error_identity=True, decoded_control_hits=1,
            target_reward_score=0.0)
    else:
        assert result["error"] in ("ScoreInfrastructureError", "RuntimeError")
        assert result["retirement_errors"] >= 2 and physical["nonprimary_errors"] >= 1
        assert "invalid_control_qualification" not in result
        assert result["invalid_qualification"] == dict(
            common, distinct_expected_errors=2, error_identity_set_match=True,
            primary_member=True, score_origin=origins["score"], cleanup_origin=origins["cleanup"])


@pytest.mark.parametrize("status", (
    "gold_error", "gold_timeout", "gold_truncated", "db_missing"))
def test_sdk_decoded_invalid_full_seven(tmp_path, status):
    """7 real decoded results/ACKs, 6 successes, 1 unrewarded invalid target."""
    _invalid_actor_case(tmp_path, status)


@pytest.mark.parametrize("case", ("zero-wire-control", "fresh-restore"))
def test_sdk_invalid_target_zero_control_and_restore(tmp_path, case):
    """Wire sensitivity only; a fresh unmutated gold_error follows the control."""
    _invalid_actor_case(tmp_path, "gold_error", control=case == "zero-wire-control")


def _timeout_driver_refusal_origin(driver):
    import ast
    path = Path(__file__).with_name("test_sql_lifecycle_process.py").resolve()
    assert Path(driver.__code__.co_filename).resolve() == path
    tree = ast.parse(path.read_text(), filename=str(path))
    function, = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_owned_guest_case"]
    expected = ast.parse(
        'if phase == "sdk-scoring-timeout" and not ('
        'result.get("ok") is True and process.returncode == 0):\n'
        '    raise AssertionError(result)').body[0]
    branch, = [node for node in ast.walk(function) if isinstance(node, ast.If)
               and ast.dump(node.test) == ast.dump(expected.test)]
    gate, = branch.body
    assert ast.dump(gate) == ast.dump(expected.body[0])
    return gate.lineno


def _timeout_parent_oracle_origin():
    """Independent parent AST, not the guest's reported error text/origin."""
    import ast
    path = Path(__file__).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkScoringTimeout"]
    method, = [node for node in cls.body
               if isinstance(node, ast.FunctionDef) and node.name == "check_public_return"]
    gate, = [node for node in ast.walk(method) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant) and node.msg.value == "SDK_TIMEOUT_PUBLIC_RETURN_BARRIER"]
    return dict(file=path.name, line=gate.lineno)


def _timeout_actor_case(tmp_path, *, control=False):
    from bench.test_validated_draw_databases import _artifacts
    from ptc import test_sql_lifecycle_process as lifecycle

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # Parent-only SQL, BEFORE the unchanged 19.5s deadline.
    driver = lifecycle._owned_guest_case
    code, line = driver.__code__, _timeout_driver_refusal_origin(driver)
    kwargs = dict(prepared=(corpus, draw, supplement, draw_sha, supplement_sha), expected_ok=True)
    if control:
        with pytest.raises(AssertionError) as caught:
            driver(tmp_path, "scorer", "sdk-scoring-timeout",
                   mutant="timeout-early-public-release", **kwargs)
        error = caught.value
        assert type(error) is AssertionError and len(error.args) == 1
        result, = error.args
        assert type(result) is dict and driver.__code__ is code
        tb = error.__traceback__
        while tb.tb_next is not None:
            tb = tb.tb_next
        assert tb.tb_frame.f_code is code and tb.tb_lineno == line
        assert Path(code.co_filename).resolve() == Path(lifecycle.__file__).resolve()
        assert tb.tb_frame.f_locals["result"] is result
        process = tb.tb_frame.f_locals["process"]
        assert process.actual_wait and process.returncode == 1
        assert all(stream is None or stream.closed for stream in (
            process.stdin, process.stdout, process.stderr))
        assert process not in tb.tb_frame.f_locals["registry"]
        assert process not in lifecycle._OWNED_GUEST_OUTER_OWNERS
        assert result["ok"] is False and result["error"] == "AssertionError"
        assert result["decision"] == "scoring-timeout-observed"
        assert result["timeout_qualification"] == dict(verified=False)
    else:
        result = driver(tmp_path, "scorer", "sdk-scoring-timeout", mutant="none", **kwargs)
        assert result["ok"] is True and result["decision"] == "scoring-timeout-qualified"
        assert result["retirement_errors"] == 0 and "timeout_control_qualification" not in result
    assert result["safe"] is True and result["physical_finalized"] is True
    assert result["outer_retirement"] == dict(
        actual_wait=True, returncode=int(control), streams_closed=True, ledger_released=True)
    assert result["retirement_stages"] == {"async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    counts = dict(
        planned_tasks=8, selected_tasks=7, excluded_tasks=1, scopes=7, policy_requests=7,
        allocations=7, owner_closes=7, acks=7, not_started_acks=7, dispatches=0,
        program_dispatches=0, scorer_dispatches=0, native_endpoints=0, returned_results=0,
        rewards=0, successful_rows=0, episodes=7, failed_episodes=7, rows=7, runners=7,
        runner_closes=7, validations=7, resource_tasks=14, cancelled_score_children=7,
        successful_harness_children=7, original_timeout_chains=7,
        held_checkpoints=6 if control else 7, early_release_hits=int(control))
    assert all(type(result[key]) is int and result[key] == value for key, value in counts.items())
    assert type(result["scoring_timeout"]) is float and result["scoring_timeout"] == 0.1
    assert result["hook_hits"] == result["mutation_hits"] == 0
    physical = result["program_physical"]
    assert physical["native_proof"] is True
    assert all(physical[key] == 0 for key in (
        "slots", "nested_safe", "creators", "creator_waits", "ambiguous_creators",
        "live_readers", "open_slot_fds", "resource_errors", "nonprimary_errors"))
    assert physical["resource_stop_calls"] and all(
        type(count) is int and count == 1 for count in physical["resource_stop_calls"])
    proof = dict(
        verified=True, scoring_timeout=0.1, original_timeout_chains=7, not_started_acks=7,
        resource_tasks=14, cancelled_score_children=7, successful_harness_children=7,
        failed_episodes=7, failed_rows=7, dispatches=0, rewards=0, returned_results=0,
        held_checkpoints=6 if control else 7, early_release_hits=int(control))
    if control:
        assert result["retirement_errors"] >= 1
        assert result["timeout_control_qualification"] == dict(
            proof, gate="SDK_TIMEOUT_PUBLIC_RETURN_BARRIER", origin=_timeout_parent_oracle_origin(),
            primary_preserved=True, single_error_identity=True)
    else:
        assert result["timeout_qualification"] == proof


def test_sdk_scoring_timeout_full_seven(tmp_path):
    """Stock 0.1 scoring, seven failed rows, seven genuine NOT_STARTED ACKs."""
    _timeout_actor_case(tmp_path)


def test_sdk_scoring_timeout_early_public_release(tmp_path):
    """One lost fixture hold, not an independent SDK writer-bypass mutation."""
    _timeout_actor_case(tmp_path, control=True)


def test_sdk_scoring_timeout_fresh_restore(tmp_path):
    """Fresh unmutated process/config/data after the directed control."""
    _timeout_actor_case(tmp_path)


def _sibling_driver_refusal_origin(driver):
    """Exact original strict-positive branch, independently read in the parent."""
    import ast
    path = Path(__file__).with_name("test_sql_lifecycle_process.py").resolve()
    assert Path(driver.__code__.co_filename).resolve() == path
    tree = ast.parse(path.read_text(), filename=str(path))
    function, = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "_owned_guest_case"]
    expected = ast.parse(
        'if phase == "sdk-sibling-score-failure" and not ('
        'result.get("ok") is True and process.returncode == 0):\n'
        '    raise AssertionError(result)').body[0]
    branch, = [node for node in ast.walk(function) if isinstance(node, ast.If)
               and ast.dump(node.test) == ast.dump(expected.test)]
    gate, = branch.body
    assert ast.dump(gate) == ast.dump(expected.body[0])
    return gate.lineno


def _sibling_expected_origins():
    """Parent-only AST derivation, no guest qualifier or production imports."""
    import ast
    path = Path(__file__).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "_SdkSiblingScoreFailure"]
    check, = [node for node in cls.body if isinstance(node, ast.FunctionDef)
              and node.name == "check_scope"]
    raised, = [node for node in ast.walk(check) if isinstance(node, ast.Raise)
               and isinstance(node.exc, ast.Attribute)
               and ast.dump(node.exc) == ast.dump(ast.parse("self.fault", mode="eval").body)]
    oracle, = [node for node in cls.body if isinstance(node, ast.FunctionDef)
               and node.name == "check_fault_origin"]
    gate, = [node for node in ast.walk(oracle) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant) and node.msg.value == "SDK_SIBLING_FAULT_ORIGIN"]
    origins = dict(injection=dict(file=path.name, line=raised.lineno),
                   oracle=dict(file=path.name, line=gate.lineno))
    path = path.parents[1] / "cotrain_owned_sql.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "OwnedSqlHarness"]
    method, = [node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
               and node.name == "score"]
    body, = [node for node in method.body if isinstance(node, ast.Try)]
    postbase = body.body[1]
    assert ast.dump(postbase.value.func) == ast.dump(ast.parse("scope.check", mode="eval").body)
    cleanup, = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                and node.name == "_drain_scope"]
    drain, = [node for node in ast.walk(cleanup) if isinstance(node, ast.Raise)]
    origins.update(harness_postbase=dict(file=path.name, line=postbase.lineno),
                   cleanup=dict(file=path.name, line=drain.lineno))
    return origins


def _sibling_actor_case(tmp_path, *, control=False):
    from bench.test_validated_draw_databases import _artifacts
    from ptc import test_sql_lifecycle_process as lifecycle

    corpus, draw, draw_sha, supplement, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)  # Parent SQL only, BEFORE original 19.5s HOST cap.
    driver = lifecycle._owned_guest_case
    code, line = driver.__code__, _sibling_driver_refusal_origin(driver)
    with pytest.raises(AssertionError) as caught:
        driver(tmp_path, "scorer", "sdk-sibling-score-failure",
               mutant="omit-sibling-fault" if control else "none",
               prepared=(corpus, draw, supplement, draw_sha, supplement_sha), expected_ok=True)
    error = caught.value
    assert type(error) is AssertionError and len(error.args) == 1
    result, = error.args
    assert type(result) is dict and driver.__code__ is code
    tb = error.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is code and tb.tb_lineno == line
    assert tb.tb_frame.f_locals["result"] is result and error.args[0] is result
    assert Path(code.co_filename).resolve() == Path(lifecycle.__file__).resolve()
    process = tb.tb_frame.f_locals["process"]
    assert process.actual_wait and process.returncode == 1
    assert all(stream is None or stream.closed for stream in (
        process.stdin, process.stdout, process.stderr))
    assert process not in tb.tb_frame.f_locals["registry"]
    assert process not in lifecycle._OWNED_GUEST_OUTER_OWNERS
    assert result["outer_retirement"] == dict(
        actual_wait=True, returncode=1, streams_closed=True, ledger_released=True)
    assert result["safe"] is True and result["ok"] is False
    assert result["physical_finalized"] is True
    assert result["retirement_stages"] == {"async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert result["executor_workers"] >= 1 and result["executor_helpers"] >= 1
    assert result["live_executor_workers"] == result["live_executor_helpers"] == 0
    if not control:
        _sdk_sibling_persist_host_result(
            result, destination=tmp_path / "sibling-host-result.json")
    count = 7 if control else 6
    counts = dict(
        planned_tasks=8, selected_tasks=7, excluded_tasks=1, scopes=7, policy_requests=7,
        overlap=2, allocations=7, program_allocations=0, scorer_allocations=7,
        dispatches=count, program_dispatches=0, scorer_dispatches=count,
        target_dispatches=int(control), acks=7, not_started_acks=int(not control),
        owner_closes=7, resource_tasks=14, runners=7, runner_closes=7, validations=7,
        returned_results=count, target_returned_results=int(control), rewards=count,
        target_rewards=int(control), episodes=7, successful_episodes=count,
        failed_episodes=int(not control), rows=7, successful_rows=count, failed_rows=int(not control),
        target_successful_rows=int(control), fault_hits=int(not control), omitted_fault_hits=int(control),
        cancelled_score_children=int(not control), failed_harness_children=int(not control),
        successful_harness_children=count)
    assert all(type(result[key]) is int and result[key] == value for key, value in counts.items())
    assert result["decision"] == "sibling-score-failure-observed"
    assert result["owner_barrier"] is result["env_barrier"] is (not control)
    assert result["hook_hits"] == result["mutation_hits"] == 0
    physical = result["program_physical"]
    assert physical["native_proof"] is True
    assert physical["slots"] == physical["nested_safe"] == physical["creators"] == physical["creator_waits"] == count
    assert all(physical[key] == 0 for key in (
        "ambiguous_creators", "live_readers", "open_slot_fds", "resource_errors"))
    assert physical["resource_stop_calls"] and all(
        type(value) is int and value == 1 for value in physical["resource_stop_calls"])
    origins = _sibling_expected_origins()
    if control:
        assert result["error"] == "AssertionError" and physical["nonprimary_errors"] == 0
        assert result["sibling_qualification"] == dict(verified=False)
        assert result["sibling_control_qualification"] == dict(
            verified=True, gate="SDK_SIBLING_FAULT_ORIGIN", origin=origins["oracle"],
            omitted_fault_hits=1, dispatches=7, acks=7, resource_tasks=14,
            successful_episodes=7, successful_rows=7, returned_results=7, rewards=7,
            primary_preserved=True, single_error_identity=True)
    else:
        assert result["error"] == "RuntimeError"
        assert "sibling_control_qualification" not in result
        assert result["sibling_qualification"] == dict(
            verified=True, episodes=7, successful_episodes=6, failed_episodes=1,
            successful_rows=6, failed_rows=1, dispatches=6, acks=7, not_started_acks=1,
            resource_tasks=14, returned_results=6, rewards=6, target_rewards=0,
            owner_barrier=True, env_barrier=True, distinct_expected_errors=2,
            error_identity_set_match=True, primary_member=True,
            harness_postbase_origin=origins["harness_postbase"],
            injection_origin=origins["injection"], cleanup_origin=origins["cleanup"])


def test_sdk_sibling_score_failure_full_seven(tmp_path):
    """6 actual matches, 1 cancelled sibling, 7 issued ACKs, 14 resource Tasks."""
    _sibling_actor_case(tmp_path)


def test_sdk_sibling_score_failure_omit_fault_control(tmp_path):
    """7 ordinary successes before the sole original late fault-origin oracle."""
    _sibling_actor_case(tmp_path, control=True)


def test_sdk_sibling_score_failure_fresh_restore(tmp_path):
    """Fresh baseline process/config/data, no automatic retry or restore."""
    _sibling_actor_case(tmp_path)
