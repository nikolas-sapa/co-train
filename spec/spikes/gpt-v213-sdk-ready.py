# Sanitized public reference, UNRUN derivative. No execution authority.
"""SOURCEONLY UNRUN: fixed three-process local SDK READY experiment, not qualification."""
import time

HARNESS_START = time.monotonic()  # Includes subsequent stdlib imports and all fixtures.

import asyncio
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace

PARENT = Path("/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06")
PROGRAM = PARENT / "sol-v159-transport-runner/spec/spikes/gpt-v213-sdk-ready.py"
PYTHON = PARENT / "modal-tools-2026-11-06/venv/bin/python"
SITE = PARENT / "modal-tools-2026-11-06/venv/lib/python3.12/site-packages"
SCRATCH = Path("/qualification-reference/scratch")
MAX_CONTROL = 8192

# Immutable alarm precedes the accepted bootstrap's first file I/O. The remainder
# retains the reviewed nofollow/size/hash/identity bootstrap, not interpreter reads.
BOOTSTRAP = r"""import os,signal,sys,time
expiry=min(time.monotonic()+2.5,float(sys.argv[-2]),float(sys.argv[-1]))
remaining=expiry-time.monotonic()
if not 0 < remaining <= 2.5: os._exit(124)
signal.signal(signal.SIGALRM,lambda *_: os._exit(124))
signal.setitimer(signal.ITIMER_REAL,remaining)
import hashlib,stat
from pathlib import Path
p=Path(sys.argv[1]);expected=sys.argv[2];size=int(sys.argv[3])
assert p.is_absolute() and p.resolve(strict=True)==p
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
 a=os.fstat(fd);assert stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==os.geteuid() and a.st_size==size and size<=131072
 with os.fdopen(fd,"rb",closefd=False) as f:raw=f.read(size+1)
 b=os.fstat(fd);c=p.lstat()
 identity=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_nlink,x.st_uid,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
 assert identity(a)==identity(b)==identity(c) and len(raw)==size and hashlib.sha256(raw).hexdigest()==expected
finally:os.close(fd)
sys.argv=[str(p),*sys.argv[4:]]
exec(compile(raw,str(p),"exec"),{"__name__":"__main__","__file__":str(p)})
"""


class Budget(TimeoutError):
    pass


def left(expiry):
    remaining = expiry - time.monotonic()
    if remaining <= 0:
        raise Budget("fixed expiry reached")
    return remaining


