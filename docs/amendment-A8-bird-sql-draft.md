# Amendment A8 — DRAFT, UNSIGNED

**This file is a draft for the owner's review. It is NOT part of
`docs/pre-registration.md`.** That file is append-only and owner-signed; nothing here has
been appended to it, and no measurement requiring this amendment has been run. The
signature line at the foot is deliberately blank.

Drafted in the voice and structure of §A5 and §A6 so that, if signed, it can be appended
with the numbering and wording intact.

**Numbered A8, not A7.** This draft was written as A7 while `docs/pre-registration.md`
ended at A6. A7 was appended to that file at 14:43 on 2026-10-11 for the cost-claim
restatement, so the number was taken before this draft was finished; the TRAIN lane
caught the collision. Renumbered rather than renegotiated: the pre-registration is
append-only and owner-signed, and a draft does not get to reuse a number that a signed
amendment already holds.

---

### A8 — 2026-10-11, BEFORE any run on it: the instrument is replaced, and that resets the benchmark again

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

**Owner signature:** ______________________  **Date:** ____________

*Unsigned. No measurement requiring this amendment has been run.*
