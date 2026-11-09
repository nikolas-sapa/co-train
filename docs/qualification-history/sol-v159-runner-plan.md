# V186 fixed native/verifier cwd repair plan

SOURCE-ONLY. Every test UNRUN. Parent owns execution, review and integration.
Only the six TASK paths may change. Accepted B source remains read-only.

## V186 tests first, current scope

Write these two finite regression tests before changing production:

1. `test_native_bootstrap_inherited_cwd_original_phase_discovery`: execute the
   generated fixed native bootstrap at a controlled import/runpy boundary.
   Start at a private fixture representing `/`. Resolve and execute tiny staged
   `train.native_qualification` fixtures for both unchanged original phase
   argvs (phases 1 and 2), using only each fresh child's inherited cwd as its
   module search root. Require 2 correct phase results, fixed source cwd before
   runpy, unchanged bootstrap sys.argv/sys.path behavior and 0 output roots.
2. `test_verify_bootstrap_inherited_cwd_original_phase_discovery`: the identical
   2-phase discovery gate through the fixed verifier bootstrap, including its
   own fixed mode argv. Require 2 correct phase results and 0 output roots.

Each test also runs the unchanged generated bootstrap with the controlled chdir
boundary disabled: parent module discovery still succeeds through its inserted
source path, but the first fresh phase discovery must raise ModuleNotFoundError,
with 0 phase fixture executions. Neither test replaces `_phase_argv`, uses the
author's current interpreter sys.path/sys.modules for discovery, or launches a
subprocess. Explicit PathFinder search paths and fresh execution namespaces
isolate the tiny private fixtures. Counts: 2 added tests, 4 positive phase
discoveries and 2 negative discovery refusals, all UNRUN.

Existing `test_raw_exec_counts_timeout_two` retains the initial SDK workdir `/`;
`test_bootstrap_no_installed_module_or_roots` retains absent-output coverage.
Those existing tests are UNRUN too.

Only after test source is written: import os/runpy/sys in `_mode_argv`, chdir to
the fixed `/opt/qualification/source` before runpy, retain the existing source
path insertion, sys.argv and runpy call. No caller-selected cwd, PYTHONPATH or
command. No original supervisor, phase argv, verifier or B changes.

**Cleanup remains BLOCKED.** Parent selected a killable local process, not an
incomplete-cleanup custody exception. The sealed host cannot be pickled/forked.
A new owner/delegation interface awaits the separate parent spike. Do not change
the current cleanup/bridge or improvise that interface in V186.

## Historical V172 plan, not additional V186 authorization

## Tests first

Finite ordinary pytest functions, controlled dependencies, no SDK, subprocess,
network or plugins. Tiny local fixtures only. These cases precede implementation.

### Transport

1. `test_import_and_raw_resource_binding`: import succeeds; resource object identity
   retained, foreign explicit binding refused, raw fake has no `.aio`.
2. `test_raw_exec_counts_timeout_two`: clock 100/deadline 102 passes timeout 2;
   exec/wait/drain awaited once, EOF once, payload counts 11/7.
3. `test_actual_rpc_frame_split_65540`: actual put generator's 65536-byte body
   produces 65540-byte frame; all SDK writes <=65536, exact input recovered.
4. `test_stdin_8mib_bound`: 17 MiB input, maximum buffered <=8388608, 3 drains.
5. `test_mutually_dependent_streams`: each pipe waits for the other, both complete.
6. `test_caps_types_deadlines`: cap 65536 accepted, 65537 refused; nonbytes,
   NaN/past deadline and bad argv refuse, invalid arguments cause 0 execs.
7. `test_actual_wait_minus_one_and_nonzero_refuse`: actual waits -1 and 3 accept 0.
8. `test_ambiguous_start_never_reissued`: failed start poisons, 1 exec total.
9. `test_quiet_iterator_end_not_completion`: empty SDK iterator/wait 0 refuses.
10. `test_envelope_invalid_records_accept_zero`: absent/truncated/duplicate,
    nonce/stream/count/hash/status mutations all refuse.
11. `test_envelope_valid_pair_exact_payload`: valid terminal pair strips framing,
    returns exact binary payload, actual wait 0, two pipe EOFs.
12. `test_fixed_launcher_invoked_with_controlled_child`: invoke fixed launcher
    with in-memory child pipes, actual child wait status 0, two terminal records.
13. `test_rpc_exact_metadata_types_and_pins`: exact keys, int not bool,
    lowercase 64 hex, declared body size/hash and caller pins checked independently.
14. `test_rpc_duplicate_nonfinite_trailing_truncation`: each malformed response
    refuses; empty put ack has exactly one zero terminator.
15. `test_manifest_canonical_bounds`: dot/dotdot/slash aliases/backslash/duplicates
    refuse; JSON/member/depth/aggregate at max+1 refuse; output-only manifest.
16. `test_streaming_response_decoder`: fragmented 65536-byte body writes bounded
    chunks to sink, no whole-file accumulator, final hash/size checked.

### Runner

17. `test_unauthorized_zero_bridge_and_lifecycle`: actual public entry refuses
    with 0 loader calls and 0 lifecycle calls.
18. `test_binding_refusal_zero_bridge`: upload/setup drift, 0 bridge imports.
19. `test_upload_snapshot_refusals_zero_lifecycle`: wrong bytes/size/path,
    symlink/hardlink/FIFO/redirected ancestor, 0 SDK calls/0 transmitted bytes.
20. `test_snapshot_retained_not_caller_file`: validated snapshot survives original
    replacement; 65536-byte maximum reads, private dir700/file600/single link.
