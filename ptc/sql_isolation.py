"""Closed SQL isolation contracts and the owned local Docker boundary.

These hashes bind NEW production data, not spike policy bytes. Source validation
is local and data-only; it does not qualify a runtime/closure for execution.
PROGRAM imports do not import bench, capture, gold, or the provider harness.
The PROGRAM worker uses these stdlib wire codecs without a scorer import.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import pwd
import re
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Generic, Literal, TypeVar, Union

if TYPE_CHECKING:
    from bench.score import ExResult
    from bench.task import SqlTask
    from train.sql_episodes import InstrumentSettings

Role = Literal["program", "scorer"]
WireKind = Literal["bootstrap", "request", "result", "exit_grant"]
AbortReason = Literal["admission", "binding", "start", "deadline", "memory",
                      "output", "protocol", "cleanup", "transport"]
Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
JsonObject = dict[str, Json]
Environment = tuple[tuple[str, str], ...]

IMAGE_MANIFEST_SHA256 = "c3729439afc4ec3f3e159e0c86aeabfadac8030ef46838a0256383d0511c5f5e"
IMAGE_CONFIG_SHA256 = "81c0aac584c3e136c75a8da272f5d08e45e1f2ae00701fbce768f490dd22164b"
MAX_PROGRAM_BYTES = 65536
MAX_ARTIFACT_BYTES = 8388608
MAX_EXTRACTION_WORK_BYTES = 67108864
MAX_MESSAGES_TOOLS_BYTES = 131072
READY = b"PILOT_READY!\n"
WIRE_SCHEMA_VERSION = 2
# Public environment from the pinned official image, not host environment.
APPROVED_ENVIRONMENT: Environment = (
    ("GPG_KEY", "7169605F62C751356D054A26A821E680E5FA6305"),  # Public CPython signing-key fingerprint. gitleaks:allow
    ("HOME", "/nonexistent"),
    ("HOSTNAME", "co-train-isolation"),
    ("LANG", "C.UTF-8"),
    ("PATH", "/usr/local/bin:/usr/bin:/bin"),
    ("PYTHON_SHA256", "c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a"),
    ("PYTHON_VERSION", "3.12.15"),
)

_READONLY = ("/proc/bus", "/proc/fs", "/proc/irq", "/proc/sys",
             "/proc/sysrq-trigger", "/dev/mqueue")
_MASKED = ("/proc/acpi", "/proc/asound", "/proc/interrupts", "/proc/kcore",
           "/proc/keys", "/proc/latency_stats", "/proc/sched_debug", "/proc/scsi",
           "/proc/timer_list", "/proc/timer_stats", "/sys/devices/virtual/powercap",
           "/sys/firmware")
_SYSCALLS = tuple("""access brk capget capset chdir clock_getres clock_gettime
clock_nanosleep close close_range dup dup3 epoll_create1 epoll_ctl epoll_pwait
execve exit exit_group faccessat faccessat2 fchdir fchmod fchmodat fchown fchownat
fcntl fdatasync flock fstat fstatfs fsync ftruncate futex getcwd getdents64 getegid
geteuid getgid getpid getppid getrandom getresgid getresuid getrlimit gettid
gettimeofday getuid ioctl lseek madvise membarrier mkdirat mmap mprotect mremap
munmap nanosleep newfstatat openat openat2 pipe2 ppoll prctl pread64 prlimit64
pselect6 pwrite64 read readlinkat readv renameat renameat2 restart_syscall rseq
rt_sigaction rt_sigprocmask rt_sigreturn sched_getaffinity sched_yield
set_robust_list set_tid_address setgid setgroups setresgid setresuid setuid
sigaltstack statfs statx sysinfo times umask uname unlinkat write writev""".split())
_ABORT_REASONS = ("admission", "binding", "start", "deadline", "memory", "output",
                  "protocol", "cleanup", "transport")


def _integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 9223372036854775807:
        raise ValueError("expected bounded integer, not bool")
    return value


def _text(value: object, *, nonempty: bool = False, maximum: int = MAX_ARTIFACT_BYTES) -> str:
    if type(value) is not str:
        raise TypeError("expected string")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError as exc:
        raise ValueError("invalid UTF-8 string") from exc
    if size > maximum or nonempty and not size:
        raise ValueError("string size outside bound")
    return value


def _digest(value: object) -> str:
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA256")
    return value


def _choice(value: object, choices: tuple[str, ...]) -> str:
    if type(value) is not str or value not in choices:
        raise ValueError("unsupported enum value")
    return value


def _version(value: object) -> None:
    if type(value) is not int or value != 1:
        raise ValueError("unsupported schema_version")


def _closed(value: object, names: tuple[str, ...]) -> JsonObject:
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("unknown/missing closed fields")
    return value


def _array(value: object) -> list:
    if type(value) is not list:
        raise TypeError("expected JSON array")
    return value


def _path(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute() or "\x00" in str(value):
        raise ValueError("explicit absolute local path required")
    return value


def _pins(value: object) -> None:
    if type(value) is not tuple or not value or any(type(p) is not SourcePin for p in value):
        raise TypeError("nonempty tuple of SourcePin required")
    if len({p.path for p in value}) != len(value):
        raise ValueError("duplicate source paths")
    for pin in value:
        pin.__post_init__()


def _environment(value: object) -> None:
    if type(value) is not tuple or any(type(p) is not tuple or len(p) != 2 or
            any(type(x) is not str for x in p) for p in value) or value != APPROVED_ENVIRONMENT:
        raise ValueError("exact approved initial ENV7 required")


@dataclass(frozen=True, slots=True)
class SourcePin:
    path: str
    sha256: str

    def __post_init__(self):
        _text(self.path, nonempty=True)
        if "\\" in self.path or ":" in self.path or "\x00" in self.path or self.path.startswith("/") or any(
                p in ("", ".", "..") for p in self.path.split("/")):
            raise ValueError("source path must be normalized bundle-relative")
        if PurePosixPath(self.path).as_posix() != self.path:
            raise ValueError("noncanonical source path")
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class Limits:
    memory_bytes: int
    swap_bytes: int
    pids: int
    tmp_bytes: int
    shm_bytes: int
    nofile: int
    deadline_ms: int
    stdout_bytes: int
    stderr_bytes: int
    input_bytes: int

    def __post_init__(self):
        for f in fields(self):
            _integer(getattr(self, f.name), minimum=0 if f.name == "swap_bytes" else 1)


def limits_for(role: Role) -> Limits:
    _choice(role, ("program", "scorer"))
    return Limits(268435456, 0, 1, 16777216, 1048576, 64,
                  10000 if role == "program" else 30000,
                  1048576 if role == "program" else 65536, 65536, 8388608)


@dataclass(frozen=True, slots=True)
class MountSlot:
    name: Literal["bundle", "database"]
    target: str
    read_only: bool = True
    propagation: str = "rprivate"
    mount_type: str = "bind"

    def __post_init__(self):
        _choice(self.name, ("bundle", "database"))
        _text(self.target); _text(self.propagation); _text(self.mount_type)
        if self.target != {"bundle": "/bundle", "database": "/db.sqlite"}[self.name] or self.read_only is not True or self.propagation != "rprivate" or self.mount_type != "bind":
            raise ValueError("nonapproved mount slot")


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    schema_version: int = 1
    uid: int = 65534
    gid: int = 65534
    hostname: str = "co-train-isolation"
    root_readonly: bool = True
    privileged: bool = False
    cap_drop: tuple[str, ...] = ("ALL",)
    no_new_privileges: bool = True
    pid_mode: str = ""
    ipc_mode: str = "private"
    cgroupns_mode: str = "private"
    uts_mode: str = ""
    network_mode: str = "none"
    seccomp_architectures: tuple[str, ...] = ("SCMP_ARCH_AARCH64",)
    seccomp_default_action: str = "SCMP_ACT_ERRNO"
    seccomp_errno: int = 1
    seccomp_syscalls: tuple[str, ...] = _SYSCALLS
    readonly_paths: tuple[str, ...] = _READONLY
    masked_paths: tuple[str, ...] = _MASKED
    mount_slots: tuple[MountSlot, ...] = (MountSlot("bundle", "/bundle"), MountSlot("database", "/db.sqlite"))
    environment_rule: str = "exact_initial_image_env7_v1"
    log_driver: str = "none"
    core_bytes: int = 0
    tmp_options: tuple[str, ...] = ("noexec", "nosuid", "nodev")
    tmp_mode: int = 1023
    memory_swappiness: int = 0

    def __post_init__(self):
        # The production profile has no permissive/unknown policy extension slot.
        for f in fields(self):
            value = getattr(self, f.name)
            if type(value) is not type(f.default) or value != f.default:
                raise ValueError("nonapproved security field: " + f.name)
            if type(value) is tuple and any(type(a) is not type(b) for a, b in zip(value, f.default)):
                raise TypeError("nonconcrete security tuple member")
        for slot in self.mount_slots:
            if type(slot) is not MountSlot:
                raise TypeError("typed mount slot required")
            slot.__post_init__()


@dataclass(frozen=True, slots=True)
class RoleBinding:
    role: Role
    image_manifest_sha256: str
    image_config_sha256: str
    platform: str
    sources: tuple[SourcePin, ...]
    security_profile_sha256: str
    limits: Limits

    def __post_init__(self):
        _choice(self.role, ("program", "scorer"))
        _digest(self.image_manifest_sha256); _digest(self.image_config_sha256)
        _choice(self.platform, ("linux/arm64",))
        if self.image_manifest_sha256 != IMAGE_MANIFEST_SHA256 or self.image_config_sha256 != IMAGE_CONFIG_SHA256 or self.platform != "linux/arm64":
            raise ValueError("unapproved image/config/platform")
        _pins(self.sources); _digest(self.security_profile_sha256)
        if type(self.limits) is not Limits or self.limits != limits_for(self.role):
            raise ValueError("nonapproved role limits")
        self.limits.__post_init__()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionBinding:
    schema_version: int = 1
    program: RoleBinding
    scorer: RoleBinding
    controller_sources: tuple[SourcePin, ...]
    policy_sha256: str
    instrument_runtime_scope: Literal["host"] = "host"

    def __post_init__(self):
        _version(self.schema_version)
        for role in ("program", "scorer"):
            record = getattr(self, role)
            if type(record) is not RoleBinding or record.role != role:
                raise ValueError("wrong role binding")
            record.__post_init__()
        _pins(self.controller_sources); _digest(self.policy_sha256)
        _choice(self.instrument_runtime_scope, ("host",))


@dataclass(frozen=True, slots=True)
class AbortInfo:
    stage: Role
    reason: AbortReason

    def __post_init__(self):
        _choice(self.stage, ("program", "scorer")); _choice(self.reason, _ABORT_REASONS)


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    role: Role
    request_sha256: str
    python_version: str
    sqlite_version: str
    bootstrap_sha256: str
    journal_sha256: str

    def __post_init__(self):
        _choice(self.role, ("program", "scorer"))
        for name in ("request_sha256", "bootstrap_sha256", "journal_sha256"):
            _digest(getattr(self, name))
        _text(self.python_version, nonempty=True); _text(self.sqlite_version, nonempty=True)


def _outcome(completed: object, abort: AbortInfo | None, receipt: RuntimeReceipt | None, role: Role) -> None:
    if (completed is None) == (abort is None):
        raise ValueError("exactly one completed/abort branch required")
    if abort is not None and (type(abort) is not AbortInfo or abort.stage != role):
        raise ValueError("abort role mismatch")
    if receipt is not None and (type(receipt) is not RuntimeReceipt or receipt.role != role):
        raise ValueError("receipt role mismatch")
    if completed is not None and receipt is None:
        raise ValueError("completed execution requires actual runtime receipt")
    if abort is not None:
        abort.__post_init__()
    if receipt is not None:
        receipt.__post_init__()


def _ex_result(value: object) -> None:
    from bench.score import ExResult
    if type(value) is not ExResult:
        raise TypeError("actual native ExResult required")
    statuses = ("match", "mismatch", "pred_error", "pred_timeout", "pred_truncated",
                "pred_empty", "gold_error", "gold_timeout", "gold_truncated", "db_missing")
    _choice(value.status, statuses)
    if type(value.score) is not float or not math.isfinite(value.score) or value.score not in (0.0, 1.0):
        raise ValueError("invalid EX score")
    if type(value.valid) is not bool or value.valid != (value.status not in statuses[6:]) or value.score != float(value.status == "match"):
        raise ValueError("inconsistent EX outcome")
    _text(value.detail); _integer(value.n_pred_rows); _integer(value.n_gold_rows)


@dataclass(frozen=True, slots=True)
class ProgramOutcome:
    """Completed native PROGRAM response (accepted or rejected), or infra abort."""
    observation: str | None
    abort: AbortInfo | None
    receipt: RuntimeReceipt | None
    rejected: bool = field(default=False, kw_only=True)

    def __post_init__(self):
        if type(self.rejected) is not bool:
            raise TypeError("rejected must be bool")
        _outcome(self.observation, self.abort, self.receipt, "program")
        if self.abort is not None and self.rejected:
            raise ValueError("infrastructure abort cannot be native rejection")
        if self.observation is not None:
            _text(self.observation, maximum=1048576)


@dataclass(frozen=True, slots=True)
class ScoreOutcome:
    result: ExResult | None
    abort: AbortInfo | None
    receipt: RuntimeReceipt | None

    def __post_init__(self):
        _outcome(self.result, self.abort, self.receipt, "scorer")
        if self.result is not None:
            _ex_result(self.result)


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryObserver:
    kind: str = "colima_default_meminfo_v1"
    binary: Path
    binary_sha256: str
    profile: str = "default"
    timeout_ms: int = 2000

    def __post_init__(self):
        _choice(self.kind, ("colima_default_meminfo_v1",)); _path(self.binary)
        _digest(self.binary_sha256); _choice(self.profile, ("default",))
        if type(self.timeout_ms) is not int or self.timeout_ms != 2000:
            raise ValueError("observer timeout must be 2000ms")


def shared_state_dir_for(daemon_socket: Path) -> Path:
    socket = _path(daemon_socket).resolve()
    uid = os.getuid()
    return Path(pwd.getpwuid(uid).pw_dir) / "scratch/co-train-isolation-shared" / (
        str(uid) + "-" + hashlib.sha256(str(socket).encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionProfile:
    schema_version: int = 1
    daemon_socket: Path
    shared_state_dir: Path
    observer: MemoryObserver
    admission_bytes: int = 469762048
    reserve_bytes: int = 201326592
    max_sample_age_ms: int = 4000
    api_timeout_ms: int = 3000
    environment: Environment
    policy: SecurityPolicy
    binding: ExecutionBinding

    def __post_init__(self):
        _version(self.schema_version); _path(self.daemon_socket); _path(self.shared_state_dir)
        if self.daemon_socket != self.daemon_socket.resolve() or self.shared_state_dir != shared_state_dir_for(self.daemon_socket):
            raise ValueError("canonical per-daemon shared state directory required")
        if type(self.observer) is not MemoryObserver or type(self.policy) is not SecurityPolicy or type(self.binding) is not ExecutionBinding:
            raise TypeError("concrete profile records required")
        self.observer.__post_init__(); self.policy.__post_init__(); self.binding.__post_init__()
        for name, expected in (("admission_bytes", 469762048), ("reserve_bytes", 201326592),
                               ("max_sample_age_ms", 4000), ("api_timeout_ms", 3000)):
            if type(getattr(self, name)) is not int or getattr(self, name) != expected:
                raise ValueError("nonapproved admission bound")
        _environment(self.environment)
        security = security_profile_sha256(self.policy, self.environment)
        if self.binding.program.security_profile_sha256 != security or self.binding.scorer.security_profile_sha256 != security or self.binding.policy_sha256 != execution_policy_sha256(self):
            raise ValueError("profile/binding fingerprint mismatch")


def _plain(value: object) -> Json:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if type(value) is tuple:
        return [_plain(x) for x in value]
    if type(value) is list:
        return [_plain(x) for x in value]
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise TypeError("JSON keys must be strings")
        return {k: _plain(v) for k, v in value.items()}
    if value is None or type(value) in (bool, int, str):
        if type(value) is str:
            _text(value)
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("not finite JSON data")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")


def bounded_bytes(value: bytes, *, maximum: int) -> bytes:
    _integer(maximum, minimum=1)
    if type(value) is not bytes:
        raise TypeError("bytes required")
    if len(value) > maximum:
        raise ValueError("byte cap exceeded, no truncated success")
    return value


def _json_line(data: bytes, *, maximum: int) -> JsonObject:
    bounded_bytes(data, maximum=maximum)
    if not data.endswith(b"\n") or data.endswith(b"\r\n") or data.count(b"\n") != 1:
        raise ValueError("one canonical JSON+LF frame required")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict or canonical_json_bytes(value) + b"\n" != data:
            raise ValueError("noncanonical JSON envelope")
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid bounded UTF-8 JSON") from exc
    return value


def _encode(record: object, cls: type) -> JsonObject:
    if type(record) is not cls:
        raise TypeError("wrong concrete record")
    record.__post_init__()
    return _plain(record)


def _fields_for(cls: type) -> tuple[str, ...]:
    return tuple(f.name for f in fields(cls))


def _flat(value: JsonObject, cls: type):
    return cls(**_closed(value, _fields_for(cls)))


def execution_binding_to_dict(binding: ExecutionBinding) -> JsonObject:
    return _encode(binding, ExecutionBinding)


def execution_binding_from_dict(value: JsonObject) -> ExecutionBinding:
    d = _closed(value, _fields_for(ExecutionBinding))
    return ExecutionBinding(schema_version=d["schema_version"],
        program=_role_from_dict(d["program"]), scorer=_role_from_dict(d["scorer"]),
        controller_sources=_pins_from_json(d["controller_sources"]),
        policy_sha256=d["policy_sha256"], instrument_runtime_scope=d["instrument_runtime_scope"])


def _pins_from_json(value: Json) -> tuple[SourcePin, ...]:
    return tuple(_flat(x, SourcePin) for x in _array(value))


def _role_from_dict(value: JsonObject) -> RoleBinding:
    d = _closed(value, _fields_for(RoleBinding))
    return RoleBinding(d["role"], d["image_manifest_sha256"], d["image_config_sha256"],
        d["platform"], _pins_from_json(d["sources"]), d["security_profile_sha256"], _flat(d["limits"], Limits))


def _policy_from_dict(value: JsonObject) -> SecurityPolicy:
    d = dict(_closed(value, _fields_for(SecurityPolicy)))
    for name in ("cap_drop", "seccomp_architectures", "seccomp_syscalls", "readonly_paths", "masked_paths", "tmp_options"):
        d[name] = tuple(_array(d[name]))
    d["mount_slots"] = tuple(_flat(x, MountSlot) for x in _array(d["mount_slots"]))
    return SecurityPolicy(**d)


def abort_info_to_dict(abort: AbortInfo) -> JsonObject:
    return _encode(abort, AbortInfo)


def abort_info_from_dict(value: JsonObject) -> AbortInfo:
    return _flat(value, AbortInfo)


def runtime_receipt_to_dict(receipt: RuntimeReceipt) -> JsonObject:
    return _encode(receipt, RuntimeReceipt)


def runtime_receipt_from_dict(value: JsonObject) -> RuntimeReceipt:
    return _flat(value, RuntimeReceipt)


def program_outcome_to_dict(outcome: ProgramOutcome) -> JsonObject:
    return _encode(outcome, ProgramOutcome)


def program_outcome_from_dict(value: JsonObject) -> ProgramOutcome:
    d = _closed(value, _fields_for(ProgramOutcome))
    return ProgramOutcome(d["observation"], None if d["abort"] is None else abort_info_from_dict(d["abort"]),
                          None if d["receipt"] is None else runtime_receipt_from_dict(d["receipt"]),
                          rejected=d["rejected"])


def score_outcome_to_dict(outcome: ScoreOutcome) -> JsonObject:
    return _encode(outcome, ScoreOutcome)


def _ex_from_dict(value: JsonObject) -> ExResult:
    from bench.score import ExResult
    result = ExResult(**_closed(value, _fields_for(ExResult)))
    _ex_result(result)
    return result


def score_outcome_from_dict(value: JsonObject) -> ScoreOutcome:
    d = _closed(value, _fields_for(ScoreOutcome))
    return ScoreOutcome(None if d["result"] is None else _ex_from_dict(d["result"]),
                        None if d["abort"] is None else abort_info_from_dict(d["abort"]),
                        None if d["receipt"] is None else runtime_receipt_from_dict(d["receipt"]))


def execution_binding_sha256(binding: ExecutionBinding) -> str:
    return hashlib.sha256(execution_binding_canonical_bytes(binding)).hexdigest()


def execution_binding_canonical_bytes(binding: ExecutionBinding) -> bytes:
    """Canonical closed binding object, no envelope and no trailing LF."""
    return canonical_json_bytes(execution_binding_to_dict(binding))


def source_pins_sha256(pins: tuple[SourcePin, ...]) -> str:
    """Canonical ordered source-pin tuple; never substitute observed digests."""
    _pins(pins)
    return hashlib.sha256(canonical_json_bytes(pins)).hexdigest()


def security_policy_sha256(policy: SecurityPolicy) -> str:
    return hashlib.sha256(canonical_json_bytes(_encode(policy, SecurityPolicy))).hexdigest()


def security_profile_sha256(policy: SecurityPolicy, environment: Environment) -> str:
    _environment(environment)
    return hashlib.sha256(canonical_json_bytes({"policy": _encode(policy, SecurityPolicy),
                                              "environment": environment})).hexdigest()


def _policy_sha(*, daemon_socket, shared_state_dir, observer, environment, policy,
                admission_bytes=469762048, reserve_bytes=201326592,
                max_sample_age_ms=4000, api_timeout_ms=3000) -> str:
    payload = {"daemon_socket": str(daemon_socket), "shared_state_dir": str(shared_state_dir),
        "observer": _encode(observer, MemoryObserver), "environment": environment,
        "policy": _encode(policy, SecurityPolicy), "admission_bytes": admission_bytes,
        "reserve_bytes": reserve_bytes, "max_sample_age_ms": max_sample_age_ms,
        "api_timeout_ms": api_timeout_ms, "wire_format": "sql_pilot_wire",
        "wire_schema_version": WIRE_SCHEMA_VERSION}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def execution_policy_sha256(profile: ExecutionProfile) -> str:
    return _policy_sha(**{name: getattr(profile, name) for name in (
        "daemon_socket", "shared_state_dir", "observer", "environment", "policy",
        "admission_bytes", "reserve_bytes", "max_sample_age_ms", "api_timeout_ms")})


def make_execution_profile(*, daemon_socket: Path, observer: MemoryObserver,
                           program_sources: tuple[SourcePin, ...],
                           scorer_sources: tuple[SourcePin, ...],
                           controller_sources: tuple[SourcePin, ...],
                           environment: Environment = APPROVED_ENVIRONMENT,
                           policy: SecurityPolicy = SecurityPolicy()) -> ExecutionProfile:
    socket = _path(daemon_socket).resolve()
    shared = shared_state_dir_for(socket)
    security = security_profile_sha256(policy, environment)
    def role(name, pins):
        return RoleBinding(name, IMAGE_MANIFEST_SHA256, IMAGE_CONFIG_SHA256,
                           "linux/arm64", pins, security, limits_for(name))
    binding = ExecutionBinding(program=role("program", program_sources), scorer=role("scorer", scorer_sources),
        controller_sources=controller_sources, policy_sha256=_policy_sha(daemon_socket=socket,
        shared_state_dir=shared, observer=observer, environment=environment, policy=policy))
    return ExecutionProfile(daemon_socket=socket, shared_state_dir=shared,
        observer=observer, environment=environment, policy=policy, binding=binding)


def execution_profile_to_dict(profile: ExecutionProfile) -> JsonObject:
    return _encode(profile, ExecutionProfile)


def execution_profile_from_dict(value: JsonObject) -> ExecutionProfile:
    d = dict(_closed(value, _fields_for(ExecutionProfile)))
    d["daemon_socket"] = Path(_text(d["daemon_socket"], nonempty=True))
    d["shared_state_dir"] = Path(_text(d["shared_state_dir"], nonempty=True))
    obs = dict(_closed(d["observer"], _fields_for(MemoryObserver)))
    obs["binary"] = Path(_text(obs["binary"], nonempty=True))
    d["observer"] = MemoryObserver(**obs)
    d["environment"] = tuple(tuple(_array(p)) for p in _array(d["environment"]))
    d["policy"] = _policy_from_dict(d["policy"])
    d["binding"] = execution_binding_from_dict(d["binding"])
    return ExecutionProfile(**d)


def execution_profile_payload_sha256(profile: ExecutionProfile) -> str:
    return hashlib.sha256(canonical_json_bytes(execution_profile_to_dict(profile))).hexdigest()


def execution_profile_envelope(profile: ExecutionProfile) -> JsonObject:
    return {"format": "sql_pilot_execution_profile", "schema_version": 1,
            "payload": execution_profile_to_dict(profile),
            "sha256": execution_profile_payload_sha256(profile)}


def execution_profile_canonical_bytes(profile: ExecutionProfile) -> bytes:
    return bounded_bytes(canonical_json_bytes(execution_profile_envelope(profile)) + b"\n", maximum=MAX_ARTIFACT_BYTES)


def execution_profile_sha256(profile: ExecutionProfile) -> str:
    """WHOLE canonical envelope INCLUDING LF, without filesystem validation.

    Profiles are concrete immutable records, validated on construction. Hashing
    is a snapshot operation; fresh source/path admission is a separate gate.
    """
    if type(profile) is not ExecutionProfile:
        raise TypeError("concrete ExecutionProfile required")
    payload = _plain(profile)
    envelope = {
        "format": "sql_pilot_execution_profile", "schema_version": 1,
        "payload": payload,
        "sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }
    raw = bounded_bytes(canonical_json_bytes(envelope) + b"\n",
                        maximum=MAX_ARTIFACT_BYTES)
    return hashlib.sha256(raw).hexdigest()


def execution_profile_from_bytes(data: bytes) -> ExecutionProfile:
    d = _closed(_json_line(data, maximum=MAX_ARTIFACT_BYTES), ("format", "schema_version", "payload", "sha256"))
    _version(d["schema_version"])
    if d["format"] != "sql_pilot_execution_profile" or _digest(d["sha256"]) != hashlib.sha256(canonical_json_bytes(d["payload"])).hexdigest():
        raise ValueError("wrong profile format/payload digest")
    return execution_profile_from_dict(d["payload"])


def installed_source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_source_pins(pins: tuple[SourcePin, ...], *, source_root: Path) -> None:
    _pins(pins)
    root = _path(source_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source root is not a directory")
    for pin in pins:
        candidate = root
        for part in pin.path.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("source symlink forbidden")
        if not candidate.resolve(strict=True).is_relative_to(root) or not candidate.is_file():
            raise ValueError("source escapes root/not regular")
        with candidate.open("rb") as stream:
            raw = bounded_bytes(stream.read(MAX_ARTIFACT_BYTES + 1), maximum=MAX_ARTIFACT_BYTES)
        if hashlib.sha256(raw).hexdigest() != pin.sha256:
            raise ValueError("source pin mismatch")


def build_execution_binding(profile: ExecutionProfile, *, source_root: Path) -> ExecutionBinding:
    """Validate supplied expected pins, never replace them with observed hashes.

    source_root is a trusted caller argument for local validation. The production
    controller/stager must pass installed_source_root(), not profile/user input.
    Complete runtime closure and daemon qualification remain boundary backlog.
    """
    if type(profile) is not ExecutionProfile:
        raise TypeError("concrete ExecutionProfile required")
    profile.__post_init__()
    for pins in (profile.binding.controller_sources, profile.binding.program.sources, profile.binding.scorer.sources):
        validate_source_pins(pins, source_root=source_root)
    binary = profile.observer.binary.resolve(strict=True)
    if not binary.is_file():
        raise ValueError("observer binary must be a regular pinned file")
    # Host observer executable is not an RPC/artifact. Homebrew's explicit
    # installed path may be a symlink; bind its actual target bytes, streaming.
    digest = hashlib.sha256()
    with binary.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    if digest.hexdigest() != profile.observer.binary_sha256:
        raise ValueError("observer binary pin mismatch")
    return profile.binding


def load_execution_profile(path: Path, *, source_root: Path) -> ExecutionProfile:
    with _path(path).open("rb") as stream:
        raw = stream.read(MAX_ARTIFACT_BYTES + 1)
    profile = execution_profile_from_bytes(raw)
    build_execution_binding(profile, source_root=source_root)
    return profile


@dataclass(frozen=True, slots=True)
class BootstrapPayload:
    python_version: str
    sqlite_version: str
    sources: tuple[SourcePin, ...]
    db_sha256: str

    def __post_init__(self):
        _text(self.python_version, nonempty=True); _text(self.sqlite_version, nonempty=True)
        _pins(self.sources); _digest(self.db_sha256)


@dataclass(frozen=True, slots=True)
class ProgramRequest:
    program: str
    max_rows: int
    db_sha256: str

    def __post_init__(self):
        _text(self.program, nonempty=True, maximum=MAX_PROGRAM_BYTES)
        _integer(self.max_rows, minimum=1); _digest(self.db_sha256)


def _task(value: object) -> None:
    from bench.task import SqlTask
    if type(value) is not SqlTask:
        raise TypeError("actual SqlTask required")
    for f in fields(value):
        _text(getattr(value, f.name))
    value.__post_init__()
    if value.db_path != "/db.sqlite":
        raise ValueError("scorer task DB path must be translated to /db.sqlite")


@dataclass(frozen=True, slots=True)
class ScoreRequest:
    task: SqlTask
    predicted_sql: str
    timeout_s: float
    max_rows: int
    compare: Literal["set", "multiset"]
    db_sha256: str

    def __post_init__(self):
        _task(self.task); _text(self.predicted_sql)
        if type(self.timeout_s) is not float or not math.isfinite(self.timeout_s) or not 0 < self.timeout_s <= 30:
            raise ValueError("finite scorer timeout within whole30s required")
        _integer(self.max_rows, minimum=1); _choice(self.compare, ("set", "multiset")); _digest(self.db_sha256)


@dataclass(frozen=True, slots=True)
class ProgramResponse:
    observation: str
    rejected: bool

    def __post_init__(self):
        _text(self.observation, maximum=1048576)
        if type(self.rejected) is not bool:
            raise TypeError("rejected must be bool")


@dataclass(frozen=True, slots=True)
class ExitGrant:
    result_sha256: str

    def __post_init__(self):
        _digest(self.result_sha256)


WirePayload = Union[BootstrapPayload, ProgramRequest, ScoreRequest, ProgramResponse, ExitGrant, "ExResult"]


def _payload(role: Role, kind: WireKind, value: object) -> JsonObject:
    if kind == "exit_grant":
        return _encode(value, ExitGrant)
    if kind == "bootstrap":
        return _encode(value, BootstrapPayload)
    if role == "program":
        return _encode(value, ProgramRequest if kind == "request" else ProgramResponse)
    if kind == "request":
        return _encode(value, ScoreRequest)
    _ex_result(value)
    return _plain(value)


def _payload_from_dict(role: Role, kind: WireKind, value: JsonObject) -> WirePayload:
    if kind == "exit_grant":
        return _flat(value, ExitGrant)
    if kind == "bootstrap":
        d = dict(_closed(value, _fields_for(BootstrapPayload)))
        d["sources"] = _pins_from_json(d["sources"])
        return BootstrapPayload(**d)
    if role == "program":
        return _flat(value, ProgramRequest if kind == "request" else ProgramResponse)
    if kind == "result":
        return _ex_from_dict(value)
    d = dict(_closed(value, _fields_for(ScoreRequest)))
    from bench.task import SqlTask
    d["task"] = SqlTask(**_closed(d["task"], _fields_for(SqlTask)))
    return ScoreRequest(**d)


def request_sha256(request: ProgramRequest | ScoreRequest) -> str:
    if type(request) not in (ProgramRequest, ScoreRequest):
        raise TypeError("typed request required")
    request.__post_init__()
    return hashlib.sha256(canonical_json_bytes(request)).hexdigest()


@dataclass(frozen=True, slots=True)
class WireMessage:
    role: Role
    kind: WireKind
    request_sha256: str | None
    payload: WirePayload

    def __post_init__(self):
        _choice(self.role, ("program", "scorer")); _choice(self.kind, ("bootstrap", "request", "result", "exit_grant"))
        _payload(self.role, self.kind, self.payload)
        if self.kind == "bootstrap":
            if self.request_sha256 is not None:
                raise ValueError("bootstrap request hash must be null")
        else:
            _digest(self.request_sha256)
            if self.kind == "request" and self.request_sha256 != request_sha256(self.payload):
                raise ValueError("request SHA must include full request/DB")


def encode_wire_message(role: Role, kind: WireKind, payload: WirePayload, *,
                        request_sha256: str | None = None) -> bytes:
    data = _payload(role, kind, payload)
    digest = hashlib.sha256(canonical_json_bytes(data)).hexdigest()
    request = digest if kind == "request" and request_sha256 is None else request_sha256
    WireMessage(role, kind, request, payload)
    envelope = {"format": "sql_pilot_wire", "schema_version": WIRE_SCHEMA_VERSION, "role": role, "kind": kind,
                "request_sha256": request, "payload": data, "sha256": digest}
    maximum = limits_for(role).input_bytes if kind in ("request", "exit_grant") else limits_for(role).stdout_bytes
    return bounded_bytes(canonical_json_bytes(envelope) + b"\n", maximum=maximum)


def decode_wire_message(data: bytes, *, role: Role, kind: WireKind,
                        request_sha256: str | None) -> WireMessage:
    _choice(role, ("program", "scorer")); _choice(kind, ("bootstrap", "request", "result", "exit_grant"))
    maximum = limits_for(role).input_bytes if kind in ("request", "exit_grant") else limits_for(role).stdout_bytes
    d = _closed(_json_line(data, maximum=maximum), ("format", "schema_version", "role", "kind", "request_sha256", "payload", "sha256"))
    if type(d["schema_version"]) is not int or d["schema_version"] != WIRE_SCHEMA_VERSION:
        raise ValueError("unsupported live wire schema")
    if d["format"] != "sql_pilot_wire" or d["role"] != role or d["kind"] != kind or d["request_sha256"] != request_sha256:
        raise ValueError("wire role/kind/request context mismatch")
    if _digest(d["sha256"]) != hashlib.sha256(canonical_json_bytes(d["payload"])).hexdigest():
        raise ValueError("wire payload digest mismatch")
    return WireMessage(role, kind, d["request_sha256"], _payload_from_dict(role, kind, d["payload"]))


def validate_output_budget(role: Role, *, bootstrap: bytes, result: bytes) -> None:
    bounded_bytes(READY + bootstrap + result, maximum=limits_for(role).stdout_bytes)


@dataclass(frozen=True, slots=True)
class ProgramDatabaseIdentity:
    path: str
    sha256: str
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int
    st_ctime_ns: int
    st_uid: int
    st_mode: int
    st_nlink: int


@dataclass(frozen=True, slots=True)
class PilotExecutor:
    profile: ExecutionProfile
    state_dir: Path

    def __init__(self, profile: ExecutionProfile, *, state_dir: Path):
        if type(profile) is not ExecutionProfile:
            raise TypeError("concrete immutable profile required")
        profile.__post_init__()
        _path(state_dir)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "state_dir", state_dir)

    def admit_program(self, *, db_path: str,
                      db_sha256: str) -> ProgramDatabaseIdentity:
        """Fresh source and database admission, without staging or execution."""
        _digest(db_sha256)
        _text(db_path, nonempty=True)
        source = Path(db_path)
        if (not source.is_absolute() or os.path.normpath(db_path) != db_path
                or "\x00" in db_path):
            raise ValueError("canonical absolute database path required")
        _fresh_owned_binding(self.profile)
        parent, name = _open_parent(source)
        try:
            def no_sidecars():
                for suffix in ("-wal", "-shm", "-journal"):
                    try:
                        os.stat(name + suffix, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise ValueError("database sidecar present")

            def identity(record):
                return ProgramDatabaseIdentity(
                    db_path, db_sha256, *(getattr(record, key) for key in (
                        "st_dev", "st_ino", "st_size", "st_mtime_ns",
                        "st_ctime_ns", "st_uid", "st_mode", "st_nlink")))

            no_sidecars()
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            try:
                before = os.fstat(fd)
                _owned_stat(before)
                sealed = identity(before)
                digest = hashlib.sha256()
                while chunk := os.read(fd, 65536):
                    digest.update(chunk)
                after = os.fstat(fd)
                _owned_stat(after)
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                _owned_stat(current)
                if (identity(after) != sealed or identity(current) != sealed
                        or digest.hexdigest() != db_sha256):
                    raise ValueError("database identity changed or digest mismatch")
                no_sidecars()
                # Rewalk the live parent chain too: a renamed parent must not
                # let an old directory descriptor stand in for the public path.
                current_parent, current_name = _open_parent(source)
                try:
                    current = os.stat(current_name, dir_fd=current_parent,
                                      follow_symlinks=False)
                    _owned_stat(current)
                    if identity(current) != sealed:
                        raise ValueError("database pathname changed")
                finally:
                    os.close(current_parent)
                return sealed
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def run_program(self, program: str, *, db_path: str, db_sha256: str,
                    max_rows: int) -> ProgramOutcome:
        try:
            request = ProgramRequest(program, max_rows, db_sha256)
        except (TypeError, ValueError):
            return ProgramOutcome(None, AbortInfo("program", "protocol"), None)
        return _run_isolated(self, "program", request, Path(db_path))

    def score_sql(self, predicted_sql: str, task: SqlTask, *, db_sha256: str,
                  instrument: InstrumentSettings) -> ScoreOutcome:
        from dataclasses import replace
        try:
            request = ScoreRequest(replace(task, db_path="/db.sqlite"), predicted_sql,
                                   instrument.scorer_timeout_s, instrument.scorer_max_rows,
                                   instrument.compare, db_sha256)
            original = Path(task.db_path)
        except (AttributeError, TypeError, ValueError):
            return ScoreOutcome(None, AbortInfo("scorer", "protocol"), None)
        return _run_isolated(self, "scorer", request, original)

    def owned_program(self, program: str, *, db_path: str, db_sha256: str,
                      max_rows: int) -> OwnedSqlInvocation[ProgramOutcome]:
        request = ProgramRequest(program, max_rows, db_sha256)
        return OwnedSqlInvocation(self, "program", request, Path(db_path))

    def owned_score(self, predicted_sql: str, task: SqlTask, *, db_sha256: str,
                    instrument: InstrumentSettings) -> OwnedSqlInvocation[ScoreOutcome]:
        from dataclasses import replace
        request = ScoreRequest(replace(task, db_path="/db.sqlite"), predicted_sql,
                               instrument.scorer_timeout_s, instrument.scorer_max_rows,
                               instrument.compare, db_sha256)
        return OwnedSqlInvocation(self, "scorer", request, Path(task.db_path))


# Runtime imports remain stdlib-only. No execution or daemon IO occurs at import.
import concurrent.futures
import fcntl
import http.client
import select
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid
import asyncio

_PROGRAM_PATHS = (
    "ptc/__init__.py", "ptc/runtime.py", "ptc/sql_arms.py", "ptc/sql_runtime.py",
    "ptc/sqlite_safety.py", "ptc/sql_isolation.py", "ptc/sql_worker.py",
)
_SCORER_PATHS = (
    "bench/__init__.py", "bench/task.py", "bench/score.py", "bench/loader.py",
    "bench/shapes.py", "bench/suite.py", "ptc/__init__.py", "ptc/runtime.py",
    "ptc/sqlite_safety.py", "ptc/paired.py", "ptc/metrics.py",
    "ptc/sql_isolation.py", "bench/sql_score_worker.py",
)
_OWNER_LABEL = "org.co-train.sql-isolation"


def _fresh_owned_binding(profile: ExecutionProfile) -> ExecutionBinding:
    binding = build_execution_binding(profile, source_root=installed_source_root())
    if ({p.path for p in binding.program.sources} != set(_PROGRAM_PATHS)
            or {p.path for p in binding.scorer.sources} != set(_SCORER_PATHS)
            or "ptc/sql_isolation.py" not in {p.path for p in binding.controller_sources}):
        raise ValueError("incomplete source closure")
    return binding


class _Failure(RuntimeError):
    def __init__(self, reason: AbortReason, detail: str):
        super().__init__(detail)
        self.reason = reason


class _HTTPFailure(_Failure):
    """Only this typed status, never text, authorizes the 409 branch."""
    def __init__(self, status: int):
        super().__init__("transport", f"daemon HTTP {status}")
        self.status = status


def _owned_stat(s, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(s.st_mode) or s.st_uid != os.getuid():
        raise ValueError("owned regular file/directory required")
    if not directory and s.st_nlink != 1:
        raise ValueError("hardlinked source refused")


def _open_parent(path: Path):
    """Walk every parent with directory FDs; never follow a source symlink."""
    path = path.absolute()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = new
        return fd, path.name
    except BaseException:
        os.close(fd)
        raise


def _secure_directory(path: Path):
    if not path.is_absolute():
        raise ValueError("absolute owned directory required")
    if path == Path("/"):
        raise ValueError("not an owned state root")
    parent, name = None, None
    if not path.parent.exists():
        _secure_directory(path.parent)
    parent, name = _open_parent(path)
    try:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            s = os.fstat(fd); _owned_stat(s, directory=True)
            if s.st_mode & 0o022:
                raise ValueError("state directory writable by other identities")
        finally:
            os.close(fd)
    finally:
        os.close(parent)


class _OwnedFileReplaced(ValueError):
    """An owned snapshot became unlinked; its bytes are never returned."""


def _read_owned(path: Path, maximum=MAX_ARTIFACT_BYTES) -> bytes:
    parent, name = _open_parent(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if (before.st_nlink == 0 and stat.S_ISREG(before.st_mode)
                    and before.st_uid == os.getuid() and 0 <= before.st_size <= maximum):
                raise _OwnedFileReplaced("source changed before initial inspection")
            _owned_stat(before)
            data = bytearray()
            while chunk := os.read(fd, min(65536, maximum + 1 - len(data))):
                data.extend(chunk)
                if len(data) > maximum:
                    raise ValueError("owned file exceeds bound")
            after = os.fstat(fd)
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink) != (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink):
                if (before.st_nlink == 1 and after.st_nlink == 0
                        and (before.st_ino, before.st_size, before.st_mtime_ns,
                             before.st_mode, before.st_uid, before.st_gid) ==
                            (after.st_ino, after.st_size, after.st_mtime_ns,
                             after.st_mode, after.st_uid, after.st_gid)):
                    raise _OwnedFileReplaced("source changed while read")
                raise ValueError("source changed while read")
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _write_owned(path: Path, data: bytes, *, mode=0o600):
    parent, name = _open_parent(path)
    tmp = "." + name + "." + uuid.uuid4().hex
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fchmod(fd, mode); os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def _append_owned(path: Path, value: object):
    parent, name = _open_parent(path)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            _owned_stat(os.fstat(fd))
            data = canonical_json_bytes(value) + b"\n"
            if os.write(fd, data) != len(data):
                raise OSError("short journal append")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def _stage_database(source: Path, expected_sha: str, stage: Path) -> Path:
    _digest(expected_sha)
    parent, name = _open_parent(source)
    out = stage / "db.sqlite"
    destination = None
    try:
        def no_sidecars():
            for suffix in ("-wal", "-shm", "-journal"):
                try:
                    os.stat(name + suffix, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise ValueError("database sidecar present")
        no_sidecars()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd); _owned_stat(before)
            digest = hashlib.sha256()
            while chunk := os.read(fd, 65536):
                digest.update(chunk)
            if digest.hexdigest() != expected_sha:
                raise ValueError("saved database digest mismatch")
            os.lseek(fd, 0, os.SEEK_SET)
            target_parent, target_name = _open_parent(out)
            try:
                destination = os.open(target_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                      os.O_NOFOLLOW, 0o600, dir_fd=target_parent)
                staged = hashlib.sha256()
                while chunk := os.read(fd, 65536):
                    staged.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        view = view[os.write(destination, view):]
                os.fchmod(destination, 0o444); os.fsync(destination)
                os.close(destination); destination = None
                os.fsync(target_parent)
            finally:
                os.close(target_parent)
            after = os.fstat(fd); _owned_stat(after)
            if staged.hexdigest() != expected_sha or (
                before.st_ino, before.st_size, before.st_mtime_ns
            ) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("database changed while staged")
            no_sidecars()
            # Verify the actual owned mount source, not just the copying stream.
            verify = hashlib.sha256()
            staged_fd = os.open(out, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                _owned_stat(os.fstat(staged_fd))
                while chunk := os.read(staged_fd, 65536):
                    verify.update(chunk)
            finally:
                os.close(staged_fd)
            if verify.hexdigest() != expected_sha:
                raise ValueError("staged database digest mismatch")
            no_sidecars()
            return out
        finally:
            os.close(fd)
    finally:
        if destination is not None:
            os.close(destination)
        os.close(parent)


def _stage_sources(profile: ExecutionProfile, job: Path):
    root = installed_source_root()
    binding = build_execution_binding(profile, source_root=root)
    if {p.path for p in binding.program.sources} != set(_PROGRAM_PATHS):
        raise ValueError("incomplete or excessive PROGRAM closure")
    if {p.path for p in binding.scorer.sources} != set(_SCORER_PATHS):
        raise ValueError("incomplete or excessive SCORER closure")
    if "ptc/sql_isolation.py" not in {p.path for p in binding.controller_sources}:
        raise ValueError("controller/guardian/stager/decoder source unpinned")
    all_pins = {}
    for pin in (*binding.program.sources, *binding.scorer.sources, *binding.controller_sources):
        if not pin.path.endswith(".py") or pin.path.split("/")[0] not in ("ptc", "bench", "train"):
            raise ValueError("non-source controller pin")
        if pin.path in all_pins and all_pins[pin.path] != pin:
            raise ValueError("inconsistent source pins")
        all_pins[pin.path] = pin
    for name, pins in (("controller", tuple(all_pins.values())),
                       ("program", binding.program.sources), ("scorer", binding.scorer.sources)):
        target = job / name
        _secure_directory(target)
        for pin in pins:
            data = _read_owned(root / pin.path)
            if hashlib.sha256(data).hexdigest() != pin.sha256:
                raise ValueError("source pin changed during staging")
            path = target / pin.path
            _secure_directory(path.parent)
            _write_owned(path, data, mode=0o444)
        _write_owned(target / "sources.json", canonical_json_bytes(pins) + b"\n", mode=0o444)
        # File modes protect against accidental mutation, hashes bind actual bytes.
        for directory, _, _ in os.walk(target, topdown=False):
            os.chmod(directory, 0o555)


def _activate_staged_import_root(job, profile):
    """Guardian only: verify the entire native/controller union before imports."""
    root = job / "controller"
    expected = {p.path: p for p in (*profile.binding.program.sources,
                                  *profile.binding.scorer.sources,
                                  *profile.binding.controller_sources)}
    if not set(_PROGRAM_PATHS + _SCORER_PATHS).issubset(expected):
        raise _Failure("binding", "incomplete staged controller/native union")
    validate_source_pins(tuple(expected.values()), source_root=root)
    for name, module in tuple(sys.modules.items()):
        if name == "bench" or name.startswith("bench.") or name == "ptc" or name.startswith("ptc."):
            origin = getattr(module, "__file__", None)
            if origin is None or not Path(origin).resolve().is_relative_to(root.resolve()):
                raise _Failure("binding", "foreign package already imported in guardian")
    sys.path.insert(0, str(root))


def _stopped_state(state: object) -> bool:
    return type(state) is dict and all(state.get(k) is False for k in (
        "Running", "Paused", "Restarting")) and type(state.get("Pid")) is int and state["Pid"] == 0


class _MuxDecoder:
    def __init__(self, *, stdout_limit: int, stderr_limit: int):
        self.limits = {1: stdout_limit, 2: stderr_limit}
        self.counts = {1: 0, 2: 0}
        self.buffer = bytearray()
        self.stream = None
        self.remaining = 0

    def feed(self, data: bytes):
        self.buffer.extend(data)
        result = []
        while self.buffer:
            if self.stream is None:
                if len(self.buffer) < 8:
                    break
                stream, a, b, c, length = struct.unpack(">BBBBI", self.buffer[:8])
                del self.buffer[:8]
                if stream not in (1, 2) or a or b or c:
                    raise _Failure("protocol", "invalid Docker stream header")
                self.stream, self.remaining = stream, length
                if not length:
                    self.stream = None
                    continue
            take = min(len(self.buffer), self.remaining,
                       self.limits[self.stream] + 1 - self.counts[self.stream])
            body = bytes(self.buffer[:take]); del self.buffer[:take]
            self.counts[self.stream] += take
            if self.counts[self.stream] > self.limits[self.stream]:
                raise _Failure("output", "output byte cap exceeded")
            self.remaining -= take
            result.append((self.stream, body))
            if not self.remaining:
                self.stream = None
        return result


def _metadata(raw: bytes):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate metadata key")
            value[key] = item
        return value
    def constant(_):
        raise ValueError("nonfinite daemon metadata")
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                      parse_constant=constant)


class _Daemon:
    def __init__(self, profile):
        self.profile = profile
        self.lock = threading.RLock()
        self.active = set()
        self.workers = set()

    def _operation_bound(self, timeout):
        end = time.monotonic() + min(timeout or 3.0, 3.0)
        if hasattr(self, "cleanup_deadline"):
            end = min(end, self.cleanup_deadline)
        elif hasattr(self, "operation_deadline"):
            end = min(end, self.operation_deadline)
        if getattr(self, "shutdown_supervision", None) is not None:
            end = min(end, self.operation_deadline)
        owned = getattr(self, "_owned", None)
        if owned is not None:
            end = min(end, owned.cap())
        return end

    def _supervise(self, end, operation_end=None):
        owned = getattr(self, "_owned", None)
        if owned is not None:
            if not getattr(self, "_owned_observation", False):
                owned.checkpoint()
            end = min(end, owned.cap())
        if time.monotonic() >= end:
            hard_end = end if operation_end is None else operation_end
            reason = "cleanup" if hasattr(self, "cleanup_deadline") else (
                "deadline" if hasattr(self, "operation_deadline") and
                hard_end >= self.operation_deadline else "transport")
            raise _Failure(reason, "absolute RPC deadline")
        shutdown = getattr(self, "shutdown_supervision", None)
        if shutdown is not None:
            shutdown()  # Cleanup mode must never disable coordinated shutdown.
        elif not hasattr(self, "cleanup_deadline"):
            if getattr(self, "control", None) is not None:
                _controller_alive(self.control)
            if getattr(self, "observer", None) is not None:
                self.observer.check()

    def _whole_rpc(self, operation, sock, end):
        """The calling supervisor stays responsive during progressing HTTP IO."""
        # Socket cancellation AND worker join share this same hard deadline.
        # Reserve a small part of the existing budget, never add a fresh join
        # timeout after it has expired.
        io_end = end - min(0.05, max(0, end - time.monotonic()) / 4)
        self._supervise(io_end, end)
        done = threading.Event()
        box = []
        def run():
            try:
                box.append((True, operation()))
            except BaseException as exc:
                box.append((False, exc))
            finally:
                done.set()
        thread = threading.Thread(target=run, name="sql-bounded-rpc", daemon=False)
        with self.lock:
            self.workers.add(thread)
        started = False
        cancellation = None
        try:
            thread.start(); started = True
            while not done.wait(min(0.01, max(0, io_end - time.monotonic()))):
                try:
                    self._supervise(io_end, end)
                except _OwnedCancellation as exc:
                    # Preserve the in-flight response and join, not merely a
                    # cancelled socket. Unknown mutations still cannot ACK.
                    cancellation = exc
                    _begin_cleanup(self._owned.journal)
            try:
                self._supervise(end)
            except _OwnedCancellation as exc:
                cancellation = exc
                _begin_cleanup(self._owned.journal)
            if not box[0][0]:
                error = box[0][1]
                if isinstance(error, _Failure):
                    raise error
                reason = "memory" if isinstance(error, MemoryError) else "transport"
                raise _RPCUncertain(reason, "incomplete/malformed RPC: " + type(error).__name__) from error
            if cancellation is not None:
                raise cancellation
            return box[0][1]
        except _HTTPFailure:
            raise  # Completed, typed HTTP status, especially the exact 409 path.
        except _OwnedCancellation:
            raise
        except _Failure as exc:
            # A cancelled mutation may have reached the peer. Never treat it as
            # completion merely because its socket was closed.
            raise _RPCUncertain(exc.reason, str(exc)) from exc
        finally:
            if started and not done.is_set():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            if started:
                owned = getattr(self, "_owned", None)
                if owned is None:
                    thread.join(timeout=max(0, end - time.monotonic()))
                else:
                    while thread.is_alive() and time.monotonic() < min(end, owned.cap()):
                        thread.join(timeout=min(0.01, max(0, min(end, owned.cap()) - time.monotonic())))
            if started and thread.is_alive():
                raise _RPCUncertain("cleanup", "RPC worker did not join after socket cancellation")
            with self.lock:
                self.workers.discard(thread)

    def call(self, method, path, body=None, *, statuses=(200,), timeout=None):
        end = self._operation_bound(timeout)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection = http.client.HTTPConnection("localhost", timeout=max(0.001, end - time.monotonic()))
        with self.lock:
            self.active.add(connection)
        def operation():
            sock.settimeout(max(0.001, end - time.monotonic()))
            sock.connect(str(self.profile.daemon_socket))
            connection.sock = sock
            raw = None if body is None else canonical_json_bytes(body)
            connection.request(method, path, body=raw,
                               headers={"Content-Type": "application/json", "Connection": "close"})
            response = connection.getresponse()
            try:
                if response.status not in statuses:
                    raise _HTTPFailure(response.status)
                data = response.read(MAX_ARTIFACT_BYTES + 1)
                bounded_bytes(data, maximum=MAX_ARTIFACT_BYTES)
                return None if not data else _metadata(data)
            finally:
                response.close()
        try:
            return self._whole_rpc(operation, sock, end)
        finally:
            connection.close(); sock.close()
            with self.lock:
                self.active.discard(connection)

    def attach(self, cid):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        end = self._operation_bound(3.0)
        def operation():
            sock.settimeout(max(0.001, end - time.monotonic())); sock.connect(str(self.profile.daemon_socket))
            request = (f"POST /containers/{cid}/attach?stream=1&stdin=1&stdout=1&stderr=1 HTTP/1.1\r\n"
                       "Host: localhost\r\nConnection: Upgrade\r\nUpgrade: tcp\r\nContent-Length: 0\r\n\r\n")
            sock.sendall(request.encode("ascii"))
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                byte = sock.recv(1)
                if not byte or len(header) >= 16384:
                    raise _Failure("transport", "attach upgrade failed")
                header.extend(byte)
            if bytes(header).split(b"\r\n", 1)[0] != b"HTTP/1.1 101 UPGRADED":
                raise _Failure("transport", "attach did not upgrade")
            sock.settimeout(0.1)
            return sock
        try:
            return self._whole_rpc(operation, sock, end)
        except BaseException:
            sock.close()
            raise


class _RPCUncertain(_Failure):
    pass


def _container_config(profile, role, job, nonce):
    limits = limits_for(role)
    seccomp = {"defaultAction": "SCMP_ACT_ERRNO", "defaultErrnoRet": 1,
               "architectures": ["SCMP_ARCH_AARCH64"],
               "syscalls": [{"names": list(_SYSCALLS), "action": "SCMP_ACT_ALLOW"}]}
    worker = "ptc/sql_worker.py" if role == "program" else "bench/sql_score_worker.py"
    host = {
        "Memory": limits.memory_bytes, "MemorySwap": limits.memory_bytes,
        "MemorySwappiness": 0, "PidsLimit": 1, "ShmSize": 1048576,
        "ReadonlyRootfs": True, "Privileged": False, "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges:true", "seccomp=" + canonical_json_bytes(seccomp).decode()],
        "PidMode": "", "IpcMode": "private", "UTSMode": "", "CgroupnsMode": "private",
        "NetworkMode": "none", "ReadonlyPaths": list(_READONLY), "MaskedPaths": list(_MASKED),
        "Ulimits": [{"Name": "nofile", "Soft": 64, "Hard": 64},
                    {"Name": "core", "Soft": 0, "Hard": 0}],
        "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=16777216,mode=1777"},
        "LogConfig": {"Type": "none", "Config": {}},
        "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0}, "AutoRemove": False,
        "Mounts": [
            {"Type": "bind", "Source": str(job / role), "Target": "/bundle", "ReadOnly": True,
             "BindOptions": {"Propagation": "rprivate"}},
            {"Type": "bind", "Source": str(job / "db.sqlite"), "Target": "/db.sqlite",
             "ReadOnly": True, "BindOptions": {"Propagation": "rprivate"}},
        ],
    }
    return {"Image": "sha256:" + IMAGE_MANIFEST_SHA256, "Hostname": "co-train-isolation",
            "User": "65534:65534", "Env": [k + "=" + v for k, v in profile.environment],
            "Entrypoint": ["/usr/local/bin/python3", "-I", "-B", "-u", "/bundle/" + worker],
            "Cmd": [], "WorkingDir": "/bundle", "Tty": False, "OpenStdin": True,
            "StdinOnce": True, "AttachStdin": True, "AttachStdout": True, "AttachStderr": True,
            "Labels": {_OWNER_LABEL: nonce, _OWNER_LABEL + ".role": role},
            "HostConfig": host}


def _verify_owned(obj, journal):
    cfg = journal["config"]
    if type(obj) is not dict or obj.get("Id") != journal["cid"]:
        raise _Failure("binding", "full owned CID mismatch")
    if obj.get("Image") not in ("sha256:" + IMAGE_MANIFEST_SHA256, "sha256:" + IMAGE_CONFIG_SHA256):
        raise _Failure("binding", "owned image mismatch")
    actual, host = obj.get("Config"), obj.get("HostConfig")
    if type(actual) is not dict or type(host) is not dict:
        raise _Failure("binding", "missing effective configuration")
    for key in ("Hostname", "User", "Env", "Entrypoint", "WorkingDir", "Tty", "OpenStdin",
                "StdinOnce", "AttachStdin", "AttachStdout", "AttachStderr", "Labels"):
        if type(actual.get(key)) is not type(cfg[key]) or actual[key] != cfg[key]:
            raise _Failure("binding", "effective Config mismatch: " + key)
    for key, value in cfg["HostConfig"].items():
        if key == "Mounts":
            continue
        if (key == "MemorySwappiness" and type(value) is int and value == 0
                and key in host and host[key] is None
                and all(type(caps.get(name)) is int and caps[name] > 0
                        for caps in (cfg["HostConfig"], host)
                        for name in ("Memory", "MemorySwap"))
                and host["Memory"] == host["MemorySwap"] ==
                    cfg["HostConfig"]["Memory"] == cfg["HostConfig"]["MemorySwap"]):
            # cgroupv2 may normalize requested zero to explicit null. Equal,
            # positive memory/total-swap caps still prohibit additional swap.
            continue
        if type(host.get(key)) is not type(value) or host[key] != value:
            raise _Failure("binding", "effective HostConfig mismatch: " + key)
    mounts = obj.get("Mounts")
    if type(mounts) is not list or len(mounts) != 2:
        raise _Failure("binding", "extra/missing mounts")
    for expected in cfg["HostConfig"]["Mounts"]:
        found = [m for m in mounts if m.get("Destination") == expected["Target"]]
        if len(found) != 1 or any(found[0].get(k) != v for k, v in (
            ("Type", "bind"), ("Source", expected["Source"]), ("RW", False),
            ("Propagation", "rprivate"))):
            raise _Failure("binding", "effective mount mismatch")
    for key in ("Binds", "Devices", "DeviceRequests", "VolumesFrom", "Links", "ExtraHosts"):
        if host.get(key) not in (None, []):
            raise _Failure("binding", "unexpected host capability: " + key)
    if host.get("PortBindings") not in (None, {}) or host.get("CapAdd") not in (None, []):
        raise _Failure("binding", "unexpected ports/capabilities")
    if host.get("Runtime") != "runc":
        raise _Failure("binding", "unexpected runtime")
    return obj


def _worker_handshake(role):
    """Guest-only bootstrap. Never substitutes host inventory versions."""
    import sqlite3
    pins = _pins_from_json(_metadata(Path("/bundle/sources.json").read_bytes()))
    actual = tuple(SourcePin(p.path, hashlib.sha256(Path("/bundle", p.path).read_bytes()).hexdigest())
                   for p in pins)
    digest = hashlib.sha256()
    with open("/db.sqlite", "rb") as db:
        while chunk := db.read(65536):
            digest.update(chunk)
    bootstrap = BootstrapPayload(sys.version.split()[0], sqlite3.sqlite_version, actual, digest.hexdigest())
    sys.stdout.buffer.write(READY + encode_wire_message(role, "bootstrap", bootstrap))
    sys.stdout.buffer.flush()
    raw = sys.stdin.buffer.readline(MAX_ARTIFACT_BYTES + 1)
    envelope = _json_line(raw, maximum=MAX_ARTIFACT_BYTES)
    sha = _digest(envelope.get("request_sha256"))
    message = decode_wire_message(raw, role=role, kind="request", request_sha256=sha)
    if message.payload.db_sha256 != digest.hexdigest():
        raise ValueError("guest database mismatch")
    return message.payload, sha


def _worker_wait_for_exit_grant(role, sha, result, request):
    """Guest stays alive after flush; grant binds the exact result bytes + LF."""
    request_bytes = len(encode_wire_message(role, "request", request, request_sha256=sha))
    remaining = limits_for(role).input_bytes - request_bytes
    raw = sys.stdin.buffer.readline(remaining + 1)
    bounded_bytes(raw, maximum=remaining)
    grant = decode_wire_message(raw, role=role, kind="exit_grant", request_sha256=sha)
    if grant.payload.result_sha256 != hashlib.sha256(result).hexdigest():
        raise ValueError("exit grant result mismatch")


def _native_call(function, *args, **kwargs):
    """Guest current-thread exception observer, not an observation-string filter.

    Native catch boundaries retain their own code/semantics. Existing frames keep
    this exception trace even when runtime.run temporarily installs its line
    deadline tracer. No event history or exception strings are allocated here.
    """
    import sqlite3
    flag = [False]
    memory_exit = SystemExit(70)
    previous = sys.gettrace()
    def trace(frame, event, arg):
        frame.f_trace_lines = False
        frame.f_trace_opcodes = False
        if event == "exception":
            value = arg[1]
            if isinstance(value, MemoryError) or (
                isinstance(value, sqlite3.Error) and
                type(getattr(value, "sqlite_errorcode", None)) is int and
                value.sqlite_errorcode == sqlite3.SQLITE_NOMEM
            ):
                flag[0] = True
        return trace
    try:
        sys.settrace(trace)
        return function(*args, **kwargs)
    finally:
        sys.settrace(previous)
        _allocation_exit(flag, memory_exit)


def _allocation_exit(flag, memory_exit):
    if flag[0]:
        raise memory_exit


class _ObservationFailure(_Failure):
    def __init__(self, detail):
        super().__init__("memory", detail)


class _MissingRawUsage(_ObservationFailure):
    def __init__(self, cid, started, finished, stats_rpc_completed_at, validation_cause):
        super().__init__("terminal candidate missing raw memory usage")
        self.cid = _digest(cid)
        self.started, self.finished = started, finished
        self.stats_rpc_completed_at = stats_rpc_completed_at
        self.validation_cause = validation_cause
        if (type(validation_cause) is not ValueError or
                any(type(t) is not float or not math.isfinite(t) for t in (
                    started, finished, stats_rpc_completed_at))):
            raise ValueError("invalid private missing-usage observation")


@dataclass(frozen=True, slots=True)
class _StoppedOwnedProof:
    cid: str
    job: Path
    nonce: str
    config_sha256: str
    guardian: int
    observer_token: str
    stopped_at: float

    def __post_init__(self):
        _digest(self.cid); _path(self.job); _text(self.nonce, nonempty=True, maximum=128)
        _digest(self.config_sha256); _integer(self.guardian, minimum=1)
        if (type(self.observer_token) is not str or
                re.fullmatch("[0-9a-f]{32}", self.observer_token) is None or
                type(self.stopped_at) is not float or not math.isfinite(self.stopped_at) or self.stopped_at < 0):
            raise ValueError("invalid private stopped proof")


def _event(job, kind, **values):
    _append_owned(job / "events.jsonl", {"kind": kind, "at": time.monotonic(), **values})


def _diagnostic_type(value):
    allowed = (type(None), bool, int, float, str, list, dict, ValueError, TypeError,
               RuntimeError, OSError, TimeoutError, MemoryError, UnicodeDecodeError,
               json.JSONDecodeError, _Failure, _HTTPFailure, _RPCUncertain, _ObservationFailure)
    return type(value).__name__ if type(value) in allowed else "other"


def _observer_failure_event(job, failure):
    # No messages, arbitrary filenames/function names, traceback locals or bodies.
    functions = ("_run", "_memory_sample", "get", "_integer", "_digest", "_vm_memory",
                 "call", "operation", "_whole_rpc", "_supervise", "_metadata", "pairs",
                 "constant", "_operation_bound", "run")
    chain = []
    for _ in range(4):
        if failure is None:
            break
        frames, seen, tb = [], 0, failure.__traceback__
        for _ in range(16):
            if tb is None:
                break
            code = tb.tb_frame.f_code
            if code.co_filename == __file__ and code.co_name in functions:
                seen += 1
                frames = (frames + [("ptc/sql_isolation.py", code.co_name, tb.tb_lineno)])[-4:]
            tb = tb.tb_next
        reason = failure.reason if type(failure) in (
            _Failure, _HTTPFailure, _RPCUncertain, _ObservationFailure) else None
        status = failure.status if type(failure) is _HTTPFailure else None
        chain.append({"type": _diagnostic_type(failure), "frames": frames,
                      "frames_truncated": tb is not None or seen > 4,
                      "reason": reason if type(reason) is str and reason in _ABORT_REASONS else None,
                      "status": status if type(status) is int and 100 <= status <= 599 else None})
        failure = failure.__cause__ if failure.__cause__ is not None else (
            None if failure.__suppress_context__ else failure.__context__)
    _event(job, "OBSERVER_FAILURE", chain=chain, chain_truncated=failure is not None)


def _vm_memory(profile, job, deadline):
    with _OWNED_CONTEXT_LOCK:
        owned = _OWNED_CONTEXTS.get(job.name)
    if owned is not None:
        return _owned_vm_memory(profile, job, deadline, owned)
    remaining = min(2.0, deadline - time.monotonic())
    if remaining <= 0:
        raise _ObservationFailure("VM observation deadline")
    token = uuid.uuid4().hex
    _event(job, "CLI_SPAWN_INTENT", token=token, guardian=os.getpid(),
           binary_sha256=profile.observer.binary_sha256)
    process = subprocess.Popen(
        [str(profile.observer.binary), "--profile", "default", "ssh", "--", "cat", "/proc/meminfo"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
        env={"HOME": pwd.getpwuid(os.getuid()).pw_dir, "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
             "LANG": "C.UTF-8"})
    try:
        _event(job, "CLI_STARTED", token=token, pid=process.pid, guardian=os.getpid())
        try:
            output, error = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate(timeout=1.0)
            raise _ObservationFailure("VM observer timeout") from exc
        if process.returncode != 0 or len(output) > 65536 or len(error) > 65536:
            raise _ObservationFailure("VM observer failed")
        fields = {}
        for line in output.decode("ascii", "strict").splitlines():
            parts = line.split()
            if parts and parts[0] in ("MemTotal:", "MemAvailable:"):
                if len(parts) != 3 or parts[2] != "kB" or parts[0] in fields:
                    raise _ObservationFailure("invalid VM memory fields")
                fields[parts[0]] = _integer(int(parts[1]), minimum=1) * 1024
        if set(fields) != {"MemTotal:", "MemAvailable:"} or fields["MemAvailable:"] > fields["MemTotal:"]:
            raise _ObservationFailure("missing or inconsistent VM memory")
        return fields["MemTotal:"], fields["MemAvailable:"]
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=1.0)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        _event(job, "CLI_JOIN_ACK", token=token, pid=process.pid, returncode=process.returncode,
               guardian=os.getpid(), reaped=True)


def _memory_sample(profile, daemon, job):
    started = time.monotonic()
    end = started + 4.0
    owned = getattr(daemon, "_owned", None)
    def result(future):
        if owned is None:
            return future.result(timeout=max(0.001, end - time.monotonic()))
        while True:
            if not getattr(daemon, "_owned_observation", False):
                try:
                    owned.checkpoint()
                except _OwnedCancellation:
                    _begin_cleanup(owned.journal)
                    raise
            remaining = min(end, owned.cap()) - time.monotonic()
            if remaining <= 0:
                raise _ObservationFailure("complete sample absolute deadline")
            try:
                return future.result(timeout=min(0.01, remaining))
            except concurrent.futures.TimeoutError:
                continue
    def get(path, timed=False):
        remaining = min(3.0, end - time.monotonic())
        if remaining <= 0:
            raise _ObservationFailure("complete sample older than four seconds")
        value = daemon.call("GET", path, timeout=remaining)
        completed = time.monotonic()  # Worker completion, never future-consumption time.
        return (value, completed) if timed else value
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="sql-metadata")
    if owned is not None:
        with owned.lock:
            owned.executors.append(pool)
    try:
        try:
            vm = pool.submit(_vm_memory, profile, job, end)
            info = pool.submit(get, "/info")
            listing = pool.submit(get, "/containers/json")
            containers = result(listing)
            if type(containers) is not list or len(containers) > 128:
                raise _ObservationFailure("invalid running-container inventory")
            ids = []
            for container in containers:
                if type(container) is not dict or container.get("State") not in ("running", "paused", "restarting"):
                    raise _ObservationFailure("unknown running-container state")
                ids.append(_digest(container.get("Id")))
            if len(set(ids)) != len(ids):
                raise _ObservationFailure("duplicate running CID")
            charges = [(cid, pool.submit(get, f"/containers/{cid}/stats?stream=false&one-shot=true", True))
                       for cid in ids]
            total, available = result(vm)
            daemon_info = result(info)
            if type(daemon_info) is not dict or _integer(daemon_info.get("MemTotal"), minimum=1) != total:
                raise _ObservationFailure("VM/daemon total mismatch")
            raw, missing, hard = [], [], []
            for cid, future in charges:
                stats, received = None, False
                try:
                    stats, completed = result(future)
                    received = True
                    if type(stats) is not dict or type(stats.get("memory_stats")) is not dict:
                        raise _ObservationFailure("missing raw memory statistics")
                    if any(key in stats and (type(stats[key]) is not str or stats[key] != cid)
                           for key in ("id", "Id", "ID")):
                        raise _ObservationFailure("contradictory stats identity")
                    charge = _integer(stats["memory_stats"].get("usage"))
                except BaseException as exc:
                    memory = stats.get("memory_stats") if type(stats) is dict else None
                    try:
                        _event(job, "MEMORY_STATS_REJECTED", cid=cid, response_received=received,
                               sample_started=started, stats_rpc_completed_at=completed if received else None,
                               stats_type=_diagnostic_type(stats),
                               memory_stats_present=type(stats) is dict and "memory_stats" in stats,
                               memory_stats_type=_diagnostic_type(memory),
                               usage_present=type(memory) is dict and "usage" in memory,
                               usage_type=_diagnostic_type(memory.get("usage") if type(memory) is dict else None))
                    except BaseException:
                        hard.append(exc)  # A failed rejection write cannot authorize discard.
                    else:
                        if type(exc) is ValueError and type(memory) is dict and "usage" not in memory:
                            missing.append((cid, completed, exc))
                        else:
                            hard.append(exc)
                    continue
                raw.append((cid, charge))
            if hard:
                raise hard[0]
            if sum(v for _, v in raw) > total:
                raise _ObservationFailure("inconsistent raw charged memory")
        finally:
            # Candidate creation also requires every future and HTTP alias gone.
            if owned is None:
                pool.shutdown(wait=True, cancel_futures=False)
            else:
                pool.shutdown(wait=False, cancel_futures=False)
                for thread in tuple(pool._threads):
                    while thread.is_alive() and time.monotonic() < owned.cap():
                        thread.join(timeout=min(0.01, max(0, owned.cap() - time.monotonic())))
                    if thread.is_alive():
                        raise _Failure("cleanup", "metadata executor join unproven")
            if daemon.active or daemon.workers:
                raise _ObservationFailure("metadata HTTP aliases not closed")
        finished = time.monotonic()
        if finished > end:
            raise _ObservationFailure("complete memory sample exceeded four seconds")
        if missing:
            if len(missing) != 1:
                raise _ObservationFailure("multiple missing raw usage observations")
            cid, completed, cause = missing[0]
            raise _MissingRawUsage(cid, started, finished, completed, cause) from cause
        headroom = min(available, total - sum(v for _, v in raw))
        if headroom < 0:
            raise _ObservationFailure("inconsistent raw charged memory")
        sample = {"started": started, "finished": finished, "available": headroom,
                  "vm_total": total, "vm_available": available, "raw_charges": raw,
                  "token": uuid.uuid4().hex, "eligible": True}
        _event(job, "MEMORY_SAMPLE", **sample)
        return sample
    except BaseException as exc:
        if isinstance(exc, (_ObservationFailure, _OwnedCancellation)):
            raise
        raise _ObservationFailure("incomplete/error raw memory observation") from exc


class _Observer:
    def __init__(self, profile, daemon, job):
        self.profile, self.daemon, self.job = profile, daemon, job
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.failure = None
        self.tokens = []
        self.retired = False
        self.state = "ACTIVE"
        self.inflight = False
        self.pending = None
        self.stopped_owned = None
        self.retired_at = None
        self.last_valid = None
        self.token = uuid.uuid4().hex
        _event(job, "OBSERVER_SPAWN_INTENT", token=self.token, guardian=os.getpid())
        self.thread = threading.Thread(target=self._run, name="sql-memory-observer", daemon=False)

    def _run(self):
        while not self.stop.is_set():
            # Reservation and gate closure are atomic under this SAME lock.
            with self.lock:
                reserved = self.state == "ACTIVE" and not self.retired and not self.stop.is_set()
                if reserved:
                    self.inflight = True
            if not reserved:
                self.stop.wait(0.25)
                continue
            try:
                sample = _memory_sample(self.profile, self.daemon, self.job)
                with self.lock:
                    sample["eligible"] = not self.retired and self.failure is None and self.pending is None
                    self.tokens.append(sample)
                    self.latest = sample
            except BaseException as exc:
                with self.lock:
                    if (type(exc) is _MissingRawUsage and self.failure is None and self.pending is None
                            and self.retired and type(self.stopped_owned) is _StoppedOwnedProof):
                        self.pending = exc
                    elif self.failure is None:
                        self.failure = self._ordinary_failure(exc)
                # A failed sample never becomes an eligible cached zero-charge frame.
            finally:
                with self.lock:
                    self.inflight = False
            self.stop.wait(0.25)

    def check(self, *, after=None, admission=False):
        with self.lock:
            if self.state != "ACTIVE" or self.retired or self.pending is not None or self.failure is not None:
                raise _ObservationFailure("observer retired or failed")
            sample = self.latest
            if sample is None or not sample["eligible"]:
                raise _ObservationFailure("missing eligible observer frame")
            if time.monotonic() - sample["finished"] > 4.0:
                raise _ObservationFailure("stale observer frame")
            if after is not None and sample["started"] < after:
                return False
            required = self.profile.admission_bytes if admission else self.profile.reserve_bytes
            if sample["available"] < required:
                raise _Failure("admission" if admission else "memory", "insufficient fresh VM headroom")
            return True

    def begin_quiesce(self):
        with self.lock:
            if self.state != "ACTIVE" or self.retired:
                raise _ObservationFailure("observer cannot quiesce")
            self.state = "QUIESCING"
        _event(self.job, "OBSERVER_QUIESCING", token=self.token)

    def park(self, *, deadline, supervise=None):
        """Drain reserved work fully. Never cancel its futures, CLI or HTTP."""
        while True:
            if supervise is not None:
                supervise()
            if time.monotonic() >= deadline:
                raise _Failure("cleanup", "original shutdown drain deadline")
            with self.lock:
                self._raise_if_failed()
                if self.state != "QUIESCING" or self.retired or self.pending is not None:
                    raise _ObservationFailure("observer cannot park")
                if not self.inflight:
                    if self.daemon.active or getattr(self.daemon, "workers", set()):
                        raise _ObservationFailure("observer aliases remain after drain")
                    self.state = "PARKED"
                    break
            self.stop.wait(min(0.01, max(0, deadline - time.monotonic())))
        self.shutdown_check()
        _event(self.job, "OBSERVER_PARKED", token=self.token)

    def shutdown_check(self):
        """Only shutdown may use the original, unsynthesized parked frame."""
        with self.lock:
            self._raise_if_failed()
            if (self.state != "PARKED" or self.retired or self.inflight or self.pending is not None
                    or self.daemon.active or getattr(self.daemon, "workers", set())):
                raise _ObservationFailure("observer not healthy parked")
            sample = self.latest
            if type(sample) is not dict or sample.get("eligible") is not True:
                raise _ObservationFailure("missing parked observer frame")
            age = time.monotonic() - sample["finished"]
            if not 0 <= age <= 4.0:
                raise _ObservationFailure("stale parked observer frame")
            if sample["available"] < self.profile.reserve_bytes:
                raise _Failure("memory", "insufficient parked VM headroom")
            return sample

    def abort_scheduler(self, *, deadline):
        """Failure-only teardown, NOT retirement/actor-absence evidence."""
        with self.lock:
            if self.state not in ("QUIESCING", "PARKED", "ABORTED") or self.retired:
                raise _Failure("cleanup", "only a closed shutdown gate may be aborted")
            self.state = "ABORTED"
            if self.failure is None:
                self.failure = _ObservationFailure("shutdown abandoned without successful cleanup proof")
            for sample in self.tokens:
                sample["eligible"] = False
            if type(self.latest) is dict:
                self.latest["eligible"] = False
        self.stop.set()
        owned = _owned_context({"nonce": self.job.name})
        if owned is None:
            self.thread.join(timeout=max(0, deadline - time.monotonic()))
        else:
            while self.thread.is_alive() and time.monotonic() < min(deadline, owned.cap()):
                self.thread.join(timeout=min(0.01, max(0, min(deadline, owned.cap()) - time.monotonic())))
        if self.thread.is_alive() or self.inflight or self.daemon.active or getattr(self.daemon, "workers", set()):
            raise _Failure("cleanup", "aborted scheduler aliases remain unresolved")
        # Deliberately no RETIRED, STOPPED, absence or JOIN_ACK event.

    def _raise_if_failed(self):
        if self.failure is not None:
            try:
                _observer_failure_event(self.job, self.failure)
            finally:
                raise _ObservationFailure("failure discovered during observer retirement") from self.failure

    def _ordinary_failure(self, exc):
        if type(exc) is _MissingRawUsage:
            failure = _ObservationFailure("incomplete/error raw memory observation")
            failure.__cause__ = exc.validation_cause
            return failure
        return exc

    def _terminal_discard_allowed(self, journal, deadline):
        candidate, proof, last = self.pending, self.stopped_owned, self.last_valid
        if (type(candidate) is not _MissingRawUsage or type(proof) is not _StoppedOwnedProof
                or type(last) is not dict or self.failure is not None
                or self.thread.is_alive() or self.daemon.active or getattr(self.daemon, "workers", set())):
            return False
        now = time.monotonic()
        times = (candidate.started, candidate.finished, candidate.stats_rpc_completed_at,
                 proof.stopped_at, self.retired_at, last.get("finished"), deadline, now)
        if any(type(t) is not float or not math.isfinite(t) for t in times):
            return False
        digest = hashlib.sha256(canonical_json_bytes(journal["config"])).hexdigest()
        return (
            candidate.cid == proof.cid == journal.get("cid")
            and proof.job == self.job and proof.nonce == journal.get("nonce")
            and proof.config_sha256 == journal.get("config_sha256") == digest
            and proof.guardian == os.getpid() and proof.guardian in journal["guardians"]
            and proof.observer_token == self.token and self.retired
            and candidate.started <= self.retired_at <= candidate.finished <= now
            and 0 <= candidate.finished - candidate.started <= 4.0
            and proof.stopped_at <= self.retired_at
            and candidate.started <= candidate.stats_rpc_completed_at
            and proof.stopped_at <= candidate.stats_rpc_completed_at <= candidate.finished
            and last.get("eligible") is True
            and type(last.get("available")) is int and last["available"] >= self.profile.reserve_bytes
            and 0 <= proof.stopped_at - last["finished"] <= 4.0
            and 0 <= now - proof.stopped_at <= 4.0
            and deadline == journal.get("cleanup_deadline") and now < deadline)

    def retire(self, deadline=None, *, stopped_owned=None):
        with self.lock:
            self.last_valid = dict(self.latest) if type(self.latest) is dict and self.latest.get("eligible") is True else None
            self.stopped_owned = stopped_owned
            self.retired_at = time.monotonic()
            self.retired = True
            self.state = "RETIRED"
            for sample in self.tokens:
                sample["eligible"] = False
            if type(self.latest) is dict:
                self.latest["eligible"] = False
        event_error = None
        try:
            _event(self.job, "OBSERVER_RETIRED")
        except BaseException as exc:
            event_error = exc
        self.stop.set()
        owned = _owned_context({"nonce": self.job.name})
        if owned is None:
            self.thread.join(timeout=max(0, min(4.5, deadline - time.monotonic())) if deadline is not None else 4.5)
        else:
            end = min(owned.cap(), deadline if deadline is not None else owned.cap())
            while self.thread.is_alive() and time.monotonic() < min(end, owned.cap()):
                self.thread.join(timeout=min(0.01, max(0, min(end, owned.cap()) - time.monotonic())))
        if self.thread.is_alive() or self.daemon.active or getattr(self.daemon, "workers", set()):
            raise _Failure("cleanup", "observer/CLI/HTTP join not acknowledged")
        if event_error is not None:
            self._raise_if_failed()
            raise event_error
        _event(self.job, "OBSERVER_THREAD_JOINED", token=self.token, guardian=os.getpid())
        self._raise_if_failed()
        journal = _metadata(_read_owned(self.job / "journal.json"))
        _prove_actor_absence(self.job, journal)
        if self.pending is not None:
            try:
                if not self._terminal_discard_allowed(journal, deadline):
                    raise _ObservationFailure("terminal stopped proof refused")
                _event(self.job, "MEMORY_TERMINAL_DISCARDED", cid=self.pending.cid,
                       started=self.pending.started, finished=self.pending.finished,
                       stats_rpc_completed_at=self.pending.stats_rpc_completed_at,
                       stopped_at=self.stopped_owned.stopped_at, retired_at=self.retired_at)
                if not self._terminal_discard_allowed(journal, deadline):
                    raise _ObservationFailure("terminal stopped proof expired")
            except BaseException:
                if self.failure is None:
                    self.failure = self._ordinary_failure(self.pending)
                self._raise_if_failed()
        _event(self.job, "OBSERVER_JOIN_ACK", samples=len(self.tokens), failed=False)


def _prove_actor_absence(job, journal):
    """No process scans/signals. Interrupted registration is explicitly unresolved."""
    if journal.get("actors_initialized") is not True:
        raise _Failure("cleanup", "missing durable actor manifest")
    events = [_metadata(line) for line in _read_owned(job / "events.jsonl").splitlines()]
    initialized = [e for e in events if e.get("kind") == "ACTORS_INITIALIZED"]
    if len(initialized) != 1 or initialized[0].get("nonce") != journal["nonce"]:
        raise _Failure("cleanup", "actor manifest initialization unproven")
    intents = [e for e in events if e.get("kind") in ("CLI_SPAWN_INTENT", "OBSERVER_SPAWN_INTENT")]
    tokens = [e.get("token") for e in intents]
    if any(type(t) is not str for t in tokens) or len(set(tokens)) != len(tokens):
        raise _Failure("cleanup", "ambiguous actor intent identity")
    for record in events:
        if record.get("kind") in ("CLI_STARTED", "CLI_JOIN_ACK", "OBSERVER_THREAD_JOINED"):
            if record.get("token") not in tokens:
                raise _Failure("cleanup", "actor record without durable spawn intent")
    reaped = {e["pid"] for e in events if e.get("kind") == "GUARDIAN_REAPED" and type(e.get("pid")) is int}
    for intent in events:
        kind, token = intent.get("kind"), intent.get("token")
        if kind not in ("CLI_SPAWN_INTENT", "OBSERVER_SPAWN_INTENT"):
            continue
        guardian = intent.get("guardian")
        if type(token) is not str or type(guardian) is not int or guardian not in journal["guardians"]:
            raise _Failure("cleanup", "unknown actor spawn identity")
        records = [e for e in events if e.get("token") == token]
        if kind == "OBSERVER_SPAWN_INTENT":
            joined = any(e.get("kind") == "OBSERVER_THREAD_JOINED" and e.get("guardian") == guardian for e in records)
            if not joined and guardian not in reaped:
                raise _Failure("cleanup", "observer thread termination unproven")
        else:
            started = [e for e in records if e.get("kind") == "CLI_STARTED"]
            joined = [e for e in records if e.get("kind") == "CLI_JOIN_ACK"]
            if len(started) != 1 or len(joined) != 1:
                raise _Failure("cleanup", "CLI spawn/registration/join completion unproven")
            pid = started[0].get("pid")
            if type(pid) is not int or pid <= 0 or joined[0].get("pid") != pid or (
                    started[0].get("guardian") != guardian or joined[0].get("guardian") != guardian or
                    joined[0].get("reaped") is not True or type(joined[0].get("returncode")) is not int):
                raise _Failure("cleanup", "CLI reaping identity unproven")
    _event(job, "ACTOR_ABSENCE_PROOF")


def _save_journal(job, journal):
    _write_owned(job / "journal.json", canonical_json_bytes(journal) + b"\n")


def _inspect(daemon, journal):
    if journal["cid"] is None:
        return None
    try:
        obj = daemon.call("GET", f"/containers/{journal['cid']}/json")
    except _HTTPFailure as exc:
        if exc.status == 404:
            return None
        raise
    return _verify_owned(obj, journal)


def _locate_created(daemon, journal):
    """Guardian-only lost-CREATE reconciliation, unique nonce AND name."""
    from urllib.parse import quote
    filters = quote(canonical_json_bytes({"label": [_OWNER_LABEL + "=" + journal["nonce"]]}).decode(),
                    safe="")
    items = daemon.call("GET", "/containers/json?all=1&filters=" + filters)
    if type(items) is not list or len(items) > 1:
        raise _Failure("cleanup", "ambiguous lost-create ownership")
    if not items:
        raise _Failure("cleanup", "attempted CREATE has unproven completion despite empty inventory")
    journal["cid"] = _digest(items[0].get("Id"))
    obj = _inspect(daemon, journal)
    if obj is None or obj.get("Name") != "/" + journal["name"]:
        raise _Failure("cleanup", "lost-create identity mismatch")
    return obj


def _controller_alive(fd):
    with _OWNED_CONTEXT_LOCK:
        owned = _OWNED_CONTROLS.get(fd)
    if owned is not None:
        owned.checkpoint()
    ready, _, _ = select.select([fd], [], [], 0)
    if ready:
        data = os.read(fd, 64)
        if not data:
            raise _Failure("transport", "controller pipe EOF")
        raise _Failure("protocol", "unexpected controller control bytes")


def _image_preflight(daemon):
    # The two approved digests form one reviewed content-addressed manifest/config
    # pair. Docker stores may report either descriptor as their local image ID.
    image = daemon.call("GET", "/images/sha256:" + IMAGE_MANIFEST_SHA256 + "/json")
    if type(image) is not dict or image.get("Os") != "linux" or image.get("Architecture") != "arm64":
        raise _Failure("binding", "local image/platform missing or incorrect")
    if image.get("Id") not in ("sha256:" + IMAGE_CONFIG_SHA256, "sha256:" + IMAGE_MANIFEST_SHA256):
        raise _Failure("binding", "local image descriptor is not the approved pair")
    digest = "@" + "sha256:" + IMAGE_MANIFEST_SHA256
    if not any(type(d) is str and d.endswith(digest) for d in image.get("RepoDigests", [])):
        raise _Failure("binding", "approved local manifest not present; never pull")


def _shutdown_check(control, observer, journal, *, parked=True):
    _controller_alive(control)
    if time.monotonic() >= journal["deadline"]:
        raise _Failure("deadline", "original role deadline during shutdown")
    _cleanup_remaining(journal)
    if not observer.thread.is_alive():
        raise _ObservationFailure("observer thread absent before STOPPED")
    return observer.shutdown_check() if parked else None


def _grant_exit(profile, daemon, journal, job, control, observer, attached, request, result_wire):
    # Durable original cleanup trigger precedes gate closure/drain.
    _begin_cleanup(journal)
    journal["shutdown_requested"] = True
    _save_journal(job, journal)
    daemon.cleanup_deadline = journal["cleanup_deadline"]
    _shutdown_check(control, observer, journal, parked=False)
    observer.begin_quiesce()
    observer.park(deadline=min(journal["deadline"], journal["cleanup_deadline"]),
                  supervise=lambda: _shutdown_check(control, observer, journal, parked=False))
    daemon.shutdown_supervision = lambda: _shutdown_check(control, observer, journal)
    frame = _shutdown_check(control, observer, journal)
    obj = _inspect(daemon, journal)
    _shutdown_check(control, observer, journal)
    state = obj.get("State") if type(obj) is dict else None
    if type(state) is dict and (state.get("OOMKilled") is True or state.get("ExitCode") == 70):
        raise _Failure("memory", "guest OOM/allocation failure before grant")
    if (type(state) is not dict or state.get("Running") is not True
            or state.get("Paused") is not False or state.get("Restarting") is not False
            or type(state.get("Pid")) is not int or state["Pid"] <= 0):
        raise _Failure("protocol", "guest did not hold owned running state for grant")
    config_sha = hashlib.sha256(canonical_json_bytes(journal["config"])).hexdigest()
    if (journal.get("config_sha256") != config_sha or observer.job != job or observer.profile is not profile
            or journal["config"]["Labels"].get(_OWNER_LABEL) != journal["nonce"]
            or os.getpid() not in journal["guardians"]):
        raise _Failure("binding", "grant ownership/configuration mismatch")
    result_sha = hashlib.sha256(result_wire).hexdigest()
    grant = encode_wire_message(journal["role"], "exit_grant", ExitGrant(result_sha),
                                request_sha256=journal["request_sha256"])
    bounded_bytes(request + grant, maximum=limits_for(journal["role"]).input_bytes)
    if "exit_grant_intent" in journal:
        raise _Failure("protocol", "exit grant cannot be retried")
    intent = {"cid": journal["cid"], "config_sha256": config_sha,
              "observer_token": observer.token, "request_sha256": journal["request_sha256"],
              "result_sha256": result_sha, "last_frame_finished": frame["finished"],
              "deadline": min(frame["finished"] + 4.0, journal["deadline"], journal["cleanup_deadline"])}
    journal["exit_grant_intent"] = intent
    _save_journal(job, journal)
    _event(job, "EXIT_GRANT_INTENT", **intent)
    _shutdown_check(control, observer, journal)
    attached.settimeout(min(0.1, max(0.001, intent["deadline"] - time.monotonic())))
    try:
        attached.sendall(grant)  # Exactly one attempt, uncertain partial delivery never retries.
    except BaseException as exc:
        raise _RPCUncertain("transport", "exit grant delivery uncertain") from exc
    _shutdown_check(control, observer, journal)
    attached.settimeout(0.1)
    _event(job, "EXIT_GRANT_SENT", cid=journal["cid"], result_sha256=result_sha)
    _shutdown_check(control, observer, journal)


def _stream_result(profile, daemon, journal, job, control, observer, attached):
    role = journal["role"]
    limits = limits_for(role)
    mux = _MuxDecoder(stdout_limit=limits.stdout_bytes, stderr_limit=limits.stderr_bytes)
    output = bytearray()
    stderr = bytearray()
    bootstrap = None
    result = None
    result_wire = None
    granted = False
    ready = False
    request = _read_owned(job / "request.wire")
    while True:
        _controller_alive(control)
        if time.monotonic() >= journal["deadline"]:
            raise _Failure("deadline", "original whole-role deadline")
        if granted:
            _shutdown_check(control, observer, journal)
        else:
            observer.check()
        try:
            raw = attached.recv(65536)
        except socket.timeout:
            continue
        if not raw:
            break
        for stream, data in mux.feed(raw):
            if stream == 2:
                stderr.extend(data)
                continue
            if result is not None:
                raise _Failure("protocol", "unsolicited output after result")
            output.extend(data)
            if not ready:
                if not READY.startswith(bytes(output[:len(READY)])):
                    raise _Failure("protocol", "READY mismatch")
                if len(output) < len(READY):
                    continue
                del output[:len(READY)]
                ready = True
            if bootstrap is None and b"\n" in output:
                index = output.index(b"\n") + 1
                wire = bytes(output[:index]); del output[:index]
                if output:
                    raise _Failure("protocol", "unsolicited pre-approval output")
                message = decode_wire_message(wire, role=role, kind="bootstrap", request_sha256=None)
                expected = getattr(profile.binding, role)
                bootstrap = message.payload
                if bootstrap.sources != expected.sources or bootstrap.db_sha256 != journal["db_sha256"]:
                    raise _Failure("binding", "guest source/database mismatch")
                if bootstrap.python_version != dict(profile.environment)["PYTHON_VERSION"]:
                    raise _Failure("binding", "guest Python does not match approved image")
                journal["bootstrap"] = _plain(bootstrap)
                journal["bootstrap_sha256"] = hashlib.sha256(wire).hexdigest()
                _save_journal(job, journal)
                if _owned_context(journal) is None:
                    attached.settimeout(min(3.0, max(0.001, journal["deadline"] - time.monotonic())))
                    attached.sendall(request)
                else:
                    _owned_send_request(attached, request, control, journal)
                attached.settimeout(0.1)
                _event(job, "REQUEST_DELIVERED", request_sha256=journal["request_sha256"])
            elif bootstrap is not None and b"\n" in output:
                wire = bytes(output)
                try:
                    result = decode_wire_message(wire, role=role, kind="result",
                                                 request_sha256=journal["request_sha256"]).payload
                except (TypeError, ValueError) as exc:
                    raise _Failure("protocol", "invalid result frame") from exc
                result_wire = wire
                output.clear()
        if result is not None and not granted and not mux.buffer and not mux.remaining:
            _grant_exit(profile, daemon, journal, job, control, observer, attached, request, result_wire)
            granted = True
    if not granted:
        # Allocation failure need not produce a provisional result. Preserve
        # reserved exit-70/OOM semantics without accepting autonomous success.
        obj = _inspect(daemon, journal)
        state = obj.get("State") if type(obj) is dict else None
        if type(state) is dict and (state.get("OOMKilled") is True or state.get("ExitCode") == 70):
            raise _Failure("memory", "guest OOM/allocation failure")
        raise _RPCUncertain("protocol", "guest exited without coordinated exit grant")
    _shutdown_check(control, observer, journal)
    journal["stdout_bytes"], journal["stderr_bytes"] = mux.counts[1], mux.counts[2]
    _write_owned(job / "stderr.bin", bytes(stderr))
    _save_journal(job, journal)
    obj = _inspect(daemon, journal)
    _shutdown_check(control, observer, journal)
    if obj is None:
        raise _Failure("cleanup", "owned object disappeared")
    state = obj["State"]
    if state.get("OOMKilled") is True or state.get("ExitCode") == 70:
        raise _Failure("memory", "guest OOM/allocation failure")
    if not _stopped_state(state):
        raise _Failure("protocol", "EOF before proven owned stop")
    if (type(state.get("ExitCode")) is not int or state["ExitCode"] != 0
            or state.get("OOMKilled") is not False or result is None or output or mux.buffer or mux.remaining):
        raise _Failure("protocol", "incomplete result or unsuccessful guest exit")
    return result


def _cleanup_owned(profile, daemon, journal, job, observer):
    stopped_owned = None
    success_candidate = bool(journal.get("shutdown_requested") and
                             getattr(daemon, "shutdown_supervision", None) is not None)
    success_error = None
    def success_phase():
        nonlocal success_error
        if success_candidate:
            try:
                _success_remaining(journal)
            except _Failure as exc:
                if success_error is None:
                    success_error = exc
    _begin_cleanup(journal)
    daemon.cleanup_deadline = journal["cleanup_deadline"]
    _save_journal(job, journal)
    _cleanup_remaining(journal)
    obj = _inspect(daemon, journal)
    if obj is None and journal["cid"] is None and journal["create_attempted"]:
        obj = _locate_created(daemon, journal)
        _save_journal(job, journal)
    if journal["cid"] is not None and obj is None:
        raise _Failure("cleanup", "unexplained owned disappearance before stop proof")
    if obj is not None:
        coordinated = journal.get("shutdown_requested") and getattr(daemon, "shutdown_supervision", None) is not None
        if coordinated:
            state = obj.get("State")
            if (not _stopped_state(state) or type(state.get("ExitCode")) is not int
                    or state["ExitCode"] != 0 or state.get("OOMKilled") is not False):
                raise _Failure("cleanup", "coordinated shutdown lost successful stopped proof")
        elif journal["kill_attempted"]:
            # A surviving replacement guardian may observe, but never repeat KILL.
            if not _stopped_state(obj.get("State")):
                raise _Failure("cleanup", "previous KILL uncertain; no second attempt")
        else:
            journal["kill_attempted"] = True
            _save_journal(job, journal)
            _event(job, "KILL_ATTEMPT", cid=journal["cid"])
            try:
                daemon.call("POST", f"/containers/{journal['cid']}/kill?signal=SIGKILL", statuses=(204,))
            except _HTTPFailure as exc:
                if exc.status != 409:
                    raise
                obj = _inspect(daemon, journal)
                if obj is None or not _stopped_state(obj.get("State")):
                    raise _Failure("cleanup", "409 without fresh exact owned stopped proof")
                _event(job, "KILL409_STOPPED_PROOF", cid=journal["cid"])
        obj = _inspect(daemon, journal)
        if obj is None or not _stopped_state(obj.get("State")):
            raise _Failure("cleanup", "owned stop not positively proven")
        _cleanup_remaining(journal)
        stopped_at = time.monotonic()
        if (type(observer) is _Observer and observer.job == job and observer.profile is profile
                and obj["State"].get("Status") in ("created", "exited")
                and not daemon.active and not getattr(daemon, "workers", set())
                and journal.get("config_sha256") == hashlib.sha256(canonical_json_bytes(journal["config"])).hexdigest()
                and journal["config"]["Labels"].get(_OWNER_LABEL) == journal["nonce"]
                and os.getpid() in journal["guardians"]):
            stopped_owned = _StoppedOwnedProof(journal["cid"], job, journal["nonce"],
                journal["config_sha256"], os.getpid(), observer.token, stopped_at)
        _event(job, "STOPPED", cid=journal["cid"], stopped_at=stopped_at)
        shutdown = getattr(daemon, "shutdown_supervision", None)
        if shutdown is not None:
            shutdown()
            daemon.shutdown_supervision = None
    success_phase()
    if observer is not None:
        if type(observer) is _Observer:
            observer.retire(deadline=journal["cleanup_deadline"], stopped_owned=stopped_owned)
        else:
            observer.retire(deadline=journal["cleanup_deadline"])
    else:
        _prove_actor_absence(job, journal)
        _event(job, "OBSERVER_JOIN_ACK", samples=0, failed=False, actor_absence_proven=True)
    _cleanup_remaining(journal)
    success_phase()
    # No sampler, CLI, future or metadata alias exists across DELETE.
    if obj is not None:
        if daemon.active or getattr(daemon, "workers", set()):
            raise _Failure("cleanup", "HTTP aliases active before delete")
        success_phase()
        daemon.call("DELETE", f"/containers/{journal['cid']}?force=false&v=false", statuses=(204,))
        success_phase()
        _event(job, "DELETE", cid=journal["cid"])
        if _inspect(daemon, journal) is not None:
            raise _Failure("cleanup", "owned object still present")
        success_phase()
        _event(job, "ABSENCE", cid=journal["cid"])
    _cleanup_remaining(journal)
    success_phase()
    journal["cleanup_elapsed"] = time.monotonic() - journal["cleanup_trigger"]
    if success_error is not None:
        raise success_error


def _begin_cleanup(journal):
    if "cleanup_deadline" not in journal:
        journal["cleanup_trigger"] = time.monotonic()
        journal["cleanup_deadline"] = journal["cleanup_trigger"] + 12.0
    elif "cleanup_trigger" not in journal:
        # Also supports a scaled, pre-seeded private test budget.
        journal["cleanup_trigger"] = min(time.monotonic(), journal["cleanup_deadline"])
    owned = _owned_context(journal)
    if owned is not None:
        owned.begin_cleanup()


def _cleanup_remaining(journal):
    owned = _owned_context(journal)
    end = journal["cleanup_deadline"]
    if owned is not None:
        end = min(end, owned.cap())
    if time.monotonic() >= end:
        raise _Failure("cleanup", "original absolute cleanup deadline exhausted")


def _success_remaining(journal):
    """Success eligibility, never authorization to skip necessary failure cleanup."""
    _cleanup_remaining(journal)
    if time.monotonic() >= journal["deadline"]:
        raise _Failure("deadline", "original role deadline through successful completion")


def _final_start_checks(control, observer, fresh_after, journal):
    _controller_alive(control)
    observer.check(after=fresh_after, admission=True)
    if time.monotonic() >= journal["deadline"]:
        raise _Failure("deadline", "original deadline immediately before START")


_PENDING_FIELDS = ("job", "nonce", "role", "profile_sha256", "request_sha256",
                   "journal_sha256", "outcome_sha256", "guardian_pid", "finalization_token",
                   "role_deadline", "cleanup_trigger", "cleanup_deadline")
_ACK_FIELDS = ("format", "schema_version", "pending_sha256", "guardian_pid",
               "finalization_token", "release_verified_at")


def _publish_immutable(path, data):
    """Same-directory complete staging + fsync + NOOVERWRITE link + dir fsync.

    Only the private staging name may be removed. A visible destination remains
    a barrier even if publication/directory fsync subsequently raises.
    """
    parent, name = _open_parent(path)
    tmp = "." + name + "." + uuid.uuid4().hex
    created = False
    try:
        _owned_stat(os.fstat(parent), directory=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        created = True
        try:
            _owned_stat(os.fstat(fd))
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError("short immutable record write")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(tmp, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(tmp, dir_fd=parent)
        created = False
        os.fsync(parent)
    finally:
        try:
            if created:
                os.unlink(tmp, dir_fd=parent)
        finally:
            os.close(parent)


def _finalization_record(kind, payload):
    return canonical_json_bytes({
        "format": "sql_pilot_finalization_" + kind, "schema_version": 1,
        "payload": payload, "sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    }) + b"\n"


def _finalization_time(value):
    if type(value) is int:
        return _integer(value)
    if type(value) is not float or not math.isfinite(value) or value < 0:
        raise ValueError("finite finalization time required, not bool")
    return value


def _finalization_nonce(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None:
        raise ValueError("invalid finalization nonce")
    return value


def _finalization_token(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{32}", value) is None:
        raise ValueError("invalid finalization attempt token")
    return value


def _read_finalization_record(raw, kind):
    record = _closed(_json_line(raw, maximum=16384), ("format", "schema_version", "payload", "sha256"))
    _version(record["schema_version"])
    if record["format"] != "sql_pilot_finalization_" + kind:
        raise ValueError("finalization record format mismatch")
    payload = _closed(record["payload"], _PENDING_FIELDS if kind == "pending" else
                      ("pending_sha256", "terminal_ack"))
    if _digest(record["sha256"]) != hashlib.sha256(canonical_json_bytes(payload)).hexdigest():
        raise ValueError("finalization envelope digest mismatch")
    if kind == "pending":
        job = _text(payload["job"], nonempty=True, maximum=4096)
        if not Path(job).is_absolute() or str(Path(job)) != job or ".." in Path(job).parts:
            raise ValueError("canonical absolute finalization job required")
        _finalization_nonce(payload["nonce"])
        _choice(payload["role"], ("program", "scorer"))
        for key in ("profile_sha256", "request_sha256", "journal_sha256", "outcome_sha256"):
            _digest(payload[key])
        _integer(payload["guardian_pid"], minimum=1)
        _finalization_token(payload["finalization_token"])
        for key in ("role_deadline", "cleanup_trigger", "cleanup_deadline"):
            _finalization_time(payload[key])
        if not 0 <= payload["cleanup_deadline"] - payload["cleanup_trigger"] <= 12:
            raise ValueError("original finalization cleanup budget invalid")
    else:
        _digest(payload["pending_sha256"])
        _parse_terminal_ack(canonical_json_bytes(payload["terminal_ack"]) + b"\n")
    return payload


def _parse_terminal_ack(raw):
    ack = _closed(_json_line(raw, maximum=4096), _ACK_FIELDS)
    _version(ack["schema_version"])
    if ack["format"] != "sql_pilot_finalization_ack":
        raise ValueError("terminal finalization ACK format mismatch")
    _digest(ack["pending_sha256"])
    _integer(ack["guardian_pid"], minimum=1)
    _finalization_token(ack["finalization_token"])
    _finalization_time(ack["release_verified_at"])
    return ack


def _shared_names(profile):
    parent, _ = _open_parent(profile.shared_state_dir / "entry")
    try:
        _owned_stat(os.fstat(parent), directory=True)
        if os.fstat(parent).st_mode & 0o022:
            raise ValueError("unsafe finalization shared directory")
        with os.scandir(parent) as entries:
            return {entry.name for entry in entries}
    finally:
        os.close(parent)


def _finalization_remaining(journal, outcome, *, suppress_outcome=False):
    _cleanup_remaining(journal)
    if outcome.abort is None and not suppress_outcome:
        _success_remaining(journal)


def _validate_finalization(profile, pending_raw, ack, *, job=None, guardian_pid=None,
                           current=False, allow_active=False, suppress_outcome=False):
    """One validator for current-pipe commit and historical admission.

    Historical checks bind release time to original budgets, not today's clock.
    They cannot resurrect an outcome: only _receive_terminal_ack authorizes a
    current invocation to call _commit_finalization.
    """
    pending = _read_finalization_record(pending_raw, "pending")
    ack = _parse_terminal_ack(canonical_json_bytes(ack) + b"\n")
    if (ack["pending_sha256"] != hashlib.sha256(pending_raw).hexdigest()
            or ack["guardian_pid"] != pending["guardian_pid"]
            or ack["finalization_token"] != pending["finalization_token"]):
        raise ValueError("finalization ACK/pending binding mismatch")
    if job is not None and str(job) != pending["job"]:
        raise ValueError("finalization current job mismatch")
    if guardian_pid is not None and ack["guardian_pid"] != guardian_pid:
        raise ValueError("finalization current guardian PID mismatch")
    job = Path(pending["job"])
    artifacts = {}
    for name, field in (("profile.json", "profile_sha256"), ("journal.json", "journal_sha256"),
                        ("outcome.json", "outcome_sha256")):
        raw = _read_owned(job / name)
        if hashlib.sha256(raw).hexdigest() != pending[field]:
            raise ValueError("finalization artifact digest mismatch")
        artifacts[name] = raw
    historical_profile = execution_profile_from_bytes(artifacts["profile.json"])
    if historical_profile.shared_state_dir != profile.shared_state_dir:
        raise ValueError("finalization shared namespace mismatch")
    if current and execution_profile_canonical_bytes(profile) != artifacts["profile.json"]:
        raise ValueError("finalization current profile mismatch")
    journal = _metadata(artifacts["journal.json"])
    if type(journal) is not dict:
        raise ValueError("finalization journal object required")
    if (journal.get("state") != "CLOSED" or journal.get("nonce") != pending["nonce"]
            or journal.get("role") != pending["role"] or journal.get("profile_sha256") != pending["profile_sha256"]
            or journal.get("request_sha256") != pending["request_sha256"]
            or journal.get("deadline") != pending["role_deadline"]
            or journal.get("cleanup_trigger") != pending["cleanup_trigger"]
            or journal.get("cleanup_deadline") != pending["cleanup_deadline"]):
        raise ValueError("finalization journal context mismatch")
    # Equality alone would accept True as 1. Validate original types as well.
    for key in ("deadline", "cleanup_trigger", "cleanup_deadline"):
        _finalization_time(journal[key])
    guardians = journal.get("guardians")
    if (type(guardians) is not list or not guardians or guardians[-1] != ack["guardian_pid"]
            or any(type(pid) is not int or pid < 1 for pid in guardians)):
        raise ValueError("finalization journal guardian mismatch")
    controller_pid = _integer(journal.get("controller"), minimum=1)
    if current and controller_pid != os.getpid() and guardian_pid != os.getpid():
        raise ValueError("finalization current controller mismatch")
    wire = decode_wire_message(_read_owned(job / "request.wire"), role=pending["role"],
                               kind="request", request_sha256=pending["request_sha256"])
    if request_sha256(wire.payload) != pending["request_sha256"]:
        raise ValueError("finalization request binding mismatch")
    outcome_data = _metadata(artifacts["outcome.json"])
    outcome = (program_outcome_from_dict(outcome_data) if pending["role"] == "program"
               else score_outcome_from_dict(outcome_data))
    receipt = outcome.receipt
    bootstrap = journal.get("bootstrap")
    if bootstrap is not None and type(bootstrap) is not dict:
        raise ValueError("finalization bootstrap object required")
    if bootstrap is None:
        if receipt is not None:
            raise ValueError("finalization receipt without bootstrap")
    elif (receipt is None or receipt.role != pending["role"]
          or receipt.request_sha256 != pending["request_sha256"]
          or receipt.journal_sha256 != pending["journal_sha256"]
          or receipt.bootstrap_sha256 != journal.get("bootstrap_sha256")
          or receipt.python_version != bootstrap.get("python_version")
          or receipt.sqlite_version != bootstrap.get("sqlite_version")):
        raise ValueError("finalization receipt binding mismatch")
    if (outcome.abort is None) != ("failure" not in journal):
        raise ValueError("finalization typed outcome/failure mismatch")
    if outcome.abort is not None and (type(journal["failure"]) is not dict
                                     or outcome.abort.reason != journal["failure"].get("reason")):
        raise ValueError("finalization typed abort reason mismatch")
    if "owned_cleanup_evidence" in journal:
        _check_owned_cleanup_evidence(job, journal)
    end = min(pending["cleanup_deadline"], pending["role_deadline"]) if outcome.abort is None else pending["cleanup_deadline"]
    if not pending["cleanup_trigger"] <= ack["release_verified_at"] < end:
        raise ValueError("finalization release outside original deadlines")
    names = _shared_names(profile)
    if "UNRESOLVED-" + pending["nonce"] + ".json" in names:
        raise _Failure("cleanup", "finalization has unresolved block")
    if "active.json" in names:
        if not allow_active:
            raise _Failure("cleanup", "finalization active reservation remains")
        active = _closed(_metadata(_read_owned(profile.shared_state_dir / "active.json")), ("nonce", "job"))
        if active != {"nonce": pending["nonce"], "job": str(job)}:
            raise _Failure("cleanup", "finalization reservation conflict")
    elif allow_active:
        raise _Failure("cleanup", "finalization reservation disappeared before unlink")
    if current:
        _finalization_remaining(journal, outcome, suppress_outcome=suppress_outcome)
        if ack["release_verified_at"] > time.monotonic():
            raise ValueError("finalization release timestamp in future")
    return pending, journal, outcome


def _refsync_owned(path):
    """Later admission reestablishes durability, never edits a marker."""
    parent, name = _open_parent(path)
    try:
        fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            _owned_stat(os.fstat(fd))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def _admit_finalizations(profile):
    """Must run under the shared lock, before ANY new reservation/daemon IO."""
    try:
        names = _shared_names(profile)
        if "active.json" in names:
            raise ValueError("active reservation")
        for name in names:
            if name.startswith("UNRESOLVED-") and name.endswith(".json"):
                closed = "CLOSED-" + name
                if closed not in names:
                    raise ValueError("unclosed block")
                _read_owned(profile.shared_state_dir / name)
                _read_owned(profile.shared_state_dir / closed)
            if name.startswith(".FINALIZATION-"):
                raise ValueError("partial finalization publication")
            if name.startswith("FINALIZATION-") and not (
                    name.startswith("FINALIZATION-PENDING-") or name.startswith("FINALIZATION-COMMITTED-")):
                raise ValueError("unknown finalization marker")
        pending_names = {n for n in names if n.startswith("FINALIZATION-PENDING-")}
        committed_names = {n for n in names if n.startswith("FINALIZATION-COMMITTED-")}
        for name in pending_names:
            nonce = _finalization_nonce(name.removeprefix("FINALIZATION-PENDING-").removesuffix(".json"))
            if name != "FINALIZATION-PENDING-" + nonce + ".json":
                raise ValueError("malformed pending filename")
            commit_name = "FINALIZATION-COMMITTED-" + nonce + ".json"
            raw = _read_owned(profile.shared_state_dir / name, maximum=16384)
            pending = _read_finalization_record(raw, "pending")
            if pending["nonce"] != nonce:
                raise ValueError("pending filename binding mismatch")
            commit = _read_finalization_record(_read_owned(profile.shared_state_dir / commit_name, maximum=16384), "committed")
            if commit["pending_sha256"] != hashlib.sha256(raw).hexdigest():
                raise ValueError("committed pending digest mismatch")
            _validate_finalization(profile, raw, commit["terminal_ack"])
            _refsync_owned(profile.shared_state_dir / name)
            _refsync_owned(profile.shared_state_dir / commit_name)
            committed_names.discard(commit_name)
        if committed_names:
            raise ValueError("committed record without pending")
    except (OSError, ValueError, TypeError, KeyError, RecursionError, _Failure) as exc:
        raise _Failure("admission", "finalization/reservation admission blocked") from exc


def _close_reservation(profile, journal, job, check=None):
    if check is None:
        raise _Failure("cleanup", "durable finalization pending required for release")
    check()
    active = profile.shared_state_dir / "active.json"
    record = _metadata(_read_owned(active))
    if record.get("nonce") != journal["nonce"] or record.get("job") != str(job):
        raise _Failure("cleanup", "global reservation changed")
    _append_owned(profile.shared_state_dir / "history.jsonl",
                  {"kind": "CLOSED", "nonce": journal["nonce"], "job": str(job),
                   "journal_sha256": hashlib.sha256(_read_owned(job / "journal.json")).hexdigest(),
                   "at": time.monotonic()})
    parent, name = _open_parent(active)
    try:
        check()
        os.unlink(name, dir_fd=parent); os.fsync(parent)
    finally:
        os.close(parent)


def _publish_finalization(profile, journal, job, journal_raw, outcome_raw, control):
    """Guardian transaction. Return ACK data only after positive release fsync."""
    outcome_data = _metadata(outcome_raw)
    outcome = (program_outcome_from_dict(outcome_data) if journal["role"] == "program"
               else score_outcome_from_dict(outcome_data))
    def live():
        _controller_alive(control)
        _finalization_remaining(journal, outcome)
    live()
    pending = {
        "job": str(job), "nonce": journal["nonce"], "role": journal["role"],
        "profile_sha256": journal["profile_sha256"], "request_sha256": journal["request_sha256"],
        "journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
        "outcome_sha256": hashlib.sha256(outcome_raw).hexdigest(), "guardian_pid": os.getpid(),
        "finalization_token": uuid.uuid4().hex, "role_deadline": journal["deadline"],
        "cleanup_trigger": journal["cleanup_trigger"], "cleanup_deadline": journal["cleanup_deadline"]
    }
    pending_raw = _finalization_record("pending", pending)
    _read_finalization_record(pending_raw, "pending")
    _publish_immutable(profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json"), pending_raw)
    live()
    _write_owned(job / "journal.json", journal_raw)
    _write_owned(job / "outcome.json", outcome_raw)
    ack = {"format": "sql_pilot_finalization_ack", "schema_version": 1,
           "pending_sha256": hashlib.sha256(pending_raw).hexdigest(), "guardian_pid": os.getpid(),
           "finalization_token": pending["finalization_token"], "release_verified_at": time.monotonic()}
    def check():
        live()
        actual = _read_owned(profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json"))
        if actual != pending_raw:
            raise ValueError("finalization pending changed before release")
        _validate_finalization(profile, actual, ack, job=job, guardian_pid=os.getpid(),
                               current=True, allow_active=True)
    _close_reservation(profile, journal, job, check)
    live()  # Crucially AFTER release-directory fsync.
    ack["release_verified_at"] = time.monotonic()
    _validate_finalization(profile, _read_owned(profile.shared_state_dir / (
        "FINALIZATION-PENDING-" + journal["nonce"] + ".json")), ack,
        job=job, guardian_pid=os.getpid(), current=True)
    live()
    return ack


def _send_terminal_ack(stream, ack):
    data = canonical_json_bytes(ack) + b"\n"
    _parse_terminal_ack(data)
    if stream.write(data) != len(data):
        raise _Failure("transport", "terminal finalization ACK short write")
    stream.flush()


def _latch_finalization_cleanup(journal, latest):
    if type(latest) is not dict:
        raise ValueError("finalization journal object required")
    if "cleanup_deadline" in latest or "cleanup_trigger" in latest:
        if "cleanup_deadline" not in latest or "cleanup_trigger" not in latest:
            raise _Failure("cleanup", "original finalization cleanup budget incomplete")
        for key in ("cleanup_trigger", "cleanup_deadline"):
            _finalization_time(latest[key])
            if key in journal and journal[key] != latest[key]:
                raise _Failure("cleanup", "original finalization cleanup budget changed")
        if not 0 <= latest["cleanup_deadline"] - latest["cleanup_trigger"] <= 12:
            raise _Failure("cleanup", "original finalization cleanup budget invalid")
        journal.setdefault("cleanup_trigger", latest["cleanup_trigger"])
        journal.setdefault("cleanup_deadline", latest["cleanup_deadline"])
    elif "cleanup_deadline" in journal:
        raise _Failure("cleanup", "original finalization cleanup budget disappeared")


def _receive_terminal_ack(process, journal, job):
    """Bounded incremental current-pipe read. Never wait/kill on outcome files."""
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    data = bytearray()
    while True:
        _latch_finalization_cleanup(journal, _metadata(_read_owned(job / "journal.json")))
        end = min(journal["deadline"] + 12, journal.get("cleanup_deadline", journal["deadline"] + 12))
        try:
            provisional = _metadata(_read_owned(job / "outcome.json"))
        except FileNotFoundError:
            provisional = None
        if provisional is not None:
            typed = (program_outcome_from_dict(provisional) if journal["role"] == "program"
                     else score_outcome_from_dict(provisional))
            if typed.abort is None:
                end = min(end, journal["deadline"])
        _finalization_time(end)
        if time.monotonic() >= end:
            raise _Failure("cleanup", "original finalization ACK deadline exhausted")
        ready, _, _ = select.select([fd], [], [], min(0.02, max(0, end - time.monotonic())))
        if ready:
            try:
                chunk = os.read(fd, 4097 - len(data))
            except BlockingIOError:
                continue
            if not chunk:
                raise _Failure("cleanup", "guardian EOF before terminal finalization ACK")
            data.extend(chunk)
            if len(data) > 4096:
                raise _Failure("protocol", "terminal finalization ACK exceeds 4096 bytes")
            if b"\n" in data:
                _parse_terminal_ack(bytes(data))
                try:
                    extra = os.read(fd, 1)
                except BlockingIOError:
                    extra = b""
                if extra:
                    raise _Failure("protocol", "duplicate terminal finalization ACK/output")
                # ACK may arrive after a RESERVED snapshot taken before select.
                # Capture the now-durable original cleanup pair, never synthesize.
                _latch_finalization_cleanup(journal, _metadata(_read_owned(job / "journal.json")))
                if "cleanup_deadline" not in journal:
                    raise _Failure("cleanup", "terminal ACK without original cleanup budget")
                return bytes(data)
        # poll() alone is not evidence. Drain an exited child's remaining pipe.
        if process.poll() is not None and not ready:
            if select.select([fd], [], [], 0)[0]:
                continue
            raise _Failure("cleanup", "guardian died without terminal finalization ACK")


def _commit_finalization(profile, job, journal, guardian_pid, frame, *, suppress_outcome=False):
    ack = _parse_terminal_ack(frame)
    pending_path = profile.shared_state_dir / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json")
    pending_raw = _read_owned(pending_path, maximum=16384)
    pending, latest, outcome = _validate_finalization(profile, pending_raw, ack, job=job,
                                                     guardian_pid=guardian_pid, current=True,
                                                     suppress_outcome=suppress_outcome)
    if (pending["nonce"] != journal["nonce"] or pending["role"] != journal["role"]
            or pending["request_sha256"] != journal["request_sha256"]
            or pending["profile_sha256"] != journal["profile_sha256"]
            or pending["role_deadline"] != journal["deadline"]
            or pending["cleanup_trigger"] != journal["cleanup_trigger"]
            or pending["cleanup_deadline"] != journal["cleanup_deadline"]):
        raise ValueError("finalization invocation context mismatch")
    _finalization_remaining(latest, outcome, suppress_outcome=suppress_outcome)
    _publish_immutable(profile.shared_state_dir / ("FINALIZATION-COMMITTED-" + journal["nonce"] + ".json"),
                       _finalization_record("committed", {"pending_sha256": ack["pending_sha256"], "terminal_ack": ack}))
    _finalization_remaining(latest, outcome, suppress_outcome=suppress_outcome)
    return outcome


def _finish_finalization(process, profile, job, journal):
    frame = _receive_terminal_ack(process, journal, job)
    outcome = _commit_finalization(profile, job, journal, process.pid, frame)
    # Reap hygiene is authorized ONLY after a received ACK + durable COMMITTED.
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired as exc:
            raise _Failure("cleanup", "post-ACK guardian reap not acknowledged") from exc
    # Also refuse output arriving after the first frame while reaping. No
    # unbounded drain and no waiting for EOF from a pre-ACK live guardian.
    try:
        extra = os.read(process.stdout.fileno(), 1)
    except BlockingIOError:
        extra = b""
    if extra:
        raise _Failure("protocol", "duplicate terminal finalization ACK/output")
    _finalization_remaining(_metadata(_read_owned(job / "journal.json")), outcome)
    return outcome


@dataclass(frozen=True, slots=True)
class _FinalizationSuccess:
    ack: dict
    outcome: ProgramOutcome | ScoreOutcome


def _block(profile, journal, job, detail):
    journal["state"] = "UNRESOLVED"
    journal["block_reason"] = detail
    save_error = None
    try:
        _save_journal(job, journal)
    except BaseException as exc:
        save_error = exc
    # The original block is immutable and is never rewritten by reconciliation.
    path = profile.shared_state_dir / ("UNRESOLVED-" + journal["nonce"] + ".json")
    if not path.exists():
        _write_owned(path, canonical_json_bytes({
            "nonce": journal["nonce"], "job": str(job), "cid": journal["cid"],
            "reason": detail, "journal_sha256": hashlib.sha256(_read_owned(job / "journal.json")).hexdigest()
        }) + b"\n")
    if save_error is not None:
        raise save_error


def _complete_guardian(profile, daemon, journal, job, observer, attached, failure, uncertain, result):
    """Cleanup is reachable even when every failure-report write keeps failing."""
    _begin_cleanup(journal)
    if failure is not None:
        daemon.shutdown_supervision = None
        journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
    try:
        _save_journal(job, journal)
    except BaseException as exc:
        uncertain = True
        failure = failure or _Failure("cleanup", "journal persistence failed: " + type(exc).__name__)
        daemon.shutdown_supervision = None
    try:
        if attached is not None:
            attached.close()
    except BaseException as exc:
        uncertain = True
        failure = failure or _Failure("cleanup", "attach close failed: " + type(exc).__name__)
        daemon.shutdown_supervision = None
    try:
        _cleanup_owned(profile, daemon, journal, job, observer)
        owned = _owned_context(journal)
        if owned is not None:
            _owned_cleanup_evidence(owned, observer)
            protocol_failure = owned.protocol_failure()
            if protocol_failure is not None:
                failure = protocol_failure
                journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
                daemon.shutdown_supervision = None
        if failure is None and journal.get("shutdown_requested"):
            _success_remaining(journal)
    except BaseException as exc:
        uncertain = True
        failure = failure or (exc if isinstance(exc, _Failure) else
                              _Failure("cleanup", type(exc).__name__))

    def retain_unresolved():
        owned = _owned_context(journal)
        try:
            if owned is not None and owned.published:
                # A visible PENDING binds the exact journal bytes. Preserve
                # that history, recording live incompleteness separately.
                _publish_immutable(
                    profile.shared_state_dir / ("UNRESOLVED-" + journal["nonce"] + ".json"),
                    canonical_json_bytes({
                        "nonce": journal["nonce"], "job": str(job), "cid": journal["cid"],
                        "reason": "cleanup",
                        "journal_sha256": hashlib.sha256(_read_owned(job / "journal.json")).hexdigest()
                    }) + b"\n")
            else:
                journal["state"] = "UNRESOLVED"
                if failure is not None:
                    journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
                _block(profile, journal, job, str(failure))
        except BaseException:
            # Active OR the immutable PENDING blocks admission even if every
            # subsequent report write fails after successful active unlink.
            pass
        if (journal.get("shutdown_requested") and observer is not None and not observer.retired
                and getattr(observer, "state", None) in ("QUIESCING", "PARKED", "ABORTED")):
            try:
                observer.abort_scheduler(deadline=journal["cleanup_deadline"])
            except BaseException:
                # No absence/retirement claim. Unknown aliases remain unresolved.
                pass

    if uncertain:
        retain_unresolved()
        if (observer is not None and not observer.retired
                and getattr(observer, "state", "ACTIVE") == "ACTIVE"):
            # Preserve active-observer mitigation/lock for unknown guest liveness.
            while True:
                observer.stop.wait(1.0)
        return None  # Uncertain aborts never publish a completion transaction.
    try:
        journal["state"] = "CLOSED"
        owned = _owned_context(journal)
        published_monitor_error = None
        if owned is not None:
            # Freeze metadata with the journal bytes, never rewrite history
            # when a later notification tightens the independent live cap.
            with owned.lock:
                owned.begin_cleanup()
                protocol_failure = owned.protocol_failure()
                if protocol_failure is not None:
                    failure = protocol_failure
                    journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
                    published_monitor_error = owned.error
                owned.published = True
        journal_raw = canonical_json_bytes(journal) + b"\n"
        receipt = None
        if journal.get("bootstrap") is not None:
            boot = journal["bootstrap"]
            receipt = RuntimeReceipt(journal["role"], journal["request_sha256"], boot["python_version"],
                                     boot["sqlite_version"], journal["bootstrap_sha256"],
                                     hashlib.sha256(journal_raw).hexdigest())
        if failure is not None:
            outcome = (ProgramOutcome(None, AbortInfo("program", failure.reason), receipt)
                       if journal["role"] == "program" else ScoreOutcome(None, AbortInfo("scorer", failure.reason), receipt))
        elif journal["role"] == "program":
            outcome = ProgramOutcome(result.observation, None, receipt, rejected=result.rejected)
        else:
            outcome = ScoreOutcome(result, None, receipt)
        ack = _publish_finalization(profile, journal, job, journal_raw,
                                    canonical_json_bytes(outcome) + b"\n", daemon.control)
        if owned is not None and published_monitor_error is not None:
            with owned.lock:
                owned.accounted_error = published_monitor_error
    except BaseException as exc:
        failure = failure or (exc if isinstance(exc, _Failure) else _Failure("cleanup", type(exc).__name__))
        retain_unresolved()
        return None
    return _FinalizationSuccess(ack, outcome)


def _completed_outcome_ready(profile, journal, outcome):
    """Evidence query only. Never authorizes adoption/current-pipe completion."""
    if journal.get("state") != "CLOSED":
        raise _Failure("cleanup", "provisional completion is not CLOSED")
    if journal.get("nonce") is not None and (
            profile.shared_state_dir / ("UNRESOLVED-" + journal["nonce"] + ".json")).exists():
        raise _Failure("cleanup", "provisional completion has an unresolved block")
    _finalization_remaining(journal, outcome)
    name = journal["nonce"]
    try:
        raw = _read_owned(profile.shared_state_dir / ("FINALIZATION-PENDING-" + name + ".json"))
        commit = _read_finalization_record(_read_owned(profile.shared_state_dir / (
            "FINALIZATION-COMMITTED-" + name + ".json")), "committed")
    except FileNotFoundError:
        return False
    if commit["pending_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("finalization committed digest mismatch")
    _validate_finalization(profile, raw, commit["terminal_ack"], current=True)
    return True


def _guardian(job: Path, control: int, emergency: bool, *, cancel_fd=None):
    journal = _metadata(_read_owned(job / "journal.json"))
    profile_raw = _read_owned(job / "profile.json")
    profile = execution_profile_from_bytes(profile_raw)
    if hashlib.sha256(profile_raw).hexdigest() != journal["profile_sha256"]:
        raise ValueError("guardian profile mismatch")
    if journal["config_sha256"] != hashlib.sha256(canonical_json_bytes(journal["config"])).hexdigest():
        raise ValueError("guardian configuration mismatch")
    _activate_staged_import_root(job, profile)
    build_execution_binding(profile, source_root=installed_source_root())
    owned = None
    if cancel_fd is not None:
        owned = _OwnedContext(job, control, cancel_fd, journal)
        owned.bridge = _owned_boundary_io(profile, job)
        owned.monitor.start()
        while not owned.ready.wait(0.01):
            if time.monotonic() >= min(journal["deadline"], owned.cap()):
                raise _Failure("cleanup", "cancellation monitor startup unproven")
    journal["guardians"].append(os.getpid())
    _save_journal(job, journal)
    _event(job, "GUARDIAN_ACK", pid=os.getpid(), emergency=emergency)
    sys.stdout.buffer.write(b"ACK\n"); sys.stdout.buffer.flush()
    if owned is None and os.read(control, 1) != b"G":
        emergency = True
    daemon = _Daemon(profile) if owned is None else owned.daemon(profile)
    daemon.operation_deadline = journal["deadline"]
    daemon.control = control
    observer = None
    attached = None
    failure = _Failure("transport", "original guardian died") if emergency else None
    result = None
    uncertain = False
    try:
        if owned is not None:
            # Monitor is registered and running before the startup grant.
            while not select.select([control], [], [], 0.01)[0]:
                owned.checkpoint()
                if time.monotonic() >= (owned.cap() if emergency else journal["deadline"]):
                    raise _Failure("deadline", "owned startup grant deadline")
            if os.read(control, 1) != b"G":
                raise _Failure("transport", "owned startup grant lost")
            owned.checkpoint()
        if not emergency:
            _controller_alive(control)
            _image_preflight(daemon)
            sample = _memory_sample(profile, daemon, job)
            if sample["available"] < profile.admission_bytes:
                raise _Failure("admission", "insufficient admission headroom")
            journal["create_attempted"] = True
            _save_journal(job, journal)
            _event(job, "CREATE_ATTEMPT")
            _controller_alive(control)
            response = daemon.call("POST", "/containers/create?name=" + journal["name"],
                                   journal["config"], statuses=(201,))
            journal["cid"] = _digest(response.get("Id"))
            _save_journal(job, journal)
            obj = _inspect(daemon, journal)
            if obj is None:
                raise _Failure("binding", "created object missing")
            journal["effective_config_sha256"] = hashlib.sha256(
                canonical_json_bytes({"Config": obj["Config"], "HostConfig": obj["HostConfig"],
                                      "Mounts": obj["Mounts"], "Image": obj["Image"]})).hexdigest()
            _save_journal(job, journal)
            attached = daemon.attach(journal["cid"])
            fresh_after = time.monotonic()
            observer_daemon = (_Daemon(profile) if owned is None else
                               owned.daemon(profile, observation=True))
            observer = _Observer(profile, observer_daemon, job)
            observer.thread.start()
            while True:
                _controller_alive(control)
                if time.monotonic() >= journal["deadline"]:
                    raise _Failure("deadline", "original pre-START deadline")
                with observer.lock:
                    has_sample = observer.latest is not None
                    error = observer.failure
                if error is not None:
                    raise _ObservationFailure("pre-START observer failed")
                if has_sample and observer.check(after=fresh_after, admission=True):
                    break
                observer.stop.wait(0.01)
            _controller_alive(control)
            observer.check(after=fresh_after, admission=True)
            if time.monotonic() >= journal["deadline"]:
                raise _Failure("deadline", "original deadline before START")
            journal["start_attempted"] = True
            _save_journal(job, journal)
            _event(job, "START_ATTEMPT", original_deadline=journal["deadline"])
            _final_start_checks(control, observer, fresh_after, journal)
            daemon.observer = observer
            daemon.call("POST", f"/containers/{journal['cid']}/start", statuses=(204,))
            result = _stream_result(profile, daemon, journal, job, control, observer, attached)
    except BaseException as exc:
        _begin_cleanup(journal)
        failure = exc if isinstance(exc, _Failure) else _Failure("transport", type(exc).__name__)
        uncertain = bool(journal.get("shutdown_requested")) or isinstance(
            exc, (_ObservationFailure, _HTTPFailure, _RPCUncertain, OSError, TimeoutError))
        daemon.shutdown_supervision = None  # Failure cleanup must still stop OWN.
        journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
    finally:
        finalization = _complete_guardian(profile, daemon, journal, job, observer, attached, failure, uncertain, result)
    if type(finalization) is not _FinalizationSuccess:
        raise _Failure("cleanup", "guardian finalization uncommitted")
    _controller_alive(control)
    _finalization_remaining(journal, finalization.outcome)
    if owned is not None:
        owned.retire()
    _send_terminal_ack(sys.stdout.buffer, finalization.ack)
    # Terminal ACK is the last completion action. No journal/event/block writes.


def _runtime_abort(role, reason):
    return (ProgramOutcome(None, AbortInfo(role, reason), None) if role == "program"
            else ScoreOutcome(None, AbortInfo(role, reason), None))


def _run_isolated(executor, role, request, db_path):
    profile = executor.profile
    lock_fd = None
    read_control = write_control = None
    process = None
    log = None
    job = None
    try:
        # Reject invalid/incomplete source bindings before any daemon IO/state IO.
        binding = build_execution_binding(profile, source_root=installed_source_root())
        if {p.path for p in binding.program.sources} != set(_PROGRAM_PATHS) or (
                {p.path for p in binding.scorer.sources} != set(_SCORER_PATHS)):
            return _runtime_abort(role, "binding")
        wire = encode_wire_message(role, "request", request)
        _secure_directory(executor.state_dir)
        _secure_directory(profile.shared_state_dir)
        lock_fd = os.open(profile.shared_state_dir / "lock",
                          os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        _owned_stat(os.fstat(lock_fd))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return _runtime_abort(role, "admission")
        _admit_finalizations(profile)
        nonce = uuid.uuid4().hex
        job = executor.state_dir / nonce
        _secure_directory(job)
        _stage_sources(profile, job)
        _stage_database(db_path, request.db_sha256, job)
        raw_profile = execution_profile_canonical_bytes(profile)
        _write_owned(job / "profile.json", raw_profile, mode=0o400)
        _write_owned(job / "request.wire", wire, mode=0o400)
        config = _container_config(profile, role, job, nonce)
        journal = {"nonce": nonce, "name": "co-train-sql-" + nonce, "role": role, "cid": None,
                   "config": config, "config_sha256": hashlib.sha256(canonical_json_bytes(config)).hexdigest(),
                   "binding": execution_binding_to_dict(binding), "profile_sha256": hashlib.sha256(raw_profile).hexdigest(),
                   "request_sha256": request_sha256(request), "db_sha256": request.db_sha256,
                   "controller": os.getpid(), "guardians": [], "bootstrap": None,
                   "actors_initialized": True,
                   "create_attempted": False, "start_attempted": False, "kill_attempted": False,
                   "deadline": time.monotonic() + limits_for(role).deadline_ms / 1000,
                   "state": "RESERVED"}
        _save_journal(job, journal)
        _event(job, "ACTORS_INITIALIZED", nonce=nonce)
        _write_owned(profile.shared_state_dir / "active.json",
                     canonical_json_bytes({"nonce": nonce, "job": str(job)}) + b"\n")
        _event(job, "RESERVATION_DURABLE", deadline=journal["deadline"])
        read_control, write_control = os.pipe()
        log = open(job / "guardian.log", "xb", buffering=0)
        def spawn(emergency):
            child = subprocess.Popen(
                [sys.executable, "-I", "-B", str(job / "controller/ptc/sql_isolation.py"),
                 "--guardian", str(job), str(read_control), "emergency" if emergency else "normal"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
                pass_fds=(read_control, lock_fd), close_fds=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"})
            until = min(journal["deadline"] + 12, time.monotonic() + 4.0)
            while time.monotonic() < until:
                if child.poll() is not None:
                    raise _Failure("transport", "guardian died before ACK")
                ready, _, _ = select.select([child.stdout], [], [], 0.05)
                if ready:
                    if child.stdout.readline(5) != b"ACK\n":
                        raise _Failure("protocol", "guardian ACK mismatch")
                    os.write(write_control, b"G")
                    return child
            raise _Failure("transport", "guardian ACK deadline")
        process = spawn(False)
        replaced = False
        while True:
            try:
                return _finish_finalization(process, profile, job, journal)
            except _Failure:
                if process.poll() is None:
                    raise
                latest = _metadata(_read_owned(job / "journal.json"))
                names = _shared_names(profile)
                # Never adopt/retry/release a pending transaction, including a
                # failed COMMITTED fsync whose destination became visible.
                if (replaced or latest.get("state") in ("CLOSED", "UNRESOLVED")
                        or time.monotonic() >= min(journal["deadline"] + 12,
                            journal.get("cleanup_deadline", journal["deadline"] + 12))
                        or any(name.startswith((
                            "FINALIZATION-PENDING-" + latest["nonce"] + ".json",
                            "FINALIZATION-COMMITTED-" + latest["nonce"] + ".json",
                            ".FINALIZATION-PENDING-" + latest["nonce"] + ".json",
                            ".FINALIZATION-COMMITTED-" + latest["nonce"] + ".json")) for name in names)
                        or "UNRESOLVED-" + latest["nonce"] + ".json" in names
                        or (job / "outcome.json").exists()):
                    raise
                process.wait()
                _event(job, "GUARDIAN_REAPED", pid=process.pid, returncode=process.returncode)
                process.stdout.close()
                replaced = True
                _begin_cleanup(latest)
                _save_journal(job, latest)
                process = spawn(True)
    except (TypeError, ValueError, OSError, KeyError, RecursionError) as exc:
        if job is not None:
            try:
                journal = _metadata(_read_owned(job / "journal.json"))
                _block(profile, journal, job, type(exc).__name__)
            except (OSError, _Failure, TypeError, ValueError, KeyError, RecursionError):
                pass  # Active or immutable PENDING remains the admission barrier.
        return _runtime_abort(role, "binding" if process is None else "transport")
    except _Failure as exc:
        if job is not None:
            try:
                journal = _metadata(_read_owned(job / "journal.json"))
                _block(profile, journal, job, str(exc))
            except (OSError, _Failure, TypeError, ValueError, KeyError, RecursionError):
                pass
        return _runtime_abort(role, exc.reason)
    finally:
        if write_control is not None:
            os.close(write_control)
        if read_control is not None:
            os.close(read_control)
        if process is not None and process.poll() is not None and process.stdout is not None:
            process.stdout.close()
        if log is not None:
            log.close()
        if lock_fd is not None:
            os.close(lock_fd)


_T = TypeVar("_T")
_CANCEL_NS = 12_000_000_000
_CANCEL_FRAME = struct.Struct(">8s16sQQ")
_UINT64_MAX = (1 << 64) - 1


def _cancel_identity(value):
    if type(value) is not uuid.UUID or value.int == 0:
        raise ValueError("non-nil invocation UUID required")


def _cancel_times(requested, deadline):
    if (type(requested) is not int or type(deadline) is not int
            or not 0 <= requested <= _UINT64_MAX - _CANCEL_NS
            or deadline != requested + _CANCEL_NS):
        raise ValueError("invalid absolute cancellation budget")


@dataclass(frozen=True, slots=True)
class CancelIntent:
    invocation_id: uuid.UUID
    reason: Literal["caller_cancelled", "runner_closed"]
    requested_ns: int
    deadline_ns: int

    def __post_init__(self):
        _cancel_identity(self.invocation_id)
        _choice(self.reason, ("caller_cancelled", "runner_closed"))
        _cancel_times(self.requested_ns, self.deadline_ns)


@dataclass(frozen=True, slots=True)
class CancelReceipt:
    status: Literal["accepted", "repeated", "already_completed"]
    intent: CancelIntent | None

    def __post_init__(self):
        _choice(self.status, ("accepted", "repeated", "already_completed"))
        if (self.status == "already_completed") != (self.intent is None):
            raise ValueError("cancellation receipt branch mismatch")
        if self.intent is not None and type(self.intent) is not CancelIntent:
            raise TypeError("concrete cancellation intent required")


@dataclass(frozen=True, slots=True)
class OutcomeAbort:
    invocation_id: uuid.UUID
    role: Role
    kind: Literal["cancelled", "infrastructure"]
    detail_code: str

    def __post_init__(self):
        _cancel_identity(self.invocation_id)
        _choice(self.role, ("program", "scorer"))
        _choice(self.kind, ("cancelled", "infrastructure"))
        _text(self.detail_code, nonempty=True, maximum=128)


class _AckAuthority:
    def __init__(self, owner):
        self.owner = owner
        self.issuing = False
        self.ack = None


@dataclass(frozen=True, slots=True)
class CleanupCompleteAck:
    invocation_id: uuid.UUID
    role: Role
    request_sha256: str
    profile_sha256: str
    not_started: bool
    released: bool
    cleanup_trigger_ns: int
    cleanup_deadline_ns: int
    completed_ns: int
    terminal_ack_sha256: str | None
    guardian_reaps: tuple[tuple[int, int], ...] = ()
    child_waits: bool = False
    thread_joins: bool = False
    _authority: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        authority = self._authority
        if (type(authority) is not _AckAuthority or not authority.issuing
                or authority.ack is not None):
            raise ValueError("only the live invocation owner may issue cleanup ACK")
        owner = authority.owner
        if (self.invocation_id != owner.invocation_id or self.role != owner.role
                or self.request_sha256 != owner.request_digest
                or self.profile_sha256 != owner.profile_digest or self.released is not True
                or type(self.not_started) is not bool
                or not 0 <= self.cleanup_trigger_ns <= self.completed_ns <= self.cleanup_deadline_ns):
            raise ValueError("cleanup ACK ownership/budget mismatch")
        if self.not_started:
            if self.terminal_ack_sha256 is not None or self.guardian_reaps:
                raise ValueError("not-started ACK cannot contain terminal evidence")
        elif (not self.guardian_reaps or not self.child_waits or not self.thread_joins
              or self.terminal_ack_sha256 is None):
            raise ValueError("started ACK requires actual reap/join evidence")


@dataclass(frozen=True, slots=True)
class InvocationCompletion(Generic[_T]):
    outcome: _T | None
    abort: OutcomeAbort | None
    cleanup_ack: CleanupCompleteAck

    def __post_init__(self):
        if (self.outcome is None) == (self.abort is None):
            raise ValueError("exactly one outcome/abort required")
        ack = self.cleanup_ack
        if (type(ack) is not CleanupCompleteAck
                or type(ack._authority) is not _AckAuthority or ack._authority.ack is not ack):
            raise ValueError("live-owner cleanup ACK required")
        if self.abort is not None and (
                type(self.abort) is not OutcomeAbort
                or self.abort.invocation_id != ack.invocation_id or self.abort.role != ack.role):
            raise ValueError("abort/cleanup identity mismatch")
        if self.outcome is not None:
            expected = ProgramOutcome if ack.role == "program" else ScoreOutcome
            if (type(self.outcome) is not expected or self.outcome.abort is not None
                    or ack._authority.owner._intent is not None):
                raise ValueError("usable outcome branch mismatch")
            self.outcome.__post_init__()
            if self.outcome.receipt.request_sha256 != ack.request_sha256:
                raise ValueError("outcome request/cleanup mismatch")


@dataclass(frozen=True, slots=True)
class InvocationSnapshot:
    state: str
    invocation_id: uuid.UUID
    role: Role
    request_sha256: str
    profile_sha256: str
    intent: CancelIntent | None
    incomplete: bool


def _encode_cancel_frame(intent: CancelIntent) -> bytes:
    if type(intent) is not CancelIntent:
        raise ValueError("concrete cancellation intent required")
    intent.__post_init__()
    return _CANCEL_FRAME.pack(b"SQLCNL01", intent.invocation_id.bytes,
                              intent.requested_ns, intent.deadline_ns)


def _decode_cancel_frame(data: bytes, *, invocation_id: uuid.UUID,
                         now_ns: int) -> tuple[int, int]:
    _cancel_identity(invocation_id)
    if (type(data) is not bytes or len(data) != _CANCEL_FRAME.size
            or type(now_ns) is not int or now_ns < 0):
        raise ValueError("invalid cancellation frame")
    magic, identity, requested, deadline = _CANCEL_FRAME.unpack(data)
    if magic != b"SQLCNL01" or identity != invocation_id.bytes:
        raise ValueError("cancellation frame identity mismatch")
    _cancel_times(requested, deadline)
    if requested > now_ns:
        raise ValueError("future cancellation timestamp")
    return requested, deadline


def _acquire_cancel_frame(fd, identity, end):
    """Sole-reader acquisition, including an oversize sentinel byte."""
    end = min(end, time.monotonic() + 0.1)
    data = bytearray()
    os.set_blocking(fd, False)
    while True:
        try:
            chunk = os.read(fd, 41 - len(data))
        except BlockingIOError:
            chunk = None
        if chunk == b"":
            raise _Failure("protocol", "cancellation notification EOF")
        if chunk is not None:
            data.extend(chunk)
            if len(data) > 40:
                raise _Failure("protocol", "oversize cancellation notification")
            if len(data) == 40:
                try:
                    extra = os.read(fd, 1)
                except BlockingIOError:
                    extra = b""
                if extra:
                    raise _Failure("protocol", "extra cancellation notification")
                try:
                    return _decode_cancel_frame(bytes(data), invocation_id=identity,
                                                now_ns=time.monotonic_ns())
                except ValueError as exc:
                    raise _Failure("protocol", "invalid cancellation notification") from exc
        if time.monotonic() >= end:
            raise _Failure("protocol", "partial cancellation notification")
        select.select([fd], [], [], min(0.01, max(0, end - time.monotonic())))


class _CancelEndpoint:
    """All access, including close, is serialized by the owner's lifetime lock."""
    def __init__(self, fd):
        self.fd = fd
        self.sent = False
        self.unavailable = False
        os.set_blocking(fd, False)
        if os.fpathconf(fd, "PC_PIPE_BUF") < _CANCEL_FRAME.size:
            raise _Failure("protocol", "cancellation pipe atomicity unavailable")

    def deliver(self, intent):
        if self.fd is None or self.sent:
            return
        self.sent = True  # Exactly one attempt, never replay a partial write.
        try:
            if os.write(self.fd, _encode_cancel_frame(intent)) != 40:
                self.unavailable = True
        except OSError:
            self.unavailable = True

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


