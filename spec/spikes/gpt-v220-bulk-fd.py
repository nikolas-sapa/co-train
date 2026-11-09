# Sanitized public reference, UNRUN derivative. No execution authority.
"""SOURCEONLY UNRUN. Seven fixed bulk-FD fixtures; C2 arithmetic blocks PASS."""
import time
START = time.monotonic()  # Before all remaining stdlib and genuine project imports.

import errno, fcntl, hashlib, json, math, os
from pathlib import Path
import re, select, signal, socket, stat, subprocess, sys
from dataclasses import asdict, fields
from decimal import Decimal
from types import SimpleNamespace as NS

REPO = Path("/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/sol-v159-transport-runner")
PROGRAM = REPO / "spec/spikes/gpt-v220-bulk-fd.py"
SCRATCH = Path("/qualification-reference/scratch")
CAP, COUNT, CONTROL, MAX_SIZE = 8388608, 10000, 8192, 2147483648
BRIEF_C2_BYTES, DERIVED_C2_BYTES = 5870001, 6510001
COUNTERS = ("req_reads", "mf_reads", "req_parses", "mf_parses",
            "records", "ready", "permits", "markers", "closed")
EXITS = {"request_mode": 5, "request_identity": 5, "request_bytes": 5,
         "request_hash": 5, "request_parse": 5, "manifest_mode": 6,
         "manifest_identity": 7, "manifest_bytes": 8, "manifest_hash": 9,
         "manifest_parse": 10, "member_count": 11, "member_record": 12}
CASES = (  # Independent expected byte counts, never fitted expectations.
    (40, 25, 8193, "", 0),
    (10000, 256, BRIEF_C2_BYTES, "", 0),
    (12886, 256, 8388609, "manifest_bytes", 8),
    (10001, 14, 1630164, "member_count", 11),
    (24, 18, 4105, "manifest_hash", 9),
    (24, 18, 4105, "manifest_identity", 7),
    (24, 18, 4105, "manifest_mode", 6),
)
# Only this fixed source is launched. Alarm is armed before bootstrap file I/O.
BOOT = """import os,signal,sys,time
end=min(float(sys.argv[-4]),float(sys.argv[-3]))
remaining=end-time.monotonic()
if not remaining > 0: os._exit(97)
signal.signal(signal.SIGALRM,lambda *_: os._exit(97))
signal.setitimer(signal.ITIMER_REAL,remaining)
sys.argv=sys.argv[1:]
import runpy
runpy.run_path(sys.argv[0],run_name="__main__")
"""

def need(value, message):
    if not value:
        raise ValueError(message)

def left(end):
    remaining = end - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("immutable expiry reached")
    return remaining

def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False, default=lambda v: format(v, "f") if type(v) is Decimal
                      else str(v) if isinstance(v, Path) else bad("non-JSON value")).encode("ascii")

def bad(message):
    raise ValueError(message)

def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate JSON key")
        result[key] = value
    return result

def loads(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: bad("nonfinite JSON"))

def shapes():
    sys.path.insert(0, str(REPO))
    from train import native_qualification as native
    from bench.task import SqlTask
    return native, SqlTask

def signature(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_uid]

def private(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600)

def hex_string(value, count=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(count) + "}", value) is not None

