"""Conditional arithmetic only; callers own completeness and lifecycle enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import sys
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from train.native_qualification import AttemptBounds


_CATEGORIES = (
    "preparation", "build", "cpu", "gpu", "ram", "provisioning",
    "teardown", "storage", "retention", "egress", "replay", "ancillary",
)
_SIZE_UNITS = {"GiB": 1073741824, "MiB": 1048576}
_RATE_UNITS = {
    "USD/item": ("item", False),
    "USD/gpu-second": ("gpu", True),
    "USD/physical-core-second": ("physical-core", True),
    "USD/GiB-second": ("GiB", True),
    "USD/MiB-second": ("MiB", True),
    "USD/GiB": ("GiB", False),
    "USD/MiB": ("MiB", False),
}


@dataclass(frozen=True)
class Charge:
    quantity: Decimal
    unit: str
    rate_usd: Decimal
    rate_unit: str
    seconds: Decimal | None


@dataclass(frozen=True)
class CostLedger:
    prior_cash_usd: Decimal
    prior_credits_usd: Decimal
    provisioning_seconds: int
    teardown_seconds: int
    charges: Mapping[str, Charge | None]


@dataclass(frozen=True)
class CostArithmetic:
    prior_gross_usd: Decimal
    remaining_usd: Decimal
    total_gross_usd: Decimal
    breakdown: tuple[tuple[str, Decimal], ...]
    scope: str = "conditional_all_charge_arithmetic_only"

    def charge_usd(self, category: str) -> Decimal:
        for name, value in self.breakdown:
            if name == category:
                return value
        raise ValueError("unknown charge category")


@dataclass(frozen=True)
class ConditionalComparison:
    required_speedup: Fraction
    h200_compute_cheaper: bool
    scope: str = "conditional_compute_arithmetic_only"


def _number(value: object, name: str) -> Fraction:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} requires finite Decimal")
    # CPython _decimal decimal_sizeof includes allocated coefficient limbs.
    # Bound tuple expansion, not caller construction, allocator overhead or RSS.
    if (
        sys.implementation.name != "cpython"
        or getattr(Decimal.__sizeof__, "__objclass__", None) is not Decimal
        or Decimal.__sizeof__(value) > 256
    ):
        raise ValueError(f"{name} decimal representation exceeds supported size limits")
    parts = value.as_tuple()
    # Bound before powers or integer conversion, even for a zero coefficient.
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


def _charge(charge: object, name: str) -> tuple[Fraction, Fraction, Fraction | None]:
    if type(charge) is not Charge:
        raise ValueError(f"{name} requires explicit charge, UNKNOWN blocks")
    if type(charge.unit) is not str or type(charge.rate_unit) is not str:
        raise ValueError(f"{name} requires explicit units")
    if charge.rate_unit not in _RATE_UNITS:
        raise ValueError(f"{name} unknown rate unit")
    rate_unit, timed = _RATE_UNITS[charge.rate_unit]
    quantity = _number(charge.quantity, f"{name}.quantity")
    rate = _number(charge.rate_usd, f"{name}.rate_usd")
    if charge.unit in _SIZE_UNITS and rate_unit in _SIZE_UNITS:
        normalized = quantity * Fraction(_SIZE_UNITS[charge.unit], _SIZE_UNITS[rate_unit])
        size_bytes = quantity * _SIZE_UNITS[charge.unit]
    elif charge.unit == rate_unit:
        normalized = quantity
        size_bytes = Fraction(0)
    else:
        raise ValueError(f"{name} quantity/rate units disagree")
    if timed:
        duration = _number(charge.seconds, f"{name}.seconds")
        return normalized * rate * duration, size_bytes, duration
    if charge.seconds is not None:
        raise ValueError(f"{name} untimed rate must not specify duration")
    return normalized * rate, size_bytes, None


def evaluate_costs(bounds: AttemptBounds, ledger: CostLedger) -> CostArithmetic:
    """Check declared gross bounds, never tariffs, balance or approval."""
    from train.native_qualification import AttemptBounds, _validate_bounds

    if type(bounds) is not AttemptBounds or type(ledger) is not CostLedger:
        raise ValueError("AttemptBounds and CostLedger required")
    ceiling = _number(bounds.total_ceiling_usd, "total_ceiling_usd")
    declared_prior = _number(bounds.prior_usage_usd, "prior_usage_usd")
    reservation = _number(bounds.remaining_worst_case_usd, "remaining_worst_case_usd")
    for name in ("lifetime_seconds", "output_bytes_per_phase", "artifact_bytes", "retention_seconds"):
        _integer(getattr(bounds, name), name, positive=True)
    _validate_bounds(bounds)
    prior = _number(ledger.prior_cash_usd, "prior_cash_usd")
    prior += _number(ledger.prior_credits_usd, "prior_credits_usd")
    if prior != declared_prior:
        raise ValueError("prior cash plus consumed credits must equal prior gross usage")
    provisioning = _integer(ledger.provisioning_seconds, "provisioning_seconds")
    teardown = _integer(ledger.teardown_seconds, "teardown_seconds")
    compute_seconds = bounds.lifetime_seconds + provisioning + teardown
    if not isinstance(ledger.charges, Mapping) or len(ledger.charges) != len(_CATEGORIES):
        raise ValueError("explicit complete charge mapping required")
    charges = dict(ledger.charges)
    if set(charges) != set(_CATEGORIES):
        raise ValueError("all 12 charge categories required, UNKNOWN blocks")
    breakdown = []
    remaining = Fraction(0)
    for name in _CATEGORIES:
        charge = charges[name]
        cost, size_bytes, duration = _charge(charge, name)
        if name in ("cpu", "gpu", "ram"):
            expected = {"cpu": ("physical-core",), "gpu": ("gpu",), "ram": ("GiB", "MiB")}
            if charge.unit not in expected[name] or duration is None:
                raise ValueError(f"{name} requires explicit resource-time unit")
            if _number(charge.quantity, name) <= 0:
                raise ValueError(f"{name} resource quantity must be positive")
            if name == "gpu" and _number(charge.quantity, name) != 1:
                raise ValueError("exactly one GPU required")
            if duration < compute_seconds:
                raise ValueError(f"{name} duration excludes lifetime or provisioning/teardown tail")
        elif name in ("storage", "retention"):
            floor = bounds.retention_seconds if name == "retention" else compute_seconds
            if duration is None or duration < floor or size_bytes < bounds.artifact_bytes:
                raise ValueError(f"{name} requires bounded artifact size and duration coverage")
        elif name == "egress":
            if duration is not None or size_bytes < bounds.artifact_bytes + 2 * bounds.output_bytes_per_phase:
                raise ValueError("egress must cover artifacts and both phase outputs")
        remaining += cost
        breakdown.append((name, _decimal(cost)))
    if remaining > reservation:
        raise ValueError("all-charge remaining cost exceeds declared reservation")
    if prior + remaining > ceiling:
        raise ValueError("all-charge gross cost exceeds ceiling")
    return CostArithmetic(_decimal(prior), _decimal(remaining), _decimal(prior + remaining),
                          tuple(breakdown))


def compare_h200(
    l40s_compute_usd_per_second: Decimal,
    h200_compute_usd_per_second: Decimal,
    hypothetical_speedup: Decimal,
) -> ConditionalComparison:
    """Same work/settings, aggregate GPU/CPU/RAM rates; excludes fixed charges."""
    l40s = _number(l40s_compute_usd_per_second, "l40s_compute_usd_per_second")
    h200 = _number(h200_compute_usd_per_second, "h200_compute_usd_per_second")
    speedup = _number(hypothetical_speedup, "hypothetical_speedup")
    if min(l40s, h200, speedup) <= 0:
        raise ValueError("positive rates and hypothetical speedup required")
    threshold = h200 / l40s
    return ConditionalComparison(threshold, speedup > threshold)
