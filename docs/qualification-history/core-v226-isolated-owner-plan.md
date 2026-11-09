# V226 isolated owner A-side plan (SOURCEONLY UNRUN)

Author: genuine Factory Core Qwen (A). Scope: A-side interfaces of the frozen
V225/V226 isolated-owner contract only. Nothing here is production, native,
provider or paid clearance. No file in this plan was executed: no run, import,
compile, test, command, Git operation, network or provider call. The parent
executes, reviews and integrates.

Ordering rule honoured: this test plan lands BEFORE the implementation plan and
before any implementation module. Every test is named with numeric pass criteria
taken from the frozen contract, not from prose adjectives.

## 0. Frozen inputs actually read

| Input | Fact used |
| --- | --- |
| `../parent-v226-contract-freeze.json` | `status=FROZEN`, 269 checks, reviewers CLEAR, shared bytes 19589, sha256 `1f041021535135b3b6827fafb503f5a37c94e7c0127fb58ebbf5764a9595b5ee`, `interpreter_hash_reads_remaining=0` |
| `train/qualification_isolated_contract.py` | 538 lines, byte-identical to the pinned shared source; all DTO/protocol vocabulary below is quoted from it |
| `../parent-v225-isolated-owner-contract.md` | A API names, birth order, cutoff mapping, release rules |
| `../parent-v226-core-isolated-owner-brief.md` | writable paths, permitted reads, prohibitions |
| `train/qualification_owned_stop.py` | 141 lines; private facts `_interpreter/_interpreter_sha256/_source_root/_sdk_root/_sdk_pins/_private_scratch/_environment/_rpc_seconds/_teardown_seconds/_arm_seconds`; defaults `teardown_seconds=1.0`, `arm_seconds=1.0` |
| `train/qualification_modal_host.py` | 633 lines; `_LATCH_LOCK`, `_ACTIVE_HOST`, `ResourceConfig`, sealed recipe/resource checks at 238-263, latch acquire 414-421, latch release 617-622 |
| `train/qualification_engineering_host.py` | 750 lines; `EngineeringAuthorization`, `AttemptReservation`, `claim_attempt_reservation`, `sealed_claim_record_path`, `UPLOAD_ROOTS`, `MAX_GPU_WINDOW_SECONDS=1800` |
| `train/qualification_watchdog.py` | 423 lines; `TrustedTeardown`, `arm`, `ArmError`, `_REAP_SECONDS=0.5`; NOT used as parent containment |
| `train/modal_app_stop.py`, `train/modal_app_stop_launcher.py` | staged stop executable reads `{"action":"stop_owned_app","app_id":...}` from stdin, `main` dup2s devnull over fd 1/2 and requires `-I -S -B` plus `sys.executable == config["interpreter"]` |
| `train/native_qualification.py` | `FilePin`, `QualificationRequest`, `_prepare_worker_transport`, `_request_binding` |
| `train/guards.py:42` | `REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]` (actual deployed owner repo root construction) |
| seven accepted reference dirs | stop-gate (gate exec/trigger/topology), shutdown-schedule (eight cutoffs), capability (one-use permit, latch before dispatch), sdk-ready (`-I -S -B`, alarm before I/O, SDK synchronizer loop), bulk-fd (register-immediately, parent-created journal), process-boundary (own-group kill/reap), original-stop-parser |

## 1. Numeric gates taken from the frozen contract

Vocabulary constants (`train/qualification_isolated_contract.py:11-24`):

| Gate | Value |
| --- | --- |
| `NS` | 1_000_000_000 |
| `MAX_NS` | 2**63-1 |
| `CONTROL_LIMIT` | 8192 framing bytes (a framing boundary, not a padded valid message) |
| `REQUEST_LIMIT` | 1_048_576 |
| `MANIFEST_LIMIT` = `OUTCOME_LIMIT` | 8_388_608 |
| `FILE_LIMIT` | 2_147_483_648 |
| `TOTAL_LIMIT` | 8_589_934_592 |
| `ASSET_LIMIT` | 4096 (so 2..4097 manifest rows) |
| `FIXED_SHUTDOWN_NS` | 9_500_000_000 |
| `RPC_SOURCE_KEY` | `train/qualification_file_rpc.py` |
| production manifest bound | 5_026_024 bytes; heaviest synthetic row inventory 5_014_235; mandatory RPC replacement 5_013_242; exact 8_388_608 can never be a valid production manifest |

Timing and schedule gates:

| Gate | Value |
| --- | --- |
| `StopTimingFacts` | `1<=rpc_ns<=30e9`, `1<=teardown_ns<=30e9`, `1<=arm_ns<=5e9`, `rpc_ns<=teardown_ns`, `teardown_ns+9.5e9<=30e9` (so `teardown_ns<=20_500_000_000`) |
| isolated extra rule | checked BEFORE bind/claim/journal/spawn |
| actual binding defaults | `teardown_seconds=1.0`, `arm_seconds=1.0`, unchanged |
| exact ceil | `ceil_ns(p/q) = (p*NS + q - 1)//q` over `float.as_integer_ratio()`; `ceil_ns(1.0)==1_000_000_000`, `ceil_ns(0.5)==500_000_000`, `ceil_ns(20.5)==20_500_000_000` |
| latest origin | `L = E - T - 9_500_000_000` |
| origin | `O = min(first_stop_ns, L)`; `ShutdownSchedule.advance` refuses any origin later than the current one |
| eight cutoffs relative to O | `O+1e9`, `O+3e9`, `O+4e9`, `O+4e9+T`, `O+4.5e9+T`, `O+6.5e9+T`, `O+8.5e9+T`, `O+9.5e9+T` |
| stage names | `cooperate, worker, trigger, command, reap, gate, controller, release` |
| default allocation (T=1e9) | 10_500_000_000 ns total; maximum allocation (T=20_500_000_000) exactly 30_000_000_000 ns |
| gate kernel alarm | initial `L+4e9+T+5e8`; valid early record `min(current, O+4e9+T+5e8)`; trigger EOF `min(current, now+T+5e8)`; only advance (never larger), persists `execve` |
| controller/gate lease | controller `L+9.5e9+T == E`; gate initial alarm `== E-5e9` |
| worker lease | `E` exactly; never beyond |
| startup gates | READY 2e9 ns and APP_RETAINED 2e9 ns, separate parent gates, never extending E |
| attempt | `1<=attempt_ns<=1800e9` and `attempt_ns > teardown_ns + 9_500_000_000` |
| E | `admission_start_ns + attempt_ns`, committed before OPEN, never renewed |
| expired cutoff | `remaining_ns` returns 0; escalation is immediate, no epsilon, no renewed waits |
| FD numbers | 7 unique integers, each `3<=fd<=2**31-1` |
| children | exactly 3 direct children on success, unique roles `worker/controller/gate`, separate sessions, `actual_reap_observed is True` for every observation |
| interpreter hash reads | 0 remaining; no test may hash the installed interpreter or invoke the real original stager |
| native/science | 0 of 7 |
| cost | $30 gross max ($25 plan + $5 reserve); one engineering attempt <=1800 s |

