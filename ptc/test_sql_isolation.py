"""Closed contracts and daemon-free regressions using trusted local fixtures."""
import dataclasses
import hashlib
import importlib
import inspect
import json
from pathlib import Path

import pytest


def api():
    module = importlib.import_module("ptc.sql_isolation")
    assert hasattr(module, "SourcePin"), "Phase0 concrete SourcePin contract missing"
    return module


def fixture_profile(tmp_path):
    m = api()
    (tmp_path / "module.py").write_text("# first-party fixture\n")
    binary = tmp_path / "colima-fixture"
    binary.write_bytes(b"not executed\n")
    pin = m.SourcePin("module.py", hashlib.sha256((tmp_path / "module.py").read_bytes()).hexdigest())
    observer = m.MemoryObserver(binary=binary, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return m.make_execution_profile(daemon_socket=tmp_path / "daemon.sock", observer=observer,
        program_sources=(pin,), scorer_sources=(pin,), controller_sources=(pin,))


def test_frozen_records_and_exact_signatures(tmp_path):
    m = api()
    profile = fixture_profile(tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.admission_bytes = 1
    executor = m.PilotExecutor(profile, state_dir=tmp_path / "run")
    assert executor.profile.binding == profile.binding
    assert tuple(inspect.signature(executor.run_program).parameters) == ("program", "db_path", "db_sha256", "max_rows")
    assert tuple(inspect.signature(executor.score_sql).parameters) == ("predicted_sql", "task", "db_sha256", "instrument")
    assert inspect.signature(executor.run_program).parameters["db_path"].kind == inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("path", ["", ".", "..", "../x", "/x", "a/../x", "a//x", "a/./x", "a\\x", "C:x", "x\x00"])
def test_source_path_rejects(path):
    with pytest.raises((TypeError, ValueError)):
        api().SourcePin(path, "a" * 64)


@pytest.mark.parametrize("digest", ["A" * 64, "g" * 64, "a" * 63, True, None])
def test_digest_strict(digest):
    with pytest.raises((TypeError, ValueError)):
        api().SourcePin("a.py", digest)


def test_binding_closed_roundtrip_and_fingerprint(tmp_path):
    m = api()
    p = fixture_profile(tmp_path)
    raw = m.execution_binding_to_dict(p.binding)
    assert m.execution_binding_from_dict(raw) == p.binding
    assert m.execution_binding_sha256(p.binding) == hashlib.sha256(m.canonical_json_bytes(raw)).hexdigest()
    for field in raw:
        bad = dict(raw); del bad[field]
        with pytest.raises((TypeError, ValueError)):
            m.execution_binding_from_dict(bad)
    with pytest.raises(ValueError):
        m.execution_binding_from_dict({**raw, "extra": 1})
    with pytest.raises((TypeError, ValueError)):
        m.execution_binding_from_dict({**raw, "schema_version": True})


@pytest.mark.parametrize("role,field,value", [
    ("program", "memory_bytes", 268435457), ("program", "swap_bytes", 1),
    ("program", "pids", True), ("program", "deadline_ms", 10001),
    ("scorer", "deadline_ms", 30001), ("scorer", "stdout_bytes", 1048576),
    ("program", "input_bytes", 8388609), ("program", "nofile", 65),
    ("program", "tmp_bytes", 16777217), ("program", "shm_bytes", 1048577),
])
def test_limits_and_role_reject_nonapproved(role, field, value):
    m = api()
    with pytest.raises((TypeError, ValueError)):
        limits = dataclasses.replace(m.limits_for(role), **{field: value})
        m.RoleBinding(role, m.IMAGE_MANIFEST_SHA256, m.IMAGE_CONFIG_SHA256,
            "linux/arm64", (m.SourcePin("a.py", "a" * 64),), "b" * 64, limits)


@pytest.mark.parametrize("maximum", [65536, 8388608, 67108864, 1048576, 131072, 16777216, 1048576])
def test_exact_plus_one_bytes(maximum):
    m = api()
    exact = b"x" * maximum
    assert m.bounded_bytes(exact, maximum=maximum) is exact
    with pytest.raises(ValueError):
        m.bounded_bytes(exact + b"x", maximum=maximum)


def test_utf8_program_boundary():
    m = api()
    assert m.ProgramRequest("é" * 32768, 1, "a" * 64).max_rows == 1
    for program in ("é" * 32768 + "x", "\ud800"):
        with pytest.raises((TypeError, ValueError)):
            m.ProgramRequest(program, 1, "a" * 64)
    with pytest.raises((TypeError, ValueError)):
        m.ProgramRequest("pass", True, "a" * 64)


def test_profile_envelope_hashes_and_readonly_load(tmp_path, monkeypatch):
    m = api(); p = fixture_profile(tmp_path)
    import socket
    import subprocess
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(1); raise AssertionError("Phase0 must never perform runtime IO")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = m.execution_profile_canonical_bytes(p)
    envelope = json.loads(raw)
    assert set(envelope) == {"format", "schema_version", "payload", "sha256"}
    assert envelope["format"] == "sql_pilot_execution_profile"
    assert envelope["sha256"] == m.execution_profile_payload_sha256(p)
    assert m.execution_profile_sha256(p) == hashlib.sha256(raw).hexdigest()
    assert m.execution_profile_sha256(p) != m.execution_profile_payload_sha256(p)
    assert m.execution_profile_from_bytes(raw) == p
    file = tmp_path / "profile.json"; file.write_bytes(raw)
    assert m.load_execution_profile(file, source_root=tmp_path) == p
    assert m.build_execution_binding(p, source_root=tmp_path) == p.binding
    for wrong in (True, 2):
        bad = dict(envelope); bad["schema_version"] = wrong
        with pytest.raises((TypeError, ValueError)):
            m.execution_profile_from_bytes(m.canonical_json_bytes(bad) + b"\n")
    try:
        outcome = m.PilotExecutor(p, state_dir=tmp_path / "run").run_program(
            "pass", db_path="/db.sqlite", db_sha256="a" * 64, max_rows=1)
    except NotImplementedError:
        outcome = None
    assert outcome is not None, "production boundary must return a typed local refusal"
    assert outcome.abort is not None and outcome.receipt is None
    assert outcome.observation is None and outcome.rejected is False
    assert calls == []


def test_source_context_escape_mutation_and_duplicates(tmp_path):
    m = api(); p = fixture_profile(tmp_path)
    (tmp_path / "module.py").write_text("# changed\n")
    with pytest.raises(ValueError):
        m.build_execution_binding(p, source_root=tmp_path)
    other = tmp_path / "outside"; other.mkdir(); (other / "x.py").write_text("pass")
    root = tmp_path / "inside"; root.mkdir(); (root / "alias").symlink_to(other, target_is_directory=True)
    pin = m.SourcePin("alias/x.py", hashlib.sha256(b"pass").hexdigest())
    with pytest.raises(ValueError):
        m.validate_source_pins((pin,), source_root=root)
    with pytest.raises(ValueError):
        dataclasses.replace(p.binding.program, sources=(pin, pin))
    assert m.installed_source_root() == Path(m.__file__).resolve().parents[1]


def test_shared_daemon_dir_not_run_dir(tmp_path):
    m = api(); p = fixture_profile(tmp_path)
    import os
    import pwd
    expected = Path(pwd.getpwuid(os.getuid()).pw_dir) / "scratch/co-train-isolation-shared" / (
        str(os.getuid()) + "-" + hashlib.sha256(str(p.daemon_socket.resolve()).encode()).hexdigest())
    assert m.shared_state_dir_for(p.daemon_socket) == expected
    assert m.PilotExecutor(p, state_dir=tmp_path / "one").profile.shared_state_dir == m.PilotExecutor(p, state_dir=tmp_path / "two").profile.shared_state_dir
    with pytest.raises(ValueError):
        dataclasses.replace(p, shared_state_dir=tmp_path / "bad")
    with pytest.raises(ValueError):
        m.shared_state_dir_for(Path("tcp://127.0.0.1"))


@pytest.mark.parametrize("field,value", [
    ("root_readonly", False), ("uid", 0), ("gid", True), ("network_mode", "host"),
    ("pid_mode", "host"), ("ipc_mode", "host"), ("cgroupns_mode", "host"),
    ("hostname", "wrong"), ("cap_drop", ()), ("no_new_privileges", False),
    ("readonly_paths", ()), ("masked_paths", ()), ("seccomp_syscalls", ("socket",)),
])
def test_closed_security_policy(field, value):
    m = api()
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(m.SecurityPolicy(), **{field: value})


def test_outcome_branches_receipts_and_actual_exresult():
    m = api()
    receipt = m.RuntimeReceipt("scorer", "a" * 64, "3.12.15", "3.45.1", "b" * 64, "c" * 64)
    from bench.score import ExResult
    result = ExResult(1.0, "match", True, "", 1, 1)
    out = m.ScoreOutcome(result, None, receipt)
    assert m.score_outcome_from_dict(m.score_outcome_to_dict(out)) == out
    assert m.runtime_receipt_from_dict(m.runtime_receipt_to_dict(receipt)) == receipt
    abort = m.AbortInfo("scorer", "cleanup")
    assert m.abort_info_from_dict(m.abort_info_to_dict(abort)) == abort
    assert m.ScoreOutcome(None, abort, None).result is None
    with pytest.raises(ValueError):
        m.ScoreOutcome(result, abort, receipt)
    with pytest.raises(ValueError):
        m.ProgramOutcome(None, None, None)
    with pytest.raises((TypeError, ValueError)):
        m.ScoreOutcome({"score": 1.0}, None, receipt)
    with pytest.raises((TypeError, ValueError)):
        m.ScoreOutcome(ExResult(float("nan"), "match", True), None, receipt)
    with pytest.raises((TypeError, ValueError)):
        m.ScoreOutcome(ExResult(1.0, "match", True, "", True, 1), None, receipt)


def test_wire_exact_envelope_context_and_db_hash():
    m = api()
    request = m.ProgramRequest("pass", 3, "a" * 64)
    h = m.request_sha256(request)
    raw = m.encode_wire_message("program", "request", request)
    assert raw.endswith(b"\n") and len(m.READY) == 13 and m.READY == b"PILOT_READY!\n"
    data = json.loads(raw)
    assert set(data) == {"format", "schema_version", "role", "kind", "request_sha256", "payload", "sha256"}
    assert data["sha256"] == data["request_sha256"] == h
    assert m.decode_wire_message(raw, role="program", kind="request", request_sha256=h).payload == request
    assert h != m.request_sha256(dataclasses.replace(request, db_sha256="b" * 64))
    for key, value in (("role", "scorer"), ("kind", "result"), ("request_sha256", "b" * 64),
                       ("schema_version", True), ("sha256", "d" * 64), ("extra", 1)):
        bad = {**data, key: value}
        with pytest.raises((TypeError, ValueError)):
            m.decode_wire_message(m.canonical_json_bytes(bad) + b"\n", role="program", kind="request", request_sha256=h)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{"a":Infinity}\n',
    b'\xff\n', b'{}\n{}\n', b'{}', b'{}\r\n', b'{"a":"\\ud800"}\n'])
def test_malformed_json_wire(raw):
    with pytest.raises((TypeError, ValueError)):
        api().decode_wire_message(raw, role="program", kind="request", request_sha256="a" * 64)


def test_bootstrap_and_result_typed_payloads():
    m = api()
    pin = m.SourcePin("ptc/runtime.py", "a" * 64)
    payload = m.BootstrapPayload("3.12.15", "3.45.1", (pin,), "b" * 64)
    raw = m.encode_wire_message("program", "bootstrap", payload)
    assert m.decode_wire_message(raw, role="program", kind="bootstrap", request_sha256=None).payload == payload
    result = m.ProgramResponse("OK", False)
    encoded = m.encode_wire_message("program", "result", result, request_sha256="c" * 64)
    assert m.decode_wire_message(encoded, role="program", kind="result", request_sha256="c" * 64).payload == result
    with pytest.raises((TypeError, ValueError)):
        m.encode_wire_message("program", "result", result)
    with pytest.raises((TypeError, ValueError)):
        m.ProgramResponse("OK", 1)
    with pytest.raises(ValueError):
        m.validate_output_budget("scorer", bootstrap=b"x" * 65524, result=b"")
    m.validate_output_budget("scorer", bootstrap=b"x" * 65523, result=b"")


def test_explicit_canonical_source_helpers(tmp_path):
    m = api(); p = fixture_profile(tmp_path)
    assert hasattr(m, "execution_binding_canonical_bytes"), "whole binding canonical helper missing"
    assert hasattr(m, "source_pins_sha256"), "canonical source-set hash helper missing"
    assert m.execution_binding_sha256(p.binding) == hashlib.sha256(m.execution_binding_canonical_bytes(p.binding)).hexdigest()
    assert m.source_pins_sha256(p.binding.controller_sources) == hashlib.sha256(m.canonical_json_bytes([{"path": x.path, "sha256": x.sha256} for x in p.binding.controller_sources])).hexdigest()
    assert m.execution_profile_envelope(p) == json.loads(m.execution_profile_canonical_bytes(p))


