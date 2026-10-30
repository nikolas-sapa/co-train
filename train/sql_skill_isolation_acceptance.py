"""Explicit, nondefault real-runtime record acceptance. No model calls.

Run only after boundary authorization:
python -B -m train.sql_skill_isolation_acceptance --execution-profile /absolute/profile.json \
    --output-dir /absolute/fresh-output

The CLI registers the profile option before invoking this file with pytest.
Bare pytest selection fails closed when the profile is missing, never skips.
Caller-authored fixtures establish runtime integration, not model/skill results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from ptc import sql_isolation as isolation
from train import sql_capture as capture
from train import sql_episodes as evidence
from train import sql_skill_eval as evaluator
from train import sql_skills as skills


_ROOT = Path(__file__).resolve().parents[1]
_PROGRAM = '''tables = execute_sql(query="SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
if len(tables) == 1:
    name = tables[0]["name"]
    quoted = '"'
    for character in name:
        quoted = quoted + ('""' if character == '"' else character)
    quoted = quoted + '"'
    print("FINAL_SQL:SELECT COUNT(*) FROM " + quoted)
'''


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _ids(label, split):
    return evidence.EpisodeIds(
        "isolated-record-runtime-acceptance", split, "caller-fixture-run",
        label, "caller-authored-rowcount", "v1",
    )


def _task(directory, label, rows, table):
    import sqlite3
    from bench.task import SqlTask

    path = directory / (label + ".sqlite")
    quoted = '"' + table.replace('"', '""') + '"'
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE " + quoted + " (value INTEGER)")
        connection.executemany(
            "INSERT INTO " + quoted + " VALUES (?)", ((i,) for i in range(rows)),
        )
    return SqlTask(
        name=label, question="Count rows in the only user table.", evidence="",
        gold_sql="SELECT COUNT(*) FROM " + quoted, db_id=label, db_path=str(path),
        tier="simple", tier_source="derived", shape="select-count",
        coarse_shape="aggregate", source="fixture",
    )


def _forbid_host(*args, **kwargs):
    raise AssertionError("real isolation acceptance reached host PROGRAM/scorer")


def _fresh_reuse(candidate_path, promotion_path, manifest_path, profile_path, state_dir):
    """Fresh interpreter, only two new DBs and externally supplied whole pin."""
    from bench.task import SqlTask

    profile = isolation.load_execution_profile(profile_path, source_root=_ROOT)
    executor = isolation.PilotExecutor(profile, state_dir=state_dir)
    candidate = skills.decode_candidate(candidate_path.read_bytes())
    promotion = skills.decode_promotion(promotion_path.read_bytes())
    manifest = json.loads(manifest_path.read_bytes())
    assert all(not Path(p).exists() for p in manifest["historical_databases"])
    evidence._score = _forbid_host
    evidence.sql_arms.ArmPair.run = _forbid_host
    results = []
    for item in manifest["cases"]:
        case = evaluator.SkillCase(
            "reuse", SqlTask(**item["task"]), evidence.EpisodeIds(**item["ids"]),
        )
        actual = evaluator.reuse_promoted(
            candidate, promotion, case, expected_promotion_sha256=manifest["approved_pin"],
            ids=evidence.EpisodeIds(**manifest["approval_ids"]),
            allow_execution=True, executor=executor,
        )
        assert actual.schema_version == 2 and actual.result.valid is True
        assert actual.result.score == 1.0 and actual.final_answer == case.task.gold_sql
        assert actual.steps[0].action == candidate.program
        assert [r.role for r in actual.runtime_receipts] == ["program", "scorer"]
        target = manifest_path.parent / (case.task.name + "-capture.json")
        target.write_bytes(capture.encode_capture(actual))
        results.append({"capture_sha256": _sha(target.read_bytes()),
                        "db_sha256": actual.db_sha256, "result": asdict(actual.result)})
    assert len(results) == 2 and results[0]["db_sha256"] != results[1]["db_sha256"]
    print(json.dumps({"fresh_reuse": results}, sort_keys=True))


def test_real_isolated_skill_lifecycle(tmp_path, request, monkeypatch):
    """No fake backend and no missing-infrastructure skips."""
    profile_path = request.config.getoption("--execution-profile", default=None)
    assert profile_path is not None, "explicit --execution-profile required; use module CLI"
    profile_path = Path(profile_path).resolve(strict=True)
    profile = isolation.load_execution_profile(profile_path, source_root=_ROOT)
    executor = isolation.PilotExecutor(profile, state_dir=tmp_path / "runtime-state")
    # Count real methods, never substitute their outcomes.
    calls, all_calls = [], []
    run_program, score_sql = isolation.PilotExecutor.run_program, isolation.PilotExecutor.score_sql
    def program(self, code, **kwargs):
        calls.append("program")
        all_calls.append("program")
        return run_program(self, code, **kwargs)
    def scorer(self, sql, task, **kwargs):
        calls.append("scorer")
        all_calls.append("scorer")
        return score_sql(self, sql, task, **kwargs)
    monkeypatch.setattr(isolation.PilotExecutor, "run_program", program)
    monkeypatch.setattr(isolation.PilotExecutor, "score_sql", scorer)
    monkeypatch.setattr(evidence, "_score", _forbid_host)
    monkeypatch.setattr(evidence.sql_arms.ArmPair, "run", _forbid_host)

    task = _task(tmp_path, "origin", 2, "source table")
    source_session = capture.start_capture(task, ids=_ids("origin", "development"),
        allow_execution=True, executor=executor)
    assert source_session.step("print('FINAL_SQL:SELECT -1')") == "FINAL_SQL:SELECT -1"
    source = source_session.finish("SELECT -1")
    assert source.result is not None and source.result.valid and source.result.score == 0
    assert calls == ["program", "scorer"] and source.schema_version == 2
    assert [r.role for r in source.runtime_receipts] == ["program", "scorer"]
    candidate = skills.create_candidate(
        source, source_task=task, source_ids=source.ids,
        skill_id="single-user-table-row-count", program=_PROGRAM,
    )
    qualifications = tuple(evaluator.SkillCase(
        "qualification", _task(tmp_path, "qualification-" + str(i), rows, table),
        _ids("qualification-" + str(i), "qualification"),
    ) for i, (rows, table) in enumerate(((0, "empty"), (1, "one"), (3, 'odd " table'), (7, "seven"))))
    approval_ids = _ids("approval", "approval")
    calls.clear()
    promotion, actuals = evaluator.promote_candidate(
        candidate, source_capture=source,
        expected_source_capture_sha256=_sha(capture.encode_capture(source)),
        source_case=evaluator.SkillCase("source_failure", task, source.ids),
        qualification_cases=qualifications, ids=approval_ids,
        allow_execution=True, executor=executor,
    )
    assert promotion is not None and promotion.schema_version == 2 and len(actuals) == 4
    assert calls == ["scorer"] + ["program", "scorer"] * 4
    assert all(c.result.valid and c.result.score == 1.0 for c in actuals)
    assert len({c.db_sha256 for c in actuals}) == 4
    for i, actual in enumerate(actuals):
        (tmp_path / ("qualification-" + str(i) + "-capture.json")).write_bytes(capture.encode_capture(actual))

    # Actual native rejection must not let a SQL-looking stdout prefix reach SCORER.
    calls.clear()
    session = capture.start_capture(task, ids=_ids("rejected", "development"),
        allow_execution=True, executor=executor)
    import pytest
    with pytest.raises(capture.CaptureProgramRejected) as raised:
        session.step("print('FINAL_SQL:SELECT 1'); 1 / 0")
    rejected = raised.value.capture
    assert rejected.terminal_label == "program_rejected" and rejected.result is None
    assert rejected.steps[0].observation == "error: ZeroDivisionError: division by zero"
    assert rejected.runtime_receipts[-1].role == "program" and calls == ["program"]
    with pytest.raises(ValueError):
        capture.rescore_capture(rejected, task, ids=rejected.ids, executor=executor)
    assert calls == ["program"]
    (tmp_path / "native-rejected-capture.json").write_bytes(capture.encode_capture(rejected))
    (tmp_path / "source-capture.json").write_bytes(capture.encode_capture(source))
    candidate_path, promotion_path = tmp_path / "candidate.json", tmp_path / "promotion.json"
    candidate_path.write_bytes(skills.encode_candidate(candidate))
    promotion_path.write_bytes(skills.encode_promotion(promotion))
    fresh = tuple(evaluator.SkillCase(
        "reuse", _task(tmp_path, label, rows, table), _ids(label, "heldout"),
    ) for label, rows, table in (("fresh-eleven", 11, "new table"), ("fresh-thirteen", 13, 'new " table')))
    calls.clear()
    with pytest.raises(ValueError, match="external approved promotion pin"):
        evaluator.reuse_promoted(
            candidate, promotion, fresh[0], expected_promotion_sha256="0" * 64,
            ids=approval_ids, allow_execution=True, executor=executor,
        )
    assert calls == []
    history = [task.db_path] + [case.task.db_path for case in qualifications]
    for path in history:
        Path(path).unlink()
    manifest = {
        "approved_pin": _sha(promotion_path.read_bytes()), "approval_ids": asdict(approval_ids),
        "historical_databases": history,
        "cases": [{"task": asdict(case.task), "ids": asdict(case.ids)} for case in fresh],
    }
    manifest_path = tmp_path / "fresh-reuse-input.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    code = """import sys
