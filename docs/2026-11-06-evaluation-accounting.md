# Evaluation accounting and trace ingestion, 2026-11-06

This branch adds offline accounting to the existing Cotrain instrument. It does
not establish a BIRD baseline, completed training, qualified second backend or
measured harness-swap benefit. Stage4/5 remain partial; stage6 remains blocked.
No activation guard, deliberate training-CLI refusal or evidence format changed.

## Trace ingestion

`ptc.paired.load(path)` and `rollouts(path)` now reject duplicate task names,
duplicate decoded JSON keys, malformed required record shapes, invalid/nonfinite
reward components and arithmetic overflow. `rollouts` requires exact boolean
`ok` when present, with missing still false. `load` remains score-only.
Finite general/negative weighted rewards, default weights, metadata and existing
paired arithmetic are preserved. Malformed input raises a generic `ValueError`;
filesystem errors remain filesystem errors. No input resource caps were added.
A task missing from BOTH arms still requires an independently scheduled plan.

## Holdout identities

`bench.holdout_accounting.account_holdout_membership(training, holdout)` accepts
explicit nonempty tuples of existing `SqlTask` records. It reports original
counts and independent ID/canonical-fingerprint overlaps, with bounded digest
diagnostics and no silent deduplication. `identities_disjoint` concerns only
declared identities. Existing fingerprints include task name and omit db_path:
renamed content can evade this check. It is NOT semantic contamination detection
or evidence that the caller supplied every training exposure. It issues no split
clearance and performs no corpus access, selection or scoring.

## Three declared seeds

`bench.seed_accounting.account_three_seeds(expected_seeds, labelled_results)`
accounts exactly three caller-selected integer labels and existing paired-result
records. Missing and void results remain explicit; duplicate/unexpected labels
and literal result-object reuse refuse. There is no pooled estimate.
`structural_three_seed_complete` projects the supplied result status/comparison,
not independent execution evidence. Distinct copies can still be caller-labelled
as separate seeds. RNG use, seed authenticity, checkpoint identity/restoration,
taskset consistency and scientific validity remain unverified. Measurement and
training/runtime/backend acceptance cannot be granted by this report.

## Harness declarations

`train.harness_swap_accounting.project_harness_swap(planned_task_ids, left, right)`
compares existing episode declarations against the explicit schedule, including
IDs absent from BOTH sides. Duplicate/extra/missing counts remain visible.
It compares declared task, database, prompt, schema, policy/revision, instrument
and reporting invariants, with backend identity intended to differ. It does not
require equal outputs, replay episodes or score anything.
`recorded_declarations_compatible` is NOT backend qualification, checkpoint proof
or measured transfer benefit. Four existing Budget bindings are unrepresented;
an ID-only schedule cannot detect identical bilateral task substitutions.
The qualified second-backend/evidence-authority decisions remain open.

## Verification boundaries

Tests use synthetic data, original record/identity APIs, explicit negative
controls and real local file errors. No experimental model/provider calls,
SDK/Docker activation, training/save/resume or corpus acquisition occurs.
Devin support inference authored changes; parent verified artifacts, reviewed
actual patches and ran narrow offline selections. Exact receipts live in the
parent scratch wave, not invented production manifests or scientific receipts.
