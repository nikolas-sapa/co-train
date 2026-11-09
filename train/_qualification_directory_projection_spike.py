"""V251 isolated owner, frozen V226/V237 APIs. SOURCEONLY UNRUN.

Only this owner grants runtime read custody. DTOs and wire messages grant none.
Every actual handle has a pre-reserved generation, including failed acquisitions,
intermediate anchors and failed closes. Unknown custody retains the common latch.
SDK work is worker-only. Kernel/provider stalls have no universal return bound.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from decimal import Decimal
import fcntl
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import time
from typing import Any
from weakref import WeakValueDictionary

from train import qualification_engineering_host as original
from train.qualification_engineering_host import (
    AttemptReservation, EngineeringAuthorization, claim_attempt_reservation,
)
from train.qualification_image_plan import candidate_recipe, recipe_sha256
from train.qualification_isolated_contract import (
    APP, SANDBOX, ASSET_LIMIT, CONTROL_LIMIT, FILE_LIMIT, MANIFEST_LIMIT,
    MAX_NS, NS, OUTCOME_LIMIT, REQUEST_LIMIT, RPC_SOURCE_KEY, TOTAL_LIMIT,
    ChildObservation, IsolatedOwnerSpec, JoinedExecution, LaunchDescriptor,
    ManifestEntry, ParentLocal, PreparedInputs, ShutdownSchedule, SourcePin,
    WorkerFDNumbers, byte_layer, canonical, decode_message, digest, encode_launch,
    encode_manifest, encode_message, input_key, integer, require,
)
from train.qualification_isolated_deadline import (
    ALARM_EXIT_CODE, DeadlineExpired, ShutdownLatch, child_argv, initial_gate_alarm_ns, monotonic_ns,
)
from train.qualification_isolated_validation import require_feasible, validation_booking
from train.qualification_modal_host import (
    ResourceConfig, acquire_common_latch, release_common_latch,
)
from train.qualification_owned_stop import OwnedAppStopBinding
from train.qualification_watchdog import TrustedTeardown

ATTEMPT_LIMIT_NS = 1800 * NS
CHUNK = 65536
MEMBER_MODE = PRIVATE_MODE = 0o600
SNAPSHOT_DIR_MODE = 0o700
REQUEST_NAME = "request.json"
MANIFEST_NAME = "isolated-owner-manifest.json"
LAUNCH_NAME = "isolated-owner-launch.json"
OUTCOME_NAME = "isolated-owner-outcome.bin"
JOURNAL_NAME = "isolated-owner-journal.jsonl"
_TOKEN = object()
_WORKER_ONLY_CHILDREN = (ChildObservation("worker", 0, True),)
_ARMED_ROLE_NAMES = frozenset(("controller", "gate"))
_DEPLOYED_ROOT = Path(__file__).absolute().parent.parent
_PREFLIGHTS = WeakValueDictionary()
_OWNERS: dict[int, Any] = {}
_RETAINED_FAILURES: list[Any] = []

# Runtime first-party import closure, including the fixed C program and helper.
# Native training occurs remotely, not in these three local children.
WORKER_SOURCE_KEYS = tuple(sorted((
    "bench/__init__.py", "bench/loader.py", "bench/score.py", "bench/shapes.py",
    "bench/suite.py", "bench/task.py", "ptc/__init__.py", "ptc/metrics.py",
    "ptc/paired.py", "ptc/runtime.py", "ptc/sqlite_safety.py", "train/__init__.py",
    "train/dead_group_probe.py", "train/engineering_budget.py", "train/guards.py",
    "train/modal_app_stop.py", "train/modal_app_stop_launcher.py",
    "train/native_model.py", "train/native_qualification.py",
    "train/qualification_engineering_host.py", "train/qualification_engineering_run.py",
    "train/qualification_file_rpc.py", "train/qualification_image_plan.py",
    "train/qualification_isolated_contract.py", "train/qualification_isolated_deadline.py",
    "train/qualification_isolated_owner.py", "train/qualification_isolated_program.py",
    "train/qualification_isolated_run.py", "train/qualification_isolated_validation.py",
    "train/qualification_isolated_worker.py", "train/qualification_modal_host.py",
    "train/qualification_modal_transport.py", "train/qualification_owned_stop.py",
    "train/qualification_remote_verification.py", "train/qualification_watchdog.py",
    "train/verdict.py",
)))
SDK_REQUIRED_KEYS = tuple(sorted((
    "modal/__init__.py", "modal/app.py", "modal/client.py", "modal/cli/__init__.py",
    "modal/cli/app.py", "modal/_image.py", "modal/_object.py",
    "modal/sandbox/__init__.py", "modal/sandbox/_sandbox.py",
    "modal/_utils/__init__.py", "modal/_utils/async_utils.py",
    "modal/io_streams.py", "modal_proto/__init__.py", "modal_proto/api_pb2.py",
    "modal_version/__init__.py",
)))


def _private(token):
    if token is not _TOKEN:
        raise PermissionError("private owner capability")


def _module_name(key):
    input_key("source", key)
    require(key.endswith(".py"), "Python source module pin")
    parts = key[:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    require(parts and all(p.isidentifier() for p in parts), "module source key")
    return ".".join(parts)


def _absolute(path):
    require(isinstance(path, Path) and path.is_absolute() and ".." not in path.parts
            and "\\" not in str(path) and "\0" not in str(path)
            and len(str(path)) <= 4096, "absolute nontraversing Path")
    return path


def _parts(key):
    require(type(key) is str and 0 < len(key.encode("utf-8")) <= 4096
            and "\\" not in key and "\0" not in key, "relative key")
    result = key.split("/")
    require(len(result) <= 64 and all(p not in {"", ".", ".."}
            and len(p.encode("utf-8")) <= 255 for p in result), "key components")
    return result


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(info, private, expected=None):
    require(stat.S_ISDIR(info.st_mode)
            and info.st_uid in (0, os.getuid()), "owned directory")
    # Ancestors may include a system sticky temporary directory. Final private
    # roots and every export directory must be owner-only, never sticky-shared.
    require(not info.st_mode & 0o022
            or info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX),
            "unsafe writable directory")
    if private:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "private owner700 directory")
    if expected is None:
        return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid
    dev = info.st_dev
    ino = info.st_ino
    mode = info.st_mode
    uid = info.st_uid
    gid = info.st_gid
    return (dev == expected[0]
            and ino == expected[1]
            and mode == expected[2]
            and uid == expected[3]
            and gid == expected[4])


def _regular(info, private):
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_uid in ((os.getuid(),) if private else (0, os.getuid())),
            "owned single-link regular file")
    if private:
        require(stat.S_IMODE(info.st_mode) == 0o600, "private owner600 file")
    return _identity(info)


class CustodyError(RuntimeError):
    def __init__(self, owner, primary=None, errors=(), *, released=False):
        super().__init__("cleanup failed; local resources observed closed" if released
                         else "local custody UNKNOWN; actual resources/latch retained")
        self.owner, self.primary, self.errors = owner, primary, tuple(errors)
        self.released = released


class _Resource(ParentLocal):
    def __init__(self, registry, generation, kind, anchor):
        self.registry, self.generation, self.kind, self.anchor = registry, generation, kind, anchor
        self.handle = None
        self.dependencies = []
        self.live_dependents = 0
        self.inherited_copy = None
        self.is_anchor = False
        self.closed_ns = None
        self.retained_fd = None
        self.attempted = self.closed = False
        self.error = None


class _Registry(ParentLocal):
    def __init__(self):
        self.records = []
        self.primary = None
        self.errors = []
        self.root_anchor = None

    def reserve(self, kind, anchor):
        record = _Resource(self, len(self.records) + 1, kind, anchor)
        self.records.append(record)
        return record

    def assert_record(self, record):
        require(type(record) is _Resource and record.registry is self
                and 0 < record.generation <= len(self.records)
                and self.records[record.generation - 1] is record, "resource generation")

    def attach(self, record, actual):
        self.assert_record(record)
        require(record.handle is None and actual is not None, "actual acquisition once")
        record.handle = actual  # Before fstat/topology/validation/exposure/await.
        if record.kind == "socket":
            record.retained_fd = actual.fileno()
        elif record.kind == "descriptor":
            record.retained_fd = actual
        return actual

    def acquire(self, kind, anchor, operation):
        record = self.reserve(kind, anchor)
        self.attach(record, operation())
        return record

    def wrap_socket(self, record):
        self.assert_record(record)
        require(record.kind == "descriptor" and not record.attempted
                and type(record.handle) is int, "registered inherited socket FD")
        try:
            actual = socket.socket(
                family=socket.AF_UNIX, type=socket.SOCK_STREAM, fileno=record.handle)
        except BaseException as error:
            # A constructor may clear/close its borrowed slot internally before
            # raising. Disposition is UNKNOWN, never a second close attempt.
            record.attempted, record.error = True, error
            self.errors.append(error)
            raise
        record.handle, record.kind = actual, "socket"  # Same OS generation, not a new duplicate.
        require(actual.fileno() == record.retained_fd, "same inherited socket generation")
        return actual

    def link(self, record, parent):
        self.assert_record(record)
        self.assert_record(parent)
        require(parent.generation < record.generation and not record.closed
                and (not parent.closed or parent.kind == "borrowed"),
                "live registered ancestor before descendant")
        record.dependencies.append(parent)
        parent.live_dependents += 1

    def fd(self, anchor, operation, *, parent=None, is_anchor=False):
        record = self.acquire("descriptor", anchor, operation)
        record.is_anchor = is_anchor
        if parent is not None:
            self.link(record, parent)
        if record.handle < 3:
            duplicate = self.acquire("descriptor", anchor, lambda: fcntl.fcntl(
                record.handle, fcntl.F_DUPFD_CLOEXEC, 3))
            duplicate.is_anchor = is_anchor
            if parent is not None:
                self.link(duplicate, parent)
            self.close(record)
            return duplicate
        return record

    def close(self, record, operation=None):
        self.assert_record(record)
        if record.closed or record.handle is None:
            return
        if record.attempted:
            raise CustodyError(self, self.primary, self.errors)
        record.attempted = True
        try:
            if operation is not None:
                operation()
            elif record.kind == "descriptor":
                os.close(record.handle)
            else:
                record.handle.close()
        except BaseException as error:
            record.error = error
            self.errors.append(error)
            raise
        record.closed = True
        record.closed_ns = monotonic_ns()
        for parent in record.dependencies:
            parent.live_dependents -= 1

    def close_all(self, records=None):
        errors = []
        # Direct dependency counts make the 4096-member case linear, while a
        # failed close leaves every actual ancestor pinned.
        for record in reversed(self.records if records is None else records):
            if record.kind in {"process", "reservation"}:
                continue
            if record.live_dependents:
                errors.append(CustodyError(self, self.primary, self.errors))
                continue
            try:
                self.close(record)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise CustodyError(self, self.primary, errors)


class _Anchor(ParentLocal):
    """Actual ancestry retained, with no post-close fstat of recycled numbers."""
    def __init__(self, registry, path, root, pins, *, private, tag=None):
        self.registry, self.path, self._root = registry, path, root
        self.pins, self.private, self.tag = pins, private, tag
        self.children = {}

    @classmethod
    def absolute(cls, registry, path, *, private, create=False, tag=None):
        _absolute(path)
        anchor = registry.root_anchor
        if anchor is None:
            root = registry.fd(tag, lambda: os.open(
                "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW), is_anchor=True)
            root.is_anchor = True
            root_pin = _directory(os.fstat(root.handle), False)
            anchor = cls(registry, Path("/"), root, [(None, None, root, root_pin, False)],
                         private=False, tag=tag)
            registry.root_anchor = anchor
        anchor.check()
        if path == Path("/"):
            _directory(os.fstat(anchor._root.handle), private)
        components = path.parts[1:]
        for index, component in enumerate(components):
            final = index == len(components) - 1
            anchor = anchor.child(component, private=private if final else False,
                                  create=create and final, tag=tag)
        return anchor

    @classmethod
    def borrowed(cls, registry, fd, *, private=False):
        record = registry.reserve("borrowed", None)
        registry.attach(record, fd)
        record.closed = True  # Borrowed from an external owner; never close it.
        pin = _directory(os.fstat(fd), private)
        return cls(registry, Path("/"), record, [(None, None, record, pin, private)],
                   private=private)

    def check(self):
        for parent, name, record, pin, private in self.pins:
            require(record.handle is not None and (
                record.kind == "borrowed" or not record.attempted),
                "ancestor close/identity unknown")
            require(_directory(os.fstat(record.handle), private, expected=pin), "open ancestor identity")
            if parent is not None:
                require(_directory(os.stat(name, dir_fd=parent.handle,
                                           follow_symlinks=False), private, expected=pin),
                        "named ancestor identity")
        require(self._root.kind == "borrowed" or not self._root.attempted,
                "anchor closed")

    def child(self, name, *, private=True, create=False, tag=None):
        require(len(_parts(name)) == 1, "directory basename")
        self.check()
        if name in self.children:
            result = self.children[name]
            if not result._root.closed:
                result.check()  # An UNKNOWN close cannot be bypassed by reopening.
                _directory(os.fstat(result._root.handle), private)
                return result
            del self.children[name]  # A new open gets a fresh registered generation.
        if create:
            os.mkdir(name, 0o700, dir_fd=self._root.handle)
        before = os.stat(name, dir_fd=self._root.handle, follow_symlinks=False)
        record = self.registry.fd(tag, lambda: os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=self._root.handle), parent=self._root, is_anchor=True)
        record.is_anchor = True
        # Register first, THEN validate both open and named objects.
        pin = _directory(os.fstat(record.handle), private)
        require(pin == _directory(before, private), "directory changed at open")
        result = _Anchor(self.registry, self.path / name, record,
                         [*self.pins, (self._root, name, record, pin, private)],
                         private=private, tag=tag)
        result.check()
        self.children[name] = result
        return result

    def parent(self, key, *, private=True, tag=None):
        parts = _parts(key)
        anchor = self
        for component in parts[:-1]:
            anchor = anchor.child(component, private=private, tag=tag)
        return anchor, parts[-1]

    def open_file(self, key, flags, *, private, mode=0o600, tag=None):
        parent, name = self.parent(key, private=private, tag=tag)
        parent.check()
        creating = bool(flags & os.O_CREAT)
        before = None if creating else os.stat(
            name, dir_fd=parent._root.handle, follow_symlinks=False)
        record = self.registry.fd(tag, lambda: os.open(
            name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode,
            dir_fd=parent._root.handle), parent=parent._root)
        opened = os.fstat(record.handle)
        identity = _regular(opened, private)
        if before is not None:
            require(identity == _regular(before, private), "file changed at open")
        result = _File(record, parent, name, identity, private)
        result.check()
        return result


class _File(ParentLocal):
    def __init__(self, record, parent, name, identity, private):
        self.record, self.parent, self.name = record, parent, name
        self.identity, self.private = identity, private

    def check(self):
        self.parent.check()
        require(not self.record.attempted or self.record.closed, "file close unknown")
        named = _regular(os.stat(self.name, dir_fd=self.parent._root.handle,
                                 follow_symlinks=False), self.private)
        require(named == self.identity, "named file identity changed")
        if not self.record.closed:
            require(_regular(os.fstat(self.record.handle), self.private) == self.identity,
                    "open file identity changed")

    def refresh(self):
        require(not self.record.attempted, "closed writable file")
        self.identity = _regular(os.fstat(self.record.handle), self.private)
        self.check()


def _stream_file(file, *, deadline_ns, size, destination=None, retain=False):
    integer(size, FILE_LIMIT)
    if retain:
        integer(size, 4 * 1024**2)
    require(destination is None or type(destination) is _File, "actual snapshot destination")
    require(monotonic_ns() < deadline_ns, "fixed file deadline")
    file.check()
    require(file.identity[6] == size, "actual file size")
    os.lseek(file.record.handle, 0, os.SEEK_SET)
    count, hasher, chunks = 0, hashlib.sha256(), []
    while True:
        file.check()
        require(monotonic_ns() < deadline_ns, "fixed file read deadline")
        block = os.read(file.record.handle, min(CHUNK, size - count + 1))
        file.check()
        require(monotonic_ns() < deadline_ns, "fixed file read deadline")
        if not block:
            break
        count += len(block)
        require(count <= size, "file grew")
        hasher.update(block)
        if destination is not None:
            destination.check()
            _write_all(destination.record.handle, block, deadline_ns)
            destination.refresh()
            require(destination.identity[6] == count, "snapshot chunk size/identity")
        if retain:
            chunks.append(block)
    require(count == size, "short file")
    file.check()
    require(monotonic_ns() < deadline_ns, "fixed file completion deadline")
    return count, hasher.hexdigest(), b"".join(chunks) if retain else None


def _write_all(fd, raw, end_ns):
    for offset in range(0, len(raw), CHUNK):
        view = memoryview(raw)[offset:offset + CHUNK]
        while view:
            require(monotonic_ns() < end_ns, "fixed write deadline")
            count = os.write(fd, view)
            require(count > 0, "short write")
            view = view[count:]
            require(monotonic_ns() < end_ns, "fixed write deadline")


@dataclass(frozen=True)
class _Upload:
    root: str
    key: str
    path: Path
    size: int
    sha256: str


class IsolatedPreflight(ParentLocal):
    def __init__(self, token=None, *, request=None, authorization=None,
                 owner_spec=None, inventory=(), export_root=None, timing=None):
        _private(token)
        self._request, self._authorization, self._spec = request, authorization, owner_spec
        self._inventory, self._export_root, self._timing = inventory, export_root, timing


def _request_metadata(request, native, source_root):
    """Original request checks that do not inspect content, SQLite or a model."""
    from bench.task import SqlTask
    require(type(request.tasks) is tuple and len(request.tasks) == 4,
            "exactly four original fixture tasks")
    for task, (name, _) in zip(request.tasks, native._FIXTURES, strict=True):
        expected = SqlTask(
            name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
            evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
            db_id=name, db_path=str(request.db_root / name / f"{name}.sqlite"),
            tier="simple", tier_source="derived", shape="fixture-select",
            coarse_shape="fixture-select", source="fixture")
        require(type(task) is SqlTask and asdict(task) == asdict(expected),
                "original fixture metadata")
    require(type(request.database_pins) is tuple and len(request.database_pins) == 4
            and all(type(p) is native.FilePin for p in request.database_pins)
            and {p.path for p in request.database_pins} == {Path(t.db_path) for t in request.tasks},
            "exact original database pin metadata")
    require(type(request.source_pins) is tuple and 1 <= len(request.source_pins) <= 512
            and all(type(p) is native.FilePin for p in request.source_pins)
            and type(request.runtime_inventory) is native.FilePin, "original source/runtime pins")
    seen = set()
    for pin in (*request.source_pins, *request.database_pins, request.runtime_inventory):
        _absolute(pin.path)
        integer(pin.size, FILE_LIMIT)
        digest(pin.sha256)
        require(pin.path not in seen, "duplicate original pin")
        seen.add(pin.path)
    require(all(p.path.is_relative_to(source_root) for p in request.source_pins)
            and any(p.path == source_root / "train/native_training.py"
                    and p.sha256 == native._CONSTRUCTION_SHA for p in request.source_pins),
            "frozen original construction source")


def _metadata(request, authorization, spec, uploads, setup_argv, export_root):
    from train import native_qualification as native
    require(type(request) is native.QualificationRequest
            and type(authorization) is EngineeringAuthorization
            and authorization.request is request, "original request/authorization identity")
    require(not authorization.bound, "authorization already bound")
    authorization.require_valid(now_seconds=int(time.time()))
    native._validate_bounds(request.bounds)
    require(authorization.plan.planned_ceiling_usd <= Decimal("25")
            and authorization.plan.total_estimated_gross_usd
                <= authorization.plan.planned_ceiling_usd,
            "gross plan capped at $25; $5 reserve is not launch allowance")
    require(type(spec) is IsolatedOwnerSpec, "exact owner spec")
    original._file_pin(authorization.policy_pin, "policy_pin", native)
    for path in (spec.source_root, spec.sdk_root, spec.private_scratch,
                 spec.evidence_path, spec.interpreter, export_root,
                 request.output_dir, request.db_root, request.model_dir):
        _absolute(path)
    require(spec.source_root == _DEPLOYED_ROOT, "actual deployed repository required")
    _request_metadata(request, native, spec.source_root)
    require(native._request_binding(request) == authorization.request_binding,
            "original request binding drift")
    require(request.output_dir == export_root and export_root.parent != Path("/"),
            "original output equals C export_root, parent separately inherited")
    roots = (spec.source_root, request.db_root, request.model_dir, request.output_dir)
    for index, left in enumerate(roots):
        for right in roots[index + 1:]:
            require(not (left == right or left in right.parents or right in left.parents),
                    "original source/data/model/export overlap")
    require(type(request.image_digest) is str and re.fullmatch(
        r"sha256:[0-9a-f]{64}", request.image_digest) is not None, "original image digest")
    binding = spec.stop_binding
    require(type(binding) is OwnedAppStopBinding
            and binding.interpreter == spec.interpreter
            and binding.source_root == spec.source_root / "train"
            and binding.sdk_root == spec.sdk_root
            and binding.private_scratch == spec.private_scratch, "original binding facts")
    env = binding.environment
    require(set(env) <= {"PATH", "HOME", "LANG", "LC_ALL"}
            and {"PATH", "HOME"} <= set(env)
            and env["PATH"] == f"{spec.interpreter.parent}:/usr/bin:/bin"
            and all(type(v) is str and "\0" not in v for v in env.values())
            and len(json.dumps(env).encode("ascii")) <= 2048, "original restricted environment")
    _absolute(Path(env["HOME"]))
    timing = binding.timing_facts()
    duration = integer(authorization.workload.duration_seconds, 1800, 1)
    require(duration <= request.bounds.lifetime_seconds, "original lifetime cap")
    require_feasible(duration * NS, timing.teardown_ns, timing.arm_ns, ready_pending=True)
    integer(authorization.preparation_seconds, 1800, 1)
    config = spec.resources
    workload = authorization.workload
    require(type(config) is ResourceConfig and type(workload.gpu_count) is int
            and workload.gpu_count == 1
            and original._gpu_label(config.gpu, workload.gpu_count) == authorization.gpu_label,
            "original charged GPU")
    require(type(config.cpu) is tuple and len(config.cpu) == 2
            and all(type(v) is float and math.isfinite(v) and 0 < v <= 2**31 - 1
                    for v in config.cpu)
            and config.cpu[0] <= config.cpu[1]
            and Decimal(str(config.cpu[1])) == Decimal(workload.cpu_cores), "original CPU caps")
    cap = Decimal(workload.ram_gib) * 1024
    require(cap == cap.to_integral_value() and type(config.memory) is tuple
            and len(config.memory) == 2
            and all(type(v) is int and 0 < v <= 2**31 - 1 for v in config.memory)
            and config.memory[0] <= config.memory[1] and Decimal(config.memory[1]) == cap,
            "original memory caps")
    recipe = candidate_recipe()
    require(authorization.image_base_reference == recipe.base_reference
            and authorization.image_recipe_sha256 == recipe_sha256(recipe), "original recipe")
    require(original._setup_argv(setup_argv) == authorization.setup_argv, "original setup argv")
    require(type(spec.worker_source_pins) is tuple
            and all(type(p) is SourcePin for p in spec.worker_source_pins)
            and tuple(p.key for p in spec.worker_source_pins) == WORKER_SOURCE_KEYS,
            "fixed reviewed source closure")
    require(all(p.size <= 4 * 1024**2 for p in spec.worker_source_pins)
            and sum(p.size for p in spec.worker_source_pins) <= 32 * 1024**2,
            "bounded reviewed first-party buffers")
    require(next(p.sha256 for p in spec.worker_source_pins
                 if p.key == "train/modal_app_stop.py") == binding.adapter_sha256,
            "same original adapter pin")
    require(type(spec.sdk_pins) is tuple and 1 <= len(spec.sdk_pins) <= 2048
            and all(type(p) is SourcePin for p in spec.sdk_pins), "SDK source pins")
    require(all(p.size <= 4 * 1024**2 for p in spec.sdk_pins)
            and sum(p.size for p in spec.sdk_pins) <= 32 * 1024**2, "bounded SDK buffers")
    keys = tuple(p.key for p in spec.sdk_pins)
    modules = tuple(_module_name(k) for k in keys)
    require(keys == tuple(sorted(set(keys))) and len(set(modules)) == len(modules)
            and {_module_name(k) for k in SDK_REQUIRED_KEYS} <= set(modules),
            "reviewed raw SDK role coverage")
    require(all(_module_name(k).split(".")[0] in {"modal", "modal_proto", "modal_version"}
                for k in keys), "only original SDK module roots")
    require({_module_name(p.key): p.sha256 for p in spec.sdk_pins} == binding.sdk_pins,
            "original module-name SDK pins versus path pins")
    require(type(uploads) in (tuple, list) and 1 <= len(uploads) <= ASSET_LIMIT,
            "four-root upload count")
    inventory = []
    for item in uploads:
        row = original._upload_entry((item.root, item.key, item.size, item.sha256))
        input_key(item.root, item.key)
        integer(item.size, FILE_LIMIT)
        path = _absolute(item.path)
        if item.root in {"source", "model", "data"}:
            root = {"source": spec.source_root, "model": request.model_dir,
                    "data": request.db_root}[item.root]
            require(path == root / item.key, "approved root/key/path binding")
        # Wheels: exact frozen supplied absolute path, NOT a scratch-root invention.
        inventory.append(_Upload(row[0], row[1], path, row[2], row[3]))
    inventory = tuple(sorted(inventory, key=lambda x: (x.root, x.key)))
    rows = tuple((i.root, i.key, i.size, i.sha256) for i in inventory)
    require(rows == tuple(sorted(authorization.uploads))
            and len({(i.root, i.key) for i in inventory}) == len(inventory),
            "original authorized four-tuples exact coverage")
    require(("source", RPC_SOURCE_KEY) in {(i.root, i.key) for i in inventory}
            and sum(i.size for i in inventory) <= TOTAL_LIMIT, "RPC/aggregate coverage")
    return inventory, timing


def preflight_isolated(request, *, authorization, owner_spec, uploads, setup_argv, export_root):
    inventory, timing = _metadata(
        request, authorization, owner_spec, uploads, setup_argv, export_root)
    result = IsolatedPreflight(
        _TOKEN, request=request, authorization=authorization, owner_spec=owner_spec,
        inventory=inventory, export_root=export_root, timing=timing)
    _PREFLIGHTS[id(result)] = result
    return result


def admit_isolated_owner(preflight):
    require(type(preflight) is IsolatedPreflight
            and _PREFLIGHTS.get(id(preflight)) is preflight, "registered preflight identity")
    # Revalidate retained metadata only. No content/serializer before consumption.
    inventory, timing = _metadata(
        preflight._request, preflight._authorization, preflight._spec,
        preflight._inventory, preflight._authorization.setup_argv, preflight._export_root)
    require(inventory == preflight._inventory and timing == preflight._timing,
            "same frozen preflight inventory/timing")
    del _PREFLIGHTS[id(preflight)]  # Admission cannot replay, even on failure.
    owner = IsolatedOwner(_TOKEN, preflight=preflight)
    acquire_common_latch(owner)
    owner._latch_held = True
    _OWNERS[id(owner)] = owner
    record = owner._registry.reserve("reservation", owner)
    try:
        owner._registry.attach(record, claim_attempt_reservation(preflight._authorization))
        owner._reservation_record = record
        owner._reservation = record.handle
        require(type(owner._reservation) is AttemptReservation, "original reservation")
        owner._reservation_custody = original._custody_for_reservation(owner._reservation)
        require(owner._reservation_custody.authorization is preflight._authorization,
                "actual original claim receipt and authorization")
        # Diagnostic mirror only. Actual generations/anchors belong to the
        # helper-issued receipt, never reconstructed from this numeric slot.
        record.retained_fd = owner._reservation._dir_fd
        owner._reservation.consume()
        require(owner._reservation.consumed and not owner._reservation.closed,
                "actual reservation consumption")
        approved, claimed = preflight._authorization.policy_pin, owner._reservation.policy_pin
        require((claimed.path, claimed.size, claimed.sha256)
                == (approved.path, approved.size, approved.sha256)
                and owner._reservation.request_binding == preflight._authorization.request_binding,
                "original claim binding")
        preflight._authorization._bind_once()
        owner._admitted = True
        return owner
    except BaseException as primary:
        owner._registry.primary = primary
        if record.handle is None:
            owner._claim_failed = True
            owner._reservation_custody = original._custody_for_failure(
                primary, authorization=preflight._authorization)
            receipt = owner._reservation_custody
            if receipt is None or receipt.has_unknown:
                failure = CustodyError(owner, primary, () if receipt is None else receipt.secondary)
                _RETAINED_FAILURES.append(failure)
                raise failure from primary
        try:
            owner.release_joined()
        except BaseException as cleanup:
            failure = CustodyError(owner, primary, (cleanup,))
            _RETAINED_FAILURES.append(failure)
            raise failure from primary
        raise


class PinnedWorkerLaunch(ParentLocal):
    def __init__(self, token=None, *, owner=None, interpreter_size=None):
        _private(token)
        self._owner, self._interpreter_size = owner, interpreter_size
        self._descriptor = None

    def descriptor_for(self, *, request_size, request_sha256, manifest_size, manifest_sha256):
        o = self._owner
        o._assert_owner()
        require(o._launch is self and self._descriptor is None, "registered launch once")
        spec, auth = o._preflight._spec, o._preflight._authorization
        self._descriptor = LaunchDescriptor(
            1, o._session, str(spec.source_root), spec.worker_source_pins,
            str(spec.sdk_root), spec.sdk_pins, self._interpreter_size,
            spec.stop_binding.interpreter_sha256, auth.request_binding,
            request_size, request_sha256, manifest_size, manifest_sha256,
            auth.setup_argv, auth.image_base_reference, auth.image_recipe_sha256,
            spec.resources.gpu, spec.resources.cpu, spec.resources.memory,
            auth.request.output_dir.name, o._attempt_ns, o._timing)
        return self._descriptor


def pin_worker_launch(owner, *, owner_spec):
    require(type(owner) is IsolatedOwner, "actual owner")
    try:
        return _pin_worker_launch(owner, owner_spec=owner_spec)
    except BaseException as error:
        if owner._registry.primary is None:
            owner._registry.primary = error
        raise


def _pin_worker_launch(owner, *, owner_spec):
    require(type(owner) is IsolatedOwner, "actual owner")
    owner._assert_owner()
    require(owner_spec is owner._preflight._spec and not owner._pin_attempted,
            "admitted spec/one launch pin")
    owner._pin_attempted = True
    owner._preparation_check()
    for root, pins in ((owner_spec.source_root, owner_spec.worker_source_pins),
                       (owner_spec.sdk_root, owner_spec.sdk_pins)):
        anchor = _Anchor.absolute(owner._registry, root, private=False)
        owner._pin_anchors.append(anchor)
        for pin in pins:
            file = anchor.open_file(pin.key, os.O_RDONLY, private=False)
            require(not file.identity[2] & 0o022, "reviewed source not writable by others")
            observed = _stream_file(file, deadline_ns=owner._prepare_end_ns, size=pin.size)
            require(observed[:2] == (pin.size, pin.sha256), "actual pinned source bytes")
            owner._registry.close(file.record)
    anchor = _Anchor.absolute(owner._registry, owner_spec.interpreter.parent, private=False)
    owner._pin_anchors.append(anchor)
    file = anchor.open_file(owner_spec.interpreter.name, os.O_RDONLY, private=False)
    require(not file.identity[2] & 0o022 and bool(file.identity[2] & 0o111),
            "trusted executable interpreter")
    size = integer(file.identity[6], 128 * 1024**2, 1)
    observed = _stream_file(file, deadline_ns=owner._prepare_end_ns, size=size)
    require(observed[1] == owner_spec.stop_binding.interpreter_sha256,
            "actual interpreter bytes, never a caller digest bypass")
    owner._registry.close(file.record)
    owner._launch = PinnedWorkerLaunch(_TOKEN, owner=owner, interpreter_size=size)
    return owner._launch


def _retain_writer_fault(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except BaseException as error:
            if self._owner._registry.primary is None:
                self._owner._registry.primary = error
            raise
    return call


class _OwnerPreparationWriter(ParentLocal):
    def __init__(self, token=None, *, owner=None):
        _private(token)
        self._owner, self._entries, self._prepared = owner, {}, None
        self._scratch = self._snapshot = self._export_parent = None

    @_retain_writer_fault
    def initialize(self):
        o = self._owner
        o._preparation_check()
        self._scratch = _Anchor.absolute(o._registry, o._preflight._spec.private_scratch,
                                         private=True)
        self._snapshot = self._scratch.child("snapshot-" + o._session,
                                             private=True, create=True)
        self._export_parent = _Anchor.absolute(
            o._registry, o._preflight._export_root.parent, private=True)

    def _check(self):
        self._owner._preparation_check()
        require(self._owner._writer is self and self._prepared is None, "registered open writer")

    @_retain_writer_fault
    def snapshot_member(self, *, root, key, source_path, size, sha256):
        self._check()
        approved = next((i for i in self._owner._preflight._inventory
                         if (i.root, i.key) == (root, key)), None)
        require(approved is not None and isinstance(source_path, Path)
                and (source_path, size, sha256) == (approved.path, approved.size, approved.sha256)
                and type(size) is int and type(sha256) is str, "approved inventory BEFORE open")
        require((root, key) not in self._entries, "snapshot member once")
        input_key(root, key)
        o = self._owner
        start = len(o._registry.records)
        anchor = _Anchor.absolute(o._registry, approved.path.parent, private=False)
        o._pin_anchors.append(anchor)
        source = anchor.open_file(approved.path.name, os.O_RDONLY, private=False)
        name = secrets.token_hex(32)
        target = self._snapshot.open_file(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                          private=True)
        observed = _stream_file(source, deadline_ns=o._prepare_end_ns, size=size,
                                destination=target)
        require(observed[:2] == (size, sha256), "approved full member hash")
        os.fsync(target.record.handle)
        target.refresh()
        require(target.identity[6] == size, "snapshot full size")
        o._registry.close(source.record)
        o._registry.close(target.record)
        # Original source ancestors have no child users: only the immutable
        # snapshot is inherited. Do not retain O(members*depth) open handles.
        o._registry.close_all(o._registry.records[start:])
        self._check()
        entry = ManifestEntry(root, key, size, sha256, name)
        self._entries[root, key] = entry
        return entry

    @_retain_writer_fault
    def _write(self, anchor, name, raw):
        file = anchor.open_file(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, private=True)
        _write_all(file.record.handle, raw, self._owner._prepare_end_ns)
        os.fsync(file.record.handle)
        file.refresh()
        self._owner._registry.close(file.record)
        return file

    @_retain_writer_fault
    def write_request(self, payload):
        self._check()
        byte_layer(payload, REQUEST_LIMIT)
        require(("request", REQUEST_NAME) not in self._entries, "derived request once")
        require(sum(i.size for i in self._owner._preflight._inventory) + len(payload)
                <= TOTAL_LIMIT, "aggregate INCLUDING request")
        name = secrets.token_hex(32)
        self._write(self._snapshot, name, payload)
        entry = ManifestEntry("request", REQUEST_NAME, len(payload),
                              hashlib.sha256(payload).hexdigest(), name)
        self._entries["request", REQUEST_NAME] = entry
        return entry

    @_retain_writer_fault
    def seal(self, entries, launch):
        self._check()
        o = self._owner
        require(o._launch is not None and launch is o._launch._descriptor,
                "owner's actual launch descriptor")
        ordered = tuple(sorted(self._entries.values(), key=lambda e: (e.root, e.key)))
        require(type(entries) is tuple and len(entries) == len(ordered)
                and all(a is b for a, b in zip(entries, ordered)), "actual registered entries")
        require({(e.root, e.key, e.size, e.sha256) for e in entries if e.root != "request"}
                == {(i.root, i.key, i.size, i.sha256) for i in o._preflight._inventory},
                "exact admitted inventory coverage")
        raw = encode_manifest(entries)
        request = self._entries["request", REQUEST_NAME]
        require((launch.request_size, launch.request_sha256,
                 launch.manifest_size, launch.manifest_sha256)
                == (request.size, request.sha256, len(raw), hashlib.sha256(raw).hexdigest()),
                "registered bytes bound by descriptor")
        self._manifest = self._write(self._scratch, MANIFEST_NAME, raw)
        launch_raw = encode_launch(launch)
        self._launch_file = self._write(self._scratch, LAUNCH_NAME, launch_raw)
        self._prepared = PreparedInputs(
            request.size, request.sha256, len(raw), hashlib.sha256(raw).hexdigest(),
            len(launch_raw), hashlib.sha256(launch_raw).hexdigest(), entries)
        self._facts = (
            request.size, request.sha256, len(raw), hashlib.sha256(raw).hexdigest(),
            len(launch_raw), hashlib.sha256(launch_raw).hexdigest())
        return self._prepared


class ControlLost(RuntimeError):
    pass


async def _pause(seconds):
    await asyncio.sleep(seconds)


class _ParentChannel(ParentLocal):
    def __init__(self, sock, *, session, end_ns, role):
        self._socket, self._session, self._end_ns, self._role = sock, digest(session), end_ns, role
        self._send_seq = self._recv_seq = 0
        self._buffer = bytearray()
        self._closed = self._close_attempted = self._half_attempted = False
        self._early_attempted = False
        self._owner = None
        sock.setblocking(False)

    async def _wait(self, end_ns, *, write=False):
        remaining = end_ns - monotonic_ns()
        if remaining <= 0:
            raise DeadlineExpired("fixed channel cutoff")
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        def ready():
            if not future.done():
                future.set_result(None)
        fd = self._socket.fileno()
        (loop.add_writer if write else loop.add_reader)(fd, ready)
        wake = None
        try:
            if self._owner is not None and self._owner._armed:
                # Wake the SAME receive/send task to inspect both independent
                # stoppers. No detached monitor task and no renewed deadline.
                wake = loop.call_later(min(.01, remaining / NS), ready)
            async with asyncio.timeout(remaining / NS):
                await future
        finally:
            if wake is not None:
                wake.cancel()
            (loop.remove_writer if write else loop.remove_reader)(fd)

    def _encode(self, kind, body):
        require(not self._closed, "channel closed")
        seq = self._send_seq + 1
        payload = encode_message(dict(v=1, session=self._session, seq=seq,
                                      kind=kind, body=body),
                                 session=self._session, seq=seq, allowed=frozenset({kind}))
        self._send_seq = seq  # Consumed BEFORE first byte, including lost writes.
        return payload

    async def send(self, kind, body, *, end_ns):
        payload = memoryview(self._encode(kind, body))
        cutoff = min(end_ns, self._end_ns)
        while payload:
            if self._owner is not None:
                self._owner._monitor_armed()
            if monotonic_ns() >= cutoff:
                raise DeadlineExpired("fixed control write")
            try:
                count = self._socket.send(payload)
            except (BlockingIOError, InterruptedError):
                await self._wait(cutoff, write=True)
                continue
            require(count > 0, "control zero write")
            payload = payload[count:]

    def _extract(self, allowed):
        if len(self._buffer) < 4:
            return None
        size = int.from_bytes(self._buffer[:4], "big")
        require(1 <= size <= CONTROL_LIMIT, "control frame cap")
        if len(self._buffer) < size + 4:
            return None
        frame = bytes(self._buffer[:size + 4])
        del self._buffer[:size + 4]
        seq = self._recv_seq + 1
        message = decode_message(frame, session=self._session, seq=seq, allowed=allowed)
        self._recv_seq = seq
        return message

    def poll_message(self, *, allowed):
        message = self._extract(allowed)
        if message is not None:
            return message
        try:
            block = self._socket.recv(CONTROL_LIMIT + 4 - len(self._buffer))
        except (BlockingIOError, InterruptedError):
            return None
        if not block:
            raise ControlLost("control EOF, including partial frame")
        self._buffer.extend(block)
        return self._extract(allowed)

    async def receive(self, *, allowed, end_ns):
        while True:
            if self._owner is not None:
                self._owner._monitor_armed()
            if monotonic_ns() >= min(end_ns, self._end_ns):
                raise DeadlineExpired("fixed control read")
            message = self.poll_message(allowed=allowed)
            if message is not None:
                return message
            await self._wait(min(end_ns, self._end_ns))

    def check_live(self):
        require(not self._closed and not self._buffer, "independent channel pending/closed")
        try:
            block = self._socket.recv(1, socket.MSG_PEEK)
        except (BlockingIOError, InterruptedError):
            return
        raise ControlLost("independent controller/gate EOF or unexpected traffic")

    def half_close(self):
        if not self._half_attempted:
            self._half_attempted = True
            self._socket.shutdown(socket.SHUT_WR)

    def try_early_stop(self, origin, cutoff):
        if self._early_attempted:
            return
        self._early_attempted = True
        try:
            raw = self._encode("EARLY_STOP", {"origin_ns": origin})
            if monotonic_ns() < cutoff:
                count = self._socket.send(raw)  # ONE nonblocking attempt, no resend.
                if count != len(raw):
                    raise ControlLost("partial EARLY_STOP")
        finally:
            self.half_close()  # Even partial/lost writes must force kernel EOF.

    def try_stop(self, cutoff):
        raw = self._encode("STOP", {})
        if monotonic_ns() < cutoff:
            require(self._socket.send(raw) == len(raw), "partial worker STOP")

    def try_finish(self, cutoff):
        raw = self._encode("FINISH", {})
        if monotonic_ns() < cutoff:
            require(self._socket.send(raw) == len(raw), "partial controller FINISH")

    def close(self):
        if self._closed:
            return
        require(not self._close_attempted, "channel close UNKNOWN, no retry")
        self._close_attempted = True
        self._socket.close()
        self._closed = True


class _Child(ParentLocal):
    def __init__(self, owner, role, record):
        self.owner, self.role, self.record = owner, role, record
        self.process = record.handle
        self.pid = None
        self.pgid = self.sid = None
        self.code = self.reaped_ns = None
        self.wait_error = None
        self.kill_attempted = False

    def topology(self):
        self.pid = integer(self.process.pid, 2**31 - 1, 1)
        self.pgid = os.getpgid(self.pid)
        self.sid = os.getsid(self.pid)
        require(self.pid == self.pgid == self.sid, "actual separate child session")

    def observe(self):
        if self.code is None and self.wait_error is None:
            # Popen.poll() may synthesize returncode 0 on ECHILD. Observe the
            # retained child's actual waitpid status instead, without a thread.
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except InterruptedError:
                return None
            except OSError as error:
                self.wait_error = self.record.error = error
                self.owner._registry.errors.append(error)
                raise
            if pid:
                require(pid == self.pid, "actual retained child wait identity")
                code = os.waitstatus_to_exitcode(status)
                integer(code, 255, -255)
                self.process.returncode = code
                self.code, self.reaped_ns = code, monotonic_ns()
                self.record.attempted = self.record.closed = True
                self.record.closed_ns = self.reaped_ns
        return self.code

    def signal_once(self):
        if self.observe() is not None or self.wait_error is not None or self.kill_attempted:
            return
        self.kill_attempted = True
        require(self.pid == self.pgid == self.sid
                and os.getpgid(self.pid) == self.pgid
                and os.getsid(self.pid) == self.sid, "retained child group identity")
        os.killpg(self.pgid, signal.SIGKILL)


class _RetainedAppEvidence(ParentLocal):
    def __init__(self, token=None, *, owner=None, worker=None, channel=None,
                 permit=None, app_id=None):
        _private(token)
        self.owner, self.worker, self.channel = owner, worker, channel
        self.session, self.permit, self.app_id = owner._session, permit, app_id
        self.stage_attempted = False


class _PreparedDelegatedStop(ParentLocal):
    def __init__(self, token=None, *, evidence=None, teardown=None, schedule=None,
                 command_pin=None):
        _private(token)
        self.evidence, self.teardown, self.schedule = evidence, teardown, schedule
        self.executable = teardown._executable
        self.environment = tuple(teardown._environment)
        self.command_pin = command_pin


def prepare_delegated_teardown(*, evidence, expires_at, schedule):
    require(type(evidence) is _RetainedAppEvidence, "actual retained App evidence")
    o = evidence.owner
    o._assert_owner()
    require(o._evidence is evidence and o._children.get("worker") is evidence.worker
            and o._channels.get("worker") is evidence.channel
            and evidence.session == o._session and o._open_permit == evidence.permit
            and evidence.worker.observe() is None
            and not evidence.stage_attempted and type(schedule) is ShutdownSchedule
            and schedule == ShutdownSchedule.latest(o._end_ns, o._timing)
            and type(evidence.app_id) is str and APP.fullmatch(evidence.app_id),
            "registered worker/channel/session/consumed OPEN evidence")
    require(monotonic_ns() < min(o._prepare_end_ns, o._booking.work_ns),
            "fixed preparation/work deadline before original stage")
    evidence.stage_attempted = True
    binding = o._preflight._spec.stop_binding
    teardown = binding.stage(expected_app_id=evidence.app_id, expires_at=expires_at)
    o._staged_teardown = teardown  # Retain actual return BEFORE validation.
    require(type(teardown) is TrustedTeardown
            and dict(teardown._environment) == binding.environment,
            "original staged command/restricted environment")
    path = _absolute(Path(teardown._executable))
    anchor = _Anchor.absolute(o._registry, path.parent, private=True)
    o._pin_anchors.append(anchor)
    file = anchor.open_file(path.name, os.O_RDONLY, private=False)
    size = integer(file.identity[6], REQUEST_LIMIT, 1)
    observed = _stream_file(file, deadline_ns=o._prepare_end_ns, size=size)
    o._registry.close(file.record)
    return _PreparedDelegatedStop(_TOKEN, evidence=evidence, teardown=teardown,
                                  schedule=schedule, command_pin=(size, observed[1]))


@dataclass(frozen=True)
class ExportEntry:
    """Data ONLY, no descriptor/path/authority aliases."""
    key: str
    kind: str
    size: int

    def __post_init__(self):
        _parts(self.key)
        require(type(self.kind) is str and self.kind in {"file", "directory"}, "export kind")
        integer(self.size, FILE_LIMIT)


class RegisteredReader(ParentLocal):
    def __init__(self, token=None, *, lease=None, file=None):
        _private(token)
        self._lease, self._file = lease, file
        self._generation = file.record.generation

    def _check(self):
        self._lease._check()
        registry = self._lease._owner._registry
        registry.assert_record(self._file.record)
        require(self._generation == self._file.record.generation
                and self._lease._reader_ids.get(id(self)) is self, "registered reader generation")

    async def read(self, maximum):
        integer(maximum, CHUNK, 1)
        await self._lease.checkpoint()
        self._check()
        require(not self._file.record.attempted, "closed reader")
        self._file.check()
        raw = os.read(self._file.record.handle, maximum)
        self._check()
        self._file.check()
        await self._lease.checkpoint()
        return raw

    async def check_identity(self):
        await self._lease.checkpoint()
        self._check()
        self._file.check()  # After data close: retained named pin/ancestors only.
        await self._lease.checkpoint()

    def close(self):
        # Cleanup must remain possible after read expiry/cancellation. Never a
        # renewed read grant; C cutoff failure is retained by the owner.
        o = self._lease._owner
        o._registry.assert_record(self._file.record)
        require(self._lease._reader_ids.get(id(self)) is self, "registered reader close")
        if self._file.record.closed:
            return
        o._registry.close(self._file.record)
        if self._file.record.closed_ns >= o._booking.close_ns:
            o._validation_close_late = True
            raise DeadlineExpired("reader close past fixed C")


class ParentReadLease(ParentLocal):
    def __init__(self, token=None, *, owner=None, registration=None, execution=None):
        _private(token)
        self._owner, self._registration, self._execution = owner, registration, execution
        self._generation = owner._lease_generation
        self._readers = []
        self._reader_ids = {}
        self._records_start = len(owner._registry.records)
        self._inventory_anchors = []

    @property
    def end_ns(self):
        self._check()
        return self._owner._end_ns

    @property
    def read_deadline_ns(self):
        self._check()
        return self._owner._booking.read_ns

    @property
    def worker_execution(self):
        self._check()
        return self._execution

    def _check(self):
        o = self._owner
        o._assert_parent_read_lease(self, request=o._preflight._request,
                                    prepared=o._inputs, export_root=o._preflight._export_root)

    async def checkpoint(self):
        self._check()
        try:
            await _pause(0)
        except BaseException:
            self._owner._invalidate_lease()
            raise
        self._check()

    def _reader(self, anchor, key, *, outcome=False):
        self._check()
        file = anchor.open_file(key, os.O_RDONLY, private=True, tag=self)
        if outcome:
            expected = self._owner._outcome
            require(file.identity[:2] == expected.identity[:2]
                    and file.identity[6] == self._execution.outcome_size,
                    "actual matching outcome identity/size")
        reader = RegisteredReader(_TOKEN, lease=self, file=file)
        self._readers.append(reader)
        self._reader_ids[id(reader)] = reader
        self._check()
        return reader

    def open_outcome(self):
        return self._reader(self._owner._writer._scratch, OUTCOME_NAME, outcome=True)

    def open_export(self, key):
        _parts(key)
        require(len(key.split("/")) - 1 <= 32, "original export depth")
        return self._reader(self._owner._export_anchor, key)

    async def export_inventory(self):
        self._check()
        rows = []
        async def walk(anchor, prefix, depth):
            require(depth <= 32, "original export depth")
            await self.checkpoint()
            record = self._owner._registry.acquire(
                "iterator", self, lambda: os.scandir(anchor._root.handle))
            self._owner._registry.link(record, anchor._root)
            try:
                while True:
                    await self.checkpoint()
                    try:
                        entry = next(record.handle)
                    except StopIteration:
                        break
                    key = prefix + entry.name
                    _parts(key)
                    info = entry.stat(follow_symlinks=False)
                    require(len(rows) < 20000 + 4, "original directory entry cap")
                    if stat.S_ISDIR(info.st_mode):
                        child = anchor.child(entry.name, private=True, tag=self)
                        self._inventory_anchors.append(child)
                        rows.append(ExportEntry(key, "directory", 0))
                        await self.checkpoint()
                        await walk(child, key + "/", depth + 1)
                    else:
                        _regular(info, True)
                        rows.append(ExportEntry(key, "file", integer(info.st_size, FILE_LIMIT)))
                    await self.checkpoint()
                anchor.check()
            finally:
                self._owner._registry.close(record)
                if monotonic_ns() >= self._owner._booking.close_ns:
                    self._owner._validation_close_late = True
                    raise DeadlineExpired("iterator close past C")
        await walk(self._owner._export_anchor, "", 0)
        await self.checkpoint()
        return tuple(rows)


def _spawn_child(*, argv, role, lease_ns, pass_fds, environment, cwd):
    require(role in {"worker", "controller", "gate"}, "fixed child role")
    integer(lease_ns, minimum=1)
    return subprocess.Popen(
        argv, pass_fds=pass_fds, close_fds=True, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=environment, cwd=cwd, restore_signals=True)


class IsolatedOwner(ParentLocal):
    def __init__(self, token=None, *, preflight=None):
        _private(token)
        self._preflight = preflight
        self._registry = _Registry()
        self._start_ns = monotonic_ns()  # Includes claim and every preparation effect.
        self._attempt_ns = preflight._authorization.workload.duration_seconds * NS
        self._end_ns = integer(self._start_ns + self._attempt_ns, minimum=1)
        self._timing = preflight._timing
        self._prepare_end_ns = min(
            self._end_ns, self._start_ns + preflight._authorization.preparation_seconds * NS)
        self._booking = validation_booking(self._end_ns, self._timing.teardown_ns)
        self._shutdown = ShutdownLatch(end_ns=self._end_ns, timing=self._timing)
        self._session = secrets.token_hex(32)
        self._admitted = self._latch_held = self._released = False
        self._reservation = self._reservation_record = None
        self._reservation_custody = None
        self._claim_failed = False
        self._reservation_failure = None
        self._staged_teardown = None
        self._writer = self._inputs = self._launch = None
        self._pin_attempted = self._run_started = self._running = False
        self._pin_anchors, self._children, self._channels = [], {}, {}
        self._channel_records, self._runtime_records = {}, []
        self._armed = set()
        self._open_permit = self._create_permit = self._evidence = None
        self._app_id = self._sandbox_id = self._outcome_facts = None
        self._outcome = self._export_anchor = self._registration = self._lease = None
        self._lease_generation = 0
        self._worker_execution = self._validated = self._execution = None
        self._published = self._validation_close_late = False
        self._validation_closed = False
        self._early_attempted = self._worker_stop_attempted = self._controller_finished = False
        self._trigger_observed = False
        self._lifecycle_errors = []
        self._missed_cutoffs = set()

    def _assert_owner(self):
        require(_OWNERS.get(id(self)) is self and self._admitted
                and self._latch_held and not self._released, "registered admitted owner")

    def _preparation_check(self):
        self._assert_owner()
        require(monotonic_ns() < self._prepare_end_ns and not self._run_started,
                "fixed preparation deadline/state")
        require(self._registry.primary is None and not self._registry.errors,
                "preparation fault is terminal, never another attempt")
        self._preflight._authorization.require_valid(now_seconds=int(time.time()))
        require_feasible(max(0, self._end_ns - monotonic_ns()), self._timing.teardown_ns,
                         self._timing.arm_ns, ready_pending=True)

    def preparation_writer(self):
        self._preparation_check()
        require(self._writer is None, "one preparation writer")
        self._writer = _OwnerPreparationWriter(_TOKEN, owner=self)
        self._writer.initialize()  # Owner already retains partly initialized writer.
        return self._writer

    def seal_inputs(self, prepared, launch):
        self._preparation_check()
        require(self._inputs is None and self._writer is not None
                and self._writer._prepared is prepared and type(prepared) is PreparedInputs
                and self._launch is launch and type(launch) is PinnedWorkerLaunch
                and launch._owner is self and launch._descriptor is not None,
                "identical owner's writer/prepared/launch seal")
        require((prepared.request_size, prepared.request_sha256,
                 prepared.manifest_size, prepared.manifest_sha256,
                 prepared.launch_size, prepared.launch_sha256) == self._writer._facts,
                "same writer buffers/digests")
        self._inputs = prepared

    def register_parent_validation(self, *, request, prepared, export_root):
        self._preparation_check()
        require(self._registration is None and prepared is not None
                and prepared is self._inputs and request is self._preflight._request
                and export_root is self._preflight._export_root, "exact validation registration once")
        self._writer._export_parent.check()
        from train.qualification_isolated_run import _make_parent_validator
        self._registration = _make_parent_validator(self, request, prepared, export_root)

    def _assert_parent_read_lease(self, lease, *, request, prepared, export_root):
        self._assert_owner()
        require(type(lease) is ParentReadLease and self._lease is lease
                and lease._owner is self and lease._registration is self._registration
                and self._registration is not None
                and self._registration.owner is self
                and self._registration.request is request is self._preflight._request
                and self._registration.prepared is prepared is self._inputs
                and self._registration.export_root is export_root is self._preflight._export_root
                and lease._generation == self._lease_generation
                and lease._execution is self._worker_execution
                and self._worker_execution is not None and not self._shutdown.armed
                and self._running and monotonic_ns() < self._booking.read_ns,
                "active registered lease/generation/deadline")
        worker = self._children["worker"]
        require(worker.code == 0 and worker.reaped_ns <= self._booking.worker_reap_ns
                and self._worker_execution.children == _WORKER_ONLY_CHILDREN
                and self._outcome_facts == (self._worker_execution.outcome_size,
                                            self._worker_execution.outcome_sha256),
                "actual matching worker-only proof")
        self._independent_live()

    def _independent_live(self):
        require(self._armed == _ARMED_ROLE_NAMES, "both actual ARM acknowledgements")
        self._monitor_armed()

    def _monitor_armed(self):
        require(not self._shutdown.armed, "independent monitoring after shutdown")
        for role in ("controller", "gate"):
            if role in self._armed:
                require(self._children[role].observe() is None, "independent child died")
                require(self._children[role].wait_error is None, "independent reap unknown")
                self._channels[role].check_live()

    def _invalidate_lease(self):
        if not self._shutdown.armed:
            self._shutdown.request_stop(monotonic_ns())
            self._lease_generation += 1

    def _pair(self):
        left = self._registry.reserve("socket", self)
        right = self._registry.reserve("socket", self)
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._registry.attach(left, a)
        self._registry.attach(right, b)
        self._runtime_records.extend((left, right))
        return left, right

    def _socket_fd(self, record):
        if record.handle.fileno() >= 3:
            return record.handle.fileno()
        if record.inherited_copy is None:
            record.inherited_copy = self._registry.fd(self, lambda: fcntl.fcntl(
                record.handle.fileno(), fcntl.F_DUPFD_CLOEXEC, 3))
            self._runtime_records.append(record.inherited_copy)
        return record.inherited_copy.handle

    def _close_child_socket_copy(self, record):
        records = [record]
        if record.inherited_copy is not None:
            records.append(record.inherited_copy)
        self._registry.close_all(records)  # Each actual copy, even if another close fails.

    def _channel(self, role, record):
        channel = _ParentChannel(record.handle, session=self._session,
                                 end_ns=self._end_ns, role=role)
        channel._owner = self
        self._channels[role], self._channel_records[role] = channel, record
        return channel

    def _spawn(self, role, *, lease, facts, fds):
        spec = self._preflight._spec
        key = ("train/qualification_isolated_worker.py" if role == "worker"
               else "train/qualification_isolated_deadline.py")
        pin = next(p for p in spec.worker_source_pins if p.key == key)
        argv = child_argv(
            interpreter=str(spec.interpreter), lease_ns=lease,
            entry_path=str(spec.source_root / key), entry_sha256=pin.sha256,
            entry_size=pin.size, source_root=str(spec.source_root), role="--" + role,
            source_pins=spec.worker_source_pins, facts=facts)
        if role == "worker":
            require_feasible(max(0, self._end_ns - monotonic_ns()), self._timing.teardown_ns,
                             self._timing.arm_ns, ready_pending=True)
            require(monotonic_ns() < self._prepare_end_ns, "preparation before worker birth")
        else:
            require(monotonic_ns() < self._arm_end_ns, "stopper birth within fixed arm/preparation")
        record = self._registry.reserve("process", self)
        self._registry.attach(record, _spawn_child(
            argv=argv, role=role, lease_ns=lease, pass_fds=tuple(fds),
            environment=spec.stop_binding.environment, cwd=str(spec.private_scratch)))
        child = _Child(self, role, record)
        self._children[role] = child  # Retain Popen BEFORE topology checks.
        child.topology()
        return child

    def _allocate_worker(self):
        w = self._writer
        parent, child = self._pair()
        self._channel("worker", parent)
        request = next(e for e in self._inputs.entries if e.root == "request")
        files = [
            w._snapshot.open_file(request.snapshot_key, os.O_RDONLY, private=True),
            w._scratch.open_file(LAUNCH_NAME, os.O_RDONLY, private=True),
            w._scratch.open_file(MANIFEST_NAME, os.O_RDONLY, private=True),
        ]
        self._outcome = w._scratch.open_file(
            OUTCOME_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL, private=True)
        self._runtime_records.extend(f.record for f in files)
        self._runtime_records.append(self._outcome.record)
        numbers = WorkerFDNumbers(
            self._socket_fd(child), *(f.record.handle for f in files),
            w._snapshot._root.handle, self._outcome.record.handle,
            w._export_parent._root.handle)
        self._worker_numbers, self._worker_child_end = numbers, child
        return numbers

    def _record_identity(self, kind, identity):
        try:
            self._reservation.record_identity(kind, identity)
        except BaseException as error:
            # Keep the primary and actual helper receipt. Only its registered
            # generation states can prove safe failure-only cleanup.
            self._reservation_failure = error
            raise

    async def _dispatch(self):
        require_feasible(max(0, self._end_ns - monotonic_ns()), self._timing.teardown_ns,
                         self._timing.arm_ns, ready_pending=True)
        numbers = self._allocate_worker()
        facts = tuple(x for k, v in numbers.__dict__.items() for x in ("--" + k, str(v)))
        worker = self._spawn("worker", lease=self._end_ns,
                             facts=("--lease", str(self._end_ns), *facts),
                             fds=tuple(numbers.__dict__.values()))
        self._close_child_socket_copy(self._worker_child_end)
        channel = self._channels["worker"]
        ready = await channel.receive(allowed=frozenset({"READY"}),
                                      end_ns=min(monotonic_ns() + 2 * NS, self._prepare_end_ns))
        require(ready["body"] == dict(request_sha256=self._inputs.request_sha256,
                manifest_sha256=self._inputs.manifest_sha256,
                launch_sha256=self._inputs.launch_sha256), "actual READY sealed facts")
        require_feasible(max(0, self._end_ns - monotonic_ns()), self._timing.teardown_ns,
                         self._timing.arm_ns, ready_pending=False)
        require(worker.observe() is None, "worker live before OPEN")
        self._open_permit = secrets.token_hex(32)  # Consumed before any OPEN bytes.
        open_cutoff = min(monotonic_ns() + 2 * NS, self._prepare_end_ns,
                          self._booking.work_ns)
        await channel.send("OPEN", dict(permit=self._open_permit, end_ns=self._end_ns),
                           end_ns=open_cutoff)
        message = await channel.receive(allowed=frozenset({"APP_RETAINED"}), end_ns=open_cutoff)
        require(message["body"]["permit"] == self._open_permit
                and worker.observe() is None, "expected actual APP_RETAINED")
        self._app_id = message["body"]["app_id"]
        self._evidence = _RetainedAppEvidence(
            _TOKEN, owner=self, worker=worker, channel=channel,
            permit=self._open_permit, app_id=self._app_id)
        self._record_identity("app", self._app_id)
        schedule = ShutdownSchedule.latest(self._end_ns, self._timing)
        prepared = prepare_delegated_teardown(
            evidence=self._evidence, expires_at=time.time() + (
                self._end_ns - monotonic_ns()) / NS, schedule=schedule)
        self._prepared_stop = prepared
        self._spawn_stoppers(prepared)
        await self._arm_stoppers()
        self._independent_live()
        self._create_permit = secrets.token_hex(32)
        await channel.send("CREATE", dict(permit=self._create_permit, end_ns=self._end_ns),
                           end_ns=self._booking.work_ns)
        message = await channel.receive(allowed=frozenset({"SANDBOX_RETAINED"}),
                                        end_ns=self._booking.work_ns)
        require(message["body"]["permit"] == self._create_permit, "one CREATE ACK")
        self._sandbox_id = message["body"]["sandbox_id"]
        self._record_identity("sandbox", self._sandbox_id)
        message = await channel.receive(allowed=frozenset({"OUTCOME"}),
                                        end_ns=self._booking.worker_export_ns)
        self._outcome_facts = (message["body"]["size"], message["body"]["sha256"])
        await channel.receive(allowed=frozenset({"FINISH"}), end_ns=self._booking.worker_reap_ns)
        while worker.observe() is None:
            self._independent_live()
            if monotonic_ns() >= self._booking.worker_reap_ns:
                raise DeadlineExpired("actual clean worker reap by R")
            await _pause(min(.01, (self._booking.worker_reap_ns - monotonic_ns()) / NS))
        require(worker.code == 0 and worker.reaped_ns <= self._booking.worker_reap_ns,
                "clean observed worker wait0 by R")
        self._outcome.refresh()
        require(self._outcome.identity[6] == self._outcome_facts[0], "matching actual OUTCOME size")
        self._worker_execution = JoinedExecution(
            (ChildObservation("worker", worker.code, True),), self._app_id, self._sandbox_id,
            *self._outcome_facts, "NOT_EXECUTED", ())
        self._independent_live()
        require(monotonic_ns() <= self._booking.worker_reap_ns, "lease creation by R")
        self._export_anchor = self._writer._export_parent.child(
            self._launch._descriptor.export_name, private=True)
        self._lease_generation += 1
        self._lease = ParentReadLease(
            _TOKEN, owner=self, registration=self._registration, execution=self._worker_execution)
        require(monotonic_ns() <= self._booking.worker_reap_ns, "actual acquired lease by R")
        data = await self._registration.validate(self._lease)  # Fixed C, directly awaited here.
        self._assert_parent_read_lease(self._lease, request=self._preflight._request,
                                       prepared=self._inputs, export_root=self._preflight._export_root)
        from train.qualification_isolated_run import _ValidatedParentData
        from train.qualification_engineering_run import EngineeringRunOutcome as OriginalOutcome
        require(type(data) is _ValidatedParentData and data.owner is self
                and data.request is self._preflight._request and data.prepared is self._inputs
                and data.export_root is self._preflight._export_root and data.lease is self._lease
                and data.worker_execution is self._worker_execution
                and type(data.original) is OriginalOutcome,
                "exact C type and registration/lease/proof links")
        self._close_validation()
        require(monotonic_ns() < self._booking.seal_ns
                and not self._validation_close_late, "validated data sealed by fixed P")
        self._validated = data

    def _spawn_stoppers(self, prepared):
        require(monotonic_ns() < min(self._prepare_end_ns, self._booking.work_ns),
                "fixed preparation before stopper births")
        cp, cc = self._pair()
        gp, gc = self._pair()
        trigger_controller, trigger_gate = self._pair()
        self._channel("controller", cp)
        self._channel("gate", gp)
        journal = self._writer._scratch.open_file(
            JOURNAL_NAME, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL, private=True)
        self._runtime_records.append(journal.record)
        self._arm_end_ns = min(monotonic_ns() + self._timing.arm_ns,
                               self._booking.work_ns, self._prepare_end_ns)
        common = ("--session", self._session, "--end", str(self._end_ns),
                  "--teardown", str(self._timing.teardown_ns),
                  "--arm-end", str(self._arm_end_ns),
                  "--app", self._app_id, "--journal", str(journal.record.handle))
        self._spawn("controller", lease=self._end_ns,
                    facts=("--control", str(self._socket_fd(cc)),
                           "--trigger", str(self._socket_fd(trigger_controller)), *common),
                    fds=(self._socket_fd(cc), self._socket_fd(trigger_controller), journal.record.handle))
        self._close_child_socket_copy(cc)
        self._close_child_socket_copy(trigger_controller)  # NO parent trigger writer.
        alarm = initial_gate_alarm_ns(self._booking.latest_origin_ns, self._timing.teardown_ns)
        self._spawn("gate", lease=alarm,
                    facts=("--control", str(self._socket_fd(gc)),
                           "--trigger", str(self._socket_fd(trigger_gate)), *common,
                           "--executable", prepared.executable,
                           "--command-size", str(prepared.command_pin[0]),
                           "--command-sha256", prepared.command_pin[1],
                           "--cwd", str(self._preflight._spec.private_scratch),
                           "--environment", json.dumps(dict(prepared.environment),
                                                       sort_keys=True, separators=(",", ":"))),
                    fds=(self._socket_fd(gc), self._socket_fd(trigger_gate), journal.record.handle))
        self._close_child_socket_copy(gc)
        self._close_child_socket_copy(trigger_gate)

    async def _arm_stoppers(self):
        cutoff = self._arm_end_ns  # Includes both child births, never renewed.
        for role in ("controller", "gate"):
            permit = secrets.token_hex(32)
            body = dict(permit=permit, end_ns=self._end_ns,
                        origin_ns=self._booking.latest_origin_ns,
                        teardown_ns=self._timing.teardown_ns, app_id=self._app_id)
            channel = self._channels[role]
            await channel.send("ARM", body, end_ns=cutoff)
            message = await channel.receive(allowed=frozenset({"ARMED"}), end_ns=cutoff)
            require(message["body"]["permit"] == permit
                    and self._children[role].observe() is None
                    and monotonic_ns() < cutoff, "actual ARM ACK/liveness within binding arm")
            self._armed.add(role)
        self._independent_live()
        require(monotonic_ns() < cutoff, "both actual ARM/liveness checks within one budget")

    def _close_validation(self):
        lease = self._lease
        if lease is None or self._validation_closed:
            return
        errors = []
        for reader in lease._readers:
            try:
                reader.close()
            except BaseException as error:
                errors.append(error)
        # Intermediate descendants only. Top export/outcome anchors are NOT
        # lease-tagged and remain held through publication and release.
        records = [r for r in self._registry.records if r.anchor is lease]
        try:
            self._registry.close_all(records)
        except BaseException as error:
            errors.append(error)
        if any(r.handle is not None and (
                not r.closed or r.closed_ns is None or r.closed_ns >= self._booking.close_ns)
               for r in records):
            self._validation_close_late = True
            errors.append(DeadlineExpired("all reader/intermediate closes by C"))
        if errors:
            raise CustodyError(self, self._registry.primary, errors)
        self._validation_closed = True

    async def run_once(self):
        self._assert_owner()
        require(self._inputs is not None and self._registration is not None
                and not self._run_started, "sealed registered run_once before any child")
        self._preparation_check()
        self._run_started = self._running = True
        primary = None
        try:
            await self._dispatch()
        except BaseException as error:
            primary = error
            self._registry.primary = error
        self._invalidate_lease()
        await self._shutdown_join()  # Same task, cancellation-resistant, no detached owner.
        self._running = False
        if primary is None:
            primary = self._registry.primary
        try:
            self._close_validation()
        except BaseException as error:
            self._lifecycle_errors.append(error)
        # Parent resource copies cannot be dropped while any admitted user is unknown.
        if all(c.code is not None for c in self._children.values()):
            self._close_runtime()
        else:
            failure = CustodyError(self, primary, self._lifecycle_errors)
            _RETAINED_FAILURES.append(failure)
            raise failure from primary
        if primary is not None:
            if self._lifecycle_errors:
                failure = CustodyError(self, primary, self._lifecycle_errors)
                _RETAINED_FAILURES.append(failure)
                raise failure from primary
            raise primary
        if self._lifecycle_errors:
            failure = CustodyError(self, primary, self._lifecycle_errors)
            self._registry.primary = failure
            _RETAINED_FAILURES.append(failure)
            raise failure
        if (self._children.get("controller") is not None
                and self._children["controller"].code != 0) or (
                self._children.get("gate") is not None
                and self._children["gate"].code > 0
                and self._children["gate"].code != ALARM_EXIT_CODE):
            failure = RuntimeError("stopper failure, actual child statuses retained by owner")
            self._registry.primary = failure
            raise failure
        require(self._validated is not None
                and set(self._children) == {"worker", "controller", "gate"},
                "normal result requires sealed C data and all three clean local joins/closes")
        gate = self._children["gate"]
        stop_command = "KILLED" if gate.code < 0 or gate.code == ALARM_EXIT_CODE else "EXITED"
        self._execution = JoinedExecution(
            tuple(ChildObservation(role, self._children[role].code, True)
                  for role in ("worker", "controller", "gate")),
            self._app_id, self._sandbox_id, *self._outcome_facts, stop_command, ())
        return self._execution

    async def _shutdown_join(self):
        cutoffs = self._shutdown.cutoffs()
        while True:
            try:
                self._shutdown_step(cutoffs)
                if all(c.code is not None for c in self._children.values()):
                    return
                now = monotonic_ns()
                if now >= cutoffs[6]:
                    return  # UNKNOWN objects retained. Never manufacture reap codes.
                await _pause(min(.01, max(0, cutoffs[6] - now) / NS))
            except asyncio.CancelledError as error:
                if self._registry.primary is None:
                    self._registry.primary = error
                # Absorb any number of deliveries, not only the first three.
                task = asyncio.current_task()
                if task is not None:
                    task.uncancel()
            except BaseException as error:
                self._lifecycle_errors.append(error)
                # Independent operations live in _shutdown_step's own catches.
                # A clock/scheduler failure cannot justify killing the gate early.
                return

    def _cleanup_call(self, operation):
        try:
            return operation()
        except BaseException as error:
            self._lifecycle_errors.append(error)
            return None

    def _shutdown_step(self, cutoffs):
        origin = self._shutdown.schedule().origin_ns
        if not self._early_attempted:
            self._early_attempted = True
            for role in ("controller", "gate"):
                channel = self._channels.get(role)
                if channel is not None:
                    self._cleanup_call(lambda channel=channel:
                                       channel.try_early_stop(origin, cutoffs[0]))
                    # Also unconditional when an injected/failed encoder/send
                    # raises before try_early_stop's own finally.
                    self._cleanup_call(channel.half_close)
        worker = self._children.get("worker")
        if worker is not None and worker.code is None and not self._worker_stop_attempted:
            self._worker_stop_attempted = True
            self._cleanup_call(lambda: self._channels["worker"].try_stop(cutoffs[0]))
        for child in self._children.values():
            self._cleanup_call(child.observe)
        controller = self._children.get("controller")
        channel = self._channels.get("controller")
        if controller is not None and controller.code is None and channel is not None:
            if not self._trigger_observed:
                try:
                    self._trigger_observed = channel.poll_message(
                        allowed=frozenset({"STOP"})) is not None
                except ControlLost:
                    pass  # Normal controller exit can precede its final frame.
                except BaseException as error:
                    self._lifecycle_errors.append(error)
        now = monotonic_ns()
        if now >= cutoffs[0]:
            if worker is not None:
                self._cleanup_call(worker.signal_once)
            if controller is not None:
                self._cleanup_call(controller.signal_once)
        # Gate gets its whole command/alarm interval, even on startup failure.
        if now >= cutoffs[4] and "gate" in self._children:
            self._cleanup_call(self._children["gate"].signal_once)
        if now >= cutoffs[5] and controller is not None:
            self._cleanup_call(controller.signal_once)
        for child in self._children.values():
            self._cleanup_call(child.observe)
        limits = {"worker": cutoffs[1], "gate": cutoffs[5], "controller": cutoffs[1]}
        for role, child in self._children.items():
            missed = ((child.code is None and now >= limits[role])
                      or (child.code is not None and (
                          child.reaped_ns is None or child.reaped_ns > limits[role])))
            if missed and role not in self._missed_cutoffs:
                self._missed_cutoffs.add(role)
                self._lifecycle_errors.append(DeadlineExpired(role + " fixed join cutoff"))

    def _close_runtime(self):
        # Every channel close is independently observed, never resolved merely
        # because another wrapper happened to close the same numeric descriptor.
        for role, channel in self._channels.items():
            self._cleanup_call(lambda role=role, channel=channel:
                               self._registry.close(self._channel_records[role], channel.close))
        for record in reversed(self._runtime_records):
            self._cleanup_call(lambda record=record: self._registry.close(record))
        cutoff = self._shutdown.cutoffs()[7]
        if any(r.closed_ns is not None and r.closed_ns >= cutoff for r in self._runtime_records):
            self._lifecycle_errors.append(DeadlineExpired("runtime closes before final release cutoff"))

    def take_validated_original(self, *, request, prepared, execution, export_root):
        self._assert_owner()
        if self._shutdown.armed and monotonic_ns() >= self._shutdown.cutoffs()[7]:
            error = DeadlineExpired("publication past original final release cutoff")
            if self._registry.primary is None:
                self._registry.primary = error
            raise error
        data = self._validated
        require(not self._running and not self._published and data is not None
                and self._validation_closed and not self._validation_close_late
                and execution is self._execution and execution is not None
                and data.owner is self and data.request is request is self._preflight._request
                and data.prepared is prepared is self._inputs
                and data.export_root is export_root is self._preflight._export_root
                and data.lease is self._lease and data.worker_execution is self._worker_execution
                and set(self._children) == {"worker", "controller", "gate"}
                and all(c.code is not None and c.record.closed for c in self._children.values())
                and all(r.closed or r.handle is None for r in self._runtime_records)
                and all(r._file.record.closed for r in self._lease._readers)
                and not self._registry.errors and not self._lifecycle_errors,
                "one-use sealed original after actual all-three joins/observed closes")
        self._published = True
        return data.original  # ZERO filesystem/hash/new lease operations.

    def release_joined(self):
        if self._released:
            return
        require(self._latch_held and _OWNERS.get(id(self)) is self,
                "actual registered latch holder")
        if self._running or any(c.code is None for c in self._children.values()):
            raise CustodyError(self, self._registry.primary, self._registry.errors)
        receipt = self._reservation_custody
        try:
            require(receipt is not None
                    and receipt.authorization is self._preflight._authorization,
                    "actual helper custody required before release")
            if self._claim_failed:
                require(original._custody_for_failure(
                    self._registry.primary, authorization=self._preflight._authorization) is receipt,
                    "actual failed-claim exception association")
                receipt.require_released()
            else:
                require(original._custody_for_reservation(self._reservation) is receipt,
                        "same actual reservation receipt")
                if self._reservation_failure is not None:
                    require(original._custody_for_failure(
                        self._reservation_failure,
                        authorization=self._preflight._authorization) is receipt,
                        "actual identity-operation exception association")
                require(not receipt.has_unknown, "unresolved helper generations retain all anchors")
        except BaseException as error:
            failure = CustodyError(self, self._registry.primary,
                (*self._registry.errors, *(() if receipt is None else receipt.secondary), error))
            _RETAINED_FAILURES.append(failure)
            raise failure from self._registry.primary
        self._invalidate_lease()  # Zero-child failure uses the same nonrenewable origin.
        # Publication comes before successful release, but joined failure and
        # zero-child preparation/admission failure remain releasable.
        require(self._validated is None or self._published or self._registry.primary is not None,
                "publish actual validated original before successful release")
        try:
            self._registry.close_all([r for r in self._registry.records if not r.is_anchor])
        except BaseException as error:
            failure = CustodyError(self, self._registry.primary, (*self._registry.errors, error))
            _RETAINED_FAILURES.append(failure)
            raise failure from self._registry.primary
        record = self._reservation_record
        close_errors = []
        if record is not None:
            event = "stopped" if self._published else "failed"
            def close_reservation():
                try:
                    self._reservation.close(event)
                except BaseException as error:
                    self._reservation_failure = error
                    if self._registry.primary is None:
                        self._registry.primary = error
                    if receipt.has_unknown:
                        raise
                    try:
                        receipt.require_released()
                    except BaseException as validation:
                        self._lifecycle_errors.append(validation)
                        raise error
                    close_errors.append(error)
                else:
                    receipt.require_released()
            try:
                self._registry.close(record, close_reservation)
            except BaseException as error:
                failure = CustodyError(self, self._registry.primary,
                    (*self._registry.errors, *receipt.secondary, error))
                _RETAINED_FAILURES.append(failure)
                raise failure from self._registry.primary
        # No root/ancestor release until every data/channel/reservation close
        # above is positively observed. Failed closes retain actual anchors.
        try:
            self._registry.close_all([r for r in self._registry.records if r.is_anchor])
        except BaseException as error:
            failure = CustodyError(self, self._registry.primary, (*self._registry.errors, error))
            _RETAINED_FAILURES.append(failure)
            raise failure from self._registry.primary
        require(not self._registry.errors
                and all(r.handle is None or r.closed for r in self._registry.records),
                "all actual users/closes observed before latch release")
        if monotonic_ns() >= self._shutdown.cutoffs()[7]:
            error = DeadlineExpired("reservation/anchor closes past final release cutoff")
            if self._registry.primary is None:
                self._registry.primary = error
            failure = CustodyError(self, self._registry.primary, (error,))
            _RETAINED_FAILURES.append(failure)
            raise failure
        require(release_common_latch(self), "same original common latch")
        self._latch_held = False
        self._released = True
        del _OWNERS[id(self)]
        if close_errors:
            failure = CustodyError(self, self._registry.primary,
                                   (*close_errors, *receipt.secondary), released=True)
            _RETAINED_FAILURES.append(failure)
            raise failure from self._registry.primary
