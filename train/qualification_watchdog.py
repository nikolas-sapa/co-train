"""Trusted-host local teardown requests, never remote cleanup/billing proof.

Deadlines bound cooperative waits, not OS-blocking Popen or scheduling stalls.
A blocked launch remains UNKNOWN; a returned launch overrun is recorded UNKNOWN.
Hard local bounds require a stronger external supervisor and responsive OS,
including bounded process creation, signalling and reaping. No remote guarantee.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from typing import TypeVar


_WIRE_LIMIT = 16384
_OUTPUT_LIMIT = 4096
_REAP_SECONDS = 0.5
_REQUEST_ON_FINISH = True
_ARM_LOCK = threading.Lock()
_ARMED_APP_IDS: set[str] = set()
_T = TypeVar("_T")


def _seconds(value: object, maximum: float) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 < value <= maximum)


class TrustedTeardown:
    """Host-audited executable; stdin identity, no argv credentials or shell."""

    def __init__(
        self, executable: Path, environment: Mapping[str, str], *,
        explicitly_trusted: bool,
    ) -> None:
        if explicitly_trusted is not True:
            raise ValueError("explicit trusted teardown authority required")
        if not isinstance(executable, Path) or not executable.is_absolute():
            raise ValueError("absolute trusted teardown executable required")
        info = executable.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022 or not os.access(executable, os.X_OK)):
            raise ValueError("trusted executable must be owned, regular and non-writable by others")
        copied = dict(environment)
        if any(
            type(key) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
            or type(value) is not str or "\0" in value
            for key, value in copied.items()
        ):
            raise ValueError("explicit string environment required")
        if len(json.dumps(copied).encode("utf-8")) > 8192:
            raise ValueError("explicit teardown environment too large")
        self._executable = str(executable)
        self._environment = tuple(copied.items())


def _signal_owned_group(process: subprocess.Popen) -> bool:
    # No poll here: a leader reaped by this owner must never be signalled again.
    if process.returncode is not None:
        return False
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return False
    return True


def _command_result() -> dict:
    return {
        "attempted": False, "returncode": None, "timed_out": False,
        "launch_overrun": False,
        "leader_reaped": False, "signal_sent": False,
        "output_bytes": 0, "output_truncated": False, "error": None,
    }


def _bounded_command(
    teardown: TrustedTeardown, app_id: str, timeout: float, deadline: float,
) -> dict:
    result = _command_result()
    end = min(time.monotonic() + timeout, deadline - _REAP_SECONDS)
    if time.monotonic() >= end:
        result["timed_out"] = True
        result["error"] = "local_deadline_exhausted"
        return result
    process = None
    selector = selectors.DefaultSelector()
    try:
        if time.monotonic() >= end:
            result["timed_out"] = True
            result["error"] = "local_deadline_exhausted"
            return result
        result["attempted"] = True
        process = subprocess.Popen(
            [teardown._executable], env=dict(teardown._environment),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True, bufsize=0,
        )
        if time.monotonic() >= end:
            result["launch_overrun"] = result["timed_out"] = True
            result["error"] = "local_launch_deadline_unknown"
            raise TimeoutError("local launch exceeded command deadline")
        payload = json.dumps({"action": "stop_owned_app", "app_id": app_id}).encode("ascii")
        os.set_blocking(process.stdin.fileno(), False)
        process.stdin.write(payload)
        process.stdin.close()
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                result["timed_out"] = True
                break
            # A fresh poll reaps only this leader. Never wait on inherited EOF.
            if process.poll() is not None:
                break
            for key, _ in selector.select(min(0.02, remaining)):
                block = os.read(key.fd, 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                count = result["output_bytes"] + len(block)
                result["output_truncated"] |= count > _OUTPUT_LIMIT
                result["output_bytes"] = min(_OUTPUT_LIMIT, count)
    except BaseException:
        # Never serialize exception messages, command output, identity or env.
        if process is None and result["attempted"] and time.monotonic() >= end:
            result["launch_overrun"] = result["timed_out"] = True
            result["error"] = "local_launch_deadline_unknown"
        else:
            result["error"] = result["error"] or "local_command_error"
    finally:
        try:
            selector.close()
        except BaseException:
            result["error"] = result["error"] or "local_selector_close_error"
        if process is not None:
            if process.returncode is None:
                try:
                    result["signal_sent"] = _signal_owned_group(process)
                except BaseException:
                    result["error"] = "local_signal_error"
            try:
                process.wait(timeout=max(0, min(_REAP_SECONDS, deadline - time.monotonic())))
                result["leader_reaped"] = True
                result["returncode"] = process.returncode
            except BaseException:
                result["error"] = "local_reap_unknown"
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        result["error"] = result["error"] or "local_close_error"
    if time.monotonic() >= deadline:
        result["error"] = result["error"] or "local_deadline_unknown"
    return result


def _write_event(fd: int, event: dict) -> None:
    wire = json.dumps(event, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
    if len(wire) > _OUTPUT_LIMIT:
        raise ValueError("bounded evidence event required")
    if os.write(fd, wire) != len(wire):
        raise OSError("short evidence write")


def _result(reason: str, command: dict) -> dict:
    return {
        "event": "result", "reason": reason, "teardown": command,
        "remote": "UNKNOWN", "billing": "UNKNOWN",
        "local_ok": (
            command["attempted"] is True and command["returncode"] == 0
            and command["leader_reaped"] and not command["timed_out"]
            and command["error"] is None
        ),
    }


class ArmError(RuntimeError):
    """Retains controller reference for trusted-host reconciliation/reaping."""

    def __init__(self, controller: Watchdog) -> None:
        super().__init__("watchdog readiness unconfirmed; retain evidence and reconcile")
        self.controller = controller


class Watchdog:
    def __init__(
        self, process: subprocess.Popen, channel: socket.socket,
        evidence_path: Path, deadline: float, teardown_seconds: float,
    ) -> None:
        self._process = process
        self._channel = channel
        self.evidence_path = evidence_path
        self._deadline = deadline
        self._teardown_seconds = teardown_seconds
        self._finished = False
        self._ran = False
        self._run_lock = threading.Lock()
        self._report: dict | None = None
        self.cleanup_errors: tuple[BaseException, ...] = ()

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("trusted-host watchdog cannot be serialized")

    def finish(self) -> dict:
        if self._report is not None:
            return self._report
        if not self._finished:
            self._finished = True
            try:
                self._channel.settimeout(0.05)
                self._channel.sendall(b"R" if _REQUEST_ON_FINISH else b"N")
            except OSError:
                pass
            finally:
                self._channel.close()
        remaining = self._deadline - time.monotonic()
        try:
            self._process.wait(timeout=max(
                0.001, min(remaining, self._teardown_seconds + _REAP_SECONDS + 0.25),
            ))
            with self.evidence_path.open("rb") as stream:
                wire = stream.read(_WIRE_LIMIT + 1)
            if len(wire) > _WIRE_LIMIT:
                raise ValueError("evidence overflow")
            records = [json.loads(line) for line in wire.splitlines()]
            report = records[-1]
            if report.get("event") != "result" or self._process.returncode != 0:
                raise ValueError("controller result missing")
            self._report = report
        except Exception:
            command = _command_result()
            command["attempted"] = None
            command["leader_reaped"] = None
            command["error"] = "controller_result_unknown"
            self._report = _result("controller_unknown", command)
        return self._report

    def run(self, callback: Callable[[], _T], *, cleanup: tuple[Callable, ...] = ()) -> _T:
        with self._run_lock:
            if (self._ran or self._finished
                    or time.monotonic() >= self._deadline - self._teardown_seconds - _REAP_SECONDS
                    or self._process.poll() is not None):
                raise RuntimeError("fresh live armed execution window required")
            self._ran = True
        primary_failed = False
        try:
            return callback()
        except BaseException:
            primary_failed = True
            raise
        finally:
            errors = []
            for index, operation in enumerate((self.finish, *cleanup)):
                try:
                    outcome = operation()
                    if index == 0 and not outcome["local_ok"]:
                        raise RuntimeError("local teardown unconfirmed; remote and billing UNKNOWN")
                except BaseException as error:
                    errors.append(error)
            self.cleanup_errors = tuple(errors)
            if errors and not primary_failed:
                raise errors[0]


def arm(
    *, custody: object, app_identity: object, app_id: str,
    teardown: TrustedTeardown, deadline: float, evidence_path: Path,
    teardown_seconds: float = 1.0, arm_seconds: float = 1.0,
) -> Watchdog:
    started = time.monotonic()
    if (app_identity is None or getattr(custody, "app_identity", None) is not app_identity
            or type(app_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", app_id)
            or getattr(app_identity, "app_id", None) != app_id):
        raise ValueError("exact retained App object and its known control-plane ID required")
    if type(teardown) is not TrustedTeardown:
        raise ValueError("explicit trusted teardown command required")
    if (not _seconds(teardown_seconds, 30) or not _seconds(arm_seconds, 5)
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not 0 < deadline - started <= 1800
            or deadline - started <= arm_seconds + teardown_seconds + _REAP_SECONDS):
        raise ValueError("finite aggregate deadline with arming/teardown reserve required")
    if (not isinstance(evidence_path, Path) or not evidence_path.is_absolute()
            or ".." in evidence_path.parts
            or any(path.is_symlink() for path in (evidence_path, *evidence_path.parents))):
        raise ValueError("absolute non-symlink trusted evidence path required")
    config = json.dumps({
        "app_id": app_id, "executable": teardown._executable,
        "environment": dict(teardown._environment), "deadline": deadline,
        "teardown_seconds": teardown_seconds,
    }, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
    if len(config) > _WIRE_LIMIT:
        raise ValueError("controller configuration too large")
    with _ARM_LOCK:
        if app_id in _ARMED_APP_IDS:
            raise FileExistsError("App already reserved in this host process")
        evidence_fd = os.open(
            evidence_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        _ARMED_APP_IDS.add(app_id)
    channel = child_channel = None
    controller = None
    try:
        _write_event(evidence_fd, {"event": "reserved", "remote": "UNKNOWN", "billing": "UNKNOWN"})
        channel, child_channel = socket.socketpair()
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()),
             "--controller", str(child_channel.fileno()), str(evidence_fd)],
            pass_fds=(child_channel.fileno(), evidence_fd), close_fds=True,
            start_new_session=True, env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        controller = Watchdog(process, channel, evidence_path, deadline, teardown_seconds)
        child_channel.close()
        ready_by = min(deadline - teardown_seconds - _REAP_SECONDS, started + arm_seconds)
        remaining = ready_by - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("watchdog arming deadline exhausted")
        channel.settimeout(remaining)
        channel.sendall(config)
        remaining = ready_by - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("watchdog arming deadline exhausted")
        channel.settimeout(remaining)
        if channel.recv(1) != b"A":
            raise RuntimeError("watchdog readiness absent")
        if time.monotonic() >= ready_by or process.poll() is not None:
            raise RuntimeError("watchdog readiness window exhausted")
        channel.settimeout(None)
        return controller
    except BaseException as primary:
        if channel is not None:
            channel.close()
        if controller is not None:
            # Keep independent teardown alive. Host gets its actual Popen to reap.
            error = ArmError(controller)
            raise error from primary
        raise
    finally:
        if child_channel is not None:
            child_channel.close()
        os.close(evidence_fd)


def _controller(channel_fd: int, evidence_fd: int) -> None:
    channel = socket.socket(fileno=channel_fd)
    trusted_ready = requested = False
    command = _command_result()
    try:
        channel.settimeout(1.0)
        wire = bytearray()
        while not wire.endswith(b"\n"):
            block = channel.recv(min(4096, _WIRE_LIMIT + 1 - len(wire)))
            if not block:
                raise ValueError("owner disappeared before configuration")
            wire.extend(block)
            if len(wire) > _WIRE_LIMIT:
                raise ValueError("configuration overflow")
        config = json.loads(wire)
        teardown = TrustedTeardown(
            Path(config["executable"]), config["environment"], explicitly_trusted=True,
        )
        deadline = config["deadline"]
        timeout = config["teardown_seconds"]
        if (not _seconds(timeout, 30) or type(deadline) not in (int, float)
                or not math.isfinite(deadline)
                or not 0 < deadline - time.monotonic() <= 1800
                or type(config["app_id"]) is not str
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", config["app_id"])):
            raise ValueError("expired controller configuration")
        trusted_ready = True
        _write_event(evidence_fd, {"event": "armed"})
        channel.sendall(b"A")
        trigger_at = deadline - timeout - _REAP_SECONDS
        reason = "deadline"
        while time.monotonic() < trigger_at:
            channel.settimeout(max(0.001, trigger_at - time.monotonic()))
            try:
                message = channel.recv(1)
            except socket.timeout:
                break
            if message == b"N":
                _write_event(evidence_fd, _result("request_suppressed", _command_result()))
                return
            reason = "finish" if message == b"R" else "owner_eof"
            break
        # Never retry a local command, even if subsequent evidence writing fails.
        requested = True
        command = _bounded_command(teardown, config["app_id"], timeout, deadline)
        _write_event(evidence_fd, _result(reason, command))
    except BaseException:
        if trusted_ready and not requested:
            requested = True
            command = _bounded_command(teardown, config["app_id"], timeout, deadline)
        command["error"] = command["error"] or "controller_error"
        _write_event(evidence_fd, _result("controller_error", command))
    finally:
        channel.close()
        os.close(evidence_fd)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--controller":
        raise SystemExit("trusted-host controller invocation required")
    _controller(int(sys.argv[2]), int(sys.argv[3]))
