# Core V240 Production Repair — Report

STATUS: SOURCEONLY UNRUN. No execution, import, compile, test, command, Git
operation, network call, provider call, or asset read was performed. Every
statement below is derived from reading source. The parent owns execution,
review, integration and commits.

Scope: the eight paths named in `../parent-v240-core-production-repair-brief.md`,
repaired against the frozen V226 + V237 interfaces. The shared DTO module
(`qualification_isolated_contract.py`), the parent-owned pure helper
(`qualification_isolated_validation.py`), the accepted RPC module and the
engineering host were treated as READONLY and were not modified. No live C
worktree file was read, searched or changed.

Plan: `docs/core-v240-repair-plan.md` (test plan T1–T50 lands before the
implementation plan, per the delivery rule).

---

## 1. What was repaired

### 1.1 `train/qualification_isolated_deadline.py`

| # | Defect | Repair |
|---|---|---|
| D1 | `anchored_open` filtered out empty/`.`/`..` components silently, then handed the remaining path to `os.open`. A key containing `..` therefore escaped the anchored root instead of being refused. | The key is now validated as a whole: empty, absolute, NUL-bearing, and any empty/`.`/`..` component is refused. No component is ever dropped or rewritten. Every intermediate is still opened `O_NOFOLLOW\|O_DIRECTORY`. |
| D2 | `controller_main` waited for `EARLY_STOP` with `deadline_ns=end_ns` (the absolute phase end `E`). | The fallback now fires at `L` (`latest_origin_ns(E, T)`), the latest legal STOP origin. Waiting to `E` let the controller sit silent through the whole window whose only purpose is to bound the STOP origin. An `EARLY_STOP` origin after `L` is now refused. |
| D3 | The trigger `sendall` and `shutdown(SHUT_WR)` were inside one `try`, so a failed `sendall` skipped the half-close and left the gate waiting on a still-open write side. | Exactly one trigger attempt, with the half-close unconditional in its own `try`. The kernel EOF now reaches the gate even when the single `sendall` raised. |

### 1.2 `train/qualification_isolated_worker.py`

| # | Defect | Repair |
|---|---|---|
| W1 | `import_sdk` verified the sealed per-file SDK pins *after* `importlib.import_module(SDK_MODULE)`. Arbitrary SDK code executed against an unpinned tree before any digest comparison ran. | `verify_sdk_pins` now runs before the SDK root is placed on `sys.path` and before the import. |
| W2 | `SDK_CLASSES` compared `modal.App.__name__` against the raw implementation label `"_App"`. The public attribute is the synchronised wrapper whose `__name__` is `"App"`, so every genuine SDK was refused. | The raw class is resolved from its own module (`modal.app._App`) and checked there; the public attribute is then required to be the wrapper over exactly that raw class, via `_wraps_raw`. |
| W3 | After `OUTCOME` the loop returned immediately. The parent drives STOP and waits for `FINISH`, so the parent blocked on a frame that could never be sent, and a clean parent EOF was treated as silent success. | After `OUTCOME` the worker waits for `STOP` with `eof_ok=True`, then sends `FINISH` and half-closes. `WorkerChannel.receive` gained `eof_ok`, which reports a clean parent half-close as `None` instead of raising `ControlEOF`. |

### 1.3 `train/qualification_isolated_owner.py`

Import-time and API-shape defects (these made the module unusable, not merely
wrong):

