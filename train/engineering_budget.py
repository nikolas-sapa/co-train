"""Pure offline rate/deadline planning; estimate only, never approval or billing proof.

Rates are caller-supplied exact Decimal observations carrying pricing identity
(source string plus observation epoch second). No live lookup happens here and
no provider guarantee, enforced cap or stop-acknowledgement billing proof is
implied: requested resources bound the plan, never actual charged usage.
Arithmetic mirrors the strict idiom of train/qualification_costs.py without
altering that closure. stdlib-only, no import-time work, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import sys

RUNTIME_CONTEXTS = ("function", "sandbox")
_ROLE_UNITS = {
    "gpu": "USD/gpu-second",
    "cpu": "USD/physical-core-second",
    "ram": "USD/GiB-second",
}
_MAX_GPU_SECONDS = 1800
_DEFAULT_MAX_OBSERVATION_AGE_SECONDS = 2592000  # 30 days


@dataclass(frozen=True)
class RateObservation:
    rate_usd: Decimal
    rate_unit: str
    source: str
    observed_at_seconds: int


@dataclass(frozen=True)
class ResourceRates:
    runtime_context: str
    gpu: RateObservation
    cpu: RateObservation
    ram: RateObservation


@dataclass(frozen=True)
class GpuWorkload:
    gpu_count: int
    cpu_cores: int
    ram_gib: Decimal
    duration_seconds: int


@dataclass(frozen=True)
class PreparationAccount:
    incurred_cash_usd: Decimal
    incurred_credits_usd: Decimal
    remaining_estimate_usd: Decimal


@dataclass(frozen=True)
class AncillaryEstimates:
    transfer_usd: Decimal
    storage_usd: Decimal
    termination_reserve_usd: Decimal


@dataclass(frozen=True)
class BudgetTerms:
    total_ceiling_usd: Decimal
    reserve_usd: Decimal


@dataclass(frozen=True)
class EngineeringBudgetPlan:
    planned_ceiling_usd: Decimal
    incurred_preparation_gross_usd: Decimal
    remaining_estimate_usd: Decimal
    total_estimated_gross_usd: Decimal
    remaining_plan_allowance_usd: Decimal
    planned_gpu_deadline_seconds: int
    breakdown: tuple[tuple[str, Decimal], ...]
    scope: str = "planning_estimate_only_no_approval_no_provider_cap_no_billing_proof"


def _number(value: object, name: str) -> Fraction:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} requires finite Decimal, UNKNOWN blocks")
    # Bound representation before arithmetic, mirroring qualification_costs.
    if (
        sys.implementation.name != "cpython"
        or getattr(Decimal.__sizeof__, "__objclass__", None) is not Decimal
        or Decimal.__sizeof__(value) > 256
    ):
        raise ValueError(f"{name} decimal representation exceeds supported size limits")
    parts = value.as_tuple()
    if len(parts.digits) > 96 or abs(parts.exponent) > 96:
        raise ValueError(f"{name} decimal representation exceeds arithmetic limits")
    coefficient = 0
    for digit in parts.digits:
        coefficient = coefficient * 10 + digit
    if parts.sign and coefficient:
        raise ValueError(f"{name} must be nonnegative")
    if parts.exponent >= 0:
        return Fraction(coefficient * 10**parts.exponent)
    return Fraction(coefficient, 10**(-parts.exponent))


def _integer(value: object, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < int(positive) or value.bit_length() > 63:
        raise ValueError(f"{name} requires bounded {'positive' if positive else 'nonnegative'} integer")
    return value


def _decimal(value: Fraction) -> Decimal:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    scale = max(twos, fives)
    if denominator != 1 or scale > 512:
        raise ValueError("result exceeds exact terminating representation")
    coefficient = value.numerator * 2**(scale - twos) * 5**(scale - fives)
    digits = tuple(int(digit) for digit in str(coefficient))
    return Decimal((0, digits, -scale))


def _observation(value: object, role: str, now: int, max_age: int) -> Fraction:
    name = f"rates.{role}"
    if type(value) is not RateObservation:
        raise ValueError(f"{name} requires RateObservation, UNKNOWN blocks")
    if type(value.rate_unit) is not str or value.rate_unit != _ROLE_UNITS[role]:
        raise ValueError(f"{name}.rate_unit must be exactly {_ROLE_UNITS[role]}")
    if type(value.source) is not str or not value.source:
        raise ValueError(f"{name}.source requires nonempty pricing observation identity")
    rate = _number(value.rate_usd, f"{name}.rate_usd")
    if rate <= 0:
        raise ValueError(f"{name}.rate_usd must be a positive observed rate")
    observed_at = _integer(value.observed_at_seconds, f"{name}.observed_at_seconds")
    if observed_at > now:
        raise ValueError(f"{name} observed after now_seconds; backward timestamp")
    if now - observed_at > max_age:
        raise ValueError(f"{name} observation is stale beyond {max_age} seconds")
    return rate


def planned_ceiling_usd(total_ceiling_usd: Decimal, reserve_usd: Decimal) -> Decimal:
    """Exact planned ceiling: total minus reserve. Estimate split, not a provider cap."""
    total = _number(total_ceiling_usd, "total_ceiling_usd")
    reserve = _number(reserve_usd, "reserve_usd")
    if total <= 0:
        raise ValueError("total_ceiling_usd must be positive")
    if reserve >= total:
        raise ValueError("reserve_usd must stay strictly below total_ceiling_usd")
    return _decimal(total - reserve)


def plan_engineering_budget(
    terms: BudgetTerms,
    rates: ResourceRates,
    workload: GpuWorkload,
    preparation: PreparationAccount,
    ancillary: AncillaryEstimates,
    now_seconds: int,
    *,
    max_observation_age_seconds: int = _DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
) -> EngineeringBudgetPlan:
    """Plan one paid GPU attempt within total-minus-reserve; estimate, never authority.

    workload.duration_seconds covers ALL owned GPU activity including
    verification, export and teardown wall time; termination_reserve_usd is its
    monetary reserve only. Incurred preparation counts cash plus credits at
    gross, never discounted. The returned deadline is a planning value, not
    enforcement; a stop acknowledgement remains no charged-end proof.
    """
    for value, name, expected in (
        (terms, "terms", BudgetTerms),
        (rates, "rates", ResourceRates),
        (workload, "workload", GpuWorkload),
        (preparation, "preparation", PreparationAccount),
        (ancillary, "ancillary", AncillaryEstimates),
    ):
        if type(value) is not expected:
            raise ValueError(f"{name} requires {expected.__name__}, UNKNOWN blocks")
    total = _number(terms.total_ceiling_usd, "terms.total_ceiling_usd")
    reserve = _number(terms.reserve_usd, "terms.reserve_usd")
    if total <= 0:
        raise ValueError("terms.total_ceiling_usd must be positive")
    if reserve >= total:
        raise ValueError("terms.reserve_usd must stay strictly below the total ceiling")
    planned = total - reserve
    now = _integer(now_seconds, "now_seconds")
    max_age = _integer(max_observation_age_seconds, "max_observation_age_seconds")
    if type(rates.runtime_context) is not str or rates.runtime_context not in RUNTIME_CONTEXTS:
        raise ValueError("rates.runtime_context must be function or sandbox, UNKNOWN blocks")
    observed_rates = {
        role: _observation(getattr(rates, role), role, now, max_age)
        for role in ("gpu", "cpu", "ram")
    }
    gpu_count = _integer(workload.gpu_count, "workload.gpu_count", positive=True)
    if gpu_count != 1:
        raise ValueError("exactly one GPU resource is plannable")
    cpu_cores = _integer(workload.cpu_cores, "workload.cpu_cores", positive=True)
    ram_gib = _number(workload.ram_gib, "workload.ram_gib")
    if ram_gib <= 0:
        raise ValueError("workload.ram_gib must be positive")
    duration = _integer(workload.duration_seconds, "workload.duration_seconds", positive=True)
    if duration > _MAX_GPU_SECONDS:
        raise ValueError("owned GPU activity duration exceeds 1800 seconds")
    incurred = _number(preparation.incurred_cash_usd, "preparation.incurred_cash_usd")
    incurred += _number(preparation.incurred_credits_usd, "preparation.incurred_credits_usd")
    prep_remaining = _number(preparation.remaining_estimate_usd, "preparation.remaining_estimate_usd")
    transfer = _number(ancillary.transfer_usd, "ancillary.transfer_usd")
    storage = _number(ancillary.storage_usd, "ancillary.storage_usd")
    termination = _number(ancillary.termination_reserve_usd, "ancillary.termination_reserve_usd")
    if incurred >= planned:
        raise ValueError("incurred preparation exhausts the planned ceiling; headroom gone")
    allowance = planned - incurred
    seconds = Fraction(duration)
    gpu_cost = observed_rates["gpu"] * gpu_count * seconds
    cpu_cost = observed_rates["cpu"] * cpu_cores * seconds
    ram_cost = observed_rates["ram"] * ram_gib * seconds
    remaining = prep_remaining + gpu_cost + cpu_cost + ram_cost + transfer + storage + termination
    if remaining > allowance:
        raise ValueError("remaining estimates exceed available planned funds")
    breakdown = (
        ("preparation_remaining", _decimal(prep_remaining)),
        ("gpu", _decimal(gpu_cost)),
        ("cpu", _decimal(cpu_cost)),
        ("ram", _decimal(ram_cost)),
        ("transfer", _decimal(transfer)),
        ("storage", _decimal(storage)),
        ("termination_reserve", _decimal(termination)),
    )
    return EngineeringBudgetPlan(
        _decimal(planned),
        _decimal(incurred),
        _decimal(remaining),
        _decimal(incurred + remaining),
        _decimal(allowance - remaining),
        now + duration,
        breakdown,
    )
