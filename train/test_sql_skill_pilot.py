"""TEST_ONLY controller assertions, never efficacy evidence."""
import importlib

import pytest


def api():
    try:
        return importlib.import_module("train.sql_skill_pilot")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_skill_pilot":
            raise
        pytest.fail("sql_skill_pilot implementation missing", pytrace=False)


@pytest.fixture(autouse=True)
def intended_controller_mutant(request, monkeypatch):
    mutation = request.config.getoption("--controller-mutant", default=None)
    if not mutation:
        return
    m = api()
    if mutation == "dbpin":
        original = m.captures.start_capture
        def fresh_snapshot(task, **kwargs):
            kwargs.pop("expected_db_sha256", None)
            return original(task, **kwargs)
        monkeypatch.setattr(m.captures, "start_capture", fresh_snapshot)
        real_case = m.evaluator.SkillCase
        class unpinned_case(real_case):
            def __init__(self, role, task, ids, **kwargs):
                kwargs.pop("expected_db_sha256", None)
                real_case.__init__(self, role, task, ids, **kwargs)
        monkeypatch.setattr(m.evaluator, "SkillCase", unpinned_case)
    elif mutation == "returnedasset":
        monkeypatch.setattr(m, "_verify_asset_capture", lambda *a, **k: None)
    elif mutation == "responsegraph":
        monkeypatch.setattr(m, "_verify_development_capture", lambda *a, **k: None)
    elif mutation == "earlierclassification":
        def skip_classification(actual, asset, binding, *, program, record, telemetry):
            m.captures.encode_capture(actual)
            if (actual.schema_version != 2 or actual.execution_binding != binding.execution_binding
                    or actual.instrument != binding.instrument or actual.ids != asset.ids
                    or actual.task_id != asset.task.name or actual.task_fingerprint != asset.task_fingerprint
                    or actual.db_sha256 != asset.db_sha256 or len(actual.steps) != 1
                    or actual.steps[0].action != program or actual.execution_abort is not None):
                raise ValueError("development capture differs from response/manifest graph")
            if actual.terminal_label == "final_submitted":
                valid = actual.result is not None and actual.result.valid is True
            elif actual.terminal_label in ("program_rejected", "aborted"):
                valid = actual.result is None
            else:
                valid = False
            if not valid or tuple((r.role, r.request_sha256) for r in actual.runtime_receipts) != m._development_receipts(actual, asset):
                raise ValueError("development receipt context differs from dispatched requests")
        monkeypatch.setattr(m, "_verify_development_capture", skip_classification)
    elif mutation == "actioncomparison":
        def skip_action_equality(actual, asset, binding, *, program, record, telemetry):
            m.captures.encode_capture(actual)
            if (actual.schema_version != 2 or actual.execution_binding != binding.execution_binding
                    or actual.instrument != binding.instrument or actual.ids != asset.ids
                    or actual.task_id != asset.task.name or actual.task_fingerprint != asset.task_fingerprint
                    or actual.db_sha256 != asset.db_sha256 or len(actual.steps) != 1
                    or actual.execution_abort is not None):
                raise ValueError("development capture differs from response/manifest graph")
            if actual.terminal_label == "final_submitted":
                if actual.result is None or actual.result.valid is not True:
                    raise ValueError("graded development capture requires a valid protected result")
            elif actual.terminal_label in ("program_rejected", "aborted"):
                if actual.result is not None:
                    raise ValueError("unscored development capture carries a result")
            else:
                raise ValueError("unsupported development terminal state")
            if tuple((r.role, r.request_sha256) for r in actual.runtime_receipts) != m._development_receipts(actual, asset):
                raise ValueError("development receipt context differs from dispatched requests")
            expected = m.capture_result(actual, route="DIRECT")
            if (record["failure_type"] != expected["failure_type"] or record["score"] != expected["score"]
                    or record["route"] != "DIRECT" or record["telemetry"] != telemetry):
                raise ValueError("development report classification differs from capture")
        monkeypatch.setattr(m, "_verify_development_capture", skip_action_equality)
    else:
        pytest.fail("unknown TEST_ONLY controller mutant")


def test_all_planned_pairs_retained_with_explicit_unrun():
    m = api()
    pairs = m.planned_pairs(tuple("case-" + str(i) for i in range(8)))
    assert len(pairs) == 8
    assert all(set(pair) == {"case_id", "B", "L"} for pair in pairs)
    assert all(pair[arm]["failure_type"] == "UNRUN" for pair in pairs for arm in ("B", "L"))
    summary = m.summarize_pairs(pairs)
    assert summary["denominator"] == 8
    assert summary["complete"] is False
    assert summary["dollar_benefit"] is None


@pytest.mark.parametrize("execution,model", [(False, False), (True, False), (False, True), (1, True), (True, 1)])
def test_independent_optins_fail_before_data_or_credentials(execution, model):
    m = api()
    with pytest.raises(ValueError, match="both"):
        m.require_optins(execution, model)


def test_sanitized_proposal_projection_no_detail_or_gold(tmp_path):
    m = api()
    from types import SimpleNamespace
    from train.sql_episodes import ActionObservation
    asset = SimpleNamespace(task=SimpleNamespace(question="question", gold_sql="GOLD_CANARY"))
    capture = SimpleNamespace(schema="schema", steps=(
        ActionObservation("attempt", "observation"),),
        result=SimpleNamespace(valid=True, score=0, detail="DETAIL_CANARY"),
        terminal_label="final_submitted", execution_abort=None)
    payload = m.proposal_payload(asset, capture)
    assert set(payload) == {"stage", "question", "schema", "attempt", "observation", "valid_zero", "library"}
    assert payload["valid_zero"] is True and payload["library"] == []
    assert "CANARY" not in str(payload)


def test_model_rejection_and_infra_are_distinct():
    m = api()
    from types import SimpleNamespace
    rejected = SimpleNamespace(terminal_label="program_rejected", execution_abort=None, result=None)
    abort = SimpleNamespace(terminal_label="execution_aborted",
                            execution_abort=SimpleNamespace(stage="program", reason="memory"), result=None)
    assert m.capture_result(rejected, route="DIRECT")["failure_type"] == "MODEL_PROGRAM_REJECTED"
    assert m.capture_result(abort, route="DIRECT")["failure_type"] == "INFRA_PROGRAM_MEMORY"
    pairs = m.planned_pairs(tuple(str(i) for i in range(8)))
    for pair in pairs:
        pair["B"] = m.capture_result(rejected, route="DIRECT")
        pair["L"] = m.capture_result(rejected, route="DIRECT")
    summary = m.summarize_pairs(pairs)
    assert summary["complete"] is True
    assert summary["B"]["accuracy"] == 0 and summary["B"]["failures"] == 8


