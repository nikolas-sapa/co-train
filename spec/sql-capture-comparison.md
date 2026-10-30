# Offline caller-capture comparison

## Test plan (frozen before implementation)

1. Six pairs made with real fixture SQLite and existing capture/scoring:
   two both solved, one treatment only, two baseline only, one both unsolved.
   Require baseline 4/6, treatment 3/6, treatment-minus-baseline -1/6,
   exactly two named regressions and one named improvement. Compare every
   statistic against the real `ptc.paired.paired(treatment, baseline)` export.
2. Independently supply six planned IDs. Remove one arm, then both arms of
   one case: retain six rows and denominator six; no statistics, CI or p-value.
   Duplicate/empty planned IDs, undeclared mapping keys and cross-case reuse
   of a path or canonical capture bytes must refuse. Zero inferred intersections.
3. Independently alter task ID, task fingerprint, database digest, schema,
   prompt, backend, instrument, capture version and execution binding.
   Each must refuse aggregate statistics and name the mismatching field.
4. Valid EX=0 stays observed failure. Missing/invalid captures, invalid gold,
   missing database, caller abort, native program rejection and typed
   infrastructure abort stay distinguishable, unscored where appropriate.
   All planned rows remain; zero admissible aggregates for incomplete evidence.
5. At least one non-mocked call to the existing paired implementation; no new
   estimator. A delegating spy checks exact complete score maps and orientation.
6. Every formatted report, including refusals, explicitly says billing, token
   usage, model-request latency and approved-reuse attribution are unavailable.
   No savings, break-even or production-readiness fields or claims.
7. Put canaries in question/prompt, schema, SQL, observations, grader detail and
   paths: require zero leaks in formatted reports or input-error messages.
   Escape caller case IDs against terminal/control injection. Move fixture DBs
   away before comparison; forbid DB opens, execution/rescore, network,
   credential reads and writes during comparison: zero forbidden accesses.
   Exercise canonical-byte, corruption, 8 MiB, symlink and hardlink guards.
8. Baseline green, then two independent fresh-module in-memory mutants:
   planned-denominator admission and task-fingerprint equality. Each must
   trigger at least one intended assertion failure, not an import/setup/source
   pin failure. Restore originals and require green again.
9. Run focused new/old capture, skill SDK/workflow/demo and paired regressions:
   zero new skips/exclusions; preserve all existing test IDs. Parent runs the
   complete suite independently.
10. Security-review correction: independently block each arm's bounded reader
    with `PermissionError` and an OS I/O error containing canary messages/paths.
    Both tests must first fail on misclassification, then require
    `capture_read_blocked`, six planned rows/denominator, absent aggregate
    statistics and zero rendered canaries. Programmer errors must propagate.

## Contract

```python
compare_capture_files(
    planned_case_ids: tuple[str, ...],
    baseline_paths: Mapping[str, Path],
    treatment_paths: Mapping[str, Path],
) -> CaptureComparison
format_comparison(comparison: CaptureComparison) -> str
```

Nonempty tuple of distinct, nonempty UTF-8 IDs, at most 256 bytes each.
Mappings are independently supplied arm declarations. Only planned keys are
allowed; an absent key is a missing capture. Values are explicit absolute
`Path`s accepted by the existing bounded safe-file reader (outside checkout,
no symlink components, single-link regular files, at most 8 MiB). Invalid
argument structure raises fixed `ValueError` text without input values or
exception chaining. Never discover paths, infer plans, read source DBs, rescore
or execute anything. Capture decode/encode must round-trip exact canonical
bytes using existing codecs.

Return frozen typed in-memory records only:

- `CaptureOutcome`: fixed state, optional valid binary score, scorer status,
  budget-refusal count and optional typed abort stage/reason. No raw errors,
  SQL, questions, observations, metadata paths or capture objects.
- `CaseComparison`: caller ID, both outcomes, fixed refusal-reason codes and
  change (`improvement`, `regression`, `tie`, `unavailable`).
- `CaptureComparison`: planned denominator, every planned row in supplied
  order, completeness, admissibility, refusal reasons, named improvements and
  regressions, optional `PairedStatistics`.
- `PairedStatistics`: n, baseline/treatment successes and accuracy, paired
  treatment-minus-baseline delta/CI/p, treatment-only/baseline-only and ties,
  copied from the existing paired export, not re-estimated.

`complete` means both arms of every planned row have valid observed scores.
`admissible` additionally requires exact within-pair equality of task ID,
task fingerprint, DB digest, schema, prompt, backend, entire instrument,
capture schema version and execution binding. Equality compares recorded
data only, not current installed sources. V1's absent execution binding is
comparable only to another absent binding. Source/settings mismatches are not
model benefit. No cross-case uniformity requirement or causal inference.

Cross-case reuse is inadmissible by equal paths or equal canonical bytes,
including byte-identical copies. Same-case sharing is allowed, not evidence
of independent trials. Caller IDs need not equal captured task/episode IDs;
the caller owns that mapping. Missing or malformed files become safe outcome
states and retain rows. All aggregate statistics are absent unless every
planned row is valid, compatible and non-reused. Individually compatible valid
rows may still identify changes when the aggregate is refused.

File outcomes remain distinct: absent mapping keys or reader
`FileNotFoundError` are `missing_capture`; other bounded-reader `OSError`s
(including `PermissionError` and I/O failures) are `capture_read_blocked`,
not a claim about file contents. Unsafe-file admission, malformed content or
noncanonical bytes remain `invalid_capture`. Blocked reads retain the planned
row, are unscored, and withhold all aggregate statistics. Neither local paths
nor exception text enter the outcome or formatter. OS-error handling is scoped
to the bounded reader, not arbitrary decoder/programmer failures.

`ExResult.valid=False` with `db_missing` is `database_missing`; other invalid
statuses are `invalid_gold`. These names report the recorded scorer signals,
not a fresh diagnosis. `execution_aborted` requires the existing typed abort;
`program_rejected` is separate. V1 `aborted` only means `unscored_abort`,
never guessed infrastructure/model failure. Budget refusals are counted
separately and do not invalidate an otherwise valid submitted final.

The formatter renders only this safe projection and escaped case IDs (JSON
ASCII quoting, bounded input). Case IDs are caller-owned and must themselves
exclude secrets/PII. No raw capture text or local paths are output. Reasons and
statuses originate from fixed closed codes. Format only genuine returned
records, not manually constructed or adversarially mutated projections.

## Limits and non-goals

Caller mappings, self-digests and equal bindings are not authenticated
provenance, model authorship, independent sampling, verified installed-code
attestation or approved-reuse invocation evidence. This adapter cannot verify
those claims. Trusted caller-owned files/ancestors must not be concurrently
replaced; inherited safe-read helpers are not filesystem snapshot isolation.
Bounds are per file, not a whole-batch resource deadline.

Billing, token usage, model-request latency and approved-reuse attribution
are unavailable in generic captures. No financial claims, production-readiness
claims, provider callbacks, persisted schema/envelope, CLI, artifact writes,
registry, dependencies, storage naming convention, execution wrapper or new
statistical method. Native trial authorization, financial gates, runtime,
capture codecs, source bindings and existing estimator remain unchanged.
