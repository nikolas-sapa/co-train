"""Source-only parent tests. Synthetic transport checks prove no native claims."""

import asyncio
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace

import pytest
from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.errors import SandboxError
from verifiers.v1.runtimes.docker import DockerConfig, DockerRuntime
from verifiers.v1.runtimes import ProgramResult
from verifiers.v1.types import AssistantMessage, Response, ToolCall

from bench.bird_bash_live import require_production_bash_runtime
from bench.test_bird_sql_worker_controller_integration import rig
from ptc.bash_owned_runtime import (
    BashActionController, BashBridgeError, BashOwnedDockerRuntime, BridgeLimits,
    _DEADLINE, _Directory, join_owned, require_bash_only,
)
from ptc import bash_owned_runtime as owned
from ptc import test_bash_bridge_client as bridge_tests
from ptc.sql_owned_bash import BashSqlBinding, BashSqlError
from ptc.test_sql_owned_bash import inputs


_UNRESOLVED_ENGINE_CHILDREN = []


@pytest.fixture
def tmp_path():
    raw = os.environ.get("TMPDIR")
    if not raw:
        raise BashBridgeError("explicit parent TMPDIR required")
    root = Path(raw)
    if not root.is_absolute() or str(root.resolve(strict=True)) != raw:
        raise BashBridgeError("canonical parent TMPDIR required")
    info = root.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise BashBridgeError("owned 0700 parent TMPDIR required")
    custody = _Directory(root)
    try:
        path = Path(tempfile.mkdtemp(prefix="br-", dir=root))
        path.chmod(0o700)
        custody.check()
        return path
    finally:
        custody.close()


def bare_runtime(root):
    runtime = object.__new__(BashOwnedDockerRuntime)
    runtime.root, runtime.scratch = root, root
    runtime.limits = BridgeLimits()
    runtime.workspace, runtime.image_id = "owned-workspace", "sha256:" + "a" * 64
    runtime._container, runtime.interpreter = "owned-policy", "/usr/bin/python3"
    runtime.config = SimpleNamespace(cpu=None, memory=None, workdir="/app")
    runtime.env = {}
    runtime.custodies, runtime.controller = [], None
    runtime.cleanup_errors, runtime.engine_tasks, runtime.engine_processes = [], set(), set()
    runtime.engine_binary = "/usr/bin/docker"
    runtime.owned_containers = {"owned-policy"}
    runtime.retirement_attempts = set()
    runtime._teardown_task, runtime._teardown_deadline = None, None
    runtime._policy_deadline, runtime._policy_claimed = None, False
    runtime.message_files = set()
    return runtime


class Binding:
    def __init__(self, events):
        self.events, self._invalid = events, False

    def check_binding(self):
        if self._invalid:
            raise BashSqlError("invalid")

    def before_action(self, call_id):
        self.events.append(("before", call_id))

    def after_action(self, call_id):
        self.events.append(("after", call_id))

    async def aclose(self):
        self.events.append(("binding-close",))


@pytest.mark.parametrize("controller_fault", ["object", "resolution"])
def test_controller_lookup_failure_keeps_independent_teardown(
        tmp_path, monkeypatch, controller_fault):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        custody = _Directory(tmp_path)
        runtime.custodies.append(custody)
        runtime.controller = object()
        events = []
        resolution_error = LookupError("controller property unavailable")

        if controller_fault == "resolution":
            def controller(owner):
                raise resolution_error
            monkeypatch.setattr(BashOwnedDockerRuntime, "controller",
                                property(controller), raising=False)

        async def engine(*argv, **kwargs):
            events.append(argv)
            issued = kwargs.get("_on_issued")
            if issued is not None:
                issued()
            return b"", b"", 0

        async def pending_engine():
            events.append(("engine-joined",))

        runtime.engine_call = engine
        pending = asyncio.create_task(pending_engine())
        runtime.engine_tasks.add(pending)
        try:
            with pytest.raises(BashBridgeError) as caught:
                await runtime.teardown()
            if controller_fault == "resolution":
                assert caught.value.__cause__ is resolution_error
            else:
                assert isinstance(caught.value.__cause__, AttributeError)
            assert pending.done() and not runtime.engine_tasks
            assert events.count(("engine-joined",)) == 1
            assert events.count(("container", "rm", "--force", "owned-policy")) == 1
            assert events.count(("volume", "rm", "owned-workspace")) == 1
            assert runtime.retirement_attempts == {"owned-policy"}
            assert not runtime.owned_containers and runtime.workspace is None
            assert runtime.custodies == [custody]
            custody.check()
            teardown = runtime._teardown_task
            before = tuple(events)
            with pytest.raises(BashBridgeError) as repeated:
                await runtime.teardown()
            assert repeated.value is caught.value
            assert runtime._teardown_task is teardown and tuple(events) == before
            with pytest.raises((BashBridgeError, AttributeError, LookupError)):
                runtime.require_valid()
        finally:
            custody.close()
            await asyncio.gather(pending, return_exceptions=True)
    asyncio.run(scenario())


