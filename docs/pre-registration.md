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

### A3 — 2026-10-03, after run 2h: A1's power figures were computed from a broken instrument

**A1 stands as written and is wrong on its central number.** It reported ~732 paired tasks
for §3's +6.8 pp band and concluded the band was below this instrument's floor at ~180 hours
of wall clock. Both figures came from run 2f's discordance rate (0.429), and run 2f was the
run whose PTC arm could not parse its own tool output (defect 5). On run 2h's discordance
(0.143), post-fix: **242 paired tasks**, roughly 7 hours at 2h's rate. The APEX-end band is
reachable.

A1 is left in place rather than corrected, because the error is the instructive part: an
amendment written honestly, disclosed as after-the-fact, and still wrong — because it
reasoned from data produced by a defect it had already documented elsewhere. **A power
calculation inherits every bias of the run it is computed from.**

### A4 — 2026-10-03, after run 2h: §6's condition is met and the deliverable is written

H1 predicted bash − PTC *"closer to +7 pp than +22 pp"*. Run 2h, the first mechanically clean
run free of a known arm asymmetry, measured **−14.3 pp**: wrong on sign, not magnitude. PTC
solved 14/14 to bash's 12/14, won both discordant pairs, and took 8.5x less cost per solved
task on 8x fewer billed prompt tokens.

**§6 fires.** `docs/results-untrained.md` is the short negative report it pre-committed, and
it is the project's output. It claims a failure to reproduce — not a demonstration that PTC
wins: the CI on the difference touches zero, exact McNemar gives p=0.5000 on two discordant
pairs, and PTC's 14/14 is a ceiling that cannot carry an effect size.

Co-training was never run, and nothing here is a verdict on H2 through H5.

### A5 — 2026-10-07, after run 2h: the taskset is extended, and that resets the benchmark

**This amendment discloses a post-hoc change to the instrument. It is the kind of change
that, left undisclosed, turns a benchmark into a result.**

15 tasks were added to `ledger` (14 → 29). Every one is a second-order read of the same five
fields: no new field, no new record, no new tool. They differ from the original tier in
needing an intermediate result — a rank, a mean, a link-walk, a set — before the final one,
where the original many-call tier is a single filter-and-sum pass.

**Why, stated plainly.** Run 2h scored PTC **14/14**. §4's H2 cites 2607.12640 for the
finding that GRPO helps *"only when there is headroom to climb"*; a taskset the untrained
model already solves completely has none, so a co-training run against it could not produce
a readable result in either direction. The alternative — 242 tasks of the existing shapes,
per A3 — buys statistical power over tasks both arms already solve, which is power to detect
nothing. A3's arithmetic stands; it answers a different question than this does.

**What this amendment does NOT license:**

- **No comparison across taskset versions is admissible.** Runs 1 through 2h were scored on
  the 14-task set. Any future run is scored on the 29-task set. A score from one is not a
  score from the other, and the two must never appear in the same table as though they were.
- **`docs/results-untrained.md` is unaffected and is not reopened.** It reports run 2h on
  the 14-task set, which is what it says it does. The ordering it found is not re-litigated
  by a harder taskset.
- **H1 through H5 stay byte-identical and stay adjudicated as they are.** §6 fired. The
  premise is dead and co-training cannot resurrect it. Any work on the extended taskset is a
  **new question**, pre-registered separately or not claimed at all.
- **The construct-validity handicap is now worse, not better.** `ledger/__init__.py` already
  records that a self-authored catalog is not evidence about catalogs in general. Authoring
  harder tasks after seeing which shape one arm failed on compounds that: bash's two failures
  on 2h were arithmetic, and this tier deliberately contains more arithmetic. A reader is
  entitled to discount it accordingly, and the Harness-Bench request
  (`docs/licence-requests.md`) remains the only fix that does not have this problem.

