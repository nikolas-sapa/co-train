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
from typing import TYPE_CHECKING, Literal, Union

if TYPE_CHECKING:
    from bench.score import ExResult
    from bench.task import SqlTask
    from train.sql_episodes import InstrumentSettings

Role = Literal["program", "scorer"]
WireKind = Literal["bootstrap", "request", "result"]
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
        "api_timeout_ms": api_timeout_ms, "wire_format": "sql_pilot_wire", "wire_schema_version": 1}
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
    """WHOLE canonical four-field envelope INCLUDING LF, not the payload digest."""
    return hashlib.sha256(execution_profile_canonical_bytes(profile)).hexdigest()


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


WirePayload = Union[BootstrapPayload, ProgramRequest, ScoreRequest, ProgramResponse, "ExResult"]


def _payload(role: Role, kind: WireKind, value: object) -> JsonObject:
    if kind == "bootstrap":
        return _encode(value, BootstrapPayload)
    if role == "program":
        return _encode(value, ProgramRequest if kind == "request" else ProgramResponse)
    if kind == "request":
        return _encode(value, ScoreRequest)
    _ex_result(value)
    return _plain(value)


def _payload_from_dict(role: Role, kind: WireKind, value: JsonObject) -> WirePayload:
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
        _choice(self.role, ("program", "scorer")); _choice(self.kind, ("bootstrap", "request", "result"))
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
    envelope = {"format": "sql_pilot_wire", "schema_version": 1, "role": role, "kind": kind,
                "request_sha256": request, "payload": data, "sha256": digest}
    maximum = limits_for(role).input_bytes if kind == "request" else limits_for(role).stdout_bytes
    return bounded_bytes(canonical_json_bytes(envelope) + b"\n", maximum=maximum)


def decode_wire_message(data: bytes, *, role: Role, kind: WireKind,
                        request_sha256: str | None) -> WireMessage:
    _choice(role, ("program", "scorer")); _choice(kind, ("bootstrap", "request", "result"))
    maximum = limits_for(role).input_bytes if kind == "request" else limits_for(role).stdout_bytes
    d = _closed(_json_line(data, maximum=maximum), ("format", "schema_version", "role", "kind", "request_sha256", "payload", "sha256"))
    _version(d["schema_version"])
    if d["format"] != "sql_pilot_wire" or d["role"] != role or d["kind"] != kind or d["request_sha256"] != request_sha256:
        raise ValueError("wire role/kind/request context mismatch")
    if _digest(d["sha256"]) != hashlib.sha256(canonical_json_bytes(d["payload"])).hexdigest():
        raise ValueError("wire payload digest mismatch")
    return WireMessage(role, kind, d["request_sha256"], _payload_from_dict(role, kind, d["payload"]))


def validate_output_budget(role: Role, *, bootstrap: bytes, result: bytes) -> None:
    bounded_bytes(READY + bootstrap + result, maximum=limits_for(role).stdout_bytes)


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


def _read_owned(path: Path, maximum=MAX_ARTIFACT_BYTES) -> bytes:
    parent, name = _open_parent(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd); _owned_stat(before)
            data = bytearray()
            while chunk := os.read(fd, min(65536, maximum + 1 - len(data))):
                data.extend(chunk)
                if len(data) > maximum:
                    raise ValueError("owned file exceeds bound")
            after = os.fstat(fd)
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink) != (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink):
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
        return end

    def _supervise(self, end, operation_end=None):
        if time.monotonic() >= end:
            hard_end = end if operation_end is None else operation_end
            reason = "cleanup" if hasattr(self, "cleanup_deadline") else (
                "deadline" if hasattr(self, "operation_deadline") and
                hard_end >= self.operation_deadline else "transport")
            raise _Failure(reason, "absolute RPC deadline")
        if not hasattr(self, "cleanup_deadline"):
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
        try:
            thread.start(); started = True
            while not done.wait(min(0.01, max(0, io_end - time.monotonic()))):
                self._supervise(io_end, end)
            self._supervise(end)
            if not box[0][0]:
                error = box[0][1]
                if isinstance(error, _Failure):
                    raise error
                reason = "memory" if isinstance(error, MemoryError) else "transport"
                raise _RPCUncertain(reason, "incomplete/malformed RPC: " + type(error).__name__) from error
            return box[0][1]
        except _HTTPFailure:
            raise  # Completed, typed HTTP status, especially the exact 409 path.
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
                thread.join(timeout=max(0, end - time.monotonic()))
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


