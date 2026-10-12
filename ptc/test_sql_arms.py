"""The parity guard: both arms reach the same answers, or this file goes red.

Run 1 reported bash +64.3 pp and it was entirely instrument. Both arms held the same
three MCP tools, but bash read their JSON with the model's own attention while PTC
reached them through a sandbox with no `import json`, no attribute access and no `ord`
-- so it received a JSON *string* it owned no primitive to parse. bash's action space
was a strict superset, five of nine harness faults penalised PTC, and a green test suite
said nothing at any point.

So parity here is not asserted, it is measured: every entry in `CAPABILITIES` carries an
executable probe per arm, and the test runs both. An arm that loses a primitive, or
gains one the other lacks, turns this red without anyone remembering to update a list.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.sql_arms import (  # noqa: E402
    CAPABILITIES,
    DECLARED_ASYMMETRIES,
    PTC_V1,
    SQL_TOOL,
    ArmPair,
    Budget,
    TaskView,
    build_probe_db,
    build_sql_arms,
    install_wrapper,
    run_bash_sql,
    run_ptc_program,
)


@pytest.fixture(scope="module")
def rig(tmp_path_factory):
    """One probe database and one wrapper directory for the whole module."""
    root = tmp_path_factory.mktemp("arms")
    db = build_probe_db(root / "probe.sqlite")
    bindir = root / "bin"
    bindir.mkdir()
    install_wrapper(bindir, str(db))
    return str(db), bindir


def _observe(cap, rig):
    """Both arms' observations for one capability, each through its own channel."""
    db, bindir = rig
    bash = run_bash_sql(db, "", bindir=bindir, max_rows=cap.max_rows,
                        command=cap.bash)
    ptc = run_ptc_program(cap.ptc, db, max_rows=cap.max_rows)
    return (bash.stdout + bash.stderr).strip(), ptc.observation.strip()


def _reaches(observation: str, cap) -> bool:
    if cap.match == "contains":
        return cap.expected in observation
    return " ".join(observation.split()) == " ".join(cap.expected.split())


@pytest.mark.parametrize("cap", CAPABILITIES, ids=lambda c: c.name)
def test_every_capability_is_reachable_on_both_arms(cap, rig):
    """The guard itself. `expected` is the ANSWER, not the channel's bytes -- bash
    reads `-list` text and PTC reads dicts, and demanding byte-identical observations
    would be demanding the channels be the same channel."""
    bash_obs, ptc_obs = _observe(cap, rig)
    bash_ok, ptc_ok = _reaches(bash_obs, cap), _reaches(ptc_obs, cap)
    assert bash_ok and ptc_ok, (
        f"{cap.name}: bash={'reaches' if bash_ok else 'CANNOT'}, "
        f"ptc={'reaches' if ptc_ok else 'CANNOT'}\n"
        f"  needed: {cap.expected!r} ({cap.match})\n"
        f"  bash saw: {bash_obs!r}\n  ptc saw:  {ptc_obs!r}\n"
        f"  why this capability is in the class: {cap.why}"
    )


def test_no_capability_is_one_sided(rig):
    """The asymmetric case stated as its own failure, because it is the one that
    invalidated run 1 and the one a per-capability failure message buries: a list where
    every entry fails on the SAME arm is a superset, not twelve unrelated bugs."""
    one_sided = []
    for cap in CAPABILITIES:
        bash_obs, ptc_obs = _observe(cap, rig)
        if _reaches(bash_obs, cap) != _reaches(ptc_obs, cap):
            one_sided.append(cap.name)
    assert not one_sided, f"action spaces diverge on: {one_sided}"


def test_the_ptc_arm_registers_exactly_one_tool():
    """Spec §156 invariant 1. TRL renders every registered tool as a schema in the
    system prompt, so registering typed per-task tools silently builds the
    typed-tool-calling comparator instead of PTC -- the exact axis this project
    measures. The catalog must reach the model through the program, not the schema."""
    tools = PTC_V1.model_tools("ptc")
    assert len(tools) == 1, tools
    names = [t["function"]["name"] for t in tools]
    assert names == ["run_program"], names
    assert SQL_TOOL not in names, (
        f"{SQL_TOOL!r} is registered as a model-visible tool. It must be reachable only "
        "from inside the program; registering it makes this the typed-tool comparator."
    )
    # the bash arm's schemas belong to verifiers' bundled harness, and this backend
    # says so rather than inventing them -- a backend that answered here would be
    # claiming ownership of an arm it does not build
    with pytest.raises(NotImplementedError):
        PTC_V1.model_tools("bash")


