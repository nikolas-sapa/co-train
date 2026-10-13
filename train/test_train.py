"""Offline tests for the training lane. No GPU, no model download, no network.

Every fixture here is synthetic. The training stack is not installed on this
machine -- `trl`, `unsloth` and `torch` all resolve to absent -- and that is a
feature of these tests rather than a limitation: the guards have to reject
exactly that environment, and `check_stack` is handed synthetic version sets
because the one real version set available is the broken one.

Numbers are derived, never typed in, following `tests/test_defect_ledger.py`.
The spec's published percentages appear only as the *expected output* of a
derivation, so a changed derivation fails rather than agreeing with itself.

**Every guard in here has been seen red.** `train/mutate.py` breaks each guard
in a fresh copy of the tree and records which test dies; `train/README.md` has
the table. A green test whose target was never broken is the shape this repo
keeps finding.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

from train import dead_group_probe as probe  # noqa: E402
from train import grpo_ptc, guards  # noqa: E402
from train import verdict as V  # noqa: E402

REPO = guards.REPO_ROOT

GOOD_STACK = {"unsloth": "2026.10.3", "trl": "1.13.0", "transformers": "4.57.6"}


# ----------------------------------------------------------------- fixtures


def step(zero_std: float | None = None, **extra) -> dict:
    """One training-step log row. "loss" is what makes it a step."""
    row = {"loss": 0.01, "grad_norm": 1.8, "reward_std": 0.1}
    if zero_std is not None:
        row[V.ZERO_STD_KEY] = zero_std
    return {**row, **extra}


def probe_log(values, taskset_id: str = "ledger-v3") -> list[dict]:
    """A probe metrics file: one provenance header, then one row per step."""
    head = [{"probe": "dead_group", "taskset_id": taskset_id}] if taskset_id is not None else []
    return head + [step(v) for v in values]


def write_manifest(root: pathlib.Path, manifest, amendment_line: str | None) -> pathlib.Path:
    (root / "bench" / "frontier").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    target = root / guards.FRONTIER_MANIFEST
    target.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest))
    (root / "docs" / "pre-registration.md").write_text(amendment_line or "# no amendments\n")
    return target


GOOD_MANIFEST = {
    "policy": "unsloth/Qwen3-0.6B",
    "pre_registration_amendment": "A8",
    "n_tasks": 198,
    "solve_rate_min": 0.2,
    "solve_rate_max": 0.8,
    # `measurement` became required when the first four keys turned out to be
    # conformant by construction. This fixture was not updated in the same change, so
    # three gate tests were left failing; they are the tests that assert the gate
    # OPENS, which is the direction a half-finished guard breaks silently in -- a gate
    # stuck shut looks exactly like a gate doing its job.
    "measurement": {
        "g": 4,
        "dead_ceiling": 0.60,
        "trainable_band": [0.119964, 0.880036],
        "n_candidates": 198,
        "retention": 1.0,
        "mean_dead_fraction": 0.32,
        "n_void_tasks": 0,
    },
}
SIGNED = "### A8 — 2026-10-12, BEFORE any run: the frontier taskset, signed\n"


# ------------------------------------------------- the derivation (spec §130)


@pytest.mark.parametrize(
    "g, published_percent",
    [(2, 67.2), (4, 39.7), (8, 15.7), (16, 2.5)],
)
def test_zero_advantage_fraction_reproduces_the_spec_table(g, published_percent):
    """p**g + (1-p)**g at p=23/29 is the spec's §130 table, to its own precision.

    The percentages are the derivation's expected output, not an input. `0.793`
    as written in the spec is a rounding of 23/29: at a literal 0.79 the G=8 cell
    comes out 15.2%, not 15.7%, so the measured fraction is what reproduces it.
    """
    realised = probe.zero_advantage_fraction(probe.SOLVE_RATE, g)
    assert round(realised * 100, 1) == published_percent


def test_solve_rate_is_the_measured_fraction_not_the_rounded_one():
    assert probe.SOLVE_RATE == probe.SOLVED / probe.ROLLOUTS
    assert round(probe.SOLVE_RATE, 3) == 0.793


def test_weak_tail_is_43_percent_at_g8():
    """The spec's weak-policy figure: p=0.1, G=8 -> 43%."""
    frac = probe.zero_advantage_fraction(probe.WEAK_TAIL_P, 8)
    assert round(frac * 100) == 43


def test_a_weak_policy_is_worse_than_a_strong_one():
    """Both tails degenerate, and Qwen3-0.6B is the weak case."""
    weak = probe.zero_advantage_fraction(probe.WEAK_TAIL_P, 8)
    strong = probe.zero_advantage_fraction(probe.SOLVE_RATE, 8)
    assert weak > strong