def _event(job, kind, **values):
    _append_owned(job / "events.jsonl", {"kind": kind, "at": time.monotonic(), **values})


def _vm_memory(profile, job, deadline):
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
    def get(path):
        remaining = min(3.0, end - time.monotonic())
        if remaining <= 0:
            raise _ObservationFailure("complete sample older than four seconds")
        return daemon.call("GET", path, timeout=remaining)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="sql-metadata")
    try:
        vm = pool.submit(_vm_memory, profile, job, end)
        info = pool.submit(get, "/info")
        listing = pool.submit(get, "/containers/json")
        containers = listing.result(timeout=max(0.001, end - time.monotonic()))
        if type(containers) is not list or len(containers) > 128:
            raise _ObservationFailure("invalid running-container inventory")
        ids = []
        for container in containers:
            if type(container) is not dict or container.get("State") not in ("running", "paused", "restarting"):
                raise _ObservationFailure("unknown running-container state")
            ids.append(_digest(container.get("Id")))
        if len(set(ids)) != len(ids):
            raise _ObservationFailure("duplicate running CID")
        charges = [(cid, pool.submit(get, f"/containers/{cid}/stats?stream=false&one-shot=true"))
                   for cid in ids]
        total, available = vm.result(timeout=max(0.001, end - time.monotonic()))
        daemon_info = info.result(timeout=max(0.001, end - time.monotonic()))
        if type(daemon_info) is not dict or _integer(daemon_info.get("MemTotal"), minimum=1) != total:
            raise _ObservationFailure("VM/daemon total mismatch")
        raw = []
        for cid, future in charges:
            stats = future.result(timeout=max(0.001, end - time.monotonic()))
            if type(stats) is not dict or type(stats.get("memory_stats")) is not dict:
                raise _ObservationFailure("missing raw memory statistics")
            charge = _integer(stats["memory_stats"].get("usage"))
            raw.append((cid, charge))
        finished = time.monotonic()
        if finished > end:
            raise _ObservationFailure("complete memory sample exceeded four seconds")
        headroom = min(available, total - sum(v for _, v in raw))
        if headroom < 0:
            raise _ObservationFailure("inconsistent raw charged memory")
        sample = {"started": started, "finished": finished, "available": headroom,
                  "vm_total": total, "vm_available": available, "raw_charges": raw,
                  "token": uuid.uuid4().hex, "eligible": True}
        _event(job, "MEMORY_SAMPLE", **sample)
        return sample
    except BaseException as exc:
        if isinstance(exc, _ObservationFailure):
            raise
        raise _ObservationFailure("incomplete/error raw memory observation") from exc
    finally:
        # Every call has a per-request remaining deadline. Never abandon futures.
        pool.shutdown(wait=True, cancel_futures=True)
        if daemon.active or daemon.workers:
            raise _ObservationFailure("metadata HTTP aliases not closed")


