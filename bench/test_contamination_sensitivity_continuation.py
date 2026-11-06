import numpy as np
import pytest

from bench import contamination_sensitivity as S


def estimate(kind, vectors):
    if kind == "auc":
        return S.stratified_auc(*vectors)
    return S.stratified_ci(*vectors, n_boot=1, seed=0)


@pytest.mark.parametrize("kind", ["auc", "ci"])
@pytest.mark.parametrize("side", [0, 2])
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_nonfinite_scores_are_not_auc_losses(kind, side, invalid):
    vectors = [np.array([5.0, 5.0]), np.array([40.0, 40.0]),
               np.array([1.0, 3.0]), np.array([40.0, 40.0])]
    vectors[side][0] = invalid
    with pytest.raises(ValueError, match="finite"):
        estimate(kind, vectors)


@pytest.mark.parametrize("kind", ["auc", "ci"])
@pytest.mark.parametrize("side", [1, 3])
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_nonfinite_lengths_do_not_shrink_pair_denominator(kind, side, invalid):
    vectors = [np.array([5.0, 5.0]), np.array([40.0, 40.0]),
               np.array([1.0, 3.0]), np.array([40.0, 40.0])]
    vectors[side][0] = invalid
    with pytest.raises(ValueError, match="finite"):
        estimate(kind, vectors)


def test_finite_same_bin_estimator_unchanged():
    lengths = np.array([40, 40])
    assert S.stratified_auc([5.0, 5.0], lengths, [1.0, 3.0], lengths) == (1.0, 4)
    assert S.stratified_auc([2.0, 2.0], lengths, [2.0, 2.0], lengths) == (0.5, 4)
    assert S.stratified_auc([1.0, 1.0], lengths, [3.0, 5.0], lengths) == (0.0, 4)
    assert S.stratified_ci(
        [5.0, 5.0], lengths, [1.0, 3.0], lengths, n_boot=20, seed=0
    ) == (1.0, 1.0)
    assert S.stratified_ci(
        [2.0, 2.0], lengths, [1.0, 3.0], lengths, n_boot=20, seed=0
    ) == (0.0, 1.0)


@pytest.mark.parametrize("kind", ["auc", "ci"])
@pytest.mark.parametrize("side", [0, 1, 2, 3, 4, 5])
def test_vectors_must_be_one_dimensional_and_aligned(kind, side):
    vectors = [np.array([5.0, 5.0]), np.array([40.0, 40.0]),
               np.array([1.0, 3.0]), np.array([40.0, 40.0])]
    if side < 4:
        vectors[side] = vectors[side].reshape(2, 1)
    else:
        vectors[1 if side == 4 else 3] = np.array([40.0])
    with pytest.raises(ValueError):
        estimate(kind, vectors)


def test_finite_bin_boundaries_and_no_pairs_unchanged():
    bird_lens = np.array([1, 13, 17, 21, 29, 1001])
    fresh_lens = np.array([12, 16, 20, 28, 1000, 0])
    assert S.stratified_auc(
        [5.0] * 6, bird_lens, [1.0] * 6, fresh_lens
    ) == (1.0, 5)
    with pytest.raises(ValueError, match="no same-bin pairs"):
        S.stratified_auc([5.0], np.array([40]), [1.0], np.array([10]))
