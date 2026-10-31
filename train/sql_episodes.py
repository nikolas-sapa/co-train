"""Immutable, task-bound evidence for trusted scripted SQL episodes.

This is an offline recorder, not a generator or a production model-request
capture. Caller provenance and payload SHA-256 are not authentication. Selected
on-disk sources/runtime settings are audit bindings, not an SBOM or attestation
of in-memory code. No token, training or real-policy reproduction claim is made.

Re-execution runs the existing real bash/PTC channels. Its literal-True opt-in
prevents accidents; it is NOT a shell sandbox. Only replay trusted scripts.
Database checks require a stable caller-owned snapshot and do not defend against
malicious concurrent ABA writes or provide filesystem snapshot isolation.

Episode v2 is opt-in reporting-enabled scripted evidence bound to the shared
contract in `train/sql_reporting`; the default v1 record, codec and replay paths
never import reporting or QA modules.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import platform
import re
import sqlite3
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from train.sql_reporting import ReportingConfig, ReportingSnapshot

from bench.score import ExResult, INVALID_STATUSES, execution_accuracy, extract_sql
from bench.task import SqlTask
from ptc import sql_arms
from train import guards


__all__ = [
    "EpisodeIds", "InstrumentSettings", "ActionObservation", "SqlEpisode",
    "ReexecutionResult", "record_scripted", "encode_episode", "decode_episode",
    "rescore_sql", "reexecute_sql",
]

MAX_BYTES = 8 * 1024 * 1024
SCHEMA_VERSION = 1
REPORTING_VERSION = 2
_REPORTING_FIELDS = ("reporting", "telemetry")
SOURCE_PATHS = (
    "bench/score.py",
    "ptc/sql_arms.py",
    "ptc/runtime.py",
    "ptc/sql_runtime.py",
    "ptc/sqlite_safety.py",
    "ptc/harness.py",
)
_ROOT = Path(__file__).resolve().parents[1]
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCORER_DEFAULTS = {
    name: parameter.default
    for name, parameter in inspect.signature(execution_accuracy).parameters.items()
    if name in ("timeout_s", "max_rows", "compare")
}
_STATUSES = INVALID_STATUSES | {
    "match", "mismatch", "pred_error", "pred_timeout", "pred_truncated", "pred_empty",
}


def _text(value, name, *, nonempty=False):
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if nonempty and not value.strip():
        raise ValueError(f"{name} must be nonempty")
    if len(value.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"{name} exceeds the evidence size limit")


def _integer(value, name, *, minimum=0):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, not a boolean")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def _number(value, name, *, positive=False):
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be numeric, not a boolean")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (positive and value <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))


def _digest(value, name):
    _text(value, name)
    if _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _version(value):
    _integer(value, "schema_version", minimum=1)
    if value not in (SCHEMA_VERSION, REPORTING_VERSION):
        raise ValueError("unsupported episode schema version")


def _arm(value):
    _text(value, "arm")
    if value not in ("ptc", "bash"):
        raise ValueError("arm must be ptc or bash")


def _json_bytes(value):
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, OverflowError) as exc:
        raise ValueError("invalid or excessively nested JSON evidence") from exc
    if len(encoded) > MAX_BYTES:
        raise ValueError("evidence exceeds 8 MiB")
    return encoded


@dataclass(frozen=True)
class EpisodeIds:
    """Caller declarations, never authenticated identities."""

    corpus_id: str
    split_id: str
    run_id: str
    episode_id: str
    policy_id: str
    policy_revision: str

    def __post_init__(self):
        _validate_ids(self)


def _validate_ids(ids):
    if type(ids) is not EpisodeIds:
        raise TypeError("ids must be EpisodeIds")
    for field in fields(ids):
        _text(getattr(ids, field.name), field.name, nonempty=True)


@dataclass(frozen=True)
class InstrumentSettings:
    action_cap: int
    action_max_rows: int
    scorer_max_rows: int
    compare: str
    scorer_timeout_s: float
    program_timeout_s: float
    wrapper_timeout_s: float
    python_version: str
    sqlite_version: str
    source_paths: tuple[str, ...]
    source_sha256: str

    def __post_init__(self):
        _validate_instrument(self)


def _validate_instrument(instrument):
    if type(instrument) is not InstrumentSettings:
        raise TypeError("instrument must be InstrumentSettings")
    for name in ("action_cap", "action_max_rows", "scorer_max_rows"):
        _integer(getattr(instrument, name), name, minimum=1)
    _text(instrument.compare, "compare")
    if instrument.compare not in ("set", "multiset"):
        raise ValueError("unsupported scorer comparison")
    for name in ("scorer_timeout_s", "program_timeout_s", "wrapper_timeout_s"):
        _number(getattr(instrument, name), name, positive=True)
    for name in ("python_version", "sqlite_version"):
        _text(getattr(instrument, name), name, nonempty=True)
    if type(instrument.source_paths) is not tuple:
        raise TypeError("source_paths must be a tuple")
    for path in instrument.source_paths:
        _text(path, "source path", nonempty=True)
    if len(set(instrument.source_paths)) != len(instrument.source_paths):
        raise ValueError("duplicate instrument source paths")
    _digest(instrument.source_sha256, "source_sha256")


@dataclass(frozen=True)
class ActionObservation:
    action: str
    observation: str

    def __post_init__(self):
        _validate_step(self)


def _validate_step(step):
    if type(step) is not ActionObservation:
        raise TypeError("steps must contain ActionObservation records")
    _text(step.action, "action")
    _text(step.observation, "observation")


def _validate_result(result):
    if type(result) is not ExResult:
        raise TypeError("result must be the existing ExResult")
    _number(result.score, "score")
    if result.score not in (0, 1):
        raise ValueError("EX scores must be binary")
    _text(result.status, "status", nonempty=True)
    if result.status not in _STATUSES:
        raise ValueError("unknown EX status")
    if type(result.valid) is not bool:
        raise TypeError("valid must be a boolean")
    if result.valid != (result.status not in INVALID_STATUSES):
        raise ValueError("EX validity disagrees with its status")
    _text(result.detail, "detail")
    _integer(result.n_pred_rows, "n_pred_rows")
    _integer(result.n_gold_rows, "n_gold_rows")


@dataclass(frozen=True)
class SqlEpisode:
    schema_version: int
    origin: str
    ids: EpisodeIds
    arm: str
    task_id: str
    task_fingerprint: str
    db_sha256: str
    schema: str
    prompt: str
    backend: str
    instrument: InstrumentSettings
    steps: tuple[ActionObservation, ...]
    final_answer: str
    extracted_sql: str
    terminal_label: str
    result: ExResult
    reporting: ReportingConfig | None = None
    telemetry: ReportingSnapshot | None = None

    def __post_init__(self):
        _validate_episode(self)


def _validate_episode(episode):
    if type(episode) is not SqlEpisode:
        raise TypeError("episode must be SqlEpisode")
    _version(episode.schema_version)
    if type(episode.origin) is not str or episode.origin != "scripted":
        raise ValueError("only scripted episode evidence is supported")
    _validate_ids(episode.ids)
    _arm(episode.arm)
    _text(episode.task_id, "task_id", nonempty=True)
    _digest(episode.task_fingerprint, "task_fingerprint")
    _digest(episode.db_sha256, "db_sha256")
    for name in ("schema", "prompt", "final_answer", "extracted_sql"):
        _text(getattr(episode, name), name)
    _text(episode.backend, "backend", nonempty=True)
    _validate_instrument(episode.instrument)
    if type(episode.steps) is not tuple:
        raise TypeError("steps must be a tuple")
    if len(episode.steps) > episode.instrument.action_cap:
        raise ValueError("recorded actions exceed the recorded action cap")
    for step in episode.steps:
        _validate_step(step)
    if type(episode.terminal_label) is not str or episode.terminal_label != "scripted_final":
        raise ValueError("unsupported scripted terminal label")
    _validate_result(episode.result)
    if episode.schema_version == SCHEMA_VERSION:
        if episode.reporting is not None or episode.telemetry is not None:
            raise ValueError("legacy episodes cannot carry reporting fields")
    else:
        if episode.reporting is None or episode.telemetry is None:
            raise ValueError("reported episodes require reporting and telemetry")
        from train import sql_reporting
        sql_reporting.validate_config(episode.reporting)
        sql_reporting.validate_snapshot(
            episode.telemetry, episode.reporting, arm=episode.arm,
        )


@dataclass(frozen=True)
class ReexecutionResult:
    observations: tuple[str, ...]
    result: ExResult
    observations_match: bool
    score_matches: bool
    telemetry: ReportingSnapshot | None = None
    telemetry_matches: bool | None = None

    def __post_init__(self):
        if type(self.observations) is not tuple:
            raise TypeError("observations must be a tuple")
        for observation in self.observations:
            _text(observation, "observation")
        _validate_result(self.result)
        if type(self.observations_match) is not bool or type(self.score_matches) is not bool:
            raise TypeError("match flags must be booleans")
        if self.telemetry is None:
            if self.telemetry_matches is not None:
                raise ValueError("a telemetry match flag requires a snapshot")
        else:
            from train import sql_reporting
            if type(self.telemetry) is not sql_reporting.ReportingSnapshot:
                raise TypeError("telemetry must be a ReportingSnapshot")
            if type(self.telemetry_matches) is not bool:
                raise TypeError("telemetry_matches must be a boolean")


def _episode_payload(episode):
    payload = asdict(episode)
    if episode.schema_version == SCHEMA_VERSION:
        for name in _REPORTING_FIELDS:
            del payload[name]
    else:
        from train import sql_reporting
        payload["reporting"] = sql_reporting.config_to_dict(episode.reporting)
        payload["telemetry"] = sql_reporting.snapshot_to_dict(episode.telemetry)
    return payload


def encode_episode(episode: SqlEpisode) -> bytes:
    """Canonical UTF-8 JSON, with a corruption digest of the canonical payload."""
    _validate_episode(episode)
    payload = _episode_payload(episode)
    digest = hashlib.sha256(_json_bytes(payload)).hexdigest()
    return _json_bytes({
        "schema_version": episode.schema_version, "payload": payload, "sha256": digest,
    })


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def _object(value, expected):
    if type(value) is not dict:
        raise TypeError("expected a JSON object")
    if set(value) != set(expected):
        raise ValueError("missing or unknown evidence keys")
    return value


def _record_object(value, cls):
    return _object(value, (field.name for field in fields(cls)))


def _from_payload(payload):
    if type(payload) is not dict:
        raise TypeError("episode payload must be an object")
    version = payload.get("schema_version")
    _version(version)
    names = tuple(
        field.name for field in fields(SqlEpisode)
        if version == REPORTING_VERSION or field.name not in _REPORTING_FIELDS
    )
    values = _object(payload, names).copy()
    if version == REPORTING_VERSION:
        from train import sql_reporting
        values["reporting"] = sql_reporting.config_from_dict(values["reporting"])
        values["telemetry"] = sql_reporting.snapshot_from_dict(values["telemetry"])
    values["ids"] = EpisodeIds(**_record_object(values["ids"], EpisodeIds))
    instrument = _record_object(values["instrument"], InstrumentSettings).copy()
    if type(instrument["source_paths"]) is not list:
        raise TypeError("source_paths must be a JSON array")
    instrument["source_paths"] = tuple(instrument["source_paths"])
    values["instrument"] = InstrumentSettings(**instrument)
    if type(values["steps"]) is not list:
        raise TypeError("steps must be a JSON array")
    values["steps"] = tuple(
        ActionObservation(**_record_object(step, ActionObservation))
        for step in values["steps"]
    )
    values["result"] = ExResult(**_record_object(values["result"], ExResult))
    return SqlEpisode(**values)


def decode_episode(data: bytes) -> SqlEpisode:
    """Decode data only. Never build an arm, score SQL or execute an action."""
    if type(data) is not bytes:
        raise TypeError("encoded evidence must be bytes")
    if len(data) > MAX_BYTES:
        raise ValueError("evidence exceeds 8 MiB")
    try:
        envelope = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid UTF-8 JSON evidence") from exc
    _object(envelope, ("schema_version", "payload", "sha256"))
    _version(envelope["schema_version"])
    _digest(envelope["sha256"], "sha256")
    episode = _from_payload(envelope["payload"])
    if episode.schema_version != envelope["schema_version"]:
        raise ValueError("episode envelope/payload versions differ")
    expected = hashlib.sha256(_json_bytes(envelope["payload"])).hexdigest()
    if envelope["sha256"] != expected:
        raise ValueError("episode payload digest mismatch")
    # Also bound the canonical envelope, not just a possibly shorter input.
    _json_bytes(envelope)
    return episode


def _task_payload(task):
    if type(task) is not SqlTask:
        raise TypeError("task must be SqlTask")
    for field in fields(task):
        _text(getattr(task, field.name), f"task.{field.name}")
    _text(task.name, "task.name", nonempty=True)
    _text(task.db_path, "task.db_path", nonempty=True)
    return {
        field.name: getattr(task, field.name)
        for field in fields(task) if field.name != "db_path"
    }


def _fingerprint(task_payload):
    return hashlib.sha256(_json_bytes(task_payload)).hexdigest()


def _without_sidecars(path):
    # Check both the caller's mount and the resolved file, including dangling
    # sidecar symlinks. A main-file-only hash is not a WAL snapshot.
    paths = {path, path.resolve()}
    for base in paths:
        for suffix in ("-wal", "-journal", "-shm"):
            sidecar = Path(str(base) + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                raise ValueError(f"database snapshot has a sidecar: {sidecar.name}")


def _db_digest(task):
    path = Path(task.db_path)
    _without_sidecars(path)
    try:
        if not path.is_file():
            raise ValueError("database snapshot is missing")
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ValueError("database snapshot changed while opening")
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
    except OSError as exc:
        raise ValueError("cannot read a stable database snapshot") from exc
    signature = lambda stat: (
        stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
    )
    if signature(before) != signature(after):
        raise ValueError("database snapshot changed while hashing")
    _without_sidecars(path)
    return digest.hexdigest()


def _check_database(task, expected):
    if _db_digest(task) != expected:
        raise ValueError("database content differs from the bound snapshot")


def _source_digest():
    try:
        sources = tuple(
            (name, hashlib.sha256((_ROOT / name).read_bytes()).hexdigest())
            for name in SOURCE_PATHS
        )
    except OSError as exc:
        raise ValueError("cannot read selected instrument sources") from exc
    return hashlib.sha256(_json_bytes(sources)).hexdigest()


def _instrument(pair, cap):
    return InstrumentSettings(
        action_cap=cap,
        action_max_rows=pair.max_rows,
        scorer_max_rows=_SCORER_DEFAULTS["max_rows"],
        compare=_SCORER_DEFAULTS["compare"],
        scorer_timeout_s=_SCORER_DEFAULTS["timeout_s"],
        program_timeout_s=pair.budget.program_timeout,
        wrapper_timeout_s=sql_arms.WRAPPER_TIMEOUT,
        python_version=platform.python_version(),
        sqlite_version=sqlite3.sqlite_version,
        source_paths=SOURCE_PATHS,
        source_sha256=_source_digest(),
    )


def _reporting_instrument(pair, cap):
    """The instrument bound to expanded reporting sources; opt-in paths only."""
    from train import sql_reporting
    instrument = _instrument(pair, cap)
    paths, digest = sql_reporting.instrument_sources(
        _ROOT, SOURCE_PATHS + ("train/sql_episodes.py",),
    )
    return replace(instrument, source_paths=paths, source_sha256=digest)


def _admit_actions(actions, cap):
    if isinstance(actions, (str, bytes, bytearray)) or not isinstance(actions, Sequence):
        raise TypeError("actions must be a complete sequence of strings")
    if len(actions) > cap:
        raise ValueError("script exceeds the existing action cap")
    admitted = tuple(actions)
    if len(admitted) > cap:
        raise ValueError("script exceeds the existing action cap")
    for action in admitted:
        _text(action, "action")
    return admitted


def _run_actions(pair, arm, actions):
    if arm == "bash":
        with tempfile.TemporaryDirectory(prefix="cotrain-sql-episode-") as bindir:
            return tuple(pair.run(arm, action, bindir=bindir) for action in actions)
    return tuple(pair.run(arm, action) for action in actions)


def _score(extracted_sql, task, instrument):
    result = execution_accuracy(
        extracted_sql, task,
        timeout_s=instrument.scorer_timeout_s,
        max_rows=instrument.scorer_max_rows,
        compare=instrument.compare,
    )
    _validate_result(result)
    return result


def record_scripted(
    task: SqlTask, *, arm: str, actions: Sequence[str], final_answer: str,
    ids: EpisodeIds, reporting: ReportingConfig | None = None,
) -> SqlEpisode:
    """Admit the entire script before building arms; FINAL is not an action."""
    _arm(arm)
    _validate_ids(ids)
    _text(final_answer, "final_answer")
    task_payload = _task_payload(task)
    cap = guards.eval_max_turns()
    _integer(cap, "action cap", minimum=1)
    admitted = _admit_actions(actions, cap)
    # Bound known inputs before executing anything. Observations are additionally
    # bounded when constructing/encoding the completed immutable record.
    _json_bytes({
        "task": task_payload, "ids": asdict(ids),
        "actions": admitted, "final_answer": final_answer,
    })
    sql_reporting = None
    channel = None
    if reporting is not None:
        from train import sql_reporting as reporting_contract
        sql_reporting = reporting_contract
        sql_reporting.validate_config(reporting)
        channel = sql_reporting.make_channel(reporting)
    db_sha256 = _db_digest(task)
    pair = (sql_arms.build_sql_arms(task) if channel is None
            else sql_arms.build_sql_arms(task, qa=channel))
    instrument = (_instrument(pair, cap) if channel is None
                  else _reporting_instrument(pair, cap))
    extracted = extract_sql(final_answer)
    _check_database(task, db_sha256)
    observations = _run_actions(pair, arm, admitted)
    _check_database(task, db_sha256)
    result = _score(extracted, task, instrument)
    _check_database(task, db_sha256)
    telemetry = (None if channel is None else sql_reporting.snapshot_channel(
        channel, reporting, arm=arm))
    episode = SqlEpisode(
        schema_version=SCHEMA_VERSION if channel is None else REPORTING_VERSION,
        origin="scripted", ids=ids, arm=arm,
        task_id=task.name, task_fingerprint=_fingerprint(task_payload),
        db_sha256=db_sha256, schema=pair.schema, prompt=pair.prompt(arm),
        backend=pair.backend.name, instrument=instrument,
        steps=tuple(
            ActionObservation(action, observation)
            for action, observation in zip(admitted, observations)
        ),
        final_answer=final_answer, extracted_sql=extracted,
        terminal_label="scripted_final", result=result,
        reporting=reporting, telemetry=telemetry,
    )
    encode_episode(episode)
    return episode


def _bind(episode, task, ids, expected_reporting=None):
    # Validate even manually constructed records, without relying on an envelope
    # or treating a recomputed self-digest as external evidence.
    encode_episode(episode)
    _validate_ids(ids)
    sql_reporting = None
    if episode.reporting is not None or expected_reporting is not None:
        # The caller's independent expectation, never the artifact's own claim.
        from train import sql_reporting as reporting_contract
        sql_reporting = reporting_contract
        sql_reporting.require_expected(episode.reporting, expected_reporting)
    task_payload = _task_payload(task)
    if episode.ids != ids:
        raise ValueError("caller IDs do not match episode IDs")
    if episode.task_id != task.name or episode.task_fingerprint != _fingerprint(task_payload):
        raise ValueError("current task does not match the recorded task")
    _check_database(task, episode.db_sha256)
    channel = None
    if episode.reporting is not None:
        channel = sql_reporting.make_channel(episode.reporting)
    pair = (sql_arms.build_sql_arms(task) if channel is None
            else sql_arms.build_sql_arms(task, qa=channel))
    cap = guards.eval_max_turns()
    current = (_instrument(pair, cap) if channel is None
               else _reporting_instrument(pair, cap))
    if current != episode.instrument:
        raise ValueError("current instrument sources/runtime/settings differ")
    if (
        pair.backend.name != episode.backend or pair.schema != episode.schema
        or pair.prompt(episode.arm) != episode.prompt
    ):
        raise ValueError("current schema/backend/prompt differs")
    if extract_sql(episode.final_answer) != episode.extracted_sql:
        raise ValueError("recorded extracted SQL disagrees with final answer")
    _check_database(task, episode.db_sha256)
    return pair, channel


def rescore_sql(
    episode: SqlEpisode, task: SqlTask, *, ids: EpisodeIds,
    expected_reporting: ReportingConfig | None = None,
) -> ExResult:
    """Run protected final/gold SQL only, never any recorded backend action."""
    _bind(episode, task, ids, expected_reporting)
    result = _score(episode.extracted_sql, task, episode.instrument)
    _check_database(task, episode.db_sha256)
    return result


def reexecute_sql(
    episode: SqlEpisode, task: SqlTask, *, ids: EpisodeIds,
    allow_execution=False, expected_reporting: ReportingConfig | None = None,
) -> ReexecutionResult:
    """Replay trusted actions once through a fresh arm, without normalization."""
    if allow_execution is not True:
        raise ValueError("re-execution requires allow_execution is True")
    pair, channel = _bind(episode, task, ids, expected_reporting)
    observations = _run_actions(
        pair, episode.arm, tuple(step.action for step in episode.steps),
    )
    _check_database(task, episode.db_sha256)
    result = _score(episode.extracted_sql, task, episode.instrument)
    _check_database(task, episode.db_sha256)
    telemetry = None
    telemetry_matches = None
    if channel is not None:
        from train import sql_reporting
        telemetry = sql_reporting.snapshot_channel(
            channel, episode.reporting, arm=episode.arm,
        )
        telemetry_matches = (
            sql_reporting.snapshots_equal(telemetry, episode.telemetry) is True
        )
    return ReexecutionResult(
        observations=observations, result=result,
        observations_match=observations == tuple(step.observation for step in episode.steps),
        score_matches=result == episode.result,
        telemetry=telemetry, telemetry_matches=telemetry_matches,
    )
