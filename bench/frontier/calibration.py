"""Pure offline diagnostics for declared, grouped binary evidence.

Provenance and fingerprints are caller declarations, not authentication. Neither
the empirical summaries nor the hypothetical IID calculation establishes
independence, confidence bounds, or a policy improvement.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from numbers import Rational, Real


_MAX_COUNT = 256
_MAX_DECIMAL_DIGITS = 8192
_MAX_RATIONAL_BITS = 32768
_STRATUM_FIELDS = (
    "task_id", "task_fingerprint", "arm", "phase", "corpus_id", "split_id",
    "run_id", "policy_revision", "scorer_id",
)
_IDENTITY_FIELDS = ("sample_id", "group_id") + _STRATUM_FIELDS


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a nonempty string")
    if not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise TypeError(f"{name} must be a finite real number, not bool")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _count(value: object, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not bool")
    if not minimum <= value <= _MAX_COUNT:
        raise ValueError(f"{name} must be between {minimum} and {_MAX_COUNT}")
    return int(value)


def _dead_probability(p: float, group_g: int) -> float:
    return p**group_g + (1 - p)**group_g


def _ratio(value: Real | Decimal) -> Fraction:
    if isinstance(value, Decimal):
        _, digits, exponent = value.as_tuple()
        expanded = max(len(digits) + max(0, exponent), 1 + max(0, -exponent))
        if expanded > _MAX_DECIMAL_DIGITS:
            raise ValueError("Decimal representation exceeds the diagnostic size limit")
    elif isinstance(value, Rational):
        bits = max(int(value.numerator).bit_length(), int(value.denominator).bit_length())
        if bits > _MAX_RATIONAL_BITS:
            raise ValueError("rational representation exceeds the diagnostic size limit")
    if isinstance(value, (Rational, Decimal)):
        result = Fraction(value)
    else:
        ratio = getattr(value, "as_integer_ratio", None)
        result = Fraction(*ratio()) if callable(ratio) else Fraction(float(value))
    bits = max(result.numerator.bit_length(), result.denominator.bit_length())
    if bits > _MAX_RATIONAL_BITS:
        raise ValueError("rational representation exceeds the diagnostic size limit")
    return result


def _log_probabilities(p: Fraction) -> tuple[float, float]:
    """Keep the smaller tail before converting either complement to float."""
    small = min(p, 1 - p)
    approximation = float(small)
    log_small = (
        math.log(approximation) if approximation >= sys.float_info.min
        else math.log(small.numerator) - math.log(small.denominator)
    )
    log_large = math.log1p(-approximation)
    return (log_small, log_large) if p <= Fraction(1, 2) else (log_large, log_small)


def _ratio_text(value: Fraction) -> str:
    # Decimal(int) is exact and avoids weakening Python's global int-string
    # safety limit for the rest of the process.
    numerator = format(Decimal(value.numerator), "f")
    if value.denominator == 1:
        return numerator
    return numerator + "/" + format(Decimal(value.denominator), "f")


def exact_screen(
    p: Real | Decimal, *, screen_n: int = 4, group_g: int = 4,
    ceiling: Real | Decimal = .60,
) -> dict:
    """Binomial expectation after screening on plug-in dead probability <= ceiling.

    Counts are bounded operationally, not as a training-group restriction.
    Log-space weights avoid intermediate binomial-power underflow. An acceptance
    probability below float representability is returned as zero, with no
    conditional estimate. Exact rational input strings distinguish interior
    probabilities from rounded numeric display fields.
    """
    screen_n = _count(screen_n, "screen_n", 1)
    group_g = _count(group_g, "group_g", 2)
    probability = _number(p, "p")
    threshold = _number(ceiling, "ceiling")
    exact_p = _ratio(p)
    exact_ceiling = _ratio(ceiling)
    if not 0 <= exact_p <= 1:
        raise ValueError("p must be in [0, 1]")
    if not 0 < exact_ceiling < 1:
        raise ValueError("ceiling must be in (0, 1)")
    accepted = []
    if 0 < exact_p < 1:
        log_p, log_q = _log_probabilities(exact_p)
        for successes in range(screen_n + 1):
            rate = Fraction(successes, screen_n)
            exact_plugin = rate**group_g + (1 - rate)**group_g
            if exact_plugin <= exact_ceiling:
                log_weight = (
                    math.log(math.comb(screen_n, successes))
                    + successes * log_p
                    + (screen_n - successes) * log_q
                )
                accepted.append((log_weight, float(exact_plugin)))
    # At p=0/1 the only positive-mass outcome has plug-in dead probability 1,
    # which can never pass a ceiling strictly below 1.
    acceptance = 0.0
    conditional = None
    if accepted:
        largest = max(weight for weight, _ in accepted)
        weights = [math.exp(weight - largest) for weight, _ in accepted]
        total = math.fsum(weights)
        acceptance = min(1.0, math.exp(largest + math.log(total)))
        if acceptance > 0:
            conditional = math.fsum(
                weight * plugin for weight, (_, plugin) in zip(weights, accepted)
            ) / total

    return {
        "assumption": "Hypothetical IID Bernoulli samples with fixed success probability p",
        "p": probability,
        "p_exact": _ratio_text(exact_p),
        "screen_n": screen_n,
        "group_g": group_g,
        "ceiling": threshold,
        "ceiling_exact": _ratio_text(exact_ceiling),
        "true_dead_probability": _dead_probability(probability, group_g),
        "acceptance_probability": acceptance,
        "conditional_plugin_dead_estimate": conditional,
    }


@dataclass(frozen=True)
class SampleEvidence:
    """One declared outcome; status is retained verbatim, validity is explicit."""

    sample_id: str
    group_id: str
    task_id: str
    task_fingerprint: str
    arm: str
    phase: str
    corpus_id: str
    split_id: str
    run_id: str
    policy_revision: str
    scorer_id: str
    score: Real | Decimal | None
    status: str
    valid: bool

    def __post_init__(self) -> None:
        _validate_sample(self)


def _validate_sample(sample: SampleEvidence) -> None:
    if not isinstance(sample, SampleEvidence):
        raise TypeError("samples must contain SampleEvidence records")
    for name in _IDENTITY_FIELDS:
        _text(getattr(sample, name), name)
    if sample.arm not in ("ptc", "bash"):
        raise ValueError("arm must be ptc or bash")
    if sample.phase not in ("screen", "confirmation"):
        raise ValueError("phase must be screen or confirmation")
    _text(sample.status, "status")
    if type(sample.valid) is not bool:
        raise TypeError("valid must be a bool")
    if sample.score is None:
        if sample.valid:
            raise ValueError("a valid sample requires a binary score")
    else:
        _number(sample.score, "score")
        if sample.score not in (0, 1):
            raise ValueError("score must be binary 0 or 1")


def _items(values: Iterable, name: str) -> Iterable:
    if isinstance(values, (str, bytes, bytearray, Mapping)):
        raise TypeError(f"{name} must be a collection, not text or a mapping")
    try:
        return iter(values)
    except TypeError as exc:
        raise TypeError(f"{name} must be iterable") from exc


def _counts(groups: list[dict]) -> dict:
    usable = [group for group in groups if group["usable"]]
    statuses = Counter(status for group in groups for status in group["statuses"])
    all_samples = sum(len(group["sample_ids"]) for group in groups)
    usable_samples = sum(len(group["sample_ids"]) for group in usable)
    return {
        "all_group_count": len(groups),
        "usable_group_count": len(usable),
        "invalid_group_count": len(groups) - len(usable),
        "all_sample_count": all_samples,
        "usable_sample_count": usable_samples,
        "invalid_sample_count": all_samples - usable_samples,
        "status_counts": dict(statuses),
        "valid_successes": sum(sum(group["scores"]) for group in usable),
    }


def summarize_groups(
    samples: Iterable[SampleEvidence], *, group_g: int,
    evaluation_task_ids: Iterable[str],
) -> dict:
    """Validate whole groups and reduce only within declared task/config strata.

    A single invalid member makes every member unusable for reward denominators.
    Such groups remain visible, with original statuses/scores/validities and a
    null dead classification. Aggregate counts are provided, but estimates are
    taskwise only: no pooled cross-task/phase plug-in probability is invented.
    Input order determines group, sample, and stratum output order.
    """
    group_g = _count(group_g, "group_g", 2)
    evaluation_ids = set()
    for task_id in _items(evaluation_task_ids, "evaluation_task_ids"):
        _text(task_id, "evaluation task ID")
        evaluation_ids.add(task_id)

    members_by_group = {}
    seen = set()
    for sample in _items(samples, "samples"):
        # Revalidate at admission, even if a caller bypassed frozen construction.
        _validate_sample(sample)
        if sample.sample_id in seen:
            raise ValueError(f"duplicate sample_id: {sample.sample_id}")
        seen.add(sample.sample_id)
        if sample.task_id in evaluation_ids:
            raise ValueError(f"evaluation-task overlap: {sample.task_id}")
        members = members_by_group.setdefault(sample.group_id, [])
        if members and any(
            getattr(sample, field) != getattr(members[0], field)
            for field in _STRATUM_FIELDS
        ):
            raise ValueError(f"mixed identity/configuration in group: {sample.group_id}")
        members.append(sample)
        if len(members) > group_g:
            raise ValueError(f"group {sample.group_id} exceeds group_g")

    groups = []
    strata_groups = {}
    for group_id, members in members_by_group.items():
        if len(members) != group_g:
            raise ValueError(f"group {group_id} must have exactly {group_g} members")
        first = members[0]
        identity = {field: getattr(first, field) for field in _STRATUM_FIELDS}
        usable = all(sample.valid for sample in members)
        scores = [None if sample.score is None else int(sample.score) for sample in members]
        dead = (sum(scores) in (0, group_g)) if usable else None
        group = {
            **identity,
            "group_id": group_id,
            "sample_ids": [sample.sample_id for sample in members],
            "scores": scores,
            "statuses": [sample.status for sample in members],
            "validities": [sample.valid for sample in members],
            "usable": usable,
            "dead": dead,
        }
        groups.append(group)
        key = tuple(identity[field] for field in _STRATUM_FIELDS)
        strata_groups.setdefault(key, []).append(group)

    strata = []
    for identity, members in strata_groups.items():
        counts = _counts(members)
        usable_count = counts["usable_group_count"]
        denominator = counts["usable_sample_count"]
        empirical = None
        plugin = None
        if usable_count:
            empirical = sum(group["dead"] is True for group in members) / usable_count
            plugin = _dead_probability(counts["valid_successes"] / denominator, group_g)
        strata.append({
            **dict(zip(_STRATUM_FIELDS, identity)),
            **counts,
            "empirical_dead_group_fraction": empirical,
            "plugin_dead_estimate": plugin,
        })

    return {
        "schema_version": 1,
        "group_g": group_g,
        **_counts(groups),
        "groups": groups,
        "strata": strata,
    }