def controller_world(tmp_path, monkeypatch, *, mode="complete", maximum=None):
    """Concrete executor with patched methods, real capture/promotion/ledger APIs.

    No model Python/SQL executes. Fixed fixture outcomes are NOT model results.
    """
    import json
    from bench.score import ExResult
    from ptc import sql_isolation as isolation
    from train import sql_episodes
    from train.test_sql_pilot_api import financial_world, receipt_for, response
    transport, profile, kwargs = financial_world(tmp_path, maximum=maximum)
    manifest = kwargs["manifest"]
    by_path = {a.task.db_path: a for a in manifest.assets}
    events = {"http": [], "program": [], "scorer": [], "reuse": []}
    def runtime_receipt(role, request):
        return isolation.RuntimeReceipt(role, isolation.request_sha256(request),
            "TEST_ONLY-python", "TEST_ONLY-sqlite", "d" * 64, "e" * 64)
    def program(self, code, *, db_path, db_sha256, max_rows):
        asset = by_path[db_path]
        events["program"].append((asset.case_id, code))
        request = isolation.ProgramRequest(code, max_rows, db_sha256)
        force = events.pop("force_next", None)
        if code == "TEST_ONLY_REJECT" or force == "reject":
            return isolation.ProgramOutcome("FINAL_SQL:SELECT -1\nTEST_ONLY_REJECTED", None,
                                             runtime_receipt("program", request), rejected=True)
        if mode == "third_qualification_abort" and asset == manifest.assets[10]:
            return isolation.ProgramOutcome(None, isolation.AbortInfo("program", "memory"), None)
        if code == "TEST_ONLY_ABORT" or force == "abort":
            return isolation.ProgramOutcome(None, isolation.AbortInfo("program", "memory"), None)
        if code == "TEST_ONLY_NO_FINAL":
            return isolation.ProgramOutcome("TEST_ONLY no final", None, runtime_receipt("program", request))
        sql = asset.task.gold_sql if code.split(" #", 1)[0].rstrip("\n") == "TEST_ONLY_GOOD_PROGRAM" else "SELECT -1"
        return isolation.ProgramOutcome("FINAL_SQL:" + sql, None, runtime_receipt("program", request))
    def score(self, predicted_sql, task, *, db_sha256, instrument):
        events["scorer"].append((task.name, predicted_sql))
        if mode == "qualification_abort" and by_path[task.db_path].partition == "qualification":
            return isolation.ScoreOutcome(None, isolation.AbortInfo("scorer", "memory"), None)
        correct = predicted_sql == task.gold_sql
        from dataclasses import replace
        request = isolation.ScoreRequest(replace(task, db_path="/db.sqlite"), predicted_sql,
            instrument.scorer_timeout_s, instrument.scorer_max_rows, instrument.compare, db_sha256)
        return isolation.ScoreOutcome(
            ExResult(float(correct), "match" if correct else "mismatch", True, "DETAIL_CANARY", 1, 1),
            None, runtime_receipt("scorer", request))
    monkeypatch.setattr(isolation.PilotExecutor, "run_program", program)
    monkeypatch.setattr(isolation.PilotExecutor, "score_sql", score)
    def forbidden(*args, **kwargs):
        pytest.fail("HOST SCORE FALLBACK", pytrace=False)
    monkeypatch.setattr(sql_episodes, "_score", forbidden)
    controller = api()
    real_reuse = controller.evaluator.reuse_promoted
    def reuse(*args, **kw):
        events["reuse"].append(args[2].task.name)
        return real_reuse(*args, **kw)
    monkeypatch.setattr(controller.evaluator, "reuse_promoted", reuse)
    monkeypatch.setattr(transport, "_read_credential", lambda: "TEST_ONLY_SYNTHETIC_CREDENTIAL")
    def http(request, key):
        body = json.loads(request)
        payload = json.loads(body["messages"][1]["content"])
        stage = payload["stage"]
        events["http"].append((stage, payload, body))
        count = len(events["http"])
        program_code = "TEST_ONLY_GOOD_PROGRAM"
        if stage == "development":
            if mode != "no_origin" and (mode != "late_origin" or count == 8):
                program_code = "TEST_ONLY_BAD_PROGRAM"
            if mode == "dev_rejection":
                program_code = "TEST_ONLY_REJECT"
            if mode.startswith("prefix_") and count == 1:
                program_code = {"prefix_graded": "TEST_ONLY_GOOD_PROGRAM",
                                "prefix_rejected": "TEST_ONLY_REJECT",
                                "prefix_no_final": "TEST_ONLY_NO_FINAL"}.get(mode, program_code)
        elif stage == "proposal":
            if mode == "unqualified":
                program_code = "TEST_ONLY_BAD_PROGRAM"
        elif stage == "endpoint":
            if mode == "endpoint_rejection" and len([x for x in events["http"] if x[0] == "endpoint"]) == 1:
                program_code = "TEST_ONLY_REJECT"
            if mode == "endpoint_abort":
                program_code = "TEST_ONLY_ABORT"
            if payload["library"] and mode in ("approved_rejection", "approved_abort"):
                events["force_next"] = "reject" if mode == "approved_rejection" else "abort"
        action = dict(kind="program", program=program_code, skill_id="", promotion_sha256="")
        if stage == "endpoint" and payload["library"]:
            if mode != "direct_identical":
                entry = payload["library"][0]
                action.update(kind="approved_skill", program="", skill_id=entry["skill_id"],
                              promotion_sha256=entry["promotion_sha256"])
        if stage == "proposal" and mode == "invalid_proposal":
            action = {}
        if stage == "development" and mode == "invalid_development":
            action = {}
        if stage == "development" and mode in ("prefix_invalid", "prefix_protocol") and count == 1:
            action = {}
        if stage == "endpoint" and mode == "invalid_reference":
            action.update(kind="approved_skill", program="", skill_id="unknown", promotion_sha256="0" * 64)
        raw = response(json.dumps(action))
        if stage == "endpoint" and mode == "unsupported_protocol":
            raw = b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"unsupported"}}]}'
        if stage == "endpoint" and mode == "malformed_outer":
            raw = b"{"
        if stage == "development" and mode == "prefix_protocol" and count == 1:
            raw = b'{"choices":[]}'
        if stage == "development":
            request_id = manifest.run_id + ":development:" + manifest.assets[count - 1].case_id
        elif stage == "proposal":
            request_id = manifest.run_id + ":proposal:one"
        else:
            asset = next(a for a in manifest.assets[12:] if a.task.question == payload["question"])
            request_id = manifest.run_id + ":endpoint:" + asset.case_id + ":" + ("L" if payload["library"] else "B")
        if not (stage == "endpoint" and mode == "missing_receipt"):
            receipt_for(transport, profile, kwargs, request_id, request, raw)
        return 200, raw
    monkeypatch.setattr(transport, "_http_attempt", http)
    return controller, kwargs, events


@pytest.mark.parametrize("mode,expected_requests", [("complete", 18), ("late_origin", 25), ("direct_identical", 18)])
def test_real_record_graph_with_fixture_methods_and_all_pairs(tmp_path, monkeypatch, mode, expected_requests):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode=mode)
    report = finish_fixture_run(m, kwargs)
    assert report["status"] == "COMPLETE"
    assert report["request_count"] == expected_requests
    assert len(events["http"]) == expected_requests
    assert report["model_results_claim"] is False
    assert len(report["pairs"]) == 8 and report["summary"]["denominator"] == 8
    assert len(report["qualification"]) == 4
    assert report["summary"]["B"]["accuracy"] == 1
    expected_reuse = 0 if mode == "direct_identical" else 8
    assert len(events["reuse"]) == expected_reuse
    assert report["summary"]["L"]["approved_reuse_invocations"] == expected_reuse
    assert all(stage != "qualification" for stage, _, _ in events["http"])
    manifest = kwargs["manifest"]
    for stage, payload, body in events["http"]:
        serialized = m.canonical_bytes(payload)
        assert b"DETAIL_CANARY" not in serialized
        assert b"TEST_ONLY_SYNTHETIC_CREDENTIAL" not in serialized
        assert len(body["messages"]) == 2
        if stage in ("development", "proposal"):
            for other in manifest.assets[8:]:
                assert other.task.question.encode() not in serialized
                assert other.task.gold_sql.encode() not in serialized
        if payload["library"]:
            assert set(payload["library"][0]) == {"skill_id", "promotion_sha256", "scope", "description", "program"}
            assert payload["library"][0]["description"] == m.DESCRIPTION
    endpoint = [payload for stage, payload, _ in events["http"] if stage == "endpoint"]
    assert ["L" if endpoint[i]["library"] else "B" for i in range(0, 16, 2)] == list(manifest.pair_first)
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    assert (directory / "candidate.json").is_file()
    assert (directory / "promotion.json").is_file()
    assert not (directory / "promotion-approval.json").exists()
    assert (kwargs["output_dir"].parent / "TEST_ONLY-external-approval.json").is_file()
    assert (directory / "report.json").is_file()
    assert report["economics"]["total_economics"] is None
    assert report["summary"]["dollar_benefit"] is None


