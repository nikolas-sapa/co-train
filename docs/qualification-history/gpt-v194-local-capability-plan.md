# V194 numeric test plan, SOURCEONLY UNRUN

Written before the new implementation. Parent owns execution, review and the
external 10.00 s cap. No result, timing, counter or containment claim is observed.
V189 and old A remain frozen.

## Test plan first

All negative operation witnesses use the same fresh-exec, operation-capable
worker as the positive case. Each fixture has a new private root, session,
nonce, socketpair and process handles. Counts come from instrumented boundaries
and, only after actual worker reap, an append-only attempt/completion journal
and exclusive marker. An exclusive marker alone is not an attempt count.

| Named case | Budget, including teardown | Numeric acceptance criteria |
|---|---:|---|
| C1 `absent_and_copied_wire` | <=1.00 s | Three real workers: absent inherited FD exits 3; source open dispatch 1; copied source `open` bytes delivered at the fresh target's open stage reject specifically `session`, not kind/sequence. Attempts/completions 0 in all three roots. |
| C2 `wrong_session_create` | <=0.50 s | One real worker, real armed sentinel, valid create kind/seq/deadline and correct nonce, only session altered. Worker error `session`, exit 5, attempts/completions 0. The single marked session-equality guard is the parent's removable red/green control; removal must make this case NONPASS. |
| C3 `unarmed_missing_dead` | <=1.25 s | Four fresh real workers: create before arm, missing sentinel, sentinel killed/reaped before arm, sentinel killed/reaped after a genuine ARMED ACK. Parent create dispatches 0 and attempts/completions 0 in each fixture. Expected parent refusals: `not_armed`; `missing` then `terminal`; `dead` then `terminal`; `dead`. |
| C4 `one_live_operation` | <=2.00 s | Spawns 2, admissions 1, open dispatches 1, arm dispatches 1, ARMED ACKs 1, create dispatches 1, consumed notices 1, actual create ACKs 1, journal attempts 1, completions 1, one 0600 marker containing the session. Actual worker accepts exactly 8192 B serialized metadata. Worker exits 0. Sentinel is observed alive before create and after worker reap, then independently stopped/reaped with exit 0. |
| C5 `sequence_and_exact_metadata` | <=0.50 s | Two admitted real workers reject create seq 2 (duplicate) and seq 1 (reorder), expected next seq 3; both exit 5 with `sequence`, attempts/completions 0. A third real worker receives a valid create header followed by a length header for an actually constructed 8193 B serialized metadata object; it rejects `size` without reading that payload, exit 5, attempts/completions 0. Supplemental decoder gates: serialized metadata exactly 8192 B accepts; 8193 B refuses; duplicate keys, all three nonfinite literals, numeric overflow, bool version/seq/deadline, extra header/metadata fields, wrong direction and wrong stage refuse. |
| C6 `one_use_and_ready_expiry` | <=0.75 s | Actually call second admission, rearm and extension on an admitted/armed fixture: 3 recorded calls/refusals and 0 change in spawn/admission/dispatch/byte counts. Then inject otherwise-valid create with initial READY cap +0.01 s, still inside the shared lease: real worker rejects `extension`, attempts/completions 0. A second fresh armed fixture receives a valid permit before its short READY cap, deliberately waits until that cap, then exits 8 at the final pre-operation expiry guard, attempts/completions 0. |
| C7 `terminal_ambiguities` | <=1.75 s | Five fresh real-worker fixtures: partial READY send (9 actual wire bytes), partial create send (9 actual wire bytes), real sentinel reports consumed arm but loses ARMED ACK, full create delivery with worker operation and suppressed ACK, worker disconnect after consumed create permit before operation. Every ambiguity calls admission, open grant, create grant, arm and replacement-spawn paths again before reap, with 5 recorded refusals and 0 additional spawns/admissions/dispatches/bytes. After reap/snapshot, repeat those 5 calls and snapshot again: 5 further refusals, actual attempt/completion delta 0. Partial sends and lost arm ACK yield 0 ops; full delivery/lost create ACK yields exactly 1 attempt/completion; consumed disconnect yields 0. No replacement is spawned. |

Every fixture must observe actual reap for every child before root removal;
every journal/marker snapshot additionally requires its worker's observed reap.
Every case requires cleanup errors 0, retained fixtures 0, lease exits 0 and
its own elapsed-time gate. A primary error and cleanup errors are both kept.
Any unobserved reap, unknown exit, forced ordinary cleanup or retained resource
is NONPASS, never a zero-op success.

Whole baseline must be <8.00 s, not merely an average. Sum of case budgets is
7.75 s. One immutable expiry is harness-start monotonic time +8.00 s, passed to
every child, including late spawns. Each child arms that absolute lease before
any channel read. Every case/I/O wait is additionally clamped to its absolute
case deadline; 0.12 s per case is reserved for cleanup. Expired budgets raise,
never become a positive epsilon. Lease exit 97 is always NONPASS.