**The new question, stated before the data exists**, so that it is a prediction rather than
a description: run 2h's bash arm retrieved all 40 records correctly and then mis-summed
fifteen numbers in context, with a shell available and used on 2.3% of calls. **Does forcing
the action to be expressed as a program make a model compute where a free-text channel lets
it guess?** That is H4's mechanism, not H1's premise. It needs its own pre-registration
before any run on this taskset is reported as evidence for it.

### A6 — 2026-10-08, BEFORE run 3c's numbers: the new question, signed

**Written while run 3c was in flight and before any of its output was read.** A5 committed
that the question the extended taskset asks "needs its own pre-registration before any run
on this taskset is reported as evidence for it", and this is it. The git timestamp is the
evidence that it precedes the data; nothing below was adjusted afterwards.

**What I knew when writing this, stated so the prediction can be discounted correctly:**
run 3b's full output, which is void as a comparison (10 bash rollouts lost to 429s) but
whose per-task scores I had read, split by tier:

| tier | bash | ptc |
|---|---|---|
| cheap, `min_calls` < 40, n=11 | 11/11, 0 void | 9/11, 0 void |
| full-scan, `min_calls` = 40, n=18 | 3/18 (10 void, 3 of 8 completed) | 11/18, 0 void |

This is therefore a **prediction from partial prior data, not from a blank slate.** It is
weaker than §4's predictions, which preceded all data. Recorded as such.

## The question

**Does forcing the action to be expressed as a program make a model compute, where a
free-text channel lets it guess?** Run 2h's bash arm retrieved all 40 records correctly
across 42 turns and then mis-summed fifteen numbers in context, with a shell available and
used on 2.3% of its calls. That is H4's mechanism — interface shaping *how* the work gets
done — and it is not H1's premise, which §6 already killed.

## Signed predictions

- **N1 — the effect is an interaction, not a marginal score.** PTC's advantage is confined
  to tasks needing many calls. Predicted: PTC − bash is **negative or near zero on the
  cheap tier** and **positive by ≥ 25 pp on the full-scan tier**. *Confidence: moderate.*
  The marginal score across all 29 is the wrong statistic and is pre-emptively declined as
  the headline: it averages two opposite effects and its value depends only on how many
  tasks of each tier the suite happens to contain.
- **N2 — bash wins the cheap tier.** Predicted bash ≥ PTC there, 10-11/11 against 9-11/11.
  A typed-tool call read with the model's own attention is the cheaper channel when one
  call suffices, and PTC pays a program-authoring overhead for nothing.
- **N3 — bash still will not use the shell.** Predicted shell-call share **< 0.10** on the
  full-scan tier, where a shell is exactly what the task needs. 2h measured 0.023, 3b
  0.0105. *This is the prediction most worth being wrong about*: if bash's share rises and
  its full-scan score rises with it, the mechanism is availability, not channel, and the
  whole framing is wrong.
- **N4 — the retry budget fixes the voids but not completely.** Predicted **≤ 4** void bash
  rollouts at `--max-retries 20`, down from 10. More than 4 means the endpoint, not the
  parameter, is the constraint, and `docs/deviations.md`'s two options come back.

## Pre-specified analysis

Paired **within each tier**, since the tiers answer different questions: `ptc/paired.py` on
the 11 cheap tasks and on the 18 full-scan tasks separately, each with its own bootstrap CI
and exact McNemar. The interaction is the difference of those two paired deltas. **Any void
rollout on either arm voids the whole comparison** — `paired.py` enforces this and must not
be worked around by dropping the arm that died.

## What would falsify this

N1 reversed, or flat across tiers, means the channel is not what decides computation and
the extension bought nothing. N3 reversed means the mechanism is tool availability and this
question should be retired rather than pursued.

## What this still does not fix

`ledger` remains self-authored, the tier split was authored after seeing which shape bash
failed on (A5), n is 11 and 18, there is one model behind one unaudited relay, and no run
repeats. A confirmed N1 on this instrument is a reason to build a better instrument, not a
result to publish.

---

### A7 — 2026-10-11, after the relay and pricing audit: A4's cost claim is restated as two ratios

