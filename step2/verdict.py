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

# The health signals HANDOFF.md asks for from run 1, restricted to what this
# stack can actually emit. `metric_contract.json` is generated from real
# library source by `gen_metric_contract.py`; `test_step2.py` asserts these
# keys are a subset of it.
#
# `entropy` is NOT here, and its absence is the point. TRL logs it, but only
# from a closure inside `_compute_loss`, which Unsloth replaces wholesale —
# and Unsloth's replacement hardcodes `compute_entropy = False`. Requiring it
# made `verdict()` report STEP 2 FAIL on every healthy run: the fail-closed
# defect sitting inside the file written to prevent fail-closed defects.
# Fifty-six mutants missed it because every test here fed synthetic log dicts
# built from the assumption under test.
REQUIRED_KEYS = ("grad_norm", "completions/mean_length", "reward_std")

MIN_STEPS = 5
ENTROPY_FLOOR = 0.01  # Garg: lr 1e-4 drives entropy to zero; 3e-5 does not.

# fp16 only. torch's GradScaler starts at init_scale=65536 and halves on
# overflow, so the first optimizer step legitimately overflows and transformers
# logs grad_norm as inf. Exempting step 0 specifically, not blanket-exempting
# non-finite values, or the real overflow signal goes with it.
GRAD_NORM_WARMUP_STEPS = 1


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _warmup_exempt(step_index: int, key: str, value) -> bool:
    """True for the one non-finite grad_norm the GradScaler is allowed.

    Shared by `verdict()` (which skips it) and `observations()` (which reports
    it) so the two cannot drift into disagreeing about what was excused.
    """
    return (
        key == "grad_norm"
        and step_index < GRAD_NORM_WARMUP_STEPS
        and not _finite(value)
    )


def training_steps(logs: list[dict]) -> list[dict]:
    """A training step is a log line carrying "loss".

    HF Trainer's end-of-run summary uses "train_loss" and eval uses
    "eval_loss", so exact-key match excludes both. The marker is deliberately
    NOT one of REQUIRED_KEYS: if grad_norm were the marker, a run that stopped
    logging it would silently shrink the step count instead of reporting the
    missing signal.
    """
    return [r for r in logs if "loss" in r]


def observations(logs: list[dict]) -> list[str]:
    """Things the operator should see that are not failures.

    Separate from `verdict()` so that neither can quietly absorb the other:
    a note must never make a run pass, and a failure must never be downgraded
    to a note.
    """
    out: list[str] = []
    steps = training_steps(logs)

    for i, row in enumerate(steps):
        if "grad_norm" in row and _warmup_exempt(i, "grad_norm", row["grad_norm"]):
            out.append(
                f"step {i}: grad_norm {row['grad_norm']!r} — expected under fp16, "
                f"GradScaler calibrating down from 65536. Not counted against the run."
            )

    if steps and not any("entropy" in r for r in steps):
        out.append(
            "entropy was not logged — Unsloth hardcodes compute_entropy=False, so "
            "Garg's clearest collapse signature (entropy -> 0 at lr 1e-4) is NOT "
            "observable on this stack. grad_norm, reward_std and KL are what remain."
        )

    kls = [r["kl"] for r in steps if _finite(r.get("kl"))]
    if kls and len(set(kls)) == 1:
        out.append(
            f"kl is the constant {kls[0]!r} on every step. Unsloth logs kl "
            f"unconditionally, and at beta=0 the per-token KL is zeros_like(...), so "
            f"a flat 0.0 means no KL was measured — do not read the JSONL as a KL curve."
        )
    return out


def verdict(logs: list[dict]) -> tuple[bool, list[str]]:
    """Apply Step 2's pass criteria to the logged metrics.

    Returns (passed, reasons). `reasons` lists every failure, not just the
    first — a run that is both truncated and NaN should say so once.
    Informational lines live in `observations()`.
    """
    reasons: list[str] = []
    steps = training_steps(logs)

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
            if k not in row or _finite(row[k]):
                continue
            if _warmup_exempt(i, k, row[k]):
                continue  # reported by observations(), not a failure
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

    # Entropy is not emitted on the Unsloth stack (see REQUIRED_KEYS). Kept
    # because raw TRL does log it, and Step 6 may well drop Unsloth for rented
    # Ampere — at which point this fires again. `observations()` states out
    # loud when it is dormant, so it is a declared gap rather than a guard
    # that quietly never runs.
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

    rows = load(sys.argv[1])
    ok, why = verdict(rows)
    print("STEP 2 PASS" if ok else "STEP 2 FAIL")
    for r in why:
        print("  -", r)
    notes = observations(rows)
    if notes:
        print("\nobservations (not failures):")
        for n in notes:
            print("  ·", n)
    sys.exit(0 if ok else 1)
