"""Offline QA-channel tests for the task-bound SQL environment seam.

Covers `spec/agent-defect-escalation-sql-environment.md`: the keyword-only
`qa=` on `train.grpo_ptc.sql_environment` binds the opt-in defect-report
collector (`ptc.sql_qa.QaChannel`) onto the existing PTC-arm prompt and
catalog. Every route is real -- temporary SQLite databases, the restricted
interpreter and the real `build_sql_arms` prompt/catalog path. No model,
provider, TRL, native job, container or network. The only subprocess is
`sys.executable` itself, for the fresh-interpreter import check.
"""

from __future__ import annotations

import builtins
import gc
import hashlib
import inspect
import pathlib
import sqlite3
import subprocess
import sys
import weakref

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

from bench.task import SqlTask  # noqa: E402
from ptc.sql_arms import build_sql_arms  # noqa: E402
from ptc.sql_qa import (  # noqa: E402
    QaChannel,
    REPORT_MARKER,
    REPORT_PROMPT,
    REPORT_TOOL,
    report_ack,
)
from train import grpo_ptc, guards  # noqa: E402

SENTINEL = "QA_GOLD_SENTINEL_7f3d9c2b"
"""Inside the fixture's gold query only -- the prompt must never surface it."""

SQL_PROGRAM = (
    'rows = execute_sql(query="SELECT label, amount FROM readings '
    'ORDER BY amount DESC")\n'
    "total = 0\n"
    "for row in rows:\n"
    '    total += row["amount"]\n'
    '    print(row["label"], row["amount"])\n'
    'print("total", total)'
)
"""A real non-reporting program with a deterministic printed observation."""

SQL_OBSERVATION = "beta 29\nalpha 17\ntotal 46"
"""Exactly what `SQL_PROGRAM` prints against the fixture database."""


def _report_program(detail: str, kind: str = "task_defect") -> str:
    """One program whose only action is the catalog's report callback."""
    return f'print({REPORT_TOOL}(kind="{kind}", detail="{detail}"))'


def _report_events(qa: QaChannel, arm: str = "ptc") -> list:
    return [e for e in qa.events if e["type"] == "report" and e["arm"] == arm]


def _db_sha256(db_path: str) -> str:
    return hashlib.sha256(pathlib.Path(db_path).read_bytes()).hexdigest()


@pytest.fixture()
def sql_task(tmp_path):
    """One real temporary SQLite database behind one SqlTask. The gold query
    embeds `SENTINEL` so the prompt assertions have a unique marker to refuse."""
    db = tmp_path / "qa-env.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "CREATE TABLE readings (label TEXT NOT NULL, amount INTEGER NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO readings (label, amount) VALUES (?, ?)",
            [("alpha", 17), ("beta", 29)],
        )
        conn.commit()
    finally:
        conn.close()
    return SqlTask(
        name="qa-env",
        question="What amounts and labels are recorded?",
        evidence="Use the readings table.",
        gold_sql=f"SELECT amount FROM readings /* {SENTINEL} */",
        db_id="qa-env",
        db_path=str(db),
        tier="simple",
        tier_source="derived",
        shape="fixture-select",
        coarse_shape="fixture-select",
        source="fixture",
    )


@pytest.fixture(autouse=True)
def framework_calls(monkeypatch):
    """Reject imports, including cached harness imports, rather than fake a stack."""
    attempted = []
    real_import = builtins.__import__
    forbidden = {
        "torch", "trl", "unsloth", "transformers", "vllm", "verifiers",
        "httpx", "pydantic", "datasets", "huggingface_hub",
    }

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"framework import attempted: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    return attempted


def test_enabled_report(sql_task):
    """Spec 1: one valid program callback produces exactly one PTC event with
    `catalog_callback` provenance, and the program reads the existing fixed
    unverified acknowledgment."""
    qa = QaChannel()
    _, environment = grpo_ptc.sql_environment(sql_task, qa=qa)
    observation = environment.step(
        _report_program("the question misnames the amount column"))
    assert observation == report_ack()
    assert len(qa.events) == 1
    (event,) = qa.events
    assert event["type"] == "report"
    assert event["arm"] == "ptc"
    assert event["provenance"] == "catalog_callback"
    assert event["kind"] == "task_defect"
    assert event["detail"] == "the question misnames the amount column"
    assert environment.turns_used == 1


