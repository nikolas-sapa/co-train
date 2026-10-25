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

import ast
import inspect
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


# ------------------------------------------- what the model actually wrote
#
# Six probe runs were adjudicated from aggregate metrics and nobody read a completion.
# Reward 0.0 with frac_reward_zero_std 1.000 was read as "the policy cannot solve
# these tasks", but it is equally consistent with output the reward's extraction does
# not recover, with nothing generated at all, and with the completion cap cutting the
# answer off. These tests pin the sampling that separates those.


def test_the_sample_records_what_was_generated_beside_what_was_extracted():
    """Both fields, because the gap between them IS the hypothesis under test.

    One reward number cannot distinguish "wrote the wrong answer" from "wrote the
    right answer in a shape the extractor missed" from "wrote nothing". The row can.
    """
    completions = ["<answer>ada</answer>", "the answer is ada", ""]
    sampler = probe.CompletionSampler()
    sampler.record(completions, probe.exact_match_reward(completions, ["ada"] * 3))
    samples = sampler.drain()

    assert [s["reward"] for s in samples] == [1.0, 0.0, 0.0]
    assert [s["extracted"] for s in samples] == ["ada", None, None]
    assert [s["completion"] for s in samples] == completions
    assert [s["chars"] for s in samples] == [len(c) for c in completions]
    # the two zeros are opposite diagnoses and the row says which: text present with
    # nothing recovered is a format fault, no text at all is a generation fault
    assert samples[1]["chars"] > 0 and samples[2]["chars"] == 0
    assert sampler.drain() == []  # drained, so the next step does not inherit this one


def test_a_long_completion_is_cut_to_its_budget_and_names_what_it_dropped():
    """A sink that swallowed whole completions would be unread for the same reason the
    aggregates were: too much to look at. The dropped count is in the value, so a cut
    sample cannot be mistaken for a model that stopped there."""
    long = "SELECT " + "x" * (probe.SAMPLE_CHARS * 3)
    sampler = probe.CompletionSampler()
    sampler.record([long], [0.0])
    sample, = sampler.drain()

    dropped = len(long) - probe.SAMPLE_CHARS
    assert sample["completion"] == long[:probe.SAMPLE_CHARS] + f"...[+{dropped} chars]"
    assert sample["chars"] == len(long)  # the untruncated length still travels with it
    assert len(sample["completion"]) < len(long)
    # and a completion inside the budget is recorded verbatim, marker and all absent
    assert probe.truncated("x" * probe.SAMPLE_CHARS) == "x" * probe.SAMPLE_CHARS


def test_the_extraction_is_cut_to_the_same_budget():
    """An unterminated fence leaves `extract_sql` returning the whole tail of the reply
    -- the case most worth seeing, and the one that would otherwise double the row it
    sits in. Asserted against `extract_sql`'s live behaviour rather than a copy of it,
    because `bench/score.py` owns what extraction means and changed it on 2026-10-14."""
    from bench.score import extract_sql

    unterminated = "```sql\nSELECT " + "y" * (probe.SAMPLE_CHARS * 2)
    sampler = probe.CompletionSampler(extract=extract_sql)
    sampler.record([unterminated], [0.0])
    sample, = sampler.drain()

    assert len(extract_sql(unterminated)) > probe.SAMPLE_CHARS  # else nothing is proved
    assert sample["extracted"] == probe.truncated(extract_sql(unterminated))
    assert sample["extracted"].endswith("chars]")


def test_sampling_keeps_one_group_per_step_across_accumulation():
    """One logged step is `gradient_accumulation_steps` reward calls, so the sampler
    accumulates across them; replacing would record only the last micro-batch and the
    JSONL would silently describe a different part of the step than its metric does.

    The cap is G because TRL lays the batch out as G consecutive completions per
    prompt: the first G are exactly one group, the unit `frac_reward_zero_std` counts.
    """
    assert probe.SAMPLES_PER_STEP == probe.NUM_GENERATIONS
    per_device, accum = probe.batch_for(probe.NUM_GENERATIONS)
    assert accum > 1, (per_device, accum)  # otherwise this test proves nothing

    sampler = probe.CompletionSampler()
    for call in range(accum):
        batch = [f"<answer>c{call}-{i}</answer>" for i in range(per_device)]
        sampler.record(batch, probe.exact_match_reward(batch, ["none"] * per_device))
    samples = sampler.drain()
    assert len(samples) == probe.SAMPLES_PER_STEP
    assert [s["extracted"] for s in samples] == [
        f"c0-{i}" for i in range(probe.SAMPLES_PER_STEP)]

    # micro-batches smaller than the cap contribute to the same step, in order
    sampler = probe.CompletionSampler()
    half = probe.SAMPLES_PER_STEP // 2
    for call in range(2):
        batch = [f"<answer>c{call}-{i}</answer>" for i in range(half)]
        sampler.record(batch, [0.0] * half)
    assert [s["extracted"] for s in sampler.drain()] == [
        f"c{call}-{i}" for call in range(2) for i in range(half)]


