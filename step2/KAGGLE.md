# Kaggle runbook — Step 2

Paste-ready. Read `README.md` for *why*; this is only *how*.

**Before you start:** Settings → Accelerator → **GPU T4 x2**, and Internet →
**On** (needed for pip and the Qwen3 download). Session budget is 30 GPU-h/week
and 12 h/session, and the kernel dies after 20-30 min idle — so the preflight
cell exists to fail in seconds rather than after the model download.

---

## The accelerator is a parameter, and today the code refuses to treat it as one

This runbook names Kaggle T4 x2 because that is what the 2026-09-30 run used,
but only three things here are actually T4-specific. Listed so a move to other
free hardware (another host, or a Colab tier) changes the right lines and not
the whole file.

| Choice | Why it is T4 | On sm_80+ (A100 / L4 / newer) |
|---|---|---|
| `fp16=True`, `bf16=False` | T4 is sm_75; bf16 needs 8.0 | **flips to bf16** |
| `dtype=torch.float16` at load | same | `torch.bfloat16` |
| Unsloth rather than raw TRL | Unsloth's fp16-on-Turing work is the reason the stack was chosen | optional — raw TRL is viable, which also lifts the `trl<=0.24` problem |

**`smoke.py:129` hard-refuses anything newer:**

```python
assert cap[0] < 8, f"expected a pre-Ampere GPU for the fp16 question, got sm_{...}"
```

That assert is *correct for Step 2* — the question was "is **fp16** stable on
free hardware", and a silent fall-through to bf16 would answer a different
question. It is left alone here for that reason. But it means the accelerator
is not yet a parameter in code: **on an Ampere-or-newer GPU this script exits
immediately**, and making it run there is an edit to that line plus the dtype
pair above, which the owner should make deliberately rather than by patching
past an assertion.

**And note what moving to bf16 costs:** Step 2's result is specifically *fp16
did not overflow or underflow in five steps*. bf16 has fp16's dynamic range
without its overflow problem, so on newer hardware that finding does not
transfer — it becomes irrelevant rather than confirmed. A co-training run on
bf16 hardware is a **new** stability question, not a settled one, and
`verdict.py`'s criteria 2-3 (finite, non-zero `grad_norm`) are what to re-read
rather than assume.

---

## Getting the files there

The repo is **private**, so `git clone` inside a notebook would mean pasting a
PAT into a cell. Use a dataset instead — no token, and it persists across
sessions.

Locally, from the repo root:

```bash
tar -czf step2-bundle.tar.gz -C step2 verdict.py gate_chat_template.py smoke.py
```

Those three are all the run needs (`test_step2.py`, `mutate.py` and `gc24.py`
are dev-side only). Upload as a **private** Kaggle Dataset named `cotrain-step2`,
then *Add Input* it to the notebook. It lands at `/kaggle/input/cotrain-step2/`.

> If you would rather clone: put the PAT in Kaggle *Add-ons → Secrets* as
> `GH_PAT` and read it with `UserSecretsClient`. Never paste it into a cell —
> notebook source is saved with the output.

---

## Cell 1 — see what the image ships, before changing it

```python
import subprocess, torch, sys
print("python ", sys.version.split()[0])
print("torch  ", torch.__version__, "| cuda", torch.version.cuda)
print("gpu    ", torch.cuda.get_device_name(0), torch.cuda.get_device_capability(),
      "x", torch.cuda.device_count())
print(subprocess.run(["pip","list"], capture_output=True, text=True).stdout.count("\n"), "packages")
for p in ("transformers","trl","peft","accelerate","unsloth"):
    print(subprocess.run(["pip","show",p], capture_output=True, text=True).stdout.split("Version:")[-1].split("\n")[0].strip() or "-", p)
```

Expect `sm_75` and `x2`. **If capability is 8.0+ you are not on a T4** and the
fp16 question this step exists to answer does not apply — `smoke.py` asserts
this and will refuse.

Note the preinstalled `torch`. The next cell may want to replace it; a torch
swap is a multi-GB download and can land a CUDA build that does not match the
driver. If it tries to, re-run with `--no-deps` for `unsloth` and install the
rest by hand.

