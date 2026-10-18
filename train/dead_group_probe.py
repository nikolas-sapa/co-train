"""The dead-group probe -- `docs/spec-cotrain.md` §270-298. Pure stdlib at import.

**This is the only GPU spend the spec authorises, and it is not training.** It
answers one question no amount of reasoning settles: *does a binary reward
produce usable groups against a 0.6B policy?* It needs no working benchmark,
because it measures the reward's geometry rather than the model's competence,
and it aborts in 5-20 steps.

| | |
|---|---|
| what | 5-20 GRPO steps, aborting; the shape and cost of the Step 2 smoke run |
| metric | `frac_reward_zero_std`, already logged by TRL |
| abort | **> 0.60 on any step.** Stop; do not continue to a training run |
| healthy | ~0.40 at G=4, derived below from the 0/1 reward and p=23/29 |
| if it fires | the reward's shape, not the pipeline, is the problem |

It is explicitly **not** a training run, not a verdict on H2-H5, and not grounds
to build the pipeline. A clean probe says the reward separates -- nothing more.

**And a clean probe says that about the taskset it ran against, not in general.**
`--taskset-id` is mandatory and is written into the metrics header, because the
realised zero-advantage fraction is a property of (policy, taskset, G) jointly
and this repo has already shipped a real number attached to the wrong
denominator. `train/verdict.py` refuses a metrics file whose header does not say
what it was a measurement of.

Everything above `main()` is importable with no GPU and none of the training
stack installed. `main()` imports unsloth/trl/torch and is the only part that
needs a T4.
"""

from __future__ import annotations

import functools
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):  # invoked as `python train/<file>.py`, not `-m`
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from train.verdict import (
    COMPLETION_SAMPLES_KEY,
    ZERO_STD_CEILING,
    ZERO_STD_KEY,
    training_steps,
)

# ------------------------------------------------------------- the derivation
#
# Measured, run 3d: 23 of 29 PTC rollouts solved (`docs/spec-cotrain.md` §130).

SOLVED, ROLLOUTS = 23, 29
SOLVE_RATE = SOLVED / ROLLOUTS
"""0.7931..., which the spec quotes as 0.793.

**Measured on `deepseek-v4-flash`, not on the policy being trained.** That is
the whole reason the probe exists: it sets the healthy expectation, and the
policy that has to realise it is Qwen3-0.6B.
"""

NUM_GENERATIONS = 4
"""G. Derived, not chosen for comfort -- see `expectation_table`."""

ABORT_CEILING = ZERO_STD_CEILING
"""Assumed, stated as assumed by the spec. Above this, most of the batch yields
no gradient. One definition, in `train/verdict.py`, because the spec says
"`verdict.py` owns pass criteria" (§242) and a live abort that disagreed with
the after-the-fact re-check would be the worst of both.

**The spec states this criterion twice, in two different forms**, and they are
not the same test:

- §240 (criterion A, for a co-training *run*): "abort above 0.60 sustained over
  10 consecutive steps".
- §282 (the probe table): "> 0.60 on **any** step".

This module implements the probe table's form, because this module is the probe.
`train/verdict.py` implements both, separately named, and neither silently
stands in for the other. See `docs/train-notes.md`.
"""

WEAK_TAIL_P = 0.1
"""The weak-policy end the spec uses to show both tails degenerate: at G=8,
p=0.1 gives 43% zero-advantage prompts against 15.7% at p=0.79. A *weak* policy
is worse than a strong one, and Qwen3-0.6B is the weak case."""


def zero_advantage_fraction(p: float, g: int) -> float:
    """Expected fraction of groups with zero advantage: `p**g + (1-p)**g`.

    GRPO's advantage is the within-group deviation from the group mean, so a
    group whose rewards are all equal contributes exactly zero gradient. Under a
    binary reward "all equal" means "all right or all wrong", which is a
    Bernoulli coincidence and nothing else -- hence the two terms, and nothing
    else in the expression. TRL's `frac_reward_zero_std` is the fraction of
    groups in the batch whose reward std is zero, so it estimates this directly.

    This is why `ledger`'s reward forces the group size. `ledger/taskset.py:306`
    returns `float(... == ...)`, an exact-match 0/1 reward (measured). Unsloth's
    documented 16 GB T4 example uses G=2, which is tolerable only because their
    GRPO notebooks use *graded* rewards, where G=2 still carries magnitude.
    Against 0/1 it carries one bit, often zero.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be a probability, got {p!r}")
    if g < 2:
        raise ValueError(
            f"g={g}: a group of one has no within-group spread at any p, so the "
            "advantage is zero by construction rather than by coincidence"
        )
    return p**g + (1.0 - p) ** g


EXPECTED_HEALTHY = zero_advantage_fraction(SOLVE_RATE, NUM_GENERATIONS)
"""~0.397, the spec's "~0.40 at G=4". Derived here, never typed in."""