def test_the_wrapped_reward_keeps_its_name_and_passes_its_scores_through():
    """TRL names its reward columns after `reward_func.__name__`, so an unnamed wrapper
    renames the metric a later run is compared against -- and a sampler that changed a
    score would be softening the reward whose geometry is the measurement."""
    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(probe.exact_match_reward, sampler)
    completions = ["<answer>ada</answer>", "no tags"]
    expected = probe.exact_match_reward(completions, ["ada"] * 2)

    assert wrapped.__name__ == probe.exact_match_reward.__name__
    assert wrapped(completions=completions, answer=["ada"] * 2) == expected
    assert len(sampler.drain()) == len(completions)
    # called positionally too: recording must not depend on TRL's call style
    assert wrapped(completions, ["ada"] * 2) == expected
    assert len(sampler.drain()) == len(completions)


def test_the_sampled_extraction_is_the_rewards_own_not_a_second_copy():
    """A sample only measures the reward if it shows the reward's own extraction."""
    from bench.score import extract_sql

    def parsed(*extra):
        return probe.build_parser().parse_args(
            ["--prompts", "p", "--taskset-id", "t", *extra])

    assert probe._extractor_for(parsed()) is probe.extracted_answer
    assert probe._extractor_for(parsed("--reward", "ex", "--db-root", ".")) is extract_sql
    # and `exact_match_reward` scores exactly what the sample reports as extracted
    text = "<answer>  ADA </answer>"
    assert probe.extracted_answer(text) == "ada"
    assert probe.exact_match_reward([text], ["ada"]) == [1.0]


def test_the_samples_ride_the_same_row_as_the_metric_through_the_sink(tmp_path):
    """One fetched artifact has to carry the metric and the text it was computed from;
    a second output file is one more thing to remember to look at."""
    sink = tmp_path / "probe.jsonl"
    sampler = probe.CompletionSampler()
    monitor = probe.ProbeMonitor(sink=sink, sampler=sampler)
    # the header records the sampling SETTINGS under a different key on purpose: one
    # key must not mean "the budget" on one row and "the text" on all the others
    monitor.header(probe="dead_group", taskset_id="fixture",
                   completion_sampling={"per_step": sampler.per_step,
                                        "chars": sampler.chars})
    sampler.record(["<answer>ada</answer>"], [1.0])
    assert monitor.observe(step(0.4)) is None
    assert monitor.observe(step(0.4)) is None  # nothing recorded for this one
    monitor.observe({"train_runtime": 1.0, "train_loss": 0.1})

    head, first, second, summary = V.load(str(sink))
    assert V.COMPLETION_SAMPLES_KEY not in head
    assert V.COMPLETION_SAMPLES_KEY not in summary  # the summary is not a step
    assert [s["extracted"] for s in first[V.COMPLETION_SAMPLES_KEY]] == ["ada"]
    # present and empty, not absent: "the reward saw no completion" must not look
    # like "sampling was switched off"
    assert second[V.COMPLETION_SAMPLES_KEY] == []
    assert V.completion_samples(V.load(str(sink))) == [(0, first[V.COMPLETION_SAMPLES_KEY][0])]


def test_sampling_is_on_by_default_and_turning_it_off_is_the_deliberate_act():
    """The lesson is that nobody looked, so the default must not depend on asking."""
    base = ["--prompts", "p", "--taskset-id", "t"]
    assert probe.build_parser().parse_args(base).no_completion_samples is False
    assert probe.build_parser().parse_args(
        base + ["--no-completion-samples"]).no_completion_samples is True
    assert probe.ProbeMonitor().sampler is None  # explicitly wired, never implicit


