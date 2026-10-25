# Frontier measurement consistency

## Authority and scope

Local consistency repair approved 2026-10-25, preserving scientific thresholds.
Preserve the public frontier API and existing count-only admission:
`MIN_FRONTIER_TASKS = power_pairs(0.25, 0.5)`, currently 59. No separate retention
threshold. The band-width utility remains diagnostic, not an admission rule.

## Numerical acceptance tests, before implementation

All fixtures are synthetic. Temporary amendment markers exercise parsing only;
they are not owner signatures, real measurements or scientific approval.

| Test | Numerical pass criterion |
| --- | --- |
| `test_public_frontier_rejects_missing_or_malformed_measurement` | All 6 cases refuse with measurement-specific reasons. |
| `test_public_frontier_names_each_missing_measurement_key` | All 5 cases name the absent key. |
| `test_public_frontier_rejects_invalid_measurement_fields` | All 40 cases refuse; 0 uncaught type/arithmetic errors. |
| `test_public_frontier_rejects_invalid_measurement_band_endpoint` | All 8 cases refuse; the other endpoint remains exactly valid. |
| `test_valid_synthetic_g4_measurement_opens_public_gate` | 1 valid G=4 fixture opens with 0 reasons. |
| `test_synthetic_count_only_boundary_has_no_new_retention_floor` | 59/198 passes; 58/198 fails only the task floor; 198/19800 (1%) passes. |
| `test_real_optimized_process_refuses_invalid_synthetic_measurement` | All 3 actual `python -O` subprocesses refuse; 0 child assert statements. |
| Existing training/native preflight regressions | 0 failed assertions or relaxed assertions in the focused offline run. |
| Probability magnitude safety | Huge integer probability fields refuse with measurement-specific reasons, 0 `OverflowError` or `TypeError`. |
| Offline audit | 0 network attempts, cache accesses and tokenizer loads under the unchanged denied-network profile and new-root harness. |

Parent confirmed baseline RED: 61 failed, 5 passed, 1.55 seconds. The targeted
66 cases must all pass after repair. A later parent-controlled negative control
must remove the live helper call in memory and make consistency tests fail,
without changing a production source file.

## Implementation plan

1. Validate the existing measurement block and required keys. G is a positive
   non-bool integer matching the lane; ceiling matches the existing abort
   ceiling; band is a pair matching the existing utility within `1e-6`.
2. Probability fields are non-bool numbers bounded to [0, 1], excluding NaN and
   infinities without float-coercing huge integers. Candidates are positive
   non-bool integers. Retention matches `n_tasks / n_candidates` within `1e-6`;
   retained tasks cannot exceed candidates.
3. Remove the unused private `min_retention` argument and dormant admission
   floor, retaining and truthfully documenting `retention_floor` as band width.
4. Connect the helper using `reasons.extend` in the public gate. Preserve
   existing independent task-count, solve-rate and amendment checks.
5. Correct only stale synthetic fixture values, including truthful 59/198
   retention at the existing task-floor boundary. Run the focused 66 cases,
   training tests and relevant native preflight tests. Defer process/watchdog
   cases until the sandbox-compatible observer is ready.

## Non-goals

No scientific documents, real manifests or signatures, model/provenance schema,
G/ceiling/power thresholds, prompts, scorers, templates, native refusal flags or
launch authorization changes. No changes to weights/acquisition or concurrent
SQL pilot/budget/isolation code. The validator performs no network access,
installation, GPU work or deployment.

Passing synthetic tests establishes local metadata consistency only, not model
capability, measurement provenance or readiness to run a scientific experiment.
