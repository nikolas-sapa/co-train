"""Bounded offline process/IPC faults, not native container acceptance."""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from ptc import sql_isolation as m
from ptc import test_sql_isolation as fixtures


def _reap(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=2)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    fixtures.REVIEW_PROCESS_RESULTS.append(
        {"pid": process.pid, "proof": "owned Popen.wait", "returncode": process.returncode})


def _line(process, seconds=5):
    # Unbuffered pipes: readiness cannot be hidden in a BufferedReader cache.
    end, result = time.monotonic() + seconds, bytearray()
    while not result.endswith(b"\n"):
        assert select.select([process.stdout], [], [], max(0, end - time.monotonic()))[0], (
            "owned process did not reach requested boundary")
        part = os.read(process.stdout.fileno(), 1)
        assert part, "owned process exited before requested boundary"
        result.extend(part)
        assert len(result) <= 8192
    return bytes(result)


_CRASH_CHILD = r'''
import os, sys, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import pytest
from ptc import sql_isolation as m
from ptc import test_sql_isolation as f
root, role, boundary = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
original = m._event
def event(job, kind, **values):
    original(job, kind, **values)
    if kind == boundary:
        os.write(sys.stdout.fileno(), b"BOUNDARY\n")
        threading.Event().wait(20)
m._event = event
with pytest.MonkeyPatch.context() as patch:
    # This path never opens a socket; keep all crash artifacts in caller scratch.
    patch.setattr(f, "_review_profile", f.fixture_profile)
    f._shutdown_race_fixture(root, patch, role, "during-stats", complete=True)
raise AssertionError("crash boundary missed")
'''


_RESTART_CHILD = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ptc import sql_isolation as m
job, shared, bypass = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
m.shared_state_dir_for = lambda _: shared
p = m.execution_profile_from_bytes(m._read_owned(job / "profile.json"))
if bypass == "yes": m._admit_finalizations = lambda _: None
try:
    m._admit_finalizations(p)
except m._Failure as exc:
    assert exc.reason == "admission"
    print("BLOCKED", flush=True)
else:
    print("ADMITTED", flush=True)
'''


def _crash_case(tmp_path, role, boundary, *, admission_bypass=False):
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", _CRASH_CHILD, str(m.installed_source_root()),
         str(tmp_path), role, boundary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, bufsize=0)
    try:
        assert _line(process) == b"BOUNDARY\n"
        job, shared = tmp_path / "job", tmp_path / "private-shared"
        before = (job / "journal.json").read_bytes()
        journal = json.loads(before)
        assert journal["role"] == role
        assert journal["shutdown_requested"] is True
        assert journal["cleanup_deadline"] - journal["cleanup_trigger"] == 12
        assert ("exit_grant_intent" in journal) is (boundary != "OBSERVER_PARKED")
        events = [json.loads(line) for line in (job / "events.jsonl").read_bytes().splitlines()]
        # No process exit, release or completion is inferred from a flushed result.
        assert not (job / "outcome.json").exists()
        assert not list(shared.glob("FINALIZATION-COMMITTED-*"))
        process.kill()
        process.wait(timeout=2)
        assert process.returncode == -9, "actual SIGKILL boundary not exercised"
        restart = subprocess.run(
            [sys.executable, "-I", "-B", "-c", _RESTART_CHILD, str(m.installed_source_root()),
             str(job), str(shared), "yes" if admission_bypass else "no"],
            capture_output=True, timeout=3)
        assert restart.returncode == 0, restart.stderr.decode(errors="replace")
        assert restart.stdout == b"BLOCKED\n", "restart admitted unresolved grant"
        assert (job / "journal.json").read_bytes() == before, "restart reset original deadlines"
        assert (shared / "active.json").exists()
        assert not list(shared.glob("FINALIZATION-COMMITTED-*"))
        return events
    finally:
        _reap(process)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("boundary", ["OBSERVER_PARKED", "EXIT_GRANT_INTENT", "EXIT_GRANT_SENT"])
def test_process_crash_at_grant_boundary_blocks_fresh_controller(tmp_path, role, boundary):
    _crash_case(tmp_path, role, boundary)


_GRANT_CHILD = r'''
import hashlib, sys
sys.path.insert(0, sys.argv[1])
from ptc import sql_isolation as m
role, bypass = sys.argv[2:4]
if role == "program":
    request = m.ProgramRequest("pass", 1, "a" * 64)
    response = m.ProgramResponse("fixture", False)
else:
    from bench.task import SqlTask
    from bench.score import ExResult
    task = SqlTask("fixture", "q", "", "SELECT 1", "db", "/db.sqlite",
                   "simple", "derived", "s", "s", "fixture")
    request = m.ScoreRequest(task, "SELECT 1", 1.0, 1, "set", "a" * 64)
    response = ExResult(1.0, "match", True, "", 1, 1)
sha = m.request_sha256(request)
wire = m.encode_wire_message(role, "result", response, request_sha256=sha)
sys.stdout.buffer.write(wire); sys.stdout.buffer.flush()
if bypass == "yes":
    import inspect
    source = inspect.getsource(m._worker_wait_for_exit_grant)
    anchor = "if grant.payload.result_sha256 != hashlib.sha256(result).hexdigest():"
    assert source.count(anchor) == 1
    exec(source.replace(anchor, "if False:"), vars(m))
m._worker_wait_for_exit_grant(role, sha, wire, request)
'''


def _fragmented_case(tmp_path, role, fault, *, digest_bypass=False):
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", _GRANT_CHILD, str(m.installed_source_root()),
         role, "yes" if digest_bypass else "no"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    try:
        result = _line(process, 3)
        grant = m.encode_wire_message(
            role, "exit_grant",
            m.ExitGrant("b" * 64 if fault == "result" else hashlib.sha256(result).hexdigest()),
            request_sha256=json.loads(result)["request_sha256"])
        # Send every byte except LF; a syntactically complete JSON object still
        # must not authorize worker exit before its framing is complete.
        for start in range(0, len(grant) - 1, 7):
            process.stdin.write(grant[start:min(start + 7, len(grant) - 1)])
        assert not select.select([process.stdout], [], [], 0.05)[0], (
            "partial grant caused early worker exit")
        assert process.poll() is None, "partial grant caused early worker exit"
        if fault != "truncated":
            process.stdin.write(b"\n")
        process.stdin.close()
        process.wait(timeout=2)
        extra, errors = process.stdout.read(), process.stderr.read()
        assert not extra
        assert (process.returncode == 0) is (fault is None), (
            "fragmented invalid grant accepted", process.returncode, errors[-1000:])
    finally:
        _reap(process)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [None, "result", "truncated"])
def test_process_fragmented_grant_requires_exact_result_and_lf(tmp_path, role, fault):
    _fragmented_case(tmp_path, role, fault)


def _drain_case(tmp_path, monkeypatch, role, fault, *, drain_bypass=False):
    # Every executable/socket is first-party, owned fixture data. Never invoke
    # Colima, Docker, a shell, a daemon or an external network endpoint.
    profile = fixtures.fixture_profile(tmp_path)
    release_path, cli_entered = tmp_path / "release-cli", tmp_path / "cli-entered"
    binary = tmp_path / "owned-observer"
    binary.write_text(
        "#!" + sys.executable + "\n"
        "import pathlib, sys, time\n"
        f"ready, release = pathlib.Path({str(cli_entered)!r}), pathlib.Path({str(release_path)!r})\n"
        "ready.write_text('ready')\n"
        "end = time.monotonic() + 2\n"
        "while not release.exists() and time.monotonic() < end: time.sleep(0.005)\n"
        "if not release.exists(): sys.exit(9)\n"
        + ("sys.exit(7)\n" if fault == "cli" else
           "print('MemTotal: 1048576 kB\\nMemAvailable: 1048576 kB')\n"))
    binary.chmod(0o700)
    # macOS UNIX paths must remain short. Retain scratch fixtures, never delete.
    scratch = Path.home() / "scratch"
    scratch.mkdir(exist_ok=True)
    socket_root = Path(tempfile.mkdtemp(prefix="sql-ipc-", dir=scratch))
    profile = m.make_execution_profile(
        daemon_socket=socket_root / "s",
        observer=m.MemoryObserver(binary=binary, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),
        program_sources=profile.binding.program.sources, scorer_sources=profile.binding.scorer.sources,
        controller_sources=profile.binding.controller_sources)
    job, journal = fixtures._review_job(tmp_path, profile, cid="a" * 64)
    journal.update(role=role, guardians=[os.getpid()])
    journal["config"] = m._container_config(profile, role, job, journal["nonce"])
    journal["config_sha256"] = hashlib.sha256(m.canonical_json_bytes(journal["config"])).hexdigest()
    if role == "program":
        request, response = m.ProgramRequest("pass", 1, "a" * 64), m.ProgramResponse("fixture", False)
    else:
        from bench.score import ExResult
        from bench.task import SqlTask
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", "/db.sqlite",
                       "simple", "derived", "s", "s", "fixture")
        request = m.ScoreRequest(task, "SELECT 1", 1.0, 1, "set", "a" * 64)
        response = ExResult(1.0, "match", True, "", 1, 1)
    journal["request_sha256"] = m.request_sha256(request)
    request_wire = m.encode_wire_message(role, "request", request)
    result_wire = m.encode_wire_message(role, "result", response, request_sha256=journal["request_sha256"])
    release_http, http_entered, quiescing = threading.Event(), threading.Event(), threading.Event()
    sends, errors, actor_events = [], [], []
    real_event = m._event
    def event(path, kind, **values):
        real_event(path, kind, **values)
        actor_events.append((kind, values))
        if kind == "OBSERVER_QUIESCING":
            quiescing.set()
    monkeypatch.setattr(m, "_event", event)
    def handler(line):
        if "/containers/json" in line:
            return 200, m.canonical_json_bytes([{"Id": journal["cid"], "State": "running"}]), 0, 0
        if "/stats?" in line:
            http_entered.set()
            assert release_http.wait(2), "HTTP release never reached"
            return (503 if fault == "http-status" else 200,
                    b"{" if fault == "http-json" else b'{"memory_stats":{"usage":1048576}}', 0, 0)
        assert line == "GET /info HTTP/1.1"
        return 200, b'{"MemTotal":1073741824}', 0, 0
    server = fixtures._LocalHTTP(profile.daemon_socket, handler)
    metadata = m._Daemon(profile)
    observer = m._Observer(profile, metadata, job)
    now = time.monotonic()
    observer.latest = {"started": now, "finished": now, "available": profile.admission_bytes,
                       "eligible": True}
    class ControlDaemon:
        def call(self, method, path):
            assert method == "GET" and path.endswith("/json")
            obj = fixtures._owned_fixture_object(journal)
            obj["State"].update(Running=True, Pid=1, Status="running", ExitCode=0, OOMKilled=False)
            return obj
    class Attach:
        def settimeout(self, timeout):
            pass
        def sendall(self, wire):
            sends.append(wire)
    if drain_bypass:
        def unsafe_park(self, **kwargs):
            self.state = "PARKED"
        monkeypatch.setattr(m._Observer, "park", unsafe_park)
        monkeypatch.setattr(m._Observer, "shutdown_check", lambda self: self.latest)
    read, write = os.pipe()
    def grant():
        try:
            m._grant_exit(profile, ControlDaemon(), journal, job, read, observer, Attach(),
                          request_wire, result_wire)
        except BaseException as exc:
            errors.append(exc)
    coordinator = threading.Thread(target=grant)
    observer.thread.start()
    try:
        assert http_entered.wait(2), "real metadata RPC did not start"
        end = time.monotonic() + 2
        while not cli_entered.exists() and time.monotonic() < end:
            observer.stop.wait(0.005)
        assert cli_entered.exists(), "real CLI did not start"
        coordinator.start()
        assert quiescing.wait(1)
        coordinator.join(0.05)
        assert not sends, "grant bypassed real CLI/HTTP drain"
        assert coordinator.is_alive(), "grant drain did not wait for owned work"
        assert metadata.active and metadata.workers
        release_http.set()
        release_path.write_text("release")
        coordinator.join(3)
        assert not coordinator.is_alive(), "drain did not finish in original sample bound"
        assert not metadata.active and not metadata.workers
        starts = [v for k, v in actor_events if k == "CLI_STARTED"]
        joins = [v for k, v in actor_events if k == "CLI_JOIN_ACK"]
        assert len(starts) == len(joins) == 1
        assert starts[0]["pid"] == joins[0]["pid"] and joins[0]["reaped"] is True
        assert joins[0]["returncode"] == (7 if fault == "cli" else 0)
        with pytest.raises(ProcessLookupError):
            os.kill(starts[0]["pid"], 0)
        assert journal["cleanup_deadline"] - journal["cleanup_trigger"] == 12
        if fault is None:
            assert not errors and len(sends) == 1
            assert observer.state == "PARKED" and not observer.inflight
            grant_message = m.decode_wire_message(
                sends[0], role=role, kind="exit_grant", request_sha256=journal["request_sha256"])
            assert grant_message.payload.result_sha256 == hashlib.sha256(result_wire).hexdigest()
        else:
            assert errors and isinstance(errors[0], m._Failure)
            assert not sends, "genuine observation error allowed grant"
            assert "exit_grant_intent" not in journal
        assert not (job / "outcome.json").exists()
    finally:
        release_http.set()
        release_path.write_text("release")
        if coordinator.ident is not None:
            coordinator.join(3)
        observer.stop.set()
        observer.thread.join(3)
        server.close()
        os.close(read)
        os.close(write)
        assert not coordinator.is_alive() and not observer.thread.is_alive()


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [None, "cli", "http-status", "http-json"])
def test_process_owned_cli_and_unix_http_unwind_before_grant(tmp_path, monkeypatch, role, fault):
    _drain_case(tmp_path, monkeypatch, role, fault)


@pytest.mark.parametrize("guard", ["admission", "drain", "result-digest"])
def test_process_fault_assertion_sensitivity(tmp_path, guard):
    baseline, mutant = tmp_path / "baseline", tmp_path / "mutant"
    baseline.mkdir()
    mutant.mkdir()
    if guard == "admission":
        _crash_case(baseline, "program", "EXIT_GRANT_INTENT")
        with pytest.raises(AssertionError, match="restart admitted unresolved grant"):
            _crash_case(mutant, "program", "EXIT_GRANT_INTENT", admission_bypass=True)
    elif guard == "drain":
        with pytest.MonkeyPatch.context() as patch:
            _drain_case(baseline, patch, "program", None)
        with pytest.MonkeyPatch.context() as patch:
            with pytest.raises(AssertionError, match="grant bypassed real CLI/HTTP drain"):
                _drain_case(mutant, patch, "program", None, drain_bypass=True)
    else:
        _fragmented_case(baseline, "program", "result")
        with pytest.raises(AssertionError, match="fragmented invalid grant accepted"):
            _fragmented_case(mutant, "program", "result", digest_bypass=True)


# Owned-API bridge, deliberately restricted to cancellation BEFORE guest CREATE.
# This is not the sixteen-boundary role/worker matrix. Unlike the old crash
# fixtures it keeps controller liveness open and delivers the real 40-byte frame.
# All executable code below is first-party Python. No socket, SQL, image, native
# observer, or daemon is used. Safety cleanup never issues a public cleanup ACK.
_OWNED_PRECREATE_GUARDIAN = r'''
import json, os, select, socket, sqlite3, subprocess, sys, threading, time
from pathlib import Path
job = Path(sys.argv[1])
control, cancel, gate, diagnostic, safety = map(int, sys.argv[2:7])
phase = sys.argv[7]
sys.path.insert(0, str(job / "controller"))
from ptc import sql_isolation as m
contexts = []
done_r, done_w = os.pipe()
cleanup_lock = threading.Lock()
stopping = threading.Event()
forbidden_calls = []
lifetime_released = threading.Event()
lifetime_owner = threading.Thread(
    target=lifetime_released.wait, name="fixture-guardian-lifetime", daemon=False)
lifetime_owner.start()

def emit(kind, **data):
    raw = json.dumps(dict(kind=kind, **data), separators=(",", ":")).encode() + b"\n"
    assert len(raw) < 4096
    assert os.write(diagnostic, raw) == len(raw)

def forbidden(*args, **kwargs):
    forbidden_calls.append(1)
    raise AssertionError("pre-CREATE fixture attempted native/network/SQL IO")

socket.socket.connect = socket.socket.connect_ex = socket.socket.bind = forbidden
socket.getaddrinfo = forbidden
sqlite3.connect = forbidden
subprocess.Popen = forbidden  # _CreatorPopen retains its actual original base.
os.killpg = forbidden
original_kill = os.kill
def direct_only(pid, sig):
    if pid <= 0:
        return forbidden(pid, sig)
    return original_kill(pid, sig)
os.kill = direct_only

def release_gate():
    assert select.select([gate], [], [], 2.0)[0], "fixture release gate missing"
    assert os.read(gate, 1) == b"G"

class Daemon:
    def __init__(self):
        self.active, self.workers = set(), set()
        self.shutdown_supervision = None
    def call(self, method, path, *args, **kwargs):
        assert not stopping.is_set(), "boundary retired by independent safety teardown"
        assert method == "GET", "pre-CREATE cancellation failed to stop dispatch"
        if path.startswith("/images/sha256:"):
            return dict(Os="linux", Architecture="arm64",
                Id="sha256:" + m.IMAGE_CONFIG_SHA256,
                RepoDigests=["fixture@sha256:" + m.IMAGE_MANIFEST_SHA256])
        if path == "/info":
            return {"MemTotal": 1073741824}
        if path == "/containers/json":
            return []
        raise AssertionError("unexpected boundary RPC: " + path)
    def attach(self, cid):
        raise AssertionError("pre-CREATE fixture must never attach")

class Bridge:
    def daemon(self, profile):
        return Daemon()
    def vm_command(self, profile):
        assert not stopping.is_set(), "CLI boundary retired"
        assert phase == "admission-cli", "unexpected VM command"
        emit("HIT", phase=phase)
        release_gate()
        assert not stopping.is_set(), "CLI creation suppressed by safety teardown"
        # One finite timer, not a readiness poll. The command has no descendants,
        # network, SQL, inherited control descriptors, or native observer binary.
        code = ("import select; select.select([],[],[],0.05); "
                "print('MemTotal: 1048576 kB\\nMemAvailable: 1048576 kB')")
        return ([sys.executable, "-I", "-B", "-c", code],
                {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})

def boundary(profile, path):
    with cleanup_lock:
        assert not stopping.is_set(), "guardian boundary retired"
        assert path == job
        context = m._owned_context(m._metadata(m._read_owned(job / "journal.json")))
        assert context is not None
        contexts.append(context)  # Actual objects, retained after retirement.
    return Bridge()
m._owned_boundary_io = boundary

def physical_cleanup():
    # Independent TEST-ONLY teardown. First join every potential CLI creator,
    # then inspect retained actual CLI objects. Never infer absence from events.
    stopping.set()
    with cleanup_lock:
        end = time.monotonic() + 3.0
        for context in contexts:
            for pool in tuple(context.executors):
                pool.shutdown(wait=False, cancel_futures=False)
                for thread in tuple(pool._threads):
                    thread.join(timeout=max(0, end - time.monotonic()))
                    assert not thread.is_alive(), "safety CLI creator thread still live"
            context.stop.set()
            if context.monitor.ident is not None:
                context.monitor.join(timeout=max(0, end - time.monotonic()))
            assert not context.monitor.is_alive(), "safety monitor join absent"
            for child in tuple(context.children):
                # These methods serialize direct signal/reap using creator locks.
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=max(0.001, end - time.monotonic()))
                assert child._creator_waited and not child._creator_ambiguous
        return sum(len(context.children) for context in contexts)

def watchdog():
    ready = select.select([safety, done_r], [], [], 6.0)[0]
    if done_r in ready:
        return
    try:
        count = physical_cleanup()
        emit("SAFE", cli_waits=count)
    except BaseException as exc:
        # No false safety assertion and no kill of a supervisor owning children.
        emit("UNSAFE", detail=type(exc).__name__ + ": " + str(exc))
        return
    os._exit(87)  # All nested creator children waited; no public ACK is added.

supervisor = threading.Thread(target=watchdog, name="fixture-safety", daemon=False)
supervisor.start()
try:
    if phase != "admission-cli":
        emit("HIT", phase=phase)
        release_gate()
        assert select.select([cancel], [], [], 0.1)[0], "real notification not ready"
        emit("NOTIFICATION_READY", at_ns=time.monotonic_ns())
        # Readiness observation does not consume the frame. The real exclusive
        # guardian monitor remains its only reader.
    m._owned_guardian(job, control, cancel, False)
    emit("EVIDENCE",
         forbidden_attempts=len(forbidden_calls),
         cancel_times=[list(context.times) if context.times is not None else None
                       for context in contexts],
         cli_waits=[dict(waited=child._creator_waited,
                         ambiguous=child._creator_ambiguous,
                         returncode=child.returncode)
                    for context in contexts for child in context.children],
         live_monitors=sum(context.monitor.is_alive() for context in contexts),
         live_executors=sum(thread.is_alive() for context in contexts
                            for pool in context.executors for thread in pool._threads),
         active_rpc=sum(len(daemon.active) + len(daemon.workers)
                        for context in contexts for daemon in context.daemons),
         contexts=len(contexts))
finally:
    # Even an assertion/production failure reaches retained creator handles.
    count = physical_cleanup()
    emit("SAFE", cli_waits=count)
    lifetime_released.set()
    lifetime_owner.join(timeout=0.2)
    assert not lifetime_owner.is_alive()
    os.write(done_w, b"D")
    supervisor.join(timeout=0.2)
    assert not supervisor.is_alive()
'''


_OWNED_PRECREATE_HOST = r'''
import asyncio, dataclasses, hashlib, json, os, select, socket, sqlite3
import subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ptc import sql_isolation as m
root, role, phase = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
GUARDIAN_SOURCE = __GUARDIAN_SOURCE__
loop = asyncio.new_event_loop()  # Private anonymous self-pipe before guards.
owner = None
slots, receipts, creation_faults = [], [], []
cleanup_lock = threading.Lock()
stopping = threading.Event()
cleanup_finished = threading.Event()
lifetime_owner = threading.Thread(
    target=cleanup_finished.wait, name="fixture-host-lifetime", daemon=False)
lifetime_owner.start()
spawn_lock = threading.Lock()
spawn_ready = loop.create_future()
done_r, done_w = os.pipe()
group_signals = []
forbidden_calls = []

def forbidden(*args, **kwargs):
    forbidden_calls.append(1)
    raise AssertionError("offline owned host attempted native/network/SQL IO")
socket.socket.connect = socket.socket.connect_ex = socket.socket.bind = forbidden
socket.getaddrinfo = forbidden
sqlite3.connect = forbidden
subprocess.Popen = forbidden
def no_groups(*args, **kwargs):
    group_signals.append(1)
    raise AssertionError("process-group signal forbidden")
os.killpg = no_groups
original_kill = os.kill
def direct_only(pid, sig):
    if pid <= 0:
        return no_groups(pid, sig)
    return original_kill(pid, sig)
os.kill = direct_only

def line(fd, end):
    data = bytearray()
    while not data.endswith(b"\n"):
        assert select.select([fd], [], [], max(0, end - time.monotonic()))[0], (
            "bounded fixture pipe deadline")
        chunk = os.read(fd, 1)
        assert chunk, "fixture pipe EOF"
        data.extend(chunk)
        assert len(data) <= 4096
    return json.loads(data)

def cleanup():
    # Retained slots are installed before owner._spawn reaches BasePopen.
    stopping.set()
    with cleanup_lock:
        if cleanup_finished.is_set():
            return
        with spawn_lock:
            pass  # Fence any in-progress BasePopen before freezing the slots.
        for slot in slots:
            child = slot.get("child")
            if child is None:
                created = slot["registry"][slot["before"]:slot.get("after")]
                assert len(created) <= 1
                child = created[0] if created else None
            if child is not None:
                end = time.monotonic() + 4.0
                try:
                    os.write(slot["safety_w"], b"S")
                except BrokenPipeError:
                    pass
                # Reap/exit never substitutes for nested creator-child proof.
                while not slot["safe"]:
                    item = line(slot["diagnostic_r"], end)
                    slot["messages"].append(item)
                    assert item["kind"] != "UNSAFE", item
                    slot["safe"] = item["kind"] == "SAFE"
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=max(0.001, end - time.monotonic()))
                assert child._creator_waited and not child._creator_ambiguous
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream is not None:
                        stream.close()
            for fd in slot["fds"]:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if owner is not None:
            # Release only the test process's retained host thread AFTER every
            # physical nested child is absent. This cannot produce a public ACK.
            owner._retained.set()
            if owner._thread is not None:
                owner._thread.join(timeout=1.0)
                assert not owner._thread.is_alive(), "host controller join absent"
            with owner._lock:
                for endpoint in owner._endpoints:
                    endpoint.close()
                fds = {item for item in owner._resources if type(item) is int}
                if owner._host_read is not None:
                    fds.add(owner._host_read)
                for fd in fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                for item in owner._resources:
                    if type(item) is not int:
                        item.close()
                owner._resources.clear()
                owner._host_read = owner._seal_lock_fd = None
        cleanup_finished.set()

def report(result, code):
    lifetime_owner.join(timeout=0.2)
    assert not lifetime_owner.is_alive()
    raw = json.dumps(dict(safe=True, **result), separators=(",", ":")).encode() + b"\n"
    assert len(raw) < 8192
    os.write(sys.stdout.fileno(), raw)
    os._exit(code)

def watchdog():
    ready = select.select([sys.stdin.fileno(), done_r], [], [], 12.0)[0]
    if done_r in ready:
        return
    cleanup()
    report(dict(ok=False, error="fixture independent safety timeout"), 90)

supervisor = threading.Thread(target=watchdog, name="fixture-host-safety", daemon=False)
supervisor.start()

