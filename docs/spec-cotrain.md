# Spec — co-training the PTC arm

2026-10-10. **This is a spec, not authorisation to build.** Nothing here has run on a
GPU. It exists because the stack question was settled today and the findings are
perishable: the TRL ceiling that blocked this moved two days ago, and three ways a
built pipeline would silently measure the wrong thing were found while establishing
that. Every number below carries whether it is **measured**, **derived** or
**assumed**.

The eval, not the pipeline, is the blocker. See *Non-goals*.

## Result

| Question | Verdict |
|---|---|
| Can the proven stack co-train at all? | **Yes, as of 2026-10-08** — Unsloth's TRL ceiling lifted to `<=1.13.0` |
| Does it need two GPUs? | **No** — one 16 GB T4, vLLM colocate + Standby, 12.59 GB peak |
| Is fp16 a T4 workaround? | **No** — it is the correct choice for GRPO on any hardware |
| Is there anything to train against? | **No** — `ledger` cannot show a training effect; this spec is blocked on that |

## The stack, with the dated reason

```
unsloth==2026.10.3        trl==1.13.0        transformers<5        fp16
```

- **unsloth 2026.9.12** — the version the Step 2 run used — declares
  `trl!=0.19.0,<=0.24.0,>=0.18.2`. **That was the wall, and it was real when the
  project hit it.** At trl 0.24.0 every seam co-training needs is at *zero*
  occurrences in `grpo_trainer.py`: `rollout_func` 0, `self.tools` 0,
  `environment_factory` 0, `tool_mask` 0. Its `__init__` takes ten parameters and
  none is an entry point for externally-driven rollouts. (Measured, read at tag.)
- **unsloth 2026.10.3**, released 2026-10-08, declares
  `trl!=0.19.0,<=1.13.0,>=0.18.2` — unconditional, no environment marker.
  `unsloth_zoo 2026.10.3` matches, with a marker that applies on Linux. (Measured,
  PyPI metadata.)
- **trl 1.13.0** has `environment_factory` 19, `get_reward` 15, `tool_mask` 27,
  `rollout_func` 13. `vllm_mode` **defaults to `"colocate"`** here; it defaulted to
  `"server"` at 0.24, which is where the "two separate CUDA devices" requirement
  came from. (Measured.)
- **`transformers<5`** remains load-bearing for the Step 2 reproduction and is
  carried forward; trl 1.13.0 needs only `transformers>=4.56.2`, so it does **not**
  constrain the TRL version. Pin TRL explicitly. (Measured.)
- **UNKNOWN:** whether Unsloth's fp16-on-Turing work still applies at trl 1.13.0.
  Declared-compatible, never run. **This is the single largest unverified
  assumption in this document.**

## fp16 is a decision, not a constraint

Qi et al., *"Defeating the Training-Inference Mismatch via FP16"*,
**arXiv:2510.26788**. The mismatch is not intrinsic to ratio arithmetic — it is a
disagreement between two engines computing the same function of the same weights,
where kernel fusion, reduction order and parallelism produce different rounding.
bf16's 7 mantissa bits (grid spacing ~0.78% near 1.0 against fp16's ~0.098%) make
that disagreement large enough to bias the gradient: **bf16's mismatch measures ~24x
fp16's.** bf16's range advantage does not pay in RL, which starts from pretrained
weights whose scale is already fixed.

**This project is the worst case, not a generic one.** The paper states the
divergence worsens with longer responses through cumulative autoregressive error,
and the importance weight is a product over every token, so per-token errors sum in
an exponent. Run 3d's PTC rollouts are p95 2,560 tokens over 6.38 turns (measured,
below). `colocate` does not mitigate it: the divergence is a kernel-path difference,
not a device-placement one.

**Consequence.** Step 2's fp16 stability result was recorded as a Turing-era
necessity; it is the right answer on the merits, and it is the only Step 2 finding
that gets *stronger* on better hardware. On a future L4/A100, **bf16 is a downgrade
to be tested, never a default upgrade.**

## Hardware line — one card

| | value | basis |
|---|---|---|
| topology | 1x T4 16 GB, `vllm_mode="colocate"`, Unsloth vLLM Standby | — |
| `num_generations` | **4** | derived (see below) |
| `max_completion_length` | **conditional — there is no unconditional value. See next table.** | — |
| generation peak | 11.2 GB vLLM (`gpu_memory_utilization=0.7`) + 1.39 resident = **12.59 GB** | derived |