**This amendment corrects numbers this document published. A4's text above is left
verbatim and is not edited** — the convention in this repo is to correct visibly, so the
wrong figure stays readable next to the right one. A4's final sentence reads *"took 8.5x
less cost per solved task on 8x fewer billed prompt tokens"*. Three faults, none of which
touch run 2h's score, its void count or its stability:

1. **The rates were never measured.** Every real-mode run was launched `--price-in 0.09
   --price-out 0.18`. The relay charges **$0.2186/M in and $0.670/M out**, measured from
   three `x-balance-remaining` deltas and now carried as named constants
   (`ptc/metrics.py:75-78`). Every dollar figure this document and its deliverable ever
   published is therefore **~2.4x low**. Independent corroboration, nine days apart on an
   unrelated route: `docs/deviations.md`'s run-1 entry recorded **$0.16 billed** — the only
   *observed* charge in this project — against $0.1502 re-derived at the measured rates
   (within 7%) and $0.0603 at the assumed ones (2.65x low).
2. **`8.5x` was two rounded cells divided.** $0.0051/$0.0006 = 8.5 only at 4 dp. At the
   rates then in use the ratio is **8.05x**; at the measured rates run 2h's cost per solved
   task is **$0.0126 against $0.0017, i.e. 7.53x** (`docs/results-untrained.md:25`).
3. **"billed" was false, and the word did the damage.** The counts are the relay's own
   `usage.prompt_tokens`, which matches `cl100k_base` over raw content exactly on short
   prompts, carries zero chat-template overhead, returns the **identical** count for one
   prompt under two different model ids, and exceeds every standard tokenizer by **43-56%
   above ~3,800 tokens**. They are relay-reported, not provider-billed. Run 2h's ratio is
   **7.99x** (660,842 / 82,664) as reported. No artifact in this repo ever recorded which
   model answered (`ptc/relay_audit.py` pins stability, because identity is not available).

**The claim is restated as two ratios and a floor, never one multiple:**

| quantity | as reported | de-inflated | note |
|---|---|---|---|
| prompt tokens, bash/ptc | **8.0-10.7x** | **6.9-8.9x** | 7.99x on 2h, 9.30x on 3c, 10.68x on 3d |
| dollars per solved task | **6.1-8.2x** | — | $0.0126-0.0243 bash against $0.0017-0.0035 PTC |

**Keep the token ratio and the cost ratio separate; merging them is how the error
happened.** The previously published `$0.0071-0.0099` range is withdrawn: `$0.0071` is run
3d's bash total over **29 tasks attempted** (0.2067/29), a per-*attempted* figure paired
with a per-*solved* bound, and the range omitted run 2h, whose bash per-solved is $0.0051 —
below its own published floor.

**Secondary 3 is withdrawn outright, not restated.** `_is_failure` prefix-matched
`"rejected:"` and `"error:"`, strings only `ptc/harness.py` emits, so **0 of 1,924 bash tool
calls ever registered a failure** and bash's 1.000 was a floor artifact. The reported gap was
an instrument asymmetry on one arm, so there is no corrected number to put in its place.

**What this does not fix.** The order of magnitude and the sign of the cost result survive;
the single multiple does not. The mechanism is unchanged and structural — bash re-sends its
transcript once per turn — and it still holds at an exact score tie (run 3d, 23/23). But the
rates are one relay on one date, not a provider price list, and the de-inflated band rests on
a tokenizer comparison rather than an invoice. **Treat the ratio as the result and the dollars
as an estimate with a stated floor.**

Signed 2026-10-11 under the owner's standing instruction this session that non-spending
decisions are the agent's to take; the owner's delegation is recorded here rather than
implied, because every other amendment in this file was signed by him directly.

---

### A8 — 2026-10-12, BEFORE any run on it: the instrument is replaced, and that resets the benchmark again — signed

**This amendment discloses the FOURTH change to this project's measuring instrument. It is
the kind of change that, left undisclosed, turns a benchmark into a result — and a fourth
one is the kind that, even disclosed, entitles a reader to ask whether any instrument in
this project survived contact with its own data.** A1 raised the floor, A3 corrected A1's
power figures, A5 extended the taskset, A7 restated A4's cost claim, and this replaces
the taskset outright. The honest
summary of that sequence is that three instruments were found inadequate *after* they were
built, and this is the first one whose inadequacy is being written down *before* a run.

