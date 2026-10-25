"""Validate the preserved PARTIAL lifecycle proof. No container execution.

PROVES: hashes pin guardian/controller/helper sources and policy bytes.
Audit/fault/journal/surface receipts receive UNPINNED semantic checks only,
not hash-bound immutable-original or authentication checks.
SHORTCUT: host-specific scratch, assertions, experimental JSON and fixed fixture.
MISSING: writable-mqueue resolution, both-role FD/env and re-exec proof,
daemon-outage guarantee, dual-supervisor loss, production implementation.
"""

import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

ROOT = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "lifecycle-spike-24d8d7b6"
)
SOURCES = {
    "life.py": "74cf0a7b1a9740d1fa18c1a5a52e0b783e912d1c857e0e1bca88325cb6bc7438",
    "guardian.py": "2f3701075f658d153d71e7263d441e1b915549c681e893dcd297a276cbaba43a",
    "controller.py": "af4f1e87ee7df347e843e35f9e6a9f0c678fc698e8179e31012b9e6676300783",
    "driver.py": "eedd30c4904ff955cbbf25f4e32b86323236fd89e94ad15fd93605a1d423c28a",
    "faults.py": "c7ab94f725f1e4fa4a95d9155b2de5e95f57c37f3b911b245f0d3361d2d2e94c",
    "surface_guest.py": "b60a0f04aa10cb165784808f6090bafb66786288ddb1ec118ed35b4c909d3456",
    "surfaces.py": "5b85cb389702d392b8b99225ba65332143e440b41f9fc42c88df6903b058ab7c",
    "audit.py": "a0f526795f8480657bfda096d48882110277ddbff4cb66d8f926aebc407bc944",
}
POLICY = "70daca97ff5306ac0dbf512a4461e412ed3df32e7fdb8cb48673e5466c97fac9"


def main():
    for name, expected in SOURCES.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((ROOT / "policy.json").read_bytes()).hexdigest() == POLICY
    audit = json.loads((ROOT / "audit.json").read_text())
    assert audit["status"] == "BLOCKED_WRITABLE_MQUEUE"
    assert audit["jobs"] == 33 and len(audit["owned_container_ids"]) == 32
    assert audit["owned_ids_absent"] and audit["unrelated_states_unchanged"]
    assert audit["overlap_count"] == 0 and audit["active_reservation_absent"]
    assert not (ROOT / "unresolved-reservation.json").exists()
    faults = json.loads((ROOT / "fault-receipts.json").read_text())
    assert len(faults) == 10
    assert all(row["resolved"] and row["seconds_after_trigger"] <= 12 for row in faults)
    for row in faults:
        journal = json.loads((Path(row["job"]) / "journal.json").read_text())
        assert journal["status"] == "RESOLVED_ABSENT"
        assert journal["create_calls"] <= 1 and journal["start_calls"] <= 1
    blocker = json.loads((ROOT / "surface-blocker.json").read_text())
    assert blocker["mqueue_openat_create_allowed"]
    assert blocker["mq_open_errno"] == 1
    print("LIFECYCLE RECEIPTS PASS; EXTENSION BLOCKED: writable mqueue; re-exec UNVERIFIED")


if __name__ == "__main__":
    main()
