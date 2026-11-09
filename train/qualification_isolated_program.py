"""Fixed worker body and V237 leased validation, new source SOURCEONLY UNRUN.

Only A calls the worker, on the genuine SDK loop, after retaining actual App
and Sandbox and acknowledging one-use CREATE. No lifecycle permits live here.
Only the registered owner calls the parent validator before normal shutdown.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import hashlib
import math
import os
from pathlib import Path
import stat
import time
from typing import Any

from train import qualification_engineering_run as original
from train.qualification_engineering_run import (
    EngineeringRunOutcome as OriginalEngineeringRunOutcome,
)
from train.qualification_isolated_contract import (
    APP, SANDBOX, FILE_LIMIT, MANIFEST_LIMIT, NS, OUTCOME_LIMIT, REQUEST_LIMIT,
    RPC_SOURCE_KEY, TOTAL_LIMIT, DelegatedWorkerHost, JoinedExecution,
    LaunchDescriptor, ManifestEntry, PreparedInputs, WorkerControl, WorkerInputs,
    WorkerProgramResult, byte_layer, canonical, closed, decode_launch,
    decode_manifest, digest, integer, parse_canonical, require,
)
from train.qualification_isolated_run import IsolatedReadCustodyError
from train.qualification_isolated_validation import validation_booking
from train.qualification_modal_transport import (
    CHUNK_BYTES, MAX_DEPTH, MAX_MEMBERS, ModalExecTransport, PlannedUpload,
    _ResponseAccumulator, _validate_key, parse_manifest_body,
)

_OUTCOME_FIELDS = {
    "attempt_id", "app_id", "sandbox_id", "phase_returncodes",
    "receipt_size", "receipt_sha256", "evidence_manifest", "exports",
}
_EXPORT_FIELDS = {"name", "path", "size", "sha256"}
_RETAINED_WORKER_FAILURES: list[BaseException] = []


class WorkerLocalCustodyError(IsolatedReadCustodyError):
    def __init__(self, resources: Any, primary: BaseException | None,
                 errors: tuple[BaseException, ...]):
        super().__init__("worker-local close unknown; resources retained")
        self.resources, self.primary, self.errors = resources, primary, errors


class _LocalFD:
    """Reserve in the actual local owner before acquisition, not after checks."""

    def __init__(self, owner: Any, anchor: Any):
        self.owner, self.anchor = owner, anchor
        self.fd: int | None = None
        self.attempted = self.closed = False
        self.failure: WorkerLocalCustodyError | None = None

    def acquire(self, name: str, flags: int, *, parent: int,
                mode: int = 0o600) -> int:
        require(self.fd is None and not self.attempted, "local acquisition once")
        self.fd = os.open(name, flags, mode, dir_fd=parent)
        # ACTUAL FD is now retained, before any fstat/check/exposure/await.
        return self.fd

    def close(self, primary: BaseException | None) -> None:
        if self.failure is not None:
            raise self.failure
        if self.fd is None or self.closed:
            return
        require(not self.attempted, "local close already attempted")
        self.attempted = True
        try:
            os.close(self.fd)
        except BaseException as cleanup:
            self.failure = WorkerLocalCustodyError(self, primary, (cleanup,))
            _RETAINED_WORKER_FAILURES.append(self.failure)
            raise self.failure from primary
        self.closed = True


def _private_regular(fd: int, *, limit: int, readonly: bool) -> os.stat_result:
    integer(fd, 2**31 - 1, 3)
    before = os.fstat(fd)
    original._regular(before)
    require(before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600,
            "private owner600 regular FD")
    integer(before.st_size, limit)
    access = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
    require(access == (os.O_RDONLY if readonly else os.O_RDWR), "FD access mode")
    return before


def _read_fd(fd: int, *, limit: int, size: int, sha256: str,
             readonly: bool, deadline: float | None = None) -> tuple[bytes, tuple[int, ...]]:
    integer(size, limit, 1)
    digest(sha256)
    before = _private_regular(fd, limit=limit, readonly=readonly)
    require(before.st_size == size, "actual FD size differs")
    identity = original._identity(before)
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, count, hasher = [], 0, hashlib.sha256()
    while True:
        require(deadline is None or time.monotonic() < deadline, "FD read deadline")
        block = os.read(fd, min(CHUNK_BYTES, size - count + 1))
        if not block:
            break
        count += len(block)
        require(count <= size, "FD grew beyond sealed size")
        hasher.update(block)
        chunks.append(block)
    require(count == size and hasher.hexdigest() == sha256, "actual FD bytes differ")
    require(original._identity(_private_regular(fd, limit=limit, readonly=readonly))
            == identity, "FD identity changed during read")
    return b"".join(chunks), identity


class _BorrowedAnchor(original._Anchor):
    """Use a borrowed directory FD, never call _Anchor's pathname constructor."""

    def __init__(self, fd: int):
        integer(fd, 2**31 - 1, 3)
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode), "borrowed directory FD")
        self.fd = self._borrowed_fd = fd
        self._borrowed_identity = original._directory_identity(info)
        self.path = Path("/")  # Inert logical path, never opened.
        self._fds: list[int] = []
        self._pins: list[Any] = []
        self._directories: dict[tuple[int, str], int] = {}
        self._records: list[_LocalFD] = []
        self.check()

    def child(self, parent: int, name: str, *, create: bool = False) -> int:
        require(type(name) is str and name not in {"", ".", ".."}
                and "/" not in name and "\\" not in name and "\0" not in name,
                "directory component refused")
        self.check()
        cached = self._directories.get((parent, name))
        if cached is not None:
            return cached
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        record = _LocalFD(self, self)
        self._records.append(record)
        try:
            fd = record.acquire(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, parent=parent)
            self._fds.append(fd)
            opened = os.fstat(fd)
            pin = original._directory_identity(opened)
            require(stat.S_ISDIR(opened.st_mode)
                    and pin == original._directory_identity(before)
                    and opened.st_uid == os.getuid()
                    and stat.S_IMODE(opened.st_mode) == 0o700,
                    "private directory identity changed")
            self._pins.append((parent, name, fd, pin))
            self._directories[parent, name] = fd
            self.check()
            return fd
        except BaseException as primary:
            record.close(primary)
            if record.fd in self._fds:
                self._fds.remove(record.fd)
            raise

    def check(self) -> None:
        require(original._directory_identity(os.fstat(self._borrowed_fd))
                == self._borrowed_identity, "borrowed directory identity changed")
        super().check()

    def close(self) -> None:
        for record in reversed(self._records):
            record.close(None)  # Unknown close stops, retaining all ancestors.
            if record.fd in self._fds:
                self._fds.remove(record.fd)