def test_expected_healthy_is_the_spec_s_about_0_40():
    assert round(probe.EXPECTED_HEALTHY, 2) == 0.40
    assert probe.EXPECTED_HEALTHY < probe.ABORT_CEILING


def test_fraction_is_symmetric_about_a_half():
    """Which is exactly why `frac_reward_zero_std` cannot tell the tails apart."""
    for p in (0.05, 0.2, 0.4, probe.SOLVE_RATE):
        assert probe.zero_advantage_fraction(p, 4) == pytest.approx(
            probe.zero_advantage_fraction(1 - p, 4)
        )


@pytest.mark.parametrize("p, g", [(-0.1, 4), (1.1, 4), (0.5, 1), (0.5, 0)])
def test_degenerate_inputs_are_refused(p, g):
    with pytest.raises(ValueError):
        probe.zero_advantage_fraction(p, g)


def test_viable_band_at_g4_brackets_the_ceiling():
    """The ceiling restated as an interval of solve rates: roughly (0.12, 0.88)."""
    lo, hi = probe.viable_band(4)
    assert lo + hi == pytest.approx(1.0)  # symmetric by construction
    assert (round(lo, 2), round(hi, 2)) == (0.12, 0.88)
    assert probe.zero_advantage_fraction(lo, 4) == pytest.approx(probe.ABORT_CEILING, abs=1e-6)
    assert lo < probe.SOLVE_RATE < hi


def test_g2_is_excluded_because_the_reference_p_sits_outside_its_band():
    """Derives the spec's exclusion of G=2 instead of quoting its 67.2%."""
    lo, hi = probe.viable_band(2)
    assert not lo < probe.SOLVE_RATE < hi
    assert probe.zero_advantage_fraction(probe.SOLVE_RATE, 2) > probe.ABORT_CEILING


def test_no_solve_rate_clears_a_ceiling_below_the_floor():
    """f(0.5, g) = 2**(1-g) is the floor; below it the band is empty, not wide."""
    assert probe.viable_band(2, ceiling=0.4) is None
    assert probe.zero_advantage_fraction(0.5, 2) == 0.5


def test_implied_solve_rates_invert_the_derivation():
    for p in (0.19, 0.4, probe.SOLVE_RATE):
        frac = probe.zero_advantage_fraction(p, 4)
        lo, hi = probe.implied_solve_rates(frac, 4)
        assert min(abs(lo - p), abs(hi - p)) < 1e-6
        assert lo + hi == pytest.approx(1.0)


def test_implied_solve_rates_refuse_an_impossible_fraction():
    """Below 2**(1-g) no solve rate produces it, so the metric is not what we think."""
    assert probe.implied_solve_rates(0.01, 4) is None
    assert probe.implied_solve_rates(probe.zero_advantage_fraction(0.5, 4), 4) is not None


# ------------------------------------------------------------------ the reward


def test_exact_match_reward_is_binary_and_matches_ledger_semantics():
    completions = [
        "<answer>  Ada  </answer>",      # whitespace and case normalised -> 1
        "<answer>ada</answer>",
        "the answer is ada",             # no tags -> 0
        "<answer>ada bob cyd</answer>",  # listing every id must not score
        "<answer>bob</answer>",
    ]
    rewards = probe.exact_match_reward(completions, ["ada"] * 5)
    probe.assert_binary_reward(rewards)
    assert rewards == [1.0, 1.0, 0.0, 0.0, 0.0]


def test_exact_match_reward_reads_chat_style_completions():
    assert probe.exact_match_reward([[{"content": "<answer>x</answer>"}]], ["x"]) == [1.0]


def test_a_graded_reward_is_refused_because_it_breaks_the_probe_s_model():
    probe.assert_binary_reward([0.0, 1.0, 1.0])
    with pytest.raises(AssertionError, match="binary"):
        probe.assert_binary_reward([0.0, 0.5, 1.0])


# ------------------------------------------------------- the live probe abort


def test_monitor_is_quiet_on_a_healthy_probe():
    monitor = probe.ProbeMonitor()
    assert [monitor.observe(row) for row in probe_log([0.40] * 5)] == [None] * 6


def test_monitor_aborts_on_any_single_step_over_the_ceiling():
    monitor = probe.ProbeMonitor()
    reasons = [monitor.observe(row) for row in probe_log([0.40, 0.40, 0.61])]
    assert reasons[-1] is not None
    assert "step 2" in reasons[-1] and "0.610" in reasons[-1]


def test_the_ceiling_is_strict():
    monitor = probe.ProbeMonitor()
    assert monitor.observe(step(probe.ABORT_CEILING)) is None


def test_monitor_fails_closed_when_the_metric_is_absent():
    """A probe whose only instrument did not report has measured nothing."""
    monitor = probe.ProbeMonitor()
    reason = monitor.observe(step(None))
    assert reason is not None and "not a number" in reason


