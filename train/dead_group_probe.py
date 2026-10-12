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

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):  # invoked as `python train/<file>.py`, not `-m`
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from train.verdict import ZERO_STD_CEILING, ZERO_STD_KEY, training_steps

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
        text = completion if isinstance(completion, str) else completion[-1]["content"]
        if ANSWER_OPEN not in text or ANSWER_CLOSE not in text:
            out.append(0.0)
            continue
        given = text.split(ANSWER_OPEN, 1)[1].split(ANSWER_CLOSE, 1)[0]
        out.append(float(" ".join(given.lower().split()) == expected.lower()))
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
        self._emit(log)
        if not training_steps([log]):
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


def probe_config(steps: int = PROBE_STEPS_MAX) -> dict[str, Any]:
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
    return {
        "max_steps": steps,
        "num_generations": NUM_GENERATIONS,
        "max_completion_length": cap.value,
        "mask_truncated_completions": True,
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


def load_prompts(path: pathlib.Path) -> list[dict[str, str]]:
    """`{"prompt": ..., "answer": ...}` per line. Both required, both non-empty."""
    rows: list[dict[str, str]] = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [k for k in ("prompt", "answer") if not str(row.get(k) or "").strip()]
        if missing:
            raise ValueError(f"{path}:{n} is missing {', '.join(missing)}")
        rows.append({"prompt": row["prompt"], "answer": row["answer"]})
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
    p.add_argument("--dry-run", action="store_true",
                   help="Print the config, the derived expectations and the resolved "
                        "stack, then exit. No GPU, no model download, no cost.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    from train.guards import check_stack, require_stack, resolved_versions

    args = build_parser().parse_args(argv)
    config = probe_config(args.steps)
    expectations = probe_expectations()
    prompts = load_prompts(args.prompts)

    if args.dry_run:
        print(json.dumps({
            "config": config,
            "expectations": expectations,
            "prompts": len(prompts),
            "taskset_id": args.taskset_id,
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

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL, load_in_4bit=False, fast_inference=True,
        max_lora_rank=LORA_RANK, gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
    )
    model = FastLanguageModel.get_peft_model(model, r=LORA_RANK, lora_alpha=LORA_RANK)

    monitor = ProbeMonitor(sink=args.out)
    monitor.header(
        probe="dead_group",
        taskset_id=args.taskset_id,
        prompts=len(prompts),
        config=config,
        expectations=expectations,
        resolved_stack=resolved_versions(),
    )

    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=[exact_match_reward],
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
