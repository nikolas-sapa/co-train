# `train/` — the dead-group probe, and a pipeline that will not run yet

Two deliverables at deliberately different maturity levels, because
`docs/spec-cotrain.md` authorises exactly one of them.

| | status |
|---|---|
| **the dead-group probe** (§270-298) | finished and runnable. Needs no working benchmark, aborts in 5-20 steps |
| **the GRPO pipeline** (§156-240) | code, with its guards live and its gate **shut**. `preflight()` raises today |

The spec is explicit that the pipeline must not be built first (§328-342): a
mis-built pipeline announces itself as *"no training effect"*, and a benchmark
that cannot show a training effect even when the pipeline is correct produces the
same output. Broken and working become indistinguishable. So the pipeline lands
as code whose guards are tested and whose precondition check fails loudly, and
nothing here launches a training run.

## Files

| file | what |
|---|---|
| `guards.py` | the version floor, the spec's three invariants, the §344 gate. Pure stdlib |
| `dead_group_probe.py` | the derivation, the reward, the live abort, the probe's `main()` |
| `verdict.py` | no-GPU PASS/ABORT over a metrics JSONL. Both abort criteria |
| `grpo_ptc.py` | the gated pipeline: config, environment, `preflight()` |
| `test_train.py` | 111 offline tests. No GPU, no network, no model download |
| `mutate.py` | 52 mutants that break each guard, and the record that each one dies |

## Run order

```bash
# 1. adjudication, invariants and derivations — laptop, no GPU
.venv-ptc/bin/python -m pytest train -q
.venv-ptc/bin/python train/mutate.py               # 52 mutants, 0 survivors

# 2. the probe's config and expectations, without spending anything
.venv-ptc/bin/python train/dead_group_probe.py \
    --prompts PROMPTS.jsonl --taskset-id WHAT_THOSE_PROMPTS_ARE --dry-run

# 3. the probe itself — free Kaggle T4, accelerator NvidiaTeslaT4
pip install "unsloth>=2026.10.3" "trl==1.13.0" "transformers<5"
python train/dead_group_probe.py \
    --prompts PROMPTS.jsonl --taskset-id WHAT_THOSE_PROMPTS_ARE \
    --steps 5 --out probe_metrics.jsonl

# 4. re-check the saved run with no GPU
python train/verdict.py probe_metrics.jsonl           # the probe: any-step ceiling
python train/verdict.py run_metrics.jsonl --run       # a run: sustained A, plus B
```

`--steps 5` on the first launch, not 20. Five steps is the minimum that
`verdict.py` will adjudicate, it answers the probe's question, and it measures
the one number the whole feasibility argument rests on and nobody has taken —
see *Cost* below.

Download `probe_metrics.jsonl` **immediately**. Kaggle's "Restart session"
discards the pip install *and* wipes `/kaggle/working`; that is how Step 2's
first-party metrics file was lost (`step2/KAGGLE.md`).

## What the probe decides

> Does a binary reward produce usable groups against a 0.6B policy?

Under a 0/1 reward a group yields zero advantage whenever all `G` rollouts
agree, which is a Bernoulli coincidence: `p**G + (1-p)**G`. At G=4 and the only
measured solve rate available (23/29, run 3d) that is **0.397**, and TRL already
logs the realised value as `frac_reward_zero_std`. Above **0.60 on any step** the
probe stops: most of the batch yields no gradient, and no taskset fixes a reward
that cannot separate.

The expectation is a loan, not a measurement. 23/29 is `deepseek-v4-flash`'s, and
the policy that has to realise it is Qwen3-0.6B. Both tails degenerate — at G=8,
p=0.1 gives 43% dead groups against 15.7% at p=0.79 — so a *weak* policy is
worse than a strong one, and Qwen3-0.6B is the weak case. Restated as an
interval, the probe is a test of whether the realised solve rate falls outside
**(0.120, 0.880)**, which is also where the spec's exclusion of G=2 comes from:
0.793 sits outside G=2's narrower band.

**A probe result is not quotable without its taskset.** `--taskset-id` is
mandatory, it is written into the metrics header, and `verdict.py` refuses a file
that lacks it. The realised fraction is a property of (policy, taskset, G)
jointly; this repo has already shipped a real number attached to the wrong
denominator.

## Cost

**$0.** Free Kaggle T4, the same shape as the Step 2 smoke run, which fits one
card at 12.59 GB peak.

**Wall-clock: unknown, and that is itself one of the things the probe measures.**
Install is 15-20 minutes (`step2/KAGGLE.md`). Per-step time is the spec's open
question §322: the only measured generation figure is Step 2's 3.2 tokens/sec
whole-loop at `use_vllm=False`, where one GRPO step at this cap would take over
an hour and free hardware is out. With vLLM it should be minutes. Nobody has
taken the number. So run five steps, read the step time off the log, and decide
about twenty from data rather than from this paragraph.

## What is blocked, and on what

The pipeline waits on spec §344: **a taskset whose tasks sit near a 0.6B model's
frontier**. `ledger` fails this on two counts — the cheap tier's shape count is a
record-schema ceiling, and run 3d scored an exact 23/23 tie — so no value of n or
G rescues it.

`guards.frontier_taskset_status()` is that requirement as a check. It wants
`bench/frontier/manifest.json`:

```json
{
  "policy": "unsloth/Qwen3-0.6B",
  "pre_registration_amendment": "A8",
  "n_tasks": 198,
  "solve_rate_min": 0.2,
  "solve_rate_max": 0.8
}
```

and it refuses, naming each fault: a missing key, a band end at 0 or 1, a band
end whose own zero-advantage fraction exceeds the abort ceiling, a policy field
that does not say which model the rates were measured on, or an amendment id
with no `signed` heading in `docs/pre-registration.md`. **That path and schema
are this lane's declared contract and need reconciling with whoever builds the
taskset.** The gate fails closed either way.

The probe is **not** gated on any of this. It measures the reward's geometry, not
the model's competence.

## Red before green

A green test proves nothing until it has been seen red, so `mutate.py` breaks
each guard in a fresh copy of the tree and records which test dies:

```
baseline: 111 passed
52 mutants, survivors: none
```

Two mutants survived the first pass, and both were real:

- **`gate: missing manifest keys ignored`** — the gate still refused a
  key-less manifest, via its *other* checks, so nothing asserted that the
  operator is told *which* key to add. Fixed by
  `test_every_required_manifest_key_is_named_when_absent`.
- **`A: never-logged metric not reported`** — `criterion_a_any_step` carried an
  aggregate "never logged" line after a loop that already failed per step, so no
  input could reach it. Deleted. `criterion_a_sustained` keeps its equivalent,
  because there the loop alone returns clean on an absent metric, and the mutant
  aimed at that one dies.

## Conventions

Numbers are derived, never typed in: the spec's published percentages appear only
as a derivation's *expected output*, so a changed derivation fails rather than
agreeing with itself (the `tests/test_defect_ledger.py` pattern). Invariant
values that live in another file — `PTCHarnessConfig.max_turns`,
`ptc.metrics.FAILURE_PREFIXES`, `MIN_CALLS_FOR_PERFECT_RATE`, `ptc.harness.TOOLS`
— are parsed out of that file rather than copied, so the trained arm cannot
quietly diverge from the eval arm.

Guards `raise` rather than `assert`, although the spec writes them as one-line
asserts: `python -O` deletes `assert` statements, and a guard an interpreter flag
can remove is not a guard. `InvariantViolation` subclasses `AssertionError`, so
the spec's semantics survive.

Design notes, the §240-vs-§282 discrepancy and the open decisions are in
`docs/train-notes.md`.
