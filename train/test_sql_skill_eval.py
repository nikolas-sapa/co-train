"""Real SQLite qualification, authority boundaries and fresh-process reuse."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from train.test_sql_skills import (
    PROGRAM, REJECT, api, canonical, envelope, ids, pin, promote, proposed,
    sentries, source_at, task_at, world,
)


class Truthy:
    def __bool__(self):
        return True


def reuse_case(evaluator, directory, label="eleven", rows=11, table=None):
    return evaluator.SkillCase(
        "reuse", task_at(directory, label, rows, table), ids(label, "reuse"),
    )


def rejected_before_dispatch(operation, counts):
    rejected = False
    try:
        operation()
    except REJECT:
        rejected = True
    assert counts["dispatch"] == 0, "admission sentry: candidate dispatched"
    assert rejected, "admission sentry: invalid authority was accepted"


@pytest.mark.parametrize("operation", ("evaluate", "promote", "reuse"))
@pytest.mark.parametrize("optin", ("missing", False, 1, Truthy()))
def test_all_execution_apis_require_literal_true(tmp_path, monkeypatch, operation, optin):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    receipt, _ = promote(module, evaluator, state)
    case = reuse_case(evaluator, tmp_path)
    counts = sentries(monkeypatch)
    kwargs = {} if optin == "missing" else {"allow_execution": optin}
    with pytest.raises(ValueError):
        if operation == "evaluate":
            evaluator.evaluate_candidate(state.candidate, state.cases[0], **kwargs)
        elif operation == "promote":
            evaluator.promote_candidate(
                state.candidate, source_capture=state.capture,
                expected_source_capture_sha256=state.source_pin, source_case=state.source,
                qualification_cases=state.cases, ids=state.approval_ids, **kwargs,
            )
        else:
            evaluator.reuse_promoted(
                state.candidate, receipt, case,
                expected_promotion_sha256=pin(module.encode_promotion(receipt)),
                ids=state.approval_ids, **kwargs,
            )
    assert counts == dict(build=0, dispatch=0, score=0)


def test_real_program_qualification_and_two_new_schema_transfers(tmp_path, monkeypatch):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    counts = sentries(monkeypatch)
    receipt, captures = promote(module, evaluator, state)
    assert receipt is not None
    assert len(captures) == 4 and counts["dispatch"] == 4
    assert counts["score"] == 5, "rerun sentry: source plus four protected scores required"
    assert len({case.task.gold_sql for case in state.cases}) == 4
    assert len({ref.task_fingerprint for ref in receipt.qualifications}) == 4
    assert len({ref.db_sha256 for ref in receipt.qualifications}) == 4
    for case, capture in zip(state.cases, captures):
        assert capture.terminal_label == "final_submitted"
        assert capture.result.valid is True and capture.result.score == 1
        assert len(capture.steps) == 1 and capture.refusals == ()
        assert capture.steps[0].action == PROGRAM
        assert capture.final_answer == case.task.gold_sql
        assert capture.ids == case.ids and capture.result.n_pred_rows == 1
        assert not hasattr(capture.steps[0], "task")
    approved_pin = pin(module.encode_promotion(receipt))
    for case in (
        reuse_case(evaluator, tmp_path, "eleven", 11),
        reuse_case(evaluator, tmp_path, "thirteen", 13, 'odd " table'),
    ):
        capture = evaluator.reuse_promoted(
            state.candidate, receipt, case, expected_promotion_sha256=approved_pin,
            ids=state.approval_ids, allow_execution=True,
        )
        assert capture.result.valid is True and capture.result.score == 1
        assert capture.final_answer == case.task.gold_sql
        assert len(capture.steps) == 1 and capture.refusals == ()
    assert counts["dispatch"] == 6 and counts["score"] == 7


@pytest.mark.parametrize("program", (
    "print('FINAL_SQL:SELECT 0')",
    "print('FINAL_SQL:SELECT COUNT(*) FROM origin')",
))
def test_constant_and_wrong_table_cannot_promote(tmp_path, monkeypatch, program):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    state.candidate = proposed(module, state.task, state.capture, program)
    counts = sentries(monkeypatch)
    receipt, captures = promote(module, evaluator, state)
    assert receipt is None and 1 <= len(captures) <= 4
    assert counts["dispatch"] == len(captures)
    assert any(c.result is not None and c.result.score == 0 for c in captures)
    assert all(len(c.steps) == 1 for c in captures)


@pytest.mark.parametrize("program", (
    "print('SELECT 1')", "print(' FINAL_SQL:SELECT 1')",
    "print('final_sql:SELECT 1')", "print('prose\\nFINAL_SQL:SELECT 1')",
    "print('FINAL_SQL:')", "print('FINAL_SQL:   ')", "print('nothing')",
    "print('FINAL_SQL:SELECT 1')\n1 / 0",
    "import os", "print(task)", "print(gold_sql)", "print(context)",
    "print('FINAL_SQL:SELECT 1')\nprint(().__class__)",
))
def test_bad_framing_rejection_and_runtime_error_abort_without_score(
    tmp_path, monkeypatch, program,
):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    candidate = proposed(module, state.task, state.capture, program)
    counts = sentries(monkeypatch)
    capture = evaluator.evaluate_candidate(candidate, state.cases[0], allow_execution=True)
    assert counts["dispatch"] == 1 and counts["score"] == 0
    assert capture.terminal_label == "aborted" and capture.result is None
    assert capture.final_answer is None and len(capture.steps) == 1


def test_well_framed_wrong_sql_is_real_zero_not_abort(tmp_path, monkeypatch):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    candidate = proposed(module, state.task, state.capture, "print('FINAL_SQL:SELECT 99')")
    counts = sentries(monkeypatch)
    capture = evaluator.evaluate_candidate(candidate, state.cases[0], allow_execution=True)
    assert capture.terminal_label == "final_submitted"
    assert capture.result.valid is True and capture.result.score == 0
    assert counts["dispatch"] == 1 and counts["score"] == 1


def test_sql_suffix_passed_unchanged_to_existing_finish(tmp_path, monkeypatch):
    from train import sql_capture

    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    suffix = "  ```sql\nSELECT COUNT(*) FROM empty;\n```  "
    candidate = proposed(module, state.task, state.capture, "print(" + repr("FINAL_SQL:" + suffix) + ")")
    original = sql_capture._CaptureSession.finish
    finals = []

    def finish(session, answer):
        finals.append(answer)
        return original(session, answer)

    monkeypatch.setattr(sql_capture._CaptureSession, "finish", finish)
    capture = evaluator.evaluate_candidate(candidate, state.cases[0], allow_execution=True)
    assert finals == [suffix] and capture.final_answer == suffix
    assert capture.result.score == 1


@pytest.mark.parametrize("limit", ("format", "extraction_work"))
def test_workflow_inherits_capture_bounds_before_extractor_or_score(
    tmp_path, monkeypatch, limit,
):
    from train import sql_episodes

    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    if limit == "format":
        program = "n = 8 * 1024 * 1024\nprint('FINAL_SQL:' + 'x' * n)"
    else:
        program = 'n = 2000000\nprint("FINAL_SQL:SELECT \'" + ";" * n + "\'")'
    candidate = proposed(module, state.task, state.capture, program)
    counts = sentries(monkeypatch)

    def forbidden_extract(text):
        raise AssertionError("bounds sentry: unbounded extractor reached")

    monkeypatch.setattr(sql_episodes, "extract_sql", forbidden_extract)
    with pytest.raises(ValueError):
        evaluator.evaluate_candidate(candidate, state.cases[0], allow_execution=True)
    assert counts["dispatch"] == 1 and counts["score"] == 0


def test_failed_qualification_stops_without_retry_or_success_receipt(tmp_path, monkeypatch):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    state.candidate = proposed(module, state.task, state.capture, "print('not framed')")
    counts = sentries(monkeypatch)
    receipt, captures = promote(module, evaluator, state)
    assert receipt is None and len(captures) == 1
    assert captures[0].terminal_label == "aborted" and captures[0].result is None
    assert counts["dispatch"] == 1 and counts["score"] == 1


def test_provisional_success_cannot_authorize_promotion(tmp_path, monkeypatch):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    provisional = evaluator.evaluate_candidate(state.candidate, state.cases[0], allow_execution=True)
    counts = sentries(monkeypatch)
    rejected_before_dispatch(
        lambda: promote(module, evaluator, state, qualification_cases=(provisional,) * 4),
        counts,
    )
    with pytest.raises(TypeError):
        promote(module, evaluator, state, reports=(provisional,) * 4)


def test_forged_recorded_zero_is_independently_rescored_before_dispatch(tmp_path, monkeypatch):
    from train.sql_capture import encode_capture, start_capture

    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    actual = start_capture(state.task, ids=state.capture.ids, allow_execution=True).finish(state.task.gold_sql)
    state.capture = dataclasses.replace(actual, result=state.capture.result)
    state.candidate = proposed(module, state.task, state.capture)
    state.source_pin = pin(encode_capture(state.capture))
    counts = sentries(monkeypatch)
    rejected_before_dispatch(lambda: promote(module, evaluator, state), counts)
    assert counts["score"] == 1, "rescore sentry: external final must reach protected scorer"


@pytest.mark.parametrize("change", (
    "pin", "source_ref", "source_ids", "source_role", "source_task",
    "source_db", "source_sidecar", "instrument", "runtime",
    "aborted", "invalid_gold",
))
def test_origin_binding_changes_reject_before_candidate_execution(
    tmp_path, monkeypatch, change,
):
    from train import sql_capture, sql_episodes

    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    kwargs = {}
    if change == "pin":
        kwargs["expected_source_capture_sha256"] = "0" * 64
    elif change == "source_ref":
        state.candidate = dataclasses.replace(
            state.candidate, source=dataclasses.replace(state.candidate.source, db_sha256="0" * 64),
        )
    elif change == "source_ids":
        state.source = dataclasses.replace(state.source, ids=ids("different"))
    elif change == "source_role":
        state.source = dataclasses.replace(state.source, role="reuse")
    elif change == "source_task":
        state.source = dataclasses.replace(
            state.source, task=dataclasses.replace(state.task, question="Changed"),
        )
    elif change == "source_db":
        import sqlite3

        with sqlite3.connect(state.task.db_path) as connection:
            connection.execute("INSERT INTO origin VALUES (999)")
    elif change == "source_sidecar":
        Path(state.task.db_path + "-wal").write_bytes(b"unbound")
    elif change == "instrument":
        state.capture = dataclasses.replace(
            state.capture, instrument=dataclasses.replace(state.capture.instrument, source_sha256="0" * 64),
        )
        state.candidate = proposed(module, state.task, state.capture)
        state.source_pin = pin(sql_capture.encode_capture(state.capture))
    elif change == "runtime":
        monkeypatch.setattr(sql_episodes.sql_arms, "WRAPPER_TIMEOUT", 123.0)
    elif change == "aborted":
        state.capture = dataclasses.replace(
            state.capture, terminal_label="aborted", result=None,
            final_answer=None, extracted_sql=None,
        )
        state.source_pin = pin(sql_capture.encode_capture(state.capture))
    else:
        # An actually invalid source is rejected even if its declared score is
        # forged into a valid zero; the gold stays host-only.
        task = dataclasses.replace(state.task, gold_sql="SELECT * FROM missing")
        captured = sql_capture.start_capture(task, ids=state.capture.ids, allow_execution=True).finish("SELECT -1")
        state.capture = dataclasses.replace(captured, result=state.capture.result)
        state.task = task
        state.source = dataclasses.replace(state.source, task=task)
        state.candidate = proposed(module, task, state.capture)
        state.source_pin = pin(sql_capture.encode_capture(state.capture))
    counts = sentries(monkeypatch)
    rejected_before_dispatch(lambda: promote(module, evaluator, state, **kwargs), counts)
    if change != "invalid_gold":
        assert counts["score"] == 0


@pytest.mark.parametrize("change", (
    "list", "generator", "three", "five", "report", "role", "scope",
    "corpus", "policy", "revision", "source_split", "episode_duplicate",
    "task_duplicate", "db_duplicate", "origin_task", "origin_db", "last_sidecar",
))
def test_all_four_qualification_inputs_admitted_before_any_dispatch(
    tmp_path, monkeypatch, change,
):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    cases = list(state.cases)
    if change == "list":
        supplied = cases
    elif change == "generator":
        supplied = iter(cases)
    elif change == "three":
        supplied = tuple(cases[:3])
    elif change == "five":
        supplied = tuple(cases + [cases[0]])
    elif change == "report":
        supplied = ({"score": 1},) * 4
    else:
        last = cases[-1]
        if change == "role":
            last = dataclasses.replace(last, role="reuse")
        elif change == "scope":
            last = dataclasses.replace(last, task=dataclasses.replace(last.task, shape="other"))
        elif change in {"corpus", "policy", "revision", "source_split", "episode_duplicate"}:
            field, value = {
                "corpus": ("corpus_id", "other"),
                "policy": ("policy_id", "other"),
                "revision": ("policy_revision", "other"),
                "source_split": ("split_id", state.capture.ids.split_id),
                "episode_duplicate": ("episode_id", cases[0].ids.episode_id),
            }[change]
            last = dataclasses.replace(last, ids=dataclasses.replace(last.ids, **{field: value}))
        elif change == "task_duplicate":
            # Same non-path task payload, different DB content.
            last = dataclasses.replace(last, task=dataclasses.replace(cases[0].task, db_path=last.task.db_path))
        elif change == "db_duplicate":
            last = dataclasses.replace(last, task=dataclasses.replace(last.task, db_path=cases[0].task.db_path))
        elif change == "origin_task":
            last = dataclasses.replace(last, task=dataclasses.replace(state.task, db_path=last.task.db_path))
        elif change == "origin_db":
            last = dataclasses.replace(last, task=dataclasses.replace(last.task, db_path=state.task.db_path))
        else:
            Path(last.task.db_path + "-shm").write_bytes(b"unbound")
        cases[-1] = last
        supplied = tuple(cases)
    counts = sentries(monkeypatch)
    rejected_before_dispatch(
        lambda: promote(module, evaluator, state, qualification_cases=supplied), counts,
    )


def test_actual_qualification_reruns_are_required_not_report_labels(tmp_path, monkeypatch):
    """A removed dispatch loop must fail this assertion, not an import/digest."""
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    counts = sentries(monkeypatch)
    receipt, captures = promote(module, evaluator, state)
    assert counts["dispatch"] == 4, "rerun sentry: four actual candidate dispatches required"
    assert counts["score"] == 5, "rerun sentry: five actual protected scores required"
    assert receipt is not None and len(captures) == 4
    assert all(ref.role == "qualification" for ref in receipt.qualifications)


@pytest.mark.parametrize("change", (
    "pin", "ids", "program", "candidate_id", "scope", "source",
    "manifest", "workflow_binding", "runtime_binding", "current_workflow",
    "case_scope", "case_role", "case_ids",
))
def test_reuse_checks_approved_pin_candidate_manifest_scope_binding_and_ids(
    tmp_path, monkeypatch, change,
):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    receipt, _ = promote(module, evaluator, state)
    case = reuse_case(evaluator, tmp_path)
    approved = pin(module.encode_promotion(receipt))
    candidate, external_ids = state.candidate, state.approval_ids
    if change == "pin":
        approved = "0" * 64
    elif change == "ids":
        external_ids = ids("wrong-approval", "approval")
    elif change == "program":
        candidate = dataclasses.replace(candidate, program="print('FINAL_SQL:SELECT 0')")
    elif change == "candidate_id":
        candidate = dataclasses.replace(candidate, skill_id="another-skill")
    elif change == "scope":
        candidate = dataclasses.replace(candidate, scope=dataclasses.replace(candidate.scope, shape="other"))
    elif change == "source":
        candidate = dataclasses.replace(candidate, source=dataclasses.replace(candidate.source, capture_sha256="0" * 64))
    elif change == "manifest":
        refs = list(receipt.qualifications)
        refs[0] = dataclasses.replace(refs[0], capture_sha256="0" * 64)
        receipt = dataclasses.replace(receipt, qualifications=tuple(refs))
    elif change == "workflow_binding":
        receipt = dataclasses.replace(
            receipt, binding=dataclasses.replace(receipt.binding, source_sha256="0" * 64),
        )
        approved = pin(module.encode_promotion(receipt))
    elif change == "runtime_binding":
        receipt = dataclasses.replace(
            receipt, binding=dataclasses.replace(
                receipt.binding, instrument=dataclasses.replace(
                    receipt.binding.instrument, program_timeout_s=123.0,
                ),
            ),
        )
        approved = pin(module.encode_promotion(receipt))
    elif change == "current_workflow":
        # Redirect source reads to changed, caller-controlled evaluator bytes.
        root = tmp_path / "changed-code"
        for name in ("train/sql_skills.py", "train/sql_skill_eval.py"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            original = Path(module.__file__).resolve().parents[1] / name
            path.write_bytes(original.read_bytes() + b"\n# changed evaluator\n")
        monkeypatch.setattr(evaluator, "_ROOT", root)
    elif change == "case_scope":
        case = dataclasses.replace(case, task=dataclasses.replace(case.task, source="other"))
    elif change == "case_role":
        case = dataclasses.replace(case, role="qualification")
    else:
        case = dataclasses.replace(case, ids=dataclasses.replace(case.ids, corpus_id="other"))
    counts = sentries(monkeypatch)
    rejected_before_dispatch(lambda: evaluator.reuse_promoted(
        candidate, receipt, case, expected_promotion_sha256=approved,
        ids=external_ids, allow_execution=True,
    ), counts)
    assert counts["score"] == 0


def test_fresh_process_receipt_reuse_after_origin_and_qualifications_deleted(tmp_path):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    receipt, captures = promote(module, evaluator, state)
    candidate_file, receipt_file = tmp_path / "candidate.json", tmp_path / "promotion.json"
    candidate_file.write_bytes(module.encode_candidate(state.candidate))
    receipt_file.write_bytes(module.encode_promotion(receipt))
    cases = (
        reuse_case(evaluator, tmp_path, "fresh-eleven", 11),
        reuse_case(evaluator, tmp_path, "fresh-thirteen", 13, 'fresh " identifier'),
    )
    for case in (state.source,) + state.cases:
        Path(case.task.db_path).unlink()
    code = '''import dataclasses, json, sys
from pathlib import Path
from bench.task import SqlTask
from ptc import sql_arms
from train.sql_episodes import EpisodeIds
from train.sql_skills import decode_candidate, decode_promotion
from train.sql_skill_eval import SkillCase, reuse_promoted
candidate = decode_candidate(Path(sys.argv[1]).read_bytes())
promotion = decode_promotion(Path(sys.argv[2]).read_bytes())
manifest = json.loads(sys.argv[3])
dispatches = []
original = sql_arms.ArmPair.run
def counted(pair, arm, action, **kwargs):
    dispatches.append(action)
    return original(pair, arm, action, **kwargs)
sql_arms.ArmPair.run = counted
results = []
for item in manifest["cases"]:
    case = SkillCase("reuse", SqlTask(**item["task"]), EpisodeIds(**item["ids"]))
    capture = reuse_promoted(candidate, promotion, case,
        expected_promotion_sha256=manifest["approved_pin"],
        ids=EpisodeIds(**manifest["ids"]), allow_execution=True)
    assert capture.result.valid is True and capture.result.score == 1
    assert len(capture.steps) == 1 and capture.refusals == ()
    assert capture.final_answer == case.task.gold_sql
    results.append(dataclasses.asdict(capture.result))
assert len(dispatches) == 2
print(json.dumps({"dispatches": len(dispatches), "results": results}, sort_keys=True))
'''
    manifest = dict(
        approved_pin=pin(receipt_file.read_bytes()), ids=dataclasses.asdict(state.approval_ids),
        cases=[dict(task=dataclasses.asdict(c.task), ids=dataclasses.asdict(c.ids)) for c in cases],
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(candidate_file), str(receipt_file),
         json.dumps(manifest)],
        cwd=Path(module.__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["dispatches"] == 2
    assert [row["score"] for row in report["results"]] == [1, 1]
    assert all(row["valid"] is True for row in report["results"])
    report.update(
        approved_promotion_sha256=manifest["approved_pin"],
        candidate_sha256=pin(candidate_file.read_bytes()),
        origin_exists=Path(state.task.db_path).exists(),
        qualification_captures=len(captures),
        returncode=result.returncode,
    )
    (tmp_path / "fresh-process-reuse-receipt.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
    )


def test_host_only_cases_are_exact_frozen_records(tmp_path):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.source.task = None
    for role, task, declared_ids in (
        ("unknown", state.task, state.source.ids),
        ("qualification", dataclasses.asdict(state.task), state.source.ids),
        ("reuse", state.task, dataclasses.asdict(state.source.ids)),
    ):
        with pytest.raises(REJECT):
            evaluator.SkillCase(role, task, declared_ids)


def test_native_discovery_and_default_unbound_environment_unchanged():
    module, evaluator = api(), api("sql_skill_eval")
    from train.grpo_ptc import PTCEnvironment, THE_TOOL_SCHEMA

    environment = PTCEnvironment(8)
    assert environment.tools == (THE_TOOL_SCHEMA,)
    assert [tool["function"]["name"] for tool in environment.tools] == ["run_program"]
    with pytest.raises(NotImplementedError):
        environment.step("print(1)")


def isolated_world(tmp_path, monkeypatch):
    """Call-graph unit fixture, not actual runtime qualification evidence."""
    from bench.score import ExResult
    from ptc import sql_isolation as isolation
    from train import sql_capture
    from train.test_sql_capture import isolation_executor, isolation_methods, isolation_score_receipt
    from types import SimpleNamespace

    module, evaluator = api(), api("sql_skill_eval")
    executor = isolation_executor(tmp_path)
    calls = isolation_methods(monkeypatch)
    def scorer(self, sql, task, **kwargs):
        calls.append(("scorer", sql, kwargs))
        match = sql != "SELECT -1"
        result = ExResult(float(match), "match" if match else "mismatch", True, "", 1, 1)
        return isolation.ScoreOutcome(result, None, isolation_score_receipt(sql, task, kwargs))
    monkeypatch.setattr(isolation.PilotExecutor, "score_sql", scorer)
    task = task_at(tmp_path, "v2-origin", 2)
    actual = sql_capture.start_capture(task, ids=ids(), allow_execution=True,
                                       executor=executor).finish("SELECT -1")
    candidate = proposed(module, task, actual)
    cases = tuple(evaluator.SkillCase(
        "qualification", task_at(tmp_path, "v2-q" + str(i), i),
        ids("v2-q" + str(i), "qualification"),
    ) for i in range(4))
    calls.clear()
    state = SimpleNamespace(
        capture=actual, task=task, candidate=candidate, executor=executor,
        source=evaluator.SkillCase("source_failure", task, actual.ids), cases=cases,
        approval_ids=ids("approval", "approval"),
        source_pin=pin(sql_capture.encode_capture(actual)),
    )
    return state, calls


def test_isolated_promotion_four_reruns_rescore_and_v2_receipt(tmp_path, monkeypatch):
    evaluator, module = api("sql_skill_eval"), api()
    assert "executor" in __import__("inspect").signature(evaluator.promote_candidate).parameters, "v2 promotion missing"
    state, calls = isolated_world(tmp_path, monkeypatch)
    receipt, captures = promote(module, evaluator, state, executor=state.executor)
    assert receipt.schema_version == 2 and len(captures) == 4
    assert [c[0] for c in calls] == ["scorer"] + ["program", "scorer"] * 4, "qualification/rerun sentry"
    assert receipt.binding.execution_binding == state.executor.profile.binding
    assert len({ref.db_sha256 for ref in receipt.qualifications}) == 4
    for ref, actual in zip(receipt.qualifications, captures):
        assert ref.capture_sha256 == pin(__import__("train.sql_capture", fromlist=["encode_capture"]).encode_capture(actual))
    encoded = module.encode_promotion(receipt)
    assert module.encode_promotion(module.decode_promotion(encoded)) == encoded
    calls.clear()
    case = reuse_case(evaluator, tmp_path, "isolated-fresh")
    actual = evaluator.reuse_promoted(
        state.candidate, receipt, case, expected_promotion_sha256=pin(encoded),
        ids=state.approval_ids, allow_execution=True, executor=state.executor,
    )
    assert actual.schema_version == 2 and actual.result.score == 1
    assert [c[0] for c in calls] == ["program", "scorer"]


def test_isolated_rejection_cannot_qualify_or_originate(tmp_path, monkeypatch):
    from train.test_sql_capture import isolation_methods
    evaluator, module = api("sql_skill_eval"), api()
    assert "executor" in __import__("inspect").signature(evaluator.evaluate_candidate).parameters, "v2 evaluation missing"
    state, _ = isolated_world(tmp_path, monkeypatch)
    calls = isolation_methods(monkeypatch, observation="FINAL_SQL:SELECT 1\nfailure", rejected=True)
    actual = evaluator.evaluate_candidate(state.candidate, state.cases[0],
        allow_execution=True, executor=state.executor)
    assert actual.terminal_label == "program_rejected", "native rejected flag lost"
    assert actual.result is None and actual.execution_abort is None
    assert [c[0] for c in calls] == ["program"]
    with pytest.raises(ValueError):
        proposed(module, state.cases[0].task, actual)


def test_isolated_origin_is_actually_rescored_before_program(tmp_path, monkeypatch):
    from train import sql_capture
    evaluator, module = api("sql_skill_eval"), api()
    assert "executor" in __import__("inspect").signature(evaluator.promote_candidate).parameters, "v2 origin missing"
    state, calls = isolated_world(tmp_path, monkeypatch)
    actual = sql_capture.start_capture(state.task, ids=state.capture.ids,
        allow_execution=True, executor=state.executor).finish("SELECT 1")
    state.capture = dataclasses.replace(actual, result=state.capture.result)
    state.candidate = proposed(module, state.task, state.capture)
    state.source_pin = pin(sql_capture.encode_capture(state.capture))
    calls.clear()
    with pytest.raises(ValueError, match="independently rescore"):
        promote(module, evaluator, state, executor=state.executor)
    assert [c[0] for c in calls] == ["scorer"], "source rescore sentry"


@pytest.mark.parametrize("change", ("pin", "scope", "no_executor", "v1_approval", "wrong_engine"))
def test_isolated_reuse_guard_before_any_backend(tmp_path, monkeypatch, change):
    evaluator, module = api("sql_skill_eval"), api()
    assert "executor" in __import__("inspect").signature(evaluator.reuse_promoted).parameters, "v2 reuse missing"
    state, calls = isolated_world(tmp_path, monkeypatch)
    receipt, _ = promote(module, evaluator, state, executor=state.executor)
    executor = state.executor
    case = reuse_case(evaluator, tmp_path, "isolated-guard")
    approved = pin(module.encode_promotion(receipt))
    if change == "pin":
        approved = "0" * 64
    elif change == "scope":
        case = dataclasses.replace(case, task=dataclasses.replace(case.task, shape="wrong"))
    elif change == "no_executor":
        executor = None
    elif change == "v1_approval":
        receipt = dataclasses.replace(receipt, schema_version=1,
            binding=dataclasses.replace(receipt.binding, execution_binding=None))
        approved = pin(module.encode_promotion(receipt))
    else:
        from ptc import sql_isolation as isolation
        old = executor.profile.binding
        scorer = dataclasses.replace(old.scorer, sources=old.scorer.sources + (
            isolation.SourcePin("train/guards.py",
                pin((Path(__file__).resolve().parents[1] / "train/guards.py").read_bytes())),
        ))
        executor = isolation.PilotExecutor(
            dataclasses.replace(executor.profile, binding=dataclasses.replace(old, scorer=scorer)),
            state_dir=tmp_path / "different-run",
        )
    calls.clear()
    rejected = False
    try:
        evaluator.reuse_promoted(state.candidate, receipt, case,
            expected_promotion_sha256=approved, ids=state.approval_ids,
            allow_execution=True, executor=executor)
    except REJECT:
        rejected = True
    assert calls == [], "approval/routing/binding sentry: unauthorized backend"
    assert rejected


@pytest.mark.parametrize("change", ("three", "duplicate", "source_split", "db_duplicate"))
def test_isolated_all_four_qualification_assets_before_program(tmp_path, monkeypatch, change):
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    cases = list(state.cases)
    if change == "three":
        cases.pop()
    elif change == "duplicate":
        cases[-1] = cases[0]
    elif change == "source_split":
        cases[-1] = dataclasses.replace(cases[-1], ids=dataclasses.replace(
            cases[-1].ids, split_id=state.source.ids.split_id,
        ))
    else:
        cases[-1] = dataclasses.replace(cases[-1], task=dataclasses.replace(
            cases[-1].task, db_path=cases[0].task.db_path,
        ))
    rejected = False
    try:
        promote(module, evaluator, state, qualification_cases=tuple(cases),
                executor=state.executor)
    except REJECT:
        rejected = True
    assert [c[0] for c in calls] == ["scorer"], "qualification admission sentry: PROGRAM dispatched"
    assert rejected


def test_isolated_native_rejection_cannot_be_qualification_success(tmp_path, monkeypatch):
    from ptc import sql_isolation as isolation
    from train.test_sql_capture import isolation_program_receipt
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    def rejected(self, code, **kwargs):
        calls.append(("program", code, kwargs))
        return isolation.ProgramOutcome(
            "FINAL_SQL:SELECT 1\nrejected", None, isolation_program_receipt(code, kwargs), rejected=True,
        )
    monkeypatch.setattr(isolation.PilotExecutor, "run_program", rejected)
    receipt, actuals = promote(module, evaluator, state, executor=state.executor)
    assert receipt is None and len(actuals) == 1
    assert actuals[0].terminal_label == "program_rejected"
    assert actuals[0].result is None and actuals[0].execution_abort is None
    assert [c[0] for c in calls] == ["scorer", "program"]


@pytest.mark.parametrize("text", (
    "SELECT 1", " FINAL_SQL:SELECT 1", "prose\nFINAL_SQL:SELECT 1",
    "final_sql:SELECT 1", "FINAL_SQL:", "FINAL_SQL:   ",
))
def test_isolated_framing_never_scores_malformed(tmp_path, monkeypatch, text):
    from train.test_sql_capture import isolation_methods
    evaluator = api("sql_skill_eval")
    state, _ = isolated_world(tmp_path, monkeypatch)
    calls = isolation_methods(monkeypatch, observation=text)
    actual = evaluator.evaluate_candidate(
        state.candidate, state.cases[0], allow_execution=True, executor=state.executor,
    )
    assert actual.terminal_label == "aborted" and actual.result is None
    assert actual.steps[0].observation == text
    assert [c[0] for c in calls] == ["program"]


def test_isolated_well_framed_wrong_sql_keeps_valid_zero_and_suffix(tmp_path, monkeypatch):
    from bench.score import ExResult
    from train.test_sql_capture import isolation_methods
    evaluator = api("sql_skill_eval")
    state, _ = isolated_world(tmp_path, monkeypatch)
    suffix = "  SELECT 99;  "
    calls = isolation_methods(monkeypatch, observation="FINAL_SQL:" + suffix,
        score=ExResult(0.0, "mismatch", True, "", 1, 1))
    actual = evaluator.evaluate_candidate(
        state.candidate, state.cases[0], allow_execution=True, executor=state.executor,
    )
    assert actual.final_answer == suffix and actual.terminal_label == "final_submitted"
    assert actual.result.valid is True and actual.result.score == 0.0
    assert [c[0] for c in calls] == ["program", "scorer"]


def test_isolated_stale_scorer_success_cannot_qualify_next_database(tmp_path, monkeypatch):
    from ptc import sql_isolation as isolation
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    original = isolation.PilotExecutor.score_sql
    previous = []
    def stale(self, sql, task, **kwargs):
        actual = original(self, sql, task, **kwargs)
        if task == state.cases[0].task:
            previous.append(actual)
        if task == state.cases[1].task:
            assert len(previous) == 1
            assert actual.receipt.request_sha256 != previous[0].receipt.request_sha256
            return previous[0]
        return actual
    monkeypatch.setattr(isolation.PilotExecutor, "score_sql", stale)
    receipt, actuals = promote(module, evaluator, state, executor=state.executor)
    assert receipt is None, "qualification receipt sentry: stale EX1 promoted"
    assert len(actuals) == 2
    assert actuals[0].result.valid is True and actuals[0].result.score == 1.0
    assert actuals[1].result is None and actuals[1].terminal_label == "execution_aborted"
    assert actuals[1].execution_abort == isolation.AbortInfo("scorer", "protocol")
    assert [r.role for r in actuals[1].runtime_receipts] == ["program"]
    assert previous[0].receipt not in actuals[1].runtime_receipts
    assert [c[0] for c in calls] == ["scorer", "program", "scorer", "program", "scorer"]


@pytest.mark.parametrize("with_receipt", (False, True))
def test_isolated_later_program_abort_retains_qualification_prefix(tmp_path, monkeypatch, with_receipt):
    from ptc import sql_isolation as isolation
    from train import sql_capture
    from train.test_sql_capture import isolation_program_receipt
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    original = isolation.PilotExecutor.run_program
    dispatched, abort_receipts = [], []
    def program(self, code, **kwargs):
        dispatched.append(kwargs["db_path"])
        if kwargs["db_path"] == state.cases[2].task.db_path:
            calls.append(("program", code, kwargs))
            receipt = isolation_program_receipt(code, kwargs) if with_receipt else None
            abort_receipts.append(receipt)
            return isolation.ProgramOutcome(
                None, isolation.AbortInfo("program", "memory"), receipt,
            )
        return original(self, code, **kwargs)
    monkeypatch.setattr(isolation.PilotExecutor, "run_program", program)
    try:
        promotion, actuals = promote(module, evaluator, state, executor=state.executor)
    except sql_capture.CaptureExecutionAborted as exc:
        # Historical behavior exposes only the third capture, losing successes.
        promotion, actuals = None, (exc.capture,)
    assert len(actuals) == 3, "qualification retention sentry: completed prefix lost"
    assert promotion is None
    assert tuple(c.ids for c in actuals) == tuple(c.ids for c in state.cases[:3])
    assert tuple(c.task_id for c in actuals) == tuple(c.task.name for c in state.cases[:3])
    for actual in actuals[:2]:
        assert actual.terminal_label == "final_submitted"
        assert actual.result.valid is True and actual.result.score == 1.0
        assert actual.steps[0].action == state.candidate.program
        assert [r.role for r in actual.runtime_receipts] == ["program", "scorer"]
    failed = actuals[2]
    assert failed.terminal_label == "execution_aborted" and failed.result is None
    assert failed.execution_abort == isolation.AbortInfo("program", "memory")
    assert failed.steps == () and failed.final_answer is failed.extracted_sql is None
    assert failed.runtime_receipts == (() if not with_receipt else (abort_receipts[0],))
    assert sql_capture.decode_capture(sql_capture.encode_capture(failed)) == failed
    assert dispatched == [case.task.db_path for case in state.cases[:3]]
    assert state.cases[3].task.db_path not in dispatched
    assert [c[0] for c in calls] == ["scorer", "program", "scorer", "program", "scorer", "program"]


@pytest.mark.parametrize("operation", ("source_rescore", "direct_evaluation"))
def test_isolated_abort_outside_qualification_still_raises(tmp_path, monkeypatch, operation):
    from ptc import sql_isolation as isolation
    from train import sql_capture
    from train.test_sql_capture import isolation_program_receipt, isolation_score_receipt
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    stage = "scorer" if operation == "source_rescore" else "program"
    receipts = []
    def aborted(self, text, *args, **kwargs):
        calls.append((stage, text, kwargs))
        receipt = (isolation_program_receipt(text, kwargs) if stage == "program"
                   else isolation_score_receipt(text, args[0], kwargs))
        receipts.append(receipt)
        abort = isolation.AbortInfo(stage, "memory")
        return (isolation.ProgramOutcome(None, abort, receipt) if stage == "program"
                else isolation.ScoreOutcome(None, abort, receipt))
    monkeypatch.setattr(isolation.PilotExecutor,
                        "score_sql" if stage == "scorer" else "run_program", aborted)
    with pytest.raises(sql_capture.CaptureExecutionAborted) as raised:
        if operation == "source_rescore":
            promote(module, evaluator, state, executor=state.executor)
        else:
            evaluator.evaluate_candidate(state.candidate, state.cases[0],
                allow_execution=True, executor=state.executor)
    actual = raised.value.capture
    assert actual.result is None and actual.terminal_label == "execution_aborted"
    assert actual.execution_abort == isolation.AbortInfo(stage, "memory")
    assert actual.runtime_receipts[-1] == receipts[0]
    assert [c[0] for c in calls] == [stage]


def _dbpin_case(case, expected):
    fields = {f.name: f for f in dataclasses.fields(type(case))}
    assert "expected_db_sha256" in fields, "dbpin SkillCase field missing"
    return dataclasses.replace(case, expected_db_sha256=expected)


def test_dbpin_skill_case_three_positional_frozen_kw_only(tmp_path):
    evaluator = api("sql_skill_eval")
    task = task_at(tmp_path, "dbpin-case", 1)
    case = evaluator.SkillCase("qualification", task, ids("case", "qualification"))
    fields = {f.name: f for f in dataclasses.fields(case)}
    assert "expected_db_sha256" in fields, "dbpin SkillCase field missing"
    assert fields["expected_db_sha256"].kw_only and case.expected_db_sha256 is None
    assert dataclasses.is_dataclass(case) and type(case).__dataclass_params__.frozen
    with pytest.raises(TypeError):
        evaluator.SkillCase(case.role, case.task, case.ids, "a" * 64)
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.expected_db_sha256 = "a" * 64
    assert _dbpin_case(case, "a" * 64).expected_db_sha256 == "a" * 64


@pytest.mark.parametrize("expected", ("", "a" * 63, "a" * 65, "A" * 64, "g" * 64,
                                    True, False, 1, b"a" * 64))
def test_dbpin_skill_case_strict_digest(tmp_path, expected):
    evaluator = api("sql_skill_eval")
    case = evaluator.SkillCase("qualification", task_at(tmp_path, "dbpin-case", 1),
                               ids("case", "qualification"))
    assert "expected_db_sha256" in {f.name for f in dataclasses.fields(case)}, "dbpin SkillCase field missing"
    with pytest.raises(REJECT):
        _dbpin_case(case, expected)


def test_dbpin_case_propagates_evaluation_source_four_qualifications_reuse(tmp_path, monkeypatch):
    from train import sql_capture
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    digest = sql_capture.evidence._db_digest
    state.source = _dbpin_case(state.source, state.capture.db_sha256)
    state.cases = tuple(_dbpin_case(c, digest(c.task)) for c in state.cases)
    starts = []
    original = sql_capture.start_capture
    def start(task, **kwargs):
        starts.append((task.name, kwargs.get("expected_db_sha256")))
        return original(task, **kwargs)
    monkeypatch.setattr(sql_capture, "start_capture", start)
    actual = evaluator.evaluate_candidate(state.candidate, state.cases[0],
        allow_execution=True, executor=state.executor)
    assert actual.db_sha256 == state.cases[0].expected_db_sha256
    assert starts == [(state.cases[0].task.name, state.cases[0].expected_db_sha256)], "dbpin case propagation lost"
    calls.clear()
    starts.clear()
    receipt, captures = promote(module, evaluator, state, executor=state.executor)
    assert receipt is not None and len(captures) == 4
    assert starts == [(c.task.name, c.expected_db_sha256) for c in state.cases]
    assert [c[2]["db_sha256"] for c in calls] == [state.source.expected_db_sha256] + [
        c.expected_db_sha256 for c in state.cases for _ in range(2)
    ]
    case = reuse_case(evaluator, tmp_path, "dbpin-heldout")
    case = _dbpin_case(case, digest(case.task))
    starts.clear()
    calls.clear()
    actual = evaluator.reuse_promoted(state.candidate, receipt, case,
        expected_promotion_sha256=pin(module.encode_promotion(receipt)),
        ids=state.approval_ids, allow_execution=True, executor=state.executor)
    assert actual.db_sha256 == case.expected_db_sha256
    assert starts == [(case.task.name, case.expected_db_sha256)]
    assert [c[2]["db_sha256"] for c in calls] == [case.expected_db_sha256] * 2


@pytest.mark.parametrize("operation", ("evaluate", "qualifications", "reuse", "origin"))
def test_dbpin_case_expectation_not_freshly_rebound(tmp_path, monkeypatch, operation):
    from train import sql_capture
    evaluator, module = api("sql_skill_eval"), api()
    state, calls = isolated_world(tmp_path, monkeypatch)
    receipt = None
    if operation == "reuse":
        receipt, _ = promote(module, evaluator, state, executor=state.executor)
        case = reuse_case(evaluator, tmp_path, "dbpin-heldout")
    else:
        case = state.source if operation == "origin" else state.cases[0]
    expected = sql_capture.evidence._db_digest(case.task)
    case = _dbpin_case(case, "f" * 64 if operation == "origin" else expected)
    if operation != "origin":
        path = Path(case.task.db_path)
        path.write_bytes(path.read_bytes() + b"replacement")
    calls.clear()
    rejected = False
    try:
        if operation == "evaluate":
            evaluator.evaluate_candidate(state.candidate, case, allow_execution=True, executor=state.executor)
        elif operation == "qualifications":
            evaluator._admit_qualifications(state.candidate, (case,) + state.cases[1:])
        elif operation == "origin":
            state.source = case
            promote(module, evaluator, state, executor=state.executor)
        else:
            evaluator.reuse_promoted(state.candidate, receipt, case,
                expected_promotion_sha256=pin(module.encode_promotion(receipt)),
                ids=state.approval_ids, allow_execution=True, executor=state.executor)
    except ValueError:
        rejected = True
    assert rejected, "dbpin admission sentry: external expectation ignored"
    assert calls == [], "dbpin admission sentry: dispatched before frozen admission"


def test_dbpin_conflicting_admitted_and_case_expectations_zero_dispatch(tmp_path, monkeypatch):
    from train import sql_capture
    evaluator = api("sql_skill_eval")
    state, calls = isolated_world(tmp_path, monkeypatch)
    case = _dbpin_case(state.cases[0], sql_capture.evidence._db_digest(state.cases[0].task))
    with pytest.raises(ValueError):
        evaluator._execute(state.candidate, case, expected_db_sha256="f" * 64, executor=state.executor)
    assert calls == []


def test_dbpin_aba_around_outer_checks_never_adopts_replacement(tmp_path, monkeypatch):
    from train import sql_capture
    evaluator = api("sql_skill_eval")
    state, calls = isolated_world(tmp_path, monkeypatch)
    case = state.cases[0]
    expected = sql_capture.evidence._db_digest(case.task)
    path = Path(case.task.db_path)
    saved = path.read_bytes()
    original = sql_capture.start_capture
    adopted = []
    def replacing_start(task, **kwargs):
        path.write_bytes(saved + b"ABA replacement")
        try:
            session = original(task, **kwargs)
            adopted.append(session._capture.db_sha256)
            return session
        finally:
            path.write_bytes(saved)
    monkeypatch.setattr(sql_capture, "start_capture", replacing_start)
    with pytest.raises(ValueError):
        evaluator._execute(state.candidate, case, expected_db_sha256=expected, executor=state.executor)
    assert adopted == [], "dbpin ABA sentry: replacement hash admitted between outer checks"
    assert sql_capture.evidence._db_digest(case.task) == expected and calls == []


@pytest.mark.parametrize("kind", ("finish", "abort_prefix", "abort_empty", "score_abort",
                                 "rejected", "program_abort", "start_abort", "finish_exception"))
def test_dbpin_all_returned_and_exception_capture_hashes_guarded(tmp_path, monkeypatch, kind):
    from ptc import sql_isolation as isolation
    from train import sql_capture
    from train.test_sql_capture import isolation_methods
    evaluator = api("sql_skill_eval")
    state, _ = isolated_world(tmp_path, monkeypatch)
    case = state.cases[0]
    expected = sql_capture.evidence._db_digest(case.task)
    kwargs = {}
    if kind == "abort_prefix":
        kwargs["observation"] = "not final SQL"
    elif kind == "abort_empty":
        kwargs["observation"] = "FINAL_SQL: "
    elif kind == "score_abort":
        kwargs["score_abort"] = isolation.AbortInfo("scorer", "memory")
    elif kind == "rejected":
        kwargs["rejected"] = True
    elif kind == "program_abort":
        kwargs["program_abort"] = isolation.AbortInfo("program", "memory")
    calls = isolation_methods(monkeypatch, **kwargs)
    def foreign(actual):
        return dataclasses.replace(actual, db_sha256="f" * 64)
    if kind == "start_abort":
        snapshot = sql_capture.start_capture(case.task, ids=case.ids,
            allow_execution=True, executor=state.executor).abort()
        actual = foreign(sql_capture._aborted(snapshot, isolation.AbortInfo("program", "memory")))
        def start(*args, **kwargs):
            raise sql_capture.CaptureExecutionAborted(actual)
        monkeypatch.setattr(sql_capture, "start_capture", start)
    elif kind in ("rejected", "program_abort"):
        original = sql_capture._CaptureSession.step
        def step(self, code):
            try:
                return original(self, code)
            except sql_capture.CaptureError as exc:
                raise type(exc)(foreign(exc.capture))
        monkeypatch.setattr(sql_capture._CaptureSession, "step", step)
    else:
        method = "abort" if kind.startswith("abort_") else "finish"
        original = getattr(sql_capture._CaptureSession, method)
        def terminal(self, *args):
            actual = original(self, *args)
            if kind == "finish_exception":
                actual = sql_capture._aborted(actual, isolation.AbortInfo("scorer", "memory"))
                raise sql_capture.CaptureExecutionAborted(foreign(actual))
            return foreign(actual)
        monkeypatch.setattr(sql_capture._CaptureSession, method, terminal)
    rejected = False
    try:
        evaluator._execute(state.candidate, case, expected_db_sha256=expected, executor=state.executor)
    except ValueError:
        rejected = True
    except sql_capture.CaptureError:
        pass
    assert rejected, "dbpin returned capture sentry: foreign hash accepted or propagated"
    assert all(c[2]["db_sha256"] == expected for c in calls)


@pytest.mark.parametrize("binding_call,completed", ((3, 1), (6, 4)))
def test_binding_failure_keeps_obtained_captures_without_authorizing_promotion(
    tmp_path, monkeypatch, binding_call, completed,
):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    counts = sentries(monkeypatch)
    binding, execute = evaluator._current_binding, evaluator._execute
    bindings, obtained = [], []

    def drift(*args, **kwargs):
        actual = binding(*args, **kwargs)
        bindings.append(actual)
        if len(bindings) == binding_call:
            return dataclasses.replace(actual, source_sha256="f" * 64)
        return actual

    def observe(*args, **kwargs):
        actual = execute(*args, **kwargs)
        obtained.append(actual)
        return actual

    monkeypatch.setattr(evaluator, "_current_binding", drift)
    monkeypatch.setattr(evaluator, "_execute", observe)
    with pytest.raises(ValueError, match="workflow binding changed") as raised:
        promote(module, evaluator, state)
    assert counts["dispatch"] == completed and counts["score"] == completed + 1
    assert len(obtained) == completed
    assert all(c.result.valid is True and c.result.score == 1 for c in obtained)
    assert raised.value.qualification_captures == tuple(obtained)
    assert tuple(c.ids for c in obtained) == tuple(c.ids for c in state.cases[:completed])