def test_the_verdict_shows_the_samples_without_being_asked():
    """A reader adjudicating a run with no correct answers is shown the text, not told
    where to grep for it -- and shown the first step's group IN FULL, because cutting
    it at a fixed count hides whichever shape came last."""
    raw = "the answer is ada"
    group = [{"chars": len(raw), "completion": raw, "extracted": None, "reward": 0.0},
             {"chars": 0, "completion": "", "extracted": None, "reward": 0.0}]
    logs = probe_log([1.0] * 5)
    for n, row in enumerate(V.training_steps(logs)):
        row[V.COMPLETION_SAMPLES_KEY] = group if n == 0 else group[:1]

    total = len(group) + (len(V.training_steps(logs)) - 1)
    notes = V.observations(logs)
    assert any(f"{total} completions sampled over 5 steps" in n for n in notes)
    assert any("0 scored above 0" in n and f"{total} had nothing recovered" in n
               for n in notes)
    assert any(raw in n for n in notes)  # verbatim, not summarised
    assert sum("step 0 sample: reward" in n for n in notes) == len(group)
    assert any(f"{total - len(group)} further samples" in n for n in notes)


def test_a_file_that_recorded_nothing_says_which_kind_of_nothing():
    """"sampling was off" and "the reward was never handed a completion" are different
    faults with different fixes, so they get different notes."""
    off = V.observations(probe_log([1.0] * 5))
    assert any("no step recorded what the model wrote" in n for n in off)
    assert any("--no-completion-samples" in n for n in off)

    logs = probe_log([1.0] * 5)
    for row in V.training_steps(logs):
        row[V.COMPLETION_SAMPLES_KEY] = []
    on = V.observations(logs)
    assert any("recorded nothing across 5 steps" in n for n in on)
    assert any("generation-path fault" in n for n in on)
    assert not any("no step recorded" in n for n in on)


def test_the_samples_are_never_a_pass_criterion():
    """Text is evidence for a diagnosis. It must not be able to make a probe pass, and
    a failure must not be downgradable to a quote."""
    def with_samples(logs, samples):
        rows = [dict(r) for r in logs]
        for row in V.training_steps(rows):
            row[V.COMPLETION_SAMPLES_KEY] = samples
        return rows

    perfect = [{"chars": 20, "completion": "<answer>ada</answer>",
                "extracted": "ada", "reward": 1.0}]
    aborting = probe_log([0.4, 0.4, 0.9, 0.4, 0.4])
    assert V.probe_verdict(with_samples(aborting, perfect)) == V.probe_verdict(aborting)

    clean = probe_log([0.4] * 5)
    assert V.probe_verdict(with_samples(clean, []))[0] is True


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


@pytest.mark.parametrize("window", [1, 3])
@pytest.mark.parametrize("value", [float("nan"), float("-inf"), float("inf")],
                         ids=["nan", "negative-infinity", "positive-infinity"])
def test_monitor_nonfinite_metrics_abort_immediately_and_agree_with_verdict(value, window):
    """An invalid instrument reading cannot wait for a finite-breach window."""
    monitor = probe.ProbeMonitor(window=window)
    reason = monitor.observe(step(value))
    verdict_reasons = V.criterion_a_any_step(monitor.rows, window=window)

    assert any("not a finite number" in r for r in verdict_reasons)
    assert reason is not None
    assert monitor.aborted == reason
    assert "step 0" in reason and V.ZERO_STD_KEY in reason
    assert repr(value) in reason
    assert len(V.training_steps(monitor.rows)) == 1


@pytest.mark.parametrize("window", [1, 3])
@pytest.mark.parametrize("value", [0.0, 0.4, 0.60])
def test_monitor_finite_controls_continue_and_agree_with_verdict(value, window):
    monitor = probe.ProbeMonitor(window=window)
    for _ in range(3):
        assert monitor.observe(step(value)) is None
        assert V.criterion_a_any_step(monitor.rows, window=window) == []
    assert monitor.aborted is None


@pytest.mark.parametrize("window", [1, 3])
@pytest.mark.parametrize("value", [float("nan"), float("-inf"), float("inf")],
                         ids=["nan", "negative-infinity", "positive-infinity"])
