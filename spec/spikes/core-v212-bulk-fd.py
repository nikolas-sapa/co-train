#!/usr/bin/env python3
"""V212 bulk FD handoff spike: SOURCEONLY UNRUN, parent-owned execution.

One unknown: can a genuine fresh worker consume, through inherited READONLY file
descriptors, both the original-request payload and a large canonical manifest,
while every control record stays <= 8192 bytes?

Modes
    python3 core-v212-bulk-fd.py                     parent harness, 7 cases
    python3 core-v212-bulk-fd.py --_v212-worker ...  one fresh Popen worker

The worker is case-agnostic. Cases differ only in what the parent puts on the
descriptors and in the expected facts it sends over control, so the same worker
code that accepts C1/C2 refuses C3-C7 on observed evidence.

Genuine first-party reuse (see docs/core-v212-bulk-fd-plan.md section 3):
QualificationRequest, FilePin, AttemptBounds, SqlTask, TIERS, _signature,
_asset_path, _pairs, _closed, _path, _validate_bounds, _check_asset_bytes,
_bounds_from_wire, _WIRE_LIMIT, _FIXTURES are imported and called.
_prepare_worker_transport is NOT
usable standalone (blocker B1) and its format is 1 MiB capped (blocker B2), so the
request descriptor carries a disclosed spike-local projection of a genuine
QualificationRequest, not the original native-sql-worker-v1 document.

Nothing here was executed. No test, import, command or subprocess was run to
produce this file.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path, PurePosixPath

_SELF = Path(__file__).resolve()
_REPO = _SELF.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Captured before the genuine-shape import below, so the run budget honestly
# includes the cost of importing bench.task and train.native_qualification.
_MODULE_LOAD = time.monotonic()

# Blocker reporting, never silent substitution. If the genuine shapes cannot be
# imported, both entry points exit with BLOCKED and the exact exception text.
_ORIGINAL_BLOCKER = ""
try:
    from bench.task import TIERS, SqlTask
    from train.native_qualification import (
        _FIXTURES,
        _WIRE_LIMIT,
        _asset_path,
        _bounds_from_wire,
        _check_asset_bytes,
        _closed,
        _pairs,
        _path,
        _signature,
        _validate_bounds,
        AttemptBounds,
        FilePin,
        QualificationRequest,
    )
except BaseException as _error:  # noqa: BLE001 - reported verbatim, never papered over
    _ORIGINAL_BLOCKER = f"{type(_error).__name__}: {_error}"
    # Only so this module stays importable; both entry points exit BLOCKED below
    # and never reach a use of any genuine shape.
    _WIRE_LIMIT = 1048576

# --------------------------------------------------------------------------
# Numeric limits. Every value is from the brief, the original source, or the
# arithmetic derived in the plan. Nothing is a stand-in for an observation.
# --------------------------------------------------------------------------

CONTROL_MAX_FRAME = 8192            # brief: control records <= 8192
MANIFEST_BYTE_CAP = 8388608         # brief
MANIFEST_COUNT_CAP = 10000          # brief
REQUEST_BYTE_CAP = _WIRE_LIMIT        # original, line 36: 1048576
NAME_LIMIT = 256                    # original _asset_path, line 307
MEMBER_SIZE = 1048576               # 7 digits, inside original 0..2*1024**3
MEMBER_ROOT = "source"              # original kind selector for _SOURCE
MEMBER_FIELDS = frozenset({"key", "root", "sha256", "size", "snapshot_key"})

# Derived, not hard-coded: measured from the empty-variable template so that a
# change in json formatting refuses the run instead of skewing byte counts.
_TEMPLATE = {"key": "", "root": MEMBER_ROOT, "sha256": "",
             "size": MEMBER_SIZE, "snapshot_key": ""}


def _dumps(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=True, allow_nan=False).encode("ascii")


FIXED_MEMBER_BYTES = len(_dumps(_TEMPLATE))
# Expected length of
#   {"key":"","root":"source","sha256":"","size":1048576,"snapshot_key":""}
# counted field by field: 1 brace + 8 ("key":"") + 1 comma + 15 ("root":"source")
# + 1 comma + 11 ("sha256":"") + 1 comma + 14 ("size":1048576) + 1 comma
# + 17 ("snapshot_key":"") + 1 brace = 71.
EXPECTED_FIXED_MEMBER_BYTES = 71
# 1 ("[") + members + sum(FIXED + len(key) + len(snapshot_key)) + 1 ("]") - 1
WORST_VALID_MANIFEST_BYTES = 1 + MANIFEST_COUNT_CAP * (1 + FIXED_MEMBER_BYTES + 2 * NAME_LIMIT)

POPEN_TOTAL = 7                     # brief: at most 7 workers
CASE_BUDGET_S = 2.50                # brief, fixtures included
RUN_BUDGET_S = 8.00                 # brief, strict <
OP_S = 2.00                         # brief, marker operation
CHALLENGE_S = 0.50                  # brief, control challenge
STOP_S = 1.00                       # brief, containment kill+reap
TERM_PROBE_S = 0.15
TEARDOWN_RESERVE_S = 0.25
SELECT_SLICE_S = 0.10
MIN_WAIT_S = 0.02
STDERR_CAP = 2000

EXIT_OK = 0
EXIT_HARNESS = 1
EXIT_INTERNAL = 2
EXIT_CHANNEL = 3
EXIT_PROTOCOL = 4
EXIT_REQUEST = 5
EXIT_MANIFEST_MODE = 6
EXIT_MANIFEST_IDENTITY = 7
EXIT_MANIFEST_BYTES = 8
EXIT_MANIFEST_SHA = 9
EXIT_MANIFEST_PARSE = 10
EXIT_MEMBER_COUNT = 11
EXIT_MEMBER_RECORD = 12
EXIT_DEADLINE = 13
EXIT_LEASE = 97

_REQUEST_SCHEMA = "v212-request-projection-v1"
_REQUEST_FIELDS = frozenset({"schema", "tasks", "db_root", "model_dir", "output_dir",
                             "source_pins", "database_pins", "runtime_inventory",
                             "image_digest", "bounds"})
_TASK_FIELDS = frozenset({"name", "question", "evidence", "gold_sql", "db_id", "db_path",
                          "tier", "tier_source", "shape", "coarse_shape", "source"})
_PIN_FIELDS = frozenset({"path", "size", "sha256"})
_MARKER_NAME = "v212.marker"
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_KEY_RE = re.compile(r"[A-Za-z0-9_./-]+")
_APPROVED_ROOTS = ("source", "model", "data")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class _Harness(Exception):
    """Parent-side gate or invariant failure."""


class _Protocol(Exception):
    """Control channel violation."""


class _Lease(Exception):
    """Absolute expiry reached; no reset, no epsilon, no further wait."""


class _Refusal(Exception):
    """Worker refusal at a named gate, with its own exit code."""

    def __init__(self, gate: str, reason: str, code: int, **observed: object) -> None:
        super().__init__(reason)
        self.gate = gate
        self.reason = reason
        self.code = code
        self.observed = observed


class _DuplicateKey(Exception):
    """Raised from inside the original _pairs hook, so it stays typed."""


# --------------------------------------------------------------------------
# Absolute immutable lease
# --------------------------------------------------------------------------

def _lease_exit() -> None:
    os._exit(EXIT_LEASE)


def _arm_lease(expiry_mono: float) -> threading.Timer:
    left = expiry_mono - time.monotonic()
    if left <= 0:
        raise _Lease("lease already expired at boot")
    timer = threading.Timer(left, _lease_exit)
    timer.daemon = True
    timer.start()
    return timer


def _left(expiry_mono: float, deadline: float, reserve: float = 0.0) -> float:
    """Remaining wait. Never clamped upward, never extended past expiry."""
    remaining = min(deadline, expiry_mono - reserve) - time.monotonic()
    if remaining <= 0:
        raise _Lease("deadline or absolute expiry reached")
    return remaining


# --------------------------------------------------------------------------
# Framed nonblocking control, <= 8192, strict session and sequence
# --------------------------------------------------------------------------

def _wait_socket(sock: socket.socket, write: bool, deadline: float, expiry: float) -> None:
    selector = selectors.DefaultSelector()
    try:
        selector.register(sock, selectors.EVENT_WRITE if write else selectors.EVENT_READ)
        while True:
            if selector.select(min(SELECT_SLICE_S, _left(expiry, deadline))):
                return
    finally:
        selector.close()


def _write_frame(sock: socket.socket, payload: dict, deadline: float, expiry: float) -> int:
    body = _dumps(payload)
    frame = len(body).to_bytes(4, "big") + body
    if len(frame) > CONTROL_MAX_FRAME:
        raise _Protocol("frame_over_cap")
    view = memoryview(frame)
    sent = 0
    while sent < len(frame):
        _wait_socket(sock, True, deadline, expiry)
        try:
            sent += sock.send(view[sent:])
        except BlockingIOError:
            continue
        except OSError as error:
            if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise _Protocol(f"send_failed:{error.errno}") from error
    return len(frame)


def _read_exact(sock: socket.socket, count: int, deadline: float, expiry: float) -> bytes:
    out = bytearray()
    while len(out) < count:
        _wait_socket(sock, False, deadline, expiry)
        try:
            block = sock.recv(count - len(out))
        except BlockingIOError:
            continue
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                continue
            raise _Protocol(f"recv_failed:{error.errno}") from error
        if not block:
            raise _Protocol("channel_closed")
        out += block
    return bytes(out)


def _read_frame(sock: socket.socket, deadline: float, expiry: float) -> tuple[dict, int]:
    size = int.from_bytes(_read_exact(sock, 4, deadline, expiry), "big")
    if size + 4 > CONTROL_MAX_FRAME:
        raise _Protocol("frame_over_cap")
    body = _read_exact(sock, size, deadline, expiry)
    if len(body) != size:
        raise _Protocol("frame_length_mismatch")
    # Control frames use the original duplicate-key hook directly: a duplicate in
    # a control frame is a protocol violation, not a manifest gate.
    try:
        return json.loads(body.decode("ascii"), object_pairs_hook=_pairs), size + 4
    except ValueError as error:
        raise _Protocol(f"frame_json:{error}") from error
    except UnicodeDecodeError as error:
        raise _Protocol("frame_not_ascii") from error


def _pairs_hook(pairs: list) -> dict:
    """Original duplicate-key refusal, retyped so callers can name the gate."""
    try:
        return _pairs(pairs)
    except ValueError as error:
        raise _DuplicateKey(str(error)) from error


class _Channel:
    """One direction-agnostic framed endpoint with strict session/sequence."""

    def __init__(self, sock: socket.socket, session: str, expiry: float) -> None:
        self.sock = sock
        self.session = session
        self.expiry = expiry
        self.sent_in = 0
        self.recv_in = 0
        self.frames_sent = 0
        self.frames_recv = 0
        self.max_frame_bytes = 0

    def send(self, kind: str, deadline: float, **fields: object) -> dict:
        self.sent_in += 1
        payload = {"v": 1, "kind": kind, "session": self.session,
                   "seq": self.sent_in, **fields}
        size = _write_frame(self.sock, payload, deadline, self.expiry)
        self.frames_sent += 1
        self.max_frame_bytes = max(self.max_frame_bytes, size)
        return payload

    def recv(self, deadline: float) -> dict:
        payload, size = _read_frame(self.sock, deadline, self.expiry)
        self.frames_recv += 1
        self.max_frame_bytes = max(self.max_frame_bytes, size)
        if payload.get("v") != 1:
            raise _Protocol("bad_version")
        if payload.get("session") != self.session:
            raise _Protocol("session_mismatch")
        if payload.get("seq") != self.recv_in + 1:
            raise _Protocol("seq_violation")
        self.recv_in += 1
        return payload


# --------------------------------------------------------------------------
# Canonical manifest: exact byte arithmetic, solved not hard-coded
# --------------------------------------------------------------------------

def _manifest_len(members: int, key_sum: int, snap_sum: int) -> int:
    return 1 + members * (1 + FIXED_MEMBER_BYTES) + key_sum + snap_sum


def _manifest_max(members: int) -> int:
    return _manifest_len(members, members * NAME_LIMIT, members * NAME_LIMIT)


def _solve_key_lengths(target: int, members: int, snap_lens: list[int]) -> list[int] | None:
    """Key lengths summing to exactly the remainder, or None if infeasible."""
    if members < 1:
        return None
    rest = target - 1 - members * (1 + FIXED_MEMBER_BYTES) - sum(snap_lens)
    if rest < members or rest > members * NAME_LIMIT:
        return None
    each, extra = divmod(rest, members)
    return [each + 1] * extra + [each] * (members - extra)


def _names(prefix: str, lengths: list[int]) -> list[str]:
    out = []
    for index, length in enumerate(lengths):
        head = f"{prefix}{index:05d}"
        if length < len(head) or length > NAME_LIMIT:
            raise _Harness(f"name length {length} unusable for prefix {head}")
        out.append(head + "x" * (length - len(head)))
    if out != sorted(out):
        raise _Harness("generated names are not in canonical sorted order")
    if len(set(out)) != len(out):
        raise _Harness("generated names are not unique")
    return out


def _fit_manifest(case: str, kind: str, members: int, snap_len: int,
                  target: int) -> tuple[bytes, int, int]:
    """Build the canonical manifest for one case at an exact byte length."""
    if kind == "max":
        target = _manifest_max(members)
        snap_lens = [NAME_LIMIT] * members
    elif kind == "over":
        # Solve the smallest member count whose maximum width reaches the target.
        # The bound is derived, not guessed: each member contributes at most
        # 1 separator + FIXED_MEMBER_BYTES + 2*NAME_LIMIT bytes, so the ceiling
        # of (target-1) over that is the first count that can possibly fit.
        # Bounded so an unreachable target refuses instead of hanging the run.
        per_member_max = 1 + FIXED_MEMBER_BYTES + 2 * NAME_LIMIT
        members = max(members, -(-(target - 1) // per_member_max))
        limit = members + 8
        while True:
            snap_lens = [NAME_LIMIT] * members
            if _solve_key_lengths(target, members, snap_lens) is not None:
                break
            members += 1
            if members > limit:
                raise _Harness(f"{case}: target {target} unreachable within {limit} members")
    else:
        snap_lens = [snap_len] * members
    key_lens = _solve_key_lengths(target, members, snap_lens)
    if key_lens is None:
        raise _Harness(f"{case}: target {target} infeasible at {members} members")
    keys = _names("m", key_lens)
    snaps = _names("s", snap_lens)
    records = [{"key": key, "root": MEMBER_ROOT,
                "sha256": hashlib.sha256(f"{MEMBER_ROOT}:{key}".encode()).hexdigest(),
                "size": MEMBER_SIZE, "snapshot_key": snap}
               for key, snap in zip(keys, snaps, strict=True)]
    predicted = _manifest_len(len(records), sum(key_lens), sum(snap_lens))
    payload = _dumps(records)
    if predicted != len(payload):
        raise _Harness(f"{case}: predicted {predicted} != actual {len(payload)}")
    if len(payload) != target:
        raise _Harness(f"{case}: actual {len(payload)} != target {target}")
    return payload, len(records), len(payload)


def _snapshot_key_ok(value: object) -> bool:
    """Spike-local mirror of the original _asset_path key rule."""
    return (type(value) is str and 1 <= len(value) <= NAME_LIMIT
            and _KEY_RE.fullmatch(value) is not None
            and all(part not in ("", ".", "..") for part in value.split("/"))
            and not PurePosixPath(value).is_absolute())


# --------------------------------------------------------------------------
# Request projection: genuine QualificationRequest, disclosed local envelope
# --------------------------------------------------------------------------

def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(handle, payload)
        os.fchmod(handle, 0o600)
        os.fsync(handle)
    finally:
        os.close(handle)


def _pin(path: Path) -> FilePin:
    """Genuine FilePin over a newly created synthetic file, verified by the
    original _check_asset_bytes (regular, nlink==1, exact size, digest, with the
    original signature compared before, at open, during and after the read)."""
    payload = hashlib.sha256(str(path).encode()).digest() * 8
    _write_private(path, payload)
    pin = FilePin(path=_path(path), size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    _check_asset_bytes(pin.path, size=pin.size, sha256=pin.sha256)
    return pin


def _build_request(private: Path) -> tuple[QualificationRequest, bytes]:
    """Construct a genuine QualificationRequest over new synthetic files.

    output_dir is deliberately left uncreated: the original host branch of
    _validate_request requires the export directory not to exist yet.
    """
    private.mkdir(parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    db_root = _path(private / "db")
    model_dir = _path(private / "model")
    output_dir = _path(private / "output")
    source_root = private / "source"
    # Every pinned file needs its own directory to exist first: _pin opens with
    # O_CREAT|O_EXCL, which creates the file but never a parent directory.
    for directory in (db_root, model_dir, source_root,
                      *(db_root / name for name, _amount in _FIXTURES)):
        directory.mkdir(parents=True, exist_ok=True)
    tasks = []
    database_pins = []
    for name, _amount in _FIXTURES:
        database = db_root / name / f"{name}.bin"
        tasks.append(SqlTask(
            name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
            evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
            db_id=name, db_path=str(database), tier=TIERS[0], tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture"))
        database_pins.append(_pin(database))
    source_pins = tuple(_pin(source_root / f"module-{index}.py") for index in range(3))
    runtime_inventory = _pin(source_root / "runtime-inventory.json")
    bounds = AttemptBounds(total_ceiling_usd=Decimal("1.25"), prior_usage_usd=Decimal("0.10"),
                           remaining_worst_case_usd=Decimal("1.15"), lifetime_seconds=900,
                           output_bytes_per_phase=1048576, artifact_bytes=4194304,
                           retention_seconds=3600)
    _validate_bounds(bounds)
    request = QualificationRequest(
        tasks=tuple(tasks), db_root=db_root, model_dir=model_dir, output_dir=output_dir,
        source_pins=source_pins, database_pins=tuple(database_pins),
        runtime_inventory=runtime_inventory,
        image_digest="sha256:" + hashlib.sha256(b"v212-synthetic-image").hexdigest(),
        bounds=bounds)
    document = {
        "schema": _REQUEST_SCHEMA,
        "tasks": [asdict(task) for task in request.tasks],
        "db_root": str(request.db_root), "model_dir": str(request.model_dir),
        "output_dir": str(request.output_dir),
        "source_pins": [asdict(pin) | {"path": str(pin.path)} for pin in request.source_pins],
        "database_pins": [asdict(pin) | {"path": str(pin.path)} for pin in request.database_pins],
        "runtime_inventory": asdict(request.runtime_inventory)
        | {"path": str(request.runtime_inventory.path)},
        "image_digest": request.image_digest,
        "bounds": {name: (format(value, "f") if isinstance(value, Decimal) else value)
                   for name, value in asdict(request.bounds).items()},
    }
    return request, _dumps(document)


def _rebuild_request(payload: bytes, gate: str, code: int) -> QualificationRequest:
    """Worker side: rebuild a genuine QualificationRequest from FD bytes."""
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs_hook)
    except _DuplicateKey as error:
        raise _Refusal(gate, "request_duplicate_key", code, detail=str(error)) from error
    except (ValueError, UnicodeDecodeError) as error:
        raise _Refusal(gate, "request_parse", code, detail=str(error)) from error
    try:
        _closed(document, set(_REQUEST_FIELDS), "request projection")
    except ValueError as error:
        raise _Refusal(gate, "request_fields", code, detail=str(error)) from error
    if document["schema"] != _REQUEST_SCHEMA:
        raise _Refusal(gate, "request_schema", code, schema=str(document["schema"])[:64])
    tasks = document["tasks"]
    if type(tasks) is not list or len(tasks) != 4:
        raise _Refusal(gate, "request_task_count", code, count=len(tasks) if type(tasks) is list else -1)
    rebuilt = []
    for row in tasks:
        try:
            _closed(row, set(_TASK_FIELDS), "task")
        except ValueError as error:
            raise _Refusal(gate, "request_fields", code, detail=str(error)) from error
        if any(type(value) is not str for value in row.values()):
            raise _Refusal(gate, "request_type", code, field="task")
        if row["tier"] not in TIERS:      # the ORIGINAL tier vocabulary
            raise _Refusal(gate, "request_tier", code, tier=row["tier"][:32])
        try:
            rebuilt.append(SqlTask(**row))
        except ValueError as error:
            raise _Refusal(gate, "request_reconstruct", code, detail=str(error)) from error
    pins = {}
    for label in ("source_pins", "database_pins", "runtime_inventory"):
        raw = document[label]
        items = raw if type(raw) is list else [raw]
        for item in items:
            try:
                _closed(item, set(_PIN_FIELDS), "pin")
            except ValueError as error:
                raise _Refusal(gate, "request_fields", code, detail=str(error)) from error
            if type(item["size"]) is not int or type(item["sha256"]) is not str:
                raise _Refusal(gate, "request_type", code, field="pin")
            pins[label] = pins.get(label, ()) + (FilePin(path=Path(item["path"]),
                                                         size=item["size"],
                                                         sha256=item["sha256"]),)
    if len(pins.get("source_pins", ())) != 3 or len(pins.get("database_pins", ())) != 4 \
            or len(pins.get("runtime_inventory", ())) != 1:
        raise _Refusal(gate, "request_pin_count", code,
                       source=len(pins.get("source_pins", ())),
                       database=len(pins.get("database_pins", ())),
                       inventory=len(pins.get("runtime_inventory", ())))
    try:
        bounds = _bounds_from_wire(document["bounds"])
    except ValueError as error:
        raise _Refusal(gate, "request_bounds", code, detail=str(error)) from error
    digest = document["image_digest"]
    if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
        raise _Refusal(gate, "request_digest_shape", code)
    request = QualificationRequest(
        tasks=tuple(rebuilt), db_root=Path(document["db_root"]),
        model_dir=Path(document["model_dir"]), output_dir=Path(document["output_dir"]),
        source_pins=pins["source_pins"], database_pins=pins["database_pins"],
        runtime_inventory=pins["runtime_inventory"][0], image_digest=digest, bounds=bounds)
    if type(request) is not QualificationRequest:
        raise _Refusal(gate, "request_reconstruct", code)
    return request


# --------------------------------------------------------------------------
# Descriptor identity and bounded exact IO
# --------------------------------------------------------------------------

def _access_bits(fd: int) -> int:
    return fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE


def _check_mode(fd: int, gate: str, code: int, label: str) -> tuple:
    if _access_bits(fd) != os.O_RDONLY:
        raise _Refusal(gate, f"{label}_mode_not_readonly", code,
                       access=_access_bits(fd), want=os.O_RDONLY)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise _Refusal(gate, f"{label}_not_regular", code, mode=stat.S_IFMT(info.st_mode))
    if info.st_nlink != 1:
        raise _Refusal(gate, f"{label}_hardlinked", code, nlink=info.st_nlink)
    return _signature(info)


def _read_hash(fd: int, size: int, grew: str, short: str, gate: str,
               code: int) -> tuple[bytes, str]:
    """Bounded exact read mirroring the original _check_asset_bytes loop."""
    digest = hashlib.sha256()
    buffer = bytearray()
    while block := os.read(fd, min(1048576, size - len(buffer) + 1)):
        digest.update(block)
        buffer += block
        if len(buffer) > size:
            raise _Refusal(gate, grew, code, read=len(buffer), want=size)
    if len(buffer) != size:
        raise _Refusal(gate, short, code, read=len(buffer), want=size)
    return bytes(buffer), digest.hexdigest()


# --------------------------------------------------------------------------
# Worker mode
# --------------------------------------------------------------------------

def _bounded_stderr(text: str) -> None:
    try:
        sys.stderr.write(text[:STDERR_CAP] + "\n")
        sys.stderr.flush()
    except OSError:
        pass


def _validate_manifest(members: list, gate_parse: str, gate_count: str, gate_record: str) -> None:
    if type(members) is not list:
        raise _Refusal(gate_parse, "manifest_not_array", EXIT_MANIFEST_PARSE)
    if len(members) > MANIFEST_COUNT_CAP:
        raise _Refusal(gate_count, "member_count_over_cap", EXIT_MEMBER_COUNT,
                       count=len(members), cap=MANIFEST_COUNT_CAP)
    previous = None
    seen_snaps = set()
    for index, member in enumerate(members):
        try:
            _closed(member, set(MEMBER_FIELDS), "member")
        except ValueError as error:
            raise _Refusal(gate_record, "member_fields", EXIT_MEMBER_RECORD,
                           index=index, detail=str(error)) from error
        root, key = member["root"], member["key"]
        size, sha, snap = member["size"], member["sha256"], member["snapshot_key"]
        if type(size) is not int or type(root) is not str or type(key) is not str \
                or type(sha) is not str or type(snap) is not str:
            raise _Refusal(gate_record, "member_type", EXIT_MEMBER_RECORD, index=index)
        if root not in _APPROVED_ROOTS:
            raise _Refusal(gate_record, "member_root_unknown", EXIT_MEMBER_RECORD,
                           index=index, root=root[:32])
        try:
            _asset_path(root, key)          # the ORIGINAL root/key validator
        except ValueError as error:
            raise _Refusal(gate_record, "member_key_rejected", EXIT_MEMBER_RECORD,
                           index=index, detail=str(error)) from error
        if not 0 <= size <= 2 * 1024**3:
            raise _Refusal(gate_record, "member_size_range", EXIT_MEMBER_RECORD, index=index)
        if _SHA_RE.fullmatch(sha) is None:
            raise _Refusal(gate_record, "member_sha_shape", EXIT_MEMBER_RECORD, index=index)
        if not _snapshot_key_ok(snap):
            raise _Refusal(gate_record, "member_snapshot_key", EXIT_MEMBER_RECORD, index=index)
        identity = (root, key)
        if previous is not None and identity <= previous:
            raise _Refusal(gate_record, "member_order", EXIT_MEMBER_RECORD, index=index)
        if snap in seen_snaps:
            raise _Refusal(gate_record, "member_duplicate", EXIT_MEMBER_RECORD, index=index)
        seen_snaps.add(snap)
        previous = identity


def _refuse_constant(value: str):
    """json parse_constant hook: refuse NaN/Infinity rather than accept them."""
    raise _Refusal("manifest_parse", "manifest_nonfinite", EXIT_MANIFEST_PARSE, value=value)


def _refusal_deadline(expiry: float) -> float:
    """Send a refusal with a short bounded deadline, never past expiry."""
    return min(time.monotonic() + 0.25, expiry - TEARDOWN_RESERVE_S)


def _open_journal(run_root: Path) -> Path:
    """Parent precreates the run journal, private, 0600, exclusively."""
    journal = run_root / "journal.log"
    fd = os.open(str(journal), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, _dumps({"v": 1, "kind": "journal_precreated", "pid": os.getpid()}) + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    return journal


def _journal_append(journal: Path, record: dict) -> None:
    """Append one bounded line with NO O_CREAT.

    The parent precreated this file, so a child that opens it without O_CREAT is
    proving it never first-creates a shared path, and the mode check is proving the
    parent's precreate really was private. A missing or wrong-mode journal is a
    custody failure, never something to silently recreate.
    """
    fd = os.open(str(journal), os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise OSError(errno.EACCES, "journal is not a private regular 0600 file")
        os.write(fd, _dumps(record)[:STDERR_CAP] + b"\n")
    finally:
        os.close(fd)


def _journal_snapshot(journal: Path) -> tuple[dict, int]:
    """Read the journal back: real line counts by kind, and the real file mode."""
    kinds: dict = {}
    try:
        raw = journal.read_bytes()
        mode = stat.S_IMODE(journal.stat().st_mode)
    except OSError:
        return kinds, -1
    for line in raw[:1048576].split(b"\n"):
        if not line:
            continue
        try:
            kind = str(json.loads(line.decode("ascii")).get("kind"))
        except (ValueError, UnicodeDecodeError):
            kind = "unparsable"
        kinds[kind] = kinds.get(kind, 0) + 1
    return kinds, mode


def _worker_main(argv: list[str]) -> int:
    """Run the ladder, then append exactly one journal line for the outcome.

    The journal append is outside the ladder so that every exit path, including a
    refusal, is recorded. A missing journal line on an otherwise accepted run is a
    custody failure and escalates the exit code.
    """
    journal = Path(argv[8]) if len(argv) == 10 else None
    code, gate, reason = _worker_body(argv)
    if journal is not None:
        try:
            _journal_append(journal, {"v": 1, "kind": "worker_exit", "pid": os.getpid(),
                                      "case": argv[9], "code": code, "gate": gate,
                                      "reason": reason})
        except OSError as error:
            _bounded_stderr(f"v212 worker journal append failed errno={error.errno}")
            if code == EXIT_OK:
                code = EXIT_PROTOCOL
    return code


def _worker_body(argv: list[str]) -> tuple[int, str, str]:
    """The gate ladder. Returns (exit code, refusal gate, refusal reason)."""
    if len(argv) != 10:
        _bounded_stderr(f"v212 worker argv count {len(argv)}")
        return EXIT_CHANNEL, "channel", "argv_count"
    root, session, nonce, req_txt, man_txt, sock_txt, mono_txt, _wall, _journal, case = argv
    try:
        request_fd, manifest_fd, sock_fd = int(req_txt), int(man_txt), int(sock_txt)
        expiry = float(mono_txt)
    except ValueError:
        _bounded_stderr("v212 worker argv not numeric")
        return EXIT_CHANNEL, "channel", "argv_not_numeric"
    channel = None
    try:
        _arm_lease(expiry)
        deadline = expiry - TEARDOWN_RESERVE_S
        if _left(expiry, deadline) <= MIN_WAIT_S:
            raise _Refusal("lease", "lease_expired", EXIT_LEASE)
        for fd in (request_fd, manifest_fd, sock_fd):
            try:
                fcntl.fcntl(fd, fcntl.F_GETFL)
            except OSError as error:
                raise _Refusal("channel", "channel_unavailable", EXIT_CHANNEL,
                               fd=fd, errno=error.errno) from error
        # Explicit family/type: socketpair() is AF_UNIX/SOCK_STREAM, and stating
        # them removes any reliance on fileno auto-detection.
        control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=sock_fd)
        control.setblocking(False)
        channel = _Channel(control, session, expiry)
        hello = channel.recv(deadline)
        if hello.get("kind") != "hello":
            raise _Protocol("expected hello")
        if hello.get("nonce") != nonce:
            raise _Protocol("nonce_mismatch")

        # ---- request descriptor: mode, identity, bytes, digest, parse, shape
        signature = _check_mode(request_fd, "request_mode", EXIT_REQUEST, "request")
        if list(hello["request_identity"]) != list(signature):
            raise _Refusal("request_identity", "request_identity_pre_read", EXIT_REQUEST,
                           observed=list(signature), expected=list(hello["request_identity"]))
        request_size = hello["request_bytes"]
        info = os.fstat(request_fd)
        if info.st_size != request_size:
            raise _Refusal("request_bytes", "request_bytes_mismatch", EXIT_REQUEST,
                           observed=info.st_size, expected=request_size)
        if request_size > REQUEST_BYTE_CAP:
            raise _Refusal("request_bytes", "request_bytes_over_cap", EXIT_REQUEST,
                           observed=request_size, cap=REQUEST_BYTE_CAP)
        payload, digest = _read_hash(request_fd, request_size, "request_read_grew",
                                     "request_read_short", "request_bytes", EXIT_REQUEST)
        if digest != hello["request_sha"]:
            raise _Refusal("request_sha", "request_sha_mismatch", EXIT_REQUEST, observed=digest)
        if list(_signature(os.fstat(request_fd))) != list(signature):
            raise _Refusal("request_identity", "request_identity_post_read", EXIT_REQUEST)
        request = _rebuild_request(payload, "request_shape", EXIT_REQUEST)

        # ---- manifest descriptor: mode, identity, bytes, digest, parse, records
        signature = _check_mode(manifest_fd, "manifest_mode", EXIT_MANIFEST_MODE, "manifest")
        if list(hello["manifest_identity"]) != list(signature):
            raise _Refusal("manifest_identity", "manifest_identity_pre_read",
                           EXIT_MANIFEST_IDENTITY, observed=list(signature),
                           expected=list(hello["manifest_identity"]))
        manifest_size = hello["manifest_bytes"]
        info = os.fstat(manifest_fd)
        if info.st_size != manifest_size:
            raise _Refusal("manifest_bytes", "manifest_bytes_mismatch", EXIT_MANIFEST_BYTES,
                           observed=info.st_size, expected=manifest_size)
        if info.st_size > MANIFEST_BYTE_CAP:
            raise _Refusal("manifest_bytes", "manifest_bytes_over_cap", EXIT_MANIFEST_BYTES,
                           observed=info.st_size, cap=MANIFEST_BYTE_CAP)
        payload, digest = _read_hash(manifest_fd, manifest_size, "manifest_read_grew",
                                     "manifest_read_short", "manifest_sha", EXIT_MANIFEST_SHA)
        if digest != hello["manifest_sha"]:
            raise _Refusal("manifest_sha", "manifest_sha_mismatch", EXIT_MANIFEST_SHA,
                           observed=digest)
        if list(_signature(os.fstat(manifest_fd))) != list(signature):
            raise _Refusal("manifest_identity", "manifest_identity_post_read",
                           EXIT_MANIFEST_IDENTITY)
        try:
            members = json.loads(payload.decode("ascii"), object_pairs_hook=_pairs_hook,
                                 parse_constant=_refuse_constant)
        except _DuplicateKey as error:
            raise _Refusal("manifest_parse", "manifest_duplicate_key", EXIT_MANIFEST_PARSE,
                           detail=str(error)) from error
        except (ValueError, UnicodeDecodeError) as error:
            raise _Refusal("manifest_parse", "manifest_parse", EXIT_MANIFEST_PARSE,
                           detail=str(error)) from error
        _validate_manifest(members, "manifest_parse", "member_count", "member_record")

        channel.send("ready", deadline, pid=os.getpid(), case=case,
                     request_bytes=request_size,
                     request_tasks=len(request.tasks), manifest_bytes=info.st_size,
                     manifest_members=len(members), manifest_sha=digest,
                     manifest_access=_access_bits(manifest_fd))
        challenge = channel.recv(deadline)
        if challenge.get("kind") != "challenge":
            raise _Protocol("expected challenge")
        channel.send("alive", deadline, pid=os.getpid())
        permit = channel.recv(deadline)
        if permit.get("kind") != "permit":
            raise _Refusal("permit", "permit_absent", EXIT_DEADLINE,
                           kind=str(permit.get("kind"))[:32])
        if permit.get("nonce") != nonce:
            raise _Refusal("permit", "permit_nonce_mismatch", EXIT_DEADLINE)
        operation = time.monotonic() + OP_S
        marker = Path(root) / _MARKER_NAME
        try:
            handle = os.open(str(marker),
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise _Refusal("marker", "marker_exists", EXIT_DEADLINE) from None
        except OSError as error:
            raise _Refusal("marker", "marker_open_failed", EXIT_DEADLINE,
                           errno=error.errno) from error
        try:
            body = _dumps({"case": case, "nonce": nonce, "pid": os.getpid()})
            os.write(handle, body)
            os.fchmod(handle, 0o600)
            os.fsync(handle)
        finally:
            os.close(handle)
        if time.monotonic() > operation:
            raise _Refusal("marker", "marker_timeout", EXIT_DEADLINE)
        channel.send("done", deadline, pid=os.getpid(), marker=_MARKER_NAME,
                     marker_bytes=len(body))
        for fd in (request_fd, manifest_fd):
            os.close(fd)
        control.close()
        return EXIT_OK, "", ""
    except _Refusal as refusal:
        if channel is not None:
            try:
                channel.send("reject", _refusal_deadline(expiry), gate=refusal.gate,
                             reason=refusal.reason, observed=refusal.observed)
            except BaseException:  # noqa: BLE001 - refusal code outranks send failure
                pass
        return refusal.code, refusal.gate, refusal.reason
    except _Lease:
        return EXIT_LEASE, "lease", "lease_expired"
    except _Protocol as error:
        if channel is not None:
            try:
                channel.send("reject", _refusal_deadline(expiry), gate="protocol",
                             reason=str(error)[:64], observed={})
            except BaseException:  # noqa: BLE001
                pass
        return EXIT_PROTOCOL, "protocol", str(error)[:64]
    except BaseException as error:  # noqa: BLE001 - bounded, never a traceback flood
        _bounded_stderr(f"v212 worker internal {type(error).__name__}: {error}")
        return EXIT_INTERNAL, "internal", type(error).__name__


# --------------------------------------------------------------------------
# Parent mode
# --------------------------------------------------------------------------

class _Resources:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.proc: subprocess.Popen | None = None
        self.owners: list[int] = []
        self.passed: list[int] = []
        self.sockets: list[socket.socket] = []
        self.retained = False
        self.errors: list[str] = []
        self.popen_calls = 0
        self.pass_transfers = 0
        self.passed_closed = 0
        self.owners_closed = 0
        self.containment = 0
        self.lease_exits = 0

    def release(self, keep_on_failure: bool, failed: bool) -> None:
        if failed and keep_on_failure:
            self.retained = True
        for fd in self.passed:
            try:
                os.close(fd)
            except OSError as error:
                self.errors.append(f"passed_close:{error.errno}")
            else:
                self.passed_closed += 1
        self.passed.clear()
        for sock in self.sockets:
            try:
                sock.close()
            except OSError as error:
                self.errors.append(f"socket_close:{error.errno}")
        self.sockets.clear()
        for fd in self.owners:
            try:
                os.close(fd)
            except OSError as error:
                self.errors.append(f"owner_close:{error.errno}")
            else:
                self.owners_closed += 1
        self.owners.clear()
        if self.proc is not None:
            for stream in (self.proc.stdout, self.proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError as error:
                        self.errors.append(f"stream_close:{error.errno}")
        if self.root is not None and not self.retained:
            try:
                shutil.rmtree(self.root)
            except OSError as error:
                self.errors.append(f"rmtree:{error.errno}")
                self.retained = True


def _spawn(res: _Resources, argv: list[str], pass_fds: tuple[int, ...]) -> subprocess.Popen:
    proc = subprocess.Popen(argv, pass_fds=pass_fds, start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, close_fds=True)
    res.popen_calls += 1
    return proc


def _reap(res: _Resources, deadline: float) -> int:
    proc = res.proc
    assert proc is not None
    left = deadline - time.monotonic()
    if left <= 0:
        res.containment += 1
        return _stop(res)
    try:
        return proc.wait(timeout=max(MIN_WAIT_S, left))
    except subprocess.TimeoutExpired:
        res.containment += 1
        return _stop(res)


def _stop(res: _Resources) -> int:
    proc = res.proc
    assert proc is not None
    if proc.poll() is None:
        proc.terminate()
        probe = time.monotonic() + TERM_PROBE_S
        while proc.poll() is None and time.monotonic() < probe:
            time.sleep(0.005)
        if proc.poll() is None:
            proc.kill()
    limit = time.monotonic() + STOP_S
    while proc.poll() is None and time.monotonic() < limit:
        time.sleep(0.005)
    # Unbounded on purpose. A bounded wait here would trade a slow reap for a
    # surviving zombie, and "no descendants" outranks the containment budget.
    # After SIGKILL the kernel reaps promptly, so this is not a real hang risk.
    return proc.wait()


def _transfer(res: _Resources, owner: int) -> int:
    """Dup an owner into a passed copy, made inheritable for this spawn only.

    The counter moves on the real dup, so it is an observation, not a literal.
    """
    passed = os.dup(owner)
    os.set_inheritable(passed, True)
    res.passed.append(passed)
    res.pass_transfers += 1
    return passed


def _close_passed(res: _Resources) -> None:
    """Close every passed copy after the fork, retaining the owners."""
    for fd in res.passed:
        os.close(fd)
        res.passed_closed += 1
    res.passed.clear()


# --------------------------------------------------------------------------
# Case specifications: seven fixed cases, no parameterisation framework
# --------------------------------------------------------------------------

CASES = (
    # C1: valid manifest at exactly CONTROL_MAX_FRAME + 1.
    {"case": "exact_control_overflow", "kind": "exact", "members": 40, "snap_len": 25,
     "target": CONTROL_MAX_FRAME + 1, "manifest_flags": os.O_RDONLY, "decoy": False,
     "wrong_sha": False, "rc": EXIT_OK, "gate": "", "reason": "", "markers": 1, "permits": 1},
    # C2: true worst valid input; the declared 8388608 is infeasible at 10000 members.
    {"case": "worst_valid_bulk", "kind": "max", "members": MANIFEST_COUNT_CAP, "snap_len": 0,
     "target": 0, "manifest_flags": os.O_RDONLY, "decoy": False, "wrong_sha": False,
     "rc": EXIT_OK, "gate": "", "reason": "", "markers": 1, "permits": 1},
    # C3: one byte over the byte cap; also over the count cap, byte gate runs first.
    # "members" is only a starting hint: the fitter raises it to the smallest count
    # whose maximum width can reach the target, then solves the widths.
    {"case": "byte_cap_refusal", "kind": "over", "members": MANIFEST_COUNT_CAP, "snap_len": 0,
     "target": MANIFEST_BYTE_CAP + 1, "manifest_flags": os.O_RDONLY, "decoy": False,
     "wrong_sha": False, "rc": EXIT_MANIFEST_BYTES, "gate": "manifest_bytes",
     "reason": "manifest_bytes_over_cap", "markers": 0, "permits": 0},
    # C4: one member over the count cap, far below the byte cap.
    {"case": "count_cap_refusal", "kind": "exact", "members": MANIFEST_COUNT_CAP + 1,
     "snap_len": 14, "target": 960097, "manifest_flags": os.O_RDONLY, "decoy": False,
     "wrong_sha": False, "rc": EXIT_MEMBER_COUNT, "gate": "member_count",
     "reason": "member_count_over_cap", "markers": 0, "permits": 0},
    # C5: same descriptor, same real digest, deliberately wrong expected digest.
    {"case": "wrong_expected_sha", "kind": "exact", "members": 24, "snap_len": 18,
     "target": 2497, "manifest_flags": os.O_RDONLY, "decoy": False, "wrong_sha": True,
     "rc": EXIT_MANIFEST_SHA, "gate": "manifest_sha", "reason": "manifest_sha_mismatch",
     "markers": 0, "permits": 0},
    # C6: byte-identical, same-size, different inode; decoy descriptor is passed.
    {"case": "different_inode", "kind": "exact", "members": 24, "snap_len": 18,
     "target": 2497, "manifest_flags": os.O_RDONLY, "decoy": True, "wrong_sha": False,
     "rc": EXIT_MANIFEST_IDENTITY, "gate": "manifest_identity",
     "reason": "manifest_identity_pre_read", "markers": 0, "permits": 0},
    # C7: writable descriptor on the same inode; only the access bits differ.
    {"case": "writable_mode", "kind": "exact", "members": 24, "snap_len": 18,
     "target": 2497, "manifest_flags": os.O_RDWR, "decoy": False, "wrong_sha": False,
     "rc": EXIT_MANIFEST_MODE, "gate": "manifest_mode",
     "reason": "manifest_mode_not_readonly", "markers": 0, "permits": 0},
)


def _run_case(spec: dict, expiry: float, journal: Path) -> dict:
    case = spec["case"]
    res = _Resources()
    record: dict = {"case": case, "failures": []}
    started = time.monotonic()
    deadline = min(started + CASE_BUDGET_S, expiry - TEARDOWN_RESERVE_S)
    failed = False
    try:
        res.root = _path(Path(tempfile.mkdtemp(prefix=f"v212-{case}-")).resolve())
        os.chmod(res.root, 0o700)
        private = res.root / "private"
        generated = time.monotonic()
        request, request_payload = _build_request(private)
        manifest_payload, member_count, manifest_bytes = _fit_manifest(
            case, spec["kind"], spec["members"], spec["snap_len"], spec["target"])
        record["fixture_gen_ms"] = round((time.monotonic() - generated) * 1000, 3)
        record["request_bytes"] = len(request_payload)
        record["manifest_bytes"] = manifest_bytes
        record["manifest_members"] = member_count
        record["request_tasks"] = len(request.tasks)
        if manifest_bytes != spec["target"] and spec["kind"] != "max":
            raise _Harness(f"{case}: generated {manifest_bytes} != target {spec['target']}")
        if spec["kind"] == "max" and manifest_bytes != WORST_VALID_MANIFEST_BYTES:
            raise _Harness(f"{case}: worst valid {manifest_bytes} != "
                           f"{WORST_VALID_MANIFEST_BYTES}")

        request_file = private / "request.json"
        manifest_file = private / "manifest.json"
        _write_private(request_file, request_payload)
        _write_private(manifest_file, manifest_payload)
        request_owner = os.open(str(request_file), os.O_RDONLY | os.O_NOFOLLOW)
        res.owners.append(request_owner)
        manifest_owner = os.open(str(manifest_file),
                                 spec["manifest_flags"] | os.O_NOFOLLOW)
        res.owners.append(manifest_owner)
        passed_manifest_owner = manifest_owner
        if spec["decoy"]:
            decoy_file = private / "manifest-decoy.json"
            _write_private(decoy_file, manifest_payload)
            decoy_owner = os.open(str(decoy_file), os.O_RDONLY | os.O_NOFOLLOW)
            res.owners.append(decoy_owner)
            passed_manifest_owner = decoy_owner
        record["owner_fds_retained"] = len(res.owners)

        session = hashlib.sha256(f"{case}:session".encode()).hexdigest()[:32]
        nonce = hashlib.sha256(f"{case}:nonce".encode()).hexdigest()[:32]
        parent_sock, child_sock = socket.socketpair()
        res.sockets.extend((parent_sock, child_sock))
        parent_sock.setblocking(False)
        child_sock.set_inheritable(True)
        res.pass_transfers += 1                     # the socket end is a real transfer
        request_passed = _transfer(res, request_owner)
        manifest_passed = _transfer(res, passed_manifest_owner)

        worker_argv = [sys.executable, str(_SELF), "--_v212-worker", str(res.root), session,
                       nonce, str(request_passed), str(manifest_passed),
                       str(child_sock.fileno()), repr(expiry), repr(time.time()),
                       str(journal), case]
        res.proc = _spawn(res, worker_argv,
                          (request_passed, manifest_passed, child_sock.fileno()))
        # Close the passed copies and the child socket end, retaining the owners.
        _close_passed(res)
        child_sock.close()
        res.passed_closed += 1
        res.sockets.remove(child_sock)

        expected_identity = list(_signature(os.fstat(request_owner)))
        # Always the ORIGINAL manifest's signature. In the decoy case the passed
        # descriptor is the copy, so this mismatch is what the identity gate must
        # catch; sending the decoy's signature would make C6 vacuously pass.
        expected_manifest_identity = list(_signature(os.fstat(manifest_owner)))
        record["manifest_sha"] = hashlib.sha256(manifest_payload).hexdigest()
        expected_sha = record["manifest_sha"]
        if spec["wrong_sha"]:
            expected_sha = hashlib.sha256(manifest_payload + b"v212-wrong").hexdigest()

        channel = _Channel(parent_sock, session, expiry)
        channel.send("hello", deadline, nonce=nonce,
                     request_bytes=len(request_payload),
                     request_sha=hashlib.sha256(request_payload).hexdigest(),
                     request_identity=expected_identity,
                     manifest_bytes=manifest_bytes, manifest_sha=expected_sha,
                     manifest_members=member_count,
                     manifest_identity=expected_manifest_identity)
        worker_started = time.monotonic()
        reply = channel.recv(deadline)
        permits = 0
        record["challenge_ms"] = 0.0
        record["marker_ms"] = 0.0
        if reply.get("kind") == "reject":
            record["reject_gate"] = str(reply.get("gate", ""))
            record["reject_reason"] = str(reply.get("reason", ""))
        elif reply.get("kind") == "ready":
            record["reject_gate"] = ""
            record["reject_reason"] = ""
            record["worker_manifest_bytes"] = reply.get("manifest_bytes")
            record["worker_manifest_members"] = reply.get("manifest_members")
            record["worker_manifest_sha"] = reply.get("manifest_sha")
            record["worker_manifest_access"] = reply.get("manifest_access")
            record["worker_request_tasks"] = reply.get("request_tasks")
            record["worker_request_bytes"] = reply.get("request_bytes")
            challenged = time.monotonic()
            channel.send("challenge", deadline)
            alive = channel.recv(min(deadline, challenged + CHALLENGE_S))
            record["challenge_ms"] = round((time.monotonic() - challenged) * 1000, 3)
            if alive.get("kind") != "alive":
                raise _Protocol(f"expected alive, got {alive.get('kind')}")
            permitted = time.monotonic()
            channel.send("permit", deadline, nonce=nonce)
            permits += 1
            done = channel.recv(min(deadline, permitted + OP_S))
            record["marker_ms"] = round((time.monotonic() - permitted) * 1000, 3)
            if done.get("kind") != "done":
                raise _Protocol(f"expected done, got {done.get('kind')}")
        else:
            raise _Protocol(f"unexpected reply {reply.get('kind')}")
        record["permit_issued"] = permits
        record["returncode"] = _reap(res, deadline)
        record["worker_ms"] = round((time.monotonic() - worker_started) * 1000, 3)
        if record["returncode"] == EXIT_LEASE:
            res.lease_exits += 1
        stderr = b""
        if res.proc.stderr is not None:
            stderr = res.proc.stderr.read(4096) or b""
        record["worker_stderr"] = stderr.decode("utf-8", "replace")[:512]

        # Snapshot markers only after the real reap.
        names = sorted(os.listdir(res.root))
        record["markers"] = names.count(_MARKER_NAME)
        record["root_entries"] = names
        if record["markers"] == 1:
            record["marker_mode"] = stat.S_IMODE(os.stat(res.root / _MARKER_NAME).st_mode)
        record["control_frames_sent"] = channel.frames_sent
        record["control_frames_recv"] = channel.frames_recv
        record["control_max_frame_bytes"] = channel.max_frame_bytes
        record["elapsed_s"] = round(time.monotonic() - started, 4)
        failed = not _gate_case(record, spec)
    except _Harness as error:
        record["failures"].append(f"harness:{error}")
        failed = True
    except _Protocol as error:
        record["failures"].append(f"protocol:{error}")
        failed = True
    except _Lease as error:
        record["failures"].append(f"lease:{error}")
        res.lease_exits += 1
        failed = True
    except BaseException as error:  # noqa: BLE001 - reported, never swallowed
        record["failures"].append(f"internal:{type(error).__name__}:{error}")
        failed = True
    finally:
        if res.proc is not None and res.proc.poll() is None:
            res.containment += 1
            _stop(res)
        record["popen_calls"] = res.popen_calls
        record["pass_fd_transfers"] = res.pass_transfers
        record["passed_copies_closed"] = res.passed_closed
        record["owner_fds_closed"] = res.owners_closed
        record["containment_used"] = res.containment
        record["lease_exits"] = res.lease_exits
        record["cleanup_errors"] = res.errors
        record.setdefault("elapsed_s", round(time.monotonic() - started, 4))
        res.release(keep_on_failure=True, failed=failed)
        record["retained_roots"] = 1 if res.retained else 0
        record["proc_retained"] = res.proc is not None and failed
        if not failed:
            _require_clean(record)
    return record


def _gate_case(record: dict, spec: dict) -> bool:
    """Compare every expected value against an observed one. No constant stands
    in for an observation."""
    ok = True

    def check(label: str, observed: object, expected: object) -> None:
        nonlocal ok
        if observed != expected:
            record["failures"].append(f"{label}: observed {observed!r} != expected {expected!r}")
            ok = False

    check("returncode", record.get("returncode"), spec["rc"])
    check("reject_gate", record.get("reject_gate"), spec["gate"])
    check("reject_reason", record.get("reject_reason"), spec["reason"])
    check("markers", record.get("markers"), spec["markers"])
    check("permit_issued", record.get("permit_issued"), spec["permits"])
    check("popen_calls", record.get("popen_calls"), 1)
    check("pass_fd_transfers", record.get("pass_fd_transfers"), 3)
    check("passed_copies_closed", record.get("passed_copies_closed"), 3)
    check("owner_fds_closed", record.get("owner_fds_closed"), record.get("owner_fds_retained"))
    check("manifest_bytes", record.get("manifest_bytes"),
          WORST_VALID_MANIFEST_BYTES if spec["kind"] == "max" else spec["target"])
    if spec["kind"] == "max":
        check("manifest_members", record.get("manifest_members"), MANIFEST_COUNT_CAP)
    elif spec["kind"] == "over":
        # The member count is solved, not fixed, so the gate is the inequality
        # that makes this case an over-cap input at all. Never a self-comparison.
        if not (record.get("manifest_members") or 0) > MANIFEST_COUNT_CAP:
            record["failures"].append(
                f"manifest_members: {record.get('manifest_members')} does not exceed "
                f"{MANIFEST_COUNT_CAP}")
            ok = False
    else:
        check("manifest_members", record.get("manifest_members"), spec["members"])
    check("request_tasks", record.get("request_tasks"), 4)
    check("request_bytes_observed", record.get("request_bytes") is not None, True)
    if record.get("control_max_frame_bytes") is None \
            or record["control_max_frame_bytes"] > CONTROL_MAX_FRAME:
        record["failures"].append(
            f"control_max_frame_bytes: {record.get('control_max_frame_bytes')} "
            f"must be observed and <= {CONTROL_MAX_FRAME}")
        ok = False
    if record.get("fixture_gen_ms") is None:
        record["failures"].append("fixture_gen_ms: not observed")
        ok = False
    if spec["rc"] == EXIT_OK:
        check("worker_manifest_bytes", record.get("worker_manifest_bytes"),
              record.get("manifest_bytes"))
        check("worker_manifest_members", record.get("worker_manifest_members"),
              record.get("manifest_members"))
        # The worker's own digest must equal the parent's independently generated
        # digest. Comparing an observation to itself would be a vacuous gate.
        check("worker_manifest_sha", record.get("worker_manifest_sha"),
              record.get("manifest_sha"))
        check("worker_request_bytes", record.get("worker_request_bytes"),
              record.get("request_bytes"))
        check("worker_request_tasks", record.get("worker_request_tasks"), 4)
        check("worker_manifest_access", record.get("worker_manifest_access"), os.O_RDONLY)
        check("marker_mode", record.get("marker_mode"), 0o600)
        if not 0 <= record.get("challenge_ms", -1) <= CHALLENGE_S * 1000:
            record["failures"].append(
                f"challenge_ms: {record.get('challenge_ms')} outside [0,{CHALLENGE_S * 1000}]")
            ok = False
        if not 0 <= record.get("marker_ms", -1) <= OP_S * 1000:
            record["failures"].append(
                f"marker_ms: {record.get('marker_ms')} outside [0,{OP_S * 1000}]")
            ok = False
    else:
        check("challenge_ms", record.get("challenge_ms"), 0.0)
        check("marker_ms", record.get("marker_ms"), 0.0)
        if record.get("worker_manifest_bytes") is not None:
            record["failures"].append("worker reached ready in a refusal case")
            ok = False
    return ok


def _require_clean(record: dict) -> None:
    """Custody gates. These run after release, so they can only add failures; the
    run summary still turns any of them into an overall FAIL."""
    for label in ("containment_used", "lease_exits", "cleanup_errors", "retained_roots"):
        value = record.get(label)
        expected = [] if label == "cleanup_errors" else 0
        if value != expected:
            record["failures"].append(f"{label}: observed {value!r} != expected {expected!r}")


def _parent_main() -> int:
    if _ORIGINAL_BLOCKER:
        print(f"BLOCKED original_shapes_unavailable: {_ORIGINAL_BLOCKER}")
        return EXIT_INTERNAL
    if FIXED_MEMBER_BYTES != EXPECTED_FIXED_MEMBER_BYTES:
        print(f"BLOCKED fixed_member_bytes: derived {FIXED_MEMBER_BYTES} != "
              f"{EXPECTED_FIXED_MEMBER_BYTES}; json formatting differs from the plan")
        return EXIT_HARNESS
    started = _MODULE_LOAD
    expiry = started + RUN_BUDGET_S
    # The parent precreates the run journal, private and 0600, before any worker
    # exists. Children only ever append to it, with no O_CREAT.
    run_root = _path(Path(tempfile.mkdtemp(prefix="v212-run-")).resolve())
    os.chmod(run_root, 0o700)
    journal = _open_journal(run_root)
    records = []
    for spec in CASES:
        if time.monotonic() >= expiry - TEARDOWN_RESERVE_S:
            records.append({"case": spec["case"],
                            "failures": ["run expiry reached before case"]})
            continue
        record = _run_case(spec, expiry, journal)
        records.append(record)
        try:
            _journal_append(journal, {"v": 1, "kind": "case_result", "pid": os.getpid(),
                                      "case": record["case"],
                                      "returncode": record.get("returncode"),
                                      "failures": len(record["failures"])})
        except OSError as error:
            record["failures"].append(f"journal_append:{error.errno}")
    elapsed = time.monotonic() - started
    journal_lines, journal_mode = _journal_snapshot(journal)
    popen_total = sum(record.get("popen_calls", 0) for record in records)
    max_frame = max((record.get("control_max_frame_bytes") or 0) for record in records)
    markers = sum(record.get("markers", 0) for record in records)
    permits = sum(record.get("permit_issued", 0) for record in records)
    failures = [line for record in records for line in record["failures"]]
    run_failures = []
    if popen_total != POPEN_TOTAL:
        run_failures.append(f"popen_total: {popen_total} != {POPEN_TOTAL}")
    if not elapsed < RUN_BUDGET_S:
        run_failures.append(f"elapsed_s: {elapsed:.4f} not < {RUN_BUDGET_S}")
    if max_frame > CONTROL_MAX_FRAME:
        run_failures.append(f"control_max_frame_bytes: {max_frame} > {CONTROL_MAX_FRAME}")
    if markers != 2 or permits != 2:
        run_failures.append(f"markers/permits: {markers}/{permits} != 2/2")
    if journal_mode != 0o600:
        run_failures.append(f"journal_mode: {journal_mode:o} != 0o600")
    if journal_lines.get("worker_exit", 0) != POPEN_TOTAL:
        run_failures.append(f"journal worker_exit lines: "
                            f"{journal_lines.get('worker_exit', 0)} != {POPEN_TOTAL}")
    if journal_lines.get("case_result", 0) != len(CASES):
        run_failures.append(f"journal case_result lines: "
                            f"{journal_lines.get('case_result', 0)} != {len(CASES)}")
    if journal_lines.get("unparsable", 0):
        run_failures.append(f"journal unparsable lines: {journal_lines['unparsable']}")
    summary = {
        "status": "PASS" if not failures and not run_failures else "FAIL",
        "elapsed_s": round(elapsed, 4),
        "popen_total": popen_total,
        "control_max_frame_bytes": max_frame,
        "control_max_frame_cap": CONTROL_MAX_FRAME,
        "fixed_member_bytes": FIXED_MEMBER_BYTES,
        "worst_valid_manifest_bytes": WORST_VALID_MANIFEST_BYTES,
        "manifest_byte_cap": MANIFEST_BYTE_CAP,
        "declared_cap_shortfall": MANIFEST_BYTE_CAP - WORST_VALID_MANIFEST_BYTES,
        "manifest_count_cap": MANIFEST_COUNT_CAP,
        "markers": markers,
        "permits": permits,
        "largest_manifest_bytes": max(record.get("manifest_bytes", 0) for record in records),
        "journal_mode": journal_mode,
        "journal_lines": journal_lines,
        "cases": [{key: value for key, value in record.items()
                   if key not in ("root_entries",)} for record in records],
        "case_failures": failures,
        "run_failures": run_failures,
    }
    # Failed custody is preserved: the run root, and with it the journal, survives
    # a FAIL so the parent can inspect it. A clean run leaves nothing behind.
    if summary["status"] == "PASS":
        try:
            shutil.rmtree(run_root)
        except OSError as error:
            summary["run_failures"].append(f"run_root_rmtree:{error.errno}")
            summary["status"] = "FAIL"
        summary["retained_run_root"] = ""
    else:
        summary["retained_run_root"] = str(run_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK if summary["status"] == "PASS" else EXIT_HARNESS


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--_v212-worker":
        if _ORIGINAL_BLOCKER:
            _bounded_stderr(f"BLOCKED original_shapes_unavailable: {_ORIGINAL_BLOCKER}")
            return EXIT_INTERNAL
        return _worker_main(argv[1:])
    return _parent_main()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
