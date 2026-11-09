"""V172/V186 finite runner tests, UNRUN. No SDK/processes."""

import asyncio
import builtins
from contextlib import nullcontext
from dataclasses import replace
import hashlib
from importlib.machinery import PathFinder
import io
import os
from pathlib import Path
import stat
import sys
import threading
from types import SimpleNamespace

import pytest

from train import qualification_engineering_run as r
from train import qualification_modal_transport as t

BINDING = "b" * 64
SETUP = ("/usr/local/bin/python3.12", "-m", "pip", "install", "--no-index",
         "--find-links", "/opt/qualification/wheels", "approved")


@pytest.fixture
def tmp_path(tmp_path):
    # macOS's system temporary path can itself contain /var -> /private/var.
    # Tests select a canonical fixture root, production refuses caller aliases.
    return tmp_path.resolve()


class Host:
    preparation_deadline = 200.0
    app_id, sandbox_id = "ap-issued", "sb-issued"
    resource = None

    def __init__(self, fail=None, end=1800.0):
        self.fail, self.end, self.calls = fail, end, []

    def check(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise ValueError(name)

    def require_active(self, request):
        self.check("active")

    def require_uploads(self, uploads):
        self.check("uploads")

    def require_setup_argv(self, argv):
        self.check("setup")

    async def open_app(self, *, deadline):
        self.check("open")
        assert deadline == self.preparation_deadline

    def begin_gpu_window(self):
        self.check("arm")
        return self.end

    async def create_once(self, *, deadline):
        self.check("create")
        self.resource = object()
        return self.resource

    async def stop_owned(self, *, deadline):
        self.calls.append(("stop", deadline))
        await asyncio.sleep(0)
        self.calls.append("stopped")


def upload(path, body, root="source", key="tiny"):
    path.write_bytes(body)
    return t.PlannedUpload(root, key, len(body), hashlib.sha256(body).hexdigest(), path)


def stops(host):
    return [call for call in host.calls if isinstance(call, tuple)]


def test_unauthorized_zero_bridge_and_lifecycle(monkeypatch, tmp_path):
    host = Host("active")
    def forbidden():
        raise AssertionError("bridge loader entered")
    monkeypatch.setattr(r, "_load_bridge", forbidden)
    with pytest.raises(ValueError, match="active"):
        asyncio.run(r.run_engineering_once(object(), host=host, uploads=(),
                    setup_argv=SETUP, export_root=tmp_path / "export"))
    assert host.calls == ["active"]


def test_binding_refusal_zero_bridge(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "_load_bridge", lambda: pytest.fail("bridge loaded"))
    for failure in ("uploads", "setup"):
        host = Host(failure)
        with pytest.raises(ValueError, match=failure):
            asyncio.run(r.run_engineering_once(object(), host=host, uploads=(),
                        setup_argv=SETUP, export_root=tmp_path / "export"))
        assert not any(name in host.calls for name in ("open", "arm", "create"))


def test_upload_snapshot_refusals_zero_lifecycle(tmp_path):
    original = upload(tmp_path / "original", b"tiny")
    plain = upload(tmp_path / "plain", b"tiny")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(original.path)
    hardlink = tmp_path / "hardlink"
    os.link(original.path, hardlink)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    parent = tmp_path / "alias"
    parent.symlink_to(tmp_path, target_is_directory=True)
    cases = (replace(plain, sha256="0" * 64), replace(plain, size=5),
             replace(original, path=symlink), replace(original, path=hardlink),
             replace(original, path=fifo), replace(plain, path=parent / "plain"),
             replace(original, path=tmp_path / "missing"))
    for item in cases:
        with pytest.raises((ValueError, OSError)):
            with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0):
                pytest.fail("unvalidated source admitted")
    assert list(tmp_path.glob(".qualification-snapshot-*")) == []


def test_snapshot_retained_not_caller_file(tmp_path):
    item = upload(tmp_path / "caller", b"retained")
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        snapshot = frozen.items[0]
        item.path.unlink()
        item.path.write_bytes(b"changed!")
        assert b"".join(snapshot.chunks()) == b"retained"
        assert stat.S_IMODE(os.fstat(snapshot.fd).st_mode) == 0o600
        assert os.fstat(snapshot.fd).st_nlink == 1
        assert stat.S_IMODE(os.stat(frozen.directory, follow_symlinks=False).st_mode) == 0o700
        assert frozen.snapshot_bytes == 8 and frozen.free_bytes_before >= 8
    assert not frozen.directory.exists()


def test_fresh_disk_includes_output_reserve_before_snapshot(monkeypatch, tmp_path):
    item = upload(tmp_path / "caller", b"tiny")
    monkeypatch.setattr(r.os, "fstatvfs", lambda fd: SimpleNamespace(f_bavail=4, f_frsize=1))
    with pytest.raises(ValueError, match="disk budget"):
        with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0,
                            reserved_bytes=1):
            pytest.fail("cap+1 disk requirement admitted")
    assert list(tmp_path.glob(".qualification-snapshot-*")) == []


def test_request_exact_original_schema(monkeypatch, tmp_path):
    from train import native_qualification as native
    # The real schema builder is exercised by the parent's original native suite.
    # Here the already-inspected original export is controlled, not invented.
    payload = b'{"schema":"native-sql-worker-v1","assets":[],"tasks":[],"image_digest":"x","bounds":{}}'
    request = object()
    monkeypatch.setattr(native, "_prepare_worker_transport", lambda value: (payload, ()))
    item = upload(tmp_path / "request", payload, "request", "request.json")
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        r._validate_request_snapshot(request, frozen.items, native)
    changed = payload.replace(b'"image_digest":"x"', b'"image_digest":"y"')
    item = upload(tmp_path / "request", changed, "request", "request.json")
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        with pytest.raises(ValueError, match="original worker"):
            r._validate_request_snapshot(request, frozen.items, native)