### The cap has two values, and neither is valid without its condition

| if you co-train | cap | training peak | overall peak |
|---|---:|---:|---:|
| **the PTC arm only** — what the project was designed to do | **3,072** | 7.47 + 1.39 = **8.86 GB** | **12.59 GB** |
| **both arms** | **4,258** | 10.35 + 1.39 = **11.74 GB** | **12.59 GB** |

PTC-only takes 3,072 because PTC's observed max is 2,642 and bash's 4,258 is
irrelevant to an arm that is not trained. Both-arms takes 4,258 because invariant 2
binds: the caps must be **identical across arms** and at least the global observed
max, or the comparison is confounded by the cap itself — which would bias the **cost
co-primary, the one finding that survived the audit**. (Both derived.)

Note what the two rows share: **generation binds in either case**, so on one card the
cap choice costs nothing in peak memory. It is a validity decision, not a capacity
one. Do not infer from the equal peaks that the numbers are interchangeable.

**Why this is written as a condition and not a number.** This project has already
shipped a real number attached to the wrong denominator — `$0.0071` travelled into
four documents and an OSF package because nobody recorded what it was a number *of*.
A cap quoted bare is the same fault waiting to happen.

Standby is what makes one card work. `rl_replacements.py:1741,1745` wraps generation
in `llm.wake_up()` / `llm.sleep(VLLM_SLEEP_MODE, default 1)`, gated on
`enable_sleep_mode`; `rl.py:3702` sets it from `UNSLOTH_VLLM_STANDBY`. Sleep level 1
offloads weights and discards the KV cache, so the phases **alternate** and the peak
is `max(gen, train)`, not their sum. (Measured in source; untested on hardware.)

Resident across both phases: fp16 weights 616,235,008 x 2 B = 1.23 GB; LoRA Adam
20,185,088 x 8 B = 0.16 GB. Logits use Unsloth's own formula,
`2 x 2 B x G x completion_tokens x 151,936` (vocab measured from
`unsloth/Qwen3-0.6B/config.json`), with TRL's `logits_to_keep` restricting it to
completion tokens.

**Why not G=2**, despite Unsloth's documented 16 GB T4 example using it:
`ledger/taskset.py:306` returns `float(... == ...)` — an **exact-match 0/1 reward**
(measured). Under a binary reward a group yields zero advantage whenever all G
rollouts agree, so at run 3d's PTC solve rate of 23/29 = 0.793 (measured):

| G | zero-advantage prompts | note |
|---:|---:|---|
| 2 | **67.2%** | excluded — two thirds of compute yields no gradient |
| 4 | 39.7% | chosen |
| 8 | 15.7% | needs two cards at the cross-arm cap |
| 16 | 2.5% | out of reach on free hardware |

Unsloth's G=2 example is tolerable because their GRPO notebooks use *graded* rewards,
where G=2 still carries magnitude. Against 0/1 it carries one bit, often zero.

**Why not G=8:** at the cross-arm cap of 4,258 it needs 20.7 GB on one card
(derived). Two T4s under DDP would fit (10.35 GB/card), and Unsloth does **not**
block that — every `_n_gpu = 1` site is gated on
`parallel_mode == NOT_DISTRIBUTED` (`models/rl.py:545`), and the hard multi-GPU
`RuntimeError` is injected only into `SFTTrainer`/`DPOTrainer`/`KTOTrainer`, never
GRPO (`tokenizer_utils.py:1780-1783`; measured in source). But that path is
**source-clear and untested**, and Unsloth's own comment carries a question mark:
`# [TODO] DDP works, but DP seems to not work? [TODO]`. Take it only after G=4
is shown to be limiting.

## Three invariants, each a one-line assertion

These are the three ways a built pipeline runs clean and measures the wrong thing.
None produces an error at any point.

**1. One registered tool.**

```python
assert len(tools) == 1          # run_program(code: str) -> str
```

TRL passes `tools=self.tools` into `apply_chat_template`
(`grpo_trainer.py:1293,1387,1425,1466`), so every registered tool is rendered as a
schema in the system prompt. Registering `ledger`'s `ids`/`get`/`links_to` **builds
the typed-tool-calling comparator instead of PTC** — the exact axis this project
measures, since `ptc/harness.py`'s premise is that the catalog lives *inside* the
program. The catalog must reach the model via `runtime.Catalog` plus prompt text.
*Absent: a complete, publishable run of the wrong arm.*

