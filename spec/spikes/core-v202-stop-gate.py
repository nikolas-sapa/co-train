#!/usr/bin/env python3
"""V202 direct-child stop-gate topology spike (standalone, stdlib only).

SOURCE-ONLY DELIVERY. The authoring worker executed nothing: no import of this
module, no run, no spawn, no exec, no signal, no test. Every subprocess, execve
and socket operation below exists only as source. The parent reviews, then owns
execution and every real spawn/exec/signal decision.

Run (parent-owned): ``python3 spec/spikes/core-v202-stop-gate.py``

Technical unknown
    A deadline controller that launches a new-session stop GRANDCHILD cannot
    guarantee parent custody if the controller dies: the grandchild is
    reparented and the parent holds no handle for it. This spike probes a
    parent-owned PRESTARTED GATE that ``os.execve()``s a FIXED harmless command
    in the SAME PID, so the parent's original ``Popen`` handle keeps working
    across the transition.

Fixed modes (dispatched on ``sys.argv[1]``; any other shape returns exit 2)
    (no extra argv)       harness: runs C1..C3, prints one numeric line per
                          case, a TOTAL gate line and RESULT. Exit 0 only when
                          every gate passes, 1 on any gate failure, 2 on
                          internal error.
    --spike-worker        tiny worker. Ignores SIGTERM, retains an active
                          thread, answers challenges. Never exits on its own
                          inside a case budget.
    --spike-controller    independent controller. Answers challenges; on one
                          ``fire`` frame sends exactly one ``trigger`` to the
                          gate, then exits 0.
    --spike-gate          prestarted gate. Answers challenges; on ``trigger``
                          OR genuine EOF on the controller channel, execs the
                          fixed command in the SAME PID.
    --spike-command       the FIXED harmless command that replaced the gate.
                          Writes exactly one exclusive 0600 marker holding its
                          own ACTUAL pid and the case nonce, reports
                          ``started``, then exits 0 (normal) or ignores SIGTERM
                          and keeps answering challenges (resistant).

Hard limits honoured in source
    No SDK, no App, no Sandbox, no GPU, no network, no provider, no
    credentials, no installed-distribution enumeration. No shell, no
    caller-supplied command, no ``eval``, no Python ``exec()``, no ``os.fork``,
    no ``preexec_fn``, no pickling, no ``multiprocessing``, no TCP, no
    bind/listen, no service. Exactly ONE ``os.execve`` call site (the gate) and
    exactly ONE ``subprocess.Popen`` call site (harness-side fixture
    construction); the command mode contains neither, so the command cannot
    launch a local subprocess or session. The protocol carries no process-group
    field and no frame-reported pid is ever a signal target: signals travel
    only through retained unreaped ``Popen`` handles, poll-checked first, never
    after reap.

PROVES (planned only; nothing here is measured until the parent runs it)
    * P1 the parent's ORIGINAL gate ``Popen`` handle stays valid across
      ``os.execve``: the command's actual pid equals ``popen_gate.pid``, the
      parent reaps it through that same handle, and ``popen_calls`` stays 3.
    * P2 genuine controller EOF (every writer copy of the controller-to-gate
      channel closed, the parent holding NONE) reaches the gate and causes
      exactly one exec and exactly one marker, with no replacement controller,
      gate or command.
    * P3 custody survives controller death AFTER the exec: the resistant
      command answers a fresh challenge, ignores SIGTERM, and is terminated
      then killed and reaped by the parent through the retained handle.
    * P4 exec preserves the descriptor and the session, so one parent-held
      socket serves ``stage=gate`` before and ``stage=command`` after, with
      strictly monotonic sequence counters handed over explicitly in argv.

SHORTCUT (probe-only, NOT production)
    * The "stop command" is a harmless marker writer, not a real Modal stop,
      App stop or Sandbox termination. Nothing remote happens.
    * Worker/controller/gate/command are fixed trusted first-party source in
      this one file. This is NOT hostile-same-user security and NOT
      arbitrary-code containment: the exec target argv[0..4] are constants.
    * Same-user socketpair channels are a local delegation concept between a
      parent and its own freshly exec'd children. No sealed authority, no
      authorization serialization, no billing, no owner API.
    * The 8 s shared lease plus the declared 10 s external parent timeout are
      experimental orphan protection, not production supervision.
    * The witness root is ``tempfile.mkdtemp`` inside a parent-created 0700
      base, not a purpose-built isolation boundary.
    * One fixture at a time; no multi-fixture concurrency or contention probe.

MISSING (gaps the parent must weigh before freezing production interfaces)
    * Everything is UNRUN. Every counter, exit code and latency is planned.
    * Interpreter startup cost is unmeasured: nine spawns plus three execs must
      fit the 2.50 s per-case and 8.00 s total budgets. Exceeding them is a
      FAIL, never a silent pass.
    * Cross-process monotonic clock sharing is ASSUMED. Every mode also carries
      a wall-clock expiry and uses the MINIMUM of the two remaining budgets, so
      a monotonic reference mismatch or a wall-clock jump can only shorten a
      budget, never lengthen it. Neither clock behaviour is verified here.
    * OS unresponsiveness, execve failure, descriptor exhaustion and SIGKILL
      latency under load are not modelled beyond the fixed gates. An execve
      failure returns exit 2 and the case fails; there is no fallback spawn.
    * No coverage for a kill between ``O_EXCL`` and the append beyond the
      ``markers==1`` gate; no clock-skew coverage; no case exercises a
      malformed trigger (the gate would return 5, which is the intended
      NONPASS).
    * No SDK, GPU, App, Sandbox, remote stop, science or provider evidence.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

# --------------------------------------------------------------------------
# Fixed constants. No cap may be increased, no wait retried, no process
# replaced, no permit reissued.
# --------------------------------------------------------------------------

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 4096
SELECT_SLICE_SECONDS = 0.10
MIN_WAIT_SECONDS = 0.02
TEARDOWN_RESERVE_SECONDS = 0.25
LOCAL_OP_SECONDS = 2.00
CHALLENGE_SECONDS = 0.50
STOP_SECONDS = 1.00
TERM_PROBE_SECONDS = 0.15
POST_KILL_WAIT_SECONDS = 0.20
CASE_BUDGET_SECONDS = 2.50
HARNESS_EXPIRY_SECONDS = 8.0
TOTAL_GATE_SECONDS = 8.0
NONCE_CHARS = 8  # secrets.token_hex(8) -> 16 hex chars

SCRIPT = os.path.abspath(__file__)
MARKER_NAME = "v202-stop.marker"
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

EXIT_OK = 0
EXIT_GATE_FAIL = 1
EXIT_INTERNAL = 2
EXIT_NO_CHANNEL = 3
EXIT_PROTOCOL = 4
EXIT_TRIGGER_INVALID = 5
EXIT_DEADLINE = 6
EXIT_LEASE = 97

NONCE_RE = re.compile(r"[0-9a-f]{16}")

STAGES = frozenset({"worker", "controller", "gate", "command"})
VIAS = frozenset({"trigger", "eof"})

# Exact bounded schemas: an extra or a missing field is a protocol violation.
SCHEMAS = {
    "challenge": frozenset({"v", "kind", "nonce", "seq"}),
    "fire": frozenset({"v", "kind", "nonce", "seq"}),
    "alive": frozenset({"v", "kind", "nonce", "seq", "pid", "stage"}),
    "trigger": frozenset({"v", "kind", "nonce", "seq"}),
    "started": frozenset(
        {"v", "kind", "nonce", "seq", "pid", "stage", "via", "marker"}
    ),
}

PARENT_TO_CHILD_KINDS = frozenset({"challenge", "fire"})
CHILD_TO_PARENT_KINDS = frozenset({"alive", "started"})
# The trigger travels controller -> gate, so it belongs to neither directed
# set above; the send allowlist is the union of all three.
CHILD_TO_CHILD_KINDS = frozenset({"trigger"})
SENDABLE_KINDS = (
    PARENT_TO_CHILD_KINDS | CHILD_TO_PARENT_KINDS | CHILD_TO_CHILD_KINDS
)
WORKER_INBOUND_KINDS = frozenset({"challenge"})
CONTROLLER_INBOUND_KINDS = frozenset({"challenge", "fire"})
GATE_INBOUND_KINDS = frozenset({"challenge"})
GATE_TRIGGER_KINDS = frozenset({"trigger"})
COMMAND_INBOUND_KINDS = frozenset({"challenge"})


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------


class SpikeError(Exception):
    """Base class for spike-local errors."""


class ProtocolError(SpikeError):
    """A frame failed strict validation. Carries the fixed reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ChannelClosed(SpikeError):
    """Peer closed the channel (EOF) or the connection was reset."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class WaitTimeout(SpikeError):
    """The shared absolute deadline expired before the frame arrived."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OpFailure(SpikeError):
    """The single witnessed operation could not be completed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------
# Shared expiry helpers. The expiry is IMMUTABLE and handed to every mode,
# including the exec target. No mode may reset it to now + 8.
# --------------------------------------------------------------------------


def _budget(expiry_mono: float, expiry_wall: float) -> float:
    """Remaining shared budget: the MINIMUM of both clocks.

    Taking the minimum can only shorten a budget, never lengthen it, so a
    monotonic reference mismatch or a wall-clock jump is fail-safe.
    """
    return min(expiry_mono - time.monotonic(), expiry_wall - time.time())


def _fmt_num(value: float) -> str:
    return repr(float(value))


def _lease_expire() -> None:
    os._exit(EXIT_LEASE)


def _install_lease(seconds: float) -> None:
    """Arm the toy safety lease BEFORE any channel I/O.

    SHORTCUT: experimental orphan protection, not production supervision. A
    non-positive remaining budget exits 97 immediately instead of doing I/O.
    """
    if seconds <= 0:
        os._exit(EXIT_LEASE)
    timer = threading.Timer(seconds, _lease_expire)
    timer.daemon = True
    timer.start()


def _start_keepalive() -> threading.Event:
    """Retain a genuinely active thread so SIGTERM resistance is observable."""
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(0.05):
            continue

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return stop


def _ignore_sigterm() -> None:
    try:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    except (OSError, ValueError):
        pass


def _remaining(deadline: float) -> float:
    """Wait budget under the common deadline minus the teardown reserve."""
    left = deadline - time.monotonic() - TEARDOWN_RESERVE_SECONDS
    return left if left > MIN_WAIT_SECONDS else MIN_WAIT_SECONDS


# --------------------------------------------------------------------------
# Nonblocking bounded channel I/O. No blocking send after select, no writer
# threads anywhere in this file.
# --------------------------------------------------------------------------


class _End:
    """One nonblocking channel end backed by a socket object."""

    def __init__(self, sock) -> None:
        self.sock = sock
        self.closed = False
        try:
            sock.setblocking(False)
        except OSError:
            pass

    def fileno(self) -> int:
        return self.sock.fileno()

    def recv(self, count: int) -> bytes:
        return self.sock.recv(count)

    def send(self, blob: bytes) -> int:
        return self.sock.send(blob)

    def detach(self) -> int:
        """Return the descriptor WITHOUT closing it (used only before execve)."""
        return self.sock.detach()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


def _open_end(fd_text: str):
    """Wrap one inherited allowlisted descriptor. Absent endpoint -> None.

    ``getsockname()`` proves the descriptor really is a live socket rather than
    an unrelated descriptor sharing the number, so an absent or wrong endpoint
    is always the fixed no-channel exit and never a later ambiguous failure.
    """
    try:
        fd = int(fd_text)
    except (TypeError, ValueError):
        return None
    if fd < 0:
        return None
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0, fd)
        sock.getsockname()
    except OSError:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        return None
    return _End(sock)


def encode_frame(frame: dict) -> bytes:
    payload = json.dumps(frame, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("frame_size")
    return payload


def _recv_exact(end: _End, count: int, deadline: float) -> bytes:
    buf = bytearray()
    while len(buf) < count:
        left = deadline - time.monotonic()
        if left <= 0:
            raise WaitTimeout("read_deadline")
        ready = select.select([end], [], [], min(left, SELECT_SLICE_SECONDS))
        if not ready[0]:
            continue
        try:
            chunk = end.recv(count - len(buf))
        except BlockingIOError:
            continue
        except (ConnectionResetError, BrokenPipeError) as exc:
            raise ChannelClosed(type(exc).__name__)
        except OSError as exc:
            raise ChannelClosed(type(exc).__name__)
        if not chunk:
            raise ChannelClosed("eof")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(end: _End, deadline: float) -> bytes:
    header = _recv_exact(end, 4, deadline)
    length = int.from_bytes(header, "big")
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise ProtocolError("frame_size")
    return _recv_exact(end, length, deadline)


def write_frame(end: _End, payload: bytes, deadline: float) -> None:
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("frame_size")
    buf = len(payload).to_bytes(4, "big") + payload
    sent = 0
    while sent < len(buf):
        left = deadline - time.monotonic()
        if left <= 0:
            raise WaitTimeout("write_deadline")
        ready = select.select([], [end], [], min(left, SELECT_SLICE_SECONDS))
        if not ready[1]:
            continue
        try:
            count = end.send(buf[sent:])
        except BlockingIOError:
            continue
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise ChannelClosed(type(exc).__name__)
        if count == 0:
            raise ChannelClosed("send_zero")
        sent += count


# --------------------------------------------------------------------------
# Strict validation (both ends, fixed rules)
# --------------------------------------------------------------------------


def decode_frame(payload: bytes, allowed_kinds, expected_nonce, last_seq: int) -> dict:
    """Strictly decode one frame. Raises ProtocolError with a fixed reason."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("malformed_json")

    def pairs_hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ProtocolError("duplicate_keys")
            out[key] = value
        return out

    def const_hook(_name):
        raise ProtocolError("nonfinite")

    try:
        frame = json.loads(
            text, object_pairs_hook=pairs_hook, parse_constant=const_hook
        )
    except ProtocolError:
        raise
    except ValueError:
        raise ProtocolError("malformed_json")

    if not isinstance(frame, dict):
        raise ProtocolError("not_object")

    kind = frame.get("kind")
    if not isinstance(kind, str) or kind not in allowed_kinds or kind not in SCHEMAS:
        raise ProtocolError("kind_not_allowed")

    expected_fields = SCHEMAS[kind]
    actual_fields = set(frame.keys())
    if actual_fields - expected_fields:
        raise ProtocolError("extra_fields")
    if expected_fields - actual_fields:
        raise ProtocolError("missing_fields")

    if type(frame["v"]) is not int or frame["v"] != PROTOCOL_VERSION:
        raise ProtocolError("version_mismatch")

    nonce = frame["nonce"]
    if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
        raise ProtocolError("nonce_shape")
    if expected_nonce is not None and nonce != expected_nonce:
        raise ProtocolError("nonce_mismatch")

    seq = frame["seq"]
    if type(seq) is not int or seq < 1 or seq <= last_seq:
        raise ProtocolError("seq_not_monotonic")

    if "pid" in expected_fields:
        # Witness only. Never a signal target: the parent signals exclusively
        # through its retained Popen handle.
        pid = frame["pid"]
        if type(pid) is not int or pid <= 0:
            raise ProtocolError("pid_shape")
    if "stage" in expected_fields and frame["stage"] not in STAGES:
        raise ProtocolError("stage_shape")
    if "via" in expected_fields and frame["via"] not in VIAS:
        raise ProtocolError("via_shape")
    if "marker" in expected_fields and frame["marker"] != MARKER_NAME:
        raise ProtocolError("marker_mismatch")

    return frame


