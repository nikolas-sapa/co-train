# What to measure next, 2026-10-22

The next useful result is a frozen-policy, per-task frontier measurement.
Another longer optimizer run would not supply the missing denominator.

No new GPU job, paid endpoint call, protocol signature or publication accompanied
this review. Recommendations below are proposals, not amended pass criteria.

## What the existing evidence now says

- v10 ran and aborted after three steps. Its last step had mean execution reward
  0.34375 and one informative group among four. The reward can separate some
  completions; sustained trainability and per-task solve rates remain unknown.
  `docs/probe-v10.md` records the executed verdict and artifact fingerprints.
- The exact 800 shipped gold references matched the local corpus and all executed
  successfully under the scorer's limits. Invalid gold execution does not explain
  this shipped draw's reward sparsity against these local files.
- A fixture-backed regression found twenty ways that semicolons inside SQL strings,
  identifiers or comments were truncated and correct answers scored zero. The
  extractor now uses SQLite's statement-completeness check at candidate
  terminators. This does not establish an effect on historical v10 scores; those
  originals have not been rescored or rewritten.
- The frontier manifest is absent and preflight fails. The co-training entry point
  also deliberately ends in `NotImplementedError`. Describing the whole pipeline
  as runnable once a manifest exists overstates the implementation.

## The remaining comparison is narrow

The comparison worth considering is matched **bash-trained versus PTC-trained
models at 0.6–1.7B, evaluated under both harnesses**, including a frozen base under
each evaluation harness. Broad claims about harness co-training, transfer, cost
variation, or internalizing a harness already have prior work.

This search found no examined source that completes that exact controlled cell.
That is a bounded literature finding, not proof of priority.

