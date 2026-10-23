"""Explicit SQL assembly contract, not native runtime or learning verification.

Constructor/tokenizer spies below are labelled wiring-only. Real SQLite calls
and one real datasets.Dataset conversion are exercised independently. No model,
generation, gradients, native template substitute or scratch-source dependency.
Missing implementation fails inside the api fixture, not during collection.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import importlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from bench.task import SqlTask
from train import dead_group_probe, grpo_ptc, guards

REVISION = "a" * 40
PROGRAM = 'rows = execute_sql(query="SELECT amount FROM readings")\nprint(rows[0]["amount"])'
FINAL = [{"role": "assistant", "content": "```sql\nSELECT amount FROM readings\n```"}]
REJECTIONS = (ValueError, RuntimeError, guards.InvariantViolation)
FRAMEWORKS = {"torch", "transformers", "trl", "unsloth", "peft", "vllm", "datasets"}


@pytest.fixture
def api():
    try:
        return importlib.import_module("train.native_training")
    except ModuleNotFoundError as exc:
        if exc.name == "train.native_training":
            pytest.fail("missing train.native_training implementation, expected failure-first RED")
        raise


@pytest.fixture
def tasks(tmp_path):
    out = []
    for name, value in (("first", 17), ("second", 29)):
        directory = tmp_path / name
        directory.mkdir()
        database = directory / f"{name}.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            connection.execute("INSERT INTO readings VALUES (?)", (value,))
        out.append(SqlTask(
            name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
            evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
            db_id=name, db_path=str(database), tier="simple", tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture",
        ))
    return out


def _replace_preflight(monkeypatch, api, replacement):
    """Patch actual module and an optional imported alias, not a public bypass."""
    monkeypatch.setattr(grpo_ptc, "preflight", replacement)
    if hasattr(api, "preflight"):
        monkeypatch.setattr(api, "preflight", replacement)


def _replace_runtime_requirement(monkeypatch, api, replacement):
    runtime = importlib.import_module("train.native_runtime")
    monkeypatch.setattr(runtime, "require_native_runtime", replacement)
    if hasattr(api, "require_native_runtime"):
        monkeypatch.setattr(api, "require_native_runtime", replacement)


@pytest.fixture
def wiring(monkeypatch, api, tasks, tmp_path):
    """Private constructor spies only: passing these checks proves wiring."""
    state = SimpleNamespace(
        events=[], loader_calls=[], peft_calls=[], config_calls=[], dataset_calls=[],
        trainer_calls=[], renders=[], suffix_calls=[], forbidden_calls=[],
        prefix_bad=False, missing_attribute=None, tools_mode="one", schema_bad=False,
        longest_prompt=21, model=object(), adapted_model=object(),
        dtype=object(), selected_template="NATIVE_TRAINER_TEMPLATE_WIRING_ONLY",
        stock_template="STOCK_TOKENIZER_TEMPLATE_WIRING_ONLY",
    )

    def preflight(arms=grpo_ptc.TRAINED_ARMS_DEFAULT, root=guards.REPO_ROOT, *, steps=200):
        state.events.append(("preflight", Path(root), steps))
        return grpo_ptc.training_config(arms, steps=steps)

    def require_runtime():
        state.events.append(("require_native_runtime",))
        return {"runtime_verified": False, "training_verified": False, "launch_authorized": False}

    state.actual_runtime_requirement = importlib.import_module(
        "train.native_runtime",
    ).require_native_runtime
    _replace_preflight(monkeypatch, api, preflight)
    _replace_runtime_requirement(monkeypatch, api, require_runtime)

    class FastLanguageModel:
        @staticmethod
        def from_pretrained(**kwargs):
            state.events.append(("model",))
            state.loader_calls.append(kwargs)
            return state.model, tokenizer

        @staticmethod
        def get_peft_model(model, **kwargs):
            assert model is state.model
            state.peft_calls.append(kwargs)
            return state.adapted_model

    class Dataset:
        @staticmethod
        def from_list(rows):
            state.events.append(("dataset",))
            snapshot = copy.deepcopy(rows)
            state.dataset_calls.append(snapshot)
            return snapshot

    class Tokenizer:
        chat_template = state.stock_template

        def apply_chat_template(self, conversation=None, **kwargs):
            state.renders.append((copy.deepcopy(conversation), dict(kwargs)))
            assert kwargs.get("chat_template") == state.selected_template
            assert kwargs.get("enable_thinking") is False
            assert kwargs.get("add_generation_prompt") is True
            assert kwargs.get("tokenize") is True
            assert len(kwargs["tools"]) == 1
            assert kwargs["tools"][0].__name__ == "run_program"
            text = json.dumps(conversation)
            count = state.longest_prompt if "FIXTURE_SECOND" in text else 13
            ids = [3] * count
            # Either single-conversation explicit-list or upstream batched
            # return_dict=True rendering is valid. Both must use native kwargs.
            if kwargs.get("return_dict", False):
                batched = bool(conversation and isinstance(conversation[0], list))
                return {"input_ids": [ids] if batched else ids}
            return [ids] if conversation and isinstance(conversation[0], list) else ids

    tokenizer = Tokenizer()
    state.tokenizer = tokenizer

    class GRPOConfig:
        def __init__(self, **kwargs):
            state.config_calls.append(kwargs)
            self.__dict__.update(kwargs)

    class GRPOTrainer:
        def __init__(self, **kwargs):
            state.events.append(("trainer",))
            state.trainer_calls.append(kwargs)
            self.kwargs = kwargs
            self.args = kwargs["args"]
            self.processing_class = kwargs["processing_class"]
            self.chat_template = state.selected_template
            self.chat_template_kwargs = dict(self.args.chat_template_kwargs)
            environment = kwargs["environment_factory"]()
            tools = [
                method for name, method in inspect.getmembers(environment, inspect.ismethod)
                if name not in {"reset", "get_reward"} and not name.startswith("_")
            ]
            if state.tools_mode == "two":
                tools = tools + [tools[0]]
            elif state.tools_mode == "wrong":
                def another_tool(code: str):
                    return code
                tools = [another_tool]
            elif state.tools_mode == "missing_key":
                self._env_tools = {"different_environment": tools}
            if state.tools_mode != "missing_key":
                self._env_tools = {None: tools}
            if state.missing_attribute:
                delattr(self, state.missing_attribute)

        def _get_tool_suffix_ids(self, tool_messages):
            state.suffix_calls.append(copy.deepcopy(tool_messages))
            assert tool_messages
            assert all(message["role"] == "tool" for message in tool_messages)
            assert all(message["name"] == "run_program" for message in tool_messages)
            if state.prefix_bad:
                raise ValueError("Unexpected tokenization: prefix IDs are not a prefix of full IDs")
            return [50, 51]

        def train(self, *args, **kwargs):
            state.forbidden_calls.append("train")
            raise AssertionError("assembly must not train")

        def save_model(self, *args, **kwargs):
            state.forbidden_calls.append("save_model")
            raise AssertionError("assembly must not save")

        def save_state(self, *args, **kwargs):
            state.forbidden_calls.append("save_state")
            raise AssertionError("assembly must not save state")

        def _save_checkpoint(self, *args, **kwargs):
            state.forbidden_calls.append("_save_checkpoint")
            raise AssertionError("assembly must not checkpoint")

    def get_json_schema(method):
        schema = copy.deepcopy(grpo_ptc.THE_TOOL_SCHEMA)
        schema["function"]["name"] = method.__name__
        if state.schema_bad:
            schema["function"]["parameters"]["properties"]["extra"] = {"type": "string"}
        return schema

    runtime = SimpleNamespace(
        FastLanguageModel=FastLanguageModel, torch=SimpleNamespace(float16=state.dtype),
        Dataset=Dataset, GRPOConfig=GRPOConfig, GRPOTrainer=GRPOTrainer,
        get_json_schema=get_json_schema,
    )

    def load_runtime():
        state.events.append(("load_runtime",))
        return runtime

    monkeypatch.setattr(api, "_load_runtime", load_runtime)
    state.runtime = runtime
    state.output = tmp_path / "fresh-output"
    state.tasks = tasks
    state.db_root = tmp_path

    def build(**overrides):
        values = dict(
            output_dir=state.output, model_revision=REVISION,
            max_seq_length=grpo_ptc.training_config()["max_completion_length"] + 21,
        )
        values.update(overrides)
        return api.build_sql_trainer(tasks, tmp_path, **values)

    state.build = build
    yield state
    assert state.forbidden_calls == []
    assert tokenizer.chat_template == state.stock_template


def test_public_constructor_has_no_runtime_or_gate_injection(api):
    signature = inspect.signature(api.build_sql_trainer)
    assert list(signature.parameters) == [
        "tasks", "db_root", "output_dir", "model_revision", "max_seq_length", "steps", "root",
    ]
    for name in ("output_dir", "model_revision", "max_seq_length", "steps", "root"):
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["steps"].default == 200
    assert Path(signature.parameters["root"].default) == guards.REPO_ROOT


def test_real_gate_blocks_before_runtime_side_effects(api, tasks, tmp_path, monkeypatch):
    attempted = []
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in FRAMEWORKS:
            attempted.append(name)
            raise AssertionError("framework imported before closed preflight")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        attempted.append("runtime/bridge work")
        raise AssertionError("work attempted before closed preflight")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(api, "_load_runtime", forbidden)
    _replace_runtime_requirement(monkeypatch, api, forbidden)
    from train import sql_bridge
    monkeypatch.setattr(sql_bridge, "prepare_sql_training", forbidden)
    if hasattr(api, "prepare_sql_training"):
        monkeypatch.setattr(api, "prepare_sql_training", forbidden)
    output = tmp_path / "never-created"
    with pytest.raises(guards.PreconditionUnmet, match="gate|frontier"):
        api.build_sql_trainer(
            tasks, tmp_path, output_dir=output, model_revision=REVISION, max_seq_length=8192,
        )
    assert attempted == []
    assert not output.exists()


def test_real_gate_survives_optimized_python(api, tasks, tmp_path):
    code = """
