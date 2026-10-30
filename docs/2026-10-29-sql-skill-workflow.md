# Caller-owned SQL skill SDK, 2026-10-29

Typed file integration around existing SQL skill APIs:
[source](../train/sql_skill_workflow.py),
[tests](../train/test_sql_skill_workflow.py),
[contract](../spec/sql-skill-workflow.md) and
[usage](../train/README.md#caller-owned-file-workflow).
The [earlier offline demo](2026-10-29-sql-reuse-demo.md) remains a separate
fixture receipt; its historical results are unchanged.

## Implemented boundary

- `create_candidate_file` is data-only and saves canonical `candidate.json`.
- `qualify_candidate_files` requires an external source-capture pin and four
  caller-owned cases. It saves returned captures before optionally publishing
  `promotion.json`, an UNAPPROVED qualification receipt.
- `reuse_approved_files` separately requires the externally retained
  whole-promotion-envelope pin and exact approval IDs. It saves `reuse.json`
  without reopening historical source/qualification databases.

Execution requires literal `allow_execution=True`; default is `False`.
The caller's executor passes through unchanged, including `None` for the
existing in-process path. Paths are absolute, with safe exclusive new output
directories outside checkout; existing files are not overwritten. Failed
qualifications retain returned captures without promotion. Typed capture
exceptions retain carried evidence and re-raise; other exceptions do not
manufacture captures. Storage failures propagate and may leave partial evidence,
not a completed receipt.

Callers still own trusted code/assets, stable DB snapshots, storage and approval
channels. The SDK does not independently approve anything or derive authority
from the receipt itself. Hashes are not authentication. Existing safe-file
helpers assume trusted filesystem ancestors without hostile concurrent replacement;
the SDK adds no race-proof sandbox.

No CLI, serialized schema, dependency/vendor or runtime adapter was added.
Existing evaluator, defaults, runtime and protected budget/scorer contracts
remain unchanged.

## Independent verification

Baseline HEAD: `79168e6b794962b7f40f26aac4c004a7446fd00c`.
All 250 bound source files stayed unchanged during validation. Independent
Python/security/general static reviews found no actionable issues; execution
validation was separate.

| Check | Recorded result |
|---|---|
| Complete configured default offline suite | 3,717 passed, 1 skipped, 2 deselected, exit 0 in 754.08s; no new exclusions. All previous 3,683 selected IDs retained, plus 35 SDK cases. |
| Focused checks | 35/35 workflow; 719/719 combined. These overlap the full suite, not additive totals. |
| Two real SQLite families | Positive-payment sum and active-member/visit join count: 8/8 qualifications and 4/4 reuses valid EX=1. |
| Fresh-process handoff | Qualification in one process, external approval arguments supplied to another: 2/2 reuse EX=1 with five old DB paths unavailable. |
| Reuse refusal | Wrong pin/approval IDs, modified candidate and absent opt-in: zero program and zero scorer dispatches. |
| Second qualification fails | Exactly two program submissions; captures score [1,0]; zero promotion artifacts. |
| Sensitivity controls | Two baseline passes; independent external-pin and failed-qualification gate mutants each exit 1 at intended assertions, not setup/import failures. |
| Audit/resources | Outer pytest external-network/cache/tokenizer counts 0/0/0; 124 recorded owned PIDs absent. New-test FD results settled after explicit GC; raw transients are not denied. |
| Protected identity | `train/sql_pilot_budget.py`, `train/test_sql_pilot_budget.py`, `spec/sql-pilot-budget.md` and `bench/score.py` matched HEAD. |

The skip is unavailable optional Torch; both deselections are existing
`tokenizer_integration` controls. Native/container/kernel and full guardian
recovery acceptance were not run. Neither model learning/benefit nor scientific
generalization nor independently authenticated approval was established.
`executor=None` is not OS confinement or production-isolation acceptance.

Parent and inherited-child external-IP denial were verified. Python audit counts
are not arbitrary-child/native telemetry; the OS profile permits loopback/Unix
IPC and is not local-proxy isolation. No global process/FD/filesystem clearance
is claimed. A validator-only truncated fixture-name lookup was corrected, with
the original incident retained; no production failure occurred.

## Evidence and remaining gates

Primary local receipt:
`/Users/nikolassapalidis/scratch/co-train-2026-10-29/workflow/independent-validation/validation-receipt.json`.
Named evidence in that directory includes `full.log`, `workflow-35.log`,
`focused-719.log`, `artifact-validation.json` and `owned-process-validation.json`.
The parent verified the evidence manifest: 132 entries, zero mismatches.
Documentation integration read the receipt; it did not rerun these checks.

Original scratch evidence is local, not portable with a clone. Repository SDK
source/tests reproduce the new mechanics with compatible existing test
dependencies and trusted caller assets; they do not recreate the original
validation environment or independently approve reuse. No logs or receipts
were fabricated or copied into this document.

The [earlier real lifecycle failure](../spec/sql-skill-pilot-handoff.md#latest-real-trial-failed-safely-closed)
is not resolved by these offline results. Financial authorization remains
closed, earlier one-shot permissions consumed, and existing native/paid/push
gates remain in force. No provider/model/native trial, deployment or new
scientific claim follows from this SDK acceptance.