def test_observer_binary_is_not_an_8mib_artifact_and_may_use_pinned_install_symlink(tmp_path):
    m = api(); p = fixture_profile(tmp_path)
    binary = tmp_path / "real-binary-fixture"; binary.write_bytes(b"x" * (8388608 + 1))
    alias = tmp_path / "installed-colima-fixture"; alias.symlink_to(binary)
    observer = m.MemoryObserver(binary=alias, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    p = m.make_execution_profile(daemon_socket=p.daemon_socket, observer=observer,
        program_sources=p.binding.program.sources, scorer_sources=p.binding.scorer.sources,
        controller_sources=p.binding.controller_sources)
    assert m.build_execution_binding(p, source_root=tmp_path) == p.binding


def test_scorer_wire_native_types_without_host_sql(tmp_path, monkeypatch):
    m = api()
    from bench.task import SqlTask
    from bench.score import ExResult
    import sqlite3
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(1); raise AssertionError("pure codecs must never execute SQL")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    task = SqlTask("fixture", "question", "", "SELECT 1", "db", "/db.sqlite", "simple", "derived", "rowcount", "rowcount", "fixture")
    request = m.ScoreRequest(task, "SELECT 1", 1.0, 10, "set", "a" * 64)
    h = m.request_sha256(request)
    raw = m.encode_wire_message("scorer", "request", request)
    assert m.decode_wire_message(raw, role="scorer", kind="request", request_sha256=h).payload == request
    result = ExResult(0.0, "gold_error", False, "original detail", 0, 0)
    raw = m.encode_wire_message("scorer", "result", result, request_sha256=h)
    assert m.decode_wire_message(raw, role="scorer", kind="result", request_sha256=h).payload == result
    for timeout in (True, float("inf"), float("nan"), 30.1):
        with pytest.raises((TypeError, ValueError)):
            dataclasses.replace(request, timeout_s=timeout)
    with pytest.raises(ValueError):
        dataclasses.replace(request, task=dataclasses.replace(task, db_path="/host.sqlite"))
    assert calls == []


def rejection_api():
    m = api()
    signature = inspect.signature(m.ProgramOutcome)
    assert "rejected" in signature.parameters, "ProgramOutcome native rejected flag missing"
    return m


def program_receipt(m):
    return m.RuntimeReceipt("program", "a" * 64, "3.12.15", "3.45.1", "b" * 64, "c" * 64)


def assert_rejected_wire_outcome_roundtrip():
    """Shared positive assertion used unchanged by the isolated drop-flag mutant."""
    m = rejection_api()
    text = 'FINAL_SQL: SELECT COUNT(*) FROM "quoted table"\nexact rejection evidence\n'
    receipt = program_receipt(m)
    response = m.ProgramResponse(text, True)
    wire = m.encode_wire_message("program", "result", response, request_sha256=receipt.request_sha256)
    assert set(json.loads(wire)["payload"]) == {"observation", "rejected"}
    decoded_response = m.decode_wire_message(wire, role="program", kind="result",
        request_sha256=receipt.request_sha256).payload
    completed = m.ProgramOutcome(decoded_response.observation, None, receipt,
        rejected=decoded_response.rejected)
    payload = m.program_outcome_to_dict(completed)
    assert set(payload) == {"observation", "abort", "receipt", "rejected"}
    restored = m.program_outcome_from_dict(payload)
    assert restored.rejected is True, "native rejected flag lost across wire/outcome codec"
    assert restored.observation == text
    assert restored.receipt == receipt
    assert restored.abort is None
    assert not hasattr(restored, "result")


def test_program_rejection_signature_preserves_three_positional_arguments():
    m = rejection_api()
    parameters = inspect.signature(m.ProgramOutcome).parameters
    assert tuple(parameters) == ("observation", "abort", "receipt", "rejected")
    assert parameters["rejected"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["rejected"].default is False
    assert dataclasses.fields(m.ProgramOutcome)[-1].kw_only
    assert m.ProgramOutcome("completed", None, program_receipt(m)).rejected is False


def test_rejected_wire_outcome_roundtrip_preserves_final_sql_evidence():
    assert_rejected_wire_outcome_roundtrip()


@pytest.mark.parametrize("flag", [0, 1])
def test_program_rejection_integer_flags_reject_constructor_and_codec(flag):
    m = rejection_api()
    with pytest.raises((TypeError, ValueError)):
        m.ProgramOutcome("completed", None, program_receipt(m), rejected=flag)
    payload = m.program_outcome_to_dict(m.ProgramOutcome("completed", None, program_receipt(m)))
    payload["rejected"] = flag
    with pytest.raises((TypeError, ValueError)):
        m.program_outcome_from_dict(payload)


@pytest.mark.parametrize("retain_receipt", [False, True])
def test_infrastructure_abort_cannot_be_native_rejection(retain_receipt):
    m = rejection_api()
    with pytest.raises(ValueError):
        m.ProgramOutcome(None, m.AbortInfo("program", "cleanup"),
            program_receipt(m) if retain_receipt else None, rejected=True)


@pytest.mark.parametrize("flag", [False, True])
def test_completed_program_requires_actual_receipt_even_when_rejected(flag):
    m = rejection_api()
    with pytest.raises(ValueError):
        m.ProgramOutcome("FINAL_SQL: SELECT 1\n", None, None, rejected=flag)


def test_program_outcome_codec_requires_exactly_four_keys():
    m = rejection_api()
    payload = m.program_outcome_to_dict(m.ProgramOutcome("completed", None, program_receipt(m)))
    assert set(payload) == {"observation", "abort", "receipt", "rejected"}
    missing = dict(payload); del missing["rejected"]
    with pytest.raises(ValueError):
        m.program_outcome_from_dict(missing)
    with pytest.raises(ValueError):
        m.program_outcome_from_dict({**payload, "extra": False})


def test_nonrejected_text_and_infrastructure_receipt_remain_distinct():
    m = rejection_api()
    receipt = program_receipt(m)
    text = "FINAL_SQL: SELECT 1\nrejected-looking text is not a flag"
    completed = m.ProgramOutcome(text, None, receipt, rejected=False)
    assert m.program_outcome_from_dict(m.program_outcome_to_dict(completed)) == completed
    assert completed.rejected is False and completed.abort is None
    aborted = m.ProgramOutcome(None, m.AbortInfo("program", "protocol"), receipt)
    assert m.program_outcome_from_dict(m.program_outcome_to_dict(aborted)) == aborted
    assert aborted.rejected is False


def boundary_api(name):
    m = api()
    assert hasattr(m, name), f"production boundary implementation missing: {name}"
    return getattr(m, name)


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_database_sidecar_refusal_never_deletes_original(tmp_path, suffix):
    stage = boundary_api("_stage_database")
    db = tmp_path / "fixture.sqlite"; db.write_bytes(b"owned database fixture")
    sidecar = Path(str(db) + suffix); sidecar.write_bytes(b"preserve")
    output = tmp_path / "stage"; output.mkdir()
    with pytest.raises((ValueError, OSError)):
        stage(db, hashlib.sha256(db.read_bytes()).hexdigest(), output)
    assert db.read_bytes() == b"owned database fixture"
    assert sidecar.read_bytes() == b"preserve"


def test_database_snapshot_exact_expected_sha_and_readonly_copy(tmp_path):
    stage = boundary_api("_stage_database")
    db = tmp_path / "fixture.sqlite"; db.write_bytes(b"owned database fixture")
    output = tmp_path / "stage"; output.mkdir()
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    copy = stage(db, digest, output)
    assert copy.read_bytes() == db.read_bytes()
    assert copy.stat().st_ino != db.stat().st_ino
    assert copy.stat().st_mode & 0o222 == 0
    bad = tmp_path / "bad"; bad.mkdir()
    with pytest.raises((ValueError, OSError)):
        stage(db, "0" * 64, bad)
    assert not (bad / "db.sqlite").exists()


def test_database_hardlinks_and_symlinks_refused(tmp_path):
    stage = boundary_api("_stage_database")
    import os
    db = tmp_path / "fixture.sqlite"; db.write_bytes(b"owned database fixture")
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    link = tmp_path / "link.sqlite"; link.symlink_to(db)
    output = tmp_path / "stage"; output.mkdir()
    with pytest.raises((ValueError, OSError)):
        stage(link, digest, output)
    link.unlink(); os.link(db, link)
    with pytest.raises((ValueError, OSError)):
        stage(db, digest, output)
    assert link.read_bytes() == db.read_bytes()


@pytest.mark.parametrize("changes", [
    {"Running": True}, {"Paused": True}, {"Restarting": True}, {"Pid": True},
    {"Pid": 1}, {"Pid": 0.0}, {"Running": 0}, {"Paused": None},
    {"Restarting": False, "Pid": "0"},
])
def test_409_requires_exact_fresh_stopped_state(changes):
    check = boundary_api("_stopped_state")
    good = {"Running": False, "Paused": False, "Restarting": False, "Pid": 0}
    assert check(good) is True
    assert check({**good, **changes}) is False


def test_mux_exact_cap_and_plus_one_abort_without_opposite_drain():
    decoder = boundary_api("_MuxDecoder")
    import struct
    m = decoder(stdout_limit=13, stderr_limit=13)
    packet = lambda stream, body: bytes([stream, 0, 0, 0]) + struct.pack(">I", len(body)) + body
    assert m.feed(packet(1, b"PILOT_READY!\n")) == [(1, b"PILOT_READY!\n")]
    with pytest.raises(Exception, match="output"):
        m.feed(packet(1, b"x") + packet(2, b"never-drain"))
    assert m.counts == {1: 14, 2: 0}


def test_worker_forwards_native_fields_without_observation_inference():
    worker_path = Path(__file__).with_name("sql_worker.py")
    assert worker_path.is_file(), "production PROGRAM worker missing"
    worker = importlib.import_module("ptc.sql_worker")
    from ptc.sql_arms import PtcResult
    native = PtcResult("error: ZeroDivisionError: division by zero", True)
    assert worker._response_for(native) == api().ProgramResponse(native.observation, True)
    native = PtcResult("rejected-looking accepted text", False)
    assert worker._response_for(native).rejected is False


# Review regressions. These use only trusted tiny fixtures/local servers, not Docker.
REVIEW_DISABLE_DECODER_GUARD = False
REVIEW_FIXTURE_ACCEPTS = 0
REVIEW_SOCKET_ROOTS = set()
REVIEW_RESOURCE_DELTAS = []
REVIEW_PROCESS_RESULTS = []


@pytest.fixture(autouse=True)
def _review_owned_socket_cleanup():
    import threading
    import os
    before = set(REVIEW_SOCKET_ROOTS)
    threads = set(threading.enumerate())
    fds = len(os.listdir("/dev/fd"))
    yield
    for root in REVIEW_SOCKET_ROOTS - before:
        socket = root / "fixture.sock"
        if socket.exists():
            socket.unlink()
        root.rmdir()
        REVIEW_SOCKET_ROOTS.remove(root)
    alive = [t.name for t in set(threading.enumerate()) - threads if t.is_alive()]
    delta = len(os.listdir("/dev/fd")) - fds
    REVIEW_RESOURCE_DELTAS.append({"fd_delta": delta, "new_live_threads": alive})
    assert not alive, "owned test thread leaked"
    assert delta == 0, "owned test FD count changed"


def _review_profile(tmp_path):
    import tempfile
    m = api()
    binary = tmp_path / "observer-not-executed"
    binary.write_bytes(b"first-party fixture, never executed")
    root = m.installed_source_root()
    pins = lambda names: tuple(m.SourcePin(p, hashlib.sha256((root / p).read_bytes()).hexdigest()) for p in names)
    socket_root = Path(tempfile.mkdtemp(prefix="production-boundary-reviewfix-unix-", dir="/tmp")).resolve()
    REVIEW_SOCKET_ROOTS.add(socket_root)
    return m.make_execution_profile(daemon_socket=socket_root / "fixture.sock",
        observer=m.MemoryObserver(binary=binary, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),
        program_sources=pins(m._PROGRAM_PATHS), scorer_sources=pins(m._SCORER_PATHS),
        controller_sources=pins(("ptc/sql_isolation.py",)))


def _review_job(tmp_path, profile, *, cid=None):
    m = api()
    job = tmp_path / "job"; job.mkdir()
    nonce = "review-owned"
    j = {"nonce": nonce, "role": "program", "cid": cid, "name": "co-train-sql-" + nonce,
         "config": m._container_config(profile, "program", job, nonce),
         "create_attempted": cid is not None, "kill_attempted": False, "guardians": [],
         "actors_initialized": True, "deadline": m.time.monotonic() + 10, "bootstrap": None}
    m._event(job, "ACTORS_INITIALIZED", nonce=nonce)
    m._save_journal(job, j)
    return job, j


def _owned_fixture_object(j):
    import copy
    cfg = copy.deepcopy(j["config"]); host = cfg.pop("HostConfig"); host["Runtime"] = "runc"
    return {"Id": j["cid"], "Image": "sha256:" + api().IMAGE_MANIFEST_SHA256,
            "Name": "/" + j["name"], "Config": cfg, "HostConfig": host,
            "State": {"Running": False, "Paused": False, "Restarting": False, "Pid": 0},
            "Mounts": [{"Type": "bind", "Source": x["Source"], "Destination": x["Target"],
                        "RW": False, "Propagation": "rprivate"} for x in host["Mounts"]]}


def _normalization_fixture(tmp_path, role):
    m = api(); profile = fixture_profile(tmp_path)
    journal = {"cid": "a" * 64, "name": "co-train-sql-normalization", "role": role,
               "config": m._container_config(profile, role, tmp_path, "normalization")}
    return journal, _owned_fixture_object(journal)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("swappiness", [0, None], ids=["requested-zero", "explicit-null"])
def test_swappiness_normalization_accepts_only_capped_zero(tmp_path, role, swappiness):
    m = api(); journal, obj = _normalization_fixture(tmp_path, role)
    requested = m.canonical_json_bytes(journal["config"])
    host = journal["config"]["HostConfig"]
    assert type(host["MemorySwappiness"]) is int and host["MemorySwappiness"] == 0
    assert host["Memory"] == host["MemorySwap"] == 268435456
    obj["HostConfig"]["MemorySwappiness"] = swappiness
    failure = None
    try:
        verified = m._verify_owned(obj, journal)
    except m._Failure as exc:
        failure = exc
    assert failure is None, "explicit capped zero/null swappiness rejected: " + str(failure)
    assert verified is obj
    assert m.canonical_json_bytes(journal["config"]) == requested, "CREATE payload was normalized"


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("swappiness", ["missing", False, True, 0.0, "0", 1, -1],
                         ids=["missing", "false", "true", "float", "string", "nonzero", "unlimited"])
def test_swappiness_normalization_rejects_other_values(tmp_path, role, swappiness):
    m = api(); journal, obj = _normalization_fixture(tmp_path, role)
    if swappiness == "missing":
        obj["HostConfig"].pop("MemorySwappiness")
    else:
        obj["HostConfig"]["MemorySwappiness"] = swappiness
    with pytest.raises(m._Failure, match="HostConfig mismatch: MemorySwappiness"):
        m._verify_owned(obj, journal)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("expected", [False, True, 0.0, "0", 1, -1],
                         ids=["false", "true", "float", "string", "nonzero", "unlimited"])
def test_swappiness_normalization_requires_requested_integer_zero(tmp_path, role, expected):
    m = api(); journal, obj = _normalization_fixture(tmp_path, role)
    journal["config"]["HostConfig"]["MemorySwappiness"] = expected
    obj["HostConfig"]["MemorySwappiness"] = None
    with pytest.raises(m._Failure, match="HostConfig mismatch: MemorySwappiness"):
        m._verify_owned(obj, journal)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("key", ["Memory", "MemorySwap"])
@pytest.mark.parametrize("side", ["actual", "both"])
@pytest.mark.parametrize("value", ["missing", None, False, True, 268435456.0, "268435456",
                                  0, -2, -1, 134217728],
                         ids=["missing", "null", "false", "true", "float", "string",
                              "zero", "negative", "unlimited", "changed"])
def test_swappiness_normalization_requires_exact_caps(tmp_path, role, key, side, value):
    m = api(); journal, obj = _normalization_fixture(tmp_path, role)
    obj["HostConfig"]["MemorySwappiness"] = None
    hosts = [obj["HostConfig"]]
    if side == "both":
        hosts.append(journal["config"]["HostConfig"])
    for host in hosts:
        if value == "missing":
            host.pop(key)
        else:
            host[key] = value
    with pytest.raises(m._Failure, match="HostConfig mismatch"):
        m._verify_owned(obj, journal)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["cid", "image", "label", "config", "pids", "capability",
                                  "mount-source", "mount-write", "extra-mount"])
def test_swappiness_normalization_keeps_other_bindings(tmp_path, role, fault):
    m = api(); journal, obj = _normalization_fixture(tmp_path, role)
    obj["HostConfig"]["MemorySwappiness"] = None
    if fault == "cid":
        obj["Id"] = "b" * 64
    elif fault == "image":
        obj["Image"] = "sha256:" + "b" * 64
    elif fault == "label":
        obj["Config"]["Labels"][m._OWNER_LABEL] = "foreign"
    elif fault == "config":
        obj["Config"]["User"] = "0:0"
    elif fault == "pids":
        obj["HostConfig"]["PidsLimit"] = True
    elif fault == "capability":
        obj["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    elif fault == "mount-source":
        obj["Mounts"][0]["Source"] = "/foreign"
    elif fault == "mount-write":
        obj["Mounts"][0]["RW"] = True
    else:
        obj["Mounts"].append(dict(obj["Mounts"][0]))
    with pytest.raises(m._Failure):
        m._verify_owned(obj, journal)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("expired", [False, True], ids=["remaining-budget", "expired-budget"])
def test_swappiness_normalization_created_cleanup_keeps_order_and_budget(tmp_path, monkeypatch, role, expired):
    m = api(); profile = fixture_profile(tmp_path)
    job, journal = _review_job(tmp_path, profile, cid="a" * 64)
    journal["role"] = role
    journal["config"] = m._container_config(profile, role, job, journal["nonce"])
    clock = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    m._begin_cleanup(journal)
    trigger, deadline = journal["cleanup_trigger"], journal["cleanup_deadline"]
    assert deadline - trigger == 12.0
    clock[0] += 12.0 if expired else 7.0
    class Fixture:
        active = set()
        removed = False
        def __init__(self):
            self.calls = []
        def call(self, method, path, *args, **kwargs):
            self.calls.append((method, path))
            clock[0] += 0.5
            if method == "POST":
                assert path == f"/containers/{journal['cid']}/kill?signal=SIGKILL"
                raise m._HTTPFailure(409)
            if method == "DELETE":
                self.removed = True
                return None
            assert method == "GET" and path == f"/containers/{journal['cid']}/json"
            if self.removed:
                raise m._HTTPFailure(404)
            obj = _owned_fixture_object(journal)
            obj["HostConfig"]["MemorySwappiness"] = None
            obj["State"]["Status"] = "created"
            return obj
    daemon = Fixture()
    failure = None
    try:
        m._cleanup_owned(profile, daemon, journal, job, None)
    except m._Failure as exc:
        failure = exc
    assert journal["cleanup_trigger"] == trigger and journal["cleanup_deadline"] == deadline
    assert daemon.cleanup_deadline == deadline
    kinds = [json.loads(line)["kind"] for line in (job / "events.jsonl").read_text().splitlines()]
    if expired:
        assert failure is not None and failure.reason == "cleanup", "expired original budget was reset"
        assert not daemon.calls and not daemon.removed
        assert not any(kind in kinds for kind in ("STOPPED", "OBSERVER_JOIN_ACK", "DELETE", "ABSENCE"))
    else:
        assert failure is None, "normalized created-state cleanup failed: " + str(failure)
        assert [k for k in kinds if k in ("STOPPED", "OBSERVER_JOIN_ACK", "DELETE", "ABSENCE")] == [
            "STOPPED", "OBSERVER_JOIN_ACK", "DELETE", "ABSENCE"]
        assert kinds.count("KILL409_STOPPED_PROOF") == 1 and daemon.removed
        assert journal["cleanup_elapsed"] == 10.0 < 12.0
        assert len(daemon.calls) == 6


class _LocalHTTP:
    """Owned UNIX fixture. Handler receives raw request, returns status/body/delay."""
    def __init__(self, path, handler):
        import socket
        import threading
        self.path, self.handler = path, handler
        self.stop = threading.Event()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(path)); self.socket.listen(16); self.socket.settimeout(0.05)
        self.threads, self.connections, self.requests = [], [], []
        self.body_bytes = 0
        self.thread = threading.Thread(target=self._serve)
        self.thread.start()

    def _serve(self):
        global REVIEW_FIXTURE_ACCEPTS
        import socket
        import threading
        while not self.stop.is_set():
            try:
                conn, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            REVIEW_FIXTURE_ACCEPTS += 1
            self.connections.append(conn)
            thread = threading.Thread(target=self._one, args=(conn,))
            self.threads.append(thread); thread.start()

    def _one(self, conn):
        try:
            conn.settimeout(1)
            data = bytearray()
            while not data.endswith(b"\r\n\r\n"):
                part = conn.recv(1)
                if not part:
                    return
                data.extend(part)
                assert len(data) < 16384
            line = bytes(data).split(b"\r\n", 1)[0].decode("ascii")
            self.requests.append(line)
            status, body, delay, drip = self.handler(line)
            import time
            if delay:
                self.stop.wait(delay)
            header = f"HTTP/1.1 {status} fixture\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            if drip:
                payload = header + body
                if drip < 0:
                    conn.sendall(header)
                    payload = body
                for byte in payload:
                    if self.stop.wait(abs(drip)):
                        return
                    conn.sendall(bytes([byte]))
                    if drip < 0:
                        self.body_bytes += 1
            else:
                conn.sendall(header + body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client intentionally cancels this owned fixture connection.
        finally:
            conn.close()

    def close(self):
        self.stop.set(); self.socket.close()
        for conn in self.connections:
            try:
                import socket
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        self.thread.join(1)
        for thread in self.threads:
            thread.join(1)
            assert not thread.is_alive(), "fixture handler must join"
        assert not self.thread.is_alive()


def test_review_1_isolated_decoder_uses_verified_complete_staged_union(tmp_path):
    import subprocess
    import sys
    m = api(); p = _review_profile(tmp_path)
    job = tmp_path / "staged"; job.mkdir(); m._stage_sources(p, job)
    (job / "profile.json").write_bytes(m.execution_profile_canonical_bytes(p))
    foreign = tmp_path / "foreign"; (foreign / "bench").mkdir(parents=True)
    (foreign / "bench/__init__.py").write_text("raise RuntimeError('FOREIGN BENCH TRAP')\n")
    # Only trusted first-party decoder/data execute in this real -I interpreter.
    code = (
        "import sys,runpy,json,pathlib;"
        f"sys.path=[x for x in sys.path if x!={str(m.installed_source_root())!r}];"
        f"sys.path.insert(0,{str(foreign)!r});"
        f"g=runpy.run_path({str(job / 'controller/ptc/sql_isolation.py')!r});"
        f"p=g['execution_profile_from_bytes'](pathlib.Path({str(job / 'profile.json')!r}).read_bytes());"
        + ("g['_activate_staged_import_root']=lambda *a:None;" if REVIEW_DISABLE_DECODER_GUARD else "")
        + f"g.get('_activate_staged_import_root',lambda *a:None)(pathlib.Path({str(job)!r}),p);"
        "r=g['_ex_from_dict']({'score':1.0,'status':'match','valid':True,'detail':'','n_pred_rows':1,'n_gold_rows':1});"
        "import bench,ptc,dataclasses;"
        "print(json.dumps({'result':dataclasses.asdict(r),'bench':bench.__file__,'ptc':ptc.__file__,'path':sys.path}))"
    )
    child = subprocess.Popen([sys.executable, "-I", "-B", "-c", code],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        output, error = child.communicate(timeout=5)
    finally:
        if child.poll() is None:
            child.kill(); child.communicate(timeout=2)
        REVIEW_PROCESS_RESULTS.append({"pid": child.pid, "proof": "owned Popen.wait/communicate", "returncode": child.returncode})
    assert child.returncode == 0, "verified isolated SCORER decode failed: " + error.decode()
    decoded = json.loads(output)
    assert decoded["result"] == {"score": 1.0, "status": "match", "valid": True, "detail": "",
                                  "n_pred_rows": 1, "n_gold_rows": 1}
    assert Path(decoded["bench"]).is_relative_to(job / "controller")
    assert Path(decoded["ptc"]).is_relative_to(job / "controller")
    assert str(m.installed_source_root()) not in decoded["path"]


def test_review_2_inflight_create_empty_list_never_releases_reservation(tmp_path, monkeypatch):
    import subprocess
    import sys
    import threading
    import types
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p)
    j["create_attempted"] = True
    entered, release, registered = threading.Event(), threading.Event(), threading.Event()
    def handler(line):
        if line.startswith("POST"):
            entered.set(); release.wait(2); registered.set()
            return 201, b'{"Id":"' + b"a" * 64 + b'"}', 0, 0
        return 200, b"[]", 0, 0
    server = _LocalHTTP(p.daemon_socket, handler)
    code = ("import socket,sys;"
            "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
            f"s.connect({str(p.daemon_socket)!r});"
            "s.sendall(b'POST /containers/create HTTP/1.1\\r\\nHost: fixture\\r\\nContent-Length: 0\\r\\n\\r\\n');"
            "s.recv(1)")
    guardian = subprocess.Popen([sys.executable, "-I", "-B", "-c", code])
    try:
        assert entered.wait(1)
        guardian.kill(); guardian.wait(timeout=1)  # Exact owned Popen, not a guessed PID.
        failure = None
        try:
            m._cleanup_owned(p, m._Daemon(p), j, job, None)
        except m._Failure as exc:
            failure = exc
        assert failure is not None, "empty list falsely proved completion of in-flight CREATE"
        shared = tmp_path / "shared"; shared.mkdir()
        (shared / "active.json").write_text(json.dumps({"nonce": j["nonce"], "job": str(job)}))
        m._block(types.SimpleNamespace(shared_state_dir=shared), j, job, str(failure))
        release.set(); assert registered.wait(1)
        assert j["state"] == "UNRESOLVED"
        assert (shared / "active.json").exists()
        assert list(shared.glob("UNRESOLVED-*.json"))
        assert not list(shared.glob("CLOSED-*"))
        # Exercise the production dispatch admission branch with fixture-local
        # storage only. No public profile validation rule is relaxed.
        private_profile = types.SimpleNamespace(
            **{field.name: getattr(p, field.name) for field in dataclasses.fields(p)})
        private_profile.shared_state_dir = shared
        monkeypatch.setattr(m, "build_execution_binding", lambda *a, **k: p.binding)
        next_executor = types.SimpleNamespace(profile=private_profile, state_dir=tmp_path / "next-run")
        refused = m._run_isolated(next_executor, "program", m.ProgramRequest("pass", 1, "a" * 64),
                                  tmp_path / "never-staged.sqlite")
        assert refused.abort == m.AbortInfo("program", "admission")
        assert not list((tmp_path / "next-run").glob("*/journal.json"))
        assert not any("/start" in request for request in server.requests)
        assert sum(request.startswith("POST /containers/create") for request in server.requests) == 1
    finally:
        release.set()
        if guardian.poll() is None:
            guardian.kill()
        guardian.wait(timeout=1)
        REVIEW_PROCESS_RESULTS.append({"pid": guardian.pid, "proof": "owned Popen.wait", "returncode": guardian.returncode})
        server.close()


def test_review_3_inflight_retirement_failure_cannot_ack_or_close(tmp_path, monkeypatch):
    import os
    import threading
    import types
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p)
    j["guardians"] = [os.getpid()]
    m._save_journal(job, j)
    observer = m._Observer(p, types.SimpleNamespace(active=set()), job)
    entered = threading.Event()
    def fail_during_join(*args):
        entered.set()
        observer.stop.wait(1)
        raise m._ObservationFailure("controlled in-flight sample failure")
    monkeypatch.setattr(m, "_memory_sample", fail_during_join)
    observer.latest = {"started": m.time.monotonic(), "finished": m.time.monotonic(),
                       "eligible": True, "available": p.admission_bytes}
    assert observer.check() is True
    observer.thread.start()
    assert entered.wait(1)
    failure = None
    try:
        observer.retire()
    except m._Failure as exc:
        failure = exc
    assert failure is not None, "retirement swallowed the in-flight observation failure"
    assert not observer.thread.is_alive()
    kinds = [json.loads(line)["kind"] for line in (job / "events.jsonl").read_text().splitlines()]
    assert "OBSERVER_JOIN_ACK" not in kinds
    assert "CLOSED" not in kinds


def _diagnostic_retirement(tmp_path, monkeypatch, case, write_failure=None):
    import os
    import threading
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p, cid="a" * 64)
    j["guardians"] = [os.getpid()]
    m._save_journal(job, j)
    observer = m._Observer(p, m._Daemon(p), job)
    entered, release = threading.Event(), threading.Event()
    canary = "DIAGNOSTIC_PRIVATE_CANARY_94c0"
    def vm_memory(*args):
        assert observer.stop.wait(1)
        return 1073741824, 1073741824
    monkeypatch.setattr(m, "_vm_memory", vm_memory)
    original_event = m._event
    def event(path, kind, **values):
        if kind in (write_failure or ()):
            raise OSError(canary)
        return original_event(path, kind, **values)
    monkeypatch.setattr(m, "_event", event)
    def handler(line):
        assert line.startswith("GET "), "diagnostic fixture attempted a daemon mutation"
        if line.startswith("GET /info "):
            return 200, b'{"MemTotal":1073741824}', 0, 0
        if line.startswith("GET /containers/json "):
            if case == "invalid-cid":
                entered.set(); assert observer.stop.wait(1)
                return 200, m.canonical_json_bytes([{"Id": canary, "State": "running"}]), 0, 0
            return 200, m.canonical_json_bytes([{"Id": j["cid"], "State": "running"}]), 0, 0
        assert line.startswith(f"GET /containers/{j['cid']}/stats?")
        entered.set()
        if case == "deadline":
            release.wait(0.8)
        else:
            assert observer.stop.wait(1)
        if case == "http503":
            return 503, canary.encode(), 0, 0
        if case == "bad-json":
            return 200, ('{"' + canary + '":').encode(), 0, 0
        stats = {"memory_stats": {"usage": 1048576}, "private": canary}
        if case == "missing-usage":
            stats["memory_stats"] = {"private": canary}
        elif case == "string-usage":
            stats["memory_stats"]["usage"] = canary
        elif case == "missing-memory-stats":
            stats.pop("memory_stats")
        elif case == "invalid-stats":
            stats = canary
        return 200, m.canonical_json_bytes(stats), 0, 0
    class Cleanup:
        active = set()
        removed = False
        def call(self, method, path, *args, **kwargs):
            if method == "POST":
                assert path.endswith("/kill?signal=SIGKILL")
                raise m._HTTPFailure(409)
            if method == "DELETE":
                self.removed = True
                return None
            assert method == "GET"
            if self.removed:
                raise m._HTTPFailure(404)
            return _owned_fixture_object(j)
    daemon = Cleanup()
    server = _LocalHTTP(p.daemon_socket, handler)
    observer.thread.start()
    failure = None
    try:
        assert entered.wait(1), "owned metadata RPC did not enter"
        j["cleanup_trigger"] = m.time.monotonic() - (11.9 if case == "deadline" else 11.0)
        j["cleanup_deadline"] = j["cleanup_trigger"] + 12.0
        original = j["cleanup_deadline"]
        began = m.time.monotonic()
        try:
            m._cleanup_owned(p, daemon, j, job, observer)
        except m._Failure as exc:
            failure = exc
        elapsed = m.time.monotonic() - began
        assert j["cleanup_deadline"] == original and daemon.cleanup_deadline == original
        if case == "deadline":
            assert failure is not None and failure.reason == "cleanup"
            assert elapsed < 0.30, "diagnostics added a fresh join budget"
        elif case == "healthy":
            assert failure is None
        else:
            assert isinstance(failure, m._ObservationFailure)
            assert str(failure) == "failure discovered during observer retirement"
        records = [json.loads(line) for line in (job / "events.jsonl").read_text().splitlines()]
        assert canary not in (job / "events.jsonl").read_text()
        if failure is not None:
            assert not daemon.removed
            assert not any(e["kind"] in ("OBSERVER_JOIN_ACK", "DELETE", "CLOSED") for e in records)
        else:
            assert daemon.removed
            assert [e["kind"] for e in records if e["kind"] in (
                "STOPPED", "OBSERVER_JOIN_ACK", "DELETE", "ABSENCE")] == [
                "STOPPED", "OBSERVER_JOIN_ACK", "DELETE", "ABSENCE"]
        return records, failure, observer
    finally:
        release.set(); observer.stop.set(); observer.thread.join(2); server.close()
        assert not observer.thread.is_alive()


