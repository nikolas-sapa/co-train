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
    MEASURED_PRICE_IN,
    MEASURED_PRICE_OUT,
    MEASURED_PRICE_PER_CALL_CEILING,
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
           new_input=0, truncated=False):
    """`usage` is the provider-REPORTED figure (`Trace.usage`); `new_input` is the deduplicated
    `Trace.num_input_tokens`. They are deliberately separate arguments because
    conflating them is the bug these tests exist to prevent."""
    return NS(reward=reward, nodes=[NS(message=m) for m in nodes],
              is_completed=completed, stop_condition=stop, usage=usage,
              num_input_tokens=new_input, is_truncated=truncated)


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


# --------------------------------------- the budget must not be the independent variable

def test_a_truncated_rollout_is_counted_and_flagged_loudly():
    """The confound that nearly rigged this experiment.

    `ledger`'s aggregation tier needs 40 tool calls. The PTC arm spends ONE program on
    that; the bash arm spends ~42 turns. With the old `max_turns: 4` the bash arm was
    capped at turn 4 and scored 0.0 across the whole tier — the tier specifically built
    to be where PTC could win. The rig would have manufactured its own result, and the
    number would have looked like a finding.

    `session.py:98` stops with `stop_condition="max_turns"` and the task scores 0.0 for
    a budget reason indistinguishable from incapacity. So truncation is counted and
    announced, never averaged silently into the score.
    """
    capped = NS(reward=0.0, nodes=[], is_completed=True, stop_condition="max_turns",
                is_truncated=True, usage=None, num_input_tokens=0)
    out = summarize([_record([capped, _trace(1.0)])], "bash", "ledger")
    assert out.n_truncated == 1
    table = render([out])
    assert "A BUDGET LIMIT BOUND" in table
    assert "INVALID" in table
    assert "TRUNCATED (budget)" in table


@pytest.mark.parametrize("stop", ["max_turns", "max_input_tokens", "max_output_tokens",
                                  "compaction_failed"])
def test_every_framework_limit_counts_as_truncation(stop):
    """`Trace.is_truncated` covers all of them, and each one produces the same false
    zero. Pinned so a new limit is not quietly excluded."""
    t = NS(reward=0.0, nodes=[], is_completed=True, stop_condition=stop,
           is_truncated=True, usage=None, num_input_tokens=0)
    assert summarize([_record([t])], "bash", "l").n_truncated == 1


def test_an_ordinary_zero_is_not_reported_as_truncation():
    """A model that answered and got it wrong is a real measurement. Conflating that
    with a budget cap would discard the actual failures."""
    out = summarize([_record([_trace(0.0)])], "ptc", "ledger")
    assert out.n_truncated == 0
    assert "A BUDGET LIMIT BOUND" not in render([out])


# ------------------------------------------------- the budget that left no mark
#
# A harness that enforces its OWN budget returns normally: `is_truncated` is False and
# `stop_condition` is "agent_completed". The first real run printed `TRUNCATED 0` while
# the cap bound 11 of 14 PTC rollouts, so these pin both directions -- a cap that bound
# must be loud, and a rollout that merely used its last turn must not be.


def _budget_nodes(turns: int, *, last_calls: bool):
    """`turns` assistant messages. `last_calls` decides whether the final one was still
    asking for a tool call, which is the whole discriminator: `harness.py:313-316`
    breaks out of the loop on an assistant message with no tool calls, so a rollout
    that answers voluntarily cannot have been stopped by the budget."""
    nodes = [_msg("system", "s"), _msg("user", "u")]
    for i in range(turns):
        final = i == turns - 1
        calls = [] if (final and not last_calls) else [NS(name="run_program")]
        nodes.append(_msg("assistant", "<answer>x</answer>" if not calls else None, calls))
        if calls:
            nodes.append(_msg("tool", "r1"))
    return nodes


def _summarize_one(trace, budget=8):
    return summarize([_record([trace])], "ptc", "ledger", turn_budget=budget)


def test_a_harness_internal_turn_cap_is_never_reported_as_zero_truncations():
    """The defect that let a binding cap print as a clean run."""
    out = _summarize_one(_trace(reward=0.0, nodes=_budget_nodes(8, last_calls=True),
                                stop="agent_completed", truncated=False))
    assert out.n_budget_exhausted == 1
    assert out.n_truncated == 1, "a budget that bound must not read as untruncated"
    assert "A BUDGET LIMIT BOUND" in render([out])


