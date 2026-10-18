# Related work: what has been answered since the pre-registration

Written 2026-10-18. Every claim about a cited paper was read off that paper (HTML or
abstract), not from a secondary summary. Every arXiv ID was re-resolved against the arXiv
export API on 2026-10-18 and the title, first authors and submission date below are what the
API returned. Nothing here changes a co-train result, number or claim; it records which of
them a reader can now find answered elsewhere, and which cannot.

**Why this file exists.** `docs/pre-registration.md` §7 says the single surviving claim is
*harness type as the independent variable*. As of 2026-10-10 that claim has a direct
predecessor with a trained PTC arm and a harness swap, `arXiv 2610.14774` (ProgAgent). The
repo did not mention it. This file says exactly what ProgAgent covers and what it leaves.

---

## 1. Verification

| arXiv ID | Title as returned by the API | First authors | Submitted | Status |
|---|---|---|---|---|
| 2610.14774 | ProgAgent: Learning Tool Orchestration through Programmatic Training | Hao Li, Keqing He, Longtao Zheng, Junlong Li, Weihao Zeng, Qian Liu, Yuzhen Huang | 2026-10-10 | verified, v1 |
| 2609.11999 | Is Bash All You Need? An Empirical Study of Tool Interfaces for Enterprise Digital Worker Agents | Hazel Mak, Susheel Suresh, Sahil Bhatnagar | 2026-09-10 | verified, v1 |
| 2608.06370 | The Bitter Lesson of Tool Calling | Ishan Patel, Sahil Sen, Elias Lumer, Vamse Kumar Subbiah | 2026-08-06 | verified, v1 |
| 2609.09218 | The Double Measurement Confound in Agent Benchmarks: De-Scaffolding, Ground-Truth Scoring, and Reliability Beyond the Mean | Yonghong Zhang, Shadi Motaali, Vu Phong Dinh | 2026-09-06 | verified, v1 |
| 2607.12161 | Token Reduction Is Not Cost Reduction | Sarel Weinberger, Amir Hozez | 2026-07-13 | verified, v5 (updated 2026-08-12) |
| 2603.01209 | Evaluating Agents Across Runtime Contracts: When Mismatch Costs Efficiency or Quality | Victor May, Van Khue Nguyen, Aaditya Salgarkar | 2026-03-01 | verified, **v3** (updated 2026-09-26) |
| 2510.26788 | Defeating the Training-Inference Mismatch via FP16 | Penghui Qi, Zichen Liu, Xiangxin Zhou | 2025-10-30 | verified, v1 |

**No ID failed to verify.** One citation has drifted, and it matters:

`2603.01209` is cited in `research/08-gap-closure.md` and in `docs/pre-registration.md`'s
preamble under the title *"Agents Learn Their Runtime: Interpreter Persistence as
Training-Time Semantics"* and with the quotation *"solution quality is statistically
indistinguishable across conditions, but token cost and stability differ substantially."*
Both are **v1** (the v1 abstract page still carries that sentence verbatim). The current
version is **v3, retitled**, and its abstract no longer asserts global indistinguishability:
its primary task reports a persistent-trained agent deployed statelessly scoring **0.61 of
optimal value against 0.77 under matched deployment**, at 80 calls per turn, and the
refinement is that *"cap tightening produces a mismatch-specific collapse only where
interruptions are frequent and matched execution resumes while mismatched execution
restarts."* The quotation is not fabricated, it is version-bound. The pre-registration's
second motivating bullet is therefore weaker than it reads: on v3's own primary task the
mismatch costs quality, not only cost and stability. **This is recorded here and
`docs/pre-registration.md` is not edited**, per its own append-only convention; whether it
warrants an amendment is the owner's call.

---

## 2. ProgAgent, read properly

`arXiv 2610.14774`, submitted 2026-10-10, cs.AI, CC BY 4.0. HKUST with BUPT and NTU
co-authors. Project page `llleoli.github.io/ProgAgent/`.

### Models and scale