def spawn_locked(invocation, job, control_fd, cancel_fd, lock_fd, log, emergency=False):
    assert not stopping.is_set(), "guardian creation suppressed by safety teardown"
    assert not emergency, "pre-CREATE fixture unexpectedly replaced guardian"
    gate_r, gate_w = os.pipe()
    diagnostic_r, diagnostic_w = os.pipe()
    safety_r, safety_w = os.pipe()
    slot = dict(registry=invocation._children, before=len(invocation._children),
                diagnostic_r=diagnostic_r, gate_w=gate_w, safety_w=safety_w,
                safe=False, messages=[], fds=[gate_w, diagnostic_r, safety_w])
    slots.append(slot)
    try:
        child = invocation._spawn(
            [sys.executable, "-I", "-B", "-c", GUARDIAN_SOURCE,
             str(job), str(control_fd), str(cancel_fd), str(gate_r),
             str(diagnostic_w), str(safety_r), phase],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
            pass_fds=(control_fd, cancel_fd, lock_fd, gate_r, diagnostic_w, safety_r),
            close_fds=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        slot["child"] = child
    finally:
        slot["after"] = len(invocation._children)
        for fd in (gate_r, diagnostic_w, safety_r):
            os.close(fd)
    if phase == "guardian-postcreation":
        item = line(diagnostic_r, time.monotonic() + 2.0)
        assert item == dict(kind="HIT", phase=phase), item
        slot["messages"].append(item)
        receipts.append(invocation.request_cancel("caller_cancelled"))
        os.write(gate_w, b"G")
        loop.call_soon_threadsafe(
            lambda: None if spawn_ready.done() else spawn_ready.set_result(None))
        creation_faults.append(1)
        raise RuntimeError("first-party postcreation/prepublication fault")
    loop.call_soon_threadsafe(
        lambda: None if spawn_ready.done() else spawn_ready.set_result(None))
    return child

def spawn(*args, **kwargs):
    with spawn_lock:
        return spawn_locked(*args, **kwargs)
m._spawn_owned_guardian = spawn

async def run():
    global owner
    binary = root / "observer-inert"
    binary.write_bytes(b"not executable, never launched\n")
    source_root = m.installed_source_root()
    def pins(names):
        return tuple(m.SourcePin(name, hashlib.sha256(
            (source_root / name).read_bytes()).hexdigest()) for name in names)
    profile = m.make_execution_profile(
        daemon_socket=root / "never-opened.sock",
        observer=m.MemoryObserver(binary=binary,
            binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),
        program_sources=pins(m._PROGRAM_PATHS), scorer_sources=pins(m._SCORER_PATHS),
        controller_sources=pins(("ptc/sql_isolation.py",)))
    db = root / "inert-db"
    db.write_bytes(b"inert bytes, not a SQLite database\n")
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    executor = m.PilotExecutor(profile, state_dir=root / "run")
    if role == "program":
        owner = executor.owned_program("print(1)", db_path=str(db),
                                       db_sha256=digest, max_rows=1)
        expected = m.ProgramRequest("print(1)", 1, digest)
    else:
        from bench.task import SqlTask
        from train.sql_episodes import InstrumentSettings
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", str(db),
                       "simple", "derived", "s", "s", "fixture")
        instrument = InstrumentSettings(1, 1, 1, "set", 1.0, 5.0, 1.0,
                                        "fixture", "fixture", (), "a" * 64)
        owner = executor.owned_score("SELECT 1", task, db_sha256=digest,
                                     instrument=instrument)
        expected = m.ScoreRequest(dataclasses.replace(task, db_path="/db.sqlite"),
                                  "SELECT 1", 1.0, 1, "set", digest)
    assert owner.snapshot().request_sha256 == m.request_sha256(expected)
    if phase == "predispatch":
        receipts.append(owner.request_cancel("caller_cancelled"))
    execution = loop.create_task(owner.execute())
    # Kernel-backed pipe readiness via add_reader, no background polling job.
    end = loop.time() + 4.0
    if phase != "predispatch":
        _, pending = await asyncio.wait([spawn_ready], timeout=4.0)
        assert not pending, "guardian creation seam not reached"
    if slots:
        slot = slots[0]
        if phase != "guardian-postcreation":
            ready = loop.create_future()
            loop.add_reader(slot["diagnostic_r"],
                            lambda: None if ready.done() else ready.set_result(None))
            try:
                _, pending = await asyncio.wait([ready], timeout=max(0, end - loop.time()))
                assert not pending, "guardian hook never became ready"
            finally:
                loop.remove_reader(slot["diagnostic_r"])
            item = line(slot["diagnostic_r"], time.monotonic() + 0.1)
            assert item == dict(kind="HIT", phase=phase), item
            slot["messages"].append(item)
            receipts.append(owner.request_cancel("caller_cancelled"))
            os.write(slot["gate_w"], b"G")
    first = receipts[0]
    assert first.status == "accepted"
    intent = first.intent
    closing = loop.create_task(owner.aclose())
    _, pending = await asyncio.wait([execution, closing], timeout=5.0)
    assert not pending, "responsive canonical cleanup did not return a public ACK"
    completion, ack = execution.result(), closing.result()
    assert completion.cleanup_ack is ack and completion.outcome is None
    assert completion.abort.kind == "cancelled" and completion.abort.role == role
    assert ack.request_sha256 == m.request_sha256(expected)
    assert ack.profile_sha256 == m.execution_profile_sha256(profile)
    assert ack.invocation_id == intent.invocation_id == owner.snapshot().invocation_id
    assert intent.requested_ns <= ack.completed_ns <= intent.deadline_ns
    assert intent.deadline_ns == intent.requested_ns + 12000000000
    assert ack.cleanup_trigger_ns == intent.requested_ns
    assert ack.cleanup_deadline_ns <= intent.deadline_ns
    assert len(creation_faults) == (1 if phase == "guardian-postcreation" else 0)
    assert owner._thread is None or not owner._thread.is_alive()
    if phase == "predispatch":
        assert not slots and not owner._children and ack.not_started
    else:
        assert len(slots) == len(owner._children) == 1, "creator guardian registry incomplete"
        child = slots[0]["child"]
        assert child is owner._children[0]
        assert child._creator_waited and not child._creator_ambiguous
        assert ack.guardian_reaps == ((child.pid, child.returncode),)
        assert child.returncode == 0 and ack.thread_joins and ack.child_waits
        assert not ack.not_started
        assert owner._host_received, "actual host notification reader did not consume frame"
        while not slot["safe"]:
            item = line(slot["diagnostic_r"], time.monotonic() + 0.5)
            slot["messages"].append(item)
            slot["safe"] = item["kind"] == "SAFE"
        evidence = [item for item in slot["messages"] if item["kind"] == "EVIDENCE"]
        assert len(evidence) == 1, "actual pre-teardown actor evidence absent"
        evidence = evidence[0]
        assert evidence["contexts"] == 1
        assert evidence["forbidden_attempts"] == 0
        assert evidence["cancel_times"] == [[intent.requested_ns, intent.deadline_ns]]
        assert evidence["live_monitors"] == evidence["live_executors"] == evidence["active_rpc"] == 0
        cli = evidence["cli_waits"]
        assert len(cli) == (1 if phase == "admission-cli" else 0), (
            "creator CLI registry omitted the dispatched memory command")
        assert all(row["waited"] and not row["ambiguous"] and row["returncode"] == 0
                   for row in cli), "actual creator CLI wait absent before public ACK"
        assert sum(item["kind"] == "HIT" for item in slot["messages"]) == 1
        if phase != "admission-cli":
            notified = [item for item in slot["messages"]
                        if item["kind"] == "NOTIFICATION_READY"]
            assert len(notified) == 1
            assert 0 <= notified[0]["at_ns"] - intent.requested_ns <= 100000000
        wire = m.decode_wire_message(
            (root / "run" / owner.invocation_id.hex / "request.wire").read_bytes(),
            role=role, kind="request", request_sha256=ack.request_sha256)
        assert wire.payload == expected
        outcome = json.loads((root / "run" / owner.invocation_id.hex / "outcome.json").read_bytes())
        typed = (m.program_outcome_from_dict(outcome) if role == "program"
                 else m.score_outcome_from_dict(outcome))
        assert typed.abort.stage == role
        assert (typed.observation if role == "program" else typed.result) is None
    assert not group_signals and not forbidden_calls
    return dict(ok=True, phase=phase, role=role, guardians=len(slots))

result, code = None, 0
try:
    result = loop.run_until_complete(run())
except BaseException as exc:
    result, code = dict(ok=False, error=type(exc).__name__ + ": " + str(exc)), 1
finally:
    cleanup()
    os.write(done_w, b"D")
    supervisor.join(timeout=0.2)
    assert not supervisor.is_alive()
    # Any intentionally retained public task is confined to this interpreter.
    # Physical teardown above cannot change its tested snapshot/completion.
    loop.close()
report(result, code)
'''


class _OwnedProbeProcess(subprocess.Popen):
    """Outer creator handle, installed before BasePopen construction."""
    def __init__(self, *args, registry, **kwargs):
        self.owner_lock = threading.RLock()
        self.actual_wait = False
        registry.append(self)
        super().__init__(*args, **kwargs)

    def poll(self):
        with self.owner_lock:
            return super().poll()

    def wait(self, timeout=None):
        with self.owner_lock:
            result = super().wait(timeout=timeout)
            self.actual_wait = True
            return result

    def send_signal(self, sig):
        with self.owner_lock:
            assert self.returncode is None, "outer signal authority already retired"
            return super().send_signal(sig)


def _owned_precreate_case(tmp_path, role, phase):
    """One shared <20s safety clock; never kill an unreleased nested supervisor."""
    source = _OWNED_PRECREATE_HOST.replace(
        "__GUARDIAN_SOURCE__", repr(_OWNED_PRECREATE_GUARDIAN))
    registry = []
    deadline = time.monotonic() + 19.0
    result = None
    try:
        process = _OwnedProbeProcess(
            [sys.executable, "-I", "-B", "-c", source,
             str(m.installed_source_root()), str(tmp_path), role, phase],
            registry=registry, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        # Leave two seconds of the SAME case budget for the safety-channel path.
        result = json.loads(_line(process, max(0, deadline - time.monotonic() - 2.0)))
        assert result.get("safe") is True, "fixture did not prove independent physical teardown"
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        assert process.returncode == 0 and result.get("ok") is True, result
    finally:
        for process in registry:
            if getattr(process, "pid", None) is None:
                continue
            try:
                process.stdin.write(b"S")
            except (BrokenPipeError, ValueError):
                pass
            if result is None:
                result = json.loads(_line(
                    process, max(0, deadline - time.monotonic())))
            # Exited outer hosts also owe their independently captured proof.
            assert result.get("safe") is True, "unsafe nested supervisor retained"
            if process.poll() is None:
                process.kill()
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
            assert process.actual_wait
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("phase", [
    "predispatch", "guardian-postcreation", "startup-wait", "admission-cli"])
def test_owned_public_precreate_cancellation_uses_real_creator_cleanup(
        tmp_path, role, phase):
    _owned_precreate_case(tmp_path, role, phase)


@pytest.mark.parametrize("has_proof", (False, True), ids=("missing", "present"))
def test_owned_fixture_exited_guardian_still_requires_safe_proof(has_proof):
    """Fixture guard unit only; no canonical resource/creator qualification."""
    import ast
    from types import SimpleNamespace

    script = ast.parse(_OWNED_PRECREATE_HOST)
    functions = [node for node in script.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("line", "cleanup")]
    diagnostic_r, diagnostic_w = os.pipe()
    safety_r, safety_w = os.pipe()
    waits = []
    child = SimpleNamespace(
        poll=lambda: 0, wait=lambda **kwargs: waits.append(1),
        _creator_waited=True, _creator_ambiguous=False,
        stdin=None, stdout=None, stderr=None)
    slot = dict(child=child, diagnostic_r=diagnostic_r, safety_w=safety_w,
                safe=False, messages=[], fds=[])
    finished = threading.Event()
    namespace = dict(
        os=os, time=time, select=select, json=json, owner=None,
        stopping=threading.Event(), cleanup_lock=threading.Lock(),
        spawn_lock=threading.Lock(), cleanup_finished=finished, slots=[slot])
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<fixture-cleanup>", "exec"),
         namespace)
    try:
        if has_proof:
            os.write(diagnostic_w, b'{"kind":"SAFE","cli_waits":0}\n')
        os.close(diagnostic_w)
        if has_proof:
            namespace["cleanup"]()
            assert finished.is_set() and waits == [1]
        else:
            with pytest.raises(AssertionError, match="EOF"):
                namespace["cleanup"]()
            assert not finished.is_set() and waits == []
    finally:
        for fd in (diagnostic_r, safety_r, safety_w):
            os.close(fd)


# Separate from the approved pre-CREATE bridge above. The generated script is
# first-party fixture code, written only into pytest scratch at test runtime.
# "role" emits static typed fixture responses, NOT native SQL/EX evidence.
# No public method, source admission, cleanup ACK or canonical result is mocked.
_OWNED_GUEST_PROBE = r'''
import asyncio, copy, dataclasses, fcntl, hashlib, json, os, select
import socket, sqlite3, struct, subprocess, sys, threading, time, types
from pathlib import Path

class _ObservedTestGates:
    """Fixture observations only. Never invent a native gate or an ACK."""
    def __init__(self, *, ensure_intents):
        self.ensure_intents = ensure_intents
        self.lock = threading.Lock()
        self.rows, self.objects, self.keys, self.occurrences = [], {}, {}, {}
        self.observed = []
        self.retiring = False

    def observe(self, hit, release):
        assert type(hit) is dict and hit.get("kind") == "HIT"
        invocation, name = hit.get("invocation_id"), hit.get("name")
        assert type(invocation) is str and invocation
        assert type(name) is str and name
        event = hit.get("event")
        assert event is None or type(event) is str
        with self.lock:
            previous = self.objects.get(id(hit))
            if previous is not None:
                return previous["hit"]
            base = (invocation, "HIT", name, event)
            occurrence = hit.get("occurrence")
            if occurrence is None:
                occurrence = self.occurrences.get(base, 0) + 1
            assert type(occurrence) is int and occurrence > 0
            self.occurrences[base] = max(self.occurrences.get(base, 0), occurrence)
            key = (*base, occurrence)
            row = self.keys.get(key)
            if row is None:
                row = dict(hit=hit, key=key, release=release, released=False, busy=False)
                self.keys[key] = row
                self.rows.append(row)  # Retain actual decoded object.
            self.observed.append(hit)  # Keep aliases alive; never reuse an object ID.
            self.objects[id(hit)] = row
            retiring = self.retiring
        if retiring:
            self._release(row)  # Late observation, AFTER original real intents.
        return row["hit"]

    def released(self, hit):
        # Ordinary successful releases owe the same exact-occurrence ledger.
        with self.lock:
            row = self.objects[id(hit)]
            row["released"] = True

    def pending_for(self, invocation_id):
        with self.lock:
            return next((row["hit"] for row in self.rows
                         if row["key"][0] == invocation_id
                         and not row["released"] and not row["busy"]), None)

    def _release(self, row):
        with self.lock:
            if row["released"] or row["busy"]:
                return
            row["busy"] = True
        try:
            # Neither public API calls nor I/O run under bookkeeping locks.
            self.ensure_intents()
            row["release"]()
        except BaseException:
            with self.lock:
                row["busy"] = False
            raise
        else:
            self.released(row["hit"])
            with self.lock:
                row["busy"] = False

    def release_one(self, hit):
        with self.lock:
            row = self.objects[id(hit)]
        self._release(row)

    def release_pending(self):
        with self.lock:
            self.retiring = True
            rows = tuple(self.rows)
        primary = None
        for row in rows:
            try:
                self._release(row)
            except BaseException as exc:
                if primary is None:
                    primary = exc
        if primary is not None:
            raise primary

def _fence_owned_start(owner, spawn_lock, stopping):
    original = owner._start
    def start():
        with spawn_lock:
            if stopping.is_set():
                raise RuntimeError("fixture owner startup retired")
            return original()
    owner._start = start

MODE = sys.argv[1]
SCRIPT = str(Path(__file__).resolve())
if MODE == "host":
    SOURCE, ROOT, ROLE, PHASE, MUTANT = sys.argv[2:7]
    END = float(sys.argv[7])
    PREPARED = tuple(sys.argv[8:])
    LOOP = asyncio.new_event_loop()  # Anonymous self-pipe, before network guards.
else:
    JOB, ROLE = Path(sys.argv[2]), sys.argv[3]
    SOURCE = str(JOB / "controller")
    if MODE == "guardian":
        PHASE, MUTANT, END = sys.argv[4], sys.argv[5], float(sys.argv[6])
    else:
        END = float(sys.argv[4])
        PHASE, MUTANT = "", sys.argv[5] if len(sys.argv) == 6 else "none"
        assert MUTANT in ("none", "program-observation-sentinel", "invalid-target-zero")
        assert MUTANT != "invalid-target-zero" or ROLE == "scorer"
sys.path.insert(0, SOURCE)
from ptc import sql_isolation as m
# CREATOR_BOUNDARY_BEGIN
# GUARDIAN_BUDGET_BEGIN
_guardian_budget_ready = False
if MODE == "guardian":
    try:
        _guardian_budget_clock = time.monotonic_ns
        _guardian_budget_write = os.write
        _guardian_budget_ready = True
    except BaseException:
        pass  # Disable metadata, never recapture after fixture replacements.
# GUARDIAN_BUDGET_END
# CREATOR_BOUNDARY_END
# CREATOR_BOUNDARY_BEGIN
_boundary_original_ready = False
if MODE == "host" and PHASE.startswith("sdk-"):
    # Original objects, before fixture thread/creator replacements or acceptance.
    try:
        _boundary_original_thread = threading.Thread
        _boundary_original_active = threading._active
        _boundary_original_frames = sys._current_frames
        _boundary_original_write = os.write
        _boundary_original_clock = time.monotonic_ns
        _boundary_original_core = (
            m.OwnedSqlInvocation._controller.__code__,
            m.OwnedSqlInvocation._register_pipe.__code__,
            m.OwnedSqlInvocation._wait_startup.__code__,
            m._CreatorPopen.__init__.__code__)
        _boundary_original_ready = True
    except BaseException:
        pass  # Disable diagnostics; never retry after fixture replacements.
# CREATOR_BOUNDARY_END

# SDK_TIMELINE_RUNTIME_HELPER_BEGIN
_timeline_original_deque = _timeline_original_popleft = None
try:
    from collections import deque as _timeline_original_deque
    _timeline_original_popleft = _timeline_original_deque.popleft
except BaseException:
    pass  # Unavailable capture; never retry after fixture replacements.

class _SdkTimeline:
    """Partial observations only; original CPython3.12.13 popleft claims slots."""
    def __init__(self, *, clock, write):
        self._clock, self._write = clock, write
        self._free_slots = _timeline_original_deque(range(64))
        self._emit_token = _timeline_original_deque([0])
        self._rows = [None] * 64
        self._disabled = self._unavailable = self._truncated = False

    def note(self, event, owner=None, registry=()):
        try:
            index = _timeline_original_popleft(self._free_slots)
        except IndexError:
            self._truncated = True
            return  # No clock or registry work after slot exhaustion.
        except BaseException:
            self._unavailable = True
            self._disabled = True
            return
        try:
            if self._disabled:
                return  # Consume this claimed slot without reuse.
            if type(event) is not int or not 1 <= event <= 6:
                raise ValueError
            ordinal = 0
            if owner is not None:
                for position, record in enumerate(registry[:64], 1):
                    if record.actual is owner:
                        ordinal = position
                        break
                if ordinal == 0:
                    raise ValueError
            ns = self._clock()  # At most one attempt per unique slot.
            if type(ns) is not int or not 0 <= ns <= 9223372036854775807:
                raise ValueError
            row = (event, ordinal, ns)
            self._rows[index] = row  # Publish only a complete immutable tuple.
        except BaseException:
            self._unavailable = True
            self._disabled = True  # No retry, slot reuse, recapture or flag clear.

    def emit_failure(self):
        try:
            _timeline_original_popleft(self._emit_token)
        except IndexError:
            return
        except BaseException:
            self._unavailable = True
            self._disabled = True
            return
        self._disabled = True
        try:
            snapshot = []
            for index in range(64):
                row = self._rows[index]  # Inspect each cell once, no coherent epoch.
                if row is None:
                    continue
                if (type(row) is not tuple or len(row) != 3
                        or any(type(value) is not int for value in row)
                        or not 1 <= row[0] <= 6 or not 0 <= row[1] <= 64
                        or not 0 <= row[2] <= 9223372036854775807):
                    self._unavailable = True
                    continue
                snapshot.append(row)
            truncated = 1 if self._truncated else 0
            wire = ('{"kind":"SDK_TIMELINE","header":[1,0,%d,%d],"rows":[%s]}\n' % (
                truncated, len(snapshot),
                ",".join("[%d,%d,%d]" % row for row in snapshot))).encode("ascii")
            if len(wire) <= 4096 and self._write is not None:
                self._write(2, wire)  # One token, one attempt; never repair a short write.
        except BaseException:
            self._unavailable = True
            self._disabled = True
# SDK_TIMELINE_RUNTIME_HELPER_END
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
CAP_NS = 12000000000
ADAPTER_RESPONSES = {
    "print('adapter ordinary fixture')": ("  ordinary fixture\nverbatim  \n", False),
    "print('adapter rejected fixture')": ("rejected: static fixture refusal  \n", True),
    "print('adapter error fixture')": ("error: static fixture failure  \n", True),
}
SCORER_FIXTURE_STATUSES = (
    "match", "mismatch", "pred_error", "pred_timeout", "pred_truncated",
    "pred_empty", "gold_error", "gold_timeout", "gold_truncated", "db_missing")
SCORER_FIXTURE_PREDICTIONS = {
    "fixture-score-status:" + status: status for status in SCORER_FIXTURE_STATUSES}
SCORER_FIXTURE_PREDICTIONS[""] = "pred_empty"

def scorer_fixture_result(prediction):
    # Explicit static frames, not execution_accuracy, SQL, or reward evidence.
    from bench.score import ExResult
    status = SCORER_FIXTURE_PREDICTIONS[prediction]
    return ExResult(float(status == "match"), status,
                    status not in SCORER_FIXTURE_STATUSES[-4:],
                    "  static scorer fixture\nnot SQL accuracy  \n",
                    0 if status == "pred_empty" else 7, 11)

forbidden_calls = []
def forbidden(*args, **kwargs):
    forbidden_calls.append(1)
    raise AssertionError("GUEST_FIXTURE_FORBIDDEN_NATIVE_NETWORK_SQL_OR_GROUP_IO")
if MODE == "host" and PHASE.startswith("sdk-"):
    # Capture trusted methods ONCE, before denial. Only first-party numeric
    # loopback ephemeral listeners and their recorded endpoints are permitted.
    # The SDK framework wraps these already-strict methods, never an unguarded
    # socket class. Guardian/role interpreters keep the blanket guard below.
    sdk_endpoints, sdk_sockets = set(), []
    sdk_retiring = threading.Event()
    trusted_bind = socket.socket.bind
    trusted_connect, trusted_connect_ex = socket.socket.connect, socket.socket.connect_ex
    trusted_resolve = socket.getaddrinfo
    def sdk_bind(sock, address):
        if (sdk_retiring.is_set() or sock.family not in (socket.AF_INET, socket.AF_INET6)
                or not isinstance(address, tuple) or len(address) < 2
                or address[0] not in ("127.0.0.1", "::1") or address[1] != 0):
            return forbidden(sock, address)
        sdk_sockets.append(sock)  # Retain actual listener before bind.
        value = trusted_bind(sock, address)
        actual = sock.getsockname()
        sdk_endpoints.add((actual[0], actual[1]))
        return value
    def sdk_connect(sock, address):
        if (sdk_retiring.is_set() or sock.family not in (socket.AF_INET, socket.AF_INET6)
                or not isinstance(address, tuple) or len(address) < 2
                or (address[0], address[1]) not in sdk_endpoints):
            return forbidden(sock, address)
        sdk_sockets.append(sock)  # Retain actual transport socket before connect.
        return trusted_connect(sock, address)
    def sdk_connect_ex(sock, address):
        if (sdk_retiring.is_set() or sock.family not in (socket.AF_INET, socket.AF_INET6)
                or not isinstance(address, tuple) or len(address) < 2
                or (address[0], address[1]) not in sdk_endpoints):
            return forbidden(sock, address)
        sdk_sockets.append(sock)
        return trusted_connect_ex(sock, address)
    def sdk_resolve(host, port, *args, **kwargs):
        if (host, port) not in sdk_endpoints:
            return forbidden(host, port)
        return trusted_resolve(host, port, *args, **kwargs)
    socket.socket.bind = sdk_bind
    socket.socket.connect, socket.socket.connect_ex = sdk_connect, sdk_connect_ex
    socket.getaddrinfo = sdk_resolve
else:
    socket.socket.connect = socket.socket.connect_ex = socket.socket.bind = forbidden
    socket.getaddrinfo = forbidden
sqlite3.connect = forbidden
if MODE == "host" and PHASE.startswith("sdk-"):
    class ForbiddenPopen(subprocess.Popen):
        # Lazy SDK MCP imports evaluate Popen[bytes]. Construction always denies.
        def __init__(self, *args, **kwargs):
            forbidden(*args, **kwargs)
    subprocess.Popen = ForbiddenPopen
else:
    subprocess.Popen = forbidden  # Concrete _CreatorPopen's original base survives.
os.killpg = os.system = forbidden
original_kill = os.kill
def direct_only(pid, sig):
    if pid <= 0:
        return forbidden(pid, sig)
    return original_kill(pid, sig)
os.kill = direct_only

def remaining(end=END):
    return max(0.001, end - time.monotonic())

def read_line(fd, end, maximum=8192):
    data = bytearray()
    while not data.endswith(b"\n"):
        assert time.monotonic() < end, "FIXTURE_READER_DEADLINE"
        assert select.select([fd], [], [], max(0, end-time.monotonic()))[0], (
            "FIXTURE_READER_DEADLINE")
        part = os.read(fd, 1)
        assert part, "FIXTURE_READER_EOF"
        data.extend(part)
        assert len(data) <= maximum, "FIXTURE_READER_BYTE_CAP"
    return bytes(data)

def write_record(fd, item):
    raw = json.dumps(item, separators=(",", ":")).encode() + b"\n"
    assert len(raw) < 4096
    assert os.write(fd, raw) == len(raw)

