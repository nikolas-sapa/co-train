"""Pass criteria for the dead-group probe and the co-training run. Pure stdlib.

`step2/verdict.py` decides whether a Step 2 smoke run counts as a pass; this
decides whether a probe says the reward separates, and whether a co-training run
should be stopped. Same split and the same reason: the run needs a GPU, the
adjudication does not, and the adjudication is the falsifiable part.

    python train/verdict.py probe_metrics.jsonl            # the probe
    python train/verdict.py run_metrics.jsonl --run        # a co-training run

**The two abort criteria of spec §240 need no new instrumentation.** Both metrics
are already emitted by the stack: `frac_reward_zero_std` is in
`step2/results/step2_metrics.jsonl` at 0.0, and trl 1.13.0 logs
`sampling/sampling_logp_difference/{mean,max}` at `grpo_trainer.py:2893,2896`.

**Criterion A is stated twice in the spec and the two forms are different tests.**
§240 says "> 0.60 sustained over 10 consecutive steps"; §282's probe table says
"> 0.60 on any step". Both are implemented, separately named, and neither stands
in for the other: `probe_verdict` uses the any-step form because it adjudicates
the probe, `run_verdict` uses the sustained form because it adjudicates a run.
The discrepancy is recorded in `docs/train-notes.md`, not resolved here.
"""

from __future__ import annotations

import json
import math
import statistics
if __package__ in (None, ""):  # invoked as `python train/<file>.py`, not `-m`
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from typing import Any, Iterable, Sequence

# ------------------------------------------------------------- the two metrics

ZERO_STD_KEY = "frac_reward_zero_std"
"""Criterion A's metric. Fraction of groups in the batch with zero reward std,
i.e. the fraction of the batch that yields no gradient."""

LOGP_DIFF_KEY = "sampling/sampling_logp_difference/mean"
"""Criterion B's metric. trl 1.13.0 computes
`vllm_importance_sampling_ratio = torch.exp(logps_diff)` (`grpo_trainer.py:2696`)
and logs the difference's mean and max, with
`vllm_importance_sampling_correction=True` and mode `"sequence_mask"` as
measured defaults."""

COMPLETION_SAMPLES_KEY = "completion_samples"
"""Where the probe records what the model actually wrote: a list per step of
`{chars, completion, extracted, reward}` -- the untruncated length, the reply cut to
`dead_group_probe.SAMPLE_CHARS`, what the reward's own extraction recovered from it,
and the score it received.

**Read as an observation and never as a criterion.** Text is evidence for a diagnosis;
it must not be able to make a probe pass, and a failure must not be downgradable to a
quote. `observations()` prints it, `probe_verdict` does not look at it."""

# ----------------------------------------------------------------- thresholds

ZERO_STD_CEILING = 0.60
"""Assumed, and stated as assumed by the spec. Above it, most of the batch
yields no gradient."""

SUSTAINED_WINDOW = 10
"""Consecutive logged steps for criterion A's run form and both arms of B."""

MIN_PROBE_STEPS = 5
"""The probe is "5-20 steps, aborting" (§279). Fewer than 5 is not a probe.

This is the fail-closed line, and it is the single most important one in the
file for the same reason it is in `step2/verdict.py`: without it every `any(...)`
below is vacuously false and a probe that trained zero steps reports a pass.
"""

LOGP_RATIO_MULTIPLE = 3.0
"""Criterion B: "a mean exceeding 3x its first-10-step median" (assumed; the
paper gives the mechanism, not a number)."""


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def training_steps(logs: Iterable[dict]) -> list[dict]:
    """A training step is a log line carrying "loss".

    Same definition as `step2/verdict.py`, deliberately re-stated rather than
    imported: this file has to work from a Kaggle session that only has `train/`,
    and an import that silently falls back would be worse than a duplicate.
    `test_train.py` asserts the two agree on a shared fixture, so the duplication
    is guarded rather than trusted.

    HF Trainer's end-of-run summary uses "train_loss" and eval uses "eval_loss",
    so exact-key match excludes both.
    """
    return [r for r in logs if "loss" in r]


