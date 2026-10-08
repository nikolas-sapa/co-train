"""`paired.py`'s own suite.

This tool decides the project's headline number, and until now it had no tests. The
session that built it found a bug in its own power function using live data (`p >= 1`
called the unanimous-discordance case undetectable), which is the argument for these:
an adjudication tool that is wrong is worse than no tool, because its output looks
like a result.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math import comb  # noqa: E402
import random  # noqa: E402

from ptc.paired import (  # noqa: E402
    mcnemar_exact,
    paired,
    power_pairs,
    refuse_voids,
    rollouts,
    split_tiers,
)


def test_a_partial_arm_is_refused_rather_than_averaged():
    """The defect this guard exists for: an intersection silently narrows the
    comparison. If one arm dies partway through, the survivors still intersect, so a
    29-task run reported `n (paired) 12` and a broken run read as a clean underpowered
    one. Unequal sets mean the pairing is gone."""
    full = {f"t{i}": 1.0 for i in range(29)}
    died_early = {f"t{i}": 1.0 for i in range(12)}
    with pytest.raises(SystemExit) as caught:
        paired(full, died_early)
    message = str(caught.value)
    assert "pairing is broken" in message
    assert "t12" in message, "the guard must name what is missing, not just refuse"
    assert "17 missing from arm B" in message


def test_the_refusal_is_symmetric():
    """Whichever arm died, the comparison is equally inadmissible. The bash arm died in
    2g and the PTC arm in earlier runs, so this cannot be one-sided."""
    a = {"x": 1.0, "y": 0.0}
    b = {"x": 1.0}
    for first, second in ((a, b), (b, a)):
        with pytest.raises(SystemExit):
            paired(first, second)


def test_no_shared_names_still_says_so_specifically():
    """A different message from the partial-arm one: the taskset is wrong, not the run."""
    with pytest.raises(SystemExit) as caught:
        paired({"a": 1.0}, {"b": 1.0})
    assert "same taskset" in str(caught.value)


def test_it_reproduces_run_2h_from_that_run_s_shape():
    """A regression lock on the published number. Run 2h: 14 paired tasks, bash won no
    discordant pair, PTC won two, twelve tied -> -14.3 pp at exact McNemar p=0.5000.
    `docs/results-untrained.md` reports these, so a change here is a change to a
    published claim and should fail loudly."""
    bash = {f"tie{i}": 1.0 for i in range(12)}
    ptc = dict(bash)
    bash["total-invoice"] = 0.0
    ptc["total-invoice"] = 1.0
    bash["total-receipt"] = 0.0
    ptc["total-receipt"] = 1.0

    got = paired(bash, ptc)
    assert got["n"] == 14
    assert round(got["delta"] * 100, 1) == -14.3
    assert (got["a_only"], got["b_only"], got["ties"]) == (0, 2, 12)
    assert round(got["p"], 4) == 0.5000
    assert round(got["mean_a"], 4) == 0.8571
    assert got["mean_b"] == 1.0


def test_a_unanimous_discordance_is_the_easiest_case_not_an_impossible_one():
    """The bug the 2h session found in this tool: `|delta|` can never exceed the
    discordance rate, so p is in [0.5, 1.0] and p == 1.0 is the EASIEST case to detect,
    not an undetectable one. Six unanimous pairs reach exact p=0.031."""
    bash = {f"loss{i}": 0.0 for i in range(6)}
    ptc = {f"loss{i}": 1.0 for i in range(6)}
    got = paired(bash, ptc)
    assert (got["a_only"], got["b_only"], got["ties"]) == (0, 6, 0)
    assert got["p"] < 0.05, "six unanimous discordant pairs are significant"


def _rows(arm: dict[str, tuple[float, bool, int]]) -> str:
    """A traces.jsonl in the shape the loader reads: score lives at
    traces[i].rewards.<c>.score, and `ok` is the only field that distinguishes an
    errored rollout from a genuine zero."""
    import json
    import tempfile
    lines = []
    for name, (score, ok, min_calls) in arm.items():
        traces = [{"rewards": {"correct": {"score": score, "weight": 1.0}}}] if ok else []
        lines.append(json.dumps({
            "ok": ok,
            "task": {"data": {"name": name, "min_calls": min_calls}},
            "traces": traces,
        }))
    path = tempfile.mktemp(suffix=".jsonl")
    Path(path).write_text("\n".join(lines) + "\n")
    return path


def test_a_void_rollout_voids_the_comparison_even_when_both_arms_have_the_task():
    """The hole this closes: a void rollout has no `rewards`, so it sums to 0.0 and is
    indistinguishable from a genuine wrong answer. Run 3b wrote all 29 names on both arms
    with 10 of bash's errored -- so the equal-set guard could not fire and the tool would
    have printed bash 14/29 vs PTC 20/29 as a real comparison, with ten crashes counted as
    failures. `compare.py` exits non-zero here; this tool used to report it."""
    a = _rows({"t1": (1.0, True, 1), "t2": (0.0, False, 40)})
    b = _rows({"t1": (1.0, True, 1), "t2": (1.0, True, 40)})
    ra, rb = rollouts(a), rollouts(b)
    assert set(ra) == set(rb), "equal key sets: this is the case the old guard missed"
    with pytest.raises(SystemExit) as caught:
        refuse_voids("bash", ra, "ptc", rb)
    message = str(caught.value)
    assert "void" in message
    assert "t2" in message, "the guard must name which task errored"
    assert "bash: 1 void" in message


def test_voids_on_either_arm_are_caught():
    for first, second in ((True, False), (False, True)):
        a = _rows({"t1": (1.0, first, 1)})
        b = _rows({"t1": (1.0, second, 1)})
        with pytest.raises(SystemExit):
            refuse_voids("a", rollouts(a), "b", rollouts(b))


def test_a_clean_run_is_not_refused():
    a = _rows({"t1": (1.0, True, 1), "t2": (0.0, True, 40)})
    b = _rows({"t1": (1.0, True, 1), "t2": (1.0, True, 40)})
    refuse_voids("a", rollouts(a), "b", rollouts(b))  # must not raise


def test_tiers_split_on_the_maximum_min_calls_not_a_hardcoded_40():
    """`len(RECORDS)` is 40 today. Deriving the full-scan tier from the data means a
    taskset built on a different record count still splits rather than silently
    reporting one tier."""
    for top, expected in ((40, ({"cheap"}, {"full"})), (7, ({"cheap"}, {"full"}))):
        r = {"full": {"score": 0.0, "ok": True, "min_calls": top},
             "cheap": {"score": 0.0, "ok": True, "min_calls": 1}}
        got = split_tiers(r)
        assert got["full-scan"] == {"full"}, top
        assert got["cheap"] == {"cheap"}, top


def test_run_2h_reports_the_effect_inside_the_tier_that_holds_it():
    """The published -14.3 pp is a marginal across a tie and an effect: on 2h's 14 tasks
    the cheap tier is +0.0 pp and the full-scan tier -33.3 pp. Locked here because A6
    pre-specifies the within-tier comparison as the one that decides, so a change to this
    split is a change to which claim the project can make."""
    bash = {f"c{i}": 1.0 for i in range(8)}          # cheap tier, tied
    ptc = dict(bash)
    for n in ("f0", "f1"):
        bash[n], ptc[n] = 0.0, 1.0                   # full-scan, PTC's two discordant wins
    for n in ("f2", "f3", "f4", "f5"):
        bash[n] = ptc[n] = 1.0
    meta = {n: {"score": 1.0, "ok": True, "min_calls": 1} for n in bash}
    for n in ("f0", "f1", "f2", "f3", "f4", "f5"):
        meta[n]["min_calls"] = 40

    marginal = paired(bash, ptc)
    assert round(marginal["delta"] * 100, 1) == -14.3

    tiers = split_tiers(meta)
    cheap = paired({n: bash[n] for n in tiers["cheap"]}, {n: ptc[n] for n in tiers["cheap"]})
    full = paired({n: bash[n] for n in tiers["full-scan"]},
                  {n: ptc[n] for n in tiers["full-scan"]})
    assert cheap["delta"] == 0.0, "the cheap tier is a tie; the marginal hides that"
    assert round(full["delta"] * 100, 1) == -33.3
    assert round((full["delta"] - cheap["delta"]) * 100, 1) == -33.3


# ------------------------------------------------------------- the statistics
#
# Every published claim in this project is a CI, a p-value or a power figure computed by
# these three functions, and this session already found one bug among them -- `p >= 1`
# called the unanimous-discordance case undetectable. Verified against independent
# computation rather than against themselves.

def _mcnemar_by_formula(b: int, c: int) -> float:
    """Exact two-sided binomial sign test, written out from the definition."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def test_mcnemar_matches_an_independent_computation():
    for b, c in ((0, 0), (0, 1), (1, 1), (0, 2), (2, 2), (1, 2), (0, 6), (3, 3),
                 (5, 6), (0, 29), (7, 13)):
        assert mcnemar_exact(b, c) == pytest.approx(_mcnemar_by_formula(b, c)), (b, c)


