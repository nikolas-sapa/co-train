"""Actual SDK JSON/eval/writer composition with a fixture-only SQL process.

Not native-profile activation, a Docker-controller fix, or arbitrary callback
containment. The reused SDK fixture's pipe compensation remains fixture-only.
Only the child connection's actual SQLite VM callback emits the progress byte.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.cli.eval import EvalConfig

from bench.task import SqlTask
from ptc.runtime import Catalog
from ptc.sql_arms import sql_catalog
from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
from ptc.test_bash_qa_eval_integration import framework, _rows  # noqa: F401
from ptc.test_ptc_qa_activation_integration import _program_call

_ID = "owned_runner_fixture"
_REPO = Path(__file__).resolve().parents[1]
QUERY = "SELECT SUM(amount) AS total FROM entries"
CODE = f"rows = execute_sql(query={QUERY!r})\nprint(rows[0]['total'] + 0)"
SLOW = (
    "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL "
    "SELECT x+1 FROM n WHERE x<1000000000) SELECT COUNT(*) FROM n"
)

# Runs once for each actual model action, not a replay in the host. The
# connection wrapper is an observer seam ONLY in this fixture child.
_CHILD = r'''
import json, os, sys
from ptc.runtime import run
from ptc import sql_arms
payload = json.loads(sys.stdin.buffer.read())
marker = int(sys.argv[1])
original_connect = sql_arms.connect_readonly
def observed_connect(path):
    connection = original_connect(path)
    sent = False
    def vm_progress():
        nonlocal sent
        if not sent:
            os.write(marker, b"V")
            sent = True
        return 0
    connection.set_progress_handler(vm_progress, 1000)
    return connection
sql_arms.connect_readonly = observed_connect
printed = []
def observe(*parts, sep=" ", end="\n"):
    printed.append(sep.join(str(part) for part in parts))
catalog = sql_arms.sql_catalog(payload["db"], max_rows=100, observe=observe)
run(payload["code"], catalog, payload["timeout"])
sys.stdout.write(json.dumps({"observation": "\n".join(printed)}))
'''


class FixtureProcessRunner:
    """Own spawn, IO and group handles even when run_program is cancelled."""
    def __init__(self, root, db, *, hold_close=False):
        self.root, self.db = root, db
        self.hold_close = hold_close
        self.progress = asyncio.Event()
        self.closing = asyncio.Event()
        self.release = asyncio.Event()
        self.completed = False
        self.closed = 0
        self.calls, self.work = [], []
        self.snapshot = None
        self.cleanup_task = None

    async def _materialize(self, item):
        if item.process is None:
            try:
                item.process = await asyncio.shield(item.spawn)
            except Exception:
                for name in ("read_fd", "write_fd"):
                    descriptor = getattr(item, name)
                    if descriptor is not None:
                        os.close(descriptor)
                        setattr(item, name, None)
                raise
        if item.io is None:
            os.close(item.write_fd)
            item.write_fd = None
            loop = asyncio.get_running_loop()

            def readable():
                try:
                    value = os.read(item.read_fd, 32)
                except BlockingIOError:
                    return
                if b"V" in value:
                    self.progress.set()
                if not value:
                    loop.remove_reader(item.read_fd)

            loop.add_reader(item.read_fd, readable)
            item.io = asyncio.create_task(
                item.process.communicate(item.payload)
            )
        return item.process

    async def run_program(self, code, *, timeout):
        self.calls.append((code, timeout))
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        item = SimpleNamespace(
            read_fd=read_fd, write_fd=write_fd, process=None, io=None,
            payload=json.dumps({
                "code": code, "timeout": timeout, "db": str(self.db),
            }).encode(),
        )
        # Store the spawn task before the first await. No cancelled spawn or
        # communicate future is discarded; close materializes and reaps both.
        item.spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, "-I", "-B", "-c",
            f"import sys; sys.path.insert(0, {str(_REPO)!r})\n" + _CHILD,
            str(write_fd), pass_fds=(write_fd,), start_new_session=True,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=self.root,
            env={"PATH": os.defpath},
        ))
        self.work.append(item)
        process = await self._materialize(item)
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(item.io), timeout=timeout,
        )
        if process.returncode != 0:
            raise RuntimeError(f"fixture child failed: {stderr.decode()}")
        return json.loads(stdout)["observation"]

    async def _cleanup(self):
        for item in self.work:
            process = await self._materialize(item)
            # Unconditional owned group kill, including a group whose leader
            # already exited. This fixture never delegates cleanup to the SDK.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for item in self.work:
            try:
                await asyncio.wait_for(asyncio.shield(item.io), 2.0)
                await asyncio.wait_for(item.process.wait(), 2.0)
            finally:
                asyncio.get_running_loop().remove_reader(item.read_fd)
                os.close(item.read_fd)
        ps = await asyncio.create_subprocess_exec(
            "/bin/ps", "-axo", "pid=,pgid=,stat=",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        ps_io = asyncio.create_task(ps.communicate())
        try:
            output, error = await asyncio.wait_for(asyncio.shield(ps_io), 2.0)
        finally:
            if ps.returncode is None:
                ps.kill()
            await asyncio.wait_for(asyncio.shield(ps_io), 2.0)
        assert ps.returncode == 0, error.decode()
        groups = {item.process.pid for item in self.work}
        rows = [
            (int(pid), int(pgid), status)
            for pid, pgid, status in (
                line.split() for line in output.decode().splitlines()
            )
        ]
        self.snapshot = [row for row in rows if row[1] in groups]
        assert self.snapshot == [], "owned fixture worker group still live"
        assert all(item.process.returncode is not None for item in self.work)
        self.completed = True

    async def cleanup(self):
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup())
        await asyncio.shield(self.cleanup_task)

    async def aclose(self):
        self.closed += 1
        self.closing.set()
        if self.hold_close:
            await asyncio.wait_for(self.release.wait(), 2.0)
        await self.cleanup()


# An on-disk, test-only registered plugin. SDK loaders resolve these actual
# classes from JSON. No replacement module, Agent.run, writer or harness swap.
_PLUGIN = '''
from contextvars import ContextVar
from typing import Literal
from verifiers.v1.agent import Agents
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.harness import Harness
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from bench.score import execution_accuracy, extract_sql
from ptc.harness import PTCHarness, PTCHarnessConfig

__all__ = ["Config", "Adapter", "EnvConfig", "FixtureEnv",
           "SetConfig", "FixtureSet"]
ACTIVE = ContextVar("owned_runner_fixture", default=None)

class Config(PTCHarnessConfig):
    id: Literal["owned_runner_fixture"] = "owned_runner_fixture"

class Adapter(PTCHarness, Harness[Config]):
    def __init__(self, config):
        super().__init__(config)

    def record(self):
        record = ACTIVE.get()
        if record is None or not record.live or record.adapter is not self:
            raise RuntimeError("fixture adapter unbound")
        return record

    async def setup(self, runtime):
        record = self.record()
        assert not record.setup
        record.setup = True

    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        record = self.record()
        assert record.setup and not record.launched
        assert data is record.task.data and trace.task.data is data
        record.launched = True
        native = PTCHarness(
            PTCHarnessConfig(program_timeout=self.config.program_timeout),
            catalog=record.host.catalog,
            program_runner_factory=record.host.factory,
        )
        record.native = native
        return await native.launch(
            ctx, trace, runtime, endpoint, secret, mcp_urls, data)

class OriginalTask(Task):
    async def setup(self, trace, runtime):
        ACTIVE.get().host.events.append(("setup", self))
        await super().setup(trace, runtime)

    async def finalize(self, trace, runtime):
        ACTIVE.get().host.events.append(("finalize", self))
        await super().finalize(trace, runtime)

    async def score(self, trace, runtime=None):
        host = ACTIVE.get().host
        host.events.append(("score", self))
        prediction = extract_sql(trace.last_reply or "")
        result = execution_accuracy(
            prediction, host.sql_task, timeout_s=1.0, max_rows=100, compare="set")
        host.scores.append((self, prediction, result))
        assert result.valid
        trace.record_reward("execution_accuracy", result.score)

class SetConfig(TasksetConfig):
    id: Literal["owned_runner_fixture"] = "owned_runner_fixture"

class FixtureSet(Taskset[OriginalTask, SetConfig]):
    def load(self):
        host = ACTIVE.get()
        task = OriginalTask(
            TaskData(name="tiny-owned-fixture",
                     prompt="Table entries(amount INTEGER). Return total amount."),
            self.config.task)
        host.tasks.append(task)
        yield task

class EnvConfig(SingleAgentEnvConfig):
    id: Literal["owned_runner_fixture"] = "owned_runner_fixture"

class FixtureEnv(Env[EnvConfig]):
    async def run(self, task: Task, agents: Agents):
        from types import SimpleNamespace
        host = ACTIVE.get()
        adapter = agents.agent.harness
        assert type(adapter) is Adapter
        record = SimpleNamespace(
            host=host, adapter=adapter, task=task, live=True,
            setup=False, launched=False, native=None)
        host.records.append(record)
        token = ACTIVE.set(record)
        try:
            trace = await agents.agent.run(task)
            host.traces.append(trace)
            assert agents.agent.harness is adapter
        finally:
            record.live = False
            ACTIVE.reset(token)
'''


def _fixture(monkeypatch, state, *, hold_close=False):
    (state.root / f"{_ID}.py").write_text(_PLUGIN)
    monkeypatch.syspath_prepend(str(state.root))
    # The generated module may be cached between tests; its sole ContextVar
    # always receives a fresh launch-local host through a reset token.
    module = importlib.import_module(_ID)
    root = state.root / "private-owner"
    root.mkdir()
    db = root / "private.sqlite"
    nonce = "host_gold_" + os.urandom(12).hex()
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE entries(amount INTEGER)")
        connection.executemany("INSERT INTO entries VALUES (?)", [(19,), (23,)])
    host = SimpleNamespace(
        root=root, db=db, nonce=nonce, owners=[], tasks=[], traces=[],
        events=[], scores=[], records=[], bindings=[],
        catalog=sql_catalog(str(db), max_rows=100),
    )
    host.sql_task = SqlTask(
        name="tiny-owned-fixture", question="Total?", evidence="",
        gold_sql=f"SELECT COALESCE(SUM(amount), 0) FROM entries /* {nonce} */",
        db_id="tiny", db_path=str(db), tier="simple", tier_source="annotated",
        shape="aggregate", coarse_shape="aggregate", source="fixture",
    )

    def factory(data, catalog):
        assert data is host.tasks[-1].data
        assert isinstance(catalog, Catalog)
        assert catalog.names() == host.catalog.names() | {"print"}
        for name, callback in host.catalog.tools.items():
            assert catalog.tools[name] is callback
        assert callable(catalog.tools["print"])
        host.bindings.append((data, catalog))
        owner = FixtureProcessRunner(root, db, hold_close=hold_close)
        host.owners.append(owner)
        return owner

    host.factory = factory
    return module, host


def _config(state, label):
    config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": _ID, "taskset": {"id": _ID},
            "interception": {"type": "server"},
            "agent": {
                "harness": {"id": _ID, "program_timeout": 8.0},
                "runtime": {"type": "subprocess"}, "max_turns": 4,
                "timeout": {"setup": 3.0, "rollout": 10.0,
                            "finalize": 2.0, "scoring": 2.0},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(state.root / label), "run": {"dir": "run"},
    }))
    state.config = config
    return config


def _policy(code=CODE):
    return ScriptedClient([
        _program_call(code), _text_step(f"```sql\n{QUERY}\n```"),
    ])


def _assert_private(host, policy):
    wire = json.dumps(policy.bodies)
    assert host.nonce not in wire and host.sql_task.gold_sql not in wire
    assert str(host.db) not in wire
    assert host.tasks[-1].data.model_dump().get("db_path") is None
    assert "gold_sql" not in host.tasks[-1].data.model_dump()
    assert [tool["function"]["name"] for tool in policy.bodies[0]["tools"]] == [
        "run_program",
    ]


async def _eval(module, host, config):
    token = module.ACTIVE.set(host)
    try:
        return await run_eval(config)
    finally:
        module.ACTIVE.reset(token)


async def _cleanup(host):
    for owner in host.owners:
        owner.release.set()
        await owner.cleanup()


def _assert_success(host, policy, config, episode):
    assert episode.ok and len(episode.traces) == 1
    trace, = episode.traces
    assert trace.ok and trace.reward == 1.0
    task = host.tasks[-1]
    assert trace.task.data is task.data
    assert host.events[-3:] == [
        ("setup", task), ("finalize", task), ("score", task),
    ]
    assert host.scores[-1][0] is task
    assert host.scores[-1][1] == QUERY
    assert host.scores[-1][2].score == 1.0
    assert policy.calls == 2
    assert policy.bodies[1]["messages"][-1]["content"] == "42"
    owner = host.owners[-1]
    assert owner.calls == [(CODE, 8.0)]
    assert owner.closed == 1 and owner.completed and owner.snapshot == []
    assert all(item.process.returncode == 0 for item in owner.work)
    row, = _rows(config)
    assert row["ok"] and row["traces"][0]["ok"]
    assert row["task"]["hash"] == task.hash
    assert row["traces"][0]["rewards"]["execution_accuracy"]["score"] == 1.0
    _assert_private(host, policy)


def test_actual_eval_typed_sql_observation_ex1_and_jsonl(monkeypatch, framework):
    state = framework
    module, host = _fixture(monkeypatch, state)
    config = _config(state, "normal")
    state.policy = policy = _policy()

    async def case():
        try:
            episode, = await _eval(module, host, config)
            _assert_success(host, policy, config, episode)
            assert len(host.scores) == len(host.bindings) == 1
            assert host.records[0].live is False
            assert all(
                not host.root.is_relative_to(runtime.workdir)
                for runtime in state.runtimes
            )
        finally:
            await _cleanup(host)
    asyncio.run(asyncio.wait_for(case(), 15.0))


def test_actual_sql_vm_cancel_twice_reaps_before_return_then_fresh_ex1(
    monkeypatch, framework,
):
    state = framework
    module, host = _fixture(monkeypatch, state, hold_close=True)
    config = _config(state, "cancelled")
    slow_code = f"print(execute_sql(query={SLOW!r}))"
    state.policy = first = _policy(slow_code)

    async def case():
        caller = asyncio.create_task(_eval(module, host, config))
        try:
            # Factory/spawn alone is not progress evidence. Await the separate
            # pipe byte emitted only by the real VM after 1000 instructions.
            async def vm_started():
                while not host.owners:
                    await asyncio.sleep(0.005)
                await host.owners[0].progress.wait()
            await asyncio.wait_for(vm_started(), 5.0)
            owner = host.owners[0]
            assert not caller.done() and first.calls == 1
            caller.cancel()
            await asyncio.wait_for(owner.closing.wait(), 2.0)
            caller.cancel()
            await asyncio.wait({caller}, timeout=0.03)
            assert not caller.done(), "SDK caller escaped owner cleanup"
            owner.release.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            # All assertions happen before asyncio.run's shutdown/teardown.
            assert owner.completed and owner.closed == 1
            assert owner.snapshot == []
            assert len(owner.work) == 1
            assert owner.work[0].process.returncode is not None
            assert owner.calls == [(slow_code, 8.0)]
            assert first.calls == 1 and host.scores == []
            assert host.events == [("setup", host.tasks[0])]
            assert host.records[0].live is False
            _assert_private(host, first)

            retry = _config(state, "fresh")
            state.policy = second = _policy()
            # Release only this fixture gate; keep the same trusted factory.
            episode_task = asyncio.create_task(_eval(module, host, retry))
            try:
                async def release_fresh():
                    while len(host.owners) < 2:
                        await asyncio.sleep(0.005)
                    host.owners[1].release.set()
                await asyncio.wait_for(release_fresh(), 3.0)
                episode, = await episode_task
            finally:
                for item in host.owners:
                    item.release.set()
                if not episode_task.done():
                    episode_task.cancel()
                await asyncio.gather(episode_task, return_exceptions=True)
            _assert_success(host, second, retry, episode)
            assert len(host.scores) == 1
            assert len(host.bindings) == len(host.owners) == 2
            assert host.owners[0] is not host.owners[1]
        finally:
            for item in host.owners:
                item.release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
            await _cleanup(host)
    asyncio.run(asyncio.wait_for(case(), 15.0))