Qwen3 **8B and 14B**, thinking mode. **No model below 8B is trained or evaluated.** This is
the single most important fact for this repo: co-train's band is 0.6-1.7B and ProgAgent's
smallest arm is **4.7x above its ceiling**.

### Training method

- **215 synthesized tasks**, each instantiated at **four environment scales** (`scale_1` to
  `scale_4`, database 99 KB to 711 KB, 12.7 to 40.3 workspace files), holding instruction,
  task logic and tool schemas fixed. 860 task instances.
- Tasks are programmatically verifiable: a Python verifier returns a binary reward over the
  final response and final environment state. *"Verification does not use an LLM judge."*
- Oracle solution must pass, with an automated repair loop; then an independent harness agent
  audits; then difficulty filtering retains tasks whose DeepSeek V4 Pro PTC pass rate lies in
  a band at every scale.
- **Recipe: cold-start SFT (3 epochs, batch 64, 128k context via YaRN, tool calls converted
  JSON to XML) then GSPO RL** (150 steps, 16 rollouts x 32 tasks per step, no KL penalty).
  Teacher trajectories from DeepSeek V4 Pro. Trained with ms-swift and verl/vLLM on H200s.
- **Three harnesses trained from the same task pool and the same hyperparameters**: DTC
  (standard typed schemas, direct calls), PTC (all environment tools through a persistent
  sandboxed IPython kernel, `tools["name"](...)`, print-selected output), and Hybrid (both).

### Harnesses compared, and the one that is absent

The contrast is **DTC vs PTC vs Hybrid**. PTC is defined as co-train defines it: a program
restricted to a typed catalog, no arbitrary execution of the task data.

**There is no bash-trained arm, and a bash arm is not constructible from the paper as
written.** All three harnesses do expose a `terminal` tool, but §C.2 states *"The task
database is accessible only through environment tools"* and the terminal runs *"shell in the
workspace directory"* under the same sandbox. So the shell can touch workspace files and
cannot reach the records the typed tools own. This is the structural inverse of co-train's
setup, where bash reaching the data is exactly what defect 5 was about and what run 2h's bash
arm did. **ProgAgent's DTC is not bash and is not a substitute for it.**

The paper's Related Work (Appendix A) cites CodeAct, Recursive Language Models, Anthropic's
code-execution posts and Patel et al. (the `2608.06370` authors) for PTC. **It does not cite
`2609.11999`, and Appendix A contains no shell-versus-catalog discussion.**

### Headline numbers (binary pass rate, %, four runs averaged)

| | MCPMark avg | LOCA-bench 8k / 64k, avg | Toolathlon | MCP-Atlas |
|---|---|---|---|---|
| ProgAgent-8B | 18.3 | 34.7 / 17.3, **24.3** | 9.3 | 38.6 |
| ProgAgent-14B | 29.7 | 41.3 / **30.7**, **38.3** | 17.1 | 45.6 |
| Qwen3-8B untrained, own harness | 3.0 (DTC) / 2.5 (PTC) | 0.3 (DTC) / 0.0 (PTC) | 2.8 | 7.6 (DTC) / 3.6 (PTC) |
| Qwen3-14B untrained, own harness | 3.2 (DTC) / 4.1 (PTC) | 0.3 (DTC) / 0.0 (PTC) | 1.9 | 12.4 (DTC) / 3.8 (PTC) |
| 8B DTC-trained | 6.0 | **4.0** | 2.8 | 19.0 |
| 14B DTC-trained | 8.0 | **9.0** | 5.6 | 29.7 |

The claim in the abstract, *"PTC-trained models outperform DTC-trained models under both
evaluation interfaces"*, is Table 6 and it holds in all four pairings.

### The swap design, and its one confound

Table 6 cross-evaluates DTC-trained and PTC-trained checkpoints under both harnesses:

