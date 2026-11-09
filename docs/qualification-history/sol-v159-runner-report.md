# V186 fixed native/verifier cwd repair report

**SOURCE-ONLY, UNRUN. Not approval. Parent review/execution remains blocking.**
Factory GPT, not verified Alliance. Original rejected files were parent-frozen
before this repair. Only the six TASK paths changed.

## V186 changes and regression source

The test plan was updated first, then the two regression tests were authored,
then the production bootstrap changed. `_mode_argv` now imports `os,runpy,sys`
and calls `os.chdir('/opt/qualification/source')` before the existing source
sys.path insertion, fixed sys.argv and runpy call. Both native and verifier
constants consume that fixed bootstrap. No caller-selected cwd or PYTHONPATH.
The initial raw SDK workdir and outer launcher cwd remain `/`.

Added exactly 2 ordinary pytest functions in
`train/test_qualification_engineering_run.py`:

- `test_native_bootstrap_inherited_cwd_original_phase_discovery`
- `test_verify_bootstrap_inherited_cwd_original_phase_discovery`

Each executes its generated mode bootstrap through controlled imports/runpy,
then discovers and executes tiny private staged phase fixtures using the original
unchanged `_phase_argv` for phases 1 and 2. PathFinder receives only explicit
fixture paths; fresh phase lookup receives inherited cwd, not parent sys.path
or sys.modules. Fresh execution namespaces keep the two phase results separate.
Each test also disables the controlled chdir effect without changing generated
argv: parent source-path discovery must still work, but first-phase discovery
must refuse before any phase fixture executes. Required totals are 4 positive
phase discoveries and 2 negative discovery refusals. **All are UNRUN.**

Existing `test_raw_exec_counts_timeout_two` checks initial workdir `/`;
`test_bootstrap_no_installed_module_or_roots` checks that first RPC and request
materialization do not precreate output. These tests remain unchanged and UNRUN.
New fixtures also require output to stay absent. No original native supervisor,
phase argv, verifier, B source or cleanup code changed.

V186 edits are confined to `train/qualification_modal_transport.py`,
`train/test_qualification_engineering_run.py` and the two assigned plan/report
documents. The other two assigned paths were not changed in this repair.
File-tool inspection only, no executed checks or temporary helper files.

**Cleanup remains BLOCKED.** Parent chose a killable local process, not an
incomplete-cleanup custody exception. The sealed host cannot be pickled/forked;
a new owner/delegation interface must await the separate parent spike. The
existing bridge is not an accepted cleanup solution. No architecture or cleanup
implementation was improvised here.

## Historical V172 source changes, not V186 approval

- Correct `typing.BinaryIO`; raw `host.resource` identity binding. Await raw
  `exec`, `drain`, `wait`, use synchronous writes/EOF. Integer timeout rounds up:
  clock100/deadline102 produces2. Every SDK write <=65536 bytes, buffering <=8MiB.
- Fixed stdlib outer launcher embeds only approved invocations, not a generic
  command CLI. Child pipes drain concurrently. Only actual child wait plus both
  pipe EOFs permits two bounded terminal records. Host requires both witnesses,
  nonce/stream/count/hash/status agreement, iterator ends, SDK wait0 and deadline.
  Quiet V1 iterator termination alone refuses. Framing overhead has a separate cap.
- Strict incremental B decoder enforces exact fields/types, nonbool integers,
  lowercase SHA256, declared body length/hash and caller pins independently.
  Empty put acknowledgements have one terminator. Get/manifest requests include
  their required empty-body terminator. Manifest is output-only and bounded for
  canonical keys, prefix aliases, JSON bytes, members, depth and aggregate.
- All uploads freeze to owner700/600, single-link regular snapshots before SDK
  admission. Anchored nofollow directory FDs, before/opened/final identities,
  bounded reads, complete writes and disk rehash protect the snapshots. Generic
  caller-file/stream puts are removed; puts accept only retained validated
  snapshots. Original source/model/data local paths must also match the original
  serializer's actual `host_path`.
- Exact bytes from existing `_prepare_worker_transport(request)` must equal the
  request upload before bridge import/allocation. Its actual asset rows must
  match the snapshots. This is not a path-independent-binding substitute.
- First RPC compiles/executes the exact approved B source snapshot as fixed
  `__main__`, with no installed train/RPC dependency. Initial cwd is `/`.
  Bootstrap makes only fixed non-output roots and necessary sealed upload
  ancestors. Neither remote output nor host export root is precreated.
  Later native/verifier lookup uses a fixed source-root `runpy` bootstrap;
  V186 adds cwd establishment as described above.
