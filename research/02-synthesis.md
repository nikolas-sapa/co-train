# 02 — Synthesis and decision
Date: 2026-09-20 · Inputs: `01-primary-sources.md` + `lanes/{harness,grpo,tokens,compute}.md` (4,901 lines)

## Executive summary

Three of the project's founding assumptions were tested against evidence. **Two failed, one
was inverted into the actual opportunity, and the real obstacle turned out to be something
the original plan never mentioned.**

1. **"Programmatic tool calling is token-efficient" — FAILED as stated.** The best controlled
   study finds plain bash beats PTC on *both* quality and cost. PTC is a fan-out optimization,
   not a general one.
2. **"Harness gain is inversely proportional to model capability" — FAILED.** The literature
   names two effects pointing the other way. Retired.
3. **"Nobody has trained a model around a harness" — TRUE but narrowing fast.** LEGO-RL
   published harness-native RL in Aug 2026. The gap is now more specific than "nobody did it."
4. **The real obstacle is harness-overfitting**, which the original plan never considered.
   DCAS measures it and, usefully, also measures the mitigation.

The project remains worth doing, is affordable (**$60–$200** for a first real experiment),
and is now aimed at a sharper question than it started with.

---

## Finding 1 — The PTC premise is inverted, and that is the opportunity

**arXiv 2609.11999, "Is Bash All You Need?"** (Microsoft + CMU, 2026-09-10). Five interfaces,
model / task text / base prompt / stopping criteria held constant. Opus-4.8 and GPT-5.5.
TheAgentCompany (174 tasks) + APEX-Agents (480 tasks).

| Interface | TAC / Opus-4.8 | Total tok | $/task |
|---|---|---|---|
| Tool-only | 44.9% | 945k | $1.20 |
| **Bash** | **69.4%** | **264k** | **$0.37** |
| PTC | 52.9% | 406k | $0.64 |

Bash beats typed tools by 21.8–24.5 pp (TAC) and 4.8–7.4 pp (APEX) at 19–72% fewer tokens.
PTC saved tokens in 4/4 arms but improved score in only **1/4**. Authors verbatim: PTC
*"underperform[s] shell-only on both quality and cost."*

**arXiv 2608.06370, "The Bitter Lesson of Tool Calling"** (2026-08-06) locates PTC's real
regime. Crossover is at **N ≈ 26 concurrent calls in one turn** — *fan-out count, not tool
catalog size*:

| Fan-out N | JSON tok | PTC tok | Δ |
|---|---|---|---|
| < 26 | — | — | PTC **more expensive** (fixed system-prompt overhead) |
| 30 | 3,559 | 3,380 | −5.0% |
| 48 | 5,097 | 3,535 | −30.6% |

JSON output scales linearly in N; a PTC script is ~constant (one `asyncio.gather`). On
*chained* sequential work PTC costs **1.5× the input tokens** of JSON. Accuracy is a different
story: PTC matches or exceeds JSON in 11/14 models, and under high fan-out GPT-5 goes
71.9% → 96.9%.

**Both vendor claims are unmeasured.** Anthropic's "150,000 → 2,000 tokens, 98.7% saving" is a
worked hypothetical about loading tool definitions: no model, no task set, no baseline, no n.
Cloudflare's code-mode post says "the results are striking" and gives zero numbers. Prime
Intellect's token claim is never isolated from the Continual Harness, subagents, or persistent
kernel shipped alongside it.

### The reframe
The paper measures **untrained** frontier models using PTC zero-shot. Prime Intellect states
plainly that *"no model has been trained around Prime Agent."* So the finding is not "PTC is
bad", it is **"PTC is the harness shape nobody has trained a model for, and it loses to bash
until someone does."**

That is a cheap, well-posed, publishable question with a *published baseline to beat*:
**does co-training close the PTC-vs-bash gap?**

---

## Finding 2 — Harness-overfitting is the real risk, and it has a known mitigation

