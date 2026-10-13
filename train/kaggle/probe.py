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


# 1. The stack, pinned to the versions the spec measured. `unsloth==2026.10.3` is
#    exact rather than `>=`: below it unsloth pins trl<=0.24.0, where rollout_func,
#    self.tools, tool_mask and get_training_chat_template are all at ZERO
#    occurrences -- but 2026.10.4 also exists and its pin was never checked, so
#    floating up would be an unverified stack rather than a safer one.
run([sys.executable, "-m", "pip", "install", "-q",
     "unsloth==2026.10.3", "trl==1.13.0", "transformers<5"])

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

assert cap[0] < 8, (
    f"expected a pre-Ampere GPU for the fp16 question, got sm_{cap[0]}{cap[1]}. "
    "fp16 is a DECISION here, not a workaround: arXiv:2510.26788 measures bf16's "
    "training-inference mismatch at ~24x fp16's. On newer hardware this becomes a "
    "new stability question rather than a settled one. Do not patch past this."
)

# 4. The probe. 5 steps is the minimum `verdict.py` will adjudicate, and it yields
#    the per-step wall-clock so 20 can be decided from data instead of guessed.
run([sys.executable, "-m", "train.dead_group_probe",
     "--prompts", "bench/probe_prompts.jsonl",
     "--taskset-id", "bird-dev-scalar-subset-seed0",
     "--steps", "5",
     "--out", OUT], cwd=REPO)

# 5. Re-adjudicate in-session, so a failure is visible in the log and not only in a
#    file someone has to remember to fetch.
subprocess.run([sys.executable, "train/verdict.py", OUT], cwd=REPO, check=False)

size = pathlib.Path(OUT).stat().st_size if pathlib.Path(OUT).exists() else 0
print(f"METRICS BYTES: {size}", flush=True)
assert size > 0, "no metrics were written; the run produced nothing to adjudicate"
