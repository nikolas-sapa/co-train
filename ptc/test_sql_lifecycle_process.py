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

MODE = sys.argv[1]
SCRIPT = str(Path(__file__).resolve())
if MODE == "host":
    SOURCE, ROOT, ROLE, PHASE, MUTANT = sys.argv[2:7]
    END = float(sys.argv[7])
    LOOP = asyncio.new_event_loop()  # Anonymous self-pipe, before network guards.
else:
    JOB, ROLE = Path(sys.argv[2]), sys.argv[3]
    SOURCE = str(JOB / "controller")
    if MODE == "guardian":
        PHASE, MUTANT, END = sys.argv[4], sys.argv[5], float(sys.argv[6])
    else:
        END = float(sys.argv[4])
        PHASE, MUTANT = "", "none"
sys.path.insert(0, SOURCE)
from ptc import sql_isolation as m

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
CAP_NS = 12000000000
forbidden_calls = []
def forbidden(*args, **kwargs):
    forbidden_calls.append(1)
    raise AssertionError("GUEST_FIXTURE_FORBIDDEN_NATIVE_NETWORK_SQL_OR_GROUP_IO")
socket.socket.connect = socket.socket.connect_ex = socket.socket.bind = forbidden
socket.getaddrinfo = forbidden
sqlite3.connect = forbidden
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

def failure_diagnostic(where, exc=None, **state):
    # Bounded code locations only: never locals, source lines, request bytes,
    # exception text, absolute paths, or synthetic proof/ACK substitutions.
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
        response = m.ProgramResponse("static first-party role fixture", False)
    else:
        from bench.score import ExResult
        response = ExResult(1.0, "match", True, "static fixture, not SQL", 1, 1)
    result = m.encode_wire_message(
        ROLE, "result", response, request_sha256=journal["request_sha256"])
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
                     ROLE, str(END)], _registry=state.role_registry,
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
                      "task-cancel", "concurrent-execute") and kind == "REQUEST_DELIVERED" or
            PHASE == "latency-startup" and kind == "GUARDIAN_ACK")
        if selected and PHASE not in hits:
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
        if PHASE in ("repeated", "task-cancel") and "cleanup-held" not in hits:
            barrier("cleanup-held")
        return cleanup(*args, **kwargs)
    m._cleanup_owned = observe_cleanup
    evidence = m._owned_cleanup_evidence
    def observe_evidence(*args, **kwargs):
        value = evidence(*args, **kwargs)
        if PHASE in ("unknown-proof", "protocol-before") and PHASE not in hits:
            barrier(PHASE)
        if PHASE == "unknown-proof":
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
        emit("GUARDIAN_ERROR", error=type(exc).__name__ + ": " + str(exc),
             fault_hits=fault_hits)
        # Ordinary errors MUST NOT exit a supervisor owning nested work. Only
        # the independent watchdog can discharge this non-daemon lifetime.
        lifetime.wait()


