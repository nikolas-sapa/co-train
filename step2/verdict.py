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

# HANDOFF.md's health signals, mapped to the keys THIS STACK logs. The stack is
# not TRL: `import unsloth` (smoke.py:20) runs before `from trl import ...`
# (smoke.py:25), and Unsloth rebinds trl.GRPOTrainer/GRPOConfig to generated
# replacements at import time (unsloth/models/rl.py:3112-3140, reached from
# PatchFastRL at unsloth/models/llama.py:4037). So the contract to check is
# unsloth/models/rl_replacements.py, not trl/trainer/grpo_trainer.py.
#
# `entropy` is deliberately absent, and its absence is the reason this file was
# revised. TRL logs entropy at grpo_trainer.py:1761 — inside `_compute_loss`,
# whose only caller is `compute_loss` (:1650), which Unsloth replaces wholesale
# (rl_replacements.py:2849-3243). That line is dead code here and no Unsloth
# metric replaces it, so requiring `entropy` made every healthy run report FAIL:
# the fail-closed defect this file exists to prevent, living inside this file.
# Corroborated by artifact as well as source — the one public Kaggle 2xT4
# Qwen3-0.6B GRPO run (research/08-gap-closure.md section 7) logs grad_norm,
# reward, completions/mean_length and frac_reward_zero_std, and no entropy.
REQUIRED_KEYS = (
    "grad_norm",
    "completions/mean_length",
    "reward_std",
    "frac_reward_zero_std",  # stands in for entropy; see DEGENERATE_FRAC below
    "kl",                    # only meaningful because smoke.py sets beta > 0
)

MIN_STEPS = 5

# `frac_reward_zero_std` is the fraction of groups whose reward std is ~0
# (trl grpo_trainer.py:1527, in the block Unsloth leaves intact). At 1.0 every
# group has zero advantage, so no gradient existed regardless of what grad_norm
# says. This is a weaker instrument than the entropy floor it replaces — it
# cannot see a policy narrowing while rewards stay spread — and that limit is
# recorded in README's known holes rather than papered over.
DEGENERATE_FRAC = 1.0


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def verdict(logs: list[dict]) -> tuple[bool, list[str]]:
    """Apply Step 2's pass criteria to the metrics the run actually logs.

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
                # fp16's GradScaler calibrates DOWNWARD by overflowing: it
                # starts at init_scale=65536, and the first step legitimately
                # produces inf, which transformers logs verbatim
                # (trainer.py:3206-3207, from accelerator.clip_grad_norm_ at
                # :2715 with error_if_nonfinite=False). Exempting step 0's
                # grad_norm costs one step of overflow coverage; not exempting
                # it fails a correct run. Narrow on purpose: step 0's other
                # keys are still checked, and grad_norm is still checked on
                # steps 1-4, which is where a real fp16 blow-up lives.
                if i == 0 and k == "grad_norm":
                    continue
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

    # Entropy's replacement. Every group degenerate on every step means the
    # advantage was zero throughout, so fp16 was never exercised — the same
    # false-green shape `reward_std` guards, measured per group instead of as a
    # batch mean, which is how the one public run at this config actually died.
    fz = [r["frac_reward_zero_std"] for r in steps if _finite(r.get("frac_reward_zero_std"))]
    if fz and all(f >= DEGENERATE_FRAC for f in fz):
        reasons.append(
            f"frac_reward_zero_std >= {DEGENERATE_FRAC} on every step — "
            "every group degenerate, no advantage anywhere"
        )

    # `kl` needs a SPREAD check, not a finiteness check. Unsloth logs it with no
    # `beta != 0.0` guard (rl_replacements.py:3141, :3144 — TRL does guard it at
    # grpo_trainer.py:1758), and at beta=0 the per-token KL is torch.zeros_like
    # (unsloth_zoo/rl_replacements.py:577-579). So "kl present and finite" is
    # satisfied by a literal constant 0.0, and the JSONL then reads as a KL
    # curve to whoever opens it next. A constant means beta was 0 or the
    # reference path never ran, not that KL was flat. Positivity is the wrong
    # test too: step 0's KL is legitimately 0.0 because LoRA initialises B to
    # zero, so the policy IS the reference on the first step.
    kl = [r["kl"] for r in steps if _finite(r.get("kl"))]
    if kl and len(set(kl)) == 1:
        reasons.append(
            f"kl is constant at {kl[0]!r} on every step — beta=0 or no reference "
            "pass, so no KL was measured"
        )

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
