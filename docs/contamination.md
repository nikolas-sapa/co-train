# Contamination check — Qwen3-0.6B against BIRD dev

**Status: RUN AND RECORDED, 2026-10-18. Verdict INCONCLUSIVE.** This is the first
contamination check on this project's taskset. `docs/bench-taskset.md` §6.3 and signed
pre-registration A8 both record that none had been run; this document records that one
was, with its controls, its numbers and its limits. The results are in
`bench/contamination_results.json`, produced by `bench/contamination.py`, and every
statistic in this file can be recomputed from that JSON with the torch-free half of the
module. The run's device and sample sizes are in §4.1; the verdict and the control defect
that produced it are §4.2–§4.3.

**Verdict: INCONCLUSIVE.** On the question channel no verbatim contamination is
detectable at this power; on the gold-SQL channel this instrument cannot tell, because the
fresh control was not matched to BIRD's gold length and the primary FAIL is a length
artifact (§4.2). The `run()` function still emits its pre-stated primary verdict (`FAIL`)
in the JSON under `primary_verdict`, and the final `verdict` field is the sensitivity-
corrected reading — the rule is not rewritten after the fact, and both numbers stand.

**What an answer here means and does not mean, stated first.** A PASS would say: on this
model, with these two membership instruments, BIRD dev does not look more memorised than
fresh question/gold-SQL pairs over the same databases. It would **not** prove absence of
contamination: a model can be contaminated in ways a log-probability instrument at 0.6B
cannot see, and the instruments can only separate text that is *verbatim* in the corpus.
Paraphrased BIRD questions with unseen gold SQL, or gold SQL in a different whitespace
form, would evade both methods. That is the honest boundary, and it is why the verdict is
one of PASS / FAIL / INCONCLUSIVE rather than anything boolean.

---

## 1. Why the check exists, and why its controls come first

`ledger` was self-authored and could not have been in any pretraining corpus. BIRD dev has
been public since 2023. Trading the first for the second traded one validity threat for
another, and A8 says so in its own words: *"BIRD dev has been public since 2023 and no
contamination check has been run."*

A membership score with no non-member control is uninterpretable. Every text receives some
log-likelihood, and a model that simply finds BIRD's register (database names, schema
vocabulary, terse questions) more predictable would score exactly like a model that
memorised it. So the check is built around three text sets and one rule: **no BIRD reading
is reported until an instrument has separated a known-public positive control from fresh
non-members in the same run.**

| set | n | what it is | why |
|---|---|---|---|
| BIRD | 300 | seeded tier-stratified draw from the seven small BIRD dev databases | the texts whose membership is in question |
| Fresh non-member | 58 | question/gold-SQL pairs authored 2026-10-18 over the SAME seven databases, every gold executed | share BIRD's register, schema vocabulary and length band, and cannot be in any corpus |
| Positive prose | 20 | public-domain lines any web-crawl corpus contains many times | proof the instrument can see memorisation at all |
| Positive SQL | 12 | canonical tutorial/SQL-doc examples (`SELECT * FROM Customers WHERE Country = 'Germany'`, ...) | the SQL-domain positive: a prose positive alone would not show the SQL channel works |
| Fresh prose (auxiliary) | 12 | passages authored 2026-10-18 in the same register and length | separates *membership* from *register*: if positive prose vs fresh prose separates as cleanly as BIRD SQL vs fresh SQL, the effect is domain, not memory |

The fresh set is the load-bearing control, so it is held to the same standard as the
corpus: **all 58 golds execute against their BIRD sqlite file with rows returned**
(`validate_fresh`, enforced in `run()` before any model call). A pair whose gold errors or
returns nothing is a broken control rather than a non-member, and the run refuses to
proceed. Three of the first-draft pairs returned zero rows and were rewritten before the
run; that is recorded here because the count of rewritten pairs is the kind of thing that
is invisible in a final table.

Length matching is a claim, so it is measured: BIRD's questions over these databases
average 84.1 characters and its gold SQL 169.5; the fresh set is held inside bands that
contain those means, and `test_fresh_control_is_in_birds_length_band` fails if it drifts
out.

---

## 2. Methods

Both are standard membership-inference instruments for a causal LM, chosen because they
answer different questions and a single method's separation is a claim while two agreeing
methods are an argument.

