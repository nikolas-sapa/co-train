"""Data-only, immutable artifacts for explicitly approved caller-authored skills.

Payload digests detect corruption. External pins cover entire canonical envelopes;
neither IDs nor self-digests authenticate a caller. Tasks/gold remain host-only.
Creation checks declared failure, not actual DB content or independent EX.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields

from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_isolation as isolation
from train import sql_capture as capture
from train import sql_episodes as evidence


__all__ = [
    "SkillScope", "SourceRef", "SkillCandidate", "SkillBinding",
    "QualificationRef", "SkillPromotion", "create_candidate",
    "encode_candidate", "decode_candidate", "encode_promotion", "decode_promotion",
]

SCHEMA_VERSION = 1
MAX_BYTES = evidence.MAX_BYTES
MAX_PROGRAM_BYTES = 65536
SOURCE_PATHS = ("train/sql_skills.py", "train/sql_skill_eval.py")
CANDIDATE_FORMAT = "sql_skill_candidate"
PROMOTION_FORMAT = "sql_skill_promotion"


def _guard(function, *args):
    try:
        return function(*args)
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid encoding or excessively nested skill artifact") from exc


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _identity(ids):
    evidence._validate_ids(ids)
    return ids.corpus_id, ids.split_id, ids.run_id, ids.episode_id


def _provenance(ids):
    evidence._validate_ids(ids)
    return ids.corpus_id, ids.policy_id, ids.policy_revision


@dataclass(frozen=True)
class SkillScope:
    source: str
    shape: str
    coarse_shape: str

    def __post_init__(self):
        _guard(_validate_scope, self)


def _validate_scope(scope):
    if type(scope) is not SkillScope:
        raise TypeError("scope must be SkillScope")
    for name in ("source", "shape", "coarse_shape"):
        evidence._text(getattr(scope, name), name, nonempty=True)


@dataclass(frozen=True)
class SourceRef:
    capture_sha256: str
    ids: evidence.EpisodeIds
    task_id: str
    task_fingerprint: str
    db_sha256: str
    instrument: evidence.InstrumentSettings

    def __post_init__(self):
        _guard(_validate_source, self)


def _validate_source(source):
    if type(source) is not SourceRef:
        raise TypeError("source must be SourceRef")
    for name in ("capture_sha256", "task_fingerprint", "db_sha256"):
        evidence._digest(getattr(source, name), name)
    evidence._text(source.task_id, "task_id", nonempty=True)
    evidence._validate_ids(source.ids)
    evidence._validate_instrument(source.instrument)


@dataclass(frozen=True)
class SkillCandidate:
    schema_version: int
    skill_id: str
    program: str
    scope: SkillScope
    source: SourceRef

    def __post_init__(self):
        _guard(_validate_candidate, self)


def _validate_candidate(candidate):
    if type(candidate) is not SkillCandidate:
        raise TypeError("candidate must be SkillCandidate")
    evidence._version(candidate.schema_version)
    evidence._text(candidate.skill_id, "skill_id", nonempty=True)
    evidence._text(candidate.program, "program", nonempty=True)
    if len(candidate.program.encode("utf-8")) > MAX_PROGRAM_BYTES:
        raise ValueError("program exceeds 65536 UTF-8 bytes")
    _validate_scope(candidate.scope)
    _validate_source(candidate.source)


@dataclass(frozen=True)
class SkillBinding:
    instrument: evidence.InstrumentSettings
    source_paths: tuple[str, ...]
    source_sha256: str
    execution_binding: isolation.ExecutionBinding | None = None

    def __post_init__(self):
        _guard(_validate_binding, self)


def _validate_binding(binding):
    if type(binding) is not SkillBinding:
        raise TypeError("binding must be SkillBinding")
    evidence._validate_instrument(binding.instrument)
    if type(binding.source_paths) is not tuple:
        raise TypeError("workflow source_paths must be a tuple")
    for path in binding.source_paths:
        evidence._text(path, "workflow source path", nonempty=True)
    if binding.source_paths != SOURCE_PATHS:
        raise ValueError("workflow source_paths differ from the selected modules")
    evidence._digest(binding.source_sha256, "source_sha256")
    if binding.execution_binding is not None:
        isolation.execution_binding_to_dict(binding.execution_binding)


@dataclass(frozen=True)
class QualificationRef:
    role: str
    ids: evidence.EpisodeIds
    task_id: str
    task_fingerprint: str
    db_sha256: str
    capture_sha256: str
    result: ExResult

    def __post_init__(self):
        _guard(_validate_qualification, self)


def _validate_qualification(ref):
    if type(ref) is not QualificationRef:
        raise TypeError("qualification must be QualificationRef")
    evidence._text(ref.role, "role")
    if ref.role != "qualification":
        raise ValueError("receipt references must have qualification role")
    evidence._validate_ids(ref.ids)
    evidence._text(ref.task_id, "task_id", nonempty=True)
    for name in ("task_fingerprint", "db_sha256", "capture_sha256"):
        evidence._digest(getattr(ref, name), name)
    evidence._validate_result(ref.result)
    if ref.result.valid is not True or ref.result.score != 1:
        raise ValueError("receipt qualifications require valid EX=1")


@dataclass(frozen=True)
class SkillPromotion:
    schema_version: int
    candidate_sha256: str
    scope: SkillScope
    source: SourceRef
    ids: evidence.EpisodeIds
    binding: SkillBinding
    qualifications: tuple[QualificationRef, ...]

    def __post_init__(self):
        _guard(_validate_promotion, self)


def _validate_promotion(promotion):
    if type(promotion) is not SkillPromotion:
        raise TypeError("promotion must be SkillPromotion")
    _promotion_version(promotion.schema_version)
    evidence._digest(promotion.candidate_sha256, "candidate_sha256")
    _validate_scope(promotion.scope)
    _validate_source(promotion.source)
    evidence._validate_ids(promotion.ids)
    _validate_binding(promotion.binding)
    if (promotion.schema_version == 2) != (promotion.binding.execution_binding is not None):
        raise ValueError("promotion version requires matching isolated binding")
    if _provenance(promotion.ids) != _provenance(promotion.source.ids):
        raise ValueError("promotion ID provenance differs from source")
    if type(promotion.qualifications) is not tuple:
        raise TypeError("qualifications must be a tuple")
    if len(promotion.qualifications) != 4:
        raise ValueError("exactly four qualification references required")
    identities = {_identity(promotion.source.ids)}
    fingerprints = {promotion.source.task_fingerprint}
    databases = {promotion.source.db_sha256}
    for ref in promotion.qualifications:
        _validate_qualification(ref)
        if (
            _provenance(ref.ids) != _provenance(promotion.source.ids)
            or ref.ids.split_id == promotion.source.ids.split_id
        ):
            raise ValueError("qualification ID provenance/split differs")
        key = _identity(ref.ids)
        if (
            key in identities or ref.task_fingerprint in fingerprints
            or ref.db_sha256 in databases
        ):
            raise ValueError("qualification references must be disjoint from origin and each other")
        identities.add(key)
        fingerprints.add(ref.task_fingerprint)
        databases.add(ref.db_sha256)


def _source_ref(source_capture):
    encoded = capture.encode_capture(source_capture)
    return SourceRef(
        _sha(encoded), source_capture.ids, source_capture.task_id,
        source_capture.task_fingerprint, source_capture.db_sha256,
        source_capture.instrument,
    )


def _declared_failure(source_capture):
    capture.encode_capture(source_capture)
    if (
        source_capture.terminal_label != "final_submitted"
        or source_capture.result.valid is not True
        or source_capture.result.score != 0
    ):
        raise ValueError("candidate requires a declared valid-zero submitted source")


def create_candidate(
    source_capture: capture.SqlCapture, *, source_task: SqlTask,
    source_ids: evidence.EpisodeIds, skill_id: str, program: str,
) -> SkillCandidate:
    """Data only: task-field consistency and declared failure, not verification."""
    def create():
        _declared_failure(source_capture)
        evidence._validate_ids(source_ids)
        payload = evidence._task_payload(source_task)
        if source_ids != source_capture.ids:
            raise ValueError("external source IDs differ from capture")
        if (
            source_task.name != source_capture.task_id
            or evidence._fingerprint(payload) != source_capture.task_fingerprint
        ):
            raise ValueError("source_task ID/fingerprint differs from capture")
        # No task, gold, DB path or question is stored or handed to the program.
        candidate = SkillCandidate(
            SCHEMA_VERSION, skill_id, program,
            SkillScope(source_task.source, source_task.shape, source_task.coarse_shape),
            _source_ref(source_capture),
        )
        encode_candidate(candidate)
        return candidate

    return _guard(create)


def _encode(record, validator, format):
    def encode():
        validator(record)
        payload = asdict(record)
        if type(record) is SkillPromotion:
            if record.schema_version == 1:
                del payload["binding"]["execution_binding"]
            else:
                payload["binding"]["execution_binding"] = isolation.execution_binding_to_dict(
                    record.binding.execution_binding,
                )
        return evidence._json_bytes({
            "format": format, "schema_version": record.schema_version,
            "payload": payload, "sha256": _sha(evidence._json_bytes(payload)),
        })

    return _guard(encode)


def encode_candidate(candidate: SkillCandidate) -> bytes:
    return _encode(candidate, _validate_candidate, CANDIDATE_FORMAT)


def encode_promotion(promotion: SkillPromotion) -> bytes:
    return _encode(promotion, _validate_promotion, PROMOTION_FORMAT)


def _ids_from(value):
    return evidence.EpisodeIds(**evidence._record_object(value, evidence.EpisodeIds))


def _instrument_from(value):
    values = evidence._record_object(value, evidence.InstrumentSettings).copy()
    if type(values["source_paths"]) is not list:
        raise TypeError("instrument source_paths must be a JSON array")
    values["source_paths"] = tuple(values["source_paths"])
    return evidence.InstrumentSettings(**values)


def _scope_from(value):
    return SkillScope(**evidence._record_object(value, SkillScope))


def _source_from(value):
    values = evidence._record_object(value, SourceRef).copy()
    values["ids"] = _ids_from(values["ids"])
    values["instrument"] = _instrument_from(values["instrument"])
    return SourceRef(**values)


def _candidate_from(value):
    values = evidence._record_object(value, SkillCandidate).copy()
    values["scope"] = _scope_from(values["scope"])
    values["source"] = _source_from(values["source"])
    return SkillCandidate(**values)


def _promotion_from(value):
    values = evidence._record_object(value, SkillPromotion).copy()
    values["scope"] = _scope_from(values["scope"])
    values["source"] = _source_from(values["source"])
    values["ids"] = _ids_from(values["ids"])
    _promotion_version(values["schema_version"])
    names = tuple(f.name for f in fields(SkillBinding)
                  if values["schema_version"] == 2 or f.name != "execution_binding")
    binding = evidence._object(values["binding"], names).copy()
    if values["schema_version"] == 2:
        binding["execution_binding"] = isolation.execution_binding_from_dict(binding["execution_binding"])
    binding["instrument"] = _instrument_from(binding["instrument"])
    if type(binding["source_paths"]) is not list:
        raise TypeError("workflow source_paths must be a JSON array")
    binding["source_paths"] = tuple(binding["source_paths"])
    values["binding"] = SkillBinding(**binding)
    if type(values["qualifications"]) is not list:
        raise TypeError("qualifications must be a JSON array")
    refs = []
    for value in values["qualifications"]:
        ref = evidence._record_object(value, QualificationRef).copy()
        ref["ids"] = _ids_from(ref["ids"])
        ref["result"] = ExResult(**evidence._record_object(ref["result"], ExResult))
        refs.append(QualificationRef(**ref))
    values["qualifications"] = tuple(refs)
    return SkillPromotion(**values)


def _promotion_version(value):
    if type(value) is not int or value not in (1, 2):
        raise ValueError("unsupported promotion schema version")


def _decode(data, format, constructor):
    def decode():
        if type(data) is not bytes:
            raise TypeError("encoded skill artifact must be bytes")
        if len(data) > MAX_BYTES:
            raise ValueError("skill artifact exceeds 8 MiB")
        envelope = json.loads(
            data.decode("utf-8"), object_pairs_hook=evidence._unique_object,
            parse_constant=evidence._reject_constant,
        )
        evidence._object(envelope, ("format", "schema_version", "payload", "sha256"))
        evidence._text(envelope["format"], "format")
        if envelope["format"] != format:
            raise ValueError("unsupported skill artifact format")
        if format == PROMOTION_FORMAT:
            _promotion_version(envelope["schema_version"])
        else:
            evidence._version(envelope["schema_version"])
        evidence._digest(envelope["sha256"], "sha256")
        record = constructor(envelope["payload"])
        if record.schema_version != envelope["schema_version"]:
            raise ValueError("skill envelope/payload versions differ")
        if envelope["sha256"] != _sha(evidence._json_bytes(envelope["payload"])):
            raise ValueError("skill artifact payload digest mismatch")
        evidence._json_bytes(envelope)
        return record

    return _guard(decode)


def decode_candidate(data: bytes) -> SkillCandidate:
    """Data only, never build environments or execute/score SQL."""
    return _decode(data, CANDIDATE_FORMAT, _candidate_from)


def decode_promotion(data: bytes) -> SkillPromotion:
    """Data only; a decoded receipt is not externally approved by decoding."""
    return _decode(data, PROMOTION_FORMAT, _promotion_from)
