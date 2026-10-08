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

from ptc.paired import paired, refuse_voids, rollouts, split_tiers  # noqa: E402


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