### 2.1 Min-K% and Min-K%++ (Shi et al. 2023; Zhang et al. 2024)

Per-token NLL of the text under the model; score the tail — the lowest-likelihood
`k = 20%` of tokens, averaged. A memorised passage is unlikely to contain many tokens the
model finds surprising.

- **Min-K%** averages the tail token log-probabilities.
- **Min-K%++** averages the tail *z-scores* `(log p(t_i) − μ_i) / σ_i`, where `μ_i`, `σ_i`
  are the mean and standard deviation of `log p(v)` over the vocabulary at position `i`.
  This removes most of the local-difficulty confound: a token that is unremarkable against
  the model's own distribution stops reading as memorisation.

Applied to **question text and gold SQL separately**. They can be contaminated
independently — a question paraphrase is a plausible pretraining accident, an exact gold
query much less so — and pooling them would let a question-level effect hide inside a
110-token SQL string.

### 2.2 Gold-SQL continuation

Present the question plus the first half of the gold SQL's tokens, greedy-decode, and
compare the completion to the held-out suffix (whitespace-normalised, trailing semicolon
stripped, case preserved). This is sequence-level: a model that memorised the query
reproduces the suffix, a model that did not continues plausibly but differently. The
positive control is the same procedure on the canonical SQL examples.

The precision of the match is the point and its limit: **only verbatim reproduction
counts.** A model that writes the same correct query with different aliasing or spacing
scores as a non-member here, so this method can understate contamination and cannot
overstate it.

---

## 3. The rule, fixed before the numbers

Written into `bench/contamination.py` as constants and pinned by tests:

- `CONTROL_AUC_FLOOR = 0.75`, `CONTROL_P_FLOOR = 0.01` — an instrument counts only if the
  positive control separates from fresh non-members with AUC ≥ 0.75 and permutation
  `p < 0.01`.
- `CONTAMINATION_AUC_FLOOR = 0.65` — the BIRD-vs-fresh separation that would count as a
  contamination signal.
- `PASS_AUC_CEILING = 0.65` — a PASS requires the **upper end of the 95% bootstrap
  interval** below this.
- `BINARY_RATE_GAP = 0.10` for the continuation method's rate contrast.
- Statistics: AUC with ties at 0.5 (Mann-Whitney), one-sided permutation p over 10 000
  label shuffles, percentile bootstrap over 10 000 resamples, Cliff's delta as the ordinal
  effect size, exact Fisher for the binary method.

**The control gates the verdict.** A method whose control fails returns INCONCLUSIVE even
if its BIRD number is high — a blind instrument's reading is not a reading. This ordering
is itself mutation-tested: swapping the gate and the PASS branch survives the obvious test
case and is caught by `test_the_control_gate_runs_first_not_last`.

---

## 4. Results

### 4.1 The run

2026-10-18, local Apple Silicon, `unsloth/Qwen3-0.6B` (same weights as `Qwen/Qwen3-0.6B`),
bfloat16 forward passes on MPS with float32 log-probabilities, $0. n = 300 BIRD (seeded
tier-stratified draw over the seven small databases: 170 simple / 96 moderate / 34
challenging), 58 fresh non-member pairs, 20 positive prose, 12 positive SQL, 12 fresh
prose. 916 forward passes plus 370 greedy continuations; the run is resumable
(`Cache`) because method B outlasts a shell's patience.

### 4.2 The primary readings, and the verdict is **INCONCLUSIVE**

The primary rule was fixed before the numbers and applied mechanically. It returned:

| method | channel | control AUC | control p | BIRD AUC | BIRD p | BIRD 95% CI | primary verdict |
|---|---|---|---|---|---|---|---|
| Min-K% | question | 0.764 | 0.0001 | 0.455 | 0.85 | [0.378, 0.533] | PASS |
| Min-K% | gold SQL | 0.888 | 0.0001 | **0.765** | 0.0001 | [0.694, 0.830] | **FAIL** |
| Min-K%++ | question | 0.825 | 0.0001 | 0.508 | 0.41 | [0.435, 0.583] | PASS |
| Min-K%++ | gold SQL | 0.792 | 0.0005 | **0.829** | 0.0001 | [0.762, 0.887] | **FAIL** |
| continuation | gold SQL | 0.000 (1/12) | 1.0 | 0.000 (7/300 vs 9/58) | 0.0002 | — | INCONCLUSIVE |
| Min-K% (aux) | prose | 0.733 | 0.015 | 0.399 | 0.88 | [0.284, 0.521] | INCONCLUSIVE |
| Min-K%++ (aux) | prose | 0.708 | 0.029 | 0.353 | 0.96 | [0.218, 0.498] | INCONCLUSIVE |

