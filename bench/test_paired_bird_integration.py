"""Real local fixture SQL behind a SCRIPTED HOST seam, not SDK acceptance.

No fake framework modules, skip-on-import, provider calls, native executor or
real corpus. PTC uses the existing restricted in-process action runtime; Bash
uses the existing query wrapper and local SQLite CLI. EX is scored separately.
"""

import hashlib
import shlex
from pathlib import Path

from bench.score import execution_accuracy
from bench.test_paired_bird import _api, _outcome, _plan, _run
from ptc.sql_arms import build_sql_arms


def test_b_real_sql_fixture_correct_wrong_and_unchanged_databases(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)
    paths = {Path(task.db_path) for task in plan.draw.planned}
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    requests = []
    observations = []
    scored = []

    async def driver(request):
        requests.append(request)
        for index, task in enumerate(request.tasks):
            # This callback is trusted and sees oracle SQL. It is intentionally
            # NOT a policy-facing adapter or evidence of gold isolation.
            pair = build_sql_arms(
                task, budget=request.instrument.budget,
                max_rows=request.instrument.action_max_rows)
            assert pair.budget is request.instrument.budget
            assert pair.schema in pair.bash_prompt
            assert pair.schema in pair.ptc_prompt
            sql = task.gold_sql if index % 2 == 0 else "SELECT 'known-wrong-fixture'"
            if request.arm == "ptc":
                observation = pair.run(
                    "ptc", "print(execute_sql(query=" + repr(sql) + "))")
            else:
                bindir = tmp_path / "wrappers" / task.name
                bindir.mkdir(parents=True, exist_ok=True)
                observation = pair.run(
                    "bash", "execute_sql " + shlex.quote(sql), bindir=bindir)
            assert observation.strip()
            assert not observation.lower().startswith(("rejected:", "error:"))
            if index % 2:
                assert "known-wrong-fixture" in observation
            observations.append((request.arm, task.name, observation))
            ex = execution_accuracy(
                sql, task, timeout_s=plan.draw.timeout_s,
                max_rows=plan.draw.max_rows, compare=plan.draw.comparison)
            assert ex.valid is True
            assert ex.score == (1.0 if index % 2 == 0 else 0.0)
            scored.append(ex)
            yield _outcome(
                api, request, task, score=ex.score, valid=ex.valid,
                status=ex.status)

    result = _run(api, plan, driver)
    assert [r.arm for r in requests] == ["bash", "ptc"]
    assert len(observations) == len(scored) == 14
    assert result.status == "complete" and result.comparison.n == 7
    assert result.comparison.delta == 0.0
    assert result.comparison.mean_a == result.comparison.mean_b == 4 / 7
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths} == before
    assert all(not Path(str(path) + suffix).exists()
               for path in paths for suffix in ("-wal", "-shm", "-journal"))
    assert result.fixture is True and result.measurement is False
