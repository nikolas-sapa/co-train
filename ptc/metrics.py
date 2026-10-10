"""The outcomes `docs/pre-registration.md` §2 commits to reporting, computed from traces.

The pre-registration's first finding is that **the metric picks the winner**: at
TAC/GPT-5.5 the untrained PTC arm already beats bash on cost and tokens while losing on
score. A rig that reports score alone therefore does not measure the pre-registered
experiment -- it measures whichever outcome someone chooses to look at afterwards, which
is the failure mode §2 exists to prevent.

So all of it is computed together, every run, from one pass over the traces:

- **Primary:** task score by the taskset's own deterministic grader.
- **Co-primary 1:** cost per *successful* task. Cost is tokens x an explicitly supplied
  price, never inferred from token count alone -- §2 cites -38.4% tokens with +6.8% cost
  (r=0.15), so treating tokens as a cost proxy is the specific mistake being avoided.
- **Co-primary 2:** stability -- completion rate, stop conditions, error classes. Per
  arXiv 2603.01209 this is the axis on which an effect is most likely to appear at all.
- **Secondary 3:** tool-call success rate. The untrained baseline in the source paper is
  PTC 65.2% vs bash 92.1%, and §4's H4 predicts this moves *before* score does.
- **Secondary 4:** shell-call share, directly comparable to OpenForgeRL's 22.6% -> 13.9%.

Everything here is descriptive. No hypothesis is tested and no winner is declared; the
comparison is a human reading two columns against pre-registered predictions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any

# A tool result the harness itself refused or failed to run, as opposed to one that
# returned an unhelpful answer. Format-dependent by nature: these are the prefixes
# `ptc/harness.py` emits. A harness whose failures look different needs a line here, and
# `test_metrics.py` pins the ones that exist so a silent format drift shows up as a
# tool-call success rate that jumps to 100%.
FAILURE_PREFIXES = ("rejected:", "error:")

# A POSITIVE control, not an equality test on the rate: it asserts that the instrument's
# known fault rate is PRESENT. The prefixes above are pinned against drift in the STRING;
# this catches the other way in — strings intact, error channel absent from the loop.
#
# Two reference rates, because which one applies depends on what you are reading:
#   untrained correct PTC arm, 70/156 = 44.87% rejected -> P(0 in 20)  = 6.7e-06
#   a SUCCESSFULLY trained arm at H4's target of 0.921  -> P(0 in 20)  = 19.5%
#                                                          P(0 in 156) = 3.4e-06
# So at eval-scale call counts this cannot false-positive on success, but on a 20-call
# smoke run it can. `render` summarizes a completed eval run and has no step index, so
# anything computing this PER TRAINING STEP must pin it to step 0, where a correct
# pipeline cannot yet have learned its way to zero failures.
MIN_CALLS_FOR_PERFECT_RATE = 20

# Names that denote a general-purpose shell rather than a typed tool.
SHELL_TOOLS = ("bash", "shell", "sh", "run_shell", "execute_bash")

# What the relay actually charges, measured 2026-10-09/10. Every real-mode run so far was
# launched with `--price-in 0.09 --price-out 0.18` and nothing had ever checked those two
# numbers against the endpoint; both are low. Derivation, all from `x-balance-remaining`
# deltas on `deepseek-v4-flash` (`ptc/relay_audit.py` holds the rest of what that endpoint
# turned out to be):
#
#   input      three large-prompt calls with 2-3 token completions, so the output term is
#              negligible: $0.2207, $0.2174, $0.2177 per M reported prompt tokens.
#   output     six calls at a fixed 15-17 token prompt with completions of 340-2,284
#              tokens; OLS over (completion_tokens, charge) gives the slope below.
#   per call   six calls at 8 prompt + 2 completion tokens did not move the balance at
#              all, so any per-call fee is under $1.7e-5; the same OLS puts the intercept
#              at $2e-6. There is no material per-call component, which matters because a
#              per-call fee would NOT have favoured the arm that makes fewer calls: bash
#              bills 10.7x the prompt tokens on only 4.6x the calls, so a fee lands
#              relatively harder on PTC and shrinks the cost gap rather than widening it.
#
# These are the RELAY's rates on one date, not a provider price list, and the quantity
# they multiply is the relay's own token count (see `prompt_tokens` below). Re-measure
# with `ptc/relay_audit.py`'s probes before trusting them on a later run.
MEASURED_PRICE_IN = 0.2186
MEASURED_PRICE_OUT = 0.670
MEASURED_PRICE_PER_CALL_CEILING = 1.7e-5
MEASURED_PRICE_ENDPOINT = "vyceai.com/v1 deepseek-v4-flash 2026-10-10"


def bootstrap_ci(values: list[float], iters: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> tuple[float, float] | None:
    """Percentile bootstrap CI for a mean. Seeded, so a reported interval is
    reproducible from the same traces rather than being differently random each run.

    §3 compares arms by whether their CIs are disjoint, which a mean alone cannot
    answer. Returns None below 2 samples, because an interval from one point is a
    number pretending to be evidence.

    ponytail: the percentile bootstrap, not BCa. It needs no scipy, and at the sample
    sizes here the refinement is far smaller than the between-task variance.
    """
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(rng.choices(values, k=n)) / n for _ in range(iters)
    )
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (lo, hi)


@dataclass
class ArmResult:
    """One arm on one taskset. Field names match the pre-registration's own labels."""

    arm: str
    taskset: str
    n_tasks: int = 0

    # Primary
    score_mean: float | None = None
    score_ci: tuple[float, float] | None = None
    n_solved: int = 0

    # Co-primary 1 — cost. The provider-reported per-call count, NOT the deduplicated
    # one: a provider charges the whole prompt on every call, and `Trace.num_input_tokens`
    # reports only each call's increment over the previous one. See `summarize`.
    #
    # "Provider-reported" is as strong as this gets, and on the endpoint every real-mode
    # run used it is weaker than it sounds. Measured 2026-10-09: the relay's
    # `usage.prompt_tokens` equals `cl100k_base` over the raw message content *exactly*
    # on short prompts, carries no chat-template overhead at all, returns the identical
    # count for the same prompt under two different model ids, and exceeds every standard
    # tokenizer by 43-56% above ~3.8k tokens. It is computed relay-side and it is not
    # internally consistent. It is still the only count anyone bills from here, so it
    # stays the basis of the co-primary — but the table must not call it "billed".
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    new_input_tokens: int = 0
    """The deduplicated count (`Trace.num_input_tokens`). Reported because it is the
    training-relevant number, and kept apart from the reported figure above so the two
    can never be confused again."""
    usage_reported: bool = False
    cost_total: float | None = None
    cost_per_solved: float | None = None
    cost_from_provider: bool = False
    cost_is_upper_bound: bool = False
    price_in: float = 0.0
    price_out: float = 0.0
    """The rates the cost above was computed at, carried so the table can name them.
    Every run to date priced itself at the launch flags and the table printed a dollar
    figure without recording what rate produced it, which is how `$0.0051 per solved
    task` came to be quoted with no way to tell it was computed at 41% of the real
    input rate."""

    # Co-primary 2 — stability
    n_completed: int = 0
    n_truncated: int = 0
    """Rollouts stopped by a framework limit (turns, tokens, compaction) rather than by
    the model finishing. These are NOT capability measurements: the task scores 0.0 for
    a budget reason indistinguishable from incapacity, so any non-zero count invalidates
    the affected tasks and is reported loudly rather than averaged into the score."""
    stop_conditions: dict[str, int] = field(default_factory=dict)
    error_types: dict[str, int] = field(default_factory=dict)
    n_budget_exhausted: int = 0
    """Rollouts STOPPED BY the turn budget: they spent it and were still asking for a
    tool call. Counted separately because a harness that enforces its own budget never
    sets `is_truncated` -- `PTCHarness` just falls out of `for _ in range(max_turns)`
    and the episode reports `stop_condition="agent_completed"`, so the first real run
    printed `TRUNCATED 0` while the cap was binding on 11 of 14 PTC rollouts. Spending
    the budget is NOT enough to qualify: a rollout that answers on its last allowed turn
    finished, and counting it would void a healthy run. These fold into `n_truncated` so
    they fire the same loud note instead of sitting in a column somebody has to notice."""

    # Secondary 3 and 4
    tool_calls: int = 0
    tool_failures: int = 0
    tool_success_rate: float | None = None
    shell_calls: int = 0
    shell_call_share: float | None = None

    turns: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_failure(content: Any) -> bool:
    text = str(content or "").strip().lower()
    return text.startswith(FAILURE_PREFIXES)