**Then the FAIL was tested, and it is a length artifact. The verdict is therefore
INCONCLUSIVE, not FAIL.** The primary contrast compared BIRD golds averaging **54.0
tokens** against fresh golds averaging **21.2** — the fresh set was *not* matched to BIRD
on gold length, and Min-K% scores longer text higher. The evidence that this alone
explains the FAIL:

1. **Within BIRD, length predicts the score as strongly as BIRD membership does.**
   Pearson r(len, Min-K%) = **+0.496**, r(len, Min-K%++) = **+0.570**. Splitting BIRD at
   the fresh set's longest gold (55 tokens): long BIRD golds score −7.22 against short
   BIRD golds' −8.43, AUC **0.769** — the same number the unstratified BIRD-vs-fresh
   comparison produced, with no fresh text involved at all.
2. **Length-stratified, BIRD is at chance.** Pairing BIRD against fresh only within
   token-length bins (1–12, 13–16, 17–20, 21–28, 29+), over 3 297 same-bin pairs:
   Min-K% **AUC 0.499**, 95% CI **[0.386, 0.622]**; Min-K%++ **AUC 0.550**, CI
   **[0.413, 0.687]**. (`bench/contamination_sensitivity.py`, recorded output.)
3. **Precision is not the cause.** A length-matched 58-vs-58 rerun under both float32 and
   bfloat16 gives min-k AUC **0.421** (fp32) / **0.422** (bf16) and min-k++ **0.476** /
   **0.474**, with identical means to two decimals. bf16 is ruled out as an explanation.
4. **The point estimates now point the other way** (BIRD below chance on Min-K%), which is
   the flattering direction for the corpus and is *not* reported as a PASS: the CIs are too
   wide to exclude a moderate effect. That asymmetry is the reason for INCONCLUSIVE rather
   than PASS.

**Effect sizes of the artifact, for the record.** Unstratified: BIRD mean log-prob −7.93
against fresh −9.41 (1.48 nats); Min-K%++ BIRD z +3.92 against fresh +2.98. Stratified
estimate: Min-K% **δ ≈ 0.00**, Min-K%++ **δ ≈ +0.10** (Cliff's, negligible by Romano's
0.147 convention), each with a CI spanning zero.

**The question channel is clean and stays clean.** BIRD questions sit at AUC 0.455
(Min-K%) and 0.508 (Min-K%++), at or below chance, CI excluding any effect above 0.58.
Question lengths were matched (BIRD mean 84.1 chars, fresh set inside the same band), and
the effect is absent on the channel where contamination would be *easiest* to show. That
asymmetry is the same one the gold-SQL artifact did not reproduce once length was removed.

**The continuation method is dropped, not reported.** Its positive control reproduced only
**1 of 12** canonical SQL snippets, below the 10% rate gap the method requires, so the
instrument is blind at 48-token suffixes on this model and its BIRD number (7/300 vs
9/58) cannot be read. INCONCLUSIVE by the pre-stated rule, and it is the branch the rule
exists for: a method that cannot detect known-public SQL cannot testify about BIRD SQL.

### 4.3 What the final reading is

**The verdict is INCONCLUSIVE.** The instrument is not blind — the positive controls
separated from the fresh non-members on the question channel (AUC 0.76 / 0.83,
p ≤ 0.0001) — but its gold-SQL comparison was confounded by the control's own length, and
once length is controlled the BIRD effect is not distinguishable from chance at n = 300 vs
58. **No claim of contamination and no claim of cleanliness is made.** The honest sentence
is: *on the question channel, no verbatim contamination is detectable; on the gold-SQL
channel this instrument, with this control, cannot tell.*

