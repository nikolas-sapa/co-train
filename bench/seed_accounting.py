"""Pure accounting of caller-labelled existing paired BIRD results.

Labels are declarations, not authenticated RNG provenance. Structural status
projects supplied result status/comparison presence, not independent replay or
adjudication of outcomes, disclosures, diagnostics, tasksets or admission.
Even three complete results prove no measured trial, completed training,
scientific acceptance, checkpoint identity or backend/runtime acceptance.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from bench.paired_bird import Comparison, PairedBirdResult


class SeedAccountingError(ValueError):
    """Malformed accounting input; messages never include caller payloads."""


@dataclass(frozen=True)
class SeedAccounting:
    """One expected label, supplied declarations and existing comparison.

    Missing declarations stay None. Complete/void describes supplied structure
    only, not independently validated execution. No source result is rewritten.
    """

    seed: int
    present: bool
    declared_status: str | None
    structural_status: str
    comparison: Comparison | None
    fixture_declared: bool | None
    measurement_declared: bool | None


@dataclass(frozen=True)
class ThreeSeedAccounting:
    """Frozen accounting projection, not a measurement or seed receipt.

    Distinct result objects can still be copies or fabricated declarations.
    Literal object-alias refusal does not establish independent trials.
    No pooled estimate is computed and no acceptance flag is configurable.
    """

    seeds: tuple[SeedAccounting, ...]

    @property
    def present_count(self) -> int:
        return sum(seed.present for seed in self.seeds)

    @property
    def missing_count(self) -> int:
        return sum(seed.structural_status == "missing" for seed in self.seeds)

    @property
    def complete_count(self) -> int:
        return sum(seed.structural_status == "complete" for seed in self.seeds)

    @property
    def void_count(self) -> int:
        return sum(seed.structural_status == "void" for seed in self.seeds)

    @property
    def structural_three_seed_complete(self) -> bool:
        return len(self.seeds) == 3 and self.complete_count == 3

    @property
    def measurement_accepted(self) -> bool:
        return False

    @property
    def scientific_accepted(self) -> bool:
        return False

    @property
    def completed_training_accepted(self) -> bool:
        return False

    @property
    def backend_accepted(self) -> bool:
        return False

    @property
    def runtime_accepted(self) -> bool:
        return False

    @property
    def rng_provenance_verified(self) -> bool:
        return False

    @property
    def checkpoint_provenance_verified(self) -> bool:
        return False


def _sequence(value) -> tuple:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SeedAccountingError("accounting inputs must be sequences")
    try:
        return tuple(value)
    except Exception:
        raise SeedAccountingError("accounting sequence could not be read") from None


def _finite_number(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _check_comparison(comparison) -> None:
    # Existing frozen records do not validate their payload types themselves.
    if type(comparison) is not Comparison:
        raise SeedAccountingError("comparison must be an existing frozen record")
    try:
        if (any(type(value) is not int for value in (
                comparison.n, comparison.a_only, comparison.b_only, comparison.ties))
                or not all(_finite_number(value) for value in (
                    comparison.mean_a, comparison.mean_b, comparison.delta,
                    comparison.p))):
            raise SeedAccountingError("comparison fields must be immutable numeric values")
        if comparison.ci is not None and (
                type(comparison.ci) is not tuple or len(comparison.ci) != 2
                or not all(_finite_number(value) for value in comparison.ci)):
            raise SeedAccountingError("comparison interval must be an immutable numeric pair")
    except AttributeError:
        raise SeedAccountingError("comparison fields are missing") from None


def _check_result(result) -> None:
    if type(result) is not PairedBirdResult:
        raise SeedAccountingError("results must be existing PairedBirdResult records")
    try:
        if (type(result.status) is not str or result.status not in ("complete", "void")
                or type(result.fixture) is not bool
                or type(result.measurement) is not bool):
            raise SeedAccountingError("result status and declarations are malformed")
        if result.status == "void":
            if result.comparison is not None:
                raise SeedAccountingError("void results must not declare a comparison")
        else:
            _check_comparison(result.comparison)
    except AttributeError:
        raise SeedAccountingError("result fields are missing") from None


def account_three_seeds(
    expected_seeds: Sequence[int],
    results: Sequence[tuple[int, PairedBirdResult]],
) -> ThreeSeedAccounting:
    """Account exactly three expected labels without selecting or proving seeds.

    Accept sequence inputs, snapshot without mutating caller containers, and
    refuse duplicate/unexpected/non-exact-int labels or literal result reuse.
    Negative and arbitrarily large labels carry no RNG-range endorsement.
    Missing results stay missing; supplied void results stay void. Comparisons
    are projected as existing immutable records, never pooled or recomputed.
    Only projected field shapes are checked, not the scientific validity of
    comparison numbers or the source result's execution/provenance.
    """
    expected = _sequence(expected_seeds)
    submitted = _sequence(results)
    if (len(expected) != 3 or any(type(seed) is not int for seed in expected)
            or len(set(expected)) != 3):
        raise SeedAccountingError("expected seeds must be three distinct exact integers")

    labelled = []
    seen_labels, seen_results = set(), set()
    for item in submitted:
        pair = _sequence(item)
        if len(pair) != 2:
            raise SeedAccountingError("each submission must contain one label and result")
        seed, result = pair
        if type(seed) is not int:
            raise SeedAccountingError("submitted labels must be exact integers")
        if seed not in expected:
            raise SeedAccountingError("submitted label is not expected")
        if seed in seen_labels:
            raise SeedAccountingError("submitted labels must not repeat")
        if id(result) in seen_results:
            raise SeedAccountingError("one result object cannot serve multiple labels")
        _check_result(result)
        seen_labels.add(seed)
        seen_results.add(id(result))
        labelled.append((seed, result))

    by_seed = dict(labelled)
    entries = []
    for seed in expected:
        result = by_seed.get(seed)
        if result is None:
            entries.append(SeedAccounting(
                seed, False, None, "missing", None, None, None))
        else:
            entries.append(SeedAccounting(
                seed, True, result.status, result.status, result.comparison,
                result.fixture, result.measurement))
    return ThreeSeedAccounting(tuple(entries))