def expectation_table(
    p: float = SOLVE_RATE, group_sizes: Sequence[int] = (2, 4, 8, 16)
) -> dict[int, float]:
    """Zero-advantage fraction by group size. Reproduces the spec's §130 table."""
    return {g: zero_advantage_fraction(p, g) for g in group_sizes}


def viable_band(
    g: int = NUM_GENERATIONS, ceiling: float = ABORT_CEILING, tol: float = 1e-9
) -> tuple[float, float] | None:
    """The `(lo, hi)` solve rates whose zero-advantage fraction stays under `ceiling`.

    `None` when no solve rate clears the ceiling at this `g`.

    This is the probe's question restated as an interval, and it is more useful
    than the ceiling on its own: at G=4 the band is roughly (0.12, 0.88), so the
    probe is a test of whether the realised p falls *outside* it. It also derives
    why G=2 is excluded rather than quoting the 67.2%: p=0.793 sits outside G=2's
    much narrower band.

    `zero_advantage_fraction(., g)` is symmetric about p=0.5 and strictly
    decreasing on [0, 0.5], with f(0)=1 and f(0.5)=2**(1-g), so there is at most
    one root below 0.5 and bisection on [0, 0.5] finds it.
    """
    if zero_advantage_fraction(0.5, g) > ceiling:
        return None
    lo, hi = 0.0, 0.5
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if zero_advantage_fraction(mid, g) > ceiling:
            lo = mid
        else:
            hi = mid
    return (hi, 1.0 - hi)


def implied_solve_rates(
    frac: float, g: int = NUM_GENERATIONS, tol: float = 1e-9
) -> tuple[float, float] | None:
    """The two solve rates that would produce an observed zero-advantage `frac`.

    `None` when no solve rate can: the fraction's floor is `2**(1-g)` (reached at
    p=0.5) and its ceiling is 1, so a realised value below the floor means the
    metric is not measuring what this model says it is.

    **Both roots, always, because they are opposite diagnoses.** A realised 0.45
    at G=4 is either a policy solving ~81% of prompts or one solving ~19% of
    them, and `frac_reward_zero_std` cannot tell them apart -- it is symmetric
    about p=0.5 by construction. The spec's warning that "both tails degenerate"
    is this symmetry. Read the mean reward to break the tie.
    """
    if not zero_advantage_fraction(0.5, g) <= frac <= 1.0:
        return None
    lo, hi = 0.0, 0.5
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if zero_advantage_fraction(mid, g) > frac:
            lo = mid
        else:
            hi = mid
    return (hi, 1.0 - hi)


# ---------------------------------------------------------------- the reward

ANSWER_OPEN, ANSWER_CLOSE = "<answer>", "</answer>"


def completion_text(completion: Any) -> str:
    """The reply text out of one TRL completion, plain or chat-style."""
    return completion if isinstance(completion, str) else completion[-1]["content"]


def extracted_answer(text: str) -> str | None:
    """What `exact_match_reward` compares, or `None` when there was no block to read.

    Split out so the recorded sample shows the reward's *own* extraction rather
    than a second implementation of it -- the gap between what was generated and
    what was extracted is only a measurement if both come from the same function.

    `None` and `""` are deliberately different: no `<answer>` block at all versus
    an empty one are different faults, and collapsing them hides the format
    hypothesis the samples exist to test.
    """
    if ANSWER_OPEN not in text or ANSWER_CLOSE not in text:
        return None
    given = text.split(ANSWER_OPEN, 1)[1].split(ANSWER_CLOSE, 1)[0]
    return " ".join(given.lower().split())


def exact_match_reward(completions: Iterable[Any], answer: Sequence[str], **_: Any) -> list[float]:
    """Binary exact match on the tagged answer. The reward whose geometry is in question.

    Deliberately the same semantics as `ledger/taskset.py:306` -- no judge, no
    partial credit, no substring search over the whole reply, because a reply
    that lists every id would otherwise contain the right one and score 1.0. The
    probe exists to measure *this* reward's group geometry, so any softening here
    would answer a different question with the same money.
    """
    out: list[float] = []
    for completion, expected in zip(completions, answer, strict=True):
        given = extracted_answer(completion_text(completion))
        out.append(float(given is not None and given == expected.lower()))
    return out