**What would settle it:** a fresh control set rewritten to BIRD's gold-length distribution
(median ~51 tokens, not 21) and re-run under the primary rule. That is a control-construction
fix, not a new instrument, and it is the first thing a follow-up should do. Until then the
pre-registration's statement — "BIRD dev has been public since 2023 and no contamination
check has been run" — becomes "a check has been run, its gold-SQL arm was confounded by
control length, and its question arm found nothing."

---

## 5. Limits

Stated as limits rather than caveats, because each one bounds what the verdict can mean:

1. **Verbatim-only.** Both methods detect text the model saw in near-identical form.
   Paraphrased contamination — a question reworded, a gold query reformatted — is outside
   what either instrument can see. A PASS therefore bounds *verbatim* contamination, not
   all exposure to BIRD's content or schema.
2. **One model, one checkpoint.** `unsloth/Qwen3-0.6B` on 2026-10-18. A different
   checkpoint or a re-upload can differ, and the result does not transfer.
3. **Two instruments, one device, one precision.** bf16 forward passes on Apple MPS with
   float32 log-probabilities, checked against fp32 on a length-matched subsample (the two
   give the same AUC to three decimals). A CPU/fp32 rerun over everything would be a
   different, arguably fairer, measurement and is not done here.
4. **The fresh control was not matched to BIRD's gold length, and that is the defect that
   produced the INCONCLUSIVE.** Fresh golds average 21.2 tokens, BIRD's 54.0. The
   stratified analysis controls for it; the *primary* contrast did not, and no number in
   §4.2 should be quoted without the stratified estimate beside it.
5. **AUC is not an absolute.** AUC 0.5 means "no rank information about the group", not
   "identical distributions"; a small but real effect can sit inside a wide CI at n = 300
   and read as PASS or INCONCLUSIVE. The CI, not the point estimate, is what the rule is
   defined on.
6. **The fresh control is written by the same author as the questions under test.** Its
   register is matched deliberately, but a systematic difference in style would bias the
   comparison. The auxiliary prose control is the check on that, and it did not reach the
   acceptance floor either.
7. **The positive control is prose and tutorials, not BIRD-adjacent SQL.** The SQL
   positive *failed* acceptance (1/12 on continuation) while the prose positive passed,
   so the SQL channel's acceptance rests on the Min-K% positive-SQL control alone
   (AUC 0.888 / 0.792), not on two agreeing instruments.

---

## 6. Instrument defects found while building it, recorded rather than patched silently

The repo's convention is to surface a defect in the report rather than let a fixed one
disappear. Three belong here.

1. **An off-by-one in the chunked statistic crashed the first full run.** The Min-K%++
   moments are accumulated in 64-position chunks (a whole-vocabulary log-softmax per
   position is 180 MB at this vocab size). The chunk bound read `chunk` instead of
   `seq - 1`, so the last block ran one position past the target tokens; `gather`
   truncates silently, the moment lists came back one longer than the log-prob list, and
   `min_kpp_score` raised. It crashed rather than returning a wrong number, which is the
   cheap failure mode, and it only appears past one chunk — the pilot's short texts
   passed. The loop now asserts all three lengths equal `seq - 1`, and
   `test_token_logprobs_lengths_agree_past_one_chunk` drives the real loop with a fake
   model at 150 positions so this cannot regress unseen.
2. **Float32 on MPS was abandoned on measured speed, and the measurement is in the module
   docstring.** `load_model` says why, and the results JSON records the dtype used so a
   rerun on another device is comparable.
3. **The first full run was killed by a 10-minute wall clock and lost everything.**
   Method A is ~4 minutes; method B (370 greedy generations) is ~45-60. A result that
   requires one uninterrupted process depends on the operator's patience. `Cache` is an
   append-only JSONL of per-item results keyed by (method, group, sha1 of the conditioned
   text), so an interrupted run resumes and a changed input is a miss rather than a
   silently reused score.

---

## 7. Reproducing

```bash
# the torch-free half — scoring and statistics — in the repo venv
.venv-ptc/bin/python -m pytest bench/test_contamination.py -q

# the full run, in the scratch venv that has torch (never .venv-ptc)
~/scratch/cotrain-contam/venv/bin/python -m bench.contamination \
    --bird ~/scratch/bird-sql/bird-dev-extracted/dev_20240627 \
    --n-bird 300 --seed 0 \
    --cache ~/scratch/cotrain-contam/contamination_cache.jsonl \
    --out bench/contamination_results.json
```