class _Link:
    """Per-direction strictly monotonic sequence state for one channel."""

    def __init__(self, end: _End, nonce: str, out_seq: int = 0, in_seq: int = 0) -> None:
        self.end = end
        self.nonce = nonce
        self.out_seq = out_seq
        self.in_seq = in_seq

    def send(self, kind: str, deadline: float, **extra) -> None:
        if kind not in SENDABLE_KINDS:
            raise ProtocolError("kind_not_allowed")
        self.out_seq += 1
        frame = {
            "v": PROTOCOL_VERSION,
            "kind": kind,
            "nonce": self.nonce,
            "seq": self.out_seq,
        }
        frame.update(extra)
        write_frame(self.end, encode_frame(frame), deadline)

    def read(self, allowed_kinds, deadline: float) -> dict:
        payload = read_frame(self.end, deadline)
        frame = decode_frame(payload, allowed_kinds, self.nonce, self.in_seq)
        self.in_seq = frame["seq"]
        return frame


# --------------------------------------------------------------------------
# The one witnessed operation
# --------------------------------------------------------------------------


def _validate_root(root: str) -> None:
    if not isinstance(root, str) or not root:
        raise ProtocolError("root_shape")
    if not os.path.isabs(root):
        raise ProtocolError("root_shape")
    if ".." in root.split("/"):
        raise ProtocolError("root_traversal")
    if os.path.normpath(root) != root:
        raise ProtocolError("root_traversal")


