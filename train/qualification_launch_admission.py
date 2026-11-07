"""Frozen conditional quote and local one-use claim. Provider admission CLOSED.

Neither this public data model nor host approval establishes provider authority.
Only an independently reviewed implementation can replace the CLOSED review leaf;
there is deliberately no JSON, boolean, proof-string or callback override API.
Local claims do not survive host loss and are not provider create deduplication.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
import math
import threading
from typing import TYPE_CHECKING

from train.qualification_costs import Charge, CostArithmetic, CostLedger, evaluate_costs

if TYPE_CHECKING:
    from train.native_qualification import AttemptBounds, QualificationRequest


MISSING_PROVIDER_PROOFS = (
    "independently reviewed complete all-charge tariff and prior gross usage snapshot",
    "numeric preparation/build/hydration and queue/provisioning charged bounds",
    "provider create multiplicity <=1 after ambiguous response, including in-flight stop",
    "absolute charged lifetime <=1800 seconds from first billable operation through termination",
    "numeric termination and post-stop billing tail, not AppStop acknowledgement",
    "bounded storage/retention/egress/replay/ancillary charges and retention end",
    "durable host one-attempt authority and independent supervisor with bounded OS operations",
    "reviewed service binding for exactly one GPU and two sequential fresh native phases, no retries",
)

_CLAIM_LOCK = threading.Lock()
# Strong references prevent object-ID reuse. Process-local only, never durable authority.
_CLAIMED_OPERATIONS: list[object] = []


def _time(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} requires finite nonnegative monotonic time")
    return value


@dataclass(frozen=True)
class FrozenCostQuote:
    bounds: AttemptBounds
    prior_cash_usd: Decimal
    prior_credits_usd: Decimal
    provisioning_seconds: int
    teardown_seconds: int
    charges: tuple[tuple[str, Charge], ...]
    issued_at: float
    expires_at: float

    def ledger(self) -> CostLedger:
        if type(self.charges) is not tuple or len(self.charges) != 12 or any(
            type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
            or type(row[1]) is not Charge for row in self.charges
        ):
            raise ValueError("immutable explicit charge rows required")
        charges = dict(self.charges)
        if len(charges) != len(self.charges):
            raise ValueError("duplicate frozen charge category")
        return CostLedger(
            self.prior_cash_usd, self.prior_credits_usd,
            self.provisioning_seconds, self.teardown_seconds, charges,
        )


def freeze_cost_quote(
    bounds: AttemptBounds, ledger: CostLedger, *, issued_at: float, expires_at: float,
) -> FrozenCostQuote:
    """Copy all charge rows before validation; arithmetic is never authorization."""
    if type(ledger) is not CostLedger:
        raise ValueError("CostLedger required")
    if not isinstance(ledger.charges, Mapping) or len(ledger.charges) != 12:
        raise ValueError("explicit complete 12-category charge mapping required")
    snapshot = CostLedger(
        ledger.prior_cash_usd, ledger.prior_credits_usd,
        ledger.provisioning_seconds, ledger.teardown_seconds, dict(ledger.charges),
    )
    evaluate_costs(bounds, snapshot)
    issued = _time(issued_at, "issued_at")
    expiry = _time(expires_at, "expires_at")
    if expiry <= issued:
        raise ValueError("positive quote validity window required")
    return FrozenCostQuote(
        bounds, snapshot.prior_cash_usd, snapshot.prior_credits_usd,
        snapshot.provisioning_seconds, snapshot.teardown_seconds,
        tuple(snapshot.charges.items()), issued, expiry,
    )


def _require_fresh_quote(quote: FrozenCostQuote, now: float) -> None:
    current = _time(now, "now")
    issued = _time(quote.issued_at, "issued_at")
    expiry = _time(quote.expires_at, "expires_at")
    if not issued <= current < expiry:
        raise PermissionError("all-charge quote not yet valid or expired")


def validate_quote(
    request: QualificationRequest, quote: object, *, now: float,
) -> CostArithmetic:
    if type(quote) is not FrozenCostQuote:
        raise PermissionError("frozen complete all-charge quote required before allocation")
    if quote.bounds != request.bounds:
        raise PermissionError("quote differs from exact requested bounds")
    _require_fresh_quote(quote, now)
    return evaluate_costs(request.bounds, quote.ledger())


def _require_provider_review(request: QualificationRequest, quote: FrozenCostQuote) -> None:
    # No external numeric contract has been independently verified. Literal bounds
    # and correct arithmetic are declarations, not evidence or trusted authority.
    raise PermissionError("provider admission CLOSED: " + "; ".join(MISSING_PROVIDER_PROOFS))


class _LocalClaim:
    __slots__ = ("operation_identity", "quote", "request", "work_deadline",
                 "charged_deadline", "_used", "_lock")

    def __init__(self, operation_identity: object, request: QualificationRequest,
                 quote: FrozenCostQuote, now: float) -> None:
        if operation_identity is None:
            raise ValueError("retained operation identity required")
        validate_quote(request, quote, now=now)
        work_seconds = request.bounds.lifetime_seconds + quote.provisioning_seconds
        self.work_deadline = now + work_seconds
        self.charged_deadline = self.work_deadline + quote.teardown_seconds
        if (not math.isfinite(self.charged_deadline)
                or not now < self.work_deadline <= self.charged_deadline
                or self.charged_deadline - now > 1800):
            raise ValueError("representable aggregate deadlines <=1800 seconds required")
        self.operation_identity = operation_identity
        self.request = request
        self.quote = quote
        self._used = False
        self._lock = threading.Lock()
        with _CLAIM_LOCK:
            if any(identity is operation_identity for identity in _CLAIMED_OPERATIONS):
                raise PermissionError("operation already claimed locally; no retry or recovery")
            _CLAIMED_OPERATIONS.append(operation_identity)

    def consume(self, request: QualificationRequest, *, now: float) -> None:
        with self._lock:
            if self._used or request is not self.request:
                raise PermissionError("exact claimed request required once")
            # Irreversible before validation or any possible provider side effect.
            self._used = True
            validate_quote(request, self.quote, now=now)
            if now >= self.work_deadline:
                raise TimeoutError("claimed work deadline expired")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("host claim cannot be serialized or restored")


def _claim_reviewed_operation(
    operation_identity: object, request: QualificationRequest, quote: FrozenCostQuote,
    *, clock: Callable[[], float],
) -> _LocalClaim:
    now = _time(clock(), "now")
    validate_quote(request, quote, now=now)
    _require_provider_review(request, quote)
    reviewed_at = _time(clock(), "reviewed_at")
    if reviewed_at < now:
        raise ValueError("monotonic clock moved backwards during review")
    validate_quote(request, quote, now=reviewed_at)
    return _LocalClaim(operation_identity, request, quote, reviewed_at)