class _Observer:
    def __init__(self, profile, daemon, job):
        self.profile, self.daemon, self.job = profile, daemon, job
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.failure = None
        self.tokens = []
        self.retired = False
        self.token = uuid.uuid4().hex
        _event(job, "OBSERVER_SPAWN_INTENT", token=self.token, guardian=os.getpid())
        self.thread = threading.Thread(target=self._run, name="sql-memory-observer", daemon=False)

    def _run(self):
        while not self.stop.is_set():
            try:
                sample = _memory_sample(self.profile, self.daemon, self.job)
                with self.lock:
                    sample["eligible"] = not self.retired
                    self.tokens.append(sample)
                    self.latest = sample
            except BaseException as exc:
                with self.lock:
                    self.failure = exc
                # A failed sample never becomes an eligible cached zero-charge frame.
                self.stop.wait(0.25)
                continue
            self.stop.wait(0.25)

    def check(self, *, after=None, admission=False):
        with self.lock:
            if self.retired or self.failure is not None:
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

    def _raise_if_failed(self):
        if self.failure is not None:
            raise _ObservationFailure("failure discovered during observer retirement")

    def retire(self, deadline=None):
        with self.lock:
            self.retired = True
            for sample in self.tokens:
                sample["eligible"] = False
        _event(self.job, "OBSERVER_RETIRED")
        self.stop.set()
        self.thread.join(timeout=max(0, min(4.5, deadline - time.monotonic())) if deadline is not None else 4.5)
        if self.thread.is_alive() or self.daemon.active or getattr(self.daemon, "workers", set()):
            raise _Failure("cleanup", "observer/CLI/HTTP join not acknowledged")
        _event(self.job, "OBSERVER_THREAD_JOINED", token=self.token, guardian=os.getpid())
        self._raise_if_failed()
        journal = _metadata(_read_owned(self.job / "journal.json"))
        _prove_actor_absence(self.job, journal)
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


def _stream_result(profile, daemon, journal, job, control, observer, attached):
    role = journal["role"]
    limits = limits_for(role)
    mux = _MuxDecoder(stdout_limit=limits.stdout_bytes, stderr_limit=limits.stderr_bytes)
    output = bytearray()
    stderr = bytearray()
    bootstrap = None
    result = None
    ready = False
    request = _read_owned(job / "request.wire")
    while True:
        _controller_alive(control)
        if time.monotonic() >= journal["deadline"]:
            raise _Failure("deadline", "original whole-role deadline")
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
                attached.settimeout(min(3.0, max(0.001, journal["deadline"] - time.monotonic())))
                attached.sendall(request)
                attached.settimeout(0.1)
                _event(job, "REQUEST_DELIVERED", request_sha256=journal["request_sha256"])
            elif bootstrap is not None and b"\n" in output:
                wire = bytes(output)
                try:
                    result = decode_wire_message(wire, role=role, kind="result",
                                                 request_sha256=journal["request_sha256"]).payload
                except (TypeError, ValueError) as exc:
                    raise _Failure("protocol", "invalid result frame") from exc
                output.clear()
    journal["stdout_bytes"], journal["stderr_bytes"] = mux.counts[1], mux.counts[2]
    _write_owned(job / "stderr.bin", bytes(stderr))
    _save_journal(job, journal)
    obj = _inspect(daemon, journal)
    if obj is None:
        raise _Failure("cleanup", "owned object disappeared")
    state = obj["State"]
    if state.get("OOMKilled") is True or state.get("ExitCode") == 70:
        raise _Failure("memory", "guest OOM/allocation failure")
    if not _stopped_state(state):
        raise _Failure("protocol", "EOF before proven owned stop")
    if state.get("ExitCode") != 0 or result is None or output or mux.buffer or mux.remaining:
        raise _Failure("protocol", "incomplete result or unsuccessful guest exit")
    return result