def summarize(records: list[Any], arm: str, taskset: str,
              price_in: float = 0.0, price_out: float = 0.0,
              price_cached: float | None = None,
              turn_budget: int | None = None) -> ArmResult:
    """Fold a run's records into the pre-registered outcome set.

    **Cost is computed from BILLED tokens, which is not the obvious field.**
    `Trace.num_input_tokens` is `max(0, call.input_tokens - previous_total)` summed over
    calls (`trace.py:min_new_input_tokens`) -- the *new* tokens per call, deduplicated
    across branches. That is the training-relevant number and it is not what anyone
    charges: a provider bills the entire prompt on every call, and a multi-turn rollout
    re-sends the whole conversation each time.

    Using it would have biased the cost co-primary **directionally**. The bash arm
    takes one tool call per turn where the PTC arm submits one program, so bash makes
    more calls and re-sends more prompt. The deduplicated count hides exactly that
    difference, understating the higher-turn arm -- and cost is precisely the axis where
    pre-reg §1 records untrained PTC already *beating* bash. The wrong field would have
    muddied the one co-primary PTC wins on.

    `Trace.usage` (`Usage.aggregate`) sums provider-reported usage per call, which is the
    figure anyone bills from. Two further traps in that model: `prompt_tokens` **excludes**
    cache reads, which live in `cached_input_tokens` and are usually billed at a
    discount, and `reasoning_tokens` are already a subset of `completion_tokens` and
    must not be added again. A third, found 2026-10-09 and recorded on `prompt_tokens`
    above: on a relay the reported count need not come from the model's tokenizer at all.

    Prices are dollars per million tokens and must be supplied. Absent them, cost is
    reported as unknown rather than as zero -- a run whose provider reported no usage
    would otherwise print `$0.00`, which reads as "free" instead of "not measured".
    A provider-reported `cost` is preferred over any arithmetic here. Whatever rates are
    passed are recorded on the result and named in the table, and `render` says so when
    they sit under `MEASURED_PRICE_IN`/`_OUT`: the dollar figures in this project were
    quoted for three weeks at 41% of the input rate and 27% of the output rate the
    endpoint turned out to charge, and nothing in the table showed it.
    """
    result = ArmResult(arm=arm, taskset=taskset)
    result.price_in = price_in
    result.price_out = price_out
    scores: list[float] = []

    provider_cost = 0.0
    provider_cost_seen = False

    for record in records:
        for error in getattr(record, "errors", None) or []:
            name = getattr(error, "type", None) or "unknown"
            result.error_types[name] = result.error_types.get(name, 0) + 1

        for trace in getattr(record, "traces", None) or []:
            result.n_tasks += 1
            result.new_input_tokens += getattr(trace, "num_input_tokens", 0) or 0
            usage = getattr(trace, "usage", None)
            if usage is not None:
                result.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                result.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
                result.cached_tokens += getattr(usage, "cached_input_tokens", None) or 0
                result.reasoning_tokens += getattr(usage, "reasoning_tokens", None) or 0
                if getattr(usage, "cost", None) is not None:
                    provider_cost += usage.cost
                    provider_cost_seen = True
            reward = getattr(trace, "reward", None)
            if reward is not None:
                scores.append(float(reward))
                if float(reward) > 0:
                    result.n_solved += 1
            if getattr(trace, "is_completed", False):
                result.n_completed += 1
            stop = getattr(trace, "stop_condition", None) or "unset"
            result.stop_conditions[stop] = result.stop_conditions.get(stop, 0) + 1

            trace_turns = 0
            last_assistant_called_tools = False
            for node in getattr(trace, "nodes", None) or []:
                message = getattr(node, "message", None)
                if message is None:
                    continue
                role = getattr(message, "role", None)
                calls = getattr(message, "tool_calls", None) or []
                if role == "assistant":
                    result.turns += 1
                    trace_turns += 1
                    last_assistant_called_tools = bool(calls)
                    for call in calls:
                        result.tool_calls += 1
                        name = (getattr(call, "name", None) or "").lower()
                        if name in SHELL_TOOLS:
                            result.shell_calls += 1
                elif role == "tool" and _is_failure(getattr(message, "content", None)):
                    result.tool_failures += 1

            # Checked AFTER the node walk, because a harness-enforced budget leaves no
            # mark on the trace: `PTCHarness` falls out of `for _ in range(max_turns)`
            # and the episode still reports `agent_completed`.
            #
            # Prefer the framework's own `Trace.num_turns` (`trace.py:656`, sampled nodes)
            # over the recount above, so this measures the same quantity the budget is
            # enforced on. The recount is the fallback for a trace that predates it.
            #
            # BOTH conditions are required, because spending the budget is not the same
            # as being stopped by it: a rollout that answers on its last allowed turn
            # ends by `break` with no tool calls (`harness.py:313-316`) and is FINISHED,
            # not truncated. Counting that would trip the rig gate and print "the score
            # comparison is INVALID" over a healthy run -- the same class of error as the
            # silent zero this replaced, just inverted.
            turns = getattr(trace, "num_turns", trace_turns)
            spent_budget = (turn_budget is not None
                            and turns >= turn_budget
                            and last_assistant_called_tools)
            if spent_budget:
                result.n_budget_exhausted += 1
            if getattr(trace, "is_truncated", False) or spent_budget:
                result.n_truncated += 1

    if scores:
        result.score_mean = sum(scores) / len(scores)
        result.score_ci = bootstrap_ci(scores)
    if result.tool_calls:
        result.tool_success_rate = 1.0 - result.tool_failures / result.tool_calls
        result.shell_call_share = result.shell_calls / result.tool_calls

    # Usage is only believable if the provider actually reported some. A canned policy
    # reports zero, and so does a provider that omits the usage block.
    result.usage_reported = (result.prompt_tokens + result.completion_tokens
                             + result.cached_tokens) > 0

    if provider_cost_seen:
        # The provider's own number beats any arithmetic here: it already knows its
        # cache discounts, tiers and rounding.
        result.cost_total = provider_cost
        result.cost_from_provider = True
    elif result.usage_reported and (price_in or price_out):
        cached_rate = price_in if price_cached is None else price_cached
        result.cost_is_upper_bound = result.cached_tokens > 0 and price_cached is None
        result.cost_total = (
            (result.prompt_tokens / 1e6) * price_in
            + (result.cached_tokens / 1e6) * cached_rate
            + (result.completion_tokens / 1e6) * price_out
        )
    if result.cost_total is not None and result.n_solved:
        result.cost_per_solved = result.cost_total / result.n_solved

    return result