def test_a_rollout_that_answers_on_its_last_allowed_turn_is_not_truncated():
    """The false positive that would void good runs. Spending the budget is not the
    same as being stopped by it: this rollout used all 8 turns and then ANSWERED, so it
    finished. Counting it trips the `nothing truncated` rig gate and prints "the score
    comparison is INVALID" over a healthy run."""
    out = _summarize_one(_trace(reward=1.0, nodes=_budget_nodes(8, last_calls=False),
                                stop="agent_completed", truncated=False))
    assert out.n_budget_exhausted == 0
    assert out.n_truncated == 0
    assert "A BUDGET LIMIT BOUND" not in render([out])


def test_a_rollout_that_stops_under_budget_is_not_truncated():
    """The other end, or the positive case could pass by flagging everything."""
    out = _summarize_one(_trace(reward=1.0, nodes=_budget_nodes(7, last_calls=True),
                                stop="agent_completed", truncated=False))
    assert out.n_budget_exhausted == 0
    assert out.n_truncated == 0


def test_the_budget_check_reads_the_frameworks_own_turn_count():
    """`Trace.num_turns` (`trace.py:656`) counts SAMPLED nodes, which is the quantity
    the budget is actually enforced on. Recounting `role == "assistant"` is a different
    number, and the two diverge on any trace the recount cannot see. Here the recount
    says 2 and the framework says 8: reading the recount leaves this untruncated."""
    trace = _trace(reward=0.0, nodes=_budget_nodes(2, last_calls=True),
                   stop="agent_completed", truncated=False)
    trace.num_turns = 8
    out = _summarize_one(trace)
    assert out.n_budget_exhausted == 1
    assert out.n_truncated == 1


def test_the_budget_banner_does_not_claim_the_rollouts_scored_zero():
    """A budget-exhausted rollout can spend the whole budget and still score 1.0, so
    the banner must not assert it scored 0.0 -- the number means "bounded", not
    "failed"."""
    out = _summarize_one(_trace(reward=1.0, nodes=_budget_nodes(8, last_calls=True),
                                stop="agent_completed", truncated=False))
    note = render([out])
    assert "A BUDGET LIMIT BOUND" in note
    assert out.score_mean == 1.0
    assert "scored 0.0" not in note


# ----------------------------------------------------- reportable-stability
#
# The project publishes CIs to one decimal place. A bound that moves between seeds would
# make that digit arbitrary, which is the same class of defect as a p-value computed under
# the wrong formula -- and it would be invisible, because every run passes the same seed.

def test_the_bootstrap_resamples_the_MEAN_and_not_a_median_or_a_sum():
    """Recomputed from the definition. A CI on the wrong statistic would still look like a
    plausible interval."""
    values = [1.0, 0.0, 0.0, 1.0, 0.0]
    import random as _random
    rng = _random.Random(3)
    draws = sorted(sum(rng.choices(values, k=5)) / 5 for _ in range(1000))
    got = bootstrap_ci(values, iters=1000, seed=3)
    assert got[0] == pytest.approx(draws[int(0.025 * 1000)])
    assert got[1] == pytest.approx(draws[min(999, int(0.975 * 1000))])


def test_published_intervals_do_not_move_across_seeds():
    """Run 2h's headline interval is [-35.7, +0.0] pp on fourteen paired tasks: two
    discordant pairs for PTC, twelve ties. Nothing in the report is seed-dependent, so a
    change here means a published bound acquired a random component."""
    diffs = [-1.0] * 2 + [0.0] * 12
    for seed in range(20):
        lo, hi = bootstrap_ci(diffs, seed=seed)
        assert round(lo * 100, 1) == -35.7, seed
        assert round(hi * 100, 1) == 0.0, seed


def test_a_small_unanimous_sample_is_stable_too():
    """Every discordant pair favouring one arm -- the cheapest case to detect, and the one
    where a sparse bootstrap could wobble most."""
    diffs = [-1.0] * 6
    bounds = {(round(bootstrap_ci(diffs, seed=s)[0] * 100, 1),
               round(bootstrap_ci(diffs, seed=s)[1] * 100, 1)) for s in range(20)}
    assert len(bounds) == 1, f"interval moved across seeds: {bounds}"


# ------------------------------------------------------------------ the cost co-primary
#
# Cost per solved task is now this project's headline finding -- the one result that held
# across every run, including an exact score tie -- and it had no test that checked the
# arithmetic against a known answer. Three of the project's twelve faults were in the code
# that READS results rather than the code that produces them, so an unverified formula
# behind the headline is the exact shape of defect this project keeps finding in itself.
#
# Verified 2026-10-08 by summing `calls[].usage` straight out of three runs' traces and
# comparing to the printed table: all six prompt-token totals matched to the token and all
# six cost-per-solved figures to the published cent. These lock that in.