def _write_marker(root: str, nonce: str, via: str) -> str:
    """Exactly one exclusive 0600 marker holding this process' ACTUAL pid."""
    _validate_root(root)
    if via not in VIAS:
        raise ProtocolError("via_shape")
    path = os.path.join(root, MARKER_NAME)
    line = "pid=%d nonce=%s via=%s stage=command\n" % (os.getpid(), nonce, via)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        # O_EXCL makes a second marker by one command structurally impossible.
        raise OpFailure("marker_exists")
    except OSError:
        raise OpFailure("open_failed")
    try:
        # Pin the mode explicitly so the 0600 gate never depends on umask.
        os.fchmod(fd, 0o600)
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    except OSError:
        raise OpFailure("write_failed")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    return MARKER_NAME


def _as_int(text) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return -1


def _snapshot_root(root: str) -> dict:
    """Observed marker facts. Taken only AFTER every relevant child was reaped."""
    snap = {
        "count": -1,
        "mode": -1,
        "lines": -1,
        "pid": -1,
        "nonce": "",
        "via": "",
    }
    try:
        names = os.listdir(root)
    except OSError:
        return snap
    snap["count"] = len(names)
    if MARKER_NAME not in names:
        return snap
    path = os.path.join(root, MARKER_NAME)
    try:
        snap["mode"] = os.lstat(path).st_mode & 0o777
    except OSError:
        pass
    fd = None
    data = b""
    try:
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            data += chunk
    except OSError:
        return snap
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    lines = [line for line in data.decode("utf-8", "replace").split("\n") if line]
    snap["lines"] = len(lines)
    if len(lines) != 1:
        return snap
    for part in lines[0].split(" "):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        if key == "pid":
            snap["pid"] = _as_int(value)
        elif key in ("nonce", "via"):
            snap[key] = value
    return snap


# --------------------------------------------------------------------------
# FIXED child modes
# --------------------------------------------------------------------------


def _worker_main(fd_text: str, expiry_mono: float, expiry_wall: float, nonce: str) -> int:
    """Tiny worker: ignores SIGTERM, retains an active thread, answers only."""
    _install_lease(_budget(expiry_mono, expiry_wall))
    end = _open_end(fd_text)
    if end is None:
        return EXIT_NO_CHANNEL
    _ignore_sigterm()
    _start_keepalive()
    link = _Link(end, nonce)
    deadline = time.monotonic() + _budget(expiry_mono, expiry_wall)
    try:
        while True:
            frame = link.read(WORKER_INBOUND_KINDS, deadline)
            if frame["kind"] == "challenge":
                link.send("alive", deadline, pid=os.getpid(), stage="worker")
    except WaitTimeout:
        return EXIT_DEADLINE
    except ChannelClosed:
        return EXIT_NO_CHANNEL
    except ProtocolError:
        return EXIT_PROTOCOL
    finally:
        end.close()


def _controller_main(
    parent_fd_text: str,
    ctrl_fd_text: str,
    expiry_mono: float,
    expiry_wall: float,
    nonce: str,
) -> int:
    """Independent controller: one trigger on one fire, then exit 0."""
    _install_lease(_budget(expiry_mono, expiry_wall))
    parent = _open_end(parent_fd_text)
    ctrl = _open_end(ctrl_fd_text)
    if parent is None or ctrl is None:
        return EXIT_NO_CHANNEL
    plink = _Link(parent, nonce)
    # Separate channel, separate sequence state.
    clink = _Link(ctrl, nonce)
    deadline = time.monotonic() + _budget(expiry_mono, expiry_wall)
    try:
        while True:
            frame = plink.read(CONTROLLER_INBOUND_KINDS, deadline)
            if frame["kind"] == "challenge":
                plink.send("alive", deadline, pid=os.getpid(), stage="controller")
                continue
            if frame["kind"] == "fire":
                clink.send("trigger", deadline)
                return EXIT_OK
    except WaitTimeout:
        return EXIT_DEADLINE
    except ChannelClosed:
        return EXIT_NO_CHANNEL
    except ProtocolError:
        return EXIT_PROTOCOL
    finally:
        ctrl.close()
        parent.close()


