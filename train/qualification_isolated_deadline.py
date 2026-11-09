"""Fixed isolated deadlines and direct controller/gate roles. SOURCEONLY UNRUN."""
from __future__ import annotations

import json
import os
import select
import signal
import socket
import sys
import time

from train.qualification_isolated_contract import (
    APP, CONTROL_LIMIT, FIXED_SHUTDOWN_NS, MAX_NS, NS, ShutdownSchedule,
    StopTimingFacts, canonical, decode_message, digest, encode_message, integer,
    remaining_ns, require,
)

STAGES = ("cooperate", "worker", "trigger", "command", "reap", "gate", "controller", "release")
STAGE_INDEX = {name: i for i, name in enumerate(STAGES)}
WORKER_ROLE, CONTROLLER_ROLE, GATE_ROLE = "worker", "controller", "gate"
STARTUP_GATE_NS = 2 * NS
ALARM_MARGIN_NS = NS // 2
ALARM_EXIT_CODE = 124
TRIGGER_BYTE = b"\x01"
STOP_ACTION = "stop_owned_app"


class DeadlineExpired(RuntimeError):
    pass


def monotonic_ns():
    return time.monotonic_ns()


def latest_origin_ns(end_ns, teardown_ns):
    integer(end_ns, minimum=1)
    integer(teardown_ns, 20_500_000_000, 1)
    require(end_ns >= teardown_ns + FIXED_SHUTDOWN_NS, "shutdown reserve")
    return end_ns - teardown_ns - FIXED_SHUTDOWN_NS


def shutdown_origin_ns(first_stop_ns, latest_ns):
    return min(integer(first_stop_ns), integer(latest_ns))


def worker_lease_ns(end_ns):
    return integer(end_ns, minimum=1)


def controller_lease_ns(latest_ns, teardown_ns):
    return integer(latest_ns + teardown_ns + FIXED_SHUTDOWN_NS, minimum=1)


