"""Dead-group probe, Kaggle entry point. See docs/RUNBOOK-probe.md for why.

Decides one thing: whether a binary 0/1 reward produces usable GRPO groups for a
0.6B policy. Aborts above 0.60 `frac_reward_zero_std` on any step.
"""

import pathlib
import subprocess
import sys

REPO = "/kaggle/working/co-train"
OUT = "/kaggle/working/probe_metrics.jsonl"


def run(args, cwd=None):
    """No shell: every argument is a literal in this file, and keeping it a list
    means a path with a space cannot become two arguments."""
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


# 1. The stack.
VLLM_WHEEL = (
    "https://github.com/vllm-project/vllm/releases/download/v0.23.0/"
    "vllm-0.23.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
)

# vLLM goes FIRST, from a CUDA-specific wheel, because it carries the hard torch pin
# and the PyPI default is built for the wrong CUDA.
#
# Version 2 installed `vllm==0.23.0` from PyPI and died on:
#   ImportError: Unsloth: vLLM was built for CUDA 13 but this system has CUDA 12.8.
# Kaggle's T4 image is CUDA 12.8 and PyPI's vllm 0.23.0 wheel is a CUDA 13 build.
# The v0.23.0 GitHub release carries six wheels and **only cu129 covers CUDA 12.x** --
# there is no cu128 build -- so this is the one option, and it is the one unsloth's own
# error message recommends.
#
# `--extra-index-url` for cu129 is not decoration: without it pip resolves
# `torch==2.11.0` to the cu128 build (verified: version 2 ended at 2.11.0+cu128), and a
# cu129 vLLM extension against a cu128 torch is the same mismatch one layer down.
# torch 2.11.0+cu129 exists on that index, checked before pushing.
run([sys.executable, "-m", "pip", "install", "-q", VLLM_WHEEL,
     "--extra-index-url", "https://download.pytorch.org/whl/cu129"])

# Then the rest, pinned. `unsloth==2026.10.3` is exact rather than `>=`: below it
# unsloth pins trl<=0.24.0, where rollout_func, self.tools, tool_mask and
# get_training_chat_template are all at ZERO occurrences -- but 2026.10.4 also exists
# and its pin was never checked, so floating up buys an unverified stack.
#
# transformers<5 is the experiment, not a preference: at 5.x the chat-template flags
# invert and the error names neither package (measured, step2/README.md). It is also
# why vLLM is pinned to 0.23.0 -- trl 1.13.0's vllm extra allows <=0.28.0, but every
# vLLM from 0.24.0 up requires transformers>=5.5.3, so the usable window is one
# release wide. Relaxing transformers<5 to reach a newer vLLM changes the experiment
# rather than fixing the install.
#
# unsloth allows torch 2.4-2.15, so none of these should move the torch installed
# above. The resolved versions are printed below so that assumption is checked rather
# than trusted.
run([sys.executable, "-m", "pip", "install", "-q",
     "unsloth==2026.10.3", "trl==1.13.0", "transformers>=4.56.2,<5"])

# 2. The code. Public repo, so no token in a cell.
run(["git", "clone", "--depth", "1",
     "https://github.com/nikolas-sapa/co-train", REPO])

# 3. Fail in seconds rather than after a model download.
import torch  # noqa: E402  -- after the install, deliberately

assert torch.cuda.is_available(), "no GPU: set Accelerator to a GPU before running"
cap = torch.cuda.get_device_capability()
name = torch.cuda.get_device_name(0)
total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"device: {name} sm_{cap[0]}{cap[1]} {total_gb:.2f} GB "
      f"count={torch.cuda.device_count()}", flush=True)

# Version 1 measured this: Tesla T4, sm_75, 15.64 GB, count=2 -- the same hardware
# Step 2 used. Printed every run because `machine_shape` is empty and Kaggle assigns
# the card, so which card this was is a measurement and not a detail. sm_75 also
# clears vLLM's sm_70 floor; a P100 (sm_60) would pass the fp16 assert below and
# then fail inside vLLM, which is why the card is logged before anything loads.
for mod in ("torch", "transformers", "trl", "vllm", "unsloth"):
    try:
        import importlib.metadata as md
        print(f"resolved {mod}: {md.version(mod)}", flush=True)
    except Exception as exc:                      # noqa: BLE001
        print(f"resolved {mod}: MISSING ({exc})", flush=True)

assert cap[0] < 8, (
    f"expected a pre-Ampere GPU for the fp16 question, got sm_{cap[0]}{cap[1]}. "
    "fp16 is a DECISION here, not a workaround: arXiv:2510.26788 measures bf16's "
    "training-inference mismatch at ~24x fp16's. On newer hardware this becomes a "
    "new stability question rather than a settled one. Do not patch past this."
)

# 4. The probe. 5 steps is the minimum `verdict.py` will adjudicate, and it yields
#    the per-step wall-clock so 20 can be decided from data instead of guessed.
# `--reward ex`, not the default. Version 3 ran the scalar-answer prompts and aborted
# at step 0 with frac_reward_zero_std 1.000 -- which is what p=0 predicts, because
# those prompts carried the schema and asked for a data value with no rows present.
# Unanswerable at any skill level, so the probe measured the prompt design.
#
# The databases are mounted read-only from a private Kaggle dataset: 77 MB holding the
# seven smallest BIRD dev databases, 922 of 1534 questions over 207 shapes. Kaggle
# extracts the uploaded archive, so they sit at <root>/<db_id>/<db_id>.sqlite rather
# than under dev_databases/; `db_path_for` accepts both and is tested on both.
DB_ROOT = "/kaggle/input/bird-dev-subset-cotrain"
assert pathlib.Path(DB_ROOT).is_dir(), (
    f"{DB_ROOT} is not mounted. Add the dataset to the kernel: a reward that cannot "
    "execute anything is indistinguishable from a policy that cannot answer, which is "
    "the confound version 3 died of."
)

run([sys.executable, "-m", "train.dead_group_probe",
     "--prompts", "bench/probe_prompts_sql.jsonl",
     "--taskset-id", "bird-dev-sql-shippable-seed0",
     "--reward", "ex",
     "--db-root", DB_ROOT,
     # G=8, not the spec's 4, and this is the probe answering its own question.
     # Version 4 measured the realised solve rate at p≈0.063-0.069 (step 0 mean
     # reward 0.125, step 1 0.0). The viable band is (0.120, 0.880) at G=4, so that
     # rate sits OUTSIDE it and the abort was correct rather than informative about
     # the reward. The band widens with G: at G=8 it is (0.062, 0.938) and every
     # candidate p falls inside -- 0.597 dead at p=0.0625, 0.564 at p=0.069, against
     # a 0.60 ceiling.
     #
     # The margin at p=0.0625 is 0.003. That is thin, so an unlucky batch can still
     # abort; G=16 (0.356 dead) is the fallback and costs roughly twice the rollouts
     # again. G is a training hyperparameter, so changing it needs no amendment --
     # restricting the taskset to easier tiers would be an instrument change and does.
     "--generations", "8",
     "--steps", "5",
     "--out", OUT], cwd=REPO)

# 5. Re-adjudicate in-session, so a failure is visible in the log and not only in a
#    file someone has to remember to fetch.
subprocess.run([sys.executable, "train/verdict.py", OUT], cwd=REPO, check=False)

size = pathlib.Path(OUT).stat().st_size if pathlib.Path(OUT).exists() else 0
print(f"METRICS BYTES: {size}", flush=True)
assert size > 0, "no metrics were written; the run produced nothing to adjudicate"