def _gate_main(
    parent_fd_text: str,
    ctrl_fd_text: str,
    expiry_mono: float,
    expiry_wall: float,
    root: str,
    nonce: str,
    resistant: str,
) -> int:
    """Prestarted gate: trigger OR genuine EOF -> ONE os.execve, SAME PID."""
    _install_lease(_budget(expiry_mono, expiry_wall))
    parent = _open_end(parent_fd_text)
    ctrl = _open_end(ctrl_fd_text)
    if parent is None or ctrl is None:
        return EXIT_NO_CHANNEL
    try:
        _validate_root(root)
    except ProtocolError:
        return EXIT_PROTOCOL
    link = _Link(parent, nonce)
    deadline = time.monotonic() + _budget(expiry_mono, expiry_wall)
    via = None
    try:
        while via is None:
            left = deadline - time.monotonic()
            if left <= 0:
                return EXIT_DEADLINE
            ready = select.select(
                [parent, ctrl], [], [], min(left, SELECT_SLICE_SECONDS)
            )
            if parent in ready[0]:
                frame = link.read(GATE_INBOUND_KINDS, deadline)
                if frame["kind"] == "challenge":
                    link.send("alive", deadline, pid=os.getpid(), stage="gate")
            if ctrl in ready[0]:
                try:
                    payload = read_frame(ctrl, deadline)
                except ChannelClosed:
                    # Genuine EOF: the parent holds NO copy of this channel and
                    # the controller was the sole writer.
                    via = "eof"
                    break
                try:
                    decode_frame(payload, GATE_TRIGGER_KINDS, nonce, 0)
                except ProtocolError:
                    # Refuse to exec on anything but a valid single trigger.
                    return EXIT_TRIGGER_INVALID
                via = "trigger"
                break
    except WaitTimeout:
        return EXIT_DEADLINE
    except ChannelClosed:
        return EXIT_NO_CHANNEL
    except ProtocolError:
        return EXIT_PROTOCOL
    if via is None:
        return EXIT_DEADLINE

    # -- the ONE trusted OS process replacement --------------------------
    # Close the trigger channel so the command never holds it, then hand the
    # parent descriptor over WITHOUT closing it and make its inheritability
    # explicit rather than depending on socket.socket(fileno=...) behaviour.
    ctrl.close()
    try:
        parent_fd = parent.detach()
        os.set_inheritable(parent_fd, True)
    except OSError:
        return EXIT_NO_CHANNEL
    argv = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        SCRIPT,
        "--spike-command",
        str(parent_fd),
        _fmt_num(expiry_mono),
        _fmt_num(expiry_wall),
        root,
        nonce,
        resistant,
        via,
        # execve preserves the PID, the group, the session and the descriptor,
        # but NOT interpreter state: the sequence counters must be handed over
        # or the parent's strict monotonic check would reject the first frame.
        str(link.out_seq),
        str(link.in_seq),
    ]
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
    try:
        os.execve(sys.executable, argv, env)
    except OSError:
        return EXIT_INTERNAL
    return EXIT_INTERNAL  # unreachable: execve does not return on success


def _command_main(
    fd_text: str,
    expiry_mono: float,
    expiry_wall: float,
    root: str,
    nonce: str,
    resistant: str,
    via: str,
    out_seq_text: str,
    in_seq_text: str,
) -> int:
    """The FIXED harmless command that replaced the gate in the SAME PID."""
    # SAME absolute expiry, never now + 8: execve destroyed the gate's threads
    # and its lease timer, so re-arm immediately from the handed-over expiry.
    _install_lease(_budget(expiry_mono, expiry_wall))
    end = _open_end(fd_text)
    if end is None:
        return EXIT_NO_CHANNEL
    if resistant == "1":
        _ignore_sigterm()
        _start_keepalive()
    link = _Link(end, nonce, _as_int(out_seq_text), _as_int(in_seq_text))
    if link.out_seq < 0 or link.in_seq < 0:
        return EXIT_PROTOCOL
    deadline = time.monotonic() + _budget(expiry_mono, expiry_wall)
    try:
        _write_marker(root, nonce, via)
    except OpFailure:
        return EXIT_INTERNAL
    except ProtocolError:
        return EXIT_PROTOCOL
    try:
        link.send(
            "started",
            deadline,
            pid=os.getpid(),
            stage="command",
            via=via,
            marker=MARKER_NAME,
        )
    except (ChannelClosed, WaitTimeout):
        # The marker is already the witness; report the ambiguity, never retry.
        return EXIT_NO_CHANNEL
    except ProtocolError:
        return EXIT_PROTOCOL
    if resistant != "1":
        end.close()
        return EXIT_OK
    try:
        while True:
            frame = link.read(COMMAND_INBOUND_KINDS, deadline)
            if frame["kind"] == "challenge":
                link.send("alive", deadline, pid=os.getpid(), stage="command")
    except WaitTimeout:
        return EXIT_DEADLINE
    except ChannelClosed:
        return EXIT_NO_CHANNEL
    except ProtocolError:
        return EXIT_PROTOCOL
    finally:
        end.close()


# --------------------------------------------------------------------------
# Parent-side resources: independent cleanup, real Popen boundary counting
# --------------------------------------------------------------------------


class Resources:
    """One fixture's sockets, Popen handles and private roots.

    ``popen_calls`` is incremented inside the single Popen wrapper on every
    REAL call, so "exactly 3 parent-owned children" is an observed boundary
    count, never a constant. Cleanup attempts every resource independently
    (own try/except each); one failure never skips the others and never masks
    the primary error. Roots are released only after every tracked child was
    actually reaped; a reap failure keeps ownership.
    """

    def __init__(self, base: str) -> None:
        self.base = base
        self.sockets = []
        self.popens = []
        self.roots = []
        self.errors = []
        self.retained_roots = []
        self.reap_failed = False
        self.popen_calls = 0
        self.cleaned = False

    def child_env(self) -> dict:
        # Minimal environment inside the parent-set private TMPDIR.
        return {"PATH": "/usr/bin:/bin", "TMPDIR": self.base}

    def pair(self):
        parent_end, child_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sockets.append(parent_end)
        self.sockets.append(child_end)
        return parent_end, child_end

    def track_root(self, path: str) -> str:
        self.roots.append(path)
        return path

    def spawn(self, mode_argv, pass_fds):
        """The ONLY subprocess.Popen call site in this file (harness side)."""
        argv = [sys.executable, "-I", "-S", "-B", SCRIPT] + list(mode_argv)
        popen = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=tuple(pass_fds),
            close_fds=True,
            start_new_session=True,
            env=self.child_env(),
        )
        self.popen_calls += 1
        self.popens.append(popen)
        return popen

    def lease_exits(self) -> int:
        return sum(1 for popen in self.popens if popen.returncode == EXIT_LEASE)

    def cleanup(self) -> None:
        # Idempotent: the case finally owns cleanup, and the harness may call
        # again on a containment error. A second pass must not manufacture
        # spurious root/socket errors over resources the first pass handled.
        if self.cleaned:
            return
        self.cleaned = True
        # 1. Reap every child independently. Signals only through the retained
        #    handle, poll-checked first, never after a successful reap.
        for popen in list(self.popens):
            try:
                if popen.poll() is None:
                    popen.kill()
                    popen.wait(timeout=POST_KILL_WAIT_SECONDS)
                else:
                    popen.wait(timeout=MIN_WAIT_SECONDS)
            except Exception as exc:
                self.reap_failed = True
                self.errors.append("reap:%s" % type(exc).__name__)
        # 2. Close every socket independently.
        for sock in list(self.sockets):
            try:
                sock.close()
            except Exception as exc:
                self.errors.append("socket:%s" % type(exc).__name__)
        # 3. Release this fixture's roots only when every reap succeeded. The
        #    private base is owned by the harness, not by this fixture.
        for path in list(self.roots):
            if self.reap_failed:
                self.retained_roots.append(path)
                continue
            try:
                shutil.rmtree(path)
            except Exception as exc:
                self.errors.append("root:%s" % type(exc).__name__)
                self.retained_roots.append(path)