**DCAS, arXiv 2608.06113** (ASE '26, ACM DOI 10.1145/3832783.3834485). Models fine-tuned on
one scaffold's trajectories, evaluated across four scaffolds, weights and benchmark fixed.

| Model | OpenHands | Claude Code | OpenCode | mini-swe | spread |
|---|---|---|---|---|---|
| Qwen3-32B (base, untrained) | 29.0 | 23.2 | 18.4 | 8.0 | 21.0 |
| SWE-Lego-Qwen3-32B (fine-tuned) | 52.6 | 44.2 | **8.4** | 37.6 | 44.2 |

**Read this carefully — I initially over-dramatized it.** The headline 52.6 → 8.4 (−44.2 pp)
cell is attributed by the authors to a *banal* cause: *"Tool-call format incompatibility
produces sharper failures… because its tool-call [format is incompatible]"* — the model emits
its training scaffold's tool-call format and OpenCode's parser rejects it.

DCAS itself leads with the **clean** figure: **−8.4 pp** (OpenHands → Claude Code), with
Nebius-SWE-Rebench-30B at −3.7 pp on the same pair. It uses −8.4 pp as its reference magnitude
throughout, not −44.2 pp. SERA-32B's −20.8 pp is part-attributed to a context-length conflict
with Claude Code's hard-coded ceiling.

**The load-bearing structural fact survives all of that**: the untrained base shows a 21.0 pp
spread; the fine-tuned model shows 44.2 pp. **Fine-tuning roughly doubled scaffold sensitivity.**
Harness-overfitting is fine-tuning-*induced*, and it is measured.

### The mitigation, also measured
`Qwen3-32B-Nex-N1` was trained on **diverse multi-format trajectories** rather than a single
scaffold. Result: 50.5% (OpenHands) vs 50.8% (Claude Code) — the gap closes entirely — though
it *"still degrades substantially on OpenCode (26.2%) and mini-swe-agent (15.6%)."*

**Design consequence for us:** train across multiple tool-call formats from day one, and treat
cross-harness evaluation as a first-class metric, not an afterthought. A single-scaffold result
is not a result.

---

## Finding 3 — The inverse-capability hypothesis is retired

The literature does **not** support a monotone inverse law. Two named effects point the other
way: **"harness leverage"** at r = 0.99 *positive*, and an **inverted-U** harness-benefit curve.
Stronger models do not reliably benefit less from scaffolding.

Supporting the coupling direction instead, **GPT-5-Codex** is the clearest public case of a
frontier model scoped to a harness, verbatim: *"purpose-built for Codex CLI… we recommend using
GPT-5-Codex only for agentic coding tasks in Codex or Codex-like environments."* A vendor-issued
deployment restriction. OpenAI's earlier **codex-1** advertised the opposite — *"strong
performance even without AGENTS.md files or custom scaffolding"* — so OpenAI publicly moved from
harness-robustness to harness-specificity between the two.

Anthropic: no harness-specific-training claim found.

**Coverage caveat:** Semantic Scholar returned HTTP 429 on all 5 attempts in this lane, so there
is no citation-ranked view and no citation-chain following. arXiv-only recall.

---

## Finding 4 — A custom harness IS trainable, with one hard prerequisite

From `trl` 1.13.0 source (`trl/trainer/grpo_trainer.py`, 3,492 lines).

`GRPOTrainer.__init__` (`:300-321`) exposes three agentic entry points of increasing generality:
- `tools=[fn, ...]` — stateless functions, schema parsed from type hints + docstring
- `environment_factory` — **stateful object, one instance per rollout**; public methods become tools
- `rollout_func` — you own generation entirely

Environment contract (`:266-283`): `reset` is required; **`get_reward` is optional and when
present the environment owns the reward**, called once per completed rollout, scored from
internal state.

### The trainability gate
A multi-turn trajectory is **one flat token sequence**; turn boundaries exist only in the mask.
TRL masks tool/environment tokens out of the loss via a parallel `tool_mask` (`:358`, extended
at `:404-412`). To know how many tokens a tool result occupies it does not guess —
`_get_tool_suffix_ids` (`:1933-1984`) renders a throwaway two-message conversation twice and
diffs.

**If the chat template is not prefix-preserving, TRL raises (`:1981-1982`) rather than
mis-masking.** Correct failure mode, but it makes **template compatibility a hard prerequisite,
not a tuning knob.** This must be verified on the chosen base model before any other work.

Also: **`mask_truncated_completions` defaults to `False` (`grpo_config.py:831`) — turn it on for
agentic rollouts.**

### Stack recommendation (from lane-grpo)
> Start on `trl` with a plain `environment_factory`; **skip Harbor**. Migrate to prime-rl +
> verifiers only on a concrete trigger: async throughput, a non-prefix-preserving chat template,
> or measured advantage collapse needing dynamic sampling.

---

## Finding 5 — It is affordable, and the unit economics are known

prime-rl ships `examples/basic/alphabet-sort`: a **real multi-turn agentic RL run**,
Qwen3-4B-Instruct-2507 + LoRA (rank 32, alpha 64), 3–5 turns per episode, 256 rollouts/step.

Measured, from its README: average reward **0.26 → 0.81**, 0% → **73% perfect attempts**, in
roughly an hour. Qualitatively the model *"explicitly breaks down its reasoning step-by-step,
even though chain-of-thought was never explicitly requested."*

| Tier | Cost |
|---|---|
| (a) Smoke test, loop runs end to end | **$5 – $30** |
| (b) First real experiment, measurable improvement | **$60 – $200** (midpoint ~$120) |
| (c) Serious run | **$1,500 – $10,000** |

**Budget against the pessimistic side — two documented contradictions in prime-rl's own repo:**
- READMEs say 100 steps; committed `rl.toml` says `max_steps = 200`. **Budget 200.**
- alphabet-sort README says "a single H100"; the committed config has no `[deployment]` block and
  `docs/scaling.md` defaults to 1 trainer + 1 inference GPU. **Budget 2 GPUs.** The README also
  states the full stack smoke test *"requires 2 GPUs"* — there is no 1-GPU path.

**The cost that is in none of the GPU tables: agentic sandboxes.** E2B's free tier caps at 20
concurrent sandboxes and 1-hour sessions, which throttles rollout concurrency independently of
GPU spend.

Hard constraint: prime-rl requires an NVIDIA GPU. Dev machine is darwin/arm64, so **all training
is rented**; local work is harness and environment code only.

---

## Finding 6 — Token count is not a valid cost proxy

**arXiv 2607.12161, "Token Reduction Is Not Cost Reduction."** Largest compression setup cut
delivered tool-output tokens **−38.4%** and *increased* provider-billed cost **+6.8%**. Pearson
**r = 0.15** between token reduction and cost reduction. Cause is cache dynamics: compression
breaks prefix caching, and cache-read tokens are billed at a fraction of uncached input.

**Consequence:** any token-efficiency claim this project makes must be validated in **billed
cost**, not token count. This also partly deflates the PTC penalty in Finding 1 — part of PTC's
measured overhead is an accounting-surface artifact, since JSON schemas pass through the API
`tools` parameter *"which some providers count separately from conversation input tokens."*

---

## Corrections to earlier project notes
| Earlier claim | Corrected |
|---|---|
| Prime Agent loses 3/9 to Claude Code, 3/9 to Codex | Wins 21/27 cells; loses 2 to CC, 3 to Codex, 1 to pi-mono |
| PTC pays off above ~26 *tools* | N ≈ 26 is **fan-out (concurrent calls per turn)**, not catalog size |
| DCAS shows a 52.6 → 8.4 capability collapse | That cell is **tool-call format incompatibility**; DCAS's own reference magnitude is **−8.4 pp** |
| nano-rlm is a one-tool harness | Canonical config is **ipython + `wait`** (min two); bash/edit/fetch/search exist as both native tools and IPython skills |
| Harness gain inversely ∝ model capability | Not supported; "harness leverage" r = 0.99 *positive*, plus an inverted-U effect |

---

## Recommended project shape

**Question:** Does co-training a small model against a PTC harness close the PTC-vs-bash gap
that arXiv 2609.11999 measured on untrained models?

Strong because: published baseline to beat · programmatic verifier already required · cheap
(~$120/experiment) · the negative result is publishable too.

**Non-goals** (explicit, per spec discipline):
- Not building a trainer. Use `trl`.
- Not building RL env plumbing. Use `environment_factory`.
- Not beating frontier models on SWE-bench.
- Not shipping a usable coding agent.

**Sequence:**
0. **Gate first — verify the chosen base model's chat template is prefix-preserving** against
   `_get_tool_suffix_ids`. If it raises, the whole approach is blocked on that model. This is a
   `/spike-first` unknown and it costs ~$0 to check.
1. Reproduce `alphabet-sort` end to end ($5–$30). Confirms the loop and the 0.26 → 0.81 delta.
2. Build the environment with a reward computed from state **the agent cannot write** (the
   Factorio RCON lesson: a prompt-level prohibition is not a constraint).
3. Implement bash and PTC harnesses behind one `environment_factory` interface. Measure the
   untrained gap; confirm it reproduces the published direction before training anything.
4. Co-train. Evaluate **cross-harness** from the first run (DCAS), in **billed cost** not tokens
   (2607.12161), with `mask_truncated_completions=True`.

## Open gaps
- Prior-art delta vs **LEGO-RL (arXiv 2608.17393)**, "Harness-Native RL for Coding Agents" — its
  stated limitation is no cross-harness test, which is exactly the DCAS hole. Needs a close read
  before committing.
- No Semantic Scholar coverage anywhere in this research (429 blackout); arXiv-only recall.
- No practitioner/forum sources: `exa_search` off, WebSearch broken, Twitter and Reddit channels off.
- Benchmark-design lane (query #4) and browser/fetch lane (query #3) not yet run.