@pytest.mark.parametrize("case", ["missing-usage", "string-usage", "missing-memory-stats",
                                  "invalid-stats", "http503", "bad-json", "invalid-cid", "healthy"])
def test_observer_diagnostic_owned_metadata_failure(tmp_path, monkeypatch, case):
    records, failure, observer = _diagnostic_retirement(tmp_path, monkeypatch, case)
    diagnostics = [e for e in records if e["kind"] == "OBSERVER_FAILURE"]
    if case == "healthy":
        assert not diagnostics
        assert not any(e["kind"] == "MEMORY_STATS_REJECTED" for e in records)
        return
    assert len(diagnostics) == 1, "original observer cause was not durably recorded"
    diagnostic = diagnostics[0]
    assert len(json.dumps(diagnostic).encode()) <= 8192
    assert diagnostic["chain"][0]["type"] == "_ObservationFailure"
    assert failure.__cause__ is observer.failure
    rejected = [e for e in records if e["kind"] == "MEMORY_STATS_REJECTED"]
    if case == "invalid-cid":
        assert not rejected
        assert any(f[1] == "_digest" for e in diagnostic["chain"] for f in e["frames"])
        return
    assert len(rejected) == 1 and rejected[0]["cid"] == "a" * 64
    assert set(rejected[0]) == {"kind", "at", "cid", "response_received", "stats_type",
                               "sample_started", "stats_rpc_completed_at",
                               "memory_stats_present", "memory_stats_type", "usage_present", "usage_type"}
    assert type(rejected[0]["sample_started"]) is float
    if rejected[0]["response_received"]:
        assert type(rejected[0]["stats_rpc_completed_at"]) is float
        assert rejected[0]["sample_started"] <= rejected[0]["stats_rpc_completed_at"] <= rejected[0]["at"]
    else:
        assert rejected[0]["stats_rpc_completed_at"] is None
    if case == "http503":
        assert any(e["type"] == "_HTTPFailure" and e["status"] == 503 for e in diagnostic["chain"])
        assert rejected[0]["response_received"] is False
    elif case in ("missing-usage", "string-usage"):
        assert rejected[0]["usage_present"] is (case == "string-usage")
        assert rejected[0]["usage_type"] == ("str" if case == "string-usage" else "NoneType")
        assert any(f[1] == "_integer" for e in diagnostic["chain"] for f in e["frames"])
    kinds = [e["kind"] for e in records]
    assert kinds.index("MEMORY_STATS_REJECTED") < kinds.index("OBSERVER_FAILURE")


@pytest.mark.parametrize("kinds", [("MEMORY_STATS_REJECTED",), ("OBSERVER_FAILURE",),
                                  ("MEMORY_STATS_REJECTED", "OBSERVER_FAILURE")])
def test_observer_diagnostic_write_failure_stays_failed(tmp_path, monkeypatch, kinds):
    records, failure, observer = _diagnostic_retirement(tmp_path, monkeypatch, "missing-usage", kinds)
    assert failure.__cause__ is observer.failure, "diagnostic I/O replaced the original observer failure"
    assert isinstance(observer.failure.__cause__, ValueError)
    assert not any(e["kind"] in ("OBSERVER_JOIN_ACK", "DELETE", "CLOSED") for e in records)


@pytest.mark.parametrize("depth", [2, 10, "cycle"])
def test_observer_diagnostic_chain_is_bounded_and_private(tmp_path, monkeypatch, depth):
    import os
    import threading
    import types
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p)
    j["guardians"] = [os.getpid()]; m._save_journal(job, j)
    observer = m._Observer(p, types.SimpleNamespace(active=set()), job)
    entered = threading.Event()
    canary = "PRIVATE_EXCEPTION_TYPE_MESSAGE_FILENAME_FUNCTION_76d3"
    unknown_type = type(canary, (RuntimeError,), {})
    def nested_failure(*args):
        entered.set(); assert observer.stop.wait(1)
        failure = m._HTTPFailure(503)
        for _ in range(2 if depth == "cycle" else depth):
            wrapper = unknown_type(canary * 4096); wrapper.__cause__ = failure; failure = wrapper
        if depth == "cycle":
            failure.__cause__ = failure
        exec(compile(f"def {canary}():\n    raise failure\n{canary}()\n",
                     "/private/" + canary + ".py", "exec"), {"failure": failure})
    monkeypatch.setattr(m, "_memory_sample", nested_failure)
    observer.thread.start()
    try:
        assert entered.wait(1)
        with pytest.raises(m._ObservationFailure):
            observer.retire(deadline=m.time.monotonic() + 1)
        data = (job / "events.jsonl").read_text()
        events = [json.loads(line) for line in data.splitlines()]
        rows = [e for e in events if e["kind"] == "OBSERVER_FAILURE"]
        assert len(rows) == 1, "nested original cause was not durably recorded"
        row = rows[0]
        assert len(json.dumps(row).encode()) <= 8192 and len(row["chain"]) <= 4
        assert row["chain_truncated"] is (depth != 2)
        assert row["chain"][0]["type"] == "other"
        if depth == 2:
            assert row["chain"][-1]["type"] == "_HTTPFailure" and row["chain"][-1]["status"] == 503
        for cause in row["chain"]:
            assert len(cause["frames"]) <= 4
            for file, function, line in cause["frames"]:
                assert file == "ptc/sql_isolation.py" and canary not in function
                assert type(line) is int and line > 0
        assert canary not in data and str(tmp_path) not in json.dumps(row)
        assert not any(e["kind"] in ("OBSERVER_JOIN_ACK", "DELETE", "CLOSED") for e in events)
    finally:
        observer.stop.set(); observer.thread.join(2)
        assert not observer.thread.is_alive()


def test_observer_diagnostic_preserves_original_cleanup_deadline(tmp_path, monkeypatch):
    _diagnostic_retirement(tmp_path, monkeypatch, "deadline")


def _terminal_owned_fixture(tmp_path, monkeypatch, role, fault=None, reverse=False):
    import os
    import threading
    import types
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p, cid="a" * 64)
    j.update(role=role, guardians=[os.getpid()])
    j["config"] = m._container_config(p, role, job, j["nonce"])
    j["config_sha256"] = hashlib.sha256(m.canonical_json_bytes(j["config"])).hexdigest()
    m._save_journal(job, j)
    observer = m._Observer(p, m._Daemon(p), job)
    phase = ["seed"]
    entered, completed, release, caught = (threading.Event() for _ in range(4))
    original_is_alive = observer.thread.is_alive
    original_ordinary = observer._ordinary_failure
    def ordinary(exc):
        converted = original_ordinary(exc)
        caught.set()
        return converted
    observer._ordinary_failure = ordinary
    pool_type = m.concurrent.futures.ThreadPoolExecutor
    class TrackedPool(pool_type):
        def submit(self, function, *args, **kwargs):
            future = super().submit(function, *args, **kwargs)
            if phase[0] == "terminal" and args and "/stats?" in str(args[0]):
                future.add_done_callback(lambda _: completed.set())
            return future
    monkeypatch.setattr(m.concurrent.futures, "ThreadPoolExecutor", TrackedPool)
    def vm_memory(*args):
        if phase[0] == "terminal" and fault != "handled-before-retirement":
            assert observer.stop.wait(1)
            if fault == "vm-error":
                raise m._ObservationFailure("trusted VM failure")
        return 1073741824, 1073741824
    monkeypatch.setattr(m, "_vm_memory", vm_memory)
    parallel = fault in ("other-null", "other-http", "other-json", "two-missing",
                         "other-unlimited", "other-timeout", "other-over-total", "vm-error", "info-error")
    original_call = observer.daemon.call
    def metadata_call(method, path, **kwargs):
        if phase[0] == "terminal" and fault == "other-timeout" and "/b" + "b" * 63 + "/stats?" in path:
            kwargs["timeout"] = 0.12
        return original_call(method, path, **kwargs)
    observer.daemon.call = metadata_call
    def handler(line):
        assert line.startswith("GET ")
        if line.startswith("GET /info "):
            if phase[0] == "terminal" and fault == "info-error":
                assert observer.stop.wait(1)
                return 200, b'{"MemTotal":1}', 0, 0
            return 200, b'{"MemTotal":1073741824}', 0, 0
        if line.startswith("GET /containers/json "):
            ids = ["a" * 64, "b" * 64] if parallel else ["b" * 64 if fault == "foreign-candidate" else "a" * 64]
            if reverse: ids.reverse()
            return 200, m.canonical_json_bytes([{"Id": cid, "State": "running"} for cid in ids]), 0, 0
        cid = line.split("/containers/")[1].split("/")[0]
        if phase[0] == "seed":
            return 200, m.canonical_json_bytes({"id": cid, "memory_stats": {"usage": 1048576}}), 0, 0
        entered.set()
        if fault not in ("completed-before-stop", "handled-before-retirement"):
            assert observer.stop.wait(1)
        if fault == "join-budget":
            release.wait(0.8)
        if cid == "b" * 64 and parallel:
            if fault == "other-http": return 503, b"", 0, 0
            if fault == "other-json": return 200, b"{", 0, 0
            if fault == "other-timeout":
                return 200, m.canonical_json_bytes({"id": cid, "memory_stats": {"usage": 1048576}}), 0.25, 0
            usage = None if fault == "other-null" else -1
            if fault == "other-over-total": usage = 2147483648
            if fault in ("vm-error", "info-error"): usage = 1048576
            body = {"id": cid, "memory_stats": {} if fault == "two-missing" else {"usage": usage}}
        else:
            body = {"id": cid, "memory_stats": {}}
            if fault in ("null", "bool", "string", "negative", "float"):
                body["memory_stats"]["usage"] = {"null": None, "bool": False, "string": "private",
                                                "negative": -1, "float": 0.0}[fault]
            elif fault == "absent-memory": body.pop("memory_stats")
            elif fault == "non-dict-memory": body["memory_stats"] = []
            elif fault == "non-dict-stats": body = []
            elif fault == "response-id": body["id"] = "b" * 64
            elif fault == "response-Id": body["Id"] = "b" * 64
            elif fault == "response-ID": body["ID"] = "b" * 64
            elif fault == "absent-response-id": body.pop("id")
            elif fault == "http": return 503, b"", 0, 0
            elif fault == "json": return 200, b"{", 0, 0
        return 200, m.canonical_json_bytes(body), 0, 0
    server = _LocalHTTP(p.daemon_socket, handler)
    seed = m._memory_sample(p, observer.daemon, job)
    observer.latest = seed; observer.tokens.append(seed)
    phase[0] = "terminal"
    prior = m._ObservationFailure("prior first-latched failure")
    if fault == "prior-failure": observer.failure = prior
    original_event = m._event
    pending_checks = []
    def event(path, kind, **values):
        if (fault == "diagnostic-write" and kind == "MEMORY_STATS_REJECTED" or
                fault == "discard-write" and kind == "MEMORY_TERMINAL_DISCARDED"):
            raise OSError("trusted diagnostic write fault")
        result = original_event(path, kind, **values)
        if kind == "OBSERVER_THREAD_JOINED":
            with pytest.raises(m._ObservationFailure):
                observer.check(admission=True)
            read, write = os.pipe()
            try:
                with pytest.raises(m._ObservationFailure):
                    m._final_start_checks(read, observer, 0.0, j)
            finally:
                os.close(read); os.close(write)
            pending_checks.append(True)
            if fault == "metadata-active": observer.daemon.active.add("owned-fixture-alias")
            if fault == "metadata-worker": observer.daemon.workers.add("owned-fixture-worker")
            if fault == "thread-active": observer.thread.is_alive = lambda: True
            if observer.pending is not None:
                if fault == "sample-old": observer.pending.started = observer.pending.finished - 4.001
                if fault == "sample-four": observer.pending.started = observer.pending.finished - 4.0
                if fault == "span-before": observer.pending.finished = observer.retired_at - 0.001
                if fault == "span-after": observer.pending.started = observer.retired_at + 0.001
                if fault == "rpc-after-finish": observer.pending.stats_rpc_completed_at = observer.pending.finished + 0.001
        return result
    monkeypatch.setattr(m, "_event", event)
    original_retire = observer.retire
    captured = []
    def retire(deadline=None, *, stopped_owned=None):
        captured.append(stopped_owned)
        if stopped_owned is not None:
            changes = {
                "proof-cid": {"cid": "b" * 64}, "proof-job": {"job": job / "foreign"},
                "proof-nonce": {"nonce": "foreign"}, "proof-config": {"config_sha256": "b" * 64},
                "proof-guardian": {"guardian": os.getpid() + 1}, "proof-token": {"observer_token": "b" * 32},
            }.get(fault, {})
            if changes: stopped_owned = dataclasses.replace(stopped_owned, **changes)
            if fault in ("last-four", "last-old", "last-future", "reserve-low"):
                age = {"last-four": 4.0, "last-old": 4.001, "last-future": -0.001}.get(fault, 0.1)
                seed["finished"] = stopped_owned.stopped_at - age
                seed["started"] = seed["finished"] - 0.01
                if fault == "reserve-low": seed["available"] = p.reserve_bytes - 1
            if fault == "no-last": observer.latest = None
            if fault == "ineligible-last": seed["eligible"] = False
            if fault == "no-proof": stopped_owned = None
        if stopped_owned is None:
            return original_retire(deadline=deadline)
        return original_retire(deadline=deadline, stopped_owned=stopped_owned)
    observer.retire = retire
    original_allowed = observer._terminal_discard_allowed
    def allowed(journal, deadline):
        if fault in ("proof-four", "old-proof"):
            now = observer.stopped_owned.stopped_at + (4.0 if fault == "proof-four" else 4.001)
            with monkeypatch.context() as patch:
                patch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: now))
                return original_allowed(journal, deadline)
        return original_allowed(journal, deadline)
    observer._terminal_discard_allowed = allowed
    if fault == "actor-proof":
        monkeypatch.setattr(m, "_prove_actor_absence", lambda *args: (_ for _ in ()).throw(m._Failure("cleanup", "actor proof refused")))
    class Cleanup:
        active = set()
        workers = set()
        removed = False
        def __init__(self): self.calls = []
        def call(self, method, path, *args, **kwargs):
            self.calls.append((method, path))
            if method == "POST":
                assert path.endswith("/kill?signal=SIGKILL")
                raise m._HTTPFailure(409)
            if method == "DELETE":
                self.removed = True
                return None
            if self.removed: raise m._HTTPFailure(404)
            obj = _owned_fixture_object(j)
            obj["State"]["Status"] = "exited"
            if fault in ("running", "paused", "restarting", "pid", "status"):
                key, value = {"running": ("Running", True), "paused": ("Paused", True),
                              "restarting": ("Restarting", True), "pid": ("Pid", 1),
                              "status": ("Status", "unknown")}[fault]
                obj["State"][key] = value
            if fault == "changed-cap": obj["HostConfig"]["Memory"] = 134217728
            if fault == "cleanup-active": self.active.add("owned-cleanup-alias")
            return obj
    daemon = Cleanup()
    observer.thread.start()
    failure = None
    try:
        assert entered.wait(1)
        if fault == "completed-before-stop": assert completed.wait(1)
        if fault == "handled-before-retirement": assert caught.wait(1)
        m._begin_cleanup(j)
        original_budget = (j["cleanup_trigger"], j["cleanup_deadline"])
        if fault == "join-budget":
            j["cleanup_trigger"] = m.time.monotonic() - 11.9
            j["cleanup_deadline"] = j["cleanup_trigger"] + 12.0
            original_budget = (j["cleanup_trigger"], j["cleanup_deadline"])
        if fault == "expired-budget":
            j["cleanup_trigger"] = m.time.monotonic() - 12.001
            j["cleanup_deadline"] = j["cleanup_trigger"] + 12.0
            original_budget = (j["cleanup_trigger"], j["cleanup_deadline"])
        try:
            m._cleanup_owned(p, daemon, j, job, observer)
        except BaseException as exc:
            failure = exc
        assert (j["cleanup_trigger"], j["cleanup_deadline"]) == original_budget
        events = [json.loads(line) for line in (job / "events.jsonl").read_text().splitlines()]
        if fault == "prior-failure": assert observer.failure is prior
        return failure, events, daemon, observer, seed, captured, pending_checks
    finally:
        observer.thread.is_alive = original_is_alive
        release.set(); observer.stop.set(); observer.thread.join(2); server.close()
        observer.daemon.active.clear(); observer.daemon.workers.clear(); daemon.active.clear()
        assert not observer.thread.is_alive()


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [None, "completed-before-stop"])
def test_terminal_rejection_retains_worker_rpc_timing(tmp_path, monkeypatch, role, fault):
    failure, events, *_ = _terminal_owned_fixture(tmp_path, monkeypatch, role, fault)
    rejected = next(e for e in events if e["kind"] == "MEMORY_STATS_REJECTED")
    stopped = next(e for e in events if e["kind"] == "STOPPED")
    assert type(rejected.get("sample_started")) is float
    assert type(rejected.get("stats_rpc_completed_at")) is float
    assert rejected["sample_started"] <= rejected["stats_rpc_completed_at"] <= rejected["at"]
    assert len(json.dumps(rejected).encode()) <= 1024
    if fault == "completed-before-stop":
        assert failure is not None
        assert rejected["stats_rpc_completed_at"] < stopped["stopped_at"]
    else:
        assert failure is None
        assert rejected["stats_rpc_completed_at"] >= stopped["stopped_at"]


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [None, "last-four", "proof-four", "sample-four", "absent-response-id"],
                         ids=["fresh", "last-exact-four", "proof-exact-four", "sample-exact-four", "absent-response-id"])
