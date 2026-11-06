"""Bounded in-memory joins of unverified frontier evidence declarations.

No bytes are decoded, paths opened, queries run or external facts authenticated.
Separately supplied pins need not be independent. Perfect synthetic/replayed
declarations can pass structure, never genuine measurement or training admission.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

__all__ = [
    "BindingLimits", "TaskBinding", "PreparationExclusion", "ScorerBinding",
    "MeasurementPlan", "ExpectedEvidence", "EvidenceBlob", "SampleRecord",
    "EvidenceBatch", "SlotDisposition", "BindingReport", "BindingError",
    "validate_frontier_bindings",
]

_LIMIT_CEILINGS = (1024, 4096, 12289, 12289, 1 << 20, 16 << 20, 256, 10)
_MAX_INTEGER = (1 << 63) - 1
_HEX = frozenset("0123456789abcdef")
_REVISION_HEX = frozenset("0123456789abcdefABCDEF")
_STATUSES = ("scored", "generation_failed", "invalid_gold", "pending", "unknown")
_DISPOSITIONS = _STATUSES + ("missing",)
_PURPOSES = ("checkpoint", "generation", "scoring")
# Source-checked in bench/score.py: rows_match and execution_accuracy.
_COMPARISONS = ("set", "multiset")
_PLAN_IDS = (
    "plan_id", "execution_id", "runtime_id", "provider_id", "route_id",
    "resource_limits_id", "grant_reference",
)
_PLAN_DIGESTS = (
    "checkpoint_sha256", "generation_sha256", "prompt_sha256", "template_sha256",
    "tool_sha256", "instrument_sha256", "source_sha256", "draw_sha256",
    "supplement_sha256",
)


class BindingError(ValueError):
    """Opaque malformed-input refusal, with no supplied data in its text."""

    def __init__(self):
        super().__init__("invalid frontier bindings")


def _fail():
    raise BindingError() from None


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class BindingLimits:
    max_planned_tasks: int
    max_scheduled_slots: int
    max_expected_evidence: int
    max_raw_evidence: int
    max_item_bytes: int
    max_aggregate_bytes: int
    max_identifier_bytes: int
    max_diagnostics: int


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class TaskBinding:
    task_id: str
    task_sha256: str
    database_sha256: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class PreparationExclusion:
    task_id: str
    reason: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class ScorerBinding:
    extraction_source_sha256: str
    scorer_source_sha256: str
    comparison: str
    timeout_s: float | int
    max_rows: int


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class MeasurementPlan:
    plan_id: str
    execution_id: str
    policy_revision: str
    checkpoint_sha256: str
    adapter_sha256: str | None
    runtime_id: str
    provider_id: str
    route_id: str
    generation_sha256: str
    prompt_sha256: str
    template_sha256: str
    tool_sha256: str
    instrument_sha256: str
    source_sha256: str
    draw_sha256: str
    supplement_sha256: str
    tasks: tuple[TaskBinding, ...]
    eligible_ids: tuple[str, ...]
    exclusions: tuple[PreparationExclusion, ...]
    g: int
    dead_ceiling: float | int
    scorer: ScorerBinding
    resource_limits_id: str
    grant_reference: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class ExpectedEvidence:
    evidence_id: str
    purpose: str
    plan_id: str
    execution_id: str
    task_id: str | None
    slot_index: int | None
    attempt_id: str | None
    generation_evidence_id: str | None
    prediction_sha256: str | None
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class EvidenceBlob:
    evidence_id: str
    payload: bytes


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class SampleRecord:
    task_id: str
    slot_index: int
    attempt_id: str
    status: str
    score: int | float | None
    generation_evidence_id: str | None
    scoring_evidence_id: str | None
    prediction_sha256: str | None


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class EvidenceBatch:
    plan: MeasurementPlan
    blobs: tuple[EvidenceBlob, ...]
    samples: tuple[SampleRecord, ...]


@dataclass(frozen=True, slots=True)
class SlotDisposition:
    task_ordinal: int
    slot_index: int
    disposition: str
    bindings_consistent: bool
    validly_scored: bool


@dataclass(frozen=True, slots=True)
class BindingReport:
    planned_tasks: int
    eligible_tasks: int
    excluded_tasks: int
    scheduled_slots: int
    observed_slots: int
    declared_attempts: int
    matched_evidence: int
    valid_declared_scores: int
    disposition_counts: tuple[tuple[str, int], ...]
    slots: tuple[SlotDisposition, ...]
    diagnostics: tuple[tuple[str, int | None, int | None], ...]
    total_issues: int
    diagnostics_truncated: bool
    bindings_consistent: bool
    schedule_complete: bool
    all_samples_validly_scored: bool

    @property
    def provenance(self) -> str:
        return "unverified"

    @property
    def attested_facts(self) -> tuple:
        return ()

    @property
    def genuine_measurement_accepted(self) -> bool:
        return False

    @property
    def training_authorized(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return "external provenance/attestation verification unavailable"


def _record(value, cls):
    """Copy trusted slot descriptors only, after an exact class identity check."""
    if type(value) is not cls:
        _fail()
    values = []
    for name in cls.__slots__:
        try:
            field = object.__getattribute__(value, name)
        except AttributeError:
            _fail()
        values.append(field)
    return cls(*values)


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        _fail()
    return value


def _number(value, low, high, *, strict_low=False, strict_high=False):
    kind = type(value)
    if kind is int:
        _integer(value, -_MAX_INTEGER, _MAX_INTEGER)
    elif kind is float:
        if not math.isfinite(value):
            _fail()
    else:
        _fail()
    if value < low or value > high:
        _fail()
    if (strict_low and value == low) or (strict_high and value == high):
        _fail()
    return value


def _tuple(value, maximum, *, nonempty=False):
    if type(value) is not tuple:
        _fail()
    if len(value) > maximum or (nonempty and not len(value)):
        _fail()
    return value


class _Budget:
    __slots__ = ("limits", "used")

    def __init__(self, limits):
        self.limits = limits
        self.used = 0

    def charge(self, amount):
        self.used += amount
        if self.used > self.limits.max_aggregate_bytes:
            _fail()

    def text(self, value, maximum, *, optional=False):
        if optional and value is None:
            return None
        if type(value) is not str:
            _fail()
        # UTF8 cannot occupy fewer bytes than codepoints. Bound before encoding.
        if not len(value) or len(value) > maximum:
            _fail()
        try:
            encoded = str.encode(value, "utf-8")
        except UnicodeEncodeError:
            _fail()
        if len(encoded) > maximum:
            _fail()
        self.charge(len(encoded))
        return value

    def identifier(self, value, *, optional=False):
        return self.text(value, self.limits.max_identifier_bytes, optional=optional)

    def digest(self, value, *, optional=False):
        return self.text(value, 64, optional=optional)


def _snapshot_limits(value):
    limits = _record(value, BindingLimits)
    for name, ceiling in zip(BindingLimits.__slots__, _LIMIT_CEILINGS, strict=True):
        _integer(object.__getattribute__(limits, name), 1, ceiling)
    return limits


def _snapshot_task(value, budget):
    task = _record(value, TaskBinding)
    return TaskBinding(
        budget.identifier(task.task_id),
        budget.digest(task.task_sha256), budget.digest(task.database_sha256),
    )


def _snapshot_exclusion(value, budget):
    exclusion = _record(value, PreparationExclusion)
    return PreparationExclusion(
        budget.identifier(exclusion.task_id), budget.identifier(exclusion.reason),
    )


def _snapshot_scorer(value, budget):
    scorer = _record(value, ScorerBinding)
    return ScorerBinding(
        budget.digest(scorer.extraction_source_sha256),
        budget.digest(scorer.scorer_source_sha256),
        budget.text(scorer.comparison, 32),
        _number(scorer.timeout_s, 0, _MAX_INTEGER, strict_low=True),
        _integer(scorer.max_rows, 1, _MAX_INTEGER),
    )


def _snapshot_plan(value, budget):
    plan = _record(value, MeasurementPlan)
    limits = budget.limits
    # Counts and the integer product precede any schedule expansion or ID index.
    tasks = _tuple(plan.tasks, limits.max_planned_tasks, nonempty=True)
    eligible = _tuple(plan.eligible_ids, limits.max_planned_tasks, nonempty=True)
    exclusions = _tuple(plan.exclusions, limits.max_planned_tasks)
    g = _integer(plan.g, 2, _LIMIT_CEILINGS[1])
    if len(eligible) * g > limits.max_scheduled_slots:
        _fail()
    ids = tuple(budget.identifier(object.__getattribute__(plan, name)) for name in _PLAN_IDS)
    revision = budget.text(plan.policy_revision, 40)
    digests = tuple(budget.digest(object.__getattribute__(plan, name)) for name in _PLAN_DIGESTS)
    adapter = budget.digest(plan.adapter_sha256, optional=True)
    task_copy = tuple(_snapshot_task(item, budget) for item in tasks)
    eligible_copy = tuple(budget.identifier(item) for item in eligible)
    excluded_copy = tuple(_snapshot_exclusion(item, budget) for item in exclusions)
    ceiling = _number(plan.dead_ceiling, 0, 1, strict_low=True, strict_high=True)
    scorer = _snapshot_scorer(plan.scorer, budget)
    return MeasurementPlan(
        plan_id=ids[0], execution_id=ids[1], policy_revision=revision,
        checkpoint_sha256=digests[0], adapter_sha256=adapter,
        runtime_id=ids[2], provider_id=ids[3], route_id=ids[4],
        generation_sha256=digests[1], prompt_sha256=digests[2],
        template_sha256=digests[3], tool_sha256=digests[4],
        instrument_sha256=digests[5], source_sha256=digests[6],
        draw_sha256=digests[7], supplement_sha256=digests[8],
        tasks=task_copy, eligible_ids=eligible_copy, exclusions=excluded_copy,
        g=g, dead_ceiling=ceiling, scorer=scorer,
        resource_limits_id=ids[5], grant_reference=ids[6],
    )


def _snapshot_expected(value, budget):
    item = _record(value, ExpectedEvidence)
    slot = item.slot_index
    if slot is not None:
        slot = _integer(slot, 0, budget.limits.max_scheduled_slots - 1)
    return ExpectedEvidence(
        budget.identifier(item.evidence_id), budget.text(item.purpose, 32),
        budget.identifier(item.plan_id), budget.identifier(item.execution_id),
        budget.identifier(item.task_id, optional=True), slot,
        budget.identifier(item.attempt_id, optional=True),
        budget.identifier(item.generation_evidence_id, optional=True),
        budget.digest(item.prediction_sha256, optional=True),
        _integer(item.byte_count, 0, budget.limits.max_item_bytes),
        budget.digest(item.sha256),
    )


def _snapshot_blob(value, budget):
    blob = _record(value, EvidenceBlob)
    evidence_id = budget.identifier(blob.evidence_id)
    if type(blob.payload) is not bytes or len(blob.payload) > budget.limits.max_item_bytes:
        _fail()
    budget.charge(len(blob.payload))
    return EvidenceBlob(evidence_id, blob.payload)


def _snapshot_sample(value, budget):
    sample = _record(value, SampleRecord)
    score = sample.score
    if score is not None:
        score = _number(score, 0, 1)
    return SampleRecord(
        budget.identifier(sample.task_id),
        _integer(sample.slot_index, 0, budget.limits.max_scheduled_slots - 1),
        budget.identifier(sample.attempt_id), budget.text(sample.status, 32), score,
        budget.identifier(sample.generation_evidence_id, optional=True),
        budget.identifier(sample.scoring_evidence_id, optional=True),
        budget.digest(sample.prediction_sha256, optional=True),
    )


def _snapshot(plan, expected, candidate, limits):
    limits = _snapshot_limits(limits)
    budget = _Budget(limits)
    expected = _tuple(expected, limits.max_expected_evidence)
    batch = _record(candidate, EvidenceBatch)
    blobs = _tuple(batch.blobs, limits.max_raw_evidence)
    samples = _tuple(batch.samples, limits.max_scheduled_slots)
    plan = _snapshot_plan(plan, budget)
    projection = _snapshot_plan(batch.plan, budget)
    expected = tuple(_snapshot_expected(item, budget) for item in expected)
    blobs = tuple(_snapshot_blob(item, budget) for item in blobs)
    samples = tuple(_snapshot_sample(item, budget) for item in samples)
    return plan, expected, EvidenceBatch(projection, blobs, samples), limits


def _sha(value):
    # All input strings have already been bounded and aggregate-charged.
    if len(value) != 64 or any(character not in _HEX for character in value):
        _fail()


def _unique(values):
    if len(set(values)) != len(values):
        _fail()


def _validate_plan(plan):
    revision = plan.policy_revision
    if len(revision) != 40 or any(character not in _REVISION_HEX for character in revision):
        _fail()
    for name in _PLAN_DIGESTS:
        _sha(object.__getattribute__(plan, name))
    if plan.adapter_sha256 is not None:
        _sha(plan.adapter_sha256)
    scorer = plan.scorer
    _sha(scorer.extraction_source_sha256)
    _sha(scorer.scorer_source_sha256)
    if scorer.comparison not in _COMPARISONS:
        _fail()
    for task in plan.tasks:
        _sha(task.task_sha256)
        _sha(task.database_sha256)


def _check_membership(plan):
    planned = tuple(task.task_id for task in plan.tasks)
    excluded = tuple(item.task_id for item in plan.exclusions)
    _unique(planned)
    _unique(plan.eligible_ids)
    _unique(excluded)
    eligible_set, excluded_set = set(plan.eligible_ids), set(excluded)
    if eligible_set & excluded_set or eligible_set | excluded_set != set(planned):
        _fail()
    if tuple(task for task in planned if task in eligible_set) != plan.eligible_ids:
        _fail()


def _validate_values(plan, expected, batch):
    _validate_plan(plan)
    _validate_plan(batch.plan)
    for item in expected:
        if item.purpose not in _PURPOSES:
            _fail()
        _sha(item.sha256)
        if item.prediction_sha256 is not None:
            _sha(item.prediction_sha256)
    for sample in batch.samples:
        if sample.status not in _STATUSES:
            _fail()
        if sample.score is not None and sample.score not in (0, 1):
            _fail()
        if sample.prediction_sha256 is not None:
            _sha(sample.prediction_sha256)


def _check_unique(expected, batch):
    # Refuse BEFORE building any dictionary that could hide an ambiguous winner.
    _unique(tuple(item.evidence_id for item in expected))
    _unique(tuple(item.evidence_id for item in batch.blobs))
    _unique(tuple(item.attempt_id for item in batch.samples))
    _unique(tuple((item.task_id, item.slot_index) for item in batch.samples))
    _unique(tuple(
        reference for item in batch.samples
        for reference in (item.generation_evidence_id, item.scoring_evidence_id)
        if reference is not None
    ))


def _plan_projection(plan):
    """Complete primitive projection, never dataclass identity/equality."""
    return (
        tuple(object.__getattribute__(plan, name) for name in _PLAN_IDS),
        plan.policy_revision,
        tuple(object.__getattribute__(plan, name) for name in _PLAN_DIGESTS),
        plan.adapter_sha256,
        tuple((task.task_id, task.task_sha256, task.database_sha256) for task in plan.tasks),
        plan.eligible_ids, tuple((item.task_id, item.reason) for item in plan.exclusions),
        plan.g, plan.dead_ceiling,
        tuple(object.__getattribute__(plan.scorer, name) for name in ScorerBinding.__slots__),
    )


class _Issues:
    __slots__ = ("maximum", "examples", "total", "consistent")

    def __init__(self, maximum):
        self.maximum = maximum
        self.examples = []
        self.total = 0
        self.consistent = True

    def add(self, code, ordinal=None, slot=None, *, inconsistent=True):
        self.total += 1
        if inconsistent:
            self.consistent = False
        if len(self.examples) < self.maximum:
            self.examples.append((code, ordinal, slot))


def _pins_match(expected, blob, digest):
    return expected.byte_count == len(blob.payload) and expected.sha256 == digest


def _association_matches(expected, purpose, plan, sample=None):
    if (
        expected.purpose != purpose or expected.plan_id != plan.plan_id
        or expected.execution_id != plan.execution_id
    ):
        return False
    if purpose == "checkpoint":
        return (
            expected.task_id is None and expected.slot_index is None
            and expected.attempt_id is None and expected.generation_evidence_id is None
            and expected.prediction_sha256 is None
        )
    if (
        expected.task_id != sample.task_id or expected.slot_index != sample.slot_index
        or expected.attempt_id != sample.attempt_id
        or expected.prediction_sha256 != sample.prediction_sha256
    ):
        return False
    if purpose == "generation":
        return expected.generation_evidence_id is None
    return expected.generation_evidence_id == sample.generation_evidence_id


def _sample_shape_valid(sample):
    generation = sample.generation_evidence_id is not None
    scoring = sample.scoring_evidence_id is not None
    prediction = sample.prediction_sha256 is not None
    score = sample.score is not None
    if sample.status == "scored":
        return generation and scoring and prediction and score
    if sample.status == "invalid_gold":
        return generation and scoring and prediction and not score
    if sample.status == "generation_failed":
        return generation and not scoring and not prediction and not score
    return not score and not scoring and (generation or not prediction)


def _coverage_complete(scheduled, observed):
    return scheduled == observed


def validate_frontier_bindings(
    plan: MeasurementPlan,
    expected_evidence: tuple[ExpectedEvidence, ...],
    candidate: EvidenceBatch,
    *,
    limits: BindingLimits,
) -> BindingReport:
    """Validate a complete bounded declaration graph, never external authority.

    schedule_complete describes record coverage only. valid_declared_scores
    counts locally bound binary declarations, not authenticated scorer results.
    All public outcomes remain unverified, including fully matching replays.
    """
    plan, expected, batch, limits = _snapshot(plan, expected_evidence, candidate, limits)
    # Nothing below receives original mutable/forged records or unbounded input.
    _validate_values(plan, expected, batch)
    _check_unique(expected, batch)
    _check_membership(plan)
    _check_membership(batch.plan)
    issues = _Issues(limits.max_diagnostics)
    projection_good = _plan_projection(plan) == _plan_projection(batch.plan)
    if not projection_good:
        issues.add("plan_mismatch")

    expected_by_id = {item.evidence_id: item for item in expected}
    raw_ids = {item.evidence_id for item in batch.blobs}
    matched = set()
    for blob in batch.blobs:
        digest = hashlib.sha256(blob.payload).hexdigest()
        declaration = expected_by_id.get(blob.evidence_id)
        if declaration is None:
            issues.add("evidence_extra")
        elif _pins_match(declaration, blob, digest):
            matched.add(blob.evidence_id)
        else:
            issues.add("evidence_bytes")
    for declaration in expected:
        if declaration.evidence_id not in raw_ids:
            issues.add("evidence_missing")

    checkpoints = tuple(item for item in expected if item.purpose == "checkpoint")
    used = set()
    checkpoint_good = len(checkpoints) == 1
    if not checkpoint_good:
        issues.add("checkpoint_count")
    for declaration in checkpoints:
        used.add(declaration.evidence_id)
        if not _association_matches(declaration, "checkpoint", plan):
            checkpoint_good = False
            issues.add("checkpoint_association")
        if declaration.sha256 != plan.checkpoint_sha256:
            checkpoint_good = False
            issues.add("checkpoint_inventory")
        if declaration.evidence_id not in matched:
            checkpoint_good = False

    ordinals = {task.task_id: ordinal for ordinal, task in enumerate(plan.tasks)}
    eligible = set(plan.eligible_ids)
    samples = {}
    for sample in batch.samples:
        ordinal = ordinals.get(sample.task_id)
        in_schedule = sample.task_id in eligible and sample.slot_index < plan.g
        shape_good = _sample_shape_valid(sample)
        good = shape_good
        if not in_schedule:
            good = False
            issues.add("sample_outside_schedule", ordinal, sample.slot_index)
        if not shape_good:
            issues.add("score_status", ordinal, sample.slot_index)
        for reference, purpose in (
            (sample.generation_evidence_id, "generation"),
            (sample.scoring_evidence_id, "scoring"),
        ):
            if reference is None:
                continue
            used.add(reference)
            declaration = expected_by_id.get(reference)
            if declaration is None:
                good = False
                issues.add("evidence_reference", ordinal, sample.slot_index)
            else:
                if not _association_matches(declaration, purpose, plan, sample):
                    good = False
                    issues.add("expected_association", ordinal, sample.slot_index)
                if reference not in matched:
                    good = False
        if in_schedule:
            samples[(sample.task_id, sample.slot_index)] = (sample, good)
    for declaration in expected:
        if declaration.evidence_id not in used:
            issues.add("evidence_unreferenced")

    counts = {status: 0 for status in _DISPOSITIONS}
    slots = []
    valid_scores = 0
    for task_id in plan.eligible_ids:
        ordinal = ordinals[task_id]
        for index in range(plan.g):
            binding = samples.get((task_id, index))
            if binding is None:
                counts["missing"] += 1
                issues.add("missing_sample", ordinal, index)
                slots.append(SlotDisposition(ordinal, index, "missing", False, False))
                continue
            sample, good = binding
            # Canonical fixed vocabulary, never an input identifier or payload.
            status = _STATUSES[_STATUSES.index(sample.status)]
            good = good and projection_good and checkpoint_good
            valid = good and status == "scored"
            counts[status] += 1
            if status != "scored":
                issues.add(status, ordinal, index, inconsistent=False)
            valid_scores += int(valid)
            slots.append(SlotDisposition(ordinal, index, status, good, valid))

    scheduled = len(plan.eligible_ids) * plan.g
    complete = _coverage_complete(scheduled, len(samples))
    return BindingReport(
        planned_tasks=len(plan.tasks), eligible_tasks=len(plan.eligible_ids),
        excluded_tasks=len(plan.exclusions), scheduled_slots=scheduled,
        observed_slots=len(samples), declared_attempts=len(batch.samples),
        matched_evidence=len(matched), valid_declared_scores=valid_scores,
        disposition_counts=tuple((status, counts[status]) for status in _DISPOSITIONS),
        slots=tuple(slots), diagnostics=tuple(issues.examples), total_issues=issues.total,
        diagnostics_truncated=issues.total > len(issues.examples),
        bindings_consistent=issues.consistent, schedule_complete=complete,
        all_samples_validly_scored=(
            issues.consistent and complete and valid_scores == scheduled
        ),
    )