class Wire:
    def __init__(self, connection, session, index):
        self.socket, self.session, self.index = connection, session, index
        self.bytes, self.sent, self.received = 0, [], []
        connection.setblocking(False)

    def transfer(self, data, count, end, sending):
        result, offset = bytearray(), 0
        while offset < count:
            timeout = left(end)
            ready = select.select([] if sending else [self.socket],
                                  [self.socket] if sending else [], [], timeout)
            if not ready[0] and not ready[1]:
                raise TimeoutError("control deadline")
            try:
                block = (self.socket.send(data[offset:]) if sending
                         else self.socket.recv(count - offset))
            except (BlockingIOError, InterruptedError):
                continue
            moved = block if sending else len(block)
            need(moved > 0, "control EOF/zero write")
            offset += moved
            self.bytes += moved
            need(self.bytes <= CONTROL, "aggregate control cap")
            if not sending:
                result.extend(block)
        left(end)
        return bytes(result)

    def send(self, kind, seq, end, **extra):
        packet = dict(v=1, kind=kind, seq=seq, session=self.session, case=self.index, **extra)
        body = dumps(packet)
        need(0 < len(body) <= 2048, "control frame cap")
        frame = len(body).to_bytes(4, "big") + body
        self.transfer(frame, len(frame), end, True)
        self.sent.append(packet)  # Count completed real messages, not intent.

    def receive(self, seq, kinds, end):
        size = int.from_bytes(self.transfer(b"", 4, end, False), "big")
        need(0 < size <= 2048 and self.bytes + size <= CONTROL, "control size cap")
        value = loads(self.transfer(b"", size, end, False))
        need(type(value) is dict and type(value.get("kind")) is str
             and value["kind"] in kinds, "control kind")
        extra = kinds[value["kind"]]
        need(set(value) == {"v", "kind", "seq", "session", "case", *extra}, "control keys")
        for key, expected in (("v", 1), ("seq", seq), ("case", self.index)):
            need(type(value[key]) is int and value[key] == expected, "control nonbool integer")
        need(type(value["session"]) is str and value["session"] == self.session, "session")
        self.received.append(value)
        return value

class Refusal(Exception):
    def __init__(self, stage):
        super().__init__(stage)
        self.stage, self.code = stage, EXITS[stage]

def refuse_if(condition, stage):
    if condition:
        raise Refusal(stage)

def pin_shape(pin):
    need(type(pin) is dict and set(pin) == {"id", "size", "sha256"}, "pin keys")
    need(type(pin["id"]) is list and len(pin["id"]) == 8
         and all(type(v) is int for v in pin["id"]), "pin identity")
    need(type(pin["size"]) is int and pin["size"] >= 0 and pin["size"] == pin["id"][4]
         and hex_string(pin["sha256"]), "pin type")

def identity(fd, pin, label):
    info = os.fstat(fd)
    refuse_if(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
              or not private(info) or info.st_uid != pin["id"][7], label + "_mode")
    refuse_if(signature(info) != pin["id"], label + "_identity")
    return info

def read_payload(fd, pin, label, cap, counts, end):
    info = identity(fd, pin, label)
    refuse_if(info.st_size > cap or info.st_size != pin["size"], label + "_bytes")
    data, digest = bytearray(), hashlib.sha256()
    while True:
        left(end)
        block = os.read(fd, min(65536, pin["size"] - len(data) + 1))
        counts["req_reads" if label == "request" else "mf_reads"] += 1
        identity(fd, pin, label)
        if not block:
            break
        data.extend(block)
        digest.update(block)
        refuse_if(len(data) > pin["size"], label + "_bytes")
    refuse_if(len(data) != pin["size"], label + "_bytes")
    refuse_if(digest.hexdigest() != pin["sha256"], label + "_hash")
    identity(fd, pin, label)
    return bytes(data), digest.hexdigest()

def rebuild(raw, root, native, Task):
    value = loads(raw)
    native._closed(value, {f.name for f in fields(native.QualificationRequest)} | {"schema"}, "projection")
    need(value.pop("schema") == "v220-local-request-projection", "projection schema")
    def path(text):
        need(type(text) is str, "projection path type")
        result = Path(text)
        need(result.is_absolute() and result.is_relative_to(root)
             and ".." not in result.parts and str(result) == text, "projection private path")
        return result
    def pin(row):
        native._closed(row, {"path", "size", "sha256"}, "FilePin")
        need(type(row["size"]) is int and 0 <= row["size"] <= MAX_SIZE
             and hex_string(row["sha256"]), "FilePin value")
        return native.FilePin(path(row["path"]), row["size"], row["sha256"])
    need(type(value["tasks"]) is list and len(value["tasks"]) == 4, "four tasks")
    tasks = []
    for row in value["tasks"]:
        native._closed(row, {f.name for f in fields(Task)}, "SqlTask")
        need(all(type(v) is str for v in row.values()), "task strings")
        path(row["db_path"])
        tasks.append(Task(**row))
    for label, count in (("source_pins", 3), ("database_pins", 4)):
        need(type(value[label]) is list and len(value[label]) == count, "pin cardinality")
        value[label] = tuple(pin(row) for row in value[label])
    value["runtime_inventory"] = pin(value["runtime_inventory"])
    value["tasks"] = tuple(tasks)
    for name in ("db_root", "model_dir", "output_dir"):
        value[name] = path(value[name])
    need(type(value["image_digest"]) is str
         and re.fullmatch("sha256:[0-9a-f]{64}", value["image_digest"]), "image label")
    value["bounds"] = native._bounds_from_wire(value["bounds"])
    request = native.QualificationRequest(**value)
    need(type(request) is native.QualificationRequest, "genuine QualificationRequest")
    return request

