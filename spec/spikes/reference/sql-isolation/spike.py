"""Replay the disposable 256-MiB proof, NOT a production executor.

SHORTCUT: requires the preserved, host-specific scratch harness and staged bundles.
MISSING: packaging, hostile protocol validation, crash-safe prelaunch registration,
independent security review, production integration, inference and billing gates.
"""

import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode is unsupported")

import hashlib
import json
from pathlib import Path

SCRATCH = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "isolation-spike-256-nqg8aj6a"
)
HELPERS = {
    "lab.py": "989aac41a1e47de323a8782daed81f353d58ab50fbc6899229c7b09067dba73c",
    "core.py": "3cd9dea0241aff672a748cdeb9ea5ba05fc564b74f4b86661592d6a6dfe6f46a",
    "watchdog.py": "ef8a9d3f40483f00761df9a0062aec319ef500625aa993e889ceefbe5c8a95c7",
}
SOURCE_MANIFEST = "296135e2c7cb7eabd82e00766713aad1f3d27f66cea480a2bf4f74ec08184d80"
PROFILE = "7db0790356ebe3372b8032958d9f77cba5599dd70929ff836f107085982ddb55"


def verify_pins():
    # SHORTCUT: pins local experimental helpers, not a distribution/attestation.
    for name, expected in HELPERS.items():
        assert hashlib.sha256((SCRATCH / name).read_bytes()).hexdigest() == expected, (name, "helper pin mismatch")
    sources = json.loads((SCRATCH / "source-hashes.json").read_text())
    canonical = json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == SOURCE_MANIFEST
    for name, expected in sources.items():
        assert hashlib.sha256((SCRATCH / name).read_bytes()).hexdigest() == expected


def main():
    # ROOT == SCRATCH below binds the actual lab.launch watchdog path to this
    # pre-import check. Source integrity only, not authentication or TOCTOU defense.
    verify_pins()
    sys.path.insert(0, str(SCRATCH))
    from core import EXPECTED, QUERY, bootstrap, record, scorer, strict
    from lab import CAP, IMAGE, ROOT, api, launch, profile, urllib

    assert ROOT == SCRATCH and CAP == 268435456
    encoded = json.dumps(profile(), separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == PROFILE
    image = api("GET", "/images/" + urllib.parse.quote(IMAGE, safe="") + "/json")
    assert image["Id"] == IMAGE.split("@")[1]
    assert image["Os"] == "linux" and image["Architecture"] == "arm64"
    # No pull path. Docker create/start fail if the pinned image is absent.
    # PROVES: actual run_ptc_program/sql_catalog sees only its RO bundle + DB,
    # discovers the quoted table, runs native SQLite, prints count 3 + final SQL.
    program = record(launch("reference-program", bootstrap(diagnostics=True)))
    assert program["stdout"] == EXPECTED
    assert program["watchdog"]["state"]["ExitCode"] == 0

    # PROVES: a different fresh compartment executes unchanged whole protected EX.
    # PROGRAM Python is never evaluated in this SCORER. Gold only enters this call.
    scored = record(
        launch(
            "reference-scorer",
            scorer(QUERY, QUERY),
            bundle="scorer",
            deadline=30,
            outcap=65536,
        )
    )
    result = strict(scored)
    assert result == {
        "score": 1.0,
        "status": "match",
        "valid": True,
        "detail": "",
        "n_pred_rows": 1,
        "n_gold_rows": 1,
    }
    assert program["id"] != scored["id"]
    assert program["watchdog"]["owned_absent"] and scored["watchdog"]["owned_absent"]
    print(json.dumps({"reference_replay": "PASS", "result": result}))


if __name__ == "__main__":
    main()