def header(logs: Iterable[dict]) -> dict | None:
    """The provenance row the probe writes before its first step."""
    for row in logs:
        if "taskset_id" in row:
            return row
    return None


def completion_samples(logs: Sequence[dict]) -> list[tuple[int, dict]]:
    """`(step index, sample)` for every completion the probe recorded."""
    return [(i, sample)
            for i, row in enumerate(training_steps(logs))
            for sample in (row.get(COMPLETION_SAMPLES_KEY) or [])]


# -------------------------------------------------------------- criterion A


def criterion_a_any_step(logs: Sequence[dict], window: int = 1) -> list[str]:
    """§282, the probe's form: abort if `frac_reward_zero_std` > 0.60 on **any** step.

    `window` is the number of consecutive breaching steps required before the
    criterion fires. It defaults to 1, which is §282 verbatim; a larger value is a
    documented power choice, not a softening, and it is why this is a parameter
    rather than a second criterion.

    **Why a window can be justified without touching the ceiling.** At G=8 the
    ceiling sits exactly on the band's lower edge: `zero_advantage_fraction` at
    p=0.062 is 0.600, so a policy that is *precisely viable* breaches a
    single-step test 47.5% of the time, and one at p=0.10 breaches it 21.6% of the
    time. Those are false aborts of a policy the probe exists to certify. At
    window 3 the same rates are 0.107 and 0.010, while a genuinely hopeless policy
    (p=0.02) still fires with probability 0.708. The window buys power against
    noise without letting a dead reward through.

    The other reason this exists: `probe_verdict` requires `MIN_PROBE_STEPS`,
    but a step-0 breach under the window-1 rule ends the run before five steps can
    ever accumulate, so the probe could not satisfy its own verdict. Two
    adjudicators over one run must not disagree about how much evidence there is.

    Fail-closed on absence. The metric is the probe's only instrument, so a run
    that did not log it has measured nothing, and a run that measured nothing
    must not read as a clean one.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window!r}")
    reasons: list[str] = []
    steps = training_steps(logs)
    breach_run: list[int] = []
    for i, row in enumerate(steps):
        value = row.get(ZERO_STD_KEY)
        if not _finite(value):
            # Per step, with no aggregate "never logged" line after the loop: a
            # step without the metric already fails here, so a summary could
            # never change the outcome. `train/mutate.py` found that line
            # surviving every mutation, which is this repo's own definition of a
            # guard worth deleting. `criterion_a_sustained` keeps its equivalent
            # because there the loop alone returns clean on an absent metric.
            reasons.append(
                f"step {i}: {ZERO_STD_KEY} is {value!r}, not a finite number -- the "
                "criterion cannot fire, so the run is not adjudicable"
            )
            continue
        if value > ZERO_STD_CEILING:
            breach_run.append(i)
            if len(breach_run) >= window:
                span = (f"step {i}" if window == 1
                        else f"steps {breach_run[0]}-{i} ({window} consecutive)")
                reasons.append(
                    f"{span}: {ZERO_STD_KEY} is {value:.3f} > {ZERO_STD_CEILING} -- most "
                    "of the batch yields no gradient. The reward's shape, not the "
                    "pipeline, is the problem, and no taskset fixes a reward that cannot "
                    "separate."
                )
                if window == 1:
                    # Every breaching step is its own reason, as §282 reads.
                    breach_run.clear()
                else:
                    break
        else:
            breach_run.clear()
    return reasons


def criterion_a_sustained(logs: Sequence[dict]) -> list[str]:
    """§240, a run's form: abort if > 0.60 is **sustained over 10 consecutive steps**.

    Strictly weaker than `criterion_a_any_step`: a single spike passes here and
    aborts there. That is the discrepancy, and it is why both exist.
    """
    reasons: list[str] = []
    steps = training_steps(logs)
    values = [(i, r.get(ZERO_STD_KEY)) for i, r in enumerate(steps)]
    if steps and not any(_finite(v) for _, v in values):
        return [f"{ZERO_STD_KEY} was never logged on any of {len(steps)} steps"]

    run_start: int | None = None
    for i, value in values:
        over = _finite(value) and value > ZERO_STD_CEILING
        if over:
            run_start = i if run_start is None else run_start
            if i - run_start + 1 >= SUSTAINED_WINDOW:
                reasons.append(
                    f"steps {run_start}-{i}: {ZERO_STD_KEY} above {ZERO_STD_CEILING} "
                    f"for {SUSTAINED_WINDOW} consecutive steps"
                )
                break
        else:
            run_start = None
    return reasons


# -------------------------------------------------------------- criterion B


def criterion_b(logs: Sequence[dict], required: bool = True) -> tuple[list[str], list[str]]:
    """§253-270: the `sampling_logp_difference` trend. Returns (reasons, notes).

    arXiv:2510.26788's diagnostic is that runs which collapse show a *growing*
    mismatch beforehand, so both arms of this test are about change, not level:

    - a monotonic rise across `SUSTAINED_WINDOW` consecutive logged steps, or
    - a mean exceeding `LOGP_RATIO_MULTIPLE` x its own first-window median.

    **There is deliberately no absolute-level test.** "A flat elevated value is a
    calibration offset, not this signal" (§261), and a level threshold would fire
    on the offset and miss the trend.

    The ratio arm is reported as *not evaluable* when the baseline median is not
    positive, rather than being silently skipped: `logps_diff` can sit at or
    below zero, and `3 x` a non-positive baseline is a smaller number, so the
    comparison would quietly invert into a guard that can never fire.
    """
    reasons: list[str] = []
    notes: list[str] = []
    steps = training_steps(logs)
    values = [r[LOGP_DIFF_KEY] for r in steps if _finite(r.get(LOGP_DIFF_KEY))]

    if not values:
        message = (
            f"{LOGP_DIFF_KEY} was never logged over {len(steps)} steps. trl 1.13.0 "
            "logs it at grpo_trainer.py:2893, so absence means the run is not on "
            "the stack the spec measured, or the key moved -- either way criterion "
            "B cannot fire and a green verdict would be a guard reporting on an "
            "unreachable target."
        )
        (reasons if required else notes).append(message)
        return reasons, notes

    if len(values) < SUSTAINED_WINDOW:
        notes.append(
            f"criterion B is NOT evaluable: {len(values)} logged values, needs "
            f"{SUSTAINED_WINDOW}. Expected on a {MIN_PROBE_STEPS}-step probe; a "
            "finding on a short run, not a pass."
        )
        return reasons, notes

    for i in range(len(values) - SUSTAINED_WINDOW + 1):
        window = values[i : i + SUSTAINED_WINDOW]
        if all(b > a for a, b in zip(window, window[1:])):
            reasons.append(
                f"steps {i}-{i + SUSTAINED_WINDOW - 1}: {LOGP_DIFF_KEY} rises "
                f"monotonically from {window[0]:.4g} to {window[-1]:.4g}. A growing "
                "training-inference mismatch is the documented precursor to collapse."
            )
            break

    baseline = statistics.median(values[:SUSTAINED_WINDOW])
    if baseline <= 0:
        notes.append(
            f"the ratio arm of criterion B is NOT evaluable: the first-"
            f"{SUSTAINED_WINDOW}-step median is {baseline:.4g}, and "
            f"{LOGP_RATIO_MULTIPLE}x a non-positive baseline is not a ceiling. The "
            "monotonic-rise arm still applies."
        )
    else:
        worst = max(values)
        if worst > LOGP_RATIO_MULTIPLE * baseline:
            reasons.append(
                f"{LOGP_DIFF_KEY} reached {worst:.4g}, above {LOGP_RATIO_MULTIPLE}x "
                f"its first-{SUSTAINED_WINDOW}-step median of {baseline:.4g}"
            )

    notes.append(
        "criterion B has only ever been exercised against synthetic fixtures. The "
        "spec's own test is to run generation in bf16 while training in fp16, where "
        "the paper's measurement says the mismatch grows ~24x, so the logged mean "
        "must move by a large visible factor; if it does not move, the metric is not "
        "wired to anything. Cost: one five-step run. Toggling "
        "vllm_importance_sampling_correction is NOT a valid test -- it changes the "
        "clipping, not the logged difference. NOT RUN; owner's call."
    )
    return reasons, notes


# ----------------------------------------------------------------- verdicts


def probe_verdict(logs: Sequence[dict], window: int = 1) -> tuple[bool, list[str]]:
    """Does this dead-group probe say the reward separates? (passed, reasons).

    Reports every failure, not just the first. Informational lines live in
    `observations()` so that a note can never make a probe pass and a failure can
    never be downgraded to a note.
    """
    reasons: list[str] = []
    steps = training_steps(logs)

    if len(steps) < MIN_PROBE_STEPS:
        reasons.append(
            f"only {len(steps)} training steps logged, need {MIN_PROBE_STEPS}"
        )

    provenance = header(logs)
    if provenance is None or not str(provenance.get("taskset_id") or "").strip():
        reasons.append(
            "no taskset_id in the metrics header. The realised zero-advantage "
            "fraction is a property of (policy, taskset, G) jointly, and this repo "
            "has already shipped a real number attached to the wrong denominator. A "
            "probe result without its taskset is not quotable."
        )

    reasons += criterion_a_any_step(logs, window=window)
    return (not reasons), reasons


def run_verdict(logs: Sequence[dict]) -> tuple[bool, list[str]]:
    """Should this co-training run be stopped? (continue_ok, reasons).

    Criterion A in its sustained form plus criterion B, both required. A run long
    enough to be worth adjudicating is long enough for B to be evaluable.
    """
    reasons: list[str] = []
    steps = training_steps(logs)
    if len(steps) < MIN_PROBE_STEPS:
        reasons.append(f"only {len(steps)} training steps logged, need {MIN_PROBE_STEPS}")
    reasons += criterion_a_sustained(logs)
    reasons += criterion_b(logs, required=True)[0]
    return (not reasons), reasons


def _sample_observations(logs: Sequence[dict]) -> list[str]:
    """What the model actually wrote, shown without being asked for.

    A reader adjudicating a run whose reward is 0.0 everywhere needs the text, not a
    pointer to the JSONL: reward 0 with text present and nothing extracted is a format
    fault, with nothing generated it is a generation fault, and with SQL extracted it
    is the policy. One summary line carries those three counts, then the FIRST SAMPLED
    STEP IN FULL.

    In full, and one step, because the unit is a group: the probe records the step's
    first `dead_group_probe.SAMPLES_PER_STEP` completions, which TRL lays out as one
    prompt's group -- exactly what `frac_reward_zero_std` counts. Printing a fixed few
    instead would cut that group mid-way and hide whichever shape came last, which is
    how the first draft of this hid the unterminated-fence case. The rest of the file
    is named, not printed.
    """
    out: list[str] = []
    steps = training_steps(logs)
    carrying = [r for r in steps if COMPLETION_SAMPLES_KEY in r]
    samples = completion_samples(logs)

    if steps and not carrying:
        return [
            "no step recorded what the model wrote, so this file cannot say WHY the "
            f"reward is what it is. A reward of 0 with {ZERO_STD_KEY} at 1.0 is equally "
            "consistent with a policy that cannot solve the task, output the reward's "
            "extraction does not recover, an empty generation path, and the completion "
            "cap cutting the answer off -- four different fixes. Re-run without "
            "--no-completion-samples; sampling is on by default."
        ]
    if carrying and not samples:
        return [
            f"completion sampling was ON and recorded nothing across {len(carrying)} "
            "steps: the reward function was never handed a completion. That is a "
            "generation-path fault, not a policy one, and no change to the reward "
            "addresses it."
        ]
    if not samples:
        return out

    scored = [s for _, s in samples if _finite(s.get("reward")) and s["reward"] > 0]
    unrecovered = [s for _, s in samples if not s.get("extracted")]
    empty = [s for _, s in samples if not s.get("chars")]
    out.append(
        f"{len(samples)} completions sampled over {len(carrying)} steps: {len(scored)} "
        f"scored above 0, {len(unrecovered)} had nothing recovered by the reward's "
        f"extraction, {len(empty)} were empty. Reward 0 with text present and nothing "
        "extracted is a format fault; with nothing generated, a generation fault; with "
        "the answer extracted, the policy."
    )
    first = min(index for index, _ in samples)
    shown = [sample for index, sample in samples if index == first]
    for sample in shown:
        out.append(
            f"step {first} sample: reward {sample.get('reward')!r}, "
            f"{sample.get('chars')!r} chars generated, "
            f"extracted {sample.get('extracted')!r}, raw {sample.get('completion')!r}"
        )
    if len(samples) > len(shown):
        out.append(
            f"{len(samples) - len(shown)} further samples, from the steps after "
            f"{first}, are in the metrics file under {COMPLETION_SAMPLES_KEY!r}."
        )
    return out


def observations(logs: Sequence[dict]) -> list[str]:
    """What the operator should see that is not a failure."""
    # Lazy, and the only edge of its kind: `dead_group_probe` imports this module
    # at its top, so the derivations have to be reached at call time. They live
    # there because that is the probe's content, not the adjudicator's.
    from train.dead_group_probe import (
        NUM_GENERATIONS,
        implied_solve_rates,
        probe_expectations,
    )

    out: list[str] = []
    steps = training_steps(logs)
    values = [r[ZERO_STD_KEY] for r in steps if _finite(r.get(ZERO_STD_KEY))]

    if values:
        realised = statistics.fmean(values)
        expected = probe_expectations()["expected_frac_reward_zero_std"]
        out.append(
            f"{ZERO_STD_KEY}: realised mean {realised:.3f} over {len(values)} steps "
            f"against {expected:.3f} expected at G={NUM_GENERATIONS} from "
            "deepseek-v4-flash's p. The reference p is not this policy's."
        )
        band = implied_solve_rates(realised, NUM_GENERATIONS)
        if band:
            out.append(
                f"that fraction implies a solve rate of about {band[0]:.3f} or "
                f"{band[1]:.3f} -- the two roots are indistinguishable from this "
                "metric alone, and they are opposite diagnoses. Read the mean reward "
                "to tell them apart."
            )

    out += _sample_observations(logs)

    if steps and not any(LOGP_DIFF_KEY in r for r in steps):
        out.append(
            f"{LOGP_DIFF_KEY} is absent, so criterion B is dormant on this file. On "
            "trl 1.13.0 it is logged unconditionally; on 0.24.0 it does not exist. "
            "`criterion_b` says what that costs."
        )

    kls = [r["kl"] for r in steps if _finite(r.get("kl"))]
    if kls and len(set(kls)) == 1:
        out.append(
            f"kl is the constant {kls[0]!r} on every step. Unsloth logs kl "
            "unconditionally and at beta=0 the per-token KL is zeros_like(...), so a "
            "flat 0.0 means no KL was measured -- do not read the JSONL as a KL curve."
        )
    return out


def load(path: str) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Re-check a probe or run metrics JSONL.")
    parser.add_argument("metrics")
    parser.add_argument("--run", action="store_true",
                        help="adjudicate a co-training run (criterion A sustained + B) "
                             "instead of a probe (criterion A on any step)")
    parser.add_argument("--abort-window", type=int, default=None,
                        help="override the window; default is the header's "
                             "`abort_window`, or 1 (§282) when the header has none")
    args = parser.parse_args(argv)

    rows = load(args.metrics)
    label = "RUN" if args.run else "PROBE"
    window = args.abort_window
    if window is None:
        window = int((header(rows) or {}).get("abort_window") or 1)
    ok, why = run_verdict(rows) if args.run else probe_verdict(rows, window=window)
    if not args.run:
        print(f"abort window: {window}")
    print(f"{label} PASS" if ok else f"{label} ABORT")
    for reason in why:
        print("  -", reason)

    notes = observations(rows) + criterion_b(rows, required=False)[1]
    if notes:
        print("\nobservations (not failures):")
        for note in notes:
            print("  ·", note)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