class Fixture:
    """Three fresh parent-owned Popen children plus their four channels."""

    def __init__(self, root, nonce, popen_w, popen_c, popen_g, worker, controller, gate):
        self.root = root
        self.nonce = nonce
        self.popen_w = popen_w
        self.popen_c = popen_c
        self.popen_g = popen_g
        self.worker = worker
        self.controller = controller
        self.gate = gate


class ParentLink(_Link):
    """Parent-held end of one channel, with a per-operation timeout clamp."""

    def expect(self, allowed_kinds, deadline: float, op_seconds: float) -> dict:
        op_deadline = min(deadline, time.monotonic() + op_seconds)
        payload = read_frame(self.end, op_deadline)
        frame = decode_frame(payload, allowed_kinds, self.nonce, self.in_seq)
        self.in_seq = frame["seq"]
        return frame


def _close_quiet(sock) -> None:
    try:
        sock.close()
    except OSError:
        pass


def _new_nonce() -> str:
    return secrets.token_hex(NONCE_CHARS)


def _make_fixture(
    res: Resources,
    prefix: str,
    resistant: str,
    expiry_mono: float,
    expiry_wall: float,
) -> Fixture:
    """Fresh private root + exactly 3 parent-owned children + the FD map.

    The parent closes every child end IMMEDIATELY after the spawn that
    inherited it, and holds NO copy of the controller-to-gate channel, so EOF
    on that channel is genuine rather than masked by a parent duplicate.
    """
    root = res.track_root(tempfile.mkdtemp(prefix=prefix, dir=res.base))
    nonce = _new_nonce()
    mono = _fmt_num(expiry_mono)
    wall = _fmt_num(expiry_wall)

    # T: controller -> gate. Created first; the parent keeps NO end.
    t_ctrl, t_gate = res.pair()

    # W: parent <-> worker.
    w_parent, w_child = res.pair()
    popen_w = res.spawn(
        ["--spike-worker", str(w_child.fileno()), mono, wall, nonce],
        (w_child.fileno(),),
    )
    _close_quiet(w_child)  # immediate FD protection, before any wait

    # C: parent <-> controller, plus the controller's T writer end.
    c_parent, c_child = res.pair()
    popen_c = res.spawn(
        [
            "--spike-controller",
            str(c_child.fileno()),
            str(t_ctrl.fileno()),
            mono,
            wall,
            nonce,
        ],
        (c_child.fileno(), t_ctrl.fileno()),
    )
    _close_quiet(c_child)
    _close_quiet(t_ctrl)  # sole writer now lives only in the controller

    # G: parent <-> gate, which hands this descriptor to the command on exec.
    g_parent, g_child = res.pair()
    popen_g = res.spawn(
        [
            "--spike-gate",
            str(g_child.fileno()),
            str(t_gate.fileno()),
            mono,
            wall,
            root,
            nonce,
            resistant,
        ],
        (g_child.fileno(), t_gate.fileno()),
    )
    _close_quiet(g_child)
    _close_quiet(t_gate)  # sole reader now lives only in the gate

    return Fixture(
        root,
        nonce,
        popen_w,
        popen_c,
        popen_g,
        ParentLink(_End(w_parent), nonce),
        ParentLink(_End(c_parent), nonce),
        ParentLink(_End(g_parent), nonce),
    )


# --------------------------------------------------------------------------
# Parent-side stop / reap / challenge primitives
# --------------------------------------------------------------------------


def _challenge(link: ParentLink, deadline: float, op_seconds: float):
    """One fresh challenge round trip. Returns (frame, elapsed_ms)."""
    started = time.monotonic()
    link.send("challenge", deadline)
    frame = link.expect({"alive"}, deadline, op_seconds)
    return frame, (time.monotonic() - started) * 1000.0


def _reap(popen, deadline: float, timeout: float):
    """One reap through the retained handle. Returns (returncode, elapsed_ms)."""
    started = time.monotonic()
    budget = min(timeout, _remaining(deadline))
    rc = None
    try:
        rc = popen.wait(timeout=budget)
    except Exception:
        rc = None
    return rc, (time.monotonic() - started) * 1000.0


def _kill_and_reap(popen, deadline: float, timeout: float):
    """SIGKILL through the retained handle, poll-checked, then one reap."""
    started = time.monotonic()
    rc = None
    try:
        if popen.poll() is None:
            popen.kill()
        rc = popen.wait(timeout=min(timeout, _remaining(deadline)))
    except Exception:
        rc = None
    return rc, (time.monotonic() - started) * 1000.0


def _stop_resistant(popen, deadline: float, timeout: float):
    """terminate(), probe SIGTERM resistance, kill(), one reap.

    Returns (returncode, term_ignored, elapsed_ms). One stop sequence, never a
    retry: a wait that times out leaves the handle to independent cleanup.
    """
    started = time.monotonic()
    term_ignored = 0
    rc = None
    try:
        if popen.poll() is None:
            popen.terminate()
            try:
                popen.wait(timeout=TERM_PROBE_SECONDS)
            except subprocess.TimeoutExpired:
                term_ignored = 1
        if popen.poll() is None:
            popen.kill()
        rc = popen.wait(timeout=min(timeout, _remaining(deadline)))
    except Exception:
        rc = None
    return rc, term_ignored, (time.monotonic() - started) * 1000.0


def _finish(observed: dict, gates: list, res: Resources):
    """Append the independent-cleanup gates after the primary gates."""
    observed["popen_calls"] = res.popen_calls
    observed["cleanup_errors"] = len(res.errors)
    observed["retained_roots"] = len(res.retained_roots)
    observed["lease_exits"] = res.lease_exits()
    gates.extend(
        [
            ("popen_calls_3", res.popen_calls == 3),
            ("lease_exits_0", res.lease_exits() == 0),
            ("cleanup_errors_0", len(res.errors) == 0),
            ("retained_roots_0", len(res.retained_roots) == 0),
        ]
    )


