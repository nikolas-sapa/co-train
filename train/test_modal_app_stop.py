"""UNRUN offline unit source. Synthetic SDK doubles do not prove SDK execution."""

import ast
import asyncio
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from train import modal_app_stop as stop
from train import modal_app_stop_launcher as launcher
from train import qualification_watchdog as watchdog


APP_ID = "ap-" + "A" * 22
OTHER_ID = "ap-" + "B" * 22
_PRODUCTION_LOAD_OFFICIAL = stop.load_official
_SDK_NAMESPACES = {"modal", "modal_proto", "modal_version"}


@pytest.fixture(autouse=True)
def no_processes_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline source unit must not launch processes or network")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    # Do not replace socket.socket: asyncio needs its purely local wakeup socket.
    class NoRealSDK(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in _SDK_NAMESPACES:
                raise AssertionError("real SDK import forbidden")
            return None

    cached_sdk = {
        name: module for name, module in sys.modules.items()
        if name.split(".")[0] in _SDK_NAMESPACES
    }
    original_meta_path = sys.meta_path[:]
    original_path = sys.path[:]
    for name in cached_sdk:
        sys.modules.pop(name)
    sys.meta_path.insert(0, NoRealSDK())
    # Only explicit synthetic-loader fixtures may replace this default prohibition.
    monkeypatch.setattr(stop, "load_official", forbidden)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name.split(".")[0] in _SDK_NAMESPACES:
                sys.modules.pop(name)
        sys.modules.update(cached_sdk)
        sys.meta_path[:] = original_meta_path
        sys.path[:] = original_path


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(stop.time, "time", lambda: 1000.0)
    return {
        "expected_app_id": APP_ID, "ownership_confirmed": True,
        "explicitly_trusted": True, "expires_at": 1100.0, "rpc_seconds": 1.0,
    }


def wire(app_id=APP_ID):
    return io.BytesIO(json.dumps({"action": "stop_owned_app", "app_id": app_id}).encode("ascii"))


class FakeBoundary:
    """Ordinary fake client/stub only. Never imports or authenticates Modal."""

    def __init__(self, failure=None):
        self.loads = 0
        self.clients = 0
        self.requests = []
        self.stops = []
        self.failure = failure

    def load(self, config):
        self.loads += 1
        owner = self

        class Client:
            @classmethod
            async def from_env(cls):
                owner.clients += 1
                return SimpleNamespace(_stub=SimpleNamespace(AppStop=owner.stop))

        def request(**kwargs):
            owner.requests.append(kwargs)
            return kwargs

        return Client, request, 17

    async def stop(self, request):
        self.stops.append(request)
        if self.failure is not None:
            raise self.failure


def invoke(config, data=None, boundary=None, claim=None):
    boundary = boundary or FakeBoundary()
    status = stop.run_request(
        wire() if data is None else io.BytesIO(data), config,
        load_boundary=boundary.load, claim=claim or (lambda config: None),
    )
    return status, boundary


@pytest.mark.parametrize("data", [
    b"", b"\0", b"{}", b"[]", b"null", b"true", b"\xff", b"{",
    b" " * (stop.WIRE_LIMIT + 1),
    json.dumps({"action": "stop_owned_app", "app_id": APP_ID, "extra": 1}).encode(),
    json.dumps({"action": "create", "app_id": APP_ID}).encode(),
    json.dumps({"action": "stop_owned_app", "app_id": OTHER_ID}).encode(),
    json.dumps({"action": "stop_owned_app", "app_id": None}).encode(),
    json.dumps({"action": "stop_owned_app", "app_id": "name-not-id"}).encode(),
    json.dumps({"action": "stop_owned_app", "app_id": APP_ID + "\0"}).encode(),
    ('{"action":"stop_owned_app","app_id":"' + APP_ID + '","app_id":"' + APP_ID + '"}').encode(),
    json.dumps({"action": "stop_owned_app", "app_id": APP_ID}).encode() + b"{}",
])
def test_rejected_wire(config, data):
    claims = []
    status, boundary = invoke(config, data, claim=lambda config: claims.append(True))
    assert status != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops), len(claims)) == (0, 0, 0, 0)


