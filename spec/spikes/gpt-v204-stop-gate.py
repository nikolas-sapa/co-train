#!/usr/bin/env python3
"""SOURCEONLY UNRUN. Fixed local exec/custody probe, not a production stop API.

PROVES is planned until parent execution/review. SHORTCUT: trusted same-user
children, marker command, Python timer fallback, unbounded OS/startup syscalls.
MISSING: production authority, watchdog/SDK/provider/native/science evidence.
"""

import collections
import json
import math
import os
import secrets
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

RETAINED = []  # Actual failed owner objects, never only path strings.
ROLES = {"worker", "controller", "gate"}
FACTS = {"pid", "pgid", "sid", "stage", "pulse_alive", "ticks", "term_ignored"}
BASE = {"v", "kind", "nonce", "seq"}
SCHEMA = {
    "ready": FACTS, "armed": FACTS, "started": FACTS | {"via"},
    "challenge": {"ticket"}, "alive": FACTS | {"ticket"},
    "fire": set(), "trigger": set(), "fired": {"fires"}, "quit": set(),
}
LIMIT = 4096


def check(value, reason):
    if not value:
        raise ValueError(reason)


def remaining(end):
    value = end - time.monotonic()
    if value <= 0:
        raise TimeoutError("expired")
    return value


def encode(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()


def pairs(items):
    result = {}
    for key, value in items:
        check(key not in result, "duplicate")
        result[key] = value
    return result


def nonfinite(_value):
    raise ValueError("noninteger_number")


def decode(data):
    check(0 < len(data) <= LIMIT, "size")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=nonfinite)


def token(value):
    return type(value) is str and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def exact(sock, count, end, clean=False):
    data = bytearray()
    while len(data) < count:
        ready, _, _ = select.select([sock], [], [], remaining(end))
        check(bool(ready), "read_timeout")
        try:
            chunk = sock.recv(count - len(data))
        except (BlockingIOError, InterruptedError):
            continue
        if not chunk:
            if clean and not data:
                raise EOFError("clean_eof")
            raise ValueError("truncated")
        data.extend(chunk)
    return bytes(data)


class Channel:
    def __init__(self, sock, nonce, tx=0, rx=0):
        self.sock, self.nonce, self.tx, self.rx = sock, nonce, tx, rx
        self.bytes = self.records = 0
        sock.setblocking(False)

    def send(self, kind, end, **fields):
        self.tx += 1
        payload = encode({"v": 1, "kind": kind, "nonce": self.nonce, "seq": self.tx, **fields})
        check(len(payload) <= LIMIT, "size")
        wire = len(payload).to_bytes(4, "big") + payload
        sent = 0
        while sent < len(wire):
            _, ready, _ = select.select([], [self.sock], [], remaining(end))
            check(bool(ready), "write_timeout")
            try:
                count = self.sock.send(wire[sent:])
            except (BlockingIOError, InterruptedError):
                continue
            check(count > 0, "closed_write")
            sent += count
            self.bytes += count
        self.records += 1

    def read(self, kinds, end):
        size = int.from_bytes(exact(self.sock, 4, end, clean=True), "big")
        check(0 < size <= LIMIT, "size")
        value = decode(exact(self.sock, size, end))
        check(type(value) is dict, "object")
        kind = value.get("kind")
        check(type(kind) is str and kind in kinds and kind in SCHEMA, "kind")
        check(set(value) == BASE | SCHEMA[kind], "fields")
        check(type(value["v"]) is int and value["v"] == 1, "version")
        check(value["nonce"] == self.nonce, "nonce")
        check(type(value["seq"]) is int and value["seq"] == self.rx + 1, "sequence")
        for key in ("pid", "pgid", "sid", "ticks", "fires"):
            if key in value:
                check(type(value[key]) is int and value[key] >= (0 if key == "ticks" else 1), key)
        for key in ("pulse_alive", "term_ignored"):
            if key in value:
                check(type(value[key]) is bool, key)
        if "stage" in value:
            check(value["stage"] in (*ROLES, "command"), "stage")
        if "ticket" in value:
            check(token(value["ticket"]), "ticket")
        if "via" in value:
            check(value["via"] in ("trigger", "eof"), "via")
        self.rx = value["seq"]
        return value