class Engine:
    def __init__(self, events, retirement_fault=False):
        self.events, self.retirement_fault = events, retirement_fault
        self.owned_containers = set()

    def actor_create_argv(self, name, command, directory):
        return "create", name, "/bin/bash", "-c", command

    def check_staging(self):
        pass

    async def engine_call(self, *argv, **kwargs):
        if argv[0] == "create":
            self.events.append(("execute", argv[-1]))
        return b'{"received":true,"status":0}\n', b"stderr\n", 7

    async def inspect_container(self, name):
        return {"State": {"Status": "exited", "ExitCode": 7}}

    async def retire_container(self, name):
        self.events.append(("retire", name))
        if self.retirement_fault:
            raise BashBridgeError("retirement unknown")
        self.owned_containers.remove(name)


def response(*calls):
    return Response(
        id="response", created=0, model="synthetic",
        finish_reason="tool_calls",
        message=AssistantMessage(tool_calls=[
            ToolCall(id=call_id, name="bash",
                     arguments=json.dumps({"command": command}, ensure_ascii=False))
            for call_id, command in calls]))


def test_two_duplicate_commands_distinct_ids_and_no_replay(tmp_path):
    async def scenario():
        events = []
        engine = Engine(events)
        controller = BashActionController(
            binding=Binding(events), runtime=engine, root=tmp_path, limits=BridgeLimits())
        original = response(("one", "printf 'x' | cat"), ("two", "printf 'x' | cat"))
        assert controller.register_response(original) is original
        assert events == []
        for call_id in ("one", "two"):
            out = await controller.dispatch("printf 'x' | cat")
            assert out == (b'{"received":true,"status":0}\n', b"stderr\n", 7)
            assert events[-1] == ("after", call_id)
            assert events[-2][0] == "retire"
        with pytest.raises(BashBridgeError):
            await controller.dispatch("printf 'x' | cat")
        assert [event[0] for event in events].count("execute") == 2
        assert controller.active is None
        assert not controller.fatal.done()
    asyncio.run(scenario())


def test_actor_argv_preserves_bytes_and_separates_mounts(tmp_path):
    runtime = bare_runtime(tmp_path)
    command = "printf 'caf\u00e9\\n' | cat; printf err >&2; exit 7"
    argv = runtime.actor_create_argv("owned-action", command, tmp_path / "sql")
    assert argv[-3:] == ("/bin/bash", "-c", command)
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--pids-limit" in argv and "--memory" in argv and "--cpus" in argv
    assert not any(value in " ".join(argv) for value in
                   ("bridge-control", "policy-bin", "docker.sock", "--privileged", "--pid=host"))


@pytest.mark.parametrize("edit,search,mcp", [
    (True, False, {}), (False, True, {}), (False, False, {"extra": "http://unused"}),
])
def test_unsupported_profile_zero_policy_executions(edit, search, mcp):
    harness = BashHarness(BashHarnessConfig(id="bash", edit=edit, search=search))
    with pytest.raises(BashBridgeError):
        require_bash_only(harness, mcp)


def test_retirement_fault_no_after_action_or_valid_outcome(tmp_path):
    async def scenario():
        events = []
        engine = Engine(events, retirement_fault=True)
        controller = BashActionController(
            binding=Binding(events), runtime=engine, root=tmp_path, limits=BridgeLimits())
        controller.register_response(response(("one", "sleep 0")))
        with pytest.raises(BashBridgeError):
            await controller.dispatch("sleep 0")
        assert len(engine.owned_containers) == 1
        assert not any(event[0] == "after" for event in events)
        with pytest.raises(BashBridgeError):
            await controller.race_policy(asyncio.sleep(0, result="exit-zero"))
    asyncio.run(scenario())


def test_fault_out_of_band_invalidates_policy_exit_zero(tmp_path):
    async def scenario():
        events = []
        controller = BashActionController(
            binding=Binding(events), runtime=Engine(events), root=tmp_path,
            limits=BridgeLimits())
        controller.fail(ValueError("protocol"))
        with pytest.raises(BashBridgeError):
            await controller.race_policy(asyncio.sleep(0, result="exit-zero"))
    asyncio.run(scenario())


def test_join_cleanup_preserves_cancellation_and_joins():
    async def scenario():
        finished = asyncio.Event()

        async def cleanup():
            await asyncio.sleep(0.01)
            finished.set()

        owned = asyncio.create_task(cleanup())
        waiter = asyncio.create_task(join_owned(owned))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert owned.done() and finished.is_set()
    asyncio.run(scenario())


def test_production_guard_still_refuses(rig, tmp_path):
    harness = BashHarness(BashHarnessConfig(id="bash", edit=False, search=False, skills=[]))
    binding = BashSqlBinding(**inputs(rig, harness=harness))
    runtime = BashOwnedDockerRuntime(
        DockerConfig(image="offline-parent-owned"), harness=harness,
        binding=binding, interpreter="/usr/local/bin/python3", scratch=tmp_path)
    assert isinstance(runtime, DockerRuntime)
    assert runtime.info.image == "offline-parent-owned"
    view = runtime.with_env({"PATH": "/untrusted"})
    assert view.__dict__ is runtime.__dict__
    assert view.env == {"PATH": "/untrusted"}
    with pytest.raises(BashSqlError):
        require_production_bash_runtime(runtime)
    asyncio.run(binding.aclose())