## 2. Non-goals

* No production, native, provider, GPU, paid, build, upload, install or launch
  clearance. Interface implementation only.
* No new contract, schema, DTO field, message kind or alternate architecture.
  Where the frozen contract is silent or contradicts the worktree, the fact is
  reported in section 6 instead of being invented.
* No C-side file is written or read: `train/qualification_isolated_run.py` and
  `train/qualification_isolated_program.py` belong to C. A imports C only inside
  the running worker, by the constant module/function name the contract fixes.
* No parent SDK import, no parent `ModalOwnedHost` construction, no serialized
  authority, no fake App, no rearm/reissue/replacement, no `SCM_RIGHTS`.
* No old-watchdog grandchild and no synchronous `Watchdog.finish` as parent
  containment; `OwnedAppStopBinding.stage` is called exactly once and
  `OwnedAppStopBinding.arm` is never called by the isolated route.
* No real OS three-child integration inside these unit tests: the parent runs
  that separately after review and allowed pins (section 6, gap G4).
* No commit, push, deploy, global setting, trust, model or provider change.

## 3. Test plan (written before implementation, never run by A)

File: `train/test_qualification_isolated_owner.py`. Finite ordinary pytest
tests, no parametrization, no plugins, no real SDK, no network, no subprocess
spawn. Real objects are used wherever an object identity is the thing under
test: real `EngineeringAuthorization` (through `issue_engineering_authorization`
only), real `OwnedAppStopBinding`, real `AttemptReservation` claims on a real
private `tmp_path` policy file, real `socket.socketpair()` channels, real
temporary owned source bytes. `subprocess.Popen` is replaced by a recording fake
inside the owner module so partial-spawn, lost-ACK, missing-reap and
failed-close paths are exercised with real FD/socket custody and injected
faults. No test hashes the installed interpreter and no test invokes
`modal_app_stop_launcher.stage_trusted_teardown`.

### 3.1 Preflight, admission and authority (tests 1-12)

1. `test_preflight_returns_private_metadata_only` - one call, 0 file reads
   (monkeypatched `os.open` counter stays 0), 0 `subprocess.Popen` calls, 0 SDK
   imports, `reservation.consumed is False`, latch still free, and the returned
   `IsolatedPreflight` refuses `pickle.dumps`, `copy.copy` and `copy.deepcopy`
   with `TypeError` (3 refusals).
2. `test_preflight_binds_exact_original_identities` - `preflight.request is
   request`, `preflight.authorization is authorization`, `preflight.owner_spec
   is owner_spec`, `preflight.timing` equals `StopTimingFacts(1e9, 1e9, 1e9)`
   for the default binding floats, and `preflight.attempt_ns ==
   duration_seconds * NS` (1200e9 for the default fixture).
3. `test_preflight_refuses_infeasible_timing_before_any_effect` - for
   `rpc_seconds=31.0`, `teardown_seconds=21.0`, `teardown_seconds=20.5` with
   `rpc_seconds=20.6`: 4 refusals, each raising before 0 claim/spawn/latch
   effects; effect counters all 0.
4. `test_preflight_refuses_foreign_authorization_and_request` - a dict, a bool,
   a JSON string and a subclass stand-in for `authorization`: 4 `PermissionError`
   or `ValueError` refusals; `authorization.bound is False` afterwards for the
   real one (a refused preflight burns no authority).
5. `test_preflight_refuses_upload_manifest_drift` - one extra row, one missing
   row, one changed sha256, one changed size: 4 refusals, 0 claims.
6. `test_preflight_requires_rpc_source_coverage` - an approved manifest without
   `("source", "train/qualification_file_rpc.py", ...)` refuses; adding exactly
   that row accepts; 2 assertions, 0 file reads.
7. `test_preflight_refuses_manifest_limits` - 4098 rows, 1 row, duplicate
   `(root, key)`, unsorted keys, one `size=2_147_483_649`, aggregate
   `8_589_934_593`, a `request` row: 7 refusals.
8. `test_preflight_refuses_setup_argv_and_export_drift` - argv differing from
   `authorization.setup_argv` (1 refusal); `export_root` relative, containing
   `..`, or not equal to `request.output_dir.parent` (3 refusals); accepted
   case yields `preflight.export_name == request.output_dir.name` and
   `len(export_name.encode("utf-8")) <= 255`.
9. `test_preflight_refuses_owner_spec_drift` - `source_root` != actual repo
   root, `sdk_root` != `binding.sdk_root`, `interpreter` != `binding.interpreter`,
   `stop_binding` of a foreign type, `resources` of a foreign type,
   `resources.gpu != authorization.gpu_label`, memory cap != `ram_gib*1024`,
   cpu cap != `workload.cpu_cores`: 8 refusals, 0 claims.
10. `test_admit_acquires_same_latch_and_original_claim` - after one
    `admit_isolated_owner`: `modal_host._ACTIVE_HOST is owner`,
    `reservation.consumed is True`, `reservation.closed is False`,
    `authorization.bound is True`, the durable record exists with exactly 1
    `reserved` line, `owner.end_ns == owner.admission_start_ns +
    preflight.attempt_ns`, and 0 `subprocess.Popen` calls plus 0 SDK imports.