@pytest.mark.parametrize("mode,status,count", [
    ("no_origin", "STOPPED_NO_ORIGIN", 8),
    ("invalid_proposal", "STOPPED_PROPOSAL", 2),
    ("unqualified", "STOPPED_UNQUALIFIED", 2),
    ("endpoint_rejection", "COMPLETE", 18),
    ("endpoint_abort", "INCOMPLETE", 3),
    ("approved_rejection", "COMPLETE", 18),
    ("approved_abort", "INCOMPLETE", 4),
    ("dev_rejection", "STOPPED_NO_ORIGIN", 8),
    ("invalid_development", "STOPPED_NO_ORIGIN", 8),
    ("qualification_abort", "INCOMPLETE", 2),
    ("invalid_reference", "COMPLETE", 18),
    ("unsupported_protocol", "INCOMPLETE", 3),
    ("missing_receipt", "INCOMPLETE", 3),
])
def test_stops_no_manufactured_origin_repair_or_dropped_pair(tmp_path, monkeypatch, mode, status, count):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode=mode)
    report = m.run_pilot(**kwargs)
    if mode in {"endpoint_rejection", "endpoint_abort", "approved_rejection", "approved_abort",
                "invalid_reference", "unsupported_protocol", "missing_receipt"}:
        if report["status"] == "AWAITING_PROMOTION_APPROVAL":
            report = m.continue_pilot(**external_continuation(m, kwargs))
    assert report["status"] == status
    assert report["request_count"] == count
    assert len(events["http"]) == count
    assert len(report["pairs"]) == 8
    assert report["summary"]["denominator"] == 8
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    if mode in ("no_origin", "invalid_proposal", "dev_rejection", "invalid_development"):
        assert not (directory / "candidate.json").exists()
        assert not (directory / "promotion.json").exists()
    if mode == "invalid_proposal":
        assert len([x for x in events["http"] if x[0] == "proposal"]) == 1
        assert len(events["program"]) == 1
    elif mode == "endpoint_rejection":
        assert report["pairs"][0]["B"]["failure_type"] == "MODEL_PROGRAM_REJECTED"
        assert report["summary"]["B"]["successes"] == 7
        assert len(events["program"]) == 21
        assert len(events["scorer"]) == 22  # rejected stdout never scored
    elif mode == "endpoint_abort":
        assert report["pairs"][0]["B"]["failure_type"] == "INFRA_PROGRAM_MEMORY"
        assert sum(p[arm]["failure_type"] == "UNRUN" for p in report["pairs"] for arm in ("B", "L")) == 15
        assert report["summary"]["complete"] is False
    elif mode == "approved_rejection":
        assert report["summary"]["L"]["failures"] == 8
        assert report["summary"]["L"]["approved_reuse_invocations"] == 8
        assert all(pair["L"]["failure_type"] == "MODEL_PROGRAM_REJECTED" for pair in report["pairs"])
    elif mode == "approved_abort":
        assert report["pairs"][0]["L"]["failure_type"] == "INFRA_PROGRAM_MEMORY"
        assert report["pairs"][0]["L"]["route"] == "APPROVED_REUSE"
        assert report["summary"]["complete"] is False
    elif mode == "dev_rejection":
        assert len(events["program"]) == 8 and events["scorer"] == []
    elif mode == "invalid_development":
        assert events["program"] == events["scorer"] == []
    elif mode == "invalid_reference":
        assert len(events["program"]) == 5
        assert events["reuse"] == []
        assert all(pair[arm]["failure_type"] == "MODEL_ACTION_INVALID"
                   for pair in report["pairs"] for arm in ("B", "L"))
    elif mode in ("unsupported_protocol", "missing_receipt"):
        assert len(events["program"]) == 5
        assert report["pairs"][0]["B"]["failure_type"] == (
            "INFRA_PROVIDER_PROTOCOL" if mode == "unsupported_protocol" else "INFRA_MODEL_REQUEST")
        assert sum(p[arm]["failure_type"] == "UNRUN" for p in report["pairs"] for arm in ("B", "L")) == 15


def test_data_only_check_never_daemon_or_credential(tmp_path, monkeypatch):
    from train.test_sql_pilot_api import financial_world
    transport, _, kwargs = financial_world(tmp_path)
    m = api()
    def forbidden(*args, **kw):
        pytest.fail("check touched execution/provider/key", pytrace=False)
    from ptc.sql_isolation import PilotExecutor
    monkeypatch.setattr(PilotExecutor, "run_program", forbidden)
    monkeypatch.setattr(PilotExecutor, "score_sql", forbidden)
    monkeypatch.setattr(transport, "_read_credential", forbidden)
    monkeypatch.setattr(transport, "_http_attempt", forbidden)
    result = m.check(kwargs["manifest"], kwargs["execution_profile"], output_dir=kwargs["output_dir"])
    assert result["runtime"] == result["provider"] == "UNPROBED"
    assert result["model_results"] == 0


def test_task_projection_is_closed_and_never_gold(tmp_path):
    from train.sql_pilot_assets import prepare_manifest
    m = api()
    manifest = prepare_manifest(tmp_path / "assets" / "manifest.json",
                               output_dir=tmp_path / "assets", run_id="TEST_ONLY")
    payload = m.task_payload(manifest.assets[0], stage="development", library=[])
    assert set(payload) == {"stage", "question", "schema", "library"}
    assert manifest.assets[0].task.gold_sql not in str(payload)
    for asset in manifest.assets[8:]:
        assert asset.task.question not in str(payload)
        assert asset.task.gold_sql not in str(payload)


def external_continuation(m, kwargs):
    """Independent TEST_ONLY approval actor, never the authorizing controller."""
    from train import sql_skills
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    checkpoint = directory / "qualification-checkpoint.json"
    promotion_raw = (directory / "promotion.json").read_bytes()
    promotion = sql_skills.decode_promotion(promotion_raw)
    approval = kwargs["output_dir"].parent / "TEST_ONLY-external-approval.json"
    raw = m.envelope_bytes("sql_pilot_host_approval", {
        "promotion_sha256": m.digest(promotion_raw),
        "candidate_sha256": m.digest((directory / "candidate.json").read_bytes()),
        "ids": __import__("dataclasses").asdict(promotion.ids)})
    approval.write_bytes(raw)
    return dict(kwargs, checkpoint_path=checkpoint, checkpoint_sha256=m.digest(checkpoint.read_bytes()),
        promotion_approval_path=approval, promotion_approval_sha256=m.digest(raw))


def finish_fixture_run(m, kwargs):
    report = m.run_pilot(**kwargs)
    if report["status"] == "AWAITING_PROMOTION_APPROVAL":
        return m.continue_pilot(**external_continuation(m, kwargs))
    return report


def test_qualification_pauses_without_self_approval_or_heldout(tmp_path, monkeypatch):
    m, kwargs, events = controller_world(tmp_path, monkeypatch)
    report = m.run_pilot(**kwargs)
    assert report["status"] == "AWAITING_PROMOTION_APPROVAL"
    assert len(events["http"]) == 2
    assert len(events["program"]) == 5
    assert events["reuse"] == []
    assert all(pair[arm]["failure_type"] == "UNRUN" for pair in report["pairs"] for arm in ("B", "L"))
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    assert not (directory / "promotion-approval.json").exists()
    checkpoint = m.open_envelope((directory / "qualification-checkpoint.json").read_bytes(),
                                 "sql_pilot_qualification_checkpoint")
    assert set(checkpoint) == {"run_id", "run_directory", "manifest_sha256", "execution_profile_sha256",
        "billing_approval_sha256", "budget_directory", "ledger_snapshot_sha256", "request_count",
        "source_case_id", "source_capture_sha256", "candidate_sha256", "promotion_sha256",
        "promotion_ids", "artifacts"}
    assert checkpoint["request_count"] == 2
    assert checkpoint["artifacts"] == sorted(checkpoint["artifacts"], key=lambda x: x["path"])