def assert_binary_reward(values: Iterable[float]) -> None:
    """The probe's premise: the reward returns 0.0 or 1.0 and nothing between.

    A graded reward makes `zero_advantage_fraction` the wrong model of the
    metric -- groups would stop agreeing by coincidence and start agreeing by
    design -- so the probe would still produce a number, and the number would
    mean something else.
    """
    bad = sorted({v for v in values if v not in (0.0, 1.0)})
    if bad:
        raise AssertionError(
            f"the probe needs a binary reward; got non-binary values {bad}. "
            "zero_advantage_fraction() models p**G + (1-p)**G, which is only the "
            "zero-advantage rate when the reward has exactly two levels."
        )


# ------------------------------------------- what the model actually wrote
#
# Six probe runs have been adjudicated and nobody has read a completion. The last three
# reported reward 0.0 with `frac_reward_zero_std` 1.000, which was read as "the policy
# cannot solve these tasks" -- but it is equally consistent with:
#
#   * output in a shape the reward's extraction does not recover (format fault),
#   * nothing generated at all (generation fault),
#   * the prompt echoed back,
#   * the completion cap cutting the answer off mid-statement.
#
# Four different fixes behind one number, and the aggregate cannot tell them apart. So
# the probe records a few completions beside the metric. These are OBSERVATIONS, never
# criteria: text is evidence for a diagnosis and must not be able to make a probe pass.

SAMPLES_PER_STEP = NUM_GENERATIONS
"""Completions recorded per logged step. Derived from G rather than chosen: TRL lays the
batch out as G consecutive completions per prompt, so the first G are exactly ONE GROUP
-- the unit `frac_reward_zero_std` counts. One group's replies side by side show whether
that group was uniform and why; the same budget scattered across groups shows neither. At
a larger G (the Kaggle run uses 8) it is a prefix of the first group, which is still one
group's text rather than a scatter."""

SAMPLE_CHARS = 600
"""Characters kept per recorded completion. A stated judgement, not a derivation: this is
the budget that still separates the four hypotheses above -- empty output, a prompt echo,
SQL in a shape the extractor misses, a reply cut off mid-statement -- while leaving a
20-step file readable. A sink that swallowed 32 full completions a step would be the same
failure in a new costume: present, unread. The untruncated length travels beside the text
as `chars`, so truncation stays detectable without storing the whole reply."""


def truncated(text: str, budget: int = SAMPLE_CHARS) -> str:
    """`text` cut to `budget` characters, saying in the value how many it dropped.

    The marker is part of the recorded string rather than a separate flag because a
    reader must not be able to mistake a sample this function cut for a model that
    stopped there -- truncation is one of the hypotheses being separated.
    """
    if len(text) <= budget:
        return text
    return text[:budget] + f"...[+{len(text) - budget} chars]"


@dataclass
class CompletionSampler:
    """The step's first few completions, each with what the reward made of it.

    Fed from inside the reward function because that is the only point in the GRPO loop
    where the generated text and the score it received are both in scope. The trainer
    callback sees aggregates only, which is how six runs went by without anyone reading
    a completion.
    """

    extract: Any = extracted_answer
    """The reward's own extraction step -- `extracted_answer` for `--reward exact`,
    `bench.score.extract_sql` for `--reward ex`. See `_extractor_for`."""

    per_step: int = SAMPLES_PER_STEP
    chars: int = SAMPLE_CHARS
    pending: list[dict] = field(default_factory=list)

    def record(self, completions: Iterable[Any], rewards: Sequence[float]) -> None:
        """Keep the first `per_step` completions of the step now in progress.

        Accumulates across calls instead of replacing, because one logged step is
        `gradient_accumulation_steps` reward calls (4 at the probe's G=4, see
        `batch_for`) and replacing would silently record only the last micro-batch.
        """
        for completion, reward in zip(completions, rewards, strict=True):
            if len(self.pending) >= self.per_step:
                return
            text = completion_text(completion)
            extracted = self.extract(text)
            # The extraction gets the same budget as the raw text: `extract_sql`
            # returns the WHOLE reply when it finds no closing fence, which is both
            # the case most worth seeing and the case that would otherwise double
            # the row it is recorded in.
            if isinstance(extracted, str):
                extracted = truncated(extracted, self.chars)
            self.pending.append({
                "chars": len(text),
                "completion": truncated(text, self.chars),
                "extracted": extracted,
                "reward": reward,
            })

    def drain(self) -> list[dict]:
        """Hand this step's samples over and start the next step empty."""
        out, self.pending = self.pending, []
        return out


