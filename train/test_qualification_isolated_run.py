"""V238 new source UNRUN; earlier 51 units accepted in V235.

No test here claims actual admission, original-asset validation, provider
execution, tensor/native science, actual child creation or actual process reap.
No real original serializer or interpreter hash is authorized by these tests.
"""
import ast
import asyncio
import builtins
import copy
from dataclasses import replace
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import pickle
import stat
import subprocess
from types import SimpleNamespace

import pytest

from train import qualification_engineering_run as original
from train import qualification_isolated_contract as c
from train import qualification_isolated_program as program
from train import qualification_isolated_run as runner
from train import qualification_modal_transport as transport

APP = "ap-" + "a" * 22
SANDBOX = "sb-localmock"
BINDING = "b" * 64
SETUP = ("/usr/local/bin/python3.12", "-m", "pip", "install", "--no-index",
         "--find-links", "/opt/qualification/wheels", "mock-approved")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def launch_for(**changes):
    values = dict(
        v=1, session="a" * 64, source_root="/mock/source",
        source_pins=(c.SourcePin("train/fixed.py", 1, "c" * 64),),
        sdk_root="/mock/sdk", sdk_pins=(c.SourcePin("modal/fixed.py", 1, "d" * 64),),
        interpreter_size=1, interpreter_sha256="e" * 64, request_binding=BINDING,
        request_size=1, request_sha256="f" * 64,
        manifest_size=1, manifest_sha256="0" * 64, setup_argv=SETUP,
        image_base_reference="mock@sha256:" + "1" * 64,
        image_recipe_sha256="2" * 64, gpu="mock", cpu=(1, 1),
        memory=(128, 128), export_name="export", attempt_ns=1800 * c.NS,
        timing=c.StopTimingFacts(c.NS, 20 * c.NS, c.NS),
    )
    values.update(changes)
    return c.LaunchDescriptor(**values)


def spec():
    # DTO only. No genuine A FilePin/resource/binding or authorization is faked.
    return c.IsolatedOwnerSpec(
        object(), Path("/mock/source"), (), Path("/mock/sdk"), (), object(),
        object(), Path("/mock/scratch"), Path("/mock/evidence"))


def upload(root, key, raw=b"tiny", path=None):
    return transport.PlannedUpload(
        root, key, len(raw), sha(raw), path or Path("/mock/inputs") / root / key)


def asset(item):
    return SimpleNamespace(kind=item.root, key=item.key, size=item.size,
                           sha256=item.sha256, host_path=item.path)


def approved():
    return (upload("source", c.RPC_SOURCE_KEY),
            upload("model", "config.json"), upload("data", "first.sqlite"),
            upload("wheels", "package.whl"))


class MockWriter:
    """Metadata-only A writer mock. Never opens original host paths."""

    def __init__(self, uploads, calls):
        self.uploads, self.calls, self.entries = uploads, calls, []

    def snapshot_member(self, **row):
        self.calls.append(("snapshot", row["root"]))
        expected = next(item for item in self.uploads
                        if (item.root, item.key) == (row["root"], row["key"]))
        assert (row["source_path"], row["size"], row["sha256"]) == (
            expected.path, expected.size, expected.sha256)
        result = c.ManifestEntry(
            row["root"], row["key"], row["size"], row["sha256"],
            f"{len(self.entries) + 1:064x}")
        self.entries.append(result)
        return result

    def write_request(self, payload):
        self.calls.append("request")
        result = c.ManifestEntry("request", "request.json", len(payload),
                                 sha(payload), "f" * 64)
        self.entries.append(result)
        return result

    def seal(self, entries, launch):
        self.calls.append("writer-seal")
        assert {(e.root, e.key) for e in entries if e.root != "request"} == {
            (item.root, item.key) for item in self.uploads}
        raw = c.encode_launch(launch)
        return c.PreparedInputs(
            launch.request_size, launch.request_sha256,
            launch.manifest_size, launch.manifest_sha256, len(raw), sha(raw), entries)


class MockPinnedLaunch:
    def __init__(self, calls, **changes):
        self.calls, self.changes = calls, changes

    def descriptor_for(self, **facts):
        self.calls.append("descriptor")
        return launch_for(**{**facts, **self.changes})


class MockOwner:
    """Mock joined custody only, not a genuine owner or process observation."""

    def __init__(self, items, calls):
        self.calls = calls
        self.writer = MockWriter(items, calls)
        self.release_error = None
        self.run_error = None

    def preparation_writer(self):
        self.calls.append("writer")
        return self.writer

    def seal_inputs(self, prepared, launch):
        self.calls.append("seal")

    def register_parent_validation(self, *, request, prepared, export_root):
        assert self.calls[-1] == "seal" and "register" not in self.calls
        self.calls.append("register")

    async def run_once(self):
        self.calls.append("run")
        if self.run_error:
            raise self.run_error
        return object()

    def release_joined(self):
        self.calls.append("release")
        if self.release_error:
            raise self.release_error


def public_harness(monkeypatch, *, allow_custody=False):
    calls, request, authorization = [], object(), object()
    items, owner_spec = approved(), spec()
    owner = MockOwner(items, calls)
    pinned = MockPinnedLaunch(calls)
    preflight = object()

    def preflight_isolated(value, **kwargs):
        assert value is request and kwargs["authorization"] is authorization
        assert kwargs["owner_spec"] is owner_spec and kwargs["uploads"] is items
        assert kwargs["setup_argv"] is SETUP
        calls.append("preflight")
        return preflight

    def admit_isolated_owner(value):
        assert value is preflight
        calls.append("admit")
        return owner

    def pin_worker_launch(value, *, owner_spec):
        assert value is owner
        calls.append("pin")
        return pinned

    api = SimpleNamespace(
        preflight_isolated=preflight_isolated,
        admit_isolated_owner=admit_isolated_owner, pin_worker_launch=pin_worker_launch)
    monkeypatch.setattr(runner, "_load_owner_api", lambda: api)
    if allow_custody:
        # Explicitly bypass ONLY in mock orchestration tests. Never production.
        monkeypatch.setattr(runner, "_require_parent_read_custody", lambda: None)

    def serializer(value):
        assert value is request and calls.index("admit") < calls.index("pin")
        calls.append("serialize")
        return b'{"mock-original-result":true}', tuple(
            asset(item) for item in items if item.root != "wheels")

    monkeypatch.setattr(runner, "_load_native", lambda: SimpleNamespace(
        _prepare_worker_transport=serializer))
    sentinel = object()

    def validate(value, **kwargs):
        assert value is request
        assert kwargs["owner"] is owner
        calls.append("validate")
        return sentinel

    monkeypatch.setattr(runner, "validate_joined_outcome", validate)
    kwargs = dict(authorization=authorization, owner_spec=owner_spec, uploads=items,
                  setup_argv=SETUP, export_root=Path("/mock/export"))
    return SimpleNamespace(calls=calls, request=request, owner=owner, kwargs=kwargs,
                           sentinel=sentinel, pinned=pinned)


def test_public_invalid_and_missing_custody(monkeypatch):
    h = public_harness(monkeypatch)
    counts = {"sdk": 0, "children": 0}
    real_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == "modal" or name.startswith("modal."):
            counts["sdk"] += 1
            pytest.fail("parent imported SDK")
        return real_import(name, *args, **kwargs)
    def no_children(*args, **kwargs):
        counts["children"] += 1
        pytest.fail("parent attempted child creation")
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(subprocess, "Popen", no_children)
    for name in ("fork", "posix_spawn", "posix_spawnp"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, no_children)
    with pytest.raises(ValueError):
        asyncio.run(runner.run_engineering_isolated_once(
            None, **{**h.kwargs, "authorization": None}))
    assert h.calls == []
    with pytest.raises(runner.FrozenReadCustodyUnavailable):
        asyncio.run(runner.run_engineering_isolated_once(h.request, **h.kwargs))
    assert h.calls == ["preflight"]
    assert not any(name in h.calls for name in ("admit", "serialize", "run"))
    assert counts == {"sdk": 0, "children": 0}
    assert set(c.PreparedInputs.__dataclass_fields__) == {
        "request_size", "request_sha256", "manifest_size", "manifest_sha256",
        "launch_size", "launch_sha256", "entries"}


def test_public_order(monkeypatch):
    h = public_harness(monkeypatch, allow_custody=True)
    assert asyncio.run(runner.run_engineering_isolated_once(
        h.request, **h.kwargs)) is h.sentinel
    assert h.calls == [
        "preflight", "admit", "pin", "serialize", "writer",
        ("snapshot", "source"), ("snapshot", "model"), ("snapshot", "data"),
        ("snapshot", "wheels"), "request", "descriptor", "writer-seal",
        "seal", "register", "run", "validate", "release"]


@pytest.mark.parametrize("unknown", [False, True])
def test_public_failure_custody(monkeypatch, unknown):
    h = public_harness(monkeypatch, allow_custody=True)
    primary = ValueError("mock content failure")
    def fail(value):
        h.calls.append("serialize")
        raise primary
    monkeypatch.setattr(runner, "serialize_original_request", fail)
    cleanup = RuntimeError("mock join/close unknown")
    if unknown:
        h.owner.release_error = cleanup
        with pytest.raises(runner.IsolatedCustodyError) as caught:
            asyncio.run(runner.run_engineering_isolated_once(h.request, **h.kwargs))
        assert caught.value.owner is h.owner
        assert caught.value.primary is primary and caught.value.cleanup is cleanup
        assert runner._RETAINED_FAILURES[-1] is caught.value
        runner._RETAINED_FAILURES.pop()
    else:
        with pytest.raises(ValueError) as caught:
            asyncio.run(runner.run_engineering_isolated_once(h.request, **h.kwargs))
        assert caught.value is primary
    assert h.calls == ["preflight", "admit", "pin", "serialize", "release"]