- Public async signature retained. Call-time private loader supplies Modal's
  synchronizer utilities. One no-translation closure, one `.aio()` dispatch.
  Raw resources/lifecycle/tasks/cleanup remain inside the SDK-loop implementation.
  Cross-thread startup ACK and cancellation intent prevent late unadmitted work;
  admitted work receives one cancellation, then joined cleanup through repeated
  caller cancellation. Admission and cleanup joins are bounded.
- Cleanup starts before App open, including ambiguous open, arm/controller,
  constructor and create failures. Unknown GPU end passes the current time to
  owned stop, never a new1800-second interval. Work/verify/export reserves remain
  end-150/end-90/end-30, cleanup uses the actual global end. Create is bounded by
  the work deadline, preserving all later reserves.
- Native mode exclusively latches before unchanged original `_worker_main`.
  Read-only profile observation targets exact original `_run_child.__code__`,
  records actual returned PID and `child.returncode`, refuses profiler conflicts,
  missing/duplicate returns, restores prior profiling on every worker path.
- Verify mode calls the accepted original full verifier once after identity and
  actual-observation checks. Its original DTO carries an explicitly inert
  `IssuedIdentity` projection, not a provider handle or authority. Codes come
  from observations, never fabricated `(0,0)`. Failure writes no success receipt.
  Library/request-validation logs go to stderr. Trusted framed stdout carries
  only the canonical descriptor index for the three fixed evidence files.
- Host GETs those descriptors from evidence, validates the receipt and compares
  an independent B output-only manifest. It streams every receipt-pinned
  checkpoint artifact to exclusive anchored export FDs, then exports evidence
  under `evidence/`. Actual disk rehash, complete writes, retained preallocation
  parent identity and final named/opened identities must agree. No artifact-sized
  response accumulator or host tensor verifier.

## Tests and checks

The prior transport/runner tests existed but were UNRUN and used invalid fakes.
Both assigned test files were rewritten before production changes, following the
named numeric plan. Added cases cover actual mode invocation with controlled
original worker/child/verifier dependencies, actual accepted-B bootstrap,
original request serializer/schema, full fake pipeline/export, separate bridge
loop and raw operations, repeated cancellation, and numeric boundary failures.
They use finite ordinary pytest, stdlib fakes and tiny local source/data fixtures.
The 8MiB manifest boundary is an in-memory control message, not an asset file.

**Executed checks: none.** No Python import, syntax compilation, pytest,
lint/type check, benchmark, subprocess, SDK/provider/network call, Git operation,
delegation, installation, environment/credential access or real asset read.
Only permitted file tools were used. No temporary iteration scripts were created.
Test names/counts are not pass evidence. Parent owns independent review and red
mutation controls, including removal of each critical refusal guard.

## Remaining parent gates

1. Run the tests and syntax/type/lint checks. Controlled tensor leaves in mode
   tests are not native/tensor/scientific verification. Full fake pipeline
   outcomes carry no real-world observations.
2. Couple A and C against actual pinned Modal1.6.3 raw/nonpersistent GPU V1 and
   the shared synchronizer. Exercise delayed startup, repeated cancellation,
   quiet stream timeout, ambiguous create/open and watchdog/controller retention.
   None has genuine SDK runtime evidence here.
3. Measure fresh disk, local preparation read/copy time and admitted resource
   budget for the future actual5.6GB bundle. Code checks fresh free space, records
   snapshot bytes and checks preparation deadlines, but no asset-size run or
   timing/memory/fit measurement was authorized. The unchanged original
   serializer additionally rereads/validates its original asset paths.
   The initial free-space requirement includes snapshots, the original request's
   maximum artifact bytes and three bounded evidence documents; filesystem
   overhead and concurrent disk use still require fresh parent measurement.
4. Validate real <=1800-second fit, phase/tensor verification, complete export
   and owned cleanup. A supplies the independently armed owned-App stop
   controller. Source inspection cannot prove charged termination.
5. Cleanup architecture is BLOCKED pending the parent killable-process spike
   and frozen owner/delegation interface. The existing sealed host cannot be
   pickled/forked. Existing `SDKBridgeIncomplete`/deadline failures and bounded
   waits do not establish remote death or charged end. No custody exception is
   selected, and no live attempt is approved.

Outcome claims remain strictly:
`remote_full_checkpoint_verification=observed`,
`host_export_byte_verification=observed`,
`host_tensor_verification=not_performed`, `strict_certificate=not_issued`.
They describe a genuinely completed real path only, not this source-only run.

VERIFY_REAL: UNRUN. No execution or approval.
