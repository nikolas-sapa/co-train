# Training-lane notes

2026-10-11. Design decisions, the discrepancies found while implementing
`docs/spec-cotrain.md`, and what is waiting on the owner. Operating instructions
live in `train/README.md`; this file is the record of what had to be judged.

Nothing here has run on a GPU. The probe is runnable and has not been run.

## The abort threshold is stated twice, and the two statements are different tests

The spec gives criterion A in two places with two different forms:

| where | form |
|---|---|
| §240, "Two abort criteria", for a co-training run | `frac_reward_zero_std` > 0.60 **sustained over 10 consecutive steps** |
| §282, the dead-group probe's table | > 0.60 **on any step** |

**Implemented: both, separately named, neither standing in for the other.**

- `verdict.criterion_a_any_step` is §282's form and is what `probe_verdict` uses,
  because the probe is what §282 describes.
- `verdict.criterion_a_sustained` is §240's form and is what `run_verdict` uses.
- `dead_group_probe.ProbeMonitor` aborts live on the any-step form, matching the
  probe table's "Stop; do not continue to a training run".

`test_criterion_a_any_step_and_sustained_are_different_tests` pins the gap with a
single-step spike, which aborts under one and passes under the other.

**The most likely reading is that this is not a contradiction**: a 5-20 step
probe cannot host a 10-step sustained window at all (a 5-step probe has no room
for one), so the any-step form is the only form available to it, and the
sustained form belongs to a 200-step run where a single spike is noise. But the
spec does not say that, both numbers are flagged `(assumed)` in it, and resolving
it is an edit to the spec — which this lane does not own. Flagged, not chosen.

**Consequence if the generous reading is wrong:** the probe is the stricter
instrument, so it can abort on a spike that a run would ride out. That direction
is the cheap error: it costs one wasted free-tier session and `verdict.py` can
re-adjudicate the saved JSONL under either criterion with no GPU.

## Criterion B detects direction, not size

§253-270's two arms are a monotonic rise over 10 consecutive logged steps, or a
mean above 3x its own first-10-step median. Both are about *change*, because the
paper's mechanism is a growing mismatch; there is deliberately no absolute-level
test, since "a flat elevated value is a calibration offset, not this signal".

Two properties worth knowing before reading an abort:

- **A monotone abort says nothing about magnitude.** Ten consecutive steps rising
  by 0.1% each trip it exactly as hard as ten doublings. That is the criterion as
  written and the mechanism as published; it is not a bug, but an abort should be
  read alongside the realised values rather than on its own.
- **False positives from noise are negligible.** Under exchangeable noise the
  probability of 10 consecutive strictly increasing values is 1/10! ≈ 2.8e-7 per
  window, so a monotone run is signal rather than luck.

**The ratio arm is reported as *not evaluable*, never silently skipped, when the
baseline median is not positive.** `logps_diff` can sit at or below zero, and
`3 x` a non-positive baseline is a *smaller* number, so the comparison would
quietly invert into a guard that can never fire. That is the shape this repo
keeps finding, so it is declared out loud instead.

**Criterion B has only ever passed, and the spec says that is not evidence.** Its
test is a GPU experiment this lane did not run: generate in bf16 while training
in fp16, where the paper's measurement says the mismatch grows ~24x, so the
logged mean must move by a large visible factor. If it does not move, the metric
is not wired to anything. One five-step run, the same shape as the probe.
Toggling `vllm_importance_sampling_correction` is **not** a valid test — it
changes the clipping, not the logged difference. `criterion_b` prints this as a
standing note on every verdict so that a green B is never read as a tested B.

## The three invariants, and the one thing that changed about them

Implemented as described in §156, with one deliberate deviation: they `raise`
rather than `assert`. `python -O` deletes `assert` statements, and a guard an
interpreter flag can remove is not a guard. `InvariantViolation` subclasses
`AssertionError`, so the spec's semantics are preserved while the statement stops
depending on `__debug__`.

**1. One registered tool.** `assert_one_tool` checks both the count and that the
one tool is `run_program`, and `test_the_trained_arm_registers_the_same_single_tool_as_the_eval_arm`
parses `ptc/harness.py`'s own `TOOLS` and asserts the trained arm's schema is
identical to it. The two arms therefore cannot drift into offering different
tools, which is the failure H4 would reward rather than catch.

**2. One cap per experiment.** The spec's instruction was to make the condition
structurally inseparable from the value, so there is no module-level `3072` or
`4258` anywhere in `train/` — `test_neither_cap_exists_as_a_bare_number` asserts
that by inspecting each module's integer attributes. `completion_cap(arms)` is
the only constructor and `assert_cap(cap, arms)` the only way to use one; a cap
built for `{"ptc"}` raises when passed into a two-arm run.

The two values come from two different rules, because they answer different
questions: a single-arm cap only has to not truncate its own arm (PTC's 2,642
rounded up to the next 1,024 → 3,072), while a cross-arm cap is a validity
constraint and must be *exactly* the global observed max (4,258) or each arm's
tail is masked at a different rate. **The 1,024 granularity is reconstructed, not
stated by the spec**, which gives 3,072 and says only "because PTC's observed max
is 2,642". The load-bearing property is the inequality, and that is asserted; the
granularity constant only reproduces the published figure from the measurement,
and is flagged as a reconstruction in the source.

**3. `max_turns` reaches the trained arm.** `eval_max_turns()` parses the default
out of `ptc/harness.py` rather than restating `8`, so the trained arm cannot get
a different budget from the measured one. `TurnBudget` is the per-rollout state
(trl's `_tool_call_loop` has no turn limit of its own and `tool_call_count` is a
logging counter), and exhaustion returns a refusal the model reads.

