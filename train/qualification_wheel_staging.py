"""Data-only wheel staging, never installation, approval or native qualification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Protocol


SELECTED_COUNT = 220
SELECTED_BYTES = 4400067018
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", re.ASCII)
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\.whl", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_URL = re.compile(
    r"https://files\.pythonhosted\.org/packages/[0-9a-f]{2}/"
    r"[0-9a-f]{2}/[0-9a-f]{60}/([A-Za-z0-9][A-Za-z0-9_.+-]*\.whl)",
    re.ASCII,
)


@dataclass(frozen=True)
class WheelPin:
    name: str
    version: str
    filename: str
    size: int
    sha256: str
    url: str


@dataclass(frozen=True)
class StagingBounds:
    """Hard wire ceiling includes one reserved overflow-detection byte."""

    max_bytes: int
    max_chunks: int
    chunk_bytes: int
    deadline_seconds: float


class WheelResponse(Protocol):
    status: int
    url: str

    def read(self, max_bytes: int, remaining_seconds: float) -> bytes: ...

    def close(self) -> None: ...


class WheelTransport(Protocol):
    """Trusted host transport: one GET, no redirects/retries, bounded reads.

    open_once/read/close must finish within the supplied remaining deadline;
    read must not buffer/return more than max_bytes. TLS verification, no proxy
    host substitution and exact URL targeting are the admitted host's duties.
    A response's self-reported URL alone is not proof of transport behavior.
    """

    def open_once(self, url: str, remaining_seconds: float) -> WheelResponse: ...


Authorization = Callable[[tuple[WheelPin, ...], Path, StagingBounds], None]


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_pins(pins: tuple[WheelPin, ...]) -> None:
    _require(0 < len(pins) <= SELECTED_COUNT, "wheel count outside bounds")
    names: set[str] = set()
    filenames: set[str] = set()
    for pin in pins:
        _require(type(pin) is WheelPin, "WheelPin required")
        for value in (pin.name, pin.version):
            _require(type(value) is str and len(value) <= 256
                     and _NAME.fullmatch(value), "invalid name/version")
        _require(type(pin.filename) is str and len(pin.filename) <= 255
                 and _FILENAME.fullmatch(pin.filename), "unsafe wheel filename")
        _require(type(pin.size) is int and 0 < pin.size <= SELECTED_BYTES,
                 "invalid wheel size")
        _require(type(pin.sha256) is str and _SHA256.fullmatch(pin.sha256),
                 "invalid SHA256")
        _require(type(pin.url) is str and len(pin.url) <= 512, "invalid URL")
        match = _URL.fullmatch(pin.url)
        _require(match is not None and match[1] == pin.filename,
                 "exact official HTTPS wheel URL required")
        name = re.sub(r"[-_.]+", "-", pin.name).lower()
        _require(name not in names and pin.filename not in filenames,
                 "duplicate name or filename")
        names.add(name)
        filenames.add(pin.filename)


def pins_from_manifests(
    reselection: Mapping[str, object], selection: Mapping[str, object],
) -> tuple[WheelPin, ...]:
    """Close the two reviewed selected lists, without interpreting approval flags."""
    def selected(document):
        rows = document.get("selected")
        _require(type(rows) is list and len(rows) == SELECTED_COUNT,
                 "exact 220 selected rows required")
        result = []
        for row in rows:
            _require(isinstance(row, Mapping), "selected row must be a mapping")
            keys = ("name", "version", "filename", "size", "sha256", "url")
            _require(all(key in row for key in keys), "missing wheel pin field")
            result.append(WheelPin(*(row[key] for key in keys)))
        pins = tuple(result)
        _validate_pins(pins)
        _require(sum(pin.size for pin in pins) == SELECTED_BYTES,
                 "selected byte closure mismatch")
        return pins

    left, right = selected(reselection), selected(selection)
    _require({pin.filename: pin for pin in left} == {pin.filename: pin for pin in right},
             "v4/v2 exact artifact closure mismatch")
    for document, key, expected in (
        (reselection, "selected_count", SELECTED_COUNT),
        (reselection, "total_declared_wheel_bytes", SELECTED_BYTES),
        (selection, "expected_count", SELECTED_COUNT),
    ):
        _require(type(document.get(key)) is int and document[key] == expected,
                 f"{key} mismatch")
    return left


def stage_wheels(
    pins: tuple[WheelPin, ...], destination: Path, *, bounds: StagingBounds,
    authorize: Authorization | None = None, transport: WheelTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Path, ...]:
    """Stage once into a fresh private directory; every failure/partial is retained.

    authorize is an independently trusted host callback, not caller metadata.
    It must raise on denial and return None only after external approval of the
    exact pins/destination/bounds. No callback or transport is supplied by default.
    Only returned paths have completed byte verification; retained files from
    a raised call must never be consumed as successful acquisitions.
    """
    _require(type(pins) is tuple, "immutable pin tuple required")
    _validate_pins(pins)
    _require(type(bounds) is StagingBounds, "StagingBounds required")
    for value, ceiling in (
        (bounds.max_bytes, SELECTED_BYTES + 1), (bounds.max_chunks, 1000000),
        (bounds.chunk_bytes, 1048576),
    ):
        _require(type(value) is int and 0 < value <= ceiling, "invalid transfer bound")
    _require(type(bounds.deadline_seconds) in (int, float)
             and math.isfinite(bounds.deadline_seconds)
             and 0 < bounds.deadline_seconds <= 1800, "invalid deadline")
    _require(sum(pin.size for pin in pins) + 1 <= bounds.max_bytes,
             "wire budget needs declared bytes plus one overflow-detection byte")
    destination = Path(destination)
    _require(destination.is_absolute() and len(destination.parts) > 1
             and ".." not in destination.parts, "absolute non-traversing destination required")
    _require(callable(authorize), "trusted external authorization required")
    _require(transport is not None and callable(getattr(transport, "open_once", None)),
             "explicit trusted host transport required")
    started = clock()
    _require(type(started) in (int, float) and math.isfinite(started), "invalid clock")
    deadline = started + bounds.deadline_seconds
    previous = started

    def remaining():
        nonlocal previous
        now = clock()
        _require(type(now) in (int, float) and math.isfinite(now) and now >= previous,
                 "clock must be finite and monotonic")
        previous = now
        if now >= deadline:
            raise TimeoutError("wheel staging deadline exhausted")
        return deadline - now

    _require(authorize(pins, destination, bounds) is None,
             "authorization callback must return None, not approval metadata")
    remaining()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directories: list[int] = []
    chain: list[tuple[int, str, int]] = []
    files: list[tuple[int, WheelPin]] = []
    received_total = 0
    wire_bytes = 0
    reads = 0
    uid = os.getuid()
    primary: BaseException | None = None

    def identity(metadata):
        return metadata.st_dev, metadata.st_ino

    def custody():
        remaining()
        for parent, name, fd in chain:
            linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
            _require(stat.S_ISDIR(linked.st_mode)
                     and identity(linked) == identity(os.fstat(fd)),
                     "directory path identity changed")
        root = os.fstat(directories[-1])
        _require(root.st_uid == uid and stat.S_IMODE(root.st_mode) == 0o700,
                 "staging directory ownership/mode changed")

    def file_custody(fd, pin, size):
        custody()
        held = os.fstat(fd)
        linked = os.stat(pin.filename, dir_fd=directories[-1], follow_symlinks=False)
        _require(stat.S_ISREG(held.st_mode) and held.st_uid == uid
                 and held.st_nlink == 1 and stat.S_IMODE(held.st_mode) == 0o600
                 and held.st_size == size and stat.S_ISREG(linked.st_mode)
                 and identity(held) == identity(linked), "wheel custody changed")

    try:
        directories.append(os.open(destination.anchor, directory_flags))
        for component in destination.parts[1:-1]:
            parent = directories[-1]
            fd = os.open(component, directory_flags, dir_fd=parent)
            directories.append(fd)
            chain.append((parent, component, fd))
        parent = directories[-1]
        os.mkdir(destination.name, 0o700, dir_fd=parent)
        fd = os.open(destination.name, directory_flags, dir_fd=parent)
        directories.append(fd)
        chain.append((parent, destination.name, fd))
        custody()
        for pin in pins:
            custody()
            fd = os.open(
                pin.filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directories[-1],
            )
            files.append((fd, pin))
            size = 0
            digest = hashlib.sha256()
            file_custody(fd, pin, size)
            response = transport.open_once(pin.url, remaining())
            transfer_error: BaseException | None = None
            try:
                file_custody(fd, pin, size)
                _require(type(response.status) is int and response.status == 200
                         and response.url == pin.url, "redirect/status/URL refused")
                while True:
                    _require(reads < bounds.max_chunks, "total chunk/read budget exhausted")
                    limit = min(bounds.chunk_bytes, pin.size - size + 1,
                                bounds.max_bytes - wire_bytes)
                    _require(limit > 0, "wire byte budget exhausted")
                    reads += 1
                    chunk = response.read(limit, remaining())
                    file_custody(fd, pin, size)
                    _require(type(chunk) is bytes and len(chunk) <= limit,
                             "transport exceeded bounded byte read")
                    wire_bytes += len(chunk)
                    if not chunk:
                        break
                    _require(size + len(chunk) <= pin.size
                             and received_total + len(chunk) <= bounds.max_bytes,
                             "received byte overflow")
                    view = memoryview(chunk)
                    while view:
                        file_custody(fd, pin, size)
                        written = os.write(fd, view)
                        _require(written > 0, "zero-progress output write")
                        size += written
                        received_total += written
                        view = view[written:]
                    digest.update(chunk)
                _require(size == pin.size and digest.hexdigest() == pin.sha256,
                         "wheel size/hash mismatch")
                os.fsync(fd)
                file_custody(fd, pin, size)
            except BaseException as error:
                transfer_error = error
                raise
            finally:
                try:
                    response.close()
                except BaseException:
                    if transfer_error is None:
                        raise
                    transfer_error.add_note("wheel response cleanup failed")
            file_custody(fd, pin, size)
        # Re-read retained descriptors: a later host callback may mutate an earlier file.
        for fd, pin in files:
            file_custody(fd, pin, pin.size)
            os.lseek(fd, 0, os.SEEK_SET)
            digest = hashlib.sha256()
            size = 0
            while size < pin.size:
                file_custody(fd, pin, pin.size)
                chunk = os.read(fd, min(bounds.chunk_bytes, pin.size - size))
                _require(chunk, "staged file truncated")
                size += len(chunk)
                digest.update(chunk)
            file_custody(fd, pin, pin.size)
            _require(digest.hexdigest() == pin.sha256, "staged bytes mutated")
        custody()
        return tuple(destination / pin.filename for pin in pins)
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup_error: BaseException | None = None
        for fd in reversed([fd for fd, _ in files] + directories):
            try:
                os.close(fd)
            except BaseException as error:
                if primary is not None:
                    primary.add_note("wheel descriptor cleanup failed")
                elif cleanup_error is None:
                    cleanup_error = error
                else:
                    cleanup_error.add_note("wheel descriptor cleanup failed")
        if primary is None and cleanup_error is not None:
            raise cleanup_error