def test_bootstrap_no_installed_module_or_roots(monkeypatch, tmp_path):
    # Execute the actual generated first-RPC bootstrap in a private filesystem
    # root, with the unchanged accepted stdlib B source. No process or SDK.
    source = Path(t.__file__).with_name("qualification_file_rpc.py").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    argv = t._bootstrap_argv(source, digest, initial=True,
                            directories=("/opt/qualification/source/train",))
    assert argv[:2] == ("/usr/local/bin/python3.12", "-c")
    assert repr(source) in argv[2]
    assert "/var/tmp/qualification/output" not in t._CREATED_ROOTS
    assert "/var/tmp/qualification/output" in argv[2]
    actual_open = os.open
    def rooted_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == "/" and dir_fd is None:
            return actual_open(tmp_path, flags, mode)
        return actual_open(path, flags, mode, dir_fd=dir_fd)
    body = b"tiny"
    item = upload(tmp_path / "upload-tiny", body, "source", "train/tiny.py")
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        request = b"".join(t.rpc_put_frames(
            item.root, item.key, item.size, item.sha256, frozen.items[0]))
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(request)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=out))
    monkeypatch.setattr(sys, "argv", ["controlled-bootstrap"])
    monkeypatch.setattr(os, "open", rooted_open)
    assert not (tmp_path / "opt").exists() and not (tmp_path / "var").exists()
    original_import = builtins.__import__
    def no_installed_train(name, *args, **kwargs):
        if name == "train" or name.startswith("train."):
            raise ModuleNotFoundError("no installed train/RPC module")
        return original_import(name, *args, **kwargs)
    with pytest.raises(SystemExit) as exit_info:
        # No import of train/RPC in the bootstrap; source is compile/exec data.
        with monkeypatch.context() as isolated:
            isolated.setattr(builtins, "__import__", no_installed_train)
            exec(compile(argv[2], "<fixed-bootstrap-test>", "exec"), {"__name__": "__main__"})
    assert exit_info.value.code == 0
    t.parse_put_ack(out.getvalue())
    assert (tmp_path / "opt/qualification/source/train/tiny.py").read_bytes() == body
    assert not (tmp_path / "var/tmp/qualification/output").exists()
    assert (tmp_path / "var/tmp/qualification/evidence").is_dir()
    # The fixed materializer also starts at "/" and never imports train.
    actual_input = tmp_path / "var/tmp/qualification/request-input/request.json"
    actual_input.write_bytes(b'{"tiny":"request"}')
    request_hash = hashlib.sha256(actual_input.read_bytes()).hexdigest()
    t._materialize_request(request_hash)
    assert (tmp_path / "var/tmp/qualification/request.json").read_bytes() == actual_input.read_bytes()
    assert not (tmp_path / "var/tmp/qualification/output").exists()
    with pytest.raises(FileExistsError):
        t._materialize_request(request_hash)
    existing_output = tmp_path / "var/tmp/qualification/output"
    existing_output.mkdir()
    with pytest.raises(ValueError, match="existing native output"):
        t._initialize_roots(initial=True)
    assert existing_output.is_dir()
    with pytest.raises(ValueError):
        t._bootstrap_argv(source, "0" * 64, initial=True)
    with pytest.raises(ValueError):
        t._bootstrap_argv(b"", hashlib.sha256(b"").hexdigest(), initial=True)


def test_cleanup_all_early_failures(monkeypatch, tmp_path):
    prepared = SimpleNamespace()
    for failure in ("open", "arm", "constructor", "create"):
        host = Host(failure)
        def constructor(*args, **kwargs):
            if failure == "constructor":
                raise ValueError("constructor")
            return SimpleNamespace()
        monkeypatch.setattr(t, "ModalExecTransport", constructor)
        with pytest.raises((ValueError, AttributeError)):
            asyncio.run(r._run_engineering_once_impl(
                object(), host=host, uploads=(), setup_argv=SETUP,
                export_root=tmp_path / "export", clock=lambda: 100.0, prepared=prepared))
        assert len(stops(host)) == 1 and host.calls[-1] == "stopped"
        assert stops(host)[0][1] == (100.0 if failure in ("open", "arm") else 1800.0)


def test_window_reserves_and_1800_ceiling(monkeypatch, tmp_path):
    assert r._stage_deadlines(1800.0, 0.0) == (1650.0, 1710.0, 1770.0)
    with pytest.raises(ValueError, match="1800"):
        r._stage_deadlines(1801.0, 0.0)
    assert r._stage_deadlines(1900.0, 100.0) == (1750.0, 1810.0, 1870.0)
    monkeypatch.setattr(t, "ModalExecTransport", PipelineTransport)
    monkeypatch.setattr(PipelineTransport, "failure", None)
    request = SimpleNamespace(bounds=SimpleNamespace(artifact_bytes=1000))
    accepted = Host(end=1900.0)
    result = asyncio.run(r._run_engineering_once_impl(
        request, host=accepted, uploads=(), setup_argv=SETUP, export_root=tmp_path / "accepted",
        clock=lambda: 100.0, prepared=prepared_stub()))
    assert len(result.exports) == 9 and accepted.calls.count("create") == 1
    assert stops(accepted) == [("stop", 1900.0)]
    refused = Host(end=1901.0)
    with pytest.raises(ValueError, match="1800"):
        asyncio.run(r._run_engineering_once_impl(
            request, host=refused, uploads=(), setup_argv=SETUP, export_root=tmp_path / "refused",
            clock=lambda: 100.0, prepared=prepared_stub()))
    assert "create" not in refused.calls and stops(refused) == [("stop", 100.0)]


def private(op):
    attempt = r._attempt_id(BINDING, "ap-issued", "sb-issued")
    return dict(v=1, op=op, request_sha256=BINDING, attempt_id=attempt,
                app_id="ap-issued", sandbox_id="sb-issued")


