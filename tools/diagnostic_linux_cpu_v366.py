"""One bounded source-pinned storage diagnostic, never a qualification."""
import time

BEGIN = time.monotonic_ns()
import signal

READY = False


def expired(_signum=None, _frame=None):
    if not READY:
        print('{"status":"NONPASS","cleanup":"UNKNOWN","error_type":"TimeoutError"}',
              flush=True)
        raise SystemExit(1)
    raise TimeoutError()


signal.signal(signal.SIGALRM, expired)
signal.setitimer(signal.ITIMER_REAL, max(0.000001, (BEGIN + 29_000_000_000
                                                - time.monotonic_ns()) / 1e9))
try:
    import hashlib
    import json
    import os
    import resource
    import ssl
    import stat
    import sys
    import tempfile
    import types
except SystemExit:
    raise
except BaseException:
    print('{"status":"NONPASS","cleanup":"UNKNOWN","error_type":"RuntimeError"}',
          flush=True)
    raise SystemExit(1) from None

VERSION = "v366-storage-diagnostic-1"
LIMITS = dict(max_bytes=67108864, per_file_bytes=33550336, guard_fixture_bytes=8192,
              chunk_bytes=8388608, deadline_ns=29000000000)
SOURCES = ("tools/diagnostic_linux_cpu_v366.py", "tools/report_linux_cpu_v366.py",
           "tools/setup_linux_cpu_v366.py",
           "train/_qualification_volume_preparer_fixture.py")
ROWS = []
SOURCE_IDENTITIES = {}
WRITTEN = 0
RESERVED = LIMITS["guard_fixture_bytes"]
PREP = None
ERRORS = {"ValueError", "RuntimeError", "OSError", "PermissionError",
          "FileNotFoundError", "TimeoutError", "MemoryError"}


def require(ok):
    if not ok:
        raise ValueError()


def deadline():
    if time.monotonic_ns() - BEGIN >= LIMITS["deadline_ns"]:
        raise TimeoutError()


def canonical(path):
    require(type(path) is str and path.startswith("/") and path != "/"
            and os.path.normpath(path) == path and "\\" not in path
            and "\0" not in path and os.path.realpath(path) == path)
    return path


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def read_source(path, cap):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and 0 <= before.st_size <= cap)
        parts, size = [], 0
        while True:
            part = os.read(fd, min(65536, cap + 1 - size))
            if not part:
                break
            parts.append(part)
            size += len(part)
            require(size <= cap)
        require(identity(before) == identity(os.fstat(fd))
                == identity(os.stat(path, follow_symlinks=False)))
        require(SOURCE_IDENTITIES.get(path, identity(before)) == identity(before))
        SOURCE_IDENTITIES[path] = identity(before)
        return b"".join(parts)
    finally:
        os.close(fd)


def closed_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def audit(event, args):
    if (event.startswith(("socket.", "subprocess.", "ctypes.", "os.exec",
                          "os.spawn", "os.posix_spawn", "os.fork"))
            or event in {"os.system", "os.kill", "os.killpg", "pty.spawn",
                         "_posixsubprocess.fork_exec"}):
        raise RuntimeError()


def progress(candidate, stage, event):
    row = dict(candidate=candidate, stage=stage, event=event,
               elapsed_ns=time.monotonic_ns() - BEGIN,
               cpu_ns=time.process_time_ns(), bytes=WRITTEN)
    raw = "DIAG_PHASE " + json.dumps(row, separators=(",", ":")) + "\n"
    require(len(raw) <= 512)
    sys.stderr.write(raw)
    sys.stderr.flush()


def measure(candidate, stage, call):
    deadline()
    require(len(ROWS) < 64)
    progress(candidate, stage, "start")
    wall, cpu = time.monotonic_ns(), time.process_time_ns()
    value = call()
    cpu, wall = time.process_time_ns() - cpu, time.monotonic_ns() - wall
    require(wall >= 0 and cpu >= 0)
    ROWS.append(dict(candidate=candidate, stage=stage, wall_ns=wall, cpu_ns=cpu))
    progress(candidate, stage, "end")
    deadline()
    return value


def permission(path):
    # Only explicit candidate ancestry; no enumeration or content reads.
    current = "/"
    for part in [""] + path.strip("/").split("/"):
        if part:
            current = os.path.join(current, part)
        s = os.stat(current, follow_symlinks=False)
        if (not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid())
                or (s.st_mode & 0o022 and not
                    (s.st_uid == 0 and s.st_mode & stat.S_ISVTX))):
            return False
    return (os.path.realpath(path) == path
            and os.access(path, os.W_OK | os.X_OK, effective_ids=True))


