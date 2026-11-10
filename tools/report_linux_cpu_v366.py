"""Validate bounded diagnostic evidence; never echo untrusted payload text."""
import json
import math
import os
import re
import stat
import sys

VERSION = "v366-storage-diagnostic-1"
STAGES = {"seed", "build", "write", "hash", "checkpoint", "anchors",
          "free_space", "fsync", "writer_close", "readback", "reader_close",
          "anchors_close", "ancestry_setup", "writer_open", "reader_open"}
LABELS = {"VAR_TMP", "MNT"}
ERRORS = {"ValueError", "RuntimeError", "OSError", "PermissionError",
          "FileNotFoundError", "TimeoutError", "MemoryError"}


def require(ok):
    if not ok:
        raise ValueError()


def integer(value, low=0, high=2**63 - 1):
    require(type(value) is int and low <= value <= high)
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def read(path, cap):
    require(os.path.isabs(path) and os.path.realpath(path) == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and before.st_size <= cap)
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, cap + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            require(len(raw) <= cap)
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
                    s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(identity(before) == identity(os.fstat(fd))
                == identity(os.stat(path, follow_symlinks=False)))
        return raw.decode("ascii", "strict")
    finally:
        os.close(fd)


def phase(line):
    require(line.startswith("DIAG_PHASE ") and len(line.encode("ascii")) <= 512)
    p = json.loads(line[11:], object_pairs_hook=unique)
    require(type(p) is dict and set(p) == {"candidate", "stage", "event",
                                          "elapsed_ns", "cpu_ns", "bytes"}
            and p["candidate"] in LABELS and p["stage"] in STAGES
            and p["event"] in {"start", "end"})
    return dict(candidate=p["candidate"], stage=p["stage"], event=p["event"],
                elapsed_ns=integer(p["elapsed_ns"]),
                cpu_ns=integer(p["cpu_ns"]),
                bytes=integer(p["bytes"], high=67108864))


def validate(value, wall):
    require(type(value) is dict and value.get("status") == "DIAGNOSTIC_COMPLETE"
            and value.get("version") == VERSION)
    require(value.get("source_pins_stable") is True
            and value.get("custody_closed") is True)
    for flag in ("full_volume_qualified", "sdk_reaping_proven",
                 "native_qualified", "gpu_unlocked"):
        require(value.get(flag) is False)
    elapsed = integer(value["elapsed_ns"], high=28999999999)
    written = integer(value["total_written_bytes"], 33550336, 67100672)
    require(value["guard_fixture_reserve_bytes"] == 8192
            and type(value["guard_fixture_reserve_bytes"]) is int
            and value["total_reserved_bytes"] == written + 8192
            and type(value["total_reserved_bytes"]) is int)
    rss = integer(value["peak_rss_bytes"], 1, 268435456)
    require(type(wall) is float and math.isfinite(wall) and 0 <= wall < 30)
    require(value["python_version"] == "3.12.13"
            and type(value["openssl_version"]) is str
            and re.fullmatch(r"OpenSSL [0-9]+\.[0-9]+\.[0-9]+[a-z]?(?: [0-9]{1,2} [A-Za-z]{3} [0-9]{4})?",
                             value["openssl_version"])
            and value["hash_backend"] in {"_hashlib", "_sha2"})
    clocks = {}
    for key in ("monotonic_resolution_ns", "cpu_resolution_ns"):
        n = value[key]
        require(type(n) in (int, float) and math.isfinite(n) and 0 < n <= 1e9)
        clocks[key] = n
    require(type(value["candidates"]) is list and len(value["candidates"]) == 2)
    candidates, complete, seen = [], set(), set()
    for c in value["candidates"]:
        require(type(c) is dict and c["candidate"] in LABELS
                and c["candidate"] not in seen
                and c["result"] in {"COMPLETE", "NOT_MEASURED"}
                and c["fstype_class"] in {"UNKNOWN", "TMPFS", "RAMFS", "REAL_STORAGE"}
                and type(c["permission"]) is bool)
        seen.add(c["candidate"])
        free = integer(c["free_bytes"])
        if c["result"] == "COMPLETE":
            require(c["permission"] and c["fstype_class"] == "REAL_STORAGE"
                    and free >= 14199074371)
            complete.add(c["candidate"])
        candidates.append(dict(candidate=c["candidate"], result=c["result"],
                               free_bytes=free, fstype_class=c["fstype_class"],
                               permission=c["permission"]))
    require(complete and written == len(complete) * 33550336)
    require(type(value["rows"]) is list and 1 <= len(value["rows"]) <= 64)
    rows = []
    for row in value["rows"]:
        require(type(row) is dict and row["candidate"] in complete
                and row["stage"] in STAGES)
        rows.append(dict(candidate=row["candidate"], stage=row["stage"],
                         wall_ns=integer(row["wall_ns"], high=elapsed),
                         cpu_ns=integer(row["cpu_ns"], high=elapsed)))
    expected = dict(seed=1, build=4, write=4, hash=4, checkpoint=8, anchors=1,
                    free_space=1, fsync=1, writer_close=1, readback=1,
                    reader_close=1, anchors_close=1, ancestry_setup=1,
                    writer_open=1, reader_open=1)
    for label in complete:
        require({stage: sum(r["candidate"] == label and r["stage"] == stage
                            for r in rows) for stage in STAGES} == expected)
    require(sum(row["wall_ns"] for row in rows) <= elapsed)
    return dict(status="DIAGNOSTIC_COMPLETE", version=VERSION, elapsed_ns=elapsed,
                external_wall_seconds=wall, total_written_bytes=written,
                total_reserved_bytes=written + 8192, guard_fixture_reserve_bytes=8192,
                peak_rss_bytes=rss,
                rows=rows, candidates=candidates, source_pins_stable=True,
                custody_closed=True, python_version="3.12.13",
                openssl_version=value["openssl_version"],
                hash_backend=value["hash_backend"], **clocks,
                full_volume_qualified=False, sdk_reaping_proven=False,
                native_qualified=False, gpu_unlocked=False)