def test_view_teardown_then_owner_stop_once(rig, tmp_path, monkeypatch):
    async def scenario():
        harness = BashHarness(BashHarnessConfig(id="bash", edit=False, search=False))
        binding = BashSqlBinding(**inputs(rig, harness=harness))
        owner = BashOwnedDockerRuntime(
            DockerConfig(image="offline-parent-owned"), harness=harness,
            binding=binding, interpreter="/usr/local/bin/python3", scratch=tmp_path)
        owner.controller = BashActionController(
            binding=binding, runtime=owner, root=tmp_path, limits=owner.limits)
        owner.owned_containers.add("owned-policy")
        owner.workspace = "owned-volume"
        events = []

        async def engine_call(self, *argv, **kwargs):
            issued = kwargs.get("_on_issued")
            if issued is not None:
                issued()
            events.append(argv)
            await asyncio.sleep(0)
            return b"", b"", 0

        monkeypatch.setattr(BashOwnedDockerRuntime, "engine_call", engine_call)
        view = owner.with_env({"TASK": "private"})
        await asyncio.gather(view.teardown(), owner.teardown(), view.teardown())
        joined = owner._teardown_task
        assert view._teardown_task is joined and joined.done()
        assert owner.stopped is view.stopped is False
        owner.require_valid()
        view.require_valid()
        await view.teardown()
        await owner.stop()
        await owner.stop()
        assert owner.stopped is view.stopped is True
        assert owner._teardown_task is joined
        assert events.count(("container", "rm", "--force", "owned-policy")) == 1
        assert events.count(("volume", "rm", "owned-volume")) == 1
        assert owner.owned_containers == set() and owner.workspace is None
    asyncio.run(scenario())


def test_with_env_policy_path_pinned_after_merge(rig, tmp_path):
    async def scenario():
        harness = BashHarness(BashHarnessConfig(id="bash", edit=False, search=False))
        binding = BashSqlBinding(**inputs(rig, harness=harness))
        runtime = BashOwnedDockerRuntime(
            DockerConfig(image="offline-parent-owned"), harness=harness,
            binding=binding, interpreter="/usr/local/bin/python3", scratch=tmp_path)
        runtime.controller = BashActionController(
            binding=binding, runtime=runtime, root=tmp_path, limits=runtime.limits)
        observed = []

        async def run(argv, env):
            observed.append(env["PATH"])
            return ProgramResult(0, "", "")

        runtime.run = run
        view = runtime.with_env({"PATH": "/task-replaced"})
        try:
            await view.run_program(
                [runtime.interpreter, "/bridge-program/chat.py", "--bash"],
                {"PATH": "/harness-override"})
            assert observed == ["/bridge-bin:/usr/local/bin:/usr/bin:/bin"]
            assert runtime._policy_claimed
        finally:
            await binding.aclose()
    asyncio.run(scenario())


def test_missing_image_refuses_before_create(rig, tmp_path, monkeypatch):
    async def scenario():
        harness = BashHarness(BashHarnessConfig(id="bash", edit=False, search=False))
        binding = BashSqlBinding(**inputs(rig, harness=harness))
        runtime = BashOwnedDockerRuntime(
            DockerConfig(image="missing"), harness=harness,
            binding=binding, interpreter="/usr/local/bin/python3", scratch=tmp_path)
        observed = []

        async def engine(*argv, **kwargs):
            observed.append(argv)
            raise BashBridgeError("missing image")

        runtime.engine_call = engine
        monkeypatch.setattr("ptc.bash_owned_runtime.sys.platform", "linux")
        monkeypatch.setattr("ptc.bash_owned_runtime.stat.S_ISSOCK", lambda mode: True)
        original_stat = os.stat

        def engine_socket_stat(path, *args, **kwargs):
            if str(path) == "/var/run/docker.sock":
                return SimpleNamespace(st_mode=0)
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr("ptc.bash_owned_runtime.os.stat", engine_socket_stat)
        try:
            with pytest.raises(BashBridgeError):
                await runtime.start()
            assert observed == [("image", "inspect", "missing")]
            assert runtime.owned_containers == set()
            assert runtime.workspace is None and runtime.root is None
        finally:
            await binding.aclose()
            for custody in runtime.custodies:
                custody.close()
            runtime.custodies.clear()
    asyncio.run(scenario())


def test_sql_capability_uses_binding_not_raw_application(tmp_path):
    async def execute_sql(*, query):
        events = leaf_events[0]
        events.append(("sql", query))
        return SimpleNamespace(columns=("one",), rows=((1,),))

    # Separate from native qualification; the real binding path is covered by
    # existing BashSqlBinding parent tests, never replaced with raw application.
    leaf_events = [[]]
    async def checked():
        events = leaf_events[0]
        leaf = Binding(events)
        leaf.execute_sql = execute_sql
        controller = BashActionController(
            binding=leaf, runtime=Engine(events), root=tmp_path, limits=BridgeLimits())
        controller.active = "original"
        token = _DEADLINE.set(asyncio.get_running_loop().time() + 1)
        try:
            stdout, stderr, status = await controller._execute_sql("SELECT 1")
        finally:
            _DEADLINE.reset(token)
        assert json.loads(stdout)["format"] == "cotrain_sql_result"
        assert events == [("sql", "SELECT 1")]
        assert stderr == b"" and status == 0
    asyncio.run(checked())


def test_limits_reject_incompatible_deadlines():
    for values in ({"action_s": 109}, {"retirement_s": 40},
                   {"delivery_s": 9}, {"workspace_bytes": 0}):
        with pytest.raises(BashBridgeError):
            BridgeLimits(**values)


