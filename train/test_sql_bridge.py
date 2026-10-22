"""Native SQL bridge regressions, not a full-trainer or compatible-stack claim.

Real temporary SQLite databases distinguish task bindings (17 versus 29).
Unit checks reject training-framework imports. Only the schema check may import
the installed Transformers schema converter; it never constructs a trainer.
The bridge is imported inside a fixture so its absence produces explicit
fixture-setup errors (pytest exit 1), not collection errors (exit 2).
No other test module's private fixtures are reused.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import importlib
import inspect
import json
import os
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

PROGRAM = 'rows = execute_sql(query="SELECT amount FROM readings")\nprint(rows[0]["amount"])'
FINAL_SQL = "```sql\nSELECT amount FROM readings;\n```"
TOOL_CALL = {
    "id": "fixture-call",
    "type": "function",
    "function": {"name": "run_program", "arguments": json.dumps({"code": PROGRAM})},
}


@pytest.fixture(autouse=True)
def framework_calls(monkeypatch):
    """Reject real framework imports, including attempts hidden behind catches."""
    attempted = []
    real_import = builtins.__import__
    real_import_module = importlib.import_module
    forbidden = {
        "torch", "trl", "unsloth", "transformers", "vllm", "verifiers",
        "httpx", "pydantic", "datasets", "huggingface_hub",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"framework import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return real_import(name, *args, **kwargs)

    def guarded_import_module(name, *args, **kwargs):
        check(name)
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    yield {
        "attempted": attempted,
        "real_import": real_import,
        "real_import_module": real_import_module,
    }
    assert attempted == []


@pytest.fixture
def bridge(framework_calls):
    try:
        return importlib.import_module("train.sql_bridge")
    except ModuleNotFoundError as exc:
        if exc.name == "train.sql_bridge":
            pytest.fail("missing native SQL bridge")
        raise


@pytest.fixture
def sql_tasks(tmp_path):
    """Flat scorer layout, identical schemas, and gold-only leakage sentinels."""
    from bench.task import SqlTask

    tasks = []
    for name, amount in (("first", 17), ("second", 29)):
        directory = tmp_path / name
        directory.mkdir()
        db = directory / f"{name}.sqlite"
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            conn.execute("INSERT INTO readings VALUES (?)", (amount,))
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


@pytest.fixture
def training_inputs(bridge, sql_tasks, tmp_path):
    return bridge.prepare_sql_training(sql_tasks, tmp_path)


def _public_tools(environment):
    """The verified native TRL discovery rule, not a hand-curated tool list."""
    return [
        (name, method)
        for name, method in inspect.getmembers(environment, inspect.ismethod)
        if not name.startswith("_") and name not in ("reset", "get_reward")
    ]


def _track_real_environments(monkeypatch, bridge):
    """Spy at the existing execution seam, while preserving real SQLite calls."""
    from train import grpo_ptc, guards

    real_environment = grpo_ptc.sql_environment
    created = []
    dispatched = []

    def tracked(task, root=guards.REPO_ROOT):
        prompt, environment = real_environment(task, root=root)
        executor = environment._executor
        assert callable(executor)

        def execute(code):
            dispatched.append((task.name, environment.turns_used, code))
            return executor(code)

        environment._executor = execute
        created.append(environment)
        return prompt, environment

    monkeypatch.setattr(grpo_ptc, "sql_environment", tracked)
    if getattr(bridge, "sql_environment", None) is real_environment:
        monkeypatch.setattr(bridge, "sql_environment", tracked)
    return created, dispatched


def _completion(content, form):
    if form == "text":
        return content
    final = {"role": "assistant", "content": content}
    if form == "empty-tool-calls":
        final["tool_calls"] = []
    if form == "after-tool":
        return [
            {"role": "assistant", "content": "", "tool_calls": [TOOL_CALL]},
            {"role": "tool", "content": FINAL_SQL, "tool_call_id": "fixture-call"},
            final,
        ]
    return [final]


def test_preparation_returns_plain_canonical_rows_without_gold_in_prompt(
    bridge, sql_tasks, training_inputs,
):
    from ptc.sql_arms import build_sql_arms
    from train import guards

    assert isinstance(training_inputs, bridge.SQLTrainingInputs)
    assert dataclasses.is_dataclass(training_inputs)
    assert isinstance(training_inputs.dataset_rows, (list, tuple))
    assert len(training_inputs.dataset_rows) == 2
    for row, task in zip(training_inputs.dataset_rows, sql_tasks, strict=True):
        assert type(row) is dict
        assert row == {
            "prompt": [{"role": "user", "content": build_sql_arms(task).prompt("ptc")}],
            "task_id": task.name,
            "answer": task.gold_sql,
            "db_id": task.db_id,
        }
        visible = json.dumps(row["prompt"])
        assert task.question in visible and task.evidence in visible
        assert "GOLD_ONLY" not in visible
        assert task.gold_sql not in visible
    assert callable(training_inputs.reward)
    assert inspect.signature(training_inputs.environment_factory).parameters == {}
    assert training_inputs.max_tool_calling_iterations == guards.eval_max_turns() == 8
    root = inspect.signature(bridge.prepare_sql_training).parameters["root"]
    assert root.kind is inspect.Parameter.KEYWORD_ONLY
    assert root.default == guards.REPO_ROOT


def test_explicit_task_order_is_preserved_without_manifest_selection(
    bridge, sql_tasks, tmp_path, monkeypatch,
):
    from train import guards

    original_read_text = pathlib.Path.read_text
    manifest_reads = []

    def guarded_read(path, *args, **kwargs):
        if path.name == "manifest.json":
            manifest_reads.append(path)
            raise AssertionError("explicit task preparation must not read a manifest")
        return original_read_text(path, *args, **kwargs)

    def forbidden_gate(*args, **kwargs):
        raise AssertionError("explicit task preparation must not select a taskset")

    monkeypatch.setattr(pathlib.Path, "read_text", guarded_read)
    monkeypatch.setattr(guards, "require_frontier_taskset", forbidden_gate)
    inputs = bridge.prepare_sql_training(list(reversed(sql_tasks)), tmp_path)
    assert [row["task_id"] for row in inputs.dataset_rows] == ["second", "first"]
    assert manifest_reads == []


@pytest.mark.parametrize("case", ["empty-tasks", "empty-id", "late-duplicate"])
def test_all_ids_are_validated_before_any_schema_or_database_work(
    bridge, sql_tasks, tmp_path, monkeypatch, case,
):
    from ptc import sql_arms
    from train import ex_reward, grpo_ptc

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("database/schema work happened before ID validation")

    for module in (bridge, sql_arms, ex_reward, grpo_ptc):
        for name in ("sql_environment", "build_sql_arms", "schema_text", "db_path_for"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    if case == "empty-tasks":
        tasks = []
    elif case == "empty-id":
        tasks = [dataclasses.replace(sql_tasks[0], name="")]
    else:
        # The duplicate is late, and the first task's missing DB must not win.
        tasks = [
            dataclasses.replace(sql_tasks[0], db_path=str(tmp_path / "missing.sqlite")),
            sql_tasks[1],
            dataclasses.replace(sql_tasks[1], question="Duplicate identity."),
        ]
    with pytest.raises(ValueError):
        bridge.prepare_sql_training(tasks, tmp_path)
    assert calls == []


@pytest.mark.parametrize("missing", ["task-db", "reward-db"])
def test_preparation_raises_for_missing_database(bridge, sql_tasks, tmp_path, missing):
    task = sql_tasks[0]
    root = tmp_path
    if missing == "task-db":
        task = dataclasses.replace(task, db_path=str(tmp_path / "absent.sqlite"))
    else:
        root = tmp_path / "unmounted"
    with pytest.raises(FileNotFoundError):
        bridge.prepare_sql_training([task], root)


@pytest.mark.parametrize("same_contents", [False, True], ids=["different-data", "byte-copy"])
def test_preparation_rejects_tool_and_reward_databases_that_are_not_same_file(
    bridge, sql_tasks, tmp_path, same_contents,
):
    other = tmp_path / "different-corpus.sqlite"
    shutil.copyfile(sql_tasks[0].db_path, other)
    if not same_contents:
        conn = sqlite3.connect(other)
        try:
            conn.execute("UPDATE readings SET amount = 999")
            conn.commit()
        finally:
            conn.close()
    task = dataclasses.replace(sql_tasks[0], db_path=str(other))
    with pytest.raises(ValueError):
        bridge.prepare_sql_training([task], tmp_path)


@pytest.mark.parametrize("link_type", ["symlink", "hardlink"])
def test_preparation_accepts_different_paths_to_same_physical_database(
    bridge, sql_tasks, tmp_path, link_type,
):
    alias = tmp_path / "same-physical-file.sqlite"
    if link_type == "symlink":
        alias.symlink_to(sql_tasks[0].db_path)
    else:
        os.link(sql_tasks[0].db_path, alias)
    task = dataclasses.replace(sql_tasks[0], db_path=str(alias))
    inputs = bridge.prepare_sql_training([task], tmp_path)
    environment = inputs.environment_factory()
    assert environment.reset(**inputs.dataset_rows[0]) is None
    assert environment.run_program(PROGRAM).strip() == "17"
    assert inputs.reward([FINAL_SQL], answer=[task.gold_sql], db_id=[task.db_id]) == [1.0]


def test_native_discovery_has_one_public_tool_and_safe_unbound_properties(training_inputs):
    environment = training_inputs.environment_factory()
    assert environment.turns_used == 0
    assert [name for name, _ in _public_tools(environment)] == ["run_program"]
    signature = inspect.signature(environment.run_program)
    assert list(signature.parameters) == ["code"]
    assert signature.return_annotation is inspect.Signature.empty
    assert environment.reset(**training_inputs.dataset_rows[0]) is None
    assert [name for name, _ in _public_tools(environment)] == ["run_program"]


def test_real_transformers_schema_matches_existing_tool_exactly(
    training_inputs, framework_calls, monkeypatch,
):
    from train import grpo_ptc

    environment = training_inputs.environment_factory()
    tools = _public_tools(environment)
    assert [name for name, _ in tools] == ["run_program"]
    # The bridge itself was imported under the guard. Only this real converter
    # import/call may load Transformers and its installed dependencies.
    with monkeypatch.context() as allowed:
        allowed.setattr(builtins, "__import__", framework_calls["real_import"])
        allowed.setattr(importlib, "import_module", framework_calls["real_import_module"])
        try:
            converter = importlib.import_module("transformers.utils.chat_template_utils")
        except ModuleNotFoundError as exc:
            if exc.name == "transformers":
                pytest.skip("optional real Transformers schema converter is not installed")
            raise
        assert converter.get_json_schema(tools[0][1]) == grpo_ptc.THE_TOOL_SCHEMA


def test_factory_does_not_bind_any_task_and_returns_independent_instances(
    bridge, sql_tasks, tmp_path, monkeypatch,
):
    created, dispatched = _track_real_environments(monkeypatch, bridge)
    inputs = bridge.prepare_sql_training(sql_tasks, tmp_path)
    count = len(created)
    first = inputs.environment_factory()
    second = inputs.environment_factory()
    assert first is not second
    assert len(created) == count
    for environment in (first, second):
        with pytest.raises(RuntimeError, match="reset|bound"):
            environment.run_program(PROGRAM)
        assert environment.turns_used == 0
    assert dispatched == []
    first.reset(**inputs.dataset_rows[0])
    second.reset(**inputs.dataset_rows[1])
    assert created[-1] is not created[-2]
    assert created[-1].budget is not created[-2].budget
    assert first.run_program(PROGRAM).strip() == "17"
    assert second.run_program(PROGRAM).strip() == "29"
    assert first.turns_used == second.turns_used == 1


def test_eight_real_dispatches_then_ninth_refusal_without_extra_dispatch(
    bridge, sql_tasks, tmp_path, monkeypatch,
):
    from train import guards

    _, dispatched = _track_real_environments(monkeypatch, bridge)
    inputs = bridge.prepare_sql_training(sql_tasks, tmp_path)
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    for turn in range(1, 9):
        assert environment.run_program(PROGRAM).strip() == "17"
        assert environment.turns_used == turn
    assert dispatched == [("first", turn, PROGRAM) for turn in range(1, 9)]
    refusal = guards.TurnBudget(max_turns=8).exhausted_message()
    assert environment.run_program(PROGRAM) == refusal
    assert environment.run_program(PROGRAM) == refusal
    assert environment.turns_used == 8
    assert len(dispatched) == 8


def test_each_reset_rebinds_real_task_and_fresh_budget_without_modifying_prompt(
    bridge, sql_tasks, tmp_path, monkeypatch,
):
    created, _ = _track_real_environments(monkeypatch, bridge)
    inputs = bridge.prepare_sql_training(sql_tasks, tmp_path)
    environment = inputs.environment_factory()
    original_rows = copy.deepcopy(inputs.dataset_rows)
    seen = []
    for index, expected in ((0, "17"), (1, "29"), (0, "17")):
        assert environment.reset(**inputs.dataset_rows[index], rollout_id="ignored") is None
        assert environment.turns_used == 0
        seen.append(created[-1])
        for _ in range(8):
            assert environment.run_program(PROGRAM).strip() == expected
        assert environment.turns_used == 8
    assert len({id(item) for item in seen}) == 3
    assert len({id(item.budget) for item in seen}) == 3
    assert inputs.dataset_rows == original_rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "unknown-task"),
        ("task_id", None),
        ("prompt", [{"role": "user", "content": "tampered prompt"}]),
        ("prompt", [{"role": "assistant", "content": "wrong role"}]),
        ("prompt", None),
        ("answer", "SELECT 999"),
        ("db_id", "second"),
    ],
    ids=["unknown-id", "null-id", "bad-prompt", "bad-role", "null-prompt", "bad-gold", "bad-db"],
)
def test_failed_reset_clears_previous_executor(training_inputs, field, value):
    environment = training_inputs.environment_factory()
    original = copy.deepcopy(training_inputs.dataset_rows[0])
    environment.reset(**original)
    assert environment.run_program(PROGRAM).strip() == "17"
    invalid = copy.deepcopy(original)
    invalid[field] = value
    with pytest.raises(ValueError):
        environment.reset(**invalid)
    with pytest.raises(RuntimeError, match="reset|bound"):
        environment.run_program(PROGRAM)
    assert environment.reset(**original) is None
    assert environment.turns_used == 0
    assert environment.run_program(PROGRAM).strip() == "17"


def test_missing_database_during_reset_cannot_leave_old_executor_active(
    training_inputs, sql_tasks, tmp_path,
):
    environment = training_inputs.environment_factory()
    environment.reset(**training_inputs.dataset_rows[0])
    assert environment.run_program(PROGRAM).strip() == "17"
    # Move only this test's temporary DB. The previously bound task still exists.
    pathlib.Path(sql_tasks[1].db_path).rename(tmp_path / "moved-second.sqlite")
    with pytest.raises(FileNotFoundError):
        environment.reset(**training_inputs.dataset_rows[1])
    with pytest.raises(RuntimeError, match="reset|bound"):
        environment.run_program(PROGRAM)


@pytest.mark.parametrize("field", ["prompt", "answer", "db_id", "task_id"])
def test_mutable_public_rows_cannot_change_private_prepared_bindings(training_inputs, field):
    original = copy.deepcopy(training_inputs.dataset_rows[0])
    public = training_inputs.dataset_rows[0]
    if field == "prompt":
        public["prompt"][0]["content"] = "injected model prompt"
    else:
        public[field] = training_inputs.dataset_rows[1][field]
    environment = training_inputs.environment_factory()
    assert environment.reset(**original) is None
    assert environment.run_program(PROGRAM).strip() == "17"
    with pytest.raises(ValueError):
        environment.reset(**public)
    with pytest.raises(RuntimeError, match="reset|bound"):
        environment.run_program(PROGRAM)
    assert environment.reset(**original) is None
    assert environment.run_program(PROGRAM).strip() == "17"


@pytest.mark.parametrize("form", ["text", "chat", "after-tool", "empty-tool-calls"])
def test_real_reward_scores_correct_equivalent_wrong_and_malformed_sql(
    training_inputs, sql_tasks, form,
):
    completions = [
        _completion(FINAL_SQL, form),
        _completion("```sql\nSELECT amount + 0 AS equivalent FROM readings;\n```", form),
        _completion("SELECT amount + 1 FROM readings", form),
        _completion("not SQL", form),
    ]
    assert training_inputs.reward(
        completions=completions,
        answer=[sql_tasks[0].gold_sql] * 4,
        db_id=[sql_tasks[0].db_id] * 4,
        task_id=[sql_tasks[0].name] * 4,
    ) == [1.0, 1.0, 0.0, 0.0]


@pytest.mark.parametrize(
    "completion",
    [
        None,
        "",
        [],
        {},
        17,
        [None],
        [{}],
        [17],
        [{"role": "assistant"}],
        [{"role": "assistant", "content": None}],
        [{"role": "assistant", "content": [FINAL_SQL]}],
        [{"role": "assistant", "content": {"sql": FINAL_SQL}}],
        [{"role": "user", "content": FINAL_SQL}],
        [{"role": "system", "content": FINAL_SQL}],
        [{"role": "tool", "content": FINAL_SQL}],
        [{"content": FINAL_SQL}],
        [{"role": "assistant", "content": FINAL_SQL, "tool_calls": [TOOL_CALL]}],
        [
            {"role": "assistant", "content": FINAL_SQL},
            {"role": "tool", "content": FINAL_SQL},
        ],
        [
            {"role": "assistant", "content": FINAL_SQL},
            {"role": "assistant", "content": "17"},
        ],
        [
            {"role": "tool", "content": FINAL_SQL},
            {"role": "assistant", "content": None, "tool_calls": [TOOL_CALL]},
        ],
    ],
    ids=[
        "none", "empty-text", "empty-chat", "bare-dict", "number", "null-message",
        "empty-message", "number-message", "missing-content", "null-content",
        "list-content", "dict-content", "user-ending", "system-ending",
        "tool-ending", "missing-role", "still-tool-calling", "earlier-assistant-sql",
        "no-final-sql", "null-tool-calling-final",
    ],
)
def test_reward_never_scores_observations_earlier_sql_or_nonfinal_messages(
    training_inputs, sql_tasks, completion,
):
    assert training_inputs.reward(
        completions=[completion],
        answer=[sql_tasks[0].gold_sql],
        db_id=[sql_tasks[0].db_id],
    ) == [0.0]


def test_reward_uses_each_rows_real_database_and_accepts_completion_iterables(
    training_inputs, sql_tasks,
):
    # This query is correct only for the first DB, despite identical schemas.
    assert training_inputs.reward(
        completions=iter(["SELECT 17", "SELECT 17"]),
        answer=[task.gold_sql for task in sql_tasks],
        db_id=[task.db_id for task in sql_tasks],
    ) == [1.0, 0.0]


@pytest.mark.parametrize(
    "sizes",
    [(2, 1, 1), (1, 2, 1), (1, 1, 2), (0, 1, 1), (1, 0, 1), (1, 1, 0)],
    ids=["extra-completion", "extra-gold", "extra-db", "no-completion", "no-gold", "no-db"],
)
def test_reward_preserves_strict_metadata_cardinality(training_inputs, sql_tasks, sizes):
    completions, answers, databases = sizes
    with pytest.raises(ValueError):
        training_inputs.reward(
            completions=iter([FINAL_SQL] * completions),
            answer=[sql_tasks[0].gold_sql] * answers,
            db_id=[sql_tasks[0].db_id] * databases,
        )


@pytest.mark.parametrize("completion", [FINAL_SQL, None], ids=["valid-final", "no-final"])
def test_reward_preserves_missing_database_exception(
    training_inputs, sql_tasks, completion,
):
    with pytest.raises(FileNotFoundError):
        training_inputs.reward(
            completions=[completion],
            answer=[sql_tasks[0].gold_sql],
            db_id=["not-mounted"],
        )


def test_reward_keeps_existing_invalid_gold_policy(training_inputs, sql_tasks, tmp_path):
    from train.ex_reward import make_execution_reward

    kwargs = {
        "completions": [FINAL_SQL],
        "answer": ["SELECT nonexistent_column FROM readings"],
        "db_id": [sql_tasks[0].db_id],
    }
    assert training_inputs.reward(**kwargs) == make_execution_reward(tmp_path)(**kwargs) == [0.0]


@pytest.mark.parametrize("version", ["5.2.0", "5.18.0"])
def test_bridge_does_not_relax_frozen_transformers_guard(bridge, version):
    from train import guards

    assert guards.TRANSFORMERS_MAJOR_CEILING == 5
    with pytest.raises(guards.StackError, match="transformers<5"):
        guards.require_stack({
            "unsloth": "2026.10.3", "trl": "1.13.0", "transformers": version,
        })


@pytest.mark.parametrize("argv", [[], ["--preflight-only"]], ids=["main", "preflight-only"])
def test_bridge_import_does_not_open_main_launch_gate(bridge, monkeypatch, argv):
    from train import grpo_ptc, guards

    reached = []

    def forbidden(*args, **kwargs):
        reached.append(True)
        raise AssertionError("blocked launch reached framework/model setup")

    monkeypatch.setattr(grpo_ptc, "require_stack", forbidden)
    monkeypatch.setattr(grpo_ptc, "model_spec", forbidden)
    with pytest.raises(guards.PreconditionUnmet):
        grpo_ptc.main(argv)
    assert reached == []
