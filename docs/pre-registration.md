# Pre-registration — model-harness co-training
Written 2026-09-25, **before any training run and before the untrained measurement.**
Sources for every number: `research/08-gap-closure.md`.

This exists because two findings say the result is otherwise decidable after the
fact rather than before it:

- **The metric picks the winner.** At TAC / GPT-5.5 the untrained PTC arm already
  beats bash on cost ($0.54 vs $0.56) and tokens (242k vs 377k) while losing on
  score (45.1 vs 67.1). So "does co-training reverse the ordering" has *different
  answers under different metrics, before a single step of training*. Choosing the
  metric afterwards is choosing the result.
- **A null on score is not a null on effect.** arXiv 2603.01209 held everything but
  one runtime property fixed and found *"solution quality is statistically
  indistinguishable across conditions, but token cost and stability differ
  substantially"*. Score alone would have reported "no effect".

---

## 1. The question

Does co-training a small model against a programmatic-tool-calling (PTC) harness
reverse the bash-over-PTC ordering measured on untrained models, and does the winner
survive a harness swap?

## 2. Outcomes, declared in advance

**Primary:** task score, by each benchmark's own deterministic grader. No LLM judge
anywhere in the reward or the primary outcome (project rule #5; and `08` §5.2 found
Harness-Bench's aggregate multiplies in a 3-part LLM rubric, which is why its
aggregate is unusable here and only `Security × Completion` is).

**Co-primary, reported always, never chosen afterwards:**
1. **Billed cost per successful task** — not tokens. Token count is not a cost proxy
   (−38.4% tokens, +6.8% cost, r=0.15; arXiv 2607.12161).
2. **Stability / failure mode** — per 2603.01209, the axis on which an effect is most
   likely to appear at all.

**Secondary, pre-declared because they are better leading indicators than score:**
3. **Tool-call success rate.** Untrained baseline from the source paper's Table 2:
   PTC **65.2%** vs bash **92.1%**. A third of PTC calls simply fail. This is the
   headroom training is supposed to claim, and it should move before score does.
4. **Shell-call share.** OpenForgeRL measured RL moving it 22.6% → 13.9% and read that
   as *"RL teaches the model to reach for the right specialized tool instead of falling
   back on a general-purpose shell"* (its §5.3). Directly comparable, already published.
5. **`frac_reward_zero_std`** from step 1 of every run. The one public Kaggle run at
   this project's exact config had reward go flat from signal starvation (0.56–1.00 of
   groups carrying zero advantage), not from numerics. Without this metric that run
   looks like a training failure.

## 3. The gap to reverse, stated numerically

Bash − PTC, recomputed from the source paper's Table 1:

| Arm | Bash | PTC | Δ | 95% CIs |
|---|---|---|---|---|
| TAC / Opus-4.8 | 69.4 | 52.9 | +16.5 | disjoint |
| TAC / GPT-5.5 | 67.1 | 45.1 | +22.0 | disjoint |
| APEX / Opus-4.8 | 48.5 | 40.1 | +8.4 | disjoint |
| APEX / GPT-5.5 | 44.6 | 37.8 | **+6.8** | **overlap 40.8–41.5** |