def remote_dependencies(monkeypatch, tmp_path):
    """Run actual original worker/_run_child code, replace only OS dependencies."""
    from train import native_qualification as native
    request_file = tmp_path / "request.json"
    request_file.write_bytes(b"{}")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    bounds = SimpleNamespace(lifetime_seconds=100, output_bytes_per_phase=100,
                             artifact_bytes=100000)
    request = SimpleNamespace(output_dir=tmp_path / "output", bounds=bounds)
    monkeypatch.setattr(r, "_EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(r, "_REMOTE_REQUEST_FILE", request_file)
    monkeypatch.setattr(native, "_REQUEST_FILE", request_file)
    monkeypatch.setattr(native, "_decode_worker_transport", lambda raw: {"bounds": {}})
    monkeypatch.setattr(native, "_request_from_wire", lambda doc: request)
    monkeypatch.setattr(native, "_validate_request", lambda req: None)
    monkeypatch.setattr(native, "_bounds_from_wire", lambda value: bounds)
    monkeypatch.setattr(native, "_request_binding", lambda req: BINDING)
    monkeypatch.setattr(native, "_path", lambda path: path)
    monkeypatch.setattr(native, "_owned_subreaper", nullcontext)
    monkeypatch.setattr(native, "_output_size", lambda *args: 0)
    monkeypatch.setattr(native, "_phase_argv", lambda *args: ("controlled",))
    monkeypatch.setattr(native, "time", SimpleNamespace(monotonic=lambda: 100.0, sleep=lambda n: None))
    class ChildOS:
        WNOWAIT = getattr(os, "WNOWAIT", 0x1000000)
        WEXITED = getattr(os, "WEXITED", 4)
        WNOHANG = getattr(os, "WNOHANG", 1)
        CLD_EXITED = getattr(os, "CLD_EXITED", 1)
        P_PID = getattr(os, "P_PID", 1)
        def __getattr__(self, name):
            return getattr(os, name)
        def set_blocking(self, *args):
            pass
        def read(self, fd, count):
            assert fd == 999999
            return b""
        def waitid(self, *args):
            return SimpleNamespace(si_code=self.CLD_EXITED, si_status=0)
        def waitpid(self, *args):
            raise ChildProcessError()
        def killpg(self, pid, sig):
            if sig == 0:
                raise ProcessLookupError()
    monkeypatch.setattr(native, "os", ChildOS())
    launched = []
    class Child:
        returncode = None
        def __init__(self):
            self.pid = 400 + len(launched)
            self.stdout = SimpleNamespace(fileno=lambda: 999999, close=lambda: None)
        def wait(self):
            self.returncode = 0
            return self.returncode
    def popen(*args, **kwargs):
        assert (r._EVIDENCE_ROOT / r._LATCH_KEY).exists()
        child = Child()
        launched.append(child)
        return child
    monkeypatch.setattr(native, "subprocess", SimpleNamespace(
        Popen=popen, DEVNULL=native.subprocess.DEVNULL, PIPE=native.subprocess.PIPE,
        STDOUT=native.subprocess.STDOUT))
    class Selector:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def register(self, *args):
            pass
        def unregister(self, *args):
            pass
        def select(self, timeout):
            return [(SimpleNamespace(fd=999999, fileobj=None), 1)]
    monkeypatch.setattr(native, "selectors",
                        SimpleNamespace(DefaultSelector=Selector, EVENT_READ=1))
    monkeypatch.setattr(native, "_read_phase_observation",
                        lambda req, phase: dict(pid=399 + phase, parent_pid=os.getpid()))
    monkeypatch.setattr(native, "_check_phase_observations", lambda observations: None)
    return native, request, evidence, launched


def input_document(monkeypatch, doc):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(r._canonical_json(doc))))


def test_native_mode_actual_observer_and_latch(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="--native or --verify"):
        r.main(["--other"])
    with pytest.raises(ValueError):
        r.main(["--native", "--verify"])
    native, request, evidence, launched = remote_dependencies(monkeypatch, tmp_path)
    target = native._run_child.__code__
    input_document(monkeypatch, private("native-attempt"))
    assert r.main(["--native"]) == 0
    assert native._run_child.__code__ is target and len(launched) == 2
    assert sys.getprofile() is None
    observation = r._load_remote_json(evidence / r._OBSERVATIONS_KEY, limit=1048576)
    assert [row["pid"] for row in observation["observations"]] == [400, 401]
    assert [row["returncode"] for row in observation["observations"]] == [0, 0]
    input_document(monkeypatch, private("native-attempt"))
    with pytest.raises(OSError):
        r.main(["--native"])
    assert len(launched) == 2


def test_native_mode_prior_profiler_and_failure_restore(monkeypatch, tmp_path):
    native, request, evidence, launched = remote_dependencies(monkeypatch, tmp_path)
    profiler = lambda *args: None
    input_document(monkeypatch, private("native-attempt"))
    sys.setprofile(profiler)
    try:
        with pytest.raises(ValueError, match="preexisting"):
            r.main(["--native"])
        assert sys.getprofile() is profiler
    finally:
        sys.setprofile(None)
    assert len(launched) == 0
    # Separate fresh evidence directory, no deletion/reuse of attempt markers.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setattr(r, "_EVIDENCE_ROOT", fresh)
    def failure(path):
        raise RuntimeError("worker failed")
    monkeypatch.setattr(native, "_worker_main", failure)
    input_document(monkeypatch, private("native-attempt"))
    with pytest.raises(RuntimeError):
        r.main(["--native"])
    assert sys.getprofile() is None and not (fresh / r._OBSERVATIONS_KEY).exists()


def verifier_setup(monkeypatch, tmp_path):
    native, request, evidence, launched = remote_dependencies(monkeypatch, tmp_path)
    input_document(monkeypatch, private("native-attempt"))
    assert r.main(["--native"]) == 0
    request.output_dir.mkdir()
    for phase in (1, 2):
        directory = request.output_dir / f"checkpoint-{phase}"
        directory.mkdir()
        for key in ("native-observation.json", "trainer_state.json", "optimizer.pt"):
            (directory / key).write_bytes(b"{}" if key.endswith(".json") else b"tiny")
    # Mode and accepted helper both run. Only the original tensor leaf is
    # controlled; this is NOT evidence that tensor verification actually passed.
    calls = []
    def verify(req, result):
        calls.append(result)
        assert req is request and result.phase_returncodes == (0, 0)
        assert type(result.service_handle) is r.IssuedIdentity
        assert result.service_handle.app_id == "ap-issued"
        return tuple(request.output_dir / f"checkpoint-{p}" for p in (1, 2))
    monkeypatch.setattr(native, "QualificationRequest", SimpleNamespace)
    monkeypatch.setattr(native, "_check_exported_artifacts", verify)
    monkeypatch.setattr(native, "_validate_phase_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(native, "_output_size", lambda *args: 16)
    return native, request, evidence, calls


def test_verify_mode_original_once(monkeypatch, tmp_path):
    native, request, evidence, calls = verifier_setup(monkeypatch, tmp_path)
    stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=stdout, write=lambda value: len(value)))
    input_document(monkeypatch, private("remote-verify"))
    assert r.main(["--verify"]) == 0 and len(calls) == 1
    index = t.parse_manifest_body(stdout.getvalue(), max_bytes=3 * 1048576, max_members=3, max_depth=0)
    assert len(index) == 3 and (evidence / r._RECEIPT_KEY).exists()
    receipt = r._load_remote_json(evidence / r._RECEIPT_KEY, limit=1048576)
    assert len(receipt["manifest"]) == 6 and receipt["phase_returncodes"] == [0, 0]


