"""Pure isolated-owner vocabulary. No authority or process lifecycle lives here."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Protocol

NS = 1_000_000_000
MAX_NS = 2**63 - 1
CONTROL_LIMIT = 8192
REQUEST_LIMIT = 1024**2
MANIFEST_LIMIT = OUTCOME_LIMIT = 8 * 1024**2
FILE_LIMIT = 2 * 1024**3
TOTAL_LIMIT = 8 * 1024**3
ASSET_LIMIT = 4096
FIXED_SHUTDOWN_NS = 9_500_000_000
RPC_SOURCE_KEY = "train/qualification_file_rpc.py"
HEX = re.compile(r"[0-9a-f]{64}\Z")
APP = re.compile(r"ap-[A-Za-z0-9]{22}\Z")
SANDBOX = re.compile(r"sb-[A-Za-z0-9]{1,253}\Z")
KEY = re.compile(r"[A-Za-z0-9_./-]+\Z")


def require(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError(label)


def integer(value: Any, maximum: int = MAX_NS, minimum: int = 0) -> int:
    require(type(value) is int and minimum <= value <= maximum, "integer")
    return value


def digest(value: Any) -> str:
    require(type(value) is str and HEX.fullmatch(value) is not None, "digest")
    return value


def closed(value: Any, fields: set[str]) -> dict:
    require(type(value) is dict and set(value) == fields, "closed schema")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def byte_layer(raw: bytes, limit: int) -> bytes:
    require(type(raw) is bytes and 1 <= len(raw) <= limit, "byte limit")
    return raw


def _pairs(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        require(key not in result, "duplicate key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("nonfinite JSON")


def parse_canonical(raw: bytes, limit: int) -> Any:
    byte_layer(raw, limit)
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        require(canonical(value) == raw, "noncanonical JSON")
        return value
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError("invalid JSON") from error


def ceil_ns(value: Any) -> int:
    require(type(value) in (int, float) and 0 < value <= MAX_NS / NS
            and math.isfinite(value),
            "positive finite seconds")
    p, q = value.as_integer_ratio()
    return integer((p * NS + q - 1) // q, minimum=1)


@dataclass(frozen=True)
class StopTimingFacts:
    rpc_ns: int
    teardown_ns: int
    arm_ns: int

    def __post_init__(self) -> None:
        integer(self.rpc_ns, 30 * NS, 1)
        integer(self.teardown_ns, 30 * NS, 1)
        integer(self.arm_ns, 5 * NS, 1)
        require(self.rpc_ns <= self.teardown_ns, "RPC exceeds teardown")
        require(self.teardown_ns + FIXED_SHUTDOWN_NS <= 30 * NS,
                "shutdown infeasible")


@dataclass(frozen=True)
class ShutdownSchedule:
    end_ns: int
    origin_ns: int
    teardown_ns: int

    def __post_init__(self) -> None:
        integer(self.end_ns, minimum=1)
        integer(self.origin_ns)
        integer(self.teardown_ns, 20_500_000_000, 1)
        require(self.origin_ns + self.teardown_ns + FIXED_SHUTDOWN_NS
                <= self.end_ns, "origin exceeds latest")

    @property
    def cutoffs(self) -> tuple[int, ...]:
        o, t = self.origin_ns, self.teardown_ns
        return (o + NS, o + 3 * NS, o + 4 * NS, o + 4 * NS + t,
                o + 4_500_000_000 + t, o + 6_500_000_000 + t,
                o + 8_500_000_000 + t, o + FIXED_SHUTDOWN_NS + t)

    def advance(self, origin_ns: int) -> ShutdownSchedule:
        integer(origin_ns, self.origin_ns)
        return ShutdownSchedule(self.end_ns, origin_ns, self.teardown_ns)

    @classmethod
    def latest(cls, end_ns: int, timing: StopTimingFacts) -> ShutdownSchedule:
        return cls(end_ns, end_ns - timing.teardown_ns - FIXED_SHUTDOWN_NS,
                   timing.teardown_ns)


def remaining_ns(cutoff_ns: int, now_ns: int) -> int:
    integer(cutoff_ns)
    integer(now_ns)
    return max(0, cutoff_ns - now_ns)


def input_key(root: str, key: str) -> None:
    require(type(root) is str and root in {"source", "model", "data", "wheels",
                                         "request"}, "input root")
    maximum = 1024 if root == "wheels" else 256
    require(type(key) is str and 1 <= len(key) <= maximum
            and KEY.fullmatch(key) is not None, "input key")
    parts = key.split("/")
    require(len(parts) <= 64 and all(p not in {"", ".", ".."}
            and len(p) <= 255 for p in parts), "key components")
    if root == "request":
        require(key == "request.json", "derived request key")


@dataclass(frozen=True)
class ManifestEntry:
    root: str
    key: str
    size: int
    sha256: str
    snapshot_key: str

    def __post_init__(self) -> None:
        input_key(self.root, self.key)
        integer(self.size, REQUEST_LIMIT if self.root == "request" else FILE_LIMIT)
        digest(self.sha256)
        digest(self.snapshot_key)


def validate_entries(entries: tuple[ManifestEntry, ...]) -> None:
    require(type(entries) is tuple and 2 <= len(entries) <= ASSET_LIMIT + 1,
            "entry count")
    require(all(type(e) is ManifestEntry for e in entries), "entry type")
    keys = [(e.root, e.key) for e in entries]
    require(keys == sorted(keys) and len(set(keys)) == len(keys), "entry order/duplicate")
    require(len({e.snapshot_key for e in entries}) == len(entries),
            "snapshot duplicate")
    require(sum(e.root == "request" for e in entries) == 1, "request coverage")
    require(("source", RPC_SOURCE_KEY) in keys, "RPC source coverage")
    require(sum(e.size for e in entries) <= TOTAL_LIMIT, "aggregate size")


def encode_manifest(entries: tuple[ManifestEntry, ...]) -> bytes:
    validate_entries(entries)
    return byte_layer(canonical({"v": 1, "entries": [asdict(e) for e in entries]}),
                      MANIFEST_LIMIT)


def decode_manifest(raw: bytes) -> tuple[ManifestEntry, ...]:
    obj = closed(parse_canonical(raw, MANIFEST_LIMIT), {"v", "entries"})
    require(type(obj["v"]) is int and obj["v"] == 1, "version")
    require(type(obj["entries"]) is list and len(obj["entries"]) <= ASSET_LIMIT + 1,
            "entries")
    fields = {"root", "key", "size", "sha256", "snapshot_key"}
    result = tuple(ManifestEntry(**closed(e, fields)) for e in obj["entries"])
    validate_entries(result)
    return result


@dataclass(frozen=True)
class SourcePin:
    key: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        input_key("source", self.key)
        integer(self.size, FILE_LIMIT)
        digest(self.sha256)


@dataclass(frozen=True)
class PreparedInputs:
    request_size: int
    request_sha256: str
    manifest_size: int
    manifest_sha256: str
    launch_size: int
    launch_sha256: str
    entries: tuple[ManifestEntry, ...]

    def __post_init__(self) -> None:
        for prefix, limit in (("request", REQUEST_LIMIT), ("manifest", MANIFEST_LIMIT),
                              ("launch", REQUEST_LIMIT)):
            integer(getattr(self, prefix + "_size"), limit, 1)
            digest(getattr(self, prefix + "_sha256"))
        validate_entries(self.entries)


@dataclass(frozen=True)
class WorkerFDNumbers:
    control: int
    request: int
    launch: int
    manifest: int
    snapshot_dir: int
    outcome: int
    export_parent: int

    def __post_init__(self) -> None:
        values = tuple(asdict(self).values())
        for value in values:
            integer(value, 2**31 - 1, 3)
        require(len(set(values)) == len(values), "descriptor alias")


class ParentLocal:
    def __reduce_ex__(self, protocol: int) -> Any:
        raise TypeError("parent-local object")

    def __copy__(self) -> Any:
        raise TypeError("parent-local object")

    def __deepcopy__(self, memo: dict) -> Any:
        raise TypeError("parent-local object")


@dataclass(frozen=True)
class IsolatedOwnerSpec(ParentLocal):
    # Exact original types/custody are checked by A, without importing them here.
    interpreter: Any
    source_root: Path
    worker_source_pins: tuple[Any, ...]
    sdk_root: Path
    sdk_pins: tuple[Any, ...]
    resources: Any
    stop_binding: Any
    private_scratch: Path
    evidence_path: Path


@dataclass(frozen=True)
class LaunchDescriptor:
    v: int
    session: str
    source_root: str
    source_pins: tuple[SourcePin, ...]
    sdk_root: str
    sdk_pins: tuple[SourcePin, ...]
    interpreter_size: int
    interpreter_sha256: str
    request_binding: str
    request_size: int
    request_sha256: str
    manifest_size: int
    manifest_sha256: str
    setup_argv: tuple[str, ...]
    image_base_reference: str
    image_recipe_sha256: str
    gpu: str
    cpu: tuple[float | int, float | int]
    memory: tuple[int, int]
    export_name: str
    attempt_ns: int
    timing: StopTimingFacts

    def __post_init__(self) -> None:
        require(type(self.v) is int and self.v == 1, "launch version")
        for name in ("session", "interpreter_sha256", "request_binding",
                     "request_sha256", "manifest_sha256", "image_recipe_sha256"):
            digest(getattr(self, name))
        for name in ("source_root", "sdk_root"):
            value = getattr(self, name)
            require(type(value) is str and value.startswith("/") and "\0" not in value
                    and len(value) <= 4096, "launch root")
        for pins in (self.source_pins, self.sdk_pins):
            require(type(pins) is tuple and 1 <= len(pins) <= ASSET_LIMIT,
                    "source pins")
            require(all(type(p) is SourcePin for p in pins), "pin type")
            keys = [p.key for p in pins]
            require(keys == sorted(keys) and len(set(keys)) == len(keys), "pin order")
        integer(self.interpreter_size, FILE_LIMIT, 1)
        integer(self.request_size, REQUEST_LIMIT, 1)
        integer(self.manifest_size, MANIFEST_LIMIT, 1)
        integer(self.attempt_ns, 1800 * NS, 1)
        require(type(self.timing) is StopTimingFacts, "timing")
        require(self.attempt_ns > self.timing.teardown_ns + FIXED_SHUTDOWN_NS,
                "attempt infeasible")
        require(type(self.setup_argv) is tuple and 1 <= len(self.setup_argv) <= 64
                and all(type(a) is str and 1 <= len(a) <= 4096 and "\0" not in a
                        for a in self.setup_argv), "setup argv")
        require(type(self.export_name) is str and self.export_name not in {"", ".", ".."}
                and "/" not in self.export_name and "\0" not in self.export_name
                and len(self.export_name.encode("utf-8")) <= 255, "export basename")
        for value in (self.image_base_reference, self.gpu):
            require(type(value) is str and 1 <= len(value) <= 4096
                    and value.isascii() and "\0" not in value, "resource label")
        require(type(self.cpu) is tuple and len(self.cpu) == 2
                and all(type(x) in (int, float) and 0 < x <= 2**31 - 1
                        and math.isfinite(x) for x in self.cpu)
                and self.cpu[0] <= self.cpu[1], "CPU pair")
        require(type(self.memory) is tuple and len(self.memory) == 2, "memory pair")
        for x in self.memory:
            integer(x, 2**31 - 1, 1)
        require(self.memory[0] <= self.memory[1], "memory order")


def encode_launch(launch: LaunchDescriptor) -> bytes:
    require(type(launch) is LaunchDescriptor, "launch type")
    return byte_layer(canonical(asdict(launch)), REQUEST_LIMIT)


def decode_launch(raw: bytes) -> LaunchDescriptor:
    fields = set(LaunchDescriptor.__dataclass_fields__)
    obj = closed(parse_canonical(raw, REQUEST_LIMIT), fields)
    for name in ("source_pins", "sdk_pins"):
        require(type(obj[name]) is list, "pins array")
        obj[name] = tuple(SourcePin(**closed(p, {"key", "size", "sha256"}))
                          for p in obj[name])
    obj["timing"] = StopTimingFacts(**closed(obj["timing"],
                                            {"rpc_ns", "teardown_ns", "arm_ns"}))
    for name in ("setup_argv", "cpu", "memory"):
        require(type(obj[name]) is list, "launch array")
        obj[name] = tuple(obj[name])
    return LaunchDescriptor(**obj)


@dataclass(frozen=True)
class ChildObservation:
    role: str
    returncode: int
    actual_reap_observed: bool

    def __post_init__(self) -> None:
        require(type(self.role) is str and self.role in {"worker", "controller", "gate"},
                "child role")
        integer(self.returncode, 255, -255)
        require(self.actual_reap_observed is True, "actual reap")


@dataclass(frozen=True)
class JoinedExecution:
    children: tuple[ChildObservation, ...]
    app_id: str | None
    sandbox_id: str | None
    outcome_size: int | None
    outcome_sha256: str | None
    stop_command: str
    error_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_observations(self.children)
        validate_result_facts(self.app_id, self.sandbox_id, self.stop_command,
                              self.error_labels)
        require((self.outcome_size is None) == (self.outcome_sha256 is None),
                "outcome pair")
        if self.outcome_size is not None:
            integer(self.outcome_size, OUTCOME_LIMIT, 1)
            digest(self.outcome_sha256)


@dataclass(frozen=True)
class EngineeringRunOutcome:
    original_outcome: Any
    children: tuple[ChildObservation, ...]
    app_id: str | None
    sandbox_id: str | None
    local_containment: str
    stop_command: str
    remote_termination: str
    charged_end: str
    error_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_observations(self.children)
        require({c.role for c in self.children} == {"worker", "controller", "gate"},
                "normal outcome requires three joins")
        validate_result_facts(self.app_id, self.sandbox_id, self.stop_command,
                              self.error_labels)
        require(self.original_outcome is not None and self.app_id is not None
                and self.sandbox_id is not None, "complete original outcome")
        require(self.local_containment == "JOINED"
                and self.remote_termination == self.charged_end == "UNKNOWN",
                "outcome scope")


@dataclass(frozen=True)
class WorkerProgramResult:
    outcome_size: int
    outcome_sha256: str

    def __post_init__(self) -> None:
        integer(self.outcome_size, OUTCOME_LIMIT, 1)
        digest(self.outcome_sha256)


@dataclass(frozen=True)
class WorkerInputs:
    fds: WorkerFDNumbers
    request_payload: bytes
    entries: tuple[ManifestEntry, ...]

    def __post_init__(self) -> None:
        require(type(self.fds) is WorkerFDNumbers, "FD numbers")
        byte_layer(self.request_payload, REQUEST_LIMIT)
        validate_entries(self.entries)


def validate_observations(children: tuple[ChildObservation, ...]) -> None:
    require(type(children) is tuple and 1 <= len(children) <= 3
            and all(type(c) is ChildObservation for c in children), "child observations")
    roles = [c.role for c in children]
    require(len(set(roles)) == len(roles) and "worker" in roles, "admitted roles")


def validate_result_facts(app_id: str | None, sandbox_id: str | None,
                          stop_command: str, labels: tuple[str, ...]) -> None:
    for value, pattern in ((app_id, APP), (sandbox_id, SANDBOX)):
        require(value is None or (type(value) is str and pattern.fullmatch(value)
                                 is not None), "result ID")
    require(type(stop_command) is str and stop_command in {
        "EXITED", "KILLED", "NOT_EXECUTED"}, "stop observation")
    require(type(labels) is tuple and len(labels) <= 128 and all(
        type(s) is str and len(s) <= 64
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s) is not None
        for s in labels), "error labels")


class WorkerControl(Protocol):
    async def receive(self, *, allowed: frozenset[str], end_ns: int) -> dict: ...
    async def send(self, kind: str, body: dict, *, end_ns: int) -> None: ...


class DelegatedWorkerHost(Protocol):
    @property
    def resource(self) -> Any: ...
    @property
    def app_id(self) -> str: ...
    @property
    def sandbox_id(self) -> str: ...
    @property
    def end_ns(self) -> int: ...
    def require_setup_argv(self, setup_argv: tuple[str, ...]) -> None: ...


class PreparationWriter(Protocol):
    def snapshot_member(self, *, root: str, key: str, source_path: Path,
                        size: int, sha256: str) -> ManifestEntry: ...
    def write_request(self, payload: bytes) -> ManifestEntry: ...
    def seal(self, entries: tuple[ManifestEntry, ...],
             launch: Any) -> PreparedInputs: ...


BODY_FIELDS = {
    "READY": {"request_sha256", "manifest_sha256", "launch_sha256"},
    "OPEN": {"permit", "end_ns"}, "APP_RETAINED": {"permit", "app_id"},
    "CREATE": {"permit", "end_ns"},
    "SANDBOX_RETAINED": {"permit", "sandbox_id"}, "STOP": set(),
    "OUTCOME": {"size", "sha256"}, "FAILED": {"stage", "code"},
    "ARM": {"permit", "end_ns", "origin_ns", "teardown_ns", "app_id"},
    "ARMED": {"permit"}, "EARLY_STOP": {"origin_ns"}, "FINISH": set(),
}


def validate_message(value: Any, *, session: str, seq: int,
                     allowed: frozenset[str]) -> dict:
    digest(session)
    integer(seq, minimum=1)
    obj = closed(value, {"v", "session", "seq", "kind", "body"})
    require(type(obj["v"]) is int and obj["v"] == 1, "version")
    digest(obj["session"])
    require(obj["session"] == session, "session")
    integer(obj["seq"], minimum=1)
    require(obj["seq"] == seq, "sequence")
    kind = obj["kind"]
    require(type(kind) is str and kind in allowed and kind in BODY_FIELDS, "kind")
    body = closed(obj["body"], BODY_FIELDS[kind])
    for key, item in body.items():
        if key.endswith("sha256") or key == "permit":
            digest(item)
        elif key in {"end_ns", "origin_ns", "teardown_ns"}:
            integer(item, minimum=0 if key == "origin_ns" else 1)
        elif key == "size":
            integer(item, OUTCOME_LIMIT, 1)
        elif key in {"app_id", "sandbox_id"}:
            pattern = APP if key == "app_id" else SANDBOX
            require(type(item) is str and pattern.fullmatch(item) is not None, "ID")
        else:
            require(type(item) is str and len(item) <= 64
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) is not None,
                    "failure label")
    if kind == "ARM":
        require(body["teardown_ns"] <= 20_500_000_000, "ARM teardown")
        ShutdownSchedule(body["end_ns"], body["origin_ns"], body["teardown_ns"])
    return obj


def encode_message(value: dict, *, session: str, seq: int,
                   allowed: frozenset[str]) -> bytes:
    validate_message(value, session=session, seq=seq, allowed=allowed)
    payload = byte_layer(canonical(value), CONTROL_LIMIT)
    return len(payload).to_bytes(4, "big") + payload


def decode_message(frame: bytes, *, session: str, seq: int,
                   allowed: frozenset[str]) -> dict:
    require(type(frame) is bytes and len(frame) >= 4, "frame prefix")
    length = int.from_bytes(frame[:4], "big")
    require(1 <= length <= CONTROL_LIMIT and len(frame) == length + 4, "frame size")
    return validate_message(parse_canonical(frame[4:], CONTROL_LIMIT),
                            session=session, seq=seq, allowed=allowed)
