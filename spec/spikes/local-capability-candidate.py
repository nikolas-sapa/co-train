#!/usr/bin/env python3
"""V189 local-capability spike candidate (standalone, stdlib only, fixed modes).

SOURCE-ONLY DELIVERY. The authoring worker executed nothing: no imports of
this module, no run, no spawn, no signal, no test. Every subprocess and
socket operation below exists only as source. The parent reviews, then owns
execution and every real spawn/signal decision.

Run (parent-owned): ``python3 spec/spikes/local-capability-candidate.py``

Fixed modes
    (no extra argv)      harness: runs cases C1..C7, prints one numeric line
                         per case, a TOTAL gate line and RESULT, exit 0 only
                         when every gate passes, 1 on any gate failure, 2 on
                         internal error.
    --spike-child FD     the FIXED worker child. Reads framed JSON only from
                         the one inherited allowlisted socketpair FD.
    --spike-sentinel FD  the FIXED sentinel child (stand-in): waits for one
                         ``arm`` frame, replies ``armed``, exits 0. Never
                         touches the filesystem.

No SDK, no App, no Sandbox, no GPU, no network, no provider, no credentials,
no installed-distribution enumeration. No ``os.fork``, no ``preexec_fn``, no
pickling, no serialization of sealed authorization objects, no dynamic or
eval'd child code. No socket service, no TCP, no bind/listen: only
``socket.socketpair()`` channels created by the parent. The protocol carries
no PID field at all, so no signal can ever be derived from a reported PID;
signals only ever travel through a retained ``Popen`` handle, poll-checked
first, and never after reap.

PROVES (only if the parent runs this and every gate passes)
    * Copied JSON alone yields 0 observed operations against a fresh fixed
      child: absent inherited endpoint (C1a), replayed valid-looking
      ``grant_open`` bytes into a fresh invocation (C1b), replayed
      ``request_open`` bytes into a fresh parent session (C1c), wrong session
      tags on both ends (C2).
    * One live session admits once, grants open once, arms once, grants
      create once. Duplicate seq, reordered seq, oversize metadata,
      duplicate JSON keys, nonfinite numbers, bool-as-int seq and extra
      fields all refuse with 0 additional ops (C5).
    * Create never grants before an independent-process ARMED ACK; a dead or
      absent sentinel yields 0 ops (C3).
    * Deadline extension refuses on both ends; second admission, rearm and
      nonce reuse refuse (C6).
    * Disconnect after a consumed permit yields at most 1 op and 0
      replacement/reissue/retry (C7).

SHORTCUT (probe-only, NOT production)
    * Same-user socketpair delegation is a local first-party DELEGATION
      CONCEPT between a parent and its own freshly exec'd children. It is
      NOT hostile-same-user security (a same-uid attacker outside this
      contract is out of scope) and NOT actual authorization: no sealed
      authority, no billing, no owner API.
    * The sentinel stand-in is a fixed toy child, or a harness-controlled
      channel where explicitly labeled, not a production independent
      watchdog.
    * The witnessed operation is one harmless exclusive marker plus a single
      appended line, not a real App/Sandbox create. "open" and "create" are
      synthetic permits only.
    * Scripted child ends (harness-held socketpair ends) exercise parent-side
      validation directly; real children cover the end-to-end flows.
    * The 8 s toy lease plus the declared 10 s external parent timeout are
      experimental orphan protection, not production supervision.
    * Wall-clock ``deadline_unix`` bounds are spike-grade, not the monotonic
      production discipline.

MISSING (gaps the parent must weigh before freezing the real API)
    * Everything is UNRUN: all counters, exit codes and timing gates are
      planned, not observed.
    * ``socket.socketpair()`` family/type behaviour and FD inheritance are
      platform-sensitive and unverified here.
    * No coverage for a child killed between ``O_EXCL`` and the append beyond
      the <=1-op gate; no coverage for clock skew on ``deadline_unix``.
    * No multi-session concurrency; no real SDK/GPU/App paths; no production
      owner/billing/watchdog integration (explicitly deferred).
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

# --------------------------------------------------------------------------
# Fixed constants (no cap may be increased, no wait retried, no permit
# reissued; these are the declared worst-case gates from the plan).
# --------------------------------------------------------------------------

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 65536
# Every socketpair end is widened to this buffer size so that any legal frame
# (<= MAX_FRAME_BYTES) can always be written without blocking against a
# same-thread reader. Without this, the single oversize-metadata injection in
# C5 would sit exactly at the platform's default AF_UNIX buffer and could
# deadlock the harness instead of producing a refusal.
SOCKET_BUFFER_BYTES = 1 << 18
MAX_METADATA_BYTES = 8192
MAX_REASON_CHARS = 128
MAX_METADATA_STR_CHARS = 256
MARKER_NAME = "spike-op.marker"

CHILD_LEASE_SECONDS = 8.0
TOTAL_GATE_SECONDS = 8.0
TEARDOWN_RESERVE_SECONDS = 0.25
MIN_WAIT_SECONDS = 0.05
SELECT_SLICE_SECONDS = 1.0
POST_KILL_WAIT_SECONDS = 0.20
CASE7B_ACK_WAIT_SECONDS = 0.50

EXIT_OK = 0
EXIT_GATE_FAIL = 1
EXIT_INTERNAL = 2
EXIT_NO_CHANNEL = 3
EXIT_AMBIGUOUS = 4
EXIT_REFUSED = 5
EXIT_PROTOCOL = 6
EXIT_OP_FAILED = 7
EXIT_LEASE = 97

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

STATE_FRESH = "fresh"
STATE_ADMITTED = "admitted"
STATE_OPEN_GRANTED = "open_granted"
STATE_ARMED = "armed"
STATE_CREATE_GRANTED = "create_granted"
STATE_CONSUMED = "consumed"

SESSION_RE = re.compile(r"[0-9a-f]{32}")

PARENT_TO_CHILD_KINDS = frozenset(
    {"ready", "grant_open", "grant_create", "refusal", "arm"}
)
CHILD_TO_PARENT_KINDS = frozenset(
    {"ack_ready", "request_open", "request_create", "ack_create", "armed"}
)
# The FIXED worker accepts exactly one kind per stage; anything else at that
# stage is a protocol violation and exits without any operation.
WORKER_STAGE_READY = frozenset({"ready"})
WORKER_STAGE_OPEN = frozenset({"grant_open", "refusal"})
WORKER_STAGE_CREATE = frozenset({"grant_create", "refusal"})
SENTINEL_INBOUND_KINDS = frozenset({"arm"})

# Exact bounded schemas: extra or missing fields refuse.
SCHEMAS = {
    "ready": frozenset(
        {"v", "kind", "session", "seq", "deadline_unix", "op_root", "marker_name"}
    ),
    "grant_open": frozenset({"v", "kind", "session", "seq", "deadline_unix"}),
    "grant_create": frozenset(
        {"v", "kind", "session", "seq", "deadline_unix", "metadata"}
    ),
    "refusal": frozenset({"v", "kind", "session", "seq", "reason"}),
    "arm": frozenset({"v", "kind", "session", "seq"}),
    "ack_ready": frozenset({"v", "kind", "session", "seq"}),
    "request_open": frozenset({"v", "kind", "session", "seq"}),
    "request_create": frozenset(
        {"v", "kind", "session", "seq", "deadline_unix", "metadata"}
    ),
    "ack_create": frozenset({"v", "kind", "session", "seq", "marker"}),
    "armed": frozenset({"v", "kind", "session", "seq"}),
}

COUNTER_NAMES = (
    "admissions",
    "grants_open",
    "grants_create",
    "armed_acks",
    "arm_failures",
    "refusals",
    "acks_create",
    # `retries` and `reissues` are structurally always 0: no retry or reissue
    # code path exists anywhere in this file. The counters exist to prove the
    # absence, not to count occurrences.
    "retries",
    "reissues",
)


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------


class SpikeError(Exception):
    """Base class for spike-local errors."""


class ProtocolViolation(SpikeError):
    """A frame failed strict validation. Carries the fixed refusal reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RefusedFrame(SpikeError):
    """Parent-side refusal was recorded; the caller must not continue."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RefusedByParent(SpikeError):
    """Child-side: the parent sent an explicit refusal frame."""


class ChannelClosed(SpikeError):
    """Peer closed the channel (EOF or zero-length send)."""


class WaitTimeout(SpikeError):
    """A shared absolute deadline expired before the frame arrived."""


class AmbiguousDispatch(SpikeError):
    """Parent-side ambiguous outcome: session consumed BEFORE the socket closed."""


class OpFailure(SpikeError):
    """Child-side: the single witnessed operation could not be completed."""


class NonceReplay(SpikeError):
    """A nonce was re-registered in the run-wide ledger."""


class _DuplicateKey(Exception):
    """Internal: duplicate JSON object key."""


class _Nonfinite(Exception):
    """Internal: NaN/Infinity/-Infinity literal."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _remaining(deadline: float) -> float:
    """Wait budget clamped to the shared absolute deadline minus teardown reserve.

    Never a sequential full timeout, never an increased cap.
    """
    left = deadline - time.monotonic() - TEARDOWN_RESERVE_SECONDS
    return left if left > MIN_WAIT_SECONDS else MIN_WAIT_SECONDS


