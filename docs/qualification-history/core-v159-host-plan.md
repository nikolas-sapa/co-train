# V159 Core host plan: engineering authority and Modal lifecycle (track A)

## Revision 4, bounded backend correction, test plan BEFORE fixes

Provenance: Core Qwen original host implementation, backend source corrections.
Only the two host modules, their two tests and these two docs may change.
The original stop binding/tests, SDK, strict/native/default paths stay untouched.
All revised host tests remain UNRUN; parent owns execution and review.

Numeric test-first acceptance criteria and named additions:
1. `test_identical_policy_bytes_different_paths_refuse_substitution`: two
   private directories, identical policy bytes and the same original request;
   claim A's marker first, claim B independently, refuse host(A, resB) before
   SDK validation/image/bind/allocation. Exactly 0 SDK calls, resB unconsumed,
   both markers unchanged; same-pin legitimate construction still succeeds.
   The same witness also refuses a size-only FilePin mismatch (same path/hash).
2. `test_policy_fifo_open_requires_nonblocking` and
   `test_append_fifo_open_requires_nonblocking`: real FIFOs, os.open
   interceptor asserts O_NONBLOCK BEFORE invoking the real syscall, then
   nonregular rejection with 0 reads/writes. Missing flag fails finitely.
   `test_policy_replacement_during_read_refuses_claim`: replace the policy
   with identical bytes but a different inode during a real read; reject before
   marker creation, retain both files, 0 live tracked descriptors.
3. `test_claim_fsync_file_then_directory_before_return`: actual descriptor
   types prove ordered file fsync then retained-directory fsync (2 calls)
   before the claim can be consumed. `test_claim_directory_fsync_failure`
   injects the exact directory sync error; no reservation returned, marker
   remains, tracked open/close counts balanced.
4. `test_close_short_write_releases_directory`,
   `test_close_fsync_failure_releases_directory`,
   `test_close_replacement_releases_directory`: closing failure releases all
   tracked FDs, preserves marker/replacement, sets closed, prevents consume
   and record_identity, repeated close adds 0 writes. Injected primary error
   survives cleanup errors. Add
   `test_stop_owned_close_failure_does_not_leak_cached_reservation` to check
   cached stop outcome still leaves 0 reservation FDs and no second write.
5. `test_append_mode_drift_refuses_before_write` and
   `test_append_owner_drift_refuses_before_write`: same inode with 0666 mode
   or fstat-injected foreign owner refuses with exactly 0 record writes.
   Exact 0600 positive append remains valid. Check owner, exact private mode,
   regular/single-link and named/opened identity each time.
6. Correct independent-approval fixtures in
   `test_reservation_required_and_unused` and
   `test_reservation_bound_to_claiming_authorization`: distinct bytes (thus
   distinct markers), no expectation weakened. The identical-byte case stays
   separate and uses distinct private directories.

Implementation sequence after plan: retain complete policy FilePin on
AttemptReservation and compare path/size/hash plus request binding before SDK;
add nofollow/nonblocking opens and before/after actual FD/path checks; sync
new marker's file then retained directory before return; finally-release
directory on close failure with terminal state and primary-error preservation;
write finite witnesses and correct colliding fixtures.

Preserve closed fixes: GPU-label count binding, sealed base-only image factory,
ArmError controller custody, intentional raw async SDK class/coroutine chain.
No new workdir assertion: create inherits image workdir (None at host level).
Non-goals: SDK/cloud/paid approval, commands, tests/import execution, Git,
processes, original watchdog/launcher edits, arbitrary marker cleanup/recovery.

Revised source counts: 38 engineering + 33 lifecycle = 71 in the two edited
test files, plus the parent's supplied unchanged 19 stop-binding cases = 90.
All UNRUN. The historical Core Qwen plan below records revisions 1-3; revision 4
supersedes their hash-only reservation matching and successful-close-only FD
release descriptions. Its six-path edit scope overrides the historical eight.

## Historical Core Qwen plan, revisions 1-3

Status: SOURCE-ONLY, all tests UNRUN. Parent owns execution, review,
integration, commits and every real/paid provider action. This plan was
written BEFORE the implementation it names.

Revision (parent-observed integration defects 1-5, applied before the test
files were written; test-first order preserved):

1. `host.resource` is the actual retained Sandbox object (None before
   creation); the sealed caps are exposed separately as
   `host.resource_config` and the constructor keyword is `resource_config`.
2. Real App/run-context handles are retained BEFORE awaiting context entry,
   and the Sandbox handle immediately after the create response BEFORE
   ID/deadline/persistence validation, so cleanup never loses real handles.
3. `stop_owned` always attempts the bounded independent owned cleanup,
   including when the caller deadline is already exhausted (bounded per-step
   floor 0.25s, `deadline_exhausted` label); no replacement, no false
   charged-end claim. New named test 22 below.
4. SDK class-label/coroutine-shape checks are honestly scoped as structural
   binding only, not genuine source-compatibility proof; the parent
   separately performs the real SDK check.
5. The existing watchdog custody API was explicitly inspected and bound
   as-is, with no invented `.finish` or launcher parameters:
   `train/qualification_watchdog.py:281-298` `arm` requires
   `custody.app_identity is app_identity`, `app_identity.app_id == app_id`,
   exact `TrustedTeardown` and a finite deadline within (0,1800] with
   arm+teardown reserve; `Watchdog.finish()` exists at line 220;
   `train/modal_app_stop_launcher.py:29-46` `stage_trusted_teardown` takes
   exactly the 14 keywords the binding forwards, including
   `adapter_module == source_root / "modal_app_stop.py"`.

