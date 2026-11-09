"""Keep parent-only qualification fixtures out of ordinary pytest collection.

These sources preserve scoped local experiments, not portable runtime admission.
Explicit collection or --noconftest does not grant execution authority.
"""
from pathlib import Path

_ROOT = Path(__file__).parent

_PARENT_ONLY_TESTS = (
    "train/test_qualification_ac_valid_output.py",
    "train/test_qualification_ac_volume.py",
    "train/test_qualification_allocation_accounting.py",
    "train/test_qualification_armed_set_performance.py",
    "train/test_qualification_directory_projection_spike.py",
    "train/test_qualification_engineering_host.py",
    "train/test_qualification_engineering_run.py",
    "train/test_qualification_isolated_owner.py",
    "train/test_qualification_isolated_run.py",
    "train/test_qualification_lease_performance.py",
    "train/test_qualification_modal_host.py",
    "train/test_qualification_modal_transport.py",
    "train/test_qualification_mode_bit_spike.py",
    "train/test_qualification_owned_stop.py",
    "train/test_qualification_private_metadata.py",
    "train/test_qualification_reservation_custody.py",
    "train/test_qualification_timeout_recovery.py",
    "train/test_qualification_volume_custody.py",
    "train/test_qualification_volume_journal.py",
)

collect_ignore = [
    str(_ROOT / name)
    for name in (*_PARENT_ONLY_TESTS, "qualification_controls", "spec/spikes")
]