def validate_manifest(raw, native, counts, end):
    counts["mf_parses"] += 1
    try:
        members = loads(raw)
    except (ValueError, RecursionError):
        raise Refusal("manifest_parse") from None
    refuse_if(type(members) is not list, "manifest_parse")
    refuse_if(not 1 <= len(members) <= COUNT, "member_count")
    previous, snapshots = None, set()
    try:
        for row in members:
            left(end)
            native._closed(row, {"root", "key", "size", "sha256", "snapshot_key"}, "member")
            native._asset_path(row["root"], row["key"])
            native._asset_path("source", row["snapshot_key"])
            need(type(row["size"]) is int and 0 <= row["size"] <= MAX_SIZE
                 and hex_string(row["sha256"]), "member size/hash")
            pair = (row["root"], row["key"])
            need((previous is None or previous < pair)
                 and row["snapshot_key"] not in snapshots, "member order/collision")
            previous = pair
            snapshots.add(row["snapshot_key"])
            counts["records"] += 1
        need(dumps(members) == raw, "canonical manifest")
    except (ValueError, TypeError):
        raise Refusal("member_record") from None
    return len(members)

def write_all(fd, data, end):
    offset = 0
    while offset < len(data):
        left(end)
        count = os.write(fd, data[offset:offset + 65536])
        need(count > 0, "zero file write")
        offset += count

def append_journal(path, row, end, registry=None, errors=None):
    need(registry is not None or type(errors) is list, "journal owner/error ledger required")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)  # NEVER O_CREAT.
    entry = register(registry, fd, "append", path) if registry is not None else None
    try:
        need(private(os.fstat(fd)), "journal private precreation")
        body = dumps(row) + b"\n"
        need(len(body) <= 2048, "journal row cap")
        write_all(fd, body, end)
    finally:
        if entry is None:
            attempt(NS(errors=errors), fd, lambda: os.close(fd))
        # Parent append FD stays registered until post-reap cleanup.

