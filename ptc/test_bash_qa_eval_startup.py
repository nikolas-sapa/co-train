"""Pre-base-constructor resource exclusion, using actual SDK plugin loading.

Class-admission cases refuse before even constructing the Taskset. The paired
task case uses only the ordinary temporary loopback framework listener, never
a runtime/provider. Poison hooks raise if reached, so no case can launch MCP.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import uuid

import pytest

from verifiers.v1 import env as env_mod
from verifiers.v1.configs.cli.eval import EvalConfig
from cotrain_bash_qa_env import run_bash_qa_eval

_SOURCE = '''
from typing import Literal
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset

__all__ = ["FixtureTaskset"]
calls = []

class SeedTask(Task):
    __SEED_HOOK__

class Config(TasksetConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"

class Ancestor(Taskset[SeedTask, Config]):
    def __init__(self, config):
        calls.append("taskset constructor")
        super().__init__(config)

    def load(self):
        calls.append("load")
        yield SeedTask(TaskData(prompt="unused"), self.config.task)

    __ANCESTOR_HOOK__

class FixtureTaskset(Ancestor):
    __TASKSET_HOOK__
'''

_HOOK = '''@classmethod
    def toolsets(cls, config):
        calls.append("__KIND__ declaration")
        raise ValueError("poison declaration reached before admission")'''
_STATEFUL = '''@classmethod
    def toolsets(cls, config):
        calls.append("stateful declaration")
        if calls.count("stateful declaration") == 1:
            return []
        raise ValueError("second declaration would start unsupported tools")'''
_SELECTOR = '''@classmethod
    def task_type(cls):
        calls.append("selector")
        return SeedTask'''


def _config(name, tmp_path):
    return EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": "cotrain_bash_qa_env",
            "taskset": {"id": name},
            "interception": {"type": "server"},
            "agent": {
                "harness": {
                    "id": "cotrain_bash_qa", "edit": False, "search": False,
                },
                "runtime": {"type": "subprocess"},
                "max_turns": 3, "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(tmp_path / "output"), "run": {"dir": "unused"},
    }))


@pytest.mark.parametrize(
    "kind", ["shared", "seed", "ancestor", "stateful", "selector"],
)
def test_pre_start_toolset_override_refuses_without_calling_declaration(
    monkeypatch, tmp_path, kind,
):
    name = "qa_eval_startup_" + uuid.uuid4().hex
    shared, seed, ancestor = "pass", "pass", "pass"
    if kind == "shared":
        shared = _HOOK.replace("__KIND__", "shared")
    elif kind == "seed":
        seed = _HOOK.replace("__KIND__", "seed")
    elif kind == "ancestor":
        ancestor = _HOOK.replace("__KIND__", "ancestor")
    elif kind == "stateful":
        shared = _STATEFUL
    else:
        shared = _SELECTOR
    source = (
        _SOURCE.replace("__PLUGIN__", name)
        .replace("__SEED_HOOK__", seed)
        .replace("__ANCESTOR_HOOK__", ancestor)
        .replace("__TASKSET_HOOK__", shared)
    )
    (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    config = _config(name, tmp_path)
    module = importlib.import_module(name)
    starts = []
    original_make = env_mod.make_interception

    def observe_start(*args, **kwargs):
        starts.append("interception")
        return original_make(*args, **kwargs)

    monkeypatch.setattr(env_mod, "make_interception", observe_start)
    error = None
    try:
        asyncio.run(asyncio.wait_for(run_bash_qa_eval(config), 20.0))
    except (ValueError, TypeError) as exc:
        error = exc
    assert error is not None, "pre-start toolset admission did not refuse"
    assert "pre-start toolset refusal" in str(error), (
        "pre-start toolset guard was reached too late"
    )
    assert module.calls == [], (
        f"pre-start toolset guard invoked unsupported plugin work: {module.calls}"
    )
    assert starts == [], "pre-start toolset guard allowed resource startup"
    assert not (tmp_path / "output").exists(), (
        "pre-start toolset refusal must precede SDK output work"
    )


def test_paired_task_cannot_reintroduce_toolset_declaration(monkeypatch, tmp_path):
    name = "qa_eval_paired_tools_" + uuid.uuid4().hex
    builder = '''def build_bash_qa_task(self, binding):
        calls.append("builder")
        return PairedTask(self.data, self.config, qa_binding=binding)'''
    source = (
        _SOURCE.replace("__PLUGIN__", name)
        .replace("__SEED_HOOK__", builder)
        .replace("__ANCESTOR_HOOK__", "pass")
        .replace("__TASKSET_HOOK__", "pass")
    )
    source += '''
from ptc.bash_qa import BashQaTaskMixin
class PairedTask(BashQaTaskMixin, SeedTask):
    @classmethod
    def toolsets(cls, config):
        calls.append("paired declaration")
        raise ValueError("poison paired declaration reached")
'''
    (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    config = _config(name, tmp_path)
    module = importlib.import_module(name)
    servers = []
    original_make = env_mod.make_interception

    def observe_start(*args, **kwargs):
        assert kwargs["requires_tunnel"] is False
        server = original_make(*args, **kwargs)
        servers.append(server)
        return server

    monkeypatch.setattr(env_mod, "make_interception", observe_start)
    episode, = asyncio.run(asyncio.wait_for(run_bash_qa_eval(config), 20.0))
    assert not episode.ok
    assert "pre-start toolset refusal" in str(episode.errors)
    assert episode.traces == []
    assert module.calls == ["taskset constructor", "load", "builder"]
    server, = servers
    assert server.sessions == server.state_sessions == {}
    row_files = list((tmp_path / "output").rglob("*.jsonl"))
    assert len(row_files) == 1
    row, = [json.loads(line) for line in row_files[0].read_text().splitlines()]
    assert not row["ok"] and row["traces"] == []