def test_the_end_of_run_summary_is_not_a_step():
    monitor = probe.ProbeMonitor()
    assert monitor.observe({"train_runtime": 298.2, "train_loss": 0.015}) is None
    assert monitor.observe({"eval_loss": 1.0}) is None
    assert V.training_steps(monitor.rows) == []


def test_the_monitor_and_the_no_gpu_verdict_agree_through_the_file(tmp_path):
    """The live abort and the after-the-fact re-check must not drift apart."""
    sink = tmp_path / "probe.jsonl"
    monitor = probe.ProbeMonitor(sink=sink)
    for row in probe_log([0.40] * 5):
        monitor.observe(row)
    assert V.probe_verdict(V.load(str(sink)))[0] is True

    monitor.observe(step(0.75))
    ok, why = V.probe_verdict(V.load(str(sink)))
    assert ok is False
    assert any("0.750" in reason for reason in why)


# ---------------------------------------------------------------- the verdict


def test_probe_passes_on_five_healthy_steps_with_provenance():
    ok, why = V.probe_verdict(probe_log([0.40] * V.MIN_PROBE_STEPS))
    assert (ok, why) == (True, [])


def test_a_short_probe_fails_closed():
    """Without this line every any(...) below is vacuously false and a probe that
    trained zero steps reports a pass."""
    ok, why = V.probe_verdict(probe_log([0.40] * (V.MIN_PROBE_STEPS - 1)))
    assert ok is False
    assert any("training steps logged" in reason for reason in why)
    assert V.probe_verdict([])[0] is False


def test_a_probe_without_a_taskset_id_is_not_quotable():
    ok, why = V.probe_verdict(probe_log([0.40] * 5, taskset_id=None))
    assert ok is False
    assert any("taskset_id" in reason for reason in why)
    assert V.probe_verdict(probe_log([0.40] * 5, taskset_id="  "))[0] is False


def test_criterion_a_any_step_and_sustained_are_different_tests():
    """The §240-vs-§282 discrepancy, pinned so neither can stand in for the other."""
    spike = [0.4] * 5 + [0.9] + [0.4] * 5
    assert V.criterion_a_any_step([step(v) for v in spike]) != []
    assert V.criterion_a_sustained([step(v) for v in spike]) == []


def test_criterion_a_sustained_needs_a_full_window():
    nine = [step(0.9)] * (V.SUSTAINED_WINDOW - 1)
    assert V.criterion_a_sustained(nine) == []
    assert V.criterion_a_sustained(nine + [step(0.9)]) != []


def test_criterion_a_sustained_resets_on_a_dip():
    rows = [step(0.9)] * 9 + [step(0.1)] + [step(0.9)] * 9
    assert V.criterion_a_sustained(rows) == []


def test_criterion_a_fails_closed_when_the_metric_was_never_logged():
    rows = [step(None)] * 12
    assert any("never logged" in r for r in V.criterion_a_sustained(rows))
    assert V.criterion_a_any_step(rows) != []


def logp(values) -> list[dict]:
    return [step(0.4, **{V.LOGP_DIFF_KEY: v}) for v in values]


def test_criterion_b_absent_metric_is_a_failure_when_required_and_a_note_when_not():
    rows = [step(0.4)] * 12
    reasons, _ = V.criterion_b(rows, required=True)
    assert any("never logged" in r for r in reasons)
    reasons, notes = V.criterion_b(rows, required=False)
    assert reasons == []
    assert any("never logged" in n for n in notes)


def test_criterion_b_is_declared_not_evaluable_on_a_short_run():
    reasons, notes = V.criterion_b(logp([0.1] * 5))
    assert reasons == []
    assert any("NOT evaluable" in n for n in notes)


def test_criterion_b_fires_on_a_monotonic_rise():
    reasons, _ = V.criterion_b(logp([0.1 * i for i in range(1, V.SUSTAINED_WINDOW + 1)]))
    assert any("monotonically" in r for r in reasons)


def test_criterion_b_ignores_a_flat_elevated_value():
    """"A flat elevated value is a calibration offset, not this signal" (§261)."""
    assert V.criterion_b(logp([50.0] * 20))[0] == []


def test_criterion_b_fires_on_a_spike_above_three_times_its_own_baseline():
    baseline = [1.0] * V.SUSTAINED_WINDOW
    assert V.criterion_b(logp(baseline))[0] == []
    reasons, _ = V.criterion_b(logp(baseline + [V.LOGP_RATIO_MULTIPLE * 1.0 + 0.01]))
    assert any("median" in r for r in reasons)


