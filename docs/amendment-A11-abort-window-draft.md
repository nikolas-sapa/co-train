# Amendment A11 — DRAFT, UNSIGNED

**This file is a draft for the owner's review. It is NOT part of
`docs/pre-registration.md`.** That file is append-only and owner-signed; nothing here has
been appended to it, and the signature line at the foot is deliberately blank.

Drafted in the voice and structure of A8 and A10 so that, if signed, it can be appended
with the numbering and wording intact. A10 is drafted and unappended; the next free number
above it is A11.

**What this amendment is.** It records that the spec carries two abort criteria for one
metric, that they conflict over the run lengths the probe actually uses, and that the
probe's live abort therefore implements one of them by default. It changes no ceiling, no
signed prediction, and no run that has already been reported. It asks the owner to sign a
**window of 3 consecutive breaching steps** as an opt-in alternative to the single-step
form, and to decide whether §240 and §282 are reworded to say which criterion governs a
probe. The spec is not edited here.

---

### A11 — 2026-10-19, BEFORE v10's numbers: the abort fires on a run of breaching steps, not on one, and the ceiling does not move

**This amendment amends the probe's abort criterion, and the discrepancy it records is
already in the spec.** `docs/spec-cotrain.md:282`, the dead-group probe's table, reads
**"> 0.60 on any step"**. `docs/spec-cotrain.md:245-251`, criterion A for a co-training
run, reads **"Abort above 0.60 sustained over 10 consecutive steps"**. Both are the same
metric, `frac_reward_zero_std`, and both name the same ceiling. One fires on a single
step; the other cannot fire in fewer than ten. For a probe whose whole stated shape is
"5-20 GRPO steps, aborting" (`docs/spec-cotrain.md:279`), the sustained form either never
fires (`--steps` below 10) or can fire only on the last step of a ten-step run, which is
not a stop but a report delivered after the work is finished. §282 governed by default,
and v9 followed it: the run ended at step 0.

**What v9 measured, and what it did not.** `docs/probe-v9.md:38-44`: the abort fired at
step 0 with `frac_reward_zero_std` 1.000 on four groups, which is 32 sequences at
`per_device_train_batch_size=8`, `gradient_accumulation_steps=4` and G=8. `docs/probe-v9.md:57-61`
states what one dead step licenses: a solve rate at or below roughly 0.05, not a rate. A
3-step window would not have measured one either. It would have continued the run far
enough to produce the five steps `train/verdict.py:69` (`MIN_PROBE_STEPS`) requires of its
own verdict, which is the internal inconsistency this amendment exists to remove: two
adjudicators over one run disagreed about how much evidence existed, and the live one
always won.

**The derivation, with its arithmetic shown.** The quantities below are computed at
G=8, `GROUPS_PER_STEP = 4` (`train/dead_group_probe.py:575`), and a binary exact-match
reward, which is what the probe runs (`train/dead_group_probe.py:729-732` names `exact`
as the reward for a self-contained task and `ex` for BIRD; both are 0/1).

- A group is dead when all eight of its generations score the same, so its probability is
  `d(p) = p^8 + (1-p)^8` (`train/dead_group_probe.py:105`).
- `frac_reward_zero_std` above 0.60 over four groups requires **at least three of the four
  to be dead**, because the metric takes only the values 0, 0.25, 0.50, 0.75 and 1.0
  (`train/dead_group_probe.py:537-539`). So the per-step breach probability is
  `S(p) = 4 d^3 (1-d) + d^4`.
- A window of `w` consecutive breaches, under the model in which steps are independent
  draws at a fixed `p`, fires with probability `S(p)^w`.