def _cost(prompt: int, completion: int, cached: int = 0,
          price_in: float = 0.09, price_out: float = 0.18,
          price_cached: float | None = None) -> float:
    """The formula from `summarize`, written out independently."""
    cached_rate = price_in if price_cached is None else price_cached
    return ((prompt / 1e6) * price_in
            + (cached / 1e6) * cached_rate
            + (completion / 1e6) * price_out)


def test_cost_uses_billed_prompt_tokens_not_the_deduplicated_count():
    """The field choice IS the finding. `Trace.num_input_tokens` is the *new* tokens per
    call, deduplicated across branches -- training-relevant and not what anyone charges.
    A provider bills the whole prompt every call, and the bash arm re-sends the whole
    transcript once per turn, so the deduplicated count understates precisely the arm that
    spends more. On run 3d: billed 2,229,481 against a deduplicated 64,261, a factor of 35.
    Using the wrong field would have erased the one co-primary PTC wins on."""
    billed, deduplicated = 2229481, 64261
    assert _cost(billed, 33793) == pytest.approx(0.2067, abs=5e-5)
    assert _cost(deduplicated, 33793) < 0.02, (
        "the deduplicated field gives a cost an order of magnitude too low")


@pytest.mark.parametrize("run,prompt,completion,solved,cost,per_solved", [
    # (run, billed prompt, completion, solved, total cost, cost per solved) -- every value
    # read off the published table and re-derived from that run's own traces.
    ("2h bash", 660842, 9518, 12, 0.0612, 0.0051),
    ("2h ptc", 82664, 7928, 14, 0.0089, 0.0006),
    ("3c bash", 2245429, 30384, 21, 0.2076, 0.0099),
    ("3c ptc", 241561, 24892, 20, 0.0262, 0.0013),
    ("3d bash", 2229481, 33793, 23, 0.2067, 0.0090),
    ("3d ptc", 208780, 24646, 23, 0.0232, 0.0010),
])
def test_the_published_cost_figures_reproduce(run, prompt, completion, solved,
                                              cost, per_solved):
    got = _cost(prompt, completion)
    assert got == pytest.approx(cost, abs=5e-5), run
    assert got / solved == pytest.approx(per_solved, abs=5e-5), run


def test_the_token_ratio_claim_is_8_0_to_10_7x():
    """Published as "8 to 10 times" until this was checked, which understated run 3d. The
    ratio grows with taskset size because bash's transcript grows per turn and PTC's does
    not, so a claim stated as a fixed range needs re-deriving whenever a run is added."""
    ratios = [660842 / 82664, 2245429 / 241561, 2229481 / 208780]
    assert min(ratios) == pytest.approx(7.99, abs=0.01)
    assert max(ratios) == pytest.approx(10.68, abs=0.01)
    assert all(r >= 7.9 for r in ratios)


def test_cost_is_flagged_as_an_upper_bound_when_cache_pricing_is_unknown():
    """A cached token billed at the full input rate overstates cost. The flag exists so a
    cost advantage is never claimed on an unstated discount."""
    full = _cost(1_000_000, 0, cached=1_000_000)
    discounted = _cost(1_000_000, 0, cached=1_000_000, price_cached=0.009)
    assert full > discounted
    assert full == pytest.approx(0.18)


# ------------------------------------------- the price itself, measured not assumed

def test_the_measured_relay_rates_are_pinned_against_silent_drift():
    """The rates are a measurement, so they get pinned like one.

    Every real-mode run in this project was launched at 0.09 in / 0.18 out and nothing
    had checked either number against the endpoint. Both are low: measured 2026-10-09/10
    from `x-balance-remaining` deltas, input is $0.2186/M (three large-prompt calls with
    2-3 token completions: 0.2207, 0.2174, 0.2177) and output is $0.670/M (OLS over six
    calls with completions of 340-2,284 tokens at a fixed 15-17 token prompt). A silent
    edit to either constant moves every re-derived dollar figure, so the multipliers
    against the launch defaults are pinned too.
    """
    assert MEASURED_PRICE_IN == pytest.approx(0.2186, abs=5e-4)
    assert MEASURED_PRICE_OUT == pytest.approx(0.670, abs=5e-3)
    assert MEASURED_PRICE_IN / 0.09 == pytest.approx(2.43, abs=0.02)
    assert MEASURED_PRICE_OUT / 0.18 == pytest.approx(3.72, abs=0.02)
    # Six calls at 8 prompt + 2 completion tokens did not move the balance at all, and
    # the same OLS puts the intercept at $2e-6. No material per-call fee exists, which
    # is load-bearing in the opposite direction to the obvious guess: bash bills 10.7x
    # the prompt tokens on 4.6x the calls, so a per-call fee would land relatively
    # harder on PTC and SHRINK the cost gap rather than widening it.
    assert MEASURED_PRICE_PER_CALL_CEILING < 2e-5


