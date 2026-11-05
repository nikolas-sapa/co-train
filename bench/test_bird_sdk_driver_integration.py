"""Test-only SQL plugins and retained driver, never a production SDK adapter.

Every integration uses the unchanged first-party _patch_runtimes ScratchRuntime
cache/foreground-transport-drain shim. This is NOT owned-runtime qualification.
Original loaders, Agent.run, run_eval, SQL actions, EX and writer remain real.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import functools
import ipaddress
import json
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import pytest
from verifiers.v1 import env as env_mod
from verifiers.v1.agent import Agent
from verifiers.v1.clients.client import Client
from verifiers.v1.configs.agent import AgentConfig, TimeoutConfig as AgentTimeout
from verifiers.v1.configs.cli.eval import EvalConfig, RunConfig
from verifiers.v1.configs.client import TrainClientConfig
from verifiers.v1.configs.env import EnvConfig, TimeoutConfig as EnvTimeout
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.dialects.chat import ChatDialect
from verifiers.v1.harness import Harness
from verifiers.v1.interception.server import InterceptionServerConfig
from verifiers.v1.runtimes import ProgramResult
from verifiers.v1.runtimes.subprocess import SubprocessConfig
from verifiers.v1.state import State
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.types import AssistantMessage, SamplingConfig, ToolCall
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.cli.output import write_episode

from bench import paired_bird as paired, prepare
from bench.score import execution_accuracy, extract_sql
from bench.test_bird_sdk_driver import _api
from bench.test_validated_draw_databases import _artifacts
from ptc.harness import PTCHarness, PTCHarnessConfig, TOOLS, _stream_message
from ptc.runtime import Catalog
from ptc.sql_arms import Budget, make_execute_sql, run_bash_sql, schema_text
from ptc.test_bash_qa_integration import _patch_runtimes, _response

if TYPE_CHECKING:
    from bench.bird_sdk_driver import SdkArmExpectation

PLUGIN = "cotrain_fixture_bird_sql"
POLICY = "scripted-sql-fixture-policy"
MODEL = "fixture-model"
_binding = ContextVar("bird_sql_fixture_binding", default=None)
_documents = ContextVar("bird_sql_fixture_documents", default=None)
BASH_TOOLS = [{"type": "function", "function": {
    "name": "bash", "description": "Fixture SQL shell exchange only",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string"}}, "required": ["query"],
        "additionalProperties": False}}}]


class FixtureHarnessConfig(PTCHarnessConfig):
    id: str = PLUGIN
    # Env eagerly constructs an UNUSED taskset-default harness config even
    # when the role pins its complete config. These inert placeholders cannot
    # pass bridge admission; every actually used field is explicitly supplied.
    arm: str = ""
    action_max_rows: int = 0
    query_timeout_s: float = 0
    instrument_identity: str = ""
    sampling_identity: str = ""
    policy_identity: str = ""


class FixtureEnvConfig(EnvConfig):
    agent: AgentConfig = AgentConfig()


class FixtureSqlTask(Task[TaskData, State]):
    async def score(self, trace, runtime=None):
        b = _binding.get()
        await b.checkpoint("scoring")
        private = b.private[self.data.name]
        result = execution_accuracy(
            extract_sql(trace.last_reply), private, timeout_s=b.draw.timeout_s,
            max_rows=b.draw.max_rows, compare=b.draw.comparison)
        b.receipts.append(b.api.SqlScoreReceipt(trace, result))
        if result.valid:
            trace.record_reward("execution_accuracy", result.score, 1.0)


class FixtureSqlTaskset(Taskset[FixtureSqlTask, TasksetConfig]):
    def load(self):
        b = _binding.get()
        for data in getattr(b.projection, b.arm):
            # No idx/key override and no private association in the TaskData.
            yield FixtureSqlTask(data, self.config.task)


class FixtureSqlEnv(Env[FixtureEnvConfig]):
    async def stop(self):
        # Test-plugin lifecycle controls, not SDK Env or writer patches.
        b = _binding.get()
        if getattr(b, "cleanup_entered", None) is not None:
            b.cleanup_entered.set()
            await b.cleanup_release.wait()
        if getattr(b, "cleanup_error", None) is not None:
            raise b.cleanup_error

    async def run(self, task, agents):
        b = _binding.get()
        agent = agents.agent
        assert isinstance(agent, Agent)
        assert agent.config == b.expected.effective_agent
        b.agents.append(agent)
        harness = agent.harness
        trace = await agent.run(task)  # original _EpisodeAgent -> original Agent
        assert agent.harness is harness
        b.traces.append(trace)
        # Last env hook, original evaluator still owns durable append_episode.
        await b.checkpoint("writer")


class FixtureSqlHarness(Harness[FixtureHarnessConfig]):
    NEEDS_CONTAINER = False
    APPENDS_SYSTEM_PROMPT = True
    SUPPORTS_MCP = False
    EXECUTES_CODE = True

    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        b = _binding.get()
        await b.checkpoint("rollout")
        private = b.private[data.name]
        cfg = self.config
        assert cfg.max_turns == b.instrument.budget.max_turns
        assert not mcp_urls
        assert cfg.action_max_rows == b.instrument.action_max_rows
        assert cfg.query_timeout_s == b.instrument.query_timeout_s
        assert cfg.program_timeout == b.instrument.budget.program_timeout
        if cfg.arm == "ptc":
            real_sql = make_execute_sql(private.db_path, max_rows=cfg.action_max_rows)

            def execute_sql(*, query):
                b.actions.append((data.name, query))
                return real_sql(query=query)

            delegate = PTCHarness(cfg, Catalog(tools={"execute_sql": execute_sql}))
            assert delegate.qa_factory is None
            b.delegates.append(delegate)
            # Task-bound catalog exists before real PTCHarness.launch. The
            # original minted Agent keeps its original loader-built harness.
            return await delegate.launch(ctx, trace, runtime, endpoint, secret,
                                         mcp_urls, data)
        messages = [{"role": "system", "content": "Fixture SQL shell exchange."},
                    {"role": "user", "content": data.prompt}]
        base = endpoint.rstrip("/")
        path = "/chat/completions" if base.endswith("/v1") else "/v1/chat/completions"
        async with httpx.AsyncClient(base_url=base, timeout=cfg.query_timeout_s,
                headers={"Authorization": f"Bearer {secret}"}) as http:
            for _ in range(cfg.max_turns):
                message = await _stream_message(http, path, {
                    "model": ctx.model, "messages": messages, "tools": BASH_TOOLS,
                    "tool_choice": "auto", "stream": True,
                    "stream_options": {"include_usage": True}})
                messages.append(message)
                calls = message.get("tool_calls") or []
                if not calls:
                    return ProgramResult(exit_code=0, stdout="", stderr="")
                assert len(calls) == 1
                call = calls[0]
                assert call["function"]["name"] == "bash"
                args = json.loads(call["function"]["arguments"])
                assert set(args) == {"query"}
                b.actions.append((data.name, args["query"]))
                result = await asyncio.to_thread(
                    run_bash_sql, private.db_path, args["query"],
                    bindir=b.scratch / data.name, max_rows=cfg.action_max_rows,
                    timeout=cfg.query_timeout_s, qa=None)
                assert result.returncode == 0
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "name": "bash", "content": result.observation})
        raise AssertionError("fixture model round bound reached")


@dataclass(frozen=True)
class FixtureSdkBinding:
    config: EvalConfig
    expected: SdkArmExpectation


class SqlPolicy(Client):
    """Real interception's client slot. All checks precede any response."""
    def __init__(self, b):
        self.b = b
        self.sessions = {}

    def validate(self, dialect, body, sampling):
        b = self.b
        name = "openai" if type(dialect) is ChatDialect else dialect
        allowed = {"model", "messages", "tools", "tool_choice", "stream",
                   "stream_options", "temperature", "top_p",
                   "max_tokens", "max_completion_tokens"}
        if name != "openai" or set(body) - allowed:
            raise b.api.BirdSdkBridgeError("fixture request envelope")
        if body.get("model") != b.expected.request_model:
            raise b.api.BirdSdkBridgeError("fixture request model")
        expected = b.expected.request_sampling.model_dump(exclude_none=True)
        actual = sampling.model_dump(exclude_none=True)
        knobs = {k: body[k] for k in ("temperature", "top_p", "max_tokens",
                                     "max_completion_tokens") if k in body}
        if "max_completion_tokens" in knobs:
            knobs["max_tokens"] = knobs.pop("max_completion_tokens")
        if actual != expected or knobs != expected:
            raise b.api.BirdSdkBridgeError("fixture request sampling")
        if (body.get("tools") != (TOOLS if b.arm == "ptc" else BASH_TOOLS)
                or body.get("tool_choice") != "auto"
                or body.get("stream") is not True
                or body.get("stream_options") != {"include_usage": True}):
            raise b.api.BirdSdkBridgeError("fixture tools/envelope")
        users = [m for m in body["messages"] if m["role"] == "user"]
        if len(users) != 1 or users[0]["content"] not in {
                d.prompt for d in getattr(b.projection, b.arm)}:
            raise b.api.BirdSdkBridgeError("fixture public prompt")
        text = json.dumps(body)
        if any(str(t.db_path) in text for t in b.draw.planned):
            raise b.api.BirdSdkBridgeError("private path reached model")

    async def get_response(self, dialect, body, sampling, session_id=None,
                           turn=None, headers=None):
        b = self.b
        try:
            self.validate(dialect, body, sampling)
        except Exception as exc:
            b.policy_rejections.append(exc)
            raise
        b.checked_requests.append((copy.deepcopy(body), sampling.model_copy(deep=True)))
        await b.checkpoint("interception")
        public = next(d for d in getattr(b.projection, b.arm)
                      if d.prompt == next(m["content"] for m in body["messages"]
                                          if m["role"] == "user"))
        count = self.sessions.get(session_id, 0)
        self.sessions[session_id] = count + 1
        if count == 0:
            assert all(t.gold_sql not in json.dumps(body) for t in b.draw.eligible)
            query = "SELECT COUNT(*) AS observed FROM sqlite_master WHERE type = 'table'"
            name = "run_program" if b.arm == "ptc" else "bash"
            arguments = ({"code": f"rows = execute_sql(query={query!r})\nprint(rows[0]['observed'])"}
                         if b.arm == "ptc" else {"query": query})
            encoded = json.dumps(arguments)
            call = ToolCall(id=f"sql-{session_id}", name=name, arguments=encoded)
            raw_call = {"id": call.id, "type": "function",
                        "function": {"name": name, "arguments": encoded}}
            response = _response(AssistantMessage(tool_calls=[call]),
                {"role": "assistant", "content": None, "tool_calls": [raw_call]},
                "tool_calls", b.responses + 1)
        else:
            assert count == 1
            tail = body["messages"][-1]
            assert tail["role"] == "tool"
            observation = str(tail["content"]).strip()
            # Parse ACTUAL SQL observation. No scripted/static result frames.
            if b.arm == "bash":
                lines = observation.splitlines()
                assert lines[0] == "observed"
                observed = int(lines[1])
            else:
                observed = int(observation)
            assert observed > 0
            b.observations.append((public.name, observed))
            index = b.projection.task_ids.index(public.name)
            final = b.private[public.name].gold_sql if index % 2 == 0 else "SELECT 'valid_wrong_sql'"
            text = f"```sql\n{final}\n```"
            response = _response(AssistantMessage(content=text),
                {"role": "assistant", "content": text}, "stop", b.responses + 1)
        b.responses += 1
        return response