def test_verify_mode_refusal_and_failure_no_receipt(monkeypatch, tmp_path):
    native, request, evidence, calls = verifier_setup(monkeypatch, tmp_path)
    bad = private("remote-verify")
    bad["app_id"] = "ap-foreign"
    input_document(monkeypatch, bad)
    with pytest.raises(ValueError):
        r.main(["--verify"])
    assert calls == [] and not (evidence / r._RECEIPT_KEY).exists()
    def failure(*args):
        raise RuntimeError("full verifier refused")
    monkeypatch.setattr(native, "_check_exported_artifacts", failure)
    input_document(monkeypatch, private("remote-verify"))
    with pytest.raises(RuntimeError):
        r.main(["--verify"])
    assert not (evidence / r._RECEIPT_KEY).exists()


def test_all_artifacts_exported(monkeypatch, tmp_path):
    data = {f"checkpoint-{p}/{key}": b"tiny-" + bytes([p])
            for p in (1, 2) for key in ("weights.bin", "optimizer.pt", "trainer_state.json")}
    entries = tuple(dict(key=key, size=len(body), sha256=hashlib.sha256(body).hexdigest())
                    for key, body in sorted(data.items()))
    class Wire:
        async def get_to(self, root, entry, sink, *, deadline):
            assert root == "output"
            sink(data[entry["key"]][:2])
            sink(data[entry["key"]][2:])
    async def run():
        with r._ExportTree(tmp_path / "export") as tree:
            return await r._export_artifacts(Wire(), tree, entries, deadline=200.0)
    exports = asyncio.run(run())
    assert len(exports) == len(data) == 6
    for item in exports:
        assert item.path.read_bytes() == data[item.name]
        assert hashlib.sha256(item.path.read_bytes()).hexdigest() == item.sha256


def test_anchored_export_alias_and_short_write(monkeypatch, tmp_path):
    actual_write = os.write
    monkeypatch.setattr(r.os, "write", lambda fd, body: actual_write(fd, body[:2]))
    wrote = False
    with pytest.raises((OSError, ValueError)):
        with r._ExportTree(tmp_path / "export") as tree:
            result = tree.write_bytes("a/b", b"complete")
            assert result.size == 8 and result.path.read_bytes() == b"complete"
            wrote = True
            old = tmp_path / "moved"
            (tmp_path / "export").rename(old)
            (tmp_path / "export").symlink_to(old, target_is_directory=True)
            tree.write_bytes("another", b"refuse")
    assert wrote
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        with r._ExportTree(alias / "new"):
            pytest.fail("redirected ancestor admitted")


class InlineBridge:
    def __init__(self):
        self.dispatches = 0
        self.marked = []

    def no_io_translation(self, closure):
        self.marked.append(closure)
        return closure

    def wrap(self, closure):
        assert closure in self.marked
        async def aio():
            self.dispatches += 1
            return await closure()
        return SimpleNamespace(aio=aio)


def test_bridge_aio_identity_and_loop(monkeypatch):
    bridge = InlineBridge()
    monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, bridge.wrap))
    marker = object()
    async def work():
        return marker
    async def run():
        return await r._dispatch_sdk(work, preparation_deadline=200.0, clock=lambda: 100.0)
    assert asyncio.run(run()) is marker and bridge.dispatches == 1


def test_cancel_before_admission_no_impl(monkeypatch):
    bridge = InlineBridge()
    calls = []
    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()
        def wrap(closure):
            async def aio():
                entered.set()
                await asyncio.wait_for(release.wait(), 1.0)
                return await closure()
            return SimpleNamespace(aio=aio)
        monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, wrap))
        async def work():
            calls.append("impl")
        task = asyncio.create_task(r._dispatch_sdk(work, preparation_deadline=200.0,
                                                  clock=lambda: 100.0))
        await asyncio.wait_for(entered.wait(), 1.0)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert calls == []