# CREATOR_BOUNDARY_BEGIN
# GUARDIAN_BUDGET_BEGIN
def _guardian_budget_diagnostic(ready, safety):
    """Non-atomic budget metadata only, never a cause or physical receipt."""
    try:
        if not _guardian_budget_ready:
            return
        observed_ns = _guardian_budget_clock()
        if type(ready) is not list:
            return
        if not ready:
            reason = "TIMEOUT"
        elif (len(ready) == 1 and type(safety) is int and safety >= 0
              and type(ready[0]) is int and ready[0] == safety):
            reason = "SAFETY_READY"
        else:
            return  # Unexpected readiness does not establish either reason.
        end_ns = int(END * 1000000000)
        cutoff_ns = int((END - 3.5) * 1000000000)
        if any(type(value) is not int or not 0 <= value <= 9223372036854775807
               for value in (end_ns, cutoff_ns, observed_ns)):
            return
        wire = json.dumps(dict(
            kind="FIXTURE_GUARDIAN_BUDGET", reason=reason,
            end_ns=end_ns, cutoff_ns=cutoff_ns, observed_ns=observed_ns),
            separators=(",", ":")).encode("utf-8") + b"\n"
        if len(wire) <= 512:
            _guardian_budget_write(2, wire)  # One captured write, including short writes.
    except BaseException:
        pass  # Original diagnostics, cleanup and ownership decisions still run.
# GUARDIAN_BUDGET_END
# CREATOR_BOUNDARY_END
# CREATOR_BOUNDARY_BEGIN
# HOST_BUDGET_BEGIN
def _host_budget_diagnostic(site, ready=None, inputs=None):
    """Boundary observation only, not retirement initiation or physical proof."""
    try:
        if (type(MODE) is not str or MODE != "host"
                or type(PHASE) is not str or not PHASE.startswith("sdk-")
                or _boundary_original_ready is not True):
            return
        if type(site) is not str:
            return
        if site == "WATCHDOG_DECISION":
            if (type(inputs) is not list or len(inputs) not in (2, 3)
                    or any(type(value) is not int or value < 0 for value in inputs)
                    or inputs[0] != 0 or len(set(inputs)) != len(inputs)
                    or type(ready) is not list
                    or any(type(value) is not int or value < 0 for value in ready)):
                return
            if inputs[1] in ready:
                return  # Original DONE precedence, including combined readiness.
            if not ready:
                reason = "TIMEOUT"
            elif len(inputs) == 3 and inputs[2] in ready:
                reason = "RACE_READY"
            elif 0 in ready:
                reason = "STDIN_READY"
            else:
                reason = "OTHER"
        elif site == "HOST_EXCEPTION":
            reason = "EXCEPTION_BOUNDARY"
        else:
            return
        observed_ns = _boundary_original_clock()
        end_ns = int(END * 1000000000)
        cutoff_ns = int((END - 3.75) * 1000000000)
        if any(type(value) is not int or not 0 <= value <= 9223372036854775807
               for value in (end_ns, cutoff_ns, observed_ns)):
            return
        wire = json.dumps(dict(
            kind="FIXTURE_HOST_BUDGET", site=site, reason=reason,
            end_ns=end_ns, cutoff_ns=cutoff_ns, observed_ns=observed_ns),
            separators=(",", ":")).encode("utf-8") + b"\n"
        if len(wire) <= 512:
            _boundary_original_write(2, wire)  # One attempt, even on a short write.
    except BaseException:
        pass  # Never replace the original failure, control flow or ownership.
# HOST_BUDGET_END
# CREATOR_BOUNDARY_END
def failure_diagnostic(where, exc=None, **state):
    # Bounded code locations only: never locals, source lines, request bytes,
    # exception text, absolute paths, or synthetic proof/ACK substitutions.
    if MODE == "host" and PHASE.startswith("sdk-"):
        # SDK failures have separate bounded task/delivery inventories. Do not
        # reintroduce arbitrary SDK filenames/function names via legacy stacks.
        try:
            raw = json.dumps(dict(
                kind="FIXTURE_FAILURE_STATE", lane="host",
                where="host-error" if where == "host-error" else "OTHER",
                error="CancelledError" if type(exc) is asyncio.CancelledError else "OTHER"),
                separators=(",", ":")).encode("utf-8") + b"\n"
            os.write(2, raw)
        except BaseException:
            pass
        return
    def location(frame, line):
        return [Path(frame.f_code.co_filename).name[:64],
                frame.f_code.co_name[:64], line]
    traceback = []
    tb = exc.__traceback__ if exc is not None else None
    while tb is not None and len(traceback) < 24:
        traceback.append(location(tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
    threads = []
    for frame in list(sys._current_frames().values())[:8]:
        stack = []
        while frame is not None and len(stack) < 16:
            stack.append(location(frame, frame.f_lineno))
            frame = frame.f_back
        threads.append(stack)
    raw = json.dumps(dict(kind="FIXTURE_FAILURE_STATE", lane=MODE, where=where,
        error=type(exc).__name__ if exc is not None else None,
        traceback=traceback, threads=threads, state=state),
        separators=(",", ":")).encode() + b"\n"
    os.write(2, raw)  # Regular fixture stderr file, outside the proof channel.

# CREATOR_BOUNDARY_BEGIN
def _creator_boundary_refs(roots):
    """Resolve original code identities only against fixed, trusted source ASTs."""
    import ast
    refs = []
    for label, code, tree, path in roots:
        if type(code) is not types.CodeType or type(label) is not int or not 1 <= label <= 7:
            continue
        scope = tree
        for name in path:
            matches = [node for node in scope.body
                       if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == name]
            if len(matches) != 1:
                scope = None
                break
            scope = matches[0]
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = min([scope.lineno] + [node.lineno for node in scope.decorator_list])
        if code.co_firstlineno != first:
            continue
        # Only statements in this code's lexical scope, never a nested code's body.
        statements, pending = {}, list(scope.body)
        while pending:
            node = pending.pop()
            if isinstance(node, ast.stmt):
                statements[node.lineno] = statements.get(node.lineno, 0) + 1
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                     ast.Lambda)):
                pending.extend(ast.iter_child_nodes(node))
        coordinates = frozenset(line for line, count in statements.items()
                                if count == 1 and 0 < line <= 2147483647)
        refs.append((label, code, coordinates))
    return tuple(refs)


class _CreatorBoundaryDiagnostic:
    """Failure-only, non-atomic metadata. Neither causal nor physical proof."""
    def __init__(self, *, refs, original_thread, active, current_frames, write, clock):
        self.refs = refs
        self.original_thread, self.active = original_thread, active
        self.current_frames, self.write, self.clock = current_frames, write, clock
        self.task_type = asyncio.Task
        self.owner_ordinals, self.task_ordinals = [], []
        self.emitted = {}

    def ordinal(self, actual, retained):
        for index in range(len(retained)):
            if retained[index] is actual:
                return index + 1
        retained.append(actual)  # Keep identity alive across the two observations.
        return len(retained)

    def location(self, code, line, leaf):
        for label, original, coordinates in self.refs:
            if code is original and type(line) is int and line in coordinates:
                return [label, line, 1 if leaf else 2]
        return [0, 0, 0 if leaf else 3]

    def frames(self, frame, stream):
        if type(frame) is not types.FrameType:
            stream["flags"] |= 8
            stream["exhausted"] = True
            return
        for depth in range(8):
            row = self.location(frame.f_code, frame.f_lineno, depth == 0)
            if depth == 0 and row[0] == 0:
                stream["flags"] |= 16
            following = frame.f_back
            if following is None or depth == 7:
                stream["exhausted"] = True
            if depth == 7 and following is not None:
                stream["flags"] |= 2
            yield row
            frame = following
            if frame is None:
                return

    def coroutine(self, coroutine, stream):
        chain = []
        unknown = False
        for _ in range(8):
            if type(coroutine) is not types.CoroutineType:
                unknown = True
                stream["flags"] |= 8
                break  # Never read attributes of a foreign awaitable.
            chain.append(coroutine)
            awaited = coroutine.cr_await
            if awaited is None:
                break
            coroutine = awaited
        else:
            if awaited is not None:
                unknown = True
                stream["flags"] |= 2
        # Await links are bounded separately. Read location fields only on each
        # fair collector turn, never precompute locations beyond its total budget.
        chain.reverse()
        if unknown:
            stream["flags"] |= 16
            if len(chain) == 8:
                stream["flags"] |= 2
                chain = chain[:7]
            if not chain:
                stream["exhausted"] = True
            yield [0, 0, 0]
        leaf = not unknown
        observed = False
        for index in range(len(chain)):
            actual = chain[index]
            code, frame = actual.cr_code, actual.cr_frame
            if frame is None:
                stream["flags"] |= 8 | 16
                if leaf:
                    leaf = False
                    yield [0, 0, 0]  # Missing leaf, never promote a surviving caller.
                continue
            observed = True
            row = self.location(code, frame.f_lineno, leaf)
            if leaf and row[0] == 0:
                stream["flags"] |= 16
            if index == len(chain) - 1:
                stream["exhausted"] = True
            yield row
            leaf = False
        if not observed and not unknown:
            stream["flags"] |= 1
        stream["exhausted"] = True

    def prepare(self, site, retirement, owners, slots, trace):
        header = dict(kind="SDK_CREATOR_BOUNDARY", version=1, site=site,
                      timestamp=0, flags=1, retirement=0,
                      inspected=[0, 0, 0, 0], omitted=[0, 0, 0, 0],
                      unavailable=[0, 0, 0, 0])
        def integer(value, maximum=2147483647):
            if type(value) is not int or value < 0:
                header["flags"] |= 16
                return 0
            if value > maximum:
                header["flags"] |= 16
                return maximum
            return value
        header["timestamp"] = integer(self.clock(), 9223372036854775807)
        if {label for label, _, _ in self.refs} != {1, 2, 3, 4, 5, 6, 7}:
            header["flags"] |= 32
        retained_tasks, task_roles, task_total = [], {}, 0
        try:
            acquired = retirement.lock.acquire(False)
        except BaseException:
            acquired = False
        if not acquired:
            header["flags"] |= 2
            header["unavailable"][1] = 1
        else:
            try:
                tasks = retirement.tasks | retirement.stop_tasks | retirement.internal_tasks
                task_total = len(tasks)
                # Reference copying is not frame/coroutine/state inspection.
                retained_tasks = list(tasks)[:256]
                task_roles = {task: retirement.task_roles.get(task, ("unclassified", None))
                              for task in retained_tasks if type(task) is self.task_type}
                for bit, event in (
                        (1, retirement.requested), (2, retirement.async_started),
                        (4, retirement.async_done), (8, retirement.fallback_requested),
                        (16, retirement.complete)):
                    if event.is_set():
                        header["retirement"] |= bit
                if retirement.finalized is True:
                    header["retirement"] |= 32
            finally:
                retirement.lock.release()
        # Never hold the retirement and creator bookkeeping locks together.
        entries = []
        creator_total = 0
        try:
            acquired = trace.lock.acquire(False)
        except BaseException:
            acquired = False
        if not acquired:
            header["flags"] |= 4
            header["unavailable"][3] = 1
        else:
            try:
                creator_total = len(trace.entries)
                entries = trace.entries[:256]
            finally:
                trace.lock.release()
        inspected_owners = owners[:64]
        inspected_slots = slots[:256]
        header["unavailable"][2] += sum(type(slot) is not dict for slot in inspected_slots)
        header["unavailable"][3] += sum(type(entry) is not dict for entry in entries)
        header["inspected"] = [len(inspected_owners), len(retained_tasks),
                               len(inspected_slots), len(entries)]
        ranked_owners = []
        for actual in inspected_owners:
            ordinal = self.ordinal(actual, self.owner_ordinals)
            ranked_owners.append((actual._completion is not None, ordinal, actual))
        ranked_owners.sort(key=lambda row: row[0])  # Stable retained-owner order.
        ranked_tasks = []
        for task in retained_tasks:
            ordinal = self.ordinal(task, self.task_ordinals)
            if type(task) is not self.task_type:
                header["unavailable"][1] += 1
                continue
            status = int(self.task_type.done(task)) | (2 * int(self.task_type.cancelled(task)))
            ranked_tasks.append((bool(status & 1), ordinal, task, status))
        ranked_tasks.sort(key=lambda row: row[0])
        selected_owners, selected_tasks = ranked_owners[:8], ranked_tasks[:32]
        header["omitted"] = [
            integer(len(owners) - len(selected_owners)),
            integer(task_total - len(selected_tasks)),
            integer(len(slots) - len(inspected_slots)),
            integer(creator_total - len(entries))]
        # Candidate identities are published BEFORE the bracketed single frame read.
        candidates = []
        for _, _, actual in selected_owners:
            thread = actual._thread
            ident = thread.ident if type(thread) is self.original_thread else None
            candidates.append((thread, ident))
        before = after = current = None
        try:
            if type(self.active) is dict:
                before = self.active.copy()
                current = self.current_frames()
                after = self.active.copy()
        except BaseException:
            pass
        owner_rows, task_rows, streams = [], [], []
        states = ("ALLOCATED", "ABORT_LATCHED", "UNRESOLVED_OWNED", "ADMITTED",
                  "HOST_SEALED", "DRAINED", "GUARDIAN_REAPED", "SPAWNING",
                  "STARTING", "RUNNING", "CLEANING")
        for index in range(len(selected_owners)):
            _, ordinal, actual = selected_owners[index]
            state = actual._state
            state_id = states.index(state) + 1 if type(state) is str and state in states else 0
            completion = int(actual._completion is not None) | (2 * int(actual._intent is not None))
            row = [integer(ordinal), state_id, completion,
                   integer(len(actual._endpoints)), integer(len(actual._children)),
                   sum(type(slot) is dict and slot.get("invocation") is actual
                       for slot in inspected_slots),
                   sum(type(entry) is dict and entry.get("registry") is actual._children
                       for entry in entries), 0, 0, 0]
            stream = dict(row=row, offset=7, flags=0, locations=[], exhausted=False)
            if header["unavailable"][2] or header["unavailable"][3]:
                stream["flags"] |= 8
            if header["flags"] & 16:
                stream["flags"] |= 32
            thread, ident = candidates[index]
            associated = (
                type(thread) is self.original_thread and type(ident) is int
                and type(before) is dict and type(after) is dict
                and before.get(ident) is thread and after.get(ident) is thread
                and thread.ident == ident and type(current) is dict)
            if not associated:
                stream["flags"] |= 8
                stream["exhausted"] = True
                stream["iterator"] = iter(())
            else:
                frame = current.get(ident)
                if frame is None:
                    stream["flags"] |= 1
                    stream["exhausted"] = True
                    stream["iterator"] = iter(())
                else:
                    stream["iterator"] = self.frames(frame, stream)
            owner_rows.append(row)
            streams.append(stream)
        for _, ordinal, task, status in selected_tasks:
            role, kind = task_roles[task]
            role_id = {"unclassified": 1, "driver": 2, "cleanup": 3}.get(role, 0) if (
                type(role) is str) else 0
            kind_id = 1 if kind is None else (
                {"owner-close": 2, "resource-close": 3, "scope-drain": 4}.get(kind, 0)
                if type(kind) is str else 0)
            row = [integer(ordinal), role_id, kind_id, status, 0, 0, 0]
            stream = dict(row=row, offset=4, flags=0, locations=[], exhausted=False)
            stream["iterator"] = self.coroutine(self.task_type.get_coro(task), stream)
            task_rows.append(row)
            streams.append(stream)
        # First opportunity for EVERY stream precedes any stream's second row.
        used = 0
        for depth in range(8):
            for stream in streams:
                try:
                    if stream["exhausted"]:
                        continue
                    if used == 64:
                        stream["flags"] |= 4
                        continue
                    location = next(stream["iterator"])
                except StopIteration:
                    stream["exhausted"] = True
                    continue
                stream["locations"].append(location)
                used += 1
        # Flatten only after fair collection, keeping each stream contiguous.
        locations = []
        for stream in streams:
            row, offset = stream["row"], stream["offset"]
            row[offset:offset + 3] = [
                len(locations), len(stream["locations"]), stream["flags"]]
            locations.extend(stream["locations"])
        for row in owner_rows:
            if row[9] & 8:
                header["unavailable"][0] += 1
        for row in task_rows:
            if row[6] & 8:
                header["unavailable"][1] += 1
        if any(header["unavailable"]):
            header["flags"] |= 8
        for field in ("inspected", "omitted", "unavailable"):
            header[field] = [integer(value) for value in header[field]]
        assert len(json.dumps(header, separators=(",", ":")).encode("utf-8")) <= 512
        return dict(header, owners=owner_rows, tasks=task_rows, locations=locations)

    def emit(self, site, retirement, owners, slots, trace):
        if type(site) is not int or site not in (1, 2):
            return
        claim = object()
        if self.emitted.setdefault(site, claim) is not claim:
            return  # Atomic claim before preparation/I/O, including failures.
        try:
            report = self.prepare(site, retirement, owners, slots, trace)
            wire = json.dumps(report, separators=(",", ":")).encode("utf-8") + b"\n"
            assert len(wire) <= 6400 < 8192
            self.write(2, wire)  # Exactly one captured write, even if short/failed.
        except BaseException:
            pass  # Never replace the original error, ledger, outcome or SAFE decision.
# CREATOR_BOUNDARY_END
def role_main():
    profile = m.execution_profile_from_bytes((JOB / "profile.json").read_bytes())
    journal = json.loads((JOB / "journal.json").read_bytes())
    # Real staged-source and inert-byte checks, no SQLite connection.
    binding = getattr(profile.binding, ROLE)
    m.validate_source_pins(binding.sources, source_root=JOB / ROLE)
    digest = hashlib.sha256((JOB / "db.sqlite").read_bytes()).hexdigest()
    assert digest == journal["db_sha256"]
    assert read_line(0, END-3, 16) == b"START\n"
    bootstrap = m.BootstrapPayload(
        dict(profile.environment)["PYTHON_VERSION"], "fixture-no-sqlite",
        binding.sources, digest)
    def output(data):
        sys.stdout.buffer.write(struct.pack(">BxxxI", 1, len(data)) + data)
        sys.stdout.buffer.flush()
    output(m.READY + m.encode_wire_message(ROLE, "bootstrap", bootstrap))
    request = m.decode_wire_message(
        read_line(0, END-3, m.limits_for(ROLE).input_bytes), role=ROLE,
        kind="request", request_sha256=journal["request_sha256"]).payload
    assert m.request_sha256(request) == journal["request_sha256"]
    if ROLE == "program":
        # Explicit static wire fixtures only, never Python/SQL evaluation.
        response = m.ProgramResponse(*ADAPTER_RESPONSES[request.program]) if (
            request.program in ADAPTER_RESPONSES) else m.ProgramResponse(
                "static first-party role fixture", False)
    else:
        from bench.score import ExResult
        response = scorer_fixture_result(request.predicted_sql) if (
            request.predicted_sql in SCORER_FIXTURE_PREDICTIONS) else ExResult(
                1.0, "match", True, "static fixture, not SQL", 1, 1)
    result = m.encode_wire_message(
        ROLE, "result", response, request_sha256=journal["request_sha256"])
    if (ROLE == "scorer" and MUTANT == "invalid-target-zero"
            and request.predicted_sql == "fixture-score-status:gold_error"):
        # One static target WIRE only. Request/policy/decoder/ACK stay original.
        result = m.encode_wire_message(
            ROLE, "result", scorer_fixture_result("fixture-score-status:mismatch"),
            request_sha256=journal["request_sha256"])
    if ROLE == "program" and MUTANT == "program-observation-sentinel":
        # Directed wire-only mutation. Keep original decoder, flags/context
        # and exit-grant protocol; no replacement native response/ACK object.
        assert request.program == "print('adapter ordinary fixture')"
        envelope = json.loads(result)
        envelope["payload"]["observation"] = "directed PROGRAM observation sentinel\n"
        envelope["sha256"] = hashlib.sha256(
            m.canonical_json_bytes(envelope["payload"])).hexdigest()
        result = m.canonical_json_bytes(envelope) + b"\n"
    output(result)
    # Delegate grant validation, but give the real helper a finite pipe reader.
    class Input:
        def readline(self, maximum):
            return read_line(0, END-3, maximum)
    original_stdin = sys.stdin  # Retain FD0's actual owning TextIOWrapper.
    sys.stdin = types.SimpleNamespace(buffer=Input())
    try:
        m._worker_wait_for_exit_grant(
            ROLE, journal["request_sha256"], result, request)
    finally:
        sys.stdin = original_stdin


class CreatorTrace:
    """Independent actual-object ledger, entered BEFORE canonical BasePopen."""
    def __init__(self, emit, stopping):
        self.emit, self.stopping = emit, stopping
        self.lock = threading.RLock()
        self.entries = []
        self.mutation_hits = 0
        self.created = lambda entry: None
        original_init, original_wait = m._CreatorPopen.__init__, m._CreatorPopen.wait
        trace = self
        def constructor(process, *args, _registry, **kwargs):
            argv = args[0]
            assert argv[:3] == [sys.executable, "-I", "-B"], (
                "only fixed first-party Python commands may execute")
            kind = ("cli" if argv[3] == "-c" else
                    "guardian" if argv[4] == "guardian" else "role")
            with trace.lock:
                assert not trace.stopping.is_set(), "fixture creator retired"
                entry = dict(process=process, kind=kind, registry=_registry,
                             index=len(trace.entries), notified=False)
                trace.entries.append(entry)
                registry = _registry
                if MUTANT == "registration" and kind == "cli" and not trace.mutation_hits:
                    # DECLARED MUTANT: bypass exactly one canonical append.
                    # The independent ledger above still holds this same object.
                    trace.mutation_hits += 1
                    class Sink:
                        def append(self, actual):
                            assert actual is process
                    registry = Sink()
                original_init(process, *args, _registry=registry, **kwargs)
                registered = process in _registry
            trace.emit("RESOURCE", actor=kind, index=entry["index"],
                       registered=registered, mutation_hits=trace.mutation_hits)
            trace.created(entry)
        def wait(process, timeout=None):
            value = original_wait(process, timeout=timeout)
            with trace.lock:
                entries = [entry for entry in trace.entries
                           if entry["process"] is process]
                assert len(entries) == 1
                entry = entries[0]
                notify = not entry["notified"]
                entry["notified"] = True
            if notify:
                trace.emit("ACTUAL_WAIT", actor=entry["kind"], index=entry["index"])
            return value
        m._CreatorPopen.__init__, m._CreatorPopen.wait = constructor, wait

    def fence(self):
        with self.lock:
            return tuple(self.entries)

    def reap(self, end):
        for entry in self.fence():
            process = entry["process"]
            assert getattr(process, "pid", None) is not None
            assert not process._creator_ambiguous, "ambiguous creator, no safety proof"
            # Every operation uses the retained object and its creator lock.
            if process.poll() is None:
                process.kill()
            process.wait(timeout=remaining(end))
            assert process._creator_waited and not process._creator_ambiguous

    def evidence(self):
        return [dict(actor=entry["kind"], index=entry["index"],
                     waited=entry["process"]._creator_waited,
                     ambiguous=entry["process"]._creator_ambiguous,
                     returncode=entry["process"].returncode,
                     registered=entry["process"] in entry["registry"])
                for entry in self.fence()]


