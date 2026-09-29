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

# Names that denote a general-purpose shell rather than a typed tool.
SHELL_TOOLS = ("bash", "shell", "sh", "run_shell", "execute_bash")


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

    # Co-primary 1 — cost. Billed tokens, NOT the deduplicated count: a provider
    # charges the whole prompt on every call, and `Trace.num_input_tokens` reports
    # only each call's increment over the previous one. See `summarize`.
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    new_input_tokens: int = 0
    """The deduplicated count (`Trace.num_input_tokens`). Reported because it is the
    training-relevant number, and kept apart from the billed figure above so the two
    can never be confused again."""
    usage_reported: bool = False
    cost_total: float | None = None
    cost_per_solved: float | None = None
    cost_from_provider: bool = False
    cost_is_upper_bound: bool = False

    # Co-primary 2 — stability
    n_completed: int = 0
    stop_conditions: dict[str, int] = field(default_factory=dict)
    error_types: dict[str, int] = field(default_factory=dict)

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
              price_cached: float | None = None) -> ArmResult:
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

    `Trace.usage` (`Usage.aggregate`) sums provider-reported usage per call, which is
    the billed figure. Two further traps in that model: `prompt_tokens` **excludes**
    cache reads, which live in `cached_input_tokens` and are usually billed at a
    discount, and `reasoning_tokens` are already a subset of `completion_tokens` and
    must not be added again.

    Prices are dollars per million tokens and must be supplied. Absent them, cost is
    reported as unknown rather than as zero -- a run whose provider reported no usage
    would otherwise print `$0.00`, which reads as "free" instead of "not measured".
    A provider-reported `cost` is preferred over any arithmetic here.
    """
    result = ArmResult(arm=arm, taskset=taskset)
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

            for node in getattr(trace, "nodes", None) or []:
                message = getattr(node, "message", None)
                if message is None:
                    continue
                role = getattr(message, "role", None)
                calls = getattr(message, "tool_calls", None) or []
                if role == "assistant":
                    result.turns += 1
                    for call in calls:
                        result.tool_calls += 1
                        name = (getattr(call, "name", None) or "").lower()
                        if name in SHELL_TOOLS:
                            result.shell_calls += 1
                elif role == "tool" and _is_failure(getattr(message, "content", None)):
                    result.tool_failures += 1

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
        ("completed", "n_completed"), ("stop conditions", "stop_conditions"),
        ("errors", "error_types"), ("prompt tokens (billed)", "prompt_tokens"),
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
             "Cost uses billed prompt tokens above it."]
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