Revision 2 (independent-review blockers 1-4, named tests planned here BEFORE
the code/test changes; test-first order preserved):

1. One-GPU escape closed: the gpu label is parsed at issuance as
   `name[:count]`; a suffix count must equal the charged
   `workload.gpu_count` (exactly 1; the budget independently refuses
   gpu_count != 1), fallback syntax (`any`, any casing) and list/multi-label
   syntax (commas, semicolons, whitespace, repeated colons, leading zeros,
   empty name/count) are refused, and the canonical label binds through
   `authorization.gpu_label` to `resource_config.gpu` by exact equality.
   Named tests: A21 (issuance refusals) and B28 (host-side binding, 0
   App/create calls on refusal).
2. Deterministic policy-bound claim: `claim_attempt_reservation` no longer
   accepts a caller-chosen path. Its only parameter is the sealed
   `EngineeringAuthorization`; the record path is derived deterministically
   as `policy_pin.path.parent / (".qualification-attempt-" +
   policy_pin.sha256 + ".jsonl")`, sealed to the exact owner-approved
   policy FilePin's owner-controlled directory, NOT to an operation nonce,
   request variant or caller filename. The reserved line records
   `policy_sha256` and `request_binding` (approval/request identities).
   Reissued authorizations under the same policy pin map to the same record
   and refuse (FileExistsError) without reading/recovering the old record;
   alternate reservation roots/paths under the same approval are
   structurally impossible (no path parameter exists). Changing the
   approved policy FilePin requires a new explicit owner approval (a new
   FilePin at issuance), never worker JSON. Named tests: A13-A15 revised,
   A22-A23 added.
3. Sealed base-only image: `ModalOwnedHost` no longer accepts a caller
   `image` parameter. The host constructs the lazy Image internally through
   the owner-controlled factory `sealed_candidate_image(sdk, authorization)`
   from the sealed immutable base reference bound at issuance (equal to the
   frozen candidate recipe), using exactly `from_registry(base,
   secret=None, setup_dockerfile_commands=[], force_build=False,
   add_python=None)`; no installation/build/layers/mounts exceptions exist.
   Caller-supplied objects, even of the same class, are refused before any
   App/allocation (TypeError on the removed keyword, every SDK counter 0).
   Class labels remain structural binding only and claim no SDK-integrity
   proof. `host.image` exposes the retained sealed object. Named tests:
   B26, B27; B16 updated to `host.image`.
4. Arm ambiguity: the existing `watchdog.arm` can raise `ArmError`
   (train/qualification_watchdog.py:193-198, raised at 348-355 `from
   primary`) carrying the live `.controller` after the controller child
   exists. `begin_gpu_window` retains `error.controller`, marks
   `arm_ambiguous` and rethrows with the primary cause intact; zero rearm
   and zero create calls occur after ambiguity; `stop_owned` finishes the
   retained controller exactly once (idempotent retained outcome),
   preserving primary errors and actual owned identities. The real existing
   watchdog APIs are kept; no custom supervisor. Named tests: B29, B30.

Counts after revision 2: 23+30+19=72 named tests.

Revision 3 (V171 durable-claim corrections, the 2 remaining REAL bypasses;
named tests planned here BEFORE the code/test changes):

1. Cross-approval host construction refused
   (`qualification_modal_host.py` checked reservation type/state only, so
   a claim under approval B could construct a host for approval A or
   reissued A): the claim now retains the claim's sealed approval
   identity (`policy_sha256`, `request_binding`) on the
   `AttemptReservation`, and the host constructor requires an exact match
   with the presented authorization BEFORE `_require_sdk`, the image
   factory, the App and any create (all SDK counters 0 on refusal); the
   refused reservation stays unconsumed. Named test: B31.
2. Claim-side policy/ancestry validation
   (`qualification_engineering_host.py` validated only the FilePin shape,
   the policy need not exist, and the parent could be a symlink, so
   O_NOFOLLOW on the final filename alone was insufficient):
   `claim_attempt_reservation` now
   - anchors at "/" and traverses the policy parent with per-step
     `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` openat, fstat-checking every
     ancestor: owner (euid) or root ownership required; group/other-
     writable directories refuse unless root-owned AND sticky (OS temp
     ancestors like /tmp); the immediate claim directory must be
     euid-owned and not group/other-writable (private claim directory);
     root-owned non-writable OS ancestors are trusted (no blind
     require-all-ancestors-same-UID);
   - validates the ACTUAL bounded policy bytes relative to the retained
     directory FD (O_NOFOLLOW): regular file, st_nlink == 1 (hardlink/
     alias refuses), owner/root ownership, no group/other write bits,
     st_size == pin.size, bounded read (pin.size <= 2**26) with
     sha256(bytes) == pin.sha256;
   - claims the record relative to the SAME directory FD
     (O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW 0o600) and compares
     opened/final identities by fstat-after-open (regular, nlink 1,
     euid-owned, mode 0600, size 0) before writing the reserved line; the
     anchored nofollow opens leave no discovery TOCTOU window;
   - closes every FD on every failure path (zero FD leak) and retains
     exactly one directory FD per live reservation, released at
     `close(event)`;
   - appends open the record NAME relative to the retained directory FD
     (no pathname/symlink reopen) and compare (st_dev, st_ino) against
     the identity recorded at claim: replacement/alias refuses with zero
     writes.
   Old records are still never read/recovered/modified; the only file
   read is the owner-approved policy itself (bounded, byte-verified).
   Named tests: A24-A28; the previous claim tests A13-A15/A17-A19/A22
   keep their semantics but their fixtures are corrected to REAL private
   policy files with matching FilePins (updated, not weakened).

