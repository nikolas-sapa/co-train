# 06 — Perplexity delta (2026-09-23)
Six deep-research reports supplied by the user. Only decision-changing content recorded.
Load-bearing claims independently re-verified by the lead before acceptance (see Verification).

## Headline: the blocking unknown is resolved, and the stack recommendation flips for the free path.

---

## 1. fp16 GRPO on T4 — VIABLE. Unknown closed.

`03-free-compute.md` flagged this as the main technical risk with "no evidence found either
direction." There is evidence, and it is mostly positive.

**Hard evidence:** `unslothai/notebooks` contains **40 Kaggle-targeted GRPO notebooks**, including
`Kaggle-Qwen2.5_(3B)-GRPO.ipynb`, `Kaggle-DeepSeek_R1_0528_Qwen3_(8B)-GRPO.ipynb`,
`Kaggle-Gemma3_(1B)-GRPO.ipynb`, and `Kaggle-Muse_Glimmer_(30B)-GRPO.ipynb`. Kaggle-targeted means
T4, which means fp16. These are not proposals; they are shipped notebooks.

**Unsloth's position is stronger than "it works":** they cite *"Defeating the Training-Inference
Mismatch via FP16"* and report their own experiments where **fp16 had smaller gradient norms and
was more stable than bf16** for RL. Their stated usage is `dtype = torch.float16` and "we'll take
care of the rest."

**The documented failure case is architecture-specific, not T4-specific.** Gemma-3 activations
exceed **800,000** against fp16's max of **65,504**, so naive autocast produces infinite activations
and gradients on T4/RTX20/V100. Unsloth's fix keeps activations in bf16/fp32, does matmuls in fp16,
and upcasts layernorm. A LLaMA-family 1.8B peaks around **324**. **Qwen3 does not exhibit Gemma-3's
activation range**, so the specific documented failure does not apply to our chosen base.

**But the TRL+vLLM path on T4 is the risky one.** A TRL PR added vLLM dtype configuration with the
motivation, verbatim: *"T4 in collab need fp16 and vllm defaults to bf16 :)"*. Before it, `use_vllm=True`
on T4 defaulted vLLM to bf16 while training ran fp16 — a training-inference dtype mismatch, exactly
the class of bug that collapsed RL elsewhere (vLLM <0.11.0 cascade attention caused KL and reward
collapse on A100; Unsloth now disables cascade attention on old vLLM).

### Decision change
**For the free Kaggle path, use Unsloth rather than raw TRL + vLLM.** This does not overturn
lane-grpo's "start on TRL" recommendation — that was reasoned about API generality on proper
hardware. It is a *hardware-specific* override: Unsloth has done the fp16-on-Turing work and TRL has
not. Sequence: Unsloth on Kaggle to prove the loop, migrate to TRL/prime-rl if and when renting.

First iteration should set `use_vllm=False` — Unsloth themselves recommend this when the inference
stack is suspect, and it removes an entire class of dtype mismatch.

**Still unverified:** no public log exists titled "GRPO on Qwen3 0.5-4B in fp16 on T4, here are the
loss/KL/overflow plots." The report says so explicitly. We are in a narrow but travelled corridor.

---

## 2. BenchJack — R31 now has tooling, and I can attack my own verifier

`05-delta-tierlist-and-rdi.md` recorded RDI's blog. There is a paper and two Apache/MIT tools.

| Artifact | Detail |
|---|---|
| Paper | **arXiv 2605.12673**, *"Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent Benchmarks with BenchJack"* — verified |
| `benchjack/benchjack` | 46 stars, **Apache-2.0**, pushed 2026-05-25 — verified |
| `moogician/trustworthy-env` | 62 stars, **MIT**, pushed 2026-04-07 — verified |

Results: **219 distinct flaws across 10 benchmarks**, near-perfect scores on 9/10 without solving
any task.