def lease(expiry):
    delay = remaining(expiry)
    check(math.isfinite(expiry) and delay <= 8.0, "lease")
    timer = threading.Timer(delay, lambda: os._exit(97))
    timer.daemon = True
    timer.start()


class Pulse:
    def __init__(self, end):
        self.ticks = 0
        ready = threading.Event()

        def heartbeat():
            while True:
                self.ticks += 1
                ready.set()
                time.sleep(0.002)

        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()
        check(ready.wait(timeout=min(remaining(end), 0.5)), "pulse_start")


def facts(stage, pulse):
    return {
        "pid": os.getpid(), "pgid": os.getpgrp(), "sid": os.getsid(0), "stage": stage,
        "pulse_alive": pulse is not None and pulse.thread.is_alive(),
        "ticks": pulse.ticks if pulse is not None else 0,
        "term_ignored": signal.getsignal(signal.SIGTERM) == signal.SIG_IGN,
    }


def write_witness(root, name, value, end, append=False):
    remaining(end)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        check(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "private_root")
        remaining(end)
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if append else os.O_EXCL)
        fd = os.open(name, flags, 0o600, dir_fd=directory)
        try:
            os.fchmod(fd, 0o600)
            data = encode(value) + b"\n"
            check(os.write(fd, data) == len(data), "short_witness")
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def journal(root, event, nonce, via, end):
    write_witness(root, "journal", {
        "event": event, "pid": os.getpid(), "nonce": nonce, "via": via,
    }, end, append=True)


def child(argv):
    expiry = float(argv[4])
    if not math.isfinite(expiry) or expiry <= time.monotonic():
        os._exit(97)
    lease(expiry)  # Before channel I/O; command re-arms this SAME absolute value.
    mode, fd, aux = argv[1][2:], int(argv[2]), int(argv[3])
    end, root, nonce, profile = float(argv[5]), argv[6], argv[7], argv[8]
    tx, rx, via = int(argv[9]), int(argv[10]), argv[11]
    check(math.isfinite(end) and 0 < end <= expiry, "case_deadline")
    check(token(nonce) and profile in ("0", "1") and tx >= 0 and rx >= 0, "argv")
    check(os.path.isabs(root) and os.path.normpath(root) == root, "root")
    check((mode in ("controller", "gate") and aux >= 3) or
          (mode in ("worker", "command") and aux == -1), "aux")
    check((mode == "command" and via in ("trigger", "eof")) or
          (mode != "command" and via == "pending" and tx == rx == 0), "stage")
    resistant = mode == "worker" or (mode == "command" and profile == "1")
    signal.signal(signal.SIGTERM, signal.SIG_IGN if resistant else signal.SIG_DFL)
    pulse = Pulse(end) if resistant else None
    link = Channel(socket.socket(fileno=fd), nonce, tx, rx)
    trigger = Channel(socket.socket(fileno=aux), nonce) if aux >= 3 else None
    if mode == "command":
        journal(root, "command", nonce, via, end)
        write_witness(root, "marker", {"pid": os.getpid(), "nonce": nonce, "via": via}, end)
        journal(root, "marker", nonce, via, end)
        link.send("started", end, **facts(mode, pulse), via=via)
        if not resistant:
            return 0
    else:
        link.send("armed" if mode == "gate" else "ready", end, **facts(mode, pulse))
    fires = 0
    while True:
        if mode == "gate":
            ready, _, _ = select.select([link.sock, trigger.sock], [], [], remaining(end))
            check(bool(ready), "gate_timeout")
            if trigger.sock in ready:
                try:
                    trigger.read({"trigger"}, end)
                    via = "trigger"
                except EOFError:  # Only clean record-boundary EOF, not truncation.
                    via = "eof"
                remaining(end)
                journal(root, "exec", nonce, via, end)
                trigger.sock.close()
                os.set_inheritable(link.sock.fileno(), True)
                # Only the parent channel application FD survives the fixed exec.
                target = [
                    sys.executable, "-I", "-S", "-B", os.path.abspath(__file__),
                    "--command", str(link.sock.fileno()), "-1", repr(expiry), repr(end),
                    root, nonce, profile, str(link.tx), str(link.rx), via,
                ]
                remaining(end)
                os.execve(sys.executable, target, {
                    "PATH": "/usr/bin:/bin", "TMPDIR": os.path.dirname(root),
                })
                raise RuntimeError("exec_returned")
            if link.sock not in ready:
                continue
        allowed = {"challenge"}
        if mode == "controller":
            allowed.add("quit" if fires else "fire")
        frame = link.read(allowed, end)
        if frame["kind"] == "challenge":
            link.send("alive", end, ticket=frame["ticket"], **facts(mode, pulse))
        elif frame["kind"] == "fire":
            fires += 1  # One-use latch before dispatch bytes; stay alive afterward.
            trigger.send("trigger", end)
            journal(root, "fire", nonce, "trigger", end)
            link.send("fired", end, fires=fires)
            # CONTROLLER_STAYS_ALIVE: parent red control inserts return 0 here.
        else:
            return 0  # Controller quit is the only graceful loop exit.


