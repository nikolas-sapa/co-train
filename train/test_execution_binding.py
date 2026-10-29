"""Offline task-bound execution regressions, not a runnable training pipeline.

Only SQLite, the existing arm/runtime and synthetic SqlTasks are exercised. No
framework substitutes: importing a model/framework path fails loudly instead.
The proposed seam is sql_environment(task) -> (existing_arm_prompt, fresh_env),
with an optional private PTCEnvironment._executor callable.
"""

from __future__ import annotations

import ast
import builtins
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

from bench.task import SqlTask  # noqa: E402
from ptc.sql_arms import build_sql_arms  # noqa: E402
from train import grpo_ptc, guards  # noqa: E402

PROGRAM = 'rows = execute_sql(query="SELECT amount FROM readings")\nprint(rows[0]["amount"])'


@pytest.fixture
def sql_tasks(tmp_path):
    """Same schema, different databases and answers: a stale binding cannot agree."""
    tasks = []
    for name, amount in (("first", 17), ("second", 29)):
        db = tmp_path / f"{name}.sqlite"
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            conn.execute("INSERT INTO readings (amount) VALUES (?)", (amount,))
            conn.commit()
        finally:
            conn.close()
        tasks.append(SqlTask(
            name=name,
            question="What amount is recorded?",
            evidence="Use the readings table.",
            gold_sql=f"SELECT amount FROM readings /* GOLD_ONLY_{name} */",
            db_id=name,
            db_path=str(db),
            tier="simple",
            tier_source="derived",
            shape="fixture-select",
            coarse_shape="fixture-select",
            source="fixture",
        ))
    return tasks


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


def test_sql_arm_real_execution_does_not_import_the_training_framework(sql_tasks):
    """Prerequisite: the existing arm must execute without ptc.harness imports."""
    pair = build_sql_arms(sql_tasks[0])
    assert pair.run("ptc", PROGRAM).strip() == "17"


def test_sql_environment_executes_a_real_sqlite_program(sql_tasks):
    _, environment = grpo_ptc.sql_environment(sql_tasks[0])
    assert environment.turns_used == 0
    assert environment.step(PROGRAM).strip() == "17"
    assert environment.turns_used == 1


def test_bound_executor_runs_eight_programs_then_refuses_ninth(sql_tasks):
    pair = build_sql_arms(sql_tasks[0])
    submitted = []

    def execute(code):
        submitted.append(code)
        return pair.run("ptc", code)

    environment = grpo_ptc.PTCEnvironment(
        max_turns=guards.eval_max_turns(), _executor=execute,
    )
    assert environment.max_turns == 8
    for _ in range(environment.max_turns):
        assert environment.step(PROGRAM).strip() == "17"
    assert submitted == [PROGRAM] * 8
    assert environment.turns_used == 8
    assert environment.step(PROGRAM) == environment.exhausted_message()
    assert "budget for this task is spent" in environment.exhausted_message()
    assert len(submitted) == 8
    assert environment.turns_used == 8


def test_bound_executor_spends_a_turn_before_dispatch_even_when_execution_raises():
    observed = []

    def execute(code):
        observed.append((environment.turns_used, code))
        raise RuntimeError("execution failed")

    environment = grpo_ptc.PTCEnvironment(
        max_turns=guards.eval_max_turns(), _executor=execute,
    )
    with pytest.raises(RuntimeError, match="execution failed"):
        environment.step(PROGRAM)
    assert observed == [(1, PROGRAM)]
    assert environment.turns_used == 1


def test_sql_environments_have_distinct_task_bindings_and_fresh_budgets(sql_tasks):
    _, first = grpo_ptc.sql_environment(sql_tasks[0])
    _, second = grpo_ptc.sql_environment(sql_tasks[1])
    _, repeated = grpo_ptc.sql_environment(sql_tasks[0])
    assert first is not second and first is not repeated
    assert first.budget is not second.budget and first.budget is not repeated.budget
    assert second.budget is not repeated.budget
    assert first.max_turns == second.max_turns == repeated.max_turns == guards.eval_max_turns()
    assert [env.turns_used for env in (first, second, repeated)] == [0, 0, 0]

    for _ in range(first.max_turns):
        assert first.step(PROGRAM).strip() == "17"
    assert first.step(PROGRAM) == first.exhausted_message()
    assert second.turns_used == repeated.turns_used == 0
    assert second.step(PROGRAM).strip() == "29"
    assert repeated.step(PROGRAM).strip() == "17"
    assert second.turns_used == repeated.turns_used == 1


def test_sql_environment_exposes_only_the_existing_arm_prompt_and_tool_schema(sql_tasks):
    task = sql_tasks[0]
    prompt, environment = grpo_ptc.sql_environment(task)
    assert prompt == build_sql_arms(task).prompt("ptc")
    assert task.question in prompt and task.evidence in prompt
    tree = ast.parse((guards.REPO_ROOT / "ptc" / "harness.py").read_text())
    tool_assignment, = [
        node for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "TOOLS"
                for target in node.targets)
    ]
    assert list(environment.tools) == ast.literal_eval(tool_assignment.value)
    assert [tool["function"]["name"] for tool in environment.tools] == ["run_program"]
    visible = prompt + json.dumps(environment.tools)
    assert task.gold_sql not in visible
    assert "GOLD_ONLY" not in visible


def test_unbound_environment_execution_remains_unimplemented():
    environment = grpo_ptc.environment_factory()()
    with pytest.raises(NotImplementedError, match="§344"):
        environment.step(PROGRAM)


@pytest.mark.parametrize("entrypoint", ["preflight", "main", "preflight-only"])
def test_execution_binding_does_not_open_the_training_gate(
    monkeypatch, framework_calls, entrypoint,
):
    reached = []

    def forbidden(name):
        def fail(*args, **kwargs):
            reached.append(name)
            raise AssertionError(f"gate reached model/framework setup: {name}")
        return fail

    monkeypatch.setattr(grpo_ptc, "require_stack", forbidden("require_stack"))
    monkeypatch.setattr(grpo_ptc, "model_spec", forbidden("model_spec"))
    with pytest.raises(guards.PreconditionUnmet):
        if entrypoint == "preflight":
            grpo_ptc.preflight()
        else:
            grpo_ptc.main(["--preflight-only"] if entrypoint == "preflight-only" else [])
    assert reached == []
    assert framework_calls == []
