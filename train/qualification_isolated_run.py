"""V238 C parent path, new source UNRUN, pending amended A/C review.

No SDK import, process lifecycle, authorization reconstruction or old-runner
fallback. The public entry retains its pre-admission integration refusal.
V235 accepted the earlier 51 mocked C units, not real lifecycle evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import hashlib
import math
from pathlib import Path
import time
from typing import Any

from train.qualification_isolated_contract import (
    ASSET_LIMIT, FILE_LIMIT, MANIFEST_LIMIT, NS, REQUEST_LIMIT, RPC_SOURCE_KEY,
    TOTAL_LIMIT, EngineeringRunOutcome, IsolatedOwnerSpec, JoinedExecution,
    LaunchDescriptor, ManifestEntry, ParentLocal, PreparedInputs,
    byte_layer, digest, encode_launch, encode_manifest,
    input_key, integer, require,
)


class FrozenReadCustodyUnavailable(RuntimeError):
    """Amended owner/validator integration has not passed parent review."""


class IsolatedReadCustodyError(RuntimeError):
    """A worker-local or owner-leased close has unresolved custody."""


class IsolatedCustodyError(RuntimeError):
    """Retain actual owner and both failures when joined release is unknown."""

    def __init__(self, owner: Any, primary: BaseException | None,
                 cleanup: BaseException):
        super().__init__("isolated custody unresolved; resources/latch retained")
        self.owner, self.primary, self.cleanup = owner, primary, cleanup


_RETAINED_FAILURES: list[IsolatedCustodyError] = []


@dataclass(frozen=True)
class OriginalTransport(ParentLocal):
    """Parent-local original serializer result, never an authority object."""

    payload: bytes
    assets: tuple[Any, ...]


def _load_native() -> Any:
    from train import native_qualification
    return native_qualification


def _load_owner_api() -> Any:
    # Parent integrates A's owner module. No alternate host.
    from train import qualification_isolated_owner
    return qualification_isolated_owner


def _require_parent_read_custody() -> None:
    raise FrozenReadCustodyUnavailable(
        "V237 amended owner-held validation requires parent A/C integration "
        "review; public entry remains blocked before admission")


@dataclass(frozen=True)
class _ValidatedParentData(ParentLocal):
    """Private data links only. A alone checks and seals this exact C type."""

    owner: Any
    request: Any
    prepared: PreparedInputs
    export_root: Path
    lease: Any
    worker_execution: JoinedExecution
    original: Any


@dataclass(frozen=True)
class _ParentValidator(ParentLocal):
    owner: Any
    request: Any
    prepared: PreparedInputs
    export_root: Path

    def _assert(self, lease: Any) -> None:
        self.owner._assert_parent_read_lease(
            lease, request=self.request, prepared=self.prepared,
            export_root=self.export_root)

    async def validate(self, lease: Any) -> _ValidatedParentData:
        # Never use a lease/DTO as standalone authority, even for its properties.
        self._assert(lease)
        execution = lease.worker_execution
        require(type(execution) is JoinedExecution
                and len(execution.children) == 1
                and execution.children[0].role == "worker"
                and execution.children[0].actual_reap_observed is True
                and execution.children[0].returncode == 0
                and not execution.error_labels, "clean actual worker reap required")
        end_ns = integer(lease.end_ns, minimum=1)
        read_ns = integer(lease.read_deadline_ns, end_ns, 1)
        require(time.monotonic_ns() < read_ns, "fixed validation deadline expired")
        from train.qualification_isolated_program import _validate_outcome_lease
        # One absolute timeout, in this task. No task/thread or renewed budget.
        async with asyncio.timeout_at(math.nextafter(read_ns / NS, -math.inf)):
            original = await _validate_outcome_lease(
                self.request, prepared=self.prepared, execution=execution,
                export_root=self.export_root, lease=lease, end_ns=end_ns,
                read_deadline_ns=read_ns)
            self._assert(lease)  # After final all-files identity sweep.
            await lease.checkpoint()
            require(lease.worker_execution is execution
                    and lease.end_ns == end_ns and lease.read_deadline_ns == read_ns
                    and time.monotonic_ns() < read_ns, "validation lease changed/expired")
            self._assert(lease)  # Last check before returning exact links.
            return _ValidatedParentData(
                self.owner, self.request, self.prepared, self.export_root,
                lease, execution, original)


def _make_parent_validator(owner: Any, request: Any, prepared: PreparedInputs,
                           export_root: Path) -> _ParentValidator:
    require(type(prepared) is PreparedInputs, "prepared input type")
    root = _absolute_metadata(export_root)
    require(root.name not in {"", ".", ".."}
            and len(root.name.encode("utf-8")) <= 255, "export basename")
    return _ParentValidator(owner, request, prepared, export_root)


def serialize_original_request(request: Any) -> OriginalTransport:
    """Call ONLY after A consumed admission; preserve all original byte checks."""
    payload, assets = _load_native()._prepare_worker_transport(request)
    byte_layer(payload, REQUEST_LIMIT)
    require(type(assets) is tuple, "original serializer asset tuple")
    return OriginalTransport(payload, assets)


def _absolute_metadata(path: Any) -> Path:
    require(isinstance(path, Path) and path.is_absolute()
            and ".." not in path.parts and "\\" not in str(path)
            and "\0" not in str(path), "absolute nontraversing Path")
    return path


def _upload_metadata(uploads: Any) -> tuple[Any, ...]:
    require(type(uploads) in (tuple, list)
            and 1 <= len(uploads) <= ASSET_LIMIT, "approved upload count")
    result = tuple(uploads)
    seen: set[tuple[str, str]] = set()
    total = 0
    for item in result:
        require(all(hasattr(item, name) for name in
                    ("root", "key", "size", "sha256", "path")), "upload fields")
        require(type(item.root) is str
                and item.root in {"source", "model", "data", "wheels"},
                "only four approved roots; request is derived")
        input_key(item.root, item.key)
        integer(item.size, FILE_LIMIT)
        digest(item.sha256)
        _absolute_metadata(item.path)
        pair = item.root, item.key
        require(pair not in seen, "duplicate approved member")
        seen.add(pair)
        total += item.size
    require(("source", RPC_SOURCE_KEY) in seen, "exact RPC source member")
    rpc = next(item for item in result
               if (item.root, item.key) == ("source", RPC_SOURCE_KEY))
    integer(rpc.size, REQUEST_LIMIT, 1)
    require(total <= TOTAL_LIMIT, "approved aggregate size")
    return result


def _metadata(request: Any, *, authorization: Any, owner_spec: Any,
              uploads: Any, setup_argv: Any, export_root: Any) -> None:
    require(request is not None and authorization is not None,
            "request and original authorization required")
    require(type(owner_spec) is IsolatedOwnerSpec, "original owner spec required")
    _upload_metadata(uploads)
    require(type(setup_argv) is tuple and 1 <= len(setup_argv) <= 64
            and all(type(arg) is str and 1 <= len(arg) <= 4096
                    and "\0" not in arg for arg in setup_argv), "exact setup argv")
    root = _absolute_metadata(export_root)
    require(root.name not in {"", ".", ".."}
            and len(root.name.encode("utf-8")) <= 255, "export basename")


def _original_coverage(transport: OriginalTransport,
                       uploads: tuple[Any, ...]) -> None:
    expected: dict[tuple[str, str], tuple[int, str, Path]] = {}
    for asset in transport.assets:
        input_key(asset.kind, asset.key)
        require(asset.kind in {"source", "model", "data"}, "original asset root")
        integer(asset.size, FILE_LIMIT)
        digest(asset.sha256)
        _absolute_metadata(asset.host_path)
        key = asset.kind, asset.key
        require(key not in expected, "duplicate original asset")
        expected[key] = asset.size, asset.sha256, asset.host_path
    actual = {(item.root, item.key): (item.size, item.sha256, item.path)
              for item in uploads if item.root in {"source", "model", "data"}}
    require(actual == expected, "original asset/path/hash coverage differs")


def prepare_isolated_inputs(
    request: Any, *, owner: Any, uploads: Any, setup_argv: tuple[str, ...],
    export_root: Path, launch: Any,
) -> PreparedInputs:
    """Owner writer alone opens/copies paths and owns all prepared resources.

    A preflight/admission binds the original four-root tuples and exact argv.
    Every supplied row, including wheels, goes through that owner's writer.
    Caller never supplies or approves the derived request root.
    """
    items = _upload_metadata(uploads)
    transport = serialize_original_request(request)
    _original_coverage(transport, items)
    require(sum(item.size for item in items) + len(transport.payload)
            <= TOTAL_LIMIT, "aggregate including derived request")
    writer = owner.preparation_writer()
    entries = []
    for item in items:
        entry = writer.snapshot_member(
            root=item.root, key=item.key, source_path=item.path,
            size=item.size, sha256=item.sha256)
        require(type(entry) is ManifestEntry
                and (entry.root, entry.key, entry.size, entry.sha256)
                == (item.root, item.key, item.size, item.sha256),
                "owner snapshot metadata differs")
        entries.append(entry)
    request_entry = writer.write_request(transport.payload)
    request_hash = hashlib.sha256(transport.payload).hexdigest()
    require(type(request_entry) is ManifestEntry
            and (request_entry.root, request_entry.key, request_entry.size,
                 request_entry.sha256)
            == ("request", "request.json", len(transport.payload), request_hash),
            "owner derived request differs")
    entries.append(request_entry)
    ordered = tuple(sorted(entries, key=lambda entry: (entry.root, entry.key)))
    manifest = encode_manifest(ordered)
    byte_layer(manifest, MANIFEST_LIMIT)
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    descriptor = launch.descriptor_for(
        request_size=len(transport.payload), request_sha256=request_hash,
        manifest_size=len(manifest), manifest_sha256=manifest_hash)
    require(type(descriptor) is LaunchDescriptor, "sealed launch descriptor type")
    require(descriptor.setup_argv == setup_argv, "approved setup argv differs")
    require(descriptor.export_name == _absolute_metadata(export_root).name,
            "approved export basename differs")
    prepared = writer.seal(ordered, descriptor)
    launch_payload = encode_launch(descriptor)
    require(type(prepared) is PreparedInputs and prepared.entries == ordered
            and (prepared.request_size, prepared.request_sha256,
                 prepared.manifest_size, prepared.manifest_sha256)
            == (len(transport.payload), request_hash, len(manifest), manifest_hash),
            "owner sealed input facts differ")
    require((prepared.launch_size, prepared.launch_sha256)
            == (len(launch_payload), hashlib.sha256(launch_payload).hexdigest()),
            "owner sealed launch facts differ")
    # The owner checks actual writer/launch/resource identity, never DTO equality.
    return prepared


def _release(owner: Any, primary: BaseException | None = None) -> None:
    if isinstance(primary, IsolatedReadCustodyError):
        failure = IsolatedCustodyError(
            owner, primary, RuntimeError("C read custody unknown; owner release forbidden"))
        _RETAINED_FAILURES.append(failure)
        raise failure from primary
    try:
        owner.release_joined()
    except BaseException as cleanup:
        failure = IsolatedCustodyError(owner, primary, cleanup)
        _RETAINED_FAILURES.append(failure)
        raise failure from (primary if primary is not None else cleanup)


def validate_joined_outcome(
    request: Any, *, owner: Any, prepared: PreparedInputs, execution: JoinedExecution,
    export_root: Path,
) -> EngineeringRunOutcome:
    require(type(prepared) is PreparedInputs, "prepared input type")
    require(type(execution) is JoinedExecution, "joined execution type")
    require({child.role for child in execution.children}
            == {"worker", "controller", "gate"}, "all three actual joins required")
    require(all(child.actual_reap_observed is True for child in execution.children),
            "actual reap required")
    original = owner.take_validated_original(
        request=request, prepared=prepared, execution=execution, export_root=export_root)
    # A verifies identical final execution, actual joins, all observed closes
    # and one-use seal. Publication performs no filesystem/hash/lease operation.
    return EngineeringRunOutcome(
        original, execution.children, execution.app_id, execution.sandbox_id,
        "JOINED", execution.stop_command, "UNKNOWN", "UNKNOWN", execution.error_labels)


async def run_engineering_isolated_once(
    request: Any, *, authorization: Any, owner_spec: IsolatedOwnerSpec,
    uploads: Any, setup_argv: tuple[str, ...], export_root: Path,
) -> EngineeringRunOutcome:
    _metadata(request, authorization=authorization, owner_spec=owner_spec,
              uploads=uploads, setup_argv=setup_argv, export_root=export_root)
    api = _load_owner_api()
    preflight = api.preflight_isolated(
        request, authorization=authorization, owner_spec=owner_spec,
        uploads=uploads, setup_argv=setup_argv, export_root=export_root)
    # SOLE REMOVAL POINT, parent only after amended A/C integration review.
    # This refusal must not consume an approval or launch work.
    _require_parent_read_custody()
    owner = api.admit_isolated_owner(preflight)
    try:
        launch = api.pin_worker_launch(owner, owner_spec=owner_spec)
        prepared = prepare_isolated_inputs(
            request, owner=owner, uploads=uploads, setup_argv=setup_argv,
            export_root=export_root, launch=launch)
        owner.seal_inputs(prepared, launch)
        owner.register_parent_validation(
            request=request, prepared=prepared, export_root=export_root)
        # A owns cancellation containment and joins. C never cancels a detached
        # task, signals a protocol PID, retries, or starts in-process SDK work.
        execution = await owner.run_once()
        result = validate_joined_outcome(
            request, owner=owner, prepared=prepared, execution=execution,
            export_root=export_root)
    except BaseException as primary:
        _release(owner, primary)
        raise
    _release(owner)
    return result
