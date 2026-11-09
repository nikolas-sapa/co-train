"""One source-only V172 engineering attempt, not a scientific certificate.

UNRUN. Public entry performs nonallocating checks and freezes approved bytes
before importing Modal's bridge. All raw SDK work and owned cleanup execute
inside that bridge on its single shared loop. No retry or replacement exists.
Remote modes preserve the original native supervisor and complete verifier.
Host exports verify bytes only, never tensors or charged resource termination.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future
from contextlib import redirect_stdout
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import secrets
import stat
import sys
import threading
import time
from typing import Any, TYPE_CHECKING

from train.qualification_modal_transport import (
    CHUNK_BYTES, GPU_WINDOW_SECONDS, MANIFEST_RESPONSE_BUDGET, MAX_DEPTH,
    MAX_MEMBERS, METADATA_LIMIT, PlannedUpload, _ResponseAccumulator, _canonical_json, _digest,
    _integer, _load_strict_json, _mode_argv, _require, _validate_key,
    parse_manifest_body,
)

if TYPE_CHECKING:
    from train.native_qualification import QualificationRequest
    from train.qualification_modal_host import ModalOwnedHost

WORK_RESERVE_SECONDS = 150
VERIFY_RESERVE_SECONDS = 90
EXPORT_RESERVE_SECONDS = 30
_PRIVATE_INPUT_LIMIT = METADATA_LIMIT
_EXEC_OUTPUT_LIMIT = METADATA_LIMIT
_CLEANUP_JOIN_SECONDS = 30.0
_OWNED_STOP_SECONDS = 20.0
_EVIDENCE_ROOT = Path("/var/tmp/qualification/evidence")
_REMOTE_REQUEST_FILE = Path("/var/tmp/qualification/request.json")
_REQUEST_KEY = "request.json"
_LATCH_KEY = "attempt-latch.json"
_OBSERVATIONS_KEY = "attempt-observations.json"
_RECEIPT_KEY = "verification.json"
_EVIDENCE_KEYS = (_LATCH_KEY, _OBSERVATIONS_KEY, _RECEIPT_KEY)
NATIVE_ARGV = _mode_argv("--native")
VERIFY_ARGV = _mode_argv("--verify")
_REMOTE_VERIFICATION_SCOPE = (
    "remote-structural-tensor-verification-only; not host verification; "
    "not independent attestation; not cloud approval; not charged-end proof"
)
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


@dataclass(frozen=True)
class IssuedIdentity:
    """Inert projection of actual issued IDs, NOT SDK handle or authority."""

    app_id: str
    sandbox_id: str


@dataclass(frozen=True)
class EvidenceExport:
    name: str
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class EngineeringRunOutcome:
    attempt_id: str
    app_id: str
    sandbox_id: str
    phase_returncodes: tuple[int, int]
    receipt_size: int
    receipt_sha256: str
    evidence_manifest: tuple[dict[str, Any], ...]
    exports: tuple[EvidenceExport, ...]

    @property
    def verification_scope(self) -> str:
        return _REMOTE_VERIFICATION_SCOPE

    @property
    def certificate(self) -> None:
        return None

    @property
    def claims(self) -> dict[str, str]:
        return dict(remote_full_checkpoint_verification="observed",
                    host_export_byte_verification="observed",
                    host_tensor_verification="not_performed",
                    strict_certificate="not_issued")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_uid)


def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _regular(info: os.stat_result) -> None:
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
             "single-link regular file required")


def _absolute(path: Path) -> Path:
    path = Path(path)
    _require(path.is_absolute() and str(path).startswith("/")
             and ".." not in path.parts and "\\" not in str(path), "canonical absolute path required")
    return path


class _Anchor:
    """Retain and recheck every directory from `/`, never resolve aliases."""

    def __init__(self, path: Path):
        self.path = _absolute(path)
        self._fds: list[int] = []
        self._pins: list[tuple[int, str, int, tuple[int, ...]]] = []
        self._directories: dict[tuple[int, str], int] = {}
        try:
            root = os.open("/", _DIR_FLAGS)
            self._fds.append(root)
            fd = root
            for name in self.path.parts[1:]:
                fd = self.child(fd, name)
            self.fd = fd
            self.check()
        except BaseException:
            self.close()
            raise

    def child(self, parent: int, name: str, *, create: bool = False) -> int:
        _require(type(name) is str and name not in ("", ".", "..") and "/" not in name
                 and "\\" not in name, "directory component refused")
        cached = self._directories.get((parent, name))
        if cached is not None:
            self.check()
            return cached
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent)
        try:
            opened = os.fstat(fd)
            _require(stat.S_ISDIR(opened.st_mode)
                     and _directory_identity(before) == _directory_identity(opened),
                     "directory identity changed")
        except BaseException:
            os.close(fd)
            raise
        self._fds.append(fd)
        self._pins.append((parent, name, fd, _directory_identity(opened)))
        self._directories[parent, name] = fd
        return fd

    def parent(self, key: str, *, create: bool = False) -> tuple[int, str]:
        _validate_key(key)
        self.check()
        fd = self.fd
        parts = key.split("/")
        for name in parts[:-1]:
            fd = self.child(fd, name, create=create)
        self.check()
        return fd, parts[-1]

    def check(self) -> None:
        for parent, name, fd, pin in self._pins:
            _require(_directory_identity(os.fstat(fd)) == pin
                     and _directory_identity(os.stat(name, dir_fd=parent,
                                                     follow_symlinks=False)) == pin,
                     "directory ancestor redirected")

    def close(self) -> None:
        for fd in reversed(self._fds):
            os.close(fd)
        self._fds.clear()

    def __enter__(self) -> _Anchor:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        piece = view[:CHUNK_BYTES]
        count = os.write(fd, piece)
        _require(type(count) is int and 0 < count <= len(piece), "file write made no progress")
        view = view[count:]


def _hash_fd(fd: int, *, limit: int, deadline: float | None = None,
             clock: Callable[[], float] = time.monotonic) -> tuple[int, str]:
    os.lseek(fd, 0, os.SEEK_SET)
    count, digest = 0, hashlib.sha256()
    while True:
        _require(deadline is None or clock() < deadline, "disk hashing deadline expired")
        block = os.read(fd, min(CHUNK_BYTES, max(1, limit - count + 1)))
        if not block:
            break
        count += len(block)
        _require(count <= limit, "file exceeds byte bound")
        digest.update(block)
    return count, digest.hexdigest()


def _open_regular(anchor: _Anchor, key: str) -> tuple[int, int, str, tuple[int, ...]]:
    parent, name = anchor.parent(key)
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    _regular(before)
    fd = os.open(name, _READ_FLAGS, dir_fd=parent)
    try:
        opened = os.fstat(fd)
        _regular(opened)
        _require(_identity(before) == _identity(opened), "file identity changed during open")
        anchor.check()
        return fd, parent, name, _identity(opened)
    except BaseException:
        os.close(fd)
        raise


def _check_file(anchor: _Anchor, fd: int, parent: int, name: str,
                identity: tuple[int, ...]) -> None:
    anchor.check()
    opened, named = os.fstat(fd), os.stat(name, dir_fd=parent, follow_symlinks=False)
    _regular(opened)
    _require(_identity(opened) == identity == _identity(named), "file final identity changed")


class _Snapshot:
    def __init__(self, item: Any, anchor: _Anchor, parent: int, name: str, fd: int):
        self.root, self.key, self.size, self.sha256 = item.root, item.key, item.size, item.sha256
        self.path = Path(item.path)
        self.anchor, self.parent, self.name, self.fd = anchor, parent, name, fd
        self.identity = _identity(os.fstat(fd))

    def check(self) -> None:
        _check_file(self.anchor, self.fd, self.parent, self.name, self.identity)
        info = os.fstat(self.fd)
        _require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(),
                 "snapshot permissions/owner changed")

    def rewind(self) -> None:
        self.check()
        os.lseek(self.fd, 0, os.SEEK_SET)

    def read(self, count: int) -> bytes:
        _require(type(count) is int and 0 < count <= CHUNK_BYTES, "bounded snapshot read required")
        self.check()
        return os.read(self.fd, count)

    def chunks(self):
        self.rewind()
        while True:
            block = self.read(CHUNK_BYTES)
            if not block:
                break
            yield block
        self.check()

    def bounded_bytes(self, limit: int) -> bytes:
        _require(self.size <= limit, "snapshot exceeds control-message bound")
        return b"".join(self.chunks())


class _SnapshotSet:
    """Private owner700/600 snapshots, fully hashed before any SDK admission."""

    def __init__(self, uploads: Sequence[Any], parent: Path, *, deadline: float,
                 clock: Callable[[], float], reserved_bytes: int = 0):
        self.uploads, self.parent, self.deadline, self.clock = uploads, Path(parent), deadline, clock
        _require(type(reserved_bytes) is int and reserved_bytes >= 0, "nonnegative disk reserve required")
        self.reserved_bytes = reserved_bytes
        self.items: list[_Snapshot] = []
        self.anchor: _Anchor | None = None
        self.directory = self.parent / (".qualification-snapshot-" + secrets.token_hex(16))
        self.snapshot_bytes = 0
        self.free_bytes_before = 0
        self._directory_fd: int | None = None
        self._created: list[tuple[str, int, tuple[int, ...]]] = []

    def __enter__(self) -> _SnapshotSet:
        try:
            self.uploads = tuple(PlannedUpload(
                item.root, item.key, item.size, item.sha256, Path(item.path)) for item in self.uploads)
            for item in self.uploads:
                _require_upload_shape(item)
            self.anchor = _Anchor(self.parent)
            required = sum(item.size for item in self.uploads) + self.reserved_bytes
            free = os.fstatvfs(self.anchor.fd)
            self.free_bytes_before = free.f_bavail * free.f_frsize
            _require(required <= self.free_bytes_before, "insufficient fresh snapshot disk budget")
            os.mkdir(self.directory.name, 0o700, dir_fd=self.anchor.fd)
            self._directory_fd = self.anchor.child(self.anchor.fd, self.directory.name)
            directory_info = os.fstat(self._directory_fd)
            _require(stat.S_IMODE(directory_info.st_mode) == 0o700
                     and directory_info.st_uid == os.getuid(), "snapshot directory must be owner700")
            for index, item in enumerate(self.uploads):
                _require(self.clock() < self.deadline, "preparation deadline expired during snapshots")
                _require(isinstance(item.path, Path),
                         "uploads require a local Path, not an unvalidated stream")
                path = _absolute(item.path)
                with _Anchor(path.parent) as source_anchor:
                    src, src_parent, src_name, before = _open_regular(source_anchor, path.name)
                    try:
                        _require(os.fstat(src).st_size == item.size, "upload size differs from approved pin")
                        name = str(index)
                        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=self._directory_fd)
                        created = os.fstat(fd)
                        self._created.append((name, fd, (created.st_dev, created.st_ino)))
                        count, digest = 0, hashlib.sha256()
                        while True:
                            _require(self.clock() < self.deadline, "preparation snapshot deadline expired")
                            block = os.read(src, min(CHUNK_BYTES, max(1, item.size - count + 1)))
                            if not block:
                                break
                            count += len(block)
                            _require(count <= item.size, "upload exceeded approved size")
                            digest.update(block)
                            _write_all(fd, block)
                        os.fsync(fd)
                        _check_file(source_anchor, src, src_parent, src_name, before)
                        _require(count == item.size and digest.hexdigest() == item.sha256,
                                 "upload size/hash differs from approved pin")
                        _require(_hash_fd(fd, limit=item.size, deadline=self.deadline,
                                          clock=self.clock) == (item.size, item.sha256),
                                 "snapshot disk bytes differ")
                        frozen = _Snapshot(item, self.anchor, self._directory_fd, name, fd)
                        frozen.check()
                        self.items.append(frozen)
                        self.snapshot_bytes += count
                    finally:
                        os.close(src)
            self.check()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self) -> None:
        _require(self.anchor is not None, "snapshot anchor absent")
        self.anchor.check()
        for item in self.items:
            item.check()

    def __exit__(self, *args: Any) -> None:
        # Remove only the exact private objects this call created. Never recurse,
        # follow a changed alias, or delete an unrelated caller-owned object.
        cleanup_error = None
        try:
            for name, fd, pin in reversed(self._created):
                try:
                    if self.anchor is not None and self._directory_fd is not None:
                        self.anchor.check()
                        info = os.stat(name, dir_fd=self._directory_fd, follow_symlinks=False)
                        _require((info.st_dev, info.st_ino) == pin,
                                 "snapshot cleanup name changed")
                        os.unlink(name, dir_fd=self._directory_fd)
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
                finally:
                    os.close(fd)
            self._created.clear()
            if cleanup_error is None and self.anchor is not None and self._directory_fd is not None:
                self.anchor.check()
                os.rmdir(self.directory.name, dir_fd=self.anchor.fd)
        finally:
            if self.anchor is not None:
                self.anchor.close()
                self.anchor = None
        if cleanup_error is not None:
            raise cleanup_error


class _ExportFile:
    def __init__(self, tree: _ExportTree, key: str):
        _validate_key(key)
        tree.check()
        self.tree, self.key = tree, key
        self.parent, self.name = tree.anchor.parent(key, create=True)
        self.fd = os.open(self.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=self.parent)
        created = os.fstat(self.fd)
        _regular(created)
        self.created = created.st_dev, created.st_ino
        self.count, self.digest = 0, hashlib.sha256()
        self.final: tuple[int, ...] | None = None
        tree.files.append(self)

    def __call__(self, block: bytes) -> None:
        _require(type(block) is bytes and len(block) <= CHUNK_BYTES,
                 "export writes must be bounded bytes")
        self.tree.anchor.check()
        self.tree.check_deadline()
        _require((os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino) == self.created,
                 "export opened identity changed")
        _write_all(self.fd, block)
        self.count += len(block)
        self.digest.update(block)

    def finish(self, *, expected_size: int, expected_sha256: str) -> EvidenceExport:
        _integer(expected_size, 8 * 1024**3, "expected export size")
        _digest(expected_sha256)
        os.fsync(self.fd)
        _regular(os.fstat(self.fd))
        _require(self.count == expected_size and self.digest.hexdigest() == expected_sha256,
                 "export received bytes differ from pins")
        before = _identity(os.fstat(self.fd))
        _require(_hash_fd(self.fd, limit=expected_size, deadline=self.tree.deadline,
                          clock=self.tree.clock) == (expected_size, expected_sha256),
                 "actual export disk bytes differ from pins")
        _check_file(self.tree.anchor, self.fd, self.parent, self.name, before)
        final = os.fstat(self.fd)
        _require((final.st_dev, final.st_ino) == self.created and final.st_size == expected_size,
                 "export final identity/size differs")
        _require(stat.S_IMODE(final.st_mode) == 0o600 and final.st_uid == os.getuid(),
                 "export file permissions/owner changed")
        self.final = _identity(final)
        return EvidenceExport(self.key, self.tree.root / self.key, expected_size, expected_sha256)

    def check(self) -> None:
        if self.final is not None:
            _check_file(self.tree.anchor, self.fd, self.parent, self.name, self.final)


class _ExportTree:
    """Exclusive anchored export root, created only AFTER remote verification."""

    def __init__(self, root: Path, *, deadline: float | None = None,
                 clock: Callable[[], float] = time.monotonic, parent_anchor: _Anchor | None = None):
        self.root, self.files = _absolute(root), []
        self.deadline, self.clock = deadline, clock
        self.parent_anchor = parent_anchor
        self.anchor: _Anchor

    def __enter__(self) -> _ExportTree:
        if self.parent_anchor is not None:
            self.parent_anchor.check()
            _require(self.parent_anchor.path == self.root.parent, "export parent binding differs")
        self.anchor = _Anchor(self.root.parent)
        try:
            if self.parent_anchor is not None:
                _require(_directory_identity(os.fstat(self.anchor.fd))
                         == _directory_identity(os.fstat(self.parent_anchor.fd)),
                         "export parent changed since preallocation")
                self.parent_anchor.check()
            parent = self.anchor.fd
            os.mkdir(self.root.name, 0o700, dir_fd=parent)
            self.anchor.fd = self.anchor.child(parent, self.root.name)
            info = os.fstat(self.anchor.fd)
            _require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid(),
                     "export root must be private owner700")
            self.check()
            return self
        except BaseException:
            self.anchor.close()
            raise

    def check(self) -> None:
        self.check_deadline()
        self.anchor.check()
        for file in self.files:
            file.check()

    def check_deadline(self) -> None:
        if self.parent_anchor is not None:
            self.parent_anchor.check()
        _require(self.deadline is None or self.clock() < self.deadline, "export disk deadline expired")

    def create(self, key: str) -> _ExportFile:
        return _ExportFile(self, key)

    def write_bytes(self, key: str, payload: bytes) -> EvidenceExport:
        target = self.create(key)
        for offset in range(0, len(payload), CHUNK_BYTES):
            target(payload[offset:offset + CHUNK_BYTES])
        return target.finish(expected_size=len(payload), expected_sha256=hashlib.sha256(payload).hexdigest())

    def __exit__(self, *args: Any) -> None:
        try:
            if args[0] is None:
                self.check()
        finally:
            for file in self.files:
                os.close(file.fd)
            self.anchor.close()


def _read_remote_bounded(path: Path, *, limit: int) -> bytes:
    _require(type(limit) is int and limit > 0, "bounded read required")
    path = _absolute(path)
    with _Anchor(path.parent) as anchor:
        fd, parent, name, before = _open_regular(anchor, path.name)
        try:
            _require(os.fstat(fd).st_size <= limit, "remote file exceeds bound")
            parts, count = [], 0
            while True:
                block = os.read(fd, min(CHUNK_BYTES, max(1, limit - count + 1)))
                if not block:
                    break
                count += len(block)
                _require(count <= limit, "remote file exceeds bound")
                parts.append(block)
            _check_file(anchor, fd, parent, name, before)
            return b"".join(parts)
        finally:
            os.close(fd)


def _write_remote_exclusive(path: Path, payload: bytes) -> None:
    _require(len(payload) <= _PRIVATE_INPUT_LIMIT, "remote control document exceeds bound")
    path = _absolute(path)
    # Existing parent only; never precreate the original native output tree.
    tree = _ExportTree.__new__(_ExportTree)
    tree.root, tree.files = path.parent, []
    tree.deadline, tree.clock = None, time.monotonic
    tree.parent_anchor = None
    tree.anchor = _Anchor(path.parent)
    try:
        tree.write_bytes(path.name, payload)
        tree.check()
    finally:
        for file in tree.files:
            os.close(file.fd)
        tree.anchor.close()


def _load_remote_json(path: Path, *, limit: int) -> Any:
    return _load_strict_json(_read_remote_bounded(path, limit=limit))


def _load_native():
    from train import native_qualification
    return native_qualification


def _load_remote_verifier():
    from train.qualification_remote_verification import (
        REMOTE_VERIFICATION_SCOPE, verify_remote_exported_artifacts,
    )
    return REMOTE_VERIFICATION_SCOPE, verify_remote_exported_artifacts


def _load_remote_request(native: Any) -> Any:
    document = _load_remote_json(_REMOTE_REQUEST_FILE, limit=_PRIVATE_INPUT_LIMIT)
    _require(type(document) is dict, "original request must be an object")
    request = native._request_from_wire(document)
    native._validate_request(request)
    return request


def _attempt_id(binding: str, app_id: str, sandbox_id: str) -> str:
    _digest(binding)
    _require(all(type(value) is str and value and "\n" not in value
                 for value in (app_id, sandbox_id)), "actual issued IDs required")
    return hashlib.sha256("\n".join((binding, app_id, sandbox_id)).encode("utf-8")).hexdigest()


def _private_input(op: str) -> dict[str, Any]:
    payload = sys.stdin.buffer.read(_PRIVATE_INPUT_LIMIT + 1)
    _require(type(payload) is bytes and len(payload) <= _PRIVATE_INPUT_LIMIT,
             "private stdin exceeds bound")
    document = _load_strict_json(payload)
    _require(type(document) is dict and set(document) == {
        "v", "op", "request_sha256", "attempt_id", "app_id", "sandbox_id"},
        "private input keys refused")
    _require(type(document["v"]) is int and document["v"] == 1 and document["op"] == op,
             "private input version/operation refused")
    _digest(document["request_sha256"])
    _digest(document["attempt_id"])
    _require(document["attempt_id"] == _attempt_id(
        document["request_sha256"], document["app_id"], document["sandbox_id"]),
        "private input attempt differs from actual issued IDs")
    return document


class _ChildReturnObserver:
    """Read-only observer for EXACT original _run_child.__code__ returns."""

    def __init__(self, target_code: Any):
        self._target = target_code
        self.observations: list[tuple[int, int]] = []
        self.invalid = False

    def __call__(self, frame: Any, event: str, arg: Any) -> None:
        if event != "return" or frame.f_code is not self._target:
            return
        child = frame.f_locals.get("child")
        code = getattr(child, "returncode", None)
        phase = frame.f_locals.get("phase")
        if (type(arg) is not int or arg <= 0 or type(code) is not int
                or type(phase) is not int or phase != len(self.observations) + 1):
            self.invalid = True
            return
        self.observations.append((arg, code))


def _scope_observer(target_code: Any):
    prior = sys.getprofile()
    _require(prior is None, "refusing preexisting profile observer")
    observer = _ChildReturnObserver(target_code)
    sys.setprofile(observer)
    return prior, observer


def _validate_observations(document: Any, *, binding: str, attempt: str,
                           app_id: str, sandbox_id: str):
    _require(type(document) is dict and set(document) == {
        "v", "op", "request_sha256", "app_id", "sandbox_id", "attempt_id", "observations"},
        "observations document keys refused")
    _require(type(document["v"]) is int and document["v"] == 1
             and document["op"] == "phase-observations", "observations version/op refused")
    _require(document["request_sha256"] == binding and document["attempt_id"] == attempt
             and document["app_id"] == app_id and document["sandbox_id"] == sandbox_id,
             "observations identity differs")
    entries = document["observations"]
    _require(type(entries) is list and len(entries) == 2, "exactly two observed phases required")
    pids, codes = [], []
    for phase, entry in enumerate(entries, 1):
        _require(type(entry) is dict and set(entry) == {"phase", "pid", "returncode"},
                 "phase observation keys refused")
        _require(type(entry["phase"]) is int and entry["phase"] == phase
                 and type(entry["pid"]) is int and entry["pid"] > 0
                 and type(entry["returncode"]) is int, "phase observation type/order refused")
        pids.append(entry["pid"])
        codes.append(entry["returncode"])
    _require(pids[0] != pids[1], "observed PIDs must be distinct")
    return tuple(pids), tuple(codes)


def _run_native_mode() -> int:
    native = _load_native()
    private = _private_input("native-attempt")
    request = _load_remote_request(native)
    binding = native._request_binding(request)
    _require(private["request_sha256"] == binding, "original worker request binding differs")
    # Refuse profiling conflict before creating the exclusive attempt marker.
    _require(sys.getprofile() is None, "refusing preexisting profile observer")
    payload = _canonical_json(private)
    _write_remote_exclusive(_EVIDENCE_ROOT / _LATCH_KEY, payload)
    _require(_load_remote_json(_EVIDENCE_ROOT / _LATCH_KEY, limit=_PRIVATE_INPUT_LIMIT) == private,
             "exclusive latch roundtrip differs")
    original_code = native._run_child.__code__
    prior, observer = _scope_observer(original_code)
    try:
        code = native._worker_main(native._REQUEST_FILE)
        _require(sys.getprofile() is observer and native._run_child.__code__ is original_code,
                 "conflicting profiler or original child function changed")
    finally:
        sys.setprofile(prior)
    _require(type(code) is int and code == 0, "original worker failed")
    _require(not observer.invalid and len(observer.observations) == 2,
             "missing/duplicate/invalid original child returns")
    document = {**private, "op": "phase-observations",
                "observations": [dict(phase=index, pid=pid, returncode=status)
                                 for index, (pid, status) in enumerate(observer.observations, 1)]}
    _, codes = _validate_observations(
        document, binding=binding, attempt=private["attempt_id"],
        app_id=private["app_id"], sandbox_id=private["sandbox_id"])
    _require(codes == (0, 0), "actual original child statuses are nonzero")
    _write_remote_exclusive(_EVIDENCE_ROOT / _OBSERVATIONS_KEY, _canonical_json(document))
    return code


def _remote_output_manifest(root: Path, limit: int) -> list[dict[str, Any]]:
    """Anchored quiescent manifest, bounded JSON/member/depth/aggregate."""
    members, total, visited = [], 0, 0
    with _Anchor(root) as anchor:
        def walk(fd: int, prefix: str, depth: int) -> None:
            nonlocal total, visited
            # scandir consumes the descriptor without refollowing path names.
            with os.scandir(fd) as entries:
                for entry in entries:
                    visited += 1
                    _require(visited <= 20000, "directory entry bound exceeded")
                    key = prefix + entry.name
                    _validate_key(key)
                    before = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(before.st_mode):
                        _require(depth < MAX_DEPTH, "manifest directory depth exceeded")
                        child = anchor.child(fd, entry.name)
                        walk(child, key + "/", depth + 1)
                    else:
                        _require(len(members) < MAX_MEMBERS, "manifest member bound exceeded")
                        opened, parent, name, pin = _open_regular(anchor, key)
                        try:
                            _require(_identity(before) == pin, "manifest member changed before hashing")
                            size, digest = _hash_fd(opened, limit=limit - total)
                            _check_file(anchor, opened, parent, name, pin)
                            total += size
                            members.append(dict(key=key, size=size, sha256=digest))
                        finally:
                            os.close(opened)
            anchor.check()
        walk(anchor.fd, "", 0)
        anchor.check()
    members.sort(key=lambda member: member["key"])
    parse_manifest_body(_canonical_json(members), max_bytes=limit)
    return members


def _evidence_index() -> bytes:
    entries = []
    for key in sorted(_EVIDENCE_KEYS):
        body = _read_remote_bounded(_EVIDENCE_ROOT / key, limit=_PRIVATE_INPUT_LIMIT)
        entries.append(dict(key=key, size=len(body), sha256=hashlib.sha256(body).hexdigest()))
    payload = _canonical_json(entries)
    _require(len(payload) <= _PRIVATE_INPUT_LIMIT, "evidence descriptor index exceeded bound")
    return payload


def _verify_evidence() -> bytes:
    native = _load_native()
    private = _private_input("remote-verify")
    request = _load_remote_request(native)
    binding = native._request_binding(request)
    _require(binding == private["request_sha256"], "original verify request binding differs")
    latch = _load_remote_json(_EVIDENCE_ROOT / _LATCH_KEY, limit=_PRIVATE_INPUT_LIMIT)
    _require(latch == {**private, "op": "native-attempt"}, "exclusive attempt latch differs")
    observations = _load_remote_json(_EVIDENCE_ROOT / _OBSERVATIONS_KEY, limit=_PRIVATE_INPUT_LIMIT)
    _, codes = _validate_observations(
        observations, binding=binding, attempt=private["attempt_id"],
        app_id=private["app_id"], sandbox_id=private["sandbox_id"])
    _require(codes == (0, 0), "actual original phase statuses are nonzero")
    # Allowed original DTO projection, codes come ONLY from actual observed
    # returns, IDs ONLY from the private host input. This is not an SDK handle.
    result = native.OwnedJobResult(
        service_handle=IssuedIdentity(private["app_id"], private["sandbox_id"]),
        exported_root=request.output_dir, phase_returncodes=codes)
    scope, verifier = _load_remote_verifier()
    _require(scope == _REMOTE_VERIFICATION_SCOPE, "original verifier scope differs")
    receipt = verifier(request, result)  # original complete verifier exactly once
    manifest = _remote_output_manifest(request.output_dir, request.bounds.artifact_bytes)
    _require(receipt.artifact_bytes == sum(entry["size"] for entry in manifest),
             "original verifier/manifest artifact bytes differ")
    document = dict(
        v=1, op="remote-verification-receipt", scope=scope, request_sha256=binding,
        attempt_id=private["attempt_id"], app_id=private["app_id"], sandbox_id=private["sandbox_id"],
        phase_observations=observations["observations"], phase_returncodes=list(codes),
        checkpoints=[dict(checkpoint=checkpoint.checkpoint.name,
                          members=sorted(checkpoint.members),
                          observation_sha256=checkpoint.observation_sha256,
                          trainer_state_sha256=checkpoint.trainer_state_sha256)
                     for checkpoint in receipt.checkpoints],
        artifact_bytes=receipt.artifact_bytes, manifest=manifest)
    _write_remote_exclusive(_EVIDENCE_ROOT / _RECEIPT_KEY, _canonical_json(document))
    return _evidence_index()


def _run_verify_mode() -> int:
    # Include original request validation/import logs, not only tensor-library
    # logs, in the stderr redirect. Stdout is exclusively the descriptor index.
    with redirect_stdout(sys.stderr):
        index = _verify_evidence()
    # Only this bounded control document goes on stdout, not verifier logs.
    view = memoryview(index)
    while view:
        count = sys.stdout.buffer.write(view[:CHUNK_BYTES])
        _require(type(count) is int and 0 < count <= min(len(view), CHUNK_BYTES),
                 "descriptor stdout write made no progress")
        view = view[count:]
    sys.stdout.buffer.flush()
    return 0


def _require_upload_shape(item: Any) -> None:
    _require(not isinstance(item, Mapping) and all(hasattr(item, name) for name in
             ("root", "key", "size", "sha256", "path")), "upload DTO attributes required")
    _require(type(item.root) is str
             and item.root in ("source", "model", "data", "wheels", "request"), "upload root refused")
    _validate_key(item.key)
    _integer(item.size, 2 * 1024**3, "upload size")
    if item.root == "request":
        _require(item.key == _REQUEST_KEY and item.size <= _PRIVATE_INPUT_LIMIT,
                 "private request upload key/byte bound refused")
    if (item.root, item.key) == ("source", "train/qualification_file_rpc.py"):
        _require(0 < item.size <= METADATA_LIMIT, "approved bootstrap source byte bound refused")
    _digest(item.sha256)
    _require(isinstance(item.path, Path), "upload source must be a local Path")
    _absolute(item.path)


def _validate_request_snapshot(request: Any, snapshots: Sequence[_Snapshot], native: Any) -> None:
    requests = [item for item in snapshots if (item.root, item.key) == ("request", _REQUEST_KEY)]
    _require(len(requests) == 1, "exactly one original request upload required")
    # This is the EXISTING serializer, including registered model inventory,
    # asset rows, complete task schema, image and decimal bounds. No invented
    # export or path-independent digest stands in for the actual worker input.
    original_payload, original_assets = native._prepare_worker_transport(request)
    actual_payload = requests[0].bounded_bytes(_PRIVATE_INPUT_LIMIT)
    _require(actual_payload == original_payload, "request upload differs from original worker payload")
    expected = {(asset.kind, asset.key, asset.size, asset.sha256) for asset in original_assets}
    actual = {(item.root, item.key, item.size, item.sha256) for item in snapshots
              if item.root in ("source", "model", "data")}
    _require(actual == expected, "uploads do not exactly cover original worker assets")
    original_paths = {(asset.kind, asset.key): asset.host_path for asset in original_assets}
    _require(all(item.path == original_paths[item.root, item.key] for item in snapshots
                 if item.root in ("source", "model", "data")),
             "upload local path differs from original worker asset path")


@dataclass
class _Preparation:
    snapshots: _SnapshotSet
    items: Sequence[_Snapshot]
    rpc_source: bytes
    rpc_sha256: str
    request_sha256: str
    binding: str


def _prepare(request: Any, *, host: Any, uploads: Sequence[Any], setup_argv: tuple[str, ...],
             export_root: Path, clock: Callable[[], float]) -> _Preparation:
    # Authority first, even before importing the original native module.
    host.require_active(request)
    host.require_uploads(uploads)
    host.require_setup_argv(setup_argv)
    _require(type(uploads) in (tuple, list) and 1 <= len(uploads) <= 10000, "bounded uploads required")
    seen = set()
    for item in uploads:
        _require_upload_shape(item)
        _require((item.root, item.key) not in seen, "duplicate upload destination")
        seen.add((item.root, item.key))
    _require(type(setup_argv) is tuple and setup_argv
             and all(type(part) is str and part for part in setup_argv), "exact setup argv required")
    export_root = _absolute(export_root)
    with _Anchor(export_root.parent) as anchor:
        try:
            os.stat(export_root.name, dir_fd=anchor.fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("host export root must remain absent")
    deadline = host.preparation_deadline
    _require(type(deadline) is float and math.isfinite(deadline) and deadline > clock(),
             "finite preparation deadline required")
    native = _load_native()
    _require(type(request) is native.QualificationRequest, "original QualificationRequest required")
    _integer(request.bounds.artifact_bytes, 8 * 1024**3, "output disk byte reserve")
    snapshots = _SnapshotSet(
        uploads, export_root.parent, deadline=deadline, clock=clock,
        reserved_bytes=request.bounds.artifact_bytes + 3 * _PRIVATE_INPUT_LIMIT)
    snapshots.__enter__()
    try:
        _validate_request_snapshot(request, snapshots.items, native)
        host.require_uploads(tuple(snapshots.items))
        sources = [item for item in snapshots.items
                   if (item.root, item.key) == ("source", "train/qualification_file_rpc.py")]
        _require(len(sources) == 1, "exactly one approved B source snapshot required")
        rpc_source = sources[0].bounded_bytes(METADATA_LIMIT)
        request_item = next(item for item in snapshots.items if item.root == "request"
                            and item.key == _REQUEST_KEY)
        _require(len([item for item in snapshots.items if item.root == "request"]) == 1,
                 "unexpected private request uploads")
        binding = native._request_binding(request)
        _digest(binding)
        snapshots.check()
        _require(clock() < deadline, "preparation deadline expired before SDK bridge")
        host.require_active(request)
        return _Preparation(snapshots, snapshots.items, rpc_source, sources[0].sha256,
                            request_item.sha256, binding)
    except BaseException:
        snapshots.__exit__(None, None, None)
        raise


def _load_bridge():
    # Call-time only. No package fakes, cached metadata, alternate loops or
    # public-resource fallback. A pins the raw Modal1.6.3/nonpersistent GPU V1.
    from modal._utils.async_utils import synchronizer, synchronize_api
    return synchronizer, synchronize_api


class SDKBridgeIncomplete(RuntimeError):
    """Bounded bridge admission/cleanup failed, remote state is UNKNOWN."""


async def _wait_shielded(task: asyncio.Future, *, deadline: float,
                         clock: Callable[[], float], ignore_cancel: bool = False):
    """Repeated caller cancellation cannot cancel or detach admitted cleanup."""
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError("bounded SDK admission/cleanup wait expired")
        try:
            return await asyncio.wait_for(asyncio.shield(task), remaining)
        except asyncio.CancelledError:
            if task.done() or not ignore_cancel:
                raise


async def _dispatch_sdk(work: Callable[[], Any], *, preparation_deadline: float,
                        clock: Callable[[], float]):
    synchronizer, synchronize_api = _load_bridge()
    acknowledgement: Future = Future()
    completed: Future = Future()
    intent = threading.Event()
    cancel_sent = False

    async def closure():
        # Cross-thread ACK is independent of synchronicity's private 1-second
        # inner-task transfer. Late closures cannot allocate after abandonment.
        task, loop = asyncio.current_task(), asyncio.get_running_loop()
        acknowledgement.set_result((loop, task))
        try:
            if intent.is_set() or clock() >= preparation_deadline:
                raise asyncio.CancelledError()
            return await work()
        finally:
            completed.set_result(None)

    synchronizer.no_io_translation(closure)
    wrapped = synchronize_api(closure)
    bridge_task = asyncio.create_task(wrapped.aio())
    ack_task = asyncio.wrap_future(acknowledgement)
    done_task = asyncio.wrap_future(completed)
    cancelled: asyncio.CancelledError | None = None
    failure: BaseException | None = None
    try:
        # Observe early bridge failures without waiting until the ACK deadline.
        finished, _ = await asyncio.wait((bridge_task, ack_task),
                                        timeout=max(0.0, preparation_deadline - clock()),
                                        return_when=asyncio.FIRST_COMPLETED)
        if bridge_task in finished:
            _require(acknowledgement.done() and completed.done(),
                     "SDK bridge returned without closure admission/completion")
            return bridge_task.result()
        if ack_task not in finished:
            raise TimeoutError("SDK bridge admission not acknowledged")
        return await asyncio.shield(bridge_task)
    except asyncio.CancelledError as error:
        cancelled = error
    except BaseException as error:
        failure = error
    # No further caller cancellation reaches bridge_task/owned SDK work.
    intent.set()
    admission_deadline = preparation_deadline
    if not acknowledgement.done():
        try:
            await _wait_shielded(ack_task, deadline=admission_deadline, clock=clock,
                                 ignore_cancel=True)
        except TimeoutError:
            # No ACK: owned work has not been admitted. A future closure sees
            # intent BEFORE implementation. Cancelling aio is safe only here.
            bridge_task.cancel()
            try:
                await _wait_shielded(bridge_task, deadline=clock() + 1.5, clock=clock,
                                     ignore_cancel=True)
            except (asyncio.CancelledError, TimeoutError):
                pass
            # Retrieve a late exception without a detached resource cleanup.
            bridge_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            if cancelled is not None:
                raise cancelled
            raise TimeoutError("SDK bridge admission deadline expired") from failure
    if acknowledgement.done():
        loop, owned_task = acknowledgement.result()
        if not completed.done() and not cancel_sent:
            cancel_sent = True
            loop.call_soon_threadsafe(owned_task.cancel)
        join_deadline = clock() + _CLEANUP_JOIN_SECONDS
        try:
            await _wait_shielded(done_task, deadline=join_deadline, clock=clock, ignore_cancel=True)
            # Joining closure's finally alone is insufficient: await the aio
            # transfer too, so its exception and cleanup completion are observed.
            try:
                await _wait_shielded(bridge_task, deadline=join_deadline, clock=clock,
                                     ignore_cancel=True)
            except asyncio.CancelledError:
                pass
        except TimeoutError as error:
            raise SDKBridgeIncomplete("SDK owned cleanup unconfirmed; resource state UNKNOWN") from error
    if cancelled is not None:
        raise cancelled
    if failure is not None:
        raise failure
    raise SDKBridgeIncomplete("SDK bridge ended without an observed outcome")


def _stage_deadlines(end: float, now: float) -> tuple[float, float, float]:
    _require(type(end) is float and math.isfinite(end) and end > now
             and end - now <= GPU_WINDOW_SECONDS, "GPU window must be within 1800 seconds")
    work, verify, export = end - 150, end - 90, end - 30
    _require(now < work < verify < export < end, "GPU reserves leave no work time")
    return work, verify, export


async def _bounded(awaitable: Any, deadline: float, clock: Callable[[], float]):
    return await asyncio.wait_for(awaitable, max(0.0, deadline - clock()))


async def _stop_once(host: Any, *, deadline: float, clock: Callable[[], float]) -> None:
    # A receives the ACTUAL global end, or now when end is unknown. The local
    # join is bounded even when the GPU interval has not begun.
    stop_task = asyncio.create_task(host.stop_owned(deadline=deadline))
    limit = max(0.05, min(_OWNED_STOP_SECONDS, deadline - clock()))
    try:
        await _wait_shielded(stop_task, deadline=clock() + limit, clock=clock, ignore_cancel=True)
    except TimeoutError as error:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
        raise SDKBridgeIncomplete("owned stop deadline expired; charged end UNKNOWN") from error


def _validate_receipt(document: Any, *, binding: str, attempt: str, app_id: str,
                      sandbox_id: str, observations: Mapping[str, Any],
                      artifact_limit: int) -> tuple[dict[str, Any], ...]:
    _require(type(document) is dict and set(document) == {
        "v", "op", "scope", "request_sha256", "attempt_id", "app_id", "sandbox_id",
        "phase_observations", "phase_returncodes", "checkpoints", "artifact_bytes", "manifest"},
        "receipt keys refused")
    _require(type(document["v"]) is int and document["v"] == 1
             and document["op"] == "remote-verification-receipt"
             and document["scope"] == _REMOTE_VERIFICATION_SCOPE, "receipt scope/version/op refused")
    _require(document["request_sha256"] == binding and document["attempt_id"] == attempt
             and document["app_id"] == app_id and document["sandbox_id"] == sandbox_id,
             "receipt identity differs from original request/host-issued IDs")
    _, codes = _validate_observations(
        observations, binding=binding, attempt=attempt, app_id=app_id, sandbox_id=sandbox_id)
    _require(codes == (0, 0) and document["phase_observations"] == observations["observations"],
             "receipt actual observations differ")
    _require(type(document["phase_returncodes"]) is list
             and all(type(code) is int for code in document["phase_returncodes"])
             and document["phase_returncodes"] == list(codes), "receipt actual phase statuses differ")
    manifest = parse_manifest_body(_canonical_json(document["manifest"]), max_bytes=artifact_limit)
    _require(bool(manifest), "receipt output manifest empty")
    _integer(document["artifact_bytes"], artifact_limit, "receipt artifact bytes")
    _require(document["artifact_bytes"] == sum(entry["size"] for entry in manifest),
             "receipt aggregate byte count differs")
    checkpoints = document["checkpoints"]
    _require(type(checkpoints) is list and len(checkpoints) == 2, "exactly two receipt checkpoints required")
    for phase, checkpoint in enumerate(checkpoints, 1):
        _require(type(checkpoint) is dict and set(checkpoint) == {
            "checkpoint", "members", "observation_sha256", "trainer_state_sha256"},
            "receipt checkpoint keys refused")
        name = f"checkpoint-{phase}"
        _require(checkpoint["checkpoint"] == name, "receipt checkpoint name differs")
        members = checkpoint["members"]
        _require(type(members) is list and members and all(type(member) is str for member in members),
                 "bounded checkpoint members required")
        for member in members:
            _validate_key(member)
        _require(members == sorted(set(members)), "checkpoint members must be sorted unique")
        actual = {entry["key"][len(name) + 1:]: entry for entry in manifest
                  if entry["key"].startswith(name + "/")}
        _require(set(actual) == set(members), "manifest does not exactly cover checkpoint members")
        for field, key in (("observation_sha256", "native-observation.json"),
                           ("trainer_state_sha256", "trainer_state.json")):
            _digest(checkpoint[field])
            _require(key in actual and actual[key]["sha256"] == checkpoint[field],
                     "receipt checkpoint JSON digest differs from output manifest")
    return manifest


async def _pull_evidence(transport: Any, entries: tuple[dict[str, Any], ...], *,
                         deadline: float) -> dict[str, bytes]:
    _require({entry["key"] for entry in entries} == set(_EVIDENCE_KEYS) and len(entries) == 3,
             "trusted verifier descriptor index must name exactly three evidence files")
    fetched = {}
    for entry in entries:
        _require(entry["size"] <= _PRIVATE_INPUT_LIMIT, "evidence member exceeds control bound")
        sink = _ResponseAccumulator(_PRIVATE_INPUT_LIMIT)
        await transport.get_to("evidence", entry, sink, deadline=deadline)
        _require(len(sink.payload) == entry["size"]
                 and hashlib.sha256(sink.payload).hexdigest() == entry["sha256"],
                 "evidence actual bytes differ from descriptor")
        fetched[entry["key"]] = sink.payload
    return fetched


async def _export_artifacts(transport: Any, tree: _ExportTree,
                            entries: Sequence[Mapping[str, Any]], *,
                            deadline: float) -> tuple[EvidenceExport, ...]:
    exports = []
    for entry in entries:
        target = tree.create(entry["key"])
        await transport.get_to("output", entry, target, deadline=deadline)
        exports.append(target.finish(expected_size=entry["size"], expected_sha256=entry["sha256"]))
        tree.check()
    tree.check()
    return tuple(exports)


async def _run_engineering_once_impl(
    request: Any, *, host: Any, uploads: Sequence[Any], setup_argv: tuple[str, ...],
    export_root: Path, clock: Callable[[], float], prepared: _Preparation,
) -> EngineeringRunOutcome:
    from train.qualification_modal_transport import ModalExecTransport

    end: float | None = None
    try:
        # Cleanup try starts BEFORE open, covering ambiguous open/controller arm,
        # transport construction and ambiguous Sandbox creation.
        await _bounded(host.open_app(deadline=host.preparation_deadline),
                       host.preparation_deadline, clock)
        candidate = host.begin_gpu_window()
        work_deadline, verify_deadline, export_deadline = _stage_deadlines(candidate, clock())
        end = candidate
        transport = ModalExecTransport(host, clock=clock)
        sandbox = await _bounded(host.create_once(deadline=work_deadline), work_deadline, clock)
        transport.sandbox = sandbox
        transport.bind_runtime(rpc_source=prepared.rpc_source, rpc_sha256=prepared.rpc_sha256,
                               setup_argv=setup_argv, request_sha256=prepared.request_sha256,
                               uploads=prepared.items)
        await transport.stage_uploads(prepared.items, deadline=work_deadline)
        await transport.exec_once(setup_argv, stdout_limit=_EXEC_OUTPUT_LIMIT,
                                  stderr_limit=_EXEC_OUTPUT_LIMIT, deadline=work_deadline)
        await transport.exec_once(transport.materialize_argv, stdout_limit=_EXEC_OUTPUT_LIMIT,
                                  stderr_limit=_EXEC_OUTPUT_LIMIT, deadline=work_deadline)
        app_id, sandbox_id = host.app_id, host.sandbox_id
        attempt = _attempt_id(prepared.binding, app_id, sandbox_id)
        private = dict(v=1, op="native-attempt", request_sha256=prepared.binding,
                       attempt_id=attempt, app_id=app_id, sandbox_id=sandbox_id)
        native_input = _canonical_json(private)
        await transport.exec_once(NATIVE_ARGV, input_chunks=(native_input,),
                                  stdout_limit=_EXEC_OUTPUT_LIMIT, stderr_limit=_EXEC_OUTPUT_LIMIT,
                                  deadline=work_deadline)
        index = _ResponseAccumulator(_PRIVATE_INPUT_LIMIT)
        await transport.exec_once(
            VERIFY_ARGV, input_chunks=(_canonical_json({**private, "op": "remote-verify"}),),
            stdout_sink=index, stdout_limit=_PRIVATE_INPUT_LIMIT, stderr_limit=_EXEC_OUTPUT_LIMIT,
            deadline=verify_deadline)
        evidence_manifest = parse_manifest_body(
            index.payload, max_bytes=3 * _PRIVATE_INPUT_LIMIT, max_members=3, max_depth=0,
            json_limit=_PRIVATE_INPUT_LIMIT)
        fetched = await _pull_evidence(transport, evidence_manifest, deadline=export_deadline)
        _require(fetched[_LATCH_KEY] == native_input, "exclusive remote attempt latch differs")
        observations = _load_strict_json(fetched[_OBSERVATIONS_KEY])
        _, codes = _validate_observations(
            observations, binding=prepared.binding, attempt=attempt,
            app_id=app_id, sandbox_id=sandbox_id)
        receipt = _load_strict_json(fetched[_RECEIPT_KEY])
        manifest = _validate_receipt(
            receipt, binding=prepared.binding, attempt=attempt, app_id=app_id,
            sandbox_id=sandbox_id, observations=observations,
            artifact_limit=request.bounds.artifact_bytes)
        # Independent B output-only manifest after remote verification, no
        # evidence-root extension to B. Exact equality refuses point-in-time drift.
        current = await transport.output_manifest(
            max_bytes=request.bounds.artifact_bytes, deadline=export_deadline)
        _require(current == manifest, "receipt-pinned output manifest changed")
        _require(clock() < export_deadline, "export reserve expired")
        with _ExportTree(
            export_root, deadline=export_deadline, clock=clock,
            parent_anchor=getattr(prepared.snapshots, "anchor", None),
        ) as tree:
            exports = list(await _export_artifacts(transport, tree, manifest, deadline=export_deadline))
            for key in _EVIDENCE_KEYS:
                exports.append(tree.write_bytes("evidence/" + key, fetched[key]))
            tree.check()
            _require(clock() < export_deadline, "export exceeded global reserve")
        payload = fetched[_RECEIPT_KEY]
        return EngineeringRunOutcome(
            attempt, app_id, sandbox_id, codes, len(payload), hashlib.sha256(payload).hexdigest(),
            evidence_manifest, tuple(exports))
    finally:
        await _stop_once(host, deadline=clock() if end is None else end, clock=clock)


async def run_engineering_once(
    request: QualificationRequest, *, host: ModalOwnedHost, uploads: Sequence[Any],
    setup_argv: tuple[str, ...], export_root: Path, clock: Callable[[], float] | None = None,
) -> EngineeringRunOutcome:
    clock = time.monotonic if clock is None else clock
    _require(callable(clock), "clock must be callable")
    prepared = _prepare(request, host=host, uploads=uploads, setup_argv=setup_argv,
                        export_root=export_root, clock=clock)
    async def work():
        # Original caller objects are captured, never translated/reconstructed.
        return await _run_engineering_once_impl(
            request, host=host, uploads=uploads, setup_argv=setup_argv,
            export_root=export_root, clock=clock, prepared=prepared)
    try:
        return await _dispatch_sdk(work, preparation_deadline=host.preparation_deadline, clock=clock)
    finally:
        prepared.snapshots.__exit__(None, None, None)


def main(argv: list[str] | None = None) -> int:
    modes = list(sys.argv[1:] if argv is None else argv)
    if modes == ["--native"]:
        return _run_native_mode()
    if modes == ["--verify"]:
        return _run_verify_mode()
    raise ValueError("worker entry modes are exactly --native or --verify")


if __name__ == "__main__":
    raise SystemExit(main())