def mount_classes():
    fd = os.open("/proc/self/mountinfo", os.O_RDONLY | os.O_NOFOLLOW
                 | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, 1048577 - len(raw)))
            if not part:
                break
            raw.extend(part)
            require(len(raw) <= 1048576)
    finally:
        os.close(fd)
    mounts = []
    for line in raw.decode("utf-8", "strict").splitlines():
        left, right = line.split(" - ", 1)
        mount = left.split()[4]
        for escaped, value in (("\\040", " "), ("\\011", "\t"),
                               ("\\012", "\n"), ("\\134", "\\")):
            mount = mount.replace(escaped, value)
        kind = right.split()[0]
        mounts.append((mount, "TMPFS" if kind == "tmpfs" else
                       "RAMFS" if kind == "ramfs" else "REAL_STORAGE"))
    return mounts


def candidate(path, label, mounts):
    row = dict(candidate=label, result="NOT_MEASURED", free_bytes=0,
               fstype_class="UNKNOWN", permission=False)
    try:
        row["permission"] = permission(path)
        if not row["permission"]:
            return row
        matches = [(p, k) for p, k in mounts
                   if p == "/" or path == p or path.startswith(p.rstrip("/") + "/")]
        if matches:
            row["fstype_class"] = max(matches, key=lambda x: len(x[0]))[1]
        facts = os.statvfs(path)
        row["free_bytes"] = facts.f_bavail * facts.f_frsize
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return row
    if row["fstype_class"] != "REAL_STORAGE" or row["free_bytes"] < 14199074371:
        return row
    run_candidate(path, label)
    row["result"] = "COMPLETE"
    return row