| Model | Eval harness | LOCA 8B: base / DTC-trained / PTC-trained | MCP-Atlas 8B: base / DTC / PTC |
|---|---|---|---|
| 8B | DTC | 0.3 / 4.0 / 6.0 | 7.6 / 19.0 / 30.6 |
| 8B | PTC | 0.0 / 10.7 / 24.3 | 3.6 / 11.8 / 38.6 |
| 14B | DTC | 0.3 / 9.0 / 13.9 | 12.4 / 29.7 / 41.6 |
| 14B | PTC | 0.0 / 20.7 / 38.3 | 3.8 / 29.0 / 45.6 |

Two observations this repo should not smooth over:

1. **The gain attenuates on transfer, and by how much is benchmark-dependent, not size-dependent.** Against each model's own untrained base, PTC-training's LOCA gain retained under DTC evaluation is **23% at 8B** (6.0 against 24.3, 4.26x attenuation) and **36% at 14B** (13.9 against 38.3, 2.82x). On MCP-Atlas it keeps **66% at 8B** (30.6 against 38.6, 1.52x) and **70% at 14B** (41.6 against 45.6, 1.43x). H3 predicted 3-4x; the observed range is **1.4x to 4.3x**, so the direction is right and a single multiplier is not. The benchmark moves the attenuation more than the model size does.
2. **On LOCA, the model trained under DTC scores higher under the PTC harness than under its
   own.** The PTC-trained gain is measured against the model itself, not against an untrained
   baseline: 14B PTC-trained scores 38.3 under PTC and 13.9 under DTC, while the DTC-trained
   14B scores 9.0 under DTC and **20.7** under PTC. The PTC harness appears to have the higher
   ceiling on that benchmark, which is why the paper attributes its gains to training rather
   than to interface access. On MCP-Atlas the DTC-trained model moves far less (29.7 to 29.0
   at 14B), so this is not a uniform harness effect.

**Disclosed confound, handled, and the fair row.** For DTC RL *"we only use scale_1
environments, as the other environments are too difficult for the model to obtain any
rewards"*; PTC used all four scales. The paper's `scale_1`-only ablation is the matched
comparison: **PTC 23.7 vs DTC 6.7 at 14B, 16.0 vs 3.3 at 8B.** The PTC advantage survives the
matching, but on the headline rows PTC and DTC were not trained on the same environment
scales.

### Process numbers, and the one that is missing

- Tool-output tokens per episode: DTC flat near 30k, PTC falls roughly 20% to below 20k.
- Tool calls per episode: programmatic arms use roughly half of DTC's (about 45 vs 90 at 8B).
- Runtime errors per episode: 6.4 to 3.6 at 14B, 7.5 to 5.0 at 8B.
- PTC calls that are single-invocation with no control flow: up to **40.7%** at 14B on
  Playwright, 10.1% on Filesystem.
- Disabling MCP server-error detection drops LOCA from 24.3 to 19.3 at 8B and 38.3 to 34.5
  at 14B.

**No billed cost, in dollars or any other currency, appears in the main text or the
appendices this reading covered (§4-§5, C.1-C.4, D.1-D.3, Table 8).** The process metrics are
tool-output tokens and tool-call counts, and `2607.12161` is exactly the finding that those
are not a cost proxy. ProgAgent makes no cost claim and this file makes none on its behalf.

---

## 3. Hypothesis map

co-train's hypotheses, against what ProgAgent and the six other references establish. "Open"
means no located source tests it, not that nothing exists.

