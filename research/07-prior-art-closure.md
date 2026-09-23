# 07 — Prior-art closure (2026-09-23)
Closes the OpenForgeRL open item from `06` §8. An arXiv phrase search on "harness-native" surfaced
**two further papers no lane had found**. All three read. This is the honest final assessment of how
much novelty the thesis still has.

## Headline: the thesis is now four papers deep in prior art. The remaining gap is real but narrow.

---

## The single most thesis-relevant sentence in the entire research effort

**OpenForgeRL** (arXiv **2607.21557v3**, 2026-07-23, *"Train Harness-native Agents in Any
Environment"*), verbatim from the abstract:

> "Beyond benchmarks, we analyze how harness choice (e.g., ZeroClaw, OpenClaw, Codex) and RL shape
> agent behavior. **We find that some harnesses are substantially harder to learn than others**, and
> that RL improves agentic reliability, such as self-verification, tool coverage, and completing
> multi-step plans, though critical abilities such as error recovery remain weak."

That is the thesis question — *does harness shape interact with training?* — asked and answered
affirmatively, seven weeks before LEGO-RL and two months before this research started.

### What OpenForgeRL actually built
- A **lightweight proxy that serves the harness's model calls while recording them as training
  data** for a standard RL codebase (veRL). Mechanically the same trick as LEGO-RL's in-process
  proxying, arrived at independently. **Two labs converged on proxy-the-model-call as the way to
  train against an arbitrary harness.** That is now the established pattern, not a clever idea.
- A **Kubernetes orchestrator running each rollout in its own remote container** — which is R2
  (isolate the verifier from the agent) falling out of an infrastructure decision.
- Results with *"only hundreds to a few thousand tasks"*: OpenForgeClaw **31.7 pass^3 / 55.9 pass@3**
  on ClawEval, **33.7** on QwenClawBench; OpenForgeGUI **37.7** OSWorld-Verified, **63.0**
  Online-Mind2Web, **72.3** WebVoyager. GUI results *"match or surpass models several times larger."*

### Why it does not close the question
1. **The harnesses compared are one family.** ZeroClaw, OpenClaw and Codex are all tool-calling
   agent harnesses. The axis `lanes/tokens.md` established as decisive — **plain shell vs
   programmatic tool calling** (arXiv 2609.11999, where bash beat PTC by 21.8-24.5 pp *untrained*) —
   is not among them.
2. **No cross-harness transfer test.** Same hole as LEGO-RL: train on A, deploy on A. DCAS
   (2608.06113) showed fine-tuning roughly doubles scaffold sensitivity, and neither harness-native
   RL paper checks whether its gains survive a harness swap.
3. **"Error recovery remains weak"** even after RL — which is HORIZON's finding reappearing inside a
   harness-native training result.

### Code availability — claimed, not found
The abstract says "open-source framework." A GitHub search returns only an alphaXiv paper mirror
(2 stars). **No canonical OpenForgeRL repo located.** Treat the framework as unavailable until
proven otherwise; do not plan on reusing it.

---

## Harness-Bench — the measurement framework this project would have had to build

**arXiv 2605.27922** (2026-05-27), *"Measuring Harness Effects across Models in Realistic Agent
Workflows."* Found by phrase search; invisible to every keyword the lanes used.

- **106 sandboxed offline tasks**, manually reviewed for *"realism, solvability, oracle-checkability,
  and integrity."* **5,194 execution trajectories.**
- Evaluates harness configurations **across multiple model backends under shared task environments,
  budgets, and evaluation protocols**, *"while preserving each harness's native execution behavior."*
- Records *"final artifacts, execution traces, usage statistics, and validator outputs."*
- Core claim, verbatim: **"agent capability should be reported at the model-harness configuration
  level rather than attributed to the base model alone."**

**That claim is this project's premise, already published with 5,194 trajectories behind it.**

It also names a failure mode the corpus had not: **"execution-alignment failures, where plausible
reasoning becomes decoupled from tool feedback, workspace state, evidence, or verifiable output
contracts."** That is a sharper description of what `lanes/browser.md` measured as the stale-tree
problem (models following a serialized tree over pixels on 0.88 of conflicting probes), generalised
beyond GUIs.

**Practical consequence:** if the tasks are obtainable, Harness-Bench is a ready-made,
oracle-checkable, offline, budget-matched measurement harness. That is weeks of work not to repeat.
No repo found — **open item**, worth one targeted search.

---

## Agentic Routing — adjacent, one idea worth stealing

**arXiv 2607.11399** (2026-07-13), *"The Harness-Native Data Flywheel."* Step-level model routing
conditioned on full harness state, in OpenSquilla, with a LightGBM cold-start ranker.

Not on the critical path. One transferable idea: every routing decision emits a structured record
*"whose labels are supplied by the environment rather than by the router itself"* — environment-
supplied labels as free training data. The same logic applies to our rejected-submission stream
(R30): verifier rejections are environment-labelled data, not just logs.

---

## Honest novelty assessment

| Prior work | What it establishes | What it leaves |
|---|---|---|
| **DCAS** 2608.06113 | Fine-tuning doubles scaffold sensitivity; 52.6→8.4 worst case | Doesn't train harness-native |
| **LEGO-RL** 2608.17393 | Harness-native RL works; +6.4/+5.8/+9.4 pts on 3 harnesses | No mixed/cross-harness (their stated future work) |
| **OpenForgeRL** 2607.21557 | **Some harnesses are substantially harder to learn than others** | One harness family; no transfer test; code not found |
| **Harness-Bench** 2605.27922 | Capability is a model-harness property, 5,194 trajectories | Evaluation only, no training |
| **Is Bash All You Need?** 2609.11999 | Bash beats PTC by 21.8-24.5 pp **untrained** | Nobody has trained either |

### What is left, stated plainly
1. **The bash-vs-PTC axis after training.** Every harness-native RL paper compares tool-calling
   harnesses to other tool-calling harnesses. The one axis with a large measured untrained gap, and
   a published baseline to beat, is untouched.
2. **Cross-harness transfer after harness-native training.** DCAS measured it without training;
   LEGO-RL and OpenForgeRL trained without measuring it. Nobody has joined the two.
3. **Small scale.** All three training papers use serious compute (35B MoE, Kubernetes clusters).
   Whether any of this reproduces at 0.6-1.7B on a free tier is unasked.

**This is a narrower project than it was two days ago, and a better-posed one.** The question is no
longer "does harness shape matter under training" — OpenForgeRL answered yes. It is: **"does
co-training reverse the bash-over-PTC ordering, and does the winner survive a harness swap?"**
Both halves have published baselines and neither has been run.

### The risk worth naming
Four papers in ten months on harness-native training means this area is moving fast and the gap may
close before a free-tier experiment finishes. Two mitigations: the bash-vs-PTC axis is oddly
neglected despite being the one with the biggest measured effect, and a *negative* result
(co-training does not reverse the ordering) is publishable and cheap.

## Open items
- **Harness-Bench tasks/code** — not located. One targeted search; high value if obtainable.
- **OpenForgeRL code** — claimed open-source, repo not found.
- Full texts of 2607.21557 and 2605.27922 read at abstract level only. Both warrant a full read
  before any build commitment, on the same reasoning that applied to LEGO-RL in `04`.
