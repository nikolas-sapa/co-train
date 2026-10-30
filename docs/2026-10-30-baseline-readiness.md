# Stage-5 readiness: BIRD paired untrained baseline

2026-10-30. SWE-2 source-readiness draft, reviewed and condensed against
`1541fed`, with main-integration consistency checked against `2f1a627`.
Preparation only, not a signed protocol or measurement.
Stage 4 remains the first priority; baseline preparation can proceed alongside it.

## 1. Existing pieces

- [BIRD loader](../bench/loader.py): `load_bird(root, require_db=True)` returns
  `SqlTask`; unavailable corpus/databases fail closed. A8 specifies BIRD dev.
- [Suite](../bench/suite.py): seeded, shape-stratified `select()` and inventory
  `report()`. [Scorer](../bench/score.py): SQL extraction, execution accuracy
  (`compare="set"`, 30-second deadline, 500,000-row cap) and `validate_golds()`.
- [Arm pair](../ptc/sql_arms.py): `build_sql_arms()` shares task information and
  budgets across bash/PTC. Opt-in [reporting](2026-10-30-agent-defect-escalation.md)
  now exists in the in-process PTC catalog and host shell, not the isolated wire.
- [Paired adjudication](../ptc/paired.py): rollout parsing, error/void handling
  and matched task sets. Its two-bucket tier split collapses BIRD's three tiers,
  as already disclosed in [the taskset contract](bench-taskset.md).
- [Frontier library](../bench/frontier/probe.py): `probe(tasks, generate, policy=...)`
  measures per-task rates using an injected generator; `write_manifest()` emits
  a nonempty measured frontier. This is not a ready model-backed CLI.
- [Training gate](../train/guards.py): checks manifest measurements, matching G,
  retention and signed amendment. Minimum task count is derived as 59.
  [A8](pre-registration.md) is signed; absence of a new signature is not the gap.

## 2. Missing evidence and wiring

- `bench/frontier/manifest.json` is absent, intentionally. Do not fabricate it.
- No eligible per-task frontier rates are supplied by the historical
  [v9](probe-v9.md)/[v10](probe-v10.md) dead-group aggregates. V10 aborted;
  changing-policy training rewards are not a frozen-policy baseline.
- [Comparison CLI](../ptc/compare.py) exposes only `glossary` and `ledger`.
  A current BIRD paired baseline needs runner integration and real rollouts.
- The exact selected suite needs disclosed valid-gold/exclusion decisions
  before model calls. V10's historical 800-gold check is not a new draw's proof.
- Freeze and record model/checkpoint identity, generation settings and runtime.
  A8 names `unsloth/Qwen3-0.6B` for frontier measurement; the gate's nonempty
  `policy` string check alone does not authenticate those weights.

## 3. Smallest offline increment

1. Fix and record seed, per-tier counts and draw settings using existing
   `bench.suite.select`; retain the complete planned task-ID list.
2. Run `validate_golds()` on that exact suite under recorded scorer bounds.
   Disclose rejected IDs/reasons separately from policy failures; invalid gold
   is not a zero score. Preserve the draw and exclusion ledger.
3. Emit draw provenance and validation results for the frontier and paired-arm
   runners to consume. Pin source/settings and database identity before calls.

This is proposed preparation, not an executed draw or validation. No local
corpus availability or database contents were checked by this note.

## 4. Compute and authorization boundary

Real frontier measurements require a generation adapter and explicit session
authorization for samples across the fixed draw. The existing
[Kaggle entrypoint](../train/kaggle/probe.py) launches the dead-group probe,
not a completed frontier runner. Free compute is not automatic authorization.
Paid providers, relay calls, training, downloads and native jobs remain outside
this note's authority. Write a manifest only from real, reviewed measurements;
a signed amendment does not turn synthetic rates into evidence.

## 5. Decisions to record before an experiment

- Choose the paired baseline's policy and runtime explicitly. Retired relay
  results do not select or authorize the new instrument.
- Match measurement G to planned training G. Historical Kaggle probe G=8 and
  committed dead-group default G=4 are different configurations.
- Main's [frontier consistency contract](../spec/frontier-measurement-consistency.md)
  uses count-only admission (currently 59 tasks) and truthful retention metadata.
  Band width is diagnostic, not an additional retention floor. Preserve this
  existing policy and the declared tier-collapse limitation.

## 6. Non-goals

No fabricated manifest, solve rates or baseline result; no relaxed gate or
protocol amendment. No reopening the retired `ledger` result, no learning,
savings or completed-stage claim. No model, database query, experiment,
install/download or Git action was performed by the SWE-2 drafting worker.
