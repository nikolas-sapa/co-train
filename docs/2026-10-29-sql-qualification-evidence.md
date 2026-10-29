# SQL qualification failure evidence, 2026-10-29

Completed offline acceptance for qualification evidence and
[outer timing](2026-10-29-sql-reuse-timing.md). This is separate from the
[bounded direct-evaluator native trial](2026-10-29-bounded-native-acceptance.md).

## Corrected failure boundary

An ordinary second-case SQLite snapshot-drift `ValueError` previously lost the
first successful qualification capture. Typed `CaptureExecutionAborted` already
retained a prefix and was not this defect.

The [evaluator](../train/sql_skill_eval.py) now attaches actual ordered
`qualification_captures` to the same exception instance, preserving its cause.
The [file SDK](../train/sql_skill_workflow.py) persists that completed prefix
before propagation. No capture is invented for an unsealed attempt.
Pins, approval ownership and execution consent remain unchanged. Legitimate
source-binding changes invalidate old artifacts; this repair does not repin them.
See [workflow tests](../train/test_sql_skill_workflow.py) and
[contract](../spec/sql-skill-workflow.md).

## Publication and durability limits

Prepublication storage faults publish no promotion. A post-rename final-directory
fsync fault has a different boundary: the same `OSError` propagates with four
valid captures, `promotion.json` is already visible, and `.promotion.pending`
is absent. No rollback is claimed. Durability is unknown.
Visible files establish neither successful API completion nor approval.

Require successful qualification return plus independent external review and
externally retained promotion pin/approval IDs before reuse. Even successful
qualification produces an UNAPPROVED receipt.

## Final independent offline verification

Baseline HEAD: `3b41b6f32d4854e11fef81c97fc044977d35d65a`.
The complete configured default suite passed **3,793 tests**, with zero failures,
one optional missing-Torch skip, two existing tokenizer deselections, ten warnings
and 28 passing subtests, exit 0 in **725.24s**. No added skips, filters or deadline
changes. All 260 bound paths stayed unchanged during validation, before this
documentation integration. Those source bytes, not later documentation, were
tested. Membership retains prior selected cases under one explicit relocation:
19 pure timing tests in bench, one unchanged real-SDK case in train.

Independent probes passed 28/28, including real SQLite source EX=0, four
qualifications EX=1 and one reuse EX=1. Three controls caused intended assertion
failures: omitted fsync (38 versus 49 simulated ns), omitted failed setup
(60 versus 100 ns), and swallowed post-rename fsync (`OSError` not raised).
Restored checks passed 19 timing tests and one storage test. Counts overlap
the full suite; never add them.

The 678 original strict resource checks had zero FD delta and no new live
threads. Separately, 54 targeted protocols had zero raw and GC-settled FD
deltas and no new live threads. All 127 recorded owned PIDs were absent.
Outer pytest network/cache/tokenizer counts were 0/0/0, with 13 permitted
loopback events. Inherited OS external-IP denial was verified; Unix IPC and
loopback remain allowed. Audits are not arbitrary-child/native telemetry or
global host/process clearance. Four protected files and 16 native-closure
files matched HEAD.

Earlier 3,772-pass prefix and 173-case evaluator/workflow receipts remain
historical, not additive totals or substitutes for this final run.

## Retained interruption, failure and correction

An initial managed run was interrupted without a terminal result. Its continuation
completed **3,792 passed, one failed**, one optional Torch skip, two configured
deselections, ten warnings and 28 passing subtests, exit 1 in **728.52s**.
All 21 new root-context items passed, but the isolated bench baseline correctly
lacked train and could not import the new real-SDK integration test.

The whole unchanged SDK class moved to
[train/test_sql_reuse_timing.py](../train/test_sql_reuse_timing.py), retaining its
AST and all 11 assertions; 19 pure bench tests stayed in bench. The original
bench-only target went from one failure/535 passes to 535 passes, both copies
without train. Focused correction passed 193 cases and 28 subtests. Fresh Python
review approved. This was test ownership, not a production evaluator/native
defect or test removal. The corrected full run then passed; failed evidence
was not overwritten.

## Local evidence

Final root: `~/scratch/co-train-2026-10-29/final-corrected-validation-q6afw45z/`.
Primary files: `validation-receipt.json`, `full-result.json`, `full.log`,
`manifest-verification.json`, `protected-native-identity.json`.

- Canonical receipt SHA256:
  `5743e3b41f780c06221db441ee75aaa2b51860b463f1e286195f72f76ef0219c`.
- Evidence manifest SHA256:
  `f796a6126e1993c3734f5876f0679f50c328f42b864e0bd89c94cde5de7a90f4`.
  Verification records 20,445 entries; inventory size is not a quality metric.
- Failed receipt:
  `~/scratch/co-train-2026-10-29/final-integrated-validation-xd7l0fty/final-validation-receipt.json`.
- Ownership correction:
  `~/scratch/co-train-2026-10-29/package-isolation-fix-dfgjvv8x/package-isolation-fix-receipt.json`.

Original logs/receipts remain local, not portable with a clone. Source/tests
reproduce mechanics, not the original validation environment. Documentation
checks are separate; no full-suite rerun accompanied these docs. Native SDK,
full adversarial guardian acceptance, model benefit and economics remain unproved.
Financial authorization and separate standing Git instructions are unchanged.
