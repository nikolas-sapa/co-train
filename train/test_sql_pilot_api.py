"""TEST_ONLY financial/action fixtures, not provider billing evidence."""
import dataclasses
import hashlib
import importlib
import json
import time

import pytest


def api():
    try:
        return importlib.import_module("train.sql_pilot_api")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_pilot_api":
            raise
        pytest.fail("sql_pilot_api implementation missing", pytrace=False)


def profile_fixture(tmp_path):
    m = api()
    from ptc.sql_isolation import SourcePin
    evidence = tmp_path / "TEST_ONLY-evidence"
    evidence.write_bytes(b"TEST_ONLY: synthetic charge/receipt authority")
    pin = SourcePin(evidence.name, hashlib.sha256(evidence.read_bytes()).hexdigest())
    profile = m.BillingProfile(
        provider="TEST_ONLY", endpoint=m.ENDPOINT, model="TEST_ONLY-model",
        valid_from=1, valid_until=4_000_000_000, authority_ref="TEST_ONLY-external-review",
        evidence=(pin,), charges=(m.Charge("all_TEST_ONLY", "request", 7, 3, 10),),
        settlement_mode="authoritative_receipt_only",
        authorization=m.Authorization("TEST_ONLY", "a" * 64, "b" * 64,
                                      str(tmp_path / "budget"), 50_000_000, 25),
        receipt_directory=str(tmp_path / "receipts"),
    )
    profile_path = tmp_path / "billing.json"
    profile_path.write_bytes(m.billing_profile_bytes(profile))
    (tmp_path / "receipts").mkdir(mode=0o700)
    return m, profile, profile_path, hashlib.sha256(profile_path.read_bytes()).hexdigest()


def test_profile_closed_roundtrip_and_round_up(tmp_path):
    m, profile, path, approval = profile_fixture(tmp_path)
    loaded = m.load_billing_profile(path, approval_sha256=approval)
    assert loaded == profile
    assert m.maximum_charge(profile) == 24
    assert m.billing_config(profile, approval).profile_sha256 == approval
    assert m.billing_config(profile, approval).zero_charge_authorized is True


@pytest.mark.parametrize("change", ["approval", "expired", "endpoint", "bool", "extra", "zero_denominator", "empty", "evidence"])
def test_financial_fail_closed_before_key_or_http(tmp_path, monkeypatch, change):
    m, profile, path, approval = profile_fixture(tmp_path)
    calls = []
    monkeypatch.setattr(m, "_read_credential", lambda: calls.append("KEY"))
    monkeypatch.setattr(m, "_http_attempt", lambda *a: calls.append("HTTP"))
    with pytest.raises((ValueError, TypeError, m.FinancialBlocked)):
        if change == "approval":
            m.load_billing_profile(path, approval_sha256="0" * 64)
        elif change == "expired":
            m.validate_billing_profile(dataclasses.replace(profile, valid_until=2))
        elif change == "endpoint":
            dataclasses.replace(profile, endpoint="http://localhost")
        elif change == "bool":
            m.Charge("x", "x", True, 1, 1)
        elif change == "extra":
            raw = json.loads(path.read_bytes())
            raw["payload"]["unknown"] = "not allowed"
            m.billing_profile_from_bytes(m.canonical_bytes(raw) + b"\n")
        elif change == "zero_denominator":
            m.Charge("x", "x", 1, 0, 1)
        elif change == "empty":
            dataclasses.replace(profile, charges=())
        else:
            (tmp_path / "TEST_ONLY-evidence").write_bytes(b"tampered")
            m.load_billing_profile(path, approval_sha256=approval)
    assert calls == []


def response(arguments, **changes):
    value = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant",
             "content": None, "tool_calls": [{"id": "fixture", "type": "function",
             "function": {"name": "submit", "arguments": arguments}}]}}],
             "model": "TEST_ONLY-opaque-alias", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
    value.update(changes)
    return json.dumps(value).encode()


