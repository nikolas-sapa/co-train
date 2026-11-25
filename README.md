# co-train

Co-train tests whether training a small model around a tool interface improves
task performance, and whether any improvement survives a harness swap.
The comparison is bash versus programmatic tool calling (PTC), with BIRD-SQL
as the current taskset.

## Current research milestones 4-6

Research priority remains **4 -> 5 -> 6**. SQL reuse/acceptance engineering
and separate local MLX work do not complete this sequence.

| Stage | Status | Remaining gap |
|---|---|---|
| 4: environment + escalation channel | **PARTIAL.** Opt-in SQL-arm/launch reporting, configured Bash evaluation and configured PTC reporting have recorded evidence. | Stock CLI admission, isolated reporting transport/binding and actual TRL rollout/training integration remain incomplete. Shell telemetry is forgeable. |
| 5: two harnesses, measure untrained first | **PARTIAL.** Both SQL harnesses and offline draw preparation/validation exist. | The current BIRD paired untrained baseline is **missing, not zero**. A real selected draw, frontier measurement and authorized paired rollouts remain. |
| 6: co-train, then cross-harness evaluation | **BLOCKED.** The required `bench/frontier/manifest.json` is absent. | Compatible stack/template, legitimate frontier evidence and completed/verified CLI integration are required. The main training CLI still raises `NotImplementedError` after preflight. |

The retired `ledger` premise check did **not** reproduce the published
bash-over-PTC ordering: PTC 14/14 versus bash 12/14 in run 2h, not statistically
separable at n=14. Preserve that [negative result](docs/results-untrained.md);
it is not the current BIRD baseline.

No completed co-training/harness-swap result or learned benefit is established.
Separate MLX sampling and weight updates are partial evidence, with an
inconclusive comparison and an incomplete three-seed trial.
See the [evidence index](docs/evidence-index.md) for limitations and source availability.

## Start here

| Question | Read |
|---|---|
| How is the repository organized? | [Project map](docs/project-map.md) |
| What is recorded, and what remains unproved? | [Evidence index](docs/evidence-index.md) |
| What should a continuing session inspect? | [HANDOFF](HANDOFF.md), dated checkpoints distinguished from current state |
| What was fixed before measurement? | [Preregistration](docs/pre-registration.md), [deviations and defect ledger](docs/deviations.md) |
| What happened in the untrained premise check? | [Results](docs/results-untrained.md), [trace provenance](docs/trace-provenance.md) |
| How are the current comparison and taskset defined? | [Harness parity](docs/harness-parity.md), [BIRD taskset](docs/bench-taskset.md) |
| Where are research and implementation contracts? | [Research index](research/README.md), [related work](docs/related-work.md), [specifications](spec/) |
| Where did the long README go? | [Historical README](docs/readme-history.md), complete dated text, receipts and corrections |

Stage-4 entry points: [reporting](docs/2026-10-30-agent-defect-escalation.md),
[SQL evidence](docs/2026-10-30-sql-reporting-evidence.md),
[Bash evaluation](docs/2026-10-31-bash-qa-eval.md) and
[PTC activation](docs/2026-10-31-ptc-qa-activation.md).
Stage-5 preparation: [readiness](docs/2026-10-30-baseline-readiness.md),
[draw preparation](docs/2026-10-31-bench-preparation.md) and
[validated-draw consumer](docs/2026-10-31-bird-validated-draw.md).
Stage-6 constraints: [native training](spec/native-training.md).

## Existing-environment quick start

From the repository root, with an **existing compatible environment**:

```bash
.venv-ptc/bin/python -m pytest -q
```

This command matches [pytest.ini](pytest.ini): default testpaths are
`tests ptc ledger bench train`; `tokenizer_integration` is excluded by default.
The environment is not shipped in Git. The system interpreter may lack the
pinned `verifiers` dependency and fail during collection.
This is not an installation recipe or permission to fetch dependencies.

No GPU is required for the default suite. Two real-tokenizer controls require
separate explicit local-artifact admission; see the
[offline harness contract](spec/offline-harness-reliability.md).
The legacy `step2` suite is outside default collection and may contact Hugging Face.
No runtime tests were rerun for this documentation cleanup; archived suite
counts are dated receipts, not a claim about the current checkout.

## Repository map

| Path | Contents |
|---|---|
| [docs/](docs/) | Reports, evidence, preregistration, deviations and dated runbooks |
| [spec/](spec/) | Implementation contracts, protocols, spikes and handoffs |
| [research/](research/README.md) | Literature synthesis, deep research and verification receipts |
| [bench/](bench/) | BIRD task loading/scoring, comparisons, draw preparation and frontier controls |
| [ptc/](ptc/README.md) | Restricted PTC runtime, reporting and SQL lifecycle mechanics |
| [train/](train/) | Gated training integration, capture and skill mechanics |
| [src/cotrain/](src/cotrain/), [tests/](tests/) | Harness contract, adversarial non-solvers and gate tests |
| [ledger/](ledger/README.md) | Retired taskset, retained results and regression coverage |
| [step2/](step2/README.md) | Historical free-GPU smoke, [results](step2/results/README.md) and separate tests |
| Root `cotrain_*.py` | SDK plugin/runner entrypoints; intentionally remain at repository root |
| [process_watchdog.py](process_watchdog.py) | Shared bounded process-cleanup helper |
| [docs/readme-history.md](docs/readme-history.md) | Full pre-cleanup README with rebased navigation |

Tests also live beside their implementation in `ptc/`, `ledger/`, `bench/`
and `train/`. Root SDK entrypoints are not miscellaneous files to relocate.
The [project map](docs/project-map.md) expands workstream and workspace boundaries.

## Evidence and authorization boundaries

- A green check alone is insufficient: mutate the real target and confirm RED
  before trusting GREEN. `tests/leaky_env.py` is deliberately exploitable,
  a permanent red-team target that must never be hardened.
- Dated SQL acceptance receipts establish bounded engineering mechanics,
  not full adversarial/kernel acceptance, production readiness or model benefit.
  Overlapping test counts must not be added.
- Paid model trials require explicit authorization and budget. Native execution
  and training require their applicable authorization. Old 19/15-job permissions
  are consumed, never replayable; preflight-only preparation is not fresh consent.
- A clone lacks original scratch receipts. Report unavailable evidence honestly;
  do not fabricate it or upload local evidence as housekeeping.
- Historical GPU restrictions concern that stack, not a blanket impossibility
  of local MLX training. Separate worktrees and their evidence remain separate.

The [historical README](docs/readme-history.md) preserves all earlier framing,
installation snippets, mutation receipts, stack corrections and branch snapshots.
Those dated statements are historical context, not current execution instructions.