def test_original_serializer_delegation(monkeypatch):
    calls, request = [], object()
    payload, assets = b"unchanged serializer bytes", ()
    def original_serializer(value):
        assert value is request
        calls.append(1)
        return payload, assets
    monkeypatch.setattr(runner, "_load_native", lambda: SimpleNamespace(
        _prepare_worker_transport=original_serializer))
    result = runner.serialize_original_request(request)
    assert result.payload is payload and result.assets is assets and calls == [1]
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="parent-local"):
            operation(result)


@pytest.mark.parametrize("mutation", [
    "missing", "extra", "duplicate", "size", "hash", "path", "request", "argv",
])
def test_prepare_exact_coverage(monkeypatch, mutation):
    items = approved()
    original_assets = tuple(asset(item) for item in items if item.root != "wheels")
    changed = list(items)
    if mutation == "missing":
        changed.pop(1)
    elif mutation == "extra":
        changed.append(upload("model", "extra.json"))
    elif mutation == "duplicate":
        changed.append(changed[1])
    elif mutation in {"size", "hash", "path"}:
        values = {"size": changed[1].size + 1, "sha256": "0" * 64,
                  "path": Path("/different/same-file")}
        field = {"size": "size", "hash": "sha256", "path": "path"}[mutation]
        changed[1] = replace(changed[1], **{field: values[field]})
    elif mutation == "request":
        changed.append(upload("request", "request.json"))
    monkeypatch.setattr(runner, "serialize_original_request", lambda request:
                        runner.OriginalTransport(b"original", original_assets))
    calls = []
    owner = MockOwner(items, calls)
    pinned = MockPinnedLaunch(calls, **({"setup_argv": ("changed",)}
                                       if mutation == "argv" else {}))
    with pytest.raises(ValueError):
        runner.prepare_isolated_inputs(
            object(), owner=owner, uploads=tuple(changed), setup_argv=SETUP,
            export_root=Path("/mock/export"), launch=pinned)
    assert "writer-seal" not in calls


def test_prepare_derived_request_and_wheels(monkeypatch):
    items, calls = approved(), []
    monkeypatch.setattr(runner, "serialize_original_request", lambda request:
                        runner.OriginalTransport(b"original", tuple(
                            asset(item) for item in items if item.root != "wheels")))
    prepared = runner.prepare_isolated_inputs(
        object(), owner=MockOwner(items, calls), uploads=items, setup_argv=SETUP,
        export_root=Path("/mock/export"), launch=MockPinnedLaunch(calls))
    assert len(prepared.entries) == len(items) + 1 == 5
    assert sum(e.root == "request" for e in prepared.entries) == 1
    assert ("snapshot", "wheels") in calls


def entry(root, key, size=0, index=1):
    return c.ManifestEntry(root, key, size, "0" * 64, f"{index:064x}")


def test_manifest_limits(monkeypatch):
    wheel_key = "/".join(("a" * 255, "b" * 255, "c" * 255, "d" * 254, "e"))
    assert len(wheel_key) == 1024
    c.input_key("wheels", wheel_key)
    c.input_key("source", "a" * 254 + "/a")
    for root, key in (("wheels", wheel_key + "e"), ("source", "a" * 255 + "/a")):
        with pytest.raises(ValueError):
            c.input_key(root, key)
    rows = [entry("source", c.RPC_SOURCE_KEY, 1, 1)]
    rows += [entry("wheels", f"wheel-{i:04}", 0, i + 2) for i in range(4095)]
    rows.append(entry("request", "request.json", 1, 4097))
    ordered = tuple(sorted(rows, key=lambda e: (e.root, e.key)))
    assert len(c.decode_manifest(c.encode_manifest(ordered))) == 4097
    with pytest.raises(ValueError):
        c.encode_manifest(tuple(sorted(
            (*ordered, entry("wheels", "one-too-many", 0, 4098)),
            key=lambda e: (e.root, e.key))))
    total_rows = (entry("source", c.RPC_SOURCE_KEY, 1, 1),
                  entry("request", "request.json", 1, 2),
                  *(entry("wheels", f"w{i}", c.FILE_LIMIT - (2 if i == 3 else 0), i + 3)
                    for i in range(4)))
    total_rows = tuple(sorted(total_rows, key=lambda e: (e.root, e.key)))
    assert sum(e.size for e in total_rows) == c.TOTAL_LIMIT
    c.encode_manifest(total_rows)
    with pytest.raises(ValueError):
        c.encode_manifest(tuple(replace(e, size=2) if e.root == "request" else e
                                for e in total_rows))
    with pytest.raises(ValueError):
        entry("wheels", "oversized", c.FILE_LIMIT + 1)
    with pytest.raises(ValueError):
        entry("request", "request.json", c.REQUEST_LIMIT + 1)
    def no_parse(*args, **kwargs):
        pytest.fail("oversized manifest reached JSON parser")
    monkeypatch.setattr(c.json, "loads", no_parse)
    with pytest.raises(ValueError, match="byte limit"):
        c.decode_manifest(b" " * (8388608 + 1))


def _write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        original._write_all(fd, raw)
    finally:
        os.close(fd)


@pytest.fixture
def owned_inputs(tmp_path):
    """Inherited-style regular FDs, not actual child inheritance or A custody."""
    root = tmp_path.resolve()
    snapshot_root = root / "snapshots"
    snapshot_root.mkdir(mode=0o700)
    bodies = {
        ("source", c.RPC_SOURCE_KEY): b"MOCK RPC, NEVER EXECUTED",
        ("source", "qualification/runtime-inventory.json"): b"MOCK inventory",
        ("model", "config.json"): b"MOCK model, not registered weights",
        ("wheels", "package.whl"): b"MOCK wheel, never installed",
        **{("data", f"{name}/{name}.sqlite"): b"MOCK database"
           for name in ("first", "second", "third", "fourth")},
    }
    document = dict(
        schema="native-sql-worker-v1", assets=[
            dict(kind=kind, key=key, size=len(raw), sha256=sha(raw))
            for (kind, key), raw in sorted(bodies.items()) if kind != "wheels"],
        tasks=[dict(name=name, question="mock", evidence="mock", gold_sql="SELECT 1",
                    db_id=name, db_asset=f"{name}/{name}.sqlite", tier="simple",
                    tier_source="derived", shape="fixture-select",
                    coarse_shape="fixture-select", source="fixture")
               for name in ("first", "second", "third", "fourth")],
        image_digest="sha256:" + "1" * 64,
        bounds=dict(total_ceiling_usd="25", prior_usage_usd="0",
                    remaining_worst_case_usd="25", lifetime_seconds=1800,
                    output_bytes_per_phase=1024, artifact_bytes=1000,
                    retention_seconds=60))
    payload = c.canonical(document)
    bodies["request", "request.json"] = payload
    entries = []
    for i, ((kind, key), raw) in enumerate(sorted(bodies.items()), 1):
        row = c.ManifestEntry(kind, key, len(raw), sha(raw), f"{i:064x}")
        _write_new(snapshot_root / row.snapshot_key, raw)
        entries.append(row)
    entries = tuple(entries)
    manifest = c.encode_manifest(entries)
    launch = launch_for(
        request_size=len(payload), request_sha256=sha(payload),
        manifest_size=len(manifest), manifest_sha256=sha(manifest))
    launch_raw = c.encode_launch(launch)
    files = {"control": b"unused mock control", "request": payload,
             "manifest": manifest, "launch": launch_raw, "outcome": b""}
    fds = {}
    try:
        for name, raw in files.items():
            path = root / name
            _write_new(path, raw)
            fds[name] = os.open(path, os.O_RDWR if name == "outcome" else os.O_RDONLY)
        fds["snapshot_dir"] = os.open(snapshot_root, os.O_RDONLY | os.O_DIRECTORY)
        fds["export_parent"] = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        numbers = c.WorkerFDNumbers(**fds)
        prepared = c.PreparedInputs(
            len(payload), sha(payload), len(manifest), sha(manifest),
            len(launch_raw), sha(launch_raw), entries)
        yield SimpleNamespace(
            root=root, snapshot_root=snapshot_root, launch=launch, prepared=prepared,
            inputs=c.WorkerInputs(numbers, payload, entries), bodies=bodies,
            request=SimpleNamespace(bounds=SimpleNamespace(artifact_bytes=1000)))
    finally:
        for fd in fds.values():
            os.close(fd)


@pytest.mark.parametrize("mutation", ["none", "bytes", "symlink", "hardlink", "inode"])
def test_snapshot_custody(owned_inputs, monkeypatch, mutation):
    bundle = owned_inputs
    row = bundle.inputs.entries[0]
    path = bundle.snapshot_root / row.snapshot_key
    if mutation == "bytes":
        path.write_bytes(b"!" * row.size)
    elif mutation in {"symlink", "hardlink"}:
        other = bundle.root / "other-new-owned-file"
        _write_new(other, bundle.bodies[row.root, row.key])
        path.unlink()
        if mutation == "symlink":
            path.symlink_to(other)
        else:
            os.link(other, path)
    elif mutation == "inode":
        real_hash = original._hash_fd
        def replace_after_hash(fd, **kwargs):
            result = real_hash(fd, **kwargs)
            path.rename(path.with_name("old-" + path.name))
            _write_new(path, bundle.bodies[row.root, row.key])
            return result
        monkeypatch.setattr(original, "_hash_fd", replace_after_hash)
    deadline = program.time.monotonic() + 5
    if mutation == "none":
        with program._SnapshotInventory(
            bundle.inputs.fds.snapshot_dir, bundle.inputs.entries,
            deadline=deadline) as snapshots:
            count = 0
            stream = snapshots.stream()
            try:
                for snapshot in stream:
                    assert type(snapshot) is original._Snapshot
                    assert len(snapshots.fds) == 1
                    wire = b"".join(transport.rpc_put_frames(
                        snapshot.root, snapshot.key, snapshot.size, snapshot.sha256, snapshot))
                    assert bundle.bodies[snapshot.root, snapshot.key] in wire
                    count += 1
            finally:
                stream.close()
            assert count == len(bundle.inputs.entries) and snapshots.fds == []
        os.fstat(bundle.inputs.fds.snapshot_dir)  # Borrowed anchor remains live.
    else:
        with pytest.raises((ValueError, OSError)):
            with program._SnapshotInventory(
                bundle.inputs.fds.snapshot_dir, bundle.inputs.entries,
                deadline=deadline) as snapshots:
                with snapshots.member(row):
                    pytest.fail("changed snapshot accepted")