def test_identical_schema_forced_tool_and_exact_messages():
    m = api()
    body = m.build_request("opaque", {"question": "Unicode α", "schema": "CREATE TABLE x(v)", "library": []})
    value = json.loads(body)
    assert len(value["messages"]) == 2
    assert [x["role"] for x in value["messages"]] == ["system", "user"]
    assert value["max_tokens"] == 2048 and value["parallel_tool_calls"] is False
    assert value["tool_choice"]["function"]["name"] == "submit"
    schema = value["tools"][0]["function"]["parameters"]
    assert set(schema["required"]) == {"kind", "program", "skill_id", "promotion_sha256"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["kind"]["enum"] == ["program", "approved_skill"]


@pytest.mark.parametrize("change", ["extra", "missing", "empty", "ref", "unknown", "direct_ref", "duplicate", "two_calls", "content", "wrong_name", "bool"])
def test_strict_action_without_fallback(change):
    m = api()
    action = dict(kind="program", program="print('x')", skill_id="", promotion_sha256="")
    library = [{"skill_id": "s", "promotion_sha256": "a" * 64}]
    if change == "extra":
        action["extra"] = 1
    elif change == "missing":
        del action["skill_id"]
    elif change == "empty":
        action["program"] = ""
    elif change == "ref":
        action.update(kind="approved_skill", program="", skill_id="s", promotion_sha256="b" * 64)
    elif change == "unknown":
        action.update(kind="approved_skill", program="", skill_id="other", promotion_sha256="a" * 64)
    elif change == "direct_ref":
        action["skill_id"] = "s"
    elif change == "bool":
        action["program"] = True
    raw = response(json.dumps(action))
    if change == "duplicate":
        raw = response('{"kind":"program","kind":"program","program":"x","skill_id":"","promotion_sha256":""}')
    elif change == "two_calls":
        value = json.loads(raw)
        value["choices"][0]["message"]["tool_calls"] *= 2
        raw = json.dumps(value).encode()
    elif change == "content":
        raw = b'{"choices":[{"finish_reason":"stop","message":{"content":"print(1)"}}]}'
    elif change == "wrong_name":
        raw = raw.replace(b'"name": "submit"', b'"name": "other"')
    with pytest.raises(m.ModelActionError):
        m.parse_response(raw, library=library)


@pytest.mark.parametrize("size", [65536, 65537])
def test_program_utf8_exact_bound(size):
    m = api()
    args = dict(kind="program", program="a" * size, skill_id="", promotion_sha256="")
    if size == 65536:
        assert m.parse_response(response(json.dumps(args)), library=[]).program == "a" * size
    else:
        with pytest.raises(m.ModelActionError):
            m.parse_response(response(json.dumps(args)), library=[])


def test_receipt_exact_binding_and_no_reservation_as_actual(tmp_path):
    m, p, _, approval = profile_fixture(tmp_path)
    request_id = "TEST_ONLY:request:1"
    payload = dict(run_id=p.authorization.run_id, request_id=request_id,
                   model_request_sha256="c" * 64, model_response_sha256="d" * 64,
                   currency="USD", actual_charge_usd_micros=9,
                   authority_ref=p.authority_ref, evidence=[dataclasses.asdict(x) for x in p.evidence])
    raw = m.envelope_bytes("sql_pilot_billing_receipt", payload)
    path = tmp_path / "receipts" / (hashlib.sha256(request_id.encode()).hexdigest() + ".json")
    path.write_bytes(raw)
    assert m.load_receipt(p, request_id, "c" * 64, "d" * 64, evidence_root=tmp_path)[0] == 9
    for key, bad in [("currency", "EUR"), ("actual_charge_usd_micros", True),
                     ("request_id", "other"), ("model_response_sha256", "e" * 64)]:
        altered = dict(payload, **{key: bad})
        path.write_bytes(m.envelope_bytes("sql_pilot_billing_receipt", altered))
        with pytest.raises(m.FinancialBlocked):
            m.load_receipt(p, request_id, "c" * 64, "d" * 64, evidence_root=tmp_path)


def test_absolute_deadline_refuses_existing_timer():
    m = api()
    import signal
    previous = signal.getitimer(signal.ITIMER_REAL)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        with pytest.raises(m.FinancialBlocked):
            with m.absolute_deadline(1):
                pytest.fail("preexisting timer stolen")
        assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 30
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous)


