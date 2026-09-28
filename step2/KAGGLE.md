# Kaggle runbook — Step 2

Paste-ready. Read `README.md` for *why*; this is only *how*.

**Before you start:** Settings → Accelerator → **GPU T4 x2**, and Internet →
**On** (needed for pip and the Qwen3 download). Session budget is 30 GPU-h/week
and 12 h/session, and the kernel dies after 20-30 min idle — so the preflight
cell exists to fail in seconds rather than after the model download.

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
!pip install -q unsloth "transformers<5"
```

`transformers<5` is **load-bearing, not hygiene.** Unsloth pins
`trl<=0.24.0`; TRL 0.24 declares `transformers>=4.56.1` with no upper bound;
transformers 5 changed `_is_package_available` to return `tuple[bool, str]`.
TRL stores the raw result, so every `is_X_available()` returns `(False, None)`
— truthy — and every optional-dependency guard fires against a missing
package. `from trl import GRPOTrainer` then dies on `mergekit`, naming neither
transformers nor the cause. Verified: 11 of 12 flags inverted on 5.5.0, zero
on 4.57.6.

Restart the kernel if pip replaced anything already imported.

## Cell 3 — preflight. Costs ~20 s, saves a session.

```python
import shutil, os
os.makedirs("/kaggle/working/step2", exist_ok=True)
for f in ("verdict.py","gate_chat_template.py","smoke.py"):
    shutil.copy(f"/kaggle/input/cotrain-step2/{f}", f"/kaggle/working/step2/{f}")
%cd /kaggle/working
!python step2/gate_chat_template.py
```

Exit 0 to continue. It checks two things: that the optional-dependency flags
are real bools, and that Qwen3-0.6B's chat template is prefix-preserving.
**Expect `prefix-preserving False`** — that is the known, correct answer, and
it does not block Step 2 (the raise it would trigger is guarded by
`if self.tools`, and TRL 0.24 has no tool loop at all). It blocks only on the
poisoned-flag condition.

## Cell 4 — the run

```python
!cd /kaggle/working && python step2/smoke.py
```

Five GRPO steps, Qwen3-0.6B, fp16, LoRA r=32, `use_vllm=False`, on-policy.
Writes `step2_metrics.jsonl` and prints `STEP 2 PASS` / `STEP 2 FAIL` with
reasons. `/kaggle/working` persists; the scrollback does not.

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