`ledger` is retired as a measuring instrument. The replacement is **BIRD-SQL dev**
(CC BY-SA 4.0) alone, scored by **execution accuracy
(EX)**: execute the predicted SQL and the gold SQL against the task's sqlite database and
compare the returned rows. The instrument is built at `bench/**` and its contract,
measurements and limits are at `docs/bench-taskset.md`.

**Why, stated plainly.** `ledger`'s schema `{id, kind, amount, owner, link}` admits exactly
**9 cheap shapes**. Replicates of a shape are correlated, so effective n is bounded by
`shapes / rho` whatever the corpus size — against the **61 effective paired tasks** this
project's own power function requires, a vertical asymptote at `rho = 9 / 61 = 0.1475`.
Going from 40 records to 400 multiplies replicates and adds zero shapes. Run 3d then scored
an exact **23/23 tie on both arms**, which is the same fact arriving as saturation: a 0/1
reward needs tasks the policy *sometimes* solves, and both saturation and uniform failure
produce groups with no variance and so no advantage. A5's extension bought harder tasks of
the same nine shapes; A3's 242 tasks would have bought power to detect nothing. Neither
answers this.

BIRD dev supplies **1534 questions over 277 fine clause-skeleton shapes** (25 coarse), and
it is the only candidate found with a *published sub-1B number* against which to site the
frontier band: SLM-SQL reports **0.5B → 56.87% EX** with a **+31.4 pt** average gain,
implying an untrained 0.5B near **25% EX** — inside the 20–80% band a 0/1 reward needs.
That last figure is arithmetic on a published aggregate, not a published untrained number,
and §S1 below is predicted with a band wide enough to say so.

**What this amendment does NOT license:**

- **No comparison across instruments is admissible.** Runs 1 through 2h were scored on
  `ledger`'s 14 tasks, runs 3a through 3d on its 29. Any future run is scored on BIRD. A
  score from one is not a score from the other, and the three must never appear in the same
  table as though they were. `docs/results-untrained.md` is unaffected and is not reopened.
- **H1 through H5 stay byte-identical and stay adjudicated as they are.** §6 fired; the
  premise is dead and a new taskset cannot resurrect it.
- **A6/N1's interaction does not transfer, and this is the central problem with this
  amendment.** N1 predicted the effect is an interaction — PTC ahead by ≥ 25 pp on the
  full-scan tier, flat or behind on the cheap tier — and that prediction rests on a
  structural contrast `ledger` had and **BIRD does not have**: summing 40 records is either
  one program with a loop or forty separate tool calls. **A BIRD task is one SQL query,
  which is one tool call on either arm.** The "one program versus forty calls" contrast
  that N1's mechanism is about is simply absent. BIRD's `simple`/`moderate`/`challenging`
  labels are a human annotation of question difficulty, not a call-count tier:
  `docs/bench-taskset.md` §6.2 measures that **20 clause-skeleton shapes appear in all
  three tiers**, so the annotation is not even a structural property of the query.
  Therefore **this instrument fixes the power and saturation defects while losing the
  mechanism A6 signed.** It cannot be reported as evidence for or against N1. What question
  it *does* answer is §"The question" below, and that question is **new** and needs this
  signature.
- **Spider is NOT admitted by this amendment.** It was never downloaded. `load_spider()`
  is verified against Spider's documented layout and a layout fixture, and against no real
  archive, so admitting it here would license a corpus nobody has executed a query
  against. It is admissible only by a later amendment, after a run against the real
  archive. This is the narrower claim: BIRD dev, and nothing else.
