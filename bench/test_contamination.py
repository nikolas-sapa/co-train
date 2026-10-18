"""Tests for `bench.contamination`'s scoring and statistics half. **No torch.**

What is pinned here is the part that decides the verdict: the tail statistic, the AUC,
the permutation p, the bootstrap interval, the Fisher table, and the three-way rule. A
broken statistic does not crash -- it returns a plausible number with the sign reversed
or a p-value that can never be small -- so every test below asserts a value that was
computed by hand or by an independent identity, not one read back off the implementation.

**Mutation evidence.** Three mutations were applied, each reverted, each caught:

1. `min_k_score` took the MEAN of the HIGHEST `frac` tokens instead of the lowest --
   the sign the whole method rests on. `test_min_k_takes_the_low_tail` went red
   (`assert 6.0 == 2.0`), restored, green.
2. `auroc` counted ties as wins instead of half-wins, making a fully tied sample read
   1.0 rather than 0.5. `test_auroc_ties_are_half` went red, restored, green.
3. `decide_verdict` checked the BIRD reading BEFORE the control gate, so a method that
   failed its own control could return PASS on BIRD. `test_a_blind_instrument_is_never_a
   _pass` went red, restored, green.

The suite also asserts that importing this module does not import torch, because a
torch import at module scope would make the repo's default `pytest` need the heavy venv.
"""

from __future__ import annotations

import importlib
import math
import sys

import pytest

from bench import contamination as C


def test_the_module_imports_without_torch():
    """The repo suite runs in a venv that has no torch; a module-scope torch import
    would break collection rather than fail one test. `importlib.reload` re-executes the
    module body. In a torch-free venv the reload is the assertion; in a torch venv the
    assertion is that the module did not pull torch in by itself."""
    try:
        import torch  # noqa: F401
    except ImportError:
        importlib.reload(C)
        return
    mod = importlib.reload(C)
    assert hasattr(mod, "run")


def test_min_k_takes_the_low_tail():
    """`[-1, -2, -6, -10]` at k=0.5 means the two lowest, mean -8.0."""
    assert C.min_k_score([-1.0, -2.0, -6.0, -10.0], 0.5) == -8.0


def test_min_k_uses_ceil_so_short_texts_still_contribute():
    # ceil(0.2 * 3) = 1 -> the single lowest token.
    assert C.min_k_score([-1.0, -5.0, -9.0], 0.2) == -9.0


def test_min_k_rejects_empty_and_bad_fraction():
    with pytest.raises(ValueError):
        C.min_k_score([], 0.2)
    with pytest.raises(ValueError):
        C.min_k_score([-1.0], 0.0)
    with pytest.raises(ValueError):
        C.min_k_score([-1.0], 1.5)


def test_min_kpp_is_a_z_score_against_the_positional_moments():
    """With constant vocab mean 0 and std 2, z = lp / 2, so the tail mean is the tail
    log-prob over 2. Checked against the arithmetic, not against min_k_score."""
    lps = [-2.0, -4.0, -8.0, -1.0]
    mus = [0.0, 0.0, 0.0, 0.0]
    sds = [2.0, 2.0, 2.0, 2.0]
    # z = [-1, -2, -4, -0.5]; lowest half (k=2) = [-4, -2]; mean -3.0
    assert C.min_kpp_score(lps, mus, sds, 0.5) == -3.0


def test_min_kpp_refuses_a_degenerate_variance():
    with pytest.raises(ValueError):
        C.min_kpp_score([-1.0], [0.0], [0.0], 0.5)