def need(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate control key")
        result[key] = value
    return result


def nonfinite(value):
    raise ValueError("nonfinite control number")


class Wire:
    def __init__(self, connection):
        self.socket, self.moved = connection, 0
        connection.setblocking(False)

    def transfer(self, data, size, expiry, sending):
        result = bytearray()
        offset = 0
        while offset < size:
            timeout = left(expiry)
            readers, writers, _ = select.select(
                [] if sending else [self.socket],
                [self.socket] if sending else [], [], timeout)
            if not readers and not writers:
                raise Budget("control I/O expiry")
            try:
                chunk = (self.socket.send(data[offset:]) if sending
                         else self.socket.recv(size - offset))
            except (BlockingIOError, InterruptedError):
                continue
            count = chunk if sending else len(chunk)
            need(count > 0, "control EOF/zero write")
            offset += count
            self.moved += count
            need(self.moved <= MAX_CONTROL, "aggregate control cap")
            if not sending:
                result.extend(chunk)
        left(expiry)
        return bytes(result)

    def send(self, document, expiry):
        body = json.dumps(document, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
        need(0 < len(body) <= 2048, "control frame cap")
        frame = struct.pack("!I", len(body)) + body
        self.transfer(frame, len(frame), expiry, True)

    def receive(self, expiry):
        header = self.transfer(b"", 4, expiry, False)
        size, = struct.unpack("!I", header)
        need(0 < size <= 2048 and self.moved + size <= MAX_CONTROL, "control cap")
        raw = self.transfer(b"", size, expiry, False)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=nonfinite)
        need(type(value) is dict, "control object required")
        return value


def message(kind, sequence, index, nonce, **extra):
    return dict(v=1, kind=kind, seq=sequence, case=index, nonce=nonce, **extra)


def check_message(value, kind, sequence, index, nonce, extra=()):
    need(set(value) == {"v", "kind", "seq", "case", "nonce", *extra},
         "control exact keys")
    for key, expected in (("v", 1), ("seq", sequence), ("case", index)):
        need(type(value[key]) is int and value[key] == expected, "control integer")
    need(type(value["kind"]) is str and value["kind"] == kind, "control kind")
    need(type(value["nonce"]) is str and value["nonce"] == nonce, "control nonce")


def environment(root):
    return {"HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
            "PATH": "/usr/bin:/bin", "LANG": "C",
            "MODAL_CONFIG_PATH": str(root / "home/empty-modal.toml")}


def sdk_facts(root):
    """Accepted audit whitelist and live negative controls, entirely in child."""
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
         "worker isolation flags")
    expected_env = environment(root)
    need(set(os.environ) <= set(expected_env) | {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"},
         "worker environment keys")
    need(all(os.environ.get(k) == v for k, v in expected_env.items()), "worker environment")
    need(os.environ.get("LC_CTYPE", "C") in {"C", "UTF-8", "C.UTF-8"}, "LC_CTYPE")
    if "__CF_USER_TEXT_ENCODING" in os.environ:
        fields = os.environ["__CF_USER_TEXT_ENCODING"].split(":")
        need(len(fields) == 3 and all(
            3 <= len(p) <= 18 and p.startswith("0x")
            and all(c in "0123456789abcdefABCDEF" for c in p[2:]) for p in fields),
            "public OS encoding")
    for directory in (root, root / "home", root / "tmp"):
        info = directory.lstat()
        need(directory.resolve(strict=True) == directory and stat.S_ISDIR(info.st_mode)
             and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
             "private directory")
    config = root / "home/empty-modal.toml"
    info = config.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == 0
         and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
         "private empty config")
    stdlib = Path(sys.base_prefix).resolve(strict=True) / "lib/python3.12"
    roots = (SITE.resolve(strict=True), stdlib, root,
             Path("/usr/share/zoneinfo").resolve(strict=False))
    files = {Path("/dev/null").resolve(), Path("/dev/urandom").resolve(),
             Path("/etc/localtime").resolve(strict=False),
             (Path(sys.base_prefix) / "lib/python312.zip").resolve(strict=False),
             (Path(sys.prefix) / "pyvenv.cfg").resolve(strict=False)}
    plist = Path("/System/Library/CoreServices/SystemVersion.plist").resolve(strict=True)
    info = plist.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
         and info.st_size <= 16384 and not stat.S_IMODE(info.st_mode) & 0o022,
         "exact public OS plist")
    files.add(plist)
    counts, denied, expected = {"client": 0, "network": 0}, [], []
    armed = None

    class Denied(RuntimeError):
        pass

    def refuse(kind):
        nonlocal armed
        if armed == kind:
            expected.append(kind)
            armed = None
        else:
            denied.append(kind)  # Sticky even if metadata swallows RuntimeError.
        raise Denied(kind)

    def canonical(value):
        if not isinstance(value, (str, bytes, Path)):
            refuse("descriptor_path")
        return Path(os.fsdecode(value)).resolve(strict=False)

    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                     "socket.gethostbyname", "socket.gethostbyaddr"}:
            counts["network"] += 1
            refuse("network")
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.exec",
                     "os.fork", "os.forkpty", "os.kill", "os.killpg"}:
            refuse(event)
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.truncate", "os.chmod",
                     "os.chown", "os.utime", "os.rename", "os.link", "os.symlink",
                     "os.chdir", "os.chflags", "os.setxattr", "os.removexattr"}:
            refuse("filesystem_mutation")
        if event in {"os.listdir", "os.scandir"}:
            frame = sys._getframe(1)
            while frame is not None:
                module = frame.f_globals.get("__name__", "")
                if type(module) is str and (
                    module.startswith(("pkg_resources", "pydantic.plugin"))
                    or (module.startswith("importlib.metadata")
                        and frame.f_code.co_name != "<module>")
                ):
                    refuse("installed_distribution_enumeration")
                frame = frame.f_back
            if not any(canonical(args[0]).is_relative_to(base) for base in roots):
                refuse("directory_outside_read_roots")
        if event == "open":
            flags = args[2]
            if type(flags) is int and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                refuse("filesystem_mutation")
            path = canonical(args[0])
            if path.name == "entry_points.txt" or "/.secrets/" in str(path) or path.name.startswith(".env"):
                refuse("credential_or_plugin_metadata")
            if path.name == ".modal.toml" and path != config:
                refuse("credential_file")
            if path not in files and not any(path.is_relative_to(base) for base in roots):
                refuse("file_outside_read_roots")

    def deny_client(*args, **kwargs):
        counts["client"] += 1
        refuse("client")

    def import_call_guard(frame, event, arg):
        if (event == "call" and frame.f_globals.get("__name__") == "modal.client"
                and frame.f_code.co_qualname in {"_Client.__init__", "_Client.from_env"}):
            deny_client()

    sys.addaudithook(audit)
    need(sys.getprofile() is None and threading.getprofile() is None, "prior profiler")
    sys.setprofile(import_call_guard)
    threading.setprofile(import_call_guard)
    sys.path.insert(0, str(roots[0]))
    try:
        import modal
        from modal.client import _Client
        _Client.from_env = classmethod(deny_client)
        _Client.__init__ = deny_client
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
    origin = Path(modal.__file__).resolve(strict=True)
    need(modal.__version__ == "1.6.3" and origin == roots[0] / "modal/__init__.py", "real SDK origin/version")
    from modal._utils.async_utils import synchronize_api, synchronizer
    from modal.io_streams import _StreamReader, _StreamReaderThroughServerParams

    def construct():
        return _StreamReader(_StreamReaderThroughServerParams(
            file_descriptor=1, object_id="sb-constructor-control", client=object()), text=True)

    ordinary, refusals, readers = [], [], []
    before = counts.copy()

    async def ordinary_control():
        ordinary.append(asyncio.get_running_loop())
        try:
            construct()
        except AssertionError as error:
            refusals.append(type(error).__name__)
        else:
            raise AssertionError("ordinary-loop reader accepted")

    asyncio.run(ordinary_control())

    async def sdk_constructor():
        loop = asyncio.get_running_loop()
        sdk_loop = synchronizer._get_loop(start=False)
        reader = construct()
        need(loop is sdk_loop and loop is not ordinary[0], "genuine SDK loop identity")
        need(type(reader) is _StreamReader and reader.file_descriptor == 1, "real raw fd1 reader")
        readers.append(reader)
        return {"running": id(loop), "synchronizer": id(sdk_loop),
                "ordinary": id(ordinary[0])}

    synchronizer.no_io_translation(sdk_constructor)
    wrapped = synchronize_api(sdk_constructor)

    async def bridge():
        return await wrapped.aio()

    loops = asyncio.run(bridge())
    deltas = {key: counts[key] - before[key] for key in counts}
    need(refusals == ["AssertionError"] and len(readers) == 1
         and counts == {"client": 0, "network": 0} and not denied, "constructor guards")
    constructor_end = counts.copy()

    def control(kind, operation):
        nonlocal armed
        need(armed is None, "control already armed")
        first = len(expected)
        armed = kind
        try:
            operation()
        except Denied as error:
            need(str(error) == kind and armed is None, "wrong denial")
        else:
            need(kind == "installed_distribution_enumeration" and armed is None,
                 "guard did not deny")
        finally:
            armed = None
        need(expected[first:] == [kind], "sticky control witness")

    import importlib.metadata
    control("installed_distribution_enumeration", lambda: list(
        importlib.metadata.distributions(path=[str(root / "tmp")])))
    control("client", lambda: _Client.from_env())
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        control("network", lambda: connection.connect(("127.0.0.1", 9)))
    outside = root.parent / (root.name + "-must-not-create")
    control("filesystem_mutation", lambda: open(outside, "wb"))
    control("filesystem_mutation", lambda: open(root / "tmp/escape", "wb"))
    intentional = {key: counts[key] - constructor_end[key] for key in counts}
    need(intentional == {"client": 1, "network": 1} and not denied, "negative controls")
    return {"version": modal.__version__,
            "origin_sha256": hashlib.sha256(str(origin).encode()).hexdigest(),
            "reader_type": type(readers[0]).__module__ + "." + type(readers[0]).__name__,
            "fd": readers[0].file_descriptor, "loops": loops,
            "ordinary_refusals": len(refusals), "sdk_constructions": len(readers),
            "constructor_deltas": deltas, "intentional_calls": intentional,
            "expected_denials": expected, "unexpected_denials": denied}


