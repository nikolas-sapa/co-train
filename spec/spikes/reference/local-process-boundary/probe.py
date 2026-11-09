"""PROVES local kill/join boundary only. SHORTCUT: watchdog is a tiny stand-in."""
import asyncio
import json
import os
from pathlib import Path
import selectors
import secrets
import signal
import stat
import subprocess
import sys
import time

# SHORTCUT: fixed tiny scripts, not a production worker/authority protocol.
WORKER = """
import asyncio,json,os,signal,sys,threading,time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
lease=threading.Timer(max(0,(int(sys.argv[2])-time.monotonic_ns())/1e9),lambda:os._exit(97))
lease.daemon=True
lease.start()
threading.Thread(target=lambda: threading.Event().wait(),daemon=False).start()
snapshot_fd=int(sys.argv[1])
snapshot_inode=os.fstat(snapshot_fd).st_ino
assert os.read(snapshot_fd,64)==b'tiny-owned-snapshot'
ignored=0
async def resistant():
 global ignored
 while True:
  try: await asyncio.sleep(3600)
  except asyncio.CancelledError: ignored+=1
async def main():
 t=asyncio.create_task(resistant())
 await asyncio.sleep(0)
 for i in range(3):
  t.cancel()
  await asyncio.sleep(0)
  assert ignored==i+1
 print(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp(),threads=threading.active_count(),snapshot_inode=snapshot_inode,cancel_ignored=ignored,term_ignored=signal.getsignal(signal.SIGTERM)==signal.SIG_IGN)),flush=True)
 await t
asyncio.run(main())
"""
WATCHDOG = r"""
import json,os,sys,threading,time
lease=threading.Timer(max(0,(int(sys.argv[2])-time.monotonic_ns())/1e9),lambda:os._exit(97))
lease.daemon=True
lease.start()
print(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp())),flush=True)
challenge=sys.stdin.buffer.readline(64)
assert len(challenge)==34 and challenge[:1]==b'P' and challenge[-1:]==b'\n'
print(json.dumps(dict(pid=os.getpid(),pgid=os.getpgrp(),challenge=challenge[1:-1].decode('ascii'))),flush=True)
assert sys.stdin.buffer.read(1)==b'Q'
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
assert os.write(fd,b'1')==1
os.close(fd)
"""

def ready(process, deadline):
    data = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while b"\n" not in data:
            left = deadline - time.monotonic()
            assert left > 0 and selector.select(left), "child admission deadline"
            chunk = os.read(process.stdout.fileno(), 512 - len(data))
            assert chunk and len(data) + len(chunk) < 512
            data.extend(chunk)
    record = json.loads(data)
    assert record["pid"] == process.pid and record["pgid"] == process.pid
    return record

def checked_group(worker, claimed_group):
    # PROVES wrong-target rejection before a signal, independently mutated.
    if claimed_group != worker.pid:
        raise PermissionError("wrong process group")
    assert claimed_group != os.getpgrp()
    assert os.getpgid(worker.pid) == worker.pid
    return claimed_group

def signal_group(worker, claimed_group, sig):
    os.killpg(checked_group(worker, claimed_group), sig)

def remaining(deadline, cap):
    value = min(cap, deadline - time.monotonic())
    if value <= 0:
        raise TimeoutError("reserved local deadline expired")
    return value

def force_join(process, deadline):
    if process is None:
        return
    if process.poll() is None:
        assert os.getpgid(process.pid) == process.pid
        assert process.pid != os.getpgrp()
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=remaining(deadline, 1))

