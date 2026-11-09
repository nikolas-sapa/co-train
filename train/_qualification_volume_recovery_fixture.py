# Sanitized public reference, UNRUN derivative. No execution authority.
"""SOURCEONLY RED HELPERS, UNRUN, NOT APPROVED TO RECOVER.

One separately reviewed recovery, never a reset/retry of consumed V305.
Parent must demonstrate RED, correct the two predicates, obtain GREEN/security
clearance and freeze/review before its ONE externally supervised10s recovery.
Internal5s includes cleanup. No bulk reads, copies, allocation or deletion.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

WORKSPACE = Path("/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06")
SOURCE = Path("/qualification-reference/scratch/pc297-4yntz90o")
PARTIAL = Path("/qualification-reference/scratch/pc305-nklrdyr7")
PARTIAL_IDENTITY = [101, 1007, 16832, 503, 20]
CACHE = "reused-generated-after-previous-full-read-not-evicted"
RESERVE = 5_609_139_779
FILE_BYTES = 2147483648
TOTAL_BYTES = 8589934592
PINS = (
    ("execution.json", 497, "0000000000000000000000000000000000000000000000000000000000000006"),
    ("diagnostics/v290-volume.json", 3788, "0000000000000000000000000000000000000000000000000000000000000007"),
    ("bulk-input/manifest.json", 1393, "0000000000000000000000000000000000000000000000000000000000000008"),
)
FAILURE_PIN = (
    "bulk-input/staging-failure.json", 633,
    "0000000000000000000000000000000000000000000000000000000000000005",
)
HASHES = (
    "0000000000000000000000000000000000000000000000000000000000000001",
    "0000000000000000000000000000000000000000000000000000000000000002",
    "0000000000000000000000000000000000000000000000000000000000000003",
    "0000000000000000000000000000000000000000000000000000000000000004",
)
_LOADER = []


def _same_file_generation(expected, actual):
    return (len(expected) == len(actual) == 10
            and expected[:9] == actual[:9]
            and expected[9] * 512 >= expected[6]
            and actual[9] * 512 >= actual[6])


def _same_rename_generation(before, after):
    return (len(before) == len(after) == 10
            and before[:8] == after[:8]
            and before[9] * 512 >= before[6]
            and after[9] * 512 >= after[6])


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _snapshot(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_blocks]


def load_helper():
    # Same-buffer reviewed-source load only. Never call prepare/main.
    path = WORKSPACE / "parent-v296-volume-preparer-frozen.py"
    require(path.resolve(strict=True) == path, "canonical reviewed helper")
    row = dict(fd=None, state="RESERVED", error=None)
    _LOADER.append(row)
    try:
        row["fd"] = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                            | os.O_CLOEXEC)
        row["state"] = "OPEN"
        before = os.fstat(row["fd"])
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and not before.st_mode & 0o022
                and before.st_size == 13185, "owned reviewed helper source")
        raw = os.read(row["fd"], 13186)
        require(_same_file_generation(_snapshot(before), _snapshot(os.fstat(row["fd"])))
                and _same_file_generation(_snapshot(before), _snapshot(path.lstat()))
                and len(raw) == 13185 and hashlib.sha256(raw).hexdigest()
                == "000000000000000000000000000000000000000000000000000000000000000f",
                "same reviewed helper bytes")
    except BaseException as error:
        row["primary"] = error
        if row["fd"] is None:
            row["state"], row["error"] = "UNKNOWN", error
        raise
    finally:
        if row["fd"] is not None:
            primary = sys.exception()
            row["state"] = "CLOSE_ATTEMPTED"
            try:
                os.close(row["fd"])
            except BaseException as error:
                row["state"], row["error"] = "UNKNOWN", error
                if primary is not None:
                    primary.add_note("helper source close failed: " + type(error).__name__)
                    raise primary from error
                raise
            row["state"] = "CLOSED"
    namespace = dict(__name__="owned_volume_reference", __file__=str(path))
    exec(compile(raw, str(path), "exec"), namespace)
    return namespace


def relocate(root_text):
    start = time.monotonic_ns()
    helper = load_helper()
    anchors = helper["Anchors"]()
    owned = helper["_OWNED"]
    directory_identity = helper["directory_identity"]
    private_file, close_fd = helper["private_file"], helper["close_fd"]
    bulk = None
    moved, preflight, files = [], [], []
    metadata_bytes = 0

    def checkpoint(root_fd=None):
        require(time.monotonic_ns() - start < 5_000_000_000,
                "recovery internal5s exceeded")
        anchors.check()
        if root_fd is not None:
            facts = os.fstatvfs(root_fd)
            require(facts.f_bavail * facts.f_frsize >= RESERVE,
                    "retained free-space floor")

    def metadata(base, relative, size, sha):
        nonlocal metadata_bytes
        path = base / relative
        parent = anchors.open(str(path.parent))
        fd = owned.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                        | os.O_CLOEXEC, dir_fd=parent)
        try:
            before = os.fstat(fd)
            private_file(before)
            require(before.st_size == size and size <= 65536, "bounded pinned metadata")
            parts, count = [], 0
            while count <= size:
                block = os.read(fd, min(65536, size - count + 1))
                metadata_bytes += len(block)
                require(metadata_bytes <= 1024**2, "metadata read budget")
                if not block:
                    break
                parts.append(block)
                count += len(block)
            raw = b"".join(parts)
            require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha,
                    "pinned historical evidence")
            require(_same_file_generation(_snapshot(before), _snapshot(os.fstat(fd)))
                    and _same_file_generation(_snapshot(before), _snapshot(os.stat(
                        path.name, dir_fd=parent, follow_symlinks=False))),
                    "stable pinned metadata")
        finally:
            close_fd(fd)
        checkpoint()
        return json.loads(raw)

    def exclusive_json(parent, name, value):
        nonlocal metadata_bytes
        raw = helper["canonical"](value)
        require(len(raw) <= 65536, "bounded recovery metadata")
        metadata_bytes += len(raw)
        require(metadata_bytes <= 1024**2, "metadata total budget")
        fd = owned.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        try:
            before = os.fstat(fd)
            private_file(before)
            helper["write_all"](fd, raw)
            os.fsync(fd)
            after = os.fstat(fd)
            private_file(after)
            # Writing metadata legitimately changes size/times; compare its
            # actual post-write generation to its actual directory entry.
            require(before.st_dev == after.st_dev and before.st_ino == after.st_ino
                    and after.st_size == len(raw), "metadata generation changed")
            identity = _snapshot(after)
            require(_same_file_generation(identity, _snapshot(os.stat(
                name, dir_fd=parent, follow_symlinks=False))), "named metadata changed")
        finally:
            close_fd(fd)
        require(_same_file_generation(identity, _snapshot(os.stat(
            name, dir_fd=parent, follow_symlinks=False))), "closed metadata changed")
        os.fsync(parent)

    def absent(parent, name):
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ValueError("unexpected duplicate prior source name: " + name)

    def current(fd):
        info = os.fstat(fd)
        private_file(info)
        require(info.st_size == FILE_BYTES and info.st_blocks * 512 >= info.st_size,
                "current dense complete owned2GiB file")
        return _snapshot(info)

    def named(parent, name):
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        private_file(info)
        require(info.st_size == FILE_BYTES and info.st_blocks * 512 >= info.st_size,
                "named dense complete owned2GiB file")
        return _snapshot(info)

    try:
        source_root = anchors.open(str(SOURCE))
        partial_root = anchors.open(str(PARTIAL))
        execution, diagnostics, original = (metadata(SOURCE, *pin) for pin in PINS)
        failure = metadata(PARTIAL, *FAILURE_PIN)
        require(execution["status"] == "PASS" and execution["cases"] == 1
                and execution["pytest_exit"] == 0
                and execution["failures"] == execution["errors"] == execution["skips"] == 0
                and execution["source_pins_stable"] is True
                and execution["origins_verified"] is True,
                "actual prior one-case PASS required")
        require(diagnostics["status"] == "BODY_COMPLETED"
                and diagnostics["release_completed"] is True
                and diagnostics["registry_live_after_release"] == 0
                and diagnostics["bulk_expected_bytes"] == TOTAL_BYTES,
                "actual prior completed release/live0 required")
        require(original["root_identity"] == directory_identity(os.fstat(source_root))
                and PARTIAL_IDENTITY == directory_identity(os.fstat(partial_root)),
                "exact two owned historical roots")
        require(set(original) == {"v", "op", "root_identity", "bulk_identity",
                                  "files", "preparation"}
                and original["v"] == 1 and original["op"] == "v290-owned-volume",
                "closed v290 manifest shape")
        require(set(original["preparation"]) == {
            "buffer_bytes", "cache", "elapsed_ns", "final_free_bytes",
            "initial_free_bytes", "written_bytes"}
                and original["preparation"] == diagnostics["preparation"]
                and original["preparation"]["written_bytes"] == TOTAL_BYTES,
                "unchanged historical preparation")
        keys = helper["KEYS"]
        require(len(original["files"]) == len(diagnostics["moved"]) == 4
                and tuple(e["key"] for e in original["files"]) == keys
                and tuple(e["key"] for e in diagnostics["moved"]) == keys,
                "exact ordered original four files")
        require(set(failure) == {"v", "status", "error_type", "error", "moved", "elapsed_ns"}
                and failure["v"] == 1 and failure["status"] == "FAIL"
                and failure["error_type"] == "ValueError"
                and failure["error"] == "exact prior validated source generation"
                and len(failure["moved"]) == 2
                and tuple(e["key"] for e in failure["moved"]) == keys[:2],
                "exact consumed V305 failure/two ordered completed moves")
        for index, move in enumerate(failure["moved"]):
            require(set(move) == {"key", "before", "after"}
                    and _same_file_generation(diagnostics["moved"][index]["export_identity"],
                                              move["before"])
                    and _same_rename_generation(move["before"], move["after"]),
                    "pinned failure ordered move provenance")

        root_fd = anchors.open(root_text)
        destination = Path(root_text)
        require(not any(destination == prior or destination in prior.parents
                        or prior in destination.parents for prior in (SOURCE, PARTIAL)),
                "fresh root disjoint from both prior roots")
        roots = [directory_identity(os.fstat(fd)) for fd in
                 (source_root, partial_root, root_fd)]
        require(len({tuple(row[:2]) for row in roots}) == 3
                and len({row[0] for row in roots}) == 1, "distinct same-device roots")
        scan = dict(fd=None, parent=owned._record(root_fd), state="RESERVED",
                    error=None, handle=None)
        owned.records.append(scan)
        try:
            scan["handle"] = os.scandir(root_fd)
            scan["state"] = "OPEN"
            require(next(scan["handle"], None) is None, "fresh empty0700 root required")
        except BaseException as error:
            if scan["handle"] is None:
                scan["state"], scan["error"] = "UNKNOWN", error
            raise
        finally:
            if scan["handle"] is not None:
                primary = sys.exception()
                scan["state"] = "CLOSE_ATTEMPTED"
                try:
                    scan["handle"].close()
                except BaseException as error:
                    scan["state"], scan["error"] = "UNKNOWN", error
                    if primary is not None:
                        primary.add_note("root iterator close failed: " + type(error).__name__)
                        raise primary from error
                    raise
                scan["state"] = "CLOSED"
        checkpoint(root_fd)
        old_bulk = anchors.open(str(SOURCE / "bulk-input"))
        partial_bulk = anchors.open(str(PARTIAL / "bulk-input"))
        require(directory_identity(os.fstat(old_bulk)) == original["bulk_identity"],
                "exact original bulk directory")
        source_dirs = {name: anchors.open(str(SOURCE / "volume-case/export/run" / name))
                       for name in ("checkpoint-1", "checkpoint-2")}
        seen = set()
        # ALL FOUR actual opened generations remain in custody before ANY
        # destination directory/placeholder creation or move.
        for index, entry in enumerate(original["files"]):
            checkpoint(root_fd)
            require(set(entry) == {"identity", "key", "name", "sha256", "size"}
                    and entry["name"] == f"blob-{index + 1}.bin"
                    and entry["size"] == FILE_BYTES and entry["sha256"] == HASHES[index],
                    "fixed descriptor/hash expectations, not current-byte proof")
            directory, leaf = entry["key"].split("/")
            export_fd = source_dirs[directory]
            absent(old_bulk, entry["name"])
            if index < 2:
                absent(export_fd, leaf)
                parent, name = partial_bulk, entry["name"]
                expected = failure["moved"][index]["after"]
            else:
                absent(partial_bulk, entry["name"])
                parent, name = export_fd, leaf
                expected = diagnostics["moved"][index]["export_identity"]
            fd = owned.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                            | os.O_CLOEXEC, dir_fd=parent)
            actual = current(fd)
            require(len(expected) == 10 and _same_file_generation(expected, actual)
                    and _same_file_generation(actual, named(parent, name)),
                    "all-source preflight logical generation and density")
            require(actual[0] == roots[2][0] and tuple(actual[:2]) not in seen,
                    "same-device distinct nonaliased source inodes")
            seen.add(tuple(actual[:2]))
            preflight.append(dict(fd=fd, parent=parent, name=name, entry=entry,
                                  expected=expected, actual=actual))
        require(len(preflight) == 4, "complete all-four opened preflight")
        checkpoint(root_fd)
        bulk = anchors.child(root_fd, "bulk-input")
        for row in preflight:
            checkpoint(root_fd)
            fd, parent, name, entry = (row[k] for k in ("fd", "parent", "name", "entry"))
            before = current(fd)
            require(_same_file_generation(row["actual"], before)
                    and _same_file_generation(before, named(parent, name)),
                    "held preflight generation unchanged")
            placeholder = owned.open(
                entry["name"], os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=bulk)
            try:
                reserved = os.fstat(placeholder)
                private_file(reserved)
                require(reserved.st_size == 0 and reserved.st_dev == before[0]
                        and _same_file_generation(_snapshot(reserved), _snapshot(os.stat(
                            entry["name"], dir_fd=bulk, follow_symlinks=False))),
                        "exclusive owned same-device empty placeholder")
                checkpoint(root_fd)
                immediate = current(fd)
                require(_same_file_generation(row["actual"], immediate)
                        and _same_file_generation(immediate, named(parent, name))
                        and _same_file_generation(_snapshot(reserved),
                                                  _snapshot(os.fstat(placeholder)))
                        and _same_file_generation(_snapshot(reserved), _snapshot(os.stat(
                            entry["name"], dir_fd=bulk, follow_symlinks=False))),
                        "immediate source and own placeholder generation")
                move = dict(key=entry["key"], source_root=str(
                    PARTIAL if parent == partial_bulk else SOURCE),
                    source_name=name, expected=row["expected"], preflight=row["actual"],
                    before=immediate, after=None, closed=None, state="RENAME_ATTEMPTED")
                moved.append(move)  # Record uncertain rename outcomes, never retry.
                os.rename(name, entry["name"], src_dir_fd=parent, dst_dir_fd=bulk)
                move["state"] = "RENAMED_UNVALIDATED"
                require(os.fstat(placeholder).st_nlink == 0, "only own placeholder replaced")
            finally:
                close_fd(placeholder)
            after = current(fd)
            move["after"] = after
            require(_same_rename_generation(immediate, after)
                    and _same_file_generation(after, named(bulk, entry["name"])),
                    "own rename changes only ctime/logical eight stable and dense")
            absent(parent, name)
            os.fsync(parent)
            os.fsync(bulk)
            # close_fd owns the actual generation. Never probe/retry its number.
            close_fd(fd)
            closed = named(bulk, entry["name"])
            move["closed"] = closed
            require(_same_file_generation(after, closed), "post-close logical generation/density")
            move["state"] = "COMPLETE"
            files.append(dict(entry, identity=closed))
            checkpoint(root_fd)
        manifest = dict(original, root_identity=directory_identity(os.fstat(root_fd)),
                        bulk_identity=directory_identity(os.fstat(bulk)), files=files,
                        preparation=dict(original["preparation"], cache=CACHE))
        exclusive_json(bulk, "manifest.json", manifest)
        receipt = dict(
            v=1, op="v307-owned-volume-recovery", source=str(SOURCE),
            partial=str(PARTIAL), destination=root_text,
            source_root_identity=roots[0], partial_root_identity=roots[1],
            destination_root_identity=roots[2],
            source_evidence=PINS, partial_failure_evidence=FAILURE_PIN,
            consumed_failure=failure, moved=moved,
            original_preparation=original["preparation"], cache=CACHE,
            hashes_are_expectations_only=True, new_bulk_written_bytes=0,
            moved_bytes=TOTAL_BYTES, elapsed_ns=time.monotonic_ns() - start)
        exclusive_json(bulk, "staging-receipt.json", receipt)
        os.fsync(root_fd)
        checkpoint(root_fd)
    except BaseException as primary:
        if bulk is not None:
            try:
                anchors.check()
                exclusive_json(bulk, "staging-failure.json", dict(
                    v=1, status="FAIL", error_type=type(primary).__name__,
                    error=str(primary)[:1024], source=str(SOURCE), partial=str(PARTIAL),
                    source_evidence=PINS, partial_failure_evidence=FAILURE_PIN,
                    moved=moved, elapsed_ns=time.monotonic_ns() - start))
            except BaseException as secondary:
                primary.add_note("failure evidence unavailable: " + type(secondary).__name__)
        raise
    finally:
        primary = sys.exception()
        try:
            anchors.close()
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note("anchor close failed: " + type(secondary).__name__)
    elapsed = time.monotonic_ns() - start
    require(elapsed < 5_000_000_000, "completed recovery including cleanup exceeded5s")
    return dict(v=1, status="COMPLETE", elapsed_ns=elapsed, moved_bytes=TOTAL_BYTES,
                new_bulk_written_bytes=0, files=4, cache=CACHE)


if __name__ == "__main__":
    require(len(sys.argv) == 3 and sys.argv[1] == "--root",
            "expected exactly --root ABSOLUTE_FRESH_0700_ROOT")
    print(json.dumps(relocate(sys.argv[2]), sort_keys=True, ensure_ascii=True,
                     allow_nan=False, separators=(",", ":")), flush=True)
