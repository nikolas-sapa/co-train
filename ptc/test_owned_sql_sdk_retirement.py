"""SOURCE-ONLY retirement state tests, not canonical actor/ACK/19.5s proof.

Written before the repair. Eight frozen gates below. No actor is launched:
the negative missing-proof case can never strand an intentionally unsafe HOST.
The idle-worker gate uses an actual original-loop ThreadPoolExecutor, only
when the parent separately authorizes executing this test source.

Ten existing cases preserved. New SOURCE-FIRST regressions: native entry/exit
has all three locks free in both success/failure cases; one original assertion
restores one runtime-local env entry before executor/undo; exact-phase wake pipe
retained before allocation, two closes, zero allocations in other phases; first
post-SAFE callback fault cannot skip second slot or any later native category.
New kernel/process objects are explicitly mocks, never actor/ACK qualification.

Failure-retirement repair, SOURCE tests BEFORE fixture implementation:
1. failure_retirement_preserves_cleanup: 2 owner-close + 4 resource-close +
   2 scope-drain tasks, 0 cancellations each, 8 original delegates once;
   1 explicit eval driver receives exactly 1 retirement cancellation.
   retain_task fallback intentionally exposes today's blanket cancellation.
2. intent_before_test_gate_release: 2 original public intent receipts precede
   all controller/public/guardian releases; pending cleanup-held gets 1 token,
   each public hold 1 release, already released/unobserved barriers 0 tokens.
3. late_cleanup_registration: before/after release, 1 original cleanup task
   retained/joined without cancellation or replacement.
4. pending_cleanup_refuses_safe: 1 protected pending cleanup, finalized False,
   SAFE count 0; original gate resolves for unit hygiene, not acceptance.
5. generic_retirement_roles: driver 1 cancel, cleanup/unclassified 0, all done,
   independent of PROGRAM; conflicting role registration is sticky failure.
6. delivery_diagnostic_snapshot: superseded below by owner-authorized EXACT4
   history, including exactly one EMPTY cleanup wave, never arbitrary OTHER.
7. diagnostic_privacy_bounds: 40 inputs, at most 32 notes/32 tasks/16 stages,
   <=8192 UTF-8 bytes per diagnostic; explicit total/omitted counts, 0 canaries.

Planned private contracts, deliberately absent implementation is NOT skipped:
retain_driver(task), retain_cleanup(task, kind); guest _ObservedTestGates(
ensure_intents=...), observe(hit, release), released(hit), release_pending().
Probe retirement uses actor.test_gates. PROGRAM helper pure _delivery_snapshot(
index, error, target, *, agent, cleanup), _delivery_diagnostic(notes, *,
agent, cleanup); retirement diagnostic(). Tests below pin closed safe schemas.
These are fixture-only tests, not a production API, ACK or native qualification.
No cleanup-cancel exemption from proof, cap relaxation or SDK work.

Authorized compatibility/cooperative retirement, tests BEFORE implementation:
1. exact_four_history_accepts: ONLY 1/EMPTY/2/3, original AGENT then SAME
   CLEANUP, SAME original Env task, 4 builtin CancelledError objects; EMPTY
   awaited before marker2, complete history validated again after caller drain.
2. exact_four_history_rejects_variants: all 4 deletions, 15 extra insertions,
   3 adjacent swaps, wrong scope/task/targets/types/args and snapshot/current
   corruption rejected. No filtering, no inferred SDK originating callsite.
3. empty_is_not_other: EMPTY iff builtin CancelledError.args == (); all other
   unknowns OTHER; immutable captures, 32-note/8192-byte privacy limits retained.
4. public_completion_precedes_native_fallback: 2 original unit public closes +
   2 drains complete BEFORE native callback, 1 driver stop, 2 real public intent
   receipts before gates, delegates once, cleanup cancels/replacements 0.
   FIRST RED exercises current finish order, not absence of a future API.
5. cooperative_cutoff_preserves_pending_api: explicit END-3.75; pending close
   uncancelled at cutoff; fallback attempted, unresolved still SAFE0. Original
   gate resolves for unit hygiene only. Retirement END-.25/safety END-3.5 stay.
6. fallback_attempts_all_after_error: 2 attempts in each of 5 native categories
   after first failure; original primary sticky, current physical proof decisive.
7. fallback_request_breaks_cooperative_wait: before/during notification,
   supervisor NEVER drives LOOP, 1 main native claim, 3 free locks at handoff/
   waits, exhaustive attempts on success/error; public cleanup cancels 0.

Narrow future private contracts pinned here: _validate_delivery_history(notes,
*, scope, env) raises AssertionError or returns None; probe async
_wait_empty_cleanup(scope); _SdkRetirement optional cooperative_cutoff=None,
async _cooperate(), request_fallback(), fallback_requested threading.Event.
HOST passes cooperative_cutoff=END-3.75 explicitly. First order test supplies
the cutoff attribute to today's class without implementing any missing method.
Native callbacks/receivers are inert mocks; real CancelIntent/CancelReceipt
and original public request_cancel are used, NEVER a native ACK claim.
Non-goals: fixture/production/SDK edits, actor attempts, cap changes, fake ACK,
forced revoke, cleanup cancellation, parked-task exemptions or SCORER work.

Explicit stopped-LOOP native handoff, SOURCE tests BEFORE implementation:
1. extracted_watchdog_native_handoff: 8 normal/early x before/during x
   success/error cases execute ORIGINAL watchdog, cleanup adapter, native
   cleanup and native proof ASTs. FIRST RED: 0 entries before MAIN readiness,
   not a missing-API assertion. Real threads/loop/locks, fake kernel/resources.
   1 native claim, 2 slots/creators/controllers/readers, 10 FD closes, 6 streams;
   MAIN publishes after drive release; registered supervisor native phase
   finishes and closes before MAIN resumes LOOP. Error completion mandatory.
2. late_watchdog_registration: before closure accounted, after closure
   ALREADY_RETIRED and 0 new destructive entries. Supervisor completion must
   progress while close waits, proving no phase/bookkeeping lock across wait.
3. handoff_missing_at_guardian_reserve: actual early watchdog, no MAIN ready;
   absolute END-3.5 wait, 0 coordinated entries, 1 missing-handoff error, SAFE0.
4. guardian_independent_safety_still_runs: ORIGINAL guardian watchdog AND
   physical_cleanup at original END-3.5, 1 cleanup despite driving/hung MAIN,
   fake resources only; independent guardian SAFE is NOT a HOST ACK/SAFE.
5. handoff_does_not_replace_proof: successful handoff/native proof plus 1
   pending original API => finalized False/SAFE0, cleanup cancels 0.

Future API assumptions: request_native_handoff() -> "REGISTERED" or
"ALREADY_RETIRED"; wait_native_handoff(deadline) -> bool, supplied END-3.5;
publish_native_handoff(); supervisor_native_finished() in registered watchdog
finally; close_native_handoff(deadline) -> bool, supplied END-.25, serialized
against registration. Missing wait records exactly SDK_NATIVE_HANDOFF_MISSING
once (method OR caller, not both). Short-lock implementation remains parent-owned.
No branch simulator/shared production helper: nested original definitions are
extracted directly; select/kernel/resources/race-observation/exit/report are
declared fakes. Real Event.wait observation delegates to the original wait.
Non-goals: implementation/strict4 changes, actor execution, extra grace, fake
ACKs, protected SDK/core changes, cleanup cancellation or proof exemptions.

Separate actual-owned SCORER cancellation, SOURCE tests BEFORE implementation:
1. scorer_completed_runner_reuse: 2 original completed runner closes + 2
   pending scorer closes = 4 retained resource tasks; 0 runner replay or
   substitution accepted. Extract original observers/lease/close-set unchanged.
2. scorer_start_all_identity: each scope's first post-cancel shield join sees
   exactly 2 original tasks, including SAME completed runner task. Missing
   scorer/replacement runner rejected; NOT 4 simultaneously pending tasks.
3. scorer_score_children: retain exact Task.score/Harness.score unit Tasks;
   original extracted _drain_scope cancels/joins pending originals, completed
   Harness child remains noncancelled and its result is observed. Surviving,
   substituted or fake child rejected. Observer helpers issue 0 cancellations.
4. scorer_dispatch_receipt: evaluate actual original qualify return expressions,
   not a new count implementation. 2 SCORER allocations/1 guardian SLOT must
   return scorer_dispatches=1 (current allocation oracle returns 2). PROGRAM
   remains allocations=2/dispatches=1/program_dispatches=1/scorer_dispatches=0.

Narrow future helper contracts: _SdkProgramCancellation(..., role="program"),
only "program"/"scorer"; expose role. retain_score_children(scope)
captures both original asyncio.Task identities/pending state and retains them;
check_score_children(scope) returns None or raises AssertionError, requires same
original children done, originally pending children actually cancelled/joined,
completed children NOT claimed cancelled and their actual result() observed.
Neither method cancels, joins, substitutes or creates child work. Existing
resource_body/installed shield observer enforce resource identity/once-only
rules. Old constructor fallback supplies ONLY the role label, never validation.
No new shared module or production/core changes. All SDK/native objects remain
inert declared fakes; original drain/observers act on real unit Tasks, NOT SDK
qualification or synthetic ACKs. Strict4/handoff code/tests stay byte-identical.
No SCORER implementation/actor/activation, runtime, imports, cap changes,
context writes, returned ExResult or manufactured result before parent RED.
"""
import ast
import asyncio
from collections import Counter
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from ptc.test_owned_sql_sdk_canonical import _SdkRetirement


def _case():
    loop = asyncio.new_event_loop()
    calls = Counter()

    def disable():
        # The request callback must execute outside the short state lock.
        assert owner.lock.acquire(blocking=False)
        owner.lock.release()
        calls.update(["disable"])
    owner = _SdkRetirement(
        loop=loop, deadline=time.monotonic() + 2.0,
        disable=disable)
    owner.patch = SimpleNamespace(undo=lambda: calls.update(["undo"]))

    def framework():
        yield
        calls.update(["framework"])
    owner.framework = framework()
    next(owner.framework)
    return loop, owner, calls


def _resource(owner, calls, name):
    actual = SimpleNamespace(closed=False)

    async def stop():
        calls.update([name])
        actual.closed = True
    owner.retain_resource(name, actual, stop, lambda: actual.closed)
    return actual


def _finish(loop, owner, *, native=lambda: True, proof=lambda: True):
    try:
        owner.finish(native_retire=native, verify_native=proof)
        return owner.finalized
    finally:
        # No intentionally unretirable loop, worker or HOST in these units.
        if owner.finalized:
            loop.close()


def test_setup_exception_retires_partial_resources():
    """One first-yield fault, one undo/stop attempt, zero leaked resources."""
    loop, owner, calls = _case()
    actual = _resource(owner, calls, "partial")

    def broken_setup():
        calls.update(["fault"])
        raise AssertionError("first yield")
        yield
    owner.framework = broken_setup()
    with pytest.raises(AssertionError) as failure:
        next(owner.framework)
    owner.fail("setup", failure.value)
    assert _finish(loop, owner)
    assert calls["fault"] == calls["partial"] == calls["undo"] == 1
    assert actual.closed and owner.outcome["ok"] is False
    assert owner.primary is failure.value


def test_overlap_assertion_still_retires_both_owners():
    """One overlap fault, two retained owners accounted, zero skipped stops."""
    loop, owner, calls = _case()
    controllers = [SimpleNamespace(accounted=False) for _ in range(2)]
    _resource(owner, calls, "server")
    calls.update(["fault"])
    owner.fail("acceptance", AssertionError("two live controllers"))

    def native():
        for actual in controllers:
            actual.accounted = True
        return True
    assert _finish(loop, owner, native=native,
                   proof=lambda: all(row.accounted for row in controllers))
    assert sum(row.accounted for row in controllers) == 2
    assert calls["fault"] == calls["server"] == calls["undo"] == 1
    assert owner.outcome["ok"] is False


def test_task_drain_failure_does_not_skip_stages():
    """One drain fault; stop, executor stage and undo each attempted once."""
    loop, owner, calls = _case()
    _resource(owner, calls, "server")
    fault = AssertionError("task drain assertion")

    def broken_check():
        calls.update(["fault"])
        raise fault
    owner.check_drained_tasks = broken_check
    owner.record_outcome({"ok": True})
    assert _finish(loop, owner)
    assert calls["fault"] == calls["server"] == calls["undo"] == 1
    assert owner.stages["executor"] == 1 and owner.outcome["ok"] is False
    assert owner.primary is fault


def test_framework_finalizer_failure_does_not_skip_stages():
    """One finalizer fault; executor stage and undo each attempted once."""
    loop, owner, calls = _case()
    fault = AssertionError("post-yield assertion")

    def broken_finalizer():
        yield
        calls.update(["fault"])
        raise fault
    owner.framework = broken_finalizer()
    next(owner.framework)
    owner.record_outcome({"ok": True})
    assert _finish(loop, owner)
    assert calls["fault"] == calls["undo"] == owner.stages["executor"] == 1
    assert owner.outcome["ok"] is False
    assert owner.primary is fault


def test_idle_executor_workers_are_joined():
    """Actual worker alive before retirement, zero captured/helper workers after."""
    loop, owner, calls = _case()
    loop.run_until_complete(asyncio.to_thread(lambda: calls.update(["work"])))
    executor = loop._default_executor
    workers = tuple(executor._threads)
    assert workers and all(worker.is_alive() for worker in workers)
    calls.update(["fault"])
    owner.fail("acceptance", AssertionError("idle-worker acceptance fault"))
    assert _finish(loop, owner)
    assert owner.executor is executor and set(workers) <= owner.workers
    assert all(not worker.is_alive() for worker in owner.workers)
    assert len(owner.executor_helpers) >= 1
    assert all(not helper.is_alive() for helper in owner.executor_helpers)
    assert calls["work"] == calls["undo"] == calls["fault"] == 1
    assert owner.outcome["ok"] is False


def test_watchdog_main_retirement_is_single_action():
    """Two racing requests, one async action/finalizer/undo; no lock-held wait."""
    loop, owner, calls = _case()
    _resource(owner, calls, "server")
    calls.update(["fault"])
    owner.fail("acceptance", AssertionError("racing retirement acceptance fault"))
    ready = threading.Event()

    def main_request():
        calls.update(["request"])
        owner.request()

    def watchdog():
        assert ready.wait(1.0)
        assert loop.is_running()
        calls.update(["request"])
        owner.request(stop_loop=True)
        loop.call_soon_threadsafe(main_request)

    async def driver():
        ready.set()
        await asyncio.Event().wait()

    thread = threading.Thread(target=watchdog)
    thread.start()
    driver_task = owner.retain_driver(loop.create_task(driver()))
    with pytest.raises(asyncio.CancelledError):
        loop.run_until_complete(driver_task)
    thread.join(1.0)
    assert not thread.is_alive()
    assert _finish(loop, owner)
    assert owner.stages["async"] == owner.stages["framework"] == 1
    assert calls["undo"] == calls["framework"] == calls["server"] == 1
    assert calls["request"] == 2 and calls["disable"] == 1
    assert calls["fault"] == 1 and owner.outcome["ok"] is False


def test_slot_failure_does_not_skip_remaining_owners():
    """One slot fault; all three slots, creators, readers and FDs attempted."""
    loop, owner, calls = _case()
    proof = []

    def slot(number):
        calls.update(["slot"])
        if number == 0:
            calls.update(["fault"])
            raise AssertionError("slot proof")
        proof.append(number)

    def native():
        owner.attempt_each("slot", range(3), slot)
        for stage in ("creator", "reader", "fd"):
            owner.attempt_each(stage, range(3), lambda _: calls.update([stage]))
        # The failed verification is an outcome failure. Separate current
        # evidence below proves all physical resources really absent.
        return True
    assert _finish(loop, owner, native=native)
    assert calls["fault"] == 1 and calls["slot"] == 3
    assert calls["creator"] == calls["reader"] == calls["fd"] == 3
    assert proof == [1, 2] and owner.outcome["ok"] is False


def test_missing_physical_proof_never_finalizes():
    """One failed proof, finalized false and zero SAFE emissions; unit only."""
    loop, owner, calls = _case()

    def missing():
        calls.update(["fault"])
        return False
    assert not _finish(loop, owner, proof=missing)
    with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
        owner.prove_safe()
    assert calls["fault"] == 1 and owner.safe_emissions == 0
    assert not owner.finalized and owner.outcome["ok"] is False
    # Fake missing proof only: actual loop/executor already retired.
    loop.close()


@pytest.mark.parametrize("stop_fails", [False, True])
def test_socket_fallback_waits_for_original_stops(stop_fails):
    """Two original stops, zero early closes, two fallback closes even on error."""
    source = Path(__file__).with_name("test_sql_lifecycle_process.py")
    module = ast.parse(source.read_bytes())
    assignment, = [
        node for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)]
    guest = ast.parse(ast.literal_eval(assignment.value))
    function, = [
        node for node in ast.walk(guest) if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "close_sdk_sockets"]
    calls = Counter()
    owner = SimpleNamespace(resources=[])
    sockets = [SimpleNamespace(close=lambda: calls.update(["close"]))
               for _ in range(2)]

    def attempt_each(stage, actuals, action):
        for actual in actuals:
            action(actual)
    owner.attempt_each = attempt_each
    namespace = {"asyncio": asyncio, "sdk_resources": owner, "sdk_sockets": sockets}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "SOCKET_FALLBACK_ONLY", "exec"), namespace)

    async def scenario():
        entered = [asyncio.Event() for _ in range(2)]
        release = [asyncio.Event() for _ in range(2)]
        fault = ValueError("unit stop error")

        async def stop(index):
            calls.update(["stop"])
            entered[index].set()
            await release[index].wait()
            if stop_fails and index == 0:
                raise fault
        tasks = [asyncio.create_task(stop(index)) for index in range(2)]
        fallback = asyncio.create_task(namespace["close_sdk_sockets"]())
        owner.resources = [SimpleNamespace(task=fallback)] + [
            SimpleNamespace(task=task) for task in tasks]
        try:
            for event in entered:
                await event.wait()
            await asyncio.sleep(0)
            assert calls["stop"] == 2
            assert calls["close"] == 0 and not fallback.done(), (
                "SDK_SOCKET_FALLBACK_BEFORE_STOPS")
            release[0].set()
            await asyncio.gather(tasks[0], return_exceptions=True)
            await asyncio.sleep(0)
            assert calls["close"] == 0 and not fallback.done()
            release[1].set()
            await fallback
            assert all(task.done() for task in tasks)
            assert calls["close"] == 2
            assert tasks[0].exception() is (fault if stop_fails else None)
        finally:
            for event in release:
                event.set()
            await asyncio.gather(*tasks, fallback, return_exceptions=True)

    asyncio.run(asyncio.wait_for(scenario(), 2.0))


@pytest.mark.parametrize("native_fails", [False, True])
def test_native_retirement_has_no_drive_or_state_lock_at_entry_exit(native_fails):
    """Two lock snapshots, three free locks each, even after one native error."""
    loop, owner, calls = _case()
    cleanup_lock = threading.Lock()
    fault = AssertionError("unit native failure")
    snapshots = []

    def snapshot():
        values = []
        for lock in (owner.lock, owner.loop_drive_lock, cleanup_lock):
            acquired = lock.acquire(blocking=False)
            values.append(acquired)
            if acquired:
                lock.release()
        snapshots.append((loop.is_running(), tuple(values)))

    def native():
        snapshot()
        try:
            if native_fails:
                raise fault
        finally:
            snapshot()

    assert _finish(loop, owner, native=native)
    assert snapshots == [(False, (True, True, True))] * 2, (
        "SDK_NATIVE_DRIVE_LOCK_HELD")
    assert owner.primary is (fault if native_fails else None)
    assert len(owner.errors) == int(native_fails)
    assert owner.finish_claims == 1 and owner.stages == {
        "async": 1, "framework": 1, "executor": 1, "undo": 1}
    assert calls["undo"] == 1 and owner.complete.is_set()


def test_original_finalizer_assert_restores_only_runtime_env_before_executor():
    """One actual local-generator assertion, arm/catch/restore=1, later stages=1."""
    import os
    from ptc.test_owned_sql_sdk_retirement_physical import (
        _SdkPhysicalProbe, _sdk_framework_finalizer)

    loop, owner, calls = _case()
    runtime = SimpleNamespace(stopped=False, env={"unit": "unchanged"})
    state = SimpleNamespace(runtimes=[runtime])
    process_path = os.environ.get("PATH")

    def original_framework():
        yield state
        calls.update(["original-finalizer"])
        for runtime in state.runtimes:
            assert "PATH" not in runtime.env

    async def stop():
        runtime.stopped = True
        calls.update(["stop"])
    owner.retain_resource("runtime", runtime, stop, lambda: runtime.stopped)
    probe = _SdkPhysicalProbe(
        "sdk-retire-framework-finalizer", SimpleNamespace(retirement=owner))
    original = original_framework()
    owner.framework = _sdk_framework_finalizer(original, probe)
    assert next(owner.framework) is state
    owner.state = state
    owner.record_outcome({"ok": False, "decision": "retirement-checkpoint"})
    assert owner.primary is None
    shutdown = owner._shutdown_executor

    def after_restore():
        assert probe.finalizer_restored == 1 and runtime.env == {"unit": "unchanged"}
        assert os.environ.get("PATH") == process_path
        calls.update(["executor-after-restore"])
        return shutdown()  # Original executor method, never a replacement stage.
    owner._shutdown_executor = after_restore
    assert _finish(loop, owner)
    assert type(owner.primary) is AssertionError
    assert owner.primary is probe.fault_error
    assert probe.fault_hits == 1
    assert probe.finalizer_armed == probe.finalizer_caught == probe.finalizer_restored == 1
    assert probe.finalizer_primary_unset and probe.finalizer_origin_verified
    assert runtime.env == {"unit": "unchanged"}
    assert os.environ.get("PATH") == process_path
    assert calls["original-finalizer"] == calls["stop"] == calls["undo"] == 1
    assert owner.stages["executor"] == owner.stages["undo"] == 1
    assert calls["executor-after-restore"] == 1
    assert owner.errors == [("framework", probe.fault_error)]


def test_watchdog_wake_pipe_is_owned_before_allocation_and_exact_phase_only(monkeypatch):
    """Mock kernel: one pipe/two retained FDs, two closes, zero other-phase pipes."""
    from ptc import test_owned_sql_sdk_retirement_physical as physical

    resources, closed, allocations = [], [], []
    owner = SimpleNamespace(
        loop=SimpleNamespace(is_running=lambda: False),
        lock=threading.Lock(), loop_drive_lock=threading.Lock(),
        remaining=lambda: 1.0)

    def retain(kind, actual, stop, verify):
        record = SimpleNamespace(kind=kind, actual=actual, stop=stop, verify=verify)
        resources.append(record)
        return record

    def pipe():
        assert len(resources) == 1 and resources[0].actual.fds == ()
        allocations.append(True)
        return 71, 72

    def fstat(fd):
        assert fd in closed
        raise OSError(9, "unit closed fd")

    def attempt_each(stage, items, action):
        for item in items:
            action(item)
    owner.retain_resource, owner.attempt_each = retain, attempt_each
    monkeypatch.setattr(physical, "os", SimpleNamespace(
        pipe=pipe, close=closed.append, fstat=fstat))
    cleanup_lock, spawn_lock = threading.Lock(), threading.Lock()
    for phase in (*physical._PHYSICAL_PHASES, "sdk-positive-one", "sdk-positive-two"):
        if phase != "sdk-retire-watchdog-race":
            assert physical._sdk_watchdog_wake(
                phase, owner, cleanup_lock, spawn_lock) is None
    assert not resources and not allocations
    wake = physical._sdk_watchdog_wake(
        "sdk-retire-watchdog-race", owner, cleanup_lock, spawn_lock)
    assert resources[0].actual is wake and wake.fds == (71, 72)
    asyncio.run(asyncio.wait_for(resources[0].stop(), 2.0))
    assert allocations == [True] and closed == [71, 72]
    assert resources[0].verify()


def test_extracted_native_slot_callback_fault_continues_all_actual_attempts():
    """Mock kernel: original wait precedes callback; 2 slots/creators/readers, 10 FDs."""
    from ptc.test_owned_sql_sdk_retirement_physical import _SdkPhysicalProbe

    source = Path(__file__).with_name("test_sql_lifecycle_process.py")
    module = ast.parse(source.read_bytes())
    assignment, = [
        node for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)]
    guest = ast.parse(ast.literal_eval(assignment.value))
    function, = [node for node in ast.walk(guest)
                 if isinstance(node, ast.FunctionDef) and node.name == "sdk_native_cleanup"]
    loop, owner, calls = _case()
    slots, owners, entries, closed, checked = [], [], [], [], []

    def stream():
        actual = SimpleNamespace(closed=False)
        actual.close = lambda: setattr(actual, "closed", True)
        return actual

    for index in range(2):
        process = SimpleNamespace(
            pid=100 + index, returncode=0, _creator_ambiguous=False,
            _creator_waited=False, stdin=stream(), stdout=stream(), stderr=stream())

        def wait(timeout=None, process=process):
            process._creator_waited = True
            calls.update(["wait"])
            return process.returncode
        process.wait, process.poll = wait, lambda: 0
        actual = SimpleNamespace(
            _lock=threading.RLock(), _retained=threading.Event(),
            _thread=SimpleNamespace(
                join=lambda timeout=None: calls.update(["controller"]),
                is_alive=lambda: False),
            _resources=[], _endpoints=[], _host_read=None,
            _seal_lock_fd=None, _children=[process])
        owners.append(actual)
        entries.append({"process": process, "registry": actual._children})
        slot = dict(invocation=actual, process=process, safety_w=20 + index,
                    reader_stop_w=30 + index, fds=list(range(40 + 5 * index, 45 + 5 * index)),
                    reader=SimpleNamespace(
                        join=lambda timeout=None: calls.update(["reader"]),
                        is_alive=lambda: False))

        def safe_wait(timeout=None, slot=slot):
            checked.append(slot)
            return True
        slot["safe"] = SimpleNamespace(wait=safe_wait, is_set=lambda: True)
        slots.append(slot)
    actor = SimpleNamespace(retirement=owner, slots=slots)
    probe = _SdkPhysicalProbe("sdk-retire-two-slot-verification", actor)
    owner.physical_probe = probe
    original_callback = probe.after_slot_safe

    def after_original_check(slot):
        assert len(checked) == len(probe.slot_checks) + 1 and checked[-1] is slot, (
            "SDK_SLOT_CALLBACK_BEFORE_ORIGINAL_SAFE")
        return original_callback(slot)
    probe.after_slot_safe = after_original_check
    namespace = dict(
        PHASE=probe.phase, END=time.monotonic() + 2.0, LOOP=loop, time=time,
        threading=threading, sdk_resources=owner, sdk_watchdog_race=None,
        cleanup_lock=threading.Lock(), spawn_lock=threading.Lock(),
        native_started=threading.Event(), native_done=threading.Event(),
        native_retained=[], native_fds=set(), native_objects=[], native_endpoints=[],
        native_entries=[], native_fenced=[False, False], stopping=threading.Event(),
        owners=owners, owner=None, slots=slots,
        trace=SimpleNamespace(lock=threading.Lock(), entries=entries),
        release_sdk_controllers=lambda: None, sdk_native_proof=lambda: True,
        os=SimpleNamespace(write=lambda fd, data: len(data), close=closed.append))
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "NATIVE_ATTEMPT_LOOP_ONLY", "exec"), namespace)
    try:
        assert namespace["sdk_native_cleanup"]()
        assert checked == slots and probe.slot_checks == slots
        assert probe.fault_hits == 1 and owner.primary is probe.fault_error
        assert owner.errors == [("guardian-safe", probe.fault_error)]
        assert probe.native_attempts["guardian-safe"] == slots
        assert probe.native_attempts["creator-reap"] == entries
        assert probe.native_attempts["controller"] == owners
        assert probe.native_attempts["reader"] == slots
        assert probe.native_attempts["creator-streams"] == entries
        assert probe.native_attempts["slot-fd"] == closed
        assert len(closed) == 10 and calls["wait"] == calls["reader"] == 2
        assert calls["controller"] == 2
        assert all(entry["process"]._creator_waited for entry in entries)
        assert all(getattr(entry["process"], name).closed
                   for entry in entries for name in ("stdin", "stdout", "stderr"))
    finally:
        loop.close()  # No real actors, workers or kernel FDs were allocated.


# Repair tests execute isolated definitions only when the parent runs pytest.
# No SDK module, generated HOST body, actor or native fixture is activated.
def _repair_namespace(filename, names, *, optional=(), source=None, extra=None):
    path = Path(__file__).with_name(filename)
    tree = ast.parse(path.read_text() if source is None else source)
    selected = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            selected[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    selected[target.id] = node
    missing = set(names) - set(selected) - set(optional)
    assert not missing, ("planned fixture contract missing", sorted(missing))
    namespace = dict(__name__=__name__, asyncio=asyncio, Counter=Counter,
                     inspect=inspect, json=json, Path=Path,
                     SimpleNamespace=SimpleNamespace, threading=threading, time=time)
    namespace.update(extra or {})
    body = [selected[name] for name in names if name in selected]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _repair_case():
    namespace = _repair_namespace("test_owned_sql_sdk_canonical.py", ["_SdkRetirement"])
    loop = asyncio.new_event_loop()
    calls = Counter()
    owner = namespace["_SdkRetirement"](
        loop=loop, deadline=time.monotonic() + 2.0,
        disable=lambda: calls.update(["disable"]))
    owner.patch = SimpleNamespace(undo=lambda: calls.update(["undo"]))

    def framework():
        yield
        calls["framework"] += 1

    owner.framework = framework()
    next(owner.framework)
    return loop, owner, calls


def _repair_register(owner, task, kind=None):
    # Crucial RED seam: absence of a future role API must not mask the
    # current behavioral bug. Old retain_task still reaches blanket cancel.
    name = "retain_driver" if kind is None else "retain_cleanup"
    retain = getattr(owner, name, None)
    returned = owner.retain_task(task) if retain is None else (
        retain(task) if kind is None else retain(task, kind))
    assert returned is task
    return task


def _repair_hygiene(loop, owner, gates, drivers=()):
    for gate in gates:
        gate.set()  # Resolve ORIGINAL unit gates, never replacement close work.
    for task in drivers:
        if not task.done() and not task.cancelling():
            task.cancel()  # Unit driver only, never cleanup.
    tasks = owner.tasks | owner.stop_tasks | owner.internal_tasks
    if tasks:
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    loop.close()


def _compat_case(*, expired_cutoff=False):
    loop, owner, calls = _repair_case()
    # A single absolute UNIT END. These are the frozen HOST offsets, not a
    # helper that restarts a relative timeout whenever cooperation begins.
    end = time.monotonic() + (3.0 if expired_cutoff else 5.0)
    owner.deadline = end - 0.25
    owner.cooperative_cutoff = end - 3.75
    return loop, owner, calls, end


def _compat_free_locks(owner, cleanup_lock):
    result = []
    for lock in (owner.lock, owner.loop_drive_lock, cleanup_lock):
        acquired = lock.acquire(blocking=False)
        result.append(acquired)
        if acquired:
            lock.release()
    return tuple(result)


def test_public_completion_precedes_native_fallback():
    """FIRST order RED: today's finish reaches native with 4 originals pending."""
    loop, owner, calls, end = _compat_case()
    actuals, receipts, ensure_intents = _repair_public_intents()
    public_gates = [asyncio.Event(), asyncio.Event()]
    guardian = asyncio.Event()
    cleanup_lock = threading.Lock()
    original_tasks, snapshots = [], []
    completed = [False] * 4
    events = []
    independent = [SimpleNamespace(stopped=False) for _ in range(2)]
    mock_native = SimpleNamespace(live=True)

    async def original_public_close(index):
        calls[("delegate", index)] += 1
        await public_gates[index].wait()
        if index == 0:
            await guardian.wait()
        # More original-loop turns than the old async_started drive: native
        # cannot accidentally observe completion merely from that first drive.
        for _ in range(12):
            await asyncio.sleep(0)
        assert mock_native.live, "unit native fallback destroyed public completion"
        completed[index] = True
        events.append(("public-complete", index))

    async def original_scope_drain(index):
        calls[("drain", index)] += 1
        await asyncio.shield(original_tasks[index])
        completed[index + 2] = True
        events.append(("drain-complete", index))

    async def eval_driver():
        await asyncio.Event().wait()

    async def start():
        for index in range(2):
            original_tasks.append(owner.retain_cleanup(
                loop.create_task(original_public_close(index)), "owner-close"))
        for index in range(2):
            original_tasks.append(owner.retain_cleanup(
                loop.create_task(original_scope_drain(index)), "scope-drain"))
        driver = owner.retain_driver(loop.create_task(eval_driver()))
        await asyncio.sleep(0)
        return driver

    def gate_release(name, event):
        assert len(receipts) == 2
        assert all(receipt.intent is actual._intent
                   for actual, receipt in zip(actuals, receipts))
        assert not owner.lock.locked()
        calls[name] += 1
        event.set()

    ledger = _repair_test_gates(ensure_intents)
    hit = dict(kind="HIT", name="cleanup-held", occurrence=1,
               invocation_id=actuals[0].invocation_id.hex)
    ledger.observe(hit, lambda: gate_release("guardian-release", guardian))

    def release():
        ensure_intents()  # Original public method/types, no constructed ACK.
        for index in range(2):
            calls[("controller-release", index)] += 1
            gate_release(("public-release", index), public_gates[index])
        ledger.release_pending()

    driver = loop.run_until_complete(start())
    owner.release = release
    for index, actual in enumerate(independent):
        async def stop(index=index, actual=actual):
            assert len(receipts) == 2 and all(gate.is_set() for gate in public_gates)
            assert guardian.is_set() and driver.cancelled()
            calls[("independent-stop", index)] += 1
            await asyncio.sleep(0)
            actual.stopped = True
        owner.retain_resource("unit-independent", actual, stop,
                              lambda actual=actual: actual.stopped)

    def native():
        snapshots.append(tuple(completed))
        events.append(("native", None))
        assert not loop.is_running()
        assert _compat_free_locks(owner, cleanup_lock) == (True, True, True)
        calls["native"] += 1
        mock_native.live = False  # Destroy only UNIT liveness, no SDK state.
        return True  # Inert fallback, NEVER a native ACK/ownership claim.

    try:
        owner.finish(native_retire=native, verify_native=lambda: not mock_native.live)
        # Keep this FIRST: uses today's actual finish, no new helper needed.
        assert snapshots == [(True, True, True, True)], (
            "PUBLIC_COMPLETION_MUST_PRECEDE_NATIVE_FALLBACK")
        assert calls["native"] == 1 and len(receipts) == 2
        assert all(calls[("delegate", i)] == calls[("drain", i)] == 1 for i in range(2))
        assert all(calls[("public-release", i)] == calls[("controller-release", i)] == 1
                   for i in range(2))
        assert calls["guardian-release"] == 1
        assert calls["disable"] == 1
        assert all(calls[("independent-stop", i)] == 1 and actual.stopped
                   for i, actual in enumerate(independent))
        assert all(task.done() and task.cancelling() == 0 for task in owner.stop_tasks)
        assert events[-1] == ("native", None)
        assert all(task.done() and not task.cancelled() and task.cancelling() == 0
                   and task.exception() is None for task in original_tasks)
        assert driver.cancelled() and driver.cancelling() == 1
        assert set(original_tasks) | {driver} <= owner.tasks
        assert owner.finalized and owner.deadline == end - 0.25
        assert owner.cooperative_cutoff == end - 3.75
    finally:
        _repair_hygiene(loop, owner, [*public_gates, guardian], [driver])


def test_failure_retirement_preserves_cleanup():
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()
    tasks = {}
    fault = AssertionError("original unit acceptance failure")
    owner.fail("acceptance", fault)

    async def cleanup(kind, index):
        key = (kind, index)
        calls[("delegate", key)] += 1
        try:
            await gate.wait()
            if kind == "scope-drain":
                await asyncio.gather(
                    tasks[("owner-close", index)],
                    tasks[("resource-close", index * 2)],
                    tasks[("resource-close", index * 2 + 1)])
            calls[("completed", key)] += 1
        except asyncio.CancelledError:
            calls[("cancelled", key)] += 1
            raise

    async def driver_body():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls["driver-cancelled"] += 1
            raise

    async def start():
        for kind, count in (("owner-close", 2), ("resource-close", 4),
                            ("scope-drain", 2)):
            for index in range(count):
                tasks[(kind, index)] = _repair_register(
                    owner, loop.create_task(cleanup(kind, index)), kind)
        driver = _repair_register(owner, loop.create_task(driver_body()))
        await asyncio.sleep(0)  # All 9 original bodies entered before retirement.
        return driver

    driver = loop.run_until_complete(start())
    owner.release = gate.set
    try:
        owner.finish(native_retire=lambda: True, verify_native=lambda: True)
        # FIRST behavioral gate, no assertion about a missing planned API.
        assert [task.cancelling() for task in tasks.values()] == [0] * 8, (
            "retirement cancelled protected original cleanup")
        assert all(calls[("delegate", key)] == calls[("completed", key)] == 1
                   and calls[("cancelled", key)] == 0 for key in tasks)
        assert all(task.done() and not task.cancelled() for task in tasks.values())
        assert driver.cancelled() and driver.cancelling() == 1
        assert calls["driver-cancelled"] == 1
        assert owner.primary is fault and owner.finalized
        assert set(tasks.values()) | {driver} <= owner.tasks
    finally:
        _repair_hygiene(loop, owner, [gate], [driver])


def _repair_program_namespace():
    optional = ("_delivery_snapshot", "_delivery_diagnostic", "_validate_delivery_history")
    return _repair_namespace(
        "test_owned_sql_sdk_program_cancellation.py",
        ["_MARKERS", *optional, "_SdkProgramCancellation"], optional=optional)


def _repair_probe(namespace, *, api, actor, owners=()):
    return namespace["_SdkProgramCancellation"](
        api=api, core=SimpleNamespace(), actor=actor, profile=object(),
        executor=object(), owners=list(owners), closes=[], programs=[], scorers=[],
        rewards=[], results=[], sdk_tasks=[], controller_gates=[])


def _repair_public_intents():
    """Original public method/types, mocked inert receiver, no execute/ACK."""
    from dataclasses import dataclass
    from typing import Literal
    import uuid

    namespace = _repair_namespace(
        "sql_isolation.py",
        ["_CANCEL_NS", "_UINT64_MAX", "_choice", "_cancel_identity",
         "_cancel_times", "CancelIntent", "CancelReceipt"],
        extra=dict(dataclass=dataclass, Literal=Literal, uuid=uuid))
    path = Path(__file__).with_name("sql_isolation.py")
    tree = ast.parse(path.read_text())
    invocation, = [node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlInvocation"]
    method, = [node for node in invocation.body
               if isinstance(node, ast.FunctionDef) and node.name == "request_cancel"]
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(path), "exec"), namespace)
    owners = [
        SimpleNamespace(_lock=threading.Lock(), _completion=None, _intent=None,
                        _state="NEW", _endpoints=[], invocation_id=uuid.UUID(int=i))
        for i in (1, 2)]
    receipts = []

    def ensure_intents():
        if not receipts:
            receipts.extend(namespace["request_cancel"](actual, "runner_closed")
                            for actual in owners)
        assert len(receipts) == 2
        for actual, receipt in zip(owners, receipts):
            assert type(receipt) is namespace["CancelReceipt"]
            assert receipt.status == "accepted" and receipt.intent is actual._intent
            assert receipt.intent.deadline_ns - receipt.intent.requested_ns == 12_000_000_000
        return receipts

    return owners, receipts, ensure_intents


def _repair_test_gates(ensure_intents):
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    tree = ast.parse(path.read_text())
    assignment, = [node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name)
                            and target.id == "_OWNED_GUEST_PROBE" for target in node.targets)]
    namespace = _repair_namespace(
        path.name, ["_ObservedTestGates"], optional=["_ObservedTestGates"],
        source=ast.literal_eval(assignment.value))
    if "_ObservedTestGates" in namespace:
        return namespace["_ObservedTestGates"](ensure_intents=ensure_intents)
    # Old fixture compatibility is observation ONLY, deliberately no repair.
    # This lets today's real install/release fail on its missing guardian token
    # rather than an AttributeError from a not-yet-authored private ledger.
    observed, released = [], []
    return SimpleNamespace(
        observe=lambda hit, release: observed.append((hit, release)),
        released=released.append, release_pending=lambda: None)


@pytest.mark.parametrize("already_released", [False, True])
def test_intent_before_test_gate_release(already_released):
    namespace = _repair_program_namespace()
    loop, owner, calls = _repair_case()
    actuals, receipts, ensure_intents = _repair_public_intents()
    ledger = _repair_test_gates(ensure_intents)
    tokens = Counter()
    messages = []

    def released(name):
        assert len(receipts) == 2, "release preceded both real public intents"
        assert all(receipt.intent is actual._intent
                   for actual, receipt in zip(actuals, receipts))
        assert not owner.lock.locked()
        tokens[name] += 1

    class Hold(asyncio.Event):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def set(self):
            released(self.name)
            super().set()

    public_holds = [Hold("public-0"), Hold("public-1")]

    def original_release():
        ensure_intents()
        released("controller-0")
        released("controller-1")

    owner.release = original_release
    actor = SimpleNamespace(
        retirement=owner, test_gates=ledger, messages=messages,
        release_pending_test_gates=ledger.release_pending)
    api = SimpleNamespace(_HOOKS=object(), _close_resource=lambda: None,
                          _rollout=SimpleNamespace(get=lambda: None))
    probe = _repair_probe(namespace, api=api, actor=actor, owners=actuals)
    probe.owner_holds = [SimpleNamespace(release=hold) for hold in public_holds]
    # Capture installation without globally replacing create_task or shield.
    probe.install(SimpleNamespace(setattr=lambda *args: None))

    def observe(name, occurrence, release_name):
        hit = dict(kind="HIT", name=name, invocation_id=actuals[0].invocation_id.hex,
                   occurrence=occurrence)
        if name == "adapter-cancel":
            hit["event"] = "REQUEST_DELIVERED"
        messages.append(hit)  # Same decoded object, not a guessed gate.
        ledger.observe(hit, lambda: released(release_name))
        return hit

    if already_released:
        request = observe("adapter-cancel", 1, "REQUEST_DELIVERED")
        ensure_intents()
        released("REQUEST_DELIVERED")  # Original ordinary successful release.
        ledger.released(request)
    pending = observe("cleanup-held", 2, "cleanup-held")
    ledger.observe(pending, lambda: released("duplicate-observation"))
    try:
        owner.release()  # Actual extracted old/new PROGRAM retirement wrapper.
        assert tokens["cleanup-held"] == 1, (
            "public-hold-only retirement omitted observed pending guardian gate")
        assert len(receipts) == 2
        assert tokens["public-0"] == tokens["public-1"] == 1
        assert tokens["controller-0"] == tokens["controller-1"] == 1
        assert all(hold.is_set() for hold in public_holds)
        ledger.release_pending()
        ledger.release_pending()
        assert tokens["cleanup-held"] == 1
        assert tokens["REQUEST_DELIVERED"] == int(already_released)
        assert tokens["unobserved"] == tokens["duplicate-observation"] == 0
        # A genuinely observed late occurrence and late public hold release
        # immediately, exactly once, still behind the same original intents.
        observe("cleanup-held", 3, "late-cleanup-held")
        observe("public-hold", 4, "late-public-hold")
        assert tokens["late-cleanup-held"] == tokens["late-public-hold"] == 1
        ledger.release_pending()
        assert tokens["late-cleanup-held"] == tokens["late-public-hold"] == 1
    finally:
        loop.close()  # No tasks, FDs, native barriers or real SDK holds allocated.


@pytest.mark.parametrize("when", ["before-release", "after-release"])
def test_late_cleanup_registration(when):
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()
    retained = []

    async def original_close():
        calls["delegate"] += 1
        await gate.wait()
        calls["complete"] += 1

    def create_original():
        retained.append(_repair_register(
            owner, loop.create_task(original_close()), "resource-close"))

    def release():
        gate.set()
        if when == "after-release":
            loop.call_soon(create_original)

    # A retained independent stop forces an actual quiesce yield, so creation
    # after release is observed by the join loop, not after final proof.
    async def independent_stop():
        await asyncio.sleep(0)
        calls["independent-stop"] += 1

    owner.retain_resource("unit-stop", object(), independent_stop,
                          lambda: calls["independent-stop"] == 1)
    owner.release = release
    owner.request()
    if when == "before-release":
        # _begin creates quiesce, this callback registers original close before
        # quiesce's first snapshot, after retirement has already been requested.
        loop.call_soon(create_original)
    try:
        owner.finish(native_retire=lambda: True, verify_native=lambda: True)
        assert len(retained) == 1
        task, = retained
        assert task in owner.tasks and task.done()
        assert task.cancelling() == 0 and not task.cancelled()
        assert calls["delegate"] == calls["complete"] == 1
        assert calls["independent-stop"] == 1 and owner.finalized
    finally:
        _repair_hygiene(loop, owner, [gate])


def test_pending_cleanup_refuses_safe():
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()

    async def original_close():
        calls["delegate"] += 1
        await gate.wait()
        calls["complete"] += 1

    async def start():
        task = _repair_register(owner, loop.create_task(original_close()), "owner-close")
        await asyncio.sleep(0)
        return task

    task = loop.run_until_complete(start())
    # Exhaust the UNIT join allowance, not the real absolute deadline.
    # Thus a false SAFE cannot be hidden behind the independent deadline check.
    owner.remaining = lambda: 0.0
    try:
        owner.finish(native_retire=lambda: True, verify_native=lambda: True)
        assert time.monotonic() < owner.deadline
        assert not owner.finalized, "pending protected cleanup passed all-task proof"
        with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
            owner.prove_safe()
        assert owner.safe_emissions == 0
        assert task in owner.tasks and not task.done() and task.cancelling() == 0
        assert calls["delegate"] == 1 and calls["complete"] == 0
    finally:
        _repair_hygiene(loop, owner, [gate])
    assert task.done() and not task.cancelled() and calls["complete"] == 1
    assert not owner.finalized and owner.safe_emissions == 0


@pytest.mark.parametrize("case", ["scorer", "adapter"])
def test_generic_retirement_roles(case):
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()

    async def body(kind):
        calls[(case, kind)] += 1
        await gate.wait()

    async def start():
        driver = _repair_register(owner, loop.create_task(body("driver")))
        cleanup = _repair_register(
            owner, loop.create_task(body("cleanup")), "scope-drain")
        # Not registered by role, still joined and NEVER proactively cancelled.
        unknown = loop.create_task(body("unclassified"))
        await asyncio.sleep(0)
        return driver, cleanup, unknown

    driver, cleanup, unknown = loop.run_until_complete(start())
    owner.release = gate.set
    try:
        owner.finish(native_retire=lambda: True, verify_native=lambda: True)
        assert driver.cancelled() and driver.cancelling() == 1
        assert cleanup.cancelling() == unknown.cancelling() == 0
        assert all(task.done() and not task.cancelled() for task in (cleanup, unknown))
        assert {driver, cleanup, unknown} <= owner.tasks and owner.finalized
        assert all(calls[(case, kind)] == 1
                   for kind in ("driver", "cleanup", "unclassified"))
    finally:
        _repair_hygiene(loop, owner, [gate], [driver])


def test_generic_retirement_roles_conflict_is_sticky():
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()

    async def original_close():
        await gate.wait()

    task = loop.create_task(original_close())
    owner.retain_task(task)
    try:
        retain_cleanup = getattr(owner, "retain_cleanup", None)
        retain_driver = getattr(owner, "retain_driver", None)
        assert callable(retain_cleanup) and callable(retain_driver), "planned explicit roles"
        retain_cleanup(task, "owner-close")
        try:
            retain_driver(task)
        except Exception:
            pass  # Raising is optional; recording the conflict is mandatory.
        assert owner.primary is not None and owner.errors
        primary = owner.primary
        owner.record_outcome({"ok": True})
        assert owner.primary is primary and owner.outcome["ok"] is False
        assert task in owner.tasks and task.cancelling() == 0
    finally:
        _repair_hygiene(loop, owner, [gate])


def _compat_history_validator(namespace):
    validate = namespace.get("_validate_delivery_history")
    assert callable(validate), "authorized strict EXACT4 history validator"
    return validate


def test_delivery_diagnostic_snapshot():
    namespace = _repair_program_namespace()
    markers = namespace["_MARKERS"]
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()
    scope = SimpleNamespace(agent_task=None, cleanup_task=None)
    actor = SimpleNamespace(retirement=owner, emit=lambda *args: None)
    api = SimpleNamespace(_HOOKS=object(), _close_resource=lambda: None,
                          _rollout=SimpleNamespace(get=lambda: scope))
    probe = _repair_probe(namespace, api=api, actor=actor)
    installed = {}
    probe.install(SimpleNamespace(
        setattr=lambda target, name, value: installed.__setitem__(name, value)))
    outer_errors = []

    async def scenario():
        ready = asyncio.Queue()
        scope.agent_task = owner.retain_task(asyncio.create_task(gate.wait()))
        scope.cleanup_task = owner.retain_task(asyncio.create_task(gate.wait()))

        async def actual_catches():
            for index in range(1, 5):
                ready.put_nowait(index)
                try:
                    target = scope.agent_task if index == 1 else scope.cleanup_task
                    await installed["shield"](target)  # ORIGINAL probe observer.
                except asyncio.CancelledError as error:
                    outer_errors.append(error)  # Same exception must be re-raised.

        task = owner.retain_task(asyncio.create_task(actual_catches()))
        try:
            # The second UNIT delivery models EMPTY, not SDK provenance.
            for index, marker in enumerate((markers[0], None, markers[1], markers[2]), 1):
                assert await ready.get() == index
                accepted = task.cancel() if index == 2 else task.cancel(marker)
                assert accepted
            await task
            return task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    try:
        env = loop.run_until_complete(asyncio.wait_for(scenario(), 2.0))
        notes = probe.delivered
        expected = [
            dict(index=i, marker=marker, join="AGENT" if i == 1 else "CLEANUP",
                 error="CancelledError")
            for i, marker in enumerate(("1", "EMPTY", "2", "3"), 1)]
        assert len(notes) == len(outer_errors) == 4
        assert all(note.error is error for note, error in zip(notes, outer_errors))
        assert [getattr(note, "snapshot", None) for note in notes] == expected
        validate = _compat_history_validator(namespace)
        assert validate(notes, scope=scope, env=env) is None
        error = asyncio.CancelledError("PRIVATE_GOLD_OTHER")
        extra = SimpleNamespace(
            scope=scope, task=env, target=scope.cleanup_task, error=error,
            snapshot=namespace["_delivery_snapshot"](
                2, error, scope.cleanup_task,
                agent=scope.agent_task, cleanup=scope.cleanup_task))
        for rejected in (notes + [extra], [notes[1], notes[0], *notes[2:]],
                         [notes[0], extra, *notes[2:]], [notes[0], *notes[2:]]):
            with pytest.raises(AssertionError):
                validate(rejected, scope=scope, env=env)
        notes[0].error.args = ("PRIVATE_GOLD_MUTATED_ARGS",)
        assert [note.snapshot for note in notes] == expected
        with pytest.raises(AssertionError):
            validate(notes, scope=scope, env=env)  # Snapshots never replace current proof.
        diagnostic = namespace.get("_delivery_diagnostic")
        assert callable(diagnostic), "planned bounded delivery diagnostic"
        report = diagnostic(notes, agent=scope.agent_task, cleanup=scope.cleanup_task)
        assert report["notes"][0]["snapshot"] == expected[0]
        assert report["notes"][0]["current_marker"] == "OTHER"
        assert report["total"] == 4 and report["omitted"] == 0
    finally:
        _repair_hygiene(loop, owner, [gate])


def _repair_safe_json(report, canaries):
    encoded = json.dumps(report, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= 8192
    assert all(canary.encode("utf-8") not in encoded for canary in canaries)
    return report


@pytest.mark.parametrize("kind", ["delivery", "retirement"])
def test_diagnostic_privacy_bounds(kind):
    canaries = ["PRIVATE_GOLD_TOKEN", "PRIVATE_TASK_NAME", "PRIVATE_SOURCE_PATH",
                "PRIVATE_LOCAL_VALUE", "PRIVATE_FUNCTION_NAME", "PRIVATE_EXCEPTION_CLASS"]
    agent, cleanup = object(), object()

    class PRIVATE_EXCEPTION_CLASS(Exception):
        pass

    errors = [asyncio.CancelledError(canaries[0] * 2000),
              PRIVATE_EXCEPTION_CLASS(canaries[3] * 2000)]
    if kind == "delivery":
        namespace = _repair_program_namespace()
        capture, diagnostic = (namespace.get(name) for name in (
            "_delivery_snapshot", "_delivery_diagnostic"))
        assert callable(capture) and callable(diagnostic), "planned bounded delivery diagnostics"
        notes = [
            SimpleNamespace(
                error=errors[i % 2], target=object(),
                snapshot=capture(i + 1, errors[i % 2], object(), agent=agent, cleanup=cleanup))
            for i in range(40)]
        report = _repair_safe_json(
            diagnostic(notes, agent=agent, cleanup=cleanup), canaries)
        assert set(report) == {"notes", "total", "omitted"}
        assert len(report["notes"]) == 32
        assert report["total"] == 40 and report["omitted"] == 8
        for index, note in enumerate(report["notes"], 1):
            assert set(note) == {"snapshot", "current_marker"}
            assert note["snapshot"] == dict(
                index=index, marker="OTHER", join="OTHER",
                error="CancelledError" if index % 2 else "OTHER")
            assert note["current_marker"] == "OTHER"
        return

    loop, owner, calls = _repair_case()
    gate = asyncio.Event()
    allowed_stages = {
        "async", "release", "task-drain", "native", "native-proof", "resource-proof",
        "framework", "executor", "undo", "physical-proof", "task", "disable",
        "start-async", "join-async", "worker-join", "finish", "OTHER"}
    # Real suspended coroutine, hostile co_filename/co_name/task name/locals.
    source = (
        "async def PRIVATE_FUNCTION_NAME():\n"
        "    local_value = secret\n"
        "    await gate.wait()\n")
    worker_namespace = dict(gate=gate, secret=canaries[3])
    exec(compile(source, "/PRIVATE_SOURCE_PATH/secret.py", "exec"), worker_namespace)
    tasks = []

    async def start():
        for index in range(40):
            task = loop.create_task(worker_namespace["PRIVATE_FUNCTION_NAME"]())
            task.set_name(f"PRIVATE_TASK_NAME-{index}")
            tasks.append(task)
            if index % 3 == 0:
                _repair_register(owner, task)
            elif index % 3 == 1:
                _repair_register(owner, task, "resource-close")
            else:
                owner.retain_task(task)  # Explicitly unclassified, not driver.
        await asyncio.sleep(0)

    loop.run_until_complete(start())
    for index in range(40):
        owner.fail(f"PRIVATE_GOLD_TOKEN-{index}", errors[index % 2])
    try:
        diagnostic = getattr(owner, "diagnostic", None)
        assert callable(diagnostic), "planned bounded retirement diagnostic"
        report = _repair_safe_json(diagnostic(), canaries)
        assert set(report) == {
            "tasks", "tasks_total", "tasks_omitted", "pending_tasks",
            "stages", "stages_total", "stages_omitted"}
        assert len(report["tasks"]) == 32
        assert report["tasks_total"] == report["pending_tasks"] == 40
        assert report["tasks_omitted"] == 8
        assert len(report["stages"]) == 16
        assert report["stages_total"] == 40 and report["stages_omitted"] == 24
        assert set(report["stages"]) <= allowed_stages
        roles = Counter(task["role"] for task in report["tasks"])
        assert all(roles[role] <= total for role, total in (
            ("driver", 14), ("cleanup", 13), ("unclassified", 13)))
        for task in report["tasks"]:
            assert set(task) == {"role", "done", "cancelled", "source"}
            assert task["role"] in {"driver", "cleanup", "unclassified"}
            assert task["done"] is task["cancelled"] is False
            assert task["source"] == {"file": "OTHER", "function": "OTHER"}
        assert not owner.requested.is_set()  # Diagnostic has no retirement side effect.
    finally:
        _repair_hygiene(loop, owner, [gate])


def _compat_history_case(namespace):
    """Actual unit task identities, synthetic error inputs, NEVER SDK evidence."""
    loop, owner, calls = _repair_case()
    gate = asyncio.Event()
    agent = owner.retain_task(loop.create_task(gate.wait()))
    cleanup = owner.retain_task(loop.create_task(gate.wait()))
    env = owner.retain_task(loop.create_task(gate.wait()))
    scope = SimpleNamespace(agent_task=agent, cleanup_task=cleanup)
    markers = namespace["_MARKERS"]
    errors = [asyncio.CancelledError(markers[0]), asyncio.CancelledError(),
              asyncio.CancelledError(markers[1]), asyncio.CancelledError(markers[2])]
    notes = [SimpleNamespace(
        scope=scope, task=env, target=agent if i == 0 else cleanup, error=error,
        snapshot=namespace["_delivery_snapshot"](
            i + 1, error, agent if i == 0 else cleanup, agent=agent, cleanup=cleanup))
        for i, error in enumerate(errors)]
    return loop, owner, gate, scope, env, notes


def test_exact_four_history_accepts():
    namespace = _repair_program_namespace()
    assert namespace["_MARKERS"] == tuple(
        f"sdk PROGRAM eval cancellation {index}" for index in (1, 2, 3))
    validate = _compat_history_validator(namespace)
    loop, owner, gate, scope, env, notes = _compat_history_case(namespace)
    try:
        originals = tuple(note.error for note in notes)
        assert validate(notes, scope=scope, env=env) is None
        assert tuple(note.error for note in notes) == originals
        assert all(note.error is original for note, original in zip(notes, originals))
        assert [note.error.args for note in notes] == [
            (namespace["_MARKERS"][0],), (), (namespace["_MARKERS"][1],),
            (namespace["_MARKERS"][2],)]
        assert [note.snapshot["marker"] for note in notes] == ["1", "EMPTY", "2", "3"]
    finally:
        _repair_hygiene(loop, owner, [gate])


_EXACT_FOUR_REJECTIONS = (
    [("missing", i) for i in range(4)]
    + [(kind, i) for kind in ("extra-empty", "extra-marked", "extra-other") for i in range(5)]
    + [("swap", i) for i in range(3)]
    + [(kind, i) for kind in ("wrong-scope", "wrong-env", "wrong-exception",
                              "exception-subclass", "current-mutation",
                              "captured-marker", "captured-join", "captured-error")
       for i in range(4)]
    + [("different-cleanup", i) for i in range(1, 4)]
    + [("wrong-agent", 0)]
    + [(kind, i) for kind in ("none-arg", "empty-string", "unknown-string",
                              "two-args", "nested-args", "string-subclass") for i in range(4)]
)


@pytest.mark.parametrize("variant,index", _EXACT_FOUR_REJECTIONS)
def test_exact_four_history_rejects_variants(variant, index):
    namespace = _repair_program_namespace()
    validate = _compat_history_validator(namespace)
    loop, owner, gate, scope, env, notes = _compat_history_case(namespace)
    original_records = tuple(notes)

    class CancelSubclass(asyncio.CancelledError):
        pass

    class MarkerSubclass(str):
        pass

    try:
        if variant == "missing":
            del notes[index]
        elif variant.startswith("extra-"):
            error = (asyncio.CancelledError() if variant == "extra-empty" else
                     asyncio.CancelledError(namespace["_MARKERS"][1]) if
                     variant == "extra-marked" else asyncio.CancelledError("PRIVATE_EXTRA"))
            notes.insert(index, SimpleNamespace(
                scope=scope, task=env, target=scope.cleanup_task, error=error,
                snapshot=namespace["_delivery_snapshot"](
                    5, error, scope.cleanup_task,
                    agent=scope.agent_task, cleanup=scope.cleanup_task)))
        elif variant == "swap":
            notes[index], notes[index + 1] = notes[index + 1], notes[index]
        elif variant == "wrong-scope":
            notes[index].scope = SimpleNamespace(
                agent_task=scope.agent_task, cleanup_task=scope.cleanup_task)
        elif variant == "wrong-env":
            notes[index].task = scope.agent_task
        elif variant in ("different-cleanup", "wrong-agent"):
            notes[index].target = env
            notes[index].snapshot = namespace["_delivery_snapshot"](
                index + 1, notes[index].error, env,
                agent=scope.agent_task, cleanup=scope.cleanup_task)
        elif variant in ("wrong-exception", "exception-subclass"):
            error_type = ValueError if variant == "wrong-exception" else CancelSubclass
            notes[index].error = error_type(*notes[index].error.args)
            notes[index].snapshot = namespace["_delivery_snapshot"](
                index + 1, notes[index].error, notes[index].target,
                agent=scope.agent_task, cleanup=scope.cleanup_task)
        elif variant.startswith("captured-"):
            snapshot = dict(notes[index].snapshot)
            field = variant.removeprefix("captured-")
            snapshot[field] = "OTHER"
            notes[index].snapshot = snapshot
        else:
            args = {
                "none-arg": (None,), "empty-string": ("",),
                "unknown-string": ("PRIVATE_UNKNOWN",),
                "two-args": (namespace["_MARKERS"][0], "PRIVATE_SECOND"),
                "nested-args": ((namespace["_MARKERS"][0],),),
                "string-subclass": (MarkerSubclass(
                    namespace["_MARKERS"][0 if index < 2 else index - 1]),),
                "current-mutation": ("PRIVATE_MUTATED_AFTER_CAPTURE",),
            }[variant]
            notes[index].error.args = args
            if variant != "current-mutation":
                notes[index].snapshot = namespace["_delivery_snapshot"](
                    index + 1, notes[index].error, notes[index].target,
                    agent=scope.agent_task, cleanup=scope.cleanup_task)
        errors_before = tuple((note.error, note.error.args) for note in notes)
        with pytest.raises(AssertionError):
            validate(notes, scope=scope, env=env)
        assert len(notes) == len(errors_before)  # Validator must not filter the input.
        assert all(note.error is error and note.error.args == args
                   for note, (error, args) in zip(notes, errors_before))
        assert all(record.error is not None for record in original_records)
    finally:
        _repair_hygiene(loop, owner, [gate])


@pytest.mark.parametrize("kind", [
    "empty", "none", "empty-string", "unknown", "tuple-arg", "wrong-exception",
    "cancel-subclass", "known-string-subclass"])
def test_empty_is_not_other(kind):
    namespace = _repair_program_namespace()
    capture = namespace["_delivery_snapshot"]
    agent, cleanup = object(), object()

    class CancelSubclass(asyncio.CancelledError):
        pass

    class MarkerSubclass(str):
        pass

    errors = {
        "empty": asyncio.CancelledError(), "none": asyncio.CancelledError(None),
        "empty-string": asyncio.CancelledError(""),
        "unknown": asyncio.CancelledError("PRIVATE_UNKNOWN"),
        "tuple-arg": asyncio.CancelledError(()), "wrong-exception": ValueError(),
        "cancel-subclass": CancelSubclass(),
        "known-string-subclass": asyncio.CancelledError(MarkerSubclass(namespace["_MARKERS"][0])),
    }
    error = errors[kind]
    snapshot = capture(2, error, cleanup, agent=agent, cleanup=cleanup)
    expected = "EMPTY" if kind == "empty" else "OTHER"
    assert snapshot["marker"] == expected
    with pytest.raises(TypeError):
        snapshot["marker"] = "3"
    error.args = ("PRIVATE_AFTER_CAPTURE",)
    assert snapshot["marker"] == expected
    assert capture(2, error, cleanup, agent=agent, cleanup=cleanup)["marker"] == "OTHER"
    _repair_safe_json(dict(snapshot), ["PRIVATE_UNKNOWN", "PRIVATE_AFTER_CAPTURE"])


def test_empty_is_not_other_privacy_bounds():
    namespace = _repair_program_namespace()
    agent, cleanup = object(), object()
    notes = []
    secret = "PRIVATE_EMPTY_DIAGNOSTIC_SECRET"
    for i in range(40):
        error = asyncio.CancelledError() if i % 2 == 0 else asyncio.CancelledError(secret * 2000)
        snapshot = namespace["_delivery_snapshot"](
            i + 1, error, cleanup, agent=agent, cleanup=cleanup)
        notes.append(SimpleNamespace(error=error, target=cleanup, snapshot=snapshot))
        error.args = (secret,)  # Captured EMPTY must not be inferred from current OTHER.
    report = _repair_safe_json(
        namespace["_delivery_diagnostic"](notes, agent=agent, cleanup=cleanup), [secret])
    assert report["total"] == 40 and report["omitted"] == 8 and len(report["notes"]) == 32
    assert [row["snapshot"]["marker"] for row in report["notes"]] == ["EMPTY", "OTHER"] * 16
    assert all(row["current_marker"] == "OTHER" for row in report["notes"])


def test_exact_four_history_accepts_waits_for_empty_before_marker_two():
    namespace = _repair_program_namespace()
    loop, owner, gate, scope, env, notes = _compat_history_case(namespace)
    queue = asyncio.Queue()
    actor = SimpleNamespace(retirement=owner, emit=lambda kind: queue.put_nowait(dict(kind=kind)))

    async def next_event(predicate):
        while True:
            item = await queue.get()
            if predicate(item):
                return item

    actor.next_event = next_event
    api = SimpleNamespace(_HOOKS=object(), _close_resource=lambda: None,
                          _rollout=SimpleNamespace(get=lambda: scope))
    probe = _repair_probe(namespace, api=api, actor=actor)
    probe.caller = env
    probe.env_tasks[id(scope)] = env
    probe.delivered = notes[:1]

    async def scenario():
        wait_empty = getattr(probe, "_wait_empty_cleanup", None)
        assert callable(wait_empty), "planned explicit EMPTY-before-marker2 wait"
        waiter = owner.retain_task(loop.create_task(wait_empty(scope)))
        await asyncio.sleep(0)
        assert not waiter.done(), "marker2 could proceed without EMPTY"
        probe.delivered.append(notes[1])
        queue.put_nowait(dict(kind="SDK_CANCEL_PROGRESS"))
        await waiter
        assert len(probe.delivered) == 2
        assert probe.delivered[1].error.args == ()

    try:
        loop.run_until_complete(asyncio.wait_for(scenario(), 2.0))
    finally:
        _repair_hygiene(loop, owner, [gate])


def test_exact_four_history_accepts_source_wait_and_fresh_final_recheck():
    path = Path(__file__).with_name("test_owned_sql_sdk_program_cancellation.py")
    tree = ast.parse(path.read_text())
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkProgramCancellation"]
    qualify, = [node for node in cls.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "qualify"]
    issue_loop, = [node for node in ast.walk(qualify) if isinstance(node, ast.For)
                   and ast.dump(node.iter) == ast.dump(
                       ast.parse("enumerate(_MARKERS)", mode="eval").body)]
    cancel, = [node for node in ast.walk(cls) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr == "cancel"]
    assert cancel in list(ast.walk(issue_loop))
    assert ast.dump(cancel) == ast.dump(ast.parse("caller.cancel(marker)", mode="eval").body), (
        "exactly 3 marked caller requests, NEVER inject EMPTY/direct Env cancellation")
    expected_counts = ast.parse(
        "caller.cancelling() == len(self.issued) == 3", mode="eval").body
    assert any(isinstance(node, ast.Assert) and ast.dump(node.test) == ast.dump(expected_counts)
               for node in ast.walk(qualify)), "3 requests is distinct from 4 target deliveries"
    first_branch, = [node for node in ast.walk(issue_loop) if isinstance(node, ast.If)
                     and ast.dump(node.test) == ast.dump(ast.parse("index == 0", mode="eval").body)]
    empty_waits = [node for node in ast.walk(first_branch) if isinstance(node, ast.Await)
                   and isinstance(node.value, ast.Call)
                   and isinstance(node.value.func, ast.Attribute)
                   and node.value.func.attr == "_wait_empty_cleanup"]
    assert len(empty_waits) == 1, "wait for exact EMPTY before issuing marker2"
    delivered_hit, = [node for node in ast.walk(first_branch) if isinstance(node, ast.Await)
                      and isinstance(node.value, ast.Call)
                      and any(isinstance(arg, ast.Constant) and arg.value == "cleanup-held"
                              for arg in node.value.args)]
    assert empty_waits[0].lineno > delivered_hit.lineno
    drain, = [node for node in ast.walk(qualify) if isinstance(node, ast.Await)
              and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "until"
              and len(node.value.args) == 1
              and ast.dump(node.value.args[0]) == ast.dump(ast.parse("caller.done", mode="eval").body)]
    validations = sorted(
        [node for node in ast.walk(qualify) if isinstance(node, ast.Call)
         and isinstance(node.func, ast.Name) and node.func.id == "_validate_delivery_history"],
        key=lambda node: node.lineno)
    assert len(validations) == 2, "strict validation before release AND after complete caller drain"
    assert validations[0].lineno < drain.lineno < validations[1].lineno
    for call, lower in ((validations[0], 0), (validations[1], drain.lineno)):
        assert len(call.args) == 1
        value = call.args[0]
        if isinstance(value, ast.Name):
            assignment, = [node for node in ast.walk(qualify) if isinstance(node, ast.Assign)
                            and lower < node.lineno < call.lineno
                            and any(isinstance(target, ast.Name) and target.id == value.id
                                    for target in node.targets)]
            value = assignment.value
        assert isinstance(value, ast.ListComp), "fresh complete observations, not stale pre-drain list"
        generator, = value.generators
        assert isinstance(generator.target, ast.Name)
        assert ast.dump(generator.iter) == ast.dump(ast.parse("self.delivered", mode="eval").body)
        assert len(generator.ifs) <= 1
        for condition in generator.ifs:
            assert ast.dump(condition) == ast.dump(ast.parse(
                f"{generator.target.id}.scope is target", mode="eval").body), (
                    "scope identity only, never filter EMPTY/OTHER/extras")


def _compat_guest_tree():
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    tree = ast.parse(path.read_text())
    assignment, = [node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                            for target in node.targets)]
    return ast.parse(ast.literal_eval(assignment.value))


def test_cooperative_cutoff_preserves_pending_api():
    loop, owner, calls, end = _compat_case(expired_cutoff=True)
    gate = asyncio.Event()

    async def original_public_close():
        calls["delegate"] += 1
        await gate.wait()
        calls["public-complete"] += 1

    async def start():
        task = owner.retain_cleanup(loop.create_task(original_public_close()), "owner-close")
        await asyncio.sleep(0)
        return task

    task = loop.run_until_complete(start())
    owner.cooperative_cutoff = end - 3.75

    def native():
        assert not loop.is_running() and not owner.loop_drive_lock.locked()
        assert not owner.lock.locked() and task in owner.tasks
        calls["native"] += 1
        # UNIT post-fallback join allowance exhausted, absolute deadline still
        # live. This does not resolve/cancel the original pending public API.
        owner.remaining = lambda: 0.0
        return True

    try:
        cooperate = getattr(owner, "_cooperate", None)
        assert callable(cooperate), "planned bounded cooperative drive"
        assert owner.cooperative_cutoff < time.monotonic() < owner.deadline
        assert owner.cooperative_cutoff == end - 3.75 and owner.deadline == end - 0.25
        owner.request()
        with owner.loop_drive_lock:
            owner._drive(cooperate())
        assert not task.done() and task.cancelling() == 0 and calls["native"] == 0
        owner.finish(native_retire=native, verify_native=lambda: True)
        assert calls["native"] == 1 and time.monotonic() < owner.deadline
        assert not owner.finalized and task in owner.tasks and not task.done()
        assert task.cancelling() == 0 and calls["delegate"] == 1
        with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
            owner.prove_safe()
        assert owner.safe_emissions == 0 and calls["public-complete"] == 0
    finally:
        _repair_hygiene(loop, owner, [gate])
    assert task.done() and not task.cancelled() and calls["public-complete"] == 1
    assert not owner.finalized and owner.safe_emissions == 0


def test_cooperative_cutoff_uses_absolute_host_bounds():
    loop, owner, calls, end = _compat_case()
    try:
        assert "cooperative_cutoff" in inspect.signature(type(owner)).parameters
        assert owner.cooperative_cutoff == end - 3.75 and owner.deadline == end - 0.25
        tree = _compat_guest_tree()
        constructor, = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == "_SdkRetirement"]
        arguments = {kw.arg: kw.value for kw in constructor.keywords}
        assert ast.dump(arguments["cooperative_cutoff"]) == ast.dump(
            ast.parse("END - 3.75", mode="eval").body), "not now + another relative allowance"
        assert ast.dump(arguments["deadline"]) == ast.dump(
            ast.parse("END - 0.25", mode="eval").body)
        assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "remaining" and node.args
                   and ast.dump(node.args[0]) == ast.dump(
                       ast.parse("END - 3.5", mode="eval").body) for node in ast.walk(tree))
    finally:
        _repair_hygiene(loop, owner, [])


@pytest.mark.parametrize("physically_resolved", [False, True])
def test_fallback_attempts_all_after_error(physically_resolved):
    loop, owner, calls, end = _compat_case()
    original = AssertionError("original unit decision failure")
    native_error = AssertionError("first native category failure")
    owner.fail("acceptance", original)
    retired = set()
    categories = ("slot", "controller", "reader", "fd", "resource")

    def attempt(stage, index):
        calls[(stage, index)] += 1
        if (stage, index) != ("slot", 0) or physically_resolved:
            retired.add((stage, index))
        if (stage, index) == ("slot", 0):
            raise native_error

    def native():
        calls["native"] += 1
        assert not loop.is_running() and not owner.loop_drive_lock.locked()
        for stage in categories:
            owner.attempt_each(stage, range(2), lambda index, stage=stage: attempt(stage, index))

    try:
        owner.finish(native_retire=native, verify_native=lambda: len(retired) == 10)
        assert calls["native"] == 1
        assert all(calls[(stage, index)] == 1 for stage in categories for index in range(2))
        assert owner.primary is original and any(error is native_error for _, error in owner.errors)
        assert owner.outcome["ok"] is False and owner.finalized is physically_resolved
        assert owner.stages["framework"] == owner.stages["executor"] == owner.stages["undo"] == 1
        if not physically_resolved:
            with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
                owner.prove_safe()
            assert owner.safe_emissions == 0
    finally:
        _repair_hygiene(loop, owner, [])


@pytest.mark.parametrize("when", ["before", "during"])
@pytest.mark.parametrize("native_error", [False, True])
def test_fallback_request_breaks_cooperative_wait(when, native_error):
    loop, owner, calls, end = _compat_case()
    gate = asyncio.Event()
    cooperative_entered, native_entered = threading.Event(), threading.Event()
    supervisor_done = threading.Event()
    cleanup_lock = threading.Lock()
    main = threading.current_thread()
    faults, snapshots, drive_threads = [], [], []
    fault = AssertionError("unit fallback slot error")
    thread = None
    task = None
    original_drive = loop.run_until_complete

    def observed_drive(awaitable):
        drive_threads.append(threading.current_thread())
        assert threading.current_thread() is main, "supervisor must NEVER drive LOOP"
        return original_drive(awaitable)

    loop.run_until_complete = observed_drive

    async def original_public_close():
        calls["delegate"] += 1
        await gate.wait()
        calls["public-complete"] += 1

    def supervisor(notify):
        try:
            if when == "during":
                assert cooperative_entered.wait(1.0)
            notify()
            notify()  # Repeated notification must not create a second claim.
            calls["notifications"] += 2
            assert native_entered.wait(1.0)
            assert not loop.is_running()
            assert _compat_free_locks(owner, cleanup_lock) == (True, True, True)
        except BaseException as error:
            faults.append(error)
        finally:
            supervisor_done.set()

    def operation(stage, index):
        calls[(stage, index)] += 1
        if native_error and (stage, index) == ("slot", 0):
            raise fault

    def native():
        assert threading.current_thread() is main and not loop.is_running()
        snapshots.append(_compat_free_locks(owner, cleanup_lock))
        with cleanup_lock:  # Short native claim, no lock across handshake wait.
            calls["native-claim"] += 1
        native_entered.set()
        assert supervisor_done.wait(1.0), "native handoff waited while holding drive/state lock"
        thread.join(1.0)  # Genuine unit supervisor join, no lock across waiting.
        calls["native-join"] += 1
        assert not thread.is_alive()
        for stage in ("slot", "controller", "reader", "fd", "resource"):
            owner.attempt_each(stage, range(2), lambda i, stage=stage: operation(stage, i))
        gate.set()  # Original unit gate, no replacement close/ACK or forced revoke.
        snapshots.append(_compat_free_locks(owner, cleanup_lock))
        return True

    try:
        cooperate = getattr(owner, "_cooperate", None)
        notify = getattr(owner, "request_fallback", None)
        assert callable(cooperate) and callable(notify), "planned notification/cooperative APIs"
        assert isinstance(owner.fallback_requested, threading.Event)

        async def observed_cooperate():
            cooperative_entered.set()
            return await cooperate()

        owner._cooperate = observed_cooperate
        task = owner.retain_cleanup(loop.create_task(original_public_close()), "owner-close")
        if when == "before":
            notify()
            assert owner.fallback_requested.is_set() and calls["native-claim"] == 0
        thread = threading.Thread(target=supervisor, args=(notify,))
        thread.start()
        owner.finish(native_retire=native, verify_native=lambda: True)
        thread.join(1.0)
        assert not thread.is_alive() and not faults
        assert owner.fallback_requested.is_set() and calls["notifications"] == 2
        assert calls["native-claim"] == owner.finish_claims == owner.stages["async"] == 1
        assert calls["native-join"] == 1
        assert snapshots == [(True, True, True)] * 2
        assert all(thread_ is main for thread_ in drive_threads)
        assert all(calls[(stage, i)] == 1
                   for stage in ("slot", "controller", "reader", "fd", "resource")
                   for i in range(2))
        assert task in owner.tasks and task.done() and not task.cancelled()
        assert task.cancelling() == 0 and calls["delegate"] == calls["public-complete"] == 1
        assert owner.finalized and owner.primary is (fault if native_error else None)
    finally:
        cooperative_entered.set()
        native_entered.set()
        supervisor_done.set()
        if thread is not None:
            thread.join(1.0)
        _repair_hygiene(loop, owner, [gate])


def test_fallback_request_breaks_cooperative_wait_source_supervisor_notification():
    tree = _compat_guest_tree()
    host, = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name == "host_main"]
    watchdog, = [node for node in host.body if isinstance(node, ast.FunctionDef)
                 and node.name == "watchdog"]
    notifications = sorted(
        [node for node in ast.walk(watchdog) if isinstance(node, ast.Call)
         and isinstance(node.func, ast.Attribute) and node.func.attr == "request_fallback"],
        key=lambda node: node.lineno)
    native_calls = sorted(
        [node for node in ast.walk(watchdog) if isinstance(node, ast.Call)
         and isinstance(node.func, ast.Name) and node.func.id == "cleanup"],
        key=lambda node: node.lineno)
    assert len(notifications) == 2, "early wake race AND ordinary SDK watchdog must notify"
    assert len(native_calls) >= 2
    assert all(notify.lineno < native.lineno
               for notify, native in zip(notifications, native_calls[:2]))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in ("run_until_complete", "run_forever")
                   for node in ast.walk(watchdog))


def _handoff_extract(parent_name, names, namespace):
    """Compile ONLY unchanged nested definitions when parent runs these tests."""
    tree = _compat_guest_tree()
    parent, = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == parent_name]
    selected = []
    for name in names:
        node, = [node for node in parent.body if isinstance(node, ast.FunctionDef)
                 and node.name == name]
        selected.append(node)
    # No AST rewriting, branch copies, or simulated watchdog control flow.
    exec(compile(ast.Module(body=selected, type_ignores=[]),
                 "EXTRACTED_" + parent_name, "exec"), namespace)
    return {name: namespace[name] for name in names}


def _handoff_require_api(owner):
    names = ("request_native_handoff", "wait_native_handoff",
             "publish_native_handoff", "supervisor_native_finished", "close_native_handoff")
    assert all(callable(getattr(owner, name, None)) for name in names), (
        "planned explicit stopped-LOOP handoff API")


def _handoff_lock_snapshot(owner, cleanup_lock, end):
    # Drive lock is deliberately held by MAIN during the intended-RED probe.
    # Other callers may briefly hold short locks; use the SAME absolute end,
    # never a fresh relative grace, to distinguish contention from a held wait.
    locks = [owner.loop_drive_lock, owner.lock, cleanup_lock]
    locks.extend(value for name, value in vars(owner).items()
                 if "handoff" in name and hasattr(value, "acquire") and hasattr(value, "release"))
    unique, values = set(), []
    for index, lock in enumerate(locks):
        if id(lock) in unique:
            continue
        unique.add(id(lock))
        owned = getattr(lock, "_is_owned", lambda: False)()
        acquired = False if owned else (lock.acquire(blocking=False) if index == 0 else
                    lock.acquire(timeout=max(0.0, end - 0.25 - time.monotonic())))
        values.append(acquired)
        if acquired:
            lock.release()
    return tuple(values)


def _handoff_native_case(loop, owner, calls, end):
    """Original native single-claim/attempt/proof code, mock kernel/resources."""
    namespace = dict(
        END=end, LOOP=loop, time=time, threading=threading,
        PHASE="sdk-retire-two-slot-verification", sdk_resources=owner,
        sdk_watchdog_race=None, cleanup_lock=threading.Lock(), spawn_lock=threading.Lock(),
        stopping=threading.Event(), native_retained=[], native_fds=set(),
        native_objects=[], native_endpoints=[], native_entries=[], native_fenced=[False, False],
        slots=[], owners=[], owner=None)
    attempts, closed, waits = [], set(), []

    class ClaimEvent(threading.Event):
        def set(self):
            calls["native-claims"] += 1
            super().set()

    class DoneEvent(threading.Event):
        def wait(self, timeout=None):
            waits.append((loop.is_running(),
                          _handoff_lock_snapshot(owner, namespace["cleanup_lock"], end)))
            return super().wait(timeout)

    namespace.update(native_started=ClaimEvent(), native_done=DoneEvent())

    def thread_stub(kind):
        actual = SimpleNamespace(joined=False)

        def join(timeout=None):
            calls[kind] += 1
            actual.joined = True
        actual.join, actual.is_alive = join, lambda: not actual.joined
        return actual

    def stream():
        actual = SimpleNamespace(closed=False)
        actual.close = lambda: setattr(actual, "closed", True)
        return actual

    entries = []
    for index in range(2):
        process = SimpleNamespace(
            pid=900 + index, returncode=0, _creator_waited=False,
            _creator_ambiguous=False, stdin=stream(), stdout=stream(), stderr=stream())

        def wait(timeout=None, process=process):
            calls["creator-waits"] += 1
            process._creator_waited = True
            return 0
        process.wait, process.poll = wait, lambda: 0
        actual = SimpleNamespace(
            _lock=threading.RLock(), _retained=threading.Event(),
            _thread=thread_stub("controller-joins"), _resources=[], _endpoints=[],
            _host_read=None, _seal_lock_fd=None, _children=[process])
        namespace["owners"].append(actual)
        entries.append(dict(process=process, registry=actual._children))
        safe = threading.Event()
        safe.set()  # DECLARED fake nested guardian proof, not an actor ACK.
        namespace["slots"].append(dict(
            invocation=actual, process=process, safe=safe,
            safety_w=200 + 5 * index, reader_stop_w=201 + 5 * index,
            reader=thread_stub("reader-joins"), fds=list(range(200 + 5 * index, 205 + 5 * index))))

    def fstat(fd):
        if fd in closed:
            raise OSError(9, "mock closed descriptor")
        return object()

    owner.physical_probe = SimpleNamespace(
        note_native_attempt=lambda stage, actual: attempts.append((stage, actual)),
        after_slot_safe=lambda slot: None)
    namespace.update(
        trace=SimpleNamespace(lock=threading.Lock(), entries=entries),
        release_sdk_controllers=lambda: calls.update(["native-controller-release"]),
        os=SimpleNamespace(write=lambda fd, data: len(data), close=closed.add, fstat=fstat))
    _handoff_extract("host_main",
                     ("sdk_native_proof", "sdk_native_cleanup", "cleanup"), namespace)
    return namespace, attempts, closed, waits


def _handoff_watchdog(namespace, owner, calls, end, *, early, select_gate=None):
    """Select/wake FD/race callbacks are inert fakes; watchdog AST is ORIGINAL."""
    race = SimpleNamespace(fds=(301, 302), reads=0)

    def read_fault(deadline):
        assert deadline == end - 3.75
        calls["early-read"] += 1
        race.reads += 1
    race.read_fault = read_fault
    # Existing dedicated early-race tests retain the real race instrumentation.
    # These inert callbacks do not publish readiness or authorize native work.
    race.native_enter = lambda: object()
    race.native_claim = lambda call, claimed: None
    race.native_exit = lambda call, proof: None
    race.join_supervisor_native = lambda: None

    def select(inputs, writes, errors, timeout):
        calls["watchdog-select"] += 1
        if select_gate is not None:
            assert select_gate.wait(max(0.0, end - 3.5 - time.monotonic()))
        return ([301] if early else [], [], [])

    namespace.update(
        sdk_watchdog_race=race if early else None, sdk_resources=owner,
        done_r=303, finished=threading.Event(), remaining=lambda deadline: max(
            0.0, deadline - time.monotonic()), select=SimpleNamespace(select=select),
        report=lambda result, code: calls.update(["mock-report"]))
    # Bind the actual decoded guest dependency in this UNIT namespace only.
    assert namespace["END"] == end
    assert namespace["PHASE"] == "sdk-retire-two-slot-verification"
    diagnostic_packets = []
    diagnostic_clock = time.monotonic_ns

    def diagnostic_write(fd, raw):
        diagnostic_packets.append((fd, raw))
        return len(raw)

    namespace.update(
        MODE="host", json=json, _boundary_original_ready=True,
        _boundary_original_clock=diagnostic_clock,
        _boundary_original_write=diagnostic_write,
        _handoff_host_budget_packets=diagnostic_packets)
    diagnostic, = [
        node for node in _compat_guest_tree().body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_host_budget_diagnostic"]
    exec(compile(ast.Module(body=[diagnostic], type_ignores=[]),
                 "EXTRACTED_host_budget_diagnostic", "exec"), namespace)
    return _handoff_extract("host_main", ("watchdog",), namespace)["watchdog"]


def _handoff_run_actual_watchdog(*, early, when, native_error, pending_api=False):
    loop, owner, calls, end = _compat_case()
    gate = asyncio.Event()
    suspended, decision = threading.Event(), threading.Event()
    ready, phase_done, phase_closed = threading.Event(), threading.Event(), threading.Event()
    entries, faults, timeline = [], [], []
    main = threading.current_thread()
    supervisor = None
    task = None
    fault = AssertionError("mock native cleanup boundary failure")
    namespace, attempts, closed, waits = _handoff_native_case(loop, owner, calls, end)
    native = namespace["sdk_native_cleanup"]
    original_drive, original_cooperate = loop.run_until_complete, owner._cooperate

    async def original_public_close():
        calls["public-delegate"] += 1
        await gate.wait()
        calls["public-complete"] += 1

    def release_original():
        if not gate.is_set():
            gate.set()
            calls["original-gate-release"] += 1

    def native_entry():
        row = dict(supervisor=threading.current_thread() is supervisor,
                   ready=ready.is_set(), running=loop.is_running(),
                   locks=_handoff_lock_snapshot(owner, namespace["cleanup_lock"], end))
        entries.append(row)
        timeline.append("supervisor-native" if row["supervisor"] else "main-native")
        try:
            proof = native()  # ORIGINAL claim, attempts and duplicate-wait path.
            if native_error and row["supervisor"]:
                # Fault after actual attempts tests the ORIGINAL watchdog except
                # and future unconditional completion finally, not a fake branch.
                raise fault
            return proof
        finally:
            if row["supervisor"]:
                calls["supervisor-native-return"] += 1
            # Old source must actually run its destructive mock-native body
            # BEFORE MAIN leaves the probe gate, not merely touch an observer.
            decision.set()
            if not pending_api:
                loop.call_soon_threadsafe(release_original)

    namespace["sdk_native_cleanup"] = native_entry
    watchdog = _handoff_watchdog(namespace, owner, calls, end,
                                 early=early, select_gate=suspended)

    # Observation ONLY: no missing methods are supplied to today's class.
    for name in ("wait_native_handoff", "publish_native_handoff",
                 "supervisor_native_finished", "close_native_handoff"):
        method = getattr(owner, name, None)
        if not callable(method):
            continue

        def observed(*args, name=name, method=method, **kwargs):
            if name == "wait_native_handoff":
                assert ((args == (end - 3.5,) and not kwargs)
                        or (not args and kwargs == {"deadline": end - 3.5}))
                timeline.append("supervisor-wait")
                decision.set()
            elif name == "publish_native_handoff":
                assert not loop.is_running()
                assert all(_handoff_lock_snapshot(owner, namespace["cleanup_lock"], end))
                ready.set()  # Observation of valid MAIN publication entry only.
                timeline.append("main-ready")
            elif name == "supervisor_native_finished":
                # Native work/except handling is over on entry to this finally
                # notification. Do not race a post-return observer flag against
                # MAIN awakened by the ORIGINAL method's event publication.
                assert calls["supervisor-native-return"] == 1
                phase_done.set()
                timeline.append("supervisor-native-finished")
            elif name == "close_native_handoff":
                assert ((args == (end - 0.25,) and not kwargs)
                        or (not args and kwargs == {"deadline": end - 0.25}))
                assert not loop.is_running()
                assert all(_handoff_lock_snapshot(owner, namespace["cleanup_lock"], end))
            value = method(*args, **kwargs)
            if name == "close_native_handoff":
                assert value is True
                assert phase_done.is_set(), "MAIN_IGNORED_REGISTERED_SUPERVISOR"
                phase_closed.set()
                timeline.append("phase-closed")
            return value
        setattr(owner, name, observed)

    def observed_drive(awaitable):
        assert threading.current_thread() is main, "SUPERVISOR_DROVE_LOOP"
        if ready.is_set():
            assert phase_done.is_set() and phase_closed.is_set(), (
                "MAIN_RESUMED_BEFORE_SUPERVISOR_NATIVE_FINISHED")
            timeline.append("loop-resume")
            if pending_api:
                # Exhaust only the UNIT asynchronous join allowance AFTER the
                # real handoff has completed within its original absolute bounds.
                owner.remaining = lambda: 0.0
        return original_drive(awaitable)
    loop.run_until_complete = observed_drive

    def hold_main():
        suspended.set()
        assert decision.wait(max(0.0, end - 3.5 - time.monotonic())), (
            "watchdog reached neither cleanup nor actual handoff wait")

    async def observed_cooperate():
        # Runs AFTER actual _cooperate suspends on its original pending work.
        loop.call_soon(hold_main)
        return await original_cooperate()
    if when == "during":
        owner._cooperate = observed_cooperate

    def run_watchdog():
        try:
            watchdog()
        except BaseException as error:
            faults.append(error)

    try:
        task = owner.retain_cleanup(loop.create_task(original_public_close()), "owner-close")
        supervisor = threading.Thread(target=run_watchdog, name="unit-extracted-watchdog")
        owner.permitted_threads = lambda: {supervisor}
        supervisor.start()
        if when == "before":
            with owner.loop_drive_lock:
                hold_main()  # LOOP stopped but MAIN has NOT released/published yet.
        owner.finish(native_retire=namespace["cleanup"], verify_native=namespace["sdk_native_proof"])
        supervisor.join(max(0.0, end - time.monotonic()))
        supervisor_entries = [row for row in entries if row["supervisor"]]
        # FIRST behavioral gate: old extracted watchdog enters ORIGINAL cleanup
        # while MAIN holds drive lock, even though future APIs are absent.
        assert supervisor_entries and all(
            row["ready"] and not row["running"] and row["locks"][0]
            for row in supervisor_entries), (
                "WATCHDOG_NATIVE_ENTERED_BEFORE_MAIN_HANDOFF", supervisor_entries)
        _handoff_require_api(owner)
        assert not supervisor.is_alive() and not faults
        assert len(entries) == 2 and len(supervisor_entries) == 1
        assert all(not row["running"] and all(row["locks"]) for row in entries)
        assert ready.is_set() and phase_done.is_set() and phase_closed.is_set()
        assert owner.fallback_requested.is_set()
        assert timeline.index("supervisor-native-finished") < timeline.index("loop-resume")
        assert calls["native-claims"] == 1 and namespace["sdk_native_proof"]()
        expected = {"guardian-signal": 2, "guardian-safe": 2, "creator-reap": 2,
                    "controller": 2, "reader": 2, "slot-fd": 10,
                    "creator-streams": 2, "creator-stream": 6}
        assert Counter(stage for stage, _ in attempts) == {
            **expected, "owner-fence": 1, "creator-fence": 1, "release": 1}
        assert len(closed) == 10
        assert calls["creator-waits"] == calls["controller-joins"] == calls["reader-joins"] == 2
        assert all(not running and all(locks) for running, locks in waits)
        assert calls["early-read"] == int(early)
        assert sum(error is fault for _, error in owner.errors) == int(native_error)
        assert task.cancelling() == 0 and calls["public-delegate"] == 1
        assert owner.finalized is (not pending_api)
        if pending_api:
            assert not task.done() and calls["public-complete"] == 0
            with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
                owner.prove_safe()
            assert owner.safe_emissions == 0
        else:
            assert task.done() and not task.cancelled() and task.exception() is None
            assert calls["public-complete"] == calls["original-gate-release"] == 1
    finally:
        suspended.set()
        decision.set()
        owner.complete.set()  # Unit thread hygiene, NEVER proof/ACK/ready.
        if supervisor is not None:
            supervisor.join(max(0.0, end - time.monotonic()))
        loop.run_until_complete = original_drive
        owner._cooperate = original_cooperate
        owner.main_finishing.set()
        _repair_hygiene(loop, owner, [gate])
    return owner, task, calls


@pytest.mark.parametrize("early", [False, True], ids=["normal", "early"])
@pytest.mark.parametrize("when", ["before", "during"])
@pytest.mark.parametrize("native_error", [False, True], ids=["success", "error"])
def test_extracted_watchdog_native_handoff(early, when, native_error):
    """8 actual branches, 0 native entries before MAIN stops and publishes."""
    _handoff_run_actual_watchdog(early=early, when=when, native_error=native_error)


@pytest.mark.parametrize("registration", ["before", "after"])
def test_late_watchdog_registration(registration):
    """Before closure: completion accounted; after closure: 0 cleanup entries."""
    loop, owner, calls, end = _compat_case()
    close_started, close_returned = threading.Event(), threading.Event()
    registered, completed = threading.Event(), threading.Event()
    faults, statuses = [], []
    thread = None
    try:
        _handoff_require_api(owner)
        owner.main_finishing.set()  # Unit MAIN scheduling role, never proof.
        namespace, attempts, closed, waits = _handoff_native_case(loop, owner, calls, end)
        native = namespace["sdk_native_cleanup"]

        def observed_native():
            calls["cleanup-entries"] += 1
            assert not loop.is_running()
            assert all(_handoff_lock_snapshot(owner, namespace["cleanup_lock"], end))
            return native()
        namespace["sdk_native_cleanup"] = observed_native
        owner.publish_native_handoff()

        if registration == "before":
            request, wait = owner.request_native_handoff, owner.wait_native_handoff
            finished = owner.supervisor_native_finished

            def observed_request():
                status = request()
                statuses.append(status)
                registered.set()
                return status

            def observed_wait(deadline):
                assert deadline == end - 3.5
                assert close_started.wait(max(0.0, end - 3.5 - time.monotonic()))
                assert owner.fallback_requested.is_set()
                return wait(deadline)

            def observed_finished():
                try:
                    assert namespace["native_done"].is_set()
                    # Hold the ORIGINAL watchdog's completion notification until
                    # the absolute reserve; MAIN must still account this caller.
                    assert not close_returned.wait(max(0.0, end - 3.5 - time.monotonic()))
                finally:
                    finished()
                    completed.set()
            owner.request_native_handoff = observed_request
            owner.wait_native_handoff = observed_wait
            owner.supervisor_native_finished = observed_finished
            watchdog = _handoff_watchdog(namespace, owner, calls, end, early=True)

            def supervisor():
                try:
                    watchdog()  # ORIGINAL branch, including cleanup and finally.
                except BaseException as error:
                    faults.append(error)
            thread = threading.Thread(target=supervisor, name="unit-late-registration")
            thread.start()
            assert registered.wait(max(0.0, end - 3.5 - time.monotonic()))
            assert statuses == ["REGISTERED"]
            close_started.set()
            assert owner.close_native_handoff(end - 0.25) is True
            close_returned.set()
            assert completed.wait(max(0.0, end - 0.25 - time.monotonic()))
            owner.complete.set()  # Release only original HOST-complete wait.
            assert calls["cleanup-entries"] == calls["native-claims"] == 1
        else:
            assert namespace["cleanup"]() is True  # Original MAIN native collection.
            assert owner.close_native_handoff(end - 0.25) is True
            close_returned.set()
            owner.complete.set()  # No waiting unit HOST finisher, not SAFE/proof.
            request = owner.request_native_handoff

            def observed_request():
                status = request()
                statuses.append(status)
                return status
            owner.request_native_handoff = observed_request
            watchdog = _handoff_watchdog(namespace, owner, calls, end, early=True)

            def supervisor():
                try:
                    watchdog()  # ORIGINAL early branch, not manual status simulation.
                except BaseException as error:
                    faults.append(error)
            thread = threading.Thread(target=supervisor, name="unit-after-phase-closure")
            thread.start()

        thread.join(max(0.0, end - time.monotonic()))
        assert not thread.is_alive() and not faults
        assert calls["cleanup-entries"] == calls["native-claims"] == 1
        assert namespace["sdk_native_proof"]() is True
        if registration == "after":
            assert statuses == ["ALREADY_RETIRED"]
        assert owner.safe_emissions == 0  # Handshake never establishes HOST SAFE.
    finally:
        close_started.set()
        owner.complete.set()
        if thread is not None:
            thread.join(max(0.0, end - time.monotonic()))
        _repair_hygiene(loop, owner, [])


def test_handoff_missing_at_guardian_reserve(monkeypatch):
    """Original early watchdog: missing MAIN => 0 cleanup, 1 error, SAFE0."""
    loop, owner, calls, end = _compat_case()
    gate = asyncio.Event()
    deadlines, faults = [], []
    wait_thread, wait_budget = [None], [0.0]
    wait_returns, timeouts = [], []
    thread = None
    task = None

    async def original_public_close():
        await gate.wait()

    try:
        _handoff_require_api(owner)
        namespace, attempts, closed, waits = _handoff_native_case(loop, owner, calls, end)
        native = namespace["sdk_native_cleanup"]

        def observed_native():
            calls["coordinated-native-entries"] += 1
            return native()
        namespace["sdk_native_cleanup"] = observed_native
        wait = owner.wait_native_handoff
        event_wait = threading.Event.wait

        def observed_event_wait(event, timeout=None):
            observed = wait_thread[0] is threading.current_thread()
            if observed:
                # Observe real Event.wait, not a replacement ready gate. The
                # allowance only shrinks, including after spurious/short waits.
                assert timeout is not None and timeout <= wait_budget[0]
                assert all(_handoff_lock_snapshot(owner, namespace["cleanup_lock"], end))
                timeouts.append(timeout)
            try:
                return event_wait(event, timeout)
            finally:
                if observed:
                    wait_budget[0] = max(0.0, end - 3.5 - time.monotonic())
        monkeypatch.setattr(threading.Event, "wait", observed_event_wait)

        def observed_wait(deadline):
            deadlines.append(deadline)
            wait_thread[0] = threading.current_thread()
            wait_budget[0] = max(0.0, deadline - time.monotonic())
            try:
                return wait(deadline)
            finally:
                wait_returns.append(time.monotonic())
                wait_thread[0] = None
        owner.wait_native_handoff = observed_wait
        task = owner.retain_cleanup(loop.create_task(original_public_close()), "owner-close")
        watchdog = _handoff_watchdog(namespace, owner, calls, end, early=True)

        def supervisor():
            try:
                watchdog()
            except BaseException as error:
                faults.append(error)
        thread = threading.Thread(target=supervisor, name="unit-missing-main-handoff")
        thread.start()
        thread.join(max(0.0, end - 0.25 - time.monotonic()))
        assert not thread.is_alive() and not faults
        assert deadlines == [end - 3.5] and time.monotonic() >= end - 3.5
        assert timeouts and len(wait_returns) == 1 and wait_returns[0] >= end - 3.5
        assert calls["coordinated-native-entries"] == calls["native-claims"] == 0
        assert len(owner.errors) == 1
        assert owner.errors[0][1].args == ("SDK_NATIVE_HANDOFF_MISSING",)
        assert not namespace["native_done"].is_set() and not namespace["sdk_native_proof"]()
        assert not owner.complete.is_set() and not owner.finalized
        assert not task.done() and task.cancelling() == 0
        with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
            owner.prove_safe()
        assert owner.safe_emissions == 0
    finally:
        owner.complete.set()
        if thread is not None:
            thread.join(max(0.0, end - time.monotonic()))
        owner.main_finishing.set()  # Suppress loop.stop only during unit hygiene.
        gate.set()
        loop.run_until_complete(asyncio.sleep(0))  # Collect queued ORIGINAL quiesce.
        _repair_hygiene(loop, owner, [gate])


def test_guardian_independent_safety_still_runs():
    """Original guardian cleanup runs at END-3.5 while unit MAIN is still driving."""
    loop, owner, calls = _repair_case()
    end = time.monotonic() + 3.75  # One UNIT END, original offsets below.
    owner.deadline, owner.cooperative_cutoff = end - 0.25, end - 3.75
    gate = asyncio.Event()
    hung = threading.Event()
    holder, faults, emitted, selections = {}, [], [], []
    main_thread = None

    async def original_public_close():
        hung.set()
        await gate.wait()
        calls["public-complete"] += 1

    def main():
        try:
            with owner.loop_drive_lock:
                task = owner.retain_cleanup(loop.create_task(original_public_close()), "owner-close")
                holder["task"] = task
                loop.run_until_complete(task)
        except BaseException as error:
            faults.append(error)

    def joined_thread(name):
        actual = SimpleNamespace(ident=77, joined=False)

        def join(timeout=None):
            calls[name] += 1
            actual.joined = True
        actual.join, actual.is_alive = join, lambda: not actual.joined
        return actual

    monitor, observer = joined_thread("monitor-join"), joined_thread("observer-join")
    worker = joined_thread("executor-join")
    pool = SimpleNamespace(_threads=[worker],
                           shutdown=lambda **kwargs: calls.update(["pool-shutdown"]))
    context = SimpleNamespace(stop=threading.Event(), executors=[pool], monitor=monitor,
                              published=False)
    observer_record = SimpleNamespace(stop=threading.Event(), thread=observer)
    attached = SimpleNamespace(closed=False)
    attached.close = lambda: setattr(attached, "closed", True)
    process = SimpleNamespace(_creator_waited=False)
    entries = [dict(process=process)]

    def fence():
        calls["fence"] += 1
        return entries

    def reap(deadline):
        calls["reap"] += 1
        assert deadline <= end - 0.5  # Original guardian physical_cleanup budget.
        process._creator_waited = True  # DECLARED fake creator wait, not an ACK.

    def select(inputs, writes, errors, timeout):
        selections.append(timeout)
        threading.Event().wait(timeout)  # Original remaining(END-3.5), no grace.
        return [], [], []

    namespace = dict(
        END=end, time=time, cleanup_lock=threading.Lock(), stopping=threading.Event(),
        stop_w=401, safety=402, done_r=403, hits=[], forbidden_calls=[],
        contexts=[context], observers=[observer_record], state=SimpleNamespace(attached=attached),
        trace=SimpleNamespace(fence=fence, reap=reap,
                              evidence=lambda: [dict(waited=process._creator_waited)]),
        memory_calls=[SimpleNamespace(wait=lambda timeout=None: bool(
            calls.update(["memory-wait"]) or True))],
        remaining=lambda deadline: max(0.0, deadline - time.monotonic()),
        select=SimpleNamespace(select=select),
        failure_diagnostic=lambda *args, **kwargs: calls.update(["guardian-diagnostic"]),
        emit=lambda kind, **data: emitted.append((kind, data)),
        os=SimpleNamespace(write=lambda fd, data: len(data),
                           _exit=lambda code: calls.update([("mock-exit", code)])))
    # Bind the actual decoded guardian dependency in this namespace only.
    guardian_diagnostic_packets = []
    guardian_diagnostic_clock = time.monotonic_ns

    def guardian_diagnostic_write(fd, raw):
        guardian_diagnostic_packets.append((fd, raw))
        return len(raw)

    namespace.update(
        json=json, _guardian_budget_ready=True,
        _guardian_budget_clock=guardian_diagnostic_clock,
        _guardian_budget_write=guardian_diagnostic_write,
        _handoff_guardian_budget_packets=guardian_diagnostic_packets)
    guardian_diagnostic, = [
        node for node in _compat_guest_tree().body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_guardian_budget_diagnostic"]
    exec(compile(ast.Module(body=[guardian_diagnostic], type_ignores=[]),
                 "EXTRACTED_guardian_budget_diagnostic_handoff", "exec"), namespace)
    _handoff_extract("guardian_main", ("physical_cleanup", "watchdog"), namespace)
    original_cleanup = namespace["physical_cleanup"]

    def observed_cleanup():
        calls["independent-cleanup"] += 1
        assert loop.is_running() and owner.loop_drive_lock.locked()
        return original_cleanup()  # ORIGINAL full safety cleanup, no substitute.
    namespace["physical_cleanup"] = observed_cleanup
    try:
        main_thread = threading.Thread(target=main, name="unit-hung-main")
        main_thread.start()
        assert hung.wait(max(0.0, end - 0.25 - time.monotonic()))
        namespace["watchdog"]()  # ORIGINAL deadline branch including cleanup/SAFE/exit.
        task = holder["task"]
        assert not faults and loop.is_running() and owner.loop_drive_lock.locked()
        assert len(selections) == 1 and 0.0 <= selections[0] <= 0.25
        assert time.monotonic() >= end - 3.5
        assert calls["independent-cleanup"] == calls["guardian-diagnostic"] == 1
        assert calls["reap"] == 2 and calls["fence"] == 2
        assert all(calls[name] == 1 for name in (
            "memory-wait", "pool-shutdown", "executor-join", "observer-join", "monitor-join"))
        assert attached.closed and context.stop.is_set() and observer_record.stop.is_set()
        assert calls[("mock-exit", 88)] == 1
        assert len(emitted) == 1 and emitted[0][0] == "SAFE"
        assert emitted[0][1]["independent"] is True
        assert not task.done() and task.cancelling() == 0 and calls["public-complete"] == 0
        assert not owner.finalized and owner.safe_emissions == 0
        with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
            owner.prove_safe()
    finally:
        loop.call_soon_threadsafe(gate.set)  # Original API gate, hygiene only.
        if main_thread is not None:
            main_thread.join(max(0.0, end - time.monotonic()))
        assert main_thread is None or not main_thread.is_alive()
        _repair_hygiene(loop, owner, [gate])


def test_handoff_does_not_replace_proof():
    """Original successful native/handshake + 1 pending API still gives SAFE0."""
    owner, task, calls = _handoff_run_actual_watchdog(
        early=True, when="during", native_error=False, pending_api=True)
    # The helper resolved only the original gate for hygiene after checking
    # pending API/finalFalse/SAFE0. Hygiene can never retroactively qualify it.
    assert task.done() and not task.cancelled() and calls["public-complete"] == 1
    assert owner.finalized is False and owner.safe_emissions == 0


# SCORER SOURCE-FIRST tests. Everything above, including strict4/handoff, frozen.
def _scorer_original_namespace():
    """Unchanged original lease/close/drain definitions, no SDK/module import."""
    path = Path(__file__).resolve().parents[1] / "cotrain_owned_sql.py"
    tree = ast.parse(path.read_text())
    names = ("_settle", "_close_resource", "_ProgramLease", "_CloseSet", "_drain_scope")
    selected = [next(node for node in tree.body if getattr(node, "name", None) == name)
                for name in names]
    namespace = dict(__name__=__name__, asyncio=asyncio)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _scorer_original_observer(name, namespace):
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    tree = ast.parse(path.read_text())
    node, = [node for node in ast.walk(tree)
             if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def _scorer_probe_case(role="scorer"):
    """Real unit Tasks, inert resources/context receiver, ORIGINAL observers."""
    namespace = _repair_program_namespace()
    core = _scorer_original_namespace()
    loop, owner, calls = _repair_case()
    ambient, task_scopes = [None], {}
    api = SimpleNamespace(
        _HOOKS=object(), _close_resource=core["_close_resource"],
        _rollout=SimpleNamespace(get=lambda: task_scopes.get(
            asyncio.current_task(loop=loop), ambient[0])))
    actor = SimpleNamespace(
        retirement=owner, owners=[], slots=[], emit=lambda *args, **kwargs: None,
        test_gates=SimpleNamespace(release_pending=lambda: None))
    kwargs = dict(
        api=api, core=SimpleNamespace(), actor=actor, profile=object(), executor=object(),
        owners=[], closes=[], programs=[], scorers=[], rewards=[], results=[],
        sdk_tasks=[], controller_gates=[])
    cls = namespace["_SdkProgramCancellation"]
    # Label ONLY, not missing validation/role-branch implementation. Existing
    # observer bugs must fail behaviorally instead of an unexpected keyword.
    probe = cls(**kwargs, role=role) if "role" in inspect.signature(cls).parameters else cls(**kwargs)
    if "role" not in inspect.signature(cls).parameters:
        probe.role = role
    patches = {}
    probe.install(SimpleNamespace(setattr=lambda target, name, value: patches.__setitem__(name, value)))

    def create_task(coroutine, *args, **kwargs):
        scope = api._rollout.get()
        actual = patches["create_task"](coroutine, *args, **kwargs)
        task_scopes[actual] = scope
        return actual
    # No global patch/context set/reset: the extracted original core delegates
    # creates through the real installed observer, shields through real asyncio.
    core["asyncio"] = SimpleNamespace(
        create_task=create_task, shield=asyncio.shield, gather=asyncio.gather,
        CancelledError=asyncio.CancelledError, Task=asyncio.Task)
    return SimpleNamespace(
        loop=loop, owner=owner, calls=calls, api=api, actor=actor, probe=probe,
        namespace=namespace, core=core, ambient=ambient, task_scopes=task_scopes,
        patches=patches, create_task=create_task, kwargs=kwargs,
        scopes=[], programs=probe.programs, scorers=probe.scorers, gates=[], runners=[])


def _scorer_runner(case, program, index):
    runner = SimpleNamespace()

    async def close():
        case.calls[("runner-delegate", index)] += 1
    runner.aclose = _scorer_original_observer(
        "observed_runner_close",
        dict(asyncio=asyncio, actor=case.actor, record=program, runner=runner,
             cancellation=case.probe, close=close))
    return runner


async def _scorer_start_resources(case):
    """Original close sets reuse 2 completed runners, create only 2 scorers."""
    for index in range(2):
        scope = SimpleNamespace(
            agent_task=None, task_score=None, harness_score=None, cleanup_task=None,
            closes=case.core["_CloseSet"](), program=object(), scorer=None)
        program = SimpleNamespace(scope=scope, harness=scope.program, runners=[], closes=[])
        runner = _scorer_runner(case, program, index)
        program.runners.append(runner)
        lease = case.core["_ProgramLease"](runner, lambda: None)
        gate = asyncio.Event()
        scorer = SimpleNamespace()
        record = SimpleNamespace(scope=scope, actual=scorer, closes=[], result=None)

        async def original_close(actual, index=index, gate=gate):
            case.calls[("scorer-delegate", index)] += 1
            await gate.wait()
        observed = _scorer_original_observer(
            "observed_scorer_close",
            dict(asyncio=asyncio, actor=case.actor, cancellation=case.probe,
                 scorer_record=lambda actual, record=record: record,
                 original_scorer_close=original_close))
        scorer.aclose = lambda observed=observed, scorer=scorer: observed(scorer)
        scope.scorer = scorer
        scope.closes.retain(lease)
        scope.closes.retain(scorer)
        case.ambient[0] = scope
        original_runner_task = scope.closes.start(lease)
        case.scopes.append(scope)
        case.programs.append(program)
        case.scorers.append(record)
        case.gates.append(gate)
        case.runners.append((runner, lease, original_runner_task))
        await original_runner_task  # Normal runner finalization BEFORE cancel.
        assert original_runner_task.done() and original_runner_task.cancelling() == 0
    case.probe.issued.append(case.namespace["_MARKERS"][0])  # Unit phase label, not SDK evidence.
    for scope, (_, _, runner_task) in zip(case.scopes, case.runners, strict=True):
        case.ambient[0] = scope
        tasks = scope.closes.start_all()  # ORIGINAL creates pending scorer only.
        assert len(tasks) == 2 and tasks[0] is runner_task
        assert scope.closes.start_all() == tasks
    await asyncio.sleep(0)  # Enter both original observed scorer-close bodies.


@pytest.mark.parametrize("mutation", ["none", "runner-replay", "runner-substitution"])
def test_scorer_completed_runner_reuse(mutation):
    case = _scorer_probe_case()

    async def scenario():
        await _scorer_start_resources(case)
        probe = case.probe
        originals = [task for _, _, task in case.runners]
        assert len(probe.resource_tasks) == len(probe.resource_bodies) == 4
        assert sum(row.task.done() for row in probe.resource_tasks) == 2
        assert sum(not row.task.done() for row in probe.resource_tasks) == 2
        assert all(task in probe.retained and task in case.owner.tasks for task in originals)
        assert all(row.task in probe.retained and row.task in case.owner.tasks
                   for row in probe.resource_tasks)
        assert all(case.calls[("runner-delegate", index)] == 1 for index in range(2))
        assert all(case.calls[("scorer-delegate", index)] == 1 for index in range(2))
        if mutation != "none":
            case.ambient[0] = case.scopes[0]
            runner = (case.runners[0][0] if mutation == "runner-replay"
                      else _scorer_runner(case, case.programs[0], 0))
            mutant = case.create_task(case.core["_close_resource"](runner))
            with pytest.raises(AssertionError):
                await mutant  # ACTUAL resource_body must reject before delegate.
            assert case.calls[("runner-delegate", 0)] == 1
        else:
            for scope, (_, lease, task) in zip(case.scopes, case.runners, strict=True):
                case.ambient[0] = scope
                assert lease.start_close() is task and scope.closes.start_all()[0] is task
            assert len(probe.resource_tasks) == len(probe.resource_bodies) == 4
        assert all(task.cancelling() == 0 for task in case.owner.tasks)
    try:
        case.loop.run_until_complete(scenario())
    finally:
        _repair_hygiene(case.loop, case.owner, case.gates)


@pytest.mark.parametrize("mutation", ["none", "missing-scorer", "replacement-runner"])
def test_scorer_start_all_identity(mutation):
    case = _scorer_probe_case()

    async def scenario():
        await _scorer_start_resources(case)
        probe = case.probe
        if mutation != "none":
            scope = case.scopes[0]
            original = case.runners[0][2]
            rows = [row for row in probe.resource_tasks if row.scope is scope]
            if mutation == "missing-scorer":
                scorer_row, = [row for row in rows if row.task is not original]
                probe.resource_tasks.remove(scorer_row)
            else:
                # Genuine retained completed runner, but the WRONG scope.
                replacement = case.runners[1][2]
                runner_row, = [row for row in rows if row.task is original]
                probe.resource_tasks[probe.resource_tasks.index(runner_row)] = SimpleNamespace(
                    scope=scope, task=replacement)
        for index, scope in enumerate(case.scopes):
            case.ambient[0] = scope
            scope.cleanup_task = case.owner.retain_cleanup(
                case.loop.create_task(case.core["_drain_scope"](scope)), "scope-drain")
            case.task_scopes[scope.cleanup_task] = scope
            if index == 0 and mutation != "none":
                # If the OLD observer wrongly accepts this ledger, release the
                # original gate next tick so rejection fails, never hangs.
                # The observer inspects the still-held state BEFORE this yield.
                case.loop.call_soon(case.gates[index].set)
                with pytest.raises(AssertionError):
                    await probe_join(scope)
                assert id(scope) not in probe.first_joins
                return
            join = case.owner.retain_task(case.loop.create_task(probe_join(scope)))
            case.task_scopes[join] = scope
            await asyncio.sleep(0)
            runner_task = case.runners[index][2]
            snapshot = probe.first_joins[id(scope)]
            assert len(snapshot) == 2 and snapshot[0] is runner_task
            assert runner_task.done() and sum(not task.done() for task in snapshot) == 1
            case.gates[index].set()
            await join
        assert len(probe.first_joins) == 2

    async def probe_join(scope):
        return await case.patches["shield"](scope.cleanup_task)  # ORIGINAL installed observer.
    try:
        case.loop.run_until_complete(scenario())
    finally:
        _repair_hygiene(case.loop, case.owner, case.gates)


@pytest.mark.parametrize("harness_state", ["pending", "completed"])
@pytest.mark.parametrize("mutation", [
    "none", "surviving", "replacement-task", "replacement-harness", "forged-child"])
def test_scorer_score_children(harness_state, mutation):
    case = _scorer_probe_case()
    children_gate = asyncio.Event()
    case.gates.append(children_gate)
    observing, observed_results = [False], set()

    class ScoreChild(asyncio.Task):
        def cancel(self, msg=None):
            if observing[0]:
                case.calls["observer-cancel"] += 1
            return super().cancel(msg)

        def result(self):
            if observing[0]:
                observed_results.add(self)
            return super().result()

    async def unit_score(pending):
        if pending:
            await children_gate.wait()
        return None  # Unit Harness.score return, never an ExResult.

    async def scenario():
        capture = getattr(case.probe, "retain_score_children", None)
        check = getattr(case.probe, "check_score_children", None)
        assert callable(capture) and callable(check), "planned score-child observation contract"
        await _scorer_start_resources(case)
        originals = []
        for scope in case.scopes:
            scope.task_score = ScoreChild(unit_score(True), loop=case.loop)
            scope.harness_score = ScoreChild(
                unit_score(harness_state == "pending"), loop=case.loop)
            originals.append((scope.task_score, scope.harness_score))
        await asyncio.sleep(0)
        for scope, pair in zip(case.scopes, originals, strict=True):
            observing[0] = True
            try:
                assert capture(scope) is None
            finally:
                observing[0] = False
            assert all(task in case.probe.retained and task in case.owner.tasks for task in pair)
            assert all(task.cancelling() == 0 for task in pair), "OBSERVER_CANCELLED_SCORE_CHILD"
        if mutation != "surviving":
            for gate in case.gates[1:]:
                gate.set()  # Original scorer-close gates, before original drain joins.
            for scope in case.scopes:
                scope.cleanup_task = case.owner.retain_cleanup(
                    case.loop.create_task(case.core["_drain_scope"](scope)), "scope-drain")
                case.task_scopes[scope.cleanup_task] = scope
                await scope.cleanup_task
            for task_score, harness_score in originals:
                assert task_score.cancelled() and task_score.cancelling() == 1
                assert harness_score.cancelled() is (harness_state == "pending")
                assert harness_score.cancelling() == int(harness_state == "pending")
        if mutation.startswith("replacement-"):
            # Genuine retained original with matching done/cancelled state;
            # status/type-only validation cannot detect this substitution.
            replacement = originals[1][int(mutation == "replacement-harness")]
            setattr(case.scopes[0], "task_score" if mutation == "replacement-task"
                    else "harness_score", replacement)
        elif mutation == "forged-child":
            case.scopes[0].task_score = SimpleNamespace(
                done=lambda: True, cancelled=lambda: True, result=lambda: None)
        before = {task: task.cancelling() for pair in originals for task in pair}
        observing[0] = True
        try:
            if mutation == "none":
                for scope in case.scopes:
                    assert check(scope) is None
            else:
                with pytest.raises(AssertionError):
                    check(case.scopes[0])
        finally:
            observing[0] = False
        assert all(task.cancelling() == count for task, count in before.items()), (
            "VALIDATOR_CANCELLED_SCORE_CHILD")
        assert case.calls["observer-cancel"] == 0, "OBSERVER_CANCELLED_SCORE_CHILD"
        if mutation == "none" and harness_state == "completed":
            assert all(pair[1] in observed_results and not pair[1].cancelled()
                       for pair in originals), "COMPLETED_HARNESS_RESULT_NOT_OBSERVED"
    try:
        case.loop.run_until_complete(scenario())
    finally:
        # Captured children must be retained by the helper. Also retain original
        # test-created children for failure hygiene if that very assertion fails.
        for scope in case.scopes:
            for name in ("task_score", "harness_score"):
                task = getattr(scope, name, None)
                if isinstance(task, asyncio.Task):
                    case.owner.retain_task(task)
        _repair_hygiene(case.loop, case.owner, case.gates)


def _scorer_actual_dispatch_receipt(probe):
    """Evaluate original return value nodes, NOT a test-authored dispatch rule."""
    path = Path(__file__).with_name("test_owned_sql_sdk_program_cancellation.py")
    tree = ast.parse(path.read_text())
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkProgramCancellation"]
    qualify, = [node for node in cls.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "qualify"]
    receipt, = [node.value for node in ast.walk(qualify)
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "dict"
                and any(keyword.arg == "scorer_dispatches" for keyword in node.value.keywords)]
    names = ("allocations", "dispatches", "program_dispatches", "scorer_dispatches")
    keywords = {keyword.arg: keyword.value for keyword in receipt.keywords}
    return {name: eval(compile(ast.Expression(body=keywords[name]), str(path), "eval"),
                       dict(probe.__class__.__init__.__globals__, self=probe))
            for name in names}


@pytest.mark.parametrize("case_name", [
    "scorer", "program", "default", "invalid-upper", "invalid-none", "invalid-other", "invalid-number"])
def test_scorer_dispatch_receipt(case_name):
    role = "scorer" if case_name == "scorer" else "program"
    case = _scorer_probe_case(role)
    try:
        cls = case.namespace["_SdkProgramCancellation"]
        if case_name.startswith("invalid-"):
            invalid = {"invalid-upper": "SCORER", "invalid-none": None,
                       "invalid-other": "runner", "invalid-number": 1}[case_name]
            with pytest.raises((AssertionError, ValueError)):
                cls(**case.kwargs, role=invalid)  # TypeError/missing API is NOT validation.
            return
        if case_name == "default":
            case.probe = cls(**case.kwargs)
            assert getattr(case.probe, "role", None) == "program"
        allocated = [SimpleNamespace(role=role), SimpleNamespace(role=role)]
        case.actor.owners[:] = allocated
        case.actor.slots[:] = [dict(invocation=allocated[0])]  # 1 declared guardian SLOT.
        case.probe.owners[:] = [SimpleNamespace(actual=actual) for actual in allocated]
        receipt = _scorer_actual_dispatch_receipt(case.probe)
        expected = dict(allocations=2, dispatches=1,
                        program_dispatches=int(role == "program"),
                        scorer_dispatches=int(role == "scorer"))
        assert receipt == expected, ("SCORER_DISPATCH_MUST_COUNT_ACTUAL_SLOTS", receipt)
    finally:
        _repair_hygiene(case.loop, case.owner, [])


# DECODED INVALID: frozen tests only. All preceding source is unchanged.
# Five groups below, no SDK Agent/eval, native invocation, ACK or HOST activation.
# Corrected HOST contract: four normal invalid phases use expected_ok=True BUT
# sticky HOST ok=False/exit1. Explicit SAME-dict parent refusal, current physical
# SAFE, actual wait/closed streams/ledgers remain mandatory in NEXT actor work.
# Six existing expected_ok=False physical contracts are NOT extended/replaced.
#
# Minimal FUTURE canonical-only API (new-feature missing-API RED is expected):
# _SdkInvalidStatus(*, api, retirement, status, scope, owner, result)
# Events: owner_held, owner_release, env_held, env_release.
# async close_owner(actual, delegate): hold exact target before delegate(actual),
# retain original owner-close/Task.score tasks; refuse replay BEFORE delegation.
# async settle_cleanup(task, delegate): call original delegate(task); ONLY exact
# scope.cleanup_task holds AFTER resolution, preserves result/error identity;
# retain cleanup task, expose settled_result/settled_error; refuse target replay.
# release(): idempotently release BOTH holds, no cancellation or new work.
# Constructor composes retirement.release with finally-release of both holds.
# check_provenance(): None/AssertionError; exact original score/drain code,
# trusted file + independently AST-derived raise line, scope/result identities,
# original settled cleanup error, all original scope/resource children done.
# check_ledger(): None/AssertionError; fresh identities EXACTLY the two distinct
# original errors, BOTH present, every stage "task", primary one of those two;
# duplicates of these SAME objects permitted, no ledger/primary mutation.
# check_target(*, episodes, rows, target_rewards): ANY observed/live/persisted
# target reward (including legitimate decoded mismatch/zero) raises literal
# SDK_INVALID_TARGET_NO_REWARD BEFORE invalid/provenance checks. Target success
# at episode OR trace/row is rejected; unrelated successful sibling is permitted.
#
# These tests supply UNIT-only public scorer/owner/trace receivers. FunctionType
# changes only an isolated globals dict, retains actual Task.score.__code__;
# NO module hook, ContextVar, production source or exception provenance is
# changed except explicitly labelled negative UNIT traceback corruptions.
# Real decoded objects cross original Task.score. No actor qualification claim.
# Original 45s command/19.5s HOST/12s intent/reserve bounds remain unchanged.
_INVALID_UNIT_STATUSES = ("gold_error", "gold_timeout", "gold_truncated", "db_missing")
_INVALID_REWARD_GATE = "SDK_INVALID_TARGET_NO_REWARD"


def _invalid_forbidden_popen(original_popen, denied_popen):
    """Preserve lazy generic annotations, delegate every counted native denial."""
    class ForbiddenPopen(original_popen):
        def __init__(self, *args, **kwargs):
            denied_popen(*args, **kwargs)
    return ForbiddenPopen


@pytest.fixture
def _invalid_unit_api(monkeypatch):
    """Reuse protocol UNIT module/guard, never SDK/native execution."""
    import subprocess
    from ptc.test_owned_sql_sdk_protocol import _module, no_native
    api = _module()
    original_popen = subprocess.Popen
    guard = no_native.__wrapped__(monkeypatch)
    next(guard)
    monkeypatch.setattr(subprocess, "Popen", _invalid_forbidden_popen(
        original_popen, subprocess.Popen))
    try:
        yield api
    finally:
        next(guard, None)


def _invalid_wire(status):
    """Original typed role fixture -> original wire encoder AND decoder."""
    from bench.score import ExResult
    from ptc import sql_isolation as core
    tree = _compat_guest_tree()
    names = ("SCORER_FIXTURE_STATUSES", "SCORER_FIXTURE_PREDICTIONS",
             "scorer_fixture_result")
    selected = []
    for name in names:
        node, = [node for node in tree.body
                 if getattr(node, "name", None) == name or (
                     isinstance(node, ast.Assign) and any(
                         isinstance(target, ast.Name) and target.id == name
                         for target in node.targets))]
        selected.append(node)
    namespace = dict(__name__=__name__)
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    prediction = "fixture-score-status:" + status
    fixture = namespace["scorer_fixture_result"](prediction)
    assert type(fixture) is ExResult
    digest = "b" * 64  # UNIT request context, not a native request/ACK claim.
    frame = core.encode_wire_message("scorer", "result", fixture, request_sha256=digest)
    message = core.decode_wire_message(
        frame, role="scorer", kind="result", request_sha256=digest)
    return SimpleNamespace(
        core=core, fixture=fixture, frame=frame, message=message,
        result=message.payload, prediction=prediction, digest=digest)


def _invalid_raise_line(api, kind):
    """Independent trusted AST, never a validator-reported origin/line."""
    path = Path(__file__).resolve().parents[1] / "cotrain_owned_sql.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    if kind == "score":
        cls, = [node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlTask"]
        function, = [node for node in cls.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "score"]
        reference = api.OwnedSqlTask.score
        message = "owned SQL task is not valid for scoring"
    else:
        assert kind == "cleanup"
        function, = [node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "_drain_scope"]
        reference = api._drain_scope
        message = "owned SQL scope cleanup failed"
    node, = [node for node in ast.walk(function)
             if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
             and any(isinstance(arg, ast.Constant) and arg.value == message
                     for arg in node.exc.args)]
    assert Path(reference.__code__.co_filename).resolve() == path
    assert reference.__code__.co_firstlineno == function.lineno
    return reference.__code__, path, node.lineno


def _invalid_last_tb(error):
    tb = error.__traceback__
    assert tb is not None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb


def _invalid_assert_original(api, error, kind, scope, result):
    expected_type = api.ScoreInfrastructureError if kind == "score" else RuntimeError
    assert type(error) is expected_type
    code, path, line = _invalid_raise_line(api, kind)
    tb = _invalid_last_tb(error)
    assert tb.tb_frame.f_code is code
    assert Path(tb.tb_frame.f_code.co_filename).resolve() == path and tb.tb_lineno == line
    assert tb.tb_frame.f_locals["scope"] is scope
    if kind == "score":
        assert tb.tb_frame.f_locals["result"] is result


def _invalid_task(context, coroutine, kind=None):
    actual = context.loop.create_task(coroutine)
    if kind is None:
        context.retirement.retain_task(actual)
    else:
        context.retirement.retain_cleanup(actual, kind)
    return actual


def _invalid_unregistered_task(context, coroutine):
    actual = context.loop.create_task(coroutine)
    context.hygiene_tasks.append(actual)  # Retain for hygiene ONLY after assertions.
    return actual


async def _invalid_unit_case(context, status="gold_error"):
    """UNIT-only public scorer, real original score code/close-set/drain."""
    from types import FunctionType
    from ptc.test_owned_sql_sdk_protocol import _UnitResource
    wire = _invalid_wire(status)
    data, runtime = object(), object()
    task = SimpleNamespace(data=data)
    trace = SimpleNamespace(
        id="unit-invalid-" + str(len(context.cases)), task=SimpleNamespace(data=data),
        last_reply=wire.prediction, rewards={}, ok=False)
    case = SimpleNamespace(
        wire=wire, result=wire.result, status=status, data=data, task=task,
        trace=trace, runtime=runtime, predictions=[], rewards=[],
        before_score_return=None, score_error=None, cleanup_error=None)
    context.cases.append(case)

    def reward(name, score):
        case.rewards.append((name, score))
        trace.rewards[name] = SimpleNamespace(score=score)
    trace.record_reward = reward  # Explicit UNIT Trace receiver, not an SDK patch.

    class UnitOnlyPublicScorer(_UnitResource):
        async def score_sql(self, prediction):
            case.predictions.append(prediction)
            if case.before_score_return is not None:
                await case.before_score_return()
            return wire.result  # SAME original decoded object, never reconstructed.

        async def aclose(self):
            context.retirement.retain_cleanup(asyncio.current_task(), "resource-close")
            return await super().aclose()

    scorer = UnitOnlyPublicScorer()
    scope = SimpleNamespace(
        task=task, data=data, trace=trace, runtime=runtime, private=object(),
        scorer=scorer, result=None, published=False, failed=False, authority=True,
        task_score=None, agent_task=None, harness_score=None, cleanup_task=None,
        finalized=True, harness_success=True, harness_done=asyncio.Event(),
        closes=context.api._CloseSet())
    scope.harness_done.set()
    scope.closes.retain(scorer)

    def fail():
        scope.failed, scope.authority = True, False

    def check(**kwargs):
        assert kwargs == dict(task=task, trace=trace, runtime=runtime)

    def unit_scope(**kwargs):
        check(**kwargs)
        return scope
    scope.fail, scope.check = fail, check
    case.scope, case.scorer = scope, scorer
    # Explicit UNIT owner receiver. No invocation, completion type or ACK is faked.
    case.owner = SimpleNamespace(
        role="scorer", _completion=SimpleNamespace(outcome=SimpleNamespace(result=wire.result)))
    original = context.api.OwnedSqlTask.score
    case.score = FunctionType(
        original.__code__, dict(original.__globals__, _scope=unit_scope),
        original.__name__, original.__defaults__, original.__closure__)
    assert case.score.__code__ is original.__code__
    assert original.__globals__["_scope"] is context.api._scope

    async def completed_harness():
        return None  # UNIT Harness.score child, not an ExResult.
    scope.harness_score = _invalid_task(context, completed_harness())
    await scope.harness_score
    return case


async def _invalid_finish(context, case, *, invalid=True):
    scope = case.scope
    if scope.task_score is None:
        score_task = _invalid_task(context, case.score(case.task, case.trace, case.runtime))
    else:
        score_task = scope.task_score
    score_value, = await asyncio.gather(score_task, return_exceptions=True)
    assert scope.task_score is score_task and scope.result is case.result
    assert case.predictions == [case.wire.prediction]
    if invalid:
        case.score_error = score_value
        _invalid_assert_original(context.api, score_value, "score", scope, case.result)
        assert scope.failed and not scope.published and case.rewards == []
        assert case.trace.rewards == {}
    else:
        assert score_value is None and score_task.exception() is None
    scope.cleanup_task = _invalid_task(context, context.api._drain_scope(scope), "scope-drain")
    cleanup_value, = await asyncio.gather(scope.cleanup_task, return_exceptions=True)
    if invalid:
        case.cleanup_error = cleanup_value
        _invalid_assert_original(context.api, cleanup_value, "cleanup", scope, case.result)
        assert cleanup_value is not score_value
    else:
        assert cleanup_value is None and scope.cleanup_task.exception() is None
    task, = scope.closes.start_all()
    assert case.scorer.close_tasks == [task] and task.done() and task.result() is None
    assert scope.closes.start(case.scorer) is task
    assert case.scorer.close_finished.is_set() and task.cancelling() == 0
    context.retirement._observe_task_errors()  # ORIGINAL identity/stage recording.
    return case


def _invalid_controller(context, case):
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    # Resolve OUTSIDE every expected-refusal context. Missing API is an explicit
    # new-feature RED, never mistaken for a mutation's successful rejection.
    namespace = _repair_namespace(
        path.name, ["_SdkInvalidStatus"], extra={"__file__": str(path.resolve())})
    controller = namespace["_SdkInvalidStatus"](
        api=context.api, retirement=context.retirement,
        status=case.status if case.status in _INVALID_UNIT_STATUSES else "gold_error",
        scope=case.scope, owner=case.owner, result=case.result)
    context.controllers.append(controller)
    return controller


async def _invalid_observe_settle(context, controller, case):
    controller.env_release.set()
    operation = _invalid_task(context, controller.settle_cleanup(
        case.scope.cleanup_task, context.api._settle))
    value, = await asyncio.gather(operation, return_exceptions=True)
    assert value is case.scope.cleanup_task.exception()
    assert controller.settled_error is value and controller.settled_result is None
    assert operation.done() and operation.cancelling() == 0


def _invalid_run(api, scenario):
    loop, retirement, calls = _repair_case()
    context = SimpleNamespace(
        api=api, loop=loop, retirement=retirement, calls=calls,
        cases=[], controllers=[], gates=[], hygiene_tasks=[])
    try:
        # Same finite 3s UNIT safety as protocol._run, NOT a HOST/native cap.
        loop.run_until_complete(asyncio.wait_for(scenario(context), 3.0))
    finally:
        for controller in context.controllers:
            # Do not trust release() UNDER TEST to perform failure hygiene.
            # Resolve the original exposed UNIT gates only AFTER assertions.
            for name in ("owner_release", "env_release"):
                gate = getattr(controller, name, None)
                if isinstance(gate, asyncio.Event):
                    gate.set()
        for task in context.hygiene_tasks:
            retirement.retain_task(task)  # Cannot retroactively satisfy a test assertion.
        _repair_hygiene(loop, retirement, context.gates)


# Group 1: four actual typed fixture wire frames, ORIGINAL encoder/decoder.
@pytest.mark.parametrize("status", _INVALID_UNIT_STATUSES)
def test_invalid_fixture_wire_roundtrip(_invalid_unit_api, status):
    from bench.score import ExResult
    wire = _invalid_wire(status)
    result = wire.message.payload
    assert type(result) is ExResult and result is wire.result
    assert result is not wire.fixture  # Decoder, not the pre-wire fixture object.
    assert result == wire.fixture
    assert result.status == status and result.valid is False
    assert type(result.score) is float and result.score == 0.0
    assert result.detail == "  static scorer fixture\nnot SQL accuracy  \n"
    assert (result.n_pred_rows, result.n_gold_rows) == (7, 11)
    assert wire.message.role == "scorer" and wire.message.kind == "result"
    assert wire.message.request_sha256 == wire.digest


# Group 2: four unchanged actual Task.score code paths, UNIT public scorer only.
@pytest.mark.parametrize("status", _INVALID_UNIT_STATUSES)
def test_original_task_invalid_branch(_invalid_unit_api, status):
    async def scenario(context):
        case = await _invalid_unit_case(context, status)
        await _invalid_finish(context, case)
        assert case.scope.result is case.result is case.wire.message.payload
        assert case.owner._completion.outcome.result is case.result
        assert case.scope.task_score.exception() is case.score_error
        assert case.scope.cleanup_task.exception() is case.cleanup_error
        assert len(case.scorer.close_tasks) == 1 and not case.rewards
        assert all(task.done() and task.cancelling() == 0 for task in context.retirement.tasks)
    _invalid_run(_invalid_unit_api, scenario)


async def _invalid_unit_raise(error, scope, result):
    raise error


# Group 3a: type/code/file/AST line/scope/result/completed-cleanup provenance.
@pytest.mark.parametrize("mutation", [
    "none", "score-type", "score-subclass", "score-origin", "score-spoofed-code",
    "score-line", "cleanup-type", "cleanup-subclass", "cleanup-origin",
    "cleanup-spoofed-code", "cleanup-line", "score-scope", "cleanup-scope",
    "scope-result", "owner-result", "forged-score", "pending-cleanup",
    "pending-harness", "settled-error",
])
def test_invalid_failure_provenance(_invalid_unit_api, mutation):
    async def scenario(context):
        from types import FunctionType, TracebackType
        case = await _invalid_unit_case(context)
        await _invalid_finish(context, case)
        scope = case.scope
        if mutation in ("score-scope", "cleanup-scope"):
            other = await _invalid_unit_case(context)
            await _invalid_finish(context, other)
            setattr(scope, "task_score" if mutation == "score-scope" else "cleanup_task",
                    other.scope.task_score if mutation == "score-scope" else other.scope.cleanup_task)
        elif mutation.startswith(("score-", "cleanup-")) and mutation.split("-", 1)[1] in (
                "type", "subclass", "origin", "spoofed-code"):
            kind, change = mutation.split("-", 1)
            expected = context.api.ScoreInfrastructureError if kind == "score" else RuntimeError
            error_type = (ValueError if change == "type" else
                          type("UnitOnlySubclass", (expected,), {}) if change == "subclass"
                          else expected)
            error = error_type("UNIT unrelated origin, not original invalid branch")
            delegate = _invalid_unit_raise
            if change == "spoofed-code":
                reference, path, line = _invalid_raise_line(context.api, kind)
                code = delegate.__code__.replace(
                    co_filename=str(path), co_firstlineno=line-1,
                    co_name=reference.co_name, co_qualname=reference.co_qualname)
                delegate = FunctionType(code, delegate.__globals__)
            task = _invalid_task(context, delegate(error, scope, case.result))
            await asyncio.gather(task, return_exceptions=True)
            assert task.exception() is error
            if change == "spoofed-code":
                tb = _invalid_last_tb(error)
                assert tb.tb_frame.f_code is not reference
                assert tb.tb_frame.f_code.co_filename == str(path) and tb.tb_lineno == line
                assert tb.tb_frame.f_locals["scope"] is scope
                assert tb.tb_frame.f_locals["result"] is case.result
            setattr(scope, "task_score" if kind == "score" else "cleanup_task", task)
        controller = _invalid_controller(context, case)
        await _invalid_observe_settle(context, controller, case)
        if mutation in ("score-line", "cleanup-line"):
            error = case.score_error if mutation == "score-line" else case.cleanup_error
            task = scope.task_score if mutation == "score-line" else scope.cleanup_task
            code, path, line = _invalid_raise_line(
                context.api, "score" if mutation == "score-line" else "cleanup")
            deepest = _invalid_last_tb(error)
            assert deepest.tb_frame.f_code is code and deepest.tb_lineno == line
            assert Path(code.co_filename).resolve() == path
            original = error.__traceback__

            def corrupt_line(tb):
                return TracebackType(
                    corrupt_line(tb.tb_next) if tb.tb_next is not None else None,
                    tb.tb_frame, tb.tb_lasti, tb.tb_lineno if tb.tb_next is not None else tb.tb_lineno+1)
            error.__traceback__ = corrupt_line(original)  # Explicit negative UNIT corruption.
            corrupted = _invalid_last_tb(error)
            assert corrupted.tb_frame is deepest.tb_frame
            assert corrupted.tb_frame.f_code is code
            assert corrupted.tb_lineno == line+1 and corrupted.tb_lineno != line
            assert task.exception() is error  # No result()/await can erase corruption.
        if mutation in ("scope-result", "owner-result"):
            replacement = _invalid_wire("gold_error").result
            assert replacement == case.result and replacement is not case.result
            if mutation == "scope-result":
                scope.result = replacement
            else:
                case.owner._completion.outcome.result = replacement
        elif mutation == "forged-score":
            scope.task_score = SimpleNamespace(
                done=lambda: True, cancelled=lambda: False, exception=lambda: case.score_error)
        elif mutation in ("pending-cleanup", "pending-harness"):
            gate = asyncio.Event()
            context.gates.append(gate)
            task = _invalid_task(context, gate.wait(), "scope-drain"
                                 if mutation == "pending-cleanup" else None)
            setattr(scope, "cleanup_task" if mutation == "pending-cleanup" else "harness_score", task)
            assert not task.done()
        elif mutation == "settled-error":
            controller.settled_error = RuntimeError(*case.cleanup_error.args)
        before = tuple(context.retirement.errors), context.retirement.primary
        if mutation == "none":
            assert controller.check_provenance() is None
        else:
            with pytest.raises(AssertionError):
                controller.check_provenance()
        assert tuple(context.retirement.errors) == before[0]
        assert context.retirement.primary is before[1]
    _invalid_run(_invalid_unit_api, scenario)


# Group 3b: exact identity SET, not length or primary ordering, fresh every call.
@pytest.mark.parametrize("mutation", [
    "primary-score", "primary-cleanup", "duplicates", "extra-identity",
    "wrong-stage", "duplicate-wrong-stage", "missing-score", "missing-cleanup",
    "missing-both", "foreign-primary", "missing-primary", "same-error-twice",
])
def test_invalid_failure_ledger(_invalid_unit_api, mutation):
    async def scenario(context):
        case = await _invalid_unit_case(context)
        await _invalid_finish(context, case)
        controller = _invalid_controller(context, case)
        await _invalid_observe_settle(context, controller, case)
        assert controller.check_provenance() is None
        retirement = context.retirement
        # ORIGINAL recorder has retained these exact task errors, no test-authored ACK.
        assert {id(error) for _, error in retirement.errors} == {
            id(case.score_error), id(case.cleanup_error)}
        assert all(stage == "task" for stage, _ in retirement.errors)
        assert controller.check_ledger() is None
        if mutation == "primary-score":
            retirement.primary = case.score_error  # UNIT ledger input permutation only.
        elif mutation == "primary-cleanup":
            retirement.primary = case.cleanup_error
        elif mutation == "duplicates":
            retirement.errors.extend([
                ("task", case.score_error), ("task", case.cleanup_error),
                ("task", case.score_error), ("task", case.cleanup_error)])
        elif mutation == "extra-identity":
            retirement.errors.append(("task", context.api.ScoreInfrastructureError(*case.score_error.args)))
        elif mutation in ("wrong-stage", "duplicate-wrong-stage"):
            if mutation == "wrong-stage":
                retirement.errors[0] = ("host", retirement.errors[0][1])
            else:
                retirement.errors.append(("acceptance", case.score_error))
        elif mutation.startswith("missing-"):
            if mutation == "missing-primary":
                retirement.primary = None
            else:
                removed = (case.score_error,) if mutation == "missing-score" else (
                    (case.cleanup_error,) if mutation == "missing-cleanup"
                    else (case.score_error, case.cleanup_error))
                retirement.errors[:] = [(stage, error) for stage, error in retirement.errors
                                        if not any(error is value for value in removed)]
        elif mutation == "foreign-primary":
            retirement.primary = RuntimeError(*case.cleanup_error.args)
        else:
            assert mutation == "same-error-twice"
            retirement.errors[:] = [("task", case.score_error), ("task", case.score_error)]
        before = tuple(retirement.errors), retirement.primary
        if mutation in ("primary-score", "primary-cleanup", "duplicates"):
            assert controller.check_ledger() is None
        else:
            with pytest.raises(AssertionError):
                controller.check_ledger()
        assert tuple(retirement.errors) == before[0] and retirement.primary is before[1]
    _invalid_run(_invalid_unit_api, scenario)


# Group 3c: SOURCE predicate only, not four actor cases or parent runtime proof.
@pytest.mark.parametrize("status", _INVALID_UNIT_STATUSES)
def test_invalid_positive_refusal_source_contract(status):
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    tree = ast.parse(path.read_text(), filename=str(path))
    driver, = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "_owned_guest_case"]
    predicate = ast.parse(
        'result.get("ok") is True and process.returncode == 0', mode="eval").body
    candidates = []
    for node in ast.walk(driver):
        if not isinstance(node, ast.If) or len(node.body) != 1:
            continue
        raised = node.body[0]
        if (isinstance(raised, ast.Raise) and isinstance(raised.exc, ast.Call)
                and isinstance(raised.exc.func, ast.Name) and raised.exc.func.id == "AssertionError"
                and len(raised.exc.args) == 1 and isinstance(raised.exc.args[0], ast.Name)
                and raised.exc.args[0].id == "result" and not raised.exc.keywords):
            candidates.append((node, raised))
    environment = dict(
        phase="sdk-invalid-" + status, expected_ok=True,
        result=dict(ok=False, safe=True), process=SimpleNamespace(returncode=1))
    applicable = [(node, raised) for node, raised in candidates if eval(
        compile(ast.Expression(body=node.test), str(path), "eval"), {}, environment)]
    assert len(applicable) == 1, "SDK_INVALID_PARENT_EXPLICIT_SAME_DICT_REFUSAL_MISSING"
    node, raised = applicable[0]
    assert any(isinstance(child, ast.UnaryOp) and isinstance(child.op, ast.Not)
               and ast.dump(child.operand) == ast.dump(predicate) for child in ast.walk(node.test))
    assert raised.exc.args[0].id == "result"  # SAME dict, not copied/rendered.
    environment.update(result=dict(ok=True, safe=True), process=SimpleNamespace(returncode=0))
    assert not eval(compile(ast.Expression(body=node.test), str(path), "eval"), {}, environment)


def _invalid_target_views(case):
    """UNIT episode/JSONL receivers, one target plus unrelated successful sibling."""
    other = SimpleNamespace(
        task=SimpleNamespace(data=object()), ok=True,
        traces=[SimpleNamespace(id="unit-unrelated", ok=True,
                                rewards={"execution_accuracy": SimpleNamespace(score=1.0)})])
    episode = SimpleNamespace(task=case.task, ok=False, traces=[case.trace])
    row = dict(ok=False, traces=[dict(id=case.trace.id, ok=False, rewards={})])
    sibling_row = dict(ok=True, traces=[dict(
        id="unit-unrelated", ok=True, rewards={"execution_accuracy": dict(score=1.0)})])
    return [episode, other], [row, sibling_row]


def _invalid_assert_oracle_origin(controller, error):
    """Check exact original method code + trusted independently derived AST gate."""
    assert type(error) is AssertionError and error.args == (_INVALID_REWARD_GATE,)
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py").resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkInvalidStatus"]
    function, = [node for node in cls.body
                 if isinstance(node, ast.FunctionDef) and node.name == "check_target"]
    gates = [node for node in ast.walk(function)
             if isinstance(node, ast.Assert) and isinstance(node.msg, ast.Constant)
             and node.msg.value == _INVALID_REWARD_GATE]
    assert gates
    tb = _invalid_last_tb(error)
    assert tb.tb_frame.f_code is type(controller).check_target.__code__
    assert Path(tb.tb_frame.f_code.co_filename).resolve() == path
    assert tb.tb_lineno in {node.lineno for node in gates}


# Group 4: zero is a reward, not absence. Oracle runs BEFORE invalid provenance.
@pytest.mark.parametrize("mutation", [
    "none", "decoded-valid-zero", "observed-zero", "observed-one", "live-zero",
    "live-other-reward", "persisted-zero", "episode-success", "trace-success",
    "row-success", "persisted-trace-success",
])
def test_invalid_oracle_rejects_zero_reward(_invalid_unit_api, mutation):
    async def scenario(context):
        case = await _invalid_unit_case(
            context, "mismatch" if mutation == "decoded-valid-zero" else "gold_error")
        await _invalid_finish(context, case, invalid=mutation != "decoded-valid-zero")
        controller = _invalid_controller(context, case)
        episodes, rows = _invalid_target_views(case)
        target_rewards = list(case.rewards)
        if mutation == "decoded-valid-zero":
            assert case.result.status == "mismatch" and case.result.valid is True
            assert case.rewards == [("execution_accuracy", 0.0)]
            assert case.scope.task_score.exception() is case.scope.cleanup_task.exception() is None
        elif mutation.startswith("observed-"):
            target_rewards.append(("execution_accuracy", 0.0 if mutation == "observed-zero" else 1.0))
        elif mutation == "live-zero":
            case.trace.rewards["execution_accuracy"] = SimpleNamespace(score=0.0)
        elif mutation == "live-other-reward":
            case.trace.rewards["any_other_reward"] = SimpleNamespace(score=0.0)
        elif mutation == "persisted-zero":
            rows[0]["traces"][0]["rewards"]["execution_accuracy"] = dict(score=0.0)
        elif mutation == "episode-success":
            episodes[0].ok = True
        elif mutation == "trace-success":
            case.trace.ok = True
        elif mutation == "row-success":
            rows[0]["ok"] = True
        elif mutation == "persisted-trace-success":
            rows[0]["traces"][0]["ok"] = True
        if mutation == "none":
            assert controller.check_target(
                episodes=episodes, rows=rows, target_rewards=target_rewards) is None
        else:
            with pytest.raises(AssertionError) as caught:
                controller.check_target(episodes=episodes, rows=rows, target_rewards=target_rewards)
            if mutation in ("decoded-valid-zero", "observed-zero", "observed-one",
                            "live-zero", "live-other-reward", "persisted-zero"):
                _invalid_assert_oracle_origin(controller, caught.value)
    _invalid_run(_invalid_unit_api, scenario)


# Group 5: two real unit Task holds; original delegates/errors are never replayed.
@pytest.mark.parametrize("mode", [
    "normal", "retire-owner", "retire-env", "retire-release-error", "owner-error",
    "target-settle-success", "non-target-success", "non-target-error",
])
def test_invalid_barrier_controller(_invalid_unit_api, mode):
    async def scenario(context):
        from ptc.test_owned_sql_sdk_protocol import _turn
        case = await _invalid_unit_case(context)
        previous_release = AssertionError("UNIT previous retirement release error")

        def original_release():
            context.calls["previous-release"] += 1
            if mode == "retire-release-error":
                raise previous_release
        context.retirement.release = original_release
        controller = _invalid_controller(context, case)
        assert all(isinstance(getattr(controller, name), asyncio.Event)
                   for name in ("owner_held", "owner_release", "env_held", "env_release"))
        sentinel = object()  # UNIT public return value, explicitly NOT an ACK.
        delegate_error = ValueError("UNIT original public delegate error")

        async def original_owner(actual):
            assert actual is case.owner
            context.calls["owner-delegate"] += 1
            if mode == "owner-error":
                raise delegate_error
            return sentinel

        if mode.startswith("non-target-"):
            async def unrelated():
                if mode == "non-target-error":
                    raise delegate_error
                return sentinel
            other = _invalid_task(context, unrelated())
            joins = []

            async def original_non_target_settle(task):
                joins.append(task)
                return await context.api._settle(task)
            observed = _invalid_task(
                context, controller.settle_cleanup(other, original_non_target_settle))
            value, = await asyncio.gather(observed, return_exceptions=True)
            assert value is (delegate_error if mode == "non-target-error" else sentinel)
            assert joins == [other]
            assert not controller.env_held.is_set() and not controller.env_release.is_set()
            assert not controller.owner_held.is_set()
            return

        public_tasks = []
        async def before_return():
            # Match real ordering: Task.score owns this callback BEFORE public
            # owner close starts. Never race a fabricated pre-score owner hold.
            public = _invalid_unregistered_task(
                context, controller.close_owner(case.owner, original_owner))
            public_tasks.append(public)
            assert await public is sentinel
        case.before_score_return = before_return
        score_task = _invalid_unregistered_task(
            context, case.score(case.task, case.trace, case.runtime))
        await controller.owner_held.wait()
        public, = public_tasks
        await _turn()
        assert case.scope.task_score is score_task
        assert score_task in context.retirement.tasks and public in context.retirement.tasks
        assert context.retirement.task_roles[public] == ("cleanup", "owner-close")
        assert not public.done() and public.cancelling() == 0
        assert context.calls["owner-delegate"] == 0
        assert case.owner._completion.outcome.result is case.result and case.scope.result is None
        assert not case.rewards and not case.trace.rewards
        replay = _invalid_task(context, controller.close_owner(case.owner, original_owner))
        with pytest.raises(AssertionError):
            await replay
        assert context.calls["owner-delegate"] == 0
        if mode in ("retire-owner", "retire-release-error"):
            context.retirement.request()  # ORIGINAL retirement calls composed release.
            await _turn()
            assert controller.owner_release.is_set() and controller.env_release.is_set()
            assert context.calls["previous-release"] == 1
        else:
            controller.owner_release.set()
        public_value, = await asyncio.gather(public, return_exceptions=True)
        assert public_value is (delegate_error if mode == "owner-error" else sentinel)
        assert context.calls["owner-delegate"] == 1 and public.cancelling() == 0
        if mode == "owner-error":
            value, = await asyncio.gather(score_task, return_exceptions=True)
            assert value is delegate_error  # Never swallowed or translated.
            assert len(case.scorer.close_tasks) == 1
            return
        await _invalid_finish(context, case)
        assert case.scope.task_score is score_task
        assert case.scope.cleanup_task.done() and len(case.scorer.close_tasks) == 1
        if mode == "target-settle-success":
            async def original_cleanup_success():
                return sentinel
            case.scope.cleanup_task = _invalid_task(
                context, original_cleanup_success(), "scope-drain")
        joins = []

        async def original_settle(task):
            joins.append(task)
            return await context.api._settle(task)

        rows = []

        async def unit_writer_receiver():
            try:
                value = await controller.settle_cleanup(case.scope.cleanup_task, original_settle)
            except BaseException:
                rows.append("UNIT failed Env returned")
                raise
            rows.append("UNIT Env returned")
            return value

        env = _invalid_task(context, unit_writer_receiver())
        await controller.env_held.wait()
        assert case.scope.cleanup_task.done() and case.scope.cleanup_task in context.retirement.tasks
        assert joins == [case.scope.cleanup_task]
        if mode not in ("retire-owner", "retire-release-error"):
            assert not env.done() and rows == []
            if mode == "target-settle-success":
                assert controller.settled_result is sentinel and controller.settled_error is None
            else:
                assert controller.settled_error is case.cleanup_error
            replay = _invalid_task(
                context, controller.settle_cleanup(case.scope.cleanup_task, original_settle))
            with pytest.raises(AssertionError):
                await replay
            assert joins == [case.scope.cleanup_task]
        if mode == "retire-env":
            context.retirement.request()
            await _turn()
            assert controller.owner_release.is_set() and controller.env_release.is_set()
            assert context.calls["previous-release"] == 1
        controller.release()
        controller.release()
        value, = await asyncio.gather(env, return_exceptions=True)
        assert value is (sentinel if mode == "target-settle-success" else case.cleanup_error)
        assert len(rows) == 1 and joins == [case.scope.cleanup_task]
        assert len(case.scorer.close_tasks) == context.calls["owner-delegate"] == 1
        assert all(task.done() and task.cancelling() == 0 for task in (
            public, score_task, case.scope.cleanup_task, env))
        if mode == "retire-release-error":
            assert any(stage == "release" and error is previous_release
                       for stage, error in context.retirement.errors)
    _invalid_run(_invalid_unit_api, scenario)


# ORIGINAL SDK SCORING TIMEOUT: TEST AUTHORING ONLY.
# Seven groups, no actors, native owners/ACKs, SDK/source hooks or timer patches.
# Existing tests above, including the post-settle cleanup-line repair, frozen.
# Real 0.1s asyncio timers below are UNIT drain/provenance evidence ONLY.
# Missing _SdkScoringTimeout is NEW-FEATURE missing-API RED, not a bug RED.
#
# Minimal FUTURE canonical-only class (AST extracted alone, no new globals):
# _SdkScoringTimeout(*, api, retirement, scope, owner)
# static configure(config, *, draw, public_data, instrument) -> model-copied
# config, scoring EXACTLY 0.1, num_tasks7/rollout1/shuffleFalse/concurrency2.
# Validate complete ordered 8/7/1 metadata; do not mutate inputs/native settings.
# request_cancel(actual, reason, delegate, release_controller): delegate FIRST;
# retain SAME real caller_cancelled receipt/intent/current task BEFORE release;
# release once per owner. Other reasons delegate unchanged, never release.
# score_cancelled(scope, task, error): retain original children/cancellation.
# async close_owner(actual, delegate): retain actual public task/children,
# hold before delegate, reject replay before delegation, preserve return/error.
# record_error(trace, error, delegate): retain SAME actual error, delegate once;
# defer completed-chain qualification to check_provenance().
# async settle_cleanup(task, delegate): exact target cleanup only, ORIGINAL
# settle first, retain result/error, then hold before unchanged Env return.
# checkpoint(*, rows) -> bounded facts below; snapshot ACTUAL held state once.
# check_public_return(): late literal assert SDK_TIMEOUT_PUBLIC_RETURN_BARRIER
# over retained checkpoint, not current post-drain state.
# check_provenance(): exact TaskError -> TimeoutError -> observed CancelledError;
# trusted ORIGINAL boundary / Rollout.close / wait_for code+AST locations,
# original scope/trace/children identities; no result/reward, completed original
# drain/resources, cancelled Task.score, SUCCEEDED Harness.score/Agent/drain.
# Fresh retirement primary MUST be None and errors EMPTY, no timeout whitelist.
# release(): idempotent, no tasks/cancel; compose previous retirement.release
# with unconditional own release in finally. Events owner_held/owner_release,
# env_held/env_release; public_task, receipt, request_task, score_cancel, error,
# settled_result/settled_error. None of these UNIT receivers claim native ACKs.
_SCORING_TIMEOUT_GATE = "SDK_TIMEOUT_PUBLIC_RETURN_BARRIER"


def _scoring_timeout_type():
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    namespace = _repair_namespace(
        path.name, ["_SdkScoringTimeout"], extra={"__file__": str(path.resolve())})
    return namespace["_SdkScoringTimeout"]


def _scoring_timeout_context(api):
    loop, retirement, calls = _repair_case()
    return SimpleNamespace(
        api=api, loop=loop, retirement=retirement, calls=calls,
        cases=[], controllers=[], gates=[], hygiene_tasks=[])


def _scoring_timeout_hygiene(context):
    # Resolve ORIGINAL gates even if the release method UNDER TEST is broken.
    for controller in context.controllers:
        controller.owner_release.set()
        controller.env_release.set()
    for gate in context.gates:
        gate.set()
    for task in context.hygiene_tasks:
        context.retirement.retain_task(task)  # AFTER assertions only.
    _repair_hygiene(context.loop, context.retirement, [])


def _scoring_timeout_owner():
    import uuid
    # Explicit UNIT receiver of the ORIGINAL public request_cancel method.
    # No execute/controller/thread/endpoint/completion or manufactured ACK.
    return SimpleNamespace(
        _lock=threading.Lock(), _completion=None, _intent=None, _state="NEW",
        _endpoints=[], invocation_id=uuid.uuid4())


def _scoring_timeout_scope(api):
    data = SimpleNamespace(name="UNIT_ONLY_timeout", prompt="UNIT ONLY", idx=0)
    trace = SimpleNamespace(
        id="unit-timeout-" + str(id(data)), task=SimpleNamespace(data=data),
        errors=[], rewards={}, ok=True, last_error=None, stop_condition=None,
        reward=0.0, num_turns=0, state=SimpleNamespace(artifacts=[]),
        is_completed=False)
    trace.timing = SimpleNamespace(**{
        name: SimpleNamespace(start=1.0, end=None)
        for name in ("boot", "setup", "agent", "finalize", "scoring")})
    trace.notify = lambda: None
    trace.split_agent_time = lambda: None
    trace.stop = lambda reason: setattr(trace, "stop_condition", reason)
    scope = SimpleNamespace(
        data=data, task=SimpleNamespace(data=data), trace=trace, runtime=None,
        harness=None, task_score=None, harness_score=None, agent_task=None,
        cleanup_task=None, result=None, published=False, failed=False,
        scorer=None, finalized=True, harness_success=False, harness_done=asyncio.Event(),
        live=True, authority=True, token=object(), closes=api._CloseSet())

    def fail():
        scope.failed, scope.authority = True, False
    scope.fail = fail
    return scope


def _scoring_timeout_controller(context, scope, owner):
    # Resolve OUTSIDE expected-refusal contexts. No optional/missing-API fallback.
    controller = _scoring_timeout_type()(
        api=context.api, retirement=context.retirement, scope=scope, owner=owner)
    context.controllers.append(controller)
    return controller


async def _scoring_timeout_case(context, *, held_resource=False):
    """Original SDK close/fail/boundary, explicit UNIT task/trace/runtime only."""
    from contextlib import AsyncExitStack
    from types import MethodType
    from ptc import sql_isolation as core
    from ptc.test_owned_sql_sdk_protocol import _UnitResource
    from verifiers.v1.rollout import Rollout
    from verifiers.v1.trace import Trace

    scope, owner = _scoring_timeout_scope(context.api), _scoring_timeout_owner()
    controller = _scoring_timeout_controller(context, scope, owner)
    case = SimpleNamespace(
        scope=scope, owner=owner, controller=controller, rows=[], recorded_errors=[],
        public_tasks=[], original_receipts=[], prestart=threading.Event(),
        calls=Counter(), cancel_error=None, early_hits=0)
    context.cases.append(case)

    class UnitOnlyResource(_UnitResource):
        async def aclose(self):
            context.retirement.retain_cleanup(asyncio.current_task(), "resource-close")
            return await super().aclose()

    case.runner = UnitOnlyResource()
    case.scorer = UnitOnlyResource(held_close=held_resource)
    scope.scorer = case.scorer
    context.gates.extend([case.runner.close_release, case.scorer.close_release])
    scope.closes.retain(case.runner)
    scope.closes.retain(case.scorer)
    await scope.closes.start(case.runner)  # Original ordinary runner already closed.
    never = asyncio.Event()
    context.gates.append(never)

    def release_controller():
        receipt = case.original_receipts[-1]
        assert controller.receipt is receipt and controller.request_task is scope.task_score
        assert receipt.intent is owner._intent and receipt.intent.reason == "caller_cancelled"
        assert receipt.intent.deadline_ns == receipt.intent.requested_ns + 12_000_000_000
        case.calls["controller-release"] += 1
        case.prestart.set()  # UNIT gate only, no native START or owned controller.

    def original_request(actual, reason):
        receipt = core.OwnedSqlInvocation.request_cancel(actual, reason)
        case.original_receipts.append(receipt)
        return receipt

    async def original_public(actual):
        assert actual is owner and case.prestart.is_set()
        case.calls["public-delegate"] += 1
        return None  # UNIT public return, explicitly NOT an ACK.
    case.original_public = original_public

    async def score(trace, runtime):
        assert trace is scope.trace and runtime is scope.runtime
        scope.task_score = asyncio.current_task()
        context.hygiene_tasks.append(scope.task_score)
        try:
            await never.wait()
        except asyncio.CancelledError as error:
            case.cancel_error = error
            scope.fail()
            controller.score_cancelled(scope, scope.task_score, error)
            controller.request_cancel(owner, "caller_cancelled", original_request, release_controller)
            public = _invalid_unregistered_task(context, controller.close_owner(owner, original_public))
            case.public_tasks.append(public)
            try:
                await context.api._settle(public)
            finally:
                await context.api._join_resource(scope, case.scorer)
            raise  # ORIGINAL cancellation object, never translated to an ExResult.

    async def finalize(trace, runtime):
        assert trace is scope.trace and runtime is scope.runtime

    async def harness_score(trace, runtime):
        assert trace is scope.trace and runtime is scope.runtime
        scope.harness_score = asyncio.current_task()
        context.hygiene_tasks.append(scope.harness_score)
        scope.harness_success = True
        scope.harness_done.set()
        return None  # Completed harness must NOT be claimed cancelled.

    async def harness_cleanup(trace, runtime):
        case.calls["harness-cleanup"] += 1

    async def runtime_stop():
        case.calls["runtime-stop"] += 1

    scope.task.score, scope.task.finalize = score, finalize
    scope.harness = SimpleNamespace(score=harness_score, cleanup=harness_cleanup)
    scope.runtime = SimpleNamespace(stop=runtime_stop)

    def original_record(trace, error):
        assert trace is scope.trace
        case.recorded_errors.append(error)
        value = Trace.record_error(trace, error)  # ORIGINAL SDK recorder on UNIT receiver.
        trace.last_error = trace.errors[-1]
        return value

    scope.trace.record_error = lambda error: controller.record_error(
        scope.trace, error, original_record)
    receiver = SimpleNamespace(
        _closed=False, _failed=False, _opened=True, _failure=None,
        _harness_session=None, _stack=AsyncExitStack(), _collect_artifacts=False,
        _borrowed_runtime=None, _timeouts=SimpleNamespace(finalize=5.0, scoring=0.1),
        task=scope.task, harness=scope.harness, runtime=scope.runtime, trace=scope.trace)
    receiver.fail = MethodType(Rollout.fail, receiver)
    case.sdk_receiver = receiver
    scope.agent_task = _invalid_unregistered_task(context, Rollout.close(receiver))

    async def unit_env_and_writer():
        try:
            result = await asyncio.shield(scope.agent_task)
        finally:
            scope.authority = False
            scope.closes.start_all()
            scope.cleanup_task = context.loop.create_task(context.api._drain_scope(scope))
            context.hygiene_tasks.append(scope.cleanup_task)
            await controller.settle_cleanup(scope.cleanup_task, context.api._settle)
            scope.live, scope.token = False, None
        case.rows.append(dict(ok=result.ok, traces=[dict(
            id=result.id, ok=result.ok, rewards=dict(result.rewards))]))
        return result
    case.env = _invalid_unregistered_task(context, unit_env_and_writer())
    return case


async def _scoring_timeout_finish(context, case):
    controller, scope = case.controller, case.scope
    controller.owner_release.set()
    await controller.env_held.wait()
    assert scope.cleanup_task.done() and scope.cleanup_task.exception() is None
    assert scope.cleanup_task in context.retirement.tasks
    assert not case.env.done() and case.rows == [] and scope.live
    assert all(task.done() and not task.cancelled() and task.result() is None
               for _, task in scope.closes._entries)
    assert controller.settled_result is None and controller.settled_error is None
    controller.env_release.set()
    assert await case.env is scope.trace
    assert scope.task_score.cancelled()
    assert scope.harness_score.done() and not scope.harness_score.cancelled()
    assert scope.harness_score.result() is None
    assert scope.agent_task.result() is scope.trace
    assert not scope.live and scope.token is None and scope.result is None
    assert not scope.published and scope.trace.rewards == {}
    assert case.rows == [dict(ok=False, traces=[dict(
        id=scope.trace.id, ok=False, rewards={})])]
    assert case.calls["public-delegate"] == case.calls["controller-release"] == 1
    assert len(case.runner.close_tasks) == len(case.scorer.close_tasks) == 1
    context.retirement._observe_task_errors()
    assert context.retirement.primary is None and context.retirement.errors == []


def _scoring_timeout_original_chain(case):
    """Independent original code/AST/identity proof, never rendered error text."""
    from verifiers.v1.errors import TaskError, boundary
    from verifiers.v1.rollout import Rollout
    error, = case.recorded_errors
    assert error is case.controller.error is case.sdk_receiver._failure
    assert type(error) is TaskError
    timeout = error.__cause__
    assert type(timeout) is TimeoutError
    assert type(timeout.__cause__) is asyncio.CancelledError
    assert timeout.__cause__ is case.cancel_error is case.controller.score_cancel
    boundary_code = boundary.__wrapped__.__code__
    boundary_path = Path(boundary_code.co_filename).resolve()
    tree = ast.parse(boundary_path.read_text(), filename=str(boundary_path))
    function, = [node for node in tree.body
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "boundary"]
    handler, = [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)
                and isinstance(node.type, ast.Name) and node.type.id == "TimeoutError"]
    gate, = [node for node in handler.body if isinstance(node, ast.Raise)]
    tb = _invalid_last_tb(error)
    assert tb.tb_frame.f_code is boundary_code and tb.tb_lineno == gate.lineno
    assert handler.name == "e" and isinstance(gate.cause, ast.Name)
    assert gate.cause.id == handler.name
    assert tb.tb_frame.f_locals["error_cls"] is TaskError
    assert tb.tb_frame.f_locals["what"] == "scoring"
    close_code = Rollout.close.__code__
    close_path = Path(close_code.co_filename).resolve()
    tree = ast.parse(close_path.read_text(), filename=str(close_path))
    cls, = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Rollout"]
    method, = [node for node in cls.body
               if isinstance(node, ast.AsyncFunctionDef) and node.name == "close"]
    call, = [node for node in ast.walk(method) if isinstance(node, ast.Await)
             and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
             and node.value.func.attr == "wait_for"]
    frames = []
    tb = timeout.__traceback__
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next
    close, = [tb for tb in frames if tb.tb_frame.f_code is close_code]
    assert close.tb_lineno == call.lineno
    assert close.tb_frame.f_locals["self"] is case.sdk_receiver
    waiter, = [tb for tb in frames if tb.tb_frame.f_code is asyncio.wait_for.__code__]
    path = Path(asyncio.wait_for.__code__.co_filename).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    function, = [node for node in tree.body
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "wait_for"]
    gate, = [node for node in function.body if isinstance(node, ast.AsyncWith)]
    assert waiter.tb_lineno == gate.lineno
    assert waiter.tb_frame.f_locals["timeout"] == 0.1
    children = waiter.tb_frame.f_locals["fut"]._children
    assert len(children) == 2 and children[0] is case.scope.task_score
    assert children[1] is case.scope.harness_score
    return SimpleNamespace(boundary=boundary_code, boundary_line=handler.body[0].lineno,
                           timeout=timeout, wait_for=asyncio.wait_for.__code__)


def _scoring_timeout_oracle_origin(controller, error):
    assert type(error) is AssertionError and error.args == (_SCORING_TIMEOUT_GATE,)
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py").resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_SdkScoringTimeout"]
    method, = [node for node in cls.body
               if isinstance(node, ast.FunctionDef) and node.name == "check_public_return"]
    gate, = [node for node in ast.walk(method) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant) and node.msg.value == _SCORING_TIMEOUT_GATE]
    tb = _invalid_last_tb(error)
    assert tb.tb_frame.f_code is type(controller).check_public_return.__code__
    assert Path(tb.tb_frame.f_code.co_filename).resolve() == path and tb.tb_lineno == gate.lineno


# Group 1: config model-copy + ORIGINAL admission guard, UNIT metadata, no SQL.
@pytest.mark.parametrize("mutation", [
    "none", "selected-six", "planned-seven", "excluded-zero", "data-order",
    "num-tasks-six", "two-rollouts", "shuffle", "concurrency-one",
])
def test_scoring_timeout_configuration_admission(_invalid_unit_api, tmp_path, mutation):
    from train.sql_episodes import InstrumentSettings
    from verifiers.v1.task import TaskData
    cls = _scoring_timeout_type()  # Missing feature is NOT an expected rejection.
    namespace = _repair_namespace("test_owned_sql_sdk_canonical.py", ["ID", "_config"])
    instrument = InstrumentSettings(
        action_cap=2, action_max_rows=3, scorer_max_rows=9, compare="multiset",
        scorer_timeout_s=3.0, program_timeout_s=5.0, wrapper_timeout_s=1.25,
        python_version="UNIT_ONLY", sqlite_version="UNIT_ONLY",
        source_paths=("ptc/sql_isolation.py",), source_sha256="a" * 64)
    # UNIT metadata, not a fabricated ValidatedDraw or runtime admission claim.
    planned = tuple(SimpleNamespace(name=f"UNIT_ONLY_{i}", question=f"UNIT ONLY {i}")
                    for i in range(8))
    draw = SimpleNamespace(planned=planned, eligible=planned[:7], exclusions=(planned[7],))
    public = tuple(TaskData(name=row.name, prompt=row.question) for row in draw.eligible)
    config = namespace["_config"](tmp_path, _invalid_unit_api, instrument, 1)
    if mutation == "selected-six":
        draw.eligible = draw.eligible[:6]
    elif mutation == "planned-seven":
        draw.planned = draw.planned[:7]
    elif mutation == "excluded-zero":
        draw.exclusions = ()
    elif mutation == "data-order":
        public = public[::-1]
    elif mutation == "num-tasks-six":
        config.num_tasks = 6
    elif mutation == "two-rollouts":
        config.num_rollouts = 2
    elif mutation == "shuffle":
        config.shuffle = True
    elif mutation == "concurrency-one":
        config.max_concurrent = 1
    before = config.model_dump(mode="json")
    native_before = dict(vars(instrument))
    retained = draw.planned, draw.eligible, draw.exclusions, public
    if mutation == "none":
        actual = cls.configure(config, draw=draw, public_data=public, instrument=instrument)
        assert actual is not config and type(actual) is type(config)
        expected = json.loads(json.dumps(before))
        expected["num_tasks"] = 7
        expected["env"]["agent"]["timeout"]["scoring"] = 0.1
        assert actual.model_dump(mode="json") == expected
        assert type(actual.env.agent.timeout.scoring) is float
        assert actual.env.agent.timeout.scoring == 0.1
        assert (actual.num_tasks, actual.num_rollouts, actual.shuffle,
                actual.max_concurrent) == (7, 1, False, 2)
        assert _invalid_unit_api._supported(
            actual, SimpleNamespace(data=public, instrument=instrument)) is None
        assert tuple(row.name for row in draw.eligible) == tuple(data.name for data in public)
    else:
        with pytest.raises(AssertionError):
            cls.configure(config, draw=draw, public_data=public, instrument=instrument)
    assert config.model_dump(mode="json") == before
    assert vars(instrument) == native_before
    assert instrument.scorer_timeout_s == 3.0 and instrument.program_timeout_s == 5.0
    assert (draw.planned, draw.eligible, draw.exclusions, public) == retained


# Group 2: actual wait_for(0.1), no future API and no mocked timer.
@pytest.mark.parametrize("shape", ("child", "gather-with-successful-harness"))
def test_scoring_timeout_original_wait_for_drain(_invalid_unit_api, shape):
    async def scenario(context):
        from ptc.test_owned_sql_sdk_protocol import _UnitResource, _turn
        resource = _UnitResource(held_close=True)
        context.gates.append(resource.close_release)
        cancelled, never = asyncio.Event(), asyncio.Event()
        context.gates.append(never)
        observed, cleanup_tasks = [], []

        async def child():
            try:
                await never.wait()
            except asyncio.CancelledError as error:
                observed.append(error)
                cleanup = _invalid_task(context, resource.aclose(), "resource-close")
                cleanup_tasks.append(cleanup)
                cancelled.set()
                await context.api._settle(cleanup)
                raise

        async def harness():
            return None

        worker = _invalid_task(context, child())
        sibling = _invalid_task(context, harness()) if shape != "child" else None
        future = worker if sibling is None else asyncio.gather(worker, sibling)
        original = asyncio.wait_for
        started = time.monotonic()
        waiter = _invalid_task(context, original(future, 0.1))
        await cancelled.wait()
        await resource.close_entered.wait()
        await _turn()
        cleanup, = cleanup_tasks
        assert time.monotonic() - started >= 0.09  # Real 0.1 timer fired.
        assert not waiter.done() and not worker.done()
        assert worker.cancelling() == 1 and not worker.cancelled()
        assert cleanup in context.retirement.tasks and not cleanup.done()
        assert cleanup.cancelling() == 0 and resource.close_tasks == [cleanup]
        if sibling is not None:
            assert sibling.done() and not sibling.cancelled() and sibling.result() is None
        resource.close_release.set()
        value, = await asyncio.gather(waiter, return_exceptions=True)
        assert type(value) is TimeoutError and type(value.__cause__) is asyncio.CancelledError
        assert value.__cause__ is observed[0]
        assert worker.cancelled() and cleanup.done() and cleanup.result() is None
        assert cleanup.cancelling() == 0 and asyncio.wait_for is original
    _invalid_run(_invalid_unit_api, scenario)


# Group 3: real original CancelIntent/Receipt, no native invocation or ACK.
@pytest.mark.parametrize("mode", (
    "accepted", "repeated", "runner-closed", "foreign-owner",
    "receipt-type", "deadline", "requested-ns",
))
def test_scoring_timeout_intent_before_controller_release(_invalid_unit_api, mode):
    async def scenario(context):
        from ptc import sql_isolation as core
        scope, owner = _scoring_timeout_scope(context.api), _scoring_timeout_owner()
        scope.task_score = asyncio.current_task()
        controller = _scoring_timeout_controller(context, scope, owner)
        gate, originals, calls = threading.Event(), [], Counter()
        actual = _scoring_timeout_owner() if mode == "foreign-owner" else owner
        reason = "runner_closed" if mode == "runner-closed" else "caller_cancelled"

        def delegate(receiver, why):
            calls["delegate"] += 1
            assert receiver is actual and why == reason and not gate.is_set()
            receipt = core.OwnedSqlInvocation.request_cancel(receiver, why)
            originals.append(receipt)
            if mode == "receipt-type":
                return SimpleNamespace(status=receipt.status, intent=receipt.intent)
            if mode == "deadline":
                object.__setattr__(receipt.intent, "deadline_ns", receipt.intent.deadline_ns+1)
            if mode == "requested-ns":
                object.__setattr__(receipt.intent, "requested_ns", -1)
            return receipt

        def release_controller():
            calls["release"] += 1
            receipt = originals[-1]
            assert calls["delegate"] >= 1 and controller.receipt is receipt
            assert controller.request_task is asyncio.current_task() is scope.task_score
            assert type(receipt) is core.CancelReceipt and type(receipt.intent) is core.CancelIntent
            assert receipt.intent is owner._intent and receipt.intent.reason == "caller_cancelled"
            assert receipt.intent.requested_ns >= 0
            assert receipt.intent.deadline_ns == receipt.intent.requested_ns + 12_000_000_000
            gate.set()

        if mode in ("accepted", "repeated", "runner-closed"):
            receipt = controller.request_cancel(actual, reason, delegate, release_controller)
            assert receipt is originals[0] and calls["delegate"] == 1
            assert calls["release"] == int(mode != "runner-closed")
            assert gate.is_set() is (mode != "runner-closed")
            if mode == "repeated":
                # Original public delegate still runs, but no second gate release.
                repeated = controller.request_cancel(
                    actual, reason, core.OwnedSqlInvocation.request_cancel, release_controller)
                assert repeated.status == "repeated" and repeated.intent is receipt.intent
                assert controller.receipt is receipt and calls["release"] == 1
        else:
            with pytest.raises(AssertionError):
                controller.request_cancel(actual, reason, delegate, release_controller)
            assert calls["delegate"] == 1 and calls["release"] == 0 and not gate.is_set()
        assert owner._completion is None and not owner._endpoints
    _invalid_run(_invalid_unit_api, scenario)


# Group 4: actual public task, original SDK 0.1 drain, no reported error/writer yet.
@pytest.mark.parametrize("mode", (
    "normal", "replayed-close", "foreign-settle-success", "foreign-settle-error",
))
def test_scoring_timeout_public_close_and_env_barriers(_invalid_unit_api, mode):
    async def scenario(context):
        case = await _scoring_timeout_case(context)
        controller, scope = case.controller, case.scope
        await controller.owner_held.wait()  # Reached only AFTER the real SDK timer.
        public, = case.public_tasks
        assert controller.public_task is public and public in context.retirement.tasks
        assert context.retirement.task_roles[public] == ("cleanup", "owner-close")
        assert not public.done() and public.cancelling() == 0
        assert scope.task_score in context.retirement.tasks and not scope.task_score.done()
        assert scope.harness_score in context.retirement.tasks
        assert scope.harness_score.done() and scope.harness_score.result() is None
        assert not scope.harness_score.cancelled() and not scope.agent_task.done()
        assert not case.env.done() and scope.live and case.rows == []
        assert case.recorded_errors == scope.trace.errors == [] and scope.trace.rewards == {}
        assert scope.result is None and not scope.published
        assert case.calls["public-delegate"] == 0 and case.calls["controller-release"] == 1
        sibling_row = dict(ok=True, traces=[dict(
            id="UNIT_ONLY_unrelated", ok=True, rewards={"execution_accuracy": dict(score=1.0)})])
        facts = controller.checkpoint(rows=[sibling_row, *case.rows])
        assert facts == dict(
            public_pending=True, public_uncancelled=True, score_pending=True,
            agent_pending=True, timeout_reported=False, target_writer=False, target_rewards=0)
        if mode == "replayed-close":
            replay = _invalid_unregistered_task(
                context, controller.close_owner(case.owner, case.original_public))
            with pytest.raises(AssertionError):
                await replay
            assert replay not in context.retirement.tasks and case.calls["public-delegate"] == 0
        elif mode.startswith("foreign-settle"):
            sentinel, original_error, joins = object(), ValueError("UNIT_ONLY unrelated settle"), []

            async def unrelated():
                if mode.endswith("error"):
                    raise original_error
                return sentinel

            async def original_settle(task):
                joins.append(task)
                return await context.api._settle(task)
            task = _invalid_unregistered_task(context, unrelated())
            observed = _invalid_unregistered_task(
                context, controller.settle_cleanup(task, original_settle))
            value, = await asyncio.gather(observed, return_exceptions=True)
            assert value is (original_error if mode.endswith("error") else sentinel)
            assert joins == [task] and not controller.env_held.is_set()
        await _scoring_timeout_finish(context, case)
        _scoring_timeout_original_chain(case)
        assert controller.check_provenance() is None
        assert controller.check_public_return() is None  # Retained held facts, not current done.
    _invalid_run(_invalid_unit_api, scenario)


# Group 5: exact original code/AST/chain/identities, including spoofed-code rejection.
@pytest.mark.parametrize("mutation", [
    "none", "task-error-type", "task-error-subclass", "timeout-type", "timeout-subclass",
    "cancel-type", "cancel-subclass", "boundary-origin", "boundary-code", "boundary-line",
    "timeout-origin", "wait-for-line", "score-task", "harness-task", "agent-task",
    "scope", "fabricated-result", "cancel-identity", "pending-drain",
    "retirement-task-error", "retirement-primary",
    "boundary-cause-missing", "boundary-cause-name",
    "wait-for-missing", "wait-for-duplicate",
])
def test_scoring_timeout_failure_provenance(_invalid_unit_api, mutation, monkeypatch):
    async def scenario(context):
        from types import FunctionType, TracebackType
        from bench.score import ExResult
        from verifiers.v1.errors import TaskError
        case = await _scoring_timeout_case(context)
        await case.controller.owner_held.wait()
        case.controller.checkpoint(rows=case.rows)
        await _scoring_timeout_finish(context, case)
        original = _scoring_timeout_original_chain(case)
        controller, scope, error = case.controller, case.scope, case.controller.error
        assert controller.check_provenance() is None

        def unit_raise(error, error_cls, what, e):
            raise error

        def move_origin(actual, *, spoof=False):
            delegate = unit_raise
            if spoof:
                code = delegate.__code__.replace(
                    co_filename=original.boundary.co_filename,
                    co_firstlineno=original.boundary_line-1,
                    co_name=original.boundary.co_name, co_qualname=original.boundary.co_qualname)
                delegate = FunctionType(code, delegate.__globals__)
            actual.__traceback__ = None  # Explicit UNIT corruption, SAME original error object.
            try:
                delegate(actual, TaskError, "scoring", original.timeout)
            except BaseException as caught:
                assert caught is actual
            actual.__traceback__ = _invalid_last_tb(actual)
            if spoof:
                tb = _invalid_last_tb(actual)
                assert tb.tb_frame.f_code is not original.boundary
                assert tb.tb_frame.f_code.co_filename == original.boundary.co_filename
                assert tb.tb_lineno == original.boundary_line

        def corrupt_line(actual, code):
            def change(tb):
                if tb is None:
                    return None
                return TracebackType(
                    change(tb.tb_next), tb.tb_frame, tb.tb_lasti,
                    tb.tb_lineno + int(tb.tb_frame.f_code is code))
            actual.__traceback__ = change(actual.__traceback__)

        if mutation.startswith("task-error-"):
            cls = ValueError if mutation.endswith("type") else type("UnitOnlyTaskError", (TaskError,), {})
            controller.error = cls("UNIT_ONLY not original SDK boundary")
            controller.error.__cause__ = original.timeout
        elif mutation in ("timeout-type", "timeout-subclass"):
            cls = ValueError if mutation == "timeout-type" else type("UnitOnlyTimeout", (TimeoutError,), {})
            error.__cause__ = cls("UNIT_ONLY wrong timeout")
        elif mutation in ("cancel-type", "cancel-subclass", "cancel-identity"):
            cls = (ValueError if mutation == "cancel-type" else
                   type("UnitOnlyCancel", (asyncio.CancelledError,), {})
                   if mutation == "cancel-subclass" else asyncio.CancelledError)
            original.timeout.__cause__ = cls()
        elif mutation in ("boundary-origin", "boundary-code"):
            move_origin(error, spoof=mutation == "boundary-code")
        elif mutation in ("boundary-cause-missing", "boundary-cause-name"):
            original_parse = ast.parse
            boundary_path = Path(original.boundary.co_filename).resolve()
            cause_hits = []

            def corrupted_causal_ast(source, filename="<unknown>", *args, **kwargs):
                tree = original_parse(source, filename, *args, **kwargs)
                if Path(filename).resolve() == boundary_path:
                    function, = [node for node in tree.body
                                 if isinstance(node, ast.AsyncFunctionDef)
                                 and node.name == "boundary"]
                    handler, = [node for node in ast.walk(function)
                                if isinstance(node, ast.ExceptHandler)
                                and isinstance(node.type, ast.Name)
                                and node.type.id == "TimeoutError"]
                    gate, = [node for node in handler.body if isinstance(node, ast.Raise)]
                    gate.cause = (None if mutation == "boundary-cause-missing"
                                  else ast.Name(id="UNIT_ONLY_unrelated_cause", ctx=ast.Load()))
                    cause_hits.append(1)
                return tree
            # Negative UNIT validator input only, never the SDK implementation.
            monkeypatch.setattr(ast, "parse", corrupted_causal_ast)
        elif mutation == "timeout-origin":
            move_origin(original.timeout)
        elif mutation in ("wait-for-missing", "wait-for-duplicate"):
            def changed_waiter(tb):
                if tb is None:
                    return None
                following = changed_waiter(tb.tb_next)
                if tb.tb_frame.f_code is original.wait_for:
                    if mutation == "wait-for-missing":
                        return following
                    following = TracebackType(
                        following, tb.tb_frame, tb.tb_lasti, tb.tb_lineno)
                return TracebackType(following, tb.tb_frame, tb.tb_lasti, tb.tb_lineno)
            original.timeout.__traceback__ = changed_waiter(original.timeout.__traceback__)
            count, tb = 0, original.timeout.__traceback__
            while tb is not None:
                count += tb.tb_frame.f_code is original.wait_for
                tb = tb.tb_next
            assert count == (0 if mutation == "wait-for-missing" else 2)
        elif mutation in ("boundary-line", "wait-for-line"):
            # AFTER every original settle/result read, never erase the corruption.
            corrupt_line(error if mutation == "boundary-line" else original.timeout,
                         original.boundary if mutation == "boundary-line" else original.wait_for)
        elif mutation in ("score-task", "harness-task", "agent-task", "scope"):
            other = await _scoring_timeout_case(context)
            await other.controller.owner_held.wait()
            other.controller.checkpoint(rows=other.rows)
            await _scoring_timeout_finish(context, other)
            if mutation == "scope":
                scope.task = other.scope.task
            else:
                name = {"score-task": "task_score", "harness-task": "harness_score",
                        "agent-task": "agent_task"}[mutation]
                setattr(scope, name, getattr(other.scope, name))
        elif mutation == "fabricated-result":
            scope.result = ExResult(0.0, "mismatch", True, "UNIT_ONLY fabricated return", 7, 11)
        elif mutation == "pending-drain":
            gate = asyncio.Event()
            context.gates.append(gate)
            scope.cleanup_task = _invalid_task(context, gate.wait(), "scope-drain")
        elif mutation == "retirement-task-error":
            # Explicit negative UNIT input: traced TaskError is NOT an allowed
            # retirement error. Never clear/suppress the original ledger.
            context.retirement.errors.append(("task", error))
            context.retirement.primary = error
        elif mutation == "retirement-primary":
            context.retirement.primary = error
        before = tuple(context.retirement.errors), context.retirement.primary
        if mutation == "none":
            assert controller.check_provenance() is None
        else:
            with pytest.raises(AssertionError):
                controller.check_provenance()
        if mutation in ("boundary-cause-missing", "boundary-cause-name"):
            assert cause_hits == [1]
        assert tuple(context.retirement.errors) == before[0]
        assert context.retirement.primary is before[1]
    _invalid_run(_invalid_unit_api, scenario)


def test_invalid_popen_guard_generic_and_counted_denial():
    """UNIT constructor denial stays counted; generic annotation starts no process."""
    import subprocess
    from typing import get_origin
    calls = []
    denied = AssertionError("UNIT_ONLY_NATIVE_DENIED")

    def original_counted_denial(*args, **kwargs):
        calls.append((args, kwargs))
        raise denied

    guarded = _invalid_forbidden_popen(subprocess.Popen, original_counted_denial)
    assert issubclass(guarded, subprocess.Popen) and get_origin(guarded[bytes]) is guarded
    with pytest.raises(AssertionError) as caught:
        guarded(["UNIT_ONLY_MUST_NOT_EXECUTE"])
    assert caught.value is denied
    assert calls == [((["UNIT_ONLY_MUST_NOT_EXECUTE"],), {})]


# Group 6: one lost fixture public hold, late literal oracle, original SDK intact.
@pytest.mark.parametrize("early", (False, True), ids=("held-checkpoint", "early-public-release"))
def test_scoring_timeout_public_return_oracle(_invalid_unit_api, early):
    async def scenario(context):
        case = await _scoring_timeout_case(context)
        controller = case.controller
        await controller.owner_held.wait()
        public, = case.public_tasks
        if early:
            case.early_hits += 1
            controller.owner_release.set()  # ONLY fixture gate, never SDK/timer mutation.
            assert await public is None  # Await the ORIGINAL public task before checkpoint.
        facts = controller.checkpoint(rows=case.rows)
        assert facts["public_pending"] is (not early) and facts["public_uncancelled"] is True
        await _scoring_timeout_finish(context, case)
        _scoring_timeout_original_chain(case)
        assert controller.check_provenance() is None  # Drain/timeout chain still genuine.
        assert case.early_hits == int(early) and case.calls["public-delegate"] == 1
        if early:
            with pytest.raises(AssertionError) as caught:
                controller.check_public_return()
            _scoring_timeout_oracle_origin(controller, caught.value)
        else:
            assert controller.check_public_return() is None
    _invalid_run(_invalid_unit_api, scenario)


# Group 7: ORIGINAL retirement, inert native callbacks, no API cleanup exemption.
@pytest.mark.parametrize("mode", (
    "owner-held", "env-held", "previous-release-error", "pending-cleanup",
))
def test_scoring_timeout_failure_hygiene(_invalid_unit_api, mode):
    context = _scoring_timeout_context(_invalid_unit_api)
    original_error = ValueError("UNIT_ONLY previous retirement release")

    def previous_release():
        context.calls["previous-release"] += 1
        if mode == "previous-release-error":
            raise original_error
    context.retirement.release = previous_release

    async def prepare():
        case = await _scoring_timeout_case(context, held_resource=mode == "pending-cleanup")
        await case.controller.owner_held.wait()
        case.controller.checkpoint(rows=case.rows)
        if mode == "env-held":
            case.controller.owner_release.set()
            await case.controller.env_held.wait()
        return case

    try:
        case = context.loop.run_until_complete(asyncio.wait_for(prepare(), 3.0))
        public, = case.public_tasks
        context.retirement.request()
        if mode == "pending-cleanup":
            # Let composed release run and the ORIGINAL resource close enter.
            context.loop.run_until_complete(asyncio.wait_for(case.scorer.close_entered.wait(), 1.0))
            resource, = case.scorer.close_tasks
            assert not resource.done() and resource.cancelling() == 0
            context.retirement.remaining = lambda: 0.0  # UNIT proof refusal, not native cap.
        context.retirement.finish(native_retire=lambda: True, verify_native=lambda: True)
        assert case.controller.owner_release.is_set() and case.controller.env_release.is_set()
        assert context.calls["previous-release"] == 1
        assert public.cancelling() == 0 and case.calls["public-delegate"] == 1
        if mode == "pending-cleanup":
            assert not context.retirement.finalized and not resource.done()
            with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
                context.retirement.prove_safe()
            assert context.retirement.safe_emissions == 0 and resource.cancelling() == 0
        else:
            assert context.retirement.finalized and case.env.done()
            assert case.scope.task_score.cancelled()
            assert case.scope.harness_score.result() is None and not case.scope.harness_score.cancelled()
            assert case.scope.cleanup_task.result() is None
            assert all(task.done() and not task.cancelled() and task.result() is None
                       for _, task in case.scope.closes._entries)
            assert len(case.rows) == 1 and not case.rows[0]["ok"]
            if mode == "previous-release-error":
                assert context.retirement.primary is original_error
                assert all(stage == "release" and error is original_error
                           for stage, error in context.retirement.errors)
            else:
                assert context.retirement.primary is None and context.retirement.errors == []
    finally:
        _scoring_timeout_hygiene(context)
    if mode == "pending-cleanup":
        assert resource.done() and not resource.cancelled()
        assert not context.retirement.finalized and context.retirement.safe_emissions == 0


@pytest.mark.parametrize("mode", ("registration", "pre-hold-retirement", "late-registration"))
def test_scoring_timeout_actual_observer_wiring(_invalid_unit_api, mode):
    """Actual allocation/observer AST, UNIT owner only, no native/ACK claim."""
    async def scenario(context):
        path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
        tree = ast.parse(path.read_text(), filename=str(path))
        acceptance, = [node for node in tree.body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "_sdk_acceptance"]
        retain, = [node for node in acceptance.body
                   if isinstance(node, ast.FunctionDef) and node.name == "retain_owner"]
        observe, = [node for node in acceptance.body
                    if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "observe_timeout_scope"]
        scope = _scoring_timeout_scope(context.api)
        record = SimpleNamespace(
            scope=scope, actual=SimpleNamespace(_controller=lambda binding: None))
        actor = SimpleNamespace(
            retirement=context.retirement, spawn_lock=threading.Lock(),
            stopping=threading.Event(), gates=[])
        unit_gate = asyncio.Event()
        context.gates.append(unit_gate)

        async def unit_observer(record):
            await unit_gate.wait()  # Registration-only receiver, no owned behavior.

        namespace = dict(
            api=context.api, actor=actor, loop=context.loop, timeout_case=True,
            _SdkScoringTimeout=_scoring_timeout_type(), owners=[],
            timeout_controllers=[], timeout_drivers=[], controller_gates=[],
            asyncio=asyncio, threading=threading, time=time,
            cancellation=None, probe=None, released_first=[False], dispatch_turn=[0])
        if mode == "registration":
            namespace["observe_timeout_scope"] = unit_observer
            nodes = [retain]
        else:
            nodes = [observe, retain]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        if mode == "late-registration":
            released = asyncio.Event()
            previous_release = context.retirement.release

            def observed_previous_release():
                try:
                    previous_release()
                finally:
                    released.set()
            context.retirement.release = observed_previous_release
            context.retirement.request()
            await released.wait()  # Original previous release has actually happened.
        before_tasks = set(asyncio.all_tasks(context.loop))
        try:
            assert namespace["retain_owner"](record) is record.actual
            observer, = namespace["timeout_drivers"]
            controller, = namespace["timeout_controllers"]
            assert observer in context.retirement.tasks
            assert observer not in context.retirement.task_roles  # Non-cancelling retention.
            assert len(actor.gates) == len(namespace["controller_gates"]) == 1
            if mode == "registration":
                assert not observer.done()
                unit_gate.set()
                assert await observer is None
            else:
                if mode == "pre-hold-retirement":
                    assert not observer.done()
                    context.retirement.request()
                done, _ = await asyncio.wait((observer,), timeout=0.25)
                assert done == {observer}, "SDK_TIMEOUT_PRE_HOLD_OBSERVER_UNRESOLVED"
                assert observer.result() is None
                assert context.retirement.requested.is_set()
                assert not controller.owner_held.is_set() and controller._checkpoint is None
                assert controller.public_task is None and controller.receipt is None
            assert observer.cancelling() == 0 and not observer.cancelled()
        finally:
            # Assertion-failure hygiene ONLY, cannot retroactively pass proof.
            context.hygiene_tasks.extend(set(asyncio.all_tasks(context.loop)) - before_tasks)
            context.controllers.extend(namespace["timeout_controllers"])
            context.gates.extend(controller.owner_held
                                 for controller in namespace["timeout_controllers"])
    _invalid_run(_invalid_unit_api, scenario)


# Timeout-only FINAL-ledger diagnostics, SOURCE-FIRST, not a functional repair.
# Seven groups / 30 pure cases. Existing 287 cases above remain byte-for-byte.
# Future external helper: _sdk_timeout_error_diagnostic(retirement, refs) -> dict,
# AST-isolated/self-contained with the standard _repair_namespace globals.
# refs: immutable tuple of (closed function label, ORIGINAL code object), stored
# OUTSIDE the frozen class as retirement.timeout_diagnostic_refs. Capture the
# actual nested observer's code at definition, BEFORE any observer scheduling.
# Origin: "OTHER" or {file: fixed basename, function: closed label, line: int}.
# Absent primary: present False / token None / type "NONE" / origin "OTHER".
# Emission: one stderr JSON line {kind: "SDK_TIMEOUT_FINAL_LEDGER", diagnostic:
# payload}, <=8192 UTF-8 bytes INCLUDING envelope/newline. Failure may emit only
# a static SDK_TIMEOUT_FINAL_LEDGER_UNAVAILABLE marker, never change reporting.
# Native/SAFE/keeper/exit receivers below are explicit inert UNIT fakes. Only
# the actual report AST, original fail(), original completed assertion and
# original qualifier's missing-bundle failure are executed when parent runs.
# No SDK/native/actor qualification, private-data dump, functional fix or retry.
_TIMEOUT_DIAG_LABELS = (
    "_sdk_timeout_completed", "_SdkScoringTimeout._check_scope",
    "_sdk_timeout_qualification", "_sdk_acceptance", "_run_sdk_host_case",
    "_sdk_acceptance.observe_timeout_scope",
)
_TIMEOUT_DIAG_TYPES = (
    "AssertionError", "AttributeError", "RuntimeError", "TypeError",
    "ValueError", "TimeoutError", "OTHER",
)
_TIMEOUT_DIAG_STAGES = ("acceptance", "host", "task", "timeout-qualifier", "OTHER")


def _timeout_diag_origins():
    from types import CodeType
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    namespace = _repair_namespace(
        path.name,
        ("_sdk_timeout_completed", "_SdkScoringTimeout", "_sdk_timeout_qualification",
         "_sdk_acceptance", "_run_sdk_host_case"),
        extra={"__file__": str(path), "ast": ast})
    acceptance = namespace["_sdk_acceptance"].__code__
    observer, = [value for value in acceptance.co_consts
                 if isinstance(value, CodeType) and value.co_name == "observe_timeout_scope"]
    refs = (
        (_TIMEOUT_DIAG_LABELS[0], namespace["_sdk_timeout_completed"].__code__),
        (_TIMEOUT_DIAG_LABELS[1], namespace["_SdkScoringTimeout"]._check_scope.__code__),
        (_TIMEOUT_DIAG_LABELS[2], namespace["_sdk_timeout_qualification"].__code__),
        (_TIMEOUT_DIAG_LABELS[3], acceptance),
        (_TIMEOUT_DIAG_LABELS[4], namespace["_run_sdk_host_case"].__code__),
        (_TIMEOUT_DIAG_LABELS[5], observer),
    )
    return SimpleNamespace(path=path, namespace=namespace, refs=refs,
                           tree=ast.parse(path.read_text(), filename=str(path)))


def _timeout_diag_helper():
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    return _repair_namespace(
        path.name, ("_sdk_timeout_error_diagnostic",),
        extra={"__file__": str(path), "ast": ast})["_sdk_timeout_error_diagnostic"]


def _timeout_diag_owner(primary=None, errors=()):
    return SimpleNamespace(lock=threading.Lock(), primary=primary, errors=list(errors))


def _timeout_diag_caught(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("UNIT diagnostic receiver did not raise")


def _timeout_diag_completed_error(origins, function=None):
    # Execute the ORIGINAL function and ORIGINAL first assertion. No rewritten
    # failing code, SDK eval, reconstruction of the actor error or line claim.
    owner = _timeout_diag_owner()
    bundle = SimpleNamespace(actor=SimpleNamespace(retirement=owner),
                             episodes=[], programs=[], scorers=[], owners=[])
    function = function if function is not None else origins.namespace["_sdk_timeout_completed"]
    error = _timeout_diag_caught(lambda: function(bundle))
    assert type(error) is AssertionError
    return error


def _timeout_diag_leaf(error):
    tb = error.__traceback__
    assert tb is not None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb


def _timeout_diag_expected(origins, label, line):
    return dict(file=origins.path.name, function=label, line=line)


def _timeout_diag_payload(payload, *, canaries=()):
    assert type(payload) is dict and set(payload) == {
        "ledger_total", "ledger_omitted", "primary_present", "primary_token",
        "primary_type", "primary_origin", "primary_seen_in_sample", "entries"}
    assert type(payload["ledger_total"]) is int and payload["ledger_total"] >= 0
    assert type(payload["entries"]) is list and len(payload["entries"]) <= 16
    assert payload["ledger_omitted"] == payload["ledger_total"] - len(payload["entries"])
    assert type(payload["ledger_omitted"]) is int and payload["ledger_omitted"] >= 0
    assert type(payload["primary_present"]) is bool
    assert type(payload["primary_seen_in_sample"]) is bool
    assert type(payload["primary_type"]) is str
    if payload["primary_present"]:
        assert type(payload["primary_token"]) is int and payload["primary_token"] == 1
        assert payload["primary_type"] in _TIMEOUT_DIAG_TYPES
    else:
        assert payload["primary_token"] is None and payload["primary_type"] == "NONE"
        assert payload["primary_origin"] == "OTHER" and not payload["primary_seen_in_sample"]

    def origin(value):
        if type(value) is str:
            assert value == "OTHER"
        else:
            assert type(value) is dict and set(value) == {"file", "function", "line"}
            assert type(value["file"]) is str and value["file"] == "test_owned_sql_sdk_canonical.py"
            assert type(value["function"]) is str and value["function"] in _TIMEOUT_DIAG_LABELS
            assert type(value["line"]) is int and value["line"] > 0
    origin(payload["primary_origin"])
    for index, entry in enumerate(payload["entries"]):
        assert type(entry) is dict and set(entry) == {
            "ledger_index", "error_token", "is_primary", "stage", "type", "origin"}
        assert type(entry["ledger_index"]) is int and entry["ledger_index"] == index
        assert type(entry["error_token"]) is int and 1 <= entry["error_token"] <= 17
        assert type(entry["is_primary"]) is bool
        assert type(entry["stage"]) is str and entry["stage"] in _TIMEOUT_DIAG_STAGES
        assert type(entry["type"]) is str and entry["type"] in _TIMEOUT_DIAG_TYPES
        origin(entry["origin"])
    wire = (json.dumps(dict(kind="SDK_TIMEOUT_FINAL_LEDGER", diagnostic=payload),
                       separators=(",", ":")) + "\n").encode("utf-8")
    assert len(wire) <= 8192
    assert all(canary not in wire.decode("utf-8") for canary in canaries)
    return payload


def _timeout_diag_report_case(*, failure=None, phase="sdk-scoring-timeout"):
    """Extract FULL actual report, with inert I/O/native/keeper/exit receivers."""
    import builtins
    from types import MethodType
    origins = _timeout_diag_origins()
    primary = _timeout_diag_completed_error(origins)
    owner = _timeout_diag_owner()
    owner.fail = MethodType(_SdkRetirement.fail, owner)  # ORIGINAL sticky ledger writer.
    owner.outcome = dict(ok=False, decision="UNIT_diagnostic_only")
    owner.fail("acceptance", primary)
    owner.timeout_diagnostic_refs = origins.refs
    owner.stages, owner.workers, owner.executor_helpers, owner.resources = Counter(), set(), set(), []
    owner.finalized = True  # UNIT receiver only, never a native/API proof.
    calls, stderr, stdout, exits, input_states = Counter(), [], [], [], []

    def prove_safe():
        calls["safe"] += 1
        return True  # Explicit UNIT fake. Not _SdkRetirement.prove_safe/native evidence.
    owner.prove_safe = prove_safe

    def diagnostic(retirement, refs):
        calls["diagnostic"] += 1
        assert retirement is owner and refs is owner.timeout_diagnostic_refs
        assert not owner.lock.locked()
        assert owner.primary is primary and len(owner.errors) == 2
        assert owner.errors[1][0] == "timeout-qualifier"
        secondary = owner.errors[1][1]
        assert type(secondary) is AttributeError
        assert _timeout_diag_leaf(secondary).tb_frame.f_code is (
            origins.namespace["_sdk_timeout_qualification"].__code__)
        input_states.append((owner.primary, tuple(owner.errors)))
        if failure == "construction":
            raise RuntimeError("UNIT_CANARY_DIAGNOSTIC_CONSTRUCTION")
        return _timeout_diag_helper()(retirement, refs)  # No fallback implementation.

    def unit_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Exact canonical import bridge: original AST qualifier + lazy actual
        # future helper. No replacement qualifier or canonical/SDK module load.
        if name == "ptc.test_owned_sql_sdk_canonical":
            available = dict(_sdk_timeout_qualification=origins.namespace["_sdk_timeout_qualification"],
                             _sdk_timeout_error_diagnostic=diagnostic)
            assert fromlist and all(item in available for item in fromlist)
            return SimpleNamespace(**{item: available[item] for item in fromlist})
        return builtins.__import__(name, globals, locals, fromlist, level)

    def write(fd, raw):
        assert fd == 2 and type(raw) is bytes and not owner.lock.locked()
        calls["stderr-attempt"] += 1
        if failure == "emission":
            raise OSError("UNIT_CANARY_DIAGNOSTIC_EMISSION")
        stderr.append(raw)
        return len(raw)

    def write_record(fd, record):
        assert fd == 1
        stdout.append(record)

    report, = [node for node in ast.walk(_compat_guest_tree())
               if isinstance(node, ast.FunctionDef) and node.name == "report"]
    namespace = dict(
        __builtins__=dict(vars(builtins), __import__=unit_import),
        PHASE=phase, sdk_resources=owner, finished=SimpleNamespace(is_set=lambda: True),
        native_fds=set(), native_entries=[], slots=[], END=time.monotonic() + 1,
        sdk_native_proof=lambda: True,  # UNIT fake, no physical qualification.
        keeper=SimpleNamespace(join=lambda **kwargs: None, is_alive=lambda: False),
        os=SimpleNamespace(write=write, _exit=exits.append),
        time=time, json=json, Path=Path, write_record=write_record,
        _sdk_timeout_error_diagnostic=diagnostic)
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    exec(compile(ast.Module(body=[report], type_ignores=[]), str(path), "exec"), namespace)
    namespace["report"](dict(ok=False), 1)
    return SimpleNamespace(
        origins=origins, primary=primary, owner=owner, calls=calls, stderr=stderr,
        stdout=stdout, exits=exits, input_states=input_states)


# Group 1. FIRST RED is missing actual-report diagnostic, NOT a behavior bug.
def test_timeout_final_ledger_includes_qualifier_failure():
    case = _timeout_diag_report_case()
    assert case.owner.primary is case.primary and len(case.owner.errors) == 2
    assert case.owner.errors[0][0] == "acceptance" and case.owner.errors[0][1] is case.primary
    secondary_stage, secondary = case.owner.errors[1]
    assert secondary_stage == "timeout-qualifier" and type(secondary) is AttributeError
    leaf = _timeout_diag_leaf(secondary)
    assert leaf.tb_frame.f_code is case.origins.namespace["_sdk_timeout_qualification"].__code__
    qualifier, = [node for node in case.origins.tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_sdk_timeout_qualification"]
    assignment, = [node for node in qualifier.body if isinstance(node, ast.Assign)
                   and ast.dump(node) == ast.dump(ast.copy_location(
                       ast.parse("b = retirement.timeout_bundle").body[0], node))]
    assert leaf.tb_lineno == assignment.lineno  # Genuine ORIGINAL missing-bundle failure.
    assert case.stdout[0]["program_physical"]["nonprimary_errors"] == 0  # Earlier snapshot STAYS.
    assert case.stdout[0]["retirement_errors"] == 2 and case.exits == [1]
    assert case.stderr, "NEW_FEATURE_TIMEOUT_FINAL_LEDGER_DIAGNOSTIC_MISSING"
    assert len(case.stderr) == 1 and case.calls["diagnostic"] == 1
    envelope = json.loads(case.stderr[0])
    assert set(envelope) == {"kind", "diagnostic"} and envelope["kind"] == "SDK_TIMEOUT_FINAL_LEDGER"
    assert len(case.stderr[0]) <= 8192 and case.stderr[0].count(b"\n") == 1
    payload = _timeout_diag_payload(envelope["diagnostic"])
    assert payload["ledger_total"] == 2 and payload["ledger_omitted"] == 0
    assert payload["primary_token"] == 1 and payload["primary_seen_in_sample"] is True
    assert [entry["error_token"] for entry in payload["entries"]] == [1, 2]
    assert [entry["stage"] for entry in payload["entries"]] == ["acceptance", "timeout-qualifier"]
    assert [entry["type"] for entry in payload["entries"]] == ["AssertionError", "AttributeError"]
    assert payload["entries"][0]["origin"] == _timeout_diag_expected(
        case.origins, "_sdk_timeout_completed", _timeout_diag_leaf(case.primary).tb_lineno)
    assert payload["entries"][1]["origin"] == _timeout_diag_expected(
        case.origins, "_sdk_timeout_qualification", assignment.lineno)


# Group 2. Receipt-local identity ordinals, never id()/equality/hash of errors.
@pytest.mark.parametrize("mode", ("sampled-primary", "outside-primary", "absent-primary"))
def test_timeout_error_identity_ordinals(mode):
    origins = _timeout_diag_origins()
    calls = Counter()

    class IdentityBomb(AssertionError):
        def forbidden(self, *args):
            calls["forbidden"] += 1
            raise AssertionError("UNIT error equality/hash/stringification forbidden")
        __str__ = __repr__ = __eq__ = __hash__ = __bool__ = forbidden

    primary = IdentityBomb("UNIT_SAME_LOOKING")
    same_looking = IdentityBomb("UNIT_SAME_LOOKING")
    third = IdentityBomb("UNIT_SAME_LOOKING")
    if mode == "sampled-primary":
        errors = [("acceptance", primary), ("host", same_looking),
                  ("task", primary), ("host", third), ("task", same_looking)]
        expected, actual_primary = [1, 2, 1, 3, 2], primary
    elif mode == "outside-primary":
        errors = [("task", same_looking)] * 16 + [("acceptance", primary)]
        expected, actual_primary = [2] * 16, primary
    else:
        errors = [("task", same_looking), ("host", third), ("task", same_looking)]
        expected, actual_primary = [1, 2, 1], None
    owner = _timeout_diag_owner(actual_primary, errors)
    before = tuple(owner.errors)
    helper = _timeout_diag_helper()
    helper.__globals__.update(id=IdentityBomb.forbidden, hash=IdentityBomb.forbidden)
    payload = _timeout_diag_payload(helper(owner, origins.refs))
    assert [entry["error_token"] for entry in payload["entries"]] == expected
    assert [entry["is_primary"] for entry in payload["entries"]] == [
        error is actual_primary for _, error in errors[:16]]
    assert payload["primary_present"] is (actual_primary is not None)
    assert payload["primary_seen_in_sample"] is (mode == "sampled-primary")
    assert owner.primary is actual_primary and len(owner.errors) == len(before)
    assert all(left[0] == right[0] and left[1] is right[1]
               for left, right in zip(owner.errors, before, strict=True))
    assert calls == Counter()


# Group 3. Actual registered code IS, not structural equality/name/filename.
@pytest.mark.parametrize("mode", (
    "original", "structural-copy", "unregistered", "deepest-only", "capture-before-schedule",
))
def test_timeout_origin_requires_code_identity(mode):
    from types import FunctionType, TracebackType
    origins = _timeout_diag_origins()
    if mode == "capture-before-schedule":
        acceptance, = [node for node in origins.tree.body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "_sdk_acceptance"]
        observe, = [node for node in acceptance.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == "observe_timeout_scope"]
        assignments = [node for node in ast.walk(acceptance) if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Attribute)
                               and target.attr == "timeout_diagnostic_refs" for target in node.targets)]
        assert len(assignments) == 1, "NEW_FEATURE_TIMEOUT_ORIGINAL_CODE_REFS_MISSING"
        assignment, = assignments
        assert ast.dump(assignment.targets[0]) == ast.dump(
            ast.parse("actor.retirement.timeout_diagnostic_refs = None").body[0].targets[0])
        assert isinstance(assignment.value, ast.Tuple)  # Immutable six-pair registry.
        assert len(assignment.value.elts) == len(_TIMEOUT_DIAG_LABELS)
        expressions = (
            "_sdk_timeout_completed.__code__", "_SdkScoringTimeout._check_scope.__code__",
            "_sdk_timeout_qualification.__code__", "_sdk_acceptance.__code__",
            "_run_sdk_host_case.__code__", "observe_timeout_scope.__code__")
        for pair, label, expression in zip(
                assignment.value.elts, _TIMEOUT_DIAG_LABELS, expressions, strict=True):
            assert isinstance(pair, ast.Tuple) and len(pair.elts) == 2
            assert isinstance(pair.elts[0], ast.Constant) and pair.elts[0].value == label
            assert ast.dump(pair.elts[1]) == ast.dump(ast.parse(expression, mode="eval").body)
        retain, = [node for node in acceptance.body
                   if isinstance(node, ast.FunctionDef) and node.name == "retain_owner"]
        schedule, = [node for node in ast.walk(retain) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == "create_task"]
        assert observe.end_lineno < assignment.lineno < schedule.lineno
        return
    original = origins.namespace["_sdk_timeout_completed"]
    error = _timeout_diag_completed_error(origins)
    expected = _timeout_diag_expected(origins, "_sdk_timeout_completed", _timeout_diag_leaf(error).tb_lineno)
    if mode == "structural-copy":
        copied = original.__code__.replace()  # SAME filename/name/line/bytecode/structural equality.
        assert copied == original.__code__ and copied is not original.__code__
        clone = FunctionType(copied, original.__globals__)
        error = _timeout_diag_completed_error(origins, clone)
        expected = "OTHER"
    elif mode in ("unregistered", "deepest-only"):
        foreign = _timeout_diag_caught(lambda: (_ for _ in ()).throw(ValueError("UNIT foreign")))
        if mode == "unregistered":
            error = foreign
        else:
            registered = _timeout_diag_leaf(error)
            error.__traceback__ = TracebackType(
                _timeout_diag_leaf(foreign), registered.tb_frame,
                registered.tb_lasti, registered.tb_lineno)
        expected = "OTHER"  # No search-back to an earlier registered frame.
    payload = _timeout_diag_payload(_timeout_diag_helper()(
        _timeout_diag_owner(error, [("acceptance", error)]), origins.refs))
    assert payload["primary_origin"] == payload["entries"][0]["origin"] == expected


# Group 4. Trusted source/ancestry statement policy. Synthetic tb_lineno cases
# probe classification ONLY; they do not claim an actual thrown Raise location.
@pytest.mark.parametrize("mode", (
    "assert", "raise", "qualifier-assignment", "ordinary-assignment",
    "qualifier-other-assignment", "wrong-ancestry",
))
def test_timeout_origin_statement_allowlist(mode):
    from types import TracebackType
    origins = _timeout_diag_origins()
    functions = {node.name: node for node in origins.tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    refs = origins.refs
    error = _timeout_diag_completed_error(origins)
    leaf = _timeout_diag_leaf(error)
    expected = _timeout_diag_expected(origins, "_sdk_timeout_completed", leaf.tb_lineno)
    if mode == "raise":
        function = functions["_run_sdk_host_case"]
        statement, = [node for node in ast.walk(function) if isinstance(node, ast.Raise)]
        coroutine = origins.namespace["_run_sdk_host_case"](
            loop=None, root=None, prepared=None, phase="UNIT", mutant="none",
            profile=None, executor=None, actor=None)
        try:
            frame = coroutine.cr_frame  # Inert original code frame, body NEVER run.
            error = RuntimeError("UNIT synthetic source-statement probe")
            error.__traceback__ = TracebackType(None, frame, frame.f_lasti, statement.lineno)
        finally:
            coroutine.close()
        expected = _timeout_diag_expected(origins, "_run_sdk_host_case", statement.lineno)
    elif mode.startswith("qualifier-"):
        error = _timeout_diag_caught(
            lambda: origins.namespace["_sdk_timeout_qualification"](_timeout_diag_owner(), {}))
        assert type(error) is AttributeError
        leaf = _timeout_diag_leaf(error)
        assert leaf.tb_frame.f_code is origins.namespace["_sdk_timeout_qualification"].__code__
        expected = _timeout_diag_expected(origins, "_sdk_timeout_qualification", leaf.tb_lineno)
        if mode == "qualifier-other-assignment":
            statement, = [node for node in functions["_sdk_timeout_qualification"].body
                           if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                           and node.targets[0].id == "proof"]
            error.__traceback__ = TracebackType(None, leaf.tb_frame, leaf.tb_lasti, statement.lineno)
            expected = "OTHER"
    elif mode == "ordinary-assignment":
        statement, = [node for node in functions["_sdk_timeout_completed"].body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == "b"]
        error.__traceback__ = TracebackType(None, leaf.tb_frame, leaf.tb_lasti, statement.lineno)
        expected = "OTHER"
    elif mode == "wrong-ancestry":
        # Same closed labels, swapped ORIGINAL refs. An Assert elsewhere in the
        # trusted file is NOT a qualifier origin merely because its line exists.
        refs = tuple((label, origins.namespace["_sdk_timeout_qualification"].__code__
                      if label == "_sdk_timeout_completed"
                      else origins.namespace["_sdk_timeout_completed"].__code__
                      if label == "_sdk_timeout_qualification" else code)
                     for label, code in refs)
        expected = "OTHER"
    payload = _timeout_diag_payload(_timeout_diag_helper()(
        _timeout_diag_owner(error, [("task", error)]), refs))
    assert payload["primary_origin"] == payload["entries"][0]["origin"] == expected


# Group 5. Closed stage/type values, 0 malicious string/equality/hash/arg calls.
@pytest.mark.parametrize("mode", (
    "exception-canaries", "stage-canaries", "filename-and-locals", "unknown-builtins",
))
def test_timeout_diagnostic_privacy(mode, monkeypatch):
    import builtins
    import io
    from types import FunctionType
    origins = _timeout_diag_origins()
    calls = Counter()
    canary = "UNIT_CANARY_TIMEOUT_PRIVATE_CORPUS_SQL_TASK_NAME"

    def forbidden(*args, **kwargs):
        calls["forbidden"] += 1
        raise AssertionError("UNIT diagnostic inspected arbitrary value")

    class Poison(AssertionError):
        __str__ = __repr__ = __eq__ = __hash__ = __bool__ = forbidden

        def __getattribute__(self, name):
            if name in ("args", "__dict__", "message", "data", "task_name", "corpus"):
                return forbidden()
            return super().__getattribute__(name)

    class Stage(str):
        __str__ = __repr__ = __eq__ = __hash__ = forbidden

    if mode == "exception-canaries":
        error = Poison(canary, dict(task_name=canary, data=canary))
        errors, primary = [("task", error), ("host", error)], error
        expected_types, expected_stages = ["OTHER"] * 2, ["task", "host"]
    elif mode == "stage-canaries":
        error = ValueError(canary)
        stages = ["acceptance", "host", "task", "timeout-qualifier",
                  canary, Stage(canary), Poison(canary), None, 17]
        errors, primary = [(stage, error) for stage in stages], error
        expected_types = ["ValueError"] * len(stages)
        expected_stages = stages[:4] + ["OTHER"] * 5
    elif mode == "filename-and-locals":
        def foreign():
            task_name = data = corpus = sql = canary  # Must NEVER inspect frame locals.
            raise ValueError(canary)
        copied = foreign.__code__.replace(co_filename="/UNIT_PRIVATE/" + canary + ".py",
                                         co_name=canary, co_qualname=canary)
        function = FunctionType(copied, foreign.__globals__, closure=foreign.__closure__)
        error = _timeout_diag_caught(function)
        errors, primary = [("host", error)], error
        expected_types, expected_stages = ["ValueError"], ["host"]
    else:
        classes = (AssertionError, AttributeError, RuntimeError, TypeError, ValueError,
                   TimeoutError, Exception, KeyError, OSError, SystemExit, Poison)
        errors = [("task", cls(canary)) for cls in classes]
        primary = errors[0][1]
        expected_types = list(_TIMEOUT_DIAG_TYPES[:6]) + ["OTHER"] * 5
        expected_stages = ["task"] * len(classes)
    helper = _timeout_diag_helper()
    helper_node, = [node for node in ast.parse(origins.path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_sdk_timeout_error_diagnostic"]
    assert not any(isinstance(node, ast.Attribute) and node.attr in ("co_filename", "f_locals")
                   for node in ast.walk(helper_node))
    read_text = Path.read_text
    paths, foreign_paths = [], []

    def trusted_read(path, *args, **kwargs):
        paths.append(path)
        if path.resolve() != origins.path.resolve():
            foreign_paths.append(True)
            raise AssertionError("UNIT traceback-supplied source path forbidden")
        return read_text(path, *args, **kwargs)

    def guarded_open(original):
        def open_source(file, *args, **kwargs):
            if not isinstance(file, (str, Path)) or Path(file).resolve() != origins.path.resolve():
                foreign_paths.append(True)
                raise AssertionError("UNIT arbitrary source I/O forbidden")
            return original(file, *args, **kwargs)
        return open_source
    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_text", trusted_read)
        guard.setattr(builtins, "open", guarded_open(builtins.open))
        guard.setattr(io, "open", guarded_open(io.open))
        report = helper(_timeout_diag_owner(primary, errors), origins.refs)
    payload = _timeout_diag_payload(report,
                                    canaries=(canary, "/UNIT_PRIVATE/"))
    assert [entry["type"] for entry in payload["entries"]] == expected_types
    assert [entry["stage"] for entry in payload["entries"]] == expected_stages
    assert all(entry["origin"] == "OTHER" for entry in payload["entries"])
    assert calls == Counter() and foreign_paths == []


class _TimeoutDiagnosticUnitLock:
    def __init__(self):
        self.actual, self.held, self.entries = threading.Lock(), False, 0

    def __enter__(self):
        assert self.actual.acquire(blocking=False)
        self.held, self.entries = True, self.entries + 1
        return self

    def __exit__(self, *args):
        self.held = False
        self.actual.release()


class _TimeoutDiagnosticUnitLedger:
    """Virtual million-row ledger: ONLY len and the bounded [:16] under lock."""
    def __init__(self, lock, total, error):
        self.lock, self.total, self.error, self.reads = lock, total, error, []

    def __len__(self):
        assert self.lock.held
        self.reads.append("len")
        return self.total

    def __getitem__(self, key):
        assert self.lock.held and type(key) is slice
        assert (key.start, key.stop, key.step) == (None, 16, None)
        self.reads.append("prefix")
        return [("task", self.error)] * min(self.total, 16)

    def __iter__(self):
        raise AssertionError("UNIT unbounded ledger traversal forbidden")

    def copy(self):
        raise AssertionError("UNIT full ledger copy forbidden")


# Group 6. Capture under SHORT lock, release before source/AST/encoding/I/O.
@pytest.mark.parametrize("mode", (
    "empty", "sixteen", "seventeen", "million",
    "traceback-32", "traceback-33", "lock-release",
))
def test_timeout_diagnostic_bounds(mode, monkeypatch):
    from types import TracebackType
    origins = _timeout_diag_origins()
    helper = _timeout_diag_helper()
    error = _timeout_diag_completed_error(origins)
    leaf = _timeout_diag_leaf(error)
    if mode.startswith("traceback-"):
        links = int(mode.removeprefix("traceback-"))
        tb = None
        for _ in range(links):
            tb = TracebackType(tb, leaf.tb_frame, leaf.tb_lasti, leaf.tb_lineno)
        error.__traceback__ = tb
        owner = _timeout_diag_owner(error, [("task", error)])
        payload = _timeout_diag_payload(helper(owner, origins.refs))
        expected = (_timeout_diag_expected(origins, "_sdk_timeout_completed", leaf.tb_lineno)
                    if links == 32 else "OTHER")
        assert payload["primary_origin"] == payload["entries"][0]["origin"] == expected
        return
    total = {"empty": 0, "sixteen": 16, "seventeen": 17,
             "million": 1_000_000, "lock-release": 17}[mode]
    lock = _TimeoutDiagnosticUnitLock()
    ledger = _TimeoutDiagnosticUnitLedger(lock, total, error)

    class SnapshotOwner:
        @property
        def primary(self):
            assert lock.held
            return None if total == 0 else error

        @property
        def errors(self):
            assert lock.held
            return ledger
    owner = SnapshotOwner()
    owner.lock = lock
    reads, parses = [], []
    read_text, parse, dumps = Path.read_text, ast.parse, json.dumps

    def read_source(path, *args, **kwargs):
        assert lock.entries == 1 and not lock.held and path.resolve() == origins.path.resolve()
        reads.append(path)
        return read_text(path, *args, **kwargs)

    def parse_source(*args, **kwargs):
        assert lock.entries == 1 and not lock.held
        parses.append(True)
        return parse(*args, **kwargs)

    def encode(*args, **kwargs):
        assert lock.entries == 1 and not lock.held
        return dumps(*args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_source)
    monkeypatch.setattr(ast, "parse", parse_source)
    monkeypatch.setattr(json, "dumps", encode)
    payload = _timeout_diag_payload(helper(owner, origins.refs))
    assert not lock.held and lock.entries == 1
    assert ledger.reads == ["len", "prefix"]
    assert payload["ledger_total"] == total
    assert len(payload["entries"]) == min(total, 16)
    assert payload["ledger_omitted"] == max(total - 16, 0)
    assert payload["primary_present"] is (total != 0)
    if mode == "lock-release":
        assert reads and parses  # Genuine registered origin needs trusted AST.


# Group 7. Diagnostic construction/emission never becomes a new error/proof.
@pytest.mark.parametrize("mode", (
    "diagnostic-success", "construction-failure", "emission-failure", "other-phase",
))
def test_timeout_diagnostic_cannot_change_outcome(mode):
    failure = {"construction-failure": "construction", "emission-failure": "emission"}.get(mode)
    case = _timeout_diag_report_case(
        failure=failure, phase="sdk-ledger-UNIT-other" if mode == "other-phase" else "sdk-scoring-timeout")
    assert case.owner.primary is case.primary
    assert case.owner.errors[0][0] == "acceptance" and case.owner.errors[0][1] is case.primary
    assert case.calls["safe"] == 1 and case.exits == [1] and len(case.stdout) == 1
    output, = case.stdout
    assert output["safe"] is True and output["ok"] is False
    assert output["decision"] == "UNIT_diagnostic_only" and output["error"] == "AssertionError"
    assert output["physical_finalized"] is True
    assert case.owner.finalized is True
    assert case.owner.outcome == dict(
        ok=False, decision="UNIT_diagnostic_only", error="AssertionError")
    assert "diagnostic" not in output and "timeout_control_qualification" not in output
    expected = dict(
        safe=True, ok=False, decision="UNIT_diagnostic_only", error="AssertionError",
        retirement_stages={}, executor_workers=0, live_executor_workers=0,
        executor_helpers=0, live_executor_helpers=0, physical_finalized=True,
        retirement_errors=1 if mode == "other-phase" else 2)
    if mode == "other-phase":
        assert output == expected  # No additional stdout protocol fields.
        assert len(case.owner.errors) == 1 and case.calls["diagnostic"] == 0
        assert case.stderr == [] and "timeout_qualification" not in output
        return
    assert len(case.owner.errors) == 2 and output["retirement_errors"] == 2
    assert case.owner.errors[1][0] == "timeout-qualifier"
    assert type(case.owner.errors[1][1]) is AttributeError
    assert output["timeout_qualification"] == dict(verified=False)
    assert output["program_physical"]["nonprimary_errors"] == 0  # NOT refreshed/final proof.
    expected.update(
        timeout_qualification=dict(verified=False),
        program_physical=dict(
            native_proof=True, slots=0, nested_safe=0, creators=0, creator_waits=0,
            ambiguous_creators=0, live_readers=0, open_slot_fds=0, resource_stop_calls=[],
            resource_errors=0, nonprimary_errors=0))
    assert output == expected  # Diagnostic stays exclusively on stderr.
    assert case.calls["diagnostic"] == 1, "NEW_FEATURE_TIMEOUT_FINAL_LEDGER_DIAGNOSTIC_MISSING"
    assert len(case.input_states) == 1
    primary, before = case.input_states[0]
    assert case.owner.primary is primary and all(
        stage == old_stage and error is old_error
        for (stage, error), (old_stage, old_error) in zip(case.owner.errors, before, strict=True))
    assert len(case.stderr) <= 1
    for raw in case.stderr:
        assert len(raw) <= 8192 and raw.count(b"\n") == 1
        assert b"UNIT_CANARY" not in raw
    if mode == "diagnostic-success":
        assert len(case.stderr) == 1
        assert json.loads(case.stderr[0])["kind"] == "SDK_TIMEOUT_FINAL_LEDGER"
    elif mode == "emission-failure":
        assert case.calls["stderr-attempt"] >= 1  # Failure actually injected.
        assert case.stderr == []
    else:
        assert all(json.loads(raw) == dict(kind="SDK_TIMEOUT_FINAL_LEDGER_UNAVAILABLE")
                   for raw in case.stderr)


# Captured tuple-fence defect, SOURCE-FIRST / seven pure cases. The original
# CreatorTrace constructor/fence and full canonical functions below are NOT
# replaced by cloned predicates or a list-returning fence adapter. Partial
# UNIT receivers deliberately stop at the NEXT original assertion, never claim
# full timeout qualification, native cleanup, SDK evaluation or publication.
# Expected pre-fix RED: two empty cases stop at the wrong original line;
# snapshot + four nonempty negatives pass. Do not repair either literal here.
def _timeout_creator_trace_case():
    import sys
    calls, events, registry = Counter(), [], []

    class InertCreatorPopen:
        """Sole underlying constructor in PRIVATE m; object-only, no process."""
        def __init__(self, argv, *, _registry, **kwargs):
            calls["underlying-constructor"] += 1
            self.argv = argv
            _registry.append(self)

        def wait(self, timeout=None):
            calls["underlying-wait"] += 1
            return 0  # Inert return only, not an actual process/wait receipt.

    def emit(kind, **data):
        events.append(dict(kind=kind, **data))

    node, = [node for node in _compat_guest_tree().body
             if isinstance(node, ast.ClassDef) and node.name == "CreatorTrace"]
    private_m = SimpleNamespace(_CreatorPopen=InertCreatorPopen)
    namespace = dict(m=private_m, sys=sys, threading=threading, MUTANT="none")
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    original_constructor, original_wait = InertCreatorPopen.__init__, InertCreatorPopen.wait
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    creator_trace = namespace["CreatorTrace"]
    trace = creator_trace(emit, threading.Event())  # ORIGINAL registration wrapper.
    assert InertCreatorPopen.__bases__ == (object,)
    assert InertCreatorPopen.__init__ is not original_constructor
    assert InertCreatorPopen.wait is not original_wait
    assert trace.fence.__func__ is creator_trace.fence  # No lambda/adapter.
    return SimpleNamespace(
        trace=trace, creator_trace=creator_trace, m=private_m, calls=calls,
        events=events, registry=registry,
        argv=[sys.executable, "-I", "-B", "-c", "UNIT_INERT_NOT_EXECUTED"])


def _timeout_creator_register(case):
    assert case.trace.fence() == ()
    process = case.m._CreatorPopen(case.argv, _registry=case.registry)
    entry, = case.trace.entries  # ORIGINAL constructor's append, not test insertion.
    assert entry["process"] is process and entry["registry"] is case.registry
    assert entry["kind"] == "cli" and entry["index"] == 0
    assert len(case.registry) == 1 and case.registry[0] is process
    assert case.calls["underlying-constructor"] == 1 and case.trace.mutation_hits == 0
    assert case.events == [dict(
        kind="RESOURCE", actor="cli", index=0, registered=True, mutation_hits=0)]
    return process, entry


def test_creator_trace_fence_original_tuple_snapshot():
    case = _timeout_creator_trace_case()
    before = case.trace.fence()
    assert type(before) is tuple and before == ()
    process, entry = _timeout_creator_register(case)
    after = case.trace.fence()
    assert type(after) is tuple and len(after) == 1 and after[0] is entry
    assert after[0] is case.trace.entries[0] and after[0]["process"] is process
    assert before == () and len(before) == 0  # Earlier snapshot cannot grow.
    assert case.trace.fence()[0] is entry
    assert process.wait(timeout=0) == 0  # ORIGINAL wait wrapper, inert delegate.
    assert case.calls == Counter({"underlying-constructor": 1, "underlying-wait": 1})
    assert case.events[-1] == dict(kind="ACTUAL_WAIT", actor="cli", index=0)
    assert len(case.events) == 2 and entry["notified"] is True


def _timeout_creator_guard_case(kind, *, creators=0, slots=0):
    assert kind in ("completed", "qualification") and creators in (0, 1) and slots in (0, 1)
    creator = _timeout_creator_trace_case()
    if creators:
        _timeout_creator_register(creator)
    snapshot = creator.trace.fence()
    assert type(snapshot) is tuple and len(snapshot) == creators
    name = "_sdk_timeout_completed" if kind == "completed" else "_sdk_timeout_qualification"
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    namespace = _repair_namespace(path.name, (name,))
    function = namespace[name]  # FULL ORIGINAL function, not a reconstructed guard.
    tree = ast.parse(path.read_text(), filename=str(path))
    original, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    guards = [(index, node) for index, node in enumerate(original.body)
              if isinstance(node, ast.Assert) and any(
                  isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                  and child.func.attr == "fence"
                  and ast.dump(child.func.value) == ast.dump(
                      ast.parse("b.actor.trace", mode="eval").body)
                  for child in ast.walk(node.test))]
    assert len(guards) == 1
    index, guard = guards[0]
    following = original.body[index + 1]
    assert isinstance(following, ast.Assert)
    expected_next = ('all(actual.role == "scorer" for actual in b.actor.owners)'
                     if kind == "completed" else "len(b.controllers) == 7")
    assert ast.dump(following.test) == ast.dump(ast.parse(expected_next, mode="eval").body)

    retirement = SimpleNamespace()
    actor = SimpleNamespace(
        retirement=retirement, trace=creator.trace, slots=[object() for _ in range(slots)],
        owners=[SimpleNamespace(role="UNIT_DELIBERATELY_WRONG") for _ in range(7)])
    if kind == "completed":
        # Seven distinct declared Task/Data receivers and matching original-order
        # episode identities satisfy EVERY gate before the native-zero assertion.
        data = [SimpleNamespace(unit_index=index) for index in range(7)]
        tasks = [SimpleNamespace(data=value) for value in data]
        bundle = SimpleNamespace(
            actor=actor, public_data=data, sdk_tasks=tasks,
            episodes=[SimpleNamespace(task=task, ok=False) for task in tasks],
            programs=[object() for _ in range(7)], scorers=[object() for _ in range(7)],
            owners=[object() for _ in range(7)], controllers=[object() for _ in range(7)],
            drivers=[object() for _ in range(7)], closes=[object() for _ in range(7)],
            results=[], rewards=[], program_calls=[])
        args = (bundle,)
    else:
        class InertDeadWorker:
            def is_alive(self):
                return False  # Declared UNIT receiver, no thread ever started.

        bundle = SimpleNamespace(actor=actor, controllers=[])  # Deliberate NEXT failure.
        retirement.timeout_bundle = bundle  # UNIT namespace only, no actual retirement.
        retirement.finalized = True
        retirement.stages = Counter({"async": 1, "framework": 1, "executor": 1, "undo": 1})
        retirement.workers, retirement.executor_helpers = [InertDeadWorker()], [InertDeadWorker()]
        physical = dict(
            native_proof=True, resource_stop_calls=[1], slots=0, nested_safe=0,
            creators=0, creator_waits=0, ambiguous_creators=0, live_readers=0,
            open_slot_fds=0, resource_errors=0, nonprimary_errors=0)
        # Declared inert physical inputs ONLY to reach the original assertion.
        # This is not native proof, and no qualifier result can be returned.
        args = (retirement, physical)
    return SimpleNamespace(
        kind=kind, creator=creator, actor=actor, retirement=retirement, bundle=bundle,
        function=function, path=path, guard=guard, following=following, args=args)


def _timeout_creator_assertion_origin(case, *, following=False):
    error = _timeout_diag_caught(lambda: case.function(*case.args))
    assert type(error) is AssertionError
    leaf = _timeout_diag_leaf(error)
    assert leaf.tb_frame.f_code is case.function.__code__
    assert Path(case.function.__code__.co_filename).resolve() == case.path.resolve()
    expected = case.following if following else case.guard
    assert leaf.tb_lineno == expected.lineno, (
        "ORIGINAL_TIMEOUT_CREATOR_GUARD_DID_NOT_ADVANCE" if following
        else "ORIGINAL_TIMEOUT_NATIVE_ZERO_GUARD_BYPASSED")
    assert case.creator.trace.fence.__func__ is case.creator.creator_trace.fence
    if case.kind == "completed":
        assert not hasattr(case.retirement, "timeout_bundle")  # No checkpoint/publication.
    else:
        assert case.retirement.timeout_bundle is case.bundle and case.bundle.controllers == []


@pytest.mark.parametrize("kind", ("completed", "qualification"))
def test_timeout_empty_creator_fence_advances_original_guard(kind):
    case = _timeout_creator_guard_case(kind)
    assert case.actor.slots == [] and case.creator.trace.fence() == ()
    _timeout_creator_assertion_origin(case, following=True)


@pytest.mark.parametrize("kind", ("completed", "qualification"))
def test_timeout_nonempty_creator_fence_rejected(kind):
    case = _timeout_creator_guard_case(kind, creators=1)
    snapshot = case.creator.trace.fence()
    assert type(snapshot) is tuple and len(snapshot) == 1
    assert snapshot[0] is case.creator.trace.entries[0] and case.actor.slots == []
    _timeout_creator_assertion_origin(case)


@pytest.mark.parametrize("kind", ("completed", "qualification"))
def test_timeout_nonempty_slots_rejected(kind):
    case = _timeout_creator_guard_case(kind, slots=1)
    assert len(case.actor.slots) == 1 and case.creator.trace.fence() == ()
    assert case.creator.calls["underlying-constructor"] == 0
    _timeout_creator_assertion_origin(case)


# Scheduling SPIKE ONLY. The dynamically requested fixture MUST be available
# under this exact global name. No native owner/ACK/SAFE or late-sibling claim.
from ptc.test_owned_sql_sdk_integration import framework  # noqa: E402,F401


def _sibling_pre_result_original_origins(api, fault, injection_code, *, cleanup=None):
    """Original Harness post-base call + local raise; optional original drain."""
    path = Path(api.__file__).resolve()
    tree = ast.parse(path.read_text(), filename=str(path))
    cls, = [node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "OwnedSqlHarness"]
    score, = [node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "score"]
    body, = [node for node in score.body if isinstance(node, ast.Try)]
    base, postbase = body.body[:2]
    assert isinstance(base, ast.Expr) and isinstance(base.value, ast.Await)
    assert isinstance(base.value.value, ast.Call)
    assert ast.dump(base.value.value.func) == ast.dump(
        ast.parse("super().score", mode="eval").body)
    assert isinstance(postbase, ast.Expr) and isinstance(postbase.value, ast.Call)
    assert ast.dump(postbase.value.func) == ast.dump(
        ast.parse("scope.check", mode="eval").body)
    frames, tb = [], fault.__traceback__
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next
    original, = [tb for tb in frames if tb.tb_frame.f_code is api.OwnedSqlHarness.score.__code__]
    assert Path(original.tb_frame.f_code.co_filename).resolve() == path
    assert original.tb_lineno == postbase.lineno
    test_path = Path(__file__).resolve()
    test_tree = ast.parse(test_path.read_text(), filename=str(test_path))
    test, = [node for node in test_tree.body if isinstance(node, ast.FunctionDef)
             and node.name == "test_sdk_sibling_postbase_sees_pending_pre_result_score"]
    wrapper, = [node for node in test.body if isinstance(node, ast.FunctionDef)
                and node.name == "checked_pre_result"]
    raised, = [node for node in ast.walk(wrapper) if isinstance(node, ast.Raise)]
    assert isinstance(raised.exc, ast.Name) and raised.exc.id == "fault"
    assert frames[-1].tb_frame.f_code is injection_code
    assert Path(injection_code.co_filename).resolve() == test_path
    assert frames[-1].tb_lineno == raised.lineno
    if cleanup is not None:
        assert type(cleanup) is RuntimeError and cleanup is not fault
        drain, = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_drain_scope"]
        final_raise, = [node for node in ast.walk(drain) if isinstance(node, ast.Raise)]
        assert isinstance(final_raise.cause, ast.Constant) and final_raise.cause.value is None
        leaf = _timeout_diag_leaf(cleanup)
        assert leaf.tb_frame.f_code is api._drain_scope.__code__
        assert Path(leaf.tb_frame.f_code.co_filename).resolve() == path
        assert leaf.tb_lineno == final_raise.lineno


def test_sdk_sibling_postbase_sees_pending_pre_result_score(request, monkeypatch):
    """One pending-before-MOCK-result sibling schedule, not owned qualification."""
    from ptc.test_owned_sql_sdk_integration import _prepare, _rows, _successful
    from ptc.test_owned_sql_sdk_faults import (
        _release_and_drain, _score_close_observer, _target_rows, _tasks, _until)

    f = _prepare(request, monkeypatch, rollouts=1, num_tasks=7, status="match")
    scorer_type = f.api.OwnedSqlScorer
    result_mock = scorer_type.score_sql  # Existing declared ExResult MOCK.
    original_check = f.api._Scope.check
    harness_code = f.api.OwnedSqlHarness.score.__code__
    task_code, drain_code = f.api.OwnedSqlTask.score.__code__, f.api._drain_scope.__code__
    fault = RuntimeError("COMPOSITION_ONLY_PENDING_PRE_RESULT_SIBLING_FAILURE")
    probe = SimpleNamespace(
        pre_result_entered=asyncio.Event(), pre_result_release=asyncio.Event(),
        postbase_entered=asyncio.Event(), fault_entered=asyncio.Event(),
        score_cancelled=asyncio.Event(), score_task=None, cancel_task=None,
        cancel_error=None, cancel_objects=[], postbase_scope=None, postbase_task=None,
        postbase_hits=0, fault_hits=0, target_delegates=0, target_returns=0,
        delegated=[], returned=[])
    control = None

    async def pending_mock(self, predicted_sql):
        scope = f.api._rollout.get()
        assert scope is not None and scope.scorer is self
        assert scope.task_score is asyncio.current_task()
        record = f.by_scorer[self]
        target = scope is scope.admission.scopes[0]
        if target:
            # Association MUST already exist: outer original observer was
            # installed AFTER this wrapper, not before its underlying hold.
            assert control.target_scope is scope and control.target is not None
            assert control.target.scorer is self
            assert control.target.score_task is asyncio.current_task()
            probe.score_task = asyncio.current_task()
            probe.pre_result_entered.set()
            try:
                await probe.pre_result_release.wait()  # BEFORE any target MOCK delegation.
            except asyncio.CancelledError as error:
                assert type(error) is asyncio.CancelledError
                assert probe.cancel_error is None
                probe.cancel_error = error
                probe.cancel_objects.append(error)
                probe.cancel_task = asyncio.current_task()
                probe.score_cancelled.set()
                raise  # The actual builtin object, never reconstruct cancellation.
            probe.target_delegates += 1
        probe.delegated.append(record)
        result = await result_mock(self, predicted_sql)
        probe.returned.append((record, result))
        if target:
            probe.target_returns += 1
        return result

    monkeypatch.setattr(scorer_type, "score_sql", pending_mock)
    control = _score_close_observer(f, monkeypatch, harness_fault=False)

    def checked_pre_result(scope, *args, **kwargs):
        result = original_check(scope, *args, **kwargs)  # ORIGINAL authority check FIRST.
        if (scope is scope.admission.scopes[0]
                and asyncio.current_task() is scope.harness_score):
            # Signal the attempt BEFORE asserting scheduling facts, so an
            # early post-base call fails the probe instead of waiting/replaying.
            probe.postbase_scope, probe.postbase_task = scope, asyncio.current_task()
            probe.postbase_hits += 1
            probe.postbase_entered.set()
            assert scope is control.target_scope and control.target is not None
            assert scope.task_score is control.target.score_task is probe.score_task
            assert isinstance(scope.task_score, asyncio.Task) and not scope.task_score.done()
            assert probe.pre_result_entered.is_set() and not probe.pre_result_release.is_set()
            assert probe.target_delegates == probe.target_returns == 0
            assert scope.result is None and control.target.result is None
            assert scope.harness_success is False and probe.fault_hits == 0
            probe.fault_hits += 1
            probe.fault_entered.set()
            raise fault  # ORIGINAL Harness.score except/finally latches failure.
        return result

    injection_code = checked_pre_result.__code__
    monkeypatch.setattr(f.api._Scope, "check", checked_pre_result)

    async def scenario():
        f.release_scores.set()  # Six ordinary result-MOCK callbacks run unchanged.
        caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
            f.config, binding=f.binding))
        try:
            await _until(caller, probe.postbase_entered.wait())
            assert probe.postbase_hits == probe.fault_hits == 1
            assert probe.fault_entered.is_set()  # Wrong ordering fails, no Harness delay.
            await _until(caller, control.target_ready.wait())
            await _until(caller, probe.fault_entered.wait())
            await _until(caller, control.env_join_entered.wait())
            await _until(caller, control.close_entered.wait())
            await _until(caller, probe.score_cancelled.wait())
            await _until(caller, control.join_entered.wait())
            target = control.target
            scope = target.scope
            assert scope is control.target_scope is scope.admission.scopes[0]
            assert probe.postbase_scope is scope
            assert probe.postbase_task is scope.harness_score
            assert probe.score_task is probe.cancel_task is scope.task_score is target.score_task
            assert type(probe.cancel_error) is asyncio.CancelledError
            assert len(probe.cancel_objects) == 1 and probe.cancel_objects[0] is probe.cancel_error
            assert scope.harness_score.done() and not scope.harness_score.cancelled()
            assert scope.harness_score.exception() is fault
            assert scope.harness_done.is_set() and not scope.harness_success
            assert target.driver.done() and not target.driver.cancelled()
            assert target.driver.exception() is None and not target.trace.ok
            assert not target.score_task.done() and target.score_task.cancelling() > 0
            assert target.close_calls == 1 and not target.closed
            assert target.close_task is not None and not target.close_task.done()
            assert target.close_task.cancelling() == 0 and target.joins == [target.close_task]
            assert scope.cleanup_task is not None and not scope.cleanup_task.done()
            assert control.env_join_task is not None and not control.env_join_task.done()
            assert control.env_join_task is not target.driver
            assert control.env_join_task is not scope.cleanup_task
            assert scope.live and scope.token is not None and scope.failed and not scope.authority
            assert scope.result is target.result is None and not scope.published
            assert probe.target_delegates == probe.target_returns == 0
            assert target.trace.rewards == {} and _target_rows(f, control) == []
            assert target.record.events == ["admit"] and target.scorer._jobs == []
            # Prepared fixture result is UNUSED, not a returned native result.
            unused_target_mock = target.record.result
            assert unused_target_mock is not None
            assert not any(record is target.record for record in probe.delegated)
            assert not control.release_close.is_set() and not caller.done()
            _sibling_pre_result_original_origins(f.api, fault, injection_code)
            assert f.api.OwnedSqlHarness.score.__code__ is harness_code
            assert f.api.OwnedSqlTask.score.__code__ is task_code
            assert f.api._drain_scope.__code__ is drain_code
            assert f.api._HOOKS is control.hooks
            f.api._check_hooks()

            control.release_close.set()  # ONLY public close, not the pre-result gate.
            episodes = await caller
            assert not probe.pre_result_release.is_set()
            assert len(episodes) == len(control.items) == len(f.scorers) == 7
            assert len(f.programs) == f.policy.calls == len(f.policy.bodies) == 7
            assert len(f.state.agents) == len(f.state.runtimes) == 7
            assert (f.config.num_tasks, f.config.num_rollouts,
                    f.config.max_concurrent, f.config.shuffle) == (7, 1, 2, False)
            assert all(episode.task.data is data for episode, data in zip(
                episodes, f.public_data, strict=True))
            actual, = f.loads
            assert (len(actual.planned), len(actual.eligible), len(actual.exclusions)) == (8, 7, 1)
            assert len(actual.databases) == 2
            assert sum(episode.ok for episode in episodes) == 6
            assert len(probe.delegated) == len(probe.returned) == len(f.entered) == 6
            assert probe.postbase_hits == probe.fault_hits == 1
            assert probe.target_delegates == probe.target_returns == 0
            assert not any(record is target.record for record in probe.delegated)
            assert all(value is record.result and value is not unused_target_mock
                       for record, value in probe.returned)
            assert target.record.result is unused_target_mock
            assert target.result is scope.result is None
            assert target.score_task.done() and target.score_task.cancelled()
            assert scope.harness_score.exception() is fault
            cleanup_error = scope.cleanup_task.exception()
            assert type(cleanup_error) is RuntimeError and cleanup_error is not fault
            _sibling_pre_result_original_origins(
                f.api, fault, injection_code, cleanup=cleanup_error)
            assert probe.cancel_objects[0] is probe.cancel_error
            cancel_frames, tb = [], probe.cancel_error.__traceback__
            while tb is not None:
                cancel_frames.append(tb.tb_frame.f_code)
                tb = tb.tb_next
            assert any(code is task_code for code in cancel_frames)
            for private, data in zip(actual.eligible, f.public_data, strict=True):
                item, = [item for item in control.items if item.record.kwargs["task"] is private]
                episode, = [episode for episode in episodes if episode.task.data is data]
                trace, = episode.traces
                assert trace is item.trace and trace.task.data is item.task.data is data
                assert item.close_calls == 1 and item.closed
                assert item.close_task.done() and item.close_task.cancelling() == 0
                assert item.close_task.result() is None and item.scorer._jobs == []
                assert item.record.events == (
                    ["admit", "close", "closed"] if item is target
                    else ["admit", "score", "close", "closed"])
                assert not item.scope.live and item.scope.token is None
                assert not item.scope.authority and not item.scope.admission.active
                if item is target:
                    assert not episode.ok and not trace.ok and trace.rewards == {}
                    assert item.scope.failed and not item.scope.harness_success
                else:
                    assert item.result is item.record.result is item.scope.result
                    assert episode.ok and trace.ok and item.scope.harness_success
                    assert set(trace.rewards) == {"execution_accuracy"}
                    assert trace.rewards["execution_accuracy"].score == 1.0
                    assert all(task.done() and not task.cancelled() and task.exception() is None
                               for task in (item.driver, item.score_task,
                                            item.scope.harness_score, item.scope.cleanup_task))
            assert sum(len(item.trace.rewards) for item in control.items) == 6
            retained = _tasks(control)
            assert all(task.done() for task in (*retained, control.env_join_task))
            assert not any(task in asyncio.all_tasks() for task in retained)
            assert all(agent.harness is original and type(original) is f.api.OwnedSqlHarness
                       for agent, original in f.state.agents)
            assert f.api._HOOKS is control.hooks
            f.api._check_hooks()
            assert all(not any(message.get("role") == "tool" for message in body["messages"])
                       for body in f.policy.bodies)
            assert f.forbidden == f.state.external == f.state.channels == []
            assert not f.executor.state_dir.exists() and not f.profile.shared_state_dir.exists()
            rows = _rows(f.config, completed=True)
            assert len(rows) == 7 and sum(_successful(row) for row in rows) == 6
            assert {trace["id"] for row in rows for trace in row["traces"]} == {
                item.trace.id for item in control.items}
            failed, = _target_rows(f, control)
            assert not failed["ok"] and all(
                not trace["ok"] and not trace.get("rewards") for trace in failed["traces"])
            assert sum(row["ok"] for row in rows) == 6
        finally:
            probe.pre_result_release.set()
            f.release_scores.set()
            await _release_and_drain(f, control, caller)

    # Parent's ORIGINAL 30s command watchdog is authority; no imported 40s cap.
    # asyncio.run performs its ordinary executor shutdown, without exemptions.
    asyncio.run(scenario())


# Frozen sibling fixture contract: exactly eight groups of ten UNIT cases.
# These receivers exercise ORIGINAL Python code/AST and identity bookkeeping.
# Opaque UNIT public-return objects and inert physical inputs are NOT native
# ACKs, dispatches, creator waits, SAFE, SDK integration or actor qualification.
# The existing no-native fixture (including generic Popen guard) stays active.
def _sibling_unit_feature():
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py").resolve()
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    names = (
        "_SdkSiblingScoreFailure", "_sdk_sibling_completed",
        "_sdk_sibling_origins", "_sdk_sibling_oracle_origin",
        "_sdk_sibling_qualification")
    present = {getattr(node, "name", None) for node in tree.body}
    missing = set(names) - present
    assert not missing, (
        "NEW_FEATURE_SIBLING_SCORE_FAILURE_MISSING/APIabsent", sorted(missing))
    # Mandatory lookup BEFORE every expected-rejection context, never optional.
    namespace = _repair_namespace(
        path.name, names, extra={"__file__": str(path)})
    cls = namespace["_SdkSiblingScoreFailure"]
    methods = (
        "retain_owner", "bind_owner", "run_controller", "check_scope",
        "request_cancel", "score_cancelled", "close_owner", "settle_cleanup",
        "checkpoint_owner", "checkpoint_env", "release", "check_fault_origin",
        "check_provenance", "check_ledger")
    assert all(callable(getattr(cls, name, None)) for name in methods), (
        "NEW_FEATURE_SIBLING_SCORE_FAILURE_MISSING/APIabsent")
    return SimpleNamespace(
        cls=cls, namespace=namespace, path=path, source=source, tree=tree)


def _sibling_unit_nodes(path, *, owner=None, name):
    tree = ast.parse(path.read_text(), filename=str(path))
    body = tree.body
    if owner is not None:
        cls, = [node for node in body if isinstance(node, ast.ClassDef)
                and node.name == owner]
        body = cls.body
    function, = [node for node in body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == name]
    return function


def _sibling_unit_frames(error):
    result, tb = [], error.__traceback__
    while tb is not None:
        result.append(tb)
        tb = tb.tb_next
    assert result
    return result


def _sibling_unit_rejection(error, function):
    assert type(error) is AssertionError
    frames = _sibling_unit_frames(error)
    assert any(tb.tb_frame.f_code is function.__code__ for tb in frames)
    # An assertion in a UNIT receiver/delegate is NOT the validator's rejection.
    assert Path(frames[-1].tb_frame.f_code.co_filename).resolve() == Path(
        function.__code__.co_filename).resolve()
    assert "NEW_FEATURE_SIBLING_SCORE_FAILURE_MISSING/APIabsent" not in error.args


def _sibling_unit_exact(actual, expected):
    """Closed dictionaries and exact builtin scalar types (bool is NOT int)."""
    assert type(actual) is type(expected)
    if type(expected) is dict:
        assert actual.keys() == expected.keys()
        for key, value in expected.items():
            _sibling_unit_exact(actual[key], value)
    else:
        assert actual == expected


def _sibling_unit_move_frame(error, code, *, replacement=None, line_delta=0):
    from types import TracebackType
    original = error.__traceback__
    matches = [tb for tb in _sibling_unit_frames(error)
               if tb.tb_frame.f_code is code]
    assert len(matches) == 1

    def changed(tb):
        if tb is None:
            return None
        frame, line = tb.tb_frame, tb.tb_lineno
        if frame.f_code is code:
            if replacement is not None:
                frame = replacement
            line += line_delta
        return TracebackType(changed(tb.tb_next), frame, tb.tb_lasti, line)
    error.__traceback__ = changed(original)  # Explicit ONE-edge UNIT corruption.
    return original


def _sibling_unit_graph(context, feature, *, omit=False):
    from ptc.test_owned_sql_sdk_protocol import _UnitResource
    scope = _scoring_timeout_scope(context.api)
    planned = tuple(SimpleNamespace(name=f"UNIT_ONLY_sibling_{index}")
                    for index in range(8))
    public = tuple(SimpleNamespace(name=row.name, prompt="UNIT ONLY", idx=index)
                   for index, row in enumerate(planned[:7]))
    tasks = tuple(SimpleNamespace(data=data, _private=private)
                  for data, private in zip(public, planned[:7], strict=True))
    instrument = SimpleNamespace(
        scorer_timeout_s=3.0, scorer_max_rows=9, compare="multiset",
        program_timeout_s=5.0)
    admitted = SimpleNamespace(
        planned=planned, eligible=planned[:7], exclusions=(planned[7],),
        timeout_s=3.0, max_rows=9, comparison="multiset")
    config = SimpleNamespace(
        num_tasks=7, num_rollouts=1, max_concurrent=2, shuffle=False,
        env=SimpleNamespace(agent=SimpleNamespace(
            timeout=SimpleNamespace(scoring=17.0),
            harness=SimpleNamespace(program_timeout=5.0))))
    executor = object()
    bound = SimpleNamespace(
        draw=admitted, data=public, instrument=instrument, executor=executor)
    admission = SimpleNamespace(
        config=config, bound=bound, tasks=tasks, scopes=[scope], active=True)
    actor = SimpleNamespace(
        retirement=context.retirement, spawn_lock=threading.Lock(),
        stopping=threading.Event(), gates=[], owners=[], slots=[],
        end=time.monotonic() + 8.0, trace=SimpleNamespace(fence=lambda: ()),
        emit=lambda *args, **kwargs: None)
    # Future UNIT END with ORIGINAL offsets, not a HOST cap or runtime grant.
    # The unchanged _invalid_run 3s UNIT safety still bounds this receiver.
    context.retirement.deadline = actor.end - 0.25
    context.retirement.cooperative_cutoff = actor.end - 3.75
    scope.admission, scope.index = admission, 0
    scope.data, scope.task, scope.private = public[0], tasks[0], planned[0]
    scope.trace.task = scope.task
    scope.trace.last_reply = "SELECT 1"
    scope.trace.id = "UNIT_ONLY_sibling_" + str(len(context.cases))
    scope.runtime = object()
    scope.harness = object.__new__(context.api.OwnedSqlHarness)
    scope.trace.metrics = {}
    scope.harness.config = SimpleNamespace(id="UNIT_ONLY_sibling")
    case = SimpleNamespace(
        feature=feature, scope=scope, actor=actor, admission=admission,
        bound=bound, admitted=admitted, config=config, instrument=instrument,
        public_data=public, sdk_tasks=tasks, target_data=public[0], omit=omit,
        controller=None, owner=None, record=None, rows=[], calls=Counter(),
        entered=asyncio.Event(), execute_entered=asyncio.Event(), request_observed=asyncio.Event(),
        score_task=None, harness_task=None, env=None, public_tasks=[],
        originals=[], requests=[], request_errors=[], cancel_objects=[], check_returns=[],
        request_mutation="accepted", check_mutation="normal",
        original_check_error=None, public_error=None,
        public_return=object(), controller_return=object(), controller_bindings=[],
        resource_tasks=[], before_injection=None)
    context.cases.append(case)
    case.wire = _invalid_wire("match")
    case.agent_release = asyncio.Event()

    async def unit_agent():
        await case.agent_release.wait()
        return scope.trace
    scope.agent_task = context.loop.create_task(unit_agent())
    context.hygiene_tasks.append(scope.agent_task)

    def fail():
        scope.failed, scope.authority, scope.trace.ok = True, False, False
    scope.fail = fail

    def check(actual, *args, **kwargs):
        case.calls["original-check"] += 1
        assert actual is scope and not args
        assert all(value is getattr(scope, key) for key, value in kwargs.items())
        if case.original_check_error is not None:
            raise case.original_check_error
        return case.original_check_return
    case.original_check_return = object()
    case.original_check = check  # Explicit UNIT guard, not admission authority.

    def scope_check(*args, **kwargs):
        if case.controller is None:
            return check(scope, *args, **kwargs)
        if case.before_injection is not None:
            callback, case.before_injection = case.before_injection, None
            callback()
        try:
            result = case.controller.check_scope(scope, *args, delegate=check, **kwargs)
            case.check_returns.append(result)
            return result
        except RuntimeError as error:
            if case.check_mutation == "replay-postbase":
                assert error is case.controller.fault
                return case.controller.check_scope(scope, *args, delegate=check, **kwargs)
            raise
    scope.check = scope_check

    def record_reward(name, value):
        scope.trace.rewards[name] = SimpleNamespace(score=value)
    scope.trace.record_reward = record_reward

    class UnitOnlyRunner(_UnitResource):
        async def aclose(self):
            task = asyncio.current_task()
            context.retirement.retain_cleanup(task, "resource-close")
            case.resource_tasks.append(task)
            return await super().aclose()

    class UnitOnlyScorer(_UnitResource):
        async def score_sql(self, predicted):
            from ptc import sql_isolation as core
            import sys
            assert predicted == "SELECT 1"
            assert scope.task_score is asyncio.current_task()
            try:
                case.controller = feature.cls(
                    api=context.api, actor=actor, scope=scope,
                    target_data=case.target_data, omit_fault=case.omit)
                context.controllers.append(case.controller)
                owner = _scoring_timeout_owner()
                case.owner = owner
                actor.owners.append(owner)  # Mirror original observed_init's preconstructor registry.
                assert case.controller.retain_owner(owner) is None
                # Inert UNIT owner initialization ONLY, never original __init__.
                owner.role, owner._candidate, owner._thread = "scorer", None, None
                owner._children = []
                owner._incomplete = False
                owner._authority = SimpleNamespace(ack=case.public_return, owner=owner)
                owner._start = lambda: case.execute_entered.set()

                def controller_delegate(binding):
                    case.calls["controller-delegate"] += 1
                    case.controller_bindings.append(binding)
                    return case.controller_return
                owner._controller = controller_delegate
                record = SimpleNamespace(
                    actual=owner, task=scope.private, scope=scope, sdk_task=scope.task,
                    kwargs=dict(executor=executor, task=scope.private, instrument=instrument),
                    prediction=predicted, scorer=SimpleNamespace(
                        actual=self, scope=scope, score_task=scope.task_score,
                        kwargs=dict(executor=executor, task=scope.private, instrument=instrument)))
                case.record = record
                assert case.controller.bind_owner(record) is None
                assert case.controller.controller_delegate is controller_delegate
                assert case.controller.owner is owner and case.controller.owner_record is record
                assert not case.controller.controller_gate.is_set()

                def request(reason):
                    caller = sys._getframe(1)  # Capture ACTUAL execute caller, not metadata.
                    mutation = case.request_mutation
                    actual = owner
                    code, line, task = caller.f_code, caller.f_lineno, asyncio.current_task()
                    if mutation == "foreign-owner":
                        actual = _scoring_timeout_owner()
                    elif mutation == "wrong-caller-task":
                        task = case.env
                    elif mutation == "wrong-caller-code":
                        code = check.__code__
                    elif mutation == "wrong-caller-line":
                        line += 1

                    def delegate(receiver, why):
                        gate_before = case.controller.controller_gate.is_set()
                        receipt = core.OwnedSqlInvocation.request_cancel(receiver, why)
                        case.originals.append(receipt)
                        case.calls["request-delegate"] += 1
                        if not context.retirement.requested.is_set():
                            assert gate_before is (mutation == "premature-controller-release")
                        if mutation == "malformed-receipt":
                            return SimpleNamespace(status=receipt.status, intent=receipt.intent)
                        if mutation == "wrong-deadline":
                            object.__setattr__(
                                receipt.intent, "deadline_ns", receipt.intent.deadline_ns + 1)
                        return receipt
                    try:
                        receipt = case.controller.request_cancel(
                            actual, reason, delegate, caller_code=code,
                            caller_line=line, caller_task=task)
                        case.requests.append(receipt)
                        assert receipt is case.originals[-1]
                        if mutation == "repeated-same-intent":
                            repeated = case.controller.request_cancel(
                                actual, reason, core.OwnedSqlInvocation.request_cancel,
                                caller_code=code, caller_line=line, caller_task=task)
                            case.requests.append(repeated)
                            assert repeated.status == "repeated"
                            assert repeated.intent is receipt.intent
                        # UNIT loop termination only. No actual completion/ACK
                        # type is constructed or submitted to a native validator.
                        owner._completion = SimpleNamespace(
                            cleanup_ack=case.public_return, outcome=None)
                        return receipt
                    except BaseException as error:
                        case.request_errors.append(error)
                        raise
                    finally:
                        case.request_observed.set()
                owner.request_cancel = request
            finally:
                case.entered.set()
            try:
                await core.OwnedSqlInvocation.execute(owner)
                assert case.omit
                return case.wire.result
            except asyncio.CancelledError as error:
                case.cancel_objects.append(error)
                assert case.controller.score_cancelled(
                    scope, asyncio.current_task(), error) is None
                raise

        async def aclose(self):
            task = asyncio.current_task()
            context.retirement.retain_cleanup(task, "resource-close")
            case.resource_tasks.append(task)
            self.close_tasks.append(task)
            self.close_entered.set()
            if case.controller is not None and case.owner is not None:
                public = context.loop.create_task(
                    case.controller.close_owner(case.owner, case.original_public))
                case.public_tasks.append(public)
                context.hygiene_tasks.append(public)
                await context.api._settle(public)
            self.close_finished.set()
            return None

    async def original_public(actual):
        assert actual is case.owner
        case.calls["public-delegate"] += 1
        if case.public_error is not None:
            raise case.public_error
        return case.public_return  # Opaque UNIT return, explicitly NOT an ACK.
    case.original_public = original_public
    case.runner, case.scorer = UnitOnlyRunner(), UnitOnlyScorer()
    case.scorer._task, case.scorer._executor = scope.private, executor
    case.scorer._instrument, case.scorer._jobs = instrument, []
    scope.scorer = case.scorer
    scope.closes.retain(case.runner)
    scope.closes.retain(case.scorer)
    return case


async def _sibling_unit_ready(context, case):
    from types import FunctionType
    from ptc.test_owned_sql_sdk_protocol import _turn
    original = context.api.OwnedSqlTask.score

    def unit_scope(**kwargs):
        assert kwargs == dict(task=case.scope.task, trace=case.scope.trace,
                              runtime=case.scope.runtime)
        return case.scope
    score = FunctionType(
        original.__code__, dict(original.__globals__, _scope=unit_scope),
        original.__name__, original.__defaults__, original.__closure__)
    assert score.__code__ is original.__code__
    await case.scope.closes.start(case.runner)
    case.score_task = context.loop.create_task(score(
        case.scope.task, case.scope.trace, case.scope.runtime))
    context.hygiene_tasks.append(case.score_task)
    await case.entered.wait()
    await _turn()
    if case.score_task.done() or case.controller is None:
        await case.score_task  # ORIGINAL constructor failure, not a hung waiter.
    assert case.scope.task_score is case.score_task and not case.score_task.done()
    assert case.execute_entered.is_set() and case.controller is not None
    assert case.controller.score_task is case.score_task
    assert type(case.controller.fault) is RuntimeError
    assert case.controller.fault.args == ("SDK_SIBLING_HARNESS_SCORE_FAILURE",)
    assert case.controller.fault.__traceback__ is None
    assert all(type(getattr(case.controller, name)) is int for name in (
        "postbase_hits", "fault_hits", "omitted_fault_hits",
        "owner_calls", "owner_delegations", "env_calls"))
    assert any(gate is case.controller.controller_gate for gate in case.actor.gates)
    return case


async def _sibling_unit_inject(context, case):
    from types import FunctionType
    original = context.api.OwnedSqlHarness.score

    def unit_scope(**kwargs):
        assert kwargs == dict(harness=case.scope.harness, trace=case.scope.trace,
                              runtime=case.scope.runtime)
        # The original _scope pre-base guard is represented explicitly as UNIT
        # input; original Harness.score itself and its super call are unchanged.
        case.controller.check_scope(
            case.scope, delegate=case.original_check, **kwargs)
        return case.scope
    score = FunctionType(
        original.__code__, dict(original.__globals__, _scope=unit_scope),
        original.__name__, original.__defaults__, original.__closure__)
    assert score.__code__ is original.__code__
    case.harness_task = context.loop.create_task(score(
        case.scope.harness, case.scope.trace, case.scope.runtime))
    context.hygiene_tasks.append(case.harness_task)
    outcome, = await asyncio.gather(case.harness_task, return_exceptions=True)
    case.agent_release.set()
    assert await case.scope.agent_task is case.scope.trace
    if case.original_check_error is None:
        assert case.scope.harness_score is case.harness_task
    if case.omit:
        assert outcome is None and case.scope.harness_success
        case.owner._completion = SimpleNamespace(
            cleanup_ack=case.public_return, outcome=SimpleNamespace(result=case.wire.result))
    return outcome


async def _sibling_unit_start_env(context, case):
    scope, controller = case.scope, case.controller

    async def env_and_writer():
        scope.authority = False
        scope.closes.start_all()
        scope.cleanup_task = context.loop.create_task(context.api._drain_scope(scope))
        context.hygiene_tasks.append(scope.cleanup_task)
        try:
            return await controller.settle_cleanup(scope.cleanup_task, context.api._settle)
        finally:
            scope.live, scope.token = False, None
            case.rows.append(dict(ok=scope.harness_success, traces=[dict(
                id=scope.trace.id, ok=scope.harness_success,
                rewards={name: dict(score=reward.score)
                         for name, reward in scope.trace.rewards.items()})]))
    case.env = context.loop.create_task(env_and_writer())
    context.hygiene_tasks.append(case.env)
    return case.env


def _sibling_unit_owner_facts():
    return dict(
        intent_observed=True, original_execute_callsite=True,
        controller_released_after_intent=True, public_pending=True,
        public_uncancelled=True, score_pending=True, score_cancelling=True,
        cleanup_pending=True, scope_live=True, token_retained=True, authority=False,
        result_absent=True, published=False, target_rewards=0, target_rows=0)


def _sibling_unit_env_facts():
    return dict(
        cleanup_done=True, score_cancelled=True, harness_fault_identity=True,
        cleanup_error_identity=True, resources_done=True, env_pending=True,
        scope_live=True, token_retained=True, authority=False, result_absent=True,
        published=False, target_rewards=0, target_rows=0)


def _sibling_unit_assert_origins(context, case):
    from ptc import sql_isolation as core
    scope, controller = case.scope, case.controller
    fault = controller.fault
    assert type(fault) is RuntimeError and fault.args == ("SDK_SIBLING_HARNESS_SCORE_FAILURE",)
    assert scope.harness_score.done() and not scope.harness_score.cancelled()
    assert scope.harness_score.exception() is fault
    path = Path(context.api.__file__).resolve()
    function = _sibling_unit_nodes(path, owner="OwnedSqlHarness", name="score")
    body, = [node for node in function.body if isinstance(node, ast.Try)]
    postbase = body.body[1]
    assert ast.dump(postbase.value.func) == ast.dump(
        ast.parse("scope.check", mode="eval").body)
    frame, = [tb for tb in _sibling_unit_frames(fault)
              if tb.tb_frame.f_code is context.api.OwnedSqlHarness.score.__code__]
    assert frame.tb_lineno == postbase.lineno
    injection = _sibling_unit_nodes(
        case.feature.path, owner="_SdkSiblingScoreFailure", name="check_scope")
    raised, = [node for node in ast.walk(injection) if isinstance(node, ast.Raise)
               and isinstance(node.exc, ast.Attribute)
               and ast.dump(node.exc) == ast.dump(ast.parse("self.fault", mode="eval").body)]
    leaf = _sibling_unit_frames(fault)[-1]
    assert leaf.tb_frame.f_code is case.feature.cls.check_scope.__code__
    assert leaf.tb_lineno == raised.lineno and leaf.tb_frame.f_locals["self"] is controller
    assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
    cleanup = scope.cleanup_task.exception()
    assert type(cleanup) is RuntimeError and cleanup is not fault
    _invalid_assert_original(context.api, cleanup, "cleanup", scope, None)
    assert scope.task_score.cancelled()  # NEVER call .exception() on this Task.
    assert len(case.cancel_objects) == 1 and controller.cancel_error is case.cancel_objects[0]
    cancel_codes = [tb.tb_frame.f_code for tb in _sibling_unit_frames(controller.cancel_error)]
    assert any(code is context.api.OwnedSqlTask.score.__code__ for code in cancel_codes)
    assert any(code is core.OwnedSqlInvocation.execute.__code__ for code in cancel_codes)
    assert controller.request_task is scope.task_score
    assert controller.request_code is core.OwnedSqlInvocation.execute.__code__
    execute = _sibling_unit_nodes(
        Path(core.__file__).resolve(), owner="OwnedSqlInvocation", name="execute")
    handler, = [node for node in ast.walk(execute) if isinstance(node, ast.ExceptHandler)
                and any(isinstance(child, ast.Constant) and child.value == "caller_cancelled"
                        for child in ast.walk(node))]
    call, = [node for node in ast.walk(handler) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "request_cancel"]
    assert controller.request_line == call.lineno
    assert controller.receipt is case.originals[0]
    assert controller.receipt.intent is case.owner._intent
    assert controller.settled_error is cleanup and controller.settled_result is None
    return fault, cleanup


async def _sibling_unit_finish(context, case):
    controller, scope = case.controller, case.scope
    await controller.owner_held.wait()
    public, = case.public_tasks
    assert controller.public_task is public and not public.done() and public.cancelling() == 0
    assert controller.intent_seen.is_set() and case.calls["request-delegate"] >= 1
    assert controller.checkpoint_owner(rows=case.rows) is None
    _sibling_unit_exact(controller.owner_checkpoint, _sibling_unit_owner_facts())
    assert context.retirement.task_roles[public] == ("cleanup", "owner-close")
    assert scope.live and scope.token is not None and not scope.authority
    assert scope.result is None and not scope.published and not scope.trace.rewards
    assert not scope.task_score.done() and scope.task_score.cancelling() > 0
    assert not scope.cleanup_task.done() and case.rows == []
    controller.owner_release.set()
    await controller.env_held.wait()
    assert public.done() and not public.cancelled() and public.cancelling() == 0
    assert public.result() is case.public_return
    assert controller.checkpoint_env(rows=case.rows) is None
    _sibling_unit_exact(controller.env_checkpoint, _sibling_unit_env_facts())
    assert not case.env.done() and scope.live and scope.token is not None
    assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
    assert scope.task_score.cancelled()
    assert context.retirement.task_roles[scope.cleanup_task] == ("cleanup", "scope-drain")
    assert case.env in context.retirement.tasks and case.env not in context.retirement.task_roles
    controller.env_release.set()
    outcome, = await asyncio.gather(case.env, return_exceptions=True)
    assert outcome is scope.cleanup_task.exception() is controller.settled_error
    assert not scope.live and scope.token is None and not scope.authority
    assert len(case.resource_tasks) == len({id(task) for task in case.resource_tasks}) == 2
    assert all(task.done() and not task.cancelled() and task.result() is None
               and task.cancelling() == 0 for task in case.resource_tasks)
    assert case.calls["public-delegate"] == controller.owner_delegations == 1
    assert len(case.runner.close_tasks) == len(case.scorer.close_tasks) == 1
    assert case.rows == [dict(ok=False, traces=[dict(
        id=scope.trace.id, ok=False, rewards={})])]
    fault, cleanup = _sibling_unit_assert_origins(context, case)
    context.retirement._observe_task_errors()
    assert {id(error) for _, error in context.retirement.errors} == {id(fault), id(cleanup)}
    assert all(stage == "task" for stage, _ in context.retirement.errors)
    return fault, cleanup


def _sibling_unit_run(api, feature, scenario):
    async def wrapped(context):
        try:
            await scenario(context)
        finally:
            # Original drains cancel only their actual children. No blanket
            # task cancellation, fabricated observation, or trusted release()
            # under test. Hygiene cannot retroactively satisfy any assertion.
            # UNIT retirement input makes a receipt-less observer bypass its
            # wait honestly. Do not fake intent, completion or Harness latches.
            context.retirement.requested.set()
            drains = []
            for case in context.cases:
                if not hasattr(case, "feature"):
                    continue
                controller = case.controller
                if controller is not None:
                    for name in ("controller_gate", "owner_release", "env_release", "observer_wake"):
                        getattr(controller, name).set()
                if case.score_task is not None:
                    case.scope.task_score = case.score_task
                    case.scope.harness_score = case.harness_task
                    case.scope.authority = False
                    case.scope.closes.start_all()
                    if case.scope.cleanup_task is None:
                        case.scope.cleanup_task = context.loop.create_task(
                            context.api._drain_scope(case.scope))
                        context.hygiene_tasks.append(case.scope.cleanup_task)
                    drains.append(case.scope.cleanup_task)
            if drains:
                await asyncio.gather(*drains, return_exceptions=True)
    _invalid_run(api, wrapped)


# 1/8: count/config guards precede zip; constructor reads ONLY admission graph.
@pytest.mark.parametrize("variant", [
    "normal", "six-selected", "seven-planned", "zero-excluded", "reversed-data",
    "copied-target-data", "wrong-private", "two-rollouts", "shuffle", "concurrency-one",
])
def test_sibling_configuration_and_association(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        case = _sibling_unit_graph(context, feature)
        if variant == "six-selected":
            case.admitted.eligible = case.admitted.eligible[:6]
        elif variant == "seven-planned":
            case.admitted.planned = case.admitted.planned[:7]
        elif variant == "zero-excluded":
            case.admitted.exclusions = ()
        elif variant == "reversed-data":
            case.bound.data = case.bound.data[::-1]
        elif variant == "copied-target-data":
            case.target_data = SimpleNamespace(**vars(case.target_data))
            assert case.target_data == case.scope.data and case.target_data is not case.scope.data
        elif variant == "wrong-private":
            case.scope.private = case.admitted.eligible[1]
        elif variant == "two-rollouts":
            case.config.num_rollouts = 2
        elif variant == "shuffle":
            case.config.shuffle = True
        elif variant == "concurrency-one":
            case.config.max_concurrent = 1
        config_before, instrument_before = dict(vars(case.config)), dict(vars(case.instrument))
        graph_before = (
            case.admitted.planned, case.admitted.eligible, case.admitted.exclusions,
            case.bound.data, case.admission.tasks, case.scope.private, case.target_data)
        previous = context.retirement.release
        if variant == "normal":
            await _sibling_unit_ready(context, case)
            controller = case.controller
            assert controller.scope is case.scope and controller.target_data is case.target_data
            assert controller.target_private is case.scope.private
            assert controller.scorer is case.scope.scorer
            assert controller.retirement is context.retirement and controller.actor is case.actor
            assert controller.score_task is case.scope.task_score
            assert case.actor.gates == [controller.controller_gate]
            assert not controller.controller_gate.is_set()
            assert context.retirement.release is not previous
        else:
            with pytest.raises(AssertionError) as caught:
                await _sibling_unit_ready(context, case)
            _sibling_unit_rejection(caught.value, feature.cls.__init__)
            assert case.controller is None and case.actor.gates == []
            assert context.retirement.release is previous
        assert vars(case.config) == config_before and vars(case.instrument) == instrument_before
        assert case.config.env.agent.timeout.scoring == 17.0
        assert graph_before == (
            case.admitted.planned, case.admitted.eligible, case.admitted.exclusions,
            case.bound.data, case.admission.tasks, case.scope.private, case.target_data)
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


# 2/8: original guard first, original Harness post-base frame, no wait/replay.
@pytest.mark.parametrize("variant", [
    "normal", "omit", "original-check-refuses", "foreign-scope", "pre-base-check",
    "wrong-current-task", "missing-owner", "completed-score", "retained-result",
    "replay-postbase",
])
def test_sibling_original_first_postbase_injection(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        from ptc.test_owned_sql_sdk_protocol import _turn
        case = await _sibling_unit_ready(
            context, _sibling_unit_graph(context, feature, omit=variant == "omit"))
        controller, scope = case.controller, case.scope
        before = case.calls["original-check"]
        if variant in ("foreign-scope", "pre-base-check", "wrong-current-task"):
            observed = scope
            if variant == "foreign-scope":
                observed = SimpleNamespace(**vars(scope))  # Sole scope-identity edge.
            elif variant == "wrong-current-task":
                gate = asyncio.Event()
                context.gates.append(gate)
                scope.harness_score = context.loop.create_task(gate.wait())
                context.hygiene_tasks.append(scope.harness_score)
                assert asyncio.current_task() is not scope.harness_score
            def original_foreign_check(actual):
                assert actual is observed
                case.calls["original-check"] += 1
                return case.original_check_return
            delegate = original_foreign_check if variant == "foreign-scope" else case.original_check
            assert controller.check_scope(observed, delegate=delegate) is (
                case.original_check_return)
            assert case.calls["original-check"] == before + 1
            assert controller.postbase_hits == controller.fault_hits == controller.omitted_fault_hits == 0
            assert not controller.postbase_seen.is_set()
            return
        original_owner = controller.owner
        if variant == "original-check-refuses":
            refused = ValueError("UNIT_ONLY original guard refusal")
            case.before_injection = lambda: setattr(case, "original_check_error", refused)
        elif variant == "missing-owner":
            case.before_injection = lambda: setattr(controller, "owner", None)
        elif variant == "completed-score":
            async def completed():
                return None
            substitute = context.loop.create_task(completed())
            context.hygiene_tasks.append(substitute)
            await substitute
            case.before_injection = lambda: setattr(scope, "task_score", substitute)
        elif variant == "retained-result":
            case.before_injection = lambda: setattr(scope, "result", object())
        elif variant == "replay-postbase":
            case.check_mutation = variant
        try:
            error = await _sibling_unit_inject(context, case)
            if variant == "normal":
                assert error is controller.fault
                assert scope.harness_score.exception() is error and scope.harness_done.is_set()
                assert not scope.harness_success and not case.score_task.done()
                assert scope.result is None and not scope.published and not scope.trace.rewards
                assert controller.postbase_hits == controller.fault_hits == 1
                assert controller.omitted_fault_hits == 0 and controller.postbase_seen.is_set()
                assert case.calls["original-check"] == before + 2
            elif variant == "omit":
                assert error is None and scope.harness_success
                assert case.check_returns == [case.original_check_return]
                assert controller.postbase_hits == controller.omitted_fault_hits == 1
                assert controller.fault_hits == 0
                await case.score_task
                assert case.calls["public-delegate"] == 1 and case.originals == []
                assert controller.owner_checkpoint is controller.env_checkpoint is None
                assert not any(getattr(controller, name).is_set()
                               for name in ("intent_seen", "owner_held", "env_held"))
                assert scope.result is case.wire.result and scope.published
            elif variant == "original-check-refuses":
                assert error is case.original_check_error
                assert controller.postbase_hits == controller.fault_hits == 0
                assert scope.harness_score.exception() is error and error is not controller.fault
                await _sibling_unit_start_env(context, case)
                outcome, = await asyncio.gather(case.env, return_exceptions=True)
                assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
                assert outcome is scope.cleanup_task.exception()
                assert type(outcome) is RuntimeError
                assert case.calls["public-delegate"] == 1
                assert controller.owner_checkpoint is controller.env_checkpoint is None
                assert not any(getattr(controller, name).is_set()
                               for name in ("intent_seen", "owner_held", "env_held"))
                context.retirement._observe_task_errors()
                assert any(actual is error for _, actual in context.retirement.errors)
                assert not any(actual is controller.fault for _, actual in context.retirement.errors)
            else:
                _sibling_unit_rejection(error, feature.cls.check_scope)
                assert controller.fault_hits == int(variant == "replay-postbase")
                assert not controller.controller_gate.is_set()
                assert scope.result is None or variant == "retained-result"
            await _turn()
            assert case.calls["controller-delegate"] == 0 and case.actor.slots == []
        finally:
            controller.owner = original_owner
            scope.task_score = case.score_task
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


# 5/8: ONE actual traceback/task/object edge changed AFTER valid provenance.
@pytest.mark.parametrize("variant", [
    "normal", "copied-fault", "wrong-injection-code", "wrong-injection-line",
    "wrong-harness-code", "wrong-postbase-line", "noncancelled-score", "pending-cleanup",
    "forged-cleanup", "replaced-settled-error",
])
def test_sibling_original_failure_provenance(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        case = await _sibling_unit_ready(context, _sibling_unit_graph(context, feature))
        assert await _sibling_unit_inject(context, case) is case.controller.fault
        await _sibling_unit_start_env(context, case)
        fault, cleanup = await _sibling_unit_finish(context, case)
        controller, scope = case.controller, case.scope
        assert controller.check_provenance() is None
        original_tb = fault.__traceback__
        original_cleanup = scope.cleanup_task
        foreign_frame = inspect.currentframe()
        try:
            if variant == "copied-fault":
                controller.fault = RuntimeError(*fault.args)
            elif variant in ("wrong-injection-code", "wrong-injection-line"):
                _sibling_unit_move_frame(
                    fault, feature.cls.check_scope.__code__,
                    replacement=foreign_frame if variant == "wrong-injection-code" else None,
                    line_delta=int(variant == "wrong-injection-line"))
            elif variant in ("wrong-harness-code", "wrong-postbase-line"):
                _sibling_unit_move_frame(
                    fault, context.api.OwnedSqlHarness.score.__code__,
                    replacement=foreign_frame if variant == "wrong-harness-code" else None,
                    line_delta=int(variant == "wrong-postbase-line"))
            elif variant == "noncancelled-score":
                async def successful():
                    return None
                substitute = context.loop.create_task(successful())
                context.hygiene_tasks.append(substitute)
                await substitute
                scope.task_score = substitute
                assert not substitute.cancelled() and substitute.exception() is None
            elif variant == "pending-cleanup":
                gate = asyncio.Event()
                context.gates.append(gate)
                scope.cleanup_task = context.loop.create_task(gate.wait())
                context.hygiene_tasks.append(scope.cleanup_task)
                assert not scope.cleanup_task.done()
            elif variant == "forged-cleanup":
                scope.cleanup_task = SimpleNamespace(
                    done=lambda: True, cancelled=lambda: False, exception=lambda: cleanup)
            elif variant == "replaced-settled-error":
                controller.settled_error = RuntimeError(*cleanup.args)
            before = tuple(context.retirement.errors), context.retirement.primary
            if variant == "normal":
                assert controller.check_provenance() is None
            else:
                with pytest.raises(AssertionError) as caught:
                    controller.check_provenance()
                _sibling_unit_rejection(caught.value, feature.cls.check_provenance)
            assert tuple(context.retirement.errors) == before[0]
            assert context.retirement.primary is before[1]
            assert case.harness_task.exception() is fault
            assert original_cleanup.exception() is cleanup
            assert case.score_task.cancelled()  # No cancelled-Task.exception().
        finally:
            fault.__traceback__ = original_tb
            controller.fault, controller.settled_error = fault, cleanup
            scope.task_score, scope.cleanup_task = case.score_task, original_cleanup
            del foreign_frame
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


# 6/8: fresh distinct identity SET, all stages, sticky member primary.
@pytest.mark.parametrize("variant", [
    "normal", "repeated-same-identities", "missing-harness", "missing-cleanup",
    "foreign-error", "wrong-stage", "duplicate-wrong-stage", "foreign-primary",
    "missing-primary", "late-foreign-error",
])
def test_sibling_exact_failure_ledger(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        case = await _sibling_unit_ready(context, _sibling_unit_graph(context, feature))
        assert await _sibling_unit_inject(context, case) is case.controller.fault
        await _sibling_unit_start_env(context, case)
        fault, cleanup = await _sibling_unit_finish(context, case)
        controller, retirement = case.controller, context.retirement
        # Pick an allowed primary that remains present in each missing-member
        # variant, so absence cannot be rejected merely as a foreign primary.
        retirement.primary = cleanup if variant == "missing-harness" else fault
        assert controller.check_provenance() is None and controller.check_ledger() is None
        if variant == "repeated-same-identities":
            retirement.errors.extend([("task", cleanup), ("task", fault), ("task", cleanup)])
        elif variant in ("missing-harness", "missing-cleanup"):
            removed = fault if variant == "missing-harness" else cleanup
            retirement.errors[:] = [(stage, error) for stage, error in retirement.errors
                                    if error is not removed]
            assert any(error is retirement.primary for _, error in retirement.errors)
        elif variant in ("foreign-error", "late-foreign-error"):
            if variant == "late-foreign-error":
                assert controller.check_ledger() is None  # Successful prior read cannot cache proof.
            retirement.errors.append(("task", RuntimeError(*fault.args)))
        elif variant == "wrong-stage":
            stage, error = retirement.errors[0]
            assert stage == "task"
            retirement.errors[0] = ("host", error)
        elif variant == "duplicate-wrong-stage":
            retirement.errors.append(("acceptance", fault))
        elif variant == "foreign-primary":
            retirement.primary = RuntimeError(*fault.args)
        elif variant == "missing-primary":
            retirement.primary = None
        before = tuple(retirement.errors), retirement.primary
        if variant in ("normal", "repeated-same-identities"):
            assert controller.check_ledger() is None
        else:
            with pytest.raises(AssertionError) as caught:
                controller.check_ledger()
            _sibling_unit_rejection(caught.value, feature.cls.check_ledger)
        assert tuple(retirement.errors) == before[0] and retirement.primary is before[1]
        assert case.harness_task.exception() is fault
        assert case.scope.cleanup_task.exception() is cleanup
        assert case.score_task.cancelled()
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


# 3/8: actual ORIGINAL execute catches cancellation delivered by ORIGINAL drain.
@pytest.mark.parametrize("variant", [
    "accepted", "repeated-same-intent", "close-enters-before-intent", "foreign-owner",
    "wrong-caller-task", "wrong-caller-code", "wrong-caller-line", "malformed-receipt",
    "wrong-deadline", "premature-controller-release",
])
def test_sibling_original_intent_before_controller_release(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        from ptc import sql_isolation as core
        case = await _sibling_unit_ready(context, _sibling_unit_graph(context, feature))
        assert await _sibling_unit_inject(context, case) is case.controller.fault
        controller = case.controller
        case.request_mutation = variant
        if variant == "close-enters-before-intent":
            case.scope.closes.start(case.scorer)
            await controller.owner_entered.wait()
            assert not controller.owner_held.is_set() and not controller.intent_seen.is_set()
            assert not controller.controller_gate.is_set() and not case.score_task.done()
            assert case.originals == [] and case.calls["public-delegate"] == 0
        elif variant == "premature-controller-release":
            controller.controller_gate.set()  # ONE proof-edge negative input.
        await _sibling_unit_start_env(context, case)
        await case.request_observed.wait()
        assert case.calls["request-delegate"] == len(case.originals) == 1
        assert type(case.originals[0]) is core.CancelReceipt
        assert case.originals[0].status == "accepted"
        if variant in ("accepted", "repeated-same-intent", "close-enters-before-intent"):
            assert case.request_errors == [] and controller.receipt is case.originals[0]
            assert controller.intent_seen.is_set() and controller.controller_gate.is_set()
            assert controller.request_task is case.score_task
            assert controller.request_code is core.OwnedSqlInvocation.execute.__code__
            intent = controller.receipt.intent
            assert intent is case.owner._intent and intent.invocation_id == case.owner.invocation_id
            assert intent.deadline_ns == intent.requested_ns + 12_000_000_000
            binding = object()
            assert controller.run_controller(binding) is case.controller_return
            assert case.controller_bindings == [binding] and case.calls["controller-delegate"] == 1
            if variant == "repeated-same-intent":
                assert len(case.requests) == 2
                assert case.requests[1].intent is intent and case.requests[1] is not case.requests[0]
            await _sibling_unit_finish(context, case)
        else:
            error, = case.request_errors
            _sibling_unit_rejection(error, feature.cls.request_cancel)
            assert controller.receipt is None and not controller.intent_seen.is_set()
            assert not controller.owner_held.is_set() and controller.owner_checkpoint is None
            assert case.calls["controller-delegate"] == 0
            assert controller.controller_gate.is_set() is (
                variant == "premature-controller-release")
            context.retirement.requested.set()  # Hygiene only, after rejection proof.
            controller.release()
            await asyncio.gather(case.env, return_exceptions=True)
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


# 4/8: public-close and scope-exit barriers, unchanged original return/errors.
@pytest.mark.parametrize("variant", [
    "normal", "replay-owner-close", "foreign-owner-close", "non-target-settle-success",
    "non-target-settle-error", "retirement-before-intent", "retirement-at-owner-hold",
    "retirement-at-env-hold", "prior-release-raises", "original-close-raises",
])
def test_sibling_public_close_and_env_barriers(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()

    async def scenario(context):
        case = _sibling_unit_graph(context, feature)
        previous_error = ValueError("UNIT_ONLY previous release failure")
        previous_states = []

        def previous_release():
            previous_states.append((
                case.controller.controller_gate.is_set(),
                case.controller.owner_release.is_set(), case.controller.env_release.is_set()))
            case.calls["previous-release"] += 1
            if variant == "prior-release-raises":
                raise previous_error
        context.retirement.release = previous_release
        await _sibling_unit_ready(context, case)
        assert await _sibling_unit_inject(context, case) is case.controller.fault
        controller, scope = case.controller, case.scope
        if variant == "original-close-raises":
            case.public_error = OSError("UNIT_ONLY original public-close failure")
        if variant in ("non-target-settle-success", "non-target-settle-error"):
            value, failure = object(), ValueError("UNIT_ONLY unrelated settle")

            async def unrelated():
                if variant == "non-target-settle-error":
                    raise failure
                return value
            other = context.loop.create_task(unrelated())
            context.hygiene_tasks.append(other)
            calls = []

            async def settle(task):
                calls.append(task)
                return await context.api._settle(task)
            if variant == "non-target-settle-error":
                with pytest.raises(ValueError) as caught:
                    await controller.settle_cleanup(other, settle)
                assert caught.value is failure
            else:
                assert await controller.settle_cleanup(other, settle) is value
            assert calls == [other] and controller.env_task is None
            assert controller.settled_result is controller.settled_error is None
            assert not controller.env_held.is_set()
        if variant == "retirement-before-intent":
            scope.closes.start(case.scorer)
            await controller.owner_entered.wait()
            assert not controller.owner_held.is_set() and case.originals == []
        else:
            await _sibling_unit_start_env(context, case)
            await controller.owner_held.wait()
        if variant in ("replay-owner-close", "foreign-owner-close"):
            actual = case.owner if variant == "replay-owner-close" else _scoring_timeout_owner()
            with pytest.raises(AssertionError) as caught:
                await controller.close_owner(actual, case.original_public)
            _sibling_unit_rejection(caught.value, feature.cls.close_owner)
            assert case.calls["public-delegate"] == 0 and controller.owner_delegations == 0
        if variant == "retirement-at-env-hold":
            controller.owner_release.set()
            await controller.env_held.wait()
        retired = variant in (
            "retirement-before-intent", "retirement-at-owner-hold",
            "retirement-at-env-hold", "prior-release-raises")
        if retired:
            context.retirement.requested.set()  # UNIT release-callback input only.
            before = (controller.controller_gate.is_set(), controller.owner_release.is_set(),
                      controller.env_release.is_set())
            if variant == "prior-release-raises":
                with pytest.raises(ValueError) as caught:
                    context.retirement.release()
                assert caught.value is previous_error
            else:
                assert context.retirement.release() is None
            assert previous_states == [before] and case.calls["previous-release"] == 1
            assert all(getattr(controller, name).is_set()
                       for name in ("controller_gate", "owner_release", "env_release", "observer_wake"))
            if variant == "retirement-before-intent":
                assert controller.owner_checkpoint is controller.env_checkpoint is None
                assert not controller.intent_seen.is_set() and not controller.owner_held.is_set()
                await _sibling_unit_start_env(context, case)
            await asyncio.gather(case.env, return_exceptions=True)
            if variant == "retirement-before-intent":
                assert not controller.env_held.is_set()
                assert controller.owner_checkpoint is controller.env_checkpoint is None
            elif variant in ("retirement-at-owner-hold", "prior-release-raises"):
                assert not controller.env_held.is_set()
                assert controller.owner_checkpoint is controller.env_checkpoint is None
            assert all(task.done() and task.cancelling() == 0 for task in case.public_tasks)
            assert case.calls["public-delegate"] == 1
        elif variant == "original-close-raises":
            controller.owner_release.set()
            await controller.env_held.wait()
            controller.env_release.set()
            await asyncio.gather(case.env, return_exceptions=True)
            public, = case.public_tasks
            assert public.done() and not public.cancelled()
            assert public.exception() is case.public_error and public.cancelling() == 0
            scorer_close, = case.scorer.close_tasks
            assert scorer_close.done() and not scorer_close.cancelled()
            assert scorer_close.exception() is case.public_error
            assert scope.task_score.done() and not scope.task_score.cancelled()
            assert scope.task_score.exception() is case.public_error
            assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
            assert controller.settled_error is scope.cleanup_task.exception()
            assert controller.settled_error is not case.public_error
            context.retirement._observe_task_errors()
            assert any(error is case.public_error for _, error in context.retirement.errors)
            with pytest.raises(AssertionError):
                controller.check_provenance()
        else:
            await _sibling_unit_finish(context, case)
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


class _SiblingUnitPublicReturn:
    """Inert identity input, NOT CleanupCompleteAck, authority, seal or native proof."""

    def __init__(self, *, not_started):
        self.not_started = not_started


class _SiblingUnitWorker:
    """Declared physical predicate double. Never starts or represents a thread."""

    def __init__(self):
        self.live = False

    def is_alive(self):
        return self.live


async def _sibling_unit_ordinary(context, target, index):
    """Real original score/Harness/drain code; decoded UNIT wire result only."""
    from types import FunctionType
    from ptc.test_owned_sql_sdk_protocol import _UnitResource
    scope = _scoring_timeout_scope(context.api)
    scope.admission, scope.index = target.admission, index
    scope.task, scope.data = target.sdk_tasks[index], target.public_data[index]
    scope.private = target.admitted.eligible[index]
    scope.trace.task, scope.trace.last_reply = scope.task, "SELECT 1"
    scope.trace.id = f"UNIT_ONLY_ordinary_{index}"
    scope.harness, scope.runtime = object.__new__(context.api.OwnedSqlHarness), object()
    scope.trace.metrics = {}
    scope.harness.config = SimpleNamespace(id="UNIT_ONLY_ordinary")
    wire = _invalid_wire("match")
    ack = _SiblingUnitPublicReturn(not_started=False)
    owner = SimpleNamespace(
        role="scorer", _intent=None, _children=[], _endpoints=[],
        _thread=_SiblingUnitWorker(), _authority=SimpleNamespace(ack=ack),
        _completion=SimpleNamespace(cleanup_ack=ack, outcome=SimpleNamespace(result=wire.result)))
    owner._authority.owner = owner
    item = SimpleNamespace(
        scope=scope, owner=owner, wire=wire, public_return=ack,
        public_tasks=[], resource_tasks=[], rows=[], calls=Counter())

    def check(**kwargs):
        assert all(value is getattr(scope, key) for key, value in kwargs.items())
    scope.check = check

    def unit_scope(**kwargs):
        check(**kwargs)
        return scope

    def reward(name, score):
        scope.trace.rewards[name] = SimpleNamespace(score=score)
    scope.trace.record_reward = reward

    class UnitOnlyResource(_UnitResource):
        async def aclose(self):
            task = asyncio.current_task()
            context.retirement.retain_cleanup(task, "resource-close")
            item.resource_tasks.append(task)
            return await super().aclose()

    class UnitOnlyScorer(UnitOnlyResource):
        async def score_sql(self, prediction):
            assert prediction == "SELECT 1" and asyncio.current_task() is scope.task_score
            item.calls["unit-result-return"] += 1
            return wire.result  # Original encoder/decoder object, not a native result.

        async def aclose(self):
            async def public():
                context.retirement.retain_cleanup(asyncio.current_task(), "owner-close")
                item.calls["public-delegate"] += 1
                return ack
            task = context.loop.create_task(public())
            item.public_tasks.append(task)
            context.hygiene_tasks.append(task)
            assert await context.api._settle(task) is ack
            return await super().aclose()
    item.runner, item.scorer = UnitOnlyResource(), UnitOnlyScorer()
    item.scorer._task, item.scorer._executor = scope.private, target.bound.executor
    item.scorer._instrument, item.scorer._jobs = target.instrument, []
    scope.scorer = item.scorer
    scope.closes.retain(item.runner)
    scope.closes.retain(item.scorer)
    item.runner.validate_program_timeout(5.0)
    await scope.closes.start(item.runner)
    functions = []
    for original in (context.api.OwnedSqlTask.score, context.api.OwnedSqlHarness.score):
        function = FunctionType(
            original.__code__, dict(original.__globals__, _scope=unit_scope),
            original.__name__, original.__defaults__, original.__closure__)
        assert function.__code__ is original.__code__
        functions.append(function)
    score = context.loop.create_task(functions[0](scope.task, scope.trace, scope.runtime))
    harness = context.loop.create_task(functions[1](scope.harness, scope.trace, scope.runtime))
    context.hygiene_tasks.extend((score, harness))
    assert await asyncio.gather(score, harness) == [None, None]
    assert scope.result is wire.result and scope.published and scope.harness_success

    async def agent():
        return scope.trace
    scope.agent_task = context.loop.create_task(agent())
    context.hygiene_tasks.append(scope.agent_task)
    assert await scope.agent_task is scope.trace
    scope.authority = False
    scope.closes.start_all()
    scope.cleanup_task = context.loop.create_task(context.api._drain_scope(scope))
    context.hygiene_tasks.append(scope.cleanup_task)
    assert await scope.cleanup_task is None
    scope.live, scope.token = False, None
    item.rows.append(dict(ok=True, traces=[dict(
        id=scope.trace.id, ok=True, rewards={"execution_accuracy": dict(score=1.0)})]))
    target.admission.scopes.append(scope)
    assert item.calls["unit-result-return"] == item.calls["public-delegate"] == 1
    assert len(item.resource_tasks) == len({id(task) for task in item.resource_tasks}) == 2
    return item


def _sibling_unit_expected_origins(feature, api):
    root = Path(api.__file__).resolve()
    harness = _sibling_unit_nodes(root, owner="OwnedSqlHarness", name="score")
    body, = [node for node in harness.body if isinstance(node, ast.Try)]
    postbase = body.body[1]
    cleanup = _sibling_unit_nodes(root, name="_drain_scope")
    drain_raise, = [node for node in ast.walk(cleanup) if isinstance(node, ast.Raise)]
    check = _sibling_unit_nodes(
        feature.path, owner="_SdkSiblingScoreFailure", name="check_scope")
    injected, = [node for node in ast.walk(check) if isinstance(node, ast.Raise)
                 and isinstance(node.exc, ast.Attribute) and node.exc.attr == "fault"]
    oracle = _sibling_unit_nodes(
        feature.path, owner="_SdkSiblingScoreFailure", name="check_fault_origin")
    gate, = [node for node in ast.walk(oracle) if isinstance(node, ast.Assert)
             and isinstance(node.msg, ast.Constant)
             and node.msg.value == "SDK_SIBLING_FAULT_ORIGIN"]
    return dict(
        harness_postbase=dict(file=root.name, line=postbase.lineno),
        injection=dict(file=feature.path.name, line=injected.lineno),
        cleanup=dict(file=root.name, line=drain_raise.lineno),
        oracle=dict(file=feature.path.name, line=gate.lineno))


async def _sibling_unit_qualification_inputs(context, feature, *, control):
    """DECLARED UNIT final-state inputs, never invoke actor/native validators.

    Physical counts, public-return doubles, finalization and dead-worker doubles
    below are test inputs to the pure qualifier, NOT acquired native evidence.
    In particular we do NOT AST-assemble real ACKs, invoke completed() with
    pretend native receipts, or publish its result as actor qualification.
    """
    target = _sibling_unit_graph(context, feature, omit=control)
    target.public_return = _SiblingUnitPublicReturn(not_started=not control)
    await _sibling_unit_ready(context, target)
    outcome = await _sibling_unit_inject(context, target)
    if control:
        assert outcome is None
        await target.score_task  # All ordinary work BEFORE late oracle.
        await _sibling_unit_start_env(context, target)
        assert await target.env is None
        assert target.controller.owner_checkpoint is target.controller.env_checkpoint is None
        assert not any(getattr(target.controller, name).is_set()
                       for name in ("intent_seen", "owner_held", "env_held"))
    else:
        assert outcome is target.controller.fault
        await _sibling_unit_start_env(context, target)
        await _sibling_unit_finish(context, target)
    target.runner.validate_program_timeout(5.0)
    target.owner._thread = _SiblingUnitWorker()
    ordinary = [await _sibling_unit_ordinary(context, target, index) for index in range(1, 7)]
    items = [target, *ordinary]
    scopes = [item.scope for item in items]
    rows = [row for item in items for row in item.rows]
    episodes = [SimpleNamespace(task=scope.task, ok=scope.trace.ok, traces=[scope.trace])
                for scope in scopes]
    owners, closes, programs, scorers = [], [], [], []
    for item in items:
        scope = item.scope
        public, = item.public_tasks
        assert public.done() and not public.cancelled() and public.result() is item.public_return
        closes.append(SimpleNamespace(actual=item.owner, task=public, ack=public.result()))
        programs.append(SimpleNamespace(
            scope=scope, harness=scope.harness, kwargs=dict(
                data=scope.data, task=scope.private, executor=target.bound.executor,
                instrument=target.instrument),
            runners=[item.runner], validations=[(item.runner, 5.0)],
            closes=[(item.runner, item.runner.close_tasks[0])]))
        if item is target:
            owner_record = target.record
            scorer_record = owner_record.scorer
            scorer_record.result = scope.result
            scorer_record.closes = list(item.scorer.close_tasks)
        else:
            scorer_record = SimpleNamespace(
                scope=scope, actual=item.scorer, score_task=scope.task_score,
                kwargs=dict(task=scope.private, executor=target.bound.executor,
                            instrument=target.instrument), result=scope.result,
                closes=list(item.scorer.close_tasks))
            owner_record = SimpleNamespace(
                actual=item.owner, scope=scope, sdk_task=scope.task, task=scope.private,
                kwargs=dict(executor=target.bound.executor, instrument=target.instrument),
                prediction="SELECT 1", scorer=scorer_record)
        owners.append(owner_record)
        scorers.append(scorer_record)
        for task in (scope.agent_task, scope.task_score, scope.harness_score, scope.cleanup_task):
            context.retirement.retain_task(task)
        assert all(task.done() and not task.cancelled() and task.result() is None
                   for _, task in scope.closes._entries)
    successful = sum(episode.ok for episode in episodes)
    dispatches = 7 if control else 6  # Explicit UNIT physical-input cardinality.
    target.actor.owners = [item.owner for item in items]
    target.actor.slots = [object() for _ in range(dispatches)]
    creators = tuple(object() for _ in range(dispatches))
    target.actor.trace.fence = lambda: creators
    checkpoint = dict(
        decision="sibling-score-failure-observed", planned_tasks=len(target.admitted.planned),
        selected_tasks=len(target.admitted.eligible), excluded_tasks=len(target.admitted.exclusions),
        scopes=len(scopes), policy_requests=len(scopes), overlap=2,
        allocations=len(owners), program_allocations=0, scorer_allocations=len(owners),
        dispatches=dispatches, program_dispatches=0, scorer_dispatches=dispatches,
        target_dispatches=int(control), acks=len(closes), not_started_acks=int(not control),
        owner_closes=len(closes), resource_tasks=sum(len(item.resource_tasks) for item in items),
        runners=len(programs), runner_closes=sum(len(item.runner.close_tasks) for item in items),
        validations=sum(len(item.runner.validations) for item in items),
        returned_results=sum(scope.result is not None for scope in scopes),
        target_returned_results=int(target.scope.result is not None),
        rewards=sum(len(scope.trace.rewards) for scope in scopes),
        target_rewards=len(target.scope.trace.rewards), episodes=len(episodes),
        successful_episodes=successful, failed_episodes=len(episodes)-successful,
        rows=len(rows), successful_rows=sum(row["ok"] for row in rows),
        failed_rows=sum(not row["ok"] for row in rows), target_successful_rows=int(rows[0]["ok"]),
        fault_hits=target.controller.fault_hits, omitted_fault_hits=target.controller.omitted_fault_hits,
        cancelled_score_children=sum(scope.task_score.cancelled() for scope in scopes),
        failed_harness_children=sum(
            not scope.harness_score.cancelled() and scope.harness_score.exception() is not None
            for scope in scopes),
        successful_harness_children=sum(
            not scope.harness_score.cancelled() and scope.harness_score.exception() is None
            for scope in scopes),
        owner_barrier=target.controller.owner_checkpoint is not None,
        env_barrier=target.controller.env_checkpoint is not None)
    bundle = SimpleNamespace(
        actor=target.actor, api=context.api, config=target.config, admitted=target.admitted,
        public_data=target.public_data, sdk_tasks=target.sdk_tasks, owners=owners, closes=closes,
        programs=programs, scorers=scorers,
        results=[(scope.scorer, scope.result) for scope in scopes if scope.result is not None],
        rewards=[(scope.trace, name, reward.score) for scope in scopes
                 for name, reward in scope.trace.rewards.items()],
        program_calls=[], policy=SimpleNamespace(
            calls=7, bodies=[dict(messages=[]) for _ in scopes]),
        policy_scopes=[(None, scope) for scope in scopes], episodes=episodes,
        state=SimpleNamespace(
            agents=[(SimpleNamespace(harness=scope.harness), scope.harness) for scope in scopes],
            runtimes=[scope.runtime for scope in scopes], channels=[], external=[]),
        instrument=target.instrument, executor=target.bound.executor, profile=object(),
        admissions=[], controller=target.controller, hooks=target.controller.hooks,
        codes=target.controller.codes, retained_documents=(b"UNIT ONLY", b"UNIT ONLY"),
        checkpoint=checkpoint)
    feature.namespace["_rows"] = lambda config: rows  # Isolated AST globals, not production patch.
    retirement = context.retirement
    retirement._observe_task_errors()
    retirement.sibling_bundle = bundle  # Declared UNIT input, not completed() evidence.
    if control:
        assert retirement.primary is None and retirement.errors == []
        with pytest.raises(AssertionError) as caught:
            target.controller.check_fault_origin()
        oracle = caught.value
        assert oracle.args == ("SDK_SIBLING_FAULT_ORIGIN",)
        assert _sibling_unit_frames(oracle)[-1].tb_frame.f_code is (
            feature.cls.check_fault_origin.__code__)
        for stage in ("acceptance", "host", "task"):
            retirement.fail(stage, oracle)  # ORIGINAL recorder, SAME original oracle.
        assert target.controller.fault.__traceback__ is None
    retirement.record_outcome(dict(ok=False, **checkpoint))
    # Explicit inert post-retirement predicate inputs, NOT real finalization.
    retirement.finalized = True
    retirement.stages = Counter({"async": 1, "framework": 1, "executor": 1, "undo": 1})
    worker, helper = _SiblingUnitWorker(), _SiblingUnitWorker()
    retirement.workers, retirement.executor_helpers = {worker}, {helper}
    physical = dict(
        native_proof=True, slots=dispatches, nested_safe=dispatches,
        creators=dispatches, creator_waits=dispatches, ambiguous_creators=0,
        live_readers=0, open_slot_fds=0, resource_errors=0,
        nonprimary_errors=0, resource_stop_calls=[1] * 14)
    assert checkpoint["resource_tasks"] == 14
    assert checkpoint["successful_rows"] == checkpoint["successful_episodes"] == dispatches
    expected_errors = ({id(retirement.primary)} if control else {
        id(target.controller.fault), id(target.scope.cleanup_task.exception())})
    assert {id(error) for _, error in retirement.errors} == expected_errors
    return SimpleNamespace(
        target=target, bundle=bundle, rows=rows, physical=physical, worker=worker,
        retirement=retirement)


# 7/8: exact closed qualifier output over EXPLICIT UNIT final-state doubles.
@pytest.mark.parametrize("variant", [
    "baseline", "omitted-control", "missing-native-proof", "extra-native-slot",
    "live-worker", "resource-error", "duplicate-resource-stop", "foreign-final-ledger-error",
    "missing-writer-row", "substituted-ACK",
])
def test_sibling_postretirement_qualification(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()
    qualify = feature.namespace["_sdk_sibling_qualification"]

    async def scenario(context):
        control = variant == "omitted-control"
        case = await _sibling_unit_qualification_inputs(context, feature, control=control)
        origins = _sibling_unit_expected_origins(feature, context.api)
        if control:
            expected = dict(
                verified=True, gate="SDK_SIBLING_FAULT_ORIGIN", origin=origins["oracle"],
                omitted_fault_hits=1, dispatches=7, acks=7, resource_tasks=14,
                successful_episodes=7, successful_rows=7, returned_results=7, rewards=7,
                primary_preserved=True, single_error_identity=True)
        else:
            expected = dict(
                verified=True, episodes=7, successful_episodes=6, failed_episodes=1,
                successful_rows=6, failed_rows=1, dispatches=6, acks=7, not_started_acks=1,
                resource_tasks=14, returned_results=6, rewards=6, target_rewards=0,
                owner_barrier=True, env_barrier=True, distinct_expected_errors=2,
                error_identity_set_match=True, primary_member=True,
                harness_postbase_origin=origins["harness_postbase"],
                injection_origin=origins["injection"], cleanup_origin=origins["cleanup"])
            _sibling_unit_exact(feature.namespace["_sdk_sibling_origins"](case.bundle), origins)
        # Every negative starts from a valid declared UNIT qualifier input.
        _sibling_unit_exact(qualify(case.retirement, case.physical), expected)
        if control:
            _sibling_unit_exact(feature.namespace["_sdk_sibling_oracle_origin"](
                case.retirement.primary, case.bundle), origins["oracle"])
            # Same-identity repetitions are permitted for control too.
            case.retirement.errors.extend([
                ("task", case.retirement.primary), ("acceptance", case.retirement.primary)])
        if variant == "missing-native-proof":
            case.physical["native_proof"] = False
        elif variant == "extra-native-slot":
            case.physical["slots"] += 1
        elif variant == "live-worker":
            case.worker.live = True
        elif variant == "resource-error":
            case.physical["resource_errors"] = 1
        elif variant == "duplicate-resource-stop":
            case.physical["resource_stop_calls"][0] = 2
        elif variant == "foreign-final-ledger-error":
            case.retirement.errors.append(("task", RuntimeError("UNIT_ONLY late foreign error")))
        elif variant == "missing-writer-row":
            case.rows.pop()
        elif variant == "substituted-ACK":
            case.bundle.closes[0].ack = _SiblingUnitPublicReturn(not_started=True)
            assert case.bundle.closes[0].ack is not case.target.public_return
        before = tuple(case.retirement.errors), case.retirement.primary
        if variant in ("baseline", "omitted-control"):
            _sibling_unit_exact(qualify(case.retirement, case.physical), expected)
        else:
            with pytest.raises(AssertionError):
                qualify(case.retirement, case.physical)
        assert tuple(case.retirement.errors) == before[0]
        assert case.retirement.primary is before[1] and case.retirement.outcome["ok"] is False
        assert case.retirement.safe_emissions == 0  # UNIT predicates cannot publish SAFE.
        case.worker.live = False
    _sibling_unit_run(_invalid_unit_api, feature, scenario)


def _sibling_unit_checkpoint_keys():
    return set((
        "decision planned_tasks selected_tasks excluded_tasks scopes policy_requests overlap "
        "allocations program_allocations scorer_allocations dispatches program_dispatches "
        "scorer_dispatches target_dispatches acks not_started_acks owner_closes resource_tasks "
        "runners runner_closes validations returned_results target_returned_results rewards "
        "target_rewards episodes successful_episodes failed_episodes rows successful_rows "
        "failed_rows target_successful_rows fault_hits omitted_fault_hits cancelled_score_children "
        "failed_harness_children successful_harness_children owner_barrier env_barrier").split())


def _sibling_unit_calls(node, name):
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)
            and ((isinstance(child.func, ast.Attribute) and child.func.attr == name)
                 or (isinstance(child.func, ast.Name) and child.func.id == name))]


def _sibling_unit_constants(node):
    return [child.value for child in ast.walk(node) if isinstance(child, ast.Constant)]


def _sibling_unit_original_driver(lifecycle, *, phase):
    """Original driver code on in-memory process/stream/ledger receivers ONLY."""
    calls, retained, owners, registry = Counter(), [], [], []

    class UnitStream:
        closed = False

        def close(self):
            self.closed = True

        def write(self, value):
            assert value == b"S"
            calls["stop-write"] += 1

    class UnitPath:
        def __truediv__(self, name):
            assert name in {"owned-guest-fixture.py", "owned-guest-fixture.stderr"}
            return self

        def __str__(self):
            return "UNIT_ONLY_NO_FILES_OR_PROCESS"

        def write_text(self, value):
            assert value == "UNIT ONLY, NEVER EXECUTED"
            calls["memory-script"] += 1
    process = SimpleNamespace(
        pid=object(), returncode=1, actual_wait=False,
        stdin=UnitStream(), stdout=UnitStream(), stderr=UnitStream())

    def wait(*, timeout):
        assert timeout > 0
        process.actual_wait = True
        calls["wait"] += 1
        return 1

    def construct(*args, **kwargs):
        assert kwargs["registry"] is registry
        assert not registry and not owners
        registry.append(process)
        owners.append(process)
        calls["unit-process"] += 1
        return process  # No actual Popen/OS process/port/pipe/signal.

    def loads(value):
        result = json.loads(value)
        retained.append(result)
        return result
    process.wait, process.poll = wait, lambda: 1
    log = UnitStream()
    namespace = _repair_namespace(
        lifecycle.name, ["_owned_guest_case"], extra=dict(
            _OWNED_GUEST_PROBE="UNIT ONLY, NEVER EXECUTED",
            _GuestOuterLedger=lambda: registry, _OwnedProbeProcess=construct,
            _OWNED_GUEST_OUTER_OWNERS=owners,
            _line=lambda actual, timeout: json.dumps(dict(ok=False, safe=True)),
            open=lambda *args, **kwargs: log,
            m=SimpleNamespace(installed_source_root=lambda: "UNIT_ONLY_ROOT"),
            sys=SimpleNamespace(executable="UNIT_ONLY_NO_PYTHON_EXECUTION"),
            subprocess=SimpleNamespace(PIPE=object()),
            json=SimpleNamespace(loads=loads, dumps=json.dumps)))
    original = namespace["_owned_guest_case"]
    with pytest.raises(AssertionError) as caught:
        original(UnitPath(), "scorer", phase, prepared=(1, 2, 3, 4, 5), expected_ok=True)
    result, = retained
    assert caught.value.args[0] is result
    assert calls["unit-process"] == calls["memory-script"] == calls["stop-write"] == 1
    assert calls["wait"] == 2 and process.actual_wait and log.closed
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    assert registry == owners == []  # Actual UNIT ledgers, not real process registries.
    assert result["outer_retirement"] == dict(
        actual_wait=True, returncode=1, streams_closed=True, ledger_released=True)
    return original, caught.value, result


# 8/8: SOURCE contracts, no actor-case invocation or native receipt assembly.
@pytest.mark.parametrize("variant", [
    "phase", "selector", "strict-positive-refusal", "unchanged-hooks",
    "preconstruction-gate-registration", "cleanup-task-roles", "closed-receipt-shapes",
    "unchanged-timeouts-fence-diagnostics", "selector-confined-to-injection",
    "release-never-fabricates-observations",
])
def test_sibling_source_contract(_invalid_unit_api, variant):
    feature = _sibling_unit_feature()
    api = _invalid_unit_api
    cls, = [node for node in feature.tree.body if isinstance(node, ast.ClassDef)
            and node.name == "_SdkSiblingScoreFailure"]
    methods = {node.name: node for node in cls.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    acceptance = _sibling_unit_nodes(feature.path, name="_sdk_acceptance")
    lifecycle = Path(__file__).with_name("test_sql_lifecycle_process.py")
    driver = _sibling_unit_nodes(lifecycle, name="_owned_guest_case")
    phase, selector = "sdk-sibling-score-failure", "omit-sibling-fault"
    if variant == "phase":
        assert phase in _sibling_unit_constants(acceptance)
        assert phase in _sibling_unit_constants(driver)
        assert phase in _sibling_unit_constants(_compat_guest_tree())
        host = _sibling_unit_nodes(feature.path, name="_run_sdk_host_case")
        assert [arg.arg for arg in host.args.kwonlyargs] == [
            "loop", "root", "prepared", "phase", "mutant", "profile", "executor", "actor"]
        assert host.args.args == [] and host.args.kwarg is host.args.vararg is None
        completed = _sibling_unit_nodes(feature.path, name="_sdk_sibling_completed")
        oracle, = _sibling_unit_calls(completed, "check_fault_origin")
        stores = [node for node in ast.walk(completed) if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Attribute) and target.attr == "sibling_bundle"
                          for target in node.targets)]
        assert len(stores) == 1 and stores[0].lineno < oracle.lineno
        outcomes = _sibling_unit_calls(completed, "record_outcome")
        assert outcomes and all(node.lineno < oracle.lineno for node in outcomes)
    elif variant == "selector":
        assert selector in _sibling_unit_constants(acceptance)
        assert selector in _sibling_unit_constants(driver)
        # Evaluate ONLY trusted input predicates, never the process driver.
        environment = dict(
            phase=phase, mutant=selector, role="scorer", prepared=(1, 2, 3, 4, 5),
            expected_ok=True, type=type, len=len)
        predicates = [node.test for node in driver.body if isinstance(node, ast.Assert)
                      and selector in _sibling_unit_constants(node)]
        assert predicates, "SDK_SIBLING_IMMUTABLE_SELECTOR_ALLOWLIST_MISSING"
        assert all(eval(compile(ast.Expression(body=node), str(lifecycle), "eval"),
                        {}, environment) for node in predicates)
        confined = [node for node in predicates if "expected_ok" in {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)}]
        assert confined
        assert all(not eval(compile(ast.Expression(body=node), str(lifecycle), "eval"),
                            {}, dict(environment, expected_ok=False)) for node in confined)
        assert all(not eval(compile(ast.Expression(body=node), str(lifecycle), "eval"),
                            {}, dict(environment, role="program")) for node in confined)
    elif variant == "strict-positive-refusal":
        environment = dict(
            phase=phase, expected_ok=True, result=dict(ok=False, safe=True),
            process=SimpleNamespace(returncode=1))
        candidates = []
        for node in ast.walk(driver):
            if not isinstance(node, ast.If) or len(node.body) != 1:
                continue
            raised = node.body[0]
            if (isinstance(raised, ast.Raise) and isinstance(raised.exc, ast.Call)
                    and isinstance(raised.exc.func, ast.Name)
                    and raised.exc.func.id == "AssertionError"
                    and len(raised.exc.args) == 1 and not raised.exc.keywords
                    and isinstance(raised.exc.args[0], ast.Name)
                    and raised.exc.args[0].id == "result"
                    and phase in _sibling_unit_constants(node.test)):
                candidates.append((node, raised))
        (node, raised), = candidates
        assert eval(compile(ast.Expression(body=node.test), str(lifecycle), "eval"),
                    {}, environment)
        assert not eval(compile(ast.Expression(body=node.test), str(lifecycle), "eval"), {}, dict(
            environment, result=dict(ok=True, safe=True), process=SimpleNamespace(returncode=0)))
        original, error, result = _sibling_unit_original_driver(lifecycle, phase=phase)
        leaf = _sibling_unit_frames(error)[-1]
        assert leaf.tb_frame.f_code is original.__code__ and leaf.tb_lineno == raised.lineno
        assert leaf.tb_frame.f_locals["result"] is result
        assert error.args == (result,) and error.args[0] is result
        # These are honest UNIT receiver calls. Actual outer process wait,
        # closed streams and both ownership registries still require actors.
    elif variant == "unchanged-hooks":
        assert api._check_hooks() is None
        assert cls.bases == []
        protected = {"score", "fail", "task_score", "harness_score", "harness_success",
                     "harness_done", "cleanup_task", "result", "published", "authority"}
        for node in ast.walk(cls):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr in protected:
                        assert isinstance(target.value, ast.Name) and target.value.id == "self"
        assert not _sibling_unit_calls(methods["check_scope"], "fail")
        assert not any(_sibling_unit_calls(method, "cancel") for method in methods.values())
        assert not any(_sibling_unit_calls(method, "setattr") for method in methods.values())
        assert api.OwnedSqlTask.score.__globals__["_scope"] is api._scope
        assert api.OwnedSqlHarness.score.__globals__["_scope"] is api._scope
    elif variant == "preconstruction-gate-registration":
        init = methods["__init__"]
        signature = inspect.signature(feature.cls.__init__).parameters
        assert tuple(signature) == ("self", "api", "actor", "scope", "target_data", "omit_fault")
        assert all(signature[name].kind is inspect.Parameter.KEYWORD_ONLY
                   for name in tuple(signature)[1:])
        assert "configure" not in methods
        positional = [node for node in ast.walk(init) if isinstance(node, ast.For)
                      and _sibling_unit_calls(node.iter, "zip")]
        loop, = positional
        counts = [node for node in ast.walk(init) if isinstance(node, ast.Assert)
                  and _sibling_unit_calls(node.test, "len")
                  and any(isinstance(child, ast.Attribute)
                          and child.attr in {"planned", "eligible", "exclusions"}
                          for child in ast.walk(node.test))]
        assert len(counts) >= 3 and all(node.lineno < loop.lineno for node in counts)
        locks = [node for node in ast.walk(init) if isinstance(node, ast.With)
                 and any(isinstance(item.context_expr, ast.Attribute)
                         and item.context_expr.attr == "spawn_lock" for item in node.items)]
        locked, = locks
        registration = [node for node in _sibling_unit_calls(locked, "append")
                        if any(isinstance(child, (ast.Name, ast.Attribute))
                               and (getattr(child, "id", None) == "controller_gate"
                                    or getattr(child, "attr", None) == "controller_gate")
                               for child in ast.walk(node))]
        assert len(registration) == 1
        assert all(node.lineno < registration[0].lineno for node in counts)
        assert not _sibling_unit_calls(locked, "wait")
        assert not _sibling_unit_calls(init, "_supported")
        for call in _sibling_unit_calls(init, "check"):
            assert not (isinstance(call.func.value, ast.Name)
                        and call.func.value.id in {"admission", "bound"})
        observed, = [node for node in acceptance.body if isinstance(node, ast.FunctionDef)
                     and node.name == "observed_init"]
        retained, = _sibling_unit_calls(observed, "retain_owner")
        constructed, = _sibling_unit_calls(observed, "original_init")
        assert retained.lineno < constructed.lineno
    elif variant == "cleanup-task-roles":
        allowed = {"owner-close", "resource-close", "scope-drain"}
        calls = _sibling_unit_calls(cls, "retain_cleanup") + _sibling_unit_calls(
            acceptance, "retain_cleanup")
        assert calls
        literal_roles = set()
        for call in calls:
            assert len(call.args) == 2
            role = call.args[1]
            if isinstance(role, ast.Constant):
                assert role.value in allowed
                literal_roles.add(role.value)
            else:
                assert isinstance(role, ast.Name) and role.id == "kind"
        assert {"owner-close", "scope-drain"} <= literal_roles
        assert _sibling_unit_calls(methods["settle_cleanup"], "retain_task")
        assert not _sibling_unit_calls(cls, "retain_driver")
    elif variant == "closed-receipt-shapes":
        completed = _sibling_unit_nodes(feature.path, name="_sdk_sibling_completed")
        shapes = []
        for node in ast.walk(completed):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
                shapes.append({keyword.arg for keyword in node.keywords})
            elif isinstance(node, ast.Dict):
                shapes.append({key.value for key in node.keys if isinstance(key, ast.Constant)})
        assert _sibling_unit_checkpoint_keys() in shapes

        async def scenario(context):
            case = await _sibling_unit_ready(context, _sibling_unit_graph(context, feature))
            assert await _sibling_unit_inject(context, case) is case.controller.fault
            await _sibling_unit_start_env(context, case)
            await _sibling_unit_finish(context, case)
            assert case.controller.owner_checkpoint == _sibling_unit_owner_facts()
            assert case.controller.env_checkpoint == _sibling_unit_env_facts()
            assert case.controller.check_fault_origin() is None
            assert case.controller.check_provenance() is None
            assert case.controller.check_ledger() is None
        _sibling_unit_run(api, feature, scenario)
    elif variant == "unchanged-timeouts-fence-diagnostics":
        import hashlib
        expected = {
            "_SdkRetirement": "800f4483b28823ccf418a995b7e6656983f4e5a29b5adda7550f561b9edf355b",
            "_sdk_timeout_error_diagnostic": "9258bcf8f0b6c72b9d22c0bd979ff7d070453e9af46662a953fd91fafe8c1565",
        }
        for name, digest in expected.items():
            node, = [node for node in feature.tree.body if getattr(node, "name", None) == name]
            assert hashlib.sha256(ast.get_source_segment(
                feature.source, node).encode()).hexdigest() == digest
        cancellation = Path(__file__).with_name("test_owned_sql_sdk_program_cancellation.py")
        assert hashlib.sha256(cancellation.read_bytes()).hexdigest() == (
            "764515ed9f913aa10165075fb4901a0ea23b9a7654fda7de9c363a12e19b72c0")
        assert 19.5 in _sibling_unit_constants(driver)
        run = methods["run_controller"]
        assert 3.75 in _sibling_unit_constants(run)
        assert any(isinstance(node, ast.Attribute) and node.attr == "end" for node in ast.walk(run))
        assert not _sibling_unit_calls(cls, "wait_for")
        assert not any(isinstance(node, ast.Name) and node.id == "SAFETY_SECONDS"
                       for node in ast.walk(cls))
        for name in ("_sdk_timeout_completed", "_sdk_timeout_qualification"):
            function = _sibling_unit_nodes(feature.path, name=name)
            assert any(isinstance(node, ast.Compare)
                       and any(isinstance(other, ast.Tuple) and not other.elts
                               for other in node.comparators)
                       and _sibling_unit_calls(node.left, "fence")
                       for node in ast.walk(function))
    elif variant == "selector-confined-to-injection":
        for name, method in methods.items():
            for node in ast.walk(method):
                if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                        and node.attr in {"omit_fault", "_omit_fault"}):
                    assert name == "check_scope"
        queue, = [node for node in acceptance.body if isinstance(node, ast.FunctionDef)
                  and node.name == "release_sibling_dispatch"]
        assert selector not in _sibling_unit_constants(queue)
        assert not any(isinstance(node, ast.Attribute) and node.attr in {"omit_fault", "_omit_fault"}
                       for node in ast.walk(queue))
        attributes = {node.attr for node in ast.walk(queue) if isinstance(node, ast.Attribute)}
        assert {"harness_success", "authority"} <= attributes
        assert all(_sibling_unit_calls(queue, name) for name in ("done", "cancelled", "exception"))
        assert _sibling_unit_calls(acceptance, "add_done_callback")
        observed, = [node for node in acceptance.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name == "observed_close"]
        assert _sibling_unit_calls(observed, "release_sibling_dispatch")

        async def scenario(context):
            case = await _sibling_unit_ready(
                context, _sibling_unit_graph(context, feature, omit=True))
            assert await _sibling_unit_inject(context, case) is None
            await case.score_task
            await _sibling_unit_start_env(context, case)
            assert await case.env is None
            assert case.controller.fault_hits == 0 and case.controller.omitted_fault_hits == 1
            assert case.controller.owner_checkpoint is case.controller.env_checkpoint is None
            assert case.originals == [] and case.calls["public-delegate"] == 1
            assert not any(getattr(case.controller, name).is_set()
                           for name in ("intent_seen", "owner_held", "env_held"))
        _sibling_unit_run(api, feature, scenario)
    else:
        assert variant == "release-never-fabricates-observations"
        release = methods["release"]
        for call in _sibling_unit_calls(release, "set"):
            assert isinstance(call.func.value, ast.Attribute)
            assert call.func.value.attr in {
                "controller_gate", "owner_release", "env_release", "observer_wake"}

        async def scenario(context):
            case = await _sibling_unit_ready(context, _sibling_unit_graph(context, feature))
            controller = case.controller
            observations = (
                "postbase_seen", "intent_seen", "owner_entered", "owner_held", "env_held")
            assert not any(getattr(controller, name).is_set() for name in observations)
            assert controller.release() is None and controller.release() is None
            assert all(getattr(controller, name).is_set() for name in (
                "controller_gate", "owner_release", "env_release", "observer_wake"))
            assert not any(getattr(controller, name).is_set() for name in observations)
            assert controller.postbase_hits == controller.fault_hits == controller.omitted_fault_hits == 0
            assert controller.owner_checkpoint is controller.env_checkpoint is None
            assert controller.receipt is controller.cancel_error is None
            assert controller.fault.__traceback__ is None and case.originals == []
            assert not case.score_task.done()
        _sibling_unit_run(api, feature, scenario)


# Sibling diagnostic track, exactly 23 pure cases in twelve frozen groups.
# UNIT receivers below are never native/ACK/SAFE or actor qualification.
_SIBLING_DIAG_ROOTS = (
    "_sdk_sibling_completed",
    "_sdk_acceptance.observe_sibling_scope",
    "_sdk_acceptance.release_sibling_dispatch",
    "_sdk_acceptance.sibling_harness_done",
    "_sdk_acceptance.observed_scope_check",
    "_sdk_acceptance",
    "_run_sdk_host_case",
    "_SdkSiblingScoreFailure.checkpoint_owner",
    "_SdkSiblingScoreFailure.checkpoint_env",
    "_SdkSiblingScoreFailure.check_fault_origin",
    "_SdkSiblingScoreFailure.check_provenance",
    "_SdkSiblingScoreFailure.check_ledger",
    "_SdkSiblingScoreFailure._locations",
    "_SdkSiblingScoreFailure._frames",
    "_sdk_sibling_qualification",
    "_sdk_sibling_origins",
    "_sdk_sibling_oracle_origin",
    "_SdkSiblingScoreFailure.check_scope",
)


def _sibling_diag_feature():
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    source = path.read_text()
    tree = ast.parse(source)
    apis = (
        "_sdk_sibling_diagnostic_refs", "_sdk_sibling_error_diagnostic",
        "_sdk_sibling_persist_host_result")
    missing = set(apis) - {getattr(node, "name", None) for node in tree.body}
    assert not missing, ("NEW_FEATURE_SIBLING_DIAGNOSTIC_API_ABSENT", sorted(missing))
    names = apis + (
        "_SdkSiblingScoreFailure", "_sdk_sibling_completed", "_sdk_acceptance",
        "_run_sdk_host_case", "_sdk_sibling_qualification",
        "_sdk_sibling_origins", "_sdk_sibling_oracle_origin")
    ns = _repair_namespace(path.name, names, extra={"__file__": str(path)})
    refs = ns[apis[0]]()
    assert type(refs) is tuple and tuple(label for label, _ in refs) == _SIBLING_DIAG_ROOTS
    return SimpleNamespace(path=path, source=source, tree=tree, ns=ns, refs=refs,
                           diagnostic=ns[apis[1]], persist=ns[apis[2]])


def _sibling_diag_error(feature):
    controller = SimpleNamespace(owner_checkpoint=object(), owner_held=threading.Event())
    error = _timeout_diag_caught(
        lambda: feature.ns["_SdkSiblingScoreFailure"].checkpoint_owner(controller, rows=[]))
    assert type(error) is AssertionError
    return error


def _sibling_diag_receipt(feature, primary, errors):
    owner = _timeout_diag_owner(primary, errors)
    before = tuple(owner.errors)
    payload = feature.diagnostic(owner, feature.refs)
    assert owner.primary is primary and len(owner.errors) == len(before)
    assert all(a[0] is b[0] and a[1] is b[1]
               for a, b in zip(owner.errors, before, strict=True))
    assert set(payload) == {
        "ledger_total", "ledger_omitted", "primary_present", "primary_token",
        "primary_type", "primary_origin", "primary_seen_in_sample", "entries"}
    assert len(payload["entries"]) <= 16
    raw = (json.dumps(dict(kind="SDK_SIBLING_FINAL_LEDGER", diagnostic=payload),
                      separators=(",", ":")) + "\n").encode()
    assert len(raw) <= 8192 and b"UNIT_PRIVATE_CANARY" not in raw
    return payload


@pytest.mark.parametrize("outside", (False, True))
def test_sibling_diagnostic_snapshot_identity(outside):
    feature = _sibling_diag_feature()
    primary, other = AssertionError(), AssertionError()
    errors = ([("task", other)] * 16 + [("acceptance", primary)] if outside
              else [("acceptance", primary), ("host", other), ("task", primary)])
    payload = _sibling_diag_receipt(feature, primary, errors)
    assert payload["primary_token"] == 1
    assert payload["primary_seen_in_sample"] is (not outside)
    assert [row["error_token"] for row in payload["entries"]] == (
        [2] * 16 if outside else [1, 2, 1])
    assert payload["ledger_total"] == len(errors)


@pytest.mark.parametrize("hostile", (False, True))
def test_sibling_diagnostic_closed_types_and_privacy(hostile):
    feature = _sibling_diag_feature()
    calls = []

    class Bomb(AssertionError):
        def forbidden(self, *args):
            calls.append(True)
            raise RuntimeError("UNIT_PRIVATE_CANARY")
        __eq__ = __hash__ = __str__ = __repr__ = forbidden
        def __getattribute__(self, name):
            return self.forbidden()

    objects = ([Bomb("UNIT_PRIVATE_CANARY"), object()] if hostile else [
        cls("UNIT_PRIVATE_CANARY") for cls in (
            AssertionError, AttributeError, RuntimeError, TypeError,
            ValueError, TimeoutError, KeyError)])
    payload = _sibling_diag_receipt(feature, objects[0], [("task", e) for e in objects])
    assert [row["type"] for row in payload["entries"]] == (
        ["OTHER", "OTHER"] if hostile else [
            "AssertionError", "AttributeError", "RuntimeError", "TypeError",
            "ValueError", "TimeoutError", "OTHER"])
    assert calls == []
    assert _sibling_diag_receipt(feature, None, [])["primary_type"] == "NONE"


@pytest.mark.parametrize("mode", ("ledger", "traceback"))
def test_sibling_diagnostic_bounds(mode):
    from types import TracebackType
    feature = _sibling_diag_feature()
    error = _sibling_diag_error(feature)
    if mode == "ledger":
        payload = _sibling_diag_receipt(feature, error, [("task", error)] * 17)
        assert len(payload["entries"]) == 16 and payload["ledger_omitted"] == 1
    else:
        leaf = _timeout_diag_leaf(error)
        tb = None
        for _ in range(33):
            tb = TracebackType(tb, leaf.tb_frame, leaf.tb_lasti, leaf.tb_lineno)
        error.__traceback__ = tb
        assert _sibling_diag_receipt(feature, error, [])["primary_origin"] == "OTHER"


@pytest.mark.parametrize("mode", ("statement", "comprehension", "foreign-copy", "undeclared"))
def test_sibling_diagnostic_ast_origins(mode):
    from types import FunctionType, TracebackType
    feature = _sibling_diag_feature()
    error = _sibling_diag_error(feature)
    leaf = _timeout_diag_leaf(error)
    label = "_SdkSiblingScoreFailure.checkpoint_owner"
    method = _sibling_unit_nodes(feature.path, owner="_SdkSiblingScoreFailure",
                                 name="checkpoint_owner")
    expected_leaf, site, line = "function", "assert", leaf.tb_lineno
    if mode == "comprehension":
        # Original generator code/frame under the declared assignment, no SDK.
        codes = [code for name, code in feature.refs if name == label]
        gen, = [code for code in codes[0].co_consts
                if getattr(code, "co_name", None) == "<genexpr>"
                and code.co_firstlineno == next(
                    n.lineno for n in ast.walk(method)
                    if isinstance(n, ast.GeneratorExp) and isinstance(n.elt, ast.Call))]
        iterator = iter([{"traces": None}])  # Builtin TypeError in ORIGINAL genexpr.
        function = FunctionType(gen, feature.ns,
                                closure=tuple(_sibling_diag_cell(SimpleNamespace(
                                    trace=SimpleNamespace(id="UNIT"))) for _ in gen.co_freevars))
        generator = function(iterator)
        error = _timeout_diag_caught(lambda: next(generator))
        assert _timeout_diag_leaf(error).tb_frame.f_code is gen
        assignment, = [n for n in method.body if isinstance(n, ast.Assign)
                        and any(isinstance(x, ast.Name) and x.id == "facts" for x in n.targets)]
        expected_leaf, site, line = "genexpr", "assign", assignment.lineno
    elif mode == "foreign-copy":
        original = feature.ns["_SdkSiblingScoreFailure"].checkpoint_owner
        copied = FunctionType(original.__code__.replace(), original.__globals__)
        assert copied.__code__ is not original.__code__
        error = _timeout_diag_caught(lambda: copied(
            SimpleNamespace(owner_checkpoint=True), rows=[]))
    elif mode == "undeclared":
        statement, = [n for n in method.body if isinstance(n, ast.Assign)
                       and isinstance(n.targets[0], ast.Attribute)]
        error.__traceback__ = TracebackType(None, leaf.tb_frame, leaf.tb_lasti,
                                           statement.end_lineno + 1)
    origin = _sibling_diag_receipt(feature, error, [])["primary_origin"]
    if mode in ("foreign-copy", "undeclared"):
        assert origin == "OTHER"
    else:
        assert origin == dict(file=feature.path.name, function=label,
                              line=line, site=site, leaf=expected_leaf)


def _sibling_diag_cell(value):
    return (lambda: value).__closure__[0]


def test_sibling_diagnostic_refs_precede_scheduling():
    from types import CodeType
    feature = _sibling_diag_feature()
    host = _sibling_unit_nodes(feature.path, name="_run_sdk_host_case")
    capture, = [n for n in ast.walk(host) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == "sibling_diagnostic_refs"
                        for t in n.targets)]
    schedule, = _sibling_unit_calls(host, "_sdk_acceptance")
    assert capture.lineno < schedule.lineno
    acceptance = feature.ns["_sdk_acceptance"].__code__
    for label, code in feature.refs:
        assert type(code) is CodeType
        if label.startswith("_sdk_acceptance."):
            assert any(code is value for value in acceptance.co_consts)
    assert len(feature.refs) == 18
    assert feature.ns["_sdk_sibling_diagnostic_refs"]() is not feature.refs


def _sibling_diag_report(feature, *, failure=None):
    import builtins
    from types import MethodType
    primary = _sibling_diag_error(feature)
    owner = _timeout_diag_owner()
    owner.fail = MethodType(_SdkRetirement.fail, owner)
    owner.outcome = dict(ok=False)
    owner.fail("acceptance", primary)
    owner.sibling_diagnostic_refs = feature.refs
    owner.stages, owner.workers, owner.executor_helpers, owner.resources = Counter(), set(), set(), []
    owner.finalized = True  # UNIT physical receiver, not a physical claim.
    events, stderr, stdout, exits = [], [], [], []
    def prove_safe():
        events.append("physical")
        return True
    owner.prove_safe = prove_safe
    def diagnostic(retirement, refs):
        events.append("diagnostic")
        assert retirement.primary is primary and len(retirement.errors) == 2
        assert retirement.errors[-1][0] == "sibling-qualifier"
        if failure == "helper":
            raise ValueError("UNIT_PRIVATE_CANARY")
        return feature.diagnostic(retirement, refs)
    def unit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ptc.test_owned_sql_sdk_canonical":
            available = dict(
                _sdk_sibling_qualification=feature.ns["_sdk_sibling_qualification"],
                _sdk_sibling_error_diagnostic=diagnostic)
            return SimpleNamespace(**{key: available[key] for key in fromlist})
        return builtins.__import__(name, globals, locals, fromlist, level)
    def write(fd, raw):
        assert fd == 2
        events.append("write")
        stderr.append(raw)
        if failure == "write":
            raise OSError("UNIT_PRIVATE_CANARY")
        return len(raw) - (failure == "short")
    report, = [n for n in ast.walk(_compat_guest_tree())
               if isinstance(n, ast.FunctionDef) and n.name == "report"]
    ns = dict(
        __builtins__=dict(vars(builtins), __import__=unit_import),
        PHASE="sdk-sibling-score-failure", sdk_resources=owner,
        finished=SimpleNamespace(is_set=lambda: True), native_fds=set(), native_entries=[],
        slots=[], END=time.monotonic() + 1, sdk_native_proof=lambda: True,
        keeper=SimpleNamespace(join=lambda **kw: None, is_alive=lambda: False),
        os=SimpleNamespace(write=write, _exit=exits.append), time=time, json=json,
        Path=Path, write_record=lambda fd, row: stdout.append(row))
    exec(compile(ast.Module(body=[report], type_ignores=[]),
                 str(feature.path.with_name("test_sql_lifecycle_process.py")), "exec"), ns)
    ns["report"](dict(ok=False), 1)
    assert owner.primary is primary and owner.errors[0][1] is primary
    assert len(owner.errors) == 2 and owner.outcome == dict(ok=False, error="AssertionError")
    assert stdout[0]["ok"] is False and stdout[0]["safe"] is True and exits == [1]
    return SimpleNamespace(owner=owner, events=events, stderr=stderr, stdout=stdout)


@pytest.mark.parametrize("failure", ("helper", "write", "short"))
def test_sibling_diagnostic_emission_failure_preserves_failure(failure):
    feature = _sibling_diag_feature()
    case = _sibling_diag_report(feature, failure=failure)
    assert case.events == ["physical", "diagnostic", "write"]
    assert len(case.stderr) == 1
    if failure == "helper":
        assert json.loads(case.stderr[0]) == dict(kind="SDK_SIBLING_FINAL_LEDGER_UNAVAILABLE")


def test_sibling_diagnostic_after_final_qualifier():
    feature = _sibling_diag_feature()
    case = _sibling_diag_report(feature)
    assert case.events == ["physical", "diagnostic", "write"]
    payload = json.loads(case.stderr[0])["diagnostic"]
    assert payload["ledger_total"] == 2
    assert payload["entries"][1]["stage"] == "sibling-qualifier"
    assert payload["entries"][1]["type"] == "AttributeError"
    assert payload["entries"][1]["origin"]["function"] == "_sdk_sibling_qualification"
    assert case.stdout[0]["program_physical"]["nonprimary_errors"] == 0


def _sibling_diag_host_tail(feature, result, destination, persist):
    actor = _sibling_unit_nodes(feature.path, name="_sibling_actor_case")
    calls = _sibling_unit_calls(actor, "_sdk_sibling_persist_host_result")
    assert len(calls) == 1
    call, = calls
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "result"
    assert ast.dump(call.keywords[0].value) == ast.dump(
        ast.parse('tmp_path / "sibling-host-result.json"', mode="eval").body)
    count, = [n for n in actor.body if isinstance(n, ast.Assign)
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "count"]
    same = [n for n in ast.walk(actor) if isinstance(n, ast.Compare)
            and any(isinstance(op, ast.Is) for op in n.ops)
            and any(isinstance(x, ast.Name) and x.id == "result"
                    for x in [n.left, *n.comparators])]
    assert same and max(n.lineno for n in same) < call.lineno < count.lineno
    statement, = [n for n in actor.body if n.lineno <= call.lineno <= n.end_lineno]
    body = [n for n in actor.body if n.lineno >= statement.lineno]
    ns = dict(result=result, tmp_path=destination.parent, control=False,
              _sdk_sibling_persist_host_result=persist)
    return _timeout_diag_caught(lambda: exec(
        compile(ast.Module(body=body, type_ignores=[]), str(feature.path), "exec"), ns))


def test_sibling_host_result_identity_before_counts(tmp_path):
    feature = _sibling_diag_feature()
    result = dict(safe=True, ok=False, error="AssertionError")
    destination = tmp_path / "sibling-host-result.json"
    seen = []
    def persist(actual, *, destination):
        assert actual is result
        seen.append(actual)
        return feature.persist(actual, destination=destination)
    error = _sibling_diag_host_tail(feature, result, destination, persist)
    assert type(error) is KeyError and error.args == ("planned_tasks",)
    assert len(seen) == 1 and seen[0] is result
    assert json.loads(destination.read_bytes()) == result
    assert destination.stat().st_mode & 0o777 == 0o600
    original = destination.read_bytes()
    assert feature.persist(dict(ok=True), destination=destination) is False
    assert destination.read_bytes() == original


@pytest.mark.parametrize("mode", ("oversize", "unknown-private", "nested", "string"))
def test_sibling_host_result_rejects_unsafe_payload(tmp_path, mode):
    feature = _sibling_diag_feature()
    destination = tmp_path / "sibling-host-result.json"
    payload = {
        "oversize": dict(program_physical=dict(resource_stop_calls=[1] * 33000)),
        "unknown-private": dict(db_path="UNIT_PRIVATE_CANARY"),
        "nested": dict(sibling_qualification=dict(verified=False, extra=object())),
        "string": dict(error="UNIT_PRIVATE_CANARY"),
    }[mode]
    assert feature.persist(payload, destination=destination) is False
    assert not destination.exists()


def test_sibling_host_result_io_failure_preserves_failure(tmp_path):
    feature = _sibling_diag_feature()
    result = dict(ok=False, error="AssertionError")
    destination = tmp_path / "missing" / "sibling-host-result.json"
    assert feature.persist(result, destination=destination) is False
    error = _sibling_diag_host_tail(
        feature, result, destination, lambda actual, **kw: feature.persist(
            actual, destination=destination))
    assert type(error) is KeyError and error.args == ("planned_tasks",)
    assert result == dict(ok=False, error="AssertionError")


def test_sibling_diagnostic_frozen_contracts():
    import hashlib
    feature = _sibling_diag_feature()
    for name, digest in (
        ("_SdkRetirement", "800f4483b28823ccf418a995b7e6656983f4e5a29b5adda7550f561b9edf355b"),
        ("_sdk_timeout_error_diagnostic", "9258bcf8f0b6c72b9d22c0bd979ff7d070453e9af46662a953fd91fafe8c1565"),
    ):
        node, = [n for n in feature.tree.body if getattr(n, "name", None) == name]
        assert hashlib.sha256(ast.get_source_segment(feature.source, node).encode()).hexdigest() == digest
    acceptance = _sibling_unit_nodes(feature.path, name="_sdk_acceptance")
    refs, = [n for n in ast.walk(acceptance) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Attribute) and t.attr == "timeout_diagnostic_refs"
                     for t in n.targets)]
    assert len(refs.value.elts) == 6
    for name in ("_sdk_timeout_completed", "_sdk_timeout_qualification"):
        node = _sibling_unit_nodes(feature.path, name=name)
        assert any(isinstance(n, ast.Compare) and _sibling_unit_calls(n.left, "fence")
                   and any(isinstance(x, ast.Tuple) and not x.elts for x in n.comparators)
                   for n in ast.walk(node))
    cancellation = feature.path.with_name("test_owned_sql_sdk_program_cancellation.py")
    assert hashlib.sha256(cancellation.read_bytes()).hexdigest() == (
        "764515ed9f913aa10165075fb4901a0ea23b9a7654fda7de9c363a12e19b72c0")


def test_sibling_failed_acquisition_preserves_original_error():
    from types import MethodType
    feature = _sibling_diag_feature()  # Mandatory APIs BEFORE expected refusal.
    owner = _timeout_diag_owner()
    owner.outcome = None
    owner.fail = MethodType(_SdkRetirement.fail, owner)
    events, errors = [], []
    owner.retain_driver = lambda task: events.append("retain")
    owner.request = lambda: events.append("request")
    controller = SimpleNamespace(owner_checkpoint=True)
    async def acceptance(**kwargs):
        assert len(owner.sibling_diagnostic_refs) == 18
        try:
            feature.ns["_SdkSiblingScoreFailure"].checkpoint_owner(controller, rows=[])
        except AssertionError as error:
            errors.append(error)
            raise
    feature.ns["_sdk_acceptance"] = acceptance
    # Registry remains original, captured before scheduling this UNIT receiver.
    original_refs = feature.refs
    feature.ns["_sdk_sibling_diagnostic_refs"] = lambda: original_refs
    async def scenario():
        try:
            await feature.ns["_run_sdk_host_case"](
                loop=asyncio.get_running_loop(), root=None, prepared=None,
                phase="sdk-sibling-score-failure", mutant="none", profile=None,
                executor=None, actor=SimpleNamespace(retirement=owner))
        except AssertionError as error:
            assert errors and error is errors[0] and owner.primary is error
            before = tuple(owner.errors)
            payload = feature.diagnostic(owner, original_refs)
            assert payload["primary_type"] == "AssertionError"
            assert payload["primary_origin"]["function"] == "_SdkSiblingScoreFailure.checkpoint_owner"
            assert owner.primary is error and owner.errors[0][1] is error
            assert len(owner.errors) == len(before) == 1
            assert _timeout_diag_leaf(error).tb_frame.f_code is (
                feature.ns["_SdkSiblingScoreFailure"].checkpoint_owner.__code__)
        else:
            raise AssertionError("UNIT genuine checkpoint refusal missing")
    asyncio.run(scenario())
    assert events == ["retain", "request"]


# Closed-resource correction: 54 UNIT cases, never native/actual-wait proof.
_SIBLING_CLEANUP_SITES = ("_sdk_sibling_completed", "_sdk_sibling_qualification")
_SIBLING_CLEANUP_VARIANTS = (
    "retained-closed", "unawaited-creator", "ambiguous-creator",
    "noninteger-returncode", "reap-pair-order", "reap-pid", "reap-returncode",
    "missing-slot", "substituted-slot-process", "missing-creator-registry-entry",
    "substituted-creator-registry-process", "open-endpoint", "open-stdin",
    "open-stdout", "open-stderr", "open-host-fd", "open-seal-fd",
    "retained-resource", "live-controller-thread", "extra-child",
)


def _sibling_cleanup_regions(source, tree):
    """Select whole ORIGINAL statements, refusing missing/ambiguous anchors."""
    regions = {}
    for site in _SIBLING_CLEANUP_SITES:
        function, = [node for node in tree.body if getattr(node, "name", None) == site]
        start, = [node for node in ast.walk(function)
                  if isinstance(node, ast.Assert)
                  and "actual._thread" in ast.get_source_segment(source, node)]
        body, = [node.body for node in ast.walk(function)
                 if isinstance(node, ast.For) and start in node.body]
        marker = ("job, = scorer.actual._jobs" if site == "_sdk_sibling_completed"
                  else "if scope is c.scope and not control:")
        stop, = [node for node in body
                 if ast.get_source_segment(source, node).startswith(marker)]
        selected = body[body.index(start):body.index(stop)]
        assert selected and selected[0] is start and selected[-1].end_lineno < stop.lineno
        regions[site] = SimpleNamespace(
            nodes=selected, first=start.lineno, last=stop.lineno - 1)
    assert set(regions) == set(_SIBLING_CLEANUP_SITES)
    return regions


@pytest.fixture(scope="module")
def _sibling_cleanup_trusted_source():
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    regions = _sibling_cleanup_regions(source, tree)
    return SimpleNamespace(path=path, source=source, tree=tree, regions=regions)


def _sibling_cleanup_predicate(site, trusted):
    # No AST mutation, assertion substitution, pass injection or helper fallback.
    original = trusted.regions[site].nodes
    return compile(ast.Module(body=original, type_ignores=[]), str(trusted.path), "exec")


def _sibling_cleanup_unit_case(*, not_started=False):
    # Declared metadata doubles ONLY. No process wait or ACK authority is simulated.
    child = SimpleNamespace(
        pid=771, returncode=0, _creator_waited=True, _creator_ambiguous=False,
        stdin=None, stdout=SimpleNamespace(closed=True), stderr=SimpleNamespace(closed=True))
    actual = SimpleNamespace(
        _thread=SimpleNamespace(is_alive=lambda: False), _children=[],
        _endpoints=[], _host_read=None, _seal_lock_fd=None, _resources=[])
    ack = SimpleNamespace(
        not_started=not_started, guardian_reaps=(), terminal_ack_sha256=None)
    slots, entries = [], []
    if not not_started:
        actual._children.append(child)
        actual._endpoints.append(SimpleNamespace(fd=None))
        ack.guardian_reaps = ((child.pid, child.returncode),)
        ack.terminal_ack_sha256 = "unit-metadata-not-native-proof"
        slots.append(dict(invocation=actual, process=child))
        entries.append(dict(process=child, registry=actual._children, kind="guardian"))
    actor = SimpleNamespace(slots=slots, trace=SimpleNamespace(fence=lambda: tuple(entries)))
    return SimpleNamespace(
        actual=actual, ack=ack, child=child, slots=slots, entries=entries,
        namespace=dict(actual=actual, ack=ack, close=SimpleNamespace(ack=ack),
                       b=SimpleNamespace(actor=actor)))


@pytest.mark.parametrize("site", _SIBLING_CLEANUP_SITES)
@pytest.mark.parametrize("variant", _SIBLING_CLEANUP_VARIANTS)
def test_sibling_retained_closed_resource_predicate(
        _sibling_cleanup_trusted_source, site, variant):
    code = _sibling_cleanup_predicate(site, _sibling_cleanup_trusted_source)
    case = _sibling_cleanup_unit_case()
    actual, child, ack = case.actual, case.child, case.ack
    if variant == "unawaited-creator":
        child._creator_waited = False
    elif variant == "ambiguous-creator":
        child._creator_ambiguous = True
    elif variant == "noninteger-returncode":
        child.returncode = False
    elif variant == "reap-pair-order":
        ack.guardian_reaps = ((child.returncode, child.pid),)
    elif variant == "reap-pid":
        ack.guardian_reaps = ((child.pid + 1, child.returncode),)
    elif variant == "reap-returncode":
        ack.guardian_reaps = ((child.pid, child.returncode + 1),)
    elif variant == "missing-slot":
        case.slots.clear()
    elif variant == "substituted-slot-process":
        case.slots[0]["process"] = SimpleNamespace(**vars(child))
    elif variant == "missing-creator-registry-entry":
        case.entries.clear()
    elif variant == "substituted-creator-registry-process":
        case.entries[0]["process"] = SimpleNamespace(**vars(child))
    elif variant == "open-endpoint":
        actual._endpoints[0].fd = 91
    elif variant in ("open-stdin", "open-stdout", "open-stderr"):
        setattr(child, variant.removeprefix("open-"), SimpleNamespace(closed=False))
    elif variant == "open-host-fd":
        actual._host_read = 92
    elif variant == "open-seal-fd":
        actual._seal_lock_fd = 93
    elif variant == "retained-resource":
        actual._resources.append(object())
    elif variant == "live-controller-thread":
        actual._thread.is_alive = lambda: True
    elif variant == "extra-child":
        actual._children.append(SimpleNamespace(**vars(child)))
    else:
        assert variant == "retained-closed"
    if variant == "retained-closed":
        exec(code, case.namespace)
    else:
        with pytest.raises(AssertionError):
            exec(code, case.namespace)


@pytest.mark.parametrize("site", _SIBLING_CLEANUP_SITES)
@pytest.mark.parametrize("variant", (
    "empty-provenance", "unexpected-child", "unexpected-endpoint",
    "unexpected-slot", "unexpected-reap",
))
def test_sibling_not_started_resource_predicate(
        _sibling_cleanup_trusted_source, site, variant):
    code = _sibling_cleanup_predicate(site, _sibling_cleanup_trusted_source)
    case = _sibling_cleanup_unit_case(not_started=True)
    if variant == "unexpected-child":
        case.actual._children.append(case.child)
    elif variant == "unexpected-endpoint":
        case.actual._endpoints.append(SimpleNamespace(fd=None))
    elif variant == "unexpected-slot":
        case.slots.append(dict(invocation=case.actual, process=case.child))
    elif variant == "unexpected-reap":
        case.ack.guardian_reaps = ((case.child.pid, case.child.returncode),)
    else:
        assert variant == "empty-provenance"
    if variant == "empty-provenance":
        exec(code, case.namespace)
    else:
        with pytest.raises(AssertionError):
            exec(code, case.namespace)


@pytest.mark.parametrize("order", ("execute-then-aclose", "aclose-then-execute"))
def test_sibling_original_predispatch_completion(tmp_path, monkeypatch, order):
    from ptc import sql_isolation as core
    from ptc import test_sql_owned_invocation as legacy
    legacy_case = legacy._case
    # Synthetic allocation and loop self-pipe precede ALL local denials.
    invocation, profile, request = legacy_case(tmp_path, "scorer")
    loop = asyncio.new_event_loop()
    bound = time.monotonic() + 3.0  # One absolute UNIT bound, not a renewed budget.
    guard = legacy.offline_only.__wrapped__(loop, monkeypatch)
    calls = next(guard)

    def denied(label):
        def reject(*args, **kwargs):
            calls.append(label)
            raise AssertionError("offline source/native attempt: " + label)
        return reject

    for name in ("build_execution_binding", "_read_owned", "_fresh_owned_binding"):
        monkeypatch.setattr(core, name, denied(name))
    for name in ("_spawn", "_controller"):
        monkeypatch.setattr(core.OwnedSqlInvocation, name, denied(name))
    monkeypatch.setattr(threading.Thread, "start", denied("Thread.start"))
    monkeypatch.setattr(legacy.socket, "socket", denied("socket.socket"))
    tasks = []
    try:
        before = invocation.snapshot()
        receipt = invocation.request_cancel("caller_cancelled")
        intent = receipt.intent
        assert receipt.status == "accepted" and intent is invocation._intent
        assert intent.reason == "caller_cancelled"
        assert intent.deadline_ns == intent.requested_ns + 12_000_000_000

        def finish(coroutine):
            task = loop.create_task(coroutine)
            tasks.append(task)
            remaining = bound - time.monotonic()
            assert remaining > 0
            _, pending = loop.run_until_complete(asyncio.wait((task,), timeout=remaining))
            assert not pending, "original predispatch completion exceeded absolute 3s UNIT bound"
            return task.result()

        if order == "execute-then-aclose":
            completion = finish(invocation.execute())
            ack = finish(invocation.aclose())
        else:
            ack = finish(invocation.aclose())
            completion = finish(invocation.execute())
        assert type(completion) is core.InvocationCompletion
        completion.__post_init__()  # Original completion, never revalidate issued ACK authority.
        assert ack is completion.cleanup_ack is invocation._authority.ack
        assert ack._authority.owner is invocation
        legacy._assert_not_started_ack(ack, before, intent)
        assert ack.cleanup_deadline_ns == intent.deadline_ns
        assert completion.outcome is None and completion.abort.kind == "cancelled"
        assert completion.abort.invocation_id == invocation.invocation_id
        assert completion.abort.role == "scorer"
        assert invocation.snapshot().intent is intent
        assert invocation.snapshot().state == "HOST_SEALED"
        assert not invocation._children and not invocation._endpoints and not invocation._resources
        assert invocation._host_read is invocation._seal_lock_fd is None
        assert not invocation.executor.state_dir.exists()
        assert not profile.shared_state_dir.exists()
        assert time.monotonic() < bound
    finally:
        pending = asyncio.all_tasks(loop)
        # No silent fixture cancellation or extended cleanup allowance.
        loop.close()
        try:
            next(guard)
        except StopIteration:
            pass
        else:
            raise AssertionError("offline guard did not finish")
        assert not pending, "original predispatch retained pending tasks"
        assert calls == [], "forbidden IO attempted, including swallowed failures"


def test_sibling_retained_cancel_endpoint_closes_real_fd():
    import errno
    import os
    from ptc import sql_isolation as core
    read_fd, write_fd = os.pipe()
    endpoint = None
    retained = []
    try:
        endpoint = core._CancelEndpoint(write_fd)
        retained.append(endpoint)
        os.fstat(write_fd)
        endpoint.close()
        assert retained == [endpoint] and retained[0] is endpoint
        assert endpoint.fd is None
        with pytest.raises(OSError) as caught:
            os.fstat(write_fd)
        assert caught.value.errno == errno.EBADF
    finally:
        if endpoint is None:
            os.close(write_fd)
        else:
            endpoint.close()
        os.close(read_fd)


def test_sibling_closed_resource_correction_source_contract(_sibling_cleanup_trusted_source):
    import hashlib
    trusted = _sibling_cleanup_trusted_source
    _history_source = _timeline_history_inputs()["canonical"].decode()
    _history_regions = _sibling_cleanup_regions(_history_source, ast.parse(_history_source))
    lines = _history_source.splitlines(keepends=True)
    for region in sorted(_history_regions.values(), key=lambda item: item.first, reverse=True):
        lines[region.first - 1:region.last] = ["RESOURCE_REGION\n"]
    assert hashlib.sha256("".join(lines).encode()).hexdigest() == (
        "43825844ddbb83867b8575e4aad49b25a898965d7d19e98c3c78e28f573680c5")
    prefix = _timeline_history_inputs()["retirement"][:400464]
    assert hashlib.sha256(prefix).hexdigest() == (
        "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d")
    for filename, digest in (
        ("test_owned_sql_sdk_lifecycle.py",
         "b2eb26d15f6d0bffa5e9f668efb60f792e1d01a219f6a332a6ac7a9e51952f65"),
        ("test_owned_sql_sdk_program_cancellation.py",
         "764515ed9f913aa10165075fb4901a0ea23b9a7654fda7de9c363a12e19b72c0"),
        ("sql_isolation.py",
         "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e"),
    ):
        assert hashlib.sha256(trusted.path.with_name(filename).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((trusted.path.parent.parent / "cotrain_owned_sql.py").read_bytes()).hexdigest() == (
        "035b7705aae0c02be00ddd49f59ba4128ede30659cf27262b816a32b06d54aad")
    for site in _SIBLING_CLEANUP_SITES:
        nodes = trusted.regions[site].nodes
        text = "\n".join(ast.get_source_segment(trusted.source, node) for node in nodes)
        assert "ack.guardian_reaps == tuple((child.pid, child.returncode)" in text
        assert 'slot["invocation"] is actual' in text
        assert 'slot["process"] is child' in text
        assert 'entry["process"] is child' in text
        assert 'entry["registry"] is actual._children' in text
        assert "child._creator_waited is True" in text
        assert "child._creator_ambiguous is False" in text
        assert "type(child.pid) is int and child.pid > 0" in text
        assert "type(child.returncode) is int" in text
        assert "if ack.not_started:" in text
        assert "not actual._children and not actual._endpoints" in text
        assert "not slots and not ack.guardian_reaps" in text
        assert "ack.terminal_ack_sha256 is None" in text
        assert "not actual._resources" in text
        assert "len(actual._children) == len(slots) == len(ack.guardian_reaps) == 1" in text
        assert ".__post_init__" not in text


@pytest.mark.parametrize("control", (False, True), ids=("baseline", "control"))
def test_sibling_qualification_compat_preserves_identities(_invalid_unit_api, control):
    adapter = globals().get("_sibling_unit_closed_qualification_inputs")
    assert callable(adapter), "UNIT_METADATA_COMPAT_ADAPTER_MISSING"
    feature = _sibling_unit_feature()
    original = _sibling_unit_qualification_inputs

    async def scenario(context):
        captured, calls = {}, []

        async def delegated(actual_context, actual_feature, *, control):
            calls.append((actual_context, actual_feature, control))
            case = await original(actual_context, actual_feature, control=control)
            bundle = case.bundle
            captured.update(
                case=case, owners=[row.actual for row in bundle.owners],
                acks=[row.ack for row in bundle.closes],
                public_tasks=[row.task for row in bundle.closes],
                completions=[row.actual._completion for row in bundle.owners],
                authorities=[row.actual._authority for row in bundle.owners],
                children=[row.actual._children for row in bundle.owners],
                endpoints=[row.actual._endpoints for row in bundle.owners],
                ledger=tuple(case.retirement.errors), primary=case.retirement.primary,
                slots=bundle.actor.slots)
            return case

        case = await adapter(delegated, context, feature, control=control)
        assert len(calls) == 1
        assert calls[0][0] is context and calls[0][1] is feature and calls[0][2] is control
        assert case is captured["case"] and case.bundle.actor.slots is captured["slots"]
        assert case.retirement.primary is captured["primary"]
        assert len(case.retirement.errors) == len(captured["ledger"])
        assert all(stage == before_stage and error is before_error
                   for (stage, error), (before_stage, before_error)
                   in zip(case.retirement.errors, captured["ledger"], strict=True))
        dispatched = 0
        for index, (owner, close) in enumerate(zip(
                case.bundle.owners, case.bundle.closes, strict=True)):
            actual, ack = owner.actual, close.ack
            assert actual is captured["owners"][index]
            assert actual._completion is captured["completions"][index]
            assert actual._authority is captured["authorities"][index]
            assert actual._children is captured["children"][index]
            assert actual._endpoints is captured["endpoints"][index]
            assert ack is captured["acks"][index] is close.task.result()
            assert close.task is captured["public_tasks"][index]
            assert ack is actual._completion.cleanup_ack is actual._authority.ack
            assert type(ack) is _SiblingUnitPublicReturn  # Still inert, never a real ACK.
            assert ack.released is True
            slots = [slot for slot in case.bundle.actor.slots if slot["invocation"] is actual]
            assert not actual._resources and actual._host_read is actual._seal_lock_fd is None
            if ack.not_started:
                assert not control and actual is case.target.owner
                assert not actual._children and not actual._endpoints and not slots
                assert ack.guardian_reaps == () and ack.terminal_ack_sha256 is None
            else:
                dispatched += 1
                child, = actual._children
                slot, = slots
                entry, = [entry for entry in case.bundle.actor.trace.fence()
                          if entry["process"] is child]
                assert slot["process"] is child
                assert entry["registry"] is actual._children and entry["kind"] == "guardian"
                assert ack.guardian_reaps == ((child.pid, child.returncode),)
                assert all(endpoint.fd is None for endpoint in actual._endpoints)
        assert dispatched == len(case.bundle.actor.slots) == (7 if control else 6)
        assert feature.namespace["_sdk_sibling_qualification"](
            case.retirement, case.physical)["verified"] is True

    _sibling_unit_run(_invalid_unit_api, feature, scenario)


def test_sibling_qualification_compat_scope_contract():
    fixture = globals().get("_sibling_qualification_closed_metadata_compat")
    assert fixture is not None, "UNIT_METADATA_COMPAT_ADAPTER_MISSING"
    original = _sibling_unit_qualification_inputs
    with pytest.MonkeyPatch.context() as patch:
        fixture.__wrapped__(SimpleNamespace(function=object()), patch)
        assert _sibling_unit_qualification_inputs is original
        fixture.__wrapped__(
            SimpleNamespace(function=test_sibling_postretirement_qualification), patch)
        assert _sibling_unit_qualification_inputs is not original
    assert _sibling_unit_qualification_inputs is original
    tree = ast.parse(Path(__file__).read_text())
    assert not any(isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "_sibling_unit_qualification_inputs"
        for target in node.targets) for node in tree.body)


async def _sibling_unit_closed_qualification_inputs(original, context, feature, *, control):
    """Enrich declared UNIT doubles only, never synthesize actual ownership proof."""
    case = await original(context, feature, control=control)
    bundle = case.bundle
    assert type(bundle.actor.trace) is SimpleNamespace  # Not a real CreatorTrace.
    slots, entries = [], []
    for index, owner in enumerate(bundle.owners):
        actual = owner.actual
        close, = [row for row in bundle.closes if row.actual is actual]
        ack = close.ack
        assert type(ack) is _SiblingUnitPublicReturn  # Never CleanupCompleteAck.
        assert ack is close.task.result() is actual._completion.cleanup_ack is actual._authority.ack
        assert not actual._children and not actual._endpoints
        assert not getattr(actual, "_resources", ())
        assert getattr(actual, "_host_read", None) is None
        assert getattr(actual, "_seal_lock_fd", None) is None
        actual._resources = []
        actual._host_read = actual._seal_lock_fd = None
        ack.guardian_reaps = ()
        ack.terminal_ack_sha256 = None
        ack.child_waits = ack.thread_joins = not ack.not_started
        ack.released = True
        if ack.not_started:
            assert actual is case.target.owner and not control
            continue
        child = SimpleNamespace(
            unit_only=True, pid=10000 + index, returncode=0,
            _creator_waited=True, _creator_ambiguous=False,
            stdin=None, stdout=None, stderr=None)
        actual._children.append(child)
        actual._endpoints.append(SimpleNamespace(unit_only=True, fd=None))
        ack.guardian_reaps = ((child.pid, child.returncode),)
        ack.terminal_ack_sha256 = "UNIT_ONLY_NOT_A_TERMINAL_ACK"
        slots.append(dict(invocation=actual, process=child))
        entries.append(dict(process=child, registry=actual._children, kind="guardian"))
    assert len(slots) == len(bundle.actor.slots) == (7 if control else 6)
    bundle.actor.slots[:] = slots  # Preserve the original UNIT list identity/count.
    bundle.actor.trace.fence = lambda: tuple(entries)
    return case


@pytest.fixture(autouse=True)
def _sibling_qualification_closed_metadata_compat(request, monkeypatch):
    """Scoped metadata upgrade for the ten unchanged legacy UNIT cases only."""
    if request.function is not test_sibling_postretirement_qualification:
        return
    original = _sibling_unit_qualification_inputs

    async def adapted(context, feature, *, control):
        return await _sibling_unit_closed_qualification_inputs(
            original, context, feature, control=control)

    monkeypatch.setitem(globals(), "_sibling_unit_qualification_inputs", adapted)


# Traceback-state amendment: exactly 12 metadata UNIT cases, not actor evidence.
@pytest.fixture(scope="module")
def _sibling_traceback_metadata_feature():
    return _sibling_diag_feature()  # Reuse original extraction, no AST rewriting.


@pytest.mark.parametrize("state", (
    "UNINSPECTED_TYPE", "NO_TRACEBACK", "LIMIT_EXCEEDED",
    "UNREGISTERED_LEAF", "UNRESOLVED_SITE", "RESOLVED",
))
def test_sibling_diagnostic_traceback_state(_sibling_traceback_metadata_feature, state):
    from types import TracebackType
    feature = _sibling_traceback_metadata_feature
    calls = []
    expected_origin = "OTHER"
    if state == "UNINSPECTED_TYPE":
        class Uninspected(AssertionError):
            def __getattribute__(self, name):
                calls.append(name)
                raise AssertionError("UNIT_PRIVATE_CANARY")
        error = Uninspected("UNIT_PRIVATE_CANARY")
    elif state == "UNREGISTERED_LEAF":
        error = _timeout_diag_caught(lambda: getattr(None, "UNIT_PRIVATE_CANARY"))
        assert type(error) is AttributeError
    else:
        error = _sibling_diag_error(feature)
        leaf = _timeout_diag_leaf(error)
        if state == "NO_TRACEBACK":
            # Current None cannot distinguish never raised from explicitly cleared.
            error.__traceback__ = None
        elif state == "LIMIT_EXCEEDED":
            tb = None
            for _ in range(33):
                tb = TracebackType(tb, leaf.tb_frame, leaf.tb_lasti, leaf.tb_lineno)
            error.__traceback__ = tb  # Synthetic UNIT links, not observed actor evidence.
        elif state == "UNRESOLVED_SITE":
            method = _sibling_unit_nodes(
                feature.path, owner="_SdkSiblingScoreFailure", name="checkpoint_owner")
            statement, = [node for node in method.body if isinstance(node, ast.Assign)
                           and isinstance(node.targets[0], ast.Attribute)]
            error.__traceback__ = TracebackType(
                None, leaf.tb_frame, leaf.tb_lasti, statement.end_lineno + 1)
        else:
            assert state == "RESOLVED"
            expected_origin = dict(
                file=feature.path.name, function="_SdkSiblingScoreFailure.checkpoint_owner",
                line=leaf.tb_lineno, site="assert", leaf="function")
    payload = _sibling_diag_receipt(feature, error, [("task", error)])
    entry, = payload["entries"]
    assert entry["traceback_state"] == state
    assert entry["origin"] == payload["primary_origin"] == expected_origin
    assert entry["error_token"] == payload["primary_token"] == 1
    assert entry["is_primary"] is True and calls == []


@pytest.mark.parametrize("stage", ("task-role", "late-driver", "UNIT_UNDECLARED_STAGE"))
def test_sibling_diagnostic_role_stage_labels(_sibling_traceback_metadata_feature, stage):
    feature = _sibling_traceback_metadata_feature
    error = AssertionError("UNIT_PRIVATE_CANARY")
    payload = _sibling_diag_receipt(feature, error, [(stage, error)])
    entry, = payload["entries"]
    assert entry["stage"] == (stage if stage != "UNIT_UNDECLARED_STAGE" else "OTHER")


@pytest.mark.parametrize("path", ("role-conflict", "late-driver"))
def test_sibling_diagnostic_original_role_failure_metadata(
        _sibling_traceback_metadata_feature, path):
    from types import MethodType
    feature = _sibling_traceback_metadata_feature
    end = time.monotonic() + 3.0  # Existing absolute UNIT bound, never renewed.
    owner = _timeout_diag_owner()
    owner.tasks, owner.task_roles, owner.role_conflicts = set(), {}, set()
    owner.requested = threading.Event()
    owner.outcome = None
    owner.fail = MethodType(_SdkRetirement.fail, owner)
    owner._cancel_drivers = MethodType(_SdkRetirement._cancel_drivers, owner)
    scheduled = []
    owner.loop = SimpleNamespace(
        call_soon_threadsafe=lambda callback: scheduled.append(callback))
    task = object()  # Opaque UNIT identity, no real driver or cancel operation.
    if path == "role-conflict":
        owner.task_roles[task] = ("cleanup", "owner-close")
        expected_stage = "task-role"
    else:
        owner.requested.set()
        expected_stage = "late-driver"
    assert _SdkRetirement._retain_role(owner, task, "driver") is task
    assert len(owner.errors) == 1
    stage, error = owner.errors[0]
    assert stage == expected_stage and type(error) is AssertionError
    assert error is owner.primary and error.__traceback__ is None
    assert task in owner.tasks
    if path == "role-conflict":
        assert task in owner.role_conflicts and scheduled == []
        assert owner.task_roles[task] == ("cleanup", "owner-close")
    else:
        callback, = scheduled  # Observe ORIGINAL scheduling, never invoke cancellation.
        assert callback.__self__ is owner
        assert callback.__func__ is _SdkRetirement._cancel_drivers
        assert owner.task_roles[task] == ("driver", None)
    before, outcome = tuple(owner.errors), owner.outcome
    payload = feature.diagnostic(owner, feature.refs)
    assert owner.primary is error and owner.outcome is outcome
    assert len(owner.errors) == len(before)
    assert all(row[0] is original[0] and row[1] is original[1]
               for row, original in zip(owner.errors, before, strict=True))
    entry, = payload["entries"]
    assert entry["traceback_state"] == "NO_TRACEBACK"
    assert entry["stage"] == expected_stage
    assert entry["origin"] == payload["primary_origin"] == "OTHER"
    assert entry["is_primary"] is True
    assert time.monotonic() < end


def test_sibling_diagnostic_metadata_bounds_and_contract(_sibling_traceback_metadata_feature):
    import hashlib
    feature = _sibling_traceback_metadata_feature
    primary = AssertionError("UNIT_PRIVATE_CANARY")
    errors = [("task", AssertionError("UNIT_PRIVATE_CANARY")) for _ in range(20)]
    payload = _sibling_diag_receipt(feature, primary, errors)
    assert len(payload["entries"]) == 16 and payload["ledger_omitted"] == 4
    assert payload["primary_seen_in_sample"] is False
    assert {payload["primary_token"], *(row["error_token"] for row in payload["entries"])} == set(
        range(1, 18))
    for entry in payload["entries"]:
        assert set(entry) == {
            "ledger_index", "error_token", "is_primary", "stage", "type", "origin",
            "traceback_state"}
        assert entry["traceback_state"] == "NO_TRACEBACK" and entry["origin"] == "OTHER"
    original = _sibling_diag_error(feature)
    other = AssertionError(*original.args)
    reused = _sibling_diag_receipt(
        feature, original, [("task", original), ("task", other), ("host", original)])
    assert [row["error_token"] for row in reused["entries"]] == [1, 2, 1]
    assert reused["entries"][0]["origin"] is reused["entries"][2]["origin"]
    typed = _sibling_diag_receipt(feature, None, [
        ("task", kind("UNIT_PRIVATE_CANARY")) for kind in (
            AssertionError, AttributeError, RuntimeError, TypeError, ValueError, TimeoutError,
            KeyError)])
    assert [row["type"] for row in typed["entries"]] == [
        "AssertionError", "AttributeError", "RuntimeError", "TypeError", "ValueError",
        "TimeoutError", "OTHER"]
    assert [row["traceback_state"] for row in typed["entries"]] == (
        ["NO_TRACEBACK"] * 6 + ["UNINSPECTED_TYPE"])
    for result in (payload, reused, typed):
        raw = json.dumps(dict(kind="SDK_SIBLING_FINAL_LEDGER", diagnostic=result)).encode()
        assert len(raw) <= 8192 and b"UNIT_PRIVATE_CANARY" not in raw
    assert tuple(label for label, _ in feature.refs) == _SIBLING_DIAG_ROOTS
    assert len(feature.refs) == 18
    for name, digest in (
        ("_SdkRetirement", "800f4483b28823ccf418a995b7e6656983f4e5a29b5adda7550f561b9edf355b"),
        ("_sdk_timeout_error_diagnostic",
         "9258bcf8f0b6c72b9d22c0bd979ff7d070453e9af46662a953fd91fafe8c1565"),
        ("_sdk_sibling_diagnostic_refs",
         "10e8cd650907e48b7c4054ba8ee109871ff3f88ecefb37ee1627a99f408012f8"),
    ):
        node, = [node for node in feature.tree.body if getattr(node, "name", None) == name]
        assert hashlib.sha256(ast.get_source_segment(feature.source, node).encode()).hexdigest() == digest
    diagnostic, = [node for node in feature.tree.body
                   if getattr(node, "name", None) == "_sdk_sibling_error_diagnostic"]
    text = ast.get_source_segment(feature.source, diagnostic)
    for original_bound in ("retirement.errors[:16]", "range(32)", "len(registered) >= 256",
                           "len(wire) > 8192"):
        assert original_bound in text
    _history_source = _timeline_history_inputs()["canonical"].decode()
    _history_tree = ast.parse(_history_source)
    _history_diagnostic, = [node for node in _history_tree.body
                            if getattr(node, "name", None) == "_sdk_sibling_error_diagnostic"]
    lines = _history_source.splitlines(keepends=True)
    lines[_history_diagnostic.lineno - 1:_history_diagnostic.end_lineno] = ["DIAGNOSTIC_FUNCTION\n"]
    assert hashlib.sha256("".join(lines).encode()).hexdigest() == (
        "e1a6d53e64436dac2b8ce0c4a850a978a3356c12448de5128819c5d217feb738")


# Creator-boundary metadata UNIT cases. No SDK, actor, native or process work.
def _creator_boundary_unit_feature():
    import sys
    import types
    tree = _compat_guest_tree()
    nodes = [node for node in tree.body
             if getattr(node, "name", None) in (
                 "_CreatorBoundaryDiagnostic", "_creator_boundary_refs")]
    assert len(nodes) == 2, "CREATOR_BOUNDARY_HELPERS_MISSING"
    namespace = dict(ast=ast, asyncio=asyncio, types=types, json=json,
                     threading=threading, sys=sys, time=time, Path=Path)
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 "CREATOR_BOUNDARY_UNIT_ONLY", "exec"), namespace)
    return SimpleNamespace(tree=tree, **namespace)


def _creator_boundary_unit_owner(**changes):
    fields = dict(_state="ALLOCATED", _completion=None, _intent=None,
                  _endpoints=[], _children=[], _thread=None)
    fields.update(changes)
    return SimpleNamespace(**fields)


def _creator_boundary_unit_retirement(tasks=()):
    return SimpleNamespace(
        lock=threading.Lock(), tasks=set(tasks), stop_tasks=set(), internal_tasks=set(),
        task_roles={}, requested=threading.Event(), async_started=asyncio.Event(),
        async_done=threading.Event(), fallback_requested=threading.Event(),
        complete=threading.Event(), finalized=False, primary=AssertionError("UNIT_SECRET"),
        errors=[], outcome=dict(ok=False, SAFE=False))


def _creator_boundary_unit_observer(feature, *, refs=(), active=None, frames=None,
                                    write=None, clock=None):
    writes = []
    observer = feature._CreatorBoundaryDiagnostic(
        refs=refs, original_thread=threading.Thread,
        active={} if active is None else active,
        current_frames=(lambda: {}) if frames is None else frames,
        write=(lambda fd, raw: writes.append((fd, raw)) or len(raw))
        if write is None else write,
        clock=(lambda: 123) if clock is None else clock)
    return observer, writes


def _creator_boundary_unit_report(observer, retirement=None, owners=(), slots=(), trace=None,
                                  site=1):
    return observer.prepare(
        site, retirement or _creator_boundary_unit_retirement(), owners, slots,
        trace or SimpleNamespace(lock=threading.Lock(), entries=[]))


def _creator_boundary_unit_frames(depth):
    import sys
    # Real inert Python frames, not custom frame/Task/coroutine attribute hooks.
    def descend(left):
        if left:
            return descend(left - 1)
        return sys._getframe()
    return descend(depth)


def test_creator_boundary_pending_first():
    feature = _creator_boundary_unit_feature()
    loop = asyncio.new_event_loop()
    async def inert():
        return None
    completed = [loop.create_task(inert()) for _ in range(93)]
    loop.run_until_complete(asyncio.gather(*completed))
    pending = [loop.create_task(inert()) for _ in range(8)]
    retirement = _creator_boundary_unit_retirement([*completed, *pending])
    retirement._snapshot_tasks = lambda: None  # Inert retained-task inventory only.
    for task in pending:
        retirement.task_roles[task] = ("cleanup", "owner-close")
    before = (set(retirement.tasks), dict(retirement.task_roles))
    observer, _ = _creator_boundary_unit_observer(feature)
    try:
        report = _creator_boundary_unit_report(observer, retirement)
        assert report["inspected"][1] == 101 and report["omitted"][1] == 69
        assert len(report["tasks"]) == 32
        assert sum(not row[3] & 1 for row in report["tasks"]) == 8
        assert all(row[1:4] == [3, 2, 0] for row in report["tasks"][:8])
        assert retirement.tasks == before[0] and retirement.task_roles == before[1]
        assert len(_SdkRetirement.diagnostic(retirement)["tasks"]) == 32
    finally:
        loop.run_until_complete(asyncio.gather(*pending))
        loop.close()


def test_creator_boundary_owner_association():
    feature = _creator_boundary_unit_feature()
    class NoEquality(SimpleNamespace):
        def __eq__(self, other):
            raise AssertionError("IDENTITY_ONLY")
    owners = [NoEquality(**vars(_creator_boundary_unit_owner(_completion=object())))
              for _ in range(8)]
    ninth = NoEquality(**vars(_creator_boundary_unit_owner()))
    owners.append(ninth)
    process, foreign_process = object(), object()
    slots = [dict(invocation=ninth, process=process),
             dict(invocation=NoEquality(**vars(ninth)), process=foreign_process)]
    entries = [dict(registry=ninth._children, process=process),
               dict(registry=[], process=foreign_process)]
    observer, _ = _creator_boundary_unit_observer(feature)
    report = _creator_boundary_unit_report(
        observer, owners=owners, slots=slots,
        trace=SimpleNamespace(lock=threading.Lock(), entries=entries))
    assert report["owners"][0][:7] == [9, 1, 0, 0, 0, 1, 1]
    again = _creator_boundary_unit_report(observer, owners=owners)
    assert [row[0] for row in again["owners"]] == [9, 1, 2, 3, 4, 5, 6, 7]
    # Stale/reused/disappearing identities must not even touch a candidate frame.
    class ForeignFrame:
        def __getattribute__(self, key):
            raise AssertionError("FOREIGN_FRAME_INSPECTED")
    thread = threading.Thread()
    thread._ident = 123456  # Inert original Thread, never started.
    ninth._thread = thread
    for membership in ({}, {thread.ident: threading.Thread()}):
        observer, _ = _creator_boundary_unit_observer(
            feature, active=membership, frames=lambda: {thread.ident: ForeignFrame()})
        row = _creator_boundary_unit_report(observer, owners=[ninth])["owners"][0]
        assert row[8] == 0 and row[9] & 8
    active = {thread.ident: thread}
    def disappearing():
        active.clear()
        return {thread.ident: ForeignFrame()}
    observer, _ = _creator_boundary_unit_observer(feature, active=active, frames=disappearing)
    assert _creator_boundary_unit_report(observer, owners=[ninth])["owners"][0][9] & 8
    active = {thread.ident: thread}
    def changed_ident():
        thread._ident += 1
        return {123456: ForeignFrame()}
    observer, _ = _creator_boundary_unit_observer(feature, active=active, frames=changed_ident)
    assert _creator_boundary_unit_report(observer, owners=[ninth])["owners"][0][9] & 8
    class CustomThread(threading.Thread):
        pass
    ninth._thread = CustomThread()
    observer, _ = _creator_boundary_unit_observer(feature)
    assert _creator_boundary_unit_report(observer, owners=[ninth])["owners"][0][9] & 8


def test_creator_boundary_original_code_and_ast():
    feature = _creator_boundary_unit_feature()
    import types
    source = "def trusted():\n    return 1\n"
    namespace = {}
    exec(compile(source, "UNIT_TRUSTED_FIXED_SOURCE", "exec"), namespace)
    code = namespace["trusted"].__code__
    tree = ast.parse(source)
    roots = [(index, code, tree, ("trusted",)) for index in range(1, 8)]
    refs = feature._creator_boundary_refs(roots)
    observer, _ = _creator_boundary_unit_observer(feature, refs=refs)
    for index in range(1, 8):
        single = feature._creator_boundary_refs([(index, code, tree, ("trusted",))])
        probe, _ = _creator_boundary_unit_observer(feature, refs=single)
        assert probe.location(code, 2, True) == [index, 2, 1]
        copied = code.replace()
        assert copied == code and copied is not code
        assert probe.location(copied, 2, True) == [0, 0, 0]
        assert probe.location((lambda: None).__code__, 2, False) == [0, 0, 3]
        assert probe.location(code, 2000000000, True) == [0, 0, 0]
    ambiguous = ast.parse(source + source)
    assert feature._creator_boundary_refs([(1, code, ambiguous, ("trusted",))]) == ()
    assert feature._creator_boundary_refs([(1, code, tree, ("missing",))]) == ()
    # Duplicate statement coordinates cannot be promoted to recognized sites.
    duplicate = ast.parse("def trusted():\n    first = 1; return first\n")
    refs = feature._creator_boundary_refs([(1, code, duplicate, ("trusted",))])
    probe, _ = _creator_boundary_unit_observer(feature, refs=refs)
    assert probe.location(code, 2, True) == [0, 0, 0]
    assert isinstance(code, types.CodeType)
    # Compile the exact seven fixed source roots, without executing any module.
    paths = (
        ("sql_isolation.py", ("OwnedSqlInvocation", "_controller")),
        ("sql_isolation.py", ("OwnedSqlInvocation", "_register_pipe")),
        ("sql_isolation.py", ("OwnedSqlInvocation", "_wait_startup")),
        ("sql_isolation.py", ("_CreatorPopen", "__init__")),
        (None, ("host_main", "spawn")),
        (None, ("CreatorTrace", "__init__", "constructor")),
        ("test_owned_sql_sdk_canonical.py", ("_sdk_acceptance", "observed_close")),
    )
    roots = []
    for label, (name, path) in enumerate(paths, 1):
        trusted = feature.tree if name is None else ast.parse(
            Path(__file__).with_name(name).read_bytes())
        original = compile(trusted, "UNIT_FIXED_TRUSTED_SOURCE", "exec")
        for component in path:
            original, = [constant for constant in original.co_consts
                         if type(constant) is types.CodeType and constant.co_name == component]
        roots.append((label, original, trusted, path))
    refs = feature._creator_boundary_refs(roots)
    assert len(refs) == 7 and [label for label, _, _ in refs] == list(range(1, 8))
    observer, _ = _creator_boundary_unit_observer(feature, refs=refs)
    for label, original, coordinates in refs:
        assert coordinates
        line = min(coordinates)
        assert observer.location(original, line, True) == [label, line, 1]
        assert observer.location(original.replace(), line, True) == [0, 0, 0]
    outer = ast.parse(Path(__file__).with_name("test_sql_lifecycle_process.py").read_bytes())
    outer_host = next(node for node in outer.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                              for target in node.targets))
    guest_spawn = roots[4][1]
    assert guest_spawn.co_firstlineno != outer_host.lineno + guest_spawn.co_firstlineno


def test_creator_boundary_traversal_limits():
    feature = _creator_boundary_unit_feature()
    frame = _creator_boundary_unit_frames(12)
    calls = []
    threads = [threading.Thread() for _ in range(8)]
    for index, thread in enumerate(threads):
        thread._ident = index + 1
    active = {thread.ident: thread for thread in threads}
    observer, _ = _creator_boundary_unit_observer(
        feature, active=active,
        frames=lambda: calls.append(1) or {thread.ident: frame for thread in threads})
    owners = [_creator_boundary_unit_owner(_thread=thread) for thread in threads]
    report = _creator_boundary_unit_report(observer, owners=owners)
    assert calls == [1] and len(report["locations"]) == 64
    assert all(row[8] == 8 and row[9] & 2 for row in report["owners"])
    assert [row[7] for row in report["owners"]] == list(range(0, 64, 8))
    assert all(row[9] & 16 for row in report["owners"])  # Foreign leaf remains unknown.
    # Forty live streams all receive their first opportunity before any seconds.
    loop = asyncio.new_event_loop()
    async def parked():
        await asyncio.sleep(0)
    tasks = [loop.create_task(parked()) for _ in range(32)]
    try:
        report = _creator_boundary_unit_report(
            observer, _creator_boundary_unit_retirement(tasks), owners)
        assert len(report["locations"]) == 64
        assert all(row[5] >= 1 for row in report["tasks"])
        assert all(row[8] >= 1 for row in report["owners"])
        assert any(row[9] & 4 for row in report["owners"])
    finally:
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
    absent, _ = _creator_boundary_unit_observer(feature, active=active)
    row = _creator_boundary_unit_report(absent, owners=owners)["owners"][0]
    assert row[9] & 1 and not row[9] & 8 and row[2] == 0
    # A recognized caller below a foreign leaf cannot turn that leaf into origin.
    shallow = _creator_boundary_unit_frames(0)
    refs = feature._creator_boundary_refs([(
        5, _creator_boundary_unit_frames.__code__, ast.parse(Path(__file__).read_bytes()),
        ("_creator_boundary_unit_frames",))])
    known, _ = _creator_boundary_unit_observer(
        feature, refs=refs, active=active,
        frames=lambda: {thread.ident: shallow for thread in threads})
    report = _creator_boundary_unit_report(known, owners=owners)
    row = report["owners"][0]
    locations = report["locations"][row[7]:row[7] + row[8]]
    assert locations[0] == [0, 0, 0] and locations[1][::2] == [5, 2]
    assert row[9] & 16
    # Review control: an exact closed inner coroutine still retained by a
    # suspended exact outer must not promote the surviving outer to leaf.
    async def review_inner():
        await asyncio.sleep(0)
    async def review_outer(awaited):
        await awaited
    refs = feature._creator_boundary_refs([(
        5, review_outer.__code__, ast.parse(Path(__file__).read_bytes()),
        ("test_creator_boundary_traversal_limits", "review_outer"))])
    known, _ = _creator_boundary_unit_observer(feature, refs=refs)
    for depth in (8, 9):
        chain = [review_inner()]
        for _ in range(depth - 1):
            chain.append(review_outer(chain[-1]))
        try:
            assert chain[-1].send(None) is None
            assert all(type(actual) is feature.types.CoroutineType for actual in chain)
            assert chain[1].cr_await is chain[0]
            chain[0].close()
            assert chain[0].cr_frame is None and chain[-1].cr_frame is not None
            stream = dict(flags=0, exhausted=False)
            locations = list(known.coroutine(chain[-1], stream))
            assert locations[0] == [0, 0, 0], "MISSING_COROUTINE_LEAF_PROMOTED_CALLER"
            assert 1 < len(locations) <= 8
            assert all(row[0] == 5 and row[2] == 2 for row in locations[1:])
            assert not any(row[2] == 1 for row in locations)
            assert stream["flags"] & 16
            if depth == 8:
                assert stream["flags"] & 8  # The closed leaf was actually inspected.
            else:
                assert stream["flags"] & 2
        finally:
            for actual in reversed(chain):
                actual.close()


def test_creator_boundary_busy_locks_do_not_wait():
    feature = _creator_boundary_unit_feature()
    calls = []
    class Busy:
        def acquire(self, blocking):
            assert blocking is False
            calls.append("try")
            return False
        def release(self):
            raise AssertionError("UNOWNED_RELEASE")
    class Forbidden:
        def __getattribute__(self, name):
            raise AssertionError("OWNER_SPAWN_PROCESS_OPERATION")
    retirement = _creator_boundary_unit_retirement()
    retirement.lock = Busy()
    owner = _creator_boundary_unit_owner()
    owner._lock = owner._spawn_lock = Forbidden()
    owner._children = [Forbidden()]
    trace = SimpleNamespace(lock=Busy(), entries=Forbidden())
    observer, _ = _creator_boundary_unit_observer(feature)
    start = time.monotonic()
    report = _creator_boundary_unit_report(observer, retirement, [owner], trace=trace)
    assert time.monotonic() - start < 0.1
    assert calls == ["try", "try"] and report["flags"] & 6 == 6
    assert report["unavailable"][1] == 1 and report["unavailable"][3] == 1
    assert report["owners"][0][4] == 1


def test_creator_boundary_privacy_and_caps():
    feature = _creator_boundary_unit_feature()
    loop = asyncio.new_event_loop()
    async def inert():
        return "UNIT_SECRET"
    tasks = [loop.create_task(inert()) for _ in range(270)]
    owners = [_creator_boundary_unit_owner() for _ in range(70)]
    slots = [dict(invocation=owners[-1], UNIT_SECRET="private/path") for _ in range(270)]
    trace = SimpleNamespace(lock=threading.Lock(), entries=[
        dict(registry=[], UNIT_SECRET="secret") for _ in range(270)])
    observer, writes = _creator_boundary_unit_observer(feature, clock=lambda: 2**80)
    def custom_override():
        raise AssertionError("CUSTOM_TASK_OVERRIDE")
    for task in tasks:
        task.done = task.cancelled = task.get_coro = custom_override
    try:
        retirement = _creator_boundary_unit_retirement(tasks)
        report = _creator_boundary_unit_report(observer, retirement, owners, slots, trace)
        assert report["inspected"] == [64, 256, 256, 256]
        assert report["omitted"] == [62, 238, 14, 14]
        assert report["timestamp"] == 2**63 - 1 and report["flags"] & 16
        assert len(report["owners"]) == 8 and len(report["tasks"]) == 32
        for site in (1, 1, 2, 2, 0, 3):
            observer.emit(site, retirement, owners, slots, trace)
        assert len(writes) == 2 and all(fd == 2 for fd, _ in writes)
        assert all(len(raw) <= 6400 and b"UNIT_SECRET" not in raw
                   and b"private/path" not in raw for _, raw in writes)
        # Independent maximal integer-width schema construction, no field dropping.
        maximum = 2147483647
        worst = dict(report, owners=[[maximum]*10 for _ in range(8)],
                     tasks=[[maximum]*7 for _ in range(32)],
                     locations=[[maximum]*3 for _ in range(64)])
        wire = json.dumps(worst, separators=(",", ":")).encode() + b"\n"
        assert len(wire) <= 6400 < 8192
        assert all(len(row) == 10 for row in report["owners"])
        assert all(len(row) == 7 for row in report["tasks"])
    finally:
        for task in tasks:
            del task.done, task.cancelled, task.get_coro
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()


def test_creator_boundary_failure_preservation():
    feature = _creator_boundary_unit_feature()
    retirement = _creator_boundary_unit_retirement()
    original = retirement.primary
    retirement.errors[:] = [("host", original)]
    outcome, errors = retirement.outcome, list(retirement.errors)
    for mode in ("prepare", "write", "short"):
        attempts = []
        def write(fd, raw):
            attempts.append((fd, raw))
            if mode == "write":
                raise OSError("UNIT_SECRET")
            return 0
        observer, _ = _creator_boundary_unit_observer(feature, write=write)
        if mode == "prepare":
            def broken(*args):
                raise original
            observer.prepare = broken
        try:
            raise original
        except BaseException as caught:
            observer.emit(1, retirement, [], [], SimpleNamespace())
            observer.emit(1, retirement, [], [], SimpleNamespace())
            assert caught is original is retirement.primary
        assert len(attempts) == (0 if mode == "prepare" else 1)
        assert retirement.outcome is outcome and retirement.outcome["SAFE"] is False
        assert retirement.errors == errors and retirement.errors[0][1] is original
        assert retirement.finalized is False
    callback, = [node for node in ast.walk(feature.tree) if isinstance(node, ast.FunctionDef)
                 and node.name == "sdk_diagnostic"]
    for mode in ("write", "short"):
        order = []
        def original_write(fd, raw):
            order.append("original")
            if mode == "write":
                raise original
            return 0
        def boundary(*args):
            order.append("boundary")
            raise original
        namespace = dict(
            json=json, os=SimpleNamespace(write=original_write),
            creator_boundary=SimpleNamespace(emit=boundary),
            sdk_resources=retirement, owners=[], slots=[], trace=SimpleNamespace())
        exec(compile(ast.Module(body=[callback], type_ignores=[]),
                     "CREATOR_BOUNDARY_ORIGINAL_CALLBACK_UNIT", "exec"), namespace)
        namespace["sdk_diagnostic"]("SDK_RETIREMENT_REFUSAL", {})
        assert order == ["original", "boundary"]
        assert retirement.primary is original and retirement.outcome is outcome
        assert retirement.errors == errors and retirement.finalized is False
    # Review controls: original metadata acquisition must fail closed, without
    # escaping into host startup or attempting a later post-replacement capture.
    import builtins
    capture, = [node for node in feature.tree.body if isinstance(node, ast.If)
                and any(isinstance(child, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "_boundary_original_core"
                    for target in child.targets) for child in ast.walk(node))]
    readiness = [node for node in feature.tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name)
                         and target.id == "_boundary_original_ready"
                         for target in node.targets)]
    host, = [node for node in feature.tree.body if getattr(node, "name", None) == "host_main"]
    configuration, = [node for node in host.body if isinstance(node, ast.If)
                      and any(isinstance(child, ast.Assign) and any(
                          isinstance(target, ast.Name) and target.id == "_boundary_roots"
                          for target in child.targets) for child in ast.walk(node))]
    results = []
    for dependency in ("_active", "_current_frames", "__code__"):
        reads, late = [], []
        injected = RuntimeError("UNIT_CAPTURE_PREPARATION_FAILURE")
        class FailingDependency(SimpleNamespace):
            def __getattribute__(self, name):
                if name == dependency:
                    reads.append(name)
                    raise injected
                return super().__getattribute__(name)
        def inert_code():
            return None
        functions = SimpleNamespace(
            _controller=FailingDependency() if dependency == "__code__" else inert_code,
            _register_pipe=inert_code, _wait_startup=inert_code)
        namespace = dict(
            MODE="host", PHASE="sdk-UNIT", creator_boundary=None, sdk_resources=retirement,
            threading=FailingDependency(Thread=threading.Thread, _active={}),
            sys=FailingDependency(_current_frames=lambda: {}),
            os=SimpleNamespace(write=lambda fd, raw: len(raw)),
            time=SimpleNamespace(monotonic_ns=lambda: 123),
            m=SimpleNamespace(OwnedSqlInvocation=functions,
                              _CreatorPopen=SimpleNamespace(__init__=inert_code)))
        escaped = None
        try:
            raise original
        except BaseException as caught:
            try:
                exec(compile(ast.Module(body=[*readiness, capture], type_ignores=[]),
                             "CREATOR_BOUNDARY_CAPTURE_FAILURE_UNIT", "exec"), namespace)
            except BaseException as error:
                escaped = error
            assert caught is original is retirement.primary
            class ReplacedDependency:
                def __getattribute__(self, name):
                    late.append(name)
                    raise injected
            def forbidden_import(*args, **kwargs):
                late.append("import")
                raise injected
            namespace.update(threading=ReplacedDependency(), sys=ReplacedDependency(),
                             m=ReplacedDependency())
            namespace["__builtins__"] = dict(vars(builtins), __import__=forbidden_import)
            exec(compile(ast.Module(body=[configuration], type_ignores=[]),
                         "CREATOR_BOUNDARY_NO_RECAPTURE_UNIT", "exec"), namespace)
            assert retirement.primary is original and retirement.outcome is outcome
            assert retirement.errors == errors and retirement.errors[0][1] is original
            assert retirement.outcome["SAFE"] is False and retirement.finalized is False
        results.append((dependency, reads, escaped is None,
                        namespace.get("_boundary_original_ready") is False,
                        late, namespace["creator_boundary"] is None))
    assert results == [(name, [name], True, True, [], True)
                       for name in ("_active", "_current_frames", "__code__")], (
        "ORIGINAL_CAPTURE_FAILURE_ESCAPED_OR_RECAPTURED", results)


def test_creator_boundary_source_contract():
    feature = _creator_boundary_unit_feature()
    import hashlib
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    source = path.read_text()
    retained, inside = [], False
    for line in _timeline_history_inputs()["lifecycle"].decode().splitlines(keepends=True):
        if line.strip() == "# CREATOR_BOUNDARY_BEGIN":
            assert not inside
            inside = True
        elif line.strip() == "# CREATOR_BOUNDARY_END":
            assert inside
            inside = False
        elif not inside:
            retained.append(line)
    assert not inside
    assert hashlib.sha256("".join(retained).encode()).hexdigest() == (
        "0c5bccf3bc538de3020a33a37a8d6570e17a2f0b66d33c26d86463467837e06d")
    assert hashlib.sha256(_timeline_history_inputs()["retirement"][:431324]).hexdigest() == (
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d")
    assert hashlib.sha256(_timeline_history_inputs()["retirement"][:400464]).hexdigest() == (
        "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d")
    for name, digest in (
        ("sql_isolation.py", "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e"),
        ("test_owned_sql_sdk_canonical.py",
         "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"),
        ("test_owned_sql_sdk_lifecycle.py",
         "b2eb26d15f6d0bffa5e9f668efb60f792e1d01a219f6a332a6ac7a9e51952f65"),
    ):
        assert hashlib.sha256(_timeline_history_inputs()["canonical"]
                              if name == "test_owned_sql_sdk_canonical.py"
                              else path.with_name(name).read_bytes()).hexdigest() == digest
    calls = [node for node in ast.walk(feature.tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "creator_boundary" and node.func.attr == "emit"]
    assert len(calls) == 2 and sorted(ast.literal_eval(node.args[0]) for node in calls) == [1, 2]
    host, = [node for node in feature.tree.body if getattr(node, "name", None) == "host_main"]
    assignments = [node for node in ast.walk(feature.tree) if isinstance(node, ast.Assign)]
    captures = {target.id: node for node in assignments for target in node.targets
                if isinstance(target, ast.Name) and target.id.startswith("_boundary_original_")}
    assert {"_boundary_original_thread", "_boundary_original_active",
            "_boundary_original_frames", "_boundary_original_write",
            "_boundary_original_clock", "_boundary_original_core"} <= captures.keys()
    trace, = [node for node in ast.walk(host) if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "trace"
                      for target in node.targets)]
    assert captures["_boundary_original_core"].lineno < trace.lineno
    configuration, = [node for node in ast.walk(host) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name)
                              and target.id == "_boundary_roots" for target in node.targets)]
    assert trace.lineno < configuration.lineno
    assert len(configuration.value.elts) == 7
    expected_paths = (
        ("OwnedSqlInvocation", "_controller"), ("OwnedSqlInvocation", "_register_pipe"),
        ("OwnedSqlInvocation", "_wait_startup"), ("_CreatorPopen", "__init__"),
        ("host_main", "spawn"), ("CreatorTrace", "__init__", "constructor"),
        ("_sdk_acceptance", "observed_close"))
    assert tuple(ast.literal_eval(root.elts[3])
                 for root in configuration.value.elts) == expected_paths
    assert ast.dump(captures["_boundary_original_active"].value) == ast.dump(
        ast.parse("threading._active", mode="eval").body)
    assert ast.dump(captures["_boundary_original_core"].value) == ast.dump(ast.parse(
        "(m.OwnedSqlInvocation._controller.__code__, "
        "m.OwnedSqlInvocation._register_pipe.__code__, "
        "m.OwnedSqlInvocation._wait_startup.__code__, "
        "m._CreatorPopen.__init__.__code__)", mode="eval").body)
    diagnostic, = [node for node in ast.walk(host) if isinstance(node, ast.FunctionDef)
                   and node.name == "sdk_diagnostic"]
    refusal, exception = sorted(calls, key=lambda node: ast.literal_eval(node.args[0]),
                                reverse=True)
    assert refusal in list(ast.walk(diagnostic))
    assert refusal.lineno > diagnostic.body[0].end_lineno
    host_try, = [node for node in host.body if isinstance(node, ast.Try)
                 and exception in list(ast.walk(node))]
    assert exception in list(ast.walk(host_try.handlers[0]))
    finish = [node for node in ast.walk(ast.Module(body=host_try.finalbody, type_ignores=[]))
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "finish"]
    assert len(finish) == 1 and exception.lineno < finish[0].lineno
    helper, = [node for node in feature.tree.body
               if getattr(node, "name", None) == "_CreatorBoundaryDiagnostic"]
    text = ast.get_source_segment(ast.literal_eval(next(
        node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets))), helper)
    for forbidden in ("snapshot(", ".poll(", ".wait(", ".cancel(", "enumerate(",
                      "is_alive(", "f_locals", "f_globals", "co_filename", ".result("):
        assert forbidden not in text


# Guardian budget UNIT metadata only. No actual watchdog thread or guest activation.
def _guardian_budget_unit_feature():
    tree = _compat_guest_tree()
    helpers = [node for node in tree.body
               if getattr(node, "name", None) == "_guardian_budget_diagnostic"]
    assert len(helpers) == 1, "GUARDIAN_BUDGET_HELPER_MISSING"
    guardian, = [node for node in tree.body if getattr(node, "name", None) == "guardian_main"]
    watchdog, = [node for node in guardian.body if getattr(node, "name", None) == "watchdog"]
    remaining, = [node for node in tree.body if getattr(node, "name", None) == "remaining"]
    flags = [node for node in tree.body if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "_guardian_budget_ready"
        for target in node.targets)]
    capture, = [node for node in tree.body if isinstance(node, ast.If) and any(
        isinstance(child, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_guardian_budget_clock"
            for target in child.targets) for child in ast.walk(node))]
    return SimpleNamespace(tree=tree, helper=helpers[0], watchdog=watchdog,
                           remaining=remaining, flags=flags, capture=capture)


def _guardian_budget_unit_case(feature, readiness="timeout", *, clock=None, writer=None,
                               capture_fault=None, cleanup_error=None, failure_error=None,
                               now=30.0, mode="guardian"):
    safety, done = 2147483629, 2147483587  # Inert identities, never OS descriptors.
    choices = dict(timeout=[], safety=[safety], done=[done], both=[safety, done],
                   reverse_both=[done, safety], unexpected=[123456789],
                   mixed=[safety, 123456789], duplicate=[safety, safety],
                   foreign_tuple=(safety,))
    ready = choices[readiness]
    events, writes, selected, errors = [], [], [], []
    ownership = SimpleNamespace(unit_only=True, retained=True)
    actual = ("UNIT_ONLY_NOT_PHYSICAL_PROOF",)
    def clock_read():
        events.append(("clock",))
        return 112233445566 if clock is None else clock()
    def write(fd, raw):
        events.append(("write",))
        writes.append((fd, raw))
        return len(raw) if writer is None else writer(fd, raw)
    class CaptureNamespace(SimpleNamespace):
        def __getattribute__(self, name):
            if name == capture_fault:
                events.append(("capture-failure", name))
                raise RuntimeError("UNIT_CAPTURE_FAILURE")
            return super().__getattribute__(name)
    def select(*args):
        events.append(("select",))
        selected.append(args)
        return ready, [], []
    def failure(where, **state):
        events.append(("failure", where, state))
        if failure_error is not None:
            raise failure_error
    def cleanup():
        events.append(("cleanup",))
        if cleanup_error is not None:
            errors.append(cleanup_error)
            raise cleanup_error
        ownership.retained = False
        return actual
    def emit(kind, **values):
        events.append((kind, values))
    namespace = dict(
        MODE=mode, END=123.75, json=json,
        time=CaptureNamespace(monotonic_ns=clock_read, monotonic=lambda: now),
        os=CaptureNamespace(write=write, _exit=lambda code: events.append(("exit", code))),
        select=SimpleNamespace(select=select), safety=safety, done_r=done,
        failure_diagnostic=failure, physical_cleanup=cleanup, emit=emit,
        hits=["UNIT_PRIVATE_CANARY"], contexts=[], forbidden_calls=[])
    # Compile only selected definitions and scalar capture, never the guest module.
    exec(compile(ast.Module(
        body=[*feature.flags, feature.capture, feature.helper, feature.remaining,
              feature.watchdog], type_ignores=[]), "GUARDIAN_BUDGET_INERT_UNIT", "exec"),
        namespace)
    return SimpleNamespace(namespace=namespace, watchdog=namespace["watchdog"],
                           writes=writes, events=events, selected=selected, ready=ready,
                           safety=safety, done=done, ownership=ownership, actual=actual,
                           errors=errors)


def _guardian_budget_unit_record(case):
    fd, raw = case.writes[0]
    assert len(case.writes) == 1 and fd == 2
    assert raw.endswith(b"\n") and len(raw) <= 512
    record = json.loads(raw)
    assert set(record) == {"kind", "reason", "end_ns", "cutoff_ns", "observed_ns"}
    assert record["kind"] == "FIXTURE_GUARDIAN_BUDGET"
    for key in ("end_ns", "cutoff_ns", "observed_ns"):
        assert type(record[key]) is int and 0 <= record[key] <= 2**63 - 1
    return record


def _guardian_budget_unit_regions(source):
    retained, ordinary, new, all_removed = [], [], [], []
    current = None
    for line in source.splitlines(keepends=True):
        if line.strip() == "# CREATOR_BOUNDARY_BEGIN":
            assert current is None
            current = [line]
        elif line.strip() == "# CREATOR_BOUNDARY_END":
            assert current is not None
            current.append(line)
            text = "".join(current)
            if "# GUARDIAN_BUDGET_BEGIN" in text:
                assert current[1].strip() == "# GUARDIAN_BUDGET_BEGIN"
                assert current[-2].strip() == "# GUARDIAN_BUDGET_END"
                assert sum(line.strip() == "# GUARDIAN_BUDGET_BEGIN"
                           for line in current) == 1
                assert sum(line.strip() == "# GUARDIAN_BUDGET_END"
                           for line in current) == 1
                new.append(text)
            else:
                ordinary.append(text)
                retained.extend(current)
            current = None
        elif current is not None:
            current.append(line)
        else:
            retained.append(line)
            all_removed.append(line)
    assert current is None
    return "".join(retained), ordinary, new, "".join(all_removed)


def test_guardian_budget_timeout_metadata():
    feature = _guardian_budget_unit_feature()
    case = _guardian_budget_unit_case(feature)
    case.watchdog()
    assert _guardian_budget_unit_record(case) == dict(
        kind="FIXTURE_GUARDIAN_BUDGET", reason="TIMEOUT",
        end_ns=int(123.75 * 1000000000),
        cutoff_ns=int((123.75 - 3.5) * 1000000000), observed_ns=112233445566)
    assert [event[0] for event in case.events] == [
        "select", "clock", "write", "failure", "cleanup", "SAFE", "exit"]
    assert case.events[-2:] == [
        ("SAFE", dict(actual=case.actual, independent=True, forbidden=0)), ("exit", 88)]


def test_guardian_budget_safety_metadata():
    feature = _guardian_budget_unit_feature()
    case = _guardian_budget_unit_case(feature, "safety")
    case.watchdog()
    assert _guardian_budget_unit_record(case)["reason"] == "SAFETY_READY"
    assert str(case.safety).encode() not in case.writes[0][1]
    assert str(case.done).encode() not in case.writes[0][1]
    for readiness in ("unexpected", "mixed", "duplicate", "foreign_tuple"):
        case = _guardian_budget_unit_case(feature, readiness)
        case.watchdog()
        assert case.writes == []
        assert [event[0] for event in case.events][-4:] == [
            "failure", "cleanup", "SAFE", "exit"]


def test_guardian_budget_done_precedence():
    feature = _guardian_budget_unit_feature()
    for readiness in ("done", "both", "reverse_both"):
        case = _guardian_budget_unit_case(feature, readiness)
        assert case.watchdog() is None
        assert case.events == [("select",)]
        assert len(case.selected) == 1 and case.writes == []
        assert case.ownership.retained is True  # No cleanup or synthesized SAFE.


def test_guardian_budget_original_select_contract():
    feature = _guardian_budget_unit_feature()
    expected = ast.parse(
        "ready = select.select([safety, done_r], [], [], remaining(END-3.5))[0]").body[0]
    assert ast.dump(feature.watchdog.body[0]) == ast.dump(expected)
    expected_done = ast.parse("if done_r in ready:\n    return").body[0]
    assert ast.dump(feature.watchdog.body[1]) == ast.dump(expected_done)
    selects = [node for node in ast.walk(feature.watchdog) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and ast.dump(node.func) == ast.dump(ast.parse("select.select", mode="eval").body)]
    assert len(selects) == 1
    for now, timeout in ((30.0, 90.25), (500.0, 0.001)):
        case = _guardian_budget_unit_case(feature, now=now)
        passed = []
        original = case.namespace["_guardian_budget_diagnostic"]
        def observe(ready, safety):
            passed.append((ready, safety))
            return original(ready, safety)
        case.namespace["_guardian_budget_diagnostic"] = observe
        case.watchdog()
        assert case.selected == [([case.safety, case.done], [], [], timeout)]
        assert passed[0][0] is case.ready and passed[0][1] == case.safety
        assert len(passed) == 1


def test_guardian_budget_capture_and_privacy():
    feature = _guardian_budget_unit_feature()
    redirected = []
    def forbidden(*args):
        redirected.append(args)
        raise AssertionError("UNIT_PRIVATE_CANARY")
    case = _guardian_budget_unit_case(feature, clock=lambda: 2**63 - 1)
    case.namespace["time"].monotonic_ns = forbidden
    case.namespace["os"].write = forbidden
    case.watchdog()
    assert _guardian_budget_unit_record(case)["observed_ns"] == 2**63 - 1
    assert redirected == []
    raw = case.writes[0][1]
    for canary in (b"UNIT_PRIVATE_CANARY", b"UNIT_ONLY_NOT_PHYSICAL_PROOF",
                   str(case.safety).encode(), str(case.done).encode(),
                   b"/Users/", b"guardian_main", b"SQL", b"pid", b"fd"):
        assert canary not in raw
    # Invalid scalar observations are omitted, not coerced, clamped or serialized.
    for observed in (True, -1, 2**63, 1.5, "UNIT_PRIVATE_CANARY", object()):
        case = _guardian_budget_unit_case(feature, clock=lambda: observed)
        case.watchdog()
        assert case.writes == [] and case.events[-1] == ("exit", 88)
    for mode in ("host", "role"):
        case = _guardian_budget_unit_case(feature, mode=mode)
        case.watchdog()  # Inert receiver only; no real non-guardian watchdog dispatch.
        assert case.namespace["_guardian_budget_ready"] is False
        assert case.writes == [] and not any(event[0] == "clock" for event in case.events)


def test_guardian_budget_emission_failure_preserves_cleanup():
    feature = _guardian_budget_unit_feature()
    def failure(*args, **kwargs):
        raise RuntimeError("UNIT_METADATA_FAILURE")
    for mode in ("clock", "conversion", "serialization", "write", "short",
                 "capture-clock", "capture-write"):
        case = _guardian_budget_unit_case(
            feature, clock=failure if mode == "clock" else None,
            writer=failure if mode == "write" else (
                (lambda fd, raw: 0) if mode == "short" else None),
            capture_fault={"capture-clock": "monotonic_ns", "capture-write": "write"}.get(mode))
        if mode == "conversion":
            case.namespace["int"] = failure
        elif mode == "serialization":
            case.namespace["json"] = SimpleNamespace(dumps=failure)
        # Capture failure remains disabled even after public dependencies recover.
        if mode.startswith("capture-"):
            case.namespace["time"].monotonic_ns = lambda: 123
            case.namespace["os"].write = lambda fd, raw: len(raw)
        case.watchdog()
        assert len(case.writes) == (1 if mode in ("write", "short") else 0)
        assert sum(event[0] == "cleanup" for event in case.events) == 1
        assert sum(event[0] == "failure" for event in case.events) == 1
        assert case.events[-2:] == [
            ("SAFE", dict(actual=case.actual, independent=True, forbidden=0)), ("exit", 88)]
        assert case.ownership.retained is False
    original = AssertionError("UNIT_ORIGINAL_FAILURE")
    case = _guardian_budget_unit_case(feature, clock=failure, failure_error=original)
    with pytest.raises(AssertionError) as caught:
        case.watchdog()
    assert caught.value is original
    assert case.ownership.retained is True and case.writes == []
    assert not any(event[0] in ("cleanup", "SAFE", "UNSAFE", "exit") for event in case.events)


def test_guardian_budget_cleanup_failure_preserves_ownership():
    feature = _guardian_budget_unit_feature()
    for readiness in ("timeout", "safety"):
        original = RuntimeError("UNIT_ORIGINAL_CLEANUP_FAILURE")
        case = _guardian_budget_unit_case(feature, readiness, cleanup_error=original)
        case.watchdog()
        assert len(case.writes) == 1
        assert case.errors == [original] and case.errors[0] is original
        assert case.ownership.retained is True
        assert [event[0] for event in case.events] == [
            "select", "clock", "write", "failure", "cleanup", "UNSAFE"]
        assert case.events[-1] == (
            "UNSAFE", dict(error="RuntimeError: UNIT_ORIGINAL_CLEANUP_FAILURE"))
        assert not any(event[0] in ("SAFE", "exit") for event in case.events)


def test_guardian_budget_source_contract():
    feature = _guardian_budget_unit_feature()
    import hashlib
    import textwrap
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    source = path.read_text()
    retained, old, new, all_removed = _guardian_budget_unit_regions(source)
    _history_retained, _history_old, _history_new, _history_all_removed = (
        _guardian_budget_unit_regions(_timeline_history_inputs()["lifecycle"].decode()))
    assert len(old) == 9 and len(new) == 3
    assert len(_history_retained.encode()) == 240418
    assert hashlib.sha256(_history_retained.encode()).hexdigest() == (
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa")
    assert hashlib.sha256(_history_all_removed.encode()).hexdigest() == (
        "0c5bccf3bc538de3020a33a37a8d6570e17a2f0b66d33c26d86463467837e06d")
    for length, expected in (
        (461193, "335fc5df9a49a6b53af1898820ef9c5cca7b45512d52fc399599133e64691257"),
        (431324, "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"),
        (400464, "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d"),
    ):
        assert hashlib.sha256(_timeline_history_inputs()["retirement"][:length] if length == 400464
                              else _timeline_history_inputs()["retirement"][:length]).hexdigest() == expected
    for name, expected in (
        ("sql_isolation.py", "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e"),
        ("test_owned_sql_sdk_canonical.py",
         "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"),
    ):
        assert hashlib.sha256(_timeline_history_inputs()["canonical"]
                              if name == "test_owned_sql_sdk_canonical.py"
                              else path.with_name(name).read_bytes()).hexdigest() == expected
    # These exact three blocks, not an unrestricted exemption for changed old code.
    additions = [ast.parse(textwrap.dedent("".join(block.splitlines(keepends=True)[2:-2])))
                 for block in new]
    assert len(additions[0].body) == 2
    assert ast.dump(additions[0].body[0]) == ast.dump(ast.parse(
        "_guardian_budget_ready = False").body[0])
    assert ast.dump(additions[0].body[1].test) == ast.dump(ast.parse(
        'MODE == "guardian"', mode="eval").body)
    capture_try, = additions[0].body[1].body
    assert isinstance(capture_try, ast.Try) and len(capture_try.handlers) == 1
    assert ast.dump(capture_try.handlers[0].type) == ast.dump(
        ast.parse("BaseException", mode="eval").body)
    assert ast.dump(capture_try.body[-1]) == ast.dump(ast.parse(
        "_guardian_budget_ready = True").body[0])
    assert len(additions[1].body) == 1
    assert additions[1].body[0].name == "_guardian_budget_diagnostic"
    assert len(additions[2].body) == 1
    call = additions[2].body[0]
    assert ast.dump(call) == ast.dump(ast.parse(
        "_guardian_budget_diagnostic(ready, safety)").body[0])
    assert ast.dump(feature.watchdog.body[2]) == ast.dump(call)
    original_body = feature.watchdog.body[:2] + feature.watchdog.body[3:]
    original_watchdog = ast.FunctionDef(
        name=feature.watchdog.name, args=feature.watchdog.args, body=original_body,
        decorator_list=feature.watchdog.decorator_list, type_params=[])
    # Compare under this interpreter against the byte-pinned original source.
    original_outer = ast.parse(retained)
    original_guest = ast.parse(ast.literal_eval(next(
        node.value for node in original_outer.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets))))
    original_guardian, = [node for node in original_guest.body
                          if getattr(node, "name", None) == "guardian_main"]
    expected_watchdog, = [node for node in original_guardian.body
                         if getattr(node, "name", None) == "watchdog"]
    assert ast.dump(original_watchdog) == ast.dump(expected_watchdog)
    source_guest = ast.literal_eval(next(
        node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)))
    helper_source = ast.get_source_segment(source_guest, feature.helper)
    for forbidden in ("time.", "os.", "snapshot(", "select(", "Thread(", "sleep(",
                      "f_locals", "f_code", "co_filename", ".pid", ".fileno",
                      "creator_boundary", "sibling", "request_cancel", "physical_cleanup"):
        assert forbidden not in helper_source


# Host budget UNIT metadata only. No guest activation or actual watchdog thread.
def _host_budget_unit_feature():
    tree = _compat_guest_tree()
    helpers = [node for node in tree.body
               if getattr(node, "name", None) == "_host_budget_diagnostic"]
    assert len(helpers) == 1, "HOST_BUDGET_HELPER_MISSING"
    host, = [node for node in tree.body if getattr(node, "name", None) == "host_main"]
    watchdog, = [node for node in host.body if getattr(node, "name", None) == "watchdog"]
    remaining, = [node for node in tree.body if getattr(node, "name", None) == "remaining"]
    outer, = [node for node in host.body if isinstance(node, ast.Try) and any(
        isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
        and child.func.attr == "fail" and child.args
        and isinstance(child.args[0], ast.Constant) and child.args[0].value == "host"
        for child in ast.walk(node))]
    return SimpleNamespace(tree=tree, helper=helpers[0], host=host, watchdog=watchdog,
                           remaining=remaining, outer=outer,
                           exception_sdk=outer.handlers[0].body[0])


def _host_budget_unit_case(feature, readiness="timeout", *, race=False, sdk=True,
                           mode="host", phase="sdk-UNIT", captured=True, clock=None,
                           writer=None, handoff="ALREADY_RETIRED", authorized=True,
                           finalized=False, cleanup_error=None, race_error=None, now=30.0):
    done, race_fd = 2147483587, 2147483629  # Inert numbers, never real descriptors.
    ready = dict(timeout=[], stdin=[0], race=[race_fd], both=[0, race_fd],
                 reverse=[race_fd, 0], unexpected=[123456789], done=[done],
                 done_stdin=[done, 0], done_race=[race_fd, done],
                 all=[0, race_fd, done])[readiness]
    events, writes, selected, fd_reads, event_queries = [], [], [], [], []
    ownership = SimpleNamespace(unit_only=True, retained=True)
    class NoEventQueries:
        def is_set(self):
            event_queries.append("is_set")
            raise AssertionError("EVENT_METADATA_QUERY_FORBIDDEN")
    state = SimpleNamespace(primary=None, errors=[], outcome=dict(ok=False, SAFE=False),
                            finalized=finalized, requested=NoEventQueries(),
                            fallback_requested=NoEventQueries())
    def clock_read():
        events.append(("clock",))
        return 112233445566 if clock is None else clock()
    def write(fd, raw):
        events.append(("write",))
        writes.append((fd, raw))
        return len(raw) if writer is None else writer(fd, raw)
    def select(*args):
        events.append(("select",))
        selected.append(args)
        return ready, [], []
    def fail(stage, error):
        events.append(("fail", stage, error))
        if state.primary is None:
            state.primary = error
        state.errors.append((stage, error))
    def native_handoff():
        events.append(("handoff",))
        return handoff
    def fallback():
        events.append(("fallback",))
    def request(**kwargs):
        events.append(("request", kwargs))
    def wait_handoff(deadline):
        events.append(("wait-handoff", deadline))
        return authorized
    def cleanup():
        events.append(("cleanup",))
        if cleanup_error is not None:
            raise cleanup_error
        ownership.retained = False  # UNIT state only, not physical evidence.
    def finished():
        events.append(("native-finished",))
    state.fail, state.request_native_handoff = fail, native_handoff
    state.request_fallback, state.request = fallback, request
    state.wait_native_handoff, state.supervisor_native_finished = wait_handoff, finished
    state.complete = SimpleNamespace(wait=lambda timeout: events.append(("complete-wait", timeout)))
    class InertRace:
        @property
        def fds(self):
            fd_reads.append(1)
            return [race_fd]
        def read_fault(self, deadline):
            events.append(("race-read", deadline))
            if race_error is not None:
                raise race_error
    namespace = dict(
        MODE=mode, PHASE=phase, END=123.75, json=json,
        _boundary_original_ready=captured, _boundary_original_clock=clock_read,
        _boundary_original_write=write,
        time=SimpleNamespace(monotonic=lambda: now, monotonic_ns=clock_read),
        os=SimpleNamespace(write=write), select=SimpleNamespace(select=select),
        done_r=done, sdk_watchdog_race=InertRace() if race else None,
        sdk_resources=state if sdk else None, cleanup=cleanup,
        finished=SimpleNamespace(set=lambda: events.append(("finished-set",))),
        report=lambda result, code: events.append(("report", result, code)))
    exec(compile(ast.Module(body=[feature.helper, feature.remaining, feature.watchdog],
                            type_ignores=[]), "HOST_BUDGET_INERT_UNIT", "exec"), namespace)
    return SimpleNamespace(feature=feature, namespace=namespace, watchdog=namespace["watchdog"],
                           sdk=state, ready=ready, done=done, race_fd=race_fd,
                           writes=writes, events=events, selected=selected, fd_reads=fd_reads,
                           ownership=ownership, event_queries=event_queries)


def _host_budget_unit_exception(case, original):
    try:
        raise original
    except BaseException as caught:
        assert caught is original
        case.namespace["exc"] = caught
        exec(compile(ast.Module(body=[case.feature.exception_sdk], type_ignores=[]),
                     "HOST_BUDGET_EXCEPTION_INERT_UNIT", "exec"), case.namespace)
        assert caught is original


def _host_budget_unit_record(case, index=0):
    fd, raw = case.writes[index]
    assert fd == 2 and raw.endswith(b"\n") and len(raw) <= 512
    result = json.loads(raw)
    assert set(result) == {"kind", "site", "reason", "end_ns", "cutoff_ns", "observed_ns"}
    assert result["kind"] == "FIXTURE_HOST_BUDGET"
    for name in ("end_ns", "cutoff_ns", "observed_ns"):
        assert type(result[name]) is int and 0 <= result[name] <= 2**63 - 1
    return result


def _host_budget_unit_regions(source):
    retained, old, new, all_removed = [], [], [], []
    current = None
    for line in source.splitlines(keepends=True):
        if line.strip() == "# CREATOR_BOUNDARY_BEGIN":
            assert current is None
            current = [line]
        elif line.strip() == "# CREATOR_BOUNDARY_END":
            assert current is not None
            current.append(line)
            text = "".join(current)
            if "# HOST_BUDGET_BEGIN" in text:
                assert current[1].strip() == "# HOST_BUDGET_BEGIN"
                assert current[-2].strip() == "# HOST_BUDGET_END"
                assert sum(line.strip() == "# HOST_BUDGET_BEGIN" for line in current) == 1
                assert sum(line.strip() == "# HOST_BUDGET_END" for line in current) == 1
                new.append(text)
            else:
                old.append(text)
                retained.extend(current)
            current = None
        elif current is not None:
            current.append(line)
        else:
            retained.append(line)
            all_removed.append(line)
    assert current is None
    return "".join(retained), old, new, "".join(all_removed)


def _host_budget_unit_migration_nodes(source):
    """Select exactly three Constant spans by their original assertion structure."""
    tree = ast.parse(source)
    function, = [node for node in tree.body
                 if getattr(node, "name", None) == "test_guardian_budget_source_contract"]
    expressions = ("len(old)", "len(retained.encode())",
                   "hashlib.sha256(retained.encode()).hexdigest()")
    nodes = []
    for expression in expressions:
        expected = ast.dump(ast.parse(expression, mode="eval").body)
        compare, = [node for node in ast.walk(function) if isinstance(node, ast.Compare)
                    and ast.dump(node.left) == expected]
        assert len(compare.ops) == len(compare.comparators) == 1
        assert isinstance(compare.ops[0], ast.Eq)
        value, = compare.comparators
        assert isinstance(value, ast.Constant)
        nodes.append(value)
    return nodes


def test_host_budget_watchdog_reasons():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    for race, readiness, reason in (
        (False, "timeout", "TIMEOUT"), (False, "stdin", "STDIN_READY"),
        (False, "unexpected", "OTHER"), (True, "timeout", "TIMEOUT"),
        (True, "race", "RACE_READY"), (True, "both", "RACE_READY"),
        (True, "reverse", "RACE_READY"), (True, "stdin", "STDIN_READY"),
        (True, "unexpected", "OTHER")):
        case = _host_budget_unit_case(feature, readiness, race=race)
        case.watchdog()
        assert len(case.writes) == 1
        assert _host_budget_unit_record(case) == dict(
            kind="FIXTURE_HOST_BUDGET", site="WATCHDOG_DECISION", reason=reason,
            end_ns=123750000000, cutoff_ns=120000000000, observed_ns=112233445566)
        assert case.events.index(("clock",)) < case.events.index(("handoff",))
        assert len(case.fd_reads) == (2 if race else 0)
        assert case.event_queries == []
    assert time.monotonic() < end


def test_host_budget_done_precedence():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    for readiness in ("done", "done_stdin", "done_race", "all"):
        case = _host_budget_unit_case(feature, readiness, race=True)
        case.watchdog()
        assert case.events == [("select",)] and case.writes == []
        assert len(case.selected) == 1 and len(case.fd_reads) == 1
        assert case.ownership.retained is True and case.sdk.errors == []
    assert time.monotonic() < end


def test_host_budget_exception_boundary_observation():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    case = _host_budget_unit_case(feature)
    original = AssertionError("UNIT_PRIVATE_EXCEPTION_CANARY")
    outcome = case.sdk.outcome
    _host_budget_unit_exception(case, original)
    assert len(case.writes) == 1
    assert _host_budget_unit_record(case) == dict(
        kind="FIXTURE_HOST_BUDGET", site="HOST_EXCEPTION", reason="EXCEPTION_BOUNDARY",
        end_ns=123750000000, cutoff_ns=120000000000, observed_ns=112233445566)
    assert [event[0] for event in case.events] == ["clock", "write", "fail"]
    assert case.sdk.primary is original and case.sdk.errors == [("host", original)]
    assert case.sdk.errors[0][1] is original and case.sdk.outcome is outcome
    assert case.ownership.retained is True and case.event_queries == []
    assert b"UNIT_PRIVATE_EXCEPTION_CANARY" not in case.writes[0][1]
    assert time.monotonic() < end


def test_host_budget_original_control_flow():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    expected_select = ast.parse(
        "ready = select.select(inputs, [], [], remaining(END-3.75))[0]").body[0]
    assert ast.dump(feature.watchdog.body[2]) == ast.dump(expected_select)
    assert ast.dump(feature.watchdog.body[3]) == ast.dump(
        ast.parse("if done_r in ready:\n    return").body[0])
    case = _host_budget_unit_case(feature, handoff="READY", finalized=True)
    passed = []
    original = case.namespace["_host_budget_diagnostic"]
    def observe(site, ready=None, inputs=None):
        passed.append((ready, inputs))
        return original(site, ready, inputs)
    case.namespace["_host_budget_diagnostic"] = observe
    case.watchdog()
    assert len(case.selected) == len(passed) == 1
    assert passed[0][0] is case.ready and passed[0][1] is case.selected[0][0]
    assert case.selected[0] == ([0, case.done], [], [], 90.0)
    assert [event[0] for event in case.events] == [
        "select", "clock", "write", "handoff", "fail", "fallback", "request",
        "wait-handoff", "cleanup", "native-finished", "complete-wait", "finished-set", "report"]
    assert ("request", dict(stop_loop=True)) in case.events
    assert ("wait-handoff", 120.25) in case.events and ("complete-wait", 93.5) in case.events
    assert case.events[-1][2] == 91
    race_error = RuntimeError("UNIT_ORIGINAL_RACE_FAULT")
    case = _host_budget_unit_case(feature, "both", race=True, handoff="READY",
                                  race_error=race_error)
    case.watchdog()
    assert [event[0] for event in case.events] == [
        "select", "clock", "write", "race-read", "fail", "handoff", "fallback",
        "request", "wait-handoff", "cleanup", "native-finished", "complete-wait"]
    assert case.sdk.errors == [("watchdog-trigger", race_error)]
    assert ("race-read", 120.0) in case.events and len(case.fd_reads) == 2
    for race in (False, True):
        case = _host_budget_unit_case(
            feature, "race" if race else "timeout", race=race,
            handoff="READY", authorized=False)
        case.watchdog()
        assert case.events[-1] == ("native-finished",)
        assert case.ownership.retained is True
        assert not any(event[0] in ("cleanup", "complete-wait", "report") for event in case.events)
    expired = _host_budget_unit_case(feature, now=500.0)
    expired.watchdog()
    assert expired.selected[0][-1] == 0.001
    assert time.monotonic() < end


def test_host_budget_capture_schema_and_privacy():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    redirected = []
    def forbidden(*args):
        redirected.append(args)
        raise AssertionError("UNIT_PRIVATE_CANARY")
    case = _host_budget_unit_case(feature, clock=lambda: 2**63 - 1)
    case.namespace["time"].monotonic_ns = forbidden
    case.namespace["os"].write = forbidden
    case.watchdog()
    assert _host_budget_unit_record(case)["observed_ns"] == 2**63 - 1 and redirected == []
    for canary in (b"UNIT_PRIVATE", b"/Users/", b"requested", b"fallback",
                   b"SAFE", b"pid", b"fd", str(case.done).encode(), str(case.race_fd).encode()):
        assert canary not in case.writes[0][1]
    for observed in (True, -1, 2**63, 1.5, object()):
        case = _host_budget_unit_case(feature, clock=lambda: observed)
        case.watchdog()
        assert case.writes == [] and case.event_queries == []
        assert case.events[-1] == ("handoff",)
    case = _host_budget_unit_case(feature, clock=lambda: 2**63 - 1)
    case.namespace["END"] = 9223372036.854774
    _host_budget_unit_exception(case, AssertionError("UNIT_PRIVATE_CANARY"))
    record = _host_budget_unit_record(case)
    assert all(len(str(record[key])) == 19 for key in ("end_ns", "cutoff_ns", "observed_ns"))
    maximum = dict(kind="FIXTURE_HOST_BUDGET", site="HOST_EXCEPTION",
                   reason="EXCEPTION_BOUNDARY", end_ns=2**63 - 1,
                   cutoff_ns=2**63 - 1, observed_ns=2**63 - 1)
    maximum_wire = json.dumps(maximum, separators=(",", ":")).encode("utf-8") + b"\n"
    assert len(case.writes[0][1]) == len(maximum_wire) <= 512
    for invalid_end in (-1, 1e30, float("inf"), float("nan"), None, object()):
        case = _host_budget_unit_case(feature)
        case.namespace["END"] = invalid_end
        case.namespace["_host_budget_diagnostic"]("HOST_EXCEPTION")
        assert case.writes == [] and case.sdk.errors == [] and case.ownership.retained is True
    for ready, inputs in (((), [0, 10]), ([], [0]), ([], [0, True]),
                          ([True], [0, 10]), ([], [0, 10, 10]), ([], None)):
        case = _host_budget_unit_case(feature)
        case.namespace["_host_budget_diagnostic"]("WATCHDOG_DECISION", ready, inputs)
        assert case.writes == [] and case.sdk.errors == []
    assert time.monotonic() < end


def test_host_budget_failures_preserve_original_failure():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    def failure(*args, **kwargs):
        raise RuntimeError("UNIT_METADATA_FAILURE")
    for mode in ("disabled", "preparation", "clock", "conversion", "write", "short"):
        case = _host_budget_unit_case(
            feature, captured=mode != "disabled", clock=failure if mode == "clock" else None,
            writer=failure if mode == "write" else (
                (lambda fd, raw: 0) if mode == "short" else None))
        if mode == "preparation":
            case.namespace["json"] = SimpleNamespace(dumps=failure)
        if mode == "conversion":
            case.namespace["int"] = failure
        original = AssertionError("UNIT_ORIGINAL_FAILURE")
        case.sdk.primary = original
        case.sdk.errors.append(("existing", original))
        ledger, outcome = case.sdk.errors, case.sdk.outcome
        case.watchdog()
        _host_budget_unit_exception(case, original)
        assert len(case.writes) == (2 if mode in ("write", "short") else 0)
        assert case.sdk.primary is original and case.sdk.errors is ledger
        assert case.sdk.errors == [("existing", original), ("host", original)]
        assert all(error is original for _, error in case.sdk.errors)
        assert case.sdk.outcome is outcome and outcome["SAFE"] is False
        assert case.ownership.retained is True and case.sdk.finalized is False
        assert sum(event[0] == "handoff" for event in case.events) == 1
        assert sum(event[0] == "fail" for event in case.events) == 1
    original = RuntimeError("UNIT_ORIGINAL_CLEANUP_FAILURE")
    case = _host_budget_unit_case(feature, handoff="READY", cleanup_error=original)
    case.watchdog()
    assert case.sdk.errors[-1] == ("watchdog-native", original)
    assert case.sdk.errors[-1][1] is original and case.ownership.retained is True
    assert case.events[-1][0] == "complete-wait"
    assert not any(event[0] in ("report", "finished-set") for event in case.events)
    assert time.monotonic() < end


def test_host_budget_scope_and_emission_count():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    for mode, phase in (("guardian", "sdk-UNIT"), ("role", "sdk-UNIT"),
                        ("host", "ordinary"), ("host", "")):
        case = _host_budget_unit_case(feature, mode=mode, phase=phase)
        case.watchdog()
        _host_budget_unit_exception(case, AssertionError("UNIT_ONLY"))
        assert case.writes == [] and not any(event[0] == "clock" for event in case.events)
    case = _host_budget_unit_case(feature, sdk=False)
    case.watchdog()
    _host_budget_unit_exception(case, AssertionError("UNIT_ONLY"))
    assert case.writes == [] and case.events[-1][0] == "report"
    case = _host_budget_unit_case(feature, "done", race=True)
    case.watchdog()  # Successful DONE path: no metadata/cleanup.
    assert case.events == [("select",)] and case.writes == []
    case = _host_budget_unit_case(feature)
    case.watchdog()
    _host_budget_unit_exception(case, AssertionError("UNIT_ONLY"))
    assert len(case.writes) == 2 and case.event_queries == []
    assert [_host_budget_unit_record(case, index)["site"] for index in (0, 1)] == [
        "WATCHDOG_DECISION", "HOST_EXCEPTION"]
    calls = [node for node in ast.walk(feature.tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "_host_budget_diagnostic"]
    assert len(calls) == 2
    assert time.monotonic() < end


def test_host_budget_source_contract():
    end = time.monotonic() + 3.0
    feature = _host_budget_unit_feature()
    import hashlib
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    source = path.read_text()
    retained, old, new, all_removed = _host_budget_unit_regions(source)
    _history_retained, _history_old, _history_new, _history_all_removed = (
        _host_budget_unit_regions(_timeline_history_inputs()["lifecycle"].decode()))
    assert len(old) == 9 and len(new) == 3 and len(_history_retained.encode()) == 239852
    assert hashlib.sha256(_history_retained.encode()).hexdigest() == (
        "c37051a6ab22ed5cf88b345c31b9473a158cbb889215b4d8896e4f5eace5c836")
    assert hashlib.sha256(_history_all_removed.encode()).hexdigest() == (
        "0c5bccf3bc538de3020a33a37a8d6570e17a2f0b66d33c26d86463467837e06d")
    # Approved fixed literals, computed once after the unchanged guardian-guard RED.
    migration_values = (
        9, 240418, "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa")
    old_values = (6, 237910, "a362af72063872e5818cf3e30ec705ad20c2d3fe24cb23a699f2b32f351403f7")
    test_bytes = _timeline_history_inputs()["retirement"]
    test_source = test_bytes.decode()
    nodes = _host_budget_unit_migration_nodes(test_source)
    lines = test_bytes.splitlines(keepends=True)
    changes = []
    for node, expected, original in zip(nodes, migration_values, old_values, strict=True):
        assert node.value == expected
        start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
        stop = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
        token = json.dumps(expected).encode()
        original_token = json.dumps(original).encode()
        assert test_bytes[start:stop] == token
        changes.append((start, stop, token, original_token))
    delta = sum(len(token) - len(original) for _, _, token, original in changes)
    prefix_length = 478655 + delta
    prefix = test_bytes[:prefix_length]
    for start, stop, token, original in sorted(changes, reverse=True):
        assert 0 <= start < stop <= prefix_length and prefix[start:stop] == token
        prefix = prefix[:start] + original + prefix[stop:]
    assert len(prefix) == 478655
    assert hashlib.sha256(prefix).hexdigest() == (
        "bd210190a2384539a21f65bc6abf41b0850fbb22b1da01574e578613a38f9317")
    # Match source AST against the exact byte-pinned literal baseline, same interpreter.
    outer = ast.parse(retained)
    original_guest = ast.parse(ast.literal_eval(next(
        node.value for node in outer.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets))))
    original_host, = [node for node in original_guest.body
                      if getattr(node, "name", None) == "host_main"]
    original_watchdog, = [node for node in original_host.body
                          if getattr(node, "name", None) == "watchdog"]
    watchdog = ast.parse(ast.unparse(feature.watchdog)).body[0]
    addition = watchdog.body.pop(4)
    assert ast.dump(addition.test) == ast.dump(
        ast.parse("sdk_resources is not None", mode="eval").body)
    assert ast.dump(addition.body[0]) == ast.dump(ast.parse(
        '_host_budget_diagnostic("WATCHDOG_DECISION", ready, inputs)').body[0])
    assert ast.dump(watchdog) == ast.dump(original_watchdog)
    exception = ast.parse(ast.unparse(feature.exception_sdk)).body[0]
    call = exception.body.pop(0)
    assert ast.dump(call) == ast.dump(ast.parse(
        '_host_budget_diagnostic("HOST_EXCEPTION")').body[0])
    original_outer, = [node for node in original_host.body if isinstance(node, ast.Try)
                       and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                               and child.func.attr == "fail" and child.args
                               and isinstance(child.args[0], ast.Constant)
                               and child.args[0].value == "host" for child in ast.walk(node))]
    assert ast.dump(exception) == ast.dump(original_outer.handlers[0].body[0])
    guest_source = ast.literal_eval(next(
        node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)))
    helper_source = ast.get_source_segment(guest_source, feature.helper)
    assert len(feature.helper.body) == 2 and isinstance(feature.helper.body[1], ast.Try)
    handler, = feature.helper.body[1].handlers
    assert isinstance(handler.type, ast.Name) and handler.type.id == "BaseException"
    for forbidden in ("sdk_resources", "getattr(", "repr(", ".is_set(", ".fds", ".fileno",
                      "time.", "os.", "Thread(", "sleep(", "select(", ".wait(",
                      ".poll(", ".acquire(", "f_locals", "co_filename"):
        assert forbidden not in helper_source
    assert time.monotonic() < end


# Cancellation-only recovery: ten bounded offline UNIT cases, not HOST liveness.
# Extract original fixture definitions; real owners/receipts, no SDK/native work.
class _ControllerCancelUnitEvent:
    def __init__(self, result=False, callback=None):
        self.ready = False
        self.result = result
        self.callback = callback
        self.waits = []

    def is_set(self):
        return self.ready

    def set(self):
        self.ready = True

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.callback is not None:
            self.callback()
        return self.ready or self.result


@pytest.fixture
def _controller_cancel_unit(tmp_path, monkeypatch):
    from ptc import sql_isolation as core
    from ptc import test_sql_owned_invocation as legacy
    bound = time.monotonic() + 3.0
    donor, profile, request = legacy._case(tmp_path, "scorer")
    loop = asyncio.new_event_loop()  # Self-pipe precedes offline denials.
    guard = legacy.offline_only.__wrapped__(loop, monkeypatch)
    denied_calls = next(guard)
    path = Path(__file__).with_name("test_owned_sql_sdk_canonical.py")
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    acceptance, = [node for node in tree.body if getattr(node, "name", None) == "_sdk_acceptance"]
    selected = [node for node in acceptance.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in ("observed_init", "retain_owner", "observed_close")]
    # Execute the actual per-acceptance holder setup when present, not an adapter.
    setup = [node for node in acceptance.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "cancel_release_events"
                     for target in node.targets)]
    fence, = [node for node in _compat_guest_tree().body
              if getattr(node, "name", None) == "_fence_owned_start"]
    fence_ns = {}
    exec(compile(ast.Module(body=[fence], type_ignores=[]), str(path), "exec"), fence_ns)
    cases = []

    def make(*, timeout=False, sibling=False, admission=None, release=None, clock=time):
        retirement = _SdkRetirement(
            loop=loop, deadline=min(bound, time.monotonic() + 2.0), disable=lambda: None)
        retirement.cancel_receipts = []
        actor = SimpleNamespace(
            retirement=retirement, spawn_lock=threading.RLock(),
            stopping=threading.Event(), owners=[], gates=[],
            end=time.monotonic() + 3.75, emit=lambda *args, **kwargs: None,
            fence_owned_start=fence_ns["_fence_owned_start"])
        case = SimpleNamespace(
            actor=actor, retirement=retirement, owners=[], bindings=[],
            admission=admission or _ControllerCancelUnitEvent(),
            release=release or _ControllerCancelUnitEvent(), events=[],
            bound=bound, core=core, donor=donor, loop=loop,
            source=source, tree=tree, scope=object(), rollout_calls=[],
            sibling_retained=[], constructed=[], original_entries=[])

        def get_scope():
            case.rollout_calls.append(case.scope)
            return case.scope

        def original_init(actual, *args, **kwargs):
            core.OwnedSqlInvocation.__init__(actual, *args, **kwargs)
            case.constructed.append(actual)

        async def observer(record):
            return None  # UNIT observer, no SDK work or fabricated outcome.

        namespace = dict(
            actor=actor, loop=loop, core=core, time=clock,
            SimpleNamespace=SimpleNamespace,
            asyncio=asyncio, original_init=original_init, owners=[],
            controller_gates=[], entered=[], closes=[], dispatch_turn=[0],
            released_first=[False], timeout_case=timeout, sibling_case=sibling,
            sibling_controller=[], sibling_queue=[], sibling_active=[None],
            release_sibling_dispatch=lambda: None,
            timeout_controllers=[], timeout_drivers=[],
            observe_timeout_scope=observer,
            _SdkScoringTimeout=lambda **kwargs: SimpleNamespace(**kwargs),
            api=SimpleNamespace(_rollout=SimpleNamespace(get=get_scope)),
            cancellation=None, probe=None, invalid_case=False,
            original_close=core.OwnedSqlInvocation.aclose)
        # Baseline constructor has no cancellation Event, so identify admission
        # creation from its current stack, without adding any runtime adapter.
        def fixture_event():
            caller = inspect.currentframe().f_back.f_code.co_name
            result = case.release if caller == "observed_init" else case.admission
            case.events.append(result)
            return result
        namespace["threading"] = SimpleNamespace(Event=fixture_event)
        case.ns = namespace
        exec(compile(ast.Module(body=setup + selected, type_ignores=[]), str(path), "exec"), namespace)

        def construct(*, specific=False, delegate=None):
            actual = object.__new__(core.OwnedSqlInvocation)
            if specific:
                namespace["sibling_case"] = True
                namespace["sibling_controller"] = [SimpleNamespace(
                    scope=case.scope, retain_owner=case.sibling_retained.append)]
            namespace["observed_init"](
                actual, donor.executor, donor.role, donor.request, donor.db_path)
            if not specific:
                def original(binding):
                    assert not actor.spawn_lock._is_owned()
                    assert not actual._lock._is_owned()
                    case.bindings.append((actual, binding))
                    if delegate is not None:
                        return delegate(actual, binding)
                    return binding  # Opaque UNIT callback result, NOT an ACK.
                actual._controller = original
                record = SimpleNamespace(actual=actual, scope=case.scope)
                namespace["retain_owner"](record)
            case.owners.append(actual)
            return actual
        case.construct = construct
        cases.append(case)
        return case
    try:
        yield make
    finally:
        assert time.monotonic() < bound, "absolute UNIT3 exhausted"
        # No forced release/cancellation: original unit observer Tasks finish.
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending))
        assert not asyncio.all_tasks(loop)
        assert all(owner._thread is None or not owner._thread.is_alive()
                   for case in cases for owner in case.owners)
        loop.close()
        next(guard, None)
        assert denied_calls == []


def _controller_cancel_authorize(case, owner, *, status="accepted"):
    receipt = owner.request_cancel("runner_closed")
    if status == "repeated":
        receipt = owner.request_cancel("runner_closed")
    case.retirement.cancel_receipts.append((owner, receipt))
    case.actor.stopping.set()
    return receipt


def _controller_cancel_reject(case, owner):
    primary = case.retirement.primary
    with pytest.raises(AssertionError) as caught:
        owner._controller(object())
    assert caught.value.args == ("SDK_CONTROLLER_PRE_ADMISSION_DEADLINE",)
    if case.retirement.errors:
        assert case.retirement.errors[-1] == ("controller-gate", caught.value)
        assert case.retirement.primary is (caught.value if primary is None else primary)
    assert case.bindings == []
    return caught.value


def test_controller_cancel_wait_healthy_gate_unchanged(_controller_cancel_unit):
    case = _controller_cancel_unit(admission=_ControllerCancelUnitEvent(result=True))
    first = case.construct()
    case.admission = _ControllerCancelUnitEvent()
    second = case.construct()
    binding = object()
    assert first._controller(binding) is binding
    assert case.bindings == [(first, binding)]
    assert case.release.waits == [] and not case.release.is_set()
    # Genuine ORIGINAL public predispatch close/ACK advances admission only.
    first.request_cancel("runner_closed")
    ack = case.loop.run_until_complete(case.ns["observed_close"](first))
    assert ack is first._completion.cleanup_ack is first._authority.ack
    assert ack.not_started and ack._authority.owner is first
    assert case.ns["dispatch_turn"] == [1]
    assert case.ns["controller_gates"][1].is_set()
    assert not case.release.is_set() and case.release.waits == []
    assert second._completion is None


def test_controller_cancel_wait_timeout_before_intent(_controller_cancel_unit):
    case = _controller_cancel_unit()
    owner = case.construct()
    error = _controller_cancel_reject(case, owner)
    assert case.retirement.primary is error
    assert case.retirement.errors == [("controller-gate", error)]
    assert len(case.release.waits) == 1
    assert owner.snapshot().intent is None
    # Missing constructor binding also fails closed with the SAME gate error.
    del owner._sdk_cancel_release_event
    case.retirement.errors.clear()
    case.retirement.primary = None
    _controller_cancel_reject(case, owner)
    assert len(case.release.waits) == 1


def test_controller_cancel_wait_ordinary_ack_not_authority(_controller_cancel_unit):
    case = _controller_cancel_unit()
    owner = case.construct()
    case.release.callback = case.admission.set
    _controller_cancel_reject(case, owner)
    assert case.admission.is_set() and not case.release.is_set()
    assert len(case.admission.waits) == len(case.release.waits) == 1


def test_controller_cancel_wait_late_authentic_intent(_controller_cancel_unit):
    from dataclasses import replace
    for status in ("accepted", "repeated"):
        case = _controller_cancel_unit()
        owner = case.construct()
        binding = object()
        def late():
            assert case.retirement.primary is not None
            _controller_cancel_authorize(case, owner, status=status)
            case.release.set()
        case.release.callback = late
        try:
            returned = owner._controller(binding)
        except AssertionError:
            # Baseline still receives REAL late cancellation after its ORIGINAL
            # gate failure; its missing delegation, not a missing helper, is RED.
            _controller_cancel_authorize(case, owner, status=status)
            for event in case.actor.gates:
                event.set()
            returned = None
        assert case.bindings == [(owner, binding)], "late authentic intent never delegated"
        assert returned is binding and len(case.release.waits) == 1
        assert type(case.retirement.primary) is AssertionError
    for corruption in ("foreign-owner", "equal-copy", "already-completed", "not-stopping"):
        case = _controller_cancel_unit()
        owner = case.construct()
        receipt = _controller_cancel_authorize(case, owner)
        if corruption == "foreign-owner":
            case.retirement.cancel_receipts[:] = [(object(), receipt)]
        elif corruption == "equal-copy":
            copied = replace(receipt.intent)
            assert copied == receipt.intent and copied is not receipt.intent
            case.retirement.cancel_receipts[:] = [(owner, case.core.CancelReceipt("accepted", copied))]
        elif corruption == "already-completed":
            case.retirement.cancel_receipts[:] = [(owner, case.core.CancelReceipt("already_completed", None))]
        else:
            case.actor.stopping.clear()
        case.release.set()
        _controller_cancel_reject(case, owner)


def test_controller_cancel_wait_failed_delivery(_controller_cancel_unit):
    # ORIGINAL lifecycle routine: failed original request/validation prevents
    # notification, including when a prior owner delivered successfully.
    for mode in ("request", "validation"):
        case = _controller_cancel_unit()
        owner = case.construct()
        other = case.construct()
        nodes = [node for node in ast.walk(_compat_guest_tree())
                 if isinstance(node, ast.FunctionDef)
                 and node.name in ("ensure_sdk_intents", "release_sdk_controllers")]
        assert len(nodes) == 2
        failure = AssertionError("UNIT original delivery failed")
        original = owner.request_cancel
        def request(reason):
            if mode == "request":
                raise failure
            receipt = original(reason)
            # Explicit invalid delivery receiver: original validator rejects
            # equal-but-distinct identity, never a manufactured ACK.
            from dataclasses import replace
            return case.core.CancelReceipt(receipt.status, replace(receipt.intent))
        owner.request_cancel = request
        ns = dict(
            owners=[other, owner], sdk_resources=case.retirement,
            gates=case.actor.gates, sdk_test_gates=SimpleNamespace(release_pending=lambda: None))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), __file__, "exec"), ns)
        with pytest.raises(AssertionError, match="SDK_PUBLIC_INTENT_MISSING"):
            ns["release_sdk_controllers"]()
        assert not case.release.is_set()
        if mode == "request":
            assert any(error is failure for _, error in case.retirement.errors)
        _controller_cancel_reject(case, owner)
        assert case.bindings == []


def test_controller_cancel_wait_notification_without_intent(_controller_cancel_unit):
    case = _controller_cancel_unit()
    owner = case.construct()
    case.actor.stopping.set()
    case.release.set()
    _controller_cancel_reject(case, owner)
    assert owner.snapshot().intent is None
    assert len(case.release.waits) == 1


def test_controller_cancel_wait_absolute_deadline(_controller_cancel_unit):
    for mode in ("absent", "expired", "zero", "during-retirement", "during-intent",
                 "receipt-retirement", "receipt-intent", "expired-intent"):
        now = [100.0]
        clock = SimpleNamespace(monotonic=lambda: now[0], monotonic_ns=lambda: int(now[0] * 1e9))
        case = _controller_cancel_unit(clock=clock)
        owner = case.construct()
        _controller_cancel_authorize(case, owner)
        original_intent = owner.snapshot().intent
        # Use the ORIGINAL intent's absolute cap, never reset its arithmetic.
        now[0] = original_intent.requested_ns / 1e9
        if mode in ("during-intent", "receipt-intent", "expired-intent"):
            # Keep retirement unexpired so its check cannot mask a missing
            # ORIGINAL intent-cap check. No real wait/intent arithmetic changes.
            now[0] = original_intent.deadline_ns / 1e9 - 0.001
        if mode == "expired-intent":
            now[0] += 0.002
        case.actor.end = now[0] + 3.75
        case.retirement.deadline = now[0] + 1.0
        if mode != "absent":
            case.release.set()
        if mode in ("expired", "zero"):
            case.retirement.deadline = now[0] - (1.0 if mode == "expired" else 0)
        if mode.startswith("during"):
            original = owner.snapshot
            def snapshot():
                value = original()
                now[0] = (case.retirement.deadline if mode == "during-retirement"
                          else original_intent.deadline_ns / 1e9 + 0.000001)
                return value
            owner.snapshot = snapshot
        if mode.startswith("receipt"):
            class ExpiringReceipts(list):
                def __iter__(self):
                    now[0] = (case.retirement.deadline if mode == "receipt-retirement"
                              else original_intent.deadline_ns / 1e9 + 0.000001)
                    return super().__iter__()
            case.retirement.cancel_receipts = ExpiringReceipts(case.retirement.cancel_receipts)
        _controller_cancel_reject(case, owner)
        assert len(case.release.waits) == 1
        expected = 0 if mode in ("expired", "zero") else 1.0
        assert case.release.waits == [expected]
        if mode in ("during-intent", "receipt-intent", "expired-intent"):
            assert now[0] < case.retirement.deadline


def test_controller_cancel_wait_original_callback_failure(_controller_cancel_unit):
    for origin in ("clock", "gate-wait", "release-wait", "stopping", "snapshot",
                   "fail", "delegate", "intent-clock", "retirement-clock",
                   "post-validation-clock", "post-validation-intent-clock"):
        case = _controller_cancel_unit()
        owner = case.construct()
        failure = AssertionError("UNIT callback assertion: " + origin)
        failures = []
        def broken(*args, **kwargs):
            failures.append(origin)
            raise failure
        if origin == "clock":
            case.ns["time"] = SimpleNamespace(monotonic=broken)
        elif origin == "gate-wait":
            case.admission.wait = broken
        elif origin == "release-wait":
            case.release.wait = broken
        elif origin == "fail":
            case.retirement.fail = broken
        else:
            _controller_cancel_authorize(case, owner)
            case.release.set()
            if origin == "stopping":
                case.actor.stopping.is_set = broken
            elif origin == "snapshot":
                owner.snapshot = broken
            elif origin == "intent-clock":
                case.ns["time"] = SimpleNamespace(monotonic=time.monotonic, monotonic_ns=broken)
            elif origin in ("retirement-clock", "post-validation-clock",
                            "post-validation-intent-clock"):
                clocks = []
                def monotonic():
                    clocks.append(None)
                    if len(clocks) == (2 if origin == "retirement-clock" else 4):
                        broken()
                    return time.monotonic()
                def monotonic_ns():
                    clocks.append(None)
                    if len(clocks) == 2:
                        broken()
                    return time.monotonic_ns()
                case.ns["time"] = (
                    SimpleNamespace(monotonic=time.monotonic, monotonic_ns=monotonic_ns)
                    if origin == "post-validation-intent-clock" else
                    SimpleNamespace(monotonic=monotonic, monotonic_ns=time.monotonic_ns))
            elif origin == "delegate":
                # Replace ONLY the explicit UNIT original callback, not wrapper.
                cell, = [cell for cell in owner._controller.__closure__
                         if callable(cell.cell_contents)
                         and getattr(cell.cell_contents, "__name__", "") == "original"]
                cell.cell_contents = broken
        with pytest.raises(AssertionError) as caught:
            owner._controller(object())
        assert caught.value is failure
        assert failures == [origin]
        assert case.bindings == []
        if origin in ("clock", "gate-wait"):
            assert case.retirement.errors == []
        elif origin != "fail":
            assert case.retirement.primary is not failure


def test_controller_cancel_wait_original_core_not_started_ack(
        _controller_cancel_unit, monkeypatch):
    import os
    from ptc import test_sql_owned_invocation as legacy
    case = _controller_cancel_unit(release=threading.Event())
    core = case.core
    observed_failure = threading.Event()
    done = threading.Event()
    errors = []
    original_fail = case.retirement.fail
    def fail(stage, error):
        original_fail(stage, error)
        observed_failure.set()
    case.retirement.fail = fail
    def original_controller(actual, binding):
        case.original_entries.append(actual)
        assert actual._completion is None and actual._candidate is None
        core.OwnedSqlInvocation._controller(actual, binding)
        assert actual._candidate == (None, "cancelled", None, ())
        assert actual._completion is None and actual._authority.ack is None
    owner = case.construct(delegate=original_controller)
    held = owner._controller
    def run(binding):
        try:
            held(binding)
        except BaseException as error:
            errors.append(error)
        finally:
            observed_failure.set()  # Baseline old gate failure is also observed.
            done.set()
    owner._controller = run
    # Original _start, original startup fence and real controller Thread.
    # Opaque offline binding receiver: cancellation branches never consume it.
    monkeypatch.setattr(core, "_fresh_owned_binding", lambda profile: object())
    forbidden = []
    def deny(*args, **kwargs):
        forbidden.append(True)
        raise AssertionError("UNIT forbidden pipe/native creation")
    monkeypatch.setattr(os, "pipe", deny)
    monkeypatch.setattr(core.OwnedSqlInvocation, "_spawn", deny)
    before = owner.snapshot()
    assert not case.actor.stopping.is_set()
    owner._start()
    assert owner._thread is not None
    assert observed_failure.wait(max(0, case.bound - time.monotonic()))
    receipt = _controller_cancel_authorize(case, owner)
    for event in case.actor.gates:
        event.set()  # Original release inventory, no baseline missing-helper abort.
    assert done.wait(max(0, case.bound - time.monotonic()))
    owner._thread.join(timeout=max(0, case.bound - time.monotonic()))
    assert not owner._thread.is_alive()
    assert case.original_entries == [owner], "original core controller was never entered"
    assert owner._candidate == (None, "cancelled", None, ())
    assert owner._completion is None and owner._authority.ack is None
    assert errors == [] and type(case.retirement.primary) is AssertionError
    assert case.retirement.primary.args == ("SDK_CONTROLLER_PRE_ADMISSION_DEADLINE",)
    async def public():
        completion = await owner.execute()
        ack = await owner.aclose()
        return completion, ack
    task = case.loop.create_task(public())
    _, pending = case.loop.run_until_complete(asyncio.wait(
        (task,), timeout=max(0, case.bound - time.monotonic())))
    assert not pending
    completion, ack = task.result()
    assert ack is completion.cleanup_ack is owner._authority.ack
    legacy._assert_not_started_ack(ack, before, receipt.intent)
    assert completion.abort.kind == "cancelled" and completion.outcome is None
    assert case.original_entries == [owner] and len(case.bindings) == 1
    assert not owner.executor.state_dir.exists()
    assert not owner.executor.profile.shared_state_dir.exists()
    assert owner._children == owner._endpoints == owner._resources == []
    assert owner._host_read is owner._seal_lock_fd is None and forbidden == []
    assert case.retirement.primary is not None  # Successful ACK never erases failure.


def test_controller_cancel_wait_source_and_registration_contract(
        _controller_cancel_unit, monkeypatch):
    case = _controller_cancel_unit()
    first = case.construct()
    assert len(case.actor.gates) == 2 and len(case.ns["controller_gates"]) == 1
    case.admission = _ControllerCancelUnitEvent()
    second = case.construct()
    assert len(case.actor.gates) == 3 and len(case.ns["controller_gates"]) == 2
    assert first._sdk_cancel_release_event is second._sdk_cancel_release_event is case.release
    assert sum(event is case.release for event in case.actor.gates) == 1
    assert all(event is not case.release for event in case.ns["controller_gates"])
    assert not case.release.is_set() and case.release.waits == []
    timeout = _controller_cancel_unit(timeout=True)
    timed = timeout.construct()
    assert timed._sdk_cancel_release_event is timeout.release
    assert len(timeout.actor.gates) == 2 and len(timeout.ns["controller_gates"]) == 1
    sibling = _controller_cancel_unit(sibling=True)
    specific = sibling.construct(specific=True)
    assert sibling.sibling_retained == [specific]
    assert len(sibling.rollout_calls) == 1 and sibling.events == []
    assert not hasattr(specific, "_sdk_cancel_release_event")
    sibling.scope = object()
    generic = sibling.construct()  # Generic sibling remains in scope.
    assert generic._sdk_cancel_release_event is sibling.release
    assert len(sibling.rollout_calls) == 2
    for owner in (first, second, timed, generic):
        # Original fenced FIRST start refuses retirement; no new controller.
        actor = next(row.actor for row in (case, timeout, sibling) if owner in row.owners)
        actor.stopping.set()
        with pytest.raises(RuntimeError, match="fixture owner startup retired"):
            owner._start()
        assert owner._thread is None
    # Stopping DURING construction may miss registration/release, but constructor
    # returns with startup fence installed: no later uncancelled first dispatch.
    race = _controller_cancel_unit()
    original = race.ns["original_init"]
    def retire_during_init(actual, *args, **kwargs):
        original(actual, *args, **kwargs)
        race.actor.stopping.set()
    race.ns["original_init"] = retire_during_init
    raced = object.__new__(case.core.OwnedSqlInvocation)
    race.ns["observed_init"](
        raced, case.donor.executor, case.donor.role, case.donor.request, case.donor.db_path)
    with pytest.raises(RuntimeError, match="fixture owner startup retired"):
        raced._start()
    assert raced._thread is None
    registration_race = _controller_cancel_unit()
    event_factory = registration_race.ns["threading"].Event
    def retire_during_event():
        registration_race.actor.stopping.set()
        for event in tuple(registration_race.actor.gates):
            event.set()  # Retirement missed the not-yet-registered new Event.
        return event_factory()
    registration_race.ns["threading"] = SimpleNamespace(Event=retire_during_event)
    raced = object.__new__(case.core.OwnedSqlInvocation)
    registration_race.ns["observed_init"](
        raced, case.donor.executor, case.donor.role, case.donor.request, case.donor.db_path)
    assert not raced._sdk_cancel_release_event.is_set()
    with pytest.raises(RuntimeError, match="fixture owner startup retired"):
        raced._start()
    assert raced._thread is None and registration_race.bindings == []
    for origin in ("constructor", "event"):
        broken = _controller_cancel_unit()
        failure = AssertionError("UNIT constructor/Event original assertion")
        def raise_original(*args, **kwargs):
            raise failure
        if origin == "constructor":
            broken.ns["original_init"] = raise_original
        else:
            broken.ns["threading"] = SimpleNamespace(Event=raise_original)
        with pytest.raises(AssertionError) as caught:
            broken.construct()
        assert caught.value is failure
    _controller_cancel_restoration_guard()


def _controller_cancel_restoration_guard():
    """Strict fixed-span reversal, never normalize an unlisted old operation."""
    import hashlib
    from ptc import test_owned_sql_sdk_canonical as canonical_module
    sha = lambda value: hashlib.sha256(value).hexdigest()
    path = Path(__file__)
    prefix = bytearray(_timeline_history_inputs()["retirement"][:502817])
    assert len(prefix) == 502817 and len(_CONTROLLER_CANCEL_RETIREMENT_PINS) == 11
    for start, old, new in _CONTROLLER_CANCEL_RETIREMENT_PINS:
        assert len(old) == len(new) == 64
        assert prefix[start:start + 64] == new.encode()
        prefix[start:start + 64] = old.encode()
    assert sha(prefix) == "6bf2c9746af5f9f21c1d1768ec80cde471e68441ce4e0e9c86f55808a1bf23f8"
    assert sha(_timeline_history_inputs()["retirement"][:400464]) == "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d"
    lifecycle = bytearray(_timeline_history_inputs()["lifecycle"])
    assert lifecycle[111575:111639] == b"6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    lifecycle[111575:111639] = b"383993b9b17725aa31cbfdbe2122857b86f370854cc9901957926c1688a2abc3"
    assert len(lifecycle) == 242360
    assert sha(lifecycle) == "3e6e96d824ce29404a4d798adf10592b81e39241207ee865995bb25da758850c"
    canonical = _timeline_history_inputs()["canonical"].decode()
    assert sha(canonical.encode()) == "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    for new, old in reversed(_CONTROLLER_CANCEL_CANONICAL_SPANS):
        assert canonical.count(new) == 1
        canonical = canonical.replace(new, old, 1)
    assert len(canonical.encode()) == 259994
    assert sha(canonical.encode()) == "383993b9b17725aa31cbfdbe2122857b86f370854cc9901957926c1688a2abc3"
    assert sha(path.with_name("sql_isolation.py").read_bytes()) == "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e"
    source = path.with_name("test_owned_sql_sdk_canonical.py").read_text()
    retirement, = [node for node in ast.parse(source).body
                   if getattr(node, "name", None) == "_SdkRetirement"]
    assert sha(ast.get_source_segment(source, retirement).encode()) == "800f4483b28823ccf418a995b7e6656983f4e5a29b5adda7550f561b9edf355b"
    roots = canonical_module._sdk_sibling_diagnostic_refs()
    assert len(roots) == 18 and tuple(label for label, _ in roots) == _SIBLING_DIAG_ROOTS

_CONTROLLER_CANCEL_RETIREMENT_PINS = [
    [
        412524,
        "0564371d43fca78d600a63335108f01d4e520dae456f4e26417c19a84f845182",
        "43825844ddbb83867b8575e4aad49b25a898965d7d19e98c3c78e28f573680c5"
    ],
    [
        431257,
        "cd1e78ef5ec7bbd09643c7b3116ed331b2456e3ea905826f330b3c6199c88d51",
        "e1a6d53e64436dac2b8ce0c4a850a978a3356c12448de5128819c5d217feb738"
    ],
    [
        456557,
        "aabc4c4193daa03706db6eb764d1ec5f4fa465dd7645ba3beb115c2921c316cb",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        456959,
        "383993b9b17725aa31cbfdbe2122857b86f370854cc9901957926c1688a2abc3",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        474886,
        "80c1c5be71608df5aa13b1f621703521b098ca4a02311f89ff4844a9b170abf5",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        475142,
        "7b72199cab33b99f5cb9824fc68132d907b413abfdc0591979e366d9e2a09a00",
        "335fc5df9a49a6b53af1898820ef9c5cca7b45512d52fc399599133e64691257"
    ],
    [
        475228,
        "aabc4c4193daa03706db6eb764d1ec5f4fa465dd7645ba3beb115c2921c316cb",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        475661,
        "383993b9b17725aa31cbfdbe2122857b86f370854cc9901957926c1688a2abc3",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        498428,
        "498313abdc1f7f1863894404aaa007f131371e2dc4b2e53266bba3ae32e209fd",
        "c37051a6ab22ed5cf88b345c31b9473a158cbb889215b4d8896e4f5eace5c836"
    ],
    [
        498766,
        "80c1c5be71608df5aa13b1f621703521b098ca4a02311f89ff4844a9b170abf5",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        500090,
        "3ad8c90b10cc80a72387470f0df014d3fb946456824e8b20ac1b9a2a271413d7",
        "bd210190a2384539a21f65bc6abf41b0850fbb22b1da01574e578613a38f9317"
    ]
]

_CONTROLLER_CANCEL_CANONICAL_SPANS = [
    [
        "    cancel_release_events = []\n",
        ""
    ],
    [
        "            sibling_retained = False\n",
        ""
    ],
    [
        "                sibling_retained = True\n",
        ""
    ],
    [
        "            if not sibling_retained:\n                if not cancel_release_events:\n                    event = threading.Event()\n                    actor.gates.append(event)\n                    cancel_release_events.append(event)\n                actual._sdk_cancel_release_event = cancel_release_events[0]\n",
        ""
    ],
    [
        "            admitted = gate.wait(max(0, actor.end - 3.75 - time.monotonic()))\n            if not admitted:\n                try:\n                    assert admitted, \"SDK_CONTROLLER_PRE_ADMISSION_DEADLINE\"\n                except AssertionError as error:\n                    actor.retirement.fail(\"controller-gate\", error)\n                    event = getattr(actual, \"_sdk_cancel_release_event\", None)\n                    if event is None:\n                        raise\n                    notified = event.wait(max(\n                        0, actor.retirement.deadline - time.monotonic()))\n                    if (not notified or not actor.stopping.is_set()\n                            or time.monotonic() >= actor.retirement.deadline):\n                        raise\n                    intent = actual.snapshot().intent\n                    if (type(intent) is not core.CancelIntent\n                            or time.monotonic_ns() >= intent.deadline_ns):\n                        raise\n                    if not any(\n                            retained is actual and type(receipt) is core.CancelReceipt\n                            and receipt.status in (\"accepted\", \"repeated\")\n                            and receipt.intent is intent\n                            for retained, receipt in actor.retirement.cancel_receipts):\n                        raise\n                    # Validation itself may consume the last absolute budget.\n                    if (time.monotonic() >= actor.retirement.deadline\n                            or time.monotonic_ns() >= intent.deadline_ns):\n                        raise\n                    return controller(binding)\n",
        "            assert gate.wait(max(0, actor.end - 3.75 - time.monotonic())), (\n                \"SDK_CONTROLLER_PRE_ADMISSION_DEADLINE\")\n"
    ],
    [
        "        if not actor.stopping.is_set() and not actor.retirement.requested.is_set():\n            if probe is None or not actor.retirement.requested.is_set():\n                assert owners[dispatch_turn[0]].actual is actual\n                dispatch_turn[0] += 1\n            # Fault cases release remaining controllers ONLY after real public\n            # cancellation, never as an ACK observer side effect.\n            if probe is None and dispatch_turn[0] < len(controller_gates):\n                controller_gates[dispatch_turn[0]].set()\n",
        "        if probe is None or not actor.retirement.requested.is_set():\n            assert owners[dispatch_turn[0]].actual is actual\n            dispatch_turn[0] += 1\n        # Fault cases release remaining controllers ONLY after real public\n        # cancellation, never as an ACK observer side effect.\n        if probe is None and dispatch_turn[0] < len(controller_gates):\n            controller_gates[dispatch_turn[0]].set()\n"
    ]
]


# ACK-order boundary correction: nine offline UNIT cases, not SDK/throughput proof.
def _close_guard_pair(make, probe):
    case = make()
    first = case.construct()
    case.admission = _ControllerCancelUnitEvent()
    second = case.construct()
    acknowledgements = {}
    for owner in (first, second):
        ack = case.loop.run_until_complete(case.core.OwnedSqlInvocation.aclose(owner))
        assert ack is owner._completion.cleanup_ack is owner._authority.ack
        assert ack.not_started and ack._authority.owner is owner
        acknowledgements[owner] = ack
    case.ns["probe"] = None if probe == "none" else SimpleNamespace()
    primary = ValueError("UNIT pre-existing retirement failure")
    case.retirement.fail("unit-marker", primary)
    return case, first, second, acknowledgements, primary


def _close_guard_no_advance(case, primary):
    assert case.ns["dispatch_turn"] == [0]
    assert all(not gate.is_set() for gate in case.ns["controller_gates"])
    assert not case.release.is_set()
    assert case.retirement.primary is primary
    assert case.retirement.errors == [("unit-marker", primary)]


def _close_guard_original_assertion(case, error, expression):
    # Require the actual unchanged observer assertion, not a UNIT stub failure.
    tb = error.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is case.ns["observed_close"].__code__
    source = Path(__file__).with_name("test_owned_sql_sdk_canonical.py").read_text()
    function, = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "observed_close"]
    assertion, = [node for node in ast.walk(function) if isinstance(node, ast.Assert)
                  and ast.get_source_segment(source, node).startswith(expression)]
    assert tb.tb_lineno == assertion.lineno


@pytest.mark.parametrize("signal", ("stopping", "requested", "both"))
def test_close_during_retirement_does_not_advance(_controller_cancel_unit, signal):
    for probe in ("none", "present"):
        case, first, second, acks, primary = _close_guard_pair(_controller_cancel_unit, probe)
        if signal in ("stopping", "both"):
            case.actor.stopping.set()
        if signal in ("requested", "both"):
            case.retirement.requested.set()
        for owner in (second, first):
            try:
                ack = case.loop.run_until_complete(case.ns["observed_close"](owner))
            except AssertionError as error:
                assert owner._completion.cleanup_ack is owner._authority.ack is acks[owner]
                assert case.ns["closes"][-1].ack is acks[owner]
                _close_guard_original_assertion(
                    case, error, "assert owners[dispatch_turn[0]].actual is actual")
                raise
            assert ack is acks[owner]
            _close_guard_no_advance(case, primary)


def test_close_healthy_ordered_advance(_controller_cancel_unit):
    for probe in ("none", "present"):
        case, first, second, acks, primary = _close_guard_pair(_controller_cancel_unit, probe)
        ack = case.loop.run_until_complete(case.ns["observed_close"](first))
        assert ack is acks[first]
        assert case.ns["dispatch_turn"] == [1]
        assert not case.ns["controller_gates"][0].is_set()
        assert case.ns["controller_gates"][1].is_set() is (probe == "none")
        assert not case.release.is_set()
        assert case.retirement.primary is primary
        assert case.retirement.errors == [("unit-marker", primary)]
        assert second._authority.ack is acks[second]


def test_close_healthy_out_of_order_rejected(_controller_cancel_unit):
    for probe in ("none", "present"):
        case, first, second, acks, primary = _close_guard_pair(_controller_cancel_unit, probe)
        with pytest.raises(AssertionError) as caught:
            case.loop.run_until_complete(case.ns["observed_close"](second))
        _close_guard_original_assertion(
            case, caught.value, "assert owners[dispatch_turn[0]].actual is actual")
        assert case.ns["closes"][-1].ack is acks[second]
        _close_guard_no_advance(case, primary)


def test_close_original_exception_preserved(_controller_cancel_unit):
    for probe in ("none", "present"):
        case, first, second, acks, primary = _close_guard_pair(_controller_cancel_unit, probe)
        case.actor.stopping.set()
        case.retirement.requested.set()
        failure = AssertionError("UNIT original public close exception")
        async def broken_close(actual):
            assert actual is second
            raise failure
        case.ns["original_close"] = broken_close  # Explicit negative UNIT callback.
        with pytest.raises(AssertionError) as caught:
            case.loop.run_until_complete(case.ns["observed_close"](second))
        assert caught.value is failure
        assert case.ns["closes"][-1].ack is None
        assert second._completion.cleanup_ack is acks[second]
        _close_guard_no_advance(case, primary)


def test_close_ack_identity_guard_preserved(_controller_cancel_unit):
    for probe in ("none", "present"):
        case, first, second, acks, primary = _close_guard_pair(_controller_cancel_unit, probe)
        case.actor.stopping.set()
        case.retirement.requested.set()
        wrong = object()
        async def wrong_close(actual):
            assert actual is second
            return wrong  # Deliberately invalid UNIT return, NOT an ACK claim.
        case.ns["original_close"] = wrong_close
        with pytest.raises(AssertionError) as caught:
            case.loop.run_until_complete(case.ns["observed_close"](second))
        _close_guard_original_assertion(
            case, caught.value, "assert actual._completion.cleanup_ack is actual._authority.ack is ack")
        assert case.ns["closes"][-1].ack is wrong
        assert second._completion.cleanup_ack is acks[second]
        _close_guard_no_advance(case, primary)


def _close_guard_stage_sources():
    path = Path(__file__)
    return dict(
        canonical=path.with_name("test_owned_sql_sdk_canonical.py").read_bytes(),
        lifecycle=path.with_name("test_sql_lifecycle_process.py").read_bytes(),
        retirement=path.read_bytes())


def test_close_guard_stage_restoration():
    end = time.monotonic() + 3.0
    proof = _close_guard_stage_restore(**_close_guard_stage_sources())
    assert proof == {
        "canonical": "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "lifecycle": "8a38a20dcd141e9e7fc96844b3cfcf91714d50d2b587814e478a1f1f1cfc7902",
        "retirement": "30a583960e87d5c767585c35aac3c2878edcc551a69520e4f55f639dbea6613c",
    }
    _controller_cancel_restoration_guard()  # Original cumulative operations unchanged.
    assert time.monotonic() < end


def test_close_guard_rejects_unlisted_change():
    end = time.monotonic() + 3.0
    sources = _close_guard_stage_sources()
    _close_guard_stage_restore(**sources)
    for name in ("canonical", "lifecycle", "retirement"):
        changed = bytearray(sources[name])
        changed[100] ^= 1  # Explicit in-memory unlisted old-byte mutation, no disk edit.
        with pytest.raises(AssertionError):
            _close_guard_stage_restore(**dict(sources, **{name: bytes(changed)}))
    assert time.monotonic() < end


def _close_guard_stage_restore(*, canonical, lifecycle, retirement):
    """Reverse only one functional span, 25 fixed SHA values and one data entry."""
    _timeline_inputs = _timeline_stage_rollback(
        **_handoff_dependency_stage_restore(
            canonical=canonical, lifecycle=lifecycle, retirement=retirement))
    canonical, lifecycle, retirement = (
        _timeline_inputs["canonical"], _timeline_inputs["lifecycle"], _timeline_inputs["retirement"])
    import hashlib
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    assert type(canonical) is type(lifecycle) is type(retirement) is bytes
    start, new, old = _CLOSE_GUARD_STAGE_CANONICAL_SPAN
    new, old = new.encode(), old.encode()
    assert len(canonical) == 261931 + len(new) - len(old)
    assert canonical[start:start + len(new)] == new
    restored = canonical[:start] + old + canonical[start + len(new):]
    assert len(restored) == 261931
    canonical_sha = sha(restored)
    assert canonical_sha == "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52"
    assert len(_CLOSE_GUARD_STAGE_LIFECYCLE_PINS) == 1
    assert len(lifecycle) == 242360
    restored = bytearray(lifecycle)
    for start, old, new in _CLOSE_GUARD_STAGE_LIFECYCLE_PINS:
        assert len(old) == len(new) == 64
        assert restored[start:start + 64] == new.encode()
        restored[start:start + 64] = old.encode()
    lifecycle_sha = sha(restored)
    assert lifecycle_sha == "8a38a20dcd141e9e7fc96844b3cfcf91714d50d2b587814e478a1f1f1cfc7902"
    assert len(_CLOSE_GUARD_STAGE_RETIREMENT_PINS) == 24
    assert len(_CLOSE_GUARD_STAGE_RETIREMENT_PINS) + len(_CLOSE_GUARD_STAGE_LIFECYCLE_PINS) == 25
    positions = [start for start, _, _ in _CLOSE_GUARD_STAGE_RETIREMENT_PINS]
    assert positions == sorted(set(positions))
    start, insertion = _CLOSE_GUARD_STAGE_TUPLE_INSERTION
    insertion = insertion.encode()
    assert len(insertion) == 1013 and 502817 < start < 536451
    # Account for the insertion BEFORE excluding only the newly appended tests.
    prefix = bytearray(retirement[:536451 + len(insertion)])
    assert len(prefix) == 536451 + len(insertion)
    assert prefix[start:start + len(insertion)] == insertion
    del prefix[start:start + len(insertion)]
    assert len(prefix) == 536451
    previous_stop = 0
    for start, old, new in _CLOSE_GUARD_STAGE_RETIREMENT_PINS:
        assert previous_stop <= start < start + 64 <= 536451
        assert len(old) == len(new) == 64
        assert prefix[start:start + 64] == new.encode()
        prefix[start:start + 64] = old.encode()
        previous_stop = start + 64
    retirement_sha = sha(prefix)
    assert retirement_sha == "30a583960e87d5c767585c35aac3c2878edcc551a69520e4f55f639dbea6613c"
    assert sha(retirement[:400464]) == "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d"
    return dict(canonical=canonical_sha, lifecycle=lifecycle_sha, retirement=retirement_sha)

_CLOSE_GUARD_STAGE_CANONICAL_SPAN = [
    182165,
    "        if not actor.stopping.is_set() and not actor.retirement.requested.is_set():\n            if probe is None or not actor.retirement.requested.is_set():\n                assert owners[dispatch_turn[0]].actual is actual\n                dispatch_turn[0] += 1\n            # Fault cases release remaining controllers ONLY after real public\n            # cancellation, never as an ACK observer side effect.\n            if probe is None and dispatch_turn[0] < len(controller_gates):\n                controller_gates[dispatch_turn[0]].set()\n",
    "        if probe is None or not actor.retirement.requested.is_set():\n            assert owners[dispatch_turn[0]].actual is actual\n            dispatch_turn[0] += 1\n        # Fault cases release remaining controllers ONLY after real public\n        # cancellation, never as an ACK observer side effect.\n        if probe is None and dispatch_turn[0] < len(controller_gates):\n            controller_gates[dispatch_turn[0]].set()\n"
]

_CLOSE_GUARD_STAGE_LIFECYCLE_PINS = [
    [
        111575,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ]
]

_CLOSE_GUARD_STAGE_RETIREMENT_PINS = [
    [
        412524,
        "e0108e94b35c84e9fac69cf2a3cd105f58717351372026c4f38e2fad14ecdcfc",
        "43825844ddbb83867b8575e4aad49b25a898965d7d19e98c3c78e28f573680c5"
    ],
    [
        431257,
        "015aa65147a271e7071495cdc4bbdfa5b19a4889cdcd6fb9dbffb8ee1eec2d9e",
        "e1a6d53e64436dac2b8ce0c4a850a978a3356c12448de5128819c5d217feb738"
    ],
    [
        456557,
        "b252330119f07ef5535cbb5ccf9b4e10eca01d61ed79f3d28f12352529600a70",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        456959,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        474886,
        "eb6bf6f5fc32b2883eb1ea08e6999b9589a9e160a6e39a0ed87010139f268214",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        475142,
        "9f83d2a77117e3506d2158746a3cdd908bad64a6684da140b45e54bf35e7dccd",
        "335fc5df9a49a6b53af1898820ef9c5cca7b45512d52fc399599133e64691257"
    ],
    [
        475228,
        "b252330119f07ef5535cbb5ccf9b4e10eca01d61ed79f3d28f12352529600a70",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        475661,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        498428,
        "d82dc846015ac39a441693e70f3ffc923a7262d35828cb613c936ff8f4086d8e",
        "c37051a6ab22ed5cf88b345c31b9473a158cbb889215b4d8896e4f5eace5c836"
    ],
    [
        498766,
        "eb6bf6f5fc32b2883eb1ea08e6999b9589a9e160a6e39a0ed87010139f268214",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        500090,
        "03e3e562e5b0dda8dc938ea9aeb01a4034f7f5e9753bfe8f913904b578520b46",
        "bd210190a2384539a21f65bc6abf41b0850fbb22b1da01574e578613a38f9317"
    ],
    [
        530537,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        530951,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        532099,
        "e0108e94b35c84e9fac69cf2a3cd105f58717351372026c4f38e2fad14ecdcfc",
        "43825844ddbb83867b8575e4aad49b25a898965d7d19e98c3c78e28f573680c5"
    ],
    [
        532279,
        "015aa65147a271e7071495cdc4bbdfa5b19a4889cdcd6fb9dbffb8ee1eec2d9e",
        "e1a6d53e64436dac2b8ce0c4a850a978a3356c12448de5128819c5d217feb738"
    ],
    [
        532459,
        "b252330119f07ef5535cbb5ccf9b4e10eca01d61ed79f3d28f12352529600a70",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        532639,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        532819,
        "eb6bf6f5fc32b2883eb1ea08e6999b9589a9e160a6e39a0ed87010139f268214",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        532999,
        "9f83d2a77117e3506d2158746a3cdd908bad64a6684da140b45e54bf35e7dccd",
        "335fc5df9a49a6b53af1898820ef9c5cca7b45512d52fc399599133e64691257"
    ],
    [
        533179,
        "b252330119f07ef5535cbb5ccf9b4e10eca01d61ed79f3d28f12352529600a70",
        "ab8858e19b81d33fe52372ac7842ce7bab3cbcc523d94257d6bc95e076c3f83d"
    ],
    [
        533359,
        "57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"
    ],
    [
        533539,
        "d82dc846015ac39a441693e70f3ffc923a7262d35828cb613c936ff8f4086d8e",
        "c37051a6ab22ed5cf88b345c31b9473a158cbb889215b4d8896e4f5eace5c836"
    ],
    [
        533719,
        "eb6bf6f5fc32b2883eb1ea08e6999b9589a9e160a6e39a0ed87010139f268214",
        "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa"
    ],
    [
        533899,
        "03e3e562e5b0dda8dc938ea9aeb01a4034f7f5e9753bfe8f913904b578520b46",
        "bd210190a2384539a21f65bc6abf41b0850fbb22b1da01574e578613a38f9317"
    ]
]

_CLOSE_GUARD_STAGE_TUPLE_INSERTION = [
    536448,
    ",\n    [\n        \"        if not actor.stopping.is_set() and not actor.retirement.requested.is_set():\\n            if probe is None or not actor.retirement.requested.is_set():\\n                assert owners[dispatch_turn[0]].actual is actual\\n                dispatch_turn[0] += 1\\n            # Fault cases release remaining controllers ONLY after real public\\n            # cancellation, never as an ACK observer side effect.\\n            if probe is None and dispatch_turn[0] < len(controller_gates):\\n                controller_gates[dispatch_turn[0]].set()\\n\",\n        \"        if probe is None or not actor.retirement.requested.is_set():\\n            assert owners[dispatch_turn[0]].actual is actual\\n            dispatch_turn[0] += 1\\n        # Fault cases release remaining controllers ONLY after real public\\n        # cancellation, never as an ACK observer side effect.\\n        if probe is None and dispatch_turn[0] < len(controller_gates):\\n            controller_gates[dispatch_turn[0]].set()\\n\"\n    ]"
]


# SDK_TIMELINE_STAGE_APPEND_BEGIN v1
# STAGE1: inert UNIT dependencies and four old-path behavioral tests only.
# No production timeline class, inverse tables, acquisition or runtime adapter.


def _timeline_source_blocks():
    """Select actual nodes between original anchors, without changing their AST."""
    path = Path(__file__)
    canonical_path = path.with_name("test_owned_sql_sdk_canonical.py")
    lifecycle_path = path.with_name("test_sql_lifecycle_process.py")
    canonical = canonical_path.read_text()
    lifecycle = lifecycle_path.read_text()
    canonical_tree = ast.parse(canonical, filename=str(canonical_path))
    lifecycle_tree = ast.parse(lifecycle, filename=str(lifecycle_path))

    def one(values, label):
        assert len(values) == 1, ("TIMELINE_SETUP_ANCHOR", label, len(values))
        return values[0]

    assignment = one([
        node for node in lifecycle_tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)], "literal guest")
    guest = ast.literal_eval(assignment.value)
    guest_tree = ast.parse(guest, filename=str(lifecycle_path))
    acceptance = one([
        node for node in canonical_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_sdk_acceptance"],
        "acceptance")
    host = one([
        node for node in guest_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "host_main"], "host")

    def same(node, expression):
        return ast.dump(node) == ast.dump(ast.parse(expression).body[0])

    ready_index = one([
        index for index, node in enumerate(guest_tree.body)
        if same(node, "_boundary_original_ready = False")], "original capture ready")
    capture_if = guest_tree.body[ready_index + 1]
    assert isinstance(capture_if, ast.If), "TIMELINE_SETUP_CAPTURE_IF"
    assert ast.dump(capture_if.test) == ast.dump(ast.parse(
        'MODE == "host" and PHASE.startswith("sdk-")', mode="eval").body)
    assert any(isinstance(node, ast.Name) and node.id == "_boundary_original_core"
               and isinstance(node.ctx, ast.Store) for node in ast.walk(capture_if))
    capture = guest_tree.body[ready_index:ready_index + 2]
    root_index = one([
        index for index, node in enumerate(host.body)
        if same(node, "root = Path(ROOT)")], "host root")
    host_prefix = host.body[:root_index + 1]
    import_index = one([
        index for index, node in enumerate(acceptance.body)
        if isinstance(node, ast.Import)
        and [(item.name, item.asname) for item in node.names] == [
            ("cotrain_owned_sql", "api")]], "original API import")
    acceptance_prefix = acceptance.body[:import_index]
    assert (acceptance_prefix and isinstance(acceptance_prefix[0], ast.Expr)
            and isinstance(acceptance_prefix[0].value, ast.Constant)
            and isinstance(acceptance_prefix[0].value.value, str)), "TIMELINE_SETUP_DOC"

    # Preserve the entire actual sibling interval, including future optional Try.
    first_intervals = []
    for parent in ast.walk(acceptance):
        for _, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            for index, node in enumerate(value):
                if not isinstance(node, ast.stmt) or not same(
                        node, "released_first[0] = True"):
                    continue
                assert same(value[index + 1], "controller_gates[0].set()")
                boundaries = [
                    stop for stop in range(index + 2, len(value))
                    if isinstance(value[stop], ast.If)
                    and isinstance(value[stop].test, ast.Name)
                    and value[stop].test.id == "invalid_case"]
                assert boundaries, "TIMELINE_SETUP_FIRST_END"
                first_intervals.append(value[index:boundaries[0]])
    first_set = one(first_intervals, "first setter interval")
    finish_if = one([
        node for node in ast.walk(host) if isinstance(node, ast.If)
        and ast.dump(node.test) == ast.dump(ast.parse(
            "sdk_resources is not None", mode="eval").body)
        and any(isinstance(child, ast.Assert)
                and isinstance(child.test, ast.Attribute)
                and isinstance(child.test.value, ast.Name)
                and child.test.value.id == "sdk_resources"
                and child.test.attr == "finalized" for child in node.body)],
        "healthy SDK finish")
    assert same(finish_if.body[0], "sdk_resources.record_outcome(result)")
    assert same(finish_if.body[1],
                "sdk_resources.finish(native_retire=sdk_native_cleanup, verify_native=sdk_native_proof)")
    assert same(finish_if.body[-1], "finished.set()")
    callbacks = [
        node for node in acceptance.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in ("observed_init", "retain_owner", "observed_close")]
    assert {node.name for node in callbacks} == {
        "observed_init", "retain_owner", "observed_close"}

    blocks = {
        "capture": (str(lifecycle_path), guest, capture),
        "host_prefix": (str(lifecycle_path), guest, host_prefix),
        "acceptance_prefix": (str(canonical_path), canonical, acceptance_prefix),
        "first_set": (str(canonical_path), canonical, first_set),
        "healthy_finish": (str(lifecycle_path), guest, finish_if.body),
    }
    # No SDK/framework import, whole module, rewritten node or synthetic call.
    for _, _, nodes in blocks.values():
        assert not any(isinstance(child, (ast.Import, ast.ImportFrom))
                       for node in nodes for child in ast.walk(node)), "TIMELINE_SETUP_IMPORT"
    return SimpleNamespace(
        blocks=blocks, canonical=canonical, canonical_path=str(canonical_path),
        callbacks=callbacks, provenance={
            name: dict(filename=filename,
                       ranges=[(node.lineno, node.end_lineno) for node in nodes],
                       actual_statements=[ast.get_source_segment(source, node)
                                          for node in nodes])
            for name, (filename, source, nodes) in blocks.items()})


class _TimelineGate(_ControllerCancelUnitEvent):
    """UNIT setter delegates first; only its returned call enters the ledger."""

    def __init__(self, ordinal, chronology):
        super().__init__()
        self.ordinal, self.chronology = ordinal, chronology
        self.returned = 0

    def set(self):
        result = super().set()
        self.returned += 1
        self.chronology.append(("setter-returned", self.ordinal))
        return result


class _TimelineReceiver:
    """Inert UNIT receiver, never the future runtime collector or a wire proof."""

    def __init__(self, *, clock, write, case, chronology, check):
        self._clock, self._write = clock, write
        self.case, self.chronology, self.check = case, chronology, check
        self.rows, self.ack_at_note, self.setter_at_note = [], [], []
        self.factory_bindings, self.emit_calls = [], 0

    def note(self, event, owner=None, registry=()):
        self.check()
        ordinal = 0
        if owner is not None:
            positions = [index for index, record in enumerate(registry, 1)
                         if record.actual is owner]
            assert len(positions) == 1, "TIMELINE_UNIT_REGISTRY"
            ordinal = positions[0]
        # Snapshot, do not gate recording on ACK validity. A misplaced callback
        # must produce a row in the wrong-ACK/exception negative controls.
        if event == 5:
            record = self.case.ns["closes"][-1]
            self.ack_at_note.append((
                owner, owner._completion.cleanup_ack, owner._authority.ack, record.ack))
        ns = self._clock()
        assert type(ns) is int
        self.rows.append((event, ordinal, ns))
        self.setter_at_note.append(tuple(self.chronology))
        self.chronology.append(("note", event, ordinal))
        self.check()

    def emit_failure(self):
        self.check()
        self.emit_calls += 1
        self._write(2, b"")  # Declared inert writer, never os.write or real fd2.


@pytest.fixture
def _timeline_baseline_units(_controller_cancel_unit):
    # The existing fixture starts the ONLY UNIT3 clock before its own setup.
    # Taking a seed exposes that existing bound, never starts a fresh deadline.
    seed = _controller_cancel_unit()
    deadline = seed.bound
    cases, contexts = [seed], []
    seed_claimed = False

    def check():
        assert time.monotonic() < deadline, "absolute timeline UNIT3 exhausted"

    check()
    source = _timeline_source_blocks()
    check()

    def make(*, admission=None):
        nonlocal seed_claimed
        check()
        if not seed_claimed:
            seed_claimed = True
            case = seed
            if admission is not None:
                case.admission = admission
        else:
            case = _controller_cancel_unit(admission=admission)
            cases.append(case)
        assert case.bound == deadline
        assert case.source == source.canonical
        for node in source.callbacks:
            callback = case.ns[node.name]
            assert callback.__code__.co_filename == source.canonical_path
            assert callback.__code__.co_firstlineno == node.lineno
        check()
        return case

    def execute(name, namespace):
        check()
        filename, _, nodes = source.blocks[name]
        # Actual nodes and original locations only. No AST replacement/injection.
        code = compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec")
        exec(code, namespace)
        check()
        return code

    def run(case, awaitable):
        check()
        try:
            return case.loop.run_until_complete(awaitable)
        finally:
            check()

    def context(case, *, chronology=None, attach=True):
        check()
        chronology = [] if chronology is None else chronology
        clocks, writes, replaced = [], [], []

        def clock():
            check()
            value = 1000000 + len(clocks)
            clocks.append(value)
            return value

        def write(fd, data):
            check()
            writes.append((fd, data))
            return len(data)

        def replacement(*args, **kwargs):
            replaced.append(True)
            raise AssertionError("UNIT public dependency recaptured")

        unit_time = SimpleNamespace(monotonic_ns=clock)
        unit_os = SimpleNamespace(write=write)
        import sys  # Stdlib reference only; frames are never queried.
        namespace = dict(
            MODE="host", PHASE="sdk-positive-two", m=case.core,
            threading=threading, sys=sys, os=unit_os, time=unit_time,
            Path=Path, ROOT="UNIT_TIMELINE_ROOT", _sdk_timeline=None)
        creator_denial = case.core._CreatorPopen.__init__
        execute("capture", namespace)
        assert namespace["_boundary_original_ready"] is True
        assert namespace["_boundary_original_clock"] is clock
        assert namespace["_boundary_original_write"] is write
        assert namespace["_boundary_original_core"] == (
            case.core.OwnedSqlInvocation._controller.__code__,
            case.core.OwnedSqlInvocation._register_pipe.__code__,
            case.core.OwnedSqlInvocation._wait_startup.__code__,
            creator_denial.__code__)
        # Denials were installed BEFORE this capture. This is the fixture's
        # denial closure code, NOT an original creator-code provenance claim.
        assert case.core._CreatorPopen.__init__ is creator_denial
        unit_time.monotonic_ns = replacement
        unit_os.write = replacement
        receiver = _TimelineReceiver(
            clock=namespace["_boundary_original_clock"],
            write=namespace["_boundary_original_write"],
            case=case, chronology=chronology, check=check)

        def _timeline_receiver_factory(*, clock, write):
            receiver.factory_bindings.append((clock, write))
            return receiver  # No note, write, source edit or helper lookup.

        namespace["_SdkTimeline"] = _timeline_receiver_factory
        if attach:
            case.actor._sdk_timeline = receiver
        result = SimpleNamespace(
            case=case, ns=namespace, receiver=receiver, clocks=clocks, writes=writes,
            replaced=replaced, chronology=chronology, clock=clock, write=write,
            creator_denial=creator_denial)
        contexts.append(result)
        check()
        return result

    def public_acks(case, owners):
        result = {}
        for owner in owners:
            check()
            assert not case.actor.stopping.is_set()
            assert not case.retirement.requested.is_set()
            ack = run(case, case.core.OwnedSqlInvocation.aclose(owner))
            assert ack is owner._completion.cleanup_ack is owner._authority.ack
            assert ack.not_started and ack._authority.owner is owner
            result[owner] = ack
        return result

    def publish(record_property, label, context, *, ack_identity=()):
        check()
        receiver = context.receiver
        assert receiver._clock is context.ns["_boundary_original_clock"] is context.clock
        assert receiver._write is context.ns["_boundary_original_write"] is context.write
        assert context.replaced == []
        assert len(context.clocks) == len(receiver.rows)
        assert all(clock is context.clock and write is context.write
                   for clock, write in receiver.factory_bindings)
        assert context.case.core._CreatorPopen.__init__ is context.creator_denial
        record_property("timeline_" + label, json.dumps(dict(
            source_blocks=source.provenance,
            callbacks={node.name: dict(filename=context.case.ns[node.name].__code__.co_filename,
                                        line=context.case.ns[node.name].__code__.co_firstlineno)
                       for node in source.callbacks},
            chronology=context.chronology, rows=receiver.rows,
            ack_identity=list(ack_identity),
            original_clock_identity=True, original_write_identity=True,
            creator_capture="already-installed offline denial closure, not original creator",
            absolute_deadline=deadline, no_recapture=True), sort_keys=True))
        check()

    units = SimpleNamespace(
        make=make, check=check, execute=execute, run=run, context=context,
        public_acks=public_acks, publish=publish, source=source, deadline=deadline)
    try:
        yield units
    finally:
        # This finalizer runs before the UNCHANGED fixture drains its own tasks
        # and verifies its SAME bound, no live owner thread and zero denied calls.
        check()
        assert all(owner._thread is None for case in cases for owner in case.constructed)
        assert all(context.replaced == [] for context in contexts)
        check()


def test_timeline_same_clock_anchors(_timeline_baseline_units, record_property):
    units = _timeline_baseline_units
    chronology = []
    gate = _TimelineGate(1, chronology)
    case = units.make(admission=gate)
    owner = case.construct()
    assert not case.ns["released_first"][0] and not gate.is_set()
    context = units.context(case, chronology=chronology)
    units.execute("host_prefix", context.ns)
    assert context.ns["root"] == Path("UNIT_TIMELINE_ROOT")
    units.execute("acceptance_prefix", case.ns)
    units.execute("first_set", case.ns)
    assert case.ns["released_first"] == [True]
    assert case.ns["controller_gates"] == [gate]
    assert gate.is_set() and gate.returned == 1
    assert case.ns["owners"][0].actual is owner
    assert not case.bindings and owner._thread is None
    units.publish(record_property, "anchors", context)
    rows = context.receiver.rows
    assert ([(event, ordinal) for event, ordinal, _ in rows] == [(1, 0), (2, 0), (3, 1)]
            and [ns for _, _, ns in rows] == [1000000, 1000001, 1000002]
            and ("setter-returned", 1) in context.receiver.setter_at_note[-1]
            ), "TIMELINE_ANCHORS_MISSING"


def test_timeline_ack_identity_precedes_timestamp(_timeline_baseline_units, record_property):
    units = _timeline_baseline_units

    def prepare():
        case = units.make()
        first = case.construct()
        case.admission = _ControllerCancelUnitEvent()
        second = case.construct()
        acks = units.public_acks(case, (first, second))
        context = units.context(case)
        case.ns["probe"] = SimpleNamespace()  # Suppresses event6, not ACK assertion.
        return case, first, second, acks, context

    # Both explicit negative callbacks precede the final positive observation.
    case, first, second, acks, context = prepare()
    case.actor.stopping.set()
    case.retirement.requested.set()
    wrong = object()

    async def wrong_close(actual):
        assert actual is second
        return wrong  # Deliberately invalid UNIT return, not a genuine ACK.

    case.ns["original_close"] = wrong_close
    with pytest.raises(AssertionError) as caught:
        units.run(case, case.ns["observed_close"](second))
    _close_guard_original_assertion(
        case, caught.value, "assert actual._completion.cleanup_ack is actual._authority.ack is ack")
    assert case.ns["closes"][-1].ack is wrong
    assert second._completion.cleanup_ack is second._authority.ack is acks[second]
    assert context.receiver.rows == [] and context.clocks == []
    assert case.ns["dispatch_turn"] == [0]
    units.publish(record_property, "wrong_ack_control", context, ack_identity=(True,))

    case, first, second, acks, context = prepare()
    case.actor.stopping.set()
    case.retirement.requested.set()
    failure = AssertionError("UNIT original public close exception")

    async def broken_close(actual):
        assert actual is second
        raise failure

    case.ns["original_close"] = broken_close
    with pytest.raises(AssertionError) as caught:
        units.run(case, case.ns["observed_close"](second))
    assert caught.value is failure
    assert case.ns["closes"][-1].ack is None
    assert second._completion.cleanup_ack is second._authority.ack is acks[second]
    assert context.receiver.rows == [] and context.clocks == []
    assert case.ns["dispatch_turn"] == [0]
    units.publish(record_property, "original_exception_control", context, ack_identity=(True,))

    case, first, second, acks, context = prepare()
    primary, errors = case.retirement.primary, tuple(case.retirement.errors)
    ack = units.run(case, case.ns["observed_close"](first))
    record = case.ns["closes"][-1]
    assert ack is record.ack is first._completion.cleanup_ack is first._authority.ack is acks[first]
    assert case.ns["dispatch_turn"] == [1]
    assert not any(gate.is_set() for gate in case.ns["controller_gates"])
    assert case.retirement.primary is primary and tuple(case.retirement.errors) == errors
    units.publish(record_property, "genuine_ack", context, ack_identity=(
        ack is record.ack, ack is first._completion.cleanup_ack, ack is first._authority.ack))
    assert ([(event, ordinal) for event, ordinal, _ in context.receiver.rows] == [(5, 1)]
            and len(context.clocks) == 1
            and context.receiver.ack_at_note == [(first, ack, ack, ack)]
            ), "TIMELINE_ACK_OBSERVATION_MISSING"


def test_timeline_normal_gate_annotations(_timeline_baseline_units, record_property):
    units = _timeline_baseline_units
    chronology = []
    gate_a = _TimelineGate(1, chronology)
    case = units.make(admission=gate_a)
    first = case.construct()
    context = units.context(case, chronology=chronology)
    units.execute("first_set", case.ns)
    assert gate_a.returned == 1 and gate_a.is_set()
    ack_first = units.run(case, case.ns["observed_close"](first))
    assert ack_first is case.ns["closes"][-1].ack is first._completion.cleanup_ack is first._authority.ack
    assert ack_first.not_started and ack_first._authority.owner is first
    assert case.ns["dispatch_turn"] == [1] and len(case.ns["controller_gates"]) == 1
    gate_b = _TimelineGate(2, chronology)
    case.admission = gate_b
    second = case.construct()  # Actual late registration sees index1 == turn1.
    assert gate_b.returned == 1 and gate_b.is_set()
    gate_c = _TimelineGate(3, chronology)
    case.admission = gate_c
    third = case.construct()
    assert not gate_c.is_set() and gate_c.returned == 0
    ack_second = units.run(case, case.ns["observed_close"](second))
    assert ack_second is case.ns["closes"][-1].ack is second._completion.cleanup_ack is second._authority.ack
    assert ack_second.not_started and ack_second._authority.owner is second
    assert case.ns["dispatch_turn"] == [2]
    assert case.ns["controller_gates"] == [gate_a, gate_b, gate_c]
    assert [gate.returned for gate in (gate_a, gate_b, gate_c)] == [1, 1, 1]
    assert all(gate.is_set() for gate in (gate_a, gate_b, gate_c))
    assert [record.actual for record in case.ns["owners"]] == [first, second, third]
    assert not case.bindings and all(owner._thread is None for owner in case.owners)
    normal = [(event, ordinal) for event, ordinal, _ in context.receiver.rows
              if event in (3, 4, 6)]
    # Each logged note must have its ORIGINAL delegate's returned marker already
    # in its snapshot, not just present eventually in a post-hoc gate flag.
    after_setters = all(
        ("setter-returned", row[1]) in snapshot
        for row, snapshot in zip(context.receiver.rows, context.receiver.setter_at_note)
        if row[0] in (3, 4, 6))
    units.publish(record_property, "normal_gates", context, ack_identity=(
        ack_first is first._authority.ack, ack_second is second._authority.ack))
    assert (normal == [(3, 1), (4, 2), (6, 3)] and after_setters
            ), "TIMELINE_NORMAL_SET_OBSERVATIONS_MISSING"


def test_timeline_healthy_io_zero(_timeline_baseline_units, record_property):
    units = _timeline_baseline_units
    case = units.make()
    owner = case.construct()
    context = units.context(case)
    units.execute("host_prefix", context.ns)
    units.execute("acceptance_prefix", case.ns)
    units.execute("first_set", case.ns)
    assert context.ns["root"] == Path("UNIT_TIMELINE_ROOT")
    assert case.ns["controller_gates"][0].is_set()
    assert owner._thread is None and not case.bindings
    calls = []
    finished = _TimelineGate(0, calls)
    outcome = {"ok": True}

    def forbidden_cleanup(*args, **kwargs):
        raise AssertionError("UNIT native cleanup sentinel invoked")

    def forbidden_proof(*args, **kwargs):
        raise AssertionError("UNIT native proof sentinel invoked")

    def record_outcome(result):
        calls.append(("record_outcome", result is namespace["result"]))

    def finish(*, native_retire, verify_native):
        assert native_retire is namespace["sdk_native_cleanup"]
        assert verify_native is namespace["sdk_native_proof"]
        calls.append(("finish", True, True))  # Identity only, never invoke.

    resources = SimpleNamespace(
        outcome=outcome, finalized=True, record_outcome=record_outcome, finish=finish)
    namespace = dict(
        result={"ok": True}, code=0, sdk_resources=resources,
        _sdk_timeline=context.receiver, sdk_native_cleanup=forbidden_cleanup,
        sdk_native_proof=forbidden_proof, finished=finished)
    units.execute("healthy_finish", namespace)
    assert calls == [("record_outcome", True), ("finish", True, True), ("setter-returned", 0)]
    assert finished.is_set() and finished.returned == 1
    assert namespace["result"] == {"ok": True} and namespace["code"] == 0
    assert resources.outcome is outcome and resources.finalized is True
    assert context.receiver.emit_calls == 0 and context.writes == []

    # Original non-target HOST prefixes and actual optional acceptance/first
    # paths also work with the existing fixture actor's absent optional attr.
    for phase in ("sdk-program-one", "sdk-retire-watchdog-race", "ordinary"):
        units.check()
        other = units.make()
        absent = units.context(other, attach=False)
        assert not hasattr(other.actor, "_sdk_timeline")
        absent.ns["PHASE"] = phase
        units.execute("host_prefix", absent.ns)
        assert absent.ns["root"] == Path("UNIT_TIMELINE_ROOT")
        assert absent.ns["_sdk_timeline"] is None
        assert absent.receiver.factory_bindings == []
        owner = other.construct()
        units.execute("acceptance_prefix", other.ns)
        units.execute("first_set", other.ns)
        assert other.ns["released_first"] == [True]
        assert other.ns["controller_gates"][0].is_set()
        assert owner._thread is None and not other.bindings
        assert absent.receiver.rows == [] and absent.receiver.emit_calls == 0
        assert absent.clocks == [] and absent.writes == []
        units.publish(record_property, "healthy_absent_" + phase, absent)
    units.publish(record_property, "healthy_finish", context)
    assert context.receiver.emit_calls == 0 and context.writes == []


def _timeline_stage_rollback(*, canonical, lifecycle, retirement):
    """Strict positional inverse to fixed4e. No filesystem or project imports."""
    import hashlib
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    raw = dict(canonical=canonical, lifecycle=lifecycle, retirement=retirement)
    assert all(type(value) is bytes for value in raw.values())
    assert sha(canonical) == _TIMELINE_ACTUAL_CANONICAL_SHA256
    restored = {}
    for name, supplied in raw.items():
        size, digest = _TIMELINE_STAGE_EXPECTED[name]
        transforms = _TIMELINE_STAGE_TRANSFORMS[name]
        assert len(transforms) == _TIMELINE_STAGE_COUNTS[name]
        previous_start, previous_stop, delta = -1, 0, 0
        inverses = []
        for start, old, new in transforms:
            assert type(start) is int and type(old) is type(new) is bytes
            assert previous_start < start and previous_stop <= start <= start + len(old) <= size
            first = start + delta
            assert first >= 0 and supplied[first:first + len(new)] == new
            inverses.append((first, first + len(new), old))
            delta += len(new) - len(old)
            previous_start, previous_stop = start, start + len(old)
        stop = size + delta
        if name == "retirement":
            tail = supplied[stop:]
            assert tail.startswith(b"\n\n# SDK_TIMELINE_STAGE_APPEND_BEGIN v1\n")
            assert tail.endswith(b"# SDK_TIMELINE_STAGE_APPEND_END v1\n")
            assert tail.count(b"# SDK_TIMELINE_STAGE_APPEND_BEGIN v1\n") == 1
            assert tail.count(b"# SDK_TIMELINE_STAGE_APPEND_END v1\n") == 1
        else:
            assert len(supplied) == stop
        value = supplied[:stop]
        assert len(value) == stop
        for first, last, original in reversed(inverses):
            assert 0 <= first <= last <= len(value)
            value = value[:first] + original + value[last:]
        assert len(value) == size and sha(value) == digest
        restored[name] = value
    return restored


def _timeline_history_inputs():
    """Read ACTUAL sources once per call; only named pure-history seams use this."""
    path = Path(__file__)
    return _timeline_stage_rollback(**_handoff_dependency_stage_restore(
        canonical=path.with_name("test_owned_sql_sdk_canonical.py").read_bytes(),
        lifecycle=path.with_name("test_sql_lifecycle_process.py").read_bytes(),
        retirement=path.read_bytes()))


_TIMELINE_ACTUAL_CANONICAL_SHA256 = '493a905b3fa99116e67bbaa0120ab0e16d85fb0256f2c364ff478742567c671e'

_TIMELINE_STAGE_EXPECTED = {'canonical': (262043, '6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06'), 'lifecycle': (242360, '156b8877c8acc57565a9d5afc92b2179c9d34eac37e24e0bb2becba4648b7ba2'), 'retirement': (554185, '523ff1dae21a6806fc61105b4830cddc8dd94b7a8608f2e5647c7168f71302a6')}

_TIMELINE_STAGE_COUNTS = {'canonical': 5, 'lifecycle': 5, 'retirement': 22}

_TIMELINE_STAGE_TRANSFORMS = {'canonical': ((156184, b'', b'    try:\n        _timeline = getattr(actor, "_sdk_timeline", None)\n        if _timeline is not None:\n            _timeline.note(2)\n    except BaseException:\n        pass\n'), (179794, b'', b'            try:\n                _timeline = getattr(actor, "_sdk_timeline", None)\n                if _timeline is not None:\n                    _timeline.note(4, actual, owners)\n            except BaseException:\n                pass\n'), (182165, b'', b'        try:\n            _timeline = getattr(actor, "_sdk_timeline", None)\n            if _timeline is not None:\n                _timeline.note(5, actual, owners)\n        except BaseException:\n            pass\n'), (182702, b'', b'                try:\n                    _timeline = getattr(actor, "_sdk_timeline", None)\n                    if _timeline is not None:\n                        _timeline.note(6, owners[dispatch_turn[0]].actual, owners)\n                except BaseException:\n                    pass\n'), (203269, b'', b'        try:\n            _timeline = getattr(actor, "_sdk_timeline", None)\n            if _timeline is not None:\n                _timeline.note(3, owners[0].actual, owners)\n        except BaseException:\n            pass\n')), 'lifecycle': ((49412, b'', b'# SDK_TIMELINE_RUNTIME_HELPER_BEGIN\n_timeline_original_deque = _timeline_original_popleft = None\ntry:\n    from collections import deque as _timeline_original_deque\n    _timeline_original_popleft = _timeline_original_deque.popleft\nexcept BaseException:\n    pass  # Unavailable capture; never retry after fixture replacements.\n\nclass _SdkTimeline:\n    """Partial observations only; original CPython3.12.13 popleft claims slots."""\n    def __init__(self, *, clock, write):\n        self._clock, self._write = clock, write\n        self._free_slots = _timeline_original_deque(range(64))\n        self._emit_token = _timeline_original_deque([0])\n        self._rows = [None] * 64\n        self._disabled = self._unavailable = self._truncated = False\n\n    def note(self, event, owner=None, registry=()):\n        try:\n            index = _timeline_original_popleft(self._free_slots)\n        except IndexError:\n            self._truncated = True\n            return  # No clock or registry work after slot exhaustion.\n        except BaseException:\n            self._unavailable = True\n            self._disabled = True\n            return\n        try:\n            if self._disabled:\n                return  # Consume this claimed slot without reuse.\n            if type(event) is not int or not 1 <= event <= 6:\n                raise ValueError\n            ordinal = 0\n            if owner is not None:\n                for position, record in enumerate(registry[:64], 1):\n                    if record.actual is owner:\n                        ordinal = position\n                        break\n                if ordinal == 0:\n                    raise ValueError\n            ns = self._clock()  # At most one attempt per unique slot.\n            if type(ns) is not int or not 0 <= ns <= 9223372036854775807:\n                raise ValueError\n            row = (event, ordinal, ns)\n            self._rows[index] = row  # Publish only a complete immutable tuple.\n        except BaseException:\n            self._unavailable = True\n            self._disabled = True  # No retry, slot reuse, recapture or flag clear.\n\n    def emit_failure(self):\n        try:\n            _timeline_original_popleft(self._emit_token)\n        except IndexError:\n            return\n        except BaseException:\n            self._unavailable = True\n            self._disabled = True\n            return\n        self._disabled = True\n        try:\n            snapshot = []\n            for index in range(64):\n                row = self._rows[index]  # Inspect each cell once, no coherent epoch.\n                if row is None:\n                    continue\n                if (type(row) is not tuple or len(row) != 3\n                        or any(type(value) is not int for value in row)\n                        or not 1 <= row[0] <= 6 or not 0 <= row[1] <= 64\n                        or not 0 <= row[2] <= 9223372036854775807):\n                    self._unavailable = True\n                    continue\n                snapshot.append(row)\n            truncated = 1 if self._truncated else 0\n            wire = (\'{"kind":"SDK_TIMELINE","header":[1,0,%d,%d],"rows":[%s]}\\n\' % (\n                truncated, len(snapshot),\n                ",".join("[%d,%d,%d]" % row for row in snapshot))).encode("ascii")\n            if len(wire) <= 4096 and self._write is not None:\n                self._write(2, wire)  # One token, one attempt; never repair a short write.\n        except BaseException:\n            self._unavailable = True\n            self._disabled = True\n# SDK_TIMELINE_RUNTIME_HELPER_END\n'), (99367, b'', b'    _sdk_timeline = None\n    if PHASE == "sdk-positive-two":\n        try:\n            _sdk_timeline = _SdkTimeline(\n                clock=_boundary_original_clock if _boundary_original_ready else None,\n                write=_boundary_original_write if _boundary_original_ready else None)\n            _sdk_timeline.note(1)\n        except BaseException:\n            pass\n'), (111575, b'6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06', b'493a905b3fa99116e67bbaa0120ab0e16d85fb0256f2c364ff478742567c671e'), (195710, b'', b'            try:\n                if _sdk_timeline is not None:\n                    actor._sdk_timeline = _sdk_timeline\n            except BaseException:\n                pass\n'), (222917, b'', b'            try:\n                if (_sdk_timeline is not None\n                        and ((sdk_resources.outcome or {}).get("ok") is not True\n                             or not sdk_resources.finalized)):\n                    _sdk_timeline.emit_failure()\n            except BaseException:\n                pass\n')), 'retirement': ((412231, b'    lines = trusted.source.splitlines(keepends=True)\n', b'    _history_source = _timeline_history_inputs()["canonical"].decode()\n    _history_regions = _sibling_cleanup_regions(_history_source, ast.parse(_history_source))\n    lines = _history_source.splitlines(keepends=True)\n'), (412284, b'    for region in sorted(trusted.regions.values(), key=lambda item: item.first, reverse=True):\n        lines[region.first - 1:region.last] = ["RESOURCE_REGION\\n"]\n', b'    for region in sorted(_history_regions.values(), key=lambda item: item.first, reverse=True):\n        lines[region.first - 1:region.last] = ["RESOURCE_REGION\\n"]\n'), (431044, b'    lines = feature.source.splitlines(keepends=True)\n', b'    _history_source = _timeline_history_inputs()["canonical"].decode()\n    _history_tree = ast.parse(_history_source)\n    _history_diagnostic, = [node for node in _history_tree.body\n                            if getattr(node, "name", None) == "_sdk_sibling_error_diagnostic"]\n    lines = _history_source.splitlines(keepends=True)\n'), (431097, b'    lines[diagnostic.lineno - 1:diagnostic.end_lineno] = ["DIAGNOSTIC_FUNCTION\\n"]\n', b'    lines[_history_diagnostic.lineno - 1:_history_diagnostic.end_lineno] = ["DIAGNOSTIC_FUNCTION\\n"]\n'), (455970, b'    for line in source.splitlines(keepends=True):\n', b'    for line in _timeline_history_inputs()["lifecycle"].decode().splitlines(keepends=True):\n'), (456478, b'hashlib.sha256(Path(__file__).read_bytes()[:431324])', b'hashlib.sha256(_timeline_history_inputs()["retirement"][:431324])'), (457171, b'hashlib.sha256(path.with_name(name).read_bytes())', b'hashlib.sha256(_timeline_history_inputs()["canonical"]\n                              if name == "test_owned_sql_sdk_canonical.py"\n                              else path.with_name(name).read_bytes())'), (474728, b'', b'    _history_retained, _history_old, _history_new, _history_all_removed = (\n        _guardian_budget_unit_regions(_timeline_history_inputs()["lifecycle"].decode()))\n'), (474782, b'len(retained.encode())', b'len(_history_retained.encode())'), (474826, b'hashlib.sha256(retained.encode())', b'hashlib.sha256(_history_retained.encode())'), (474964, b'hashlib.sha256(all_removed.encode())', b'hashlib.sha256(_history_all_removed.encode())'), (475404, b'hashlib.sha256(Path(__file__).read_bytes()[:length])', b'hashlib.sha256(Path(__file__).read_bytes()[:length] if length == 400464\n                              else _timeline_history_inputs()["retirement"][:length])'), (475751, b'hashlib.sha256(path.with_name(name).read_bytes())', b'hashlib.sha256(_timeline_history_inputs()["canonical"]\n                              if name == "test_owned_sql_sdk_canonical.py"\n                              else path.with_name(name).read_bytes())'), (498277, b'', b'    _history_retained, _history_old, _history_new, _history_all_removed = (\n        _host_budget_unit_regions(_timeline_history_inputs()["lifecycle"].decode()))\n'), (498324, b'len(retained.encode())', b'len(_history_retained.encode())'), (498368, b'hashlib.sha256(retained.encode())', b'hashlib.sha256(_history_retained.encode())'), (498506, b'hashlib.sha256(all_removed.encode())', b'hashlib.sha256(_history_all_removed.encode())'), (498930, b'    test_bytes = Path(__file__).read_bytes()\n', b'    test_bytes = _timeline_history_inputs()["retirement"]\n'), (529859, b'    prefix = bytearray(path.read_bytes()[:502817])\n', b'    prefix = bytearray(_timeline_history_inputs()["retirement"][:502817])\n'), (530408, b'    lifecycle = bytearray(path.with_name("test_sql_lifecycle_process.py").read_bytes())\n', b'    lifecycle = bytearray(_timeline_history_inputs()["lifecycle"])\n'), (530834, b'    canonical = path.with_name("test_owned_sql_sdk_canonical.py").read_text()\n', b'    canonical = _timeline_history_inputs()["canonical"].decode()\n'), (544984, b'', b'    _timeline_inputs = _timeline_stage_rollback(\n        canonical=canonical, lifecycle=lifecycle, retirement=retirement)\n    canonical, lifecycle, retirement = (\n        _timeline_inputs["canonical"], _timeline_inputs["lifecycle"], _timeline_inputs["retirement"])\n'))}




# STAGE2: lazy actual-helper units. No code below runs during assembly/compile.
class _TimelineUnitThreads:
    """At most two TEST-ONLY workers, reused; every wait/join uses original UNIT3."""

    def __init__(self, deadline):
        import queue
        self.queue = queue.Queue()
        self.deadline = deadline
        self.stop = object()
        self.releases, self.jobs, self.workers = [], [], []
        for _ in range(2):
            worker = threading.Thread(target=self._work, daemon=False)
            self.workers.append(worker)
            worker.start()

    def remaining(self):
        return max(0, self.deadline - time.monotonic())

    def _work(self):
        import queue
        while True:
            try:
                item = self.queue.get(timeout=self.remaining())
            except queue.Empty:
                return
            if item is self.stop:
                return
            callback, job = item
            try:
                callback()
            except BaseException as error:
                job.errors.append(error)
            finally:
                job.done.set()

    def event(self):
        event = threading.Event()
        self.releases.append(event)
        return event

    def submit(self, callback):
        job = SimpleNamespace(done=threading.Event(), errors=[])
        self.jobs.append(job)
        self.queue.put((callback, job))
        return job

    def wait(self, event):
        assert event.wait(self.remaining()), "timeline TEST-ONLY wait exhausted UNIT3"

    def result(self, job):
        self.wait(job.done)
        assert job.errors == [], "timeline TEST-ONLY worker failed"

    def close(self):
        for event in self.releases:
            event.set()
        for _ in self.workers:
            self.queue.put(self.stop)
        for worker in self.workers:
            worker.join(timeout=self.remaining())
        assert all(not worker.is_alive() for worker in self.workers)
        assert all(job.done.is_set() and not job.errors for job in self.jobs)
        assert time.monotonic() < self.deadline, "timeline TEST-ONLY joins exhausted UNIT3"


@pytest.fixture
def _timeline_feature_units(_timeline_baseline_units, monkeypatch):
    """Lazy, actual helper only. Never a module import or missing-helper fallback."""
    import collections
    units = _timeline_baseline_units
    units.check()
    case = units.make()
    context = units.context(case, attach=False)
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    outer = ast.parse(path.read_text())
    assignment, = [
        node for node in outer.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)]
    guest = ast.literal_eval(assignment.value)
    tree = ast.parse(guest, filename=str(path))
    index, = [
        index for index, node in enumerate(tree.body) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_timeline_original_deque"
                for target in node.targets)]
    helper_nodes = tree.body[index:index + 3]
    assert (len(helper_nodes) == 3 and isinstance(helper_nodes[1], ast.Try)
            and isinstance(helper_nodes[2], ast.ClassDef)
            and helper_nodes[2].name == "_SdkTimeline"), "TIMELINE_FEATURE_SETUP"
    env, = [node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ENV"
                    for target in node.targets)]
    assert helper_nodes[-1].end_lineno < env.lineno
    assert context.ns["_boundary_original_ready"] is True
    namespace = dict(context.ns)
    # Actual class and original deque capture, selected from actual guest bytes.
    exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), str(path), "exec"), namespace)
    cls = namespace["_SdkTimeline"]
    original_deque = collections.deque
    original_popleft = original_deque.popleft
    assert namespace["_timeline_original_deque"] is original_deque
    assert namespace["_timeline_original_popleft"] is original_popleft
    assert cls.__init__.__code__.co_filename == str(path)

    host, = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "host_main"]
    attachment = []
    for parent in ast.walk(host):
        for _, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            for position, node in enumerate(value):
                if (isinstance(node, ast.Return) and isinstance(node.value, ast.Await)
                        and isinstance(node.value.value, ast.Call)
                        and isinstance(node.value.value.func, ast.Name)
                        and node.value.value.func.id == "_run_sdk_host_case"):
                    attachment.append(value[position - 1])
    attach_node, = attachment
    assert isinstance(attach_node, ast.Try)
    assert any(isinstance(node, ast.Attribute) and node.attr == "_sdk_timeline"
               and isinstance(node.ctx, ast.Store) for node in ast.walk(attach_node))
    default = object()
    pool_holder = []

    def pool():
        units.check()
        if not pool_holder:
            pool_holder.append(_TimelineUnitThreads(units.deadline))
        return pool_holder[0]

    def record(*, clock=default, writer=default, trace=None):
        units.check()
        writes = []

        def write(fd, raw):
            units.check()
            writes.append((fd, raw))
            if trace is not None:
                trace.append("write")
            if writer is not default:
                return writer(fd, raw)
            return len(raw)

        value = cls(
            clock=namespace["_boundary_original_clock"] if clock is default else clock,
            write=None if writer is None else write)
        assert type(value._free_slots) is type(value._emit_token) is original_deque
        return SimpleNamespace(recorder=value, writes=writes)

    def attach(target_case, recorder):
        units.check()
        attach_ns = dict(actor=target_case.actor, _sdk_timeline=recorder)
        exec(compile(ast.Module(body=[attach_node], type_ignores=[]),
                     str(path), "exec"), attach_ns)
        assert target_case.actor._sdk_timeline is recorder
        units.check()

    def envelope(state, index=0):
        units.check()
        fd, raw = state.writes[index]
        assert type(fd) is int and fd == 2
        assert type(raw) is bytes and len(raw) <= 4096
        data = json.loads(raw)
        assert set(data) == {"kind", "header", "rows"} and data["kind"] == "SDK_TIMELINE"
        header = data["header"]
        assert (type(header) is list and len(header) == 4
                and all(type(value) is int for value in header))
        assert header[:2] == [1, 0] and header[2] in (0, 1)
        assert header[3] == len(data["rows"]) <= 64
        for row in data["rows"]:
            assert type(row) is list and len(row) == 3
            assert all(type(value) is int for value in row)
            assert 1 <= row[0] <= 6 and 0 <= row[1] <= 64 and 0 <= row[2] <= 2**63 - 1
        for canary in (b"UNIT_TIMELINE_PRIVATE", b"SQL", b"/Users/", b"trace",
                       b"payload", b"pid", b"error", b"fd"):
            assert canary not in raw
        return data

    def finish_unit(recorder, *, ok=False, finalized=True, trace=None,
                    finish_error=None, outcome=None):
        units.check()
        trace = [] if trace is None else trace

        def forbidden_cleanup(*args, **kwargs):
            raise AssertionError("UNIT native cleanup sentinel invoked")

        def forbidden_proof(*args, **kwargs):
            raise AssertionError("UNIT native proof sentinel invoked")

        class Resources:
            def __init__(self):
                self.outcome = {"ok": ok} if outcome is None else outcome

            @property
            def finalized(self):
                trace.append("finalized")
                return finalized

            def record_outcome(self, result):
                assert result is result_ns["result"]
                trace.append("record")

            def finish(self, *, native_retire, verify_native):
                assert native_retire is forbidden_cleanup
                assert verify_native is forbidden_proof
                trace.append("finish")
                if finish_error is not None:
                    raise finish_error

        resources = Resources()

        class Finished:
            def set(self):
                trace.append("finished")

        result_ns = dict(
            result={"ok": ok}, code=0, sdk_resources=resources,
            _sdk_timeline=recorder, sdk_native_cleanup=forbidden_cleanup,
            sdk_native_proof=forbidden_proof, finished=Finished())
        return SimpleNamespace(ns=result_ns, resources=resources, trace=trace)

    def location(error, node):
        tb = error.__traceback__
        while tb.tb_next is not None:
            tb = tb.tb_next
        assert tb.tb_frame.f_code.co_filename == str(Path(__file__))
        assert tb.tb_lineno == node.lineno

    def sources():
        units.check()
        value = _close_guard_stage_sources()  # Existing ACTUAL-three reader.
        units.check()
        return value

    feature = SimpleNamespace(
        units=units, case=case, context=context, namespace=namespace, cls=cls,
        tree=tree, guest=guest, host=host, path=path, record=record, attach=attach,
        envelope=envelope, finish_unit=finish_unit, pool=pool, location=location,
        sources=sources, monkeypatch=monkeypatch, check=units.check,
        original_deque=original_deque, original_popleft=original_popleft)
    try:
        yield feature
    finally:
        if pool_holder:
            pool_holder[0].close()
        assert case.core._CreatorPopen.__init__ is context.creator_denial
        units.check()


def test_timeline_failure_emission_once(_timeline_feature_units, record_property):
    f = _timeline_feature_units
    # The actual class, not Stage1's inert factory, drives real source anchors.
    namespace = dict(f.context.ns, _SdkTimeline=f.cls)
    f.units.execute("host_prefix", namespace)
    recorder = namespace["_sdk_timeline"]
    assert type(recorder) is f.cls and recorder._clock is f.context.clock
    assert recorder._write is f.context.write
    f.attach(f.case, recorder)
    owner = f.case.construct()
    f.units.execute("acceptance_prefix", f.case.ns)
    f.units.execute("first_set", f.case.ns)
    assert [row[:2] for row in recorder._rows if row is not None] == [
        (1, 0), (2, 0), (3, 1)]
    assert owner._thread is None and f.context.replaced == []

    for ok, finalized in ((False, True), (True, False)):
        f.check()
        trace = []
        state = f.record(trace=trace)
        state.recorder.note(1)
        unit = f.finish_unit(state.recorder, ok=ok, finalized=finalized, trace=trace)
        if finalized:
            f.units.execute("healthy_finish", unit.ns)
            assert trace[-1] == "finished" and unit.ns["code"] == 1
        else:
            with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
                f.units.execute("healthy_finish", unit.ns)
            assert "finished" not in trace
        assert len(state.writes) == 1
        assert trace.index("finish") < trace.index("write")
        assert trace.index("write") < len(trace) - 1
        assert f.envelope(state)["header"] == [1, 0, 0, 1]
        state.recorder.emit_failure()
        assert len(state.writes) == 1

    healthy = f.record()
    healthy.recorder.note(1)
    unit = f.finish_unit(healthy.recorder, ok=True, finalized=True)
    f.units.execute("healthy_finish", unit.ns)
    assert healthy.writes == [] and unit.trace[-1] == "finished"
    missing = f.record(writer=None)
    unit = f.finish_unit(missing.recorder)
    f.units.execute("healthy_finish", unit.ns)
    assert missing.writes == []
    original = RuntimeError("UNIT original finish failure")
    state = f.record()
    unit = f.finish_unit(state.recorder, finish_error=original)
    with pytest.raises(RuntimeError) as caught:
        f.units.execute("healthy_finish", unit.ns)
    assert caught.value is original and state.writes == [] and "finished" not in unit.trace
    # Finalized assertion is ORIGINAL source and remains active even without metadata.
    unit = f.finish_unit(None, ok=True, finalized=False)
    with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
        f.units.execute("healthy_finish", unit.ns)
    record_property("timeline_failure_source", str(f.path))
    f.check()


def test_timeline_bounds_privacy_and_unavailable(_timeline_feature_units):
    f = _timeline_feature_units
    comparisons, clocks = [], []
    owner = object()

    class Record:
        def __init__(self, value):
            self.value = value

        @property
        def actual(self):
            comparisons.append(None)
            return self.value

        def __repr__(self):
            raise AssertionError("UNIT_TIMELINE_PRIVATE SQL /Users/payload")

    registry = [Record(object()) for _ in range(63)] + [Record(owner)]

    def clock():
        clocks.append(None)
        return 2**63 - 1

    state = f.record(clock=clock)
    for _ in range(64):
        f.check()
        state.recorder.note(6, owner, registry)
    assert len(clocks) == 64 and len(comparisons) == 4096
    before = tuple(state.recorder._rows)
    state.recorder.note(6, owner, registry)
    assert len(clocks) == 64 and len(comparisons) == 4096
    assert tuple(state.recorder._rows) == before and state.recorder._truncated is True
    state.recorder.emit_failure()
    data = f.envelope(state)
    assert data["header"] == [1, 0, 1, 64] and all(row == [6, 64, 2**63 - 1] for row in data["rows"])

    class IntSubclass(int):
        pass

    for value in (True, IntSubclass(1), -1, 2**63, 1.5,
                  "UNIT_TIMELINE_PRIVATE", object()):
        f.check()
        state = f.record(clock=lambda: value)
        state.recorder.note(1)
        assert state.recorder._disabled and state.recorder._unavailable
        assert all(row is None for row in state.recorder._rows)
        state.recorder.emit_failure()
        assert f.envelope(state)["header"] == [1, 0, 0, 0]
    for event in (True, IntSubclass(1), 0, 7):
        state = f.record()
        state.recorder.note(event)
        assert state.recorder._disabled and state.recorder._unavailable
    state = f.record(clock=lambda: (_ for _ in ()).throw(
        AssertionError("clock reached for unmapped owner")))
    state.recorder.note(1, object(), registry)
    assert state.recorder._disabled and state.recorder._unavailable

    import collections
    redirected = []

    def forbidden(*args, **kwargs):
        redirected.append(True)
        raise AssertionError("UNIT public deque recaptured")

    with f.monkeypatch.context() as patch:
        patch.setattr(collections, "deque", forbidden)
        state = f.record()
        state.recorder.note(1)
        state.recorder.emit_failure()
        assert f.envelope(state)["header"] == [1, 0, 0, 1]
        assert f.namespace["_timeline_original_deque"] is f.original_deque
        assert f.namespace["_timeline_original_popleft"] is f.original_popleft
    assert redirected == []

    # Only two test workers for the ENTIRE case, reused for the in-flight job.
    pool = f.pool()
    entered = [pool.event(), pool.event()]
    release = [pool.event(), pool.event()]
    claimed = []

    def held_clock():
        index = len(claimed)
        claimed.append(index)
        entered[index].set()
        pool.wait(release[index])
        return 200 if index == 0 else 100

    state = f.record(clock=held_clock)
    try:
        first = pool.submit(lambda: state.recorder.note(1))
        pool.wait(entered[0])
        second = pool.submit(lambda: state.recorder.note(2))
        pool.wait(entered[1])
        release[1].set()
        pool.result(second)
        assert state.recorder._rows[0] is None
        assert state.recorder._rows[1] == (2, 0, 100)
        release[0].set()
        pool.result(first)
        assert state.recorder._rows[:2] == [(1, 0, 200), (2, 0, 100)]
        state.recorder.emit_failure()
        assert f.envelope(state)["rows"] == [[1, 0, 200], [2, 0, 100]]
    finally:
        for event in release:
            event.set()

    calls = []

    def reentrant_clock():
        position = len(calls)
        calls.append(position)
        state.recorder.note(2)  # Recursion stops at the original64 claims.
        return position

    state = f.record(clock=reentrant_clock)
    state.recorder.note(1)
    assert calls == list(range(64)) and state.recorder._truncated
    assert len([row for row in state.recorder._rows if row is not None]) == 64
    state.recorder.emit_failure()
    assert f.envelope(state)["header"] == [1, 0, 1, 64]

    entered_one, release_one = pool.event(), pool.event()
    calls = []

    def inflight_clock():
        position = len(calls)
        calls.append(position)
        if position == 0:
            entered_one.set()
            pool.wait(release_one)
        return position

    state = f.record(clock=inflight_clock)
    try:
        pending = pool.submit(lambda: state.recorder.note(1))
        pool.wait(entered_one)
        state.recorder.note(2)
        state.recorder.emit_failure()
        wire = state.writes[0][1]
        assert f.envelope(state)["rows"] == [[2, 0, 1]]
        assert f.envelope(state)["header"] == [1, 0, 0, 1]
        release_one.set()
        pool.result(pending)
        assert state.recorder._rows[:2] == [(1, 0, 0), (2, 0, 1)]
        state.recorder.emit_failure()
        assert len(state.writes) == 1 and state.writes[0][1] is wire
    finally:
        release_one.set()
    f.check()


def _timeline_original_release_control(f):
    """Actual unchanged release function + actual intent/gate class, no SDK work."""
    units = f.units
    chronology = []
    first_gate, second_gate = _TimelineGate(1, chronology), _TimelineGate(2, chronology)
    case = units.make(admission=first_gate)
    first = case.construct()
    case.admission = second_gate
    second = case.construct()
    acks = units.public_acks(case, (first, second))
    state = f.record()
    f.attach(case, state.recorder)
    gates_node, = [node for node in f.tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "_ObservedTestGates"]
    intents, = [node for node in ast.walk(f.host)
                if isinstance(node, ast.FunctionDef) and node.name == "ensure_sdk_intents"]
    release, = [node for node in ast.walk(f.host)
                if isinstance(node, ast.FunctionDef) and node.name == "release_sdk_controllers"]
    namespace = dict(
        threading=threading, sdk_resources=case.retirement,
        owners=case.actor.owners, gates=case.actor.gates)
    exec(compile(ast.Module(body=[gates_node, intents, release], type_ignores=[]),
                 str(f.path), "exec"), namespace)
    gate_inventory = namespace["_ObservedTestGates"](
        ensure_intents=namespace["ensure_sdk_intents"])
    namespace["sdk_test_gates"] = gate_inventory
    namespace["release_sdk_controllers"]()
    receipts = tuple(case.retirement.cancel_receipts)
    assert len(receipts) == 2
    assert all(receipt.status == "already_completed" for _, receipt in receipts)
    assert first_gate.returned == second_gate.returned == 1
    assert first._authority.ack is acks[first] and second._authority.ack is acks[second]
    assert gate_inventory.rows == [] and gate_inventory.retiring
    namespace["release_sdk_controllers"]()
    assert tuple(case.retirement.cancel_receipts) == receipts
    assert first_gate.returned == second_gate.returned == 1
    assert all(row is None for row in state.recorder._rows) and state.writes == []
    f.check()


def _timeline_raising_setter_controls(f):
    units = f.units
    for site in ("first", "late", "ack"):
        f.check()
        failure = RuntimeError("UNIT original setter failure")

        class RaisingGate(_TimelineGate):
            def set(self):
                raise failure  # Declared UNIT setter, original exception object.

        chronology = []
        a, b = _TimelineGate(1, chronology), _TimelineGate(2, chronology)
        if site == "first":
            a = RaisingGate(1, chronology)
        else:
            b = RaisingGate(2, chronology)
        case = units.make(admission=a)
        first = case.construct()
        state = f.record()
        f.attach(case, state.recorder)
        if site == "first":
            with pytest.raises(RuntimeError) as caught:
                units.execute("first_set", case.ns)
            assert not any(row is not None and row[0] == 3 for row in state.recorder._rows)
        elif site == "late":
            units.execute("first_set", case.ns)
            units.run(case, case.ns["observed_close"](first))
            case.admission = b
            with pytest.raises(RuntimeError) as caught:
                case.construct()
            assert not any(row is not None and row[0] == 4 for row in state.recorder._rows)
        else:
            case.admission = b
            second = case.construct()
            acks = units.public_acks(case, (first, second))
            units.execute("first_set", case.ns)
            with pytest.raises(RuntimeError) as caught:
                units.run(case, case.ns["observed_close"](first))
            assert case.ns["closes"][-1].ack is acks[first]
            assert not any(row is not None and row[0] == 6 for row in state.recorder._rows)
        assert caught.value is failure
        assert all(owner._thread is None for owner in case.constructed)


def test_timeline_preserves_original_failure(_timeline_feature_units):
    f = _timeline_feature_units
    units, case = f.units, f.case
    owner = case.construct()
    acks = units.public_acks(case, (owner,))
    primary = AssertionError("UNIT original primary")
    case.retirement.fail("unit-marker", primary)
    ledger, outcome = case.retirement.errors, case.retirement.outcome
    entries = tuple(ledger)
    safe, finalized = case.retirement.safe_emissions, case.retirement.finalized

    def unchanged():
        assert case.retirement.primary is primary and case.retirement.errors is ledger
        assert tuple(ledger) == entries and ledger[0][1] is primary
        assert case.retirement.outcome is outcome
        assert case.retirement.safe_emissions == safe == 0
        assert case.retirement.finalized is finalized is False
        assert owner._authority.ack is owner._completion.cleanup_ack is acks[owner]

    def fault(*args, **kwargs):
        raise RuntimeError("UNIT metadata fault")

    for mode in ("clock", "validation", "claim-error", "claim-type", "collection",
                 "encoding-preparation", "writer", "writer-encoding", "short"):
        f.check()
        state = f.record(
            clock=fault if mode == "clock" else (lambda: True) if mode == "validation" else f.context.clock,
            writer=fault if mode == "writer" else (
                (lambda fd, raw: (_ for _ in ()).throw(
                    UnicodeEncodeError("ascii", "UNIT", 0, 1, "UNIT writer encoding failure")))
                if mode == "writer-encoding" else (lambda fd, raw: 0) if mode == "short"
                else (lambda fd, raw: len(raw))))
        with f.monkeypatch.context() as patch:
            if mode in ("claim-error", "claim-type"):
                patch.setitem(f.namespace, "_timeline_original_popleft",
                              fault if mode == "claim-error" else lambda value: "invalid-slot")
            state.recorder.note(1)
        if mode in ("clock", "validation", "claim-error", "claim-type"):
            assert state.recorder._disabled and state.recorder._unavailable
            calls = len(f.context.clocks)
            state.recorder.note(2)
            assert len(f.context.clocks) == calls
        if mode == "collection":
            class BrokenRows:
                def __getitem__(self, index):
                    fault()
            state.recorder._rows = BrokenRows()
        with f.monkeypatch.context() as patch:
            if mode == "encoding-preparation":
                # Fail the original schema/wire preparation dependency, not a
                # copied/replaced encoder or a claim about str.encode internals.
                patch.setitem(f.namespace, "any", fault)
            unit = f.finish_unit(
                state.recorder, finalized=False, outcome=outcome)
            with pytest.raises(AssertionError, match="SDK_PHYSICAL_PROOF_MISSING"):
                units.execute("healthy_finish", unit.ns)
        attempts = len(state.writes)
        state.recorder.emit_failure()
        assert len(state.writes) == attempts <= 1
        unchanged()

    # Lookup/call failures in ACTUAL optional source paths, no code replacement.
    class LookupFault:
        def __getattr__(self, name):
            if name == "_sdk_timeline":
                fault()
            return getattr(case.actor, name)

    for mode in ("lookup", "call"):
        state = f.record()
        if mode == "call":
            state.recorder.note = fault  # Explicit injected receiver-call fault.
            f.attach(case, state.recorder)
            case.ns["actor"] = case.actor
        else:
            case.ns["actor"] = LookupFault()
        units.execute("acceptance_prefix", case.ns)
        units.execute("first_set", case.ns)
        unchanged()
    case.ns["actor"] = case.actor

    # One pool, two TEST-ONLY workers total, reused for all writer modes.
    pool = f.pool()
    for mode in ("ok", "throw", "short"):
        f.check()
        entered, release = pool.event(), pool.event()
        reentries = []
        state = None

        def writer(fd, raw):
            reentries.append(True)
            state.recorder.emit_failure()  # Reentrant token claimant, no retry.
            entered.set()
            pool.wait(release)
            if mode == "throw":
                raise primary
            return 0 if mode == "short" else len(raw)

        state = f.record(writer=writer)
        state.recorder.note(1)
        try:
            first = pool.submit(state.recorder.emit_failure)
            pool.wait(entered)
            second = pool.submit(state.recorder.emit_failure)
            pool.result(second)
            assert len(state.writes) == 1 and reentries == [True]
            release.set()
            pool.result(first)
            state.recorder.emit_failure()
            assert len(state.writes) == 1
            assert f.envelope(state)["header"] == [1, 0, 0, 1]
        finally:
            release.set()
        unchanged()

    _timeline_raising_setter_controls(f)
    _timeline_original_release_control(f)
    unchanged()
    # An original finish exception still propagates unchanged.
    state = f.record(writer=fault)
    unit = f.finish_unit(state.recorder, finish_error=primary)
    with pytest.raises(AssertionError) as caught:
        units.execute("healthy_finish", unit.ns)
    assert caught.value is primary and state.writes == []
    unchanged()
    f.check()


def test_timeline_exact_stage_rollback(_timeline_feature_units):
    f = _timeline_feature_units
    import hashlib
    actual = _handoff_dependency_stage_restore(**f.sources())
    restored = _timeline_stage_rollback(**actual)
    assert set(restored) == {"canonical", "lifecycle", "retirement"}
    for name, (length, digest) in _TIMELINE_STAGE_EXPECTED.items():
        assert len(restored[name]) == length
        assert hashlib.sha256(restored[name]).hexdigest() == digest
    assert _timeline_history_inputs() == restored  # Actual reader, not baseline substitute.
    assert _TIMELINE_STAGE_COUNTS == {"canonical": 5, "lifecycle": 5, "retirement": 22}
    assert sum(_TIMELINE_STAGE_COUNTS.values()) == 32
    for name, transforms in _TIMELINE_STAGE_TRANSFORMS.items():
        value = restored[name]
        for start, old, new in reversed(transforms):
            assert value[start:start + len(old)] == old
            value = value[:start] + new + value[start + len(old):]
        if name == "retirement":
            assert actual[name].startswith(value)
            tail = actual[name][len(value):]
            assert tail.startswith(b"\n\n# SDK_TIMELINE_STAGE_APPEND_BEGIN v1\n")
            assert tail.endswith(b"# SDK_TIMELINE_STAGE_APPEND_END v1\n")
        else:
            assert value == actual[name]
    f.check()


def test_timeline_rollback_rejects_unlisted_changes(_timeline_feature_units):
    f = _timeline_feature_units
    actual = _handoff_dependency_stage_restore(**f.sources())
    _timeline_stage_rollback(**actual)  # Positive FIRST, then behavioral negatives.
    for name in actual:
        for old, new in ((b"SOURCE-ONLY", b"SOURCE_ONLY"),) if name == "retirement" else (
                (b'"""', b"'''"),):
            # Same-length syntactically valid comment/docstring mutation; the
            # actual fixed-prefix digest, not Python parser failure, rejects it.
            raw = actual[name]
            if name == "retirement":
                assert raw.startswith(b'"""SOURCE-ONLY')
                changed = raw.replace(old, new, 1)
            else:
                # A newline inside the existing initial source text changes no
                # code token. Insertion is still unlisted and must be rejected.
                changed = b"\n" + raw
            ast.parse(changed)
            with pytest.raises(AssertionError):
                _timeline_stage_rollback(**dict(actual, **{name: changed}))
        raw = bytearray(actual[name])
        raw[100] ^= 1  # Independent old-byte change, never written to disk.
        with pytest.raises(AssertionError):
            _timeline_stage_rollback(**dict(actual, **{name: bytes(raw)}))

    for name, transforms in _TIMELINE_STAGE_TRANSFORMS.items():
        first = transforms[0]
        start, old, new = first
        for altered in (
                transforms[1:], (first,) + transforms,
                ((start + 1, old, new),) + transforms[1:],
                ((start, old, new + b" "),) + transforms[1:],
                (first, (start, b"x", b"x")) + transforms[2:]):
            with f.monkeypatch.context() as patch:
                patch.setitem(globals(), "_TIMELINE_STAGE_TRANSFORMS",
                              dict(_TIMELINE_STAGE_TRANSFORMS, **{name: altered}))
                with pytest.raises(AssertionError):
                    _timeline_stage_rollback(**actual)
    for altered in (
            actual["retirement"].replace(b"# SDK_TIMELINE_STAGE_APPEND_END v1\n", b"", 1),
            actual["retirement"] + b"# unlisted after tail\n",
            actual["retirement"].replace(b"# SDK_TIMELINE_STAGE_APPEND_BEGIN v1\n", b"", 1)):
        with pytest.raises(AssertionError):
            _timeline_stage_rollback(**dict(actual, retirement=altered))
    # Mutate a real timing byte as well as old source and inverse data.
    start, _, new = _TIMELINE_STAGE_TRANSFORMS["canonical"][0]
    changed = bytearray(actual["canonical"])
    changed[start + new.index(b".note(2)")] ^= 1
    with pytest.raises(AssertionError):
        _timeline_stage_rollback(**dict(actual, canonical=bytes(changed)))
    f.check()


def _timeline_actual_ast_controls(f, actual_lifecycle):
    """Execute unchanged original comparison statements with ACTUAL inputs."""
    import copy
    import textwrap
    path = Path(__file__)
    source = path.read_text()
    tree = ast.parse(source)

    def test_node(name):
        node, = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == name]
        return node

    def run(nodes, namespace):
        f.check()
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        f.check()

    def reject(nodes, namespace, assertion):
        with pytest.raises(AssertionError) as caught:
            run(nodes, namespace)
        f.location(caught.value, assertion)

    guardian = test_node("test_guardian_budget_source_contract")
    start, = [index for index, node in enumerate(guardian.body)
              if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "additions" for t in node.targets)]
    stop, = [index for index, node in enumerate(guardian.body)
             if isinstance(node, ast.Assert)
             and ast.get_source_segment(source, node).startswith(
                 "assert ast.dump(original_watchdog) == ast.dump(expected_watchdog)")]
    nodes = guardian.body[start:stop + 1]
    retained, old, new, removed = _guardian_budget_unit_regions(actual_lifecycle.decode())
    assert len(old) == 9 and len(new) == 3
    feature = _guardian_budget_unit_feature()
    environment = dict(ast=ast, textwrap=textwrap, feature=feature, new=new, retained=retained)
    run(nodes, dict(environment))
    mutated = copy.copy(feature)
    mutated.watchdog = copy.deepcopy(feature.watchdog)
    mutated.watchdog.body.append(ast.Pass())
    reject(nodes, dict(environment, feature=mutated), guardian.body[stop])
    changed = list(new)
    assert changed[2].count("_guardian_budget_diagnostic(ready, safety)") == 1
    changed[2] = changed[2].replace(
        "_guardian_budget_diagnostic(ready, safety)", "_guardian_budget_diagnostic(safety, ready)")
    call_assert, = [node for node in nodes if isinstance(node, ast.Assert)
                   and ast.get_source_segment(source, node).startswith("assert ast.dump(call) ==")]
    reject(nodes, dict(environment, new=changed), call_assert)

    host = test_node("test_host_budget_source_contract")
    start, = [index for index, node in enumerate(host.body)
              if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "outer" for t in node.targets)]
    stop, = [index for index, node in enumerate(host.body)
             if isinstance(node, ast.Assert)
             and ast.get_source_segment(source, node).startswith(
                 "assert ast.dump(exception) == ast.dump(original_outer.handlers[0].body[0])")]
    nodes = host.body[start:stop + 1]
    retained, old, new, removed = _host_budget_unit_regions(actual_lifecycle.decode())
    assert len(old) == 9 and len(new) == 3
    feature = _host_budget_unit_feature()
    environment = dict(ast=ast, feature=feature, retained=retained)
    run(nodes, dict(environment))
    mutated = copy.copy(feature)
    mutated.watchdog = copy.deepcopy(feature.watchdog)
    mutated.watchdog.body.append(ast.Pass())
    watchdog_assert, = [node for node in nodes if isinstance(node, ast.Assert)
                        and ast.get_source_segment(source, node).startswith(
                            "assert ast.dump(watchdog) == ast.dump(original_watchdog)")]
    reject(nodes, dict(environment, feature=mutated), watchdog_assert)
    mutated = copy.copy(feature)
    mutated.exception_sdk = copy.deepcopy(feature.exception_sdk)
    mutated.exception_sdk.body.append(ast.Pass())
    reject(nodes, dict(environment, feature=mutated), host.body[stop])
    f.check()


def test_timeline_recursive_history_and_actual_runtime_pin(_timeline_feature_units):
    f = _timeline_feature_units
    import hashlib
    actual = f.sources()

    def actual_pin(inputs):
        digest = hashlib.sha256(inputs["canonical"]).hexdigest()
        assert digest == _TIMELINE_ACTUAL_CANONICAL_SHA256
        module = ast.parse(inputs["lifecycle"])
        assignment, = [node for node in module.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "_OWNED_GUEST_PROBE"
                               for t in node.targets)]
        guest = ast.literal_eval(assignment.value)
        node, = [node for node in ast.walk(ast.parse(guest)) if isinstance(node, ast.Assert)
                 and isinstance(node.test, ast.Compare)
                 and isinstance(node.test.left, ast.Call)
                 and isinstance(node.test.left.func, ast.Attribute)
                 and node.test.left.func.attr == "hexdigest"
                 and isinstance(node.test.left.func.value, ast.Call)
                 and any(isinstance(child, ast.Name) and child.id == "_boundary_canonical_source"
                         for child in ast.walk(node.test.left))]
        assert len(node.test.comparators) == 1
        assert isinstance(node.test.comparators[0], ast.Constant)
        assert node.test.comparators[0].value == digest

    actual_pin(actual)
    with pytest.raises(AssertionError):
        actual_pin(dict(actual, canonical=b"\n" + actual["canonical"]))
    digest = _TIMELINE_ACTUAL_CANONICAL_SHA256.encode()
    assert actual["lifecycle"].count(digest) == 1
    wrong_pin = actual["lifecycle"].replace(
        digest, _TIMELINE_STAGE_EXPECTED["canonical"][1].encode(), 1)
    ast.parse(wrong_pin)
    with pytest.raises(AssertionError):
        actual_pin(dict(actual, lifecycle=wrong_pin))
    restored = _timeline_stage_rollback(**_handoff_dependency_stage_restore(**actual))
    assert _close_guard_stage_restore(**actual) == dict(
        canonical="57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
        lifecycle="8a38a20dcd141e9e7fc96844b3cfcf91714d50d2b587814e478a1f1f1cfc7902",
        retirement="30a583960e87d5c767585c35aac3c2878edcc551a69520e4f55f639dbea6613c")
    # Existing cumulative algorithm, including actual class/core/18-root checks.
    _controller_cancel_restoration_guard()
    assert len(_CONTROLLER_CANCEL_CANONICAL_SPANS) == 6
    assert len(_CLOSE_GUARD_STAGE_RETIREMENT_PINS) == 24
    assert len(_CONTROLLER_CANCEL_RETIREMENT_PINS) == 11
    assert hashlib.sha256(_handoff_dependency_stage_restore(**actual)["retirement"][:400464]).hexdigest() == (
        "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d")
    # Migration positions are read from strictly restored history, never moved.
    nodes = _host_budget_unit_migration_nodes(restored["retirement"].decode())
    assert tuple(node.value for node in nodes) == (
        9, 240418, "da1728e7dbb4cc4cbc5a9acff31b558867ae1e500dfcb4a0f3c05ce6ddd598aa")
    _timeline_actual_ast_controls(f, actual["lifecycle"])
    f.check()
# SDK_TIMELINE_STAGE_APPEND_END v1


# HANDOFF_DEPENDENCY_STAGE_APPEND_BEGIN v1
_HANDOFF_DEPENDENCY_BASELINE_EXPECTED = {'canonical': (263160, '493a905b3fa99116e67bbaa0120ab0e16d85fb0256f2c364ff478742567c671e'), 'lifecycle': (246761, 'fd23278f69698eb90878f7f6fbc64a05b56d0daab4423527e58216eb43e4a0ad'), 'retirement': (632407, 'dae7e2a6dc88a1c1ed9480fa1891790d14cc86b9525b774d48e229f374cdf372')}
_HANDOFF_DEPENDENCY_STAGE_TRANSFORMS = ((95276, b'    return _handoff_extract("host_main", ("watchdog",), namespace)["watchdog"]', b'    # Bind the actual decoded guest dependency in this UNIT namespace only.\n    assert namespace["END"] == end\n    assert namespace["PHASE"] == "sdk-retire-two-slot-verification"\n    diagnostic_packets = []\n    diagnostic_clock = time.monotonic_ns\n\n    def diagnostic_write(fd, raw):\n        diagnostic_packets.append((fd, raw))\n        return len(raw)\n\n    namespace.update(\n        MODE="host", json=json, _boundary_original_ready=True,\n        _boundary_original_clock=diagnostic_clock,\n        _boundary_original_write=diagnostic_write,\n        _handoff_host_budget_packets=diagnostic_packets)\n    diagnostic, = [\n        node for node in _compat_guest_tree().body\n        if isinstance(node, ast.FunctionDef)\n        and node.name == "_host_budget_diagnostic"]\n    exec(compile(ast.Module(body=[diagnostic], type_ignores=[]),\n                 "EXTRACTED_host_budget_diagnostic", "exec"), namespace)\n    return _handoff_extract("host_main", ("watchdog",), namespace)["watchdog"]'), (116413, b'', b'    # Bind the actual decoded guardian dependency in this namespace only.\n    guardian_diagnostic_packets = []\n    guardian_diagnostic_clock = time.monotonic_ns\n\n    def guardian_diagnostic_write(fd, raw):\n        guardian_diagnostic_packets.append((fd, raw))\n        return len(raw)\n\n    namespace.update(\n        json=json, _guardian_budget_ready=True,\n        _guardian_budget_clock=guardian_diagnostic_clock,\n        _guardian_budget_write=guardian_diagnostic_write,\n        _handoff_guardian_budget_packets=guardian_diagnostic_packets)\n    guardian_diagnostic, = [\n        node for node in _compat_guest_tree().body\n        if isinstance(node, ast.FunctionDef)\n        and node.name == "_guardian_budget_diagnostic"]\n    exec(compile(ast.Module(body=[guardian_diagnostic], type_ignores=[]),\n                 "EXTRACTED_guardian_budget_diagnostic_handoff", "exec"), namespace)\n'), (412770, b'Path(__file__).read_bytes()[:400464]', b'_timeline_history_inputs()["retirement"][:400464]'), (457167, b'Path(__file__).read_bytes()[:400464]', b'_timeline_history_inputs()["retirement"][:400464]'), (476278, b'Path(__file__).read_bytes()[:length] if length == 400464', b'_timeline_history_inputs()["retirement"][:length] if length == 400464'), (531648, b'path.read_bytes()[:400464]', b'_timeline_history_inputs()["retirement"][:400464]'), (546288, b'    _timeline_inputs = _timeline_stage_rollback(\n        canonical=canonical, lifecycle=lifecycle, retirement=retirement)', b'    _timeline_inputs = _timeline_stage_rollback(\n        **_handoff_dependency_stage_restore(\n            canonical=canonical, lifecycle=lifecycle, retirement=retirement))'), (583175, b'    return _timeline_stage_rollback(\n        canonical=path.with_name("test_owned_sql_sdk_canonical.py").read_bytes(),\n        lifecycle=path.with_name("test_sql_lifecycle_process.py").read_bytes(),\n        retirement=path.read_bytes())', b'    return _timeline_stage_rollback(**_handoff_dependency_stage_restore(\n        canonical=path.with_name("test_owned_sql_sdk_canonical.py").read_bytes(),\n        lifecycle=path.with_name("test_sql_lifecycle_process.py").read_bytes(),\n        retirement=path.read_bytes()))'), (621546, b'    actual = f.sources()', b'    actual = _handoff_dependency_stage_restore(**f.sources())'), (622842, b'    actual = f.sources()', b'    actual = _handoff_dependency_stage_restore(**f.sources())'), (631192, b'    restored = _timeline_stage_rollback(**actual)', b'    restored = _timeline_stage_rollback(**_handoff_dependency_stage_restore(**actual))'), (631878, b'actual["retirement"][:400464]', b'_handoff_dependency_stage_restore(**actual)["retirement"][:400464]'))
_HANDOFF_DEPENDENCY_BODY_SIZE = 634489
_HANDOFF_DEPENDENCY_BODY_SHA256 = '471804bd9bc19258d91522d7162c2093d588fbd79a24dcbe4453b04d4d5f1020'
_HANDOFF_DEPENDENCY_ACTUAL_PREFIX_SHA256 = '03c431fc28cd1276a201c7cdc217a41ad94e0ae0166ac2f4bc8c489924f47967'
_HANDOFF_DEPENDENCY_TAIL_SIZE = 62661

from hashlib import sha256 as _handoff_dependency_sha256


def _handoff_dependency_source_pin(*, canonical, lifecycle, retirement, expected):
    """EXTERNAL trusted full-source pins; never derive expected from target."""
    raw = dict(canonical=canonical, lifecycle=lifecycle, retirement=retirement)
    assert type(expected) is dict and set(expected) == set(raw)
    for name, value in raw.items():
        assert type(value) is bytes
        size, digest = expected[name]
        assert type(size) is int and size >= 0
        assert type(digest) is str and len(digest) == 64
        assert len(value) == size and _handoff_dependency_sha256(value).hexdigest() == digest


def _handoff_dependency_stage_restore(*, canonical, lifecycle, retirement):
    """Pure positional history inverse; EXTERNAL pins authenticate its own tail."""
    sha = lambda data: _handoff_dependency_sha256(data).hexdigest()
    raw = dict(canonical=canonical, lifecycle=lifecycle, retirement=retirement)
    assert all(type(value) is bytes for value in raw.values())
    for name in ("canonical", "lifecycle"):
        size, digest = _HANDOFF_DEPENDENCY_BASELINE_EXPECTED[name]
        assert len(raw[name]) == size and sha(raw[name]) == digest
    assert len(retirement) == (_HANDOFF_DEPENDENCY_BODY_SIZE
                               + _HANDOFF_DEPENDENCY_TAIL_SIZE)
    assert sha(retirement[:_HANDOFF_DEPENDENCY_BODY_SIZE]) == _HANDOFF_DEPENDENCY_BODY_SHA256
    assert sha(retirement[:400464]) == _HANDOFF_DEPENDENCY_ACTUAL_PREFIX_SHA256
    tail = retirement[_HANDOFF_DEPENDENCY_BODY_SIZE:]
    assert tail.startswith(b"\n\n# HANDOFF_DEPENDENCY_STAGE_APPEND_BEGIN v1\n")
    assert tail.endswith(b"# HANDOFF_DEPENDENCY_STAGE_APPEND_END v1\n")
    assert tail.count(b"# HANDOFF_DEPENDENCY_STAGE_APPEND_BEGIN v1\n") == 1
    assert tail.count(b"# HANDOFF_DEPENDENCY_STAGE_APPEND_END v1\n") == 1
    size, digest = _HANDOFF_DEPENDENCY_BASELINE_EXPECTED["retirement"]
    transforms = _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS
    assert type(transforms) is tuple and len(transforms) == 12
    previous_start, previous_stop, delta = -1, 0, 0
    inverses = []
    for start, old, new in transforms:
        assert type(start) is int and type(old) is type(new) is bytes
        assert previous_start < start and previous_stop <= start <= start + len(old) <= size
        first = start + delta
        assert 0 <= first <= first + len(new) <= _HANDOFF_DEPENDENCY_BODY_SIZE
        assert retirement[first:first + len(new)] == new
        inverses.append((first, first + len(new), old))
        delta += len(new) - len(old)
        previous_start, previous_stop = start, start + len(old)
    assert size + delta == _HANDOFF_DEPENDENCY_BODY_SIZE
    value = retirement[:_HANDOFF_DEPENDENCY_BODY_SIZE]
    for first, last, old in reversed(inverses):
        assert 0 <= first <= last <= len(value)
        value = value[:first] + old + value[last:]
    assert len(value) == size and sha(value) == digest
    return dict(canonical=canonical, lifecycle=lifecycle, retirement=value)


# New explicit UNIT fixtures only. No autouse/global source adapter.
# Runtime AST inputs remain actual sources pinned by repository-trusted data;
# parent-reviewed external pins authenticate BOTH the source and that data.

def _handoff_dependency_unit():
    """One UNIT3 covers adjacent pin/source setup, every control, final checks."""
    started = time.monotonic()
    end = started + 3.0
    import stat

    def check():
        assert time.monotonic() < end, "HANDOFF_DEPENDENCY_UNIT3"
        assert _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS is original_transforms

    original_transforms = _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS
    check()
    path = Path(__file__)
    assert path.is_absolute() and path.resolve(strict=True) == path
    assert stat.S_ISREG(path.lstat().st_mode)
    pins_path = path.with_name("owned_sql_sdk_handoff_dependency_pins.json")
    assert stat.S_ISREG(pins_path.lstat().st_mode)
    assert pins_path.resolve(strict=True) == pins_path
    names = {
        "canonical": "test_owned_sql_sdk_canonical.py",
        "lifecycle": "test_sql_lifecycle_process.py",
        "retirement": "test_owned_sql_sdk_retirement.py",
    }
    pins = json.loads(pins_path.read_bytes())
    assert type(pins) is dict and set(pins) == set(names.values())
    expected = {}
    sources = {}
    for name, filename in names.items():
        row = pins[filename]
        assert type(row) is dict and set(row) == {"bytes", "sha256"}
        size, digest = row["bytes"], row["sha256"]
        assert type(size) is int and size > 0
        assert type(digest) is str and len(digest) == 64
        assert all(character in "0123456789abcdef" for character in digest)
        expected[name] = (size, digest)
        source_path = path.with_name(filename)
        assert stat.S_ISREG(source_path.lstat().st_mode)
        assert source_path.resolve(strict=True) == source_path
        sources[name] = source_path.read_bytes()  # Actual3, once each, no baseline substitute.
        check()
    assert expected["canonical"] == (
        263160, "493a905b3fa99116e67bbaa0120ab0e16d85fb0256f2c364ff478742567c671e")
    assert expected["lifecycle"] == (
        246761, "fd23278f69698eb90878f7f6fbc64a05b56d0daab4423527e58216eb43e4a0ad")
    # Repository-trusted test data, NOT independent security authority/self-authentication.
    # Parent pins actual R AND adjacent JSON externally before import/spawn.
    # No hash(actual) expected value, environment selector or pin fallback.
    _handoff_dependency_source_pin(**sources, expected=expected)
    check()
    outer = ast.parse(sources["lifecycle"])
    assignment, = [
        node for node in outer.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_OWNED_GUEST_PROBE"
                for target in node.targets)]
    guest = ast.literal_eval(assignment.value)
    guest_tree = ast.parse(guest)
    diagnostic, = [
        node for node in guest_tree.body if isinstance(node, ast.FunctionDef)
        and node.name == "_host_budget_diagnostic"]
    host, = [node for node in guest_tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "host_main"]
    watchdog, = [node for node in host.body
                 if isinstance(node, ast.FunctionDef) and node.name == "watchdog"]
    assert _handoff_dependency_sha256(ast.get_source_segment(
        guest, diagnostic).encode()).hexdigest() == (
            "81b2fd6feb595304a4db4ebf57d41d6d9cf68b81308012594d3c7ce538661b33")
    diagnostic_clock, = [
        node for node in ast.walk(diagnostic) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "_boundary_original_clock"]
    diagnostic_write, = [
        node for node in ast.walk(diagnostic) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "_boundary_original_write"]
    assert diagnostic.lineno < diagnostic_clock.lineno < diagnostic_write.lineno
    data_expected = {'_CLOSE_GUARD_STAGE_CANONICAL_SPAN': (1043, '09552a8fe021c471089e52fb383c3785a61d551220b99ff0c858fceb1abba71c'), '_CLOSE_GUARD_STAGE_LIFECYCLE_PINS': (218, '7fb8069fe783f01a3fffdab4dc9fecb85eb01e6bc7b4eacb32cb5ac66d8f0ea4'), '_CLOSE_GUARD_STAGE_RETIREMENT_PINS': (4359, '19ec97711a0aaf2d42b876a07b0ed261bdd1bc78724ee4341c0a8b134e398ed6'), '_CLOSE_GUARD_STAGE_TUPLE_INSERTION': (1095, '7fd78d1e1aa707233ba2a594483e2be21284fc42e4c36647fce56bac9ec79b2e'), '_CONTROLLER_CANCEL_CANONICAL_SPANS': (3489, '5aedf74c92885b84b4cacbfe1a4ef74530ef7d5e74b8f8a3b225d149316fcb71'), '_CONTROLLER_CANCEL_RETIREMENT_PINS': (2019, '9bf4ceeda3922c808c5e1925d1084f153a4104c9cc2ef78a95ab9934c0825c65'), '_TIMELINE_ACTUAL_CANONICAL_SHA256': (102, 'f0b8f3ae3072902f8dc1689bd2450b3456e7e790962e5e45afaca448b29a1b12'), '_TIMELINE_STAGE_COUNTS': (75, '7ab9ef7f5b6186ed5cf4c070703e51db0622cb0ed1b1a81ab54f32ac54368653'), '_TIMELINE_STAGE_EXPECTED': (301, '15fa99f81c62628644b61185877169b00bc589850523268f743ad5cca357794e'), '_TIMELINE_STAGE_TRANSFORMS': (10203, '79065ba48c31227286b460edc162611024c5251d034e91c908241f8ff6a1e48e')}
    check()
    return SimpleNamespace(
        started=started, end=end, check=check, path=path, sources=sources,
        expected=expected, guest=guest, guest_tree=guest_tree,
        diagnostic=diagnostic, diagnostic_clock=diagnostic_clock,
        diagnostic_write=diagnostic_write, watchdog=watchdog,
        data_expected=data_expected, original_transforms=original_transforms)


def _handoff_dependency_check_table_text(unit, source):
    """Independent reviewed old-definition pins, not expected hashes of target."""
    unit.check()
    text = source.decode()
    assignments = {
        target.id: node for node in ast.parse(source).body
        if isinstance(node, ast.Assign) for target in node.targets
        if isinstance(target, ast.Name)}
    for name, (size, digest) in unit.data_expected.items():
        raw = ast.get_source_segment(text, assignments[name]).encode()
        assert len(raw) == size and _handoff_dependency_sha256(raw).hexdigest() == digest
        unit.check()


def _handoff_dependency_inverse_with_rows(unit, rows):
    """Same NEW pure inverse code, private complete globals; no module rebinding."""
    import types
    unit.check()
    prototype = _handoff_dependency_stage_restore
    namespace = dict(
        __builtins__=__builtins__,
        _handoff_dependency_sha256=_handoff_dependency_sha256,
        _HANDOFF_DEPENDENCY_BASELINE_EXPECTED=_HANDOFF_DEPENDENCY_BASELINE_EXPECTED,
        _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS=rows,
        _HANDOFF_DEPENDENCY_BODY_SIZE=_HANDOFF_DEPENDENCY_BODY_SIZE,
        _HANDOFF_DEPENDENCY_BODY_SHA256=_HANDOFF_DEPENDENCY_BODY_SHA256,
        _HANDOFF_DEPENDENCY_ACTUAL_PREFIX_SHA256=_HANDOFF_DEPENDENCY_ACTUAL_PREFIX_SHA256,
        _HANDOFF_DEPENDENCY_TAIL_SIZE=_HANDOFF_DEPENDENCY_TAIL_SIZE)
    for name in prototype.__code__.co_names:
        if name.startswith("@"):
            assert name in ("@pytest_ar", "@py_builtins")
            namespace[name] = prototype.__globals__[name]
            assert namespace[name] is prototype.__globals__[name]
    value = types.FunctionType(prototype.__code__, namespace, prototype.__name__)
    assert value.__code__ is prototype.__code__
    assert value.__globals__ is namespace
    assert value.__globals__ is not prototype.__globals__
    assert _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS is unit.original_transforms
    unit.check()
    return value


def _handoff_dependency_watchdog_case(unit, early, *, writer_mode="normal", selector_error=None):
    """Actual corrected harness/helper/watchdog; all owner/native receivers inert."""
    unit.check()
    assert writer_mode in ("normal", "throw", "short")
    events, forbidden_calls, owner_calls, selector_calls, gate_waits, remaining_calls = (
        [], [], [], [], [], [])
    marker = RuntimeError("UNIT_HANDOFF_DEPENDENCY_OWNER_STOP")
    write_error = RuntimeError("UNIT_HANDOFF_DEPENDENCY_WRITE")
    calls = Counter()
    clock = time.monotonic_ns
    namespace = dict(END=unit.end, PHASE="sdk-retire-two-slot-verification")
    packets = []
    selector_returned_ns = []
    owner_entered_ns = []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("HANDOFF_DEPENDENCY_NATIVE_OR_PUBLIC_ALIAS_ESCAPE")

    def request_native_handoff():
        unit.check()
        owner_entered_ns.append(clock())
        owner_calls.append("request_native_handoff")
        events.append("owner-request")
        raise marker  # Declared UNIT receiver, never a real owner/handoff receipt.

    def gate_wait(timeout):
        unit.check()
        gate_waits.append(timeout)
        # New UNIT3 END has already crossed the original3.5 reserve.
        # Original harness expression remains untouched, this gate never waits.
        assert timeout == 0.0
        if selector_error is not None:
            raise selector_error
        return True

    namespace["cleanup"] = forbidden
    owner = SimpleNamespace(request_native_handoff=request_native_handoff)
    watchdog = _handoff_watchdog(
        namespace, owner, calls, unit.end, early=early,
        select_gate=SimpleNamespace(wait=gate_wait))
    packets = namespace["_handoff_host_budget_packets"]
    captured_clock = namespace["_boundary_original_clock"]
    captured_write = namespace["_boundary_original_write"]
    assert captured_clock is clock is time.monotonic_ns
    assert captured_write.__name__ == "diagnostic_write"
    assert captured_write.__code__.co_freevars == ("diagnostic_packets",)
    assert len(captured_write.__closure__) == 1
    assert captured_write.__closure__[0].cell_contents is packets
    assert namespace["MODE"] == "host" and namespace["_boundary_original_ready"] is True
    assert namespace["PHASE"] == "sdk-retire-two-slot-verification"
    assert namespace["END"] == unit.end and namespace["json"] is json
    actual_helper = namespace["_host_budget_diagnostic"]
    assert actual_helper.__globals__ is namespace
    assert actual_helper.__code__.co_filename == "EXTRACTED_host_budget_diagnostic"
    assert actual_helper.__code__.co_firstlineno == unit.diagnostic.lineno
    assert watchdog.__globals__ is namespace
    assert watchdog.__code__.co_filename == "EXTRACTED_host_main"
    assert watchdog.__code__.co_firstlineno == unit.watchdog.lineno
    assert packets == []
    original_select = namespace["select"].select
    original_remaining = namespace["remaining"]

    def remaining(deadline):
        unit.check()
        assert deadline == unit.end - 3.75
        value = original_remaining(deadline)
        remaining_calls.append((deadline, value))
        return value

    def select(inputs, writes, errors, timeout):
        unit.check()
        assert inputs == ([0, 303, 301] if early else [0, 303])
        assert writes == errors == []
        assert remaining_calls == [(unit.end - 3.75, timeout)]
        assert packets == [] and owner_calls == []
        selector_calls.append((tuple(inputs), tuple(writes), tuple(errors), timeout))
        events.append("select")
        value = original_select(inputs, writes, errors, timeout)
        selector_returned_ns.append(clock())
        assert value == ([301] if early else [], [], [])
        assert packets == []
        events.append("select-return")
        return value

    write_attempts = []

    def controlled_writer(fd, raw):
        unit.check()
        write_attempts.append((fd, raw))
        captured_write(fd, raw)  # The SAME real harness collector, one attempt.
        if writer_mode == "throw":
            raise write_error
        return 0  # Short write: original diagnostic must not retry or alter flow.

    namespace["remaining"] = remaining
    namespace["select"] = SimpleNamespace(select=select)
    # Only public aliases INSIDE the extracted namespace are poisoned.
    namespace["time"] = SimpleNamespace(monotonic_ns=forbidden, monotonic=forbidden)
    namespace["os"] = SimpleNamespace(write=forbidden)
    if writer_mode != "normal":
        namespace["_boundary_original_write"] = controlled_writer
    assert namespace["_boundary_original_clock"] is captured_clock
    assert captured_write.__closure__[0].cell_contents is packets
    expected_error = marker if selector_error is None else selector_error
    with pytest.raises(RuntimeError) as caught:
        watchdog()
    assert caught.value is expected_error
    assert calls["watchdog-select"] == 1
    assert len(selector_calls) == len(gate_waits) == len(remaining_calls) == 1
    assert calls["early-read"] == (int(early) if selector_error is None else 0)
    assert calls["mock-report"] == 0 and forbidden_calls == []
    assert namespace["END"] == unit.end
    assert namespace["PHASE"] == "sdk-retire-two-slot-verification"
    assert namespace["_boundary_original_clock"] is captured_clock
    if writer_mode == "normal":
        assert namespace["_boundary_original_write"] is captured_write
    else:
        assert namespace["_boundary_original_write"] is controlled_writer
    if selector_error is None:
        assert owner_calls == ["request_native_handoff"]
        assert events == ["select", "select-return", "owner-request"]
        assert len(packets) == 1
        assert len(write_attempts) == int(writer_mode != "normal")
        requests = sorted(
            [node for node in ast.walk(unit.watchdog) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "request_native_handoff"], key=lambda node: node.lineno)
        assert len(requests) == 2
        expected_line = requests[0 if early else 1].lineno
        trace = caught.value.__traceback__
        watchdog_sites = []
        while trace is not None:
            if trace.tb_frame.f_code is watchdog.__code__:
                watchdog_sites.append(trace.tb_lineno)
            trace = trace.tb_next
        assert watchdog_sites == [expected_line]
    else:
        assert packets == [] and write_attempts == [] and owner_calls == []
        assert events == ["select"] and selector_returned_ns == [] and owner_entered_ns == []
    unit.check()
    return SimpleNamespace(
        packets=packets, captured_clock=captured_clock, captured_write=captured_write,
        selector_returned_ns=selector_returned_ns, owner_entered_ns=owner_entered_ns,
        caught=caught.value, marker=marker, write_error=write_error,
        write_attempts=write_attempts, owner_calls=owner_calls, calls=calls)


def _handoff_dependency_packet(unit, case, early):
    unit.check()
    assert len(case.packets) == 1, "HANDOFF_HOST_BUDGET_PACKET_REQUIRED"
    fd, raw = case.packets[0]
    assert type(fd) is int and fd == 2
    assert type(raw) is bytes and 0 < len(raw) <= 512
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    packet = json.loads(raw)
    assert set(packet) == {"kind", "site", "reason", "end_ns", "cutoff_ns", "observed_ns"}
    assert packet == dict(
        kind="FIXTURE_HOST_BUDGET", site="WATCHDOG_DECISION",
        reason="RACE_READY" if early else "TIMEOUT",
        end_ns=int(unit.end * 1000000000),
        cutoff_ns=int((unit.end - 3.75) * 1000000000),
        observed_ns=packet["observed_ns"])
    assert all(type(packet[key]) is int and 0 <= packet[key] <= 9223372036854775807
               for key in ("end_ns", "cutoff_ns", "observed_ns"))
    assert len(case.selector_returned_ns) == len(case.owner_entered_ns) == 1
    assert case.selector_returned_ns[0] <= packet["observed_ns"] <= case.owner_entered_ns[0]
    assert case.caught is case.marker and case.caught is not case.write_error
    unit.check()


@pytest.mark.parametrize("early", (False, True), ids=("normal", "early"))
def test_handoff_dependency_emits_actual_host_diagnostic(early):
    unit = _handoff_dependency_unit()
    try:
        for writer_mode in ("normal", "throw", "short"):
            case = _handoff_dependency_watchdog_case(unit, early, writer_mode=writer_mode)
            _handoff_dependency_packet(unit, case, early)
            assert case.calls["watchdog-select"] == 1
            assert case.owner_calls == ["request_native_handoff"]
            unit.check()
        original_error = RuntimeError("UNIT_ORIGINAL_SELECTOR_ERROR")
        interrupted = _handoff_dependency_watchdog_case(unit, early, selector_error=original_error)
        assert interrupted.caught is original_error
        assert interrupted.packets == [] and interrupted.owner_calls == []
        # An absent packet cannot pass the positive behavioral observation gate.
        with pytest.raises(AssertionError, match="HANDOFF_HOST_BUDGET_PACKET_REQUIRED"):
            _handoff_dependency_packet(unit, interrupted, early)
        unit.check()
    finally:
        unit.check()


def test_handoff_dependency_strict_current_stage():
    unit = _handoff_dependency_unit()
    try:
        assert _handoff_dependency_source_pin(**unit.sources, expected=unit.expected) is None
        baseline = _handoff_dependency_stage_restore(**unit.sources)
        assert set(baseline) == {"canonical", "lifecycle", "retirement"}
        for name, (size, digest) in _HANDOFF_DEPENDENCY_BASELINE_EXPECTED.items():
            assert len(baseline[name]) == size
            assert _handoff_dependency_sha256(baseline[name]).hexdigest() == digest
        assert baseline["canonical"] is unit.sources["canonical"]
        assert baseline["lifecycle"] is unit.sources["lifecycle"]
        _handoff_dependency_check_table_text(unit, unit.sources["retirement"])
        _handoff_dependency_check_table_text(unit, baseline["retirement"])
        historical = _timeline_stage_rollback(**baseline)
        for name, (size, digest) in _TIMELINE_STAGE_EXPECTED.items():
            assert len(historical[name]) == size
            assert _handoff_dependency_sha256(historical[name]).hexdigest() == digest
        assert _timeline_history_inputs() == historical
        assert _close_guard_stage_restore(**unit.sources) == dict(
            canonical="57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
            lifecycle="8a38a20dcd141e9e7fc96844b3cfcf91714d50d2b587814e478a1f1f1cfc7902",
            retirement="30a583960e87d5c767585c35aac3c2878edcc551a69520e4f55f639dbea6613c")
        # Original cumulative guards inspect class/core/18 function roots,
        # never instantiate an SDK/native owner.
        _controller_cancel_restoration_guard()
        assert len(_CONTROLLER_CANCEL_CANONICAL_SPANS) == 6
        assert len(_CONTROLLER_CANCEL_RETIREMENT_PINS) == 11
        assert len(_CLOSE_GUARD_STAGE_RETIREMENT_PINS) == 24
        unit.check()
    finally:
        unit.check()


def test_handoff_dependency_rejects_unlisted_mutations():
    unit = _handoff_dependency_unit()
    try:
        _handoff_dependency_source_pin(**unit.sources, expected=unit.expected)
        restored = _handoff_dependency_stage_restore(**unit.sources)
        inverse = _handoff_dependency_inverse_with_rows(unit, unit.original_transforms)
        assert inverse(**unit.sources) == restored
        unit.check()
        for name, raw in unit.sources.items():
            mutants = [b"\n" + raw]
            if name == "retirement":
                assert raw.startswith(b'"""SOURCE-ONLY')
                mutants.append(raw.replace(b"SOURCE-ONLY", b"SOURCE_ONLY", 1))
            else:
                old = raw[:3]
                assert old == b'"""'
                mutants.append(b"'''" + raw[3:raw.index(b'"""', 3)] +
                               b"'''" + raw[raw.index(b'"""', 3) + 3:])
            for changed in mutants:
                ast.parse(changed)  # Valid source, not parser-failure RED.
                supplied = dict(unit.sources, **{name: changed})
                with pytest.raises(AssertionError):
                    _handoff_dependency_source_pin(**supplied, expected=unit.expected)
                with pytest.raises(AssertionError):
                    _handoff_dependency_stage_restore(**supplied)
                unit.check()
        raw = unit.sources["retirement"]
        start, old, new = unit.original_transforms[0]
        first = raw.index(b"Bind", start, start + len(new))
        changed = raw[:first] + b"BIND" + raw[first + 4:]
        ast.parse(changed)
        with pytest.raises(AssertionError):
            _handoff_dependency_stage_restore(**dict(unit.sources, retirement=changed))
        # Real pre-existing timeline source byte, still valid Python.
        start, old, new = _TIMELINE_STAGE_TRANSFORMS["canonical"][0]
        timing = unit.sources["canonical"]
        at = start + new.index(b".note(2)") + len(b".note(")
        assert timing[at:at + 1] == b"2"
        changed = timing[:at] + b"9" + timing[at + 1:]
        ast.parse(changed)
        with pytest.raises(AssertionError):
            _handoff_dependency_stage_restore(**dict(unit.sources, canonical=changed))
        rows = unit.original_transforms
        first = rows[0]
        start, old, new = first
        altered = (
            rows[1:], rows + (rows[-1],),
            (first, first) + rows[2:],
            (rows[1], rows[0]) + rows[2:],
            ((start + 1, old, new),) + rows[1:],
            (first, (start + 1, rows[1][1], rows[1][2])) + rows[2:],
            ((start, old, new + b" "),) + rows[1:],
            ((start, b"X" + old[1:], new),) + rows[1:],
            ((start, old, b"X" + new[1:]),) + rows[1:],
            ((True, old, new),) + rows[1:],
            ((start, bytearray(old), new),) + rows[1:],
        )
        for bad_rows in altered:
            inverse = _handoff_dependency_inverse_with_rows(unit, bad_rows)
            with pytest.raises(AssertionError):
                inverse(**unit.sources)
            assert _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS is rows
            unit.check()
        # Explicit negatives for the ONE newly approved guardian row.
        guardian = rows[1]
        start, old, new = guardian
        assert b"guardian_diagnostic_packets = []" in new
        guardian_altered = (
            rows[:1] + rows[2:],                         # Missing new row.
            rows[:2] + (guardian,) + rows[2:],           # Duplicate new row.
            (guardian, rows[0]) + rows[2:],              # Baseline order.
            rows[:1] + ((rows[0][0], old, new),) + rows[2:],  # Overlap.
            rows[:1] + ((float(start), old, new),) + rows[2:],
            rows[:1] + ((start, bytearray(old), new),) + rows[2:],
            rows[:1] + ((start, old, bytearray(new)),) + rows[2:],
            rows[:1] + ((start, b"X" + old[1:], new),) + rows[2:],
            rows[:1] + ((start, old, b"X" + new[1:]),) + rows[2:],
        )
        for bad_rows in guardian_altered:
            inverse = _handoff_dependency_inverse_with_rows(unit, bad_rows)
            with pytest.raises(AssertionError):
                inverse(**unit.sources)
            assert _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS is rows
            unit.check()
        begin = b"# HANDOFF_DEPENDENCY_STAGE_APPEND_BEGIN v1\n"
        end = b"# HANDOFF_DEPENDENCY_STAGE_APPEND_END v1\n"
        body_stop = _HANDOFF_DEPENDENCY_BODY_SIZE
        body, tail = raw[:body_stop], raw[body_stop:]
        assert tail.count(begin) == tail.count(end) == 1
        for changed in (
                body + tail.replace(begin, b"", 1),
                body + tail.replace(end, b"", 1),
                body + tail.replace(begin, begin + begin, 1),
                body + tail.replace(end, end + end, 1),
                raw + b"# unlisted after tail\n",
                raw[:-1],
                body):
            ast.parse(changed)
            with pytest.raises(AssertionError):
                _handoff_dependency_stage_restore(**dict(unit.sources, retirement=changed))
            with pytest.raises(AssertionError):
                _handoff_dependency_source_pin(
                    **dict(unit.sources, retirement=changed), expected=unit.expected)
            unit.check()
        # Separate repository-trusted full-source pin data rejects tail mutations.
        # Not self-authentication: parent external pins authenticate source AND JSON.
        for old, new in (
                (b"_HANDOFF_DEPENDENCY_BODY_SIZE = 634489\n",
                 b"_HANDOFF_DEPENDENCY_BODY_SIZE = 634490\n"),
                (b'    """Pure positional history inverse; EXTERNAL pins authenticate its own tail."""\n',
                 b'    """Pure positional history inverse! EXTERNAL pins authenticate its own tail."""\n')):
            assert tail.count(old) == 1
            changed = body + tail.replace(old, new, 1)
            ast.parse(changed)
            with pytest.raises(AssertionError):
                _handoff_dependency_source_pin(
                    **dict(unit.sources, retirement=changed), expected=unit.expected)
            unit.check()
        _handoff_dependency_source_pin(**unit.sources, expected=unit.expected)
    finally:
        unit.check()


def test_handoff_dependency_actual_prefix_and_history_inputs():
    unit = _handoff_dependency_unit()
    try:
        assert _handoff_dependency_sha256(
            unit.sources["retirement"][:400464]).hexdigest() == (
                "03c431fc28cd1276a201c7cdc217a41ad94e0ae0166ac2f4bc8c489924f47967")
        restored = _handoff_dependency_stage_restore(**unit.sources)
        assert _handoff_dependency_sha256(restored["retirement"][:400464]).hexdigest() == (
            "fbec74e011ebb335446ff28a588d080d32b278f3d4865c1c503e72b71d68528d")
        _handoff_dependency_check_table_text(unit, unit.sources["retirement"])
        historical = _timeline_history_inputs()
        assert historical == _timeline_stage_rollback(**restored)
        assert historical["lifecycle"] != unit.sources["lifecycle"]
        canonical_digest = unit.expected["canonical"][1]
        assert canonical_digest == _TIMELINE_ACTUAL_CANONICAL_SHA256
        pin, = [
            node for node in ast.walk(unit.guest_tree) if isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Call)
            and isinstance(node.test.left.func, ast.Attribute)
            and node.test.left.func.attr == "hexdigest"
            and any(isinstance(child, ast.Name) and child.id == "_boundary_canonical_source"
                    for child in ast.walk(node.test.left))]
        assert len(pin.test.comparators) == 1
        assert isinstance(pin.test.comparators[0], ast.Constant)
        assert pin.test.comparators[0].value == canonical_digest
        canonical_tree = ast.parse(unit.sources["canonical"])
        retirement, = [node for node in canonical_tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "_SdkRetirement"]
        assert _handoff_dependency_sha256(ast.get_source_segment(
            unit.sources["canonical"].decode(), retirement).encode()).hexdigest() == (
                "800f4483b28823ccf418a995b7e6656983f4e5a29b5adda7550f561b9edf355b")
        import stat
        core_path = unit.path.with_name("sql_isolation.py")
        assert stat.S_ISREG(core_path.lstat().st_mode)
        assert core_path.resolve(strict=True) == core_path
        core = core_path.read_bytes()
        assert _handoff_dependency_sha256(core).hexdigest() == (
            "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e")
        unit.check()
        assert len(_SIBLING_DIAG_ROOTS) == 18

        def location(error, node):
            trace = error.__traceback__
            while trace.tb_next is not None:
                trace = trace.tb_next
            assert trace.tb_frame.f_code.co_filename == str(unit.path)
            assert trace.tb_lineno == node.lineno
            unit.check()

        # The unchanged old checker extracts/compares ACTUAL guardian/watchdog/
        # exception nodes and rejects its real AST mutations at original asserts.
        # No reconstructed lifecycle input, source/Path adapter or owner fixture.
        _timeline_actual_ast_controls(
            SimpleNamespace(check=unit.check, location=location), unit.sources["lifecycle"])
        unit.check()
    finally:
        unit.check()


def _handoff_dependency_guardian_bind(unit):
    """Compile only the ACTUAL new binding statements, not the old UNIT."""
    unit.check()
    source = unit.sources["retirement"].decode()
    tree = _handoff_dependency_guardian_span_tree(unit)
    original, = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "test_guardian_independent_safety_still_runs"]
    start, = [index for index, node in enumerate(original.body)
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name)
                      and target.id == "guardian_diagnostic_packets" for target in node.targets)]
    stop, = [index for index, node in enumerate(original.body)
             if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and isinstance(node.value.func, ast.Name)
             and node.value.func.id == "_handoff_extract"]
    nodes = original.body[start:stop]
    assert len(nodes) == 6
    assert isinstance(nodes[-1], ast.Expr)
    assert "EXTRACTED_guardian_budget_diagnostic_handoff" in ast.get_source_segment(
        source, nodes[-1])
    # A private wrapper retains the original collector closure and source lines.
    wrapper = ast.FunctionDef(
        name="bind", args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="namespace")],
            kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=nodes + [ast.Return(value=ast.Name(id="namespace", ctx=ast.Load()))],
        decorator_list=[])
    ast.fix_missing_locations(wrapper)
    environment = dict(ast=ast, json=json, time=time, _compat_guest_tree=_compat_guest_tree)
    exec(compile(ast.Module(body=[wrapper], type_ignores=[]), str(unit.path), "exec"),
         environment)
    namespace = dict(END=unit.end)
    assert environment["bind"](namespace) is namespace
    helper, = [node for node in unit.guest_tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "_guardian_budget_diagnostic"]
    guardian, = [node for node in unit.guest_tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "guardian_main"]
    watchdog, = [node for node in guardian.body if isinstance(node, ast.FunctionDef)
                 and node.name == "watchdog"]
    actual_helper = namespace["_guardian_budget_diagnostic"]
    assert actual_helper.__globals__ is namespace
    assert actual_helper.__code__.co_filename == "EXTRACTED_guardian_budget_diagnostic_handoff"
    assert actual_helper.__code__.co_firstlineno == helper.lineno
    dependencies = {node.id for node in ast.walk(helper)
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert dependencies - {
        "ready", "safety", "observed_ns", "reason", "end_ns", "cutoff_ns",
        "wire", "value", "type", "list", "len", "int", "any", "dict", "BaseException"
    } == {"END", "json", "_guardian_budget_ready",
          "_guardian_budget_clock", "_guardian_budget_write"}
    assert "MODE" not in namespace
    assert namespace["END"] is unit.end and namespace["json"] is json
    assert namespace["_guardian_budget_ready"] is True
    assert namespace["_guardian_budget_clock"] is time.monotonic_ns
    writer = namespace["_guardian_budget_write"]
    assert writer.__name__ == "guardian_diagnostic_write"
    assert writer.__code__.co_freevars == ("guardian_diagnostic_packets",)
    assert writer.__closure__[0].cell_contents is namespace["_handoff_guardian_budget_packets"]
    assert writer.__code__.co_filename == str(unit.path)
    assert writer.__code__.co_firstlineno == nodes[2].lineno
    _handoff_extract("guardian_main", ("watchdog",), namespace)
    assert namespace["watchdog"].__globals__ is namespace
    assert namespace["watchdog"].__code__.co_filename == "EXTRACTED_guardian_main"
    assert namespace["watchdog"].__code__.co_firstlineno == watchdog.lineno
    unit.check()
    return SimpleNamespace(namespace=namespace, helper=helper, watchdog=watchdog,
                           binding_nodes=nodes, writer=writer)


def _handoff_dependency_guardian_case(
        unit, readiness="timeout", *, writer_mode="normal", selector_error=None,
        missing=None):
    """Inert select/diagnostic receivers; stop before ANY physical cleanup."""
    unit.check()
    bound = _handoff_dependency_guardian_bind(unit)
    namespace, captured_write = bound.namespace, bound.writer
    packets = namespace["_handoff_guardian_budget_packets"]
    clock = namespace["_guardian_budget_clock"]
    monotonic = time.monotonic
    selected, returned, entered, downstream, forbidden_calls, attempts = [], [], [], [], [], []
    marker = RuntimeError("UNIT_HANDOFF_GUARDIAN_STOP")
    writer_error = RuntimeError("UNIT_HANDOFF_GUARDIAN_WRITER")
    safety, done = 402, 403  # Inert identities, never allocated descriptors.
    ready = dict(timeout=[], safety=[safety], done=[done],
                 both=[safety, done], reverse_both=[done, safety])[readiness]
    assert writer_mode in ("normal", "throw", "short")

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("HANDOFF_GUARDIAN_NATIVE_OR_PUBLIC_ALIAS_ESCAPE")

    def remaining(deadline):
        unit.check()
        assert deadline == unit.end - 3.5
        return max(0.0, deadline - monotonic())

    def select(inputs, writes, errors, timeout):
        unit.check()
        assert inputs == [safety, done] and writes == errors == []
        assert timeout == 0.0 and packets == [] and downstream == []
        selected.append((inputs, writes, errors, timeout))
        if selector_error is not None:
            raise selector_error
        returned.append(clock())
        return ready, [], []

    def failure_diagnostic(*args, **kwargs):
        entered.append(clock())
        downstream.append((args, kwargs))
        assert args == ("guardian-before-safety",)
        assert kwargs == dict(hits=[], published=[], monitor_alive=[])
        raise marker  # Existing downstream call, BEFORE original physical paths.

    def controlled_writer(fd, raw):
        unit.check()
        attempts.append((fd, raw))
        captured_write(fd, raw)
        if writer_mode == "throw":
            raise writer_error
        return 0

    namespace.update(
        safety=safety, done_r=done, select=SimpleNamespace(select=select),
        remaining=remaining, failure_diagnostic=failure_diagnostic, hits=[], contexts=[],
        physical_cleanup=forbidden, emit=forbidden, forbidden_calls=[],
        time=SimpleNamespace(monotonic=forbidden, monotonic_ns=forbidden),
        os=SimpleNamespace(write=forbidden, _exit=forbidden))
    if writer_mode != "normal":
        namespace["_guardian_budget_write"] = controlled_writer
    if missing is not None:
        del namespace[missing]
    caught = None
    try:
        namespace["watchdog"]()
    except (RuntimeError, NameError) as error:
        caught = error
    assert len(selected) == 1 and forbidden_calls == []
    if selector_error is not None:
        assert caught is selector_error
        assert returned == entered == downstream == packets == attempts == []
    elif missing == "_guardian_budget_diagnostic":
        assert type(caught) is NameError
        assert caught.name == "_guardian_budget_diagnostic"
        assert entered == downstream == packets == attempts == []
    elif done in ready:
        assert caught is None and entered == downstream == packets == attempts == []
    else:
        assert caught is marker and caught is not writer_error
        assert len(returned) == len(entered) == len(downstream) == 1
        # Sentinel propagates from the actual existing diagnostic statement.
        site, = [node for node in ast.walk(bound.watchdog) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "failure_diagnostic"]
        trace, sites = caught.__traceback__, []
        while trace is not None:
            if trace.tb_frame.f_code is namespace["watchdog"].__code__:
                sites.append(trace.tb_lineno)
            trace = trace.tb_next
        assert sites == [site.lineno]
    if missing != "_guardian_budget_clock":
        assert namespace["_guardian_budget_clock"] is clock
    if missing != "_guardian_budget_write":
        assert namespace["_guardian_budget_write"] is (
            captured_write if writer_mode == "normal" else controlled_writer)
    assert captured_write.__closure__[0].cell_contents is packets
    if missing is None:
        assert len(attempts) == (int(writer_mode != "normal")
                                 if selector_error is None and done not in ready else 0)
    unit.check()
    return SimpleNamespace(packets=packets, returned=returned, entered=entered,
                           attempts=attempts, downstream=downstream,
                           caught=caught, marker=marker, writer=captured_write)


def _handoff_dependency_guardian_packet(unit, case, readiness):
    unit.check()
    assert len(case.packets) == 1, "HANDOFF_GUARDIAN_BUDGET_PACKET_REQUIRED"
    fd, raw = case.packets[0]
    assert type(fd) is int and fd == 2
    assert type(raw) is bytes and 0 < len(raw) <= 512
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    packet = json.loads(raw)
    assert set(packet) == {"kind", "reason", "end_ns", "cutoff_ns", "observed_ns"}
    assert packet == dict(
        kind="FIXTURE_GUARDIAN_BUDGET",
        reason="TIMEOUT" if readiness == "timeout" else "SAFETY_READY",
        end_ns=int(unit.end * 1000000000),
        cutoff_ns=int((unit.end - 3.5) * 1000000000),
        observed_ns=packet["observed_ns"])
    assert all(type(packet[key]) is int and 0 <= packet[key] <= 9223372036854775807
               for key in ("end_ns", "cutoff_ns", "observed_ns"))
    assert len(case.returned) == len(case.entered) == len(case.downstream) == 1
    assert case.returned[0] <= packet["observed_ns"] <= case.entered[0]
    assert case.caught is case.marker
    unit.check()


def test_handoff_dependency_guardian_namespace_complete():
    unit = _handoff_dependency_unit()
    try:
        bound = _handoff_dependency_guardian_bind(unit)
        assert bound.namespace["_handoff_guardian_budget_packets"] == []
        rows = _HANDOFF_DEPENDENCY_STAGE_TRANSFORMS
        assert type(rows) is tuple and len(rows) == 12
        assert b"guardian_diagnostic_packets = []" in rows[1][2]
        original = rows[:1] + rows[2:]
        assert tuple(row[0] for row in original) == (
            95276, 412770, 457167, 476278, 531648, 546288,
            583175, 621546, 622842, 631192, 631878)
        canonical = json.dumps(
            [[offset, old.hex(), new.hex()] for offset, old, new in original],
            separators=(",", ":")).encode()
        # Independently captured current393 data, not derived from changed source.
        assert _handoff_dependency_sha256(canonical).hexdigest() == (
            "0cc84b205ad33ef0361d40663f8d6aaa8b974dfd42ee6acaac11d7271c442958")
        unit.check()
    finally:
        unit.check()


@pytest.mark.parametrize("readiness", ("timeout", "safety"), ids=("timeout", "safety"))
def test_handoff_dependency_emits_actual_guardian_diagnostic(readiness):
    unit = _handoff_dependency_unit()
    try:
        for writer_mode in ("normal", "throw", "short"):
            case = _handoff_dependency_guardian_case(
                unit, readiness, writer_mode=writer_mode)
            _handoff_dependency_guardian_packet(unit, case, readiness)
            assert len(case.packets) == len(case.downstream) == 1
            unit.check()
    finally:
        unit.check()


def test_handoff_dependency_guardian_done_and_missing_binding_controls():
    unit = _handoff_dependency_unit()
    try:
        for readiness in ("done", "both", "reverse_both"):
            case = _handoff_dependency_guardian_case(unit, readiness)
            assert case.packets == case.downstream == [] and case.caught is None
        selector_error = RuntimeError("UNIT_HANDOFF_GUARDIAN_SELECTOR")
        interrupted = _handoff_dependency_guardian_case(unit, selector_error=selector_error)
        assert interrupted.caught is selector_error and interrupted.packets == []
        missing_helper = _handoff_dependency_guardian_case(
            unit, missing="_guardian_budget_diagnostic")
        assert type(missing_helper.caught) is NameError and missing_helper.packets == []
        for missing in ("END", "json", "_guardian_budget_ready",
                        "_guardian_budget_clock", "_guardian_budget_write"):
            bound = _handoff_dependency_guardian_bind(unit)
            namespace = bound.namespace
            del namespace[missing]
            # END is also needed by the watchdog BEFORE the helper call.
            # Exercise the unchanged actual helper directly for all five
            # dependency negatives, without restoring/repairing any binding.
            assert namespace["_guardian_budget_diagnostic"]([], 402) is None
            case = SimpleNamespace(packets=namespace["_handoff_guardian_budget_packets"])
            assert case.packets == []
            with pytest.raises(AssertionError, match="HANDOFF_GUARDIAN_BUDGET_PACKET_REQUIRED"):
                _handoff_dependency_guardian_packet(unit, case, "timeout")
            unit.check()
    finally:
        unit.check()


def _handoff_dependency_guardian_span_tree(unit, *, span=None):
    """Fresh actual guardian AST, authenticated against separately trusted full R."""
    unit.check()
    source = unit.sources["retirement"]
    expected = unit.expected["retirement"]
    assert type(source) is bytes, "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"
    assert type(expected) is tuple and len(expected) == 2, "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"
    size, digest = expected
    assert type(size) is int and size > 0, "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"
    assert type(digest) is str and len(digest) == 64, "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"
    assert all(character in "0123456789abcdef" for character in digest), (
        "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH")
    assert len(source) == size and _handoff_dependency_sha256(source).hexdigest() == digest, (
        "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH")
    fixed = (
        114009, 120207, 6198, 2450,
        "77fe84ec091a34f002bc3de464bc0d71f020fdb4b525645ed836d0c2a8c4d859")
    if span is None:
        span = fixed
    assert type(span) is tuple and span == fixed, "HANDOFF_GUARDIAN_SPAN_METADATA_AUTH"
    start, stop, length, prefix_lf, span_digest = span
    assert 0 < start < stop <= len(source) and stop - start == length, (
        "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH")
    assert source[start - 1:start] == b"\n", "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH"
    assert source[:start].count(b"\n") == prefix_lf, "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH"
    actual = source[start:stop]
    assert len(actual) == length and _handoff_dependency_sha256(actual).hexdigest() == span_digest, (
        "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH")
    assert actual.startswith(b"def test_guardian_independent_safety_still_runs():\n"), (
        "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH")
    assert actual.endswith(b"\n\n\n") and source[stop:stop + 4] == b"def ", (
        "HANDOFF_GUARDIAN_SPAN_BOUNDARY_AUTH")
    tree = ast.parse(b"\n" * prefix_lf + actual)
    original, = tree.body
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "test_guardian_independent_safety_still_runs"
    assert (original.lineno, original.end_lineno) == (2451, 2577)
    unit.check()
    return tree


def test_handoff_dependency_guardian_span_ast_attributes():
    end = time.monotonic() + 3.0
    unit = None
    try:
        unit = _handoff_dependency_unit()
        assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        source = unit.sources["retirement"]
        whole = ast.parse(source)
        original, = [node for node in whole.body if isinstance(node, ast.FunctionDef)
                     and node.name == "test_guardian_independent_safety_still_runs"]
        actual, = _handoff_dependency_guardian_span_tree(unit).body
        assert ast.dump(original, include_attributes=True) == ast.dump(
            actual, include_attributes=True)
        unit.check()
    finally:
        try:
            if unit is not None:
                unit.check()
        finally:
            assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"


def test_handoff_dependency_guardian_span_isolation():
    end = time.monotonic() + 3.0
    unit = None
    try:
        unit = _handoff_dependency_unit()
        assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        first_tree = _handoff_dependency_guardian_span_tree(unit)
        second_tree = _handoff_dependency_guardian_span_tree(unit)
        # CPython deliberately shares operator/context singleton AST objects.
        shared = (ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)
        assert first_tree is not second_tree
        assert not ({id(node) for node in ast.walk(first_tree) if not isinstance(node, shared)}
                    & {id(node) for node in ast.walk(second_tree) if not isinstance(node, shared)})
        second_dump = ast.dump(second_tree, include_attributes=True)
        first_tree.body[0].name = "private_span_mutation"
        assert ast.dump(second_tree, include_attributes=True) == second_dump
        first = _handoff_dependency_guardian_bind(unit)
        second = _handoff_dependency_guardian_bind(unit)
        assert first is not second and first.namespace is not second.namespace
        assert first.writer is not second.writer
        assert first.namespace["_guardian_budget_diagnostic"] is not (
            second.namespace["_guardian_budget_diagnostic"])
        assert first.namespace["watchdog"] is not second.namespace["watchdog"]
        first_nodes = ast.Module(body=first.binding_nodes, type_ignores=[])
        second_nodes = ast.Module(body=second.binding_nodes, type_ignores=[])
        assert not ({id(node) for node in ast.walk(first_nodes) if not isinstance(node, shared)}
                    & {id(node) for node in ast.walk(second_nodes) if not isinstance(node, shared)})
        first_packets = first.namespace["_handoff_guardian_budget_packets"]
        second_packets = second.namespace["_handoff_guardian_budget_packets"]
        assert first_packets is not second_packets and first_packets == second_packets == []
        assert first.writer.__closure__[0].cell_contents is first_packets
        assert second.writer.__closure__[0].cell_contents is second_packets
        second_bind_dump = ast.dump(second_nodes, include_attributes=True)
        first.namespace["private_span_marker"] = True
        first.binding_nodes[0].lineno = -1
        assert first.writer(2, b"private-span-isolation\n") == len(b"private-span-isolation\n")
        assert first_packets == [(2, b"private-span-isolation\n")] and second_packets == []
        assert "private_span_marker" not in second.namespace
        assert ast.dump(second_nodes, include_attributes=True) == second_bind_dump
        assert second.namespace["_guardian_budget_write"] is second.writer
        unit.check()
    finally:
        try:
            if unit is not None:
                unit.check()
        finally:
            assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"


@pytest.mark.parametrize("corruption,guard", (
    ("binding-byte", "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"),
    ("unrelated-byte", "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"),
    ("shifted-span", "HANDOFF_GUARDIAN_SPAN_METADATA_AUTH"),
    ("bad-expected-pin", "HANDOFF_GUARDIAN_SPAN_SOURCE_AUTH"),
), ids=("binding-byte", "unrelated-byte", "shifted-span", "bad-expected-pin"))
def test_handoff_dependency_guardian_span_authentication(corruption, guard):
    end = time.monotonic() + 3.0
    unit = None
    try:
        unit = _handoff_dependency_unit()
        assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        positive, = _handoff_dependency_guardian_span_tree(unit).body
        assert positive.name == "test_guardian_independent_safety_still_runs"
        source = unit.sources["retirement"]
        expected = unit.expected["retirement"]
        copied = SimpleNamespace(
            sources=dict(unit.sources), expected=dict(unit.expected), check=unit.check)
        span = None
        if corruption == "binding-byte":
            index = source.index(b"guardian_diagnostic_packets = []", 114009, 120207)
            copied.sources["retirement"] = (
                source[:index] + bytes([source[index] ^ 1]) + source[index + 1:])
        elif corruption == "unrelated-byte":
            copied.sources["retirement"] = bytes([source[0] ^ 1]) + source[1:]
        elif corruption == "shifted-span":
            span = (
                114010, 120208, 6198, 2450,
                "77fe84ec091a34f002bc3de464bc0d71f020fdb4b525645ed836d0c2a8c4d859")
        else:
            assert corruption == "bad-expected-pin"
            copied.expected["retirement"] = (expected[0], "0" * 64)
        with pytest.raises(AssertionError, match=guard):
            _handoff_dependency_guardian_span_tree(copied, span=span)
        assert unit.sources["retirement"] is source
        assert unit.expected["retirement"] is expected
        unit.check()
    finally:
        try:
            if unit is not None:
                unit.check()
        finally:
            assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"


def test_handoff_dependency_guardian_span_comparative_parse(record_property):
    end = time.monotonic() + 3.0
    unit = None
    try:
        unit = _handoff_dependency_unit()
        assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        source = unit.sources["retirement"]
        baseline_text = source.decode()  # Original binder's str input, outside timing.
        whole_samples, span_samples = [], []
        reference = None
        for _ in range(3):
            for samples, parse in (
                    (whole_samples, lambda: ast.parse(baseline_text)),
                    (span_samples, lambda: _handoff_dependency_guardian_span_tree(unit))):
                unit.check()
                assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
                started = time.perf_counter()
                tree = parse()
                samples.append(time.perf_counter() - started)
                assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
                original, = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name == "test_guardian_independent_safety_still_runs"]
                actual = ast.dump(original, include_attributes=True)
                if reference is None:
                    reference = actual
                assert actual == reference
                unit.check()
                del original, tree  # Release each AST outside the timed parse.
                assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        assert len(whole_samples) == len(span_samples) == 3
        whole_median, span_median = sorted(whole_samples)[1], sorted(span_samples)[1]
        record_property("whole_parse_median_seconds", whole_median)
        record_property("authenticated_span_median_seconds", span_median)
        record_property("whole_parse_samples_seconds", json.dumps(whole_samples))
        record_property("authenticated_span_samples_seconds", json.dumps(span_samples))
        assert whole_median > 0 and span_median <= 0.5 * whole_median
        unit.check()
    finally:
        try:
            if unit is not None:
                unit.check()
        finally:
            assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"


def test_handoff_dependency_guardian_span_integrity():
    end = time.monotonic() + 3.0
    unit = None
    try:
        unit = _handoff_dependency_unit()
        assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
        source = unit.sources["retirement"]
        assert _handoff_dependency_source_pin(**unit.sources, expected=unit.expected) is None
        assert _HANDOFF_DEPENDENCY_BODY_SIZE == 634489
        assert _HANDOFF_DEPENDENCY_TAIL_SIZE == len(source) - 634489
        assert _handoff_dependency_sha256(source[:634489]).hexdigest() == (
            "471804bd9bc19258d91522d7162c2093d588fbd79a24dcbe4453b04d4d5f1020")
        assert _handoff_dependency_sha256(source[:400464]).hexdigest() == (
            "03c431fc28cd1276a201c7cdc217a41ad94e0ae0166ac2f4bc8c489924f47967")
        assert len(source[114009:120207]) == 6198
        assert source[:114009].count(b"\n") == 2450
        assert _handoff_dependency_sha256(source[114009:120207]).hexdigest() == (
            "77fe84ec091a34f002bc3de464bc0d71f020fdb4b525645ed836d0c2a8c4d859")
        restored = _handoff_dependency_stage_restore(**unit.sources)
        assert len(restored["retirement"]) == 632407
        assert _handoff_dependency_sha256(restored["retirement"]).hexdigest() == (
            "dae7e2a6dc88a1c1ed9480fa1891790d14cc86b9525b774d48e229f374cdf372")
        assert restored["canonical"] is unit.sources["canonical"]
        assert restored["lifecycle"] is unit.sources["lifecycle"]
        for name, (size, digest) in _HANDOFF_DEPENDENCY_BASELINE_EXPECTED.items():
            assert len(restored[name]) == size
            assert _handoff_dependency_sha256(restored[name]).hexdigest() == digest
        _handoff_dependency_check_table_text(unit, source)
        _handoff_dependency_check_table_text(unit, restored["retirement"])
        historical = _timeline_stage_rollback(**restored)
        assert _TIMELINE_STAGE_EXPECTED == {
            "canonical": (262043, "6526627438e0cca0778b6c27ea20655ce42ee3cba8bb377e5f06cf54182d9a06"),
            "lifecycle": (242360, "156b8877c8acc57565a9d5afc92b2179c9d34eac37e24e0bb2becba4648b7ba2"),
            "retirement": (554185, "523ff1dae21a6806fc61105b4830cddc8dd94b7a8608f2e5647c7168f71302a6"),
        }
        for name, (size, digest) in _TIMELINE_STAGE_EXPECTED.items():
            assert len(historical[name]) == size
            assert _handoff_dependency_sha256(historical[name]).hexdigest() == digest
        assert _timeline_history_inputs() == historical
        assert _close_guard_stage_restore(**unit.sources) == dict(
            canonical="57d241080fe314df5294d6395933ac91d27a32c35e3f9e061ec2ee64705c8a52",
            lifecycle="8a38a20dcd141e9e7fc96844b3cfcf91714d50d2b587814e478a1f1f1cfc7902",
            retirement="30a583960e87d5c767585c35aac3c2878edcc551a69520e4f55f639dbea6613c")
        unit.check()
    finally:
        try:
            if unit is not None:
                unit.check()
        finally:
            assert time.monotonic() < end, "HANDOFF_GUARDIAN_SPAN_UNIT3"
# HANDOFF_DEPENDENCY_STAGE_APPEND_END v1
