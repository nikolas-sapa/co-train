#!/usr/bin/env python3
"""SOURCEONLY UNRUN. Fixed stdlib capability experiment, not production authority.

Only the parent may execute/review this delivery. Three fixed entry modes:
harness, --worker, --sentinel. No SDK, commands or services. Toy children do not spawn.
PROVES is planned only until the parent records real case/counter/timing results.
SHORTCUT: trusted same-user toy children, synthetic journal/marker operation,
fixed fault effects and Python timer containment. Production authority, SDK
lifecycle, watchdog delegation and paid/native/tensor/science proof are MISSING.
"""

from __future__ import annotations

import collections
import json
import math
import os
import re
import secrets
import select
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time


LIMIT = 8192
RESERVE = 0.12
LEASE = 8.0
MARKER = "operation.marker"
JOURNAL = "attempt.journal"
HEX = re.compile(r"[0-9a-f]{32}")
BASE = {"v", "kind", "session", "nonce", "seq"}
FIELDS = {
    "ready": {"deadline"},
    "ready_ack": set(),
    "want_open": set(),
    "open": {"deadline"},
    "want_create": set(),
    "create": {"deadline"},
    "consumed": set(),
    "created": set(),
    "error": {"reason"},
    "arm": {"deadline", "effect"},
    "arm_consumed": set(),
    "armed": set(),
    "check": set(),
    "alive": set(),
    "stop": set(),
    "stopped": set(),
}
EFFECTS = {"normal", "lost_ack", "disconnect", "expiry"}


class Reject(Exception):
    """A specific local/protocol refusal, never an operation result."""


class Ambiguous(Exception):
    """A dispatch or reply is uncertain; the parent session is terminal."""


class Closed(Exception):
    pass


