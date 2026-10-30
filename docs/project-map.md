# Project map

Updated 2026-10-30. Research priority is the original **4 -> 5 -> 6** sequence.
Recent SQL reuse/acceptance work was separate engineering scope drift, not
completion of that sequence. This map changes no protocol, runtime, gates,
experiment permissions or product positioning.

## Reading order

1. [Current research milestone table](../README.md#current-research-milestones-4-6):
   stage 4 PARTIAL, stage 5 PARTIAL, stage 6 BLOCKED.
2. [Harness parity](harness-parity.md), [untrained results](results-untrained.md)
   and [taskset contract](bench-taskset.md): existing instruments, the retained
   preregistered negative result and current-taskset baseline gaps.
3. [Native training constraints](../spec/native-training.md): frontier/stack/
   CLI requirements, not proof of an executed training path.
4. [HANDOFF](../HANDOFF.md) and [evidence index](evidence-index.md): current
   priorities followed by dated evidence and local-only source boundaries.

The [completion roadmap](completion-roadmap.md) is earlier planning history.
For separate SQL mechanics, use the [portable helper receipt](2026-10-30-portable-sql-skill-sdk-acceptance.md)
and its [usage contract](../spec/sql-skill-sdk-acceptance.md); these are not
prerequisites to stage 4 defect-channel work.

## Workstreams

| Track | Scope | Evidence boundary |
|---|---|---|
| Research stages 4-6 | Environment/defect channel, paired current-taskset untrained baseline, then co-training/harness swap. | PARTIAL / PARTIAL / BLOCKED. Existing runtime, scoring and both harnesses do not establish channel/shortcut completion, a current baseline or trained benefit. |
| SQL engineering | Capture, caller-authored skills, qualification/reuse and native lifecycle. | Published `1501f0b` includes recorded portable offline acceptance. Earlier [direct-evaluator 19-job](2026-10-29-bounded-native-acceptance.md) and [SDK 15-job](2026-10-29-native-sql-skill-workflow.md) native campaigns passed; portable-helper native phases NOT_EXECUTED. Separate bounded engineering, not stage 4-6 or adversarial/kernel completion. |
| Local MLX | Actual sampling, GRPO updates, adapters and controlled comparisons on local hardware. | Separate dated evidence; no completed holdout/three-seed trial or harness-swap proof. Not stage 6 completion; historical Mac/CUDA restrictions are not a blanket ban on local training. |

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

The workspace section below is a **historical 2026-10-27 snapshot**, not a fresh
remote-branch/worktree audit for this update.

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

1. **Stage 4 first:** finish the structured agent defect-escalation/verifier-QA
   channel and demonstrate the reporting route and one instrumented rule-legal
   shortcut's deterministic telemetry. Existing SQL runtime/reward/isolation
   pieces are partial implementation, not that missing channel.
2. **Stage 5:** prepare the matched current-taskset untrained comparison under
   the [parity contract](harness-parity.md). Keep every planned task, error
   categories and invalid-gold outcomes visible before training. The
   [frontier probe](../bench/frontier/probe.py) exists, but
   `bench/frontier/manifest.json` is absent. Measurement is baseline preparation,
   not an additional blocker on stage 4 coding. Preserve the retired `ledger`
   negative result and existing preregistration/amendment gates.
3. **Stage 6:** only after legitimate frontier measurements, compatible stack
   and completed/verified native CLI integration satisfy the existing gates,
   perform the preregistered training and actual cross-harness evaluation under
   its appropriate authorization. Main CLI still explicitly refuses after
   preflight; no dependency or protected-gate bypass is proposed.

Optional portable SQL-native acceptance is separate and off the critical path.
Old 19/15-job permissions are consumed; preflight-only context preparation is
not fresh execution consent. This update grants no model/native/training
experiment or spending permission. Future work follows applicable authorization;
paid calls need an explicit budget, not agent-session usage. Engineering counts
do not establish learned benefit, savings, demand or customer traction.

## Non-goals

No runtime fixes, dependency installs, new experiments, evidence edits, file
deletions, worktree consolidation, public uploads or accelerator submissions.
No new market, traction, savings or model-improvement claims.