class _SnapshotInventory:
    """Actual original _Snapshot instances, opened ONLY at generated names."""

    def __init__(self, directory_fd: int, entries: tuple[ManifestEntry, ...],
                 *, deadline: float):
        self.anchor = _BorrowedAnchor(directory_fd)
        info = os.fstat(directory_fd)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "private snapshot directory")
        require(fcntl.fcntl(directory_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
                "readonly snapshot directory")
        self.entries, self.deadline = entries, deadline
        self.fds: list[int] = []
        self.close_errors: list[BaseException] = []
        self.records: list[_LocalFD] = []

    def __enter__(self) -> _SnapshotInventory:
        return self

    @contextmanager
    def member(self, entry: ManifestEntry):
        require(not self.fds and not self.close_errors,
                "snapshot member active or close unknown")
        digest(entry.snapshot_key)
        require(time.monotonic() < self.deadline, "snapshot hash deadline")
        parent, name = self.anchor.parent(entry.snapshot_key)
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        original._regular(before)
        record = _LocalFD(self, self.anchor)
        self.records.append(record)
        primary = None
        try:
            fd = record.acquire(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, parent=parent)
            self.fds.append(fd)
            _private_regular(fd, limit=FILE_LIMIT, readonly=True)
            identity = original._identity(os.fstat(fd))
            require(identity == original._identity(before), "snapshot open identity changed")
            self.anchor.check()
            require(original._hash_fd(fd, limit=entry.size, deadline=self.deadline)
                    == (entry.size, entry.sha256), "snapshot actual bytes differ")
            original._check_file(self.anchor, fd, parent, name, identity)
            item = PlannedUpload(entry.root, entry.key, entry.size,
                                 entry.sha256, Path(entry.snapshot_key))
            snapshot = original._Snapshot(item, self.anchor, parent, name, fd)
            require(snapshot.identity == identity, "snapshot identity changed")
            snapshot.check()
            yield snapshot
            snapshot.check()
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                record.close(primary)
            except WorkerLocalCustodyError as failure:
                self.close_errors.extend(failure.errors)
                raise
            else:
                if record.fd in self.fds:
                    self.fds.remove(record.fd)

    def stream(self):
        for entry in self.entries:
            with self.member(entry) as snapshot:
                yield snapshot

    def __exit__(self, kind: Any, primary: Any, tb: Any) -> None:
        # A stream must be closed before exiting. Never retry an ambiguous
        # close, or close a recycled FD number a second time.
        if self.fds or self.close_errors:
            if isinstance(primary, WorkerLocalCustodyError):
                return  # Propagate the original primary AND close failures intact.
            failure = WorkerLocalCustodyError(self, primary, tuple(self.close_errors))
            _RETAINED_WORKER_FAILURES.append(failure)
            raise failure from primary


class _RegisteredExportFile(original._ExportFile):
    """Original sink/finish/check behavior, with safe acquisition custody."""

    def __init__(self, tree: _AnchoredExportTree, key: str):
        _validate_key(key)
        tree.check()
        self.tree, self.key = tree, key
        self.parent, self.name = tree.anchor.parent(key, create=True)
        self.count, self.digest, self.final = 0, hashlib.sha256(), None
        record = _LocalFD(tree, tree.anchor)
        tree.records.append(record)
        self.fd = record.acquire(
            self.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            parent=self.parent)
        tree.files.append(self)
        created = os.fstat(self.fd)
        original._regular(created)
        require(created.st_uid == os.getuid() and stat.S_IMODE(created.st_mode) == 0o600,
                "private created export")
        self.created = created.st_dev, created.st_ino


class _AnchoredExportTree(original._ExportTree):
    """Reuse original file sinks beneath the inherited export-parent anchor."""

    def __init__(self, parent_fd: int, name: str, *, deadline: float):
        # The logical root affects DTO labels only. It is never reopened.
        super().__init__(Path("/") / name, deadline=deadline)
        self._parent_fd = parent_fd
        self.records: list[_LocalFD] = []

    def create(self, key: str) -> _RegisteredExportFile:
        return _RegisteredExportFile(self, key)

    def __enter__(self) -> _AnchoredExportTree:
        self.anchor = _BorrowedAnchor(self._parent_fd)
        try:
            self.check_deadline()
            os.mkdir(self.root.name, 0o700, dir_fd=self._parent_fd)
            self.anchor.fd = self.anchor.child(self._parent_fd, self.root.name)
            info = os.fstat(self.anchor.fd)
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                    "private export root")
            self.check()
            return self
        except BaseException as primary:
            try:
                self.anchor.close()
            except BaseException as cleanup:
                failure = WorkerLocalCustodyError(self, primary, (cleanup,))
                _RETAINED_WORKER_FAILURES.append(failure)
                raise failure from primary
            raise

    def __exit__(self, kind: Any, primary: Any, tb: Any) -> None:
        errors = []
        if primary is None:
            try:
                self.check()
            except BaseException as error:
                errors.append(error)
        for record in reversed(self.records):
            try:
                record.close(primary)
            except BaseException as error:
                errors.append(error)
                break
        if not errors:
            try:
                self.anchor.close()
            except BaseException as error:
                errors.append(error)
        # Never delete failed partials, release borrowed FDs or suppress a close.
        if errors:
            failure = WorkerLocalCustodyError(self, primary, tuple(errors))
            _RETAINED_WORKER_FAILURES.append(failure)
            raise failure from primary


