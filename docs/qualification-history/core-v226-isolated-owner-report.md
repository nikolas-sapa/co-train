# V226 isolated owner A-side report (SOURCEONLY UNRUN)

## 0. Status

| Item | Value |
| --- | --- |
| Assignment | `../parent-v226-core-isolated-owner-brief.md` |
| Freeze | `../parent-v226-contract-freeze.json`, `status=FROZEN`, shared bytes 19589, sha256 `1f041021535135b3b6827fafb503f5a37c94e7c0127fb58ebbf5764a9595b5ee` |
| Author | Factory Core Qwen, A-side only |
| Commands run | 0. No execution, import, compile, test, Git, network, provider, SDK, config, asset read, install or native launch |
| Attempts | One engineering attempt, inside the 1800 s bound; no provider, GPU, build, upload or install action |
| Installed-interpreter hash reads consumed | 0 (production cost reported as G7) |
| Output state | Every artifact below is UNRUN source and is not an approval. The parent owns execution, review, integration and commits |

## 1. Deliverables

| Path | State | Lines | Content |
| --- | --- | --- | --- |
| `docs/core-v226-isolated-owner-plan.md` | NEW | 701 | Test plan first (numbered pass criteria), then the implementation plan, non-goals, gaps, and section 7 post-review corrections |
| `train/qualification_isolated_deadline.py` | NEW | 652 | Shutdown arithmetic, `ShutdownLatch`, sealed child argv/bootstrap, anchored file helpers, `controller_main` and `gate_main` |
| `train/qualification_isolated_worker.py` | NEW | 775 | Worker side: sealed argv facts, `WorkerFDNumbers`, anchored reads, `WorkerChannel`, `DelegatedHost`, one delegated program call |
| `train/qualification_isolated_owner.py` | NEW | 1961 | Preflight, admission, launch pinning, preparation writer, permits, registry, parent channel, dispatch, shutdown, joins, release |
| `train/test_qualification_isolated_owner.py` | NEW | 2337 | 151 test functions, no process spawned, no installed-interpreter read |
| `train/qualification_owned_stop.py` | surgical | 209 | Read-only pin-fact properties plus `timing_facts()`; no default, limit or behaviour change |
| `train/qualification_modal_host.py` | surgical | 653 | One common latch: `acquire_common_latch`/`release_common_latch` around the existing `_LATCH_LOCK`/`_ACTIVE_HOST` slot, with `open_app`/`stop_owned` routed through it |
| `docs/core-v226-isolated-owner-report.md` | NEW | this file | Delivery report |

No other file was created, edited, moved or deleted. Nothing was committed.

## 2. Frozen gates implemented as delivered

| Gate | Delivered value |
| --- | --- |
| `NS`, `MAX_NS` | `1_000_000_000`, `2**63 - 1` (contract) |
| Attempt bound | `ATTEMPT_LIMIT_NS = 1800 * NS`; `E = admission_start_ns + attempt_ns` |
| Latest STOP origin | `L = E - teardown_ns - FIXED_SHUTDOWN_NS` (`FIXED_SHUTDOWN_NS = 9_500_000_000`) |
| Worker lease | `worker_lease_ns(E) == E` exactly |
| Controller lease | `L + FIXED_SHUTDOWN_NS + teardown_ns == E` (the release cutoff at `L`) |
| Gate initial kernel alarm | `L + 4 s + teardown_ns + ALARM_MARGIN_NS == E - 5 s`; later alarms only ever advance downward |
| Startup gate | `STARTUP_GATE_NS = 2 s` for READY and APP_RETAINED; never extends `E` |
| Shutdown stages | `("cooperate", "worker", "trigger", "command", "reap", "gate", "controller", "release")`, one origin, no renewed cutoff |
| Reap bound | `WAITPID_SECONDS = 5.0`, clamped by the stage budget; a second attempt follows a kill, never a wait |
| Inherited descriptors | 7 per worker, validated by the frozen `WorkerFDNumbers` (each >= 3, no alias) |
| Permits | `PERMIT_BYTES = 32`, 64-hex, latched before the first dispatch byte, spent once, terminal on ambiguity, never resent |
| File modes | member `0o400`, private `0o600`, owner directories `0o700` |
| Limits | `REQUEST_LIMIT = 1 MiB`, `FILE_LIMIT = 2 GiB`, `CONTROL_LIMIT = 8192`, `JOURNAL_LIMIT = 4096`, `ASSET_LIMIT = 4096` |
| Mandatory upload | `("source", "train/qualification_file_rpc.py")` required in the sealed approval and in every pinned entry set |
| Stop observation | `EXITED` (0), `KILLED` (non-zero or signal), `NOT_EXECUTED` (no gate or no status) |
| Child roles | `worker`, `controller`, `gate`; frozen birth order worker, then controller, then gate |