def test_external_continuation_no_upstream_reexecution_and_immutable_phase1(tmp_path, monkeypatch):
    m, kwargs, events = controller_world(tmp_path, monkeypatch)
    report = m.run_pilot(**kwargs)
    assert report["status"] == "AWAITING_PROMOTION_APPROVAL"
    continuation = external_continuation(m, kwargs)
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    upstream_programs = list(events["program"])
    result = m.continue_pilot(**continuation)
    assert result["status"] == "COMPLETE" and result["request_count"] == 18
    assert events["program"][:len(upstream_programs)] == upstream_programs
    assert len(events["program"]) == 21
    assert len(events["reuse"]) == 8
    assert all(stage == "endpoint" for stage, _, _ in events["http"][2:])
    assert all((directory / name).read_bytes() == raw for name, raw in before.items())
    assert (directory / "endpoint-claim.json").is_file()
    assert (directory / "endpoint" / "endpoint-report.json").is_file()
    persisted = m.open_envelope((directory / "endpoint" / "endpoint-report.json").read_bytes(),
                                "sql_pilot_endpoint_report")
    assert persisted == result
    count = len(events["http"])
    with pytest.raises((ValueError, OSError)):
        m.continue_pilot(**continuation)
    assert len(events["http"]) == count


def test_third_qualification_abort_retains_ordered_three_captures(tmp_path, monkeypatch):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode="third_qualification_abort")
    result = m.run_pilot(**kwargs)
    assert result["status"] == "INCOMPLETE"
    assert len(result["qualification"]) == 3
    assert [r["score"] for r in result["qualification"]] == [1, 1, None]
    assert result["qualification"][-1]["failure_type"] == "INFRA_PROGRAM_MEMORY"
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    assert len(list(directory.glob("qualification-*.capture.json"))) == 3
    assert not (directory / "qualification-checkpoint.json").exists()
    assert len(events["http"]) == 2
    assert len(events["program"]) == 4


def prepared_continuation(tmp_path, monkeypatch):
    m, kwargs, events = controller_world(tmp_path, monkeypatch)
    result = m.run_pilot(**kwargs)
    assert result["status"] == "AWAITING_PROMOTION_APPROVAL"
    return m, external_continuation(m, kwargs), events


@pytest.mark.parametrize("change", [
    "checkpoint_pin", "approval_pin", "missing_approval", "approval_fields", "approval_candidate",
    "approval_inside", "candidate", "source_capture", "qualification", "planned", "report",
    "request", "ledger", "budget_dir", "billing_pin", "execution_profile", "run_path",
    "checkpoint_fields", "checkpoint_source", "checkpoint_bool", "artifact_order",
    "artifact_duplicate", "artifact_traversal", "artifact_symlink", "artifact_hardlink",
    "approval_ids", "approval_promotion", "approval_malformed", "missing_checkpoint",
    "checkpoint_location", "billing_profile", "manifest", "current_observer",
])
def test_continuation_rejects_changed_authority_and_graph_before_activity(tmp_path, monkeypatch, change):
    import dataclasses
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    checkpoint = kwargs["checkpoint_path"]
    if change == "checkpoint_pin":
        kwargs["checkpoint_sha256"] = "0" * 64
    elif change == "approval_pin":
        kwargs["promotion_approval_sha256"] = "0" * 64
    elif change == "missing_approval":
        kwargs["promotion_approval_path"] = tmp_path / "missing"
    elif change in ("approval_fields", "approval_candidate", "approval_ids", "approval_promotion", "approval_malformed"):
        path = kwargs["promotion_approval_path"]
        value = m.open_envelope(path.read_bytes(), "sql_pilot_host_approval")
        if change == "approval_ids":
            value["ids"]["episode_id"] = "TEST_ONLY-other"
        elif change == "approval_malformed":
            path.write_bytes(b"{")
            kwargs["promotion_approval_sha256"] = m.digest(path.read_bytes())
        else:
            field = {"approval_fields": "extra", "approval_candidate": "candidate_sha256",
                     "approval_promotion": "promotion_sha256"}[change]
            value[field] = "0" * 64
        if change != "approval_malformed":
            path.write_bytes(m.envelope_bytes("sql_pilot_host_approval", value))
            kwargs["promotion_approval_sha256"] = m.digest(path.read_bytes())
    elif change == "approval_inside":
        inside = directory / "TEST_ONLY-unapproved-location.json"
        inside.write_bytes(kwargs["promotion_approval_path"].read_bytes())
        kwargs["promotion_approval_path"] = inside
    elif change in ("candidate", "source_capture", "qualification", "planned", "report", "request"):
        name = {"candidate": "candidate.json", "source_capture": "development-rowcount-01.capture.json",
                "qualification": "qualification-0.capture.json", "planned": "planned.json",
                "report": "report.json"}.get(change)
        path = directory / name if name else next(directory.glob("*.request.json"))
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "ledger":
        from train.sql_pilot_budget import BudgetLedger
        snapshot_profile = m.load_billing_profile(kwargs["billing_profile_path"], approval_sha256=kwargs["approval_sha256"])
        from train.sql_pilot_api import billing_config
        ledger = BudgetLedger.open(str(kwargs["budget_dir"]), billing_config(snapshot_profile, kwargs["approval_sha256"]))
        ledger.reserve("TEST_ONLY:outside:1", 24)
    elif change == "budget_dir":
        kwargs["budget_dir"] = tmp_path / "other-budget"
    elif change == "billing_pin":
        kwargs["approval_sha256"] = "0" * 64
    elif change == "billing_profile":
        path = kwargs["billing_profile_path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "manifest":
        manifest = kwargs["manifest"]
        kwargs["manifest"] = dataclasses.replace(manifest, run_id="OTHER",
            assets=tuple(dataclasses.replace(a, ids=dataclasses.replace(a.ids, run_id="OTHER"))
                         for a in manifest.assets))
    elif change == "current_observer":
        (tmp_path / "TEST_ONLY-observer").write_bytes(b"TEST_ONLY-stale-observer")
    elif change == "execution_profile":
        from train.test_sql_pilot_api import execution_fixture
        kwargs["execution_profile"] = execution_fixture(tmp_path / "other-profile")
    elif change == "run_path":
        kwargs["output_dir"] = tmp_path / "other-output"
        kwargs["output_dir"].mkdir()
    elif change == "missing_checkpoint":
        kwargs["checkpoint_path"] = tmp_path / "missing-checkpoint"
    elif change == "checkpoint_location":
        kwargs["checkpoint_path"] = tmp_path / "copied-checkpoint.json"
        kwargs["checkpoint_path"].write_bytes(checkpoint.read_bytes())
    elif change in ("artifact_symlink", "artifact_hardlink"):
        path = directory / "candidate.json"
        if change == "artifact_symlink":
            saved = directory / "TEST_ONLY-original-candidate"
            path.rename(saved)
            path.symlink_to(saved)
        else:
            (tmp_path / "TEST_ONLY-linked-candidate").hardlink_to(path)
    else:
        value = m.open_envelope(checkpoint.read_bytes(), "sql_pilot_qualification_checkpoint")
        if change == "checkpoint_fields":
            value["extra"] = 1
        elif change == "checkpoint_source":
            value["source_case_id"] = "rowcount-02"
        elif change == "checkpoint_bool":
            value["request_count"] = True
        elif change == "artifact_order":
            value["artifacts"].reverse()
        elif change == "artifact_duplicate":
            value["artifacts"].append(value["artifacts"][0])
        else:
            value["artifacts"][0]["path"] = "../candidate.json"
        checkpoint.write_bytes(m.envelope_bytes("sql_pilot_qualification_checkpoint", value))
        kwargs["checkpoint_sha256"] = m.digest(checkpoint.read_bytes())
    calls = []
    from train import sql_pilot_api
    def constructor(*a, **kw):
        calls.append("CONSTRUCT")
        raise AssertionError("continuation admitted invalid authority")
    monkeypatch.setattr(m.PilotAPI, "__init__", constructor)
    monkeypatch.setattr(m.PilotExecutor, "__init__", constructor)
    monkeypatch.setattr(sql_pilot_api, "_read_credential", lambda: calls.append("KEY"))
    before = {key: len(events[key]) for key in ("http", "program", "scorer", "reuse")}
    with pytest.raises((ValueError, TypeError, OSError, m.FinancialBlocked)):
        m.continue_pilot(**kwargs)
    assert calls == []
    assert {key: len(events[key]) for key in before} == before
    assert not (directory / "endpoint-claim.json").exists()


@pytest.mark.parametrize("maximum,awaiting", [(3_124_998, True), (3_124_999, False)])
def test_phase_boundary_requires_sixteen_maximum_charge_reservations(tmp_path, monkeypatch, maximum, awaiting):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, maximum=maximum)
    result = m.run_pilot(**kwargs)
    assert (result["status"] == "AWAITING_PROMOTION_APPROVAL") is awaiting
    checkpoint = kwargs["output_dir"] / "pilot-TEST_ONLY" / "qualification-checkpoint.json"
    assert checkpoint.exists() is awaiting
    assert len(events["http"]) == 2 and events["reuse"] == []


