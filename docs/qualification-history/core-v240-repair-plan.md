# V240 Core A Production Repair — Plan

SOURCEONLY. Nothing in this plan was executed, imported, compiled or tested
here. The parent executes, reviews and integrates.

Scope is the eight paths named by `../parent-v240-core-production-repair-brief.md`.
`train/qualification_isolated_contract.py`, `train/qualification_isolated_validation.py`,
`train/qualification_file_rpc.py` and `train/qualification_engineering_host.py`
are READONLY and are treated as frozen oracles: every repair below is derived
from what they actually export, never from an assumed shape.

`train/qualification_owned_stop.py` and `train/qualification_modal_host.py` need
no change. The common latch is already extracted into
`acquire_common_latch` / `release_common_latch`, and the stop binding already
exposes `timing_facts()`, `stage()` and `arm()`. Both are left byte-identical.

---

## 1. Test plan (lands first)

Target: `train/test_qualification_isolated_owner.py`. Ceiling 200 cases, every
name unique. Each case is named with the numeric or structural fact it pins.

### 1.1 Frozen-API conformance (the defects that made the suite unrunnable)

| # | Test | Pass criterion |
|---|------|----------------|
| T1 | `test_preflight_isolated_returns_a_validated_preflight` | `preflight_isolated(request, authorization=…, owner_spec=…, uploads=…, setup_argv=…, export_root=…)` returns `IsolatedPreflight`; `preflight.timing` is `StopTimingFacts`; no latch holder exists yet (`modal_host._ACTIVE_HOST is None`). |
| T2 | `test_preflight_isolated_is_metadata_only_and_takes_no_latch` | After a successful preflight, `modal_host._ACTIVE_HOST is None` and no file exists under `spec.private_scratch`. |
| T3 | `test_admit_isolated_owner_takes_the_preflight_positionally` | `admit_isolated_owner(preflight)` succeeds; the keyword form raises `TypeError`. |
| T4 | `test_admission_binds_the_one_use_authorization_exactly_once` | After admission `authorization.bound is True`; a second `admit_isolated_owner` on the same authorization raises `PermissionError`. |
| T5 | `test_pin_worker_launch_returns_a_pinned_launch` | `pin_worker_launch(owner, owner_spec=spec)` returns `PinnedWorkerLaunch`; `owner_spec` is required (omitting it raises `TypeError`). |
| T6 | `test_descriptor_for_binds_the_four_sealed_facts` | `launch.descriptor_for(request_size=…, request_sha256=…, manifest_size=…, manifest_sha256=…)` returns `LaunchDescriptor` with those four values verbatim and `session` 64-hex. |
| T7 | `test_descriptor_for_refuses_a_drifted_request_digest` | A wrong `request_sha256` raises `ValueError`; the same call with the staged digest succeeds. |
| T8 | `test_seal_inputs_accepts_prepared_and_launch_positionally` | `owner.seal_inputs(prepared, launch)` returns `PreparedInputs`; `owner.seal_inputs(prepared=…, launch=…)` raises `TypeError`. |
| T9 | `test_pinned_worker_launch_is_one_use` | A second `pin_worker_launch` on the same owner raises `ValueError`. |
| T10 | `test_admitted_run_is_private_and_neither_copies_nor_serializes` | `copy.copy`, `copy.deepcopy` and `pickle.dumps` each raise `TypeError`. |

### 1.2 Frozen names, modes and keys

| # | Test | Pass criterion |
|---|------|----------------|
| T11 | `test_request_name_is_the_contract_request_root_key` | `REQUEST_NAME == "request.json"` and `input_key("request", REQUEST_NAME)` does not raise. |
| T12 | `test_member_mode_is_owner_read_write_private` | `MEMBER_MODE == 0o600`; a staged member's `st_mode & 0o777 == 0o600`. |
| T13 | `test_writer_stages_a_zero_byte_approved_member` | A 0-byte upload stages and its `ManifestEntry.size == 0`; `seal` accepts it (contract `ManifestEntry` minimum is 0). |
| T14 | `test_worker_source_keys_cover_the_complete_firstparty_closure` | `WORKER_SOURCE_KEYS` is sorted, unique, contains `RPC_SOURCE_KEY`, `train/qualification_isolated_program.py`, `train/qualification_isolated_run.py`, `train/qualification_isolated_validation.py`, `bench/__init__.py` and `ptc/__init__.py`. |
| T15 | `test_child_argv_entry_paths_carry_the_train_prefix` | The worker argv's entry path ends `train/qualification_isolated_worker.py`; the controller/gate entry paths end `train/qualification_isolated_deadline.py`. |
| T16 | `test_private_file_names_are_stable` | `MANIFEST_NAME`, `LAUNCH_NAME`, `OUTCOME_NAME`, `JOURNAL_NAME` are the frozen basenames and none equals `REQUEST_NAME`. |