| Hypothesis | Status | Evidence, and what it does not reach |
|---|---|---|
| **H1** untrained bash-over-PTC gap reproduces, at ~+7 pp | **Falsified by run 2h; not addressed by ProgAgent** | A4 and `docs/results-untrained.md`: −14.3 pp at n=14, CI touching zero. ProgAgent has no bash arm and no untrained comparison on the bash axis. Its untrained DTC-vs-PTC cells (LOCA 0.3 vs 0.0 at both sizes; MCPMark 8B 3.0 vs 2.5, 14B 3.2 vs 4.1; MCP-Atlas 8B 7.6 vs 3.6, 14B 12.4 vs 3.8) differ by 0.3-8.6 pp on near-floor rates and the paper reports no test of them. |
| **H2** co-training narrows but does not reverse at 0.6-1.7B | **Partially answered; scale wrong** | ProgAgent reverses at **8B and 14B** on all four benchmarks (LOCA 14B 38.3 vs 9.0; MCPMark 14B 29.7 vs 8.0). That is the reversal co-train predicted would not happen, **4.7x to 8.2x above co-train's model ceiling** (8B and 14B against a 1.7B ceiling). Nothing in it says a 0.6-1.7B model reverses. The `scale_1`-matched rows (23.7 vs 6.7 at 14B) do not change this. |
| **H3** cross-harness transfer positive but attenuated ~3-4x | **Partially answered: direction confirmed, multiplier not** | Table 6, gain retained when PTC-training is evaluated under DTC: LOCA **4.26x / 2.82x** attenuation (8B / 14B), MCP-Atlas **1.52x / 1.43x**. Positive and attenuated everywhere, but the constant 3-4x does not hold and the benchmark gap is larger than the model-size gap. DTC-trained models conversely gain *more* under the PTC harness on LOCA (9.0 to 20.7), so the swap is not symmetric. |
| **H4** effect appears in tool-call success rate and cost before score | **Partially answered: success, not cost, not ordering** | Runtime errors fall 6.4 to 3.6 (14B) and tool calls roughly halve while score rises, so process metrics move with training. **No success-rate-versus-score ordering test, no billed cost, no per-task variance analysis.** A9's point stands untouched: the cost axis is unmeasured here, and ProgAgent's token reductions would not settle it. |
| **H5** narrow beats wide at this scale | **Partially answered at 8B/14B; co-train's band untouched** | Hybrid (DTC+PTC, a strict superset action space) loses to PTC on all four benchmarks at both sizes (14B LOCA 31.3 vs 38.3; MCPMark 25.4 vs 29.7; MCP-Atlas 38.6 vs 45.6). That is narrow-beats-wide, at 8B/14B. H5 predicted exactly this at 0.6-1.7B and records that the crossover needs capability this project lacks. ProgAgent extends the evidence upward; it does not enter the band. |
| **N1** the effect is a call-count interaction | **Still open, and A8 already refuses it on BIRD** | ProgAgent scales *environment state*, not call count: instruction, logic and tool schemas are held fixed while the database grows. Its own DTC degradation with scale (pass@8 0.95 to 0.42) is context growth, which is N1's mechanism family but not its measurement. No located source has a call-count tier with a trained bash arm. |

**Summary in one line.** ProgAgent answers *"does PTC-training beat DTC-training, and does the
winner survive a harness swap"* at 8B and 14B, in the affirmative on both counts, and it
answers no co-train hypothesis inside co-train's model band or on co-train's bash axis.

---

## 4. The cell that remains open

Stated precisely so it can be attacked or retired:

> **PTC-trained versus bash-trained, at a small open model (0.6-1.7B), with a cross-harness
> swap in both directions.**

Three things keep it open, each a separate reason:

1. **No bash-trained arm exists in ProgAgent**, and its shell cannot reach the task data. The
   bash axis, which `2609.11999` measured untrained and which A4 measured inverted at n=14,
   is untrained-only everywhere else in the corpus.
2. **No model below 8B is trained** in ProgAgent. H2's prediction is specifically about small
   scale, and a reversal at 14B is compatible with a narrowing at 0.6B.
3. **No cost-per-solved-task measurement** accompanies any trained PTC arm. A7's result, and
   A9's condition on it, have no trained counterpart in either direction.

Against that, the cell is narrower than it was on 2026-09-25. The DTC analogue of the same
experiment is now published with a swap and a clean advantage, so a future co-train run that
reproduced "PTC-training reverses the untrained ordering and transfers" at 8B would be a
replication, not a contribution. What would remain a contribution is the **bash** arm at
small scale and the **cost** axis, together with a taskset where a multi-call contrast
exists, which A8 records BIRD does not have.

---

## 5. The other references, briefly

Each entry says only what changes for this repo.

