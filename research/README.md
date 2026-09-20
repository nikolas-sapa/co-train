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

## Method notes
- Every arXiv ID cited was independently re-resolved against the arXiv API before acceptance.
- Vendor docs went stale twice (Kaggle P100, TRL doc paths). Vendor *source* was correct both
  times. Prefer source and test suites over docs for capability questions.
- Retrieval was degraded throughout: WebSearch broken (Bedrock rejects the tool type),
  `exa_search` off, Semantic Scholar 429 blackout, Twitter/Reddit channels off. Recall is
  arXiv + GitHub + Jina Reader only. **No practitioner/forum sources anywhere in this corpus.**

## Not yet done
- Research #3: browser use and fetch.
- Research #4: creative benchmark design (Vending-Bench 2 shape).
- Close read of LEGO-RL (arXiv 2608.17393) for prior-art delta.
