"""The metrics are the experiment's output, so they get attacked like the grader.

A wrong number here is worse than a crash: it reads as a finding. `docs/pre-registration.md`
§2 exists because choosing the metric after the fact chooses the result, and a rig that
computes the pre-registered set incorrectly does the same thing while looking rigorous.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.metrics import (  # noqa: E402
    FAILURE_PREFIXES,
    SHELL_TOOLS,
    ArmResult,
    bootstrap_ci,
    render,
    summarize,
)


def _msg(role, content=None, tool_calls=None):
    return NS(role=role, content=content, tool_calls=tool_calls or [])


def _usage(prompt=0, completion=0, cached=None, reasoning=None, cost=None):
    return NS(prompt_tokens=prompt, completion_tokens=completion,
              cached_input_tokens=cached, reasoning_tokens=reasoning, cost=cost)


def _trace(reward=1.0, nodes=(), completed=True, stop="complete", usage=None,
           new_input=0):
    """`usage` is the BILLED figure (`Trace.usage`); `new_input` is the deduplicated
    `Trace.num_input_tokens`. They are deliberately separate arguments because
    conflating them is the bug these tests exist to prevent."""
    return NS(reward=reward, nodes=[NS(message=m) for m in nodes],
              is_completed=completed, stop_condition=stop, usage=usage,
              num_input_tokens=new_input)


def _record(traces, errors=()):
    return NS(traces=list(traces), errors=list(errors))


def _conversation(tool_name="ledger_get", result="ok"):
    return [
        _msg("system", "s"), _msg("user", "u"),
        _msg("assistant", None, [NS(name=tool_name)]),
        _msg("tool", result),
        _msg("assistant", "<answer>x</answer>"),
    ]


# --------------------------------------------------------------- the primary

def test_score_is_the_mean_over_traces():
    out = summarize([_record([_trace(1.0), _trace(0.0), _trace(1.0)])], "ptc", "ledger")
    assert out.n_tasks == 3
    assert out.score_mean == pytest.approx(2 / 3)
    assert out.n_solved == 2


def test_a_confidence_interval_is_reported_not_just_a_mean():
    """§3 compares arms by whether their CIs are disjoint. A point estimate cannot
    answer that, so a missing interval is a missing result."""
    out = summarize([_record([_trace(1.0) for _ in range(10)] +
                             [_trace(0.0) for _ in range(10)])], "ptc", "ledger")
    assert out.score_ci is not None
    low, high = out.score_ci
    assert low <= out.score_mean <= high
    assert low > 0.0 and high < 1.0


def test_no_interval_is_invented_from_a_single_task():
    """An interval from one point is a number pretending to be evidence."""
    assert summarize([_record([_trace(1.0)])], "ptc", "ledger").score_ci is None
    assert bootstrap_ci([1.0]) is None
    assert bootstrap_ci([]) is None


def test_the_bootstrap_is_reproducible():
    """An interval that differs between two reads of the same traces cannot be
    reported in a paper."""
    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0]
    assert bootstrap_ci(values) == bootstrap_ci(values)


def test_a_degenerate_sample_gives_a_degenerate_interval():
    assert bootstrap_ci([1.0] * 8) == (1.0, 1.0)


# ------------------------------------------------------------ cost, honestly

def test_cost_is_unknown_rather_than_zero_when_usage_is_missing():
    """The false green this project keeps finding. A canned policy reports no usage;
    printing `$0.00` would read as "free" instead of "not measured"."""
    out = summarize([_record([_trace(usage=None)])], "ptc", "ledger",
                    price_in=1.0, price_out=2.0)
    assert out.usage_reported is False
    assert out.cost_total is None
    assert out.cost_per_solved is None


def test_cost_is_unknown_when_no_price_is_supplied():
    """§2: token count is NOT a cost proxy (-38.4% tokens, +6.8% cost, r=0.15). With no
    price there is no cost, and inventing one from tokens is the cited mistake."""
    out = summarize([_record([_trace(usage=_usage(1000, 500))])], "ptc", "ledger")
    assert out.usage_reported is True
    assert out.cost_total is None


def test_cost_per_solved_task_not_per_task():
    """The co-primary is cost per *successful* task: an arm that fails cheaply is not
    cheap."""
    out = summarize([_record([_trace(1.0, usage=_usage(2_000_000, 1_000_000)),
                              _trace(0.0, usage=_usage(0, 0))])],
                    "ptc", "ledger", price_in=3.0, price_out=15.0)
    assert out.cost_total == pytest.approx(2 * 3.0 + 1 * 15.0)
    assert out.cost_per_solved == pytest.approx(21.0 / 1)


def test_no_division_by_zero_when_nothing_was_solved():
    out = summarize([_record([_trace(0.0, usage=_usage(1000, 1000))])], "ptc", "ledger",
                    price_in=1.0, price_out=1.0)
    assert out.cost_total is not None
    assert out.cost_per_solved is None


# -------------------------------------------------------------- the stability

def test_stop_conditions_and_errors_are_counted():
    """Per 2603.01209 this is the axis an effect is most likely to appear on at all,
    so a run that scored the same but failed differently must be visible."""
    out = summarize([
        _record([_trace(stop="complete"), _trace(stop="error", completed=False)],
                errors=[NS(type="HarnessError")]),
    ], "ptc", "ledger")
    assert out.stop_conditions == {"complete": 1, "error": 1}
    assert out.error_types == {"HarnessError": 1}
    assert out.n_completed == 1


# --------------------------------------------- tool-call success and shell share

def test_tool_calls_and_failures_are_counted():
    """H4's leading indicator: the source paper's untrained baseline is PTC 65.2% vs
    bash 92.1%, and §4 predicts this moves before score does."""
    nodes = [
        _msg("assistant", None, [NS(name="ledger_get")]), _msg("tool", "ok"),
        _msg("assistant", None, [NS(name="ledger_get")]), _msg("tool", "rejected: nope"),
    ]
    out = summarize([_record([_trace(nodes=nodes)])], "ptc", "ledger")
    assert out.tool_calls == 2
    assert out.tool_failures == 1
    assert out.tool_success_rate == 0.5


@pytest.mark.parametrize("content", ["rejected: import", "error: ZeroDivisionError",
                                     "REJECTED: shouting", "  error: padded"])
def test_every_harness_failure_prefix_is_recognised(content):
    """Pinned so a reworded harness message shows up as a suspiciously perfect tool
    success rate instead of silently inflating the secondary outcome."""
    nodes = [_msg("assistant", None, [NS(name="t")]), _msg("tool", content)]
    assert summarize([_record([_trace(nodes=nodes)])], "ptc", "l").tool_failures == 1


def test_an_ordinary_result_is_not_counted_as_a_failure():
    nodes = [_msg("assistant", None, [NS(name="t")]), _msg("tool", "no such record")]
    out = summarize([_record([_trace(nodes=nodes)])], "ptc", "l")
    assert out.tool_failures == 0
    assert out.tool_success_rate == 1.0


def test_shell_call_share_separates_the_shell_from_typed_tools():
    """OpenForgeRL measured RL moving this 22.6% -> 13.9% and read it as the model
    learning to reach for the specialised tool. Directly comparable only if the shell
    is distinguished from the catalog."""
    nodes = [
        _msg("assistant", None, [NS(name="bash")]), _msg("tool", "ok"),
        _msg("assistant", None, [NS(name="ledger_get")]), _msg("tool", "ok"),
    ]
    out = summarize([_record([_trace(nodes=nodes)])], "bash", "ledger")
    assert out.shell_calls == 1
    assert out.shell_call_share == 0.5


def test_the_ptc_arm_has_no_shell_by_construction():
    """`run_program` is not a shell. If this ever counts as one the arm has stopped
    being PTC."""
    assert "run_program" not in SHELL_TOOLS
    nodes = [_msg("assistant", None, [NS(name="run_program")]), _msg("tool", "ok")]
    out = summarize([_record([_trace(nodes=nodes)])], "ptc", "ledger")
    assert out.shell_call_share == 0.0


def test_rates_are_absent_rather_than_zero_when_no_tool_was_called():
    """A run with no tool calls has an undefined success rate, not a perfect one."""
    out = summarize([_record([_trace(nodes=[_msg("assistant", "hi")])])], "ptc", "l")
    assert out.tool_calls == 0
    assert out.tool_success_rate is None
    assert out.shell_call_share is None


# ------------------------------------------------------------------ rendering

def test_every_preregistered_outcome_appears_in_the_table():
    """The point of §2 is that the co-primaries are reported ALWAYS, never chosen
    afterwards. Dropping one from the table is choosing."""
    table = render([summarize([_record([_trace()])], "bash", "ledger"),
                    summarize([_record([_trace()])], "ptc", "ledger")])
    for label in ("score (primary)", "score 95% CI", "cost / solved",
                  "tool success rate", "shell-call share", "stop conditions",
                  "errors", "completed"):
        assert label in table, label


def test_unknown_cost_is_flagged_loudly_in_the_table():
    table = render([summarize([_record([_trace()])], "ptc", "ledger")])
    assert "UNKNOWN, not zero" in table


def test_the_table_does_not_declare_a_winner():
    """Descriptive only. §2's whole concern is that whoever reads the numbers reads
    them against predictions made in advance, not against a verdict printed here."""
    table = render([summarize([_record([_trace(1.0)])], "bash", "l"),
                    summarize([_record([_trace(0.0)])], "ptc", "l")]).lower()
    # "tool failures" is a legitimate row label, so the check is for verdict words,
    # not for any occurrence of "fail". The first draft of this test flagged its own
    # metric name — a reminder that a crude assertion fails on the honest case too.
    for verdict in ("winner", " wins", "better", "worse", "reverses the ordering",
                    "confirms", "significant"):
        assert verdict not in table, verdict


def test_rendering_survives_an_empty_run():
    assert render([]) == "(no results)"
    assert isinstance(ArmResult(arm="a", taskset="b").as_dict(), dict)


# ------------------------------------- billed vs deduplicated tokens (the big one)

def test_cost_uses_billed_prompt_tokens_not_the_deduplicated_count():
    """The bug this section exists for, caught by reading verifiers' source rather
    than by spending money on a run.

    `Trace.num_input_tokens` is `max(0, call.input_tokens - previous_total)` summed
    over calls — the NEW tokens per call. Nobody bills that. A provider charges the
    whole prompt on every call, so a four-turn rollout pays for the conversation four
    times. Here the billed figure is 10x the deduplicated one, and cost must follow the
    billed figure.

    It biased the co-primary directionally, which is why it matters: the bash arm makes
    more calls than the PTC arm (one tool call per turn vs one program), so it re-sends
    more prompt, and the deduplicated count hides precisely that. Cost is the axis
    pre-reg §1 records untrained PTC already winning on.
    """
    out = summarize([_record([_trace(usage=_usage(prompt=1_000_000, completion=0),
                                     new_input=100_000)])],
                    "bash", "ledger", price_in=1.0, price_out=1.0)
    assert out.prompt_tokens == 1_000_000
    assert out.new_input_tokens == 100_000
    assert out.cost_total == pytest.approx(1.0), "cost must follow the billed tokens"


def test_the_deduplicated_count_is_still_reported_separately():
    """It is the training-relevant number and worth having — just never as cost."""
    out = summarize([_record([_trace(usage=_usage(500, 100), new_input=42)])], "p", "l")
    assert out.new_input_tokens == 42
    table = render([out])
    assert "new input tokens*" in table
    assert "DEDUPLICATED" in table


def test_a_provider_reported_cost_beats_our_arithmetic():
    """The provider already knows its own cache discounts, tiers and rounding."""
    out = summarize([_record([_trace(usage=_usage(1_000_000, 1_000_000, cost=0.07))])],
                    "ptc", "l", price_in=999.0, price_out=999.0)
    assert out.cost_total == pytest.approx(0.07)
    assert out.cost_from_provider is True
    assert "provider-reported" in render([out])


def test_cached_tokens_are_counted_and_flagged_as_an_upper_bound():
    """`Usage.prompt_tokens` EXCLUDES cache reads (types.py), so ignoring
    `cached_input_tokens` would undercount the prompt entirely. Cache reads are usually
    discounted, so charging them at the full input rate overstates — which is declared
    rather than hidden."""
    out = summarize([_record([_trace(usage=_usage(prompt=1_000_000, completion=0,
                                                 cached=1_000_000))])],
                    "ptc", "l", price_in=1.0, price_out=1.0)
    assert out.cached_tokens == 1_000_000
    assert out.cost_total == pytest.approx(2.0)
    assert out.cost_is_upper_bound is True
    assert "UPPER BOUND" in render([out])


def test_a_cache_price_removes_the_upper_bound_caveat():
    out = summarize([_record([_trace(usage=_usage(1_000_000, 0, cached=1_000_000))])],
                    "ptc", "l", price_in=1.0, price_out=1.0, price_cached=0.1)
    assert out.cost_total == pytest.approx(1.1)
    assert out.cost_is_upper_bound is False


def test_reasoning_tokens_are_reported_but_not_billed_twice():
    """types.py: reasoning tokens are a SUBSET of completion tokens. Adding them to the
    cost again would inflate every reasoning model's bill."""
    out = summarize([_record([_trace(usage=_usage(0, 1_000_000, reasoning=600_000))])],
                    "ptc", "l", price_in=1.0, price_out=1.0)
    assert out.reasoning_tokens == 600_000
    assert out.cost_total == pytest.approx(1.0)


def test_usage_is_summed_across_traces_and_records():
    out = summarize([_record([_trace(usage=_usage(100, 10)), _trace(usage=_usage(200, 20))]),
                     _record([_trace(usage=_usage(700, 70))])], "ptc", "l")
    assert out.prompt_tokens == 1000
    assert out.completion_tokens == 100
