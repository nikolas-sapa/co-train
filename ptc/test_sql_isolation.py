"""Pure Phase0 contract. Imports in bodies preserve assertion-based baseline RED."""
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
    with pytest.raises(NotImplementedError):
        m.PilotExecutor(p, state_dir=tmp_path / "run").run_program("pass", db_path="/db.sqlite", db_sha256="a" * 64, max_rows=1)
    with pytest.raises(NotImplementedError):
        m.PilotExecutor(p, state_dir=tmp_path / "run").score_sql("SELECT 1", None, db_sha256="a" * 64, instrument=None)
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