### 1.3 Anchored FD hygiene

| # | Test | Pass criterion |
|---|------|----------------|
| T17 | `test_anchored_open_refuses_an_absolute_key` | `anchored_open(fd, "/etc/passwd", O_RDONLY)` raises `ValueError`. |
| T18 | `test_anchored_open_refuses_a_dot_component` | Keys `"."`, `"a/./b"`, `"a/../b"`, `"a//b"`, `""` and `"a/"` each raise `ValueError`. |
| T19 | `test_anchored_open_refuses_a_symlinked_leaf` | Unchanged: a symlinked leaf raises `OSError` (`ELOOP`). |
| T20 | `test_hash_descriptor_streams_without_allocating_the_whole_file` | `_hash_descriptor` on a sparse 64 MiB member returns the exact digest while peak allocation stays under 8 MiB (chunked reads of `CHUNK`). |

### 1.4 Descriptor and custody

| # | Test | Pass criterion |
|---|------|----------------|
| T21 | `test_inherited_outcome_descriptor_is_owner_read_write` | The `inherited_outcome` FD answers `os.fstat` and `fcntl.fstat` with `O_ACCMODE == O_RDWR`, so C's write-then-readback hash succeeds. |
| T22 | `test_release_joined_retains_the_latch_while_a_child_join_is_unknown` | With a hanging child reap, `release_joined()` leaves `modal_host._ACTIVE_HOST` as this owner's holder and `registry.released is False`. |
| T23 | `test_release_joined_frees_the_common_latch_after_three_clean_joins` | After three observed reaps and clean closes, `_ACTIVE_HOST is None` and `registry.released is True`. |
| T24 | `test_release_joined_reports_a_stopped_reservation_after_a_clean_stop` | `stop_command == STOP_EXITED` closes the reservation with `"stopped"`; any other observation closes it with `"failed"`. |
| T25 | `test_reap_bounds_every_wait_and_never_blocks_the_loop` | A hanging `Popen.wait` is answered inside `WAITPID_SECONDS` and the owner escalates; no unbounded executor thread survives the call. |

### 1.5 Protocol order

| # | Test | Pass criterion |
|---|------|----------------|
| T26 | `test_shutdown_receives_outcome_then_finish_before_any_stop` | The parent's receive sequence on the worker link is `OUTCOME` then `FINISH`; `STOP` is sent only after `FINISH` is observed. |
| T27 | `test_three_children_are_born_in_the_frozen_order` | Spawn order is worker, controller, gate; `len(children) == 3` on success. |
| T28 | `test_controller_and_gate_are_prestarted_before_create` | Both `ARM`/`ARMED` exchanges complete before the single `CREATE` is dispatched. |
| T29 | `test_exactly_one_create_is_dispatched` | Send-kind histogram on the worker link contains `CREATE` exactly once. |
| T30 | `test_controller_fallback_waits_until_the_latest_origin_not_the_end` | With no `EARLY_STOP`, the controller's own trigger deadline is `L`, and `L < E`. |
| T31 | `test_controller_shuts_its_trigger_write_half_unconditionally` | After one `EARLY_STOP` attempt the trigger socket's write half is shut even when the send raised `OSError`. |

### 1.6 Worker

| # | Test | Pass criterion |
|---|------|----------------|
| T32 | `test_import_sdk_verifies_every_pin_before_executing_sdk_code` | With a drifted SDK pin, `import_sdk` raises before `sys.modules["modal"]` is populated. |
| T33 | `test_import_sdk_binds_the_raw_async_exports` | The returned namespace exposes objects whose `__name__` is `_App`, `_Sandbox`, `_Image` and whose `__module__` is `modal.app`, `modal.sandbox._sandbox`, `modal._image`. |
| T34 | `test_worker_sends_finish_after_a_successful_outcome` | After `OUTCOME` the worker sends `FINISH` on the same link and exits 0 without waiting for `STOP`. |
| T35 | `test_worker_absorbs_a_concurrent_stop_after_outcome` | A `STOP` arriving after `OUTCOME` is consumed, not treated as a lost link, and the exit code stays 0. |
| T36 | `test_worker_treats_a_control_eof_after_outcome_as_clean` | EOF after `OUTCOME` yields exit 0 and no `FAILED` frame. |
| T37 | `test_worker_channel_sessions_are_64_hex` | `_channel_pair()` defaults to a 64-hex session; a non-hex session raises `ValueError` at construction. |