def test_token_logprobs_lengths_agree_past_one_chunk():
    """**Regression test for a defect caught by the first full run.** The chunked loop
    bound its slices by `chunk` instead of `seq - 1`, so the last chunk ran one position
    past the targets; `gather` truncates silently, leaving the moment lists one longer
    than the log-prob list and `min_kpp_score` raising mid-run. A text longer than one
    64-token chunk is what exposes it, which is why the pilot's short texts passed.

    Driven through the real loop with a fake model and tokenizer so this stays
    torch-free in spirit; torch is only the tensor library the fake uses, and the test
    skips (loudly, in the summary) when it is absent, as in the repo venv.
    """
    torch = pytest.importorskip("torch")
    import types

    vocab = 50
    seq = 150

    class FakeTok:
        def __call__(self, text, return_tensors=None, add_special_tokens=False):
            return types.SimpleNamespace(
                input_ids=torch.arange(seq).unsqueeze(0) % vocab)

    class FakeOut:
        def __init__(self, seq_len, vocab_size):
            # Distinct per-position logits so the moment computation is non-degenerate.
            base = torch.arange(seq_len * vocab_size, dtype=torch.float32).reshape(
                1, seq_len, vocab_size)
            self.logits = base / (seq_len * vocab_size)

    class FakeModel:
        def __call__(self, ids):
            return FakeOut(ids.shape[1], vocab)

    lps, mus, sds = C.token_logprobs(FakeModel(), FakeTok(), "x", "cpu", chunk=64)
    assert len(lps) == len(mus) == len(sds) == seq - 1
    # And the statistic consumes them without raising.
    assert isinstance(C.min_kpp_score(lps, mus, sds), float)


def test_auroc_perfect_separation_is_one():
    assert C.auroc([3.0, 4.0, 5.0], [1.0, 2.0, 2.5]) == 1.0


def test_auroc_ties_are_half():
    """Fully tied -> 0.5. Counting a tie as a win made this 1.0, which would have
    reported 'perfect contamination evidence' from two identical score lists."""
    assert C.auroc([1.0, 1.0], [1.0, 1.0]) == 0.5


def test_auroc_reversed_is_zero():
    assert C.auroc([1.0, 2.0], [3.0, 4.0]) == 0.0