class _CreatorPopen(subprocess.Popen):
    """Retain the actual object even if BasePopen construction/publication fails."""
    def __init__(self, *args, _registry, **kwargs):
        self._creator_lock = threading.RLock()
        self._creator_reaped = False
        self._creator_waited = False
        self._creator_ambiguous = False
        _registry.append(self)
        try:
            super().__init__(*args, **kwargs)
        except BaseException:
            self._creator_ambiguous = getattr(self, "pid", None) is None
            raise

    def wait(self, timeout=None):
        with self._creator_lock:
            try:
                result = super().wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                raise
            except BaseException:
                self._creator_ambiguous = True
                raise
            self._creator_reaped = True
            self._creator_waited = True
            return result

    def poll(self):
        with self._creator_lock:
            result = super().poll()
            if result is not None:
                self._creator_reaped = True
            return result

    def kill(self):
        with self._creator_lock:
            if self._creator_reaped or self._creator_ambiguous:
                raise _Failure("cleanup", "creator signal authority retired")
            return super().kill()

    def send_signal(self, sig):
        with self._creator_lock:
            if self._creator_reaped or self._creator_ambiguous:
                raise _Failure("cleanup", "creator signal authority retired")
            return super().send_signal(sig)

    def terminate(self):
        with self._creator_lock:
            if self._creator_reaped or self._creator_ambiguous:
                raise _Failure("cleanup", "creator signal authority retired")
            return super().terminate()