| Primary source | What it already studies | Limit for this comparison |
|---|---|---|
| [ProgAgent, 2610.14774](https://arxiv.org/html/2610.14774v1), §§4–5 and Appendix C | Qwen3-8B/14B, PTC/DTC/Hybrid training and cross-harness evaluation | Typed DTC is not a matched bash treatment; models exceed this project's band. Training difficulty exposure also needs care when interpreting headline comparisons. |
| [Multi-Harness RL, 2609.04518v2](https://arxiv.org/abs/2609.04518v2), revised 9 October | Source-harness gains and transfer to an unseen coding harness | Neither normalization rule significantly improves on SFT under the unseen harness. Positive transfer cannot be assumed from generic co-training arguments. |
| [HarnessBandit, 2609.13739](https://arxiv.org/abs/2609.13739) | Multi-harness scheduling, learnability and transfer at Qwen3.5-2B | Small-model harness learning itself is occupied. The examined abstract does not establish matched bash/PTC training. |
| [HarnessRL, 2610.26426](https://arxiv.org/html/2610.26426), 19 October | Adaptive sampling, guidance and rubrics at 4B/9B | Relevant to non-discriminative rewards, but adopting adaptive rubric rewards changes this project's deterministic-reward treatment. |
| [Harness-Zero, 2609.24974](https://arxiv.org/html/2609.24974), §§4.1–4.4 | Qwen3.5-9B LoRA SFT distilling harness behavior, deployment under one fixed Bash harness | Internalizing a harness is occupied; no matched bash/PTC treatment or 0.6–1.7B comparison. |
| [The Bitter Lesson of Tool Calling, 2608.06370](https://arxiv.org/html/2608.06370v1), §§3.2, 3.5, 7 | Inference-interface comparison on proprietary checkpoints | PTC running Python through a shell is not an independent bash training arm. BFCL argument-echo stubs do not establish end-to-end tool execution. |
| [Runtime-contract study, 2603.01209v3](https://arxiv.org/abs/2603.01209v3) | Qwen3-8B paired SFT and a 2×2 deployment comparison | Shows why call-budget and interface controls matter; it does not supply this project's small-scale bash/PTC treatment. |

The repo's H1 non-reproduction remains closed; its original model was
`deepseek-v4-flash`, not a 0.6B model. A8 does not keep the original H2 reversal
question alive by renaming a BIRD result. H3/H4/H5 remain the relevant BIRD
questions. N1 still needs a genuine call-count contrast and a different,
owner-approved instrument.

## Smallest useful next experiment

Measure the frozen `unsloth/Qwen3-0.6B` policy on the fixed candidate draw, task by
task, before optimizer updates. Use the intended training channel and prompt,
the same sampling settings, quote-aware extraction, and set-based EX.

The existing direct-SQL GRPO probe registers neither tools nor a rollout function.
It is a useful SQL reward diagnostic, not evidence that the PTC training harness
works. If the intended channel is PTC, its rollout path needs implementation and
offline integration checks before its frontier can be measured.

Before execution:

1. Fix the channel, model revision, candidate IDs, database/input hashes, G and
   sampling budget. Spec default G=4 and observed v9/v10 G=8 are different
   measurements, not interchangeable defaults.
2. Declare evaluation membership before observing screening successes. A
   frontier-selected training set must not silently become an unbiased evaluation
   set.
3. Retain taskwise generation counts, successes, scorer validity/status and
   exclusions. Report all candidate and retained counts, shapes and raw outcomes.
   Do not derive taskwise rates from a marginal mean.
4. Keep the pre-registered S1 marginal EX prediction, 10–40%, evaluated on the
   unfiltered candidate draw. Screening retention is a different quantity.

At the existing ceiling, per-task screening uses
`p_i**G + (1-p_i)**G <= 0.60`. The theoretical band is approximately 0.120–0.880
for G=4 and 0.06186–0.93814 for G=8. With only four samples, retained empirical
rates are 0.25, 0.50 and 0.75; these are coarse screening estimates, not precise
underlying probabilities.

For all 800 candidates, one screening pass needs 3,200 generations at G=4 or
6,400 at G=8 per evaluated policy/channel. These are sample counts, not a dollar
or wall-clock estimate. No such pass was launched here.

If screening supports proceeding, an H3 pilot can compare PTC-trained and frozen
base under both evaluation harnesses. The full surviving comparison also needs a
matched bash-trained checkpoint. Neither experiment tests N1 on BIRD.

## Protocol arithmetic to settle before compute

The independent check is stored locally at
`~/scratch/co-train-research-2026-10-22/protocol-arithmetic.json`.
No signed text or threshold was changed.

### 59 tasks is not the stated H3-powered sample

Using the repo's `ptc.paired.power_pairs`, discordance 0.5, alpha 0.05 and target
power 0.8:

| Target difference | Paired tasks returned |
|---|---:|
| 25 percentage points | 59 |
| 13.5 percentage points | 219 |

At 59 tasks, independently summing the exact two-sided McNemar rejection
probabilities gives power 0.296014 for 13.5 percentage points under the same
rounded-discordance model. This calculation conditions on
`round(n * discordance)` discordant pairs, as the repo does; it is not a new
unconditional power analysis.

Keep 59 as the current feasibility floor. Do not call it an 80%-powered H3
evaluation. The mismatch between A8's prose and the helper's 25-point input needs
an explicit owner disposition, without editing away signed history.

### A11's initial-window probability is not a ten-step stopping probability

Under A11's own fixed-policy, independent-step model, at the G=8 band's edge a
group is dead with probability 0.60. Four groups make the probability of a step
strictly exceeding the ceiling:

`S = 4 * 0.60**3 * 0.40 + 0.60**4 = 0.4752`.

- Three initial breaches: `S**3 = 0.107307`.
- At least one run of three consecutive breaches anywhere in ten steps:
  **0.458311**.

Dynamic programming and enumeration of all 1,024 ten-step binary sequences agree
within `1e-12`. This is model arithmetic, not an empirical forecast for a changing
policy or heterogeneous tasks.

A window of three can stop after three steps, below the five-step verdict
minimum, as v10 actually did. A delay bound of two extra steps applies only to a
continuing breach streak; resets can delay the stop further. With four groups,
ceilings 0.60 and 0.70 both select observed fractions 0.75 and 1.0; a ceiling of
0.75 selects only 1.0. The draft's attainable-event wording is incorrect.

## Gate implementation is not the whole declared contract

`train.guards.frontier_taskset_status` requires the `measurement` key but does
not call `_check_measurement`. The helper's G, band, count and retention checks
are therefore dormant. In particular, its approximately 76% retention floor is
neither an enforced current threshold nor a signed pass criterion.

Do not "fix" this by wiring in the whole helper: that would activate an
unsupported measurement policy. First separate signed requirements from extra
assumptions, resolve the latter explicitly, then add negative tests for the
approved manifest contract.

The invalid-gold reward path also has conflicting contracts: training maps a
broken gold to zero, while the scorer distinguishes a void. All 800 shipped
golds passed local validation, so no replacement policy was invented during
this continuation.

## Work order

1. Decide the frozen measurement's exact channel and G, then freeze its sample
   budget and evaluation membership.
2. Implement and verify the missing intended rollout path and the approved
   manifest checks. Keep preflight closed until genuine evidence exists.
3. Authorize the named screening run separately. Record model/code/data identity
   and preserve all outputs immediately.
4. Use its evidence to decide whether a matched training experiment is worth
   running. Correct A11 before signing or using it to certify a GRPO result.

GPU runs, paid fallbacks, protocol signatures and public claims remain outside
this review's authorization.
