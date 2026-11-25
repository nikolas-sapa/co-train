"""SOURCE role-bounded cancellation probe, not cancellation authority.

Frozen numeric criteria precede implementation in canonical and scratch plan:
7 selected Tasks, 2 original scopes/owners, 1 actual native dispatch,
2 original public owner closes/ACKs (one NOT_STARTED).
PROGRAM: 2 PROGRAM allocations/0 SCORER; SCORER: 2 SCORER/0 PROGRAM.
Three exact-marker eval-caller cancels must really reach the target Env;
later two reach its same cleanup join while both public closes remain held.
Authorized EXACT4 history: marker1 at agent, EMPTY args() at cleanup, marker2
and marker3 at SAME cleanup, all builtin CancelledErrors on SAME original Env.
Await actual EMPTY before marker2 and recheck full history after caller drain.
PROGRAM's EMPTY is qualified; SCORER must independently prove it.
OTHER never qualifies. This recognizes only compatibility with the reported
SDK wave, never its originating callsite.
Two actual resource-close tasks per scope precede its first cleanup join;
all four original runner/scorer close bodies enter before either hold releases.
SCORER reuses two already-completed runner tasks, never four pending tasks.
No live target writer row, reward, fake ACK, direct Env cancellation, context
write, protected lifecycle patch, coroutine-local/closure inspection or new cap.
Public-return barriers do not imply continuous native ownership. Stock SDK
delivery failure is BLOCKED, not a substitute cancellation test. Physical
retirement/all-task-done proof remains HOST-owned; unknown-at-cap excluded.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace


CANCEL_PROGRAM_PHASE = "sdk-cancel-program"
CANCEL_SCORER_PHASE = "sdk-cancel-scorer"
_MARKERS = tuple("sdk PROGRAM eval cancellation " + str(index) for index in (1, 2, 3))


def _delivery_snapshot(index, error, target, *, agent, cleanup):
    """Catch-time scalars only; never retain a mutable exception-args alias."""
    from types import MappingProxyType
    marker = "OTHER"
    args = error.args if type(error) is asyncio.CancelledError else ()
    if type(error) is asyncio.CancelledError and args == ():
        marker = "EMPTY"
    elif len(args) == 1 and type(args[0]) is str:
        for number, known in enumerate(_MARKERS, 1):
            if args[0] == known:
                marker = str(number)
                break
    return MappingProxyType(dict(
        index=index if type(index) is int and 0 <= index <= 2**63-1 else 0,
        marker=marker,
        join=("AGENT" if target is not None and target is agent else
              "CLEANUP" if target is not None and target is cleanup else "OTHER"),
        error="CancelledError" if type(error) is asyncio.CancelledError else "OTHER"))


def _validate_delivery_history(notes, *, scope, env):
    """Complete raw target history only; captured scalars are NOT authority."""
    from types import MappingProxyType
    assert len(notes) == 4, "SDK_CANCEL_EXACT_FOUR_DELIVERIES"
    agent, cleanup = scope.agent_task, scope.cleanup_task
    assert all(isinstance(task, asyncio.Task) for task in (env, agent, cleanup))
    assert agent is not cleanup and env is not agent and env is not cleanup
    expected_args = ((_MARKERS[0],), (), (_MARKERS[1],), (_MARKERS[2],))
    expected_markers = ("1", "EMPTY", "2", "3")
    prior_index = 0
    for position, note in enumerate(notes):
        assert note.scope is scope and note.task is env, "SDK_CANCEL_ENV_IDENTITY"
        target = agent if position == 0 else cleanup
        assert note.target is target, "SDK_CANCEL_JOIN_IDENTITY"
        assert type(note.error) is asyncio.CancelledError, "SDK_CANCEL_EXCEPTION_TYPE"
        args = note.error.args
        assert type(args) is tuple and len(args) == len(expected_args[position]), (
            "SDK_CANCEL_EXACT_ARGUMENT_SHAPE")
        assert not args or type(args[0]) is str, "SDK_CANCEL_EXACT_ARGUMENT_TYPE"
        assert args == expected_args[position], "SDK_CANCEL_EXACT_ARGUMENTS"
        snapshot = note.snapshot
        assert type(snapshot) is MappingProxyType, "SDK_CANCEL_MUTABLE_CAPTURE"
        assert set(snapshot) == {"index", "marker", "join", "error"}
        index = snapshot["index"]
        assert type(index) is int and prior_index < index <= 2**63-1
        prior_index = index
        assert snapshot["marker"] == expected_markers[position]
        assert snapshot == _delivery_snapshot(
            index, note.error, note.target, agent=agent, cleanup=cleanup), (
                "SDK_CANCEL_CAPTURE_CURRENT_MISMATCH")


def _delivery_diagnostic(notes, *, agent, cleanup):
    rows = []
    for note in notes[:32]:
        snapshot = note.snapshot
        index = snapshot["index"]
        captured = dict(
            index=index if type(index) is int and 0 <= index <= 2**63-1 else 0,
            marker=snapshot["marker"] if snapshot["marker"] in ("1", "EMPTY", "2", "3") else "OTHER",
            join=snapshot["join"] if snapshot["join"] in ("AGENT", "CLEANUP") else "OTHER",
            error="CancelledError" if snapshot["error"] == "CancelledError" else "OTHER")
        current = _delivery_snapshot(
            index, note.error, note.target, agent=agent, cleanup=cleanup)
        rows.append(dict(snapshot=captured, current_marker=current["marker"]))
    report = dict(notes=rows, total=len(notes), omitted=len(notes)-len(rows))
    while len(json.dumps(report, separators=(",", ":")).encode("utf-8")) > 8064 and rows:
        rows.pop()
        report["omitted"] += 1
    return report


class _SdkProgramCancellation:
    def __init__(self, *, api, core, actor, profile, executor, owners, closes,
                 programs, scorers, rewards, results, sdk_tasks, controller_gates,
                 role="program"):
        assert type(role) is str and role in ("program", "scorer")
        self.role = role
        self.api, self.core, self.actor = api, core, actor
        self.profile, self.executor = profile, executor
        self.owners, self.closes = owners, closes
        self.programs, self.scorers = programs, scorers
        self.rewards, self.results, self.sdk_tasks = rewards, results, sdk_tasks
        self.controller_gates = controller_gates
        self.resource_tasks, self.resource_bodies = [], []
        self._resource_scopes, self._score_children = {}, {}
        self.owner_holds, self.delivered, self.issued = [], [], []
        self.env_tasks, self.first_joins = {}, {}
        self.retained, self.finished_scopes = set(), set()
        self.seen_events = set()
        self.caller = None
        self.releasing = False
        self.hooks = api._HOOKS
        self.close_resource = api._close_resource
        self.shield, self.create_task = asyncio.shield, asyncio.create_task

    def progress(self):
        self.actor.emit("SDK_CANCEL_PROGRESS")

    def install(self, patch):
        def observed_create_task(coroutine, *args, **kwargs):
            # Code identity only. Never inspect coroutine frames/locals.
            selected = getattr(coroutine, "cr_code", None) is self.close_resource.__code__
            scope = self.api._rollout.get() if selected else None  # READ ONLY.
            actual = self.create_task(coroutine, *args, **kwargs)
            if selected:
                assert scope is not None
                self.actor.retirement.retain_cleanup(actual, "resource-close")
                self.resource_tasks.append(SimpleNamespace(scope=scope, task=actual))
                self._resource_scopes[actual] = scope
                self.retained.add(actual)  # Original task, before its first await.
                self.progress()
            return actual

        async def observed_shield(awaitable):
            scope, current = self.api._rollout.get(), asyncio.current_task()
            if scope is not None:
                if awaitable is scope.agent_task:
                    previous = self.env_tasks.setdefault(id(scope), current)
                    assert previous is current
                    self.retained.add(current)
                    self.actor.retirement.retain_task(current)
                    self.actor.retirement.retain_task(awaitable)
                tasks = [row.task for row in self.resource_tasks if row.scope is scope]
                cleanup_join = (scope.cleanup_task is not None
                                and awaitable is scope.cleanup_task)
                if cleanup_join:
                    self.actor.retirement.retain_cleanup(awaitable, "scope-drain")
                resource_join = any(awaitable is task for task in tasks)
                if self.issued and (cleanup_join or resource_join):
                    assert len(tasks) == 2, "SDK_CANCEL_START_ALL_BEFORE_FIRST_JOIN"
                    if self.role == "scorer":
                        self._check_resource_tasks(scope, tasks)
                    self.first_joins.setdefault(id(scope), tuple(tasks))
                    if isinstance(awaitable, asyncio.Task):
                        self.retained.add(awaitable)
            try:
                return await self.shield(awaitable)
            except asyncio.CancelledError as exc:
                if (scope is not None and current is self.env_tasks.get(id(scope))
                        and (awaitable is scope.agent_task
                             or awaitable is scope.cleanup_task)):
                    snapshot = _delivery_snapshot(
                        len(self.delivered)+1, exc, awaitable,
                        agent=scope.agent_task, cleanup=scope.cleanup_task)
                    self.delivered.append(SimpleNamespace(
                        scope=scope, task=current, target=awaitable, error=exc,
                        snapshot=snapshot))
                    self.progress()
                raise  # Same actual delivered exception, never reconstruct.

        original_release = self.actor.retirement.release

        def release_for_retirement():
            original_release()  # Real intents BEFORE any controller release.
            self.releasing = True
            self.actor.retirement.attempt_each(
                "public-hold", tuple(self.owner_holds),
                lambda hold: None if hold.release.is_set() else hold.release.set())
            self.actor.test_gates.release_pending()

        self.actor.retirement.release = release_for_retirement
        patch.setattr(asyncio, "create_task", observed_create_task)
        patch.setattr(asyncio, "shield", observed_shield)

    def _check_resource_tasks(self, scope, tasks):
        assert len(tasks) == 2 and tasks[0] is not tasks[1]
        originals = [task for task, original_scope in self._resource_scopes.items()
                     if original_scope is scope]
        assert len(originals) == 2
        assert all(task is original for task, original in zip(tasks, originals, strict=True))
        assert all(isinstance(task, asyncio.Task) and task in self.retained
                   and self._resource_scopes.get(task) is scope for task in tasks)
        program, = [row for row in self.programs if row.scope is scope]
        runner_body, = [row for row in self.resource_bodies
                        if row.scope is scope and row.kind == "runner"]
        assert runner_body.record is program and runner_body.task is tasks[0]
        assert len(program.runners) == len(program.closes) == 1
        runner, runner_task = program.closes[0]
        assert runner is program.runners[0] and runner_task is tasks[0]
        assert runner_task.done() and not runner_task.cancelled()
        assert runner_task.cancelling() == 0 and runner_task.result() is None
        scorer_bodies = [row for row in self.resource_bodies
                         if row.scope is scope and row.kind == "scorer"]
        # start_all creates the original scorer Task before its body can run.
        # Creation-time scope provenance is already retained above, no yield.
        assert len(scorer_bodies) <= 1
        if scorer_bodies:
            body, = scorer_bodies
            scorer, = [row for row in self.scorers if row.actual is scope.scorer]
            assert body.record is scorer and body.task is tasks[1]
            assert scorer.closes == [tasks[1]]

    def retain_score_children(self, scope):
        """Observe actual original children only; original scope drains them."""
        assert self.role == "scorer"
        pair = (scope.task_score, scope.harness_score)
        assert all(isinstance(task, asyncio.Task) for task in pair)
        assert pair[0] is not pair[1]
        existing = self._score_children.get(id(scope))
        if existing is not None:
            assert existing.scope is scope
            assert all(task is original for task, original in zip(
                pair, existing.tasks, strict=True))
            return
        pending = tuple(not task.done() for task in pair)
        self._score_children[id(scope)] = SimpleNamespace(
            scope=scope, tasks=pair, pending=pending)
        for task, was_pending in zip(pair, pending, strict=True):
            self.retained.add(task)
            self.actor.retirement.retain_task(task)
            if not was_pending:
                assert not task.cancelled() and task.exception() is None
                assert task.result() is None  # Completed Harness.score is not cancelled.

    def check_score_children(self, scope):
        """Validate retained identities/results after ORIGINAL scope cleanup."""
        original = self._score_children.get(id(scope))
        assert original is not None and original.scope is scope
        pair = (scope.task_score, scope.harness_score)
        assert all(isinstance(task, asyncio.Task) and task is retained
                   for task, retained in zip(pair, original.tasks, strict=True))
        for task, was_pending in zip(pair, original.pending, strict=True):
            assert task in self.retained and task.done()
            if was_pending:
                assert task.cancelled() and task.cancelling() > 0
            else:
                assert not task.cancelled() and task.cancelling() == 0
                assert task.exception() is None and task.result() is None

    def resource_body(self, kind, record):
        scope = self.api._rollout.get()
        current = asyncio.current_task()
        self.actor.retirement.retain_cleanup(current, "resource-close")
        assert scope is not None
        resource_task, = [row for row in self.resource_tasks
                          if row.scope is scope and row.task is current]
        assert not any(row.task is current for row in self.resource_bodies)
        if self.role == "scorer":
            assert kind in ("runner", "scorer") and record.scope is scope
            assert self._resource_scopes.get(current) is scope
            assert not any(row.scope is scope and row.kind == kind
                           for row in self.resource_bodies)
            if kind == "runner":
                assert any(record is row for row in self.programs)
                assert record.harness is scope.program and len(record.runners) == 1
                assert record.closes == [(record.runners[0], current)]
            else:
                assert any(record is row for row in self.scorers)
                assert record.actual is scope.scorer and record.closes == [current]
        self.resource_bodies.append(SimpleNamespace(
            kind=kind, record=record, scope=scope, task=resource_task.task))
        self.retained.add(current)
        self.progress()

    async def close_owner(self, actual, record, original):
        self.actor.retirement.retain_cleanup(asyncio.current_task(), "owner-close")
        assert len(self.owners) == 2 and actual.role == self.role
        assert not any(hold.actual is actual for hold in self.owner_holds)
        assert record.task is asyncio.current_task()
        receipt = actual.request_cancel("runner_closed")  # Actual public API.
        intent = actual.snapshot().intent
        assert receipt.status in ("accepted", "repeated") and receipt.intent is intent
        assert intent is not None and intent.invocation_id == actual.invocation_id
        assert intent.deadline_ns == intent.requested_ns + 12_000_000_000
        hold = SimpleNamespace(actual=actual, record=record, receipt=receipt,
                               intent=intent, release=asyncio.Event(), delegated=0)
        self.owner_holds.append(hold)
        self.retained.add(record.task)
        if self.releasing:
            self.actor.ensure_intents()
            hold.release.set()  # Failure retirement only, never qualification.
        self.progress()
        await hold.release.wait()
        hold.delegated += 1
        ack = await original(actual)
        record.ack = ack
        assert ack is actual._completion.cleanup_ack is actual._authority.ack
        self.progress()
        return ack

    def blocked(self, reason):
        assert reason in ("CALLER_ESCAPED", "MARKER_DELIVERY")
        target = self.owners[0].scope
        self.actor.retirement.record_outcome(dict(
            ok=False, decision="blocked", blocked=reason,
            caller_cancellations=len(self.issued),
            delivered_cancellations=sum(note.scope is target for note in self.delivered),
            owner_closes=len(self.closes),
            pending_owner_closes=sum(not hold.record.task.done() for hold in self.owner_holds)))
        raise AssertionError("SDK_" + self.role.upper() + "_CANCELLATION_BLOCKED_" + reason) from None

    async def until(self, predicate, *, delivery=False):
        while not predicate():
            if self.caller is not None and self.caller.done():
                self.blocked("CALLER_ESCAPED")
            try:
                await self.actor.next_event(lambda item: item["kind"] == "SDK_CANCEL_PROGRESS")
            except TimeoutError:
                if delivery:
                    self.blocked("MARKER_DELIVERY")
                raise

    def _diagnose_deliveries(self, scope):
        try:
            self.actor.diagnostic("SDK_CANCEL_DELIVERY", _delivery_diagnostic(
                [note for note in self.delivered if note.scope is scope],
                agent=scope.agent_task, cleanup=scope.cleanup_task))
        except BaseException:
            pass  # Never replace original exceptions or interrupt retirement.

    async def _wait_empty_cleanup(self, scope):
        try:
            await self.until(lambda: sum(note.scope is scope for note in self.delivered) >= 2,
                             delivery=True)
        finally:
            self._diagnose_deliveries(scope)  # BEFORE gate, even on missing delivery.
        notes = [note for note in self.delivered if note.scope is scope]
        assert len(notes) == 2, "SDK_CANCEL_EMPTY_HISTORY"
        note = notes[1]
        assert note.task is self.env_tasks[id(scope)], "SDK_CANCEL_ENV_IDENTITY"
        assert scope.cleanup_task is not None and note.target is scope.cleanup_task
        assert type(note.error) is asyncio.CancelledError and note.error.args == (), (
            "SDK_CANCEL_EXACT_EMPTY_REQUIRED")
        assert note.snapshot["marker"] == "EMPTY"
        assert note.snapshot == _delivery_snapshot(
            note.snapshot["index"], note.error, note.target,
            agent=scope.agent_task, cleanup=scope.cleanup_task), (
                "SDK_CANCEL_CAPTURE_CURRENT_MISMATCH")

    async def event_for(self, actual, kind, name=None):
        def matches(item):
            return (id(item) not in self.seen_events
                    and item.get("invocation_id") == actual.invocation_id.hex
                    and item["kind"] == kind
                    and (name is None or item.get("name") == name))

        # Progress waits may already have consumed a real native observation.
        # Reuse its original object, once, never replay/fabricate a notification.
        observed = [*self.actor.messages,
                    *(item for slot in self.actor.slots for item in slot["messages"])]
        item = next((item for item in observed if matches(item)), None)
        if item is None:
            item = await self.actor.next_event(matches)
        self.seen_events.add(id(item))
        return item

    def held(self, read_rows):
        assert not self.caller.done() and len(self.owners) == 2
        assert len(self.owner_holds) == len(self.closes) == 2
        assert len({id(hold.record.task) for hold in self.owner_holds}) == 2
        for hold in self.owner_holds:
            assert hold.delegated == 0 and not hold.release.is_set()
            assert not hold.record.task.done() and hold.record.task.cancelling() == 0
            assert hold.actual.snapshot().intent is hold.intent is hold.receipt.intent
            assert hold.intent.deadline_ns == hold.intent.requested_ns + 12_000_000_000
        assert len(self.resource_tasks) == len(self.resource_bodies) == 4
        if self.role == "scorer":
            assert sum(row.task.done() for row in self.resource_tasks) == 2
            assert all(row.task.cancelling() == 0 for row in self.resource_tasks)
            assert all(row.task.done() is (row.kind == "runner")
                       for row in self.resource_bodies)
        for program in self.programs:
            scope = program.scope
            assert scope.live and scope.token is program.token is scope.issued_token
            assert not scope.authority and scope.failed and not scope.published
            assert scope.agent_task is not None and not scope.agent_task.done()
            assert scope.cleanup_task is not None and not scope.cleanup_task.done()
            assert not self.env_tasks[id(scope)].done()
            assert len(self.first_joins[id(scope)]) == 2
            assert {id(task) for task in self.first_joins[id(scope)]} == {
                id(row.task) for row in self.resource_tasks if row.scope is scope}
            if self.role == "scorer":
                self._check_resource_tasks(scope, self.first_joins[id(scope)])
                children = self._score_children[id(scope)]
                assert children.tasks[0] is scope.task_score and not scope.task_score.done()
                assert children.tasks[1] is scope.harness_score
            assert scope.trace.rewards == {} and not scope.trace.ok
        assert not self.rewards and not self.results
        rows = read_rows()
        assert not any(row["ok"] or any(trace["ok"] for trace in row["traces"]) for row in rows)
        target_ids = {program.scope.trace.id for program in self.programs}
        assert not any(trace["id"] in target_ids for row in rows for trace in row["traces"])

    async def qualify(self, *, caller, config, admitted, public_data, policy,
                      instrument, state, entered, read_rows, documents,
                      program_calls=()):
        self.caller = caller
        self.retained.add(caller)
        caller.add_done_callback(lambda _: self.progress())
        assert len(entered) == len(self.owners) == len(self.programs) == len(self.scorers) == 2
        assert len(self.sdk_tasks) == len(public_data) == 7
        assert all(task.data is data for task, data in zip(self.sdk_tasks, public_data, strict=True))
        assert (len(admitted.planned), len(admitted.eligible), len(admitted.exclusions)) == (8, 7, 1)
        assert (config.num_tasks, config.num_rollouts, config.shuffle,
                config.max_concurrent) == (7, 1, False, 2)
        assert (instrument.action_cap, instrument.action_max_rows,
                instrument.program_timeout_s) == (2, 3, 5.0)
        first, second = self.owners
        assert first.scope is not second.scope and first.sdk_task is not second.sdk_task
        assert first.scope.data is not second.scope.data and first.scope.trace is not second.scope.trace
        assert first.scope.runtime is not second.scope.runtime
        assert all(row.actual.role == self.role for row in self.owners)
        barrier = "adapter-cancel" if self.role == "program" else "score-adapter-cancel"
        self.controller_gates[0].set()  # Only the first original controller enters admission.
        delivered = await self.event_for(first.actual, "HIT", barrier)
        if self.role == "program":
            assert delivered["event"] == "REQUEST_DELIVERED"
        else:
            # Existing score-adapter-cancel HIT has no event field. Its
            # original guardian writes/fsyncs this actual record BEFORE HIT.
            job = self.executor.state_dir / first.actual.invocation_id.hex
            events = [json.loads(line) for line in (job / "events.jsonl").read_bytes().splitlines()]
            request_event, = [event for event in events
                              if event.get("kind") == "REQUEST_DELIVERED"]
            assert request_event["request_sha256"] == first.actual.snapshot().request_sha256
            assert request_event["request_sha256"] == self.core.request_sha256(first.actual.request)
        slot, = self.actor.slots
        assert slot["invocation"] is first.actual and not self.controller_gates[1].is_set()
        creator, = self.actor.trace.fence()
        assert creator["process"] is slot["process"]
        assert creator["process"] in creator["registry"] and creator["process"].poll() is None
        resources = [item for item in slot["messages"] if item["kind"] == "RESOURCE"]
        assert any(item["actor"] == "role" for item in resources)
        assert any(item["actor"] == "cli" for item in resources)
        assert all(item["registered"] for item in resources)
        if self.role == "scorer":
            assert not program_calls and all(owner.role == "scorer" for owner in self.actor.owners)
            assert all(not any(message.get("role") == "tool" for message in body["messages"])
                       for body in policy.bodies)
            for owner in self.owners:
                scope, scorer = owner.scope, owner.scorer
                assert owner.sdk_task is scope.task and owner.task is scope.private
                assert scorer.actual is scope.scorer and scorer.scope is scope
                assert scorer.score_task is scope.task_score and scope.result is None
                job, = scorer.actual._jobs
                assert job.invocation is owner.actual
                assert job.request_sha256 == self.core.request_sha256(owner.actual.request)
                owner.score_job = job  # Original private job, observation only.
                assert not scope.task_score.done()
                self.retain_score_children(scope)
        target = first.scope
        for index, marker in enumerate(_MARKERS):
            if index:
                self.held(read_rows)
            self.issued.append(marker)
            assert caller.cancel(marker)
            await self.until(lambda: any(
                note.scope is target and note.error.args == (marker,)
                for note in self.delivered), delivery=True)
            note, = [note for note in self.delivered
                     if note.scope is target and note.error.args == (marker,)]
            assert type(note.error) is asyncio.CancelledError
            assert note.task is self.env_tasks[id(target)]
            if index == 0:
                assert note.target is target.agent_task
                await self.until(lambda: len(self.owner_holds) == 2
                                 and len(self.resource_bodies) == 4
                                 and all(program.scope.cleanup_task is not None
                                         for program in self.programs))
                self.held(read_rows)
                second_hold, = [hold for hold in self.owner_holds if hold.actual is second.actual]
                assert second.actual.snapshot().intent is second_hold.intent
                self.controller_gates[1].set()  # AFTER real preSTART intent only.
                first_hold, = [hold for hold in self.owner_holds if hold.actual is first.actual]
                consumed = {}
                while len(consumed) < 2:
                    item = await self.event_for(first.actual, "CONSUMED")
                    assert item["lane"] not in consumed
                    assert item["times"] == [
                        first_hold.intent.requested_ns, first_hold.intent.deadline_ns]
                    consumed[item["lane"]] = item
                assert set(consumed) == {"host", "guardian"}
                self.actor.release(first.actual)  # REQUEST_DELIVERED token.
                await self.event_for(first.actual, "HIT", "cleanup-held")
                await self._wait_empty_cleanup(target)
            else:
                assert note.target is target.cleanup_task
                prior, = [old for old in self.delivered
                          if old.scope is target and old.error.args == (_MARKERS[1],)]
                assert note.task is prior.task and note.target is prior.target
                self.held(read_rows)
        target_notes = [note for note in self.delivered if note.scope is target]
        self._diagnose_deliveries(target)
        _validate_delivery_history(target_notes, scope=target, env=self.env_tasks[id(target)])
        assert caller.cancelling() == len(self.issued) == 3
        self.held(read_rows)
        self.actor.release(first.actual)  # Distinct cleanup-held release, matched above.
        for hold in self.owner_holds:
            hold.release.set()
        await self.until(caller.done)  # Existing HOST event/deadline bound only.
        target_notes = [note for note in self.delivered if note.scope is target]
        self._diagnose_deliveries(target)
        _validate_delivery_history(target_notes, scope=target, env=self.env_tasks[id(target)])
        assert caller.cancelling() == len(self.issued) == 3
        assert caller.cancelled(), "SDK_CANCEL_EVAL_CALLER_NOT_CANCELLED"
        try:
            caller.result()
        except asyncio.CancelledError as exc:
            assert type(exc) is asyncio.CancelledError
        else:
            raise AssertionError("SDK_CANCEL_EVAL_CALLER_NOT_CANCELLED")
        for program in self.programs:
            scope = program.scope
            for task in (scope.agent_task, scope.task_score, scope.harness_score,
                         scope.cleanup_task):
                if task is not None:
                    self.retained.add(task)
            assert not scope.live and scope.token is None and not scope.authority
            assert scope.cleanup_task.done() and not scope.cleanup_task.cancelled()
            assert scope.cleanup_task.exception() is None and not scope.published
            assert not scope.trace.ok and not scope.trace.rewards
            self.finished_scopes.add(id(scope))
            bodies = [row for row in self.resource_bodies if row.scope is scope]
            assert {row.kind for row in bodies} == {"runner", "scorer"} and len(bodies) == 2
            runner_body, = [row for row in bodies if row.kind == "runner"]
            scorer_body, = [row for row in bodies if row.kind == "scorer"]
            scorer, = [row for row in self.scorers if row.actual is scope.scorer]
            assert runner_body.record is program and scorer_body.record is scorer
            assert program.closes == [(program.runners[0], runner_body.task)]
            assert scorer.closes == [scorer_body.task] and scorer.result is None
            assert program.validations == [(program.runners[0], 5.0)]
            assert program.context.get(self.api._rollout) is scope
            assert scope.program is program.harness and scope.task.data is scope.data
            assert program.kwargs["task"] is scope.private
            assert program.kwargs["data"] is scope.data
            assert any(scope.runtime is runtime for runtime in state.runtimes)
            if self.role == "scorer":
                self.check_score_children(scope)
                assert scorer.scope is scope and scorer.score_task is scope.task_score
                assert type(scorer.cancel_error) is asyncio.CancelledError
                assert scope.result is None and not program_calls
        assert all(task.done() for task in self.retained)
        for task in self.retained:
            if not task.cancelled():
                assert task.exception() is None
        for index, owner in enumerate(self.owners):
            actual = owner.actual
            hold, = [hold for hold in self.owner_holds if hold.actual is actual]
            completion, ack = actual._completion, hold.record.ack
            assert hold.delegated == 1 and hold.record.task.done()
            assert actual.executor is self.executor and self.executor.profile is self.profile
            assert type(completion) is self.core.InvocationCompletion
            assert type(ack) is self.core.CleanupCompleteAck
            assert ack is completion.cleanup_ack is actual._authority.ack
            assert ack._authority.owner is actual and ack.role == self.role
            assert ack.invocation_id == actual.invocation_id
            assert ack.request_sha256 == self.core.request_sha256(actual.request)
            assert ack.profile_sha256 == self.core.execution_profile_sha256(self.profile)
            assert ack.released and ack.not_started is (index == 1)
            assert completion.outcome is None and completion.abort.kind == "cancelled"
            assert completion.abort.detail_code == "cancelled"
            assert actual.snapshot().intent is hold.intent
            assert not actual._thread.is_alive()
            assert actual.db_path == Path(owner.task.db_path)
            db, = [db for db in admitted.databases if db.db_id == owner.task.db_id]
            assert actual.request.db_sha256 == db.sha256
            if self.role == "program":
                assert actual.request.max_rows == 3
            else:
                job, = owner.scorer.actual._jobs
                assert job is owner.score_job and job.invocation is actual
                assert job.close_task is hold.record.task and job.ack is ack
                assert job.request_sha256 == ack.request_sha256
                assert owner.kwargs["instrument"] is instrument
                assert owner.scorer.kwargs["instrument"] is instrument
                assert owner.scorer.kwargs["task"] is owner.task
                assert actual.request.max_rows == instrument.scorer_max_rows
                assert actual.request.timeout_s == instrument.scorer_timeout_s
                assert actual.request.compare == instrument.compare
                assert actual.request.predicted_sql == owner.prediction
                assert actual.request.task.gold_sql == owner.task.gold_sql
                assert actual.request.task.db_path == "/db.sqlite"
            if index == 0:
                assert ack.child_waits and ack.thread_joins and len(ack.guardian_reaps) == 1
                if self.role == "scorer":
                    assert actual._children == [creator["process"]]
                    assert ack.guardian_reaps == ((
                        creator["process"].pid, creator["process"].returncode),)
            else:
                assert not ack.child_waits and not ack.thread_joins and not ack.guardian_reaps
                assert not any(item["invocation"] is actual for item in self.actor.slots)
                if self.role == "scorer":
                    assert not actual._children
        assert len(self.actor.owners) == 2 and len(self.actor.slots) == 1
        assert creator["process"]._creator_waited and not creator["process"]._creator_ambiguous
        assert type(creator["process"].returncode) is int
        assert not self.rewards and not self.results and policy.calls == len(policy.bodies) == 2
        assert len(state.agents) == len(state.runtimes) == 2
        assert all(agent.harness is original for agent, original in state.agents)
        assert not state.external and not state.channels and not self.actor.forbidden_calls
        assert self.api._HOOKS is self.hooks and self.api._close_resource is self.close_resource
        evidence = await self.event_for(first.actual, "EVIDENCE")
        actuals = evidence["actual"]
        assert not evidence["forbidden"] and not evidence["fault_hits"] and evidence["released"]
        assert evidence["hits"] == [barrier, "cleanup-held"]
        assert evidence["monitor_times"] == [[
            first_hold.intent.requested_ns, first_hold.intent.deadline_ns]]
        assert evidence["accounted"] == [True]
        assert sum(row["actor"] == "role" for row in actuals) == 1
        assert sum(row["actor"] == "cli" for row in actuals) >= 2
        assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                   and type(row["returncode"]) is int for row in actuals)
        rows = read_rows()
        assert not any(row["ok"] or any(trace["ok"] for trace in row["traces"]) for row in rows)
        assert {trace["id"] for row in rows for trace in row["traces"]} <= {
            program.scope.trace.id for program in self.programs}
        public = json.dumps([policy.bodies, rows])
        assert "gold_sql" not in public and "db_path" not in public
        assert all(value not in public for task in admitted.planned
                   for value in (task.gold_sql, task.db_path))
        assert all(path.read_bytes() == original for path, original in documents)
        return dict(
            decision="cancellation-qualified", evaluation_cancelled=caller.cancelled(),
            selected_tasks=len(self.sdk_tasks), scopes=len(self.programs),
            allocations=len(self.owners), dispatches=len(self.actor.slots),
            program_dispatches=sum(slot["invocation"].role == "program"
                                   for slot in self.actor.slots),
            scorer_dispatches=sum(slot["invocation"].role == "scorer"
                                  for slot in self.actor.slots),
            program_calls=len(program_calls),
            score_children=sum(len(row.tasks) for row in self._score_children.values()),
            cancelled_score_children=sum(task.cancelled()
                for row in self._score_children.values() for task in row.tasks),
            completed_score_children=sum(not task.cancelled()
                for row in self._score_children.values() for task in row.tasks),
            observed_score_cancellations=sum(
                type(getattr(row, "cancel_error", None)) is asyncio.CancelledError
                for row in self.scorers),
            acks=sum(hold.record.ack is hold.actual._authority.ack for hold in self.owner_holds),
            not_started_acks=sum(hold.record.ack.not_started for hold in self.owner_holds),
            owner_closes=len(self.closes), resource_tasks=len(self.resource_tasks),
            resource_close_bodies=len(self.resource_bodies),
            start_all_scopes=len(self.first_joins), caller_cancellations=len(self.issued),
            delivered_cancellations=len(target_notes),
            empty_cleanup_deliveries=sum(
                note.target is target.cleanup_task and note.error.args == ()
                for note in target_notes),
            cleanup_join_deliveries=sum(
                note.target is target.cleanup_task for note in target_notes),
            same_cleanup_join_cancellations=sum(
                note.target is target.cleanup_task
                and note.error.args in ((_MARKERS[1],), (_MARKERS[2],))
                for note in target_notes),
            consumed_lanes=len(consumed), revoked_scopes=len(self.finished_scopes),
            retained_tasks=len(self.retained),
            live_retained_tasks=sum(not task.done() for task in self.retained),
            rewards=len(self.rewards), returned_results=len(self.results),
            successful_rows=sum(row["ok"] for row in rows),
            rows=len(rows), policy_requests=policy.calls)