| true `p` | `d(p)` | `S(p)`, one step | `S(p)^3` | `S(p)^10` |
|---|---:|---:|---:|---:|
| 0.02 (hopeless) | 0.8508 | 0.892 | **0.708** | 0.317 |
| 0.062 (band's lower edge, rounded) | 0.599 | 0.474 | **0.107** | 0.00057 |
| 0.10 (weak tail) | 0.4305 | 0.216 | **0.010** | 2.2e-07 |
| 0.15 | 0.2725 | 0.064 | 0.0003 | 1.2e-12 |

**The row that matters is 0.062, and it is exactly on the ceiling.** The viable band's
lower edge is the root of `zero_advantage_fraction(p, 8) = 0.60`
(`train/dead_group_probe.py:142`), so at `p = 0.061857...` the expected dead fraction is
0.600, **on** the ceiling, not under it. A policy that is precisely viable therefore
breaches a single-step test 47.5% of the time (0.4739 on the exact band edge; the value
0.475 is the same quantity at `p = 0.062`, and both are the same fact). At `p = 0.10` it
breaches 21.6% of the time. Those are false aborts of a policy the probe exists to
certify, and the ceiling sits on the edge for the reason
`train/dead_group_probe.py:536-539` gives: four groups is the minimum at which the metric
can reach five levels and so range across a 0.60 threshold at all.

**Why the window and not a lower ceiling. This is the load-bearing choice of the
amendment.** The ceiling is **not changed**. Loosening it would be the wrong fix for three
separate reasons, each checkable:

1. **A higher ceiling would stop detecting a dead reward at all.** The metric has five
   attainable values. At `GROUPS_PER_STEP = 4`, any ceiling in (0.50, 0.75] fires only on
   a 0.75 draw, which needs four of four groups dead, the very event the criterion exists
   to catch. Moving 0.60 to 0.70 would not "reduce false aborts"; it would select the same
   event and call it tolerated.
2. **The 0.60 figure is derived from the metric's meaning, not chosen for the run.** It is
   the point above which most of the batch contributes no gradient
   (`train/verdict.py:62-64`, "assumed, and stated as assumed by the spec"). Raising it
   after an abort has been observed would be choosing the threshold after the result,
   which `docs/deviations.md:3-4` forbids in its own first paragraph.
3. **Loosening is silent; a window is visible.** A ceiling change alters what a number
   means. A window change alters how many observations a number must have, and it leaves
   the ceiling readable as the same ceiling.

**What a breach is, stated so the window cannot be read as a softening.** The criterion
is `value > 0.60`, strictly. The window is the number of *consecutive* steps that must
each breach before the run stops. At `w = 3` a single unlucky batch is recorded and the
run continues; three in a row stop it. Under the table above, a hopeless policy
(`p = 0.02`) still fires with probability **0.708** within three steps, so the window does
not let a dead reward through; it stops a live one from being killed by one draw. The
honest statement of the trade is in both directions and both are in the table: the window
buys a viable policy from 0.474 down to 0.107, and it costs the hopeless policy from 0.892
to 0.708.

**What the window costs, in wall clock.** v9's one logged step took **429.70 s**
(`~/scratch/probe-v9/probe_metrics.jsonl`, field `step_time`; a single step, so this is a
point estimate and not a distribution). The window can delay a stop by at most `w - 1`
steps beyond the first breach, so at `w = 3` it burns up to **two extra steps, about
14.3 minutes**, on a policy that would have stopped. `--steps 10` bounds the total at
**1.19 h** of training at that rate. Neither figure includes model download, setup, or
the Kaggle session's own overhead, and the probe's wall clock has deliberately been left
unmeasured beyond v9's one step (`HANDOFF.md:103-104`). The cost is real, bounded, and
paid only by the runs that were going to stop anyway.

**What it does not cost.** It does not change the ceiling, the reward, the taskset, the
group size, or any signed prediction. A run that breaches three times in a row stops with
a reason that names the span; a run that never breaches is untouched.

**The default stays 1, and the window is opt-in.** `ABORT_WINDOW = 1`
(`train/dead_group_probe.py:70`) and `criterion_a_any_step(..., window: int = 1)`
(`train/verdict.py:119`) are §282 verbatim, and this amendment does not move either. The
window is passed explicitly, per run, as `--abort-window` (`train/dead_group_probe.py:747`)
and is threaded into the same function the after-the-fact verdict reads
(`train/dead_group_probe.py:850`, `train/test_train.py` "the live monitor and the verdict
apply the same window"), so the stop and the re-read cannot disagree. A window of 1 is the
signed default; anything larger is a declared power choice for a named run.

**Where the window is recorded, and where it is not yet.** `ABORT_WINDOW`'s own docstring
(`train/dead_group_probe.py:70-79`) says the value is "recorded in the header", and
`--abort-window`'s help text (`train/dead_group_probe.py:747-756`) says the same. **It is
not, as of `f3565eb`.** The header call at
`train/dead_group_probe.py:851-865` passes `probe`, `taskset_id`, `prompts`, `config`,
`expectations`, `resolved_stack` and `completion_sampling`; none of those carries
`abort_window`, and `probe_expectations` (`train/dead_group_probe.py:645`) emits a fixed
description of the form (`:654`) rather than the run's value. The v9 header in
`~/scratch/probe-v9/probe_metrics.jsonl` confirms it: no such key. **This amendment
requires the window in the metrics header before an opt-in run is read**, and until that
key exists a window-3 file and a window-1 file are indistinguishable after the fact. This
is stated as a defect rather than left as a dependency, because a rule whose value is not
recorded cannot be honoured after the run that used it.

**What would falsify the choice.** A run of forty groups whose **pooled** dead-group rate
contradicts its step-0 reading. At forty groups the pooled rate has a standard error of
about `sqrt(0.25/40) = 0.079` under `p = 0.5`, and at most 0.079 anywhere, so it resolves
a step-level reading to roughly ±15 percentage points at 95%. If a run's step 0 reads
above the ceiling and the pooled rate across all forty groups lands well below the
band, or the reverse, a step 0 under the ceiling followed by a pooled rate that sits
above it, then the step is not a noisy draw from the same policy, the independence
assumption under the table is wrong for this probe, and the window's arithmetic is not
about this run. **No file derives a threshold for "contradicts", and this draft does not
invent one.** The natural next step, if the owner wants it sharp, is a pre-registered
statistic on the pooled rate; it is not stated here as though it existed.

**Not measured, and named so it is not read as measured:**

- **Whether steps are independent at a fixed `p`.** The table treats each step as a fresh
  draw, which is the assumption `frac_reward_zero_std`'s own derivation makes. GRPO
  changes the policy between steps, so `p` drifts and consecutive breaches are positively
  correlated in any run that is actually training. Positive correlation raises `S(p)^3`
  above the tabulated value for the same marginal `p`. **No run has measured the
  autocorrelation of `frac_reward_zero_std`, and none of the numbers above is a forecast
  of a trained run's sequence.**
- **The per-step wall clock.** 429.70 s is one step of one run on one T4, before any
  warm-up term. It is used above as a point estimate and is not a distribution.
- **Whether 3 is the right window.** 3 is the smallest value at which the viable-policy
  false-abort rate falls below 0.11 at G=8 and four groups; 10 is what §240 says and loses
  the hopeless-policy detection rate to 0.317. The choice of 3 is argued from the table,
  not demonstrated by a run.

**What this amendment does NOT license:**

- **It does not make the ceiling negotiable.** Every run still reports `frac_reward_zero_std`
  against 0.60. A window-3 run that breaches is a run with a dead reward and a slower
  stop, not a run that passed.
- **It does not change the sustained criterion for a co-training run.** §240's form
  (`train/verdict.py:185`, `criterion_a_sustained`) remains what governs a run long enough
  for ten steps to be evidence. A probe is not that run.
- **It does not produce a solve rate from v9.** v9's four groups are four groups. The
  amendment removes a false-stop mode; it adds no observations to a run already ended.
- **It does not reword the spec.** The discrepancy between `docs/spec-cotrain.md:247-248`
  and `docs/spec-cotrain.md:282` is recorded here and left for the owner. Whether the probe
  table is reworded to name its own form, or §240 is scoped explicitly to runs of ten or
  more steps, is a spec decision this draft does not take.

## What this still does not fix

A window of any finite length is a test on a metric that takes five values per step; it
buys power against step noise, not against a group size too small to resolve the policy.
The probe's underlying question, whether a 0.6B policy's binary reward separates on this
taskset, is still answered by its realised `p`, and a window delays that answer rather
than improving it. The instrument that removes the single-step problem for good is more
groups per step, which costs batch memory and slows every step, and `MIN_GROUPS_PER_STEP`
(`train/dead_group_probe.py:574`) already records why 4 is the floor rather than a
preference.

---

**Owner signature:** ______________________  **Date:** ____________

*Unsigned. No amendment signature is claimed and none is implied. v10, which runs
`--steps 10` with `--abort-window 3` (`f3565eb`), is the first run this draft describes;
no number from it is quoted here.*