### 1.7 V237 parent validation

| # | Test | Pass criterion |
|---|------|----------------|
| T38 | `test_register_parent_validation_is_one_use_and_needs_sealed_inputs` | Before `seal_inputs` it raises `ValueError`; after, it returns `None`; a second call raises `ValueError`. |
| T39 | `test_register_parent_validation_builds_the_fixed_validator` | It calls `train.qualification_isolated_run._make_parent_validator(owner=…, request=…, prepared=…, export_root=…)` exactly once with those keyword names. |
| T40 | `test_parent_read_lease_exposes_the_frozen_bookings` | `lease.end_ns == E`, `lease.read_deadline_ns == validation_booking(E, T).read_ns`, and `lease.worker_execution` is the sealed booking. |
| T41 | `test_registered_reader_bounds_every_read_to_65536_bytes` | `reader.read(0)` and `reader.read(65537)` each raise `ValueError`; `reader.read(65536)` returns at most 65536 bytes. |
| T42 | `test_export_entry_carries_relative_key_kind_and_size_only` | `ExportEntry` has exactly `key`, `kind`, `size`; `kind` is `"file"` or `"directory"`; an absolute key raises `ValueError`. |
| T43 | `test_export_inventory_reports_the_exact_tree` | `await lease.export_inventory()` returns every exported key once, sorted, with the right kind and size. |
| T44 | `test_take_validated_original_is_one_use_and_needs_three_joins` | Before the joins it raises `ValueError`; after, it returns `EngineeringRunOutcome`; a second call raises `ValueError`. |
| T45 | `test_take_validated_original_refuses_a_missing_service_identity` | A join set without both `app_id` and `sandbox_id` raises `ValueError`. |
| T46 | `test_minimum_remaining_is_checked_before_effects_and_before_birth` | `require_feasible` is invoked once in preflight and once before the worker spawn; an infeasible remainder refuses with no latch and no child. |
| T47 | `test_metadata_allowance_covers_teardown_plus_169_5s_plus_arm` | The allowance the owner reserves is `>= T + 169.5s + actual_arm_ns`, so the worst frozen case (T=20.5s, arm=5s) needs 195s. |
| T48 | `test_assert_parent_read_lease_is_private_and_synchronous` | `_assert_parent_read_lease` is not a coroutine function and raises `ValueError` on a foreign lease. |

### 1.8 Suite hygiene

| # | Test | Pass criterion |
|---|------|----------------|
| T49 | `test_suite_has_unique_names_and_stays_under_two_hundred_cases` | Collected count `<= 200`; `len(names) == len(set(names))`. |
| T50 | the duplicate `test_seal_terminal_is_idempotent` | The evidence-side copy is renamed `test_evidence_seal_terminal_is_idempotent`; both bodies are retained. |

---

## 2. Implementation plan

### 2.1 `train/qualification_isolated_owner.py`

Ordered by the failure each repair removes.

1. **`TOTAL_LIMIT` NameError.** `_validate_uploads` reads `TOTAL_LIMIT`, which is
   absent from the contract import list. Add it.
2. **Import-time NameError on the spawn default.**
   `IsolatedOwner.__init__` declares `spawn=_spawn_child`, but `_spawn_child` is
   defined 620 lines later, so the default is evaluated before the name exists.
   Change the default to `None` and resolve it inside the body.
3. **Public API shape.** Add `preflight_isolated(request, *, authorization,
   owner_spec, uploads, setup_argv, export_root)`. Change
   `admit_isolated_owner` to take the preflight positionally. Change
   `pin_worker_launch(owner, *, owner_spec)` to return a new private
   `PinnedWorkerLaunch` exposing
   `descriptor_for(*, request_size, request_sha256, manifest_size,
   manifest_sha256) -> LaunchDescriptor`. Change `seal_inputs` to
   `seal_inputs(self, prepared, launch)`.
4. **Missing one-use bind.** Admission never calls
   `authorization._bind_once()`. Insert it after `reservation.consume()` and
   before `admission_start_ns`, matching the frozen order
   latch → claim → consume → bind → admission_start_ns → end_ns.
5. **`REQUEST_NAME`.** `"isolated-owner-request.json"` violates the contract's
   `input_key` rule that the `"request"` root key is exactly `"request.json"`.
   Change the constant; keep the request *file* inside the private scratch under
   a distinct basename so the two namespaces never collide.
