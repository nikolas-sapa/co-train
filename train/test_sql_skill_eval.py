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