11. `test_original_and_isolated_overlap_is_at_most_one` - with an isolated owner
    admitted, `ModalOwnedHost.open_app` on a second sealed approval raises and
    `_ACTIVE_HOST` is still the isolated owner; with a `ModalOwnedHost` holding
    the latch, `admit_isolated_owner` raises and the second claim record is
    absent: 2 refusals, latch holder unchanged in both, 0 additional consumed
    reservations.
12. `test_second_admission_refuses_without_recovery` - a second
    `admit_isolated_owner` under the same approval raises `FileExistsError`,
    writes 0 extra record lines, deletes nothing, and the first owner still
    holds the latch.

### 3.2 Pinning and descriptors (tests 13-19)

13. `test_pin_requires_admitted_owner` - pinning before admission raises;
    pinning with `owner_spec` not identical to the admitted one raises;
    2 refusals, 0 launches registered.
14. `test_pin_chooses_fixed_source_set_relative_actual_repo_root` - the pinned
    key tuple equals the module constant `WORKER_SOURCE_KEYS` exactly (same
    length and order), every key is `sorted`, unique, matches
    `[A-Za-z0-9_./-]+` and is `<=256` bytes, and `pinned.source_root ==
    str(actual repo root)`; 0 caller-supplied program name is accepted (a
    caller-chosen entry module raises).
