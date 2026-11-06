"""Single-use, bounded retention of actual offline probe observations.

Producer-generated pins check self-consistency, not independent custody.
No models, external receipts, persistent schema, writers or authority gates.
Raw host results are sensitive; the legacy ProbeResult remains mutable.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock

from bench import prepare
from bench.frontier.draw_probe import probe_validated_draw
from bench.frontier.probe import ProbeResult, SampleObservation
from bench.score import ExResult
from bench.task import SqlTask
from train import frontier_bindings as core

__all__ = ["CaptureError", "CaptureSnapshot", "CapturedProbe", "CaptureSession"]

_GOLD_VOID = ("gold_error", "gold_timeout", "gold_truncated")
_VALID = ("match", "mismatch", "pred_error", "pred_timeout",
          "pred_truncated", "pred_empty")
_REASONS = ("capture_refused", "database_unavailable", "unknown_operational_outcome")
_SCORE_PREFIX = b"frontier-score-v1;"
_MAX_INTEGER = (1 << 63) - 1


class CaptureError(ValueError):
    """Opaque refusal. Codes are code-owned, never supplied content."""

    def __init__(self, code="capture_refused"):
        self.code = code if type(code) is str and code in _REASONS else "capture_refused"
        super().__init__("frontier capture refused")


def _fail(code="capture_refused"):
    raise CaptureError(code) from None


@dataclass(frozen=True, slots=True)
class CaptureSnapshot:
    state: str
    callback_invocations: int
    retained_completions: int
    observations: int
    evidence_items: int
    reason: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class CapturedProbe:
    """Sensitive results. Only the wrapper/evidence are frozen, NOT result."""

    result: ProbeResult
    batch: core.EvidenceBatch
    retention_pins: tuple[core.ExpectedEvidence, ...]
    report: core.BindingReport


def _utf8_size(value, maximum):
    """Count before encode/allocation, rejecting subclasses and lone surrogates."""
    if type(value) is not str or len(value) > maximum:
        _fail()
    size = 0
    for character in value:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF:
            _fail()
        size += 1 if point < 0x80 else 2 if point < 0x800 else 3 if point < 0x10000 else 4
        if size > maximum:
            _fail()
    return size


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _namespace(plan, task_id, slot, purpose, maximum):
    # Decimal UTF8 byte lengths make delimiters/Unicode in IDs unambiguous.
    values = (plan.plan_id, plan.execution_id, task_id, str(slot), purpose)
    sizes = tuple(_utf8_size(value, maximum) for value in values)
    length = 4 + sum(len(str(size)) + 1 + size for size in sizes)
    if length > maximum:
        _fail()
    return "fc1;" + "".join(str(size) + ":" + value
                           for size, value in zip(sizes, values, strict=True))


def _text_bytes(value):
    # Only previously exact-type, UTF8-bounded internal record strings.
    return len(value.encode("utf-8"))


def _checkpoint_pin(plan, evidence_id, inventory):
    return core.ExpectedEvidence(
        evidence_id, "checkpoint", plan.plan_id, plan.execution_id,
        None, None, None, None, None, len(inventory), _sha(inventory))


def _core_check(plan, pins, batch, limits):
    try:
        return core.validate_frontier_bindings(plan, pins, batch, limits=limits)
    except core.BindingError:
        _fail()


def _reserve(plan, limits, checkpoint_pin, inventory):
    """Reserve the complete graph's deterministic strings, never fake samples.

    Same byte accounting as core: two plan projections, expected strings, raw
    IDs/payloads and sample strings. Pins ARE the expected declaration tuple,
    not a second independent source. Reserve the longer invalid_gold status.
    """
    budget = core._Budget(limits)
    core._snapshot_plan(plan, budget)
    core._snapshot_plan(plan, budget)
    checkpoint = checkpoint_pin.evidence_id
    for value in (checkpoint, "checkpoint", plan.plan_id, plan.execution_id,
                  checkpoint_pin.sha256, checkpoint):
        budget.charge(_text_bytes(value))
    budget.charge(len(inventory))
    identifiers = []
    for task_id in plan.eligible_ids:
        for slot in range(plan.g):
            attempt, generation, scoring = (
                _namespace(plan, task_id, slot, purpose, limits.max_identifier_bytes)
                for purpose in ("a", "g", "s"))
            # Expected generation/scoring, raw gen/score, and sample record.
            strings = (
                generation, "generation", plan.plan_id, plan.execution_id,
                task_id, attempt,
                scoring, "scoring", plan.plan_id, plan.execution_id,
                task_id, attempt, generation,
                generation, scoring,
                task_id, attempt, "invalid_gold", generation, scoring,
            )
            # Each expected has prediction+payload hashes; sample has prediction.
            budget.charge(sum(_text_bytes(value) for value in strings) + 5 * 64)
            identifiers.append((task_id, slot, attempt, generation, scoring))
    return budget.used, tuple(identifiers)


def _encode_score(sql, result, budget, limits):
    """Preflight actual framed representation before any large encode/join."""
    if type(result) is not ExResult:
        _fail()
    # Copy original six fields now; never retain a mutable host record reference.
    try:
        score, status, valid, detail, predicted, gold = (
            object.__getattribute__(result, name) for name in
            ("score", "status", "valid", "detail", "n_pred_rows", "n_gold_rows"))
    except AttributeError:
        _fail()
    if type(score) not in (int, float) or score not in (0, 1):
        _fail()
    if type(valid) is not bool or type(status) is not str:
        _fail()
    if status == "db_missing":
        _fail("database_unavailable")
    if (valid and status not in _VALID) or (not valid and status not in _GOLD_VOID):
        _fail()
    if ((status == "match" and score != 1)
            or (valid and status != "match" and score != 0)
            or (not valid and score != 0)):
        _fail()
    for count in (predicted, gold):
        if type(count) is not int or not 0 <= count <= _MAX_INTEGER:
            _fail()
    sql_size = _utf8_size(sql, limits.max_item_bytes)
    detail_size = _utf8_size(detail, limits.max_item_bytes)
    score_text = ("i:" + str(score)) if type(score) is int else "f:" + score.hex()
    # Digest has exactly 64 ASCII bytes; it is computed only after admission.
    fields = (sql, None, score_text, status, "true" if valid else "false",
              detail, str(predicted), str(gold))
    sizes = (sql_size, 64, len(score_text), len(status), 4 if valid else 5,
             detail_size, len(str(predicted)), len(str(gold)))
    length = len(_SCORE_PREFIX) + sum(len(str(n)) + 1 + n for n in sizes)
    if length > limits.max_item_bytes:
        _fail()
    # Settle only this observed status reservation. Never borrow unknown future
    # payload space. Complete scored captures use their exact representation.
    if valid:
        budget.used -= len("invalid_gold") - len("scored")
    budget.charge(length)
    prediction = _sha(sql.encode("utf-8"))
    encoded = []
    for index, (field, size) in enumerate(zip(fields, sizes, strict=True)):
        encoded.append(str(size).encode("ascii") + b":")
        encoded.append(prediction.encode("ascii") if index == 1 else field.encode("utf-8"))
    return (_SCORE_PREFIX + b"".join(encoded), prediction,
            "scored" if valid else "invalid_gold", score if valid else None)


def _observation_matches(observation, task_id, slot, completion):
    if type(observation) is not SampleObservation:
        return False
    try:
        observed_task, observed_slot, observed_completion = (
            object.__getattribute__(observation, name)
            for name in ("task_id", "slot_index", "completion"))
    except AttributeError:
        return False
    return (
        type(observed_task) is str and observed_task == task_id
        and type(observed_slot) is int and observed_slot == slot
        and type(observed_completion) is str and observed_completion == completion
    )


def _bind_admitted(plan, admitted):
    """Existing preparation owns corpus/source/database revalidation."""
    if type(admitted) is not prepare.ValidatedDraw:
        _fail()
    if (len(admitted.planned) != len(plan.tasks)
            or len(admitted.eligible) != len(plan.eligible_ids)
            or len(admitted.exclusions) != len(plan.exclusions)
            or len(admitted.databases) > len(plan.tasks)):
        _fail()
    databases = {db.db_id: db.sha256 for db in admitted.databases}
    actual = tuple((t.name, prepare._task_sha256(t), databases.get(t.db_id))
                   for t in admitted.planned)
    declared = tuple((t.task_id, t.task_sha256, t.database_sha256) for t in plan.tasks)
    if (
        actual != declared
        or tuple(t.name for t in admitted.eligible) != plan.eligible_ids
        or tuple((e.id, e.status) for e in admitted.exclusions)
        != tuple((e.task_id, e.reason) for e in plan.exclusions)
        or admitted.draw_sha256 != plan.draw_sha256
        or admitted.supplement_sha256 != plan.supplement_sha256
        or admitted.comparison != plan.scorer.comparison
        or admitted.timeout_s != plan.scorer.timeout_s
        or admitted.max_rows != plan.scorer.max_rows
    ):
        _fail()
    sources = prepare._source_sha256()
    if (
        _sha(prepare._canonical_bytes(sources)) != plan.source_sha256
        or sources["bench/score.py"] != plan.scorer.extraction_source_sha256
        or sources["bench/score.py"] != plan.scorer.scorer_source_sha256
    ):
        _fail()


def _report_matches(report, plan, batch, pins, known_missing, invalid_count):
    """Full counters/slots are authoritative here, NOT diagnostic examples."""
    ordinals = {t.task_id: i for i, t in enumerate(plan.tasks)}
    wanted_missing = {(ordinals[task_id], slot) for task_id, slot in known_missing}
    missing = {(s.task_ordinal, s.slot_index) for s in report.slots
               if s.disposition == "missing"}
    observed_good = all(s.bindings_consistent for s in report.slots
                        if s.disposition != "missing")
    return (
        missing == wanted_missing and observed_good
        and report.observed_slots == report.declared_attempts == len(batch.samples)
        and report.matched_evidence == len(batch.blobs) == len(pins)
        and report.valid_declared_scores == len(batch.samples) - invalid_count
        and report.total_issues == len(known_missing) + invalid_count
        and report.schedule_complete is (not known_missing)
        and report.bindings_consistent is (not known_missing)
        and report.provenance == "unverified" and report.attested_facts == ()
        and report.genuine_measurement_accepted is False
        and report.training_authorized is False
    )


class CaptureSession:
    """One synchronous operation; snapshots reveal only lifecycle/counts.

    Callback invocation is not provider success/failure/retirement. A FINISHED
    session may have known gold-void gaps, and never authenticates measurement.
    """

    __slots__ = (
        "_plan", "_limits", "_inventory", "_checkpoint", "_ids",
        "_reserved_bytes", "_lock", "_state", "_calls", "_retained",
        "_observed", "_items", "_reason", "_callback_failed",
    )

    def __init__(self, plan, checkpoint_inventory, *, limits):
        # Pure core admission; no preparation, corpus, SQL, generator or file IO.
        try:
            limits = core._snapshot_limits(limits)
            temporary = core._Budget(limits)
            plan = core._snapshot_plan(plan, temporary)
            core._validate_plan(plan)
            core._check_membership(plan)
            count = len(plan.eligible_ids) * plan.g
            if 2 * count + 1 > min(limits.max_expected_evidence, limits.max_raw_evidence):
                _fail()
            if (type(checkpoint_inventory) is not bytes
                    or len(checkpoint_inventory) > limits.max_item_bytes):
                _fail()
            checkpoint_id = _namespace(
                plan, "", 0, "c", limits.max_identifier_bytes)
            checkpoint = _checkpoint_pin(plan, checkpoint_id, checkpoint_inventory)
            initial_batch = core.EvidenceBatch(
                plan, (core.EvidenceBlob(checkpoint_id, checkpoint_inventory),), ())
            report = _core_check(plan, (checkpoint,), initial_batch, limits)
            if (report.matched_evidence != 1 or report.observed_slots != 0
                    or report.total_issues != count
                    or checkpoint.sha256 != plan.checkpoint_sha256):
                _fail()
            reserved, identifiers = _reserve(
                plan, limits, checkpoint, checkpoint_inventory)
        except core.BindingError:
            _fail()
        self._plan, self._limits = plan, limits
        self._inventory, self._checkpoint = checkpoint_inventory, checkpoint
        self._reserved_bytes, self._ids = reserved, identifiers
        self._lock = Lock()
        self._state = "READY"
        self._calls = self._retained = self._observed = 0
        self._items, self._reason = 1, "none"
        self._callback_failed = False

    @property
    def snapshot(self):
        with self._lock:
            return CaptureSnapshot(self._state, self._calls, self._retained,
                                   self._observed, self._items, self._reason)

    def run(self, root, draw_path, supplement_path, generate, *,
            expected_draw_sha256, expected_supplement_sha256, fixture):
        # Reentry refusal is outside the operation handler: don't poison its owner.
        with self._lock:
            if self._state != "READY":
                _fail()
            self._state = "RUNNING"
        try:
            return self._run(root, draw_path, supplement_path, generate,
                             expected_draw_sha256, expected_supplement_sha256, fixture)
        except BaseException as error:
            reason = "unknown_operational_outcome"
            if type(error) is CaptureError and not self._callback_failed:
                # Exception instances are mutable caller objects too. Never let
                # a changed/deleted code leak text or mask the original failure.
                try:
                    code = object.__getattribute__(error, "code")
                except AttributeError:
                    code = None
                reason = (code if type(code) is str and code in _REASONS
                          else "capture_refused")
            with self._lock:
                self._state = "QUARANTINED"
                self._reason = reason
            # No cleanup, retries, provider claims or replacement exceptions.
            raise

    def _run(self, root, draw_path, supplement_path, generate,
             expected_draw_sha256, expected_supplement_sha256, fixture):
        plan, limits = self._plan, self._limits
        if (
            type(expected_draw_sha256) is not str
            or type(expected_supplement_sha256) is not str
            or expected_draw_sha256 != plan.draw_sha256
            or expected_supplement_sha256 != plan.supplement_sha256
            or type(fixture) is not bool or not callable(generate)
        ):
            _fail()
        admission_kwargs = dict(expected_draw_sha256=expected_draw_sha256,
                                expected_supplement_sha256=expected_supplement_sha256,
                                fixture=fixture)
        admitted = prepare.load_validated_draw(
            root, draw_path, supplement_path, **admission_kwargs)
        _bind_admitted(plan, admitted)
        tasks = {t.name: t for t in admitted.eligible}
        budget = core._Budget(limits)
        budget.used = self._reserved_bytes
        blobs = [core.EvidenceBlob(self._checkpoint.evidence_id, self._inventory)]
        pins, samples, known_missing = [self._checkpoint], [], []
        cursor, outstanding, invalid_count = 0, None, 0

        def wrapped(task):
            nonlocal outstanding
            if outstanding is not None or cursor >= len(self._ids):
                _fail()
            task_id, slot, attempt, generation_id, scoring_id = self._ids[cursor]
            if type(task) is not SqlTask or task.name != task_id or task != tasks[task_id]:
                _fail()
            # No raw partial is installed on the session object.
            outstanding = (task_id, slot, attempt, generation_id, scoring_id, None, None)
            with self._lock:
                self._calls += 1
            try:
                completion = generate(task)
            except BaseException:
                self._callback_failed = True
                raise
            # Refuse in-memory task mutation too, not just persistent corpus drift.
            if task != tasks[task_id]:
                _fail()
            length = _utf8_size(completion, limits.max_item_bytes)
            try:
                budget.charge(length)
            except core.BindingError:
                _fail()
            payload = completion.encode("utf-8")
            outstanding = (task_id, slot, attempt, generation_id, scoring_id,
                           completion, payload)
            with self._lock:
                self._retained += 1
            return completion

        def observe(observation):
            nonlocal outstanding, cursor, invalid_count
            if outstanding is None:
                _fail()
            task_id, slot, attempt, generation_id, scoring_id, completion, payload = outstanding
            if not _observation_matches(observation, task_id, slot, completion):
                _fail()
            try:
                extracted_sql = object.__getattribute__(observation, "extracted_sql")
                original_result = object.__getattribute__(observation, "result")
            except AttributeError:
                _fail()
            try:
                scoring_bytes, prediction, status, score = _encode_score(
                    extracted_sql, original_result, budget, limits)
            except core.BindingError:
                _fail()
            generation = core.ExpectedEvidence(
                generation_id, "generation", plan.plan_id, plan.execution_id,
                task_id, slot, attempt, None, prediction, len(payload), _sha(payload))
            scoring = core.ExpectedEvidence(
                scoring_id, "scoring", plan.plan_id, plan.execution_id,
                task_id, slot, attempt, generation_id, prediction,
                len(scoring_bytes), _sha(scoring_bytes))
            pins.extend((generation, scoring))
            blobs.extend((core.EvidenceBlob(generation_id, payload),
                          core.EvidenceBlob(scoring_id, scoring_bytes)))
            samples.append(core.SampleRecord(
                task_id, slot, attempt, status, score, generation_id, scoring_id, prediction))
            outstanding = None
            cursor += 1
            if status == "invalid_gold":
                invalid_count += 1
                for suffix in range(slot + 1, plan.g):
                    known_missing.append((task_id, suffix))
                cursor += plan.g - slot - 1
            with self._lock:
                self._observed += 1
                self._items += 2

        # Exactly one invocation of the ORIGINAL helper, including its final
        # fresh admission. Explicit G/ceiling, no source/backend/gate rewiring.
        result = probe_validated_draw(
            root, draw_path, supplement_path, wrapped, **admission_kwargs,
            policy=plan.policy_revision, g=plan.g, dead_ceiling=plan.dead_ceiling,
            sample_observer=observe)
        if outstanding is not None or cursor != len(self._ids):
            _fail()
        batch = core.EvidenceBatch(plan, tuple(blobs), tuple(samples))
        retention_pins = tuple(pins)
        report = _core_check(plan, retention_pins, batch, limits)
        if not _report_matches(
                report, plan, batch, retention_pins, known_missing, invalid_count):
            _fail()
        captured = CapturedProbe(result, batch, retention_pins, report)
        with self._lock:
            self._state = "FINISHED"
        return captured