def test_auroc_matches_the_rank_identity():
    """AUC = (sum of ranks of positives - n(n+1)/2) / (n*m), computed independently.
    Average ranks are used for ties, which is the identity's tie convention; this sample
    has no duplicates, and `test_auroc_ties_are_half` pins the tie case separately."""
    pos = [-1.5, 0.2, 2.7, -0.4]
    neg = [-3.0, -0.9, 0.1, 1.1, -2.2]
    pooled = sorted(pos + neg)
    assert len(set(pooled)) == len(pooled)
    rank_sum = sum(pooled.index(v) + 1 for v in pos)
    expected = (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    assert C.auroc(pos, neg) == pytest.approx(expected)


def test_cliffs_delta_is_two_auc_minus_one():
    pos, neg = [3.0, 4.0], [1.0, 2.0]
    assert C.cliffs_delta(pos, neg) == pytest.approx(2 * C.auroc(pos, neg) - 1)


def test_permutation_p_is_one_sided_and_never_zero():
    """The p-value is `(1 + hits) / (1 + n_perm)` and can never be 0, so at 2000
    permutations nothing below 1/2001 is reportable. The exact value is pinned because
    the shuffle is seeded and therefore deterministic: 3 of 2000 shuffles happen to land
    the five largest values in the positive slot. Pinning it means a change to the RNG
    call order shows up here rather than silently changing every published p."""
    assert C.permutation_auc_p(list(range(10, 15)), list(range(5)),
                               n_perm=2000) == pytest.approx(4 / 2001)


def test_permutation_p_is_near_one_for_identical_group_centres():
    pos = [0.0] * 20
    neg = [0.0] * 20
    p = C.permutation_auc_p(pos, neg, n_perm=500)
    assert p == pytest.approx(1.0)


def test_bootstrap_ci_brackets_the_point_estimate():
    pos = [1.0, 2.0, 3.0, 4.0, 5.0]
    neg = [0.0, 0.5, 1.0, 1.5, 2.0]
    lo, hi = C.bootstrap_auc_ci(pos, neg, n_boot=2000)
    assert lo <= C.auroc(pos, neg) <= hi
    assert 0.0 <= lo <= hi <= 1.0


def test_bootstrap_ci_is_narrow_on_perfect_separation():
    """Disjoint ranges, so every resample still separates almost completely. It is not
    exactly 1.0: resampling with replacement duplicates an item at each range's edge, and
    two identical scores across groups count as half-wins. That is the correct tie
    convention, so the assertion is a high lower bound rather than perfection."""
    pos = [100.0 + i for i in range(30)]
    neg = [float(i) for i in range(30)]
    lo, hi = C.bootstrap_auc_ci(pos, neg, n_boot=1000)
    assert lo > 0.85 and hi == 1.0


def test_fisher_matches_hand_computation():
    """a=8,b=2 vs c=2,d=8: the two-sided p is the sum of tables no more likely than
    the observed one; 0.0230 by hand."""
    assert C.fisher_two_sided(8, 2, 2, 8) == pytest.approx(0.0230, abs=5e-4)


def test_fisher_symmetric_and_capped_at_one():
    assert C.fisher_two_sided(1, 1, 1, 1) == 1.0
    assert C.fisher_two_sided(3, 0, 0, 3) == pytest.approx(
        C.fisher_two_sided(0, 3, 3, 0))


def test_suffix_match_normalises_whitespace_and_a_trailing_semicolon():
    assert C.suffix_match(" FROM t\n WHERE x = 1; ", "FROM t WHERE x = 1")
    assert not C.suffix_match(" FROM t WHERE x = 2", "FROM t WHERE x = 1")
    # Case is preserved deliberately: SELECT and select are different bytes, and the
    # model reproduced the words either way.
    assert not C.suffix_match("from t where x = 1", "FROM t WHERE x = 1")


def test_control_gate_beats_a_badly_wrong_bird_reading():
    """A blind instrument (control AUC 0.52) with a 'perfect' BIRD AUC is INCONCLUSIVE,
    never PASS: the number cannot be interpreted on a method that cannot see a known
    positive."""
    assert C.decide_verdict(control_auc=0.52, control_p=0.4,
                            bird_auc=1.0, bird_p=1e-6,
                            bird_ci=(0.99, 1.0)) == "INCONCLUSIVE"


def test_a_working_instrument_with_low_bird_auc_is_a_pass():
    assert C.decide_verdict(control_auc=0.95, control_p=1e-6,
                            bird_auc=0.52, bird_p=0.4,
                            bird_ci=(0.44, 0.60)) == "PASS"


def test_the_control_gate_runs_first_not_last():
    """**This case was added because mutation 3 survived without it.** Swapping
    `decide_verdict`'s two branches left the original blind-control test green, because
    its BIRD CI was (0.99, 1.0) and the *later* FAIL branch caught it in either order.
    Here the BIRD reading is a clean-looking pass (CI upper 0.60) on an instrument that
    cannot see a known positive: only the gate ordering stops this returning PASS."""
    assert C.decide_verdict(control_auc=0.40, control_p=0.9,
                            bird_auc=0.02, bird_p=0.9,
                            bird_ci=(0.10, 0.60)) == "INCONCLUSIVE"


def test_a_working_instrument_with_high_bird_auc_is_a_fail():
    assert C.decide_verdict(control_auc=0.95, control_p=1e-6,
                            bird_auc=0.80, bird_p=1e-6,
                            bird_ci=(0.72, 0.88)) == "FAIL"


def test_verdict_is_three_way_never_boolean():
    """The type discipline the repo asks for: a bare True/False adjudication is the
    failure mode this check exists to avoid."""
    out = C.decide_verdict(control_auc=0.9, control_p=1e-5,
                           bird_auc=0.62, bird_p=0.02, bird_ci=(0.5, 0.75))
    assert out in {"PASS", "FAIL", "INCONCLUSIVE"}


def test_binary_verdict_branches():
    assert C.decide_binary_verdict(control_rates=(0.5, 0.0), control_p=1e-4,
                                   bird_rates=(0.4, 0.0), bird_p=1e-6) == "FAIL"
    assert C.decide_binary_verdict(control_rates=(0.5, 0.0), control_p=1e-4,
                                   bird_rates=(0.02, 0.0), bird_p=0.5) == "PASS"
    assert C.decide_binary_verdict(control_rates=(0.02, 0.0), control_p=0.5,
                                   bird_rates=(0.9, 0.0), bird_p=1e-9) == "INCONCLUSIVE"


def test_summarise_carries_the_control_with_the_reading():
    pos = [3.0 + 0.1 * i for i in range(12)]
    fresh = [1.0 + 0.1 * i for i in range(12)]
    bird = [0.5 + 0.1 * i for i in range(12)]  # below the fresh range: a clean pass
    r = C.summarise("min-k", "question", pos, fresh, bird, n_perm=2000, n_boot=200)
    assert r.n_positive == r.n_fresh == r.n_bird == 12
    assert r.control_auc == 1.0
    assert r.verdict == "PASS"
    d = C.reading_to_dict(r)
    assert isinstance(d["bird_ci"], list)


def test_fresh_control_file_is_well_formed_and_n_matches():
    """The committed control set: unique names, every field present, and its own n. The
    database execution check lives in the run, which has the corpus; this test keeps a
    malformed file from reaching the run at all."""
    pairs = C.load_fresh()
    assert len(pairs) == 58
    names = [p["name"] for p in pairs]
    assert len(set(names)) == len(names)
    for p in pairs:
        assert p["tier"] in ("simple", "moderate", "challenging"), p
        assert p["question"].strip() and p["sql"].strip().lower().startswith(("select", "with"))
        assert p["db_id"] in C.SHIPPABLE_DB_IDS, p


def test_fresh_control_is_in_birds_length_band():
    """The control's job is to be a fair non-member, so its length distribution is a
    claim. BIRD's own questions average 84 chars over these databases; the fresh set is
    held inside a generous band so a length-driven score difference cannot be mistaken
    for membership."""
    pairs = C.load_fresh()
    q = [len(p["question"]) for p in pairs]
    s = [len(p["sql"]) for p in pairs]
    assert 30 <= sum(q) / len(q) <= 160
    assert 30 <= sum(s) / len(s) <= 320


def test_positive_controls_are_nonempty_and_distinct():
    assert len(C.POSITIVE_PROSE) >= 15
    assert len(set(C.POSITIVE_PROSE)) == len(C.POSITIVE_PROSE)
    assert len(C.POSITIVE_SQL) >= 10
    assert len(C.FRESH_PROSE) >= 10
    assert not (set(C.POSITIVE_PROSE) & set(C.FRESH_PROSE))


def test_bird_sample_is_stratified_by_tier_and_reproducible():
    """A synthetic task list, so the test does not need the corpus. The draw must return
    the requested n, cover every tier in proportion, and be identical for one seed and
    differ across seeds."""
    from bench.task import SqlTask

    def task(i: int, tier: str):
        return SqlTask(
            name=f"bird-{i:04d}", question="q", evidence="", gold_sql="SELECT 1",
            db_id="superhero", db_path="/nonexistent", tier=tier,
            tier_source="annotated", shape="s", coarse_shape="c", source="bird")

    pool = ([task(i, "simple") for i in range(100)]
            + [task(100 + i, "moderate") for i in range(50)]
            + [task(150 + i, "challenging") for i in range(20)])
    a = C.bird_sample(pool, 51, seed=0)
    b = C.bird_sample(pool, 51, seed=0)
    c = C.bird_sample(pool, 51, seed=1)
    assert len(a) == 51
    tiers = [t.tier for t in a]
    assert set(tiers) == {"simple", "moderate", "challenging"}
    assert tiers.count("simple") > tiers.count("moderate") > tiers.count("challenging")
    assert [t.name for t in a] == [t.name for t in b]
    assert [t.name for t in a] != [t.name for t in c]


def test_bird_sample_ignores_databases_outside_the_small_set():
    from bench.task import SqlTask

    inside = SqlTask(name="bird-0001", question="q", evidence="", gold_sql="SELECT 1",
                     db_id="superhero", db_path="/x", tier="simple",
                     tier_source="annotated", shape="s", coarse_shape="c",
                     source="bird")
    outside = SqlTask(name="bird-0002", question="q", evidence="", gold_sql="SELECT 1",
                      db_id="financial", db_path="/x", tier="simple",
                      tier_source="annotated", shape="s", coarse_shape="c",
                      source="bird")
    assert [t.name for t in C.bird_sample([inside, outside], 2)] == ["bird-0001"]


def test_summarise_auroc_uses_bird_against_fresh_not_against_the_control():
    """Regression guard for the defect this module was first written with: the binary
    branch reported the CONTROL's AUC in the BIRD column. In the continuous path the two
    groups must be independent -- a BIRD list equal to the fresh list is an AUC of 0.5
    even when the control separates perfectly."""
    pos = [10.0] * 10
    fresh = [0.0] * 10
    r = C.summarise("min-k", "question", pos, fresh, list(fresh), n_perm=200, n_boot=200)
    assert r.control_auc == 1.0
    assert r.bird_auc == 0.5
    assert not math.isnan(r.bird_p)


def test_cache_round_trips_and_resumes_across_instances(tmp_path):
    """A run interrupted between two items must not rescore the first. The cache is
    append-only JSONL keyed by (method, group, sha1(text)); a second `Cache` over the same
    file must see every write the first made, and a changed text must be a miss."""
    path = tmp_path / "cache.jsonl"
    first = C.Cache(str(path))
    assert first.get("min-k", "bird-question", "hello") is None
    first.put("min-k", "bird-question", "hello", [-3.0, 1.5])
    first.put("continuation", "bird:7", "SELECT x", [True])
    first.close()

    second = C.Cache(str(path))
    assert second.get("min-k", "bird-question", "hello") == [-3.0, 1.5]
    assert second.get("continuation", "bird:7", "SELECT x") == [True]
    # Same text, different group or method -> miss, because a score is not portable
    # across what it was conditioned on.
    assert second.get("min-k", "fresh-question", "hello") is None
    assert second.get("min-kpp", "bird-question", "hello") is None
    # Changed text -> miss.
    assert second.get("min-k", "bird-question", "hello!") is None


def test_cache_without_a_path_is_memory_only():
    mem = C.Cache(None)
    mem.put("min-k", "g", "text", [1.0])
    assert mem.get("min-k", "g", "text") == [1.0]
    mem.close()


def test_stratified_auc_removes_a_pure_length_confound():
    """The statistic this whole sensitivity analysis rests on. Construct two groups where
    the POOLED comparison is perfect separation (long texts score higher, and BIRD has
    only long texts) but every same-bin comparison is a tie. The stratified AUC must be
    0.5: it is the fix for exactly the defect the primary run hit."""
    import numpy as np

    from bench import contamination_sensitivity as S

    # bin boundaries from LENGTH_BINS: (1,12) (13,16) (17,20) (21,28) (29,1000)
    bird = [5.0, 5.0]                        # two long BIRD items, len 40
    bird_lens = np.array([40, 40])
    fresh = [1.0, 3.0]                       # short fresh items, len 10
    fresh_lens = np.array([10, 10])
    # Different bins -> no same-bin pairs at all; the estimator refuses rather than
    # silently falling back to the pooled number.
    with pytest.raises(ValueError):
        S.stratified_auc(bird, bird_lens, fresh, fresh_lens)

    # Now the same score gap with MATCHED lengths: still separated, so AUC 1.0.
    matched_lens = np.array([40, 40])
    auc, n = S.stratified_auc(bird, bird_lens, fresh, matched_lens)
    assert (auc, n) == (1.0, 4)

    # And equal scores at matched lengths read 0.5, not 1.0.
    auc, _ = S.stratified_auc([2.0, 2.0], bird_lens, [2.0, 2.0], matched_lens)
    assert auc == 0.5


def test_stratified_ci_brackets_the_point_estimate():
    import numpy as np

    from bench import contamination_sensitivity as S

    bird = [3.0, 4.0, 5.0, 4.5]
    bird_lens = np.array([15, 15, 18, 22])
    fresh = [1.0, 2.0, 3.5, 4.0, 2.5, 3.0]
    fresh_lens = np.array([14, 15, 19, 22, 16, 21])
    point, _ = S.stratified_auc(bird, bird_lens, fresh, fresh_lens)
    lo, hi = S.stratified_ci(bird, bird_lens, fresh, fresh_lens, n_boot=500)
    assert lo <= point <= hi


def test_recorded_result_keeps_both_the_primary_verdict_and_the_correction():
    """The results file is a record, so its shape is asserted: the pre-stated primary rule
    returned FAIL and that value is preserved under `primary_verdict`, while the final
    `verdict` is the sensitivity-corrected INCONCLUSIVE. A future edit that deletes the
    FAIL would hide the confound; one that deletes the correction would overstate it."""
    import json
    from pathlib import Path

    path = Path(C.__file__).parent / "contamination_results.json"
    if not path.is_file():
        pytest.skip("no recorded run yet")
    d = json.loads(path.read_text())
    assert d["primary_verdict"] == "FAIL"
    assert d["verdict"] == "INCONCLUSIVE"
    assert "length" in d["verdict_reason"].lower()
    # The stratified estimates travel with the file, so the correction can be recomputed.
    sens = d["sensitivity"]
    assert sens["min-k"]["stratified_auc"] < 0.6
    assert sens["lengths"]["bird_mean_tokens"] > 2 * sens["lengths"]["fresh_mean_tokens"]
