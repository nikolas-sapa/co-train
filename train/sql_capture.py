"""Incremental evidence for trusted, explicitly admitted SQL/PTC execution.

This is not provider-message/token capture, model authorship evidence, training,
or an OS sandbox. Caller IDs and payload hashes are not authentication. Selected
on-disk sources/settings are audit bindings, not in-memory-code attestation.
Database binding requires a stable caller-owned snapshot, not malicious ABA
mutation or filesystem snapshot isolation. No native tools are registered here.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from bench.score import ExResult
from bench.task import SqlTask
from train import grpo_ptc, guards, sql_episodes as evidence


__all__ = [
    "SqlCapture", "start_capture", "encode_capture", "decode_capture",
    "rescore_capture",
]

MAX_BYTES = evidence.MAX_BYTES
MAX_EXTRACTION_WORK_BYTES = 64 * 1024 * 1024
SCHEMA_VERSION = 1
FORMAT = "sql_execution_capture"
_EXTRA_SOURCES = (
    "train/sql_capture.py",
    "train/sql_episodes.py",
    "train/grpo_ptc.py",
    "train/guards.py",
    "bench/task.py",
)
SOURCE_PATHS = evidence.SOURCE_PATHS + _EXTRA_SOURCES
_ROOT = Path(__file__).resolve().parents[1]


def _bounded_extract_sql(text):
    """Bound raw UTF-8 prefix work before invoking the unchanged SQL extractor.

    This conservative per-invocation proxy counts even discarded prose/fences
    and semicolons in quotes/comments or after an early complete statement.
    It is not a whole-operation CPU/memory deadline.
    """
    evidence._text(text, "final_answer")
    encoded = text.encode("utf-8")
    work = len(encoded)
    start = 0
    while work <= MAX_EXTRACTION_WORK_BYTES:
        position = encoded.find(b";", start)
        if position < 0:
            return evidence.extract_sql(text)
        work += position + 1
        start = position + 1
    raise ValueError("SQL extraction work exceeds 64 MiB per invocation")


@dataclass(frozen=True)
class SqlCapture:
    schema_version: int
    origin: str
    ids: evidence.EpisodeIds
    arm: str
    task_id: str
    task_fingerprint: str
    db_sha256: str
    schema: str
    prompt: str
    backend: str
    instrument: evidence.InstrumentSettings
    steps: tuple[evidence.ActionObservation, ...]
    refusals: tuple[evidence.ActionObservation, ...]
    final_answer: str | None
    extracted_sql: str | None
    terminal_label: str
    result: ExResult | None

    def __post_init__(self):
        _validate_capture(self)


def _validate_capture(capture):
    if type(capture) is not SqlCapture:
        raise TypeError("capture must be SqlCapture")
    evidence._version(capture.schema_version)
    for name, expected in (("origin", "incremental_execution"), ("arm", "ptc")):
        evidence._text(getattr(capture, name), name)
        if getattr(capture, name) != expected:
            raise ValueError(f"unsupported capture {name}")
    evidence._validate_ids(capture.ids)
    evidence._text(capture.task_id, "task_id", nonempty=True)
    for name in ("task_fingerprint", "db_sha256"):
        evidence._digest(getattr(capture, name), name)
    for name in ("schema", "prompt"):
        evidence._text(getattr(capture, name), name)
    evidence._text(capture.backend, "backend", nonempty=True)
    evidence._validate_instrument(capture.instrument)
    for name in ("steps", "refusals"):
        sequence = getattr(capture, name)
        if type(sequence) is not tuple:
            raise TypeError(f"{name} must be a tuple")
        for step in sequence:
            evidence._validate_step(step)
    cap = capture.instrument.action_cap
    if len(capture.steps) > cap:
        raise ValueError("executed submissions exceed the recorded action cap")
    if capture.refusals:
        if len(capture.steps) != cap:
            raise ValueError("budget refusals require an exhausted execution budget")
        refusal = guards.TurnBudget(max_turns=cap).exhausted_message()
        if any(step.observation != refusal for step in capture.refusals):
            raise ValueError("recorded refusal differs from the budget refusal")
    evidence._text(capture.terminal_label, "terminal_label")
    if capture.terminal_label == "aborted":
        if any(value is not None for value in (
            capture.final_answer, capture.extracted_sql, capture.result,
        )):
            raise ValueError("aborted captures cannot carry a final answer or score")
    elif capture.terminal_label == "final_submitted":
        evidence._text(capture.final_answer, "final_answer")
        evidence._text(capture.extracted_sql, "extracted_sql")
        if _bounded_extract_sql(capture.final_answer) != capture.extracted_sql:
            raise ValueError("extracted SQL disagrees with the submitted final")
        evidence._validate_result(capture.result)
    else:
        raise ValueError("unsupported capture terminal label")


def encode_capture(capture: SqlCapture) -> bytes:
    """Canonical, bounded UTF-8 JSON. The digest is not authentication."""
    _validate_capture(capture)
    payload = asdict(capture)
    return evidence._json_bytes({
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "payload": payload,
        "sha256": hashlib.sha256(evidence._json_bytes(payload)).hexdigest(),
    })


def _from_payload(payload):
    values = evidence._record_object(payload, SqlCapture).copy()
    values["ids"] = evidence.EpisodeIds(
        **evidence._record_object(values["ids"], evidence.EpisodeIds),
    )
    instrument = evidence._record_object(
        values["instrument"], evidence.InstrumentSettings,
    ).copy()
    if type(instrument["source_paths"]) is not list:
        raise TypeError("source_paths must be a JSON array")
    instrument["source_paths"] = tuple(instrument["source_paths"])
    values["instrument"] = evidence.InstrumentSettings(**instrument)
    for name in ("steps", "refusals"):
        if type(values[name]) is not list:
            raise TypeError(f"{name} must be a JSON array")
        values[name] = tuple(
            evidence.ActionObservation(
                **evidence._record_object(step, evidence.ActionObservation),
            )
            for step in values[name]
        )
    if values["result"] is not None:
        values["result"] = ExResult(
            **evidence._record_object(values["result"], ExResult),
        )
    return SqlCapture(**values)


def decode_capture(data: bytes) -> SqlCapture:
    """Decode data only: no environment creation, scorer call or action execution."""
    if type(data) is not bytes:
        raise TypeError("encoded capture must be bytes")
    if len(data) > MAX_BYTES:
        raise ValueError("capture exceeds 8 MiB")
    try:
        envelope = json.loads(
            data.decode("utf-8"), object_pairs_hook=evidence._unique_object,
            parse_constant=evidence._reject_constant,
        )
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid UTF-8 JSON capture") from exc
    evidence._object(envelope, ("format", "schema_version", "payload", "sha256"))
    evidence._text(envelope["format"], "format")
    if envelope["format"] != FORMAT:
        raise ValueError("unsupported capture format")
    evidence._version(envelope["schema_version"])
    evidence._digest(envelope["sha256"], "sha256")
    capture = _from_payload(envelope["payload"])
    expected = hashlib.sha256(evidence._json_bytes(envelope["payload"])).hexdigest()
    if envelope["sha256"] != expected:
        raise ValueError("capture payload digest mismatch")
    evidence._json_bytes(envelope)
    return capture


def _instrument(pair, cap):
    # Reuse the existing instrument and its selected-source digest, then bind
    # the additional actual capture/environment/budget owners as well.
    instrument = evidence._instrument(pair, cap)
    try:
        extra = tuple(
            (name, hashlib.sha256((_ROOT / name).read_bytes()).hexdigest())
            for name in _EXTRA_SOURCES
        )
    except OSError as exc:
        raise ValueError("cannot read selected capture sources") from exc
    digest = hashlib.sha256(evidence._json_bytes(
        (instrument.source_sha256, extra),
    )).hexdigest()
    return replace(instrument, source_paths=SOURCE_PATHS, source_sha256=digest)


def _bind(capture, task, ids):
    encode_capture(capture)
    evidence._validate_ids(ids)
    payload = evidence._task_payload(task)
    if capture.ids != ids:
        raise ValueError("caller IDs do not match capture IDs")
    if (
        capture.task_id != task.name
        or capture.task_fingerprint != evidence._fingerprint(payload)
    ):
        raise ValueError("current task does not match the captured task")
    evidence._check_database(task, capture.db_sha256)
    pair = evidence.sql_arms.build_sql_arms(task)
    if _instrument(pair, guards.eval_max_turns()) != capture.instrument:
        raise ValueError("current capture sources/runtime/settings differ")
    if (
        pair.schema != capture.schema or pair.backend.name != capture.backend
        or pair.prompt("ptc") != capture.prompt
    ):
        raise ValueError("current schema/backend/prompt differs")
    evidence._check_database(task, capture.db_sha256)


class _CaptureSession:
    """Synchronous host session; per-session locking serializes submissions."""

    def __init__(self, task, ids, capture, environment):
        self._task = task
        self._ids = ids
        self._capture = capture
        self._environment = environment
        self._state = "active"
        self._lock = threading.Lock()

    @property
    def prompt(self) -> str:
        return self._capture.prompt

    def _require_active(self):
        if self._state != "active":
            raise RuntimeError(f"capture session is {self._state}")

    def _invalidate(self):
        self._state = "invalidated"
        self._environment = None

    def _admit_text(self, text, name):
        evidence._text(text, name)
        # Bound known input plus accumulated evidence before execution/scoring.
        # Unknown observation/result size is checked again before sealing.
        evidence._json_bytes({
            "capture": asdict(self._capture), name: text,
        })

    def step(self, code: str) -> str:
        with self._lock:
            self._require_active()
            try:
                self._admit_text(code, "code")
                _bind(self._capture, self._task, self._ids)
                environment = self._environment
                cap = self._capture.instrument.action_cap
                if (
                    environment.max_turns != cap
                    or environment.budget.max_turns != cap
                    or environment.turns_used != len(self._capture.steps)
                ):
                    raise ValueError("session execution budget differs from evidence")
                executed = environment.turns_used < cap
                observation = environment.step(code)
                evidence._check_database(self._task, self._capture.db_sha256)
                step = evidence.ActionObservation(code, observation)
                name = "steps" if executed else "refusals"
                capture = replace(self._capture, **{
                    name: getattr(self._capture, name) + (step,),
                })
                encode_capture(capture)
                self._capture = capture
                return observation
            except BaseException:
                self._invalidate()
                raise

    def finish(self, final_answer: str) -> SqlCapture:
        with self._lock:
            self._require_active()
            try:
                self._admit_text(final_answer, "final_answer")
                _bind(self._capture, self._task, self._ids)
                extracted = _bounded_extract_sql(final_answer)
                result = evidence._score(
                    extracted, self._task, self._capture.instrument,
                )
                evidence._check_database(self._task, self._capture.db_sha256)
                capture = replace(
                    self._capture, terminal_label="final_submitted",
                    final_answer=final_answer, extracted_sql=extracted, result=result,
                )
                encode_capture(capture)
                self._capture = capture
                self._state = "final_submitted"
                self._environment = None
                return capture
            except BaseException:
                self._invalidate()
                raise

    def abort(self) -> SqlCapture:
        with self._lock:
            self._require_active()
            try:
                encode_capture(self._capture)
                self._state = "aborted"
                self._environment = None
                return self._capture
            except BaseException:
                self._invalidate()
                raise


def start_capture(
    task: SqlTask, *, ids: evidence.EpisodeIds, allow_execution=False,
) -> _CaptureSession:
    """Admit trusted execution explicitly, then bind a fresh canonical environment."""
    if allow_execution is not True:
        raise ValueError("capture requires allow_execution is True")
    evidence._validate_ids(ids)
    payload = evidence._task_payload(task)
    evidence._json_bytes({"task": payload, "ids": asdict(ids)})
    db_sha256 = evidence._db_digest(task)
    pair = evidence.sql_arms.build_sql_arms(task)
    prompt, environment = grpo_ptc.sql_environment(task)
    cap = guards.eval_max_turns()
    instrument = _instrument(pair, cap)
    if prompt != pair.prompt("ptc") or environment.max_turns != cap:
        raise ValueError("canonical execution environment differs from capture binding")
    evidence._check_database(task, db_sha256)
    capture = SqlCapture(
        schema_version=SCHEMA_VERSION, origin="incremental_execution",
        ids=replace(ids), arm="ptc", task_id=task.name,
        task_fingerprint=evidence._fingerprint(payload), db_sha256=db_sha256,
        schema=pair.schema, prompt=prompt, backend=pair.backend.name,
        instrument=instrument, steps=(), refusals=(), final_answer=None,
        extracted_sql=None, terminal_label="aborted", result=None,
    )
    encode_capture(capture)
    return _CaptureSession(task, ids, capture, environment)


def rescore_capture(
    capture: SqlCapture, task: SqlTask, *, ids: evidence.EpisodeIds,
) -> ExResult:
    """Recheck external bindings, then score final/gold SQL, never recorded actions."""
    _validate_capture(capture)
    if capture.terminal_label != "final_submitted":
        raise ValueError("aborted capture has no submitted final to rescore")
    _bind(capture, task, ids)
    result = evidence._score(capture.extracted_sql, task, capture.instrument)
    evidence._check_database(task, capture.db_sha256)
    return result