def check_facts(facts):
    need(type(facts) is dict and set(facts) == {
        "version", "origin_sha256", "reader_type", "fd", "loops", "ordinary_refusals",
        "sdk_constructions", "constructor_deltas", "intentional_calls",
        "expected_denials", "unexpected_denials"}, "READY facts keys")
    for key, value in (("version", "1.6.3"),
                       ("reader_type", "modal.io_streams._StreamReader"),
                       ("origin_sha256", hashlib.sha256(
                           str(SITE.resolve(strict=True) / "modal/__init__.py").encode()).hexdigest())):
        need(type(facts[key]) is str and facts[key] == value, "READY real SDK witness")
    for key in ("fd", "ordinary_refusals", "sdk_constructions"):
        need(type(facts[key]) is int and facts[key] == 1, "READY constructor count/fd")
    loops = facts["loops"]
    need(type(loops) is dict and set(loops) == {"running", "synchronizer", "ordinary"}
         and all(type(v) is int and v > 0 for v in loops.values()), "READY loop types")
    need(loops["running"] == loops["synchronizer"] != loops["ordinary"], "READY loop identity")
    for key, expected in (("constructor_deltas", 0), ("intentional_calls", 1)):
        values = facts[key]
        need(type(values) is dict and set(values) == {"client", "network"}
             and all(type(v) is int and v == expected for v in values.values()), "READY counters")
    need(type(facts["expected_denials"]) is list and facts["expected_denials"] == [
        "installed_distribution_enumeration", "client", "network",
        "filesystem_mutation", "filesystem_mutation"], "READY intentional denials")
    need(type(facts["unexpected_denials"]) is list and not facts["unexpected_denials"],
         "READY unexpected denial")


