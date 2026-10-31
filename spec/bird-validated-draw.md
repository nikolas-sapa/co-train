# Validated BIRD draw consumer

Status: implemented in `bench.prepare.load_validated_draw`, fixture-verified.
The binding reference remains a separate, non-production composition spike.

## Test plan, before implementation

Use synthetic fixture corpora only. Reuse preparation fixtures and real
freeze/validate publication. Test corruption may recompute independently
retained fixture digests to reach deeper checks; never repin historical or
real-corpus evidence.

1. **Ordered partition:** 8 planned tasks, 1 invalid gold, exactly 7 eligible
   tasks and 1 ordered exclusion. Returned planned denominator stays 8.
   No selection, redraw or replacement occurs.
2. **Digest admission:** independently alter each document and each expected
   digest. All 4 cases refuse before JSON parsing, corpus load or SQL.
   A bad supplement digest must refuse even when the draw JSON is malformed.
3. **Shape and relationship:** reject missing/extra keys, wrong exact types,
   duplicate/unknown IDs, reordered IDs, overlapping or incomplete partition,
   unknown exclusion status/category, wrong counts/shapes/settings, wrong
   draw relationship and false identity acknowledgement. Each named mutation
   gets its own refusal assertion, not one broad exception test.
4. **Readiness:** underfilled draws, blocked supplements, unusable or empty
   supplements, and either fixture flag mismatch produce 0 returned tasks.
5. **Current identity:** independently drift manifest, universe/task contents,
   selected database bytes, sidecars, source or runtime identity. Each refuses
   before any selection or SQL. Recheck identity after resolution and reject
   drift between the two checks.
6. **Read-only consumption:** two successful loads produce equal frozen
   results, 0 SQL/gold-validation/selection calls and 0 published files.
   Input documents remain byte-identical.
7. **Bounded input:** each document above 16 MiB refuses before parsing/corpus
   access; malformed JSON and duplicate object keys refuse.
8. **Actual guard control:** bypass retained-digest comparison in memory.
   A targeted digest-admission test must turn RED, then GREEN after restoration.
9. Existing preparation tests pass without changing published schema or
   existing freeze/validate defaults.

## Reference implementation

`spec/spikes/reference/bird-sdk-binding/bird_sdk_probe.py` proves the downstream
SDK Task/channel/scorer/writer composition with synthetic data. It does **not**
prove artifact admission. The preparation module already owns frozen draw
identity, planned-ID resolution and gold-validation supplement publication.
This increment fills only its missing read-only consumer API.

## Public API

Add to `bench.prepare`:

```python
load_validated_draw(
    root, draw_path, supplement_path, *,
    expected_draw_sha256, expected_supplement_sha256, fixture=False,
) -> ValidatedDraw
```

`ValidatedDraw` is a frozen dataclass with:

- `planned: tuple[SqlTask, ...]`, original planned order, including exclusions.
- `eligible: tuple[SqlTask, ...]`, planned order with exclusions removed.
- `exclusions: tuple[DrawExclusion, ...]`, planned order.
- `draw_sha256`, `supplement_sha256`, `fixture`, `timeout_s`, `max_rows`,
  `comparison`.
- `databases: tuple[DrawDatabase, ...]`, added by the
  [admitted DB-record projection](bird-validated-draw-databases.md). These
  frozen records preserve all admitted planned DB identities in order,
  including excluded-only DBs, with `db_id`, `sha256`, `size_bytes`.

`DrawExclusion` is frozen with `id`, `status`, `category`. No mutable document
dicts, raw query errors, gold result rows or host paths are added to receipts.
Host-side SqlTask values retain their existing fields, including oracle SQL.

## Implementation plan

1. Implement alongside existing preparation helpers. Reuse identity and
   planned-resolution logic; do not duplicate corpus loading or selection.
2. Validate exact digest and fixture argument types. Read at most 16 MiB plus
   one byte per document. Check **both independently retained byte digests
   before parsing either document or touching the corpus**.
3. Strictly parse documents, reject duplicate keys, enforce existing draw
   schema and an exact supplement schema matching `validate_draw` output.
   Preserve canonical draw-byte checks and require canonical supplement bytes.
   Require frozen draw, complete/usable supplement, zero exact-int model
   calls, matching exact-bool fixture flags and explicit fixture opt-in.
   The draw itself remains `usable=False`. Unready inputs raise
   `PreparationError`, rather than returning an empty successful result.
4. Verify supplement references the retained draw, preserves planned order,
   and partitions it exhaustively and disjointly. Validate exclusion mappings,
   settings, per-tier counts and shape counts against resolved original tasks.
5. Snapshot code/runtime identity, load the corpus, resolve only planned IDs,
   validate counts and current full identity with existing sidecar/database
   checks. Repeat current identity verification before returning.
   Do not run SQL, `validate_golds`, `select`, or publication helpers.
6. Return immutable host-side values. Refusals use `PreparationError` with
   bounded messages. Do not expose raw artifact bodies or database errors.

Architecture review approved this ownership/API plan. The second identity
pass must freshly reload manifest/universe/task values, not merely rehash the
first loaded objects. Updating `prepare.py` intentionally changes its source
identity; do not repin existing evidence to compensate.

## Non-goals and authorization boundary

No SDK plugin, paired runner, CLI, model/client/checkpoint/tokenizer choice,
policy authentication, training adapter, estimator, frontier gate change,
historical replay, corpus inspection or real draw. No retry/backfill/rescoring.
No claim that hashing provides adversarial database immutability.

## Verification

297 affected tests passed in 11.88s: 92 consumer-contract cases, 7
consumer-admission cases, 101 existing preparation cases and 97 adjacent
benchmark cases. This is not the full suite. The retained-digest bypass
produced one intended assertion failure; bypassing consumer error normalization
produced five intended failures and two deep-input refusals that still passed.
Restored tests passed. See `docs/2026-10-31-bird-validated-draw.md`.

Later baseline work must separately prove per-episode ownership, task-local
SQL isolation, shared enforced budgets, single final-response scoring,
valid-zero versus void classification, complete scheduled pair coverage and
PTC-minus-Bash statistics. Real baseline execution requires separately
authorized policy, corpus/draw and explicit execution/spending ceilings.
