# Project map

Updated 2026-10-27. This map organizes existing work; it does not change the
research protocol, runtime, experiment permissions or product positioning.

## Reading order

1. [README](../README.md): short orientation and offline-check entry point.
2. [Evidence index](evidence-index.md): demonstrated results, failures and gaps.
3. [SQL next-session handoff](../spec/sql-skill-pilot-handoff.md): current
   SQL blocker, source pins, local receipts and permission boundaries.
4. [HANDOFF](../HANDOFF.md): detailed dated history when needed.

For the original hypothesis, read [untrained results](results-untrained.md)
before [related work](related-work.md) and [the research index](../research/README.md).
The [completion roadmap](completion-roadmap.md) is an earlier planning document;
the later SQL handoff takes precedence for current SQL status.

## Workstreams

| Track | Scope | Evidence boundary |
|---|---|---|
| Untrained comparison | Bash versus PTC on retired `ledger` tasks. | Historical small-sample result; no trained-model or customer-savings conclusion. |
| SQL skill pilot | Execution capture, caller-authored SQL skills, qualification/reuse and a gated model-pilot controller. | Offline mechanics work; real record lifecycle failed before reuse. Financial gate closed, zero live pilot model calls. |
| Local MLX | Sampling, GRPO updates, adapters and controlled comparisons on local hardware. | Separate source/evidence; improvement unproven, three-seed trial incomplete, no holdout evaluation. |

Do not combine overlapping test counts or use one track's permissions/results
for another.

## Directory map

| Path | Purpose |
|---|---|
| `docs/` | Research reports, preregistration, deviations and dated runbooks. |
| `spec/` | Implementation contracts, pilot protocol and SQL continuation handoff. |
| `research/` | Source research, synthesis and dated verification receipts. |
| `src/cotrain/`, `tests/` | Harness contract, adversarial non-solvers and gate fixtures. Deliberately leaky fixtures are test targets, not cleanup candidates. |
| `ptc/` | Restricted programmatic-tool-calling runtime and SQL isolation. |
| `ledger/` | Retired taskset retained for historical comparison and regression tests. |
| `bench/` | SQL task loading/scoring, harness comparisons and frontier controls. |
| `train/` | Training integration, SQL capture/skill mechanics and pilot control. |
| `step2/` | Historical free-GPU smoke, results and separate legacy tests. |
| `process_watchdog.py` | Shared bounded process-cleanup support. |

## Local workspace boundaries

Snapshot checked 2026-10-27, before this documentation cleanup:

| Workspace | Saved checkpoint | Use |
|---|---|---|
| `~/Developer/co-train` | `fix/nonfinite-dead-group-monitor`, `6bda2ac` | Writable SQL checkout and this documentation cleanup. |
| `~/scratch/co-train-mlx-session-handoff-2026-10-25/worktree` | `docs/mlx-three-seed-handoff-2026-10-25`, `8c877fd` | Separate MLX continuation. Start at its `docs/2026-10-25-mlx-continuation.md`. |
| `~/scratch/co-train-frontier-validation-2026-10-25/worktree` | `fix/frontier-measurement-consistency`, `ec165f7` | Separate frontier/MLX source checkpoint. |
| `~/scratch/co-train-native-runtime-2026-10-24/worktree` | `feat/native-pinned-local-model`, `da011d7` | Separate native-runtime work. |
| `~/Developer/misc/co-train` | Read-only reference checkout | Not the writable project checkout. |

These are machine-local paths, not portable clone contents or verified remote
branch states. Do not merge, move or clean other worktrees as housekeeping.
The MLX continuation identifies 568 sealed evidence entries outside Git;
preserve those roots and their manifests.

## Next priorities

- Organization: use this map and the evidence index instead of treating dated
  checkpoints as simultaneous current state.
- SQL engineering: diagnose the recorded pre-STOPPED missing-usage gap offline.
  A new real trial needs separate approval.
- MLX engineering: CPU-only RSS-probe diagnosis under its separate handoff.
  No new training or holdout run is authorized by this cleanup.
- YC/Speedrun preparation: decide the customer and first use case, collect buyer
  evidence, and choose a reproducible demonstration. Technical receipts do not
  establish demand. See the evidence index for the missing proof.

## Non-goals

No runtime fixes, dependency installs, new experiments, evidence edits, file
deletions, worktree consolidation, public uploads or accelerator submissions.
No new market, traction, savings or model-improvement claims.