def test_the_ratio_arm_is_declared_not_evaluable_on_a_non_positive_baseline():
    """3x a non-positive baseline is a smaller number, so the test would invert."""
    rows = logp([0.0] * V.SUSTAINED_WINDOW + [99.0])
    reasons, notes = V.criterion_b(rows)
    assert reasons == []
    assert any("ratio arm" in n and "NOT evaluable" in n for n in notes)


def test_run_verdict_requires_both_criteria():
    healthy = logp([1.0] * 12)
    assert V.run_verdict(healthy)[0] is True
    assert V.run_verdict([step(0.4)] * 12)[0] is False          # B not wired
    assert V.run_verdict(logp([1.0] * 12)[:3])[0] is False      # too short


def test_training_steps_agrees_with_step2s_definition():
    """The duplicated definition is guarded, not trusted. See `V.training_steps`."""
    from step2.verdict import training_steps as step2_training_steps

    rows = [step(0.4), {"train_runtime": 1.0, "train_loss": 0.1}, {"eval_loss": 2.0}, {}]
    assert V.training_steps(rows) == step2_training_steps(rows)


def test_cli_exit_codes_distinguish_pass_from_abort(tmp_path, capsys):
    good, bad = tmp_path / "good.jsonl", tmp_path / "bad.jsonl"
    good.write_text("\n".join(json.dumps(r) for r in probe_log([0.4] * 5)))
    bad.write_text("\n".join(json.dumps(r) for r in probe_log([0.4, 0.4, 0.9, 0.4, 0.4])))
    assert V.main([str(good)]) == 0
    assert "PROBE PASS" in capsys.readouterr().out
    assert V.main([str(bad)]) == 1
    assert "PROBE ABORT" in capsys.readouterr().out


def test_observations_report_the_realised_number_against_the_reference():
    notes = V.observations(probe_log([0.45] * 5))
    assert any("realised mean 0.450" in n for n in notes)
    assert any("implies a solve rate" in n for n in notes)


# --------------------------------------------------------------- stack guards


def test_the_measured_stack_passes():
    assert guards.check_stack(GOOD_STACK) == []


def test_below_the_unsloth_floor_is_a_different_experiment_not_a_worse_one():
    faults = guards.check_stack({**GOOD_STACK, "unsloth": "2026.9.12"})
    assert len(faults) == 1
    assert "different experiment" in faults[0]
    assert "zero occurrences" in faults[0]


def test_the_floor_is_compared_as_a_version_not_a_string():
    """"2026.9.12" > "2026.10.3" is TRUE as a string, and 2026.9.12 is the
    version this project actually ran. A string compare waves it through."""
    assert "2026.9.12" > "2026.10.3"
    assert guards._parse_version("2026.9.12") < guards._parse_version("2026.10.3")
    assert guards._parse_version("2026.10.3") == guards.UNSLOTH_FLOOR


@pytest.mark.parametrize(
    "override, needle",
    [
        ({"unsloth": None}, "not installed"),
        ({"trl": None}, "not installed"),
        ({"trl": "0.24.0"}, "not the pinned"),
        ({"trl": "1.14.0"}, "not the pinned"),
        ({"transformers": "5.18.0"}, "transformers<5"),
        ({"transformers": None}, "not installed"),
    ],
)
def test_every_stack_fault_is_reported(override, needle):
    faults = guards.check_stack({**GOOD_STACK, **override})
    assert any(needle in f for f in faults), faults


def test_the_dev_machine_is_rejected():
    """The one real version set available here is the broken one, and it must fail."""
    with pytest.raises(guards.StackError):
        guards.require_stack()
    assert guards.resolved_versions()["unsloth"] is None


def test_patch_and_local_version_suffixes_parse():
    assert guards.check_stack({**GOOD_STACK, "trl": "1.13.0.post1"}) == []
    assert guards.check_stack({**GOOD_STACK, "transformers": "4.57.6+cu128"}) == []


# ------------------------------------------------- invariant 1: one tool


def test_one_registered_tool_passes():
    guards.assert_one_tool([grpo_ptc.THE_TOOL_SCHEMA])


@pytest.mark.parametrize("tools", [[], [grpo_ptc.THE_TOOL_SCHEMA] * 2])
def test_the_wrong_number_of_tools_is_refused(tools):
    with pytest.raises(guards.InvariantViolation, match="invariant 1"):
        guards.assert_one_tool(tools)


def test_registering_ledgers_three_tools_is_refused():
    """This is the flipped arm: it would build the typed-tool-calling comparator."""
    ledger_tools = [{"function": {"name": n}} for n in ("ids", "get", "links_to")]
    with pytest.raises(guards.InvariantViolation) as excinfo:
        guards.assert_one_tool(ledger_tools)
    assert "3 registered tools" in str(excinfo.value)
    with pytest.raises(guards.InvariantViolation, match="not 'run_program'"):
        guards.assert_one_tool(ledger_tools[:1])