def worker():
    need(len(sys.argv) == 8 and sys.argv[1] == "--worker", "fixed worker arguments")
    fd, root, index, nonce = int(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    case_end, run_end = float(sys.argv[6]), float(sys.argv[7])
    need(fd >= 3 and index in (0, 1, 2) and len(nonce) == 32
         and all(c in "0123456789abcdef" for c in nonce), "worker primitives")
    need(root.is_absolute() and root.name == f"case-{index}"
         and root.parent.parent == SCRATCH and root.parent.name.startswith("gpt-v213-"),
         "fixed private root")
    need(math.isfinite(case_end) and math.isfinite(run_end) and case_end <= run_end,
         "fixed finite expiries")
    left(case_end)
    need(signal.getitimer(signal.ITIMER_REAL)[0] > 0, "bootstrap alarm missing")
    with socket.socket(fileno=fd) as connection:
        need(connection.family == socket.AF_UNIX and connection.type == socket.SOCK_STREAM,
             "inherited Unix control")
        wire = Wire(connection)
        facts = sdk_facts(root)
        check_facts(facts)
        io_end = min(time.monotonic() + .5, case_end, run_end)
        wire.send(message("READY", 0, index, nonce, pid=os.getpid(),
                          pgid=os.getpgid(0), sid=os.getsid(0), facts=facts), io_end)
        finish = wire.receive(io_end)
        check_message(finish, "FINISH", 1, index, nonce)
        wire.send(message("DONE", 2, index, nonce), io_end)
    # Normal interpreter exit, including SDK daemon-thread exit, is measured by parent wait.


class Failure(RuntimeError):
    def __init__(self, owner, primary):
        super().__init__("NONPASS: fresh SDK READY spike")
        self.owner, self.primary = owner, primary
        self.cleanup_errors = owner.errors  # Actual exceptions and owning objects.


def record_error(state, owner, operation):
    try:
        operation()
    except BaseException as error:
        state.errors.append((owner, error))


def fd_closed(fd):
    try:
        os.fstat(fd)
    except OSError as error:
        need(error.errno == errno.EBADF, "unexpected closed-FD error")
    else:
        raise ValueError("descriptor still open")


def reap(owner, expiry):
    code = owner.process.wait(timeout=max(0.0, expiry - time.monotonic()))
    owner.reaped_at = time.monotonic()
    owner.reaped = True
    need(owner.reaped_at <= expiry, "late reap")
    return code


def contain(owner, state):
    process = owner.process
    if process is None or process.returncode is not None:
        return
    if owner.stop_end is None:
        owner.stop_end = min(owner.case_end, state.expiry, time.monotonic() + 1)
    try:
        process.wait(timeout=0)
        owner.reaped = True
        owner.reaped_at = time.monotonic()
        return  # Never signal after this actual reap.
    except subprocess.TimeoutExpired:
        pass
    need(owner.pgid == owner.sid == process.pid, "unverified group retained, not signalled")
    owner.forced += 1
    # Keep signal and reap errors separately, without one masking the other.
    record_error(state, owner, lambda: os.killpg(process.pid, signal.SIGKILL))
    reap(owner, owner.stop_end)  # Popen identity only, never control payload.


def release_case(owner, state):
    if owner.process is not None and owner.process.returncode is None:
        return  # Retain sockets, directory FD and root until actual reap.
    for connection in owner.sockets:
        if connection.fileno() != -1:
            record_error(state, owner, connection.close)
    for path in (owner.root / "tmp/escape", owner.root / "home/empty-modal.toml"):
        if path.is_symlink() or path.exists():
            record_error(state, owner, path.unlink)
    for path in (owner.root / "tmp", owner.root / "home", owner.root):
        if path.exists():
            record_error(state, owner, path.rmdir)
    owner.removed = not owner.root.exists()
    if owner.removed and owner.root_fd is not None and not owner.fd_released:
        def close_root():
            os.close(owner.root_fd)
            owner.fd_released = True
            fd_closed(owner.root_fd)
        record_error(state, owner, close_root)


def release_base(state):
    if any(not owner.removed for owner in state.cases):
        return
    if state.base is not None and state.base.exists():
        state.base.rmdir()
    if state.base_fd is not None and not state.base_fd_released:
        os.close(state.base_fd)
        state.base_fd_released = True
        fd_closed(state.base_fd)


def run_spike():
    state = SimpleNamespace(expiry=HARNESS_START + 8, base=None, base_fd=None,
                            base_fd_released=False, cases=[], errors=[], results=[])
    try:
        need(threading.active_count() == 1 and not any(
            name == "modal" or name.startswith("modal.") for name in sys.modules),
            "coordinator must be single-threaded and SDK-free")
        left(state.expiry)
        need(Path(__file__).resolve(strict=True) == PROGRAM, "fixed spike program")
        raw = PROGRAM.read_bytes()  # This source only, never interpreter binary.
        need(0 < len(raw) <= 131072, "bootstrap source cap")
        digest = hashlib.sha256(raw).hexdigest()
        state.base = Path(tempfile.mkdtemp(prefix="gpt-v213-", dir=str(SCRATCH)))
        os.chmod(state.base, 0o700)
        need(state.base.resolve(strict=True) == state.base, "canonical private base")
        state.base_fd = os.open(state.base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for index in range(3):
            start = time.monotonic()
            owner = SimpleNamespace(
                root=state.base / f"case-{index}", case_end=min(start + 2.5, state.expiry),
                root_fd=None, fd_released=False, process=None, sockets=[],
                pgid=None, sid=None, reaped=False, reaped_at=None, forced=0,
                stop_end=None, removed=False, started=start, dispatch=None, ready_at=None,
                nonce=None, frames=[])
            state.cases.append(owner)
            left(owner.case_end)
            owner.root.mkdir(mode=0o700)
            os.chmod(owner.root, 0o700)
            owner.root_fd = os.open(owner.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for directory in ("home", "tmp"):
                (owner.root / directory).mkdir(mode=0o700)
                os.chmod(owner.root / directory, 0o700)
            with (owner.root / "home/empty-modal.toml").open("xb") as config:
                os.fchmod(config.fileno(), 0o600)
            outside = state.base / (owner.root.name + "-must-not-create")
            os.symlink(outside, owner.root / "tmp/escape")
            parent_socket, child_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            owner.sockets.extend((parent_socket, child_socket))
            nonce = os.urandom(16).hex()
            need(nonce not in {result["nonce"] for result in state.results}, "nonce repeated")
            owner.nonce = nonce
            command = (str(PYTHON), "-I", "-S", "-B", "-c", BOOTSTRAP,
                       str(PROGRAM), digest, str(len(raw)), "--worker",
                       str(child_socket.fileno()), str(owner.root), str(index), nonce,
                       repr(owner.case_end), repr(state.expiry))
            left(owner.case_end)
            dispatch = time.monotonic()
            owner.dispatch = dispatch
            owner.process = subprocess.Popen(
                command, env=environment(owner.root), cwd=str(owner.root),
                pass_fds=(child_socket.fileno(),), close_fds=True, start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            owner.pgid = os.getpgid(owner.process.pid)
            owner.sid = os.getsid(owner.process.pid)
            need(owner.pgid == owner.sid == owner.process.pid, "actual new session")
            wire = Wire(parent_socket)
            ready = wire.receive(min(dispatch + 2, owner.case_end, state.expiry))
            owner.frames.append(ready)
            check_message(ready, "READY", 0, index, nonce, ("pid", "pgid", "sid", "facts"))
            for key, value in (("pid", owner.process.pid), ("pgid", owner.pgid), ("sid", owner.sid)):
                need(type(ready[key]) is int and ready[key] == value, "Popen identity witness")
            check_facts(ready["facts"])
            ready_at = time.monotonic()
            owner.ready_at = ready_at
            need(ready_at - dispatch <= 2, "READY exceeded proposed 2 seconds")
            io_end = min(ready_at + .5, owner.case_end, state.expiry)
            owner.stop_end = min(ready_at + 1, owner.case_end, state.expiry)
            finish = message("FINISH", 1, index, nonce)
            owner.frames.append(finish)
            wire.send(finish, io_end)
            done = wire.receive(io_end)
            owner.frames.append(done)
            check_message(done, "DONE", 2, index, nonce)
            io_elapsed = time.monotonic() - ready_at
            need(io_elapsed <= .5 and reap(owner, owner.stop_end) == 0, "worker IO/exit")
            # Keep both parent socket objects until real zero reap. Closing the
            # extra child-end copy now permits an immediate, nonblocking EOF test.
            child_socket.close()
            need(parent_socket.recv(1) == b"", "trailing control bytes/no EOF")
            release_case(owner, state)
            need(not state.errors and owner.removed and owner.fd_released
                 and all(s.fileno() == -1 for s in owner.sockets)
                 and not outside.exists() and owner.forced == 0, "fixture cleanup")
            elapsed = time.monotonic() - start
            need(elapsed <= 2.5, "fixture including teardown exceeded 2.5 seconds")
            left(state.expiry)
            state.results.append({
                "case": index, "name": f"fresh_{index + 1}", "nonce": nonce,
                "sequences": [frame["seq"] for frame in owner.frames],
                "popen_identity": id(owner.process),
                "pid": owner.process.pid, "pgid": owner.pgid, "sid": owner.sid,
                "ready_seconds": ready_at - dispatch, "io_seconds": io_elapsed,
                "stop_reap_seconds": owner.reaped_at - ready_at,
                "fixture_seconds": elapsed, "wait_returncode": owner.process.returncode,
                "control_bytes": wire.moved, "facts": ready["facts"],
                "fds_closed": all(s.fileno() == -1 for s in owner.sockets) and owner.fd_released,
                "root_removed": owner.removed})
        release_base(state)
        retained = sum(
            (o.process is not None and o.process.returncode is None)
            or any(s.fileno() != -1 for s in o.sockets)
            or (o.root_fd is not None and not o.fd_released) or not o.removed
            for o in state.cases)
        reaps = sum(o.reaped for o in state.cases)
        forced = sum(o.forced for o in state.cases)
        leases = sum(o.process.returncode == 124 for o in state.cases)
        base_removed = not state.base.exists()
        need(len(state.results) == reaps == 3 and not state.errors and forced == leases == 0
             and retained == 0 and state.base_fd_released and base_removed,
             "total/base cleanup")
        total = time.monotonic() - HARNESS_START
        need(total < 8, "total including base removal exceeded 8 seconds")
        return {"status": "PASS", "scope": "fresh_local_SDK_constructor_READY_only",
                "cases": state.results, "total_seconds": total,
                "base_removed": base_removed, "base_fd_closed": state.base_fd_released,
                "actual_reaps": reaps,
                "cleanup_errors": len(state.errors),
                "forced_cleanup": forced, "lease_exits": leases,
                "retained_live_ownership": retained, "provider_operations": "not_performed",
                "qualification": False, "external_10_seconds": "parent_enforced_only"}
    except BaseException as primary:
        for owner in state.cases:
            record_error(state, owner, lambda o=owner: contain(o, state))
            record_error(state, owner, lambda o=owner: release_case(o, state))
            owner.cleanup_observed_at = time.monotonic()
        record_error(state, state, lambda: release_base(state))
        state.cleanup_observed_at = time.monotonic()
        raise Failure(state, primary) from primary


if __name__ == "__main__":
    if len(sys.argv) > 1:
        worker()
    else:
        try:
            receipt = run_spike()
        except Failure as error:
            RETAINED_FAILURE = error  # Embedding parent must retain this actual object.
            print(json.dumps({"status": "NONPASS", "primary": repr(error.primary),
                              "cleanup_errors": [repr(e) for _, e in error.cleanup_errors],
                              "total_seconds": error.owner.cleanup_observed_at - HARNESS_START,
                              "owned_pids": [o.process.pid for o in error.owner.cases
                                             if o.process is not None]}), flush=True)
            raise
        print(json.dumps(receipt, sort_keys=True, allow_nan=False), flush=True)
