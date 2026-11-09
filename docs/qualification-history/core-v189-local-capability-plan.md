# V189 Core local capability spike — named numeric plan (source-only, UNRUN)

Status: SOURCE-ONLY. This plan was written BEFORE
`spec/spikes/local-capability-candidate.py`. Nothing was executed, imported,
tested or spawned by the authoring worker; every command/subprocess
operation exists only as source. The parent executes, reviews and only then
decides on actual spawn/signals. No SDK, no App, no GPU, no network, no
provider, no credentials, no installed-distribution enumeration. No
SDK/native/science/paid-readiness claims are made anywhere in this spike.

## Theses under test (technical unknown, NOT production design)

1. A fresh fixed Python child cannot perform the tiny synthetic operation
   from copied JSON alone: without the inherited live channel, or with
   replayed valid-looking frames from an earlier session, the observed
   operation counter stays 0.
2. One live parent session cannot be replayed, replaced or rearmed: wrong
   session, non-monotonic seq, second admission, rearm and deadline
   extension all refuse with 0 additional ops, and a disconnect after a
   consumed permit never triggers replacement/reissue/retry.

The live channel is a local first-party DELEGATION CONCEPT between a parent
and its own freshly exec'd children. It is NOT hostile-same-user security
(a same-uid attacker outside this contract is out of scope) and NOT actual
authorization (no sealed authority, no billing, no owner API).

## Non-goals (mandatory)

- No production owner/billing/watchdog amendments; no typed delegation or
  owner API (the parent freezes those AFTER this spike passes).
- No actual Modal App, Sandbox, GPU, SDK import or provider call; "open"
  and "create" are synthetic permits only.
- No `os.fork`, no `preexec_fn`, no pickling, no serialization of sealed
  authorization objects, no dynamic/eval'd child code.
- No socket service, no TCP, no bind/listen path of our own, no remote
  commands; only `socket.socketpair()` channels created by the parent.
- No signals derived from protocol-reported PIDs (the protocol carries no
  PID fields at all); no signalling after reap; no old PIDs/markers/roots.
- No cap increases, no retries, no auto-reissue anywhere.
- No reliance on V185/V187 spike source as a working reference (the V187
  plan was read for constraints only).

## Candidate architecture (one standalone stdlib-only file, three fixed modes)

`spec/spikes/local-capability-candidate.py` runs as:

- harness (default argv): executes cases C1..C7 sequentially, prints one
  numeric line per case plus a TOTAL gate line, exit 0 only if every
  expected counter matches; exit 1 on any gate failure; exit 2 on internal
  error.
- `--spike-child <fd>`: the FIXED worker child. Fresh exec of the same file
  via `subprocess.Popen([sys.executable, __file__, "--spike-child", fd],
  pass_fds=(channel_fd,), start_new_session=True, env={"PATH":
  "/usr/bin:/bin"}, stdio DEVNULL)`. Reads framed JSON ONLY from the one
  inherited allowlisted socketpair FD; minimal environment carries no
  capability data; argv carries no capability data. Fixed state machine:
  READY -> ack_ready -> request_open -> grant_open -> request_create ->
  grant_create -> ONE witnessed op -> ack_create. Any validation failure
  exits without any op.
- `--spike-sentinel <fd>`: the FIXED sentinel child (stand-in): waits for
  one `arm` frame on its own inherited socketpair FD, replies `armed`,
  exits 0. Never touches the filesystem. SHORTCUT label: process-separated
  stand-in, not a production independent watchdog.

Witnessed operation (independent op counter): the child's only possible
side effect is one fixed harmless marker under the case's witness root:
`os.open(op_root/"spike-op.marker", O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,
0o600)` plus exactly one appended line + fsync. Roots are fresh
`tempfile.mkdtemp` directories (private 0700, owner-owned, no existing
files). The observed op counter is `len(os.listdir(root))` taken by the
parent AFTER the actual worker reap, never a hardcoded success. O_EXCL
makes >1 op by one child structurally impossible.

Parent-side session (`CapabilitySession`): one retained socketpair end,
one 32-hex nonce (registered in a run-wide `NonceLedger`; re-registration
refuses as `nonce_replay`), strictly monotonic per-direction seq, one
absolute cap `cap_unix = admit_wall + case_budget` that no frame may
extend, single-use state machine
`fresh -> admitted -> open_granted -> armed -> create_granted -> consumed`,
counters `{admissions, grants_open, grants_create, armed_acks,
arm_failures, refusals, acks_create, retries, reissues}` with `retries`
and `reissues` structurally always 0 (no retry/reissue code path exists;
the counters exist to prove absence). The parent retains/consumes the
session BEFORE any ambiguous dispatch (`close_ambiguous()` marks the
session consumed, then closes) and never auto-retries.