def _require_sdk_loop() -> None:
    # Only the worker calls this. Accepted fresh-constructor reference uses this
    # exact loop identity, not an ordinary asyncio loop or public .aio objects.
    from modal._utils.async_utils import synchronizer
    require(asyncio.get_running_loop() is synchronizer._get_loop(start=False),
            "genuine worker SDK loop required")


def _deadlines(host: DelegatedWorkerHost,
               launch: LaunchDescriptor) -> tuple[float, float, float]:
    integer(host.end_ns, minimum=1)
    require(0 < host.end_ns - time.monotonic_ns() <= launch.attempt_ns <= 1800 * NS,
            "actual E exceeds original attempt allowance")
    booking = validation_booking(host.end_ns, launch.timing.teardown_ns)
    # S tightens the original reserves. Actual host.end_ns remains E.
    end = math.nextafter(booking.phase_end_ns / NS, -math.inf)
    return original._stage_deadlines(end, time.monotonic())


def _input_document(inputs: WorkerInputs, launch: LaunchDescriptor,
                    *, deadline: float) -> dict[str, Any]:
    require(type(inputs) is WorkerInputs and type(launch) is LaunchDescriptor,
            "fixed worker input types")
    manifest, manifest_identity = _read_fd(
        inputs.fds.manifest, limit=MANIFEST_LIMIT, size=launch.manifest_size,
        sha256=launch.manifest_sha256, readonly=True, deadline=deadline)
    entries = decode_manifest(manifest)
    require(entries == inputs.entries, "worker manifest entries differ")
    request_payload, request_identity = _read_fd(
        inputs.fds.request, limit=REQUEST_LIMIT, size=launch.request_size,
        sha256=launch.request_sha256, readonly=True, deadline=deadline)
    require(request_payload == inputs.request_payload, "worker request bytes differ")
    from train import native_qualification as native
    # Data decoding only. Never reconstruct SealedAuthorization or an App.
    document = native._decode_worker_transport(request_payload)
    expected = {(row["kind"], row["key"], row["size"], row["sha256"])
                for row in document["assets"]}
    actual = {(e.root, e.key, e.size, e.sha256) for e in entries
              if e.root in {"source", "model", "data"}}
    require(actual == expected, "wire original source/model/data coverage")
    request = next(e for e in entries if e.root == "request")
    require((request.size, request.sha256) == (launch.request_size, launch.request_sha256),
            "manifest derived request differs")
    launch_raw_size = os.fstat(inputs.fds.launch).st_size
    integer(launch_raw_size, REQUEST_LIMIT, 1)
    # Launch hash is held/validated by A before dispatch. C independently
    # requires exact canonical bytes of the supplied sealed descriptor.
    from train.qualification_isolated_contract import encode_launch
    expected_launch = encode_launch(launch)
    launch_raw, launch_identity = _read_fd(
        inputs.fds.launch, limit=REQUEST_LIMIT, size=len(expected_launch),
        sha256=hashlib.sha256(expected_launch).hexdigest(),
        readonly=True, deadline=deadline)
    require(decode_launch(launch_raw) == launch, "inherited launch differs")
    for fd, identity in ((inputs.fds.manifest, manifest_identity),
                         (inputs.fds.request, request_identity),
                         (inputs.fds.launch, launch_identity)):
        require(original._identity(os.fstat(fd)) == identity, "input FD changed after decode")
    return document


