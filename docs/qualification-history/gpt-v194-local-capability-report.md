# V194 capability repair, SOURCEONLY UNRUN

Outcome: three new source-only artifacts. No execution, approval or PASS claim.
The numeric test plan preceded implementation. The standalone probe is about
1.2k lines, rather than a patch to the frozen 2088-line V189 candidate.

## Scope and validation status

Authored only:

- `spec/spikes/gpt-v194-local-capability.py`
- `docs/gpt-v194-local-capability-plan.md`
- `docs/gpt-v194-local-capability-report.md`

Read only own AGENTS, the V194 parent brief, frozen V189 spike/plan/report,
and these new authored artifacts. V189 and old A were not edited. No Git
comparison was performed, so no checksum/byte-identity verification is claimed.

Existing checks run: NONE. New checks written: C1 through C7 inside the
standalone probe, including 15 supplemental decoder checks. New checks run:
NONE. No syntax parse, import, test, timing measurement or subprocess was
executed by the author. No commands, Git, network, provider, SDK, configuration,
credentials, assets or delegation. Only file-tool orchestration and file edits.
Python/security review and all red/green controls remain parent-owned, UNRUN.

## Frozen blockers addressed in source, not yet verified

| V189 blocker | V194 source change and planned witness |
|---|---|
| A late child receives another eight seconds | `Run.expiry` is assigned once from harness start +8.00 s. Every fresh exec receives that same absolute monotonic value. Each child arms its timer before opening/reading the inherited endpoint. |
| Blocking write after select; widened buffers/writer threads | All socket ends are nonblocking. Framed reads/writes share absolute deadlines and handle would-block without resetting them. No buffer changes or writer threads. The only toy thread is the lease timer. |
| Permission/counters latched after send | Admission/open/arm/create intent precedes dispatch. `intent_before_dispatch` records the actual flag at that boundary, checked during cleanup. C7 transmits exactly nine bytes before injected failure and invokes prohibited paths afterward. |
| Worker uses startup lease instead of READY cap | Worker freezes `initial`, checks open/create deadlines against it, and takes the minimum of READY/open/create/common bounds for the operation. C6 injects READY +0.01 s within the global lease, and separately expires an already-consumed valid permit. |
| Reap can return None, then snapshot/release | `Owned.join` returns an observed exit or raises. Every snapshot requires `worker_handle.reaped`. Root release requires every retained process reaped. Failed containment retains fixture/handles/root, reports errors and prevents PASS. |
| Sentinel exits at ARMED | Sentinel sends `arm_consumed`, then ARMED, and blocks for check/stop. Parent checks its actual retained handle before create and obtains an `alive` response after worker reap before stopping/reaping it separately. C3 also kills/reaps it after a real ARMED ACK. |
| Negative witnesses cannot perform the operation | Every negative uses the same fresh exec worker and real journal/marker operation path as C4. No scripted peers or controlled fake sentinel endpoints. Malicious-parent injection helpers are explicitly labeled. |
| Wrong kind masks session/replay guard | C1 replays an actual source `open` payload at the target's open stage with seq 2. C2 alters only the create session, preserving kind, seq, stage, nonce and deadline. Both demand worker error `session`. `SESSION_GUARD` marks the exact removable equality guard. |
| Constant zero retry counters | No retry/reissue counters. Actual repeated admission/open/create/arm/spawn calls increment call/refusal counters. Before/after spawn, intent, dispatch, record-attempt and byte snapshots must match. C7 adds a second batch after reap and compares actual operation snapshots. |
| Only a total time gate | Each case checks its own elapsed time including cleanup, against the original budget. Total must be <8.00 s. Every case deadline is clamped to the common expiry; cleanup has 0.12 s reserved. No expired timeout is replaced by an epsilon. |

## Exact named cases and expected observations, ALL UNRUN

`create_dispatches` counts authorized dispatch intent, including a partial
header, not completed operations. Explicit injections are counted separately
as `injection_calls` and remain visible in actual wire counters/events.
`admission_intents`, READY dispatches and READY ACKs are distinct counters.

| Case | Budget | Expected counters/witnesses, not results |
|---|---:|---|
| `C1_absent_and_copied_wire` | 1.00 s | 3 workers/spawns; 2 admissions; source open dispatch 1; target copied-wire injection 1; worker exits `[3,4,5]`; replay error `session`; attempts/completions 0 in each fixture. |
| `C2_wrong_session_create` | 0.50 s | Worker 1 + sentinel 1; open/ARMED 1 each; injected create 1; authorized create dispatches 0; worker error `session`, exit 5; attempts/completions 0. Sentinel checked alive after worker reap, then exit 0. |
| `C3_unarmed_missing_dead` | 1.25 s | 4 workers + 2 sentinels; open dispatches 4; authorized creates 0; earlier ARMED ACKs 1; parent refusals 6 across four fixtures; worker exits all 4; killed sentinel exits both -9; attempts/completions 0 in every fixture. |
| `C4_one_live_operation` | 2.00 s | Spawns 2; admission/open/arm/create intents 1 each; READY ACK 1; arm-consumed/ARMED 1 each; metadata payload 8192 B; consumed/create ACK 1 each; attempt/completion 1 each; marker 1, mode 0600, exact session content; worker/sentinel exits 0; sentinel alive-after-worker-reap 1. |
| `C5_sequence_and_exact_metadata` | 0.50 s | 3 workers/spawns; open dispatches 3; injected creates 3; errors `sequence`, `sequence`, `size`; exits all 5; attempts/completions 0 each. Complete serialized metadata 8192 B accepts, 8193 B refuses. Live oversized-length fault 1; 15 supplemental decoder checks. |
| `C6_one_use_and_ready_expiry` | 0.75 s | 2 workers + 2 sentinels; second-admission/rearm/extension calls 3 and refusals 3; observed spawn/admission/dispatch/record/byte delta 0. Injected extended create 1 rejects `extension`; other fixture authorized create/consumed 1 then exits 8 at operation expiry. Worker exits `[5,8]`, sentinel exits `[0,0]`; attempts/completions 0 in both. |
| `C7_terminal_ambiguities` | 1.75 s | 5 workers + 4 sentinels; partial READY 9 bytes; partial create 9 additional bytes; lost-arm-ACK fixture arm-consumed 1 and sentinel exit 4. Full delivered/lost-create-ACK fixture attempts/completions 1; consumed-disconnect fixture 0. Worker exits all 4. Each fixture invokes 5 prohibited paths before reap and 5 after reap: 10 calls/refusals, boundary deltas 0, post-reap attempt/completion/marker deltas 0. |