def test_callback_nonfinite_metrics_stop_and_raise_without_waiting_for_window(
    monkeypatch, value, window
):
    """Exercise the real callback body without importing the training stack."""
    from types import ModuleType, SimpleNamespace

    transformers = ModuleType("transformers")
    transformers.TrainerCallback = object
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monitor = probe.ProbeMonitor(window=window)
    callback = probe.make_callback(monitor)
    control = SimpleNamespace(should_training_stop=False)

    if window == 3:
        # One finite breach has not filled the window. An invalid next reading
        # must stop now, not wait for a third step or reset the finite streak.
        assert callback.on_log(None, None, control, logs=step(0.9)) is control
        assert control.should_training_stop is False
        assert monitor.aborted is None

    with pytest.raises(probe.DeadGroupAbort, match=V.ZERO_STD_KEY) as abort:
        callback.on_log(None, None, control, logs=step(value))

    assert control.should_training_stop is True
    assert str(abort.value) == monitor.aborted
    assert V.criterion_a_any_step(monitor.rows, window=window) != []


@pytest.mark.parametrize("window", [1, 3])
def test_monitor_finite_breaches_abort_only_when_the_window_is_full(window):
    monitor = probe.ProbeMonitor(window=window)
    for _ in range(window - 1):
        assert monitor.observe(step(0.9)) is None
        assert V.criterion_a_any_step(monitor.rows, window=window) == []
    assert monitor.observe(step(0.9)) is not None
    assert V.criterion_a_any_step(monitor.rows, window=window) != []


def test_monitor_finite_clear_step_resets_the_breach_window():
    monitor = probe.ProbeMonitor(window=3)
    for value in (0.9, 0.9, 0.4, 0.9, 0.9):
        assert monitor.observe(step(value)) is None
        assert V.criterion_a_any_step(monitor.rows, window=3) == []
    assert monitor.observe(step(0.9)) is not None
    assert V.criterion_a_any_step(monitor.rows, window=3) != []


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


def test_criterion_a_window_suppresses_one_unlucky_batch_and_not_a_dead_reward():
    """The probe's own verdict needs five steps; the live abort used to end the run at
    step 0, so the two adjudicators disagreed about how much evidence exists.

    At G=8 the ceiling sits on the band's lower edge: a precisely viable policy breaches
    a one-step test 47.5% of the time. A window of 3 takes that to 0.107 while a
    hopeless policy (p=0.02) still fires with probability 0.708.
    """
    one_bad = [step(0.9)] + [step(0.4)] * 4
    assert V.criterion_a_any_step(one_bad) != []          # §282 verbatim
    assert V.criterion_a_any_step(one_bad, window=3) == []
    # a dead reward breaches every step, so the window does not save it
    assert V.criterion_a_any_step([step(0.95)] * 5, window=3) != []


def test_the_window_does_not_fire_without_a_consecutive_run():
    rows = [step(0.9), step(0.9), step(0.1), step(0.9), step(0.9)]
    assert V.criterion_a_any_step(rows, window=3) == []
    assert V.criterion_a_any_step(rows + [step(0.9)], window=3) != []


def test_the_window_refuses_zero_rather_than_reading_as_never_abort():
    with pytest.raises(ValueError, match="window"):
        V.criterion_a_any_step([step(0.9)], window=0)


def test_the_live_monitor_and_the_verdict_apply_the_same_window():
    """One definition decides both, so a live stop cannot disagree with the file.

    Under window 1 a single breaching step ends the run; under window 3 it records and
    continues, and the re-read verdict agrees at every prefix.
    """
    for window in (1, 3):
        monitor = probe.ProbeMonitor(window=window)
        reason = None
        for v in (0.9, 0.9, 0.9):
            reason = monitor.observe(step(v)) or reason
            if reason:
                break
        verdict_reasons = V.criterion_a_any_step(monitor.rows, window=window)
        assert bool(reason) is bool(verdict_reasons), (window, reason, verdict_reasons)


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
    """Corrected contract: only optional B is note-only on a short probe.

    Required B's old [] expectation mistook unevaluable for passing. The required
    case is pinned by test_run_verdict_integrity_required_short_b_is_not_a_note_only.
    """
    reasons, notes = V.criterion_b(logp([0.1] * 5), required=False)
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


def test_run_verdict_integrity_ten_complete_constant_steps_pass_without_a_header():
    """A flat positive B is a control, not a collapse or a new provenance gate."""
    assert V.run_verdict(logp([1.0] * V.SUSTAINED_WINDOW)) == (True, [])


def test_run_verdict_integrity_five_steps_cannot_pass_an_unevaluable_b():
    rows = logp([1.0] * V.MIN_PROBE_STEPS)
    ok, reasons = V.run_verdict(rows)
    assert ok is False, "five steps cannot evaluate B's ten-step window"
    assert any("B" in r and "evaluable" in r.lower() for r in reasons), reasons