21. `test_request_exact_original_schema`: original complete worker wire canonical
    payload matches; path-only mutation with same path-independent binding refuses.
22. `test_bootstrap_no_installed_module_or_roots`: fixed bootstrap compiles exact
    approved B source; initializes only fixed roots; output remains absent.
23. `test_cleanup_all_early_failures`: ambiguous open, arm, transport constructor
    and create failures each await stop exactly once; unknown end deadline now.
24. `test_window_reserves_and_1800_ceiling`: work=end-150, verify=end-90,
    export=end-30, cleanup=end; 1800 accepted, 1801 refused before create.
25. `test_native_mode_actual_observer_and_latch`: invoke --native with controlled
    original worker dependencies, 2 real function returns observed, latch before
    worker; second attempt invokes worker 0 additional times.
26. `test_native_mode_prior_profiler_and_failure_restore`: prior profiler refuses;
    worker failure restores prior profile; missing/duplicate observations refuse.
27. `test_verify_mode_original_once`: invoke --verify, full verifier 1 call,
    actual PIDs/codes and host-issued IDs projected inertly, descriptor index 3.
28. `test_verify_mode_refusal_and_failure_no_receipt`: invalid observation 0
    verifier calls; verifier failure creates 0 success receipts.
29. `test_all_artifacts_exported`: full fake pipeline exports every receipt member,
    not merely 3 JSON files; byte/hash re-read from disk, exclusive root.
30. `test_anchored_export_alias_and_short_write`: partial writes complete;
    redirected ancestors/changed file identity/hardlinks refuse.
31. `test_bridge_aio_identity_and_loop`: fake loader dispatch once, original
    argument/result identities preserved; SDK operations all on bridge loop.
32. `test_cancel_before_admission_no_impl`: cancellation before startup ACK,
    closure later sees intent; 0 implementation/resource calls.
33. `test_cancel_after_admission_cleanup_joined`: cancel admitted work once,
    stop1 completes before cancellation escapes, including repeated cancellation.
34. `test_admission_and_cleanup_bounded`: unacknowledged startup and stalled
    cleanup do not wait forever; no unknown-resource termination claim.
35. `test_host_imports_no_tensor_stack`: owned imports add 0 tensor modules.
36. `test_full_pipeline_failure_no_retry`: native failure/ambiguity -> verify0,
    native1, stop1; receipt hash/truncation refuses.

Existing functional expectations retained, incorrect raw fakes and timeout
expectation repaired. Tests are evidence only after parent execution, never
native/scientific or real SDK proof.

Additional named finite cases exercise the same gates through real entry points:
`test_actual_original_schema_preflight_and_public_success`,
`test_actual_public_preflight_wrong_request_bytes_and_path_zero_sdk`,
`test_public_bridge_original_argument_identity_separate_loop`,
`test_public_cancellation_actual_owned_stop_once`,
`test_native_missing_duplicate_returns_refuse_and_restore`,
`test_export_parent_changed_after_preallocation_refuses_zero_files`,
`test_fresh_disk_includes_output_reserve_before_snapshot`,
`test_export_replaced_inode_and_new_hardlink_refuse`,
`test_full_success_path_all_nine_exports_and_reserves`,
`test_full_pipeline_native_and_receipt_refusals`,
`test_caller_deadline_without_pipe_completion`,
`test_envelope_fragmentation_and_framing_cap`,
`test_unvalidated_caller_stream_refused_before_first_wire_byte`,
`test_manifest_global_worst_case_numeric_gates`, and
`test_put_100000_exact_two_frames_and_one_terminator`.
Numeric global manifest gates include 10000/10001 members, depth32/33,
8GiB/8GiB+1 aggregate declarations, and canonical 8MiB/8MiB+1 JSON.
No large asset files are created by these cases.

## Implementation after tests

1. Inspect original request serialization, worker, full verifier, accepted B and
   only named raw SDK/synchronizer sources.
2. Repair raw transport; fixed stdlib completion launcher and strict incremental
   envelope/B decoders, bounded independently for payload and framing.
3. Anchored source snapshots and exact original wire comparison before bridge.
   Bootstrap accepted B directly from approved source bytes, cwd `/`.
   Remove generic caller streams from puts: only an actual retained validated
   snapshot may generate put frames. Bootstrap creates only fixed roots and
   necessary ancestors of sealed upload destinations, since B does not mkdir.
4. Bridge public async entry through call-time synchronizer loader. Startup ACK,
   intent flag, single owned cancellation, joined bounded cleanup on SDK loop.
5. Cleanup begins before open; arm before create; fixed reserves. Keep original
   native pipeline, observe original return frames without replacements.
6. Remote full verifier once; canonical 3-evidence descriptor index on stdout;
   output-only B manifest and streaming GET of every receipt-pinned artifact.
7. Anchored exclusive local exports, complete writes, actual disk rehash and
   retained preallocation-parent identity checks. Update report with source-only
   limitations. Actual source/model/data local paths must match the original
   serializer's `_StagedAsset.host_path`, not merely its four wire attributes.

## Non-goals

No execution/import of project code while authoring, tests, commands, delegation,
Git, SDK/provider/network calls, asset reads, installations or configuration
changes. No B/native/helper edits. No retries/replacements, alternative trainers,
invented SDK handles/authority/success codes or strict/science claims.

## Parent-only gates

Run all finite tests plus red mutation controls; sterile pinned SDK1.6.3
raw/synchronizer coupling; fresh snapshot disk/preparation accounting for actual
5.6GB bundle; live fit, byte delivery, watchdog and charged-end checks. None is
approved or claimed by source work.