def test_checkpoint_published_last_after_fsynced_phase_one_report(tmp_path, monkeypatch):
    m, kwargs, _ = controller_world(tmp_path, monkeypatch)
    original = m.write_new
    writes = []
    def write(path, raw):
        original(path, raw)
        writes.append(path.name)
    monkeypatch.setattr(m, "write_new", write)
    result = m.run_pilot(**kwargs)
    assert result["status"] == "AWAITING_PROMOTION_APPROVAL"
    assert writes[-2:] == ["report.json", "qualification-checkpoint.json"]
    assert "promotion-approval.json" not in writes


def test_malformed_outer_endpoint_stops_with_all_unrun_slots_retained(tmp_path, monkeypatch):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode="malformed_outer")
    result = finish_fixture_run(m, kwargs)
    assert result["status"] == "INCOMPLETE"
    assert len(events["http"]) == 3
    assert result["pairs"][0]["B"]["failure_type"] == "INFRA_PROVIDER_PROTOCOL"
    assert sum(p[arm]["failure_type"] == "UNRUN" for p in result["pairs"] for arm in ("B", "L")) == 15


def read_actor_bytes(fd, count, timeout=20):
    import os
    import select
    import time
    deadline = time.monotonic() + timeout
    result = b""
    while len(result) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            pytest.fail("owned fixture actor timed out")
        block = os.read(fd, count - len(result))
        if not block:
            pytest.fail("owned fixture actor closed without result")
        result += block
    return result


def wait_actor(pid, timeout=5):
    import os
    import time
    deadline = time.monotonic() + timeout
    while True:
        found, status = os.waitpid(pid, os.WNOHANG)
        if found:
            return found, status
        if time.monotonic() >= deadline:
            pytest.fail("owned fixture actor did not reap within five seconds")
        time.sleep(0.01)


def reap_actors(pending):
    import os
    import signal
    for pid in tuple(pending):
        found, _ = os.waitpid(pid, os.WNOHANG)
        if not found:
            os.kill(pid, signal.SIGKILL)
            wait_actor(pid)
        pending.remove(pid)


def test_eight_real_processes_at_most_one_durable_endpoint_claim(tmp_path, monkeypatch, record_property):
    import os
    from train.test_sql_pilot_api import open_descriptors
    descriptors = open_descriptors()
    m, kwargs, _ = prepared_continuation(tmp_path, monkeypatch)
    class Claimed(RuntimeError):
        pass
    def no_endpoint_constructor(*args, **kw):
        raise Claimed
    monkeypatch.setattr(m.PilotAPI, "__init__", no_endpoint_constructor)
    start_r, start_w = os.pipe()
    result_r, result_w = os.pipe()
    pending = set()
    try:
        for _ in range(8):
            pid = os.fork()
            if pid == 0:
                try:
                    os.close(start_w)
                    os.close(result_r)
                    os.read(start_r, 1)
                    try:
                        m.continue_pilot(**kwargs)
                    except Claimed:
                        outcome = b"C"
                    except (ValueError, FileExistsError):
                        outcome = b"R"
                    except BaseException:
                        outcome = b"E"
                    else:
                        outcome = b"E"
                    os.write(result_w, outcome)
                finally:
                    os._exit(0)
            pending.add(pid)
        os.write(start_w, b"x" * 8)
        outcomes = read_actor_bytes(result_r, 8)
        assert sorted(outcomes) == sorted(b"CRRRRRRR")
        actors = sorted(pending)
        for pid in tuple(pending):
            found, status = wait_actor(pid)
            pending.remove(pid)
            assert found == pid and os.waitstatus_to_exitcode(status) == 0
        directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
        assert (directory / "endpoint-claim.json").is_file()
        claim_raw = (directory / "endpoint-claim.json").read_bytes()
        claim = m.open_envelope(claim_raw, "sql_pilot_endpoint_claim")
        assert set(claim) == {"checkpoint_sha256", "promotion_approval_sha256", "ledger_snapshot_sha256", "request_ids"}
        assert claim["request_ids"] == m._endpoint_request_ids(kwargs["manifest"])
        assert len(claim["request_ids"]) == 16
        with pytest.raises(ValueError, match="claimed"):
            m.continue_pilot(**kwargs)
        assert (directory / "endpoint-claim.json").read_bytes() == claim_raw
    finally:
        reap_actors(pending)
        for fd in (start_r, start_w, result_r, result_w):
            os.close(fd)
    assert pending == set() and open_descriptors() == descriptors
    record_actor_evidence(record_property, actors, descriptors)


def test_real_sigkill_after_endpoint_claim_denies_replay(tmp_path, monkeypatch, record_property):
    import os
    import signal
    from train.test_sql_pilot_api import open_descriptors
    descriptors = open_descriptors()
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    ack_r, ack_w = os.pipe()
    block_r, block_w = os.pipe()
    def pause_after_claim(*args, **kw):
        os.write(ack_w, b"C")
        os.read(block_r, 1)
        raise AssertionError("owned actor unexpectedly resumed")
    monkeypatch.setattr(m.PilotAPI, "__init__", pause_after_claim)
    pid = os.fork()
    if pid == 0:
        try:
            m.continue_pilot(**kwargs)
        finally:
            os._exit(1)
    pending = {pid}
    try:
        assert read_actor_bytes(ack_r, 1) == b"C"
        directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
        before = (directory / "endpoint-claim.json").read_bytes()
        os.kill(pid, signal.SIGKILL)
        found, status = wait_actor(pid)
        pending.remove(pid)
        assert found == pid and os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
        with pytest.raises(ValueError, match="claimed"):
            m.continue_pilot(**kwargs)
        assert (directory / "endpoint-claim.json").read_bytes() == before
        assert len(events["http"]) == 2
        planned = m.open_envelope((directory / "planned.json").read_bytes(), "sql_pilot_planned")
        assert len(planned["pairs"]) == 8
        assert all(pair[arm]["failure_type"] == "UNRUN" for pair in planned["pairs"] for arm in ("B", "L"))
        endpoint = m.open_envelope((directory / "endpoint" / "endpoint-report.json").read_bytes(),
                                  "sql_pilot_endpoint_report")
        assert endpoint["status"] == "INCOMPLETE" and len(endpoint["pairs"]) == 8
        assert all(pair[arm]["failure_type"] == "UNRUN" for pair in endpoint["pairs"] for arm in ("B", "L"))
    finally:
        reap_actors(pending)
        for fd in (ack_r, ack_w, block_r, block_w):
            os.close(fd)
    assert pending == set() and open_descriptors() == descriptors
    record_actor_evidence(record_property, [pid], descriptors)


