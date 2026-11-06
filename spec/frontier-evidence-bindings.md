# Offline frontier evidence bindings

Status: ACCEPTED FOR OFFLINE STRUCTURAL IMPLEMENTATION ONLY

This is separate from the draft genuine-evidence boundary. It does not accept
genuine measurements, verify attestations, publish manifests, or admit training.
Owner explicitly delegated implementation after the precise offline-validator
and synthetic-fixture-test scope was presented. No experiment grant is created.

## Test plan first

All checks proposed here are UNRUN until parent records actual results.

1. `test_complete_schedule`: 8 planned tasks, 1 excluded, 7 eligible, explicit
   illustrative G4 produce 28 ordered slot dispositions and 0 excluded slots.
   One checkpoint declaration plus generation/scoring evidence for each valid
   sample gives 57 raw-evidence associations. No rates or measurement claim.
2. `test_missing_and_failure_dispositions`: removing one sample leaves 27
   observed slots and 1 missing; removing a whole task leaves 4 missing.
   Generation failure, invalid gold, pending and unknown each remain distinct.
   Failure plus score0 is inconsistent, failure count1, valid-score count0.
3. `test_bindings`: mutate one execution/policy/checkpoint/adapter/runtime/
   generation/instrument/draw/supplement/source binding, payload byte/digest,
   role, task, slot, attempt or prediction-to-score association: no consistency.
4. `test_duplicates`: duplicate planned membership, raw/expected evidence IDs,
   receipt reuse, repeated attempts and multiple sample records per slot refuse
   without selecting a winner. Duplicate keys cannot disappear into dicts.
5. `test_authority`: perfectly matching synthetic input, fabricated expected
   pins, self-derived matching pins and identical replay remain unverified.
   A changed expected execution refuses; identical replay is not detectable
   as stale and must never be called fresh. No authority callback/flag input.
6. `test_exact_types`: bool integers, NaN/infinity, malformed/missing fields,
   subclasses/lookalikes, mappings/iterators/callables and invalid enum/scalar
   values refuse without invoking user methods or leaking input.
7. `test_limits`: each explicit limit boundary B accepted; B+1 refused before
   hashing/expansion, using small limits for product tests. No truncation into
   success. Aggregate metadata/raw budgets enforced before hashing.
8. `test_no_side_effects`: 0 file opens/path resolutions, SQL queries, provider/
   network calls, heavy framework imports, outputs or train/save/resume calls.
   Paths/URLs in otherwise valid opaque IDs remain data and trigger 0 access.
9. `test_immutable_opaque_report`: no raw bytes, SQL, prompts, responses or
   input identifiers in public errors/repr. Errors <=80 characters. Output
   nested collections immutable and unaffected by later input mutation.
10. Intended call-phase RED controls: lose expectation/association/uniqueness/
    coverage/bounds enforcement independently and require the corresponding
    oracle to fail. Promote an otherwise valid report to verified and require
    the provenance oracle to fail. Restore positives. No setup RED counts.

## Selected API

Two new source/test files only: `train/frontier_bindings.py` and
`train/test_frontier_bindings.py`. No existing consumers or constructors change.

`validate_frontier_bindings(plan, expected_evidence, candidate, *, limits)`
returns a frozen `BindingReport`. Inputs are explicitly validated frozen,
slotted dataclasses, exact builtin scalars, bytes and tuples. No arbitrary
mappings, iterators, callbacks, file adapters, JSON parser or crypto protocol.

Expose:
- BindingLimits
- TaskBinding
- PreparationExclusion
- ScorerBinding
- MeasurementPlan
- ExpectedEvidence
- EvidenceBlob
- SampleRecord
- EvidenceBatch
- SlotDisposition
- BindingReport
- BindingError
- validate_frontier_bindings

The worker may select readable field spellings, but must document the exact
public signatures in tests and report. It may not omit any binding below.

## Required record semantics

`TaskBinding`: opaque task ID, task fingerprint SHA256, database SHA256.
`PreparationExclusion`: task ID and opaque exclusion reason.
`ScorerBinding`: extraction/scorer source identities, supported existing
comparison mode, finite positive timeout and positive exact-int max rows.

`MeasurementPlan` binds plan/execution IDs; 40-hex policy source revision;
measured checkpoint inventory SHA256; optional adapter SHA256 (None explicitly
means no adapter); runtime/provider/route IDs; generation/prompt/template/tool/
source SHA256 identities; draw/supplement SHA256; ordered tasks, ordered eligible
IDs, exclusions; exact integer G>=2 and finite ceiling strictly between0and1;
scorer binding; explicit opaque resource-limit and grant-reference declarations.
Declarations are not verified approval. No production defaults.
The implemented declaration includes a separate instrument SHA256. Policy source
revision accepts exactly40ASCIIhex characters, compared literally; SHA256 pins
are canonical lowercase64hex. Timeout/max_rows have the conservative numeric
ceiling 2**63-1; this is not a production scorer-setting authorization.
Tasks are nonempty and unique. Eligible membership is nonempty, preserves
planned order, and together with unique exclusions partitions planned tasks.

