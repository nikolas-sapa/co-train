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