Parent red controls, each in a separate fresh externally capped invocation:
remove the marked session guard (C2 must fail); remove the initial READY-cap
comparison (C6 must fail); move the final expiry guard past the operation
(C6 must fail); move create/READY/arm intent latches after dispatch (C7 must
fail); remove the pre-create sentinel liveness guard (C3 after-ACK death must
fail). These are parent-owned mutations of disposable copies, not author runs.
Do not accept green until the relevant control is observed red.

## Implementation plan

One smaller standalone stdlib file, three entry modes: harness, fixed worker,
fixed sentinel. No generic command runner or caller code. Fresh exec uses the
current interpreter with isolated/no-site flags, one allowlisted socketpair FD,
`close_fds`, `start_new_session`, DEVNULL stdio and a fixed minimal environment.
Trusted argv binds session, nonce, private root and common monotonic expiry.
No protocol PID, signal-by-PID, descendant process, fork/preexec/pickle, TCP,
service, SDK, provider, credential, configuration or asset access.

Nonblocking sockets use length-prefixed JSON and absolute-deadline select,
read and write loops. Each serialized JSON record is <=8192 B. To satisfy BOTH
that cap and the exact 8192 B serialized metadata boundary, create is a header
record followed immediately by one metadata-only record in a fixed protocol
stage. Metadata is not embedded inside a larger JSON envelope. The header
binds session/nonce/strict consecutive seq/deadline; the next record inherits
that single-use channel/stage binding. An 8193 B metadata record is rejected
at framing and by the supplemental decoder. No buffer widening or writer
threads.

Exact schemas, duplicate-key rejection, nonfinite rejection (including overflow),
strict primitive types, no extra fields, exact direction/stage and consecutive
per-direction sequence apply on both endpoints. Initial READY cap is frozen
by the worker, separate from the longer common lease; every grant can only
shorten it. The last expiry check immediately precedes journaled operation.

Parent admission, open, arm and create intent are consumed before the first
dispatch byte. Incomplete write, missing ACK or channel loss is terminal.
Repeat calls increment attempt/refusal counters but cannot dispatch or spawn.
The same spawn entry point used initially is called by the replacement probe.
No reported constant retry counters stand in for observations.

Sentinel remains blocked in its armed stage, does not exit at ARMED, and answers
exactly one liveness check after the protected worker has reaped. A separate
`arm_consumed` notice precedes ARMED, including the lost-ACK fault. Teardown uses
its retained handle/channel separately. All handles/FDs are owned immediately;
cleanup attempts each independently. Failed containment retains the fixture,
Popen handles and root in a harness-owned registry and prints NONPASS.

## Explicit shortcuts and non-goals

- Same-user, trusted first-party toy children, not hostile-same-user security.
- Synthetic operation: append `attempt`, exclusive marker write/fsync, append
  `complete`. No real App, SDK, watchdog, paid/native/tensor/science work.
- Metadata has exactly `effect` and printable-ASCII `pad`. Fixed effects:
  `normal`, `lost_ack`, `disconnect`, `expiry`. These exercise the real worker,
  not a peer incapable of operations. Sentinel has one fixed lost-ACK fault.
  Partial transmission is a parent-side byte-counted fault after nine bytes.
- The 8193 B live framing test sends its declared length only: the worker must
  reject before reading an oversized body. The separately constructed complete
  8193 B serialization is checked directly by the metadata decoder.
- Expiry effect intentionally waits until the initial READY cap after permit
  consumption. No arbitrary sleeps, commands or code arrive over the protocol.
- Supplemental decoder checks are not substitutes for real-worker negatives.
- The C7 after-reap repeat batch is necessary to measure attempt deltas without
  ever reading a live worker's journal. The first batch tests terminal refusal
  before joining; neither batch is a constant retry/reissue counter.
- Python timer leases are fallback containment only, not kernel guarantees.
  Process startup, filesystem syscalls and scheduler behavior need parent
  measurement. No unrun worst-case timing estimate counts as evidence.
- Production authority, SDK lifecycle, watchdog delegation, paid/native/tensor/
  science proof, hostile callers and multi-session concurrency remain MISSING.

## Delivery status

SOURCEONLY UNRUN. No commands, imports, execution, tests, Git, network,
provider access or delegation by the author. PROVES remains planned only.

## Parent V196 correction, final run pending

V195 actual baseline passed C1-C6; C7 stopped at partial READY with worker exit3, all21 children reaped, no cleanup errors or retained roots. Full close raced the child's inherited-socket bootstrap. The first C7 fixture now half-closes its outgoing stream, retains the connected peer through the same bounded join, then closes in finally. Exact expected exit4 and every numeric/operation gate remain unchanged. Other finish calls are unchanged. Fixture creation honors the parent's private session TMPDIR rather than hardcoded global /tmp; runtime records include each fixture root for independent confinement checks. Narrow independent diagnosis supports this correction; final-source review/run and mutation controls remain pending. No SDK/GPU proof.