- **The row comparison is decided: set-based, which is official BIRD.** Official
  `evaluation.py` compares `set(predicted) == set(gold)`. The stricter multiset is more
  defensible in isolation, but comparability to the published sub-1B numbers that site the
  frontier band in this very amendment is the entire reason for leaving a self-authored
  taskset, and a multiset number is comparable to none of them. **Set is the headline;
  multiset is a disclosed sensitivity check.** This reverses the instruction the lane was
  given — the brief wrongly called multiset "BIRD's convention" — and the reversal is
  recorded rather than quietly applied, per this repo's convention. `bench/score.py`
  defaults to `set` and a test pins the default, which until 2026-10-12 nothing did: every
  comparison test passed `compare=` explicitly, so the one value a caller gets by saying
  nothing was the one value nothing checked.
- **The construct-validity handicap changes character rather than improving.** `ledger` was
  self-authored, which is a disclosed handicap, and had one compensating virtue: it could
  not have been in any model's pretraining data. **BIRD dev has been public since 2023 and
  no contamination check has been run.** Trading a self-authored construct for a public
  benchmark trades one validity threat for another. The 25% band estimate is itself drawn
  from a *trained* published number and inherits the same exposure.

## Scope: what this instrument is admitted FOR

Stated as a limit rather than left as a caveat, because the preceding section argues it
and a reader skimming would still mistake a BIRD number for an N1 result.

**Admitted for H3, H4 and H5** — the in-harness training gain, and whether it survives a
harness swap. Those are the project's only live hypotheses: §6 fired, H1 is dead on sign,
and the +6.8 pp replication target is retired with it. H3's 13.5 pp needs **59 paired
tasks** at band-centre discordance, which BIRD reaches at any plausible rho. That is the
measurement this instrument exists to make possible.

**Not admitted for N1, or for any claim about the action channel's interaction with call
count.** The contrast N1's mechanism lives in is absent from BIRD by construction. No
table, abstract or figure may place a BIRD number alongside an N1 prediction.

**The sequence that fills the manifest, in order, with no step skipped:**

1. A seeded stratified draw from BIRD dev (`bench/suite.py`).
2. The **free** dead-group probe measures **per-task** solve rates on
   `unsloth/Qwen3-0.6B` — the policy actually being trained, not a proxy.
3. `bench/frontier/manifest.json` is written **from that measurement**.
4. `train/guards.py`'s §344 gate opens, and only then.

**`solve_rate_min`/`max` must never be filled from the ~25% estimate in this amendment.**
That figure is a *marginal* over a corpus; the gate reads *per-task* rates, and the two
are not interchangeable. At the same marginal 0.25 and G=4, a suite where every task sits
at p=0.25 has a mean dead-group fraction of 0.320 and is trainable, while a suite where a
quarter of tasks are always solved and three quarters never are reads **1.000** and is
not. The two are indistinguishable as a marginal. The gate also requires `n_tasks >= 59`,
derived from the power function rather than stored, because the band is a band over the
*retained* subset and so conformant by construction: without that floor a suite that drew
198 tasks and kept three passed every band check.

## The question

**Does the action channel change a 0.6B model's execution accuracy on text-to-SQL, on a
taskset where neither arm is saturated?** Not A6's question. A6 asked whether forcing the
action to be expressed as a program makes a model *compute* where free text lets it guess,
and its evidence was bash retrieving 40 records correctly and then mis-summing fifteen
numbers in context. That mechanism needs a multi-call task to exist in. On BIRD the model
emits one query and the database does the computing, so what remains testable is the
narrower and less interesting question above: whether the channel costs or buys anything
when the task is a single call on either arm.

**Stated as a prediction rather than a description:** §S4 predicts the answer is
essentially *no*, and says so numerically, because the mechanism that would make it *yes*
has been removed by the change of instrument. **If the owner wants A6's mechanism tested,
BIRD is the wrong instrument and this amendment should be rejected in favour of a taskset
with a genuine call-count tier.** That is the decision this draft exists to put in front of
the owner, and it is not one this lane can make.

## Signed predictions

Labelled `S1`–`S5` to keep them distinct from §4's `H` series and A6's `N` series. Each
threshold is numeric. All are to be evaluated on a seeded stratified draw from BIRD dev
(`bench.suite.select`), scored by `bench.score.execution_accuracy`.