def main():
    require(len(sys.argv) == 9 and sys.argv[1::2]
            == ["--stdout", "--stderr", "--wall", "--exit-code"])
    last = None
    try:
        stderr = read(sys.argv[4], 65536)
        lines = stderr.splitlines()
        require(len(lines) <= 128)
        phases = [phase(line) for line in lines]
        if phases:
            last = phases[-1]
        value = json.loads(read(sys.argv[2], 32768), object_pairs_hook=unique)
        require(type(value) is dict)
        if sys.argv[8] != "0":
            failure = dict(status="NONPASS", cleanup="UNKNOWN")
            if value.get("error_type") in ERRORS:
                failure["error_type"] = value["error_type"]
            if last is not None:
                failure["last_phase"] = last
            return failure, 1
        wall = float(read(sys.argv[6], 256).strip())
        result = validate(value, wall)
        expected_phases = [(r["candidate"], r["stage"], event)
                           for r in result["rows"] for event in ("start", "end")]
        require([(p["candidate"], p["stage"], p["event"]) for p in phases]
                == expected_phases)
        require(all(p["elapsed_ns"] <= result["elapsed_ns"] for p in phases)
                and all(a["elapsed_ns"] <= b["elapsed_ns"]
                        and a["cpu_ns"] <= b["cpu_ns"] and a["bytes"] <= b["bytes"]
                        for a, b in zip(phases, phases[1:]))
                and phases[-1]["bytes"] == result["total_written_bytes"])
        return result, 0
    except BaseException:
        failure = dict(status="NONPASS", cleanup="UNKNOWN")
        if last is not None:
            failure["last_phase"] = last
        return failure, 1


if __name__ == "__main__":
    try:
        result, code = main()
        print(json.dumps(result, separators=(",", ":"), allow_nan=False), flush=True)
    except BaseException:
        print('{"status":"NONPASS","cleanup":"UNKNOWN"}', flush=True)
        code = 1
    sys.exit(code)
