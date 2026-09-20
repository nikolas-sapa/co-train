# Lane: Real Compute Cost to RL-Finetune a Small Model on Agentic Rollouts (Single Node)

**Research date: 2026-09-19.** Every web fetch in this document was made on 2026-09-19 via
`curl -fsSL "https://r.jina.ai/<URL>"`, `raw.githubusercontent.com`, or the HuggingFace raw file
endpoint. WebSearch was unavailable (HTTP 400) for the duration of this lane.

**Labeling convention used throughout:**
- **[SOURCED]** — the number appears verbatim on a page I fetched. URL + fetch date given.
- **[ESTIMATED]** — I computed it. The arithmetic is shown inline. No estimate appears without its arithmetic.
- **[UNVERIFIED]** — commonly-cited but I could NOT confirm it from a reachable primary source. Do not rely on these.

---

## 0. Bottom line up front

**A first real experiment costs on the order of $60–$200 (midpoint ~$120).**

The project is affordable. The reason is specific and checkable: prime-rl ships a working multi-turn
agentic RL config (`examples/basic/alphabet-sort`) that trains Qwen3-4B with LoRA and moves average
reward from 0.26 to 0.81, and it is sized for one or two H100s at roughly an hour per run. You are not
funding a research program; you are funding a handful of ~2-hour runs on 2 rented GPUs.

The budget risk is NOT the GPU hourly rate. It is:
1. the sandbox-concurrency ceiling on agentic rollouts (E2B free tier caps at 20 concurrent sandboxes
   and 1-hour sessions), and
2. the fact that prime-rl's stated wall-clock is README prose that **contradicts its own committed
   config** on both step count and GPU count (details in section 4).

---

## 1. Hard context for this lane

The developer machine is Apple Silicon (darwin/arm64). prime-rl's README states plainly:

> "Currently, you **need at least one NVIDIA GPU to use prime-rl**."
> — [SOURCED] https://raw.githubusercontent.com/PrimeIntellect-ai/prime-rl/main/README.md line 72, fetched 2026-09-19

So **100% of training compute is rented**. There is no local-GPU fallback and no hybrid option. Every
hour in this document is an hour someone pays for.

### The reference compute shape

From TRL's `examples/grpo_harbor/grpo_harbor.py` docstring
[SOURCED] https://raw.githubusercontent.com/huggingface/trl/main/examples/grpo_harbor/grpo_harbor.py, fetched 2026-09-19:

```
Usage (server vLLM, single-node 2+2 GPU split):

# Terminal 1 - vLLM
CUDA_VISIBLE_DEVICES=2,3 VLLM_SERVER_DEV_MODE=1 vllm serve Qwen/Qwen3-4B --tensor-parallel-size 2 --port 8000 \
    --weight-transfer-config '{"backend": "nccl"}' \
    --logprobs-mode processed_logprobs \
    --max-logprobs -1

# Terminal 2 - training
CUDA_VISIBLE_DEVICES=0,1 accelerate launch \
    --config_file examples/accelerate_configs/deepspeed_zero2.yaml --num_processes 2 \
    examples/grpo_harbor/grpo_harbor.py \
    --vllm-mode server --vllm-server-base-url http://localhost:8000 --env e2b
```

That is 4 GPUs: 2 training (accelerate + deepspeed_zero2) + 2 vLLM serving (tensor-parallel-size 2),
weight transfer over NCCL. The script's defaults are `--model Qwen/Qwen3-4B`, `--agent bash`,
`--env docker` (with `e2b` recommended in the docstring), and dataset
`AdithyaSK/data_agent_rl_environment_train`. [SOURCED, same file+date]

prime-rl's equivalent default is smaller: **1 trainer GPU + 1 inference GPU.**

> "`rl` defaults to 1 trainer GPU and 1 inference GPU."
> — [SOURCED] https://raw.githubusercontent.com/PrimeIntellect-ai/prime-rl/main/docs/scaling.md line 35, fetched 2026-09-19

TRL requires the two processes be on **separate CUDA devices** in server mode:

> "When using vLLM with TRL, the **vLLM server** and the **trainer** must run on **separate CUDA
> devices** to prevent conflicts."
> — [SOURCED] https://huggingface.co/docs/trl/main/en/vllm_integration, fetched 2026-09-19

TRL offers two modes. **Colocate mode** (the default) runs vLLM inside the trainer process sharing GPU
memory; **server mode** runs vLLM as a separate process on dedicated GPUs communicating over HTTP.
[SOURCED, same URL+date]. This distinction drives the entire VRAM analysis in section 3.

---

## 2. Pricing table

All rows fetched **2026-09-19**.

### 2.1 Primary table — the GPUs this project would actually use

| Provider | GPU | VRAM | $/GPU-hr | On-demand vs spot | Source URL |
|---|---|---|---|---|---|
| RunPod | H100 SXM | 80 GB | $3.49 | on-demand (tier ambiguous, see note A) | https://www.runpod.io/pricing |
| RunPod | H100 PCIe | 80 GB | $2.89 | on-demand | https://www.runpod.io/pricing |
| RunPod | H100 NVL | 94 GB | $3.19 | on-demand | https://www.runpod.io/pricing |
| RunPod | A100 SXM | 80 GB | $1.59 | on-demand | https://www.runpod.io/pricing |
| RunPod | A100 PCIe | 80 GB | $1.59 | on-demand | https://www.runpod.io/pricing |
| RunPod | L40S | 48 GB | $1.09 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX 6000 Ada | 48 GB | $0.84 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX A6000 | 48 GB | $0.53 | on-demand | https://www.runpod.io/pricing |
| RunPod | A40 | 48 GB | $0.49 | on-demand | https://www.runpod.io/pricing |
| RunPod | L40 | 48 GB | $0.82 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX 5090 | 32 GB | $0.99 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX 4090 | 24 GB | $0.74 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX 3090 | 24 GB | $0.50 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX A5000 | 24 GB | $0.27 | on-demand | https://www.runpod.io/pricing |
| RunPod | L4 | 24 GB | $0.49 | on-demand | https://www.runpod.io/pricing |
| RunPod | RTX Pro 6000 | 96 GB | $2.09 | on-demand | https://www.runpod.io/pricing |
| RunPod | H200 | 141 GB | $4.59 | on-demand | https://www.runpod.io/pricing |
| RunPod | B200 | 180 GB | $6.79 | on-demand | https://www.runpod.io/pricing |
| RunPod | B300 | 288 GB | $7.89 | on-demand | https://www.runpod.io/pricing |
| Lambda | H100 SXM (8x) | 80 GB | $3.99 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | H100 SXM (4x) | 80 GB | $4.09 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | A100 SXM (8x) | 80 GB | $2.79 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | A100 SXM (8x) | 40 GB | $1.99 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | A100 PCIe (4x) | 40 GB | $1.99 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | A6000 (4x) | 48 GB | $1.09 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | B200 SXM6 (8x) | 180 GB | $6.69 | on-demand only, NO spot | https://lambda.ai/pricing |
| Lambda | V100 (8x) | 16 GB | $0.79 | on-demand only, NO spot | https://lambda.ai/pricing |
| Vast.ai | H100 SXM | 80 GB | $1.73 floor / **$2.22 median** | marketplace, mixed interruptible | https://vast.ai/pricing |
| Vast.ai | H100 PCIE | 80 GB | $2.00 floor / **$2.54 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | H100 NVL | 80 GB | $2.00 floor / **$2.87 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | A100 SXM4 | 80 GB | $0.47 floor / **$0.75 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | A100 PCIE | 80 GB | $0.33 floor / **$0.85 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | L40S | 48 GB | $0.47 floor / **$0.80 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX A6000 | 48 GB | $0.43 floor / **$0.60 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX PRO 6000 S | 48 GB | $0.96 floor / **$1.53 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX PRO 6000 WS | 96 GB | $0.93 floor / **$1.47 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX PRO 6000 Max-Q | 96 GB | $0.52 floor / **$1.40 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX 5090 | 32 GB | $0.27 floor / **$0.70 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX 4090 | 24 GB | $0.14 floor / **$0.53 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX 3090 | 24 GB | $0.10 floor / **$0.20 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | RTX A5000 | 24 GB | $0.15 floor / **$0.23 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | A10 | 24 GB | $0.20 floor / **$0.24 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | L4 | 24 GB | $0.13 floor / **$0.32 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | H200 | 141 GB | $2.63 floor / **$4.74 median** | marketplace | https://vast.ai/pricing |
| Vast.ai | B200 | 192 GB | $8.13 floor / **$8.75 median** | marketplace | https://vast.ai/pricing |
| Prime Intellect | ALL | — | **UNKNOWN** | — | see Known Gaps #1 |
| Hyperbolic | ALL | — | **UNKNOWN** | — | see Known Gaps #2 |

