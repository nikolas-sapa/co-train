"""Host-only transfer leaves. External owner admits and bounds the whole lifecycle.

No provider, resource allocation, phase execution or approval is supplied here.
The owner supplies exclusive custody, independent export pins, interruption of
blocking I/O, retention of failed artifacts and unconditional resource teardown.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import io
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import BinaryIO, ContextManager, Iterator, Protocol, TypeVar

from train import native_qualification as native


_CHUNK = 1048576
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_Stream = TypeVar("_Stream")


class UploadReader(Protocol):
    """Drain until EOF; each read may return at most one 1 MiB block."""

    def read(self, size: int = -1) -> bytes: ...


class ExportReader(UploadReader, Protocol):
    def stat(self) -> os.stat_result: ...


class OwnedTransport(Protocol):
    """Trusted non-default owner adapter, never inferred from worker JSON.

    write_file exclusively creates one fixed worker file, consumes the reader
    and reports bytes written, with no outer retry. open_export rejects links
    in EVERY remote component and binds stat/read to one regular open handle.
    Both enforce the supplied absolute monotonic deadline, including blocking
    calls and any builtin same-exec resume. Neither creates/replaces a resource.
    These obligations require independent adapter review and real verification.
    """

    def write_file(self, resource: object, path: str, source: UploadReader, *,
                   deadline: float) -> int: ...

    def open_export(self, resource: object, path: str, *,
                    deadline: float) -> ContextManager[ExportReader]: ...


@dataclass
class TransferBudget:
    """Shared wire-byte cap/deadline, not authorization or a charge guarantee."""

    max_bytes: int
    deadline: float
    transferred_bytes: int = field(default=0, init=False)
    _failed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        native._positive(self.max_bytes, "transfer max_bytes")
        native._require(type(self.deadline) in (int, float) and math.isfinite(self.deadline),
                        "finite monotonic deadline required")
        native._require(self.deadline <= time.monotonic() + 1800,
                        "transfer deadline exceeds maximum attempt lifetime")

    def check(self, reserve: int = 0) -> None:
        native._require(not self._failed, "failed transfer budget cannot be reused")
        native._require(time.monotonic() < self.deadline, "transfer deadline expired")
        native._require(self.transferred_bytes + reserve <= self.max_bytes,
                        "aggregate transfer byte cap exceeded")

    def charge(self, size: int) -> None:
        self.transferred_bytes += size
        self.check()

    def _read_limit(self, size: int) -> int:
        self.check()
        remaining = self.max_bytes - self.transferred_bytes
        native._require(size == 0 or remaining > 0, "aggregate transfer byte cap exhausted")
        return min(size, remaining)


@contextmanager
def _operation(transport: OwnedTransport, resource: object,
               budget: TransferBudget) -> Iterator[None]:
    native._require(type(budget) is TransferBudget, "explicit TransferBudget required")
    try:
        budget.check()
        native._require(resource is not None and transport is not None,
                        "trusted transport and owned resource required")
        yield
        budget.check()
    except BaseException:
        budget._failed = True
        raise


@contextmanager
def _managed(context: ContextManager[_Stream], label: str) -> Iterator[_Stream]:
    stream = context.__enter__()
    try:
        yield stream
    except BaseException as primary:
        try:
            context.__exit__(type(primary), primary, primary.__traceback__)
        except BaseException:
            BaseException.add_note(primary, label)
        raise
    else:
        context.__exit__(None, None, None)


@contextmanager
def _owned_fds() -> Iterator[list[int]]:
    descriptors = []
    primary = None
    try:
        yield descriptors
    except BaseException as error:
        primary = error
        raise
    finally:
        first = None
        while descriptors:
            fd = descriptors.pop()
            try:
                os.close(fd)
            except BaseException as error:
                if primary is not None:
                    BaseException.add_note(primary, "local descriptor cleanup failed")
                elif first is None:
                    first = error
                else:
                    BaseException.add_note(first, "local descriptor cleanup failed")
        if first is not None:
            raise first


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    native._require(isinstance(path, Path) and path.is_absolute()
                    and ".." not in path.parts, "absolute nontraversing local path required")
    with _owned_fds() as descriptors:
        fd = os.open("/", _DIRECTORY)
        descriptors.append(fd)
        for part in path.parts[1:]:
            next_fd = os.open(part, _DIRECTORY, dir_fd=fd)
            descriptors.append(next_fd)
            # A failed close can already have released fd; never retry it.
            descriptors.remove(fd)
            os.close(fd)
            fd = next_fd
        yield fd


def _regular_signature(info: os.stat_result, size: int) -> tuple[int, ...]:
    native._require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == size,
                    "transfer metadata drift/link refused")
    return native._signature(info)


@contextmanager
def _source(asset: native._StagedAsset) -> Iterator[BinaryIO]:
    with _directory(asset.host_path.parent) as parent:
        with _owned_fds() as descriptors:
            fd = os.open(asset.host_path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            descriptors.append(fd)
            stream = os.fdopen(fd, "rb")
            descriptors.remove(fd)
            with _managed(stream, "local upload stream cleanup failed") as stream:
                signature = _regular_signature(os.fstat(stream.fileno()), asset.size)
                yield stream
                native._require(native._signature(os.stat(asset.host_path.name, dir_fd=parent,
                                                         follow_symlinks=False))
                                == signature, "asset path changed during transfer")


class _Upload:
    def __init__(self, stream: BinaryIO, size: int, digest: str, budget: TransferBudget):
        self._stream, self._size, self._expected, self._budget = stream, size, digest, budget
        self._digest = hashlib.sha256()
        self._count = 0

    def read(self, size: int = -1) -> bytes:
        self._budget.check()
        native._require(type(size) is int and size >= -1, "invalid upload read size")
        limit = _CHUNK if size == -1 else min(size, _CHUNK)
        limit = self._budget._read_limit(min(limit, self._size - self._count + 1))
        if limit == 0:
            return b""
        block = self._stream.read(limit)
        native._require(type(block) is bytes, "invalid upload read")
        self._budget.charge(len(block))
        native._require(len(block) <= limit, "invalid upload read")
        self._count += len(block)
        native._require(self._count <= self._size, "upload grew during transfer")
        self._digest.update(block)
        return block

    def finish(self, written: int) -> None:
        self._budget.check()
        native._require(type(written) is int and written == self._count == self._size
                        and self._digest.hexdigest() == self._expected,
                        "partial upload or asset hash drift")


def stage_worker_assets(request: native.QualificationRequest, *, transport: OwnedTransport,
                        resource: object, budget: TransferBudget) -> None:
    """Stage one prepared packet; publish its closed request last, never retry."""
    with _operation(transport, resource, budget):
        payload, assets = native._prepare_worker_transport(request)
        budget.check()
        document = native._decode_worker_transport(payload)
        rows = document["assets"]
        native._require(len(rows) == len(assets) and all(
            row == {key: getattr(asset, key) for key in ("kind", "key", "size", "sha256")}
            for row, asset in zip(rows, assets)), "prepared asset table differs from wire")
        budget.check(len(payload) + sum(asset.size for asset in assets) + len(assets) + 1)
        signatures = []
        for asset in assets:
            budget.check()
            try:
                with _directory(asset.host_path.parent) as parent:
                    info = os.stat(asset.host_path.name, dir_fd=parent, follow_symlinks=False)
                    signatures.append(_regular_signature(info, asset.size))
            except OSError as error:
                raise ValueError("cannot open pinned upload source") from error
        for asset, signature in zip(assets, signatures):
            budget.check()
            with _source(asset) as stream:
                native._require(native._signature(os.fstat(stream.fileno())) == signature,
                                "asset changed before upload")
                reader = _Upload(stream, asset.size, asset.sha256, budget)
                written = transport.write_file(resource, str(native._asset_path(asset.kind, asset.key)),
                                               reader, deadline=budget.deadline)
                reader.finish(written)
                native._require(native._signature(os.fstat(stream.fileno())) == signature,
                                "asset changed during upload")
        reader = _Upload(io.BytesIO(payload), len(payload), hashlib.sha256(payload).hexdigest(), budget)
        written = transport.write_file(resource, str(native._REQUEST_FILE), reader,
                                       deadline=budget.deadline)
        reader.finish(written)


def _export_members(members: tuple[native.FilePin, ...], artifact_cap: int) -> None:
    native._require(type(members) is tuple and 1 <= len(members) <= 1024,
                    "bounded agreed export pins required")
    seen = set()
    total = 0
    for pin in members:
        native._require(type(pin) is native.FilePin and isinstance(pin.path, Path),
                        "relative export FilePin required")
        parts = pin.path.parts
        native._require(len(parts) == 2 and parts[0] in {"checkpoint-1", "checkpoint-2"}
                        and re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,255}", parts[1]),
                        "unsafe checkpoint member")
        native._require(pin.path not in seen, "duplicate export member")
        seen.add(pin.path)
        native._require(type(pin.size) is int and 0 <= pin.size <= artifact_cap
                        and type(pin.sha256) is str
                        and re.fullmatch("[0-9a-f]{64}", pin.sha256), "invalid export pin")
        total += pin.size
    native._require(total <= artifact_cap, "aggregate artifact byte cap exceeded")


def _remote_signature(stream: ExportReader, size: int) -> tuple[int, ...]:
    return _regular_signature(stream.stat(), size)


def _copy_export(source: ExportReader, target: BinaryIO, pin: native.FilePin,
                 budget: TransferBudget) -> None:
    count = 0
    digest = hashlib.sha256()
    while True:
        limit = budget._read_limit(min(_CHUNK, pin.size - count + 1))
        block = source.read(limit)
        native._require(type(block) is bytes, "invalid export read")
        budget.charge(len(block))
        native._require(len(block) <= limit, "invalid export read")
        count += len(block)
        native._require(count <= pin.size, "export stream exceeds agreed size")
        if not block:
            break
        native._require(target.write(block) == len(block), "short local export write")
        digest.update(block)
    native._require(count == pin.size and digest.hexdigest() == pin.sha256,
                    "partial export or remote hash drift")


def _rehash(target: BinaryIO, pin: native.FilePin, budget: TransferBudget) -> None:
    before = native._signature(os.fstat(target.fileno()))
    target.seek(0)
    count = 0
    digest = hashlib.sha256()
    while True:
        budget.check()
        block = target.read(min(_CHUNK, pin.size - count + 1))
        count += len(block)
        native._require(count <= pin.size, "local export grew")
        if not block:
            break
        digest.update(block)
    native._require(count == pin.size and digest.hexdigest() == pin.sha256
                    and native._signature(os.fstat(target.fileno())) == before,
                    "local export rehash/metadata failure")


def export_worker_checkpoints(
    request: native.QualificationRequest, members: tuple[native.FilePin, ...], *,
    transport: OwnedTransport, resource: object, phase_returncodes: tuple[int, int],
    budget: TransferBudget,
) -> tuple[Path, Path]:
    """Export owner-agreed pins, then defer native semantics to the frozen checker.

    Pins are independently agreed relative members, NOT a stdout manifest.
    Fresh private output and partial files are deliberately retained on failure.
    Local fsync calls do not establish provider durability/retention guarantees.
    """
    with _operation(transport, resource, budget):
        native._require(type(phase_returncodes) is tuple and len(phase_returncodes) == 2
                        and all(type(code) is int and code == 0 for code in phase_returncodes),
                        "both original native phases must succeed before export")
        _export_members(members, request.bounds.artifact_bytes)
        budget.check(sum(pin.size for pin in members) + len(members))
        root = request.output_dir
        native._require(isinstance(root, Path) and root.is_absolute() and root.name
                        and ".." not in root.parts, "fresh absolute export root required")
        with _directory(root.parent) as parent:
            os.mkdir(root.name, mode=0o700, dir_fd=parent)
            with _owned_fds() as descriptors:
                root_fd = os.open(root.name, _DIRECTORY, dir_fd=parent)
                descriptors.append(root_fd)
                os.fchmod(root_fd, 0o700)
                identity = os.fstat(root_fd)
                directories = {}
                for pin in members:
                    budget.check()
                    directory, name = pin.path.parts
                    if directory not in directories:
                        os.mkdir(directory, mode=0o700, dir_fd=root_fd)
                        folder = os.open(directory, _DIRECTORY, dir_fd=root_fd)
                        descriptors.append(folder)
                        directories[directory] = folder
                        os.fchmod(folder, 0o700)
                    folder = directories[directory]
                    complete = False
                    remote = transport.open_export(resource, str(native._OUTPUT / pin.path),
                                                   deadline=budget.deadline)
                    with _managed(remote, "remote export context cleanup failed") as source:
                        budget.check()
                        signature = _remote_signature(source, pin.size)
                        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=folder)
                        descriptors.append(fd)
                        target = os.fdopen(fd, "w+b")
                        descriptors.remove(fd)
                        with _managed(target, "local export stream cleanup failed") as target:
                            os.fchmod(target.fileno(), 0o600)
                            _copy_export(source, target, pin, budget)
                            native._require(_remote_signature(source, pin.size) == signature,
                                            "remote export changed during read")
                            target.flush()
                            os.fsync(target.fileno())
                            _rehash(target, pin, budget)
                            info = os.stat(name, dir_fd=folder, follow_symlinks=False)
                            native._require(native._signature(info)
                                            == native._signature(os.fstat(target.fileno()))
                                            and info.st_nlink == 1, "local export path replaced")
                        complete = True
                    native._require(complete, "export context suppressed a transfer failure")
                for fd in directories.values():
                    budget.check()
                    os.fsync(fd)
                os.fsync(root_fd)
                os.fsync(parent)
                current = os.stat(root.name, dir_fd=parent, follow_symlinks=False)
                native._require((current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino)
                                and stat.S_ISDIR(current.st_mode), "export root replaced")
        budget.check()
        result = native.OwnedJobResult(resource, root, phase_returncodes)
        checkpoints = native._check_exported_artifacts(request, result)
        budget.check()
        return checkpoints
