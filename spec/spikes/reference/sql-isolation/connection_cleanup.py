"""Proven connection cleanup and partial live follow-up. NOT a launcher."""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

# SHORTCUT: disposable absolute path. No Docker/network/program execution.
ROOT = Path("/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/confinement-spike-cleanup-l901euc3")
MANIFEST_SHA256 = "bad9b9a86843d8fe3601b8712b22f9dc953f7534b6a42475e093e02214236891"

def verify_evidence():
    raw = (ROOT / "artifact-manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(raw)
    for name, expected in manifest["files"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    ownership = json.loads((ROOT / "ownership-check.json").read_text())
    assert ownership["active_aliases_reach_owned_http"]
    assert len(ownership["cases"]) == 16
    assert all(row["closed"] == 1 for row in ownership["cases"])
    sample = json.loads((ROOT / "observer-diagnostic.json").read_text())
    assert sample["ended"] - sample["started"] <= 4
    assert sample["available"] >= 469762048
    # PROVES: finally-close on actual active API aliases, one qualifying live
    # full sampler, SCORER surfaces, delayed start gates and five fault recoveries.
    # This historical sample is NOT current permission to launch.
    audit = json.loads((ROOT / "audit.json").read_text())
    assert audit["owned_ids_absent"] and audit["unrelated_states_unchanged"]
    assert audit["overlap_count"] == 0 and audit["active_reservation_absent"]
    assert audit["status"] == "BLOCKED_REEXEC_IDENTITY_ASSERTION"
    # MISSING: complete both-role reexec identities, denials, output/deadline
    # bounds and next benign pair. First guest assertion preserved, not retried.
    # Prior timeout cause UNKNOWN; no FD exhaustion or timeout-cure claim.
    return {"status": audit["status"], "pinned_files": len(manifest["files"]),
            "finally_cases": 16, "jobs": audit["jobs"],
            "cids_absent": len(audit["owned_container_ids"]),
            "supervisors_absent": len(audit["supervisor_pids_absent"]),
            "unrun_gates": audit["unrun_gates"]}

if __name__ == "__main__":
    print(json.dumps(verify_evidence(), sort_keys=True))
    raise SystemExit(2)  # Artifact integrity verified, architecture still BLOCKED.