15. `test_pin_binds_actual_binding_facts` - `pinned.sdk_root ==
    str(binding.sdk_root)`, `pinned.interpreter == binding.interpreter`,
    `pinned.interpreter_sha256 == "a"*64` (the binding's own fact),
    `pinned.interpreter_size == st_size` of the owned fake interpreter, and the
    SDK pin keys equal `sorted(binding.sdk_pins)`; 0 installed-interpreter hash
    reads (the fake interpreter lives in `tmp_path`).
16. `test_pin_refuses_missing_pinned_source` - removing one pinned file from the
    owned fake repo raises, registers 0 launches, and leaves 0 open FDs
    (registry unresolved list stays empty).
17. `test_descriptor_for_seals_owner_facts_and_prepared_digests` - one call
    returns a `LaunchDescriptor` with `v==1`, `session == pinned.session`
    (64-hex), `attempt_ns == preflight.attempt_ns`, `timing ==
    preflight.timing`, `setup_argv == authorization.setup_argv`,
    `image_base_reference == candidate_recipe().base_reference`,
    `image_recipe_sha256 == recipe_sha256(recipe)`, `gpu ==
    authorization.gpu_label`, `export_name == preflight.export_name`, and
    `decode_launch(encode_launch(descriptor)) == descriptor`; a second call with
    the same digests returns an equal but non-identical descriptor (2 objects,
    1 sealed launch registered).
18. `test_descriptor_for_refuses_digest_and_size_drift` - `request_size=0`,
    `request_size=1_048_577`, a 63-hex `request_sha256`, `manifest_size=0`,
    `manifest_size=8_388_609`, a 65-hex `manifest_sha256`: 6 refusals, 0
    registered launches.
19. `test_launch_descriptor_bounds_are_exact` - `attempt_ns=1800*NS` accepted,
    `1800*NS+1` refused; `attempt_ns == teardown_ns+9_500_000_000` refused and
    `+1` accepted; `len(encode_launch(descriptor)) <= 1_048_576`: 4 assertions.

### 3.3 Preparation writer and sealing (tests 20-26)

20. `test_preparation_writer_is_one_registered_object` - `owner
    .preparation_writer()` twice returns the identical object (1 identity), and
    the writer refuses `pickle.dumps` with `TypeError`.
21. `test_snapshot_member_checks_approved_path_before_read` - for
    `("source", key)`, `("model", key)`, `("data", key)` the presented
    `source_path` must equal the sealed root join; 3 wrong-path refusals with 0
    bytes read (read counter 0), and 3 accepted copies whose returned
    `ManifestEntry.snapshot_key` is 64-hex and unique.
22. `test_snapshot_member_refuses_alias_and_drift` - a symlinked source, a
    hardlinked source (`st_nlink==2`), a size drift, a sha256 drift, a
    non-regular source, a source outside the approved root, a wheels key
    outside `private_scratch`: 7 refusals, each leaving 0 partial snapshot
    members (snapshot directory listing count unchanged).
23. `test_snapshot_copy_is_full_write_full_hash` - one accepted member: written
    size equals the approved size, the reopened snapshot member hashes to the
    approved sha256, mode is `0o600`, `st_nlink==1`, and 1 `fsync` was issued.
24. `test_write_request_derives_request_row` - `write_request(payload)` returns
    `ManifestEntry("request", "request.json", len(payload), sha256(payload),
    64-hex)`; `len(payload)=1_048_576` accepted and `1_048_577` refused;
    an empty payload refused: 3 assertions.
25. `test_seal_binds_registered_members_and_launch` - `seal(entries, launch)`
    returns `PreparedInputs` whose `entries` is the identical tuple object,
    whose `manifest_sha256 == sha256(encode_manifest(entries))`,
    `manifest_size == len(encode_manifest(entries)) <= 8_388_608`,
    `launch_sha256 == sha256(encode_launch(launch))`, and which holds the actual
    snapshot directory FD (registry shows 1 retained directory FD).
26. `test_seal_inputs_requires_identity_not_dto_equality` - an equal-but-not
    identical `PreparedInputs` copy refuses; an equal-but-not-identical
    `LaunchDescriptor` refuses; a matching pair with one flipped digest byte
    refuses; the actual registered pair accepts: 3 refusals, 1 acceptance, and
    `owner.sealed is True` only after the acceptance.

### 3.4 Deadline module: schedule, latch, alarm (tests 27-33)

27. `test_latest_origin_and_cutoffs_are_exact` - with `E=1_900_000_000_000` and
    `T=2e9`: `L == 1_888_500_000_000` and `cutoffs == (1_889_500_000_000,
    1_891_500_000_000, 1_892_500_000_000, 1_894_500_000_000,
    1_895_000_000_000, 1_897_000_000_000, 1_899_000_000_000,
    1_900_000_000_000)` (8 exact integers, matching the accepted
    shutdown-schedule oracle).
28. `test_default_and_maximum_allocation_fit_the_reserve` - with `T=1e9` the
    eight cutoffs span exactly `10_500_000_000` ns; with `T=20_500_000_000`
    exactly `30_000_000_000` ns; `T=20_500_000_001` refuses at
    `StopTimingFacts`: 3 assertions.
29. `test_latch_is_one_transition_and_never_renews` - `request_stop` at
    `500e9`, `501e9`, `502e9` returns `True` once and `False` twice,
    `stop_requests == 3`, and `cutoffs` stay the `EARLY` oracle tuple
    `(501e9, 503e9, 504e9, 506e9, 506_500_000_000, 508_500_000_000,
    510_500_000_000, 511_500_000_000)`.
30. `test_late_origin_clamps_and_advance_refuses` - `request_stop(L+1_500_000_000)`
    clamps `O` to `L` (cutoffs unchanged from the latest-origin tuple);
    `schedule().advance(L+1)` raises `ValueError`; `advance(O-1)` returns a
    schedule whose 8 cutoffs are each exactly `1e9` earlier: 3 assertions.
31. `test_expired_cutoff_escalates_immediately` - for each of the 8 stages and
    `now in (cutoff, cutoff+1)`: 16 `DeadlineExpired` refusals, 0 recorded
    waits, and `remaining_ns(cutoff, now) == 0`; at `cutoff-1` the remaining is
    exactly `1`.
32. `test_gate_alarm_only_advances` - `initial_gate_alarm_ns(L, T) ==
    L+4e9+T+5e8`; `early_gate_alarm_ns(initial, O, T) == min(initial,
    O+4e9+T+5e8)`; `eof_gate_alarm_ns(initial, now, T) == min(initial,
    now+T+5e8)`; a later candidate never increases the value (3 monotonic
    non-increasing assertions); and `initial_gate_alarm_ns(L, T) == E-5e9`.
33. `test_leases_never_exceed_e` - `worker_lease_ns(E) == E`,
    `controller_lease_ns(L, T) == E`, `initial_gate_alarm_ns(L, T) == E-5e9`,
    and `alarm_seconds(deadline, now)` is `0.0` when expired and never above
    `1800.0`: 4 assertions.

### 3.5 One-use permits, registry and channels (tests 34-40)

34. `test_permit_latch_is_set_before_dispatch_bytes` - the permit is marked
    consumed before the first wire byte (byte counter 0 at consumption), a
    second `consume` raises, and a lost response permits 0 resends: 3
    assertions.
35. `test_registry_registers_before_use_and_keeps_faults` - registering a fake
    `Popen`, an FD, a socket and a path yields 4 registered entries; a failing
    `close` and a failing `wait` leave both the primary and the cleanup
    exception objects retained (2 exception objects), the entries unresolved,
    and 0 handles replaced by strings.
36. `test_missing_reap_retains_objects_and_latch` - a fake worker whose
    `returncode` stays `None` after `SIGKILL`: `release_joined` raises,
    `_ACTIVE_HOST` is still the owner, the Popen/FD/socket objects are still
    retained (3 retained objects), and the durable consumed claim record still
    exists with its `reserved` line (1 line, 0 erasures).
37. `test_release_joined_closes_independent_resources_then_roots_and_latch` -
    after 3 observed reaps and 0 close faults: 1 reservation `close("stopped")`
    append, snapshot directory and scratch roots released, `_ACTIVE_HOST is
    None`, and the consumed claim record is NOT erased (record still present,
    `consumed is True`, `closed is True`).
38. `test_release_joined_works_for_zero_children` - a preparation failure with
    0 spawned children: `release_joined()` closes 0 children, releases the
    latch, appends 1 `failed` record line and does not raise.
39. `test_channel_rejects_wrong_session_sequence_and_kind` - a frame with a
    foreign session, `seq=2` when `1` is expected, an unlisted kind, an unknown
    body field, a truncated frame and a `8193`-byte payload: 6 refusals, and
    0 accepted messages.
40. `test_heaviest_closed_message_fits_the_framing_bound` - the heaviest
    constructible ARM message (64-hex permit, 64-hex session, 20-digit
    `end_ns/origin_ns/teardown_ns`, 25-character `ap-` ID) encodes to
    `len(payload) <= 8192` with a 4-byte prefix, and an `8192`-byte payload is
    accepted while `8193` refuses: 3 assertions.

### 3.6 Birth order, ACK loss, cancellation and shutdown (tests 41-52)

41. `test_run_once_birth_order_is_exact` - one successful fake run records the
    ordered event list
    `["worker_spawn","ready","open","app_retained","record_app","stage",
    "controller_spawn","gate_spawn","arm_controller","arm_gate","create",
    "sandbox_retained","record_sandbox","outcome","early_stop","shut_wr",
    "join_worker","join_gate","join_controller"]` (19 events, exact order), with
    exactly 3 `Popen` attempts, 3 successes, `start_new_session=True` on all 3,
    0 `preexec_fn`, and 1 `Sandbox`-equivalent CREATE dispatch.
42. `test_controller_and_gate_are_born_after_command_sealed_and_after_open` -
    the `stage` event index is greater than the `app_retained` index and less
    than the `controller_spawn` index; `controller_spawn` and `gate_spawn`
    indices are both greater than the `open` index and less than the `create`
    index: 4 inequalities.
43. `test_ready_gate_is_two_seconds_and_separate_from_e` - a worker that never
    sends READY: 1 refusal labelled `ready_expired`, the wait bound used is
    `<=2e9` ns, `owner.end_ns` is unchanged (0 renewal), the worker is killed
    and reaped (1 observation, `actual_reap_observed is True`), and `run_once`
    raises instead of returning.
44. `test_e_is_committed_before_open_and_never_renewed` - `owner.end_ns ==
    admission_start_ns + attempt_ns` before OPEN, after OPEN and after the run;
    3 equal values, 0 renewals.
45. `test_lost_open_ack_is_ambiguity_not_retry` - a worker that receives OPEN
    and never answers: exactly 1 OPEN dispatch, 0 resends, the App state stays
    UNKNOWN (`app_id is None`), 0 CREATE dispatches, the worker is joined (1
    observation) and `run_once` raises.
46. `test_lost_app_retained_ack_refuses_staging` - a worker that answers OPEN
    with a malformed APP_RETAINED (foreign session) and then nothing: 0 `stage`
    calls, 0 controller spawns, 0 gate spawns, 1 worker join, and 1 raised
    error.
47. `test_lost_arm_ack_refuses_create` - controller ARMED received, gate ARM
    lost: 0 CREATE dispatches, 1 ARM resend count of 0, both children contained
    and joined (2 observations), the gate group killed by its own verified pgid,
    and `run_once` raises.
48. `test_lost_create_ack_retains_sandbox_ambiguity` - a worker that receives
    CREATE and never answers: 1 CREATE dispatch, 0 resends, `sandbox_id is
    None`, 3 children joined, and `remote_termination`/`charged_end` are never
    claimed (no `EngineeringRunOutcome` is produced by A; `run_once` raises).
49. `test_three_repeated_cancellations_cannot_abort_joined_shutdown` - for each
    of the 3 cancellation points (App-entry, arming, running): 3
    `CancelledError` deliveries, 1 completed shutdown bookkeeping per point,
    3 observed reaps, 0 renewed cutoffs (`cutoffs` identical before and after),
    and the latch retained whenever a reap or close stayed unknown (3 scenarios,
    9 reaps total).
50. `test_early_stop_is_one_attempt_then_shut_wr` - 1 EARLY_STOP frame on each
    of the 3 links (3 frames total), 0 resends, `SHUT_WR` issued on all 3 links
    regardless of delivery, and the controller link EOF observed by the fake
    controller peer (1 EOF).
51. `test_unestablished_trigger_contains_controller_by_third_cutoff` - a
    controller that never reports its stop witness: the parent kills the
    controller group at or before the `worker` cutoff (`O+3e9`), 1 `killpg`
    call addressed to the controller's own retained unreaped pgid equal to its
    Popen pid, `pgid == sid == pid` verified before signalling, and the gate
    peer observes trigger EOF (1 EOF) and execs (1 exec).
52. `test_stop_command_observation_vocabulary` - gate exec'd and exited 0 gives
    `stop_command == "EXITED"`; parent-killed gate gives `"KILLED"`; a gate that
    never exec'd gives `"NOT_EXECUTED"`: 3 exact strings, and 0 other values.

### 3.7 Worker-side source (tests 53-58, no processes)

53. `test_worker_defers_c_import_until_runtime` - importing
    `train.qualification_isolated_worker` leaves
    `"train.qualification_isolated_program"` absent from `sys.modules` (0 C
    imports at import time), and the constant program target is exactly
    `("train.qualification_isolated_program", "run_prepared_worker")`.
54. `test_worker_inputs_validation_is_exact` - `WorkerInputs` with a
    `1_048_577`-byte payload refuses; 7 FD numbers with one duplicate refuses;
    one FD `==2` refuses; a valid set accepts: 3 refusals, 1 acceptance.
55. `test_worker_channel_is_independent_per_direction` - the send sequence and
    the receive sequence each start at `seq=1` and advance by exactly 1 (2
    independent counters), and a received `seq` equal to the send counter is
    refused (1 refusal).
56. `test_worker_sdk_role_validation_fails_closed` - a stand-in SDK whose
    `App.__module__` is `modal.app` but whose `Sandbox.__name__` is `Sandbox`,
    one whose `Sandbox.create` is not a coroutine function, one whose
    `modal.__file__` is outside `launch.sdk_root`, and one whose
    `modal.__version__ != "1.6.3"`: 4 refusals, 0 accepted SDK namespaces.
57. `test_delegated_host_end_ns_is_the_open_deadline` - `host.end_ns` equals the
    OPEN `end_ns` exactly after 3 later clock advances (0 renewals),
    `host.resource is` the retained sandbox object, and
    `require_setup_argv(launch.setup_argv)` passes while a one-item drift raises
    `PermissionError`: 3 assertions.
58. `test_worker_source_pin_verification_is_bounded` - a pinned source with a
    flipped byte refuses, a pinned source with a drifted size refuses, and a
    matching set of 5 pins verifies with 5 full hash reads and 0 reads outside
    `launch.source_root`: 2 refusals, 5 reads.

### 3.8 Surgical integrations (tests 59-62)

59. `test_binding_timing_facts_are_exact_ceils` - for
    `rpc_seconds=1.0, teardown_seconds=1.0, arm_seconds=1.0` the binding returns
    `StopTimingFacts(1_000_000_000, 1_000_000_000, 1_000_000_000)`; for
    `rpc_seconds=0.1, teardown_seconds=0.25, arm_seconds=0.5` it returns
    `(100_000_000, 250_000_000, 500_000_000)`; for
    `teardown_seconds=20.5` it returns `teardown_ns == 20_500_000_000`; and
    `rpc_seconds=2.0, teardown_seconds=1.0` refuses with `ValueError`: 4
    assertions, 0 changed defaults.
60. `test_binding_pin_facts_are_read_only_copies` - `binding.sdk_pins` equals
    the constructor mapping, mutating the returned dict changes nothing (0
    drift), `binding.environment` likewise, and `binding.source_root`,
    `binding.sdk_root`, `binding.interpreter`, `binding.interpreter_sha256`,
    `binding.private_scratch` are the validated constructor values: 5
    assertions.
61. `test_common_latch_helpers_are_exclusive_and_idempotent` -
    `acquire_common_latch(a)` then `acquire_common_latch(b)` raises;
    `release_common_latch(b)` returns `False` and leaves `a` held;
    `release_common_latch(a)` returns `True` and leaves `_ACTIVE_HOST is None`;
    a second `release_common_latch(a)` returns `False`: 4 assertions.
62. `test_existing_host_behaviour_is_unchanged` - the existing
    `train/test_qualification_modal_host.py` and
    `train/test_qualification_owned_stop.py` suites are untouched by the
    surgical edits (0 modified lines in those two files) and the refactored
    `open_app`/`stop_owned` latch calls keep 1 acquisition and 1 release per
    host lifecycle, with `_ACTIVE_HOST` cleared only for the identical holder.

## 4. Implementation plan (after the test plan)

### 4.1 `train/qualification_isolated_deadline.py` (NEW)

Absolute shutdown arithmetic plus the two independent shutdown children. No SDK
import, no import-time work, stdlib plus the frozen shared vocabulary only.

* `STAGES`, `STAGE_INDEX`, `STARTUP_GATE_NS = 2*NS`, `ALARM_MARGIN_NS = NS//2`,
  `ALARM_EXIT_CODE = 124`.
* `latest_origin_ns`, `shutdown_origin_ns`, `controller_lease_ns`,
  `worker_lease_ns`, `initial_gate_alarm_ns`, `early_gate_alarm_ns`,
  `eof_gate_alarm_ns`, `advance_gate_alarm_ns`, `alarm_seconds`,
  `install_alarm` (SIGALRM handler `os._exit(124)` plus `setitimer(ITIMER_REAL,
  remaining)`, installed before any source/FD I/O by the bootstrap).
* `DeadlineExpired(RuntimeError)` and `ShutdownLatch`: one transition,
  `O = min(first_stop_ns, L)`, repeated requests counted but never renewing,
  `stage_cutoff`, `remaining` (raises `DeadlineExpired` at `<=0` so escalation is
  immediate and never epsilon-renewed).
* `BOOTSTRAP`: the accepted sdk-ready bootstrap shape. Kernel alarm first, then
  nofollow/regular/nlink/uid/size/sha256/identity-before-after validation of the
  parent-sealed entry module, then the parent-sealed `source_root` inserted into
  `sys.path`, then `exec`. Argv carries only the parent-sealed absolute end, the
  entry path/size/sha256, the source root and the role facts: no commands, no
  credentials, no ambient discovery.
* `_journal_append(dir_fd, name, record)`: children append without `O_CREAT`,
  relative to the inherited journal directory FD.
* `controller_main(argv)`: validate argv, send `ARMED`, then wait for
  `EARLY_STOP` or link EOF/partial/malformed; on any of them write the single
  trigger byte to the gate (sole trigger writer), send `STOP` as the dispatched
  witness, then wait for `FINISH` or the lease and exit 0. A dead controller
  closes the trigger socket, which is the gate's EOF path.
* `gate_main(argv)`: validate argv, send `ARMED`, install nothing (bootstrap
  alarm already holds `L+4e9+T+5e8`), then `select` on link and trigger. A valid
  `EARLY_STOP` record advances the alarm to `min(current, O+4e9+T+5e8)`. A
  trigger record, a partial/malformed record or a clean EOF advances to
  `min(current, now+T+5e8)`, appends the `exec` journal record, closes the
  trigger copy, marks the link FD inheritable and `os.execve`s the parent-sealed
  staged command in the same PID/session, preserving the parent's original
  `Popen`. The kernel alarm survives the exec.
* `main()` dispatch on `sys.argv[1]` in `{"--controller", "--gate"}`.

### 4.2 `train/qualification_isolated_worker.py` (NEW)

Worker-side only; the parent never imports it.

* Constants: `PROGRAM_MODULE = "train.qualification_isolated_program"`,
  `PROGRAM_FUNCTION = "run_prepared_worker"`, `SDK_VERSION = "1.6.3"` (the
  first-party fact recorded in `train/modal_app_stop.py` and
  `train/modal_app_stop_launcher.py`), `SDK_CLASSES` role labels identical to
  `qualification_modal_host._SDK_CLASSES`.
* `read_payload(fd, limit)`, `load_launch(fds)`, `load_inputs(fds, launch)`:
  full bounded reads of the request/launch/manifest FDs, canonical decode,
  exact size/sha256 comparison against the sealed launch, `decode_manifest`.
* `verify_source_pins(root, pins, deadline_ns)`: anchored nofollow full-hash
  verification of the fixed reviewed source-module set;
  `verify_snapshot_members(dir_fd, entries, deadline_ns)`: metadata for every
  row plus a full hash for `source` rows only (bounded).
* `import_sdk(launch, deadline_ns)`: `sys.path` already carries the sealed
  source root; the sealed `sdk_root` is inserted, `modal` imported, origin
  checked against `sdk_root/modal/__init__.py`, version checked against
  `SDK_VERSION`, role labels and coroutine shapes checked, and every
  `launch.sdk_pins` entry full-hash verified. Fail closed on any mismatch.
* `WorkerChannel`: implements the shared `WorkerControl` protocol; independent
  `seq` per direction starting at 1; `encode_message`/`decode_message`;
  aggregate `CONTROL_LIMIT` cap; nonblocking socket with bounded `select`;
  clean-EOF detection; `shutdown_read`/`close` with observation.
* `DelegatedHost`: implements `DelegatedWorkerHost`; `resource` is the actual
  retained raw Sandbox, `app_id`/`sandbox_id` are the actual service IDs,
  `end_ns` is the immutable OPEN deadline (never a fresh window), and
  `require_setup_argv` compares the launch tuple exactly.
* `async worker_loop(*, inputs, launch, control)`: READY, OPEN, SDK import on
  the SDK synchronizer loop, App constructed and retained BEFORE the entry
  await, APP_RETAINED with the actual ID, CREATE, one `Sandbox.create`, actual
  Sandbox retained before SANDBOX_RETAINED, then the deferred C import and one
  `run_prepared_worker` call. A concurrent bounded watcher absorbs one
  EARLY_STOP/EOF and stops cooperation without aborting the outcome
  bookkeeping.
* `worker_main(fds)`: builds inputs/channel, runs the loop through the accepted
  `synchronizer.no_io_translation` + `synchronize_api` + `.aio()` bridge, writes
  no outcome bytes itself (C owns the outcome FD), sends `OUTCOME` or `FAILED`,
  closes its inherited copies with observation and returns the exit code.
* `main()` dispatch on `--worker` plus the 7 whitelisted FD numbers.

### 4.3 `train/qualification_isolated_owner.py` (NEW)

Parent-side orchestration; SDK-free.

* `WORKER_SOURCE_KEYS`: the fixed reviewed source-module set, relative to the
  actual deployed owner repo root, derived exactly as `train/guards.py:42`
  derives `REPO_ROOT` (`Path(__file__).resolve().parents[1]`).
* `_OwnedRegistry`: registers `Popen`/FD/socket/path immediately after creation
  and before any use; keeps close/reap observations; retains primary AND cleanup
  exception objects; never clears an unresolved list; never replaces a handle
  with a string; releases roots only after every admitted user is dead and its
  close observed.
* `_Permit`: fresh 64-hex one-use capability; latch set before the first
  dispatch byte; terminal on ambiguity; no resend.
* `_ParentChannel`: parent end of a control socketpair, bounded framed
  send/receive over the frozen vocabulary, `shutdown_write`, `close`.
* `_RetainedAppEvidence`: sealed only by the expected-state dispatcher from the
  actual worker `Popen`/channel/session, the consumed OPEN permit, the actual
  APP_RETAINED message, actual liveness and the original owner; non-serializable.
* `_PreparedDelegatedStop` and `prepare_delegated_teardown(*, evidence,
  expires_at, schedule)`: verifies the exact binding and owner, derives the
  original App ID from the actual message, calls
  `binding.stage(expected_app_id=..., expires_at=...)` unchanged exactly once,
  and retains `TrustedTeardown`/environment/pins/schedule. Only the owner
  consumes it. `binding.arm` is never called.
* `IsolatedPreflight`: metadata only; retains original object identities;
  validates the sealed authorization, the exact original request type, the
  upload manifest against `authorization.uploads` plus the four approved roots,
  the mandatory RPC source row, every manifest limit, `setup_argv` equality,
  `export_root == request.output_dir.parent`, the owner spec against the actual
  repo root and the actual binding facts, the sealed recipe and the sealed
  resource caps, and the isolated timing rule (all before any effect).
* `admit_isolated_owner`: common latch (`qualification_modal_host
  .acquire_common_latch`) -> `claim_attempt_reservation` -> `reservation.consume()`
  -> `authorization._bind_once()` -> `admission_start_ns` -> `end_ns`.
* `pin_worker_launch`: after admission only; fixed key set; per-key anchored
  nofollow size/sha256 reads of the owner's own first-party sources; the
  interpreter re-read through the same anchored nofollow path, its size and
  sha256 confirmed against the bytes actually read and required to equal the
  binding fact (corrected in section 7: this is one interpreter hash read, not
  `os.stat` metadata); SDK root/pins from the binding;
  a fresh 64-hex session; registers the launch on the owner.
* `IsolatedOwner`: `preparation_writer()`, `seal_inputs(prepared, launch)`,
  `async run_once()`, `release_joined()`, plus the registry, the shutdown latch,
  the journal and the retained roots.
* `_PreparationWriter`: owns the snapshot directory, the request/manifest/launch
  files and their anchors; `snapshot_member` derives the approved path per root
  (`source` -> owner source root, `model` -> `request.model_dir`, `data` ->
  `request.db_root`, `wheels` -> `owner_spec.private_scratch`), verifies it
  before reading, copies with full writes and full hashes, and generates a
  unique flat 64-hex `snapshot_key`; `write_request` receives the original
  serializer payload; `seal` binds the registered members, writes the canonical
  manifest and launch and returns `PreparedInputs` with the same custody.
* `run_once`: the frozen birth order, one CREATE, the eight-cutoff shutdown, and
  a `JoinedExecution` only after real joins. Every independent
  close/kill/wait is attempted while preserving the primary and cleanup
  exception objects. Partial failures raise after the admitted subset is joined
  and its owned closes are attempted.

### 4.4 Surgical edits

* `train/qualification_owned_stop.py`: add read-only pin-fact properties
  (`interpreter`, `interpreter_sha256`, `source_root`, `sdk_root`, `sdk_pins`,
  `private_scratch`, `environment`) returning copies for the two mappings, and
  `timing_facts() -> StopTimingFacts` built from the already-validated floats
  with the contract's exact `ceil_ns`. No default, limit or existing behaviour
  changes; no new import-time work beyond the pure shared vocabulary.
* `train/qualification_modal_host.py`: add `acquire_common_latch(holder)` and
  `release_common_latch(holder)` around the existing `_LATCH_LOCK`/`_ACTIVE_HOST`
  slot, widen the `_ACTIVE_HOST` annotation to `object | None`, and route
  `open_app`/`stop_owned` through those two helpers so the isolated owner and
  `ModalOwnedHost` share exactly one latch implementation. No lifecycle,
  authority or resource behaviour changes.

## 5. Verification performed by A

None executable. A ran 0 commands, 0 imports, 0 compiles and 0 tests. Every
statement above comes from reading the frozen contract, the named first-party
modules and the seven accepted reference directories. All delivered source is
UNRUN and is not an approval.

## 6. Missing facts and known gaps (reported, not invented)

* **G1 `train/qualification_file_rpc.py` is absent from this worktree.** The
  frozen contract makes `("source", "train/qualification_file_rpc.py")`
  mandatory manifest coverage (`qualification_isolated_contract.py:20,175`). The
  file exists in `integration/train` and in two other worktrees, which are not
  permitted reads for A. Consequence: `preflight_isolated` requires the row in
  the sealed approval (metadata only, no read), and C's snapshot copy of that
  row can only succeed once the parent places the file in the deployed owner
  repo. A did not create, copy or read it.
* **G2 C's transitive import set is unreadable from A.** `WORKER_SOURCE_KEYS`
  must cover everything C's `train.qualification_isolated_program` imports at
  worker runtime, and `ModalExecTransport` does not exist in this worktree. A
  pins the contract-named program module plus A's own worker-side modules and
  the frozen shared vocabulary. The parent must confirm pin coverage against C's
  actual imports at integration; a missing key fails closed in the worker.
* **G3 No wheels root fact exists.** `input_key` approves a `wheels` root and
  `UPLOAD_ROOTS` includes it, but neither `QualificationRequest` nor
  `IsolatedOwnerSpec` carries a wheels directory (`stage_wheels` takes an
  owner-chosen destination). A binds `wheels` source paths under
  `owner_spec.private_scratch` and refuses anything outside it. Parent
  confirmation requested.
* **G4 No real three-child OS integration in these tests.** Per the brief the
  parent executes that only after review and allowed pins. The tests drive the
  parent's real FD/socket/Popen bookkeeping through a recording `Popen` fake and
  real socketpairs, so spawn/ACK/reap/close faults are exercised, but no test
  spawns a process.
* **G5 No SDK version field exists in `LaunchDescriptor`.** The worker
  therefore validates the sealed `sdk_root` origin, the per-file `sdk_pins`
  hashes, the raw class role labels and `modal.__version__ == "1.6.3"` (a
  first-party fact), rather than a launch-supplied version.
* **G6 `export_name` derivation.** The frozen contract fixes
  `export_name` as a validated basename created beneath the inherited export
  parent FD but names no source for it. A derives it from the sealed request:
  `export_name = request.output_dir.name` with
  `export_root == request.output_dir.parent`, so the export directory is exactly
  the approved `output_dir` addressed as (parent FD, basename). Parent
  confirmation requested.
* **G7 One interpreter hash read per production dispatch.** `pin_worker_launch`
  re-reads `spec.interpreter` and hashes it to confirm the sealed binding fact,
  so a real dispatch of the real interpreter consumes one interpreter hash read.
  The frozen receipt leaves `interpreter_hash_reads_remaining=0`, so the parent
  must authorize that read (or supply an owner-pinned interpreter) before any
  parent execution. The delivered test suite binds an owned stand-in interpreter
  under `tmp_path` (section 3.2), so the suite consumes 0 installed-interpreter
  reads.

## 7. Post-review corrections (recorded, not silently patched)

These are the corrections A made to its own plan and source while reviewing the
delivered implementation end to end. The plan text above is amended only where
it was factually wrong (the `pin_worker_launch` interpreter line).

1. **The preparation writer creates its own directories.** Section 4.3 said the
   writer "owns the snapshot directory". `_OwnerPreparationWriter` now also
   creates `private_scratch` and the approved export parent at `0o700` before it
   opens anything, because `run_once` inherits an anchored `export_parent`
   directory descriptor and `admit_isolated_owner` creates no directories. A
   writer that required a foreign `mkdir` would make every dispatch fail closed
   on a fresh scratch. An existing directory keeps its own mode. Both are
   exported as `writer.export_dir`, which `_allocate_descriptors` uses for the
   `export_parent` descriptor.
2. **Escalation resolves every channel label.** `_join_all` closes and resolves
   `worker_channel`, `controller_channel` and `gate_channel` by registry label,
   including on the escalation path where `channel is None`. Previously an
   escalated run left `worker_channel` unresolved even though its socket was
   already closed, which kept the owner's custody report dirty.
3. **Test-suite interpreter binding corrected.** The first delivered fixtures
   bound `Path(sys.executable)`, contradicting section 1 ("no test may hash the
   installed interpreter") and section 3.2. They now bind an owned stand-in
   interpreter under `tmp_path`, which is what `OwnedAppStopBinding`,
   `IsolatedOwnerSpec`, `pin_worker_launch` and every launch pin use.
4. **The real original stager is never invoked.** Section 3 forbids it, but the
   delivered `prepare_delegated_teardown` staging test called the real
   `binding.stage`, which reaches
   `modal_app_stop_launcher.stage_trusted_teardown`. That call is now replaced
   by a local stand-in returning a real `TrustedTeardown` over an owned
   executable; everything after the launcher stays the real code path, and the
   test asserts the launcher saw exactly one call with the pinned facts.
5. **Delivered signatures differ from section 4.3.** `IsolatedOwner.seal_inputs
   (*, launch)` derives the staged entries from the writer's own sealed set
   instead of taking an explicit `prepared` tuple (the writer's
   `seal(entries, launch)` still validates the request row and the manifest
   against the pinned launch); the writer class is `_OwnerPreparationWriter(*,
   scratch, snapshot_dir, export_dir, registry, deadline_ns)`, so every anchored
   open is deadline-bounded and the export parent is an explicit approved fact.
6. **Two delivered tests cover section 3.6 through `run_once` itself.**
   `test_run_once_releases_everything_when_the_worker_spawn_fails` and
   `test_run_once_contains_and_joins_the_worker_when_the_control_link_dies`
   exercise the real socketpairs, the real FD allocation/reservation/closure,
   the real `_escalate`/`_join_all` and the real release path with spawn
   injected and no process created. They assert the worker's inherited argv
   fact set and that its seven FD numbers satisfy the frozen
   `WorkerFDNumbers` gate. Delivered total: 151 test functions.
7. **Inherited descriptor labels are namespaced.** `_allocate_descriptors`
   registered the descriptor the children inherit for the snapshot directory
   under the label `snapshot_dir`, which the preparation writer already owns for
   its own anchored directory descriptor. The registry refuses a duplicate
   label, so every dispatch would have died at allocation; and
   `_close_descriptors`, which resolves by that same name, would have marked the
   writer's still-open anchor resolved while closing the inherited descriptor.
   The seven inherited descriptors are now registered and resolved as
   `inherited_request`, `inherited_manifest`, `inherited_launch`,
   `inherited_snapshot_dir`, `inherited_outcome`, `inherited_export_parent` and
   `inherited_journal`. The child fact names (`--request`, `--snapshot_dir`,
   `--export_parent`, ...) are unchanged, so the frozen child argv is untouched.
8. **The export parent is the approved `output_dir.parent`.** The first
   delivered `_allocate_descriptors` opened `private_scratch/export`, so the
   child's sealed `export_name` would have created
   `private_scratch/export/<name>` instead of the approved `output_dir`,
   contradicting G6. `_export_root(authorization)` now derives and validates the
   parent (absolute, non-traversing, never `/`), the writer creates it, and
   `export_root / export_name == output_dir` is asserted by test.
9. **No test can signal a real process group.** The spawn fakes report this
   session's pid, so an escalation or reap-timeout kill would SIGKILL the test
   session itself. An autouse fixture records every `os.killpg` the owner issues
   and answers `ProcessLookupError`, exactly what a vanished child answers, so
   the containment paths still run for real without a real signal.