- **S1 — the untrained policy lands inside the frontier band.** Predicted untrained 0.6B
  marginal EX on the drawn suite: **between 10% and 40%**, point estimate 25%. *Confidence:
  low-to-moderate* — the point estimate is `56.87 − 31.4` on a published aggregate, not a
  published untrained figure, and the project's model is 0.6B against SLM-SQL's 0.5B. The
  band is wide because the inference is weak.
- **S2 — the instrument is not saturated and not uniformly failing.** Predicted: **neither
  arm scores below 5% or above 95% on any tier**, and no tier produces an exact tie between
  arms. This is the defect that killed `ledger` (23/23 on both arms), stated as a
  falsifiable threshold rather than a hope. *Confidence: moderate.*
- **S3 — BIRD's difficulty annotation carries real difficulty signal for a 0.6B model.**
  Predicted EX **decreasing by ≥ 5 pp per step** across `simple` → `moderate` →
  `challenging`. *Confidence: moderate.* **This is the prediction most worth being wrong
  about.** The annotation is human and is measurably *not* structural — 20 shapes appear in
  all three tiers — so a flat or reversed profile means the tier split carries no
  difficulty signal, any tier-wise analysis on this instrument is meaningless, and §6.2 of
  `docs/bench-taskset.md` becomes the headline rather than a caveat.
- **S4 — the channel effect is small here, and A6's ≥ 25 pp does not reappear.** Predicted
  **|PTC − bash| < 10 pp** on the marginal EX, and the 95% CI on the paired difference
  **includes 0**. *Confidence: moderate.* A single SQL query is one tool call on either
  arm, so the call-count contrast that would produce a large effect is absent by
  construction. A large effect here would mean the channel matters for reasons A6 never
  identified, and would make this instrument more interesting than this amendment claims.
- **S5 — the corpus's gold defect rate stays negligible on the drawn suite.** Predicted
  **≤ 1%** of drawn tasks have a gold query rejected at 30 s and 100 000 rows. Measured on
  the full corpus: **4 of 1534 = 0.26%** rejected, of which only **2 (0.13%) are genuine
  defects** — golds that do not terminate in 60 s (`bird-0518`, `bird-0701`). The other two
  (`bird-0384`, `bird-0406`) are **not defective at all**: their golds legitimately return
  228 765 and 278 230 rows and execute in about a second once the row cap is raised. They
  are excluded by this instrument's `max_rows` bound, which is **this lane's judgement and
  an owner decision** (`docs/bench-taskset.md` §4.3), not a fault in BIRD. *Confidence:
  high* — this is an extrapolation from a completed measurement, not a guess.

## Pre-specified analysis

Paired per task on a shared seeded suite, `ptc/paired.py`, with its bootstrap CI and exact
McNemar — unchanged, and **not to be worked around**: any void rollout on either arm voids
the comparison. Three commitments specific to this instrument:

1. **`validate_golds()` runs before any model call**, and every task it rejects is dropped
   *and disclosed* with its name and the reason, distinguishing a non-terminating gold
   (a corpus defect) from one excluded by the row cap (a bound this project chose). A
   defective task found mid-run voids the comparison; found beforehand it is a disclosed
   exclusion. The excluded list is reported whatever its length, including when empty.
2. **The marginal EX is the headline, and the tier-wise interaction is pre-emptively
   declined as one.** This inverts A6, deliberately. A6 declined the marginal because
   `ledger`'s two tiers answered opposite questions; here the tiers are a human difficulty
   annotation that is not structural and is not shape-disjoint (105 shape-tier
   duplications), so an interaction computed across them is a quantity whose
   interpretation nobody has established. Tier-wise deltas are to be *reported* — S3 needs
   them — and not advanced as the effect.