def _same_pid(snap: dict, popen_g, started_pid_match: int) -> int:
    return int(snap["pid"] > 0 and snap["pid"] == popen_g.pid and started_pid_match == 1)


# --------------------------------------------------------------------------
# Named numeric case 1: normal arm -> worker kill -> exec in the same PID
# --------------------------------------------------------------------------


def _case1(res: Resources, expiry_mono: float, expiry_wall: float, deadline: float):
    started_case = time.monotonic()
    observed = {}
    gates = []
    try:
        fx = _make_fixture(res, "v202-c1-", "0", expiry_mono, expiry_wall)
        gate_pid = fx.popen_g.pid

        # Worker answers, then is stopped: SIGTERM ignored, SIGKILL works.
        frame, ms = _challenge(fx.worker, deadline, CHALLENGE_SECONDS)
        observed["chal_worker_ms"] = round(ms, 1)
        observed["worker_stage"] = frame["stage"]
        rc, term_ignored, stop_ms = _stop_resistant(fx.popen_w, deadline, STOP_SECONDS)
        observed["worker_rc"] = rc
        observed["worker_term_ignored"] = term_ignored
        observed["worker_stop_ms"] = round(stop_ms, 1)

        # Controller and gate still alive and responsive after that death.
        frame, ms = _challenge(fx.controller, deadline, CHALLENGE_SECONDS)
        observed["chal_controller_ms"] = round(ms, 1)
        observed["controller_stage"] = frame["stage"]
        frame, ms = _challenge(fx.gate, deadline, CHALLENGE_SECONDS)
        observed["chal_gate_ms"] = round(ms, 1)
        observed["gate_pre_stage"] = frame["stage"]
        observed["gate_pre_pid_match"] = int(frame["pid"] == gate_pid)

        # One fire -> one trigger -> ONE execve in the SAME PID.
        fx.controller.send("fire", deadline)
        op_started = time.monotonic()
        frame = fx.gate.expect({"started"}, deadline, LOCAL_OP_SECONDS)
        observed["started_ms"] = round((time.monotonic() - op_started) * 1000.0, 1)
        observed["started_via"] = frame["via"]
        observed["started_stage"] = frame["stage"]
        started_pid_match = int(frame["pid"] == gate_pid)
        observed["started_pid_match"] = started_pid_match
        observed["exec_count"] = 1 if frame["stage"] == "command" else 0

        # Controller exits 0; the command is reaped through the ORIGINAL handle.
        rc_c, ms_c = _reap(fx.popen_c, deadline, STOP_SECONDS)
        observed["controller_rc"] = rc_c
        observed["controller_reap_ms"] = round(ms_c, 1)
        rc_g, ms_g = _reap(fx.popen_g, deadline, STOP_SECONDS)
        observed["command_rc"] = rc_g
        observed["command_reap_ms"] = round(ms_g, 1)

        # Snapshot ONLY after all three children were actually reaped.
        snap = _snapshot_root(fx.root)
        observed["markers"] = snap["count"]
        observed["marker_mode"] = oct(snap["mode"]) if snap["mode"] >= 0 else snap["mode"]
        observed["marker_lines"] = snap["lines"]
        observed["marker_pid_match"] = int(snap["pid"] == gate_pid)
        observed["marker_nonce_match"] = int(snap["nonce"] == fx.nonce)
        observed["marker_via"] = snap["via"]
        observed["same_pid"] = _same_pid(snap, fx.popen_g, started_pid_match)
        observed["elapsed_s"] = round(time.monotonic() - started_case, 3)

        gates = [
            ("worker_rc_sigkill", observed["worker_rc"] == -9),
            ("worker_term_ignored_1", observed["worker_term_ignored"] == 1),
            ("worker_stop_ms_le_1000", observed["worker_stop_ms"] <= 1000.0),
            ("worker_stage_worker", observed["worker_stage"] == "worker"),
            ("chal_worker_ms_le_500", observed["chal_worker_ms"] <= 500.0),
            ("chal_controller_ms_le_500", observed["chal_controller_ms"] <= 500.0),
            ("chal_gate_ms_le_500", observed["chal_gate_ms"] <= 500.0),
            (
                "controller_stage_controller",
                observed["controller_stage"] == "controller",
            ),
            ("gate_pre_stage_gate", observed["gate_pre_stage"] == "gate"),
            ("gate_pre_pid_match_1", observed["gate_pre_pid_match"] == 1),
            ("started_via_trigger", observed["started_via"] == "trigger"),
            ("started_stage_command", observed["started_stage"] == "command"),
            ("started_pid_match_1", observed["started_pid_match"] == 1),
            ("exec_count_1", observed["exec_count"] == 1),
            ("started_ms_le_2000", observed["started_ms"] <= 2000.0),
            ("controller_rc_0", observed["controller_rc"] == EXIT_OK),
            ("controller_reap_ms_le_1000", observed["controller_reap_ms"] <= 1000.0),
            ("command_rc_0", observed["command_rc"] == EXIT_OK),
            ("command_reap_ms_le_1000", observed["command_reap_ms"] <= 1000.0),
            ("markers_1", observed["markers"] == 1),
            ("marker_mode_0600", snap["mode"] == 0o600),
            ("marker_lines_1", observed["marker_lines"] == 1),
            ("marker_pid_match_1", observed["marker_pid_match"] == 1),
            ("marker_nonce_match_1", observed["marker_nonce_match"] == 1),
            ("marker_via_trigger", observed["marker_via"] == "trigger"),
            ("same_pid_1", observed["same_pid"] == 1),
            ("elapsed_s_le_2_50", observed["elapsed_s"] <= CASE_BUDGET_SECONDS),
        ]
        return observed, gates
    finally:
        res.cleanup()
        _finish(observed, gates, res)


# --------------------------------------------------------------------------
# Named numeric case 2: controller death BEFORE trigger -> genuine EOF exec
# --------------------------------------------------------------------------


