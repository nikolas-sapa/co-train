"""Phase B constructor forwarding, not actual TRL/runtime acceptance.

Private preflight/model/framework/schema doubles below prove source wiring only.
Real-gate tests keep the original preflight. SQLite, bridge/reset, SQL reward and
restricted catalog execution are real. No actual framework/model is imported.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import importlib
import inspect
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

REVISION = "a" * 40
PROGRAM = 'print(execute_sql(query="SELECT amount FROM readings")[0]["amount"])'
FRAMEWORKS = {
    "torch", "transformers", "trl", "unsloth", "unsloth_zoo", "vllm",
    "datasets", "peft", "accelerate", "bitsandbytes", "verifiers",
    "httpx", "huggingface_hub",
}


@pytest.fixture(autouse=True)
def no_frameworks(monkeypatch):
    original = builtins.__import__
    original_module = importlib.import_module
    attempted = []

    def check(name):
        if name.split(".")[0] in FRAMEWORKS or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"unexpected framework import: {name}")

    def guarded(name, *args, **kwargs):
        check(name)
        return original(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    yield
    assert attempted == []


@pytest.fixture
def sql_tasks(tmp_path):
    from bench.task import SqlTask

    tasks = []
    for name, value in (("first", 17), ("second", 29)):
        directory = tmp_path / name
        directory.mkdir()
        database = directory / f"{name}.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            connection.execute("INSERT INTO readings VALUES (?)", (value,))
            connection.commit()
        finally:
            connection.close()
        tasks.append(SqlTask(
            name=name, question="What amount is recorded?", evidence="Use readings.",
            gold_sql=f"SELECT amount FROM readings /* GOLD_ONLY_{name} */",
            db_id=name, db_path=str(database), tier="simple", tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture",
        ))
    return tasks


@pytest.fixture
def native_wiring(monkeypatch, sql_tasks, tmp_path, no_frameworks):
    """Shared NEW-test private constructor doubles, never a real TRL stack."""
    from train import grpo_ptc, native_training

    state = SimpleNamespace(
        api=native_training, tasks=sql_tasks, db_root=tmp_path,
        events=[], prepare_calls=[], prepared=[], prepared_rows=[], trainers=[], callbacks=[],
        renders=[], schemas=[], suffixes=[], loader_calls=[], configs=[],
        forbidden=[], model=object(), adapted_model=object(), dtype=object(),
        output=tmp_path / "never-created-output", model_dir=tmp_path / "unread-model",
        selected_template="PRIVATE_CONSTRUCTOR_TEMPLATE_ONLY",
    )
    state.original_config = grpo_ptc.training_config()
    config_before = copy.deepcopy(state.original_config)
    tasks_before = copy.deepcopy(sql_tasks)
    real_prepare = native_training.sql_bridge.prepare_sql_training

    def preflight(*, root, steps):
        state.events.append("preflight")
        assert root is native_training.guards.REPO_ROOT
        assert steps == state.original_config["max_steps"]
        return state.original_config

    def verify(model_dir, *, model_revision):
        state.events.append("verify_model")
        assert model_dir == state.model_dir
        assert model_revision == REVISION
        return SimpleNamespace(path=str(model_dir))

    def prepare(tasks, db_root, **kwargs):
        state.events.append("prepare")
        state.prepare_calls.append((tasks, db_root, kwargs))
        prepared = real_prepare(tasks, db_root, **kwargs)
        state.prepared.append(prepared)
        state.prepared_rows.append(copy.deepcopy(prepared.dataset_rows))
        return prepared

    class Dataset:
        @staticmethod
        def from_list(rows):
            state.events.append("dataset")
            return SimpleNamespace(rows=rows)

    class Tokenizer:
        chat_template = "UNMODIFIED_STOCK_TEMPLATE"

        def apply_chat_template(self, messages, **kwargs):
            state.renders.append((copy.deepcopy(messages), kwargs))
            assert kwargs["chat_template"] == state.selected_template
            assert kwargs["enable_thinking"] is False
            assert kwargs["tokenize"] is True
            assert kwargs["add_generation_prompt"] is True
            assert kwargs["return_dict"] is False
            return [7] * 11

    tokenizer = Tokenizer()

    class FastLanguageModel:
        @staticmethod
        def from_pretrained(**kwargs):
            state.events.append("model")
            state.loader_calls.append(kwargs)
            return state.model, tokenizer

        @staticmethod
        def get_peft_model(model, **kwargs):
            state.events.append("peft")
            assert model is state.model
            return state.adapted_model

    class Config:
        def __init__(self, **kwargs):
            state.events.append("config")
            state.configs.append(kwargs)
            self.__dict__.update(kwargs)

    class Trainer:
        def __init__(self, **kwargs):
            state.events.append("trainer")
            state.trainers.append(self)
            self.kwargs = kwargs
            self.processing_class = kwargs["processing_class"]
            self.chat_template = state.selected_template
            self.chat_template_kwargs = dict(kwargs["args"].chat_template_kwargs)
            environment = kwargs["environment_factory"]()
            self._env_tools = {None: [
                method for name, method in inspect.getmembers(environment, inspect.ismethod)
                if not name.startswith("_") and name not in {"reset", "get_reward"}
            ]}

        def _get_tool_suffix_ids(self, messages):
            state.events.append("suffix")
            state.suffixes.append(messages)
            return [50, 51]

        def add_callback(self, callback):
            state.events.append("attach")
            state.callbacks.append(callback)

        def __getattribute__(self, name):
            if name in {
                "train", "save_model", "save_state", "_save_checkpoint",
                "resume", "resume_from_checkpoint", "push_to_hub",
            }:
                state.forbidden.append(name)
                raise AssertionError(f"constructor attempted {name}")
            return object.__getattribute__(self, name)

    def schema_double(method):
        """Canonical-schema double, NOT the installed Transformers converter."""
        signature = inspect.signature(method)
        assert method.__name__ == "run_program"
        assert list(signature.parameters) == ["code"]
        assert signature.parameters["code"].annotation == "str"
        assert signature.return_annotation is inspect.Signature.empty
        assert inspect.getdoc(method).startswith(
            "Execute a Python program against the typed catalog."
        )
        state.schemas.append(method)
        return copy.deepcopy(grpo_ptc.THE_TOOL_SCHEMA)

    runtime = SimpleNamespace(
        Dataset=Dataset, FastLanguageModel=FastLanguageModel,
        torch=SimpleNamespace(float16=state.dtype), GRPOConfig=Config,
        GRPOTrainer=Trainer, get_json_schema=schema_double,
    )

    def load():
        state.events.append("runtime")
        return runtime

    monkeypatch.setattr(grpo_ptc, "native_sql_preflight", preflight)
    monkeypatch.setattr(native_training.native_model, "verify_local_model", verify)
    monkeypatch.setattr(native_training.sql_bridge, "prepare_sql_training", prepare)
    monkeypatch.setattr(native_training, "_load_runtime", load)
    state.prepare = prepare
    state.runtime = runtime
    state.kwargs = dict(
        output_dir=state.output, model_dir=state.model_dir,
        model_revision=REVISION,
        max_seq_length=state.original_config["max_completion_length"] + 16,
        steps=200, root=native_training.guards.REPO_ROOT,
    )

    def build(**kwargs):
        return native_training.build_sql_trainer(
            state.tasks, state.db_root, **{**state.kwargs, **kwargs},
        )

    state.build = build
    yield state
    assert state.forbidden == []
    assert state.original_config == config_before
    assert state.tasks == tasks_before
    assert [prepared.dataset_rows for prepared in state.prepared] == state.prepared_rows
    assert tokenizer.chat_template == "UNMODIFIED_STOCK_TEMPLATE"
    assert not state.output.exists()


def assert_real_reporting(trainer, *, message="native reporting snapshot missing after reset"):
    """Exercise the actual accepted bridge; usable by both new forwarding tests."""
    from ptc.sql_qa import report_ack
    from train.sql_reporting import snapshot_to_dict

    environment = trainer.kwargs["environment_factory"]()
    row = trainer.kwargs["train_dataset"].rows[0]
    environment.reset(**row)
    observed = environment.run_program(
        'print(report_defect(kind="other", detail="forwarding control"))'
    )
    snapshot = environment.reporting_snapshot
    assert snapshot is not None, message
    assert snapshot_to_dict(snapshot)["arms"]["ptc"]["reports"] == 1
    assert observed == report_ack()


def test_explicit_keyword_only_reporting_signature():
    from train import native_training

    signature = inspect.signature(native_training.build_sql_trainer)
    assert list(signature.parameters) == [
        "tasks", "db_root", "output_dir", "model_dir", "model_revision",
        "max_seq_length", "steps", "root", "reporting",
    ]
    assert signature.parameters["reporting"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["reporting"].default is None


@pytest.mark.parametrize("explicit_none", [False, True])
def test_default_keeps_old_prepare_signature(native_wiring, monkeypatch, explicit_none):
    state = native_wiring
    calls = []

    def old_signature(tasks, db_root, *, root):
        calls.append((tasks, db_root, root))
        return state.prepare(tasks, db_root, root=root)

    monkeypatch.setattr(state.api.sql_bridge, "prepare_sql_training", old_signature)
    trainer = state.build(**({"reporting": None} if explicit_none else {}))
    assert len(calls) == len(state.prepare_calls) == 1
    assert calls[0][0] is state.tasks and calls[0][1] is state.db_root
    assert calls[0][2] is state.kwargs["root"]
    environment = trainer.kwargs["environment_factory"]()
    for row, expected in zip(trainer.kwargs["train_dataset"].rows, ("17", "29"), strict=True):
        environment.reset(**row)
        assert environment.run_program(PROGRAM) == expected
        assert environment.reporting_snapshot is None


def test_identical_config_once_reaches_real_factory_and_keeps_native_contracts(
    native_wiring, monkeypatch,
):
    from ptc.sql_arms import build_sql_arms
    from ptc.sql_qa import report_ack
    from train import sql_reporting

    state = native_wiring
    config = sql_reporting.ReportingConfig(shortcut_ids=("fixture_shortcut",))
    before_config = dataclasses.asdict(config)
    before_db = [Path(task.db_path).read_bytes() for task in state.tasks]
    channels = []
    original_channel = sql_reporting.make_channel

    def tracked(config):
        channel = original_channel(config)
        channels.append(channel)
        return channel

    monkeypatch.setattr(sql_reporting, "make_channel", tracked)
    trainer = state.build(reporting=config)
    assert trainer is state.trainers[0]
    assert state.events == [
        "preflight", "verify_model", "prepare", "runtime", "dataset",
        "model", "peft", "config", "trainer", "suffix",
    ]
    assert len(state.prepare_calls) == 1
    tasks, db_root, kwargs = state.prepare_calls[0]
    assert tasks is state.tasks and db_root is state.db_root
    assert kwargs == {"root": state.kwargs["root"], "reporting": config}
    assert kwargs["reporting"] is config
    prepared = state.prepared[0]
    assert trainer.kwargs["train_dataset"].rows is prepared.dataset_rows
    assert trainer.kwargs["environment_factory"] is prepared.environment_factory
    assert trainer.kwargs["reward_funcs"] == [prepared.reward]
    assert len(state.schemas) == len(state.suffixes) == 1
    assert len(state.renders) == 2
    assert [tool.__name__ for tool in trainer._env_tools[None]] == ["run_program"]
    assert state.configs[0]["max_tool_calling_iterations"] == (
        prepared.max_tool_calling_iterations
    ) == 8
    assert state.configs[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert state.loader_calls[0]["model_name"] == str(state.model_dir)
    assert state.loader_calls[0]["local_files_only"] is True
    assert state.loader_calls[0]["dtype"] is state.dtype
    assert trainer.kwargs["model"] is state.adapted_model
    assert len(channels) == 2  # Ephemeral preparation, not reset rollouts.
    environment = prepared.environment_factory()
    old_snapshots = []
    for index, row in enumerate(prepared.dataset_rows):
        assert set(row) == {"prompt", "task_id", "answer", "db_id"}
        prompt = row["prompt"][0]["content"]
        assert prompt == build_sql_arms(
            state.tasks[index], qa=original_channel(config),
        ).prompt("ptc")
        assert "GOLD_ONLY" not in prompt
        environment.reset(**row)
        assert environment.turns_used == 0
        assert environment.run_program(PROGRAM) == ("17", "29")[index]
        assert environment.run_program(
            f'print(report_defect(kind="other", detail="reset-{index}"))'
        ) == report_ack()
        snapshot = environment.reporting_snapshot
        old_snapshots.append((snapshot, snapshot.data))
        doc = sql_reporting.snapshot_to_dict(snapshot)
        assert doc["arms"]["ptc"]["reports"] == doc["total_events"] == 1
        assert doc["arms"]["ptc"]["events"][0]["detail"] == f"reset-{index}"
        assert doc["arms"]["bash"]["events"] == []
        assert prepared.reward(
            ["SELECT amount FROM readings", "SELECT amount + 1 FROM readings"],
            answer=[row["answer"]] * 2, db_id=[row["db_id"]] * 2,
        ) == [1.0, 0.0]
    assert len(channels) == 4
    assert channels[2] is not channels[3]
    assert all(not channel.events for channel in channels[:2])
    assert [channel.events[0]["detail"] for channel in channels[2:]] == ["reset-0", "reset-1"]
    assert all(snapshot.data == original for snapshot, original in old_snapshots)
    assert dataclasses.asdict(config) == before_config
    assert [Path(task.db_path).read_bytes() for task in state.tasks] == before_db


@pytest.mark.parametrize("malformed", [False, True])
def test_real_preflight_still_refuses_before_any_work(monkeypatch, tmp_path, malformed):
    from train import grpo_ptc, guards, native_training, sql_reporting

    reporting = False if malformed else sql_reporting.ReportingConfig()
    with pytest.raises(guards.PreconditionUnmet) as expected:
        grpo_ptc.native_sql_preflight(root=guards.REPO_ROOT, steps=200)
    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append("downstream")
        raise AssertionError("work preceded real closed gate")

    for owner, name in (
        (native_training, "_load_runtime"),
        (native_training.native_model, "verify_local_model"),
        (native_training.sql_bridge, "prepare_sql_training"),
        (sql_reporting, "make_channel"), (sql_reporting, "validate_config"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    output = tmp_path / "never-created"
    with pytest.raises(guards.PreconditionUnmet) as caught:
        native_training.build_sql_trainer(
            object(), object(), output_dir=output,
            model_dir=tmp_path / "unread-model", model_revision=REVISION,
            max_seq_length=8192, reporting=reporting,
        )
    assert type(caught.value) is type(expected.value)
    assert str(caught.value) == str(expected.value)
    tb = caught.value.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is guards.require_frontier_taskset.__code__
    assert attempted == [] and not output.exists()


@pytest.mark.parametrize(
    "field,value,message",
    [("model_revision", "main", "model_revision must be a full 40-hex revision"),
     ("max_seq_length", True, "max_seq_length must be a positive integer"),
     ("steps", 0, "steps must be a positive integer")],
)
def test_bad_arguments_precede_gate_and_reporting_validation(
    monkeypatch, tmp_path, field, value, message,
):
    from train import grpo_ptc, native_training, sql_reporting

    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append("work")
        raise AssertionError("bad input reached downstream work")

    monkeypatch.setattr(grpo_ptc, "native_sql_preflight", forbidden)
    monkeypatch.setattr(sql_reporting, "validate_config", forbidden)
    kwargs = dict(
        output_dir=tmp_path / "out", model_dir=tmp_path / "model",
        model_revision=REVISION, max_seq_length=8192, steps=200, reporting=False,
    )
    kwargs[field] = value
    with pytest.raises(ValueError) as caught:
        native_training.build_sql_trainer(object(), object(), **kwargs)
    assert str(caught.value) == message
    assert attempted == []


def test_bridge_remains_config_validator_after_preflight_and_model(native_wiring):
    state = native_wiring
    with pytest.raises(TypeError) as caught:
        state.build(reporting=False)
    assert str(caught.value) == "expected an exact ReportingConfig"
    assert state.events == ["preflight", "verify_model", "prepare"]
    assert len(state.prepare_calls) == 1 and state.prepare_calls[0][2]["reporting"] is False
    assert state.trainers == []


def test_reporting_keeps_existing_native_context_bound(native_wiring):
    from train.sql_reporting import ReportingConfig

    state = native_wiring
    with pytest.raises(ValueError, match="above caller max_seq_length"):
        state.build(
            reporting=ReportingConfig(),
            max_seq_length=state.original_config["max_completion_length"] + 10,
        )
    assert len(state.schemas) == len(state.suffixes) == len(state.trainers) == 1


def test_native_forwarding_loss_canary_then_restored_positive(native_wiring, monkeypatch):
    from train.sql_reporting import ReportingConfig

    state = native_wiring
    config = ReportingConfig()

    def drop_reporting(tasks, db_root, *, root, reporting=None):
        return state.prepare(tasks, db_root, root=root)

    with monkeypatch.context() as lost:
        lost.setattr(state.api.sql_bridge, "prepare_sql_training", drop_reporting)
        trainer = state.build(reporting=config)  # Valid constructor, reset and SQL path.
        with pytest.raises(AssertionError) as caught:
            assert_real_reporting(trainer)
        assert str(caught.value).splitlines()[0] == (
            "native reporting snapshot missing after reset"
        )
    assert_real_reporting(state.build(reporting=config))


def test_fresh_imports_remain_reporting_and_framework_lazy():
    repo = Path(__file__).resolve().parents[1]
    code = (
        "import builtins, sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        f"frameworks = {sorted(FRAMEWORKS)!r}\n"
        "original = builtins.__import__\n"
        "attempted = []\n"
        "def guarded(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    names = {name} | {name + '.' + part for part in (fromlist or ())}\n"
        "    if names & {'train.sql_reporting', 'ptc.sql_qa'} or name.split('.')[0] in frameworks:\n"
        "        attempted.append(name)\n"
        "        raise AssertionError('optional module import: ' + name)\n"
        "    return original(name, globals, locals, fromlist, level)\n"
        "builtins.__import__ = guarded\n"
        "from train import native_training, sql_training_run\n"
        "assert attempted == []\n"
        "assert not {'train.sql_reporting', 'ptc.sql_qa'} & set(sys.modules)\n"
        "assert not set(frameworks) & {name.split('.')[0] for name in sys.modules}\n"
        "print('LAZY_NATIVE_REPORTING_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True, text=True, timeout=12,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LAZY_NATIVE_REPORTING_OK"
