"""Mock-kernel lifecycle composition, NOT unchanged bundled chat-loop/native proof.

All checks are source-only until parent executes them. No actual-child gates here.
The production refusal is stubbed only in explicitly marked composition tests.
SQL command transport is synthetic; original broker/controller lifecycle remains.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from typing import get_type_hints

import httpx
import pytest
from verifiers.v1.agent import _EpisodeAgent
from verifiers.v1.clients import ModelContext
from verifiers.v1.clients.eval import EvalClient
from verifiers.v1.runtimes import ProgramResult
from verifiers.v1.runtimes.docker import DockerConfig
from verifiers.v1.task import Task
from verifiers.v1.types import Request, Response
from verifiers.v1.utils import loaders
from verifiers.v1.utils.decorators import discover_decorated

from bench import bird_bash_live as bash
from bench.bird_sdk_live import BirdBashTask, BirdSqlTask
from bench.score import ExResult
from bench.test_bird_sdk_live_product import (
    _case, _execute as _execute_ptc, _execution_fixture, restore_vf_run_id,
)
from bench.test_bird_sql_worker_controller_integration import rig
from ptc import bash_owned_runtime as owned
from ptc import bird_sql_worker_controller as sql_worker
from ptc import sql_owned_program
from ptc.bash_owned_runtime import BashActionController, BashOwnedDockerRuntime, BridgeLimits
from ptc.bird_sql_worker_controller import QueryWorkerController
from ptc.harness import PTCHarness, ProgramInfrastructureError
from ptc.sql_owned_bash import BashSqlBinding, BashSqlError
from ptc.sql_owned_score import OwnedSqlScorer
from ptc.test_bash_owned_runtime import response, tmp_path
from ptc.test_sql_owned_bash import inputs
from ptc import sql_isolation as core
from train import sql_live_reuse as live


def _composition_scratch(basetemp):
    if basetemp is None:
        raise owned.BashBridgeError("explicit ROOT/cases basetemp required")
    cases = Path(basetemp)
    if (not cases.is_absolute() or cases.name != "cases"
            or cases.resolve(strict=False) != cases):
        raise owned.BashBridgeError("canonical ROOT/cases basetemp required")
    root = cases.parent
    if len(os.fsencode(root)) > 48:
        raise owned.BashBridgeError("cold ROOT exceeds runtime socket budget")
    custody = owned._Directory(root)
    try:
        info = os.fstat(custody.fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise owned.BashBridgeError("owner-private 0700 cold ROOT required")
        custody.check()
    finally:
        custody.close()
    return root


@pytest.fixture
def mock_kernel_composition(tmp_path, rig, monkeypatch, request):
    case = _case(tmp_path)
    values = inputs(rig)
    row = live.SqlLiveInput(values["sql_task"], values["schema"], values["db_sha256"])
    case.plan = live.SqlLivePlan((row,))
    case.instrument = values["instrument"]
    config = case.config
    config.env.agent.harness = loaders.harness_config_type("bash")(
        id="bash", edit=False, search=False)
    config.env.agent.runtime = DockerConfig(image="offline-parent-owned", workdir="/app")
    case.policy = live.SqlLivePolicy(
        config.env.agent.model_copy(deep=True, update={
            "model": config.model, "client": config.client.model_copy(deep=True),
            "sampling": config.sampling.model_copy(deep=True)}),
        ModelContext(config.model, config.client.model_copy(deep=True),
                     config.sampling.model_copy(deep=True)))
    source = tmp_path / "approved-source"
    source.write_text("approved source\n")
    spec = bash.BashTaskResources(
        row, config.env.agent.runtime, values["broker_config"], values["db_size_bytes"],
        "/usr/local/bin/python3",
        _composition_scratch(request.config.getoption("basetemp")),
        "/usr/bin/docker", BridgeLimits(),
        ((str(source), hashlib.sha256(source.read_bytes()).hexdigest()),))
    state = SimpleNamespace(
        case=case, spec=spec, source=source, events=[], associations=[], requests=[],
        registrations=[], actions=[], scores=[], admissions=[], evals=[],
        starts=[], allocations=[], ready=[], reached=[],
        sql_containers={}, sql_events=[], sql_results=[],
        fault=None, mismatch=False, invalid=False, primary=None,
        cancel_stage=None, sql_started=None, sql_release=None,
        teardown_started=None, teardown_release=None, close_started=None,
        close_release=None, handler=None)
    real_eval = live.run_eval
    real_register = BashActionController.register_response
    real_before, real_after = BashSqlBinding.before_action, BashSqlBinding.after_action
    real_close = OwnedSqlScorer.aclose
    real_binding_close = BashSqlBinding.aclose
    real_start = BashOwnedDockerRuntime.start
    real_bind = bash._bind_resources
    real_stat = owned.os.stat
    real_sql_preflight = QueryWorkerController._preflight
    state.original_scorer_close = real_close

    def association():
        item = live._ACTIVE_ASSOCIATION.get()
        if item is not None and item not in state.associations:
            state.associations.append(item)
        return item

    async def counted_eval(config):
        state.evals.append(config)
        return await real_eval(config)

    async def start(runtime):
        state.starts.append(runtime)
        await real_start(runtime)
        state.ready.append((runtime.root, runtime.workspace, set(runtime.owned_containers)))

    def bind(item, spec):
        state.allocations.append(item)
        return real_bind(item, spec)

    def socket_stat(path, *args, **kwargs):
        if path == "/var/run/docker.sock":
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600)
        return real_stat(path, *args, **kwargs)

    def sql_preflight(controller, query):
        request, argv = real_sql_preflight(controller, query)
        assert query == "SELECT 1"
        assert request == b'{"format":"cotrain_sql_query","version":1,"query":"SELECT 1"}'
        assert controller not in state.sql_containers
        name, owner = controller.state.resource_name, controller.state.owner_id
        state.sql_containers[controller] = SimpleNamespace(
            ident=hashlib.sha256((name + owner).encode()).hexdigest(),
            name=name, owner=owner, request=request, create_argv=argv,
            exists=False, removed=False, status="created")
        return request, argv

    async def sql_command(controller, argv, *, deadline, capacity, request=None,
                          interrupt=False, start_effect=None):
        controller._check_identity()
        controller._remaining(deadline)
        if interrupt and controller._revoked:
            if start_effect is not None:
                controller._observe(start_effect, False)
            raise sql_worker._Revoked("query revoked")
        container = state.sql_containers[controller]
        assert (controller.state.resource_name, controller.state.owner_id) == (
            container.name, container.owner)
        assert type(argv) is tuple and argv[:5] == controller._argv()
        args = argv[5:]
        if args[:1] == ("start",):
            assert args == ("start", "--attach", "--interactive", container.ident)
            assert container.exists and not container.removed and container.status == "created"
            assert interrupt is True and start_effect is not None
            assert start_effect.kind is sql_worker.EffectKind.START
            assert start_effect in controller.state.pending
            assert type(request) is bytes and request == container.request
            assert request == b'{"format":"cotrain_sql_query","version":1,"query":"SELECT 1"}'
            assert capacity == controller._config.worker.limits.response_max_bytes
            controller._observe(start_effect, True)
            container.status = "exited"
            stdout = json.dumps({
                "format": "cotrain_sql_result", "version": 1, "status": "rows",
                "columns": ["1"], "rows": [[["integer", "1"]]], "message": None,
            }, separators=(",", ":")).encode()
            command = "start"
        else:
            assert request is None and interrupt is False and start_effect is None
            assert capacity == controller._config.control_stdout_max_bytes
            if args[:1] == ("create",):
                assert argv == container.create_argv
                assert not container.exists and not container.removed
                assert args[args.index("--name") + 1] == container.name
                assert args[args.index("--label") + 1] == (
                    f"{sql_worker._OWNER_LABEL}={container.owner}")
                assert container.request == (
                    b'{"format":"cotrain_sql_query","version":1,"query":"SELECT 1"}')
                container.exists = True
                stdout = (container.ident + "\n").encode("ascii")
                command = "create"
            elif args == ("inspect", "--type", "container", container.ident):
                assert container.exists and not container.removed
                stdout = json.dumps([{
                    "Id": container.ident, "Name": "/" + container.name,
                    "Config": {"Labels": {sql_worker._OWNER_LABEL: container.owner}},
                    "State": {"Status": container.status, "Running": False,
                              "OOMKilled": False, "ExitCode": 0},
                }]).encode()
                command = "inspect"
            elif args == ("rm", "--force", container.ident):
                assert container.exists and not container.removed
                container.exists, container.removed = False, True
                stdout = (container.ident + "\n").encode("ascii")
                command = "rm"
            elif args == ("container", "ls", "--all", "--no-trunc", "--filter",
                          f"label={sql_worker._OWNER_LABEL}={container.owner}",
                          "--format", "{{json .}}"):
                assert container.exists or container.removed
                stdout = (json.dumps({
                    "ID": container.ident, "Names": container.name,
                    "Labels": f"{sql_worker._OWNER_LABEL}={container.owner}",
                }).encode() + b"\n") if container.exists else b""
                command = "inventory"
            else:
                raise AssertionError("unexpected synthetic SQL command")
        assert len(stdout) <= capacity
        state.sql_events.append((controller, command, controller._revoked))
        return sql_worker._CommandOutput(stdout, b"", 0)

    async def engine_call(runtime, *argv, **kwargs):
        item = association()
        state.events.append(("engine", argv))
        issued = kwargs.get("_on_issued")
        if issued is not None:
            issued()
        if argv[:2] == ("image", "inspect"):
            return json.dumps([{"Id": "sha256:" + "a" * 64, "Config": {}}]).encode(), b"", 0
        if argv[:2] == ("volume", "inspect"):
            return json.dumps([{
                "Name": runtime.workspace, "Driver": "local", "Options": {
                    "type": "tmpfs", "device": "tmpfs",
                    "o": f"size={runtime.limits.workspace_bytes},"
                         f"nr_inodes={runtime.limits.workspace_inodes},uid=0,gid=0,mode=0700",
                }}]).encode(), b"", 0
        if argv[:2] == ("container", "inspect"):
            return json.dumps([{"Name": "/" + argv[-1], "Id": "b" * 64,
                                "State": {"Status": "exited", "ExitCode": 0}}]).encode(), b"", 0
        if argv[:2] == ("container", "rm") and state.fault == "container":
            state.reached.append(("fault", "container"))
            raise BashSqlError("mock-kernel container retirement unresolved")
        if argv[:2] == ("volume", "rm"):
            if state.teardown_started is not None:
                state.teardown_started.set()
                await state.teardown_release.wait()
            if state.fault == "volume":
                state.reached.append(("fault", "volume"))
                raise BashSqlError("mock-kernel volume retirement unresolved")
            state.events.append(("physical-retired",))
        if argv[:2] == ("start", "--attach"):
            if state.cancel_stage == "action":
                state.reached.append(("cancel", "action"))
                raise state.primary
            result = await item.bash_resources.binding.execute_sql(query="SELECT 1")
            state.sql_results.append(result)
        return b"", b"", 0

    def client_init(client, config):
        client.base_url, client.api_key, client.headers = config.base_url, "synthetic", {}
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))

    def upstream(request):
        state.requests.append(json.loads(request.content))
        if len(state.requests) == 1:
            delta = {"tool_calls": [
                {"index": index, "id": call_id, "type": "function",
                 "function": {"name": "bash", "arguments": '{"command":"printf same"}'}}
                for index, call_id in enumerate(("one", "two"))]}
            reason = "tool_calls"
        else:
            delta, reason = {"content": "SELECT 1"}, "stop"
        message = {"role": "assistant", **delta}
        if "tool_calls" in message:
            message["tool_calls"] = [
                {key: value for key, value in call.items() if key != "index"}
                for call in message["tool_calls"]]
        return httpx.Response(200, json={
            "id": f"mock-{len(state.requests)}", "object": "chat.completion",
            "created": 1, "model": case.config.model,
            "choices": [{"index": 0, "message": message, "finish_reason": reason}]})

    async def kernel_run(runtime, argv, env):
        item = association()
        assert runtime is item.runtime_view and "--bash" in argv
        assert "--edit" not in argv and "--search" not in argv
        endpoint = next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--base-url="))
        secret = next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--api-key="))
        messages = [{"role": "user", "content": item.task.data.prompt}]
        tools = [{"type": "function", "function": {
            "name": "bash", "parameters": {"type": "object", "properties": {
                "command": {"type": "string"}}, "required": ["command"]}}}]
        if state.handler is not None:
            await state.handler(item)
        async with httpx.AsyncClient() as client:
            result = await client.post(endpoint.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + secret},
                json={"model": case.config.model, "messages": messages, "tools": tools})
            result.raise_for_status()
            message = result.json()["choices"][0]["message"]
            messages.append(message)
            for call in message["tool_calls"]:
                await runtime.controller.dispatch(json.loads(call["function"]["arguments"])["command"])
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": "ok"})
            result = await client.post(endpoint.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + secret},
                json={"model": case.config.model, "messages": messages, "tools": tools})
            result.raise_for_status()
        return ProgramResult(0, "", "")

    def register(controller, original):
        state.registrations.extend(call.id for call in original.message.tool_calls or ())
        return real_register(controller, original)

    def before(binding, call_id):
        state.actions.append(("before", call_id))
        real_before(binding, call_id)

    def after(binding, call_id):
        real_after(binding, call_id)
        state.actions.append(("after", call_id))

    def admit(executor, *, db_path, db_sha256):
        state.admissions.append((executor, db_path, db_sha256))
        return core.ProgramDatabaseIdentity(db_path, db_sha256, 1, 1, 1, 1, 1, 1, 1, 1)

    async def score(scorer, sql):
        item = association()
        assert scorer is item.scorer and item.score_ready
        assert item.bash_resources.owner.stopped is item.runtime_view.stopped is False
        assert ("physical-retired",) in state.events
        state.scores.append(sql)
        state.events.append(("score",))
        if state.cancel_stage == "score":
            state.reached.append(("cancel", "score"))
            raise state.primary
        return ExResult(0.0 if state.mismatch or state.invalid else 1.0,
                        "gold_error" if state.invalid else "mismatch" if state.mismatch else "match",
                        not state.invalid)

    async def close_scorer(scorer):
        item = association()
        assert item.bash_resources.owner.stopped
        state.events.append(("stop-observed-after-agent",))
        if state.close_started is not None:
            state.close_started.set()
            await state.close_release.wait()
        await real_close(scorer)

    async def close_binding(binding):
        if state.sql_started is not None:
            state.sql_started.set()
            await state.sql_release.wait()
        if state.cancel_stage == "finalize":
            state.reached.append(("cancel", "finalize"))
            raise state.primary
        if state.fault == "binding":
            state.reached.append(("fault", "binding"))
            raise BashSqlError("mock-kernel binding retirement unresolved")
        await real_binding_close(binding)

    monkeypatch.setattr(live, "run_eval", counted_eval)
    monkeypatch.setattr(bash, "_bind_resources", bind)
    monkeypatch.setattr(BashOwnedDockerRuntime, "start", start)
    monkeypatch.setattr(owned, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(owned.os, "stat", socket_stat)
    monkeypatch.setattr(BashOwnedDockerRuntime, "engine_call", engine_call)
    monkeypatch.setattr(QueryWorkerController, "_preflight", sql_preflight)
    monkeypatch.setattr(QueryWorkerController, "_command", sql_command)
    monkeypatch.setattr(BashOwnedDockerRuntime, "run", kernel_run)
    monkeypatch.setattr(EvalClient, "__init__", client_init)
    monkeypatch.setattr(BashActionController, "register_response", register)
    monkeypatch.setattr(BashSqlBinding, "before_action", before)
    monkeypatch.setattr(BashSqlBinding, "after_action", after)
    monkeypatch.setattr(core.PilotExecutor, "admit_program", admit)
    monkeypatch.setattr(OwnedSqlScorer, "score_sql", score)
    monkeypatch.setattr(OwnedSqlScorer, "aclose", close_scorer)
    monkeypatch.setattr(BashSqlBinding, "aclose", close_binding)
    return state


def _mock_gate(monkeypatch):
    monkeypatch.setattr(bash, "require_production_bash_runtime", lambda runtime: None)


def _execute(state, **updates):
    case = state.case
    options = dict(executor=case.fixture.executor, instrument=case.instrument,
                   expected_policy=case.policy, allow_execution=True,
                   allow_model_requests=True, bash_resources=(state.spec,))
    options.update(updates)
    return live.run_sql_live(case.plan, case.config, **options)


def _run(state):
    return asyncio.run(asyncio.wait_for(_execute(state), 10))


def _assert_no_score(state):
    assert len(state.admissions) == len(state.scores) == 0
    assert all(item.receipt is None and item.result is None for item in state.associations)
    for item in state.associations:
        if item._controller is not None:
            _assert_control_closed(item._controller)
    assert live._ACTIVE_ASSOCIATION.get() is live._ACTIVE_SCOPE.get() is None


def _assert_started(state):
    assert len(state.starts) == len(state.allocations) == len(state.ready) == 1
    root, workspace, containers = state.ready[0]
    assert root.parent == state.spec.scratch and root.name.startswith("bb-")
    assert len(root.name) == 15
    assert len(os.fsencode(root / ("sql-" + "a" * 24) / "socket")) <= 100
    assert workspace and len(containers) == 1
    engine = [event[1] for event in state.events if event[0] == "engine"]
    assert any(argv[:2] == ("volume", "create") and workspace in argv for argv in engine)
    assert any(argv[0] == "create" and containers <= set(argv) for argv in engine)


def _assert_sql_transport_completed(state):
    assert len(state.sql_containers) == len(state.sql_results) == 2
    assert len({item.ident for item in state.sql_containers.values()}) == 2
    assert len({item.owner for item in state.sql_containers.values()}) == 2
    assert len({item.name for item in state.sql_containers.values()}) == 2
    assert len(state.sql_events) == 14
    for (controller, container), result in zip(
            state.sql_containers.items(), state.sql_results, strict=True):
        assert [(command, revoked) for owner, command, revoked in state.sql_events
                if owner is controller] == [
            ("create", False), ("inspect", False), ("start", False),
            ("inspect", False), ("inspect", True), ("rm", True), ("inventory", True)]
        assert container.removed and not container.exists and container.status == "exited"
        assert controller.state.phase == "CLOSED" and not controller.state.pending
        assert controller._revoked and not controller._local_uncertain
        assert controller._records == []
        assert controller._owner_task.done() and controller._cleanup_task.done()
        assert controller._cleanup_task.result() is None
        assert controller._owner_task.result() is controller._outcome
        assert controller._outcome.error is None and controller._outcome.value is result
        assert type(result) is sql_worker.QueryWorkerResult
        assert result.status == "rows" and result.columns == ("1",)
        assert result.rows == ((1,),) and type(result.rows[0][0]) is int
        assert result.message is None
    item, = state.associations
    binding = item.bash_resources.binding
    assert binding._close_task.done() and binding._close_task.result() is None
    broker = binding._owner
    assert broker.closed and broker.revoked and broker._failure is None
    assert broker._settled.done() and broker._settled.result() is None
    assert broker._collector_finished.done() and broker._collector_finished.result() is None
    assert broker._active is broker._execution is broker._retirement is None
    assert not broker._requests and all(task.done() for task in broker._owned_tasks())


def _assert_control_closed(controller):
    for capability in (controller.control, controller.sql):
        if capability is not None:
            assert capability.revoked
            assert not capability.handlers and not capability.writers
            assert not capability.unresolved_writers and not capability.owned_children
            if capability.server is not None:
                assert not capability.server.is_serving()
                assert all(sock.fileno() == -1 for sock in capability.server.sockets)


def test_bash_guard_precedes_canonical_eval_and_resources(mock_kernel_composition):
    state = mock_kernel_composition
    refused = False
    try:
        _run(state)
    except (BashSqlError, live.SqlLiveError):
        refused = True
    assert refused, "actual production guard-call loss must fail this unchanged test"
    assert len(state.evals) == len(state.events) == len(state.associations) == 0
    assert len(state.starts) == len(state.allocations) == len(state.requests) == 0
    assert len(state.registrations) == len(state.actions) == len(state.admissions) == 0


@pytest.mark.parametrize("arm", ["ptc", "bash"])
def test_exact_arm_interceptor_discovery(mock_kernel_composition, arm):
    state = mock_kernel_composition
    case = state.case
    if arm == "ptc":
        root = state.source.parent / "ptc-control"
        root.mkdir(mode=0o700)
        scope = _case(root).scope
    else:
        scope = live._Scope(case.plan, case.config, case.fixture.executor, case.instrument,
                            case.policy, None, bash_resources=(state.spec,))
    token = live._ACTIVE_SCOPE.set(scope)
    try:
        task, = loaders.load_taskset(scope.config.env.taskset)
        expected = BirdSqlTask if arm == "ptc" else BirdBashTask
        assert type(task) is expected
        inherited = discover_decorated(Task(task.data, task.config), "intercept")
        actual = discover_decorated(task, "intercept")
        inherited_functions = {hook.__func__ for hook in inherited}
        assert inherited_functions <= {hook.__func__ for hook in actual}
        added = [hook for hook in actual if hook.__func__ not in inherited_functions]
        if arm == "ptc":
            assert added == []
            assert not hasattr(task, "check_bash_request")
            assert not hasattr(task, "register_bash_response")
        else:
            assert {hook.__func__ for hook in added} == {
                BirdBashTask.check_bash_request, BirdBashTask.register_bash_response}
            assert sum(get_type_hints(hook).get("request") is Request for hook in added) == 1
            assert sum(get_type_hints(hook).get("response") is Response for hook in added) == 1
        assert task.setup.__func__ is BirdSqlTask.setup
        assert task.finalize.__func__ is BirdSqlTask.finalize
        assert task.execution_accuracy.__func__ is BirdSqlTask.execution_accuracy
    finally:
        live._ACTIVE_SCOPE.reset(token)


def test_ptc_rollout_preserves_original_task_data(tmp_path, monkeypatch):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path)
    real_launch, real_check = PTCHarness.launch, sql_owned_program._Binding.check
    launches, checks = [], []

    async def launch(harness, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        item = live._ACTIVE_ASSOCIATION.get()
        assert type(item.task) is BirdSqlTask
        assert data is item.task.data is trace.task.data
        launches.append(data)
        return await real_launch(harness, ctx, trace, runtime, endpoint, secret, mcp_urls, data)

    def check(binding, data, compiled, print_callback):
        assert data is binding.data
        copied = data.model_copy(deep=True)
        assert copied == data and copied is not data
        with pytest.raises(ProgramInfrastructureError, match="owned SQL binding changed"):
            real_check(binding, copied, compiled, print_callback)
        real_check(binding, data, compiled, print_callback)
        checks.append(data)

    monkeypatch.setattr(PTCHarness, "launch", launch)
    monkeypatch.setattr(sql_owned_program._Binding, "check", check)
    result = asyncio.run(asyncio.wait_for(_execute_ptc(case), 10))
    assert len(launches) == len(result.episodes) == len(result.receipts) == 1
    assert checks and all(data is launches[0] for data in checks)
    assert len(state.scores) == 1
    assert result.episodes[0].task.data is launches[0]


@pytest.mark.parametrize("arm,mutation", [
    ("ptc", "sibling"), ("ptc", "subclass"), ("ptc", "setup"),
    ("ptc", "finalize"), ("ptc", "execution_accuracy"),
    ("bash", "sibling"), ("bash", "subclass"), ("bash", "setup"),
    ("bash", "finalize"), ("bash", "execution_accuracy"),
    ("bash", "_bash_association"), ("bash", "check_bash_request"),
    ("bash", "register_bash_response"),
])
def test_exact_arm_class_and_method_authority(mock_kernel_composition, arm, mutation):
    state = mock_kernel_composition
    case = state.case
    if arm == "ptc":
        root = state.source.parent / "ptc-control"
        root.mkdir(mode=0o700)
        scope = _case(root).scope
    else:
        scope = live._Scope(case.plan, case.config, case.fixture.executor, case.instrument,
                            case.policy, None, bash_resources=(state.spec,))
    token = live._ACTIVE_SCOPE.set(scope)
    try:
        task, = loaders.load_taskset(scope.config.env.taskset)
        scope.check_task(task)
        if mutation in ("sibling", "subclass"):
            if mutation == "sibling":
                candidate_cls = BirdBashTask if arm == "ptc" else BirdSqlTask
            else:
                class Derived(type(task)):
                    pass
                candidate_cls = Derived
            candidate = candidate_cls(task.data, task.config)
            with pytest.raises(live.SqlLiveError, match="task identity differs"):
                scope.register(candidate)
            scope.tasks[task.data.name] = candidate
            with pytest.raises(live.SqlLiveError, match="task identity differs"):
                scope.check_task(candidate)
        else:
            original = getattr(task, mutation)

            async def replacement(self, *args):
                return None

            setattr(task, mutation, replacement.__get__(task))
            with pytest.raises(live.SqlLiveError, match="behavior differs|lifecycle method differs"):
                scope.check_task(task)
            setattr(task, mutation, original)
            scope.check_task(task)
        assert state.starts == state.allocations == state.events == []
    finally:
        live._ACTIVE_SCOPE.reset(token)


def test_composition_scratch_uses_explicit_cold_root(mock_kernel_composition, request):
    state = mock_kernel_composition
    cases = Path(request.config.getoption("basetemp"))
    assert state.spec.scratch == cases.parent
    assert len(os.fsencode(state.spec.scratch)) + 52 <= 100
    assert state.source.parent != state.spec.scratch
    absent_cases = cases.parent / "tmp" / "cases"
    assert absent_cases.parent.is_dir() and not absent_cases.exists()
    assert _composition_scratch(absent_cases) == absent_cases.parent
    assert not absent_cases.exists()
    with pytest.raises(owned.BashBridgeError, match="explicit ROOT/cases"):
        _composition_scratch(None)
    with pytest.raises(owned.BashBridgeError, match="canonical ROOT/cases"):
        _composition_scratch(state.source.parent)


def test_original_borrowed_view_shares_lifecycle(mock_kernel_composition, monkeypatch):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    result = _run(state)
    _assert_started(state)
    item, = state.associations
    owner, view = item.bash_resources.owner, item.runtime_view
    assert owner is not view and owner.__dict__ is view.__dict__
    assert owner.env is not view.env
    view.env["TASK_ONLY"] = "separate"
    assert "TASK_ONLY" not in owner.env
    fields = ("controller", "_policy_claimed", "_policy_deadline",
              "_teardown_task", "_teardown_deadline", "workspace")
    for field in fields:
        original = getattr(owner, field)
        replacement = object()
        try:
            setattr(view, field, replacement)
            assert getattr(owner, field) is replacement
            setattr(owner, field, original)
            assert getattr(view, field) is original
        finally:
            setattr(owner, field, original)
    assert len(result.receipts) == 1
    _assert_control_closed(item._controller)


def test_original_shared_sdk_lifecycle(mock_kernel_composition, monkeypatch):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    result = _run(state)
    assert len(state.evals) == len(result.episodes) == len(result.receipts) == 1
    _assert_started(state)
    _assert_sql_transport_completed(state)
    item, = state.associations
    episode, = result.episodes
    trace, = episode.traces
    assert item.task is item.scope.tasks[item.task.data.name]
    assert trace is item.trace is result.receipts[0].trace
    assert BirdSqlTask.score is Task.score
    assert set(trace.rewards) == {"execution_accuracy"}
    assert trace.rewards["execution_accuracy"].score == 1
    assert len(state.admissions) == len(state.scores) == 1
    assert state.events.index(("physical-retired",)) < state.events.index(("score",))
    assert state.events.index(("score",)) < state.events.index(("stop-observed-after-agent",))
    assert item.bash_resources.owner.stopped
    _assert_control_closed(item._controller)
    assert item.retention is item.capture is None and result.captures == ()
    assert live._ACTIVE_ASSOCIATION.get() is live._ACTIVE_SCOPE.get() is None


def test_two_original_bash_calls_one_reward(mock_kernel_composition, monkeypatch):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    result = _run(state)
    _assert_sql_transport_completed(state)
    assert len(state.requests) == 2
    assert state.registrations == ["one", "two"]
    assert state.actions == [
        ("before", "one"), ("after", "one"), ("before", "two"), ("after", "two")]
    assert len(state.scores) == len(result.receipts) == 1
    item, = state.associations
    before = list(state.actions)
    with pytest.raises(BashSqlError):
        asyncio.run(item.bash_resources.owner.controller.dispatch("printf same"))
    assert state.actions == before and len(state.scores) == 1
    _assert_control_closed(item._controller)


@pytest.mark.parametrize("context", ["absent", "association", "scope", "Trace"])
def test_request_response_handler_context(mock_kernel_composition, monkeypatch, context):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)

    async def handler(item):
        state.reached.append(("handler", context))
        a = live._ACTIVE_ASSOCIATION.set(None if context != "association" else object())
        s = live._ACTIVE_SCOPE.set(item.scope if context != "scope" else object())
        trace = copy.copy(item.trace) if context == "Trace" else item.trace
        count = len(state.registrations)
        actions = list(state.actions)
        try:
            if context == "absent":
                assert await item.task.check_bash_request(Request(messages=[]), trace) is None
                # No synthetic request may register another call.
                assert len(state.registrations) == count
                assert await item.task.register_bash_response(response(), trace) is None
            else:
                for hook, value in (
                        (item.task.check_bash_request, Request(messages=[])),
                        (item.task.register_bash_response, response(("foreign", "printf same")))):
                    with pytest.raises(live.SqlLiveError):
                        await hook(value, trace)
                assert len(state.registrations) == count
                assert state.actions == actions
                raise live.SqlLiveError("foreign mock-kernel handler context")
        finally:
            live._ACTIVE_SCOPE.reset(s)
            live._ACTIVE_ASSOCIATION.reset(a)

    state.handler = handler
    if context == "absent":
        _run(state)
        item, = state.associations
        _assert_control_closed(item._controller)
    else:
        with pytest.raises(live.SqlLiveError):
            _run(state)
        assert state.registrations == state.actions == []
        _assert_no_score(state)
    assert state.reached == [("handler", context)]
    _assert_started(state)


def test_public_bash_projection(mock_kernel_composition, monkeypatch):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    result = _run(state)
    data = result.episodes[0].task.data
    item, = state.associations
    _assert_control_closed(item._controller)
    assert data.prompt == bash.public_bash_prompt(
        state.spec.input.task.question, state.spec.input.schema)
    wire = data.model_dump_json()
    for value in (
            state.spec.input.task.db_path, state.spec.input.task.gold_sql,
            state.spec.input.task.evidence, str(state.spec.scratch),
            state.spec.engine_binary, "approved_skill", "broker_config", "source_pins"):
        assert value not in wire


@pytest.mark.parametrize("boundary", [
    "request", "response", "before-action", "after-SQL", "after-action", "pre-score",
])
@pytest.mark.parametrize("drift", ["source", "context", "task", "agent", "scorer", "resource"])
def test_host_source_and_identity_drift(mock_kernel_composition, monkeypatch, boundary, drift):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    real_check = live._Association.check
    refusals = []

    def checked(item, *, retired=False):
        try:
            return real_check(item, retired=retired)
        except (live.SqlLiveError, BashSqlError) as error:
            if state.reached:
                refusals.append(error)
            raise

    monkeypatch.setattr(live._Association, "check", checked)

    def mutate(item):
        state.reached.append(("drift", boundary, drift))
        if drift == "source":
            state.source.write_text("changed\n")
        elif drift == "context":
            object.__setattr__(item.ctx, "client", item.ctx.client.model_copy(deep=True))
        elif drift == "task":
            item.task.data = item.task.data.model_copy(deep=True)
        elif drift == "agent":
            item.agent.harness = copy.copy(item.harness)
        elif drift == "scorer":
            item.scorer = object()
        else:
            object.__setattr__(state.spec, "engine_binary", "/changed/engine")

    if boundary in ("request", "pre-score"):
        name = "check_request" if boundary == "request" else "require_score_ready"
        real = getattr(live._Association, name)

        def check(item, *args):
            mutate(item)
            return real(item, *args)
        monkeypatch.setattr(live._Association, name, check)
    elif boundary == "response":
        real = BashActionController.register_response

        def register(controller, original):
            out = real(controller, original)
            mutate(live._ACTIVE_ASSOCIATION.get() or next(
                iter(live._ACTIVE_SCOPE.get().associations.values())))
            return out
        monkeypatch.setattr(BashActionController, "register_response", register)
    elif boundary == "after-SQL":
        real = QueryWorkerController.execute

        async def execute(controller, sql):
            out = await real(controller, sql)
            mutate(live._ACTIVE_ASSOCIATION.get())
            return out
        monkeypatch.setattr(QueryWorkerController, "execute", execute)
    else:
        name = "before_action" if boundary == "before-action" else "after_action"
        real = getattr(BashSqlBinding, name)

        def action(binding, call_id):
            mutate(live._ACTIVE_ASSOCIATION.get())
            return real(binding, call_id)
        monkeypatch.setattr(BashSqlBinding, name, action)
    with pytest.raises((live.SqlLiveError, BashSqlError, RuntimeError, AttributeError)):
        _run(state)
    assert state.reached == [("drift", boundary, drift)]
    expected = {
        "source": "approved Bash source binding differs",
        "context": "actual SQL episode association differs",
        "task": "original SQL task behavior differs",
        "agent": "actual SQL episode association differs",
        "scorer": "actual SQL episode association differs",
        "resource": "Bash resource custody changed",
    }
    assert refusals and str(refusals[0]) == expected[drift]
    _assert_started(state)
    if boundary == "request":
        assert state.registrations == state.actions == []
    elif boundary == "response":
        assert state.registrations == ["one", "two"] and state.actions == []
    elif boundary in ("before-action", "after-SQL", "after-action"):
        assert state.registrations == ["one", "two"]
        assert ("after", "one") not in state.actions
        if boundary != "before-action":
            assert state.actions == [("before", "one")]
    else:
        assert state.actions == [
            ("before", "one"), ("after", "one"), ("before", "two"), ("after", "two")]
    _assert_no_score(state)


def test_retirement_precedes_score(mock_kernel_composition, monkeypatch):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)

    async def scenario():
        state.sql_started, state.sql_release = asyncio.Event(), asyncio.Event()
        state.teardown_started, state.teardown_release = asyncio.Event(), asyncio.Event()
        caller = asyncio.create_task(_execute(state))
        try:
            await asyncio.wait_for(state.sql_started.wait(), 5)
            _assert_started(state)
            assert state.actions == [
                ("before", "one"), ("after", "one"), ("before", "two"), ("after", "two")]
            assert len(state.admissions) == len(state.scores) == 0
            assert not state.teardown_started.is_set()
            state.sql_release.set()
            await asyncio.wait_for(state.teardown_started.wait(), 5)
            assert len(state.admissions) == len(state.scores) == 0
            state.teardown_release.set()
            result = await asyncio.wait_for(caller, 5)
            assert len(result.receipts) == len(state.admissions) == len(state.scores) == 1
            item, = state.associations
            _assert_control_closed(item._controller)
        finally:
            state.sql_release.set()
            state.teardown_release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["binding", "container", "volume"])
def test_retirement_fault_never_scores(mock_kernel_composition, monkeypatch, fault):
    state = mock_kernel_composition
    state.fault = fault
    _mock_gate(monkeypatch)
    with pytest.raises((live.SqlLiveError, BashSqlError, RuntimeError)):
        _run(state)
    assert ("fault", fault) in state.reached
    assert all(event == ("fault", fault) for event in state.reached)
    _assert_started(state)
    if fault == "container":
        assert state.actions == [("before", "one")]
    else:
        assert state.actions == [
            ("before", "one"), ("after", "one"), ("before", "two"), ("after", "two")]
    _assert_no_score(state)
    item, = state.associations
    bound = item.bash_resources
    if fault == "binding":
        assert bound.binding.cleanup_error is not None or not bound.binding._closed
    elif fault == "container":
        assert len(bound.owner.owned_containers) >= 1
    else:
        assert bound.owner.workspace is not None
    assert item.score_ready is False


async def _invoke_env(state):
    case = state.case
    scope = live._Scope(case.plan, case.config, case.fixture.executor, case.instrument,
                        case.policy, None, bash_resources=(state.spec,))
    token = live._ACTIVE_SCOPE.set(scope)
    try:
        env = loaders.load_environment(case.config.env)
        task, = env.taskset
        agent = _EpisodeAgent(
            case.policy.agent.model_copy(deep=True), interception=None,
            name="agent", shared_tools={}, task_cls=type(task), gate=None,
            completed=[], on_trace=None, on_discard=None, warned_resources=set())
        try:
            await env.run(task, SimpleNamespace(agent=agent))
        finally:
            assert live._ACTIVE_ASSOCIATION.get() is None
    finally:
        scope.live = False
        live._ACTIVE_SCOPE.reset(token)


@pytest.mark.parametrize("stage", ["setup", "action", "SQL", "finalize", "score"])
@pytest.mark.parametrize("secondary_cancels", [1, 3])
def test_primary_cancellation_survives_cleanup(
        mock_kernel_composition, monkeypatch, stage, secondary_cancels):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    primary = asyncio.CancelledError("actual-primary-" + stage)
    original_cause = ValueError("primary-cause")
    primary.__cause__ = original_cause
    primary.add_note("original primary note")
    state.primary, state.cancel_stage = primary, stage
    if stage == "setup":
        real = BirdSqlTask.setup

        async def setup(task, trace, runtime):
            await real(task, trace, runtime)
            state.reached.append(("cancel", "setup"))
            raise primary
        monkeypatch.setattr(BirdSqlTask, "setup", setup)
    elif stage == "SQL":
        # Inject at the awaited SQL boundary, not a broker's neutral wire error.
        async def cancelled_sql(binding, *, query):
            state.reached.append(("cancel", "SQL"))
            raise primary
        monkeypatch.setattr(BashSqlBinding, "execute_sql", cancelled_sql)

    async def scenario():
        state.close_started, state.close_release = asyncio.Event(), asyncio.Event()
        caller = asyncio.create_task(_invoke_env(state))
        try:
            await asyncio.wait_for(state.close_started.wait(), 5)
            _assert_started(state)
            assert state.reached and all(event == ("cancel", stage) for event in state.reached)
            item, = state.associations
            assert item.live is False
            for _ in range(secondary_cancels):
                caller.cancel("secondary")
                await asyncio.sleep(0)
            state.close_release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await caller
            assert caught.value is primary and primary.__cause__ is original_cause
            assert "original primary note" in primary.__notes__
            assert item.receipt is item.result is None
            assert item.bash_resources.owner._teardown_task.done()
            assert item.scorer._closed
            if stage != "score":
                assert len(state.admissions) == len(state.scores) == 0
            else:
                assert len(state.admissions) == len(state.scores) == 1
            _assert_control_closed(item._controller)
        finally:
            state.close_release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
    asyncio.run(scenario())
    assert live._ACTIVE_ASSOCIATION.get() is live._ACTIVE_SCOPE.get() is None


@pytest.mark.parametrize("cleanup_fault", ["none", "resolution", "await"])
@pytest.mark.parametrize("secondary_cancels", [1, 3])
def test_controller_drift_cannot_skip_retained_cleanup(
        mock_kernel_composition, monkeypatch, cleanup_fault, secondary_cancels):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    real_controller_close = BashActionController.aclose
    real_binding_close = BashSqlBinding.aclose
    real_stop = BashOwnedDockerRuntime.stop
    real_run = BashOwnedDockerRuntime.run
    primary = asyncio.CancelledError("controller-drift-primary")
    primary.add_note("original primary note")
    secondary = RuntimeError("controller-close-" + cleanup_fault)
    secondary_cause = ValueError("original cleanup cause")
    secondary.__cause__ = secondary_cause
    secondary.add_note("original cleanup note")

    async def drift(item):
        state.reached.append(("controller-drift", cleanup_fault))
        state.retained_controller = item._controller
        owner = item.bash_resources.owner
        state.original_containers = set(owner.owned_containers)
        state.original_workspace = owner.workspace
        owner.controller = object()
        with pytest.raises(live.SqlLiveError) as refusal:
            item.check()
        state.custody_refusal = refusal.value
        primary.__cause__ = refusal.value
        raise primary

    async def run(runtime, argv, env):
        try:
            return await real_run(runtime, argv, env)
        finally:
            state.events.append(("kernel-unwound",))

    class ControllerClose:
        def __get__(self, controller, cls=None):
            if controller is None:
                return self
            state.events.append(("controller-close-resolved", controller))
            if not state.associations[0].live:
                state.events.append(("association-controller-close-resolved", controller))
            if cleanup_fault == "resolution":
                raise secondary

            async def close():
                state.events.append(("controller-close-invoked", controller))
                await real_controller_close(controller)
                state.events.append(("controller-close-task", controller._close_task))
                if cleanup_fault == "await":
                    raise secondary
            return close

    async def close_binding(binding):
        state.events.append(("original-binding-close", binding))
        if not state.associations[0].live:
            state.events.append(("association-binding-close", binding))
        await real_binding_close(binding)

    async def stop(owner):
        item, = state.associations
        assert not item.live and ("kernel-unwound",) in state.events
        state.events.append(("owner-stop-after-agent", owner))
        await real_stop(owner)

    async def close_scorer(scorer):
        state.events.append(("original-scorer-close", scorer))
        state.close_started.set()
        await state.close_release.wait()
        await state.original_scorer_close(scorer)

    state.handler = drift
    monkeypatch.setattr(BashOwnedDockerRuntime, "run", run)
    monkeypatch.setattr(BashActionController, "aclose", ControllerClose())
    monkeypatch.setattr(BashSqlBinding, "aclose", close_binding)
    monkeypatch.setattr(BashOwnedDockerRuntime, "stop", stop)
    monkeypatch.setattr(OwnedSqlScorer, "aclose", close_scorer)

    async def scenario():
        state.close_started, state.close_release = asyncio.Event(), asyncio.Event()
        caller = asyncio.create_task(_invoke_env(state))
        try:
            await asyncio.wait_for(state.close_started.wait(), 5)
            _assert_started(state)
            assert state.reached == [("controller-drift", cleanup_fault)]
            assert state.original_containers and state.original_workspace
            for _ in range(secondary_cancels):
                caller.cancel("secondary-controller-drift")
                await asyncio.sleep(0)
            state.close_release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await caller
            assert caught.value is primary
            assert primary.__cause__ is state.custody_refusal
            assert "original primary note" in primary.__notes__
            assert any("secondary Bash cleanup:" in note for note in primary.__notes__)
            item, = state.associations
            owner, binding = item.bash_resources.owner, item.bash_resources.binding
            controller = state.retained_controller
            assert item._controller is controller and owner.controller is not controller
            if cleanup_fault != "none":
                assert any(error is secondary for error in controller.cleanup_errors)
                assert secondary.__cause__ is secondary_cause
                assert "original cleanup note" in secondary.__notes__
            assert ("controller-close-resolved", controller) in state.events
            assert ("association-controller-close-resolved", controller) in state.events
            assert ("original-binding-close", binding) in state.events
            assert ("association-binding-close", binding) in state.events
            assert ("owner-stop-after-agent", owner) in state.events
            assert ("original-scorer-close", item.original_scorer) in state.events
            assert binding._close_task.done() and binding._owner.closed
            assert item.original_scorer._closed
            if cleanup_fault == "resolution":
                assert controller._close_task is None and not controller.closed
                assert controller.control.custody is not None
                controller.control.custody.check()
            else:
                assert controller._close_task.done() and controller.closed
                assert controller.control.revoked and controller.control.custody is None
                close_tasks = [event[1] for event in state.events
                               if event[0] == "controller-close-task"]
                assert close_tasks and all(task is controller._close_task for task in close_tasks)
            engine = [event[1] for event in state.events if event[0] == "engine"]
            for name in state.original_containers:
                assert sum(argv[:2] == ("container", "rm") and argv[-1] == name
                           for argv in engine) == 1
            assert sum(argv[:2] == ("volume", "rm")
                       and argv[-1] == state.original_workspace for argv in engine) == 1
            assert not owner.owned_containers and owner.workspace is None
            assert not owner.engine_tasks and not owner.engine_processes
            assert owner._teardown_task.done()
            assert owner._teardown_task.exception() is not None
            assert owner.custodies and primary._sql_live_association is item
            assert not item.score_ready
            with pytest.raises((owned.BashBridgeError, AttributeError)):
                owner.require_valid()
        finally:
            state.close_release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
            if cleanup_fault == "resolution" and hasattr(state, "retained_controller"):
                # Release test-owned listener only after retaining/asserting failed custody.
                await state.retained_controller.control.close()
                _assert_control_closed(state.retained_controller)
    asyncio.run(scenario())
    _assert_no_score(state)


@pytest.mark.parametrize("invalid", [False, True])
def test_ex_zero_and_invalid_are_distinct(mock_kernel_composition, monkeypatch, invalid):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    state.invalid, state.mismatch = invalid, not invalid
    if invalid:
        with pytest.raises(live.SqlLiveError):
            _run(state)
        assert all(item.receipt is item.result is None for item in state.associations)
        item, = state.associations
        assert set(item.trace.rewards) == {"execution_accuracy"}
        assert item.trace.rewards["execution_accuracy"] is None
    else:
        result = _run(state)
        assert len(result.receipts) == 1 and result.receipts[0].result.valid
        assert result.receipts[0].result.score == 0
        assert result.episodes[0].traces[0].rewards["execution_accuracy"].score == 0
    assert len(state.admissions) == len(state.scores) == 1
    item, = state.associations
    _assert_control_closed(item._controller)


@pytest.mark.parametrize("profile", ["edit", "search", "MCP", "skills", "approval", "reuse", "capture"])
def test_bash_profile_and_capture_refusals(mock_kernel_composition, monkeypatch, profile):
    state = mock_kernel_composition
    _mock_gate(monkeypatch)
    updates = {}
    if profile in ("edit", "search"):
        setattr(state.case.config.env.agent.harness, profile, True)
    elif profile == "skills":
        state.case.config.env.agent.harness.skills.append("forbidden-skill")
    elif profile == "approval":
        updates["approved_skill"] = object()
    elif profile == "reuse":
        row = replace(state.spec.input, reuse_case=object())
        state.case.plan = live.SqlLivePlan((row,))
        state.spec = replace(state.spec, input=row)
    elif profile == "capture":
        updates["capture"] = live.SqlLiveCapture("c", "s", "r", "p", "v")
    else:
        from verifiers.v1.harnesses.bash.harness import BashHarness

        harness = BashHarness(state.case.config.env.agent.harness)
        with pytest.raises(BashSqlError):
            owned.require_bash_only(harness, {"extra": "http://unused.invalid"})
        assert len(state.events) == len(state.actions) == 0
        return
    with pytest.raises(live.SqlLiveError):
        asyncio.run(_execute(state, **updates))
    assert len(state.events) == len(state.actions) == len(state.admissions) == 0