@pytest.mark.parametrize("change", [
    {"expires_at": 999.0}, {"expires_at": 1000.0}, {"expires_at": float("nan")},
    {"expires_at": 2801.0}, {"ownership_confirmed": False},
    {"explicitly_trusted": False}, {"expected_app_id": OTHER_ID},
    {"rpc_seconds": 0}, {"rpc_seconds": 31}, {"ownership_confirmed": 1},
])
def test_stale_or_unowned(config, change):
    config.update(change)
    status, boundary = invoke(config)
    assert status != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (0, 0, 0)


def test_exact_stop(config):
    status, boundary = invoke(config)
    assert status == 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 1, 1)
    assert boundary.requests == boundary.stops == [{"app_id": APP_ID, "source": 17}]


@pytest.mark.parametrize("failure", [
    RuntimeError("private SDK error with identity and credentials"),
    TimeoutError("private timeout"), asyncio.CancelledError("private cancellation"),
    KeyboardInterrupt("private interruption"),
])
def test_ambiguous_failure(config, failure, capsys):
    status, boundary = invoke(config, boundary=FakeBoundary(failure))
    assert status != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 1, 1)
    assert capsys.readouterr() == ("", "")


def test_wait_timeout_no_retry(config):
    boundary = FakeBoundary()

    async def delayed(request):
        boundary.stops.append(request)
        await asyncio.Event().wait()

    boundary.stop = delayed
    config["rpc_seconds"] = 0.001
    status, boundary = invoke(config, boundary=boundary)
    assert status != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 1, 1)


def test_expired_during_boundary_load(config):
    boundary = FakeBoundary()

    def load(current):
        result = boundary.load(current)
        current["expires_at"] = 999.0
        return result

    assert stop.run_request(
        wire(), config, load_boundary=load, claim=lambda config: None,
    ) != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 0, 0)


def test_expired_during_request_read(config, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(stop.time, "time", lambda: now[0])
    boundary = FakeBoundary()
    claims = []

    class ExpiringSyntheticStream:
        def read(self, limit):
            now[0] = 1101.0
            return wire().read(limit)

    status = stop.run_request(
        ExpiringSyntheticStream(), config, load_boundary=boundary.load,
        claim=lambda current: claims.append(True),
    )
    assert status != 0
    assert (len(claims), boundary.loads, boundary.clients, len(boundary.stops)) == (0, 0, 0, 0)


def test_default_loader_is_resolved_dynamically(config, monkeypatch):
    boundary = FakeBoundary()
    monkeypatch.setattr(stop, "load_official", boundary.load)
    status = stop.run_request(wire(), config, claim=lambda current: None)
    assert status == 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 1, 1)


@pytest.mark.parametrize("name", [
    "modal", "modal.client", "modal_proto", "modal_proto.api_pb2",
    "modal_version", "modal_version.unreviewed",
])
def test_sdk_fallback_imports_are_blocked(name):
    with pytest.raises(AssertionError, match="real SDK import forbidden"):
        importlib.import_module(name)


def test_boundary_failure_is_private(config, capsys):
    def wrong_boundary(current):
        raise ValueError("synthetic private source/version/origin error")

    assert stop.run_request(
        wire(), config, load_boundary=wrong_boundary, claim=lambda config: None,
    ) != 0
    assert capsys.readouterr() == ("", "")


def test_local_success_never_remote_or_billing_proof():
    command = watchdog._command_result()
    command.update(attempted=True, returncode=0, leader_reaped=True)
    result = watchdog._result("finished", command)
    assert result["local_ok"] is True
    assert result["remote"] == result["billing"] == "UNKNOWN"


def test_main_suppresses_fds_and_requires_isolated_interpreter(config, monkeypatch):
    redirects = []
    monkeypatch.setattr(stop.os, "open", lambda *args: 99)
    monkeypatch.setattr(stop.os, "dup2", lambda source, target: redirects.append((source, target)))
    monkeypatch.setattr(stop.os, "close", lambda fd: None)
    monkeypatch.setattr(stop.sys, "flags", SimpleNamespace(isolated=0, no_site=0))
    assert stop.main(config) != 0
    assert redirects == [(99, 1), (99, 2)]


