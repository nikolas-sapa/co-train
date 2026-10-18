# Amendment A10 — DRAFT, UNSIGNED

**This file is a draft for the owner's review. It is NOT part of
`docs/pre-registration.md`.** That file is append-only and owner-signed; nothing here has
been appended to it, and the signature line at the foot is deliberately blank.

Drafted in the voice and structure of A5, A6 and A8 so that, if signed, it can be appended
with the numbering and wording intact. A9 is appended unsigned; the next free number above
it is A10.

**What this amendment is.** It records the project's first contamination check, adds the
check itself to the pre-registered analysis of any future BIRD run, and writes down what a
PASS on it does and does not license. It does not change the taskset, the question, or any
signed prediction. If the owner's reading of the result is that it should change what A8
admits, that decision is the owner's and the draft states the options rather than taking
them.

---

### A10 — 2026-10-18, BEFORE the first BIRD measurement: contamination is checked, and a PASS is a bound rather than a clearance

**This amendment closes a hole A8 disclosed and left open.** A8's "what this does NOT
license" section records, in its own words, that *"BIRD dev has been public since 2023 and
no contamination check has been run"*, and that trading a self-authored construct for a
public benchmark *"trades one validity threat for another."* The check has now been run:
`bench/contamination.py`, results at `bench/contamination_results.json`, methods, controls
and limits at `docs/contamination.md`. It ran locally at $0, on the policy the project
trains, against the real BIRD dev corpus.

**Why the check needed a control to be a check at all.** A membership score with no
non-member is uninterpretable: every text gets a likelihood, and a model that simply finds
BIRD's register more predictable would read exactly like a model that memorised it. So the
run carries a fresh non-member control — question/gold-SQL pairs authored over the *same*
seven BIRD databases, every gold executed — and two positive controls (public-domain prose
and canonical tutorial SQL). The fresh set cannot be in any pretraining corpus by
construction, and it shares BIRD's schema vocabulary and length band, which is what makes
it a fair negative rather than an easy one.

**The rule was fixed before the numbers, and it is three-way.** A method counts only if
its positive control separates from the fresh non-members (AUC ≥ 0.75, permutation
`p < 0.01`); a method whose control fails returns INCONCLUSIVE whatever its BIRD number
says, because a blind instrument's reading is not a reading. A PASS requires the upper end
of a 95% bootstrap interval below the contamination floor (AUC 0.65). No threshold was
chosen after seeing BIRD.

**What the result is.** The verdict is **INCONCLUSIVE**, and the reason matters more than
the label. On the question channel, Min-K% and Min-K%++ both return BIRD at chance
(AUC 0.455 and 0.508; 95% CIs [0.378, 0.533] and [0.435, 0.583]) against a fresh control
they *can* see (control AUC 0.764 and 0.825, p ≤ 0.0001). On the gold-SQL channel the
pre-stated rule returned FAIL (AUC 0.765 and 0.829), and that FAIL is a control
construction defect, not a contamination finding: the fresh golds averaged 21.2 tokens
against BIRD's 54.0, the score correlates with length within BIRD itself (r = +0.50 and
+0.57), and length-stratified the effect is at chance (AUC 0.499, CI [0.386, 0.622];
AUC 0.550, CI [0.413, 0.687]). A length-matched 58-vs-58 rerun under float32 and
bfloat16 agrees (AUC 0.42–0.48). Both numbers are kept in the results file — the primary
under `primary_verdict`, the corrected under `verdict` — because deleting the FAIL would
hide the confound and deleting the correction would overstate it. The continuation method
is dropped: its positive control reproduced 1 of 12 canonical SQL snippets, so the
instrument is blind at 48-token suffixes.

**So the sentence A8 wrote changes to:** *"BIRD dev has been public since 2023; a
contamination check has now been run, its question arm found nothing detectable, its
gold-SQL arm was confounded by the control's own length, and its continuation arm was
blind."* That is a smaller sentence than a PASS would be, and it is the one the run
supports.