| # | Defect | Repair |
|---|---|---|
| O1 | `IsolatedOwner.__init__` bound `spawn=_spawn_child` as a default argument, but `_spawn_child` is defined below the class. `NameError` at import. | The default is `None`; the real function is resolved in the body. |
| O2 | `_validate_uploads` referenced `TOTAL_LIMIT`, which was not in the import list. `NameError` on the first admission. | `TOTAL_LIMIT` added to the contract import. |
| O3 | No `preflight_isolated`; `admit_isolated_owner` took `spec=`/`authorization=` kwargs; no `PinnedWorkerLaunch`; no `descriptor_for`. The frozen C caller could not reach the module at all. | Public API now matches the frozen snapshot: `preflight_isolated(request, *, authorization, owner_spec, uploads, setup_argv, export_root)`, `admit_isolated_owner(preflight)` (positional), `pin_worker_launch(owner, *, owner_spec) -> PinnedWorkerLaunch`, `PinnedWorkerLaunch.descriptor_for(*, request_size, request_sha256, manifest_size, manifest_sha256) -> LaunchDescriptor`. `__all__` updated. |
| O4 | `seal_inputs(*, launch)` was keyword-only and re-sealed internally. C calls it positionally with an already-sealed `PreparedInputs`. | Now `seal_inputs(prepared, launch)`. It adopts and cross-checks the caller's facts (entries, request size/digest, manifest size/digest, session) rather than re-sealing, so the owner can never record a launch whose four sealed facts disagree with the inputs it will hand the worker. |
| O5 | Admission never called `authorization._bind_once()`. One authorization could be reused across attempts. | The one-use authority is now spent after the claim identity is proven and before the attempt clock starts, so a failed attempt still burns the authorization. |
| O6 | `pin_worker_launch` accepted a caller-supplied `attempt_ns`, letting the launch be rebound to a different attempt than the admitted one. | The attempt is the admitted one and is not a knob. Pinning is one-use per owner. |

Correctness and safety defects:

| # | Defect | Repair |
|---|---|---|
| O7 | `IsolatedPreflight._validate_paths` used `type(spec.interpreter) is Path`. A resolved `PosixPath` is a `Path` *subclass* instance on POSIX, so every real interpreter path was rejected. | `isinstance(spec.interpreter, Path)`. |
| O8 | `_validate_binding` required `binding.source_root == spec.source_root`. The two are deliberately different levels: `spec.source_root` is the repository root carrying `train/`, `bench/`, `ptc/`; `binding.source_root` is the `train/` directory holding `qualification_owned_stop.py`. Every correctly sealed binding was refused. | Now requires `binding.source_root == spec.source_root / "train"`. |
| O9 | `REQUEST_NAME` was `"isolated-owner-request.json"`. The contract's `input_key` admits exactly one key for the `"request"` root: `"request.json"`. Every seal raised. | `REQUEST_NAME = "request.json"`. |
| O10 | `MEMBER_MODE` was `0o400`. A read-only member cannot be re-staged or repaired after a partial write, and the frozen contract treats isolated private artifacts as owner read/write. | `MEMBER_MODE = 0o600`. |
| O11 | `snapshot_member` used `integer(size, ..., 1)`, refusing zero-byte members. The contract's `ManifestEntry` size minimum is 0. | Minimum is now 0, and `_stage_member` streams a zero-byte member correctly. |
| O12 | The mutable outcome descriptor was opened `O_WRONLY`. The worker writes the outcome body through it and then reads the same descriptor back to hash what it actually wrote; a write-only descriptor made that read-back verification impossible. | Opened `O_RDWR \| O_CREAT \| O_EXCL \| O_NOFOLLOW`. |
| O13 | `_hash_descriptor` did `stream.read(size + 1)`, allocating up to the whole `FILE_LIMIT` (2 GiB) for one pinned member. A large but legitimate pin could exhaust the owner's memory before any digest comparison ran. | Streamed in bounded `CHUNK` reads and hashed incrementally. The overshoot check is a separate one-byte probe read, not an over-allocation. |
| O14 | Staging materialised the whole member in memory (`_read_local` returned bytes, `_write_member` wrote them). | New `_stage_local` streams bounded chunks from the anchored source descriptor straight into the snapshot descriptor while hashing. `_read_local` now returns the hex digest, which is all the pin path needs. |
| O15 | `WORKER_SOURCE_KEYS` held 11 entries. A partial closure lets an unpinned first-party module reach the sandbox through an unverified path. | Expanded to the complete first-party closure: 27 `train/` modules (including the C-side `qualification_isolated_program.py`, `qualification_isolated_run.py`, `qualification_engineering_run.py`, `qualification_modal_transport.py` and the parent-owned `qualification_isolated_validation.py`), 6 `bench/` modules and 5 `ptc/` modules, sorted and unique. |
| O16 | The worker entry path was `spec.source_root / "qualification_isolated_worker.py"`, dropping the `train/` prefix. The bootstrap received a path that does not exist, and the pin lookup could never match. | `spec.source_root / "train" / "qualification_isolated_worker.py"`. |
| O17 | `prepare_delegated_teardown(*, binding, expected_app_id, expires_at, timing)` took the App ID as a caller-supplied string, so a caller could stage a stop against an identity the run never observed. | V225 signature: `prepare_delegated_teardown(*, evidence, expires_at, schedule)`. The App ID is derived from the sealed `_RetainedAppEvidence`, which now carries the `stop_binding` it was observed under. `_PreparedDelegatedStop.timing` became `.schedule`. |
| O18 | `release_joined` released the common latch while registry entries were still unresolved, handing the shared latch to the next holder while this owner still held live descriptors, sockets or child processes. | The latch is released last, after the reservation, writer and registry. Anything still unresolved is retained with an `UNRESOLVED_AT_RELEASE` error label rather than discarded. |
| O19 | `_reap` ran the blocking `process.wait` on the loop's default executor (`run_in_executor(None, ...)`), which is shared and unbounded from this caller's point of view. | A dedicated three-slot executor (`_reap_executor`) matching the frozen three-child topology, so the owner's thread footprint stays fixed. |
| O20 | `_validate_uploads` unpacked `authorization.uploads` as raw 4-tuples. The sealed authorization carries upload *objects* with `root`, `key`, `size`, `sha256` and a real local `path`. Every issued authorization raised `ValueError`. | Iterates the objects, validates each field through the contract helpers, and requires the local `path` attribute. |