## Open decision: should turn exhaustion count as a tool failure?

The refusal `TurnBudget` returns is deliberately **not** prefixed with one of
`ptc.metrics.FAILURE_PREFIXES`, and `assert_turn_budget` fires if it ever is.

The reasoning: a turn-budget refusal is a harness event, not a rejected program.
Prefixing it would fold mode-3 turn exhaustion into H4's `tool_success_rate`,
where §238 says H4's response is sign-indeterminate and the remedy is to "log
turn counts separately from H4" — so `PTCEnvironment.turns_used` is reported
separately.

**The spec does not say which way this goes, and it is a measurement decision.**
The alternative reading is that a refusal the model reads is exactly what
`_is_failure` was built to count, and excluding it under-reports. The guard is
written so that reversing the decision is one assertion and one string, not a
search through the pipeline. Owner's call.

## Why the frontier gate checks what it checks

§344's requirement is a taskset whose tasks sit near a 0.6B model's frontier.
Expressed as a check, that is a *band*, not a count: a 0/1 reward needs tasks the
policy sometimes solves, and saturation (p→1) and uniform failure (p→0) both
produce zero-advantage groups. So the manifest must declare a measured
`solve_rate_min`/`max`, both strictly inside (0, 1), **and** both ends must clear
the probe's own abort ceiling under `zero_advantage_fraction` — the gate calls
the probe's derivation rather than restating a threshold. A band end at 0.05
reads 0.815 dead groups at G=4 and is refused as dead on arrival.

Two further requirements, each from a fault this repo has already had:

- **`policy`** must say which model the rates were measured on. The number that
  sets every expectation in the spec is `deepseek-v4-flash`'s, and the policy
  being trained is Qwen3-0.6B. A band measured on the wrong model is not evidence
  about this one.
- **`pre_registration_amendment`** must name an amendment that carries a `signed`
  heading in `docs/pre-registration.md`. A taskset change is a change to the
  instrument, and A5 committed that such a change "needs its own pre-registration
  before any run on this taskset is reported as evidence". The gate reads that
  file and never writes it.

`bench/frontier/manifest.json` and this schema are **this lane's declared
contract** and need reconciling with whoever builds the taskset. The gate fails
closed on anything it does not recognise, so a mismatch is loud rather than
permissive.

## Stack facts encoded as guards

- **`unsloth >= 2026.10.3` fails, it does not warn.** Below the floor unsloth
  pins `trl<=0.24.0`, where `rollout_func`, `self.tools`, `environment_factory`
  and `tool_mask` are all at zero occurrences — not a degraded run, a different
  experiment. The comparison is on parsed version tuples, never strings:
  `"2026.9.12" > "2026.10.3"` is **true** as a string, and 2026.9.12 is the
  version this project actually ran, so a string compare waves through exactly
  the case the floor exists for. `test_the_floor_is_compared_as_a_version_not_a_string`
  asserts both halves.
- **`trl == 1.13.0` is pinned explicitly**, because nothing else in the stack
  constrains it: trl 1.13.0 needs only `transformers>=4.56.2`, so
  `transformers<5` leaves the resolver free inside unsloth's whole range.
- **`vllm_mode="colocate"` is written out in both configs**, because the default
  flips inside the version range this project has used — `"colocate"` at 1.13.0,
  `"server"` at 0.24.0, and server mode brings a two-device requirement. Same
  source, different topology, no error.
- **fp16 is set explicitly and bf16 explicitly false**, as a decision rather than
  a T4 workaround: arXiv:2510.26788 measures bf16's training-inference mismatch
  at ~24x fp16's, worsening with response length, and this project's rollouts are
  p95 2,560 tokens over 6.38 turns. On future Ampere, bf16 is a downgrade to be
  tested, never a default upgrade.

**`gpu_memory_utilization=0.7` is carried forward unchanged and remains the
spec's open question §361:** whether vLLM computes it against total or free VRAM
when the trainer already holds 1.39 GB. If total, the 12.59 GB peak stands; if
free, the real allocation is larger than the derivation assumes and it needs
lowering. The probe's first run on hardware settles it, and the dry run prints
the value so it is visible before launch rather than after an OOM.

## What `grpo_ptc.py` does not contain

The trainer call shapes (`FastLanguageModel.from_pretrained`, `GRPOConfig`,
`environment_factory`) are read from library source and **have never been
executed**; whether Unsloth's fp16-on-Turing work still applies at trl 1.13.0 is
the spec's own largest unverified assumption (§51). So `main()` does not load a
model and then refuse — `preflight()` refuses first, for free, and the line after
it raises `NotImplementedError` so that removing the gate cannot silently produce
a run.

`PTCEnvironment.step` spends a turn and then raises rather than returning a
plausible string, for the same reason: a stub that returned program output would
make an empty or flipped pipeline look like a working one, which is the one
failure mode the whole spec is organised around.

## Needs the owner

1. **The probe launch.** $0 on free Kaggle, wall-clock unknown (§322, the number
   the feasibility argument rests on). Command in `train/README.md`. It decides
   whether a binary exact-match reward is viable at all.
2. **Which prompts the probe runs against**, and therefore what its answer is
   about. `--taskset-id` is mandatory and recorded, but the choice is a
   measurement decision: `ledger` is where the 23/29 reference came from, and it
   is also the taskset §344 says is unfit for training.
3. **Turn exhaustion and H4** — the open decision above.
4. **Criterion B's falsification run**, one five-step bf16-generation run, not
   taken.
5. **The main run** ($6.29 / 13.2 h) is not implied by any of this. The pipeline
   is gated and the gate is shut.
