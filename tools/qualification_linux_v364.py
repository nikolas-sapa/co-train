"""Source-only Linux CPU driver. One process, fresh generation, one exact case.

Run under an independently enforced GNU timeout --signal=KILL 30s. No retry.
The 29-second absolute deadline starts before admission/imports/generation and
ends after pytest teardown, custody checks and durable diagnostic close.
This qualifies original Python readers, NOT native science or SDK child reaps.
"""
import time

_NOW_NS = time.monotonic_ns
BEGIN_NS = _NOW_NS()
DEADLINE_NS = BEGIN_NS + 29_000_000_000

import argparse
import contextlib
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import sys
import threading
import xml.etree.ElementTree as ET


VERSION = "v364-linux-cpu-1"
MODE = "fresh-generated-not-evicted"
NODEID = ("train/test_qualification_ac_volume.py::"
          "test_actual_ac_four_two_gib_files_full_validation")
PREPARER = "train._qualification_volume_preparer_fixture"
TEST_MODULE = "train.test_qualification_ac_volume"
REQUIRED_ORIGINS = (
    "train", "train.native_qualification", "train.engineering_budget",
    "train.qualification_engineering_host", "train.qualification_owned_stop",
    "train.qualification_modal_host", "train.qualification_isolated_contract",
    "train.qualification_isolated_validation", "train.qualification_isolated_owner",
    "train.qualification_isolated_worker", "train.qualification_isolated_deadline",
    "train.qualification_isolated_run", "train.qualification_isolated_program",
    "train.qualification_engineering_run", "train.qualification_modal_transport",
    "train.test_qualification_isolated_owner", TEST_MODULE, PREPARER,
)


def require(value, label="Linux source admission refused"):
    if not value:
        raise RuntimeError(label)


def deadline():
    require(_NOW_NS() < DEADLINE_NS, "shared internal29s deadline exceeded")


def read(path, limit=2_097_152):
    require(path.is_absolute() and path == path.resolve() and not path.is_symlink())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and 0 <= before.st_size <= limit)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        identity = lambda info: (
            info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(len(raw) == before.st_size
                and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()))
        return raw
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def private_directory(path):
    require(path.is_absolute() and path == path.resolve() and not path.is_symlink())
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def real_filesystem(root):
    # Linux mount metadata only, never payload/assets/interpreter contents.
    with open("/proc/self/mountinfo", "rb") as stream:
        raw = stream.read(1_048_577)
    require(0 < len(raw) <= 1_048_576, "bounded Linux mount metadata required")
    mounts = []
    for line in raw.decode("utf-8", "strict").splitlines():
        left, right = line.split(" - ", 1)
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)),
                       left.split()[4])
        mount = Path(point)
        if root.is_relative_to(mount):
            mounts.append((len(mount.parts), right.split()[0]))
    require(mounts and max(mounts)[1] not in ("tmpfs", "ramfs"),
            "qualification root must be on a real filesystem")


class PinnedLoader(importlib.abc.Loader):
    def __init__(self, path, raw, loaded, name):
        self.path, self.raw, self.loaded, self.name = path, raw, loaded, name

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        require(self.name not in self.loaded, "source module executed twice")
        require(Path(module.__file__) == self.path)
        # Compile the EXACT buffer whose digest was checked before payload.
        exec(compile(self.raw, str(self.path), "exec", dont_inherit=True), module.__dict__)
        self.loaded[self.name] = self.path


class PinnedFinder(importlib.abc.MetaPathFinder):
    def __init__(self, workspace, sources):
        self.workspace, self.sources, self.loaded = workspace, sources, {}
        self.modules = {}
        for relative in sources:
            parts = Path(relative).parts
            if relative.endswith(".py") and parts[0] in ("train", "bench", "ptc"):
                name = ".".join(parts)[:-3]
                package = name.endswith(".__init__")
                if package:
                    name = name[:-9]
                require(name not in self.modules)
                self.modules[name] = (relative, package)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] not in ("train", "bench", "ptc"):
            return None
        require(fullname in self.modules, "unpinned project import refused")
        relative, package = self.modules[fullname]
        source_path = self.workspace / relative
        return importlib.util.spec_from_file_location(
            fullname, source_path,
            loader=PinnedLoader(source_path, self.sources[relative], self.loaded, fullname),
            submodule_search_locations=[str(source_path.parent)] if package else None)


