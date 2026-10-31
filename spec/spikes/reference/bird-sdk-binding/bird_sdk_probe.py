"""Throwaway composition probe, NOT a production BIRD runner.

PROVES: actual SDK episodes can use task-local SQL channels and host scoring.
SHORTCUT: manual temporary harness assignment, hardcoded fixtures, sequential arms.
MISSING: retained-draw admission, paired denominator, production launch ownership,
shared enforced budgets, cancellation/failure qualification and campaign settings.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
from typing import Literal

import pytest
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset

from bench.score import execution_accuracy, extract_sql
from bench.task import SqlTask
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_arms import build_sql_arms, install_wrapper
from ptc.test_bash_qa_activation_integration import (
    ScriptedClient, _bash_call, _text_step,
)
from ptc.test_bash_qa_eval_integration import framework  # noqa: F401
from ptc.test_ptc_qa_activation_integration import _program_call

__all__ = ["BirdProbeEnv", "BirdProbeTaskset"]
PAIRS, SQL_TASKS, TASKS, TRACES, EVENTS = {}, {}, [], [], []
QUERY = "SELECT SUM(amount) AS total FROM entries"
ORACLE = "SELECT COALESCE(SUM(amount), 0) FROM entries"


class ProbeData(TaskData):
    arm: Literal["bash", "ptc"]


class BirdProbeTask(Task[ProbeData]):
    async def setup(self, trace, runtime):
        EVENTS.append(("setup", self))
        await super().setup(trace, runtime)
        if self.data.arm == "bash":
            self.bindir = Path(runtime.workdir) / "bird-probe-sql"
            self.had_path = "PATH" in runtime.env
            self.old_path = runtime.env.get("PATH")
            install_wrapper(self.bindir, SQL_TASKS[self.data.name].db_path)
            effective = self.old_path if self.had_path else os.environ.get("PATH", os.defpath)
            runtime.env["PATH"] = f"{self.bindir}{os.pathsep}{effective}"

    async def finalize(self, trace, runtime):
        EVENTS.append(("finalize", self))
        try:
            await super().finalize(trace, runtime)
        finally:
            if self.data.arm == "bash" and hasattr(self, "bindir"):
                try:
                    if self.had_path:
                        runtime.env["PATH"] = self.old_path
                    else:
                        runtime.env.pop("PATH", None)
                finally:
                    if self.bindir.exists():
                        shutil.rmtree(self.bindir)

    async def score(self, trace, runtime=None):
        EVENTS.append(("score", self))
        result = execution_accuracy(
            extract_sql(trace.last_reply or ""), SQL_TASKS[self.data.name],
            timeout_s=2.0, max_rows=100, compare="set",
        )
        assert result.valid
        trace.record_reward("execution_accuracy", result.score)
        trace.info["bird_probe"] = {"status": result.status, "valid": result.valid}


class ProbeTasksetConfig(TasksetConfig):
    id: Literal["bird_sdk_probe"] = "bird_sdk_probe"
    arm: Literal["bash", "ptc"]


class BirdProbeTaskset(Taskset[BirdProbeTask, ProbeTasksetConfig]):
    def load(self):
        for name, pair in PAIRS.items():
            task = BirdProbeTask(
                ProbeData(name=name, prompt=pair.prompt(self.config.arm), arm=self.config.arm),
                self.config.task,
            )
            TASKS.append(task)
            yield task


class ProbeEnvConfig(SingleAgentEnvConfig):
    id: Literal["bird_sdk_probe"] = "bird_sdk_probe"


class BirdProbeEnv(Env[ProbeEnvConfig]):
    async def run(self, task, agents):
        original = agents.agent.harness
        try:
            if task.data.arm == "ptc":
                # SHORTCUT: ordinary SQL harness, NOT the report-only QA runner.
                agents.agent.harness = PTCHarness(
                    PTCHarnessConfig(id="ptc.harness", max_turns=4, program_timeout=2.0),
                    catalog=PAIRS[task.data.name].catalog(),
                )
            TRACES.append(await agents.agent.run(task))
        finally:
            agents.agent.harness = original


def test_real_sdk_sql_channels(framework, monkeypatch):
    state = framework
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    # Ensure the dynamically loaded plugin and pytest share the same fixture state.
    module = importlib.import_module("bird_sdk_probe")
    assert module.PAIRS is PAIRS
    PAIRS.clear()
    SQL_TASKS.clear()
    TASKS.clear()
    TRACES.clear()
    EVENTS.clear()
    db = state.root / "synthetic.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE entries(amount INTEGER)")
        conn.executemany("INSERT INTO entries VALUES (?)", [(19,), (23,)])
    task = SqlTask(
        name="fixture-sum", question="What is the total amount?", evidence="",
        gold_sql=ORACLE, db_id="synthetic", db_path=str(db),
        tier="simple", tier_source="annotated", shape="aggregate",
        coarse_shape="aggregate", source="fixture",
    )
    SQL_TASKS[task.name] = task
    PAIRS[task.name] = build_sql_arms(task)
    for arm in ("bash", "ptc"):
        config = EvalConfig.model_validate_json(json.dumps({
            "model": "fixture-model",
            "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
            "env": {
                "id": "bird_sdk_probe",
                "taskset": {"id": "bird_sdk_probe", "arm": arm},
                "interception": {"type": "server"},
                "agent": {
                    "harness": {"id": "bash", "edit": False, "search": False},
                    "runtime": {"type": "subprocess"}, "max_turns": 4,
                    "timeout": {"setup": 5.0, "rollout": 15.0, "finalize": 5.0, "scoring": 5.0},
                    "retries": {"max_retries": 0},
                },
                "retries": {"max_retries": 0},
            },
            "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
            "push": False, "resume": False, "clean": False, "rich": None,
            "output_dir": str(state.root / arm), "run": {"dir": "run"},
        }))
        action = (
            _bash_call("execute_sql " + shlex.quote(QUERY))
            if arm == "bash" else _program_call(f"print(execute_sql(query={QUERY!r}))")
        )
        policy = ScriptedClient([action, _text_step(f"```sql\n{QUERY}\n```")])
        state.config, state.policy = config, policy
        episodes = asyncio.run(asyncio.wait_for(run_eval(config), 20.0))
        assert len(episodes) == 1
        assert episodes[0].ok and len(episodes[0].traces) == 1
        assert episodes[0].traces[0] is TRACES[-1] and TRACES[-1].ok
        assert TRACES[-1].task.data is TASKS[-1].data
        assert TRACES[-1].reward == 1.0
        assert policy.calls == 2, "actual reactive dispatch count"
        assert "42" in str(policy.bodies[1]["messages"][-1]), "SQL result reached next request"
        assert ORACLE not in json.dumps(policy.bodies), "exact oracle text excluded from every request"
        assert len(policy.bodies[0]["tools"]) == 1, "one model-facing tool"
        files = list(Path(config.output_dir).rglob("*.jsonl"))
        assert len(files) == 1 and len(files[0].read_text().splitlines()) == 1
        row = json.loads(files[0].read_text())
        assert row["ok"] and row["traces"][0]["ok"]
        assert row["task"]["data"]["name"] == task.name
        assert row["task"]["data"]["arm"] == arm
        assert row["task"]["hash"] == row["traces"][0]["task"]["hash"] == TASKS[-1].hash
        reward = row["traces"][0]["rewards"]["execution_accuracy"]
        assert reward["score"] == reward["weight"] == 1.0
        assert row["traces"][0]["info"]["bird_probe"] == {"status": "match", "valid": True}
    assert len(TRACES) == len(TASKS) == 2
    for task in TASKS:
        assert [kind for kind, receiver in EVENTS if receiver is task] == [
            "setup", "finalize", "score",
        ], "SDK invoked each original Task hook exactly once"
    assert [trace.info["bird_probe"] for trace in TRACES] == [
        {"status": "match", "valid": True},
        {"status": "match", "valid": True},
    ]