def _outcome_document(outcome: OriginalEngineeringRunOutcome) -> dict[str, Any]:
    require(type(outcome) is OriginalEngineeringRunOutcome, "original outcome type")
    # Wire paths are relative export labels, never host paths or authority.
    # Parent reconstructs original EvidenceExport Path values below its anchor.
    return dict(
        attempt_id=outcome.attempt_id, app_id=outcome.app_id,
        sandbox_id=outcome.sandbox_id, phase_returncodes=list(outcome.phase_returncodes),
        receipt_size=outcome.receipt_size, receipt_sha256=outcome.receipt_sha256,
        evidence_manifest=list(outcome.evidence_manifest),
        exports=[dict(name=e.name, path=e.name, size=e.size, sha256=e.sha256)
                 for e in outcome.exports],
    )


def _outcome_header(doc: dict[str, Any]) -> None:
    digest(doc["attempt_id"])
    require(type(doc["app_id"]) is str and APP.fullmatch(doc["app_id"]) is not None,
            "original outcome App ID")
    require(type(doc["sandbox_id"]) is str
            and SANDBOX.fullmatch(doc["sandbox_id"]) is not None,
            "original outcome Sandbox ID")
    codes = doc["phase_returncodes"]
    require(type(codes) is list and len(codes) == 2
            and all(type(code) is int and code == 0 for code in codes),
            "original successful phase codes")
    integer(doc["receipt_size"], REQUEST_LIMIT, 1)
    digest(doc["receipt_sha256"])
    require(type(doc["evidence_manifest"]) is list, "evidence array")
    evidence = parse_manifest_body(
        canonical(doc["evidence_manifest"]), max_bytes=3 * REQUEST_LIMIT,
        max_members=3, max_depth=0, json_limit=REQUEST_LIMIT)
    require(len(evidence) == 3
            and {e["key"] for e in evidence} == set(original._EVIDENCE_KEYS),
            "exact evidence coverage")
    require(all(e["size"] <= REQUEST_LIMIT for e in evidence), "evidence member cap")
    exports = doc["exports"]
    require(type(exports) is list and 3 <= len(exports) <= MAX_MEMBERS + 3,
            "original exports array")


def _export_metadata(item: dict[str, Any], seen: set[str]) -> None:
    closed(item, _EXPORT_FIELDS)
    require(type(item["name"]) is str, "export name string")
    _validate_key(item["name"])
    require(type(item["path"]) is str and item["path"] == item["name"],
            "export path must be relative anchored name")
    integer(item["size"], FILE_LIMIT)
    digest(item["sha256"])
    require(item["name"] not in seen, "duplicate export")
    seen.add(item["name"])


