# Sanitized public reference, UNRUN derivative. No execution authority.
"""SOURCEONLY UNRUN. Original staged executable/parser refusal, not AppStop.
SHORTCUT: synthetic ID; trusted local filesystem; fixed oversized invalid stdin.
MISSING: genuine App ownership, original arm, SDK stop/provider/billing proof.
"""
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import termios
import time

R = Path("/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06")
INTERPRETER = Path("/qualification-reference/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12")
CLAIM = R / "parent-v215-interpreter-read-claim.json"
RETAINED = []


def require(value, message):
    if not value:
        raise ValueError(message)


def left(end):
    value = end - time.monotonic()
    if value <= 0:
        raise TimeoutError("expired")
    return value


def read_owned(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid in (0, os.getuid())
                and not a.st_mode & 0o022 and a.st_size <= limit, "file_metadata")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        b = os.fstat(fd)
        require((a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) ==
                (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns)
                and len(data) == a.st_size, "file_changed")
        return data
    finally:
        os.close(fd)


def exact(channel, size, end):
    data = bytearray()
    while len(data) < size:
        ready, _, _ = select.select([channel], [], [], left(end))
        require(ready, "read_timeout")
        try:
            part = channel.recv(size - len(data))
        except (BlockingIOError, InterruptedError):
            continue
        require(part, "eof")
        data.extend(part)
    return bytes(data)


def send(channel, data, end):
    position = 0
    while position < len(data):
        _, ready, _ = select.select([], [channel], [], left(end))
        require(ready, "write_timeout")
        try:
            count = channel.send(data[position:])
        except (BlockingIOError, InterruptedError):
            continue
        require(count > 0, "closed")
        position += count


def queued(fd):
    result = array.array("i", [0])
    fcntl.ioctl(fd, termios.FIONREAD, result, True)
    return result[0]


def gate(argv):
    fd, target, digest, root, nonce, expiry, end = (
        int(argv[2]), Path(argv[3]), argv[4], Path(argv[5]), argv[6],
        float(argv[7]), float(argv[8]))
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, left(expiry))
    require(target.name == "stop-owned-app" and target.parent.parent == root
            and target.parent.name.startswith("owned-app-stop-"), "target")
    raw = read_owned(target, 131072)
    require(hashlib.sha256(raw).hexdigest() == digest
            and stat.S_IMODE(target.stat().st_mode) == 0o500, "target_pin")
    channel = socket.socket(fileno=fd)
    channel.setblocking(False)
    message = json.dumps({"kind": "gate_ready", "nonce": nonce, "pid": os.getpid(),
                          "pgid": os.getpgrp(), "sid": os.getsid(0)}).encode()
    send(channel, len(message).to_bytes(4, "big") + message, end)
    require(exact(channel, 1, end) == b"T", "trigger")
    channel.close()
    left(end)
    # No subprocess or new session. Original wrapper then execs its interpreter.
    os.execve(str(target), [str(target)], {
        "HOME": str(root / "home"), "PATH": str(INTERPRETER.parent) + ":/usr/bin:/bin",
        "LANG": "C",
    })