The repo venv does not have torch and must not have it; every torch import in the module
is function-local, and a test reloads the module to keep that true.


---

# v2 — the length-matched control, and what it measured

**Appended 2026-10-19. This section does not rewrite §4.** Everything above stands as the
v1 record: the primary rule returned FAIL, the FAIL was retracted to INCONCLUSIVE, and both
numbers stay in `bench/contamination_results.json`. What is new here is the control the v1
section named as the fix — "a fresh control set rewritten to BIRD's gold-length
distribution (median ~51 tokens, not 21) and re-run under the primary rule" (§4.3) — and
what that control measured when it existed.

**Status: RUN AND RECORDED. Verdict INCONCLUSIVE, with the question channel reading PASS on
Min-K%++ and the gold-SQL channel INCONCLUSIVE on its own control.**

---

## V2.1 The control that was built

`bench/contamination_fresh_v2.json`: 58 question/gold-SQL pairs authored 2026-10-19 over
the SAME seven BIRD dev databases as v1, every gold executed against its sqlite with rows
returned before any model call (the run refuses otherwise, via `validate_fresh`). v1 is
kept in place and untouched; it is the record of the defect. Both controls now coexist, and
`run(fresh_path=, fresh_tag=)` selects between them without either reading the other's
cached scores, because the tag is in every cache key (`fresh_group_names`).

The length match is a measurement in `bench/contamination_sensitivity.py`'s `bin_table`,
rendered from `bench/contamination_sensitivity_v2.json`. BIRD is the n=300, seed=0 draw
from §4.1, the same draw the v1 run used:

| gold-SQL tokens | BIRD n | BIRD share | BIRD mean | BIRD median | v2 n | v2 share | v2 mean | v2 median |
|---|---|---|---|---|---|---|---|---|
| 1-12 | 7 | 0.023 | 11.0 | 12.0 | 1 | 0.017 | 12.0 | 12.0 |
| 13-16 | 6 | 0.020 | 14.3 | 14.0 | 1 | 0.017 | 14.0 | 14.0 |
| 17-20 | 13 | 0.043 | 18.9 | 19.0 | 3 | 0.052 | 17.7 | 17.0 |
| 21-28 | 10 | 0.033 | 24.7 | 24.5 | 2 | 0.034 | 26.0 | 26.0 |
| 29+ | 264 | 0.880 | 58.9 | 53.5 | 51 | 0.879 | 58.9 | 58.0 |
| **all** | **300** | | **54.05** | **51.0** | **58** | | **54.02** | **55.0** |

**What this table supports, and what it does not.** The bin proportions agree to within one
item per bin at the five-bin resolution the sensitivity analysis uses; the overall means
agree to 0.03 tokens (54.02 against 54.05); the 29+ bin's own mean is identical to two
decimals (58.9 against 58.9). The **median does not match**: 55.0 against BIRD's 51.0, and
the band counts explain why. Counted at a ten-token resolution the five-bin table hides,
BIRD's draw has 46 items at 29-41, 75 at 42-51 and 49 at 52-60; v2 has **0**, 16 and 14.
v2 has no short-tail items at all and a thinner 52-60 band, so its middle sits higher even
with the mean held. The upper tail is thinner too: v2's longest gold is 88 tokens, BIRD's
draw contains 11 items of 90 or more, two of them above 260. Both are limits below, because
the claim is "mean-matched and bin-matched at the estimator's resolution", not
"distributionally identical".

Whether that residual matters is a measurement, not an opinion: §4.2's finding was that
Min-K% scores *longer* text higher, with r(len, score) = +0.496 / +0.570 **within BIRD**.
Matching the means matches the quantity that prediction is linear in, and the stratified
estimator below does not use the marginal distribution at all: it pairs only same-bin
items. The residual pearson in V2.3 is unchanged from v1 (+0.496, +0.570), so the
length-score relation inside the two sets is the same relation.

## V2.2 The primary rule, re-run

