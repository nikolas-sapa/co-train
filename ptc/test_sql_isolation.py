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
            obj["State"]["ExitCode"] = 0
            daemon = types.SimpleNamespace(call=lambda *a, **k: obj)
            assert m._stream_result(p, daemon, journal, job, read, observer, attached) == response
            assert delivered == [request_wire]
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
    m = api(); p = _review_profile(tmp_path)
    shared = tmp_path / "private-dispatch"; shared.mkdir()
    private_profile = types.SimpleNamespace(**{f.name: getattr(p, f.name) for f in dataclasses.fields(p)})
    private_profile.shared_state_dir = shared
    profile_wire = m.execution_profile_canonical_bytes(p)
    monkeypatch.setattr(m, "build_execution_binding", lambda *a, **k: p.binding)
    monkeypatch.setattr(m, "execution_profile_canonical_bytes", lambda _: profile_wire)
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
    # Real owned OS process: writes durable outcome, then remains alive >2s.
    code = (
        "import os,sys,json,pathlib,time;"
        "job=pathlib.Path(sys.argv[1]);fd=int(sys.argv[2]);"
        "os.write(1,b'ACK\\n');assert os.read(fd,1)==b'G';"
        "j=json.loads((job/'journal.json').read_bytes());j['state']=sys.argv[4];"
        "f=open(job/'journal.json','wb');f.write(json.dumps(j).encode());f.flush();os.fsync(f.fileno());f.close();"
        "f=open(job/'outcome.json','xb');f.write(sys.argv[3].encode());f.flush();os.fsync(f.fileno());f.close();"
        "(pathlib.Path(sys.argv[5])/'active.json').unlink() if sys.argv[4]=='CLOSED' else None;"
        "time.sleep(30)"
    )
    def spawn(command, **kwargs):
        child = OwnedProcess([sys.executable, "-I", "-B", "-c", code,
                              command[5], command[6], outcome_wire.decode(), state, str(shared)], **kwargs)
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
    assert result == expected and result.receipt == receipt
    if state == "CLOSED":
        assert before_cleanup["timeouts"] == 1 and before_cleanup["waits"][0] == 2
        assert before_cleanup["kills"] == 1 and before_cleanup["returncode"] == -9
        assert len(before_cleanup["waits"]) == 2, "dispatch did not reap its exact killed Popen"
        assert not (shared / "active.json").exists()
    else:
        assert before_cleanup == {"waits": [], "timeouts": 0, "kills": 0, "returncode": None}
        assert (shared / "active.json").exists()
    records = [json.loads(path.read_bytes()) for path in executor.state_dir.glob("*/journal.json")]
    assert len(records) == 1 and records[0]["state"] == state
    assert not list(shared.glob("UNRESOLVED-*")), "hygiene reap manufactured a new admission block"