def test_terminal_owned_positive(tmp_path, monkeypatch, role, fault):
    failure, events, daemon, observer, seed, captured, checks = _terminal_owned_fixture(tmp_path, monkeypatch, role, fault)
    assert failure is None, "strict post-STOPPED terminal observation was not discarded: " + str(failure)
    kinds = [e["kind"] for e in events]
    assert kinds.count("MEMORY_TERMINAL_DISCARDED") == 1
    assert kinds.count("MEMORY_SAMPLE") == 1 and observer.tokens == [seed]
    assert kinds.index("MEMORY_TERMINAL_DISCARDED") < kinds.index("OBSERVER_JOIN_ACK") < kinds.index("DELETE")
    assert daemon.removed and checks and not seed["eligible"]
    assert [method for method, _ in daemon.calls] == ["GET", "POST", "GET", "GET", "DELETE", "GET"]
    assert seed["raw_charges"] == [("a" * 64, 1048576)]
    assert seed["available"] == 1073741824 - 1048576
    discarded = next(e for e in events if e["kind"] == "MEMORY_TERMINAL_DISCARDED")
    assert not any(key in discarded for key in ("available", "raw_charges", "token"))
    assert captured and type(captured[0]) is api()._StoppedOwnedProof
    with pytest.raises(dataclasses.FrozenInstanceError):
        captured[0].cid = "b" * 64


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [
    "null", "bool", "string", "negative", "float", "absent-memory", "non-dict-memory", "non-dict-stats",
    "response-id", "response-Id", "response-ID",
    "http", "json", "foreign-candidate", "proof-cid", "proof-job", "proof-nonce", "proof-config",
    "proof-guardian", "proof-token", "changed-cap", "running", "paused", "restarting", "pid", "status",
    "completed-before-stop", "last-old", "last-future", "old-proof", "reserve-low", "no-last",
    "ineligible-last", "no-proof", "prior-failure", "diagnostic-write", "discard-write",
    "cleanup-active", "metadata-active", "metadata-worker", "thread-active", "actor-proof",
    "join-budget", "expired-budget", "handled-before-retirement",
    "sample-old", "span-before", "span-after", "rpc-after-finish",
])
def test_terminal_owned_strict_refusal(tmp_path, monkeypatch, role, fault):
    failure, events, daemon, observer, *_ = _terminal_owned_fixture(tmp_path, monkeypatch, role, fault)
    assert failure is not None, "terminal proof accepted forbidden " + fault
    assert isinstance(failure, api()._Failure), "unexpected non-protocol test failure"
    assert not daemon.removed
    assert not any(e["kind"] in ("MEMORY_TERMINAL_DISCARDED", "OBSERVER_JOIN_ACK", "DELETE", "CLOSED") for e in events)
    with pytest.raises(api()._ObservationFailure):
        observer.check(admission=True)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("reverse", [False, True], ids=["own-first", "own-last"])
@pytest.mark.parametrize("fault", ["other-null", "other-http", "other-json", "other-unlimited",
                                  "other-timeout", "other-over-total", "two-missing", "vm-error", "info-error"])
def test_terminal_owned_hard_error_priority(tmp_path, monkeypatch, role, reverse, fault):
    failure, events, daemon, *_ = _terminal_owned_fixture(tmp_path, monkeypatch, role, fault, reverse)
    assert failure is not None, "candidate hid a parallel hard error"
    assert isinstance(failure, api()._Failure), "unexpected non-protocol test failure"
    assert not daemon.removed
    assert not any(e["kind"] in ("MEMORY_TERMINAL_DISCARDED", "OBSERVER_JOIN_ACK", "DELETE", "CLOSED") for e in events)


@pytest.mark.parametrize("registered", [False, True])
def test_review_4_emergency_none_is_not_actor_absence(tmp_path, registered):
    import os
    import select
    import subprocess
    import sys
    import time
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p, cid="a" * 64)
    child_read, child_write = os.pipe()
    child_code = f"import os;os.write(1,b'READY\\n');os.read({child_read},1);os.write(1,b'CHILD_DONE\\n')"
    guardian_code = ("import os,sys,subprocess;"
        f"p=subprocess.Popen([sys.executable,'-I','-B','-c',{child_code!r}],pass_fds=({child_read},));"
        f"os.close({child_read});print('PID',p.pid,flush=True);sys.stdin.buffer.read(1)")
    guardian = subprocess.Popen([sys.executable, "-I", "-B", "-c", guardian_code],
                                pass_fds=(child_read,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    os.close(child_read)
    lines = []
    for _ in range(2):
        assert select.select([guardian.stdout], [], [], 2)[0]
        lines.append(guardian.stdout.readline().decode().strip())
    child_pid = int(next(line.split()[1] for line in lines if line.startswith("PID ")))
    assert "READY" in lines
    j["guardians"] = [guardian.pid]
    m._save_journal(job, j)
    token = "unfinished-owned-spawn"
    m._event(job, "CLI_SPAWN_INTENT", token=token, guardian=guardian.pid, binary_sha256="a" * 64)
    if registered:
        m._event(job, "CLI_STARTED", token=token, pid=child_pid, guardian=guardian.pid)
    guardian.kill(); guardian.wait(timeout=1)
    REVIEW_PROCESS_RESULTS.append({"pid": guardian.pid, "proof": "owned Popen.wait", "returncode": guardian.returncode})
    m._event(job, "GUARDIAN_REAPED", pid=guardian.pid, returncode=guardian.returncode)
    class Fixture:
        active = set()
        removed = False
        def call(self, method, path, *args, **kwargs):
            if method == "POST":
                raise m._HTTPFailure(409)
            if method == "DELETE":
                self.removed = True
                return None
            return None if self.removed else _owned_fixture_object(j)
    daemon = Fixture()
    try:
        failure = None
        try:
            m._cleanup_owned(p, daemon, j, job, None)
        except m._Failure as exc:
            failure = exc
        assert failure is not None, "emergency guardian synthesized observer/CLI absence"
        assert daemon.removed is False
        assert not select.select([guardian.stdout], [], [], 0.02)[0], "orphan must remain on its owned control pipe"
        kinds = [json.loads(line)["kind"] for line in (job / "events.jsonl").read_text().splitlines()]
        assert "STOPPED" in kinds and "OBSERVER_JOIN_ACK" not in kinds and "DELETE" not in kinds
    finally:
        os.write(child_write, b"x"); os.close(child_write)
        assert select.select([guardian.stdout], [], [], 2)[0]
        assert guardian.stdout.readline() == b"CHILD_DONE\n"
        guardian.stdout.close(); guardian.stdin.close()
        until = time.monotonic() + 2
        while True:
            try:
                os.kill(child_pid, 0)  # Absence observation only, never a signal/authority decision.
            except ProcessLookupError:
                REVIEW_PROCESS_RESULTS.append({"pid": child_pid, "proof": "owned control-pipe exit ACK plus PID absence"})
                break
            assert time.monotonic() < until, "controlled orphan did not exit/reap"
            time.sleep(0.01)


@pytest.mark.parametrize("fault", ["deadline", "stale", "controller", "observer"])
def test_review_5_stalled_prestart_write_performs_zero_starts(tmp_path, monkeypatch, fault):
    import os
    import types
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p)
    clock = [1000.0]
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    j.update(profile_sha256=m.execution_profile_sha256(p),
             config_sha256=hashlib.sha256(m.canonical_json_bytes(j["config"])).hexdigest(),
             request_sha256="b" * 64, db_sha256="c" * 64, start_attempted=False,
             deadline=1010.0, state="RESERVED")
    m._save_journal(job, j); (job / "profile.json").write_bytes(m.execution_profile_canonical_bytes(p))
    read, write = os.pipe(); os.write(write, b"G")
    starts = []
    shared_observers = []
    class FixtureObserver:
        def __init__(self, *args):
            import threading
            self.lock = threading.Lock(); self.latest = {"started": clock[0]}
            self.failure = None; self.retired = False
            self.thread = types.SimpleNamespace(start=lambda: None)
            self.stop = types.SimpleNamespace(wait=lambda _: None)
            shared_observers.append(self)
        def check(self, **kwargs):
            if self.failure is not None or clock[0] - self.latest["started"] > 4:
                raise m._ObservationFailure("stale/failed fixture observer")
            return True
    class FixtureDaemon:
        active = set()
        def __init__(self, *args): pass
        def call(self, method, path, *args, **kwargs):
            if "/start" in path: starts.append(clock[0])
            return {"Id": "a" * 64}
        def attach(self, cid): return types.SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(m, "_Daemon", FixtureDaemon)
    monkeypatch.setattr(m, "_Observer", FixtureObserver)
    monkeypatch.setattr(m, "build_execution_binding", lambda *a, **k: p.binding)
    monkeypatch.setattr(m, "_activate_staged_import_root", lambda *a: None, raising=False)
    monkeypatch.setattr(m, "_image_preflight", lambda *a: None)
    monkeypatch.setattr(m, "_memory_sample", lambda *a: {"available": p.admission_bytes})
    monkeypatch.setattr(m, "_inspect", lambda d, record: _owned_fixture_object(record))
    def complete_control(*args):
        record = args[2]
        record["bootstrap"] = {"python_version": "3.12.15", "sqlite_version": "fixture"}
        record["bootstrap_sha256"] = "d" * 64
        return m.ProgramResponse("trusted control fixture", False)
    monkeypatch.setattr(m, "_stream_result", complete_control)
    def cleanup(*args):
        args[2]["cleanup_elapsed"] = 0
        if args[-1] is not None: args[-1].retired = True
    monkeypatch.setattr(m, "_cleanup_owned", cleanup)
    monkeypatch.setattr(m, "_close_reservation", lambda *a: None)
    def block(profile, record, path, detail):
        record["state"] = "UNRESOLVED"; m._save_journal(path, record)
    monkeypatch.setattr(m, "_block", block)
    original_event = m._event
    def delayed_event(path, kind, **kwargs):
        nonlocal write
        original_event(path, kind, **kwargs)
        if kind == "START_ATTEMPT":
            if fault == "deadline": clock[0] += 11
            if fault == "stale": clock[0] += 4.001
            if fault == "observer": shared_observers[-1].failure = RuntimeError("fixture")
            if fault == "controller": os.close(write); write = None
    monkeypatch.setattr(m, "_event", delayed_event)
    try:
        with pytest.raises(m._Failure, match="finalization"):
            m._guardian(job, read, False)
        assert starts == [], f"{fault} changed during durable writes but START still executed"
    finally:
        os.close(read)
        if write is not None: os.close(write)


@pytest.mark.parametrize("mode", ["header", "body", "start", "controller", "observer"])
def test_review_6_progressing_rpc_has_absolute_deadline_and_external_watch(tmp_path, mode):
    import os
    import threading
    import time
    m = api(); p = _review_profile(tmp_path)
    body = b"{}" if mode != "body" else b'{"padding":"' + b"x" * 80 + b'"}'
    delay, drip = (0.5, 0) if mode in ("start", "controller", "observer") else (0, -0.01 if mode == "body" else 0.01)
    server = _LocalHTTP(p.daemon_socket, lambda _: (200, body, delay, drip))
    daemon = m._Daemon(p)
    daemon.operation_deadline = time.monotonic() + 0.16
    read, write = os.pipe()
    closer = None
    if mode == "controller":
        daemon.operation_deadline = time.monotonic() + 2
        daemon.control = read
        closer = threading.Thread(target=lambda: (time.sleep(0.06), os.close(write)))
        closer.start()
    if mode == "observer":
        import types
        failed = threading.Event()
        def check():
            if failed.is_set(): raise m._ObservationFailure("controlled observer loss during RPC")
        daemon.observer = types.SimpleNamespace(check=check)
        daemon.operation_deadline = time.monotonic() + 2
        closer = threading.Thread(target=lambda: (time.sleep(0.06), failed.set()))
        closer.start()
    began = time.monotonic()
    failure = None
    try:
        try:
            daemon.call("POST" if mode in ("start", "controller") else "GET", "/start" if mode == "start" else "/fixture")
        except m._Failure as exc:
            failure = exc
        assert failure is not None, "progressing/delayed RPC escaped its absolute supervisor"
        assert time.monotonic() - began < 0.45
        assert not daemon.active
        assert not daemon.workers
        if mode == "body": assert server.body_bytes > 1, "body path was not reached"
    finally:
        if closer is not None: closer.join(1)
        if mode != "controller": os.close(write)
        os.close(read); server.close()


def test_review_6_cleanup_reuses_one_absolute_budget(tmp_path):
    import time
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p, cid="a" * 64)
    original_deadline = time.monotonic() + 0.24
    j["cleanup_deadline"] = original_deadline
    def handler(line):
        if line.startswith("POST"): return 409, b"", 0.07, 0
        if line.startswith("DELETE"): return 204, b"", 0.07, 0
        return 200, m.canonical_json_bytes(_owned_fixture_object(j)), 0.07, 0
    server = _LocalHTTP(p.daemon_socket, handler)
    began = time.monotonic(); failure = None
    try:
        try:
            m._cleanup_owned(p, m._Daemon(p), j, job, None)
        except m._Failure as exc:
            failure = exc
        assert failure is not None, "cleanup reset/ignored the shared absolute budget"
        assert failure.reason == "cleanup", "cumulative cleanup must exhaust its budget, not fail at typed HTTP409"
        assert j["cleanup_deadline"] == original_deadline
        assert time.monotonic() - began < 0.5
        assert not any(line.startswith("DELETE") for line in server.requests)
    finally:
        server.close()


@pytest.mark.parametrize("native_boundary", ["program", "scorer", "sqlite_nomem"])
def test_review_7_swallowed_typed_allocation_is_reserved_memory_exit(tmp_path, monkeypatch, native_boundary):
    m = api()
    from ptc import sql_worker
    from bench import sql_score_worker
    from bench import score
    import ptc.runtime
    import sqlite3
    import sys
    def allocation(*args, **kwargs):
        if native_boundary == "sqlite_nomem":
            exc = sqlite3.OperationalError("controlled fixture, deliberately not an error classifier")
            exc.sqlite_errorcode = sqlite3.SQLITE_NOMEM
            raise exc
        raise MemoryError("controlled tiny first-party exception")
    if native_boundary == "program":
        monkeypatch.setattr(ptc.runtime, "run", allocation)
        request = m.ProgramRequest("pass", 1, "a" * 64)
        monkeypatch.setattr(sql_worker, "_worker_handshake", lambda _: (request, "b" * 64))
        worker = sql_worker
    else:
        class Connection:
            def set_progress_handler(self, *args): pass
            def execute(self, *args): return allocation()
            def close(self): pass
        from bench.task import SqlTask
        db = tmp_path / "fixture"; db.write_bytes(b"not opened as SQLite")
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", str(db), "simple", "derived", "s", "s", "fixture")
        request = m.ScoreRequest(dataclasses.replace(task, db_path="/db.sqlite"), "SELECT 1", 1.0, 1, "set", "a" * 64)
        monkeypatch.setattr(score, "_connect", lambda _: Connection())
        # Native path existence check, no SQL or final result is mocked.
        monkeypatch.setattr(score.Path, "is_file", lambda _: True)
        monkeypatch.setattr(sql_score_worker, "_worker_handshake", lambda _: (request, "b" * 64))
        worker = sql_score_worker
    previous = sys.gettrace()
    emitted = []
    monkeypatch.setattr(worker, "encode_wire_message", lambda *a, **k: emitted.append(a) or b"")
    code = None
    try:
        worker.main()
    except SystemExit as exc:
        code = exc.code
    assert code == 70, f"{native_boundary} allocation was swallowed as native rejection/EX"
    assert emitted == [], "resource failure emitted a model/grade result"
    assert sys.gettrace() is previous


def test_review_6_typed_http409_survives_rpc_and_every_response_closes(tmp_path):
    m = api(); p = _review_profile(tmp_path)
    server = _LocalHTTP(p.daemon_socket, lambda _: (409, b"irrelevant body", 0, 0))
    daemon = m._Daemon(p)
    try:
        failure = None
        try:
            daemon.call("POST", "/fixture")
        except m._Failure as exc:
            failure = exc
        assert type(failure) is m._HTTPFailure and failure.status == 409, "typed HTTP409 lost across absolute RPC wrapper"
        assert not daemon.active and not daemon.workers
    finally:
        server.close()


