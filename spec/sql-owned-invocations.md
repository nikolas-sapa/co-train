# Owned SQL invocation cancellation

2026-10-31. Selected source-engineering contract. Not native/profile approval.
Base main: `9149df4e3323aa5f17807243e8216462d578c06d`.

## Test plan, before implementation

All phase-one tests use synthetic profiles, fake transports and real
creator-owned first-party subprocesses. No Docker/daemon/network, provider,
model, corpus or SQL execution.

| Gate | Numeric acceptance |
| --- | --- |
| Role/race matrix | Eight boundaries for each role, 16 cases: predispatch, creation/prepublication, startup wait, pre-START, inflight, result reception, finalization publication, post-wire-ACK/pre-host-seal. One selected hook hit. No usable result after accepted cancellation. |
| Responsive cleanup | PROGRAM and scorer host ACK within one absolute 12.000s budget from first accepted host intent; actual creator child waits and thread joins, zero remaining owned actors. |
| Repeated intent | Three requests, two during cleanup; same immutable intent object, timestamp and deadline. Caller held until ACK. |
| Async caller cancellation | Both roles: three `Task.cancel()` calls against started `execute()`, including two during held cleanup. Caller remains pending until actual cleanup ACK, then raises original `CancelledError`; same first intent/deadline, one dispatch. |
| Concurrent callers | Both roles: two started `execute()` callers join exactly one dispatch and receive the identical retained completion; subsequent close returns its identical ACK. |
| Live journal replacement | Force one atomic replacement between open/initial inspection and during read, separately. Discard each unlinked snapshot and reread within the existing host cap; observe the replacement once. Strict artifact reads, in-place mutation and actual hardlinks still fail. No command replay or new deadline. |
| Frame validation | Reject every truncated length0–39, length41, bad magic/UUID, invalid/overflowing deadline arithmetic and future timestamp. Valid delayed frames never extend the deadline. |
| Wait notification | Responsive startup, transport and terminal-ACK fixtures observe cancellation within0.100s, without controller EOF. |
| Creation faults | One postcreation/prepublication failure for guardian and CLI respectively. Actual objects retained before failure; direct children waited before any clean ACK. |
| Unknown proof | Withhold one stop/join proof. At deadline, incomplete snapshot, retained ownership/barrier, zero ACKs; execute/close remain pending. Independent fixture teardown does not upgrade the tested outcome. |
| Late delivery | Cancel after guardian monitor retirement but before host seal. Valid independent complete proof permits cancelled completion despite EPIPE/EBADF; ambiguous proof remains incomplete. |
| Postcompletion | Receipt `already_completed`, no accepted intent and zero notification writes after host seal. |
| Post-reap fault | One fault, zero clean ACKs and zero process-group signals. Reaping cannot restore signal authority. |
| Canonical sensitivity | Ownership-registration and cleanup-validation mutations each hit once and fail one named intended ownership assertion; retained safety teardown and restored positives. Canary-only control insufficient. |
| Compatibility | Legacy executor/harness call shapes; worker default5s, PROGRAM ceiling10,000ms/scorer30,000ms; existing memory/admission limits unchanged. |
| Review regressions | A valid historical success released before R can be committed and resource-validated after R but before its unchanged cleanup cap; default success eligibility still rejects it. One malformed cleanup frame and one delayed extra byte each remain a protocol failure after monitor join. An identical monitor fault accounted in published typed abort may retire; an unaccounted/new fault prevents ACK. |
| Fixture safety | Exited guardian without independent nested-child SAFE proof cannot yield fixture safety. One missing-proof rejection and one restored proof acceptance; test-only lifetime owners cannot exit before nested cleanup. Not a canonical ownership mutant. |

Future SDK gates are deferred: actual VM-progress-triggered cancellation,
three caller cancellations, no extra policy/program/scorer/rollout-finalize
dispatch after abort, fresh integer42/EX1/exactly one completed original-writer
JSONL row, unsupported binding/timeout/MCP/QA/catalog refused before model.
Phase one does not claim these gates.

## Non-goals

No native/profile activation or qualification, source-pin updates, runtime/model/
draw/spend selection, campaign/training, SDK changes, BIRD configured binding,
generic tracer changes, process-group signals, action replay, or universal
bounded caller return with unknown resource liveness.

## Decision and evidence

User delegated the transport decision; selected separate invocation-bound
anonymous cancellation pipes plus an owned handle. Controller liveness and
terminal-finalization channels stay live. A framed-channel migration was not
selected. A thread event or controller EOF alone cannot implement cancellation.

Prior scratch source00993999 qualified ten role-tagged controlled-failure cases
after Python/security review, with actual child waits/thread joins and no
post-reap signals. Those helpers do not prove the new public API, production
bootstrap, actual scorer SQL, SDK cancellation or native qualification. They
are not repository acceptance tests for this feature.

## Public API and state

Add inert `PilotExecutor.owned_program` and `owned_score` methods with the same
inputs as their existing synchronous counterparts. Preserve those counterparts.
Factory methods validate inputs and allocate host ownership state, not native/
profile I/O, staging, processes or daemon work. Execution performs unchanged
binding/source admission before any staging/spawn.