All rows above are [SOURCED], fetched 2026-09-19.

### 2.2 Page freshness

- RunPod page carries its own banner: **"Updated September 13, 2026"** [SOURCED] — 6 days stale at fetch. Good.
- Lambda page `Published Time: Thu, 17 Sep 2026` [SOURCED] — 2 days stale. Good.
- Vast.ai page `Published Time: Tue, 15 Sep 2026` [SOURCED] — 4 days stale, but Vast prices are
  live-market and the page says so ("Prices set by supply and demand across 40+ data centers"), so
  treat the numbers as indicative of a market, not a fixed rate card.

### 2.3 Reading notes — these change the numbers materially

**Note A — RunPod Community vs Secure Cloud is UNRESOLVED.** The pricing page renders a
`Community Cloud | Secure Cloud` toggle in JavaScript. The text proxy returned exactly one price per
GPU — whichever tier was the default render. H100 SXM at $3.49 is consistent with Secure Cloud rates.
**Community Cloud is typically cheaper and I could not read it.** Budget against the table above and
treat any Community saving as upside. Confidence: moderate on which tier was captured.

**Note B — Vast "from" prices are a trap. Use the median column.** The "from" figure is the single
cheapest listing on the platform at fetch time: heterogeneous consumer hardware, unknown host
reliability, frequently interruptible. The gap is large and systematic — RTX 4090 is $0.14 floor
versus $0.53 median (3.8x), H200 is $2.63 versus $4.74 (1.8x). **Every Vast-based cost in section 5
uses the median.** Quoting the floor would understate a real budget by 2-4x.

**Note C — Lambda has no spot tier and no consumer cards.** No L40S, no 4090, no 5090 anywhere on the
page. If the plan is "cheap 24GB cards", Lambda is not a candidate. Lambda prices are also quoted
"plus applicable sales tax/VAT/GST" [SOURCED] — every other provider's quoted price here is pre-tax too,
but Lambda states it explicitly.

**Note D — Lambda reserved capacity costs MORE than on-demand, not less.** 1-Click Clusters, H100,
2 weeks to 1 year commitment: 16 GPUs at $6.16/GPU/hr, 64 at $5.85, 256 at $5.54 [SOURCED]. Compare
$3.99 on-demand for the 8x instance. Do not assume a commitment buys a discount here; for this
project's scale it does the opposite.

**Note E — RunPod Serverless is a different product and priced much higher** (B300 $9.98/hr,
B200 $8.64/hr, H200 $5.93/hr) [SOURCED]. Irrelevant to a persistent trainer+vLLM setup. Listed only so
nobody quotes it by mistake.

---

## 3. VRAM feasibility

### 3.1 Verified model architecture (the basis for all KV-cache arithmetic)

Fetched from `https://huggingface.co/Qwen/<model>/raw/main/config.json`, 2026-09-19. All [SOURCED]:

| Model | layers | hidden | Q heads | KV heads | head_dim | vocab |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 28 | 1024 | 16 | 8 | 128 | 151,936 |
| Qwen3-1.7B | 28 | 2048 | 16 | 8 | 128 | 151,936 |
| Qwen3-4B-Instruct-2507 | 36 | 2560 | 32 | 8 | 128 | 151,936 |
| Qwen3-8B | 36 | 4096 | 32 | 8 | 128 | 151,936 |

All four use grouped-query attention with **8 KV heads x 128 head_dim = 1024 KV dim**. This is why KV
cache is cheap for this family and why 4B and 8B have *identical* per-token KV cost.

**KV cache per token (bf16)** [ESTIMATED, arithmetic shown]:
`2 (K and V) x 2 bytes x num_layers x 1024`
- 0.6B / 1.7B (28 layers): `2 x 2 x 28 x 1024 = 114,688 bytes = 112 KiB/token`
- 4B / 8B (36 layers): `2 x 2 x 36 x 1024 = 147,456 bytes = 144 KiB/token`

**Model weights at bf16 (2 bytes/param)** [ESTIMATED]:
- 0.6B -> 1.2 GB, 1.7B -> 3.4 GB, 4B -> 8.0 GB, 8B -> 16.0 GB

### 3.2 Published memory anchors (not guesses)

**Unsloth GRPO memory breakdown**, Llama-3.1-8B, 20K context, 8 generations per prompt.
[SOURCED] https://docs.unsloth.ai/basics/reinforcement-learning-guide, fetched 2026-09-19:

| Component | Unsloth | Standard + Flash Attention 2 |
|---|---|---|
| Training memory cost | 42 GB | 414 GB |
| GRPO loss memory cost | 9.8 GB | 78.3 GB |
| Inference cost | 0 GB | 16 GB |
| Inference KV cache (20K ctx) | 2.5 GB | 2.5 GB |
| **Total** | **54.33 GB** | **510.8 GB** |

Their own arithmetic, quoted [SOURCED, same URL+date]:
- GRPO logits: "2 * 2 bytes * 8 (num generations) * 20K (context length) * 128256 (vocabulary size)
  = 78.3GB in VRAM"
- KV cache: "Llama 3.1 8B has 32 layers, and both K and V are 1024 in size. So memory usage for 20K
  context length = 2 * 2 bytes * 32 layers * 20K context length * 1024 = 2.5GB per batch... Otherwise
  you will need 20GB for the KV cache" (at vLLM batch size 8)

