"""The arm plan — the one part of `compare.py` that decides what gets billed.

`compare.py` was untested: 104 tests across `ptc/` and none touched the arm loop.
That is how a real-mode control survived as a relabelled duplicate of its tool arm.
"""

import argparse
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ptc_compare", Path(__file__).with_name("compare.py"))
compare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare)


def _args(mode):
    return argparse.Namespace(
        mode=mode, taskset="glossary", model="m", base_url="http://127.0.0.1:1/v1",
        key_var="OPENAI_API_KEY", num_tasks=5, output_dir="~/scratch/x",
        arms="bash,ptc", price_in=0.0, price_out=0.0, price_cached=None,
        max_turns=80, rollout_timeout=900, max_concurrent=None, max_retries=0)


def test_real_mode_runs_no_control_arm():
    """A real control is its tool arm relabelled, so it is a second invoice for a
    duplicate measurement. Billed work must not be ordered by accident."""
    assert compare._arm_plan("real", "bash,ptc") == [("bash", True), ("ptc", True)]


def test_canned_mode_keeps_both_controls_and_the_table_order():
    """Canned is where the control is real -- `_canned_policy` refuses the tool
    channel -- and it is what establishes that the grader requires tool use."""
    assert compare._arm_plan("canned", "bash,ptc") == [
        ("bash", True), ("bash", False), ("ptc", True), ("ptc", False)]


def test_the_config_is_blind_to_whether_an_arm_is_a_control():
    """The reason the plan has to drop the control, asserted rather than described.

    If someone later builds a genuine toolless control, this test goes red and tells
    them `_arm_plan` is now wrong -- which is the only way that change stays honest.
    """
    for arm in ("bash", "ptc"):
        tool = compare._config(arm, _args("real"), "tag-tool")
        control = compare._config(arm, _args("real"), "tag-control")
        tool["run"]["dir"] = control["run"]["dir"] = "<normalised>"
        assert tool == control, f"{arm}: _config now distinguishes a control"


def test_a_single_arm_still_plans_cleanly():
    assert compare._arm_plan("real", "ptc") == [("ptc", True)]
    assert compare._arm_plan("canned", "ptc") == [("ptc", True), ("ptc", False)]


def test_an_errored_run_is_announced_not_averaged():
    """A dead endpoint produces a table of zeros indistinguishable from a model that
    solved nothing. The probe that found this ran against a closed port and exited 0."""
    from ptc.metrics import ArmResult, render

    bad = ArmResult(arm="bash", taskset="glossary", n_tasks=1)
    bad.stop_conditions = {"error": 1}
    out = render([bad])
    assert "ROLLOUTS ERRORED" in out, out
    assert "bash 1" in out


def test_a_clean_run_carries_no_error_banner():
    """The banner has to be absent when it should be, or it is decoration."""
    from ptc.metrics import ArmResult, render

    ok = ArmResult(arm="bash", taskset="glossary", n_tasks=1)
    ok.stop_conditions = {"agent_completed": 1}
    assert "ROLLOUTS ERRORED" not in render([ok])


def test_the_configured_turn_budget_reaches_the_ptc_harness():
    """`PTCHarnessConfig.max_turns` shadows the agent-level budget and defaults to 8,
    so setting only `agent["max_turns"]` left the PTC arm at 8 programs while `bash`
    spent up to 44 turns on the same tier -- the turn budget becoming the independent
    variable. Asserted by BUILDING the harness config rather than reading the dict
    back: the right value under a name the harness never reads would satisfy a weaker
    check, which is exactly how this survived the 4 -> 80 raise."""
    from ptc.harness import PTCHarnessConfig

    harness = compare._config("ptc", _args("real"), "t")["env"]["agent"]["harness"]
    assert PTCHarnessConfig(**harness).max_turns == 80


def test_invariant_no_second_turn_cap_exists_on_the_bash_path():
    """NOT a regression test — it passes against the pre-fix code too, so it proves
    nothing about the PTC propagation fix and must not be read as cover for it.

    It is a forward-looking invariant: it records WHY the fix above is PTC-only. Nothing
    in the bash path declares its own `max_turns`, so bash reads the agent-level budget
    already. If a future `HarnessConfig` grows one, bash silently acquires the same
    shadowing bug and this goes red, which is the only moment the assertion is useful.
    """
    from verifiers.v1.configs.harness import HarnessConfig

    agent = compare._config("bash", _args("real"), "t")["env"]["agent"]
    assert agent["max_turns"] == 80
    assert "max_turns" not in HarnessConfig.model_fields


# ------------------------------------------- the two flags that bill, not measure
#
# These are measurement POLICY, not instrument: widening either one changes what the
# numbers mean. They had no tests at all, so a later blanket retry would pass silently.


def test_the_retry_policy_is_restricted_to_provider_errors_exactly():
    """Pinned as exact equality, deliberately. A retry that is not scoped to transport
    faults re-runs rollouts that SHOULD score 0.0 -- a harness or sandbox fault is a
    real result, and retrying it until it passes is the rig grading itself. Widening
    `include`, or dropping it for a blanket retry, must fail here rather than quietly
    change the experiment.

    Widened once, on purpose, and this docstring is the record of why (defect 6): the
    arms name the same transport fault differently. PTC owns its HTTP client so a relay
    timeout is a `ProviderError`; the bash arm's bundled runtime raises
    `openai.APIError: The request timed out` in a subprocess and the rig re-wraps it as
    `HarnessError`. With only `ProviderError` retryable, a 429 on one task was survivable
    and an identical timeout on another was fatal -- for bash, on `richest-owner`, its
    heaviest task. A deterministic harness fault still ends red after exhausting retries,
    which is what the original scoping was protecting. Any FURTHER widening must fail
    here."""
    cfg = compare._config("ptc", _args("real"), "t")
    assert "retries" not in cfg["env"], "retries must stay off unless asked for"

    args = _args("real")
    args.max_retries = 3
    assert compare._config("ptc", args, "t")["env"]["retries"] == {
        "max_retries": 3, "include": ["ProviderError", "HarnessError"],
    }


def test_the_rollout_fan_out_can_be_held_below_a_provider_limit():
    """`max_concurrent` was hardwired to `--num-tasks`, so scaling the measurement
    scaled the request rate with it and a 4-concurrent endpoint answered 429 on 23 of
    28 rollouts. Unset must keep the old behaviour; set must win."""
    args = _args("real")
    assert compare._config("ptc", args, "t")["max_concurrent"] == args.num_tasks

    args.max_concurrent = 1
    assert compare._config("ptc", args, "t")["max_concurrent"] == 1