**`2609.11999`, Is Bash All You Need?** Six authors, Microsoft and CMU, 2026-09-10. Five
interfaces on TheAgentCompany and APEX-Agents with Opus-4.8 and GPT-5.5. Bash alone beats
typed tools by 21.8-24.5 pp on TAC and 4.8-7.4 pp on APEX at 19-72% fewer tokens; PTC uses
fewer tokens than direct typed calls with *"broadly similar task performance, but generally
underperforms bash alone in both quality and cost efficiency."* This is the paper whose
untrained ordering H1 predicted would reproduce at the small end, and A4 falsified the
prediction. One independent deviation from it now exists in this repo: run 2h, at n=14 and
against a self-authored taskset. ProgAgent's untrained floor cells differ from it in direction
on MCPMark at 14B (PTC 4.1 against DTC 3.2) but are too close to the floor to be called a
replication in either direction. Neither is a replication of the enterprise setting, and this
repo's recorded citation check found no citations to the paper (A4;
`research/08-gap-closure.md` §6).

**`2608.06370`, The Bitter Lesson of Tool Calling.** PTC versus native JSON across 14 models
on BFCL v4. *"Programmatic tool calling matches or exceeds native JSON tool calling in 11 of
14 models"*, with a 10.6% improvement for the GPT-5.6 family, and it holds under context rot
where the baseline degrades 2.3%. Read against `2609.11999` this is the useful tension:
PTC beats JSON and loses to bash. ProgAgent's finding that DTC-training loses to PTC-training
is a third position, and the three are consistent only if the untrained ordering depends on
what PTC is compared against, which is the repo's axis.

**`2609.09218`, The Double Measurement Confound.** Names two confounds: execution-critical
decisions made by the scaffold rather than the model, and scorers that do not reflect task
correctness. Finding: *"scorer validity is benchmark-specific, whereas scaffold ownership is
an uncontrolled axis wherever we probed it."* This is the methodological warrant for
co-train's pre-registered grouping boundary and held-out harness, and it is the citation a
reader will look for when asking whether a harness comparison means anything. It does not
provide a harness comparison.

**`2607.12161`, Token Reduction Is Not Cost Reduction.** 38.4% fewer delivered tool-output
tokens, **6.8% higher billed cost**, Pearson r = 0.15 between token reduction and cost
reduction, with prompt-cache creation and reads dominating input-side cost. This is the
standing reason co-train's co-primary is dollars per solved task and not tokens, and it is
the reason ProgAgent's token-column gains cannot be read as cost savings.

**`2603.01209`, runtime contracts.** v3 retitled; the finding is a 2x2 train-runtime
cross-evaluation on three tasks with Qwen3-8B, showing that training traces carry strategies
specific to the runtime they were collected under, and a mismatch cost that is mostly in
tokens and stability but, on the primary task at 80 calls per turn, in quality as well (0.61
vs 0.77). It is the closest design precedent to co-train's swap, one layer down the stack:
interpreter persistence rather than shell versus PTC, and SFT rather than RL. See §1 for the
version drift.

**`2510.26788`, FP16.** The training-inference mismatch in RL fine-tuning has a numerical
root cause that BF16 rounding errors create and FP16 removes. This underpins Step 2's verdict,
that fp16 GRPO is stable on a T4, and it is the reason a T4 run is a valid instrument rather
than a compromise.

---

## 6. What this file does not do

- It does not re-rank co-train's hypotheses. H1 is falsified by A4 and stays falsified; A8's
  narrowing of BIRD to H3/H4/H5 stands; nothing here makes any run admissible that A8 refused.
- It does not claim ProgAgent is wrong. Nothing above disputes its numbers; the disagreements
  recorded are about *scope*, chiefly that its "DTC" is not bash and its smallest model is 8B.
- It does not claim the open cell is novel by exhaustion. That claim would need a fresh
  literature sweep as of 2026-10-18, and no such sweep was run for this file. What is claimed
  is narrower: none of the seven cited works contains that cell, and ProgAgent, the closest,
  is missing two of its three defining features.