def test_cancel_after_admission_cleanup_joined(monkeypatch):
    bridge = InlineBridge()
    monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, bridge.wrap))
    events = []
    async def run():
        admitted, cleanup, cleanup_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def work():
            try:
                admitted.set()
                await asyncio.Event().wait()
            finally:
                events.append("stop")
                cleanup_started.set()
                await asyncio.wait_for(cleanup.wait(), 1.0)
                events.append("stopped")
        task = asyncio.create_task(r._dispatch_sdk(work, preparation_deadline=200.0,
                                                  clock=lambda: 100.0))
        await asyncio.wait_for(admitted.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 1.0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert events == ["stop", "stopped"]
    asyncio.run(run())


def test_admission_and_cleanup_bounded(monkeypatch):
    bridge = InlineBridge()
    async def never():
        await asyncio.Event().wait()
    monkeypatch.setattr(r, "_load_bridge",
                        lambda: (bridge, lambda closure: SimpleNamespace(aio=never)))
    async def run():
        loop = asyncio.get_running_loop()
        before = loop.time()
        with pytest.raises(TimeoutError, match="admission"):
            await r._dispatch_sdk(never, preparation_deadline=before + 0.02, clock=loop.time)
        assert loop.time() - before < 1.0
    asyncio.run(run())
    class Stalled(Host):
        async def stop_owned(self, *, deadline):
            self.calls.append(("stop", deadline))
            try:
                await asyncio.Event().wait()
            finally:
                self.calls.append("stop-cancelled")
    async def cleanup():
        loop = asyncio.get_running_loop()
        before = loop.time()
        host = Stalled()
        with pytest.raises(r.SDKBridgeIncomplete):
            await r._stop_once(host, deadline=before, clock=loop.time)
        assert loop.time() - before < 1.0
        assert len(stops(host)) == 1 and host.calls[-1] == "stop-cancelled"
    asyncio.run(cleanup())


def test_host_imports_no_tensor_stack():
    import ast
    forbidden = {"torch", "numpy", "peft", "transformers"}
    for module in (r, t):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {part.name.split(".")[0] for part in node.names} & forbidden
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_full_pipeline_failure_no_retry(monkeypatch, tmp_path):
    calls = []
    class BrokenTransport:
        def __init__(self, *args, **kwargs):
            calls.append("transport")
        @property
        def sandbox(self):
            return None
        @sandbox.setter
        def sandbox(self, value):
            calls.append("bound")
        def bind_runtime(self, **kwargs):
            calls.append("bind")
        async def stage_uploads(self, *args, **kwargs):
            calls.append("stage")
            raise ValueError("controlled stage failure")
    monkeypatch.setattr(t, "ModalExecTransport", BrokenTransport)
    host = Host()
    prepared = SimpleNamespace(rpc_source=b"source", rpc_sha256="0" * 64,
                               request_sha256="0" * 64, items=())
    with pytest.raises(ValueError, match="stage failure"):
        asyncio.run(r._run_engineering_once_impl(
            object(), host=host, uploads=(), setup_argv=SETUP,
            export_root=tmp_path / "export", clock=lambda: 100.0, prepared=prepared))
    assert calls.count("stage") == 1 and len(stops(host)) == 1


class PipelineTransport:
    """In-memory transport boundary, not real remote/native verification."""

    instances = []
    failure = None

    def __init__(self, host, *, clock):
        self.host, self.clock, self.calls, self.evidence = host, clock, [], {}
        self.materialize_argv = ("fixed-materializer",)
        self.data = {f"checkpoint-{phase}/{key}": b"tiny" if key == "optimizer.pt" else b"{}"
                     for phase in (1, 2)
                     for key in ("native-observation.json", "trainer_state.json", "optimizer.pt")}
        self.manifest = tuple(dict(key=key, size=len(body), sha256=hashlib.sha256(body).hexdigest())
                              for key, body in sorted(self.data.items()))
        self.instances.append(self)

    @property
    def sandbox(self):
        return self.host.resource

    @sandbox.setter
    def sandbox(self, value):
        assert value is self.host.resource

    def bind_runtime(self, **kwargs):
        pass

    async def stage_uploads(self, items, *, deadline):
        self.calls.append(("stage", deadline))

    async def exec_once(self, argv, *, input_chunks=(), stdout_sink=None,
                        stdout_limit, stderr_limit, deadline):
        self.calls.append((argv, deadline))
        if argv == r.NATIVE_ARGV:
            self.evidence[r._LATCH_KEY] = b"".join(input_chunks)
            if self.failure in ("native", "ambiguous"):
                error = t.ExecStartAmbiguous if self.failure == "ambiguous" else ValueError
                raise error("controlled native failure")
        if argv == r.VERIFY_ARGV:
            original = r._load_strict_json(self.evidence[r._LATCH_KEY])
            observations = dict(original, op="phase-observations", observations=[
                dict(phase=1, pid=400, returncode=0), dict(phase=2, pid=401, returncode=0)])
            self.evidence[r._OBSERVATIONS_KEY] = r._canonical_json(observations)
            sha = hashlib.sha256(b"{}").hexdigest()
            document = dict(original, op="remote-verification-receipt",
                scope=r._REMOTE_VERIFICATION_SCOPE,
                phase_observations=observations["observations"], phase_returncodes=[0, 0],
                checkpoints=[dict(checkpoint=f"checkpoint-{phase}",
                    members=sorted(("native-observation.json", "trainer_state.json", "optimizer.pt")),
                    observation_sha256=sha, trainer_state_sha256=sha) for phase in (1, 2)],
                artifact_bytes=16, manifest=list(self.manifest))
            if self.failure == "receipt-binding":
                document["app_id"] = "ap-not-issued"
            body = r._canonical_json(document)
            if self.failure == "receipt-truncation":
                body = body[:-1]
            self.evidence[r._RECEIPT_KEY] = body
            index = [dict(key=key, size=len(body), sha256=hashlib.sha256(body).hexdigest())
                     for key, body in sorted(self.evidence.items())]
            if self.failure == "receipt-hash":
                index[-1]["sha256"] = "0" * 64
            stdout_sink(r._canonical_json(index))
        return t.ExecOutcome(0, 0, 0, True, True)

    async def get_to(self, root, entry, sink, *, deadline):
        self.calls.append((("get", root, entry["key"]), deadline))
        body = (self.evidence if root == "evidence" else self.data)[entry["key"]]
        sink(body)

    async def output_manifest(self, *, max_bytes, deadline):
        self.calls.append(("manifest-output", deadline))
        return self.manifest


def prepared_stub():
    return SimpleNamespace(rpc_source=b"controlled", rpc_sha256="0" * 64,
        request_sha256="0" * 64, binding=BINDING, items=(),
        snapshots=SimpleNamespace(__exit__=lambda *args: None))


def test_full_success_path_all_nine_exports_and_reserves(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "ModalExecTransport", PipelineTransport)
    monkeypatch.setattr(PipelineTransport, "failure", None)
    host = Host()
    request = SimpleNamespace(bounds=SimpleNamespace(artifact_bytes=1000))
    result = asyncio.run(r._run_engineering_once_impl(
        request, host=host, uploads=(), setup_argv=SETUP, export_root=tmp_path / "export",
        clock=lambda: 100.0, prepared=prepared_stub()))
    wire = PipelineTransport.instances[-1]
    assert len(result.exports) == 9 and result.phase_returncodes == (0, 0)
    assert sum(argv == r.NATIVE_ARGV for argv, deadline in wire.calls) == 1
    assert sum(argv == r.VERIFY_ARGV for argv, deadline in wire.calls) == 1
    assert (r.NATIVE_ARGV, 1650.0) in wire.calls and (r.VERIFY_ARGV, 1710.0) in wire.calls
    assert all(deadline == 1770.0 for argv, deadline in wire.calls
               if argv == "manifest-output" or isinstance(argv, tuple) and argv[:1] == ("get",))
    assert stops(host) == [("stop", 1800.0)] and host.calls.count("create") == 1
    assert result.certificate is None and result.claims["host_tensor_verification"] == "not_performed"
    for exported in result.exports:
        assert exported.path.stat().st_size == exported.size
        assert hashlib.sha256(exported.path.read_bytes()).hexdigest() == exported.sha256


def test_full_pipeline_native_and_receipt_refusals(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "ModalExecTransport", PipelineTransport)
    for index, failure in enumerate(("native", "ambiguous", "receipt-binding",
                                     "receipt-truncation", "receipt-hash")):
        monkeypatch.setattr(PipelineTransport, "failure", failure)
        host = Host()
        with pytest.raises((ValueError, t.ExecStartAmbiguous)):
            asyncio.run(r._run_engineering_once_impl(
                SimpleNamespace(bounds=SimpleNamespace(artifact_bytes=1000)),
                host=host, uploads=(), setup_argv=SETUP, export_root=tmp_path / str(index),
                clock=lambda: 100.0, prepared=prepared_stub()))
        wire = PipelineTransport.instances[-1]
        assert sum(argv == r.NATIVE_ARGV for argv, deadline in wire.calls) == 1
        assert sum(argv == r.VERIFY_ARGV for argv, deadline in wire.calls) == (
            0 if failure in ("native", "ambiguous") else 1)
        assert len(stops(host)) == 1 and host.calls[-1] == "stopped"


def test_public_bridge_original_argument_identity_separate_loop(monkeypatch, tmp_path):
    from train.test_qualification_modal_transport import Sandbox
    # This is a controlled bridge dependency, NOT an alternate production loop.
    sdk_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=sdk_loop.run_forever)
    bridge = InlineBridge()
    dispatches, seen, closed, raw_operations = [], [], [], []
    def raw_check(name):
        assert asyncio.get_running_loop() is sdk_loop
        raw_operations.append(name)
    class LoopSandbox(Sandbox):
        async def exec(self, *argv, **kwargs):
            raw_check("exec")
            process = await super().exec(*argv, **kwargs)
            original_write, original_eof = process.stdin.write, process.stdin.write_eof
            original_drain, original_wait = process.stdin.drain, process.wait
            def write(block):
                raw_check("write")
                original_write(block)
            def eof():
                raw_check("EOF")
                original_eof()
            async def drain():
                raw_check("drain")
                await original_drain()
            async def wait():
                raw_check("wait")
                return await original_wait()
            class LoopReader:
                def __init__(self, reader, name):
                    self.reader, self.name = reader, name
                async def __aiter__(self):
                    raw_check(self.name)
                    async for block in self.reader:
                        yield block
            process.stdin.write, process.stdin.write_eof = write, eof
            process.stdin.drain, process.wait = drain, wait
            process.stdout = LoopReader(process.stdout, "stdout")
            process.stderr = LoopReader(process.stderr, "stderr")
            return process
    def wrap(closure):
        assert closure in bridge.marked
        async def aio():
            dispatches.append(1)
            return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(closure(), sdk_loop))
        return SimpleNamespace(aio=aio)
    monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, wrap))
    marker, request, host, uploads, root = object(), object(), Host(), [], tmp_path / "export"
    host.resource = LoopSandbox(b"payload", b"stderr")
    prep = prepared_stub()
    prep.snapshots = SimpleNamespace(__exit__=lambda *args: closed.append(1))
    monkeypatch.setattr(r, "_prepare", lambda *args, **kwargs: prep)
    async def implementation(value, **kwargs):
        assert value is request
        assert kwargs["host"] is host and kwargs["uploads"] is uploads
        assert kwargs["setup_argv"] is SETUP and kwargs["export_root"] is root
        assert asyncio.get_running_loop() is sdk_loop
        streamed = []
        raw = t.ModalExecTransport(host, clock=lambda: 100.0)
        outcome = await raw.exec_once(t.RPC_SERVE_ARGV, input_chunks=(b"input",),
            stdout_sink=streamed.append, stdout_limit=100, stderr_limit=100, deadline=102.0)
        assert outcome.returncode == 0 and b"".join(streamed) == b"payload"
        seen.append(1)
        return marker
    monkeypatch.setattr(r, "_run_engineering_once_impl", implementation)
    async def run():
        assert asyncio.get_running_loop() is not sdk_loop
        return await r.run_engineering_once(request, host=host, uploads=uploads,
            setup_argv=SETUP, export_root=root, clock=lambda: 100.0)
    thread.start()
    try:
        assert asyncio.run(run()) is marker
        assert dispatches == seen == closed == [1]
        assert sorted(raw_operations) == sorted(
            ["exec", "write", "EOF", "drain", "wait", "stdout", "stderr"])
    finally:
        sdk_loop.call_soon_threadsafe(sdk_loop.stop)
        thread.join(timeout=1.0)
        assert not thread.is_alive()
        sdk_loop.close()


