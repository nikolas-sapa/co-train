"""Synthetic host transport checks, not native checkpoint or provider proof."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest


def make_case(tmp_path, monkeypatch):
    spec = importlib.util.find_spec("train.qualification_transfer")
    assert spec is not None, "bounded host transfer helper missing"
    api = importlib.import_module("train.qualification_transfer")
    nq = importlib.import_module("train.native_qualification")
    task_type = importlib.import_module("bench.task").SqlTask
    bounds = nq.AttemptBounds(Decimal(25), Decimal(0), Decimal(25), 1800, 4096, 4096, 60)
    assets = []
    tasks = []
    for index, key in enumerate(("example.py", nq._RUNTIME_KEY, "a", "b", "c", "d")):
        path = tmp_path / f"asset-{index}"
        raw = f"synthetic-{index}".encode()
        path.write_bytes(raw)
        kind = "source" if index < 2 else "data"
        assets.append(nq._StagedAsset(path, kind, key, len(raw), hashlib.sha256(raw).hexdigest()))
        if kind == "data":
            row = asdict(task_type(key, "fixture", "", "SELECT 1", key, str(path),
                                   "simple", "derived", "fixture", "fixture", "fixture"))
            row.pop("db_path")
            row["db_asset"] = key
            tasks.append(row)
    wire_bounds = asdict(bounds)
    for key, value in wire_bounds.items():
        if isinstance(value, Decimal):
            wire_bounds[key] = str(value)
    document = {
        "schema": "native-sql-worker-v1",
        "assets": [{key: getattr(asset, key) for key in ("kind", "key", "size", "sha256")}
                   for asset in assets],
        "tasks": tasks, "image_digest": "sha256:" + "0" * 64, "bounds": wire_bounds,
    }
    payload = json.dumps(document).encode()
    request = SimpleNamespace(output_dir=tmp_path / "export", bounds=bounds)
    monkeypatch.setattr(nq, "_prepare_worker_transport", lambda request: (payload, tuple(assets)))
    validations = []

    def validate(request, result):
        validations.append(result)
        return result.exported_root / "checkpoint-1", result.exported_root / "checkpoint-2"

    monkeypatch.setattr(nq, "_check_exported_artifacts", validate)
    now = [10.0]
    monkeypatch.setattr(api.time, "monotonic", lambda: now[0])
    resource = object()
    transport = MemoryTransport()
    members = []
    for index in (1, 2):
        key = f"checkpoint-{index}/synthetic.bin"
        raw = f"checkpoint-{index}".encode()
        transport.files[str(nq._OUTPUT / key)] = raw
        members.append(nq.FilePin(Path(key), len(raw), hashlib.sha256(raw).hexdigest()))
    return SimpleNamespace(api=api, nq=nq, assets=assets, payload=payload, document=document,
                           request=request, validations=validations, transport=transport,
                           resource=resource, members=tuple(members), now=now, tmp=tmp_path)


class MeasuredReader(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.reads = []
        self.after_read = None

    def read(self, size=-1):
        raw = super().read(size)
        self.reads.append((size, len(raw)))
        if self.after_read:
            self.after_read()
        return raw


class RemoteReader(MeasuredReader):
    def __init__(self, raw, metadata):
        super().__init__(raw)
        self.metadata = metadata
        self.stat_calls = 0
        self.drift = False

    def stat(self):
        self.stat_calls += 1
        values = list(self.metadata)
        if self.drift and self.stat_calls > 1:
            values[8] += 1
        return os.stat_result(values, {"st_mtime_ns": values[8] * 1000000000,
                                       "st_ctime_ns": 0})


class MemoryTransport:
    def __init__(self):
        self.files = {}
        self.writes = []
        self.opens = []
        self.short = False
        self.error = False
        self.tick = None
        self.mode = stat.S_IFREG | 0o600
        self.links = 1
        self.size_delta = 0
        self.drift = False
        self.suppress = False
        self.upload_bytes = 0
        self.readers = []
        self.reported_sizes = {}

    def write_file(self, resource, path, source, *, deadline):
        self.writes.append((resource, path, deadline))
        assert not hasattr(source, "name") and not hasattr(source, "fileno")
        if self.error:
            raise OSError("synthetic write failure")
        if self.short:
            raw = source.read(1)
            self.upload_bytes += len(raw)
            self.files[path] = raw
            return 1
        output = bytearray()
        self.files[path] = b""
        while True:
            if self.tick:
                self.tick()
            raw = source.read(3)
            self.upload_bytes += len(raw)
            if not raw:
                break
            output.extend(raw)
            self.files[path] = bytes(output)
        self.files[path] = bytes(output)
        return len(output)

    @contextmanager
    def open_export(self, resource, path, *, deadline):
        self.opens.append((resource, path, deadline))
        raw = self.files[path]
        metadata = os.stat_result((self.mode, 1, 1, self.links, 0, 0,
                                   self.reported_sizes.get(path, len(raw) + self.size_delta),
                                   0, 0, 0))
        stream = RemoteReader(raw, metadata)
        self.readers.append(stream)
        stream.drift = self.drift
        try:
            yield stream
        except Exception:
            if not self.suppress:
                raise
        finally:
            stream.close()


def budget(case, cap=100000):
    return case.api.TransferBudget(max_bytes=cap, deadline=100.0)


def stage(case, shared=None, **kwargs):
    return case.api.stage_worker_assets(case.request, transport=case.transport,
                                       resource=case.resource, budget=shared or budget(case), **kwargs)


def export(case, shared=None, members=None, codes=(0, 0)):
    return case.api.export_worker_checkpoints(
        case.request, case.members if members is None else members,
        transport=case.transport, resource=case.resource,
        phase_returncodes=codes, budget=shared or budget(case),
    )


def wire_bytes(case):
    return case.transport.upload_bytes + sum(
        returned for reader in case.transport.readers for requested, returned in reader.reads
    )


class CloseFaults:
    def __init__(self, case):
        self.case = case
        self.real_open = os.open
        self.real_close = os.close
        self.real_fdopen = os.fdopen
        self.acquired = []
        self.live = {}
        self.attempts = []
        self.streams = []
        self.fd_error = lambda token: None
        self.local_error = None
        self.remote_error = None
        self.read_error = None
        self.remote_exits = 0

    def open(self, path, flags, *args, **kwargs):
        fd = self.real_open(path, flags, *args, **kwargs)
        token = (len(self.acquired), fd, str(path))
        self.acquired.append(token)
        self.live[fd] = token
        return fd

    def close(self, fd):
        token = self.live[fd]
        self.attempts.append(token)
        error = self.fd_error(token)
        if error is not None:
            raise error
        self.real_close(fd)
        self.live.pop(fd)

    def fdopen(self, fd, *args, **kwargs):
        stream = self.real_fdopen(fd, *args, **kwargs)
        self.streams.append((stream, self.live[fd]))
        faults = self

        class LocalStream:
            def __getattr__(self, name):
                return getattr(stream, name)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

            def close(self):
                faults.attempts.append(faults.live[fd])
                if faults.local_error is not None:
                    raise faults.local_error
                stream.close()
                faults.live.pop(fd)

        return LocalStream()

    def install(self, patch):
        patch.setattr(self.case.api.os, "open", self.open)
        patch.setattr(self.case.api.os, "close", self.close)
        patch.setattr(self.case.api.os, "fdopen", self.fdopen)
        original = self.case.transport.open_export

        @contextmanager
        def remote(resource, path, *, deadline):
            with original(resource, path, deadline=deadline) as source:
                def after_read():
                    if self.read_error is not None and len(source.reads) == 2:
                        raise self.read_error

                source.after_read = after_read
                try:
                    yield source
                finally:
                    self.remote_exits += 1
                    if self.remote_error is not None:
                        raise self.remote_error

        patch.setattr(self.case.transport, "open_export", remote)

    def fallback(self):
        # Failed closes may or may not release custody; restore real cleanup on RED too.
        first = None
        for stream, token in self.streams:
            try:
                stream.close()
            except BaseException as error:
                if first is None:
                    first = error
            finally:
                if stream.closed and self.live.get(token[1]) == token:
                    self.live.pop(token[1])
        for fd in tuple(self.live):
            try:
                self.real_close(fd)
            except BaseException as error:
                if first is None:
                    first = error
            finally:
                self.live.pop(fd)
        if first is not None:
            raise first

    def assert_all_attempted(self):
        assert len(self.attempts) == len(self.acquired)
        assert set(self.attempts) == set(self.acquired)


def test_export_transfer_error_survives_remote_close(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    primary = OSError("synthetic transfer failure")
    faults.read_error = primary
    faults.remote_error = OSError("private-remote-path-must-not-be-noted")
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                export(case, shared)
            assert caught.value is primary
            assert primary.__notes__ == ["remote export context cleanup failed"]
            assert primary.__context__ is None
            assert faults.remote_exits == 1
            faults.assert_all_attempted()
            assert shared._failed and len(case.transport.opens) == 1
            assert case.validations == []
            assert (case.request.output_dir / case.members[0].path).is_file()
    finally:
        faults.fallback()


def test_export_cancellation_survives_all_cleanup(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)

    class CancelTransfer(BaseException):
        pass

    primary = CancelTransfer("synthetic cancellation")
    faults.read_error = primary
    faults.local_error = OSError("private-local-path-must-not-be-noted")
    faults.remote_error = OSError("private-remote-path-must-not-be-noted")
    faults.fd_error = lambda token: OSError("private-fd-must-not-be-noted") if (
        faults.remote_exits
    ) else None
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                export(case, shared)
            assert caught.value is primary
            assert set(primary.__notes__) == {
                "local export stream cleanup failed",
                "remote export context cleanup failed",
                "local descriptor cleanup failed",
            }
            assert primary.__context__ is None
            assert faults.remote_exits == 1
            faults.assert_all_attempted()
            assert shared._failed and len(case.transport.opens) == 1
            assert case.validations == []
            assert (case.request.output_dir / case.members[0].path).is_file()
    finally:
        faults.fallback()


def test_export_cleanup_only_error_survives_later_closes(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    first = OSError("synthetic first cleanup failure")
    failures = []

    def fail_final_close(token):
        if faults.remote_exits == 2:
            error = first if not failures else OSError("private-later-close-must-not-be-noted")
            failures.append(token)
            return error
        return None

    faults.fd_error = fail_final_close
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                export(case, shared)
            assert caught.value is first
            assert len(failures) == 4
            assert first.__notes__ == ["local descriptor cleanup failed"] * 3
            assert first.__context__ is None
            faults.assert_all_attempted()
            assert shared._failed and len(case.transport.opens) == faults.remote_exits == 2
            assert case.validations == []
            assert all((case.request.output_dir / pin.path).is_file() for pin in case.members)
    finally:
        faults.fallback()


def test_directory_predecessor_close_failure_closes_new_fd(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    primary = OSError("synthetic predecessor close failure")
    faults.fd_error = lambda token: primary if token[0] == 0 else None
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                with case.api._directory(tmp_path):
                    pytest.fail("directory body entered after predecessor close failure")
            assert caught.value is primary
            assert len(faults.acquired) == 2
            faults.assert_all_attempted()
            assert faults.attempts[1] == faults.acquired[1]
    finally:
        faults.fallback()


def test_upload_transport_error_survives_source_close(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    primary = OSError("synthetic upload transport failure")
    faults.local_error = OSError("private-source-path-must-not-be-noted")

    def fail_after_read():
        if case.transport.upload_bytes == 3:
            raise primary

    case.transport.tick = fail_after_read
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                stage(case, shared)
            assert caught.value is primary
            assert primary.__notes__ == ["local upload stream cleanup failed"]
            assert primary.__context__ is None
            assert len(case.transport.writes) == 1
            assert case.transport.upload_bytes == shared.transferred_bytes == 3
            assert shared._failed
            assert len(faults.streams) == 1 and not faults.streams[0][0].closed
            faults.assert_all_attempted()
    finally:
        faults.fallback()
    assert faults.live == {} and all(stream.closed for stream, token in faults.streams)


def test_upload_cancellation_survives_source_close(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)

    class CancelUpload(BaseException):
        pass

    primary = CancelUpload("synthetic upload cancellation")
    faults.local_error = OSError("private-source-path-must-not-be-noted")

    def cancel_after_read():
        if case.transport.upload_bytes == 3:
            raise primary

    case.transport.tick = cancel_after_read
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                stage(case, shared)
            assert caught.value is primary
            assert primary.__notes__ == ["local upload stream cleanup failed"]
            assert primary.__context__ is None
            assert len(case.transport.writes) == 1
            assert case.transport.upload_bytes == shared.transferred_bytes == 3
            assert shared._failed
            assert len(faults.streams) == 1 and not faults.streams[0][0].closed
            faults.assert_all_attempted()
    finally:
        faults.fallback()
    assert faults.live == {} and all(stream.closed for stream, token in faults.streams)


def test_source_fdopen_failure_closes_raw_fd_once(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    primary = OSError("synthetic source fdopen failure")
    failed = []

    def fail_fdopen(fd, *args, **kwargs):
        assert stat.S_ISREG(os.fstat(fd).st_mode)
        failed.append(faults.live[fd])
        raise primary

    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            patch.setattr(case.api.os, "fdopen", fail_fdopen)
            with pytest.raises(BaseException) as caught:
                stage(case, shared)
            assert caught.value is primary
            assert len(failed) == 1
            assert failed[0][2] == case.assets[0].host_path.name
            assert faults.attempts.count(failed[0]) == 1
            with pytest.raises(OSError) as closed:
                os.fstat(failed[0][1])
            assert closed.value.errno == 9
            assert faults.streams == [] and case.transport.writes == []
            assert shared._failed and shared.transferred_bytes == 0
            faults.assert_all_attempted()
    finally:
        faults.fallback()
    assert faults.live == {}


def test_upload_cleanup_only_source_error_propagates(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    faults = CloseFaults(case)
    primary = OSError("synthetic source cleanup-only failure")
    faults.local_error = primary
    shared = budget(case)
    try:
        with monkeypatch.context() as patch:
            faults.install(patch)
            with pytest.raises(BaseException) as caught:
                stage(case, shared)
            assert caught.value is primary
            assert getattr(primary, "__notes__", []) == []
            assert primary.__context__ is None
            assert len(case.transport.writes) == 1
            path = str(case.nq._asset_path(case.assets[0].kind, case.assets[0].key))
            assert case.transport.files[path] == case.assets[0].host_path.read_bytes()
            assert case.transport.upload_bytes == shared.transferred_bytes == case.assets[0].size
            assert shared._failed
            assert len(faults.streams) == 1 and not faults.streams[0][0].closed
            faults.assert_all_attempted()
    finally:
        faults.fallback()
    assert faults.live == {} and all(stream.closed for stream, token in faults.streams)


def overflow_final(case):
    member = case.members[-1]
    remote = str(case.nq._OUTPUT / member.path)
    case.transport.files[remote] += b"x"
    case.transport.reported_sizes[remote] = member.size


def test_stage_fixed_assets_and_wire(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    shared = budget(case)
    stage(case, shared)
    assert len(case.transport.writes) == 7
    assert case.transport.files[str(case.nq._REQUEST_FILE)] == case.payload
    for asset in case.assets:
        target = str(case.nq._asset_path(asset.kind, asset.key))
        assert case.transport.files[target] == asset.host_path.read_bytes()
        assert str(asset.host_path).encode() not in case.payload
    assert b"host_path" not in case.payload and b"credential" not in case.payload
    assert shared.transferred_bytes == sum(row.size for row in case.assets) + len(case.payload)


def test_stage_metadata_drift(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case.assets[0].host_path.write_bytes(b"larger-than-approved-synthetic")
    with pytest.raises(ValueError):
        stage(case)
    assert case.transport.writes == []


def test_stage_hash_drift(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case.assets[0].host_path.write_bytes(b"x" * case.assets[0].size)
    with pytest.raises(ValueError):
        stage(case)
    assert len(case.transport.writes) == 1
    assert str(case.nq._REQUEST_FILE) not in case.transport.files


def test_stage_duplicate_or_traversing_assets(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    for changed in (replace(case.assets[1], kind=case.assets[0].kind, key=case.assets[0].key),
                    replace(case.assets[1], key="../escape")):
        rows = (case.assets[0], changed, *case.assets[2:])
        monkeypatch.setattr(case.nq, "_prepare_worker_transport", lambda request: (case.payload, rows))
        with pytest.raises(ValueError):
            stage(case)
    assert case.transport.writes == []


def test_stage_links(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    original = case.assets[0]
    for kind in ("symlink", "hardlink"):
        link = case.tmp / kind
        if kind == "symlink":
            link.symlink_to(original.host_path)
        else:
            os.link(original.host_path, link)
        case.assets[0] = replace(original, host_path=link)
        with pytest.raises(ValueError):
            stage(case)
    assert case.transport.writes == []


def test_shared_total_cap(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    staging_size = len(case.payload) + sum(row.size for row in case.assets)
    shared = budget(case, staging_size + sum(row.size for row in case.members) - 1)
    stage(case, shared)
    with pytest.raises(ValueError):
        export(case, shared)
    assert case.transport.opens == []
    assert not case.request.output_dir.exists()


def test_shared_deadline(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case.now[0] = 100.0
    with pytest.raises(ValueError):
        stage(case)
    assert case.transport.writes == []
    case.now[0] = 10.0
    case.transport.tick = lambda: case.now.__setitem__(0, 100.0)
    with pytest.raises(ValueError):
        stage(case)
    assert len(case.transport.writes) == 1


def test_partial_stage_and_no_retry(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    for failure in ("short", "error"):
        case.transport.short = failure == "short"
        case.transport.error = failure == "error"
        shared = budget(case)
        before = len(case.transport.writes)
        with pytest.raises((ValueError, OSError)):
            stage(case, shared)
        with pytest.raises(ValueError):
            stage(case, shared)
        assert len(case.transport.writes) == before + 1


def test_export_fresh_private_and_rehashed(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    synced = []
    original = case.api.os.fsync

    def sync(fd):
        synced.append(os.fstat(fd).st_mode)
        original(fd)

    monkeypatch.setattr(case.api.os, "fsync", sync)
    paths = export(case)
    assert paths == tuple(case.request.output_dir / f"checkpoint-{i}" for i in (1, 2))
    assert len(case.validations) == 1 and len(case.transport.opens) == 2
    assert stat.S_IMODE(case.request.output_dir.stat().st_mode) == 0o700
    for member in case.members:
        path = case.request.output_dir / member.path
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert hashlib.sha256(path.read_bytes()).hexdigest() == member.sha256
    assert sum(stat.S_ISREG(mode) for mode in synced) >= 2


def test_export_no_overwrite(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    existing = case.tmp / "existing"
    existing.mkdir()
    marker = existing / "marker"
    marker.write_bytes(b"keep")
    for path in (existing, case.tmp / "alias"):
        if path != existing:
            path.symlink_to(existing, target_is_directory=True)
        case.request.output_dir = path
        with pytest.raises((ValueError, OSError)):
            export(case)
    assert marker.read_bytes() == b"keep"
    assert case.transport.opens == []


def test_export_invalid_members(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    first = case.members[0]
    for members in ((first, first), (replace(first, path=Path("../escape")),),
                    (replace(first, path=Path("/absolute")),),
                    (replace(first, path=Path("elsewhere/file")),)):
        with pytest.raises(ValueError):
            export(case, members=members)
    assert not case.request.output_dir.exists()
    assert case.transport.opens == []


def test_export_links_or_metadata_drift(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    for index, (mode, links, delta, drift) in enumerate((
        (stat.S_IFLNK, 1, 0, False), (stat.S_IFREG, 2, 0, False),
        (stat.S_IFIFO, 1, 0, False), (stat.S_IFREG, 1, 1, False),
        (stat.S_IFREG, 1, 0, True),
    )):
        case.request.output_dir = case.tmp / f"bad-metadata-{index}"
        case.transport.mode, case.transport.links = mode, links
        case.transport.size_delta, case.transport.drift = delta, drift
        with pytest.raises(ValueError):
            export(case)
    assert case.validations == []


def test_export_partial_overflow_hash_and_retention(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    first = case.members[0]
    remote = str(case.nq._OUTPUT / first.path)
    original = case.transport.files[remote]
    for index, raw in enumerate((original[:-1], original + b"x",
                                 b"x" * len(original), original[:-1])):
        case.request.output_dir = case.tmp / f"partial-{index}"
        case.transport.files[remote] = raw
        case.transport.size_delta = len(original) - len(raw)
        case.transport.suppress = index == 3
        before = len(case.transport.opens)
        with pytest.raises(ValueError):
            export(case)
        assert case.request.output_dir.is_dir()
        assert (case.request.output_dir / first.path).is_file()
        assert len(case.transport.opens) == before + 1
    assert case.validations == []


def test_export_fsync_and_local_rehash_failure(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    original = case.api.os.fsync
    for index in (0, 1):
        case.request.output_dir = case.tmp / f"durability-{index}"

        def sync(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                if index == 0:
                    raise OSError("synthetic fsync failure")
                path = case.request.output_dir / case.members[0].path
                path.write_bytes(b"x" * case.members[0].size)
            original(fd)

        monkeypatch.setattr(case.api.os, "fsync", sync)
        with pytest.raises((ValueError, OSError)):
            export(case)
        assert (case.request.output_dir / case.members[0].path).is_file()
    assert case.validations == []


def test_phase_or_final_validation_error(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    for codes in ((1, 0), (0, 1), (False, 0)):
        with pytest.raises(ValueError):
            export(case, codes=codes)
    assert not case.request.output_dir.exists() and case.transport.opens == []

    def reject(request, result):
        raise ValueError("synthetic final validator failure")

    monkeypatch.setattr(case.nq, "_check_exported_artifacts", reject)
    with pytest.raises(ValueError, match="final validator"):
        export(case)
    assert case.request.output_dir.is_dir()


def test_explicit_owner_and_shared_deadline(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    for transport, resource in ((None, case.resource), (case.transport, None)):
        with pytest.raises(ValueError):
            case.api.stage_worker_assets(case.request, transport=transport,
                                         resource=resource, budget=budget(case))
    for cap, deadline in ((True, 100), (0, 100), (100, float("inf")),
                          (100, True), (100, 1811)):
        with pytest.raises(ValueError):
            case.api.TransferBudget(max_bytes=cap, deadline=deadline)
    shared = budget(case)
    stage(case, shared)
    export(case, shared)
    calls = case.transport.writes + case.transport.opens
    assert all(resource is case.resource and deadline == shared.deadline
               for resource, path, deadline in calls)


def test_stage_requires_probe_headroom(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    shared = budget(case, len(case.payload) + sum(row.size for row in case.assets))
    with pytest.raises(ValueError):
        stage(case, shared)
    assert shared._failed and shared.transferred_bytes == wire_bytes(case) == 0
    assert case.transport.writes == []
    with pytest.raises(ValueError):
        stage(case, shared)
    assert case.transport.writes == []


def test_export_shared_exact_cap_requires_probe_headroom(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    staging_size = len(case.payload) + sum(row.size for row in case.assets)
    shared = budget(case, staging_size + sum(row.size for row in case.members))
    stage(case, shared)
    staged_files = dict(case.transport.files)
    overflow_final(case)
    with pytest.raises(ValueError):
        export(case, shared)
    assert shared._failed
    assert shared.transferred_bytes == wire_bytes(case) == staging_size
    assert wire_bytes(case) <= shared.max_bytes
    assert case.transport.opens == [] and not case.request.output_dir.exists()
    assert len(case.transport.writes) == 7 and case.validations == []
    for resource, path, deadline in case.transport.writes:
        assert case.transport.files[path] == staged_files[path]
    with pytest.raises(ValueError):
        export(case, shared)
    assert case.transport.opens == []


def test_shared_exact_streams_with_admitted_probe_headroom(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    declared = (len(case.payload) + sum(row.size for row in case.assets)
                + sum(row.size for row in case.members))
    probes = len(case.assets) + 1 + len(case.members)
    assert probes == 9
    shared = budget(case, declared + probes)
    stage(case, shared)
    export(case, shared)
    assert shared.transferred_bytes == wire_bytes(case) == declared
    assert shared.max_bytes - shared.transferred_bytes == probes
    assert not shared._failed and len(case.validations) == 1
    assert len(case.transport.writes) == 7 and len(case.transport.opens) == 2
    for reader in case.transport.readers:
        assert reader.reads[-1] == (1, 0)


def test_copy_export_caps_final_overflow_read(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    staging_size = len(case.payload) + sum(row.size for row in case.assets)
    shared = budget(case, staging_size + sum(row.size for row in case.members))
    stage(case, shared)
    overflow_final(case)
    paths = []
    with pytest.raises(ValueError):
        with case.api._operation(case.transport, case.resource, shared):
            for index, member in enumerate(case.members):
                path = case.tmp / f"copy-{index}"
                paths.append(path)
                remote = str(case.nq._OUTPUT / member.path)
                with case.transport.open_export(case.resource, remote,
                                                deadline=shared.deadline) as reader:
                    with path.open("wb") as target:
                        case.api._copy_export(reader, target, member, shared)
    assert shared._failed
    assert shared.transferred_bytes == wire_bytes(case) == shared.max_bytes
    assert len(paths) == len(case.transport.opens) == 2
    for path, member in zip(paths, case.members):
        assert path.read_bytes() == case.transport.files[str(case.nq._OUTPUT / member.path)][:member.size]
    remaining = shared.max_bytes - staging_size
    for reader in case.transport.readers:
        for requested, returned in reader.reads:
            assert 0 < requested <= remaining and returned <= requested
            remaining -= returned
    assert remaining == 0 and case.transport.readers[-1].reads == [(case.members[-1].size,
                                                                  case.members[-1].size)]
    before = len(case.transport.opens)
    with pytest.raises(ValueError):
        export(case, shared)
    assert len(case.transport.opens) == before and case.validations == []


def test_upload_caps_overflow_read(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    raw = b"payload"
    source = MeasuredReader(raw + b"x")
    shared = budget(case, len(raw))
    reader = case.api._Upload(source, len(raw), hashlib.sha256(raw).hexdigest(), shared)
    path = "synthetic-upload"
    with pytest.raises(ValueError):
        with case.api._operation(case.transport, case.resource, shared):
            case.transport.write_file(case.resource, path, reader, deadline=shared.deadline)
    actual = sum(returned for requested, returned in source.reads)
    assert source.reads == [(3, 3), (3, 3), (1, 1)]
    assert shared._failed and actual == shared.transferred_bytes == shared.max_bytes
    assert source.tell() == len(raw) and case.transport.files[path] == raw
    assert case.transport.upload_bytes == len(raw) and len(case.transport.writes) == 1
    with pytest.raises(ValueError):
        with case.api._operation(case.transport, case.resource, shared):
            case.transport.write_file(case.resource, path, reader, deadline=shared.deadline)
    assert len(case.transport.writes) == 1 and len(source.reads) == 3


def test_upload_exact_stream_with_admitted_probe_headroom(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    raw = b"payload"
    source = MeasuredReader(raw)
    shared = budget(case, len(raw) + 1)
    reader = case.api._Upload(source, len(raw), hashlib.sha256(raw).hexdigest(), shared)
    with case.api._operation(case.transport, case.resource, shared):
        written = case.transport.write_file(case.resource, "synthetic-upload", reader,
                                            deadline=shared.deadline)
        reader.finish(written)
    assert source.reads == [(3, 3), (3, 3), (2, 1), (1, 0)]
    assert shared.transferred_bytes == case.transport.upload_bytes == len(raw)
    assert not shared._failed


def test_export_overflow_probe_is_charged(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    declared = (len(case.payload) + sum(row.size for row in case.assets)
                + sum(row.size for row in case.members))
    shared = budget(case, declared + len(case.assets) + 1 + len(case.members))
    stage(case, shared)
    overflow_final(case)
    with pytest.raises(ValueError):
        export(case, shared)
    assert shared._failed
    assert shared.transferred_bytes == wire_bytes(case) == declared + 1
    assert wire_bytes(case) <= shared.max_bytes
    assert case.transport.readers[-1].reads == [(case.members[-1].size + 1,
                                               case.members[-1].size + 1)]
    assert len(case.transport.opens) == 2 and case.validations == []
    for member in case.members:
        assert (case.request.output_dir / member.path).is_file()
    before = wire_bytes(case)
    with pytest.raises(ValueError):
        export(case, shared)
    assert wire_bytes(case) == before and len(case.transport.opens) == 2


@pytest.mark.parametrize("direction", ("upload", "export"))
def test_read_bytes_charged_before_deadline_failure(tmp_path, monkeypatch, direction):
    case = make_case(tmp_path, monkeypatch)
    raw = b"abc"
    source = MeasuredReader(raw)
    source.after_read = lambda: case.now.__setitem__(0, 100.0)
    shared = budget(case, len(raw) + 1)
    pin = case.nq.FilePin(Path("checkpoint-1/synthetic.bin"), len(raw),
                          hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="deadline"):
        with case.api._operation(case.transport, case.resource, shared):
            if direction == "upload":
                reader = case.api._Upload(source, pin.size, pin.sha256, shared)
                reader.read(3)
            else:
                case.api._copy_export(source, io.BytesIO(), pin, shared)
    assert shared._failed and shared.transferred_bytes == len(raw)
    assert sum(returned for requested, returned in source.reads) == len(raw)
    assert len(source.reads) == 1
    with pytest.raises(ValueError, match="failed"):
        shared.check()
