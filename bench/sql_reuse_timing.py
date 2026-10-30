"""External caller-operation timing, not provider/team end-to-end measurement.

No SDK imports, execution policy changes, automatic approval, or file output.
Callbacks and clocks are trusted in-process caller code. Each span includes only
synchronous work inside its callback, including its final output writes/fsync.
Caller preparation outside the callback and observation finalization are excluded.
Nanoseconds are integer wall durations, not CPU, money, tokens or human time.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
from time import perf_counter_ns
from typing import Callable, TypeVar

_KINDS = ("candidate_prepare", "qualification", "reuse", "baseline_full")
_T = TypeVar("_T")


def _duration(value: int | None) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("duration must be nonnegative integer nanoseconds or unknown")


def _boolean(value: bool) -> None:
    if type(value) is not bool:
        raise ValueError("explicit boolean required")


@dataclass(frozen=True)
class Span:
    kind: str
    elapsed_ns: int | None
    completed: bool
    clock_valid: bool

    def __post_init__(self):
        if self.kind not in _KINDS:
            raise ValueError("unsupported operation kind")
        _duration(self.elapsed_ns)
        _boolean(self.completed)
        _boolean(self.clock_valid)
        if self.clock_valid != (self.elapsed_ns is not None):
            raise ValueError("clock validity must match known duration")


class Timer:
    """Explicitly opted-in callbacks; returns/raises original SDK objects unchanged.

    No callback arguments or exception messages retained. An invalid final clock
    records unknown duration. If the callback also failed, its original exception
    wins; otherwise the clock error propagates. Not a concurrent/team span collector.
    """

    def __init__(self, *, clock: Callable[[], int] = perf_counter_ns):
        self._clock = clock
        self._observations: list[Span] = []

    @property
    def observations(self) -> tuple[Span, ...]:
        return tuple(self._observations)

    def _tick(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 0:
            raise ValueError("clock must return nonnegative integer nanoseconds")
        return value

    def run(
        self, kind: str, operation: Callable[[], _T], *, allow_execution: bool = False,
    ) -> _T:
        if allow_execution is not True:
            raise ValueError("caller operation requires explicit allow_execution=True")
        if kind not in _KINDS:
            raise ValueError("unsupported operation kind")
        start = self._tick()

        def close(completed: bool) -> None:
            try:
                end = self._tick()
                if end < start:
                    raise ValueError("monotonic clock went backwards")
            except BaseException:
                self._observations.append(Span(kind, None, completed, False))
                raise
            self._observations.append(Span(kind, end - start, completed, True))

        try:
            result = operation()
        except BaseException:
            try:
                close(False)
            except BaseException:
                # A broken final measurement must not replace the caller error.
                pass
            raise
        close(True)
        return result


@dataclass(frozen=True)
class Arm:
    """Trusted full caller-operation duration and independent solved validity.

    An aborted/error attempt may retain full_ns but must not be solved_valid=True.
    Timing alone cannot establish task quality, scope comparability or completeness.
    """
    full_ns: int | None
    solved_valid: bool | None

    def __post_init__(self):
        _duration(self.full_ns)
        if self.solved_valid is not None:
            _boolean(self.solved_valid)


@dataclass(frozen=True)
class Pair:
    """Predeclare one per planned pair; absent arms remain explicit None.

    case_id is opaque caller memory only, never rendered. No semantic matching.
    """
    case_id: str
    baseline: Arm | None
    treatment: Arm | None
    comparable: bool | None

    def __post_init__(self):
        if type(self.case_id) is not str or not self.case_id:
            raise ValueError("nonempty opaque pair identifier required")
        for arm in (self.baseline, self.treatment):
            if arm is not None and type(arm) is not Arm:
                raise TypeError("arms must be Arm or unknown")
        if self.comparable is not None:
            _boolean(self.comparable)


@dataclass(frozen=True)
class Row:
    case: int
    baseline_ns: int | None
    treatment_ns: int | None
    eligible: bool


@dataclass(frozen=True)
class Scenario:
    uses: int
    net_per_use_ns: Fraction
    total_net_ns: Fraction


@dataclass(frozen=True)
class Analysis:
    planned_pairs: int
    rows: tuple[Row, ...]
    setup_ns: int | None
    baseline_mean_ns: Fraction | None
    treatment_mean_ns: Fraction | None
    gross_per_use_ns: Fraction | None
    break_even_uses: int | None
    scenarios: tuple[Scenario, ...]


def analyze(
    observations: tuple[Pair, ...], setup_attempts: tuple[Span, ...], *,
    planned_case_ids: tuple[str, ...], setup_complete: bool,
) -> Analysis:
    """All-planned-case arithmetic, never a successful-only cohort.

    Caller asserts that setup_attempts contains EVERY setup attempt and that each
    arm is a full, comparable operation span. Failed attempts count toward setup.
    Unknown setup or ANY absent/invalid/incomparable arm suppresses all aggregate
    means/savings. Known individual durations and setup overhead remain visible.
    No confidence interval, paired estimator, extrapolated adoption or cost claim.
    """
    _boolean(setup_complete)
    if type(planned_case_ids) is not tuple or not planned_case_ids:
        raise ValueError("nonempty immutable planned identifiers required")
    if any(type(case_id) is not str or not case_id for case_id in planned_case_ids):
        raise ValueError("planned identifiers must be nonempty opaque strings")
    if len(set(planned_case_ids)) != len(planned_case_ids):
        raise ValueError("planned identifiers must be unique")
    if type(observations) is not tuple or any(type(pair) is not Pair for pair in observations):
        raise TypeError("observations must be a tuple of Pair records")
    observed = {pair.case_id: pair for pair in observations}
    if len(observed) != len(observations):
        raise ValueError("duplicate pair observations")
    if not observed.keys() <= set(planned_case_ids):
        raise ValueError("observations must belong to the predeclared plan")
    planned_pairs = tuple(observed.get(case_id, Pair(case_id, None, None, None))
                          for case_id in planned_case_ids)
    if type(setup_attempts) is not tuple:
        raise TypeError("setup attempts must be a tuple")
    if any(type(span) is not Span or span.kind not in ("candidate_prepare", "qualification")
           for span in setup_attempts):
        raise ValueError("only candidate preparation and qualification are setup")
    setup_ns = None
    if setup_complete and setup_attempts and all(s.clock_valid for s in setup_attempts):
        setup_ns = sum(s.elapsed_ns for s in setup_attempts)
    rows = tuple(Row(
        n,
        pair.baseline.full_ns if pair.baseline is not None else None,
        pair.treatment.full_ns if pair.treatment is not None else None,
        pair.comparable is True
        and pair.baseline is not None and pair.baseline.solved_valid is True
        and pair.baseline.full_ns is not None
        and pair.treatment is not None and pair.treatment.solved_valid is True
        and pair.treatment.full_ns is not None,
    ) for n, pair in enumerate(planned_pairs, 1))
    count = len(planned_pairs)
    if setup_ns is None or not all(row.eligible for row in rows):
        return Analysis(count, rows, setup_ns, None, None, None, None, ())
    baseline = Fraction(sum(row.baseline_ns for row in rows), count)
    treatment = Fraction(sum(row.treatment_ns for row in rows), count)
    gross = baseline - treatment
    break_even = None
    if gross > 0:
        ratio = Fraction(setup_ns) / gross
        break_even = max(1, -(-ratio.numerator // ratio.denominator))
    scenarios = tuple(Scenario(n, gross - Fraction(setup_ns, n), gross * n - setup_ns)
                      for n in (100, 1000, 10000))
    return Analysis(count, rows, setup_ns, baseline, treatment, gross, break_even, scenarios)


def render_summary(result: Analysis) -> str:
    """Numeric/status allowlist only. Opaque IDs and source data never rendered.

    Fraction values are exact rational strings in nanoseconds, not rounded ms.
    None means unavailable; break-even None alone does not distinguish unknown
    from nonpositive gross (use savings_status).
    """
    def exact(value: Fraction | None) -> str | None:
        return str(value) if value is not None else None

    status = "unavailable"
    if result.gross_per_use_ns is not None:
        status = "nonpositive_gross" if result.gross_per_use_ns <= 0 else "known"
    return json.dumps({
        "units": "ns",
        "scope": "caller_callback_outer_wall_only",
        "planned_pairs": result.planned_pairs,
        "rows": [
            {"case": r.case, "baseline_ns": r.baseline_ns,
             "treatment_ns": r.treatment_ns, "eligible": r.eligible}
            for r in result.rows
        ],
        "setup_ns": result.setup_ns,
        "baseline_mean_ns": exact(result.baseline_mean_ns),
        "treatment_mean_ns": exact(result.treatment_mean_ns),
        "gross_per_use_ns": exact(result.gross_per_use_ns),
        "savings_status": status,
        "break_even_uses": result.break_even_uses,
        "scenarios": [
            {"label": "SCENARIO", "uses": s.uses, "net_per_use_ns": exact(s.net_per_use_ns),
             "total_net_ns": exact(s.total_net_ns)}
            for s in result.scenarios
        ],
        "unavailable": [
            "retrieval", "search", "team_discovery", "billing", "tokens",
            "human_review", "cpu_time", "provider_latency", "team_wall_time",
        ],
    }, sort_keys=True, separators=(",", ":"), allow_nan=False)
