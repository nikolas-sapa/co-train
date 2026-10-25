"""Pinned PARTIAL confinement spike. Not a launcher or production API."""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

# SHORTCUT: absolute disposable paths. No Docker/network/host program execution.
ROOT = Path("/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/confinement-spike-8gaeoa1e")
MANIFEST_SHA256 = "5707b2554569560f8e4bf2f612602da34ffa1c748fd1454caa2a281f1747fdc3"
OLD = Path("/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/isolation-spike-256-nqg8aj6a")
OLD_HELPERS = {
    "lab.py": "989aac41a1e47de323a8782daed81f353d58ab50fbc6899229c7b09067dba73c",
    "core.py": "3cd9dea0241aff672a748cdeb9ea5ba05fc564b74f4b86661592d6a6dfe6f46a",
}

def verify_preserved_evidence():
    raw = (ROOT / "artifact-manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(raw)
    for name, expected in manifest["files"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    for name, expected in OLD_HELPERS.items():
        assert hashlib.sha256((OLD / name).read_bytes()).hexdigest() == expected
    audit = json.loads((ROOT / "audit.json").read_text())
    assert audit["status"] == "BLOCKED_MEMORY_METADATA_TRANSPORT"
    assert audit["owned_ids_absent"] and audit["supervisor_pids_absent"]
    assert audit["unrelated_states_unchanged"] and audit["overlap_count"] == 0
    # PROVES: integrity of 107 files, actual one-entry sensitivity, PROGRAM
    # surfaces and both-role effective config inspections. See recorded receipts.
    # MISSING: SCORER inventory, delayed-start/EOF/deadline tests, new-config
    # critical faults, reexec/bounds. Latest observer diagnostic FAILED, not a
    # validated implementation. Never promote these partial results as green.
    return {"status": audit["status"], "pinned_files": len(manifest["files"]),
            "jobs": audit["jobs"], "owned_ids_absent": len(audit["owned_container_ids"]),
            "supervisor_pids_absent": len(audit["supervisor_pids_absent"]),
            "unrun_gates": audit["unrun_gates"]}

if __name__ == "__main__":
    print(json.dumps(verify_preserved_evidence(), sort_keys=True))
    raise SystemExit(2)  # Deliberately BLOCKED, even when evidence hashes verify.