def test_absolute_deadline_interrupts_slow_operation_and_restores():
    m = api()
    import signal
    handler = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    with pytest.raises(m.FinancialBlocked):
        with m.absolute_deadline(0.03):
            time.sleep(1)
    assert time.monotonic() - started < 0.5
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def execution_fixture(tmp_path):
    from ptc import sql_isolation as isolation
    from pathlib import Path
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = Path(isolation.__file__).resolve().parents[1]
    name = "train/sql_pilot_api.py"
    pin = isolation.SourcePin(name, hashlib.sha256((root / name).read_bytes()).hexdigest())
    binary = tmp_path / "TEST_ONLY-observer"
    binary.write_bytes(b"TEST_ONLY never executed")
    observer = isolation.MemoryObserver(binary=binary, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return isolation.make_execution_profile(daemon_socket=tmp_path / "TEST_ONLY.sock",
        observer=observer, program_sources=(pin,), scorer_sources=(pin,), controller_sources=(pin,))


def financial_world(tmp_path, *, maximum=None):
    from train.sql_pilot_assets import prepare_manifest, manifest_sha256
    from ptc.sql_isolation import execution_profile_sha256
    m, profile, profile_path, _ = profile_fixture(tmp_path)
    manifest = prepare_manifest(tmp_path / "assets" / "manifest.json",
                               output_dir=tmp_path / "assets", run_id="TEST_ONLY")
    execution = execution_fixture(tmp_path)
    profile = dataclasses.replace(profile, authorization=dataclasses.replace(profile.authorization,
        manifest_sha256=manifest_sha256(manifest), execution_profile_sha256=execution_profile_sha256(execution)))
    if maximum is not None:
        profile = dataclasses.replace(profile, charges=(m.Charge("TEST_ONLY-all", "request", maximum, 1, 1),))
    profile_path.write_bytes(m.billing_profile_bytes(profile))
    approval = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    m.init_budget(billing_profile_path=profile_path, approval_sha256=approval, manifest=manifest,
                  execution_profile=execution, budget_dir=tmp_path / "budget")
    kwargs = dict(billing_profile_path=profile_path, approval_sha256=approval,
                  manifest=manifest, execution_profile=execution, budget_dir=tmp_path / "budget",
                  output_dir=output, allow_execution=True, allow_model_requests=True)
    return m, profile, kwargs


def receipt_for(m, profile, kwargs, request_id, request, raw, actual=9):
    from pathlib import Path
    value = dict(run_id=profile.authorization.run_id, request_id=request_id,
                 model_request_sha256=hashlib.sha256(request).hexdigest(),
                 model_response_sha256=hashlib.sha256(raw).hexdigest(), currency="USD",
                 actual_charge_usd_micros=actual, authority_ref=profile.authority_ref,
                 evidence=[dataclasses.asdict(x) for x in profile.evidence])
    path = Path(profile.receipt_directory) / (hashlib.sha256(request_id.encode()).hexdigest() + ".json")
    path.write_bytes(m.envelope_bytes("sql_pilot_billing_receipt", value))


def test_durable_claim_before_key_and_transport_failure_holds_on_restart(tmp_path, monkeypatch):
    m, profile, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    events = []
    def key():
        events.append(("KEY", client.ledger.snapshot().requests[-1].state))
        return "TEST_ONLY_SYNTHETIC_CREDENTIAL"
    def transport(request, secret):
        events.append(("HTTP", secret == "TEST_ONLY_SYNTHETIC_CREDENTIAL"))
        raise RuntimeError("must not persist " + secret)
    monkeypatch.setattr(m, "_read_credential", key)
    monkeypatch.setattr(m, "_http_attempt", transport)
    with pytest.raises(m.FinancialBlocked) as error:
        client.request("TEST_ONLY:failure:1", {"library": []}, library=[])
    assert events == [("KEY", "dispatch_claimed"), ("HTTP", True)]
    assert "SYNTHETIC_CREDENTIAL" not in str(error.value)
    snap = client.ledger.snapshot()
    assert snap.reserved_charge_micros == 24 and snap.settled_charge_micros == 0
    with pytest.raises(m.FinancialBlocked):
        m.PilotAPI(**kwargs)
    assert len(events) == 2
    for path in kwargs["output_dir"].iterdir():
        assert b"TEST_ONLY_SYNTHETIC_CREDENTIAL" not in path.read_bytes()


@pytest.mark.parametrize("outcome", ["settled", "zero", "missing", "overrun", "malformed", "echo", "redirect"])
def test_one_attempt_and_exact_authoritative_receipt_settlement(tmp_path, monkeypatch, outcome):
    m, profile, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    events = []
    request_id = "TEST_ONLY:receipt:1"
    raw = response(json.dumps(dict(kind="program", program="print('x')", skill_id="", promotion_sha256="")))
    if outcome == "malformed":
        raw = response("{}")
    elif outcome == "echo":
        raw = b'{"error":"TEST_ONLY_SYNTHETIC_CREDENTIAL"}'
    def key():
        events.append("KEY")
        return "TEST_ONLY_SYNTHETIC_CREDENTIAL"
    def transport(request, secret):
        events.append("HTTP")
        if outcome not in ("missing", "echo"):
            receipt_for(m, profile, kwargs, request_id, request, raw,
                        actual=25 if outcome == "overrun" else 0 if outcome == "zero" else 9)
        return 302 if outcome == "redirect" else 200, raw
    monkeypatch.setattr(m, "_read_credential", key)
    monkeypatch.setattr(m, "_http_attempt", transport)
    if outcome in ("missing", "overrun", "echo"):
        with pytest.raises(m.FinancialBlocked):
            client.request(request_id, {"library": []}, library=[])
    elif outcome in ("malformed", "redirect"):
        with pytest.raises(m.ModelActionError) as error:
            client.request(request_id, {"library": []}, library=[])
        assert error.value.telemetry["actual_charge_usd_micros"] == 9
    else:
        reply = client.request(request_id, {"library": []}, library=[])
        assert reply.action.kind == "program"
        assert reply.telemetry["actual_charge_usd_micros"] == (0 if outcome == "zero" else 9)
        assert reply.telemetry["cache_protocol"] == "UNKNOWN"
    assert events == ["KEY", "HTTP"]
    snap = client.ledger.snapshot()
    if outcome in ("missing", "echo"):
        assert snap.reserved_charge_micros == 24
        assert snap.requests[0].actual_charge_micros is None
    elif outcome == "overrun":
        assert snap.status == "halted_overrun" and snap.settled_charge_micros == 25
    else:
        assert snap.reserved_charge_micros == 0
    # No replay, no auto-retry, even with a new API instance.
    from train.sql_pilot_budget import BudgetError
    before = list(events)
    try:
        restarted = m.PilotAPI(**kwargs)
        with pytest.raises((ValueError, OSError, m.FinancialBlocked, BudgetError)):
            restarted.request(request_id, {"library": []}, library=[])
    except m.FinancialBlocked:
        pass
    assert events == before
    for path in kwargs["output_dir"].iterdir():
        assert b"TEST_ONLY_SYNTHETIC_CREDENTIAL" not in path.read_bytes()


@pytest.mark.parametrize("change", ["manifest", "execution", "budget_path", "approval", "missing_profile", "missing_ledger", "flag"])
def test_api_admission_before_credential_and_backend(tmp_path, monkeypatch, change):
    m, profile, kwargs = financial_world(tmp_path)
    calls = []
    monkeypatch.setattr(m, "_read_credential", lambda: calls.append("KEY"))
    monkeypatch.setattr(m, "_http_attempt", lambda *a: calls.append("HTTP"))
    from ptc.sql_isolation import PilotExecutor
    monkeypatch.setattr(PilotExecutor, "run_program", lambda *a, **k: calls.append("PROGRAM"))
    monkeypatch.setattr(PilotExecutor, "score_sql", lambda *a, **k: calls.append("SCORER"))
    if change == "manifest":
        kwargs["manifest"] = dataclasses.replace(kwargs["manifest"], run_id="OTHER",
            assets=tuple(dataclasses.replace(a, ids=dataclasses.replace(a.ids, run_id="OTHER"))
                         for a in kwargs["manifest"].assets))
    elif change == "execution":
        kwargs["execution_profile"] = execution_fixture(tmp_path / "other")
    elif change == "budget_path":
        from pathlib import Path
        kwargs["budget_dir"] = tmp_path / "other-budget"
        kwargs["budget_dir"].mkdir(mode=0o700)
    elif change == "approval":
        kwargs["approval_sha256"] = "0" * 64
    elif change == "missing_profile":
        kwargs["billing_profile_path"] = tmp_path / "missing"
    elif change == "missing_ledger":
        kwargs["budget_dir"] = tmp_path / "missing"
    else:
        kwargs["allow_model_requests"] = False
    with pytest.raises((ValueError, TypeError, OSError, m.FinancialBlocked)):
        m.PilotAPI(**kwargs)
    assert calls == []


def open_descriptors():
    import os
    result = {}
    for value in os.listdir("/dev/fd"):
        try:
            info = os.fstat(int(value))
            result[value] = (info.st_mode, info.st_dev, info.st_ino, info.st_rdev)
        except OSError:
            pass  # /dev/fd enumeration's own descriptor has already closed.
    return result


def loopback_server(handler):
    import http.server
    import socketserver
    class Server(http.server.HTTPServer):
        def server_bind(self):
            # HTTPServer's cosmetic reverse-DNS lookup opens a process-global
            # Darwin mDNSResponder socket. No DNS is needed for this fixture.
            socketserver.TCPServer.server_bind(self)
            self.server_name = "TEST_ONLY"
            self.server_port = self.server_address[1]
    return Server(("127.0.0.1", 0), handler)


def test_actual_httpx_loopback_sdk_one_attempt_no_redirect_or_retry():
    m = api()
    import http.server
    import threading
    descriptors = open_descriptors()
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path, body, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header("Location", "/must-not-follow")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
        def log_message(self, *args):
            pass
    server = loopback_server(Handler)
    thread = threading.Thread(target=server.serve_forever, name="TEST_ONLY-httpx-loopback")
    thread.start()
    try:
        with m.absolute_deadline(3):
            status, raw = m._httpx_post("http://127.0.0.1:" + str(server.server_port) + "/fixture",
                                      b'{"TEST_ONLY":true}', "TEST_ONLY_SYNTHETIC_CREDENTIAL")
        assert status == 302 and raw == b"{}"
        assert calls == [("/fixture", b'{"TEST_ONLY":true}', "Bearer TEST_ONLY_SYNTHETIC_CREDENTIAL")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert open_descriptors() == descriptors


def test_context_exact_utf8_bound_and_plus_one():
    m = api()
    initial = json.loads(m.build_request("opaque", {"question": "", "library": []}))
    size = len(m.canonical_bytes({name: initial[name] for name in ("messages", "tools")}))
    payload = {"question": "α" * ((m.MAX_CONTEXT_BYTES - size) // 2), "library": []}
    remaining = m.MAX_CONTEXT_BYTES - len(m.canonical_bytes({
        name: json.loads(m.build_request("opaque", payload))[name] for name in ("messages", "tools")}))
    payload["question"] += "a" * remaining
    request = json.loads(m.build_request("opaque", payload))
    assert len(m.canonical_bytes({name: request[name] for name in ("messages", "tools")})) == 131072
    payload["question"] += "a"
    with pytest.raises(ValueError, match="131072"):
        m.build_request("opaque", payload)


def pytest_addoption(parser):
    parser.addoption("--pilot-mutant", default=None, help="TEST_ONLY intended guard bypass")


@pytest.fixture(autouse=True)
def intended_mutant(request, monkeypatch):
    mutation = request.config.getoption("--pilot-mutant", default=None)
    if not mutation:
        return
    m = api()
    if mutation == "claim":
        monkeypatch.setattr(m.BudgetLedger, "claim_dispatch", lambda *a: None)
    elif mutation == "authorization":
        monkeypatch.setattr(m, "authorize", lambda profile, approval_sha256, **k: m.billing_config(profile, approval_sha256))
    elif mutation == "credential":
        monkeypatch.setattr(m, "_reject_credential", lambda *a, **k: None)
    elif mutation == "protocol":
        original = m._provider_arguments
        def downgrade(raw):
            try:
                return original(raw)
            except m.ProtocolStop:
                raise m.ModelActionError("TEST_ONLY protocol downgrade") from None
        monkeypatch.setattr(m, "_provider_arguments", downgrade)
    else:
        from train import sql_skill_pilot as controller
        if mutation == "sanitization":
            original = controller.proposal_payload
            def leaking(asset, capture):
                result = original(asset, capture)
                result["raw_detail"] = capture.result.detail
                return result
            monkeypatch.setattr(controller, "proposal_payload", leaking)
        elif mutation == "denominator":
            original = controller.planned_pairs
            monkeypatch.setattr(controller, "planned_pairs", lambda ids: original(ids)[:-1])
        elif mutation == "rejection":
            original = controller.capture_result
            def discard(capture, **kwargs):
                result = original(capture, **kwargs)
                if result["failure_type"] == "MODEL_PROGRAM_REJECTED":
                    result["failure_type"] = "MODEL_NO_FINAL_SQL"
                return result
            monkeypatch.setattr(controller, "capture_result", discard)
        elif mutation == "leakage":
            original = controller.task_payload
            def leak_task(asset, **kwargs):
                result = original(asset, **kwargs)
                result["gold_sql"] = asset.task.gold_sql
                return result
            monkeypatch.setattr(controller, "task_payload", leak_task)
        elif mutation == "reference":
            original = m.parse_response
            def accept_reference(raw, *, library, **kwargs):
                obj = json.loads(raw)
                action = json.loads(obj["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
                extra = {"skill_id": action["skill_id"], "promotion_sha256": action["promotion_sha256"]}
                return original(raw, library=[*library, extra], **kwargs)
            monkeypatch.setattr(m, "parse_response", accept_reference)
        elif mutation == "actualreuse":
            original = controller.route_action
            def bypass_reuse(action, asset, *, executor, approved):
                if action.kind == "approved_skill":
                    return controller.execute_program(asset, approved.candidate.program, executor=executor), "APPROVED_REUSE"
                return original(action, asset, executor=executor, approved=approved)
            monkeypatch.setattr(controller, "route_action", bypass_reuse)
        elif mutation == "no-repair":
            original = m.PilotAPI.request
            def repair(self, request_id, payload, **kwargs):
                try:
                    return original(self, request_id, payload, **kwargs)
                except m.ModelActionError as error:
                    if payload["stage"] != "proposal":
                        raise
                    return m.ModelReply(m.PilotAction("program", "TEST_ONLY_GOOD_PROGRAM", "", ""), error.telemetry)
            monkeypatch.setattr(m.PilotAPI, "request", repair)
        elif mutation == "externalapproval":
            original = controller.validate_approval
            def ignore_pin(approved):
                return original(dataclasses.replace(approved,
                    approval_sha256=m.digest(approved.approval_path.read_bytes())))
            monkeypatch.setattr(controller, "validate_approval", ignore_pin)
        elif mutation == "continuation":
            original = controller._verify_checkpoint
            def ignore_pin(directory, path, pin, *args):
                return original(directory, path, m.digest(path.read_bytes()), *args)
            monkeypatch.setattr(controller, "_verify_checkpoint", ignore_pin)
        elif mutation == "persistence":
            original = controller._persist_endpoint_report
            def initial_only(directory, report, snapshot):
                if not (directory / "endpoint-report.json").exists():
                    original(directory, report, snapshot)
            monkeypatch.setattr(controller, "_persist_endpoint_report", initial_only)
        elif mutation == "checkpoint":
            monkeypatch.setattr(controller, "_publish_checkpoint", lambda *a: None)
        elif mutation == "endpointclaim":
            monkeypatch.setattr(controller, "_claim_endpoint", lambda *a, **kw: None)
        else:
            pytest.fail("unknown TEST_ONLY mutant")


@pytest.mark.parametrize("extra", [0, 1])
def test_httpx_actual_body_exact_cap_no_truncation(extra):
    m = api()
    import http.server
    import threading
    descriptors = open_descriptors()
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(m.MAX_BYTES + extra))
            self.end_headers()
            try:
                self.wfile.write(b"x" * (m.MAX_BYTES + extra))
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = loopback_server(Handler)
    thread = threading.Thread(target=server.serve_forever, name="TEST_ONLY-body-cap")
    thread.start()
    try:
        url = "http://127.0.0.1:" + str(server.server_port) + "/TEST_ONLY"
        with m.absolute_deadline(5):
            if extra:
                with pytest.raises(m.FinancialBlocked, match="8 MiB"):
                    m._httpx_post(url, b"{}", "TEST_ONLY_SYNTHETIC_CREDENTIAL")
            else:
                status, raw = m._httpx_post(url, b"{}", "TEST_ONLY_SYNTHETIC_CREDENTIAL")
                assert status == 200 and len(raw) == 8388608
        assert calls == ["/TEST_ONLY"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert open_descriptors() == descriptors


def test_httpx_actual_slow_drip_hits_absolute_deadline():
    m = api()
    import http.server
    import threading
    descriptors = open_descriptors()
    stopped = threading.Event()
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            try:
                for _ in range(1000):
                    if stopped.wait(0.01):
                        break
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = loopback_server(Handler)
    thread = threading.Thread(target=server.serve_forever, name="TEST_ONLY-slow-drip")
    thread.start()
    started = time.monotonic()
    try:
        with pytest.raises(m.FinancialBlocked, match="absolute request deadline"):
            with m.absolute_deadline(0.15):
                m._httpx_post("http://127.0.0.1:" + str(server.server_port) + "/TEST_ONLY",
                              b"{}", "TEST_ONLY_SYNTHETIC_CREDENTIAL")
        assert time.monotonic() - started < 1
        assert calls == ["/TEST_ONLY"]
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert open_descriptors() == descriptors


@pytest.mark.parametrize("field,bad", [
    ("valid_from", True), ("valid_until", 1), ("settlement_mode", "upper_bound"),
    ("evidence", []), ("charges", []), ("receipt_directory", "../receipts"),
    ("authorization", {}), ("model", 1), ("provider", ""),
])
def test_profile_rehashed_invalid_nested_fields_reject(tmp_path, field, bad):
    m, profile, _, _ = profile_fixture(tmp_path)
    payload = dataclasses.asdict(profile)
    payload[field] = bad
    # Correct self-hash does not bypass the closed typed payload.
    with pytest.raises((ValueError, TypeError)):
        m.billing_profile_from_bytes(m.envelope_bytes("sql_pilot_billing_profile", payload))


@pytest.mark.parametrize("bad", [
    b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
    b'{"x":"\\ud800"}', b"\xff",
])
def test_untrusted_json_negative_boundaries(bad):
    m = api()
    with pytest.raises((ValueError, TypeError)):
        m.strict_json(bad)


@pytest.mark.parametrize("placement", ["value", "key", "serialized", "nested_serialized"])
def test_request_credential_collision_before_persistence_and_http(tmp_path, monkeypatch, placement):
    m, _, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    credential = "TEST_ONLY\\interior\\credential"
    payload = {"library": []}
    if placement == "value":
        payload["question"] = credential
    elif placement == "key":
        payload[credential] = "x"
    elif placement == "serialized":
        payload["question"] = json.dumps({"inner": credential})
    else:
        payload["question"] = json.dumps({"inner": json.dumps({credential: "x"})})
    events = []
    def key():
        events.append(client.ledger.snapshot().requests[-1].state)
        return credential
    def transport(*args):
        events.append("HTTP")
        return 200, b"{}"
    monkeypatch.setattr(m, "_read_credential", key)
    monkeypatch.setattr(m, "_http_attempt", transport)
    with pytest.raises(m.FinancialBlocked):
        client.request("TEST_ONLY:collision:1", payload, library=[])
    assert events == ["dispatch_claimed"]
    assert list(kwargs["output_dir"].iterdir()) == []
    assert client.ledger.snapshot().reserved_charge_micros == 24


@pytest.mark.parametrize("placement", ["key", "value", "arguments", "nested_arguments", "malformed"])
def test_escaped_response_credential_never_persisted(tmp_path, monkeypatch, placement):
    m, _, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    credential = "TEST_ONLY\\interior\\credential"
    value = json.loads(response(json.dumps(dict(kind="program", program="safe", skill_id="", promotion_sha256=""))))
    if placement == "key":
        value[credential] = "echo"
    elif placement == "value":
        value["echo"] = credential
    elif placement == "arguments":
        value["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps({"echo": credential})
    elif placement == "nested_arguments":
        value["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
            {"echo": json.dumps({credential: "x"})})
    raw = b'{"bad":' + json.dumps(credential).encode() if placement == "malformed" else json.dumps(value).encode()
    monkeypatch.setattr(m, "_read_credential", lambda: credential)
    monkeypatch.setattr(m, "_http_attempt", lambda *a: (200, raw))
    with pytest.raises(m.FinancialBlocked):
        client.request("TEST_ONLY:echo:1", {"library": []}, library=[])
    assert not list(kwargs["output_dir"].glob("*.response.json"))
    assert client.ledger.snapshot().reserved_charge_micros == 24


@pytest.mark.parametrize("raw", [b"{", b"[]", b'{"choices":{}}'])
def test_malformed_outer_provider_protocol_stops_after_honest_settlement(tmp_path, monkeypatch, raw):
    m, profile, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    request_id = "TEST_ONLY:protocol:1"
    def transport(request, key):
        receipt_for(m, profile, kwargs, request_id, request, raw)
        return 200, raw
    monkeypatch.setattr(m, "_read_credential", lambda: "TEST_ONLY_SYNTHETIC_CREDENTIAL")
    monkeypatch.setattr(m, "_http_attempt", transport)
    with pytest.raises(m.ProtocolStop):
        client.request(request_id, {"library": []}, library=[])
    assert client.ledger.snapshot().settled_charge_micros == 9
    if raw == b"{":
        assert not list(kwargs["output_dir"].glob("*.response.json"))


def test_outer_protocol_failure_is_not_model_action_failure():
    m = api()
    try:
        m.parse_response(b"{", library=[])
    except m.ModelActionError as error:
        assert type(error) is m.ProtocolStop
    else:
        pytest.fail("malformed outer provider JSON accepted")


def test_invalid_submit_arguments_remain_model_failure(tmp_path, monkeypatch):
    m, profile, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    raw = response("{")
    request_id = "TEST_ONLY:arguments:1"
    def transport(request, key):
        receipt_for(m, profile, kwargs, request_id, request, raw)
        return 200, raw
    monkeypatch.setattr(m, "_read_credential", lambda: "TEST_ONLY_SYNTHETIC_CREDENTIAL")
    monkeypatch.setattr(m, "_http_attempt", transport)
    with pytest.raises(m.ModelActionError) as error:
        client.request(request_id, {"library": []}, library=[])
    assert type(error.value) is m.ModelActionError
    assert client.ledger.snapshot().settled_charge_micros == 9


def test_safe_request_persisted_after_claim_and_credential_before_http(tmp_path, monkeypatch):
    m, profile, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    request_id = "TEST_ONLY:order:1"
    raw = response(json.dumps(dict(kind="program", program="safe", skill_id="", promotion_sha256="")))
    events = []
    original = m.write_new
    def persisted(path, data):
        original(path, data)
        if path.name.endswith(".request.json"):
            events.append("DURABLE_REQUEST")
    def key():
        events.append(client.ledger.snapshot().requests[-1].state)
        return "TEST_ONLY_SYNTHETIC_CREDENTIAL"
    def transport(request, credential):
        events.append("HTTP")
        path = kwargs["output_dir"] / (hashlib.sha256(request_id.encode()).hexdigest() + ".request.json")
        assert path.read_bytes() == request
        receipt_for(m, profile, kwargs, request_id, request, raw)
        return 200, raw
    monkeypatch.setattr(m, "write_new", persisted)
    monkeypatch.setattr(m, "_read_credential", key)
    monkeypatch.setattr(m, "_http_attempt", transport)
    client.request(request_id, {"library": []}, library=[])
    assert events == ["dispatch_claimed", "DURABLE_REQUEST", "HTTP"]


def test_credential_scan_work_uncertainty_holds_before_http(tmp_path, monkeypatch):
    m, _, kwargs = financial_world(tmp_path)
    client = m.PilotAPI(**kwargs)
    monkeypatch.setattr(m, "_CREDENTIAL_SCAN_WORK_BYTES", 1)
    monkeypatch.setattr(m, "_read_credential", lambda: "TEST_ONLY_SYNTHETIC_CREDENTIAL")
    events = []
    monkeypatch.setattr(m, "_http_attempt", lambda *a: events.append("HTTP"))
    with pytest.raises(m.FinancialBlocked, match="inspection work"):
        client.request("TEST_ONLY:scan:1", {"question": "safe", "library": []}, library=[])
    assert events == [] and list(kwargs["output_dir"].iterdir()) == []
    assert client.ledger.snapshot().reserved_charge_micros == 24