def _close_quiet(sock) -> None:
    try:
        sock.close()
    except Exception:
        pass


def _is_printable_ascii(text: str) -> bool:
    return all(0x20 <= ord(ch) <= 0x7E for ch in text)


def _is_finite_number(value) -> bool:
    if type(value) is bool:
        return False
    if type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    return False


def _metadata_scalar_ok(value) -> bool:
    if value is None or type(value) is bool or type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is str:
        return len(value) <= MAX_METADATA_STR_CHARS and _is_printable_ascii(value)
    return False


# --------------------------------------------------------------------------
# Framing: 4-byte big-endian length prefix + UTF-8 JSON payload
# --------------------------------------------------------------------------


def encode_frame(frame: dict) -> bytes:
    payload = json.dumps(frame, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolViolation("frame_size")
    return payload


def _recv_exact(sock, count: int, deadline: float) -> bytes:
    buf = bytearray()
    while len(buf) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WaitTimeout("read_deadline")
        ready = select.select([sock], [], [], min(remaining, SELECT_SLICE_SECONDS))
        if not ready[0]:
            continue
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise ChannelClosed("eof")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock, deadline: float) -> bytes:
    header = _recv_exact(sock, 4, deadline)
    length = int.from_bytes(header, "big")
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise ProtocolViolation("frame_size")
    return _recv_exact(sock, length, deadline)


def write_frame(sock, payload: bytes, deadline: float) -> None:
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolViolation("frame_size")
    buf = len(payload).to_bytes(4, "big") + payload
    sent = 0
    while sent < len(buf):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WaitTimeout("write_deadline")
        ready = select.select([], [sock], [], min(remaining, SELECT_SLICE_SECONDS))
        if not ready[1]:
            continue
        count = sock.send(buf[sent:])
        if count == 0:
            raise ChannelClosed("send_zero")
        sent += count


# --------------------------------------------------------------------------
# Strict validation (both ends, fixed rules)
# --------------------------------------------------------------------------


def _strict_loads(payload: bytes):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolViolation("malformed_json")

    def pairs_hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise _DuplicateKey()
            out[key] = value
        return out

    def const_hook(_name):
        raise _Nonfinite()

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=const_hook)
    except _DuplicateKey:
        raise ProtocolViolation("duplicate_keys")
    except _Nonfinite:
        raise ProtocolViolation("nonfinite")
    except ValueError:
        raise ProtocolViolation("malformed_json")


def _validate_metadata(value) -> None:
    if not isinstance(value, dict):
        raise ProtocolViolation("metadata_shape")
    try:
        blob = json.dumps(value, separators=(",", ":"), allow_nan=False, sort_keys=True)
    except (TypeError, ValueError):
        raise ProtocolViolation("metadata_shape")
    if len(blob.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ProtocolViolation("metadata_oversize")
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > MAX_METADATA_STR_CHARS:
            raise ProtocolViolation("metadata_scalar")
        if not _is_printable_ascii(key):
            raise ProtocolViolation("metadata_scalar")
        if not _metadata_scalar_ok(item):
            raise ProtocolViolation("metadata_scalar")


def _validate_root(value, expected_root) -> None:
    if not isinstance(value, str) or not value:
        raise ProtocolViolation("op_root_shape")
    if not os.path.isabs(value):
        raise ProtocolViolation("op_root_shape")
    if ".." in value.split("/"):
        raise ProtocolViolation("op_root_traversal")
    if os.path.normpath(value) != value:
        raise ProtocolViolation("op_root_traversal")
    if expected_root is not None and value != expected_root:
        raise ProtocolViolation("op_root_mismatch")


def decode_and_validate(
    payload: bytes,
    allowed_kinds,
    expected_session,
    last_seq: int,
    deadline_bound=None,
    expected_root=None,
) -> dict:
    """Strictly decode one frame. Raises ProtocolViolation with a fixed reason."""
    frame = _strict_loads(payload)
    if not isinstance(frame, dict):
        raise ProtocolViolation("not_object")

    if "kind" not in frame:
        raise ProtocolViolation("missing_fields")
    kind = frame["kind"]
    if not isinstance(kind, str) or kind not in allowed_kinds or kind not in SCHEMAS:
        raise ProtocolViolation("kind_not_allowed")

    expected_fields = SCHEMAS[kind]
    actual_fields = set(frame.keys())
    if actual_fields - expected_fields:
        raise ProtocolViolation("extra_fields")
    if expected_fields - actual_fields:
        raise ProtocolViolation("missing_fields")

    if type(frame["v"]) is not int or frame["v"] != PROTOCOL_VERSION:
        raise ProtocolViolation("version_mismatch")

    session = frame["session"]
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
        raise ProtocolViolation("session_shape")
    if expected_session is not None and session != expected_session:
        raise ProtocolViolation("session_mismatch")

    seq = frame["seq"]
    if type(seq) is not int:
        raise ProtocolViolation("seq_not_monotonic")
    if seq < 1 or seq <= last_seq:
        raise ProtocolViolation("seq_not_monotonic")

    if "deadline_unix" in expected_fields:
        deadline_unix = frame["deadline_unix"]
        if not _is_finite_number(deadline_unix) or deadline_unix <= 0:
            raise ProtocolViolation("deadline_shape")
        if deadline_bound is not None and deadline_unix > deadline_bound:
            raise ProtocolViolation("deadline_extension")

    if "op_root" in expected_fields:
        _validate_root(frame["op_root"], expected_root)

    if "marker_name" in expected_fields:
        if frame["marker_name"] != MARKER_NAME:
            raise ProtocolViolation("marker_mismatch")
    if "marker" in expected_fields:
        if frame["marker"] != MARKER_NAME:
            raise ProtocolViolation("marker_mismatch")

    if "reason" in expected_fields:
        reason = frame["reason"]
        if not isinstance(reason, str) or len(reason) > MAX_REASON_CHARS:
            raise ProtocolViolation("reason_shape")
        if not _is_printable_ascii(reason):
            raise ProtocolViolation("reason_shape")

    if "metadata" in expected_fields:
        _validate_metadata(frame["metadata"])

    return frame


def encode_child_frame(kind: str, session: str, seq: int, **extra) -> bytes:
    frame = {"v": PROTOCOL_VERSION, "kind": kind, "session": session, "seq": seq}
    frame.update(extra)
    return encode_frame(frame)


# --------------------------------------------------------------------------
# Run-wide nonce ledger
# --------------------------------------------------------------------------


class NonceLedger:
    """Run-wide single-use nonce registry. Re-registration refuses."""

    def __init__(self) -> None:
        self._seen = set()
        self._lock = threading.Lock()

    def new_nonce(self) -> str:
        with self._lock:
            for _ in range(16):
                candidate = secrets.token_hex(16)
                if candidate not in self._seen:
                    self._seen.add(candidate)
                    return candidate
        raise NonceReplay("nonce_exhausted")

    def register(self, nonce: str) -> None:
        if not isinstance(nonce, str) or not SESSION_RE.fullmatch(nonce):
            raise ProtocolViolation("session_shape")
        with self._lock:
            if nonce in self._seen:
                raise NonceReplay("nonce_replay")
            self._seen.add(nonce)


# --------------------------------------------------------------------------
# Resource tracking with independent cleanup attempts (V187 constraints)
# --------------------------------------------------------------------------


class Resources:
    """Tracks sockets, Popen handles and witness roots for one case.

    Cleanup attempts every resource independently (own try/except each); one
    failure never skips the others and never masks the primary error. Roots
    are released only after every tracked child was actually reaped; a reap
    failure keeps ownership (handle retained, root NOT released).
    """

    def __init__(self) -> None:
        self.sockets = []
        self.popens = []
        self.roots = []
        self.errors = []
        self.retained_roots = []
        self.reap_failed = False

    def track_socket(self, sock):
        self.sockets.append(sock)
        return sock

    def track_popen(self, popen):
        self.popens.append(popen)
        return popen

    def track_root(self, path: str) -> str:
        self.roots.append(path)
        return path

    def lease_exits(self) -> int:
        return sum(1 for popen in self.popens if popen.returncode == EXIT_LEASE)

    def cleanup(self, deadline: float) -> None:
        # 1. Reap every child independently. Signals only through the
        #    retained handle, poll-checked first, never after reap.
        for popen in list(self.popens):
            try:
                if popen.poll() is None:
                    popen.kill()
                    popen.wait(timeout=POST_KILL_WAIT_SECONDS)
                else:
                    popen.wait(timeout=max(MIN_WAIT_SECONDS, _remaining(deadline)))
            except Exception as exc:
                self.reap_failed = True
                self.errors.append("reap:%s" % type(exc).__name__)
        # 2. Close every socket independently.
        for sock in list(self.sockets):
            try:
                sock.close()
            except Exception as exc:
                self.errors.append("socket:%s" % type(exc).__name__)
        # 3. Release roots only when every reap succeeded.
        for path in list(self.roots):
            if self.reap_failed:
                self.retained_roots.append(path)
                continue
            try:
                shutil.rmtree(path)
            except Exception as exc:
                self.errors.append("root:%s" % type(exc).__name__)
                self.retained_roots.append(path)


def _mk_root(res: Resources, prefix: str) -> str:
    """Fresh private (0700) owner-owned witness root with no existing files."""
    return res.track_root(tempfile.mkdtemp(prefix=prefix))


def _widen_buffers(sock) -> None:
    """Best-effort: make every legal frame writable without flow-control blocking."""
    for option in (socket.SO_RCVBUF, socket.SO_SNDBUF):
        try:
            sock.setsockopt(socket.SOL_SOCKET, option, SOCKET_BUFFER_BYTES)
        except OSError:
            pass


def _achieved_sndbuf(sock) -> int:
    try:
        return int(sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF))
    except (OSError, ValueError):
        return 0


