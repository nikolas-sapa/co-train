"""Original SDK identity and fail-closed composition, no model/provider calls."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.harnesses.utils import compaction, core
from verifiers.v1.runtimes.subprocess import SubprocessRuntime
from verifiers.v1.task import Task, TaskData, WireTaskData
from verifiers.v1.utils.loaders import harness_class

from bench.bird_bash_live import (
    bind_bash_sql_leaf, public_bash_prompt, require_production_bash_runtime,
)
from bench.test_bird_sql_worker_controller_integration import rig
from ptc.sql_owned_bash import BashSqlError
from ptc.test_sql_owned_bash import inputs


def test_original_loader_not_a_product_impostor():
    assert harness_class("bash") is BashHarness
    assert BashHarness.launch.__module__ == "verifiers.v1.harnesses.bash.harness"


def test_original_dispatch_preserves_full_command(monkeypatch):
    commands = []
    command = 'for n in 1 2; do printf "%s\\n" "$n"; done | sort -r'
    call = SimpleNamespace(id="one", function=SimpleNamespace(
        name="bash", arguments=json.dumps({"command": command})))
    messages = iter((
        SimpleNamespace(tool_calls=[call], model_dump=lambda **kw: {"role": "assistant"}),
        SimpleNamespace(tool_calls=[], model_dump=lambda **kw: {"role": "assistant"}),
    ))
    class SyntheticCompactor:
        async def complete(self, history):
            return SimpleNamespace(choices=[SimpleNamespace(message=next(messages))]), history

        def reached(self, completion, tokens):
            return False

    # The real bundle supplies these globals from the preceding utils module.
    monkeypatch.setattr(core, "bound_tool_message", compaction.bound_tool_message, raising=False)
    monkeypatch.setattr(core, "estimated_tokens", compaction.estimated_tokens, raising=False)
    monkeypatch.setattr(core, "run_bash", lambda value: commands.append(value) or "synthetic")
    history = []
    asyncio.run(core.run_chat_loop(
        SimpleNamespace(tool_interception_url="", bash=True, edit=True, search=False),
        SyntheticCompactor(), history, {}, {}, None))
    assert commands == [command]
    assert history[1]["content"] == "synthetic"


def test_question_schema_only_zero_private_canaries():
    prompt = public_bash_prompt("PUBLIC_QUESTION", "CREATE TABLE public_schema(n);")
    assert "PUBLIC_QUESTION" in prompt and "public_schema" in prompt
    assert all(secret not in prompt for secret in (
        "GOLD_CANARY", "EVIDENCE_CANARY", "/private/canary.sqlite"))


@pytest.mark.parametrize("runtime", [None, object(), SubprocessRuntime])
def test_no_unqualified_runtime_or_metadata_proof(runtime):
    with pytest.raises(BashSqlError, match="qualified full-shell"):
        require_production_bash_runtime(runtime)


def test_binding_reuses_original_task_harness_and_score(rig):
    values = inputs(rig)
    task = values["task"]
    leaf = bind_bash_sql_leaf(**values)
    assert leaf._task is task
    assert leaf._harness is values["harness"]
    assert type(leaf._harness) is BashHarness
    assert task.score.__func__ is Task.score
    asyncio.run(leaf.aclose())
    assert rig.log() == []


@pytest.mark.parametrize("kind", ["leak", "extra", "skills"])
def test_public_impostor_or_drift_zero_actions(rig, kind):
    values = inputs(rig)
    if kind == "leak":
        values["task"].data = TaskData(name="toy", prompt="GOLD_CANARY")
    elif kind == "extra":
        values["task"].data = WireTaskData(
            **values["task"].data.model_dump(), private_gold="GOLD_CANARY")
    else:
        values["harness"] = BashHarness(BashHarnessConfig(
            id="bash", skills=["https://example.invalid/skill"]))
    with pytest.raises(BashSqlError):
        bind_bash_sql_leaf(**values)
    assert rig.log() == []
