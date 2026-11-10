"""V290 SOURCE ONLY, UNRUN. Separate parent-supervised preparation, not H191.

Closed CLI: APPROVED_RUNTIME THIS_SOURCE --root ABSOLUTE_FRESH_0700_ROOT.
Parent imposes external60s; cooperative internal50s includes generation/fsync.
No asset reads, processes, retries, cleanup, sparse files or second bulk copy.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time


FILE_BYTES = 2 * 1024**3
TOTAL_BYTES = 4 * FILE_BYTES
BUFFER_BYTES = 8 * 1024**2
HEADROOM = 1024**2
RESERVE = 5_608_091_203
MANIFEST_LIMIT = 65_536
KEYS = (
    "checkpoint-1/native-observation.json",
    "checkpoint-1/trainer_state.json",
    "checkpoint-2/native-observation.json",
    "checkpoint-2/trainer_state.json",
)


def require(ok, label):
    if not ok:
        raise ValueError(label)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def directory_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]


def file_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_blocks]


def private_directory(info):
    require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.getuid(), "owned0700 directory required")


def private_file(info):
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid() and info.st_nlink == 1,
            "owned0600 single-link regular file required")


class _OwnedCustody:
    """Retain every acquired generation and required unresolved ancestry."""

    def __init__(self):
        self.records = []

    def _record(self, fd):
        for row in reversed(self.records):
            if row["fd"] == fd and row["state"] == "OPEN":
                return row
        raise RuntimeError("owned open generation required")

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        if any(row["state"] in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")
               for row in self.records):
            raise RuntimeError("unresolved owned descriptor custody")
        parent = None if dir_fd is None else self._record(dir_fd)
        row = dict(fd=None, parent=parent, state="RESERVED", error=None)
        self.records.append(row)  # Reserve before acquisition.
        try:
            fd = os.open(path, flags, mode, dir_fd=dir_fd)
        except OSError as error:
            row["state"], row["error"] = "NO_FD", error
            raise
        except BaseException as error:
            row["state"], row["error"] = "UNKNOWN", error
            raise
        row["fd"] = fd  # Attach before validation, identity reads or exposure.
        row["state"] = "OPEN"
        return fd

    def close(self, fd):
        row = self._record(fd)
        try:
            row["state"] = "CLOSE_ATTEMPTED"
            os.close(fd)
        except BaseException as error:
            row["state"], row["error"] = "UNKNOWN", error
            raise
        row["state"] = "CLOSED"

    def _required(self, ancestor):
        for row in self.records:
            if row["state"] not in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN"):
                continue
            parent = row["parent"]
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent["parent"]
        return False

    def close_all(self):
        first = None
        for row in reversed(self.records):
            if row["state"] != "OPEN" or self._required(row):
                continue
            try:
                self.close(row["fd"])
            except BaseException as error:
                if first is None:
                    first = error
        unresolved = [row for row in self.records
                      if row["state"] in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")]
        if unresolved:
            # Preserve the original exception object, not only its text.
            error = next((row["error"] for row in unresolved
                          if row["error"] is not None), first)
            if error is not None:
                raise error
            raise RuntimeError("unresolved owned descriptor custody")
        if first is not None:
            raise first


_OWNED = _OwnedCustody()

def close_fd(fd):
    primary = sys.exception()
    try:
        _OWNED.close(fd)
    except BaseException as secondary:
        if primary is None:
            raise
        primary.add_note("owned descriptor close failed: " + type(secondary).__name__
                         + ": " + str(secondary)[:512])


class Anchors:
    """Pin only explicitly supplied ancestry, never enumerate other paths."""

    def __init__(self):
        self.entries = []

    def open(self, path):
        require(type(path) is str and path == str(Path(path))
                and Path(path).is_absolute() and ".." not in Path(path).parts
                and "\\" not in path and "\0" not in path and path != "/",
                "canonical absolute root required")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = _OWNED.open("/", flags)
        self.entries.append((fd, None, None, directory_identity(os.fstat(fd))))
        for name in Path(path).parts[1:]:
            parent = fd
            fd = _OWNED.open(name, flags, dir_fd=parent)
            self.entries.append((fd, parent, name, directory_identity(os.fstat(fd))))
        private_directory(os.fstat(fd))
        self.check()
        return fd

    def child(self, parent, name):
        os.mkdir(name, 0o700, dir_fd=parent)  # Exclusive, never exist_ok.
        fd = _OWNED.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                     | os.O_CLOEXEC, dir_fd=parent)
        self.entries.append((fd, parent, name, directory_identity(os.fstat(fd))))
        private_directory(os.fstat(fd))
        self.check()
        return fd

    def check(self):
        for fd, parent, name, expected in self.entries:
            require(directory_identity(os.fstat(fd)) == expected, "anchor changed")
            if parent is not None:
                require(directory_identity(os.stat(
                    name, dir_fd=parent, follow_symlinks=False)) == expected,
                    "named ancestry changed")

    def close(self):
        _OWNED.close_all()  # Retain UNKNOWN rows and their required ancestors.


def write_all(fd, raw, on_write=None):
    view = memoryview(raw)
    offset = 0
    while offset < len(view):
        count = os.write(fd, view[offset:])
        require(count > 0, "short write made no progress")
        offset += count
        if on_write is not None:
            on_write(count)


def exclusive_json(parent, name, value):
    raw = canonical(value)
    require(len(raw) <= MANIFEST_LIMIT, "bounded preparation metadata")
    fd = _OWNED.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | os.O_CLOEXEC, 0o600, dir_fd=parent)
    try:
        before = os.fstat(fd)
        private_file(before)
        write_all(fd, raw)
        os.fsync(fd)
        after = os.fstat(fd)
        private_file(after)
        require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                and after.st_size == len(raw), "metadata generation changed")
        require(file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                == file_identity(after), "named metadata changed")
    finally:
        close_fd(fd)
    os.fsync(parent)


def prepare(root, *, deadline_ns=None):
    start = time.monotonic_ns()
    if deadline_ns is not None:
        require(type(deadline_ns) is int and start < deadline_ns <= start + 29_000_000_000,
                "shared absolute internal29s deadline required")
    anchors = Anchors()
    bulk = None
    written = 0
    files = []
    active_file = None
    summary = None

    def record_write(count):
        nonlocal written
        written += count

    def deadline():
        if deadline_ns is None:
            require(time.monotonic_ns() - start < 50_000_000_000,
                    "preparation internal50s exceeded")
        else:
            require(time.monotonic_ns() < deadline_ns,
                    "shared internal29s deadline exceeded")

    def free_space(root_fd):
        facts = os.fstatvfs(root_fd)
        return facts.f_bavail * facts.f_frsize

    def checkpoint(root_fd):
        deadline()
        anchors.check()
        available = free_space(root_fd)
        require(available >= TOTAL_BYTES - written + RESERVE + HEADROOM,
                "insufficient available space for remaining bytes/reserve/headroom")
        return available

    try:
        root_fd = anchors.open(root)
        # Only this explicitly supplied fresh owned root, no broad search.
        with os.scandir(root_fd) as entries:
            require(next(entries, None) is None, "preparation root must be empty")
        initial_free = checkpoint(root_fd)
        bulk = anchors.child(root_fd, "bulk-input")
        for number, key in enumerate(KEYS, 1):
            name = f"blob-{number}.bin"
            active_file = name
            fd = _OWNED.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=bulk)
            try:
                initial = os.fstat(fd)
                private_file(initial)
                require(initial.st_size == 0, "only new empty generation")
                digest = hashlib.sha256()
                size = 0
                while size < FILE_BYTES:
                    checkpoint(root_fd)
                    block = os.urandom(min(BUFFER_BYTES, FILE_BYTES - size))
                    write_all(fd, block, record_write)
                    digest.update(block)
                    size += len(block)
                    del block  # Never retain previous buffer during next allocation.
                    checkpoint(root_fd)
                os.fsync(fd)
                checkpoint(root_fd)
                final = os.fstat(fd)
                private_file(final)
                require((initial.st_dev, initial.st_ino) == (final.st_dev, final.st_ino)
                        and final.st_size == FILE_BYTES
                        and final.st_blocks * 512 >= final.st_size,
                        "dense complete stable2GiB generation required")
                identity = file_identity(final)
                require(file_identity(os.stat(name, dir_fd=bulk, follow_symlinks=False))
                        == identity, "named generated blob changed")
                files.append(dict(name=name, key=key, size=size,
                                  sha256=digest.hexdigest(), identity=identity))
            finally:
                close_fd(fd)
            require(file_identity(os.stat(name, dir_fd=bulk, follow_symlinks=False))
                    == identity, "closed blob identity changed")
            active_file = None
        os.fsync(bulk)
        require(written == TOTAL_BYTES, "exact8GiB preparation required")
        final_free = checkpoint(root_fd)
        manifest = dict(
            v=1, op="v290-owned-volume",
            root_identity=directory_identity(os.fstat(root_fd)),
            bulk_identity=directory_identity(os.fstat(bulk)), files=files,
            preparation=dict(
                elapsed_ns=time.monotonic_ns() - start, written_bytes=written,
                initial_free_bytes=initial_free, final_free_bytes=final_free,
                buffer_bytes=BUFFER_BYTES, cache="fresh-generated-not-evicted"))
        exclusive_json(bulk, "manifest.json", manifest)
        checkpoint(root_fd)
        os.fsync(root_fd)
        deadline()
        summary = dict(v=1, status="COMPLETE", written_bytes=written,
                       initial_free_bytes=initial_free, final_free_bytes=free_space(root_fd),
                       cache="fresh-generated-not-evicted")
    except BaseException as primary:
        if bulk is not None:
            try:
                anchors.check()
                exclusive_json(bulk, "preparation-failure.json", dict(
                    v=1, status="FAIL", error_type=type(primary).__name__,
                    error=str(primary)[:1024], written_bytes=written,
                    elapsed_ns=time.monotonic_ns() - start, active_file=active_file,
                    completed_files=files))
            except BaseException as secondary:
                primary.add_note("failure provenance write failed: "
                                 + type(secondary).__name__ + ": " + str(secondary)[:512])
        raise
    finally:
        primary = sys.exception()
        try:
            anchors.close()
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note("anchor close failed: " + type(secondary).__name__)
    deadline()  # Also include actual ancestry close time in internal50.
    summary["elapsed_ns"] = time.monotonic_ns() - start
    return summary


def main():
    require(len(sys.argv) == 3 and sys.argv[1] == "--root",
            "expected exactly --root ABSOLUTE_FRESH_0700_ROOT")
    summary = prepare(sys.argv[2])
    print(canonical(summary).decode("ascii"), flush=True)


if __name__ == "__main__":
    main()