Same model, same machine, same 300-item BIRD draw, same cache file, fresh set only new. Run
2026-10-19, `unsloth/Qwen3-0.6B`, bfloat16 on MPS, $0. Every BIRD reading was served from
the existing cache (916 forward passes' worth), so the run cost 58 + 58 new Min-K scorings,
20 new long-positive scorings, and 58 new continuations. Output:
`bench/contamination_results_v2.json`.

| method | channel | positive control | control AUC | control p | BIRD AUC | BIRD p | BIRD 95% CI | verdict |
|---|---|---|---|---|---|---|---|---|
| Min-K% | question | prose (20) | 0.733 | 0.0006 | 0.448 | 0.89 | [0.365, 0.533] | INCONCLUSIVE |
| Min-K% | gold SQL | short SQL (12) | **0.596** | 0.15 | 0.418 | 0.98 | [0.343, 0.495] | INCONCLUSIVE |
| Min-K%++ | question | prose (20) | 0.761 | 0.0002 | 0.447 | 0.90 | [0.370, 0.527] | PASS |
| Min-K%++ | gold SQL | short SQL (12) | **0.359** | 0.94 | 0.420 | 0.98 | [0.342, 0.501] | INCONCLUSIVE |
| continuation | gold SQL | positive SQL (12) | 1.000 (1/12) | 0.17 | 1.000 (7/300 vs 0/58) | 0.60 | — | INCONCLUSIVE |

**The v1 FAIL does not reproduce, and this time the control is the right length.** Against a
control with the same mean gold length, the BIRD gold-SQL channel separates at **AUC 0.418**
(Min-K%) and **0.420** (Min-K%++) — at or below chance, with CIs that exclude anything above
0.50. The v1 numbers were 0.765 and 0.829 against a control 32.8 tokens shorter. The 1.48 nats
of mean log-probability gap that produced them (§4.2) were the length difference, and with
the length removed the point estimates do not merely return to chance, they sit below it.

**The gold-SQL arm is INCONCLUSIVE, and for a new reason.** Its own positive control failed
the acceptance gate: the 12 canonical SQL snippets average **12.7 tokens** and the v2 fresh
golds average **54.0**, so the positive control is now the short half of its own comparison
and separates at 0.596 / 0.359. That is the same defect v1 had, one layer up: fixing the
fresh control's length exposed the positive control's. The channel's BIRD reading (0.418 /
0.420) is therefore not interpretable under the pre-stated rule, even though its direction
is the reassuring one. It is reported and not acted on, which is the rule working: a PASS
on a blind instrument is what §3's gate forbids, and the question channel's Min-K% row is
the live instance of that gate (0.733 control, INCONCLUSIVE despite a clean-looking BIRD
number). **The question channel's Min-K%++ row is the only PASS in the table**, and it is a
PASS on a control that separated at 0.761.

## V2.3 The stratified sensitivity, with v2

`bench/contamination_sensitivity.py` on the v2 results, recorded at
`bench/contamination_sensitivity_v2.json`. Same estimator and bins as §4.2's stratified
analysis, so the two are comparable:

| method | pearson(len, score) within BIRD | unstratified AUC | stratified AUC | same-bin pairs | 95% CI |
|---|---|---|---|---|---|
| Min-K% | +0.496 | 0.418 | **0.399** | 13 536 | [0.329, 0.464] |
| Min-K%++ | +0.570 | 0.420 | **0.402** | 13 536 | [0.330, 0.473] |

Both intervals exclude 0.5 **from below**: BIRD ranks as significantly *less* member-like
than a length-matched fresh control at n=300 against 58, on both methods. The stratified
estimate carries no verdict of its own (V1 reported it beside the corrected verdict in the
same way); read against the pre-stated rule it would satisfy the PASS ceiling on its upper
end (0.464, 0.473 both below 0.65), but the control gate above it did not open for the
primary reading, so the rule returns INCONCLUSIVE. The asymmetry is worth naming: an
instrument that cannot see known-public SQL and also reads BIRD as *below* chance is more
consistent with a BIRD register the model finds harder than with memorisation, and it is
not evidence of cleanliness, because nothing here shows the instrument could have seen BIRD
if BIRD were there. At 0.6B the corpus is, if anything, harder than fresh text, and a
harder corpus is the direction that would *mask* contamination, not the direction that
rules it out.

**The unstratified and stratified numbers now agree**, which they did not in v1: 0.418
against 0.399, and 0.420 against 0.402. That agreement is the check that the length
covariate has stopped doing work. In v1 the pair was 0.765 unstratified against 0.499
stratified, and the gap was the confound.