```python
class OwnedSqlInvocation(Generic[T]):
    def request_cancel(
        self, reason: Literal["caller_cancelled", "runner_closed"],
    ) -> CancelReceipt: ...
    async def execute(self) -> InvocationCompletion[T]: ...
    async def aclose(self) -> CleanupCompleteAck: ...
    def snapshot(self) -> InvocationSnapshot: ...
```

Register owner state before execution awaits or starts its controller.
The controller worker has an invocation-owned lifetime, not an unjoined shared
default asyncio-executor lifetime.
`execute` starts at most one dispatch; concurrent/repeated callers join the same
retained completion, never replay. Direct coroutine cancellation becomes a
latched intent; repeated caller cancellation cannot detach cleanup. Original
caller cancellation propagates only after clean ACK.

Records:

- `CancelIntent`: invocation ID, first reason, requested monotonic ns and
  absolute cleanup deadline.
- `CancelReceipt`: `accepted`, `repeated`, or `already_completed`; accepted
  repeats expose the identical intent object. After host seal, intent is None
  and no descriptors are written.
- `OutcomeAbort`: invocation ID, role, `cancelled`/`infrastructure`, stable
  detail code, not parsed exception text.
- `InvocationCompletion[T]`: exactly one of usable outcome/abort, plus valid
  cleanup ACK.
- Snapshot: execution/cleanup state, identity and optional intent/incomplete
  status. Diagnostic data never confers signal authority.

Acceptance-test field spellings, fixed before implementation:
`CancelIntent(invocation_id: UUID, reason, requested_ns, deadline_ns)`;
`CancelReceipt.status/intent`; snapshot
`state/invocation_id/role/request_sha256/profile_sha256/intent/incomplete`;
completion `outcome/abort/cleanup_ack`; abort
`invocation_id/role/kind/detail_code`. ACK includes
`invocation_id/role/request_sha256/profile_sha256/not_started/released/
cleanup_trigger_ns/cleanup_deadline_ns/completed_ns/terminal_ack_sha256`,
plus actual guardian-reap/child-wait/thread-join evidence for started work.
Public-record reconstruction cannot issue an ACK.

Pure codec helpers: `_encode_cancel_frame(intent) -> bytes` and
`_decode_cancel_frame(data, *, invocation_id: UUID, now_ns: int) ->
tuple[int, int]` preserve requested/deadline ns; malformed frames raise
`ValueError`. Invocation UUID must be non-nil.

```text
ALLOCATED -> ADMITTED -> SPAWNING -> STARTING -> RUNNING
    -> FINALIZING -> DRAINED -> GUARDIAN_REAPED -> HOST_SEALED
Cancel/failure -> ABORT_LATCHED -> CLEANING
    -> DRAINED -> GUARDIAN_REAPED -> HOST_SEALED
    -> UNRESOLVED_OWNED
```

Invocation identity is allocated before dispatch and bound to the existing job
nonce, role, request digest and profile digest. PROGRAM request remains code/
max_rows/DB digest only. Gold/Task remains in separate scorer request.

## Notification protocol

Fixed40-byte `struct.Struct(">8s16sQQ")`: magic `b"SQLCNL01"`,
invocation UUID bytes, first host `time.monotonic_ns()`, absolute cleanup deadline.
Both processes use the same host clock. Require requested <= current time,
no unsigned overflow, and deadline == requested +12,000,000,000ns.

Two independent anonymous pipes: host-controller wakeup and guardian
notification. Register endpoints at creation; explicit inheritance transfers only
the guardian read endpoint. Worker/CLI children inherit no control capabilities.
Require PIPE_BUF >=40. Writers are nonblocking and write exactly one complete
frame, once per endpoint. Before endpoint creation, retain the first intent and
deliver its same frame when the endpoint is registered. No repeated appends.
Endpoint retirement/close and notification writes share lifetime synchronization;
never write through a retired numeric descriptor that the OS could have reused.

Reader buffers at most41 bytes to detect oversize; incomplete acquisition is
capped at100ms and every applicable existing deadline. Wrong/extra/truncated
data or premature EOF is protocol failure, never clean delivery. A valid late
frame triggers immediate expired-budget handling, not a new budget.

Each replacement guardian, if existing recovery permits it, gets a fresh
registered notification pipe and the same immutable intent once. Never share
consumption with an earlier guardian, reset the clock, or replay program work.
No replacement while a live unresolved guardian still owns the operation.

One host controller reader owns its pipe. One registered guardian monitor owns
its pipe; shared cancellation/deadline state is locked and immutable. RPC,
observer and supervisor threads consult the latch, not the pipe. Register
monitor before start, begin before startup grant, bound stop checks to10ms,
and stop/join it with the other actors. Do not rely on daemon-thread exit.

Startup/result/finalization waits select on notification readiness. RPC/attach
supervision observes the latch at bounded checkpoints. Cancellation interrupts
execution; in cleanup it suppresses results and tightens caps, not repeatedly
throws across trusted finalizers. Original controller EOF remains controller loss.

