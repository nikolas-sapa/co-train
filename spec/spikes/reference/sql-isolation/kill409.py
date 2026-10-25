"""OFFLINE remaining-gates PASS, not a production launcher/security/billing proof.

PROVES: one real event-gated OWN SIGKILL409 -> fresh full-CID checked STOPPED ->
managed observer/CLI retirement ACK before DELETE; nine negative transitions;
three remaining target-marker boundaries, native unchanged PTC/scorer pair;
second and FINAL approved root namespace probe stable against pinned baseline1.

PRESERVES: prior three accepted jobs/eight reexec gates/10s and30s deadlines,
original failed UNRESOLVED case, original block plus operator CLOSED history.
LIMITS: ordinary daemon/surviving trusted supervisor. Sampling is mitigation.
No outage/reboot/dual-loss, production CV2/wrong-pin, rate or billing acceptance.
Local byte hashes are integrity, not authentication or TOCTOU immunity.
No imports of launchers, Docker calls, root commands or subprocesses here.
"""
import sys
if sys.flags.optimize:
    raise SystemExit("Reference requires assertions; optimized mode unsupported")

import hashlib
import json
from pathlib import Path

ROOT = Path(
    "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
    "kill409-spike-le2xr2tn"
)
READBACK = "ab074d404406dd81b419d47c5086408bd2ae23d4c4aa4b74079b24c0e8814b26"


def main():
    raw = (ROOT / "source-readback.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == READBACK
    manifest = json.loads(raw)
    parent = Path(
        "/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/"
        "observer-retirement-final-1sl59eoj"
    )
    old_raw = (parent / "source-readback.json").read_bytes()
    assert hashlib.sha256(old_raw).hexdigest() == manifest["old_readback_sha256"]
    for name, expected in json.loads(old_raw)["sha256"].items():
        assert hashlib.sha256((parent / name).read_bytes()).hexdigest() == expected
    here = Path(__file__).resolve().parent
    for name, expected in manifest["old_seven_references_sha256"].items():
        assert hashlib.sha256((here / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((here / "README.md").read_bytes()).hexdigest() == manifest["readme_sha256"]
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for name, expected in manifest["active_runtime_pins"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for link in manifest["readonly_policy_symlinks"]:
        path = Path(link["path"])
        assert str(path.resolve()) == link["target"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == link["target_sha256"]
    for path, expected in manifest["frozen_native_imports"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
    assert hashlib.sha256(Path(manifest["operator_closed_history_path"]).read_bytes()).hexdigest() == manifest["operator_closed_history_sha256"]
    result = json.loads((ROOT / "final-result.json").read_text())
    assert result["overall_status"] == "PASS_REMAINING_GATES"
    assert result["runtime_jobs"] == result["accepted_remaining_jobs"] == 6
    assert result["actual_owned_kill409_control"] and result["pure_negatives"] == 9
    assert result["pure_next_start_callbacks"] == 0
    assert result["managed_retirement_acks_before_remove"] == 6
    assert result["root_total_privileged_commands"] == 2 and result["new_before_root_commands"] == 0
    assert result["root_baseline2_stable"] and result["all_observers_joined"]
    assert result["new_owned_cids_absent"] == 6 and result["old_owned_cid_hashes_absent"] == 4
    assert result["supervisors_absent"] == 20
    assert result["new_observer_cli_absent"] == 20 and result["old_observer_cli_absent"] == 15
    assert result["root_cli_absent"] == 2 and result["all_logged_http_finally_closed"]
    assert result["unrelated10_same"] and result["overlap_count"] == 0 and result["reservation_absent"]
    assert result["old_block_reconciliation"] == "CLOSED_HISTORY_ORIGINAL_BLOCK_RETAINED"
    assert result["old_failed_case_status"] == "UNRESOLVED_NOT_ACCEPTED" and not result["new_metadata_block"]
    assert result["min_admission_available"] >= 469762048
    assert result["min_prestart_available"] >= 469762048 and result["min_monitored_available"] >= 201326592
    assert result["max_prestart_age"] <= 4 and result["max_sample_seconds"] <= 4
    assert result["max_retirement_join"] <= 1
    assert result["native_pair"] == {"program_bytes": 59, "whole_scorer_bytes": 88, "complete_scorer_fields": 6, "exit": 0, "oom": False}
    assert result["carried_forward"]["deadline_replays"] == result["model_calls"] == 0
    assert result["production_acceptance"] is False and result["spend_verified"] is False
    assert result["budget_50_authorization"] == "BLOCKED"
    print(json.dumps({"overall_status": result["overall_status"], "accepted_remaining_jobs": 6,
                      "production_acceptance": False, "budget_50_authorization": "BLOCKED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