def _mk_pair(res: Resources):
    parent_end, child_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    _widen_buffers(parent_end)
    _widen_buffers(child_end)
    res.track_socket(parent_end)
    res.track_socket(child_end)
    return parent_end, child_end


def _spawn(mode: str, channel_fd: int, pass_fds) -> subprocess.Popen:
    """Fresh exec of this same fixed file. No fork, no preexec_fn, no pickling."""
    argv = [sys.executable, os.path.abspath(__file__), mode, str(channel_fd)]
    # Fixed argv, fixed file, minimal environment, new session, no shell.
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=tuple(pass_fds),
        close_fds=True,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def _spawn_worker(res: Resources, child_end, inherit: bool):
    """Spawn the FIXED worker; close the parent's copy of the child end at once."""
    channel_fd = child_end.fileno()
    popen = res.track_popen(
        _spawn("--spike-child", channel_fd, (channel_fd,) if inherit else ())
    )
    _close_quiet(child_end)  # immediate FD protection, before any wait
    return popen, channel_fd


def _spawn_sentinel(res: Resources, child_end):
    channel_fd = child_end.fileno()
    popen = res.track_popen(_spawn("--spike-sentinel", channel_fd, (channel_fd,)))
    _close_quiet(child_end)  # immediate FD protection, before any wait
    return popen, channel_fd


def _reap(popen, deadline: float):
    """Reap through the retained handle only. Returns returncode or None."""
    try:
        return popen.wait(timeout=max(MIN_WAIT_SECONDS, _remaining(deadline)))
    except Exception:
        pass
    try:
        if popen.poll() is None:
            popen.kill()
        return popen.wait(timeout=POST_KILL_WAIT_SECONDS)
    except Exception:
        return None


def _snapshot_root(root: str) -> dict:
    """Observed operation counter. Taken only AFTER the actual worker reap."""
    snap = {"ops": -1, "mode": -1, "lines": -1}
    try:
        names = os.listdir(root)
    except OSError:
        return snap
    snap["ops"] = len(names)
    if MARKER_NAME not in names:
        return snap
    path = os.path.join(root, MARKER_NAME)
    try:
        snap["mode"] = os.lstat(path).st_mode & 0o777
    except OSError:
        pass
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        data = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
        snap["lines"] = len(
            [line for line in data.decode("utf-8", "replace").split("\n") if line]
        )
    except OSError:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    return snap


# --------------------------------------------------------------------------
# Parent-side session
# --------------------------------------------------------------------------


class CapabilitySession:
    """One retained socketpair end, one nonce, one absolute cap, single use.

    State machine: fresh -> admitted -> open_granted -> armed ->
    create_granted -> consumed. Deadlines can never extend ``cap_unix``.
    """

    def __init__(self, sock, session: str, op_root: str, cap_unix: float) -> None:
        self.sock = sock
        self.session = session
        self.op_root = op_root
        self.cap_unix = cap_unix
        self.state = STATE_FRESH
        self.counters = {name: 0 for name in COUNTER_NAMES}
        self.refusal_reasons = []
        self.last_payload = None
        self._in_seq = 0
        self._out_seq = 0

    @property
    def inbound_seq(self) -> int:
        """Last ACCEPTED inbound seq. Refused frames never advance it."""
        return self._in_seq

    @property
    def outbound_seq(self) -> int:
        """Number of frames this session actually put on the wire."""
        return self._out_seq

    # -- outbound ---------------------------------------------------------

    def _next_out(self) -> int:
        self._out_seq += 1
        return self._out_seq

    def _send(self, kind: str, deadline: float, **extra) -> bytes:
        if self.state == STATE_CONSUMED:
            raise ProtocolViolation("session_consumed")
        if kind not in PARENT_TO_CHILD_KINDS:
            raise ProtocolViolation("kind_not_allowed")
        frame = {
            "v": PROTOCOL_VERSION,
            "kind": kind,
            "session": self.session,
            "seq": self._next_out(),
        }
        frame.update(extra)
        payload = encode_frame(frame)
        write_frame(self.sock, payload, deadline)
        self.last_payload = payload
        return payload

    def send_raw(self, payload: bytes, deadline: float) -> None:
        """Replay foreign bytes verbatim. Never touches seq, state or counters."""
        write_frame(self.sock, payload, deadline)

    def _refuse(self, reason: str, deadline: float, send: bool = True) -> None:
        self.counters["refusals"] += 1
        self.refusal_reasons.append(reason)
        if not send or self.sock is None or self.state == STATE_CONSUMED:
            return
        try:
            self._send("refusal", deadline, reason=reason[:MAX_REASON_CHARS])
        except Exception:
            pass

    # -- lifecycle --------------------------------------------------------

    def admit(self, deadline: float) -> None:
        if self.state != STATE_FRESH:
            # Second admission refuses and sends NO frame.
            self._refuse("second_admission", deadline, send=False)
            raise RefusedFrame("second_admission")
        self._send(
            "ready",
            deadline,
            deadline_unix=self.cap_unix,
            op_root=self.op_root,
            marker_name=MARKER_NAME,
        )
        self.counters["admissions"] += 1
        self.state = STATE_ADMITTED

    def _read_validated(self, deadline: float) -> dict:
        try:
            payload = read_frame(self.sock, deadline)
            frame = decode_and_validate(
                payload,
                CHILD_TO_PARENT_KINDS,
                self.session,
                self._in_seq,
                deadline_bound=self.cap_unix,
                expected_root=None,
            )
        except ProtocolViolation as exc:
            # Refused frames never advance the ledger.
            self._refuse(exc.reason, deadline)
            raise RefusedFrame(exc.reason) from exc
        except (ChannelClosed, WaitTimeout) as exc:
            # Consume the session BEFORE the socket closes; never auto-retry.
            self.close_ambiguous()
            raise AmbiguousDispatch(str(exc)) from exc
        except OSError as exc:
            self.close_ambiguous()
            raise AmbiguousDispatch(type(exc).__name__) from exc
        self._in_seq = frame["seq"]
        return frame

    def probe_inbound(self, deadline: float) -> dict:
        """Read and strictly validate one inbound frame without a state expectation.

        Used only by the C5 injection probe; a refusal is recorded exactly as
        for any other inbound violation and never advances the ledger.
        """
        return self._read_validated(deadline)

    def await_ack_ready(self, deadline: float) -> dict:
        frame = self._read_validated(deadline)
        if frame["kind"] != "ack_ready" or self.state != STATE_ADMITTED:
            self._refuse("state_order", deadline)
            raise RefusedFrame("state_order")
        return frame

    def await_request_open(self, deadline: float) -> dict:
        frame = self._read_validated(deadline)
        if frame["kind"] != "request_open" or self.state != STATE_ADMITTED:
            self._refuse("state_order", deadline)
            raise RefusedFrame("state_order")
        return frame

    def grant_open(self, deadline: float) -> bytes:
        if self.state != STATE_ADMITTED:
            self._refuse("state_order", deadline, send=False)
            raise RefusedFrame("state_order")
        payload = self._send("grant_open", deadline, deadline_unix=self.cap_unix)
        self.counters["grants_open"] += 1
        self.state = STATE_OPEN_GRANTED
        return payload

    def arm(self, link, deadline: float) -> None:
        # Rearm check first: a session arms at most once, ever.
        if self.counters["armed_acks"] >= 1:
            self.counters["arm_failures"] += 1
            self._refuse("rearm_refused", deadline, send=False)
            raise RefusedFrame("rearm_refused")
        if link is None:
            self.counters["arm_failures"] += 1
            self._refuse("sentinel_absent", deadline, send=False)
            raise RefusedFrame("sentinel_absent")
        if not link.usable():
            self.counters["arm_failures"] += 1
            self._refuse("sentinel_dead", deadline, send=False)
            raise RefusedFrame("sentinel_dead")
        if self.state != STATE_OPEN_GRANTED:
            self._refuse("state_order", deadline, send=False)
            raise RefusedFrame("state_order")
        link.arm(deadline)
        self.counters["armed_acks"] += 1
        self.state = STATE_ARMED

    def await_request_create(self, deadline: float) -> dict:
        frame = self._read_validated(deadline)
        if frame["kind"] != "request_create":
            self._refuse("state_order", deadline)
            raise RefusedFrame("state_order")
        if self.state != STATE_ARMED:
            self._refuse("not_armed", deadline)
            raise RefusedFrame("not_armed")
        return frame

    def grant_create(self, frame: dict, deadline: float) -> bytes:
        if self.state != STATE_ARMED:
            self._refuse("state_order", deadline, send=False)
            raise RefusedFrame("state_order")
        payload = self._send(
            "grant_create",
            deadline,
            deadline_unix=self.cap_unix,
            metadata=frame["metadata"],
        )
        self.counters["grants_create"] += 1
        self.state = STATE_CREATE_GRANTED
        return payload

    def await_ack_create(self, deadline: float) -> dict:
        frame = self._read_validated(deadline)
        if frame["kind"] != "ack_create" or self.state != STATE_CREATE_GRANTED:
            self._refuse("state_order", deadline)
            raise RefusedFrame("state_order")
        self.counters["acks_create"] += 1
        self.state = STATE_CONSUMED
        return frame

    def close_ambiguous(self) -> None:
        """Mark consumed FIRST, then close. No replacement, no reissue, no retry."""
        self.state = STATE_CONSUMED
        if self.sock is not None:
            _close_quiet(self.sock)