class FixtureBirdSdkDriver:
    def __init__(self, *, plan, draw, instrument, policy_identity, bash, ptc, output_root):
        a = _api()
        documents = _documents.get()
        if documents is None or documents[0] is not draw or draw.fixture is not True:
            raise a.BirdSdkBridgeError("retained fixture documents required")
        paired._require_plan(plan)
        root, draw_path, supplement_path = documents[1:]
        self.reload_args = (root, draw_path, supplement_path)
        self.reload_kwargs = dict(expected_draw_sha256=draw.draw_sha256,
            expected_supplement_sha256=draw.supplement_sha256, fixture=True)
        fresh = prepare.load_validated_draw(*self.reload_args, **self.reload_kwargs)
        if fresh != draw or plan.draw != draw:
            raise a.BirdSdkBridgeError("draw/plan drift")
        self.a, self.plan, self.draw = a, plan, draw
        self.instrument, self.policy_identity = instrument, policy_identity
        self.bindings = {"bash": bash, "ptc": ptc}
        for arm, binding in self.bindings.items():
            h = binding.expected.effective_agent.harness
            if h.arm != arm or h.policy_identity != policy_identity:
                raise a.BirdSdkBridgeError("retained arm/policy declaration mismatch")
        self.output_root = output_root
        self.seals = {arm: a.admit_sdk_config(binding.config,
            expected=binding.expected, instrument=instrument, output_root=output_root)
            for arm, binding in self.bindings.items()}
        paths = [s.run_dir for s in self.seals.values()]
        if paths[0] == paths[1] or paths[0] in paths[1].parents or paths[1] in paths[0].parents:
            raise a.BirdSdkBridgeError("arm destinations overlap")
        self.schemas = tuple(schema_text(t.db_path) for t in draw.eligible)
        self.projection = a.project_sql_tasks(draw.eligible, schemas=self.schemas,
                                              action_max_rows=instrument.action_max_rows)
        self.consumed = set()
        self.evaluation_tasks = []
        self.states = {}

    def __call__(self, request):
        async def outcomes():
            if type(request) is not paired.ArmRequest or request.arm not in self.bindings:
                raise self.a.BirdSdkBridgeError("request type/arm")
            expected = paired.ArmRequest(self.plan.plan_id, request.arm,
                self.draw.eligible, self.instrument, self.policy_identity, 1)
            if (type(request.num_rollouts) is not int or request.num_rollouts != 1
                    or request != expected or request.arm in self.consumed):
                raise self.a.BirdSdkBridgeError("request drift/consumed")
            fresh = prepare.load_validated_draw(*self.reload_args, **self.reload_kwargs)
            if fresh != self.draw or self.plan.draw != self.draw:
                raise self.a.BirdSdkBridgeError("retained draw drift")
            self.a._check_projection(self.projection)
            if self.projection != self.a.project_sql_tasks(
                    self.draw.eligible, schemas=self.schemas,
                    action_max_rows=self.instrument.action_max_rows):
                raise self.a.BirdSdkBridgeError("projection drift")
            self.seals[request.arm]._check(fresh=True)
            self.consumed.add(request.arm)
            # A retained task owns all scopes; no token crosses a yield.
            # Capture actual owner exceptions INSIDE that owner task. Shield a
            # normal done signal, never a cancelled Task's synthesized exception.
            done = asyncio.get_running_loop().create_future()
            completion = {"result": None, "error": None}

            async def evaluate():
                try:
                    completion["result"] = await self._evaluate(request)
                except BaseException as exc:
                    completion["error"] = exc
                    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
                        raise  # Fatal process controls never become valid success.

            def finished(task):
                try:
                    task.result()
                except BaseException as exc:
                    # Prestart cancellation has no body/identity observation.
                    # Retain its real available message, without inventing one.
                    if completion["error"] is None:
                        completion["error"] = exc
                done.set_result(None)

            owner = asyncio.create_task(evaluate())
            owner.add_done_callback(finished)
            self.evaluation_tasks.append(owner)
            cancellation = None
            forwarded = False
            while True:
                try:
                    await asyncio.shield(done)
                    break
                except asyncio.CancelledError as exc:
                    if cancellation is None:
                        cancellation = exc
                    if not owner.done() and not forwarded:
                        owner.cancel()
                        forwarded = True
            if cancellation is not None:
                raise cancellation
            if completion["error"] is not None:
                raise completion["error"]
            for outcome in completion["result"]:
                yield outcome
        return outcomes()

    async def _evaluate(self, request):
        b = self.states[request.arm]
        token = _binding.set(b)
        b.scope_owner = asyncio.current_task()
        try:
            self.seals[request.arm]._check(fresh=True)
            b.evaluator_calls += 1
            episodes = await run_eval(self.bindings[request.arm].config)
            b.episodes = tuple(episodes)
            self.assert_cleanup(b)
            path = self.seals[request.arm].run_dir / "traces.jsonl"
            records = tuple(json.loads(line) for line in path.read_text().splitlines())
            assert len(records) == len(episodes)
            actual = {e.id: e for e in episodes}
            assert len(actual) == len(records)
            assert {row["id"] for row in records} == set(actual)
            for row in records:
                assert row == actual[row["id"]].model_dump(mode="json", exclude_none=True)
            return self.a.decode_sdk_episodes(tuple(episodes), request=request,
                projection=self.projection, scores=tuple(b.receipts),
                settings=self.seals[request.arm], task_type="FixtureSqlTask",
                run_dir=self.seals[request.arm].run_dir)
        finally:
            assert asyncio.current_task() is b.scope_owner
            _binding.reset(token)
            b.scope_closed = True

    @staticmethod
    def assert_cleanup(b):
        assert all(not s.sessions and not s.stack._exit_callbacks for s in b.servers)
        assert all(not r._owned_foreground and not r.env for r in b.runtimes)
        assert all(not s.runner.sites for s in b.servers if hasattr(s, "runner"))