def _case2(res: Resources, expiry_mono: float, expiry_wall: float, deadline: float):
    started_case = time.monotonic()
    observed = {}
    gates = []
    try:
        fx = _make_fixture(res, "v202-c2-", "0", expiry_mono, expiry_wall)
        gate_pid = fx.popen_g.pid
        popen_before = res.popen_calls

        frame, ms = _challenge(fx.worker, deadline, CHALLENGE_SECONDS)
        observed["chal_worker_ms"] = round(ms, 1)
        observed["worker_stage"] = frame["stage"]
        frame, ms = _challenge(fx.controller, deadline, CHALLENGE_SECONDS)
        observed["chal_controller_ms"] = round(ms, 1)
        observed["controller_stage"] = frame["stage"]
        frame, ms = _challenge(fx.gate, deadline, CHALLENGE_SECONDS)
        observed["chal_gate_ms"] = round(ms, 1)
        observed["gate_pre_stage"] = frame["stage"]
        observed["gate_pre_pid_match"] = int(frame["pid"] == gate_pid)

        # Kill and reap ONLY the controller group. The parent holds NO copy of
        # the controller-to-gate channel, so this closes the sole writer.
        rc_c, ms_c = _kill_and_reap(fx.popen_c, deadline, STOP_SECONDS)
        observed["controller_rc"] = rc_c
        observed["controller_stop_ms"] = round(ms_c, 1)
        observed["additional_popens"] = res.popen_calls - popen_before

        # The gate MUST observe actual EOF and exec exactly once, same PID.
        op_started = time.monotonic()
        frame = fx.gate.expect({"started"}, deadline, LOCAL_OP_SECONDS)
        observed["eof_exec_ms"] = round((time.monotonic() - op_started) * 1000.0, 1)
        observed["started_via"] = frame["via"]
        observed["started_stage"] = frame["stage"]
        started_pid_match = int(frame["pid"] == gate_pid)
        observed["started_pid_match"] = started_pid_match
        observed["exec_count"] = 1 if frame["stage"] == "command" else 0

        # The parent still reaps the command through the ORIGINAL gate Popen.
        rc_g, ms_g = _reap(fx.popen_g, deadline, STOP_SECONDS)
        observed["command_rc"] = rc_g
        observed["command_reap_ms"] = round(ms_g, 1)

        # Worker independently reaped.
        rc_w, term_w, ms_w = _stop_resistant(fx.popen_w, deadline, STOP_SECONDS)
        observed["worker_rc"] = rc_w
        observed["worker_term_ignored"] = term_w
        observed["worker_stop_ms"] = round(ms_w, 1)

        snap = _snapshot_root(fx.root)
        observed["markers"] = snap["count"]
        observed["marker_mode"] = oct(snap["mode"]) if snap["mode"] >= 0 else snap["mode"]
        observed["marker_lines"] = snap["lines"]
        observed["marker_pid_match"] = int(snap["pid"] == gate_pid)
        observed["marker_nonce_match"] = int(snap["nonce"] == fx.nonce)
        observed["marker_via"] = snap["via"]
        observed["same_pid"] = _same_pid(snap, fx.popen_g, started_pid_match)
        observed["elapsed_s"] = round(time.monotonic() - started_case, 3)

        gates = [
            ("chal_worker_ms_le_500", observed["chal_worker_ms"] <= 500.0),
            ("chal_controller_ms_le_500", observed["chal_controller_ms"] <= 500.0),
            ("chal_gate_ms_le_500", observed["chal_gate_ms"] <= 500.0),
            ("gate_pre_stage_gate", observed["gate_pre_stage"] == "gate"),
            ("gate_pre_pid_match_1", observed["gate_pre_pid_match"] == 1),
            ("controller_rc_sigkill", observed["controller_rc"] == -9),
            (
                "controller_stop_ms_le_1000",
                observed["controller_stop_ms"] <= 1000.0,
            ),
            ("additional_popens_0", observed["additional_popens"] == 0),
            ("started_via_eof", observed["started_via"] == "eof"),
            ("started_stage_command", observed["started_stage"] == "command"),
            ("started_pid_match_1", observed["started_pid_match"] == 1),
            ("exec_count_1", observed["exec_count"] == 1),
            ("eof_exec_ms_le_2000", observed["eof_exec_ms"] <= 2000.0),
            ("command_rc_0", observed["command_rc"] == EXIT_OK),
            (
                "command_reap_ms_le_1000",
                observed["command_reap_ms"] <= 1000.0,
            ),
            ("worker_rc_sigkill", observed["worker_rc"] == -9),
            ("worker_term_ignored_1", observed["worker_term_ignored"] == 1),
            ("worker_stop_ms_le_1000", observed["worker_stop_ms"] <= 1000.0),
            ("markers_1", observed["markers"] == 1),
            ("marker_mode_0600", snap["mode"] == 0o600),
            ("marker_lines_1", observed["marker_lines"] == 1),
            ("marker_pid_match_1", observed["marker_pid_match"] == 1),
            ("marker_nonce_match_1", observed["marker_nonce_match"] == 1),
            ("marker_via_eof", observed["marker_via"] == "eof"),
            ("same_pid_1", observed["same_pid"] == 1),
            ("elapsed_s_le_2_50", observed["elapsed_s"] <= CASE_BUDGET_SECONDS),
        ]
        return observed, gates
    finally:
        res.cleanup()
        _finish(observed, gates, res)


# --------------------------------------------------------------------------
# Named numeric case 3: controller death WHILE the command runs
# --------------------------------------------------------------------------