Counts after revision 3: 28+31+19=78 named tests.

## Owned paths (exactly, per shared contract track A8paths A)

- `train/qualification_engineering_host.py` (authority/reservation)
- `train/qualification_modal_host.py` (real SDK lifecycle)
- `train/qualification_owned_stop.py` (concrete independent AppStop watchdog binding)
- `train/test_qualification_engineering_host.py`
- `train/test_qualification_modal_host.py`
- `train/test_qualification_owned_stop.py`
- `docs/core-v159-host-plan.md`, `docs/core-v159-host-report.md`

No existing tracked source changes. No SDK edits. No commands were run.

## Named numeric test plan (before implementation)

Finite ordinary pytest tests, no parametrization, no plugins, no processes,
no SDK calls while authoring. Fake SDK classes in tests carry the exact
`__module__`/`__name__` of the real async implementation classes so the
host's origin checks are exercised; genuine SDK use is a later parent check,
not mocked proof. Each of the three files carries >=18 tests (contract item 1
requires >=18 for the host/authority area; this plan delivers 23+30+19=72).

### train/test_qualification_engineering_host.py (28 tests)

1. `test_issue_binds_exact_request_digest` — issued `request_binding` equals
   an independently recomputed `native._request_binding(request)` (64 hex).
2. `test_issue_recomputes_plan_and_accepts_no_plan_label` — issuance has no
   plan parameter; `authorization.plan` field-for-field equals a fresh
   `plan_engineering_budget(...)` recomputation (7 breakdown pairs equal).
3. `test_workload_duration_1800_accepted` — duration_seconds=1800 issues.
4. `test_workload_duration_1801_rejected` — duration_seconds=1801 raises
   ValueError, no authorization object exists.
5. `test_policy_pin_requires_exact_native_filepin` — `True`, `1`, `"path"`,
   `{"path":...}` JSON dict all raise; only `native.FilePin` issues.
6. `test_policy_pin_rejects_bad_shape` — relative path, `..` component,
   size 0, 63-hex and 65-hex digests, uppercase hex all raise (5 refusals).
7. `test_expired_authority_refuses` — `require_valid(now_seconds=expires)`
   and `expires+1` raise PermissionError; `expires-1` passes (boundary 0).
8. `test_authority_expiry_window_bounds` — expires-now of 0, -1 and 86401
   rejected at issuance; 1 and 86400 accepted.
9. `test_clock_backwards_refuses` — `require_valid(now_seconds=issued-1)`
   raises PermissionError.
10. `test_authorization_single_use_binding` — `_bind_once()` second call
    raises PermissionError; first succeeds.
11. `test_authorization_not_serializable` — `pickle.dumps` raises TypeError;
    `__reduce_ex__` raises TypeError.
12. `test_budget_helper_alone_is_not_authority` — no public constructor
    path accepts an `EngineeringBudgetPlan`: direct construction without the
    issuance token raises PermissionError even with a valid plan.
13. `test_reservation_first_claim_creates_record` — claiming from a sealed
    authorization creates the record at the deterministic policy-derived
    path (`policy_pin.path.parent / ".qualification-attempt-<policy
    sha256>.jsonl"`) 0o600 with exactly 1 byte-exact line
    `{"v":1,"event":"reserved","policy_sha256":...,"request_binding":...}`.
14. `test_reservation_second_claim_refuses_without_reads` — a second claim
    from a REISSUED authorization (same policy pin, fresh clock/expiry)
    raises FileExistsError; file bytes are byte-identical before/after and
    the file still exists (0 reads, 0 deletions, 0 recovery).
15. `test_reservation_existing_symlink_refuses` — pre-existing symlink at
    the derived record path raises (O_NOFOLLOW|O_EXCL); target untouched.
16. `test_reservation_consume_once` — second `consume()` raises RuntimeError.
17. `test_reservation_identity_appends_only` — `record_identity("app", ap-id)`
    and `("sandbox", sb-id)` append exactly 1 line each; bad kind, non-str,
    `ap-` pattern mismatch all raise; file grows append-only (byte prefix
    stable).
18. `test_reservation_close_idempotent` — `close("stopped")` appends 1 line;
    second close appends 0; bad event raises ValueError.
19. `test_reservation_not_serializable` — pickle raises TypeError.
20. `test_uploads_and_setup_argv_sealed_at_issuance` — uploads entries with
    root outside {source,model,data,wheels}, key `..`/absolute/empty, size
    -1 or >2^36, non-hex sha, duplicate (root,key) all raise (>=6 refusals);
    setup_argv empty tuple, 65 items, 4097-char item, embedded NUL all raise
    (4 refusals); exact valid inputs issue and expose byte-equal tuples.
21. `test_gpu_label_one_exact_gpu_only` — "A100" and "A100:1" issue and
    expose `authorization.gpu_label` byte-equal; "A100:8", "A100:2",
    "A100:0", "any", "ANY", "any:1", "A100,A10G", "A100;A10G", "A100 2",
    "A100:", ":1", "A100:01", "A100:1:2", "" and 42 all raise ValueError
    (15 refusals); a `GpuWorkload(gpu_count=2, ...)` with "A100:2" also
    refuses (budget first), and the parsed suffix
    count is bound to the charged `workload.gpu_count` (1).