def test_writable_fd_and_metadata_cap(owned_inputs, monkeypatch):
    path = owned_inputs.root / "request"
    fd = os.open(path, os.O_RDWR)
    try:
        with pytest.raises(ValueError, match="access mode"):
            program._read_fd(
                fd, limit=c.REQUEST_LIMIT, size=owned_inputs.launch.request_size,
                sha256=owned_inputs.launch.request_sha256, readonly=True)
    finally:
        os.close(fd)
    fd = owned_inputs.inputs.fds.outcome
    os.ftruncate(fd, c.OUTCOME_LIMIT + 1)
    monkeypatch.setattr(program.os, "read", lambda *a: pytest.fail("oversized FD read"))
    with pytest.raises(ValueError):
        program._read_fd(fd, limit=c.OUTCOME_LIMIT, size=c.OUTCOME_LIMIT,
                         sha256="0" * 64, readonly=False)


class MockHost:
    """No actual SDK App/Sandbox; cannot satisfy production loop/custody."""
    app_id, sandbox_id = APP, SANDBOX

    def __init__(self):
        self.resource = object()
        self.end_ns = program.time.monotonic_ns() + 1700 * c.NS

    def require_setup_argv(self, argv):
        assert argv == SETUP

    def __getattr__(self, name):
        if name in {"open_app", "create_once", "begin_gpu_window", "stop_owned"}:
            pytest.fail("C attempted lifecycle or renewed E")
        raise AttributeError(name)


class MockPipelineTransport:
    """In-memory protocol boundary only. NO native/full-verifier execution."""
    instances = []
    failure = None

    def __init__(self, host, *, clock):
        self.host, self.clock, self.calls, self.evidence = host, clock, [], {}
        self.materialize_argv = ("mock-fixed-materializer",)
        self.data = {f"checkpoint-{phase}/{key}":
                     (b"tiny" if key == "optimizer.pt" else b"{}")
                     for phase in (1, 2) for key in
                     ("native-observation.json", "trainer_state.json", "optimizer.pt")}
        self.manifest = tuple(dict(key=key, size=len(raw), sha256=sha(raw))
                              for key, raw in sorted(self.data.items()))
        self.instances.append(self)

    def bind_runtime(self, **kwargs):
        assert kwargs["setup_argv"] == SETUP
        assert all(type(s) is c.ManifestEntry for s in kwargs["uploads"])
        self.calls.append("bind")

    async def stage_uploads(self, items, *, deadline):
        for item in items:
            assert type(item) is original._Snapshot
            assert sha(b"".join(item.chunks())) == item.sha256
        self.calls.append(("stage", deadline))

    async def exec_once(self, argv, *, input_chunks=(), stdout_sink=None, **kwargs):
        self.calls.append((argv, kwargs["deadline"]))
        if argv == original.NATIVE_ARGV:
            self.evidence[original._LATCH_KEY] = b"".join(input_chunks)
            if self.failure == "native":
                raise ValueError("mock native failure")
        if argv == original.VERIFY_ARGV:
            private = original._load_strict_json(self.evidence[original._LATCH_KEY])
            observations = dict(private, op="phase-observations", observations=[
                dict(phase=1, pid=100, returncode=0), dict(phase=2, pid=101, returncode=0)])
            if self.failure == "phase":
                observations["observations"][1]["phase"] = 1
            self.evidence[original._OBSERVATIONS_KEY] = c.canonical(observations)
            receipt = dict(
                private, op="remote-verification-receipt",
                scope=original._REMOTE_VERIFICATION_SCOPE,
                phase_observations=observations["observations"], phase_returncodes=[0, 0],
                checkpoints=[dict(checkpoint=f"checkpoint-{phase}",
                    members=sorted(("native-observation.json", "trainer_state.json", "optimizer.pt")),
                    observation_sha256=sha(b"{}"), trainer_state_sha256=sha(b"{}"))
                    for phase in (1, 2)],
                artifact_bytes=16, manifest=list(self.manifest))
            if self.failure == "receipt-identity":
                receipt["app_id"] = "ap-" + "z" * 22
            self.evidence[original._RECEIPT_KEY] = c.canonical(receipt)
            index = [dict(key=key, size=len(raw), sha256=sha(raw))
                     for key, raw in sorted(self.evidence.items())]
            if self.failure == "evidence-hash":
                index[0]["sha256"] = "0" * 64
            stdout_sink(c.canonical(index))
        return transport.ExecOutcome(0, 0, 0, True, True)

    async def get_to(self, root, entry, sink, *, deadline):
        self.calls.append((("get", root, entry["key"]), deadline))
        raw = (self.evidence if root == "evidence" else self.data)[entry["key"]]
        if self.failure == "export-bytes" and root == "output":
            raw = b"!" * len(raw)
        sink(raw)

    async def output_manifest(self, *, max_bytes, deadline):
        self.calls.append(("output-manifest", deadline))
        return self.manifest[:-1] if self.failure == "manifest" else self.manifest


def worker_run(monkeypatch, bundle, *, failure=None):
    MockPipelineTransport.instances.clear()
    monkeypatch.setattr(MockPipelineTransport, "failure", failure)
    monkeypatch.setattr(program, "ModalExecTransport", MockPipelineTransport)
    monkeypatch.setattr(program, "_require_sdk_loop", lambda: None)
    host = MockHost()
    result = asyncio.run(program.run_prepared_worker(
        inputs=bundle.inputs, launch=bundle.launch, host=host, control=object()))
    return host, result, MockPipelineTransport.instances[-1]


def execution_for(result):
    # Synthetic observations, not a substitute for A's actual Popen custody.
    return c.JoinedExecution(
        tuple(c.ChildObservation(role, 0, True) for role in ("worker", "controller", "gate")),
        APP, SANDBOX, result.outcome_size, result.outcome_sha256, "EXITED", ())


def test_worker_pipeline(monkeypatch, owned_inputs):
    host, result, wire = worker_run(monkeypatch, owned_inputs)
    calls = [row for row in wire.calls if type(row) is tuple]
    assert [row[0] for row in calls[:5]] == [
        "stage", SETUP, wire.materialize_argv, original.NATIVE_ARGV, original.VERIFY_ARGV]
    assert sum(row[0] == original.NATIVE_ARGV for row in calls) == 1
    assert sum(row[0] == original.VERIFY_ARGV for row in calls) == 1
    booking = program.validation_booking(host.end_ns, owned_inputs.launch.timing.teardown_ns)
    end = program.math.nextafter(booking.phase_end_ns / c.NS, -program.math.inf)
    assert calls[0][1] == calls[1][1] == calls[2][1] == calls[3][1] == end - 150
    assert calls[4][1] == end - 90
    assert all(deadline == end - 30 for op, deadline in calls[5:])
    assert end - 30 <= booking.worker_export_ns / c.NS
    assert host.end_ns == booking.end_ns
    monkeypatch.setattr(runner, "_load_native", lambda: pytest.fail("original serializer rerun"))
    from train import native_qualification as native
    monkeypatch.setattr(native, "_request_binding", lambda request: BINDING)
    h = leased_harness(monkeypatch, owned_inputs, execution_for(result))
    data = asyncio.run(h.owner.validate_mock_lease())
    assert type(data) is runner._ValidatedParentData
    assert data.worker_execution is h.lease.worker_execution
    assert len(data.worker_execution.children) == 1
    assert h.owner.calls.index("mock-worker-reaped") < h.owner.calls.index("open:outcome")
    h.owner.join_mock_guards(data)
    outcome = runner.validate_joined_outcome(
        h.request, owner=h.owner, prepared=h.prepared, execution=h.execution,
        export_root=h.export_root)
    assert type(outcome.original_outcome) is original.EngineeringRunOutcome
    assert len(outcome.original_outcome.exports) == 9
    assert outcome.original_outcome.phase_returncodes == (0, 0)
    assert outcome.remote_termination == outcome.charged_end == "UNKNOWN"
    assert outcome.local_containment == "JOINED"


@pytest.mark.parametrize("failure", [
    "native", "phase", "receipt-identity", "evidence-hash", "manifest", "export-bytes",
])
def test_worker_mutations(monkeypatch, owned_inputs, failure):
    with pytest.raises(ValueError):
        worker_run(monkeypatch, owned_inputs, failure=failure)
    wire = MockPipelineTransport.instances[-1]
    assert sum(type(row) is tuple and row[0] == original.NATIVE_ARGV
               for row in wire.calls) == 1
    assert sum(type(row) is tuple and row[0] == original.VERIFY_ARGV
               for row in wire.calls) == (0 if failure == "native" else 1)
    assert os.fstat(owned_inputs.inputs.fds.outcome).st_size == 0
    if failure != "export-bytes":
        assert not (owned_inputs.root / "export").exists()
    else:
        assert (owned_inputs.root / "export").is_dir()  # Failed partial retained.