def _cleanup_owned(profile, daemon, journal, job, observer):
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
        if journal["kill_attempted"]:
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
        _event(job, "STOPPED", cid=journal["cid"])
    if observer is not None:
        observer.retire(deadline=journal["cleanup_deadline"])
    else:
        _prove_actor_absence(job, journal)
        _event(job, "OBSERVER_JOIN_ACK", samples=0, failed=False, actor_absence_proven=True)
    _cleanup_remaining(journal)
    # No sampler, CLI, future or metadata alias exists across DELETE.
    if obj is not None:
        if daemon.active or getattr(daemon, "workers", set()):
            raise _Failure("cleanup", "HTTP aliases active before delete")
        daemon.call("DELETE", f"/containers/{journal['cid']}?force=false&v=false", statuses=(204,))
        _event(job, "DELETE", cid=journal["cid"])
        if _inspect(daemon, journal) is not None:
            raise _Failure("cleanup", "owned object still present")
        _event(job, "ABSENCE", cid=journal["cid"])
    _cleanup_remaining(journal)
    journal["cleanup_elapsed"] = time.monotonic() - journal["cleanup_trigger"]


def _begin_cleanup(journal):
    if "cleanup_deadline" not in journal:
        journal["cleanup_trigger"] = time.monotonic()
        journal["cleanup_deadline"] = journal["cleanup_trigger"] + 12.0
    elif "cleanup_trigger" not in journal:
        # Also supports a scaled, pre-seeded private test budget.
        journal["cleanup_trigger"] = min(time.monotonic(), journal["cleanup_deadline"])


def _cleanup_remaining(journal):
    if time.monotonic() >= journal["cleanup_deadline"]:
        raise _Failure("cleanup", "original absolute cleanup deadline exhausted")


def _final_start_checks(control, observer, fresh_after, journal):
    _controller_alive(control)
    observer.check(after=fresh_after, admission=True)
    if time.monotonic() >= journal["deadline"]:
        raise _Failure("deadline", "original deadline immediately before START")


def _close_reservation(profile, journal, job):
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
        os.unlink(name, dir_fd=parent); os.fsync(parent)
    finally:
        os.close(parent)


def _block(profile, journal, job, detail):
    journal["state"] = "UNRESOLVED"
    journal["block_reason"] = detail
    _save_journal(job, journal)
    # The original block is immutable and is never rewritten by reconciliation.
    path = profile.shared_state_dir / ("UNRESOLVED-" + journal["nonce"] + ".json")
    if not path.exists():
        _write_owned(path, canonical_json_bytes({
            "nonce": journal["nonce"], "job": str(job), "cid": journal["cid"],
            "reason": detail, "journal_sha256": hashlib.sha256(_read_owned(job / "journal.json")).hexdigest()
        }) + b"\n")