## 3. Surgical edits, exact scope

`train/qualification_owned_stop.py`: added read-only properties returning the
already-validated private facts (`interpreter`, `interpreter_sha256`,
`source_root`, `sdk_root`, `sdk_pins`, `private_scratch`, `environment`, with
copies for the two mappings) and `timing_facts() -> StopTimingFacts` built from
the validated floats with the contract's `ceil_ns`. `stage` and `arm` are
untouched; the owner calls `stage` exactly once and never calls `arm`.

`train/qualification_modal_host.py`: added `acquire_common_latch(holder)` and
`release_common_latch(holder)` over the existing lock and slot, widened the
`_ACTIVE_HOST` annotation to `object | None`, and routed `open_app` and
`stop_owned` through the two helpers, so the isolated owner and
`ModalOwnedHost` share exactly one latch implementation. The latch does not
support reentry: a second holder refuses, and one holder releases once. No
lifecycle, authority or resource behaviour changed.

## 4. Test suite

151 test functions, all source-only. Sections and counts: deadline arithmetic
and sealed child argv 26, anchored file operations 8, resource registry 6,
one-use permits 6, parent channel 8, retained evidence 7, preparation writer 11,
preflight 14, admission 8, launch pinning 4, delegated teardown 5, stop
observation 6, owner construction/deadlines/dispatch/release 17, worker module
14, common latch 2, frozen constants and export derivation 9.

What the suite exercises without spawning anything:

* Real arithmetic against the frozen offsets, including `E`, `L`, both leases,
  all four gate alarms, the eight cutoffs and the clamp of a late first STOP.
* Real anchored filesystem operations on `tmp_path`: nofollow refusals,
  traversal refusals, size and hash drift, hardlink refusal, expired deadline.
* Real `socketpair` frames through `_ParentChannel` and `WorkerChannel`,
  including session, kind and size refusals and clean EOF.
* Real admission through `claim_attempt_reservation`, `reservation.consume()`,
  `authorization._bind_once()` and the common latch, with a real private policy
  file per admission.
* Real launch pinning: every pinned key is re-read through anchored nofollow
  descriptors and confirmed against the bytes actually read.
* Real dispatch bookkeeping through `run_once` with spawn injected:
  `test_run_once_releases_everything_when_the_worker_spawn_fails` and
  `test_run_once_contains_and_joins_the_worker_when_the_control_link_dies`
  drive the real descriptor allocation, reservation and closure, the real
  `_escalate` and `_join_all`, the real `JoinedExecution` construction and the
  real terminal release, and assert the worker's inherited argv facts against
  the frozen `WorkerFDNumbers` gate.

Hygiene that the suite enforces on itself:

* No test reads or hashes the installed interpreter. The binding, the spec and
  every launch pin bind to an owned stand-in interpreter under `tmp_path`.
* No test invokes the real original stager. `stage_trusted_teardown` is replaced
  by a local stand-in returning a real `TrustedTeardown` over an owned
  executable; everything after the launcher stays the real code path.
* No test can signal a real process group. An autouse fixture records every
  `os.killpg` the owner issues and answers `ProcessLookupError`, which is what a
  vanished child answers, so containment paths run for real.

What the suite cannot prove (G4): no real three-child OS integration, no real
Modal SDK call, no real export written by C's program. The parent executes those
after review and allowed pins.

## 5. Defects found by end-to-end review, and fixed

All ten were found by reading the delivered source against the frozen contract,
never by running it. The first six were fixed before this report's final pass;
the last four were found while walking `run_once` end to end and are recorded in
plan section 7 rather than patched silently.