@pytest.mark.parametrize("mutation", [
    "outcome-bytes", "unknown-field", "bool-code", "export-bytes",
    "extra-file", "evidence-bytes", "receipt-size", "path",
])
def test_outcome_fd_validation(monkeypatch, owned_inputs, mutation):
    _, result, _ = worker_run(monkeypatch, owned_inputs)
    from train import native_qualification as native
    monkeypatch.setattr(native, "_request_binding", lambda request: BINDING)
    fd = owned_inputs.inputs.fds.outcome
    execution = execution_for(result)
    if mutation in {"outcome-bytes", "unknown-field", "bool-code", "receipt-size", "path"}:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, c.OUTCOME_LIMIT)
        doc = c.parse_canonical(raw, c.OUTCOME_LIMIT)
        if mutation == "unknown-field":
            doc["approved"] = True
        elif mutation == "bool-code":
            doc["phase_returncodes"] = [False, 0]
        elif mutation == "receipt-size":
            doc["receipt_size"] += 1
        elif mutation == "path":
            doc["exports"][0]["path"] = "/unanchored/host/path"
        rewritten = c.canonical(doc) if mutation != "outcome-bytes" else b"!" * len(raw)
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        original._write_all(fd, rewritten)
        # Keep expected hash unchanged for raw mutation. Other cases prove
        # schema/evidence validation even if child supplied a matching hash.
        if mutation != "outcome-bytes":
            execution = replace(execution, outcome_size=len(rewritten),
                                outcome_sha256=sha(rewritten))
    elif mutation in {"export-bytes", "evidence-bytes"}:
        name = ("checkpoint-1/optimizer.pt" if mutation == "export-bytes"
                else "evidence/" + original._OBSERVATIONS_KEY)
        path = owned_inputs.root / "export" / name
        path.write_bytes(b"!" * path.stat().st_size)
    else:
        _write_new(owned_inputs.root / "export/extra", b"not declared")
    h = leased_harness(monkeypatch, owned_inputs, execution)
    with pytest.raises(ValueError):
        asyncio.run(h.owner.validate_mock_lease())
    assert h.owner.data is None
    assert all(reader.closed and reader.close_calls == 1 for reader in h.lease.readers)


def test_reap_required_before_any_output_read(monkeypatch, owned_inputs):
    execution = c.JoinedExecution(
        (c.ChildObservation("worker", 1, True),), APP, SANDBOX, 1, "0" * 64, "NOT_EXECUTED", ())
    h = leased_harness(monkeypatch, owned_inputs, execution)
    monkeypatch.setattr(program.os, "read", lambda *a: pytest.fail("read before clean worker reap"))
    with pytest.raises(ValueError, match="clean actual worker reap"):
        asyncio.run(h.owner.validate_mock_lease())
    assert h.lease.readers == []


def test_repeated_cancellation(monkeypatch):
    h = public_harness(monkeypatch, allow_custody=True)
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        cancellations = []
        async def run_once():
            h.calls.append("run")
            entered.set()
            while not finish.is_set():
                try:
                    await finish.wait()
                except asyncio.CancelledError:
                    cancellations.append(1)
            h.calls.append("mock-joined")
            raise asyncio.CancelledError()
        h.owner.run_once = run_once
        task = asyncio.create_task(runner.run_engineering_isolated_once(h.request, **h.kwargs))
        await entered.wait()
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0)
            assert "release" not in h.calls
        assert cancellations == [1, 1, 1]
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert h.calls[-2:] == ["mock-joined", "release"]
        assert h.calls.count("release") == 1
    asyncio.run(scenario())


def test_unknown_reap_cancellation_retains_owner(monkeypatch):
    h = public_harness(monkeypatch, allow_custody=True)
    primary = asyncio.CancelledError()
    h.owner.run_error = primary
    h.owner.release_error = RuntimeError("mock unknown reap")
    with pytest.raises(runner.IsolatedCustodyError) as caught:
        asyncio.run(runner.run_engineering_isolated_once(h.request, **h.kwargs))
    assert caught.value.owner is h.owner and caught.value.primary is primary
    assert h.calls[-2:] == ["run", "release"]
    assert "validate" not in h.calls
    assert runner._RETAINED_FAILURES.pop() is caught.value


def test_stdout_text_is_not_completion():
    decoder = transport._EnvelopeDecoder("a" * 64, "stdout", 1024, None)
    with pytest.raises(ValueError):
        decoder(b"training completed successfully")
    body = b"training completed successfully"
    decoder = transport._EnvelopeDecoder("a" * 64, "stdout", 1024, None)
    decoder(b"D" + len(body).to_bytes(4, "big") + body)
    with pytest.raises(ValueError, match="terminal"):
        decoder.finish()


def test_source_guards_and_existing_entrypoints():
    tree = ast.parse(inspect.getsource(runner))
    assert not any(isinstance(node, ast.ImportFrom) and node.module
                   and node.module.split(".")[0] == "modal" for node in ast.walk(tree))
    worker = inspect.getsource(program.run_prepared_worker)
    assert "original.NATIVE_ARGV" in worker and "original.VERIFY_ARGV" in worker
    for forbidden in ("_dispatch_sdk(", "_stop_once(", "begin_gpu_window(",
                      "open_app(", "create_once(", "run_engineering_once("):
        assert forbidden not in worker
    assert "synchronizer._get_loop(start=False)" in inspect.getsource(program._require_sdk_loop)
    # C neither reimplements nor weakens the original native/verifier.
    assert "native._worker_main(native._REQUEST_FILE)" in inspect.getsource(original._run_native_mode)
    assert "verify_remote_exported_artifacts" in inspect.getsource(original._load_remote_verifier)
    assert "os.chdir('/opt/qualification/source')" in original.NATIVE_ARGV[2]
    assert "sys.path.insert(0,'/opt/qualification/source')" in original.VERIFY_ARGV[2]


def test_heaviest_frozen_manifest_metadata():
    # Independent JSON arithmetic from frozen parent gates, synthetic metadata
    # ONLY. No member content, model registration or native request approval.
    def wheel_key(index):
        return "/".join((f"{index:04}" + "a" * 251, "b" * 255,
                         "c" * 255, "d" * 254, "e"))
    encode = lambda obj: json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode("ascii")
    rows = [dict(root="wheels", key=wheel_key(i),
                 size=10_000_000 if i < 499 else 1_000_000,
                 sha256="0" * 64, snapshot_key=f"{i:064x}") for i in range(4096)]
    request_row = dict(root="request", key="request.json", size=1048576,
                       sha256="0" * 64, snapshot_key=f"{4096:064x}")
    upper = 20 + 4096 * 1226 + 212 + 4096
    assert upper == 5026024 < 8388608
    synthetic = encode(dict(v=1, entries=sorted(
        rows + [request_row], key=lambda row: (row["root"], row["key"]))))
    assert len(synthetic) == 5014235
    with pytest.raises(ValueError, match="RPC source"):
        c.decode_manifest(synthetic)
    rows[-1].update(root="source", key=c.RPC_SOURCE_KEY)
    raw = encode(dict(v=1, entries=sorted(
        rows + [request_row], key=lambda row: (row["root"], row["key"]))))
    assert len(raw) == 5013242
    decoded = c.decode_manifest(raw)
    assert len(decoded) == 4097 and c.encode_manifest(decoded) == raw


def test_snapshot_4097_rows_one_member_fd(tmp_path):
    root = tmp_path.resolve() / "maximum-owned-snapshots"
    root.mkdir(mode=0o700)
    rows = [c.ManifestEntry("source", c.RPC_SOURCE_KEY, 1, sha(b"x"), "0" * 64)]
    rows += [c.ManifestEntry("wheels", f"w{i}", 1, sha(b"x"), f"{i + 1:064x}")
             for i in range(4095)]
    rows.append(c.ManifestEntry("request", "request.json", 1, sha(b"x"), f"{4096:064x}"))
    rows = tuple(sorted(rows, key=lambda row: (row.root, row.key)))
    c.validate_entries(rows)
    for row in rows:
        _write_new(root / row.snapshot_key, b"x")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with program._SnapshotInventory(
            fd, rows, deadline=program.time.monotonic() + 30) as snapshots:
            stream = snapshots.stream()
            count = 0
            try:
                for snapshot in stream:
                    assert len(snapshots.fds) == 1
                    assert b"".join(snapshot.chunks()) == b"x"
                    count += 1
            finally:
                stream.close()
            assert count == 4097 and snapshots.fds == []
    finally:
        os.close(fd)


def test_independent_same_bytes_fd_identity(monkeypatch, owned_inputs):
    bundle = owned_inputs
    replacement = bundle.root / "same-bytes-different-inode"
    _write_new(replacement, bundle.inputs.request_payload)
    other = os.open(replacement, os.O_RDONLY)
    fd = bundle.inputs.fds.request
    real_read = os.read
    replaced = []
    try:
        def swapped_read(number, count):
            raw = real_read(number, count)
            if number == fd and not replaced:
                # Preserve byte/hash result, change only opened object identity.
                os.lseek(other, len(bundle.inputs.request_payload), os.SEEK_SET)
                os.dup2(other, fd)
                replaced.append(1)
            return raw
        with monkeypatch.context() as patch:
            patch.setattr(program.os, "read", swapped_read)
            with pytest.raises(ValueError, match="identity changed"):
                program._read_fd(
                    fd, limit=c.REQUEST_LIMIT, size=bundle.launch.request_size,
                    sha256=bundle.launch.request_sha256, readonly=True)
        assert replaced == [1]
    finally:
        os.close(other)