def test_review_7_deadline_tracer_does_not_hide_allocation_and_zero_division_is_unchanged(tmp_path, monkeypatch):
    m = api()
    import ptc.sql_arms
    from ptc.runtime import Catalog
    def controlled_tool(*args, **kwargs):
        raise MemoryError("trusted tiny exception beneath runtime.run tracer")
    monkeypatch.setattr(ptc.sql_arms, "sql_catalog", lambda *a: Catalog(tools={"print": controlled_tool}))
    with pytest.raises(SystemExit) as allocation:
        m._native_call(ptc.sql_arms.run_ptc_program, "print(1)", str(tmp_path / "unused"))
    assert allocation.value.code == 70
    monkeypatch.undo()
    native = m._native_call(ptc.sql_arms.run_ptc_program, "print('FINAL_SQL: SELECT 1'); 1/0",
                            str(tmp_path / "unused"))
    assert native.rejected is True
    assert native.observation == "error: ZeroDivisionError: division by zero"


@pytest.mark.parametrize("gold,pred", [("SELECT 1", "SELECT 1"), ("SELECT 1", "SELECT 2"),
                                     ("SELECT missing FROM absent", "SELECT 1")])
def test_review_7_tiny_trusted_native_six_field_parity_and_trace_restore(tmp_path, gold, pred):
    import sqlite3
    import sys
    from bench.task import SqlTask
    from bench.score import execution_accuracy
    db = tmp_path / "trusted.sqlite"
    sqlite3.connect(db).close()
    task = SqlTask("trusted", "q", "", gold, "db", str(db), "simple", "derived", "s", "s", "fixture")
    baseline = execution_accuracy(pred, task)
    previous = sys.gettrace()
    def existing_trace(frame, event, arg):
        return existing_trace
    sys.settrace(existing_trace)
    try:
        wrapped = api()._native_call(execution_accuracy, pred, task)
        assert sys.gettrace() is existing_trace
    finally:
        sys.settrace(previous)
    assert dataclasses.asdict(wrapped) == dataclasses.asdict(baseline)


@pytest.mark.parametrize("fault", ["orphan_started", "orphan_join", "duplicate_intent", "foreign_guardian"])
def test_review_4_actor_history_requires_complete_one_to_one_ownership(tmp_path, fault):
    import os
    m = api(); p = _review_profile(tmp_path); job, j = _review_job(tmp_path, p)
    j["guardians"] = [os.getpid()]
    token = "controlled-actor-record"
    if fault not in ("orphan_started", "orphan_join"):
        m._event(job, "CLI_SPAWN_INTENT", token=token, guardian=os.getpid())
    if fault == "duplicate_intent":
        m._event(job, "CLI_SPAWN_INTENT", token=token, guardian=os.getpid())
    if fault != "orphan_join":
        m._event(job, "CLI_STARTED", token=token, guardian=-1 if fault == "foreign_guardian" else os.getpid(), pid=123456)
    m._event(job, "CLI_JOIN_ACK", token=token, guardian=os.getpid(), pid=123456, reaped=True, returncode=0)
    failure = None
    try:
        m._prove_actor_absence(job, j)
    except m._Failure as exc:
        failure = exc
    assert failure is not None, f"{fault} actor history was accepted as positive absence"


def test_review_6_emergency_keeps_original_cleanup_deadline(tmp_path):
    m = api()
    j = {"cleanup_trigger": m.time.monotonic() - 13, "cleanup_deadline": m.time.monotonic() - 1}
    original = dict(j)
    m._begin_cleanup(j)
    assert j == original
    with pytest.raises(m._Failure, match="original absolute cleanup"):
        m._cleanup_remaining(j)


def test_review_6_malformed_completed_rpc_is_typed_uncertain(tmp_path):
    m = api(); p = _review_profile(tmp_path)
    server = _LocalHTTP(p.daemon_socket, lambda _: (200, b"{", 0, 0))
    daemon = m._Daemon(p); failure = None
    try:
        try:
            daemon.call("GET", "/fixture")
        except Exception as exc:
            failure = exc
        assert isinstance(failure, m._RPCUncertain), "malformed RPC escaped durable-UNRESOLVED classification"
        assert failure.reason == "transport"
        assert not daemon.active and not daemon.workers
    finally:
        server.close()


def test_review_6_rpc_join_cannot_add_fresh_time_after_absolute_budget(tmp_path):
    import socket
    import time
    m = api(); p = _review_profile(tmp_path); daemon = m._Daemon(p)
    reader, writer = socket.socketpair()
    reader.settimeout(0.30)  # Even the intentionally disabled guard stays fixture-bounded.
    end = time.monotonic() + 0.16
    daemon.operation_deadline = end
    def controlled_unwind():
        try:
            reader.recv(1)
        finally:
            time.sleep(0.09)  # Controlled worker-unwind latency, no hostile code.
    failure = None
    began = time.monotonic()
    try:
        try:
            daemon._whole_rpc(controlled_unwind, reader, end)
        except m._Failure as exc:
            failure = exc
        assert failure is not None
        assert time.monotonic() - began < 0.20, "RPC join received fresh time beyond its original absolute budget"
    finally:
        reader.close(); writer.close()
        # Fixture owns these exact worker objects. Production must retain the
        # uncertainty rather than claiming a join ACK after its deadline.
        for thread in tuple(daemon.workers):
            thread.join(1)
            assert not thread.is_alive()


@pytest.mark.parametrize("path", ["check", "prestart", "stream"])
def test_review2_1_slow_success_is_fresh_from_finish_in_gap_and_next_sample(tmp_path, monkeypatch, path):
    import os
    import struct
    import types
    m = api(); p = _review_profile(tmp_path); job, journal = _review_job(tmp_path, p, cid="a" * 64)
    clock = [100.0]
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    total = 1073741824
    class Metadata:
        active = set()
        workers = set()
        def call(self, method, url, **kwargs):
            assert method == "GET"
            return {"MemTotal": total} if url == "/info" else []
    def slow_vm(*args):
        clock[0] = 103.9
        return total, total
    monkeypatch.setattr(m, "_vm_memory", slow_vm)
    observer = m._Observer(p, Metadata(), job)
    class OneSample:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, seconds):
            assert seconds == 0.25
            clock[0] += seconds
            self.stopped = True
    observer.stop = OneSample()
    observer._run()  # Actual sampler, publication and 0.25s cadence, simulated clock.
    assert observer.failure is None and len(observer.tokens) == 1
    assert observer.latest["finished"] - observer.latest["started"] == pytest.approx(3.9)
    failure = None
    try:
        observer.check()
    except m._ObservationFailure as exc:
        failure = exc
    assert failure is None, "successful 3.9s sample became stale during the 0.25s sampling gap"
    clock[0] = observer.latest["finished"] + 3.95  # Next legal sample still in flight.
    request = m.ProgramRequest("pass", 1, "b" * 64)
    request_wire = m.encode_wire_message("program", "request", request)
    journal.update(deadline=110.0, db_sha256=request.db_sha256,
                   request_sha256=m.request_sha256(request))
    (job / "request.wire").write_bytes(request_wire)
    read, write = os.pipe()
    try:
        if path == "check":
            assert observer.check(admission=True)
            assert observer.check(after=100.001, admission=True) is False  # Start-based ordering unchanged.
        elif path == "prestart":
            m._final_start_checks(read, observer, 100.0, journal)
        else:
            bootstrap = m.BootstrapPayload(dict(p.environment)["PYTHON_VERSION"], "fixture-not-guest",
                                           p.binding.program.sources, request.db_sha256)
            response = m.ProgramResponse("trusted protocol fixture", False)
            packet = lambda data: b"\x01\0\0\0" + struct.pack(">I", len(data)) + data
            chunks = iter([packet(m.READY + m.encode_wire_message("program", "bootstrap", bootstrap)),
                           packet(m.encode_wire_message("program", "result", response,
                                                        request_sha256=journal["request_sha256"])), b""])
            delivered = []
            attached = types.SimpleNamespace(recv=lambda _: next(chunks), sendall=delivered.append,
                                             settimeout=lambda _: None)
            obj = _owned_fixture_object(journal)
            journal["guardians"] = [os.getpid()]
            journal["config_sha256"] = hashlib.sha256(m.canonical_json_bytes(journal["config"])).hexdigest()
            observer.thread = types.SimpleNamespace(is_alive=lambda: True)  # Simulated-clock sampler only.
            def inspect_state(*args, **kwargs):
                obj["State"].update(Running=len(delivered) < 2, Pid=1 if len(delivered) < 2 else 0,
                                    ExitCode=0, OOMKilled=False)
                return obj
            daemon = types.SimpleNamespace(call=inspect_state)
            assert m._stream_result(p, daemon, journal, job, read, observer, attached) == response
            assert delivered[0] == request_wire and len(delivered) == 2
            grant = m.decode_wire_message(delivered[1], role="program", kind="exit_grant",
                                          request_sha256=journal["request_sha256"])
            assert grant.payload.result_sha256 == hashlib.sha256(
                m.encode_wire_message("program", "result", response,
                                      request_sha256=journal["request_sha256"])).hexdigest()
    finally:
        os.close(read); os.close(write)
    kinds = [json.loads(line)["kind"] for line in (job / "events.jsonl").read_text().splitlines()]
    assert "UNRESOLVED" not in kinds
    assert not list(tmp_path.rglob("UNRESOLVED-*"))


@pytest.mark.parametrize("frame", ["missing", "ineligible", "old_finished", "exact_four_seconds"])
def test_review2_1_finished_age_still_refuses_missing_ineligible_and_old(tmp_path, monkeypatch, frame):
    import types
    m = api(); p = _review_profile(tmp_path); job, _ = _review_job(tmp_path, p)
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: 104.0))
    observer = m._Observer(p, types.SimpleNamespace(active=set(), workers=set()), job)
    if frame != "missing":
        observer.latest = {"started": 96.1, "finished": 100.0, "eligible": frame != "ineligible",
                           "available": p.admission_bytes}
        if frame == "old_finished": observer.latest["finished"] -= 0.001
    if frame == "exact_four_seconds":
        assert observer.check(admission=True) is True
    else:
        with pytest.raises(m._ObservationFailure):
            observer.check(admission=True)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("state", ["CLOSED", "UNRESOLVED"])
def test_review2_2_durable_outcome_survives_slow_guardian_reap(tmp_path, monkeypatch, role, state):
    import subprocess
    import sys
    import types
    from bench.score import ExResult
    from bench.task import SqlTask
    m = api()
    shared = tmp_path / "private-dispatch"; shared.mkdir()
    monkeypatch.setattr(m, "shared_state_dir_for", lambda _: shared)
    p = private_profile = _review_profile(tmp_path)
    monkeypatch.setattr(m, "build_execution_binding", lambda *a, **k: p.binding)
    monkeypatch.setattr(m, "_stage_sources", lambda *a: None)
    monkeypatch.setattr(m, "_stage_database", lambda *a: None)
    if role == "program":
        request = m.ProgramRequest("pass", 1, "a" * 64)
    else:
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", "/db.sqlite",
                       "simple", "derived", "s", "s", "fixture")
        request = m.ScoreRequest(task, "SELECT 1", 1.0, 1, "set", "a" * 64)
    receipt = m.RuntimeReceipt(role, m.request_sha256(request), "fixture-not-guest", "fixture-not-SQLite",
                               "b" * 64, "c" * 64)
    # Controlled typed protocol data, not a guest/native grading claim.
    if role == "program":
        expected = (m.ProgramOutcome("durable native-shaped fixture", None, receipt, rejected=True)
                    if state == "CLOSED" else m.ProgramOutcome(None, m.AbortInfo(role, "transport"), receipt))
    else:
        expected = (m.ScoreOutcome(ExResult(1.0, "match", True, "", 1, 1), None, receipt)
                    if state == "CLOSED" else m.ScoreOutcome(None, m.AbortInfo(role, "transport"), receipt))
    outcome_wire = m.canonical_json_bytes(expected) + b"\n"
    children = []
    real_popen = subprocess.Popen
    class OwnedProcess(real_popen):
        def __init__(self, *args, **kwargs):
            self.waits, self.timeouts, self.kills = [], 0, 0
            super().__init__(*args, **kwargs)
        def wait(self, timeout=None):
            self.waits.append(timeout)
            try:
                return super().wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.timeouts += 1
                raise
        def kill(self):
            self.kills += 1
            return super().kill()
    # Preserve node IDs, update superseded absence-only fixture to real terminal
    # transaction. UNRESOLVED artifacts are now explicitly uncommittable.
    code = r'''
import os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[6])
import ptc.sql_isolation as m
job, fd, state, shared = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[4], Path(sys.argv[5])
m.shared_state_dir_for = lambda _: shared
os.write(1, b"ACK\n")
assert os.read(fd, 1) == b"G"
p = m.execution_profile_from_bytes(m._read_owned(job / "profile.json"))
j = m._metadata(m._read_owned(job / "journal.json"))
j.update(state=state, guardians=[os.getpid()], bootstrap={
    "python_version":"fixture-not-guest", "sqlite_version":"fixture-not-SQLite"}, bootstrap_sha256="b"*64)
m._begin_cleanup(j)
jraw = m.canonical_json_bytes(j) + b"\n"
o = m._metadata(sys.argv[3].encode())
o["receipt"]["journal_sha256"] = m.hashlib.sha256(jraw).hexdigest()
oraw = m.canonical_json_bytes(o) + b"\n"
if state == "UNRESOLVED":
    m._write_owned(job / "journal.json", jraw)
    m._write_owned(job / "outcome.json", oraw)
    os._exit(0)
ack = m._publish_finalization(p, j, job, jraw, oraw, fd)
m._send_terminal_ack(sys.stdout.buffer, ack)
time.sleep(30)
'''
    def spawn(command, **kwargs):
        child = OwnedProcess([sys.executable, "-I", "-B", "-c", code,
                              command[5], command[6], outcome_wire.decode(), state, str(shared),
                              str(m.installed_source_root())], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(m, "subprocess", types.SimpleNamespace(
        Popen=spawn, DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    executor = types.SimpleNamespace(profile=private_profile, state_dir=tmp_path / "dispatch")
    error = result = None
    before_cleanup = None
    try:
        try:
            result = m._run_isolated(executor, role, request, tmp_path / "never-staged.sqlite")
        except Exception as exc:
            error = exc
        assert len(children) == 1
        child = children[0]
        before_cleanup = {"waits": list(child.waits), "timeouts": child.timeouts,
                          "kills": child.kills, "returncode": child.returncode}
    finally:
        for child in children:
            if child.poll() is None: child.kill()
            child.wait(timeout=2)
            if child.stdout is not None: child.stdout.close()
            REVIEW_PROCESS_RESULTS.append({"pid": child.pid, "proof": "owned Popen.wait",
                                           "returncode": child.returncode, "dispatch": before_cleanup})
    assert error is None, f"raw CLOSED reap exception discarded durable outcome: {type(error).__name__}"
    if state == "CLOSED":
        records = [json.loads(path.read_bytes()) for path in executor.state_dir.glob("*/journal.json")]
        actual_receipt = dataclasses.replace(receipt, journal_sha256=hashlib.sha256(
            m.canonical_json_bytes(records[0]) + b"\n").hexdigest())
        assert result == dataclasses.replace(expected, receipt=actual_receipt)
        assert before_cleanup["timeouts"] == 1 and before_cleanup["waits"][0] == 2
        assert before_cleanup["kills"] == 1 and before_cleanup["returncode"] == -9
        assert len(before_cleanup["waits"]) == 2, "dispatch did not reap its exact killed Popen"
        assert not (shared / "active.json").exists()
    else:
        assert result.abort is not None and result.receipt is None, "adopted uncertain abort artifact"
        assert before_cleanup == {"waits": [], "timeouts": 0, "kills": 0, "returncode": 0}
        assert (shared / "active.json").exists()
    records = [json.loads(path.read_bytes()) for path in executor.state_dir.glob("*/journal.json")]
    assert len(records) == 1 and records[0]["state"] == state
    blocks = [path.name for path in shared.glob("UNRESOLVED-*")]
    if state == "CLOSED":
        assert not blocks, "post-ACK hygiene reap manufactured an admission block"
    else:
        assert blocks == ["UNRESOLVED-" + records[0]["nonce"] + ".json"]


# Coordinated shutdown tests are source-first, daemon-free protocol checks.
@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", [None, "role", "request", "result", "version", "extra",
                                  "missing", "duplicate", "utf8", "json", "oversize", "eof"])
def test_shutdown_b01_real_pipe_workers_hold_until_exact_grant(tmp_path, role, fault):
    import select
    import subprocess
    import sys
    import time
    m = api()
    # Exercise each real worker main and shared hold over owned OS pipes.
    # Native computation is tiny trusted fixture data, not a kernel claim.
    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from ptc import sql_isolation as m;"
        "from types import SimpleNamespace;"
        "from " + ("ptc import sql_worker" if role == "program" else "bench import sql_score_worker") + " as w;"
        + ("r=m.ProgramRequest('pass',1,'a'*64);"
           if role == "program" else
           "from bench.task import SqlTask;"
           "t=SqlTask('fixture','q','','SELECT 1','db','/db.sqlite','simple','derived','s','s','fixture');"
           "r=m.ScoreRequest(t,'SELECT 1',1.0,1,'set','a'*64);")
        + "w._worker_handshake=lambda role:(r,m.request_sha256(r));"
        + ("w._native_call=lambda *a,**k:SimpleNamespace(observation='unchanged',rejected=False);"
           if role == "program" else
           "from bench.score import ExResult;w._native_call=lambda *a,**k:ExResult(1.0,'match',True,'',1,1);")
        + "w.main()"
    )
    child = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(m.installed_source_root())],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert select.select([child.stdout], [], [], 3)[0], "worker emitted no provisional result"
        result = child.stdout.readline()
        assert result.endswith(b"\n") and json.loads(result)["schema_version"] == 2
        time.sleep(0.25)
        assert child.poll() is None, "worker exited before controller grant"
        grant = m.encode_wire_message(role, "exit_grant",
            m.ExitGrant(hashlib.sha256(result).hexdigest()),
            request_sha256=json.loads(result)["request_sha256"])
        if fault == "eof":
            grant = b""
        elif fault in ("utf8", "json", "oversize", "duplicate"):
            grant = {"utf8": b"\xff\n", "json": b"{\n",
                     "oversize": b"x" * (m.MAX_ARTIFACT_BYTES + 1) + b"\n",
                     "duplicate": grant[:-2] + b',"role":"program"}\n'}[fault]
        elif fault is not None:
            bad = json.loads(grant)
            if fault == "role": bad["role"] = "scorer" if role == "program" else "program"
            if fault == "request": bad["request_sha256"] = "b" * 64
            if fault == "result":
                bad["payload"]["result_sha256"] = "b" * 64
                bad["sha256"] = hashlib.sha256(m.canonical_json_bytes(bad["payload"])).hexdigest()
            if fault == "version": bad["schema_version"] = 1
            if fault == "extra": bad["payload"]["extra"] = 1
            if fault == "missing": del bad["payload"]["result_sha256"]
            grant = m.canonical_json_bytes(bad) + b"\n"
        began = time.monotonic()
        extra, errors = child.communicate(grant, timeout=1)
        assert time.monotonic() - began < 1
        assert not extra, "worker emitted extra stdout after provisional result"
        assert (child.returncode == 0) is (fault is None), (child.returncode, errors[-1000:])
    finally:
        if child.poll() is None: child.kill()
        child.wait(timeout=1)
        for pipe in (child.stdin, child.stdout, child.stderr):
            if pipe is not None: pipe.close()
        REVIEW_PROCESS_RESULTS.append({"pid": child.pid, "proof": "owned Popen.wait",
                                       "returncode": child.returncode})


@pytest.mark.parametrize("age,reserve,accept", [(4.0, 201326592, True),
    (4.001, 201326592, False), (4.0, 201326591, False)])
