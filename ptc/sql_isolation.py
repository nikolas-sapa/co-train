"""Pure, closed SQL isolation contracts. No daemon or execution implementation.

These hashes bind NEW production data, not spike policy bytes. Source validation
is local and data-only; it does not qualify a runtime/closure for execution.
PROGRAM imports do not import bench, capture, gold, or the provider harness.
The future worker can use these stdlib wire codecs without a scorer import.
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
        raise NotImplementedError("Phase0: PROGRAM staging/guardian/daemon boundary not implemented")

    def score_sql(self, predicted_sql: str, task: SqlTask, *, db_sha256: str,
                  instrument: InstrumentSettings) -> ScoreOutcome:
        raise NotImplementedError("Phase0: whole SCORER boundary not implemented; no host fallback")