def test_public_cancellation_actual_owned_stop_once(monkeypatch, tmp_path):
    bridge = InlineBridge()
    monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, bridge.wrap))
    monkeypatch.setattr(r, "_prepare", lambda *args, **kwargs: prepared_stub())
    async def run():
        admitted, stopped, stop_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class Hanging(PipelineTransport):
            async def stage_uploads(self, items, *, deadline):
                admitted.set()
                await asyncio.Event().wait()
        class WaitingStop(Host):
            async def stop_owned(self, *, deadline):
                self.calls.append(("stop", deadline))
                stop_started.set()
                await asyncio.wait_for(stopped.wait(), 1.0)
                self.calls.append("stopped")
        monkeypatch.setattr(t, "ModalExecTransport", Hanging)
        host = WaitingStop()
        task = asyncio.create_task(r.run_engineering_once(
            object(), host=host, uploads=(), setup_argv=SETUP, export_root=tmp_path / "export",
            clock=lambda: 100.0))
        await asyncio.wait_for(admitted.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(stop_started.wait(), 1.0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        stopped.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(stops(host)) == 1 and host.calls[-1] == "stopped"
    asyncio.run(run())


def tiny_original_request(monkeypatch, tmp_path):
    """Real original serializer/schema, only asset admission/model inventory controlled."""
    from decimal import Decimal
    from bench.task import SqlTask
    from train import guards, native_qualification as native
    source, model, data = (tmp_path / name for name in ("source", "model", "data"))
    for directory in (source, model, data):
        directory.mkdir()
    (source / "train").mkdir()
    b_source = Path(t.__file__).with_name("qualification_file_rpc.py").read_bytes()
    source_path = source / "train/qualification_file_rpc.py"
    source_path.write_bytes(b_source)
    def pin(path, body):
        path.write_bytes(body)
        return native.FilePin(path, len(body), hashlib.sha256(body).hexdigest())
    source_pin = native.FilePin(source_path, len(b_source), hashlib.sha256(b_source).hexdigest())
    model_pin = pin(model / "tiny", b"m")
    runtime = pin(tmp_path / "runtime", b"r")
    databases = tuple(pin(data / f"fixture-{phase}", b"d") for phase in range(4))
    tasks = tuple(SqlTask(name=name, question="q", evidence="", gold_sql="select 1",
        db_id=name, db_path=str(database.path), tier="simple", tier_source="derived",
        shape="one", coarse_shape="one", source="fixture")
        for name, database in zip(("first", "second", "third", "fourth"), databases))
    bounds = native.AttemptBounds(Decimal("25"), Decimal("0"), Decimal("25"),
                                 1800, 65536, 100000, 60)
    request = native.QualificationRequest(tasks, data, model, tmp_path / "export",
        (source_pin,), databases, runtime, "sha256:" + "1" * 64, bounds)
    monkeypatch.setattr(guards, "REPO_ROOT", source)
    monkeypatch.setattr(native, "_validate_request", lambda request: None)
    monkeypatch.setattr(native, "_verified_model_members", lambda request: (model_pin,))
    payload, assets = native._prepare_worker_transport(request)
    uploads = tuple(t.PlannedUpload(asset.kind, asset.key, asset.size, asset.sha256, asset.host_path)
                    for asset in assets)
    request_upload = upload(tmp_path / "request-upload", payload, "request", "request.json")
    return native, request, uploads + (request_upload,), payload


def test_actual_original_schema_preflight_and_public_success(monkeypatch, tmp_path):
    native, request, uploads, payload = tiny_original_request(monkeypatch, tmp_path)
    document = native._decode_worker_transport(payload)
    assert set(document) == {"schema", "assets", "tasks", "image_digest", "bounds"}
    assert document["schema"] == "native-sql-worker-v1" and len(document["tasks"]) == 4
    bridge = InlineBridge()
    monkeypatch.setattr(r, "_load_bridge", lambda: (bridge, bridge.wrap))
    monkeypatch.setattr(t, "ModalExecTransport", PipelineTransport)
    monkeypatch.setattr(PipelineTransport, "failure", None)
    host = Host()
    result = asyncio.run(r.run_engineering_once(
        request, host=host, uploads=uploads, setup_argv=SETUP,
        export_root=request.output_dir, clock=lambda: 100.0))
    assert bridge.dispatches == 1 and len(result.exports) == 9
    assert host.calls.index("active") < host.calls.index("open")
    assert host.calls.index("uploads") < host.calls.index("open")
    assert host.calls.index("setup") < host.calls.index("open")
    assert list(tmp_path.glob(".qualification-snapshot-*")) == []


def test_actual_public_preflight_wrong_request_bytes_and_path_zero_sdk(monkeypatch, tmp_path):
    native, request, uploads, payload = tiny_original_request(monkeypatch, tmp_path)
    bridge_calls = []
    monkeypatch.setattr(r, "_load_bridge", lambda: bridge_calls.append(1))
    request_item = uploads[-1]
    altered = r._load_strict_json(payload)
    altered["output_dir"] = "/invented/native/export"
    changed = upload(tmp_path / "changed-request", r._canonical_json(altered), "request", "request.json")
    model_index = next(index for index, item in enumerate(uploads) if item.root == "model")
    copy = tmp_path / "wrong-local-model-path"
    copy.write_bytes(uploads[model_index].path.read_bytes())
    wrong_path = list(uploads)
    wrong_path[model_index] = replace(uploads[model_index], path=copy)
    wrong_hash = list(uploads)
    wrong_hash[model_index] = replace(uploads[model_index], sha256="0" * 64)
    cases = (uploads[:-1] + (changed,), tuple(wrong_path), tuple(wrong_hash))
    for items in cases:
        host = Host()
        with pytest.raises(ValueError):
            asyncio.run(r.run_engineering_once(
                request, host=host, uploads=items, setup_argv=SETUP,
                export_root=request.output_dir, clock=lambda: 100.0))
        assert "open" not in host.calls and "create" not in host.calls and stops(host) == []
    assert bridge_calls == [] and not request.output_dir.exists()
    assert list(tmp_path.glob(".qualification-snapshot-*")) == []


def test_native_missing_duplicate_returns_refuse_and_restore(monkeypatch, tmp_path):
    native, request, evidence, launched = remote_dependencies(monkeypatch, tmp_path)
    for label in ("missing", "duplicate"):
        fresh = tmp_path / label
        fresh.mkdir()
        monkeypatch.setattr(r, "_EVIDENCE_ROOT", fresh)
        def worker(path):
            if label == "duplicate":
                for phase in (1, 2, 2):
                    native._run_child(path, phase, deadline=200.0, output_limit=100)
            return 0
        monkeypatch.setattr(native, "_worker_main", worker)
        input_document(monkeypatch, private("native-attempt"))
        with pytest.raises(ValueError, match="returns"):
            r.main(["--native"])
        assert sys.getprofile() is None and not (fresh / r._OBSERVATIONS_KEY).exists()


def test_export_replaced_inode_and_new_hardlink_refuse(tmp_path):
    for index, change in enumerate(("replace", "hardlink")):
        wrote = False
        with pytest.raises(ValueError):
            with r._ExportTree(tmp_path / str(index)) as tree:
                result = tree.write_bytes("file", b"real")
                wrote = True
                if change == "replace":
                    result.path.unlink()
                    result.path.write_bytes(b"fake")
                else:
                    os.link(result.path, tmp_path / "new-link")
                tree.check()
        assert wrote


def test_export_parent_changed_after_preallocation_refuses_zero_files(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    with r._Anchor(parent) as retained:
        parent.rename(tmp_path / "old-parent")
        parent.mkdir()
        with pytest.raises(ValueError, match="redirected"):
            with r._ExportTree(parent / "export", parent_anchor=retained):
                pytest.fail("new parent admitted")
        assert not (parent / "export").exists()


def _assert_bootstrap_inherited_cwd_phase_discovery(tmp_path, mode, bootstrap):
    from train import native_qualification as native

    root = tmp_path / "sandbox"
    source = root / "opt/qualification/source"
    package = source / "train"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    entry = package / "qualification_engineering_run.py"
    entry.write_text("launch_phases()\n", encoding="utf-8")
    phase_file = package / "native_qualification.py"
    phase_file.write_text(
        "import os,sys\nPHASE = int(sys.argv[2])\nCWD = os.getcwd()\n",
        encoding="utf-8",
    )
    output = root / "var/tmp/qualification/output"
    fixed_source = "/opt/qualification/source"
    fixture_roots = {fixed_source: source}
    original_phase_argv = native._phase_argv
    original_phase_code = original_phase_argv.__code__
    assert bootstrap == t._mode_argv(mode)
    assert bootstrap[:2] == ("/usr/local/bin/python3.12", "-c")

    def discover(module, search):
        # Explicit fresh-child paths, never sys.path or sys.modules lookup.
        parent = PathFinder.find_spec("train", search)
        if parent is None:
            raise ModuleNotFoundError("no staged package at inherited cwd")
        spec = PathFinder.find_spec(module, parent.submodule_search_locations)
        if spec is None:
            raise ModuleNotFoundError("no staged module at inherited cwd")
        return spec

    def run_bootstrap(apply_chdir):
        state = SimpleNamespace(cwd=root)
        bootstrap_sys = SimpleNamespace(path=[], argv=[])
        events, phase_calls, phase_results = [], [], []

        def chdir(path):
            assert path == fixed_source
            events.append(("chdir", path))
            if apply_chdir:
                state.cwd = fixture_roots[path]

        def launch_phases():
            for phase in (1, 2):
                # The original builder is called afresh; no replacement seam.
                argv = native._phase_argv(
                    Path("/var/tmp/qualification/request.json"), phase)
                phase_calls.append(argv)
                assert argv == (
                    "/usr/local/bin/python3.12", "-m", "train.native_qualification",
                    "--_phase", str(phase), "--_request",
                    "/var/tmp/qualification/request.json",
                )
                inherited_cwd = state.cwd
                child_spec = discover(argv[2], [str(inherited_cwd)])
                assert Path(child_spec.origin) == phase_file
                child_modules = {
                    "sys": SimpleNamespace(argv=[child_spec.origin, *argv[3:]]),
                    "os": SimpleNamespace(getcwd=lambda: str(inherited_cwd)),
                }

                def child_import(name, globals=None, locals=None, fromlist=(), level=0):
                    assert level == 0 and name in child_modules
                    return child_modules[name]

                child_builtins = dict(vars(builtins), __import__=child_import)
                child_globals = {"__builtins__": child_builtins, "__name__": "__main__"}
                # Only the discovered tiny fixture executes, in a fresh namespace.
                exec(compile(Path(child_spec.origin).read_bytes(), child_spec.origin,
                             "exec"), child_globals)
                phase_results.append((child_globals["PHASE"], child_globals["CWD"]))
                assert not output.exists()

        def run_module(module, *, run_name):
            events.append(("runpy", state.cwd))
            assert module == "train.qualification_engineering_run"
            assert run_name == "__main__"
            assert bootstrap_sys.argv == [module, mode]
            assert bootstrap_sys.path == [fixed_source]
            # Parent lookup works even with chdir disabled. Its inserted path
            # is deliberately NOT forwarded to the fresh phase boundary.
            entry_spec = discover(
                module, [str(fixture_roots[path]) for path in bootstrap_sys.path])
            assert Path(entry_spec.origin) == entry
            assert not output.exists()
            exec(compile(entry.read_bytes(), str(entry), "exec"),
                 {"__builtins__": {}, "launch_phases": launch_phases})

        modules = {
            "os": SimpleNamespace(chdir=chdir),
            "runpy": SimpleNamespace(run_module=run_module),
            "sys": bootstrap_sys,
        }

        def bootstrap_import(name, globals=None, locals=None, fromlist=(), level=0):
            assert level == 0 and name in modules
            return modules[name]

        controlled_builtins = dict(vars(builtins), __import__=bootstrap_import)
        assert not output.exists()
        if apply_chdir:
            exec(bootstrap[2], {"__builtins__": controlled_builtins})
            assert events == [("chdir", fixed_source), ("runpy", source)]
            assert phase_results == [(1, str(source)), (2, str(source))]
            assert len(phase_calls) == 2
        else:
            with pytest.raises(ModuleNotFoundError, match="staged package"):
                exec(bootstrap[2], {"__builtins__": controlled_builtins})
            assert events == [("chdir", fixed_source), ("runpy", root)]
            assert len(phase_calls) == 1 and phase_results == []
        assert not output.exists()
        assert native._phase_argv is original_phase_argv
        assert native._phase_argv.__code__ is original_phase_code

    run_bootstrap(True)
    run_bootstrap(False)


def test_native_bootstrap_inherited_cwd_original_phase_discovery(tmp_path):
    _assert_bootstrap_inherited_cwd_phase_discovery(tmp_path, "--native", r.NATIVE_ARGV)


def test_verify_bootstrap_inherited_cwd_original_phase_discovery(tmp_path):
    _assert_bootstrap_inherited_cwd_phase_discovery(tmp_path, "--verify", r.VERIFY_ARGV)
