"""Opt-in SQL skill pilot controller. No default-arm changes or live approval.

The controller never executes model Python/SQL on the host. PROGRAM and SCORER
are the concrete PilotExecutor; v1 trusted-host fallback is not permitted.
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ptc.sql_isolation import (
    ExecutionProfile, PilotExecutor, build_execution_binding,
    execution_profile_sha256, installed_source_root, load_execution_profile,
)
from train import sql_capture as captures
from train import sql_skill_eval as evaluator
from train import sql_skills as skills
from train.sql_pilot_assets import (
    PilotAsset, PilotManifest, canonical_bytes, closed, digest, envelope_bytes,
    fsync_dir, load_manifest, manifest_sha256, open_envelope, prepare_manifest,
    read_file, safe_path, validate_manifest, write_new, sha, integer, strict_json,
)
from train.sql_pilot_api import (
    DESCRIPTION, FinancialBlocked, ModelActionError, PilotAPI, PilotAction,
    ProtocolStop, authorize, init_budget, load_billing_profile, maximum_charge,
    load_receipt, build_request, parse_response,
)
from train.sql_pilot_budget import BudgetError, BudgetLedger


def require_optins(allow_execution, allow_model_requests):
    if allow_execution is not True or allow_model_requests is not True:
        raise ValueError("both execution and model opt-ins must be literal True")


def planned_pairs(case_ids):
    if type(case_ids) is not tuple or len(case_ids) != 8 or len(set(case_ids)) != 8:
        raise ValueError("eight distinct endpoint case IDs required")
    return [{"case_id": case_id,
             "B": {"failure_type": "UNRUN", "score": None, "route": None, "telemetry": None},
             "L": {"failure_type": "UNRUN", "score": None, "route": None, "telemetry": None}}
            for case_id in case_ids]


def capture_result(capture, *, route):
    abort = capture.execution_abort
    failure = None
    score = None
    if abort is not None:
        failure = "INFRA_" + abort.stage.upper() + "_" + abort.reason.upper()
    elif capture.terminal_label == "program_rejected":
        failure = "MODEL_PROGRAM_REJECTED"
    elif capture.terminal_label != "final_submitted" or capture.result is None:
        failure = "MODEL_NO_FINAL_SQL"
    elif capture.result.valid is not True:
        failure = "INVALID_GOLD"
    else:
        score = capture.result.score
        if score != 1:
            failure = "MODEL_" + capture.result.status.upper()
    return {"failure_type": failure, "score": score, "route": route, "telemetry": None}


def summarize_pairs(pairs):
    if len(pairs) != 8:
        raise ValueError("never reduce planned denominator eight")
    result = {"denominator": 8, "complete": True, "dollar_benefit": None,
              "provider_adherence": "UNVERIFIED", "effective_version": "UNKNOWN",
              "cache_protocol": "UNKNOWN"}
    for arm in ("B", "L"):
        records = [pair[arm] for pair in pairs]
        successes = sum(record.get("score") == 1 for record in records)
        failures = [record.get("failure_type") for record in records]
        if any(f == "UNRUN" or f == "INVALID_GOLD" or
               type(f) is str and f.startswith("INFRA_") for f in failures):
            result["complete"] = False
        costs = [r.get("telemetry", {}).get("actual_charge_usd_micros")
                 if type(r.get("telemetry")) is dict else None for r in records]
        latencies = [r["telemetry"].get("latency_ms") for r in records
                     if type(r.get("telemetry")) is dict]
        result[arm] = {"accuracy": successes / 8, "successes": successes,
                       "failures": sum(f is not None for f in failures),
                       "failure_types": failures,
                       "approved_reuse_invocations": sum(r.get("route") == "APPROVED_REUSE" for r in records),
                       "invocation_rate": sum(r.get("route") == "APPROVED_REUSE" for r in records) / 8,
                       "actual_charge_usd_micros": sum(costs) if all(type(x) is int for x in costs) else None,
                       "latency_ms": latencies}
    return result


def proposal_payload(asset, capture):
    # Never serialize ExResult/detail/task objects into a generator projection.
    if (capture.terminal_label != "final_submitted" or capture.execution_abort is not None
            or capture.result is None or capture.result.valid is not True
            or capture.result.score != 0 or len(capture.steps) != 1):
        raise ValueError("proposal requires one independently admitted valid-zero attempt")
    return {"stage": "proposal", "question": asset.task.question,
            "schema": capture.schema, "attempt": capture.steps[0].action,
            "observation": capture.steps[0].observation,
            "valid_zero": True, "library": []}


def task_payload(asset: PilotAsset, *, stage, library):
    # Native schema construction is local metadata from frozen, trusted SQLite.
    # Gold/evidence/IDs/other task partitions are deliberately not projected.
    from ptc.sql_arms import build_sql_arms
    pair = build_sql_arms(asset.task)
    return {"stage": stage, "question": asset.task.question,
            "schema": pair.schema, "library": library}


def _executor(executor):
    if type(executor) is not PilotExecutor:
        raise TypeError("concrete PilotExecutor required, no arbitrary callbacks")
    build_execution_binding(executor.profile, source_root=installed_source_root())


def _verify_asset_capture(actual, asset: PilotAsset):
    captures.encode_capture(actual)
    if (actual.schema_version != 2 or actual.execution_binding is None
            or actual.ids != asset.ids or actual.task_id != asset.task.name
            or actual.task_fingerprint != asset.task_fingerprint
            or actual.db_sha256 != asset.db_sha256):
        raise ValueError("execution capture differs from manifest asset")


def execute_program(asset: PilotAsset, program: str, *, executor: PilotExecutor):
    _executor(executor)
    session = captures.start_capture(asset.task, ids=asset.ids,
                                     allow_execution=True, executor=executor,
                                     expected_db_sha256=asset.db_sha256)
    try:
        observation = session.step(program)
        if not observation.startswith("FINAL_SQL:") or not observation[len("FINAL_SQL:"):].strip():
            actual = session.abort()
        else:
            actual = session.finish(observation[len("FINAL_SQL:"):])
        _verify_asset_capture(actual, asset)
        return actual
    except Exception as error:
        # Lazy lookup supports parallel source development, not a fallback:
        # missing production methods/signatures still raise, never become green.
        exceptions = tuple(cls for name in ("CaptureProgramRejected", "CaptureExecutionAborted")
                           if isinstance((cls := getattr(captures, name, None)), type))
        if isinstance(error, exceptions):
            _verify_asset_capture(error.capture, asset)
            return error.capture
        raise


@dataclass(frozen=True, slots=True)
class ApprovedSkill:
    candidate: skills.SkillCandidate
    promotion: skills.SkillPromotion
    promotion_sha256: str
    approval_path: Path
    approval_sha256: str


def library_entry(approved: ApprovedSkill):
    validate_approval(approved)
    return {"skill_id": approved.candidate.skill_id,
            "promotion_sha256": approved.promotion_sha256,
            "scope": asdict(approved.candidate.scope), "description": DESCRIPTION,
            "program": approved.candidate.program}


def validate_approval(approved: ApprovedSkill):
    if type(approved) is not ApprovedSkill:
        raise TypeError("frozen host approval required")
    # This pin lives outside the promotion artifact and cannot be model-selected.
    raw = read_file(approved.approval_path)
    if digest(raw) != sha(approved.approval_sha256):
        raise ValueError("external whole-approval pin mismatch")
    obj = closed(open_envelope(raw, "sql_pilot_host_approval"),
                 ("promotion_sha256", "candidate_sha256", "ids"))
    if (obj["promotion_sha256"] != approved.promotion_sha256
            or digest(skills.encode_promotion(approved.promotion)) != approved.promotion_sha256
            or obj["candidate_sha256"] != digest(skills.encode_candidate(approved.candidate))
            or obj["ids"] != asdict(approved.promotion.ids)
            or approved.promotion.schema_version != 2
            or approved.promotion.binding.execution_binding is None
            or len(approved.promotion.qualifications) != 4):
        raise ValueError("external host approval/promotion binding mismatch")


def route_action(action: PilotAction, asset: PilotAsset, *, executor: PilotExecutor,
                 approved: ApprovedSkill | None):
    if type(action) is not PilotAction:
        raise TypeError("concrete validated action required")
    action.__post_init__()
    _executor(executor)
    if action.kind == "program":
        # No byte-match shortcut: identical or adapted direct programs stay direct.
        return execute_program(asset, action.program, executor=executor), "DIRECT"
    if approved is None:
        raise ModelActionError("no approved library reference available")
    validate_approval(approved)
    if (action.skill_id != approved.candidate.skill_id
            or action.promotion_sha256 != approved.promotion_sha256):
        raise ModelActionError("unknown reference; no direct fallback")
    case = evaluator.SkillCase("reuse", asset.task, asset.ids,
                               expected_db_sha256=asset.db_sha256)
    try:
        actual = evaluator.reuse_promoted(
            approved.candidate, approved.promotion, case,
            expected_promotion_sha256=approved.promotion_sha256,
            ids=approved.promotion.ids, allow_execution=True, executor=executor)
    except captures.CaptureError as error:
        _verify_asset_capture(error.capture, asset)
        return error.capture, "APPROVED_REUSE"
    _verify_asset_capture(actual, asset)
    return actual, "APPROVED_REUSE"


def _persist_capture(directory, name, capture):
    if capture.schema_version != 2 or capture.execution_binding is None:
        raise ValueError("controller requires isolated v2 capture, never trusted-host fallback")
    write_new(directory / (name + ".capture.json"), captures.encode_capture(capture))


def _ids(manifest, label, split):
    return replace(manifest.assets[0].ids, split_id=split, episode_id=label)


def _model_failure(error):
    return {"failure_type": "MODEL_ACTION_INVALID", "score": None, "route": None,
            "telemetry": error.telemetry}


def _model_only_amortization(report):
    summary = report["summary"]
    baseline = summary["B"]["actual_charge_usd_micros"]
    library = summary["L"]["actual_charge_usd_micros"]
    overhead = [r.get("telemetry", {}).get("actual_charge_usd_micros")
                if type(r.get("telemetry")) is dict else None
                for r in report["development"] + report["proposal"]]
    result = {"qualification_compute_usd_micros": None, "total_economics": None,
              "model_request_only": None}
    if (not summary["complete"] or type(baseline) is not int or type(library) is not int
            or not overhead or any(type(x) is not int for x in overhead)
            or baseline <= library):
        return result
    generation = sum(overhead)
    savings = baseline - library  # eight-pair sum, exact integer USD micros
    result["model_request_only"] = {
        "scope": "authoritative model-request receipts only; excludes unpriced local compute",
        "generation_usd_micros": generation,
        "savings_per_use_usd_micros": {"numerator": savings, "denominator": 8},
        "break_even_uses": (generation * 8 + savings - 1) // savings,
        "amortized_generation_usd_micros": {
            str(n): {"numerator": generation, "denominator": n} for n in (100, 1000, 10000)}}
    return result


def run_pilot(manifest: PilotManifest, execution_profile: ExecutionProfile, *,
              output_dir: Path, billing_profile_path: Path, approval_sha256: str,
              budget_dir: Path, allow_execution=False, allow_model_requests=False):
    require_optins(allow_execution, allow_model_requests)
    validate_manifest(manifest)
    profile = load_billing_profile(billing_profile_path, approval_sha256=approval_sha256)
    config = authorize(profile, approval_sha256, manifest=manifest,
                       execution_profile=execution_profile, budget_dir=budget_dir)
    ledger = BudgetLedger.open(str(budget_dir), config)  # open existing only
    snapshot = ledger.snapshot()
    # No resume protocol: a prior request cannot be cloned/replayed into a new run.
    if snapshot.requests or snapshot.status != "active":
        raise FinancialBlocked("pilot requires an unused authorized ledger; no replay")
    build_execution_binding(execution_profile, source_root=installed_source_root())
    safe_path(output_dir, exists=True, directory=True)
    directory = output_dir / ("pilot-" + manifest.run_id)
    directory.mkdir(mode=0o700)  # exclusive; never reuse previous artifacts
    fsync_dir(output_dir)
    api = PilotAPI(billing_profile_path=billing_profile_path, approval_sha256=approval_sha256,
                   manifest=manifest, execution_profile=execution_profile,
                   budget_dir=budget_dir, output_dir=directory,
                   allow_execution=True, allow_model_requests=True)
    executor = PilotExecutor(execution_profile, state_dir=directory / "execution")
    heldout = manifest.assets[12:]
    pairs = planned_pairs(tuple(asset.case_id for asset in heldout))
    report = {"schema_version": 1, "run_id": manifest.run_id,
              "manifest_sha256": manifest_sha256(manifest),
              "execution_profile_sha256": execution_profile_sha256(execution_profile),
              "billing_approval_sha256": approval_sha256, "status": "INCOMPLETE",
              "requested_model": profile.model, "provider": profile.provider,
              "endpoint": profile.endpoint, "effective_version": "UNKNOWN",
              "cache_protocol": "UNKNOWN",
              "stop_reason": None, "development": [], "proposal": [],
              "qualification": [], "pairs": pairs, "model_results_claim": False}
    write_new(directory / "planned.json", envelope_bytes("sql_pilot_planned", report))
    source = source_asset = None
    try:
        for asset in manifest.assets[:8]:
            record = {"case_id": asset.case_id, "telemetry": None,
                      "failure_type": "INFRA_MODEL_REQUEST"}
            report["development"].append(record)
            try:
                reply = api.request(manifest.run_id + ":development:" + asset.case_id,
                                    task_payload(asset, stage="development", library=[]),
                                    library=[], program_only=True)
                record["telemetry"] = reply.telemetry
            except ProtocolStop:
                raise
            except ModelActionError as error:
                record.update(_model_failure(error))
                continue
            started = time.monotonic_ns()
            try:
                actual = execute_program(asset, reply.action.program, executor=executor)
            except ValueError:
                record.update(failure_type="INFRA_EXECUTION_BINDING", score=None,
                              route=None, telemetry=reply.telemetry)
                report["stop_reason"] = record["failure_type"]
                return report
            _persist_capture(directory, "development-" + asset.case_id, actual)
            record.update(capture_result(actual, route="DIRECT"), telemetry=reply.telemetry)
            record["execution_latency_ms"] = (time.monotonic_ns() - started) // 1_000_000
            if actual.execution_abort is not None:
                report["stop_reason"] = record["failure_type"]
                return report
            if (actual.terminal_label == "final_submitted" and actual.result is not None
                    and actual.result.valid is True and actual.result.score == 0):
                # A recorded zero is not authority. Separate SCORER-only rescore.
                started = time.monotonic_ns()
                rescored = captures.rescore_capture(actual, asset.task, ids=asset.ids, executor=executor)
                record["independent_rescore_latency_ms"] = (time.monotonic_ns() - started) // 1_000_000
                if rescored.valid is True and rescored.score == 0:
                    source, source_asset = actual, asset
                    break
        if source is None:
            report.update(status="STOPPED_NO_ORIGIN", stop_reason="no independently rescored valid EX0")
            return report
        report["proposal"].append({"failure_type": "INFRA_MODEL_REQUEST", "telemetry": None})
        try:
            proposal = api.request(manifest.run_id + ":proposal:one",
                                   proposal_payload(source_asset, source), library=[], program_only=True)
            report["proposal"][0] = {"telemetry": proposal.telemetry}
        except ProtocolStop:
            raise
        except ModelActionError as error:
            report["proposal"][0] = _model_failure(error)
            report.update(status="STOPPED_PROPOSAL", stop_reason="one proposal invalid; zero repairs")
            return report
        candidate = skills.create_candidate(
            source, source_task=source_asset.task, source_ids=source_asset.ids,
            skill_id="single-user-table-row-count", program=proposal.action.program)
        write_new(directory / "candidate.json", skills.encode_candidate(candidate))
        source_pin = digest(captures.encode_capture(source))
        started = time.monotonic_ns()
        promotion, qualification_captures = evaluator.promote_candidate(
            candidate, source_capture=source, expected_source_capture_sha256=source_pin,
            source_case=evaluator.SkillCase("source_failure", source_asset.task, source_asset.ids,
                                            expected_db_sha256=source_asset.db_sha256),
            qualification_cases=tuple(evaluator.SkillCase("qualification", a.task, a.ids,
                                                          expected_db_sha256=a.db_sha256)
                                      for a in manifest.assets[8:12]),
            ids=_ids(manifest, "approval", "approval"), allow_execution=True, executor=executor)
        report["qualification_latency_ms"] = (time.monotonic_ns() - started) // 1_000_000
        for i, actual in enumerate(qualification_captures):
            try:
                _verify_asset_capture(actual, manifest.assets[8 + i])
            except ValueError:
                report["stop_reason"] = "INFRA_EXECUTION_BINDING"
                return report
            _persist_capture(directory, "qualification-" + str(i), actual)
            report["qualification"].append(capture_result(actual, route="DIRECT"))
        if any(actual.execution_abort is not None for actual in qualification_captures):
            report["stop_reason"] = "qualification infrastructure abort"
            return report
        if promotion is None:
            report.update(status="STOPPED_UNQUALIFIED", stop_reason="four actual EX1 qualifications not achieved")
            return report
        if len(qualification_captures) != 4:
            raise ValueError("promotion requires all four actual captures")
        promotion_raw = skills.encode_promotion(promotion)
        write_new(directory / "promotion.json", promotion_raw)
        _continuation_capacity(ledger.snapshot(), profile)
        report["status"] = "AWAITING_PROMOTION_APPROVAL"
        return report
    except (FinancialBlocked, BudgetError):
        report["stop_reason"] = "financial or delivery uncertainty; STOP, reservation retained"
        return report
    except ProtocolStop as error:
        report["stop_reason"] = "provider tool protocol not established; STOP"
        report["protocol_failure_telemetry"] = error.telemetry
        return report
    except Exception as error:
        cls = getattr(captures, "CaptureExecutionAborted", None)
        if isinstance(cls, type) and isinstance(error, cls):
            _persist_capture(directory, "execution-aborted", error.capture)
            report["stop_reason"] = capture_result(error.capture, route="DIRECT")["failure_type"]
            return report
        # Unknown backend/integration failures are not model EX0s or green runs.
        report["stop_reason"] = "controller/backend exception; INCOMPLETE"
        raise
    finally:
        report["summary"] = summarize_pairs(pairs)
        report["economics"] = _model_only_amortization(report)
        report["request_count"] = len(ledger.snapshot().requests)
        write_new(directory / "report.json", envelope_bytes("sql_pilot_report", report))
        if report["status"] == "AWAITING_PROMOTION_APPROVAL":
            _publish_checkpoint(directory, manifest, execution_profile, approval_sha256,
                                budget_dir, ledger.snapshot(), source_asset)


_CHECKPOINT = "qualification-checkpoint.json"
_CHECKPOINT_FIELDS = (
    "run_id", "run_directory", "manifest_sha256", "execution_profile_sha256",
    "billing_approval_sha256", "budget_directory", "ledger_snapshot_sha256",
    "request_count", "source_case_id", "source_capture_sha256", "candidate_sha256",
    "promotion_sha256", "promotion_ids", "artifacts",
)


def _snapshot_sha(snapshot):
    return digest(canonical_bytes(asdict(snapshot)))


def _continuation_capacity(snapshot, profile):
    count = len(snapshot.requests)
    if (snapshot.status != "active" or not 2 <= count <= 9
            or any(r.state != "settled" for r in snapshot.requests)
            or snapshot.config.request_limit - count < 16
            or snapshot.config.limit_usd_micros - snapshot.exposure_micros < 16 * maximum_charge(profile)):
        raise FinancialBlocked("checkpoint requires settled upstream history and sixteen funded slots")


def _artifact_names(report, snapshot):
    names = {"planned.json", "report.json", "candidate.json", "promotion.json"}
    for record in report["development"]:
        if record["failure_type"] != "MODEL_ACTION_INVALID":
            names.add("development-" + record["case_id"] + ".capture.json")
    names.update("qualification-" + str(i) + ".capture.json" for i in range(4))
    for record in snapshot.requests:
        stem = digest(record.request_id.encode("utf-8"))
        names.update(stem + suffix for suffix in (".request.json", ".response.json", ".receipt.json"))
    return sorted(names)


def _publish_checkpoint(directory, manifest, execution_profile, approval_sha256,
                        budget_dir, snapshot, source_asset):
    report = open_envelope(read_file(directory / "report.json"), "sql_pilot_report")
    promotion = skills.decode_promotion(read_file(directory / "promotion.json"))
    payload = {
        "run_id": manifest.run_id, "run_directory": str(directory),
        "manifest_sha256": manifest_sha256(manifest),
        "execution_profile_sha256": execution_profile_sha256(execution_profile),
        "billing_approval_sha256": approval_sha256, "budget_directory": str(budget_dir),
        "ledger_snapshot_sha256": _snapshot_sha(snapshot), "request_count": len(snapshot.requests),
        "source_case_id": source_asset.case_id,
        "source_capture_sha256": digest(read_file(directory / ("development-" + source_asset.case_id + ".capture.json"))),
        "candidate_sha256": digest(read_file(directory / "candidate.json")),
        "promotion_sha256": digest(read_file(directory / "promotion.json")),
        "promotion_ids": asdict(promotion.ids),
        "artifacts": [{"path": name, "sha256": digest(read_file(directory / name))}
                      for name in _artifact_names(report, snapshot)],
    }
    # Report and every artifact have already been fsynced. Publication is LAST.
    write_new(directory / _CHECKPOINT, envelope_bytes("sql_pilot_qualification_checkpoint", payload))


def _verify_capture_graph(actual, asset, binding, *, program=None):
    captures.encode_capture(actual)
    if (actual.schema_version != 2 or actual.execution_binding != binding.execution_binding
            or actual.instrument != binding.instrument or actual.ids != asset.ids
            or actual.task_id != asset.task.name or actual.task_fingerprint != asset.task_fingerprint
            or actual.db_sha256 != asset.db_sha256 or len(actual.steps) != 1
            or actual.terminal_label != "final_submitted" or actual.result is None
            or actual.result.valid is not True or actual.execution_abort is not None):
        raise ValueError("capture differs from frozen task/current binding")
    if program is not None and actual.steps[0].action != program:
        raise ValueError("qualification program differs from frozen candidate")
    from ptc.sql_isolation import ProgramRequest, ScoreRequest, request_sha256
    instrument = actual.instrument
    expected = (
        ("program", request_sha256(ProgramRequest(actual.steps[0].action, instrument.action_max_rows, asset.db_sha256))),
        ("scorer", request_sha256(ScoreRequest(
            replace(asset.task, db_path="/db.sqlite"), actual.extracted_sql,
            instrument.scorer_timeout_s, instrument.scorer_max_rows, instrument.compare, asset.db_sha256))),
    )
    if tuple((r.role, r.request_sha256) for r in actual.runtime_receipts) != expected:
        raise ValueError("capture receipt context differs from dispatched requests")


def _development_receipts(actual, asset):
    from ptc.sql_isolation import ProgramRequest, ScoreRequest, request_sha256
    instrument = actual.instrument
    expected = [("program", request_sha256(ProgramRequest(
        actual.steps[0].action, instrument.action_max_rows, asset.db_sha256)))]
    if actual.terminal_label == "final_submitted":
        expected.append(("scorer", request_sha256(ScoreRequest(
            replace(asset.task, db_path="/db.sqlite"), actual.extracted_sql,
            instrument.scorer_timeout_s, instrument.scorer_max_rows,
            instrument.compare, asset.db_sha256))))
    return tuple(expected)


def _verify_development_capture(actual, asset, binding, *, program, record, telemetry):
    captures.encode_capture(actual)
    if (actual.schema_version != 2 or actual.execution_binding != binding.execution_binding
            or actual.instrument != binding.instrument or actual.ids != asset.ids
            or actual.task_id != asset.task.name or actual.task_fingerprint != asset.task_fingerprint
            or actual.db_sha256 != asset.db_sha256 or len(actual.steps) != 1
            or actual.steps[0].action != program or actual.execution_abort is not None):
        raise ValueError("development capture differs from response/manifest graph")
    if actual.terminal_label == "final_submitted":
        if actual.result is None or actual.result.valid is not True:
            raise ValueError("graded development capture requires a valid protected result")
    elif actual.terminal_label in ("program_rejected", "aborted"):
        if actual.result is not None:
            raise ValueError("unscored development capture carries a result")
    else:
        raise ValueError("unsupported development terminal state")
    if tuple((r.role, r.request_sha256) for r in actual.runtime_receipts) != _development_receipts(actual, asset):
        raise ValueError("development receipt context differs from dispatched requests")
    expected = capture_result(actual, route="DIRECT")
    if (record["failure_type"] != expected["failure_type"] or record["score"] != expected["score"]
            or record["route"] != "DIRECT" or record["telemetry"] != telemetry):
        raise ValueError("development report classification differs from capture")


def _verify_checkpoint(directory, checkpoint_path, checkpoint_sha256, manifest, execution_profile,
                       approval_sha256, budget_dir, snapshot, profile, billing_profile_path):
    if safe_path(checkpoint_path, exists=True) != directory / _CHECKPOINT:
        raise ValueError("checkpoint must be the original run's expected file")
    raw = read_file(checkpoint_path)
    if digest(raw) != sha(checkpoint_sha256):
        raise ValueError("external whole-checkpoint pin mismatch")
    obj = closed(open_envelope(raw, "sql_pilot_qualification_checkpoint"), _CHECKPOINT_FIELDS)
    expected = {"run_id": manifest.run_id, "run_directory": str(directory),
        "manifest_sha256": manifest_sha256(manifest),
        "execution_profile_sha256": execution_profile_sha256(execution_profile),
        "billing_approval_sha256": approval_sha256, "budget_directory": str(budget_dir),
        "ledger_snapshot_sha256": _snapshot_sha(snapshot), "request_count": len(snapshot.requests)}
    if any(obj[key] != value or type(obj[key]) is not type(value) for key, value in expected.items()):
        raise ValueError("checkpoint run/profile/ledger context mismatch")
    _continuation_capacity(snapshot, profile)
    count = integer(obj["request_count"], minimum=2)
    source_asset = manifest.assets[count - 2]
    if obj["source_case_id"] != source_asset.case_id:
        raise ValueError("checkpoint source is not the last development-prefix case")
    expected_ids = [manifest.run_id + ":development:" + a.case_id for a in manifest.assets[:count - 1]]
    expected_ids.append(manifest.run_id + ":proposal:one")
    if [r.request_id for r in snapshot.requests] != expected_ids:
        raise ValueError("ledger history is not the exact development prefix plus one proposal")
    artifacts = obj["artifacts"]
    if type(artifacts) is not list or len(artifacts) > 64:
        raise ValueError("bounded artifact graph required")
    from ptc.sql_isolation import SourcePin
    names = []
    for value in artifacts:
        pin = SourcePin(**closed(value, ("path", "sha256")))
        names.append(pin.path)
        if digest(read_file(directory / pin.path)) != pin.sha256:
            raise ValueError("checkpoint artifact pin mismatch")
    if names != sorted(set(names)):
        raise ValueError("sorted unique artifact paths required")
    report = open_envelope(read_file(directory / "report.json"), "sql_pilot_report")
    if names != _artifact_names(report, snapshot):
        raise ValueError("checkpoint artifact graph is not complete/exact")
    planned = open_envelope(read_file(directory / "planned.json"), "sql_pilot_planned")
    pairs = planned_pairs(tuple(a.case_id for a in manifest.assets[12:]))
    if (report["status"] != "AWAITING_PROMOTION_APPROVAL" or report["pairs"] != pairs
            or planned["pairs"] != pairs or report["request_count"] != count
            or len(report["development"]) != count - 1 or len(report["proposal"]) != 1
            or len(report["qualification"]) != 4):
        raise ValueError("phase-one report/planned slots differ")
    for key in ("run_id", "manifest_sha256", "execution_profile_sha256", "billing_approval_sha256"):
        if report[key] != expected[key] or planned[key] != expected[key]:
            raise ValueError("phase-one report context differs")
    if [r["case_id"] for r in report["development"]] != [a.case_id for a in manifest.assets[:count - 1]]:
        raise ValueError("development records are not the frozen prefix")
    candidate_raw = read_file(directory / "candidate.json")
    promotion_raw = read_file(directory / "promotion.json")
    source_raw = read_file(directory / ("development-" + source_asset.case_id + ".capture.json"))
    for key, value in (("candidate_sha256", candidate_raw), ("promotion_sha256", promotion_raw),
                       ("source_capture_sha256", source_raw)):
        if sha(obj[key]) != digest(value):
            raise ValueError("checkpoint core artifact pin mismatch")
    candidate = skills.decode_candidate(candidate_raw)
    promotion = skills.decode_promotion(promotion_raw)
    source = captures.decode_capture(source_raw)
    # Existing metadata-only binding builder, never instantiate an executor here.
    binding = replace(evaluator._current_binding(source_asset.task),
                      execution_binding=execution_profile.binding)
    _verify_capture_graph(source, source_asset, binding)
    skills._declared_failure(source)
    expected_candidate = skills.create_candidate(source, source_task=source_asset.task,
        source_ids=source_asset.ids, skill_id="single-user-table-row-count", program=candidate.program)
    if (candidate != expected_candidate or promotion.source != candidate.source
            or promotion.candidate_sha256 != digest(candidate_raw) or promotion.scope != candidate.scope
            or promotion.schema_version != 2 or promotion.binding != binding
            or obj["promotion_ids"] != asdict(promotion.ids)
            or promotion.ids != _ids(manifest, "approval", "approval")):
        raise ValueError("source/candidate/promotion graph differs")
    for i, (asset, reference) in enumerate(zip(manifest.assets[8:12], promotion.qualifications, strict=True)):
        raw_capture = read_file(directory / ("qualification-" + str(i) + ".capture.json"))
        actual = captures.decode_capture(raw_capture)
        _verify_capture_graph(actual, asset, binding, program=candidate.program)
        if (actual.result.score != 1 or reference.capture_sha256 != digest(raw_capture)
                or reference.ids != asset.ids or reference.task_id != asset.task.name
                or reference.task_fingerprint != asset.task_fingerprint or reference.db_sha256 != asset.db_sha256
                or reference.result != actual.result or report["qualification"][i]["score"] != 1):
            raise ValueError("four actual qualification captures do not match promotion")
    for i, record in enumerate(snapshot.requests):
        stem = digest(record.request_id.encode("utf-8"))
        request_raw = read_file(directory / (stem + ".request.json"))
        response_raw = read_file(directory / (stem + ".response.json"))
        telemetry = open_envelope(read_file(directory / (stem + ".receipt.json")), "sql_pilot_request_record")
        proposal = i == count - 1
        payload = proposal_payload(source_asset, source) if proposal else task_payload(
            manifest.assets[i], stage="development", library=[])
        if request_raw != build_request(profile.model, payload):
            raise ValueError("request bytes differ from frozen phase-one projection")
        if (telemetry["request_id"] != record.request_id or telemetry["request_sha256"] != digest(request_raw)
                or telemetry["response_sha256"] != digest(response_raw)
                or telemetry["actual_charge_usd_micros"] != record.actual_charge_micros
                or record.maximum_charge_micros != maximum_charge(profile)):
            raise ValueError("request telemetry/ledger graph differs")
        charge, receipt_sha = load_receipt(profile, record.request_id, digest(request_raw), digest(response_raw),
                                          evidence_root=billing_profile_path.parent)
        if charge != record.actual_charge_micros or receipt_sha != record.settlement_evidence_sha256:
            raise ValueError("authoritative receipt differs from settled ledger")
        if proposal:
            action = parse_response(response_raw, library=[], program_only=True)
            if action.program != candidate.program:
                raise ValueError("candidate is not the exact single proposal")
        else:
            asset = manifest.assets[i]
            record = report["development"][i]
            try:
                action = parse_response(response_raw, library=[], program_only=True)
            except ProtocolStop:
                raise ValueError("development protocol stop cannot qualify a checkpoint") from None
            except ModelActionError:
                capture_path = directory / ("development-" + asset.case_id + ".capture.json")
                if (record["failure_type"] != "MODEL_ACTION_INVALID" or record["score"] is not None
                        or record["route"] is not None or record["telemetry"] != telemetry
                        or capture_path.exists() or capture_path.is_symlink()):
                    raise ValueError("invalid development action requires exact invalid report and no capture")
                continue
            raw_capture = read_file(directory / ("development-" + asset.case_id + ".capture.json"))
            actual = captures.decode_capture(raw_capture)
            _verify_development_capture(actual, asset, binding, program=action.program,
                                        record=record, telemetry=telemetry)
    return obj, report, candidate, promotion


def _endpoint_request_ids(manifest):
    return [manifest.run_id + ":endpoint:" + a.case_id + ":" + arm
            for a, first in zip(manifest.assets[12:], manifest.pair_first, strict=True)
            for arm in (first, "L" if first == "B" else "B")]


def _claim_endpoint(directory, *, checkpoint_sha256, promotion_approval_sha256,
                    ledger_snapshot_sha256, request_ids):
    write_new(directory / "endpoint-claim.json", envelope_bytes("sql_pilot_endpoint_claim", {
        "checkpoint_sha256": checkpoint_sha256, "promotion_approval_sha256": promotion_approval_sha256,
        "ledger_snapshot_sha256": ledger_snapshot_sha256, "request_ids": request_ids}))


def _persist_endpoint_report(directory, report, snapshot):
    report["summary"] = summarize_pairs(report["pairs"])
    report["economics"] = _model_only_amortization(report)
    report["request_count"] = len(snapshot.requests)
    raw = envelope_bytes("sql_pilot_endpoint_report", report)
    target = directory / "endpoint-report.json"
    if target.exists() or target.is_symlink():
        safe_path(target, exists=True)
    pending = directory / "endpoint-report.pending.json"
    write_new(pending, raw)
    os.replace(pending, target)
    fsync_dir(directory)


def continue_pilot(manifest: PilotManifest, execution_profile: ExecutionProfile, *, output_dir: Path,
                   checkpoint_path: Path, checkpoint_sha256: str, promotion_approval_path: Path,
                   promotion_approval_sha256: str, billing_profile_path: Path, approval_sha256: str,
                   budget_dir: Path, allow_execution=False, allow_model_requests=False):
    require_optins(allow_execution, allow_model_requests)
    validate_manifest(manifest)
    safe_path(output_dir, exists=True, directory=True)
    directory = safe_path(output_dir / ("pilot-" + manifest.run_id), exists=True, directory=True)
    if (directory / "endpoint-claim.json").exists() or (directory / "endpoint-claim.json").is_symlink():
        raise ValueError("one-shot endpoint opportunity already claimed; no replay")
    profile = load_billing_profile(billing_profile_path, approval_sha256=approval_sha256)
    config = authorize(profile, approval_sha256, manifest=manifest,
                       execution_profile=execution_profile, budget_dir=budget_dir)
    ledger = BudgetLedger.open(str(budget_dir), config)
    snapshot = ledger.snapshot()
    build_execution_binding(execution_profile, source_root=installed_source_root())
    checkpoint, phase_one, candidate, promotion = _verify_checkpoint(
        directory, checkpoint_path, checkpoint_sha256, manifest, execution_profile, approval_sha256,
        budget_dir, snapshot, profile, billing_profile_path)
    safe_path(promotion_approval_path, exists=True)
    if promotion_approval_path.is_relative_to(directory):
        raise ValueError("promotion approval must be external to controller-owned run")
    approved = ApprovedSkill(candidate, promotion, checkpoint["promotion_sha256"],
                             promotion_approval_path, promotion_approval_sha256)
    validate_approval(approved)
    if _snapshot_sha(ledger.snapshot()) != checkpoint["ledger_snapshot_sha256"]:
        raise ValueError("ledger changed during continuation admission")
    _claim_endpoint(directory, checkpoint_sha256=checkpoint_sha256,
                    promotion_approval_sha256=promotion_approval_sha256,
                    ledger_snapshot_sha256=checkpoint["ledger_snapshot_sha256"],
                    request_ids=_endpoint_request_ids(manifest))
    # The claim is never removed, including exceptions, partial writes or death.
    if _snapshot_sha(ledger.snapshot()) != checkpoint["ledger_snapshot_sha256"]:
        raise ValueError("ledger changed after endpoint claim; claim retained")
    endpoint = directory / "endpoint"
    endpoint.mkdir(mode=0o700)
    fsync_dir(directory)
    report = strict_json(canonical_bytes(phase_one))
    report.update(status="INCOMPLETE", stop_reason=None, checkpoint_sha256=checkpoint_sha256,
                  promotion_approval_sha256=promotion_approval_sha256)
    _persist_endpoint_report(endpoint, report, ledger.snapshot())
    api = PilotAPI(billing_profile_path=billing_profile_path, approval_sha256=approval_sha256,
                   manifest=manifest, execution_profile=execution_profile, budget_dir=budget_dir,
                   output_dir=endpoint, allow_execution=True, allow_model_requests=True)
    executor = PilotExecutor(execution_profile, state_dir=endpoint / "execution")
    entry = library_entry(approved)
    pairs = report["pairs"]
    try:
        for i, asset in enumerate(manifest.assets[12:]):
            first = manifest.pair_first[i]
            for arm in (first, "L" if first == "B" else "B"):
                library = [] if arm == "B" else [entry]
                pairs[i][arm] = {"failure_type": "INFRA_MODEL_REQUEST", "score": None,
                                 "route": None, "telemetry": None}
                _persist_endpoint_report(endpoint, report, ledger.snapshot())
                try:
                    reply = api.request(manifest.run_id + ":endpoint:" + asset.case_id + ":" + arm,
                                        task_payload(asset, stage="endpoint", library=library), library=library)
                except ProtocolStop as error:
                    pairs[i][arm]["failure_type"] = "INFRA_PROVIDER_PROTOCOL"
                    pairs[i][arm]["telemetry"] = error.telemetry
                    raise
                except ModelActionError as error:
                    pairs[i][arm] = _model_failure(error)
                    _persist_endpoint_report(endpoint, report, ledger.snapshot())
                    continue
                started = time.monotonic_ns()
                try:
                    actual, route = route_action(reply.action, asset, executor=executor,
                                                 approved=approved if arm == "L" else None)
                except ModelActionError as error:
                    pairs[i][arm] = _model_failure(error)
                    pairs[i][arm]["telemetry"] = reply.telemetry
                    _persist_endpoint_report(endpoint, report, ledger.snapshot())
                    continue
                except ValueError:
                    pairs[i][arm].update(failure_type="INFRA_EXECUTION_BINDING", score=None,
                                         route=None, telemetry=reply.telemetry)
                    report["stop_reason"] = pairs[i][arm]["failure_type"]
                    _persist_endpoint_report(endpoint, report, ledger.snapshot())
                    return report
                execution_ms = (time.monotonic_ns() - started) // 1_000_000
                _persist_capture(endpoint, "endpoint-" + asset.case_id + "-" + arm, actual)
                pairs[i][arm] = capture_result(actual, route=route)
                pairs[i][arm].update(telemetry=reply.telemetry, execution_latency_ms=execution_ms,
                    model_plus_execution_latency_ms=execution_ms + reply.telemetry["latency_ms"])
                _persist_endpoint_report(endpoint, report, ledger.snapshot())
                if actual.execution_abort is not None:
                    report["stop_reason"] = pairs[i][arm]["failure_type"]
                    return report
        report["status"] = "COMPLETE" if summarize_pairs(pairs)["complete"] else "INCOMPLETE"
        return report
    except (FinancialBlocked, BudgetError):
        report["stop_reason"] = "financial or delivery uncertainty; STOP, reservation retained"
        return report
    except ProtocolStop:
        report["stop_reason"] = "provider tool protocol not established; STOP"
        return report
    finally:
        _persist_endpoint_report(endpoint, report, ledger.snapshot())


def check(manifest: PilotManifest, profile: ExecutionProfile, *, output_dir: Path):
    validate_manifest(manifest)
    safe_path(output_dir, exists=True, directory=True)
    build_execution_binding(profile, source_root=installed_source_root())
    return {"run_id": manifest.run_id, "assets": 20, "manifest_sha256": manifest_sha256(manifest),
            "execution_profile_sha256": execution_profile_sha256(profile),
            "runtime": "UNPROBED", "provider": "UNPROBED",
            "financial": "BLOCKED_UNTIL_EXTERNALLY_APPROVED_COMPLETE_PROFILE",
            "model_results": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "check", "init-budget", "run", "continue-endpoint"):
        child = sub.add_parser(name)
        child.add_argument("--manifest", type=Path, required=True)
        child.add_argument("--execution-profile", type=Path, required=True)
        child.add_argument("--output-dir", type=Path, required=True)
        if name == "prepare":
            child.add_argument("--run-id", required=True)
        if name in ("init-budget", "run", "continue-endpoint"):
            child.add_argument("--billing-profile", type=Path, required=True)
            child.add_argument("--billing-approval-sha256", required=True)
            child.add_argument("--budget-dir", type=Path, required=True)
        if name in ("run", "continue-endpoint"):
            child.add_argument("--allow-execution", action="store_true")
            child.add_argument("--allow-model-requests", action="store_true")
        if name == "continue-endpoint":
            child.add_argument("--checkpoint", type=Path, required=True)
            child.add_argument("--checkpoint-sha256", required=True)
            child.add_argument("--promotion-approval", type=Path, required=True)
            child.add_argument("--promotion-approval-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command in ("run", "continue-endpoint"):
        require_optins(args.allow_execution, args.allow_model_requests)
    safe_path(args.execution_profile, exists=True)
    profile = load_execution_profile(args.execution_profile, source_root=installed_source_root())
    if args.command == "prepare":
        result = prepare_manifest(args.manifest, output_dir=args.output_dir, run_id=args.run_id)
        print(canonical_bytes({"run_id": result.run_id, "assets": 20, "model_results": 0}).decode())
        return 0
    manifest = load_manifest(args.manifest)
    if args.command == "check":
        result = check(manifest, profile, output_dir=args.output_dir)
    elif args.command == "init-budget":
        safe_path(args.output_dir, exists=True, directory=True)
        init_budget(billing_profile_path=args.billing_profile,
                    approval_sha256=args.billing_approval_sha256, manifest=manifest,
                    execution_profile=profile, budget_dir=args.budget_dir)
        result = {"status": "LOCAL_BUDGET_CREATED", "model_results": 0}
    else:
        continuation = {}
        if args.command == "continue-endpoint":
            continuation = dict(checkpoint_path=args.checkpoint, checkpoint_sha256=args.checkpoint_sha256,
                promotion_approval_path=args.promotion_approval,
                promotion_approval_sha256=args.promotion_approval_sha256)
        function = continue_pilot if args.command == "continue-endpoint" else run_pilot
        result = function(manifest, profile, output_dir=args.output_dir,
                           billing_profile_path=args.billing_profile,
                           approval_sha256=args.billing_approval_sha256, budget_dir=args.budget_dir,
                           allow_execution=args.allow_execution, allow_model_requests=args.allow_model_requests,
                           **continuation)
        # Keep potentially model-authored evidence out of terminal output.
        print(canonical_bytes({"status": result["status"], "model_results_claim": False}).decode())
        return 0 if result["status"] in ("COMPLETE", "AWAITING_PROMOTION_APPROVAL") else 2
    print(canonical_bytes(result).decode())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, TypeError, OSError, FinancialBlocked, BudgetError):
        raise SystemExit("pilot refused; no unsafe fallback")