## Wire protocol and strict validation (bounded JSON)

Framing: 4-byte big-endian length prefix + UTF-8 JSON payload; frame
payload <= 65536 B; reads are clamped to the shared absolute deadline.

Exact schemas (extra or missing fields refuse):

- parent->child: `ready {v,kind,session,seq,deadline_unix,op_root,marker_name}`,
  `grant_open {v,kind,session,seq,deadline_unix}`,
  `grant_create {v,kind,session,seq,deadline_unix,metadata}`,
  `refusal {v,kind,session,seq,reason}`, `arm {v,kind,session,seq}` (sentinel channel)
- child->parent: `ack_ready {v,kind,session,seq}`,
  `request_open {v,kind,session,seq}`,
  `request_create {v,kind,session,seq,deadline_unix,metadata}`,
  `ack_create {v,kind,session,seq,marker}`, `armed {v,kind,session,seq}` (sentinel channel)

Validation rules (both ends, fixed):

- duplicate JSON object keys refuse (`object_pairs_hook`);
- nonfinite numbers refuse (`parse_constant` on NaN/Infinity/-Infinity);
- bool-as-integer refuses (`type(x) is int` excludes bool);
- `v` == 1 exactly; `kind` in the direction's allowed set; exact field set;
- `session` fullmatch `[0-9a-f]{32}` and equal to the retained/established
  session once known (wrong session refuses);
- `seq` integer >= 1 and strictly greater than the last accepted seq for
  that direction (duplicates and reorders refuse; refused frames never
  advance the ledger);
- `deadline_unix` finite, > 0 and <= the session cap (parent) / <= the
  child's own fixed lease bound (child): deadlines can never extend the
  initial fixed bound from either side;
- `op_root` absolute, traversal-free, equal to the established root;
  `marker_name`/`marker` equal the one fixed constant;
- `reason` <= 128 ASCII chars; `metadata` a dict serializing to <= 8192 B
  with scalar-only values (str <= 256 printable ASCII, finite float, int
  not bool, bool, None).

Fixed exit codes: 0 OK, 2 internal, 3 no-channel (absent inherited
endpoint), 4 ambiguous (EPIPE/closed/timeout after admission), 5 refused
(grant refused; no op), 6 protocol violation (no op), 7 op failed, 97
safety-lease `os._exit`. Lease exit never passes any case.

## Named numeric cases (all counters OBSERVED, asserted against EXPECTED)

Shared per-case absolute deadline = case start + budget; every wait uses
`remaining = deadline - now - 0.25s teardown reserve` (min 0.05s), never
sequential full timeouts. `ops` = witness files counted after reap.

1. `case1_absent_endpoint_or_replay_zero_ops` (budget 1.00s)
   - 1a absent inherited endpoint: worker spawned with `pass_fds=()`, so
     the fixed FD does not exist in the child -> exit 3, ops 0.
   - 1b replay to fresh invocation: source session S_A (scripted child
     end, SHORTCUT label) admits and grants open, its `grant_open(S_A)`
     wire bytes are captured; a FRESH real worker under session S_B
     receives the copied stale grant instead of a live one -> child
     refuses (exit 6), ops 0, grants_open_B == 0. The captured
     `request_open(S_A)` bytes replayed into a fresh scripted session S_C
     refuse parent-side (`session_mismatch`): grants_open_C == 0,
     refusals_C == 1.
   - EXPECTED: ops == 0, exit_absent == 3, exit_replay == 6,
     grants_open_b == 0, grants_open_c == 0, refusals_c == 1,
     retries == 0, reissues == 0, lease_exits == 0.
2. `case2_wrong_session_zero_ops` (budget 0.50s)
   - 2a scripted session S1 admitted; injected `request_open` and
     `ack_create` frames tagged with a different valid-shaped session S2
     -> 2 refusals `session_mismatch`, no grants, ledger seq unadvanced.
   - 2b real child established under READY(S_A); a second READY(S_B)
     frame -> child-side refusal, exit 6, ops 0.
   - EXPECTED: ops == 0, refusals_a == 2, exit_b == 6, grants_open == 0,
     grants_create == 0, retries == 0, lease_exits == 0.