class Expired(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def left(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Expired("deadline")
    return remaining


def dump(value):
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Reject("duplicate")
        result[key] = value
    return result


def nonfinite(_value):
    raise Reject("nonfinite")


def finite_tree(value):
    if type(value) is float and not math.isfinite(value):
        raise Reject("nonfinite")
    if type(value) is dict:
        for item in value.values():
            finite_tree(item)
    elif type(value) is list:
        for item in value:
            finite_tree(item)


def load(payload):
    if not 0 < len(payload) <= LIMIT:
        raise Reject("size")
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
        finite_tree(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Reject("json") from exc


def number(value):
    if type(value) is int:
        return 0 < value < 2**63
    return type(value) is float and math.isfinite(value) and value > 0


def decode(payload, kinds, session, nonce, previous, cap):
    value = load(payload)
    if type(value) is not dict:
        raise Reject("object")
    kind = value.get("kind")
    if type(kind) is not str or kind not in kinds or kind not in FIELDS:
        raise Reject("kind")
    if set(value) != BASE | FIELDS[kind]:
        raise Reject("fields")
    if type(value["v"]) is not int or value["v"] != 1:
        raise Reject("version")
    if type(value["session"]) is not str or not HEX.fullmatch(value["session"]):
        raise Reject("session_shape")
    # SESSION_GUARD: parent red/green removes exactly this conditional + raise.
    if value["session"] != session:
        raise Reject("session")
    if type(value["nonce"]) is not str or value["nonce"] != nonce:
        raise Reject("capability")
    if type(value["seq"]) is not int or value["seq"] != previous + 1:
        raise Reject("sequence")
    if "deadline" in value:
        if not number(value["deadline"]):
            raise Reject("deadline")
        # READY_CAP_GUARD: worker passes its frozen initial cap, not its lease.
        if value["deadline"] > cap:
            raise Reject("extension")
    if "reason" in value:
        text = value["reason"]
        if type(text) is not str or not 0 < len(text) <= 64:
            raise Reject("reason")
        if not all(32 <= ord(char) <= 126 for char in text):
            raise Reject("reason")
    if kind == "arm":
        if type(value["effect"]) is not str or value["effect"] not in ("normal", "lost_ack"):
            raise Reject("effect")
    return value


def metadata(payload):
    value = load(payload)
    if type(value) is not dict or set(value) != {"effect", "pad"}:
        raise Reject("metadata_fields")
    if type(value["effect"]) is not str or value["effect"] not in EFFECTS:
        raise Reject("effect")
    if type(value["pad"]) is not str:
        raise Reject("pad")
    if not all(32 <= ord(char) <= 126 for char in value["pad"]):
        raise Reject("pad")
    if len(dump(value)) > LIMIT:
        raise Reject("size")
    return value


def read_exact(sock, count, deadline):
    result = bytearray()
    while len(result) < count:
        ready, _, _ = select.select([sock], [], [], left(deadline))
        if not ready:
            raise Expired("read")
        try:
            chunk = sock.recv(count - len(result))
        except (BlockingIOError, InterruptedError):
            continue
        if not chunk:
            raise Closed("eof")
        result.extend(chunk)
    return bytes(result)


def read_record(sock, deadline):
    count = int.from_bytes(read_exact(sock, 4, deadline), "big")
    if not 0 < count <= LIMIT:
        raise Reject("size")
    return read_exact(sock, count, deadline)


def write_record(sock, payload, deadline, counts, partial=False):
    if not 0 < len(payload) <= LIMIT:
        raise Reject("size")
    wire = len(payload).to_bytes(4, "big") + payload
    counts["record_attempts"] += 1
    write_bytes(sock, wire, deadline, counts, partial=partial)
    counts["records"] += 1


def write_bytes(sock, wire, deadline, counts, partial=False):
    """Nonblocking byte boundary, also used by the fixed oversized-header fault."""
    sent = 0
    stop = 9 if partial else len(wire)
    while sent < stop:
        _, ready, _ = select.select([], [sock], [], left(deadline))
        if not ready:
            raise Expired("write")
        try:
            count = sock.send(wire[sent:stop])
        except (BlockingIOError, InterruptedError):
            continue
        if count == 0:
            raise Closed("zero_send")
        sent += count
        counts["bytes"] += count
    if partial:
        counts["partial_failures"] += 1
        raise Closed("injected_after_9_bytes")


class Channel:
    def __init__(self, sock, session, nonce, deadline):
        self.sock, self.session, self.nonce = sock, session, nonce
        self.deadline = deadline
        self.rx = self.tx = 0
        self.counts = collections.Counter()
        sock.setblocking(False)

    def send(self, kind, *, partial=False, overrides=None, **extra):
        self.tx += 1
        value = {
            "v": 1, "kind": kind, "session": self.session,
            "nonce": self.nonce, "seq": self.tx, **extra,
        }
        if overrides:
            value.update(overrides)
        payload = dump(value)
        self.raw(payload, partial=partial)
        return payload

    def raw(self, payload, *, partial=False):
        write_record(
            self.sock, payload, self.deadline, self.counts, partial=partial,
        )

    def recv(self, *kinds, cap=None):
        payload = read_record(self.sock, self.deadline)
        value = decode(
            payload, set(kinds), self.session, self.nonce, self.rx,
            self.deadline if cap is None else cap,
        )
        self.rx = value["seq"]
        return value


def arm_lease(expiry):
    remaining = expiry - time.monotonic()
    if not math.isfinite(expiry) or remaining <= 0:
        os._exit(97)
    # No child gets now+8. A late child inherits the same original expiry.
    if remaining > LEASE:
        raise Reject("lease")
    timer = threading.Timer(remaining, lambda: os._exit(97))
    timer.daemon = True
    timer.start()
    return timer


def append_event(directory, event):
    fd = os.open(
        JOURNAL, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
        0o600, dir_fd=directory,
    )
    try:
        os.fchmod(fd, 0o600)
        line = (event + "\n").encode("ascii")
        if os.write(fd, line) != len(line):
            raise OSError("short_journal")
        os.fsync(fd)
    finally:
        os.close(fd)


def operation(root, session, deadline):
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Reject("root")
        # FINAL_EXPIRY_GUARD: no attempt journal entry before this check.
        left(deadline)
        append_event(directory, "attempt")
        left(deadline)
        fd = os.open(
            MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        try:
            os.fchmod(fd, 0o600)
            data = (session + "\n").encode("ascii")
            if os.write(fd, data) != len(data):
                raise OSError("short_marker")
            os.fsync(fd)
        finally:
            os.close(fd)
        append_event(directory, "complete")
    finally:
        os.close(directory)


def worker(channel, root, lease):
    ready = channel.recv("ready", cap=lease)
    initial = ready["deadline"]
    channel.deadline = min(lease, initial)
    left(channel.deadline)
    channel.send("ready_ack")
    channel.send("want_open")
    opened = channel.recv("open", cap=initial)
    channel.send("want_create")
    permit = channel.recv("create", cap=initial)
    data = metadata(read_record(channel.sock, channel.deadline))
    deadline = min(initial, opened["deadline"], permit["deadline"], lease)
    channel.send("consumed")
    # Fixed trusted fault hooks; every fixture still uses this real op path.
    if data["effect"] == "disconnect":
        channel.sock.shutdown(socket.SHUT_RDWR)
        return 4
    if data["effect"] == "expiry":
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    operation(root, channel.session, deadline)
    if data["effect"] == "lost_ack":
        return 4
    channel.send("created")
    return 0


def sentinel(channel, _root, lease):
    frame = channel.recv("arm", cap=lease)
    channel.deadline = min(lease, frame["deadline"])
    channel.send("arm_consumed")
    if frame["effect"] == "lost_ack":
        return 4
    channel.send("armed")
    # ARMED is not an instruction to exit. Stay independently alive.
    channel.recv("check")
    channel.send("alive")
    channel.recv("stop")
    channel.send("stopped")
    return 0


def child_main(argv):
    channel = None
    timer = None
    try:
        lease = float(argv[3])
        timer = arm_lease(lease)  # Before opening the FD or any channel read.
        session, nonce, root = argv[4:7]
        if not HEX.fullmatch(session) or not HEX.fullmatch(nonce):
            return 2
        try:
            sock = socket.socket(fileno=int(argv[2]))
            if sock.family != socket.AF_UNIX:
                sock.close()
                return 3
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
                sock.close()
                return 3
            sock.getpeername()
        except (ValueError, OSError):
            return 3
        channel = Channel(sock, session, nonce, lease)
        if not os.path.isabs(root) or os.path.normpath(root) != root:
            raise Reject("root")
        return (worker if argv[1] == "--worker" else sentinel)(channel, root, lease)
    except Reject as exc:
        if channel is not None:
            try:
                channel.send("error", reason=str(exc))
            except (OSError, Closed, Expired, Reject):
                pass
        return 5
    except Expired:
        return 8
    except (Closed, OSError):
        return 4
    except Exception:
        return 2
    finally:
        if channel is not None:
            channel.sock.close()
        if timer is not None:
            timer.cancel()


class Owned:
    """Only this parent object reaps/signals its retained, newly created Popen."""

    def __init__(self, handle):
        self.handle = handle
        self.reaped = False
        self.code = None

    def live(self):
        if self.reaped:
            return False
        code = self.handle.poll()
        if code is None:
            return True
        self.code = self.handle.wait(timeout=0)
        self.reaped = True
        return False

    def join(self, deadline):
        if not self.reaped:
            self.code = self.handle.wait(timeout=left(deadline))
            self.reaped = True
        return self.code

    def kill_join(self, deadline):
        if self.live():  # No signal after observed reap.
            self.handle.kill()
        if not self.reaped:
            remaining = deadline - time.monotonic()
            # Zero is a nonblocking reap observation, not a renewed timeout.
            self.code = self.handle.wait(timeout=remaining if remaining > 0 else 0)
            self.reaped = True
        return self.code


class Run:
    def __init__(self):
        self.started = time.monotonic()
        self.expiry = self.started + LEASE
        self.nonces = set()
        self.retained = []

    def fresh(self):
        value = secrets.token_hex(16)
        if value in self.nonces:
            raise Reject("nonce_reuse")
        self.nonces.add(value)
        return value


class Fixture:
    def __init__(self, case, *, inherit=True):
        self.case = case
        self.counts = collections.Counter()
        self.events = []
        self.sockets = []
        self.channels = []
        self.processes = []
        self.resource_errors = []
        self.worker_handle = self.sentinel_handle = None
        self.wire = self.sentinel_wire = None
        self.root = None
        self.snap = None
        self.terminal = self.admitted = self.opened = False
        self.arm_used = self.armed = self.used = False
        self.ready_cap = case.io_end
        self.session = case.run.fresh()
        self.nonce = case.run.fresh()
        case.fixtures.append(self)
        left(case.io_end)
        self.root = tempfile.mkdtemp(prefix="gpt-v194-")
        os.chmod(self.root, 0o700)
        self.spawn_worker(inherit=inherit)

    def refuse(self, reason, *, terminal=False):
        if terminal:
            self.terminal = True
        self.counts["refusals"] += 1
        self.events.append(["refused", reason])
        raise Reject(reason)

    def spawn(self, mode, inherit=True):
        left(self.case.io_end)
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sockets.extend((parent, child))
        parent.setblocking(False)
        child.setblocking(False)
        fd = child.fileno()
        args = [
            sys.executable, "-I", "-S", "-B", os.path.abspath(__file__), mode,
            str(fd), repr(self.case.run.expiry), self.session, self.nonce,
            self.root,
        ]
        self.counts["spawn_attempts"] += 1
        try:
            handle = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
                pass_fds=(fd,) if inherit else (), start_new_session=True,
                env={"PATH": "/usr/bin:/bin"},
            )
            owned = Owned(handle)
            self.processes.append(owned)
            self.counts["spawns"] += 1
        finally:
            try:
                child.close()  # Immediate copy closure, before any read.
            except OSError as exc:
                self.resource_errors.append("spawn_fd:" + type(exc).__name__)
        channel = Channel(parent, self.session, self.nonce, self.case.io_end)
        self.channels.append(channel)
        return owned, channel

    def spawn_worker(self, *, inherit=True):
        self.counts["spawn_worker_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if self.worker_handle is not None:
            self.refuse("replacement")
        self.worker_handle, self.wire = self.spawn("--worker", inherit=inherit)

    def new_sentinel(self):
        if self.terminal or self.sentinel_handle is not None:
            self.refuse("replacement")
        self.sentinel_handle, self.sentinel_wire = self.spawn("--sentinel")

    def dispatch(self, kind, channel, *, partial=False, **extra):
        intent = {
            "ready": self.admitted, "open": self.opened,
            "arm": self.arm_used, "create": self.used,
        }[kind]
        self.events.append(["intent_before_dispatch", kind, intent])
        self.counts[kind + "_dispatches"] += 1
        try:
            return channel.send(kind, partial=partial, **extra)
        except (OSError, Closed, Expired, Reject) as exc:
            self.terminal = True
            raise Ambiguous(str(exc)) from exc

    def receive(self, channel, *kinds):
        try:
            return channel.recv(*kinds)
        except (OSError, Closed, Expired, Reject) as exc:
            self.terminal = True
            raise Ambiguous(str(exc)) from exc

    def admit(self, *, partial=False, short=False):
        self.counts["admit_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if self.admitted:
            self.refuse("second_admission")
        if short:
            self.ready_cap = min(self.case.io_end, time.monotonic() + 0.12)
        self.admitted = True  # ADMISSION_LATCH, before dispatch bytes.
        self.counts["admission_intents"] += 1
        self.dispatch("ready", self.wire, partial=partial, deadline=self.ready_cap)
        self.receive(self.wire, "ready_ack")
        self.counts["ready_acks"] += 1

    def open(self):
        self.counts["open_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if not self.admitted or self.opened:
            self.refuse("open_state")
        self.receive(self.wire, "want_open")
        self.opened = True
        self.last_open = self.dispatch("open", self.wire, deadline=self.ready_cap)
        self.receive(self.wire, "want_create")

    def arm(self, *, missing=False, effect="normal"):
        self.counts["arm_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if self.arm_used:
            self.refuse("rearm")
        if not self.opened:
            self.refuse("not_open")
        self.arm_used = True  # ARM_LATCH includes missing/failed ACK.
        if missing:
            self.refuse("missing", terminal=True)
        if self.sentinel_handle is None:
            self.new_sentinel()
        if not self.sentinel_handle.live():
            self.refuse("dead", terminal=True)
        self.dispatch(
            "arm", self.sentinel_wire, deadline=self.case.io_end, effect=effect,
        )
        self.receive(self.sentinel_wire, "arm_consumed")
        self.counts["arm_consumed"] += 1
        self.receive(self.sentinel_wire, "armed")
        self.armed = True
        self.counts["armed_acks"] += 1

    def extend(self, proposed):
        self.counts["extend_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if not number(proposed) or proposed > self.ready_cap:
            self.refuse("extension")
        self.refuse("immutable_cap")

    def create(self, *, effect="normal", partial=False, metadata_size=None):
        self.counts["create_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if self.used:
            self.refuse("spent")
        if not self.armed:
            self.refuse("not_armed")
        # SENTINEL_LIVENESS_GUARD, including death after an earlier ARMED ACK.
        if self.sentinel_handle is None or not self.sentinel_handle.live():
            self.refuse("dead", terminal=True)
        left(min(self.ready_cap, self.case.io_end))
        self.used = True  # CREATE_LATCH, before even a partial header.
        self.dispatch(
            "create", self.wire, partial=partial, deadline=self.ready_cap,
        )
        data = {"effect": effect, "pad": ""}
        if metadata_size is not None:
            data["pad"] = "x" * (metadata_size - len(dump(data)))
        payload = dump(data)
        if metadata_size is not None:
            require(len(payload) == metadata_size, "metadata_wire_size")
        try:
            self.wire.raw(payload)
            self.counts["metadata_bytes"] += len(payload)
        except (OSError, Closed, Expired, Reject) as exc:
            self.terminal = True
            raise Ambiguous(str(exc)) from exc
        self.receive(self.wire, "consumed")
        self.counts["consumed"] += 1

    def ack(self):
        self.counts["ack_calls"] += 1
        if self.terminal:
            self.refuse("terminal")
        if not self.used:
            self.refuse("not_created")
        self.receive(self.wire, "created")
        self.counts["create_acks"] += 1
        self.terminal = True

    def inject_create(self, *, overrides=None, with_metadata=True):
        """Explicit malicious-parent test traffic, not an authorized grant."""
        self.counts["injection_calls"] += 1
        self.events.append(["injection", "create", overrides or {}])
        self.wire.send("create", deadline=self.ready_cap, overrides=overrides)
        if with_metadata:
            try:
                self.wire.raw(dump({"effect": "normal", "pad": ""}))
            except (Closed, OSError) as exc:
                # The invalid header can be rejected before this second record.
                # Do not retry; still demand the worker's exact error witness.
                self.terminal = True
                self.events.append(["injection_body_closed", type(exc).__name__])

    def inject_oversize_metadata(self):
        blank = {"effect": "normal", "pad": ""}
        data = {**blank, "pad": "x" * (8193 - len(dump(blank)))}
        payload = dump(data)
        require(len(payload) == 8193, "live_oversize_serialization")
        self.inject_create(with_metadata=False)
        self.counts["oversize_header_dispatches"] += 1
        write_bytes(
            self.wire.sock, len(payload).to_bytes(4, "big"),
            self.case.io_end, self.wire.counts,
        )
        self.events.append(["oversize_metadata_header", len(payload)])

    def error(self, reason):
        frame = self.receive(self.wire, "error")
        self.terminal = True
        require(frame["reason"] == reason, "worker_error_" + reason)
        self.counts["worker_errors"] += 1
        self.events.append(["worker_error", frame["reason"]])

    def boundary(self):
        result = {
            key: self.counts[key] for key in (
                "spawn_attempts", "spawns", "ready_dispatches",
                "admission_intents", "open_dispatches", "arm_dispatches",
                "create_dispatches",
            )
        }
        result["records_attempted"] = sum(c.counts["record_attempts"] for c in self.channels)
        result["bytes"] = sum(c.counts["bytes"] for c in self.channels)
        return result

    def finish(self, code, *, dead_sentinel=False, half_close=False):
        if half_close:
            self.wire.sock.shutdown(socket.SHUT_WR)
        else:
            self.wire.sock.close()
        try:
            actual = self.worker_handle.join(self.case.io_end)
        finally:
            if half_close:
                self.wire.sock.close()
        require(actual == code, "worker_exit_" + str(actual))
        if self.sentinel_handle is not None:
            alive = self.sentinel_handle.live()
            if self.armed and not dead_sentinel:
                require(alive, "sentinel_died_during_operation")
                self.sentinel_wire.send("check")
                self.receive(self.sentinel_wire, "alive")
                self.counts["alive_after_worker_reap"] += 1
                self.sentinel_wire.send("stop")
                self.receive(self.sentinel_wire, "stopped")
                actual = self.sentinel_handle.join(self.case.io_end)
                require(actual == 0, "sentinel_exit")
            elif alive:
                raise AssertionError("unexpected_live_unarmed_sentinel")
        self.snapshot()

    def snapshot(self):
        require(self.worker_handle.reaped, "snapshot_without_worker_reap")
        names = set(os.listdir(self.root))
        require(names <= {JOURNAL, MARKER}, "unexpected_root_entries")
        journal = b""
        marker = b""
        mode = 0
        for name in sorted(names):
            fd = os.open(os.path.join(self.root, name), os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode), "nonregular_witness")
                require(info.st_nlink == 1 and info.st_size <= 4096, "witness_shape")
                content = os.read(fd, 4097)
                require(len(content) == info.st_size, "witness_short_read")
                require(stat.S_IMODE(info.st_mode) == 0o600, "witness_mode")
                if name == JOURNAL:
                    journal = content
                else:
                    marker, mode = content, stat.S_IMODE(info.st_mode)
            finally:
                os.close(fd)
        lines = journal.splitlines()
        require(all(line in (b"attempt", b"complete") for line in lines), "journal")
        self.snap = {
            "attempts": lines.count(b"attempt"),
            "completions": lines.count(b"complete"),
            "journal_file": JOURNAL in names,
            "marker": int(MARKER in names), "marker_mode": mode,
            "journal": journal.decode("ascii"),
            "marker_valid": marker == (self.session + "\n").encode("ascii"),
        }

    def expect_ops(self, count):
        require(self.snap is not None, "no_snapshot")
        require(self.snap["attempts"] == count, "attempt_count")
        require(self.snap["completions"] == count, "completion_count")
        require(self.snap["marker"] == count, "marker_count")
        require(self.snap["journal_file"] == bool(count), "journal_presence")
        if count:
            require(self.snap["journal"] == "attempt\ncomplete\n", "journal_order")
            require(self.snap["marker_valid"], "marker_content")

    def cleanup(self):
        errors = list(self.resource_errors)
        fd_failed = False
        for owned in self.processes:
            try:
                if not owned.reaped:
                    if owned.live():
                        errors.append("forced_cleanup")
                        owned.kill_join(self.case.end)
                    else:
                        require(owned.reaped, "unobserved_reap")
            except Exception as exc:
                errors.append("reap:" + type(exc).__name__)
        for sock in self.sockets:
            try:
                sock.close()
            except Exception as exc:
                errors.append("fd:" + type(exc).__name__)
                fd_failed = True
        contained = all(owned.reaped for owned in self.processes) and not fd_failed
        if self.worker_handle is not None and self.worker_handle.reaped and self.snap is None:
            try:
                self.snapshot()
            except Exception as exc:
                errors.append("snapshot:" + type(exc).__name__ + ":" + str(exc))
        if contained and self.root is not None:
            try:
                shutil.rmtree(self.root)
            except Exception as exc:
                errors.append("root:" + type(exc).__name__)
                contained = False
        if not contained:
            self.case.run.retained.append(self)  # Keep handles/root/ownership.
            errors.append("retained:" + str(self.root))
        if any(owned.code == 97 for owned in self.processes):
            errors.append("lease_exit")
        for event in self.events:
            if event[0] == "intent_before_dispatch" and event[2] is not True:
                errors.append("late_intent_latch:" + event[1])
        return {
            "fixture_root": self.root,
            "counts": dict(self.counts),
            "wire": [dict(channel.counts) for channel in self.channels],
            "exits": [owned.code for owned in self.processes],
            "reaped": [owned.reaped for owned in self.processes],
            "snapshot": self.snap, "events": self.events, "cleanup_errors": errors,
        }


class Case:
    def __init__(self, run, name, budget):
        self.run, self.name, self.budget = run, name, budget
        self.started = time.monotonic()
        self.end = min(self.started + budget, run.expiry)
        self.io_end = self.end - RESERVE
        self.fixtures = []
        self.extra = {}

    def execute(self, function):
        primary = None
        try:
            left(self.io_end)
            function(self)
        except Exception as exc:
            primary = type(exc).__name__ + ":" + str(exc)
        observations = []
        for fixture in self.fixtures:
            try:
                observations.append(fixture.cleanup())
            except Exception as exc:
                # Preserve unexpected cleanup bugs and every remaining fixture.
                self.run.retained.append(fixture)
                observations.append({
                    "cleanup_errors": ["cleanup:" + type(exc).__name__ + ":" + str(exc)],
                    "retained_root": fixture.root,
                })
        elapsed = time.monotonic() - self.started
        ok = (
            primary is None and elapsed <= self.budget
            and time.monotonic() < self.run.expiry
            and not self.run.retained
            and all(not item["cleanup_errors"] for item in observations)
        )
        result = {
            "case": self.name, "budget_s": self.budget, "elapsed_s": elapsed,
            "primary": primary, "fixtures": observations, **self.extra,
            "result": "PASS" if ok else "NONPASS",
        }
        print(json.dumps(result, sort_keys=True), flush=True)
        return ok


def refused(function, reason):
    try:
        function()
    except Reject as exc:
        require(str(exc) == reason, "refusal_" + reason + "_got_" + str(exc))
    else:
        raise AssertionError("accepted_" + reason)


def ambiguous(function):
    try:
        function()
    except Ambiguous:
        return
    raise AssertionError("expected_ambiguity")


def opened(case, *, short=False):
    fixture = Fixture(case)
    fixture.admit(short=short)
    fixture.open()
    return fixture


def c1(case):
    absent = Fixture(case, inherit=False)
    absent.finish(3)
    absent.expect_ops(0)
    source = opened(case)
    copied = source.last_open
    source.finish(4)
    source.expect_ops(0)
    target = Fixture(case)
    target.admit()
    target.receive(target.wire, "want_open")
    target.counts["copied_wire_injections"] += 1
    target.wire.raw(copied)  # Correct open kind, seq 2 and current open stage.
    target.error("session")
    target.finish(5)
    target.expect_ops(0)
    require(source.counts["open_dispatches"] == 1, "source_open")
    require(target.counts["open_dispatches"] == 0, "target_authorized_open")


def c2(case):
    fixture = opened(case)
    fixture.arm()
    wrong = "0" * 32 if fixture.session != "0" * 32 else "1" * 32
    fixture.inject_create(overrides={"session": wrong})
    fixture.error("session")
    fixture.finish(5)
    fixture.expect_ops(0)


def c3(case):
    before = opened(case)
    refused(before.create, "not_armed")
    before.finish(4)
    before.expect_ops(0)
    missing = opened(case)
    refused(lambda: missing.arm(missing=True), "missing")
    refused(missing.create, "terminal")
    missing.finish(4)
    missing.expect_ops(0)
    dead = opened(case)
    dead.new_sentinel()
    require(dead.sentinel_handle.kill_join(case.io_end) == -9, "dead_before_arm_exit")
    refused(dead.arm, "dead")
    refused(dead.create, "terminal")
    dead.finish(4)
    dead.expect_ops(0)
    after = opened(case)
    after.arm()
    require(after.sentinel_handle.kill_join(case.io_end) == -9, "dead_after_arm_exit")
    refused(after.create, "dead")
    after.finish(4, dead_sentinel=True)
    after.expect_ops(0)
    for fixture in case.fixtures:
        require(fixture.counts["create_dispatches"] == 0, "unarmed_dispatch")
    require(after.counts["armed_acks"] == 1, "earlier_real_armed_ack")


def c4(case):
    fixture = opened(case)
    fixture.arm()
    fixture.create(metadata_size=8192)
    fixture.ack()
    fixture.finish(0)
    fixture.expect_ops(1)
    expected = {
        "spawns": 2, "admission_intents": 1, "ready_dispatches": 1, "ready_acks": 1,
        "open_dispatches": 1, "arm_dispatches": 1, "arm_consumed": 1,
        "armed_acks": 1, "metadata_bytes": 8192,
        "create_dispatches": 1, "consumed": 1, "create_acks": 1,
        "alive_after_worker_reap": 1, "refusals": 0,
    }
    for key, value in expected.items():
        require(fixture.counts[key] == value, "valid_" + key)
    require(fixture.snap["marker_mode"] == 0o600, "marker_mode")
    require(fixture.sentinel_handle.reaped and fixture.sentinel_handle.code == 0, "sentinel_reap")


def decoder_checks(case, fixture):
    base = {
        "v": 1, "kind": "create", "session": fixture.session,
        "nonce": fixture.nonce, "seq": 3, "deadline": fixture.ready_cap,
    }
    checks = []

    def bad_header(label, payload, reason):
        refused(
            lambda: decode(
                payload, {"create"}, fixture.session, fixture.nonce,
                2, fixture.ready_cap,
            ),
            reason,
        )
        checks.append(label)

    blank = {"effect": "normal", "pad": ""}
    exact = {"effect": "normal", "pad": "x" * (LIMIT - len(dump(blank)))}
    exact_wire = dump(exact)
    require(len(exact_wire) == 8192, "exact_metadata_length")
    require(metadata(exact_wire) == exact, "exact_metadata_accept")
    larger = dump({**exact, "pad": exact["pad"] + "x"})
    require(len(larger) == 8193, "oversize_metadata_length")
    refused(lambda: metadata(larger), "size")
    for key, value, reason in (
        ("seq", True, "sequence"), ("v", True, "version"),
        ("deadline", True, "deadline"), ("extra", 1, "fields"),
        ("kind", "open", "kind"),
    ):
        bad_header("header_" + key, dump({**base, key: value}), reason)
    bad_header("wrong_direction", dump({**base, "kind": "want_create"}), "kind")
    wire = dump(base)
    bad_header("duplicate", wire.replace(b'"seq":3', b'"seq":3,"seq":3'), "duplicate")
    deadline_token = dump(base["deadline"])
    for label, token in (
        ("nan", b"NaN"), ("infinity", b"Infinity"),
        ("negative_infinity", b"-Infinity"), ("overflow", b"1e9999"),
    ):
        bad_header(label, wire.replace(deadline_token, token), "nonfinite")
    refused(lambda: metadata(dump({**blank, "extra": 1})), "metadata_fields")
    refused(lambda: metadata(b'{"effect":"normal","pad":"","pad":""}'), "duplicate")
    case.extra["decoder_checks"] = checks + [
        "metadata_8192_accept", "metadata_8193_refuse",
        "metadata_extra", "metadata_duplicate",
    ]


def c5(case):
    for sequence in (2, 1):
        fixture = opened(case)
        fixture.inject_create(overrides={"seq": sequence}, with_metadata=False)
        fixture.error("sequence")
        fixture.finish(5)
        fixture.expect_ops(0)
    oversized = opened(case)
    oversized.inject_oversize_metadata()
    oversized.error("size")
    oversized.finish(5)
    oversized.expect_ops(0)
    decoder_checks(case, oversized)


def c6(case):
    fixture = opened(case)
    fixture.arm()
    boundary = fixture.boundary()
    refusals_before = fixture.counts["refusals"]
    calls = sum(fixture.counts[key] for key in ("admit_calls", "arm_calls", "extend_calls"))
    refused(fixture.admit, "second_admission")
    refused(fixture.arm, "rearm")
    extension = fixture.ready_cap + 0.01
    require(extension < case.run.expiry, "extension_inside_global_lease")
    refused(lambda: fixture.extend(extension), "extension")
    after = fixture.boundary()
    require(after == boundary, "repeat_dispatch_delta")
    require(fixture.counts["refusals"] - refusals_before == 3, "three_repeat_refusals")
    case.extra["repeat_boundary_delta"] = {
        key: after[key] - value for key, value in boundary.items()
    }
    require(
        sum(fixture.counts[key] for key in ("admit_calls", "arm_calls", "extend_calls")) - calls == 3,
        "three_actual_repeat_calls",
    )
    fixture.inject_create(overrides={"deadline": extension}, with_metadata=False)
    fixture.error("extension")
    fixture.finish(5)
    fixture.expect_ops(0)
    expiry = opened(case, short=True)
    expiry.arm()
    expiry.create(effect="expiry")
    ambiguous(expiry.ack)
    expiry.finish(8)
    expiry.expect_ops(0)
    require(expiry.counts["consumed"] == 1, "valid_permit_before_expiry")


def prohibited_second_calls(fixture):
    boundary = fixture.boundary()
    refusals = fixture.counts["refusals"]
    calls_before = sum(fixture.counts[key] for key in (
        "admit_calls", "open_calls", "create_calls", "arm_calls", "spawn_worker_calls",
    ))
    for function in (
        fixture.admit, fixture.open, fixture.create, fixture.arm, fixture.spawn_worker,
    ):
        refused(function, "terminal")
    after = fixture.boundary()
    calls_after = sum(fixture.counts[key] for key in (
        "admit_calls", "open_calls", "create_calls", "arm_calls", "spawn_worker_calls",
    ))
    require(after == boundary, "ambiguity_boundary_changed")
    require(fixture.counts["refusals"] - refusals == 5, "five_repeat_refusals")
    require(calls_after - calls_before == 5, "five_actual_repeat_calls")
    fixture.events.append([
        "observed_second_call_delta",
        {key: after[key] - value for key, value in boundary.items()},
        {"calls": calls_after - calls_before, "refusals": fixture.counts["refusals"] - refusals},
    ])


def joined_second_calls(fixture):
    """Observe operation deltas only when both snapshots follow actual reap."""
    require(fixture.worker_handle.reaped, "repeat_snapshot_without_reap")
    before = dict(fixture.snap)
    prohibited_second_calls(fixture)
    fixture.snapshot()
    require(fixture.snap == before, "post_reap_operation_delta")
    fixture.events.append([
        "observed_post_reap_operation_delta",
        {
            key: fixture.snap[key] - before[key]
            for key in ("attempts", "completions", "marker")
        },
    ])


def c7(case):
    admission = Fixture(case)
    ambiguous(lambda: admission.admit(partial=True))
    require(admission.wire.counts["bytes"] == 9, "partial_ready_bytes")
    prohibited_second_calls(admission)
    admission.finish(4, half_close=True)
    admission.expect_ops(0)
    joined_second_calls(admission)

    partial = opened(case)
    partial.arm()
    previous = partial.wire.counts["bytes"]
    ambiguous(lambda: partial.create(partial=True))
    require(partial.wire.counts["bytes"] - previous == 9, "partial_create_bytes")
    prohibited_second_calls(partial)
    partial.finish(4)
    partial.expect_ops(0)
    joined_second_calls(partial)

    arm = opened(case)
    ambiguous(lambda: arm.arm(effect="lost_ack"))
    prohibited_second_calls(arm)
    require(arm.sentinel_handle.join(case.io_end) == 4, "sentinel_consumed_lost_ack")
    arm.finish(4)
    arm.expect_ops(0)
    joined_second_calls(arm)
    require(arm.counts["arm_consumed"] == 1, "real_arm_consumed_notice")

    lost = opened(case)
    lost.arm()
    lost.create(effect="lost_ack")
    ambiguous(lost.ack)
    prohibited_second_calls(lost)
    lost.finish(4)
    lost.expect_ops(1)
    joined_second_calls(lost)

    disconnect = opened(case)
    disconnect.arm()
    disconnect.create(effect="disconnect")
    ambiguous(disconnect.ack)
    prohibited_second_calls(disconnect)
    disconnect.finish(4)
    disconnect.expect_ops(0)
    joined_second_calls(disconnect)
    for fixture in (lost, disconnect):
        require(fixture.counts["consumed"] == 1, "actual_consumed_notice")
        require(fixture.counts["create_acks"] == 0, "no_create_ack")
    case.extra["ambiguity_variants"] = [
        "partial_ready", "partial_create", "lost_arm_ack",
        "full_delivery_lost_create_ack", "disconnect_after_consumed",
    ]


CASES = (
    ("C1_absent_and_copied_wire", 1.00, c1),
    ("C2_wrong_session_create", 0.50, c2),
    ("C3_unarmed_missing_dead", 1.25, c3),
    ("C4_one_live_operation", 2.00, c4),
    ("C5_sequence_and_exact_metadata", 0.50, c5),
    ("C6_one_use_and_ready_expiry", 0.75, c6),
    ("C7_terminal_ambiguities", 1.75, c7),
)


def harness():
    run = Run()
    accepted = []
    for name, budget, function in CASES:
        accepted.append(Case(run, name, budget).execute(function))
    elapsed = time.monotonic() - run.started
    ok = all(accepted) and elapsed < 8.0 and not run.retained
    print(json.dumps({
        "total_elapsed_s": elapsed, "total_gate_s": 8.0,
        "external_parent_cap_s": 10.0,
        "retained_roots": [fixture.root for fixture in run.retained],
        "result": "PASS" if ok else "NONPASS",
    }, sort_keys=True), flush=True)
    return 0 if ok else 1


def main():
    if len(sys.argv) == 1:
        return harness()
    if len(sys.argv) == 7 and sys.argv[1] in ("--worker", "--sentinel"):
        return child_main(sys.argv)
    return 2


if __name__ == "__main__":
    sys.exit(main())