@pytest.mark.parametrize("fault", ["overflow", "error", "timeout"])
def test_engine_primary_survives_cleanup(tmp_path, monkeypatch, fault):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        primary = {"overflow": BashBridgeError("engine or actor output overflow"),
                   "error": OSError("engine read"), "timeout": TimeoutError("engine read")}[fault]
        secondary = asyncio.CancelledError("cleanup")
        counts = {"spawn": 0, "kill": 0, "join": 0, "wait": 0}
        body_errors = []

        async def read():
            if fault == "overflow":
                return b"x" * (runtime.limits.output_bytes + 1)
            raise primary

        async def blocked():
            await asyncio.Event().wait()

        class Process:
            returncode = None
            stdin = None
            stdout = SimpleNamespace(read=lambda count: read(),
                                     _transport=SimpleNamespace(close=lambda: None))
            stderr = SimpleNamespace(read=lambda count: blocked(),
                                     _transport=SimpleNamespace(close=lambda: None))

            def kill(self):
                counts["kill"] += 1

            async def wait(self):
                counts["wait"] += 1
                self.returncode = -9
                return -9

        async def spawn(*args, **kwargs):
            counts["spawn"] += 1
            return Process()

        async def join(task, deadline=None):
            counts["join"] += 1
            value = await join_owned(task, deadline)
            if counts["join"] == 1:
                body_errors.append(value[0])
                raise secondary
            return value

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(owned, "join_owned", join)
        with pytest.raises(type(primary)) as raised:
            await runtime.engine_call("exec", "synthetic")
        assert raised.value is body_errors[0]
        if fault != "overflow":
            assert raised.value is primary
        else:
            assert str(raised.value) == "engine or actor output overflow"
        assert counts == {"spawn": 1, "kill": 1, "join": 3, "wait": 1}
        assert runtime.cleanup_errors.count(secondary) == 1
        assert len(runtime.cleanup_errors) == 2
        assert all(isinstance(error, asyncio.CancelledError) for error in runtime.cleanup_errors)
        assert runtime.engine_tasks == set() and runtime.engine_processes == set()
    asyncio.run(scenario())


@pytest.mark.parametrize("controller_fault", ["object", "resolution", "fail"])
@pytest.mark.parametrize("primary_kind", ["cancel", "error"])
def test_original_engine_primary_survives_notification_drift(
        tmp_path, monkeypatch, controller_fault, primary_kind):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        started, release = asyncio.Event(), asyncio.Event()
        primary = ValueError("engine primary")
        cause = LookupError("existing primary cause")
        notes = ["existing primary note"]
        secondary = RuntimeError("private notification failure")
        primaries, caught, readers, joins, notifications = [], [], [], [], []
        counts = {"spawn": 0, "kill": 0, "wait": 0, "stdout": 0, "stderr": 0}

        async def read(count):
            readers.append(asyncio.current_task())
            return b""

        def close(name):
            counts[name] += 1

        class Process:
            returncode = None
            stdin = None
            stdout = SimpleNamespace(read=read, _transport=SimpleNamespace(
                close=lambda: close("stdout")))
            stderr = SimpleNamespace(read=read, _transport=SimpleNamespace(
                close=lambda: close("stderr")))

            def kill(self):
                counts["kill"] += 1

            async def wait(self):
                counts["wait"] += 1
                if counts["wait"] == 1:
                    started.set()
                    try:
                        await release.wait()
                    except asyncio.CancelledError as error:
                        error.__cause__ = cause
                        error.add_note(notes[0])
                        primaries.append(error)
                        raise
                    primary.__cause__ = cause
                    primary.add_note(notes[0])
                    primaries.append(primary)
                    raise primary
                self.returncode = -9
                return -9

        process = Process()

        async def spawn(*args, **kwargs):
            counts["spawn"] += 1
            return process

        async def join(task, deadline=None):
            joins.append(task)
            return await join_owned(task, deadline)

        def fail(error):
            notifications.append(error)
            raise secondary

        async def invoke():
            try:
                await runtime.engine_call("exec", "synthetic")
            except BaseException as error:
                caught.append(error)
            else:
                pytest.fail("engine primary was swallowed")

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(owned, "join_owned", join)
        call = asyncio.create_task(invoke())
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            drifted = object()
            if controller_fault == "resolution":
                def controller(owner):
                    notifications.append("resolution")
                    raise secondary
                monkeypatch.setattr(BashOwnedDockerRuntime, "controller",
                                    property(controller), raising=False)
            elif controller_fault == "fail":
                runtime.controller = SimpleNamespace(fail=fail)
            else:
                runtime.controller = drifted
            if primary_kind == "cancel":
                call.cancel("caller cancellation")
            else:
                release.set()
            await call
            assert len(primaries) == 1 and len(caught) == 1
            actual_primary = primaries[0]
            assert caught[0] is actual_primary
            if primary_kind == "cancel":
                assert isinstance(actual_primary, asyncio.CancelledError)
            else:
                assert actual_primary is primary
            assert actual_primary.__cause__ is cause
            assert actual_primary.__notes__ == notes
            assert cause.__cause__ is None and cause.__context__ is None
            assert counts == {
                "spawn": 1, "kill": 1, "wait": 2, "stdout": 1, "stderr": 1}
            assert len(readers) == 2 and len(set(readers)) == 2
            assert all(task.done() and not task.cancelled() for task in readers)
            assert len(joins) == 3 and all(task.done() for task in joins)
            assert all(task.result() == [b""] for task in joins[:2])
            assert joins[2].result() == [-9]
            assert not runtime.engine_tasks and not runtime.engine_processes
            assert len(runtime.cleanup_errors) == 1
            retained = runtime.cleanup_errors[0]
            assert retained is not actual_primary
            if controller_fault == "object":
                assert isinstance(retained, AttributeError)
                assert retained.obj is drifted and retained.name == "fail"
                assert notifications == []
            else:
                assert retained is secondary
                assert notifications == (
                    ["resolution"] if controller_fault == "resolution"
                    else [actual_primary])
            assert retained.__cause__ is None and retained.__context__ is None
        finally:
            release.set()
            if not call.done():
                call.cancel()
            await asyncio.gather(call, return_exceptions=True)
    asyncio.run(scenario())