3. `case3_create_before_armed_or_dead_sentinel_zero_ops` (budget 1.25s)
   - 3a scripted, sentinel never armed: admit -> open granted ->
     `request_create` refuses `not_armed` (1 refusal), grants_create 0.
   - 3b dead sentinel: REAL sentinel child spawned, terminated via its
     retained Popen handle (poll-checked; never a reported PID, never
     after reap) and reaped BEFORE any arm; `arm()` over the dead channel
     -> `sentinel_dead` arm_failure + refusal; `request_create` refuses
     `not_armed` (2 refusals), grants_create 0.
   - 3c absent sentinel: `arm(None)` -> `sentinel_absent` arm_failure +
     refusal; `request_create` refuses `not_armed` (2 refusals).
   - EXPECTED: ops == 0, grants_create == 0, armed_acks == 0,
     arm_failures == 2, refusals_total == 5, retries == 0, lease_exits == 0.
4. `case4_valid_ready_open_armed_create_one_op` (budget 2.00s)
   - Full live flow: REAL worker + REAL sentinel children (fresh exec,
     start_new_session, one inherited FD each, parent-side copies of the
     child ends closed IMMEDIATELY after spawn). READY -> ack_ready ->
     request_open -> grant_open -> arm -> ARMED ACK -> request_create ->
     grant_create -> child performs the ONE exclusive marker + single
     appended line -> ack_create -> clean exits; reap both, then snapshot
     and release the root.
   - EXPECTED: ops == 1, marker mode == 0o600, marker lines == 1,
     worker exit == 0, sentinel exit == 0, grants_open == 1,
     grants_create == 1, armed_acks == 1, refusals == 0, acks_create == 1,
     retries == 0, reissues == 0, lease_exits == 0, elapsed <= 2.00s.
5. `case5_duplicate_reordered_seq_zero_additional_ops` (budget 0.50s)
   - Scripted child admitted; valid ack_ready(seq 1) + request_open(seq 2)
     granted (grants_open == 1); then 7 injections, each refused with the
     exact reason, in order: duplicate seq 2 `seq_not_monotonic`;
     reordered seq 1 `seq_not_monotonic`; request_create(seq 3) with
     8193-B metadata `metadata_oversize`; raw payload with duplicate
     `"seq"` key `duplicate_keys`; raw payload with `NaN` deadline
     `nonfinite`; `"seq": true` `seq_not_monotonic` (bool-as-int);
     ack_ready with an extra field `extra_fields`.
   - EXPECTED: ops == 0, grants_open == 1, grants_create == 0,
     refusals == 7 with the exact ordered reason list, retries == 0.
6. `case6_second_admission_rearm_extended_deadline_zero_additional_ops`
   (budget 0.75s)
   - Scripted child + REAL sentinel: admit (admissions 1) -> ack_ready ->
     request_open granted -> arm once (armed_acks 1, sentinel exit 0,
     reaped) -> request_create with `deadline_unix = cap + 60` refuses
     `deadline_extension` (grants_create 0) -> second `admit()` refuses
     `second_admission` (admissions stays 1, no frame sent) -> second
     `arm()` refuses `rearm_refused` (armed_acks stays 1) -> reusing the
     consumed nonce in the ledger refuses `nonce_replay`.
   - EXPECTED: ops == 0, admissions == 1, grants_open == 1,
     grants_create == 0, armed_acks == 1, refusals == 3,
     nonce_replay_refusals == 1, sentinel_exit == 0, retries == 0.
7. `case7_disconnect_after_consumed_permit_at_most_one_op` (budget 1.75s)
   - 7a REAL worker + REAL sentinel: flow through grant_create sent; the
     parent then `close_ambiguous()` (session consumed BEFORE the socket
     closes) WITHOUT reading the reply. The child either completed the op
     and EPIPEs on ack (exit 4) or never saw the grant (exit 4); both
     satisfy the gate. Reap, then snapshot.
   - 7b scripted silent child with a CONTROLLED sentinel channel
     (SHORTCUT label: harness-held socketpair end with a pre-scripted
     `armed` reply): grant_create sent, child never replies, the ack wait
     times out inside the remaining deadline, session consumed ambiguous,
     no second grant is ever sent.
   - EXPECTED: ops_a <= 1 (and marker lines == 1 when ops_a == 1),
     ops_b == 0, exit_a in {0, 4}, grants_create total == 2 (one per
     sub-session), second_grants == 0, retries == 0, reissues == 0,
     lease_exits == 0.

