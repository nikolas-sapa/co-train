"""Pinned Modal1.6.3 RAW transport, fixed completion envelope and B wire.

SOURCE-ONLY, UNRUN. Raw exec/readers/writers must run on Modal's synchronizer
loop. Only the outer runner's bridge has .aio; raw resources never do.
Iterator end is not delivery proof (V1 suppresses ExecTimeoutError). Both
launcher terminal records, SDK wait0, pipe iterator ends and deadline are
mandatory. No retries, provider construction, tensor imports or authority.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
import secrets
import time
from typing import Any, BinaryIO

CHUNK_BYTES = 65536
METADATA_LIMIT = 1048576
STDIN_DRAIN_BYTES = 8 * 1024**2
MANIFEST_RESPONSE_BUDGET = 8 * 1024**2
GPU_WINDOW_SECONDS = 1800
MAX_FILE_BYTES = 2 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3
MAX_MEMBERS = 10000
MAX_DEPTH = 32
_TERMINAL_LIMIT = 1024
_PYTHON = "/usr/local/bin/python3.12"
RPC_SERVE_ARGV = (_PYTHON, "-m", "train.qualification_file_rpc", "--serve")
RPC_ROOTS: Mapping[str, str] = {
    "source": "/opt/qualification/source",
    "model": "/opt/qualification/model",
    "data": "/opt/qualification/data",
    "wheels": "/opt/qualification/wheels",
    "output": "/var/tmp/qualification/output",
    "evidence": "/var/tmp/qualification/evidence",
    "request": "/var/tmp/qualification/request-input",
}
_CREATED_ROOTS = tuple(value for key, value in RPC_ROOTS.items() if key != "output")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class ExecStartAmbiguous(RuntimeError):
    """Process start may have happened; never reissue."""


class ExecAmbiguous(RuntimeError):
    """Deadline expired; cancellation is not termination evidence."""


class ExecOutputLimitExceeded(ValueError):
    """Payload or independently bounded framing exceeded its cap."""


@dataclass(frozen=True)
class ExecOutcome:
    returncode: int
    stdout_bytes: int
    stderr_bytes: int
    stdout_complete: bool
    stderr_complete: bool


@dataclass(frozen=True)
class PlannedUpload:
    root: str
    key: str
    size: int
    sha256: str
    path: Path


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("nonfinite or floating JSON value")


def _load_strict_json(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant, parse_float=_reject_constant)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("invalid bounded JSON") from error


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def _digest(value: Any) -> None:
    _require(type(value) is str and len(value) == 64
             and all(character in "0123456789abcdef" for character in value),
             "sha256 must be 64 lowercase hex characters")


def _integer(value: Any, cap: int, label: str) -> None:
    _require(type(value) is int and 0 <= value <= cap, f"{label}: bounded integer required")


def _validate_key(key: str) -> None:
    _require(type(key) is str, "key must be a string")
    parts = key.split("/")
    _require(0 < len(key.encode("utf-8")) <= 4096 and len(parts) <= 64
             and "\\" not in key and "\0" not in key
             and all(part not in ("", ".", "..") and len(part.encode("utf-8")) <= 255
                     for part in parts), "noncanonical key")


def _validate_root(root: str) -> None:
    _require(type(root) is str and root in RPC_ROOTS, "fixed RPC root required")


def _frame(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


def rpc_put_frames(root: str, key: str, size: int, sha256: str,
                   source: BinaryIO) -> Iterator[bytes]:
    """B framing from a retained validated snapshot ONLY, no generic streams."""
    _validate_root(root)
    _validate_key(key)
    _integer(size, MAX_FILE_BYTES, "size")
    _digest(sha256)
    from train.qualification_engineering_run import _Snapshot
    _require(type(source) is _Snapshot, "put requires a fully validated retained snapshot")
    _require((source.root, source.key, source.size, source.sha256) == (root, key, size, sha256),
             "put snapshot binding differs")
    source.rewind()
    yield _frame(_canonical_json(dict(v=1, op="put", root=root, key=key,
                                     size=size, sha256=sha256)))
    remaining, digest = size, hashlib.sha256()
    while remaining:
        block = source.read(min(remaining, CHUNK_BYTES))
        _require(type(block) is bytes and 0 < len(block) <= min(remaining, CHUNK_BYTES),
                 "upload source ended early or returned excessive bytes")
        remaining -= len(block)
        digest.update(block)
        yield _frame(block)
    _require(source.read(1) == b"", "upload source exceeds declared size")
    _require(digest.hexdigest() == sha256, "upload source hash differs")
    yield _frame(b"")


def rpc_get_metadata(root: str, key: str, size: int, sha256: str) -> dict[str, Any]:
    _validate_root(root)
    _validate_key(key)
    _integer(size, MAX_FILE_BYTES, "size")
    _digest(sha256)
    return dict(v=1, op="get", root=root, key=key, size=size, sha256=sha256)


def rpc_manifest_metadata(root: str, *, max_bytes: int, max_members: int,
                          max_depth: int) -> dict[str, Any]:
    _require(root == "output", "manifest root must be output")
    _integer(max_bytes, MAX_TOTAL_BYTES, "max_bytes")
    _integer(max_members, MAX_MEMBERS, "max_members")
    _integer(max_depth, MAX_DEPTH, "max_depth")
    return dict(v=1, op="manifest", root=root, max_bytes=max_bytes,
                max_members=max_members, max_depth=max_depth)


def rpc_request_frames(metadata: dict[str, Any]) -> Iterator[bytes]:
    _require(type(metadata) is dict and type(metadata.get("v")) is int
             and metadata["v"] == 1, "RPC version required")
    if metadata.get("op") == "get":
        expected = rpc_get_metadata(metadata["root"], metadata["key"],
                                    metadata["size"], metadata["sha256"])
    else:
        _require(metadata.get("op") == "manifest", "metadata-only operation refused")
        expected = rpc_manifest_metadata(metadata["root"], max_bytes=metadata["max_bytes"],
                                         max_members=metadata["max_members"],
                                         max_depth=metadata["max_depth"])
    _require(metadata == expected and set(metadata) == set(expected), "request keys refused")
    yield _frame(_canonical_json(metadata))
    yield _frame(b"")


class RPCResponseDecoder:
    """Incremental B decoder. Retains metadata <=1MiB, never retains file bodies."""

    def __init__(self, op: str, sink: Callable[[bytes], None], *,
                 expected_size: int | None = None, expected_sha256: str | None = None):
        _require(op in ("put", "get", "manifest"), "response operation refused")
        if expected_size is not None:
            _integer(expected_size, MAX_TOTAL_BYTES, "expected_size")
        if expected_sha256 is not None:
            _digest(expected_sha256)
        self.op, self.sink = op, sink
        self.expected_size, self.expected_sha256 = expected_size, expected_sha256
        self.metadata: dict[str, Any] | None = None
        self._buffer = bytearray()
        self._needed, self._state = 4, "metadata-length"
        self._count, self._hash = 0, hashlib.sha256()
        self._frames = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def __call__(self, chunk: bytes) -> None:
        _require(type(chunk) is bytes, "RPC chunk must be bytes")
        view = memoryview(chunk)
        while view:
            _require(self._state != "done", "RPC trailing bytes")
            take = min(self._needed - len(self._buffer), len(view))
            self._buffer.extend(view[:take])
            view = view[take:]
            if len(self._buffer) != self._needed:
                continue
            value = bytes(self._buffer)
            self._buffer.clear()
            if self._state.endswith("length"):
                length = int.from_bytes(value, "big")
                if self._state == "metadata-length":
                    _require(1 <= length <= METADATA_LIMIT, "metadata length out of bounds")
                    self._state, self._needed = "metadata", length
                elif length == 0:
                    self._state = "done"
                else:
                    _require(length <= CHUNK_BYTES, "data frame length out of bounds")
                    self._frames += 1
                    _require(self._frames <= MAX_TOTAL_BYTES, "too many RPC frames")
                    self._state, self._needed = "data", length
            elif self._state == "metadata":
                meta = _load_strict_json(value)
                _require(type(meta) is dict and set(meta) == {"v", "ok", "op", "size", "sha256"}
                         and type(meta["v"]) is int and meta["v"] == 1
                         and meta["ok"] is True and type(meta["op"]) is str
                         and meta["op"] == self.op, "response metadata refused")
                _integer(meta["size"], MAX_TOTAL_BYTES, "declared size")
                _digest(meta["sha256"])
                if self.expected_size is not None:
                    _require(meta["size"] == self.expected_size, "declared size differs from pin")
                if self.expected_sha256 is not None:
                    _require(meta["sha256"] == self.expected_sha256, "declared hash differs from pin")
                if self.op == "put":
                    _require(meta["size"] == 0 and meta["sha256"] == _EMPTY_SHA256,
                             "put acknowledgement must be empty")
                self.metadata = meta
                self._state, self._needed = "data-length", 4
            else:
                self._count += len(value)
                _require(self.metadata is not None and self._count <= self.metadata["size"],
                         "body exceeds declared size")
                self._hash.update(value)
                self.sink(value)
                self._state, self._needed = "data-length", 4

    def finish(self) -> dict[str, Any]:
        _require(self._state == "done" and not self._buffer and self.metadata is not None,
                 "RPC truncated before terminator/EOF")
        _require(self._count == self.metadata["size"], "body size differs from declaration")
        _require(self._hash.hexdigest() == self.metadata["sha256"],
                 "body hash differs from declaration")
        if self.expected_size is not None:
            _require(self._count == self.expected_size, "body size differs from pin")
        if self.expected_sha256 is not None:
            _require(self._hash.hexdigest() == self.expected_sha256, "body hash differs from pin")
        return self.metadata


def parse_rpc_response(payload: bytes, *, op: str, expected_size: int | None = None,
                       expected_sha256: str | None = None) -> tuple[dict[str, Any], bytes]:
    """Small control responses only; artifacts must use the streaming decoder."""
    _require(type(payload) is bytes, "RPC response must be bytes")
    body = _ResponseAccumulator(min(len(payload) + 1, MANIFEST_RESPONSE_BUDGET))
    decoder = RPCResponseDecoder(op, body, expected_size=expected_size,
                                 expected_sha256=expected_sha256)
    decoder(payload)
    return decoder.finish(), body.payload


def parse_put_ack(payload: bytes) -> None:
    parse_rpc_response(payload, op="put", expected_size=0, expected_sha256=_EMPTY_SHA256)


def parse_manifest_body(body: bytes, *, max_bytes: int = MAX_TOTAL_BYTES,
                        max_members: int = MAX_MEMBERS, max_depth: int = MAX_DEPTH,
                        json_limit: int = MANIFEST_RESPONSE_BUDGET) -> tuple[dict[str, Any], ...]:
    for value, cap, label in ((max_bytes, MAX_TOTAL_BYTES, "aggregate"),
                              (max_members, MAX_MEMBERS, "members"),
                              (max_depth, MAX_DEPTH, "depth"),
                              (json_limit, MANIFEST_RESPONSE_BUDGET, "JSON")):
        _integer(value, cap, label)
    _require(type(body) is bytes and len(body) <= json_limit, "manifest JSON bound exceeded")
    entries = _load_strict_json(body)
    _require(type(entries) is list and len(entries) <= max_members, "manifest member bound exceeded")
    total, previous = 0, None
    file_keys, directory_keys = set(), set()
    for entry in entries:
        _require(type(entry) is dict and set(entry) == {"key", "size", "sha256"},
                 "manifest member keys refused")
        _validate_key(entry["key"])
        _integer(entry["size"], MAX_FILE_BYTES, "member size")
        _digest(entry["sha256"])
        _require(len(entry["key"].split("/")) - 1 <= max_depth, "manifest depth exceeded")
        _require(previous is None or previous < entry["key"], "manifest duplicate or unordered key")
        parts = entry["key"].split("/")
        parents = {"/".join(parts[:index]) for index in range(1, len(parts))}
        _require(entry["key"] not in directory_keys and not parents.intersection(file_keys),
                 "manifest file/directory alias")
        file_keys.add(entry["key"])
        directory_keys.update(parents)
        previous = entry["key"]
        total += entry["size"]
        _require(total <= max_bytes, "manifest aggregate bound exceeded")
    _require(body == _canonical_json(entries), "manifest must be canonical JSON")
    return tuple(entries)


def response_budget(expected_size: int) -> int:
    _integer(expected_size, MAX_TOTAL_BYTES, "expected size")
    # B permits short data frames; one-byte frames are the worst allowed case.
    return 4 + METADATA_LIMIT + 5 * expected_size + 4


class _ResponseAccumulator:
    """Small control messages only. Artifact GETs use RPCResponseDecoder directly."""

    def __init__(self, cap: int):
        _require(type(cap) is int and 0 < cap <= MANIFEST_RESPONSE_BUDGET,
                 "control accumulator cap must be within 8MiB")
        self._cap, self._buffer = cap, bytearray()

    def __call__(self, chunk: bytes) -> None:
        _require(type(chunk) is bytes and len(self._buffer) + len(chunk) <= self._cap,
                 "response exceeded framing budget")
        self._buffer.extend(chunk)

    @property
    def payload(self) -> bytes:
        return bytes(self._buffer)


def _launch_enveloped(argv, nonce, stdout_limit, stderr_limit, *,
                      _popen=None, _stdout=None, _stderr=None):
    """Fixed outer launcher, not a native phase supervisor or command CLI.

    Its source is embedded with one fixed approved invocation. No command is
    read from argv/stdin/environment. Child stdin is inherited unchanged.
    """
    import hashlib
    import json
    import subprocess
    import sys
    import threading

    popen = subprocess.Popen if _popen is None else _popen
    outputs = (sys.stdout.buffer if _stdout is None else _stdout,
               sys.stderr.buffer if _stderr is None else _stderr)
    child = popen(argv, stdin=sys.stdin.buffer, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, shell=False, close_fds=True, cwd="/")
    states = [{"size": 0, "hash": hashlib.sha256(), "eof": False} for _ in range(2)]
    errors = []

    def write_all(out, data):
        view = memoryview(data)
        while view:
            count = out.write(view[:65536])
            if type(count) is not int or not 0 < count <= min(len(view), 65536):
                raise ValueError("outer pipe write made no progress")
            view = view[count:]
        out.flush()

    def drain(index, pipe, cap):
        try:
            # Buffered pipe read fills this fixed block or reaches actual EOF.
            # Thus framing overhead is independently bounded by ceil(cap/64KiB).
            while True:
                block = pipe.read(65536)
                if type(block) is not bytes or len(block) > 65536:
                    raise ValueError("child pipe type/length refused")
                if not block:
                    states[index]["eof"] = True
                    return
                states[index]["size"] += len(block)
                if states[index]["size"] > cap:
                    raise ValueError("child payload cap exceeded")
                states[index]["hash"].update(block)
                write_all(outputs[index], b"D" + len(block).to_bytes(4, "big") + block)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=drain, args=(index, pipe, cap), daemon=True)
               for index, (pipe, cap) in enumerate(
                   ((child.stdout, stdout_limit), (child.stderr, stderr_limit)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    code = child.wait()
    if errors or type(code) is not int or not all(state["eof"] for state in states):
        return 1
    # Neither terminal is emitted until ACTUAL child wait AND both pipe EOFs.
    for index, stream in enumerate(("stdout", "stderr")):
        record = dict(v=1, nonce=nonce, stream=stream, size=states[index]["size"],
                      sha256=states[index]["hash"].hexdigest(), returncode=code)
        body = json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("ascii")
        if len(body) > 1024:
            return 1
        write_all(outputs[index], b"T" + len(body).to_bytes(4, "big") + body)
    return 0 if code == 0 else 1


def _launcher_argv(argv: tuple[str, ...], nonce: str, stdout_limit: int,
                   stderr_limit: int) -> tuple[str, ...]:
    spec = dict(argv=list(argv), nonce=nonce, stdout_limit=stdout_limit,
                stderr_limit=stderr_limit)
    # Source is from this approved first-party module, not caller code. The
    # data literal has no CLI/eval surface; the launcher has no command parser.
    code = (inspect.getsource(_launch_enveloped)
            + "\n# qualification-envelope-v1 " + _canonical_json(spec).decode("ascii")
            + "\nraise SystemExit(_launch_enveloped("
            + repr(tuple(argv)) + "," + repr(nonce) + ","
            + repr(stdout_limit) + "," + repr(stderr_limit) + "))\n")
    return (_PYTHON, "-c", code)


def _launcher_spec(argv: tuple[str, ...]) -> dict[str, Any]:
    """Read-only unit seam, no source evaluation."""
    _require(argv[:2] == (_PYTHON, "-c") and len(argv) == 3, "fixed launcher argv required")
    marker = "# qualification-envelope-v1 "
    lines = [line[len(marker):] for line in argv[2].splitlines() if line.startswith(marker)]
    _require(len(lines) == 1, "fixed launcher spec required")
    return _load_strict_json(lines[0].encode("ascii"))


class _EnvelopeDecoder:
    def __init__(self, nonce: str, stream: str, limit: int,
                 sink: Callable[[bytes], None] | None):
        self.nonce, self.stream, self.limit, self.sink = nonce, stream, limit, sink
        self.count, self._hash = 0, hashlib.sha256()
        self._buffer, self._needed, self._state = bytearray(), 5, "header"
        self._kind, self._terminal = None, None
        self._frames, self._wire = 0, 0
        self._frame_cap = (limit + CHUNK_BYTES - 1) // CHUNK_BYTES + 1
        self._wire_cap = limit + 5 * self._frame_cap + 5 + _TERMINAL_LIMIT

    def __call__(self, chunk: bytes) -> None:
        _require(type(chunk) is bytes, "exec stream yielded non-bytes")
        self._wire += len(chunk)
        if self._wire > self._wire_cap:
            raise ExecOutputLimitExceeded("exec framing cap exceeded")
        view = memoryview(chunk)
        while view:
            _require(self._terminal is None, "duplicate terminal or trailing bytes")
            take = min(self._needed - len(self._buffer), len(view))
            self._buffer.extend(view[:take])
            view = view[take:]
            if len(self._buffer) != self._needed:
                continue
            value = bytes(self._buffer)
            self._buffer.clear()
            if self._state == "header":
                self._kind, length = value[:1], int.from_bytes(value[1:], "big")
                _require(self._kind in (b"D", b"T"), "invalid envelope frame kind")
                cap = CHUNK_BYTES if self._kind == b"D" else _TERMINAL_LIMIT
                _require(1 <= length <= cap, "envelope frame length refused")
                self._state, self._needed = "body", length
            elif self._kind == b"D":
                self._frames += 1
                if self._frames > self._frame_cap:
                    raise ExecOutputLimitExceeded("exec framing count cap exceeded")
                self.count += len(value)
                if self.count > self.limit:
                    raise ExecOutputLimitExceeded("exec payload cap exceeded")
                self._hash.update(value)
                if self.sink is not None:
                    self.sink(value)
                self._state, self._needed = "header", 5
            else:
                record = _load_strict_json(value)
                _require(type(record) is dict and set(record) == {
                    "v", "nonce", "stream", "size", "sha256", "returncode"},
                    "terminal keys refused")
                _require(type(record["v"]) is int and record["v"] == 1
                         and type(record["nonce"]) is str and record["nonce"] == self.nonce
                         and type(record["stream"]) is str and record["stream"] == self.stream,
                         "terminal version/nonce/stream differs")
                _integer(record["size"], self.limit, "terminal size")
                _digest(record["sha256"])
                _require(type(record["returncode"]) is int, "terminal child status must be integer")
                _require(record["size"] == self.count
                         and record["sha256"] == self._hash.hexdigest(),
                         "terminal payload count/hash differs")
                self._terminal = record

    def finish(self) -> int:
        _require(self._terminal is not None and not self._buffer,
                 "missing or truncated terminal record")
        return self._terminal["returncode"]


def _initialize_roots(initial=False, directories=()):
    """Self-contained fixed bootstrap initialization, never creates output."""
    import os
    import stat

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    paths = ("/opt/qualification/source", "/opt/qualification/model",
             "/opt/qualification/data", "/opt/qualification/wheels",
             "/var/tmp/qualification/evidence", "/var/tmp/qualification/request-input")
    paths = paths + tuple(directories)
    root = os.open("/", flags)
    retained, pins, opened_paths = [root], [], {"/": root}
    try:
        for path in paths:
            fd, prefix = root, ""
            for name in path.split("/")[1:]:
                prefix += "/" + name
                if prefix in opened_paths:
                    fd = opened_paths[prefix]
                    continue
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                before = os.stat(name, dir_fd=fd, follow_symlinks=False)
                child = os.open(name, flags, dir_fd=fd)
                retained.append(child)
                opened = os.fstat(child)
                if (not stat.S_ISDIR(opened.st_mode)
                        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                    raise ValueError("bootstrap directory identity changed")
                pins.append((fd, name, child))
                opened_paths[prefix] = child
                fd = child
        for parent, name, child in pins:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("bootstrap directory redirected")
        if initial:
            # /var/tmp/qualification/output must remain absent.
            try:
                os.stat("output", dir_fd=opened_paths["/var/tmp/qualification"],
                        follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("unexpected existing native output")
    finally:
        for fd in reversed(retained):
            os.close(fd)


def _bootstrap_argv(source: bytes, sha256: str, *, initial: bool = False,
                    directories: tuple[str, ...] = ()) -> tuple[str, ...]:
    _digest(sha256)
    _require(type(source) is bytes and 0 < len(source) <= METADATA_LIMIT
             and hashlib.sha256(source).hexdigest() == sha256,
             "approved B source SHA differs")
    for directory in directories:
        _require(any(directory.startswith(RPC_ROOTS[root] + "/")
                     for root in ("source", "model", "data", "wheels", "request")),
                 "bootstrap only creates approved upload ancestors inside fixed roots")
        _validate_key(directory.lstrip("/"))
    code = (inspect.getsource(_initialize_roots)
            + "\n_initialize_roots(initial=" + repr(initial)
            + ",directories=" + repr(directories) + ")\n"
            + "import sys\nsys.argv=['qualification_file_rpc.py','--serve']\n"
            + "exec(compile(" + repr(source) + ",'train/qualification_file_rpc.py','exec'),"
            + "{'__name__':'__main__'})\n")
    return (_PYTHON, "-c", code)


def _materialize_request(expected_sha256):
    """Fixed anchored bounded request copy, with complete writes and rehash."""
    import hashlib
    import os
    import stat

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fds, pins = [], []

    def directory(path):
        fd = os.open("/", flags)
        fds.append(fd)
        for name in path.split("/")[1:]:
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            child = os.open(name, flags, dir_fd=fd)
            opened = os.fstat(child)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(child)
                raise ValueError("request ancestor changed")
            pins.append((fd, name, child))
            fds.append(child)
            fd = child
        return fd

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def check():
        for parent, name, child in pins:
            named, opened = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("request ancestor redirected")

    def hash_fd(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        digest, count = hashlib.sha256(), 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            count += len(block)
            if count > 1048576:
                raise ValueError("request exceeds 1MiB")
            digest.update(block)
        return count, digest.hexdigest()

    try:
        parent = directory("/var/tmp/qualification")
        source_parent = directory("/var/tmp/qualification/request-input")
        try:
            os.stat("output", dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("native output must remain absent")
        before = os.stat("request.json", dir_fd=source_parent, follow_symlinks=False)
        src = os.open("request.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_parent)
        fds.append(src)
        opened = os.fstat(src)
        if (identity(before) != identity(opened) or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1 or opened.st_size > 1048576):
            raise ValueError("request source identity refused")
        dst = os.open("request.json", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=parent)
        fds.append(dst)
        created = os.fstat(dst)
        digest, count = hashlib.sha256(), 0
        while True:
            block = os.read(src, 65536)
            if not block:
                break
            count += len(block)
            if count > 1048576:
                raise ValueError("request size exceeded")
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(dst, view)
                if not 0 < written <= len(view):
                    raise ValueError("request copy made no progress")
                view = view[written:]
        os.fsync(dst)
        before_disk = os.fstat(dst)
        disk_bytes = hash_fd(dst)
        final = os.fstat(dst)
        named = os.stat("request.json", dir_fd=parent, follow_symlinks=False)
        check()
        if (identity(opened) != identity(os.fstat(src))
                or identity(opened) != identity(os.stat("request.json", dir_fd=source_parent,
                                                       follow_symlinks=False))
                or digest.hexdigest() != expected_sha256
                or disk_bytes != (count, expected_sha256)
                or identity(before_disk) != identity(final)
                or identity(final) != identity(named)
                or (created.st_dev, created.st_ino) != (final.st_dev, final.st_ino)
                or not stat.S_ISREG(final.st_mode) or final.st_nlink != 1
                or final.st_size != count or stat.S_IMODE(final.st_mode) != 0o600):
            raise ValueError("request final bytes/identity differ")
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _mode_argv(mode: str) -> tuple[str, ...]:
    _require(mode in ("--native", "--verify"), "fixed worker mode required")
    code = ("import os,runpy,sys\nos.chdir('/opt/qualification/source')\n"
            "sys.path.insert(0,'/opt/qualification/source')\n"
            "sys.argv=['train.qualification_engineering_run'," + repr(mode) + "]\n"
            "runpy.run_module('train.qualification_engineering_run',run_name='__main__')\n")
    return (_PYTHON, "-c", code)


class ModalExecTransport:
    """Only host.resource is authority for the exact retained raw Sandbox."""

    def __init__(self, host: Any, *, clock: Callable[[], float] | None = None):
        self._host, self._clock = host, time.monotonic if clock is None else clock
        self._sandbox = getattr(host, "resource", None)
        self._poisoned: str | None = None
        self._allowed = {RPC_SERVE_ARGV, _mode_argv("--native"), _mode_argv("--verify")}
        self._rpc_initial: tuple[str, ...] | None = None
        self._rpc: tuple[str, ...] | None = None
        self.materialize_argv: tuple[str, ...] | None = None

    @property
    def sandbox(self) -> object:
        return self._sandbox

    @sandbox.setter
    def sandbox(self, value: object) -> None:
        _require(value is not None and value is getattr(self._host, "resource", None),
                 "explicit Sandbox must be identical to host.resource")
        _require(self._sandbox is None or self._sandbox is value, "Sandbox already bound")
        self._sandbox = value

    @property
    def poisoned(self) -> str | None:
        return self._poisoned

    def bind_runtime(self, *, rpc_source: bytes, rpc_sha256: str,
                     setup_argv: tuple[str, ...], request_sha256: str,
                     uploads: Any = ()) -> None:
        self._host.require_setup_argv(setup_argv)
        _digest(request_sha256)
        # B deliberately does not mkdir during put. These are only the necessary
        # ancestors of the already sealed/frozen upload destinations, not a
        # caller-selected root or a general remote directory service.
        directories = set()
        for item in uploads:
            _validate_key(item.key)
            _require(item.root in ("source", "model", "data", "wheels", "request"),
                     "bootstrap upload root refused")
            if "/" in item.key:
                directories.add(RPC_ROOTS[item.root] + "/" + item.key.rsplit("/", 1)[0])
        self._rpc_initial = _bootstrap_argv(
            rpc_source, rpc_sha256, initial=True, directories=tuple(sorted(directories)))
        self._rpc = _bootstrap_argv(rpc_source, rpc_sha256)
        code = (inspect.getsource(_materialize_request)
                + "\n_materialize_request(" + repr(request_sha256) + ")\n")
        self.materialize_argv = (_PYTHON, "-c", code)
        self._allowed.update((self._rpc_initial, self._rpc, self.materialize_argv, setup_argv))

    async def exec_once(self, argv: tuple[str, ...] | list[str], *, input_chunks: Any = (),
                        stdout_sink: Callable[[bytes], None] | None = None,
                        stdout_limit: int, stderr_limit: int, deadline: float) -> ExecOutcome:
        _require(self._poisoned is None, "transport poisoned by incomplete prior exec")
        _require(type(argv) in (tuple, list) and bool(argv)
                 and all(type(value) is str and value for value in argv), "invalid argv")
        argv = tuple(argv)
        _require(argv in self._allowed, "invocation is not a fixed approved operation")
        for cap in (stdout_limit, stderr_limit):
            _require(type(cap) is int and 0 < cap <= response_budget(MAX_TOTAL_BYTES),
                     "positive bounded stream cap required")
        _require(type(deadline) is float and math.isfinite(deadline)
                 and deadline > self._clock(), "finite future deadline required")
        _require(self._sandbox is not None
                 and self._sandbox is getattr(self._host, "resource", None),
                 "no retained Sandbox bound")
        remaining = deadline - self._clock()
        nonce = secrets.token_hex(32)
        wrapped = _launcher_argv(argv, nonce, stdout_limit, stderr_limit)
        try:
            process = await asyncio.wait_for(
                self._sandbox.exec(*wrapped, text=False, timeout=max(1, math.ceil(remaining)),
                                   workdir="/"), remaining)
        except asyncio.CancelledError:
            self._poisoned = "exec start cancelled, resource may exist"
            raise
        except BaseException as error:
            self._poisoned = "exec start ambiguous"
            raise ExecStartAmbiguous("exec start ambiguous; never reissued") from error
        out = _EnvelopeDecoder(nonce, "stdout", stdout_limit, stdout_sink)
        err = _EnvelopeDecoder(nonce, "stderr", stderr_limit, None)

        async def pump(reader: Any, decoder: _EnvelopeDecoder) -> None:
            async for block in reader:
                decoder(block)
            decoder.finish()

        async def feed() -> None:
            buffered = 0
            async for block in _maybe_async_iter(input_chunks):
                _require(isinstance(block, (bytes, bytearray, memoryview)) and len(block) > 0,
                         "stdin requires nonempty bytes-like chunks")
                view = memoryview(block)
                while view:
                    piece = bytes(view[:CHUNK_BYTES])
                    view = view[len(piece):]
                    if buffered + len(piece) > STDIN_DRAIN_BYTES:
                        await process.stdin.drain()
                        buffered = 0
                    process.stdin.write(piece)
                    buffered += len(piece)
            process.stdin.write_eof()
            await process.stdin.drain()

        tasks = [asyncio.create_task(feed()), asyncio.create_task(pump(process.stdout, out)),
                 asyncio.create_task(pump(process.stderr, err)), asyncio.create_task(process.wait())]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), max(0.0, deadline - self._clock()))
            code = tasks[-1].result()
            _require(type(code) is int and code == 0, "SDK wait must actually return integer0")
            _require(out.finish() == err.finish() == 0, "actual child status is nonzero")
            _require(self._clock() < deadline, "exec deadline expired")
            return ExecOutcome(code, out.count, err.count, True, True)
        except BaseException as error:
            self._poisoned = "incomplete exec; never reissued"
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(error, TimeoutError):
                raise ExecAmbiguous("deadline expired; cancellation is not termination evidence") from error
            raise

    async def _rpc_once(self, frames: Any, decoder: RPCResponseDecoder, *,
                        limit: int, deadline: float) -> None:
        _require(self._rpc is not None and self._rpc_initial is not None,
                 "approved B bootstrap not bound")
        argv, self._rpc_initial = self._rpc_initial, self._rpc
        await self.exec_once(argv, input_chunks=frames, stdout_sink=decoder,
                             stdout_limit=limit, stderr_limit=65536, deadline=deadline)
        decoder.finish()

    async def stage_uploads(self, items: Any, *, deadline: float) -> None:
        for item in items:
            item.check()
            item.rewind()
            decoder = RPCResponseDecoder("put", lambda block: None, expected_size=0,
                                          expected_sha256=_EMPTY_SHA256)
            await self._rpc_once(rpc_put_frames(item.root, item.key, item.size,
                                                item.sha256, item), decoder,
                                 limit=METADATA_LIMIT + 8, deadline=deadline)
            item.check()

    async def get_to(self, root: str, entry: Mapping[str, Any],
                     sink: Callable[[bytes], None], *, deadline: float) -> None:
        decoder = RPCResponseDecoder("get", sink, expected_size=entry["size"],
                                      expected_sha256=entry["sha256"])
        await self._rpc_once(rpc_request_frames(rpc_get_metadata(
            root, entry["key"], entry["size"], entry["sha256"])), decoder,
            limit=response_budget(entry["size"]), deadline=deadline)

    async def output_manifest(self, *, max_bytes: int, deadline: float) -> tuple[dict[str, Any], ...]:
        sink = _ResponseAccumulator(MANIFEST_RESPONSE_BUDGET)
        decoder = RPCResponseDecoder("manifest", sink)
        await self._rpc_once(rpc_request_frames(rpc_manifest_metadata(
            "output", max_bytes=max_bytes, max_members=MAX_MEMBERS, max_depth=MAX_DEPTH)),
            decoder, limit=response_budget(MANIFEST_RESPONSE_BUDGET), deadline=deadline)
        return parse_manifest_body(sink.payload, max_bytes=max_bytes)


async def _maybe_async_iter(source: Any) -> AsyncIterator[bytes]:
    if hasattr(source, "__aiter__"):
        async for item in source:
            yield item
    else:
        for item in source:
            yield item
