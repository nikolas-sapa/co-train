"""Step 2 pass criteria and the smoke-task reward. Pure stdlib — no torch.

This file is the falsifiable part of Step 2. The training run itself only
happens on Kaggle, but whether that run *counts as a pass* is decided here,
against numeric thresholds, by code that is tested on the dev machine.

Split deliberately: `smoke.py` needs a GPU, this does not.
"""

from __future__ import annotations

import json
import math

# ---------------------------------------------------------------- reward

TARGET_WORDS = 20


def word_count_reward(completions, **kwargs) -> list[float]:
    """Continuous reward: how close the completion is to TARGET_WORDS words.

    Continuous, NOT binary, and that is the whole point. GRPO's advantage is
    the within-group deviation from the group mean, so a reward that returns
    the same value for all `num_generations` samples yields a zero advantage
    and therefore a zero gradient. The run would complete, log green, and
    prove nothing about fp16 — the exact false-green shape Step 1 kept hitting.
    An untrained 0.6B emits wildly different lengths, so this one cannot
    collapse. `verdict()` checks that it did not anyway.

    ponytail: length proxy, not a real task. Step 4 brings the real reward.
    """
    out = []
    for c in completions:
        text = c if isinstance(c, str) else c[-1]["content"]
        n = len(text.split())
        out.append(max(0.0, 1.0 - abs(n - TARGET_WORDS) / TARGET_WORDS))
    return out


# ---------------------------------------------------------------- verdict

# The four health signals HANDOFF.md requires from run 1, mapped to the keys
# TRL actually logs (verified against trl v0.24.0 grpo_trainer.py, which is
# the ceiling Unsloth pins at `trl>=0.18.2,!=0.19.0,<=0.24.0`).
REQUIRED_KEYS = ("grad_norm", "completions/mean_length", "entropy", "reward_std")

MIN_STEPS = 5
ENTROPY_FLOOR = 0.01  # Garg: lr 1e-4 drives entropy to zero; 3e-5 does not.


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def verdict(logs: list[dict]) -> tuple[bool, list[str]]:
    """Apply Step 2's pass criteria to TRL's logged metrics.

    Returns (passed, reasons). `reasons` lists every failure, not just the
    first — a run that is both truncated and NaN should say so once.
    """
    reasons: list[str] = []

    # A training step is a log line carrying "loss". HF Trainer's end-of-run
    # summary uses "train_loss" and eval uses "eval_loss", so exact-key match
    # excludes both. The marker is deliberately NOT one of REQUIRED_KEYS: if
    # grad_norm were the marker, a run that stopped logging it would silently
    # shrink the step count instead of reporting the missing signal.
    steps = [r for r in logs if "loss" in r]

    # Fail-closed on an empty or short run. Without this, every `all(...)`
    # below is vacuously true and a run that trained zero steps reports a
    # pass. This is the single most important line in the file.
    if len(steps) < MIN_STEPS:
        reasons.append(f"only {len(steps)} training steps logged, need {MIN_STEPS}")

    for i, row in enumerate(steps):
        missing = [k for k in REQUIRED_KEYS if k not in row]
        if missing:
            reasons.append(f"step {i}: missing {', '.join(missing)}")
        for k in REQUIRED_KEYS:
            if k in row and not _finite(row[k]):
                reasons.append(f"step {i}: {k} is {row[k]!r}, not finite")
        if "loss" in row and not _finite(row["loss"]):
            reasons.append(f"step {i}: loss is {row['loss']!r}, not finite")

    # fp16 overflow shows up as a non-finite grad_norm (caught above) or as a
    # grad_norm pinned at exactly zero because every gradient underflowed.
    gn = [r["grad_norm"] for r in steps if _finite(r.get("grad_norm"))]
    if gn and not any(g > 0.0 for g in gn):
        reasons.append("grad_norm is 0.0 on every step — no gradient reached the weights")

    # Non-degenerate reward: at least one step must have within-group spread,
    # or the gradient was zero by construction and fp16 was never exercised.
    rs = [r["reward_std"] for r in steps if _finite(r.get("reward_std"))]
    if rs and not any(s > 0.0 for s in rs):
        reasons.append("reward_std is 0.0 on every step — degenerate reward, run proves nothing")

    ent = [r["entropy"] for r in steps if _finite(r.get("entropy"))]
    if ent and not all(e > ENTROPY_FLOOR for e in ent):
        worst = min(ent)
        reasons.append(f"entropy collapsed to {worst:.4g} (floor {ENTROPY_FLOOR}) — policy collapse")

    return (not reasons), reasons


def load(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import sys

    ok, why = verdict(load(sys.argv[1]))
    print("STEP 2 PASS" if ok else "STEP 2 FAIL")
    for r in why:
        print("  -", r)
    sys.exit(0 if ok else 1)