def test_unknown_c_read_close_never_releases_owner(monkeypatch, owned_inputs):
    bundle = owned_inputs
    inventory = program._SnapshotInventory(
        bundle.inputs.fds.snapshot_dir, bundle.inputs.entries,
        deadline=program.time.monotonic() + 5)
    actual_close = os.close
    member_fd = None
    baseline = len(program._RETAINED_WORKER_FAILURES)
    try:
        with pytest.raises(program.WorkerLocalCustodyError) as caught:
            with inventory:
                with inventory.member(bundle.inputs.entries[0]) as snapshot:
                    member_fd = snapshot.fd
                    def close_unknown(fd):
                        if fd == member_fd:
                            raise OSError("MOCK close failed before kernel close")
                        actual_close(fd)
                    monkeypatch.setattr(program.os, "close", close_unknown)
        owner = MockOwner((), [])
        with pytest.raises(runner.IsolatedCustodyError) as retained:
            runner._release(owner, caught.value)
        assert owner.calls == []
        assert retained.value.owner is owner and retained.value.primary is caught.value
        assert inventory.fds == [member_fd]
        os.fstat(bundle.inputs.fds.snapshot_dir)
        os.fstat(bundle.inputs.fds.export_parent)
        assert runner._RETAINED_FAILURES.pop() is retained.value
    finally:
        # Fixture alone knows mock raised BEFORE the real close. Production
        # never retries an unknown close or drops its retained owner.
        monkeypatch.setattr(program.os, "close", actual_close)
        if member_fd is not None:
            actual_close(member_fd)
        del program._RETAINED_WORKER_FAILURES[baseline:]


def test_default_joined_validator_does_not_invent_custody(owned_inputs):
    execution = execution_for(c.WorkerProgramResult(1, "0" * 64))
    class UnsealedOwner:
        def take_validated_original(self, **kwargs):
            raise ValueError("no owner-sealed validation")
    with pytest.raises(ValueError, match="owner-sealed"):
        runner.validate_joined_outcome(
            owned_inputs.request, owner=UnsealedOwner(), prepared=owned_inputs.prepared,
            execution=execution, export_root=owned_inputs.root / "export")


@pytest.mark.parametrize("field", ["request", "manifest", "launch"])
def test_writer_must_return_bound_buffers(monkeypatch, field):
    items, calls = approved(), []
    owner = MockOwner(items, calls)
    monkeypatch.setattr(runner, "serialize_original_request", lambda request:
                        runner.OriginalTransport(b"original", tuple(
                            asset(item) for item in items if item.root != "wheels")))
    if field == "request":
        real_write = owner.writer.write_request
        def changed_request(payload):
            return replace(real_write(payload), sha256="0" * 64)
        owner.writer.write_request = changed_request
    else:
        real_seal = owner.writer.seal
        def changed_seal(entries, launch):
            return replace(real_seal(entries, launch), **{field + "_sha256": "0" * 64})
        owner.writer.seal = changed_seal
    with pytest.raises(ValueError):
        runner.prepare_isolated_inputs(
            object(), owner=owner, uploads=items, setup_argv=SETUP,
            export_root=Path("/mock/export"), launch=MockPinnedLaunch(calls))


@pytest.mark.parametrize("seconds", [150, 1801])
def test_deadlines_refuse_expired_work_or_renewed_window(seconds):
    host = MockHost()
    host.end_ns = program.time.monotonic_ns() + seconds * c.NS
    with pytest.raises(ValueError):
        program._deadlines(host, launch_for())


class MockRegisteredReader:
    """Tiny-file A stand-in, NOT actual anchored owner/registry authority.

    Actual local bytes/permissions/identity are checked. Only tests reopen these
    newly owned paths. Production C receives no path/FD operations from this mock.
    """

    def __init__(self, lease, key, path):
        self.lease, self.key, self.path = lease, key, path
        self.fd, self.closed, self.close_calls = None, False, 0
        self.closed_identity_checks = 0
        lease.readers.append(self)  # Reserve before open or post-open checks.
        self.fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(self.fd)
            self._regular(info)
            self.pin = original._identity(info)
            self._identity()
        except BaseException:
            self.close()
            raise

    def _regular(self, info):
        c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                  and stat.S_IMODE(info.st_mode) == 0o600
                  and info.st_uid == os.getuid(), "mock owner600/singlelink file")

    def _identity(self):
        named = self.path.lstat()
        self._regular(named)
        c.require(original._identity(named) == self.pin, "mock retained named identity")
        if not self.closed:
            c.require(original._identity(os.fstat(self.fd)) == self.pin,
                      "mock opened identity")

    async def read(self, maximum):
        self.lease._check()
        assert not self.closed and 1 <= maximum <= 65536
        self.lease.calls.append(("read", self.key, maximum))
        await self.lease.checkpoint()
        if self.lease.on_read is not None:
            await self.lease.on_read(self, maximum)
        self.lease._check()
        return os.read(self.fd, maximum)

    async def check_identity(self):
        self.lease._check()
        await self.lease.checkpoint()
        self.lease.calls.append("identity:" + ("closed:" if self.closed else "") + self.key)
        if self.closed:
            self.closed_identity_checks += 1
        self._identity()  # Closed case never fstats the old/reused FD number.
        self.lease._check()

    def close(self):
        self.close_calls += 1
        assert self.close_calls == 1
        if self.lease.close_error is not None:
            raise self.lease.close_error
        os.close(self.fd)
        self.closed = True
        self.lease.calls.append("close:" + self.key)


class MockReadLease:
    """Mock proof/liveness only. Does not prove a real reap or live fallback."""

    def __init__(self, owner):
        self.owner = owner
        self.end_ns = program.time.monotonic_ns() + 50 * c.NS
        self.read_deadline_ns = program.validation_booking(
            self.end_ns, owner.bundle.launch.timing.teardown_ns).read_ns
        self.worker_execution = owner.worker_execution
        self.readers, self.calls = [], owner.calls
        self.on_read = self.close_error = None
        self.checkpoints = 0

    def _check(self):
        self.owner._assert_parent_read_lease(
            self, request=self.owner.request, prepared=self.owner.prepared,
            export_root=self.owner.export_root)

    async def checkpoint(self):
        self._check()
        self.checkpoints += 1
        await asyncio.sleep(0)
        self._check()

    def open_outcome(self):
        self._check()
        self.calls.append("open:outcome")
        return MockRegisteredReader(self, "outcome", self.owner.bundle.root / "outcome")

    def open_export(self, key):
        self._check()
        self.calls.append("open:" + key)
        return MockRegisteredReader(self, key, self.owner.export_root / key)

    async def export_inventory(self):
        self._check()
        entries = []
        for root, dirs, files in os.walk(self.owner.export_root, followlinks=False):
            await self.checkpoint()
            base = Path(root)
            info = base.lstat()
            c.require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
                      and info.st_uid == os.getuid(), "mock owner700 directory")
            for name in sorted(dirs + files):
                await self.checkpoint()
                path = base / name
                info = path.lstat()
                kind = "directory" if stat.S_ISDIR(info.st_mode) else "file"
                if kind == "file":
                    c.require(stat.S_ISREG(info.st_mode), "mock regular inventory")
                entries.append(SimpleNamespace(
                    key=path.relative_to(self.owner.export_root).as_posix(),
                    kind=kind, size=0 if kind == "directory" else info.st_size))
        self._check()
        return tuple(entries)


class MockValidationOwner:
    """Explicit mock of frozen A bridge. Actual A acceptance remains parent work."""

    def __init__(self, bundle, execution):
        self.bundle, self.request, self.prepared = bundle, bundle.request, bundle.prepared
        self.export_root = bundle.root / "export"
        self.execution = execution
        self.worker_execution = replace(
            execution, children=tuple(x for x in execution.children if x.role == "worker"),
            stop_command="NOT_EXECUTED")
        self.calls, self.registered = [], False
        self.sealed, self.worker_reaped, self.guards_live = False, False, True
        self.invalid = self.used = self.joined = False
        self.data = self.lease = self.active_lease = None

    def register_parent_validation(self, *, request, prepared, export_root):
        c.require(self.sealed and not self.registered, "mock registration once after seal")
        c.require(request is self.request and prepared is self.prepared
                  and export_root is self.export_root, "mock registration links")
        self.registered = True
        self.calls.append("register")
        self.validator = runner._make_parent_validator(self, request, prepared, export_root)

    def issue_mock_lease(self):
        assert self.registered and self.worker_reaped and self.lease is None
        self.calls.append("mock-worker-reaped")
        self.lease = self.active_lease = MockReadLease(self)
        return self.lease

    def _assert_parent_read_lease(self, lease, *, request, prepared, export_root):
        c.require(self.registered and request is self.request and prepared is self.prepared
                  and export_root is self.export_root, "mock exact registration links")
        c.require(type(lease) is MockReadLease and lease is self.active_lease
                  and lease.owner is self and lease.worker_execution is self.worker_execution,
                  "mock active lease/proof identity")
        c.require(self.worker_reaped and self.guards_live and not self.invalid,
                  "mock worker proof/guards invalid")
        c.require(program.time.monotonic_ns() < lease.read_deadline_ns <= lease.end_ns,
                  "mock fixed validation deadline expired")

    async def validate_mock_lease(self):
        try:
            return await self.validator.validate(self.lease)
        except BaseException:
            # Stand-in for A's awaited invalidation and shutdown, NOT real joins.
            self.invalid, self.guards_live, self.active_lease = True, False, None
            self.calls.append("mock-invalidated")
            raise

    def join_mock_guards(self, data):
        assert type(data) is runner._ValidatedParentData
        assert data.owner is self and data.request is self.request
        assert data.prepared is self.prepared and data.export_root is self.export_root
        assert data.lease is self.lease and data.worker_execution is self.worker_execution
        assert type(data.original) is original.EngineeringRunOutcome
        assert not self.invalid and self.guards_live
        assert all(r.closed and r.close_calls == 1 for r in self.lease.readers)
        self.data = data
        self.calls.extend(("mock-data-sealed", "mock-normal-shutdown", "mock-all3-joined"))
        self.joined, self.guards_live, self.active_lease = True, False, None

    def take_validated_original(self, *, request, prepared, execution, export_root):
        c.require(request is self.request and prepared is self.prepared
                  and execution is self.execution and export_root is self.export_root,
                  "mock exact publication links")
        c.require(self.joined and self.data is not None and not self.used
                  and not self.invalid, "mock joined one-use publication")
        self.used = True
        self.calls.append("take")
        return self.data.original


