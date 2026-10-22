# Probe v10: three steps, some successful rewards, ABORT

Evidence reconciled on 2026-10-22. The run existed before this audit; this is not a
new GPU run. Its original metrics and kernel log remain unchanged.

## What ran

The companion log records `--steps 10 --abort-window 3`. The metrics header records
G=8, 32 sequences per step, execution reward, taskset
`bird-dev-sql-shippable-seed0`, and the resolved stack:

| Package | Version |
|---|---|
| unsloth | 2026.10.3 |
| trl | 1.13.0 |
| transformers | 4.57.6 |
| torch | 2.11.0+cu128 |

Ten steps were requested. Three were recorded:

| Recorded step, zero-based | Dead-group fraction | Mean reward | Gradient norm | Step seconds |
|---|---:|---:|---:|---:|
| 0 | 1.00 | 0.00000 | 3.0050e-06 | 400.146 |
| 1 | 1.00 | 0.00000 | 4.1971e-08 | 250.818 |
| 2 | 0.75 | 0.34375 | 0.413225 | 18.131 |

`completions/clipped_ratio` is zero on all three steps. There are four stored
completion samples per step, twelve samples in total. Those samples are not the
whole batch.

The third step has a nonzero execution reward and reward standard deviation.
The run therefore does not support "the reward was uniformly zero." It also does
not establish per-task solve rates, an eligible frontier taskset, or a training
gain. These are training-time aggregates from a changing policy.

## Re-read verdict

Executed from the repo checkout, using the existing project interpreter:

```sh
PY=/Users/nikolassapalidis/Developer/misc/co-train/.venv-ptc/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" train/verdict.py \
  /Users/nikolassapalidis/scratch/probe-v10/probe_metrics.jsonl \
  --abort-window 3
```

Exit 1, `PROBE ABORT`:

- Only three training steps are present; the verdict requires at least five.
- Steps 0 through 2 each exceed the strict 0.60 ceiling, filling the three-step
  consecutive-breach window.

The historical header omits `abort_window`. Window 3 comes from the command in
the companion log; it must be supplied explicitly when re-reading this artifact.
The current producer records the window, but that does not repair old headers.

Two printed observations need qualification:

- The verdict's default reference is G=4, while this artifact records G=8. Its
  printed 0.397 expected dead fraction is therefore not a G=8 baseline. The
  artifact's own header stores 0.156548 for its reference policy at G=8. Neither
  reference is a measured solve rate for this policy.
- `sampling/sampling_logp_difference/mean` is absent on every step. The associated
  criterion cannot be evaluated from this artifact. Missing is not zero, and an
  ABORT must not be promoted to PASS by filling it.

## Independent offline check of the shipped tasks

The exact `bench/probe_prompts_sql.jsonl` was matched against the existing local
BIRD metadata and database files on 2026-10-22:

- 800 rows, 800 unique task IDs.
- Every database ID, gold SQL string and resolved database path matched.
- All seven expected databases were present.
- `bench.score.validate_golds` executed all 800 golds with a 30-second cooperative
  SQLite deadline and a 500,000-row cap: **zero defective golds**.

Databases: `california_schools`, `debit_card_specializing`, `formula_1`,
`student_club`, `superhero`, `thrombosis_prediction`, `toxicology`.

Corpus root:
`/Users/nikolassapalidis/scratch/bird-sql/bird-dev-extracted/dev_20240627`.
The machine-readable result is
`/Users/nikolassapalidis/scratch/co-train-research-2026-10-22/shipped-gold-validation.json`.

This check does not establish that the historical Kaggle upload contained
byte-identical databases. It does not validate prompt/schema wording, exclude
pretraining contamination, or measure model accuracy. It does rule out defective
gold execution in the exact 800 shipped references against these local files,
under the stated limits.

## Provenance and limits

Original local artifacts:

| Artifact | SHA-256 |
|---|---|
| `~/scratch/probe-v10/probe_metrics.jsonl` | `789f24a26cde1470acf1daca8bac57db12517d44db5516477c304f02ddc9f90d` |
| `~/scratch/probe-v10/cotrain-dead-group-probe.log` | `74290a85e00597632fbcb5b7dcd19f4f891b61e4cf7a6c235b6c8d5410a20d76` |

The header lacks a model revision, code commit, input content hashes and database
hashes. The companion log establishes the requested window, not those missing
identities. No retrospective values have been inserted. These artifacts are
local, not archived in this repository.

The log reports two allocated T4s but one device used by the trainer. Allocation
does not establish peak VRAM. The three observed step times are not a forecast
for another run.

## What this changes next

Another longer GRPO probe is not yet justified by a missing v10 result: the result
exists and is ABORT. A frozen-policy, per-task measurement would answer the still
missing frontier question more directly; its exact channel, G, sampling budget
and authorization need to be fixed before execution.

A11 remains an unsigned draft. Its claim that a window of three would ensure the
five-step minimum is contradicted by this run. Its probability and stopping-delay
claims also need correction before signature. No signed text was changed.

`python -m train.grpo_ptc --preflight-only` was executed and exits 1 with
`PreconditionUnmet`: `bench/frontier/manifest.json` is absent. Even beyond that
gate, `train/grpo_ptc.py` deliberately ends in `NotImplementedError`; the
co-training loop is not a runnable implementation hidden behind a missing file.
Do not fabricate a manifest to bypass either problem.