def sampling_reward(reward: Any, sampler: CompletionSampler) -> Any:
    """`reward`, wrapped so each call records its first few completions.

    Scores are passed through untouched: this adds an observation, it does not soften
    a reward whose geometry is the thing being measured.

    `functools.wraps` is load-bearing rather than tidiness -- TRL names its reward
    columns after `reward_func.__name__` (`rewards/<name>/mean`), so an unnamed
    wrapper would rename the metric a later run is compared against.
    """

    @functools.wraps(reward)
    def sampling(*args: Any, **kwargs: Any) -> list[float]:
        values = reward(*args, **kwargs)
        # TRL calls reward functions by keyword; `train/test_train.py` and the rewards'
        # own docstrings call them positionally. Both are accepted, and neither raises:
        # a diagnostic that could kill the run it is diagnosing is not worth having, and
        # recording nothing is a finding `verdict.observations` reports in words.
        completions = kwargs.get("completions", args[0] if args else ())
        sampler.record(completions, values)
        return values

    return sampling


# ------------------------------------------------------------- the live abort


class DeadGroupAbort(RuntimeError):
    """The probe's ceiling was breached. The run stops here, by design."""


@dataclass
class ProbeMonitor:
    """Per-step adjudication, plus the metrics sink the no-GPU verdict re-reads.

    Separate from the trainer callback so that all of it is testable offline
    against synthetic log dicts -- and separate from `train/verdict.py` so the
    live abort and the after-the-fact re-check cannot drift into disagreeing:
    `verdict.probe_verdict` re-derives the same answer from the file this writes.
    """

    ceiling: float = ABORT_CEILING
    sink: pathlib.Path | None = None
    sampler: CompletionSampler | None = None
    rows: list[dict] = field(default_factory=list)
    aborted: str | None = None

    def header(self, **fields: Any) -> None:
        """Write the provenance row. Call once, before the first step."""
        self._emit(dict(fields))

    def observe(self, log: dict) -> str | None:
        """Record one log row. Returns an abort reason, or `None` to continue.

        Fail-closed on a missing metric. `frac_reward_zero_std` is the probe's
        only instrument: if it is absent, the probe has measured nothing, and a
        run that measured nothing must not read as a clean one. This repo has
        shipped a guard that passed because its target was unreachable; this is
        that shape, and it is the reason the probe is worth running at all.
        """
        is_step = bool(training_steps([log]))
        if is_step and self.sampler is not None:
            # On the step's own row, so one fetched artifact carries the metric and the
            # text it was computed from. Written even when the list is empty: "the
            # reward was never handed a completion" and "sampling was switched off" are
            # different faults and must not look alike in the file.
            log = {**log, COMPLETION_SAMPLES_KEY: self.sampler.drain()}
        self._emit(log)
        if not is_step:
            return None  # the end-of-run summary and eval rows are not steps

        index = len(training_steps(self.rows)) - 1
        value = log.get(ZERO_STD_KEY)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            self.aborted = (
                f"step {index}: {ZERO_STD_KEY} is {value!r}, not a number. The probe's "
                "only instrument is not reporting; this is not a clean probe."
            )
        elif value > self.ceiling:
            self.aborted = (
                f"step {index}: {ZERO_STD_KEY} is {value:.3f}, above the {self.ceiling} "
                f"ceiling (healthy ~{EXPECTED_HEALTHY:.2f} at G={NUM_GENERATIONS}). "
                "Most of the batch yields no gradient. Stop; do not continue to a "
                "training run."
            )
        return self.aborted

    def _emit(self, row: dict) -> None:
        self.rows.append(row)
        if self.sink is not None:
            with self.sink.open("a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")


def make_callback(monitor: ProbeMonitor) -> Any:
    """A `transformers.TrainerCallback` wired to `monitor`. Imports transformers.

    Built here rather than declared as a subclass at module scope so this file
    stays importable with nothing installed -- which is what lets every line of
    `ProbeMonitor` be tested on a laptop.
    """
    from transformers import TrainerCallback  # noqa: PLC0415  (deliberate, see above)

    class _ProbeCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):  # noqa: ANN001
            reason = monitor.observe(dict(logs or {}))
            if reason:
                # Both, not either: `should_training_stop` in case something
                # upstream swallows the exception, and the raise so that nothing
                # downstream can read the run as complete.
                control.should_training_stop = True
                raise DeadGroupAbort(reason)
            return control

    return _ProbeCallback()


# ----------------------------------------------------------------- the config

