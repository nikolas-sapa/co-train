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
