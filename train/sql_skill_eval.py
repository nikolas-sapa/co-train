"""Bounded opt-in qualification/reuse through the existing real capture path.

Caller-authored programs only. No native tools, models, registry or automatic
learning. AST/tracing/evidence limits are not an OS or hard-memory sandbox.
External approval pins and caller-owned evaluator/assets remain the trust root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bench.task import SqlTask
from ptc.sql_isolation import PilotExecutor
from train import guards
from train import sql_capture as capture
from train import sql_episodes as evidence
from train import sql_skills as skills


__all__ = [
    "SkillCase", "evaluate_candidate", "promote_candidate", "reuse_promoted",
]

_ROOT = Path(__file__).resolve().parents[1]
_PREFIX = "FINAL_SQL:"


@dataclass(frozen=True)
class SkillCase:
    """Host-only external task input; never encoded into skill artifacts."""

    role: str
    task: SqlTask
    ids: evidence.EpisodeIds
    expected_db_sha256: str | None = field(default=None, kw_only=True)

    def __post_init__(self):
        skills._guard(_validate_case, self)


def _validate_case(case):
    if type(case) is not SkillCase:
        raise TypeError("case must be SkillCase")
    evidence._text(case.role, "role")
    if case.role not in ("source_failure", "qualification", "reuse"):
        raise ValueError("unsupported skill case role")
    evidence._task_payload(case.task)
    evidence._validate_ids(case.ids)
    if case.expected_db_sha256 is not None:
        evidence._digest(case.expected_db_sha256, "expected_db_sha256")


def _opt_in(allow_execution):
    if allow_execution is not True:
        raise ValueError("skill execution requires allow_execution is True")


def _admit_scope(candidate, case):
    """Exact caller routing declarations, not semantic-policy certification."""
    _validate_case(case)
    scope = skills.SkillScope(case.task.source, case.task.shape, case.task.coarse_shape)
    if scope != candidate.scope:
        raise ValueError("case routing scope differs from candidate")
    if skills._provenance(case.ids) != skills._provenance(candidate.source.ids):
        raise ValueError("case ID provenance differs from source")


def _current_binding(task, executor=None):
    pair = evidence.sql_arms.build_sql_arms(task)
    instrument = capture._instrument(pair, guards.eval_max_turns(), executor)
    try:
        sources = tuple(
            (name, skills._sha((_ROOT / name).read_bytes()))
            for name in skills.SOURCE_PATHS
        )
    except OSError as exc:
        raise ValueError("cannot read selected skill workflow sources") from exc
    return skills.SkillBinding(
        instrument, skills.SOURCE_PATHS, skills._sha(evidence._json_bytes(sources)),
        capture._execution_binding(executor),
    )


def _execute(candidate, case, *, expected_db_sha256=None, executor=None):
    if case.expected_db_sha256 is not None:
        if expected_db_sha256 is not None and expected_db_sha256 != case.expected_db_sha256:
            raise ValueError("admitted and case database expectations differ")
        expected_db_sha256 = case.expected_db_sha256
    if expected_db_sha256 is not None:
        evidence._digest(expected_db_sha256, "expected_db_sha256")
        evidence._check_database(case.task, expected_db_sha256)

    def checked(actual):
        if expected_db_sha256 is not None and actual.db_sha256 != expected_db_sha256:
            raise ValueError("execution capture differs from expected database snapshot")
        return actual

    try:
        session = capture.start_capture(
            case.task, ids=case.ids, allow_execution=True, executor=executor,
            expected_db_sha256=expected_db_sha256,
        )
        if expected_db_sha256 is not None:
            evidence._check_database(case.task, expected_db_sha256)
        observation = session.step(candidate.program)
        if not observation.startswith(_PREFIX):
            return checked(session.abort())
        sql = observation[len(_PREFIX):]
        if not sql.strip():
            return checked(session.abort())
        # The existing capture owns bounds/extraction and protected EX. Do not
        # strip/normalise or execute this suffix as Python, or replay the program.
        return checked(session.finish(sql))
    except capture.CaptureProgramRejected as exc:
        return checked(exc.capture)
    except capture.CaptureExecutionAborted as exc:
        checked(exc.capture)
        raise


def evaluate_candidate(
    candidate: skills.SkillCandidate, case: SkillCase, *, allow_execution=False,
    executor: PilotExecutor | None = None,
) -> capture.SqlCapture:
    """Provisional only; even EX=1 here cannot authorize promotion."""
    _opt_in(allow_execution)
    skills.encode_candidate(candidate)
    _admit_scope(candidate, case)
    if case.role not in ("qualification", "reuse"):
        raise ValueError("provisional evaluation requires qualification or reuse role")
    capture._execution_binding(executor)
    if executor is not None and _current_binding(case.task, executor).instrument != candidate.source.instrument:
        raise ValueError("current candidate source/runtime binding differs")
    return _execute(candidate, case, executor=executor)


def _admit_origin(candidate, source_capture, expected_pin, source_case, executor=None):
    evidence._digest(expected_pin, "expected_source_capture_sha256")
    source = skills._source_ref(source_capture)
    if source.capture_sha256 != expected_pin or source != candidate.source:
        raise ValueError("external source pin/reference differs from candidate")
    skills._declared_failure(source_capture)
    _admit_scope(candidate, source_case)
    if source_case.role != "source_failure" or source_case.ids != source.ids:
        raise ValueError("external source case role/IDs differ")
    if (
        source_case.expected_db_sha256 is not None
        and source_case.expected_db_sha256 != source_capture.db_sha256
    ):
        raise ValueError("source case database expectation differs from capture")
    # This is the authority for actual failure, not the recorded result.
    result = capture.rescore_capture(
        source_capture, source_case.task, ids=source_case.ids,
        executor=executor,
    )
    if result.valid is not True or result.score != 0:
        raise ValueError("source must independently rescore to valid EX=0")


def _admit_qualifications(candidate, cases):
    if type(cases) is not tuple:
        raise TypeError("qualification_cases must be an external tuple")
    if len(cases) != 4:
        raise ValueError("exactly four external qualification cases required")
    identities = {skills._identity(candidate.source.ids)}
    fingerprints = {candidate.source.task_fingerprint}
    databases = {candidate.source.db_sha256}
    admitted = []
    for case in cases:
        _admit_scope(candidate, case)
        if case.role != "qualification":
            raise ValueError("all four cases require qualification role")
        if case.ids.split_id == candidate.source.ids.split_id:
            raise ValueError("qualification split must differ from source split")
        fingerprint = evidence._fingerprint(evidence._task_payload(case.task))
        digest = case.expected_db_sha256
        if digest is None:
            digest = evidence._db_digest(case.task)
        else:
            evidence._check_database(case.task, digest)
        identity = skills._identity(case.ids)
        if identity in identities or fingerprint in fingerprints or digest in databases:
            raise ValueError("qualification cases must be disjoint from origin and each other")
        identities.add(identity)
        fingerprints.add(fingerprint)
        databases.add(digest)
        admitted.append((case, fingerprint, digest))
    # Recheck all four snapshots after completing the manifest, before dispatch.
    for case, _, digest in admitted:
        evidence._check_database(case.task, digest)
    return tuple(admitted)


def promote_candidate(
    candidate: skills.SkillCandidate, *, source_capture: capture.SqlCapture,
    expected_source_capture_sha256: str, source_case: SkillCase,
    qualification_cases: tuple[SkillCase, ...], ids: evidence.EpisodeIds,
    allow_execution=False, executor: PilotExecutor | None = None,
) -> tuple[skills.SkillPromotion | None, tuple[capture.SqlCapture, ...]]:
    """Rescore source, admit four external cases, then rerun each once.

    Unexpected errors retain obtained qualification_captures on the same exception.
    """
    _opt_in(allow_execution)
    candidate_bytes = skills.encode_candidate(candidate)
    evidence._validate_ids(ids)
    if skills._provenance(ids) != skills._provenance(candidate.source.ids):
        raise ValueError("promotion ID provenance differs from source")
    capture._execution_binding(executor)
    _admit_origin(
        candidate, source_capture, expected_source_capture_sha256, source_case,
        executor,
    )
    admitted = _admit_qualifications(candidate, qualification_cases)
    binding = _current_binding(admitted[0][0].task, executor)
    captures = []
    references = []
    try:
        for case, fingerprint, digest in admitted:
            if _current_binding(case.task, executor) != binding:
                raise ValueError("workflow binding changed before qualification")
            try:
                actual = _execute(candidate, case, expected_db_sha256=digest, executor=executor)
            except capture.CaptureExecutionAborted as exc:
                captures.append(exc.capture)
                return None, tuple(captures)
            captures.append(actual)
            if (
                actual.terminal_label != "final_submitted"
                or actual.result.valid is not True or actual.result.score != 1
            ):
                return None, tuple(captures)
            if (
                actual.task_fingerprint != fingerprint or actual.db_sha256 != digest
                or actual.instrument != binding.instrument
                or actual.execution_binding != binding.execution_binding
            ):
                raise ValueError("qualification capture differs from admitted task/runtime")
            references.append(skills.QualificationRef(
                case.role, case.ids, actual.task_id, actual.task_fingerprint,
                actual.db_sha256, skills._sha(capture.encode_capture(actual)), actual.result,
            ))
        if _current_binding(admitted[0][0].task, executor) != binding:
            raise ValueError("workflow binding changed during qualification")
        promotion = skills.SkillPromotion(
            skills.SCHEMA_VERSION if executor is None else 2, skills._sha(candidate_bytes), candidate.scope,
            candidate.source, ids, binding, tuple(references),
        )
        skills.encode_promotion(promotion)
    except Exception as exc:
        # Preserve failure identity/cause and only evidence already obtained.
        # In particular, never synthesize the current unsealed attempt.
        exc.qualification_captures = tuple(captures)
        raise
    return promotion, tuple(captures)


def reuse_promoted(
    candidate: skills.SkillCandidate, promotion: skills.SkillPromotion,
    case: SkillCase, *, expected_promotion_sha256: str, ids: evidence.EpisodeIds,
    allow_execution=False, executor: PilotExecutor | None = None,
) -> capture.SqlCapture:
    """Trust an externally approved receipt, never reopen old evidence databases."""
    _opt_in(allow_execution)
    candidate_bytes = skills.encode_candidate(candidate)
    promotion_bytes = skills.encode_promotion(promotion)
    evidence._digest(expected_promotion_sha256, "expected_promotion_sha256")
    if skills._sha(promotion_bytes) != expected_promotion_sha256:
        raise ValueError("external approved promotion pin differs")
    if (
        skills._sha(candidate_bytes) != promotion.candidate_sha256
        or candidate.scope != promotion.scope or candidate.source != promotion.source
    ):
        raise ValueError("candidate pin/scope/source differs from approved promotion")
    evidence._validate_ids(ids)
    if ids != promotion.ids:
        raise ValueError("external approval IDs differ from promotion")
    _admit_scope(candidate, case)
    if case.role != "reuse":
        raise ValueError("approved reuse requires reuse role")
    digest = case.expected_db_sha256
    if digest is None:
        digest = evidence._db_digest(case.task)
    else:
        evidence._check_database(case.task, digest)
    if _current_binding(case.task, executor) != promotion.binding:
        raise ValueError("current capture/workflow runtime binding differs")
    return _execute(candidate, case, expected_db_sha256=digest, executor=executor)
