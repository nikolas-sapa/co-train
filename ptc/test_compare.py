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
        max_turns=80, rollout_timeout=900)


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