3. **n is reported as a shape count beside the question count, never as the question count
   alone.** `bench.suite.report()` prints both and prints `rho_max = shapes / n_required`.
   At band-centre discordance the +6.8 pp APEX target of §3 needs **859 paired tasks**
   against 141/154/87 tier shapes, i.e. it is reachable only if within-shape correlation is
   below **0.164 / 0.179 / 0.101**; A6/N1's ≥ 25 pp needs **59** and is reachable at any
   rho. **So this instrument is adequate for a large effect and still inadequate for the
   project's own headline target**, and that sentence must accompany any reported number.
4. **If this instrument is used for a GRPO run, the frontier band is a MEASUREMENT and is
   reported as one.** The per-task solve-rate band that
   `train/guards.py:frontier_taskset_status` gates on must come from
   `bench.frontier.probe` run against the policy being trained, never from S1's marginal
   estimate: a corpus at 25% marginal accuracy composed of tasks solved 0-of-4 or 4-of-4
   yields a dead group on **every** task while reporting a healthy-looking 25%
   (`docs/bench-taskset.md` §9.1). The probe's retention rate — how much of the drawn suite
   is trainable at all — is reported alongside the band, because the band itself is
   conformant by construction once out-of-band tasks are discarded.

## What would falsify this

- **S1 outside 10–40%** means the frontier-band argument that motivated BIRD was wrong.
  Below 10% is uniform failure and the taskset is too hard for a 0.6B policy; above 40%
  means the published arithmetic does not transfer. Either way the instrument needs
  re-siting before it measures anything, and a fifth instrument change is on the table.
- **S2 violated** — a saturated tier or an exact tie — means the replacement reproduced the
  exact defect it was built to remove, and the shape count was not the binding constraint
  after all.
- **S3 flat or reversed** retires tier-wise analysis on this instrument entirely, and with
  it any residual hope of recovering something A6-shaped from BIRD.
- **S4 large and separable** does not confirm A6; it means the channel acts through a
  mechanism neither A6 nor this amendment named, and the finding would need its own
  pre-registration before being claimed as anything.
- **S5 above 1%** means the corpus needs auditing before use, not working around.

## What this still does not fix

`ptc/paired.py:split_tiers` buckets `min_calls == max` against everything else, which is a
**two**-bucket split; BIRD has **three** tiers, so a run collapses to
`challenging` against `simple + moderate`. The change that would be required is written
into `docs/bench-taskset.md` §6.1 and **has deliberately not been made** — which pair of
tiers constitutes "the interaction" is a pre-registration question, not a code question.

Beyond that: EX is not semantic equivalence, so a correct query with an extra column scores
wrong; the tiers are not shape-disjoint, so the interaction's components are correlated
through 105 shape-tier duplications by an amount nobody has quantified; Spider was never
downloaded, so `load_spider()` is verified against the documentation and not against the
archive; contamination is unchecked; there is still one model behind one unaudited relay;
no run repeats; and `bench` is absent from `pytest.ini`'s `testpaths`, so its 50 tests are
skipped by a bare `pytest`.

**A confirmed S-series on this instrument is a reason to build a better instrument, not a
result to publish.** The Harness-Bench request in `docs/licence-requests.md` remains the
only fix that does not have the self-authorship or the contamination problem, and this
amendment does not change that.

---

**Signed 2026-10-12** under the owner's standing instruction this session that every
decision which does not spend money is the agent's to take. The delegation is recorded
here rather than implied, because every amendment before A7 was signed by him directly.
Five choices inside this amendment were taken under that delegation and are named so a
reader can discount them: admitting BIRD at all; narrowing it to H3/H4/H5 and refusing it
for N1; set-based comparison over multiset; excluding Spider; and raising the row ceiling
to 500,000. **No measurement requiring this amendment has been run at the time of
signing** — `bench/frontier/manifest.json` does not exist, `train/guards.py`'s gate is
shut, and the git timestamp is the evidence that this precedes the data.

---

### A9 — 2026-10-14, after the caching audit: the dollar ratio is an upper bound, and the condition favours bash — UNSIGNED

**Status: UNSIGNED.** Drafted by Claude under Nikolas' direction. It restates a condition on
A7's cost claim and records the first external corroboration this result has had. It is not
an owner's signature on the amendment.

