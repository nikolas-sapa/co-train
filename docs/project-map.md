# Project map

Navigation refreshed 2026-11-01 from recorded documentation, not a new runtime
or remote-state audit. Research priority remains **4 -> 5 -> 6**.
SQL reuse/acceptance is separate engineering, not completion of that sequence.
This map changes no protocol, gates, experiment permissions or positioning.

## Reading order

1. [Current milestones](../README.md#current-research-milestones-4-6):
   stage 4 PARTIAL, stage 5 PARTIAL, stage 6 BLOCKED.
2. [Evidence index](evidence-index.md): dated observations, limitations and
   machine-local sources. Test totals overlap and are not additive.
3. [Reporting](2026-10-30-agent-defect-escalation.md),
   [SQL reporting evidence](2026-10-30-sql-reporting-evidence.md),
   [configured Bash evaluation](2026-10-31-bash-qa-eval.md) and
   [configured PTC activation](2026-10-31-ptc-qa-activation.md):
   stage-4 implementation evidence and remaining boundaries.
4. [Baseline readiness](2026-10-30-baseline-readiness.md),
   [draw preparation](2026-10-31-bench-preparation.md) and
   [validated-draw consumer](2026-10-31-bird-validated-draw.md):
   preparation mechanics, not a measured BIRD baseline.
5. [Harness parity](harness-parity.md), [taskset contract](bench-taskset.md),
   [preregistration](pre-registration.md), [negative untrained result](results-untrained.md)
   and [defect/amendment ledger](deviations.md): preserve the measurement contract.
6. [Native training constraints](../spec/native-training.md) and
   [HANDOFF](../HANDOFF.md): frontier/stack/CLI gates and dated continuation history.

The [completion roadmap](completion-roadmap.md) is earlier planning history.
The [historical README](readme-history.md) preserves the entire pre-cleanup
landing page, including dated receipts, negative results, visible corrections,
old installation commands and branch snapshots. It is not current guidance.
For the earlier free-GPU verdict, use [Step 2 results](../step2/results/README.md).

## Workstreams

| Track | Scope | Evidence boundary |
|---|---|---|
| Research stages 4-6 | Reporting on SQL arms and launch routes, configured Bash evaluation and configured PTC reporting; then paired BIRD baseline and co-training/harness swap. | PARTIAL / PARTIAL / BLOCKED. Stock CLI admission, isolated transport/binding and actual TRL integration remain incomplete. Shell telemetry is forgeable; no current-taskset baseline or trained benefit. |
| SQL engineering | Capture, caller-authored skills, qualification/reuse and native lifecycle. | Published `1501f0b` includes recorded portable offline acceptance. Earlier [19-job direct-evaluator](2026-10-29-bounded-native-acceptance.md) and [15-job SDK](2026-10-29-native-sql-skill-workflow.md) native campaigns passed; portable-helper native phases remain NOT_EXECUTED. No full adversarial/kernel acceptance. |
| Local MLX | Actual sampling, GRPO updates, adapters and controlled comparisons on local hardware. | Separate dated evidence; comparison inconclusive and three-seed trial incomplete. No completed holdout or harness-swap proof. Historical Mac/CUDA restrictions are not a blanket ban on local training. |

Use the [portable helper receipt](2026-10-30-portable-sql-skill-sdk-acceptance.md)
and [contract](../spec/sql-skill-sdk-acceptance.md) for separate SQL mechanics.
In-progress owned SQL SDK binding is not qualified by this navigation update.
Controlled engineering references: [binding contract](../spec/sql-owned-sdk-binding.md),
[generation-failure composition](../spec/spikes/reference/sql-sdk-generation-failure/README.md)
and [Env writer-barrier composition](../spec/spikes/reference/sql-sdk-writer-barrier/README.md).
Their fixture results are not native ownership or research qualification.
Do not transfer permissions or results between tracks.

## Directory map

| Path | Purpose / entry point |
|---|---|
| [docs/](./) | Research reports, preregistration, deviations and dated runbooks. Start with the [evidence index](evidence-index.md). |
| [spec/](../spec/) | Implementation contracts, pilot protocol, spikes and SQL continuation handoff. [Native training](../spec/native-training.md) records the closed gates. |
| [research/](../research/README.md) | Source research, synthesis, deep lanes and dated verification receipts. |
| [bench/](../bench/) | SQL loading/scoring, harness comparisons, draw preparation and frontier controls. No frontier manifest is supplied. |
| [ptc/](../ptc/README.md) | Restricted PTC runtime, reporting and SQL isolation/lifecycle mechanics, with adjacent tests. |
| [train/](../train/) | Training integration, SQL capture/skill mechanics and gated pilot control, with adjacent tests. |
| [src/cotrain/](../src/cotrain/), [tests/](../tests/) | Harness contract, adversarial non-solvers and gate fixtures. Deliberately leaky fixtures must not be hardened. |
| [ledger/](../ledger/README.md) | Retired taskset retained for historical comparison and regression tests. |
| [step2/](../step2/README.md) | Historical free-GPU smoke, results and separate legacy tests that may reach Hugging Face. |
| Root `cotrain_*.py` | SDK plugin/runner entrypoints, intentionally flat at repository root. Do not move as housekeeping. |
| [process_watchdog.py](../process_watchdog.py) | Shared bounded process-cleanup support. |
| [pytest.ini](../pytest.ini) | Default collection: `tests ptc ledger bench train`; tokenizer integration excluded, `step2` separate. |
| [readme-history.md](readme-history.md) | Full archived README; original headings/internal anchors retained and relative Markdown links rebased. |

Root entrypoints include `cotrain_bash_qa.py`, `cotrain_bash_qa_env.py`,
`cotrain_bash_qa_eval.py`, `cotrain_ptc_qa.py` and `cotrain_owned_sql.py`.
Their presence is not a qualification or supported-stock-CLI claim.
See [existing-environment quick start](../README.md#existing-environment-quick-start)
for the source-checked test command, not an installation recipe.
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

1. **Stage 4, PARTIAL:** retain existing reporting/configured-runner evidence.
   Complete unsupported activation routes, isolated reporting transport/binding
   and actual TRL rollout integration without relaxing admission. See the
   [launch contract](../spec/agent-defect-escalation-harness.md).
2. **Stage 5, PARTIAL:** offline draw freeze/validation and retained-draw consumption
   are implemented, fixture-tested preparation. Select a real draw with disclosed
   bounds and preserve every planned task, provenance, exclusions, invalid golds
   and error categories. A production paired SDK runner and the BIRD baseline
   remain missing, not zero. No policy, runtime or group size is chosen here.
   A8 is signed; missing legitimate measurements/manifest are not a signature gap.
   Historical dead-group aggregates and published paper numbers are not eligible
   current-taskset rates.
3. **Stage 6, BLOCKED:** obtain legitimate frontier evidence and satisfy the
   unchanged stack/template and completed/verified native CLI gates before
   authorized preregistered training, holdout, three-seed and harness-swap evaluation.
   `bench/frontier/manifest.json` remains absent; the main training CLI explicitly
   raises `NotImplementedError` after preflight.

Preserve the retired `ledger` negative result and preregistration/amendment gates.
Frontier measurement is baseline preparation, not a stage-4 blocker.
Optional portable SQL-native acceptance stays separate and off the critical path.

Old 19/15-job permissions are consumed and never replayed; preflight-only
preparation is not fresh execution consent. Paid calls require explicit budget,
not agent-session usage. This update grants no install, model, native, training
or paid-experiment permission. Engineering counts establish no learned benefit,
savings, demand or customer traction.

## Non-goals

No runtime fixes, dependency installs, new experiments, evidence edits, file
deletions, worktree consolidation, public uploads or accelerator submissions.
No new market, traction, savings or model-improvement claims.