def test_shutdown_b06_parked_original_frame_bounds(tmp_path, monkeypatch, age, reserve, accept):
    import types
    m = api(); p = _review_profile(tmp_path); job, _ = _review_job(tmp_path, p)
    observer = m._Observer(p, types.SimpleNamespace(active=set(), workers=set()), job)
    observer.state = "PARKED"
    original = {"started": 99.0, "finished": 100.0, "available": reserve, "eligible": True}
    observer.latest = original
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: 100.0 + age))
    with pytest.raises(m._ObservationFailure):
        observer.check()
    if accept:
        assert observer.shutdown_check() is original
    else:
        with pytest.raises(m._Failure): observer.shutdown_check()
    assert original == {"started": 99.0, "finished": 100.0, "available": reserve, "eligible": True}


@pytest.mark.parametrize("failure", [False, True])
def test_shutdown_b04_reserved_sample_drains_and_first_failure_latches(tmp_path, monkeypatch, failure):
    import threading
    import types
    m = api(); p = _review_profile(tmp_path); job, _ = _review_job(tmp_path, p)
    observer = m._Observer(p, types.SimpleNamespace(active=set(), workers=set()), job)
    entered, release = threading.Event(), threading.Event()
    calls = []
    first = m._ObservationFailure("first genuine fixture failure")
    cadence, advance, checked = threading.Event(), threading.Event(), threading.Event()
    cadence_count = [0]
    def sample(*args):
        calls.append(1); entered.set()
        assert release.wait(1)
        if failure: raise first
        now = m.time.monotonic()
        return {"started": now, "finished": now, "available": p.admission_bytes, "eligible": True}
    monkeypatch.setattr(m, "_memory_sample", sample)
    real_wait = observer.stop.wait
    def cadence_wait(seconds):
        if threading.current_thread() is observer.thread and seconds == 0.25:
            cadence_count[0] += 1
            if cadence_count[0] == 1:
                cadence.set()
                advance.wait(2)
            else:
                checked.set()
                return real_wait(0.01)
            return real_wait(0)
        return real_wait(seconds)
    monkeypatch.setattr(observer.stop, "wait", cadence_wait)
    observer.thread.start()
    try:
        assert entered.wait(1)
        observer.begin_quiesce()
        assert observer.state == "QUIESCING" and observer.inflight is True
        release.set()
        if failure:
            with pytest.raises(m._ObservationFailure):
                observer.park(deadline=m.time.monotonic() + 1)
            assert observer.failure is first
            with pytest.raises(m._Failure): observer.shutdown_check()
        else:
            observer.park(deadline=m.time.monotonic() + 1)
            assert observer.state == "PARKED" and observer.inflight is False
            assert observer.shutdown_check() is observer.latest
        assert observer.thread.is_alive(), "parking retired observer before STOPPED"
        assert cadence.wait(1), "initial sample never reached cadence barrier"
        advance.set()
        assert checked.wait(1), "observer never checked the closed scheduling gate"
        assert len(calls) == 1, "closed scheduling gate admitted a sample"
    finally:
        release.set(); advance.set(); observer.stop.set(); observer.thread.join(2)
        assert not observer.thread.is_alive()


def _shutdown_race_fixture(tmp_path, monkeypatch, role, schedule, fault=None, *, complete=False, expiry=None):
    import os
    import struct
    import threading
    import types
    from bench.score import ExResult
    from bench.task import SqlTask
    m = api()
    clock = [100.0]
    if expiry is not None:
        monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    if complete:
        shared = tmp_path / "private-shared"; shared.mkdir()
        monkeypatch.setattr(m, "shared_state_dir_for", lambda _: shared)
    p = _review_profile(tmp_path)
    job, journal = _review_job(tmp_path, p, cid="a" * 64)
    journal.update(role=role, guardians=[os.getpid()])
    journal["config"] = m._container_config(p, role, job, journal["nonce"])
    journal["config_sha256"] = hashlib.sha256(m.canonical_json_bytes(journal["config"])).hexdigest()
    if role == "program":
        request, response = m.ProgramRequest("pass", 1, "b" * 64), m.ProgramResponse("unchanged", False)
    else:
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", "/db.sqlite",
                       "simple", "derived", "s", "s", "fixture")
        request = m.ScoreRequest(task, "SELECT 1", 1.0, 1, "set", "b" * 64)
        response = ExResult(1.0, "match", True, "", 1, 1)
    sha = m.request_sha256(request)
    journal.update(request_sha256=sha, db_sha256=request.db_sha256)
    if complete:
        profile_raw = m.execution_profile_canonical_bytes(p)
        journal.update(profile_sha256=hashlib.sha256(profile_raw).hexdigest(), controller=os.getpid())
        m._write_owned(job / "profile.json", profile_raw)
    wire = m.encode_wire_message(role, "result", response, request_sha256=sha)
    request_wire = m.encode_wire_message(role, "request", request)
    (job / "request.wire").write_bytes(request_wire)
    m._save_journal(job, journal)
    if complete:
        journal["state"] = "RESERVED"
        m._save_journal(job, journal)
        m._write_owned(p.shared_state_dir / "active.json",
                       m.canonical_json_bytes({"nonce": journal["nonce"], "job": str(job)}) + b"\n")
    def expire(phase):
        if expiry is not None and expiry[1] == phase:
            clock[0] = journal["deadline" if expiry[0] == "role" else "cleanup_deadline"]
    entered, release, published = threading.Event(), threading.Event(), threading.Event()
    running, deleted, missing = [True], [False], []
    stats, delivered, timeline = [], [], []
    metadata_lock = threading.Lock()
    class Metadata:
        def __init__(self):
            self.active, self.workers = set(), set()
        def call(self, method, path, **kwargs):
            assert method == "GET"
            if path == "/info":
                if fault == "info": raise m._ObservationFailure("genuine info error")
                return {"MemTotal": 1073741824}
            if path == "/containers/json":
                if schedule == "before-inventory":
                    entered.set(); assert release.wait(2)
                return [{"Id": journal["cid"], "State": "running"}]
            assert "/stats?" in path
            if schedule == "between-inventory-stats":
                entered.set(); assert release.wait(2)
            alias = object()
            with metadata_lock: self.active.add(alias)
            stats.append("start"); timeline.append("stats-start")
            try:
                if schedule == "during-stats":
                    entered.set(); assert release.wait(2)
                if fault == "stats": raise m._ObservationFailure("genuine stats error")
                if fault == "validation": return {"memory_stats": {"usage": True}}
                if fault == "missing" or not running[0]:
                    missing.append(1)
                    return {"memory_stats": {}}
                return {"memory_stats": {"usage": 1048576}}
            finally:
                timeline.append("stats-finish"); stats.append("finish")
                with metadata_lock:
                    if fault != "http-unwind": self.active.remove(alias)
    metadata = Metadata()
    def vm(*args):
        if fault == "vm": raise m._ObservationFailure("genuine VM error")
        if fault == "cli-unwind": raise m._ObservationFailure("controlled CLI finalizer failure")
        return 1073741824, 1073741824
    monkeypatch.setattr(m, "_vm_memory", vm)
    if fault == "pool-unwind":
        real_pool = m.concurrent.futures.ThreadPoolExecutor
        def pool(*args, **kwargs):
            instance = real_pool(*args, **kwargs)
            shutdown = instance.shutdown
            def unwind(*args, **kwargs):
                shutdown(*args, **kwargs)
                raise m._ObservationFailure("controlled pool finalizer failure after real join")
            instance.shutdown = unwind
            return instance
        monkeypatch.setattr(m.concurrent.futures, "ThreadPoolExecutor", pool)
    original_event = m._event
    parked = [False]
    original_save, original_write = m._save_journal, m._write_owned
    def save(path, record):
        if parked[0] and fault in ("persistent-journal", "persistent-store"):
            timeline.append("JOURNAL_WRITE_REFUSED")
            raise OSError("persistent fixture ENOSPC")
        return original_save(path, record)
    def write_owned(path, data, **kwargs):
        if parked[0] and fault == "persistent-store":
            raise OSError("persistent fixture ENOSPC")
        value = original_write(path, data, **kwargs)
        if path.name == "outcome.json": expire("outcome")
        return value
    monkeypatch.setattr(m, "_save_journal", save)
    monkeypatch.setattr(m, "_write_owned", write_owned)
    original_append = m._append_owned
    def append_owned(path, value):
        result = original_append(path, value)
        if path.name == "history.jsonl": expire("reservation")
        return result
    monkeypatch.setattr(m, "_append_owned", append_owned)
    def event(path, kind, **values):
        original_event(path, kind, **values)
        timeline.append(kind)
        if kind == "OBSERVER_QUIESCING":
            assert not delivered[1:], "grant preceded scheduling gate closure"
        if kind == "MEMORY_SAMPLE": published.set()
        if kind == "OBSERVER_PARKED": parked[0] = True
        if kind == "OBSERVER_RETIRED": expire("retirement")
    monkeypatch.setattr(m, "_event", event)
    observer = m._Observer(p, metadata, job)
    now = m.time.monotonic()
    seed = {"started": now, "finished": now, "available": p.admission_bytes, "eligible": True}
    observer.latest = seed
    real_wait, coordinator = observer.stop.wait, threading.current_thread()
    def drain_wait(seconds):
        # Only an actual drain wait releases reserved metadata work. Removing
        # drain must deterministically fail, not win a scheduler timing race.
        if (threading.current_thread() is coordinator and observer.state == "QUIESCING"
                and seconds <= 0.01):
            release.set()
        return real_wait(seconds)
    monkeypatch.setattr(observer.stop, "wait", drain_wait)
    class ControlDaemon:
        active = set()
        workers = set()
        shutdown_supervision = None
        def call(self, method, path, **kwargs):
            if self.shutdown_supervision is not None: self.shutdown_supervision()
            if method == "POST":
                assert path.endswith("/kill?signal=SIGKILL")
                running[0] = False
                return None
            if method == "DELETE":
                assert "OBSERVER_JOIN_ACK" in timeline
                assert not observer.thread.is_alive()
                deleted[0] = True
                expire("delete")
                return None
            assert method == "GET" and path.endswith("/json")
            if deleted[0]:
                expire("absence")
                raise m._HTTPFailure(404)
            if not running[0]: expire("stopped-inspect")
            obj = _owned_fixture_object(journal)
            obj["State"].update(Running=running[0], Pid=1 if running[0] else 0,
                                Status="running" if running[0] else "exited", ExitCode=0, OOMKilled=False)
            if fault == "foreign-cid": obj["Id"] = "c" * 64
            if fault == "changed-config": obj["HostConfig"]["Memory"] += 1
            if fault == "early-exit" and running[0]:
                obj["State"].update(Running=False, Pid=0, Status="exited")
            if not running[0]:
                if fault == "nonzero": obj["State"]["ExitCode"] = 1
                if fault == "oom": obj["State"]["OOMKilled"] = True
            return obj
    daemon = ControlDaemon()
    bootstrap = m.BootstrapPayload(dict(p.environment)["PYTHON_VERSION"], "fixture-not-guest",
                                   getattr(p.binding, role).sources, request.db_sha256)
    packet = lambda data: b"\x01\0\0\0" + struct.pack(">I", len(data)) + data
    result_wire = wire
    if fault == "bad-result":
        bad = json.loads(wire); bad["request_sha256"] = "f" * 64
        result_wire = m.canonical_json_bytes(bad) + b"\n"
    frames = [packet(m.READY + m.encode_wire_message(role, "bootstrap", bootstrap)), packet(result_wire)]
    if fault == "extra-stdout": frames.append(packet(b"unsolicited\n"))
    if fault == "malformed-mux": frames.append(b"\x03\0\0\0\0\0\0\x01x")
    chunks = iter(frames + [b""])
    class Attach:
        def recv(self, _):
            chunk = next(chunks)
            if not chunk:
                assert len(delivered) == 2, "guest exited without grant"
                expire("eof")
            return chunk
        def close(self):
            timeline.append("ATTACH_CLOSED")
        def settimeout(self, _): pass
        def sendall(self, data):
            delivered.append(data)
            if len(delivered) == 1:
                assert data == request_wire
                return
            assert len(delivered) == 2, "grant retried"
            grant = m.decode_wire_message(data, role=role, kind="exit_grant", request_sha256=sha)
            assert grant.payload.result_sha256 == hashlib.sha256(wire).hexdigest()
            assert observer.state == "PARKED" and not observer.inflight
            assert observer.thread.is_alive()
            assert not metadata.active and not metadata.workers
            assert stats == ["start", "finish"]
            timeline.append("grant")
            running[0] = False
            expire("grant")
            if fault == "uncertain-grant":
                raise OSError("controlled partial send uncertainty")
    read, write = os.pipe()
    daemon.control = read
    observer.thread.start()
    error = None
    attached = Attach()
    try:
        if schedule == "after-publication":
            assert published.wait(2)
            publication_end = m.time.monotonic() + 1
            while True:
                with observer.lock:
                    if observer.latest is not seed: break
                assert m.time.monotonic() < publication_end, "sample never published"
                observer.stop.wait(0.001)
        else:
            assert entered.wait(2)
        try:
            result = m._stream_result(p, daemon, journal, job, read, observer, attached)
            assert result == response
            if complete:
                m._complete_guardian(p, daemon, journal, job, observer, attached, None, False, result)
            else:
                m._cleanup_owned(p, daemon, journal, job, observer)
        except (m._Failure, OSError) as exc:
            error = exc
            if complete:
                failure = exc if isinstance(exc, m._Failure) else m._Failure("transport", type(exc).__name__)
                daemon.shutdown_supervision = None
                journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
                m._complete_guardian(p, daemon, journal, job, observer, attached, failure, True, None)
            elif fault in ("missing", "stats", "info", "vm", "validation"):
                daemon.shutdown_supervision = None
                release.set()
                try:
                    m._cleanup_owned(p, daemon, journal, job, observer)
                except m._Failure:
                    assert observer.failure is not None
                else:
                    raise AssertionError("genuine observer failure allowed successful cleanup")
        return error, timeline, delivered, missing, observer, journal
    finally:
        release.set(); observer.stop.set(); observer.thread.join(3)
        metadata.active.clear()  # Owned synthetic alias, only after all assertions/joins.
        os.close(read); os.close(write)
        assert not observer.thread.is_alive()


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("schedule", ["before-inventory", "between-inventory-stats",
                                     "during-stats", "after-publication"])
def test_shutdown_b03_eight_result_sample_schedules(tmp_path, monkeypatch, role, schedule):
    error, timeline, delivered, missing, observer, journal = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, schedule)
    assert error is None, str(error)
    assert len(delivered) == 2 and missing == []
    assert timeline.index("stats-finish") < timeline.index("grant") < timeline.index("STOPPED")
    assert timeline.index("OBSERVER_PARKED") < timeline.index("grant")
    assert timeline.index("STOPPED") < timeline.index("OBSERVER_RETIRED")
    assert timeline.index("ACTOR_ABSENCE_PROOF") < timeline.index("OBSERVER_JOIN_ACK")
    assert timeline.index("OBSERVER_JOIN_ACK") < timeline.index("DELETE") < timeline.index("ABSENCE")
    assert timeline.count("MEMORY_SAMPLE") == 1 and "MEMORY_TERMINAL_DISCARDED" not in timeline
    assert journal["cleanup_deadline"] == journal["cleanup_trigger"] + 12.0
    assert observer.state == "RETIRED"


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["missing", "stats", "info", "vm", "validation"])
def test_shutdown_b05_genuine_drain_errors_never_grant(tmp_path, monkeypatch, role, fault):
    error, timeline, delivered, missing, observer, _ = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, "during-stats", fault)
    assert error is not None and observer.failure is not None
    assert len(delivered) <= 1
    assert not any(k in timeline for k in ("grant", "OBSERVER_JOIN_ACK", "DELETE", "CLOSED"))


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["foreign-cid", "changed-config", "early-exit", "nonzero", "oom",
                                  "bad-result", "extra-stdout", "malformed-mux", "uncertain-grant"])
def test_shutdown_b07_integrity_and_uncertain_send_never_succeed(tmp_path, monkeypatch, role, fault):
    error, timeline, delivered, _, _, _ = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, "during-stats", fault)
    assert error is not None
    assert len(delivered) <= 2, "uncertain grant was retried"
    assert not any(k in timeline for k in ("OBSERVER_JOIN_ACK", "DELETE", "CLOSED"))
    if fault in ("foreign-cid", "changed-config", "early-exit", "bad-result"):
        assert len(delivered) <= 1, "invalid ownership/result received a grant"
    if fault == "uncertain-grant":
        assert isinstance(error, api()._RPCUncertain)
        assert timeline.count("grant") == 1 and "EXIT_GRANT_SENT" not in timeline


@pytest.mark.parametrize("fault", ["controller", "role-deadline", "freshness", "cleanup-deadline"])
def test_shutdown_b06_cleanup_mode_keeps_explicit_supervision(tmp_path, monkeypatch, fault):
    import os
    import types
    m = api(); p = _review_profile(tmp_path); job, journal = _review_job(tmp_path, p)
    clock = [104.001 if fault == "freshness" else 100.0]
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    observer = m._Observer(p, types.SimpleNamespace(active=set(), workers=set()), job)
    observer.state = "PARKED"
    observer.latest = {"started": 99.0, "finished": 100.0, "available": p.reserve_bytes, "eligible": True}
    observer.thread = types.SimpleNamespace(is_alive=lambda: True)
    journal.update(deadline=100.0 if fault == "role-deadline" else 120.0,
                   cleanup_deadline=100.0 if fault == "cleanup-deadline" else 112.0)
    read, write = os.pipe()
    if fault == "controller":
        os.close(write); write = None
    daemon = m._Daemon(p)
    daemon.cleanup_deadline = journal["cleanup_deadline"]
    daemon.operation_deadline = journal["deadline"]
    daemon.shutdown_supervision = lambda: m._shutdown_check(read, observer, journal)
    try:
        with pytest.raises(m._Failure):
            daemon._supervise(130.0)  # Operation still live; independent shutdown bounds must win.
    finally:
        os.close(read)
        if write is not None: os.close(write)


def test_shutdown_b07_unknown_actor_absence_refuses_ack(tmp_path, monkeypatch):
    import types
    m = api(); p = _review_profile(tmp_path); job, journal = _review_job(tmp_path, p)
    journal["actors_initialized"] = False
    m._save_journal(job, journal)
    observer = m._Observer(p, types.SimpleNamespace(active=set(), workers=set()), job)
    # No native work or daemon calls. This is a real owned observer thread.
    observer.state = "QUIESCING"
    now = m.time.monotonic()
    observer.latest = {"started": now, "finished": now, "available": p.reserve_bytes, "eligible": True}
    observer.thread.start()
    try:
        observer.park(deadline=m.time.monotonic() + 1)
        with pytest.raises(m._Failure):
            observer.retire(deadline=m.time.monotonic() + 1)
        kinds = [json.loads(line)["kind"] for line in (job / "events.jsonl").read_text().splitlines()]
        assert not any(k in kinds for k in ("OBSERVER_JOIN_ACK", "DELETE", "CLOSED"))
    finally:
        observer.stop.set(); observer.thread.join(2)
        assert not observer.thread.is_alive()


@pytest.mark.parametrize("guard", ["hold", "scheduling", "drain", "latch", "binding",
                                  "freshness", "deadline", "absence"])