def test_the_trained_arm_registers_the_same_single_tool_as_the_eval_arm():
    """Parsed out of `ptc/harness.py`, so the two arms cannot drift."""
    eval_tools = guards.module_literal("ptc/harness.py", "TOOLS")
    assert len(eval_tools) == 1
    assert eval_tools[0]["function"]["name"] == guards.THE_TOOL
    assert grpo_ptc.THE_TOOL_SCHEMA == eval_tools[0]


# ------------------------------------------- invariant 2: one cap per experiment


def test_the_ptc_only_cap_is_3072_and_clears_its_arm():
    cap = guards.completion_cap(("ptc",))
    assert cap.value == 3072
    assert cap.value >= guards.OBSERVED_MAX["ptc"] == 2642


def test_the_cross_arm_cap_is_exactly_the_global_observed_max():
    cap = guards.completion_cap(("ptc", "bash"))
    assert cap.value == 4258 == max(guards.OBSERVED_MAX.values())
    for arm in ("ptc", "bash"):
        assert cap.value >= guards.OBSERVED_MAX[arm]


def test_neither_cap_exists_as_a_bare_number():
    """The structural half of invariant 2: there is nothing to import and quote."""
    for module in (guards, grpo_ptc, probe):
        bare = {
            name: value
            for name, value in vars(module).items()
            if isinstance(value, int) and not isinstance(value, bool) and value in (3072, 4258)
        }
        assert bare == {}, f"{module.__name__} exposes a bare cap: {bare}"


def test_a_cap_is_not_transferable_between_experiments():
    ptc_only = guards.completion_cap(("ptc",))
    guards.assert_cap(ptc_only, ("ptc",))
    with pytest.raises(guards.InvariantViolation, match="not transferable"):
        guards.assert_cap(ptc_only, ("ptc", "bash"))


def test_a_cap_below_its_arms_observed_max_is_refused():
    """At cap 1,024, 8/29 PTC rollouts vanish from the loss entirely."""
    hand_rolled = guards.CompletionCap(frozenset({"ptc"}), 1024)
    with pytest.raises(guards.InvariantViolation, match="binding observed max"):
        guards.assert_cap(hand_rolled, ("ptc",))


def test_a_shared_cap_that_is_not_the_global_max_is_refused():
    shared = guards.CompletionCap(frozenset({"ptc", "bash"}), 4259)
    with pytest.raises(guards.InvariantViolation, match="exactly the global observed max"):
        guards.assert_cap(shared, ("ptc", "bash"))


@pytest.mark.parametrize("arms", [(), ("sql",), ("ptc", "sql")])
def test_an_undeclared_arm_has_no_cap(arms):
    with pytest.raises(guards.InvariantViolation, match="invariant 2"):
        guards.completion_cap(arms)


def test_the_configs_cap_is_the_cap_for_its_arms():
    assert grpo_ptc.training_config(("ptc",))["max_completion_length"] == 3072
    assert grpo_ptc.training_config(("ptc", "bash"))["max_completion_length"] == 4258
    assert probe.probe_config()["max_completion_length"] == 3072


# ------------------------------------------- invariant 3: max_turns reaches the arm


def test_the_turn_budget_is_read_out_of_the_eval_harness():
    source = (REPO / "ptc" / "harness.py").read_text()
    assert f"max_turns: int = Field({guards.eval_max_turns()}," in source


def test_the_factory_built_environment_satisfies_invariant_3():
    environment = grpo_ptc.environment_factory()()
    guards.assert_turn_budget(environment)
    assert environment.max_turns == guards.eval_max_turns()
    assert environment.turns_used == 0


def test_a_turn_unbounded_trained_arm_is_refused():
    class Unbounded:
        max_turns = 10**9

        def exhausted_message(self):
            return "out of turns"

    with pytest.raises(guards.InvariantViolation, match="invariant 3"):
        guards.assert_turn_budget(Unbounded())


def test_exhaustion_must_return_a_refusal_the_model_reads_not_a_hang():
    class Silent:
        max_turns = guards.eval_max_turns()
        exhausted_message = None

    with pytest.raises(guards.InvariantViolation, match="refusal the model"):
        guards.assert_turn_budget(Silent())


def test_the_refusal_must_not_be_counted_as_a_tool_failure():
    """Prefixing it would fold turn exhaustion into H4, whose sign is indeterminate."""
    prefix = guards.failure_prefixes()[0]

    class Conflated:
        max_turns = guards.eval_max_turns()

        def exhausted_message(self):
            return f"{prefix} no turns remain"

    with pytest.raises(guards.InvariantViolation, match="tool failure"):
        guards.assert_turn_budget(Conflated())