MODEL = "unsloth/Qwen3-0.6B"
LORA_RANK = 32
BETA = 0.04
"""Not 0. At beta=0 Unsloth's unconditional `kl` logging emits a literal
constant 0.0, which is what made a public 314-step Kaggle run uninformative;
0.04 is what turned that dead channel into Step 2's measurement."""

LEARNING_RATE = 3e-5
"""Garg: lr 1e-4 drives entropy to zero, 3e-5 does not. Step 2 used 3e-5."""

GPU_MEMORY_UTILIZATION = 0.7
"""**Open question, spec §361:** whether this is computed against total or free
VRAM when the trainer already holds 1.39 GB. If total, it needs lowering. The
12.59 GB peak figure assumes 11.2 GB of vLLM against total."""

PROBE_STEPS_MIN, PROBE_STEPS_MAX = 5, 20
""""5-20 steps, aborting" (§279). Fewer than 5 is not a probe; more is a study."""

CHAT_TEMPLATE_KWARGS = {"enable_thinking": False}
"""Passed to `GRPOConfig` by both configs, so the probe and the run generate under the
same template variables.

Qwen3-0.6B's template emits `<|im_start|>assistant\\n` followed by `<think>` unless
this flag is False, in which case it emits a closed empty think block. With thinking
on, the 0.6B model wrote 8,000-13,000 characters of prose reasoning per completion and
never reached its stop token inside the 3,072-token cap: v8 logged `clipped_ratio`
1.000 and `mean_terminated_length` 0.0 for all eight rollouts, which
`mask_truncated_completions=True` then removed from the loss entirely. Reward 0.000,
`frac_reward_zero_std` 1.000, `grad_norm` 0.0 — the same signature as v7, which was
read as a policy finding for six runs.

Shared rather than written twice because a probe that generates differently from the
run measures a different policy's geometry, and the two would drift silently."""

# The template's own wrapper adds a few tokens around the prompt text. No separate
# constant for it: `max_seq_length_for` rounds up to 1024, and the prompt-plus-cap sum
# (2612 + 3072 = 5684) has 460 tokens of headroom before the rounding moves, so a
# wrapper of the size Qwen3's template emits cannot make the sequence length short.
# Carried nowhere as a second number, because a number nothing derives is how 2048 and
# 3072 came to coexist in the first place.


# Groups per step, and why it is a declared quantity rather than whatever TRL defaults
# to. `frac_reward_zero_std` is a FRACTION OVER GROUPS, so the number of groups in a
# step is the metric's resolution. At TRL's default total batch of 8 sequences:
#
#     G=4 -> 2 groups -> the metric can only be 0, 0.5 or 1
#     G=8 -> 1 group  -> the metric can only be 0 or 1
#
# Both were run. v4 (G=4) logged exactly 0.5 then 1.0; v5 (G=8) logged exactly 1.0.
# Neither was measuring a fraction -- with one group the statistic is a Bernoulli draw,
# and comparing it to a 0.60 ceiling compares a single coin flip to its own mean. At
# p=0.0625 a lone group is uniform about 60% of the time, so the probe aborted at the
# rate the configuration predicted *for a healthy run*, and the abort carried no
# information.
#
# A guard whose threshold the metric cannot approach is a guard reporting on an
# unreachable target. MIN_GROUPS_PER_STEP=4 gives five attainable levels (0, .25, .5,
# .75, 1) so 0.60 sits inside the range, and a 1.0 draw at p=0.0625 needs all four
# groups uniform -- probability 0.597**4, about 0.13, instead of 0.60.
# The longest prompt the taskset actually produces, in TOKENS, measured from a run
# rather than estimated. v6's log: `Input IDs of shape (8, 2612) with length 2612 >
# the model's max sequence length of 2048`. BIRD prompts carry a full CREATE-statement
# schema, so they are long by construction.
MEASURED_MAX_PROMPT_TOKENS = 2612

