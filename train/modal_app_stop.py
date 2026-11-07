"""Source-only exact-ID stop adapter. Local return never proves remote cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from types import ModuleType
from typing import BinaryIO


WIRE_LIMIT = 1024
SDK_VERSION = "1.6.3"
_APP_ID = re.compile(r"ap-[A-Za-z0-9]{22}")
_REQUIRED = {
    "modal", "modal.app", "modal.cli.app", "modal.client",
    "modal_proto", "modal_proto.api_pb2", "modal_version",
}


def trusted_path(path: Path, *, directory: bool = False, private: bool = False) -> None:
    if (not isinstance(path, Path) or not path.is_absolute()
            or ".." in path.parts or path != path.resolve()):
        raise ValueError("trusted absolute resolved path required")
    for ancestor in reversed(path.parents):
        info = ancestor.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                or info.st_mode & 0o022):
            raise ValueError("untrusted ancestry")
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid not in (0, os.getuid())
            or info.st_mode & 0o022):
        raise ValueError("untrusted source")
    if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("private owned path required")


def retained_source(path: Path, digest: str, *, limit: int = 4 * 1024 * 1024) -> bytes:
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("independent SHA256 required")
    trusted_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid())
                or info.st_mode & 0o022 or info.st_size > limit):
            raise ValueError("untrusted source")
        source = stream.read(limit + 1)
    if len(source) > limit or hashlib.sha256(source).hexdigest() != digest:
        raise ValueError("source pin mismatch")
    return source


def validate_owner(config: Mapping[str, object]) -> None:
    now = time.time()
    expires = config.get("expires_at")
    if (config.get("explicitly_trusted") is not True
            or config.get("ownership_confirmed") is not True
            or type(config.get("expected_app_id")) is not str
            or _APP_ID.fullmatch(config["expected_app_id"]) is None
            or type(expires) not in (int, float) or not math.isfinite(expires)
            or not 0 < expires - now <= 1800):
        raise ValueError("fresh independent owned identity required")
    timeout = config.get("rpc_seconds")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 30):
        raise ValueError("bounded local wait required")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def read_request(stream: BinaryIO, expected_app_id: str) -> str:
    wire = stream.read(WIRE_LIMIT + 1)
    if not wire or len(wire) > WIRE_LIMIT or b"\0" in wire:
        raise ValueError("invalid request")
    request = json.loads(wire.decode("ascii"), object_pairs_hook=_unique_pairs)
    if (type(request) is not dict or set(request) != {"action", "app_id"}
            or request["action"] != "stop_owned_app"
            or type(request["app_id"]) is not str
            or _APP_ID.fullmatch(request["app_id"]) is None
            or request["app_id"] != expected_app_id):
        raise ValueError("invalid request")
    return request["app_id"]


class _RetainedLoader(importlib.abc.Loader):
    def __init__(self, path: Path, source: bytes) -> None:
        self.path = path
        self.source = source

    def create_module(self, spec: object) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        exec(compile(self.source, str(self.path), "exec"), module.__dict__)


class PinnedSDK(importlib.abc.MetaPathFinder):
    """Only direct SDK Python sources are pinned; dependencies remain host trust."""

    def __init__(self, root: Path, pins: Mapping[str, str]) -> None:
        trusted_path(root, directory=True)
        if not _REQUIRED.issubset(pins) or len(pins) > 2048:
            raise ValueError("complete reviewed SDK source pins required")
        self.sources: dict[str, tuple[Path, bytes, bool]] = {}
        total = 0
        for name, digest in pins.items():
            if (type(name) is not str
                    or not re.fullmatch(r"(modal|modal_proto|modal_version)(\.[A-Za-z_]\w*)*", name)):
                raise ValueError("invalid SDK module pin")
            base = root.joinpath(*name.split("."))
            package = base.is_dir()
            path = base / "__init__.py" if package else base.with_suffix(".py")
            source = retained_source(path, digest)
            total += len(source)
            if total > 32 * 1024 * 1024:
                raise ValueError("SDK source set too large")
            self.sources[name] = path, source, package

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> object:
        if fullname.split(".")[0] not in {"modal", "modal_proto", "modal_version"}:
            return None
        if fullname not in self.sources:
            raise ImportError("unpinned SDK module")
        filename, source, package = self.sources[fullname]
        return importlib.util.spec_from_file_location(
            fullname, filename, loader=_RetainedLoader(filename, source),
            submodule_search_locations=[str(filename.parent)] if package else None,
        )


def validate_exports(
    version: ModuleType, client: ModuleType, proto: ModuleType, sdk: PinnedSDK,
) -> tuple[object, object, int]:
    for module in (version, client, proto):
        expected = sdk.sources.get(module.__name__)
        if (expected is None or module.__file__ != str(expected[0])
                or module.__spec__ is None
                or module.__spec__.origin != str(expected[0])
                or not isinstance(module.__spec__.loader, _RetainedLoader)
                or module.__spec__.loader.path != expected[0]
                or module.__spec__.loader.source != expected[1]):
            raise ValueError("official module origin required")
    if getattr(version, "__version__", None) != SDK_VERSION:
        raise ValueError("official SDK version mismatch")
    client_type = getattr(client, "_Client", None)
    method = getattr(client_type, "from_env", None)
    function = getattr(method, "__func__", None)
    request_type = getattr(proto, "AppStopRequest", None)
    source = getattr(proto, "APP_STOP_SOURCE_CLI", None)
    if (not isinstance(client_type, type) or client_type.__module__ != "modal.client"
            or client_type.__name__ != "_Client"
            or not asyncio.iscoroutinefunction(function)
            or function.__qualname__ != "_Client.from_env"
            or function.__code__.co_filename != client.__file__
            or not callable(request_type)
            or getattr(request_type, "__module__", None) != "modal_proto.api_pb2"
            or type(source) is not int):
        raise ValueError("original official stop exports required")
    return client_type, request_type, source


def load_official(config: Mapping[str, object]) -> tuple[object, object, int]:
    sdk = PinnedSDK(Path(config["sdk_root"]), config["sdk_pins"])
    if any(name.split(".")[0] in {"modal", "modal_proto", "modal_version"} for name in sys.modules):
        raise ValueError("fresh SDK process required")
    sys.meta_path.insert(0, sdk)
    # -S suppresses site/.pth processing. Only this explicit dependency root is added.
    sys.path.append(str(config["sdk_root"]))
    version = importlib.import_module("modal_version")
    if getattr(version, "__version__", None) != SDK_VERSION:
        raise ValueError("official SDK version mismatch")
    client = importlib.import_module("modal.client")
    proto = importlib.import_module("modal_proto.api_pb2")
    return validate_exports(version, client, proto, sdk)


async def _stop_once(
    config: Mapping[str, object], app_id: str, boundary: tuple[object, object, int],
) -> None:
    try:
        client_type, request_type, source = boundary
        validate_owner(config)
        request = request_type(app_id=app_id, source=source)
        client = await client_type.from_env()
        validate_owner(config)
        # Original Modal 1.6.3 CLI route, modal/cli/app.py:407-408.
        await client._stub.AppStop(request)
    except BaseException:
        # Keep private exceptions out of asyncio's task-shutdown diagnostics.
        raise RuntimeError("local stop failed") from None


def claim_once(config: Mapping[str, object]) -> None:
    directory = Path(config["claim_directory"])
    trusted_path(directory, directory=True, private=True)
    fd = os.open(
        directory / "stop.claim", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
    )
    os.close(fd)


def run_request(
    stream: BinaryIO, config: Mapping[str, object], *,
    load_boundary: Callable | None = None, claim: Callable = claim_once,
) -> int:
    """Unit injection boundary is not actual SDK execution proof."""
    try:
        validate_owner(config)
        app_id = read_request(stream, config["expected_app_id"])
        validate_owner(config)
        claim(config)
        boundary = (load_official if load_boundary is None else load_boundary)(config)
        validate_owner(config)
        timeout = min(config["rpc_seconds"], config["expires_at"] - time.time())
        if timeout <= 0:
            return 1
        asyncio.run(asyncio.wait_for(_stop_once(config, app_id, boundary), timeout))
        return 0
    except BaseException:
        return 1


def main(config: Mapping[str, object]) -> int:
    try:
        # Suppress SDK logging and native fd writes, not just Python print calls.
        fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(fd, 1)
            os.dup2(fd, 2)
        finally:
            os.close(fd)
        if (not sys.flags.isolated or not sys.flags.no_site
                or not sys.dont_write_bytecode
                or Path(sys.executable).resolve() != Path(config["interpreter"])):
            return 1
        retained_source(
            Path(config["interpreter"]), config["interpreter_sha256"], limit=128 * 1024 * 1024,
        )
        return run_request(sys.stdin.buffer, config)
    except BaseException:
        return 1