def test_mcnemar_is_symmetric_and_inside_the_unit_interval():
    """Both properties are load-bearing: `paired` decides which arm is which by the sign
    of b - c, so an asymmetric p would let arm order change the verdict."""
    for b in range(13):
        for c in range(13):
            p = mcnemar_exact(b, c)
            assert 0.0 <= p <= 1.0, (b, c, p)
            assert p == pytest.approx(mcnemar_exact(c, b)), (b, c)


def test_mcnemar_needs_six_unanimous_pairs_not_seven():
    """The boundary the old guard got wrong. Six unanimous discordant pairs give an exact
    two-sided p of 0.031; seven are unnecessary for significance."""
    assert mcnemar_exact(0, 6) == pytest.approx(0.03125)
    assert mcnemar_exact(0, 6) <= 0.05
    assert mcnemar_exact(0, 5) > 0.05


def power_at(n: int, delta: float, discordance: float, alpha: float = 0.05) -> float:
    """Power at a given n, recomputed from the definition rather than read from the
    function under test: draw d discordant pairs, reject when the minority count is at or
    below the largest count whose exact p clears alpha."""
    d = round(n * discordance)
    if d < 2:
        return 0.0
    p = 0.5 + delta / (2 * discordance)
    crit = -1
    for k in range(d // 2 + 1):
        if mcnemar_exact(k, d - k) <= alpha:
            crit = k
        else:
            break
    if crit < 0:
        return 0.0
    return sum(comb(d, i) * p ** (d - i) * (1 - p) ** i for i in range(crit + 1))


def test_power_returns_the_MINIMAL_n_that_reaches_the_target():
    """A power function that returns a number too small is the dangerous direction: it
    would size a real run underpowered and let the result be read as a null."""
    for delta, disc in ((0.1, 0.5), (0.2, 0.5), (0.3, 0.5), (0.1, 0.2)):
        n = power_pairs(delta, disc)
        assert n is not None
        assert power_at(n, delta, disc) >= 0.80, (delta, disc, n)
        assert power_at(n - 1, delta, disc) < 0.80, (
            f"n={n} is not minimal for delta={delta} disc={disc}")


def test_power_falls_as_the_effect_shrinks():
    need = [power_pairs(d, 0.5) for d in (0.05, 0.1, 0.15, 0.2, 0.3, 0.5)]
    assert need == sorted(need, reverse=True), need


def test_power_RISES_with_discordance_and_that_is_not_a_bug():
    """Counter-intuitive, so pinned before someone 'fixes' it. With `delta` held fixed, a
    higher discordance rate splits the same total signal across more coin-flips, so
    `p = 0.5 + delta / (2 * disc)` moves toward a half and the run needs MORE pairs, not
    fewer. Only when `delta == discordance` -- every discordant pair favouring one arm --
    is the effect unanimous and the cheapest to detect."""
    need = [power_pairs(0.1, d) for d in (0.1, 0.2, 0.3, 0.5, 0.8)]
    assert need == sorted(need), need
    assert power_pairs(0.5, 0.5) < power_pairs(0.1, 0.5)
    # The boundary is detectable, with variance small because the pairs are unanimous.
    assert power_pairs(0.25, 0.25) is not None
    assert power_pairs(0.5, 0.5) <= 12


def test_power_returns_none_only_for_inputs_that_cannot_occur():
    assert power_pairs(0.5, 0.2) is None, "delta cannot exceed the discordance rate"
    assert power_pairs(0.0, 0.5) is None
    assert power_pairs(-0.1, 0.5) is None
    assert power_pairs(0.1, 0.0) is None


def test_power_matches_a_simulation_of_the_test_it_claims_to_size():
    """The analytic route and a simulated one have to agree, because a wrong p formula
    would be self-consistent across every other test in this file and still size every
    run in the project wrongly."""
    delta, disc = 0.2, 0.5
    n = power_pairs(delta, disc)
    d = round(n * disc)
    p = 0.5 + delta / (2 * disc)
    rng = random.Random(0)
    trials = 4000
    rejected = 0
    for _ in range(trials):
        wins = sum(1 for _ in range(d) if rng.random() < p)
        if mcnemar_exact(wins, d - wins) <= 0.05:
            rejected += 1
    simulated = rejected / trials
    assert simulated == pytest.approx(0.80, abs=0.06), (
        f"simulated power {simulated:.3f} disagrees with the analytic sizing")