def test_shutdown_b08_sensitivity_controls(tmp_path, monkeypatch, guard):
    """Each bypass must fail an ordinary protocol assertion, never import/collection."""
    import subprocess
    import textwrap
    m = api()
    def replace_method(cls, name, old, new):
        source = textwrap.dedent(inspect.getsource(getattr(cls, name)))
        assert source.count(old) == 1, "mutation anchor changed"
        namespace = {}
        exec(source.replace(old, new), vars(m), namespace)
        monkeypatch.setattr(cls, name, namespace[name])
    baseline = tmp_path / "baseline"; baseline.mkdir()
    mutant = tmp_path / "mutant"; mutant.mkdir()
    def run(check, directory, *args):
        # Baseline fixture hooks/clock must not contaminate the mutant.
        with monkeypatch.context() as local:
            return check(directory, local, *args)
    if guard in ("hold", "binding"):
        fault = None if guard == "hold" else "result"
        test_shutdown_b01_real_pipe_workers_hold_until_exact_grant(baseline, "program", fault)
        real_popen = subprocess.Popen
        def spawn(command, **kwargs):
            command = list(command)
            if guard == "hold":
                injection = "w._worker_wait_for_exit_grant=lambda *a,**k:None;w.main()"
            else:
                injection = (
                    "import inspect,textwrap;"
                    "s=textwrap.dedent(inspect.getsource(m._worker_wait_for_exit_grant));"
                    "s=s.replace('if grant.payload.result_sha256 != hashlib.sha256(result).hexdigest():','if False:');"
                    "exec(s,m.__dict__);w._worker_wait_for_exit_grant=m._worker_wait_for_exit_grant;w.main()")
            assert command[4].count("w.main()") == 1
            command[4] = command[4].replace("w.main()", injection)
            return real_popen(command, **kwargs)
        monkeypatch.setattr(subprocess, "Popen", spawn)
        with pytest.raises(AssertionError):
            test_shutdown_b01_real_pipe_workers_hold_until_exact_grant(mutant, "program", fault)
    elif guard == "scheduling":
        run(test_shutdown_b04_reserved_sample_drains_and_first_failure_latches, baseline, False)
        replace_method(m._Observer, "_run", 'self.state == "ACTIVE"', 'self.state != "RETIRED"')
        with pytest.raises(AssertionError, match="closed scheduling gate"):
            run(test_shutdown_b04_reserved_sample_drains_and_first_failure_latches, mutant, False)
    elif guard == "drain":
        run(test_shutdown_b03_eight_result_sample_schedules, baseline, "program", "during-stats")
        replace_method(m._Observer, "park", "if not self.inflight:", "if True:")
        with pytest.raises(AssertionError):
            run(test_shutdown_b03_eight_result_sample_schedules, mutant, "program", "during-stats")
    elif guard == "latch":
        run(test_shutdown_b05_genuine_drain_errors_never_grant, baseline, "program", "missing")
        replace_method(m._Observer, "_run", "elif self.failure is None:", "elif False:")
        with pytest.raises(AssertionError):
            run(test_shutdown_b05_genuine_drain_errors_never_grant, mutant, "program", "missing")
    elif guard == "freshness":
        run(test_shutdown_b06_parked_original_frame_bounds, baseline, 4.001, 201326592, False)
        replace_method(m._Observer, "shutdown_check", "if not 0 <= age <= 4.0:", "if False:")
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            run(test_shutdown_b06_parked_original_frame_bounds, mutant, 4.001, 201326592, False)
    elif guard == "deadline":
        run(test_shutdown_b06_cleanup_mode_keeps_explicit_supervision, baseline, "controller")
        replace_method(m._Daemon, "_supervise", "if shutdown is not None:", "if False:")
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            run(test_shutdown_b06_cleanup_mode_keeps_explicit_supervision, mutant, "controller")
    else:
        run(test_shutdown_b07_unknown_actor_absence_refuses_ack, baseline)
        monkeypatch.setattr(m, "_prove_actor_absence", lambda *args: None)
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            run(test_shutdown_b07_unknown_actor_absence_refuses_ack, mutant)


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_shutdown_b02_wire_version_policy_and_exact_lf_binding(tmp_path, monkeypatch, role):
    from bench.score import ExResult
    m = api(); profile = fixture_profile(tmp_path)
    response = m.ProgramResponse("unchanged", False) if role == "program" else ExResult(1.0, "match", True, "", 1, 1)
    result = m.encode_wire_message(role, "result", response, request_sha256="a" * 64)
    grant = m.encode_wire_message(role, "exit_grant", m.ExitGrant(hashlib.sha256(result).hexdigest()),
                                  request_sha256="a" * 64)
    assert json.loads(result)["schema_version"] == json.loads(grant)["schema_version"] == 2
    assert profile.schema_version == profile.binding.schema_version == 1
    decoded = m.decode_wire_message(grant, role=role, kind="exit_grant", request_sha256="a" * 64)
    assert decoded.payload.result_sha256 != hashlib.sha256(result[:-1]).hexdigest()
    old = json.loads(result); old["schema_version"] = 1
    with pytest.raises(ValueError):
        m.decode_wire_message(m.canonical_json_bytes(old) + b"\n",
                              role=role, kind="result", request_sha256="a" * 64)
    maximum = m.limits_for(role).input_bytes
    exact_request = b"x" * (maximum - len(grant))
    assert len(m.bounded_bytes(exact_request + grant, maximum=maximum)) == maximum
    with pytest.raises(ValueError):
        m.bounded_bytes(exact_request + b"x" + grant, maximum=maximum)
    current_policy = m.execution_policy_sha256(profile)
    monkeypatch.setattr(m, "WIRE_SCHEMA_VERSION", 1)
    assert m.execution_policy_sha256(profile) != current_policy


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("overflow", [0, 1])
def test_shutdown_b02_guest_counts_request_plus_grant(tmp_path, monkeypatch, role, overflow):
    import io
    import types
    from bench.task import SqlTask
    m = api()
    if role == "program":
        request = m.ProgramRequest("pass", 1, "a" * 64)
    else:
        task = SqlTask("fixture", "q", "", "SELECT 1", "db", "/db.sqlite",
                       "simple", "derived", "s", "s", "fixture")
        request = m.ScoreRequest(task, "SELECT 1", 1.0, 1, "set", "a" * 64)
    sha, result = m.request_sha256(request), b"exact original result frame\n"
    request_wire = m.encode_wire_message(role, "request", request)
    grant = m.encode_wire_message(role, "exit_grant", m.ExitGrant(hashlib.sha256(result).hexdigest()),
                                  request_sha256=sha)
    cap = len(request_wire) + len(grant) - overflow
    original = m.limits_for
    monkeypatch.setattr(m, "limits_for", lambda role: dataclasses.replace(original(role), input_bytes=cap))
    monkeypatch.setattr(m, "sys", types.SimpleNamespace(stdin=types.SimpleNamespace(buffer=io.BytesIO(grant))))
    if overflow:
        with pytest.raises(ValueError, match="byte cap exceeded"):
            m._worker_wait_for_exit_grant(role, sha, result, request)
    else:
        m._worker_wait_for_exit_grant(role, sha, result, request)


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["persistent-journal", "persistent-store", "uncertain-grant"])
def test_shutdown_b11_b12_guardian_failure_orchestration(tmp_path, monkeypatch, role, fault):
    error, timeline, delivered, _, observer, journal = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, "during-stats", fault, complete=True)
    assert error is not None
    assert "ATTACH_CLOSED" in timeline
    assert (tmp_path / "private-shared/active.json").is_file()
    assert not (tmp_path / "job/outcome.json").exists()
    assert journal["state"] == "UNRESOLVED"
    assert not observer.thread.is_alive()
    if fault.startswith("persistent"):
        assert len(delivered) == 1
        assert timeline.count("JOURNAL_WRITE_REFUSED") >= 2, "failure was only one-shot"
        assert observer.state == "ABORTED" and not observer.retired
        assert not any(k in timeline for k in ("KILL_ATTEMPT", "STOPPED", "OBSERVER_RETIRED",
                                               "OBSERVER_JOIN_ACK", "DELETE", "CLOSED"))
    else:
        assert len(delivered) == 2 and timeline.count("grant") == 1
        assert "EXIT_GRANT_SENT" not in timeline
        assert (tmp_path / "private-shared/UNRESOLVED-review-owned.json").is_file()
        assert "ABSENCE" in timeline or journal["state"] == "UNRESOLVED"


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("budget", ["role", "cleanup"])
@pytest.mark.parametrize("phase", ["grant", "eof", "stopped-inspect", "retirement", "delete", "absence",
                                  "outcome", "reservation"])
def test_shutdown_b13_original_deadlines_through_completion(tmp_path, monkeypatch, role, budget, phase):
    _, timeline, delivered, _, _, journal = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, "during-stats", complete=True, expiry=(budget, phase))
    assert len(delivered) == 2
    assert journal["cleanup_deadline"] == journal["cleanup_trigger"] + 12.0
    assert journal["state"] == "UNRESOLVED"
    assert (tmp_path / "private-shared/active.json").is_file(), "overdue result released reservation"
    if phase not in ("outcome", "reservation"):
        assert not (tmp_path / "job/outcome.json").exists()
    else:
        assert (tmp_path / "job/outcome.json").exists(), "provisional evidence was lost"
        m = api()
        with pytest.raises(m._Failure):
            m._completed_outcome_ready(None, journal, type("Completed", (), {"abort": None})())
    if budget == "role" and phase in ("retirement", "delete", "absence"):
        assert "ABSENCE" in timeline, "role expiry blocked otherwise-authorized failure cleanup"


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("fault", ["cli-unwind", "http-unwind", "pool-unwind"])
def test_shutdown_b14_drain_unwind_failure_blocks_park_and_grant(tmp_path, monkeypatch, role, fault):
    error, timeline, delivered, _, observer, _ = _shutdown_race_fixture(
        tmp_path, monkeypatch, role, "during-stats", fault)
    assert error is not None and observer.failure is not None
    assert len(delivered) <= 1
    assert not any(k in timeline for k in ("OBSERVER_PARKED", "EXIT_GRANT_INTENT",
                                           "OBSERVER_JOIN_ACK", "DELETE", "CLOSED"))


@pytest.mark.parametrize("role", ["program", "scorer"])
@pytest.mark.parametrize("state", ["pending", "closed", "unresolved", "blocked", "role-expired", "cleanup-expired"])
def test_shutdown_b15_controller_completion_interlock(tmp_path, monkeypatch, role, state):
    import types
    from bench.score import ExResult
    m = api()
    profile = types.SimpleNamespace(shared_state_dir=tmp_path)
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: 100.0))
    receipt = m.RuntimeReceipt(role, "a" * 64, "fixture", "fixture", "b" * 64, "c" * 64)
    outcome = (m.ProgramOutcome("provisional", None, receipt) if role == "program" else
               m.ScoreOutcome(ExResult(1.0, "match", True, "", 1, 1), None, receipt))
    journal = {"shutdown_requested": True, "state": "CLOSED", "deadline": 110.0,
               "cleanup_deadline": 112.0, "nonce": "fixture"}
    if state == "pending": (tmp_path / "active.json").write_text("durable reservation remains")
    if state == "unresolved": journal["state"] = "UNRESOLVED"
    if state == "blocked": (tmp_path / "UNRESOLVED-fixture.json").write_text("retained block")
    if state == "role-expired": journal["deadline"] = 100.0
    if state == "cleanup-expired": journal["cleanup_deadline"] = 100.0
    if state in ("pending", "closed"):
        assert m._completed_outcome_ready(profile, journal, outcome) is False, "provisional artifact without ACK/COMMITTED"
    else:
        with pytest.raises(m._Failure):
            m._completed_outcome_ready(profile, journal, outcome)


def _finalization_fixture(tmp_path, monkeypatch, *, abort=False, guardian_pid=None):
    """Real owned files and lock namespace; no Docker/CLI/HTTP mocks involved."""
    import os
    m = api()
    shared = tmp_path / "finalization-shared"; shared.mkdir()
    monkeypatch.setattr(m, "shared_state_dir_for", lambda _: shared)
    profile = _review_profile(tmp_path)
    job, journal = _review_job(tmp_path, profile)
    request = m.ProgramRequest("pass", 1, "b" * 64)
    raw_profile = m.execution_profile_canonical_bytes(profile)
    now = m.time.monotonic()
    journal.update(state="CLOSED", guardians=[guardian_pid or os.getpid()], controller=os.getpid(),
                   profile_sha256=hashlib.sha256(raw_profile).hexdigest(),
                   request_sha256=m.request_sha256(request), cleanup_trigger=now,
                   cleanup_deadline=now + 12, deadline=now - 1 if abort else now + 10,
                   bootstrap={"python_version": "fixture", "sqlite_version": "fixture"},
                   bootstrap_sha256="d" * 64)
    if abort: journal["failure"] = {"reason": "deadline", "detail": "fixture typed abort"}
    raw_journal = m.canonical_json_bytes(journal) + b"\n"
    receipt = m.RuntimeReceipt("program", journal["request_sha256"], "fixture", "fixture",
                               "d" * 64, hashlib.sha256(raw_journal).hexdigest())
    outcome = (m.ProgramOutcome(None, m.AbortInfo("program", "deadline"), receipt) if abort else
               m.ProgramOutcome("completed", None, receipt))
    raw_outcome = m.canonical_json_bytes(outcome) + b"\n"
    m._write_owned(job / "profile.json", raw_profile)
    m._write_owned(job / "request.wire", m.encode_wire_message("program", "request", request))
    m._write_owned(job / "journal.json", raw_journal)
    m._write_owned(job / "prepared-outcome", raw_outcome)
    m._write_owned(shared / "active.json",
                   m.canonical_json_bytes({"nonce": journal["nonce"], "job": str(job)}) + b"\n")
    read, write = os.pipe()
    return m, profile, job, journal, raw_journal, raw_outcome, outcome, read, write


@pytest.fixture
def finalization_files(tmp_path, monkeypatch):
    import os
    values = _finalization_fixture(tmp_path, monkeypatch)
    try:
        yield values
    finally:
        os.close(values[-2]); os.close(values[-1])


def _finalization_attempt(values):
    m, profile, job, journal, raw_journal, raw_outcome, _, read, _ = values
    return m._publish_finalization(profile, journal, job, raw_journal, raw_outcome, read)


def _assert_finalization_blocked(values):
    m, profile, *_ = values
    with pytest.raises(m._Failure, match="finalization|reservation"):
        m._admit_finalizations(profile)


def test_finalization_f01_real_unlink_persistent_fsync_failure(finalization_files, monkeypatch):
    import os
    import stat
    values = finalization_files
    m, profile, job, journal, *rest = values
    original_fsync, original_write = os.fsync, os.write
    failed = [False]
    def fsync(fd):
        if (not (profile.shared_state_dir / "active.json").exists()
                and stat.S_ISDIR(os.fstat(fd).st_mode)):
            failed[0] = True
        if failed[0]: raise OSError("persistent release fsync outage")
        return original_fsync(fd)
    def write(fd, data):
        if failed[0]: raise OSError("all subsequent writes refused")
        return original_write(fd, data)
    monkeypatch.setattr(m.os, "fsync", fsync)
    monkeypatch.setattr(m.os, "write", write)
    with pytest.raises(OSError): _finalization_attempt(values)
    assert failed[0] and not (profile.shared_state_dir / "active.json").exists(), "real unlink not exercised"
    pending = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    assert pending.is_file() and (job / "outcome.json").is_file()
    assert json.loads((job / "journal.json").read_bytes())["state"] == "CLOSED"
    assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
    _assert_finalization_blocked(values)  # Before any reservation/CREATE/START.
    assert not m._completed_outcome_ready(profile, journal, values[6]), "absence gate accepted failed fsync"
    reached = []
    def forbidden(*args):
        reached.append("stage/create/start")
        raise AssertionError("pending admission allowed new job work")
    monkeypatch.setattr(m, "_stage_sources", forbidden)
    executor = m.PilotExecutor(profile, state_dir=job.parent)
    refused = m._run_isolated(executor, "program", m.ProgramRequest("pass", 1, "b" * 64),
                              job / "never-open.sqlite")
    assert refused.abort.reason == "admission" and reached == [], "fresh controller crossed durable pending"


@pytest.mark.parametrize("operation", [
    "pending-write", "pending-filefsync", "pending-publish", "pending-dirfsync",
    "journal", "outcome", "history", "unlink", "releasefsync", "ack",
    "commit-write", "commit-filefsync", "commit-publish", "commit-dirfsync"])
def test_finalization_f04_real_operation_faults(finalization_files, monkeypatch, operation):
    import io
    import os
    import stat
    values = finalization_files
    m, profile, job, journal, *_ = values
    phase, pending_durable, unlinks = [None], [False], []
    publish, write, fsync, link, unlink = m._publish_immutable, os.write, os.fsync, os.link, os.unlink
    owned_write, append = m._write_owned, m._append_owned
    def publication(path, data):
        phase[0] = "pending" if path.name.startswith("FINALIZATION-PENDING") else "commit"
        try:
            result = publish(path, data)
            if phase[0] == "pending": pending_durable[0] = True
            return result
        finally:
            phase[0] = None
    def fail(label):
        if operation == label: raise OSError("controlled " + label)
    def writing(fd, data):
        fail(str(phase[0]) + "-write")
        return write(fd, data)
    def syncing(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if phase[0]: fail(phase[0] + ("-dirfsync" if directory else "-filefsync"))
        elif directory and not (profile.shared_state_dir / "active.json").exists(): fail("releasefsync")
        return fsync(fd)
    def linking(*args, **kwargs):
        fail(str(phase[0]) + "-publish")
        return link(*args, **kwargs)
    def unlinking(path, **kwargs):
        if str(path) == "active.json":
            assert pending_durable[0], "active unlink before durable pending"
            unlinks.append(path); fail("unlink")
        return unlink(path, **kwargs)
    def writing_owned(path, data, **kwargs):
        if path.name == "journal.json": fail("journal")
        if path.name == "outcome.json": fail("outcome")
        return owned_write(path, data, **kwargs)
    def appending(path, data):
        if path.name == "history.jsonl": fail("history")
        return append(path, data)
    class AckStream(io.BytesIO):
        def write(self, data):
            fail("ack")
            return super().write(data)
    monkeypatch.setattr(m, "_publish_immutable", publication)
    monkeypatch.setattr(m.os, "write", writing); monkeypatch.setattr(m.os, "fsync", syncing)
    monkeypatch.setattr(m.os, "link", linking); monkeypatch.setattr(m.os, "unlink", unlinking)
    monkeypatch.setattr(m, "_write_owned", writing_owned); monkeypatch.setattr(m, "_append_owned", appending)
    completed = []
    with pytest.raises((OSError, m._Failure)):
        ack = _finalization_attempt(values)
        stream = AckStream()
        m._send_terminal_ack(stream, ack)
        completed.append(m._commit_finalization(profile, job, journal, os.getpid(), stream.getvalue()))
    assert not completed
    if operation.startswith("pending"): assert not unlinks
    if operation != "commit-dirfsync": _assert_finalization_blocked(values)
    else:
        # Visible COMMITTED is not current-call success. Later admission may
        # validate and reestablish its durability, never return this outcome.
        assert list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
        m._admit_finalizations(profile)


@pytest.mark.parametrize("field", ["job", "nonce", "role", "profile_sha256", "request_sha256",
    "journal_sha256", "outcome_sha256", "guardian_pid", "finalization_token",
    "role_deadline", "cleanup_trigger", "cleanup_deadline"])
def test_finalization_f06_pending_field_binding(finalization_files, field):
    import os
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    path = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    record = json.loads(path.read_bytes())
    value = record["payload"][field]
    record["payload"][field] = (value + 1 if type(value) in (int, float) else
                               ("scorer" if field == "role" else
                                ("f" * 64 if field.endswith("sha256") else value + "-other")))
    raw = m._finalization_record("pending", record["payload"])
    path.write_bytes(raw)  # Deliberate trusted-fixture corruption, not publisher.
    ack["pending_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises((ValueError, TypeError, OSError, m._Failure)):
        m._commit_finalization(profile, job, journal, os.getpid(), m.canonical_json_bytes(ack) + b"\n")
    assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))


@pytest.mark.parametrize("fault", ["format", "schema_version", "pending_sha256", "guardian_pid",
    "finalization_token", "release_verified_at", "bool-time", "nan-time", "extra", "missing",
    "duplicate-key", "partial", "duplicate-frame", "oversize", "eof"])
