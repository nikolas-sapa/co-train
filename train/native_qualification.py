"""Bounded engineering attempt, never production admission or a certificate."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
import copy
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
import dis
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import platform
import random
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from types import CodeType, FunctionType, MethodType, SimpleNamespace
from typing import TYPE_CHECKING, Any, ContextManager, Literal, Protocol
import weakref
import zipfile

if TYPE_CHECKING:
    from bench.task import SqlTask


_WIRE_LIMIT = 1048576
_REQUEST_FILE = Path("/var/tmp/qualification/request.json")
_OUTPUT = Path("/var/tmp/qualification/output")
_SOURCE = Path("/opt/qualification/source")
_MODEL = Path("/opt/qualification/model")
_DATA = Path("/opt/qualification/data")
_RUNTIME_KEY = "qualification/runtime-inventory.json"
_FIXTURES = (("first", 17), ("second", 29), ("third", 41), ("fourth", 53))
_CONSTRUCTION_SHA = "a9ed0c422adab7bc44f073c8a5fe2b83e3be7497110bfb297442f5216054ed4f"
_SELECTED_SOURCES = {
    "transformers.trainer": "1bb62572e150a929b7738ea529fbd0e1decc9a08ea904387989b9a2434dbd162",
    "trl.trainer.grpo_trainer": "cdbc962dda43cd58ff288680f7b2897903d113fcc87556e1f967163e37d248bc",
    "unsloth_zoo.compiler": "14134bb0f483515fa1a4d7ac1300fa0636214e265c0c4b1d622732d66552b9cf",
    "accelerate.optimizer": "41f802910e5d03e7cb4a2fd9ec204f44239b5c0d6b2fdcf11e0e2dc8a0848360",
    "accelerate.accelerator": "fb8f7c1e37146c68a73ca5a4dd820a28dc5c211e15a360bf500ece111ae4d43a",
    "torch.optim.optimizer": "ea3497233845529a212f81d4d325828eadc20f387ab94b1c21b96057f0001536",
    "torch.optim.adam": "7e5c8482c91b88e355a8bdf1d4b1930e8d961fb99f00c2179946b164a03652b6",
    "torch.optim.adamw": "54299056b7745c162192132bb6028f3387c05ff4203518ff0240058584968312",
    "torch.optim.lr_scheduler": "e5618b99182cb3fcbf6155e5b6f00fd471a0933272db098c375bdb90a64b2084",
    # Admitted rendered reference only. Different installed bytes are incompatible.
    "torch.amp.grad_scaler": "c952281af1b87408a406115149981ddb86936aba353637140706ee8760367738",
}


@dataclass(frozen=True)
class FilePin:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class AttemptBounds:
    total_ceiling_usd: Decimal
    prior_usage_usd: Decimal
    remaining_worst_case_usd: Decimal
    lifetime_seconds: int
    output_bytes_per_phase: int
    artifact_bytes: int
    retention_seconds: int


@dataclass(frozen=True)
class QualificationRequest:
    tasks: tuple[SqlTask, ...]
    db_root: Path
    model_dir: Path
    output_dir: Path
    source_pins: tuple[FilePin, ...]
    database_pins: tuple[FilePin, ...]
    runtime_inventory: FilePin
    image_digest: str
    bounds: AttemptBounds


@dataclass(frozen=True)
class OwnedJobResult:
    service_handle: object
    exported_root: Path
    phase_returncodes: tuple[int, int]


class QualificationController(Protocol):
    """Trusted external owner, not a capability manufactured by worker JSON.

    Approval covers build, staging, one service resource, every charge, bounded
    export/retention and unconditional resource teardown, even before a handle
    can be returned. run_once must not replace/retry a failed owned resource.
    """

    def require_approved(self, request: QualificationRequest) -> None: ...

    def run_once(self, request: QualificationRequest) -> OwnedJobResult: ...


@dataclass(frozen=True)
class _StagedAsset:
    host_path: Path
    kind: str
    key: str
    size: int
    sha256: str


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _positive(value: object, name: str) -> None:
    _require(type(value) is int and value > 0, f"{name} must be a positive integer")


def _costs_within_ceiling(left: Decimal, right: Decimal, ceiling: Decimal) -> bool:
    digit_deltas: dict[int, int] = {}
    for value, sign in ((left, 1), (right, 1), (ceiling, -1)):
        parts = value.as_tuple()
        for index, digit in enumerate(reversed(parts.digits)):
            if digit:
                position = parts.exponent + index
                digit_deltas[position] = digit_deltas.get(position, 0) + sign * digit

    prefix = 0
    previous_position = None
    # Lower tails lie strictly between -1 and 2 current-position units.
    # Only prefixes 0/-1 remain undecided; -1 across a gap >= 2 stays negative.
    for position in sorted(digit_deltas, reverse=True):
        if prefix == -1 and previous_position is not None:
            if previous_position - position >= 2:
                return True
            prefix *= 10
        prefix += digit_deltas[position]
        if prefix >= 1:
            return False
        if prefix <= -2:
            return True
        previous_position = position
    return prefix <= 0


def _validate_bounds(bounds: AttemptBounds) -> None:
    _require(isinstance(bounds, AttemptBounds), "AttemptBounds required")
    for name in ("total_ceiling_usd", "prior_usage_usd", "remaining_worst_case_usd"):
        value = getattr(bounds, name)
        _require(type(value) is Decimal and value.is_finite(), f"{name} requires finite Decimal")
    _require(0 < bounds.total_ceiling_usd <= 25, "total all-charge ceiling must be in (0,25]")
    _require(bounds.prior_usage_usd >= 0 and bounds.remaining_worst_case_usd >= 0,
             "usage and remaining all-charge cost must be nonnegative")
    _require(_costs_within_ceiling(bounds.prior_usage_usd, bounds.remaining_worst_case_usd,
                                 bounds.total_ceiling_usd),
             "prior plus remaining all-charge cost exceeds ceiling")
    for name in ("lifetime_seconds", "output_bytes_per_phase", "artifact_bytes", "retention_seconds"):
        _positive(getattr(bounds, name), name)
    _require(bounds.lifetime_seconds <= 1800, "aggregate lifetime exceeds 1800 seconds")


def _path(path: Path) -> Path:
    _require(isinstance(path, Path) and path.is_absolute() and ".." not in path.parts,
             "absolute nontraversing Path required")
    for component in (path, *path.parents):
        _require(not component.is_symlink(), f"symlink path refused: {component}")
    return path


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _check_asset_bytes(path: Path, *, size: int, sha256: str) -> None:
    _path(path)
    _require(type(size) is int and 0 <= size <= 2 * 1024**3, "invalid pinned size")
    _require(type(sha256) is str and re.fullmatch("[0-9a-f]{64}", sha256), "invalid pinned digest")
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                 "asset must be regular and not hardlinked")
        _require(before.st_size == size, "asset size differs from approved bytes")
        with path.open("rb") as stream:
            _require(_signature(os.fstat(stream.fileno())) == _signature(before), "asset changed at open")
            digest = hashlib.sha256()
            count = 0
            while block := stream.read(min(1048576, size - count + 1)):
                count += len(block)
                _require(count <= size, "asset grew during read")
                digest.update(block)
            _require(count == size and digest.hexdigest() == sha256, "asset byte pin mismatch")
            _require(_signature(os.fstat(stream.fileno())) == _signature(before), "asset changed during read")
        _require(_signature(path.lstat()) == _signature(before), "asset changed after read")
    except OSError as error:
        raise ValueError(f"cannot verify asset: {path}") from error


def _validate_fixture_scope(tasks: tuple[SqlTask, ...], db_root: Path) -> None:
    from bench.task import SqlTask
    import sqlite3

    root = _path(db_root)
    _require(type(tasks) is tuple and len(tasks) == 4, "exactly four fixture tasks required")
    for task, (name, amount) in zip(tasks, _FIXTURES, strict=True):
        database = root / name / f"{name}.sqlite"
        expected = SqlTask(
            name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
            evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
            db_id=name, db_path=str(database), tier="simple", tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture",
        )
        _require(type(task) is SqlTask and asdict(task) == asdict(expected),
                 f"fixture fields differ: {name}")
        _path(database)
        _require(database.is_file() and database.stat().st_nlink == 1, "fixture database missing/linked")
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                rows = connection.execute("SELECT amount FROM readings LIMIT 2").fetchall()
                schema = connection.execute("PRAGMA table_info(readings)").fetchall()
            _require(rows == [(amount,)], f"fixture database value differs: {name}")
            _require(len(schema) == 1 and schema[0][1:4] == ("amount", "INTEGER", 1),
                     "fixture database schema differs")
        except sqlite3.Error as error:
            raise ValueError(f"invalid fixture database: {name}") from error


def _validate_request(request: QualificationRequest) -> None:
    from train import guards, native_model

    _require(type(request) is QualificationRequest, "QualificationRequest required")
    _validate_bounds(request.bounds)
    roots = tuple(_path(path) for path in
                  (request.db_root, request.model_dir, request.output_dir, guards.REPO_ROOT))
    for index, left in enumerate(roots):
        for right in roots[index + 1:]:
            _require(not (left == right or left in right.parents or right in left.parents),
                     "source/data/model/export paths overlap")
    worker = request.output_dir == _OUTPUT and guards.REPO_ROOT == _SOURCE
    if not worker:
        _require(not request.output_dir.exists(), "host export must not already exist")
    _require(type(request.image_digest) is str
             and re.fullmatch(r"sha256:[0-9a-f]{64}", request.image_digest), "exact image digest required")
    _validate_fixture_scope(request.tasks, request.db_root)
    _require(type(request.database_pins) is tuple and len(request.database_pins) == 4,
             "exact database pins required")
    _require(all(type(pin) is FilePin for pin in request.database_pins),
             "database FilePin values required")
    _require({pin.path for pin in request.database_pins} == {Path(task.db_path) for task in request.tasks},
             "database pins do not cover fixtures exactly")
    _require(type(request.source_pins) is tuple and 1 <= len(request.source_pins) <= 512,
             "bounded source pins required")
    _require(all(type(pin) is FilePin for pin in request.source_pins)
             and type(request.runtime_inventory) is FilePin, "source/runtime FilePin values required")
    seen = set()
    for pin in (*request.source_pins, *request.database_pins, request.runtime_inventory):
        _require(type(pin) is FilePin and pin.path not in seen, "duplicate/invalid file pin")
        seen.add(pin.path)
        _check_asset_bytes(pin.path, size=pin.size, sha256=pin.sha256)
    for pin in request.source_pins:
        _require(pin.path.is_relative_to(guards.REPO_ROOT), "source outside fixed repository root")
    construction = guards.REPO_ROOT / "train/native_training.py"
    _require(any(pin.path == construction and pin.sha256 == _CONSTRUCTION_SHA
                 for pin in request.source_pins), "frozen common construction source pin missing")
    if worker:
        _candidate_prerequisites()
        with _REQUEST_FILE.open("rb") as stream:
            document = _decode_worker_transport(stream.read(_WIRE_LIMIT + 1))
        _require(_request_from_wire(document) == request, "mounted request differs from worker configuration")
        for row in document["assets"]:
            _check_asset_bytes(_asset_path(row["kind"], row["key"]),
                               size=row["size"], sha256=row["sha256"])
        expected_model = {
            (pin.path.relative_to(_MODEL).as_posix(), pin.size, pin.sha256)
            for pin in _verified_model_members(request)
        }
        _require({(row["key"], row["size"], row["sha256"]) for row in document["assets"]
                  if row["kind"] == "model"} == expected_model, "wire model assets do not match registered inventory")
        _check_firstparty_sources(request)
    native_model.verify_local_model(request.model_dir, model_revision=native_model.MODEL_REVISION)


def _verified_model_members(request: QualificationRequest) -> tuple[FilePin, ...]:
    from train import native_model

    native_model.verify_local_model(request.model_dir, model_revision=native_model.MODEL_REVISION)
    inventory = native_model._parse_inventory(
        Path(native_model.__file__).with_name("native_model_inventory.json").read_bytes(),
        native_model.INVENTORY_SHA256,
    )
    return tuple(FilePin(request.model_dir / row.path, row.size, row.sha256) for row in inventory.files)


def _asset_path(kind: str, key: str) -> Path:
    _require(type(kind) is str and kind in {"source", "model", "data"}, "unknown asset kind")
    _require(type(key) is str and 1 <= len(key) <= 256
             and re.fullmatch(r"[A-Za-z0-9_./-]+", key), "invalid relative asset key")
    parts = key.split("/")
    _require(all(part not in {"", ".", ".."} for part in parts)
             and not PurePosixPath(key).is_absolute(), "unsafe asset key")
    return {"source": _SOURCE, "model": _MODEL, "data": _DATA}[kind] / key


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def _closed(value: Any, names: set[str], label: str) -> None:
    _require(type(value) is dict and set(value) == names, f"invalid {label} fields")


def _bounds_from_wire(value: Any) -> AttemptBounds:
    _closed(value, {field.name for field in fields(AttemptBounds)}, "bounds")
    value = dict(value)
    for name in ("total_ceiling_usd", "prior_usage_usd", "remaining_worst_case_usd"):
        text = value[name]
        _require(type(text) is str and len(text) <= 64
                 and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text), "invalid wire Decimal")
        value[name] = Decimal(text)
    bounds = AttemptBounds(**value)
    _validate_bounds(bounds)
    return bounds


def _decode_worker_transport(payload: bytes) -> dict[str, Any]:
    from bench.task import SqlTask

    _require(type(payload) is bytes and len(payload) <= _WIRE_LIMIT, "worker JSON exceeds 1 MiB")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("invalid closed worker JSON") from error
    _closed(document, {"schema", "assets", "tasks", "image_digest", "bounds"}, "worker")
    _require(document["schema"] == "native-sql-worker-v1", "unknown worker schema")
    _require(type(document["image_digest"]) is str
             and re.fullmatch(r"sha256:[0-9a-f]{64}", document["image_digest"]), "invalid image label")
    _bounds_from_wire(document["bounds"])
    assets = document["assets"]
    _require(type(assets) is list and 1 <= len(assets) <= 1024, "invalid asset count")
    keys = set()
    for member in assets:
        _closed(member, {"kind", "key", "size", "sha256"}, "asset")
        _asset_path(member["kind"], member["key"])
        pair = (member["kind"], member["key"])
        _require(pair not in keys, "asset collision")
        keys.add(pair)
        _require(type(member["size"]) is int and 0 <= member["size"] <= 2 * 1024**3,
                 "invalid asset size")
        _require(type(member["sha256"]) is str
                 and re.fullmatch("[0-9a-f]{64}", member["sha256"]), "invalid asset digest")
    _require(("source", _RUNTIME_KEY) in keys, "reserved runtime inventory missing")
    tasks = document["tasks"]
    _require(type(tasks) is list and len(tasks) == 4, "exactly four wire tasks required")
    task_fields = {field.name for field in fields(SqlTask)} - {"db_path"}
    db_keys = set()
    for row in tasks:
        _closed(row, task_fields | {"db_asset"}, "task")
        _require(all(type(row[name]) is str for name in task_fields), "task fields must be strings")
        _asset_path("data", row["db_asset"])
        _require(("data", row["db_asset"]) in keys and row["db_asset"] not in db_keys,
                 "missing or repeated database asset")
        db_keys.add(row["db_asset"])
    _require({key for kind, key in keys if kind == "data"} == db_keys, "extra data assets refused")
    return document


def _prepare_worker_transport(
    request: QualificationRequest,
) -> tuple[bytes, tuple[_StagedAsset, ...]]:
    from train import guards

    _validate_request(request)
    staged = []
    for kind, root, pins in (
        ("source", guards.REPO_ROOT, request.source_pins),
        ("model", request.model_dir, _verified_model_members(request)),
        ("data", request.db_root, request.database_pins),
    ):
        for pin in pins:
            _require(pin.path.is_relative_to(root), "asset outside approved root")
            key = pin.path.relative_to(root).as_posix()
            _asset_path(kind, key)
            _require(not (kind == "source" and key == _RUNTIME_KEY), "reserved source collision")
            _check_asset_bytes(pin.path, size=pin.size, sha256=pin.sha256)
            staged.append(_StagedAsset(pin.path, kind, key, pin.size, pin.sha256))
    pin = request.runtime_inventory
    _check_asset_bytes(pin.path, size=pin.size, sha256=pin.sha256)
    staged.append(_StagedAsset(pin.path, "source", _RUNTIME_KEY, pin.size, pin.sha256))
    bounds = asdict(request.bounds)
    for name, value in bounds.items():
        if isinstance(value, Decimal):
            bounds[name] = format(value, "f")
    tasks = []
    for task in request.tasks:
        row = asdict(task)
        row["db_asset"] = Path(row.pop("db_path")).relative_to(request.db_root).as_posix()
        tasks.append(row)
    document = {
        "schema": "native-sql-worker-v1",
        "assets": [{key: getattr(asset, key) for key in ("kind", "key", "size", "sha256")}
                   for asset in staged],
        "tasks": tasks, "image_digest": request.image_digest, "bounds": bounds,
    }
    payload = json.dumps(document, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    _decode_worker_transport(payload)
    return payload, tuple(staged)


def _request_from_wire(document: dict[str, Any]) -> QualificationRequest:
    from bench.task import SqlTask

    # Round-trip validation also protects callers of this private reconstruction leaf.
    document = _decode_worker_transport(json.dumps(document, allow_nan=False).encode())
    pins = {kind: [] for kind in ("source", "model", "data")}
    runtime = None
    for row in document["assets"]:
        pin = FilePin(_asset_path(row["kind"], row["key"]), row["size"], row["sha256"])
        if (row["kind"], row["key"]) == ("source", _RUNTIME_KEY):
            runtime = pin
        else:
            pins[row["kind"]].append(pin)
    _require(runtime is not None, "runtime pin missing")
    tasks = []
    for row in document["tasks"]:
        row = dict(row)
        row["db_path"] = str(_asset_path("data", row.pop("db_asset")))
        tasks.append(SqlTask(**row))
    return QualificationRequest(
        tuple(tasks), _DATA, _MODEL, _OUTPUT, tuple(pins["source"]),
        tuple(pins["data"]), runtime, document["image_digest"],
        _bounds_from_wire(document["bounds"]),
    )


def _phase_argv(request_file: Path, phase: Literal[1, 2]) -> tuple[str, ...]:
    _require(type(phase) is int and phase in (1, 2), "invalid phase")
    _require(request_file == _REQUEST_FILE, "private request path must be fixed")
    return ("/usr/local/bin/python3.12", "-m", "train.native_qualification",
            "--_phase", str(phase), "--_request", str(_REQUEST_FILE))


@contextmanager
def _owned_subreaper() -> ContextManager[None]:
    libc = None
    old = None
    if sys.platform == "linux":
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        _require(libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0,
                 "cannot inspect process-local child subreaper")
        old = previous.value
        _require(libc.prctl(36, 1, 0, 0, 0) == 0, "cannot own orphaned phase descendants")
    try:
        yield
    finally:
        if libc is not None:
            _require(libc.prctl(36, old, 0, 0, 0) == 0, "cannot restore process-local child subreaper")


def _run_child(
    request_file: Path, phase: Literal[1, 2], *, deadline: float, output_limit: int,
) -> None:
    _positive(output_limit, "output limit")
    _require(type(deadline) is float and 0 < deadline < float("inf"), "finite aggregate deadline required")
    _require(time.monotonic() < deadline, "aggregate deadline expired before launch")
    artifact_limit = None
    if request_file == _REQUEST_FILE:
        with request_file.open("rb") as stream:
            document = _decode_worker_transport(stream.read(_WIRE_LIMIT + 1))
        artifact_limit = _bounds_from_wire(document["bounds"]).artifact_bytes
    nonreaping = hasattr(os, "waitid") and hasattr(os, "WNOWAIT")
    with _owned_subreaper():
        child = subprocess.Popen(
            _phase_argv(request_file, phase), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
            shell=False, close_fds=True,
        )
        status = None
        reaped = False
        owned = True
        try:
            _require(child.stdout is not None, "missing child output stream")
            os.set_blocking(child.stdout.fileno(), False)
            count = 0
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                eof = False
                while not eof or status is None:
                    remaining = deadline - time.monotonic()
                    _require(remaining > 0, "aggregate child deadline expired")
                    if artifact_limit is not None:
                        _output_size(_OUTPUT, artifact_limit)
                    for key, _ in selector.select(min(remaining, 0.05)):
                        block = os.read(key.fd, min(65536, output_limit - count + 1))
                        if not block:
                            selector.unregister(key.fileobj)
                            eof = True
                            continue
                        count += len(block)
                        _require(count <= output_limit, "combined child output exceeded cap")
                    # Retain the leader until cleanup so its PID/group cannot be
                    # recycled between status observation and owned-group signal.
                    if nonreaping:
                        try:
                            status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        except ChildProcessError as error:
                            owned = False
                            raise ValueError("owned phase leader status became ambiguous") from error
                    elif eof:
                        try:
                            pid, wait_status = os.waitpid(child.pid, os.WNOHANG)
                        except ChildProcessError as error:
                            owned = False
                            raise ValueError("owned phase leader already reaped externally") from error
                        if pid == child.pid:
                            reaped = True
                            owned = False
                            child.returncode = os.waitstatus_to_exitcode(wait_status)
                            status = child.returncode
                        elif pid != 0:
                            owned = False
                            raise ValueError("owned phase waitpid returned ambiguous PID")
                    if eof and status is None:
                        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            if (nonreaping and (status.si_code != os.CLD_EXITED or status.si_status != 0)
                    or not nonreaping and status != 0):
                raise RuntimeError(f"native phase {phase} failed")
        finally:
            if owned and not reaped:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                reaped = True
                owned = False
            if child.stdout is not None:
                child.stdout.close()
            if nonreaping and reaped:
                reap_deadline = time.monotonic() + 2
                while True:
                    try:
                        pid, _ = os.waitpid(-child.pid, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if pid == 0:
                        _require(time.monotonic() < reap_deadline, "owned phase descendants did not reap")
                        time.sleep(0.005)
            if reaped:
                try:
                    os.killpg(child.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise ValueError("phase group remains after leader reap; external owner teardown required")


def _worker_main(request_file: Path) -> int:
    started = time.monotonic()
    _path(request_file)
    with request_file.open("rb") as stream:
        document = _decode_worker_transport(stream.read(_WIRE_LIMIT + 1))
    request = _request_from_wire(document)
    _validate_request(request)
    deadline = started + request.bounds.lifetime_seconds
    _require(not request.output_dir.exists(), "worker output must initially be fresh")
    for phase in (1, 2):
        _run_child(request_file, phase, deadline=deadline,
                   output_limit=request.bounds.output_bytes_per_phase)
    _require(time.monotonic() < deadline, "aggregate deadline exceeded during cleanup")
    return 0


def _observer_dependencies() -> SimpleNamespace:
    import numpy
    import torch
    from peft import get_peft_model_state_dict
    from transformers import TrainerCallback

    return SimpleNamespace(torch=torch, numpy=numpy, TrainerCallback=TrainerCallback,
                           get_peft_model_state_dict=get_peft_model_state_dict)


def _snapshot(value: Any, dependencies: SimpleNamespace) -> Any:
    if dependencies.torch.is_tensor(value):
        _require(bool(dependencies.torch.isfinite(value).all()), "nonfinite native state tensor")
        return value.detach().cpu().clone()
    if isinstance(value, Mapping):
        return {key: _snapshot(item, dependencies) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_snapshot(item, dependencies) for item in value)
    if type(value) in (int, bool, str, type(None)):
        return value
    if type(value) is float:
        _require(float("-inf") < value < float("inf"), "nonfinite native state scalar")
        return value
    raise ValueError(f"unsupported native state type: {type(value).__name__}")


def _equal(left: Any, right: Any, dependencies: SimpleNamespace) -> bool:
    torch = dependencies.torch
    if torch.is_tensor(left) or torch.is_tensor(right):
        return (torch.is_tensor(left) and torch.is_tensor(right)
                and bool(torch.isfinite(left).all()) and bool(torch.isfinite(right).all())
                and bool(torch.equal(left.detach().cpu(), right.detach().cpu())))
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(_equal(left[key], right[key], dependencies) for key in left)
    if type(left) in (tuple, list) and type(right) is type(left):
        return len(left) == len(right) and all(_equal(a, b, dependencies) for a, b in zip(left, right, strict=True))
    if type(left) is not type(right):
        return False
    if type(left) in (str, int, float, bool, type(None)):
        if type(left) is float:
            return (float("-inf") < left < float("inf")
                    and float("-inf") < right < float("inf") and left == right)
        return left == right
    return bool(dependencies.numpy.array_equal(left, right))


def _capture_rng(dependencies: SimpleNamespace) -> dict[str, Any]:
    torch = dependencies.torch
    _require(torch.cuda.is_available(), "CUDA RNG required for this native candidate")
    return {
        "python": random.getstate(),
        "numpy": copy.deepcopy(dependencies.numpy.random.get_state()),
        "cpu": torch.get_rng_state().clone(),
        "cuda": torch.cuda.get_rng_state().clone(),
        "cuda_all": [state.clone() for state in torch.cuda.get_rng_state_all()],
    }


def _restore_probe_rng(saved: dict[str, Any], dependencies: SimpleNamespace) -> None:
    random.setstate(saved["python"])
    dependencies.numpy.random.set_state(saved["numpy"])
    dependencies.torch.set_rng_state(saved["cpu"])
    dependencies.torch.cuda.set_rng_state_all(saved["cuda_all"])


def _check_sampler(trainer: Any) -> None:
    dependencies = _observer_dependencies()
    saved = _capture_rng(dependencies)
    sampler = loader = iterator = None
    accelerator = getattr(trainer, "accelerator", None)
    registered = getattr(accelerator, "_dataloaders", None)
    previous_loaders = list(registered) if registered is not None else None
    _require(getattr(trainer, "_train_dataloader", None) is None,
             "disposable probe cannot consume an existing training loader")
    try:
        args = trainer.args
        for name, expected in (
            ("num_generations", 4), ("generation_batch_size", 16),
            ("steps_per_generation", 2), ("per_device_train_batch_size", 8),
            ("gradient_accumulation_steps", 2), ("num_iterations", 1),
        ):
            _require(type(getattr(args, name)) is int and getattr(args, name) == expected,
                     f"resolved sampler config differs: {name}")
        _require(len(trainer.train_dataset) == 4, "sampler dataset must contain four rows")
        ids = [row["task_id"] for row in trainer.train_dataset]
        _require(ids == [name for name, _ in _FIXTURES], "sampler dataset task identity differs")
        sampler = trainer._get_train_sampler()
        indices = list(itertools.islice(iter(sampler), 33))
        _require(len(sampler) == len(indices) == 32, "actual sampler must yield exactly 32 indices")
        _require(all(type(index) is int for index in indices)
                 and Counter(indices) == Counter({0: 8, 1: 8, 2: 8, 3: 8}),
                 "actual sampler distribution differs")
        loader = trainer.get_train_dataloader()
        iterator = iter(loader)
        batches = list(itertools.islice(iterator, 3))
        _require(len(batches) == 2, "prepared loader must yield exactly two batches")
        for batch in batches:
            _require(type(batch) is list and len(batch) == 16, "native identity-collator batch must have 16 rows")
            _require(Counter(row["task_id"] for row in batch) == Counter(dict.fromkeys(ids, 4)),
                     "prepared batch task distribution differs")
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
        if previous_loaders is not None:
            _require(all(any(item is previous for item in registered) for previous in previous_loaders),
                     "probe altered existing accelerator dataloaders")
            _require(all(any(item is previous for previous in previous_loaders) or item is loader
                         for item in registered), "probe registered an unknown extra dataloader")
            registered[:] = previous_loaders
        del iterator, loader, sampler
        _restore_probe_rng(saved, dependencies)


_CHECKPOINT_MEMBERS = frozenset({
    "trainer_state.json", "optimizer.pt", "scheduler.pt", "scaler.pt",
    "rng_state.pth", "adapter_model.safetensors", "adapter_config.json",
    "entropy_ctrl_state.json", "training_args.bin", "README.md",
    "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
    "added_tokens.json", "vocab.json", "merges.txt", "chat_template.jinja",
    "config.json", "generation_config.json",
})
_MAX_CHECKPOINT_BYTES = 2 * 1024**3
_MAX_MEMBER_BYTES = 1024**3


def _checkpoint_members(checkpoint: Path, limit: int = _MAX_CHECKPOINT_BYTES) -> set[str]:
    _path(checkpoint)
    _require(checkpoint.is_dir(), "native checkpoint directory missing")
    names = set()
    total = 0
    for member in checkpoint.iterdir():
        _require(len(names) < len(_CHECKPOINT_MEMBERS), "too many native checkpoint members")
        _require(member.name in _CHECKPOINT_MEMBERS, f"unexpected checkpoint member: {member.name}")
        info = member.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "linked/nonregular checkpoint member")
        _require(info.st_size <= _MAX_MEMBER_BYTES, "checkpoint member exceeds byte limit")
        total += info.st_size
        _require(total <= min(limit, _MAX_CHECKPOINT_BYTES), "checkpoint exceeds byte limit")
        names.add(member.name)
    return names


def _read_member(checkpoint: Path, name: str, limit: int) -> bytes:
    _require(name in _checkpoint_members(checkpoint), f"missing native member: {name}")
    path = checkpoint / name
    before = path.lstat()
    _require(before.st_size <= limit, f"native member too large: {name}")
    with path.open("rb") as stream:
        _require(_signature(os.fstat(stream.fileno())) == _signature(before), "checkpoint changed at open")
        raw = stream.read(limit + 1)
        _require(len(raw) == before.st_size and len(raw) <= limit, "checkpoint changed during read")
        _require(_signature(os.fstat(stream.fileno())) == _signature(before), "checkpoint changed during read")
    _require(_signature(path.lstat()) == _signature(before), "checkpoint changed after read")
    return raw


def _json_member(checkpoint: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_member(checkpoint, name, _WIRE_LIMIT), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"invalid checkpoint JSON: {name}") from error
    _require(type(value) is dict, "native JSON object required")
    return value


def _rng_allowlist(dependencies: SimpleNamespace) -> list[Any]:
    numpy = dependencies.numpy
    result = []
    core = getattr(numpy, "_core", None)
    if core is None:
        core = getattr(numpy, "core", None)
    multiarray = getattr(core, "multiarray", None)
    for value in (
        getattr(multiarray, "_reconstruct", None), getattr(numpy, "ndarray", None),
        getattr(numpy, "dtype", None), getattr(getattr(numpy, "dtypes", None), "UInt32DType", None),
    ):
        if value is not None:
            _require(getattr(value, "__module__", "").startswith("numpy"), "non-native RNG allowlist")
            result.append(value)
    return result


def _load_native_state(checkpoint: Path, name: str, dependencies: SimpleNamespace) -> Any:
    _require(name in {"optimizer.pt", "scheduler.pt", "scaler.pt", "rng_state.pth"},
             "unapproved native deserializer member")
    _require(name in _checkpoint_members(checkpoint), f"missing native member: {name}")
    path = checkpoint / name
    before = path.lstat()
    with path.open("rb") as stream:
        _require(_signature(os.fstat(stream.fileno())) == _signature(before), "native member changed at open")
        _check_native_archive(stream)
        stream.seek(0)
        get_globals = getattr(dependencies.torch.serialization, "get_safe_globals", None)
        _require(callable(get_globals), "native Torch safe-global inspection API required")
        allowed = _rng_allowlist(dependencies)
        _require(all(any(item is native for native in allowed) for item in get_globals()),
                 "unreviewed ambient Torch deserialization allowlist")
        with dependencies.torch.serialization.safe_globals(
            allowed if name == "rng_state.pth" else [],
        ):
            value = dependencies.torch.load(stream, weights_only=True, map_location="cpu")
        _require(_signature(os.fstat(stream.fileno())) == _signature(before), "native member changed during load")
    _require(_signature(path.lstat()) == _signature(before), "native member changed after load")
    return value


def _check_native_archive(stream: Any) -> None:
    try:
        with zipfile.ZipFile(stream) as archive:
            seen = set()
            total = 0
            for member in archive.infolist():
                _require(len(seen) < 8192 and member.filename not in seen, "duplicate/excessive native ZIP members")
                _asset_path("source", member.filename.rstrip("/"))
                _require(member.compress_type == zipfile.ZIP_STORED and not member.flag_bits & 1,
                         "compressed/encrypted native tensor archive unsupported")
                mode = member.external_attr >> 16
                _require(not stat.S_ISLNK(mode), "native tensor archive link refused")
                total += member.file_size
                _require(member.file_size <= _MAX_MEMBER_BYTES and total <= _MAX_MEMBER_BYTES,
                         "native tensor archive storage exceeds limit")
                seen.add(member.filename)
            _require(seen and any(name.endswith("/data.pkl") for name in seen),
                     "native torch ZIP state layout missing")
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("invalid native tensor archive") from error


def _load_adapter_state(checkpoint: Path) -> Mapping[str, Any]:
    from safetensors import safe_open

    _require("adapter_model.safetensors" in _checkpoint_members(checkpoint), "native adapter missing")
    path = checkpoint / "adapter_model.safetensors"
    before = path.lstat()
    result = {}
    total = 0
    with safe_open(str(path), framework="pt", device="cpu") as reader:
        for key in reader.keys():
            _require(len(result) < 4096, "too many adapter tensors")
            tensor = reader.get_tensor(key)
            total += tensor.numel() * tensor.element_size()
            _require(total <= _MAX_MEMBER_BYTES, "adapter tensor bytes exceed limit")
            result[key] = tensor
    _require(_signature(path.lstat()) == _signature(before), "adapter changed during read")
    return result


def _native_adapter_state(trainer: Any, dependencies: SimpleNamespace) -> Mapping[str, Any]:
    model = trainer.accelerator.unwrap_model(trainer.model)
    export = getattr(dependencies, "get_peft_model_state_dict", None)
    _require(callable(export), "native PEFT get_peft_model_state_dict API required")
    _require(set(model.peft_config) == {"default"} and model.active_adapter == "default",
             "exactly one native default adapter required")
    try:
        state = model.state_dict(keep_vars=True)
        native = export(model, state_dict=state, adapter_name="default", save_embedding_layers=False)
    except (AttributeError, TypeError) as error:
        raise ValueError("native PEFT keep_vars export API unavailable") from error
    trainable = [(name, parameter) for name, parameter in model.named_parameters()
                 if parameter.requires_grad]
    _require(trainable and len(trainable) <= 4096, "bounded trainable adapter parameters required")
    _require(all("lora_" in name for name, _ in trainable), "non-LoRA trainable state unsupported")
    covered = set()
    for name, parameter in trainable:
        # Native export chooses keys; live object identity, not guessed renaming,
        # establishes complete coverage of the actual trainable parameters.
        keys = [key for key, tensor in native.items() if tensor is parameter]
        _require(len(keys) == 1 and keys[0] not in covered,
                 f"native PEFT export does not unambiguously cover trainable: {name}")
        covered.add(keys[0])
    _require(covered == set(native), "native PEFT export contains unsupported nontrainable state")
    return native


def _compare_restored_state(trainer: Any, checkpoint_1: Path) -> None:
    dependencies = _observer_dependencies()
    expected = _load_adapter_state(checkpoint_1)
    actual = _native_adapter_state(trainer, dependencies)
    _require(_equal(actual, expected, dependencies), "native adapter/model tensors differ")
    for name, state in (
        ("optimizer.pt", trainer.optimizer.state_dict()),
        ("scheduler.pt", trainer.lr_scheduler.state_dict()),
    ):
        _require(_equal(state, _load_native_state(checkpoint_1, name, dependencies), dependencies),
                 f"native restored state differs: {name}")
    scaler = trainer.accelerator.scaler
    if scaler is not None:
        _require(_equal(scaler.state_dict(), _load_native_state(checkpoint_1, "scaler.pt", dependencies),
                        dependencies), "native scaler state differs")
    if trainer.use_adaptive_entropy:
        entropy = _json_member(checkpoint_1, "entropy_ctrl_state.json")
        _closed(entropy, {"entropy_coef", "last_world_entropy"}, "native entropy")
        _require(_equal(entropy, {"entropy_coef": trainer.entropy_coef,
                                 "last_world_entropy": trainer._last_world_entropy}, dependencies),
                 "native entropy state differs")
        _require(trainer._entropy_window_stats is None, "native entropy window remains pending")


def _check_checkpoint(trainer: Any, checkpoint: Path, expected_step: Literal[1, 2]) -> None:
    _require(type(expected_step) is int and expected_step in (1, 2), "invalid expected checkpoint step")
    members = _checkpoint_members(checkpoint)
    required = {"trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth",
                "adapter_model.safetensors", "adapter_config.json"}
    # training_args.bin is an opaque native file: existence only, never load it.
    _require(required <= members, "incomplete native full-state checkpoint")
    state = _json_member(checkpoint, "trainer_state.json")
    _require(type(state.get("global_step")) is int and state["global_step"] == expected_step
             and type(state.get("max_steps")) is int and state["max_steps"] == 2,
             "native checkpoint step/horizon differs")
    _require(trainer.state.global_step == expected_step and trainer.args.max_steps == 2
             and trainer.state.max_steps == 2 and trainer.args.save_only_model is False,
             "live checkpoint boundary differs")
    adapter_config = _json_member(checkpoint, "adapter_config.json")
    _require(adapter_config.get("peft_type") == "LORA"
             and type(adapter_config.get("r")) is int and adapter_config["r"] == 32
             and type(adapter_config.get("lora_alpha")) is int and adapter_config["lora_alpha"] == 32,
             "native checkpoint LoRA configuration differs")
    window = trainer.args.steps_per_generation * trainer.args.num_iterations
    _require(type(trainer._step) is int and trainer._step % window == 0,
             "checkpoint has unfinished generation reuse")
    _require(trainer._entropy_window_stats is None, "checkpoint entropy window remains pending")
    if trainer.accelerator.scaler is not None:
        _require("scaler.pt" in members, "native AMP scaler missing")
    dependencies = _observer_dependencies()
    rng = _load_native_state(checkpoint, "rng_state.pth", dependencies)
    _require(type(rng) is dict and set(rng) == {"python", "numpy", "cpu", "cuda"},
             "unsupported single-GPU native RNG layout")
    _require(dependencies.torch.is_tensor(rng["cpu"]) and dependencies.torch.is_tensor(rng["cuda"]),
             "single-GPU native RNG fields must be tensors, not all-device lists")
    _compare_restored_state(trainer, checkpoint)


def _base_optimizer(optimizer: Any) -> Any:
    seen = set()
    while hasattr(optimizer, "optimizer"):
        _require(id(optimizer) not in seen, "cyclic optimizer wrapping")
        seen.add(id(optimizer))
        optimizer = optimizer.optimizer
    _require(callable(getattr(optimizer, "register_step_pre_hook", None))
             and callable(getattr(optimizer, "register_step_post_hook", None)),
             "original optimizer observation hooks unavailable")
    return optimizer


def _expected_optimizer_implementations() -> SimpleNamespace:
    optimizer, _, optimizer_code = _selected_module("torch.optim.optimizer")
    adam, _, adam_code = _selected_module("torch.optim.adam")
    adamw, _, adamw_code = _selected_module("torch.optim.adamw")
    accelerate, _, accelerate_code = _selected_module("accelerate.optimizer")
    scheduler, _, scheduler_code = _selected_module("torch.optim.lr_scheduler")
    scaler, _, scaler_code = _selected_module("torch.amp.grad_scaler")
    roles = {}

    def role(name: str, module: Any, code: CodeType, qualname: str,
             defaults: Any = None, kwdefaults: Any = None) -> None:
        roles[name] = (_find_code(code, qualname), vars(module), defaults, kwdefaults)

    role("base_init", optimizer, optimizer_code, "Optimizer.__init__")
    role("adam_init", adam, adam_code, "Adam.__init__",
         (1e-3, (0.9, 0.999), 1e-8, 0, False),
         dict(foreach=None, maximize=False, capturable=False, differentiable=False,
              fused=None, decoupled_weight_decay=False))
    role("adamw_init", adamw, adamw_code, "AdamW.__init__",
         (1e-3, (0.9, 0.999), 1e-8, 1e-2, False),
         dict(maximize=False, foreach=None, capturable=False, differentiable=False, fused=None))
    role("outer_init", accelerate, accelerate_code, "AcceleratedOptimizer.__init__", (True, None))
    role("scaler_init", scaler, scaler_code, "GradScaler.__init__",
         ("cuda", 65536.0, 2.0, 0.5, 2000, True))
    role("raw", adam, adam_code, "Adam.step", (None,))
    role("grad", optimizer, optimizer_code, "_use_grad_for_differentiable.<locals>._use_grad")
    role("profile", optimizer, optimizer_code, "Optimizer.profile_hook_step.<locals>.wrapper")
    role("outer", accelerate, accelerate_code, "AcceleratedOptimizer.step", (None,))
    role("patch", accelerate, accelerate_code, "patch_optimizer_step.<locals>.patched_step")
    role("scheduler", scheduler, scheduler_code,
         "LRScheduler.__init__.<locals>.patch_track_step_called.<locals>.wrap_step.<locals>.wrapper")
    role("scaler_step", scaler, scaler_code, "GradScaler.step")
    role("scaler_maybe", scaler, scaler_code, "GradScaler._maybe_opt_step")
    for name, method in (("pre_hook", "register_step_pre_hook"),
                         ("post_hook", "register_step_post_hook"),
                         ("step_code", "_optimizer_step_code"),
                         ("patch_function", "_patch_step_function")):
        role(name, optimizer, optimizer_code, f"Optimizer.{method}")
    return SimpleNamespace(
        topology="accelerated", base=adamw.AdamW, outer=accelerate.AcceleratedOptimizer,
        scaler=scaler.GradScaler, scheduler=scheduler.LRScheduler, roles=roles,
        classes=((optimizer.Optimizer, (object,), "base_init"),
                 (adam.Adam, (optimizer.Optimizer,), "adam_init"),
                 (adamw.AdamW, (adam.Adam,), "adamw_init"),
                 (accelerate.AcceleratedOptimizer, (optimizer.Optimizer,), "outer_init"),
                 (scaler.GradScaler, (object,), "scaler_init")),
    )


def _optimizer_function(function: Any, role: str, spec: SimpleNamespace,
                        links: Mapping[str, Any]) -> Any:
    expected, namespace, defaults, kwdefaults = spec.roles[role]
    _require(type(function) is FunctionType
             and _code_shape(function.__code__) == _code_shape(expected)
             and function.__globals__ is namespace
             and function.__defaults__ == defaults and function.__kwdefaults__ == kwdefaults,
             f"optimizer origin code/globals/defaults mismatch: {role}")
    _require(set(function.__code__.co_freevars) == set(links)
             and len(function.__closure__ or ()) == len(links),
             f"optimizer origin closure layout mismatch: {role}")
    try:
        cells = dict(zip(function.__code__.co_freevars, function.__closure__ or (), strict=True))
        _require(all(cells[name].cell_contents is target or (
            type(target) is MethodType and type(cells[name].cell_contents) is MethodType
            and cells[name].cell_contents.__self__ is target.__self__
            and cells[name].cell_contents.__func__ is target.__func__
        ) for name, target in links.items()),
                 f"optimizer origin closure target mismatch: {role}")
    except ValueError as error:
        raise ValueError(f"optimizer origin closure mismatch: {role}") from error
    if hasattr(function, "__wrapped__"):
        _require("func" in links and function.__wrapped__ is links["func"],
                 f"optimizer origin wrapped target mismatch: {role}")
    return function


def _optimizer_method(receiver: Any, name: str, role: str, spec: SimpleNamespace) -> Any:
    method = getattr(receiver, name, None)
    _require(type(method) is MethodType and method.__self__ is receiver
             and name not in vars(receiver)
             and getattr(type(receiver), name, None) is method.__func__,
             f"optimizer origin bound receiver mismatch: {role}")
    return _optimizer_function(method.__func__, role, spec, {})


def _optimizer_graph(trainer: Any, spec: SimpleNamespace, transient: bool) -> SimpleNamespace:
    for cls, bases, role in spec.classes:
        _require(type(cls) is type and cls.__bases__ == bases,
                 "optimizer origin concrete class/MRO mismatch")
        constructor = cls.__dict__.get("__init__")
        links = {"__class__": cls} if "__class__" in spec.roles[role][0].co_freevars else {}
        _optimizer_function(constructor, role, spec, links)
    outer = trainer.optimizer
    base = outer if spec.topology == "direct" else getattr(outer, "optimizer", None)
    _require(type(base) is spec.base, "optimizer origin native concrete type mismatch")
    functions = [
        _optimizer_method(base, "register_step_pre_hook", "pre_hook", spec),
        _optimizer_method(base, "register_step_post_hook", "post_hook", spec),
    ]
    if spec.topology == "direct":
        raw = _optimizer_method(base, "step", "raw", spec)
        return SimpleNamespace(base=base, graph=tuple(functions + [raw]), raw=raw,
                               calls=((raw.__code__, base, "raw"),))
    _require(spec.topology == "accelerated" and type(outer) is spec.outer,
             "optimizer origin prepared concrete type mismatch")
    scale = trainer.accelerator.scaler
    _require(type(scale) is spec.scaler and outer.scaler is scale
             and scale._enabled is True, "optimizer origin active scaler mismatch")
    _require(isinstance(trainer.lr_scheduler, spec.scheduler)
             and trainer.lr_scheduler.optimizer is outer,
             "optimizer origin scheduler owner mismatch")
    for name, role in (("_optimizer_step_code", "step_code"),
                       ("_patch_step_function", "patch_function")):
        functions.append(_optimizer_method(base, name, role, spec))
    profile = getattr(type(base), "step", None)
    _require(type(profile) is FunctionType and profile.__closure__,
             "optimizer origin native profile wrapper missing")
    # Extract only fixed closure roles; each target is independently checked below.
    def target(function: Any, name: str) -> Any:
        _require(type(function) is FunctionType, "optimizer origin callable closure required")
        try:
            cells = dict(zip(function.__code__.co_freevars, function.__closure__ or (), strict=True))
            return cells[name].cell_contents
        except (KeyError, ValueError) as error:
            raise ValueError("optimizer origin missing closure target") from error

    grad = target(profile, "func")
    raw = target(grad, "func")
    _optimizer_function(raw, "raw", spec, {})
    _optimizer_function(grad, "grad", spec, {"func": raw})
    _optimizer_function(profile, "profile", spec, {"func": grad})
    original = getattr(outer, "_optimizer_original_step_method", None)
    _require(type(original) is MethodType and original.__self__ is base
             and original.__func__ is profile, "optimizer origin saved native self/step mismatch")
    patch = getattr(outer, "_optimizer_patched_step_method", None)
    _optimizer_function(patch, "patch", spec, {"accelerated_optimizer": outer, "method": original})
    actual = base.step
    _require((transient and actual is patch) or (
        not transient and type(actual) is MethodType and actual.__self__ is base
        and actual.__func__ is profile), "optimizer origin native instance step mismatch")
    outer_step = getattr(type(outer), "step", None)
    _optimizer_function(outer_step, "outer", spec, {})
    wrapper = vars(outer).get("step")
    reference = target(wrapper, "opt_ref")
    _require(type(reference) is weakref.ReferenceType and reference() is outer,
             "optimizer origin scheduler weakref mismatch")
    _optimizer_function(wrapper, "scheduler", spec, {"func": outer_step, "opt_ref": reference})
    scale_step = _optimizer_method(scale, "step", "scaler_step", spec)
    scale_maybe = _optimizer_method(scale, "_maybe_opt_step", "scaler_maybe", spec)
    functions.extend((profile, grad, raw, patch, outer_step, wrapper, scale_step, scale_maybe))
    return SimpleNamespace(
        base=base, graph=(outer, base, scale, trainer.lr_scheduler, *functions), raw=raw,
        calls=((raw.__code__, base, "raw"), (outer_step.__code__, outer, "outer"),
               (scale_step.__code__, scale, "scaler")),
    )


def _bind_optimizer_origin(trainer: Any) -> SimpleNamespace:
    spec = _expected_optimizer_implementations()
    bound = _optimizer_graph(trainer, spec, False)

    def check(transient: bool = False) -> None:
        current = _optimizer_graph(trainer, spec, transient)
        _require(len(current.graph) == len(bound.graph)
                 and all(left is right for left, right in zip(current.graph, bound.graph, strict=True)),
                 "optimizer origin anchored graph changed")

    bound.check = check
    return bound


def _make_callback(trainer: Any, phase: Literal[1, 2], checkpoint_1: Path | None) -> Any:
    _require(type(phase) is int and phase in (1, 2), "invalid callback phase")
    _require((phase == 2) == (checkpoint_1 is not None), "resume checkpoint/phase mismatch")
    dependencies = _observer_dependencies()

    class NativeObserver(dependencies.TrainerCallback):
        def __init__(self) -> None:
            self.phase = phase
            self.checkpoint = checkpoint_1
            self.started = False
            self.boundary = "new"
            self.updates = 0
            self.generations = 0
            self.saved = False
            self.restored_rng = False
            self.restores = 0
            self.trace_active = False
            self.native_clip = False
            self.requires_clip_trace = False
            self.hooks = []
            self.original_optimizer = None
            self.base_optimizer = None
            self.original_step = None
            self.optimizer_origin = None
            self.amp_active = False
            self.raw_calls = 0
            self.raw_returns = 0
            self.violation = None
            self.parameters = ()
            self.before = {}
            self.nonzero = set()
            self.scheduler_epoch = None
            self.saved_rng = None
            self.provenance = ()

        def _bindings(self) -> None:
            _require(self.violation is None, self.violation or "native observer violation")
            _require(trainer.optimizer is self.original_optimizer, "prepared optimizer identity changed")
            _require(_base_optimizer(trainer.optimizer) is self.base_optimizer, "original optimizer changed")
            self.optimizer_origin.check(self.amp_active)
            actual = tuple((name, parameter) for name, parameter in trainer.model.named_parameters()
                           if parameter.requires_grad)
            _require(len(actual) == len(self.parameters) and all(
                left_name == right_name and left is right
                for (left_name, left), (right_name, right) in zip(actual, self.parameters, strict=True)
            ), "trainable parameter binding changed")
            bound = [parameter for group in self.base_optimizer.param_groups for parameter in group["params"]]
            _require(len({id(parameter) for parameter in bound}) == len(bound), "optimizer parameter alias")
            _require({id(parameter) for parameter in bound if parameter.requires_grad}
                     == {id(parameter) for _, parameter in self.parameters}, "foreign optimizer parameters")

        def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            _require(not self.started and args.max_steps == state.max_steps == 2,
                     "unexpected train-begin/horizon")
            _require(args.save_only_model is False and args.fp16 is True,
                     "full-state FP16 native training required")
            _require(state.global_step == (0 if phase == 1 else 1), "unexpected starting global step")
            self.optimizer_origin = _bind_optimizer_origin(trainer)
            self.original_optimizer = trainer.optimizer
            self.base_optimizer = self.optimizer_origin.base
            self.original_step = self.optimizer_origin.raw
            self.parameters = tuple((name, parameter) for name, parameter in trainer.model.named_parameters()
                                    if parameter.requires_grad)
            _require(self.parameters and all("lora_" in name for name, _ in self.parameters),
                     "native LoRA trainables required")
            self._bindings()
            if phase == 2:
                _compare_restored_state(trainer, checkpoint_1)
                self.saved_rng = _load_native_state(checkpoint_1, "rng_state.pth", dependencies)
            self.scheduler_epoch = trainer.lr_scheduler.last_epoch
            self.hooks.append(self.base_optimizer.register_step_pre_hook(self._pre_hook))
            self.hooks.append(self.base_optimizer.register_step_post_hook(self._post_hook))
            self.started = True
            self.boundary = "ready"

        def on_pre_optimizer_step(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            _require(self.started and self.boundary == "ready" and self.updates == 0,
                     "extra/misordered optimizer boundary")
            _require(trainer.accelerator.sync_gradients is True, "not an actual accumulation sync boundary")
            if self.trace_active:
                _require(self.generations >= 1 and (phase == 1 or self.restored_rng),
                         "update before native generation/RNG restore")
                _require(not self.requires_clip_trace or self.native_clip,
                         "native unscale/clip did not return before gradient observation")
            self._bindings()
            self.before = {}
            self.nonzero = set()
            self.raw_calls = self.raw_returns = 0
            for name, parameter in self.parameters:
                gradient = parameter.grad
                _require(bool(dependencies.torch.isfinite(parameter).all()), "nonfinite trainable parameter")
                if gradient is not None:
                    _require(bool(dependencies.torch.isfinite(gradient).all()), "nonfinite observed LoRA gradient")
                    if bool(dependencies.torch.count_nonzero(gradient).item()):
                        self.nonzero.add(name)
                native = self.base_optimizer.state.get(parameter, {})
                self.before[name] = (
                    parameter.detach().cpu().clone(), _snapshot(native, dependencies),
                )
            _require(self.nonzero, "all observed LoRA gradients are zero/missing")
            self.boundary = "pre"

        def _pre_hook(self, optimizer: Any, args: Any, kwargs: Any) -> None:
            _require(optimizer is self.base_optimizer and self.boundary == "pre",
                     "original optimizer step bypassed native pre-boundary")
            self._bindings()
            self.boundary = "step"
            return None

        def _post_hook(self, optimizer: Any, args: Any, kwargs: Any) -> None:
            _require(optimizer is self.base_optimizer and self.boundary == "step",
                     "unexpected original optimizer return")
            self._bindings()
            self.boundary = "post"
            return None

        def on_optimizer_step(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            _require(self.boundary == "post", "missing actual original optimizer step")
            if self.trace_active:
                _require(self.raw_calls == self.raw_returns == 1,
                         "missing original native Adam step normal return")
            _require(not trainer.accelerator.optimizer_step_was_skipped, "native AMP optimizer update skipped")
            self._bindings()
            witnessed = False
            for name, parameter in self.parameters:
                before, native_before = self.before[name]
                _require(bool(dependencies.torch.isfinite(parameter).all()), "nonfinite updated LoRA tensor")
                delta = parameter.detach().cpu() - before
                _require(bool(dependencies.torch.isfinite(delta).all()), "nonfinite native tensor displacement")
                native_after = self.base_optimizer.state.get(parameter, {})
                if name in self.nonzero and bool(dependencies.torch.count_nonzero(delta).item()):
                    old_step = native_before.get("step", 0)
                    new_step = native_after.get("step")
                    if dependencies.torch.is_tensor(old_step):
                        old_step = old_step.item()
                    if dependencies.torch.is_tensor(new_step):
                        new_step = new_step.item()
                    _require(type(new_step) in (float, int) and new_step == old_step + 1,
                             "corresponding native optimizer step state did not advance")
                    _require(not _equal(native_before, native_after, dependencies),
                             "native optimizer state unchanged")
                    _snapshot(native_after, dependencies)
                    witnessed = True
            _require(witnessed, "no same-parameter finite displacement plus native optimizer advance")
            self.updates += 1
            self.boundary = "updated"

        def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            _require(self.violation is None, self.violation or "native observer violation")
            _require(self.boundary == "updated" and self.updates == 1 and state.global_step == phase,
                     "unexpected native update/step order")
            _require(args.max_steps == state.max_steps == 2, "native horizon changed")
            _require(trainer.lr_scheduler.last_epoch == self.scheduler_epoch + 1,
                     "native scheduler did not progress once")
            control.should_save = True
            if phase == 1:
                control.should_training_stop = True
            self.boundary = "complete"

        def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            _require(self.violation is None, self.violation or "native observer violation")
            _require(self.boundary == "complete" and not self.saved, "unexpected/extra native save callback")
            if self.trace_active:
                _require(self.native_save_returned, "callback preceded original TRL save return")
            _check_checkpoint(trainer, Path(args.output_dir) / f"checkpoint-{phase}", phase)
            self.saved = True

        def close(self) -> None:
            for hook in self.hooks:
                hook.remove()
            self.hooks.clear()

    return NativeObserver()


def _code_shape(code: CodeType) -> tuple[Any, ...]:
    constants = tuple(_code_shape(value) if isinstance(value, CodeType) else value
                      for value in code.co_consts)
    return (code.co_code, constants, code.co_names, code.co_varnames,
            code.co_freevars, code.co_cellvars, code.co_argcount,
            code.co_posonlyargcount, code.co_kwonlyargcount, code.co_flags & 0xFFFF,
            code.co_exceptiontable)


def _find_code(code: CodeType, qualname: str) -> CodeType:
    matches = []

    def visit(current: CodeType) -> None:
        if current.co_qualname == qualname:
            matches.append(current)
        for constant in current.co_consts:
            if isinstance(constant, CodeType):
                visit(constant)

    visit(code)
    _require(len(matches) == 1, f"selected source code target missing/ambiguous: {qualname}")
    return matches[0]


def _check_firstparty_sources(request: QualificationRequest) -> None:
    pins = {pin.path: pin for pin in request.source_pins}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename)
        if not path.is_relative_to(_SOURCE):
            continue
        _require(path in pins and path.suffix == ".py", f"loaded first-party source lacks approved pin: {name}")
        pin = pins[path]
        _require(pin.size <= _WIRE_LIMIT, "first-party source exceeds byte bound")
        _check_asset_bytes(path, size=pin.size, sha256=pin.sha256)
        compiled = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        for value in vars(module).values():
            if getattr(value, "__module__", None) != name:
                continue
            code = getattr(value, "__code__", None)
            if isinstance(code, CodeType):
                _require(_code_shape(code) == _code_shape(_find_code(compiled, value.__qualname__)),
                         f"loaded first-party function differs from approved source: {name}.{value.__qualname__}")


def _selected_module(name: str) -> tuple[Any, bytes, CodeType]:
    module = sys.modules.get(name)
    _require(module is not None and getattr(module, "__file__", None), f"selected module not loaded: {name}")
    path = _path(Path(module.__file__))
    _require(path.suffix == ".py" and path.stat().st_size <= 1048576, "unsupported loaded source file")
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == _SELECTED_SOURCES[name],
             f"loaded source differs from reviewed selected representation: {name}")
    # Compile for code comparison only. Never execute or import this compiled text.
    compiled = compile(raw, str(path), "exec", dont_inherit=True)
    return module, raw, compiled


def _selected_method(
    trainer: Any, name: str, module: Any, compiled: CodeType, owner: str,
) -> CodeType:
    method = getattr(trainer, name, None)
    function = getattr(method, "__func__", None)
    _require(function is not None and getattr(method, "__self__", None) is trainer,
             f"native bound method missing: {name}")
    expected = _find_code(compiled, f"{owner}.{name}")
    owner_class = getattr(module, owner)
    original = owner_class.__dict__.get(name)
    _require(original is function and _code_shape(function.__code__) == _code_shape(expected),
             f"loaded method is not selected original code: {name}")
    return function.__code__


def _rewritten_loop(raw: bytes, trainer_raw: bytes) -> CodeType:
    tree = ast.parse(raw)
    trainer_tree = ast.parse(trainer_raw)
    trainer_class = next(node for node in trainer_tree.body
                         if isinstance(node, ast.ClassDef) and node.name == "Trainer")
    method = next(node for node in trainer_class.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_inner_training_loop")
    lines = trainer_raw.decode().splitlines(keepends=True)
    original = "".join(lines[method.lineno - 1:method.end_lineno])
    # Reproduce only the reviewed pure-text substitutions, not Zoo execution.
    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "debug_info"
                           for target in node.targets)
                   and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    debug = [node.value.value for node in sorted(assignments, key=lambda node: node.lineno)
             if 6770 <= node.lineno <= 6830]
    _require(len(debug) == 2, "unknown selected Zoo loop rewrite")
    start = re.search(r"logger\.info\([\"'].+?Running training", original)
    _require(start is not None, "selected Trainer loop logging anchor missing")
    end = original.find("\n\n", start.start())
    _require(end > start.start(), "selected Trainer loop logging end missing")
    old = original[start.start():end]
    indentation = re.search(r"\n([\s\t]{1,})", old)
    _require(indentation is not None, "selected logging indentation missing")
    spaces = indentation.group(0)[1:]

    def indented(value: str) -> str:
        parts = value.split("\n")
        return "\n".join([parts[0]] + [spaces + item[8:] for item in parts[1:]])

    rewritten = original.replace(old, indented(debug[0]))
    rewritten = rewritten.replace("debug_info =", indented(debug[1]), 1)
    front = re.match(r"[\t\s]{1,}", rewritten)
    _require(front is not None, "selected loop indentation missing")
    rewritten = re.sub(r"^" + front.group(0), "", rewritten, flags=re.MULTILINE)
    rewritten = rewritten.replace("train_dataloader = tpu_spmd_dataloader(train_dataloader)",
                                  "raise RuntimeError('Unsloth: TPUs are not yet supported!')")
    rewritten = rewritten.replace("_inner_training_loop", "_fast_inner_training_loop", 1)
    rewritten = rewritten.replace("is_torch_tpu_available()", "False")
    rewritten = rewritten.replace("is_torch_xla_available()", "False")
    return _find_code(compile(rewritten, "<selected-zoo-rewrite>", "exec", dont_inherit=True),
                      "_fast_inner_training_loop")


def _expected_method_codes(trainer: Any) -> Mapping[str, CodeType]:
    from train import grpo_ptc

    _candidate_prerequisites()
    _check_loaded_candidate(trainer, grpo_ptc.training_config(grpo_ptc.TRAINED_ARMS_DEFAULT, 2))
    transformers, trainer_raw, trainer_code = _selected_module("transformers.trainer")
    trl, _, trl_code = _selected_module("trl.trainer.grpo_trainer")
    _, zoo_raw, _ = _selected_module("unsloth_zoo.compiler")
    _selected_module("accelerate.optimizer")
    accelerate, _, accelerate_code = _selected_module("accelerate.accelerator")
    for name in ("clip_grad_norm_", "unscale_gradients", "prepare_optimizer"):
        _selected_method(trainer.accelerator, name, accelerate, accelerate_code, "Accelerator")
    _require(all(cls.__module__.split(".")[0] in {"trl", "transformers", "unsloth", "builtins"}
                 for cls in type(trainer).__mro__), "unknown loaded Trainer MRO provenance")
    expected = {}
    for name in ("train", "_load_rng_state", "_run_epoch", "_clip_grad_norm",
                 "_load_from_checkpoint", "_load_scaler"):
        expected[name] = _selected_method(trainer, name, transformers, trainer_code, "Trainer")
    for name in ("_generate_and_score_completions", "_save_checkpoint",
                  "_load_optimizer_and_scheduler", "_get_train_sampler", "get_train_dataloader"):
        expected[name] = _selected_method(trainer, name, trl, trl_code, "GRPOTrainer")
    method = trainer._inner_training_loop
    function = getattr(method, "__func__", None)
    _require(function is not None and method.__self__ is trainer, "missing loaded native inner loop")
    stock = _find_code(trainer_code, "Trainer._inner_training_loop")
    rewritten = _rewritten_loop(zoo_raw, trainer_raw)
    _require(_code_shape(function.__code__) in (_code_shape(stock), _code_shape(rewritten)),
             "unmapped selected Zoo/Trainer inner-loop code")
    _require(transformers.Trainer.__dict__["_inner_training_loop"] is function,
             "unknown native inner-loop binding")
    expected["_inner_training_loop"] = function.__code__
    return expected


def _assert_method_bindings(trainer: Any, expected: Mapping[str, CodeType]) -> None:
    for name, code in expected.items():
        method = getattr(trainer, name, None)
        _require(getattr(method, "__self__", None) is trainer
                 and getattr(getattr(method, "__func__", None), "__code__", None) is code,
                 f"loaded native method identity changed: {name}")


def _normal_return(frame: Any) -> bool:
    # A profile "return", arg=None also occurs on exception unwind. The actual
    # executing return instruction distinguishes it without wrapping the method.
    instruction = next((item for item in dis.get_instructions(frame.f_code)
                        if item.offset == frame.f_lasti), None)
    return instruction is not None and instruction.opname in {"RETURN_VALUE", "RETURN_CONST"}


def _compare_rng(saved: Mapping[str, Any], dependencies: SimpleNamespace) -> None:
    _require(set(saved) == {"python", "numpy", "cpu", "cuda"}, "unsupported native RNG state")
    _require(dependencies.torch.is_tensor(saved["cuda"]), "native single-device CUDA state required")
    actual = _capture_rng(dependencies)
    _require(_equal(saved["python"], actual["python"], dependencies), "Python RNG restore mismatch")
    _require(_equal(saved["numpy"], actual["numpy"], dependencies), "NumPy RNG restore mismatch")
    _require(_equal(saved["cpu"], actual["cpu"], dependencies), "CPU RNG restore mismatch")
    _require(_equal(saved["cuda"], actual["cuda"], dependencies), "CUDA RNG restore mismatch")


@contextmanager
def _observe_calls(trainer: Any, observer: Any) -> ContextManager[None]:
    expected = _expected_method_codes(trainer)
    required = {"train", "_inner_training_loop", "_load_rng_state",
                "_generate_and_score_completions", "_save_checkpoint"}
    _require(required <= set(expected), "required loaded observer targets missing")
    _assert_method_bindings(trainer, expected)
    observer.provenance = tuple(
        (cls.__module__, cls.__qualname__) for cls in type(trainer).__mro__
    )
    observer.native_save_returned = False
    observer.trace_active = True
    observer.requires_clip_trace = "_clip_grad_norm" in expected
    dependencies = _observer_dependencies()
    previous = sys.getprofile()
    previous_trace = sys.gettrace()
    names = {code: name for name, code in expected.items()}
    _require(len(names) == len(expected), "ambiguous native code targets")
    active = {}
    optimizer_active = {}
    counts = Counter()
    train_active = False
    loop_active = False
    pending_save = False

    def observe(frame: Any, event: str, arg: Any) -> None:
        nonlocal train_active, loop_active, pending_save
        origin = observer.optimizer_origin
        if origin is not None:
            for code, receiver, role in origin.calls:
                if frame.f_code is code and frame.f_locals.get("self") is receiver:
                    if event == "return" and not _normal_return(frame):
                        optimizer_active.pop(id(frame), None)
                        observer.violation = observer.violation or f"native optimizer unwound exceptionally: {role}"
                        if role in {"scaler", "outer"}:
                            observer.amp_active = False
                        return
                    _require(observer.violation is None, observer.violation or "native observer violation")
                    if event == "call":
                        _require(id(frame) not in optimizer_active, "recursive native optimizer call")
                        optimizer_active[id(frame)] = role
                        if role == "scaler":
                            observer.amp_active = True
                        if role == "raw":
                            _require(observer.boundary in {"pre", "step"} and observer.raw_calls == 0,
                                     "unexpected original native Adam step call")
                            origin.check(observer.amp_active)
                            observer.raw_calls += 1
                    elif event == "return":
                        _require(optimizer_active.pop(id(frame), None) == role,
                                 "native optimizer return without call")
                        if role == "raw":
                            observer.raw_returns += 1
                        elif role == "outer":
                            observer.amp_active = False
                            origin.check()
        name = names.get(frame.f_code)
        if name is not None and frame.f_locals.get("self") is trainer:
            # Never raise a second observer error while the primary unwinds.
            if event == "return" and not _normal_return(frame):
                active.pop(id(frame), None)
                observer.violation = observer.violation or f"native observed target unwound exceptionally: {name}"
                if name == "_inner_training_loop":
                    loop_active = False
                elif name == "train":
                    train_active = False
                elif name == "_save_checkpoint":
                    pending_save = False
                return
            _require(observer.violation is None, observer.violation or "native observer violation")
            _assert_method_bindings(trainer, expected)
            if event == "call":
                _require(id(frame) not in active, "recursive native observer target")
                active[id(frame)] = name
                counts[name] += 1
                if name == "train":
                    _require(counts[name] == 1, "extra original train call")
                    train_active = True
                elif name == "_inner_training_loop":
                    _require(train_active and counts[name] == 1, "unexpected original inner loop")
                    loop_active = True
                elif name == "_load_rng_state":
                    _require(observer.phase == 2 and observer.started and train_active and loop_active
                             and counts[name] == 1 and observer.generations == 0,
                             "unexpected native RNG restore call/order")
                    _require(Path(frame.f_locals.get("checkpoint", "")) == observer.checkpoint,
                             "native RNG restore checkpoint differs")
                elif name == "_generate_and_score_completions":
                    _require(train_active and loop_active and observer.started
                             and observer.updates == 0 and counts[name] == 1,
                             "unexpected/extra native generation request")
                    _require(observer.phase == 1 or observer.restored_rng,
                             "resumed generation preceded native normal RNG restore")
                    observer.generations += 1
                elif name == "_clip_grad_norm":
                    _require(observer.started and observer.boundary == "ready" and not observer.native_clip,
                             "unexpected native clipping order")
                elif name == "_save_checkpoint":
                    _require(observer.boundary == "complete" and not pending_save and counts[name] == 1,
                             "unexpected native full save order")
                    pending_save = True
            elif event == "return":
                _require(active.pop(id(frame), None) == name, "native return without call")
                if name == "_load_rng_state":
                    # No chained observer or user code runs before this comparison.
                    try:
                        _compare_rng(observer.saved_rng, dependencies)
                    except ValueError as error:
                        observer.violation = str(error)
                        return
                    observer.restores += 1
                    observer.restored_rng = True
                elif name == "_clip_grad_norm":
                    observer.native_clip = True
                elif name == "_save_checkpoint":
                    _require(pending_save, "native save return without start")
                    observer.native_save_returned = True
                    pending_save = False
                elif name == "_inner_training_loop":
                    loop_active = False
                elif name == "train":
                    train_active = False
        if previous is not None:
            previous(frame, event, arg)

    def profile(frame: Any, event: str, arg: Any) -> None:
        try:
            observe(frame, event, arg)
        except ValueError as error:
            observer.violation = observer.violation or str(error)
            raise

    sys.setprofile(profile)
    try:
        yield
        _require(observer.violation is None, observer.violation or "native observer violation")
        _require(observer.started and observer.optimizer_origin is not None,
                 "missing native optimizer origin observation")
        observer._bindings()
        _assert_method_bindings(trainer, expected)
        _require(counts["train"] == counts["_inner_training_loop"] == 1
                 and observer.updates == 1 and observer.generations == 1
                 and observer.saved and observer.native_save_returned and not active and not optimizer_active,
                 "missing native train/update/save observation")
        _require(observer.phase == 1 or observer.restores == 1, "missing normal native RNG restore")
    finally:
        sys.setprofile(previous)
        # We never install a trace hook, but preserve the preexisting trace too.
        if sys.gettrace() is not previous_trace:
            sys.settrace(previous_trace)
        observer.trace_active = False
        observer.close()


def _candidate_prerequisites() -> None:
    from train import native_runtime

    _require(platform.system() == "Linux" and sys.version_info[:2] == (3, 12),
             "native attempt requires the selected Linux Python 3.12 candidate")
    report = native_runtime.native_runtime_report()
    _require(report["metadata_source"] == "installed", "installed candidate metadata required")
    # Attempt prerequisites are not the permanently unresolved production gates.
    # Do not mutate the report or reinterpret metadata as loaded-runtime proof.
    for category in ("missing", "invalid", "native", "selected", "policy"):
        _require(not report["issues"][category], f"candidate prerequisite failed: {category}")


def _check_loaded_candidate(trainer: Any, config: Mapping[str, Any]) -> None:
    dependencies = _observer_dependencies()
    torch = dependencies.torch
    _require(torch.cuda.is_available() and torch.cuda.device_count() == 1,
             "exactly one visible CUDA device required")
    _require(trainer.args.world_size == 1 and trainer.args.process_index == 0,
             "distributed qualification is unsupported")
    _require(not trainer.is_deepspeed_enabled and not trainer.is_fsdp_enabled
             and not trainer.args.dataloader_persistent_workers and trainer.args.dataloader_num_workers == 0,
             "unsupported distributed/persistent dataloader topology")
    _require(trainer.accelerator.scaler is not None and trainer.accelerator.mixed_precision == "fp16"
             and 0 < trainer.args.max_grad_norm < float("inf"), "original native FP16 unscale/clip required")
    for name, value in config.items():
        _require(getattr(trainer.args, name) == value, f"loaded native configuration differs: {name}")
    _require(trainer.args.fp16 is True and trainer.args.bf16 is False
             and trainer.args.save_only_model is False and trainer.args.push_to_hub is False,
             "native precision/save settings differ")
    model = trainer.accelerator.unwrap_model(trainer.model)
    _require(not getattr(model, "is_loaded_in_4bit", False), "4-bit model refused")
    _require(model.config.max_position_embeddings >= 8192, "loaded model context is too short")
    configs = model.peft_config
    _require(set(configs) == {"default"} and configs["default"].r == configs["default"].lora_alpha == 32,
             "loaded LoRA rank/alpha differs from original settings")
    parameters = [parameter for parameter in model.parameters() if parameter.is_floating_point()]
    _require(parameters and all(parameter.dtype != torch.bfloat16 for parameter in parameters),
             "loaded BF16 model tensors refused")
    _require(any(parameter.dtype == torch.float16 for parameter in parameters),
             "loaded FP16 model tensors missing")
    _native_adapter_state(trainer, dependencies)


def _run_phase(request: QualificationRequest, phase: Literal[1, 2]) -> None:
    from train import grpo_ptc, guards, native_model, native_training, sql_bridge

    _require(type(phase) is int and phase in (1, 2), "invalid native phase")
    _validate_request(request)
    config = grpo_ptc._preflight_invariants(grpo_ptc.TRAINED_ARMS_DEFAULT, guards.REPO_ROOT, 2)
    source = native_model.verify_local_model(request.model_dir, model_revision=native_model.MODEL_REVISION)
    prepared = sql_bridge.prepare_sql_training(request.tasks, request.db_root)
    trainer = native_training._construct_sql_trainer(
        prepared, source, config, output=request.output_dir, max_seq_length=8192,
    )
    checkpoint_1 = request.output_dir / "checkpoint-1" if phase == 2 else None
    observer = _make_callback(trainer, phase, checkpoint_1)
    trainer.add_callback(observer)
    with _observe_calls(trainer, observer):
        _check_sampler(trainer)
        if phase == 1:
            trainer.train()
        else:
            trainer.train(resume_from_checkpoint=str(checkpoint_1))
    _check_checkpoint(trainer, request.output_dir / f"checkpoint-{phase}", phase)
    _output_size(request.output_dir, request.bounds.artifact_bytes)


def _output_size(root: Path, limit: int) -> int:
    _path(root)
    if not root.exists():
        return 0
    _require(root.is_dir(), "native output root is not a directory")
    pending = [(root, 0)]
    count = total = 0
    while pending:
        directory, depth = pending.pop()
        for path in directory.iterdir():
            count += 1
            _require(count <= 1024, "too many native output members")
            info = path.lstat()
            _require(not stat.S_ISLNK(info.st_mode), "linked native output refused")
            if stat.S_ISDIR(info.st_mode):
                _require(depth < 2, "native output nesting exceeds limit")
                pending.append((path, depth + 1))
            else:
                _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "nonregular/hardlinked native output")
                total += info.st_size
                _require(total <= limit, "aggregate native artifact byte limit exceeded")
    return total


def _check_exported_artifacts(request: QualificationRequest, result: OwnedJobResult) -> tuple[Path, Path]:
    _require(type(result) is OwnedJobResult and result.service_handle is not None,
             "external owned-job result required")
    _require(type(result.phase_returncodes) is tuple and len(result.phase_returncodes) == 2
             and all(type(code) is int and code == 0 for code in result.phase_returncodes),
             "both original native phases must have completed successfully")
    _require(result.exported_root == request.output_dir, "external export destination differs")
    root = _path(result.exported_root)
    _require(root.is_dir(), "external export missing")
    _output_size(root, request.bounds.artifact_bytes)
    _require({path.name for path in root.iterdir()} <= {"checkpoint-1", "checkpoint-2", "README.md"},
             "unexpected native export root members")
    dependencies = _observer_dependencies()
    states = []
    adapters = []
    for step in (1, 2):
        checkpoint = root / f"checkpoint-{step}"
        members = _checkpoint_members(checkpoint, request.bounds.artifact_bytes)
        _require({"trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth", "scaler.pt",
                  "adapter_config.json", "adapter_model.safetensors"} <= members,
                 "exported native full checkpoint incomplete")
        state = _json_member(checkpoint, "trainer_state.json")
        _require(type(state.get("global_step")) is int and state["global_step"] == step
                 and type(state.get("max_steps")) is int and state["max_steps"] == 2,
                 "exported native checkpoint step/horizon differs")
        optimizer = _load_native_state(checkpoint, "optimizer.pt", dependencies)
        scheduler = _load_native_state(checkpoint, "scheduler.pt", dependencies)
        rng = _load_native_state(checkpoint, "rng_state.pth", dependencies)
        _require(set(rng) == {"python", "numpy", "cpu", "cuda"}
                 and dependencies.torch.is_tensor(rng["cuda"]), "exported native RNG layout differs")
        scaler = _load_native_state(checkpoint, "scaler.pt", dependencies)
        _require(type(scaler) is dict and set(scaler) == {
            "scale", "growth_factor", "backoff_factor", "growth_interval", "_growth_tracker",
        }, "exported active FP16 scaler state missing/invalid")
        _require(type(scaler["scale"]) in (int, float) and scaler["scale"] > 0
                 and type(scaler["growth_factor"]) in (int, float) and scaler["growth_factor"] > 1
                 and type(scaler["backoff_factor"]) in (int, float) and 0 < scaler["backoff_factor"] < 1
                 and type(scaler["growth_interval"]) is int and scaler["growth_interval"] > 0
                 and type(scaler["_growth_tracker"]) is int and scaler["_growth_tracker"] >= 0,
                 "exported active FP16 scaler values invalid")
        _snapshot(scaler, dependencies)
        if "entropy_ctrl_state.json" in members:
            entropy = _json_member(checkpoint, "entropy_ctrl_state.json")
            _closed(entropy, {"entropy_coef", "last_world_entropy"}, "exported native entropy")
            _snapshot(entropy, dependencies)
        _snapshot(optimizer, dependencies)
        _snapshot(scheduler, dependencies)
        states.append((optimizer, scheduler))
        adapters.append(_load_adapter_state(checkpoint))
    _require(adapters[0].keys() == adapters[1].keys() and adapters[0], "exported native adapter key mismatch")
    _require(not _equal(adapters[0], adapters[1], dependencies), "exported native adapter tensors did not change")
    _snapshot(adapters[0], dependencies)
    _snapshot(adapters[1], dependencies)
    _require(not _equal(states[0][0], states[1][0], dependencies)
             and states[1][1]["last_epoch"] == states[0][1]["last_epoch"] + 1,
             "exported native optimizer/scheduler state did not advance")
    return root / "checkpoint-1", root / "checkpoint-2"


def attempt_sql_qualification(
    request: QualificationRequest, *, controller: QualificationController,
) -> tuple[Path, Path]:
    """Ask one trusted external owner for one attempt; never retry or authorize production."""
    _validate_request(request)
    controller.require_approved(request)
    result = controller.run_once(request)
    return _check_exported_artifacts(request, result)


def _main(argv: list[str]) -> int:
    if not argv:
        return 0
    _require(sys.executable == "/usr/local/bin/python3.12", "private worker interpreter differs")
    if argv == ["--_request", str(_REQUEST_FILE)]:
        return _worker_main(_REQUEST_FILE)
    _require(len(argv) == 4 and argv[0] == "--_phase" and argv[1] in {"1", "2"}
             and argv[2:] == ["--_request", str(_REQUEST_FILE)], "unknown private worker arguments")
    with _REQUEST_FILE.open("rb") as stream:
        document = _decode_worker_transport(stream.read(_WIRE_LIMIT + 1))
    request = _request_from_wire(document)
    phase = int(argv[1])
    _run_phase(request, phase)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