def _new_session(ledger: NonceLedger, sock, op_root: str, deadline: float):
    cap_unix = time.time() + max(0.0, deadline - time.monotonic())
    return CapabilitySession(sock, ledger.new_nonce(), op_root, cap_unix)


def _aggregate(sessions, names=COUNTER_NAMES) -> dict:
    out = {}
    for name in names:
        out[name] = sum(session.counters[name] for session in sessions)
    return out


def _second_grants(sessions) -> int:
    """Observed absence of any second create grant per session."""
    return sum(max(0, s.counters["grants_create"] - 1) for s in sessions)


# --------------------------------------------------------------------------
# Sentinel link (independent-process ARMED ACK gate)
# --------------------------------------------------------------------------


class SentinelLink:
    """One retained sentinel channel. SHORTCUT: toy child or controlled channel."""

    def __init__(self, sock, session: str, popen=None, controlled: bool = False):
        self.sock = sock
        self.session = session
        self.popen = popen
        self.controlled = controlled
        self.reaped = False
        self.exit_code = None
        self._in_seq = 0
        self._out_seq = 0

    def usable(self) -> bool:
        if self.sock is None:
            return False
        if self.controlled:
            return True
        if self.popen is None or self.reaped:
            return False
        return self.popen.poll() is None

    def arm(self, deadline: float) -> dict:
        self._out_seq += 1
        payload = encode_child_frame("arm", self.session, self._out_seq)
        write_frame(self.sock, payload, deadline)
        frame_payload = read_frame(self.sock, deadline)
        frame = decode_and_validate(
            frame_payload,
            {"armed"},
            self.session,
            self._in_seq,
            deadline_bound=None,
            expected_root=None,
        )
        self._in_seq = frame["seq"]
        return frame

    def reap(self, deadline: float):
        if self.popen is None or self.reaped:
            return self.exit_code
        self.exit_code = _reap(self.popen, deadline)
        self.reaped = self.exit_code is not None
        return self.exit_code

    def terminate_and_reap(self, deadline: float) -> None:
        """Terminate BEFORE any arm, through the retained handle, poll-checked."""
        if self.popen is None or self.reaped:
            return
        try:
            if self.popen.poll() is None:
                self.popen.terminate()
        except Exception:
            pass
        self.reap(deadline)


def _new_sentinel_link(res: Resources, ledger: NonceLedger):
    parent_end, child_end = _mk_pair(res)
    popen, _fd = _spawn_sentinel(res, child_end)
    return SentinelLink(parent_end, ledger.new_nonce(), popen=popen)


def _new_controlled_sentinel_link(res: Resources, ledger: NonceLedger, deadline: float):
    """SHORTCUT: harness-held peer end with a pre-scripted ``armed`` reply.

    This is an explicitly controlled live channel, not an independent process.
    It is used only for the C7b silent-child disconnect sub-flow, where the
    sentinel is not the subject of the assertion.
    """
    parent_end, peer_end = _mk_pair(res)
    nonce = ledger.new_nonce()
    write_frame(peer_end, encode_child_frame("armed", nonce, 1), deadline)
    return SentinelLink(parent_end, nonce, popen=None, controlled=True)


# --------------------------------------------------------------------------
# Scripted child end (SHORTCUT: exercises parent-side validation directly)
# --------------------------------------------------------------------------


class ScriptedPeer:
    """Harness-held child end of a socketpair. Not a real child process.

    SHORTCUT: exercises parent-side strict validation directly. It cannot
    perform the witnessed operation at all, so any op it reports would be a
    harness bug, not child behaviour; the real-child sub-flows carry the
    end-to-end evidence.
    """

    def __init__(self, sock, session: str) -> None:
        self.sock = sock
        self.session = session
        self.last_payload = None
        self.writers = []
        self._seq = 0
        achieved = _achieved_sndbuf(sock)
        self.inline_limit = achieved - 64 if achieved > 64 else 4096

    def _write(self, payload: bytes, deadline: float) -> None:
        if len(payload) + 4 <= self.inline_limit:
            write_frame(self.sock, payload, deadline)
            return

        # Defensive only: a payload larger than the achieved socket buffer
        # would block a same-thread writer against a same-thread reader. The
        # widened buffers make this unreachable for every legal frame; if a
        # platform refuses the widening, write from a daemon thread so the
        # caller can read concurrently instead of hanging the harness.
        def _writer() -> None:
            try:
                write_frame(self.sock, payload, deadline)
            except Exception:
                pass

        thread = threading.Thread(target=_writer, daemon=True)
        thread.start()
        self.writers.append(thread)

    def send(self, kind: str, deadline: float, **extra) -> bytes:
        self._seq += 1
        return self.send_seq(kind, self._seq, deadline, **extra)

    def send_seq(self, kind: str, seq: int, deadline: float, **extra) -> bytes:
        payload = encode_child_frame(kind, self.session, seq, **extra)
        self._write(payload, deadline)
        self.last_payload = payload
        return payload

    def send_raw(self, payload: bytes, deadline: float) -> None:
        self._write(payload, deadline)
        self.last_payload = payload


# --------------------------------------------------------------------------
# FIXED child modes
# --------------------------------------------------------------------------


def _start_lease(seconds: float) -> None:
    """Independent global safety lease so no external timeout can orphan us.

    SHORTCUT: experimental orphan protection, not production supervision.
    """

    def _expire() -> None:
        os._exit(EXIT_LEASE)

    timer = threading.Timer(seconds, _expire)
    timer.daemon = True
    timer.start()