def test_finalization_f06_closed_ack(finalization_files, fault):
    import os
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    if fault in ("format", "finalization_token"): ack[fault] += "-wrong"
    if fault == "schema_version": ack[fault] = True
    if fault == "pending_sha256": ack[fault] = "f" * 64
    if fault == "guardian_pid": ack[fault] += 1
    if fault == "release_verified_at": ack[fault] = journal["cleanup_deadline"]
    if fault == "bool-time": ack["release_verified_at"] = True
    if fault == "nan-time": ack["release_verified_at"] = float("nan")
    if fault == "extra": ack["extra"] = 1
    if fault == "missing": del ack["finalization_token"]
    raw = json.dumps(ack, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if fault == "duplicate-key": raw = raw[:-2] + b',"guardian_pid":1}\n'
    if fault == "partial": raw = raw[:-1]
    if fault == "duplicate-frame": raw += raw
    if fault == "oversize": raw = b" " * 4096 + raw
    if fault == "eof": raw = b""
    with pytest.raises((ValueError, TypeError, m._Failure)):
        m._commit_finalization(profile, job, journal, os.getpid(), raw)
    _assert_finalization_blocked(finalization_files)


@pytest.mark.parametrize("fault", ["no-commit", "partial-pending", "duplicate-pending",
    "extra-pending", "envelope-digest", "pending-symlink", "missing-profile", "missing-journal",
    "missing-outcome", "missing-request", "outcome-bytes", "commit-partial", "commit-symlink",
    "commit-binding", "commit-pending-sha", "request-binding", "pending-unreadable",
    "commit-unreadable", "iteration-error"])
def test_finalization_f08_historical_admission(finalization_files, monkeypatch, fault):
    import os
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    if fault != "no-commit":
        m._commit_finalization(profile, job, journal, os.getpid(), m.canonical_json_bytes(ack) + b"\n")
    pending = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    committed = profile.shared_state_dir / ("FINALIZATION-COMMITTED-" + journal["nonce"] + ".json")
    if fault == "partial-pending": pending.write_bytes(b'{"format":')
    if fault == "duplicate-pending": pending.write_bytes(pending.read_bytes()[:-2] + b',"sha256":"f"}\n')
    if fault == "extra-pending":
        record = json.loads(pending.read_bytes()); record["extra"] = 1
        pending.write_bytes(m.canonical_json_bytes(record) + b"\n")
    if fault == "envelope-digest":
        record = json.loads(pending.read_bytes()); record["sha256"] = "f" * 64
        pending.write_bytes(m.canonical_json_bytes(record) + b"\n")
    if fault in ("pending-symlink", "commit-symlink"):
        path = pending if fault == "pending-symlink" else committed
        target = job / "marker-copy"; target.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(target)
    if fault.startswith("missing-"): (job / (fault[8:] + (".wire" if fault == "missing-request" else ".json"))).unlink()
    if fault == "outcome-bytes": (job / "outcome.json").write_bytes((job / "outcome.json").read_bytes() + b"\n")
    if fault == "commit-partial": committed.write_bytes(b"{")
    if fault == "commit-binding":
        record = json.loads(committed.read_bytes())
        record["payload"]["terminal_ack"]["finalization_token"] = "f" * 32
        committed.write_bytes(m._finalization_record("committed", record["payload"]))
    if fault == "commit-pending-sha":
        record = json.loads(committed.read_bytes())
        record["payload"]["pending_sha256"] = "f" * 64
        committed.write_bytes(m._finalization_record("committed", record["payload"]))
    if fault == "request-binding":
        (job / "request.wire").write_bytes(m.encode_wire_message(
            "program", "request", m.ProgramRequest("changed", 1, "b" * 64)))
    if fault.endswith("-unreadable"):
        target = pending if fault == "pending-unreadable" else committed
        read_owned = m._read_owned
        def unreadable(path, *args, **kwargs):
            if path == target: raise PermissionError("controlled marker read denied, even under root")
            return read_owned(path, *args, **kwargs)
        monkeypatch.setattr(m, "_read_owned", unreadable)
    if fault == "iteration-error":
        def denied(*args): raise PermissionError("controlled owned-directory iteration failure")
        monkeypatch.setattr(m.os, "scandir", denied)
    _assert_finalization_blocked(finalization_files)


@pytest.mark.parametrize("abort", [False, True])
def test_finalization_f07_original_bounds_and_immutable_commit(tmp_path, monkeypatch, abort):
    import os
    import types
    values = _finalization_fixture(tmp_path, monkeypatch, abort=abort)
    m, profile, job, journal, *_ = values
    try:
        ack = _finalization_attempt(values)
        raw = m.canonical_json_bytes(ack) + b"\n"
        outcome = m._commit_finalization(profile, job, journal, os.getpid(), raw)
        assert (outcome.abort is not None) is abort
        m._admit_finalizations(profile)
        marker = profile.shared_state_dir / ("FINALIZATION-COMMITTED-" + journal["nonce"] + ".json")
        original = marker.read_bytes()
        with pytest.raises(FileExistsError): m._publish_immutable(marker, b"must not replace\n")
        assert marker.read_bytes() == original
        clock = journal["cleanup_deadline"] if abort else journal["deadline"]
        monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=lambda: clock))
        with pytest.raises(m._Failure):
            m._commit_finalization(profile, job, journal, os.getpid(), raw)
    finally:
        os.close(values[-2]); os.close(values[-1])


@pytest.mark.parametrize("point", ["hold", "exit-zero", "after-ack-stall", "before-pending",
                                  "after-pending", "after-unlink", "after-release-fsync", "fragmented"])
def test_finalization_f02_f03_f05_f09_owned_guardian_process(tmp_path, monkeypatch, point):
    """Actual isolated Python + pipe + production transaction/receive/commit."""
    import os
    import subprocess
    import sys
    import time
    m = api()
    # Child waits for G before opening fixture artifacts or invoking product code.
    code = r'''
import os, stat, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import ptc.sql_isolation as m
job, shared, point = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
if os.read(sys.stdin.fileno(), 1) != b"G": os._exit(2)
m.shared_state_dir_for = lambda _: shared
p = m.execution_profile_from_bytes(m._read_owned(job / "profile.json"))
jraw, oraw = m._read_owned(job / "journal.json"), m._read_owned(job / "prepared-outcome")
j = m._metadata(jraw)
write, publish, unlink, fsync = m._write_owned, m._publish_immutable, os.unlink, os.fsync
def writing(path, data, **kwargs):
    return write(path, data, **kwargs)
def publishing(path, data):
    result = publish(path, data)
    if point == "after-pending" and path.name.startswith("FINALIZATION-PENDING"): os._exit(0)
    return result
def unlinking(path, **kwargs):
    result = unlink(path, **kwargs)
    if str(path) == "active.json":
        # Deliberately expose the old false-success state for >2s: CLOSED +
        # outcome + no active, but no positive release fsync / terminal ACK.
        if point in ("hold", "exit-zero"):
            time.sleep(2.25)
            if point == "exit-zero": os._exit(0)
        if point == "after-unlink": os._exit(0)
    return result
def syncing(fd):
    result = fsync(fd)
    if point == "after-release-fsync" and stat.S_ISDIR(os.fstat(fd).st_mode) and not (shared / "active.json").exists():
        os._exit(0)
    return result
m._write_owned, m._publish_immutable, os.unlink, os.fsync = writing, publishing, unlinking, syncing
if point == "before-pending": os._exit(0)
ack = m._publish_finalization(p, j, job, jraw, oraw, sys.stdin.fileno())
if point == "fragmented":
    for byte in m.canonical_json_bytes(ack) + b"\n":
        os.write(sys.stdout.fileno(), bytes([byte]))
else:
    m._send_terminal_ack(sys.stdout.buffer, ack)
if point == "after-ack-stall": time.sleep(10)
'''
    process = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(m.installed_source_root()),
                                str(tmp_path / "job"), str(tmp_path / "finalization-shared"), point],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    values = None
    try:
        values = _finalization_fixture(tmp_path, monkeypatch, guardian_pid=process.pid)
        _, profile, job, journal, *_ = values
        process.stdin.write(b"G"); process.stdin.flush()
        started = time.monotonic()
        if point in ("hold", "fragmented", "after-ack-stall"):
            outcome = m._finish_finalization(process, profile, job, journal)
            assert outcome.observation == "completed"
            if point == "hold":
                assert time.monotonic() - started >= 2.25, "pre-ACK outcome accepted or guardian killed"
                assert process.returncode == 0, "pre-ACK hygiene killed provisional guardian"
            if point == "after-ack-stall":
                assert process.returncode == -9 and time.monotonic() - started >= 2
            assert len(list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))) == 1
            m._admit_finalizations(profile)
        else:
            with pytest.raises((m._Failure, ValueError, OSError)):
                m._finish_finalization(process, profile, job, journal)
            if point == "exit-zero":
                process.wait(timeout=2)
                assert process.returncode == 0, "exit-zero boundary not exercised"
            assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
            _assert_finalization_blocked(values)
    finally:
        if process.poll() is None: process.kill()
        process.wait(timeout=2)
        process.stdin.close(); process.stdout.close(); process.stderr.close()
        REVIEW_PROCESS_RESULTS.append({"pid": process.pid, "proof": "owned Popen.wait",
                                       "returncode": process.returncode})
        if values is not None:
            os.close(values[-2]); os.close(values[-1])


@pytest.mark.parametrize("guard", ["pending-admission", "ack-required", "digest-binding"])
def test_finalization_f09_intended_red_controls(finalization_files, monkeypatch, guard):
    import os
    import types
    values = finalization_files
    m, profile, job, journal, *_ = values
    ack = _finalization_attempt(values)
    if guard == "pending-admission":
        _assert_finalization_blocked(values)
        monkeypatch.setattr(m, "_admit_finalizations", lambda _: None)
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            _assert_finalization_blocked(values)
    elif guard == "ack-required":
        # Actual EOF pipe: baseline cannot commit even with all provisional files.
        read, write = os.pipe(); os.close(write)
        stream = os.fdopen(read, "rb", buffering=0)
        process = types.SimpleNamespace(pid=os.getpid(), stdout=stream, poll=lambda: 0,
                                        wait=lambda **kw: 0)
        try:
            def no_ack_no_commit():
                try: m._finish_finalization(process, profile, job, journal)
                except m._Failure: pass
                assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*")), "ACK bypass accepted completion"
            no_ack_no_commit()
            monkeypatch.setattr(m, "_receive_terminal_ack", lambda *args: m.canonical_json_bytes(ack) + b"\n")
            with pytest.raises(AssertionError, match="ACK bypass accepted completion"):
                no_ack_no_commit()
        finally:
            stream.close()
    else:
        outcome = json.loads((job / "outcome.json").read_bytes()); outcome["observation"] = "tampered"
        (job / "outcome.json").write_bytes(m.canonical_json_bytes(outcome) + b"\n")
        frame = m.canonical_json_bytes(ack) + b"\n"
        def digest_must_reject():
            with pytest.raises((m._Failure, ValueError), match="digest|artifact"):
                m._commit_finalization(profile, job, journal, os.getpid(), frame)
        digest_must_reject()
        source = inspect.getsource(m._validate_finalization)
        target = 'if hashlib.sha256(raw).hexdigest() != pending[field]:'
        assert source.count(target) == 1
        namespace = {}
        exec(source.replace(target, 'if field != "outcome_sha256" and hashlib.sha256(raw).hexdigest() != pending[field]:'), vars(m), namespace)
        monkeypatch.setattr(m, "_validate_finalization", namespace["_validate_finalization"])
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            digest_must_reject()


@pytest.mark.parametrize("kind", ["pending", "committed"])
@pytest.mark.parametrize("field", ["format", "schema_version", "bool-schema", "extra", "missing",
                                  "duplicate", "payload-extra", "payload-missing", "sha256", "payload-type"])
def test_finalization_f06_closed_marker_envelopes(finalization_files, kind, field):
    import os
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    m._commit_finalization(profile, job, journal, os.getpid(), m.canonical_json_bytes(ack) + b"\n")
    path = profile.shared_state_dir / ("FINALIZATION-" + kind.upper() + "-" + journal["nonce"] + ".json")
    record = json.loads(path.read_bytes())
    if field == "format": record[field] = "other"
    if field == "schema_version": record[field] = 2
    if field == "bool-schema": record["schema_version"] = True
    if field == "extra": record["extra"] = 1
    if field == "missing": del record["format"]
    if field == "payload-extra": record["payload"]["extra"] = 1
    if field == "payload-missing": record["payload"].pop(next(iter(record["payload"])))
    if field == "payload-type": record["payload"] = []
    if field.startswith("payload-"):
        record["sha256"] = hashlib.sha256(m.canonical_json_bytes(record["payload"])).hexdigest()
    if field == "sha256": record[field] = "f" * 64
    raw = m.canonical_json_bytes(record) + b"\n"
    if field == "duplicate": raw = raw[:-2] + b',"schema_version":1}\n'
    path.write_bytes(raw)
    _assert_finalization_blocked(finalization_files)


@pytest.mark.parametrize("budget", ["role", "cleanup"])
def test_finalization_f07_partial_live_pipe_original_deadlines(finalization_files, monkeypatch, budget):
    import os
    import types
    m, profile, job, journal, *_ = finalization_files
    _finalization_attempt(finalization_files)
    read, write = os.pipe()
    os.write(write, b"{")  # Writable peer stays live; readline() would block.
    stream = os.fdopen(read, "rb", buffering=0)
    calls = []
    start = journal["deadline" if budget == "role" else "cleanup_deadline"]
    def clock():
        calls.append(1)
        return start + len(calls) - 1
    monkeypatch.setattr(m, "time", types.SimpleNamespace(monotonic=clock))
    process = types.SimpleNamespace(pid=os.getpid(), stdout=stream, poll=lambda: None)
    try:
        with pytest.raises(m._Failure, match="original.*deadline"):
            m._receive_terminal_ack(process, journal, job)
        assert len(calls) == 1, "partial live ACK bypassed original deadline"
        assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
    finally:
        stream.close(); os.close(write)


def test_finalization_f08_cross_profile_fresh_controller_barrier(finalization_files, monkeypatch, tmp_path):
    m, profile, job, journal, *_ = finalization_files
    _finalization_attempt(finalization_files)
    other_root = tmp_path / "other-profile"; other_root.mkdir()
    other = _review_profile(other_root)  # Different observer/profile, same shared lock namespace.
    assert m.execution_profile_sha256(other) != m.execution_profile_sha256(profile)
    state = tmp_path / "other-run"; state.mkdir()
    reached = []
    def forbidden(*args):
        reached.append("new job work")
        raise AssertionError("uncommitted cross-profile transaction admitted")
    monkeypatch.setattr(m, "_stage_sources", forbidden)
    outcome = m._run_isolated(m.PilotExecutor(other, state_dir=state), "program",
                              m.ProgramRequest("pass", 1, "b" * 64), job / "never-open.sqlite")
    assert outcome.abort.reason == "admission" and not reached
    assert list(state.iterdir()) == []


@pytest.mark.parametrize("fault", ["duplicate", "oversize", "partial-eof"])
def test_finalization_f06_real_terminal_pipe_bounds(finalization_files, fault):
    import os
    import types
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    raw = m.canonical_json_bytes(ack) + b"\n"
    data = raw + raw if fault == "duplicate" else (b"x" * 4097 if fault == "oversize" else raw[:-1])
    read, write = os.pipe()
    stream = os.fdopen(read, "rb", buffering=0)
    try:
        assert os.write(write, data) == len(data)
        os.close(write); write = None
        process = types.SimpleNamespace(pid=os.getpid(), stdout=stream, poll=lambda: 0)
        with pytest.raises((ValueError, m._Failure)):
            m._finish_finalization(process, profile, job, journal)
        assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
    finally:
        stream.close()
        if write is not None: os.close(write)


@pytest.mark.parametrize("field", ["role", "request_sha256", "python_version", "sqlite_version",
                                  "bootstrap_sha256", "journal_sha256"])
def test_finalization_f06_receipt_binding(finalization_files, field):
    import os
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    path = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    pending = json.loads(path.read_bytes())["payload"]
    outcome = json.loads((job / "outcome.json").read_bytes())
    outcome["receipt"][field] = ("scorer" if field == "role" else
                                 ("f" * 64 if field.endswith("sha256") else "other"))
    raw_outcome = m.canonical_json_bytes(outcome) + b"\n"
    (job / "outcome.json").write_bytes(raw_outcome)
    pending["outcome_sha256"] = hashlib.sha256(raw_outcome).hexdigest()
    raw_pending = m._finalization_record("pending", pending)
    path.write_bytes(raw_pending)
    ack["pending_sha256"] = hashlib.sha256(raw_pending).hexdigest()
    with pytest.raises((TypeError, ValueError, m._Failure)):
        m._commit_finalization(profile, job, journal, os.getpid(), m.canonical_json_bytes(ack) + b"\n")
    assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))


@pytest.mark.parametrize("field", ["cleanup_trigger", "cleanup_deadline"])
def test_finalization_f07_controller_latches_original_cleanup(finalization_files, field):
    import os
    import types
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    changed = dict(journal); changed[field] += 0.5
    (job / "journal.json").write_bytes(m.canonical_json_bytes(changed) + b"\n")
    read, write = os.pipe()
    stream = os.fdopen(read, "rb", buffering=0)
    try:
        raw = m.canonical_json_bytes(ack) + b"\n"
        assert os.write(write, raw) == len(raw)
        process = types.SimpleNamespace(pid=os.getpid(), stdout=stream, poll=lambda: None)
        with pytest.raises(m._Failure, match="original.*cleanup"):
            m._receive_terminal_ack(process, journal, job)
        assert not list(profile.shared_state_dir.glob("FINALIZATION-COMMITTED-*"))
    finally:
        stream.close(); os.close(write)


def test_finalization_f07_ack_arrives_after_reserved_snapshot(finalization_files, monkeypatch):
    import os
    import types
    m, profile, job, journal, *_ = finalization_files
    ack = _finalization_attempt(finalization_files)
    original = {key: value for key, value in journal.items()
                if key not in ("cleanup_trigger", "cleanup_deadline")}
    original["state"] = "RESERVED"
    old_raw = m.canonical_json_bytes(original) + b"\n"
    read_owned, reads = m._read_owned, []
    def snapshot(path, *args, **kwargs):
        if path == job / "journal.json":
            reads.append(1)
            if len(reads) == 1: return old_raw
        return read_owned(path, *args, **kwargs)
    monkeypatch.setattr(m, "_read_owned", snapshot)
    read, write = os.pipe()
    stream = os.fdopen(read, "rb", buffering=0)
    try:
        raw = m.canonical_json_bytes(ack) + b"\n"
        assert os.write(write, raw) == len(raw)
        process = types.SimpleNamespace(pid=os.getpid(), stdout=stream, poll=lambda: None)
        frame = m._receive_terminal_ack(process, original, job)
        assert len(reads) >= 2, "ACK used pre-publication journal snapshot"
        assert original["cleanup_trigger"] == journal["cleanup_trigger"]
        assert original["cleanup_deadline"] == journal["cleanup_deadline"]
        assert m._commit_finalization(profile, job, original, os.getpid(), frame).observation == "completed"
    finally:
        stream.close(); os.close(write)


def test_finalization_f08_nonregular_owned_marker_cannot_block_open(finalization_files):
    import os
    import threading
    m, profile, job, journal, *_ = finalization_files
    _finalization_attempt(finalization_files)
    path = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    path.unlink(); os.mkfifo(path, 0o600)  # Controlled malformed owned fixture.
    done, failures = threading.Event(), []
    def admission():
        try: m._admit_finalizations(profile)
        except m._Failure as exc: failures.append(exc.reason)
        finally: done.set()
    thread = threading.Thread(target=admission)
    thread.start()
    writer = None
    try:
        finished = done.wait(1)
    finally:
        if not done.is_set():
            # Unblock a broken blocking read before asserting RED. Never leave
            # an owned test thread parked in FIFO open.
            writer = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        thread.join(2)
        if writer is not None: os.close(writer)
    assert not thread.is_alive()
    assert finished and failures == ["admission"], "nonregular pending blocked in open"
