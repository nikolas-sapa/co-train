# V238 validation implementation, SOURCEONLY

## Tests first (parent executes, author does not)

Preserve the existing 51 accepted C cases, updating only explicitly amended
deadline/read/publication expectations. V235 records those old units passing,
not actual SDK/native/process-reap evidence. All changes below remain UNRUN.
Keep this complete C module below 200 collected cases, no skips/xfails/capraises.

1. `test_public_order`: exactly one registration after seal and before run,
   one final validation, one joined release. Default refusal consumes zero
   admissions/serializations/children/SDK calls.
2. Lease identity tests: each foreign/copied/replayed request, prepared,
   execution, owner, export-root and lease attempt refuses; zero reads before
   the fixed owner's assertion. DTOs and copied grants confer zero authority.
   These are explicitly mocked owner observations, not actual A acceptance.
3. Worker-reap/publication ordering: zero reads without mock clean worker reap;
   validation with only worker proof and live mock guards precedes shutdown;
   publication before all three mock joins refuses. Final publication performs
   zero file opens/reads/stats, hashes, serializers or new lease operations.
4. Async streaming: every read requests 1..65536 bytes, every chunk and entry
   checkpoints, EOF/size/hash exact. Fixed V never moves on early completion;
   equality/slow reads/guard EOF refuse. Three cancellations invalidate mock
   proof and cannot yield a wrapper; existing repeated joined-cleanup test stays.
5. Existing closed-schema/receipt/observation/evidence/bulk mutations remain
   rejecting. Add permission, link, directory, missing/extra inventory and
   identity mutations. Evidence refusal causes zero bulk export opens.
6. Regression: mutate or replace an already closed earlier export while a
   later export is read. Exactly the final all-files identity sweep refuses,
   using retained named pins, never fstat on its closed data FD.
7. Regression: worker file/directory/export acquisition is registered before
   its first post-open validation. Inject validation failure AND failed close:
   retained actual FD, anchor, primary and close exceptions; exactly one close
   attempt, no blind retry on exit or FD-number reuse.
8. Worker timing: helper-derived S, unchanged S-150/S-90/S-30 reserves, actual E
   unchanged, export no later than B. Check maximum T=20.5 and synthetic E;
   preserve native/verifier exactly once, original argv/cwd/runtime and freshness.

## Implementation

- Keep the one pre-admission `_require_parent_read_custody()` call in
  `run_engineering_isolated_once` as the integration review gate.
- After input sealing, call the frozen `register_parent_validation` once.
  Await `run_once`, publish through `take_validated_original`, then release.
- Implement fixed `_make_parent_validator(owner, request, prepared, export_root)`,
  private async validator, and frozen seven-field `_ValidatedParentData`.
  Assert fixed registration links before reads, after the final identity sweep,
  and before returning. A owns lease construction, actual proof and invalidation.
- Replace disconnected raw-FD validation with async lease-only reads and fixed
  absolute timeout. Validate exact outcome, original evidence and receipt before
  bulk hashes; compare files and ancestor directories; recheck all closed readers
  after all hashes. Return original outcome only, never a successful wrapper.
- Override unsafe worker anchor child/file acquisition and export sink
  construction with pre-reserved local acquisition records. Keep original
  snapshot type, sink behavior, full disk hashes and native pipeline.
- Use readonly `validation_booking(E, T).phase_end_ns` for worker reserves.
  Do not change helper/shared DTOs, actual E, A lifecycle or B limits.

`ExportEntry`'s prose “relativekey/kind/size” is read as `key` (relative export
key), `kind`, `size`, consistent with the existing manifest vocabulary. Parent
must confirm this spelling with A before removing the refusal; no alternate
attribute probing or fallback will be added.

## Non-goals and limits

No A/shared/helper/original-module edits or other worktree reads. No execution,
imports, compilation, tests, commands, Git, network, delegation, SDK/config,
credentials, interpreter/assets/stager reads or hashes. Parent executes/reviews.
No old unsafe runner fallback, provider/GPU/build/upload/install or science.
Three scoped interpreter reads consumed, zero remain. $30 actual gross maximum
($25 plan + $5 reserve), separately bounded preparation, one attempt <=1800s
including upload/install/native/verify/export/cleanup, no retry/replacement.
Native/science 0/7. No Alliance/Orca or production acceptance claims.