def test_real_sigkill_after_financial_dispatch_keeps_reservation_and_zero_replay(tmp_path, monkeypatch, record_property):
    import os
    import signal
    from train.test_sql_pilot_api import financial_world, open_descriptors
    descriptors = open_descriptors()
    transport, _, kwargs = financial_world(tmp_path)
    client = transport.PilotAPI(**kwargs)
    ack_r, ack_w = os.pipe()
    block_r, block_w = os.pipe()
    monkeypatch.setattr(transport, "_read_credential", lambda: "TEST_ONLY_SYNTHETIC_CREDENTIAL")
    def pause_dispatch(*args):
        os.write(ack_w, b"C")
        os.read(block_r, 1)
        raise AssertionError("owned financial actor unexpectedly resumed")
    monkeypatch.setattr(transport, "_http_attempt", pause_dispatch)
    pid = os.fork()
    if pid == 0:
        try:
            client.request("TEST_ONLY:killed:1", {"library": []}, library=[])
        finally:
            os._exit(1)
    pending = {pid}
    try:
        assert read_actor_bytes(ack_r, 1) == b"C"
        snapshot = client.ledger.snapshot()
        assert snapshot.requests[-1].state == "dispatch_claimed"
        assert snapshot.reserved_charge_micros == 24
        os.kill(pid, signal.SIGKILL)
        found, status = wait_actor(pid)
        pending.remove(pid)
        assert found == pid and os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
        with pytest.raises(transport.FinancialBlocked, match="unsettled"):
            transport.PilotAPI(**kwargs)
        assert client.ledger.snapshot() == snapshot
    finally:
        reap_actors(pending)
        for fd in (ack_r, ack_w, block_r, block_w):
            os.close(fd)
    assert pending == set() and open_descriptors() == descriptors
    record_actor_evidence(record_property, [pid], descriptors)


def record_actor_evidence(record_property, pids, descriptors):
    import json
    import os
    from train.test_sql_pilot_api import open_descriptors
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    record_property("reaped_owned_pids", json.dumps(pids))
    record_property("fd_identities_before", json.dumps(descriptors, sort_keys=True))
    record_property("fd_identities_after", json.dumps(open_descriptors(), sort_keys=True))


def test_rehashed_candidate_scope_still_requires_actual_source_scope(tmp_path, monkeypatch):
    import dataclasses
    from train import sql_skills
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    candidate = sql_skills.decode_candidate((directory / "candidate.json").read_bytes())
    changed = dataclasses.replace(candidate, scope=dataclasses.replace(candidate.scope, shape="TEST_ONLY-unqualified"))
    candidate_raw = sql_skills.encode_candidate(changed)
    (directory / "candidate.json").write_bytes(candidate_raw)
    promotion = sql_skills.decode_promotion((directory / "promotion.json").read_bytes())
    promotion_raw = sql_skills.encode_promotion(dataclasses.replace(promotion,
        candidate_sha256=m.digest(candidate_raw), scope=changed.scope))
    (directory / "promotion.json").write_bytes(promotion_raw)
    value = m.open_envelope(kwargs["checkpoint_path"].read_bytes(), "sql_pilot_qualification_checkpoint")
    value["candidate_sha256"] = m.digest(candidate_raw)
    value["promotion_sha256"] = m.digest(promotion_raw)
    for pin in value["artifacts"]:
        pin["sha256"] = m.digest((directory / pin["path"]).read_bytes())
    kwargs["checkpoint_path"].write_bytes(m.envelope_bytes("sql_pilot_qualification_checkpoint", value))
    base = {key: kwargs[key] for key in ("manifest", "execution_profile", "output_dir",
        "billing_profile_path", "approval_sha256", "budget_dir", "allow_execution", "allow_model_requests")}
    continuation = external_continuation(m, base)
    calls = []
    def constructor(*a, **kw):
        calls.append("CONSTRUCT")
        raise AssertionError("incoherent scope admitted")
    monkeypatch.setattr(m.PilotAPI, "__init__", constructor)
    monkeypatch.setattr(m.PilotExecutor, "__init__", constructor)
    with pytest.raises(ValueError, match="source/candidate"):
        m.continue_pilot(**continuation)
    assert calls == [] and len(events["http"]) == 2


@pytest.mark.parametrize("count,allowed", [(0, False), (1, False), (2, True), (9, True), (10, False)])
def test_checkpoint_requires_two_to_nine_settled_requests_and_sixteen_slots(tmp_path, count, allowed):
    from train.test_sql_pilot_api import financial_world
    from train.sql_pilot_api import billing_config
    from train.sql_pilot_budget import BudgetLedger
    transport, profile, kwargs = financial_world(tmp_path)
    ledger = BudgetLedger.open(str(kwargs["budget_dir"]), billing_config(profile, kwargs["approval_sha256"]))
    for i in range(count):
        request_id = "TEST_ONLY:capacity:" + str(i)
        ledger.reserve(request_id, 24)
        ledger.claim_dispatch(request_id)
        ledger.settle(request_id, 9, "f" * 64)
    snapshot = ledger.snapshot()
    assert snapshot.config.request_limit == 25 and all(r.state == "settled" for r in snapshot.requests)
    m = api()
    if allowed:
        assert m._continuation_capacity(snapshot, profile) is None
        assert snapshot.config.request_limit - count >= 16
    else:
        with pytest.raises(transport.FinancialBlocked):
            m._continuation_capacity(snapshot, profile)


def continuation_cli_args(kwargs):
    from ptc.sql_isolation import execution_profile_canonical_bytes
    root = kwargs["output_dir"].parent
    profile_path = root / "TEST_ONLY-cli-profile.json"
    profile_path.write_bytes(execution_profile_canonical_bytes(kwargs["execution_profile"]))
    return ["continue-endpoint", "--manifest", str(root / "assets" / "manifest.json"),
        "--execution-profile", str(profile_path), "--output-dir", str(kwargs["output_dir"]),
        "--billing-profile", str(kwargs["billing_profile_path"]),
        "--billing-approval-sha256", kwargs["approval_sha256"],
        "--budget-dir", str(kwargs["budget_dir"]), "--checkpoint", str(kwargs["checkpoint_path"]),
        "--checkpoint-sha256", kwargs["checkpoint_sha256"],
        "--promotion-approval", str(kwargs["promotion_approval_path"]),
        "--promotion-approval-sha256", kwargs["promotion_approval_sha256"]]


@pytest.mark.parametrize("flags", [[], ["--allow-execution"], ["--allow-model-requests"]])
def test_continuation_cli_requires_both_optins_before_activity(tmp_path, monkeypatch, flags):
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    before = {key: len(value) for key, value in events.items()}
    with pytest.raises(ValueError):
        m.main(continuation_cli_args(kwargs) + flags)
    assert {key: len(value) for key, value in events.items()} == before
    assert not (kwargs["checkpoint_path"].parent / "endpoint-claim.json").exists()


def test_continuation_cli_whole_pins_reach_actual_two_phase_flow(tmp_path, monkeypatch, capsys):
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    assert m.main(continuation_cli_args(kwargs) + ["--allow-execution", "--allow-model-requests"]) == 0
    assert len(events["http"]) == 18 and len(events["reuse"]) == 8
    assert capsys.readouterr().out.strip() == '{"model_results_claim":false,"status":"COMPLETE"}'


def test_atomic_progress_report_counts_each_completed_outcome_before_next_request(tmp_path, monkeypatch):
    m, kwargs, _ = prepared_continuation(tmp_path, monkeypatch)
    original = m._persist_endpoint_report
    progress = []
    def persist(directory, report, *args):
        original(directory, report, *args)
        progress.append(m.open_envelope((directory / "endpoint-report.json").read_bytes(),
                                        "sql_pilot_endpoint_report"))
    monkeypatch.setattr(m, "_persist_endpoint_report", persist)
    result = m.continue_pilot(**kwargs)
    first = next(p for p in progress if p["pairs"][0]["B"]["score"] == 1)
    assert first["request_count"] == 3
    assert first["status"] == "INCOMPLETE" and first["summary"]["complete"] is False
    assert first["summary"]["B"]["successes"] == 1 and first["summary"]["L"]["successes"] == 0
    assert sum(pair[arm]["failure_type"] == "UNRUN" for pair in first["pairs"] for arm in ("B", "L")) == 15
    assert progress[-1] == result