def _child_read(sock, allowed, session, last_seq, mono_deadline, unix_bound):
    """Read one frame in a FIXED child. ``allowed`` must be parent->child kinds."""
    if not set(allowed) <= PARENT_TO_CHILD_KINDS:
        raise ProtocolViolation("kind_not_allowed")
    payload = read_frame(sock, mono_deadline)
    return decode_and_validate(
        payload,
        allowed,
        session,
        last_seq,
        deadline_bound=unix_bound,
        expected_root=None,
    )


def _child_send(sock, kind: str, session: str, seq: int, mono_deadline, **extra) -> None:
    write_frame(sock, encode_child_frame(kind, session, seq, **extra), mono_deadline)


def _perform_op(op_root: str, marker_name: str, session: str) -> None:
    """The one witnessed operation: exclusive marker + exactly one appended line."""
    _validate_root(op_root, None)
    if marker_name != MARKER_NAME:
        raise ProtocolViolation("marker_mismatch")
    path = os.path.join(op_root, marker_name)
    line = ("spike-op session=%s\n" % session).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        # O_EXCL makes a second op by one child structurally impossible.
        raise OpFailure("marker_exists")
    except OSError:
        raise OpFailure("open_failed")
    try:
        # Pin the mode explicitly so the 0o600 gate does not depend on umask.
        os.fchmod(fd, 0o600)
        os.write(fd, line)
        os.fsync(fd)
    except OSError:
        raise OpFailure("write_failed")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _child_flow(sock, mono_deadline: float, unix_bound: float) -> int:
    """READY -> ack_ready -> request_open -> grant_open -> request_create ->
    grant_create -> ONE witnessed op -> ack_create. Any validation failure
    exits without any op."""
    frame = _child_read(sock, WORKER_STAGE_READY, None, 0, mono_deadline, unix_bound)
    session = frame["session"]
    op_root = frame["op_root"]
    marker_name = frame["marker_name"]
    in_seq = frame["seq"]

    _child_send(sock, "ack_ready", session, 1, mono_deadline)
    _child_send(sock, "request_open", session, 2, mono_deadline)

    frame = _child_read(
        sock, WORKER_STAGE_OPEN, session, in_seq, mono_deadline, unix_bound
    )
    if frame["kind"] == "refusal":
        raise RefusedByParent(frame["reason"])
    in_seq = frame["seq"]

    _child_send(
        sock,
        "request_create",
        session,
        3,
        mono_deadline,
        deadline_unix=frame["deadline_unix"],
        metadata={"spike": "v189"},
    )

    frame = _child_read(
        sock, WORKER_STAGE_CREATE, session, in_seq, mono_deadline, unix_bound
    )
    if frame["kind"] == "refusal":
        raise RefusedByParent(frame["reason"])

    _perform_op(op_root, marker_name, session)
    _child_send(sock, "ack_create", session, 4, mono_deadline, marker=marker_name)
    return EXIT_OK


def _open_channel(fd_text: str):
    """Open the ONE inherited allowlisted endpoint. Absent endpoint -> exit 3.

    ``getsockname()`` proves the descriptor really is a live socket rather than
    an unrelated descriptor that happens to share the number, so an absent or
    wrong endpoint is always the fixed no-channel exit and never an ambiguous
    failure discovered later.
    """
    try:
        fd = int(fd_text)
    except (TypeError, ValueError):
        return None, EXIT_INTERNAL
    if fd < 0:
        return None, EXIT_NO_CHANNEL
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0, fd)
        sock.getsockname()
    except OSError:
        if sock is not None:
            _close_quiet(sock)
        return None, EXIT_NO_CHANNEL
    return sock, EXIT_OK


def _child_main(fd_text: str) -> int:
    mono_deadline = time.monotonic() + CHILD_LEASE_SECONDS
    unix_bound = time.time() + CHILD_LEASE_SECONDS
    _start_lease(CHILD_LEASE_SECONDS)
    sock, status = _open_channel(fd_text)
    if sock is None:
        return status
    try:
        return _child_flow(sock, mono_deadline, unix_bound)
    except ProtocolViolation:
        return EXIT_PROTOCOL
    except RefusedByParent:
        return EXIT_REFUSED
    except OpFailure:
        return EXIT_OP_FAILED
    except (ChannelClosed, WaitTimeout):
        return EXIT_AMBIGUOUS
    except (BrokenPipeError, ConnectionResetError, OSError):
        return EXIT_AMBIGUOUS
    except Exception:
        return EXIT_INTERNAL
    finally:
        _close_quiet(sock)


def _sentinel_main(fd_text: str) -> int:
    """FIXED sentinel stand-in: one ``arm`` frame in, one ``armed`` reply out.

    Never touches the filesystem. SHORTCUT: process-separated stand-in, not a
    production independent watchdog.
    """
    mono_deadline = time.monotonic() + CHILD_LEASE_SECONDS
    unix_bound = time.time() + CHILD_LEASE_SECONDS
    _start_lease(CHILD_LEASE_SECONDS)
    sock, status = _open_channel(fd_text)
    if sock is None:
        return status
    try:
        frame = _child_read(
            sock, SENTINEL_INBOUND_KINDS, None, 0, mono_deadline, unix_bound
        )
        _child_send(sock, "armed", frame["session"], 1, mono_deadline)
        return EXIT_OK
    except ProtocolViolation:
        return EXIT_PROTOCOL
    except (ChannelClosed, WaitTimeout):
        return EXIT_AMBIGUOUS
    except (BrokenPipeError, ConnectionResetError, OSError):
        return EXIT_AMBIGUOUS
    except Exception:
        return EXIT_INTERNAL
    finally:
        _close_quiet(sock)


# --------------------------------------------------------------------------
# Named numeric cases (every counter OBSERVED, never a hardcoded success)
# --------------------------------------------------------------------------