def host_main():
    root = Path(ROOT)
    stopping, finished = threading.Event(), threading.Event()
    spawn_lock, cleanup_lock = threading.Lock(), threading.Lock()
    done_r, done_w = os.pipe()
    owner = None
    slots, messages, gates = [], [], []
    queue = asyncio.Queue()
    host_hits, host_faults = [], []
    mutation_hits = [0]
    cached_validation = [None]
    cancel_write_original = [None]
    keeper = threading.Thread(target=finished.wait,
                              name="guest-fixture-host-lifetime", daemon=False)
    keeper.start()
    def emit(kind, **data):
        item = dict(kind=kind, lane="host", **data)
        LOOP.call_soon_threadsafe(queue.put_nowait, item)
    trace = CreatorTrace(emit, stopping)

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
                    slot["messages"].append(item)
                    if item["kind"] == "SAFE":
                        assert item.get("independent") is True
                        assert all(row["waited"] and not row["ambiguous"]
                                   and type(row["returncode"]) is int for row in item["actual"])
                        slot["safe"].set()
                    LOOP.call_soon_threadsafe(queue.put_nowait, item)
        except BaseException as exc:
            LOOP.call_soon_threadsafe(queue.put_nowait,
                dict(kind="READER_ERROR", error=type(exc).__name__ + ": " + str(exc)))

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
                reader_stop_w=stop_w,
                fds=[gate_w, diagnostic_r, safety_w, stop_r, stop_w])
            slots.append(slot)  # Register channels before actual BasePopen.
            thread = threading.Thread(target=reader, args=(slot,),
                                      name="guest-fixture-diagnostics", daemon=False)
            slot["reader"] = thread
            thread.start()
            try:
                process = invocation._spawn(
                    [sys.executable, "-I", "-B", SCRIPT, "guardian", str(job),
                     ROLE, PHASE, MUTANT, str(END), str(control_fd), str(cancel_fd),
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

    acquire = m._acquire_cancel_frame
    def observe_acquisition(*args, **kwargs):
        value = acquire(*args, **kwargs)
        emit("CONSUMED", at_ns=time.monotonic_ns(), times=list(value))
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

    def cleanup():
        stopping.set()
        for event in gates:
            event.set()
        with cleanup_lock:
            if finished.is_set():
                return
            with spawn_lock:
                pass  # Fence constructors before freezing the independent ledger.
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
            if owner is not None:
                owner._retained.set()  # Physical safety only, never an ACK.
                if owner._thread is not None:
                    owner._thread.join(timeout=remaining(end))
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
        keeper.join(timeout=0.2)
        assert not keeper.is_alive()
        write_record(1, dict(safe=True, **result))
        os._exit(code)
    def watchdog():
        ready = select.select([0, done_r], [], [], remaining(END-3.75))[0]
        if done_r in ready:
            return
        try:
            cleanup()
        except BaseException:
            return  # Lifetime keeper prevents unsafe ordinary-error exit.
        report(dict(ok=False, error="independent fixture safety deadline"), 91)
    supervisor = threading.Thread(target=watchdog, name="guest-host-safety", daemon=False)
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
                    "cli-fault", "unknown-proof", "protocol-after", "postreap-fault"):
                raise AssertionError(item["error"])

    def release():
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

    async def run():
        nonlocal owner
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
        result = LOOP.run_until_complete(run())
        result = dict(ok=True, **result)
    except BaseException as exc:
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
        result, code = dict(ok=False, error=type(exc).__name__+": "+str(exc)), 1
    finally:
        # Record the API decision before independently touching physical owners.
        result = dict(result or {}, mutation_hits=mutation_hits[0]+guardian_hits[0],
                      host_faults=host_faults,
                      hook_hits=sum(item["kind"] == "HIT" for item in messages))
        if cancel_write_original[0] is not None:
            os.write = cancel_write_original[0]
        cleanup()
        denied = len(forbidden_calls) + sum(
            item.get("forbidden", 0) for slot in slots for item in slot["messages"]
            if item["kind"] == "SAFE")
        if denied:
            result.update(ok=False, error="forbidden fixture IO attempted", forbidden=denied)
            code = 1
        os.write(done_w, b"D")
        supervisor.join(timeout=0.2)
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


def _owned_guest_case(tmp_path, role, phase, *, mutant="none"):
    """Private explicit driver. Each fresh interpreter gets one immutable mode.

    No env/profile selector or repository-source mutation. Unknown-proof and
    postpublication-protocol cases intentionally reach the REAL 12s intent cap;
    the separate program-R test crosses the REAL unchanged 10s role ceiling.
    All cases retain one shared 19.5s outer safety deadline.
    """
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
             str(deadline)], registry=registry, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=log, bufsize=0,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        result = json.loads(_line(process, max(0, deadline-time.monotonic()-1.0)))
        assert result.get("safe") is True, "outer host omitted independent nested SAFE"
        process.wait(timeout=max(0.001, deadline-time.monotonic()))
        assert result.get("ok") is True and process.returncode == 0, result
        return result
    finally:
        try:
            for process in registry:
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
        finally:
            log.close()


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