def _guardian(job: Path, control: int, emergency: bool):
    journal = _metadata(_read_owned(job / "journal.json"))
    profile_raw = _read_owned(job / "profile.json")
    profile = execution_profile_from_bytes(profile_raw)
    if hashlib.sha256(profile_raw).hexdigest() != journal["profile_sha256"]:
        raise ValueError("guardian profile mismatch")
    if journal["config_sha256"] != hashlib.sha256(canonical_json_bytes(journal["config"])).hexdigest():
        raise ValueError("guardian configuration mismatch")
    _activate_staged_import_root(job, profile)
    build_execution_binding(profile, source_root=installed_source_root())
    journal["guardians"].append(os.getpid())
    _save_journal(job, journal)
    _event(job, "GUARDIAN_ACK", pid=os.getpid(), emergency=emergency)
    sys.stdout.buffer.write(b"ACK\n"); sys.stdout.buffer.flush()
    if os.read(control, 1) != b"G":
        emergency = True
    daemon = _Daemon(profile)
    daemon.operation_deadline = journal["deadline"]
    daemon.control = control
    observer = None
    attached = None
    failure = _Failure("transport", "original guardian died") if emergency else None
    result = None
    uncertain = False
    try:
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
            observer = _Observer(profile, _Daemon(profile), job)
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
        uncertain = isinstance(exc, (_ObservationFailure, _HTTPFailure, _RPCUncertain, OSError, TimeoutError))
        journal["failure"] = {"reason": failure.reason, "detail": str(failure)}
        _save_journal(job, journal)
    finally:
        _begin_cleanup(journal)
        _save_journal(job, journal)
        if attached is not None:
            attached.close()
        try:
            _cleanup_owned(profile, daemon, journal, job, observer)
        except BaseException as exc:
            uncertain = True
            failure = _Failure("cleanup", type(exc).__name__ + ": " + str(exc))
        if uncertain:
            _block(profile, journal, job, str(failure))
        else:
            journal["state"] = "CLOSED"
            _save_journal(job, journal)
            _close_reservation(profile, journal, job)
        receipt = None
        if journal.get("bootstrap") is not None:
            boot = journal["bootstrap"]
            receipt = RuntimeReceipt(journal["role"], journal["request_sha256"], boot["python_version"],
                                     boot["sqlite_version"], journal["bootstrap_sha256"],
                                     hashlib.sha256(_read_owned(job / "journal.json")).hexdigest())
        if failure is not None:
            outcome = (ProgramOutcome(None, AbortInfo("program", failure.reason), receipt)
                       if journal["role"] == "program" else
                       ScoreOutcome(None, AbortInfo("scorer", failure.reason), receipt))
        elif journal["role"] == "program":
            outcome = ProgramOutcome(result.observation, None, receipt, rejected=result.rejected)
        else:
            outcome = ScoreOutcome(result, None, receipt)
        _write_owned(job / "outcome.json", canonical_json_bytes(outcome) + b"\n")
        if uncertain and observer is not None and not observer.retired:
            # Keep mitigation alive when OWN liveness is unknown. The reservation
            # and original block remain durable; no subsequent START is possible.
            while True:
                observer.stop.wait(1.0)


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
        if (profile.shared_state_dir / "active.json").exists():
            return _runtime_abort(role, "admission")
        # Unclosed original block history is never cleared by another profile/run.
        for block in profile.shared_state_dir.glob("UNRESOLVED-*.json"):
            if not (profile.shared_state_dir / ("CLOSED-" + block.name)).is_file():
                return _runtime_abort(role, "admission")
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
            if (job / "outcome.json").is_file():
                outcome_data = _metadata(_read_owned(job / "outcome.json"))
                # Unknown-liveness guardian deliberately survives with its lock.
                if _metadata(_read_owned(job / "journal.json"))["state"] == "UNRESOLVED":
                    return (program_outcome_from_dict(outcome_data) if role == "program"
                            else score_outcome_from_dict(outcome_data))
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # CLOSED outcome is already durable. Reaping is hygiene,
                    # never grounds to discard the completed typed outcome.
                    process.kill()
                    process.wait()
                return (program_outcome_from_dict(outcome_data) if role == "program"
                        else score_outcome_from_dict(outcome_data))
            if process.poll() is not None:
                process.wait()
                _event(job, "GUARDIAN_REAPED", pid=process.pid, returncode=process.returncode)
                process.stdout.close()
                if replaced:
                    raise _Failure("cleanup", "replacement guardian died")
                replaced = True
                latest = _metadata(_read_owned(job / "journal.json"))
                _begin_cleanup(latest)
                _save_journal(job, latest)
                process = spawn(True)
            if time.monotonic() > journal["deadline"] + 12:
                raise _Failure("cleanup", "guardian exceeded original deadline plus cleanup")
            select.select([], [], [], 0.02)
    except (TypeError, ValueError, OSError) as exc:
        if job is not None and (job / "journal.json").exists():
            journal = _metadata(_read_owned(job / "journal.json"))
            _block(profile, journal, job, type(exc).__name__)
        return _runtime_abort(role, "binding" if process is None else "transport")
    except _Failure as exc:
        if job is not None and (job / "journal.json").exists():
            journal = _metadata(_read_owned(job / "journal.json"))
            _block(profile, journal, job, str(exc))
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


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--guardian" or sys.argv[4] not in ("normal", "emergency"):
        raise SystemExit("internal guardian entry point only")
    _guardian(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "emergency")