@pytest.mark.parametrize("kind", ["empty", "partial", "broken_symlink"])
def test_existing_partial_endpoint_claim_is_never_reset_or_replayed(tmp_path, monkeypatch, kind):
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    claim = kwargs["checkpoint_path"].parent / "endpoint-claim.json"
    if kind == "broken_symlink":
        claim.symlink_to(tmp_path / "TEST_ONLY-missing-target")
    else:
        claim.write_bytes(b"" if kind == "empty" else b"{")
    before_stat = claim.lstat()
    before = {key: len(value) for key, value in events.items()}
    calls = []
    def constructor(*a, **kw):
        calls.append("CONSTRUCT")
        raise AssertionError("partial claim admitted")
    monkeypatch.setattr(m.PilotAPI, "__init__", constructor)
    monkeypatch.setattr(m.PilotExecutor, "__init__", constructor)
    with pytest.raises(ValueError, match="claimed"):
        m.continue_pilot(**kwargs)
    after_stat = claim.lstat()
    assert (before_stat.st_ino, before_stat.st_size, before_stat.st_mtime_ns) == (
        after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns)
    assert calls == [] and {key: len(value) for key, value in events.items()} == before


def endpoint_result(m, continuation):
    """Retain persisted evidence even when the old controller propagates refusal."""
    try:
        return m.continue_pilot(**continuation)
    except (ValueError, m.captures.CaptureError):
        path = continuation["checkpoint_path"].parent / "endpoint" / "endpoint-report.json"
        return m.open_envelope(path.read_bytes(), "sql_pilot_endpoint_report")


def mutate_fixture_database(path):
    import hashlib
    import os
    import sqlite3
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    os.chmod(path, 0o600)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA user_version = 12345")
        connection.commit()
    finally:
        connection.close()
        os.chmod(path, 0o444)
    after = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert before != after, "TEST_ONLY mutation must change real fixture bytes"
    return before, after


@pytest.mark.parametrize("arm", ["B", "L"])
def test_manifest_db_pin_after_last_http_prevents_all_dispatch_and_complete(tmp_path, monkeypatch, arm):
    from train import sql_pilot_api
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    asset = kwargs["manifest"].assets[-1]
    original = sql_pilot_api._http_attempt
    changed = []
    def mutate_after_http(request, key):
        result = original(request, key)
        stage, payload, _ = events["http"][-1]
        if stage == "endpoint" and payload["question"] == asset.task.question and bool(payload["library"]) == (arm == "L"):
            changed.append((len(events["program"]), len(events["scorer"])))
            mutate_fixture_database(asset.task.db_path)
        return result
    monkeypatch.setattr(sql_pilot_api, "_http_attempt", mutate_after_http)
    result = endpoint_result(m, kwargs)
    assert len(changed) == 1, "HTTP mutation must actually run"
    assert (len(events["program"]), len(events["scorer"])) == changed[0]
    assert result["status"] == "INCOMPLETE"
    assert result["pairs"][-1][arm]["failure_type"] == "INFRA_EXECUTION_BINDING"
    assert result["pairs"][-1][arm]["score"] is None
    assert not (kwargs["checkpoint_path"].parent / "endpoint" / ("endpoint-" + asset.case_id + "-" + arm + ".capture.json")).exists()


def test_program_to_scorer_window_mutation_is_unscored_incomplete(tmp_path, monkeypatch):
    m, kwargs, events = prepared_continuation(tmp_path, monkeypatch)
    target = kwargs["manifest"].assets[-1]
    original = m.PilotExecutor.run_program
    changed = []
    def mutate_after_program(self, code, **kw):
        result = original(self, code, **kw)
        if kw["db_path"] == target.task.db_path:
            changed.append((len(events["program"]), len(events["scorer"])))
            mutate_fixture_database(target.task.db_path)
        return result
    monkeypatch.setattr(m.PilotExecutor, "run_program", mutate_after_program)
    result = endpoint_result(m, kwargs)
    assert len(changed) == 1
    assert (len(events["program"]), len(events["scorer"])) == changed[0]
    assert result["status"] == "INCOMPLETE"
    assert result["pairs"][-1]["B"]["score"] is None
    assert result["pairs"][-1]["B"]["failure_type"] == "INFRA_EXECUTION_BINDING"


def test_saved_manifest_hash_reaches_direct_source_all_four_quals_and_reuse(tmp_path, monkeypatch):
    m, kwargs, _ = controller_world(tmp_path, monkeypatch)
    by_path = {a.task.db_path: a.db_sha256 for a in kwargs["manifest"].assets}
    starts, origins, qualifications, reuses = [], [], [], []
    start, promote, reuse = m.captures.start_capture, m.evaluator.promote_candidate, m.evaluator.reuse_promoted
    def capture_start(task, **kw):
        starts.append((task.db_path, kw.get("expected_db_sha256")))
        return start(task, **kw)
    def promotion(*a, **kw):
        origins.append(kw["source_case"])
        qualifications.extend(kw["qualification_cases"])
        return promote(*a, **kw)
    def reuse_case(*a, **kw):
        reuses.append(a[2])
        return reuse(*a, **kw)
    monkeypatch.setattr(m.captures, "start_capture", capture_start)
    monkeypatch.setattr(m.evaluator, "promote_candidate", promotion)
    monkeypatch.setattr(m.evaluator, "reuse_promoted", reuse_case)
    result = finish_fixture_run(m, kwargs)
    assert result["status"] == "COMPLETE"
    assert len(starts) == 21 and all(pin == by_path[path] for path, pin in starts)
    assert len(origins) == 1 and origins[0].expected_db_sha256 == by_path[origins[0].task.db_path]
    assert len(qualifications) == 4 and all(c.expected_db_sha256 == by_path[c.task.db_path] for c in qualifications)
    assert len(reuses) == 8 and all(c.expected_db_sha256 == by_path[c.task.db_path] for c in reuses)


def foreign_capture(actual, field):
    from dataclasses import replace
    if field == "ids":
        return replace(actual, ids=replace(actual.ids, episode_id="TEST_ONLY-foreign"))
    return replace(actual, **{field: "0" * 64})


@pytest.mark.parametrize("field", ["db_sha256", "task_fingerprint", "ids"])
@pytest.mark.parametrize("route,outcome", [
    ("direct", "normal"), ("direct", "rejected"), ("direct", "aborted"),
    ("reuse", "normal"), ("reuse", "rejected"), ("reuse", "aborted"),
    ("qualification", "normal"), ("qualification", "rejected"), ("qualification", "aborted"),
])
def test_foreign_returned_or_exception_capture_is_infrastructure_not_accepted(tmp_path, monkeypatch, field, route, outcome):
    mode = "third_qualification_abort" if route == "qualification" and outcome == "aborted" else "complete"
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode=mode)
    target = kwargs["manifest"].assets[10] if route == "qualification" else kwargs["manifest"].assets[-1]
    changed = []
    step = m.captures._CaptureSession.step
    def target_step(self, code):
        is_target = self._task.name == target.task.name
        if route == "direct":
            is_target = is_target and not events["http"][-1][1]["library"]
        elif route == "reuse":
            is_target = is_target and bool(events["http"][-1][1]["library"])
        if is_target and outcome == "rejected":
            events["force_next"] = "reject"
        if is_target and outcome == "aborted":
            events["force_next"] = "abort"
        try:
            return step(self, code)
        except m.captures.CaptureError as error:
            if is_target and route == "direct":
                changed.append(error.capture)
                raise type(error)(foreign_capture(error.capture, field))
            raise
    monkeypatch.setattr(m.captures._CaptureSession, "step", target_step)
    if route == "direct" and outcome == "normal":
        finish = m.captures._CaptureSession.finish
        def target_finish(self, answer):
            actual = finish(self, answer)
            if self._task.name == target.task.name and not events["http"][-1][1]["library"]:
                changed.append(actual)
                return foreign_capture(actual, field)
            return actual
        monkeypatch.setattr(m.captures._CaptureSession, "finish", target_finish)
    elif route == "reuse":
        reuse = m.evaluator.reuse_promoted
        def foreign_reuse(*a, **kw):
            try:
                actual = reuse(*a, **kw)
            except m.captures.CaptureExecutionAborted as error:
                actual = error.capture
            if a[2].task.name == target.task.name:
                changed.append(actual)
                actual = foreign_capture(actual, field)
                if outcome != "normal":
                    cls = m.captures.CaptureProgramRejected if outcome == "rejected" else m.captures.CaptureExecutionAborted
                    raise cls(actual)
            return actual
        monkeypatch.setattr(m.evaluator, "reuse_promoted", foreign_reuse)
    elif route == "qualification":
        promote = m.evaluator.promote_candidate
        def foreign_qualification(*a, **kw):
            promotion, captures = promote(*a, **kw)
            captures = list(captures)
            index = next(i for i, c in enumerate(captures) if c.task_id == target.task.name)
            changed.append(captures[index])
            captures[index] = foreign_capture(captures[index], field)
            return promotion, tuple(captures)
        monkeypatch.setattr(m.evaluator, "promote_candidate", foreign_qualification)
    report = m.run_pilot(**kwargs)
    if route != "qualification":
        assert report["status"] == "AWAITING_PROMOTION_APPROVAL"
        report = endpoint_result(m, external_continuation(m, kwargs))
    assert len(changed) == 1, "foreign capture injection must actually run"
    assert report["status"] == "INCOMPLETE"
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    if route == "qualification":
        assert len(report["qualification"]) == 2
        assert not (directory / "qualification-2.capture.json").exists()
    else:
        arm = "B" if route == "direct" else "L"
        assert report["pairs"][-1][arm]["failure_type"] == "INFRA_EXECUTION_BINDING"
        assert report["pairs"][-1][arm]["score"] is None
        assert not (directory / "endpoint" / ("endpoint-" + target.case_id + "-" + arm + ".capture.json")).exists()