def leased_harness(monkeypatch, bundle, execution):
    from train import native_qualification as native
    monkeypatch.setattr(native, "_request_binding", lambda request: BINDING)
    owner = MockValidationOwner(bundle, execution)
    owner.sealed = True
    owner.register_parent_validation(
        request=owner.request, prepared=owner.prepared, export_root=owner.export_root)
    owner.worker_reaped = True
    lease = owner.issue_mock_lease()
    return SimpleNamespace(
        owner=owner, lease=lease, request=owner.request, prepared=owner.prepared,
        execution=execution, export_root=owner.export_root)


def validated_harness(monkeypatch, bundle):
    _, result, _ = worker_run(monkeypatch, bundle)
    return leased_harness(monkeypatch, bundle, execution_for(result))


def test_registration_once_after_seal_and_fixed_data_fields(monkeypatch, owned_inputs):
    owner = MockValidationOwner(owned_inputs, execution_for(c.WorkerProgramResult(1, "0" * 64)))
    args = dict(request=owner.request, prepared=owner.prepared, export_root=owner.export_root)
    with pytest.raises(ValueError, match="once after seal"):
        owner.register_parent_validation(**args)
    owner.sealed = True
    owner.register_parent_validation(**args)
    with pytest.raises(ValueError, match="once after seal"):
        owner.register_parent_validation(**args)
    assert owner.calls == ["register"]
    assert set(runner._ValidatedParentData.__dataclass_fields__) == {
        "owner", "request", "prepared", "export_root", "lease", "worker_execution", "original"}
    assert runner._ValidatedParentData.__dataclass_params__.frozen
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="parent-local"):
            operation(owner.validator)


@pytest.mark.parametrize("mutation", [
    "foreign-request", "copied-request", "foreign-prepared", "copied-prepared",
    "foreign-owner", "copied-owner", "copied-root", "foreign-lease", "copied-lease",
    "dto-lease", "copied-proof", "unreaped", "controller-eof", "gate-eof", "replay",
])
def test_validator_registration_links_before_reads(monkeypatch, owned_inputs, mutation):
    h = leased_harness(monkeypatch, owned_inputs, execution_for(c.WorkerProgramResult(1, "0" * 64)))
    validator, lease = h.owner.validator, h.lease
    if mutation == "foreign-request":
        validator = replace(validator, request=object())
    elif mutation == "copied-request":
        validator = replace(validator, request=copy.copy(h.request))
    elif mutation == "foreign-prepared":
        validator = replace(validator, prepared=object())
    elif mutation == "copied-prepared":
        validator = replace(validator, prepared=replace(h.prepared))
    elif mutation == "foreign-owner":
        validator = replace(validator, owner=MockValidationOwner(owned_inputs, h.execution))
    elif mutation == "copied-owner":
        validator = replace(validator, owner=copy.copy(h.owner))
    elif mutation == "copied-root":
        validator = replace(validator, export_root=Path(str(h.export_root)))
    elif mutation == "foreign-lease":
        lease = MockReadLease(h.owner)
    elif mutation == "copied-lease":
        lease = copy.copy(h.lease)
    elif mutation == "dto-lease":
        lease = h.prepared
    elif mutation == "copied-proof":
        h.lease.worker_execution = replace(h.lease.worker_execution)
    elif mutation == "unreaped":
        h.owner.worker_reaped = False
    elif mutation in {"controller-eof", "gate-eof"}:
        h.owner.guards_live = False
    else:
        h.owner.invalid, h.owner.active_lease = True, None
    with pytest.raises(ValueError):
        asyncio.run(validator.validate(lease))
    assert h.lease.readers == [] and not any(
        type(x) is str and x.startswith("open:") for x in h.owner.calls)


def test_final_publication_zero_io_hash_or_lease(monkeypatch, owned_inputs):
    h = validated_harness(monkeypatch, owned_inputs)
    data = asyncio.run(h.owner.validate_mock_lease())
    assert h.owner.guards_live and not h.owner.joined
    with pytest.raises(ValueError, match="joined one-use"):
        runner.validate_joined_outcome(
            h.request, owner=h.owner, prepared=h.prepared, execution=h.execution,
            export_root=h.export_root)
    worker_only = h.lease.worker_execution
    with pytest.raises(ValueError, match="all three"):
        runner.validate_joined_outcome(
            h.request, owner=h.owner, prepared=h.prepared, execution=worker_only,
            export_root=h.export_root)
    assert "take" not in h.owner.calls
    h.owner.join_mock_guards(data)
    before = list(h.owner.calls)
    def forbidden(*args, **kwargs):
        pytest.fail("final publication attempted filesystem/hash/lease work")
    with monkeypatch.context() as patch:
        for name in ("open", "read", "stat", "lstat", "fstat", "scandir"):
            patch.setattr(os, name, forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(io, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(hashlib, "sha256", forbidden)
        patch.setattr(hashlib, "new", forbidden)
        patch.setattr(h.lease, "open_outcome", forbidden)
        patch.setattr(h.lease, "open_export", forbidden)
        patch.setattr(h.lease, "checkpoint", forbidden)
        patch.setattr(h.lease, "export_inventory", forbidden)
        patch.setattr(h.owner, "issue_mock_lease", forbidden)
        patch.setattr(runner, "serialize_original_request", forbidden)
        patch.setattr(runner, "_make_parent_validator", forbidden)
        result = runner.validate_joined_outcome(
            h.request, owner=h.owner, prepared=h.prepared, execution=h.execution,
            export_root=h.export_root)
    assert result.original_outcome is data.original
    assert h.owner.calls == before + ["take"]
    assert result.children is h.execution.children and result.local_containment == "JOINED"
    assert result.remote_termination == result.charged_end == "UNKNOWN"
    assert h.owner.calls.index("mock-worker-reaped") < h.owner.calls.index("open:outcome")
    assert h.owner.calls.index("mock-data-sealed") < h.owner.calls.index("mock-normal-shutdown")
    assert h.owner.calls.index("mock-all3-joined") < h.owner.calls.index("take")
    with pytest.raises(ValueError, match="one-use"):
        runner.validate_joined_outcome(
            h.request, owner=h.owner, prepared=h.prepared, execution=h.execution,
            export_root=h.export_root)
    with pytest.raises(ValueError, match="active lease"):
        asyncio.run(h.owner.validator.validate(h.lease))


@pytest.mark.parametrize("mutation", ["request", "prepared", "execution", "export-root", "foreign-execution"])
def test_final_publication_exact_links(monkeypatch, owned_inputs, mutation):
    h = validated_harness(monkeypatch, owned_inputs)
    data = asyncio.run(h.owner.validate_mock_lease())
    h.owner.join_mock_guards(data)
    args = dict(owner=h.owner, prepared=h.prepared, execution=h.execution, export_root=h.export_root)
    request = h.request
    if mutation == "request":
        request = copy.copy(request)
    elif mutation == "prepared":
        args["prepared"] = replace(h.prepared)
    elif mutation == "execution":
        args["execution"] = replace(h.execution)
    elif mutation == "foreign-execution":
        args["execution"] = replace(h.execution, outcome_sha256="0" * 64)
    else:
        args["export_root"] = Path(str(h.export_root))
    with pytest.raises(ValueError, match="publication links"):
        runner.validate_joined_outcome(request, **args)
    assert not h.owner.used and "take" not in h.owner.calls


def test_streaming_bounds_checkpoints_and_fixed_cutoff():
    """Real C async reader on bytes, explicitly mocked generation/liveness."""
    class MemoryLease:
        end_ns = program.time.monotonic_ns() + 10 * c.NS
        read_deadline_ns = end_ns - c.NS
        worker_execution = object()
        def __init__(self):
            self.checkpoints = 0
        async def checkpoint(self):
            self.checkpoints += 1
            await asyncio.sleep(0)
    class Reader:
        def __init__(self, lease):
            self.raw, self.offset, self.bounds = b"x" * (2 * 65536 + 1), 0, []
            self.closed, self.checks = 0, 0
            self.lease = lease
        async def read(self, maximum):
            self.bounds.append((maximum, self.lease.checkpoints))
            block = self.raw[self.offset:self.offset + maximum]
            self.offset += len(block)
            await asyncio.sleep(0)
            return block
        async def check_identity(self):
            self.checks += 1
            await asyncio.sleep(0)
        def close(self):
            self.closed += 1
    lease = MemoryLease()
    reader = Reader(lease)
    lease.open_export = lambda key: reader
    reads = program._LeaseReads(lease, lease.worker_execution, lease.end_ns, lease.read_deadline_ns)
    fixed = reads.read_ns
    assert asyncio.run(reads.read("tiny", size=len(reader.raw), sha256=sha(reader.raw),
                                  retain=True)) == reader.raw
    assert [x[0] for x in reader.bounds] == [65536, 65536, 2, 1]
    assert all(b[1] > a[1] for a, b in zip(reader.bounds, reader.bounds[1:]))
    assert lease.checkpoints >= 2 * len(reader.bounds) + 4
    assert reader.closed == 1 and reader.checks == 2 and reads.read_ns == fixed
    assert reads.verified == [reader]


@pytest.mark.parametrize("mutation", ["equal", "slow", "renewed", "guard-loss"])
def test_lease_deadline_and_guard_loss_invalidate(monkeypatch, owned_inputs, mutation):
    h = validated_harness(monkeypatch, owned_inputs)
    entered = []
    async def interrupt(reader, maximum):
        entered.append(reader.key)
        if mutation == "slow":
            await asyncio.sleep(1)
        elif mutation == "renewed":
            h.lease.read_deadline_ns += c.NS
        elif mutation == "guard-loss":
            h.owner.guards_live = False
    h.lease.on_read = interrupt
    if mutation == "equal":
        now = program.time.monotonic_ns()
        h.lease.read_deadline_ns = now
        monkeypatch.setattr(program.time, "monotonic_ns", lambda: now)
    elif mutation == "slow":
        h.lease.read_deadline_ns = program.time.monotonic_ns() + 100_000_000
    if mutation == "renewed":
        # C must reject renewal even if the mock owner permits the new value.
        error_type = ValueError
    else:
        error_type = TimeoutError if mutation == "slow" else ValueError
    with pytest.raises(error_type):
        asyncio.run(h.owner.validate_mock_lease())
    assert h.owner.invalid and h.owner.data is None and h.owner.active_lease is None
    assert all(r.closed and r.close_calls == 1 for r in h.lease.readers)
    assert "take" not in h.owner.calls
    assert bool(entered) is (mutation != "equal")


@pytest.mark.parametrize("at", ["outcome", "evidence", "bulk"])
def test_cancelled_leased_reads_never_seal(monkeypatch, owned_inputs, at):
    h = validated_harness(monkeypatch, owned_inputs)
    async def scenario():
        entered = asyncio.Event()
        async def pause(reader, maximum):
            matches = (reader.key == "outcome" if at == "outcome" else
                       reader.key.startswith("evidence/") if at == "evidence" else
                       reader.key.startswith("checkpoint-"))
            if matches:
                entered.set()
                await asyncio.Event().wait()
        h.lease.on_read = pause
        task = asyncio.create_task(h.owner.validate_mock_lease())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert h.owner.invalid and h.owner.data is None
        assert all(r.closed and r.close_calls == 1 for r in h.lease.readers)
        with pytest.raises(ValueError, match="active lease"):
            await h.owner.validator.validate(h.lease)
        assert "take" not in h.owner.calls
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "permission-file", "permission-directory", "extra-directory", "missing-file",
    "symlink", "hardlink", "identity", "outcome-permission",
])
def test_leased_content_and_inventory_refusals(monkeypatch, owned_inputs, mutation):
    h = validated_harness(monkeypatch, owned_inputs)
    path = h.export_root / "checkpoint-1/optimizer.pt"
    if mutation == "permission-file":
        path.chmod(0o640)
    elif mutation == "permission-directory":
        path.parent.chmod(0o750)
    elif mutation == "extra-directory":
        (h.export_root / "empty-extra").mkdir(mode=0o700)
    elif mutation == "missing-file":
        path.unlink()
    elif mutation in {"symlink", "hardlink"}:
        other = owned_inputs.root / "new-owned-alias"
        _write_new(other, b"tiny")
        path.unlink()
        path.symlink_to(other) if mutation == "symlink" else os.link(other, path)
    elif mutation == "outcome-permission":
        (owned_inputs.root / "outcome").chmod(0o640)
    else:
        replaced = []
        async def replace_during_read(reader, maximum):
            if reader.key == "checkpoint-1/optimizer.pt" and not replaced:
                replaced.append(1)
                path.rename(path.with_name("replaced"))
                _write_new(path, b"tiny")
        h.lease.on_read = replace_during_read
    with pytest.raises(ValueError):
        asyncio.run(h.owner.validate_mock_lease())
    assert h.owner.data is None and "take" not in h.owner.calls
    assert all(r.closed and r.close_calls == 1 for r in h.lease.readers)


