"""`audit.py` classifies tool calls to decide A6's N3, so its classifier is the thing
being tested -- not the trace format, which `test_harness.py` covers.

N3's whole content is "the bash arm does not compute on full-scan tasks even though a
shell is exactly what the task needs". A classifier that counted `ls` as computing would
manufacture the opposite finding, and one that missed `sum(...)` would manufacture N3
itself. Both directions are pinned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.audit import ARITHMETIC, audit_rollout, calls_of, final_answer  # noqa: E402


def _rollout(name: str, min_calls: int, calls: list[tuple[str, str]],
             answer: str = "", score: float = 1.0, ok: bool = True) -> dict:
    nodes = []
    for tool_name, args in calls:
        nodes.append({"message": {"role": "assistant", "content": None,
                                  "tool_calls": [{"type": "function", "name": tool_name,
                                                  "arguments": args}]}})
    if answer:
        nodes.append({"message": {"role": "assistant", "content": answer}})
    return {
        "ok": ok,
        "task": {"data": {"name": name, "min_calls": min_calls}},
        # A genuinely void rollout has NO rewards -- that is what makes it
        # indistinguishable from a 0.0 score in a rewards-only reading.
        "traces": [{"rewards": ({"correct": {"score": score, "weight": 1.0}}
                                if ok else {}),
                    "nodes": nodes}],
    }


def test_calls_are_read_in_order_with_their_arguments():
    r = _rollout("t", 1, [("ledger_ids", "{}"), ("ledger_get", '{"id": "r00"}'),
                          ("bash", 'echo hi')])
    got = calls_of(r)
    assert [c["name"] for c in got] == ["ledger_ids", "ledger_get", "bash"]
    assert got[1]["arguments"] == '{"id": "r00"}'


def test_the_final_answer_is_the_last_assistant_message_with_content():
    r = _rollout("t", 1, [("bash", "ls")], answer="<answer>8971</answer>")
    assert final_answer(r) == "<answer>8971</answer>"


def test_computing_and_merely_touching_a_shell_are_distinguished():
    """The distinction N3 turns on. `sort`/`wc`/`head` retrieve or print; they do not
    compute, and counting them would make any arm that lists files look like it
    aggregates."""
    computing = ["sum(x)", "awk '{s+=$1}'", "python3 -c 'print(1+1)'",
                 "jq '[.[].amount] | add'", "echo $((2+3))"]
    retrieving = ["ls", "cat records.json | sort", "wc -l", "head -5", "grep r00"]
    for cmd in computing:
        assert ARITHMETIC.search(cmd), f"should count as computing: {cmd}"
    for cmd in retrieving:
        assert not ARITHMETIC.search(cmd), f"should NOT count as computing: {cmd}"


def test_shell_share_is_over_all_calls_not_just_shell_calls():
    r = _rollout("t", 40, [("ledger_get", "{}")] * 8 + [("bash", "ls")] * 2)
    a = audit_rollout(r)
    assert a["shell_calls"] == 2
    assert a["catalog_calls"] == 8
    assert a["n_calls"] == 10
    assert a["shell_share"] == 0.2


def test_arithmetic_rollouts_count_a_rollout_once_however_many_sums_it_runs():
    many = _rollout("t", 40, [("bash", "sum: 1+2"), ("bash", "sum: 3+4")])
    none = _rollout("t", 40, [("bash", "ls"), ("bash", "cat x")])
    assert audit_rollout(many)["arithmetic_calls"] == 2
    assert audit_rollout(none)["arithmetic_calls"] == 0


def test_the_tier_comes_from_min_calls_and_a_void_rollout_is_flagged():
    assert audit_rollout(_rollout("a", 40, []))["tier"] == "full-scan"
    assert audit_rollout(_rollout("b", 2, []))["tier"] == "cheap"
    void = audit_rollout(_rollout("c", 40, [], ok=False))
    assert void["ok"] is False and void["score"] == 0.0
    assert void["shell_share"] == 0.0, "a void rollout has no calls to divide by"


def test_it_reads_run_2h_s_full_scan_tier_as_n3_holds():
    """The regression lock on the live result this tool was written for: on 2h the bash
    arm's full-scan shell share is 0.0227 and one of its six rollouts computes. If a
    classifier change moves this, it moves a pre-registered claim."""
    assert not ARITHMETIC.search("ls"), "retrieval must stay out of the numerator"
    r = _rollout("t", 40, [("ledger_get", "{}")] * 43 + [("bash", "ls")])
    assert audit_rollout(r)["shell_share"] == pytest.approx(1 / 44, abs=1e-4)
