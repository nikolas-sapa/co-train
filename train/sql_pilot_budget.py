"""Offline arithmetic and durable single-dispatch permission, not billing proof.

Hashes/references do not authenticate pricing, usage, or callers. Local POSIX
storage and trusted ancestors/writers are required. No network execution exists.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace


__all__ = [
    "BudgetError", "BudgetConfig", "BudgetSnapshot", "RequestRecord",
    "Reservation", "DispatchClaim", "Settlement", "BudgetLedger",
]

MAX_BYTES = 65536
_MAX_MONEY = (1 << 63) - 1
_STATE = "state.json"
_GUARD = "guard"
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_CONFIG_FIELDS = {
    "run_id", "approved_model", "profile_sha256", "authority_ref",
    "limit_usd_micros", "request_limit", "zero_charge_authorized",
}
_REQUEST_FIELDS = {
    "request_id", "maximum_charge_micros", "state", "actual_charge_micros",
    "settlement_evidence_sha256",
}


class BudgetError(Exception):
    """Rejected input/storage, or explicit commit uncertainty. Never retry blindly."""


def _text(value, maximum):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or any(not 32 <= ord(char) <= 126 for char in value)):
        raise BudgetError("invalid printable ASCII identity")


def _digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise BudgetError("invalid SHA-256 digest")


def _money(value, zero_authorized):
    if type(value) is not int or not 0 <= value <= _MAX_MONEY:
        raise BudgetError("invalid integer USD micros")
    if value == 0 and not zero_authorized:
        raise BudgetError("zero charge not authorized")


@dataclass(frozen=True)
class BudgetConfig:
    run_id: str
    approved_model: str
    profile_sha256: str
    authority_ref: str
    limit_usd_micros: int = 50_000_000
    request_limit: int = 25
    zero_charge_authorized: bool = False

    def __post_init__(self):
        _text(self.run_id, 128)
        _text(self.approved_model, 256)
        _digest(self.profile_sha256)
        _text(self.authority_ref, 256)
        if type(self.limit_usd_micros) is not int or self.limit_usd_micros != 50_000_000:
            raise BudgetError("unsupported budget limit")
        if type(self.request_limit) is not int or self.request_limit != 25:
            raise BudgetError("unsupported request limit")
        if type(self.zero_charge_authorized) is not bool:
            raise BudgetError("invalid zero charge authorization")


@dataclass(frozen=True)
class RequestRecord:
    request_id: str
    maximum_charge_micros: int
    state: str
    actual_charge_micros: int | None
    settlement_evidence_sha256: str | None


@dataclass(frozen=True)
class Reservation:
    request_id: str
    maximum_charge_micros: int


@dataclass(frozen=True)
class DispatchClaim:
    request_id: str
    maximum_charge_micros: int


@dataclass(frozen=True)
class Settlement:
    request_id: str
    maximum_charge_micros: int
    actual_charge_micros: int
    settlement_evidence_sha256: str
    halted: bool


def _unsettled(requests):
    return tuple(record for record in requests if record.state != "settled")


@dataclass(frozen=True)
class BudgetSnapshot:
    config: BudgetConfig
    status: str
    requests: tuple[RequestRecord, ...]

    @property
    def settled_charge_micros(self):
        return sum(record.actual_charge_micros for record in self.requests
                   if record.state == "settled")

    @property
    def reserved_charge_micros(self):
        return sum(record.maximum_charge_micros for record in _unsettled(self.requests))

    @property
    def exposure_micros(self):
        return self.settled_charge_micros + self.reserved_charge_micros


def _within_money(config, exposure, maximum):
    return exposure + maximum <= config.limit_usd_micros


def _within_count(config, count):
    return count <= config.request_limit


def _claimable(state):
    return state == "reserved"


def _matching_config(left, right):
    return left == right


def _config(config):
    if type(config) is not BudgetConfig:
        raise BudgetError("expected BudgetConfig")
    config.__post_init__()


def _fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        raise BudgetError("invalid object fields")


def _validate(snapshot):
    """Replay possible reserve/claim/settle history, not merely field types."""
    config = snapshot.config
    _config(config)
    if type(snapshot.status) is not str or snapshot.status not in ("active", "halted_overrun"):
        raise BudgetError("invalid ledger status")
    if not _within_count(config, len(snapshot.requests)):
        raise BudgetError("request count exceeded")
    seen = set()
    settled = 0
    halted = False
    for index, record in enumerate(snapshot.requests):
        _text(record.request_id, 128)
        _money(record.maximum_charge_micros, config.zero_charge_authorized)
        if halted or record.request_id in seen:
            raise BudgetError("invalid request history")
        seen.add(record.request_id)
        if not _within_money(config, settled, record.maximum_charge_micros):
            raise BudgetError("historical reservation exceeds budget")
        if type(record.state) is not str or record.state not in (
                "reserved", "dispatch_claimed", "settled"):
            raise BudgetError("invalid request state")
        if record.state == "settled":
            _money(record.actual_charge_micros, config.zero_charge_authorized)
            _digest(record.settlement_evidence_sha256)
            halted = record.actual_charge_micros > record.maximum_charge_micros
            settled += record.actual_charge_micros
        elif (record.actual_charge_micros is not None
              or record.settlement_evidence_sha256 is not None
              or index != len(snapshot.requests) - 1):
            raise BudgetError("invalid unresolved request history")
    if (snapshot.status == "halted_overrun") != halted:
        raise BudgetError("inconsistent overrun status")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _encode(snapshot):
    _validate(snapshot)
    payload = asdict(snapshot)
    raw = _canonical(dict(
        format="sql_pilot_budget", schema_version=1, payload=payload,
        sha256=hashlib.sha256(_canonical(payload)).hexdigest(),
    ))
    if len(raw) > MAX_BYTES:
        raise BudgetError("ledger exceeds byte limit")
    return raw


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise BudgetError("duplicate JSON field")
        result[key] = value
    return result


def _not_integer(_value):
    raise BudgetError("non-integer JSON number")


def _depth(text):
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 12:
                raise BudgetError("JSON nesting exceeds limit")
        elif char in "]}":
            depth -= 1


def _decode(raw, expected):
    if len(raw) > MAX_BYTES:
        raise BudgetError("ledger exceeds byte limit")
    try:
        text = raw.decode("utf-8")
        _depth(text)
        envelope = json.loads(text, object_pairs_hook=_pairs,
                              parse_float=_not_integer, parse_constant=_not_integer)
        _fields(envelope, {"format", "schema_version", "payload", "sha256"})
        if (type(envelope["format"]) is not str or envelope["format"] != "sql_pilot_budget"
                or type(envelope["schema_version"]) is not int
                or envelope["schema_version"] != 1):
            raise BudgetError("unsupported ledger format or version")
        _digest(envelope["sha256"])
        payload = envelope["payload"]
        _fields(payload, {"config", "status", "requests"})
        if hashlib.sha256(_canonical(payload)).hexdigest() != envelope["sha256"]:
            raise BudgetError("ledger payload digest mismatch")
        _fields(payload["config"], _CONFIG_FIELDS)
        config = BudgetConfig(**payload["config"])
        if not _matching_config(config, expected):
            raise BudgetError("ledger configuration mismatch")
        requests = payload["requests"]
        if type(requests) is not list or not _within_count(config, len(requests)):
            raise BudgetError("invalid request collection")
        for record in requests:
            _fields(record, _REQUEST_FIELDS)
        snapshot = BudgetSnapshot(config, payload["status"],
                                  tuple(RequestRecord(**record) for record in requests))
        _validate(snapshot)
        return snapshot
    except (UnicodeError, ValueError, TypeError, RecursionError, OverflowError):
        raise BudgetError("invalid ledger encoding") from None


def _identity(info):
    return info.st_dev, info.st_ino


def _safe(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise BudgetError("unsafe ledger storage metadata")


def _parts(directory):
    try:
        path = os.fspath(directory)
    except TypeError:
        raise BudgetError("expected absolute ledger directory") from None
    if type(path) is not str or not path.startswith("/") or "\x00" in path:
        raise BudgetError("expected absolute ledger directory")
    parts = path.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise BudgetError("invalid ledger directory components")
    return parts


def _walk(parts):
    fd = os.open("/", _DIR_FLAGS)
    try:
        for part in parts:
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            previous_fd, fd = fd, next_fd
            _close_all(previous_fd)
        return fd
    except BaseException:
        _close_all(fd)
        raise


def _close_all(*descriptors):
    failed = False
    for fd in descriptors:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                failed = True
    if failed:
        raise BudgetError("close uncertain; do not dispatch or retry") from None


def _linked(fd, directory_fd, name):
    info = os.fstat(fd)
    _safe(info)
    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    _safe(named)
    if _identity(info) != _identity(named):
        raise BudgetError("ledger inode changed")
    return info


def _read(directory_fd, expected):
    fd = os.open(_STATE, _READ_FLAGS, dir_fd=directory_fd)
    try:
        before = _linked(fd, directory_fd, _STATE)
        if before.st_size > MAX_BYTES:
            raise BudgetError("ledger exceeds byte limit")
        chunks = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = _linked(fd, directory_fd, _STATE)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise BudgetError("ledger changed during read")
        return _decode(b"".join(chunks), expected)
    finally:
        _close_all(fd)


def _commit(directory_fd, snapshot):
    raw = _encode(snapshot)
    name = ".budget-" + uuid.uuid4().hex + ".tmp"
    fd = None
    owned = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        owned = _identity(os.fstat(fd))
        _linked(fd, directory_fd, name)
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("short ledger write")
            remaining = remaining[written:]
        os.fsync(fd)
        _linked(fd, directory_fd, name)
        os.replace(name, _STATE, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except (OSError, BudgetError):
        raise BudgetError("commit uncertain; do not dispatch or retry") from None
    finally:
        if owned is not None:
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                _safe(info)
                if _identity(info) == owned:
                    os.unlink(name, dir_fd=directory_fd)
            except (OSError, BudgetError):
                pass
        _close_all(fd)


class BudgetLedger:
    """Reopen/revalidate under a stable real guard lock for every operation."""

    def __init__(self, parts, config, directory_identity, guard_identity):
        self._parts = parts
        self._config = config
        self._directory_identity = directory_identity
        self._guard_identity = guard_identity

    @classmethod
    def create(cls, directory, config):
        _config(config)
        parts = _parts(directory)
        parent_fd = directory_fd = guard_fd = None
        try:
            parent_fd = _walk(parts[:-1])
            # Exclusive directory creation is the initialization race gate.
            os.mkdir(parts[-1], 0o700, dir_fd=parent_fd)
            directory_fd = os.open(parts[-1], _DIR_FLAGS, dir_fd=parent_fd)
            _safe(os.fstat(directory_fd), directory=True)
            os.fsync(parent_fd)
            guard_fd = os.open(_GUARD, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=directory_fd)
            _linked(guard_fd, directory_fd, _GUARD)
            fcntl.flock(guard_fd, fcntl.LOCK_EX)
            os.fsync(guard_fd)
            os.fsync(directory_fd)
            # Do not overwrite even an unexpected state in the new directory.
            try:
                os.stat(_STATE, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise BudgetError("ledger already exists")
            snapshot = BudgetSnapshot(config, "active", ())
            _commit(directory_fd, snapshot)
            return snapshot
        except OSError:
            raise BudgetError("creation failed; do not dispatch or retry") from None
        finally:
            _close_all(guard_fd, directory_fd, parent_fd)

    @classmethod
    def open(cls, directory, expected_config):
        _config(expected_config)
        parts = _parts(directory)
        directory_fd = guard_fd = None
        try:
            directory_fd = _walk(parts)
            info = os.fstat(directory_fd)
            _safe(info, directory=True)
            # Never O_CREAT: state without its original guard is unrecoverable here.
            guard_fd = os.open(_GUARD, _READ_FLAGS, dir_fd=directory_fd)
            _linked(guard_fd, directory_fd, _GUARD)
            fcntl.flock(guard_fd, fcntl.LOCK_EX)
            guard = _linked(guard_fd, directory_fd, _GUARD)
            if guard.st_size != 0:
                raise BudgetError("guard must be empty")
            _read(directory_fd, expected_config)
            return cls(parts, expected_config, _identity(info), _identity(guard))
        except OSError:
            raise BudgetError("cannot safely open ledger") from None
        finally:
            _close_all(guard_fd, directory_fd)

    @contextmanager
    def _locked(self):
        directory_fd = guard_fd = None
        try:
            directory_fd = _walk(self._parts)
            info = os.fstat(directory_fd)
            _safe(info, directory=True)
            if _identity(info) != self._directory_identity:
                raise BudgetError("ledger directory changed")
            guard_fd = os.open(_GUARD, _READ_FLAGS, dir_fd=directory_fd)
            _linked(guard_fd, directory_fd, _GUARD)
            fcntl.flock(guard_fd, fcntl.LOCK_EX)
            guard = _linked(guard_fd, directory_fd, _GUARD)
            if _identity(guard) != self._guard_identity or guard.st_size != 0:
                raise BudgetError("ledger guard changed")
            yield directory_fd, _read(directory_fd, self._config)
        except OSError:
            raise BudgetError("ledger I/O uncertain; do not dispatch or retry") from None
        finally:
            _close_all(guard_fd, directory_fd)

    def snapshot(self):
        with self._locked() as (_, snapshot):
            return snapshot

    def reserve(self, request_id, max_charge_micros):
        _text(request_id, 128)
        _money(max_charge_micros, self._config.zero_charge_authorized)
        with self._locked() as (directory_fd, snapshot):
            if (snapshot.status != "active" or _unsettled(snapshot.requests)
                    or any(record.request_id == request_id for record in snapshot.requests)
                    or not _within_count(snapshot.config, len(snapshot.requests) + 1)
                    or not _within_money(snapshot.config, snapshot.exposure_micros,
                                         max_charge_micros)):
                raise BudgetError("reservation not admitted")
            record = RequestRecord(request_id, max_charge_micros, "reserved", None, None)
            _commit(directory_fd, replace(snapshot, requests=snapshot.requests + (record,)))
            return Reservation(request_id, max_charge_micros)

    def claim_dispatch(self, request_id):
        _text(request_id, 128)
        with self._locked() as (directory_fd, snapshot):
            record = self._last(snapshot, request_id)
            if not _claimable(record.state):
                raise BudgetError("dispatch claim not available")
            claimed = replace(record, state="dispatch_claimed")
            _commit(directory_fd, replace(
                snapshot, requests=snapshot.requests[:-1] + (claimed,)))
            return DispatchClaim(request_id, record.maximum_charge_micros)

    def settle(self, request_id, actual_charge_micros, settlement_evidence_sha256):
        _text(request_id, 128)
        _money(actual_charge_micros, self._config.zero_charge_authorized)
        _digest(settlement_evidence_sha256)
        with self._locked() as (directory_fd, snapshot):
            record = self._last(snapshot, request_id)
            if record.state != "dispatch_claimed":
                raise BudgetError("settlement not available")
            halted = actual_charge_micros > record.maximum_charge_micros
            settled = replace(record, state="settled", actual_charge_micros=actual_charge_micros,
                              settlement_evidence_sha256=settlement_evidence_sha256)
            _commit(directory_fd, replace(
                snapshot, status="halted_overrun" if halted else "active",
                requests=snapshot.requests[:-1] + (settled,)))
            return Settlement(request_id, record.maximum_charge_micros,
                              actual_charge_micros, settlement_evidence_sha256, halted)

    @staticmethod
    def _last(snapshot, request_id):
        if not snapshot.requests or snapshot.requests[-1].request_id != request_id:
            raise BudgetError("request not available for transition")
        return snapshot.requests[-1]