@pytest.mark.parametrize("mutation", ["changed", "replaced"])
def test_earlier_closed_export_changed_during_later_read(monkeypatch, owned_inputs, mutation):
    h = validated_harness(monkeypatch, owned_inputs)
    earlier = "checkpoint-1/optimizer.pt"
    later = "checkpoint-2/optimizer.pt"
    changed = []
    async def change_earlier(reader, maximum):
        if reader.key != later or changed:
            return
        prior = next(r for r in h.lease.readers if r.key == earlier)
        assert prior.closed and prior.close_calls == 1 and prior.closed_identity_checks == 0
        path = h.export_root / earlier
        if mutation == "changed":
            path.write_bytes(b"FAIL")  # Same size; inventory still matches.
        else:
            path.rename(owned_inputs.root / "retained-old-export-inode")
            _write_new(path, b"tiny")  # Same size/hash, different retained inode.
        changed.append(prior)
    h.lease.on_read = change_earlier
    with pytest.raises(ValueError, match="retained named identity"):
        asyncio.run(h.owner.validate_mock_lease())
    assert len(changed) == 1 and changed[0].closed_identity_checks == 1
    assert h.owner.calls.index("close:" + earlier) < h.owner.calls.index("open:" + later)
    assert h.owner.calls[-2:] == ["identity:closed:" + earlier, "mock-invalidated"]
    assert h.owner.data is None and all(r.close_calls == 1 for r in h.lease.readers)


def test_evidence_failure_precedes_all_bulk_opens(monkeypatch, owned_inputs):
    h = validated_harness(monkeypatch, owned_inputs)
    path = h.export_root / "evidence" / original._OBSERVATIONS_KEY
    path.write_bytes(b"!" * path.stat().st_size)
    with pytest.raises(ValueError):
        asyncio.run(h.owner.validate_mock_lease())
    assert not any(type(x) is str and x.startswith("open:checkpoint-") for x in h.owner.calls)
    assert h.owner.invalid and h.owner.data is None


def test_fixed_owner_assertions_before_reads_after_sweep_and_before_return(monkeypatch, owned_inputs):
    h = validated_harness(monkeypatch, owned_inputs)
    assertions = []
    fixed_assert = runner._ParentValidator._assert
    def observe(validator, lease):
        assertions.append((len(lease.readers),
                           tuple(r.closed_identity_checks for r in lease.readers)))
        fixed_assert(validator, lease)
    monkeypatch.setattr(runner._ParentValidator, "_assert", observe)
    data = asyncio.run(h.owner.validate_mock_lease())
    assert assertions[0] == (0, ())
    assert len(assertions) == 3
    assert all(count == 1 for count in assertions[1][1])
    assert assertions[1] == assertions[2]
    assert data.owner is h.owner and data.request is h.request
    assert data.prepared is h.prepared and data.export_root is h.export_root
    assert data.lease is h.lease and data.worker_execution is h.lease.worker_execution
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="parent-local"):
            operation(data)


@pytest.mark.parametrize("target", ["snapshot", "directory", "export"])
def test_post_open_validation_and_failed_close_retain_actual_custody(monkeypatch, owned_inputs, target):
    bundle = owned_inputs
    primary = ValueError("MOCK first post-open validation failure")
    cleanup = OSError("MOCK close failed before kernel close")
    acquired, close_attempts = [], []
    actual_open, actual_fstat, actual_close = os.open, os.fstat, os.close
    baseline = len(program._RETAINED_WORKER_FAILURES)
    inventory = program._SnapshotInventory(
        bundle.inputs.fds.snapshot_dir, bundle.inputs.entries,
        deadline=program.time.monotonic() + 5)
    anchor = program._BorrowedAnchor(bundle.inputs.fds.export_parent)
    tree = program._AnchoredExportTree(
        bundle.inputs.fds.export_parent, "new-owned-custody-tree",
        deadline=program.time.monotonic() + 5)
    row = bundle.inputs.entries[0]
    name = row.snapshot_key if target == "snapshot" else (
        "new-owned-directory" if target == "directory" else "new-owned-export")
    if target == "directory":
        (bundle.root / name).mkdir(mode=0o700)

    def records():
        return inventory.records if target == "snapshot" else (
            anchor._records if target == "directory" else tree.records)

    def opened(path, *args, **kwargs):
        fd = actual_open(path, *args, **kwargs)
        if path == name:
            acquired.append(fd)
        return fd

    def post_open_check(fd):
        if acquired and fd == acquired[0]:
            record = records()[-1]
            assert record.fd == fd and record.anchor is not None
            assert not record.attempted and not record.closed
            raise primary
        return actual_fstat(fd)

    def failed_close(fd):
        if acquired and fd == acquired[0]:
            close_attempts.append(fd)
            raise cleanup
        return actual_close(fd)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(program.os, "open", opened)
            patch.setattr(program.os, "fstat", post_open_check)
            patch.setattr(program.os, "close", failed_close)
            with pytest.raises(program.WorkerLocalCustodyError) as caught:
                if target == "snapshot":
                    with inventory:
                        with inventory.member(row):
                            pytest.fail("post-open check did not fail")
                elif target == "directory":
                    anchor.child(bundle.inputs.fds.export_parent, name)
                else:
                    with tree:
                        tree.create(name)
            record = records()[-1]
            assert len(acquired) == 1 and record.fd == acquired[0]
            assert record.failure.primary is primary and record.failure.errors == (cleanup,)
            assert record.attempted and not record.closed
            assert record.anchor is (inventory.anchor if target == "snapshot" else
                                     anchor if target == "directory" else tree.anchor)
            if target == "export":
                assert caught.value.primary is primary
                assert caught.value.errors[0] is record.failure
            else:
                assert caught.value is record.failure
            # Re-observation never retries an ambiguous actual close.
            with pytest.raises(program.WorkerLocalCustodyError):
                record.close(None)
            assert close_attempts == acquired
        actual_fstat(record.fd)  # Retained ACTUAL descriptor, not just a label.
        actual_fstat(record.anchor._borrowed_fd)
        assert program._RETAINED_WORKER_FAILURES[baseline:]
    finally:
        # Fixture knows failed_close did not enter the kernel. Only this mock
        # cleanup may close it; production must retain the ambiguous generation.
        for owned in (inventory.records, anchor._records,
                      tree.records, tree.anchor._records if hasattr(tree, "anchor") else []):
            for record in owned:
                if record.fd is not None and not record.closed:
                    actual_close(record.fd)
                    record.closed = True
        del program._RETAINED_WORKER_FAILURES[baseline:]