@pytest.fixture
def synthetic_sdk(tmp_path, monkeypatch):
    # Fixture filesystem ancestry is not production trust evidence.
    monkeypatch.setattr(stop, "trusted_path", lambda *args, **kwargs: None)
    root = tmp_path.resolve() / "sdk"
    root.mkdir()
    sources = {
        "modal": b"", "modal.app": b"", "modal.cli": b"", "modal.cli.app": b"",
        "modal.client": (
            b"class _Client:\n"
            b"    @classmethod\n"
            b"    async def from_env(cls):\n"
            b"        synthetic_calls['clients'] += 1\n"
            b"        client = cls()\n"
            b"        client._stub = client\n"
            b"        return client\n"
            b"    async def AppStop(self, request):\n"
            b"        synthetic_calls['stops'].append(dict(request))\n"
        ),
        "modal_proto": b"",
        "modal_proto.api_pb2": b"class AppStopRequest(dict): pass\nAPP_STOP_SOURCE_CLI = 17\n",
        "modal_version": b"__version__ = '1.6.3'\n",
    }
    packages = {"modal", "modal.cli", "modal_proto"}
    pins = {}
    paths = {}
    for name, source in sources.items():
        base = root.joinpath(*name.split("."))
        path = base / "__init__.py" if name in packages else base.with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
        pins[name] = hashlib.sha256(source).hexdigest()
        paths[name] = path
    return root, pins, paths


@pytest.fixture
def production_loader(config, synthetic_sdk, monkeypatch):
    """Actual product loader, but retained sources/exports are entirely synthetic."""
    root, pins, paths = synthetic_sdk
    config.update(sdk_root=str(root), sdk_pins=pins)
    state = SimpleNamespace(
        calls={"clients": 0, "stops": []}, executed=[], mutate=lambda module: None,
    )
    original_exec = stop._RetainedLoader.exec_module

    def exec_synthetic(loader, module):
        assert loader.path.is_relative_to(root)
        module.__dict__["synthetic_calls"] = state.calls
        original_exec(loader, module)
        state.executed.append(module.__name__)
        state.mutate(module)

    monkeypatch.setattr(stop._RetainedLoader, "exec_module", exec_synthetic)
    monkeypatch.setattr(stop, "load_official", _PRODUCTION_LOAD_OFFICIAL)
    return state


@pytest.mark.parametrize("mutation", [
    "version", "origin", "spec_origin", "client", "method", "request", "source", "loader",
    "required_pin", "submodule_pin", "late_version",
])
def test_production_loader_rejects_synthetic_sdk(
    config, synthetic_sdk, production_loader, mutation, capsys,
):
    root, pins, paths = synthetic_sdk

    def mutate(module):
        if module.__name__ == "modal_version" and mutation == "version":
            module.__version__ = "0.0.0"
        if module.__name__ == "modal.client":
            if mutation == "late_version":
                sys.modules["modal_version"].__version__ = "0.0.0"
            elif mutation == "origin":
                module.__file__ = "/synthetic-wrong/origin.py"
            elif mutation == "spec_origin":
                module.__spec__.origin = "/synthetic-wrong/origin.py"
            elif mutation == "client":
                module._Client = object
            elif mutation == "method":
                module._Client.from_env = lambda: None
            elif mutation == "loader":
                module.__spec__.loader = None
        if module.__name__ == "modal_proto.api_pb2":
            if mutation == "request":
                module.AppStopRequest = object
            elif mutation == "source":
                module.APP_STOP_SOURCE_CLI = None

    production_loader.mutate = mutate
    if mutation == "required_pin":
        pins.pop("modal.app")
    elif mutation == "submodule_pin":
        source = paths["modal.client"].read_bytes() + b"\nimport modal.unreviewed\n"
        paths["modal.client"].write_bytes(source)
        # Synthetic SDK bytes only, never product-source approval.
        pins["modal.client"] = hashlib.sha256(source).hexdigest()
    status = stop.run_request(wire(), config, claim=lambda current: None)
    assert status != 0
    assert production_loader.calls == {"clients": 0, "stops": []}
    if mutation == "required_pin":
        assert production_loader.executed == []
    elif mutation == "version":
        assert production_loader.executed == ["modal_version"]
    else:
        assert "modal_version" in production_loader.executed
    if mutation not in {"version", "required_pin", "submodule_pin"}:
        assert "modal_proto.api_pb2" in production_loader.executed
    assert capsys.readouterr() == ("", "")