def _case3(res: Resources, expiry_mono: float, expiry_wall: float, deadline: float):
    started_case = time.monotonic()
    observed = {}
    gates = []
    try:
        fx = _make_fixture(res, "v202-c3-", "1", expiry_mono, expiry_wall)
        gate_pid = fx.popen_g.pid
        popen_before = res.popen_calls

        frame, ms = _challenge(fx.worker, deadline, CHALLENGE_SECONDS)
        observed["chal_worker_ms"] = round(ms, 1)
        frame, ms = _challenge(fx.controller, deadline, CHALLENGE_SECONDS)
        observed["chal_controller_ms"] = round(ms, 1)
        frame, ms = _challenge(fx.gate, deadline, CHALLENGE_SECONDS)
        observed["chal_gate_ms"] = round(ms, 1)
        observed["gate_pre_stage"] = frame["stage"]
        observed["gate_pre_pid_match"] = int(frame["pid"] == gate_pid)

        # Genuine trigger and exec observed BEFORE any controller death.
        fx.controller.send("fire", deadline)
        op_started = time.monotonic()
        frame = fx.gate.expect({"started"}, deadline, LOCAL_OP_SECONDS)
        observed["started_ms"] = round((time.monotonic() - op_started) * 1000.0, 1)
        observed["started_via"] = frame["via"]
        observed["started_stage"] = frame["stage"]
        started_pid_match = int(frame["pid"] == gate_pid)
        observed["started_pid_match"] = started_pid_match
        observed["exec_count"] = 1 if frame["stage"] == "command" else 0

        # Kill and reap the controller, then the worker, independently.
        rc_c, ms_c = _kill_and_reap(fx.popen_c, deadline, STOP_SECONDS)
        observed["controller_rc"] = rc_c
        observed["controller_stop_ms"] = round(ms_c, 1)
        rc_w, term_w, ms_w = _stop_resistant(fx.popen_w, deadline, STOP_SECONDS)
        observed["worker_rc"] = rc_w
        observed["worker_term_ignored"] = term_w
        observed["worker_stop_ms"] = round(ms_w, 1)

        # The resistant command survives both deaths and answers fresh.
        frame, ms = _challenge(fx.gate, deadline, CHALLENGE_SECONDS)
        observed["chal_command_after_death_ms"] = round(ms, 1)
        observed["chal_command_stage"] = frame["stage"]
        observed["chal_command_pid_match"] = int(frame["pid"] == gate_pid)

        # The parent terminates, then KILLs and reaps its retained handle.
        rc_g, term_g, ms_g = _stop_resistant(fx.popen_g, deadline, STOP_SECONDS)
        observed["command_rc"] = rc_g
        observed["command_term_ignored"] = term_g
        observed["command_stop_ms"] = round(ms_g, 1)
        observed["additional_popens"] = res.popen_calls - popen_before

        snap = _snapshot_root(fx.root)
        observed["markers"] = snap["count"]
        observed["marker_mode"] = oct(snap["mode"]) if snap["mode"] >= 0 else snap["mode"]
        observed["marker_lines"] = snap["lines"]
        observed["marker_pid_match"] = int(snap["pid"] == gate_pid)
        observed["marker_nonce_match"] = int(snap["nonce"] == fx.nonce)
        observed["marker_via"] = snap["via"]
        observed["same_pid"] = _same_pid(snap, fx.popen_g, started_pid_match)
        observed["elapsed_s"] = round(time.monotonic() - started_case, 3)

        gates = [
            ("chal_worker_ms_le_500", observed["chal_worker_ms"] <= 500.0),
            ("chal_controller_ms_le_500", observed["chal_controller_ms"] <= 500.0),
            ("chal_gate_ms_le_500", observed["chal_gate_ms"] <= 500.0),
            ("gate_pre_stage_gate", observed["gate_pre_stage"] == "gate"),
            ("gate_pre_pid_match_1", observed["gate_pre_pid_match"] == 1),
            ("started_via_trigger", observed["started_via"] == "trigger"),
            ("started_pid_match_1", observed["started_pid_match"] == 1),
            ("exec_count_1", observed["exec_count"] == 1),
            ("started_ms_le_2000", observed["started_ms"] <= 2000.0),
            ("controller_rc_sigkill", observed["controller_rc"] == -9),
            (
                "controller_stop_ms_le_1000",
                observed["controller_stop_ms"] <= 1000.0,
            ),
            ("worker_rc_sigkill", observed["worker_rc"] == -9),
            ("worker_term_ignored_1", observed["worker_term_ignored"] == 1),
            ("worker_stop_ms_le_1000", observed["worker_stop_ms"] <= 1000.0),
            (
                "chal_command_after_death_ms_le_500",
                observed["chal_command_after_death_ms"] <= 500.0,
            ),
            ("chal_command_stage_command", observed["chal_command_stage"] == "command"),
            ("chal_command_pid_match_1", observed["chal_command_pid_match"] == 1),
            ("command_term_ignored_1", observed["command_term_ignored"] == 1),
            ("command_rc_sigkill", observed["command_rc"] == -9),
            ("command_stop_ms_le_1000", observed["command_stop_ms"] <= 1000.0),
            ("additional_popens_0", observed["additional_popens"] == 0),
            ("markers_1", observed["markers"] == 1),
            ("marker_mode_0600", snap["mode"] == 0o600),
            ("marker_lines_1", observed["marker_lines"] == 1),
            ("marker_pid_match_1", observed["marker_pid_match"] == 1),
            ("marker_nonce_match_1", observed["marker_nonce_match"] == 1),
            ("marker_via_trigger", observed["marker_via"] == "trigger"),
            ("same_pid_1", observed["same_pid"] == 1),
            ("elapsed_s_le_2_50", observed["elapsed_s"] <= CASE_BUDGET_SECONDS),
        ]
        return observed, gates
    finally:
        res.cleanup()
        _finish(observed, gates, res)


CASES = (
    ("case1_normal_arm_worker_kill_exec_same_pid", _case1),
    ("case2_controller_death_before_trigger_eof_exec_once", _case2),
    ("case3_controller_death_while_command_runs_custody_retained", _case3),
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
    expiry_mono = started + HARNESS_EXPIRY_SECONDS
    expiry_wall = time.time() + HARNESS_EXPIRY_SECONDS

    # Parent-set private TMPDIR: every tiny root lives inside it.
    base = None
    try:
        base = tempfile.mkdtemp(prefix="v202-base-")
        os.chmod(base, 0o700)
    except OSError:
        print("RESULT FAIL base_unavailable", flush=True)
        return EXIT_INTERNAL

    all_pass = True
    popen_total = 0
    cleanup_error_total = 0
    retained_total = 0
    lease_total = 0
    for index, (name, fn) in enumerate(CASES, start=1):
        res = Resources(base)
        case_deadline = min(expiry_mono, time.monotonic() + CASE_BUDGET_SECONDS)
        try:
            observed, gates = fn(res, expiry_mono, expiry_wall, case_deadline)
        except Exception as exc:
            # Containment errors are NONPASS, never a pass.
            observed = {
                "internal_error": type(exc).__name__,
                "detail": str(exc)[:120],
            }
            gates = [("internal_error", False)]
            res.cleanup()
        popen_total += res.popen_calls
        cleanup_error_total += len(res.errors)
        retained_total += len(res.retained_roots)
        lease_total += res.lease_exits()
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
    # Release the private base only when nothing was retained anywhere.
    base_released = 0
    if retained_total == 0 and cleanup_error_total == 0:
        try:
            shutil.rmtree(base)
            base_released = 1
        except OSError:
            base_released = 0

    timing_ok = elapsed < TOTAL_GATE_SECONDS
    hygiene_ok = (
        cleanup_error_total == 0
        and retained_total == 0
        and lease_total == 0
        and base_released == 1
        and popen_total == 9
    )
    print(
        "TOTAL elapsed_s=%.3f gate_s=%.2f popen_total=%d cleanup_errors=%d "
        "retained_roots=%d lease_exits=%d base_released=%d %s"
        % (
            elapsed,
            TOTAL_GATE_SECONDS,
            popen_total,
            cleanup_error_total,
            retained_total,
            lease_total,
            base_released,
            "PASS" if (timing_ok and hygiene_ok) else "FAIL",
        ),
        flush=True,
    )
    result_ok = all_pass and timing_ok and hygiene_ok
    print("RESULT %s" % ("PASS" if result_ok else "FAIL"), flush=True)
    # On FAIL with base_released=0 the base stays on disk for parent inspection.
    # Nothing in this harness touches it again.
    return EXIT_OK if result_ok else EXIT_GATE_FAIL


def _dispatch(argv) -> int:
    count = len(argv)
    if count == 1:
        return _run_harness()
    mode = argv[1]
    if mode == "--spike-worker" and count == 6:
        return _worker_main(argv[2], float(argv[3]), float(argv[4]), argv[5])
    if mode == "--spike-controller" and count == 7:
        return _controller_main(
            argv[2], argv[3], float(argv[4]), float(argv[5]), argv[6]
        )
    if mode == "--spike-gate" and count == 9:
        return _gate_main(
            argv[2],
            argv[3],
            float(argv[4]),
            float(argv[5]),
            argv[6],
            argv[7],
            argv[8],
        )
    if mode == "--spike-command" and count == 11:
        return _command_main(
            argv[2],
            float(argv[3]),
            float(argv[4]),
            argv[5],
            argv[6],
            argv[7],
            argv[8],
            argv[9],
            argv[10],
        )
    return EXIT_INTERNAL


def main(argv) -> int:
    try:
        return _dispatch(argv)
    except Exception:
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