## Declared worst-case timing gates

| gate | value |
| --- | --- |
| per-case budgets (C1..C7) | 1.00 + 0.50 + 1.25 + 2.00 + 0.50 + 0.75 + 1.75 = 7.75 s |
| total baseline gate | harness TOTAL must stay < 8.00 s (sum of worst-case budgets 7.75 s) |
| per local operation | <= 2.00 s (the largest single case budget); every wait clamped to the shared absolute case deadline minus a 0.25 s teardown reserve |
| child safety lease | each FIXED toy child starts an independent daemon `threading.Timer` at startup and `os._exit(97)` at a common monotonic 8.0 s lease deadline from its own start, even if the harness dies |
| external parent timeout | declared 10.0 s (enforced by the parent's runner, never by this harness; the 7.75 s budget leaves headroom so the lease cannot fire on a normal run) |
| lease exit | 97 from any child fails the case; success never accepts a lease exit |
| reap failure | failed cleanup keeps ownership (handle retained, root NOT released), case NONPASS; the toy lease guarantees no orphan beyond 8 s |
| cap changes | none: no budget may be increased, no wait retried, no permit reissued |

## Safety and cleanup rules (V187 constraints applied)

- Every child is new and invocation-owned; the protocol carries no PID
  fields, so no signal can ever be derived from a reported PID; signals
  only ever go through the retained `Popen` handle, poll-checked first,
  and never after reap.
- Immediate FD protection: the parent closes its copy of each child-end
  socket right after spawn, before any wait.
- Cleanup attempts each resource independently (own try/except per socket
  and per Popen); one failure never skips the others and never masks the
  primary error.
- Witness snapshot (listdir/stat/read of the marker) and root release
  happen only AFTER the actual worker reap (`wait()` returned); on reap
  failure the root stays retained and the path is printed.
- Fresh roots per case/sub-flow; no existing files; no old
  PIDs/markers/resources touched anywhere.
- No `os.fork`, no `preexec_fn`, no pickling; fresh exec only.

## PROVES / SHORTCUT / MISSING register (planned; mirrored in source comments)

PROVES (only when the parent runs it and every gate passes):
- copied JSON alone (absent endpoint, replayed frames, wrong session)
  yields 0 observed ops against a fresh fixed child;
- one live session admits once, grants open once, arms once, grants create
  once; duplicates/reorders/oversize/duplicate-key/nonfinite/bool-int/
  extra-field frames refuse with 0 additional ops;
- create never grants before an independent-process ARMED ACK; dead or
  absent sentinel yields 0 ops;
- deadline extension refuses on both ends; second admission/rearm/nonce
  reuse refuse;
- disconnect after a consumed permit yields <= 1 op and 0
  replacement/reissue/retry.

SHORTCUT (probe-only, NOT production):
- same-user socketpair delegation is a first-party concept, not
  hostile-same-user security and not actual authorization;
- sentinel stand-in is a fixed toy child (or a harness-controlled channel
  where labeled), not a production independent watchdog;
- the witnessed op is one harmless exclusive marker + single append, not a
  real App/Sandbox create; no SDK anywhere;
- scripted child ends (harness-held socketpair ends) exercise parent-side
  validation directly; real children cover the end-to-end flows;
- the 8 s toy lease + declared 10 s external timeout are experimental
  orphan protection, not production supervision;
- wall-clock `deadline_unix` bounds are spike-grade, not the monotonic
  production discipline.

MISSING (gaps the parent must weigh before freezing the real API):
- everything is UNRUN: all counters, exit codes and timing gates are
  planned, not observed;
- `socket.socketpair()` family/type behavior and FD inheritance are
  platform-sensitive and unverified here;
- no coverage for a child killed between O_EXCL and the append beyond the
  <=1-op gate; no coverage for clock skew on `deadline_unix`;
- no multi-session concurrency; no real SDK/GPU/App paths; no production
  owner/billing/watchdog integration (explicitly deferred).

## Execution contract (parent-owned)

- Run: `python3 spec/spikes/local-capability-candidate.py` (harness mode);
  children are spawned only by the harness itself.
- Output: one `CASE n name ... PASS|FAIL` numeric line per case, a
  `TOTAL elapsed_s=... gate_s=8.0 PASS|FAIL` line, and `RESULT PASS|FAIL`.
- Exit codes: 0 all gates pass; 1 any gate failure; 2 internal error.
- The authoring worker executed nothing; this plan and the candidate are
  source-only output, not approval.