def test_production_loader_accepts_synthetic_sdk(config, production_loader):
    status = stop.run_request(wire(), config, claim=lambda current: None)
    assert status == 0
    assert production_loader.executed == [
        "modal_version", "modal", "modal.client", "modal_proto", "modal_proto.api_pb2",
    ]
    assert production_loader.calls == {
        "clients": 1, "stops": [{"app_id": APP_ID, "source": 17}],
    }


def synthetic_exports(sdk):
    modules = []
    for name in ("modal_version", "modal.client", "modal_proto.api_pb2"):
        spec = sdk.find_spec(name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


@pytest.mark.parametrize("mutation", [
    "version", "origin", "spec_origin", "client", "method", "request", "source", "loader",
])
def test_export_guards(synthetic_sdk, mutation):
    root, pins, paths = synthetic_sdk
    sdk = stop.PinnedSDK(root, pins)
    version, client, proto = synthetic_exports(sdk)
    if mutation == "version":
        version.__version__ = "0.0.0"
    elif mutation == "origin":
        client.__file__ = "/wrong/origin.py"
    elif mutation == "spec_origin":
        client.__spec__.origin = "/wrong/origin.py"
    elif mutation == "client":
        client._Client = object
    elif mutation == "method":
        client._Client.from_env = lambda: None
    elif mutation == "request":
        proto.AppStopRequest = object
    elif mutation == "source":
        proto.APP_STOP_SOURCE_CLI = None
    else:
        proto.__spec__.loader = None
    with pytest.raises(ValueError):
        stop.validate_exports(version, client, proto, sdk)


def test_synthetic_exports_accepted_without_client_call(synthetic_sdk):
    root, pins, paths = synthetic_sdk
    sdk = stop.PinnedSDK(root, pins)
    version, client, proto = synthetic_exports(sdk)
    assert stop.validate_exports(version, client, proto, sdk) == (
        client._Client, proto.AppStopRequest, 17,
    )


def test_retained_source(synthetic_sdk):
    root, pins, paths = synthetic_sdk
    sdk = stop.PinnedSDK(root, pins)
    paths["modal_version"].write_bytes(b"raise AssertionError('later bytes executed')\n")
    version = synthetic_exports(sdk)[0]
    assert version.__version__ == "1.6.3"
    with pytest.raises(ValueError, match="source pin mismatch"):
        stop.PinnedSDK(root, pins)
    with pytest.raises(ImportError):
        sdk.find_spec("modal.unreviewed")
    assert sdk.find_spec("unrelated_dependency") is None


def test_missing_sdk_pin(synthetic_sdk):
    root, pins, paths = synthetic_sdk
    pins.pop("modal.client")
    with pytest.raises(ValueError):
        stop.PinnedSDK(root, pins)


def test_missing_sdk_source(synthetic_sdk):
    root, pins, paths = synthetic_sdk
    pins["modal.missing"] = "0" * 64
    with pytest.raises(FileNotFoundError):
        stop.PinnedSDK(root, pins)


def test_one_shot(config, tmp_path, monkeypatch):
    # Test real exclusive claim syscall; fixture ancestry is separately mocked.
    monkeypatch.setattr(stop, "trusted_path", lambda *args, **kwargs: None)
    config["claim_directory"] = str(tmp_path.resolve())
    boundary = FakeBoundary()
    first, _ = invoke(config, boundary=boundary, claim=stop.claim_once)
    second, _ = invoke(config, boundary=boundary, claim=stop.claim_once)
    assert first == 0 and second != 0
    assert (boundary.loads, boundary.clients, len(boundary.stops)) == (1, 1, 1)
    assert stat.S_IMODE((tmp_path / "stop.claim").stat().st_mode) == 0o600


@pytest.fixture
def staging(config, synthetic_sdk, tmp_path, monkeypatch):
    root, pins, paths = synthetic_sdk
    monkeypatch.setattr(launcher, "trusted_path", lambda *args, **kwargs: None)
    source_root = tmp_path.resolve() / "source"
    source_root.mkdir()
    adapter = source_root / "modal_app_stop.py"
    adapter.write_bytes(Path(stop.__file__).read_bytes())
    interpreter = tmp_path.resolve() / "python-pinned"
    interpreter.write_bytes(b"synthetic interpreter, never executed")
    interpreter.chmod(0o500)
    home = tmp_path.resolve() / "explicit-home"
    home.mkdir(mode=0o700)
    return {
        **config, "interpreter": interpreter,
        "interpreter_sha256": hashlib.sha256(interpreter.read_bytes()).hexdigest(),
        "source_root": source_root, "adapter_module": adapter,
        "adapter_sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        "sdk_root": root, "sdk_pins": pins, "private_scratch": tmp_path.resolve(),
        "environment": {"PATH": f"{interpreter.parent}:/usr/bin:/bin", "HOME": str(home)},
    }


def test_staging(staging):
    teardown = launcher.stage_trusted_teardown(**staging)
    executable = Path(teardown._executable)
    source = executable.read_text()
    assert stat.S_IMODE(executable.stat().st_mode) == 0o500
    assert stat.S_IMODE(executable.parent.stat().st_mode) == 0o700
    assert f'exec {staging["interpreter"]} -I -S -B "$0"' in source
    assert dict(teardown._environment) == staging["environment"]
    assert "os.environ" not in source
    ast.parse(source)


@pytest.mark.parametrize("change", [
    {"explicitly_trusted": False}, {"ownership_confirmed": False},
    {"adapter_sha256": "0" * 64}, {"interpreter_sha256": "0" * 64},
    {"sdk_pins": {}}, {"environment": {"PATH": "/bin"}},
    {"environment": {"PATH": "/bin", "HOME": "/private", "MODAL_TOKEN_SECRET": "synthetic"}},
])
def test_staging_rejects_before_staging(staging, change, monkeypatch):
    def no_stage(*args, **kwargs):
        raise AssertionError("invalid config reached staging")

    monkeypatch.setattr(launcher.tempfile, "mkdtemp", no_stage)
    staging.update(change)
    with pytest.raises((ValueError, FileNotFoundError)):
        launcher.stage_trusted_teardown(**staging)


@pytest.mark.parametrize("unsafe", ["ancestor_mode", "ancestor_owner", "leaf_mode", "not_private"])
def test_unsafe_ancestry(monkeypatch, unsafe):
    path = Path("/host-owned/private")

    def info(current):
        mode = stat.S_IFDIR | 0o700
        uid = os.getuid()
        if current == Path("/host-owned") and unsafe == "ancestor_mode":
            mode |= 0o020
        if current == Path("/host-owned") and unsafe == "ancestor_owner":
            uid = max(os.getuid(), 0) + 10000
        if current == path and unsafe == "leaf_mode":
            mode |= 0o002
        if current == path and unsafe == "not_private":
            mode |= 0o040
        return SimpleNamespace(st_mode=mode, st_uid=uid)

    monkeypatch.setattr(Path, "resolve", lambda self: self)
    monkeypatch.setattr(Path, "lstat", info)
    with pytest.raises(ValueError):
        stop.trusted_path(path, directory=True, private=True)


def test_watchdog_integration_is_additive():
    tree = ast.parse(Path(launcher.__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Attribute) and node.func.attr in {"Popen", "arm", "run"}
        for node in calls
    )
    assert any(isinstance(node.func, ast.Name) and node.func.id == "TrustedTeardown" for node in calls)
    source = Path(stop.__file__).read_text()
    assert "await client._stub.AppStop(request)" in source
    assert not any(name in source for name in (
        "AppCreate", "AppLookup", "AppList", "AppGetByDeploymentName", "TaskList",
    ))
