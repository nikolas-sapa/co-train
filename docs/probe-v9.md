# Probe v9 — the first run that measured the policy

Run 2026-10-18/19 on free Kaggle T4, kernel clone `1796039` (contains #16, #17, #22), $0.
Output: `~/scratch/probe-v9/` (log, `probe_metrics.jsonl`). Header records the stack:
unsloth 2026.10.3, trl 1.13.0, transformers 4.57.6, torch 2.11.0+cu128. Config unchanged
from v8 except the generation fix: 800 prompts, G=8, per-device 8, accumulation 4,
`max_completion_length` 3072, `chat_template_kwargs={"enable_thinking": False}`.

## The generation fault is gone

| metric | v8 | v9 |
|---|---|---|
| `completions/clipped_ratio` | 1.000 | **0.000** |
| `completions/mean_length` | 3072.0 | **58.84** |
| `completions/mean_terminated_length` | 0.0 | **58.84** (= mean) |
| `completions/min` / `max_length` | 3072 / 3072 | **18 / 206** |
| `grad_norm` | 0.0 (exact) | **2.996e-06** |

Every completion terminated inside the cap, so `mask_truncated_completions` masked nothing.
`grad_norm` is non-zero for the first time in nine runs, which is the mechanical proof the
reward was actually called. PR #22 fixed the fault it was written for.

## What the model wrote

All four sampled completions are well-formed fenced SQL, correctly extracted, and **wrong**:

```
SELECT attribute_value FROM superhero WHERE superhero_name = 'Hulk';
```

`attribute_value` and `attribute_name` live on `hero_attribute` and `attribute`, not on
`superhero`, so the query errors. Executed against `superhero.sqlite` during v8's diagnosis,
the corrected join scores 1.0. This is a policy failure, not a format or generation fault:
the three diagnoses verdict.py separates are now distinguishable, and it picked "the policy".

## The abort, and what it licenses

```
PROBE ABORT
  - step 0: frac_reward_zero_std is 1.000, above the 0.6 ceiling
```

`per_device_train_batch_size=8`, `gradient_accumulation_steps=4`, G=8 → 32 sequences per
step = **4 prompts × 8 generations**. So the abort rests on four groups, one step.

The expected fraction of dead groups at G=8 is `p**8 + (1-p)**8`. The probability that all
four groups are dead by chance, if the true solve rate were `p`:

| true p | P(all 4 groups dead) |
|---|---|
| 0.25 | 0.000 |
| 0.15 | 0.006 |
| 0.10 | 0.034 |
| 0.05 | 0.194 |
| 0.02 | 0.524 |

**One dead step cannot separate p = 0 from p = 0.05.** At p = 0.05 there is a ~19% chance of
seeing exactly this; at p = 0.02 it is a coin flip. So v9 rules out a competent policy and
rules in a weak one, and it does not produce a solve-rate estimate. The honest sentence is
narrower than "0/8 solved": *four prompts produced four dead groups, which is consistent
with a solve rate at or below roughly 0.05 and not with anything above 0.15.*

## The question this leaves

The abort criterion is §282's "any step above the ceiling", and `GROUPS_PER_STEP = 4` was
chosen so the metric could reach five attainable levels and be comparable to 0.60. Those two
choices collide at step 0: the first unlucky batch ends the probe before a rate exists.

That is a design decision for the owner, not a lane's call, and three routes exist —
more groups per step (more attainable levels, slower), a warm-up that collects `k` steps
before adjudicating, or a taskset whose tasks sit higher on the policy's frontier. The
measurement they would replace is this one, so the choice should be made deliberately.

## Defects filed

One: the bare-string prompt (ledger row 26, fixed by #22). The generation fault that
produced v8 is closed and v9 is its evidence.