def _closed_outcome(raw: bytes) -> dict[str, Any]:
    doc = closed(parse_canonical(raw, OUTCOME_LIMIT), _OUTCOME_FIELDS)
    _outcome_header(doc)
    seen = set()
    for item in doc["exports"]:
        _export_metadata(item, seen)
    require(sum(item["size"] for item in doc["exports"]) <= TOTAL_LIMIT + 3 * REQUEST_LIMIT,
            "original export aggregate cap")
    return doc


def _write_outcome(fd: int, outcome: OriginalEngineeringRunOutcome,
                   *, deadline: float) -> WorkerProgramResult:
    raw = byte_layer(canonical(_outcome_document(outcome)), OUTCOME_LIMIT)
    _closed_outcome(raw)
    before = _private_regular(fd, limit=OUTCOME_LIMIT, readonly=False)
    require(before.st_size == 0, "outcome is one-write only")
    require(time.monotonic() < deadline, "outcome write deadline")
    os.lseek(fd, 0, os.SEEK_SET)
    for offset in range(0, len(raw), CHUNK_BYTES):
        require(time.monotonic() < deadline, "outcome write deadline")
        original._write_all(fd, raw[offset:offset + CHUNK_BYTES])
    os.fsync(fd)
    after = _private_regular(fd, limit=OUTCOME_LIMIT, readonly=False)
    require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
            and after.st_size == len(raw), "outcome identity/size differs")
    size, sha = original._hash_fd(fd, limit=OUTCOME_LIMIT, deadline=deadline)
    require((size, sha) == (len(raw), hashlib.sha256(raw).hexdigest()),
            "actual outcome bytes differ")
    require(original._identity(os.fstat(fd)) == original._identity(after),
            "outcome changed during final hash")
    require(time.monotonic() < deadline, "worker export deadline expired")
    return WorkerProgramResult(size, sha)