## One cleanup deadline

Let H = first host intent +12s; E = earlier established cleanup deadline if any;
R = original whole-role deadline. Effective cleanup deadline is
`min(H, E when present, R +12s)`. Execution retains its original role ceiling.
Every transport, join, finalization and actual reap consumes the same remaining
budget; no additional reap grace afterward. Repeats never extend H/E.

Before immutable finalization publication, tighten existing cleanup metadata
consistently. After publication, never rewrite it; apply the tighter live cap
in addition to its recorded cap.

At deadline with missing proof: incomplete snapshot, retained admission barrier/
owner/mitigation, no ACK or usable outcome. Execute and close remain pending.
This is not bounded caller return. No supervisor handoff is assumed. Fixture
safety teardown must be separately identified and cannot rewrite that decision.

## Completion and ownership

One host lock arbitrates cancellation acceptance, result suppression, proof
validation and host seal, with no await between last check and sealing.
Late accepted cancellation may suppress a received/durably published result
without rewriting immutable history. After host seal, reject retroactive intent.

EPIPE/EBADF after guardian-monitor retirement records delivery unavailable.
Independent complete evidence and actual guardian reap within the effective cap
still permit cancelled completion. A broken pipe alone never proves release.

`CleanupCompleteAck` is immutable host evidence constructed only by the live
owner through a private capability. It binds invocation/role/request/profile,
cleanup trigger/cap, not-started/released status, terminal-ACK digest when
started, actual child waits/thread joins/guardian reaps and completion time.
Public deserialization/adoption must not create a valid ACK.

Started-work ACK requires owned guest stop/deletion/absence; closed/drained
attachments and RPC aliases; joined RPC/coordinator/executor/observer/monitor
threads; actual creator CLI waits; any replacement guardian waits; current
validated finalization proof; actual parent-held guardian Popen.wait; no
unresolved or in-flight operation. Wire ACK is preliminary, not resource ACK.

Retain actual process objects before BasePopen construction/startup publication,
using a private creator-owned subclass, never a global production patch. Preserve
partial handles and endpoints on failure. Serialize direct-child operations
against reaping. Never derive signal authority from PIDs in wire/journal/runtime
JSON/snapshots. No process-group signaling is introduced.

## Phase-one files and test seams

- `ptc/sql_isolation.py`: owner/records, descriptor protocol, bounded wait
  integration, creation ownership, monitor lifecycle, ACK and sealing.
- `ptc/test_sql_owned_invocation.py`: new public API/protocol/race fixtures.
- `ptc/test_sql_lifecycle_process.py`: relevant lifecycle regressions and
  canonical ownership/cleanup controls.
- `ptc/test_sql_isolation.py`: targeted real-file finalization deadline
  regressions alongside its existing finalization fixtures.

Keep implementation in the existing controller module with no new project-module
dependency. `_PROGRAM_PATHS`/`_SCORER_PATHS` and staged source key membership stay
unchanged; changed bytes invalidate old pins naturally, never repin real profiles.
Private guardian entry: `--owned-guardian JOB CONTROL_FD CANCEL_FD normal|emergency`.
Legacy entry remains supported with strict argument validation.

Private backend substitutions, fresh fixture interpreters only:
`_spawn_owned_guardian(...)` and `_owned_boundary_io(profile, job)`. Real APIs
still perform source/binding admission; tests pin fresh synthetic profiles to
installed source and fake observer bytes. Fake boundary uses actual owned Python
actors and fixed CLI. Do not replace public API/admission with precomputed
results, add a public backend selector, or expose an environment/profile bypass.
Keep test-only safety supervision distinct from a production owner/ACK.

For deterministic race/fault gates, fresh fixtures may additionally wrap a
canonical private helper or a retained creator object's method with one
observational, bounded barrier. Delegate to the real helper and preserve its
result/proof; never replace public execution or admission. An independent
test-only pre-Base creator ledger may observe the concrete constructor.
Explicit canonical sensitivity mutations are the sole exception to delegation:
name the bypass, hit once, retain independent safety ownership, require the
intended resource/proof assertion to fail, then restore and rerun the positive.
These are test-local instrumentation, not production hooks or selectors.

## Implementation sequence

1. Independent acceptance tests and exact intended RED assertions.
2. Records, owner state and frame codec.
3. Actual creation retention.
4. Exclusive notification readers and bounded checkpoints.
5. Cleanup cap, monitor retirement, late sealing and actual post-reap ACK.
6. Fake-only positives, canonical mutants/restored positives, existing affected
   regressions and Python/security reviews. Publish only verified scope.

## Deferred adapter

Do not modify harness/runtime/worker/binding/profile in phase one. Existing
factory receives data/catalog, not the actual frozen launch timeout.

Later adapter phase may add optional synchronous runner
`validate_program_timeout(timeout)` after inert factory construction but before
model loop, using the core's actual frozen timeout; failure still closes runner.
Old factories/runners retain behavior. SQL initially supports existing5.0s only.
That seam and a new explicit BIRD configured binding require their own tests;
report-only `cotrain_ptc_qa` is not BIRD binding.
