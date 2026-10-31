# Read-only validated draw consumption

`bench.prepare.load_validated_draw` consumes a frozen preparation draw and its
gold-validation supplement. It does not draw tasks, run SQL, validate golds,
publish artifacts or execute a baseline.

## API

```python
from bench.prepare import load_validated_draw

# Synthetic fixture example. Retain these digests when publishing, separately
# from the documents. Do not recompute them from input files during admission.
suite = load_validated_draw(
    fixture_root, draw_path, supplement_path,
    expected_draw_sha256=retained_draw_sha256,
    expected_supplement_sha256=retained_supplement_sha256,
    fixture=True,
)
```

`ValidatedDraw` and `DrawExclusion` are public frozen dataclasses.
`suite.planned` preserves every originally scheduled task, including excluded
tasks; `suite.eligible` and `suite.exclusions` preserve their planned order.
The results contain tuples rather than mutable document dictionaries, both
retained digests, fixture flag and validation timeout/row/comparison settings.
SqlTask values stay host-side and retain their original gold SQL.

## Admission

- Each document is limited to 16 MiB, with one extra byte read to detect overflow.
- Both independently retained byte digests must pass before parsing either
  document or accessing the corpus.
- Strict canonical JSON rejects duplicate keys, non-finite values, unexpected
  schema keys and wrong exact types.
- The draw must be frozen; its `usable` remains false. The supplement must
  reference that exact draw and be complete, usable and nonempty.
- Fixture flags must match both documents and the exact-bool caller argument.
  Synthetic artifacts require explicit `fixture=True`.
- Planned IDs, ordered exhaustive/disjoint eligibility and exclusions, bounded
  exclusion categories, settings, tier counts and shape counts must agree.
- Two fresh identity passes reload manifest/universe/tasks, resolve planned
  IDs without selection and verify source/runtime/database identities and
  sidecars. The consumer never reruns gold SQL.
- Recursive JSON/numeric overflow and filesystem drift receive neutral,
  unchained `PreparationError` at the consumer boundary. Existing publisher
  error behavior is unchanged.

Changing preparation source intentionally invalidates older source identities.
Do not repin historical evidence to make it pass. Hashes describe quiescent
identity, not adversarial database immutability.

## Verification and limits

Final affected run: **297 passed in 11.88s**, comprising:

- 92 consumer-contract tests, including the 8 planned / 7 eligible / 1 exclusion
  fixture and isolated cross-document relationship checks.
- 7 admission/error-boundary tests.
- 101 existing preparation and 97 adjacent benchmark tests.

This is not the full repository suite.

Two actual in-memory controls ran in isolated Python children:

1. Substitute the retained supplement digest comparison result: 1 callback
   hit, intended assertion RED. The malformed draw then reached parsing, which
   must not happen before the bad supplement digest is rejected.
2. Bypass consumer error normalization: 7 calls, 5 intended RED cases
   (two injected parser recursion failures, a real oversized timeout integer,
   and filesystem failures in each identity pass), 2 real deep-input refusals
   still GREEN. Restored code passes.

Final controls left all three product/test source files unchanged. The
8 targeted restored cases passed in 0.32s separately, not 8 additional unique
tests. Python and security reviews approved the bounded implementation.

Initial depth-2000 tests assumed a decoder recursion threshold that this
CPython runtime did not exhibit. Those diagnostic failures are retained.
Final tests separate real deep-input refusal from deterministic injected
recursion-boundary checks; no measured depth threshold is claimed.

Both implementation workers used SWE-2 High; their exports confirm file-tool
invocations and separate product/test file ownership. Parent added review
regressions and isolated relationship cases, ran checks and owns publication.
Evidence is under `~/scratch/co-train-2026-10-31/bird-validated-draw-085f841/`.
Contract: [`spec/bird-validated-draw.md`](../spec/bird-validated-draw.md).

No corpus inspection, real draw, model baseline, training, frontier manifest,
new estimator or gate change. A production paired SDK runner, shared enforced
budgets and authorized measurements remain missing. Research stays
**4 PARTIAL / 5 PARTIAL / 6 BLOCKED**; current paired BIRD baseline is
**missing, not zero**.
