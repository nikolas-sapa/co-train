"""The GRPO co-training pipeline for the PTC arm. **Gated, and the gate is shut.**

`docs/spec-cotrain.md` is explicit that this must not be built first (§328-342):

> A mis-built pipeline normally announces itself as "no training effect". If the
> benchmark cannot show a training effect even when the pipeline is *correct*,
> then broken and working produce identical output -- so the eval is not merely
> what the pipeline feeds, it is **the only instrument that could validate it**.

So this file lands as code with its guards live and its gate closed. Calling
`preflight()` -- which `main()` does before anything costs money -- raises
`PreconditionUnmet` until the blocking requirement of §344 is satisfied: a
taskset whose tasks sit near a 0.6B model's frontier, declared in
`bench/frontier/manifest.json`, with a *signed* pre-registration amendment.

**Status of each part, stated because the parts differ:**

| part | status |
|---|---|
| `preflight` and everything in `train/guards.py` | implemented, tested offline, fails red |
| `training_config` | implemented, tested offline |
| `PTCEnvironment` turn budget and refusal | implemented, tested offline |
| `sql_environment` | task-bound execution seam only; no TRL integration |
| `step_zero_tool_success` | implemented, tested offline |
| `model_spec` / `training_config` call shapes | **read from library source, never run** |
| the taskset, its catalog, the dataset loader | not built; the frontier taskset's deliverable |

Nothing in this project has executed on trl 1.13.0. Whether Unsloth's
fp16-on-Turing work still applies there is the single largest unverified
assumption in the spec (§51).
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

if __package__ in (None, ""):  # invoked as `python train/<file>.py`, not `-m`
    import pathlib as _pathlib
    import sys as _sys

    _sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from train.dead_group_probe import (
    BETA,
    CHAT_TEMPLATE_KWARGS,
    GPU_MEMORY_UTILIZATION,
    LEARNING_RATE,
    LORA_RANK,
    MODEL,
    NUM_GENERATIONS,
    exact_match_reward,
)
from train.guards import (
    REPO_ROOT,
    InvariantViolation,
    TurnBudget,
    assert_cap,
    assert_one_tool,
    assert_turn_budget,
    completion_cap,
    eval_max_turns,
    module_literal,
    require_frontier_taskset,
    require_stack,
    resolved_versions,
)

# -------------------------------------------------------- the one tool, again

THE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_program",
        "description": "Execute a Python program against the typed catalog.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "The program."}},
            "required": ["code"],
        },
    },
}
"""The schema TRL registers. Deliberately the same single tool `ptc/harness.py`
exposes to the eval arm, and deliberately **not** a list that anything else can
append to: the catalog reaches the model through `ptc.runtime.Catalog` plus
prompt text, never as sibling tool schemas. `test_train.py` checks this schema's
name against the one parsed out of `ptc/harness.py`, so the two arms cannot drift
into offering different tools."""


# ------------------------------------------------------------- the environment


@dataclass
class PTCEnvironment:
    """Per-rollout state handed out by the `environment_factory`.

    This exists because trl's `_tool_call_loop` is `while idxs_with_tool:` whose
    only exit is "all overlong", and `tool_call_count` is a logging counter, not
    a limit (measured). The turn budget has to live here, per rollout -- which is
    why the pipeline needs trl 1.13.0 and not 0.26 -- and running out has to
    return a refusal the model reads rather than a hang.

    `turns_used` is recorded per rollout and reported separately from H4 on
    purpose: mode 3's signature lives in turn counts, and H4's own response to it
    is sign-indeterminate (§238).
    """

    max_turns: int
    tools: tuple[dict, ...] = (THE_TOOL_SCHEMA,)
    budget: TurnBudget = field(init=False)
    _executor: Callable[[str], str] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.budget = TurnBudget(max_turns=self.max_turns)
        assert_one_tool(self.tools)

    @property
    def turns_used(self) -> int:
        return self.budget.used

    def exhausted_message(self) -> str:
        return self.budget.exhausted_message()

    def step(self, code: str) -> str:
        """Spend a turn before dispatching to an explicitly task-bound executor.

        Unbound environments still raise rather than returning plausible output.
        This seam does not wire TRL rollouts, model calls or training.
        """
        refusal = self.budget.consume()
        if refusal is not None:
            return refusal
        if self._executor is None:
            raise NotImplementedError(
                "program execution has no task-bound executor (spec §344). "
                "See preflight()."
            )
        return self._executor(code)


def environment_factory(root: pathlib.Path = REPO_ROOT):
    """A zero-argument factory, which is the shape trl 1.13.0 expects.

    The budget is read from `ptc/harness.py` at factory-build time rather than
    passed in, so the trained arm cannot be given a different turn budget from
    the eval arm by a caller that means well.
    """
    max_turns = eval_max_turns(root)

    def factory() -> PTCEnvironment:
        return PTCEnvironment(max_turns=max_turns)

    return factory


def sql_environment(
    task: Any, root: pathlib.Path = REPO_ROOT,
) -> tuple[str, PTCEnvironment]:
    """Bind one SqlTask to a fresh environment and its existing PTC-arm prompt.

    Only the arm's prompt and the existing single program-tool schema are exposed;
    the gold query is not a model input. Imports stay local so the unbound factory
    and preflight need neither SQL-arm execution nor any training framework.
    """
    from ptc.sql_arms import Budget, build_sql_arms

    max_turns = eval_max_turns(root)
    pair = build_sql_arms(task, budget=Budget(max_turns=max_turns))

    def execute(code: str) -> str:
        return pair.run("ptc", code)

    return pair.prompt("ptc"), PTCEnvironment(max_turns=max_turns, _executor=execute)


# ------------------------------------------------------------------- config

TRAINED_ARMS_DEFAULT = ("ptc",)
"""What the project was designed to do. Two arms is a different experiment with a
different cap -- see `training_config`."""


def training_config(
    arms: Sequence[str] = TRAINED_ARMS_DEFAULT, steps: int = 200
) -> dict[str, Any]:
    """`GRPOConfig` kwargs for a co-training run. Pure data, checkable offline.

    `max_completion_length` comes from `completion_cap(arms)` and is validated
    against those same arms, so the cap can never be read without its condition:
    3,072 for the PTC arm alone, 4,258 when two arms are compared, and no way to
    get either number without saying which experiment you are running.

    `vllm_mode` is written out rather than inherited **because its default flips
    inside the version range this project has used**: `"colocate"` at trl 1.13.0,
    `"server"` at 0.24.0, and server mode brings a two-device requirement. Same
    source, different topology, no error (§88).
    """
    cap = completion_cap(arms)
    assert_cap(cap, arms)
    return {
        "max_steps": steps,
        "num_generations": NUM_GENERATIONS,
        "max_completion_length": cap.value,
        "mask_truncated_completions": True,
        # Shared with the probe by import, not by convention: a run that generates
        # with thinking on while the probe measured with it off is the same class of
        # fault as two arms under two different caps.
        "chat_template_kwargs": dict(CHAT_TEMPLATE_KWARGS),
        "beta": BETA,
        "learning_rate": LEARNING_RATE,
        "fp16": True,
        "bf16": False,
        "use_vllm": True,
        "vllm_mode": "colocate",
        "vllm_gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "logging_steps": 1,
        "report_to": "none",
        "num_iterations": 1,
    }


# ------------------------------- the cheap validation that does not need the eval


def step_zero_tool_success(
    tool_calls: int, tool_failures: int, root: pathlib.Path = REPO_ROOT
) -> str | None:
    """A warning string when step 0's tool-call success rate is a floor artifact.

    "Record tool-call success at step 0 before the first gradient step -- a
    flipped arm reads 1.000 immediately, from one generation pass, with no
    training and no working benchmark" (§238). This is the cheapest check in the
    project and the only one that catches invariant 1 empirically.

    `tool_success_rate = 1.0 - tool_failures / tool_calls`, and a failure is a
    result whose text starts with one of `ptc.metrics.FAILURE_PREFIXES` -- strings
    only `ptc/harness.py` emits. A flipped arm has no PTC harness in the loop, so
    `_is_failure` can never match, failures are 0, and the rate is pinned at
    exactly 1.000 independent of how badly the model performs. Measured, not
    hypothetical: run 3d's bash arm is 0 failures in 822 calls.

    The threshold is `ptc.metrics.MIN_CALLS_FOR_PERFECT_RATE`, read from that
    file so the two cannot disagree.
    """
    minimum = module_literal("ptc/metrics.py", "MIN_CALLS_FOR_PERFECT_RATE", root)
    if tool_calls >= minimum and tool_failures == 0:
        return (
            f"step 0: {tool_calls} tool calls, 0 detected failures, so "
            f"tool_success_rate is exactly 1.000 over at least {minimum} calls. On "
            "the PTC arm that is a floor artifact, not a performance figure: it is "
            "what a flipped arm reads, because ledger's tools return JSON or null "
            "and can never match ptc.metrics' failure predicate. Check invariant 1 "
            "before reading this as a result -- H4 would score it as a spectacular "
            "confirmation of a prediction signed in advance."
        )
    return None


# ----------------------------------------------------------------- preflight


def preflight(
    arms: Sequence[str] = TRAINED_ARMS_DEFAULT,
    root: pathlib.Path = REPO_ROOT,
    versions: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Every guard, in the order that fails cheapest first. Raises; returns the config.

    1. the §344 gate -- no GPU, no download, no money; shut today
    2. the resolved stack -- below the unsloth floor is a different experiment
    3. invariant 1 -- exactly one registered tool
    4. invariant 2 -- one cap per experiment, bound to its arms
    5. invariant 3 -- `max_turns` reaches the trained arm, and runs out loud
    """
    require_frontier_taskset(root)
    require_stack(versions)

    config = training_config(arms)
    environment = environment_factory(root)()
    assert_one_tool(environment.tools)
    assert_turn_budget(environment, root)

    cap = completion_cap(arms)
    assert_cap(cap, arms)
    if config["max_completion_length"] != cap.value:
        raise InvariantViolation(
            f"invariant 2: config cap {config['max_completion_length']} is not the "
            f"cap derived for {sorted(arms)} ({cap})"
        )
    return config