def test_original_engine_success_does_not_notify(tmp_path, monkeypatch):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        lookups, joins, readers = [], [], []
        counts = {"spawn": 0, "kill": 0, "wait": 0, "stdout": 0, "stderr": 0}

        def controller(owner):
            lookups.append(owner)
            raise AssertionError("success must not resolve controller")

        def stream(name, data):
            chunks = [data, b""]

            async def read(count):
                readers.append(asyncio.current_task())
                return chunks.pop(0)

            def close():
                counts[name] += 1

            return SimpleNamespace(
                read=read, _transport=SimpleNamespace(close=close))

        class Process:
            returncode = None
            stdin = None
            stdout = stream("stdout", b"out")
            stderr = stream("stderr", b"err")

            def kill(self):
                counts["kill"] += 1

            async def wait(self):
                counts["wait"] += 1
                self.returncode = 0
                return 0

        async def spawn(*args, **kwargs):
            counts["spawn"] += 1
            return Process()

        async def join(task, deadline=None):
            joins.append(task)
            return await join_owned(task, deadline)

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(owned, "join_owned", join)
        monkeypatch.setattr(BashOwnedDockerRuntime, "controller",
                            property(controller), raising=False)
        assert await runtime.engine_call("exec", "synthetic") == (b"out", b"err", 0)
        assert lookups == [] and runtime.cleanup_errors == []
        assert counts == {
            "spawn": 1, "kill": 0, "wait": 2, "stdout": 1, "stderr": 1}
        assert len(set(readers)) == 2
        assert all(task.done() and not task.cancelled() for task in readers)
        assert len(joins) == 3 and all(task.done() for task in joins)
        assert [task.result() for task in joins] == [[b"out"], [b"err"], [0]]
        assert not runtime.engine_tasks and not runtime.engine_processes
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["fault", "cancel"])
def test_policy_primary_survives_cleanup(tmp_path, monkeypatch, fault):
    async def scenario():
        events = []
        controller = BashActionController(
            binding=Binding(events), runtime=Engine(events), root=tmp_path,
            limits=BridgeLimits())
        primary = ValueError("policy body")
        secondary = ValueError("cleanup") if fault == "fault" else asyncio.CancelledError()
        joins = []

        async def policy():
            raise primary

        async def join(task, deadline=None):
            joins.append(task)
            await join_owned(task, deadline)
            raise secondary

        monkeypatch.setattr(owned, "join_owned", join)
        with pytest.raises(ValueError) as raised:
            await controller.race_policy(policy())
        assert raised.value is primary
        assert len(joins) == 1 and joins[0].done()
        assert controller.cleanup_errors == [secondary]
        assert controller.fatal.done() and events == []
    asyncio.run(scenario())


@pytest.mark.parametrize("options", [
    "valid", "missing", "unsupported", "missing-inodes", "wrong-inodes",
])
def test_workspace_bounded_keeper(tmp_path, options):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        calls = []
        expected = {"type": "tmpfs", "device": "tmpfs",
                    "o": f"size={runtime.limits.workspace_bytes},"
                         f"nr_inodes={runtime.limits.workspace_inodes},uid=0,gid=0,mode=0700"}

        async def engine(*argv, **kwargs):
            calls.append(argv)
            value = {"Name": runtime.workspace, "Driver": "local", "Options": expected}
            if options == "missing":
                value["Options"] = {}
            if options == "unsupported":
                value["Driver"] = "other"
            if options in ("missing-inodes", "wrong-inodes"):
                value["Options"] = {**expected, "o": expected["o"].replace(
                    "nr_inodes=4096,", "" if options == "missing-inodes" else "nr_inodes=0,")}
            return json.dumps([value]).encode(), b"", 0

        runtime.engine_call = engine
        if options == "valid":
            await runtime.create_workspace()
            policy = runtime.policy_create_argv()
            assert policy.count(
                "type=volume,src=owned-workspace,dst=/bridge-workspace-keeper,readonly") == 1
        else:
            with pytest.raises(BashBridgeError, match="bounded local tmpfs"):
                await runtime.create_workspace()
        assert len(calls) == 2
        assert calls[0] == ("volume", "create", "--driver", "local", "--opt",
                            "type=tmpfs", "--opt", "device=tmpfs", "--opt",
                            f"o={expected['o']}", "owned-workspace")
        assert calls[1] == ("volume", "inspect", "owned-workspace")
        assert not any(argv[0] == "create" for argv in calls)
    asyncio.run(scenario())