def install_audit(root, pins):
    """H191 private-Unix/process denial, plus owned-root file-write confinement."""
    bound, sockets, forbidden = set(), [], []
    pending = threading.local()
    base_open = os.open
    base_bind = socket.socket.bind
    base_fileno = socket.socket.fileno
    fd_paths = {}
    trusted = tuple({Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()})

    def path_for(value, dir_fd=None):
        if isinstance(value, int):
            require(value in fd_paths, "unowned descriptor path refused")
            return fd_paths[value]
        path = Path(os.fsdecode(value))
        require("\0" not in str(path) and ".." not in path.parts)
        if not path.is_absolute():
            parent = Path.cwd() if dir_fd in (None, -1) else path_for(dir_fd)
            path = parent / path
        return path.resolve()

    def owned(path):
        require(path.is_relative_to(root), "filesystem side effect outside owned root")

    def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
        absolute = path_for(path, dir_fd)
        previous = getattr(pending, "open_path", None)
        pending.open_path = absolute
        try:
            fd = base_open(path, flags, mode, dir_fd=dir_fd)
        finally:
            pending.open_path = previous
        # No identity read/validation between acquisition and the original
        # caller's custody attachment. Those checks remain the caller's job.
        fd_paths[fd] = absolute
        return fd

    def tracked_bind(sock, address):
        previous = getattr(pending, "bind", None)
        pending.bind = (sock, address)
        try:
            value = base_bind(sock, address)
            sockets.append(sock)
            return value
        finally:
            pending.bind = previous

    def private_address(value):
        require(isinstance(value, str) and "\0" not in value)
        path = Path(value)
        require(path.is_absolute() and path.parent == path.parent.resolve()
                and path.parent.is_relative_to(root) and path.parent.is_dir())
        ancestor = path.parent
        while True:
            info = ancestor.stat()
            require(info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o022)
            if ancestor == root:
                require(stat.S_IMODE(info.st_mode) == 0o700)
                break
            ancestor = ancestor.parent
        return str(path)

    def audit(event, args):
        if event == "open":
            value, _, flags = args
            absolute = getattr(pending, "open_path", None)
            if absolute is None:
                absolute = path_for(value)
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                owned(absolute)
            else:
                require(absolute.is_relative_to(root) or absolute in pins
                        or any(absolute.is_relative_to(p) for p in trusted)
                        or (flags & os.O_DIRECTORY and absolute in root.parents),
                        "unapproved file read refused")
        elif event in ("os.mkdir", "os.remove", "os.rmdir"):
            dir_fd = args[2] if event == "os.mkdir" else args[1]
            owned(path_for(args[0], dir_fd))
        elif event in ("os.chmod", "os.chown", "os.utime"):
            owned(path_for(args[0], args[-1]))
        elif event == "os.rename":
            owned(path_for(args[0], args[2]))
            owned(path_for(args[1], args[3]))
        elif event == "os.truncate":
            owned(path_for(args[0]))
        elif event in ("os.link", "os.symlink"):
            raise RuntimeError("links refused")
        elif event == "os.chdir":
            owned(path_for(args[0]))
        elif event == "socket.__new__":
            require(args[1] == socket.AF_UNIX and int(args[2]) & 15 == socket.SOCK_STREAM)
        elif event == "socket.bind":
            require(getattr(pending, "bind", None) == (args[0], args[1]))
            address = private_address(args[1])
            require(not Path(address).exists() and not Path(address).is_symlink())
            bound.add(address)
        elif event == "socket.connect":
            address = private_address(args[1])
            info = Path(address).lstat()
            require(address in bound and stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid())
        elif event.startswith("socket.") and event != "socket.gethostname":
            raise RuntimeError("network route refused")
        elif (event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.fork",
                        "os.forkpty", "os.exec", "os.spawn", "os.kill", "os.killpg",
                        "signal.pthread_kill", "pty.spawn")
              or event.startswith("ctypes.")):
            if len(forbidden) < 16:
                forbidden.append(event)
            raise RuntimeError("processes, signals and foreign-function routes refused")

    sys.addaudithook(audit)
    os.open = tracked_open
    socket.socket.bind = tracked_bind
    return sockets, forbidden, base_fileno