import builtins, json, pathlib, sys
from bench.task import SqlTask
from train import guards
original = builtins.__import__
def guarded(name, *a, **kw):
    if name.split('.')[0] in {'torch','transformers','trl','unsloth','peft','vllm','datasets'}:
        raise RuntimeError('framework import before preflight')
    return original(name, *a, **kw)
builtins.__import__ = guarded
from train.native_training import build_sql_trainer
tasks = [SqlTask(**row) for row in json.loads(sys.argv[1])]
try:
    build_sql_trainer(tasks, sys.argv[2], output_dir=sys.argv[3],
                      model_revision='a'*40, max_seq_length=8192)
except guards.PreconditionUnmet:
    if pathlib.Path(sys.argv[3]).exists():
        raise RuntimeError('output created before gate')
    print('REAL_GATE_CLOSED')
else:
    raise RuntimeError('closed preflight bypassed')
"""
    output = tmp_path / "optimized-output"
    result = subprocess.run(
        [sys.executable, "-O", "-B", "-c", code,
         json.dumps([dataclasses.asdict(task) for task in tasks]), str(tmp_path), str(output)],
        cwd=guards.REPO_ROOT,
        env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
             "HF_DATASETS_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REAL_GATE_CLOSED"
    assert not output.exists()


def test_preflight_then_fresh_runtime_requirement_then_imports(wiring):
    wiring.build()
    assert [event[0] for event in wiring.events[:3]] == [
        "preflight", "require_native_runtime", "load_runtime",
    ]
    assert wiring.events[0] == ("preflight", guards.REPO_ROOT, 200)


def test_runtime_rejection_precedes_imports_and_output(wiring, api, monkeypatch):
    runtime = importlib.import_module("train.native_runtime")

    _replace_runtime_requirement(monkeypatch, api, wiring.actual_runtime_requirement)
    with pytest.raises(runtime.NativeRuntimeError):
        wiring.build()
    assert [event[0] for event in wiring.events] == ["preflight"]
    assert wiring.loader_calls == wiring.dataset_calls == wiring.trainer_calls == []
    assert not wiring.output.exists()


def test_two_task_assembly_preserves_native_inputs(wiring):
    trainer = wiring.build()
    rows = wiring.dataset_calls[0]
    assert len(wiring.dataset_calls) == len(wiring.trainer_calls) == 1
    assert len(rows) == 2
    assert all(set(row) == {"prompt", "task_id", "answer", "db_id"} for row in rows)
    assert [row["task_id"] for row in rows] == ["first", "second"]
    assert all(isinstance(row["prompt"], list) for row in rows)
    assert all("GOLD_" not in json.dumps(row["prompt"]) for row in rows)
    assert "tools" not in trainer.kwargs
    assert len(trainer._env_tools[None]) == 1
    assert trainer._env_tools[None][0].__name__ == "run_program"
    assert "optimizers" not in trainer.kwargs
    assert not trainer.kwargs.get("callbacks")
    environment = trainer.kwargs["environment_factory"]()
    for row, value in zip(rows, ("17", "29"), strict=True):
        assert environment.reset(**row) is None
        assert environment.turns_used == 0
        assert environment.run_program(PROGRAM).strip() == value
        assert environment.turns_used == 1
    reward = trainer.kwargs["reward_funcs"]
    assert len(reward) == 1
    assert reward[0] is not dead_group_probe.exact_match_reward
    assert reward[0](
        completions=[FINAL, FINAL],
        answer=[row["answer"] for row in rows], db_id=[row["db_id"] for row in rows],
    ) == [1.0, 1.0]
    assert reward[0](
        completions=[[{"role": "assistant", "content": "SELECT 0"}]] * 2,
        answer=[row["answer"] for row in rows], db_id=[row["db_id"] for row in rows],
    ) == [0.0, 0.0]


@pytest.mark.parametrize("steps", [1, 17, 200])
def test_constructor_arguments_are_separate(wiring, steps):
    trainer = wiring.build(steps=steps)
    assert len(wiring.loader_calls) == len(wiring.peft_calls) == len(wiring.config_calls) == 1
    loader = wiring.loader_calls[0]
    assert loader["model_name"] == dead_group_probe.MODEL
    assert loader["revision"] == REVISION
    assert loader["local_files_only"] is True
    assert loader["dtype"] is wiring.dtype
    assert loader["max_seq_length"] == trainer.args.max_completion_length + 21
    assert loader["load_in_4bit"] is False
    assert loader["fast_inference"] is True
    assert loader["max_lora_rank"] == dead_group_probe.LORA_RANK
    assert loader["gpu_memory_utilization"] == dead_group_probe.GPU_MEMORY_UTILIZATION
    assert not {"lora_rank", "reward_funcs", "environment_factory"} & loader.keys()
    assert wiring.peft_calls[0]["r"] == wiring.peft_calls[0]["lora_alpha"] == dead_group_probe.LORA_RANK
    assert trainer.kwargs["model"] is wiring.adapted_model
    config = wiring.config_calls[0]
    for key, value in grpo_ptc.training_config(steps=steps).items():
        assert config[key] == value
    per_device, accumulation = dead_group_probe.batch_for(dead_group_probe.NUM_GENERATIONS)
    assert config["per_device_train_batch_size"] == per_device
    assert config["gradient_accumulation_steps"] == accumulation
    assert config["remove_unused_columns"] is False
    assert config["max_tool_calling_iterations"] == guards.eval_max_turns()
    assert Path(config["output_dir"]) == wiring.output
    assert wiring.events[0][-1] == steps


def test_checkpoint_configuration_is_not_restore_proof(wiring):
    trainer = wiring.build(steps=17)
    assert trainer.args.save_strategy == "steps"
    assert trainer.args.save_steps == 17
    assert trainer.args.save_only_model is False
    assert trainer.args.push_to_hub is False
    assert wiring.forbidden_calls == []
    assert not list(wiring.output.glob("checkpoint-*"))


@pytest.mark.parametrize("override", [
    {"model_revision": None}, {"model_revision": "main"}, {"model_revision": "a" * 39},
    {"model_revision": "g" * 40}, {"model_revision": True},
    {"max_seq_length": 0}, {"max_seq_length": -1}, {"max_seq_length": True},
    {"max_seq_length": 3537.0}, {"max_seq_length": "3537"},
    {"steps": 0}, {"steps": True}, {"steps": 1.5},
])
def test_invalid_caller_inputs_reject_before_runtime_imports(wiring, override):
    with pytest.raises((ValueError, TypeError)):
        wiring.build(**override)
    assert not any(event[0] == "load_runtime" for event in wiring.events)
    assert wiring.loader_calls == wiring.dataset_calls == wiring.trainer_calls == []
    assert not wiring.output.exists()


@pytest.mark.parametrize("kind", ["nonempty", "file", "symlink", "dangling_symlink"])
def test_unsafe_output_rejected_without_overwrite(wiring, tmp_path, kind):
    output = wiring.output
    if kind == "nonempty":
        output.mkdir()
        (output / "keep.txt").write_text("KEEP")
    elif kind == "file":
        output.write_text("KEEP")
    else:
        target = tmp_path / "other-output"
        if kind == "symlink":
            target.mkdir()
        output.symlink_to(target, target_is_directory=True)
    with pytest.raises((ValueError, TypeError, OSError)):
        wiring.build()
    assert not any(event[0] == "load_runtime" for event in wiring.events)
    assert wiring.loader_calls == wiring.dataset_calls == wiring.trainer_calls == []
    if kind == "nonempty":
        assert (output / "keep.txt").read_text() == "KEEP"
    elif kind == "file":
        assert output.read_text() == "KEEP"
    else:
        assert output.is_symlink()


def test_existing_empty_output_is_not_a_nonempty_overwrite(wiring):
    wiring.output.mkdir()
    assert wiring.build() is not None
    assert list(wiring.output.iterdir()) == []


@pytest.mark.parametrize("contaminant", ["torch", "transformers", "trl", "peft"])
def test_private_runtime_loader_rejects_contaminated_process_before_import(
    api, monkeypatch, contaminant,
):
    attempted = []
    monkeypatch.setitem(sys.modules, contaminant, SimpleNamespace())
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in FRAMEWORKS:
            attempted.append(name)
            raise AssertionError("fresh-process guard allowed framework import")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(REJECTIONS, match="fresh|already|order|process|import"):
        api._load_runtime()
    assert attempted == []


@pytest.mark.parametrize("attribute", [
    "processing_class", "chat_template", "chat_template_kwargs", "_env_tools",
])
def test_missing_native_attributes_reject_instead_of_fallback(wiring, attribute):
    wiring.missing_attribute = attribute
    with pytest.raises(REJECTIONS, match=attribute):
        wiring.build()


def test_missing_native_suffix_method_rejects(wiring, monkeypatch):
    monkeypatch.delattr(wiring.runtime.GRPOTrainer, "_get_tool_suffix_ids")
    with pytest.raises(REJECTIONS, match="suffix|_get_tool_suffix_ids"):
        wiring.build()


@pytest.mark.parametrize("mode", ["two", "wrong", "missing_key"])
def test_native_discovery_requires_exact_one_program_tool(wiring, mode):
    wiring.tools_mode = mode
    with pytest.raises(REJECTIONS, match="tool|environment|run_program|None"):
        wiring.build()


def test_native_discovered_schema_must_match_canonical_tool(wiring):
    wiring.schema_bad = True
    with pytest.raises(REJECTIONS, match="schema|tool|run_program"):
        wiring.build()


def test_actual_native_template_context_uses_all_rows_and_kwargs(wiring):
    trainer = wiring.build()
    assert len(wiring.renders) == 2
    assert all(kwargs["chat_template"] == trainer.chat_template for _, kwargs in wiring.renders)
    assert trainer.processing_class.chat_template != trainer.chat_template
    assert all(kwargs["tools"] == trainer._env_tools[None] for _, kwargs in wiring.renders)
    assert all(kwargs["enable_thinking"] is False for _, kwargs in wiring.renders)
    assert wiring.suffix_calls
    rendered_text = json.dumps([conversation for conversation, _ in wiring.renders])
    assert "FIXTURE_FIRST" in rendered_text and "FIXTURE_SECOND" in rendered_text
    assert "GOLD_" not in rendered_text


def test_one_token_context_undersize_rejects(wiring):
    cap = grpo_ptc.training_config()["max_completion_length"]
    with pytest.raises(REJECTIONS, match="context|sequence|length|token"):
        wiring.build(max_seq_length=cap + wiring.longest_prompt - 1)
    assert len(wiring.trainer_calls) == 1
    assert wiring.forbidden_calls == []


def test_actual_native_suffix_prefix_failure_propagates_without_identity_fix(wiring):
    wiring.prefix_bad = True
    with pytest.raises(REJECTIONS, match="prefix"):
        wiring.build()
    assert len(wiring.suffix_calls) == 1
    assert wiring.tokenizer.chat_template == wiring.stock_template


def test_real_dataset_arrow_interop_only_not_selected_runtime_compatibility(wiring):
    # Installed datasets5.0.1 is outside selected Unsloth datasets<5. Real Arrow
    # conversion here proves row interoperability ONLY, not runtime admission.
    from datasets import Dataset

    wiring.runtime.Dataset = Dataset
    trainer = wiring.build()
    dataset = trainer.kwargs["train_dataset"]
    assert isinstance(dataset, Dataset)
    assert dataset.column_names == ["prompt", "task_id", "answer", "db_id"]
    assert len(dataset) == 2
    assert dataset[0]["task_id"] == "first" and dataset[1]["task_id"] == "second"
    assert dataset[0]["answer"] == wiring.tasks[0].gold_sql
    assert dataset[1]["answer"] == wiring.tasks[1].gold_sql
    assert isinstance(dataset[0]["prompt"], list)
    environment = trainer.kwargs["environment_factory"]()
    environment.reset(**dataset[1])
    assert environment.run_program(PROGRAM).strip() == "29"