| # | Module | Symptom if shipped | Root cause | Fix |
| --- | --- | --- | --- | --- |
| 1 | deadline | Controller lease 9.5 s + T short of `E`, so the controller died before the release cutoff | `controller_lease_ns` re-derived `L` from a value that was already `L`, subtracting the reserve twice | `latest + FIXED_SHUTDOWN_NS + teardown_ns` |
| 2 | deadline | Gate alarm fired after the controller lease, so a missing trigger outlived its owner | Same double subtraction in `initial_gate_alarm_ns` | `latest + 4 s + teardown_ns + ALARM_MARGIN_NS` (`E - 5 s`) |
| 3 | owner | Gate spawned with the wrong initial alarm | `_spawn_children` computed the alarm locally | Uses `initial_gate_alarm_ns(latest, teardown_ns)` |
| 4 | owner | Anchored verification could block past `E` | Writer had no deadline fact | `_OwnerPreparationWriter` takes `deadline_ns`; every `verify_anchored_file` call passes it |
| 5 | owner | RPC coverage accepted a wrong-root row, and preflight refused every valid approval because the request entry is staged later | `_validate_uploads` matched on key only and called `validate_entries` on the pre-request preview | Row must be `root == "source" and key == RPC_SOURCE_KEY`; the preview is no longer entry-validated |
| 6 | owner | Request member keyed under a name no reader expects | `write_request` used a local name | Uses `REQUEST_NAME` |
| 7 | owner | Every dispatch died at descriptor allocation with `duplicate resource label snapshot_dir`; and `_close_descriptors` would have marked the writer's still-open anchor resolved while closing the inherited descriptor | The inherited snapshot-directory descriptor was registered under the label the preparation writer already owns, and closure resolves by that same name | The seven inherited descriptors are registered and resolved as `inherited_request`, `inherited_manifest`, `inherited_launch`, `inherited_snapshot_dir`, `inherited_outcome`, `inherited_export_parent`, `inherited_journal`. Child fact names are unchanged, so the frozen child argv is untouched |
| 8 | owner | Export landed in `private_scratch/export/<name>` instead of the approved `output_dir`, contradicting G6 | `_allocate_descriptors` opened a scratch subdirectory as the inherited export parent | New `_export_root(authorization)` derives and validates `output_dir.parent` (absolute, non-traversing, never `/`); the writer creates it; `export_root / export_name == output_dir` is asserted by test |
| 9 | owner | `run_once` failed on a fresh scratch: nothing created the private scratch or the export parent, and the writer required `scratch.is_dir()` | Admission creates claim records but no directories | The preparation writer creates both directories before it opens anything, owner-only when it creates them, and an existing directory keeps its own mode |
| 10 | owner | An escalated run left `worker_channel` unresolved although its socket was already closed, keeping the custody report dirty | `_join_all` resolved the worker channel only when a channel object was passed, and escalation passes `None` | `_join_all` closes and resolves all three channel labels by registry label, on both paths |

## 6. Known gaps (reported, not invented)

* **G1 `train/qualification_file_rpc.py` is absent from this worktree.** The
  freeze makes that row mandatory manifest coverage. The file exists in
  `integration/train` and in worktrees A may not read. Preflight requires the row
  in the sealed approval (metadata only) and the snapshot copy can only succeed
  once the parent places the file in the deployed owner repo. A did not create,
  copy or read it.
* **G2 C's transitive import set is unreadable from A.** `WORKER_SOURCE_KEYS`
  pins the contract-named program module, A's worker-side modules and the frozen
  shared vocabulary (11 sorted keys). `ModalExecTransport` does not exist here.
  The parent must confirm pin coverage against C's actual imports; a missing key
  fails closed in the worker.
* **G3 No wheels root fact exists.** `input_key` approves a `wheels` root but
  neither `QualificationRequest` nor `IsolatedOwnerSpec` carries a wheels
  directory. A binds `wheels` source paths under `private_scratch` and refuses
  anything outside it. Parent confirmation requested.
* **G4 No real three-child OS integration in these tests.** Per the brief the
  parent executes that only after review and allowed pins.