# Unsloth defaults `max_seq_length` to 2048 and the probe never set it, so the context
# was SMALLER THAN THE PROMPT. Three symptoms, one cause:
#
#   - the prompt filled all 2048 and overflowed, leaving no room to generate into
#   - completions came back empty or instantly truncated, so reward was 0.0 and
#     `frac_reward_zero_std` 1.0 on every step of every run
#   - `mask_truncated_completions=True` then masked all of them, which is why
#     `grad_norm` logged 0.0 in six consecutive runs and nobody could explain it
#
# `max_completion_length` was simultaneously set to 3072 -- LARGER than the model's
# entire context. That pair cannot both be satisfied, and nothing checked it. The
# completion cap and the sequence length were chosen in different places by different
# reasoning and never multiplied together.
#
# Qwen3-0.6B supports far more natively, so the ceiling here is VRAM, not the model.
def max_seq_length_for(completion_cap_tokens: int,
                       prompt_tokens: int = MEASURED_MAX_PROMPT_TOKENS) -> int:
    """Context that fits the longest prompt AND a full-length completion.

    Derived, and rounded up to a multiple of 1024 because attention kernels prefer it.
    Returned by a function rather than stored as a constant so it cannot drift out of
    step with the cap it has to accommodate -- which is exactly how 2048 and 3072 came
    to coexist.
    """
    need = prompt_tokens + completion_cap_tokens
    return -(-need // 1024) * 1024


MIN_GROUPS_PER_STEP = 4
GROUPS_PER_STEP = 4


def batch_for(g: int, groups: int = GROUPS_PER_STEP) -> tuple[int, int]:
    """(per_device_train_batch_size, gradient_accumulation_steps) for `groups` groups.

    Returned as a pair and derived from G rather than written as two constants,
    because the invariant is their PRODUCT divided by G and two independent numbers
    cannot carry an invariant between them.
    """
    if groups < MIN_GROUPS_PER_STEP:
        raise ValueError(
            f"{groups} groups per step gives the metric {groups + 1} attainable "
            f"levels; the {ABORT_CEILING} ceiling needs at least "
            f"{MIN_GROUPS_PER_STEP}, or the comparison is a coin flip against its "
            "own mean"
        )
    total = g * groups
    # One optimiser step per logged step, so accumulation carries the whole batch
    # when it will not fit on the card at once. 8 sequences per forward is what the
    # T4 ran at a 3,072-token completion cap.
    per_device = min(8, total)
    accum = total // per_device
    return per_device, accum


def probe_config(steps: int = PROBE_STEPS_MAX, g: int = NUM_GENERATIONS) -> dict[str, Any]:
    """`GRPOConfig` kwargs for the probe. Pure data, so it is checkable offline.

    `vllm_mode` is written out rather than inherited **because its default flips
    inside the version range this project has used**: `"colocate"` at trl 1.13.0,
    `"server"` at 0.24.0, where server mode brings its two-device requirement.
    Same source, different topology, no error (spec §88).
    """
    from train.guards import completion_cap  # local: keeps the import graph acyclic

    if not PROBE_STEPS_MIN <= steps <= PROBE_STEPS_MAX:
        raise ValueError(
            f"probe is {PROBE_STEPS_MIN}-{PROBE_STEPS_MAX} steps, got {steps}; "
            "fewer is not a probe and more is a study the spec does not authorise"
        )
    cap = completion_cap(("ptc",))
    per_device, accum = batch_for(g)
    return {
        "max_steps": steps,
        "num_generations": g,
        "per_device_train_batch_size": per_device,
        "gradient_accumulation_steps": accum,
        "max_completion_length": cap.value,
        "mask_truncated_completions": True,
        # Qwen3's template opens a `<think>` block unless this is False, and the
        # template is where it is read: `{%- if enable_thinking is defined and
        # enable_thinking is false %}` injects an empty closed think block. Left at
        # the default the model reasons inside the block, never reaches its stop
        # token inside the cap, and every rollout is masked -- v8's failure.
        "chat_template_kwargs": dict(CHAT_TEMPLATE_KWARGS),
        "beta": BETA,
        "learning_rate": LEARNING_RATE,
        "fp16": True,
        "bf16": False,
        "use_vllm": True,
        "vllm_mode": "colocate",
        "vllm_gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "logging_steps": 1,
        "save_strategy": "no",
        "report_to": "none",
        "num_iterations": 1,
    }


def probe_expectations(g: int = NUM_GENERATIONS) -> dict[str, Any]:
    """Everything the probe predicts, derived. For the dry run and the header."""
    band = viable_band(g)
    return {
        "p_reference": SOLVE_RATE,
        "p_reference_source": f"run 3d PTC, {SOLVED}/{ROLLOUTS}, deepseek-v4-flash",
        "num_generations": g,
        "expected_frac_reward_zero_std": zero_advantage_fraction(SOLVE_RATE, g),
        "abort_ceiling": ABORT_CEILING,
        "abort_form": "any step (spec §282); §240 says 10 consecutive -- see train/verdict.py",
        "viable_solve_rate_band": band,
        "weak_tail": {
            "p": WEAK_TAIL_P,
            "g": 8,
            "frac": zero_advantage_fraction(WEAK_TAIL_P, 8),
            "note": "both tails degenerate; a weak policy is worse than a strong one",
        },
        "by_group_size": expectation_table(SOLVE_RATE),
    }


# ---------------------------------------------------------------------- main


def load_prompts(path: pathlib.Path) -> list[dict[str, Any]]:
    """`{"prompt": ..., "answer": ...}` per line. Both required, both non-empty.

    **`prompt` is rendered as a one-message conversation, not left as a string.**
    TRL only applies the chat template to conversational prompts; a bare string is
    tokenized verbatim, so the `<|im_start|>assistant` generation prompt is never
    emitted and the model is never told it is the assistant. v8 measured the cost of
    that: `completions/clipped_ratio` 1.000, `mean_length == max_length == 3072`,
    `mean_terminated_length` 0.0, every rollout masked, reward never exercised, and
    four sampled replies that each echoed the schema and then kept writing past the
    cap. The model could not emit a stop token because the template's stop token was
    never in play. Rendering the conversation is what makes `enable_thinking: False`
    in `probe_config` reachable at all, since that flag is a template variable.
    """
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [k for k in ("prompt", "answer") if not str(row.get(k) or "").strip()]
        if missing:
            raise ValueError(f"{path}:{n} is missing {', '.join(missing)}")
        # Extra columns are preserved, not dropped. TRL passes every dataset column
        # into the reward as a kwarg, and the execution reward needs `db_id` to find
        # the database. Dropping them here is what forced `answer` to carry a baked
        # scalar in the first place, and that is the design that read 1.000.
        kept = {
            "prompt": [{"role": "user", "content": row["prompt"]}],
            "answer": row["answer"],
        }
        for extra in ("db_id",):
            if row.get(extra):
                kept[extra] = row[extra]
        rows.append(kept)
    if not rows:
        raise ValueError(f"{path} has no prompts")
    return rows


def build_parser():
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--prompts", type=pathlib.Path, required=True,
                   help="JSONL of {prompt, answer}. The probe's realised number is a "
                        "property of this file as much as of the policy.")
    p.add_argument("--taskset-id", required=True,
                   help="What the prompts are, recorded in the metrics header. Mandatory: "
                        "a zero-advantage fraction quoted without its taskset is the "
                        "$0.0071 fault again.")
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("probe_metrics.jsonl"))
    p.add_argument("--steps", type=int, default=PROBE_STEPS_MAX)
    p.add_argument("--generations", type=int, default=NUM_GENERATIONS,
                   help="GRPO group size G. Default is the spec's 4. **Raising it is "
                        "how a measured solve rate below the viable band is answered**: "
                        "the band widens with G, so the first real run (p about 0.063 "
                        "to 0.069 measured) sits OUTSIDE (0.120, 0.880) at G=4 and "
                        "inside (0.062, 0.938) at G=8. Recorded in the header -- a "
                        "zero-advantage fraction quoted without its G is meaningless, "
                        "since G is half of what the metric is a function of.")
    p.add_argument("--reward", choices=("exact", "ex"), default="exact",
                   help="`exact`: binary string match on a tagged <answer> block, for "
                        "a self-contained task. `ex`: execution accuracy -- the model "
                        "writes SQL, the database executes it, result sets are "
                        "compared. Use `ex` for BIRD: the first real run proved the "
                        "scalar-answer prompts were unanswerable (schema but no rows), "
                        "so the solve rate was structurally 0 and the probe read 1.000 "
                        "and aborted on its own prompt design.")
    p.add_argument("--db-root", type=pathlib.Path, default=None,
                   help="Required with --reward ex. Holds dev_databases/<db_id>/. On "
                        "Kaggle this is the mounted dataset directory.")
    p.add_argument("--no-completion-samples", action="store_true",
                   help=f"Stop recording the first {SAMPLES_PER_STEP} completions of "
                        "each step into --out. Sampling is ON by default and this flag "
                        "is the only way off, because six probe runs were adjudicated "
                        "from aggregate metrics with nobody reading a completion: the "
                        "default must not depend on someone remembering to ask, so "
                        "switching it off is the deliberate act.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the config, the derived expectations and the resolved "
                        "stack, then exit. No GPU, no model download, no cost.")
    return p


