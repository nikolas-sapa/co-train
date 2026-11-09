"""Fixed isolated SDK worker. SOURCEONLY UNRUN, not production clearance.

Bootstrap executes retained reviewed first-party buffers before imports. This
worker independently retains reviewed direct SDK buffers before SDK import.
Installed dependencies remain host trust; no same-UID atomicity is promised.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import importlib
import importlib.abc
import importlib.util
import inspect
import os
from pathlib import Path
import socket
import stat
import sys
import time
from types import SimpleNamespace

from train.qualification_isolated_contract import (
    APP, SANDBOX, MANIFEST_LIMIT, NS, REQUEST_LIMIT, LaunchDescriptor,
    WorkerFDNumbers, WorkerInputs, WorkerProgramResult, byte_layer, decode_launch,
    decode_manifest, digest, encode_launch, integer, require,
)
from train.qualification_isolated_deadline import _parse_child_args
from train.qualification_isolated_owner import (
    CHUNK, SDK_REQUIRED_KEYS, WORKER_SOURCE_KEYS, _Anchor, _ParentChannel,
    _Registry, _module_name, _stream_file, _regular,
)
from train.qualification_isolated_validation import validation_booking

PROGRAM_MODULE = "train.qualification_isolated_program"
PROGRAM_FUNCTION = "run_prepared_worker"
SDK_VERSION = "1.6.3"
SDK_CLASSES = (("App", "modal.app", "_App"), ("Sandbox", "modal.sandbox._sandbox", "_Sandbox"),
               ("Image", "modal._image", "_Image"))
_SDK = None
_RETAINED_HOSTS = []
_RETAINED_FAILURES = []


class ControlEOF(RuntimeError):
    pass


class WorkerChannel(_ParentChannel):
    def __init__(self, sock, *, session, end_ns):
        super().__init__(sock, session=session, end_ns=end_ns, role="worker")

    @property
    def end_ns(self):
        return self._end_ns

    def shutdown_write(self):
        self.half_close()


def read_payload(fd, limit, *, deadline_ns):
    integer(limit, MANIFEST_LIMIT, 1)
    count, chunks = 0, []
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        require(time.monotonic_ns() < deadline_ns, "fixed payload deadline")
        block = os.read(fd, min(CHUNK, limit - count + 1))
        require(time.monotonic_ns() < deadline_ns, "fixed payload deadline")
        if not block:
            break
        count += len(block)
        require(count <= limit, "payload limit")
        chunks.append(block)
    return byte_layer(b"".join(chunks), limit)


def load_launch(fds, *, deadline_ns):
    raw = read_payload(fds.launch, REQUEST_LIMIT, deadline_ns=deadline_ns)
    return decode_launch(raw), hashlib.sha256(raw).hexdigest()


def load_inputs(fds, launch, *, deadline_ns):
    request = read_payload(fds.request, REQUEST_LIMIT, deadline_ns=deadline_ns)
    manifest = read_payload(fds.manifest, MANIFEST_LIMIT, deadline_ns=deadline_ns)
    require((len(request), hashlib.sha256(request).hexdigest())
            == (launch.request_size, launch.request_sha256), "sealed request bytes")
    require((len(manifest), hashlib.sha256(manifest).hexdigest())
            == (launch.manifest_size, launch.manifest_sha256), "sealed manifest bytes")
    return WorkerInputs(fds, request, decode_manifest(manifest))


def verify_source_pins(launch, *, deadline_ns):
    require(time.monotonic_ns() < deadline_ns, "source custody deadline")
    loaders = [loader for loader in sys.meta_path
               if getattr(loader, "_isolated_firstparty", False) is True]
    require(len(loaders) == 1, "actual verified-buffer bootstrap loader")
    loader = loaders[0]
    require(tuple(p.key for p in launch.source_pins) == WORKER_SOURCE_KEYS,
            "fixed reviewed first-party closure")
    for pin in launch.source_pins:
        require(time.monotonic_ns() < deadline_ns, "source custody deadline")
        path, raw, package = loader.sources[_module_name(pin.key)]
        require(path == str(Path(launch.source_root) / pin.key)
                and len(raw) == pin.size and hashlib.sha256(raw).hexdigest() == pin.sha256,
                "pre-import retained source custody")
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in {"train", "bench", "ptc"}:
            require(module.__spec__ is not None and module.__spec__.loader is loader
                    and module.__file__ == loader.sources[name][0], "executed buffer module origin")
    return len(launch.source_pins)


class _SDKBuffers(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, root, pins, registry, deadline_ns):
        self.sources = {}
        anchor = _Anchor.absolute(registry, root, private=False)
        total = 0
        for pin in pins:
            require(time.monotonic_ns() < deadline_ns, "SDK pre-import pin deadline")
            name = _module_name(pin.key)
            require(name.split(".")[0] in {"modal", "modal_proto", "modal_version"}
                    and name not in self.sources, "original SDK module/alias")
            integer(pin.size, 4 * 1024**2)
            file = anchor.open_file(pin.key, os.O_RDONLY, private=False)
            require(not file.identity[2] & 0o022, "reviewed SDK not writable by others")
            size, sha, raw = _stream_file(file, deadline_ns=deadline_ns, size=pin.size, retain=True)
            require((size, sha) == (pin.size, pin.sha256), "SDK retained actual bytes")
            registry.close(file.record)
            total += size
            require(total <= 32 * 1024**2, "original direct SDK source cap")
            self.sources[name] = str(root / pin.key), raw, pin.key.endswith("/__init__.py")

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in {"modal", "modal_proto", "modal_version"}:
            return None
        require(fullname in self.sources, "unreviewed direct SDK import")
        filename, raw, package = self.sources[fullname]
        return importlib.util.spec_from_file_location(
            fullname, filename, loader=self,
            submodule_search_locations=[str(Path(filename).parent)] if package else None)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        filename, raw, package = self.sources[module.__name__]
        exec(compile(raw, filename, "exec"), module.__dict__)

    def assert_module(self, module):
        require(module.__name__ in self.sources
                and module.__file__ == self.sources[module.__name__][0]
                and module.__spec__ is not None and module.__spec__.loader is self,
                "actual SDK retained-buffer role origin")


def import_sdk(launch, *, deadline_ns):
    require({_module_name(k) for k in SDK_REQUIRED_KEYS}
            <= {_module_name(p.key) for p in launch.sdk_pins}, "reviewed SDK roles")
    require(not any(n.split(".")[0] in {"modal", "modal_proto", "modal_version"}
                    for n in sys.modules), "fresh SDK process")
    registry = _Registry()
    try:
        loader = _SDKBuffers(Path(launch.sdk_root), launch.sdk_pins, registry, deadline_ns)
        # Every direct SDK buffer above is retained BEFORE the first import.
        sys.meta_path.insert(0, loader)
        sys.path.append(launch.sdk_root)  # Explicit dependency root, no site/.pth.
        version = importlib.import_module("modal_version")
        loader.assert_module(version)
        require(version.__version__ == SDK_VERSION, "reviewed SDK version")
        sdk = SimpleNamespace(loader=loader)
        for attribute, module_name, class_name in SDK_CLASSES:
            module = importlib.import_module(module_name)
            loader.assert_module(module)
            cls = vars(module).get(class_name)
            require(isinstance(cls, type) and cls.__module__ == module_name
                    and cls.__name__ == class_name, "original raw async SDK export")
            setattr(sdk, attribute, cls)
        require(inspect.iscoroutinefunction(sdk.Sandbox.create)
                and inspect.iscoroutinefunction(sdk.App.stop)
                and sdk.Sandbox.create.__code__.co_filename
                    == loader.sources["modal.sandbox._sandbox"][0]
                and sdk.App.stop.__code__.co_filename == loader.sources["modal.app"][0]
                and callable(sdk.Image.from_registry), "reviewed raw method roles")
        utils = importlib.import_module("modal._utils.async_utils")
        loader.assert_module(utils)
        sdk.synchronizer = utils.synchronizer
        sdk.synchronize_api = utils.synchronize_api
        require(callable(sdk.synchronize_api)
                and callable(sdk.synchronizer.no_io_translation), "accepted SDK loop bridge")
        require(time.monotonic_ns() < deadline_ns, "SDK READY deadline")
        return sdk
    except BaseException as primary:
        registry.primary = primary
        _RETAINED_FAILURES.append((registry, primary))
        raise
    finally:
        registry.close_all()


class DelegatedHost:
    def __init__(self, *, launch, end_ns):
        require(type(launch) is LaunchDescriptor, "sealed launch")
        self._launch, self._end_ns = launch, integer(end_ns, minimum=1)
        self._app = self._run_context = self._resource = None
        self._app_id = self._sandbox_id = None

    @property
    def resource(self):
        require(self._resource is not None, "actual retained Sandbox")
        return self._resource

    @property
    def app_id(self):
        require(self._app_id is not None, "actual App ID")
        return self._app_id

    @property
    def sandbox_id(self):
        require(self._sandbox_id is not None, "actual Sandbox ID")
        return self._sandbox_id

    @property
    def end_ns(self):
        return self._end_ns

    def require_setup_argv(self, setup_argv):
        require(type(setup_argv) is tuple and setup_argv == self._launch.setup_argv,
                "original approved setup")

    def retain_app(self, *, app, run_context):
        require(self._app is None and app is not None and run_context is not None,
                "actual App/context retained once BEFORE entry await")
        self._app, self._run_context = app, run_context

    def retain_resource(self, resource):
        require(self._resource is None and resource is not None, "actual Sandbox retained once")
        self._resource = resource

    def __reduce_ex__(self, protocol):
        raise TypeError("worker-local actual host")


def digest_app_id(value):
    require(type(value) is str and APP.fullmatch(value) is not None, "actual App ID")
    return value


def require_sandbox_id(value):
    require(type(value) is str and SANDBOX.fullmatch(value) is not None, "actual Sandbox ID")
    return value


def _seconds_left(cutoff):
    remaining = cutoff - time.monotonic_ns()
    if remaining <= 0:
        raise TimeoutError("fixed worker cutoff")
    return remaining / NS  # No epsilon/fresh floor.


async def _controlled_program(*, inputs, launch, host, control, cutoff):
    from train.qualification_isolated_program import run_prepared_worker
    running = stopper = None
    primary = None
    try:
        running = asyncio.create_task(run_prepared_worker(
            inputs=inputs, launch=launch, host=host, control=control))
        stopper = asyncio.create_task(control.receive(
            allowed=frozenset({"STOP"}), end_ns=host.end_ns))
        async with asyncio.timeout(_seconds_left(cutoff)):
            completed, pending = await asyncio.wait(
                (running, stopper), return_when=asyncio.FIRST_COMPLETED)
            if stopper in completed:
                stopper.result()  # EOF/error also aborts the one program.
                raise ControlEOF("parent STOP before worker completion")
            return running.result()
    except BaseException as error:
        primary = error
        raise
    finally:
        # These actual SDK-loop tasks are always awaited here, never detached.
        # A cancellation-resistant SDK may stall until independent OS containment.
        errors = []
        tasks = tuple(t for t in (running, stopper) if t is not None)
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except BaseException as error:
                if error is not primary:
                    errors.append(error)
        if errors:
            failure = RuntimeError("actual SDK-loop task cleanup failed")
            failure.tasks, failure.primary, failure.cleanup = (running, stopper), primary, tuple(errors)
            _RETAINED_FAILURES.append(failure)
            raise failure from primary


async def worker_loop(*, inputs, launch, control):
    sdk = _SDK
    require(sdk is not None and asyncio.get_running_loop()
            is sdk.synchronizer._get_loop(start=False), "actual SDK synchronizer loop")
    lease = control.end_ns
    booking = validation_booking(lease, launch.timing.teardown_ns)
    await control.send("READY", dict(
        request_sha256=launch.request_sha256, manifest_sha256=launch.manifest_sha256,
        launch_sha256=hashlib.sha256(encode_launch(launch)).hexdigest()), end_ns=lease)
    opened = await control.receive(allowed=frozenset({"OPEN"}), end_ns=booking.work_ns)
    end = opened["body"]["end_ns"]
    require(type(end) is int and end == lease, "one committed E, no worker renewal")
    open_permit = digest(opened["body"]["permit"])
    host = DelegatedHost(launch=launch, end_ns=end)
    _RETAINED_HOSTS.append(host)
    image = sdk.Image.from_registry(launch.image_base_reference, secret=None,
                                    setup_dockerfile_commands=[], force_build=False, add_python=None)
    require(type(image) is sdk.Image, "original lazy raw Image")
    app = sdk.App(None, include_source=False)
    context = app.run(detach=False)
    host.retain_app(app=app, run_context=context)
    open_cutoff = min(time.monotonic_ns() + 2 * NS, booking.work_ns)
    async with asyncio.timeout(_seconds_left(open_cutoff)):
        await context.__aenter__()
    host._app_id = digest_app_id(app.app_id)
    await control.send("APP_RETAINED", dict(permit=open_permit, app_id=host.app_id),
                       end_ns=open_cutoff)
    created = await control.receive(allowed=frozenset({"CREATE"}), end_ns=booking.work_ns)
    require(created["body"]["end_ns"] == end, "CREATE same immutable E")
    create_permit = digest(created["body"]["permit"])
    timeout = integer((end - time.monotonic_ns() + NS - 1) // NS, 1800, 1)
    async with asyncio.timeout(_seconds_left(booking.work_ns)):
        sandbox = await sdk.Sandbox.create(
            app=app, image=image, gpu=launch.gpu, cpu=launch.cpu, memory=launch.memory,
            timeout=timeout, block_network=True, secrets=None, network_file_systems={},
            volumes={}, encrypted_ports=(), h2_ports=(), unencrypted_ports=(),
            custom_domain=None, proxy=None, include_oidc_identity_token=False,
            readiness_probe=None, pty=False, pty_info=None, cidr_allowlist=None,
            outbound_cidr_allowlist=None, outbound_domain_allowlist=None,
            _experimental_outbound_policy=None, _experimental_enable_snapshot=False,
            _experimental_persistent=False)
        host.retain_resource(sandbox)  # BEFORE even the timeout context exit await.
    require(type(sandbox) is sdk.Sandbox, "actual raw Sandbox")
    host._sandbox_id = require_sandbox_id(sandbox.object_id)
    await control.send("SANDBOX_RETAINED", dict(
        permit=create_permit, sandbox_id=host.sandbox_id), end_ns=booking.work_ns)
    result = await _controlled_program(
        inputs=inputs, launch=launch, host=host, control=control, cutoff=booking.worker_export_ns)
    require(type(result) is WorkerProgramResult, "fixed C result")
    await control.send("OUTCOME", dict(size=result.outcome_size, sha256=result.outcome_sha256),
                       end_ns=booking.worker_export_ns)
    await control.send("FINISH", {}, end_ns=booking.worker_reap_ns)
    control.shutdown_write()
    # Success exits NOW. Waiting for parent's normal STOP deadlocks V237 booking.
    return result


def _run_on_sdk_loop(sdk, *, inputs, launch, control):
    async def entry():
        return await worker_loop(inputs=inputs, launch=launch, control=control)
    sdk.synchronizer.no_io_translation(entry)
    wrapped = sdk.synchronize_api(entry)
    async def bridge():
        return await wrapped.aio()
    return asyncio.run(bridge())


def worker_main(fds, *, lease_ns=None):
    global _SDK
    require(type(fds) is WorkerFDNumbers and type(lease_ns) is int, "sealed worker facts")
    registry = _Registry()
    channel = None
    code = 1
    primary = None
    try:
        control_record = registry.acquire("descriptor", None, lambda: fds.control)
        for fd in (fds.request, fds.launch, fds.manifest, fds.snapshot_dir,
                   fds.outcome, fds.export_parent):
            record = registry.reserve("descriptor", None)
            registry.attach(record, fd)  # Inherited actual copies BEFORE checks.
        registry.wrap_socket(control_record)
        require(control_record.handle.family == socket.AF_UNIX, "inherited private Unix control")
        for fd in (fds.request, fds.launch, fds.manifest, fds.outcome):
            _regular(os.fstat(fd), True)
            access = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
            require(access == (os.O_RDWR if fd == fds.outcome else os.O_RDONLY),
                    "readonly inputs, mutable O_RDWR outcome")
        for fd in (fds.snapshot_dir, fds.export_parent):
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700
                    and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
                    "private readonly inherited directory")
        require(os.fstat(fds.outcome).st_size == 0, "initial mutable outcome empty")
        launch, launch_hash = load_launch(fds, deadline_ns=lease_ns)
        verify_source_pins(launch, deadline_ns=lease_ns)
        inputs = load_inputs(fds, launch, deadline_ns=lease_ns)
        _SDK = import_sdk(launch, deadline_ns=lease_ns)
        channel = WorkerChannel(control_record.handle, session=launch.session, end_ns=lease_ns)
        _run_on_sdk_loop(_SDK, inputs=inputs, launch=launch, control=channel)
        code = 0
    except BaseException as error:
        primary = registry.primary = error
        _RETAINED_FAILURES.append((registry, error))
    finally:
        try:
            registry.close_all()
        except BaseException as cleanup:
            _RETAINED_FAILURES.append((registry, primary, cleanup))
            code = 1  # Never report clean worker wait0 after a close error.
    return code


def _parse_worker_args(argv):
    return _parse_child_args(argv, "worker", (
        "lease", "control", "request", "launch", "manifest", "snapshot_dir",
        "outcome", "export_parent"))


def main():
    facts = _parse_worker_args(list(sys.argv))
    lease = integer(int(facts.pop("lease")), minimum=1)
    return worker_main(WorkerFDNumbers(**{k: int(v) for k, v in facts.items()}), lease_ns=lease)


if __name__ == "__main__":
    raise SystemExit(main())