6. **`MEMBER_MODE`.** `0o400` is unreadable by C's `_SnapshotInventory` write
   path and disagrees with C's `mode == 0o600` check. Change to `0o600`.
7. **Zero-byte members.** `snapshot_member` floors size at 1 via
   `integer(size, …, 1)`. The contract's `ManifestEntry` minimum is 0. Floor at 0
   for non-request roots and keep 1 for the `"request"` root, whose contract
   minimum really is 1.
8. **Outcome FD access mode.** `inherited_outcome` is opened `O_WRONLY`, but C's
   `_write_outcome` writes and then calls `_hash_fd`, and
   `_private_regular(readonly=False)` requires `O_RDWR`. Open it `O_RDWR`.
9. **`_hash_descriptor` allocation.** `stream.read(size + 1)` materialises up to
   `FILE_LIMIT + 1` = 2 GiB. Replace with chunked `os.read` of `CHUNK`, bounded
   by the caller's deadline, accumulating into a hasher plus a bounded buffer
   only when the caller needs the bytes.
10. **Bootstrap entry paths.** `spec.source_root / "qualification_isolated_worker.py"`
    drops the `train/` prefix that every `WORKER_SOURCE_KEY` carries. Use
    `spec.source_root / "train" / "qualification_isolated_worker.py"` and the
    matching deadline path.
11. **`_validate_binding` root comparison.** `binding.source_root` is the `train`
    directory; `spec.source_root` is the repository root. Compare
    `binding.source_root == spec.source_root / "train"`.
12. **`_validate_paths` interpreter check.** `type(spec.interpreter) is Path` is
    false for the `PosixPath` instances `Path(...)` actually returns. Use
    `isinstance`.
13. **Upload inventory binding.** `_validate_uploads` iterates
    `authorization.uploads`, which are raw `(root, key, size, sha256)` 4-tuples
    with no `path`. The frozen C route passes upload *objects* with
    `root/key/size/sha256/path`. Accept the preflight's objects, validate each
    against the four approved roots and `input_key`, require an absolute
    non-traversing `path`, refuse duplicates, keep
    `rpc.size <= REQUEST_LIMIT` and `1 <= rpc.size`, and bound the aggregate by
    `TOTAL_LIMIT`.
14. **Writer inventory check.** `_OwnerPreparationWriter.snapshot_member` accepts
    any `(root, key)`. Bind it to the admitted inventory: refuse a member whose
    `(root, key, size, sha256)` is not an approved upload, and freeze the
    wheels path from the matching preflight item.
15. **`WORKER_SOURCE_KEYS`.** Extend to the complete firstparty closure C needs
    at runtime: the isolated modules including `qualification_isolated_program.py`,
    `qualification_isolated_run.py` and `qualification_isolated_validation.py`,
    plus `bench/{__init__,loader,score,shapes,suite,task}.py` and
    `ptc/{__init__,metrics,paired,runtime,sqlite_safety}.py`.
16. **`prepare_delegated_teardown` signature.** Restore the V225 form
    `(*, evidence: _RetainedAppEvidence, expires_at: float,
    schedule: ShutdownSchedule)`. The factory verifies the exact binding and
    owner, derives the original App ID from the evidence, and calls
    `binding.stage(expected_app_id=…, expires_at=…)` unchanged.
17. **Shutdown order.** V237 makes the worker send `OUTCOME` then `FINISH` on its
    own. `_shutdown` currently sends `STOP` and only then waits for `FINISH`.
    Receive `FINISH` at the worker cutoff first, then run the STOP transition.
18. **`release_joined` retention.** It releases the latch even when the registry
    still holds unresolved entries. Refuse the latch release and the terminal
    registry release while any admitted child join or close is unknown; still
    close every independent resource.
19. **`_reap` executor.** `loop.run_in_executor(None, process.wait)` parks an
    unbounded detached thread on a `wait()` with no timeout. Pass an explicit
    bounded timeout to `process.wait` and keep the executor default only for
    that bounded call.
20. **Generation-slot reservation.** Reserve a registry generation slot before
    each acquisition and register the actual FD/socket/Popen/iterator
    immediately after it exists, so a failure between create and register cannot
    orphan a live handle.
21. **`AdmittedOwnerRun` exposure.** Drop it from `__all__`, keep the type
    private in spirit, and add `__copy__`/`__deepcopy__` refusals alongside the
    existing `__reduce_ex__`.
22. **`engineering_outcome`.** It synthesises `original_outcome` from
    `JoinedExecution` alone. Replace it with the V237 one-use publication
    `take_validated_original`, which requires the actual validated parent data.
