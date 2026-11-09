# V238 C validation delivery

**SOURCEONLY UNRUN new source. Public entry BLOCKED, not production acceptance.**

Genuine GPT C author. Tests-first V238 plan preceded source edits. Only these
five paths changed:

- `train/qualification_isolated_run.py`
- `train/qualification_isolated_program.py`
- `train/test_qualification_isolated_run.py`
- `docs/gpt-v238-validation-plan.md`
- `docs/gpt-v238-validation-report.md`

V237 freeze/helper, shared DTOs, original modules, A and historical V226
documents/receipts remain readonly. No other worktree or A source was read.

## Implemented fixed interfaces

- `_make_parent_validator(owner, request, prepared, export_root)` returns the
  private frozen `_ParentValidator`, whose `async validate(lease)` checks the
  fixed owner's `_assert_parent_read_lease(lease, *, request, prepared,
  export_root)` before reading, after the final identity sweep, and before return.
- `_ValidatedParentData` has exactly seven frozen fields: `owner`, `request`,
  `prepared`, `export_root`, `lease`, `worker_execution`, `original`. It retains
  exact object links and the original engineering outcome, not a shared wrapper.
  It and the validator prohibit ordinary copy/deepcopy/pickle. A must verify
  exact returned type/links and its own generation; these objects mint no grant.
- Public orchestration, behind the existing refusal, seals inputs, calls
  `owner.register_parent_validation(request=..., prepared=..., export_root=...)`
  once, awaits `owner.run_once()`, calls final validation, then joined release.
- `validate_joined_outcome(request, *, owner, prepared, execution, export_root)`
  is the sole public signature amendment. It checks three joined observations,
  calls `owner.take_validated_original(...)` once, and constructs the shared
  wrapper. It performs no filesystem, hash, serializer or lease operation.
  Remote termination and charged end remain `UNKNOWN`.

**Exact refusal removal point:** `train/qualification_isolated_run.py:314`,
the `_require_parent_read_custody()` call in `run_engineering_isolated_once`,
after `preflight_isolated` and immediately before `admit_isolated_owner`.
Parent alone may remove that call after amended A/C integration review. There
is no flag, caller approval boolean, speculative attribute fallback, or old
runner route. The lazy owner import still requires parent integration.

## Leased validation and custody

Removed the disconnected `_validate_outcome_fds`, raw-FD export reader and
parent directory walker. The C-internal async `_validate_outcome_lease` is called
only by the fixed validator after the owner's assertion. It uses only the
frozen lease/reader methods. No parent pathname opens or raw FD access remain.

Prerequisite is the exact owner-created worker-only execution with observed
clean worker reap, while A's independent controller/gate remain armed. A alone
constructs the lease, acquires/registers actual resources, checks generations,
invalidates proof, observes closes, seals by P, shuts down and joins all three.
C cannot publish the shared successful wrapper during leased validation.

Reads request 1..65536 bytes, checkpoint before/after operations and chunks,
hash every byte and verify EOF/size. One absolute, conservatively rounded V
timeout surrounds validation in the same task. E/V/proof identity are captured
once and checked for changes, with no renewed timeout or detached task/thread.
Expiry/cancellation still attempts each acquired data-reader close once.
Failed close retains lease, reader, primary and cleanup errors; C forbids owner
release on unresolved custody. A remains responsible for actual close records.

Closed canonical outcome/schema checks, exact request/attempt/App/Sandbox,
evidence descriptors, latch, observations, receipt, output/evidence coverage,
artifact caps and full export hashes remain. The unchanged original bounded
receipt/observation metadata validator is bracketed by checkpoints; it is not
rerun serialization or native verification. Evidence validation precedes every
bulk export open. C checks exact inventory files, sizes and ancestor directories,
no extras. Original 20000 output entries plus three evidence files and their
directory gives the unchanged 20004 local entry cap, also enforced while deriving
expected directories to bound metadata growth.

After all hashes and the final inventory, C calls `check_identity()` for EVERY
verified reader, including outcome/evidence and already closed earlier exports.
A must implement these checks through retained named pins/intermediate anchors,
not fstat on closed/recycled FD numbers. Top-level anchors remain A-owned.

Worker acquisition no longer calls unsafe original `_open_regular` or inherited
open-then-register directory/sink constructors. `_LocalFD` records are reserved
in the actual local owner before `os.open`; the returned actual FD is stored
immediately, before fstat/validation/exposure/await. Safe overrides cover snapshot
members, intermediate/export directories and export sinks. Ambiguous closes
retain actual record/owner/anchor and both failures, and never retry that
generation, including after its numeric descriptor has been reused.

Worker deadlines now use
`validation_booking(host.end_ns, launch.timing.teardown_ns).phase_end_ns` as S,
then unchanged original S-150/S-90/S-30 reserves. Actual E remains unchanged,
export ends by B, and actual allowance still cannot exceed 1800 seconds.
Original T+9.5<=30 shutdown, setup/materialization, one native invocation, one
full verifier, output freshness, argv/cwd/runtime capsule, full disk hashes,
original snapshot type and B seven-root limits remain unchanged.

## Tests and evidence

Existing evidence: parent V235 accepts V234's **51 old C unit cases**, zero
failures/errors/skips, stable pins/all eight origins, full wall 1.82 seconds.
Those were explicit mocks/new-owned files, not actual SDK/native/reap proof.
V230/V232 failure receipts were not overwritten. V237's helper acceptance is
booking arithmetic only, not validation throughput or runtime lease proof.

This delivery preserves those cases and assertions, changing only amended
registration/deadline/read/publication expectations. New source adds bridge
identity/foreign/copy/replay refusals, registration once, worker-before-read and
all-three-before-publication ordering, zero-I/O publication tripwires, bounded
reads/checkpoints, fixed deadline/slow read/guard loss, three cancellation
locations, permissions/links/inventory corruption, evidence-before-bulk refusal,
all-reader final sweep, and maximum-T independent deadline arithmetic.

Specific regressions cover an earlier closed export changed or same-byte
replaced DURING a later export read, and post-open validation failure plus failed
close for snapshot/directory/export acquisitions. A further close-then-error
mock reuses the descriptor number and confirms C never retries that generation.
Synthetic metadata tests cover exactly 20004 entries and the 20005 refusal.
Source inventory predicts **103 total cases (51 retained + 52 added)**, below
200; this is not an executed collection count. Parent must count independently.
No skips, xfails or raised execution caps were added.

All new lifecycle/lease/SDK/native observations are explicitly mocked. Local
bytes/permissions/identities in authored tests use only newly owned tiny files;
larger boundaries use synthetic metadata, not real assets. Mock-owner identity
tests exercise C's fixed bridge calls, NOT actual A authorization/generation
acceptance. Actual A foreign/copy/replay/reap/close/three-cancellation integration
gates remain required and cannot be replaced with these mocks.

**Author executed zero checks:** no imports, compile, lint, collection, tests,
commands, subprocesses, Git, network, provider, delegation or source execution.
Only allowed file reads/searches/patches were used. No installed interpreter,
stager, SDK source, credentials, config, locks, binaries, assets, models, data or
wheels were read/hashed. No temporary iteration scripts or helper files exist.

## Remaining blockers and limits

1. Parent review/integration of A's actual lease/registry/generation/reap/guard/
   close/seal/shutdown implementation and this C bridge, followed by independent
   source review and authorized bounded execution. No actual process reaps,
   fallback liveness, native verification or throughput were established here.
2. The frozen prose describes `ExportEntry` as “relativekey/kind/size”, without
   a Python declaration. C interprets this as `key` (relative export key),
   `kind`, `size`. Parent must confirm the spelling with A before removing the
   refusal. No alternate-name probing or shared-module change was introduced.
3. Fixed deadlines fail closed; 30 seconds is not a throughput promise.
   Unresponsive individual OS syscalls remain UNKNOWN, with no universal hard
   return/billing guarantee or same-UID adversarial filesystem atomicity claim.

No A/shared edits, fallback runner, paid/provider/GPU/build/upload/install,
assets/interpreter/stager actions, science, commits or pushes. Three scoped
interpreter reads consumed, zero remain. $30 actual gross max ($25 plan + $5
reserve), separately bounded preparation, one attempt <=1800s including
upload/install/native/verify/export/cleanup, no retry/replacement. Native/science
0/7. No Alliance/Orca claims.

VERIFY_REAL: New V238 source SOURCEONLY UNRUN. Earlier 51 mocked units accepted
by parent V235. Public route remains blocked; no production approval.
