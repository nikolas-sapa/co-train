# HANDOFF — model-harness co-training

**Read this first. Then `research/02-synthesis.md`, then `research/07-prior-art-closure.md`.**
Status as of 2026-09-23: **research complete, no code written.** 7,174 lines across 13 commits.

---

## The question

> **Does co-training a small model against a programmatic-tool-calling (PTC) harness reverse the
> bash-over-PTC ordering that arXiv 2609.11999 measured on untrained models — and does the winner
> survive a harness swap?**

Both halves have published baselines. Neither has been run.

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

### Step 1 — Four adversarial toy agents (do this FIRST, before the environment exists)
From Berkeley RDI's Agent-Eval Checklist: **null, random, prompt-injection, state-tampering.**
Rule: *"if any non-solver scores above baseline, the benchmark is considered broken."*

This is the cheapest high-value work in the whole plan and it is the concrete form of R24. It also
inverts the usual order deliberately: **you cannot write the verifier correctly until you have
something trying to break it.**

### Step 2 — Prove the loop on free hardware
Kaggle, accelerator `NvidiaTeslaT4` (= T4 x2), **Unsloth** (not raw TRL — see Hard Constraints),
fp16, LoRA rank 16-32, Qwen3-0.6B, `use_vllm=False`, 5 steps. Goal is only: does it run and is
fp16 stable.

### Step 3 — Verifier before environment
Snapshot-restored verification instance · constrained replay · verdict bound to a fresh
verifier-minted token · role separation so the agent never holds keys to the ledger it is scored on.
**Complete set or ship nothing** — RECEIPT's ablation: 45% (self-judgment) → **9%** (partial) →
100% (full). Partial hardening scores *worse than none*.
Then **test it both ways**: reference solution must PASS, planted mutant must FAIL.
Then run **BenchJack** (`github.com/benchjack/benchjack`, Apache-2.0) against it.

### Step 4 — Environment, minimal action space, escalation channel from day one
Reward computed from state the agent cannot write. Structured escalation channel (cut hacking
23.6%→5.3% across 8 models at no perf cost, *and* doubles as verifier-QA). Plant one instrumented
rule-legal shortcut so hack telemetry is deterministic.

### Step 5 — Two harnesses behind one interface, measure untrained first
bash and PTC. **Confirm the published gap reproduces in your setup before training anything.**

### Step 6 — Co-train, then evaluate cross-harness
Cross-harness eval from run 1. Report **billed cost**, not tokens. `mask_truncated_completions=True`.

---

## Hard constraints (expensive to rediscover)

| Constraint | Detail |
|---|---|
| **No local training** | Dev machine is darwin/arm64. prime-rl requires NVIDIA. All training rented or Kaggle. |
| **Kaggle reality** | T4 x2 (P100 retired 2026-09-15), **30 GPU-h/week**, **12 h/session**, **20-30 min idle timeout**, 20 GB persisted at `/kaggle/working`. No A100/H100 free. Multi-process vLLM+trainer in one session is demonstrated (`kaggle-vllm`). |
| **T4 = no bf16** | Compute capability 7.5. bf16 needs 8.0. fp16 only. vLLM floor is 7.5, so T4 just clears it; **P100 (6.0) cannot run vLLM at all.** |
| **Use Unsloth on T4, not raw TRL** | A TRL PR exists *solely* because "T4 in collab need fp16 and vllm defaults to bf16." Unsloth ships 40 Kaggle GRPO notebooks and has done the fp16-on-Turing work. Migrate to TRL/prime-rl only when renting proper hardware. |
| **TRL trainability gate** | TRL raises at `grpo_trainer.py:1981-1982` if the chat template is not prefix-preserving. Escape hatch if it fails: proxy the model call (LEGO-RL and OpenForgeRL both do this). |
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
   also the biggest single accuracy gain.
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
- **fp16 GRPO on Qwen3 specifically at 0.6-1.7B.** 40 Kaggle GRPO notebooks exist, and Gemma-3's
  fp16 failure (activations >800k vs fp16 max 65,504) is architecture-specific and does not apply to
  Qwen3 — but no public log shows Qwen3 GRPO fp16 loss/KL curves on T4. You are in a narrow but
  travelled corridor.
- **Harness-Bench tasks/code** — 106 oracle-checkable tasks, would save weeks. Repo not located.
- **OpenForgeRL code** — claimed open-source, repo not found (only a 2-star paper mirror).
- **R33 dispersion+level screening** for continuous rewards — unvalidated, publishable either way.
- Full texts of 2607.21557 and 2605.27922 read at abstract level only.

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
| `research/07-prior-art-closure.md` | Before committing to the thesis. Honest novelty assessment. |
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

## Starting the next session
Invoke `/superpowers:brainstorming` before writing code — the project-level skill gate requires it
for new feature work, and the environment design genuinely has undefined scope.
