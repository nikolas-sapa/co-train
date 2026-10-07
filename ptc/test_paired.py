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

from ptc.paired import paired  # noqa: E402


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