22. `test_claim_location_sealed_to_policy_identity` —
    `inspect.signature(claim_attempt_reservation)` has exactly 1 parameter
    named `authorization`; passing `record_path=...` raises TypeError; a
    reissued authorization (same pin, fresh now/expiry, fresh request
    object) maps to the identical derived path
    (`sealed_claim_record_path`), and the second claim refuses with
    FileExistsError leaving the old record bytes unchanged; the reserved
    line carries both approval identities (`policy_sha256` == pin.sha256,
    `request_binding` == the issuing authorization's binding).
23. `test_claim_requires_sealed_authorization` — True, a dict, a bare
    native FilePin and None raise PermissionError and create 0 files
    anywhere under the owner directory (empty directory witness).
24. `test_claim_validates_real_policy_bytes_and_ownership` — a REAL
    private policy file with matching FilePin claims (reserved line
    byte-exact with `policy_sha256` + `request_binding`); 9 refusals each
    leaving ZERO `.qualification-attempt-*` files in tmp_path: missing
    policy, byte drift (same size, different bytes), size drift (+1),
    hash drift, symlinked policy path, hardlinked policy (st_nlink 2),
    directory at the policy path, group-writable policy (0o660),
    other-writable policy (0o664); each raises OSError-family with no
    record created and no SDK involvement.
25. `test_claim_ancestor_chain_and_private_directory_validated` — 4
    refusals leaving zero record files: symlinked immediate parent
    (nofollow traversal refuses), group-writable immediate parent
    (0o770), other-writable intermediate ancestor (0o777), group-writable
    intermediate ancestor (0o775); positive control: the identical layout
    with the intermediate at 0o755 claims successfully (the ancestry check
    can pass, not only fail); root-owned non-writable OS ancestors above
    are trusted, so pytest tmp_path chains claim.
26. `test_claim_symlinked_parent_switch_cannot_double_claim` — after a
    successful claim, renaming the parent aside and symlinking it to a
    fresh directory refuses the reissued authorization's claim
    (OSError); the switched-to directory receives zero records, with AND
    without a copied policy file inside it; the original marker bytes
    remain unchanged under the renamed parent (unread, unrecovered,
    unmodified).
27. `test_claim_failure_paths_close_all_fds` — monkeypatched os.open/
    os.close counters: a successful claim leaves exactly 1 retained FD
    (opened == closed + 1, the directory FD); every append is balanced
    (opened == closed); each failure path (reissued second claim,
    hash-drifted policy, symlinked parent) closes every FD it opened
    (opened == closed); zero FD leak on all paths.
28. `test_append_relative_to_retained_dir_fd_rejects_alias` — after a
    baseline append, renaming the record aside and symlinking an attacker
    target at the record name refuses the next append (OSError) with the
    target and the moved record unchanged; a fresh regular-file
    replacement at the record name refuses (inode mismatch vs the
    retained claim identity) with zero writes; unlinking the replacement
    refuses (ENOENT); the moved original bytes are unchanged throughout.

### train/test_qualification_modal_host.py (31 tests)

1. `test_default_no_authority_refuses` — constructing `ModalOwnedHost` with
   a plan object, `True`, a dict or None as authorization raises
   PermissionError; fake SDK counters stay at exactly 0 App/build/create/exec
   calls.
2. `test_reservation_required_and_unused` — missing/foreign reservation type
   raises; consumed or closed reservation raises; 0 SDK calls.
3. `test_sdk_class_origin_checked` — SDK namespace whose App/Sandbox/Image
   `__module__`/`__name__` deviates by 1 character raises ValueError; 0 calls.
4. `test_sdk_coroutine_exports_checked` — non-coroutine `Sandbox.create` or
   `App.stop` raises ValueError.
5. `test_cpu_limit_matches_charged_planning` — cpu=(2.0,4.0) with
   workload.cpu_cores=4 accepted; limit 4.5, 3.0, request>limit, non-float,
   non-tuple all raise (5 refusals); accepted maximum tuple value == 4.
6. `test_memory_limit_matches_charged_planning` — memory=(8192,16384) with
   ram_gib=Decimal(16) accepted (16*1024=16384); limit 16385, 16383,
   non-int, request>limit raise (4 refusals).
7. `test_gpu_label_bound_to_authorization` — resource.gpu equal to sealed
   label accepted; any drift raises ValueError.
8. `test_open_app_real_empty_ephemeral_once` — App constructed with
   `(None, include_source=False)` exactly, run entered with `detach=False`,
   `ap-`+22-alnum ID retained, `host.app_id` set, reservation consumed once
   and identity line appended; second `open_app` raises and App constructor
   call count stays exactly 1.
9. `test_open_app_ambiguous_refuses_retry` — run entry raising leaves
   `open_ambiguous` True; retry raises; App constructor calls == 1 (<=1).
10. `test_open_app_deadline_bounds` — deadline <= now, > preparation_deadline
    (700.0 at prep=600, clock=100.0): 700.0 accepted, 700.5 refused, 99.0
    refused; refusals happen before `consume()` (reservation unconsumed).
11. `test_open_app_requires_valid_authority` — expired wall clock raises
    PermissionError; 0 SDK calls.
12. `test_one_resource_latch` — second host's `open_app` raises while the
    first is active; after the first `stop_owned` completes, the latch frees
    (0 concurrent active hosts, exactly 1 at peak).
13. `test_begin_gpu_window_1800_end` — duration 1800 at clock 100.0 returns
    exactly 1900.0; end-now <= 1800; second call raises RuntimeError.
14. `test_begin_gpu_window_arms_watchdog_before_create` — stage called with
    `expected_app_id == host.app_id` and `expires_at - wall_now <= 1800`;
    arm called with `custody.app_identity is app`, exact `app_id`,
    `deadline == end`, exact evidence path; arm precedes any create call
    (create counter 0 at arm time).
15. `test_begin_gpu_window_requires_open_app` — before open_app raises
    RuntimeError; 0 staging/arm calls.
16. `test_create_once_exact_kwargs` — captured kwargs equal the sealed set:
    `app` is retained App, `image` is `host.image` (the internally
    constructed sealed base-only Image), `gpu` == sealed label,
    `cpu`/`memory` tuples, `block_network=True`, `timeout` == ceil(window
    end - now) within [1,1800], `secrets=None`, `include_oidc_identity_token`
    False, `encrypted_ports`/`h2_ports`/`unencrypted_ports` empty,
    `pty=False`, `pty_info=None`, `custom_domain=None`, `proxy=None`,
    `cidr_allowlist`/`outbound_cidr_allowlist`/`outbound_domain_allowlist`/
    `_experimental_outbound_policy` None, `_experimental_enable_snapshot`
    False, `_experimental_persistent` False; sandbox object+`sb-` ID retained.
17. `test_create_once_ambiguous_never_reissues` — create raising (and create
    timing out) leaves `creation_ambiguous` True; every later `create_once`
    raises; total SDK create calls == 1 exactly (<=1 after ambiguity).
18. `test_create_requires_armed_window_and_deadline` — create before
    begin_gpu_window raises; deadline > window end (1900.0) refused at
    1900.5; deadline <= now refused; refusals leave create calls == 0.
19. `test_stop_owned_sequence_and_unknown_ends` — bounded terminate,
    App.stop, context `__aexit__`, watchdog `finish()` each called exactly
    once in order; outcome keeps actual `app_id`/`sandbox_id`;
    `remote_termination == "UNKNOWN"` and `charged_end == "UNKNOWN"` even on
    full success; a stop ACK is never labelled billing end.
20. `test_stop_owned_fallback_and_failure_labels` — sandbox terminate and
    App.stop raising still call watchdog `finish()`, keep identities, record
    `sandbox_terminate == "UNKNOWN"`, `app_stop == "UNKNOWN"`, error labels
    {"sandbox_terminate_failed","app_stop_failed"}, and never fabricate
    success; second `stop_owned` returns the identical retained outcome with
    0 additional SDK calls.
21. `test_require_bindings_refuse_drift` — `require_active` with a different
    request object, mutated digest or expired authority raises and 0 SDK
    calls; `require_uploads` accepts DTOs exposing exactly
    `(root,key,size,sha256)` matching the sealed manifest and refuses size+1,
    sha drift, 1 extra item, 1 missing item, DTO missing an attribute
    (5 refusals); `require_setup_argv` accepts the exact argv and refuses
    1-token drift and reordering (2 refusals).
22. `test_stop_owned_cleans_after_caller_deadline_exhausted` — with the
    monotonic clock already past the stop deadline, `stop_owned` does not
    raise: terminate, `App.stop`, context close, watchdog `finish()` and
    reservation close are each still attempted exactly once, the outcome
    carries the `deadline_exhausted` label plus any step failures, keeps
    actual identities and `remote_termination == charged_end == "UNKNOWN"`,
    and no replacement or reissue occurs (create calls stay 1).
23. `test_resource_is_retained_sandbox_and_config_sealed` — `host.resource`
    is None before creation and identity-equal to the actual retained
    Sandbox after `create_once`; `host.resource_config` is the sealed
    ResourceConfig (gpu == sealed label, cpu limit == charged cores,
    memory limit == charged GiB*1024); a config whose gpu drifts 1 char or
    whose cpu/memory limit is off by 0.5/1 is refused at construction
    (>=3 refusals).
24. `test_stop_owned_cleans_retained_handles_after_ambiguous_open` — when
    context entry fails after the App/run-context handles were retained,
    `host.app_id` stays None, `open_ambiguous` stays True, and `stop_owned`
    still attempts the retained `App.stop` and context `__aexit__` (each
    called >= 1), labels their failures, closes the reservation and frees
    the latch, with `remote_termination == charged_end == "UNKNOWN"`.
25. `test_host_not_serializable` — `pickle.dumps(host)` raises TypeError
    and `host.__reduce_ex__(4)` raises TypeError (0 leaks of retained
    handles or sealed authority through serialization).
26. `test_sealed_image_constructed_from_frozen_base_only` — construction
    records exactly 1 `from_registry` call with positional args ==
    (`authorization.image_base_reference`,) (byte-equal to the frozen
    candidate recipe base) and kwargs exactly `{secret: None,
    setup_dockerfile_commands: [], force_build: False, add_python: None}`;
    `host.image` is that returned object; 0 App/run/create/exec calls at
    construction; no other image API surface is invoked (0 layer/mount/
    build witness entries).
27. `test_caller_supplied_image_refused_before_allocation` — passing any
    `image=` keyword to the constructor (even the fake SDK's own Image
    instance, same class) raises TypeError and every fake SDK counter stays
    at exactly 0 (0 App, 0 run, 0 create, 0 from_registry): refusal before
    any allocation, with class sameness proving nothing.
28. `test_gpu_config_bound_to_sealed_one_gpu_label` — issuing with sealed
    label "A100:1": a config `gpu == "A100:1"` is accepted and forwarded
    byte-equal into the create kwargs; configs "A100:8" (multi-GPU escape)
    and "A100" (drift) both refuse with ValueError at construction with 0
    App/run/create/from_registry calls.
29. `test_arm_ambiguity_retains_controller_and_refuses_rearm_create` —
    `watchdog.arm` raising `ArmError(controller)` after the child exists:
    `begin_gpu_window` rethrows the same error (`.controller` and primary
    `__cause__` intact), `host.arm_ambiguous` is True; a second
    `begin_gpu_window` refuses with 0 additional arm calls (total arm calls
    == 1); `create_once` refuses with 0 create calls; `stop_owned` finishes
    the retained controller exactly once (`finish_calls == 1`, report
    returned), preserves the real `app_id`, closes the reservation, frees
    the latch and keeps `remote_termination == charged_end == "UNKNOWN"`;
    a second `stop_owned` adds 0 finishes.
30. `test_stage_failure_marks_arm_ambiguous_without_controller` —
    `stage_trusted_teardown` raising: `begin_gpu_window` rethrows,
    `arm_ambiguous` is True with no controller retained (0 arm calls),
    `create_once` refuses with 0 create calls, and `stop_owned` still
    completes with `watchdog_report is None`, closing the reservation and
    freeing the latch without inventing any billed end.
31. `test_reservation_bound_to_claiming_authorization` — real policy
    fixtures A and B (distinct policy files AND distinct request
    bindings) each claim their own reservation; constructing a host with
    (authorization A, reservation B), (reissued A, reservation B) and
    (authorization B, reservation A) each raises PermissionError BEFORE
    the image factory: ZERO from_registry/app/enter/create calls and
    `authorization.bound is False` on every refusal; both refused
    reservations stay unconsumed; the legitimate pairing (reissued A,
    reservation A) constructs with exactly 1 from_registry call (the
    check can pass, not only fail).

### train/test_qualification_owned_stop.py (19 tests)

1. `test_binding_requires_explicit_ownership_confirmation` —
   `ownership_confirmed` False/None/1/"yes" raises ValueError (4 refusals);
   True constructs.
2. `test_binding_path_validation` — relative interpreter, relative
   source_root, relative sdk_root, relative private_scratch, non-Path
   interpreter raise ValueError (5 refusals).
3. `test_binding_digest_validation` — interpreter_sha256 and adapter_sha256
   of 63 hex, 65 hex, uppercase, non-str raise (>=4 refusals).
4. `test_binding_seconds_bounds` — rpc_seconds 0, -1, 30.5 rejected, 30
   accepted; teardown_seconds 31 rejected, 30 accepted; arm_seconds 5.5
   rejected, 5 accepted; non-finite (inf/nan) rejected (>=8 checks).
5. `test_binding_pins_and_environment_copied` — sdk_pins/environment stored
   as equal-value copies; mutating the caller dict afterwards changes
   nothing observable; empty pins or environment raise.
6. `test_binding_not_serializable` — pickle raises TypeError.
7. `test_stage_delegates_exact_inputs` — with
   `launcher.stage_trusted_teardown` monkeypatched, `stage` passes exactly:
   interpreter, interpreter_sha256, `adapter_module ==
   source_root/"modal_app_stop.py"`, adapter_sha256, sdk_root, sdk_pins,
   private_scratch, expected_app_id, `ownership_confirmed=True`,
   `explicitly_trusted=True`, expires_at, rpc_seconds, environment
   (13 keyword bindings, byte-equal values); the staged TrustedTeardown
   sentinel is returned unmodified.
8. `test_stage_rejects_bad_app_id` — non-str, empty expected_app_id raise
   ValueError with 0 launcher calls.
9. `test_stage_rejects_nonfinite_expiry` — expires_at inf/nan/non-number
   raise with 0 launcher calls.
10. `test_arm_delegates_exact_inputs` — with `watchdog.arm` monkeypatched,
    `arm` passes custody, app_identity, app_id, teardown, deadline,
    evidence_path plus the binding's own teardown_seconds/arm_seconds
    (8 keyword bindings byte-equal); the returned Watchdog sentinel is
    returned unmodified.
11. `test_arm_passes_binding_seconds_not_caller_seconds` — arm kwargs carry
    the constructor values (2.0/0.5), not defaults 1.0/1.0.
12. `test_no_custom_supervision_surfaces` — module exposes exactly
    `OwnedAppStopBinding` publicly; no Popen/socket/thread/signal attribute
    exists on the binding (guard-removal witness: any such attribute added
    later fails this test).
13. `test_stage_and_arm_are_the_only_public_methods` — public method set is
    exactly {"stage","arm"} (witness against added lifecycle hooks).
14. `test_binding_reuses_existing_modules` — module-level
    `launcher`/`watchdog` attributes are exactly
    `train.modal_app_stop_launcher`/`train.qualification_watchdog` (no
    reimplementation).
15. `test_stage_expiry_forwarded_unchanged` — expires_at 1762000000.5
    forwarded byte-equal (no clamping in the binding; the launcher's own
    <=1800s freshness check stays authoritative).
16. `test_stage_expected_app_id_forwarded_unchanged` — "ap-"+22 alnum
    forwarded byte-equal.
17. `test_arm_evidence_path_forwarded_unchanged` — absolute Path forwarded
    by identity (`is`).
18. `test_arm_identity_forwarded_by_identity` — custody/app_identity/
    teardown forwarded by identity (`is`), never copied.
19. `test_binding_constructor_does_no_file_io` — constructor with
    nonexistent synthetic paths succeeds (staging, not construction, touches
    the filesystem); 0 os.open calls observed via monkeypatched os.open
    witness during construction.

## Implementation design (frozen shared boundaries preserved)

### train/qualification_engineering_host.py

- `EngineeringAuthorization`: sealed host-local one-use authorization.
  Private constructor gated by a module-private issuance token; the only
  sanctioned path is `issue_engineering_authorization(...)`, a trusted-host
  API taking the exact original `QualificationRequest` object, the
  operator-policy `native.FilePin`, complete explicit budget inputs
  (`BudgetTerms`, `ResourceRates`, `GpuWorkload`, `PreparationAccount`,
  `AncillaryEstimates`, `now_seconds`, `expires_at_seconds`,
  `preparation_seconds`), frozen candidate image identity
  (base reference + recipe SHA256 from `train.qualification_image_plan`),
  gpu label (parsed at issuance to exactly one charged GPU: a suffix count
  must equal the charged `workload.gpu_count`, and fallback/list syntax is
  refused), sealed upload manifest `(root,key,size,sha256)` and fixed
  offline `setup_argv`. It recomputes `plan_engineering_budget` itself and
  never accepts a plan label; a budget plan alone is not authority. Worker
  JSON/bools/dicts are structurally rejected by exact-type checks. The
  request digest is `native._request_binding(request)`. `require_valid`
  enforces issued-at/expiry against a caller wall clock. Not serializable.
- `claim_attempt_reservation(authorization)` -> `AttemptReservation`:
  the only parameter is the sealed authorization; the private owner-only
  durable record path is derived deterministically via
  `sealed_claim_record_path(authorization)` ==
  `policy_pin.path.parent / (".qualification-attempt-" + policy_pin.sha256
  + ".jsonl")`, sealed to the exact owner-approved policy FilePin's
  owner-controlled directory (no caller-selectable root/path/filename or
  operation nonce). The claim anchors at "/" and traverses the parent
  chain with per-step `O_DIRECTORY|O_NOFOLLOW` openat calls (a symlinked
  parent refuses), fstat-validating every ancestor (owner/root ownership;
  group/other-writable refuses unless root-owned AND sticky; the
  immediate claim directory must be owner-owned and not group/other-
  writable), then validates the ACTUAL policy file relative to the
  retained directory FD (O_NOFOLLOW; regular; nlink 1; owner/root-owned;
  no write bits for group/other; size == pin.size <= 2**26; bounded read
  with sha256 == pin.sha256), and only then creates the record relative
  to the SAME directory FD with
  `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` 0o600 BEFORE any billable API,
  comparing opened/final identities by fstat-after-open (regular, nlink
  1, owner-owned, mode 0600, size 0; the anchored nofollow opens leave no
  discovery TOCTOU window) before writing the reserved line
  (`policy_sha256` + `request_binding`). Every failure path closes every
  FD (zero leak); exactly one directory FD stays retained per live
  reservation and is released at `close(event)`. Appends open the record
  NAME relative to the retained directory FD (no pathname/symlink reopen)
  and compare (st_dev, st_ino) with the claim-time identity: replacement
  or alias refuses with zero writes. An
  existing or ambiguous record refuses with no reads, no recovery, no
  deletion, no signals (append-only afterwards). `consume()` is a one-use
  latch; `record_identity("app"|"sandbox", id)` and `close(event)` append
  bounded JSON lines. `policy_sha256`/`request_binding` read-only
  properties expose the claim's sealed approval identity to the host.
  Not serializable. The original strict owner
  (`train.qualification_owner`) stays untouched.

### train/qualification_owned_stop.py

`OwnedAppStopBinding`: concrete compatible binding over the EXISTING bounded
watchdog mechanisms, no custom process supervision:

- `stage(expected_app_id, expires_at)` delegates to
  `train.modal_app_stop_launcher.stage_trusted_teardown` (exact-owned-ID
  stop executable over the pinned official Modal 1.6.3 SDK, AppStop route
  modal/cli/app.py:407-408 via `train.modal_app_stop`).
- `arm(custody, app_identity, app_id, teardown, deadline, evidence_path)`
  delegates to `train.qualification_watchdog.arm` (independent controller
  child, bounded local teardown, append-only evidence).
The existing watchdog fully supports a real owned-App stop, so no custom
supervisor is introduced. Remaining issues reported in the report doc:
AppStop ACK is not billing-end proof (recorded UNKNOWN), and an ambiguous
`open_app` failure before arming leaves reconciliation to the parent.

### train/qualification_modal_host.py

Inspected actual Modal 1.6.3 async API (read-only, named files):

- `modal/app.py:196-264` `_App.__init__` lazy local constructor
  (`include_source=False` supported); `modal/app.py:423-432`
  `_set_local_app` sets `_app_id` on run entry; `modal/app.py:434-500`
  `run()` is `synchronicity.async_wrap.asynccontextmanager`, which is
  contextlib semantics (`synchronicity/async_wrap.py:67-92`), delegating to
  `modal/runner.py:370-427` `_run_app` (`AppCreateRequest`,
  `APP_STATE_EPHEMERAL` when `detach=False`, heartbeats, no deploy);
  `modal/app.py:1625-1644` `async App.stop()` sends `AppStopRequest`.
- `modal/sandbox/_sandbox.py:179-359` `_Sandbox.create` is a `@staticmethod`
  coroutine with exact kwargs used here (`app`, `image`, `gpu`, `cpu`,
  `memory`, `timeout`, `block_network`, no secrets/OIDC/ports/persistent/
  snapshot); `modal/sandbox/_sandbox.py:1014-1034` `async terminate()`;
  `modal/_object.py:304` `object_id`.
- `modal/_image.py:2281-2364` `Image.from_registry(tag, secret=None,
  setup_dockerfile_commands=[], force_build=False, add_python=None)` is a
  lazy local constructor matching the existing frozen candidate recipe.
  No `.aio` or context-manager syntax was guessed: the host requires the
  exact raw async classes `modal.app._App`, `modal.sandbox._sandbox.
  _Sandbox`, `modal._image._Image` (origin-checked by `__module__`/`__name__`
  and coroutine exports) and awaits their plain coroutines.

`ResourceConfig(gpu, cpu=(request,limit), memory=(request,limit))`: maximum
tuple values must equal the charged planning inputs
(`workload.cpu_cores`, `workload.ram_gib*1024` MiB, exact Decimal equality).

`ModalOwnedHost(*, authorization, reservation, sdk, resource_config,
stop_binding, evidence_path, clock=time.monotonic, wall_clock=time.time)`:

- Default no authority refuses (exact sealed types required).
- The reservation must be claimed under the exact presented authorization
  (`reservation.policy_sha256` == `authorization.policy_pin.sha256` AND
  `reservation.request_binding` == `authorization.request_binding`) —
  checked BEFORE `_require_sdk`, the image factory, the App and any
  create, so a claim under approval B can never construct a host for
  approval A or reissued A (all SDK counters stay 0; the refused
  reservation stays unconsumed).
- `require_active(request)`, `require_uploads(items)`,
  `require_setup_argv(argv)` bind to the sealed approval and refuse drift;
  upload DTOs must expose `root/key/size/sha256`.
- `preparation_deadline`, `app_id`, `sandbox_id` properties; `resource` is
  the actual retained Sandbox object (None before creation) and
  `resource_config` is the sealed ResourceConfig (revision defect 1).
- `async open_app(*, deadline)`: real empty ephemeral App
  (`_App(None, include_source=False)`, `run(detach=False)` entered under
  `asyncio.wait_for`); the App object and run context are retained BEFORE
  awaiting entry (revision defect 2), then the service-issued `ap-` ID is
  validated and persisted to the durable reservation record; one-shot
  (ambiguity refuses retry), behind a process-wide one-resource latch.
- `begin_gpu_window() -> float`: arms the concrete independent owned-App
  stop watchdog (stage + arm) BEFORE create, establishes the single global
  end = now + sealed duration <= 1800 seconds including cleanup, returns end.
- `async create_once(*, deadline)`: one real `Sandbox.create` coroutine
  call, explicit single GPU, CPU/RAM tuples, `block_network=True`, no
  secrets/OIDC/ports/persistent/snapshot, sandbox `timeout` bounded by the
  window; the returned Sandbox is retained BEFORE its `sb-` ID is validated
  or persisted (revision defect 2); after any ambiguity create is called
  <=1 total, never reissued.
- `async stop_owned(*, deadline)`: bounded `Sandbox.terminate()`, retained
  `App.stop()`, run-context `__aexit__` close, then the independent watchdog
  `finish()` as fallback; ALWAYS attempted, including after the caller
  deadline is exhausted (bounded 0.25s per-step floor plus a
  `deadline_exhausted` label, revision defect 3); preserves actual
  App/Sandbox identities; records `remote_termination="UNKNOWN"` and
  `charged_end="UNKNOWN"` always; no cost estimate guarantees a total and no
  shutdown ACK proves billing ceased. Idempotent, returns the retained
  `OwnedStopOutcome`.
- SDK class-label/coroutine-shape checks are structural binding only, not
  genuine source-compatibility proof (revision defect 4); the parent
  separately performs the real SDK check.
- Sealed base-only image (revision 2 blocker 3): the host constructs the
  lazy Image internally via the owner-controlled factory
  `sealed_candidate_image(sdk, authorization)` from the sealed immutable
  base reference (`from_registry(base, secret=None,
  setup_dockerfile_commands=[], force_build=False, add_python=None)`, base
  re-checked equal to the frozen candidate recipe). No caller `image`
  parameter exists; supplying the keyword refuses with TypeError before any
  App/allocation. `host.image` exposes the retained sealed object. No image
  build/staging API is exposed; no installation/build/layers/mounts
  exceptions.
- Arm ambiguity (revision 2 blocker 4): on any stage/arm failure
  `begin_gpu_window` retains `ArmError.controller`
  (train/qualification_watchdog.py:193-198), marks `arm_ambiguous` and
  rethrows with the primary cause intact; zero rearm and zero create calls
  after ambiguity; `stop_owned` finishes the retained controller exactly
  once.

## Non-goals (mandatory, from the shared contract)

No paid/live actions, unreviewed scientific claims, legacy 179/200 audits,
source gate weakening, blanket trust/sandbox assertions, global
configuration/provider/trust/model changes, local/global installs,
locks/credentials/.env/binary/model/data/wheel reads,
installed-distribution enumeration, SDK edits, protected original repository
changes, old marker recovery/deletion/signalling, custom process supervisor,
worker Git/delegation. Tests stay UNRUN until the parent validates. No
automatic retry/replacement, no scientific campaign, no relaxation of the
existing strict <=25/default CLOSED gates; this engineering route is
explicitly separate.