def harness(root, spec_path):
    import shutil
    start = time.monotonic()
    expiry, case_end = start + 8.0, start + 2.5
    io_end = case_end - 0.25
    owner = {"handle": None, "fds": [], "sockets": [], "root": root}
    result = {"status": "NONPASS", "primary": None, "cleanup_errors": [],
              "binary_parent_opens": 0, "claim_consumed": False, "gate_popen_calls": 0}
    released = False
    try:
        require(root.is_absolute() and root.resolve(strict=True) == root
                and root.parent == R.parent and root.name.startswith("pc215-")
                and root.stat().st_uid == os.getuid()
                and stat.S_ISDIR(root.stat().st_mode)
                and stat.S_IMODE(root.stat().st_mode) == 0o700, "root")
        spec = json.loads(read_owned(spec_path, 32768))
        require(set(spec) == {"interpreter", "interpreter_size", "source_root",
                             "sdk_root", "source_pins", "sdk_pins"}, "spec_fields")
        source_root = R / "core-v159-qwen-engineering-host"
        sdk_root = R / "modal-tools-2026-11-06/venv/lib/python3.12/site-packages"
        require(spec["source_root"] == str(source_root) and
                spec["sdk_root"] == str(sdk_root), "fixed_roots")
        required_modules = {"modal", "modal.app", "modal.cli.app", "modal.client",
                            "modal_proto", "modal_proto.api_pb2", "modal_version"}
        require(set(spec["sdk_pins"]) == required_modules, "fixed_sdk_sources")
        expected_sources = {str(source_root / "train" / name) for name in (
            "__init__.py", "modal_app_stop.py", "modal_app_stop_launcher.py",
            "qualification_watchdog.py")}
        for module in required_modules:
            base = sdk_root.joinpath(*module.split("."))
            expected_sources.add(str(base / "__init__.py" if base.is_dir()
                                     else base.with_suffix(".py")))
        require(set(spec["source_pins"]) == expected_sources, "fixed_source_set")
        require(spec["interpreter"] == str(INTERPRETER) and
                spec["interpreter_size"] == 49968, "permission_target")
        for name, pin in spec["source_pins"].items():
            body = read_owned(Path(name), 4 * 1024**2)
            require(hashlib.sha256(body).hexdigest() == pin, "source_pin")
        require(time.monotonic() - start <= 2.0, "source_preparation_time")
        sys.path.insert(0, spec["source_root"])
        from train import modal_app_stop as adapter
        from train import modal_app_stop_launcher as launcher
        require(not any(n.split(".")[0] in {"modal", "modal_proto", "modal_version"}
                        for n in sys.modules), "parent_sdk_import")
        sdk_pins = dict(spec["sdk_pins"])
        require(set(sdk_pins) == adapter._REQUIRED, "sdk_source_set")

        def audit(event, args):
            if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                if Path(os.fsdecode(args[0])) == INTERPRETER:
                    result["binary_parent_opens"] += 1
                    require(result["claim_consumed"] and result["binary_parent_opens"] <= 2,
                            "binary_read_budget")
            if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                         "socket.gethostbyname", "socket.gethostbyaddr"}:
                raise RuntimeError("parent_network_forbidden")
        sys.addaudithook(audit)
        left(io_end)
        pin_start = time.monotonic()
        claim = os.open(CLAIM, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(claim, 0o600)
            data = json.dumps({"interpreter": str(INTERPRETER),
                               "maximum_hash_passes": 3, "state": "CONSUMED_NO_RETRY"}).encode()
            require(os.write(claim, data) == len(data), "claim_write")
            os.fsync(claim)
        finally:
            os.close(claim)
        result["claim_consumed"] = True
        binary = read_owned(INTERPRETER, 49968)
        require(len(binary) == 49968, "interpreter_size")
        digest = hashlib.sha256(binary).hexdigest()
        del binary
        result["pin_and_claim_elapsed_s"] = time.monotonic() - pin_start
        require(result["pin_and_claim_elapsed_s"] <= 2.0, "pin_and_claim_time")
        left(io_end)
        stage_start = time.monotonic()
        teardown = launcher.stage_trusted_teardown(
            interpreter=INTERPRETER, interpreter_sha256=digest,
            source_root=Path(adapter.__file__).parent,
            adapter_module=Path(adapter.__file__),
            adapter_sha256=spec["source_pins"][str(Path(adapter.__file__))],
            sdk_root=Path(spec["sdk_root"]), sdk_pins=sdk_pins, private_scratch=root,
            expected_app_id="ap-" + secrets.token_hex(11),
            ownership_confirmed=True, explicitly_trusted=True,
            expires_at=time.time() + 60, rpc_seconds=1.0,
            environment={"HOME": str(root / "home"),
                         "PATH": str(INTERPRETER.parent) + ":/usr/bin:/bin", "LANG": "C"})
        result["stage_elapsed_s"] = time.monotonic() - stage_start
        require(result["stage_elapsed_s"] <= 2.0 and result["binary_parent_opens"] == 2, "stage")
        require(not any(n.split(".")[0] in {"modal", "modal_proto", "modal_version"}
                        for n in sys.modules), "parent_sdk_import")
        require(dict(teardown._environment) == {
            "HOME": str(root / "home"),
            "PATH": str(INTERPRETER.parent) + ":/usr/bin:/bin",
            "LANG": "C"}, "original_environment")
        target = Path(teardown._executable)
        target_digest = hashlib.sha256(read_owned(target, 131072)).hexdigest()
        r, w = os.pipe()
        owner["fds"].extend((r, w))
        require(os.write(w, b"x" * 1025) == 1025 and queued(r) == 1025, "prefill")
        result["stdin_queued_before"] = queued(r)
        parent, child = socket.socketpair()
        owner["sockets"].extend((parent, child))
        parent.setblocking(False)
        nonce = secrets.token_hex(16)
        ready_start = time.monotonic()
        ready_end = min(io_end, ready_start + 0.5)
        left(ready_end)
        result["gate_popen_calls"] += 1
        handle = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", os.path.abspath(__file__), "--gate",
             str(child.fileno()), str(target), target_digest, str(root), nonce,
             repr(expiry), repr(io_end)],
            stdin=r, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(child.fileno(),), close_fds=True, start_new_session=True,
            env={"HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
                 "PATH": "/usr/bin:/bin", "LANG": "C"})
        owner["handle"] = handle
        child.close()
        size = int.from_bytes(exact(parent, 4, ready_end), "big")
        require(0 < size <= 1024, "ready_size")
        ack = json.loads(exact(parent, size, ready_end))
        require(set(ack) == {"kind", "nonce", "pid", "pgid", "sid"}
                and ack["kind"] == "gate_ready" and ack["nonce"] == nonce
                and ack["pid"] == ack["pgid"] == ack["sid"] == handle.pid, "gate_identity")
        result["ready_elapsed_s"] = time.monotonic() - ready_start
        require(result["ready_elapsed_s"] <= 0.5 and time.monotonic() <= ready_end,
                "ready_time")
        result["retained_gate_pid"] = handle.pid
        command_start = time.monotonic()
        command_end = min(io_end, command_start + 1.0)
        send(parent, b"T", command_end)
        require(handle.wait(timeout=left(command_end)) == 1, "original_exit")
        result["command_elapsed_s"] = time.monotonic() - command_start
        require(result["command_elapsed_s"] <= 1.0 and time.monotonic() <= command_end,
                "command_time")
        result["actual_reap"] = handle.returncode
        result["stdin_queued_after"] = queued(r)
        require(result["stdin_queued_after"] == 0, "parser_not_reached")
        require(not (target.parent / "stop.claim").exists(), "stop_claim_created")
        result["parser_consumption_witness"] = True
        result["binary_hash_passes_established"] = 3
        result["interpreter_sha256"] = digest
    except Exception as error:
        result["primary"] = repr(error)
    finally:
        cleanup_start = time.monotonic()
        cleanup_end = min(case_end, cleanup_start + 1.0)
        handle = owner["handle"]
        if handle is not None:
            try:
                if handle.poll() is None:
                    result["cleanup_errors"].append("forced_gate_cleanup")
                    os.killpg(handle.pid, signal.SIGKILL)
                    handle.wait(timeout=max(0, cleanup_end - time.monotonic()))
                require(type(handle.returncode) is int, "unobserved_reap")
                result["actual_reap"] = handle.returncode
            except Exception as error:
                result["cleanup_errors"].append("reap:" + repr(error))
        for channel in owner["sockets"]:
            try:
                channel.close()
            except Exception as error:
                result["cleanup_errors"].append("socket:" + repr(error))
        for fd in owner["fds"]:
            try:
                os.close(fd)
            except Exception as error:
                result["cleanup_errors"].append("fd:" + repr(error))
        result["process_fd_cleanup_s"] = time.monotonic() - cleanup_start
        if result["process_fd_cleanup_s"] > 1.0 or time.monotonic() > case_end:
            result["cleanup_errors"].append("cleanup_time")
        if result["primary"] is None and not result["cleanup_errors"]:
            try:
                left(case_end)
                release_start = time.monotonic()
                shutil.rmtree(root)
                released = True
                require(time.monotonic() - release_start <= 2.0, "root_release_time")
            except Exception as error:
                result["cleanup_errors"].append("release:" + repr(error))
        if not released:
            RETAINED.append(owner)
    elapsed = time.monotonic() - start
    result.update(elapsed_s=elapsed, root_released=released, retained_owners=len(RETAINED),
                  original_stager=True, sdk_appstop_performed=False,
                  synthetic_id_fixture=True, network_attestation=False)
    if (result["primary"] is None and not result["cleanup_errors"] and released
            and elapsed <= 2.5 and elapsed < 8.0 and result.get("actual_reap") == 1):
        result["status"] = "PASS_LOCAL_ORIGINAL_PARSER_REFUSAL"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    if len(sys.argv) == 9 and sys.argv[1] == "--gate":
        gate(sys.argv)
    elif len(sys.argv) == 3:
        sys.exit(harness(Path(sys.argv[1]), Path(sys.argv[2])))
    else:
        raise SystemExit(2)