_OWNED_CONTEXT_LOCK = threading.RLock()
_OWNED_CONTEXTS = {}
_OWNED_CONTROLS = {}


class _OwnedCancellation(_Failure):
    def __init__(self):
        super().__init__("transport", "owned invocation cancellation")


def _owned_context(journal):
    with _OWNED_CONTEXT_LOCK:
        return _OWNED_CONTEXTS.get(journal.get("nonce"))


class _OwnedContext:
    """Guardian-wide locked latch. Only monitor consumes its notification FD."""
    def __init__(self, job, control, cancel_fd, journal):
        self.job, self.control, self.cancel_fd = job, control, cancel_fd
        self.identity = uuid.UUID(hex=journal["nonce"])
        _cancel_identity(self.identity)
        self.journal = journal
        self.lock = threading.RLock()
        self.times = None
        self.error = None
        self.accounted_error = None
        self.cleaning = False
        self.published = False
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.children = []
        self.daemons = []
        self.executors = []
        self.bridge = None
        self.monitor = threading.Thread(target=self._monitor, name="sql-cancel-monitor", daemon=False)
        with _OWNED_CONTEXT_LOCK:
            _OWNED_CONTEXTS[journal["nonce"]] = self
            _OWNED_CONTROLS[control] = self

    def daemon(self, profile, *, observation=False):
        daemon = self.bridge.daemon(profile)
        daemon._owned = self
        daemon._owned_observation = observation
        with self.lock:
            self.daemons.append(daemon)
        return daemon

    def _monitor(self):
        try:
            first = True
            while True:
                if select.select([self.cancel_fd], [], [],
                                 0 if first or self.stop.is_set() else 0.01)[0]:
                    if self.times is not None:
                        if os.read(self.cancel_fd, 1):
                            raise _Failure("protocol", "extra cancellation notification")
                        raise _Failure("protocol", "cancellation notification EOF")
                    end = self.cap() if self.cleaning else min(self.cap(), self.journal["deadline"])
                    times = _acquire_cancel_frame(self.cancel_fd, self.identity, end)
                    with self.lock:
                        self.times = times
                    self.ready.set()
                    first = False
                    continue
                self.ready.set()
                first = False
                if self.stop.is_set():
                    return
        except BaseException as exc:
            with self.lock:
                self.error = exc
        finally:
            self.ready.set()

    def cap(self):
        with self.lock:
            end = min(self.journal["deadline"] + 12,
                      self.journal.get("cleanup_deadline", self.journal["deadline"] + 12))
            if self.times is not None:
                end = min(end, self.times[1] / 1e9)
            return end

    def checkpoint(self):
        with self.lock:
            if self.cleaning:
                return
            if self.error is not None:
                raise _Failure("protocol", "cancellation monitor protocol failure")
            if self.times is not None:
                raise _OwnedCancellation()

    def protocol_failure(self):
        with self.lock:
            if self.error is not None:
                return _Failure("protocol", "cancellation monitor protocol failure")
        return None

    def begin_cleanup(self):
        with self.lock:
            self.cleaning = True
            if not self.published and self.times is not None:
                self.journal["cleanup_trigger"] = min(
                    self.journal["cleanup_trigger"], self.times[0] / 1e9)
                self.journal["cleanup_deadline"] = self.cap()
            elif not self.published:
                self.journal["cleanup_deadline"] = self.cap()

    def retire(self):
        self.stop.set()
        while self.monitor.is_alive() and time.monotonic() < self.cap():
            self.monitor.join(timeout=min(0.01, max(0, self.cap() - time.monotonic())))
        if self.monitor.is_alive():
            raise _Failure("cleanup", "cancellation monitor did not join")
        for child in self.children:
            if not child._creator_waited or child._creator_ambiguous:
                raise _Failure("cleanup", "creator CLI wait absent")
        for daemon in self.daemons:
            if daemon.active or daemon.workers:
                raise _Failure("cleanup", "owned RPC actors remain")
        for pool in self.executors:
            if any(thread.is_alive() for thread in tuple(pool._threads)):
                raise _Failure("cleanup", "owned metadata executor remains")
        if time.monotonic() >= self.cap():
            raise _Failure("cleanup", "owned retirement budget exhausted")
        os.close(self.cancel_fd)
        with _OWNED_CONTEXT_LOCK:
            _OWNED_CONTROLS.pop(self.control, None)
            _OWNED_CONTEXTS.pop(self.identity.hex, None)
        failure = self.protocol_failure()
        if failure is not None and self.error is not self.accounted_error:
            raise failure