- **Two methods, both reported, neither privileged.** Min-K%/Min-K%++ on question text and
  gold SQL separately, and gold-SQL continuation (give a prefix, greedily complete, exact-
  match the suffix). The first is token-level, the second sequence-level; they fail in
  different directions, and the report names the method whose control failed rather than
  dropping it silently. It is named here: continuation.
- **The verdict is PASS / FAIL / INCONCLUSIVE, never a boolean, with effect size, CI and
  permutation p.** The numbers for every channel are in `docs/contamination.md` §4.2.

**What this amendment does NOT license, stated as narrowly as A8 stated its own limits:**

- **A PASS is evidence of absence *at this power*, for *verbatim* text, on *this
  checkpoint*.** Both instruments detect a text the model saw in near-identical form. A
  question reworded or a gold query reformatted evades both. So a PASS bounds verbatim
  contamination of `unsloth/Qwen3-0.6B` on 2026-10-18; it does not clear BIRD of every
  form of exposure, and it does not transfer to another checkpoint or another model.
- **A PASS is not a result about training, and cannot be cited as one.** It removes one
  handicap from the instrument's construct validity; it does not make a BIRD number
  comparable to a `ledger` number (A8 already forbids that), and it does not make BIRD
  admissible for N1 (A8 already refuses that).
- **A FAIL does not void H3, H4 or H5 by itself.** Those are within-instrument deltas on
  the same corpus, and contamination that is equal on both arms cancels in the delta. A
  FAIL would matter most to the *absolute* EX number and to the frontier-band siting; the
  draft does not decide, on the owner's behalf, what a FAIL means for them.
- **INCONCLUSIVE is a legitimate outcome and must be reported as one.** If the positive
  control fails to separate, the honest sentence is "this instrument cannot see membership
  on this model", not "no contamination found". A PASS is only ever issued behind a
  control that worked.

**Pre-specified analysis for any future BIRD run, added by this amendment:**

1. **The contamination check is re-run against the checkpoint actually measured.** The
   result belongs to a model version; a run on a different checkpoint cites the check for
   *that* checkpoint, not this one.
2. **The fresh control is regenerated when it is re-run, and is dated.** The current file
   is `bench/contamination_fresh.json`, authored 2026-10-18, n = 58, every gold executed.
   A control reused years later is still a non-member — that is its virtue — but its
   *style* match to BIRD decays with the author's memory of the corpus, and regeneration
   keeps that visible.
3. **The verdict is quoted with its sample sizes and its control numbers in the same
   sentence.** "PASS (n = 300 BIRD, 58 fresh, control AUC x)" is a result; "PASS" alone is
   a slogan.

**What would falsify the claim this amendment rests on:**

- **The positive control failing to separate** means the instrument is blind and any
  reading — PASS or FAIL — is INCONCLUSIVE. That happened in the pilot's first full run
  for a different reason (an off-by-one in the chunked statistic that raised mid-run), and
  the lesson is recorded: an instrument defect that crashes is cheaper than one that
  returns a plausible number.
- **A BIRD AUC above the floor with a control that works** would mean the corpus is
  contaminated for this model, and the check would have earned its keep.

## What this still does not fix

The check is local, single-device and single-checkpoint; it uses two membership methods
where the literature has more (concentration/perturbation scores, loss-based calibration);
and it cannot rule out paraphrase-level exposure. The project's stated better instrument —
a private, contamination-controlled suite — remains the only fix that removes the problem
rather than measuring it, and `docs/licence-requests.md`'s Harness-Bench request remains
open at zero comments.

---

**Owner signature:** ______________________  **Date:** ____________

*Unsigned. No measurement requiring this amendment has been run: the contamination check
itself is a $0 local measurement and needed no amendment to be taken, and no BIRD score
has been produced.*