def test_parent_failed_reader_close_retains_lease_primary_and_owner(monkeypatch, owned_inputs):
    h = validated_harness(monkeypatch, owned_inputs)
    primary = ValueError("MOCK read failure")
    cleanup = OSError("MOCK parent close unknown before kernel close")
    async def failed_read(reader, maximum):
        raise primary
    h.lease.on_read, h.lease.close_error = failed_read, cleanup
    release_calls = []
    h.owner.release_joined = lambda: release_calls.append("release")
    baseline = len(program._RETAINED_PARENT_FAILURES)
    try:
        with pytest.raises(program.ParentReaderCustodyError) as caught:
            asyncio.run(h.owner.validate_mock_lease())
        failure = caught.value
        assert failure.lease is h.lease and failure.reader is h.lease.readers[0]
        assert failure.primary is primary and failure.cleanup is cleanup
        assert failure.reader.close_calls == 1 and not failure.reader.closed
        os.fstat(failure.reader.fd)
        assert program._RETAINED_PARENT_FAILURES[-1] is failure
        with pytest.raises(runner.IsolatedCustodyError) as retained:
            runner._release(h.owner, failure)
        assert retained.value.owner is h.owner and retained.value.primary is failure
        assert runner._RETAINED_FAILURES.pop() is retained.value
        assert failure.reader.close_calls == 1 and release_calls == []
    finally:
        # Mock close_error is known to precede kernel close, unlike production.
        for reader in h.lease.readers:
            if not reader.closed:
                os.close(reader.fd)
                reader.closed = True
        del program._RETAINED_PARENT_FAILURES[baseline:]


def test_max_teardown_worker_booking_only_tightens_original_reserves(monkeypatch):
    now = 1000 * c.NS
    monkeypatch.setattr(program.time, "monotonic_ns", lambda: now)
    monkeypatch.setattr(program.time, "monotonic", lambda: now / c.NS)
    host = SimpleNamespace(end_ns=now + 1800 * c.NS)
    launch = launch_for(timing=c.StopTimingFacts(c.NS, 20_500_000_000, 5 * c.NS))
    actual_end = host.end_ns
    work, verify, export = program._deadlines(host, launch)
    # Independent arithmetic from frozen V229 maximum-T example, not helper
    # agreement with itself. Float rounding may only tighten these cutoffs.
    for actual, reserve in ((work, 185), (verify, 125), (export, 65)):
        expected = actual_end / c.NS - reserve
        assert expected - 0.000001 < actual <= expected
    assert verify - work == 60 and export - verify == 60
    assert host.end_ns == actual_end


def test_no_legacy_c_acquisition_or_parent_raw_fd_validation():
    assert "_validate_outcome_fds" not in vars(program)
    source = inspect.getsource(program)
    assert "original._open_regular(" not in source
    assert "super().child(" not in source
    parent_source = inspect.getsource(program._validate_outcome_lease)
    for forbidden in ("os.open(", "os.read(", "os.fstat(", "original._hash_fd(",
                      "to_thread(", "create_task(", "run_in_executor("):
        assert forbidden not in parent_source
    assert inspect.iscoroutinefunction(runner._ParentValidator.validate)
    assert inspect.iscoroutinefunction(program._validate_outcome_lease)


def test_unknown_close_never_retries_reused_fd_number(monkeypatch, owned_inputs):
    """Kernel-close-then-error mock, distinct from before-kernel-close tests."""
    root = owned_inputs.root
    _write_new(root / "new-owned-old-generation", b"old")
    _write_new(root / "new-owned-new-generation", b"new")
    anchor = program._BorrowedAnchor(owned_inputs.inputs.fds.export_parent)
    owner = SimpleNamespace(records=[])
    record = program._LocalFD(owner, anchor)
    owner.records.append(record)
    fd = record.acquire("new-owned-old-generation", os.O_RDONLY,
                        parent=owned_inputs.inputs.fds.export_parent)
    primary = ValueError("MOCK validation failure")
    cleanup = OSError("MOCK error AFTER successful kernel close")
    actual_close, replacement, attempts = os.close, None, []
    baseline = len(program._RETAINED_WORKER_FAILURES)
    def ambiguous(number):
        assert number == fd
        attempts.append(number)
        actual_close(number)
        raise cleanup
    try:
        with monkeypatch.context() as patch:
            patch.setattr(program.os, "close", ambiguous)
            with pytest.raises(program.WorkerLocalCustodyError) as caught:
                record.close(primary)
        replacement = os.open(root / "new-owned-new-generation", os.O_RDONLY)
        if replacement != fd:
            os.dup2(replacement, fd)
            actual_close(replacement)
            replacement = fd
        assert replacement == record.fd and record.attempted and not record.closed
        with pytest.raises(program.WorkerLocalCustodyError) as replay:
            record.close(None)
        assert replay.value is caught.value and attempts == [fd]
        assert caught.value.primary is primary and caught.value.errors == (cleanup,)
        assert caught.value.resources is record and record.anchor is anchor
        os.fstat(replacement)
        assert os.read(replacement, 3) == b"new"
    finally:
        if replacement is not None:
            actual_close(replacement)  # Fixture owns this distinct generation.
        del program._RETAINED_WORKER_FAILURES[baseline:]


@pytest.mark.parametrize("extra", [False, True])
def test_inventory_original_entry_limit_including_ancestor_directories(extra):
    """Synthetic metadata boundary only, zero files or remote authorities."""
    expected = {f"d{i}/f": {"size": 0} for i in range(10000)}
    expected.update({"evidence/" + key: {"size": 0} for key in original._EVIDENCE_KEYS})
    if extra:
        expected.pop("d0/f")
        expected["d0/extra/f"] = {"size": 0}
    entries = []
    for i in range(10000):
        entries.append(SimpleNamespace(key=f"d{i}", kind="directory", size=0))
        entries.append(SimpleNamespace(key=f"d{i}/f", kind="file", size=0))
    entries.append(SimpleNamespace(key="evidence", kind="directory", size=0))
    entries.extend(SimpleNamespace(key="evidence/" + key, kind="file", size=0)
                   for key in original._EVIDENCE_KEYS)
    assert len(entries) == 20004 and len(expected) == 10003
    class InventoryLease:
        end_ns = program.time.monotonic_ns() + 20 * c.NS
        read_deadline_ns = end_ns - c.NS
        worker_execution = object()
        def __init__(self):
            self.enumerations = self.checkpoints = 0
        async def checkpoint(self):
            self.checkpoints += 1
            await asyncio.sleep(0)
        async def export_inventory(self):
            self.enumerations += 1
            return tuple(entries)
    lease = InventoryLease()
    reads = program._LeaseReads(lease, lease.worker_execution, lease.end_ns, lease.read_deadline_ns)
    if extra:
        with pytest.raises(ValueError, match="directory entry cap"):
            asyncio.run(reads.inventory(expected))
        assert lease.enumerations == 0
    else:
        asyncio.run(reads.inventory(expected))
        assert lease.enumerations == 1 and lease.checkpoints >= 2 * len(entries)


def test_snapshot_open_nonblocking_on_fifo_substitution(monkeypatch, owned_inputs):
    """Real owned FIFO race; missing flag fails before a potentially blocking open."""
    bundle = owned_inputs
    row = bundle.inputs.entries[0]
    path = bundle.snapshot_root / row.snapshot_key
    actual_open = os.open
    acquired, calls = [], []

    def substitute(name, flags, mode=0o777, *, dir_fd=None):
        if name == row.snapshot_key and dir_fd == bundle.inputs.fds.snapshot_dir:
            calls.append(flags)
            assert flags & os.O_NONBLOCK, "snapshot open must be nonblocking"
            path.unlink()
            os.mkfifo(path, 0o600)
            fd = actual_open(name, flags, mode, dir_fd=dir_fd)
            acquired.append(fd)
            return fd
        return actual_open(name, flags, mode, dir_fd=dir_fd)

    inventory = program._SnapshotInventory(
        bundle.inputs.fds.snapshot_dir, bundle.inputs.entries,
        deadline=program.time.monotonic() + 5)
    with monkeypatch.context() as patch:
        patch.setattr(program.os, "open", substitute)
        with pytest.raises(ValueError, match="single-link regular file required"):
            with inventory:
                with inventory.member(row):
                    pytest.fail("FIFO snapshot reached content hashing")
    assert len(calls) == len(acquired) == 1
    assert calls[0] & os.O_NOFOLLOW and calls[0] & os.O_NONBLOCK
    record = inventory.records[-1]
    assert record.fd == acquired[0] and record.attempted and record.closed
    assert not inventory.fds and not inventory.close_errors
    with pytest.raises(OSError):
        os.fstat(acquired[0])

def test_worker_outcome_final_hash_cannot_overrun_export_booking(monkeypatch, owned_inputs):
    actual_time, actual_hash = program.time, original._hash_fd
    late = []
    monkeypatch.setattr(program, "time", SimpleNamespace(
        monotonic=lambda: late[0] if late else actual_time.monotonic(),
        monotonic_ns=actual_time.monotonic_ns))
    def hash_then_expire(fd, **kwargs):
        result = actual_hash(fd, **kwargs)
        if fd == owned_inputs.inputs.fds.outcome:
            late.append(kwargs["deadline"])
        return result
    monkeypatch.setattr(original, "_hash_fd", hash_then_expire)
    with pytest.raises(ValueError, match="worker export deadline expired"):
        worker_run(monkeypatch, owned_inputs)
    assert len(late) == 1
    wire = MockPipelineTransport.instances[-1]
    assert sum(type(row) is tuple and row[0] == original.NATIVE_ARGV
               for row in wire.calls) == 1
    assert sum(type(row) is tuple and row[0] == original.VERIFY_ARGV
               for row in wire.calls) == 1