def test_run_verdict_integrity_one_b_value_in_twelve_steps_cannot_pass():
    rows = logp([1.0] * 12)
    for row in rows[1:]:
        del row[V.LOGP_DIFF_KEY]
    ok, reasons = V.run_verdict(rows)
    assert ok is False, "one finite B value does not make twelve steps adjudicable"
    assert any(V.LOGP_DIFF_KEY in r or "criterion B" in r for r in reasons), reasons


_MISSING_RUN_METRIC = object()
_INVALID_RUN_METRICS = [
    pytest.param(_MISSING_RUN_METRIC, id="missing"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-inf"),
    pytest.param(float("-inf"), id="negative-inf"),
]


def _replace_run_metric(rows, index, key, value):
    if value is _MISSING_RUN_METRIC:
        del rows[index][key]
    else:
        rows[index][key] = value


def _assert_unevaluable_metric(reasons, key):
    """An instrumentation fault must not masquerade as measured collapse."""
    assert any(
        key in r and any(marker in r.lower() for marker in (
            "not adjudicable", "not evaluable", "not a finite", "invalid",
            "insufficient", "missing", "never logged",
        ))
        for r in reasons
    ), reasons


@pytest.mark.parametrize(
    "n_steps,bad_index",
    [(n, i) for n in (10, 12) for i in range(n)],
    ids=[f"{n}-steps-row-{i}" for n in (10, 12) for i in range(n)],
)
@pytest.mark.parametrize("key", [V.ZERO_STD_KEY, V.LOGP_DIFF_KEY], ids=["A", "B"])
@pytest.mark.parametrize("value", _INVALID_RUN_METRICS)
def test_run_verdict_integrity_every_required_row_must_be_finite(
    n_steps, bad_index, key, value,
):
    """176 cases: every position, both metrics, both lengths, four telemetry faults."""
    rows = logp([1.0] * n_steps)
    _replace_run_metric(rows, bad_index, key, value)
    ok, reasons = V.run_verdict(rows)
    assert ok is False, (n_steps, bad_index, key, value, reasons)
    _assert_unevaluable_metric(reasons, key)
    assert any(f"step {bad_index}" in r for r in reasons), reasons


@pytest.mark.parametrize("value", _INVALID_RUN_METRICS)
def test_run_verdict_integrity_a_gap_is_unevaluable_not_a_healthy_reset(value):
    """Two nine-step breaches separated by missing data are not a healthy A trace."""
    rows = [step(0.9) for _ in range(2 * V.SUSTAINED_WINDOW - 1)]
    gap = V.SUSTAINED_WINDOW - 1
    _replace_run_metric(rows, gap, V.ZERO_STD_KEY, value)
    reasons = V.criterion_a_sustained(rows)
    _assert_unevaluable_metric(reasons, V.ZERO_STD_KEY)
    assert not any("consecutive steps" in r for r in reasons), reasons


@pytest.mark.parametrize("value", _INVALID_RUN_METRICS)
def test_run_verdict_integrity_b_gap_never_compresses_a_consecutive_window(value):
    """Ten rising valid values with a hole do not make ten consecutive logged steps."""
    rows = logp([1.0 + i / 100 for i in range(V.SUSTAINED_WINDOW + 1)])
    _replace_run_metric(rows, V.SUSTAINED_WINDOW // 2, V.LOGP_DIFF_KEY, value)
    reasons, _ = V.criterion_b(rows, required=True)
    assert not any("monotonically" in r for r in reasons), reasons
    _assert_unevaluable_metric(reasons, V.LOGP_DIFF_KEY)


@pytest.mark.parametrize("value", _INVALID_RUN_METRICS)
def test_run_verdict_integrity_b_gap_cannot_shift_the_first_ten_step_baseline(value):
    rows = logp([1.0] * V.SUSTAINED_WINDOW + [4.0, 4.0])
    _replace_run_metric(rows, 0, V.LOGP_DIFF_KEY, value)
    reasons, _ = V.criterion_b(rows, required=True)
    _assert_unevaluable_metric(reasons, V.LOGP_DIFF_KEY)
    assert any("first-10-step baseline" in r and "NOT evaluable" in r for r in reasons)
    assert not any(" reached " in r for r in reasons), reasons


def test_run_verdict_integrity_b_reports_real_logged_row_indices_after_a_gap():
    rows = logp([1.0] + [1.0 + i / 100 for i in range(V.SUSTAINED_WINDOW + 1)])
    del rows[0][V.LOGP_DIFF_KEY]
    reasons, _ = V.criterion_b(rows, required=True)
    _assert_unevaluable_metric(reasons, V.LOGP_DIFF_KEY)
    assert any("steps 1-10:" in r and "monotonically" in r for r in reasons), reasons
    assert not any("steps 0-9:" in r for r in reasons), reasons


@pytest.mark.parametrize("baseline", [0.0, -1.0])
def test_run_verdict_integrity_nonpositive_finite_baseline_remains_informational(baseline):
    """Owner policy unchanged: this note is not a new scientific failure criterion."""
    assert V.run_verdict(logp([baseline] * V.SUSTAINED_WINDOW)) == (True, [])


def test_run_verdict_integrity_required_short_b_is_not_a_note_only():
    """The run requires B; a short probe may merely observe that B is unavailable.

    The older `test_criterion_b_is_declared_not_evaluable_on_a_short_run`
    expected [] with required=True and was kept intact for the verified RED phase.
    It now explicitly tests required=False, matching the "not a pass" contract.
    """
    reasons, _ = V.criterion_b(logp([1.0] * V.MIN_PROBE_STEPS), required=True)
    assert any("NOT evaluable" in r for r in reasons), reasons
    optional_reasons, notes = V.criterion_b(
        logp([1.0] * V.MIN_PROBE_STEPS), required=False,
    )
    assert optional_reasons == []
    assert any("NOT evaluable" in n for n in notes), notes


def test_run_verdict_integrity_probe_defaults_and_scientific_constants_stay_fixed():
    assert V.MIN_PROBE_STEPS == 5
    assert V.SUSTAINED_WINDOW == 10
    assert V.ZERO_STD_CEILING == 0.60
    assert V.LOGP_RATIO_MULTIPLE == 3.0
    assert V.probe_verdict(probe_log([0.4] * V.MIN_PROBE_STEPS)) == (True, [])
    assert V.probe_verdict(probe_log([0.4] * (V.MIN_PROBE_STEPS - 1)))[0] is False
    assert V.probe_verdict(probe_log([0.9] + [0.4] * 4))[0] is False
    # The ratio threshold remains strictly greater than 3x, never >= or an offset.
    baseline = logp([1.0] * V.SUSTAINED_WINDOW)
    assert V.run_verdict(baseline + logp([V.LOGP_RATIO_MULTIPLE])) == (True, [])
    ok, reasons = V.run_verdict(baseline + logp([V.LOGP_RATIO_MULTIPLE + 0.01]))
    assert ok is False
    assert any("median" in r for r in reasons), reasons


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


@pytest.mark.parametrize("transformers", ["5.2.0", "5.17.0", "5.18.0"])
def test_default_stack_keeps_the_transformers_five_ceiling(transformers):
    versions = {**GOOD_STACK, "transformers": transformers}
    assert guards.check_stack_common(versions) == []
    faults = guards.check_stack(versions)
    assert len(faults) == 1
    assert "transformers<5" in faults[0]
    with pytest.raises(guards.StackError, match="transformers<5"):
        guards.require_stack(versions)


def test_default_stack_delegates_shared_checks_without_replacing_them(monkeypatch):
    seen = []

    def common(versions):
        seen.append(dict(versions))
        return ["shared-stack-sentinel"]

    monkeypatch.setattr(guards, "check_stack_common", common)
    assert guards.check_stack(GOOD_STACK) == ["shared-stack-sentinel"]
    assert seen == [GOOD_STACK]


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


def test_native_preflight_has_no_runtime_policy_or_fixture_switches():
    parameters = inspect.signature(grpo_ptc.native_sql_preflight).parameters
    assert list(parameters) == ["root", "steps"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY
               for parameter in parameters.values())
    assert parameters["root"].default == REPO
    assert parameters["steps"].default == 200
    with pytest.raises(TypeError):
        grpo_ptc.native_sql_preflight(versions=GOOD_STACK)
    with pytest.raises(TypeError):
        grpo_ptc.native_sql_preflight(arms=("ptc", "bash"))
    with pytest.raises(TypeError):
        grpo_ptc.native_sql_preflight(require_runtime=lambda: None)


@pytest.mark.parametrize("entrypoint", ["preflight", "native_sql_preflight"])
@pytest.mark.parametrize("steps", [1, 17, 200])
def test_both_preflights_check_frontier_before_stack_or_config(
    tmp_path, monkeypatch, entrypoint, steps,
):
    def forbidden(*args, **kwargs):
        pytest.fail("missing frontier reached stack/runtime/config work")

    monkeypatch.setattr(grpo_ptc, "require_stack", forbidden)
    monkeypatch.setattr(grpo_ptc, "require_native_runtime", forbidden)
    monkeypatch.setattr(grpo_ptc, "training_config", forbidden)
    with pytest.raises(guards.PreconditionUnmet, match="no frontier taskset"):
        getattr(grpo_ptc, entrypoint)(root=tmp_path, steps=steps)


@pytest.mark.parametrize("entrypoint", ["preflight", "native_sql_preflight"])
@pytest.mark.parametrize("steps", [1, 17, 200])
def test_optimized_preflight_sources_keep_missing_frontier_closed(
    tmp_path, entrypoint, steps,
):
    """Compile actual gate/entrypoint source with -O semantics, without processes."""
    guard_namespace = dict(vars(guards))
    exec(compile(inspect.getsource(guards.require_frontier_taskset),
                 "<optimized-frontier>", "exec", optimize=1), guard_namespace)
    tree = ast.parse(pathlib.Path(grpo_ptc.__file__).read_text())
    tree.body = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == entrypoint
    ]
    assert len(tree.body) == 1
    namespace = dict(vars(grpo_ptc))
    namespace["require_frontier_taskset"] = guard_namespace["require_frontier_taskset"]
    exec(compile(tree, "<optimized-preflight>", "exec", optimize=1), namespace)
    with pytest.raises(guards.PreconditionUnmet, match="no frontier taskset"):
        namespace[entrypoint](root=tmp_path, steps=steps)


@pytest.mark.parametrize("steps", [1, 17, 200])
def test_native_preflight_uses_fixed_arms_and_preserves_requested_steps(
    tmp_path, monkeypatch, steps,
):
    calls = []
    monkeypatch.setattr(grpo_ptc, "require_native_runtime", lambda: calls.append("native"))

    def forbidden(*args, **kwargs):
        pytest.fail("native preflight called the default Transformers<5 enforcer")

    monkeypatch.setattr(grpo_ptc, "require_stack", forbidden)
    root = gate_open_root(tmp_path)
    config = grpo_ptc.native_sql_preflight(root=root, steps=steps)
    assert calls == ["native"]
    assert config == grpo_ptc.training_config(grpo_ptc.TRAINED_ARMS_DEFAULT, steps=steps)


def test_native_preflight_keeps_real_runtime_blockers_after_frontier(tmp_path, monkeypatch):
    from train import native_runtime

    def absent(name):
        raise native_runtime.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(native_runtime.metadata, "version", absent)
    with pytest.raises(native_runtime.NativeRuntimeError) as caught:
        grpo_ptc.native_sql_preflight(root=gate_open_root(tmp_path))
    assert caught.value.report["issues"]["unresolved"]
    assert all(not caught.value.report[key] for key in (
        "candidate_approved", "dependency_graph_verified", "abi_verified",
        "runtime_verified", "training_verified", "launch_authorized",
    ))


@pytest.mark.parametrize("entrypoint", ["preflight", "native_sql_preflight"])
@pytest.mark.parametrize("fault", ["tools", "completion_cap", "turn_budget"])
def test_both_preflights_refuse_each_shared_scientific_fault(
    tmp_path, monkeypatch, entrypoint, fault,
):
    root = gate_open_root(tmp_path)
    kwargs = {"root": root}
    if entrypoint == "native_sql_preflight":
        # Wiring test only: the real native runtime remains blocked elsewhere.
        monkeypatch.setattr(grpo_ptc, "require_native_runtime", lambda: None)
    else:
        kwargs["versions"] = GOOD_STACK
    if fault == "completion_cap":
        config = grpo_ptc.training_config()
        config["max_completion_length"] -= 1
        monkeypatch.setattr(grpo_ptc, "training_config", lambda *args, **kwargs: config)
        invariant = 2
    else:
        environment = grpo_ptc.environment_factory(root)()
        if fault == "tools":
            environment.tools = (grpo_ptc.THE_TOOL_SCHEMA,) * 2
            invariant = 1
        else:
            environment.max_turns += 1
            invariant = 3
        monkeypatch.setattr(grpo_ptc, "environment_factory",
                            lambda root: lambda: environment)
    with pytest.raises(guards.InvariantViolation, match=f"invariant {invariant}"):
        getattr(grpo_ptc, entrypoint)(**kwargs)


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


def test_the_probe_renders_prompts_as_a_conversation_not_a_bare_string(tmp_path):
    """A bare string is tokenized verbatim, so no generation prompt reaches the model.

    v8's evidence: `clipped_ratio` 1.000, `mean_length == max_length == 3072`,
    `mean_terminated_length` 0.0, all eight rollouts masked, reward never exercised,
    completions that echoed the schema and kept writing. The model had no stop token
    to emit because the template that places it was never applied.
    """
    path = tmp_path / "prompts.jsonl"
    path.write_text(json.dumps({"prompt": "who?", "answer": "ada", "db_id": "x"}) + "\n")
    (row,) = probe.load_prompts(path)
    assert isinstance(row["prompt"], list) and len(row["prompt"]) == 1
    assert row["prompt"][0] == {"role": "user", "content": "who?"}
    assert row["answer"] == "ada" and row["db_id"] == "x"  # reward kwargs survive


def test_both_configs_disable_thinking_by_the_same_value():
    """The probe's geometry is about the policy the run trains. Thinking on in one
    and off in the other is two policies, and nothing would raise."""
    p = probe.probe_config()
    r = grpo_ptc.training_config(("ptc",))
    assert p["chat_template_kwargs"] == r["chat_template_kwargs"] == {"enable_thinking": False}
    # a copy, not the module dict: a caller mutating one config must not reach the other
    p["chat_template_kwargs"]["enable_thinking"] = True
    assert probe.CHAT_TEMPLATE_KWARGS == {"enable_thinking": False}
    assert grpo_ptc.training_config(("ptc",))["chat_template_kwargs"]["enable_thinking"] is False


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
    at_floor = {**GOOD_MANIFEST, "n_tasks": guards.MIN_FRONTIER_TASKS,
                "measurement": {**GOOD_MANIFEST["measurement"],
                                "retention": guards.MIN_FRONTIER_TASKS / 198}}
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


def test_the_context_fits_the_prompt_and_a_full_completion():
    """Six runs died because the sequence length was smaller than the prompt.

    Unsloth defaults `max_seq_length` to 2048 and the probe never set it, while
    `max_completion_length` was 3072 -- larger than the model's entire context. The two
    were chosen in different places by different reasoning and never multiplied
    together. v6's log: `Input IDs of shape (8, 2612) with length 2612 > the model's max
    sequence length of 2048`.

    The prompt therefore consumed the whole context with nothing left to generate into,
    so completions were empty or instantly truncated (reward 0.0,
    frac_reward_zero_std 1.0) and `mask_truncated_completions=True` masked all of them,
    which is the unexplained `grad_norm` of 0.0 in every run.
    """
    from train.dead_group_probe import (MEASURED_MAX_PROMPT_TOKENS, max_seq_length_for,
                                        probe_config)

    for g in (4, 8):
        config = probe_config(5, g)
        cap = config["max_completion_length"]
        seq = max_seq_length_for(cap)
        assert seq >= MEASURED_MAX_PROMPT_TOKENS + cap, (g, seq, cap)
        # the old pairing must now be impossible to express
        assert seq > 2048, seq
        assert cap < seq, (cap, seq)
        assert seq % 1024 == 0, seq


def test_a_longer_cap_moves_the_context_with_it():
    """Derived rather than stored, so the two cannot drift apart again. This is the
    property that was missing, not the specific 6144."""
    from train.dead_group_probe import MEASURED_MAX_PROMPT_TOKENS, max_seq_length_for

    small, large = max_seq_length_for(1024), max_seq_length_for(4096)
    assert large > small
    for cap in (512, 1024, 3072, 4258, 8192):
        assert max_seq_length_for(cap) >= MEASURED_MAX_PROMPT_TOKENS + cap, cap


def test_the_verdict_rejudges_a_file_under_the_window_it_ran_with(tmp_path, capsys):
    """v10 ran window 3 and its header could not say so; re-read as window 1 it would
    report an abort the run itself never applied."""
    rows = [{"probe": "dead_group", "taskset_id": "t", "abort_window": 3}]
    rows += [step(v) for v in (0.9, 0.4, 0.4, 0.4, 0.4)]
    path = tmp_path / "m.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert V.main([str(path)]) == 0
    assert "abort window: 3" in capsys.readouterr().out
    assert V.main([str(path), "--abort-window", "1"]) == 1