23. **V237 validation surface.** Add `register_parent_validation(*, request,
    prepared, export_root)`, `_assert_parent_read_lease(lease, *, request,
    prepared, export_root)`, `take_validated_original(*, request, prepared,
    execution, export_root)`, and the `ParentReadLease`, `RegisteredReader` and
    `ExportEntry` types. The lease's bookings come from
    `qualification_isolated_validation.validation_booking(E, T)`; the read
    deadline is the fixed `read_ns`, never a derived value.

### 2.2 `train/qualification_isolated_worker.py`

1. **Pin before import.** `import_sdk` imports `modal` and only then calls
   `verify_sdk_pins`, so SDK code executes before its pins are checked. Verify
   every SDK pin against the sealed root first, then import.
2. **Raw exports.** `SDK_CLASSES` compares `getattr(modal, "App").__name__` to
   `"_App"`, but the public synchronizer wrapper is named `App`. Resolve the raw
   implementation objects (`modal.app._App`,
   `modal.sandbox._sandbox._Sandbox`, `modal._image._Image`) and check those,
   keeping the public wrappers only where the call sites need them.
3. **`FINISH` after `OUTCOME`.** `worker_loop` returns straight after `OUTCOME`.
   On success send `FINISH`, then exit; do not wait for the parent's `STOP`.
4. **Concurrent `STOP`/EOF after `OUTCOME`.** Consume a `STOP` that races the
   `FINISH` and treat a clean EOF as success, so neither is mislabelled a lost
   link.
5. **Cancellation bridge.** `_run_on_sdk_loop`'s inner bridge absorbs
   cancellations but never observes the control link. Keep the `CANCEL_LIMIT`
   absorption and add the post-outcome `STOP`/EOF drain.

### 2.3 `train/qualification_isolated_deadline.py`

1. **`anchored_open` component validation.** `[p for p in key.split("/") if p]`
   silently drops empty components and passes `..` through to `os.open`. Reject
   the key itself when it is empty, absolute, or contains an empty, `.` or `..`
   component. This is the shared helper both the owner and the worker walk.
2. **Controller fallback deadline.** `controller_main` waits for `EARLY_STOP`
   with `deadline_ns=end_ns` (`E`). The fallback must fire at `L`, the latest
   origin, so the frozen reserve still fits.
3. **Unconditional `SHUT_WR`.** The trigger write half is shut only on the
   success path. Shut it after one `EARLY_STOP` attempt even when the send
   raised, so the gate always observes an edge.
4. **Clean controller exit.** After the `FINISH` exchange, close both sockets and
   return 0 only when no frame was lost; otherwise exit non-zero so the parent's
   join observation is honest.

### 2.4 `train/test_qualification_isolated_owner.py`

Rewrite the fixtures and every call site onto the frozen API:
`preflight_isolated` → `admit_isolated_owner(preflight)` →
`pin_worker_launch(owner, owner_spec=…)` → `descriptor_for` →
`seal_inputs(prepared, launch)`. Replace `_channel_pair`'s `session="s"` with a
64-hex session. Rename the duplicate `test_seal_terminal_is_idempotent`. Update
the constant assertions for `REQUEST_NAME`, `MEMBER_MODE` and
`WORKER_SOURCE_KEYS`, and add the cases in §1. Keep the suite at or under 200
cases with unique names.

---

## 3. Non-goals

- No change to `qualification_isolated_contract.py`,
  `qualification_isolated_validation.py`, `qualification_file_rpc.py`,
  `qualification_engineering_host.py`, `qualification_owned_stop.py` or
  `qualification_modal_host.py`.
- No change to any parent document or frozen C snapshot, and no read of the live
  C worktree.
- No execution: no import, compile, test run, command, Git operation, network
  call, provider call, SDK import, interpreter run, stager run or delegation.
- No live Modal App, Sandbox, GPU, build, upload or installation.
- No new dependency, no new public module, no reshaping of the frozen DTOs.
- No claim of remote termination or billing end: both stay `UNKNOWN`.
- No Git add, commit, push or deploy.

## 4. Delivery order

1. This plan.
2. `train/test_qualification_isolated_owner.py` onto the frozen API.
3. `train/qualification_isolated_deadline.py` (shared anchored helper first, so
   the owner and worker repairs land on a correct walk).
4. `train/qualification_isolated_worker.py`.
5. `train/qualification_isolated_owner.py`.
6. `docs/core-v240-repair-report.md`.
7. End-to-end re-read of every resulting file for definition ordering,
   referenced names and frozen API agreement.