async def run_prepared_worker(
    *, inputs: WorkerInputs, launch: LaunchDescriptor,
    host: DelegatedWorkerHost, control: WorkerControl,
) -> WorkerProgramResult:
    """Original body order, once, after A's actual retained Sandbox ACK."""
    _require_sdk_loop()
    work_deadline, verify_deadline, export_deadline = _deadlines(host, launch)
    host.require_setup_argv(launch.setup_argv)
    require(host.resource is not None, "actual retained raw Sandbox required")
    require(APP.fullmatch(host.app_id) is not None
            and SANDBOX.fullmatch(host.sandbox_id) is not None, "actual host IDs")
    document = _input_document(inputs, launch, deadline=work_deadline)
    from train import native_qualification as native
    bounds = native._bounds_from_wire(document["bounds"])
    require(launch.attempt_ns <= bounds.lifetime_seconds * NS,
            "launch exceeds original request allowance")
    require(host.end_ns - time.monotonic_ns() <= launch.attempt_ns,
            "host end exceeds original committed allowance")
    with _SnapshotInventory(inputs.fds.snapshot_dir, inputs.entries,
                            deadline=work_deadline) as snapshots:
        rpc_entry = next(e for e in inputs.entries
                         if (e.root, e.key) == ("source", RPC_SOURCE_KEY))
        with snapshots.member(rpc_entry) as rpc:
            rpc_source = rpc.bounded_bytes(REQUEST_LIMIT)
        request_entry = next(e for e in inputs.entries if e.root == "request")
        with snapshots.member(request_entry) as request:
            require(request.bounded_bytes(REQUEST_LIMIT) == inputs.request_payload,
                    "derived request snapshot differs")
        transport = ModalExecTransport(host, clock=time.monotonic)
        transport.sandbox = host.resource
        transport.bind_runtime(
            rpc_source=rpc_source, rpc_sha256=rpc_entry.sha256,
            setup_argv=launch.setup_argv, request_sha256=launch.request_sha256,
            uploads=inputs.entries)
        stream = snapshots.stream()
        try:
            await transport.stage_uploads(stream, deadline=work_deadline)
        finally:
            stream.close()
        await transport.exec_once(
            launch.setup_argv, stdout_limit=REQUEST_LIMIT,
            stderr_limit=REQUEST_LIMIT, deadline=work_deadline)
        await transport.exec_once(
            transport.materialize_argv, stdout_limit=REQUEST_LIMIT,
            stderr_limit=REQUEST_LIMIT, deadline=work_deadline)
        app_id, sandbox_id = host.app_id, host.sandbox_id
        attempt = original._attempt_id(launch.request_binding, app_id, sandbox_id)
        private = dict(v=1, op="native-attempt", request_sha256=launch.request_binding,
                       attempt_id=attempt, app_id=app_id, sandbox_id=sandbox_id)
        native_input = original._canonical_json(private)
        await transport.exec_once(
            original.NATIVE_ARGV, input_chunks=(native_input,),
            stdout_limit=REQUEST_LIMIT, stderr_limit=REQUEST_LIMIT,
            deadline=work_deadline)
        index = _ResponseAccumulator(REQUEST_LIMIT)
        await transport.exec_once(
            original.VERIFY_ARGV,
            input_chunks=(original._canonical_json({**private, "op": "remote-verify"}),),
            stdout_sink=index, stdout_limit=REQUEST_LIMIT, stderr_limit=REQUEST_LIMIT,
            deadline=verify_deadline)
        evidence_manifest = parse_manifest_body(
            index.payload, max_bytes=3 * REQUEST_LIMIT, max_members=3,
            max_depth=0, json_limit=REQUEST_LIMIT)
        fetched = await original._pull_evidence(
            transport, evidence_manifest, deadline=export_deadline)
        require(fetched[original._LATCH_KEY] == native_input, "exclusive remote latch differs")
        observations = original._load_strict_json(fetched[original._OBSERVATIONS_KEY])
        _, codes = original._validate_observations(
            observations, binding=launch.request_binding, attempt=attempt,
            app_id=app_id, sandbox_id=sandbox_id)
        receipt = original._load_strict_json(fetched[original._RECEIPT_KEY])
        manifest = original._validate_receipt(
            receipt, binding=launch.request_binding, attempt=attempt, app_id=app_id,
            sandbox_id=sandbox_id, observations=observations,
            artifact_limit=bounds.artifact_bytes)
        current = await transport.output_manifest(
            max_bytes=bounds.artifact_bytes, deadline=export_deadline)
        require(current == manifest, "receipt-pinned output manifest changed")
        require(time.monotonic() < export_deadline, "export reserve expired")
        with _AnchoredExportTree(inputs.fds.export_parent, launch.export_name,
                                 deadline=export_deadline) as tree:
            exports = list(await original._export_artifacts(
                transport, tree, manifest, deadline=export_deadline))
            for key in original._EVIDENCE_KEYS:
                exports.append(tree.write_bytes("evidence/" + key, fetched[key]))
            tree.check()
        payload = fetched[original._RECEIPT_KEY]
        outcome = OriginalEngineeringRunOutcome(
            attempt, app_id, sandbox_id, codes, len(payload),
            hashlib.sha256(payload).hexdigest(), evidence_manifest, tuple(exports))
        # A alone sends OUTCOME and drives STOP. No bulk/control lifecycle here.
        return _write_outcome(inputs.fds.outcome, outcome, deadline=export_deadline)


class ParentReaderCustodyError(IsolatedReadCustodyError):
    """A retains actual resources; C also retains exact lease/reader failures."""

    def __init__(self, lease: Any, reader: Any, primary: BaseException | None,
                 cleanup: BaseException):
        super().__init__("parent reader close unknown; owner release forbidden")
        self.lease, self.reader = lease, reader
        self.primary, self.cleanup = primary, cleanup


_RETAINED_PARENT_FAILURES: list[ParentReaderCustodyError] = []