def trial(root, index, hard_end_ns):
    started = time.monotonic()
    deadline = started + 3
    admission_end = started + 0.75
    path = root / ("snapshot-" + str(index))
    stop_marker = root / ("stand-in-stop-" + str(index))
    fd = None
    closed = 0
    worker = watchdog = None
    primary = None
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C",
                   "HOME": str(root), "TMPDIR": str(root)}
    try:
        # Protect every successful open immediately, including initialization.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            assert os.write(fd, b"tiny-owned-snapshot") == len(b"tiny-owned-snapshot")
        finally:
            os.close(fd)
            fd = None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        identity = os.fstat(fd)
        watchdog = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-c", WATCHDOG,
             str(stop_marker), str(hard_end_ns)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, close_fds=True, env=environment,
        )
        wd = ready(watchdog, admission_end)
        worker = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-c", WORKER,
             str(fd), str(hard_end_ns)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, close_fds=True, pass_fds=(fd,), env=environment,
        )
        wr = ready(worker, admission_end)
        assert wr["cancel_ignored"] == 3 and wr["term_ignored"] is True
        assert wr["threads"] >= 2 and wr["snapshot_inode"] == identity.st_ino
        assert wd["pgid"] != wr["pgid"]
        try:
            signal_group(worker, watchdog.pid, signal.SIGKILL)
        except PermissionError:
            pass
        else:
            raise AssertionError("wrong process group admitted")
        assert watchdog.poll() is None
        assert closed == 0 and path.stat().st_ino == identity.st_ino
        signal_group(worker, worker.pid, signal.SIGTERM)
        try:
            worker.wait(timeout=remaining(admission_end, 0.1))
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError("worker did not resist SIGTERM")
        kill_started = time.monotonic()
        signal_group(worker, worker.pid, signal.SIGKILL)
        assert worker.wait(timeout=remaining(deadline - 1, 1)) == -signal.SIGKILL
        kill_seconds = time.monotonic() - kill_started
        assert kill_seconds <= 1 and watchdog.poll() is None
        challenge = secrets.token_hex(16)
        challenge_started = time.monotonic()
        watchdog.stdin.write(b"P" + challenge.encode("ascii") + b"\n")
        watchdog.stdin.flush()
        response = ready(watchdog, min(challenge_started + 0.5, deadline - 0.5))
        assert response["challenge"] == challenge
        challenge_seconds = time.monotonic() - challenge_started
        assert closed == 0 and os.fstat(fd).st_ino == identity.st_ino
        os.close(fd)
        fd = None
        closed += 1
        assert path.stat().st_ino == identity.st_ino
        path.unlink()
        watchdog.stdin.write(b"Q")
        watchdog.stdin.flush()
        watchdog.stdin.close()
        assert watchdog.wait(timeout=remaining(deadline, 0.5)) == 0
        assert stop_marker.read_bytes() == b"1"
        elapsed = time.monotonic() - started
        assert closed == 1 and elapsed <= 3
        return {"trial": index, "ignored_cancellations": 3, "wrong_group_refused": True,
                "watchdog_survived_worker_kill": True, "snapshot_release_after_join": True,
                "watchdog_challenge_seconds": challenge_seconds, "stop_marker_actions": 1,
                "kill_join_seconds": kill_seconds, "elapsed_seconds": elapsed}
    except BaseException as error:
        primary = error
        raise
    finally:
        errors = []
        # Every owned child is attempted independently, even if another fails.
        for process in (worker, watchdog):
            try:
                force_join(process, deadline)
            except BaseException as error:
                errors.append(error)
        # SHORTCUT safety lease: these toy children self-exit by global8s,
        # independently of parent survival. Not a production SDK mechanism.
        # Failed containment is NONPASS; retain snapshots until observed reap.
        for process in (worker, watchdog):
            if process is not None and process.returncode is None:
                try:
                    lease_end = hard_end_ns / 1e9 + 0.5
                    process.wait(timeout=remaining(lease_end, 8.5))
                except BaseException as error:
                    errors.append(error)
        for process in (worker, watchdog):
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except BaseException as error:
                            errors.append(error)
        if fd is not None:
            if worker is None or worker.returncode is not None:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(error)
            else:
                # Explicit OS containment failure, never a cleanup success.
                RETAINED.append((root, fd, worker, watchdog))
                errors.append(RuntimeError("unreaped ownership; snapshot retained"))
        if errors:
            if primary is not None:
                primary.add_note("local cleanup failures: " + "; ".join(map(str, errors)))
            else:
                raise BaseExceptionGroup("local cleanup failed", errors)

RETAINED = []

def main():
    root = Path(sys.argv[1])
    assert root.is_absolute() and root.resolve(strict=True) == root
    info = root.stat()
    assert info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    mode = sys.argv[2]
    assert mode in ("baseline", "guard-control")
    hard_end_ns = time.monotonic_ns() + 8_000_000_000
    results = [trial(root, n, hard_end_ns) for n in range(3 if mode == "baseline" else 1)]
    print(json.dumps({"status": "PASS", "scope": "local-process-isolation-only",
                      "results": results,
                      "worst_kill_join_seconds": max(x["kill_join_seconds"] for x in results),
                      "worst_trial_seconds": max(x["elapsed_seconds"] for x in results),
                      "sdk_provider_gpu_native": False}))

if __name__ == "__main__":
    main()