**Unsloth's stated rules of thumb** [SOURCED, same URL+date], verbatim:
- "For GRPO's **GPU VRAM requirements for QLoRA 4-bit**, the general rule is the model parameters =
  the amount of VRAM you will need... **LoRA 16-bit will use at minimum 4x more VRAM.**"
- "**Minimum requirement:** Just 5GB VRAM is enough to train your own reasoning model locally (for any
  model with 1.5B parameters or less)"
- "With 15GB VRAM, Unsloth allows you to transform any model up to 17B parameters"
- "Unsloth could originally finetune Llama 3.3 70B Instruct in 1x 48GB GPU... If we do not remove
  double memory usage, then we'll need >= 80GB of VRAM when loading Unsloth and vLLM together."

**CRITICAL CAVEAT on transferring Unsloth's numbers to this project.** Unsloth's savings assume vLLM
is **colocated in the trainer's own CUDA memory space** — that is explicitly where their 16 GB
"inference cost" saving comes from: *"Unsloth also uses the same GPU / CUDA memory space as the
underlying inference engine (vLLM), unlike implementations in other packages. This shaves 16GB of
memory."* [SOURCED, same URL+date].

The TRL grpo_harbor reference shape does the **opposite** — a separate vLLM server on separate GPUs.
In that topology the trainer GPU holds **no KV cache and no vLLM weights at all**, and the vLLM GPU
holds no optimizer state. The two sides must therefore be budgeted separately. That is how section 3.3
is laid out.

**TRL's memory levers** [SOURCED] https://huggingface.co/docs/trl/main/en/reducing_memory_usage, fetched 2026-09-19:
- "Gradient checkpointing is **enabled by default in all trainers**" — so activations are already reduced.
- `loss_type="chunked_nll"` is the **default in SFTTrainer**: "peak activation memory scales with
  `chunk_size x vocab_size` instead of `(batch x seq_len) x vocab_size`". Not compatible with
  `use_liger_kernel=True`, PEFT, or VLM.
- Liger Kernel: "increase multi-GPU training throughput by 20% and reduce memory usage by 60%".
- vLLM sleep mode offloads vLLM params + cache to CPU RAM during the optimization step.
- `activation_offloading=True` moves activations to CPU RAM during forward.

**prime-rl's memory levers** [SOURCED] https://raw.githubusercontent.com/PrimeIntellect-ai/prime-rl/main/docs/scaling.md, fetched 2026-09-19:
- `fused_lm_head_token_chunk_size` "defaults to `1024` for RL training" and avoids materializing the
  `[batch * seq, vocab]` logits tensor. Only available with `model.impl = "custom"`.
- `ac_offloading` on by default with `max_inflight_activations = 5`: "lowering the peak memory usage
  by **30-40%** in some cases, while only losing ~3-5% of throughput."
- `model.optim_cpu_offload = true` (state-only) is on by default. Full offload supports AdamW and
  SignSGD only, and disables gradient clipping.
- SignSGD is stateless: "8 instead of 16 bytes per parameter" of host RAM versus AdamW.

### 3.3 VRAM feasibility table

**Trainer process only** (separate vLLM server; gradient checkpointing on; chunked/fused LM head on;
seq_len 2048-4096; micro-batch 1).

[ESTIMATED] Arithmetic for bf16 full finetune with AdamW mixed precision:
`bytes/param = 2 (bf16 weight) + 2 (bf16 grad) + 4 (fp32 Adam m) + 4 (fp32 Adam v) = 12`,
plus an fp32 master weight copy `+4` = **16 bytes/param** in the standard mixed-precision setup.
- 0.6B: `0.6e9 x 16 = 9.6 GB`  (at 12 B/p: 7.2 GB)
- 1.7B: `1.7e9 x 16 = 27.2 GB` (at 12 B/p: 20.4 GB)
- 4B:   `4.0e9 x 16 = 64.0 GB` (at 12 B/p: 48.0 GB)
- 8B:   `8.0e9 x 16 = 128.0 GB` (at 12 B/p: 96.0 GB)

[ESTIMATED] Activations + GRPO logits overhead, added on top: with a fused/chunked LM head at
chunk 1024, the logits tensor is `1024 x 151,936 x 4 bytes (fp32) = 0.62 GB` per copy; GRPO holds
policy and reference logprobs, so ~1.5-2.5 GB. Activations with full activation checkpointing at
seq 2048-4096 and micro-batch 1 run ~1-4 GB for these model sizes. **Total overhead allowance: +4 to +8 GB.**

[ESTIMATED] LoRA bf16 (rank 32): frozen base at 2 bytes/param, adapters ~0.1-0.2% of params, optimizer
state only on adapters (negligible), same +4 to +8 GB overhead.

[ESTIMATED] QLoRA 4-bit: base at 0.5 bytes/param, same overhead.

| Model | bf16 full FT | LoRA bf16 (r32) | QLoRA 4-bit |
|---|---|---|---|
| Qwen3-0.6B | ~12-18 GB | ~5-6 GB | ~4-5 GB |
| Qwen3-1.7B | ~25-35 GB | ~8-10 GB | ~6-7 GB |
| Qwen3-4B | ~55-72 GB | ~14-18 GB | ~8-11 GB |
| Qwen3-8B | ~100-136 GB | ~23-28 GB | ~11-15 GB |

Cross-check: the QLoRA column matches Unsloth's "model parameters = the amount of VRAM you will need"
rule and their "5GB for <=1.5B params" floor. The LoRA column is roughly 2-3x the QLoRA column, against
Unsloth's stated "at minimum 4x" — my LoRA estimate may be slightly optimistic. Treat the LoRA column
as a floor, not a ceiling.

**vLLM process only** (weights + KV floor) [ESTIMATED from the verified per-token KV figures in 3.1]:

| Model | weights | KV @ 2048 ctx x 16 rollouts | KV @ 4096 x 32 | KV @ 8192 x 32 |
|---|---|---|---|---|
| Qwen3-0.6B | 1.2 GB | 3.5 GB | 14 GB | 28 GB |
| Qwen3-1.7B | 3.4 GB | 3.5 GB | 14 GB | 28 GB |
| Qwen3-4B | 8.0 GB | 4.5 GB | 18 GB | 36 GB |
| Qwen3-8B | 16.0 GB | 4.5 GB | 18 GB | 36 GB |

Worked example for the 4B @ 4096x32 cell: `4096 tokens x 32 concurrent = 131,072 tokens;
131,072 x 144 KiB = 18.0 GB`.

**Important operational caveat:** vLLM's `gpu_memory_utilization` defaults to ~0.9, so vLLM will
*claim* roughly 90% of whatever card you hand it regardless of these floors. These numbers tell you
what will **fit**, not what `nvidia-smi` will show.

### 3.4 The three answers the lane asked for: what fits on ONE card

Trainer and vLLM **colocated on a single card**:

