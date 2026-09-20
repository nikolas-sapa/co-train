# 03 — Free compute path
Date: 2026-09-20 (rev 2) · Supersedes `lanes/compute.md` §6 ("none of them can run the
reference setup", Kaggle unverified behind 403s).

> **rev 2 correction.** Rev 1 of this document concluded that Kaggle's free GPU is a Tesla
> P100, that P100 cannot run vLLM, and that the free path therefore hinged on an unverified
> T4x2 option. **That was wrong, because Kaggle's web docs are stale.** Kaggle's own official
> CLI source proves P100 is retired and T4 is the default. The free path is confirmed live and
> needs no manual check. Details below.

## Answer

**Free works, and it is verified.** Two corrections to the earlier analysis:
1. The 2-GPU requirement is a **prime-rl** constraint, not a law. TRL runs the whole loop on one GPU.
2. Kaggle's default free GPU is a **T4 x2**, not the P100 its web docs still name.

Remaining real constraint: **T4 has no bf16**, so fp16 with its stability tax, and ~16GB/card.

---

## 1. Kaggle's actual free hardware [SOURCED — Kaggle's own CLI]

The web docs at `kaggle.com/docs/notebooks` say, verbatim: *"You can add a single NVIDIA Tesla
P100 to your Notebook for free."* **This is stale.** From `Kaggle/kaggle-cli`,
`src/kaggle/api/kaggle_api_extended.py:486-491`:

```python
_RETIRED_ACCELERATORS = {
    "nvidiateslap100": "Sessions run on the default GPU (NvidiaTeslaT4) instead.",
    "tpuv38":          "Sessions run on the default TPU (TpuV5E8) instead.",
    "tpu1vmv38":       "Sessions run on the default TPU (TpuV5E8) instead.",
    "tpuv232":         "Sessions run on CPU instead, with no accelerator at all.",
    "tpuv2256":        "Sessions run on CPU instead, with no accelerator at all.",
}
```

And `src/kaggle/cli.py:3039-3041`, verbatim:
> *"Specify the type of accelerator to use for the kernel run (e.g. **'NvidiaTeslaT4' for GPU
> T4 x2** or 'TpuV5E8' for TPU v5e-8). Retired accelerators such as 'NvidiaTeslaP100' are
> accepted but warn, since the session runs on a replacement instead."*

| Accelerator | Status | Capability | vLLM (needs >=7.5) | bf16 (needs >=8.0) |
|---|---|---|---|---|
| `NvidiaTeslaP100` | **RETIRED** -> auto-substituted with T4 | 6.0 | no | no |
| **`NvidiaTeslaT4`** | **DEFAULT GPU, x2** | **7.5** | **YES** | **no** |
| `NvidiaTeslaA100` | Accepted, not retired | 8.0 | yes | yes |
| `TpuV5E8` | Default TPU (v3-8 retired) | n/a | n/a | n/a |

**On the A100:** the string appears only in the CLI's "not retired" test list. It is absent from
the CLI source and from every docs page fetched. **No evidence it is available on the free tier.**
Do not plan around it. [UNVERIFIED]

### Quota and limits [SOURCED] kaggle.com/docs/efficient-gpu-usage, fetched 2026-09-20
- *"quota limit per week of GPU... resets weekly and is **30 hours** or sometimes higher"*
- *"Interactive sessions remain active until they reach the **60 minute idle timeout**"*
- *"Free GPU availability is limited: in busy times, you might be placed in a **queue**."*
- **20 GB** persisted to `/kaggle/working`

---

## 2. The unlock: TRL runs the whole loop on ONE GPU [SOURCED]

`trl/trainer/grpo_config.py:121-128`, verbatim:
> `vllm_mode` (`str`, *optional*, defaults to **`"colocate"`**) ...
> `"colocate"`: vLLM will run in the **same process and share the training GPUs**. This avoids
> the need for a separate server but may cause resource contention with training.

Plus `vllm_enable_sleep_mode` (`:133-135`): *"offload weights/cache during the optimizer step.
Keeps GPU memory usage low."* Default `vllm_gpu_memory_utilization = 0.3` (`:157`), so on a 16GB
T4 vLLM takes ~5GB and training gets ~11GB.

prime-rl's README states the full stack *"requires 2 GPUs"* with no 1-GPU path. Kaggle gives two
T4s anyway, so either works — but TRL's colocate mode means a single card is enough, which also
keeps Colab viable as a backup.

