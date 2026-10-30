"""Validate preserved PARTIAL reexec evidence, OFFLINE ONLY.

PROVES: both-role kernel reexec/denial/output/deadline probes; sensitive controls.
BLOCKED: post-fault complete benign pair, raw-stat HTTP 404 stopped further jobs.
SHORTCUT: local selected-byte hashes, not authentication, attestation or TOCTOU
protection. Historical lifecycle.py receipts remain UNPINNED semantic checks.
MISSING: production executor/security acceptance, daemon/dual-supervisor failure
guarantees, provider/model/billing proof. Never evaluates guest text on this host.
"""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

ROOT = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "final-reexec-spike-c4ogmely"
)
READBACK = "5c6686f242cf4825c4aab7ee74bf4c0b5d41bd8a1167ae4c2d5a53b6af4603ef"
REVIEWED_REFERENCES = {
    "spike.py": "6485adc658b48e7ca400cec6ae6ca2ad02555702bbd15c18bed288e259603903",
    "lifecycle.py": "0aaaa8d4d47bfa7d5d4e9d76e708584f4c311e8d87cf9c7605df852234d6fe6d",
    "confinement.py": "8f285eedc75b06dcf63d9e4276a18097cd27820bf71c0af4be74de9cf23c5f2b",
    "connection_cleanup.py": "356eebde5d9bbcf78f2ffdd8a7ca79fc7ce39b147bc5b2b7be153b4cab4edc70",
}


def main():
    for name, expected in REVIEWED_REFERENCES.items():
        assert hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() == expected
    raw = (ROOT / "offline-readback.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == READBACK
    readback = json.loads(raw)
    for name, expected in readback["scratch_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    controls = json.loads((ROOT / "comparator-checks.json").read_text())
    assert controls["passed"] == len(controls["cases"]) == 138
    assert controls["nonenv_fields"] == 14 and controls["nested_fields"] == 13
    assert controls["external_resource_calls"] == 0
    review = json.loads((ROOT / "reference-checks.json").read_text())
    assert review["baseline_pin_check"] and review["mutated_watchdog_rejected"]
    assert review["helper_imports_or_daemon_calls"] == 0
    assert len(review["optimized_controls"]) == 4
    assert all(x["optimized_rejected"] and x["scratch_or_helper_or_daemon_access"] == 0
               for x in review["optimized_controls"])
    first = json.loads((ROOT / "reexec-receipts.json").read_text())
    rest = json.loads((ROOT / "remaining-receipts.json").read_text())
    assert len(first) == 5 and len(rest) == 2
    identities = [x for x in first if x["mode"] == "identity"]
    assert {x["role"] for x in identities} == {"program", "scorer"}
    for receipt in identities:
        assert receipt["before"]["kernel"] == receipt["after"]["kernel"]
        assert receipt["socket_fork"] == {"socket": 1, "fork": 1}
        assert receipt["environment_delta"]["added"] == ["PWD"]
        assert receipt["environment_delta"]["removed"] == receipt["environment_delta"]["changed"] == []
    overflow = json.loads((ROOT / "bound-checks.json").read_text())
    assert overflow["actual_scorer_stdout_boundary_pass"] and overflow["mutations_rejected"] == 3
    result = json.loads((ROOT / "acceptance.json").read_text())
    assert result["status"] == "BLOCKED" and result["all_requested_guest_gates"] == 8
    assert result["jobs"] == result["owned_cids_absent"] == 9
    assert result["supervisors_absent"] == 18 and result["cli_absent"] == 117
    assert result["unrelated_states_unchanged"] and result["unrelated_count"] == 10
    assert result["overlap_count"] == 0 and result["reservation_absent"]
    error = result["failure"]["metadata_errors"][0]
    assert error["slot"] == "stats[0]" and error["stage"] == "body" and error["http_status"] == 404
    assert readback["no_creates_or_starts_after_metadata_failure"] and readback["scorer_benign_unrun"]
    print(json.dumps({"reference_validation": "PASS", "overall_gate": "BLOCKED_BENIGN_PAIR",
                      "reason": "raw-stat HTTP 404; no further guest dispatch",
                      "boundary_guest_gates_passed": 8, "production_security_acceptance": False}))
    return 2  # Deliberately nonzero: preserved partial proof is not a green gate.


if __name__ == "__main__":
    raise SystemExit(main())