def guardian_main():
    control, cancel, gate, diagnostic, safety = map(int, sys.argv[7:12])
    stopping, lifetime = threading.Event(), threading.Event()
    stop_r, stop_w = os.pipe()
    done_r, done_w = os.pipe()
    cleanup_lock = threading.Lock()
    contexts, observers, daemons = [], [], []
    hits, fault_hits = [], []
    def emit(kind, **data):
        write_record(diagnostic, dict(kind=kind, lane="guardian", **data))
    keeper = threading.Thread(target=lifetime.wait,
                              name="guest-fixture-guardian-lifetime", daemon=False)
    keeper.start()
    trace = CreatorTrace(emit, stopping)

    def barrier(name, **data):
        hits.append(name)
        emit("HIT", name=name, **data)
        ready = select.select([gate, stop_r], [], [], remaining(END-3.5))[0]
        assert stop_r not in ready and gate in ready, "fixture guardian barrier aborted"
        assert os.read(gate, 1) == b"G"

    # Observe actual context/observer objects before either starts its thread.
    context_init, observer_init = m._OwnedContext.__init__, m._Observer.__init__
    memory_calls = []
    def protect_start(thread):
        original = thread.start
        def start():
            with trace.lock:
                assert not stopping.is_set(), "fixture thread creator retired"
                return original()
        thread.start = start
    def observe_context(self, *args, **kwargs):
        with trace.lock:
            assert not stopping.is_set()
            contexts.append(self)
            context_init(self, *args, **kwargs)
            protect_start(self.monitor)
    def observe_observer(self, *args, **kwargs):
        with trace.lock:
            assert not stopping.is_set()
            observers.append(self)
            observer_init(self, *args, **kwargs)
            protect_start(self.thread)
    m._OwnedContext.__init__, m._Observer.__init__ = observe_context, observe_observer
    sample = m._memory_sample
    def observe_sample(*args, **kwargs):
        with trace.lock:
            assert not stopping.is_set(), "fixture sample creator retired"
            done = threading.Event()
            memory_calls.append(done)
        try:
            return sample(*args, **kwargs)
        finally:
            done.set()
    m._memory_sample = observe_sample

    acquire, monitor = m._acquire_cancel_frame, m._OwnedContext._monitor
    def observe_acquisition(*args, **kwargs):
        value = acquire(*args, **kwargs)
        emit("CONSUMED", at_ns=time.monotonic_ns(), times=list(value))
        return value
    def observe_monitor(self):
        value = monitor(self)
        emit("MONITOR_DONE", error=self.error is not None,
             at_ns=time.monotonic_ns())
        return value
    m._acquire_cancel_frame, m._OwnedContext._monitor = observe_acquisition, observe_monitor

    state = types.SimpleNamespace(
        role=None, started=False, deleted=False, attached=None, role_registry=[],
        profile=None, journal=None, lock=threading.RLock())

    def actual_wait(process):
        return process.wait(timeout=remaining(min(END-3, contexts[0].cap())))

    class Attached:
        def __init__(self, process):
            self.process = process
            self.timeout = 0.1
            self.lock = threading.RLock()
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
        def settimeout(self, value):
            self.timeout = value
        def send(self, data):
            with self.lock:
                fd = self.process.stdin.fileno()
                if not select.select([], [fd], [], min(0.01, self.timeout))[1]:
                    raise socket.timeout()
                return os.write(fd, data)
        def sendall(self, data):
            end = min(END-3, contexts[0].cap(), state.journal["deadline"])
            remaining_data = memoryview(data)
            while remaining_data:
                assert time.monotonic() < end, "fake pipe send deadline"
                try:
                    remaining_data = remaining_data[self.send(remaining_data):]
                except (socket.timeout, BlockingIOError):
                    continue
        def recv(self, maximum):
            with self.lock:
                fd = self.process.stdout.fileno()
                if not select.select([fd], [], [], min(0.01, self.timeout))[0]:
                    raise socket.timeout()
                data = os.read(fd, maximum)
            if not data:
                actual_wait(self.process)
            return data
        def close(self):
            with self.lock:
                for stream in (self.process.stdin, self.process.stdout):
                    stream.close()

    class Daemon:
        def __init__(self):
            self.active, self.workers = set(), set()
            self.lock = threading.RLock()
            self.shutdown_supervision = None
            daemons.append(self)
        def call(self, method, path, *args, **kwargs):
            assert not stopping.is_set(), "fixture boundary retired"
            token, thread = object(), threading.current_thread()
            with self.lock:
                self.active.add(token)
                self.workers.add(thread)
            try:
                return self.operation(method, path, *args, **kwargs)
            finally:
                with self.lock:
                    self.active.remove(token)
                    self.workers.remove(thread)
        def operation(self, method, path, *args, **kwargs):
            if path.startswith("/images/sha256:"):
                assert method == "GET"
                return dict(Os="linux", Architecture="arm64",
                    Id="sha256:" + m.IMAGE_CONFIG_SHA256,
                    RepoDigests=["fixture@sha256:" + m.IMAGE_MANIFEST_SHA256])
            if path == "/info":
                return {"MemTotal": 1073741824}
            if path == "/containers/json":
                process = state.role
                return ([{"Id": "c"*64, "State": "running"}]
                        if process is not None and process.poll() is None else [])
            if "/stats?" in path:
                return {"memory_stats": {"usage": 1024}}
            if path.startswith("/containers/create?"):
                assert method == "POST" and state.role is None
                assert args[0] == state.journal["config"]
                state.role = m._CreatorPopen(
                    [sys.executable, "-I", "-B", SCRIPT, "role", str(JOB),
                     ROLE, str(END), *([MUTANT] if PHASE == "static-frame"
                     and MUTANT in ("program-observation-sentinel", "invalid-target-zero") else [])],
                    _registry=state.role_registry,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, close_fds=True, env=ENV, bufsize=0)
                return {"Id": "c"*64}
            assert path.startswith("/containers/" + "c"*64), path
            process = state.role
            assert process is not None
            if path.endswith("/start"):
                assert method == "POST" and not state.started
                os.write(process.stdin.fileno(), b"START\n")
                state.started = True
                return None
            if "/kill?" in path:
                assert method == "POST"
                if process.poll() is None:
                    process.kill()
                actual_wait(process)
                return None
            if method == "DELETE":
                assert process.poll() is not None and process._creator_waited
                state.deleted = True
                return None
            assert method == "GET" and path.endswith("/json")
            if state.deleted:
                assert process._creator_waited and process.poll() is not None
                raise m._HTTPFailure(404)
            alive = process.poll() is None  # Actual retained creator object.
            if not alive:
                actual_wait(process)
            config = copy.deepcopy(state.journal["config"])
            host = config.pop("HostConfig")
            host["Runtime"] = "runc"
            return dict(Id="c"*64, Name="/" + state.journal["name"],
                Image="sha256:" + m.IMAGE_MANIFEST_SHA256,
                Config=config, HostConfig=host,
                State=dict(Running=alive, Paused=False, Restarting=False,
                    Pid=process.pid if alive else 0, OOMKilled=False,
                    ExitCode=0 if alive else process.returncode,
                    Status=("running" if state.started else "created") if alive else "exited"),
                Mounts=[dict(Type="bind", Source=mount["Source"],
                    Destination=mount["Target"], RW=False, Propagation="rprivate")
                    for mount in state.journal["config"]["HostConfig"]["Mounts"]])
        def attach(self, cid):
            assert cid == "c"*64
            state.attached = Attached(state.role)
            return state.attached

    class Bridge:
        def daemon(self, profile):
            return Daemon()
        def vm_command(self, profile):
            # Actual _owned_vm_memory creates/waits this fixed memory CLI.
            return ([sys.executable, "-I", "-B", "-c",
                     "print('MemTotal: 1048576 kB\\nMemAvailable: 1048576 kB')"], ENV)
    def boundary(profile, job):
        assert job == JOB and len(contexts) == 1
        state.profile, state.journal = profile, contexts[0].journal
        return Bridge()
    m._owned_boundary_io = boundary

    def created(entry):
        if (PHASE == "cli-fault" and entry["kind"] == "cli"
                and state.role is not None and not fault_hits):
            fault_hits.append("cli-postcreation")
            barrier("cli-fault", index=entry["index"])
            raise m._Failure("transport", "declared fixture CLI postcreation fault")
    trace.created = created
    event = m._event
    def observe_event(job, kind, **values):
        value = event(job, kind, **values)
        selected = (
            PHASE == "preSTART" and kind == "START_ATTEMPT" or
            PHASE in ("inflight", "repeated", "latency-transport",
                      "task-cancel", "concurrent-execute",
                      "adapter-cancel", "score-adapter-cancel") and kind == "REQUEST_DELIVERED" or
            PHASE == "latency-startup" and kind == "GUARDIAN_ACK")
        if selected and PHASE not in hits:
            if PHASE == "adapter-cancel" and kind == "REQUEST_DELIVERED":
                barrier(PHASE, event=kind)
            else:
                barrier(PHASE)
        return value
    m._event = observe_event
    grant = m._grant_exit
    def observe_grant(*args, **kwargs):
        if PHASE == "result-reception" and "result-reception" not in hits:
            barrier("result-reception")
        return grant(*args, **kwargs)
    m._grant_exit = observe_grant
    cleanup = m._cleanup_owned
    def observe_cleanup(*args, **kwargs):
        if PHASE in ("repeated", "task-cancel", "adapter-cancel",
                     "score-adapter-cancel") and "cleanup-held" not in hits:
            barrier("cleanup-held")
        return cleanup(*args, **kwargs)
    m._cleanup_owned = observe_cleanup
    evidence = m._owned_cleanup_evidence
    def observe_evidence(*args, **kwargs):
        value = evidence(*args, **kwargs)
        if PHASE in ("unknown-proof", "protocol-before",
                     "adapter-infrastructure", "adapter-missingproof",
                     "score-adapter-infrastructure", "score-adapter-missingproof",
                     "score-adapter-shutdown") and PHASE not in hits:
            barrier(PHASE)
        if PHASE in ("unknown-proof", "adapter-missingproof",
                     "score-adapter-missingproof", "score-adapter-shutdown"):
            fault_hits.append("withheld-resource-proof")
            # DECLARED FAULT: one join proof withheld, although the independent
            # ledger still knows the physical observer actually joined.
            args[0].journal["owned_cleanup_evidence"]["observer_joined"] = False
            emit("RESOURCE_PROOF_WITHHELD", fault_hits=len(fault_hits))
            raise m._Failure("cleanup", "declared missing final resource proof")
        return value
    m._owned_cleanup_evidence = observe_evidence
    publish = m._publish_finalization
    def observe_publication(*args, **kwargs):
        value = publish(*args, **kwargs)
        if PHASE in ("publication", "latency-terminal", "protocol-after") and PHASE not in hits:
            barrier(PHASE)
        return value
    m._publish_finalization = observe_publication

    def physical_cleanup():
        with cleanup_lock:
            stopping.set()
            os.write(stop_w, b"S")  # Broadcast readiness, no reader consumes it.
            end = min(END-0.5, time.monotonic()+3.0)
            trace.fence()  # No constructor may pass its stopping check afterward.
            for observer in observers:
                observer.stop.set()
            for context in contexts:
                context.stop.set()
            trace.reap(end)  # Kill/wait direct role/CLI objects before thread joins.
            for call in tuple(memory_calls):
                assert call.wait(timeout=remaining(end)), "memory creator call did not exit"
            for context in contexts:
                for pool in tuple(context.executors):
                    pool.shutdown(wait=False, cancel_futures=False)
                    for thread in tuple(pool._threads):
                        thread.join(timeout=remaining(end))
                        assert not thread.is_alive(), "safety executor join absent"
            for observer in observers:
                if observer.thread.ident is not None:
                    observer.thread.join(timeout=remaining(end))
                assert not observer.thread.is_alive(), "safety observer join absent"
            for context in contexts:
                if context.monitor.ident is not None:
                    context.monitor.join(timeout=remaining(end))
                assert not context.monitor.is_alive(), "safety monitor join absent"
            if state.attached is not None:
                state.attached.close()
            # Fence again: the independent ledger, not the canonical registry,
            # proves all actual children absent even under registration mutation.
            trace.reap(end)
            assert all(entry["process"]._creator_waited for entry in trace.fence())
            return trace.evidence()

    def watchdog():
        ready = select.select([safety, done_r], [], [], remaining(END-3.5))[0]
        if done_r in ready:
            return
# CREATOR_BOUNDARY_BEGIN
# GUARDIAN_BUDGET_BEGIN
        _guardian_budget_diagnostic(ready, safety)
# GUARDIAN_BUDGET_END
# CREATOR_BOUNDARY_END
        failure_diagnostic("guardian-before-safety", hits=hits[-8:],
            published=[context.published for context in contexts[:2]],
            monitor_alive=[context.monitor.is_alive() for context in contexts[:2]])
        try:
            actual = physical_cleanup()
            emit("SAFE", actual=actual, independent=True, forbidden=len(forbidden_calls))
        except BaseException as exc:
            emit("UNSAFE", error=type(exc).__name__ + ": " + str(exc))
            return  # Non-daemon lifetime owner deliberately preserves ownership.
        os._exit(88)  # No public ACK can be rescued by independent teardown.
    supervisor = threading.Thread(target=watchdog, name="guest-fixture-safety", daemon=False)
    supervisor.start()
    try:
        m._owned_guardian(JOB, control, cancel, False)
        actual = trace.evidence()  # Capture BEFORE independent cleanup.
        assert all(row["waited"] and not row["ambiguous"] for row in actual)
        assert all(not context.monitor.is_alive() for context in contexts)
        assert all(not observer.thread.is_alive() for observer in observers)
        assert all(not thread.is_alive() for context in contexts
                   for pool in context.executors for thread in pool._threads)
        assert all(not daemon.active and not daemon.workers for daemon in daemons)
        assert state.attached is None or (
            state.role.stdin.closed and state.role.stdout.closed)
        emit("EVIDENCE", actual=actual, hits=hits, fault_hits=fault_hits,
             forbidden=len(forbidden_calls), observers=len(observers),
             monitor_times=[list(context.times) if context.times else None
                            for context in contexts],
             accounted=[context.error is context.accounted_error
                        for context in contexts],
             released=state.deleted)
        actual = physical_cleanup()
        emit("SAFE", actual=actual, independent=True, forbidden=len(forbidden_calls))
        lifetime.set()
        keeper.join(timeout=0.2)
        assert not keeper.is_alive()
        os.write(done_w, b"D")
        supervisor.join(timeout=0.2)
        assert not supervisor.is_alive()
    except BaseException as exc:
        failure_diagnostic("guardian-error", exc, hits=hits[-8:])
        emit("GUARDIAN_ERROR", error=type(exc).__name__ if PHASE.startswith(
            "score-adapter-") else type(exc).__name__ + ": " + str(exc),
             fault_hits=fault_hits)
        # Ordinary errors MUST NOT exit a supervisor owning nested work. Only
        # the independent watchdog can discharge this non-daemon lifetime.
        lifetime.wait()


def host_main():
    _sdk_timeline = None
    if PHASE == "sdk-positive-two":
        try:
            _sdk_timeline = _SdkTimeline(
                clock=_boundary_original_clock if _boundary_original_ready else None,
                write=_boundary_original_write if _boundary_original_ready else None)
            _sdk_timeline.note(1)
        except BaseException:
            pass
    root = Path(ROOT)
    stopping, finished = threading.Event(), threading.Event()
    spawn_lock, cleanup_lock = threading.Lock(), threading.Lock()
    done_r, done_w = os.pipe()
    owner = None
    owners = []
    unresolved_owners = []
    slots, messages, gates = [], [], []
    queue = asyncio.Queue()
    host_hits, host_faults = [], []
    mutation_hits = [0]
    cached_validation = [None]
    cancel_write_original = [None]
    sdk_resources = None
# CREATOR_BOUNDARY_BEGIN
    creator_boundary = None
# CREATOR_BOUNDARY_END
    sdk_test_gates = None
    sdk_watchdog_race = sdk_wake_setup_error = None
    if PHASE.startswith("sdk-"):
        from ptc.test_owned_sql_sdk_canonical import _SdkRetirement
        def disable_sdk():
            stopping.set()
            sdk_retiring.set()
        # Register the staged physical owner BEFORE any SDK bridge/framework
        # construction. Never substitute its evidence for a public owner ACK.
        sdk_resources = _SdkRetirement(
            loop=LOOP, deadline=END-0.25, disable=disable_sdk,
            cooperative_cutoff=END-3.75)
        sdk_resources.cancel_receipts = []
        def ensure_sdk_intents():
            def cancel(actual):
                previous = [receipt for retained, receipt in
                            tuple(sdk_resources.cancel_receipts) if retained is actual]
                if previous:
                    receipt = previous[0]
                else:
                    receipt = actual.request_cancel("runner_closed")
                    sdk_resources.cancel_receipts.append((actual, receipt))
                if receipt.status == "already_completed":
                    assert actual._completion is not None
                else:
                    assert receipt.status in ("accepted", "repeated")
                    assert receipt.intent is not None
                    assert receipt.intent is actual.snapshot().intent
                return receipt
            retained = tuple(owners)
            receipts = sdk_resources.attempt_each("owner-cancel", retained, cancel)
            assert len(receipts) == len(retained), "SDK_PUBLIC_INTENT_MISSING"

        sdk_test_gates = _ObservedTestGates(ensure_intents=ensure_sdk_intents)

        def release_sdk_controllers():
            # ALL original public intents precede ANY fixture gate release.
            ensure_sdk_intents()
            for event in tuple(gates):
                if not event.is_set():
                    event.set()
            sdk_resources.attempt_each(
                "test-gate", (None,), lambda _: sdk_test_gates.release_pending())
        sdk_resources.release = release_sdk_controllers
        async def close_sdk_sockets():
            # These sockets alias SDK-owned listeners/transports. Start this
            # fallback with all stops, but let the actual owners unregister
            # them before closing any remaining descriptors. Stop errors
            # remain on their original tasks for retirement qualification.
            current = asyncio.current_task()
            stops = tuple(record.task for record in sdk_resources.resources
                          if record.task is not None and record.task is not current)
            if stops:
                await asyncio.gather(*stops, return_exceptions=True)
            sdk_resources.attempt_each(
                "socket-close", sdk_sockets, lambda actual: actual.close())
        sdk_resources.retain_resource(
            "fixture-sockets", sdk_sockets, close_sdk_sockets,
            lambda: all(actual.fileno() == -1 for actual in sdk_sockets))
        if PHASE == "sdk-retire-watchdog-race":
            from ptc.test_owned_sql_sdk_retirement_physical import _sdk_watchdog_wake
            try:
                sdk_watchdog_race = _sdk_watchdog_wake(
                    PHASE, sdk_resources, cleanup_lock, spawn_lock)
            except BaseException as exc:
                # Even a partial pipe constructor belongs to staged retirement,
                # not an ordinary setup exit before the lifetime owner starts.
                sdk_wake_setup_error = exc
    keeper = threading.Thread(target=finished.wait,
                              name="guest-fixture-host-lifetime", daemon=False)
    keeper.start()
    def emit(kind, **data):
        item = dict(kind=kind, lane="host", **data)
        LOOP.call_soon_threadsafe(queue.put_nowait, item)

    def sdk_diagnostic(kind, report):
        # Closed allowlisted payloads only, stderr is not the SAFE channel.
        try:
            assert kind in ("SDK_CANCEL_DELIVERY", "SDK_RETIREMENT_REFUSAL")
            raw = json.dumps(dict(kind=kind, diagnostic=report),
                             separators=(",", ":")).encode("utf-8") + b"\n"
            assert len(raw) <= 8192
            os.write(2, raw)
        except BaseException:
            pass  # Never suppress actual cleanup/proof because emission failed.
# CREATOR_BOUNDARY_BEGIN
        if kind == "SDK_RETIREMENT_REFUSAL" and creator_boundary is not None:
            try:
                creator_boundary.emit(2, sdk_resources, owners, slots, trace)
            except BaseException:
                pass
