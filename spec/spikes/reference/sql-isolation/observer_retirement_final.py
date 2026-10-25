"""OFFLINE BLOCKED final attempt, not production/security/billing acceptance.

PROVES: root baseline1, two before-only identities, three managed retirements,
one accepted target-marker boundary, strict pure negative controls.
BLOCKED: owned KILL409 exits cleanup before observer retirement. Emergency
process-death reconciliation is cleanup only, not a successful protocol retry.
MISSING: baseline2/stability, remaining boundaries and actual native recovery pair.
SHORTCUT: local byte hashes are integrity, not authentication or TOCTOU protection.
No launcher imports, metadata access, root commands or guest evaluation here.
"""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

ROOT = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "observer-retirement-final-1sl59eoj"
)
READBACK = "9490a9a015f3e7e7e6c88b18427fefd2832608c15d85de8ad3db754e2bc708ab"


def main():
    raw = (ROOT / "source-readback.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == READBACK
    readback = json.loads(raw)
    for name, expected in readback["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for name, expected in readback["active_runtime_pins"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for link in readback["readonly_policy_symlinks"]:
        path = Path(link["path"])
        assert str(path.resolve()) == link["target"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == link["target_sha256"]
    baseline = json.loads((ROOT / "root-baseline-1.json").read_text())
    assert baseline["status"] == "TRUSTED_HOST_BASELINE" and baseline["links_returned"] == 12
    assert baseline["returncode"] == 0 and all(baseline["self_equals_vm_pid1"].values())
    assert baseline["stdin"] == "DEVNULL" and baseline["cli_absent"]
    assert not (ROOT / "root-baseline-2.json").exists()
    controls = json.loads((ROOT / "pure-controls-final.json").read_text())
    assert controls["passed"] == 31 and controls["subsequent_starts"] == controls["runtime_mutations"] == 0
    result = json.loads((ROOT / "final-result.json").read_text())
    assert result["overall_status"] == "BLOCKED_OWN_KILL409_INCOMPLETE_RETIREMENT"
    assert result["accepted_runtime_cases"] == 3 and result["runtime_jobs"] == 4
    assert result["managed_retirement_acks_before_remove"] == 3
    assert result["failure"]["http_status"] == 409 and result["failure"]["target_matches_owned"] is True
    assert result["failure"]["endpoint"] == "POST /containers/{owned}/kill"
    assert result["daemon_message_not_running"]
    assert result["failed_worker_final"]["observer_dead"] is False
    assert result["failed_worker_final"]["http_clients_remaining"] == 1
    assert result["owned_cids_absent"] == 4 and result["supervisors_absent"] == 8 and result["all_cli_absent"] == 16
    assert result["all_observer_processes_now_gone"] and result["all_logged_http_clients_finally_closed"]
    assert result["unrelated10_same"] and result["overlap_count"] == 0
    assert result["reservation_absent"] and result["durable_next_admission_block"]
    assert result["native_recovery_pair"] == "NOT_RUN" and result["stderr_cases"] == "NOT_RUN"
    assert result["deadline_replays"] == result["model_calls"] == 0
    print(json.dumps({"reference_validation": "VERIFIED_BLOCKED_EVIDENCE", "overall_status": result["overall_status"],
                      "accepted_runtime_cases": 3, "production_acceptance": False}))
    return 2  # No all-gates PASS or production-freeze claim.


if __name__ == "__main__":
    raise SystemExit(main())