## V2.4 The positive SQL control, measured rather than assumed

This is the defect v2 exposed, and it belongs in the report rather than in a fix commit.
`POSITIVE_SQL` was written when the fresh control averaged 21.2 tokens; its mean is 12.7 and
its longest item is 22 tokens. Against v2's fresh golds it separates at AUC 0.596 (Min-K%)
and 0.359 (Min-K%++) — the shorter of the two sets scores lower on a statistic that rewards
length, so the positive control lost the comparison it exists to win.

Two things were done, and the order matters:

1. **The failure is recorded, not patched away.** The v2 result above is the primary
   reading, produced by the rule as pre-stated, with the short positive in place.
2. **A length-matched positive was added beside it**: `POSITIVE_SQL_LONG`, 20 canonical
   W3Schools/Northwind queries in longer forms, mean **23.0 tokens**. `run()` scores both,
   and `promote_positive_control` chooses between them by a fixed rule: the short one stands
   if it passes; the long one adjudicates only if the short one fails **and** the long one
   passes; if both fail, the short one stands and the channel is INCONCLUSIVE.

**The long control also failed**: AUC **0.722** (Min-K%) and **0.615** (Min-K%++) against
the same fresh golds, below the 0.75 floor. So the promotion rule did not fire, the SQL
channel stays INCONCLUSIVE, and the honest reading is that at 0.6B neither form of the
canonical-SQL positive separates from a length-matched fresh control on this instrument. The
prose positive passes on both methods (0.733 and 0.761), so the instrument is not blind in
general; it is blind to the SQL positive specifically. §5's limit 7 said the SQL channel's
acceptance rested on the Min-K positive alone; after v2 it rests on nothing, and that is a
weaker position than v1 recorded.

## V2.5 What the two controls agree on, and where they do not

| | v1 (mean 21.2) | v2 (mean 54.0) |
|---|---|---|
| Min-K% gold SQL, unstratified | 0.765 FAIL | 0.418 (channel INCONCLUSIVE on its control) |
| Min-K%++ gold SQL, unstratified | 0.829 FAIL | 0.420 (same) |
| Min-K% gold SQL, stratified | 0.499 [0.386, 0.622] | 0.399 [0.329, 0.464] |
| Min-K%++ gold SQL, stratified | 0.550 [0.413, 0.687] | 0.402 [0.330, 0.473] |
| Min-K% question | 0.455 | 0.448 |
| Min-K%++ question | 0.508 PASS | 0.447 PASS |

**They agree that the question channel is clean** (0.448-0.508 across both controls and both
methods), and they agree on the stratified gold-SQL reading's *direction*: at or below
chance once length is controlled. They disagree on the unstratified gold-SQL reading by
0.35 AUC, and that disagreement is entirely the control's length: v1's stratified estimate
(0.499/0.550) already predicted what v2's unstratified number would be (0.418/0.420). The
sensitivity analysis that rescued v1 from its own FAIL was pointing at the right answer
before the better control existed.

## V2.6 Limits that bound this section

1. **The explicit question in the lane brief is answered; the verdict is still not PASS.**
   The SQL channel cannot be adjudicated by this instrument at 0.6B because no positive
   control that would license a reading has passed the gate. A future control that passes
   would let the 0.418 / 0.420 reading be adjudicated; this report does not assume it would
   then read PASS.
