# Sanitized public reference, UNRUN derivative. No execution authority.
"""V316 SOURCE ONLY, UNRUN. Parent owns tests/reviews/ONE recovery.

RED's unchecked pure parser must NEVER be used for recovery. GREEN also needs
independent clearance/freeze before the single parent-supervised invocation.
Closed --root CLI, internal5s including cleanup, parent external10s.
No bulk reads/copies/hashes/allocation/deletion, processes, threads or retries.
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
SOURCE = Path("/qualification-reference/scratch/pc309-80pg7a82")
METADATA_ROOT = WORKSPACE / "parent-v320-recovery-evidence"
CACHE = "reused-generated-after-previous-full-read-not-evicted"
RESERVE = 5_609_139_779
FILE_BYTES = 2147483648
TOTAL_BYTES = 8589934592
KEYS = (
    "checkpoint-1/native-observation.json", "checkpoint-1/trainer_state.json",
    "checkpoint-2/native-observation.json", "checkpoint-2/trainer_state.json",
)
HASHES = (
    "0000000000000000000000000000000000000000000000000000000000000001",
    "0000000000000000000000000000000000000000000000000000000000000002",
    "0000000000000000000000000000000000000000000000000000000000000003",
    "0000000000000000000000000000000000000000000000000000000000000004",
)
PINS = (
    (SOURCE, "bulk-input/manifest.json", 1419,
     "000000000000000000000000000000000000000000000000000000000000000a"),
    (SOURCE, "bulk-input/staging-receipt.json", 4617,
     "000000000000000000000000000000000000000000000000000000000000000b"),
    (WORKSPACE, "parent-v310-volume-nonpass.json", 1461,
     "000000000000000000000000000000000000000000000000000000000000000c"),
    (WORKSPACE, "parent-v314-diagnostic-run-authorization.json", 866,
     "000000000000000000000000000000000000000000000000000000000000000d"),
    (WORKSPACE, "parent-v316-timeout-source-generation-exact.json", 3652,
     "000000000000000000000000000000000000000000000000000000000000000e"),
)
DIRECTORIES = {
    ".": [101, 1006, 16832, 503, 20],
    "bulk-input": [101, 1001, 16832, 503, 20],
    "volume-case": [101, 1009, 16832, 503, 20],
    "volume-case/export": [101, 1010, 16832, 503, 20],
    "volume-case/export/run": [101, 1011, 16832, 503, 20],
    "volume-case/export/run/checkpoint-1": [101, 1012, 16832, 503, 20],
    "volume-case/export/run/checkpoint-2": [101, 1013, 16832, 503, 20],
}
_LOADER = []


def require(ok, message):
    if not ok:
        raise ValueError(message)


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


def _shape(value, fields):
    require(type(value) is dict and set(value) == set(fields.split()),
            "closed provenance object")


def _identity(value):
    require(type(value) is list and len(value) == 10
            and all(type(n) is int and n >= 0 for n in value),
            "complete exact integer identity")
    require(value[0] == DIRECTORIES["."][0] and value[2:7]
            == [33152, 503, 20, 1, FILE_BYTES] and value[9] * 512 >= value[6],
            "historical/current dense private single-link2GiB identity")


def _validated_sources(manifest, receipt, timeout, generation):
    try:
        _shape(manifest, "v op root_identity bulk_identity files preparation")
        _shape(generation, "v op source source_directories files evidence prior_status "
               "hashes_are_expectations_only bulk_bytes_read new_bulk_written_bytes")
        require(manifest["v"] == generation["v"] == 1
                and manifest["op"] == "v290-owned-volume"
                and generation["op"] == "v316-timeout-source-generation"
                and generation["source"] == str(SOURCE)
                and generation["prior_status"] == "NONPASS_EXTERNAL_TIMEOUT"
                and generation["hashes_are_expectations_only"] is True
                and generation["bulk_bytes_read"] == generation["new_bulk_written_bytes"] == 0,
                "exact timeout source generation operation/root/facts")
        require(generation["source_directories"] == DIRECTORIES
                and manifest["root_identity"] == DIRECTORIES["."]
                and manifest["bulk_identity"] == DIRECTORIES["bulk-input"],
                "all seven exact source directory bindings")
        require(generation["evidence"] == [
            dict(base=str(base), name=name, size=size, sha256=sha)
            for base, name, size, sha in PINS[:4]], "fixed evidence correspondence")
        prep_fields = "buffer_bytes cache elapsed_ns final_free_bytes initial_free_bytes written_bytes"
        _shape(manifest["preparation"], prep_fields)
        prep = manifest["preparation"]
        require(prep["cache"] == CACHE and prep["written_bytes"] == TOTAL_BYTES
                and prep["buffer_bytes"] == 8388608
                and all(type(prep[n]) is int and prep[n] >= 0 for n in (
                    "elapsed_ns", "final_free_bytes", "initial_free_bytes")),
                "historical preparation exact8GiB/reused cache")
        _shape(receipt, "v op source partial destination source_root_identity "
               "partial_root_identity destination_root_identity source_evidence "
               "partial_failure_evidence consumed_failure moved original_preparation "
               "cache hashes_are_expectations_only new_bulk_written_bytes moved_bytes elapsed_ns")
        require(receipt["v"] == 1 and receipt["op"] == "v307-owned-volume-recovery"
                and receipt["destination"] == str(SOURCE)
                and receipt["destination_root_identity"] == DIRECTORIES["."]
                and receipt["source"] == "/qualification-reference/scratch/pc297-4yntz90o"
                and receipt["partial"] == "/qualification-reference/scratch/pc305-nklrdyr7"
                and receipt["source_root_identity"] == [101, 1008, 16832, 503, 20]
                and receipt["partial_root_identity"] == [101, 1007, 16832, 503, 20]
                and receipt["cache"] == CACHE and receipt["hashes_are_expectations_only"] is True
                and receipt["new_bulk_written_bytes"] == 0 and receipt["moved_bytes"] == TOTAL_BYTES
                and type(receipt["elapsed_ns"]) is int and 0 <= receipt["elapsed_ns"] < 5_000_000_000,
                "completed historical recovery root/bytes/cache")
        _shape(receipt["original_preparation"], prep_fields)
        require(receipt["original_preparation"]["cache"] == "fresh-generated-not-evicted"
                and dict(receipt["original_preparation"], cache=CACHE) == prep,
                "unchanged original historical preparation")
        require(receipt["source_evidence"] == [
            ["execution.json", 497, "0000000000000000000000000000000000000000000000000000000000000006"],
            ["diagnostics/v290-volume.json", 3788, "0000000000000000000000000000000000000000000000000000000000000007"],
            ["bulk-input/manifest.json", 1393, "0000000000000000000000000000000000000000000000000000000000000008"]]
                and receipt["partial_failure_evidence"] == [
                    "bulk-input/staging-failure.json", 633,
                    "0000000000000000000000000000000000000000000000000000000000000005"],
                "retained immutable historical evidence pins")
        failure = receipt["consumed_failure"]
        _shape(failure, "v status error_type error moved elapsed_ns")
        require(failure["v"] == 1 and failure["status"] == "FAIL"
                and failure["error_type"] == "ValueError"
                and failure["error"] == "exact prior validated source generation"
                and type(failure["moved"]) is list and len(failure["moved"]) == 2
                and type(failure["elapsed_ns"]) is int and failure["elapsed_ns"] >= 0,
                "preserved consumed V305 failure")
        for index, old in enumerate(failure["moved"]):
            _shape(old, "key before after")
            _identity(old["before"])
            _identity(old["after"])
            require(old["key"] == KEYS[index]
                    and _same_rename_generation(old["before"], old["after"]),
                    "historical consumed ordered move")
        _shape(timeout, "status spec spec_sha256 root actual_execute_exit signal "
               "external_limit_seconds internal_limit_seconds execution_report_absent "
               "metrics_absent buffered_logs_empty observed_state previous_success recovery "
               "one_recovery_consumed no_unchanged_retry source_only_diagnosis_task gpu_native_science")
        require(timeout["status"] == "NONPASS_EXTERNAL_TIMEOUT"
                and timeout["root"] == str(SOURCE) and timeout["signal"] == "TIMEOUT"
                and timeout["actual_execute_exit"] is None
                and timeout["internal_limit_seconds"] == 29
                and timeout["external_limit_seconds"] == 30
                and timeout["execution_report_absent"] is True
                and timeout["metrics_absent"] is True and timeout["buffered_logs_empty"] is True
                and timeout["one_recovery_consumed"] is True
                and timeout["no_unchanged_retry"] is True
                and timeout["spec"] == "parent-v310-optimized-ac-volume-spec.json"
                and timeout["spec_sha256"]
                == "0000000000000000000000000000000000000000000000000000000000000009",
                "prior timeout remains NONPASS, limits/consumed claims unchanged")
        previous = timeout["recovery"]
        _shape(previous, "actual_exit internal_seconds wall_seconds bytes new_bulk_bytes "
               "manifest_sha256 receipt_sha256 metadata_identity_validation full_content_hash")
        require(previous["actual_exit"] == 0 and previous["bytes"] == TOTAL_BYTES
                and previous["new_bulk_bytes"] == 0
                and 0 <= previous["internal_seconds"] < 5
                and 0 <= previous["wall_seconds"] < 10
                and previous["manifest_sha256"] == PINS[0][3]
                and previous["receipt_sha256"] == PINS[1][3]
                and previous["metadata_identity_validation"] == "PASS_before_test"
                and previous["full_content_hash"] == "NOT_CONFIRMED_THIS_RUN",
                "historical recovery does not prove current full content")
        require(type(manifest["files"]) is list and type(generation["files"]) is list
                and type(receipt["moved"]) is list
                and len(manifest["files"]) == len(generation["files"]) == len(receipt["moved"]) == 4,
                "exact four files and four completed ordered receipt moves")
        seen = set()
        for index, (historical, actual, move) in enumerate(zip(
                manifest["files"], generation["files"], receipt["moved"])):
            for entry in (historical, actual):
                _shape(entry, "identity key name sha256 size")
                _identity(entry["identity"])
                require(entry["key"] == KEYS[index] and entry["name"] == f"blob-{index + 1}.bin"
                        and type(entry["size"]) is int and entry["size"] == FILE_BYTES
                        and entry["sha256"] == HASHES[index],
                        "fixed ordered keys/names/sizes/hash expectations")
            _shape(move, "key source_root source_name expected preflight before after closed state")
            for field in ("expected", "preflight", "before", "after", "closed"):
                _identity(move[field])
            require(move["key"] == KEYS[index] and move["state"] == "COMPLETE"
                    and move["source_root"] == receipt["partial" if index < 2 else "source"]
                    and move["source_name"] == (
                        f"blob-{index + 1}.bin" if index < 2 else KEYS[index].split("/")[1])
                    and _same_file_generation(move["expected"], move["preflight"])
                    and _same_file_generation(move["preflight"], move["before"])
                    and _same_rename_generation(move["before"], move["after"])
                    and _same_file_generation(move["after"], move["closed"])
                    and _same_file_generation(historical["identity"], move["closed"])
                    and _same_rename_generation(move["closed"], actual["identity"]),
                    "strict historical-to-current logical provenance, ctime only at rename")
            if index < 2:
                require(_same_file_generation(failure["moved"][index]["after"], move["expected"]),
                        "consumed split failure bound to prior recovery")
            inode = tuple(actual["identity"][:2])
            require(inode not in seen, "nonaliased current source descriptors")
            seen.add(inode)
        return tuple(generation["files"])
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("malformed timeout recovery provenance") from error


def _metadata_path(base, relative):
    return (METADATA_ROOT if base == WORKSPACE else base) / relative


def _snapshot(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_blocks]


def load_helper():
    # Same-buffer pinned namespace definition only, never prepare/main.
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
        path = _metadata_path(base, relative)
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
                    "pinned historical/current metadata bytes")
            identity = _snapshot(before)
            require(_same_file_generation(identity, _snapshot(os.fstat(fd)))
                    and _same_file_generation(identity, _snapshot(os.stat(
                        path.name, dir_fd=parent, follow_symlinks=False))),
                    "stable pinned metadata")
        finally:
            close_fd(fd)
        require(_same_file_generation(identity, _snapshot(os.stat(
            path.name, dir_fd=parent, follow_symlinks=False))), "closed pinned metadata")
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
        manifest, prior_receipt, timeout, authorization, generation = (
            metadata(*pin) for pin in PINS)
        require(authorization["status"]
                == "USER_APPROVED_ONE_ADDITIONAL_REVIEWED_RECOVERY_AND_ONE_INSTRUMENTED_CPU_RUN"
                and authorization["answer"] == "Allow one after reviews and tests"
                and authorization["execution_status"] == "UNRUN_UNRESERVED"
                and authorization["prior_claims_not_reset"] == [
                    "parent-v305-relocation-claim.json", "parent-v309-recovery-claim.json"],
                "pinned single additional recovery authorization")
        sources = _validated_sources(manifest, prior_receipt, timeout, generation)
        require(len(sources) == 4 and tuple(e["key"] for e in sources) == KEYS,
                "exact four source descriptors")
        bound = {}
        for relative, expected in DIRECTORIES.items():
            fd = anchors.open(str(SOURCE if relative == "." else SOURCE / relative))
            require(directory_identity(os.fstat(fd)) == expected
                    == generation["source_directories"][relative],
                    "exact current named source directory binding")
            bound[relative] = fd
        root_fd = anchors.open(root_text)
        destination = Path(root_text)
        prior_roots = (SOURCE, WORKSPACE, Path(prior_receipt["source"]),
                       Path(prior_receipt["partial"]))
        require(not any(destination == prior or destination in prior.parents
                        or prior in destination.parents for prior in prior_roots),
                "fresh root disjoint from source/evidence/historical roots")
        destination_identity = directory_identity(os.fstat(root_fd))
        require(destination_identity[0] == DIRECTORIES["."][0]
                and tuple(destination_identity[:2]) not in {
                    tuple(value[:2]) for value in DIRECTORIES.values()},
                "distinct same-device destination root")
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
        seen = set()
        # Hold ALL FOUR actual source FDs/ancestry before destination creation.
        for entry in sources:
            checkpoint(root_fd)
            directory, leaf = entry["key"].split("/")
            parent = bound["volume-case/export/run/" + directory]
            absent(bound["bulk-input"], entry["name"])
            fd = owned.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                            | os.O_CLOEXEC, dir_fd=parent)
            actual = current(fd)
            require(_same_file_generation(entry["identity"], actual)
                    and _same_file_generation(actual, named(parent, leaf)),
                    "all-source opened preflight logical generation/density")
            require(actual[0] == destination_identity[0] and tuple(actual[:2]) not in seen,
                    "same-device distinct nonaliased source inodes")
            seen.add(tuple(actual[:2]))
            preflight.append(dict(fd=fd, parent=parent, name=leaf, entry=entry, actual=actual))
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
                move = dict(key=entry["key"], source_root=str(SOURCE), source_name=name,
                            expected=entry["identity"], preflight=row["actual"],
                            before=immediate, after=None, closed=None, state="RENAME_ATTEMPTED")
                moved.append(move)  # Record uncertainty BEFORE rename, never retry.
                os.rename(name, entry["name"], src_dir_fd=parent, dst_dir_fd=bulk)
                move["state"] = "RENAMED_UNVALIDATED"
                require(os.fstat(placeholder).st_nlink == 0, "only own placeholder replaced")
            finally:
                close_fd(placeholder)
            after = current(fd)
            move["after"] = after
            require(_same_rename_generation(immediate, after)
                    and _same_file_generation(after, named(bulk, entry["name"])),
                    "own rename first8 stable and both dense")
            absent(parent, name)
            os.fsync(parent)
            os.fsync(bulk)
            close_fd(fd)  # Never probe/retry this retired numeric descriptor.
            closed = named(bulk, entry["name"])
            move["closed"] = closed
            require(_same_file_generation(after, closed), "post-close first9/density")
            move["state"] = "COMPLETE"
            files.append(dict(entry, identity=closed))
            checkpoint(root_fd)
        new_manifest = dict(
            manifest, root_identity=destination_identity,
            bulk_identity=directory_identity(os.fstat(bulk)), files=files,
            preparation=dict(manifest["preparation"], cache=CACHE))
        exclusive_json(bulk, "manifest.json", new_manifest)
        exclusive_json(bulk, "staging-receipt.json", dict(
            v=1, op="v316-timeout-owned-volume-recovery", source=str(SOURCE),
            destination=root_text, source_directories=generation["source_directories"],
            metadata_read_root=str(METADATA_ROOT),
            destination_root_identity=destination_identity,
            evidence=[dict(base=str(base), name=name, size=size, sha256=sha)
                      for base, name, size, sha in PINS],
            prior_receipt=prior_receipt, prior_timeout=timeout, source_generation=generation,
            original_preparation=prior_receipt["original_preparation"], moved=moved,
            cache=CACHE, hashes_are_expectations_only=True,
            moved_bytes=TOTAL_BYTES, new_bulk_written_bytes=0,
            elapsed_ns=time.monotonic_ns() - start))
        os.fsync(root_fd)
        checkpoint(root_fd)
    except BaseException as primary:
        if bulk is not None:
            try:
                anchors.check()
                exclusive_json(bulk, "staging-failure.json", dict(
                    v=1, status="FAIL", error_type=type(primary).__name__,
                    error=str(primary)[:1024], source=str(SOURCE),
                    evidence=[dict(base=str(base), name=name, size=size, sha256=sha)
                              for base, name, size, sha in PINS],
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