def _case1(ledger: NonceLedger, deadline: float):
    """absent inherited endpoint or replay payload to fresh invocation -> 0 ops."""
    res = Resources()
    sessions = []
    exit_absent = None
    exit_replay = None
    try:
        # 1a: absent inherited endpoint (pass_fds=()), fixed FD missing in child.
        root_absent = _mk_root(res, "v189-c1a-")
        parent_absent, child_absent = _mk_pair(res)
        popen_absent, _fd = _spawn_worker(res, child_absent, inherit=False)
        exit_absent = _reap(popen_absent, deadline)
        _close_quiet(parent_absent)

        # 1b source: scripted session S_A produces REAL captured wire bytes.
        root_src = _mk_root(res, "v189-c1src-")
        parent_src, child_src = _mk_pair(res)
        session_src = _new_session(ledger, parent_src, root_src, deadline)
        sessions.append(session_src)
        peer_src = ScriptedPeer(child_src, session_src.session)
        session_src.admit(deadline)
        peer_src.send("ack_ready", deadline)
        session_src.await_ack_ready(deadline)
        peer_src.send("request_open", deadline)
        request_open_bytes = peer_src.last_payload
        session_src.await_request_open(deadline)
        session_src.grant_open(deadline)
        grant_open_bytes = session_src.last_payload

        # 1b: FRESH real worker under session S_B receives the copied stale
        # grant instead of a live one -> child-side refusal, no op.
        root_replay = _mk_root(res, "v189-c1b-")
        parent_replay, child_replay = _mk_pair(res)
        session_replay = _new_session(ledger, parent_replay, root_replay, deadline)
        sessions.append(session_replay)
        popen_replay, _fd2 = _spawn_worker(res, child_replay, inherit=True)
        session_replay.send_raw(grant_open_bytes, deadline)
        exit_replay = _reap(popen_replay, deadline)

        # 1c: captured request_open(S_A) replayed into a fresh scripted session
        # S_C refuses parent-side.
        root_c = _mk_root(res, "v189-c1c-")
        parent_c, child_c = _mk_pair(res)
        session_c = _new_session(ledger, parent_c, root_c, deadline)
        sessions.append(session_c)
        peer_c = ScriptedPeer(child_c, session_c.session)
        session_c.admit(deadline)
        reason_c = None
        try:
            peer_c.send_raw(request_open_bytes, deadline)
            session_c.await_request_open(deadline)
        except RefusedFrame as exc:
            reason_c = exc.reason

        # Snapshot only after every worker was actually reaped.
        snaps = [_snapshot_root(root) for root in res.roots]
        totals = _aggregate(sessions)
        observed = {
            "ops": sum(snap["ops"] for snap in snaps),
            "exit_absent": exit_absent,
            "exit_replay": exit_replay,
            "grants_open_src": session_src.counters["grants_open"],
            "grants_open_b": session_replay.counters["grants_open"],
            "grants_open_c": session_c.counters["grants_open"],
            "refusals_c": session_c.counters["refusals"],
            "reason_c": reason_c,
            "retries": totals["retries"],
            "reissues": totals["reissues"],
            "lease_exits": res.lease_exits(),
        }
        gates = [
            ("ops_zero", observed["ops"] == 0),
            ("exit_absent_3", exit_absent == EXIT_NO_CHANNEL),
            ("exit_replay_6", exit_replay == EXIT_PROTOCOL),
            ("grants_open_src_1", observed["grants_open_src"] == 1),
            ("grants_open_b_0", observed["grants_open_b"] == 0),
            ("grants_open_c_0", observed["grants_open_c"] == 0),
            ("refusals_c_1", observed["refusals_c"] == 1),
            ("reason_c_session_mismatch", reason_c == "session_mismatch"),
            ("retries_0", observed["retries"] == 0),
            ("reissues_0", observed["reissues"] == 0),
            ("lease_exits_0", observed["lease_exits"] == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        observed_cleanup = {
            "cleanup_errors": len(res.errors),
            "retained_roots": len(res.retained_roots),
        }
        try:
            observed.update(observed_cleanup)
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case2(ledger: NonceLedger, deadline: float):
    """wrong session -> 0 ops (parent-side tags and a real child-side READY)."""
    res = Resources()
    sessions = []
    try:
        # 2a: scripted session S1; frames tagged with a different valid-shaped
        # session S2 refuse parent-side and never advance the ledger.
        root_a = _mk_root(res, "v189-c2a-")
        parent_a, child_a = _mk_pair(res)
        session_a = _new_session(ledger, parent_a, root_a, deadline)
        sessions.append(session_a)
        peer_a = ScriptedPeer(child_a, session_a.session)
        other_session = ledger.new_nonce()
        session_a.admit(deadline)
        peer_a.send("ack_ready", deadline)
        session_a.await_ack_ready(deadline)
        peer_a.send_raw(encode_child_frame("request_open", other_session, 2), deadline)
        try:
            session_a.await_request_open(deadline)
        except RefusedFrame:
            pass
        peer_a.send_raw(
            encode_child_frame("ack_create", other_session, 3, marker=MARKER_NAME),
            deadline,
        )
        try:
            session_a.await_ack_create(deadline)
        except RefusedFrame:
            pass
        last_seq_a = session_a.inbound_seq  # observed ledger position

        # 2b: real child established under READY(S_A); a second READY(S_B) frame
        # refuses child-side.
        root_b = _mk_root(res, "v189-c2b-")
        parent_b, child_b = _mk_pair(res)
        session_b = _new_session(ledger, parent_b, root_b, deadline)
        sessions.append(session_b)
        popen_b, _fd = _spawn_worker(res, child_b, inherit=True)
        session_b.admit(deadline)
        session_b.await_ack_ready(deadline)
        session_b.await_request_open(deadline)
        second_ready = encode_frame(
            {
                "v": PROTOCOL_VERSION,
                "kind": "ready",
                "session": ledger.new_nonce(),
                "seq": 2,
                "deadline_unix": session_b.cap_unix,
                "op_root": root_b,
                "marker_name": MARKER_NAME,
            }
        )
        session_b.send_raw(second_ready, deadline)
        exit_b = _reap(popen_b, deadline)

        snaps = [_snapshot_root(root) for root in res.roots]
        totals = _aggregate(sessions)
        observed = {
            "ops": sum(snap["ops"] for snap in snaps),
            "refusals_a": session_a.counters["refusals"],
            "reasons_a": "|".join(session_a.refusal_reasons),
            "last_seq_a": last_seq_a,
            "exit_b": exit_b,
            "grants_open": totals["grants_open"],
            "grants_create": totals["grants_create"],
            "retries": totals["retries"],
            "lease_exits": res.lease_exits(),
        }
        gates = [
            ("ops_zero", observed["ops"] == 0),
            ("refusals_a_2", observed["refusals_a"] == 2),
            (
                "reasons_a_session_mismatch",
                observed["reasons_a"] == "session_mismatch|session_mismatch",
            ),
            ("ledger_unadvanced", last_seq_a == 1),
            ("exit_b_6", exit_b == EXIT_PROTOCOL),
            ("grants_open_0", observed["grants_open"] == 0),
            ("grants_create_0", observed["grants_create"] == 0),
            ("retries_0", observed["retries"] == 0),
            ("lease_exits_0", observed["lease_exits"] == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case3(ledger: NonceLedger, deadline: float):
    """create before ARMED / missing or dead sentinel -> 0 ops."""
    res = Resources()
    sessions = []
    try:
        # 3a: scripted, sentinel never armed.
        root_a = _mk_root(res, "v189-c3a-")
        parent_a, child_a = _mk_pair(res)
        session_a = _new_session(ledger, parent_a, root_a, deadline)
        sessions.append(session_a)
        peer_a = ScriptedPeer(child_a, session_a.session)
        session_a.admit(deadline)
        peer_a.send("ack_ready", deadline)
        session_a.await_ack_ready(deadline)
        peer_a.send("request_open", deadline)
        session_a.await_request_open(deadline)
        session_a.grant_open(deadline)
        reason_a = None
        try:
            peer_a.send(
                "request_create",
                deadline,
                deadline_unix=session_a.cap_unix,
                metadata={},
            )
            session_a.await_request_create(deadline)
        except RefusedFrame as exc:
            reason_a = exc.reason

        # 3b: REAL sentinel terminated and reaped BEFORE any arm.
        root_b = _mk_root(res, "v189-c3b-")
        parent_b, child_b = _mk_pair(res)
        session_b = _new_session(ledger, parent_b, root_b, deadline)
        sessions.append(session_b)
        peer_b = ScriptedPeer(child_b, session_b.session)
        link_b = _new_sentinel_link(res, ledger)
        link_b.terminate_and_reap(deadline)
        _close_quiet(link_b.sock)
        session_b.admit(deadline)
        peer_b.send("ack_ready", deadline)
        session_b.await_ack_ready(deadline)
        peer_b.send("request_open", deadline)
        session_b.await_request_open(deadline)
        session_b.grant_open(deadline)
        reason_b_arm = None
        try:
            session_b.arm(link_b, deadline)
        except RefusedFrame as exc:
            reason_b_arm = exc.reason
        try:
            peer_b.send(
                "request_create",
                deadline,
                deadline_unix=session_b.cap_unix,
                metadata={},
            )
            session_b.await_request_create(deadline)
        except RefusedFrame:
            pass

        # 3c: absent sentinel.
        root_c = _mk_root(res, "v189-c3c-")
        parent_c, child_c = _mk_pair(res)
        session_c = _new_session(ledger, parent_c, root_c, deadline)
        sessions.append(session_c)
        peer_c = ScriptedPeer(child_c, session_c.session)
        session_c.admit(deadline)
        peer_c.send("ack_ready", deadline)
        session_c.await_ack_ready(deadline)
        peer_c.send("request_open", deadline)
        session_c.await_request_open(deadline)
        session_c.grant_open(deadline)
        reason_c_arm = None
        try:
            session_c.arm(None, deadline)
        except RefusedFrame as exc:
            reason_c_arm = exc.reason
        try:
            peer_c.send(
                "request_create",
                deadline,
                deadline_unix=session_c.cap_unix,
                metadata={},
            )
            session_c.await_request_create(deadline)
        except RefusedFrame:
            pass

        snaps = [_snapshot_root(root) for root in res.roots]
        totals = _aggregate(sessions)
        observed = {
            "ops": sum(snap["ops"] for snap in snaps),
            "grants_open": totals["grants_open"],
            "grants_create": totals["grants_create"],
            "armed_acks": totals["armed_acks"],
            "arm_failures": totals["arm_failures"],
            "refusals_total": totals["refusals"],
            "reasons": "|".join(
                session_a.refusal_reasons
                + session_b.refusal_reasons
                + session_c.refusal_reasons
            ),
            "retries": totals["retries"],
            "lease_exits": res.lease_exits(),
        }
        gates = [
            ("ops_zero", observed["ops"] == 0),
            ("grants_create_0", observed["grants_create"] == 0),
            ("armed_acks_0", observed["armed_acks"] == 0),
            ("arm_failures_2", observed["arm_failures"] == 2),
            ("refusals_total_5", observed["refusals_total"] == 5),
            (
                "reasons_exact",
                observed["reasons"]
                == "not_armed|sentinel_dead|not_armed|sentinel_absent|not_armed",
            ),
            ("reason_a_not_armed", reason_a == "not_armed"),
            ("reason_b_sentinel_dead", reason_b_arm == "sentinel_dead"),
            ("reason_c_sentinel_absent", reason_c_arm == "sentinel_absent"),
            ("retries_0", observed["retries"] == 0),
            ("lease_exits_0", observed["lease_exits"] == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case4(ledger: NonceLedger, deadline: float):
    """valid READY/open/ARMED/create -> exactly 1 observed op."""
    res = Resources()
    sessions = []
    started = time.monotonic()
    try:
        root = _mk_root(res, "v189-c4-")
        parent_worker, child_worker = _mk_pair(res)
        session = _new_session(ledger, parent_worker, root, deadline)
        sessions.append(session)
        popen_worker, _fd_w = _spawn_worker(res, child_worker, inherit=True)
        link = _new_sentinel_link(res, ledger)

        session.admit(deadline)
        session.await_ack_ready(deadline)
        session.await_request_open(deadline)
        session.grant_open(deadline)
        session.arm(link, deadline)
        sentinel_exit = link.reap(deadline)
        _close_quiet(link.sock)
        frame = session.await_request_create(deadline)
        session.grant_create(frame, deadline)
        session.await_ack_create(deadline)
        worker_exit = _reap(popen_worker, deadline)

        snap = _snapshot_root(root)
        elapsed = time.monotonic() - started
        totals = _aggregate(sessions)
        observed = {
            "ops": snap["ops"],
            "marker_mode": oct(snap["mode"]) if snap["mode"] >= 0 else snap["mode"],
            "marker_lines": snap["lines"],
            "worker_exit": worker_exit,
            "sentinel_exit": sentinel_exit,
            "grants_open": totals["grants_open"],
            "grants_create": totals["grants_create"],
            "armed_acks": totals["armed_acks"],
            "refusals": totals["refusals"],
            "acks_create": totals["acks_create"],
            "retries": totals["retries"],
            "reissues": totals["reissues"],
            "lease_exits": res.lease_exits(),
            "elapsed_s": round(elapsed, 3),
        }
        gates = [
            ("ops_1", snap["ops"] == 1),
            ("marker_mode_0600", snap["mode"] == 0o600),
            ("marker_lines_1", snap["lines"] == 1),
            ("worker_exit_0", worker_exit == EXIT_OK),
            ("sentinel_exit_0", sentinel_exit == EXIT_OK),
            ("grants_open_1", totals["grants_open"] == 1),
            ("grants_create_1", totals["grants_create"] == 1),
            ("armed_acks_1", totals["armed_acks"] == 1),
            ("refusals_0", totals["refusals"] == 0),
            ("acks_create_1", totals["acks_create"] == 1),
            ("retries_0", totals["retries"] == 0),
            ("reissues_0", totals["reissues"] == 0),
            ("lease_exits_0", res.lease_exits() == 0),
            ("elapsed_le_2s", elapsed <= 2.00),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case5(ledger: NonceLedger, deadline: float):
    """duplicate/reordered seq after admission -> 0 additional ops."""
    res = Resources()
    sessions = []
    try:
        root = _mk_root(res, "v189-c5-")
        parent_end, child_end = _mk_pair(res)
        session = _new_session(ledger, parent_end, root, deadline)
        sessions.append(session)
        peer = ScriptedPeer(child_end, session.session)
        session.admit(deadline)
        peer.send("ack_ready", deadline)
        session.await_ack_ready(deadline)
        peer.send("request_open", deadline)
        session.await_request_open(deadline)
        session.grant_open(deadline)

        oversized = "a" * (MAX_METADATA_BYTES + 1)
        injections = [
            # 1. duplicate seq 2
            encode_child_frame("request_open", session.session, 2),
            # 2. reordered seq 1
            encode_child_frame("ack_ready", session.session, 1),
            # 3. request_create(seq 3) with 8193-B metadata
            encode_child_frame(
                "request_create",
                session.session,
                3,
                deadline_unix=session.cap_unix,
                metadata={"blob": oversized},
            ),
            # 4. raw payload with a duplicate "seq" key
            (
                b'{"v":1,"kind":"request_open","session":"'
                + session.session.encode("ascii")
                + b'","seq":3,"seq":4}'
            ),
            # 5. raw payload with a NaN deadline
            (
                b'{"v":1,"kind":"request_create","session":"'
                + session.session.encode("ascii")
                + b'","seq":3,"deadline_unix":NaN,"metadata":{}}'
            ),
            # 6. bool-as-int seq
            (
                b'{"v":1,"kind":"request_open","session":"'
                + session.session.encode("ascii")
                + b'","seq":true}'
            ),
            # 7. ack_ready with an extra field
            (
                b'{"v":1,"kind":"ack_ready","session":"'
                + session.session.encode("ascii")
                + b'","seq":3,"extra":"x"}'
            ),
        ]
        reasons = []
        for payload in injections:
            peer.send_raw(payload, deadline)
            try:
                session.probe_inbound(deadline)
                reasons.append("accepted")
            except RefusedFrame as exc:
                reasons.append(exc.reason)
            except AmbiguousDispatch:
                reasons.append("ambiguous")

        snaps = [_snapshot_root(root)]
        totals = _aggregate(sessions)
        observed = {
            "ops": sum(snap["ops"] for snap in snaps),
            "grants_open": totals["grants_open"],
            "grants_create": totals["grants_create"],
            "refusals": totals["refusals"],
            "reasons": "|".join(reasons),
            "last_seq": session.inbound_seq,  # observed ledger position
            "retries": totals["retries"],
        }
        expected_reasons = (
            "seq_not_monotonic|seq_not_monotonic|metadata_oversize|duplicate_keys"
            "|nonfinite|seq_not_monotonic|extra_fields"
        )
        gates = [
            ("ops_zero", observed["ops"] == 0),
            ("grants_open_1", totals["grants_open"] == 1),
            ("grants_create_0", totals["grants_create"] == 0),
            ("refusals_7", totals["refusals"] == 7),
            ("reasons_exact", observed["reasons"] == expected_reasons),
            ("ledger_still_2", observed["last_seq"] == 2),
            ("retries_0", totals["retries"] == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case6(ledger: NonceLedger, deadline: float):
    """second admission / rearm / extended deadline -> 0 additional ops."""
    res = Resources()
    sessions = []
    nonce_replay_refusals = 0
    try:
        root = _mk_root(res, "v189-c6-")
        parent_end, child_end = _mk_pair(res)
        session = _new_session(ledger, parent_end, root, deadline)
        sessions.append(session)
        peer = ScriptedPeer(child_end, session.session)
        link = _new_sentinel_link(res, ledger)

        session.admit(deadline)
        peer.send("ack_ready", deadline)
        session.await_ack_ready(deadline)
        peer.send("request_open", deadline)
        session.await_request_open(deadline)
        session.grant_open(deadline)
        session.arm(link, deadline)
        sentinel_exit = link.reap(deadline)
        _close_quiet(link.sock)

        # Extended deadline refuses; the cap can never be extended by a frame.
        reason_deadline = None
        try:
            peer.send(
                "request_create",
                deadline,
                deadline_unix=session.cap_unix + 60.0,
                metadata={},
            )
            session.await_request_create(deadline)
        except RefusedFrame as exc:
            reason_deadline = exc.reason

        # Second admission refuses and sends NO frame.
        out_seq_before = session.outbound_seq  # observed frame counter
        reason_admission = None
        try:
            session.admit(deadline)
        except RefusedFrame as exc:
            reason_admission = exc.reason
        frames_sent_by_second_admit = session.outbound_seq - out_seq_before

        # Rearm refuses.
        reason_rearm = None
        try:
            session.arm(link, deadline)
        except RefusedFrame as exc:
            reason_rearm = exc.reason

        # Reusing the consumed nonce in the run-wide ledger refuses.
        reason_nonce = None
        try:
            ledger.register(session.session)
        except NonceReplay as exc:
            nonce_replay_refusals += 1
            reason_nonce = str(exc)

        snaps = [_snapshot_root(root)]
        totals = _aggregate(sessions)
        observed = {
            "ops": sum(snap["ops"] for snap in snaps),
            "admissions": totals["admissions"],
            "grants_open": totals["grants_open"],
            "grants_create": totals["grants_create"],
            "armed_acks": totals["armed_acks"],
            "arm_failures": totals["arm_failures"],
            "refusals": totals["refusals"],
            "reasons": "|".join(session.refusal_reasons),
            "nonce_replay_refusals": nonce_replay_refusals,
            "sentinel_exit": sentinel_exit,
            "retries": totals["retries"],
        }
        gates = [
            ("ops_zero", observed["ops"] == 0),
            ("admissions_1", totals["admissions"] == 1),
            ("grants_open_1", totals["grants_open"] == 1),
            ("grants_create_0", totals["grants_create"] == 0),
            ("armed_acks_1", totals["armed_acks"] == 1),
            ("refusals_3", totals["refusals"] == 3),
            (
                "reasons_exact",
                observed["reasons"]
                == "deadline_extension|second_admission|rearm_refused",
            ),
            ("reason_deadline_extension", reason_deadline == "deadline_extension"),
            ("reason_second_admission", reason_admission == "second_admission"),
            ("reason_rearm_refused", reason_rearm == "rearm_refused"),
            ("second_admit_sent_no_frame", frames_sent_by_second_admit == 0),
            ("nonce_replay_refusals_1", nonce_replay_refusals == 1),
            ("reason_nonce_replay", reason_nonce == "nonce_replay"),
            ("sentinel_exit_0", sentinel_exit == EXIT_OK),
            ("retries_0", totals["retries"] == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


def _case7(ledger: NonceLedger, deadline: float):
    """disconnect after consumed permit but before reply -> at most 1 op."""
    res = Resources()
    sessions = []
    try:
        # 7a: REAL worker + REAL sentinel; grant_create sent, then the session
        # is consumed BEFORE the socket closes, without reading the reply.
        root_a = _mk_root(res, "v189-c7a-")
        parent_a, child_a = _mk_pair(res)
        session_a = _new_session(ledger, parent_a, root_a, deadline)
        sessions.append(session_a)
        popen_a, _fd_a = _spawn_worker(res, child_a, inherit=True)
        link_a = _new_sentinel_link(res, ledger)
        session_a.admit(deadline)
        session_a.await_ack_ready(deadline)
        session_a.await_request_open(deadline)
        session_a.grant_open(deadline)
        session_a.arm(link_a, deadline)
        sentinel_exit_a = link_a.reap(deadline)
        _close_quiet(link_a.sock)
        frame_a = session_a.await_request_create(deadline)
        session_a.grant_create(frame_a, deadline)
        session_a.close_ambiguous()  # consumed FIRST, then closed; no reply read
        exit_a = _reap(popen_a, deadline)

        # 7b: scripted silent child + CONTROLLED sentinel channel (SHORTCUT:
        # harness-held peer end with a pre-scripted armed reply).
        root_b = _mk_root(res, "v189-c7b-")
        parent_b, child_b = _mk_pair(res)
        session_b = _new_session(ledger, parent_b, root_b, deadline)
        sessions.append(session_b)
        peer_b = ScriptedPeer(child_b, session_b.session)
        link_b = _new_controlled_sentinel_link(res, ledger, deadline)
        session_b.admit(deadline)
        peer_b.send("ack_ready", deadline)
        session_b.await_ack_ready(deadline)
        peer_b.send("request_open", deadline)
        session_b.await_request_open(deadline)
        session_b.grant_open(deadline)
        session_b.arm(link_b, deadline)
        peer_b.send(
            "request_create", deadline, deadline_unix=session_b.cap_unix, metadata={}
        )
        frame_b = session_b.await_request_create(deadline)
        session_b.grant_create(frame_b, deadline)
        ambiguous_b = 0
        ack_wait = time.monotonic() + min(
            CASE7B_ACK_WAIT_SECONDS, _remaining(deadline)
        )
        try:
            session_b.await_ack_create(ack_wait)
        except AmbiguousDispatch:
            ambiguous_b = 1
        except RefusedFrame:
            ambiguous_b = 0

        snap_a = _snapshot_root(root_a)
        snap_b = _snapshot_root(root_b)
        totals = _aggregate(sessions)
        observed = {
            "ops_a": snap_a["ops"],
            "lines_a": snap_a["lines"],
            "ops_b": snap_b["ops"],
            "exit_a": exit_a,
            "sentinel_exit_a": sentinel_exit_a,
            "state_a": session_a.state,
            "state_b": session_b.state,
            "ambiguous_b": ambiguous_b,
            "grants_create_total": totals["grants_create"],
            "second_grants": _second_grants(sessions),
            "retries": totals["retries"],
            "reissues": totals["reissues"],
            "lease_exits": res.lease_exits(),
        }
        gates = [
            ("ops_a_le_1", snap_a["ops"] <= 1),
            ("lines_a_1_when_ops_a_1", snap_a["ops"] != 1 or snap_a["lines"] == 1),
            ("ops_b_0", snap_b["ops"] == 0),
            ("exit_a_in_0_4", exit_a in (EXIT_OK, EXIT_AMBIGUOUS)),
            ("state_a_consumed", session_a.state == STATE_CONSUMED),
            ("state_b_consumed", session_b.state == STATE_CONSUMED),
            ("ambiguous_b_1", ambiguous_b == 1),
            ("grants_create_total_2", totals["grants_create"] == 2),
            ("second_grants_0", _second_grants(sessions) == 0),
            ("retries_0", totals["retries"] == 0),
            ("reissues_0", totals["reissues"] == 0),
            ("lease_exits_0", res.lease_exits() == 0),
        ]
        return observed, gates
    finally:
        res.cleanup(deadline)
        try:
            observed.update(
                {
                    "cleanup_errors": len(res.errors),
                    "retained_roots": len(res.retained_roots),
                }
            )
            gates.extend(
                [
                    ("cleanup_errors_0", len(res.errors) == 0),
                    ("retained_roots_0", len(res.retained_roots) == 0),
                ]
            )
        except NameError:
            pass


CASES = (
    ("case1_absent_endpoint_or_replay_zero_ops", 1.00, _case1),
    ("case2_wrong_session_zero_ops", 0.50, _case2),
    ("case3_create_before_armed_or_dead_sentinel_zero_ops", 1.25, _case3),
    ("case4_valid_ready_open_armed_create_one_op", 2.00, _case4),
    ("case5_duplicate_reordered_seq_zero_additional_ops", 0.50, _case5),
    (
        "case6_second_admission_rearm_extended_deadline_zero_additional_ops",
        0.75,
        _case6,
    ),
    ("case7_disconnect_after_consumed_permit_at_most_one_op", 1.75, _case7),
)


# --------------------------------------------------------------------------
# Harness mode
# --------------------------------------------------------------------------


def _format_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)


def _run_harness() -> int:
    started = time.monotonic()
    ledger = NonceLedger()
    all_pass = True
    for index, (name, budget, fn) in enumerate(CASES, start=1):
        case_deadline = time.monotonic() + budget
        try:
            observed, gates = fn(ledger, case_deadline)
        except Exception as exc:  # containment errors are NONPASS, never a pass
            observed = {"internal_error": type(exc).__name__, "detail": str(exc)[:120]}
            gates = [("internal_error", False)]
        failed = [gate_name for gate_name, ok in gates if not ok]
        ok = not failed
        all_pass = all_pass and ok
        fields = " ".join(
            "%s=%s" % (key, _format_value(observed[key])) for key in sorted(observed)
        )
        line = "CASE %d %s %s %s" % (index, name, fields, "PASS" if ok else "FAIL")
        if failed:
            line += " failed_gates=%s" % ",".join(failed)
        print(line, flush=True)
    elapsed = time.monotonic() - started
    timing_ok = elapsed < TOTAL_GATE_SECONDS
    print(
        "TOTAL elapsed_s=%.3f gate_s=%.2f %s"
        % (elapsed, TOTAL_GATE_SECONDS, "PASS" if timing_ok else "FAIL"),
        flush=True,
    )
    result_ok = all_pass and timing_ok
    print("RESULT %s" % ("PASS" if result_ok else "FAIL"), flush=True)
    return EXIT_OK if result_ok else EXIT_GATE_FAIL


def main(argv) -> int:
    if len(argv) == 3 and argv[1] == "--spike-child":
        return _child_main(argv[2])
    if len(argv) == 3 and argv[1] == "--spike-sentinel":
        return _sentinel_main(argv[2])
    if len(argv) == 1:
        try:
            return _run_harness()
        except Exception:
            return EXIT_INTERNAL
    return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