def worker(argv):
    need(len(argv) == 10, "fixed worker args")
    root = Path(argv[0])
    request_fd, manifest_fd, control_fd = map(int, argv[1:4])
    session, index = argv[4], int(argv[5])
    case_end, run_end, work_end = map(float, argv[6:9])
    need(argv[9] == "v220" and len({request_fd, manifest_fd, control_fd}) == 3, "fixed worker mode")
    need(all(math.isfinite(v) for v in (case_end, run_end, work_end))
         and work_end < case_end <= run_end and hex_string(session, 32), "worker bounds")
    need(root.parent.parent == SCRATCH and root.parent.name.startswith("gpt-v220-")
         and root.name == f"C{index + 1}" and 0 <= index < 7, "private worker root")
    end = min(work_end, run_end, case_end, START + 2)
    counts = dict.fromkeys(COUNTERS, 0)
    connection, wire, primary, errors, code, stage = None, None, None, [], 2, "internal"
    def audit(event, args):
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork",
                     "os.forkpty", "os.exec", "os.kill", "os.killpg", "socket.connect",
                     "socket.bind", "socket.getaddrinfo", "socket.gethostbyname"}:
            raise RuntimeError("worker process/network call forbidden")
    sys.addaudithook(audit)
    try:
        left(end)
        need(signal.getitimer(signal.ITIMER_REAL)[0] > 0, "independent bootstrap alarm")
        connection = socket.socket(fileno=control_fd)
        need(connection.family == socket.AF_UNIX, "Unix control")
        wire = Wire(connection, session, index)
        native, Task = shapes()
        hello = wire.receive(0, {"INIT": ("request", "manifest")}, end)
        for label in ("request", "manifest"):
            pin_shape(hello[label])
        request_raw, _ = read_payload(request_fd, hello["request"], "request",
                                      native._WIRE_LIMIT, counts, end)
        counts["req_parses"] += 1
        try:
            request = rebuild(request_raw, root, native, Task)
        except (ValueError, TypeError):
            raise Refusal("request_parse") from None
        identity(request_fd, hello["request"], "request")
        raw, digest = read_payload(manifest_fd, hello["manifest"], "manifest", CAP, counts, end)
        members = validate_manifest(raw, native, counts, end)
        # Both same inherited descriptors, after ALL parsing and record checks.
        identity(request_fd, hello["request"], "request")
        identity(manifest_fd, hello["manifest"], "manifest")
        wire.send("READY", 1, end, pid=os.getpid(), tasks=len(request.tasks),
                  members=members, sha256=digest)
        counts["ready"] += 1
        challenge_end = min(end, time.monotonic() + .5)
        challenge = wire.receive(2, {"CHALLENGE": ("token",)}, challenge_end)
        need(hex_string(challenge["token"], 32), "challenge token")
        wire.send("ALIVE", 3, challenge_end, token=challenge["token"])
        permit = wire.receive(4, {"PERMIT": ("token",)}, end)
        need(hex_string(permit["token"], 32), "one-use permit")
        identity(request_fd, hello["request"], "request")
        identity(manifest_fd, hello["manifest"], "manifest")
        counts["permits"] += 1
        marker_fd = os.open(root / "marker", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        counts["markers"] += 1
        try:
            os.fchmod(marker_fd, 0o600)
            marker = dumps(dict(session=session, permit=permit["token"], pid=os.getpid(), case=index))
            write_all(marker_fd, marker, end)
        finally:
            attempt(NS(errors=errors), marker_fd, lambda: os.close(marker_fd))
        wire.send("DONE", 5, end, sha256=hashlib.sha256(marker).hexdigest())
        code, stage = 0, ""
    except Refusal as error:
        primary, code, stage = error, error.code, error.stage
        try:
            wire.send("REJECT", 1, end, stage=stage, code=code)
        except BaseException as extra:
            errors.append(extra)
    except BaseException as error:
        primary = error
    finally:
        for fd in (request_fd, manifest_fd, control_fd):
            try:
                connection.close() if fd == control_fd and connection is not None else os.close(fd)
                counts["closed"] += 1
            except BaseException as error:
                errors.append(error)
        try:
            append_journal(root.parent / "journal", dict(
                kind="worker_exit", case=index, session=session, pid=os.getpid(),
                code=code, stage=stage, stats=counts), case_end, errors=errors)
        except BaseException as error:
            errors.append(error)
    if errors or (primary is not None and not isinstance(primary, Refusal)):
        print(repr((primary, errors)), file=sys.stderr, flush=True)
        return 2
    return code

def register(owner, fd, role, path=None, obj=None):
    entry = NS(fd=fd, role=role, path=path, obj=obj, closed=False)
    owner.handles.append(entry)  # Immediately after the actual creation call.
    return entry

def open_file(owner, path, flags, role="owner"):
    if flags & os.O_CREAT:
        owner.paths.add(path)  # Register the actual Path before creation.
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    entry = register(owner, fd, role, path)
    if flags & os.O_CREAT:
        os.fchmod(fd, 0o600)
    return entry

def close(entry):
    if entry.closed:
        return
    entry.obj.close() if entry.obj is not None else os.close(entry.fd)
    entry.closed = True
    try:
        os.fstat(entry.fd)
    except OSError as error:
        need(error.errno == errno.EBADF, "closed descriptor verification")
    else:
        bad("descriptor remains open")

def attempt(state, owner, operation):
    try:
        operation()
    except BaseException as error:
        state.errors.append((owner, error))  # Keep exceptions AND actual owners.

def new_file(owner, name, data, end):
    entry = open_file(owner, owner.root / name, os.O_RDWR | os.O_CREAT | os.O_EXCL)
    write_all(entry.fd, data, end)
    return entry

def actual_pin(entry, end):
    before, digest, offset = os.fstat(entry.fd), hashlib.sha256(), 0
    need(private(before), "private parent payload")
    while True:
        left(end)
        block = os.pread(entry.fd, min(65536, before.st_size - offset + 1), offset)
        if not block:
            break
        digest.update(block)
        offset += len(block)
        need(offset <= before.st_size, "parent payload grew")
    need(signature(before) == signature(os.fstat(entry.fd)) and offset == before.st_size,
         "parent payload changed")
    return dict(id=signature(before), size=offset, sha256=digest.hexdigest())

def project(owner, native, Task, end):
    pins = []
    for i in range(8):
        body = f"v220-new-pin-{i:02d}\n".encode("ascii")
        entry = new_file(owner, f"pin-{i}", body, end)
        observed = actual_pin(entry, end)
        pins.append(native.FilePin(entry.path, observed["size"], observed["sha256"]))
    tasks = tuple(Task(name=name, question="Synthetic amount?", evidence="",
                       gold_sql="SELECT 1", db_id=name, db_path=str(pins[i + 3].path),
                       tier="simple", tier_source="derived", shape="synthetic",
                       coarse_shape="synthetic", source="fixture")
                  for i, (name, _) in enumerate(native._FIXTURES))
    bounds = native.AttemptBounds(Decimal("1.25"), Decimal(".10"), Decimal("1.15"),
                                  900, 1048576, 4194304, 3600)
    native._validate_bounds(bounds)
    request = native.QualificationRequest(
        tasks, owner.root / "db", owner.root / "model", owner.root / "output",
        tuple(pins[:3]), tuple(pins[3:7]), pins[7], "sha256:" + "a" * 64, bounds)
    return dumps(dict(schema="v220-local-request-projection", **asdict(request)))

def manifest(index, end):
    count, snapshot_width, target, _, _ = CASES[index]
    if index == 1:
        target = DERIVED_C2_BYTES  # True full-width witness, NOT the brief expectation.
    template = dict(root="source", key="", size=MAX_SIZE, sha256="", snapshot_key="")
    need(len(dumps(template)) == 74, "independent empty template arithmetic")
    template["sha256"] = "a" * 64
    need(len(dumps(template)) == 138, "required digest contributes 64 bytes")
    total_keys = target - 1 - 139 * count - snapshot_width * count
    width, extra = divmod(total_keys, count)
    need(6 <= width <= 256 and width + bool(extra) <= 256, "exact length fit")
    records = []
    for i in range(count):
        left(end)
        key_width = width + (i < extra)
        records.append(dict(root="source", key=f"m{i:05d}" + "x" * (key_width - 6),
                            size=MAX_SIZE, sha256="a" * 64,
                            snapshot_key=f"s{i:05d}" + "x" * (snapshot_width - 6)))
    raw = dumps(records)
    need(len(raw) == target, "real canonical length differs from independent target")
    return raw, len(records)

def wait(owner, end):
    code = owner.process.wait(timeout=max(0.0, end - time.monotonic()))
    owner.reaped, owner.reap_at = True, time.monotonic()
    need(owner.reap_at <= end, "late reap")
    return code

def contain(owner, state):
    if owner.process is None or owner.process.returncode is not None:
        return
    if owner.stop_end is None:
        owner.stop_end = min(owner.case_end, state.end, time.monotonic() + 1)
    try:
        owner.process.wait(timeout=0)
        owner.reaped, owner.reap_at = True, time.monotonic()
        return  # No signals after actual reap.
    except subprocess.TimeoutExpired:
        pass
    need(owner.pgid == owner.sid == owner.process.pid, "unknown group retained")
    owner.forced += 1
    attempt(state, owner, lambda: os.killpg(owner.process.pid, signal.SIGKILL))
    wait(owner, owner.stop_end)  # No TERM probe or renewed allowance.

def release(owner, state):
    if owner.process is not None and not owner.reaped:
        return
    for entry in owner.handles:
        if entry.role != "directory":
            attempt(state, owner, lambda e=entry: close(e))
    if any(not h.closed and h.role != "directory" for h in owner.handles):
        return
    for path in owner.paths:
        attempt(state, owner, lambda p=path: p.unlink(missing_ok=True))
    if owner.root.exists():
        attempt(state, owner, owner.root.rmdir)
    owner.removed = not owner.root.exists()
    if owner.removed:
        for entry in owner.handles:
            if entry.role == "directory":
                attempt(state, owner, lambda e=entry: close(e))

def snapshot(owner, path, end):
    entry = open_file(owner, path, os.O_RDONLY, "snapshot")
    need(os.fstat(entry.fd).st_size <= CONTROL, "snapshot cap before read/hash")
    observed = actual_pin(entry, end)
    need(observed["size"] <= CONTROL, "snapshot cap")
    raw = os.pread(entry.fd, CONTROL + 1, 0)
    need(len(raw) == observed["size"] and hashlib.sha256(raw).hexdigest() == observed["sha256"]
         and signature(os.fstat(entry.fd)) == observed["id"], "snapshot identity/hash")
    return raw

class Failure(RuntimeError):
    def __init__(self, state, primary):
        super().__init__("NONPASS bulk-FD spike")
        self.owner, self.primary, self.cleanup_errors = state, primary, state.errors

def run():
    state = NS(root=SCRATCH / ("gpt-v220-" + os.urandom(12).hex()), handles=[],
               paths=set(), cases=[], errors=[], results=[], end=START + 8,
               process=None, reaped=False, removed=False, started=START, permit_tokens=set())
    try:
        native, Task = shapes()
        left(state.end - .25)
        os.mkdir(state.root, 0o700)
        os.chmod(state.root, 0o700)
        need(state.root.resolve(strict=True) == state.root, "canonical private base")
        register(state, os.open(state.root, os.O_RDONLY | os.O_DIRECTORY), "directory", state.root)
        journal = state.root / "journal"
        new_file(state, "journal", b"", state.end - .25)  # Parent exclusive 0600 precreate.
        for index, spec in enumerate(CASES):
            started = time.monotonic()  # Before generation and per-case creation.
            case_end = min(started + 2.5, state.end - .25)
            owner = NS(root=state.root / f"C{index + 1}", handles=[], paths=set(),
                       process=None, reaped=False, reap_at=None, pgid=None, sid=None,
                       forced=0, stop_end=None, removed=False, case_end=case_end,
                       started=started, session=os.urandom(16).hex(), wire=None, popen_calls=0)
            state.cases.append(owner)
            work_end = case_end - .25
            left(work_end)
            os.mkdir(owner.root, 0o700)
            os.chmod(owner.root, 0o700)
            register(owner, os.open(owner.root, os.O_RDONLY | os.O_DIRECTORY), "directory", owner.root)
            request_data = project(owner, native, Task, work_end)
            manifest_data, generated_members = manifest(index, work_end)
            new_file(owner, "request", request_data, work_end)
            new_file(owner, "manifest", manifest_data, work_end)
            request_owner = open_file(owner, owner.root / "request", os.O_RDONLY)
            manifest_owner = open_file(owner, owner.root / "manifest", os.O_RDWR if index == 6 else os.O_RDONLY)
            request_pin, manifest_pin = actual_pin(request_owner, work_end), actual_pin(manifest_owner, work_end)
            need(request_pin["size"] == len(request_data) and manifest_pin["size"] == len(manifest_data)
                 and request_pin["sha256"] == hashlib.sha256(request_data).hexdigest()
                 and manifest_pin["sha256"] == hashlib.sha256(manifest_data).hexdigest(), "actual disk pins")
            supplied = manifest_owner
            if index == 5:
                new_file(owner, "decoy", manifest_data, work_end)
                supplied = open_file(owner, owner.root / "decoy", os.O_RDONLY)
                other = actual_pin(supplied, work_end)
                need(other["id"][1] != manifest_pin["id"][1] and other["size"] == manifest_pin["size"]
                     and other["sha256"] == manifest_pin["sha256"], "real different-inode witness")
            if index == 4:
                manifest_pin = dict(manifest_pin, sha256=(
                    "0" if manifest_pin["sha256"][0] != "0" else "1") + manifest_pin["sha256"][1:])
            owner.pair = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            parent, child = owner.pair
            register(owner, parent.fileno(), "control", obj=parent)
            child_entry = register(owner, child.fileno(), "passed", obj=child)
            request_pass = register(owner, os.dup(request_owner.fd), "passed")
            manifest_pass = register(owner, os.dup(supplied.fd), "passed")
            owner.paths.add(owner.root / "marker")
            need(owner.session not in {c.session for c in state.cases[:-1]}, "fresh session")
            command = (sys.executable, "-I", "-S", "-B", "-c", BOOT, str(PROGRAM),
                       "--worker", str(owner.root), str(request_pass.fd), str(manifest_pass.fd),
                       str(child_entry.fd), owner.session, str(index), repr(case_end),
                       repr(state.end), repr(work_end), "v220")
            # BOOT consumes case/run expiries at -4/-3, never the work lease.
            left(work_end)
            dispatch = time.monotonic()
            owner.process = subprocess.Popen(
                command, pass_fds=(request_pass.fd, manifest_pass.fd, child_entry.fd),
                start_new_session=True, close_fds=True, cwd=str(owner.root),
                env={"PATH": "/usr/bin:/bin", "LANG": "C"}, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL)
            owner.popen_calls += 1
            owner.pgid, owner.sid = os.getpgid(owner.process.pid), os.getsid(owner.process.pid)
            need(owner.pgid == owner.sid == owner.process.pid, "actual new PGID/SID")
            for entry in (request_pass, manifest_pass, child_entry):
                close(entry)  # Passed copies only; owning descriptors remain held.
            wire = owner.wire = Wire(parent, owner.session, index)
            op_end = min(dispatch + 2, work_end)
            wire.send("INIT", 0, op_end, request=request_pin, manifest=manifest_pin)
            reply = wire.receive(1, {"READY": ("pid", "tasks", "members", "sha256"),
                                     "REJECT": ("stage", "code")}, op_end)
            if reply["kind"] == "READY":
                need(spec[4] == 0, "negative fixture reached READY")
                for key, expected in (("pid", owner.process.pid), ("tasks", 4), ("members", spec[0])):
                    need(type(reply[key]) is int and reply[key] == expected, "READY observation")
                need(type(reply["sha256"]) is str and reply["sha256"] == manifest_pin["sha256"], "READY hash")
                challenge_start, token = time.monotonic(), os.urandom(16).hex()
                challenge_end = min(challenge_start + .5, op_end)
                wire.send("CHALLENGE", 2, challenge_end, token=token)
                alive = wire.receive(3, {"ALIVE": ("token",)}, challenge_end)
                need(type(alive["token"]) is str and alive["token"] == token, "challenge echo")
                owner.permit = os.urandom(16).hex()
                need(owner.permit not in state.permit_tokens and owner.permit != owner.session, "fresh permit")
                wire.send("PERMIT", 4, op_end, token=owner.permit)
                state.permit_tokens.add(owner.permit)
                done = wire.receive(5, {"DONE": ("sha256",)}, op_end)
                need(hex_string(done["sha256"]), "DONE digest")
                observed_stage = ""
            else:
                need(type(reply["stage"]) is str and type(reply["code"]) is int
                     and (reply["stage"], reply["code"]) == spec[3:5], "exact refusal stage/code")
                observed_stage = reply["stage"]
            owner.stage = observed_stage
            stop_start = time.monotonic()
            owner.stop_end = min(stop_start + 1, case_end, state.end)
            need(wait(owner, owner.stop_end) == spec[4], "real worker exit mismatch")
            need(parent.recv(1) == b"", "trailing control/no EOF")  # Nonblocking, after reap.
            names = os.listdir(owner.root)  # First marker snapshot, only after actual reap.
            markers = names.count("marker")
            permits = sum(packet["kind"] == "PERMIT" for packet in wire.sent)
            if markers:
                expected_marker = dumps(dict(session=owner.session, permit=owner.permit,
                                             pid=owner.process.pid, case=index))
                need(snapshot(owner, owner.root / "marker", case_end) == expected_marker
                     and hashlib.sha256(expected_marker).hexdigest() == done["sha256"], "actual marker")
            append_journal(journal, dict(kind="case_result", case=index, session=owner.session,
                           pid=owner.process.pid, code=owner.process.returncode,
                           stage=observed_stage, stats={}), case_end, owner)
            rows = [loads(line) for line in snapshot(owner, journal, case_end).splitlines()]
            need(len(rows) == 2 * (index + 1), "actual journal rows")
            for i, row in enumerate(rows):
                c = state.cases[i // 2]
                kind = "worker_exit" if i % 2 == 0 else "case_result"
                need(type(row) is dict and set(row) == {"kind", "case", "session", "pid", "code", "stage", "stats"},
                     "closed journal row")
                need(all(type(row[k]) is int for k in ("case", "pid", "code")), "journal nonbool integers")
                need(row == dict(kind=kind, case=i // 2, session=c.session, pid=c.process.pid,
                     code=c.process.returncode, stage=c.stage, stats=row["stats"]), "actual journal identities")
                stats = row["stats"]
                need(type(stats) is dict and set(stats) == (set(COUNTERS) if i % 2 == 0 else set())
                     and all(type(v) is int and v >= 0 for v in stats.values()), "journal counters")
            counts = rows[-2]["stats"]
            release(owner, state)  # No counter copies/gates before actual cleanup.
            elapsed = time.monotonic() - started
            result = dict(case=index + 1, bytes=len(manifest_data), members=generated_members,
                          stage=observed_stage, code=owner.process.returncode, permits=permits,
                          markers=markers, counts=counts, control_bytes=wire.bytes,
                          popen_identity=id(owner.process), pid=owner.process.pid,
                          popen_calls=owner.popen_calls, messages_sent=len(wire.sent),
                          messages_received=len(wire.received),
                          pgid=owner.pgid, sid=owner.sid, session=owner.session,
                          fds=len(owner.handles), closed=sum(h.closed for h in owner.handles),
                          passed_closed=sum(h.closed and h.role == "passed" for h in owner.handles),
                          removed=owner.removed, seconds=elapsed, journal_rows=len(rows))
            state.results.append(result)
            need(not state.errors and result["fds"] == result["closed"]
                 and result["passed_closed"] == 3 and owner.removed and owner.forced == 0
                 and owner.popen_calls == 1 and generated_members == spec[0]
                 and elapsed <= 2.5 and wire.bytes <= CONTROL, "post-cleanup fixture gates")
            expected_positive = int(index < 2)
            need(result["messages_sent"] == result["messages_received"] == (3 if expected_positive else 1),
                 "actual message counts")
            need(permits == markers == counts["permits"] == counts["markers"] == counts["ready"]
                 == expected_positive and counts["closed"] == 3 and counts["req_parses"] == 1
                 and counts["req_reads"] > 0, "post-operation real counters")
            need(counts["mf_parses"] == int(index in (0, 1, 3))
                 and (counts["mf_reads"] > 0) == (index in (0, 1, 3, 4))
                 and counts["records"] == (spec[0] if index < 2 else 0), "gate-order counters")
            need(len(manifest_data) == spec[2],
                 f"C{index + 1} arithmetic: observed {len(manifest_data)} != brief {spec[2]}; digest value costs 64 bytes/member")
            left(state.end)
        release(state, state)  # Base/journal only after all seven actual reaps.
        total = time.monotonic() - START
        need(total < 8 and len(state.results) == 7 and not state.errors
             and sum(c.popen_calls for c in state.cases) == sum(c.reaped for c in state.cases) == 7
             and all(c.reaped and c.removed and all(h.closed for h in c.handles)
                     and c.forced == 0 and c.process.returncode != 97 for c in state.cases)
             and state.removed and all(h.closed for h in state.handles), "run cleanup/time gate")
        return dict(status="PASS", total_seconds=total, cases=state.results,
                    popen_calls=sum(c.popen_calls for c in state.cases), reaps=sum(c.reaped for c in state.cases),
                    projection="not_original_serialization", member_bytes="not_verified")
    except BaseException as primary:
        for owner in state.cases:
            attempt(state, owner, lambda c=owner: contain(c, state))
            attempt(state, owner, lambda c=owner: release(c, state))
        if all(c.process is None or c.reaped for c in state.cases) and all(c.removed for c in state.cases):
            attempt(state, state, lambda: release(state, state))
        state.observed_end = time.monotonic()
        raise Failure(state, primary) from primary

if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        raise SystemExit(worker(sys.argv[2:]))
    need(len(sys.argv) == 1, "fixed parent mode")
    try:
        receipt = run()
    except Failure as error:
        RETAINED_FAILURE = error  # Actual owners survive for an embedding parent.
        print(json.dumps(dict(status="NONPASS", primary=repr(error.primary),
              cleanup_errors=[repr(e) for _, e in error.cleanup_errors],
              total_seconds=error.owner.observed_end - START,
              cases=error.owner.results), sort_keys=True), flush=True)
        raise
    print(json.dumps(receipt, sort_keys=True), flush=True)