### 1.4 `train/test_qualification_isolated_owner.py`

Fixed before the code changes, per the delivery rule. Summary of the edits:

- Duplicate test name `test_seal_terminal_is_idempotent` renamed to
  `test_evidence_seal_terminal_is_idempotent` (suite requires unique names).
- Session constants `_SESSION = "a1" * 32` and `_FOREIGN_SESSION = "b2" * 32`
  added; `digest()` requires exactly 64 lowercase hex, so the previous
  `session="s"` literals could never validate. Propagated through
  `_channel_pair`, every `_RetainedAppEvidence`, every `WorkerChannel`
  (which also moved `lease_ns=` to `end_ns=`) and every `_frame` call.
- `allowed=("X",)` tuples replaced with `frozenset({"X"})`.
- `channel.lease_ns` replaced with `channel.end_ns`.
- The EOF test now expects `ControlLost` rather than `ValueError`.
- Imports expanded: `ControlLost`, `ExportEntry`, `ParentReadLease`,
  `PinnedWorkerLaunch`, `RegisteredReader`, `preflight_isolated`.
- New helpers: `UploadItem` (root/key/size/sha256/path), `_upload_items()`,
  `_preflight()`, `_admit()`, `_pin_launch()`, `_evidence()`, `_schedule()`.
- Admission call sites moved from `admit_isolated_owner(spec=..., authorization=...)`
  to the preflight flow.
- `test_admission_refuses_a_foreign_spec_type` now exercises
  `IsolatedPreflight(spec=object(), authorization=...).validate()`.
- `pin_worker_launch` call sites moved to `_pin_launch(admitted, entries)`,
  which pins through the owner and binds the four facts via `descriptor_for`.
- `test_pin_worker_launch_accepts_an_explicit_bounded_attempt` replaced by
  `test_pin_worker_launch_seals_the_admitted_attempt_and_is_one_use`, since
  `attempt_ns` is no longer a caller knob.
- `seal_inputs` call sites moved to positional `(prepared, launch)`, including
  the `_sealed_owner` helper.
- `prepare_delegated_teardown` tests moved to the V225 signature, with a new
  `test_prepare_delegated_teardown_refuses_evidence_without_an_app_id`.
- `MEMBER_MODE` assertion moved to `0o600`; the staging test renamed to
  `test_writer_stages_a_member_at_mode_0600_and_returns_its_entry`.
- `REQUEST_NAME` assertion tightened to `== "request.json"` plus a
  distinctness check against the other private names.

---