**What this does not touch.** The token ratio (8.0-10.7x as reported, 6.9-8.9x de-inflated),
the mechanism, and the sign of the cost result. Nothing here is a withdrawal.

**The condition, which A7 stated too weakly.** A7 says the rates are "one relay on one date,
not a provider price list", and that the dollars are "an estimate with a stated floor". Both
are true and both are insufficient, because neither names the *direction* of the bias. The
relay reported **zero cached input tokens on both arms**. Run 3d's own table
(`~/scratch/co-train-run3d/run.log:15`):

```
prompt tokens (billed)     2229481    208780
cached tokens                    0         0
```

`ptc/metrics.py:244` reads `cached_input_tokens` and `:321` raises `cost_is_upper_bound` when
a cached price is missing, so the instrument was built to see caching. It saw none. Every
input token in every admissible run is therefore priced at the full uncached rate.

**That is not neutral between the arms.** bash re-sends its transcript once per turn, so its
prompt is a long, stable, growing prefix -- the ideal prefix-cache hit pattern. PTC sends
short prompts that vary per call and cache poorly. Providers bill cache reads at a fraction
of uncached input. **So a no-cache billing basis maximises exactly the ratio this project
reports.** `research/02-synthesis.md:196-197` already held the mechanism: *"r = 0.15 between
token reduction and cost reduction. Cause is cache dynamics: compression breaks prefix
caching, and cache-read tokens are billed at a fraction of uncached input."* The mechanism
was documented and then measured under the one condition where it cannot bite.

**Restated:** `6.1-8.2x dollars per solved task` is an **upper bound conditioned on no prefix
caching**, and the amount by which prefix caching would compress it is **unmeasured**. Only a
run against an endpoint that reports `cached_input_tokens` settles it.

**External corroboration, recorded because it is the first this result has had.** HarnessTax
(UC Berkeley and Arena Intelligence Inc.; Pan, Yang, Arabzadeh, Chiang, Stoica, Zaharia --
https://harnesstax.github.io/) evaluates 21 model-harness pairs over 7 models and 3 harnesses
on SWE-bench Lite and Terminal-Bench 2.0, 30 tasks x 3 repetitions, bootstrap intervals, on a
fixed direct-API price list:

- *"Harness choice has little effect on task success rate, but can significantly affect the
  cost. The same model can achieve similar success rates at up to 5x costs."*
- Claude Fable 5: 97.8% in Claude Code, 96.7% in Codex, 96.7% in Pi -- Claude Code at about
  **2x Pi** ($1.33 vs $0.67). Across shared models Claude Code is **2.0x Pi** and **1.6x
  Codex** on SWE-bench Lite. Harness effect on success rate within **+/-2%**.
- *"Claude Code's mean initial context is over 10x Pi's"* -- the same mechanism, on real
  harnesses rather than a self-authored pair.

This project's finding is the same claim, with the same metric, at a larger effect size, on
n=29 with one model behind one unaudited relay. **The gap between their ~2x and this
project's 6.1-8.2x is a caching question, not a disagreement**, and the paragraph above is
why.

Also recorded: Reason Machines (https://reasonmachines.com, Agent 1.1 post dated 2026-10-10)
ships a product on this premise -- *"The model sets the pass rate; the harness sets the
bill"* -- reports cost per solved task as its headline metric, cites HarnessTax, and states
that *"going from 95% to 98% [cache hit rate] cut one modelled bill by about 17%."* Its
`codemode` tool is this project's PTC arm under another name. **The co-primary this project
treats as its surviving result is a solved and commercialised question elsewhere.** That
bears on what this instrument should be pointed at next, and it is the honest reason to stop
describing the cost ratio as this project's contribution.

**What would settle A9:** one paired run on an endpoint that reports `cached_input_tokens`,
with `price_cached` supplied, so `cost_is_upper_bound` can go false. Until then the dollar
figure carries the condition in the same sentence as the number, every time it is stated.