## Cell 2 — install, with the pin that matters

```python
!pip install --no-cache-dir --timeout 60 --retries 5 -q unsloth==2026.9.12 "trl==0.24.0" "transformers<5"
```

**Do NOT restart the kernel afterwards.** Kaggle's "Restart session" resets the
container to the base image and silently discards the install: pip reports
`Successfully installed`, then after the restart the module is simply absent.
This cost a full re-install on the 2026-09-30 run.

Instead run every cell below with `!`, so each gets a fresh subprocess that sees
the new packages. The notebook kernel keeps the image's stale `transformers
5.0.0` in memory, which is harmless because nothing that matters runs in-kernel.
Verify with a subprocess, not an import:

```python
!python -c "import transformers, trl; print(transformers.__version__, trl.__version__); from trl import GRPOTrainer; print('OK')"
```

`--timeout 60 --retries 5` bounds each socket wait. Without it pip hung twice
with **CPU at 0.00%** and no output — a dead socket, not slow work. Judge by the
session resource panel, not the output: CPU moving means progress, `0.00%` for
two minutes means dead, interrupt and re-run. Downloads are cached, so a re-run
resumes quickly.

`transformers<5` is **load-bearing, not hygiene.** Unsloth 2026.9.12 pinned
`trl<=0.24.0` (2026.10.3 does not — see below); TRL 0.24 declares
`transformers>=4.56.1` with no upper bound;
transformers 5 changed `_is_package_available` to return `tuple[bool, str]`.
TRL stores the raw result, so every `is_X_available()` returns `(False, None)`
— truthy — and every optional-dependency guard fires against a missing
package. `from trl import GRPOTrainer` then dies on `mergekit`, naming neither
transformers nor the cause. Verified: 11 of 12 flags inverted on 5.5.0, zero
on 4.57.6.

**The version pins are new, and the reason is that the old command stopped
pinning itself.** `pip install unsloth "transformers<5"` was self-pinning when
it was written: unsloth **2026.9.12**, the version the 2026-09-30 run used,
declares `trl!=0.19.0,<=0.24.0,>=0.18.2`, so TRL could not go above 0.24
whatever pip preferred. Unsloth **2026.10.3** (2026-10-08) declares
`trl!=0.19.0,<=1.13.0,>=0.18.2`. The ceiling moved, and `transformers<5` does
not substitute for it, because trl 1.13.0 requires only `transformers>=4.56.2`
— which 4.57.6 satisfies. So an unpinned `unsloth` is now free to bring TRL up
to 1.13.0, where `max_prompt_length` does not exist (`grpo_config.py`: 2
occurrences at tag v0.24.0, 0 at v1.13.0) and which `smoke.py` passes.
GRPOConfig would raise after the install, the queue and the weight download.

The pins above name the stack the artifact records (`step2/results/README.md`:
unsloth 2026.9.12, unsloth_zoo 2026.9.8, trl 0.24.0, transformers 4.57.6)
rather than a ceiling guessed from metadata. `trl<=0.24` *is* declared-
compatible with unsloth 2026.10.3, but that pairing has never been run and is
not what produced the PASS, so it is not what this cell asks for.

> **UNKNOWN: what pip actually resolves inside the Kaggle image cannot be
> established from a dev machine, and this cell is not evidence that it can.**
> Kaggle preinstalls torch, transformers and bitsandbytes, so resolution
> depends on what is already satisfied there. A cross-platform `pip install
> --dry-run --platform manylinux2014_x86_64` was tried and is NOT faithful:
> `--platform` forces `--only-binary=:all:`, which excludes sdists and made the
> resolver pick unsloth 2025.10.1; pinning unsloth==2026.10.3 under those flags
> failed outright on bitsandbytes wheel availability. Neither result describes
> Kaggle. Treat the resolved versions as unverified until cell 2's own output
> prints them, which is what the verify line below is for.

**The defence that does not depend on predicting the resolution** is
`gate_chat_template.py`: it diffs smoke.py's GRPOConfig kwargs against the
**installed** class via `dataclasses.fields`, so it reports whatever actually
resolved and exits 1 before the weight download. Run cell 3 even if cell 2
looked clean.


Do not restart — see above.

## Cell 3 — preflight. Costs ~20 s, saves a session.

```python
import shutil, os
os.makedirs("/kaggle/working/step2", exist_ok=True)
for f in ("verdict.py","gate_chat_template.py","smoke.py"):
    shutil.copy(f"/kaggle/input/cotrain-step2/{f}", f"/kaggle/working/step2/{f}")
