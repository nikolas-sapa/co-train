"""OFFLINE partial evidence only: BLOCKED_BASELINE_UNKNOWN, no corrected executor.

PROVES: one event-gated unchanged-order OWN404 control, then joined teardown.
MISSING: corrected retirement ordering/ineligibility/foreign-unknown negatives,
trusted VM-host baseline, new namespace checks, four target-marker cases, benign
role pair. No production freeze/security/billing acceptance.
SHORTCUT: host-specific local-byte hashes, not authentication or TOCTOU defense.
The old control ACK's ineligibility flag is NOT proof of a new admission policy.
Never imports a launcher, performs metadata probes or evaluates guest code.
"""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

ROOT = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "observer-retirement-spike-qrh4ikjq"
)
READBACK = "71dbac7d16de05dffaa514cc096af668163f908b6fdf3254a967eb190db34ea5"


def main():
    raw = (ROOT / "source-readback.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == READBACK
    readback = json.loads(raw)
    for name, expected in readback["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert readback["new_retirement_implementation"] is False
    control = json.loads((ROOT / "identity-control-result.json").read_text())
    assert control["status"] == "CONTROL_OWN404_PREDICATE_PASS"
    assert control["original_old_404_target"] == "UNKNOWN"
    assert control["new_ordering_applied"] is False
    assert control["capture"]["target_matches_owned"] is True
    assert control["stopped"]["target_matches_owned"] is True
    assert control["removed"]["status"] == 204
    error = control["actual_error"]
    assert error["target_matches_owned"] is True and error["phase"] == "REMOVED"
    assert error["http_status"] == 404 and error["stage"] == "body"
    assert (error["sample"], error["slot"]) == (control["capture"]["sample"], control["capture"]["slot"])
    assert control["capture"]["time"] < control["stopped"]["time"] < control["removed"]["time"] < error["time"]
    assert control["observer_joined"] and control["all_http_connections_closed"]
    result = json.loads((ROOT / "correction-result.json").read_text())
    assert result["overall_status"] == "BLOCKED_BASELINE_UNKNOWN"
    assert result["baseline"]["returncode"] == 1 and result["baseline"]["returned_lines"] == 6
    assert result["baseline"]["required_lines"] == 12
    assert result["actual_guest_cases"] == result["owned_cids_absent"] == 1
    assert result["supervisors_absent"] == 2 and result["all_cli_absent"] == 5
    assert result["observer_workers_joined"] == 53 and result["observer_join_seconds"] <= 1
    assert result["unrelated10_same"] and result["overlap_count"] == 0 and result["reservation_absent"]
    assert result["gates"]["new_retirement_ordering"] == "NOT_IMPLEMENTED_NOT_RUN"
    assert result["gates"]["foreign_unknown_retirement_negatives"] == "NOT_RUN"
    assert result["production_freeze"] is False and result["model_calls"] == 0
    print(json.dumps({"reference_validation": "PASS", "overall_status": "BLOCKED_BASELINE_UNKNOWN",
                      "control": "OWN404_PREDICATE_ONLY", "remaining_runtime_gates": "NOT_RUN"}))
    return 2  # Partial proof is deliberately not a green acceptance gate.


if __name__ == "__main__":
    raise SystemExit(main())
