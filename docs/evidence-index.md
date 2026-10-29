# Evidence index

Updated 2026-10-29 with capture comparison, caller-owned SDK and demo receipts.
These are recorded results, not fresh test runs from documentation integration.
The project has working experimental mechanics and unresolved acceptance
failures. Model improvement and production readiness are not established.

## Recorded technical evidence

| Date / scope | Recorded observation | Source | Limitation |
|---|---|---|---|
| 2026-10-29, read-only capture comparison | Final corrected-byte suite: 3,765 passed, one optional Torch skip, two configured tokenizer deselections. All prior SDK IDs retained plus 48 comparison cases. | [Comparison verification receipt](2026-10-29-sql-capture-comparison.md). | Caller arms are not authenticated provenance or approved-reuse attribution. Illustrative paired test is not model benefit, significance or savings. Counts overlap earlier suites. |
| 2026-10-29, caller-owned SQL skill SDK | 3,717 offline passes, one optional Torch skip, two existing tokenizer deselections. Two SQLite families: 8/8 qualifications and 4/4 reuse EX=1; separate-process reuse 2/2. | [SDK verification receipt](2026-10-29-sql-skill-workflow.md). | Qualification is UNAPPROVED; trusted assets, external pins and exact approval IDs required. No native/guardian acceptance or model benefit. Counts overlap earlier suites. |
| 2026-10-29, portable offline SQL reuse | Two independently executed fixture demos, each four EX=1 qualifications and two fresh-process EX=1 reuses. Complete configured offline suite: 3,682 passed, one optional Torch skip, two existing tokenizer deselections. | [Demo command and verification receipt](2026-10-29-sql-reuse-demo.md). | Standard-library fixture mechanics, synthetic container metadata in process tests. No new native acceptance, model benefit or independently authenticated approval. |
| Untrained `ledger` report, checkpoint reviewed 2026-10-27 | Run 2h: PTC 14/14, bash 12/14. | [Untrained results](results-untrained.md), [trace provenance](trace-provenance.md), [deviations](deviations.md). | Retired taskset, n=14, not statistically separable. Cost estimates have provenance/correction limits; no general customer-savings claim. |
| 2026-10-24, caller-authored SQL skills | Recorded qualification and fresh-process reuse of a supplied program. | [HANDOFF, executable-skills checkpoint](../HANDOFF.md), [skill contract](../spec/sql-executable-skills.md). | Offline mechanics, not model-generated skill discovery or scientific generalization. Does not override the later real lifecycle failure. |
| 2026-10-25, SQL source checkpoint | 3,403 offline passes; one optional Torch skip, two tokenizer deselections, ten existing fork warnings. | [SQL handoff, what is verified](../spec/sql-skill-pilot-handoff.md#what-is-verified). | Historical source-bound receipt, not a fresh run or full kernel acceptance. Counts overlap earlier suites; never add them together. |
| 2026-10-25, real SQL trial | Two native tests passed. Record lifecycle failed at its first PROGRAM, before scoring, qualification or reuse. Missing-usage RPC completed 4.796 ms before STOPPED. | [SQL handoff, latest real trial](../spec/sql-skill-pilot-handoff.md#latest-real-trial-failed-safely-closed). | Strict discard correctly refused; the observed race remains unresolved. Cleanup is not acceptance. |
| 2026-10-25, SQL model pilot | Zero live model calls; financial gate closed. | [SQL handoff, financial gate](../spec/sql-skill-pilot-handoff.md#financial-gate-closed). | No measured model benefit, model-generated skill benefit or dollar savings. Agent-session model usage is separate. |
| 2026-10-25, separate MLX controlled comparison | Base 48/192, adapter 51/192; +1.5625 percentage points, 95% prompt-cluster interval [-3.6458, +7.2917] points. | Local MLX continuation, source location below. | Interval includes zero; improvement unproven. Separate worktree/evidence, not a SQL-pilot result. |
| 2026-10-25, separate MLX three-seed attempt | Seed7001: 320 generations, 17 updates. Seed7002 rejected after RSS-helper timeout; third seed and evaluations not launched. | Local MLX continuation, source location below. | Incomplete trial, no holdout model evaluation, no pooled effect estimate. Rejected prefix is control-only evidence. |

## Source availability

The linked contracts and handoffs are repository documents. Several primary
logs, manifests and trial receipts live outside Git:

- Capture comparison final validation:
  `/Users/nikolassapalidis/scratch/co-train-2026-10-29/comparison/independent-final-validation/validation-receipt.json`.
  [Summary](2026-10-29-sql-capture-comparison.md) distinguishes corrected-byte
  acceptance from older prefix evidence and separate Devin static review.
- SQL skill SDK validation:
  `/Users/nikolassapalidis/scratch/co-train-2026-10-29/workflow/independent-validation/validation-receipt.json`.
  The [SDK summary](2026-10-29-sql-skill-workflow.md) separates reproducible
  source/test mechanics from local, nonportable original evidence.
- SQL reuse demo validation:
  `/Users/nikolassapalidis/scratch/co-train-2026-10-29/independent-validation/validation-receipt.json`.
  The [durable summary](2026-10-29-sql-reuse-demo.md) records verification and
  limitations. Original scratch receipts are not portable; the runnable demo is.
- SQL: `~/scratch/co-train-completion-2026-10-24/`. Exact receipt directories,
  hashes and consumed permissions are listed in the
  [SQL handoff](../spec/sql-skill-pilot-handoff.md#evidence-to-inspect-not-replay).
- MLX continuation:
  `~/scratch/co-train-mlx-session-handoff-2026-10-25/worktree/docs/2026-10-25-mlx-continuation.md`,
  saved in local commit `8c877fd`. It identifies seven sealed evidence roots,
  totaling 568 entries, and their manifest hashes.

A clone alone does not contain the original acceptance evidence. The 2026-10-27
cleanup read handoffs without verifying primary receipt hashes or rerunning
tests; the 2026-10-29 summary records separate independent execution validation.
Documentation integration did not rerun it. Missing local evidence must be reported as unavailable,
not replaced with a fabricated receipt. Do not upload it as housekeeping.

## Application-preparation gaps

| Question | Current boundary | Evidence still needed |
|---|---|---|
| Who is the first customer, and what task do they need done? | This repository does not establish a validated buyer or product use case. | Owner-selected customer/use case and dated buyer conversations. |
| What works in a demonstration? | [Offline demo](2026-10-29-sql-reuse-demo.md), [file SDK](2026-10-29-sql-skill-workflow.md) and [read-only comparison](2026-10-29-sql-capture-comparison.md) mechanics verified; latest real record lifecycle failed. | Native lifecycle acceptance remains open and requires separate authorization. SDK reuse needs trusted assets/external approval; comparison cannot establish provenance, reuse attribution or savings. Offline success is not production readiness. |
| Does the model improve? | Separate MLX comparison includes zero; later trial incomplete. | An accepted controlled evaluation under a frozen protocol, with failed runs retained. New experiments require authorization. |
| Is there traction or willingness to pay? | Not established by technical test counts or local experiments. | Actual user activity, commitments or payments, if obtained. No invented metrics. |
| What is different from existing work? | Original framing has later related work. | A precise comparison using [related work](related-work.md), tied to the chosen customer/use case. |

These gaps are a preparation checklist, not application answers or a decision
that the project cannot become a company. No accelerator form was completed
or submitted, and no current deadline or eligibility rule was checked here.