def repin_fixture_checkpoint(m, kwargs, *, remove=()):
    """TEST_ONLY external actor, no ledger edits or invented receipt hashes."""
    checkpoint = kwargs["output_dir"] / "pilot-TEST_ONLY" / "qualification-checkpoint.json"
    value = m.open_envelope(checkpoint.read_bytes(), "sql_pilot_qualification_checkpoint")
    value["artifacts"] = [pin for pin in value["artifacts"] if pin["path"] not in remove]
    for pin in value["artifacts"]:
        pin["sha256"] = m.digest((checkpoint.parent / pin["path"]).read_bytes())
    checkpoint.write_bytes(m.envelope_bytes("sql_pilot_qualification_checkpoint", value))
    return external_continuation(m, kwargs)


@pytest.mark.parametrize("earlier", ["graded", "rejected", "no_final", "invalid"])
def test_terminal_aware_development_prefix_remains_valid_without_reexecution(tmp_path, monkeypatch, earlier):
    m, kwargs, events = controller_world(tmp_path, monkeypatch, mode="prefix_" + earlier)
    phase_one = m.run_pilot(**kwargs)
    assert phase_one["status"] == "AWAITING_PROMOTION_APPROVAL"
    assert len(phase_one["development"]) == 2
    before = list(events["http"])
    result = m.continue_pilot(**external_continuation(m, kwargs))
    assert result["status"] == "COMPLETE" and result["request_count"] == 19
    assert events["http"][:3] == before
    assert all(stage == "endpoint" for stage, _, _ in events["http"][3:])


@pytest.mark.parametrize("change", [
    "source_comment", "source_newline", "earlier_comment", "earlier_newline",
    "valid_without_capture", "invalid_with_capture", "failure_type", "score", "route",
    "earlier_telemetry", "source_telemetry", "receipt_program", "receipt_scorer",
    "earlier_db", "earlier_fingerprint", "earlier_ids", "earlier_instrument", "protocol",
])
def test_every_development_response_graph_rejects_before_endpoint_activity(tmp_path, monkeypatch, change):
    from dataclasses import replace
    m, kwargs, events = controller_world(tmp_path, monkeypatch,
        mode="prefix_invalid" if change == "invalid_with_capture" else "prefix_protocol" if change == "protocol" else "prefix_graded")
    manifest = kwargs["manifest"]
    if change.endswith(("comment", "newline")):
        original = m.execute_program
        index = 1 if change.startswith("source_") else 0
        suffix = " #TEST_ONLY comment" if change.endswith("comment") else "\n"
        def different_program(asset, program, **kw):
            if asset == manifest.assets[index]:
                program += suffix
            return original(asset, program, **kw)
        monkeypatch.setattr(m, "execute_program", different_program)
    if change == "protocol":
        request = m.PilotAPI.request
        def fabricate_invalid(self, *a, **kw):
            try:
                return request(self, *a, **kw)
            except m.ProtocolStop as error:
                ordinary = m.ModelActionError("TEST_ONLY fabricated protocol classification")
                ordinary.telemetry = error.telemetry
                raise ordinary
        monkeypatch.setattr(m.PilotAPI, "request", fabricate_invalid)
    result = m.run_pilot(**kwargs)
    assert result["status"] == "AWAITING_PROMOTION_APPROVAL"
    assert len(result["development"]) == 2
    directory = kwargs["output_dir"] / "pilot-TEST_ONLY"
    report_path = directory / "report.json"
    report = m.open_envelope(report_path.read_bytes(), "sql_pilot_report")
    first_path = directory / ("development-" + manifest.assets[0].case_id + ".capture.json")
    remove = ()
    if change == "valid_without_capture":
        first_path.rename(tmp_path / "TEST_ONLY-retained-earlier.capture.json")
        remove = (first_path.name,)
        report["development"][0].update(failure_type="MODEL_ACTION_INVALID", score=None, route=None)
    elif change == "invalid_with_capture":
        executor = m.PilotExecutor(kwargs["execution_profile"], state_dir=tmp_path / "TEST_ONLY-extra-capture")
        actual = m.execute_program(manifest.assets[0], "TEST_ONLY_GOOD_PROGRAM", executor=executor)
        first_path.write_bytes(m.captures.encode_capture(actual))
    elif change in ("failure_type", "score", "route"):
        report["development"][0][change] = {"failure_type": "MODEL_NO_FINAL_SQL", "score": 0, "route": "APPROVED_REUSE"}[change]
    elif change in ("earlier_telemetry", "source_telemetry"):
        report["development"][0 if change.startswith("earlier") else 1]["telemetry"]["latency_ms"] += 1
    elif change.startswith("receipt_"):
        actual = m.captures.decode_capture(first_path.read_bytes())
        receipts = list(actual.runtime_receipts)
        index = 0 if change == "receipt_program" else 1
        receipts[index] = replace(receipts[index], request_sha256="0" * 64)
        first_path.write_bytes(m.captures.encode_capture(replace(actual, runtime_receipts=tuple(receipts))))
    elif change.startswith("earlier_") and change not in ("earlier_comment", "earlier_newline"):
        actual = m.captures.decode_capture(first_path.read_bytes())
        field = {"earlier_db": "db_sha256", "earlier_fingerprint": "task_fingerprint", "earlier_ids": "ids"}.get(change)
        actual = foreign_capture(actual, field) if field else replace(actual,
            instrument=replace(actual.instrument, source_sha256="0" * 64))
        first_path.write_bytes(m.captures.encode_capture(actual))
    report_path.write_bytes(m.envelope_bytes("sql_pilot_report", report))
    continuation = repin_fixture_checkpoint(m, kwargs, remove=remove)
    calls = []
    def constructor(*a, **kw):
        calls.append("CONSTRUCT")
        raise AssertionError("inconsistent development graph admitted")
    from train import sql_pilot_api
    monkeypatch.setattr(m.PilotAPI, "__init__", constructor)
    monkeypatch.setattr(m.PilotExecutor, "__init__", constructor)
    monkeypatch.setattr(sql_pilot_api, "_read_credential", lambda: calls.append("KEY"))
    before = {key: len(value) for key, value in events.items()}
    with pytest.raises((ValueError, OSError)):
        m.continue_pilot(**continuation)
    assert calls == [] and {key: len(value) for key, value in events.items()} == before
    assert not (directory / "endpoint-claim.json").exists()