def test_a_table_priced_under_the_measured_rate_says_so_in_the_table():
    """The drift guard that fires at run time rather than in CI.

    A dollar figure with no rate beside it is what made `$0.0051 per solved task`
    quotable for three weeks at 41% of the real input rate. The table now names the rate
    it used and flags the gap, so the next person to read a run output cannot miss it.
    """
    at_launch = summarize([_record([_trace(usage=_usage(1_000_000, 1_000))])],
                          "bash", "ledger", price_in=0.09, price_out=0.18)
    assert at_launch.price_in == 0.09 and at_launch.price_out == 0.18
    flagged = render([at_launch])
    assert "PRICED UNDER THE MEASURED RATE" in flagged
    assert "2.4x on input" in flagged
    assert "$0.09/M in, $0.18/M out" in flagged

    at_measured = summarize([_record([_trace(usage=_usage(1_000_000, 1_000))])],
                            "bash", "ledger", price_in=MEASURED_PRICE_IN,
                            price_out=MEASURED_PRICE_OUT)
    assert "PRICED UNDER THE MEASURED RATE" not in render([at_measured])


def test_an_unpriced_run_is_not_also_flagged_as_underpriced():
    """Cost is already reported as unknown without a price (§2), and a second loud note
    about a rate nobody supplied would bury the first."""
    table = render([summarize([_record([_trace(usage=_usage(1_000, 10))])],
                              "ptc", "ledger")])
    assert "PRICED UNDER THE MEASURED RATE" not in table
    assert "cost computed at" not in table

# ------------------- a tool-call success rate of exactly 1.000 is an instrument claim
# `tool_success_rate = 1.0 - tool_failures / tool_calls`, and failures are detected by
# prefix-matching the strings `ptc/harness.py` emits (`FAILURE_PREFIXES`). The module
# docstring already warns that a format drift "shows up as a tool-call success rate
# that jumps to 100%", and the prefixes are pinned against drift in the STRING. Nothing
# caught the other way in: the strings intact and the error channel absent from the loop
# entirely. Measured on run 3d: the PTC arm is 74 failures in 156 calls (0.5256), while
# the bash arm is 0 in 822 -- its four tools return JSON or shell output and can never
# match, so its 1.000 is a floor artifact, not a performance figure.


def _json_only_arm(n_calls):
    """An arm whose tool results can never match FAILURE_PREFIXES -- the shape both the
    bash arm and a mis-wired PTC arm produce."""
    nodes = []
    for i in range(n_calls):
        nodes.append(_msg("assistant", tool_calls=[NS(function=NS(name="ledger_get"))]))
        nodes.append(_msg("tool", content='{"id": "r00", "kind": "invoice"}'))
    return [_record([_trace(nodes=nodes)])]


def test_a_perfect_tool_call_rate_over_many_calls_is_flagged():
    """Zero failures in 20+ calls is likelier an absent error channel than a perfect
    policy: at any true failure rate >= 10%, P(0 in 20) <= 0.9**20 = 12%."""
    r = summarize(_json_only_arm(40), arm="suspect", taskset="t")
    assert r.tool_calls == 40 and r.tool_failures == 0
    assert r.tool_success_rate == 1.0
    out = render([r])
    assert "NO TOOL FAILURE WAS DETECTABLE" in out, out[:400]


def test_the_flag_stays_quiet_when_the_error_channel_is_live():
    """The PTC arm on run 3d: 74 failures in 156 calls. A measured rate must not be
    flagged, or the warning is noise and gets switched off."""
    nodes = []
    for i in range(156):
        nodes.append(_msg("assistant", tool_calls=[NS(function=NS(name="run_program"))]))
        nodes.append(_msg("tool", content="rejected: name 'foo' is not defined"
                                          if i < 74 else '{"id": "r00"}'))
    r = summarize([_record([_trace(nodes=nodes)])], arm="ptc", taskset="t")
    assert r.tool_failures == 74 and abs(r.tool_success_rate - 0.5256) < 0.001
    assert "NO TOOL FAILURE WAS DETECTABLE" not in render([r])


def test_a_short_run_at_1_000_is_not_flagged():
    """Below the floor a perfect rate is unremarkable, and flagging it would train the
    reader to ignore the line that matters."""
    r = summarize(_json_only_arm(5), arm="short", taskset="t")
    assert r.tool_success_rate == 1.0
    assert "NO TOOL FAILURE WAS DETECTABLE" not in render([r])