from pathlib import Path
from train.sql_skill_isolation_acceptance import _fresh_reuse
_fresh_reuse(*(Path(p) for p in sys.argv[1:]))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", code, str(candidate_path), str(promotion_path),
         str(manifest_path), str(profile_path), str(tmp_path / "fresh-state")],
        cwd=_ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    assert child.returncode == 0, child.stderr + child.stdout
    report = json.loads(child.stdout)
    assert len(report["fresh_reuse"]) == 2
    report.update(approved_promotion_sha256=manifest["approved_pin"],
                  candidate_sha256=_sha(candidate_path.read_bytes()),
                  historical_database_count=5, historical_remaining=0,
                  model_requests=0, parent_real_calls=all_calls)
    (tmp_path / "runtime-record-acceptance.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-profile", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    profile = args.execution_profile.resolve(strict=True)
    output = args.output_dir
    if not output.is_absolute() or output.exists():
        parser.error("--output-dir must be a new absolute path")
    output.mkdir(parents=True)
    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--execution-profile")
    import pytest
    return int(pytest.main([
        str(Path(__file__).resolve()), "-q", "-ra", "--tb=short", "-p", "no:cacheprovider",
        "--execution-profile=" + str(profile), "--basetemp=" + str(output / "pytest"),
    ], plugins=[Options()]))


if __name__ == "__main__":
    raise SystemExit(main())