def test_the_budget_spends_exactly_max_turns_then_refuses():
    budget = guards.TurnBudget(max_turns=3)
    assert [budget.consume() for _ in range(3)] == [None, None, None]
    assert budget.remaining() == 0
    refusal = budget.consume()
    assert "3-program budget" in refusal
    assert budget.used == 3  # a refused turn is not a spent one


def test_failure_prefixes_are_read_from_ptc_metrics():
    assert guards.failure_prefixes() == ("rejected:", "error:")
    assert guards.module_literal("ptc/metrics.py", "MIN_CALLS_FOR_PERFECT_RATE") == 20


def test_a_missing_literal_is_a_loud_failure_not_a_default():
    with pytest.raises(guards.InvariantViolation, match="could not find"):
        guards.module_literal("ptc/metrics.py", "NO_SUCH_CONSTANT")


# ------------------------------------------------- the §344 precondition


def test_the_gate_is_shut_on_this_repo_today():
    """**Expected to fail the day the frontier taskset lands, and that failure is
    the signal to unblock the pipeline.** Update it then to assert the manifest
    conforms; do not delete it.
    """
    status = guards.frontier_taskset_status()
    assert status.ok is False
    assert any(guards.FRONTIER_MANIFEST in reason for reason in status.reasons)
    with pytest.raises(guards.PreconditionUnmet, match="§344"):
        guards.require_frontier_taskset()


def test_a_conforming_manifest_with_a_signed_amendment_opens_the_gate(tmp_path):
    write_manifest(tmp_path, GOOD_MANIFEST, SIGNED)
    status = guards.frontier_taskset_status(tmp_path)
    assert status == guards.Precondition(True, ())


@pytest.mark.parametrize(
    "override, needle",
    [
        ({"solve_rate_max": 1.0}, "saturated"),
        ({"solve_rate_min": 0.0}, "never solves"),
        ({"solve_rate_min": 0.05}, "dead on arrival"),
        ({"solve_rate_min": 0.9, "solve_rate_max": 0.3}, "solve_rate_min 0.9 >"),
        ({"policy": ""}, "which policy"),
        ({"n_tasks": 0}, "n_tasks"),
        ({"pre_registration_amendment": ""}, "names no pre-registration"),
        ({"pre_registration_amendment": "A99"}, "is not signed"),
    ],
)
def test_every_way_the_precondition_fails_is_reported(tmp_path, override, needle):
    write_manifest(tmp_path, {**GOOD_MANIFEST, **override}, SIGNED)
    status = guards.frontier_taskset_status(tmp_path)
    assert status.ok is False
    assert any(needle in reason for reason in status.reasons), status.reasons


def test_an_off_frontier_band_end_is_rejected_by_the_probes_own_derivation(tmp_path):
    """A band end the policy almost never solves is dead before training starts."""
    off_frontier = 0.05
    frac = probe.zero_advantage_fraction(off_frontier, probe.NUM_GENERATIONS)
    assert frac > probe.ABORT_CEILING
    write_manifest(tmp_path, {**GOOD_MANIFEST, "solve_rate_min": off_frontier}, SIGNED)
    reasons = guards.frontier_taskset_status(tmp_path).reasons
    assert any(f"{frac:.3f}" in r for r in reasons), reasons


def test_an_unsigned_amendment_does_not_open_the_gate(tmp_path):
    write_manifest(tmp_path, GOOD_MANIFEST, "### A8 — 2026-10-12: frontier taskset (draft)\n")
    status = guards.frontier_taskset_status(tmp_path)
    assert status.ok is False
    assert any("not signed" in reason for reason in status.reasons)


@pytest.mark.parametrize("body", ["{not json", "[]", '{"policy": "x"}'])
def test_a_malformed_manifest_fails_closed(tmp_path, body):
    write_manifest(tmp_path, body, SIGNED)
    assert guards.frontier_taskset_status(tmp_path).ok is False


def test_every_required_manifest_key_is_named_when_absent(tmp_path):
    """Not just "not ok" -- the operator has to be told which key to add."""
    for key in guards.MANIFEST_REQUIRED:
        partial = {k: v for k, v in GOOD_MANIFEST.items() if k != key}
        write_manifest(tmp_path, partial, SIGNED)
        reasons = guards.frontier_taskset_status(tmp_path).reasons
        assert any(f"is missing {key}" in reason for reason in reasons), (key, reasons)


# ------------------------------------------------------------- the pipeline


def test_preflight_refuses_before_anything_costs_money():
    with pytest.raises(guards.PreconditionUnmet):
        grpo_ptc.preflight()
    with pytest.raises(guards.PreconditionUnmet):
        grpo_ptc.main(["--preflight-only"])