%cd /kaggle/working
!python step2/gate_chat_template.py
```

Exit 0 to continue. It checks three things: that TRL's optional-dependency
flags are real bools, that every `GRPOConfig` kwarg `smoke.py` passes exists on
the **installed** TRL, and that `unsloth/Qwen3-0.6B`'s chat template is
prefix-preserving.

**Expect `prefix-preserving False`** — that is the known, correct answer, and
it does not block Step 2 (the raise it would trigger is guarded by
`if self.tools`, and TRL 0.24 has no tool loop at all). It blocks on the
poisoned-flag and unknown-kwarg conditions.

It now checks `unsloth/Qwen3-0.6B`, which is what `smoke.py` loads; it used to
default to `Qwen/Qwen3-0.6B` and so measured a template the run never sees.
That mattered more than it sounds — see `README.md`, "The repair matches
`Qwen/Qwen3-0.6B`. The run loads `unsloth/Qwen3-0.6B`." On a TRL that has the
tool loop (>= 0.26) expect **`PASS, CONDITIONALLY`** on this repo, with the one
assignment it tells you to make. Pass a different repo as `argv[1]` to compare.

## Cell 4 — the run

```python
!cd /kaggle/working && python step2/smoke.py
```

Five GRPO steps, Qwen3-0.6B, fp16, LoRA r=32, `use_vllm=False`, on-policy.
Writes `step2_metrics.jsonl` and prints `STEP 2 PASS` / `STEP 2 FAIL` with
reasons. **Download the JSONL the moment the run ends** — `/kaggle/working` did
NOT survive the 2026-09-30 run. The session reset after `smoke.py` finished and
wiped the directory before the file could be fetched, so the committed result in
`step2/results/` had to be reconstructed from notebook stdout. Do not assume
`/kaggle/working` persists.

## Cell 5 — re-check and keep the evidence

```python
!cd /kaggle/working && python step2/verdict.py step2_metrics.jsonl
from IPython.display import FileLink; FileLink("step2_metrics.jsonl")
```

Download the JSONL and commit it — it is the evidence for the Step 2 claim,
and `verdict.py` can be re-run against it later without a GPU.

---

## Reading a failure

| Symptom | Meaning |
|---|---|
| `ModuleNotFoundError: mergekit` | Cell 2's pin was skipped or a later install pulled transformers 5 back in. |
| `GRPOConfig.__init__() got an unexpected keyword argument` | Cell 2's version pins were skipped, so pip resolved a TRL above 0.24 under Unsloth's lifted ceiling. `max_prompt_length` is the first casualty; the preflight names the kwarg. |
| `assert cap[0] < 8` | Not a T4. Wrong accelerator selected. |
| `reward_std is 0.0 on every step` | Degenerate reward — the run produced no gradient and proves nothing about fp16. Not a pass. |
| `grad_norm ... not finite` | **This is the fp16 answer, and it is "no".** Record it; that is a real result, not a bug to work around. |
| `entropy collapsed` | Check `learning_rate` is still 3e-5. Garg: 1e-4 drives entropy to zero. |
| `only N training steps logged` | The run died early; the reasons above it say why. |
| OOM | Drop `per_device_train_batch_size` and `num_generations` together — TRL requires batch to be divisible by `num_generations`. |

A `STEP 2 FAIL` from criterion 2 or 3 is **not** a broken script. fp16
instability on Turing is exactly what this step was built to detect, and a
clean negative closes Step 2 just as well as a pass — it sends Step 6 to
rented Ampere instead. `08` found prime-rl cannot run on a T4 at all, so that
fork was already live.