Nominal inventory, derived from source rather than measured: 19 fresh roots,
19 workers, 10 sentinels, 29 actual Popen boundaries, 2 total operation attempts,
2 completions, 1 actual create ACK. No replacement spawn.

All case cleanup error lists must be empty; all child reaped flags true;
retained fixtures/roots 0; lease exits 0. Known primary failure and cleanup
failures appear separately in each runtime JSON case record. Runtime exit 0
requires every case and total gate; 1 is NONPASS; 2 denotes invalid child
invocation/internal child failure. A lease exit 97 is never accepted.

## PROVES, planned only until parent run

- Live inherited endpoint and fresh session/capability binding, with copied
  valid-stage bytes and otherwise-valid wrong-session create rejected causally.
- One-use parent permission boundaries, actual worker sequence/deadline
  rejection, and zero-op witnesses for missing/dead/unarmed sentinel states.
- One observed journaled operation and actual ACK while the independently
  retained sentinel stays alive through worker completion.
- Terminal partial transmission, lost arm ACK, full operation/lost create ACK
  and consumed-permit disconnect, with real refused second calls and observed
  spawn/dispatch/attempt deltas rather than constants.

These statements are hypotheses. No real child, ACK, refusal, counter,
containment result or timing has been observed by this author.

## SHORTCUT

- Trusted same-user toy code, not hostile-same-user authorization. Session,
  nonce, root and common lease bind via trusted argv plus inherited socket FD.
- Synthetic append-only attempt/completion journal and exclusive marker.
  Fixed effects only: `normal`, `lost_ack`, `disconnect`, `expiry`; no commands.
- Create is two bounded records: authority header, then metadata object.
  This preserves an 8192 B cap on every JSON record while allowing exactly
  8192 B serialized metadata. Metadata inherits the validated header/channel
  stage, not an independent capability or sequence.
- The live 8193 B test sends the declared length only, requiring rejection
  before body read. Direct decoding also tests the entire 8193 B serialization.
- Parent fault after nine bytes, sentinel's fixed lost-ACK hook, and worker's
  fixed suppressed-ACK/disconnect/expiry hooks are explicit test choreography.
  A rejected injected header can close before the optional body write; that
  closure is recorded, never retried, and the exact worker error is still required.
- C7 operation deltas use two snapshots after reap. Its first refusal batch
  runs before joining, without reading a live worker's journal.
- Timer leases are fallback only. The invoker owns the external 10.00 s cap.
  Blocking filesystem syscalls, interpreter startup and OS scheduling are not
  proven bounded by source inspection.

## MISSING / parent handoff

- All execution, syntax/lint checks, Python/security review, timing gates and
  mutation red/green controls are UNRUN. No numeric gate was relaxed.
- Parent must measure fresh-process/default-entry execution, including cold
  startup, against each original case budget and the <8.00 s whole baseline
  under its external 10.00 s containment cap. No estimated headroom is evidence.
- Parent must observe C2 red after removing `SESSION_GUARD`, then green on
  restored source; other named controls are in the plan. Retained ownership,
  forced cleanup, unknown exits and timer exits are NONPASS, not retries.
- Production authority, SDK lifecycle, watchdog delegation and paid/native/
  tensor/science proof remain MISSING. No production API is proposed or frozen.
- Previously proven local OS isolation is separate evidence. This artifact
  neither reruns it nor extends it to Modal, provider or native termination.

VERIFY_REAL: SOURCEONLY UNRUN. Parent executes and reviews; no approval.

## Parent V196 evidence and correction

Author's source-only claims above remain unchanged. Parent V195 actually ran the baseline: C1-C6 PASS; first C7 partial-READY fixture NONPASS (`worker_exit_3`). All21 children reaped; cleanup errors, timer exits and retained roots0; elapsed0.694343s. Failed source and receipt retained separately. A debugger traced an early full-close/bootstrap race, not a permit/operation failure. Parent preserves exact expected exit4 by half-closing only this fixture's stream, keeping its peer connected through the existing bounded reap and closing in finally. No acceptance widening, deadline change or worker guard change. Private session TMPDIR now controls fixture roots, recorded for independent verification. Corrected source has not yet run; no full-seven-case or production success claim.
