"""Print bounded non-private terminal evidence, never raw fixture diagnostics."""
import argparse
import json
import math
import os
from pathlib import Path
import stat
import sys


def read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not (stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.getuid() and before.st_size <= limit):
            raise ValueError("report file metadata")
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink,
                               s.st_uid, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if (len(raw) != before.st_size
                or signature(before) != signature(after)
                or signature(before) != signature(path.lstat())):
            raise ValueError("report file changed")
        return raw
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--wall", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()
    summary = {"status": "NONPASS", "terminal_exit": args.exit_code,
               "cleanup": "unproven", "native_qualification": False,
               "sdk_owned_child_reaps_proven": False}
    try:
        if args.exit_code != 0:
            raise ValueError("nonzero terminal exit")
        lines = read(args.stdout, 2_097_152).decode("utf-8").splitlines()
        if len(lines) != 1:
            raise ValueError("exactly one terminal report required")
        report = json.loads(lines[0])
        wall = float(read(args.wall, 64).decode("ascii").strip())
        if not (math.isfinite(wall) and 0 < wall < 30):
            raise ValueError("external wall gate")
        if not (report["status"] == "PASS" and report["cases"] == 1
                and report["failures"] == report["errors"] == report["skips"] == 0
                and report["pytest_exit"] == 0
                and report["source_pins_stable"] is True
                and report["origins_verified"] is True
                and report["unclosed_bound_sockets"] == 0
                and report["forbidden_operations"] == []
                and type(report["elapsed_ns"]) is int
                and 0 < report["elapsed_ns"] < 29_000_000_000
                and report["preparation"]["written_bytes"] == 8_589_934_592
                and report["native_qualification"] is False
                and report["sdk_owned_child_reaps_proven"] is False):
            raise ValueError("qualification terminal gate")
        metrics = report["volume_metrics"]
        readers = metrics["reader_counters"]
        bulk = [row for row in readers if row["bytes"] == 2_147_483_648]
        if not (len(readers) == 8 and len(bulk) == 4
                and sum(row["bytes"] for row in bulk) == 8_589_934_592
                and all(row["eof_reads"] == row["closed_identity_checks"] == 1
                        and row["positive_reads"] > 0
                        and 0 < row["maximum_positive_bytes"]
                        <= row["requested_maximum"] <= 65536 for row in readers)
                and metrics["c_calls"] == metrics["receipt_calls"] == 1
                and metrics["release_completed"] is True
                and metrics["registry_live_after_release"] == 0):
            raise ValueError("original reader/lifecycle evidence")
        summary.update(status="PASS", cleanup="reported complete for synthetic path",
                       cases=1, failures=0, errors=0, skips=0,
                       elapsed_ns=report["elapsed_ns"], external_wall_seconds=wall,
                       written_bytes=report["preparation"]["written_bytes"],
                       source_pins_stable=True, origins_verified=True,
                       readers=len(readers), eof_observations=8,
                       closed_reader_identity_checks=8,
                       lifecycle="synthetic observations",
                       cache="fresh-generated-not-evicted-no-cold-cache-claim")
    except (KeyError, TypeError, ValueError, OSError, UnicodeError):
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 1
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