def make_fixture_bird_sdk_driver(*, plan: paired.PairedBirdPlan,
                                 draw: prepare.ValidatedDraw,
                                 instrument: paired.Instrument, policy_identity: str,
                                 bash: FixtureSdkBinding, ptc: FixtureSdkBinding,
                                 output_root: Path) -> FixtureBirdSdkDriver:
    return FixtureBirdSdkDriver(plan=plan, draw=draw, instrument=instrument,
        policy_identity=policy_identity, bash=bash, ptc=ptc, output_root=output_root)


def _run(coro):
    async def checked():
        before = asyncio.all_tasks()
        try:
            return await asyncio.wait_for(coro, 20.0)
        finally:
            await asyncio.sleep(0)
            leaked = {t for t in asyncio.all_tasks() - before if not t.done()}
            assert not leaked, f"detached tasks before loop shutdown: {leaked}"
            assert _binding.get() is None
    return asyncio.run(checked())


def make_case(tmp_path, monkeypatch, a):
    root, dp, ds, sp, ss = _artifacts(tmp_path, excluded_only=True)
    plan = paired.prepare_paired_bird(root, dp, sp, expected_draw_sha256=ds,
        expected_supplement_sha256=ss, fixture=True)
    draw = plan.draw
    instrument = paired.Instrument("sql-sdk-fixture",
        Budget(max_turns=3, max_retries=0, retry_on=(),
               rollout_timeout=10.0, program_timeout=2.0),
        action_max_rows=17, query_timeout_s=3.0, sampling_identity="scripted-temp-zero")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / f"{PLUGIN}.py").write_text(
        "from bench.test_bird_sdk_driver_integration import "
        "FixtureSqlEnv, FixtureSqlTaskset, FixtureSqlHarness\n"
        "__all__ = ['FixtureSqlEnv', 'FixtureSqlTaskset', 'FixtureSqlHarness']\n")
    monkeypatch.syspath_prepend(str(plugins))
    monkeypatch.delitem(sys.modules, PLUGIN, raising=False)
    bindings = {}
    for arm in ("bash", "ptc"):
        run_client = TrainClientConfig(base_url="http://127.0.0.1:1",
            api_key_var="BIRD_FIXTURE_UNUSED_API_KEY", headers={"x-fixture": "run"})
        role_client = (None if arm == "bash" else run_client.model_copy(
            update={"headers": {"x-fixture": "role"}}))
        harness = FixtureHarnessConfig(arm=arm, max_turns=3, program_timeout=2.0,
            action_max_rows=17, query_timeout_s=3.0, instrument_identity=instrument.identity,
            sampling_identity=instrument.sampling_identity, policy_identity=POLICY,
            tool_timeout=2.0, skills=[], env={}, forward_env=[], mcp_header_env={})
        role = AgentConfig(harness=harness, runtime=SubprocessConfig(),
            model=None if arm == "bash" else MODEL, client=role_client,
            sampling=SamplingConfig(temperature=0.0), max_turns=3,
            timeout=AgentTimeout(setup=5, rollout=10, finalize=3, scoring=5),
            retries=RetryConfig(max_retries=0, include=[], exclude=[]))
        env = FixtureEnvConfig(id=PLUGIN, taskset=TasksetConfig(id=PLUGIN),
            agent=role, timeout=EnvTimeout(episode=15, finalize=3),
            retries=RetryConfig(max_retries=0, include=[], exclude=[]),
            max_concurrent_agents=1, interception=InterceptionServerConfig())
        config = EvalConfig(env=env, run=RunConfig(name=arm, dir=arm, attach=None),
            model=MODEL if arm == "bash" else "unused-run-model", client=run_client,
            sampling=SamplingConfig(temperature=0.2, top_p=0.8, max_tokens=128),
            num_tasks=None, num_rollouts=1, shuffle=False, max_concurrent=2,
            dry_run=False, clean=False, resume=False, push=False, rich=None,
            output_dir=output_root)
        # Independent literal expected resolution, NOT bridge resolver output.
        effective = role.model_copy(deep=True, update={
            "harness": harness.model_copy(deep=True), "model": MODEL,
            "client": (role_client or run_client).model_copy(deep=True),
            "sampling": SamplingConfig(temperature=0.0, top_p=0.8, max_tokens=128)})
        expectation = a.SdkArmExpectation(config.model_copy(deep=True), effective,
            MODEL, SamplingConfig(temperature=0.0, top_p=0.8, max_tokens=128))
        bindings[arm] = FixtureSdkBinding(config, expectation)
    token = _documents.set((draw, root, dp, sp))
    try:
        driver = make_fixture_bird_sdk_driver(plan=plan, draw=draw,
            instrument=instrument, policy_identity=POLICY,
            bash=bindings["bash"], ptc=bindings["ptc"], output_root=output_root)
    finally:
        _documents.reset(token)
    for arm in ("bash", "ptc"):
        async def checkpoint(stage, arm=arm):
            b = driver.states[arm]
            if b.failure_stage == stage:
                raise RuntimeError("intentional fixture lifecycle failure")
            if b.gate == stage:
                b.entered.set()
                try:
                    await b.release.wait()
                except asyncio.CancelledError:
                    b.cancellations += 1
                    raise
        scratch = tmp_path / f"scratch-{arm}"
        b = SimpleNamespace(api=a, arm=arm, draw=draw, projection=driver.projection,
            instrument=instrument, expected=bindings[arm].expected, scratch=scratch,
            private={t.name: t for t in draw.eligible}, agents=[], traces=[], receipts=[],
            episodes=(), servers=[], runtimes=[], actions=[], observations=[], delegates=[],
            checked_requests=[], policy_rejections=[], evaluator_calls=0, responses=0,
            gate=None, entered=None, release=None, cancellations=0, failure_stage=None,
            checkpoint=checkpoint, scope_closed=False)
        b.policy = SqlPolicy(b)
        driver.states[arm] = b
    runtimes = []
    _patch_runtimes(monkeypatch, tmp_path / "runtime-shim", runtimes)
    for b in driver.states.values():
        b.runtimes = runtimes
    original_make = env_mod.make_interception

    def interception(config, **kwargs):
        b = _binding.get()
        server = original_make(config, **kwargs)
        server.clients[b.expected.effective_agent.client.model_dump_json()] = b.policy
        b.servers.append(server)
        return server
    monkeypatch.setattr(env_mod, "make_interception", interception)
    denied = []
    connect, connect_ex, getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def check(address):
        if isinstance(address, tuple):
            host = address[0]
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "localhost"
            if not local:
                denied.append(address)
                raise AssertionError("external connection denied")

    def guarded_connect(sock, address):
        check(address)
        return connect(sock, address)

    def guarded_connect_ex(sock, address):
        check(address)
        return connect_ex(sock, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        check((host, 0))
        return getaddrinfo(host, *args, **kwargs)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

    class Case:
        def request(self, arm):
            return paired.ArmRequest(plan.plan_id, arm, draw.eligible, instrument, POLICY, 1)

        def consume(self, request):
            async def collect():
                rows = [row async for row in driver(request)]
                self.state = driver.states[request.arm]
                self.state.receipts = tuple(self.state.receipts)
                FixtureBirdSdkDriver.assert_cleanup(self.state)
                return tuple(rows)
            return _run(collect())

        def run_arm(self, arm):
            return self.consume(self.request(arm))

        def decode(self, *, episodes=None, scores=None, arm="bash", run_dir=None):
            b = driver.states[arm]
            return a.decode_sdk_episodes(
                self.state.episodes if episodes is None else episodes,
                request=self.request(arm), projection=driver.projection,
                scores=tuple(self.state.receipts) if scores is None else scores,
                settings=driver.seals[arm], task_type="FixtureSqlTask",
                run_dir=driver.seals[arm].run_dir if run_dir is None else run_dir)

        def assert_no_dispatch(self):
            assert not driver.evaluation_tasks
            assert all(b.evaluator_calls == b.responses == 0 for b in driver.states.values())
            assert not list(output_root.iterdir())
    c = Case()
    c.driver, c.plan, c.draw, c.instrument = driver, plan, draw, instrument
    c.bindings, c.output_root, c.schemas, c.denied = bindings, output_root, driver.schemas, denied
    c.runtimes, c.retained = runtimes, (draw, root, dp, sp)
    return c


def test_original_sdk_pair(tmp_path, monkeypatch):
    c = make_case(tmp_path, monkeypatch, _api())
    result = _run(paired.run_paired_bird(c.plan, run_arm=c.driver,
        instrument=c.instrument, policy_identity=POLICY, num_rollouts=1))
    assert result.status == "complete", result.diagnostics
    assert len(result.arm_a) == len(result.arm_b) == result.comparison.n == 7
    assert (result.disclosure.planned, result.disclosure.eligible, result.disclosure.excluded) == (8, 7, 1)
    assert result.fixture is True and result.measurement is False
    assert result.cost is result.usage is None
    assert len(c.driver.evaluation_tasks) == 2
    for arm in ("bash", "ptc"):
        b = c.driver.states[arm]
        assert b.evaluator_calls == 1
        assert len(b.agents) == len(b.traces) == len(b.episodes) == len(b.receipts) == 7
        assert len(b.actions) == len(b.observations) == 7
        assert b.responses == len(b.checked_requests) == 14
        assert b.scope_closed
        c.driver.assert_cleanup(b)
        rows = (c.driver.seals[arm].run_dir / "traces.jsonl").read_text().splitlines()
        assert len(rows) == 7
        outcomes = result.arm_a if arm == "bash" else result.arm_b
        assert all(o.output_ref.startswith(str(c.driver.seals[arm].run_dir / "traces.jsonl") + "#episode=")
                   for o in outcomes)
    assert not c.denied
    assert len(c.runtimes) == 14
    assert all(not r.env and not r._owned_foreground for r in c.runtimes)
    assert all(d.qa_factory is None and d.config.program_timeout == 2
               for d in c.driver.states["ptc"].delegates)


def test_single_use(tmp_path, monkeypatch):
    a = _api()
    c = make_case(tmp_path, monkeypatch, a)
    assert len(c.run_arm("bash")) == 7
    with pytest.raises(a.BirdSdkBridgeError):
        c.run_arm("bash")
    assert c.driver.states["bash"].evaluator_calls == 1
    assert len(c.driver.evaluation_tasks) == 1
    # A real SDK scoring failure writes original failure records, but produces
    # ZERO buffered outcomes and never restores the consumed arm.
    b = c.driver.states["ptc"]
    b.failure_stage = "scoring"
    async def failed_arm():
        seen = []
        with pytest.raises(a.BirdSdkBridgeError):
            async for outcome in c.driver(c.request("ptc")):
                seen.append(outcome)
        assert not seen
        assert b.scope_closed
        c.driver.assert_cleanup(b)
    _run(failed_arm())
    with pytest.raises(a.BirdSdkBridgeError):
        c.run_arm("ptc")
    assert b.evaluator_calls == 1 and len(c.driver.evaluation_tasks) == 2
    assert len((c.driver.seals["ptc"].run_dir / "traces.jsonl").read_text().splitlines()) == 7


@pytest.mark.parametrize("stage", ("interception", "rollout", "scoring", "writer", "writer_wait", "early_close"))
def test_cancel_cleanup_same_task(tmp_path, monkeypatch, stage):
    c = make_case(tmp_path, monkeypatch, _api())
    b = c.driver.states["bash"]

    async def scenario():
        iterator = c.driver(c.request("bash"))
        if stage == "early_close":
            first = await anext(iterator)
            assert first.completed and b.scope_closed and len(b.episodes) == 7
            await iterator.aclose()
        else:
            b.gate, b.entered, b.release = stage, asyncio.Event(), asyncio.Event()
            writer_release = threading.Event()
            writer_completed = []
            if stage == "writer_wait":
                loop = asyncio.get_running_loop()

                class WriterGateExecutor(ThreadPoolExecutor):
                    """Gate executor scheduling, NOT SDK writer/evaluator code.

                    Original append_episode is really awaiting its original
                    write_episode worker. The same unmodified worker executes
                    once after release; no fabricated/replacement writer.
                    """
                    def submit(self, fn, /, *args, **kwargs):
                        if isinstance(fn, functools.partial) and fn.args and fn.args[0] is write_episode:
                            original = fn

                            def gated():
                                loop.call_soon_threadsafe(b.entered.set)
                                assert writer_release.wait(5), "writer gate watchdog"
                                result = original()
                                writer_completed.append(True)
                                return result
                            fn = gated
                        return super().submit(fn, *args, **kwargs)

                loop.set_default_executor(WriterGateExecutor(max_workers=2))
            consumer = asyncio.create_task(anext(iterator))
            try:
                await b.entered.wait()
                consumer.cancel()
                await asyncio.sleep(0)
                consumer.cancel()  # repeat interruption while shield-joining
            finally:
                writer_release.set()
            with pytest.raises(asyncio.CancelledError):
                await consumer
            await iterator.aclose()
            if stage == "writer_wait":
                assert writer_completed
                path = c.driver.seals["bash"].run_dir / "traces.jsonl"
                assert path.exists() and path.read_text().strip()
                # Original partial durable records survive cancellation.
                assert all(json.loads(line)["id"] for line in path.read_text().splitlines())
            else:
                assert b.cancellations >= 1
            assert c.driver.evaluation_tasks[0].cancelling() == 1
        assert b.scope_closed
        assert all(t.done() for t in c.driver.evaluation_tasks)
        c.driver.assert_cleanup(b)
        assert all(not r.env and not r._owned_foreground for r in c.runtimes)
    _run(scenario())


def test_reporting_and_external_closed(tmp_path, monkeypatch):
    c = make_case(tmp_path, monkeypatch, _api())
    from ptc.sql_qa import QaChannel
    def forbidden(*args, **kwargs):
        raise AssertionError("QA factory/receipt reached reporting-off bridge")
    monkeypatch.setattr(QaChannel, "__init__", forbidden)
    assert len(c.run_arm("ptc")) == 7
    assert all(d.qa_factory is None for d in c.state.delegates)
    assert "report_defect" not in json.dumps([body for body, _ in c.state.checked_requests])
    assert not c.denied
    with socket.socket() as sock, pytest.raises(AssertionError, match="external connection denied"):
        sock.connect(("203.0.113.1", 443))
    assert c.denied == [("203.0.113.1", 443)]


def test_followup01_caller_cancel_precedes_cleanup_failure(tmp_path, monkeypatch):
    c = make_case(tmp_path, monkeypatch, _api())
    b = c.driver.states["bash"]
    async def scenario():
        b.gate, b.entered, b.release = "rollout", asyncio.Event(), asyncio.Event()
        b.cleanup_entered, b.cleanup_release = asyncio.Event(), asyncio.Event()
        b.cleanup_error = RuntimeError("actual fixture Env.stop cleanup failure")
        iterator = c.driver(c.request("bash"))
        consumer = asyncio.create_task(anext(iterator))
        await b.entered.wait()
        consumer.cancel("first-caller")
        await b.cleanup_entered.wait()
        # Observe the actual first exception caught at the driver boundary.
        first = iterator.ag_frame.f_locals["cancellation"]
        assert type(first) is asyncio.CancelledError and first.args == ("first-caller",)
        consumer.cancel("second-caller")
        await asyncio.sleep(0)
        consumer.cancel("third-caller")
        b.cleanup_release.set()
        try:
            with pytest.raises(asyncio.CancelledError) as observed:
                await consumer
            assert observed.value is first, "FIRST_CALLER_CANCEL_IDENTITY_REPLACED"
        finally:
            await iterator.aclose()
            assert b.scope_closed and all(t.done() for t in c.driver.evaluation_tasks)
            c.driver.assert_cleanup(b)
            assert all(not r.env and not r._owned_foreground for r in c.runtimes)
        assert c.driver.evaluation_tasks[0].cancelling() == 1
    _run(scenario())


def test_followup01_native_owner_cancel_identity(tmp_path, monkeypatch):
    c = make_case(tmp_path, monkeypatch, _api())
    b = c.driver.states["bash"]
    async def scenario():
        sentinel = asyncio.CancelledError("native-owner-Env.stop")
        b.cleanup_error = sentinel
        iterator = c.driver(c.request("bash"))
        try:
            with pytest.raises(asyncio.CancelledError) as observed:
                await anext(iterator)
            assert observed.value is sentinel, "NATIVE_OWNER_CANCEL_IDENTITY_REPLACED"
        finally:
            await iterator.aclose()
            assert b.scope_closed
            c.driver.assert_cleanup(b)
        with pytest.raises(_api().BirdSdkBridgeError):
            await anext(c.driver(c.request("bash")))
        assert b.evaluator_calls == 1 and all(t.done() for t in c.driver.evaluation_tasks)
    _run(scenario())


def _followup01_prestart_probe(path):
    """Honest owner-join unit control, no SDK trace or evaluator fabrication."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        c = make_case(Path(path), monkeypatch, _api())
        class CancelBeforeStart(list):
            def append(self, owner):
                super().append(owner)
                owner.cancel("prestart-owner-sentinel")
        c.driver.evaluation_tasks = CancelBeforeStart()
        async def scenario():
            iterator = c.driver(c.request("bash"))
            with pytest.raises(asyncio.CancelledError) as observed:
                await anext(iterator)
            assert observed.value.args == ("prestart-owner-sentinel",)
            await iterator.aclose()
            assert all(t.done() for t in c.driver.evaluation_tasks)
            assert all(b.evaluator_calls == b.responses == 0 for b in c.driver.states.values())
            assert not list(c.output_root.iterdir()) and not c.runtimes
        _run(scenario())


def test_followup01_prestart_owner_process_watchdog(tmp_path):
    """Self-contained external 10s PROCESS watchdog, not evidence-runner dependent."""
    import os
    import subprocess
    import tempfile
    # Child gets its own fixture directory; no Git/install/network/model commands.
    path = tmp_path / "child"
    path.mkdir()
    command = [sys.executable, "-B", "-c",
        "from bench.test_bird_sdk_driver_integration import _followup01_prestart_probe; "
        "import sys; _followup01_prestart_probe(sys.argv[1])", str(path)]
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                     "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "HF_HUB_OFFLINE": "1"},
                stdout=output, stderr=subprocess.STDOUT, timeout=10)
        except subprocess.TimeoutExpired:
            pytest.fail("PRESTART_OWNER_PROCESS_WATCHDOG_EXPIRED")
        output.seek(0)
        diagnostic = output.read().decode(errors="replace")
    assert result.returncode == 0, diagnostic


def test_output_destination_seal(tmp_path, monkeypatch):
    a = _api()
    c = make_case(tmp_path, monkeypatch, a)
    binding = c.bindings["ptc"]
    # Fresh destinations ensure these refusals exercise pair overlap itself,
    # not the independent existing-directory guard.
    for directory in ("bash", "bash/nested", "./bash"):
        config = binding.config.model_copy(deep=True)
        config.run.dir = directory
        token = _documents.set(c.retained)
        try:
            with pytest.raises(a.BirdSdkBridgeError):
                make_fixture_bird_sdk_driver(plan=c.plan, draw=c.draw,
                    instrument=c.instrument, policy_identity=POLICY, bash=c.bindings["bash"],
                    ptc=FixtureSdkBinding(config, dataclasses.replace(binding.expected,
                        config=config.model_copy(deep=True))), output_root=c.output_root)
        finally:
            _documents.reset(token)
    c.assert_no_dispatch()
    dest = c.driver.seals["bash"].run_dir
    dest.mkdir()
    (dest / "configs").mkdir()
    sentinel = {dest / "configs/eval.json": b"config sentinel\n",
                dest / "traces.jsonl": b"trace sentinel\n"}
    for path, content in sentinel.items():
        path.write_bytes(content)
    with pytest.raises(a.BirdSdkBridgeError):
        c.run_arm("bash")
    assert all(path.read_bytes() == content for path, content in sentinel.items())
    assert not c.driver.evaluation_tasks and c.driver.states["bash"].responses == 0
    for directory in ("../escape", str(tmp_path / "absolute"), "ptc/../../escape"):
        config = binding.config.model_copy(deep=True)
        config.run.dir = directory
        expected = dataclasses.replace(binding.expected, config=config.model_copy(deep=True))
        with pytest.raises(a.BirdSdkBridgeError):
            a.admit_sdk_config(config, expected=expected, instrument=c.instrument,
                               output_root=c.output_root)
    link = c.output_root / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    config = binding.config.model_copy(deep=True)
    config.run.dir = "alias/new"
    with pytest.raises(a.BirdSdkBridgeError):
        a.admit_sdk_config(config, expected=dataclasses.replace(binding.expected,
            config=config.model_copy(deep=True)), instrument=c.instrument, output_root=c.output_root)
    # Separate fresh arm succeeds. A copied matching original JSONL is NOT its destination.
    c.run_arm("ptc")
    copied = tmp_path / "copied"
    copied.mkdir()
    original = c.driver.seals["ptc"].run_dir / "traces.jsonl"
    (copied / "traces.jsonl").write_bytes(original.read_bytes())
    with pytest.raises(a.BirdSdkBridgeError):
        c.decode(arm="ptc", run_dir=copied)
    assert all(path.read_bytes() == content for path, content in sentinel.items())
