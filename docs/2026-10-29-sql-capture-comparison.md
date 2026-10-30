# Read-only SQL capture comparison, 2026-10-29

[Source](../train/sql_capture_comparison.py),
[tests](../train/test_sql_capture_comparison.py),
[contract](../spec/sql-capture-comparison.md) and
[usage](../train/README.md#offline-comparison-of-caller-owned-captures).
This adds analysis of caller-owned saved captures alongside the
[file SDK](2026-10-29-sql-skill-workflow.md) and
[offline demo](2026-10-29-sql-reuse-demo.md), without changing their receipts.

## Usage and boundary

Existing README fragment, with independently planned IDs and caller-owned
absolute capture paths already supplied:

```python
from train.sql_capture_comparison import compare_capture_files, format_comparison

comparison = compare_capture_files(planned_case_ids, baseline_paths, treatment_paths)
print(format_comparison(comparison))
```

Canonical bounded safe-file reads return typed in-memory results. Analysis opens
no DBs and performs no fresh execution, scoring, writes or network requests.
Every planned row remains, including missing captures in both arms. Missing
files, malformed/unsafe content, `capture_read_blocked`, invalid gold, recorded
missing databases and infrastructure aborts remain distinguishable.
Incomplete coverage, incompatible recorded bindings or cross-case capture reuse
withhold aggregate statistics. Complete admissible evidence delegates to the
unchanged `ptc.paired.paired(treatment, baseline)` estimator.

Caller mappings declare arms, not authenticated provenance, model authorship
or approved-reuse attribution. Equal recorded bindings are not installed-code
attestation. Inputs/ancestors must be trusted against concurrent replacement.
The formatter omits SQL, questions, schema, observations, grader detail and
paths; caller case IDs must themselves contain no secrets/PII.
Billing, token usage, model-request latency and proof of approved reuse are
explicitly unavailable in generic captures.

## Final corrected-byte verification

Baseline HEAD: `db48830bb64770532d39e6a4eff6d59f79695c7a`.
All 254 bound source files remained unchanged during validation; 20 protected/
owner files matched HEAD, including estimator, evaluator, runtime, budget and
scorer owners.

| Check | Recorded result |
|---|---|
| Complete configured default offline suite | 3,765 passed, 1 optional missing-Torch skip, 2 existing tokenizer deselections, 10 warnings; exit 0 in 768.39s. No added exclusions. |
| Membership | All 3,718 SDK selected IDs retained plus 48 comparison cases; no removed IDs. |
| Focused runs | 48/48 comparison and 1,036/1,036 focused passed twice. Counts overlap the full suite, not additive totals. |
| Sensitivity | Planned-denominator and task-fingerprint mutants fail intended assertions; two-test baselines and restorations pass. |
| Illustrative six-pair SQLite test | Baseline 4/6, treatment 3/6; delta -1/6, CI [-2/3,1/3], p=1; exactly two regressions and one improvement. Existing paired export/orientation verified. |
| Analysis guard | DBs unavailable; zero forbidden execution, scoring, network, credential-read or write events; zero formatted canary leaks. |
| Audit/resources | Outer pytest network/cache/tokenizer 0/0/0. Observed comparison protocols: raw and GC-settled FD deltas zero, no new live threads. All 253 recorded owned PIDs absent. |

The six-pair result is illustrative test evidence, not scientific benefit,
statistical significance or customer savings. Python audit counts are not
arbitrary-child/native telemetry. Inherited OS external-IP denial was verified;
loopback/Unix IPC remain permitted, not local-proxy isolation. Resource checks
cover observed protocols and recorded PIDs, not total host clearance.

Security review found blocked reads incorrectly labeled invalid content.
Two RED failures with 46 passes preceded the fix; all 48 then passed.
Bounded-reader `PermissionError`/other `OSError` now yield unscored
`capture_read_blocked`; missing files remain `missing_capture`. Aggregate
statistics stay absent and exception text/paths do not leak. Python/security
re-review closed the finding; broader general review found no actionable issues.

Separate actual Devin CLI review used SWE-2 High (`swe-2-high`), session
`florentine-mulberry`: exit 0, 95.197s, no issues across three specific static
contract challenges, zero agent tool calls and unchanged source bytes.
This was static review, not test execution. The earlier Droid attempt was
not SWE and is not counted as this review.

The first final-suite attempt retained two long-socket-path harness failures.
Scratch-only equivalent AF_UNIX addressing/bootstrap resolved them without
changing product source, assertions or thresholds. This is not a pristine
uninstrumented-harness claim. A non-failing 60s nested-baseline stack was retained;
the nested baseline later passed.

## Local evidence and remaining gates

Primary final receipt:
`/Users/nikolassapalidis/scratch/co-train-2026-10-29/comparison/independent-final-validation/validation-receipt.json`.
That directory contains `full-final.log`, `independent-analysis-receipt.json`,
`owned-process-validation.json` and `manifest-verification.json`.
The parent verified the 177-entry evidence manifest.
Separate Devin receipt:
`/Users/nikolassapalidis/scratch/co-train-2026-10-29/devin-swe/acceptance-2026-10-29T13-08-13-372Z/receipt.json`.

The older 3,763-pass receipt under `comparison/independent-validation/` covers
older prefix bytes only, not final corrected-byte acceptance. Original receipts/
logs stay local scratch, not portable with a clone. Repository source/tests
reproduce current mechanics, not the original validation environment.
Documentation integration read receipts and did not rerun suites.

No native/container/kernel or full guardian recovery acceptance, model benefit,
authenticated approval or approved-reuse attribution was established. No new
native/API/training trial, paid action, push or deployment follows from this
analysis capability. Financial gate remains closed, earlier one-shot permissions
consumed, and existing authorization gates unchanged.