| Configuration | 1x 80GB (H100) | 1x 48GB (L40S / A6000) | 1x 24GB (RTX 4090) |
|---|---|---|---|
| Qwen3-0.6B full FT + vLLM | YES, roomy | YES | YES, tight (~20 GB) |
| Qwen3-1.7B full FT + vLLM | YES (~53 GB) | short ctx only | NO |
| Qwen3-4B full FT + vLLM | **NO** — ~65 + ~13 = ~78 GB, will OOM on fragmentation | NO | NO |
| **Qwen3-4B LoRA + vLLM** | **YES — this is the shipped alphabet-sort example** | YES @ ctx <=2048 | NO |
| Qwen3-4B QLoRA + vLLM | YES | YES | NO — needs 2 cards |
| Qwen3-8B LoRA + vLLM | YES (~59 GB) @ moderate ctx | tight | NO |
| Qwen3-8B QLoRA + vLLM | YES | YES (~15 + ~20 = 35 GB) | NO |
| Qwen3-8B full FT | **NO** — needs ZeRO-2/FSDP across 2+ GPUs | NO | NO |

**Practical reading:**
- **80GB H100:** 4B LoRA is the sweet spot and is a shipped, documented config. 4B *full finetune* does
  not fit alongside vLLM — do not plan on it.
- **48GB (L40S at $1.09 RunPod / $0.80 Vast median):** the best value tier. 4B LoRA at ctx 2048 fits.
  This is the card to default to for tier (b).
- **24GB (4090 at $0.74 RunPod / $0.53 Vast median):** only viable for 0.6B and 1.7B, and realistically
  you want **two** of them (one trainer, one vLLM) — which is prime-rl's default topology anyway.
  4B does not fit on a single 24GB card in any configuration.

Confidence: **moderate**. The arithmetic is built on verified model configs and a sourced published
anchor, but none of it was measured on hardware in this lane. The 4B-LoRA-on-one-H100 row is the
exception — that one is **strong**, because it is a config prime-rl actually ships and documents.

---

## 4. Wall-clock to signal, AGENTIC multi-turn specifically

This is the strongest evidence in the lane, because prime-rl ships three graduated examples with
stated GPU counts and times, and two of the three are genuinely multi-turn.

All [SOURCED] from `https://raw.githubusercontent.com/PrimeIntellect-ai/prime-rl/main/README.md` and
the per-example `README.md` / `rl.toml`, fetched 2026-09-19.

### 4.1 The three shipped examples

| Example | Model | Turns | Committed config | Stated wall-clock |
|---|---|---|---|---|
| Reverse Text | Qwen3-0.6B | single-turn | 20 steps, 8x16 = 128 batch, seq 128 | "single consumer GPU in a **few minutes**" |
| **Alphabet Sort** | **Qwen3-4B-Instruct-2507** | **multi-turn (3-5)** | LoRA r32/a64, batch 256, group 16, seq 2048, 768 max completion tokens | **"single H100 GPU in just over an hour"** |
| Wordle | Qwen3-1.7B | multi-turn | batch 512, group 16, seq 8192, 1024 max completion tokens | "**2-4 H100 GPUs in a few hours**" |

Top-level README quotes, verbatim [SOURCED]:
- "**Reverse Text**: Train `Qwen3-0.6B` to reverse a small chunk of text... Can be trained on a single
  consumer GPU in a few minutes, and is ideal for getting started."
- "**Wordle**: Train `Qwen3-1.7B` to play Wordle. A fun example of multi-turn SFT and RL training. Can
  be trained on a 2-4 H100 GPUs in a few hours."
- "**Alphabet Sort**: Train `Qwen3-4B-Instruct-2507` to sort names alphabetically. Demonstrates
  multi-turn RL training via LoRA without SFT warmup. Can be trained on a single H100 GPU in just over
  an hour."

### 4.2 Alphabet Sort — the single most decision-relevant data point

This is a real multi-turn agentic RL run that produces a large, measured improvement in about an hour.

Committed `examples/basic/alphabet-sort/rl.toml` [SOURCED]:
```toml
max_steps = 200
seq_len = 2048
[model]              name = "Qwen/Qwen3-4B-Instruct-2507"
[trainer.model.lora] rank = 32
                     alpha = 64
[trainer.optim]      lr = 1e-5
[orchestrator]       batch_size = 256
                     group_size = 16
[orchestrator.train.sampling] max_completion_tokens = 768
[[orchestrator.train.source]] env.taskset.min_turns = 3
                              env.taskset.max_turns = 5
                              env.agent.harness.id = "null"
                              env.agent.runtime.type = "subprocess"
[inference]          # Default inference config
```

Measured outcome, quoted from the example README [SOURCED]:
- Baseline: "We got an **average reward of ~0.26** across 20x3 rollouts. The model achieves **0% perfect
  attempts**... and **0% perfect examples**."
- After RL: "Way better! Our model now gets an **average reward of ~0.81** with **73% perfect attempts**
  (44/60 rollouts score 1.0) and **65% perfect examples** (13/20 examples have all 3 rollouts at 1.0)."
- Qualitative: "the model now correctly sorts names and explicitly breaks down its reasoning
  step-by-step, even though chain-of-thought was never explicitly requested."

**Rollout volume** [ESTIMATED]: `batch_size = 256` with `group_size = 16`. Cross-checked against the
Wordle README's phrasing — "each generating training batches of 32x16 rollouts, for a total batch size
of 512" — which establishes that `batch_size` in these configs is **total rollouts**, not prompts. So
alphabet-sort is 16 unique prompts x 16 rollouts = **256 rollouts/step**, each a 3-5 turn conversation
at up to 768 completion tokens per turn.
- At the README's 100 steps: `256 x 100 = 25,600 multi-turn rollouts`
- At the config's 200 steps: `256 x 200 = 51,200 multi-turn rollouts`

**Steps per hour** [ESTIMATED]: dividing the stated "just over an hour" by the step count gives roughly
**100-200 steps/hr**. This is arithmetic on prose, not a measured throughput figure — see the caveats
immediately below, and Known Gaps #4.

### 4.3 TWO documented contradictions — budget against the pessimistic side

I verified both of these directly against the repo. They are real, not transcription errors on my part.

**Contradiction 1 — step count.** The alphabet-sort README says *"We train with LoRA (rank 32,
alpha 64) for **100 steps**"* and *"This will write a DCP checkpoint in
`outputs/rl/checkpoints/step_100`"*. The committed `rl.toml` says **`max_steps = 200`**.
The same pattern appears in Wordle: README says 100 steps, `rl.toml` says `max_steps = 200`.
**Budget for 200.**

**Contradiction 2 — GPU count.** The alphabet-sort README says *"This example runs on a single H100
GPU."* But the committed `rl.toml` contains **no `[deployment]` block at all** (I fetched the complete
43-line file to confirm), and `docs/scaling.md` states the default is *"1 trainer GPU and 1 inference
GPU"*. So running the shipped config as-is asks for **2 GPUs**, not 1, unless you override the
deployment. **Budget for 2.**

The same discrepancy, larger, in Wordle: README says "2-4 H100 GPUs", committed `rl.toml` says
`num_train_gpus = 2, num_infer_gpus = 6` — **8 GPUs**, with `data_parallel_size = 6` on the inference
side. [SOURCED]

### 4.4 Smoke-test floor is explicitly documented

> "Check that the full RL stack (inference + orchestrator + trainer) runs end-to-end
> (*this requires 2 GPUs*)"
> — [SOURCED] prime-rl README line 163, fetched 2026-09-19