**This independently confirms lane-grpo's "start on TRL, skip Harbor" recommendation, for a
reason that lane never considered: TRL is the only one of the two that runs free.**

---

## 3. The one real constraint: no bf16

vLLM source `vllm/platforms/cuda.py:256-259`:
```python
if self.has_device_capability(80):
    return [torch.bfloat16, torch.float16, torch.float32]
if self.has_device_capability(60):
    # fp16 / fp32 only
```
T4 is 7.5 -> **fp16 only**. Qwen3 checkpoints are bf16-native; they load and run in fp16, but
GRPO in fp16 needs loss scaling and is less numerically stable. **This is the main technical risk
of the free path.** No sourced evidence found on fp16 GRPO stability at small scale, either
direction. [UNVERIFIED]

---

## 4. Recommended free configuration

| Setting | Value | Why |
|---|---|---|
| Platform | **Kaggle, accelerator `NvidiaTeslaT4` (= T4 x2)** | default free GPU, capability 7.5 |
| Stack | **TRL**, not prime-rl | colocate = 1 GPU; prime-rl needs 2 |
| `vllm_mode` | `"colocate"` (default) | no separate server process |
| `vllm_enable_sleep_mode` | `True` | frees VRAM during optimizer step |
| dtype | **fp16** | T4 has no bf16 |
| Model | **Qwen3-0.6B**, then 1.7B | fits ~11GB training budget with LoRA |
| Tuning | LoRA | full finetune will not fit |
| `mask_truncated_completions` | `True` | required for agentic rollouts (`grpo_config.py:831`) |
| Checkpoints | `/kaggle/working`, every N steps | 20GB persisted; idle timeout kills runs |

---

## 5. What it actually costs in time

[ESTIMATED — arithmetic on peak throughput, not a benchmark]
T4 fp16 ~65 TFLOPS; H100 bf16 ~990 TFLOPS. Ratio ~**15x**, before the T4's much lower memory
bandwidth and the fp16 tax. Real-world on memory-bound rollout generation is likely worse.

prime-rl's `alphabet-sort` (Qwen3-**4B**, reward 0.26 -> 0.81) takes ~1h on H100-class hardware.
- Same 4B on a T4: ~15h. **Exceeds the session cap and half the weekly quota.** Impractical.
- At **0.6B** (~6.7x fewer params): plausibly **2-4h**. One session, ~10% of weekly quota.

**So "it only costs time" is almost right — it costs time AND model size.** The free path caps
you at roughly 0.6B-1.7B. That is fine for the question this project asks, because the comparison
is co-trained vs untrained **at the same size**, not against frontier models.

---

## 6. Other free options

| Option | Verdict |
|---|---|
| **Colab free** | Single T4, capability 7.5, so colocate would work. But the FAQ disallows *"connecting to remote proxies"* and bypassing the notebook UI, with termination *"at any time without warning"*. Fine for a smoke test, not a run you care about. |
| **HF Spaces ZeroGPU** | Structurally impossible. Gradio-SDK-only; GPU allocated per decorated *function call*, not held for a process lifetime. The 48/96GB is irrelevant. |
| **Kaggle TPU v5e-8** | Free and current (v3-8 retired). But vLLM/TRL GRPO on TPU is a much rougher path. Not recommended. |
| Vast.ai Startup, Lambda Researchers | [UNVERIFIED] pages exist, terms never fetched. Tier (b) is ~$120; chasing credits may cost more time than it saves. |

---

## 7. Revised plan sequence

0. **Template gate (free, CPU-only):** verify the base model's chat template is prefix-preserving,
   else TRL raises at `grpo_trainer.py:1981-1982`. Do this before anything else.
1. Kaggle smoke test: TRL + `vllm_mode="colocate"` + fp16 + Qwen3-0.6B, tiny env, 5 steps.
   Confirms the loop and, critically, whether fp16 GRPO is stable.
2. Reproduce an alphabet-sort-shaped result at 0.6B. Checkpoint to `/kaggle/working` every N steps.
3. Build the real environment; reward from state the agent cannot write (Factorio RCON lesson).
4. Rent GPUs only if fp16 instability or the session cap actually bites. The ~$120 tier is the
   fallback, not the plan.

## Method note
The P100 error in rev 1 came from trusting Kaggle's web documentation. The correction came from
Kaggle's own client source. **Vendor docs went stale; the vendor's code did not.** Worth
generalizing: for any "what hardware/version does X actually support" question, check the tool's
source or its test suite before its docs.
