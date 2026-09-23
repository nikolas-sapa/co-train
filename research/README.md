# co-train — research index

Model-harness co-training: can a small model, RL-trained against a specific agent harness,
beat that harness's untrained baseline — and does it survive a harness swap?

## Documents
| File | What it holds |
|---|---|
| `01-primary-sources.md` | Repo/stack sweep. The Prime Intellect layering, the ACP training contract, nano-rlm anatomy, TRL Harbor, install paths. |
| `02-synthesis.md` | **Start here.** Decision document. What failed, what survived, recommended project shape, non-goals, sequence. |
| `03-free-compute.md` | Free GPU path (rev 2). Kaggle T4x2 verified from vendor source, TRL colocate, fp16 constraint. |
| `lanes/harness.md` | Harness-specific training, DCAS harness-overfitting, inverse-capability. 1,661 L |
| `lanes/grpo.md` | GRPOTrainer multi-turn API, loss masking, verifiers, failure modes. 1,336 L |
| `lanes/tokens.md` | PTC vs bash vs typed tools, compaction, token-vs-cost. 936 L |
| `lanes/compute.md` | Pricing, VRAM, wall-clock, three-tier dollar answer. 793 L |
| `lanes/bench.md` | Vending-Bench 2 verified, reward-hacking taxonomy, **34 design rules**. 336 L |
| `lanes/browser.md` | SPA detection, compile-the-flow, observation space, prompt injection, agent-web contract. 666 L |
| `04-prior-art-lego-rl.md` | LEGO-RL delta. Not scooped; their future work is our angle. |
| `05-delta-tierlist-and-rdi.md` | Berkeley RDI broke 8/8 agent benchmarks. Four harnesses the sweep missed. |
| `06-perplexity-delta.md` | **fp16-on-T4 unknown RESOLVED.** BenchJack tooling, practitioner failure modes, sandbox economics, from-scratch verdict. |

## Headline findings
1. **PTC loses to plain bash** on untrained models, on both quality and cost (arXiv 2609.11999).
   That is the opportunity: PTC is the harness shape nobody has trained a model for.
2. **Harness-overfitting is real and fine-tuning-induced.** DCAS (2608.06113): fine-tuning roughly
   doubled scaffold sensitivity. Mitigation is measured — multi-format trajectory training.
3. **Inverse-capability hypothesis is retired.** Literature shows a *positive* harness-leverage
   effect (r=0.99) and an inverted-U, not a monotone inverse law.
4. **Token count is not a cost proxy.** −38.4% tokens, +6.8% billed cost, r=0.15 (2607.12161).
5. **Trainability gate:** TRL masks tool tokens via `tool_mask`, but raises if the chat template
   is not prefix-preserving (`grpo_trainer.py:1981-1982`). Check before spending anything.
6. **Free is viable.** Kaggle T4x2 + TRL colocate + fp16 + Qwen3-0.6B. Paid fallback ~$120.
7. **Four literatures converge on the ACTION SPACE as the lever** (bash > typed tools; AgentOccam's
   action pruning was the only token-reducing step and the biggest accuracy gain; AutoTailor 1,283
   -> 33 APIs; verifier coverage decays as tool count grows). Shrink the actions, keep a fallback.
8. **Partial verifier hardening scores WORSE than none** (RECEIPT: 45% -> 9% -> ... -> 100%).
   Complete set or ship nothing.
9. **Broken verifiers teach hacking** — unreachable visible reward is the fastest-liftoff condition
   (38 steps vs 77). Test every verifier both ways.
10. **The uncapped scalar suits an RL target**, because binary scoring wastes ~75% of the rollout
    budget on ties. But uncapped buys headroom, not safety.
11. **Every major agent benchmark audited has been broken** (Berkeley RDI, 8/8, near-perfect scores
    with zero tasks solved and zero LLM calls). OpenAI dropped SWE-bench Verified after finding
    59.4% of audited problems had flawed tests. Verifier correctness is THE problem, not a detail.
12. **fp16 GRPO on T4 works** — Unsloth ships 40 Kaggle-targeted GRPO notebooks. The free path is
    unblocked, but use Unsloth rather than raw TRL+vLLM on Turing hardware.
13. **BenchJack (Apache-2.0) can attack our own verifier**, with a V1-V8 taxonomy and four
    adversarial toy agents. Build those four before the environment is finished.
14. **From-scratch pretraining is a detour.** nanochat's $100 buys a GPT-2-class model (MMLU 31%);
    useful agents need >=1B params and >=1T tokens. A 7B LoRA costs $40-200.

## Method notes
- Every arXiv ID cited was independently re-resolved against the arXiv API before acceptance.
- Vendor docs went stale twice (Kaggle P100, TRL doc paths). Vendor *source* was correct both
  times. Prefer source and test suites over docs for capability questions.
- Retrieval was degraded throughout: WebSearch broken (Bedrock rejects the tool type),
  `exa_search` off, Semantic Scholar 429 blackout, Twitter/Reddit channels off. Recall is
  arXiv + GitHub + Jina Reader only. **No practitioner/forum sources anywhere in this corpus.**

## Status
All six research lanes complete (~6,700 lines). `02-synthesis.md` carries the decision, including
an addendum folding in the bench and browser lanes and a revised build sequence.

## Next
Execute the build sequence in `02-synthesis.md` as amended by `06-perplexity-delta.md` §1 and §2:
1. Four adversarial toy agents (null, random, prompt-injection, state-tampering) — cheapest
   high-value work available, and they must exist before the environment is called done.
2. Unsloth on Kaggle T4x2, fp16, `use_vllm=False`, Qwen3-0.6B, 5-step smoke test.
3. Verifier first, environment second. Snapshot-restored, replay-scored, verdict-token-bound,
   role-separated. Complete set or nothing.
Set `NCCL_CUMEM_ENABLE=0` before any vLLM weight sync (180s -> 4s on 70B).