def initial_gate_alarm_ns(latest_ns, teardown_ns):
    return integer(latest_ns + 4 * NS + teardown_ns + NS // 2, minimum=1)


def advance_gate_alarm_ns(current_ns, candidate_ns):
    return min(integer(current_ns), integer(candidate_ns))


def early_gate_alarm_ns(current_ns, origin_ns, teardown_ns):
    return advance_gate_alarm_ns(current_ns, origin_ns + 4 * NS + teardown_ns + NS // 2)


def eof_gate_alarm_ns(current_ns, now_ns, teardown_ns):
    return advance_gate_alarm_ns(current_ns, now_ns + teardown_ns + NS // 2)


def alarm_seconds(deadline_ns, now_ns=None):
    return remaining_ns(deadline_ns, monotonic_ns() if now_ns is None else now_ns) / NS


def install_alarm(deadline_ns):
    # setitimer(0) DISABLES an alarm, so expired means exit, not a renewed floor.
    remaining = alarm_seconds(deadline_ns)
    if remaining <= 0:
        os._exit(ALARM_EXIT_CODE)
    signal.signal(signal.SIGALRM, lambda *_: os._exit(ALARM_EXIT_CODE))
    signal.setitimer(signal.ITIMER_REAL, remaining)


class ShutdownLatch:
    def __init__(self, *, end_ns, timing):
        require(type(timing) is StopTimingFacts, "actual binding timing")
        self.end_ns, self.timing = end_ns, timing
        self.latest_ns = latest_origin_ns(end_ns, timing.teardown_ns)
        self._schedule = None
        self.stop_requests = 0

    @property
    def armed(self):
        return self._schedule is not None

    def request_stop(self, now_ns):
        self.stop_requests += 1
        if self._schedule is not None:
            return False
        self._schedule = ShutdownSchedule(
            self.end_ns, shutdown_origin_ns(now_ns, self.latest_ns), self.timing.teardown_ns)
        return True

    def schedule(self):
        require(self._schedule is not None, "first STOP required")
        return self._schedule

    def cutoffs(self):
        return self.schedule().cutoffs

    def stage_remaining_ns(self, stage, now_ns):
        require(stage in STAGE_INDEX, "shutdown stage")
        return remaining_ns(self.cutoffs()[STAGE_INDEX[stage]], now_ns)

    def stage_remaining(self, stage, now_ns):
        result = self.stage_remaining_ns(stage, now_ns)
        if result == 0:
            raise DeadlineExpired("expired fixed stage")
        return result


# Installed in a fresh -I -S -B child. Alarm FIRST, then every first-party
# dependency is verified and retained BEFORE any first-party import executes.
# SDK import custody is independently established by the worker's buffer loader.
# This pins reviewed modules, not all installed dependencies or same-UID races.
BOOTSTRAP = r'''import os,signal,sys,time
expiry=int(sys.argv[1]);left=(expiry-time.monotonic_ns())/1000000000
if not 0<left<=1800:os._exit(124)
signal.signal(signal.SIGALRM,lambda *_:os._exit(124))
signal.setitimer(signal.ITIMER_REAL,left)
import hashlib,json,stat,importlib.abc,importlib.util
from pathlib import Path
entry=Path(sys.argv[2]);entrysha=sys.argv[3];entrysize=int(sys.argv[4]);root=Path(sys.argv[5])
pins=json.loads(sys.argv[6]);role=sys.argv[7]
key="train/qualification_isolated_worker.py" if role=="--worker" else "train/qualification_isolated_deadline.py"
if role not in ("--worker","--controller","--gate") or not root.is_absolute() or ".." in root.parts or entry!=root/key:os._exit(124)
def identity(s):return(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def directory(s):
    if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0,os.getuid()) or (s.st_mode&0o022 and not(s.st_uid==0 and s.st_mode&stat.S_ISVTX)):raise ValueError("owned ancestor")
    return(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid)
records=[]
def opened(name,flags,parent=None):
    record=[None,False,False,None];records.append(record)
    record[0]=os.open(name,flags,dir_fd=parent)
    return record
def close(record):
    if record[0] is not None and not record[1]:
        record[1]=True
        try:os.close(record[0])
        except BaseException as error:
            record[3]=error
            raise
        record[2]=True
def source(path,size,expected):
    ancestry=[];base=opened("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    chain=[base];fd=None
    try:
        rootpin=directory(os.fstat(base[0]))
        for component in path.parts[1:-1]:
            parent=base
            base=opened(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,parent[0]);chain.append(base)
            state=os.fstat(base[0]);named=os.stat(component,dir_fd=parent[0],follow_symlinks=False)
            if not stat.S_ISDIR(state.st_mode) or directory(state)!=directory(named):raise ValueError("ancestor")
            ancestry.append((parent,component,base,directory(state)))
        fd=opened(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,base[0]);a=os.fstat(fd[0])
        if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid not in (0,os.getuid()) or a.st_mode&0o022 or a.st_size!=size or size>4194304:raise ValueError("source")
        def check():
            if identity(a)!=identity(os.fstat(fd[0])) or identity(a)!=identity(os.stat(path.name,dir_fd=base[0],follow_symlinks=False)):raise ValueError("identity")
            if directory(os.fstat(chain[0][0]))!=rootpin:raise ValueError("root identity")
            for parent,name,child,pin in ancestry:
                if directory(os.fstat(child[0]))!=pin or directory(os.stat(name,dir_fd=parent[0],follow_symlinks=False))!=pin:raise ValueError("ancestor")
        chunks=[];count=0;h=hashlib.sha256()
        while True:
            check()
            if time.monotonic_ns()>=expiry:raise ValueError("expired")
            block=os.read(fd[0],min(65536,size-count+1))
            check()
            if time.monotonic_ns()>=expiry:raise ValueError("expired")
            if not block:break
            count+=len(block)
            if count>size:raise ValueError("grew")
            chunks.append(block);h.update(block)
        if count!=size or h.hexdigest()!=expected:raise ValueError("pin")
        check()
        return b"".join(chunks)
    finally:
        primary=sys.exc_info()[1];errors=[]
        for record in ([fd] if fd is not None else [])+list(reversed(chain)):
            if errors:break
            try:close(record)
            except BaseException as error:errors.append(error)
        if errors:
            failure=RuntimeError("bootstrap close custody unknown")
            failure.records=records;failure.primary=primary;failure.cleanup=tuple(errors)
            raise failure from primary
class Buffers(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    _isolated_firstparty=True
    def __init__(self):self.sources={}
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".")[0] not in {"train","bench","ptc"}:return None
        if fullname not in self.sources:raise ImportError("unreviewed firstparty import")
        filename,raw,package=self.sources[fullname]
        return importlib.util.spec_from_file_location(fullname,filename,loader=self,submodule_search_locations=[str(Path(filename).parent)] if package else None)
    def create_module(self,spec):return None
    def exec_module(self,module):
        filename,raw,package=self.sources[module.__name__]
        exec(compile(raw,filename,"exec"),module.__dict__)
loader=Buffers();total=0;seen=set()
for pin in pins:
    k=pin["key"]
    if set(pin)!={"key","size","sha256"} or not k.endswith(".py") or k.startswith("/") or any(p in ("",".","..") for p in k.split("/")) or "\\" in k or k in seen:raise ValueError("source key")
    seen.add(k);raw=source(root/k,pin["size"],pin["sha256"]);total+=len(raw)
    if total>33554432:raise ValueError("source total")
    name=k[:-3].replace("/",".");package=name.endswith(".__init__")
    if package:name=name[:-9]
    if name in loader.sources:raise ValueError("module alias")
    loader.sources[name]=(str(root/k),raw,package)
if key not in seen or len(loader.sources[key[:-3].replace("/",".")][1])!=entrysize or hashlib.sha256(loader.sources[key[:-3].replace("/",".")][1]).hexdigest()!=entrysha:raise ValueError("entry pin")
if any(n.split(".")[0] in {"train","bench","ptc"} for n in sys.modules):raise ValueError("fresh firstparty process")
sys.meta_path.insert(0,loader);sys.path.insert(0,str(root))
sys.argv=[str(entry),*sys.argv[7:]]
module=__import__(key[:-3].replace("/","."),fromlist=["main"])
raise SystemExit(module.main())
'''


def child_argv(*, interpreter, lease_ns, entry_path, entry_sha256, entry_size,
               source_root, role, facts, source_pins):
    require(role in {"--worker", "--controller", "--gate"}, "fixed child role")
    integer(lease_ns, minimum=1)
    digest(entry_sha256)
    integer(entry_size, 4 * 1024**2, 1)
    rows = [dict(key=p.key, size=p.size, sha256=p.sha256) for p in source_pins]
    return [interpreter, "-I", "-S", "-B", "-c", BOOTSTRAP,
            str(lease_ns), entry_path, entry_sha256, str(entry_size), source_root,
            canonical(rows).decode("ascii"), role, *facts]


def verify_anchored_file(dir_fd, key, *, size, sha256, deadline_ns):
    # Compatibility helper uses the same actual custody as production, not a
    # hidden open+validate helper that loses its FD if validation/close fails.
    from train.qualification_isolated_owner import _Anchor, _Registry, _stream_file
    registry = _Registry()
    try:
        anchor = _Anchor.borrowed(registry, dir_fd)
        file = anchor.open_file(key, os.O_RDONLY, private=False)
        require(_stream_file(file, deadline_ns=deadline_ns, size=size)[:2]
                == (size, digest(sha256)), "actual file pin")
    except BaseException as primary:
        registry.primary = primary
        raise
    finally:
        registry.close_all()


class _Frames:
    """Incremental parser: never owns a blocking partial-frame receive loop."""
    def __init__(self, session):
        self.session, self.sequence, self.buffer = digest(session), 0, bytearray()

    @property
    def pending(self):
        if len(self.buffer) < 4:
            return False
        size = int.from_bytes(self.buffer[:4], "big")
        return not 1 <= size <= CONTROL_LIMIT or len(self.buffer) >= size + 4

    def extract(self, allowed):
        if len(self.buffer) < 4:
            return None
        size = int.from_bytes(self.buffer[:4], "big")
        require(1 <= size <= CONTROL_LIMIT, "control cap")
        if len(self.buffer) < size + 4:
            return None
        frame = bytes(self.buffer[:size + 4])
        del self.buffer[:size + 4]
        self.sequence += 1
        return decode_message(frame, session=self.session, seq=self.sequence, allowed=allowed)

    def feed(self, sock, allowed):
        message = self.extract(allowed)
        if message is not None:
            return message
        try:
            raw = sock.recv(CONTROL_LIMIT + 4 - len(self.buffer))
        except (BlockingIOError, InterruptedError):
            return None
        if not raw:
            raise EOFError("control EOF, including partial frame")
        self.buffer.extend(raw)
        return self.extract(allowed)


def _send(sock, session, seq, kind, body, cutoff):
    raw = memoryview(encode_message(
        dict(v=1, session=session, seq=seq, kind=kind, body=body),
        session=session, seq=seq, allowed=frozenset({kind})))
    while raw:
        left = cutoff - monotonic_ns()
        if left <= 0:
            raise DeadlineExpired("fixed child write")
        _, writable, _ = select.select([], [sock], [], left / NS)
        if writable:
            try:
                count = sock.send(raw)
            except (BlockingIOError, InterruptedError):
                continue
            require(count > 0, "child zero write")
            raw = raw[count:]


def _parse_child_args(argv, role, required):
    require(len(argv) >= 2 and argv[1] == "--" + role, "fixed child role")
    require(len(argv[2:]) % 2 == 0, "fact pairs")
    facts = {}
    for key, value in zip(argv[2::2], argv[3::2]):
        require(key.startswith("--") and key[2:] not in facts, "unique named facts")
        facts[key[2:]] = value
    require(set(facts) == set(required), "closed child arguments")
    return facts


_COMMON = ("control", "trigger", "journal", "session", "end", "teardown", "arm-end", "app")


def _facts(argv, role):
    extra = (() if role == "controller" else
             ("executable", "command-size", "command-sha256", "cwd", "environment"))
    facts = _parse_child_args(argv, role, (*_COMMON, *extra))
    facts["end"] = integer(int(facts["end"]), minimum=1)
    facts["teardown"] = integer(int(facts["teardown"]), 20_500_000_000, 1)
    facts["arm-end"] = integer(int(facts["arm-end"]), facts["end"], 1)
    digest(facts["session"])
    require(APP.fullmatch(facts["app"]) is not None, "sealed actual App ID")
    return facts


def _sockets(facts):
    # Child-local borrowed copies, retained before socket validation.
    from train.qualification_isolated_owner import _Registry
    registry = _Registry()
    records = []
    try:
        numbers = [integer(int(facts[n]), 2**31 - 1, 3)
                   for n in ("control", "trigger", "journal")]
        require(len(set(numbers)) == 3, "no inherited stopper descriptor alias")
        for number in numbers:
            record = registry.acquire("descriptor", None, lambda number=number: number)
            records.append(record)
        journal = records.pop()
        for record in records:
            registry.wrap_socket(record)
        from train.qualification_isolated_owner import _regular
        import fcntl
        _regular(os.fstat(journal.handle), True)
        require(fcntl.fcntl(journal.handle, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY,
                "private inherited journal writer")
        for record in records:
            record.handle.setblocking(False)
            require(record.handle.family == socket.AF_UNIX, "private inherited Unix socket")
    except BaseException as error:
        registry.primary = error
        _RETAINED_CHILD_FAILURES.append((registry, error))
        raise
    return registry, records


def _arm(frame, facts):
    body = frame["body"]
    require(body["end_ns"] == facts["end"]
            and body["teardown_ns"] == facts["teardown"]
            and body["origin_ns"] == latest_origin_ns(facts["end"], facts["teardown"])
            and body["app_id"] == facts["app"], "exact sealed ARM facts")
    return body["permit"]


def _receive_arm(control, trigger, frames, facts, *, gate):
    while monotonic_ns() < facts["arm-end"]:
        readable, _, _ = select.select(
            [control, trigger] if gate else [control], [], [],
            0 if frames.pending else max(0, facts["arm-end"] - monotonic_ns()) / NS)
        if gate and trigger in readable:
            trigger.recv(CONTROL_LIMIT)
            return False  # Readable trigger/EOF has priority over partial control.
        if control in readable or frames.pending:
            frame = frames.feed(control, frozenset({"ARM"}))
            if frame is not None:
                permit = _arm(frame, facts)
                _send(control, facts["session"], 1, "ARMED", {"permit": permit}, facts["arm-end"])
                return True
    raise DeadlineExpired("actual binding arm budget")


def controller_main(argv):
    facts = _facts(argv, "controller")
    registry, records = _sockets(facts)
    control, trigger = (r.handle for r in records)
    frames = _Frames(facts["session"])
    latest = latest_origin_ns(facts["end"], facts["teardown"])
    origin = latest
    primary = None
    try:
        try:
            _receive_arm(control, trigger, frames, facts, gate=False)
            while monotonic_ns() < latest:
                readable, _, _ = select.select(
                    [control], [], [], 0 if frames.pending else max(0, latest - monotonic_ns()) / NS)
                if control in readable or frames.pending:
                    message = frames.feed(control, frozenset({"EARLY_STOP"}))
                    if message is not None:
                        require(message["body"]["origin_ns"] <= latest, "early origin")
                        origin = message["body"]["origin_ns"]
                        break
        except (EOFError, ValueError, DeadlineExpired, OSError):
            origin = min(monotonic_ns(), latest)
            pass  # Lost/malformed ARM/control always triggers, never waits until E.
        try:
            trigger.send(TRIGGER_BYTE)  # ONE nonblocking attempt.
        except (BlockingIOError, OSError):
            pass
        finally:
            try:
                trigger.shutdown(socket.SHUT_WR)
            finally:
                registry.close(records[1])  # SOLE trigger writer, unconditional EOF.
        try:
            _send(control, facts["session"], 2, "STOP", {},
                  min(origin + NS, facts["end"]))
        except (OSError, DeadlineExpired):
            pass  # Parent independently observes the actual controller exit.
        return 0  # No post-trigger FINISH wait, no sync old-watchdog route.
    except BaseException as error:
        primary = registry.primary = error
        raise
    finally:
        try:
            registry.close_all()
        except BaseException:
            if primary is None:
                raise
            # Retained actual registry keeps BOTH errors until this process exits.
            _RETAINED_CHILD_FAILURES.append((registry, primary))
            raise


_RETAINED_CHILD_FAILURES = []


def _prepare_gate_exec(facts, registry, command_registry, alarm):
    """Finish fallible file/pipe/cwd work BEFORE acknowledging ARM."""
    from pathlib import Path
    from train.qualification_isolated_owner import _Anchor, _stream_file, _write_all
    cutoff = min(alarm, facts["arm-end"])
    executable = Path(facts["executable"])
    anchor = _Anchor.absolute(command_registry, executable.parent, private=True)
    file = anchor.open_file(executable.name, os.O_RDONLY, private=False)
    require(file.identity[4] == os.getuid() and not file.identity[2] & 0o022
            and bool(file.identity[2] & 0o111), "original trusted executable metadata")
    require(_stream_file(file, deadline_ns=cutoff, size=int(facts["command-size"]))[:2]
            == (int(facts["command-size"]), digest(facts["command-sha256"])), "original command pin")
    environment = json.loads(facts["environment"])
    ambient = dict(os.environ)
    if "LC_CTYPE" not in environment and ambient.get("LC_CTYPE") in {"C", "C.UTF-8", "UTF-8"}:
        ambient.pop("LC_CTYPE")
    require(type(environment) is dict and environment == ambient
            and set(environment) <= {"PATH", "HOME", "LANG", "LC_ALL"}
            and {"PATH", "HOME"} <= set(environment), "sealed restricted environment")
    # Interpreter may add a public LC_CTYPE on macOS; owner passes the original
    # command environment to exec, never a reconstructed ambient environment.
    read_record = command_registry.reserve("descriptor", None)
    write_record = command_registry.reserve("descriptor", None)
    read_fd, write_fd = os.pipe()
    command_registry.attach(read_record, read_fd)
    command_registry.attach(write_record, write_fd)
    _write_all(write_fd, canonical({"action": STOP_ACTION, "app_id": facts["app"]}), cutoff)
    command_registry.close(write_record)
    stdin_record = command_registry.reserve("descriptor", None)
    command_registry.attach(stdin_record, os.dup2(read_fd, 0, inheritable=True))
    # The actual fd 0 now belongs to the original same-PID executable. Keep its
    # generation retained here, deliberately not closed before exec.
    stdin_record.kind = "exec-stdin"
    command_registry.close_all([r for r in command_registry.records if r is not stdin_record])
    # Control/trigger/journal are intentionally handed to kernel exec, not
    # explicitly closed after triggering. An unknown close there must not
    # prevent the already verified original command from executing.
    for record in registry.records:
        fd = record.handle if record.kind == "descriptor" else record.handle.fileno()
        os.set_inheritable(fd, False)
        require(not os.get_inheritable(fd), "gate inherited copy CLOEXEC")
    os.chdir(facts["cwd"])
    require(monotonic_ns() < cutoff, "gate executable ready within original arm budget")
    return executable, environment


def gate_main(argv):
    facts = _facts(argv, "gate")
    alarm = initial_gate_alarm_ns(
        latest_origin_ns(facts["end"], facts["teardown"]), facts["teardown"])
    install_alarm(alarm)  # Bootstrap installed this exact absolute alarm before I/O.
    registry, records = _sockets(facts)
    from train.qualification_isolated_owner import _Registry
    command_registry = _Registry()
    control, trigger = (r.handle for r in records)
    frames = _Frames(facts["session"])
    try:
        executable, environment = _prepare_gate_exec(facts, registry, command_registry, alarm)
        try:
            armed = _receive_arm(control, trigger, frames, facts, gate=True)
            if armed:
                while True:
                    left = alarm - monotonic_ns()
                    if left <= 0:
                        os._exit(ALARM_EXIT_CODE)
                    readable, _, _ = select.select(
                        [trigger, control], [], [], 0 if frames.pending else left / NS)
                    if trigger in readable:
                        trigger.recv(CONTROL_LIMIT)  # Byte/EOF has priority over partial control.
                        break
                    if control in readable or frames.pending:
                        message = frames.feed(control, frozenset({"EARLY_STOP"}))
                        if message is not None:
                            origin = message["body"]["origin_ns"]
                            require(origin <= latest_origin_ns(facts["end"], facts["teardown"]),
                                    "early gate origin")
                            alarm = early_gate_alarm_ns(alarm, origin, facts["teardown"])
                            install_alarm(alarm)
                            break
        except (EOFError, ValueError, DeadlineExpired, OSError):
            pass  # Broken/partial control triggers original stop, not early gate kill.
        alarm = eof_gate_alarm_ns(alarm, monotonic_ns(), facts["teardown"])
        install_alarm(alarm)  # Advance only; timer survives same-PID exec.
        os.execve(str(executable), [str(executable)], environment)
        return 1
    except BaseException as primary:
        registry.primary = command_registry.primary = primary
        _RETAINED_CHILD_FAILURES.append((registry, command_registry, primary))
        raise


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--controller":
        return controller_main(list(sys.argv))
    require(len(sys.argv) >= 2 and sys.argv[1] == "--gate", "fixed role")
    return gate_main(list(sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