def gate_open_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree where §344 is satisfied and the files the invariants read are real.

    `ptc/harness.py` and `ptc/metrics.py` are copied rather than stubbed, so
    `eval_max_turns` and `failure_prefixes` still read the repo's own values.
    """
    write_manifest(tmp_path, GOOD_MANIFEST, SIGNED)
    (tmp_path / "ptc").mkdir(exist_ok=True)
    for name in ("harness.py", "metrics.py"):
        shutil.copy(REPO / "ptc" / name, tmp_path / "ptc" / name)
    return tmp_path


def test_preflight_checks_the_stack_once_the_gate_is_open(tmp_path):
    with pytest.raises(guards.StackError):
        grpo_ptc.preflight(root=gate_open_root(tmp_path), versions={"unsloth": None})


def test_preflight_passes_every_invariant_once_the_gate_opens(tmp_path):
    """The only end-to-end green of the pipeline's guards: the gate and the stack
    are the two things stopping it today, and with both satisfied the three
    invariants hold against the repo's real harness files."""
    config = grpo_ptc.preflight(root=gate_open_root(tmp_path), versions=GOOD_STACK)
    assert config["max_completion_length"] == guards.completion_cap(("ptc",)).value
    assert config["num_generations"] == 4


def test_step_zero_tool_success_flags_the_floor_artifact():
    """Run 3d measured: bash 0 failures in 822 calls, PTC 74 in 156."""
    flagged = grpo_ptc.step_zero_tool_success(822, 0)
    assert flagged is not None and "floor artifact" in flagged
    assert grpo_ptc.step_zero_tool_success(156, 74) is None
    assert grpo_ptc.step_zero_tool_success(19, 0) is None  # below MIN_CALLS_FOR_PERFECT_RATE


def test_the_turn_budget_refusal_reaches_the_model_through_step():
    environment = grpo_ptc.environment_factory()()
    environment.budget.used = environment.max_turns
    assert "budget for this task is spent" in environment.step("print(1)")


def test_program_execution_is_not_stubbed_into_looking_like_it_works():
    """A stub returning plausible output would make an empty pipeline look fine."""
    with pytest.raises(NotImplementedError, match="§344"):
        grpo_ptc.environment_factory()().step("print(1)")


# ----------------------------------------------------------------- the configs


def test_the_probe_config_is_the_hardware_line_the_spec_derived():
    config = probe.probe_config()
    assert config["vllm_mode"] == "colocate"  # default flips across the version range
    assert (config["fp16"], config["bf16"]) == (True, False)
    assert config["num_generations"] == probe.NUM_GENERATIONS == 4
    assert config["mask_truncated_completions"] is True
    assert config["logging_steps"] == 1  # per-step abort needs a per-step log
    assert config["save_strategy"] == "no"  # no checkpoint from a probe is worth keeping


@pytest.mark.parametrize("steps", [0, 4, 21, 200])
def test_the_probe_refuses_to_become_a_study(steps):
    with pytest.raises(ValueError, match="probe"):
        probe.probe_config(steps)


def test_fp16_is_set_explicitly_in_both_configs():
    """bf16's mismatch measures ~24x fp16's, and it worsens with response length."""
    for config in (probe.probe_config(), grpo_ptc.training_config(("ptc",))):
        assert config["fp16"] is True and config["bf16"] is False
    assert grpo_ptc.model_spec()["load_in_4bit"] is False