* **G5 No SDK version field exists in `LaunchDescriptor`.** The worker validates
  the sealed `sdk_root` origin, the per-file `sdk_pins`, the raw class role
  labels and `modal.__version__ == "1.6.3"` (a first-party fact) instead.
* **G6 `export_name` and its parent are derived, not supplied.** The contract
  fixes a validated basename plus an inherited parent descriptor and names no
  export path. A derives `export_name = request.output_dir.name` and
  `export_root = request.output_dir.parent`, so the pair addresses exactly the
  approved `output_dir`. Parent confirmation requested.
* **G7 One interpreter hash read per production dispatch.** `pin_worker_launch`
  re-reads `spec.interpreter` and hashes it to confirm the sealed binding fact,
  because this module never trusts a precomputed digest. A real dispatch of the
  real interpreter therefore consumes one interpreter hash read, and the frozen
  receipt leaves `interpreter_hash_reads_remaining = 0`. The parent must
  authorize that read, or supply an owner-pinned interpreter, before any parent
  execution. The delivered suite consumes 0 installed-interpreter reads because
  it binds an owned stand-in.
* **G8 `_reserve_descriptor` renumbers a socket destructively.** To satisfy the
  frozen `>= 3` descriptor gate it dups and then closes the original, which is
  correct for a plain file descriptor but leaves a `socket` object pointing at a
  closed descriptor while the duplicate is never closed by the parent. This only
  triggers if a `socketpair` lands in a stdio slot, i.e. if the parent runs with
  0, 1 or 2 closed. A did not change it: the fix belongs in the frozen
  FD-numbering path and needs the parent's decision (dup without closing the
  original, and register the duplicate for closure).

## 7. Locked interpretation choices

1. Admission order: validate, latch, claim, consume, identity-bind,
   `admission_start_ns`, `end_ns`. Validation precedes every effect.
2. The worker performs the SDK operations. The parent sends OPEN and CREATE
   permits and retains the reported identities; it never calls the SDK itself.
3. Pre-STOP dispatch reads are bounded by `L`; READY and APP_RETAINED use the
   separate 2 s startup gate, which never extends `E`.
4. One STOP transition over eight cutoffs; `request_stop` is idempotent and
   never renews a cutoff; an origin later than `L` is clamped to `L`.
5. `binding.stage()` runs exactly once, after the worker reports the App ID;
   `binding.arm()` is never called, because the gate child owns its own kernel
   alarm and execs the staged executable with the exact owned App ID on stdin.
6. The common latch does not support reentry.
7. `_spawn_child` installs no alarm in the parent; children are session leaders
   (`start_new_session=True`), `restore_signals=False`, `close_fds=True`, empty
   environment, with only the sealed descriptors passed.
8. `_validate_uploads` does not entry-validate the pre-request preview; the
   request entry is staged later by `write_request`.
9. The gate's initial alarm is `E - 5 s`, not `E`, so it fires before the release
   cutoff when the trigger never arrives.
10. The preparation writer, not admission, creates the owner's directories:
    admission stays validation-first, and preparation is the stage that owns
    directory effects.
11. `JoinedExecution` is only constructed after observed reaps. A run whose
    worker was never born surfaces its primary exception instead of a fabricated
    join.

## 8. What the parent must do next

1. Execute the suite (`train/test_qualification_isolated_owner.py`) and review
   the four defects in section 5 plus plan section 7.
2. Place `train/qualification_file_rpc.py` in the deployed owner repo (G1) and
   confirm `WORKER_SOURCE_KEYS` against C's real imports (G2).
3. Decide the interpreter hash read (G7) before any parent execution, and the
   `_reserve_descriptor` socket question (G8).
4. Confirm G3 (wheels root) and G6 (export derivation) against the sealed
   request shape.
5. Run the real three-child OS integration and the real SDK path (G4) under
   allowed pins; A's tests stop at the injected-spawn boundary by design.

## 9. Verification statement

A ran nothing. Every statement above comes from reading the frozen contract, the
frozen freeze receipt, the named first-party modules and the accepted reference
directories, and from re-reading the delivered source end to end. The defects in
section 5 were found that way and fixed in source; none was observed at runtime,
and none is confirmed fixed at runtime. All output is SOURCEONLY UNRUN and is not
an approval.