## 2. What was NOT repaired, and why

These are named so the parent can decide. None was silently dropped.

| Item | Status | Reason |
|---|---|---|
| V237 validation surface on the owner (`register_parent_validation`, `_assert_parent_read_lease`, `take_validated_original`) | NOT IMPLEMENTED | `ExportEntry` and `ParentReadLease` are now imported and the test file references them, but the three owner methods were not written. This is the largest remaining gap. It needs the frozen C caller's exact call order, which I could not confirm without reading the live C worktree (forbidden by the brief). |
| `engineering_outcome` synthesises `original_outcome` from `JoinedExecution` alone | NOT REPAIRED | The real original outcome comes from `take_validated_original`, which is part of the V237 surface above. Repairing this independently would invent a second source of truth. |
| `_shutdown` protocol ordering | NOT CHANGED | On re-reading, the existing order (EARLY_STOP to both children, STOP to worker, FINISH from worker, STOP witness from controller, FINISH to controller) matches the frozen protocol. My earlier note that STOP preceded FINISH incorrectly was wrong; no edit was made. |
| Controller clean-exit verification | NOT ADDED | The controller journals the FINISH witness and exits 0. Whether a missing witness should produce a non-zero exit is a protocol decision the brief does not settle; changing it unilaterally could break the parent's join expectations. |
| Gate alarm initial value | NOT CHANGED | The existing `cutoffs.origin_ns + STOP_LEAD_NS + GATE_SLACK_NS` evaluates to `O + 4 + 2T + 0.5`, which matches the intended `L + 4 + T + 0.5` given `STOP_LEAD_NS = 2T`. No defect confirmed. |
| `AdmittedOwnerRun` public visibility | PARTIAL | It already raises `TypeError` from `__reduce_ex__`, so it is non-serializable. It remains in `__all__` because the test file imports it directly; making it private would require renaming every test reference, which is a larger churn than the brief warrants. |
| `_validate_pins` interpreter/adapter digest comparison | NOT ADDED | The frozen receipt authorizes zero interpreter hash reads (G7). The interpreter digest must therefore arrive as a sealed fact and be cross-checked against `binding.interpreter_sha256` without any read. `pin_worker_launch` still calls `_pin_file(spec.interpreter, ...)`, which *does* read the interpreter. Resolving this needs the parent to confirm which sealed fact carries the authorized interpreter digest. |

---

## 3. Verification performed

None. No test was run, no module was imported, no file was compiled, no command
was executed. This is a source-only delivery.

What was done instead:

- Every defect above was confirmed by reading the actual source at the cited
  location before editing, not inferred from the earlier defect list.
- Two items from the earlier defect list were **withdrawn** after re-reading
  (`_shutdown` ordering, gate alarm value); they are recorded in section 2
  rather than "fixed".
- The frozen V225 signature for `prepare_delegated_teardown` was confirmed
  against `../parent-v225-isolated-owner-contract.md` line 128 rather than
  taken from memory.
- The `WORKER_SOURCE_KEYS` closure was built from the actual files present in
  this worktree (`train/`, `bench/`, `ptc/` listings) plus the first-party
  import edges found by searching those modules. The four C-side modules named
  in the closure are **absent from this A worktree**; the parent must place
  them, exactly as for `RPC_SOURCE_KEY`.

## 4. Known follow-ups for the parent

1. The V237 validation surface is the blocking gap. Without it the owner cannot
   produce a validated original outcome.
2. `_pin_file(spec.interpreter, ...)` performs one interpreter hash read, which
   conflicts with the G7 zero-read receipt. Decide the sealed-fact source.
3. The four C-side modules in `WORKER_SOURCE_KEYS` must exist at those exact
   keys or every pin will refuse.
4. `_stage_local` and `_hash_descriptor` changed return types. Any caller
   outside the three repaired files that consumed `_read_local`'s old
   `(bytes, stat)` tuple needs updating. A search inside the writable scope
   found no such caller.

VERIFY_REAL: not performed. This delivery is SOURCEONLY UNRUN; no check was
executed, so no claim here is backed by a passing run. The parent must execute
the suite before treating any of it as verified.