### The V1-V8 taxonomy (use this as the environment-design checklist)
| ID | Class | Our exposure |
|---|---|---|
| V1 | Isolation failure (agent and evaluator share environment) | **Primary risk.** R2 addresses it |
| V2 | Answers shipped with the test | Applies if any gold state is on disk |
| V3 | RCE into evaluator (`eval()`/`exec()` on agent data) | Applies to any parsed submission |
| V4 | LLM-judge prompt injection | Avoided if reward is programmatic |
| V5 | Weak string matching | Applies to any substring/normalized check |
| V6 | Evaluation logic gaps (scoring doesn't validate success) | **R31 catches this** |
| V7 | Trusting untrusted output (logs, test output from agent env) | **Primary risk** |
| V8 | Excessive permissions (root, network, writable binaries) | Applies to every sandbox choice |

### The cheapest thing on this entire list
The **Agent-Eval Checklist** ships four adversarial toy agents — **null, random, prompt-injection,
state-tampering**. The rule: *"if any non-solver scores above baseline, the benchmark is considered
broken."* That is four trivial scripts and it is the concrete implementation of R24 ("apply real
optimization pressure before declaring the environment safe"). **Build these before the environment
is finished, not after.**

### Patching is possible, and the asymmetry is instructive
Under iterative attacker-defender refinement: WebArena ~100% → <5% → **0%** hackable;
OSWorld ~100% → 7.9% → **0%**; SWE-bench Pro 100% → **23%**. **Terminal-Bench remains structurally
broken** because verifier logic still runs in the agent's container as root with network and
writable system binaries — V1/V7/V8 uncorrected. The ones that got to zero did so by *structural*
separation, not by patching individual exploits. Confirms R2 and R6.

---

## 3. Kaggle confirmed, with two corrections in our favour

Kaggle's **2026-09-15 product announcement** confirms `03-free-compute.md` rev 2 independently:
P100 retired, *"Sessions run on the default GPU (NvidiaTeslaT4) instead."* L4 exists but only for
"a small set of competitions." No A100/H100 on the free tier, confirmed across multiple sources.

**Two corrections to my doc:**
- **Session limit is 12 hours, not 9.** Kaggle raised it from 9h to 12h for CPU and GPU notebooks.
  TPU stays ~9h. My rev-2 assumed the 12h cap without sourcing it; now sourced.
- **Idle timeout is 20-30 minutes, not 60.** I wrote 60 from the docs page. Community reports say
  20-30. Checkpoint more aggressively than planned.

**The unlock I did not expect:** a live project, `kaggle-vllm`, documents the validated runtime as
**2 × Tesla T4 (SM75), 15,360 MiB each, PyTorch 2.10.0+cu128, CUDA 12.8**, and demonstrates
`vllm serve` running inside a Kaggle notebook on dual T4s with real two-rank NCCL. **Multi-process
vLLM + trainer in one Kaggle session is demonstrated, not theoretical.** Constraint: 2×16 GB is
tight for two concurrent large models, so either tensor-parallel one model across both cards or run
generation and training sequentially.

---

## 4. Practitioner evidence — the gap that was empty is now filled

This is the material the corpus most lacked. Highest-value items only.

**Reward hacking, observed in production (Prime Intellect):** verbatim — *"the agent shares a
sandbox with the grading machinery, and a policy under RL pressure will eventually find whatever
seam is left – a test file it can edit, grading state it can tamper with, an artifact that leaks the
expected answer."* Their fixes are architectural and directly reusable:
- Rebuild task images so **tests, expected outputs and grading scripts are hidden during rollouts
  and restored only at scoring time**, even when upstream images shipped them readable.
- Run **gold-patch and no-op validation passes** and drop any task gradeable as solved with zero
  edits. **This is R31, independently arrived at, in production.**
- Roadmap: grading in fully isolated sandboxes. (= R2.)

**GRPO hyperparameters that actually broke (Aayush Garg, Qwen2.5-Math-1.5B):**
- `lr = 1e-4` → **policy collapse**, response-length spikes, token entropy to near zero. `3e-5` stable.
- Removing the group-mean baseline → gradient norms blow up, response length collapses.
- **Off-policy reuse of 16 optimizer steps per rollout batch → collapse mid-run**, length down to
  ~100 tokens. On-policy (1 step) best; 2 acceptable.
- Removing std-normalisation (Dr. GRPO style) → smoother gradients but plateaus at 0.65 vs 0.72.
- **Early-warning signals to log: gradient norm, `mean_response_length`, token entropy.** When norms
  spike or lengths drop sharply, the run is unhealthy. Cheapest instrumentation available.

**vLLM weight sync, the 45x fix:** Gloo broadcast of a 70B policy took **~180 s per sync, about a
quarter of total training time**. NCCL hung with `Cuda failure 'invalid argument'`. Fix:
`export NCCL_CUMEM_ENABLE=0` → **180 s → 4 s** (70B), **5-6 s → 0.85 s** (8B). One environment
variable.

**Throughput trap:** OpenEnv per-episode WebSocket connections cost 1000+ handshakes per 1000
episodes, 10-50 s of pure overhead plus concurrency-limit pressure. Fix: one module-level persistent
connection for the whole run.

**Avoid LLM-as-judge in the reward (Spheron):** it *"roughly doubles total compute per step and adds
systematic bias"*, and non-deterministic sandboxes make *"reward variance dominate the training
signal"* so learning stalls. Use fully verifiable rewards and `--network none --read-only`.

**Cost calibration points, real:**
- Garg: **~$140 total** for 20+ GRPO ablation runs (including failures) on Modal H100s. 20 steps
  ≈ 28 min on a 24 GB RTX 4090; ~10 min on tuned H100.
- GRPO-Zero: Qwen2.5-**3B** on a single **A40 48 GB**, "a few hours", **$0.44/hr on RunPod ⇒ $1-2
  per run**. Supports 24 GB cards by offloading optimizer state to CPU.

These sit *below* `compute.md`'s $60-200 tier-(b) estimate, which was built from prime-rl's
4-GPU reference shape. **Tier (b) is probably conservative by several multiples for a 0.6-3B model.**

---

## 5. Sandbox economics — the risk `compute.md` named but could not price

At 2 vCPU / 4 GiB per rollout and **256 concurrent**:

| Provider | $/sandbox-hr | 256 concurrent | Concurrency ceiling | Burst cold start |
|---|---|---|---|---|
| E2B | $0.1656 | **~$42/hr** | Hobby **20** (unusable), Pro 100, addons to 1,100 | median ~1.6 s (vendor claims <200 ms sequential) |
| Daytona | $0.1656 | ~$42/hr | governed by creation rate (300-600/min) | 27-90 ms warm; 2-5 s misconfigured |
| Modal | ~$0.238 | **~$61/hr** | plan-gated 100-1,000 containers | ~0.88 s median |
| Fly Machines | preset-based | **~$3.5-9/hr** | account quota | <1 s |

Three things bite: **plan-gated concurrency** (E2B Hobby's 20-sandbox cap rules out 256 outright),
**wall-clock billing** (you pay while the sandbox idles, and long-horizon environments idle a lot),
and **burst cold starts** (vendor numbers are sequential; concurrent bursts are 5-10x worse).

**Consequence:** at 256 rollouts/step, sandbox cost is the same order as GPU cost. Packing many
rollouts per VM (Fly Machines / Docker-on-a-rented-box) is ~5-10x cheaper than per-sandbox
infrastructure, at the cost of weaker isolation — which collides directly with V1/V8 above. **Real
tension: cheap sandboxes and tamper-proof verification pull opposite ways.** Resolve it by keeping
the verifier out of the rollout sandbox entirely (R2) rather than by hardening each sandbox.

---

## 6. Build-your-own-model: it is a detour, quantified

- **nanochat ~$100 is still accurate** (8×H100, ~4-5 h at ~$24/h). What you get: ~560M params on
  ~11B tokens, CORE ≈ 0.22 vs GPT-2-large 0.21, **MMLU ~31%**, GSM8K and HumanEval in single digits.
  Karpathy's own scaling: ~$300 beats GPT-2 on CORE; $600-1000 reaches "simple math and coding."
- Next rung up, SmolLM-style **1B on 45B tokens**: 8×H100 × 1.5 days ≈ **$600-900**.
- **TinyLlama 1.1B (3T tokens): ~34,560 GPU-hours, $70-140k.** SmolLM3 3B: **437,760 GPU-hours.**
- Useful-agent threshold is **≥1B params and ≥1T tokens** (token multiplier 3000-5000). nanochat's
  default is a token multiplier of ~20.
- Meanwhile a **LoRA fine-tune of a 7B is $40-200**.

**Verdict: from-scratch pretraining is worth it only to learn the pipeline, not to get an agent.**
nanochat is the capstone lab. For this project's actual question, fine-tuning a small open base is
the correct call and costs less. This retires the "build my own model" thread as a *separate*
project, not a prerequisite.

---

## 7. Environment options — EcoGym is not what `bench.md` hoped

`bench.md` flagged EcoGym as *"the closest open codebase to Vending-Bench — worth cloning."*
Correction: **it is an LLM-agent evaluation harness, not a Gym-style RL environment.**

`OPPO-PersonalAI/EcoGym`, Apache-2.0, created Feb 2026. No `env.reset()` / `env.step(action)`, no
training script, no replay buffer, no TRL/prime-rl dependency. Built on Agno with one-tool-call-per-
turn and a `task_done` tool; reward computed by `cal_metric(final_state)` at episode end. **As of
Sept 2026 there are no public reports of anyone using it as an RL training environment.**

One thing it does get right and worth copying: **reward is a function of business state and hidden
parameters, not a value the agent can write**, and termination (bankruptcy, burnout, DAU collapse)
is environment-enforced. That is R1 satisfied by construction.

**More RL-ready alternatives it surfaced:**
- **AgentGym-RL** (`WooooDyy/AgentGym-RL`, arXiv **2509.08755** verified) — 7 scenario families,
  14 tasks, common reset/step interface, per-environment HTTP servers, supports PPO/GRPO, and ships
  **ScalingInter-RL** (start short-horizon, extend gradually) specifically to fight horizon collapse.
  **The strongest drop-in candidate found.**
- **EnterpriseArena** — 132-month CFO simulation; terminal value = `5 × trailing revenue + cash −
  5,000 × N_tool_calls`, which is a **metered-cost objective in the Vending-Bench-2 spirit**, plus a
  hard bankruptcy constraint.
- **DeliveryGym** (arXiv 2609.19801) — explicitly advertised as a verifiable, scalable RL environment.
- **CUA-Gym** (arXiv **2605.25624** verified) — verifiable training environments for computer-use
  agents, trained with GSPO.

---

## 8. New prior art — one more hit on the thesis

**OpenForgeRL, "Train Harness-Native Agents in Any Environment"** (submitted 2026-08-07): end-to-end
training *inside native inference harnesses*, explicitly targeting train-deploy mismatch. Same family
as LEGO-RL. **Not yet fetched or verified by the lead — open item**, and it must be read before
committing, the same way LEGO-RL was in `04`.

Also surfaced, both verified: **arXiv 2502.01600** *"Reinforcement Learning for Long-Horizon
Interactive LLM Agents"* (~114 Google Scholar citations, AppWorld, LOOP variant of PPO) and
**arXiv 2509.08755** AgentGym-RL (~35 citations). Both were invisible to keyword search and are the
citation-ranked recall the Semantic Scholar blackout cost us.

**Harbor (ICLR 2026)** is framed as making *"the transition from executable evaluation to trainable
environment construction explicit"* — i.e. harness-as-RL-environment. That reframes TRL's
`trl.experimental.harbor` from an implementation detail to a published position.

---

## Verification
Independently re-checked by the lead before acceptance:
- arXiv **2605.12673** (BenchJack) — resolves, title matches.
- `benchjack/benchjack` Apache-2.0 46 stars; `moogician/trustworthy-env` MIT 62 stars — both live.
- arXiv **2502.01600**, **2509.08755**, **2605.25624** — all resolve, titles match.
- `unslothai/notebooks` — **40** Kaggle GRPO notebooks confirmed by tree listing, names quoted above.

Accepted on the reports' word, NOT re-verified: all pricing figures, all citation counts, the Kaggle
product-announcement contents, Garg's and GRPO-Zero's numbers, the Unsloth fp16-vs-bf16 gradient-norm
claim, and OpenForgeRL's existence.