def render(results: list[ArmResult]) -> str:
    """Two columns, every pre-registered outcome, no winner declared."""
    if not results:
        return "(no results)"

    def cell(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, tuple):
            return f"[{value[0]:.3f}, {value[1]:.3f}]"
        if isinstance(value, float):
            return f"{value:.4f}" if value < 1 else f"{value:.3f}"
        if isinstance(value, dict):
            return ", ".join(f"{k}={v}" for k, v in sorted(value.items())) or "—"
        return str(value)

    rows = [
        ("tasks", "n_tasks"), ("score (primary)", "score_mean"),
        ("score 95% CI", "score_ci"), ("solved", "n_solved"),
        ("completed", "n_completed"), ("TRUNCATED (budget)", "n_truncated"),
        ("  of which stopped by turn budget", "n_budget_exhausted"),
        ("stop conditions", "stop_conditions"),
        ("errors", "error_types"), ("prompt tokens (relay-reported)", "prompt_tokens"),
        ("cached tokens", "cached_tokens"),
        ("completion tokens", "completion_tokens"),
        ("reasoning tokens", "reasoning_tokens"),
        ("new input tokens*", "new_input_tokens"), ("cost total", "cost_total"),
        ("cost / solved", "cost_per_solved"), ("tool calls", "tool_calls"),
        ("tool failures", "tool_failures"), ("tool success rate", "tool_success_rate"),
        ("shell-call share", "shell_call_share"), ("assistant turns", "turns"),
    ]
    width = max(len(label) for label, _ in rows) + 2
    header = "".ljust(width) + "".join(r.arm.rjust(22) for r in results)
    lines = [header, "-" * len(header)]
    for label, attr in rows:
        lines.append(label.ljust(width) +
                     "".join(cell(getattr(r, attr)).rjust(22) for r in results))
    notes = ["* new input tokens is the DEDUPLICATED count (training-relevant). "
             "Cost uses the relay-reported prompt tokens above it."]
    # The rate is part of the result, not a launch detail. A dollar figure with no rate
    # beside it was quotable for three weeks at 41% of what the endpoint charges, and the
    # table gave no way to notice. Named on every run, flagged when it is under the
    # measured rate, and the flag names the measurement so it can be re-checked.
    priced = [r for r in results if r.price_in or r.price_out]
    if priced:
        r0 = priced[0]
        notes.append(f"cost computed at ${r0.price_in:g}/M in, ${r0.price_out:g}/M out "
                     f"(supplied at launch).")
        if (r0.price_in < MEASURED_PRICE_IN * 0.99
                or r0.price_out < MEASURED_PRICE_OUT * 0.99):
            under = (f"{MEASURED_PRICE_IN / r0.price_in:.1f}x on input"
                     if r0.price_in else "unmeasurable on input, which was passed as 0")
            notes.insert(0, (
                f"*** PRICED UNDER THE MEASURED RATE: {MEASURED_PRICE_ENDPOINT} charges "
                f"${MEASURED_PRICE_IN:g}/M in and ${MEASURED_PRICE_OUT:g}/M out, so "
                f"every cost figure below is low by roughly {under}. The arm-to-arm "
                f"RATIO survives a uniform rate; the absolute dollars do not."))
    # An errored rollout is NOT a zero score -- nothing ran. An unreachable endpoint, a
    # rejected key or a provider fault lands here as a table of zeros that reads exactly
    # like a model that solved nothing, which is the shape this project keeps getting
    # bitten by: a clean-looking result measured against a target that was never there.
    errored = {r.arm: r.stop_conditions.get("error", 0) for r in results
               if r.stop_conditions.get("error")}
    if errored:
        notes.insert(0, "*** ROLLOUTS ERRORED: " + ", ".join(
            f"{arm} {n}" for arm, n in errored.items()) +
            ". Those rollouts scored 0.0 because nothing ran, not because the arm "
            "failed the task. Every number in this table is meaningless until the run "
            "completes — check the endpoint, the key and the provider first.")
    # A rate of exactly 1.000 over a non-trivial number of calls is far more likely an
    # absent error channel than a perfect policy. Measured on run 3d: the PTC arm is 74
    # failures in 156 calls (0.5256), the bash arm 0 in 822 — its tools (`bash`,
    # `ledger_get`, `ledger_ids`, `ledger_links_to`) return JSON or shell output and can
    # never match FAILURE_PREFIXES, so its 1.000 is a floor, not a measurement. Secondary
    # 3 therefore compares a measured rate against an unmeasurable one. Flagged, not
    # raised, per `2026-10-08-warn-rather-than-raise-a-fail-loud-default`.
    undetectable = {r.arm: r.tool_calls for r in results
                    if r.tool_calls >= MIN_CALLS_FOR_PERFECT_RATE and not r.tool_failures}
    if undetectable:
        notes.insert(0, "*** NO TOOL FAILURE WAS DETECTABLE: " + ", ".join(
            f"{arm} 0 of {n} calls" for arm, n in undetectable.items()) +
            f". `tool_success_rate` is 1.0 - failures/calls, and a failure is a result "
            f"whose text starts with {' or '.join(repr(p) for p in FAILURE_PREFIXES)} — "
            f"the strings `ptc/harness.py` emits. An arm whose tools return JSON or shell "
            f"output cannot produce one, so 1.000 here may mean the error channel is NOT "
            f"IN THE LOOP rather than that nothing failed. Check what tools the arm was "
            f"given before reading this as a capability: a tool-call success rate is only "
            f"comparable between arms whose failures are both visible to this predicate. "
            f"A tool loop that wraps exceptions as {{'error': ...}} (trl 1.13.0 does, at "
            f"grpo_trainer.py:2029) yields a BRACE-first string this predicate cannot see, "
            f"so a harness must FORMAT its own rejections rather than raise them.")
    truncated = {r.arm: r.n_truncated for r in results if r.n_truncated}
    if truncated:
        notes.insert(0, "*** A BUDGET LIMIT BOUND: " + ", ".join(
            f"{arm} {n}" for arm, n in truncated.items()) +
            ". Those rollouts were still asking for tool calls when the budget ran out, "
            "so whatever they scored is a floor and not a capability measurement — a "
            "rollout can exhaust the budget and still score 1.0. The score comparison "
            "is INVALID until the budget is raised: the limit, not the arm, is what "
            "bounded them.")
    if not all(r.usage_reported for r in results):
        notes.append("usage was not reported by at least one arm — cost is UNKNOWN, "
                     "not zero.")
    if any(r.cost_is_upper_bound for r in results):
        notes.append("cached tokens were billed at the full input rate — cost is an "
                     "UPPER BOUND. Pass --price-cached for the real figure.")
    if any(r.cost_from_provider for r in results):
        notes.append("cost is provider-reported, not computed from prices.")
    lines.append("")
    lines.extend(f"NOTE: {n}" for n in notes)
    return "\n".join(lines)