def write_report(root, payload):
    fd = os.open(root / "execution.json",
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(payload, output, sort_keys=True, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--spec-sha256", required=True)
    options = parser.parse_args()
    require(sys.platform == "linux" and sys.version_info[:3] == (3, 12, 13))
    require(sys.flags.isolated and sys.flags.safe_path and sys.dont_write_bytecode)
    workspace, root, spec_path = map(Path, (options.workspace, options.root, options.spec))
    require(workspace.is_absolute() and workspace == workspace.resolve()
            and workspace.is_dir() and not workspace.is_symlink())
    private_directory(root)
    require(not root.is_relative_to(workspace) and not workspace.is_relative_to(root)
            and not any(root.is_relative_to(Path(p).resolve())
                        for p in (sys.prefix, sys.base_prefix)))
    require(re.fullmatch("[0-9a-f]{64}", options.spec_sha256))
    raw = read(spec_path, 65_536)
    require(sha(raw) == options.spec_sha256, "spec digest mismatch")
    spec = json.loads(raw, object_pairs_hook=no_duplicates)
    require(type(spec) is dict and set(spec) == {
        "version", "mode", "python_version", "pytest_version", "pins", "origins", "nodeid"})
    require(spec["version"] == VERSION and spec["mode"] == MODE
            and spec["python_version"] == "3.12.13" and spec["nodeid"] == NODEID)
    require(type(spec["pytest_version"]) is str
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", spec["pytest_version"]))
    require(type(spec["pins"]) is dict and 40 <= len(spec["pins"]) <= 80)
    sources = {}
    for relative, digest in spec["pins"].items():
        require(type(relative) is str and relative == str(Path(relative))
                and not Path(relative).is_absolute() and ".." not in Path(relative).parts
                and "\\" not in relative and "\0" not in relative
                and (relative.endswith(".py") or relative == "train/native_model_inventory.json")
                and type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest))
        source = read(workspace / relative)
        require(sha(source) == digest, "source pin mismatch: " + relative)
        sources[relative] = source
    require("tools/qualification_linux_v364.py" in sources
            and Path(__file__).resolve() == workspace / "tools/qualification_linux_v364.py")
    require(type(spec["origins"]) is dict
            and set(REQUIRED_ORIGINS).issubset(spec["origins"]))
    finder = PinnedFinder(workspace, sources)
    for name, relative in spec["origins"].items():
        require(type(name) is str and name in finder.modules
                and finder.modules[name][0] == relative)
    require(not any(name.split(".", 1)[0] in ("train", "bench", "ptc") for name in sys.modules))
    require(set(os.environ) == {
        "HOME", "TMPDIR", "PATH", "LANG", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"},
        "payload environment must contain only five approved keys")
    require(os.environ["HOME"] == str(root / "home")
            and os.environ["TMPDIR"] == str(root / "tmp")
            and os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
            and sys.pycache_prefix == str(root / "cache"))
    require(not any(root.iterdir()), "fresh qualification root must be empty")
    real_filesystem(root)
    os.chdir(root)
    # Installed, workflow-pinned pytest is trusted startup, not project payload.
    import pytest
    require(pytest.__version__ == spec["pytest_version"])
    trusted_pytest = Path(sys.prefix) / "lib/python3.12/site-packages/pytest/__init__.py"
    require(Path(pytest.__file__).resolve() == trusted_pytest)
    sockets, forbidden, fileno = install_audit(root, {workspace / p for p in sources})
    sys.meta_path.insert(0, finder)
    deadline()
    preparer = importlib.import_module(PREPARER)
    preparation = preparer.prepare(str(root), deadline_ns=DEADLINE_NS)
    require(preparation["status"] == "COMPLETE"
            and preparation["written_bytes"] == 8_589_934_592
            and preparation["initial_free_bytes"] >= 14_199_074_371
            and preparation["final_free_bytes"] >= 5_609_139_779
            and preparation["cache"] == MODE)
    require(all(row["state"] in ("CLOSED", "NO_FD") for row in preparer._OWNED.records),
            "preparation descriptor custody unresolved")
    for name in ("home", "tmp", "cases", "cache"):
        (root / name).mkdir(mode=0o700)
    config = root / "pytest.ini"
    with config.open("x") as output:
        output.write("[pytest]\n")
    config.chmod(0o600)
    test = importlib.import_module(TEST_MODULE)
    context = dict(version=VERSION, mode=MODE, root=str(root), start_ns=BEGIN_NS,
                   deadline_ns=DEADLINE_NS, completed=False)
    require(test._LINUX_V364_CONTEXT is None)
    test._LINUX_V364_CONTEXT = context
    collected, reports = [], []

    class Observer:
        def pytest_collection_finish(self, session):
            collected.extend(item.nodeid for item in session.items)
            require(collected == [NODEID], "exact one-case collection required")

        def pytest_runtest_logreport(self, report):
            reports.append((report.nodeid, report.when, report.outcome))

    junit, log = root / "junit.xml", root / "pytest.log"
    args = [
        str(workspace / NODEID.split("::")[0]) + "::" + NODEID.split("::")[1],
        "-q", "-s", "--tb=short", "--assert=plain", "-p", "no:cacheprovider",
        "--noconftest", "-c", str(config), "--rootdir", str(workspace),
        "-o", "addopts=", "-o", "log_file=" + str(root / "pytest-library.log"),
        "--basetemp", str(root / "cases"), "--junitxml", str(junit),
    ]
    deadline()
    with log.open("x") as output, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        code = int(pytest.main(args, plugins=[Observer()]))
    # pytest.main returning includes all fixture/session teardown and JUnit close.
    deadline()
    cases = ET.fromstring(read(junit)).findall(".//testcase")
    failures = sum(len(case.findall("failure")) for case in cases)
    errors = sum(len(case.findall("error")) for case in cases)
    skips = sum(len(case.findall("skipped")) for case in cases)
    require(code == 0 and collected == [NODEID]
            and reports == [(NODEID, phase, "passed") for phase in ("setup", "call", "teardown")]
            and len(cases) == 1 and failures == errors == skips == 0
            and cases[0].get("name") == NODEID.split("::")[1],
            "one exact case with zero skips/errors/failures required")
    require(context["completed"] is True, "diagnostic/ancestry close did not complete")
    require(all(row["state"] in ("CLOSED", "NO_FD") for row in test._OWNED.records),
            "test descriptor custody unresolved")
    metrics = json.loads(read(root / "diagnostics/v290-volume.json"))
    require(metrics["status"] == "BODY_COMPLETED" and metrics["release_completed"] is True
            and metrics["registry_live_after_release"] == 0
            and metrics["cache"] == MODE + "-no-cold-cache-claim"
            and metrics["lifecycle"] == "synthetic observations")
    origins_ok = all(name in finder.loaded and name in sys.modules
                     and Path(sys.modules[name].__file__).resolve() == workspace / relative
                     for name, relative in spec["origins"].items())
    require(origins_ok, "required pinned origins not executed")
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename is not None and Path(filename).is_absolute():
            path = Path(filename).resolve()
            if path.is_relative_to(workspace):
                require((name == "__main__"
                         and path == workspace / "tools/qualification_linux_v364.py")
                        or (name in finder.loaded and finder.loaded[name] == path),
                        "project source bypassed pinned same-buffer loader")
    stable = all(sha(read(workspace / p)) == digest for p, digest in spec["pins"].items())
    unclosed = sum(fileno(sock) >= 0 for sock in sockets)
    require(stable and not forbidden and unclosed == 0,
            "source drift, forbidden operation or unclosed socket")
    payload = dict(
        version=VERSION, status="PASS", nodeid=NODEID, cases=1, failures=failures,
        errors=errors, skips=skips, pytest_exit=code, source_pins_stable=stable,
        origins_verified=origins_ok, preparation=preparation, volume_metrics=metrics,
        cache=MODE + "-no-cold-cache-claim", full_process_deadline_ns=29_000_000_000,
        timing_scope="admission, fresh generation, exact pytest, all teardown and diagnostic close",
        external_kill30_and_terminal_exit_zero_required=True,
        child_processes_allowed=False, lifecycle="synthetic observations",
        sdk_owned_child_reaps_proven=False, native_qualification=False,
        unclosed_bound_sockets=unclosed, forbidden_operations=forbidden)
    deadline()
    write_report(root, dict(
        payload, status="AWAITING_TERMINAL_CLOSE",
        elapsed_ns_before_diagnostic_write=_NOW_NS() - BEGIN_NS))
    deadline()  # Includes durable diagnostic descriptor close.
    payload["elapsed_ns"] = _NOW_NS() - BEGIN_NS
    print(json.dumps(payload, sort_keys=True), flush=True)
    deadline()


def internal_timeout(signum, frame):
    raise TimeoutError("shared internal29s deadline exceeded")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, internal_timeout)
    remaining = (DEADLINE_NS - _NOW_NS()) / 1_000_000_000
    require(remaining > 0, "startup exceeded shared deadline")
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        main()
    except BaseException as error:
        print(json.dumps(dict(version=VERSION, status="NONPASS",
                              error_type=type(error).__name__, cleanup="unproven",
                              elapsed_ns=_NOW_NS() - BEGIN_NS)), flush=True)
        raise