The README's preceding steps confirm the ladder: SFT trainer alone = 1 GPU, RL trainer alone = 1 GPU,
inference server alone = 1 GPU, **full stack = 2 GPUs**. There is no 1-GPU path to validating the
whole loop.

### 4.5 Hardware prime-rl is actually tested on

> "We develop and test on NVIDIA RTX 3090/4090/5090, A100, H100, H200, and B200."
> — [SOURCED] prime-rl README line 68, fetched 2026-09-19

Consumer cards are explicitly supported and tested. This is what makes the cheap tier-(a) path credible
rather than wishful.

### 4.6 One setup cost that will surprise you

> "Optional: Install Flash Attention 3 (on Hopper GPUs only...)... **This step will take a while**, as
> it builds the Flash Attention 3 extension from source, as it has no wheels prebuilt."
> — [SOURCED] prime-rl README lines 116-118, fetched 2026-09-19

On a rented H100 you are paying for that build. This is a real component of the tier-(a) estimate and is
why I budget 4-8 hours for a smoke test that involves only minutes of actual training.

Confidence on section 4: **strong** for all configs, batch sizes, rollout counts and reward deltas
(these are committed files and documented results). **Moderate** for the absolute hour figures — they
are README prose, they contradict the repo's own configs, and I could not corroborate them against the
training logs (Known Gaps #4).

---

## 5. The three-tier dollar answer

Every assumption is stated. All hourly rates are from the section 2 table, fetched 2026-09-19. All
Vast figures use the **median**, never the floor (Note B). All arithmetic is shown.

### Tier (a) — Smoke test: prove the loop runs end to end

**Assumptions, stated:**
1. 2 GPUs. This is prime-rl's documented minimum for the full stack (section 4.4), not a guess.
2. Model is Qwen3-0.6B (reverse-text), then a short multi-turn run. 0.6B full-FT + vLLM fits 24 GB
   per section 3.4.
3. **4-8 hours wall-clock, dominated by setup rather than training.** The training itself is "a few
   minutes". The hours go to: container/image pull, `uv sync`, the from-source Flash Attention 3 build
   on Hopper (section 4.6), NCCL/port wiring between the two processes, and first-time debugging.
4. On-demand pricing. No spot, no interruption risk on a debugging session.
5. Excludes storage/egress (RunPod network volumes bill separately; immaterial at this scale).

**Arithmetic:**
- 2x RTX 4090, Vast median $0.53: `2 x 0.53 = $1.06/hr; x 4-8 hr = $4.24 - $8.48`
- 2x RTX 4090, RunPod $0.74: `2 x 0.74 = $1.48/hr; x 4-8 hr = $5.92 - $11.84`
- 2x RTX 5090, RunPod $0.99: `2 x 0.99 = $1.98/hr; x 4-8 hr = $7.92 - $15.84`
- 2x H100 SXM, RunPod $3.49: `2 x 3.49 = $6.98/hr; x 4-8 hr = $27.92 - $55.84`

### **ANSWER (a): $5 - $30.**

Use 2x 4090 or 2x 5090. There is no reason to pay H100 rates to prove that plumbing works, and prime-rl
explicitly tests on 3090/4090/5090. The H100 path ($28-$56) is listed only to show what you would waste.

---

### Tier (b) — First real experiment: measurable improvement on a small agentic benchmark

**Assumptions, stated:**
1. Reproduce and extend Alphabet-Sort-class work: Qwen3-4B, LoRA r32, genuine multi-turn (3-5 turns),
   256 rollouts/step. This is a real agentic benchmark with a published reward delta (0.26 -> 0.81),
   not a toy.
2. **2 GPUs**, per the shipped config's actual default — NOT the README's "single H100" claim
   (Contradiction 2, section 4.3).
3. **~2 hours per run**, per the config's `max_steps = 200` — NOT the README's 100 steps
   (Contradiction 1, section 4.3).
4. **5-10 runs total**: one baseline eval, 3-6 hyperparameter or reward-shaping attempts, 1-2 outright
   failures, plus final eval. This is what "an experiment" means as opposed to "one run".
5. Add idle and debugging time between runs. **Total: 20-30 GPU-node-hours.**
6. On-demand. Spot interruption mid-run wastes more than it saves at this scale.

**Arithmetic:**
- 2x L40S, RunPod $1.09: `2 x 1.09 = $2.18/hr; x 30 hr = $65.40`
- 2x L40S, Vast median $0.80: `2 x 0.80 = $1.60/hr; x 30 hr = $48.00`
- 2x A100 SXM 80GB, RunPod $1.59: `2 x 1.59 = $3.18/hr; x 25 hr = $79.50`
- 2x H100 SXM, Vast median $2.22: `2 x 2.22 = $4.44/hr; x 20 hr = $88.80`
- 2x H100 SXM, RunPod $3.49: `2 x 3.49 = $6.98/hr; x 20 hr = $139.60`
- 2x H100 SXM, Lambda $3.99: `2 x 3.99 = $7.98/hr; x 20 hr = $159.60`

### **ANSWER (b): $60 - $200. Midpoint ~$120.**

**This is the headline number for the whole lane.** A genuine multi-turn agentic RL experiment on
Qwen3-4B that produces a measurable improvement costs about as much as a mid-range dinner. The 48GB
L40S tier is the value pick — 4B LoRA at ctx 2048 fits (section 3.4) at roughly a third of H100 cost.

---

### Tier (c) — Serious run

**Assumptions, stated:**
1. A real agentic benchmark (SWE-style, tool-use, or a Harbor task suite), not a synthetic sorting task.
2. Qwen3-4B or Qwen3-8B, longer contexts (4096-8192), higher rollout concurrency.
3. Wordle-scale topology or larger: **8-GPU node, 2 training + 6 inference**, which is what Wordle's
   committed `rl.toml` actually specifies (section 4.3).
4. Multiple seeds and ablations. **100-300 node-hours** across the campaign.
5. On-demand. (Spot is defensible here if checkpointing is solid, and would cut these figures, but I
   have no sourced spot rate to quote for H100 — see Known Gaps #1.)

**Arithmetic:**
- 8x H100 SXM, Vast median $2.22: `8 x 2.22 = $17.76/hr; x 100 hr = $1,776; x 300 hr = $5,328`
- 8x H100 SXM, RunPod $3.49: `8 x 3.49 = $27.92/hr; x 100 hr = $2,792; x 300 hr = $8,376`
- 8x H100 SXM, Lambda $3.99: `8 x 3.99 = $31.92/hr; x 100 hr = $3,192; x 300 hr = $9,576`
- Lean alternative, stay 2x H100 RunPod for 200 hr: `$6.98/hr x 200 = $1,396`

### **ANSWER (c): $1,500 - $10,000.**

The spread is driven almost entirely by one decision: stay single-node 2-GPU and iterate slowly
(~$1,400), or take a full 8-GPU node and run ablations in parallel (~$3,000-$9,600). It is not driven
by provider choice.

---

### 5.1 The cost that is in none of the GPU tables: agentic sandboxes

Agentic rollouts execute untrusted model-generated actions, which needs a sandbox. The TRL harbor
example's docstring recommends E2B (`harbor[e2b]`, `--env e2b`) though its argparse default is
`--env docker`. [SOURCED, grpo_harbor.py, 2026-09-19]

**E2B pricing** [SOURCED] https://e2b.dev/pricing, fetched 2026-09-19:
- **Free / Hobby:** "$100 one-time usage credit", "Sessions up to 1 hour", "**20 concurrent sandboxes**",
  default sandbox CPU/RAM, no credit card required.
- **Pro:** "$150/month", "Sessions up to 24 hours", "100 concurrent sandboxes, expandable to 1,100",
  custom CPU/RAM. Billing is "per second of a running sandbox". Their own on-page calculator example
  shows `$166 usage + $150 plan = $316 total monthly`.
- **Enterprise:** "requires $3,000/mo minimum".

**Why this matters more than it looks.** At 256 rollouts/step (alphabet-sort's actual batch), a 20-
concurrent-sandbox cap means rollout generation serializes into ~13 waves per step. **The sandbox tier,
not the GPU, becomes the throughput bottleneck.** And the 1-hour Hobby session cap sits right at the
length of a single alphabet-sort run.

**Mitigation:** the `docker` backend is grpo_harbor's argparse default and "just needs a reachable
Docker daemon" [SOURCED, grpo_harbor.py]. Running Docker sandboxes locally on the GPU node you are
already renting costs **$0 extra** and has no concurrency cap beyond the node's own CPU/RAM. **Use
Docker, not E2B, unless there is a specific reason not to.** Budget $0 for sandboxes on that path.

Confidence: **strong** on the E2B figures and the Docker alternative; **moderate** on the
13-waves-per-step throughput implication (that is my arithmetic: `256 / 20 = 12.8`, and it assumes no
pipelining, which a good orchestrator may partly hide).

---

## 6. Free and cheap tiers

**Headline: none of them can run the reference two-process trainer + vLLM setup.** That is the finding,
and it is a structural blocker, not a quota problem.

### HF Spaces ZeroGPU — NOT USABLE for RL training
[SOURCED] https://huggingface.co/docs/hub/spaces-zerogpu, fetched 2026-09-19:
- Hardware: "dynamically allocates and releases **NVIDIA RTX Pro 6000 Blackwell** GPUs"
- Sizes: `large` (default) = "Half NVIDIA RTX Pro 6000 Blackwell", **48GB**, quota cost 1x;
  `xlarge` = "Full NVIDIA RTX Pro 6000 Blackwell", **96GB**, quota cost 2x
- Hosting: "Free personal accounts: accounts in good standing (verified email, account older than 30
  days) can host up to **2 ZeroGPU Spaces** for free." PRO hosts up to 10. PRO users get "x8 more daily
  usage quota".
- **The blocker:** "ZeroGPU Spaces are **exclusively compatible with the Gradio SDK**" and GPU is
  allocated per `@spaces.GPU`-decorated **function call**, not held for the life of a process.

A persistent vLLM server plus a separate long-running trainer process is **structurally impossible**
under that model. The 48/96GB VRAM is tantalizing and irrelevant. Confidence: **strong**.

### Google Colab — hostile to this workload on the free tier
[SOURCED] https://research.google.com/colaboratory/faq.html, fetched 2026-09-19:
- "Colab resources are **not guaranteed and not unlimited**, and usage limits sometimes fluctuate."
- Explicitly disallowed on free managed runtimes: "**connecting to remote proxies**"; and workloads
  where users "bypass the notebook UI and using a web UI on a Colab managed runtime" are "disallowed...
  and **may be terminated at any time without warning**."
- "Virtual machines are deleted when idle for a while, and have a **maximum lifetime enforced by the
  Colab service**."
- Escape hatch offered: paid plans, GCP Marketplace, Colab Enterprise, or a local runtime.

Single GPU per runtime, and the terms are pointed at exactly the "run a server process in a notebook"
pattern this project needs. Confidence: **strong** on the restrictions. The FAQ's "Resource Limits"
section did not render specific GPU types or hour caps in the text extraction, so I have **no sourced
figure** for Colab GPU hours or GPU model.

### Kaggle — the only free tier with TWO GPUs, but I could not verify anything about it
Kaggle is structurally the most interesting free option, because a T4x2 session would nominally match
prime-rl's 1-trainer + 1-inference split on two physically separate devices.

**I could not verify a single Kaggle number.**
- `kaggle.com/docs/efficient-gpu-usage` and `kaggle.com/docs/notebooks` both return **HTTP 403** through
  the text proxy.
- WebFetch on the same URL returned the model's own recollection rather than page content, and said so
  explicitly: *"Only the page title came through... not the body text. So I can't quote exact figures
  from that page."*

Commonly cited figures — 30 GPU-hours/week, 12-hour session cap, T4x2 / L4x4 / P100 options, 20-hour
TPU quota — are **[UNVERIFIED]**. Do not put them in a report as fact. **To resolve: open a Kaggle
notebook and run `nvidia-smi` and `torch.cuda.device_count()`; the remaining quota is shown in the
notebook sidebar and is not exposed via any API.**

Even if verified, the likely blockers are 16GB per T4 (which per section 3.4 caps you at 0.6B/1.7B) and
a session cap shorter than a serious run.

### Research credit programs — NOT INVESTIGATED
WebSearch being unavailable made program discovery impractical. Vast.ai has a "Startup Program" and
Lambda has a "Startups and Researchers" page (both linked from their navs, both [SOURCED] as existing,
neither fetched for terms). This is an open gap, and given tier (b) costs ~$120, chasing credits may
not be worth the effort.

---

## 7. Sources consulted

Every URL fetched in this lane, with date and what it yielded.

### Pricing
| URL | Date | Result |
|---|---|---|
| https://www.runpod.io/pricing | 2026-09-19 | Full on-demand GPU table + Serverless. Page self-dated "Updated September 13, 2026". Community/Secure toggle is JS — only one tier captured. |
| https://lambda.ai/pricing | 2026-09-19 | On-demand instances (1x/2x/4x/8x) + 1-Click Cluster rates. Page `Published Time: Thu, 17 Sep 2026`. |
| https://vast.ai/pricing | 2026-09-19 | Marketplace "from" and "median" for ~50 GPUs. Page `Published Time: Tue, 15 Sep 2026`. |
| https://www.primeintellect.ai/pricing | 2026-09-19 | **HTTP 404 — page does not exist.** |
| https://api.primeintellect.ai/api/v1/availability/ | 2026-09-19 | **HTTP 403** — requires `Authorization: Bearer` key. |
| https://api.primeintellect.ai/api/v1/availability/gpu-types | 2026-09-19 | **HTTP 404.** |
| https://docs.primeintellect.ai/api-reference/check-gpu-availability | 2026-09-19 | Documents `/api/v1/availability/gpus` and `/disks`, query params (regions, gpu_count, gpu_type e.g. `H100_80GB`, socket, security, page_size max 100). Confirms auth requirement. No prices. |
| https://www.primeintellect.ai/ | 2026-09-19 | Homepage GPU widget. **Placeholder data — see Known Gaps #1.** |
| https://docs.primeintellect.ai/introduction | 2026-09-19 | Product map only (Lab, Hosted Training, Environments Hub, Sandboxes, On-Demand Cloud, Multi-Node Clusters). No prices. |
| https://hyperbolic.xyz/pricing | 2026-09-19 | **JS-only.** Extraction returned cookie-consent text exclusively. |
| https://www.hyperbolic.ai/pricing | 2026-09-19 | No price content extractable. |
| https://docs.hyperbolic.ai/docs/hyperbolic-pricing | 2026-09-19 | No price content. |
| https://app.hyperbolic.ai/compute | 2026-09-19 | One marketing line only: "Spin up H100/H200 GPU clusters at unbeatable pay-as-you-go pricing." No numbers. |
| https://hyperbolic.ai/gpus | 2026-09-19 | No price content. |
| https://e2b.dev/pricing | 2026-09-19 | Hobby / Pro / Enterprise tiers, concurrency caps, session caps, per-second billing model. |

### Framework docs and source
| URL | Date | Result |
|---|---|---|
| https://raw.githubusercontent.com/PrimeIntellect-ai/prime-rl/main/README.md | 2026-09-19 | NVIDIA-GPU requirement; tested-hardware list; 2-GPU full-stack smoke test; the three examples with GPU counts and wall-clock; Flash Attention 3 build warning. |
| .../prime-rl/main/examples/basic/reverse-text/README.md | 2026-09-19 | 2-GPU design; 20 RL steps at 8x16 rollouts, batch 128, seq 128; baseline reward ~0.05. |
| .../prime-rl/main/examples/basic/wordle/README.md | 2026-09-19 | Multi-turn; 100 steps (prose), 32x16 rollouts, batch 512, ctx 4096 (prose); reward ~0.2 -> ~1.5, win rate 0% -> ~60%. |
| .../prime-rl/main/examples/basic/wordle/rl.toml | 2026-09-19 | `max_steps=200`, `num_train_gpus=2`, `num_infer_gpus=6`, `batch_size=512`, `group_size=16`, `seq_len=8192`, `max_completion_tokens=1024`, `data_parallel_size=6`. |
| .../prime-rl/main/examples/basic/alphabet-sort/README.md | 2026-09-19 | "single H100 GPU"; 100 steps (prose); reward 0.26 -> 0.81; 73% perfect attempts; 65% perfect examples. |
| .../prime-rl/main/examples/basic/alphabet-sort/rl.toml | 2026-09-19 | Complete 43-line file. `max_steps=200`, `seq_len=2048`, LoRA r32/a64, lr 1e-5, `batch_size=256`, `group_size=16`, `max_completion_tokens=768`, `min_turns=3`, `max_turns=5`. **No `[deployment]` block.** |
| .../prime-rl/main/examples/basic/alphabet-sort/eval.toml | 2026-09-19 | 20 examples, group_size 3, 768 max completion tokens. |
| .../prime-rl/main/docs/scaling.md | 2026-09-19 | Default 1 trainer + 1 inference GPU; FSDP/EP/CP; `fused_lm_head_token_chunk_size=1024` default; `ac_offloading` 30-40% peak memory saving at 3-5% throughput cost; optimizer CPU offload defaults; SignSGD; benchmarking via `metrics.jsonl` (`perf/throughput`, `perf/mfu`, `time/step`, `perf/peak_memory`). |
| https://raw.githubusercontent.com/huggingface/trl/main/examples/grpo_harbor/grpo_harbor.py | 2026-09-19 | The 2+2 GPU reference shape; NCCL weight transfer; `--env docker` argparse default with e2b recommended; default model Qwen/Qwen3-4B; default agent `bash`. |
| https://huggingface.co/docs/trl/main/en/vllm_integration | 2026-09-19 | Separate-CUDA-device requirement; colocate (default) vs server mode; `--weight-transfer-config` nccl vs ipc; note that vLLM offline data-parallel scaling for non-MoE models was removed in vLLM 0.14.0 (PR #30739). |
| https://huggingface.co/docs/trl/main/en/reducing_memory_usage | 2026-09-19 | Gradient checkpointing on by default; `chunked_nll` default in SFTTrainer; Liger (+20% throughput, -60% memory); vLLM sleep mode; activation offloading; PEFT. |
| https://huggingface.co/docs/trl/main/en/speeding_up_training | 2026-09-19 | vLLM server startup; attention backends; bf16 vs fp16 guidance. |
| https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/README.md | 2026-09-19 | Confirms verifiers <-> prime-rl <-> Environments Hub integration. **No GPU, memory, or timing data.** |
| https://docs.unsloth.ai/basics/reinforcement-learning-guide | 2026-09-19 | The full GRPO memory table (54.33 vs 510.8 GB); QLoRA "params = GB" rule; "4x more" for LoRA 16-bit; 5GB floor for <=1.5B; KV-cache and logits arithmetic; colocated-vLLM caveat. |
| https://docs.unsloth.ai/get-started/beginner-start-here/unsloth-requirements | 2026-09-19 | VRAM value pairs for QLoRA vs LoRA. **Row labels did not render — see Known Gaps #5.** |
| https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json | 2026-09-19 | 28 layers, hidden 1024, 16 Q / 8 KV heads, head_dim 128, vocab 151936. |
| https://huggingface.co/Qwen/Qwen3-1.7B/raw/main/config.json | 2026-09-19 | 28 layers, hidden 2048, 16 Q / 8 KV heads, head_dim 128, vocab 151936. |
| https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/main/config.json | 2026-09-19 | 36 layers, hidden 2560, 32 Q / 8 KV heads, head_dim 128, vocab 151936, max_position 262144. |
| https://huggingface.co/Qwen/Qwen3-8B/raw/main/config.json | 2026-09-19 | 36 layers, hidden 4096, 32 Q / 8 KV heads, head_dim 128, vocab 151936. |

### Free tiers
| URL | Date | Result |
|---|---|---|
| https://huggingface.co/docs/hub/spaces-zerogpu | 2026-09-19 | RTX Pro 6000 Blackwell; large 48GB / xlarge 96GB; 2 free Spaces; Gradio-SDK-only; per-function allocation. |
| https://research.google.com/colaboratory/faq.html | 2026-09-19 | Restrictions and termination policy. "Resource Limits" section did not render specifics. |
| https://www.kaggle.com/docs/efficient-gpu-usage | 2026-09-19 | **HTTP 403** via text proxy; WebFetch returned model knowledge not page content. |
| https://www.kaggle.com/docs/notebooks | 2026-09-19 | **HTTP 403.** |
| https://www.kaggle.com/discussions/product-feedback/583279 | 2026-09-19 | No usable content. |

### Literature and logs (all failed)
| URL | Date | Result |
|---|---|---|
| api.semanticscholar.org/graph/v1/paper/search (2 queries) | 2026-09-19 | **HTTP 429 Too Many Requests.** Needs an API key. |
| export.arxiv.org/api/query — `"agentic reinforcement learning" AND "GPU hours"` | 2026-09-19 | Zero matching results. |
| https://api.wandb.ai/api/v1/runs/primeintellect/alphabet-sort-4b-lora | 2026-09-19 | **404.** |
| https://api.wandb.ai/graphql — projects `alphabet-sort-4b-lora`, `examples`, `wordle`, `alphabet-sort` under entity `primeintellect` | 2026-09-19 | Endpoint reachable unauthenticated (it returned a valid GraphQL field error for a bad field name, then valid responses), but **all four projects return `{"data":{"project":null}}`** — not anonymously queryable. |

---

## 8. Confidence summary

| Finding | Confidence |
|---|---|
| RunPod / Lambda / Vast.ai per-hour rates | **Strong** — fetched from live pricing pages, all self-dated within 6 days |
| Which RunPod tier (Community vs Secure) was captured | **Moderate** — $3.49 H100 SXM is consistent with Secure; toggle unreadable |
| Vast median as the correct planning number | **Strong** — floor vs median gap is documented on the page itself |
| Prime Intellect pricing | **Unknown** — see Gap #1. Homepage widget actively misleading. |
| Hyperbolic pricing | **Unknown** — see Gap #2 |
| Qwen3 architecture / KV-cache per-token math | **Strong** — from official `config.json` files |
| Unsloth GRPO memory anchors (54.33 / 510.8 GB) | **Strong** — published table, quoted verbatim |
| My bf16/LoRA/QLoRA trainer VRAM estimates | **Moderate** — standard arithmetic, not measured; LoRA column may be optimistic vs Unsloth's "4x" rule |
| "4B LoRA fits one 80GB H100" | **Strong** — it is a shipped, documented prime-rl config |
| "4B full FT does NOT fit one 80GB alongside vLLM" | **Moderate** — arithmetic (~78 GB of 80), no measurement |
| prime-rl example configs, batch sizes, rollout counts, reward deltas | **Strong** — committed files and documented results |
| The two README-vs-config contradictions | **Strong** — verified directly against both files |
| Absolute wall-clock hours ("~1 hour", "a few hours") | **Moderate** — README prose, contradicted by the repo's own configs, uncorroborated by logs |
| Steps/hour (~100-200) | **Speculative** — arithmetic on prose, not a measured throughput number |
| Tier (a) $5-$30 | **Strong** — 2-GPU minimum is documented; only the setup-hours assumption is mine |
| Tier (b) $60-$200 | **Moderate** — rates are solid; the 5-10 runs and 20-30 node-hours are reasoned assumptions, not sourced |
| Tier (c) $1,500-$10,000 | **Speculative** — rates solid, but 100-300 node-hours is a planning assumption with no external anchor |
| E2B pricing and concurrency caps | **Strong** — from the pricing page |
| Docker backend is free and is the argparse default | **Strong** — from the grpo_harbor source |
| ZeroGPU unusable for RL training | **Strong** — Gradio-only + per-function allocation are both documented |
| Colab restrictions | **Strong** on the policy text; **no sourced figures** for GPU type or hours |
| Kaggle anything | **Unverified** — 403s throughout; do not cite |

---

## 9. Known gaps

**1. Prime Intellect pricing is unresolved — and it is the provider prime-rl itself recommends.**
This is the most important gap in the lane. prime-rl's README points users at
`app.primeintellect.ai` for "renting on-demand single GPUs for developing, debugging and small
ablations" [SOURCED, README line 72].
- `/pricing` returns **404**.
- The availability API returns **403** without a Bearer key.
- **The homepage GPU widget is placeholder marketing, not data.** Evidence it must not be trusted:
  `$3.14/HR` (= pi) repeats identically across H200, GH200, RTX Pro 6000, A100 **and** A40 — five
  cards with wildly different real market prices. The same widget labels **H200 as "80 GB VRAM"**
  when H200 is 141 GB. Every card shows the same "Available x2 . x1".
- The only entries that do not look like placeholders were **H100 $2.43/HR on-demand with
  "Spot 0.94/HR"**, B200 $3.49, B300 $4.99. **I did not use these anywhere in this report.** If the
  H100 spot figure is real it would be materially cheaper than anything in section 2 and would change
  tier (c).
- **To resolve:** log in at `app.primeintellect.ai/dashboard/on-demand-gpus`, or generate an API key
  and call `GET /api/v1/availability/gpus?gpu_type=H100_80GB&gpu_count=1`.

**2. Hyperbolic is unreachable.** Pricing is client-rendered on all four URLs tried
(`hyperbolic.xyz/pricing`, `hyperbolic.ai/pricing`, `/gpus`, `docs.hyperbolic.ai`). They advertise
H100/H200 pay-as-you-go but publish no number a text fetch can read. **To resolve:** load in a real
browser, or find their API.

**3. RunPod Community Cloud rates were not captured.** The toggle is JavaScript. Community is
typically cheaper than Secure. All RunPod figures here should be treated as an upper bound.

**4. No measured wall-clock anywhere in this report.** All three prime-rl W&B projects
(`primeintellect/examples`, `/wordle`, `/alphabet-sort-4b-lora`) return `null` to anonymous GraphQL,
even though the endpoint itself is reachable without auth. The README W&B links are shared-view URLs
that need the browser UI. **Consequence: the hour figures are repo prose that contradicts the repo's
own committed configs on both step count and GPU count.** **To resolve:** open the W&B workspace links
in a browser and read `_runtime` / step timing, or just run the alphabet-sort config yourself for 10
steps and extrapolate from `time/step` in `monitors/file/metrics.jsonl` — `docs/scaling.md` documents
exactly this workflow and points at `benchmarks/scripts/run_single_benchmark.py`. **That single 10-step
run would cost under $1 and would replace the weakest number in this entire lane.**

**5. The Unsloth requirements table row labels did not render.** I captured the QLoRA/LoRA VRAM value
pairs (3.5/8, 5/19, 6/22, 6.5/24, 7.5/29, 8.5/33, 22/64, 26/76, 30/96, 41/164, 48/192, 53/212,
237/950) but **not which model size each row belongs to**. I therefore used only Unsloth's explicitly
quoted rules, never the table, and no number in section 3 depends on guessing that mapping.

**6. Kaggle is entirely unverified** (403 through the text proxy; WebFetch returned model knowledge and
flagged that it had). Since Kaggle's T4x2 is the only free option that structurally matches the
2-process topology, this is worth 5 minutes in a browser if free compute matters.

**7. No independent, third-party agentic-RL cost measurement.** Semantic Scholar rate-limited (429) and
the arXiv query returned nothing. **Every wall-clock number in section 4 traces to prime-rl's own
repository — a single source, and an interested one** (Prime Intellect sells the GPUs it recommends for
running its framework). Treat the timings as vendor-published benchmarks.

**8. Research credit programs not investigated.** Vast.ai "Startup Program" and Lambda "Startups and
Researchers" pages exist but were not fetched for terms. Low priority given tier (b) is ~$120.

**9. Multi-turn rollout throughput is unmeasured.** I have rollouts/step (sourced) and total hours
(prose), but no tokens/sec or seconds/rollout for agentic multi-turn generation. Agentic rollouts are
much slower than single-turn math because each turn is a separate generation round-trip plus
environment execution, and none of the sources quantified that penalty. The tier (b) and (c) hour
assumptions absorb this uncertainty but do not eliminate it.