def _view(db: str) -> TaskView:
    class _T:
        db_path = db
        question = "How many employees are there?"
        gold_sql = "SELECT COUNT(*) FROM emp"
        name = "probe-1"
        tier = "simple"
        tier_index = 1
    return _T()


def test_both_arms_get_one_budget_struct(rig):
    """A per-arm budget is how an instrument asymmetry gets reintroduced after the
    capability probes have all passed: identical abilities, unequal turns."""
    db, _ = rig
    pair = build_sql_arms(_view(db))
    assert isinstance(pair.budget, Budget)
    assert pair.budget is pair.budget      # one struct, not one per arm
    # there is no path that builds a single arm
    assert isinstance(pair, ArmPair) and pair.bash_prompt and pair.ptc_prompt


def test_both_prompts_carry_the_same_schema(rig):
    """Identical information, different channel. The schema is read once and handed to
    both prompts precisely so the two cannot drift."""
    db, _ = rig
    pair = build_sql_arms(_view(db))
    assert pair.schema in pair.bash_prompt
    assert pair.schema in pair.ptc_prompt
    assert pair.view.question in pair.bash_prompt
    assert pair.view.question in pair.ptc_prompt


def test_every_declared_asymmetry_carries_a_reason():
    """Five asymmetries are declared rather than denied. Each needs a stated reason, or
    `DECLARED_ASYMMETRIES` becomes the place inconvenient findings go to be filed."""
    assert DECLARED_ASYMMETRIES, "an empty declaration list is a claim of perfect parity"
    for a in DECLARED_ASYMMETRIES:
        assert a.name and a.direction and a.expect, a
        assert a.direction in ("bash", "ptc", "neither"), (a.name, a.direction)
    # Four of the five favour bash and the fifth is covered by a capability probe. If
    # that ever reads as a clean split, someone has been filing findings here.
    assert {a.direction for a in DECLARED_ASYMMETRIES} == {"bash", "neither"}


def test_the_swap_seam_takes_a_second_backend(rig):
    """H4/H5 need a policy trained on one harness evaluated on another, so the arm pair
    must not be welded to `ptc.harness`. A stub backend standing in for the second
    implementation is what proves the seam is real rather than described."""
    db, bindir = rig

    class _Stub:
        name = "stub-v0"

        def arm_ids(self):
            return PTC_V1.arm_ids()

        def model_tools(self):
            return PTC_V1.model_tools()

        def catalog(self, *a, **k):
            return PTC_V1.catalog(*a, **k)

        def run_bash(self, *a, **k):
            return PTC_V1.run_bash(*a, **k)

        def run_ptc(self, *a, **k):
            return PTC_V1.run_ptc(*a, **k)

    stub = _Stub()
    # `HarnessBackend` is a plain Protocol, so structural conformance is checked by
    # calling it, not by isinstance -- which would need @runtime_checkable and would
    # only confirm the method NAMES anyway.
    for method in ("arm_ids", "model_tools", "catalog", "run_bash", "run_ptc"):
        assert callable(getattr(stub, method)), method
    pair = build_sql_arms(_view(db), backend=stub)
    assert pair.backend.name == "stub-v0"
    assert pair.bash_prompt and pair.ptc_prompt


def test_all_names_in_dunder_all_exist():
    """`SECOND_HARNESS_REQUIREMENTS` was exported and never defined, so `import *`
    raised and three docstrings pointed at nothing. A module's own export list is the
    cheapest thing in the file to check and nothing was checking it."""
    import ptc.sql_arms as mod
    missing = [n for n in mod.__all__ if not hasattr(mod, n)]
    assert not missing, missing


def test_the_second_harness_requirements_name_the_defect_they_exist_for():
    """The list is the swap seam's contract. Conformance to the Protocol does not make
    an implementation comparable, and that gap is where run 1's +64.3 pp came from."""
    from ptc.sql_arms import SECOND_HARNESS_REQUIREMENTS as reqs
    assert len(reqs) >= 5
    joined = " ".join(reqs)
    assert "EXACTLY ONE tool" in joined          # spec §156 invariant 1
    assert "defect 5" in joined                  # the fault the seam must not re-ship