**2. One cap per experiment; shared across arms whenever two arms are compared.**

```python
# PTC arm only — the designed experiment:
assert cap == 3072 >= observed_max["ptc"]                    # 2,642
# both arms co-trained:
assert cap_ptc == cap_bash >= max(observed_max.values())     # 4,258
```

**Neither number is usable without its condition** — see the cap table above.
`mask_truncated_completions=True` means a rollout over the cap is **dropped from the
loss, not truncated**. At cap 1,024, 8/29 PTC rollouts vanish (27.6%, measured) — all
from the full-scan tier, the only tier with headroom. And if two arms are compared
under *different* caps, the cap masks each arm's tail at a different rate: PTC's is
2,642 and bash's 4,258, so a shared 3,072 would silently delete bash rollouts PTC
keeps. *Absent: trained on the saturated half, measured on the dead half — or a cost
comparison confounded by its own truncation threshold.*

**3. `max_turns` reaches the trained arm.**

```python
assert env.max_turns == EVAL_MAX_TURNS      # 8, PTCHarnessConfig default
```

trl's `_tool_call_loop` is `while idxs_with_tool:` whose only exit is "all overlong";
`tool_call_count` is a logging counter, not a limit (measured). The budget must live
in the `environment_factory` instance — per-rollout state, which is why this needs
1.13.0 and not 0.26 — and exhaustion must return a refusal the model reads, matching
`runtime.py`'s existing "a rejection the model reads, not a hang". *Absent: defect 1
again — a turn-unbounded trained arm against an 8-turn eval arm.*

## Two abort criteria, over metrics the stack already emits

`verdict.py` owns pass criteria; these extend it for a co-training run. **Neither
needs new instrumentation.**

**A. `frac_reward_zero_std` ceiling.** Already logged by TRL and already present in
`step2/results/step2_metrics.jsonl` at 0.0. Expected ~0.40 at G=4 (derived from the
binary reward and p=0.793). **Abort above 0.60 sustained over 10 consecutive steps**
(assumed threshold) — it means most of the batch yields no gradient. Note both tails
degenerate: p=0.1 gives 43% dead at G=8 against 15.7% at p=0.79, so a *weak* policy
is worse than a strong one. This is answerable in the first few steps of any run,
which makes it a cheap early exit rather than a study.

**B. `sampling/sampling_logp_difference` trend.** trl 1.13.0 computes
`vllm_importance_sampling_ratio = torch.exp(logps_diff)` (`grpo_trainer.py:2696`) and
logs `sampling/sampling_logp_difference/{mean,max}` (`:2893,:2896`), with
`vllm_importance_sampling_correction=True` and mode `"sequence_mask"` as defaults
(measured). arXiv:2510.26788's diagnostic is that runs which collapse show a
*growing* mismatch beforehand. **Abort on a monotonically rising mean across 10
consecutive logged steps, or a mean exceeding 3x its first-10-step median** (assumed
thresholds; the paper gives the mechanism, not a number). A flat elevated value is a
calibration offset, not this signal.

**Making B fire.** A check that has only ever passed is not evidence. Run generation
in bf16 while training in fp16: the paper's own measurement says the mismatch grows
~24x, so the logged mean must move by a large visible factor. If it does not move,
the metric is not wired to anything. Cost: one five-step run, the same shape as Step
2. Toggling `vllm_importance_sampling_correction` is **not** a valid test — it
changes the clipping, not the logged difference.

## The dead-group probe — not a training run, and not blocked on the eval

**This is the only GPU spend this document authorises, and it is not training.** It
answers one question that no amount of reasoning settles: *does a binary reward
produce usable groups against a 0.6B policy?* It needs no working benchmark, because
it measures the reward's geometry rather than the model's competence.

| | |
|---|---|
| what | 5-20 GRPO steps, aborting; the shape and cost of the Step 2 smoke run |
| metric | `frac_reward_zero_std` — **already logged by TRL**, already in `step2/results/step2_metrics.jsonl` at 0.0 |
| config | the stack and hardware line above; G=4; cap per the condition that applies |
| **abort ceiling** | **> 0.60 on any step** (assumed). Stop; do not continue to a training run |
| expected if healthy | ~0.40 at G=4 (derived from the 0/1 reward and p=0.793) |
| outcome if it fires | the reward's shape, not the pipeline, is the problem — and no taskset fixes a reward that cannot separate |