`ExpectedEvidence`: evidence ID, purpose (checkpoint/generation/scoring),
plan/execution, optional task/slot/attempt association, optional referenced
generation evidence ID for scoring, exact nonnegative byte count and SHA256.
Exactly one checkpoint declaration is plan/execution-bound, not sample-bound.
Generation/scoring declarations bind exactly to their sample; scoring also
references that sample's generation evidence. Expected pins are supplied
separately but this API cannot establish their independence or custody.
Checkpoint evidence is the opaque inventory artifact for this structural join:
its expected/raw digest must also equal the plan checkpoint-inventory pin. This
does not prove inventory meaning, checkpoint weights or loaded-checkpoint facts.
Expected generation/scoring declarations and sample records additionally bind
an explicit prediction SHA256. Scored/invalid-gold samples require that pin;
generation failures cannot declare a prediction; pending/unknown may retain one.

`EvidenceBlob`: evidence ID and exact opaque bytes.
`EvidenceBatch`: complete plan projection, tuple of blobs and sample records.
The projection must match the fully validated supplied plan. Raw bytes remain
opaque; a correct digest does not prove receipt meaning or normalized claims.

`SampleRecord`: task ID, index within G, nonempty attempt ID, status, optional
declared binary score, optional generation/scoring evidence IDs.
Statuses: scored, generation_failed, invalid_gold, pending, unknown.
Missing sample is absence of a record, not a scored zero.
Scored requires generation+scoring references and exact numeric0or1, excluding
bool. Invalid gold needs generation+invalid-scoring evidence but no score.
Generation failure needs a generation/failure evidence reference, no scoring
reference or score. Pending/unknown may retain available generation evidence,
must have no score, and cannot be treated as terminal success.
Malformed status/score combinations are inconsistent, not zero-filled.

Each attempt and referenced receipt belongs to exactly one slot. Expected IDs,
raw IDs and records cannot be silently deduplicated. Extra/missing raw evidence,
unreferenced expected evidence and wrong associations prevent consistency.

## Processing and error behavior

Perform exact-type, fixed-record-field, scalar, count and aggregate budget
validation before equality, indexing, hashing or slot expansion.
Guard `eligible_count*G` before expansion; bounded integers exclude bool.
Never invoke arbitrary equality methods, descriptors, iterators or callbacks.
Read missing exact-record fields defensively; malformed records must not leak
AttributeError or supplied data. No blanket exception swallowing.

Malformed shape/type, limit violations and duplicate identities raise generic
`BindingError` (ValueError subclass), no input text, <=80 characters, from None.
Semantic mismatches and missing/failed/pending outcomes return an inconsistent
or incomplete report with fixed-code diagnostics. No authoritative winner
exists for duplicate sample/attempt/receipt associations; they may refuse as
BindingError rather than produce a report.

Hash each well-shaped blob once using stdlib hashlib.sha256, after budgets.
Expected byte count and digest bind the candidate bytes, not provenance.
Do not execute scorer, extraction, SQL, selector, provider or corpus loader.
Validate existing comparison-mode spellings from actual source; no new modes.

## Explicit limits, not production settings

Require a supplied `BindingLimits`; no API defaults. Implementation ceilings:
- 1,024 planned tasks.
- 4,096 scheduled slots/sample records.
- 12,289 expected evidence and 12,289 candidate blobs.
- 1 MiB per raw item.
- 16 MiB aggregate raw bytes and UTF8 string payload across supplied inputs.
- 256 UTF8 bytes per opaque identifier.
- 10 diagnostic examples.

Limits must be positive exact integers within ceilings. Count/string/byte
length checks occur before expensive work. Check codepoint length before
bounded UTF8 encoding, refuse invalid Unicode, and charge repeated supplied
strings too. Fixed record nesting needs no generic decoder. No arbitrary
numeric magnitude or caller-selected unlimited limits.

Diagnostic overflow retains total issue counts, a bounded truncation indication
and failing disposition; never turns failure into success. No raw input IDs
in diagnostic examples or report repr; use planned task ordinal/slot indices.

## Output and honest claims

Report planned/eligible/excluded counts, scheduled and observed slot counts,
declared attempts, matched evidence count, valid declared scores, fixed
disposition counts, immutable ordered per-slot dispositions and diagnostics.
Dispositions identify planned ordinal and slot index, not supplied ID strings.
Snapshot only validated scalars; no references to raw input objects.
A declared binary score is not an authenticated scorer result.

Distinguish `bindings_consistent`, `schedule_complete` and
`all_samples_validly_scored`. Pending/failure/invalid/missing are never complete
valid-scored measurements, even when all slot records are present.
Counters describe declarations. Duplicate records are refused before counting
can hide ambiguity. No solve rates, band computation or frontier retention.

Provenance is ALWAYS unverified; attested facts ALWAYS empty.
Genuine-measurement acceptance and training authorization ALWAYS false.
Public result construction must not supply approval flags as evidence.
Fixed reason: external provenance/attestation verification unavailable.
Consistent fabricated expectations and opaque receipts can pass structure;
nothing in this increment authenticates facts, independence or freshness.

## Non-goals and integration

No genuine-evidence verifier, attestation verifier, signing scheme, parser,
file adapter, persistent schema, CLI, provider or native integration.
No current caller is rewired. Existing probe only returns aggregate rates and
must not be used to manufacture per-attempt evidence. A future approved adapter
can use this structural join before separate external provenance verification.
No fixture-only API relaxation, native/genuine/training gate bypass, source/
runtime qualification, retries/redraws, model/corpus acquisition, SDK/Docker,
installs, training/save/resume, publication, or spent profile renewal.
