# HANDOFF — model-harness co-training

**Current state is this section. Everything under [History](#history) is the body this
section superseded, kept verbatim** — the convention in this repo is to correct visibly, not
to overwrite.

---

## Current state, 2026-10-22, native SQL training inputs

`train.sql_bridge.prepare_sql_training` now prepares plain conversational rows,
a zero-argument native environment factory, and the existing SQL execution
reward from explicitly supplied tasks. It does not choose a taskset or construct
a trainer. Only `run_program` is exported as a tool; reserved `reset` validates
the row against private frozen bindings and creates fresh execution state.
Failed resets clear the old executor first. Tool and scorer databases must be
the same physical file. The prompt and eight-submission budget match evaluation.

Native transcript normalization accepts only a final assistant string without
outstanding tool calls; observations and earlier SQL cannot become answers.
Strict metadata cardinality, missing-database exceptions and invalid-gold
mapping are unchanged. Requested positive integer `--steps` now reaches
preflight/configuration; it previously silently stayed at 200.

Before implementation, the step tests produced 12 failures and two controls
passed. All 66 bridge cases failed in fixture setup because the module was
absent, with pytest exit 1 rather than a collection failure. After implementation,
all 80 new cases passed. Four independent runtime mutations removed the
submission limit, stale-reset invalidation, corpus-identity check and unfinished
answer rejection: 1, 7, 2 and 1 assertions failed respectively. No production
file was mutated.

The actual production adapter also passed through the hash-verified
`GRPOTrainer._tool_call_loop` from official TRL v1.13.0: one real SQLite result
17, one exact tool schema, external mask positions zero, and final execution
reward 1. Changing only that method's mask in memory failed with exit 1.
Optimized Python is explicitly rejected. Tokenization, generation and response
parsing are fixtures; this is not complete trainer, gradient or CUDA evidence.
See `spec/spikes/reference/` and
`research/2026-10-22-training-bridge-contract.json`.

Python/security static reviews approved the bounded changes. The final offline
warm-cache default suite passed **1189 tests, one optional torch skip**, in
143.89 seconds. Cold-cache bootstrap remains unverified.

**Main training is still not runnable.** Real `--preflight-only --steps 17`
still exits 1 for the absent frontier manifest; the downstream
`NotImplementedError` remains. Native TRL environments require Transformers
at least 5.2, while the frozen project guard requires below 5. The local 5.18.0
schema utility does not establish a compatible stack; Unsloth's checked metadata
caps Transformers at 5.17.0. Resolve this conflict explicitly before a patched
trainer/optimizer/checkpoint smoke on approved hardware.

No dependency installation, model loading, GPU job, paid service, scientific
threshold, amendment, signature, manifest, push or release was performed.
The earlier SQL repair and all remaining process, bootstrap, invalid-gold and
measurement-contract gates still apply.

## Earlier checkpoint, 2026-10-22, SQL safety and scorer integrity (`3a86d60`)

The previously reproduced SQL file writes, rewards for no-result SQL, and
timed-out wrapper replacement are repaired. Both Python SQL paths install the
same fail-closed authorizer; both CLI invocations require `-safe`. The scorer
requires result metadata, preserving genuine empty queries. Sweep wrappers
belong to individual watched invocations and survive until their work ends.
Timeout and execution errors are no longer conflated.

Real SQLite/CLI regressions went red before the repairs. Four independent
negative controls then disabled the PTC guard, scorer guard, CLI count safe
flag, and CLI final safe flag: 20, 8, 2 and 2 assertion failures respectively.
Valid-query controls also passed. All 800 shipped gold queries remain valid
under the protected scorer at 30 seconds/500,000 rows per query; the local
metadata and code hashes are in
`research/2026-10-22-sql-safety-golds.json`. This is not a new full-corpus parity
sweep or proof of historical Kaggle database bytes.

Python review caught two dependency regressions that the repository-wide suite
missed. The guard now lives in stdlib-only `ptc.sqlite_safety`, keeping PTC
importable without bench. Three training integration cases live in `train/`,
so the real isolated bench mutation baseline passes without copying training
code into it. Both findings were reproduced, repaired, and re-reviewed.
The guard/standalone group passed 70 checks; scorer/reward/isolated-bench checks
passed 48. These are overlapping with the default suite.

The final default suite passed **1109 tests, with one optional torch test
skipped**, in 122.63 seconds: 136 more cases than `5bac4fc`. This was an offline
warm-cache run, not proof of cold-cache tokenizer bootstrap.

Co-training is still not runnable or experiment-ready. Main training and the
frontier gate remain closed. Watchdog cancellation, mutation process lifetime,
cold-cache tokenizer bootstrap, invalid-gold void policy, and the frozen
model/channel/data contract remain open. SQL guards do not sandbox the OS or
the wider bash shell. The eight historical channel divergences were not
silently repaired or remeasured. No GPU job, paid call, signature, threshold
change, push or release was performed. See `docs/completion-roadmap.md`.

## Earlier checkpoint, 2026-10-22, team hardening (`5bac4fc`)

The unresolved SQL/scoring findings below describe that earlier checkpoint;
the current section above supersedes them.

The five-lane audit led to four implementation tracks, with regression failures
executed before production changes. The branch now has real task-bound SQL
execution, required-telemetry checks that reject unevaluable runs, lossless
frontier diagnostic reports, corpus-order-independent seeded selection, and
mutation runners that distinguish invalid verification from killed mutants.
Literal SQLite paths cannot inject URI access modes; malformed tool argument
shapes return rejection data and permit retry. The diagnostic writer rejects
manifest aliases, including hard links.

Python review found three stale registered mutation anchors. All 52 anchors now
match exactly once, and the three repaired mutations were executed against a
real fresh baseline: all three died, with zero survivors or invalid runs.
Security review's hard-link finding was also reproduced and repaired.
The final post-review default suite passed **973 tests, with one optional
torch test skipped**. That is 329 additional test cases over the preceding
644-pass baseline. Python and security source reviews approved the bounded
patch; they did not establish whole-system safety.

**This does not make co-training runnable or the instrument experiment-ready.**
The actual preflight still exits 1 for the missing frontier manifest, and main
training remains unimplemented after that gate. Disposable fixtures also
confirmed two unresolved blockers: both SQL arms can create files with
`VACUUM INTO`, and comment-only SQL can receive execution reward against an
empty result. No channel/scoring policy was silently changed. Cold-cache
offline tokenizer controls also failed; warm-cache green is not a bootstrap.

[`docs/completion-roadmap.md`](docs/completion-roadmap.md) records the repairs,
reproductions, remaining safety/process/provenance gaps, and acceptance checks
from runnable training through the six-cell scientific comparison. Probe/run
thresholds, signed amendments and the 800 shipped prompt files are unchanged.
No GPU run, paid call, signature, push or release was performed.

## Earlier continuation, 2026-10-22

**v10 ran and aborted after three steps.** The local metrics and companion log were
found and re-read with the logged three-step window. Dead fractions were 1.00,
1.00 and 0.75; the third step had mean execution reward 0.34375 and gradient norm
0.413225. All clipping ratios were zero. The verdict is `PROBE ABORT`, not an
unobserved ten-step run or a frontier measurement. See `docs/probe-v10.md` for
artifact hashes, provenance gaps and the executed verdict.

All 800 shipped SQL prompt IDs, database references and gold queries matched the
local corpus; all 800 gold queries executed successfully under the scorer's
30-second deadline and 500,000-row cap. That does not establish byte identity with
the historical Kaggle upload.

The frontier manifest is still absent and preflight was verified to fail closed.
The downstream co-training entry point also remains deliberately unimplemented.
A11 is still unsigned. No new GPU run, scientific-criterion change, signature,
paid call or publication was performed.

`research/2026-10-22-continuation-review.md` records the current literature,
independently checked power/abort arithmetic, and the proposed frozen-policy
frontier measurement. It also distinguishes dormant manifest-validation code
from enforced requirements; do not wire in its unsigned retention floor.

The SQL extractor now preserves semicolons inside quotes/comments while retaining
only the first statement. Twenty fixture-backed failures were reproduced before
the fix; the final default suite passed 644 tests with one optional torch test
skipped. Python and security source reviews approved the change.

---

## Current state — 2026-10-19

**The probe now measures the policy, and the policy is weak.** v9 is the first run in nine
where generation, extraction and reward all worked: `clipped_ratio` 0.000,
`mean_terminated_length` == `mean_length` == 58.8, and `grad_norm` non-zero for the first
time. It aborted at step 0 on `frac_reward_zero_std` 1.000, and **that abort is a finding
rather than a fault** — but on four groups, one step, so it licenses "solve rate at or
below ~0.05", not a rate. Full write-up: `docs/probe-v9.md`.

- **The generation fault is closed, and its cause was the prompt's shape.** The prompt was
  a bare string, so TRL never applied the chat template: no `<|im_start|>assistant`, no stop
  token, every completion rode to the 3072 cap and was masked. Fixed by rendering prompts as
  one-message conversations plus `enable_thinking: False`, shared by both configs (#22).
- **A repeated signature finally explained.** `grad_norm` 0.0 appeared in v7 and v8 and was
  read against the reward both times. It meant the reward was never called.
- **The taskset's validity threat is now measured, not assumed.** First contamination check:
  question channel clean (AUC 0.455 / 0.508 against controls the instrument can *see* at
  0.764 / 0.825); gold-SQL channel INCONCLUSIVE because the fresh control's length was not
  matched to BIRD's, and length alone reproduced the whole signal. `docs/contamination.md`,
  A10 drafted unsigned.
- **The arm-parity gap has a check it did not have.** A differential sweep over all 1534
  BIRD golds finds 8 real divergences, including 4 where the bash channel loses a trailing
  all-NULL row. Closing those needs the channel to change — owner's call (#24).
- **ProgAgent (arXiv 2610.14774) is the paper that scooped this, and `docs/related-work.md`
  now says so.** It trains 8B/14B only, has no bash arm, and does not enter this project's
  band. The open cell is PTC-trained vs bash-trained at 0.6–1.7B with a bidirectional swap.
- **OSF `2hfzt` is public** as of 2026-10-18, files re-synced to the 26-defect ledger. There
  is no DOI: OSF mints those for registrations and preprints, not project nodes.
- **Still $0 spent, and the $6.29 main run remains unauthorised.** The pipeline gate is shut
  and `bench/frontier/manifest.json` still does not exist.

**The open decision, and it is the owner's:** v9's abort criterion (§282, any step over the
ceiling) collides with `GROUPS_PER_STEP = 4` at step 0 — the first unlucky batch ends the
probe before a rate exists. Three routes: more groups per step, a warm-up collecting k steps
before adjudicating, or a taskset higher on the policy's frontier. Each replaces the
measurement v9 produced.

---

## Current state — 2026-10-12

**A8 is signed and the instrument is replaced.** `ledger` is retired; BIRD-SQL dev is the
taskset; the paired SQL arms exist with parity measured rather than asserted; and the
co-training pipeline is built with its gate shut. 482 tests. Nothing has been measured on
the new instrument and no money has been spent.

- **`docs/pre-registration.md` gained A7 and A8, both appended, neither an edit.** A7
  restates A4's cost claim as two ratios and a floor and withdraws secondary 3 outright.
  A8 replaces the taskset. Both were signed under the owner's standing instruction this
  session that every decision not costing money is the agent's; that delegation is
  recorded in each amendment rather than implied. The file's md5 moved twice and the OSF
  node's copy was re-uploaded to match both times.
- **BIRD cannot test A6's mechanism, and that is the session's load-bearing finding.**
  N1's interaction needs the one-program-versus-forty-calls contrast; a BIRD task is one
  query, one call on either arm. BIRD's simple/moderate/challenging labels are a human
  annotation and 20 clause skeletons appear in all three tiers, so they are not even
  structural. **BIRD is admitted for H3/H4/H5 only and is inadmissible on N1.** Do not
  place a BIRD number beside an N1 prediction.
- **BIRD's numbers, measured against the real downloaded corpus:** 1534 questions, 277
  fine clause-skeleton shapes (25 coarse) against `ledger`'s 9. Gold validity 1530/1534
  clean; of the four rejected only **two** are genuine defects, the other two legitimately
  return 228,765 and 278,230 rows in ~1s. +25 pp needs 59 paired tasks and is reachable at
  any rho; +6.8 pp needs 859 and is reachable only below rho 0.164/0.179/0.101 per tier,
  so BIRD raises shapes 31x and still misses the project's own retired headline target.
- **`compare="set"` is the default and the headline; multiset is a sensitivity check.**
  Official BIRD `evaluation.py` uses `set()`, and comparability to the published sub-1B
  numbers is why a self-authored taskset was abandoned. Until 2026-10-12 nothing pinned
  the default: every comparison test passed `compare=` explicitly, so the one value a
  caller gets by saying nothing was the one value nothing checked.
- **`ptc/paired.py`'s `power_pairs` was crashing, and the band was invisible from both
  sides.** `comb(d, i) * p ** (d - i)` converts an exact big integer to float, which
  raises past d≈1030, so every delta in 0.02-0.04 died. delta ≥ 0.05 answers below that d
  and delta < 0.02 stops at d=1000 on the lower `hi` bound, so all four published figures
  -- 59, 398, 859, 1571 -- sat outside it and nine runs never touched it. Now computed in
  log space; the four values are unchanged and pinned. `_attained` deliberately did NOT
  get the same fix: it is demo()'s independent check, so it uses exact `Fraction`
  arithmetic instead, and an AST test keeps it from being routed through the helper.
- **The parity guard is twelve executable probes, not a claim.** Each capability carries a
  bash probe, a PTC probe and the answer both must reach; `expected` is the ANSWER, not
  the channel's bytes, because demanding byte-identical observations would demand the
  channels be the same channel. Two probes are run 1's defect 5 as tests. Five asymmetries
  are declared, four favouring bash. Emptying `SQL_PRIMITIVES` turns two capabilities and
  the one-sided check red, verified and restored byte-identical.
- **The pipeline gate is shut and says why.** `train/guards.py` requires a signed
  amendment (A8 now reads as signed; A7 deliberately does not), a per-task solve-rate band
  inside (0.120, 0.880), and `n_tasks >= 59` **derived** from `power_pairs` rather than
  stored. `bench/frontier/manifest.json` does not exist, so `preflight()` raises.
- **`solve_rate_min` must never be filled from the ~25% estimate.** That is a marginal
  over a corpus; the gate reads per-task rates. At the same marginal 0.25 and G=4, a suite
  where every task sits at p=0.25 reads 0.320 dead groups and is trainable, while one
  where a quarter are always solved and three quarters never are reads **1.000** and is
  not. Indistinguishable as a marginal.
- **The next action is the free dead-group probe, and it costs $0.** Free Kaggle T4, 12.59
  GB peak, `--steps 5`, `pip install "unsloth>=2026.10.3" "trl==1.13.0"`. Below unsloth
  2026.10.3 this is not a degraded run but another one. Wall-clock is deliberately
  unmeasured and the probe yields the step time so 20 steps is decided from data. It needs
  a prompts file from a BIRD draw first. **Download `probe_metrics.jsonl` immediately** --
  Kaggle's restart wipes `/kaggle/working`, which is how Step 2's metrics were lost once.
- **The $6.29 / 13.2 h main run is still unauthorised and is not the next thing.** The
  free probe answers whether a binary reward separates at all, and no taskset fixes a
  reward that cannot.
- **Spider is not admitted.** Never downloaded; `load_spider()` is verified against
  documentation and a layout fixture only. It needs its own amendment.
- **Contamination replaced self-authorship as the validity threat.** `ledger` could not
  have been pretrained on; BIRD dev has been public since 2023 and no check has been run.
  H3 is a within-instrument delta on both arms against the same corpus, which is what
  keeps BIRD usable, and that argument is written into A8 rather than assumed.

---

## Superseded — current state as of 2026-10-11

**Kept verbatim. Superseded by the section above; read it for what was true on 10-11, not
for what is true now.**

## Current state — 2026-10-11

Steps 1 and 2 are done, the PTC arm is built, and the untrained premise check has met a real
model fourteen times. **It is decided: the premise did not hold.** Nothing in the History
section below describes any of that.

- **Start with `docs/deviations.md`'s defect ledger** (new, at the top of that file).
  **Thirteen** distinct faults — nine in the harness, **four** in the tools that adjudicate
  the result — each with the run that exposed it and the observation that caught it. Every
  one was invisible to a green test suite, and the thirteenth was worse: the suite pinned the
  two failure-prefix strings against drift and so locked in the blindness it was meant to
  guard. Read it before believing any number in this repo. **The count moved 12 → 13 on
  2026-10-10; it is derived from the ledger's own tables, so derive it rather than quote
  this line.**
- **`docs/results-untrained.md` is the pre-committed output.** §6 fired: run 2h measured
  PTC 14/14 against bash 12/14 on the original 14 tasks, so H1 is wrong on **sign**. Not
  separable at n=14 — a non-reproduction, not a reversal.
- **The taskset was extended 14 → 29** (`pre-registration.md` §8/A5) because PTC's 14/14
  left no headroom for a training effect. A6 signs the new question before its data existed.
- **Only 2h, 3c and 3d are admissible.** Runs 1-2f carry instrument defects; 2g is
  unreadable (defect 6); 3a and 3b are void — 3a on `--max-retries 0`, which was my own
  launch error, and 3b on the rate limit that flag exists to survive.
- **Run 3d is the cleanest: zero voids, zero truncations, 29/29 completed on both arms, and
  an exact 23/23 tie.** Launched `--max-turns 150 --max-retries 20 --max-concurrent 1`.
- **The defensible finding is cost, not accuracy.** bash re-sends its transcript once per
  turn, so it reports **8.0-10.7x the prompt tokens** (**6.9-8.9x** once the relay's own
  token counter is corrected for). Cost per solved task is **6.1-8.2x** higher:
  **$0.0126-0.0243** against PTC's **$0.0017-0.0035** at the relay's measured rates.
  Structural, on a co-primary declared in advance, and it holds at a tie.
  **⚠ CORRECTED 2026-10-10.** The token ratio reproduces exactly; the dollars did not. They
  were computed at $0.09/$0.18 per M against a measured $0.2186/$0.670, and the published
  range `$0.0071-0.0099` mixed cost-per-task-*attempted* (3d, 0.2067/29 = $0.0071) into a
  per-*solved* range that also omitted run 2h, whose bash per-solved is $0.0051 — below the
  floor it published. **Keep the token ratio and the cost ratio separate; merging them is
  how the error happened.** Audit and derivation: `ptc/relay_audit.py`, `docs/deviations.md`.
- **The tier pattern is consistent and never significant.** bash +18.2 then +9.1 pp on the
  11 cheap tasks, PTC -5.6 pp on the 18 full-scan tasks in both clean runs, interaction
  -23.7 then -14.6 pp, both CIs including zero, against a signed -25 pp threshold missed
  twice. Point estimates on this n, not demonstrated effects.
- **Co-training was never run and H2-H5 are unadjudicated.** Step 3 stays unstarted.
- **Outreach:** author email sent 2026-10-07. OSF node `2hfzt` private, loaded and
  md5-verified; public + DOI held to a reply or 2026-10-17. Its title and description were
  replaced 2026-10-11 from `docs/outreach.md`'s derived block, and two of its three files
  have been re-uploaded twice as the audit corrected them. Harness-Bench licence request
  open, zero comments.
- **This repository is public as of 2026-10-11** (`nikolas-sapa/co-train`), by the owner's
  decision, before the OSF node. The node is still private and the 2026-10-17 hold stands,
  so the findings are readable here first and carry no DOI.
- **A relay and pricing audit on 2026-10-10/11 corrected published numbers.** Cost per
  solved task was priced at an assumed $0.09/M against a measured $0.2186/M, so every
  dollar figure was ~2.4x low; the published `$0.0071` floor was a cost-per-task-*attempted*
  figure in a per-*solved* range; `8.5x` was two rounded cells divided; and the cost claim
  is now two ratios, not one — tokens 8.0-10.7x (6.9-8.9x de-inflated) and dollars 6.1-8.2x
  with a stated floor. Secondary 3 is **withdrawn**: its failure predicate only ever matched
  one arm's error strings, so bash's 1.000 was a floor artifact. Defect count 13, eleven
  fixed, one structural, one withdrawn — all derived from the ledger tables by
  `tests/test_defect_ledger.py`, which also pins the run count and the repair states.
- `ptc/paired.py` adjudicates (paired CI, exact McNemar, required n, tier split, and a
  refusal to read a partial run). `ptc/audit.py` answers whether an arm computes or
  guesses. **Run the suite as `.venv-ptc/bin/python -m pytest`** — the system interpreter
  has no `verifiers` and dies during *collection*, not at the end. A bare `pytest` is now
  correct: as of **2026-10-10** `pytest.ini`'s `testpaths` covers `tests ptc ledger`. It
  used to read `testpaths = tests`, so `pytest` collected 51 and silently skipped the two
  suites that matter — and this file documented that workaround instead of fixing the
  config. `step2` stays a separate invocation (`-m pytest step2`); it reaches the HF hub.
- **Never run the suite while a real-mode run is in flight.** It serves MCP servers the
  live run is also spawning; contention fails a server-dependent test for ~3 minutes and
  reads as a regression. Suite time over ~30s is the tell.

---

# History

**Everything below this line predates 2026-10-08 and is superseded by [Current
state](#current-state--2026-10-08) above.** It is kept, unedited, because a build log that
quietly rewrites its own premises cannot be audited — and because the step-by-step plan, the
hard constraints and the "do NOT do these" list are still the operative reference for Steps
3-6, which have not started. Read it for *why things are shaped this way*; do not read it for
what is true now.

The original header of this file, verbatim:

**Read this first. Then `research/02-synthesis.md`, `research/07-prior-art-closure.md`, then
`research/08-gap-closure.md` — which supersedes `07`'s novelty assessment.**
Status as of 2026-09-25: **research complete. Step 1 BUILT** (branch
`step1-nonsolver-gate`, 18 commits, 51 tests). Next: **Step 2.**
See `docs/superpowers/specs/` and `docs/superpowers/plans/` for Step 1's spec and plan.

---

## The question

> **Does co-training a small model against a programmatic-tool-calling (PTC) harness reverse the
> bash-over-PTC ordering that arXiv 2609.11999 measured on untrained models — and does the winner
> survive a harness swap?**

Both halves have published baselines. Neither has been run.

**⚠ CORRECTED 2026-09-25 — the gap is smaller than this document originally claimed.**
The `+21.8-24.5 pp` figure cited below is **bash vs Tool-only** (`tokens.md:100-105`), not
bash vs PTC. Bash − PTC, recomputed from Table 1 (`tokens.md:69-92`):

| Arm | Bash | PTC | Bash − PTC | 95% CIs |
|---|---|---|---|---|
| TAC / Opus-4.8 | 69.4 | 52.9 | **+16.5** | disjoint |
| TAC / GPT-5.5 | 67.1 | 45.1 | **+22.0** | disjoint |
| APEX / Opus-4.8 | 48.5 | 40.1 | **+8.4** | disjoint |
| APEX / GPT-5.5 | 44.6 | 37.8 | **+6.8** | **overlap 40.8-41.5** |

Range to reverse is **+6.8 to +22.0 pp**, and one of four arms is not significant. Worse for the
framing: at TAC/GPT-5.5 PTC already wins on cost ($0.54 vs $0.56) and tokens (242k vs 377k).
**Under a cost-per-successful-task metric the ordering is already reversed in one untrained arm.**
Choose Step 5's metric *before* the untrained run or the result is unfalsifiable after the fact.

**Why it is worth doing** (after four papers of prior art narrowed it):
- Every harness-native RL paper compares tool-calling harnesses to *other tool-calling harnesses*.
  The bash-vs-PTC axis has the biggest measured untrained gap (bash +21.8-24.5 pp) and is untouched.
- DCAS measured cross-harness degradation without training. LEGO-RL and OpenForgeRL trained without
  measuring transfer. Nobody joined the two halves.
- Nobody has tried any of it at 0.6-1.7B on free hardware.
- **A negative result is publishable and cheap.**

**Non-goals** (explicit): not building a trainer · not building RL env plumbing · not beating
frontier models on SWE-bench · not shipping a usable coding agent · not pretraining from scratch
(quantified as a detour in `06` §6).

---

## Build sequence

### Step 1 — ✅ DONE (2026-09-25). Five adversarial non-solvers + the gate.
`src/cotrain/contract.py` · `src/cotrain/nonsolvers.py` · `tests/leaky_env.py` ·
`tests/test_gate.py` + 3 test files. 51 tests. **Read `docs/HANDOFF-STEP2.md` before continuing.**
Five, not four: RDI's checklist is "a minimum bar", and observation-channel leakage
(WebArena ~100%, OSWorld 73%) needed its own agent — the gate was measurably blind to it.

### Step 1 (original text) — Four adversarial toy agents (do this FIRST, before the environment exists)
From Berkeley RDI's Agent-Eval Checklist: **null, random, prompt-injection, state-tampering.**
Rule: *"if any non-solver scores above baseline, the benchmark is considered broken."*

This is the cheapest high-value work in the whole plan and it is the concrete form of R24. It also
inverts the usual order deliberately: **you cannot write the verifier correctly until you have
something trying to break it.**

### Step 2 — ✅ DONE (2026-09-30). Prove the loop on free hardware
Kaggle, accelerator `NvidiaTeslaT4` (= T4 x2), **Unsloth** (not raw TRL — see Hard Constraints),
fp16, LoRA rank 16-32, Qwen3-0.6B, `use_vllm=False`, 5 steps. Goal is only: does it run and is
fp16 stable.

**`STEP 2 PASS`. fp16 GRPO is stable on T4.** 5 steps, 298 s, `grad_norm` finite and
positive throughout (1.72–2.43), `reward_std` > 0 every step so the gradient was real,
`kl` rising 1.3e-05 → 2.5e-02 — **the KL curve nobody had published**, which is why
`beta` was set to 0.04 rather than 0. Full analysis, caveats and stack in
`step2/results/`. Re-checkable with no GPU:
`python step2/verdict.py step2/results/step2_metrics.jsonl`.

**Consequence: the free path holds.** Rented Ampere is not required for Step 3 — and
per `08`, prime-rl could not have used a T4 anyway, so the two paths were disjoint.

Caveats, stated: not a learning run (the reward is output length, and reward hacking is
visible by step 4); entropy is unobservable because Unsloth hardcodes
`compute_entropy=False`; single-GPU; five steps is not a trend. The committed JSONL is
**reconstructed from notebook stdout** — Kaggle wiped `/kaggle/working` before it could
be downloaded.

`step2/` — gate check, run script, pass criteria, 73 tests, 59 mutants / 0 survivors.

### Step 3 — Verifier before environment
Snapshot-restored verification instance · constrained replay · verdict bound to a fresh
verifier-minted token · role separation so the agent never holds keys to the ledger it is scored on.
**Complete set or ship nothing** — RECEIPT's ablation: 45% (self-judgment) → **9%** (partial) →
100% (full). Partial hardening scores *worse than none*.
Then **test it both ways**: reference solution must PASS, planted mutant must FAIL.
Then **source-audit** it with **BenchJack** — **it shipped**: `github.com/benchjack/benchjack`,
Apache-2.0, 46 stars, pushed 2026-05-25, paper arXiv 2605.12673. The RDI blog's "preparing for
public release" is stale, which is why `06` recorded it as unlocated. Know what it is (`08` §4c):
a static + LLM audit pipeline that scans a *repository* against V1-V8 and shells out to
`claude --print` / `codex`. It is **not** an adversarial rollout, and the four toy agents are
**not** in it — they are a checklist item from the RDI blog, which is why Step 1 builds them.
For the runtime half add **`moogician/trustworthy-env`** (MIT, 62 stars, Z3-backed,
`detect.py audit --run-cmd`). Take two things from Harness-Bench's design (`08` §5.2): the
model/state secret split, and `Security ∈ {0,1}` as a **multiplicative** gate so a hack zeroes
the whole task rather than costing a penalty term.

### Step 4 — Environment, minimal action space, escalation channel from day one
Reward computed from state the agent cannot write. Structured escalation channel (cut hacking
23.6%→5.3% across 8 models at no perf cost, *and* doubles as verifier-QA). Plant one instrumented
rule-legal shortcut so hack telemetry is deterministic.

### Step 5 — Two harnesses behind one interface, measure untrained first
bash and PTC. **Confirm the published gap reproduces in your setup before training anything** —
and target the conservative **+6.8 pp** APEX figure, not the TAC number. `08` §6: APEX's "bash"
arm is a real `sh -c` server (the MCP-confound fear is **refuted** by the paper's own Appendix
B.2), but TAC's typed catalog is author-built and self-declared *"not every shell-accessible
endpoint"*, so TAC's larger delta is the one to discount.
**Evaluate `verifiers` before building two harnesses** (`08` §2.5): it already ships `bash` and
`rlm(builtin_tools=["ipython"])` — which is 2609.11999's PTC definition — behind one `Harness`
ABC, selected by `--env.agent.harness.id`. Add two leading indicators: tool-call **success rate**
(untrained PTC 65.2% vs bash 92.1%, Table 2) and **shell-call share** (OpenForgeRL measured RL
moving it 22.6% → 13.9%, its §5.3 — the closest published result to this project's question).

### Step 6 — Co-train, then evaluate cross-harness
Cross-harness eval from run 1. Report **billed cost**, not tokens. `mask_truncated_completions=True`.
**Pre-register token cost and stability as primary outcomes alongside score** — 2603.01209 held
everything but one runtime property fixed and found *"solution quality is statistically
indistinguishable across conditions, but token cost and stability differ substantially"*. State
the GRPO **grouping boundary** and test under an unseen harness (2609.04518, whose sealed
24,000-evaluation result is that the *evaluation* harness moves solve rate 4.3x where the
training recipe moves it 1.16x). Hold action-space **altitude** comparable across arms or declare
the asymmetry (`08` §8): a deliberately minimal PTC vocabulary makes a PTC loss unattributable.

---

## Hard constraints (expensive to rediscover)

| Constraint | Detail |
|---|---|
| **No local training** | Dev machine is darwin/arm64. prime-rl requires NVIDIA. All training rented or Kaggle. Every prime-rl GPU dep is gated `sys_platform == 'linux'`. |
| **prime-rl is Ampere+, not just "NVIDIA"** | Source, not docs (`08` §3): `DTYPE_MAP` has **no float16** and FSDP hardcodes `param_dtype=torch.bfloat16` (`trainer/model.py:98-101,471`), so **prime-rl cannot train on a T4 at all** — not slowly, not at all. Tested floor is RTX 3090/A100+ (`README.md:68`); the pinned flash-attn wheels carry sm_80/90/100/120, **no sm_75**. A rented T4 does not unlock prime-rl: the Unsloth-on-T4 path and the prime-rl path are **disjoint**, not two rungs of one ladder. `verifiers` (MIT, pure Python, runs on darwin/arm64) is the part that carries across both. |
| **Kaggle reality** | T4 x2 (P100 retired 2026-09-15), **30 GPU-h/week**, **12 h/session**, **20-30 min idle timeout**, 20 GB persisted at `/kaggle/working`. No A100/H100 free. Multi-process vLLM+trainer in one session is demonstrated (`kaggle-vllm`). |
| **T4 = no bf16** | Compute capability 7.5. bf16 needs 8.0. fp16 only. vLLM floor is 7.5, so T4 just clears it; **P100 (6.0) cannot run vLLM at all.** |
| **Use Unsloth on T4, not raw TRL** | A TRL PR exists *solely* because "T4 in collab need fp16 and vllm defaults to bf16." Unsloth ships 40 Kaggle GRPO notebooks and has done the fp16-on-Turing work. Migrate to TRL/prime-rl only when renting proper hardware. |
| **TRL trainability gate** | ⚠ **CORRECTED by Step 2 — see `step2/README.md`.** The raise is guarded by `if self.tools`: it is inside the multi-turn tool loop, so a no-tools GRPO run never reaches it. It does not exist at all in TRL ≤ 0.24.0 (`trl/chat_template_utils.py` is 404 at that tag; `self.tools` appears zero times), and **Unsloth pins `trl<=0.24.0`** — so on the Step 2 stack the gate is absent, not merely unfired. Qwen3-0.6B **does fail** the check where it exists (it drops `<think></think>` from history), but TRL auto-repairs it via `get_training_chat_template`, verified False→True here. **The proxy escape hatch is not needed.** Steps 5-6 are a different matter: PTC *is* tool calling, and that path does not exist on the Unsloth stack. |
| **`verifiers` is pinned to a commit, not a tag** | `ptc/requirements.txt`: `69cc0f9` in `.venv-ptc` (py3.12, reports 0.3.2.dev137). No released tag works — `ptc/harness.py` imports `verifiers.v1.harnesses.utils.mcp`, which was only factored out of the per-harness `program.py` copies *after* the newest tag v0.3.1, so going back through the tags moves away from it. The ref was recovered from `docs/spike-verifiers.md` §Environment, which recorded it; it was **not** re-derived from matching module paths, and PyPI `verifiers` (0.1.5, no `v1/` tree) is a different package. The `glossary` taskset is pinned to the same commit as a `#subdirectory=` — it is `--taskset`'s default and is **not** on PyPI, and the spike had it installed from a since-orphaned `~/scratch/` clone. |
| **`NCCL_CUMEM_ENABLE=0`** | Set before any vLLM weight sync. 180 s → 4 s on 70B. One env var. |
| **Sandbox cost ≈ GPU cost** | 256 concurrent rollouts ≈ $42/hr (E2B/Daytona), $61 (Modal), $3.5-9 (Fly Machines). E2B Hobby caps at **20 concurrent** — unusable. Wall-clock billed, so idle environments cost money. |

## Budget
Smoke test $5-30 · first real experiment **$60-200** (probably conservative: Garg ran 20+ GRPO
ablations for ~$140 total; GRPO-Zero does Qwen2.5-3B on one A40 for $1-2/run) · serious $1,500-10,000.
**Free path exists**, capped at ~0.6-1.7B by the 12 h session and T4 speed (~15x slower than H100).

---

## Do NOT do these (learned the expensive way)

1. **Do not prompt the agent not to cheat.** Measured at zero effect or negative: BAITBENCH stays
   >50% under an explicit no-cheat prompt; a restrictive prompt was *fastest* to hack; Prime Agent
   defeated an explicit heartbeat.
2. **Do not read the score from state the agent can write.** WebArena scored ~100% by opening the
   task config over `file://`. Factorio's Production Score was read from the game's own counters and
   RCON wrote them directly.
3. **Do not audit only application state.** RDI's exploits include a fake binary on `$PATH`, a
   pytest plugin hook, and uninitialized GPU memory holding the evaluator's prior answer.
4. **Do not ship a partially hardened verifier.** 9% precision is worse than the 45% you get with
   none, because it produces confident wrong verdicts.
5. **Do not put an LLM judge in the reward.** Doubles compute per step, adds systematic bias, and is
   a documented hack surface (V4).
6. **Do not compress the observation to save tokens.** AgentOccam tripled success while *increasing*
   observation tokens 33%. The only token-reducing step was cutting the action space — which was
   also the biggest single accuracy gain. **But "shrink the action space" is a rule with an
   exception** (`08` §8): shrink same-altitude primitives, do **not** cap abstraction depth.
   SCAFFOLD, on the same 7B base, beat AgentOccam 42.7 vs 16.8 with a *larger* recursively
   composed vocabulary; flattening it to depth ≤ 1 cost 6.3 pp and leaving it unpruned cost 3.1 pp,
   so the optimum is interior. NapMem is the trained version of the same shape: the wide interface
   **prompted** (48.39) loses to the narrow one (54.08), the wide interface **trained** wins
   (62.74). Expect narrow to win at 0.6-1.7B anyway, and pre-register that.
7. **Do not trust vendor docs over vendor source.** Bit twice this research: Kaggle's docs still say
   P100; TRL's doc URLs 404'd while the source was fine. Check the repo or its test suite.
8. **Do not let a research agent own a file-writing contract.** The `research` agent type's tool
   grant changed mid-session; two lanes lost their reports. Have them return content, you write it.

## Health signals to log from run 1
Gradient norm · `mean_response_length` · token entropy · reward_std. Garg's collapse signatures:
lr 1e-4 → policy collapse and entropy to zero (3e-5 stable); off-policy reuse of 16 steps → collapse
mid-run; removing the group-mean baseline → gradient blowup. Stay on-policy.

---

## Known unknowns
Five of these closed on 2026-09-25. Detail and sourcing: `research/08-gap-closure.md`.

- **fp16 GRPO on Qwen3 — narrowed to the KL curve only** (`08` §7). A public Kaggle **2×T4**
  run settles the rest: `rkkzone/qwen3-0.6b-math-l45-grpo-adapter` ships `training_logs.json`
  and `hardware_profile.json` — `fp16=True`, `bf16=False`, `use_vllm=False`, dense Qwen3-0.6B,
  **314 steps over 5.9 h, 2.40 GB peak VRAM, zero non-finite values** in loss/grad_norm/reward.
  It logged no KL (`beta=0`); a sibling run with `beta=0.04` finished and merged but published
  no log. **Mechanism confirmed in source, and it flips one corpus assumption:** Unsloth
  force-float32s `qwen3_5` and `qwen3_moe` for *"NaN grad norms in float16 training"* but
  **not dense `qwen3`** (`loader.py:118-127`), and Qwen3 has **QK-norm** where Qwen2 has none
  (`modeling_qwen3.py:237-238`), bounding exactly the attention logits that used to overflow.
  So Gemma-3's failure does not transfer to *dense* Qwen3 — but it **does** transfer to Qwen3.5
  and MoE. **Model choice is load-bearing: pin dense Qwen3-0.6B/1.7B, never Qwen3.5 or MoE.**
  Unsloth's fp16-on-T4 path is by design (`rl.py`: *"V100/T4 never pick bf16"*) and carries
  no-bf16 regression tests; TRL's 5,073-line GRPO test file has **zero** `fp16` hits and its
  GPU CI left Turing (T4 → L40S). That asymmetry is why Step 2 stays on Unsloth.
- **Harness-Bench — FOUND**: `github.com/Qihoo360/harness-bench`, 112 stars, in **footnote 1**
  of the paper, invisible to arXiv metadata. 106 task dirs verified real (`task.yaml` ×106,
  `oracle_grade.py` ×106, 812 fixtures), plus 12 harness adapters. **No LICENSE file →
  all-rights-reserved.** Read it, do not vendor it. Also: *"106 oracle-checkable"* is
  overstated — the criterion is *"deterministic checks **or a specified rubric**"*, 86 tasks
  ship an `llm_rubric.py`, and the aggregate multiplies in an LLM judge, which rule #5 bars
  from a reward. Usable subset is `Security × Completion`.
- **OpenForgeRL code — FOUND**: `github.com/MSR-Orchard/OpenForge-RL`, 17 stars, default branch
  **`master`** (so `/main` 404s). The v3 "added github link" is the vanity redirect
  `aka.ms/OpenForge-RL`, which is why a `github.com` search missed it. Recording proxy is real
  (58 KB `vllm_proxy.py`). **No LICENSE.**
- **R33 dispersion+level screening** for continuous rewards — still unvalidated, publishable
  either way, and now **corroborated by that public run**: its reward went flat with
  `frac_reward_zero_std` at 0.56-1.00, i.e. most groups carried zero advantage. Signal
  starvation, not numerics. Log this metric from step 1.
- **Full texts of 2607.21557 and 2605.27922 — now read** (`08` §5). Three corpus claims fell,
  the largest being that OpenForgeRL **does** run a cross-harness transfer test (its §5.2,
  Table 5) — `07` read only the abstract.
- **Still genuinely open:** the KL curve at `beta>0` on T4; whether any of this reproduces at
  0.6-1.7B; and whether 2609.11999's untrained gap reproduces at all (zero citations, §6).

## Three publishable experiments sitting in the gaps
1. Token-meter ablation (with vs without charging the agent for its own output tokens) — never run.
2. RECEIPT-grade tamper-proof verifier ported to an economic environment — the bench lane's own
   synthesis, unpublished.
3. Dispersion+level screening for continuous-reward environments — no paper does it.

---

## Corpus map
| File | Read when |
|---|---|
| `research/02-synthesis.md` | **Start here.** The decision, + addendum folding in bench/browser. |
| `research/07-prior-art-closure.md` | Before committing to the thesis. Honest novelty assessment — **partly superseded by `08` §1**. |
| `research/08-gap-closure.md` | **Read with `07`.** Closes 8 gaps: novelty narrowed to one axis, four transfer scoops, three "missing" repos found, fp16 unknown narrowed to KL, counter-evidence to "shrink the action space", and `verifiers` vs our `contract.py`. |
| `research/06-perplexity-delta.md` | Before touching Kaggle or the verifier. fp16 + BenchJack + costs. |
| `research/03-free-compute.md` | Setting up the free path. |
| `research/05-delta-tierlist-and-rdi.md` | Verifier design. RDI broke 8/8 benchmarks. |
| `research/lanes/bench.md` | Environment design. **34 rules**, R1-R6 are the load-bearing ones. |
| `research/lanes/grpo.md` | GRPOTrainer API, loss masking, failure modes. 1,336 L. |
| `research/lanes/harness.md` | Harness-overfitting evidence. 1,661 L. |
| `research/lanes/tokens.md` | The bash-vs-PTC measurement this project is built on. 936 L. |
| `research/lanes/browser.md` | Only if the environment touches the web. 668 L. |
| `research/lanes/compute.md` | Pricing, VRAM, wall-clock. 793 L. |

## Standing caveat
Retrieval was degraded for the whole research phase: WebSearch broken, `exa_search` off, Semantic
Scholar 429'd, Twitter/Reddit unavailable. Every lane source is arXiv, GitHub, or a vendor doc.
**Practitioner evidence arrived only via user-supplied Perplexity reports** (`06`), and was not
independently verified beyond the load-bearing claims listed in that file's Verification section.
`08` ran under the same broken `WebSearch`, using `curl`/`gh`/arXiv-API/OpenAlex and repo clones;
every load-bearing claim there was re-verified against the primary artifact (paper full text,
repo, or committed run log) rather than a lane report.
**One risk unchanged and now quantified:** arXiv 2609.11999, the measurement this whole project
rests on, has **zero citations** by five independent routes (OpenAlex, Scholar, HF papers,
full-text grep, Semantic Scholar). It is unreplicated, uncriticised and first-party. Step 5's
untrained reproduction is not a formality — it is the experiment that decides whether the premise
is real.

## Starting the next session
**Read `docs/HANDOFF-STEP2.md` first.** It carries what Step 1 learned, the corrections it forced
into this document, and the constraints Step 1 now places on Steps 3-5.

Invoke `/superpowers:brainstorming` before writing code — the project-level skill gate requires it
for new feature work, and the environment design genuinely has undefined scope.