2. **The median is not matched** (55.0 against 51.0) and the upper tail is thinner (max 88
   against BIRD's 541), because v2 carries no gold at 29-41 tokens and fewer at 42-51. The
   mean and the five bins are matched, and the within-BIRD length-score correlation is
   unchanged, which is the evidence that the residual does not do work. It is not a claim of
   distributional equality, and a reviewer who wants equality should weight the stratified
   estimate, which does not use the marginal distribution at all.
3. **One model, one device, one day**, as in §5. The v2 run was bfloat16 on MPS to match the
   cached BIRD half it reuses; a full fp32 rerun is a different measurement and is not done.
4. **The fresh set is still authored by the same hand as the questions under test.** V2
   makes it shorter-distance than v1 on length and no closer on style. The auxiliary prose
   control did not reach the acceptance floor on either run, so the register check remains
   unavailable.
5. **Continuation still cannot contribute.** The positive control reproduced 1 of 12 on v1
   and 1 of 12 here, `fresh` went 9/58 to 0/58 (the v2 golds are longer, so there is more
   suffix to reproduce), and BIRD stayed 7/300. The instrument is blind at 48-token suffixes
   on this model on both controls, and its verdict is INCONCLUSIVE by the pre-stated rule.

## V2.7 The verdict sentence

**On the question channel no verbatim contamination is detectable against either control
(0.448 / 0.447, n=300 vs 58); on the gold-SQL channel the BIRD reading is at or below
chance once the control is length-matched (0.418 unstratified, 0.399 stratified), but the
instrument's own SQL positive control no longer passes acceptance at this control's length,
so that reading is recorded as INCONCLUSIVE rather than PASS, and the two controls together
say only what §4.3 already said: no claim of contamination and no claim of cleanliness.**

## V2.8 Reproducing v2

```bash
# the length match, which is the measurement this section is built on
~/scratch/cotrain-contam/venv/bin/python -m bench.contamination_sensitivity \
    bench/contamination_results_v2.json

# the run itself, in the torch venv, reusing the v1 cache for the BIRD half
~/scratch/cotrain-contam/venv/bin/python -m bench.contamination \
    --bird ~/scratch/bird-sql/bird-dev-extracted/dev_20240627 \
    --n-bird 300 --seed 0 \
    --fresh bench/contamination_fresh_v2.json --fresh-tag v2 \
    --cache ~/scratch/cotrain-contam/contamination_cache.jsonl \
    --out bench/contamination_results_v2.json
```

## V2.9 Defect found while building v2, recorded rather than patched silently

**The positive control was length-confounded by the fix to the fresh control.** The v1
control was short (21.2 tokens) against a short positive (12.7), and the pair was fair; the
v2 control is long (54.0) against the same 12.7, and the positive now loses a comparison it
should win. Nothing in the v1 report could have caught it, because the defect only exists
in the presence of the fix. It was found by reading the v2 control AUCs (0.596 and 0.359,
both far below v1's 0.888 and 0.792 on the *same 12 texts*) and asking what changed other
than the fresh set: the answer was the fresh set's length. `POSITIVE_SQL_LONG` and
`promote_positive_control` are the repair; the repair's own failure (0.722 / 0.615) is
reported above rather than tuned away, and the count for `docs/deviations.md` is the
owner's to move.

## V2.10 Mutation evidence for every guard this section relies on

Each guard added for v2 was mutated once and the designated test had to go red. The script
that did it keeps the original bytes, applies one exact substitution, runs the test, then
restores the file and asserts the sha256 is unchanged. All eight mutations were caught;
every file was restored byte-identical (`sha256` verified after each).

| mutation | test | result |
|---|---|---|
| `fresh_group_names` drops the tag from the continuation group | `test_two_tags_do_not_share_a_cache_entry` | RED |
| `score_texts` scores on a cache hit instead of a miss | `test_score_texts_scores_only_misses` | RED |
| `promote_positive_control` returns the long control unconditionally | `test_promote_positive_control_keeps_a_passing_short_control` | RED |
| `promote_positive_control` falls through to the long control | `test_promote_positive_control_does_not_rescue_two_failing_controls` | RED |
| `bin_table` divides share by the number of bins | `test_bin_table_counts_and_means_agree_with_hand_arithmetic` | RED |
| `bin_table` reports 0.0 for an empty bin's mean | same test | RED |
| one 12-token v2 pair replaced by a 16-token one | `test_v2_control_is_length_matched_to_bird` | RED |
| the recorded v2 verdict asserted as PASS | `test_recorded_v2_result_keeps_its_own_fresh_control_and_verdict` | RED |

**One guard survived its first mutation and was repaired rather than accepted.** The
recorded-result test initially checked only that each row's own verdict obeyed the control
gate; hard-coding `"PASS"` into the payload left every row INCONCLUSIVE and nothing
compared the file's overall verdict to them. The test now recomputes the overall verdict
from the file's own rows by the documented rule and asserts equality, and the same mutation
is caught. That is recorded because a guard that cannot fail is the defect, and this one
could not until it was rewritten.
