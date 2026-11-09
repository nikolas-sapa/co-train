"""Five new actual metadata routing regressions, no filesystem fixture reads."""
import pytest

from train import _qualification_timeout_recovery_fixture as recovery


@pytest.mark.parametrize("index", range(5))
def test_fixed_metadata_read_path_keeps_provenance_and_private_staging(index):
    base, name, size, sha = recovery.PINS[index]
    original = (base, name, size, sha)
    expected_parent = recovery.SOURCE if index < 2 else (
        recovery.WORKSPACE / "parent-v320-recovery-evidence")
    assert recovery._metadata_path(base, name) == expected_parent / name
    assert recovery.PINS[index] == original