def _extractor_for(args: Any) -> Any:
    """The scoring step's own extraction, so a sample shows what the reward read.

    Not a reimplementation of it: `extracted_answer` is the function
    `exact_match_reward` compares with, and `bench.score.extract_sql` is the one
    `train/ex_reward.py` hands the database. The gap between the raw text and this
    value is the hypothesis under test, and it is only a measurement of the reward if
    it is literally the reward's own step.
    """
    if args.reward == "exact":
        return extracted_answer
    from bench.score import extract_sql  # noqa: PLC0415
    return extract_sql


def _reward_for(args: Any) -> Any:
    """Pick the reward, and record which one in the metrics header.

    Both are binary, so `assert_binary_reward` and `zero_advantage_fraction`'s
    `p**G + (1-p)**G` model hold either way. Which one ran is not a detail: a
    zero-advantage fraction quoted without its reward is the same class of fault as one
    quoted without its taskset.
    """
    if args.reward == "exact":
        return exact_match_reward
    from train.ex_reward import make_execution_reward  # noqa: PLC0415
    return make_execution_reward(args.db_root)


def main(argv: Sequence[str] | None = None) -> int:
    from train.guards import check_stack, require_stack, resolved_versions

    args = build_parser().parse_args(argv)
    if args.reward == "ex" and args.db_root is None:
        raise SystemExit("--reward ex needs --db-root: without the databases the "
                         "reward cannot execute anything, and a reward that cannot "
                         "score is indistinguishable from a policy that cannot answer")
    config = probe_config(args.steps, args.generations)
    expectations = probe_expectations(args.generations)
    prompts = load_prompts(args.prompts)

    if args.dry_run:
        print(json.dumps({
            "config": config,
            "expectations": expectations,
            "prompts": len(prompts),
            "taskset_id": args.taskset_id,
            "reward": args.reward,
            "completion_sampling": (None if args.no_completion_samples else
                                    {"per_step": SAMPLES_PER_STEP, "chars": SAMPLE_CHARS}),
            "resolved_stack": resolved_versions(),
            "stack_faults": check_stack(resolved_versions()),
        }, indent=2, default=str))
        return 0

    require_stack()  # before the model download, not after

    # UNVERIFIED BELOW THIS LINE. Nothing in this project has run on trl 1.13.0,
    # and whether Unsloth's fp16-on-Turing work still applies there is the single
    # largest unverified assumption in the spec (§51). The call shapes come from
    # reading the library, not from a run.
    from unsloth import FastLanguageModel  # noqa: PLC0415
    from datasets import Dataset  # noqa: PLC0415
    from trl import GRPOConfig, GRPOTrainer  # noqa: PLC0415

    # `max_seq_length` is passed explicitly. Omitting it took unsloth's default of
    # 2048, which is smaller than this taskset's longest prompt (2612 measured), so
    # the prompt consumed the whole context and left nothing to generate into.
    seq_len = max_seq_length_for(config["max_completion_length"])
    print(f"max_seq_length={seq_len} "
          f"(prompt<={MEASURED_MAX_PROMPT_TOKENS} + completion "
          f"{config['max_completion_length']})", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL, load_in_4bit=False, fast_inference=True,
        max_seq_length=seq_len,
        max_lora_rank=LORA_RANK, gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
    )
    model = FastLanguageModel.get_peft_model(model, r=LORA_RANK, lora_alpha=LORA_RANK)

    sampler = (None if args.no_completion_samples
               else CompletionSampler(extract=_extractor_for(args)))
    reward = _reward_for(args)
    if sampler is not None:
        reward = sampling_reward(reward, sampler)

    monitor = ProbeMonitor(sink=args.out, sampler=sampler)
    monitor.header(
        probe="dead_group",
        taskset_id=args.taskset_id,
        prompts=len(prompts),
        config=config,
        expectations=expectations,
        resolved_stack=resolved_versions(),
        # Provenance for the samples themselves: what was recorded, how much of it, and
        # through which extraction. A sample quoted without its budget invites the same
        # mistake as a zero-advantage fraction quoted without its taskset. Deliberately
        # NOT `verdict.COMPLETION_SAMPLES_KEY`: that key means "this step's completions"
        # on every row that carries it, and one key holding a settings dict on the header
        # and a list of text everywhere else is how a reader or a parser gets it wrong.
        completion_sampling=None if sampler is None else {
            "per_step": sampler.per_step,
            "chars": sampler.chars,
            "extract": getattr(sampler.extract, "__name__", str(sampler.extract)),
        },
    )

    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=[reward],
        args=GRPOConfig(**config, output_dir="probe_out"),
        train_dataset=Dataset.from_list(prompts),
        callbacks=[make_callback(monitor)],
    )
    try:
        trainer.train()
    except DeadGroupAbort as abort:
        print(f"PROBE ABORT\n  - {abort}")
        return 1
    print("probe completed; re-check with: python train/verdict.py", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