def model_spec() -> dict[str, Any]:
    """`FastLanguageModel` kwargs. Pure data, so the stack choices are checkable offline.

    `load_in_4bit=False` and fp16 are not a T4 workaround. arXiv:2510.26788
    measures bf16's training-inference mismatch at **~24x fp16's**, because
    sampling (vLLM) and training are two kernel paths and bf16's 7 mantissa bits
    cannot absorb their disagreement -- and it worsens with response length,
    which is this project's worst case at p95 2,560 tokens over 6.38 turns. Step
    2's stability result is corroboration, not the reason. On a future L4/A100,
    bf16 is a downgrade to be tested, never a default upgrade.
    """
    return {
        "model_name": MODEL,
        "load_in_4bit": False,
        "fast_inference": True,
        "max_lora_rank": LORA_RANK,
        "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "lora_rank": LORA_RANK,
        "reward_funcs": [exact_match_reward.__name__],
    }


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arms", nargs="+", default=list(TRAINED_ARMS_DEFAULT),
                        help="which arms are TRAINED. Decides the completion cap; "
                             "two arms is a different experiment.")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--preflight-only", action="store_true",
                        help="run every guard and print the config. No GPU, no cost.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = preflight(args.arms)  # raises PreconditionUnmet today, by design

    if args.preflight_only:
        print(json.dumps(
            {"config": config, "model": model_spec(), "arms": sorted(args.arms),
             "resolved_stack": resolved_versions()}, indent=2, default=str))
        return 0

    # No model is loaded above this line on purpose. Loading Qwen3-0.6B and then
    # refusing would spend the download and the session to arrive at the same
    # answer preflight() already gave for free.
    raise NotImplementedError(
        "the taskset, its catalog and the dataset loader are the frontier taskset's "
        "deliverable (spec §344), and the trl 1.13.0 rollout seam has never been "
        "executed. preflight() refuses above; this line exists so that removing the "
        "gate cannot silently produce a run. The trainer call shape is documented in "
        "docs/train-notes.md, read from library source rather than from a run."
    )


if __name__ == "__main__":
    raise SystemExit(main())