def test_healthchecks_disabled(tmp_path):
    runtime = bare_runtime(tmp_path)
    for argv in (runtime.policy_create_argv(),
                 runtime.actor_create_argv("actor", "true", tmp_path / "sql")):
        assert argv.count("--no-healthcheck") == 1


@pytest.mark.parametrize("fault", ["symlink", "writable", "comma", "NUL"])
def test_scratch_custody_refuses(tmp_path, monkeypatch, fault):
    path = tmp_path / "scratch"
    if fault == "symlink":
        path.symlink_to(tmp_path, target_is_directory=True)
    elif fault == "writable":
        path.mkdir(mode=0o777)
        path.chmod(0o777)
        path = path / "private"
        path.mkdir(mode=0o700)
    else:
        path = tmp_path / ("bad,name" if fault == "comma" else "bad\0name")
    async def scenario():
        runtime = bare_runtime(tmp_path)
        runtime.scratch, runtime._started_once = path, False
        calls = []

        async def engine(*argv, **kwargs):
            calls.append(argv)
            raise AssertionError("engine must not be reached")

        runtime.engine_call = engine
        original_stat = os.stat

        def engine_socket_stat(path, *args, **kwargs):
            if str(path) == "/var/run/docker.sock":
                return SimpleNamespace(st_mode=0o140000)
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(owned.sys, "platform", "linux")
        monkeypatch.setattr(owned.os, "stat", engine_socket_stat)
        with pytest.raises(BashBridgeError):
            await runtime.start()
        assert calls == []
    asyncio.run(scenario())


def test_staging_link_swap_refuses(tmp_path):
    runtime = bare_runtime(tmp_path)
    custody = _Directory(tmp_path)
    runtime.custodies.append(custody)
    custody.stage("script", b"original", 0o444)
    original_inode = os.fstat(custody.fd).st_ino
    (tmp_path / "script").rename(tmp_path / "retained-original")
    (tmp_path / "script").write_bytes(b"replacement")
    try:
        with pytest.raises(BashBridgeError, match="staged file link custody"):
            runtime.actor_create_argv("actor", "true", tmp_path / "sql")
        assert os.fstat(custody.fd).st_ino == original_inode
        assert (tmp_path / "retained-original").read_bytes() == b"original"
    finally:
        custody.close()


def test_original_message_file_io(tmp_path):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        calls = []
        data, path = b'[{"role":"user","content":"original"}]', ".vf-initial-messages-trace.json"

        async def engine(*argv, **kwargs):
            calls.append((argv, kwargs, _DEADLINE.get()))
            return (data if "-i" not in argv else b""), b"", 0

        runtime.engine_call = engine
        await runtime.write(path, data)
        assert await runtime._read(path) == data
        assert len(calls) == 2 and calls[0][1] == {"input": data}
        assert calls[0][0][-1] == path and calls[1][0][-2] == path
        assert calls[0][2] == calls[1][2] == runtime._policy_deadline
        assert calls[1][0][-1] == str(runtime.limits.output_bytes + 1)
        events = []
        runtime.harness = BashHarness(BashHarnessConfig(id="bash", edit=False, search=False))
        runtime.controller = BashActionController(
            binding=Binding(events), runtime=runtime, root=tmp_path, limits=runtime.limits)

        async def run(argv, env):
            assert argv[-1] == f"--initial-messages-file={path}"
            return ProgramResult(0, "", "")

        runtime.run = run
        await runtime.run_program(
            [runtime.interpreter, "/bridge-program/chat.py", "--bash",
             f"--initial-messages-file={path}"], {})
        for operation in (runtime.write("unsupported", b""), runtime._read("unsupported")):
            with pytest.raises(BashBridgeError):
                await operation
        with pytest.raises(BashBridgeError, match="inherited unbounded"):
            runtime._exec({})
        assert len(calls) == 2
    asyncio.run(scenario())


def test_deadline_unresolved_retains_ownership(tmp_path):
    async def scenario():
        events = []
        engine = Engine(events)
        limits = BridgeLimits(action_s=0.01, engine_s=0.01, protocol_s=0.001,
                              retirement_s=0.01, delivery_s=0.002)

        async def engine_call(*argv, **kwargs):
            await asyncio.sleep(0.025)
            owned._remaining()

        async def retire(name):
            await asyncio.Event().wait()

        engine.engine_call, engine.retire_container = engine_call, retire
        controller = BashActionController(
            binding=Binding(events), runtime=engine, root=tmp_path, limits=limits)
        controller.register_response(response(("one", "true")))
        complete = asyncio.get_running_loop().time() + 0.03
        token = _DEADLINE.set(complete)
        try:
            with pytest.raises(TimeoutError):
                await controller.dispatch("true")
            assert len(engine.owned_containers) == 1
            assert controller.active == "one" and controller.fatal.done()
            assert not any(event[0] == "after" for event in events)
            assert len(controller.owned_cleanup) == 1
            assert len(controller.cleanup_errors) == 1
            assert isinstance(controller.cleanup_errors[0], TimeoutError)
        finally:
            _DEADLINE.reset(token)
            for task in controller.owned_cleanup:
                task.cancel()
            await asyncio.gather(*controller.owned_cleanup, return_exceptions=True)
            if controller.sql is not None and controller.sql.server is not None:
                controller.sql.server.close()
                await controller.sql.server.wait_closed()
                if controller.sql.custody is not None:
                    controller.sql.custody.close()
                    controller.sql.custody = None
            controller._dispatch_watchdog.cancel()
            await asyncio.gather(controller._dispatch_watchdog, return_exceptions=True)
    asyncio.run(scenario())


