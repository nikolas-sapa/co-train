"""V307 allocation snapshots, not authority. No relocation or huge test calls."""
import pytest

from train import test_qualification_ac_volume as volume
from train import _qualification_volume_recovery_fixture as recovery

prohibit_real_effects = volume.prohibit_real_effects


@pytest.fixture(params=(volume, recovery), ids=("consumer", "recovery"))
def module(request):
    return request.param


def identity():
    # Layout is the independently observed stat descriptor format; the first
    # nine fields are the logical identity enforced by the actual C/A reader.
    return [16777233, 1001, 0o100600, 503, 20, 1, 2147483648, 100, 200, 4210688]


def test_dense_allocation_change_preserves_logical_generation(module):
    before, after = identity(), identity()
    after[9] = 4194304
    assert module._same_file_generation(before, after), "dense allocation drift is not identity drift"


@pytest.mark.parametrize("field", range(9))
def test_each_logical_generation_field_still_must_match(module, field):
    before, after = identity(), identity()
    after[field] += 1
    assert not module._same_file_generation(before, after)


@pytest.mark.parametrize("side", ("before", "after"))
def test_sparse_historical_or_current_allocation_refuses(module, side):
    before, after = identity(), identity()
    (before if side == "before" else after)[9] = 0
    assert not module._same_file_generation(before, after)


def test_rename_allows_ctime_and_dense_allocation_change(module):
    before, after = identity(), identity()
    after[8], after[9] = 999, 4194304
    assert module._same_rename_generation(before, after), "rename preserves data, not allocation accounting"


@pytest.mark.parametrize("field", range(8))
def test_each_rename_stable_field_still_must_match(module, field):
    before, after = identity(), identity()
    after[field] += 1
    assert not module._same_rename_generation(before, after)


@pytest.mark.parametrize("side", ("before", "after"))
def test_sparse_before_or_after_rename_refuses(module, side):
    before, after = identity(), identity()
    (before if side == "before" else after)[9] = 0
    assert not module._same_rename_generation(before, after)