**Why it is worth taking before anything else is built.** Both tails degenerate: at
G=8, p=0.1 gives **43%** zero-advantage prompts against **15.7%** at p=0.79
(derived), so a *weak* policy is worse than a strong one. Qwen3-0.6B is the weak
case, and the 0.793 figure that sets the healthy expectation is
`deepseek-v4-flash`'s. So the realised value could plausibly be anywhere from 0.15 to
0.60+, and the difference decides whether a binary exact-match reward is viable at
all. This project has historically re-derived such numbers after the money was spent;
this one fires before.

**It is explicitly not** a training run, a verdict on H2-H5, or grounds to build the
pipeline. A clean probe says the reward separates — nothing more.

## Measured quantities, with provenance

From run 3d's traces, `~/scratch/co-train-run3d/*/traces.jsonl`, per-call `usage`
intact. 29 rollouts per arm. Re-derived independently; every figure reproduces.

| quantity | PTC | bash |
|---|---:|---:|
| turns/task | **6.38** | 29.34 |
| completion tokens, total | 24,646 | 33,793 |
| completion/turn — mean / p95 / max | 133 / 322 / 493 | 40 / 80 / 1,774 |
| completion/rollout — mean / median / p95 / max | 850 / 645 / **2,560** / **2,642** | 1,165 / 1,232 / 3,256 / **4,258** |

**These are floors, not forecasts, and the reason is the model.**
`ledger-ptc-tool/configs/resolved/eval.json` records `model = deepseek-v4-flash`,
`base_url = https://vyceai.com/v1`. "Untrained" in `results-untrained.md` means *not
co-trained*, **not small** — these are frontier-class rollouts under no training
pressure. Qwen3-0.6B will not beat `deepseek-v4-flash`'s already-low PTC tool-call
success of 0.561, so expect more turns and longer programs; GRPO also drifts longer
before it drifts better. **Log the realised completion-length distribution from step
1**, so a drifting tail is visible before it starts masking the hard tier.

**The mean is reassuring and irrelevant.** Logits are allocated for the padded group,
so the longest rollout in the group sets the footprint. Design against the tail.

Not measured, and load-bearing: **vLLM throughput for 0.6B fp16 on a T4.** The only
measured generation figure is Step 2's **3.2 tokens/sec** whole-loop at
`use_vllm=False` (954 generated tokens / 298.24 s). At that rate a single GRPO step
is over an hour and free hardware is out; with vLLM it is minutes. The entire
feasibility argument rests on a number nobody has taken.

## Non-goals

- **This spec is not authorisation to build.** No code follows from it today.
- **The eval is the blocker, and the pipeline must not be built first.** A mis-built
  pipeline normally announces itself as "no training effect". If the benchmark cannot
  show a training effect even when the pipeline is *correct*, then broken and working
  produce identical output — so the eval is not merely what the pipeline feeds, it is
  **the only instrument that could validate it**. Building first yields a confident
  wrong answer rather than no answer.
- Not a verifier (Step 3), not a cross-harness evaluation (Step 6), not a second arm.
  Not a decision about rented hardware.
- Not a re-opening of Step 2. That result stands and is re-checkable with no GPU.

The one exception is scoped and has its own section above: **the dead-group probe**.
It needs no working benchmark, aborts on a number, and is not a training run.

## Blocking requirement — the precondition this spec waits on

**A taskset whose tasks sit near a 0.6B model's frontier.** Not merely more shapes.
A 0/1 reward needs tasks the policy *sometimes* solves: saturation (p approaching 1)
and uniform failure (p approaching 0) both produce zero-advantage groups, and the
second is the likelier failure for a 0.6B policy. `ledger` fails this on two counts —
the cheap tier's shape count is a record-schema ceiling, and run 3d scored an exact
23/23 tie — so no value of n or G rescues it. Until that taskset exists, every number
in this document is preparation for a measurement that cannot yet be made.

## Open

- Unsloth fp16-on-Turing at trl 1.13.0 — the stack's premise, untested.
- vLLM throughput for 0.6B fp16 on T4 — decides minutes vs hours per step.
- Realised completion-length distribution for a 0.6B policy under GRPO — decides
  whether the 4,258 cap holds.
- Whether `gpu_memory_utilization=0.7` is computed against total or free VRAM when
  the trainer already holds 1.39 GB; if total, it needs lowering.
- The zero-advantage fraction for the actual policy, which criterion A answers
  cheaply and which no amount of reasoning settles.
