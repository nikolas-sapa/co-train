# V226 C tests first

SOURCEONLY UNRUN. Frozen receipt is FROZEN, interfaces only, 269 parent pure
checks, two guard-loss RED controls. No production or paid clearance.

## Test plan, before implementation

All new tests belong in `train/test_qualification_isolated_run.py`. Tests are
source-only for parent review/execution. Mocks are explicitly not SDK, native,
provider, authorization or actual process-reap evidence.

1. `test_public_invalid_and_missing_custody`: invalid/default inputs cause zero
   serializer, admission, SDK and child calls. Valid metadata still fails before
   admission while frozen parent read-custody interface is missing.
2. `test_public_order` and `test_public_failure_custody`: mock preflight/admit/pin/
   original serializer/writer/seal/run/validate/release ordering, each exactly
   once. Content failure consumes one mock admission, starts zero children.
   Unknown release retains owner and primary/cleanup errors, never retries.
3. `test_prepare_exact_coverage`: source/model/data exact original tuples and
   host paths, wheels passed to actual owner writer, exact setup argv. Extra,
   missing, duplicate, changed size/hash/path and caller request-root rows each
   refuse. Derived request is exactly one additional row, not approval root five.
4. `test_original_serializer_delegation`: exactly one unchanged original
   `_prepare_worker_transport` call after mock admission; no request projection.
   Original serializer remains asset-reading and is NOT run on real assets.
5. `test_manifest_limits`: wheel key 1024 accepted, 1025 rejected; native key 256
   accepted, 257 rejected. Maximum 4096 approved plus one request; aggregate
   8 GiB includes request; each asset <=2 GiB, request <=1 MiB. Raw manifest
   8388609 refuses before parsing; no claim exact 8 MiB is production-valid.
   Independent frozen witnesses remain 5014235 without mandatory RPC (reject),
   5013242 with RPC (metadata accept), conservative upper bound 5026024.
6. `test_snapshot_custody`: new-owned tiny files, readonly inherited-style FDs,
   no original host-path reads. Changed bytes, same-content different inode,
   writable FD and symlink/hardlink refuse; named/open identity checked before
   and after hashing and during transport reads. Original `_Snapshot` exact
   type is used because existing RPC checks it, not an alternate transport.
   Stream original snapshots one at a time, at most one member FD open even
   at 4097 rows. Source RPC and derived request are read through that same
   readonly/hash/identity path before staging. Lazy staging closes the current
   member on exceptions/cancellation as well as on ordinary iteration.
7. `test_worker_pipeline`: mock transport only, original fixed native and full
   verify argv each once, original order stage/setup/materialize/native/verify/
   evidence/output/export. Deadlines E-150/E-90/E-30, never renewed. No lifecycle
   calls or stdout-text completion shortcuts. Original native/full verifier
   functions and science checks remain untouched.
8. `test_worker_mutations`: native failure, receipt identity/hash, observation
   phase/order, changed current manifest and changed export bytes all refuse.
   Each mutation must make its positive test RED; parent executes these controls.
9. `test_outcome_fd_validation`: real new-owned mutable outcome FD, canonical
   closed schema <=8388608, actual streamed hash/size and independent identity.
   No bool-as-int, unknown fields, arbitrary classes or authority deserialization.
   Exact receipt/latch/observations and all exported hashes validated beneath
   borrowed export-parent FD. Worker-reap prerequisite, all three joins needed
   for normal wrapper; remote termination and charged end remain UNKNOWN.
10. `test_repeated_cancellation`: three cancellations while mock `run_once`
    owns custody; no detached cleanup and no release before its completion.
    Unknown close/reap retains latch/resources in owner-bearing failure.
11. Source guards: no SDK imports in parent; worker delegates raw await to
    existing `ModalExecTransport`. Genuine fresh synchronizer-loop constructor
    is accepted `local-sdk-ready` reference, not rerun. No alternative pipeline,
    wrapper `_dispatch_sdk`/`_stop_once`, App reconstruction or renewed window.

## Interface blocker, found before implementation

Frozen `PreparationWriter` exposes only `snapshot_member`, `write_request`,
`seal`. `PreparedInputs` contains sizes/digests/entries only. `JoinedExecution`
contains observations/IDs/outcome size+digest, no FD. `IsolatedOwner` exposes no
borrowed parent output/export-reader API. `validate_joined_outcome(request, *,
prepared, execution, export_root)` therefore cannot reach owner-held outcome
or export-parent descriptors without inventing an A API, leaking authority into
DTOs, or reopening user paths. All three are forbidden.
The parent validator also receives no committed E, although the worker host
does. The missing owner read-custody interface must retain ancestor/resource
identities, register validator-opened FDs and supply an E-clamped validation
deadline. Unknown validator closes must prevent owner/latch release too.

Implement FD-based internal validation independently, but public orchestration
must refuse before admission on this known missing interface. No speculative A
attribute, registration bypass, path fallback, success stub or bool approval.
Parent must amend/freeze an owner-held read-custody interface and its lifetime
before production integration. This is not solved by caller normalization.

## Implementation plan

1. Add SDK-free C parent module with exact original serializer delegation,
   metadata/coverage preparation through owner writer, intended orchestration,
   owner-bearing errors, and explicit pre-admission interface gate.
2. Add fixed worker program: borrowed anchors, readonly snapshot validation,
   original transport/execution-body sequence and original evidence validators,
   anchored exports, bounded closed outcome wire and post-reap FD validator.
3. Add new tests with explicit mock boundaries and owned filesystem fixtures.
4. File-tool-only source inspection. No import/compile/test/command execution.
   Record exact gaps and checks NOT run in report.

## Non-goals

No existing file changes, A implementation/read of concurrent A work, shared
contract edits, SDK/vendor/config/assets/binaries/model/data/credentials reads,
original stager/interpreter hash reruns, execution/delegation/Git/network/provider,
build/install/upload/GPU or paid operations. No retries/replacements/science.
One intended attempt, <=1800 seconds including admission/preparation, original
$25 plan plus $5 reserve, $30 actual gross maximum, separately bounded
preparation. Native/science remain 0/7. Parent owns review/execution/integration.
