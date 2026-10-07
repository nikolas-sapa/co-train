"""The taskset's own suite. It attacks the grader and the data, not the model.

A benchmark whose answers were never checked is a way to be confidently wrong at
scale: a wrong expected value silently converts a correct arm into a losing one, and
nothing in the run would show it. `docs/pre-registration.md` §5 requires the verifier be
tested both ways -- reference solution passes, planted mutant fails -- before it scores
anything, so that is what these do.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

verifiers = pytest.importorskip("verifiers")

import verifiers.v1 as vf  # noqa: E402

from ledger.servers.store import RECORDS, LedgerToolset  # noqa: E402
from ledger.taskset import (  # noqa: E402
    LedgerTaskConfig,
    LedgerTaskData,
    LedgerTask,
    _chain_end,
    _tasks,
)


def _tools():
    """The toolset called directly. `test_harness.py` already covers the MCP transport;
    here the question is whether the tools return the right thing."""
    return LedgerToolset(vf.ToolsetConfig())


def _score(answer: str, reply: str) -> float:
    task = LedgerTask(
        LedgerTaskData(idx=0, name="t", prompt="p", answer=answer, min_calls=1),
        LedgerTaskConfig(),
    )

    class FakeTrace:
        last_reply = reply

    return asyncio.run(task.correct(FakeTrace()))


# ------------------------------------------------------------------ the data

def test_the_answers_are_computed_from_the_data_not_transcribed():
    """Recomputes every expected value by a route independent of `_tasks`. A
    hand-typed expected value is a second implementation that can disagree with the
    first, and the disagreement would read as the model being wrong."""
    answers = {name: answer for name, _p, answer, _m in _tasks()}

    assert answers["lookup-r00"] == str(RECORDS["r00"]["amount"])
    assert answers["owner-r22"] == RECORDS["r22"]["owner"]

    totals = {}
    for record in RECORDS.values():
        totals[record["kind"]] = totals.get(record["kind"], 0) + record["amount"]
    for kind, total in totals.items():
        assert answers[f"total-{kind}"] == str(total)

    assert answers["count-invoice"] == str(
        sum(1 for r in RECORDS.values() if r["kind"] == "invoice"))

    per_owner: dict[str, int] = {}
    for record in RECORDS.values():
        per_owner[record["owner"]] = per_owner.get(record["owner"], 0) + record["amount"]
    assert answers["richest-owner"] == max(per_owner, key=lambda o: per_owner[o])

    assert answers["largest-record"] == max(
        RECORDS.values(), key=lambda r: (r["amount"], r["id"]))["id"]


def test_the_hard_answers_are_computed_from_the_data_not_transcribed():
    """Same contract as the test above, for the tier added 2026-10-07. Recomputed by a
    route independent of `_tasks` -- different expressions, not the same comprehension
    pasted twice -- because a wrong expected value on a hard task is the one defect
    that reads as the model failing to reason."""
    answers = {name: answer for name, _p, answer, _m in _tasks()}

    # walk then aggregate
    for start in ("r03", "r11"):
        walk, cur = [start], start
        while RECORDS[cur]["link"]:
            cur = RECORDS[cur]["link"]
            walk.append(cur)
        total = 0
        for rid in walk:
            total += RECORDS[rid]["amount"]
        assert answers[f"chainsum-{start}"] == str(total), start
    assert answers["chainend-owner-r11"] == RECORDS[_chain_end("r11")]["owner"]

    # rank, not extreme
    descending = sorted((r["amount"] for r in RECORDS.values()), reverse=True)
    assert answers["third-largest-amount"] == str(descending[2])
    assert descending[1] != descending[2], "a tie at rank 3 makes the answer ambiguous"

    kind_totals: dict[str, int] = {}
    for record in RECORDS.values():
        kind_totals[record["kind"]] = kind_totals.get(record["kind"], 0) + record["amount"]
    ranked_kinds = sorted(kind_totals, key=lambda k: kind_totals[k], reverse=True)
    assert answers["second-kind-total"] == ranked_kinds[1]

    # mean, not sum -- and the two must disagree or the task tests nothing
    sums: dict[str, int] = {}
    counts: dict[str, int] = {}
    for record in RECORDS.values():
        sums[record["owner"]] = sums.get(record["owner"], 0) + record["amount"]
        counts[record["owner"]] = counts.get(record["owner"], 0) + 1
    by_mean = max(sums, key=lambda o: sums[o] / counts[o])
    assert answers["owner-largest-mean"] == by_mean
    assert by_mean != max(sums, key=lambda o: sums[o]), (
        "richest by mean and by sum are the same owner, so the task no longer "
        "distinguishes a mean from a sum")

    mean = sum(r["amount"] for r in RECORDS.values()) / len(RECORDS)
    assert answers["above-mean-count"] == str(
        len([r for r in RECORDS.values() if r["amount"] > mean]))

    # set reasoning
    kinds_per_owner: dict[str, set[str]] = {}
    for record in RECORDS.values():
        kinds_per_owner.setdefault(record["owner"], set()).add(record["kind"])
    every_kind = {r["kind"] for r in RECORDS.values()}
    complete = sorted(o for o, ks in kinds_per_owner.items() if ks == every_kind)
    assert answers["owners-all-kinds"] == " ".join(complete)
    assert 0 < len(complete) < len(kinds_per_owner), (
        "every owner or no owner holds all kinds, so the answer is degenerate")
    assert answers["invoice-total-all-kind-owners"] == str(sum(
        r["amount"] for r in RECORDS.values()
        if r["owner"] in complete and r["kind"] == "invoice"))

    pointed_at = [r["link"] for r in RECORDS.values() if r["link"]]
    assert answers["isolated-total"] == str(sum(
        r["amount"] for r in RECORDS.values()
        if r["link"] is None and r["id"] not in pointed_at))

    for kind in every_kind:
        assert answers[f"kind-max-{kind}"] == str(
            max(r["amount"] for r in RECORDS.values() if r["kind"] == kind)), kind


def test_the_longest_chain_start_is_unambiguous():
    """A tie for longest chain makes the answer arbitrary, and the arm that picked the
    other one would be marked wrong for being right."""
    lengths: dict[str, int] = {}
    for rid in RECORDS:
        seen, cur, n = set(), rid, 1
        while RECORDS[cur]["link"] and cur not in seen:
            seen.add(cur)
            cur = RECORDS[cur]["link"]
            n += 1
        lengths[rid] = n
    ranked = sorted(lengths.values(), reverse=True)
    assert ranked[0] > ranked[1], "two records begin chains of equal longest length"
    answers = {name: answer for name, _p, answer, _m in _tasks()}
    assert lengths[answers["longest-chain-start"]] == ranked[0]


def test_the_hard_tier_needs_more_than_one_pass_over_the_data():
    """The point of this tier is that filter-and-sum is not enough. Each of these needs
    an intermediate result -- a rank, a mean, a walk, a set -- before the final one, and
    every one of them is reported at the full-scan cost so the cost co-primary stays
    readable against difficulty."""
    second_order = {
        "third-largest-amount", "second-kind-total", "owner-largest-mean",
        "above-mean-count", "owners-all-kinds", "invoice-total-all-kind-owners",
        "isolated-total", "longest-chain-start",
    }
    calls = {name: m for name, _p, _a, m in _tasks()}
    assert second_order <= set(calls), second_order - set(calls)
    for name in second_order:
        assert calls[name] == len(RECORDS), name


def test_the_chain_answers_are_terminal():
    """A chain answer that still has a link is a truncated walk, and a model that
    walked one step further would be marked wrong for being right."""
    for name, _p, answer, _m in _tasks():
        if name.startswith("chain-"):
            assert RECORDS[answer]["link"] is None, name


def test_chain_following_terminates_on_a_cycle():
    """The data has no cycle today. The walk is bounded anyway, because the failure
    mode of an unbounded walk is a hung grader rather than a wrong answer."""
    saved = RECORDS["r30"]["link"]
    RECORDS["r30"]["link"] = "r03"          # close r03 -> r14 -> r21 -> r30 -> r03
    try:
        assert _chain_end("r03") in RECORDS
    finally:
        RECORDS["r30"]["link"] = saved


def test_no_record_links_to_itself():
    for rid, record in RECORDS.items():
        assert record["link"] != rid


def test_the_richest_owner_is_unambiguous():
    """A tie would make two different replies both correct while the grader accepts
    one. The task would then be measuring which tie the model happened to pick."""
    per_owner: dict[str, int] = {}
    for record in RECORDS.values():
        per_owner[record["owner"]] = per_owner.get(record["owner"], 0) + record["amount"]
    ranked = sorted(per_owner.values(), reverse=True)
    assert ranked[0] != ranked[1]


def test_the_largest_record_is_unambiguous():
    amounts = sorted((r["amount"] for r in RECORDS.values()), reverse=True)
    assert amounts[0] != amounts[1]


def test_the_backlink_answer_is_the_complete_set():
    """`links_to` can return several ids, so the expected answer must be all of them
    in the order the grader compares. One id would mark a complete reply wrong."""
    answers = {name: answer for name, _p, answer, _m in _tasks()}
    expected = sorted(r["id"] for r in RECORDS.values() if r["link"] == "r30")
    assert answers["backlink-r30"] == " ".join(expected)


# ----------------------------------------------------------------- the tools

def test_every_tool_returns_parseable_json():
    """Defect 5: a PTC program has no `import json`, no `.split` and no `ord`, so the
    only shape it can read is one the bridge can decode for it. Prose or a
    space-separated list leaves this arm unable to use a tool the bash arm reads fine."""
    tools = _tools()
    for text in (tools.ids(), tools.get("r00"), tools.get("r99"),
                 tools.links_to("r30"), tools.links_to("r99")):
        json.loads(text)  # raises if a return ever goes back to prose


def test_the_tools_answer_correctly():
    tools = _tools()
    assert json.loads(tools.get("r00")) == RECORDS["r00"]
    assert json.loads(tools.ids()) == sorted(RECORDS)
    assert json.loads(tools.links_to("r30")) == ["r21"]


def test_the_tools_are_case_and_whitespace_tolerant():
    """A model will send ` R00 `. Failing on that measures typing, not capability."""
    tools = _tools()
    assert tools.get("  R00 ") == tools.get("r00")
    assert tools.links_to(" R30\n") == tools.links_to("r30")


def test_a_missing_record_says_so_instead_of_raising():
    """The reply is data the model reads and can act on. An exception would end the
    program instead, which measures the runtime rather than the model.

    JSON `null` and `[]` rather than the prose "no such record"/"none" they used to be:
    defect 5 made every return JSON so a PTC program can parse one, and a sentence is
    the one shape it still could not read."""
    assert json.loads(_tools().get("r99")) is None
    assert json.loads(_tools().links_to("r99")) == []


def test_no_tool_answers_a_task_in_one_call():
    """The catalog must not do the task. A `ledger_total(kind)` tool would collapse
    every aggregation task into one call and the suite would measure nothing about
    action channels."""
    assert {name for name in dir(_tools()) if not name.startswith("_")} >= {
        "ids", "get", "links_to"}
    assert not [n for n in dir(_tools())
                if n in ("total", "sum", "count", "aggregate", "richest", "largest")]


# ---------------------------------------------------------------- the grader

def test_the_grader_accepts_the_reference_answer():
    assert _score("8971", "here you go <answer>8971</answer>") == 1.0


@pytest.mark.parametrize("reply, why", [
    ("<answer>8970</answer>", "off by one"),
    ("<answer></answer>", "empty"),
    ("the answer is 8971", "untagged"),
    ("<answer>8971", "unclosed"),
    ("", "no reply at all"),
])
def test_the_grader_rejects_planted_mutants(reply, why):
    """Every one of these is a way a wrong reply could have been scored 1.0 by a
    looser grader. Required by pre-reg §5: a check that has never gone red is not
    evidence."""
    assert _score("8971", reply) == 0.0, why


def test_the_grader_does_not_search_the_whole_reply():
    """The trap this grader exists to avoid. A substring check would score 1.0 for a
    reply that dumped every record, because the right answer is somewhere inside it."""
    dump = " ".join(str(r["amount"]) for r in RECORDS.values())
    assert _score("8971", f"<answer>{dump}</answer>") == 0.0
    assert _score("8971", f"{dump} <answer>0</answer>") == 0.0


def test_the_grader_normalises_case_and_spacing_only():
    assert _score("ferrari", "<answer> FERRARI </answer>") == 1.0
    assert _score("r21 r30", "<answer>r21   r30</answer>") == 1.0
    assert _score("r21 r30", "<answer>r30 r21</answer>") == 0.0


def test_the_grader_survives_a_missing_reply():
    """`trace.last_reply` is None when the arm produced nothing -- a crashed program,
    an exhausted turn budget. That must score 0.0, not raise inside the grader and
    take the whole rollout's record with it."""
    class NoReply:
        last_reply = None

    task = LedgerTask(
        LedgerTaskData(idx=0, name="t", prompt="p", answer="x", min_calls=1),
        LedgerTaskConfig(),
    )
    assert asyncio.run(task.correct(NoReply())) == 0.0


