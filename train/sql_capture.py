"""Incremental evidence for trusted, explicitly admitted SQL/PTC execution.

This is not provider-message/token capture, model authorship evidence, training,
or an OS sandbox. Caller IDs and payload hashes are not authentication. Selected
on-disk sources/settings are audit bindings, not in-memory-code attestation.
Database binding requires a stable caller-owned snapshot, not malicious ABA
mutation or filesystem snapshot isolation. No native tools are registered here.

Capture v3 is opt-in reporting-enabled in-process evidence bound to the shared
contract in `train/sql_reporting`; default v1 and isolated v2 records, codecs
and sessions never import reporting or QA modules.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from train.sql_reporting import ReportingConfig, ReportingSnapshot

from bench.score import ExResult
from bench.task import SqlTask
from ptc import sql_isolation as isolation
from train import grpo_ptc, guards, sql_episodes as evidence


__all__ = [
    "SqlCapture", "start_capture", "encode_capture", "decode_capture",
    "rescore_capture", "CaptureError", "CaptureProgramRejected", "CaptureExecutionAborted",
]

MAX_BYTES = evidence.MAX_BYTES
MAX_EXTRACTION_WORK_BYTES = 64 * 1024 * 1024
SCHEMA_VERSION = 1
REPORTING_VERSION = 3
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
_ISOLATED_FIELDS = ("execution_binding", "runtime_receipts", "execution_abort")
_REPORTING_FIELDS = ("reporting", "telemetry")


def _capture_version(value):
    if type(value) is not int or value not in (1, 2, 3):
        raise ValueError("unsupported capture schema version")


def _execution_binding(executor):
    if executor is None:
        return None
    if type(executor) is not isolation.PilotExecutor:
        raise TypeError("concrete PilotExecutor required")
    return isolation.build_execution_binding(executor.profile, source_root=_ROOT)


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
    execution_binding: isolation.ExecutionBinding | None = None
    runtime_receipts: tuple[isolation.RuntimeReceipt, ...] = ()
    execution_abort: isolation.AbortInfo | None = None
    reporting: ReportingConfig | None = None
    telemetry: ReportingSnapshot | None = None

    def __post_init__(self):
        _validate_capture(self)


def _validate_capture(capture):
    if type(capture) is not SqlCapture:
        raise TypeError("capture must be SqlCapture")
    _capture_version(capture.schema_version)
    if type(capture.runtime_receipts) is not tuple:
        raise TypeError("runtime_receipts must be a tuple")
    if capture.schema_version == 1:
        if capture.execution_binding is not None or capture.runtime_receipts or capture.execution_abort is not None:
            raise ValueError("v1 captures require empty isolation defaults")
        if capture.reporting is not None or capture.telemetry is not None:
            raise ValueError("v1 captures cannot carry reporting fields")
    elif capture.schema_version == 3:
        if capture.execution_binding is not None or capture.runtime_receipts or capture.execution_abort is not None:
            raise ValueError("v3 captures omit isolated-only fields")
        from train import sql_reporting
        sql_reporting.validate_config(capture.reporting)
        sql_reporting.validate_snapshot(
            capture.telemetry, capture.reporting, arm="ptc",
        )
    else:
        if capture.reporting is not None or capture.telemetry is not None:
            raise ValueError("v2 captures cannot carry reporting fields")
        isolation.execution_binding_to_dict(capture.execution_binding)
        for receipt in capture.runtime_receipts:
            isolation.runtime_receipt_to_dict(receipt)
        if capture.execution_abort is not None:
            isolation.abort_info_to_dict(capture.execution_abort)
        if (capture.terminal_label == "execution_aborted") != (capture.execution_abort is not None):
            raise ValueError("execution abort requires its typed terminal")
        programs = sum(r.role == "program" for r in capture.runtime_receipts)
        if programs < len(capture.steps):
            raise ValueError("isolated steps require PROGRAM runtime receipts")
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
        if capture.schema_version == 2 and (
            not capture.runtime_receipts or capture.runtime_receipts[-1].role != "scorer"
        ):
            raise ValueError("isolated final requires SCORER runtime receipt")
    elif capture.schema_version == 2 and capture.terminal_label in ("execution_aborted", "program_rejected"):
        if capture.result is not None:
            raise ValueError("isolated abort/rejection must remain unscored")
        if capture.final_answer is None:
            if capture.extracted_sql is not None:
                raise ValueError("extracted SQL requires submitted final")
        elif _bounded_extract_sql(capture.final_answer) != capture.extracted_sql:
            raise ValueError("extracted SQL disagrees with retained final")
        if capture.terminal_label == "program_rejected" and (
            not capture.steps or not capture.runtime_receipts
            or capture.runtime_receipts[-1].role != "program"
            or capture.execution_abort is not None
        ):
            raise ValueError("native rejection requires completed PROGRAM evidence")
    else:
        raise ValueError("unsupported capture terminal label")


def _capture_payload(capture):
    payload = asdict(capture)
    if capture.schema_version == 1:
        for name in _ISOLATED_FIELDS + _REPORTING_FIELDS:
            del payload[name]
    elif capture.schema_version == 2:
        for name in _REPORTING_FIELDS:
            del payload[name]
        payload["execution_binding"] = isolation.execution_binding_to_dict(capture.execution_binding)
        payload["runtime_receipts"] = [
            isolation.runtime_receipt_to_dict(r) for r in capture.runtime_receipts
        ]
        payload["execution_abort"] = (
            None if capture.execution_abort is None
            else isolation.abort_info_to_dict(capture.execution_abort)
        )
    else:
        for name in _ISOLATED_FIELDS:
            del payload[name]
        from train import sql_reporting
        payload["reporting"] = sql_reporting.config_to_dict(capture.reporting)
        payload["telemetry"] = sql_reporting.snapshot_to_dict(capture.telemetry)
    return payload


def encode_capture(capture: SqlCapture) -> bytes:
    """Canonical, bounded UTF-8 JSON. The digest is not authentication."""
    _validate_capture(capture)
    payload = _capture_payload(capture)
    return evidence._json_bytes({
        "format": FORMAT,
        "schema_version": capture.schema_version,
        "payload": payload,
        "sha256": hashlib.sha256(evidence._json_bytes(payload)).hexdigest(),
    })


def _from_payload(payload):
    if type(payload) is not dict:
        raise TypeError("capture payload must be an object")
    version = payload.get("schema_version")
    _capture_version(version)
    names = tuple(
        f.name for f in fields(SqlCapture)
        if (version == 2 or f.name not in _ISOLATED_FIELDS)
        and (version == 3 or f.name not in _REPORTING_FIELDS)
    )
    values = evidence._object(payload, names).copy()
    if version == 3:
        from train import sql_reporting
        values["reporting"] = sql_reporting.config_from_dict(values["reporting"])
        values["telemetry"] = sql_reporting.snapshot_from_dict(values["telemetry"])
    if version == 2:
        values["execution_binding"] = isolation.execution_binding_from_dict(values["execution_binding"])
        if type(values["runtime_receipts"]) is not list:
            raise TypeError("runtime_receipts must be a JSON array")
        values["runtime_receipts"] = tuple(
            isolation.runtime_receipt_from_dict(r) for r in values["runtime_receipts"]
        )
        if values["execution_abort"] is not None:
            values["execution_abort"] = isolation.abort_info_from_dict(values["execution_abort"])
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
    _capture_version(envelope["schema_version"])
    evidence._digest(envelope["sha256"], "sha256")
    capture = _from_payload(envelope["payload"])
    if capture.schema_version != envelope["schema_version"]:
        raise ValueError("capture envelope/payload versions differ")
    expected = hashlib.sha256(evidence._json_bytes(envelope["payload"])).hexdigest()
    if envelope["sha256"] != expected:
        raise ValueError("capture payload digest mismatch")
    evidence._json_bytes(envelope)
    return capture


def _instrument(pair, cap, executor=None, reporting=None):
    # Reuse the existing instrument and its selected-source digest, then bind
    # the additional actual capture/environment/budget owners as well.
    _execution_binding(executor)
    instrument = evidence._instrument(pair, cap)
    if reporting is not None:
        from train import sql_reporting
        paths, digest = sql_reporting.instrument_sources(_ROOT, SOURCE_PATHS)
        return replace(instrument, source_paths=paths, source_sha256=digest)
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


def _bind(capture, task, ids, executor=None, expected_reporting=None):
    encode_capture(capture)
    sql_reporting = None
    if capture.reporting is not None or expected_reporting is not None:
        # The caller's independent expectation, never the artifact's own claim.
        # Reporting is in-process only: refuse before any executor is inspected.
        from train import sql_reporting as reporting_contract
        sql_reporting = reporting_contract
        sql_reporting.require_expected(capture.reporting, expected_reporting)
        if executor is not None:
            raise ValueError("reporting captures cannot bind an isolated executor")
    binding = _execution_binding(executor)
    expected_version = (
        REPORTING_VERSION if capture.reporting is not None
        else SCHEMA_VERSION if executor is None else 2
    )
    if capture.schema_version != expected_version or capture.execution_binding != binding:
        raise ValueError("capture isolation binding/executor differs")
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
    channel = None
    if capture.reporting is not None:
        channel = sql_reporting.make_channel(capture.reporting)
    pair = (evidence.sql_arms.build_sql_arms(task) if channel is None
            else evidence.sql_arms.build_sql_arms(task, qa=channel))
    if _instrument(
        pair, guards.eval_max_turns(), executor, reporting=capture.reporting,
    ) != capture.instrument:
        raise ValueError("current capture sources/runtime/settings differ")
    if (
        pair.schema != capture.schema or pair.backend.name != capture.backend
        or pair.prompt("ptc") != capture.prompt
    ):
        raise ValueError("current schema/backend/prompt differs")
    evidence._check_database(task, capture.db_sha256)


class CaptureError(RuntimeError):
    """Base for new v2 terminal execution evidence only."""

    def __init__(self, capture):
        encode_capture(capture)
        self.capture = capture
        super().__init__(capture.terminal_label)


class CaptureProgramRejected(CaptureError):
    """Native PROGRAM rejection, not infrastructure failure or an EX score."""


class CaptureExecutionAborted(CaptureError):
    """Infrastructure/resource failure retaining frozen, unscored evidence."""


def _receipts(capture, receipt):
    return capture.runtime_receipts + (() if receipt is None else (receipt,))


def _aborted(capture, abort, receipt=None, **retained):
    actual = replace(
        capture, terminal_label="execution_aborted", result=None,
        execution_abort=abort, runtime_receipts=_receipts(capture, receipt), **retained,
    )
    encode_capture(actual)
    return actual


def _program_outcome(executor, code, capture, task):
    try:
        expected = isolation.request_sha256(isolation.ProgramRequest(
            code, capture.instrument.action_max_rows, capture.db_sha256,
        ))
    except (TypeError, ValueError):
        return isolation.ProgramOutcome(None, isolation.AbortInfo("program", "protocol"), None)
    try:
        outcome = executor.run_program(
            code, db_path=task.db_path, db_sha256=capture.db_sha256,
            max_rows=capture.instrument.action_max_rows,
        )
    except Exception:
        return isolation.ProgramOutcome(None, isolation.AbortInfo("program", "transport"), None)
    try:
        isolation.program_outcome_to_dict(outcome)
        if outcome.receipt is not None and outcome.receipt.request_sha256 != expected:
            raise ValueError("PROGRAM receipt request context differs")
    except (TypeError, ValueError):
        return isolation.ProgramOutcome(None, isolation.AbortInfo("program", "protocol"), None)
    return outcome


def _score_outcome(executor, sql, capture, task):
    try:
        instrument = capture.instrument
        expected = isolation.request_sha256(isolation.ScoreRequest(
            replace(task, db_path="/db.sqlite"), sql, instrument.scorer_timeout_s,
            instrument.scorer_max_rows, instrument.compare, capture.db_sha256,
        ))
    except (TypeError, ValueError):
        return isolation.ScoreOutcome(None, isolation.AbortInfo("scorer", "protocol"), None)
    try:
        outcome = executor.score_sql(
            sql, task, db_sha256=capture.db_sha256, instrument=capture.instrument,
        )
    except Exception:
        return isolation.ScoreOutcome(None, isolation.AbortInfo("scorer", "transport"), None)
    try:
        isolation.score_outcome_to_dict(outcome)
        if outcome.receipt is not None and outcome.receipt.request_sha256 != expected:
            raise ValueError("SCORER receipt request context differs")
    except (TypeError, ValueError):
        return isolation.ScoreOutcome(None, isolation.AbortInfo("scorer", "protocol"), None)
    return outcome


class _CaptureSession:
    """Synchronous host session; per-session locking serializes submissions."""

    def __init__(self, task, ids, capture, environment, executor=None,
                 channel=None, reporting=None):
        self._task = task
        self._ids = ids
        self._capture = capture
        self._environment = environment
        self._executor = executor
        self._channel = channel
        self._reporting = reporting
        self._state = "active"
        self._lock = threading.Lock()

    @property
    def prompt(self) -> str:
        return self._capture.prompt

    @property
    def reporting_snapshot(self):
        """Current validated diagnostic telemetry, or None on disabled sessions.

        Read-only even on finished, aborted or invalidated sessions; it never
        performs an action, scorer call or re-seal of the retained capture.
        """
        if self._channel is None:
            return None
        from train import sql_reporting
        return sql_reporting.snapshot_channel(
            self._channel, self._reporting, arm="ptc",
        )

    def _with_telemetry(self, capture):
        if self._channel is None:
            return capture
        from train import sql_reporting
        return replace(
            capture, telemetry=sql_reporting.snapshot_channel(
                self._channel, self._reporting, arm="ptc",
            ),
        )

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
            "capture": _capture_payload(self._capture), name: text,
        })
        if name == "code" and self._executor is not None:
            isolation.ProgramRequest(text, self._capture.instrument.action_max_rows,
                                     self._capture.db_sha256)

    def step(self, code: str) -> str:
        with self._lock:
            self._require_active()
            try:
                self._admit_text(code, "code")
                _bind(
                    self._capture, self._task, self._ids, self._executor,
                    expected_reporting=self._reporting,
                )
                if self._executor is not None:
                    return self._isolated_step(code)
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
                capture = self._with_telemetry(capture)
                encode_capture(capture)
                self._capture = capture
                return observation
            except BaseException:
                self._invalidate()
                raise

    def _isolated_step(self, code):
        actual = self._capture
        if len(actual.steps) == actual.instrument.action_cap:
            observation = guards.TurnBudget(max_turns=actual.instrument.action_cap).exhausted_message()
            actual = replace(actual, refusals=actual.refusals + (
                evidence.ActionObservation(code, observation),
            ))
        else:
            outcome = _program_outcome(self._executor, code, actual, self._task)
            if outcome.abort is not None:
                self._capture = _aborted(actual, outcome.abort, outcome.receipt)
                raise CaptureExecutionAborted(self._capture)
            evidence._check_database(self._task, actual.db_sha256)
            observation = outcome.observation
            actual = replace(
                actual, steps=actual.steps + (evidence.ActionObservation(code, observation),),
                runtime_receipts=_receipts(actual, outcome.receipt),
                terminal_label="program_rejected" if outcome.rejected else actual.terminal_label,
            )
            if outcome.rejected:
                encode_capture(actual)
                self._capture = actual
                raise CaptureProgramRejected(actual)
        encode_capture(actual)
        self._capture = actual
        return observation

    def finish(self, final_answer: str) -> SqlCapture:
        with self._lock:
            self._require_active()
            try:
                self._admit_text(final_answer, "final_answer")
                _bind(
                    self._capture, self._task, self._ids, self._executor,
                    expected_reporting=self._reporting,
                )
                extracted = _bounded_extract_sql(final_answer)
                if self._executor is not None:
                    outcome = _score_outcome(self._executor, extracted, self._capture, self._task)
                    if outcome.abort is not None:
                        actual = _aborted(
                            self._capture, outcome.abort, outcome.receipt,
                            final_answer=final_answer, extracted_sql=extracted,
                        )
                    else:
                        evidence._check_database(self._task, self._capture.db_sha256)
                        actual = replace(
                            self._capture, terminal_label="final_submitted",
                            final_answer=final_answer, extracted_sql=extracted, result=outcome.result,
                            runtime_receipts=_receipts(self._capture, outcome.receipt),
                        )
                    encode_capture(actual)
                    self._capture = actual
                    self._state = actual.terminal_label
                    self._environment = None
                    return actual
                result = evidence._score(
                    extracted, self._task, self._capture.instrument,
                )
                evidence._check_database(self._task, self._capture.db_sha256)
                capture = replace(
                    self._capture, terminal_label="final_submitted",
                    final_answer=final_answer, extracted_sql=extracted, result=result,
                )
                capture = self._with_telemetry(capture)
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
                capture = self._with_telemetry(self._capture)
                encode_capture(capture)
                self._capture = capture
                self._state = "aborted"
                self._environment = None
                return capture
            except BaseException:
                self._invalidate()
                raise


def start_capture(
    task: SqlTask, *, ids: evidence.EpisodeIds, allow_execution=False,
    executor: isolation.PilotExecutor | None = None,
    expected_db_sha256: str | None = None,
    reporting: ReportingConfig | None = None,
) -> _CaptureSession:
    """Admit trusted execution explicitly, then bind a fresh canonical environment."""
    if allow_execution is not True:
        raise ValueError("capture requires allow_execution is True")
    sql_reporting = None
    channel = None
    if reporting is not None:
        # Reporting is in-process only: refuse before the executor is inspected.
        if executor is not None:
            raise ValueError("reporting captures cannot bind an isolated executor")
        from train import sql_reporting as reporting_contract
        sql_reporting = reporting_contract
        sql_reporting.validate_config(reporting)
        channel = sql_reporting.make_channel(reporting)
    if expected_db_sha256 is not None:
        evidence._digest(expected_db_sha256, "expected_db_sha256")
    binding = _execution_binding(executor)
    evidence._validate_ids(ids)
    payload = evidence._task_payload(task)
    evidence._json_bytes({"task": payload, "ids": asdict(ids)})
    if expected_db_sha256 is None:
        db_sha256 = evidence._db_digest(task)
    else:
        db_sha256 = expected_db_sha256
        evidence._check_database(task, db_sha256)
    pair = (evidence.sql_arms.build_sql_arms(task) if channel is None
            else evidence.sql_arms.build_sql_arms(task, qa=channel))
    if executor is None:
        prompt, environment = (
            grpo_ptc.sql_environment(task) if channel is None
            else grpo_ptc.sql_environment(task, qa=channel)
        )
    else:
        prompt, environment = pair.prompt("ptc"), None
    cap = guards.eval_max_turns()
    instrument = _instrument(pair, cap, executor, reporting=reporting)
    if prompt != pair.prompt("ptc") or (environment is not None and environment.max_turns != cap):
        raise ValueError("canonical execution environment differs from capture binding")
    evidence._check_database(task, db_sha256)
    telemetry = (None if channel is None else sql_reporting.snapshot_channel(
        channel, reporting, arm="ptc"))
    capture = SqlCapture(
        schema_version=(
            SCHEMA_VERSION if executor is None and channel is None
            else REPORTING_VERSION if channel is not None else 2
        ),
        origin="incremental_execution",
        ids=replace(ids), arm="ptc", task_id=task.name,
        task_fingerprint=evidence._fingerprint(payload), db_sha256=db_sha256,
        schema=pair.schema, prompt=prompt, backend=pair.backend.name,
        instrument=instrument, steps=(), refusals=(), final_answer=None,
        extracted_sql=None, terminal_label="aborted", result=None,
        execution_binding=binding,
        reporting=reporting, telemetry=telemetry,
    )
    encode_capture(capture)
    if expected_db_sha256 is not None:
        if capture.db_sha256 != expected_db_sha256:
            raise ValueError("constructed capture differs from expected database snapshot")
        evidence._check_database(task, expected_db_sha256)
    return _CaptureSession(
        task, ids, capture, environment, executor,
        channel=channel, reporting=reporting,
    )


def rescore_capture(
    capture: SqlCapture, task: SqlTask, *, ids: evidence.EpisodeIds,
    executor: isolation.PilotExecutor | None = None,
    expected_reporting: ReportingConfig | None = None,
) -> ExResult:
    """Recheck external bindings, then score final/gold SQL, never recorded actions."""
    _validate_capture(capture)
    if capture.terminal_label != "final_submitted":
        raise ValueError("aborted capture has no submitted final to rescore")
    _bind(capture, task, ids, executor, expected_reporting)
    if executor is not None:
        outcome = _score_outcome(executor, capture.extracted_sql, capture, task)
        if outcome.abort is not None:
            raise CaptureExecutionAborted(_aborted(capture, outcome.abort, outcome.receipt))
        evidence._check_database(task, capture.db_sha256)
        return outcome.result
    result = evidence._score(capture.extracted_sql, task, capture.instrument)
    evidence._check_database(task, capture.db_sha256)
    return result