def run_candidate(parent, label):
    global RESERVED, WRITTEN
    require(RESERVED + LIMITS["per_file_bytes"] <= LIMITS["max_bytes"])
    RESERVED += LIMITS["per_file_bytes"]  # Before any synthetic acquisition.
    anchors = PREP.Anchors()
    file_written = 0
    try:
        def setup_ancestry():
            root = tempfile.mkdtemp(prefix="v366-", dir=parent)
            rootfd = anchors.open(root)
            require(permission(parent))
            return rootfd, anchors.child(rootfd, "bulk-input")

        rootfd, bulk = measure(label, "ancestry_setup", setup_ancestry)

        def free_space():
            facts = os.fstatvfs(rootfd)
            return facts.f_bavail * facts.f_frsize

        def checkpoint():
            deadline()
            anchors.check()
            require(free_space() >= PREP.TOTAL_BYTES - file_written
                    + PREP.RESERVE + PREP.HEADROOM)
            deadline()

        measure(label, "anchors", anchors.check)
        require(measure(label, "free_space", free_space) >= 14199074371)
        fd = measure(label, "writer_open", lambda: PREP._OWNED.open(
                              "blob.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                              | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                              0o600, dir_fd=bulk))
        initial = os.fstat(fd)
        PREP.private_file(initial)
        require(initial.st_size == 0)
        digest = hashlib.sha256()
        seed = measure(label, "seed", lambda: os.urandom(8388600))

        def record_write(count):
            global WRITTEN
            nonlocal file_written
            WRITTEN += count
            file_written += count
            require(WRITTEN + LIMITS["guard_fixture_bytes"] <= RESERVED
                    <= LIMITS["max_bytes"])

        for number in range(4):
            measure(label, "checkpoint", checkpoint)
            size = min(LIMITS["chunk_bytes"], LIMITS["per_file_bytes"] - file_written)
            block = measure(label, "build", lambda: PREP._counter_block(seed, number)[:size])
            require(len(block) == size and size > 0)
            measure(label, "write", lambda: PREP.write_all(fd, block, record_write))
            measure(label, "hash", lambda: digest.update(block))
            del block
            measure(label, "checkpoint", checkpoint)
        del seed
        measure(label, "fsync", lambda: os.fsync(fd))
        final = os.fstat(fd)
        PREP.private_file(final)
        require((initial.st_dev, initial.st_ino) == (final.st_dev, final.st_ino)
                and final.st_size == LIMITS["per_file_bytes"]
                and final.st_blocks * 512 >= final.st_size)
        expected_identity = PREP.file_identity(final)

        def named():
            require(PREP.file_identity(os.stat("blob.bin", dir_fd=bulk,
                                               follow_symlinks=False))
                    == expected_identity)

        named()
        measure(label, "writer_close", lambda: PREP._OWNED.close(fd))
        named()
        reader = measure(label, "reader_open", lambda: PREP._OWNED.open(
            "blob.bin", os.O_RDONLY | os.O_NOFOLLOW
            | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=bulk))
        require(PREP.file_identity(os.fstat(reader)) == expected_identity)

        def readback():
            other, size = hashlib.sha256(), 0
            while True:
                deadline()
                part = os.read(reader, 65536)
                if not part:
                    break
                size += len(part)
                require(size <= LIMITS["per_file_bytes"])
                other.update(part)
            require(size == LIMITS["per_file_bytes"]
                    and other.digest() == digest.digest())
            require(PREP.file_identity(os.fstat(reader)) == expected_identity)
            named()

        measure(label, "readback", readback)
        measure(label, "reader_close", lambda: PREP._OWNED.close(reader))
        named()
        anchors.check()
    finally:
        # A failed close preserves UNKNOWN and its required ancestry, never retries.
        measure(label, "anchors_close", anchors.close)


def run():
    global PREP
    require(len(sys.argv) == 9 and sys.argv[1::2]
            == ["--workspace", "--root", "--spec", "--spec-sha256"])
    workspace, root, specpath = (canonical(sys.argv[n]) for n in (2, 4, 6))
    wanted = sys.argv[8]
    require(len(wanted) == 64 and all(c in "0123456789abcdef" for c in wanted))
    require(sys.platform == "linux" and sys.version_info[:3] == (3, 12, 13)
            and sys.flags.isolated and sys.flags.dont_write_bytecode
            and sys.flags.safe_path and sys.pycache_prefix == root + "/cache")
    require(dict(os.environ) == dict(HOME=root + "/home", TMPDIR=root + "/tmp",
                                    PATH="/usr/bin:/bin", LANG="C.UTF-8"))
    s = os.stat(root, follow_symlinks=False)
    require(stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o700
            and s.st_uid == os.getuid())
    os.chdir(root)
    sys.addaudithook(audit)
    raw = read_source(specpath, 32768)
    require(hashlib.sha256(raw).hexdigest() == wanted)
    spec = json.loads(raw, object_pairs_hook=closed_object)
    require(type(spec) is dict and set(spec) == {"version", "python_version",
                                                "pins", "limits"}
            and spec["version"] == VERSION and spec["python_version"] == "3.12.13"
            and type(spec["limits"]) is dict and spec["limits"] == LIMITS
            and all(type(n) is int for n in spec["limits"].values())
            and type(spec["pins"]) is dict
            and set(spec["pins"]) == set(SOURCES))
    buffers = {}
    for source in SOURCES:
        pin = spec["pins"][source]
        require(type(pin) is str and len(pin) == 64
                and all(c in "0123456789abcdef" for c in pin))
        path = canonical(workspace + "/" + source)
        buffers[source] = read_source(path, 2 * 1024**2)
        require(hashlib.sha256(buffers[source]).hexdigest() == pin)
    require(hashlib.sha256(b"abc").hexdigest()
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    PREP = types.ModuleType("_v366_private_preparer")
    sys.modules[PREP.__name__] = PREP
    exec(compile(buffers[SOURCES[-1]], "<pinned-preparer>", "exec"), PREP.__dict__)
    try:
        mounts = mount_classes()
        candidates = [candidate(path, label, mounts)
                      for path, label in (("/var/tmp", "VAR_TMP"), ("/mnt", "MNT"))]
        require(any(row["result"] == "COMPLETE" for row in candidates))
    finally:
        PREP._OWNED.close_all()
    require(all(row["state"] in ("CLOSED", "NO_FD")
                for row in PREP._OWNED.records))
    for source in SOURCES:
        require(read_source(workspace + "/" + source, 2 * 1024**2)
                == buffers[source])
    require(read_source(specpath, 32768) == raw)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    require(rss <= 256 * 1024**2 and WRITTEN + LIMITS["guard_fixture_bytes"] == RESERVED
            and 0 < WRITTEN <= LIMITS["max_bytes"])
    result = dict(status="DIAGNOSTIC_COMPLETE", version=VERSION,
                  total_written_bytes=WRITTEN, total_reserved_bytes=RESERVED,
                  guard_fixture_reserve_bytes=LIMITS["guard_fixture_bytes"],
                  rows=ROWS, candidates=candidates, source_pins_stable=True,
                  custody_closed=True, peak_rss_bytes=rss,
                  python_version="3.12.13", openssl_version=ssl.OPENSSL_VERSION,
                  hash_backend=hashlib.sha256.__module__,
                  monotonic_resolution_ns=time.get_clock_info("monotonic").resolution * 1e9,
                  cpu_resolution_ns=time.get_clock_info("process_time").resolution * 1e9,
                  full_volume_qualified=False, sdk_reaping_proven=False,
                  native_qualified=False, gpu_unlocked=False)
    deadline()
    result["elapsed_ns"] = time.monotonic_ns() - BEGIN
    output = json.dumps(result, separators=(",", ":"), allow_nan=False)
    require(len(output.encode("ascii")) <= 32768)
    deadline()
    print(output, flush=True)


if __name__ == "__main__":
    try:
        READY = True
        run()
    except BaseException as error:
        if PREP is not None:
            try:
                PREP._OWNED.close_all()
            except BaseException:
                pass
        kind = type(error).__name__
        print(json.dumps(dict(status="NONPASS", cleanup="UNKNOWN",
                              error_type=kind if kind in ERRORS else "RuntimeError"),
                         separators=(",", ":")), flush=True)
        sys.exit(1)