# ------------------------------------------------------------- the suite shape

def test_the_suite_spans_three_difficulty_tiers():
    """One-call tasks alone cannot show a gap: both arms saturate, which is exactly
    what `compare.py canned` measured on `glossary`. Many-call tasks are where a
    program-over-catalog arm could win if it wins anywhere."""
    tiers = sorted({m for _n, _p, _a, m in _tasks()})
    assert tiers[0] == 1
    assert tiers[-1] == len(RECORDS)
    assert len(tiers) >= 3


def test_task_names_are_unique():
    names = [name for name, _p, _a, _m in _tasks()]
    assert len(names) == len(set(names))


def test_every_prompt_asks_for_the_answer_tags():
    """The grader requires them, so a prompt that omits them grades the model on
    guessing the format."""
    for name, prompt, _a, _m in _tasks():
        assert "<answer></answer>" in prompt, name


def test_the_dataset_is_committed_not_generated_at_load():
    """A taskset whose answers change with a library version is not a benchmark. The
    records are read from a committed file; nothing regenerates them."""
    path = Path(__file__).parent / "servers" / "records.json"
    assert json.loads(path.read_text()) == RECORDS


# ------------------------------------------------------ the server subprocess

def test_the_tool_server_starts_as_its_own_process():
    """The regression this exists for. Verifiers launches each tool server as
    `python -m ledger.servers.store` from the runtime's workdir, so a parent's
    `sys.path.insert` does not reach it: the server died with `No module named
    'ledger'` and the whole run HUNG until the port-file timeout rather than failing
    loudly. Every in-process test above stayed green throughout.

    `glossary` never hits this because it is installed in site-packages. Asserting on
    the real subprocess is the only way to see it — a mock of `serve` would have
    reproduced the green.
    """
    from ledger import on_pythonpath
    from verifiers.v1.harnesses.utils.mcp import call_mcp, connect_mcp
    from verifiers.v1.mcp import serve

    on_pythonpath()

    async def go():
        from contextlib import AsyncExitStack

        async with serve(LedgerToolset(vf.ToolsetConfig())) as url:
            async with AsyncExitStack() as stack:
                _schemas, dispatch, servers = await connect_mcp(
                    {"mcpServers": {"ledger": {"url": url}}}, stack)
                got = await call_mcp(servers, dispatch, "ledger_get", {"id": "r00"})
                return sorted(dispatch), got

    names, got = asyncio.run(go())
    assert names == ["ledger_get", "ledger_ids", "ledger_links_to"]
    assert str(RECORDS["r00"]["amount"]) in str(got)


def test_on_pythonpath_sets_the_variable_a_subprocess_reads():
    """`sys.path` is the in-process half and `PYTHONPATH` is the half that crosses a
    process boundary. Only the second one fixed the hang, so it is the one pinned."""
    import os

    from ledger import REPO_ROOT, on_pythonpath

    saved = os.environ.get("PYTHONPATH")
    try:
        os.environ.pop("PYTHONPATH", None)
        on_pythonpath()
        assert REPO_ROOT in os.environ["PYTHONPATH"].split(os.pathsep)
        # Idempotent: repeated calls must not grow the variable without bound.
        on_pythonpath()
        assert os.environ["PYTHONPATH"].split(os.pathsep).count(REPO_ROOT) == 1
    finally:
        if saved is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = saved
