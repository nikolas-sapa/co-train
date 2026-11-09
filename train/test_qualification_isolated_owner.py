"""V251 fixture-only tests. SOURCEONLY UNRUN.

Fake process observations below are NOT actual reaps or provider evidence.
Only newly owned source, interpreter and SDK stand-ins are hashed. The original
launcher is substituted at its exact boundary; no real stager/signals/processes.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import inspect
import os
from pathlib import Path
import pickle
import socket
import stat
import sys
from types import SimpleNamespace
import time

import pytest

from train import guards, native_qualification as native
from train import qualification_engineering_host as authority
from train import qualification_isolated_contract as dto
from train import qualification_isolated_deadline as deadline
from train import qualification_isolated_owner as api
from train import qualification_isolated_run as adapter
from train import qualification_isolated_worker as worker
from train import qualification_isolated_program as program
from train import qualification_modal_host as common
from train import qualification_owned_stop as stop
from train.engineering_budget import (
    AncillaryEstimates, BudgetTerms, GpuWorkload, PreparationAccount,
    RateObservation, ResourceRates,
)
from train.qualification_image_plan import candidate_recipe, recipe_sha256
from train.qualification_isolated_validation import (
    minimum_remaining_ns, require_feasible, validation_booking,
)
from train.qualification_watchdog import TrustedTeardown
from bench.task import SqlTask

NS = dto.NS
SESSION = "ab" * 32
APP = "ap-" + "A" * 22
SANDBOX = "sb-" + "B" * 22
EMPTY = hashlib.sha256(b"").hexdigest()
_REAL_CLOSE = os.close
_REAL_RESERVATION_CLOSE = authority.AttemptReservation.close


def put(path, raw=b"x", mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def pin(path, key):
    raw = path.read_bytes()
    return dto.SourcePin(key, len(raw), hashlib.sha256(raw).hexdigest())


@pytest.fixture(autouse=True)
def prohibit_real_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("real process/signal/original stager forbidden")
    monkeypatch.setattr(api.subprocess, "Popen", forbidden)
    monkeypatch.setattr(api.os, "killpg", forbidden)
    monkeypatch.setattr(api.os, "waitpid", forbidden)
    monkeypatch.setattr(stop.launcher, "stage_trusted_teardown", forbidden)
    yield
    # Fixture teardown only, not a production release assertion.
    for retained in tuple(api._OWNERS.values()):
        for record in reversed(retained._registry.records):
            if record.handle is not None and not record.closed:
                try:
                    if record.kind == "descriptor":
                        _REAL_CLOSE(record.handle)
                    elif record.kind in {"socket", "iterator"}:
                        record.handle.close()
                    elif record.kind == "reservation":
                        _REAL_RESERVATION_CLOSE(record.handle, "failed")
                except OSError:
                    pass
    common._ACTIVE_HOST = None
    api._OWNERS.clear()
    api._PREFLIGHTS.clear()
    api._RETAINED_FAILURES.clear()
    worker._RETAINED_HOSTS.clear()
    worker._RETAINED_FAILURES.clear()
    deadline._RETAINED_CHILD_FAILURES.clear()


@pytest.fixture
def case(tmp_path, monkeypatch):
    root = tmp_path / "source"
    for key in api.WORKER_SOURCE_KEYS:
        put(root / key, ("# owned " + key + "\n").encode())
    sdk = tmp_path / "sdk"
    for key in api.SDK_REQUIRED_KEYS:
        put(sdk / key, ("# owned " + key + "\n").encode())
    executable = put(tmp_path / "owned/python", b"fixture-interpreter", 0o700)
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    export_parent = tmp_path / "export"
    export_parent.mkdir(mode=0o700)
    export = export_parent / "run"
    monkeypatch.setattr(api, "_DEPLOYED_ROOT", root)
    monkeypatch.setattr(guards, "REPO_ROOT", root)
    policy = put(tmp_path / "policy", b"owned independent policy")
    construction = put(root / "train/native_training.py", b"# fixture construction\n")
    construction_pin = pin(construction, "construction")
    monkeypatch.setattr(native, "_CONSTRUCTION_SHA", construction_pin.sha256)
    tasks = tuple(SqlTask(
        name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
        evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
        db_id=name, db_path=str(tmp_path / "data" / name / f"{name}.sqlite"),
        tier="simple", tier_source="derived", shape="fixture-select",
        coarse_shape="fixture-select", source="fixture") for name, _ in native._FIXTURES)
    request = native.QualificationRequest(
        tasks, tmp_path / "data", tmp_path / "model", export,
        (native.FilePin(construction, construction_pin.size, construction_pin.sha256),),
        tuple(native.FilePin(Path(t.db_path), 0, EMPTY) for t in tasks),
        native.FilePin(tmp_path / "inventory", 0, EMPTY), "sha256:" + "0" * 64,
        native.AttemptBounds(Decimal("25"), Decimal("0"), Decimal("25"),
                             600, 1024, 1024 * 1024, 60))
    items = tuple(SimpleNamespace(
        root="source", key=k, path=root / k,
        size=(root / k).stat().st_size, sha256=pin(root / k, k).sha256)
        for k in api.WORKER_SOURCE_KEYS)
    now = int(time.time())
    recipe = candidate_recipe()
    auth = authority.issue_engineering_authorization(
        request=request, policy_pin=native.FilePin(
            policy, policy.stat().st_size, hashlib.sha256(policy.read_bytes()).hexdigest()),
        terms=BudgetTerms(Decimal("25"), Decimal("5")),
        rates=ResourceRates("sandbox", *(
            RateObservation(Decimal("0.000001"), unit, "fixture", now - 1)
            for unit in ("USD/gpu-second", "USD/physical-core-second", "USD/GiB-second"))),
        workload=GpuWorkload(1, 4, Decimal("16"), 600),
        preparation=PreparationAccount(Decimal("1"), Decimal("0.5"), Decimal("2")),
        ancillary=AncillaryEstimates(Decimal("0.5"), Decimal("0.25"), Decimal("1")),
        now_seconds=now, expires_at_seconds=now + 3600, preparation_seconds=300,
        image_base_reference=recipe.base_reference,
        image_recipe_sha256=recipe_sha256(recipe), gpu_label="A100",
        uploads=tuple((i.root, i.key, i.size, i.sha256) for i in items),
        setup_argv=("python", "-m", "pip", "install", "--no-index"))
    binding = stop.OwnedAppStopBinding(
        interpreter=executable, interpreter_sha256=pin(executable, "python").sha256,
        adapter_sha256=pin(root / "train/modal_app_stop.py", "adapter").sha256,
        source_root=root / "train", sdk_root=sdk,
        sdk_pins={api._module_name(k): pin(sdk / k, k).sha256
                  for k in api.SDK_REQUIRED_KEYS},
        private_scratch=scratch,
        environment={"HOME": str(home), "PATH": f"{executable.parent}:/usr/bin:/bin"},
        rpc_seconds=1, ownership_confirmed=True)
    spec = dto.IsolatedOwnerSpec(
        executable, root, tuple(pin(root / k, k) for k in api.WORKER_SOURCE_KEYS),
        sdk, tuple(pin(sdk / k, k) for k in api.SDK_REQUIRED_KEYS),
        common.ResourceConfig("A100", (0.25, 4.0), (128, 16384)), binding,
        scratch, scratch / "evidence.json")
    return SimpleNamespace(request=request, auth=auth, spec=spec, items=items,
                           root=root, sdk=sdk, export=export, tmp=tmp_path)


def preflight(c, **overrides):
    args = dict(authorization=c.auth, owner_spec=c.spec, uploads=c.items,
                setup_argv=c.auth.setup_argv, export_root=c.export)
    args.update(overrides)
    return api.preflight_isolated(c.request, **args)


@pytest.fixture
def owner(case):
    result = api.admit_isolated_owner(preflight(case))
    yield result
    if not result._released and not result._running:
        try:
            result.release_joined()
        except api.CustodyError:
            pass  # Tests below assert the retained actual records/latch.


def prepare(c, o):
    launch = api.pin_worker_launch(o, owner_spec=c.spec)
    writer = o.preparation_writer()
    entries = [writer.snapshot_member(
        root=i.root, key=i.key, source_path=i.path, size=i.size, sha256=i.sha256)
        for i in c.items]
    entries.append(writer.write_request(b'{"fixture":1}'))
    entries = tuple(sorted(entries, key=lambda x: (x.root, x.key)))
    raw = dto.encode_manifest(entries)
    req = next(e for e in entries if e.root == "request")
    descriptor = launch.descriptor_for(
        request_size=req.size, request_sha256=req.sha256,
        manifest_size=len(raw), manifest_sha256=hashlib.sha256(raw).hexdigest())
    prepared = writer.seal(entries, descriptor)
    o.seal_inputs(prepared, launch)
    return prepared, launch


def register(c, o):
    prepared, launch = prepare(c, o)
    o.register_parent_validation(
        request=c.request, prepared=prepared, export_root=c.export)
    return prepared, launch


def test_frozen_surface():
    assert tuple(inspect.signature(api.preflight_isolated).parameters) == (
        "request", "authorization", "owner_spec", "uploads", "setup_argv", "export_root")
    assert tuple(inspect.signature(api.admit_isolated_owner).parameters) == ("preflight",)
    assert tuple(inspect.signature(api.pin_worker_launch).parameters) == ("owner", "owner_spec")
    assert tuple(inspect.signature(api.IsolatedOwner.run_once).parameters) == ("self",)
    assert tuple(inspect.signature(api.IsolatedOwner.release_joined).parameters) == ("self",)
    assert tuple(inspect.signature(api.IsolatedOwner.seal_inputs).parameters) == (
        "self", "prepared", "launch")
    for method, parameters in (
        (api.IsolatedOwner.preparation_writer, ("self",)),
        (api.PinnedWorkerLaunch.descriptor_for, (
            "self", "request_size", "request_sha256", "manifest_size", "manifest_sha256")),
        (api.IsolatedOwner.register_parent_validation, ("self", "request", "prepared", "export_root")),
        (api.IsolatedOwner._assert_parent_read_lease, ("self", "lease", "request", "prepared", "export_root")),
        (api.IsolatedOwner.take_validated_original, ("self", "request", "prepared", "execution", "export_root")),
    ):
        assert tuple(inspect.signature(method).parameters) == parameters
    assert tuple(api.ExportEntry.__dataclass_fields__) == ("key", "kind", "size")
    assert not hasattr(dto, "ExportEntry") and not hasattr(dto, "ParentReadLease")
    for cls in (api.IsolatedPreflight, api.IsolatedOwner, api.PinnedWorkerLaunch,
                api.ParentReadLease, api.RegisteredReader, api._RetainedAppEvidence):
        with pytest.raises((TypeError, PermissionError)):
            cls()


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_authority_noncopy_nonserialize(case, operation):
    flight = preflight(case)
    owner = api.admit_isolated_owner(flight)
    launch = api.pin_worker_launch(owner, owner_spec=case.spec)
    for obj in (flight, owner, launch):
        with pytest.raises(TypeError):
            operation(obj)
    owner.release_joined()


@pytest.mark.parametrize("field,value", [
    ("gpu", "A100:8"), ("cpu", (0.25, 5.0)), ("cpu", (0.25, float("inf"))),
    ("cpu", (1, 4)),
    ("memory", (128, 16385)), ("memory", (True, 16384)),
])
def test_metadata_refusals_resources(case, monkeypatch, field, value):
    config = replace(case.spec.resources, **{field: value})
    spec = replace(case.spec, resources=config)
    monkeypatch.setattr(api, "claim_attempt_reservation", lambda *_: pytest.fail("claim"))
    with pytest.raises(ValueError):
        preflight(case, owner_spec=spec)
    assert not case.auth.bound and common._ACTIVE_HOST is None


@pytest.mark.parametrize("change", ["path", "size", "sha", "root", "key", "missing", "duplicate"])
def test_metadata_refusals_uploads(case, change):
    items = [SimpleNamespace(**vars(i)) for i in case.items]
    if change == "path":
        items[0].path = Path("relative")
    elif change == "size":
        items[0].size = True
    elif change == "sha":
        items[0].sha256 = "z" * 64
    elif change == "root":
        items[0].root = "request"
    elif change == "key":
        items[0].key = "../escape"
    elif change == "missing":
        items.pop()
    else:
        items.append(items[0])
    with pytest.raises(ValueError):
        preflight(case, uploads=items)
    assert not case.auth.bound and common._ACTIVE_HOST is None


@pytest.mark.parametrize("change", ["bound", "request", "setup", "source", "sdk", "sdk_alias", "interpreter", "recipe"])
def test_metadata_refusals_identity(case, change):
    spec = case.spec
    if change == "bound":
        case.auth._bind_once()
    elif change == "request":
        case.request = replace(case.request, image_digest="sha256:" + "1" * 64)
    elif change == "setup":
        case.auth._setup_argv = ()
    elif change == "source":
        spec = replace(spec, source_root=case.tmp / "foreign")
    elif change == "sdk":
        spec = replace(spec, sdk_pins=spec.sdk_pins[:-1])
    elif change == "sdk_alias":
        spec = replace(spec, sdk_pins=tuple(sorted(
            (*spec.sdk_pins, dto.SourcePin("modal_version.py", 0, EMPTY)), key=lambda p: p.key)))
    elif change == "interpreter":
        spec = replace(spec, interpreter=Path("/foreign"))
    else:
        case.auth._image_recipe_sha256 = "0" * 64
    with pytest.raises((ValueError, PermissionError)):
        preflight(case, owner_spec=spec)
    assert common._ACTIVE_HOST is None


def test_metadata_no_content_or_children(case, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("metadata content read")
    monkeypatch.setattr(api.os, "open", forbidden)
    result = preflight(case)
    assert result._request is case.request and not case.auth.bound


def test_metadata_plan_above_twenty_five_refuses_without_effects(case, monkeypatch):
    case.auth._plan = replace(case.auth.plan, planned_ceiling_usd=Decimal("25.01"))
    monkeypatch.setattr(api.os, "open", lambda *a, **k: pytest.fail("content"))
    monkeypatch.setattr(api, "claim_attempt_reservation", lambda *a: pytest.fail("claim"))
    with pytest.raises(ValueError):
        preflight(case)
    assert common._ACTIVE_HOST is None and not case.auth.bound


@pytest.mark.parametrize("field,value", [
    ("_rpc_seconds", 1.1), ("_teardown_seconds", 20.500000001),
    ("_arm_seconds", 5.000000001),
])
def test_metadata_binding_timing_refused_before_claim(case, monkeypatch, field, value):
    setattr(case.spec.stop_binding, field, value)
    monkeypatch.setattr(api, "claim_attempt_reservation", lambda *a: pytest.fail("claim"))
    monkeypatch.setattr(api.os, "open", lambda *a, **k: pytest.fail("content"))
    with pytest.raises(ValueError):
        preflight(case)
    assert not case.auth.bound and common._ACTIVE_HOST is None


def test_original_tuple_authorization_and_frozen_paths(case):
    p = preflight(case)
    assert tuple((i.root, i.key, i.size, i.sha256) for i in p._inventory) == case.auth.uploads
    old = p._inventory[0].path
    case.items[0].path = case.tmp / "substitution"
    assert p._inventory[0].path == old


def test_admission_original_once_and_common_latch(case, monkeypatch):
    events = []
    original_claim = api.claim_attempt_reservation
    original_consume = authority.AttemptReservation.consume
    original_bind = authority.EngineeringAuthorization._bind_once
    def claim(a):
        events.append("claim")
        return original_claim(a)
    def consume(r):
        events.append("consume")
        return original_consume(r)
    def bind(a):
        events.append("bind")
        return original_bind(a)
    monkeypatch.setattr(api, "claim_attempt_reservation", claim)
    monkeypatch.setattr(authority.AttemptReservation, "consume", consume)
    monkeypatch.setattr(authority.EngineeringAuthorization, "_bind_once", bind)
    p = preflight(case)
    o = api.admit_isolated_owner(p)
    assert events == ["claim", "consume", "bind"]
    assert o._reservation.consumed and case.auth.bound
    assert common._ACTIVE_HOST is o
    with pytest.raises((ValueError, PermissionError)):
        api.admit_isolated_owner(p)
    with pytest.raises(RuntimeError):
        common.acquire_common_latch(object())
    o.release_joined()
    assert common._ACTIVE_HOST is None
    assert o._end_ns - o._start_ns == 600 * NS


def test_admission_failed_close_retains_actual_owner(case, monkeypatch):
    original = authority.AttemptReservation.consume
    def fail(r):
        original(r)
        raise ValueError("primary")
    monkeypatch.setattr(authority.AttemptReservation, "consume", fail)
    monkeypatch.setattr(authority.AttemptReservation, "close",
                        lambda *a: (_ for _ in ()).throw(OSError("cleanup")))
    with pytest.raises(api.CustodyError) as caught:
        api.admit_isolated_owner(preflight(case))
    o = caught.value.owner
    assert common._ACTIVE_HOST is o and o._reservation.consumed
    assert isinstance(o._registry.primary, ValueError)
    assert isinstance(o._registry.errors[0], OSError)


def test_admission_opaque_claim_failure_cannot_release_from_absent_return(case, monkeypatch):
    primary = OSError("fixture opaque original claim failure")
    def fail(_):
        raise primary
    monkeypatch.setattr(api, "claim_attempt_reservation", fail)
    with pytest.raises(api.CustodyError) as caught:
        api.admit_isolated_owner(preflight(case))
    retained = caught.value.owner
    assert retained._registry.primary is primary and retained._claim_failed
    assert common._ACTIVE_HOST is retained and not case.auth.bound
    with pytest.raises(api.CustodyError):
        retained.release_joined()


@pytest.mark.parametrize("t,a,minimum", [(NS, NS, 171_500_000_000),
                                        (20_500_000_000, 5 * NS, 195 * NS)])
def test_feasibility_exact_worst_case(t, a, minimum):
    assert minimum_remaining_ns(t, a, ready_pending=True) == minimum
    require_feasible(minimum, t, a, ready_pending=True)
    with pytest.raises(ValueError):
        require_feasible(minimum - 1, t, a, ready_pending=True)
    b = validation_booking(2000 * NS, t)
    assert b.read_ns - b.worker_reap_ns == 30 * NS
    assert (b.close_ns - b.read_ns, b.seal_ns - b.close_ns,
            b.latest_origin_ns - b.seal_ns) == (NS, NS, NS)


def test_registry_generation_acquire_before_postvalidation():
    registry = api._Registry()
    record = registry.reserve("descriptor", None)
    actual = object()
    registry.attach(record, actual)
    primary = ValueError("postvalidation")
    registry.primary = primary
    def fail():
        raise OSError("close")
    with pytest.raises(OSError):
        registry.close(record, fail)
    assert record.handle is actual and record.attempted and not record.closed
    assert registry.primary is primary and len(registry.errors) == 1
    with pytest.raises(api.CustodyError):
        registry.close(record, lambda: pytest.fail("blind retry"))
    next_record = registry.reserve("descriptor", None)
    assert next_record.generation != record.generation


def test_registry_socket_close_clearing_wrapper_retains_original_number():
    a, b = socket.socketpair()
    number = a.fileno()
    class ClearingSocket:
        def fileno(self):
            return self.number
        number = -1
        def close(self):
            self.number = -1
            raise OSError("fixture close cleared wrapper slot")
    standin = ClearingSocket()
    standin.number = number
    registry = api._Registry()
    record = registry.acquire("socket", None, lambda: standin)
    try:
        with pytest.raises(OSError):
            registry.close(record)
        assert record.retained_fd == number and record.handle is standin
        assert record.handle.fileno() == -1 and not record.closed and record.attempted
        with pytest.raises(api.CustodyError):
            registry.close(record)
    finally:
        a.close()  # The stand-in above was known not to close the actual fixture socket.
        b.close()


def test_registry_inherited_socket_registered_before_wrapper_failure(monkeypatch):
    a, b = socket.socketpair()
    number = a.detach()
    registry = api._Registry()
    record = registry.acquire("descriptor", None, lambda: number)
    def fail(family=socket.AF_UNIX, type=socket.SOCK_STREAM, *, fileno):
        assert family == socket.AF_UNIX and type == socket.SOCK_STREAM
        assert fileno == number and record.handle == number and record.retained_fd == number
        raise OSError("fixture wrapper failure")
    monkeypatch.setattr(api.socket, "socket", fail)
    try:
        with pytest.raises(OSError):
            registry.wrap_socket(record)
        assert record.handle == number and record.attempted and not record.closed
        with pytest.raises(api.CustodyError):
            registry.close_all()
    finally:
        _REAL_CLOSE(number)  # Explicit fixture disposal, the substituted wrapper never closed it.
        b.close()


def test_writer_foreign_path_before_open(case, owner, monkeypatch):
    w = owner.preparation_writer()
    i = case.items[0]
    monkeypatch.setattr(api.os, "open", lambda *a, **k: pytest.fail("foreign open"))
    with pytest.raises(ValueError):
        w.snapshot_member(root=i.root, key=i.key, source_path=case.tmp / "foreign",
                          size=i.size, sha256=i.sha256)


def test_writer_zero_byte_wheel_and_exact_supplied_path(case):
    wheel = put(case.tmp / "wheels/empty.whl", b"")
    item = SimpleNamespace(root="wheels", key="empty.whl", size=0, sha256=EMPTY, path=wheel)
    case.items += (item,)
    case.auth._uploads = tuple(sorted(
        (*case.auth.uploads, ("wheels", item.key, 0, EMPTY))))
    o = api.admit_isolated_owner(preflight(case))
    try:
        entry = o.preparation_writer().snapshot_member(
            root=item.root, key=item.key, source_path=wheel, size=0, sha256=EMPTY)
        target = o._writer._snapshot.path / entry.snapshot_key
        assert target.stat().st_size == 0 and stat.S_IMODE(target.stat().st_mode) == 0o600
    finally:
        o.release_joined()


def test_writer_stream_bounds_and_full_hash(case, owner, monkeypatch):
    p = case.items[0].path
    # Do not reuse the admitted owner after changing this owned fixture member.
    owner.release_joined()
    # Exercise real streaming helper on an owned file, not a caller authority.
    p.write_bytes(b"x" * (3 * 65536 + 7))
    registry = api._Registry()
    anchor = api._Anchor.absolute(registry, p.parent, private=False)
    f = anchor.open_file(p.name, os.O_RDONLY, private=False)
    sizes = []
    original = api.os.read
    def read(fd, maximum):
        sizes.append(maximum)
        return original(fd, maximum)
    monkeypatch.setattr(api.os, "read", read)
    assert api._stream_file(f, deadline_ns=time.monotonic_ns() + NS,
                            size=p.stat().st_size)[1] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert max(sizes) <= 65536 and len(sizes) >= 4
    registry.close(f.record)
    registry.close_all()


def test_writer_identity_checked_after_each_chunk_not_only_final_hash(tmp_path, monkeypatch):
    path = put(tmp_path / "member", b"x" * (3 * 65536))
    registry = api._Registry()
    anchor = api._Anchor.absolute(registry, tmp_path, private=True)
    file = anchor.open_file(path.name, os.O_RDONLY, private=False)
    original, reads = os.read, []
    def read(fd, maximum):
        raw = original(fd, maximum)
        reads.append(len(raw))
        if len(reads) == 1:
            path.chmod(0o640)  # Same bytes/hash, changed named/open metadata.
        return raw
    monkeypatch.setattr(api.os, "read", read)
    try:
        with pytest.raises(ValueError, match="identity"):
            api._stream_file(file, deadline_ns=time.monotonic_ns()+NS, size=3*65536)
        assert reads == [65536]
    finally:
        registry.close_all()


def test_writer_one_use_request_and_foreign_seal(case, owner):
    prepared, launch = prepare(case, owner)
    assert owner._writer._prepared is prepared
    assert next(e.key for e in prepared.entries if e.root == "request") == "request.json"
    with pytest.raises(ValueError):
        owner.seal_inputs(replace(prepared), launch)
    with pytest.raises(ValueError):
        owner.preparation_writer()
    with pytest.raises(ValueError):
        owner._writer.write_request(b"again")


def test_launch_descriptor_owner_identity(case, owner):
    prepared, launch = prepare(case, owner)
    assert owner._launch is launch and launch._descriptor.session == owner._session
    assert launch._descriptor.source_root == str(case.root)
    assert case.spec.stop_binding.source_root == case.root / "train"
    with pytest.raises(ValueError):
        launch.descriptor_for(request_size=1, request_sha256=EMPTY,
                              manifest_size=1, manifest_sha256=EMPTY)
    with pytest.raises(ValueError):
        owner.seal_inputs(prepared, copy.copy(launch._descriptor))


def test_launch_source_drift_after_admission(case, owner):
    (case.root / api.WORKER_SOURCE_KEYS[0]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        api.pin_worker_launch(owner, owner_spec=case.spec)
    assert owner._reservation.consumed and case.auth.bound


def test_manifest_max_rows_and_aggregate():
    rows = [dto.ManifestEntry("source", dto.RPC_SOURCE_KEY, 0, EMPTY, "0" * 64)]
    rows.extend(dto.ManifestEntry("wheels", f"w{i}.whl", 0, EMPTY, f"{i+1:064x}")
                for i in range(4095))
    rows.append(dto.ManifestEntry("request", "request.json", 1, EMPTY, "f" * 64))
    rows = tuple(sorted(rows, key=lambda x: (x.root, x.key)))
    assert len(rows) == 4097 and len(dto.encode_manifest(rows)) < 8 * 1024**2
    with pytest.raises(ValueError):
        dto.encode_manifest(tuple(sorted((*rows, dto.ManifestEntry(
            "wheels", "extra", 0, EMPTY, "e" * 64)), key=lambda x: (x.root, x.key))))
    with pytest.raises(ValueError):
        dto.ManifestEntry("wheels", "big", 2 * 1024**3 + 1, EMPTY, EMPTY)


def test_manifest_heaviest_keys_and_exact_eight_gib_metadata_boundary():
    rows = [dto.ManifestEntry("source", dto.RPC_SOURCE_KEY, 1024**2, EMPTY, "0"*64)]
    for i in range(4095):
        key = "/".join(("x"*255, "x"*255, "x"*255, "y"*252, f"{i:03x}"))
        assert len(key) == 1024
        rows.append(dto.ManifestEntry("wheels", key, 2*1024**2, EMPTY, f"{i+1:064x}"))
    rows.append(dto.ManifestEntry("request", "request.json", 1024**2, EMPTY, "f"*64))
    ordered = tuple(sorted(rows, key=lambda e: (e.root, e.key)))
    assert len(ordered) == 4097 and sum(e.size for e in ordered) == 8*1024**3
    assert len(dto.encode_manifest(ordered)) <= 5_026_024 < 8*1024**2
    increased = tuple(replace(e, size=e.size+1) if e.root == "wheels" and e is rows[1]
                      else e for e in ordered)
    with pytest.raises(ValueError):
        dto.encode_manifest(increased)


def test_preparation_actual_c_entry_and_export_basename(case, owner, monkeypatch):
    launch = api.pin_worker_launch(owner, owner_spec=case.spec)
    assets = tuple(native._StagedAsset(i.path, i.root, i.key, i.size, i.sha256)
                   for i in case.items)
    # Only original content serializer is a fixture. C preparation and A
    # writer/seal are their actual implementations and real fixture handles.
    monkeypatch.setattr(adapter, "serialize_original_request",
                        lambda request: adapter.OriginalTransport(b"{}", assets))
    prepared = adapter.prepare_isolated_inputs(
        case.request, owner=owner, uploads=case.items, setup_argv=case.auth.setup_argv,
        export_root=case.export, launch=launch)
    assert launch._descriptor.export_name == case.export.name
    assert owner._writer._export_parent.path == case.export.parent
    owner.seal_inputs(prepared, launch)
    owner.register_parent_validation(
        request=case.request, prepared=prepared, export_root=case.export)


def test_writer_4096_owned_members_bounds_live_descriptors(case):
    remaining = 4096 - len(case.items)
    wheels = []
    for i in range(remaining):
        path = put(case.tmp / "owned-wheels" / str(i) / "empty.whl", b"")
        wheels.append(SimpleNamespace(root="wheels", key=f"{i}.whl",
                                      path=path, size=0, sha256=EMPTY))
    case.items += tuple(wheels)
    case.auth._uploads = tuple(sorted(
        (i.root, i.key, i.size, i.sha256) for i in case.items))
    o = api.admit_isolated_owner(preflight(case))
    try:
        writer = o.preparation_writer()
        for i in case.items:
            writer.snapshot_member(
                root=i.root, key=i.key, source_path=i.path, size=i.size, sha256=i.sha256)
            assert sum(r.handle is not None and not r.closed
                       for r in o._registry.records if r.kind == "descriptor") < 256
        writer.write_request(b"{}")
        assert len(writer._entries) == 4097
    finally:
        o.release_joined()


def test_registration_once_after_identical_seal(case, owner):
    with pytest.raises(ValueError):
        owner.register_parent_validation(request=case.request, prepared=None, export_root=case.export)
    prepared, _ = prepare(case, owner)
    with pytest.raises(ValueError):
        owner.register_parent_validation(request=case.request, prepared=replace(prepared),
                                         export_root=case.export)
    owner.register_parent_validation(request=case.request, prepared=prepared, export_root=case.export)
    with pytest.raises(ValueError):
        owner.register_parent_validation(request=case.request, prepared=prepared, export_root=case.export)


def test_registration_absent_refuses_before_any_child(case, owner, monkeypatch):
    prepare(case, owner)
    monkeypatch.setattr(api, "_spawn_child", lambda **k: pytest.fail("child"))
    with pytest.raises(ValueError):
        asyncio.run(owner.run_once())
    assert owner._children == {}


class FakePopen:
    """Explicitly mocked Popen: poll results are fixture observations only."""
    def __init__(self, pid, code=None):
        self.pid, self.returncode, self.code = pid, None, code
        self.polls = 0
    def poll(self):
        self.polls += 1
        self.returncode = self.code
        return self.code


def install_mocked_lifecycle(c, o, monkeypatch, *, failure=None):
    """Real A dispatch/framing/registry; injected child/channel observations."""
    events, born, channels = [], {}, {}
    c.export.mkdir(mode=0o700)
    staged = put(c.tmp / "staged-stop", b"fixture stop", 0o700)
    def stage(**kwargs):
        events.append(("stage", kwargs["expected_app_id"]))
        return TrustedTeardown(staged, kwargs["environment"], explicitly_trusted=True)
    monkeypatch.setattr(stop.launcher, "stage_trusted_teardown", stage)
    monkeypatch.setattr(stop.OwnedAppStopBinding, "arm",
                        lambda *a, **k: pytest.fail("surrogate arm"))
    def spawn(**kw):
        role = kw["role"]
        events.append(("birth", role))
        if failure == role + "_spawn":
            raise OSError(role)
        p = FakePopen(40000 + len(born), None)
        born[role] = p
        return p
    monkeypatch.setattr(api, "_spawn_child", spawn)
    def waitpid(pid, flags):
        assert flags == os.WNOHANG
        process = next((p for p in born.values() if p.pid == pid), None)
        assert process is not None, "no real child waits in fixture"
        code = process.poll()
        return (0, 0) if code is None else (pid, -code if code < 0 else code << 8)
    monkeypatch.setattr(api.os, "waitpid", waitpid)
    monkeypatch.setattr(api.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(api.os, "getsid", lambda pid: pid)
    def kill(pid, sig):
        events.append(("kill", pid))
        for p in born.values():
            if p.pid == pid:
                p.code = -9
    monkeypatch.setattr(api.os, "killpg", kill)
    original_channel = api._ParentChannel
    class MockedChannel(original_channel):
        def __init__(self, *a, role, **k):
            super().__init__(*a, role=role, **k)
            self.sent = []
            channels[role] = self
        async def send(self, kind, body, *, end_ns):
            dto.encode_message(dict(v=1, session=o._session, seq=len(self.sent)+1,
                                    kind=kind, body=body), session=o._session,
                               seq=len(self.sent)+1, allowed=frozenset({kind}))
            self.sent.append((kind, body))
            events.append(("send", self._role, kind))
            if kind == "FINISH" and self._role == "controller":
                born["controller"].code = born["gate"].code = 0
        async def receive(self, *, allowed, end_ns):
            expected = next(iter(allowed))
            if failure == expected:
                raise api.ControlLost("mocked lost ACK")
            last = self.sent[-1][1] if self.sent else {}
            bodies = {
                "READY": dict(request_sha256=o._inputs.request_sha256,
                              manifest_sha256=o._inputs.manifest_sha256,
                              launch_sha256=o._inputs.launch_sha256),
                "APP_RETAINED": dict(permit=last.get("permit"), app_id=APP),
                "ARMED": dict(permit=last.get("permit")),
                "SANDBOX_RETAINED": dict(permit=last.get("permit"), sandbox_id=SANDBOX),
                "OUTCOME": dict(size=2, sha256=hashlib.sha256(b"{}").hexdigest()),
                "FINISH": {}, "STOP": {},
            }
            if expected == "FINISH":
                born["worker"].code = 0
                events.append(("worker_clean_exit",))
            self._recv_seq += 1
            return dto.validate_message(dict(v=1, session=o._session, seq=self._recv_seq,
                                             kind=expected, body=bodies[expected]),
                                        session=o._session, seq=self._recv_seq, allowed=allowed)
        def try_early_stop(self, origin, cutoff):
            events.append(("early", self._role))
            if "gate" in born and born["gate"].code is None:
                born["gate"].code = 0
            if "controller" in born and born["controller"].code is None:
                born["controller"].code = 0
        def check_live(self):
            assert born[self._role].code is None
        def poll_message(self, *, allowed):
            return None
        def try_stop(self, cutoff):
            events.append(("worker_stop",))
            if "worker" in born:
                born["worker"].code = -9
        def half_close(self):
            events.append(("half_close", self._role))
    monkeypatch.setattr(api, "_ParentChannel", MockedChannel)
    # Fixed C factory still constructs its actual type. Substitute only its
    # data validation body, never A's authority construction/assertions.
    async def validate(validator, lease):
        validator._assert(lease)
        assert born["worker"].polls > 0 and born["worker"].returncode == 0
        assert not o._shutdown.armed
        events.append(("validation",))
        await lease.checkpoint()
        return adapter._ValidatedParentData(
            o, c.request, o._inputs, c.export, lease, lease.worker_execution,
            fixture_original(c))
    monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
    # Worker writes through the real owned outcome descriptor in this fixture.
    original_allocate = o._allocate_worker
    def allocate():
        result = original_allocate()
        os.write(o._outcome.record.handle, b"{}")
        return result
    monkeypatch.setattr(o, "_allocate_worker", allocate)
    return events, born, channels


def fixture_original(c):
    from train.qualification_engineering_run import EngineeringRunOutcome
    return EngineeringRunOutcome(
        "ef" * 32, APP, SANDBOX, (0, 0), 2, hashlib.sha256(b"{}").hexdigest(), (), ())


def test_mocked_three_role_success_worker_reap_before_validation(case, owner, monkeypatch):
    prepared, _ = register(case, owner)
    events, born, channels = install_mocked_lifecycle(case, owner, monkeypatch)
    result = asyncio.run(owner.run_once())
    assert [e[1] for e in events if e[0] == "birth"] == ["worker", "controller", "gate"]
    assert sum(e[0] == "stage" for e in events) == 1
    assert events.index(("worker_clean_exit",)) < events.index(("validation",))
    assert events.index(("validation",)) < events.index(("early", "controller"))
    assert all(p.polls and p.returncode == 0 for p in born.values())
    assert [k for k, _ in channels["worker"].sent] == ["OPEN", "CREATE"]
    original = owner.take_validated_original(
        request=case.request, prepared=prepared, execution=result, export_root=case.export)
    assert original is owner._validated.original
    with pytest.raises(ValueError):
        owner.take_validated_original(
            request=case.request, prepared=prepared, execution=result, export_root=case.export)
    owner.release_joined()
    assert common._ACTIVE_HOST is None and owner._released


@pytest.mark.parametrize("failure", [
    "worker_spawn", "controller_spawn", "gate_spawn",
    "READY", "APP_RETAINED", "ARMED", "SANDBOX_RETAINED", "OUTCOME", "FINISH",
])
def test_mocked_partial_spawn_and_lost_ack_no_resend(case, owner, monkeypatch, failure):
    register(case, owner)
    events, born, channels = install_mocked_lifecycle(case, owner, monkeypatch, failure=failure)
    # Advance only sleeps in the cleanup state machine, not feasibility/dispatch.
    now = [time.monotonic_ns()]
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    async def tick(seconds):
        now[0] += max(1, int(seconds * NS))
    monkeypatch.setattr(api, "_pause", tick)
    with pytest.raises((OSError, api.ControlLost, api.CustodyError)):
        asyncio.run(owner.run_once())
    assert all(p.polls and p.returncode is not None for p in born.values())
    for channel in channels.values():
        kinds = [k for k, _ in channel.sent]
        assert kinds.count("OPEN") <= 1 and kinds.count("CREATE") <= 1 and kinds.count("ARM") <= 1
    assert len(born) <= 3


def test_publication_foreign_data_execution_and_zero_fs(case, owner, monkeypatch):
    prepared, _ = register(case, owner)
    install_mocked_lifecycle(case, owner, monkeypatch)
    result = asyncio.run(owner.run_once())
    with pytest.raises(ValueError):
        owner.take_validated_original(request=case.request, prepared=prepared,
                                      execution=replace(result), export_root=case.export)
    with monkeypatch.context() as m:
        m.setattr(api.os, "open", lambda *a, **k: pytest.fail("final FS"))
        m.setattr(api.hashlib, "sha256", lambda *a: pytest.fail("final hash"))
        final = adapter.validate_joined_outcome(case.request, owner=owner, prepared=prepared,
                                               execution=result, export_root=case.export)
    assert final.local_containment == "JOINED"


def test_publication_and_release_cannot_succeed_after_original_final_cutoff(case, owner, monkeypatch):
    prepared, _ = register(case, owner)
    install_mocked_lifecycle(case, owner, monkeypatch)
    execution = asyncio.run(owner.run_once())
    monkeypatch.setattr(api, "monotonic_ns", lambda: owner._shutdown.cutoffs()[7])
    with pytest.raises(deadline.DeadlineExpired):
        owner.take_validated_original(
            request=case.request, prepared=prepared, execution=execution, export_root=case.export)
    with pytest.raises(api.CustodyError):
        owner.release_joined()
    assert common._ACTIVE_HOST is owner and not owner._released


def test_release_unknown_close_retains_latch_and_actual_fd(case, owner, monkeypatch):
    owner.preparation_writer()
    record = owner._writer._snapshot._root
    original = api.os.close
    calls = []
    def close(fd):
        if fd == record.handle:
            calls.append(fd)
            raise OSError("unknown close")
        original(fd)
    monkeypatch.setattr(api.os, "close", close)
    with pytest.raises(api.CustodyError):
        owner.release_joined()
    assert common._ACTIVE_HOST is owner and not owner._released
    assert record.handle >= 0 and record.attempted and not record.closed
    with pytest.raises(api.CustodyError):
        owner.release_joined()
    assert len(calls) == 1
    # Autouse fixture alone later closes this still-open, newly owned fake
    # failure handle. Production performs no retry.


def test_shutdown_fixed_eight_cutoffs_and_alarm():
    timing = dto.StopTimingFacts(NS, 20_500_000_000, 5 * NS)
    latch = deadline.ShutdownLatch(end_ns=2000 * NS, timing=timing)
    assert latch.request_stop(100 * NS)
    cutoffs = latch.cutoffs()
    assert cutoffs == (101*NS, 103*NS, 104*NS, 124_500_000_000,
                       125*NS, 127*NS, 129*NS, 130*NS)
    for _ in range(3):
        assert not latch.request_stop(200 * NS) and latch.cutoffs() == cutoffs
    latest = 1970 * NS
    assert deadline.initial_gate_alarm_ns(latest, timing.teardown_ns) == 1995 * NS
    assert deadline.early_gate_alarm_ns(1995 * NS, 100 * NS, timing.teardown_ns) == 125 * NS
    assert deadline.alarm_seconds(1, now_ns=2) == 0


@pytest.mark.parametrize("key", ["", "/absolute", ".", "..", "../leaf", "a//b", "a/./b", "a\\b"])
def test_anchor_rejects_unsafe_key_before_open(tmp_path, key):
    registry = api._Registry()
    anchor = api._Anchor.absolute(registry, tmp_path, private=False)
    try:
        with pytest.raises(ValueError):
            anchor.open_file(key, os.O_RDONLY, private=False)
    finally:
        registry.close_all()


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "hash", "size", "deadline"])
def test_anchored_pin_refusal(tmp_path, mutation):
    p = put(tmp_path / "file", b"bytes")
    if mutation == "symlink":
        p.unlink()
        p.symlink_to(put(tmp_path / "target", b"bytes"))
    if mutation == "hardlink":
        os.link(p, tmp_path / "alias")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises((ValueError, OSError)):
            deadline.verify_anchored_file(
                fd, "file", size=6 if mutation == "size" else 5,
                sha256=EMPTY if mutation == "hash" else hashlib.sha256(b"bytes").hexdigest(),
                deadline_ns=1 if mutation == "deadline" else time.monotonic_ns() + NS)
    finally:
        os.close(fd)


def test_channel_canonical_framing_and_coalescing():
    a, b = socket.socketpair()
    channel = api._ParentChannel(a, session=SESSION, end_ns=time.monotonic_ns()+NS,
                                 role="worker")
    frames = [dto.encode_message(dict(v=1, session=SESSION, seq=i, kind="FINISH", body={}),
                                 session=SESSION, seq=i, allowed=frozenset({"FINISH"}))
              for i in (1, 2)]
    b.sendall(b"".join(frames))
    async def read():
        for _ in range(2):
            assert (await channel.receive(allowed=frozenset({"FINISH"}),
                                           end_ns=time.monotonic_ns()+NS))["kind"] == "FINISH"
    try:
        asyncio.run(read())
    finally:
        channel.close()
        b.close()


@pytest.mark.parametrize("fault", ["foreign", "oversize", "unexpected", "eof", "partial"])
def test_channel_refuses_invalid_or_eof(fault):
    a, b = socket.socketpair()
    c = api._ParentChannel(a, session=SESSION, end_ns=time.monotonic_ns()+NS, role="worker")
    if fault in {"foreign", "unexpected"}:
        session = "cd"*32 if fault == "foreign" else SESSION
        b.sendall(dto.encode_message(dict(v=1, session=session, seq=1, kind="STOP", body={}),
                                     session=session, seq=1, allowed=frozenset({"STOP"})))
    elif fault == "oversize":
        b.sendall((8193).to_bytes(4, "big"))
    elif fault == "partial":
        b.sendall(b"\0\0")
    b.close()
    try:
        with pytest.raises((ValueError, api.ControlLost)):
            asyncio.run(c.receive(allowed=frozenset({"FINISH"}), end_ns=time.monotonic_ns()+NS))
    finally:
        c.close()
        c.close()


def test_worker_fixed_program_and_payload(tmp_path):
    assert (worker.PROGRAM_MODULE, worker.PROGRAM_FUNCTION, worker.SDK_VERSION) == (
        "train.qualification_isolated_program", "run_prepared_worker", "1.6.3")
    p = put(tmp_path / "payload", b"abcdef")
    fd = os.open(p, os.O_RDONLY)
    try:
        assert worker.read_payload(fd, 6, deadline_ns=time.monotonic_ns()+NS) == b"abcdef"
        os.lseek(fd, 0, os.SEEK_SET)
        with pytest.raises(ValueError):
            worker.read_payload(fd, 5, deadline_ns=time.monotonic_ns()+NS)
    finally:
        os.close(fd)
    assert worker.digest_app_id(APP) == APP
    with pytest.raises(ValueError):
        worker.digest_app_id("ap-short")
    with pytest.raises(ValueError):
        worker.require_sandbox_id("local")


def test_sdk_module_key_binding_and_fixed_closure():
    assert api._module_name("modal/sandbox/__init__.py") == "modal.sandbox"
    assert api._module_name("modal/sandbox/_sandbox.py") == "modal.sandbox._sandbox"
    assert api.WORKER_SOURCE_KEYS == tuple(sorted(set(api.WORKER_SOURCE_KEYS)))
    for key in ("train/dead_group_probe.py", "train/verdict.py",
                "train/qualification_remote_verification.py",
                "train/qualification_isolated_program.py",
                "train/qualification_isolated_validation.py"):
        assert key in api.WORKER_SOURCE_KEYS
    assert "setitimer" in deadline.BOOTSTRAP
    assert "meta_path" in deadline.BOOTSTRAP and "compile" in deadline.BOOTSTRAP


def install_lease_body(c, o, monkeypatch, body):
    events, born, channels = install_mocked_lifecycle(c, o, monkeypatch)
    async def validate(validator, lease):
        validator._assert(lease)
        await body(lease)
        validator._assert(lease)
        return adapter._ValidatedParentData(
            o, c.request, o._inputs, c.export, lease, lease.worker_execution, fixture_original(c))
    monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
    return events, born, channels


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_lease_private_copy_foreign_and_post_shutdown_replay(case, owner, monkeypatch, operation):
    prepared, _ = register(case, owner)
    retained = []
    async def body(lease):
        retained.append(lease)
        with pytest.raises(TypeError):
            operation(lease)
        foreign = object.__new__(api.ParentReadLease)
        foreign.__dict__.update(lease.__dict__)
        with pytest.raises(ValueError):
            owner._assert_parent_read_lease(
                foreign, request=case.request, prepared=prepared, export_root=case.export)
        for changed in (
            dict(request=replace(case.request), prepared=prepared, export_root=case.export),
            dict(request=case.request, prepared=replace(prepared), export_root=case.export),
            dict(request=case.request, prepared=prepared, export_root=Path(str(case.export))),
        ):
            with pytest.raises(ValueError):
                owner._assert_parent_read_lease(lease, **changed)
        generation = owner._lease_generation
        owner._lease_generation += 1
        with pytest.raises(ValueError):
            await lease.checkpoint()
        owner._lease_generation = generation
        await lease.checkpoint()
    install_lease_body(case, owner, monkeypatch, body)
    execution = asyncio.run(owner.run_once())
    with pytest.raises(ValueError):
        asyncio.run(retained[0].checkpoint())
    owner.take_validated_original(
        request=case.request, prepared=prepared, execution=execution, export_root=case.export)


def test_reader_real_c_hash_inventory_yields_and_closed_fd_reuse(case, owner, monkeypatch):
    prepared, _ = register(case, owner)
    raw = b"a" * (65536 + 23)
    yields, maximums = [], []
    original_pause, original_read, original_fstat = api._pause, os.read, os.fstat
    async def pause(seconds):
        yields.append(seconds)
        await original_pause(seconds)
    def read(fd, maximum):
        maximums.append(maximum)
        return original_read(fd, maximum)
    monkeypatch.setattr(api, "_pause", pause)
    monkeypatch.setattr(api.os, "read", read)
    async def body(lease):
        reads = program._LeaseReads(
            lease, lease.worker_execution, lease.end_ns, lease.read_deadline_ns)
        expected = {"nested/a.bin": dict(size=len(raw)), "empty": dict(size=0)}
        await reads.inventory(expected)
        await reads.read("nested/a.bin", size=len(raw),
                         sha256=hashlib.sha256(raw).hexdigest(), retain=False)
        await reads.read("empty", size=0, sha256=EMPTY, retain=False)
        first = reads.verified[0]
        with pytest.raises(TypeError):
            copy.copy(first)
        assert first._file.record.closed
        with pytest.raises(ValueError):
            await first.read(65537)
        number = first._file.record.handle
        replacement = os.open(case.tmp / "replacement", os.O_RDONLY)
        if replacement != number:
            os.dup2(replacement, number)
            os.close(replacement)
        try:
            with monkeypatch.context() as m:
                def fstat(fd):
                    assert fd != number, "closed/recycled number was inspected"
                    return original_fstat(fd)
                m.setattr(api.os, "fstat", fstat)
                for reader in reads.verified:
                    await reads.identity(reader)
                first.close()  # Idempotence cannot close the recycled generation.
            assert stat.S_ISREG(original_fstat(number).st_mode)
        finally:
            os.close(number)
    install_lease_body(case, owner, monkeypatch, body)
    put(case.export / "nested/a.bin", raw)
    (case.export / "nested").chmod(0o700)
    put(case.export / "empty", b"")
    put(case.tmp / "replacement", b"owned replacement")
    execution = asyncio.run(owner.run_once())
    assert maximums and max(maximums) <= 65536 and len(yields) >= 20
    lease_records = [r for r in owner._registry.records if r.anchor is owner._lease]
    assert lease_records and all(r.closed for r in lease_records)
    assert all(r.closed_ns < owner._booking.close_ns for r in lease_records)
    assert not owner._export_anchor._root.closed
    owner.take_validated_original(
        request=case.request, prepared=prepared, execution=execution, export_root=case.export)


def test_reader_final_sweep_detects_earlier_closed_file_change(case, owner, monkeypatch):
    register(case, owner)
    async def body(lease):
        reads = program._LeaseReads(
            lease, lease.worker_execution, lease.end_ns, lease.read_deadline_ns)
        for key in ("a", "b"):
            await reads.read(key, size=1, sha256=hashlib.sha256(key.encode()).hexdigest(),
                             retain=False)
        assert all(r._file.record.closed for r in reads.verified)
        (case.export / "a").write_bytes(b"changed after its data reader closed")
        for reader in reads.verified:
            await reads.identity(reader)  # Same final sweep used by fixed C.
    install_lease_body(case, owner, monkeypatch, body)
    put(case.export / "a", b"a")
    put(case.export / "b", b"b")
    with pytest.raises(ValueError, match="identity"):
        asyncio.run(owner.run_once())
    assert owner._validated is None and owner._execution is None


def test_fixed_c_validator_rejects_bad_actual_outcome_once(case, owner, monkeypatch):
    register(case, owner)
    real_validate = adapter._ParentValidator.validate
    install_mocked_lifecycle(case, owner, monkeypatch)
    monkeypatch.setattr(adapter._ParentValidator, "validate", real_validate)
    real_body, calls = program._validate_outcome_lease, []
    async def body(*args, **kwargs):
        calls.append(1)
        return await real_body(*args, **kwargs)
    monkeypatch.setattr(program, "_validate_outcome_lease", body)
    with pytest.raises(ValueError):
        asyncio.run(owner.run_once())
    assert calls == [1] and owner._lease._readers[0]._file.record.closed
    assert owner._validated is None


def test_reader_unknown_close_retains_actual_parent_anchors_and_both_errors(case, owner, monkeypatch):
    register(case, owner)
    retained, closes = [], []
    real_close = os.close
    primary = ValueError("fixture validation primary")
    async def body(lease):
        reader = lease.open_export("nested/a")
        retained.append(reader)
        record = reader._file.record
        def close(fd):
            if fd == record.handle:
                closes.append(fd)
                raise OSError("fixture unknown reader close")
            real_close(fd)
        monkeypatch.setattr(api.os, "close", close)
        raise primary
    install_lease_body(case, owner, monkeypatch, body)
    put(case.export / "nested/a", b"a")
    (case.export / "nested").chmod(0o700)
    with pytest.raises(api.CustodyError) as caught:
        asyncio.run(owner.run_once())
    record = retained[0]._file.record
    assert caught.value.primary is primary and len(closes) == 1
    assert record.attempted and not record.closed and common._ACTIVE_HOST is owner
    assert not retained[0]._file.parent._root.closed
    with pytest.raises(api.CustodyError):
        owner.release_joined()
    assert len(closes) == 1 and not owner._export_anchor._root.closed


@pytest.mark.parametrize("target", ["APP_RETAINED", "ARMED", "OUTCOME", "VALIDATION"])
def test_shutdown_three_repeated_cancellations_cannot_escape_joins(case, owner, monkeypatch, target):
    register(case, owner)
    events, born, channels = install_mocked_lifecycle(case, owner, monkeypatch)
    base = api._ParentChannel
    entered = asyncio.Event()
    now = [time.monotonic_ns()]
    kills = []
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    real_kill = api.os.killpg
    def kill(pid, sig):
        kills.append((pid, now[0]))
        real_kill(pid, sig)  # The explicitly mocked fixture signal, never OS.
    monkeypatch.setattr(api.os, "killpg", kill)
    class BlockingChannel(base):
        async def receive(self, *, allowed, end_ns):
            if target in allowed:
                entered.set()
                await asyncio.Event().wait()
            return await super().receive(allowed=allowed, end_ns=end_ns)
        def try_early_stop(self, origin, cutoff):
            events.append(("early", self._role))
        def try_stop(self, cutoff):
            events.append(("worker_stop",))
    monkeypatch.setattr(api, "_ParentChannel", BlockingChannel)
    if target == "VALIDATION":
        async def validate(validator, lease):
            validator._assert(lease)
            lease.open_outcome()
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
    async def tick(seconds):
        await asyncio.sleep(0)
        now[0] += max(NS // 2, int(seconds * NS))
    monkeypatch.setattr(api, "_pause", tick)
    async def scenario():
        task = asyncio.create_task(owner.run_once())
        await entered.wait()
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "cancellation escaped directly awaited cleanup"
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert all(p.polls and p.returncode is not None for p in born.values())
    assert all(r.closed for r in owner._runtime_records)
    if "gate" in born:
        gate_kills = [when for pid, when in kills if pid == born["gate"].pid]
        assert gate_kills and min(gate_kills) >= owner._shutdown.cutoffs()[4]
    assert owner._execution is None
    if owner._lease is not None:
        assert all(reader._file.record.closed for reader in owner._lease._readers)


def test_shutdown_unknown_reap_retains_all_actual_resources_latch(case, owner, monkeypatch):
    register(case, owner)
    _, born, _ = install_mocked_lifecycle(
        case, owner, monkeypatch, failure="APP_RETAINED")
    monkeypatch.setattr(FakePopen, "poll", lambda p: None)
    now = [time.monotonic_ns()]
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    async def tick(seconds):
        now[0] += max(NS // 2, int(seconds * NS))
    monkeypatch.setattr(api, "_pause", tick)
    with pytest.raises(api.CustodyError):
        asyncio.run(owner.run_once())
    assert owner._children["worker"].process is born["worker"]
    assert owner._children["worker"].code is None and common._ACTIVE_HOST is owner
    assert all(not r.attempted for r in owner._runtime_records if not r.closed)
    assert not owner._writer._snapshot._root.closed
    with pytest.raises(api.CustodyError):
        owner.release_joined()


def test_shutdown_external_reap_never_synthesizes_clean_zero(case, owner, monkeypatch):
    register(case, owner)
    events, born, _ = install_mocked_lifecycle(case, owner, monkeypatch)
    waitpid, lost = api.os.waitpid, []
    def external_wait(pid, flags):
        if pid == born["worker"].pid and born["worker"].code == 0:
            lost.append(pid)
            raise ChildProcessError("fixture externally reaped")
        return waitpid(pid, flags)
    monkeypatch.setattr(api.os, "waitpid", external_wait)
    now = [time.monotonic_ns()]
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    async def tick(seconds):
        now[0] += max(NS // 2, int(seconds * NS))
    monkeypatch.setattr(api, "_pause", tick)
    with pytest.raises(api.CustodyError):
        asyncio.run(owner.run_once())
    child = owner._children["worker"]
    assert len(lost) == 1 and child.code is None
    assert child.process is born["worker"] and isinstance(child.wait_error, ChildProcessError)
    assert ("kill", child.pid) not in events  # A reused PID is not signal authority.
    assert owner._lease is None and common._ACTIVE_HOST is owner


@pytest.mark.parametrize("fault", ["exit", "eof"])
def test_independent_loss_interrupts_blocked_worker_receive(case, owner, monkeypatch, fault):
    register(case, owner)
    real_channel = api._ParentChannel
    _, born, channels = install_mocked_lifecycle(case, owner, monkeypatch)
    mocked = api._ParentChannel
    elapsed = []
    class Blocked(mocked):
        async def receive(self, *, allowed, end_ns):
            if "OUTCOME" not in allowed:
                return await super().receive(allowed=allowed, end_ns=end_ns)
            a, b = socket.socketpair()
            c, d = socket.socketpair()
            original_socket = self._socket
            controller = channels["controller"]
            old_controller_socket, old_check = controller._socket, controller.check_live
            self._socket, controller._socket = a, c
            a.setblocking(False)
            c.setblocking(False)
            controller.check_live = lambda: real_channel.check_live(controller)
            def fail():
                if fault == "exit":
                    born["controller"].code = 0
                else:
                    d.shutdown(socket.SHUT_WR)
            asyncio.get_running_loop().call_soon(fail)
            started = time.monotonic()
            try:
                return await real_channel.receive(self, allowed=allowed, end_ns=end_ns)
            finally:
                elapsed.append(time.monotonic() - started)
                self._socket = original_socket
                controller._socket, controller.check_live = old_controller_socket, old_check
                for sock in (a, b, c, d):
                    sock.close()
    monkeypatch.setattr(api, "_ParentChannel", Blocked)
    with pytest.raises((ValueError, api.ControlLost)):
        asyncio.run(owner.run_once())
    assert len(elapsed) == 1 and elapsed[0] < .5
    assert owner._shutdown.armed and owner._validated is None


@pytest.mark.parametrize("wire", [b"\0", b"\0\0\0", b"\0\0\0\x40{"])
def test_gate_trigger_priority_over_partial_control_and_eof(monkeypatch, wire):
    control, parent = socket.socketpair()
    trigger, writer = socket.socketpair()
    control.setblocking(False)
    trigger.setblocking(False)
    parent.sendall(wire)
    writer.close()
    facts = {"arm-end": time.monotonic_ns() + NS}
    try:
        assert deadline._receive_arm(
            control, trigger, deadline._Frames(SESSION), facts, gate=True) is False
    finally:
        control.close()
        parent.close()
        trigger.close()


def test_shutdown_early_stop_partial_send_always_half_closes():
    class PartialSocket:
        def __init__(self):
            self.shutdowns, self.sends = [], 0
        def setblocking(self, value):
            pass
        def send(self, raw):
            self.sends += 1
            return 1
        def shutdown(self, how):
            self.shutdowns.append(how)
    sock = PartialSocket()
    channel = api._ParentChannel(sock, session=SESSION, end_ns=time.monotonic_ns()+NS,
                                 role="controller")
    now = time.monotonic_ns()
    with pytest.raises(api.ControlLost):
        channel.try_early_stop(now, now + NS)
    channel.try_early_stop(now, now + NS)
    assert sock.sends == 1 and sock.shutdowns == [socket.SHUT_WR]


def test_controller_partial_eof_triggers_without_waiting_for_latest(tmp_path):
    parent, control = socket.socketpair()
    trigger, gate = socket.socketpair()
    journal = put(tmp_path / "journal", b"")
    journal_fd = os.open(journal, os.O_WRONLY | os.O_APPEND)
    control_fd, trigger_fd = control.detach(), trigger.detach()
    end = time.monotonic_ns() + 1000 * NS
    facts = dict(control=control_fd, trigger=trigger_fd, journal=journal_fd,
                 session=SESSION, end=end, teardown=NS,
                 **{"arm-end": time.monotonic_ns() + NS, "app": APP})
    argv = ["fixture-controller", "--controller",
            *(s for k, v in facts.items() for s in ("--" + k, str(v)))]
    parent.sendall(b"\0\0")  # Partial ARM, then unconditional parent write EOF.
    parent.shutdown(socket.SHUT_WR)
    try:
        started = time.monotonic()
        assert deadline.controller_main(argv) == 0
        assert time.monotonic() - started < 1
        assert gate.recv(1) in (deadline.TRIGGER_BYTE, b"")
        assert gate.recv(1) == b""
    finally:
        parent.close()
        gate.close()


def test_registry_post_open_mode_failure_keeps_actual_fd_until_close(tmp_path):
    registry = api._Registry()
    anchor = api._Anchor.absolute(registry, tmp_path, private=True)
    put(tmp_path / "bad", b"owned", 0o644)
    with pytest.raises(ValueError):
        anchor.open_file("bad", os.O_RDONLY, private=True)
    record = registry.records[-1]
    assert record.kind == "descriptor" and record.handle >= 3 and not record.attempted
    assert stat.S_ISREG(os.fstat(record.handle).st_mode)
    registry.close_all()
    with pytest.raises(OSError):
        os.fstat(record.handle)


def test_registry_renumber_close_failure_retains_actual_duplicate_and_ancestors(tmp_path, monkeypatch):
    registry = api._Registry()
    anchor = api._Anchor.absolute(registry, tmp_path, private=True)
    path = put(tmp_path / "owned", b"fixture")
    actual = os.open(path, os.O_RDONLY)
    class SimulatedLowFD(int):
        def __lt__(self, other):
            return other == 3  # Exercise relocation WITHOUT touching fd 0/1/2.
    real_close = os.close
    calls = []
    def close(fd):
        if fd == actual:
            calls.append(fd)
            raise OSError("fixture old-generation close unknown")
        real_close(fd)
    monkeypatch.setattr(api.os, "close", close)
    start = len(registry.records)
    with pytest.raises(OSError):
        registry.fd(None, lambda: SimulatedLowFD(actual), parent=anchor._root)
    original, duplicate = registry.records[start:]
    assert original.handle == actual and duplicate.handle != actual
    assert not duplicate.closed and anchor._root.live_dependents == 2
    with pytest.raises(api.CustodyError):
        registry.close_all()
    assert duplicate.closed and not anchor._root.attempted and len(calls) == 1
    # Explicit fixture disposal after the custody assertion, not a production
    # resolution/retry: mocked close above is known never to have closed it.
    real_close(actual)
    original.closed = True
    anchor._root.live_dependents -= 1
    registry.close_all()


@pytest.mark.parametrize("abort", [None, "STOP", "EOF"])
def test_worker_one_c_call_retained_objects_and_no_post_outcome_stop_wait(case, owner, monkeypatch, abort):
    prepared, launch = prepare(case, owner)
    events, calls = [], []
    class Image:
        @staticmethod
        def from_registry(*args, **kwargs):
            return Image()
    class App:
        def __init__(self, *args, **kwargs):
            self.app_id = APP
        def run(self, **kwargs):
            app = self
            class Context:
                async def __aenter__(self):
                    assert worker._RETAINED_HOSTS[-1]._app is app
                    events.append("app_retained_before_entry")
                    return app
            return Context()
    class Sandbox:
        object_id = SANDBOX
        @staticmethod
        async def create(**kwargs):
            events.append("create")
            return Sandbox()
    class Synchronizer:
        def _get_loop(self, *, start):
            return asyncio.get_running_loop()
    monkeypatch.setattr(worker, "_SDK", SimpleNamespace(
        App=App, Sandbox=Sandbox, Image=Image, synchronizer=Synchronizer()))
    started = asyncio.Event()
    async def body(**kwargs):
        calls.append(1)
        started.set()
        if abort:
            await asyncio.Event().wait()
        return dto.WorkerProgramResult(2, hashlib.sha256(b"{}").hexdigest())
    monkeypatch.setattr(program, "run_prepared_worker", body)
    class Control:
        end_ns = owner._end_ns
        async def send(self, kind, body, *, end_ns):
            if kind == "SANDBOX_RETAINED":
                assert type(worker._RETAINED_HOSTS[-1].resource) is Sandbox
            events.append(kind)
        async def receive(self, *, allowed, end_ns):
            kind = next(iter(allowed))
            events.append("receive_" + kind)
            if kind == "STOP":
                await started.wait()
                if abort == "EOF":
                    raise api.ControlLost("fixture EOF")
                if abort == "STOP":
                    return dict(body={})
                await asyncio.Event().wait()
            return dict(body=dict(permit="ab"*32, end_ns=self.end_ns))
        def shutdown_write(self):
            events.append("half_close")
    inputs = dto.WorkerInputs(dto.WorkerFDNumbers(*range(3, 10)), b"{}", prepared.entries)
    invocation = worker.worker_loop(inputs=inputs, launch=launch._descriptor, control=Control())
    if abort:
        with pytest.raises((worker.ControlEOF, api.ControlLost)):
            asyncio.run(invocation)
        assert "OUTCOME" not in events and "FINISH" not in events
    else:
        result = asyncio.run(invocation)
        assert result.outcome_size == 2
        assert events[-3:] == ["OUTCOME", "FINISH", "half_close"]
        assert events.count("receive_STOP") == 1  # Concurrent body watcher ONLY.
    assert calls == [1] and events.count("create") == 1


@pytest.mark.parametrize("version_key", ["modal_version/__init__.py", "modal_version.py"])
def test_sdk_owned_buffers_precede_import_and_execute_pinned_raw_exports(case, monkeypatch, version_key):
    bodies = {
        "modal/app.py": "class _App:\n    async def stop(self): pass\n",
        "modal/sandbox/_sandbox.py":
            "class _Sandbox:\n    @staticmethod\n    async def create(): pass\n",
        "modal/_image.py":
            "class _Image:\n    @staticmethod\n    def from_registry(): return _Image()\n",
        version_key: "__version__ = '1.6.3'\n",
        "modal/_utils/async_utils.py":
            "class Sync:\n    def no_io_translation(self, entry): return entry\n"
            "synchronizer = Sync()\ndef synchronize_api(entry): return entry\n",
    }
    keys = tuple(sorted(version_key if k == "modal_version/__init__.py" else k
                        for k in api.SDK_REQUIRED_KEYS))
    for key in keys:
        put(case.sdk / key, bodies.get(key, "# owned SDK stand-in\n").encode())
    sdk_pins = tuple(pin(case.sdk / key, key) for key in keys)
    case.spec.stop_binding._sdk_pins = {api._module_name(p.key): p.sha256 for p in sdk_pins}
    case.spec = replace(case.spec, sdk_pins=sdk_pins)
    o = api.admit_isolated_owner(preflight(case))
    prepare(case, o)
    original_import = worker.importlib.import_module
    loaded = []
    def imported(name):
        if not loaded:
            loader = sys.meta_path[0]
            assert isinstance(loader, worker._SDKBuffers)
            assert len(loader.sources) == len(sdk_pins)
            # Must NEVER execute this later on-disk replacement.
            put(case.sdk / "modal/app.py", b"raise AssertionError('late source import')\n")
        loaded.append(name)
        return original_import(name)
    existing = set(sys.modules)
    with monkeypatch.context() as m:
        m.setattr(worker.sys, "meta_path", list(sys.meta_path))
        m.setattr(worker.sys, "path", list(sys.path))
        m.setattr(worker.importlib, "import_module", imported)
        try:
            sdk = worker.import_sdk(o._launch._descriptor, deadline_ns=time.monotonic_ns()+NS)
            assert sdk.App.__module__ == "modal.app" and sdk.App.__name__ == "_App"
            assert sdk.Sandbox.create.__code__.co_filename == str(
                case.sdk / "modal/sandbox/_sandbox.py")
            assert loaded[0] == "modal_version"
        finally:
            for name in tuple(sys.modules):
                if name not in existing and name.split(".")[0] in {"modal", "modal_proto", "modal_version"}:
                    del sys.modules[name]  # Only new fixture modules, fresh check is in import_sdk.
    o.release_joined()


def test_gate_exec_prepared_before_arm_and_kernel_closes_control_on_exec(case, monkeypatch):
    parent, control = socket.socketpair()
    writer, trigger = socket.socketpair()
    journal_fd = os.open(put(case.tmp / "gate-journal", b""), os.O_WRONLY | os.O_APPEND)
    control_fd, trigger_fd = control.detach(), trigger.detach()
    inherited = (control_fd, trigger_fd, journal_fd)
    executable = put(case.tmp / "gate-stop", b"owned stop executable", 0o700)
    environment = dict(case.spec.stop_binding.environment)
    end = time.monotonic_ns() + 1000 * NS
    facts = dict(control=control_fd, trigger=trigger_fd, journal=journal_fd,
                 session=SESSION, end=end, teardown=NS,
                 **{"arm-end": time.monotonic_ns() + NS, "app": APP,
                    "executable": str(executable), "command-size": executable.stat().st_size,
                    "command-sha256": pin(executable, "stop").sha256,
                    "cwd": str(case.tmp), "environment": dto.canonical(environment).decode()})
    argv = ["fixture-gate", "--gate",
            *(s for k, v in facts.items() for s in ("--" + k, str(v)))]
    parent.sendall(dto.encode_message(
        dict(v=1, session=SESSION, seq=1, kind="ARM", body=dict(
            permit=SESSION, end_ns=end, origin_ns=deadline.latest_origin_ns(end, NS),
            teardown_ns=NS, app_id=APP)),
        session=SESSION, seq=1, allowed=frozenset({"ARM"})))
    events, armed = [], [False]
    real_send, real_close = deadline._send, api._Registry.close
    class ExpectedExec(Exception):
        pass
    def close(registry, record, operation=None):
        events.append(("close", armed[0]))
        return real_close(registry, record, operation)
    def send(*args):
        assert not armed[0] and ("stdin",) in events and ("cwd", str(case.tmp)) in events
        assert all(not os.get_inheritable(fd) for fd in inherited)
        real_send(*args)
        armed[0] = True
        writer.shutdown(socket.SHUT_WR)
    def dup2(fd, target, *, inheritable):
        assert target == 0 and inheritable is True
        events.append(("stdin",))
        return 0  # Fixture metadata only, never replace pytest's real fd 0.
    def execve(path, args, env):
        assert path == str(executable) and args == [str(executable)] and env == environment
        assert armed[0] and not any(e == ("close", True) for e in events)
        assert all(not os.get_inheritable(fd) for fd in inherited)
        events.append(("exec",))
        raise ExpectedExec("fixture only, no actual exec")
    try:
        with monkeypatch.context() as m:
            m.setattr(deadline, "install_alarm", lambda end: None)
            m.setattr(deadline.os, "environ", environment)
            m.setattr(deadline.os, "chdir", lambda path: events.append(("cwd", path)))
            m.setattr(deadline.os, "dup2", dup2)
            m.setattr(deadline.os, "execve", execve)
            m.setattr(api._Registry, "close", close)
            m.setattr(deadline, "_send", send)
            for fd in inherited:
                os.set_inheritable(fd, True)
            with pytest.raises(ExpectedExec):
                deadline.gate_main(argv)
        assert events.count(("exec",)) == 1
    finally:
        # Explicit disposal after a substituted exec. Production transfers
        # these three copies to the kernel's CLOEXEC handling.
        for retained in deadline._RETAINED_CHILD_FAILURES:
            if len(retained) == 3:
                retained[0].close_all()
                retained[1].close_all([r for r in retained[1].records if r.kind != "exec-stdin"])
        parent.close()
        writer.close()


@pytest.mark.parametrize("role", ["worker", "controller", "gate"])
@pytest.mark.parametrize("offset", [0, 1])
def test_positive_reap_observation_respects_original_join_cutoff(owner, monkeypatch, role, offset):
    now = [time.monotonic_ns()]
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    owner._invalidate_lease()
    cutoffs = owner._shutdown.cutoffs()
    limit = cutoffs[5] if role == "gate" else cutoffs[1]
    process = FakePopen(41000, 0)
    record = owner._registry.acquire("child", owner, lambda: process)
    child = api._Child(owner, role, record)
    child.pid = child.pgid = child.sid = process.pid
    owner._children[role] = child
    owner._channels[role] = SimpleNamespace(
        try_early_stop=lambda *args: None, half_close=lambda: None,
        try_stop=lambda *args: None, poll_message=lambda **kwargs: None)
    monkeypatch.setattr(api.os, "waitpid", lambda pid, flags: (pid, 0))
    now[0] = limit + offset
    asyncio.run(owner._shutdown_join())
    assert child.code == 0 and child.reaped_ns == limit + offset and record.closed
    assert owner._missed_cutoffs == ({role} if offset else set())
    assert sum(isinstance(e, deadline.DeadlineExpired)
               for e in owner._lifecycle_errors) == offset
    assert len(owner._lifecycle_errors) == offset


def test_full_lifecycle_late_gate_reap_prevents_publication(case, monkeypatch):
    owner = api.admit_isolated_owner(preflight(case))
    prepared, _ = register(case, owner)
    _, born, _ = install_mocked_lifecycle(case, owner, monkeypatch)
    now = [time.monotonic_ns()]
    monkeypatch.setattr(api, "monotonic_ns", lambda: now[0])
    original_step = owner._shutdown_step
    def late_gate(cutoffs):
        born["controller"].code = 0
        owner._children["controller"].observe()
        now[0] = cutoffs[5] + 1
        original_step(cutoffs)
    monkeypatch.setattr(owner, "_shutdown_step", late_gate)
    with pytest.raises(api.CustodyError):
        asyncio.run(owner.run_once())
    assert owner._missed_cutoffs == {"gate"}
    assert all(c.code == 0 for c in owner._children.values())
    assert owner._execution is None and not owner._published
    with pytest.raises(ValueError):
        owner.take_validated_original(
            request=case.request, prepared=prepared, execution=None, export_root=case.export)


@pytest.mark.parametrize("kind", ["app", "sandbox"])
def test_opaque_identity_append_failure_retains_unknown_temp_fd_and_latch(
        case, owner, monkeypatch, kind):
    register(case, owner)
    install_mocked_lifecycle(case, owner, monkeypatch)
    original_append = authority.AttemptReservation._append
    real_open, real_write, real_close = os.open, os.write, os.close
    helper_anchor = owner._reservation._dir_fd
    primary, secondary = OSError("owned append primary"), OSError("owned close secondary")
    active, temporary, close_attempts = [False], [], []
    append_calls, all_closes = [], []
    def append(reservation, value):
        if reservation is owner._reservation:
            append_calls.append(dict(value))
        active[0] = (reservation is owner._reservation
                     and value.get("event") == "identity" and value.get("kind") == kind)
        try:
            return original_append(reservation, value)
        finally:
            active[0] = False
    def open_file(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if active[0] and kwargs.get("dir_fd") == owner._reservation._dir_fd:
            assert path == owner._reservation._name
            temporary.append(fd)
        return fd
    def write(fd, raw):
        if active[0] and fd in temporary:
            raise primary
        return real_write(fd, raw)
    def close(fd):
        all_closes.append(fd)
        if active[0] and fd in temporary:
            close_attempts.append(fd)
            raise secondary
        return real_close(fd)
    try:
        with monkeypatch.context() as m:
            m.setattr(authority.AttemptReservation, "_append", append)
            m.setattr(authority.os, "open", open_file)
            m.setattr(authority.os, "write", write)
            m.setattr(authority.os, "close", close)
            with pytest.raises((OSError, api.CustodyError)) as caught:
                asyncio.run(owner.run_once())
            assert caught.value is primary or caught.value.primary is primary
            assert len(temporary) == 1 and close_attempts == temporary
            receipt = authority._custody_for_reservation(owner._reservation)
            assert owner._reservation_custody is receipt and receipt.primary is primary
            assert any(error is secondary for error in receipt.secondary)
            assert any(r.fd == temporary[0] and r.state == "UNKNOWN"
                       and r.close_error is secondary for r in receipt.records)
            assert stat.S_ISREG(os.fstat(temporary[0]).st_mode)
            assert set(owner._children) == (
                {"worker"} if kind == "app" else {"worker", "controller", "gate"})
            assert all(c.code is not None and c.reaped_ns is not None and c.record.closed
                       for c in owner._children.values())
            before_release = (list(append_calls), list(all_closes))
            for _ in range(2):
                with pytest.raises(api.CustodyError):
                    owner.release_joined()
            assert (append_calls, all_closes) == before_release
            assert close_attempts == temporary
            assert common._ACTIVE_HOST is owner and not owner._released
            assert not owner._reservation.closed
            assert not owner._writer._scratch._root.closed
    finally:
        # Dispose only the known owned fixture FD after checking live retention.
        # Production has no permission to infer/close this hidden generation.
        for fd in temporary:
            real_close(fd)
        # This anchor was never close-attempted, and belongs only to this
        # fixture. The UNKNOWN child cannot authorize production release.
        real_close(helper_anchor)


def test_actual_failed_claim_closed_receipt_releases_failed_owner_only(case, monkeypatch):
    primary, retained = OSError("owned policy validation failure"), []
    acquire = api.acquire_common_latch
    def capture(owner):
        retained.append(owner)
        return acquire(owner)
    def fail(*args, **kwargs):
        raise primary
    monkeypatch.setattr(api, "acquire_common_latch", capture)
    monkeypatch.setattr(authority, "_validate_policy_at", fail)
    with pytest.raises(OSError) as caught:
        api.admit_isolated_owner(preflight(case))
    assert caught.value is primary and len(retained) == 1
    owner = retained[0]
    receipt = authority._custody_for_failure(primary, authorization=case.auth)
    assert owner._reservation_custody is receipt and owner._reservation is None
    receipt.require_released()
    assert owner._released and common._ACTIVE_HOST is None and not owner._children
    assert not case.auth.bound and owner._execution is None


def test_actual_failed_claim_unknown_receipt_retains_latch_without_reservation(case, monkeypatch):
    primary, secondary = OSError("owned policy read failure"), OSError("owned policy close failure")
    real_open, real_close, real_read = os.open, os.close, os.read
    active, target, attempts = set(), [], []
    def open_file(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        active.add(fd)
        if str(path) == case.auth.policy_pin.path.name:
            target.append(fd)
        return fd
    def close(fd):
        if fd in target:
            attempts.append(fd)
            raise secondary
        real_close(fd)
        active.remove(fd)
    def read(fd, size):
        if fd in target:
            raise primary
        return real_read(fd, size)
    try:
        with monkeypatch.context() as m:
            m.setattr(authority.os, "open", open_file)
            m.setattr(authority.os, "close", close)
            m.setattr(authority.os, "read", read)
            with pytest.raises(api.CustodyError) as caught:
                api.admit_isolated_owner(preflight(case))
            owner = caught.value.owner
            receipt = authority._custody_for_failure(primary, authorization=case.auth)
            assert caught.value.primary is primary and owner._reservation is None
            assert owner._reservation_custody is receipt and receipt.has_unknown
            assert any(error is secondary for error in receipt.secondary)
            assert common._ACTIVE_HOST is owner and not owner._released
            before = list(attempts)
            for _ in range(2):
                with pytest.raises(api.CustodyError):
                    owner.release_joined()
            assert attempts == before == target and len(active) == 2
    finally:
        for fd in active:
            real_close(fd)


@pytest.mark.parametrize("kind", ["app", "sandbox"])
def test_known_clean_identity_failure_uses_receipt_for_failure_only_release(
        case, owner, monkeypatch, kind):
    register(case, owner)
    install_mocked_lifecycle(case, owner, monkeypatch)
    primary, writes = OSError("owned clean identity write failure"), []
    real_write = os.write
    def write(fd, raw):
        if b'"event":"identity"' in raw and ('"kind":"' + kind + '"').encode() in raw:
            writes.append(fd)
            raise primary
        return real_write(fd, raw)
    monkeypatch.setattr(authority.os, "write", write)
    with pytest.raises(OSError) as caught:
        asyncio.run(owner.run_once())
    assert caught.value is primary and len(writes) == 1
    receipt = owner._reservation_custody
    assert not receipt.has_unknown and receipt.primary is primary
    assert all(c.code is not None and c.record.closed for c in owner._children.values())
    with monkeypatch.context() as m:
        m.setattr(authority.os, "write", lambda *args: pytest.fail("failure cleanup appended again"))
        owner.release_joined()
    receipt.require_released()
    assert owner._released and common._ACTIVE_HOST is None and owner._execution is None


def test_known_clean_final_reservation_error_releases_then_preserves_primary(case, owner, monkeypatch):
    primary = OSError("owned final fsync failure")
    def fail(fd):
        raise primary
    monkeypatch.setattr(authority.os, "fsync", fail)
    with pytest.raises(api.CustodyError) as caught:
        owner.release_joined()
    assert caught.value.primary is primary and caught.value.released
    owner._reservation_custody.require_released()
    assert owner._released and common._ACTIVE_HOST is None and owner._execution is None
