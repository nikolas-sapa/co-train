# Project map

Updated 2026-10-30. Research priority is the original **4 -> 5 -> 6** sequence.
Recent SQL reuse/acceptance work was separate engineering scope drift, not
completion of that sequence. This map changes no protocol, runtime, gates,
experiment permissions or product positioning.

## Reading order

1. [Current research milestone table](../README.md#current-research-milestones-4-6):
   stage 4 PARTIAL, stage 5 PARTIAL, stage 6 BLOCKED.
2. [Agent defect escalation](2026-10-30-agent-defect-escalation.md) and the
   [launch contract](../spec/agent-defect-escalation-harness.md): implemented
   collector/SQL-arm and `PTCHarness.launch` reporting, payload bounds,
   validation receipts and the remaining stage-4 routes.
3. [Stage-5 baseline readiness](2026-10-30-baseline-readiness.md): proposed
   seeded draw, gold-validation/exclusion ledger and frontier-adapter gaps
   before any paired measurement.
4. [Harness parity](harness-parity.md), [untrained results](results-untrained.md)
   and [taskset contract](bench-taskset.md): existing instruments, the retained
   preregistered negative result and current-taskset baseline gaps.
5. [Native training constraints](../spec/native-training.md): frontier/stack/
   CLI requirements, not proof of an executed training path.
6. [HANDOFF](../HANDOFF.md) and [evidence index](evidence-index.md): current
   priorities followed by dated evidence and local-only source boundaries.

The [completion roadmap](completion-roadmap.md) is earlier planning history.
For separate SQL mechanics, use the [portable helper receipt](2026-10-30-portable-sql-skill-sdk-acceptance.md)
and its [usage contract](../spec/sql-skill-sdk-acceptance.md); these are not
prerequisites to stage 4 defect-channel work.

## Workstreams

| Track | Scope | Evidence boundary |
|---|---|---|
| Research stages 4-6 | Agent defect-escalation channel (collector, real PTC/shell arms and launch opt-in built; production routes and config bindings pending), paired current-taskset untrained baseline, then co-training/harness swap. | PARTIAL / PARTIAL / BLOCKED. Reporting so far is opt-in caller-owned memory plus forgeable shell markers, not authenticated production routes; no current-taskset baseline or trained benefit. |
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

1. **Stage 4 first, still PARTIAL.** Done portion: the opt-in
   [defect/shortcut channel](2026-10-30-agent-defect-escalation.md) now has a
   caller-owned collector, real PTC catalog and actual shell-runner arms with
   shared reporting semantics/quotas across both prompts, a deterministic
   real-SQLite rule-legal shortcut fixture, and the constructor-only
   `PTCHarness.launch` `qa_factory` from the
   [launch contract](../spec/agent-defect-escalation-harness.md): launch-scoped
   channels, local/MCP `report_defect` collision refusal and weak live-channel
   tracking. Shell markers are forgeable output, not authenticated tool calls.
   Proof at `ae2323d`: 813 targeted passes (14 launch lifecycle plus 799
   existing selection) and two real RED-then-restored controls; a default-copy
   regression and a non-overlapping concurrency test were fixed
   pre-publication. Targeted selection only, not a full suite or native proof.
   Remaining artifacts: production Bash verifier routing, framework/CLI/config
   activation of the implemented PTC launch route, isolated report transport, sealed
   capture/SqlEpisode reporting-config binding and TRL integration. Handoff
   acceptance for "complete": reports on both real production routes with no
   lost reports or independent errors, evidenced by bounded reporting
   configuration bound to reviewed source. Do not invent a schema to get there.
2. **Stage 5, PARTIAL:** first the exact seeded draw with the complete
   task-ID list, local `validate_golds()` on that exact suite, an exclusion
   ledger and draw provenance —
   [proposed preparation](2026-10-30-baseline-readiness.md), not an executed
   step. Then a real frontier generation adapter and a BIRD paired driver, and
   only under explicit authorization the frozen-policy per-task measurement
   that produces `bench/frontier/manifest.json` and the paired baseline under
   the [parity contract](harness-parity.md). [A8](pre-registration.md) is
   signed; the missing pieces are the manifest and eligible rates, not a
   signature. Historical v9/v10 dead-group aggregates are not eligible rates;
   do not copy published paper numbers into BIRD results. Keep every planned
   task, error categories and invalid-gold outcomes visible. Preserve the
   retired `ledger` negative result and existing preregistration/amendment
   gates; measurement is baseline preparation, not a stage-4 blocker.
3. **Stage 6, BLOCKED:** requires the legitimate frontier manifest, compatible
   frontier/stack/template and completed/verified native CLI gates, then the
   actual preregistered holdout with three-seed and harness-swap evidence. The
   native main CLI still explicitly refuses after preflight; no dependency or
   protected-gate bypass or relaxation is proposed.

Optional portable SQL-native acceptance stays separate and off the critical
path; it is not a stage-4 prerequisite. Old 19/15-job permissions are consumed
and never replayed; preflight-only context preparation is not fresh execution
consent. The separate MLX continuation is real partial work, not stage-6
holdout/three-seed/harness-swap proof. This update grants no install, model,
native, training or paid-experiment permission. Future work follows applicable
authorization; paid calls need an explicit budget, not agent-session usage.
Engineering counts do not establish learned benefit, savings, demand or
customer traction.

## Non-goals

No runtime fixes, dependency installs, new experiments, evidence edits, file
deletions, worktree consolidation, public uploads or accelerator submissions.
No new market, traction, savings or model-improvement claims.