**Target the APEX end (+6.8 to +8.4), not the TAC end.** `08` §6: APEX's bash arm is a
genuine `sh -c` server (the MCP confound is refuted by the paper's own Appendix B.2),
whereas TAC's typed catalog is author-built and self-declared *"not every
shell-accessible endpoint"* — so the larger TAC delta is the one carrying a
construct-validity handicap. One of four arms is not significant.

## 4. Signed predictions

Recorded so that being wrong is visible.

- **H1 — the untrained gap reproduces, at the small end.** Predicted bash − PTC closer
  to +7 pp than +22 pp. *Confidence: moderate.* Risk: the source paper has **zero
  citations** by five independent routes, is first-party, and is unreplicated.
- **H2 — co-training narrows the gap but does not reverse it at 0.6–1.7B.**
  *Confidence: moderate-to-high*, on three independent grounds: the evaluation harness
  dominates the training recipe 4.3× vs 1.16× across 24,000 sealed evaluations
  (2609.04518); small models prefer localized, low-altitude actions while only larger
  ones exploit a wide interface (NapMem's own behavioural analysis); and GRPO added
  nothing to a strong supervised 4–8B baseline across 18 controlled runs, helping
  *"only when there is headroom to climb"* (2607.12640).
- **H3 — cross-harness transfer is positive but attenuated ~3–4×.** Direct read from
  OpenForgeRL Table 5 (+13.5 in-harness vs +3.3/+4.6 out-of-harness).
- **H4 — the effect appears in tool-call success rate and cost before it appears in
  score.** *This is the prediction most worth being wrong about*: if score moves and
  success rate does not, the mechanism is not what this project thinks it is.
- **H5 — narrow beats wide at this scale.** `08` §8 found real counter-evidence that a
  *larger* action space wins (SCAFFOLD +25.9 on a held-constant 7B base; NapMem's wide
  interface winning only *after* training: prompted 48.39 < narrow 54.08 < trained
  62.74). Both are ≥7B. Predicting the crossover needs capability this project does not
  have, and recording that so a narrow-wins result is not retrofitted as vindication.

## 5. Methodological commitments

- **Grouping boundary stated.** 2609.04518's explicit ask: *"Multi-harness RL reports
  should state the grouping boundary and test under an unseen harness."* This project
  groups **within** task-harness pairs unless stated otherwise per run.
- **A held-out harness from run 1.** Not train-on-A-deploy-on-A.
- **Action-space altitude held comparable across arms, or the asymmetry declared.**
  A deliberately minimal PTC vocabulary against a composed shell makes a PTC loss
  unattributable (`08` §8).
- **The verifier is tested both ways before it scores anything**: reference solution
  must PASS, planted mutant must FAIL. A green anti-cheat check that has never gone red
  is not evidence.
- **Health signals from run 1**: gradient norm, `mean_response_length`, token entropy,
  `reward_std`, `frac_reward_zero_std`, and **KL** — KL is the only curve nobody has
  published for this configuration, and it requires `beta > 0` (TRL v0.24.0 defaults
  `beta = 0.0` and logs `kl` only when `beta != 0.0`).
- **Model pinned to dense Qwen3.** `qwen3_5` and `qwen3_moe` are on Unsloth's
  force-float32 list for fp16 NaN grad norms; dense `qwen3` is not (`08` §7). Not a
  preference — an upgrade to Qwen3.5 breaks the run.

## 6. What would falsify the project, not just the hypothesis

**If the untrained bash-over-PTC gap does not reproduce, the project is over** and the
correct output is a short negative report on a first-party unreplicated result. This is
cheap and publishable, and it is the reason the untrained measurement should run before
weeks of verifier and environment work.

## 7. Non-goals

Not building a trainer. Not building RL environment plumbing. Not beating frontier
models on SWE-bench. Not shipping a usable coding agent. Not pretraining from scratch.
Not claiming novelty in harness-native training *or* in cross-harness transfer — both
are published (`08` §1.2). The single surviving claim is **harness type as the
independent variable**: shell vs PTC, model held constant, which is unoccupied across
20 arXiv queries, 13 Scholar queries and 13 OpenAlex calls.

---

## 8. Amendments

**Append-only. §1-7 above are left byte-identical to what was written on 2026-09-25,
before any run.** An amendment states what was learned, when, and from which data, and
it never edits a prediction into agreement with a result. If a reader cannot tell the
original from the revision, the pre-registration has stopped doing its job.

### A1 — 2026-10-03, after run 2f: H1's predicted band is below this instrument's floor

**What was learned.** `ptc/paired.py` reports the paired tasks needed for 80% power at
exact McNemar, given an observed discordance rate. At run 2f's rate (0.429), detecting
§3's APEX-end target of **+6.8 pp needs ~732 paired tasks**. Run 2f carried 14, at
roughly 3h26m of wall clock for 28 rollouts at `--max-concurrent 1`: ~180 hours for 732.
Its own point estimate (+28.6 pp) needs 39.

**What this changes, and what it does not.** H1 stands exactly as written, and it is
**not** restated as a large-effect prediction to make it passable. What changes is the
claim that will be made from it: this design can report whether a *large* bash-over-PTC
gap exists, and cannot adjudicate the +6.8 to +8.4 pp band it predicted in either
direction. A null at this n is not evidence of absence at that band, and will not be
written as one. §6's kill condition still applies on its own terms — a gap that fails to
reproduce *directionally* ends the project — and run 2f does not trigger it: the gap
reproduced, large and in the predicted direction, at p=0.2188 with the CI on the
difference touching zero.

**Disclosed because it is after the fact.** This amendment was written after seeing run
2f's numbers. The power ceiling is a property of n and the discordance rate, not of the
result, and it would have read identically had the sign gone the other way — but it was
still found by looking, and that is recorded rather than smoothed over.

**Open and deliberately not decided here.** Whether to buy the n. 732 paired tasks is
reachable only by growing the taskset ~50x, and the aggregation families that produce
the discordance do not expand per-record the way the lookup families do (there is one
richest owner). Expanding the cheap families lowers the discordance rate and buys tasks
without buying power. No taskset expansion is pre-registered by this amendment.

### A2 — 2026-10-03, after run 2f: every real-mode number before run 2g is instrument-bound

Runs 1 through 2f each measured an instrument defect at least as large as the effect
sought; `docs/deviations.md` carries all five with the trace evidence for each. Defect 5
is the one that matters for interpretation: the bash arm held the typed catalog as
native tools *and* reached data it could read with its own attention, while the PTC arm
reached the same three functions through a sandbox with no parser, making bash's action
space a strict superset. **No score comparison from runs 1-2f is admissible**, including
2f's +28.6 pp. Run 2g, post-fix, is the first run whose score gap is attributable to the
action channel rather than to the rig.