class _LeaseReads:
    """No FD access. All operations remain subject to A's live generation."""

    def __init__(self, lease: Any, execution: JoinedExecution, end_ns: int,
                 read_ns: int):
        self.lease, self.execution = lease, execution
        self.end_ns, self.read_ns = end_ns, read_ns
        self.verified: list[Any] = []

    def check(self) -> None:
        require(self.lease.end_ns == self.end_ns
                and self.lease.read_deadline_ns == self.read_ns
                and self.lease.worker_execution is self.execution,
                "fixed lease facts changed")
        require(time.monotonic_ns() < self.read_ns, "fixed validation deadline expired")

    async def checkpoint(self) -> None:
        self.check()
        await self.lease.checkpoint()  # Independently checks shutdown and yields.
        self.check()

    async def identity(self, reader: Any) -> None:
        await self.checkpoint()
        await reader.check_identity()
        await self.checkpoint()

    async def read(self, key: str | None, *, size: int, sha256: str,
                   retain: bool) -> bytes:
        integer(size, OUTCOME_LIMIT if key is None else FILE_LIMIT)
        digest(sha256)
        await self.checkpoint()
        reader = self.lease.open_outcome() if key is None else self.lease.open_export(key)
        primary = None
        try:
            await self.checkpoint()
            await self.identity(reader)
            count, hasher, chunks = 0, hashlib.sha256(), []
            while True:
                await self.checkpoint()
                maximum = min(65536, size - count + 1)
                block = await reader.read(maximum)
                await self.checkpoint()
                require(type(block) is bytes and len(block) <= maximum,
                        "bounded lease read bytes required")
                if not block:
                    break
                count += len(block)
                require(count <= size, "leased file grew beyond sealed size")
                hasher.update(block)
                if retain:
                    chunks.append(block)
            require((count, hasher.hexdigest()) == (size, sha256),
                    "leased actual full hash/size differs")
            await self.identity(reader)
            self.verified.append(reader)  # A retains named pins AFTER data close.
            return b"".join(chunks)
        except BaseException as error:
            primary = error
            raise
        finally:
            # Closing must still happen after expiry/cancellation. A checks C,
            # retains unknown closes and intermediates; never retry this number.
            try:
                reader.close()
            except BaseException as cleanup:
                failure = ParentReaderCustodyError(self.lease, reader, primary, cleanup)
                _RETAINED_PARENT_FAILURES.append(failure)
                raise failure from primary

    async def inventory(self, expected: dict[str, dict[str, Any]]) -> None:
        expected_dirs: set[str] = set()
        for key in expected:
            await self.checkpoint()
            parts = key.split("/")
            require(len(parts) - 1 <= MAX_DEPTH, "export tree depth")
            expected_dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
            require(len(expected_dirs) + len(expected) <= 20000 + 4,
                    "export directory entry cap")
        await self.checkpoint()
        entries = await self.lease.export_inventory()
        await self.checkpoint()
        require(type(entries) is tuple and len(entries) <= 20000 + 4,
                "export directory entry cap")
        seen, files, directories = set(), set(), set()
        for entry in entries:
            await self.checkpoint()
            # Frozen relative-key/kind/size data, never file descriptors.
            key = entry.key
            _validate_key(key)
            integer(entry.size, FILE_LIMIT)
            require(key not in seen, "duplicate export inventory entry")
            seen.add(key)
            if entry.kind == "directory":
                require(key in expected_dirs, "undeclared export directory")
                directories.add(key)
            else:
                require(entry.kind == "file" and key in expected,
                        "undeclared export file/kind")
                require(entry.size == expected[key]["size"], "inventory file size differs")
                files.add(key)
            await self.checkpoint()
        require(files == set(expected) and directories == expected_dirs,
                "export tree exact coverage")

    async def payload_facts(self, payload: bytes) -> tuple[int, str]:
        hasher = hashlib.sha256()
        for offset in range(0, len(payload), 65536):
            await self.checkpoint()
            hasher.update(payload[offset:offset + 65536])
            await self.checkpoint()
        return len(payload), hasher.hexdigest()