def test_the_probe_dry_run_needs_no_gpu(tmp_path, capsys):
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(json.dumps({"prompt": "who?", "answer": "ada"}) + "\n")
    assert probe.main([
        "--prompts", str(prompts), "--taskset-id", "synthetic-smoke", "--dry-run",
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["taskset_id"] == "synthetic-smoke"
    assert printed["stack_faults"]  # this machine is not the stack
    assert printed["expectations"]["expected_frac_reward_zero_std"] == probe.EXPECTED_HEALTHY


@pytest.mark.parametrize(
    "body", ['{"prompt": "a"}', '{"answer": "b"}', '{"prompt": " ", "answer": "b"}', ""]
)
def test_prompts_missing_an_answer_are_refused(tmp_path, body):
    path = tmp_path / "prompts.jsonl"
    path.write_text(body)
    with pytest.raises(ValueError):
        probe.load_prompts(path)


def test_the_gate_refuses_a_frontier_too_small_to_carry_the_effect(tmp_path):
    """`n_tasks` must clear `MIN_FRONTIER_TASKS`, which is derived from the power
    function rather than stored.

    The band is a band over the RETAINED subset, so it is conformant by construction:
    before this floor, a suite that drew 198 tasks and kept 3 passed every band check.
    n is where the information is.
    """
    too_small = {**GOOD_MANIFEST, "n_tasks": guards.MIN_FRONTIER_TASKS - 1,
                 "measurement": {**GOOD_MANIFEST["measurement"],
                                 "retention": (guards.MIN_FRONTIER_TASKS - 1) / 198}}
    write_manifest(tmp_path, too_small, SIGNED)
    status = guards.frontier_taskset_status(tmp_path)
    assert not status.ok
    assert any("below the" in r and "paired tasks" in r for r in status.reasons), \
        status.reasons

    # and the boundary itself passes, so the floor is not off by one
    at_floor = {**GOOD_MANIFEST, "n_tasks": guards.MIN_FRONTIER_TASKS}
    write_manifest(tmp_path, at_floor, SIGNED)
    assert guards.frontier_taskset_status(tmp_path).ok


def test_the_frontier_floor_is_derived_from_the_power_function(tmp_path):
    """Not a stored 59. The power function was corrected on 2026-10-12 for an
    int-to-float OverflowError, and a second copy of its output would not have
    moved with it."""
    from ptc.paired import power_pairs
    assert guards.MIN_FRONTIER_TASKS == power_pairs(0.25, 0.5)


def test_the_gate_takes_a_string_root(tmp_path):
    """`root / FRONTIER_MANIFEST` raised TypeError on a str. The gate's entire purpose
    is to say why it is shut; failing with an operator error on an ordinary argument is
    not that."""
    write_manifest(tmp_path, GOOD_MANIFEST, SIGNED)
    assert guards.frontier_taskset_status(str(tmp_path)).ok


def test_the_execution_reward_finds_a_database_in_either_layout(tmp_path):
    """BIRD nests databases under `dev_databases/`; a Kaggle dataset does not.

    Uploading with `--dir-mode zip` makes Kaggle extract the archive and mount its
    contents at the dataset root, so the same file lands one directory shallower.
    Hard-coding either layout turns a mount-path detail into an aborted run, because a
    missing database is the one thing the execution reward refuses to score as a
    policy failure.
    """
    from train.ex_reward import db_path_for

    nested = tmp_path / "bird" / "dev_databases" / "toxicology"
    nested.mkdir(parents=True)
    (nested / "toxicology.sqlite").write_bytes(b"")
    assert db_path_for(tmp_path / "bird", "toxicology") == str(
        nested / "toxicology.sqlite")

    flat = tmp_path / "kaggle" / "toxicology"
    flat.mkdir(parents=True)
    (flat / "toxicology.sqlite").write_bytes(b"")
    assert db_path_for(tmp_path / "kaggle", "toxicology") == str(
        flat / "toxicology.sqlite")

    # absent in both: returns the canonical path so the caller's error names the
    # layout the corpus is meant to have
    assert "dev_databases" in db_path_for(tmp_path / "empty", "toxicology")


def test_the_execution_reward_refuses_to_score_a_missing_database(tmp_path):
    """Scoring 0 for an unmounted corpus reads as a policy that cannot answer -- the
    exact confound that made the first probe run unreadable (schema-only prompts,
    structurally zero solve rate, frac_reward_zero_std 1.000 at step 0)."""
    import pytest as _pytest

    from train.ex_reward import make_execution_reward

    reward = make_execution_reward(tmp_path)
    with _pytest.raises(FileNotFoundError, match="not mounted"):
        reward(["```sql\nSELECT 1\n```"], ["SELECT 1"], ["toxicology"])


def test_the_metric_has_enough_groups_to_reach_its_own_ceiling():
    """`frac_reward_zero_std` is a fraction OVER GROUPS, so groups-per-step is its
    resolution -- and nothing checked it until 2026-10-13.

    At TRL's default total batch of 8 sequences, G=4 gives 2 groups and G=8 gives 1.
    Both were run on free hardware: v4 (G=4) logged exactly 0.5 then 1.0, v5 (G=8)
    logged exactly 1.0. With one group the statistic is a Bernoulli draw and the 0.60
    ceiling is unreachable, so the comparison was a coin flip against its own mean --
    and at p=0.0625 a lone group is uniform about 60% of the time, meaning the probe
    aborted at the rate a HEALTHY configuration predicts.
    """
    from train.dead_group_probe import (ABORT_CEILING, MIN_GROUPS_PER_STEP,
                                        batch_for, probe_config)

    for g in (4, 8):
        config = probe_config(5, g)
        total = (config["per_device_train_batch_size"]
                 * config["gradient_accumulation_steps"])
        groups = total // g
        assert total % g == 0, (g, total)
        assert groups >= MIN_GROUPS_PER_STEP, (g, groups)
        # the ceiling must sit strictly inside the attainable levels, not on an edge
        levels = [i / groups for i in range(groups + 1)]
        assert min(levels) < ABORT_CEILING < max(levels), (groups, levels)

    with pytest.raises(ValueError, match="attainable levels"):
        batch_for(8, 1)
    with pytest.raises(ValueError, match="attainable levels"):
        batch_for(4, MIN_GROUPS_PER_STEP - 1)
