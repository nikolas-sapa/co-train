# Step 2 result — fp16 GRPO is stable on T4

Run date **2026-09-30**. Verdict **STEP 2 PASS**. This closes the question that
gated Steps 3-6: *does the loop run, and is fp16 stable on free hardware.*

Re-check the claim with no GPU:

```bash
python step2/verdict.py step2/results/step2_metrics.jsonl
```

## The numbers

| Step | `loss` | `grad_norm` | `reward_std` | `kl` | mean len |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.0134 | 1.837 | 0.0707 | 1.34e-05 | 26.4 |
| 2 | 0.1957 | 2.433 | 0.2248 | 2.16e-05 | 27.9 |
| 3 | −0.1506 | 2.011 | 0.1581 | 2.61e-03 | 21.6 |
| 4 | −0.0503 | 2.063 | 0.0354 | 1.33e-03 | 19.3 |
| 5 | 0.0687 | 1.716 | 0.1132 | 2.49e-02 | 24.1 |

`train_runtime` 298 s. No OOM. `completions/clipped_ratio` 0.0 throughout, so
`max_completion_length=128` never bound and `mask_truncated_completions` never
had to fire.

## What passed, and what that rules out

**`grad_norm` finite and > 0 on every step**, range 1.7–2.4, no drift. fp16 did
not overflow and did not underflow to zero. Notably there was **no GradScaler
warm-up `inf` on step 0** either — cleaner than the code allows for. The
one-step exemption in `verdict.py` went unused, so it remains untested against a
real overflow.

**`reward_std` > 0 on every step**, so a real within-group gradient existed at
every step. The run is not a vacuous pass: a degenerate reward would have
completed just as cleanly while exercising nothing.

**`kl` non-flat**, 1.3e-05 → 2.5e-02, rising across three orders of magnitude.
This is the artifact worth keeping. `research/08-gap-closure.md` §7 found a
public Kaggle 2×T4 run at nearly this config that did 314 steps clean — but at
`beta=0`, where Unsloth's unconditional `kl` logging emits a literal constant
`0.0`. Setting `beta=0.04` is what turned that dead channel into a measurement,
and `observations()` checks flatness rather than finiteness precisely so a
constant could not be mistaken for a curve.

## What this does NOT show

- **Not a learning run.** The reward is output length. Five steps at 0.6B teach
  nothing about capability, and no checkpoint from this is worth keeping.
- **Reward hacking is visible and expected.** By step 4 the completions collapse
  onto one template — *"A mountain path winds through {dense foliage | misty
  peaks | lush valleys}, offering breathtaking views and a sense of adventure"* —
  scoring 0.75–0.85 on all eight samples. The reward *is* length, so a template
  of the right length is an optimal policy. This confirms the probe worked; it
  says nothing good about the task.
- **Entropy was not observable.** Unsloth hardcodes `compute_entropy = False`,
  so Garg's clearest collapse signature is unavailable on this stack. Declared
  by `observations()` on every run rather than left silent.
- **Single-GPU.** Unsloth forces `_n_gpu = 1`; both T4s were visible, one was
  used. `NCCL_CUMEM_ENABLE` was inert.
- **Five steps is not a trend.** No slope can be fit. Stability here means "did
  not explode in five steps", not "is stable at 300".

## Provenance, stated because it is weaker than it should be

`step2_metrics.jsonl` in this directory is **reconstructed from notebook
stdout**, not the file `smoke.py` wrote. Kaggle reset the session immediately
after the run and wiped `/kaggle/working` before the file could be downloaded.

Every per-step value is transcribed verbatim from the printed log dicts, and
`verdict.py` run against the reconstruction reproduces the same verdict and the
same single observation that Kaggle printed. The `config` block, however, is
read from `smoke.py` at commit `52aacf0` rather than from the run's own header,
which was lost with the file.

A first-party file would be better evidence. It costs one more Kaggle session
(~20 min, mostly install) and is worth doing if this result is ever published.
`KAGGLE.md` now says to download immediately.

## Stack, for reproduction

```
Tesla T4  sm_75  x2 visible, 1 used
torch 2.10.0+cu128  CUDA 12.8  Triton 3.6.0  Xformers 0.0.35
transformers 4.57.6   trl 0.24.0   unsloth 2026.9.12   unsloth_zoo 2026.9.8
bfloat16 = FALSE      FA2 = False
Qwen3-0.6B, LoRA r=32, 20,185,088 / 616,235,008 trainable (3.28%)
beta 0.04, lr 3e-5, num_generations 8, num_iterations 1, use_vllm False
```

Two environment notes that cost real time, both now in `KAGGLE.md`:

- `cut_cross_entropy` / `torchao` want torch ≥ 2.11 and the image ships 2.10, so
  the fused cpp extensions are skipped with a warning. Benign — it falls back to
  unfused kernels.
- Kaggle's "Restart session" discards the pip install *and* wiped
  `/kaggle/working`. Install and run in one session, with `!` subprocesses.

## Consequence for the build sequence

Step 3 is now unblocked, and the hardware fork resolved toward the cheap side:
**the T4 path works, so rented Ampere is not required to proceed.** `08` had
already established that prime-rl cannot train on a T4 at all — no float16 in
`DTYPE_MAP`, FSDP hardcoded to bfloat16 — so Unsloth-on-T4 and prime-rl were
disjoint paths, and this result keeps the free one open.