# CREATOR_BOUNDARY_END

    if sdk_resources is not None:
        sdk_resources.emit_diagnostic = lambda report: sdk_diagnostic(
            "SDK_RETIREMENT_REFUSAL", report)
    trace = CreatorTrace(emit, stopping)

    def release_sdk_gate(slot):
        # Same genuine gate mechanism as ordinary release, exactly one token.
        assert os.write(slot["gate_w"], b"G") == 1

    def reader(slot):
        buffer = bytearray()
        try:
            while time.monotonic() < END-0.5:
                ready = select.select([slot["diagnostic_r"], slot["reader_stop_r"]],
                                      [], [], remaining(END-0.5))[0]
                if slot["reader_stop_r"] in ready:
                    return
                if slot["diagnostic_r"] not in ready:
                    return
                chunk = os.read(slot["diagnostic_r"], 4096)
                if not chunk:
                    LOOP.call_soon_threadsafe(queue.put_nowait, dict(kind="DIAGNOSTIC_EOF"))
                    return
                buffer.extend(chunk)
                assert len(buffer) <= 8192
                while b"\n" in buffer:
                    raw, _, rest = buffer.partition(b"\n")
                    buffer[:] = rest
                    item = json.loads(raw)
                    item["invocation_id"] = slot["invocation_id"]
                    if sdk_test_gates is not None and item["kind"] == "HIT":
                        sdk_test_gates.observe(
                            item, lambda slot=slot: release_sdk_gate(slot))
                    slot["messages"].append(item)  # Observe BEFORE publication.
                    if item["kind"] == "SAFE":
                        assert item.get("independent") is True
                        assert all(row["waited"] and not row["ambiguous"]
                                   and type(row["returncode"]) is int for row in item["actual"])
                        slot["safe"].set()
                    LOOP.call_soon_threadsafe(queue.put_nowait, item)
        except BaseException as exc:
            LOOP.call_soon_threadsafe(queue.put_nowait,
                dict(kind="READER_ERROR", error=type(exc).__name__ if
                     sdk_resources is not None else type(exc).__name__ + ": " + str(exc)))

    def host_barrier(name):
        event = threading.Event()
        gates.append(event)
        host_hits.append(name)
        emit("HIT", name=name)
        assert event.wait(timeout=remaining(END-3.5)), "host barrier deadline"
        assert not stopping.is_set(), "host barrier aborted by safety teardown"

    def spawn(invocation, job, control_fd, cancel_fd, lock_fd, log, emergency=False):
        with spawn_lock:
            assert not stopping.is_set() and not emergency
            gate_r, gate_w = os.pipe()
            diagnostic_r, diagnostic_w = os.pipe()
            safety_r, safety_w = os.pipe()
            stop_r, stop_w = os.pipe()
            slot = dict(gate_w=gate_w, diagnostic_r=diagnostic_r, safety_w=safety_w,
                safe=threading.Event(), messages=[], reader_stop_r=stop_r,
                reader_stop_w=stop_w, invocation=invocation,
                invocation_id=invocation.invocation_id.hex,
                fds=[gate_w, diagnostic_r, safety_w, stop_r, stop_w])
            slots.append(slot)  # Register channels before actual BasePopen.
            thread = threading.Thread(target=reader, args=(slot,),
                                      name="guest-fixture-diagnostics", daemon=False)
            slot["reader"] = thread
            thread.start()
            try:
                process = invocation._spawn(
                    [sys.executable, "-I", "-B", SCRIPT, "guardian", str(job),
                     invocation.role if PHASE.startswith("sdk-") else ROLE,
                     ("adapter-cancel" if PHASE == "sdk-cancel-program"
                      and invocation.role == "program" else
                      "score-adapter-cancel" if PHASE == "sdk-cancel-scorer"
                      and invocation.role == "scorer" else
                      "static-frame" if PHASE.startswith("sdk-") else PHASE),
                     MUTANT, str(END), str(control_fd), str(cancel_fd),
                     str(gate_r), str(diagnostic_w), str(safety_r)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
                    pass_fds=(control_fd, cancel_fd, lock_fd, gate_r, diagnostic_w, safety_r),
                    close_fds=True, env=ENV)
                slot["process"] = process
            finally:
                for fd in (gate_r, diagnostic_w, safety_r):
                    os.close(fd)
            original_wait = process.wait
            selected = PHASE in (
                "postwire", "late-ambiguous", "postreap-fault",
                "invalid-current-proof", "late-after-role-deadline")
            used = [False]
            def post_wait(timeout=None):
                value = original_wait(timeout=timeout)
                if selected and not used[0] and not stopping.is_set():
                    used[0] = True
                    host_barrier(PHASE)
                    if PHASE == "postreap-fault":
                        host_faults.append("postreap")
                        emit("POSTREAP_FAULT", count=len(host_faults))
                        raise m._Failure("cleanup", "declared fixture post-reap fault")
                return value
            process.wait = post_wait
            return process
    m._spawn_owned_guardian = spawn
# CREATOR_BOUNDARY_BEGIN
    if sdk_resources is not None and _boundary_original_ready:
        try:
            # No acceptance has run. Capture the installed original fixture code
            # and canonical nested code without invoking either.
            from ptc.test_owned_sql_sdk_canonical import _sdk_acceptance
            _boundary_original_acceptance = _sdk_acceptance.__code__
            _boundary_close_codes = [
                code for code in _boundary_original_acceptance.co_consts
                if type(code) is types.CodeType and code.co_name == "observed_close"]
            _boundary_original_close = (
                _boundary_close_codes[0] if len(_boundary_close_codes) == 1 else None)
            creator_boundary = _CreatorBoundaryDiagnostic(
                refs=(), original_thread=_boundary_original_thread,
                active=_boundary_original_active, current_frames=_boundary_original_frames,
                write=_boundary_original_write, clock=_boundary_original_clock)
            import ast
            _boundary_core_source = (Path(SOURCE) / "ptc/sql_isolation.py").read_bytes()
            _boundary_canonical_source = (
                Path(SOURCE) / "ptc/test_owned_sql_sdk_canonical.py").read_bytes()
            assert hashlib.sha256(_boundary_core_source).hexdigest() == (
                "25e76d1b0f4a96a57712a837a1a092db4442bc31eba0ca0a0336d0f7a749968e")
            assert hashlib.sha256(_boundary_canonical_source).hexdigest() == (
                "493a905b3fa99116e67bbaa0120ab0e16d85fb0256f2c364ff478742567c671e")
            _boundary_core_ast = ast.parse(_boundary_core_source)
            _boundary_canonical_ast = ast.parse(_boundary_canonical_source)
            _boundary_guest_ast = ast.parse(Path(SCRIPT).read_bytes())
            _boundary_roots = (
                (1, _boundary_original_core[0], _boundary_core_ast,
                 ("OwnedSqlInvocation", "_controller")),
                (2, _boundary_original_core[1], _boundary_core_ast,
                 ("OwnedSqlInvocation", "_register_pipe")),
                (3, _boundary_original_core[2], _boundary_core_ast,
                 ("OwnedSqlInvocation", "_wait_startup")),
                (4, _boundary_original_core[3], _boundary_core_ast,
                 ("_CreatorPopen", "__init__")),
                (5, spawn.__code__, _boundary_guest_ast, ("host_main", "spawn")),
                (6, m._CreatorPopen.__init__.__code__, _boundary_guest_ast,
                 ("CreatorTrace", "__init__", "constructor")),
                (7, _boundary_original_close, _boundary_canonical_ast,
                 ("_sdk_acceptance", "observed_close")))
            creator_boundary.refs = _creator_boundary_refs(_boundary_roots)
        except BaseException:
            pass  # Missing/ambiguous source stays unavailable, never alters retirement.
# CREATOR_BOUNDARY_END

    acquire = m._acquire_cancel_frame
    def observe_acquisition(*args, **kwargs):
        value = acquire(*args, **kwargs)
        identity = {"invocation_id": args[1].hex} if PHASE.startswith(
            ("score-adapter-", "sdk-")) else {}
        emit("CONSUMED", at_ns=time.monotonic_ns(), times=list(value), **identity)
        return value
    m._acquire_cancel_frame = observe_acquisition
    validate = m._validate_finalization
    def observe_validation(*args, **kwargs):
        caller = sys._getframe(1).f_code.co_name
        if PHASE in ("invalid-current-proof", "late-ambiguous") and caller == "_seal":
            assert cached_validation[0] is not None
            assert not host_faults
            host_faults.append("withheld-current-proof")
            marker = owner.executor.profile.shared_state_dir / (
                "UNRESOLVED-" + owner.invocation_id.hex + ".json")
            m._publish_immutable(marker, m.canonical_json_bytes(
                {"fixture": "current resource proof withheld"}) + b"\n")
            emit("CURRENT_PROOF_WITHHELD", count=len(host_faults))
            if MUTANT == "cleanup-validation":
                # DECLARED MUTANT: one stale ACTUAL prior validator result,
                # bypassing precisely the final current-resource validation.
                mutation_hits[0] += 1
                return cached_validation[0]
        value = validate(*args, **kwargs)
        if kwargs.get("current") and caller == "_terminal":
            cached_validation[0] = value
        return value
    m._validate_finalization = observe_validation

    native_started, native_done = threading.Event(), threading.Event()
    native_retained, native_fds, native_objects, native_endpoints = [], set(), [], []
    native_entries, native_fenced = [], [False, False]

    def sdk_native_proof():
        # Current actual-object evidence, never the absence of an event/PID.
        if not native_done.is_set() or not all(native_fenced):
            return False
        if not all(slot["safe"].is_set() for slot in slots):
            return False
        for entry in native_entries:
            actual = entry["process"]
            if (not getattr(actual, "_creator_waited", False)
                    or getattr(actual, "_creator_ambiguous", True)
                    or type(actual.returncode) is not int):
                return False
        if any(getattr(actual, "_thread", None) is not None
               and actual._thread.is_alive() for actual in native_retained):
            return False
        for actual in native_retained:
            if (getattr(actual, "_resources", ())
                    or getattr(actual, "_host_read", None) is not None
                    or getattr(actual, "_seal_lock_fd", None) is not None
                    or any(endpoint.fd is not None
                           for endpoint in getattr(actual, "_endpoints", ()))):
                return False
        if any(slot["reader"].is_alive() for slot in slots):
            return False
        for fd in native_fds:
            try:
                os.fstat(fd)
            except OSError as exc:
                if exc.errno == 9:
                    continue
                return False
            return False
        return (all(getattr(actual, "closed", False) for actual in native_objects)
                and all(endpoint.fd is None for endpoint in native_endpoints))

    def sdk_native_cleanup():
        # Claim under a SHORT lock. Concurrent callers wait ONLY outside it;
        # no SDK completion or loop work is awaited with cleanup_lock held.
        race = (sdk_watchdog_race if sdk_watchdog_race is not None
                and sdk_watchdog_race.reads == 1 else None)
        call = race.native_enter() if race is not None else None
        with cleanup_lock:
            claimed = not native_started.is_set()
            if claimed:
                native_started.set()
        if race is not None:
            race.native_claim(call, claimed)  # AFTER releasing cleanup_lock.
        if not claimed:
            native_done.wait(timeout=max(0, END-0.25-time.monotonic()))
            if race is not None:
                race.join_supervisor_native()
            proof = sdk_native_proof()
            if race is not None:
                race.native_exit(call, proof)
            return proof
        end = END-0.25
        attempt = sdk_resources.attempt_each
        if PHASE == "sdk-retire-two-slot-verification":
            def attempt(stage, items, action):
                def observed(actual):
                    sdk_resources.physical_probe.note_native_attempt(stage, actual)
                    return action(actual)
                return sdk_resources.attempt_each(stage, items, observed)
        stopping.set()
        attempt("release", (None,), lambda _: release_sdk_controllers())

        def close_fd(fd):
            native_fds.add(fd)
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != 9:
                    raise

        def signal(slot):
            try:
                os.write(slot["safety_w"], b"S")
            except BrokenPipeError:
                pass

        def nested_safe(slot):
            # Exited guardians owe the SAME nested proof; never kill one
            # owning unknown descendants just to satisfy an outer timeout.
            assert slot["safe"].wait(max(0, end-time.monotonic())), (
                "GUARDIAN_NESTED_SAFE_PROOF_MISSING")
            if PHASE == "sdk-retire-two-slot-verification":
                sdk_resources.physical_probe.after_slot_safe(slot)

        def reap(entry):
            actual = entry["process"]
            matching = [slot for slot in slots
                        if slot["invocation"]._children is entry["registry"]]
            assert len(matching) == 1 and matching[0]["safe"].is_set()
            assert getattr(actual, "pid", None) is not None
            assert not actual._creator_ambiguous
            if actual.poll() is None:
                actual.kill()
            actual.wait(timeout=max(0, end-time.monotonic()))
            assert actual._creator_waited and not actual._creator_ambiguous

        def retire_owner(actual):
            assert native_fenced[0], "OWNER_CREATOR_FENCE_MISSING"
            if not hasattr(actual, "_lock"):
                assert not getattr(actual, "_resources", ())
                assert getattr(actual, "_thread", None) is None
                return
            if hasattr(actual, "_retained"):
                actual._retained.set()  # Physical release, not public ACK.
            thread = getattr(actual, "_thread", None)
            if thread is not None:
                thread.join(timeout=max(0, end-time.monotonic()))
                assert not thread.is_alive(), "HOST_CONTROLLER_JOIN_ABSENT"
            assert actual._lock.acquire(timeout=max(0, end-time.monotonic()))
            try:
                endpoints = tuple(getattr(actual, "_endpoints", ()))
                native_endpoints.extend(endpoints)
                native_fds.update(endpoint.fd for endpoint in endpoints
                                  if endpoint.fd is not None)
                attempt("endpoint", endpoints, lambda endpoint: endpoint.close())
                resources = tuple(getattr(actual, "_resources", ()))
                fds = {item for item in resources if type(item) is int}
                if getattr(actual, "_host_read", None) is not None:
                    fds.add(actual._host_read)
                attempt("owner-fd", fds, close_fd)
                objects = [item for item in resources if type(item) is not int]
                native_objects.extend(objects)
                attempt("owner-object", objects, lambda item: item.close())
                if hasattr(actual, "_resources"):
                    actual._resources.clear()
                actual._host_read = actual._seal_lock_fd = None
            finally:
                actual._lock.release()

        def stop_reader(slot):
            os.write(slot["reader_stop_w"], b"S")
            slot["reader"].join(timeout=max(0, end-time.monotonic()))
            assert not slot["reader"].is_alive(), "DIAGNOSTIC_READER_JOIN_ABSENT"

        def close_streams(entry):
            actual = entry["process"]
            assert actual._creator_waited and not actual._creator_ambiguous
            streams = [stream for stream in (actual.stdin, actual.stdout, actual.stderr)
                       if stream is not None]
            native_objects.extend(streams)
            attempt("creator-stream", streams, lambda stream: stream.close())

        def freeze_owners(_):
            assert spawn_lock.acquire(timeout=max(0, end-time.monotonic()))
            try:
                native_retained.extend(owners if owners else (
                    () if owner is None else (owner,)))
                native_fenced[0] = True
            finally:
                spawn_lock.release()

        def freeze_creators(_):
            assert native_fenced[0], "CREATOR_CONSTRUCTION_NOT_FENCED"
            assert trace.lock.acquire(timeout=max(0, end-time.monotonic()))
            try:
                native_entries.extend(trace.entries)
                native_fenced[1] = True
            finally:
                trace.lock.release()

        try:
            attempt("owner-fence", (None,), freeze_owners)
            attempt("creator-fence", (None,), freeze_creators)
            # Signal ALL slots first. One failed slot cannot skip any later
            # slot, creator, owner, reader, descriptor or stream attempt.
            attempt("guardian-signal", slots, signal)
            attempt("guardian-safe", slots, nested_safe)
            attempt("creator-reap", native_entries, reap)
            attempt("controller", tuple(owners) if owners else native_retained, retire_owner)
            attempt("reader", slots, stop_reader)
            for slot in slots:
                attempt("slot-fd", slot["fds"], close_fd)
            attempt("creator-streams", native_entries, close_streams)
        finally:
            native_done.set()
        proof = sdk_native_proof()
        if race is not None:
            race.native_exit(call, proof)
        return proof

    def cleanup():
        if sdk_resources is not None:
            return sdk_native_cleanup()
        stopping.set()
        for event in gates:
            event.set()
        with cleanup_lock:
            if finished.is_set():
                return
            with spawn_lock:
                # Fence constructors, retain every partial adapter allocation.
                retained = tuple(owners) if owners else (() if owner is None else (owner,))
            end = min(END-0.25, time.monotonic()+3.25)
            for slot in slots:
                try:
                    os.write(slot["safety_w"], b"S")
                except BrokenPipeError:
                    pass
                # SAFE remains mandatory even when the guardian has exited.
                assert slot["safe"].wait(timeout=remaining(end)), (
                    "GUARDIAN_NESTED_SAFE_PROOF_MISSING")
            trace.reap(end)
            for current in retained:
                if not hasattr(current, "_lock"):
                    # Canonical __init__ has not reached any resource creation.
                    assert not getattr(current, "_resources", ())
                    assert getattr(current, "_thread", None) is None
                    continue
                if hasattr(current, "_retained"):
                    current._retained.set()  # Physical safety only, never an ACK.
                if getattr(current, "_thread", None) is not None:
                    current._thread.join(timeout=remaining(end))
                    assert not current._thread.is_alive(), "host controller join absent"
                with current._lock:
                    for endpoint in getattr(current, "_endpoints", ()):
                        endpoint.close()
                    resources = getattr(current, "_resources", ())
                    fds = {item for item in resources if type(item) is int}
                    if getattr(current, "_host_read", None) is not None:
                        fds.add(current._host_read)
                    for fd in fds:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                    for item in resources:
                        if type(item) is not int:
                            item.close()
                    if hasattr(current, "_resources"):
                        current._resources.clear()
                    current._host_read = current._seal_lock_fd = None
            for slot in slots:
                os.write(slot["reader_stop_w"], b"S")
                slot["reader"].join(timeout=remaining(end))
                assert not slot["reader"].is_alive(), "diagnostic reader join absent"
                for fd in slot["fds"]:
                    os.close(fd)
            for entry in trace.fence():
                for stream in (entry["process"].stdin, entry["process"].stdout,
                               entry["process"].stderr):
                    if stream is not None:
                        stream.close()
            finished.set()

    def report(result, code):
        assert finished.is_set()
        if sdk_resources is not None:
            if not sdk_resources.prove_safe():
                return
            probe = getattr(sdk_resources, "physical_probe", None)
            if probe is not None:
                # Acceptance qualification cannot interrupt physical teardown
                # or suppress its real SAFE. A failed qualifier is NOT an
                # expected-failure pass in the outer driver.
                try:
                    proof = probe.qualify()
                except BaseException as exc:
                    sdk_resources.fail("physical-qualifier", exc)

                    def error_origin(error):
                        origin = error.__traceback__
                        if origin is None:
                            return None
                        while origin.tb_next is not None:
                            origin = origin.tb_next
                        return dict(
                            file=Path(origin.tb_frame.f_code.co_filename).name,
                            line=origin.tb_lineno)
                    proof = dict(verified=False, phase=probe.phase,
                                 fault_hits=probe.fault_hits,
                                 qualification_error=type(exc).__name__,
                                 qualification_origin=error_origin(exc),
                                 retirement_error_count=len(sdk_resources.errors),
                                 retirement_error_types=[
                                     dict(stage=stage[:64], error=type(error).__name__,
                                          origin=error_origin(error))
                                     for stage, error in sdk_resources.errors[:16]])
                result = dict(result, physical_qualification=proof)
            if sdk_resources.outcome is not None:
                result = dict(result, **sdk_resources.outcome)
            result.update(
                retirement_stages=dict(sdk_resources.stages),
                executor_workers=len(sdk_resources.workers),
                live_executor_workers=sum(actual.is_alive()
                                          for actual in sdk_resources.workers),
                executor_helpers=len(sdk_resources.executor_helpers),
                live_executor_helpers=sum(actual.is_alive()
                                          for actual in sdk_resources.executor_helpers),
                physical_finalized=sdk_resources.finalized,
                retirement_errors=len(sdk_resources.errors))
            if PHASE in (
                    "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                    "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                    "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                    "sdk-sibling-score-failure"):
                primary = sdk_resources.primary
                nonprimary = sum(error is not primary for _, error in sdk_resources.errors)
                open_fds = 0
                for fd in native_fds:
                    try:
                        os.fstat(fd)
                    except OSError as exc:
                        if exc.errno != 9:
                            raise
                    else:
                        open_fds += 1
                result["program_physical"] = dict(
                    native_proof=sdk_native_proof(), slots=len(slots),
                    nested_safe=sum(slot["safe"].is_set() for slot in slots),
                    creators=len(native_entries),
                    creator_waits=sum(getattr(entry["process"], "_creator_waited", False)
                                      for entry in native_entries),
                    ambiguous_creators=sum(getattr(
                        entry["process"], "_creator_ambiguous", True) for entry in native_entries),
                    live_readers=sum(slot["reader"].is_alive() for slot in slots),
                    open_slot_fds=open_fds,
                    resource_stop_calls=[record.stop_calls for record in sdk_resources.resources],
                    resource_errors=sum(
                        record.task is None or not record.task.done()
                        or record.task.cancelled() or record.task.exception() is not None
                        for record in sdk_resources.resources),
                    nonprimary_errors=nonprimary)
                failure = getattr(sdk_resources, "program_failure", None)
                if (failure is not None and sdk_resources.finalized
                        and sdk_native_proof() and nonprimary == 0):
                    result["acceptance_failure"] = failure
                else:
                    result.pop("acceptance_failure", None)
            if PHASE in (
                    "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                    "sdk-invalid-gold_truncated", "sdk-invalid-db_missing"):
                result["invalid_qualification"] = dict(
                    verified=False, status=PHASE.removeprefix("sdk-invalid-"))
                try:
                    controller = sdk_resources.invalid_controller
                    proof = controller.qualify(result["program_physical"])
                    if sdk_resources.invalid_control:
                        result["invalid_control_qualification"] = proof
                    else:
                        result["invalid_qualification"] = proof
                except BaseException as exc:
                    sdk_resources.fail("invalid-qualifier", exc)
                    result.update(sdk_resources.outcome or {})
                    result["retirement_errors"] = len(sdk_resources.errors)
            if PHASE == "sdk-sibling-score-failure":
                from ptc.test_owned_sql_sdk_canonical import _sdk_sibling_qualification
                result["sibling_qualification"] = dict(verified=False)
                try:
                    proof = _sdk_sibling_qualification(sdk_resources, result["program_physical"])
                    if proof.get("gate") == "SDK_SIBLING_FAULT_ORIGIN":
                        result["sibling_control_qualification"] = proof
                    else:
                        result["sibling_qualification"] = proof
                except BaseException as exc:
                    sdk_resources.fail("sibling-qualifier", exc)
                    result.update(sdk_resources.outcome or {})
                    result["retirement_errors"] = len(sdk_resources.errors)
                # Fresh FINAL ledger after the unchanged qualifier and physical
                # retirement. One bounded stderr attempt, never outcome proof.
                try:
                    from ptc.test_owned_sql_sdk_canonical import _sdk_sibling_error_diagnostic
                    diagnostic = _sdk_sibling_error_diagnostic(
                        sdk_resources, getattr(sdk_resources, "sibling_diagnostic_refs", ()))
                    raw = (json.dumps(dict(
                        kind="SDK_SIBLING_FINAL_LEDGER", diagnostic=diagnostic),
                        separators=(",", ":")) + "\n").encode("utf-8")
                    if len(raw) > 8192:
                        raise ValueError("SDK_SIBLING_FINAL_LEDGER_UNAVAILABLE")
                except BaseException:
                    raw = b'{"kind":"SDK_SIBLING_FINAL_LEDGER_UNAVAILABLE"}\n'
                try:
                    os.write(2, raw)  # No retry, including after a short write.
                except BaseException:
                    pass
            if PHASE == "sdk-scoring-timeout":
                from ptc.test_owned_sql_sdk_canonical import _sdk_timeout_qualification
                result["timeout_qualification"] = dict(verified=False)
                try:
                    proof = _sdk_timeout_qualification(sdk_resources, result["program_physical"])
                    if sdk_resources.timeout_bundle.mutant == "timeout-early-public-release":
                        result["timeout_control_qualification"] = proof
                    else:
                        result["timeout_qualification"] = proof
                except BaseException as exc:
                    sdk_resources.fail("timeout-qualifier", exc)
                    result.update(sdk_resources.outcome or {})
                    result["retirement_errors"] = len(sdk_resources.errors)
                # FINAL ledger, after qualifier failure was recorded. Diagnostic
                # failure must not alter qualification, SAFE or stdout protocol.
                try:
                    from ptc.test_owned_sql_sdk_canonical import _sdk_timeout_error_diagnostic
                    diagnostic = _sdk_timeout_error_diagnostic(
                        sdk_resources, getattr(sdk_resources, "timeout_diagnostic_refs", ()))
                    raw = (json.dumps(dict(
                        kind="SDK_TIMEOUT_FINAL_LEDGER", diagnostic=diagnostic),
                        separators=(",", ":")) + "\n").encode("utf-8")
                    if len(raw) > 8192:
                        raise ValueError("SDK_TIMEOUT_FINAL_LEDGER_UNAVAILABLE")
                except BaseException:
                    raw = b'{"kind":"SDK_TIMEOUT_FINAL_LEDGER_UNAVAILABLE"}\n'
                try:
                    os.write(2, raw)  # One attempt; no retry after possible partial emission.
                except BaseException:
                    pass
            if result.get("ok") is not True:
                code = 1
        keeper.join(timeout=(max(0, END-time.monotonic())
                             if sdk_resources is not None else 0.2))
        assert not keeper.is_alive()
        write_record(1, dict(safe=True, **result))
        os._exit(code)
    def watchdog():
        inputs = [0, done_r]
        if sdk_watchdog_race is not None:
            inputs.append(sdk_watchdog_race.fds[0])
        ready = select.select(inputs, [], [], remaining(END-3.75))[0]
        if done_r in ready:
            return
# CREATOR_BOUNDARY_BEGIN
# HOST_BUDGET_BEGIN
        if sdk_resources is not None:
            _host_budget_diagnostic("WATCHDOG_DECISION", ready, inputs)
# HOST_BUDGET_END
# CREATOR_BOUNDARY_END
        if sdk_watchdog_race is not None and sdk_watchdog_race.fds[0] in ready:
            try:
                sdk_watchdog_race.read_fault(END-3.75)
            except BaseException as exc:
                sdk_resources.fail("watchdog-trigger", exc)
            if sdk_resources.request_native_handoff() == "ALREADY_RETIRED":
                return
            try:
                sdk_resources.request_fallback()
                sdk_resources.request(stop_loop=True)
                if not sdk_resources.wait_native_handoff(END-3.5):
                    return  # Guardian safety remains independent at this bound.
                try:
                    cleanup()  # Ready means stopped LOOP and released drive lock.
                except BaseException as exc:
                    sdk_resources.fail("watchdog-native", exc)
            finally:
                sdk_resources.supervisor_native_finished()
            # This explicit early test path never reports/exits from supervisor.
            # Main retains driving ownership and emits the sole final SAFE.
            sdk_resources.complete.wait(max(0, END-0.25-time.monotonic()))
            return
        if sdk_resources is not None:
            if sdk_resources.request_native_handoff() == "ALREADY_RETIRED":
                return
            try:
                sdk_resources.fail("watchdog",
                                   AssertionError("independent fixture safety deadline"))
                sdk_resources.request_fallback()
                sdk_resources.request(stop_loop=True)
                if not sdk_resources.wait_native_handoff(END-3.5):
                    return
                try:
                    cleanup()  # Native only, after explicit MAIN authorization.
                except BaseException as exc:
                    sdk_resources.fail("watchdog-native", exc)
            finally:
                sdk_resources.supervisor_native_finished()
            # No native/retirement lock is held while main services LOOP.
            sdk_resources.complete.wait(max(0, END-0.25-time.monotonic()))
            if sdk_resources.finalized:
                finished.set()
                report(dict(ok=False, error="independent fixture safety deadline"), 91)
            return
        try:
            cleanup()
        except BaseException:
            return  # Lifetime keeper prevents unsafe ordinary-error exit.
        report(dict(ok=False, error="independent fixture safety deadline"), 91)
    supervisor = threading.Thread(target=watchdog, name="guest-host-safety", daemon=False)
    if sdk_watchdog_race is not None:
        sdk_watchdog_race.supervisor = supervisor  # Retain before Thread.start.
    if sdk_resources is not None:
        sdk_resources.permitted_threads = lambda: {keeper, supervisor}
    supervisor.start()

    guardian_hits = [0]
    async def next_event(predicate, timeout=4.0):
        end = min(END-3.75, LOOP.time()+timeout)
        while True:
            assert time.monotonic() < end, "fixture event deadline"
            item = await asyncio.wait_for(queue.get(), timeout=remaining(end))
            messages.append(item)
            guardian_hits[0] = max(guardian_hits[0], item.get("mutation_hits", 0))
            if item["kind"] == "RESOURCE":
                assert item["registered"], "CREATOR_REGISTRATION_BEFORE_PUBLICATION"
            assert item["kind"] not in ("READER_ERROR", "UNSAFE"), item
            if predicate(item):
                return item
            if item["kind"] == "GUARDIAN_ERROR" and PHASE not in (
                    "cli-fault", "unknown-proof", "protocol-after", "postreap-fault",
                    "adapter-missingproof", "score-adapter-missingproof",
                    "score-adapter-shutdown"):
                raise AssertionError(item["error"])

    def release(invocation=None):
        if invocation is not None:
            matching = [slot for slot in slots if slot["invocation"] is invocation]
            assert len(matching) == 1
            if sdk_test_gates is not None:
                hit = sdk_test_gates.pending_for(invocation.invocation_id.hex)
                assert hit is not None, "SDK_UNOBSERVED_TEST_GATE_RELEASE"
                sdk_test_gates.release_one(hit)
                return
            os.write(matching[0]["gate_w"], b"G")
            return
        for event in gates:
            event.set()
        if slots and not gates:
            os.write(slots[0]["gate_w"], b"G")

    def barrier_held():
        fd = os.open(owner.executor.profile.shared_state_dir / "lock", os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    async def pending(execution, closing, *, at_cap=False):
        if at_cap:
            delay = max(0, owner._cap()-time.monotonic()) + 0.03
            # Real monotonic deadline, not a mocked clock or a response-latency claim.
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0.15)
        assert not execution.done() and (closing is None or not closing.done()), (
            "HOST_ACK_WITH_INVALID_CURRENT_PROOF" if PHASE == "invalid-current-proof"
            else "HOST_ACK_WITH_MISSING_RESOURCE_PROOF")
        assert owner._completion is None and owner._authority.ack is None
        assert barrier_held(), "unresolved owner lost actual admission lock"
        if owner._intent is not None:
            assert owner._intent.deadline_ns == owner._intent.requested_ns + CAP_NS
            assert owner._cap() <= owner._intent.deadline_ns/1e9
        if at_cap or PHASE == "invalid-current-proof":
            snapshot = owner.snapshot()
            assert snapshot.incomplete and snapshot.state == "UNRESOLVED_OWNED"
        return dict(decision="pending", at_cap=at_cap)

    async def run_adapter(profile, db, digest, executor):
        # Host-only imports. Legacy phases never import or activate the adapter.
        import httpx
        from bench.task import SqlTask
        from verifiers.v1.task import TaskData
        from ptc import sql_arms
        from ptc.harness import PTCHarness, PTCHarnessConfig, ProgramInfrastructureError
        from ptc.test_owned_program_runner import Policy, _assistant, _launch

        nonlocal owner
        assert PHASE in ("adapter-normal-rejected", "adapter-normal-error",
                         "adapter-cancel", "adapter-infrastructure", "adapter-missingproof")
        ordinary, rejected, error = ADAPTER_RESPONSES
        normal = PHASE in ("adapter-normal-rejected", "adapter-normal-error")
        codes = [ordinary, rejected if PHASE == "adapter-normal-rejected" else error] if (
            normal) else [ordinary]
        policy = Policy(*[_assistant(code) for code in codes], _assistant(None))
        private_gold = "SELECT 'PRIVATE_ADAPTER_GOLD_DO_NOT_FORWARD'"
        task = SqlTask("adapter-fixture", "fixture question", "", private_gold,
                       "fixture-db", str(db), "simple", "derived", "s", "s", "fixture")
        data = TaskData(name=task.name, prompt="Static adapter forwarding fixture.")
        catalogs, bindings, runners, validations, calls = [], [], [], [], []
        close_entries, close_exits, owner_closes, seals, cancellations = [], [], [], [], []
        started, cancel_writes = [], []
        canonical_init = m.OwnedSqlInvocation.__init__
        def observe_init(actual, *args, **kwargs):
            with spawn_lock:
                assert not stopping.is_set(), "fixture owner creator retired"
                owners.append(actual)  # Before canonical initialization, including partials.
                canonical_init(actual, *args, **kwargs)
                _fence_owned_start(actual, spawn_lock, stopping)
        # Even a broken inert builder must leave every allocation safety-owned.
        m.OwnedSqlInvocation.__init__ = observe_init
        canonical_catalog = sql_arms.sql_catalog
        def observe_catalog(*args, **kwargs):
            value = canonical_catalog(*args, **kwargs)
            catalogs.append(value)
            return value
        sql_arms.sql_catalog = observe_catalog
        try:
            from ptc.sql_owned_program import build_owned_sql_program_harness
            harness = build_owned_sql_program_harness(
                PTCHarnessConfig(program_timeout=5.0), data=data, task=task,
                executor=executor, db_sha256=digest, max_rows=1)
        finally:
            sql_arms.sql_catalog = canonical_catalog
        assert type(harness) is PTCHarness and len(catalogs) == 1
        assert not owners and not trace.fence() and not policy.requests
        base = catalogs[0]
        canonical_allocate = m.PilotExecutor.owned_program
        canonical_close = m.OwnedSqlInvocation.aclose

        async def observe_owner_close(actual):
            record = dict(invocation=actual, task=asyncio.current_task(), ack=None)
            owner_closes.append(record)
            value = await canonical_close(actual)
            record["ack"] = value
            return value
        m.OwnedSqlInvocation.aclose = observe_owner_close

        def observe_allocate(actual_executor, code, **kwargs):
            nonlocal owner
            assert actual_executor is executor
            assert kwargs == dict(db_path=str(db), db_sha256=digest, max_rows=1)
            assert len(runners) == 1 and len(calls) == len(owners)+1
            # Request N+1 may not escape before N's real host ACK and joins.
            for previous in owners:
                assert previous._completion is not None
                assert previous._authority.ack is previous._completion.cleanup_ack
                assert not previous._thread.is_alive()
                assert all(child._creator_waited and not child._creator_ambiguous
                           for child in previous._children)
            actual = canonical_allocate(actual_executor, code, **kwargs)
            assert owners[-1] is actual and type(actual) is m.OwnedSqlInvocation
            owner = actual
            assert actual.request == m.ProgramRequest(code, 1, digest)
            original_start, original_seal = actual._start, actual._seal
            def observe_start():
                jobs = [job for job in runners[0]._jobs if job.invocation is actual]
                assert len(jobs) == 1, "ADAPTER_JOB_NOT_RETAINED_BEFORE_EXECUTE"
                if not any(item is actual for item in started):
                    started.append(actual)
                return original_start()
            def observe_seal(*args, **kwargs):
                value = original_seal(*args, **kwargs)
                assert value is actual._completion
                assert value.cleanup_ack is actual._authority.ack
                seals.append((actual, value, time.monotonic_ns()))
                return value
            actual._start, actual._seal = observe_start, observe_seal
            return actual
        m.PilotExecutor.owned_program = observe_allocate
        original_factory = harness.program_runner_factory
        def observe_factory(actual_data, compiled):
            assert actual_data is data and not policy.requests
            assert compiled is not base and compiled.names() == base.names() | {"print"}
            assert "print" not in base.names() and callable(compiled.tools["print"])
            assert all(compiled.tools[name] is callback
                       for name, callback in base.tools.items())
            runner = original_factory(actual_data, compiled)
            runners.append(runner)
            bindings.append((actual_data, compiled))
            original_validate = runner.validate_program_timeout
            original_run, original_close = runner.run_program, runner.aclose
            def observe_timeout(actual_runner, timeout):
                assert actual_runner is runner
                assert timeout == 5.0 and type(timeout) in (int, float)
                assert not policy.requests and not owners and not trace.fence()
                validations.append(timeout)
                value = original_validate(timeout)
                assert value is None and not forbidden_calls and not trace.fence()
                return value
            async def observe_run(actual_runner, code, *, timeout):
                assert actual_runner is runner
                calls.append((code, timeout, runner))
                try:
                    return await original_run(code, timeout=timeout)
                except asyncio.CancelledError as exc:
                    cancellations.append(exc)
                    raise
            async def observe_close(actual_runner):
                assert actual_runner is runner
                close_entries.append(asyncio.current_task())
                value = await original_close()
                assert value is None
                close_exits.append(time.monotonic_ns())
                return value
            runner_type = type(runner)
            runner_type.validate_program_timeout = observe_timeout
            runner_type.run_program, runner_type.aclose = observe_run, observe_close
            return runner  # The exact real runner, no proxy or replacement owner.
        harness.program_runner_factory = observe_factory
        scripted_transport = policy.transport()
        def observe_policy(request):
            if policy.requests:
                assert owners and all(actual._completion is not None for actual in owners)
                assert all(actual._authority.ack is actual._completion.cleanup_ack
                           and not actual._thread.is_alive() for actual in owners)
                assert all(job.ack is job.invocation._authority.ack
                           and job.close_task is not None and job.close_task.done()
                           for job in runners[0]._jobs)
            assert private_gold.encode() not in request.content
            return scripted_transport.handle_request(request)
        harness.transport = httpx.MockTransport(observe_policy)

        async def event_for(actual, kind, name=None):
            return await next_event(lambda item: (
                item.get("invocation_id") == actual.invocation_id.hex
                and item["kind"] == kind and (name is None or item.get("name") == name)))

        def slot_for(actual):
            matching = [slot for slot in slots if slot["invocation"] is actual]
            assert len(matching) == 1
            return matching[0]

        async def held(launch):
            marker = LOOP.create_future()
            LOOP.call_soon(marker.set_result, None)
            await asyncio.wait_for(marker, timeout=remaining(END-3.75))
            assert not launch.done(), "ADAPTER_CALLER_ESCAPED_HELD_CLEANUP"
            assert owner._completion is None and owner._authority.ack is None

        def original_native_cancel(launch):
            # Inspect the actual await chain, not launch's unrelated frame locals.
            coroutine = launch.get_coro()
            for _ in range(32):
                frame = getattr(coroutine, "cr_frame", None)
                if frame is not None and frame.f_code.co_name == "execute":
                    if frame.f_locals.get("self") is owner:
                        value = frame.f_locals.get("original_cancel")
                        assert isinstance(value, asyncio.CancelledError)
                        return value
                coroutine = getattr(coroutine, "cr_await", None)
                if coroutine is None:
                    break
            raise AssertionError("actual native execute cancellation not retained")

        launch = LOOP.create_task(_launch(harness, data))
        caller_done = []
        launch.add_done_callback(lambda actual: caller_done.append(time.monotonic_ns()))
        first_cancel = None
        intent = None
        if not normal:
            hit = await next_event(lambda item: item["kind"] == "HIT"
                                   and item.get("name") == PHASE)
            assert len(owners) == len(runners) == len(started) == 1
            assert hit["invocation_id"] == owner.invocation_id.hex
            assert len(slots) == 1 and len(trace.fence()) == 1
            if PHASE == "adapter-infrastructure":
                now = time.monotonic_ns()
                raw = struct.pack(">8s16sQQ", b"BADMAGIC", owner.invocation_id.bytes,
                                  now, now+CAP_NS)
                assert os.write(owner._endpoints[-1].fd, raw) == 40
                monitored = await event_for(owner, "MONITOR_DONE")
                assert monitored["error"] is True
                release(owner)
            else:
                if PHASE == "adapter-missingproof":
                    assert time.monotonic()+12.03 < END-3.75, (
                        "ADAPTER_REAL_INTENT_CAP_EXCEEDS_FIXTURE_BUDGET")
                real_write = os.write
                cancel_write_original[0] = real_write
                def observe_cancel_write(fd, raw):
                    endpoints = [endpoint for endpoint in owner._endpoints
                                 if endpoint.fd is not None and endpoint.fd == fd]
                    count = real_write(fd, raw)
                    cancel_writes.extend((endpoint, bytes(raw), count) for endpoint in endpoints)
                    return count
                os.write = observe_cancel_write
                first_message = "first adapter launch cancellation"
                assert launch.cancel(first_message)
                await held(launch)
                first_cancel = original_native_cancel(launch)
                assert first_cancel.args == (first_message,) and launch.cancelling() == 1
                intent = owner.snapshot().intent
                assert intent is not None and intent.reason == "caller_cancelled"
                assert intent.deadline_ns == intent.requested_ns+CAP_NS
                if PHASE == "adapter-missingproof":
                    assert intent.deadline_ns/1e9+0.03 < END-3.75
                consumed = {}
                while len(consumed) < 2:
                    item = await next_event(lambda item: item["kind"] == "CONSUMED")
                    assert item["lane"] not in consumed
                    consumed[item["lane"]] = item
                assert set(consumed) == {"host", "guardian"}
                assert all(item["times"] == [intent.requested_ns, intent.deadline_ns]
                           for item in consumed.values())
                release(owner)
                if PHASE == "adapter-cancel":
                    await event_for(owner, "HIT", "cleanup-held")
                    for number in (2, 3):
                        assert launch.cancel("later adapter launch cancellation " + str(number))
                        await held(launch)
                        assert launch.cancelling() == number
                        assert original_native_cancel(launch) is first_cancel
                        assert owner.snapshot().intent is intent
                        assert not seals and not caller_done and not close_exits
                    release(owner)
                else:
                    withheld = await event_for(owner, "RESOURCE_PROOF_WITHHELD")
                    assert withheld["fault_hits"] == 1
                    await asyncio.sleep(max(0, intent.deadline_ns/1e9-time.monotonic())+0.03)
                    assert time.monotonic_ns() >= intent.deadline_ns+30000000
                    assert time.monotonic() < END-3.75
                    assert not launch.done() and not seals and not caller_done
                    assert owner._completion is None and owner._authority.ack is None
                    assert owner.snapshot().state == "UNRESOLVED_OWNED"
                    assert owner.snapshot().incomplete and barrier_held()
                    assert (profile.shared_state_dir / "active.json").exists()
                    assert len(policy.requests) == len(calls) == len(owners) == 1
                    assert len(bindings) == len(runners) == len(validations) == 1
                    assert validations == [5.0] and len(catalogs) == 1
                    assert len(runners[0]._jobs) == 1
                    job = runners[0]._jobs[0]
                    assert job.invocation is owner and job.ack is None
                    assert job.completion is None
                    assert job.close_task is None or not job.close_task.done()
                    assert len(close_entries) <= 1
                    assert not close_exits and not cancellations
                    assert len(cancel_writes) == 2
                    assert {id(endpoint) for endpoint, raw, count in cancel_writes} == {
                        id(endpoint) for endpoint in owner._endpoints}
                    assert all(raw == m._encode_cancel_frame(intent) and count == 40
                               for endpoint, raw, count in cancel_writes)
                    assert not forbidden_calls
                    return dict(decision="pending", at_cap=True, dispatches=1,
                                requests=1, acks=0, caller_cancellations=1)

        done, _ = await asyncio.wait([launch], timeout=remaining(END-3.75))
        assert launch in done, "ADAPTER_RESPONSIVE_CLEANUP_DID_NOT_COMPLETE"
        # Let the registered caller-done observation run before ordering assertions.
        marker = LOOP.create_future()
        LOOP.call_soon(marker.set_result, None)
        await marker
        if PHASE == "adapter-cancel":
            assert launch.cancelled() and launch.cancelling() == 3
            try:
                launch.result()
            except asyncio.CancelledError as exc:
                assert exc is first_cancel and cancellations == [exc]
            else:
                raise AssertionError("original adapter cancellation did not propagate")
        elif PHASE == "adapter-infrastructure":
            try:
                launch.result()
            except ProgramInfrastructureError as exc:
                assert private_gold not in str(exc)
            else:
                raise AssertionError("ADAPTER_INFRASTRUCTURE_BECAME_POLICY_FEEDBACK")
        else:
            assert launch.result().exit_code == 0 and not cancellations
        count = 2 if normal else 1
        assert len(policy.requests) == (3 if normal else 1), (
            "ADAPTER_ABORT_DISPATCHED_NEXT_POLICY_REQUEST")
        assert len(bindings) == len(runners) == len(validations) == 1
        assert validations == [5.0] and len(catalogs) == 1
        assert len(close_entries) == len(close_exits) == 1
        assert len(owners) == len(started) == len(slots) == len(seals) == count
        assert len({actual.invocation_id for actual in owners}) == count
        assert len(trace.fence()) == count
        assert all(entry["kind"] == "guardian" for entry in trace.fence())
        assert [(code, timeout) for code, timeout, runner in calls] == [
            (code, 5.0) for code in codes]
        assert all(runner is runners[0] for code, timeout, runner in calls)
        assert len(runners[0]._jobs) == len(owner_closes) == count
        for actual in owners:
            completion = actual._completion
            ack = completion.cleanup_ack
            job = next(job for job in runners[0]._jobs if job.invocation is actual)
            assert job.ack is ack is actual._authority.ack
            assert job.close_task is not None and job.close_task.done()
            assert not job.close_task.cancelled() and job.close_task.exception() is None
            assert job.completion is None or job.completion is completion
            closes = [record for record in owner_closes if record["invocation"] is actual]
            assert len(closes) == 1 and closes[0]["task"] is job.close_task
            assert closes[0]["ack"] is ack
            assert ack.invocation_id == actual.invocation_id and ack.role == "program"
            assert ack.request_sha256 == m.request_sha256(actual.request)
            assert ack.profile_sha256 == m.execution_profile_sha256(profile)
            assert ack.child_waits and ack.thread_joins and not ack.not_started
            assert not actual._thread.is_alive()
            assert len(actual._children) == 1
            assert all(child._creator_waited and not child._creator_ambiguous
                       and type(child.returncode) is int for child in actual._children)
            assert ack.guardian_reaps == tuple((child.pid, child.returncode)
                                              for child in actual._children)
            slot = slot_for(actual)
            assert slot["process"] is actual._children[0]
            evidence = next((item for item in slot["messages"]
                             if item["kind"] == "EVIDENCE"), None)
            if evidence is None:
                evidence = await event_for(actual, "EVIDENCE")
            rows = evidence["actual"]
            assert sum(row["actor"] == "role" for row in rows) == 1
            assert sum(row["actor"] == "cli" for row in rows) >= 2
            assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                       and type(row["returncode"]) is int for row in rows)
            assert evidence["observers"] == 1 and evidence["released"]
            assert evidence["forbidden"] == 0 and evidence["accounted"] == [True]
            wire = (root / "guest-run" / actual.invocation_id.hex / "request.wire").read_bytes()
            assert private_gold.encode() not in wire
            assert m.decode_wire_message(wire, role="program", kind="request",
                request_sha256=ack.request_sha256).payload == actual.request
            if normal:
                expected, is_rejected = ADAPTER_RESPONSES[actual.request.program]
                assert completion.abort is None and completion.outcome.abort is None
                assert completion.outcome.observation == expected
                assert completion.outcome.rejected is is_rejected
                assert job.completion is completion
            elif PHASE == "adapter-infrastructure":
                assert completion.outcome is None and completion.abort.kind == "infrastructure"
                assert completion.abort.detail_code == "protocol"
                persisted = m.program_outcome_from_dict(json.loads(
                    (root / "guest-run" / actual.invocation_id.hex / "outcome.json").read_bytes()))
                assert persisted.abort.reason == "protocol" and persisted.observation is None
            else:
                assert completion.outcome is None and completion.abort.kind == "cancelled"
                assert actual.snapshot().intent is intent
                assert intent.requested_ns <= ack.completed_ns <= ack.cleanup_deadline_ns
                assert ack.cleanup_deadline_ns <= intent.deadline_ns
            sealed = [item for item in seals if item[0] is actual]
            assert len(sealed) == 1 and sealed[0][1] is completion
            assert ack.completed_ns <= sealed[0][2] <= close_exits[0] <= caller_done[0]
        assert len({id(item[1].cleanup_ack) for item in seals}) == count
        assert all(entry["process"]._creator_waited and not entry["process"]._creator_ambiguous
                   for entry in trace.fence())
        if normal:
            assert [body["messages"][-1]["content"] for body in policy.bodies[1:]] == [
                ADAPTER_RESPONSES[code][0] for code in codes]
        if PHASE == "adapter-cancel":
            assert len(cancel_writes) == 2
            assert {id(endpoint) for endpoint, raw, size in cancel_writes} == {
                id(endpoint) for endpoint in owner._endpoints}
            assert all(raw == m._encode_cancel_frame(intent) and size == 40
                       for endpoint, raw, size in cancel_writes)
        assert not forbidden_calls
        return dict(decision="ack", dispatches=count, requests=len(policy.requests),
                    acks=count, runner_closes=1,
                    caller_cancellations=3 if PHASE == "adapter-cancel" else 0)

    async def run_scorer_adapter(profile, db, digest, executor):
        # Host-only, no TaskData, SDK, policy, reward, or host SQL path.
        from bench.score import ExResult
        from bench.task import SqlTask
        from train.sql_episodes import InstrumentSettings

        nonlocal owner
        status_phases = {"score-adapter-status-" + status for status in SCORER_FIXTURE_STATUSES}
        assert PHASE in status_phases | {
            "score-adapter-requests", "score-adapter-cancel", "score-adapter-infrastructure",
            "score-adapter-missingproof", "score-adapter-shutdown"}
        assert m.limits_for("scorer").deadline_ms == 30000
        multi = PHASE == "score-adapter-shutdown"
        missing = PHASE == "score-adapter-missingproof" or multi
        predictions = ["fixture-score-status:match"]
        if PHASE in status_phases:
            predictions = ["fixture-score-status:" + PHASE.removeprefix("score-adapter-status-")]
        elif PHASE == "score-adapter-requests":
            predictions.append("")  # Empty input is native-accepted, no extraction.
        elif multi:
            predictions.append("fixture-score-status:mismatch")
        task = SqlTask("owned-scorer-fixture", "private fixture question",
                       "private fixture evidence", "SELECT 'PRIVATE_SCORER_FIXTURE_GOLD'",
                       "private-fixture-db", str(db), "moderate", "annotated",
                       "private-shape", "private-coarse-shape", "fixture")
        instrument = InstrumentSettings(
            action_cap=3, action_max_rows=17, scorer_max_rows=23, compare="multiset",
            scorer_timeout_s=30.0 if PHASE == "score-adapter-requests" else 8.125,
            program_timeout_s=2.5, wrapper_timeout_s=19.0,
            python_version="fixture-python", sqlite_version="fixture-sqlite",
            source_paths=("fixture/instrument/source.py",), source_sha256="b"*64)
        original_task, original_settings = dataclasses.asdict(task), dataclasses.asdict(instrument)
        allocated, started, seals, owner_closes, score_calls, escaped_cancels = [], [], [], [], [], []
        operation_exits = []
        shutdown_entries, shutdown_exits, score_tasks, cancel_writes = [], [], [], []
        second_gate = threading.Event()
        canonical_init = m.OwnedSqlInvocation.__init__
        canonical_allocate, canonical_close = m.PilotExecutor.owned_score, m.OwnedSqlInvocation.aclose

        def observe_init(actual, *args, **kwargs):
            with spawn_lock:
                assert not stopping.is_set(), "fixture owner creator retired"
                owners.append(actual)  # Retain even partial initialization.
                canonical_init(actual, *args, **kwargs)
                _fence_owned_start(actual, spawn_lock, stopping)
        m.OwnedSqlInvocation.__init__ = observe_init

        async def observe_owner_close(actual):
            record = dict(invocation=actual, task=asyncio.current_task(), ack=None,
                          known_tasks=tuple(job.close_task for job in scorer._jobs))
            owner_closes.append(record)
            emit("SCORE_OWNER_CLOSE_STARTED", invocation_id=actual.invocation_id.hex)
            value = await canonical_close(actual)
            record["ack"] = value
            return value
        m.OwnedSqlInvocation.aclose = observe_owner_close

        def observe_allocate(actual_executor, prediction, actual_task, **kwargs):
            nonlocal owner
            assert actual_executor is executor and actual_task is task
            assert kwargs == dict(db_sha256=digest, instrument=instrument)
            assert kwargs["instrument"] is instrument
            assert dataclasses.asdict(task) == original_task
            assert dataclasses.asdict(instrument) == original_settings
            assert len(allocated) < len(predictions) and prediction == predictions[len(allocated)]
            actual = canonical_allocate(actual_executor, prediction, actual_task, **kwargs)
            assert type(actual) is m.OwnedSqlInvocation and owners[-1] is actual
            allocated.append(actual)
            owner = actual
            assert actual.db_path == db and task.db_path == str(db)
            expected = m.ScoreRequest(
                dataclasses.replace(task, db_path="/db.sqlite"), prediction,
                instrument.scorer_timeout_s, instrument.scorer_max_rows, instrument.compare, digest)
            assert actual.request == expected and actual.request.task.gold_sql == task.gold_sql
            initial = actual.snapshot()
            original_start, original_seal = actual._start, actual._seal
            def observe_start():
                jobs = [job for job in scorer._jobs if job.invocation is actual]
                assert len(jobs) == 1, "SCORER_JOB_NOT_RETAINED_BEFORE_EXECUTE"
                assert jobs[0].snapshot == initial and initial.state == "ALLOCATED"
                assert initial.role == "scorer" and initial.intent is None and not initial.incomplete
                assert initial.request_sha256 == m.request_sha256(expected)
                assert initial.profile_sha256 == m.execution_profile_sha256(profile)
                if not any(item is actual for item in started):
                    started.append(actual)
                return original_start()  # Delegates through the installed startup fence.
            def observe_seal(*args, **kwargs):
                value = original_seal(*args, **kwargs)
                assert value is actual._completion and value.cleanup_ack is actual._authority.ack
                seals.append((actual, value, time.monotonic_ns()))
                return value
            actual._start, actual._seal = observe_start, observe_seal
            if multi and len(allocated) == 2:
                # Real second controller is retained/published, held BEFORE
                # admission. First unresolved owner keeps the shared lock.
                original_controller = actual._controller
                with spawn_lock:
                    assert not stopping.is_set()
                    gates.append(second_gate)
                def held_controller(binding):
                    emit("SCORE_CONTROLLER_HELD", invocation_id=actual.invocation_id.hex)
                    assert second_gate.wait(timeout=remaining(END-3.75)), (
                        "scorer second-controller fixture deadline")
                    if stopping.is_set():
                        return  # Physical teardown, never an API candidate/ACK.
                    return original_controller(binding)
                actual._controller = held_controller
            return actual
        m.PilotExecutor.owned_score = observe_allocate

        # No new module is imported on any of the existing 77 paths.
        from ptc.sql_owned_score import (
            OwnedSqlScorer, ScoreInfrastructureError, build_owned_sql_scorer)
        scorer = build_owned_sql_scorer(
            task=task, executor=executor, db_sha256=digest, instrument=instrument)
        assert type(scorer) is OwnedSqlScorer
        assert not owners and not trace.fence() and not forbidden_calls
        assert scorer.admit() is None
        assert scorer.admit() is None  # Recheck the original seal, never reseal.
        assert not owners and not trace.fence() and not forbidden_calls
        original_score, original_shutdown = scorer.score_sql, scorer.aclose
        def observe_operation_exit():
            # Capture at the actual public adapter boundary, not a later
            # assertion turn in which an escaped cleanup might have caught up.
            operation_exits.append((asyncio.current_task(), time.monotonic_ns(), tuple(
                (job.invocation, job.ack,
                 job.close_task is not None and job.close_task.done(),
                 job.invocation._thread is not None and not job.invocation._thread.is_alive())
                for job in scorer._jobs)))
        def instrument_methods():
            async def observe_score(actual_scorer, prediction):
                assert actual_scorer is scorer
                score_calls.append(prediction)
                try:
                    result = await original_score(prediction)
                except asyncio.CancelledError as exc:
                    escaped_cancels.append(exc)
                    observe_operation_exit()
                    raise
                except ScoreInfrastructureError:
                    observe_operation_exit()
                    raise
                observe_operation_exit()
                return result
            async def observe_shutdown(actual_scorer):
                assert actual_scorer is scorer
                shutdown_entries.append(asyncio.current_task())
                value = await original_shutdown()
                assert value is None
                shutdown_exits.append(time.monotonic_ns())
                return value
            type(scorer).score_sql, type(scorer).aclose = observe_score, observe_shutdown
        instrument_methods()

        def start_score(prediction):
            operation = LOOP.create_task(scorer.score_sql(prediction))
            score_tasks.append(operation)
            return operation

        async def event_for(actual, kind, name=None):
            return await next_event(lambda item: (
                item.get("invocation_id") == actual.invocation_id.hex
                and item["kind"] == kind and (name is None or item.get("name") == name)))

        async def finish(operation):
            done, _ = await asyncio.wait([operation], timeout=remaining(END-3.75))
            assert operation in done, "SCORER_RESPONSIVE_CLEANUP_DID_NOT_COMPLETE"

        def job_for(actual):
            jobs = [job for job in scorer._jobs if job.invocation is actual]
            assert len(jobs) == 1
            return jobs[0]

        async def acknowledged(actual, *, dispatched=True):
            job, completion = job_for(actual), actual._completion
            assert completion is not None
            ack = completion.cleanup_ack
            assert job.ack is ack is actual._authority.ack
            assert job.completion is None or job.completion is completion
            assert job.close_task is not None and job.close_task.done()
            assert not job.close_task.cancelled() and job.close_task.exception() is None
            closes = [record for record in owner_closes if record["invocation"] is actual]
            assert len(closes) == 1 and closes[0]["task"] is job.close_task
            assert closes[0]["ack"] is ack, "SCORER_ACTUAL_CLOSE_ACK_NOT_RETAINED"
            assert ack.invocation_id == actual.invocation_id and ack.role == "scorer"
            assert ack.request_sha256 == actual.snapshot().request_sha256
            assert ack.profile_sha256 == m.execution_profile_sha256(profile)
            assert actual._thread is not None and not actual._thread.is_alive()
            sealed = [entry for entry in seals if entry[0] is actual]
            assert len(sealed) == 1 and sealed[0][1] is completion
            assert ack.completed_ns <= sealed[0][2]
            if not dispatched:
                assert ack.not_started and not actual._children and ack.guardian_reaps == ()
                return ack
            assert not ack.not_started and ack.child_waits and ack.thread_joins
            matching = [slot for slot in slots if slot["invocation"] is actual]
            assert len(matching) == 1 and len(actual._children) == 1
            assert matching[0]["process"] is actual._children[0]
            assert all(child._creator_waited and not child._creator_ambiguous
                       and type(child.returncode) is int for child in actual._children)
            assert ack.guardian_reaps == tuple((child.pid, child.returncode)
                                              for child in actual._children)
            evidence = next((item for item in matching[0]["messages"]
                             if item["kind"] == "EVIDENCE"), None)
            if evidence is None:
                evidence = await event_for(actual, "EVIDENCE")
            rows = evidence["actual"]
            assert sum(row["actor"] == "role" for row in rows) == 1
            assert sum(row["actor"] == "cli" for row in rows) >= 2
            assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                       and type(row["returncode"]) is int for row in rows)
            assert evidence["observers"] == 1 and evidence["released"]
            assert evidence["accounted"] == [True] and evidence["forbidden"] == 0
            wire = (root / "guest-run" / actual.invocation_id.hex / "request.wire").read_bytes()
            decoded = m.decode_wire_message(wire, role="scorer", kind="request",
                                           request_sha256=ack.request_sha256).payload
            assert decoded == actual.request
            assert decoded.task == dataclasses.replace(task, db_path="/db.sqlite")
            assert decoded.task.gold_sql == task.gold_sql and actual.db_path == db
            assert (decoded.timeout_s, decoded.max_rows, decoded.compare, decoded.db_sha256) == (
                instrument.scorer_timeout_s, instrument.scorer_max_rows, instrument.compare, digest)
            return ack

        def retained_native_cancel(operation, actual):
            coroutine = operation.get_coro()
            for _ in range(32):
                frame = getattr(coroutine, "cr_frame", None)
                if frame is not None and frame.f_code.co_name == "execute":
                    if frame.f_locals.get("self") is actual:
                        value = frame.f_locals.get("original_cancel")
                        assert isinstance(value, asyncio.CancelledError)
                        return value
                coroutine = getattr(coroutine, "cr_await", None)
                if coroutine is None:
                    break
            raise AssertionError("actual scorer execute cancellation not retained")

        async def held_turn(operation, actual):
            marker = LOOP.create_future()
            LOOP.call_soon(marker.set_result, None)
            await asyncio.wait_for(marker, timeout=remaining(END-3.75))
            assert not operation.done(), "SCORER_CALLER_ESCAPED_HELD_CLEANUP"
            assert actual._completion is None and actual._authority.ack is None

        def watch_cancel_writes():
            real_write = os.write
            cancel_write_original[0] = real_write
            def observe_write(fd, raw):
                endpoints = [(actual, endpoint) for actual in allocated
                             for endpoint in actual._endpoints
                             if endpoint.fd is not None and endpoint.fd == fd]
                count = real_write(fd, raw)
                cancel_writes.extend((actual, endpoint, bytes(raw), count)
                                     for actual, endpoint in endpoints)
                return count
            os.write = observe_write

        async def consumed_intent(actual, intent):
            seen = {}
            # Multi-owner close-start observations may already have drained a
            # genuine consumption event. Reuse that observation, never replay.
            for item in messages:
                if item["kind"] == "CONSUMED" and item["times"] == [
                        intent.requested_ns, intent.deadline_ns]:
                    assert item["lane"] not in seen
                    seen[item["lane"]] = item
            while len(seen) < 2:
                item = await next_event(lambda item: item["kind"] == "CONSUMED")
                assert item["lane"] not in seen
                if item["lane"] == "guardian":
                    assert item["invocation_id"] == actual.invocation_id.hex
                seen[item["lane"]] = item
            assert set(seen) == {"host", "guardian"}
            assert all(item["invocation_id"] == actual.invocation_id.hex for item in seen.values())
            assert all(item["times"] == [intent.requested_ns, intent.deadline_ns]
                       for item in seen.values())

        def exact_frames(actual, intent):
            assert len(cancel_writes) == 2
            assert {id(endpoint) for invocation, endpoint, raw, count in cancel_writes} == {
                id(endpoint) for endpoint in actual._endpoints}
            assert all(invocation is actual and raw == m._encode_cancel_frame(intent) and count == 40
                       for invocation, endpoint, raw, count in cancel_writes)

        operation = start_score(predictions[0])
        if PHASE in status_phases or PHASE == "score-adapter-requests":
            results = []
            for index, prediction in enumerate(predictions):
                if index:
                    operation = start_score(prediction)
                await finish(operation)
                actual = allocated[index]
                await acknowledged(actual)
                result = operation.result()
                completion = actual._completion
                assert completion.abort is None and completion.outcome.abort is None
                assert result is completion.outcome.result, "SCORER_NATIVE_RESULT_IDENTITY_CHANGED"
                assert type(result) is ExResult and result == scorer_fixture_result(prediction)
                assert job_for(actual).completion is completion
                results.append(result)
            assert len(allocated) == len(started) == len(seals) == len(predictions)
            assert len({actual.invocation_id for actual in allocated}) == len(predictions)
        else:
            hit = await next_event(lambda item: item["kind"] == "HIT"
                                   and item.get("name") == PHASE)
            assert len(allocated) == len(started) == 1
            first = allocated[0]
            assert hit["invocation_id"] == first.invocation_id.hex
            if PHASE == "score-adapter-infrastructure":
                now = time.monotonic_ns()
                raw = struct.pack(">8s16sQQ", b"BADMAGIC", first.invocation_id.bytes, now, now+CAP_NS)
                assert os.write(first._endpoints[-1].fd, raw) == 40
                monitored = await event_for(first, "MONITOR_DONE")
                assert monitored["error"] is True
                release(first)
                await finish(operation)
                try:
                    operation.result()
                except ScoreInfrastructureError:
                    pass
                else:
                    raise AssertionError("SCORER_PROTOCOL_ABORT_BECAME_EXRESULT")
                await acknowledged(first)
                assert first._completion.outcome is None
                assert first._completion.abort.kind == "infrastructure"
                assert first._completion.abort.detail_code == "protocol"
                persisted = m.score_outcome_from_dict(json.loads(
                    (root / "guest-run" / first.invocation_id.hex / "outcome.json").read_bytes()))
                assert persisted.result is None and persisted.abort.reason == "protocol"
            else:
                if missing:
                    assert time.monotonic()+12.03 < END-3.75, (
                        "SCORER_REAL_INTENT_CAP_EXCEEDS_FIXTURE_BUDGET")
                watch_cancel_writes()
                if multi:
                    second_operation = start_score(predictions[1])
                    controller_held = await next_event(
                        lambda item: item["kind"] == "SCORE_CONTROLLER_HELD")
                    assert len(allocated) == len(started) == 2
                    second = allocated[1]
                    assert controller_held["invocation_id"] == second.invocation_id.hex
                    assert second._thread.is_alive() and second.snapshot().intent is None
                    assert not second._children and len(slots) == 1
                    assert time.monotonic()+12.03 < END-3.75
                    adapter_close = LOOP.create_task(scorer.aclose())
                    while len(owner_closes) < 2:
                        await next_event(lambda item: item["kind"] == "SCORE_OWNER_CLOSE_STARTED")
                    jobs = [job_for(actual) for actual in allocated]
                    assert all(job.close_task is not None for job in jobs)
                    assert len({id(job.close_task) for job in jobs}) == 2
                    assert all(item is not None for item in owner_closes[0]["known_tasks"]), (
                        "SCORER_SHUTDOWN_JOINED_FIRST_BEFORE_STARTING_ALL_CLOSES")
                    assert len(owner_closes[0]["known_tasks"]) == 2
                    intent = first.snapshot().intent
                    assert intent is not None and intent.reason == "runner_closed"
                    assert second.snapshot().intent is not None
                    assert second.snapshot().intent.reason == "runner_closed"
                    assert not adapter_close.done() and first._authority.ack is None
                    second_gate.set()
                    await finish(second_operation)
                    try:
                        second_operation.result()
                    except ScoreInfrastructureError:
                        pass
                    else:
                        raise AssertionError("SCORER_SHUTDOWN_ABORT_BECAME_EXRESULT")
                    await acknowledged(second, dispatched=False)
                    exited = [entry for entry in operation_exits if entry[0] is second_operation]
                    assert len(exited) == 1
                    fact = next(item for item in exited[0][2] if item[0] is second)
                    assert fact[1] is second._authority.ack and fact[2] and fact[3]
                    assert not adapter_close.done() and not operation.done()
                    refused = LOOP.create_task(scorer.score_sql(""))
                    await finish(refused)
                    try:
                        refused.result()
                    except ScoreInfrastructureError:
                        pass
                    else:
                        raise AssertionError("closing scorer accepted new work")
                    assert len(allocated) == len(scorer._jobs) == 2
                else:
                    first_message = "first actual scorer caller cancellation"
                    assert operation.cancel(first_message)
                    await held_turn(operation, first)
                    first_cancel = retained_native_cancel(operation, first)
                    assert first_cancel.args == (first_message,) and operation.cancelling() == 1
                    intent = first.snapshot().intent
                    assert intent is not None and intent.reason == "caller_cancelled"
                assert intent.deadline_ns == intent.requested_ns+CAP_NS
                if missing:
                    assert intent.deadline_ns/1e9+0.03 < END-3.75
                await consumed_intent(first, intent)
                release(first)
                if missing:
                    withheld = await event_for(first, "RESOURCE_PROOF_WITHHELD")
                    assert withheld["fault_hits"] == 1
                    await asyncio.sleep(max(0, intent.deadline_ns/1e9-time.monotonic())+0.03)
                    assert time.monotonic_ns() >= intent.deadline_ns+30000000
                    assert time.monotonic() < END-3.75
                    assert not operation.done() and first._completion is None
                    assert first._authority.ack is None and job_for(first).ack is None
                    assert job_for(first).completion is None
                    snapshot = first.snapshot()
                    assert snapshot.incomplete and snapshot.state == "UNRESOLVED_OWNED"
                    assert snapshot.intent is intent and barrier_held()
                    assert first._thread is not None and first._thread.is_alive()
                    assert (profile.shared_state_dir / "active.json").exists()
                    assert not shutdown_exits and not escaped_cancels
                    if multi:
                        assert not adapter_close.done() and len(owner_closes) == 2
                        assert job_for(second).ack is second._authority.ack
                        assert job_for(second).ack is not None
                        assert job_for(first).close_task is not None
                        assert not job_for(first).close_task.done()
                        assert len(seals) == 1 and seals[0][0] is second
                    else:
                        assert not seals
                        assert job_for(first).close_task is None or not job_for(first).close_task.done()
                    exact_frames(first, intent)
                    unresolved_owners.append(first)
                    assert len(allocated) == len(owners) == len(started) == len(scorer._jobs) == (
                        2 if multi else 1)
                    assert len(slots) == len(trace.fence()) == 1
                    assert score_calls == predictions + ([""] if multi else [])
                    assert not forbidden_calls
                    return dict(decision="pending", at_cap=True, allocations=len(allocated),
                                dispatches=1, acks=1 if multi else 0,
                                owner_closes=len(owner_closes), shutdown_pending=multi)
                await event_for(first, "HIT", "cleanup-held")
                for number in (2, 3):
                    assert operation.cancel("later actual scorer cancellation " + str(number))
                    await held_turn(operation, first)
                    assert operation.cancelling() == number
                    assert retained_native_cancel(operation, first) is first_cancel
                    assert first.snapshot().intent is intent and not seals and not escaped_cancels
                release(first)
                await finish(operation)
                try:
                    operation.result()
                except asyncio.CancelledError as exc:
                    assert exc is first_cancel and escaped_cancels == [exc]
                else:
                    raise AssertionError("first scorer caller cancellation did not propagate")
                ack = await acknowledged(first)
                assert operation.cancelled() and operation.cancelling() == 3
                assert first._completion.outcome is None and first._completion.abort.kind == "cancelled"
                assert intent.requested_ns <= ack.completed_ns <= ack.cleanup_deadline_ns <= intent.deadline_ns
                exact_frames(first, intent)

        count = len(predictions)
        assert len(allocated) == len(owners) == len(started) == len(scorer._jobs) == count
        assert len(slots) == len(trace.fence()) == len(seals) == count
        assert all(entry["kind"] == "guardian" and entry["process"]._creator_waited
                   and not entry["process"]._creator_ambiguous for entry in trace.fence())
        assert score_calls == predictions
        assert len(operation_exits) == count
        for operation, exited_at, facts in operation_exits:
            actual = allocated[score_tasks.index(operation)]
            fact = next(item for item in facts if item[0] is actual)
            assert fact[1] is actual._authority.ack and fact[2] and fact[3], (
                "SCORER_CALLER_ESCAPED_BEFORE_REAL_CLOSE_ACK")
            assert fact[1].completed_ns <= exited_at
        retained_tasks = tuple(job.close_task for job in scorer._jobs)
        assert await scorer.aclose() is None
        assert await scorer.aclose() is None
        assert tuple(job.close_task for job in scorer._jobs) == retained_tasks
        assert len(owner_closes) == count and len(shutdown_exits) == len(shutdown_entries) == 2
        try:
            await scorer.score_sql("")
        except ScoreInfrastructureError:
            pass
        else:
            raise AssertionError("closed scorer accepted new work")
        assert len(allocated) == len(owners) == count, "SCORER_CLOSE_REPLAYED_INVOCATION"
        assert dataclasses.asdict(task) == original_task
        assert dataclasses.asdict(instrument) == original_settings and not forbidden_calls
        return dict(decision="ack", allocations=count, dispatches=count, acks=count,
                    owner_closes=len(owner_closes), caller_cancellations=(
                        3 if PHASE == "score-adapter-cancel" else 0))

    async def run():
        nonlocal owner
        if sdk_wake_setup_error is not None:
            raise sdk_wake_setup_error
        binary = root / "guest-observer-inert"
        binary.write_bytes(b"never execute native observer bytes\n")
        source_root = m.installed_source_root()
        def pins(paths):
            return tuple(m.SourcePin(path, hashlib.sha256(
                (source_root / path).read_bytes()).hexdigest()) for path in paths)
        profile = m.make_execution_profile(
            daemon_socket=root / "guest-never-opened.sock",
            observer=m.MemoryObserver(binary=binary,
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),
            program_sources=pins(m._PROGRAM_PATHS),
            scorer_sources=pins(m._SCORER_PATHS),
            controller_sources=pins(("ptc/sql_isolation.py",)))
        db = root / "guest-inert-db"
        db.write_bytes(b"inert first-party bytes, not SQLite\n")
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        executor = m.PilotExecutor(profile, state_dir=root / "guest-run")
        if PHASE.startswith("sdk-"):
            from ptc.test_owned_sql_sdk_canonical import _run_sdk_host_case
            assert ROLE == ("program" if PHASE == "sdk-cancel-program" else "scorer")
            assert len(PREPARED) == 5
            assert MUTANT == "none" or (
                PHASE == "sdk-program-one"
                and MUTANT == "program-observation-sentinel") or (
                PHASE == "sdk-invalid-gold_error" and MUTANT == "invalid-target-zero") or (
                PHASE == "sdk-scoring-timeout" and MUTANT == "timeout-early-public-release") or (
                PHASE == "sdk-sibling-score-failure" and MUTANT == "omit-sibling-fault")
            actor = types.SimpleNamespace(
                owners=owners, spawn_lock=spawn_lock, stopping=stopping,
                gates=gates, trace=trace, slots=slots, next_event=next_event,
                messages=messages, release=release, test_gates=sdk_test_gates,
                ensure_intents=ensure_sdk_intents, diagnostic=sdk_diagnostic,
                emit=emit, end=END, retirement=sdk_resources,
                fence_owned_start=_fence_owned_start,
                forbidden_calls=forbidden_calls, bound_sockets=sdk_sockets,
                native_proof=sdk_native_proof, watchdog_race=sdk_watchdog_race)
            try:
                if _sdk_timeline is not None:
                    actor._sdk_timeline = _sdk_timeline
            except BaseException:
                pass
            return await _run_sdk_host_case(
                loop=LOOP, root=root, prepared=PREPARED, phase=PHASE,
                mutant=MUTANT, profile=profile, executor=executor, actor=actor)
        if PHASE.startswith("score-adapter-"):
            assert ROLE == "scorer" and MUTANT == "none"
            return await run_scorer_adapter(profile, db, digest, executor)
        if PHASE.startswith("adapter-"):
            assert ROLE == "program" and MUTANT == "none"
            return await run_adapter(profile, db, digest, executor)
        if ROLE == "program":
            owner = executor.owned_program("print(1)", db_path=str(db),
                                           db_sha256=digest, max_rows=1)
            request = m.ProgramRequest("print(1)", 1, digest)
        else:
            from bench.task import SqlTask
            from train.sql_episodes import InstrumentSettings
            task = SqlTask("guest-fixture", "q", "", "SELECT 1", "db", str(db),
                           "simple", "derived", "s", "s", "fixture")
            instrument = InstrumentSettings(1, 1, 1, "set", 1.0, 5.0, 1.0,
                                            "fixture", "fixture", (), "a"*64)
            owner = executor.owned_score("SELECT 1", task, db_sha256=digest,
                                         instrument=instrument)
            request = m.ScoreRequest(dataclasses.replace(task, db_path="/db.sqlite"),
                                      "SELECT 1", 1.0, 1, "set", digest)
        assert owner.snapshot().request_sha256 == m.request_sha256(request)
        observed_owner_failures = set()
        def observe_owner_failure(point, exc):
            if point in observed_owner_failures:
                return
            observed_owner_failures.add(point)
            try:
                failure_diagnostic(point, exc,
                    reason=exc.reason[:64] if isinstance(exc, m._Failure) else None)
            except BaseException:
                pass  # Diagnostic IO must not replace the real wait/exception.
        retained_wait, seal = owner._retained.wait, owner._seal
        def observe_retained_wait(*args, **kwargs):
            observe_owner_failure("controller-retained", sys.exception())
            return retained_wait(*args, **kwargs)
        def observe_seal(*args, **kwargs):
            try:
                return seal(*args, **kwargs)
            except BaseException as exc:
                observe_owner_failure("host-seal-error", exc)
                raise
        owner._retained.wait, owner._seal = observe_retained_wait, observe_seal
        joined_callers, caller_order = [], []
        second_execution = None
        original_cancel = None
        cancel_writes = []
        if PHASE == "concurrent-execute":
            start = owner._start
            def observe_started_caller():
                value = start()
                joined_callers.append(asyncio.current_task())
                emit("EXECUTE_REGISTERED", number=len(joined_callers))
                return value
            owner._start = observe_started_caller
        elif PHASE == "task-cancel":
            diagnosed_seal = owner._seal
            def observe_cancellation_seal(*args, **kwargs):
                value = diagnosed_seal(*args, **kwargs)
                caller_order.append(("ack", value, time.monotonic_ns()))
                return value
            owner._seal = observe_cancellation_seal
        execution = LOOP.create_task(owner.execute())
        intent = None
        history = None
        closing = None
        if PHASE in ("task-cancel", "concurrent-execute"):
            await next_event(lambda item: item["kind"] == "HIT" and item["name"] == PHASE)
            controller = owner._thread
            def assert_single_started_dispatch():
                children = trace.fence()
                assert len(children) == 1 and children[0]["kind"] == "guardian"
                actual_guardian = children[0]["process"]
                assert len(slots) == 1 and slots[0]["process"] is actual_guardian
                assert len(owner._children) == 1 and owner._children[0] is actual_guardian
                assert owner._thread is controller
                assert sum(item["kind"] == "RESOURCE" and item.get("actor") == "role"
                           for item in slots[0]["messages"]) == 1
            assert_single_started_dispatch()
            assert controller is not None and controller.is_alive()
            assert not execution.done() and owner._completion is None
            assert owner._authority.ack is None and owner.snapshot().intent is None
            if PHASE == "concurrent-execute":
                assert joined_callers == [execution]
                second_execution = LOOP.create_task(owner.execute())
                await next_event(lambda item:
                    item["kind"] == "EXECUTE_REGISTERED" and item["number"] == 2)
                assert joined_callers == [execution, second_execution]
                assert not execution.done() and not second_execution.done()
                assert owner._completion is None and owner._authority.ack is None
                assert_single_started_dispatch()
                release()
            else:
                # Only the actual owner.execute() task is cancelled, never a
                # shield, waiter or shadow task. Observe real endpoint writes.
                real_cancel_write = os.write
                cancel_write_original[0] = real_cancel_write
                def observe_cancel_write(fd, data):
                    endpoints = [endpoint for endpoint in owner._endpoints
                                 if endpoint.fd is not None and endpoint.fd == fd]
                    count = real_cancel_write(fd, data)
                    for endpoint in endpoints:
                        cancel_writes.append((endpoint, bytes(data), count))
                    return count
                os.write = observe_cancel_write
                def observe_cancelled_caller(actual):
                    # Do not retrieve its exception here: result() below must
                    # be the first retrieval of the actual original exception.
                    caller_order.append((
                        "caller-done", owner._completion, time.monotonic_ns(),
                        owner._authority.ack, actual.cancelled(),
                        not controller.is_alive(),
                        all(entry["process"]._creator_waited and
                            not entry["process"]._creator_ambiguous
                            for entry in trace.fence())))
                execution.add_done_callback(observe_cancelled_caller)
                async def cancellation_turn():
                    # cancel() queues this task's wakeup before this FIFO
                    # marker. A finite event-driven turn, not a blind sleep.
                    marker = LOOP.create_future()
                    LOOP.call_soon(marker.set_result, None)
                    await asyncio.wait_for(marker, timeout=remaining(
                        min(END-3.75, owner._cap())))
                    assert not execution.done(), "Task.cancel detached held cleanup"
                    frame = execution.get_coro().cr_frame
                    assert frame is not None
                    caught = frame.f_locals.get("original_cancel")
                    assert isinstance(caught, asyncio.CancelledError)
                    return caught
                first_message = "first started caller cancellation"
                before_cancel = time.monotonic_ns()
                assert execution.cancel(first_message)
                original_cancel = await cancellation_turn()
                assert execution.cancelling() == 1
                assert original_cancel.args == (first_message,)
                intent = owner.snapshot().intent
                assert intent is not None and intent.reason == "caller_cancelled"
                first_fields = (intent.invocation_id, intent.reason,
                                intent.requested_ns, intent.deadline_ns)
                assert before_cancel <= intent.requested_ns <= time.monotonic_ns()
                assert intent.deadline_ns == intent.requested_ns + CAP_NS
                consumed = {}
                while len(consumed) < 2:
                    item = await next_event(lambda item: item["kind"] == "CONSUMED")
                    assert item["lane"] not in consumed, "duplicate frame acquisition"
                    consumed[item["lane"]] = item
                assert set(consumed) == {"host", "guardian"}
                assert all(item["times"] == [intent.requested_ns, intent.deadline_ns]
                           for item in consumed.values())
                release()  # Consume the first pipe token, no sticky Event reset.
                await next_event(lambda item: item["kind"] == "HIT"
                                 and item["name"] == "cleanup-held")
                for number, message in ((2, "second during held cleanup"),
                                        (3, "third during held cleanup")):
                    assert execution.cancel(message)
                    assert await cancellation_turn() is original_cancel
                    assert execution.cancelling() == number
                    assert owner.snapshot().intent is intent
                    assert (intent.invocation_id, intent.reason,
                            intent.requested_ns, intent.deadline_ns) == first_fields
                    assert owner._completion is None and owner._authority.ack is None
                    assert not caller_order, "ACK/caller escape before cleanup release"
                    assert_single_started_dispatch()
                assert len(cancel_writes) == 2
                assert {id(row[0]) for row in cancel_writes} == {
                    id(endpoint) for endpoint in owner._endpoints}
                assert all(row[1] == m._encode_cancel_frame(intent) and row[2] == 40
                           for row in cancel_writes)
                release()  # A distinct second pipe token releases actual cleanup.
        if PHASE not in ("postseal", "task-cancel", "concurrent-execute"):
            await next_event(lambda item: item["kind"] == "HIT" and item["name"] == PHASE)
            if PHASE in ("protocol-before", "protocol-after"):
                if PHASE == "protocol-after":
                    job = root / "guest-run" / owner.invocation_id.hex
                    history = {path: path.read_bytes() for path in (
                        job / "journal.json", job / "outcome.json",
                        profile.shared_state_dir / (
                            "FINALIZATION-PENDING-" + owner.invocation_id.hex + ".json"),
                        profile.shared_state_dir / "history.jsonl")}
                endpoint = owner._endpoints[-1]
                if PHASE == "protocol-after":
                    receipt = owner.request_cancel("caller_cancelled")
                    assert receipt.status == "accepted"
                    intent = receipt.intent
                    consumed = await next_event(lambda item:
                        item["kind"] == "CONSUMED" and item["lane"] == "guardian")
                    assert consumed["times"] == [intent.requested_ns, intent.deadline_ns]
                    # DECLARED FAULT: an extra byte AFTER the real valid-frame
                    # acquisition, not an oversize first read or controller EOF.
                    assert os.write(endpoint.fd, b"x") == 1
                else:
                    requested = time.monotonic_ns()
                    raw = struct.pack(">8s16sQQ", b"BADMAGIC", owner.invocation_id.bytes,
                                      requested, requested+CAP_NS)
                    assert os.write(endpoint.fd, raw) == 40
                await next_event(lambda item: item["kind"] == "MONITOR_DONE"
                                 and item["error"])
            else:
                if PHASE == "late-after-role-deadline":
                    assert ROLE == "program"
                    await asyncio.sleep(max(0, owner._journal["deadline"]-time.monotonic())+0.02)
                receipt = owner.request_cancel("caller_cancelled")
                assert receipt.status == "accepted"
                intent = receipt.intent
            if PHASE.startswith("latency-"):
                seen = {}
                for item in messages:
                    if item["kind"] == "CONSUMED":
                        seen[item["lane"]] = item
                while len(seen) < 2:
                    item = await next_event(lambda item: item["kind"] == "CONSUMED", timeout=0.2)
                    seen[item["lane"]] = item
                assert set(seen) == {"host", "guardian"}
                for item in seen.values():
                    assert item["times"] == [intent.requested_ns, intent.deadline_ns]
                    assert 0 <= item["at_ns"]-intent.requested_ns <= 100000000
            if PHASE in ("postwire", "late-ambiguous", "postreap-fault",
                         "invalid-current-proof", "late-after-role-deadline"):
                assert owner._endpoints[-1].unavailable, "actual retired-reader EPIPE absent"
            release()
            if PHASE == "repeated":
                await next_event(lambda item: item["kind"] == "HIT"
                                 and item["name"] == "cleanup-held")
                assert not execution.done()
                two = owner.request_cancel("runner_closed")
                three = owner.request_cancel("caller_cancelled")
                assert two.status == three.status == "repeated"
                assert two.intent is three.intent is intent
                assert intent.deadline_ns == intent.requested_ns + CAP_NS
                assert not execution.done(), "caller escaped held actual cleanup"
                release()
            if PHASE in ("unknown-proof", "protocol-after"):
                if PHASE == "unknown-proof":
                    withheld = await next_event(
                        lambda item: item["kind"] == "RESOURCE_PROOF_WITHHELD")
                    assert withheld["fault_hits"] == 1
                closing = LOOP.create_task(owner.aclose())
                decision = await pending(execution, closing, at_cap=True)
                if history is not None:
                    assert all(path.read_bytes() == raw for path, raw in history.items()), (
                        "published immutable history changed after new monitor fault")
                else:
                    assert (profile.shared_state_dir / "active.json").exists()
                return decision
            if PHASE == "cli-fault":
                fault = next(item for item in messages
                             if item["kind"] == "HIT" and item["name"] == "cli-fault")
                await next_event(lambda item: item["kind"] == "ACTUAL_WAIT"
                                 and item.get("index") == fault["index"]
                                 and item.get("actor") == "cli")
                error = await next_event(lambda item: item["kind"] == "GUARDIAN_ERROR")
                assert error["fault_hits"] == ["cli-postcreation"]
                closing = LOOP.create_task(owner.aclose())
                return await pending(execution, closing)
            if PHASE in ("postreap-fault", "invalid-current-proof", "late-ambiguous"):
                applied = await next_event(lambda item: item["kind"] == (
                    "POSTREAP_FAULT" if PHASE == "postreap-fault"
                    else "CURRENT_PROOF_WITHHELD"))
                assert applied["count"] == 1
                closing = LOOP.create_task(owner.aclose())
                return await pending(execution, closing)
        wait_end = min(END-3.75, owner._cap())
        callers = [execution] if second_execution is None else [execution, second_execution]
        done, _ = await asyncio.wait(callers, timeout=remaining(wait_end))
        assert len(done) == len(callers), "responsive started-guest cleanup failed to issue ACK"
        if PHASE == "task-cancel":
            assert execution.cancelled() and execution.cancelling() == 3
            assert [item[0] for item in caller_order] == ["ack", "caller-done"]
            sealed, cancelled = caller_order
            completion = owner._completion
            assert completion is sealed[1] is cancelled[1]
            assert cancelled[3] is completion.cleanup_ack
            assert cancelled[4] and cancelled[5] and cancelled[6]
            assert completion.cleanup_ack.completed_ns <= sealed[2] <= cancelled[2]
            try:
                execution.result()
            except asyncio.CancelledError as exc:
                assert exc is original_cancel and exc.args == (first_message,)
                assert owner._authority.ack is completion.cleanup_ack
                assert cancelled[2] <= time.monotonic_ns()
            else:
                raise AssertionError("original caller cancellation did not propagate after ACK")
        else:
            completion = execution.result()
            if PHASE == "concurrent-execute":
                assert second_execution.result() is completion
        ack = completion.cleanup_ack
        if PHASE in ("task-cancel", "concurrent-execute"):
            retained_job = root / "guest-run" / owner.invocation_id.hex
            retained_artifacts = {path: path.read_bytes() for path in (
                retained_job / "outcome.json",
                profile.shared_state_dir / "history.jsonl")}
            assert await owner.execute() is completion
            assert all(path.read_bytes() == data
                       for path, data in retained_artifacts.items())
        assert ack.invocation_id == owner.invocation_id
        assert ack.role == ROLE and ack.request_sha256 == m.request_sha256(request)
        assert ack.profile_sha256 == m.execution_profile_sha256(profile)
        assert ack.child_waits and ack.thread_joins and not ack.not_started
        assert owner._thread is not None and not owner._thread.is_alive()
        assert all(entry["process"]._creator_waited and
                   not entry["process"]._creator_ambiguous for entry in trace.fence())
        assert ack.guardian_reaps == tuple(
            (entry["process"].pid, entry["process"].returncode) for entry in trace.fence())
        if intent is not None:
            assert completion.outcome is None and completion.abort.kind == "cancelled"
            assert completion.abort.role == ROLE
            assert completion.abort.invocation_id == intent.invocation_id
            assert intent.requested_ns <= ack.completed_ns <= ack.cleanup_deadline_ns
            assert ack.cleanup_deadline_ns <= intent.deadline_ns
            assert intent.deadline_ns == intent.requested_ns + CAP_NS
        elif PHASE == "protocol-before":
            assert completion.outcome is None and completion.abort.kind == "infrastructure"
            assert completion.abort.detail_code == "protocol"
        else:
            assert PHASE in ("postseal", "concurrent-execute") and completion.abort is None
            assert owner.snapshot().intent is None
            assert isinstance(completion.outcome,
                              m.ProgramOutcome if ROLE == "program" else m.ScoreOutcome)
            if PHASE == "concurrent-execute":
                assert completion.outcome.abort is None
                if ROLE == "program":
                    assert completion.outcome.observation == "static first-party role fixture"
                else:
                    assert completion.outcome.result is not None
        job = root / "guest-run" / owner.invocation_id.hex
        wire = m.decode_wire_message((job / "request.wire").read_bytes(), role=ROLE,
            kind="request", request_sha256=ack.request_sha256)
        assert wire.payload == request
        evidence = next((item for item in messages if item["kind"] == "EVIDENCE"), None)
        while evidence is None:
            evidence = await next_event(lambda item: item["kind"] == "EVIDENCE")
        actual = evidence["actual"]
        assert all(row["registered"] and row["waited"] and not row["ambiguous"]
                   and type(row["returncode"]) is int for row in actual)
        if PHASE == "latency-startup":
            assert not actual and evidence["observers"] == 0
        else:
            assert sum(row["actor"] == "role" for row in actual) == 1
            assert sum(row["actor"] == "cli" for row in actual) >= 2
            assert evidence["observers"] == 1 and evidence["released"]
        assert not evidence["forbidden"] and not forbidden_calls
        if PHASE == "protocol-before":
            assert evidence["accounted"] == [True]
            outcome = json.loads((job / "outcome.json").read_bytes())
            typed = (m.program_outcome_from_dict(outcome) if ROLE == "program"
                     else m.score_outcome_from_dict(outcome))
            assert typed.abort.reason == "protocol"
            assert (typed.observation if ROLE == "program" else typed.result) is None
        if PHASE == "late-after-role-deadline":
            committed = json.loads((profile.shared_state_dir / (
                "FINALIZATION-COMMITTED-"+owner.invocation_id.hex+".json")).read_bytes())
            release_at = committed["payload"]["terminal_ack"]["release_verified_at"]
            assert release_at < owner._journal["deadline"] < ack.completed_ns/1e9
        expected_hits = (0 if PHASE == "postseal"
                         else 2 if PHASE in ("repeated", "task-cancel") else 1)
        assert len(evidence["hits"]) + len(host_hits) == expected_hits
        if PHASE in ("task-cancel", "concurrent-execute"):
            assert_single_started_dispatch()
            assert sum(row["actor"] == "guardian" for row in trace.evidence()) == 1
            if PHASE == "task-cancel":
                assert owner.snapshot().intent is intent
                assert len(cancel_writes) == 2
                assert all(row[1] == m._encode_cancel_frame(intent) and row[2] == 40
                           for row in cancel_writes)
                assert sum(item["kind"] == "CONSUMED"
                           for item in slots[0]["messages"]) == 1
                os.write = cancel_write_original[0]
                cancel_write_original[0] = None
        writes = []
        original_write = os.write
        def observe_write(*args, **kwargs):
            writes.append(1)
            return original_write(*args, **kwargs)
        os.write = observe_write
        try:
            late = [owner.request_cancel(reason) for reason in
                    ("caller_cancelled", "runner_closed", "caller_cancelled")]
        finally:
            os.write = original_write
        assert not writes
        assert all(item.status == "already_completed" and item.intent is None for item in late)
        assert (await owner.aclose()) is ack
        if PHASE in ("task-cancel", "concurrent-execute"):
            assert await owner.execute() is completion
            assert (await owner.aclose()) is ack
            assert_single_started_dispatch()
            assert all(path.read_bytes() == data
                       for path, data in retained_artifacts.items())
            return dict(decision="ack", actors=actual, dispatches=1,
                        caller_cancellations=3 if PHASE == "task-cancel" else 0,
                        shared_completion=True)
        return dict(decision="ack", actors=actual)

    result, code = None, 0
    try:
        if sdk_resources is not None:
            with sdk_resources.loop_drive_lock:
                acceptance_driver = LOOP.create_task(run())
                sdk_resources.retain_driver(acceptance_driver)
                result = LOOP.run_until_complete(acceptance_driver)
        else:
            result = LOOP.run_until_complete(run())
        result = dict(ok=True, **result)
        if sdk_resources is not None and sdk_resources.outcome is not None:
            # A retirement checkpoint is explicitly NOT evaluation success.
            result.update(sdk_resources.outcome)
    except BaseException as exc:
        if sdk_resources is not None:
# CREATOR_BOUNDARY_BEGIN
# HOST_BUDGET_BEGIN
            _host_budget_diagnostic("HOST_EXCEPTION")
# HOST_BUDGET_END
# CREATOR_BOUNDARY_END
            sdk_resources.fail("host", exc)
            if PHASE == "sdk-program-one":
                from ptc.test_owned_sql_sdk_canonical import _program_acceptance_failure
                sdk_resources.program_failure = _program_acceptance_failure(
                    exc, sdk_resources)
# CREATOR_BOUNDARY_BEGIN
        if creator_boundary is not None:
            try:
                creator_boundary.emit(1, sdk_resources, owners, slots, trace)
            except BaseException:
                pass
# CREATOR_BOUNDARY_END
        fields = ("kind", "lane", "name", "actor", "index", "registered",
                  "independent")
        observed = [item for slot in slots for item in slot["messages"]]
        failure_diagnostic("host-error", exc,
            owner_state=owner._state if owner is not None else None,
            completion=owner is not None and owner._completion is not None,
            host_hits=host_hits[-8:],
            consumed=[{key: item[key] for key in fields
                       if key in item} for item in messages[-24:]],
            received=[{key: item[key] for key in fields
                       if key in item} for item in observed[-24:]])
        result, code = dict(
            (sdk_resources.outcome or {}) if PHASE in (
                "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                "sdk-sibling-score-failure") else {},
            ok=False, error=type(exc).__name__ if (
                PHASE.startswith("score-adapter-")
                or PHASE in (
                    "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                    "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                    "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                    "sdk-sibling-score-failure"))
            else type(exc).__name__+": "+str(exc)), 1
    finally:
        # Record the API decision before independently touching physical owners.
        result = dict(result or {}, mutation_hits=mutation_hits[0]+guardian_hits[0],
                      host_faults=host_faults,
                      hook_hits=sum(item["kind"] == "HIT" for item in messages))
        if cancel_write_original[0] is not None:
            os.write = cancel_write_original[0]
        if sdk_resources is not None:
            sdk_resources.record_outcome(result)
            sdk_resources.finish(
                native_retire=sdk_native_cleanup, verify_native=sdk_native_proof)
            result.update(sdk_resources.outcome or {})
            if result.get("ok") is not True:
                code = 1
            try:
                if (_sdk_timeline is not None
                        and ((sdk_resources.outcome or {}).get("ok") is not True
                             or not sdk_resources.finalized)):
                    _sdk_timeline.emit_failure()
            except BaseException:
                pass
            assert sdk_resources.finalized, "SDK_PHYSICAL_PROOF_MISSING"
            finished.set()
        else:
            cleanup()
        if unresolved_owners and result.get("ok") is True:
            if any(actual._completion is not None or actual._authority.ack is not None
                   for actual in unresolved_owners):
                result.update(ok=False, error="physical teardown upgraded unresolved scorer API")
                code = 1
        if PHASE == "adapter-missingproof" and result.get("ok") is True:
            # Independent physical SAFE must never manufacture public success.
            if any(actual._completion is not None or actual._authority.ack is not None
                   for actual in owners):
                result.update(ok=False, error="physical teardown upgraded unresolved API")
                code = 1
        denied = len(forbidden_calls) + sum(
            item.get("forbidden", 0) for slot in slots for item in slot["messages"]
            if item["kind"] == "SAFE")
        if denied:
            result.update(ok=False, error="forbidden fixture IO attempted", forbidden=denied)
            code = 1
            if sdk_resources is not None:
                sdk_resources.fail("forbidden", AssertionError("forbidden fixture IO attempted"))
                sdk_resources.record_outcome(result)
        os.write(done_w, b"D")
        supervisor.join(timeout=(max(0, END-time.monotonic())
                                 if sdk_resources is not None else 0.2))
        assert not supervisor.is_alive()
        LOOP.close()  # Pending unknown API tasks die only with this safe interpreter.
    report(result, code)


if MODE == "role":
    role_main()
elif MODE == "guardian":
    guardian_main()
else:
    assert MODE == "host"
    host_main()
'''


_OWNED_GUEST_OUTER_OWNERS = []


class _GuestOuterLedger(list):
    """Retain even an unsafe/partial outer object beyond an assertion unwind."""
    def append(self, process):
        _OWNED_GUEST_OUTER_OWNERS.append(process)
        super().append(process)


def _owned_guest_case(
        tmp_path, role, phase, *, mutant="none", prepared=None, expected_ok=True):
    """Private explicit driver. Each fresh interpreter gets one immutable mode.

    No env/profile selector or repository-source mutation. Unknown-proof and
    postpublication-protocol cases intentionally reach the REAL 12s intent cap;
    the separate program-R test crosses the REAL unchanged 10s role ceiling.
    All cases retain one shared 19.5s outer safety deadline.
    """
    assert type(expected_ok) is bool
    if not expected_ok:
        from ptc.test_owned_sql_sdk_retirement_physical import _PHYSICAL_PHASES
        assert phase in _PHYSICAL_PHASES and role == "scorer"
        assert mutant == "none" and prepared is not None and len(prepared) == 5
    assert prepared is None or (
        phase.startswith("sdk-") and len(prepared) == 5 and (
            mutant == "none" or (phase == "sdk-program-one"
                                and mutant == "program-observation-sentinel") or (
                phase == "sdk-invalid-gold_error" and mutant == "invalid-target-zero") or (
                phase == "sdk-scoring-timeout" and mutant == "timeout-early-public-release") or (
                phase == "sdk-sibling-score-failure" and mutant == "omit-sibling-fault")))
    assert phase != "sdk-sibling-score-failure" or (
        role == "scorer" and expected_ok and prepared is not None
        and type(prepared) is tuple and len(prepared) == 5
        and mutant in ("none", "omit-sibling-fault"))
    assert mutant != "omit-sibling-fault" or (
        phase == "sdk-sibling-score-failure" and role == "scorer"
        and prepared is not None and expected_ok)
    assert mutant != "program-observation-sentinel" or (
        phase == "sdk-program-one" and prepared is not None and expected_ok)
    assert mutant != "invalid-target-zero" or (
        phase == "sdk-invalid-gold_error" and role == "scorer"
        and prepared is not None and expected_ok)
    assert mutant != "timeout-early-public-release" or (
        phase == "sdk-scoring-timeout" and role == "scorer"
        and prepared is not None and expected_ok)
    prepared_args = [] if prepared is None else [str(value) for value in prepared]
    script = tmp_path / "owned-guest-fixture.py"
    script.write_text(_OWNED_GUEST_PROBE)
    registry = _GuestOuterLedger()
    deadline = time.monotonic() + 19.5
    result = None
    log = open(tmp_path / "owned-guest-fixture.stderr", "xb", buffering=0)
    try:
        process = _OwnedProbeProcess(
            [sys.executable, "-I", "-B", str(script), "host",
             str(m.installed_source_root()), str(tmp_path), role, phase, mutant,
             str(deadline), *prepared_args], registry=registry, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=log, bufsize=0,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        result = json.loads(_line(process, max(0, deadline-time.monotonic()-1.0)))
        assert result.get("safe") is True, "outer host omitted independent nested SAFE"
        process.wait(timeout=max(0.001, deadline-time.monotonic()))
        if expected_ok:
            if phase == "sdk-program-one" and not (
                    result.get("ok") is True and process.returncode == 0):
                # Pytest rewrites assert messages. Keep this actual receipt
                # dictionary for the phase-bound expected-failure proof.
                raise AssertionError(result)
            if phase in (
                    "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                    "sdk-invalid-gold_truncated", "sdk-invalid-db_missing") and not (
                    result.get("ok") is True and process.returncode == 0):
                raise AssertionError(result)
            if phase == "sdk-scoring-timeout" and not (
                    result.get("ok") is True and process.returncode == 0):
                raise AssertionError(result)
            if phase == "sdk-sibling-score-failure" and not (
                    result.get("ok") is True and process.returncode == 0):
                raise AssertionError(result)
            assert result.get("ok") is True and process.returncode == 0, result
        else:
            assert result.get("ok") is False and process.returncode == 1, result
            assert process.actual_wait
            assert result.get("physical_finalized") is True, result
            proof = result.get("physical_qualification", {})
            assert proof.get("verified") is True and proof.get("phase") == phase, json.dumps(proof)
            assert proof.get("fault_hits") == 1 and proof.get("primary_preserved") is True, result
            if phase == "sdk-retire-framework-finalizer":
                from ptc.test_owned_sql_sdk_retirement_physical import (
                    _framework_path_assert_location)
                assert result.get("error") == "AssertionError", result
                assert proof.get("original_assert_origin_verified") is True, result
                assert proof.get("original_assert_origin") == _framework_path_assert_location(
                    Path(__file__).with_name("test_bash_qa_eval_integration.py")), result
            else:
                assert result.get("error") == "_SdkPhysicalFault", result
            assert result.get("retirement_stages") == {
                "async": 1, "framework": 1, "executor": 1, "undo": 1}, result
            assert result.get("executor_workers", 0) >= 1, result
            assert result.get("executor_helpers", 0) >= 1, result
            assert result.get("live_executor_workers") == 0, result
            assert result.get("live_executor_helpers") == 0, result
            result["outer_actual_wait"] = process.actual_wait
        return result
    finally:
        try:
            for process in (tuple(registry) if phase in (
                    "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                    "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                    "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                    "sdk-sibling-score-failure") else registry):
                if getattr(process, "pid", None) is None:
                    continue
                try:
                    process.stdin.write(b"S")
                except (BrokenPipeError, ValueError):
                    pass
                if result is None:
                    result = json.loads(_line(process, max(0, deadline-time.monotonic())))
                # Exited hosts owe the identical proof. Exit code is NEVER absence.
                assert result.get("safe") is True, "unsafe outer lifetime owner retained"
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=max(0.001, deadline-time.monotonic()))
                assert process.actual_wait
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
                _OWNED_GUEST_OUTER_OWNERS.remove(process)
                if phase in (
                        "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                        "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                        "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                        "sdk-sibling-score-failure"):
                    registry.remove(process)
        finally:
            log.close()
        if phase in (
                "sdk-program-one", "sdk-cancel-program", "sdk-cancel-scorer",
                "sdk-invalid-gold_error", "sdk-invalid-gold_timeout",
                "sdk-invalid-gold_truncated", "sdk-invalid-db_missing", "sdk-scoring-timeout",
                "sdk-sibling-score-failure"):
            assert result is not None and result.get("safe") is True
            assert process.actual_wait and type(process.returncode) is int
            streams_closed = all(stream is None or stream.closed for stream in (
                process.stdin, process.stdout, process.stderr))
            ledger_released = process not in registry and process not in _OWNED_GUEST_OUTER_OWNERS
            assert streams_closed and ledger_released
            result["outer_retirement"] = dict(
                actual_wait=process.actual_wait, returncode=process.returncode,
                streams_closed=streams_closed, ledger_released=ledger_released)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("phase", [
    "preSTART", "inflight", "result-reception", "publication", "postwire"])
def test_owned_guest_remaining_cancellation_boundaries(tmp_path, role, phase):
    result = _owned_guest_case(tmp_path, role, phase)
    assert result["decision"] == "ack" and result["hook_hits"] == 1


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("phase", ["latency-startup", "latency-transport", "latency-terminal"])
def test_owned_guest_actual_notification_consumption_under_100ms(tmp_path, role, phase):
    _owned_guest_case(tmp_path, role, phase)


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_three_intents_keep_cleanup_caller_held(tmp_path, role):
    _owned_guest_case(tmp_path, role, "repeated")


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_cli_postcreation_retains_actual_creator(tmp_path, role):
    result = _owned_guest_case(tmp_path, role, "cli-fault")
    assert result["decision"] == "pending" and result["hook_hits"] == 1


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_missing_proof_at_real_intent_cap_stays_pending(tmp_path, role):
    result = _owned_guest_case(tmp_path, role, "unknown-proof")
    assert result["decision"] == "pending" and result["at_cap"] is True


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("phase", ["late-ambiguous", "postreap-fault"])
def test_owned_guest_late_missing_proof_never_issues_ack(tmp_path, role, phase):
    result = _owned_guest_case(tmp_path, role, phase)
    assert result["decision"] == "pending" and result["hook_hits"] == 1


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_host_seal_rejects_retroactive_intent_without_writes(tmp_path, role):
    _owned_guest_case(tmp_path, role, "postseal")


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_malformed_before_publication_has_typed_protocol_ack(tmp_path, role):
    _owned_guest_case(tmp_path, role, "protocol-before")


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_new_malformed_after_publication_keeps_history_and_no_ack(tmp_path, role):
    result = _owned_guest_case(tmp_path, role, "protocol-after")
    assert result["decision"] == "pending" and result["at_cap"] is True


def test_owned_guest_late_cancel_can_seal_after_real_program_ceiling(tmp_path):
    _owned_guest_case(tmp_path, "program", "late-after-role-deadline")


@pytest.mark.parametrize("control", ["registration", "cleanup-validation"])
def test_owned_guest_canonical_mutants_hit_resource_assertion_and_restore(tmp_path, control):
    phase = "preSTART" if control == "registration" else "invalid-current-proof"
    intended = ("CREATOR_REGISTRATION_BEFORE_PUBLICATION" if control == "registration"
                else "HOST_ACK_WITH_INVALID_CURRENT_PROOF")
    for name, mutant in (("baseline", "none"), ("mutant", control), ("restored", "none")):
        root = tmp_path / name
        root.mkdir()
        if mutant == "none":
            result = _owned_guest_case(root, "program", phase, mutant=mutant)
            assert result["mutation_hits"] == 0
        else:
            with pytest.raises(AssertionError, match=intended) as failure:
                _owned_guest_case(root, "program", phase, mutant=mutant)
            assert "'mutation_hits': 1" in str(failure.value), (
                "canonical bypass did not hit exactly once")


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_three_task_cancellations_wait_for_ack(tmp_path, role):
    result = _owned_guest_case(tmp_path, role, "task-cancel")
    assert result["decision"] == "ack" and result["hook_hits"] == 2
    assert result["caller_cancellations"] == 3 and result["dispatches"] == 1
    assert result["shared_completion"] is True


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_owned_guest_concurrent_started_execute_callers_share_completion(tmp_path, role):
    result = _owned_guest_case(tmp_path, role, "concurrent-execute")
    assert result["decision"] == "ack" and result["hook_hits"] == 1
    assert result["caller_cancellations"] == 0 and result["dispatches"] == 1
    assert result["shared_completion"] is True


# Intended RED until the adapter exists. Parent source/security review MUST
# precede actor execution; these nodes claim no actual SDK/native/SQL activation.
def test_owned_sql_adapter_normal_rejected(tmp_path):
    result = _owned_guest_case(tmp_path, "program", "adapter-normal-rejected")
    assert result["decision"] == "ack" and result["hook_hits"] == 0
    assert result["dispatches"] == result["acks"] == 2
    assert result["requests"] == 3 and result["runner_closes"] == 1


def test_owned_sql_adapter_normal_error(tmp_path):
    result = _owned_guest_case(tmp_path, "program", "adapter-normal-error")
    assert result["decision"] == "ack" and result["hook_hits"] == 0
    assert result["dispatches"] == result["acks"] == 2
    assert result["requests"] == 3 and result["runner_closes"] == 1


def test_owned_sql_adapter_cancel(tmp_path):
    result = _owned_guest_case(tmp_path, "program", "adapter-cancel")
    assert result["decision"] == "ack" and result["hook_hits"] == 2
    assert result["dispatches"] == result["acks"] == result["requests"] == 1
    assert result["caller_cancellations"] == 3 and result["runner_closes"] == 1


def test_owned_sql_adapter_infrastructure(tmp_path):
    result = _owned_guest_case(tmp_path, "program", "adapter-infrastructure")
    assert result["decision"] == "ack" and result["hook_hits"] == 1
    assert result["dispatches"] == result["acks"] == result["requests"] == 1
    assert result["runner_closes"] == 1


def test_owned_sql_adapter_missingproof(tmp_path):
    result = _owned_guest_case(tmp_path, "program", "adapter-missingproof")
    assert result["decision"] == "pending" and result["at_cap"] is True
    assert result["hook_hits"] == 1 and result["acks"] == 0
    assert result["dispatches"] == result["requests"] == result["caller_cancellations"] == 1


# New scorer actors remain BLOCKED until parent Python/security source clearance.
# Static SCORER frames prove lifetime and forwarding, not SQL accuracy or rewards.
@pytest.mark.parametrize("status", [
    "match", "mismatch", "pred_error", "pred_timeout", "pred_truncated",
    "pred_empty", "gold_error", "gold_timeout", "gold_truncated", "db_missing",
])
def test_owned_sql_scorer_native_result_identity(tmp_path, status):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-status-" + status)
    assert result["decision"] == "ack" and result["hook_hits"] == 0
    assert result["allocations"] == result["dispatches"] == result["acks"] == 1
    assert result["owner_closes"] == 1 and result["caller_cancellations"] == 0


def test_owned_sql_scorer_two_predictions_preserve_private_request(tmp_path):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-requests")
    assert result["decision"] == "ack" and result["hook_hits"] == 0
    assert result["allocations"] == result["dispatches"] == result["acks"] == 2
    assert result["owner_closes"] == 2


def test_owned_sql_scorer_three_cancellations_wait_for_actual_ack(tmp_path):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-cancel")
    assert result["decision"] == "ack" and result["hook_hits"] == 2
    assert result["allocations"] == result["dispatches"] == result["acks"] == 1
    assert result["owner_closes"] == 1 and result["caller_cancellations"] == 3


def test_owned_sql_scorer_protocol_abort_is_fatal_without_replay(tmp_path):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-infrastructure")
    assert result["decision"] == "ack" and result["hook_hits"] == 1
    assert result["allocations"] == result["dispatches"] == result["acks"] == 1
    assert result["owner_closes"] == 1 and result["caller_cancellations"] == 0


def test_owned_sql_scorer_missing_proof_at_real_cap_stays_pending(tmp_path):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-missingproof")
    assert result["decision"] == "pending" and result["at_cap"] is True
    assert result["hook_hits"] == 1
    assert result["allocations"] == result["dispatches"] == 1 and result["acks"] == 0
    assert result["shutdown_pending"] is False


def test_owned_sql_scorer_shutdown_starts_all_real_close_tasks(tmp_path):
    result = _owned_guest_case(tmp_path, "scorer", "score-adapter-shutdown")
    assert result["decision"] == "pending" and result["at_cap"] is True
    assert result["hook_hits"] == 1 and result["shutdown_pending"] is True
    assert result["allocations"] == result["owner_closes"] == 2
    assert result["dispatches"] == result["acks"] == 1