class Run:
    def __init__(self):
        self.started = time.monotonic()
        self.expiry = self.started + 8.0
        self.base = None
        self.owners = []
        self.attempts = self.successes = 0
        self.errors = []
        self.times = {}
        self.released = False


class Fixture:
    def __init__(self, run, number):
        self.run, self.number = run, number
        self.started = time.monotonic()
        self.end = min(run.expiry, self.started + 2.5)
        self.io_end = self.end - 0.25
        self.ps, self.codes, self.links = {}, {}, {}
        self.sockets, self.events, self.errors = [], [], []
        self.times, self.snapshot = {}, None
        self.root = self.primary = self.original_gate = None
        self.attempts = self.successes = self.fire_dispatches = 0
        self.started_replies = self.arm_acks = 0
        self.disposed = False
        self.trigger_copies = None
        self.nonce = secrets.token_hex(16)
        run.owners.append(self)

    def op(self, label, cap, action, enclosing=None, cleanup=False):
        start = time.monotonic()
        bound = self.end if cleanup else self.io_end
        end = min(bound, start + cap, bound if enclosing is None else enclosing)
        remaining(end)
        try:
            value = action(end)
        finally:
            elapsed = time.monotonic() - start
            self.times[label] = {"seconds": elapsed, "limit": cap}
        check(elapsed <= cap and time.monotonic() <= end, label + "_time")
        return value

    def close(self, *sockets):
        for sock in sockets:
            if sock is not None:
                try:
                    sock.close()
                except Exception as exc:
                    self.errors.append("fd:" + repr(exc))

    def pair(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sockets.extend((a, b))
        a.setblocking(False)
        b.setblocking(False)
        return a, b

    def spawn(self, role, parent_end, child_end, aux=None):
        self.links[role] = Channel(parent_end, self.nonce)

        def perform(end):
            fds = (child_end.fileno(),) + (() if aux is None else (aux.fileno(),))
            argv = [
                sys.executable, "-I", "-S", "-B", os.path.abspath(__file__), "--" + role,
                str(child_end.fileno()), str(-1 if aux is None else aux.fileno()),
                repr(self.run.expiry), repr(self.io_end), self.root, self.nonce,
                "1" if self.number == 3 else "0", "0", "0", "pending",
            ]
            try:
                remaining(end)  # Immediately before this actual Popen boundary.
                self.attempts += 1
                self.run.attempts += 1
                handle = subprocess.Popen(
                    argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True, pass_fds=fds,
                    start_new_session=True, env={"PATH": "/usr/bin:/bin", "TMPDIR": self.run.base},
                )
                self.ps[role] = handle  # Retain custody before any wait or closure.
                self.successes += 1
                self.run.successes += 1
            finally:
                self.close(child_end, aux)
        self.op("spawn_" + role, 2.0, perform)

    def validate(self, frame, role, stage):
        expected = self.ps[role].pid
        check(frame["pid"] == frame["pgid"] == frame["sid"] == expected, "identity")
        check(frame["stage"] == stage, "stage")
        resistant = stage == "worker" or (stage == "command" and self.number == 3)
        check(frame["pulse_alive"] == frame["term_ignored"] == resistant, "resistance")
        check(frame["ticks"] > 0 if resistant else frame["ticks"] == 0, "heartbeat")
        self.events.append(frame)

    def build(self):
        remaining(self.io_end)
        check(self.run.base is not None, "base_unavailable")

        def create_root(end):
            remaining(end)
            self.root = tempfile.mkdtemp(prefix="case-", dir=self.run.base)
            os.chmod(self.root, 0o700)
        self.op("create_root", 2.0, create_root)
        ctrl, gate = self.pair()
        for role, aux in (("worker", None), ("controller", ctrl), ("gate", gate)):
            parent_end, child_end = self.pair()
            self.spawn(role, parent_end, child_end, aux)
        self.original_gate = self.ps["gate"]
        self.trigger_copies = sum(sock.fileno() >= 0 for sock in (ctrl, gate))
        check(self.trigger_copies == 0 and self.attempts == self.successes == 3, "topology")
        check(len({handle.pid for handle in self.ps.values()}) == 3, "distinct_groups")
        for role in ("worker", "controller", "gate"):
            kind = "armed" if role == "gate" else "ready"
            frame = self.op("initial_" + role, 2.0, lambda end: self.links[role].read({kind}, end))
            self.validate(frame, role, role)
            self.arm_acks += int(kind == "armed")

    def live(self, role):
        if role in self.codes:
            return False
        handle = self.ps[role]
        if handle.poll() is None:
            return True
        self.record_exit(role, handle.wait(timeout=0))
        return False

    def record_exit(self, role, code):
        check(type(code) is int and self.ps[role].returncode == code, "unobserved_reap")
        self.codes[role] = code

    def join(self, role, end, cleanup=False):
        if role not in self.codes:
            delay = end - time.monotonic()
            if delay <= 0 and not cleanup:
                raise TimeoutError("join_expired")
            code = self.ps[role].wait(timeout=delay if delay > 0 else 0)
            self.record_exit(role, code)
        return self.codes[role]

    def send_signal(self, role, sig):
        if not self.live(role):
            return False
        # Signal target ONLY from this retained, unreaped, new-session Popen.
        target = self.ps[role].pid
        self.events.append({"signal_role": role, "signal": int(sig), "owned_pgid": target})
        os.killpg(target, sig)
        return True

    def challenge(self, role, stage, label, enclosing=None):
        ticket = secrets.token_hex(16)

        def perform(end):
            self.links[role].send("challenge", end, ticket=ticket)
            frame = self.links[role].read({"alive"}, end)
            check(frame["ticket"] == ticket, "fresh_challenge")
            self.validate(frame, role, stage)
        self.op(label, 0.5, perform, enclosing)

    def kill(self, role):
        def perform(end):
            check(self.send_signal(role, signal.SIGKILL), "kill_already_exited")
            check(self.join(role, end) == -9, "kill_exit")
        self.op("kill_" + role, 1.0, perform)

    def stop(self, role, stage):
        def perform(end):
            check(self.send_signal(role, signal.SIGTERM), "term_already_exited")
            self.challenge(role, stage, "after_TERM_" + role, end)
            check(self.send_signal(role, signal.SIGKILL), "not_term_resistant")
            check(self.join(role, end) == -9, "stop_exit")
        self.op("stop_" + role, 1.0, perform)

    def started_command(self, via, end):
        frame = self.links["gate"].read({"started"}, end)
        self.started_replies += 1
        self.validate(frame, "gate", "command")
        check(frame["via"] == via, "exec_cause")

    def fire(self):
        def perform(end):
            check(self.fire_dispatches == 0, "second_fire")
            self.fire_dispatches += 1
            self.links["controller"].send("fire", end)
            frame = self.links["controller"].read({"fired"}, end)
            check(frame["fires"] == 1, "trigger_count")
            self.events.append(frame)
            self.started_command("trigger", end)
        self.op("fire_to_started", 2.0, perform)

    def normal_join(self, role):
        self.op("join_" + role, 2.0, lambda end: check(self.join(role, end) == 0, "normal_exit"))

    def scenario(self):
        if self.number == 1:
            self.stop("worker", "worker")
            self.challenge("controller", "controller", "controller_after_worker")
            self.challenge("gate", "gate", "gate_after_worker")
            self.fire()
            self.normal_join("gate")
            self.challenge("controller", "controller", "controller_after_fire")
            check(self.live("controller"), "controller_not_alive_until_quit")

            def quit_controller(end):
                self.links["controller"].send("quit", end)
                check(self.join("controller", end) == 0, "controller_quit")
            self.op("quit_controller", 2.0, quit_controller)
        elif self.number == 2:
            self.challenge("controller", "controller", "controller_before_kill")
            self.challenge("gate", "gate", "gate_before_eof")
            self.kill("controller")
            self.op("eof_to_started", 2.0, lambda end: self.started_command("eof", end))
            self.normal_join("gate")
            self.stop("worker", "worker")
        else:
            self.fire()
            self.challenge("controller", "controller", "controller_during_command")
            check(self.live("controller"), "controller_dead_before_intentional_kill")
            self.kill("controller")
            self.stop("worker", "worker")
            self.challenge("gate", "command", "command_after_other_groups")
            self.stop("gate", "command")
        check(self.ps["gate"] is self.original_gate, "gate_handle_replaced")
        check(self.attempts == self.successes == 3 and self.arm_acks == self.started_replies == 1, "counts")

    def observe_witnesses(self, end):
        check(set(self.ps) == set(self.codes) == ROLES, "snapshot_without_three_reaps")
        check(all(type(code) is int and self.ps[role].returncode == code
                  for role, code in self.codes.items()), "snapshot_unobserved_exit")
        remaining(end)
        names = set(os.listdir(self.root))
        check(names == {"journal", "marker"}, "witness_names")
        data, modes = {}, {}
        for name in names:
            remaining(end)
            fd = os.open(os.path.join(self.root, name), os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                modes[name] = stat.S_IMODE(info.st_mode)
                check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid() and
                      stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= LIMIT, "witness_stat")
                body = os.read(fd, LIMIT + 1)
                check(len(body) == info.st_size, "witness_read")
                data[name] = [decode(line) for line in body.splitlines()]
            finally:
                os.close(fd)
        rows, markers = data["journal"], data["marker"]
        check(all(type(row) is dict for row in rows + markers), "witness_objects")
        counts = collections.Counter(row.get("event") for row in rows)
        self.snapshot = {
            "journal_counts": dict(counts), "markers": sum(name == "marker" for name in names),
            "marker_lines": len(markers), "marker": markers, "modes": modes,
        }
        expected_fire = int(self.number != 2)
        check(counts == {"exec": 1, "command": 1, "marker": 1, **({"fire": 1} if expected_fire else {})}, "journal_counts")
        via = "eof" if self.number == 2 else "trigger"
        for row in rows:
            check(set(row) == {"event", "pid", "nonce", "via"}, "journal_schema")
            role = "controller" if row["event"] == "fire" else "gate"
            check(type(row["pid"]) is int and row["pid"] == self.ps[role].pid and
                  row["nonce"] == self.nonce and row["via"] == via, "journal_identity")
        check([row["event"] for row in rows if row["event"] != "fire"] ==
              ["exec", "command", "marker"], "exec_order")
        check(len(markers) == 1 and type(markers[0].get("pid")) is int, "marker_count_type")
        check(markers == [{"pid": self.original_gate.pid, "nonce": self.nonce, "via": via}], "marker_identity")

    def cleanup(self):
        cleanup_start = time.monotonic()
        cleanup_end = min(self.end, cleanup_start + 1.0)  # Shared by ALL owned reaps.
        for role in ("gate", "controller", "worker"):
            if role not in self.ps:
                continue
            try:
                if self.live(role):
                    self.errors.append("forced_cleanup:" + role)
                    self.send_signal(role, signal.SIGKILL)
                    self.join(role, cleanup_end, cleanup=True)
            except Exception as exc:
                self.errors.append("reap:" + role + ":" + repr(exc))
        self.close(*self.sockets)  # Every FD attempted independently.
        elapsed = time.monotonic() - cleanup_start
        self.times["containment_and_fd_cleanup"] = {"seconds": elapsed, "limit": 1.0}
        if elapsed > 1.0 or time.monotonic() > self.end:
            self.errors.append("cleanup_time")
        if set(self.ps) != ROLES or set(self.codes) != ROLES:
            self.errors.append("unproved_three_reaps")
        if 97 in self.codes.values():
            self.errors.append("lease_exit")
        if not self.errors:
            try:
                def release(end):
                    self.observe_witnesses(end)
                    remaining(end)
                    shutil.rmtree(self.root)
                    self.disposed = True
                self.op("witness_and_root_release", 2.0, release, cleanup=True)
            except Exception as exc:
                self.errors.append("witness_or_release:" + repr(exc))
        if not self.disposed:
            RETAINED.append(self)

    def execute(self):
        try:
            self.build()
            self.scenario()
        except Exception as exc:
            self.primary = repr(exc)
        finally:
            try:
                self.cleanup()
            except Exception as exc:
                self.errors.append("cleanup_crash:" + repr(exc))
                RETAINED.append(self)
        elapsed = time.monotonic() - self.started  # AFTER all fixture teardown.
        ok = self.primary is None and not self.errors and self.disposed and elapsed <= 2.5
        return {
            "case": ("C1_normal_original_handle", "C2_controller_eof_original_handle",
                     "C3_controller_dies_during_resistant_command")[self.number - 1],
            "result": "PASS" if ok else "NONPASS", "elapsed_s": elapsed, "limit_s": 2.5,
            "primary": self.primary, "cleanup_errors": self.errors, "reaps": self.codes,
            "popen_attempts": self.attempts, "popen_successes": self.successes,
            "fire_dispatches": self.fire_dispatches, "started_replies": self.started_replies,
            "arm_acks": self.arm_acks, "times": self.times, "events": self.events,
            "snapshot": self.snapshot, "root_released": self.disposed,
            "trigger_parent_copies": self.trigger_copies,
            "owned_pids": {role: handle.pid for role, handle in self.ps.items()},
            "original_gate_handle": self.original_gate is not None and self.ps.get("gate") is self.original_gate,
            "wire": {role: {"bytes": link.bytes, "records": link.records}
                     for role, link in self.links.items()},
        }


def harness():
    run = Run()
    results = []
    try:
        start = time.monotonic()
        bound = min(run.expiry, start + 2.0)
        try:
            remaining(bound)
            run.base = tempfile.mkdtemp(prefix="gpt-v204-")  # Parent TMPDIR selection.
            os.chmod(run.base, 0o700)
        finally:
            run.times["base_create"] = time.monotonic() - start
        remaining(bound)
        for number in (1, 2, 3):
            result = Fixture(run, number).execute()
            results.append(result)
            print(json.dumps(result, sort_keys=True), flush=True)
    except Exception as exc:
        run.errors.append("harness:" + repr(exc))
    finally:
        try:
            check(not RETAINED and all(owner.disposed for owner in run.owners), "retained_owners")
            check(len(results) == 3 and run.base is not None, "incomplete_run")
            start = time.monotonic()
            bound = min(run.expiry, start + 2.0)
            try:
                remaining(bound)
                shutil.rmtree(run.base)
                run.released = True
            finally:
                run.times["base_release"] = time.monotonic() - start
            remaining(bound)
        except Exception as exc:
            run.errors.append("base:" + repr(exc))
            RETAINED.append(run)
    elapsed = time.monotonic() - run.started  # AFTER base removal, unrounded.
    ok = (len(results) == 3 and all(r["result"] == "PASS" for r in results) and
          run.attempts == run.successes == 9 and run.released and
          not RETAINED and not run.errors and elapsed < 8.0)
    print(json.dumps({
        "result": "PASS" if ok else "NONPASS", "total_elapsed_s": elapsed, "limit_s": 8.0,
        "popen_attempts": run.attempts, "popen_successes": run.successes,
        "base_released": run.released, "errors": run.errors, "retained_objects": len(RETAINED),
        "base_times_s": run.times,
        "retained_roots": [owner.root for owner in RETAINED if isinstance(owner, Fixture)],
        "retained_base": run.base if not run.released else None, "external_parent_cap_s": 10.0,
    }, sort_keys=True), flush=True)
    return 0 if ok else 1


def main():
    if len(sys.argv) == 1:
        return harness()
    if len(sys.argv) == 12 and sys.argv[1] in ("--worker", "--controller", "--gate", "--command"):
        try:
            return child(sys.argv)
        except Exception:
            return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