def test_default_compatibility(sql_task):
    """Spec 2: omitted `qa` and explicit `qa=None` produce identical prompts,
    single-tool schemas, budgets and SQL observations."""
    prompt_default, env_default = grpo_ptc.sql_environment(sql_task)
    prompt_none, env_none = grpo_ptc.sql_environment(sql_task, qa=None)
    assert prompt_default == prompt_none
    assert prompt_default == build_sql_arms(sql_task).prompt("ptc")
    assert list(env_default.tools) == list(env_none.tools)
    for env in (env_default, env_none):
        assert [tool["function"]["name"] for tool in env.tools] == ["run_program"]
        assert env.max_turns == guards.eval_max_turns()
        assert env.budget.used == 0
    assert inspect.signature(grpo_ptc.sql_environment).parameters["qa"].kind == (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert env_default.budget is not env_none.budget
    assert env_default.budget.max_turns == env_none.budget.max_turns
    observed_default = env_default.step(SQL_PROGRAM)
    observed_none = env_none.step(SQL_PROGRAM)
    assert observed_default == observed_none == SQL_OBSERVATION


def test_opt_in_prompt(sql_task):
    """Spec 3: reporting text appears only on the opt-in prompt, and neither
    prompt exposes the fixture's unique gold-query sentinel."""
    prompt_default, _ = grpo_ptc.sql_environment(sql_task)
    prompt_qa, _ = grpo_ptc.sql_environment(sql_task, qa=QaChannel())
    assert prompt_qa == build_sql_arms(sql_task, qa=QaChannel()).prompt("ptc")
    assert REPORT_PROMPT in prompt_qa
    assert REPORT_TOOL in prompt_qa
    assert "defect" in prompt_qa
    for banned in (REPORT_PROMPT, REPORT_TOOL, REPORT_MARKER,
                   "defect", "allegation"):
        assert banned not in prompt_default
    for prompt in (prompt_default, prompt_qa):
        assert SENTINEL not in prompt
        assert sql_task.gold_sql not in prompt
        assert "GOLD" not in prompt


def test_sql_parity(sql_task):
    """Spec 4: a real non-reporting SQL program has identical observations with
    reporting off and on, records zero reports, and leaves the database's
    SHA-256 unchanged."""
    digest_before = _db_sha256(sql_task.db_path)
    qa = QaChannel()
    _, env_off = grpo_ptc.sql_environment(sql_task)
    _, env_on = grpo_ptc.sql_environment(sql_task, qa=qa)
    obs_off = env_off.step(SQL_PROGRAM)
    obs_on = env_on.step(SQL_PROGRAM)
    assert obs_off == obs_on == SQL_OBSERVATION
    assert tuple(qa.events) == ()
    assert _db_sha256(sql_task.db_path) == digest_before


@pytest.mark.parametrize(
    "bad_channel",
    [
        pytest.param(True, id="bool"),
        pytest.param(False, id="false-bool"),
        pytest.param(0, id="zero"),
        pytest.param([], id="empty-list"),
        pytest.param("ptc", id="arm-name-string"),
        pytest.param({"kind": "task_defect"}, id="report-shaped-dict"),
        pytest.param(QaChannel, id="channel-class-not-instance"),
        pytest.param(lambda task: QaChannel(), id="channel-factory"),
    ],
)
def test_invalid_channel(sql_task, bad_channel):
    """Spec 5: a `qa` that is not a `QaChannel` instance is refused before any
    program executes -- never silently wrapped, factory-called or recorded
    into. The seam synthesizes no channel of its own."""
    with pytest.raises(TypeError, match="concrete QaChannel"):
        grpo_ptc.sql_environment(sql_task, qa=bad_channel)


def test_invalid_report(sql_task):
    """Spec 6: an invalid report is a visible refusal in the program's real
    `rejected:` response format, spends exactly one submission, accepts zero
    events and leaves the database unchanged."""
    digest_before = _db_sha256(sql_task.db_path)
    qa = QaChannel()
    _, environment = grpo_ptc.sql_environment(sql_task, qa=qa)
    observation = environment.step(_report_program("x", kind="not_a_kind"))
    assert observation.startswith("rejected:")
    assert report_ack() not in observation
    assert environment.turns_used == 1
    assert _report_events(qa) == []
    assert any(
        e["type"] == "report_rejected" and e["arm"] == "ptc"
        for e in qa.events
    ), "a refused report needs a visible rejection event, not silence"
    assert _db_sha256(sql_task.db_path) == digest_before


def test_report_quota(sql_task):
    """Spec 7: nine valid callback attempts in ONE program retain exactly eight
    accepted reports; the ninth is refused in the program's `rejected:` format
    and cannot become an accepted report."""
    qa = QaChannel()
    _, environment = grpo_ptc.sql_environment(sql_task, qa=qa)
    program = "\n".join(
        f'print({REPORT_TOOL}(kind="other", detail="attempt-{i}"))'
        for i in range(9)
    )
    observation = environment.step(program)
    assert observation.startswith("rejected:")
    assert "report limit" in observation
    reports = _report_events(qa)
    assert len(reports) == 8
    assert [e["detail"] for e in reports] == [f"attempt-{i}" for i in range(8)]
    assert not any(e.get("detail") == "attempt-8" for e in qa.events)
    assert any(e["type"] == "overflow" for e in qa.events), (
        "the capped ninth attempt must be visible, not silent"
    )
    assert environment.turns_used == 1


def test_submission_budget(sql_task):
    """Spec 8: after the existing submission cap is spent, one further reporting
    program returns the unchanged exhaustion refusal -- the program never
    executes, so it adds zero events."""
    qa = QaChannel()
    _, disabled = grpo_ptc.sql_environment(sql_task)
    _, environment = grpo_ptc.sql_environment(sql_task, qa=qa)
    assert environment.step(_report_program("early report")) == report_ack()
    for _ in range(environment.max_turns - 1):
        assert environment.step(SQL_PROGRAM) == SQL_OBSERVATION
    assert environment.turns_used == environment.max_turns
    events_before = len(qa.events)
    refusal = environment.step(_report_program("late report"))
    assert refusal == environment.exhausted_message()
    assert refusal == disabled.exhausted_message()
    assert "budget for this task is spent" in refusal
    assert len(qa.events) == events_before
    assert len(_report_events(qa)) == 1


def test_independent_channels(sql_task):
    """Spec 9: two fresh caller-supplied channels receive only their own
    environment's reports, and one environment's spent submission budget does
    not consume the other's."""
    first_channel, second_channel = QaChannel(), QaChannel()
    _, first = grpo_ptc.sql_environment(sql_task, qa=first_channel)
    _, second = grpo_ptc.sql_environment(sql_task, qa=second_channel)
    first.step(_report_program("first allegation"))
    second.step(_report_program("second allegation"))
    assert [e["detail"] for e in _report_events(first_channel)] == [
        "first allegation"]
    assert [e["detail"] for e in _report_events(second_channel)] == [
        "second allegation"]
    for _ in range(first.max_turns - 1):
        first.step(SQL_PROGRAM)
    assert first.step(SQL_PROGRAM) == first.exhausted_message()
    assert second.step(SQL_PROGRAM) == SQL_OBSERVATION
    assert second.turns_used == 2
    assert [e["detail"] for e in _report_events(first_channel)] == [
        "first allegation"]
    assert [e["detail"] for e in _report_events(second_channel)] == [
        "second allegation"]


def test_default_no_qa_import(tmp_path):
    """Spec 10: a fresh interpreter can build and step the DISABLED environment
    without `ptc.sql_qa` ever entering `sys.modules`."""
    db = tmp_path / "fresh-interp.sqlite"
    repo = pathlib.Path(__file__).resolve().parents[1]
    child = (
        "import sqlite3, sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "db_path = sys.argv[1]\n"
        "conn = sqlite3.connect(db_path)\n"
        "try:\n"
        "    conn.execute('CREATE TABLE readings (amount INTEGER NOT NULL)')\n"
        "    conn.execute('INSERT INTO readings (amount) VALUES (41)')\n"
        "    conn.commit()\n"
        "finally:\n"
        "    conn.close()\n"
        "class Task:\n"
        "    name = 'fresh-interp'\n"
        "    question = 'What amount is recorded?'\n"
        "    evidence = ''\n"
        "    gold_sql = 'SELECT amount FROM readings'\n"
        "    db_path = db_path\n"
        "    tier = 'simple'\n"
        "from train.grpo_ptc import sql_environment\n"
        "prompt, environment = sql_environment(Task())\n"
        "observation = environment.step(\n"
        "    'print(execute_sql(query=\"SELECT amount FROM readings\")"
        "[0][\"amount\"])')\n"
        "leaked = sorted(m for m in sys.modules if 'sql_qa' in m)\n"
        "assert not leaked, f'default path imported {leaked}'\n"
        "assert 'report_defect' not in prompt\n"
        "assert observation.strip() == '41'\n"
        "print('CHILD_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", child, str(db)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "CHILD_OK" in result.stdout


def test_unbound_factory_unchanged():
    """Spec 11: the existing zero-argument factory remains unbound, exposes
    exactly one program tool and refuses execution as before."""
    factory = grpo_ptc.environment_factory()
    assert inspect.signature(factory).parameters == {}
    environment = factory()
    assert [tool["function"]["name"] for tool in environment.tools] == [
        "run_program"]
    assert environment.turns_used == 0
    with pytest.raises(NotImplementedError, match="§344"):
        environment.step(SQL_PROGRAM)
    assert environment.turns_used == 1


def test_channel_released(sql_task):
    """Spec 12: the channel is caller-owned. Once the caller's reference and the
    environment that holds the executor are dropped, the channel is
    collectible -- nothing process-global keeps it alive."""
    qa = QaChannel()
    reference = weakref.ref(qa)

    _, environment = grpo_ptc.sql_environment(sql_task, qa=qa)
    assert environment.step(_report_program("tracked allegation")) == report_ack()
    assert len(_report_events(qa)) == 1
    assert reference() is qa

    del qa, environment
    gc.collect()
    assert reference() is None, (
        "the caller-owned channel stayed reachable after every reference was "
        "dropped -- something is retaining it globally"
    )