async def _validate_outcome_lease(
    request: Any, *, prepared: PreparedInputs, execution: JoinedExecution,
    export_root: Path, lease: Any, end_ns: int, read_deadline_ns: int,
) -> OriginalEngineeringRunOutcome:
    """Only fixed _ParentValidator calls this after A's registration assertion."""
    require(type(prepared) is PreparedInputs and type(execution) is JoinedExecution,
            "exact worker/prepared types")
    integer(request.bounds.artifact_bytes, TOTAL_LIMIT, 1)
    require(execution.outcome_size is not None and execution.outcome_sha256 is not None,
            "actual outcome facts required")
    reads = _LeaseReads(lease, execution, end_ns, read_deadline_ns)
    raw = await reads.read(
        None, size=execution.outcome_size, sha256=execution.outcome_sha256, retain=True)
    await reads.checkpoint()
    doc = closed(parse_canonical(raw, OUTCOME_LIMIT), _OUTCOME_FIELDS)
    _outcome_header(doc)
    await reads.checkpoint()
    exports_by_name, seen, total, bulk_total = {}, set(), 0, 0
    evidence_names = {"evidence/" + key for key in original._EVIDENCE_KEYS}
    exported_evidence_names: set[str] = set()
    for item in doc["exports"]:
        await reads.checkpoint()
        _export_metadata(item, seen)
        exports_by_name[item["name"]] = item
        if item["name"].startswith("evidence/"):
            exported_evidence_names.add(item["name"])
        total += item["size"]
        if item["name"] in evidence_names:
            require(item["size"] <= REQUEST_LIMIT, "exported evidence caps before read")
        else:
            bulk_total += item["size"]
        await reads.checkpoint()
    require(total <= TOTAL_LIMIT + 3 * REQUEST_LIMIT, "original export aggregate cap")
    require(bulk_total <= request.bounds.artifact_bytes, "original artifact cap before read")
    require(exported_evidence_names == evidence_names, "exported evidence names")
    from train import native_qualification as native
    binding = native._request_binding(request)  # Metadata only, no serializer.
    attempt = original._attempt_id(binding, execution.app_id, execution.sandbox_id)
    require((doc["attempt_id"], doc["app_id"], doc["sandbox_id"])
            == (attempt, execution.app_id, execution.sandbox_id), "outcome identity differs")
    await reads.checkpoint()
    await reads.inventory(exports_by_name)
    evidence_bytes = {}
    for item in doc["exports"]:
        await reads.checkpoint()
        if item["name"] in evidence_names:
            evidence_bytes[item["name"][len("evidence/"):]] = await reads.read(
                item["name"], size=item["size"], sha256=item["sha256"], retain=True)
    require(set(evidence_bytes) == set(original._EVIDENCE_KEYS), "exported evidence coverage")
    private = dict(v=1, op="native-attempt", request_sha256=binding,
                   attempt_id=attempt, app_id=execution.app_id, sandbox_id=execution.sandbox_id)
    require(evidence_bytes[original._LATCH_KEY] == original._canonical_json(private),
            "original exported latch differs")
    evidence_manifest = parse_manifest_body(
        canonical(doc["evidence_manifest"]), max_bytes=3 * REQUEST_LIMIT,
        max_members=3, max_depth=0, json_limit=REQUEST_LIMIT)
    for entry in evidence_manifest:
        await reads.checkpoint()
        require(await reads.payload_facts(evidence_bytes[entry["key"]])
                == (entry["size"], entry["sha256"]), "evidence descriptor differs")
    observations = original._load_strict_json(evidence_bytes[original._OBSERVATIONS_KEY])
    receipt_bytes = evidence_bytes[original._RECEIPT_KEY]
    require(await reads.payload_facts(receipt_bytes)
            == (doc["receipt_size"], doc["receipt_sha256"]), "receipt actual identity differs")
    await reads.checkpoint()
    # Keep the original bounded metadata/receipt/observation validator intact.
    manifest = original._validate_receipt(
        original._load_strict_json(receipt_bytes), binding=binding, attempt=attempt,
        app_id=execution.app_id, sandbox_id=execution.sandbox_id,
        observations=observations, artifact_limit=request.bounds.artifact_bytes)
    await reads.checkpoint()
    expected_exports = {}
    for entry in manifest:
        await reads.checkpoint()
        expected_exports[entry["key"]] = entry["size"], entry["sha256"]
    for entry in evidence_manifest:
        await reads.checkpoint()
        expected_exports["evidence/" + entry["key"]] = entry["size"], entry["sha256"]
    require(len(expected_exports) == len(manifest) + 3, "output/evidence path collision")
    require(set(expected_exports) == set(exports_by_name), "original receipt/export coverage differs")
    for name, item in exports_by_name.items():
        await reads.checkpoint()
        require((item["size"], item["sha256"]) == expected_exports[name],
                "original receipt/export coverage differs")
    # Evidence identity/schema/receipt validation MUST precede every bulk open.
    for item in doc["exports"]:
        await reads.checkpoint()
        if item["name"] not in evidence_names:
            await reads.read(item["name"], size=item["size"], sha256=item["sha256"],
                             retain=False)
    exports = []
    for item in doc["exports"]:
        await reads.checkpoint()
        exports.append(original.EvidenceExport(
            item["name"], export_root / item["name"], item["size"], item["sha256"]))
    result = OriginalEngineeringRunOutcome(
        attempt, execution.app_id, execution.sandbox_id, tuple(doc["phase_returncodes"]),
        doc["receipt_size"], doc["receipt_sha256"], evidence_manifest, tuple(exports))
    await reads.inventory(exports_by_name)
    # Every earlier file, including closed data readers and outcome. A checks
    # retained named pins/actual anchors, never fstat on a recycled descriptor.
    for reader in reads.verified:
        await reads.identity(reader)
    await reads.checkpoint()
    return result