class _OwnedBoundaryIO:
    """Private first-party fixture seam, not a profile/backend selector.

    A fresh fake guardian may substitute this object. daemon(profile) must
    implement the existing call/attach contract and active/workers manifests.
    vm_command(profile) supplies argv/env for the actual creator-owned CLI.
    Canonical observer, stream, cleanup and finalization are not substituted.
    """
    def daemon(self, profile):
        return _Daemon(profile)

    def vm_command(self, profile):
        return ([str(profile.observer.binary), "--profile", "default", "ssh", "--",
                 "cat", "/proc/meminfo"],
                {"HOME": pwd.getpwuid(os.getuid()).pw_dir,
                 "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "LANG": "C.UTF-8"})


def _owned_boundary_io(profile, job):
    return _OwnedBoundaryIO()


def _owned_wait(process, cap):
    """Actual creator wait, with a live cap that can tighten during the wait."""
    while True:
        remaining = cap() - time.monotonic()
        if remaining <= 0:
            raise _Failure("cleanup", "actual creator wait budget exhausted")
        try:
            return process.wait(timeout=min(0.01, remaining))
        except subprocess.TimeoutExpired:
            continue


def _owned_vm_memory(profile, job, deadline, owned):
    """Actual creator handles, including failed constructor/publication handles."""
    end = min(deadline, time.monotonic() + 2, owned.cap())
    token = uuid.uuid4().hex
    _event(job, "CLI_SPAWN_INTENT", token=token, guardian=os.getpid(),
           binary_sha256=profile.observer.binary_sha256)
    process = None
    start = len(owned.children)
    started_record = False
    try:
        argv, env = owned.bridge.vm_command(profile)
        process = _CreatorPopen(
            argv, _registry=owned.children, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, env=env)
        _event(job, "CLI_STARTED", token=token, pid=process.pid, guardian=os.getpid())
        started_record = True
        while True:
            remaining = min(end, owned.cap()) - time.monotonic()
            if remaining <= 0:
                raise _ObservationFailure("VM observer absolute deadline")
            try:
                output, error = process.communicate(timeout=min(0.01, remaining))
                _owned_wait(process, owned.cap)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode != 0 or len(output) > 65536 or len(error) > 65536:
            raise _ObservationFailure("VM observer failed")
        values = {}
        for line in output.decode("ascii", "strict").splitlines():
            parts = line.split()
            if parts and parts[0] in ("MemTotal:", "MemAvailable:"):
                if len(parts) != 3 or parts[2] != "kB" or parts[0] in values:
                    raise _ObservationFailure("invalid VM memory fields")
                values[parts[0]] = _integer(int(parts[1]), minimum=1) * 1024
        if (set(values) != {"MemTotal:", "MemAvailable:"}
                or values["MemAvailable:"] > values["MemTotal:"]):
            raise _ObservationFailure("missing or inconsistent VM memory")
        return values["MemTotal:"], values["MemAvailable:"]
    finally:
        # Constructor may have created a child before raising: local assignment
        # is not ownership. The pre-Base registry is authoritative here.
        created = owned.children[start:]
        for child in created:
            if child._creator_ambiguous or getattr(child, "pid", None) is None:
                raise _Failure("cleanup", "CLI creation ownership unresolved")
            if not child._creator_waited:
                if child.poll() is None:
                    child.kill()
                _owned_wait(child, owned.cap)
            if not child._creator_waited:
                raise _Failure("cleanup", "CLI actual creator wait absent")
            for stream in (getattr(child, "stdin", None), getattr(child, "stdout", None),
                           getattr(child, "stderr", None)):
                if stream is not None:
                    stream.close()
            if not started_record:
                _event(job, "CLI_STARTED", token=token, pid=child.pid, guardian=os.getpid())
                started_record = True
            _event(job, "CLI_JOIN_ACK", token=token, pid=child.pid,
                   returncode=child.returncode, guardian=os.getpid(), reaped=True)
        if time.monotonic() >= owned.cap():
            raise _Failure("cleanup", "CLI finalization exceeded owned cleanup cap")


def _check_owned_cleanup_evidence(job, journal):
    evidence = _closed(journal["owned_cleanup_evidence"], (
        "events_sha256", "creator_waits", "executors_joined", "observer_joined",
        "rpc_joined", "guest_released"))
    for name in ("observer_joined", "rpc_joined", "guest_released"):
        if evidence[name] is not True:
            raise _Failure("cleanup", "owned cleanup evidence incomplete")
    _integer(evidence["creator_waits"])
    _integer(evidence["executors_joined"])
    raw = _read_owned(job / "events.jsonl")
    if hashlib.sha256(raw).hexdigest() != _digest(evidence["events_sha256"]):
        raise _Failure("cleanup", "owned cleanup event binding changed")
    events = [_metadata(line) for line in raw.splitlines()]
    if any(type(event) is not dict for event in events):
        raise _Failure("cleanup", "owned cleanup event object required")
    absence = [i for i, event in enumerate(events) if event.get("kind") == "ACTOR_ABSENCE_PROOF"]
    if not absence:
        raise _Failure("cleanup", "owned actor absence evidence missing")
    cid = journal.get("cid")
    if cid is None:
        if journal.get("create_attempted") is not False:
            raise _Failure("cleanup", "attempted guest creation remains unproven")
    else:
        _digest(cid)
        positions = {}
        for kind in ("STOPPED", "DELETE", "ABSENCE"):
            positions[kind] = [i for i, event in enumerate(events)
                               if event.get("kind") == kind and event.get("cid") == cid]
            if not positions[kind]:
                raise _Failure("cleanup", "owned guest release evidence missing")
        delete = positions["DELETE"][-1]
        if not (any(i < delete for i in positions["STOPPED"])
                and any(i < delete for i in absence)
                and any(i > delete for i in positions["ABSENCE"])):
            raise _Failure("cleanup", "owned release evidence ordering invalid")


def _owned_cleanup_evidence(owned, observer):
    """Bind canonical resource proof to the immutable finalization journal."""
    if observer is not None and (
            not observer.retired or observer.thread.is_alive() or observer.inflight):
        raise _Failure("cleanup", "owned observer join absent")
    with owned.lock:
        if any(not child._creator_waited or child._creator_ambiguous for child in owned.children):
            raise _Failure("cleanup", "owned CLI creator wait absent")
        if any(daemon.active or daemon.workers for daemon in owned.daemons):
            raise _Failure("cleanup", "owned RPC aliases/workers remain")
        if any(thread.is_alive() for pool in owned.executors for thread in tuple(pool._threads)):
            raise _Failure("cleanup", "owned executor thread join absent")
        owned.journal["owned_cleanup_evidence"] = {
            "events_sha256": hashlib.sha256(_read_owned(owned.job / "events.jsonl")).hexdigest(),
            "creator_waits": len(owned.children), "executors_joined": len(owned.executors),
            "observer_joined": True, "rpc_joined": True, "guest_released": True}
        _check_owned_cleanup_evidence(owned.job, owned.journal)
    _cleanup_remaining(owned.journal)


def _owned_guardian(job: Path, control: int, cancel_fd: int, emergency: bool):
    _guardian(job, control, emergency, cancel_fd=cancel_fd)


def _owned_send_request(attached, request, control, journal):
    end = min(journal["deadline"], time.monotonic() + 3)
    remaining = memoryview(request)
    try:
        while remaining:
            _controller_alive(control)
            if time.monotonic() >= end:
                raise _Failure("transport", "request delivery absolute deadline")
            attached.settimeout(min(0.01, max(0.001, end - time.monotonic())))
            try:
                count = attached.send(remaining[:65536])
            except socket.timeout:
                continue
            if not count:
                raise _Failure("transport", "request delivery EOF")
            remaining = remaining[count:]
    finally:
        attached.settimeout(0.1)


def _spawn_owned_guardian(owner, job, control_fd, cancel_fd, lock_fd, log,
                          emergency=False):
    """Return creator-retained Popen; fake bootstraps use owner._spawn as well."""
    return owner._spawn(
        [sys.executable, "-I", "-B", str(job / "controller/ptc/sql_isolation.py"),
         "--owned-guardian", str(job), str(control_fd), str(cancel_fd),
         "emergency" if emergency else "normal"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
        pass_fds=(control_fd, cancel_fd, lock_fd), close_fds=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"})


class OwnedSqlInvocation(Generic[_T]):
    """Single-dispatch owner. Unknown cleanup deliberately retains this owner."""
    def __init__(self, executor, role, request, db_path):
        self.executor, self.role, self.request, self.db_path = executor, role, request, db_path
        self.invocation_id = uuid.uuid4()
        self.request_digest = request_sha256(request)
        self.profile_digest = execution_profile_sha256(executor.profile)
        self._lock = threading.RLock()
        self._authority = _AckAuthority(self)
        self._intent = None
        self._state = "ALLOCATED"
        self._incomplete = False
        self._completion = None
        self._candidate = None
        self._thread = None
        self._children = []
        self._endpoints = []
        self._host_read = None
        self._host_received = False
        self._journal = None
        self._proof = None
        self._seal_lock_fd = None
        self._resources = []
        self._retained = threading.Event()

    def request_cancel(self, reason: Literal["caller_cancelled", "runner_closed"]) -> CancelReceipt:
        _choice(reason, ("caller_cancelled", "runner_closed"))
        with self._lock:
            if self._completion is not None:
                return CancelReceipt("already_completed", None)
            if self._intent is not None:
                return CancelReceipt("repeated", self._intent)
            now = time.monotonic_ns()
            self._intent = CancelIntent(self.invocation_id, reason, now, now + _CANCEL_NS)
            self._state = "ABORT_LATCHED"
            for endpoint in self._endpoints:
                endpoint.deliver(self._intent)
            return CancelReceipt("accepted", self._intent)

    def snapshot(self) -> InvocationSnapshot:
        with self._lock:
            incomplete = self._incomplete
            if self._completion is None and self._thread is not None:
                incomplete |= time.monotonic() >= self._cap()
            return InvocationSnapshot(
                "UNRESOLVED_OWNED" if incomplete else self._state,
                self.invocation_id, self.role, self.request_digest, self.profile_digest,
                self._intent, incomplete)

    def _cap(self):
        with self._lock:
            end = float("inf")
            if self._journal is not None:
                end = min(self._journal["deadline"] + 12,
                          self._journal.get("cleanup_deadline", float("inf")))
            if self._intent is not None:
                end = min(end, self._intent.deadline_ns / 1e9)
            return end

    def _register_pipe(self):
        with self._lock:
            read_fd, write_fd = os.pipe()
            try:
                endpoint = _CancelEndpoint(write_fd)
            except BaseException:
                os.close(read_fd); os.close(write_fd)
                raise
            self._endpoints.append(endpoint)
            if self._intent is not None:
                endpoint.deliver(self._intent)
            return read_fd, endpoint

    def _spawn(self, *args, **kwargs):
        return _CreatorPopen(*args, _registry=self._children, **kwargs)

    def _issue(self, *, not_started, terminal=None, reaps=()):
        now = time.monotonic_ns()
        if self._intent is not None:
            trigger, end = self._intent.requested_ns, self._intent.deadline_ns
        elif self._journal is not None and "cleanup_trigger" in self._journal:
            trigger = int(self._journal["cleanup_trigger"] * 1e9)
            end = int(self._cap() * 1e9)
        else:
            trigger, end = now, now + _CANCEL_NS
        if not not_started:
            end = min(end, int(self._cap() * 1e9))
        self._authority.issuing = True
        try:
            ack = CleanupCompleteAck(
                self.invocation_id, self.role, self.request_digest, self.profile_digest,
                not_started, True, trigger, end, now, terminal, reaps,
                not not_started, not not_started, self._authority)
        finally:
            self._authority.issuing = False
        self._authority.ack = ack
        return ack

    def _seal(self, outcome, detail, *, not_started, terminal=None, reaps=()):
        # Caller holds the same lock as cancellation, no await through issuance.
        if not not_started:
            if self._proof is None or self._thread is None or self._thread.is_alive():
                raise _Failure("cleanup", "post-reap host proof absent")
            actual = tuple((p.pid, p.returncode) for p in self._children
                           if p._creator_waited and not p._creator_ambiguous)
            if (actual != reaps or len(actual) != len(self._children)
                    or any(endpoint.fd is not None for endpoint in self._endpoints)
                    or self._host_read is not None):
                raise _Failure("cleanup", "owned actors/endpoints remain at host seal")
            job, frame, guardian_pid = self._proof
            if terminal != hashlib.sha256(frame).hexdigest():
                raise _Failure("cleanup", "terminal proof digest changed")
            _, latest, _ = _validate_finalization(
                self.executor.profile,
                _read_owned(self.executor.profile.shared_state_dir / (
                    "FINALIZATION-PENDING-" + self.invocation_id.hex + ".json")),
                _parse_terminal_ack(frame), job=job, guardian_pid=guardian_pid, current=True,
                suppress_outcome=True)
            if "owned_cleanup_evidence" not in latest:
                raise _Failure("cleanup", "owned canonical cleanup evidence absent")
            self._host_checkpoint()
            if self._seal_lock_fd is None:
                raise _Failure("cleanup", "host admission ownership absent")
            # Resource proof can outlive usable-result eligibility. Historical
            # release checks remain intact; only the host may suppress output.
            if self._intent is None and detail is None:
                try:
                    _success_remaining(self._journal)
                except _Failure as exc:
                    detail = exc.reason
        ack = self._issue(not_started=not_started, terminal=terminal, reaps=reaps)
        if not not_started:
            try:
                os.close(self._seal_lock_fd)
            except BaseException:
                self._authority.ack = None
                raise
            self._seal_lock_fd = None
            self._resources.clear()
        abort = None
        if self._intent is not None:
            abort = OutcomeAbort(self.invocation_id, self.role, "cancelled", "cancelled")
        elif detail is not None:
            abort = OutcomeAbort(self.invocation_id, self.role, "infrastructure", detail)
        self._completion = InvocationCompletion(None if abort else outcome, abort, ack)
        self._state = "HOST_SEALED"
        return self._completion

    def _start(self):
        with self._lock:
            if self._completion is not None or self._thread is not None or self._incomplete:
                return
            if self._intent is not None:
                if time.monotonic_ns() > self._intent.deadline_ns:
                    self._incomplete = True
                    self._state = "UNRESOLVED_OWNED"
                    return
                try:
                    self._seal(None, "cancelled", not_started=True)
                except ValueError:
                    self._incomplete = True
                    self._state = "UNRESOLVED_OWNED"
                return
            try:
                binding = _fresh_owned_binding(self.executor.profile)
            except (TypeError, ValueError, OSError, KeyError, RecursionError):
                self._seal(None, "binding", not_started=True)
                return
            self._state = "ADMITTED"
            self._thread = threading.Thread(
                target=self._controller, args=(binding,),
                name="sql-owned-controller-" + self.invocation_id.hex, daemon=False)
            try:
                self._thread.start()
            except BaseException:
                if self._thread.ident is not None or self._thread.is_alive():
                    self.request_cancel("runner_closed")
                else:
                    self._thread = None
                    self._seal(None, "start", not_started=True)

    async def execute(self) -> InvocationCompletion[_T]:
        original_cancel = None
        self._start()
        while True:
            with self._lock:
                if (self._completion is None and self._candidate is not None
                        and self._thread is not None and not self._thread.is_alive()):
                    self._thread.join(timeout=0)
                    outcome, detail, terminal, reaps = self._candidate
                    try:
                        self._seal(outcome, detail, not_started=not reaps,
                                   terminal=terminal, reaps=reaps)
                    except Exception:
                        self._candidate = None
                        self._incomplete = True
                completed = self._completion
            if completed is not None:
                if original_cancel is not None:
                    raise original_cancel
                return completed
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError as exc:
                if original_cancel is None:
                    original_cancel = exc
                self.request_cancel("caller_cancelled")

    async def aclose(self) -> CleanupCompleteAck:
        self.request_cancel("runner_closed")
        return (await self.execute()).cleanup_ack

    def _host_checkpoint(self):
        if self._host_read is not None and not self._host_received:
            if select.select([self._host_read], [], [], 0)[0]:
                _acquire_cancel_frame(self._host_read, self.invocation_id, self._cap())
                self._host_received = True
        if time.monotonic() >= self._cap():
            raise _Failure("cleanup", "owned cleanup budget exhausted")

    def _wait_startup(self, process, write_control, *, emergency=False):
        data = bytearray()
        os.set_blocking(process.stdout.fileno(), False)
        end = min(self._cap(), self._cap() if emergency else self._journal["deadline"],
                  time.monotonic() + 4)
        while time.monotonic() < end:
            self._host_checkpoint()
            ready, _, _ = select.select([process.stdout.fileno()], [], [], 0.01)
            if ready:
                chunk = os.read(process.stdout.fileno(), 5 - len(data))
                if not chunk:
                    raise _Failure("transport", "guardian startup EOF")
                data.extend(chunk)
                if b"\n" in data:
                    if bytes(data) != b"ACK\n":
                        raise _Failure("protocol", "guardian startup mismatch")
                    os.write(write_control, b"G")
                    return
        raise _Failure("transport", "guardian startup deadline")

    def _terminal(self, process, profile, job):
        data = bytearray()
        fd = process.stdout.fileno()
        while True:
            self._host_checkpoint()
            try:
                latest = _metadata(_read_owned(job / "journal.json"))
            except _OwnedFileReplaced:
                # Mutable journal snapshots are atomically replaced. Discard
                # the unlinked bytes, keeping the same cap/checkpoint loop.
                continue
            self._latch_cleanup(latest)
            ready, _, _ = select.select([fd], [], [], 0.01)
            if not ready:
                continue
            chunk = os.read(fd, 4097 - len(data))
            if not chunk:
                raise _Failure("cleanup", "guardian EOF before terminal ACK")
            data.extend(chunk)
            if len(data) > 4096:
                raise _Failure("protocol", "terminal ACK byte cap")
            if b"\n" not in data:
                continue
            frame = bytes(data)
            _parse_terminal_ack(frame)
            # Commit validates the complete current transaction, not file presence.
            self._latch_cleanup(_metadata(_read_owned(job / "journal.json")))
            outcome = _commit_finalization(
                profile, job, self._journal, process.pid, frame, suppress_outcome=True)
            self._state = "DRAINED"
            _owned_wait(process, self._cap)
            if not process._creator_waited or process._creator_ambiguous or process.returncode != 0:
                raise _Failure("cleanup", "actual guardian wait absent/unsuccessful")
            self._host_checkpoint()
            if os.read(fd, 1):
                raise _Failure("protocol", "duplicate terminal output")
            _validate_finalization(
                profile, _read_owned(profile.shared_state_dir / (
                    "FINALIZATION-PENDING-" + self.invocation_id.hex + ".json")),
                _parse_terminal_ack(frame), job=job, guardian_pid=process.pid, current=True,
                suppress_outcome=True)
            self._proof = (job, frame, process.pid)
            self._state = "GUARDIAN_REAPED"
            return outcome, hashlib.sha256(frame).hexdigest()

    def _latch_cleanup(self, latest):
        if not isinstance(latest, dict):
            raise ValueError("owned journal required")
        if "cleanup_deadline" not in latest:
            if "cleanup_deadline" in self._journal:
                raise _Failure("cleanup", "owned cleanup budget disappeared")
            return
        trigger = _finalization_time(latest["cleanup_trigger"])
        end = _finalization_time(latest["cleanup_deadline"])
        if not 0 <= end - trigger <= 12:
            raise _Failure("cleanup", "invalid owned cleanup budget")
        with self._lock:
            if (end > self._journal.get("cleanup_deadline", end)
                    or trigger > self._journal.get("cleanup_trigger", trigger)):
                raise _Failure("cleanup", "owned cleanup budget extended")
            self._journal["cleanup_trigger"] = trigger
            self._journal["cleanup_deadline"] = end

    def _controller(self, binding):
        profile, executor = self.executor.profile, self.executor
        lock_fd = None
        read_control = write_control = None
        cancel_read = None
        log = None
        job = None
        reservation = False
        clean = False
        try:
            with self._lock:
                if self._intent is not None:
                    self._candidate = (None, "cancelled", None, ())
                    return
            _secure_directory(executor.state_dir)
            _secure_directory(profile.shared_state_dir)
            lock_fd = os.open(profile.shared_state_dir / "lock",
                              os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            self._resources.append(lock_fd)
            _owned_stat(os.fstat(lock_fd))
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                with self._lock:
                    self._candidate = (None, "admission", None, ())
                clean = True
                return
            _admit_finalizations(profile)
            nonce = self.invocation_id.hex
            job = executor.state_dir / nonce
            _secure_directory(job)
            _stage_sources(profile, job)
            _stage_database(self.db_path, self.request.db_sha256, job)
            raw_profile = execution_profile_canonical_bytes(profile)
            _write_owned(job / "profile.json", raw_profile, mode=0o400)
            _write_owned(job / "request.wire",
                         encode_wire_message(self.role, "request", self.request), mode=0o400)
            config = _container_config(profile, self.role, job, nonce)
            journal = {
                "nonce": nonce, "name": "co-train-sql-" + nonce, "role": self.role, "cid": None,
                "config": config, "config_sha256": hashlib.sha256(canonical_json_bytes(config)).hexdigest(),
                "binding": execution_binding_to_dict(binding), "profile_sha256": self.profile_digest,
                "request_sha256": self.request_digest, "db_sha256": self.request.db_sha256,
                "controller": os.getpid(), "guardians": [], "bootstrap": None,
                "actors_initialized": True, "create_attempted": False, "start_attempted": False,
                "kill_attempted": False,
                "deadline": time.monotonic() + limits_for(self.role).deadline_ms / 1000,
                "state": "RESERVED"}
            with self._lock:
                self._journal = journal
                self._state = "SPAWNING"
            _save_journal(job, journal)
            _event(job, "ACTORS_INITIALIZED", nonce=nonce)
            # From the first reservation attempt on, failures retain ownership.
            reservation = True
            _write_owned(profile.shared_state_dir / "active.json",
                         canonical_json_bytes({"nonce": nonce, "job": str(job)}) + b"\n")
            _event(job, "RESERVATION_DURABLE", deadline=journal["deadline"])
            self._host_read, _ = self._register_pipe()
            log = open(job / "guardian.log", "xb", buffering=0)
            self._resources.append(log)
            for attempt in range(2):
                read_control, write_control = os.pipe()
                cancel_read, endpoint = self._register_pipe()
                self._resources.extend((read_control, write_control, cancel_read))
                before = len(self._children)
                try:
                    process = _spawn_owned_guardian(
                        self, job, read_control, cancel_read, lock_fd, log, bool(attempt))
                except BaseException:
                    created = self._children[before:]
                    if (len(created) != 1 or created[0]._creator_ambiguous
                            or getattr(created[0], "stdout", None) is None
                            or getattr(created[0], "pid", None) is None):
                        raise
                    # Retained object, not an unassigned local/PID. A live
                    # normal bootstrap receives the runner-close intent and
                    # follows the same canonical cleanup transaction.
                    process = created[0]
                    self.request_cancel("runner_closed")
                if process not in self._children:
                    raise _Failure("cleanup", "guardian creation not creator-registered")
                # Parent must not keep a reader alive after actual inheritance.
                os.close(cancel_read)
                self._resources.remove(cancel_read)
                cancel_read = None
                try:
                    self._state = "STARTING"
                    self._wait_startup(process, write_control, emergency=bool(attempt))
                    self._state = "RUNNING" if not attempt else "CLEANING"
                    outcome, terminal = self._terminal(process, profile, job)
                    break
                except _Failure:
                    if process.poll() is None:
                        raise  # Never replace a live unresolved owner.
                    _owned_wait(process, self._cap)
                    latest = _metadata(_read_owned(job / "journal.json"))
                    names = _shared_names(profile)
                    if (attempt or latest.get("state") in ("CLOSED", "UNRESOLVED")
                            or any(name.startswith((
                                "FINALIZATION-PENDING-" + nonce,
                                "FINALIZATION-COMMITTED-" + nonce,
                                ".FINALIZATION-PENDING-" + nonce,
                                ".FINALIZATION-COMMITTED-" + nonce)) for name in names)
                            or "UNRESOLVED-" + nonce + ".json" in names
                            or (job / "outcome.json").exists()):
                        raise
                    _event(job, "GUARDIAN_REAPED", pid=process.pid,
                           returncode=process.returncode)
                    process.stdout.close()
                    self._latch_cleanup(latest)
                    _begin_cleanup(latest)
                    with self._lock:
                        latest["cleanup_deadline"] = min(latest["cleanup_deadline"], self._cap())
                        if self._intent is not None:
                            latest["cleanup_trigger"] = min(
                                latest["cleanup_trigger"], self._intent.requested_ns / 1e9)
                        self._journal = latest
                        journal = latest
                        # Retire the old pipe under the producer's same lock.
                        # Replacement gets independent readers and one delivery.
                        endpoint.close()
                        os.close(read_control); os.close(write_control)
                        self._resources.remove(read_control)
                        self._resources.remove(write_control)
                        read_control = write_control = None
                    _save_journal(job, latest)
            reaps = tuple((p.pid, p.returncode) for p in self._children
                          if p._creator_waited and not p._creator_ambiguous)
            if len(reaps) != len(self._children):
                raise _Failure("cleanup", "missing creator guardian wait")
            detail = outcome.abort.reason if outcome.abort is not None else None
            clean = True
            with self._lock:
                self._candidate = (outcome if detail is None else None, detail, terminal, reaps)
        except BaseException as exc:
            if not reservation and not self._children:
                clean = True
                with self._lock:
                    self._candidate = (None, exc.reason if isinstance(exc, _Failure) else "binding",
                                       None, ())
            else:
                # No inherited legacy finally-release, kill or post-ACK grace.
                for child in self._children:
                    try:
                        if (not child._creator_waited and not child._creator_ambiguous
                                and child.poll() is not None):
                            _owned_wait(child, self._cap)
                    except BaseException:
                        pass  # No signal authority or completion claim follows.
                with self._lock:
                    self._incomplete = True
                    self._state = "UNRESOLVED_OWNED"
                # Preserve actual resources, control liveness and mitigation.
                self._retained.wait()
        finally:
            if clean:
                try:
                    with self._lock:
                        for endpoint in self._endpoints:
                            endpoint.close()
                        for fd in (self._host_read, read_control, write_control, cancel_read):
                            if fd is not None:
                                os.close(fd)
                        self._host_read = None
                        for child in self._children:
                            if child._creator_waited and child.stdout is not None:
                                child.stdout.close()
                        if log is not None:
                            log.close()
                        if lock_fd is not None and self._children:
                            self._seal_lock_fd = lock_fd
                        elif lock_fd is not None:
                            os.close(lock_fd)
                        self._resources[:] = ([self._seal_lock_fd]
                                              if self._seal_lock_fd is not None else [])
                except BaseException:
                    with self._lock:
                        self._candidate = None
                        self._incomplete = True
                        self._state = "UNRESOLVED_OWNED"
                    self._retained.wait()


def _internal_guardian_entry():
    owned = len(sys.argv) == 6 and sys.argv[1] == "--owned-guardian"
    legacy = len(sys.argv) == 5 and sys.argv[1] == "--guardian"
    if not (owned or legacy) or sys.argv[-1] not in ("normal", "emergency"):
        raise SystemExit("internal guardian entry point only")
    job = Path(sys.argv[2])
    _path(job)
    if owned and (str(job) != sys.argv[2] or ".." in job.parts or job == Path("/")):
        raise SystemExit("canonical owned guardian job required")
    raw_fds = sys.argv[3:5] if owned else sys.argv[3:4]
    if any(re.fullmatch(r"[0-9]+", value) is None for value in raw_fds):
        raise SystemExit("invalid internal guardian descriptors")
    fds = tuple(int(value) for value in raw_fds)
    if (any(fd < 3 for fd in fds) or len(set(fds)) != len(fds)
            or owned and any(str(fd) != raw for fd, raw in zip(fds, raw_fds))):
        raise SystemExit("invalid internal guardian descriptors")
    for fd in fds:
        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
            raise SystemExit("internal guardian pipe required")
        if owned and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            raise SystemExit("owned guardian read capability required")
        os.set_inheritable(fd, False)
    if owned:
        _owned_guardian(job, fds[0], fds[1], sys.argv[-1] == "emergency")
    else:
        _guardian(job, fds[0], sys.argv[-1] == "emergency")


if __name__ == "__main__":
    _internal_guardian_entry()