def test_dispatch_primary_survives_cleanup_cancel(tmp_path):
    async def scenario():
        events = []
        engine = Engine(events)
        primary = BashBridgeError("overflow")
        secondary = asyncio.CancelledError("retirement")

        async def execute(*argv, **kwargs):
            raise primary

        async def retire(name):
            raise secondary

        engine.engine_call, engine.retire_container = execute, retire
        controller = BashActionController(
            binding=Binding(events), runtime=engine, root=tmp_path, limits=BridgeLimits())
        controller.register_response(response(("one", "true")))
        with pytest.raises(BashBridgeError) as raised:
            await controller.dispatch("true")
        assert raised.value is primary
        assert controller.cleanup_errors.count(secondary) == 1
        assert len(controller.cleanup_errors) == 2
        assert isinstance(controller.cleanup_errors[1], BashBridgeError)
        assert len(engine.owned_containers) == 1
        assert events == [("before", "one")]
        assert controller.fatal.done()
        controller._dispatch_watchdog.cancel()
        await asyncio.gather(controller._dispatch_watchdog, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("budget", ["expired", "issued", "ambiguous"])
def test_retirement_consumes_only_at_launch(tmp_path, monkeypatch, budget):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        primary, launches = OSError("ambiguous launch"), []

        class Process:
            returncode, stdin = 0, None

            def __init__(self, data):
                self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
                self.stdout.feed_data(data)
                for stream in (self.stdout, self.stderr):
                    stream.feed_eof()
                    stream._transport = SimpleNamespace(close=lambda: None)

            async def wait(self):
                return self.returncode

        async def spawn(*args, **kwargs):
            launches.append(args)
            assert runtime.retirement_attempts == {"owned-policy"}
            if budget == "ambiguous":
                raise primary
            return Process(b"owned-policy\n" if "ls" in args else b"")

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        token = _DEADLINE.set(asyncio.get_running_loop().time() + (
            -1 if budget == "expired" else 1))
        try:
            if budget == "expired":
                with pytest.raises(TimeoutError):
                    await runtime.retire_container("owned-policy")
                assert launches == [] and runtime.retirement_attempts == set()
            elif budget == "ambiguous":
                with pytest.raises(OSError) as raised:
                    await runtime.retire_container("owned-policy")
                assert raised.value is primary
                with pytest.raises(BashBridgeError, match="already attempted"):
                    await runtime.retire_container("owned-policy")
                assert len(launches) == 1
                assert launches[0][-4:] == ("container", "rm", "--force", "owned-policy")
                assert runtime.retirement_attempts == {"owned-policy"}
            else:
                with pytest.raises(BashBridgeError, match="removal not observed"):
                    await runtime.retire_container("owned-policy")
                with pytest.raises(BashBridgeError, match="already attempted"):
                    await runtime.retire_container("owned-policy")
                assert len(launches) == 2
                assert sum("rm" in args for args in launches) == 1
                assert runtime.retirement_attempts == {"owned-policy"}
            assert runtime.owned_containers == {"owned-policy"}
        finally:
            _DEADLINE.reset(token)
    asyncio.run(scenario())


@pytest.mark.parametrize("route", ["helper", "teardown"])
def test_first_cancellation_survives_held_task_expiry(tmp_path, monkeypatch, route):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        runtime.limits = BridgeLimits(retirement_s=0.05)
        runtime.owned_containers.clear()
        runtime.workspace = None
        release, started = asyncio.Event(), asyncio.Event()
        cancellations = []
        actual_wait = asyncio.wait

        async def observe_wait(*args, **kwargs):
            try:
                return await actual_wait(*args, **kwargs)
            except asyncio.CancelledError as error:
                cancellations.append(error)
                raise

        async def held():
            started.set()
            await release.wait()

        task = asyncio.create_task(held())
        runtime.engine_tasks.add(task)
        monkeypatch.setattr(owned.asyncio, "wait", observe_wait)
        deadline = asyncio.get_running_loop().time() + 0.05
        waiter = asyncio.create_task(
            join_owned(task, deadline) if route == "helper" else runtime.teardown())
        try:
            await started.wait()
            await asyncio.sleep(0)
            waiter.cancel("first cancellation")
            with pytest.raises(asyncio.CancelledError) as raised:
                await waiter
            assert len(cancellations) == 1
            assert raised.value is cancellations[0]
            cause = raised.value.__cause__
            while cause is not None and not isinstance(cause, TimeoutError):
                cause = cause.__cause__
            assert isinstance(cause, TimeoutError)
            assert task in runtime.engine_tasks and not task.done()
            if route == "teardown":
                assert runtime._teardown_task is not None
        finally:
            release.set()
            await task
            if runtime._teardown_task is not None:
                await asyncio.gather(runtime._teardown_task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("size", [16, 17])
def test_original_public_read_limit_and_sentinel(tmp_path, monkeypatch, size):
    async def scenario():
        runtime = bare_runtime(tmp_path)
        runtime.limits = BridgeLimits(output_bytes=16)
        path, calls = ".vf-initial-messages-limit.json", []
        runtime.message_files.add(path)

        class Process:
            returncode, stdin = 0, None

            def __init__(self):
                self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
                self.stdout.feed_data(b"x" * size)
                for stream in (self.stdout, self.stderr):
                    stream.feed_eof()
                    stream._transport = SimpleNamespace(close=lambda: None)

            async def wait(self):
                return self.returncode

        async def spawn(*args, **kwargs):
            calls.append(args)
            return Process()

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        if size == 16:
            assert await runtime.read(path, max_bytes=16) == b"x" * 16
        else:
            with pytest.raises(SandboxError, match="over the 16 byte limit"):
                await runtime.read(path, max_bytes=16)
        assert len(calls) == 1 and calls[0][-2:] == (path, "17")
        assert runtime.engine_tasks == runtime.engine_processes == set()
    asyncio.run(scenario())


@pytest.mark.parametrize("value", [True, 0, -1, 65537, None, float("inf"), "4096"])
def test_workspace_inode_limits_refuse(value):
    with pytest.raises(BashBridgeError):
        BridgeLimits(workspace_inodes=value)


@pytest.mark.parametrize("value", [1, 4096, 65536])
def test_workspace_inode_limits_exact_option(tmp_path, value):
    runtime = bare_runtime(tmp_path)
    runtime.limits = BridgeLimits(workspace_inodes=value)
    assert BridgeLimits().workspace_inodes == 4096
    assert runtime.workspace_create_argv()[-2] == (
        f"o=size={runtime.limits.workspace_bytes},nr_inodes={value},uid=0,gid=0,mode=0700")


@pytest.mark.parametrize("factory", ["runtime", "client"])
@pytest.mark.parametrize("fault", ["valid", "missing", "noncanonical", "mode", "owner"])
def test_fixtures_require_private_parent_tmpdir(tmp_path, monkeypatch, factory, fault):
    root = tmp_path / "parent-tmp"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    fixture = globals()["tmp_path"] if factory == "runtime" else bridge_tests.tmp_path
    monkeypatch.setenv("TMPDIR", str(root))
    if fault == "missing":
        monkeypatch.delenv("TMPDIR")
    elif fault == "noncanonical":
        monkeypatch.setenv("TMPDIR", str(root) + "/.")
    elif fault == "mode":
        root.chmod(0o755)
    elif fault == "owner":
        uid = os.geteuid()
        monkeypatch.setattr(owned.os, "geteuid", lambda: uid + 1)
    if fault == "valid":
        child = fixture.__wrapped__()
        assert child.parent == root
        info = child.stat()
        assert info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
    else:
        with pytest.raises(BashBridgeError):
            fixture.__wrapped__()


def test_real_engine_pipe_overflow_reaps(tmp_path, monkeypatch):
    if os.environ.get("BASH_BRIDGE_PARENT_ENGINE_CHILD") != "approved-child-profile":
        pytest.skip("separate independently supervised benign engine child profile only")

    async def scenario():
        runtime = bare_runtime(tmp_path)
        runtime.limits = BridgeLimits(output_bytes=1024, engine_s=5)
        executable = tmp_path / "benign-engine"
        code = (
            "import os,time\n"
            "for _ in range(256):\n"
            "    os.write(1,b'x'*16384)\n"
            "    os.write(2,b'y'*16384)\n"
            "time.sleep(60)\n"
        )
        executable.write_bytes(b"#!" + os.fsencode(sys.executable) + b"\n" + code.encode())
        executable.chmod(0o500)
        runtime.engine_binary = str(executable)
        failures = []
        runtime.controller = SimpleNamespace(fail=failures.append)
        actual_spawn, paused, processes = asyncio.create_subprocess_exec, [], []

        async def spawn(*args, **kwargs):
            proc = await actual_spawn(*args, **kwargs)
            runtime.engine_processes.add(proc)
            processes.append(proc)
            try:
                async with asyncio.timeout(1):
                    while not (proc.stdout._paused and proc.stderr._paused):
                        await asyncio.sleep(0.001)
                paused.append(True)
                return proc
            except BaseException:
                try:
                    if proc.returncode is None:
                        proc.kill()
                    runtime._close_engine_pipes(proc)
                    async with asyncio.timeout(1):
                        await proc.wait()
                    runtime.engine_processes.discard(proc)
                finally:
                    raise

        monkeypatch.setattr(owned.asyncio, "create_subprocess_exec", spawn)
        try:
            with pytest.raises(BashBridgeError, match="engine or actor output overflow") as raised:
                await runtime.engine_call("benign-overflow")
            assert paused == [True]
            assert failures == [raised.value]
            assert len(processes) == 1 and processes[0].returncode == -9
            assert all(stream._transport.is_closing()
                       for stream in (processes[0].stdout, processes[0].stderr))
            assert runtime.engine_tasks == runtime.engine_processes == set()
            assert not any(isinstance(error, TimeoutError) for error in runtime.cleanup_errors)
        finally:
            if runtime.engine_tasks or runtime.engine_processes:
                _UNRESOLVED_ENGINE_CHILDREN.append(runtime)
    asyncio.run(scenario())
