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

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.sql_arms import (  # noqa: E402
    BASH_CHANNEL,
    CAPABILITIES,
    DECLARED_ASYMMETRIES,
    PTC_V1,
    ASYMMETRY_REASONS,
    PTC_CHANNEL,
    SECOND_HARNESS_REQUIREMENTS,
    SQL_TOOL,
    UNREACHABLE_IN_SANDBOX,
    ArmPair,
    Budget,
    TaskView,
    build_probe_db,
    build_sql_arms,
    install_wrapper,
    prompt_for,
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


def _observe(cap, rig, backend=PTC_V1):
    """Both arms' observations for one capability, each through its own channel.

    Routed through `backend.run_bash`/`backend.run_ptc` rather than the module-level
    functions. `SECOND_HARNESS_REQUIREMENTS` entry 6 promises that a second
    implementation inherits this whole guard, and while this helper called the
    module-level functions directly that promise was a manual obligation: every probe
    exercised `PTC_V1` no matter which backend was passed.
    """
    db, bindir = rig
    view = _view(db)
    bash = backend.run_bash(cap.bash, view, cap.max_rows, bindir)
    ptc = backend.run_ptc(cap.ptc, view, cap.max_rows)
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
        evidence = ""
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
    # `pair.budget is pair.budget` was here and cannot fail -- an identity check
    # against itself. What matters is that there is ONE budget on the pair rather than
    # a per-arm field, so assert the shape that would have to change to break it.
    assert not any(f.name.startswith(("bash_budget", "ptc_budget"))
                   for f in dataclasses.fields(pair)), dataclasses.fields(pair)
    assert pair.budget.max_turns > 0 and pair.budget.max_retries >= 0
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


# ------------------------------------------------------------------------------
# The four clauses that `ptc/sql_arms.py`'s docstrings claimed were tested and were
# not. Found 2026-10-13 by the lane writing `docs/harness-parity.md` against the
# code. A docstring asserting a guard is the thing this file exists to prevent, and
# one of the three even said so -- "prose asserting otherwise is what let it ship."
# ------------------------------------------------------------------------------


def test_the_two_prompts_differ_only_by_the_channel_paragraph(rig):
    """Contract clause 1, and the defect-5 confound.

    `SHARED_PROMPT`'s docstring claimed this test rendered both prompts, removed the
    two channel strings and failed unless the remainders were byte-identical. It did
    not exist: `test_both_prompts_carry_the_same_schema` only checked that schema and
    question appear as substrings, so body text present in one arm's prompt and absent
    from the other passed green. An arm told more about its own channel, its own cap or
    the task is exactly the confound run 1 turned out to be.
    """
    db, _ = rig
    view = _view(db)
    bash = prompt_for(view, "bash", max_rows=200)
    ptc = prompt_for(view, "ptc", max_rows=200)

    assert BASH_CHANNEL.format(tool=SQL_TOOL, max_rows=200) in bash or "sqlite3" in bash
    stripped_bash = bash.replace(
        BASH_CHANNEL.format(tool=SQL_TOOL, max_rows=200), "")
    stripped_ptc = ptc.replace(
        PTC_CHANNEL.format(tool=SQL_TOOL, max_rows=200), "")

    assert stripped_bash == stripped_ptc, (
        "the prompts differ outside the channel paragraph\n"
        f"  bash-only: {set(stripped_bash.split()) - set(stripped_ptc.split())}\n"
        f"  ptc-only:  {set(stripped_ptc.split()) - set(stripped_bash.split())}"
    )


@pytest.mark.parametrize("asym", [a for a in DECLARED_ASYMMETRIES if a.probe],
                         ids=lambda a: a.name)
def test_every_declared_asymmetry_still_exists(asym, rig):
    """`Asymmetry.probe`/`expect` were inert data -- never run by anything.

    Its own docstring says why that matters: "a declared asymmetry whose limit quietly
    went away leaves docs/harness-parity.md describing a sandbox that no longer exists,
    and a declared asymmetry nobody probed is indistinguishable from a guess."
    """
    db, _ = rig
    result = run_ptc_program(asym.probe, db, max_rows=200)

    if asym.expect == "rejected":
        assert result.rejected, (
            f"{asym.name} is declared unreachable in the sandbox, but the probe ran. "
            "Either the sandbox widened and this is no longer an asymmetry, or the "
            "probe stopped probing it."
        )
    elif asym.expect == "partial_loss":
        assert "seen-before-the-failure" not in result.observation or result.rejected, (
            f"{asym.name}: output printed before the failure survived, so the declared "
            "partial-output loss is not happening"
        )
    else:
        pytest.fail(f"unhandled expect {asym.expect!r} on {asym.name}")


def test_declared_asymmetries_cover_every_sandbox_limit():
    """`DECLARED_ASYMMETRIES`'s docstring claimed this was asserted. It was not --
    `UNREACHABLE_IN_SANDBOX` was not even imported here.

    A sandbox limit declared in `sql_runtime` with no asymmetry entry is a gap nobody
    measured, which is how five of run 1's nine harness faults stayed invisible.
    """
    declared = {a.name for a in DECLARED_ASYMMETRIES}
    missing = set(UNREACHABLE_IN_SANDBOX) - declared
    assert not missing, (
        f"sandbox limits with no declared asymmetry: {sorted(missing)}. Add an entry "
        "with a probe, or remove the limit."
    )


def test_every_declared_asymmetry_has_a_retrievable_reason():
    """`Asymmetry.reason` was never accessed, so a name absent from both reason dicts
    failed at render time rather than test time -- i.e. when someone was reading the
    document, not when they broke it."""
    for a in DECLARED_ASYMMETRIES:
        reason = UNREACHABLE_IN_SANDBOX.get(a.name) or ASYMMETRY_REASONS.get(a.name)
        assert reason and reason.strip(), (
            f"{a.name} has no reason in UNREACHABLE_IN_SANDBOX or ASYMMETRY_REASONS"
        )


def test_the_capability_guard_runs_against_a_second_backend(rig):
    """`SECOND_HARNESS_REQUIREMENTS` entry 6 promises a second implementation inherits
    this guard. Until `_observe` took a backend, every probe exercised `PTC_V1`
    whichever backend was passed, so that promise was a manual obligation.

    Also exercises the stub's `model_tools(arm)` for real rather than asserting
    `callable()`, which proves object acceptance and not conformance.
    """
    calls: list[str] = []

    class _Recording:
        name = "recording-v0"

        def arm_ids(self):
            return PTC_V1.arm_ids()

        def model_tools(self, arm):
            calls.append(f"model_tools:{arm}")
            return PTC_V1.model_tools(arm)

        def catalog(self, *a, **k):
            return PTC_V1.catalog(*a, **k)

        def run_bash(self, command, view, max_rows, bindir):
            calls.append("run_bash")
            return PTC_V1.run_bash(command, view, max_rows, bindir)

        def run_ptc(self, program, view, max_rows):
            calls.append("run_ptc")
            return PTC_V1.run_ptc(program, view, max_rows)

    backend = _Recording()
    cap = next(c for c in CAPABILITIES if c.name == "run_query")
    bash_obs, ptc_obs = _observe(cap, rig, backend=backend)

    assert "run_bash" in calls and "run_ptc" in calls, calls
    assert _reaches(bash_obs, cap) and _reaches(ptc_obs, cap)
    assert len(backend.model_tools("ptc")) == 1
    assert "model_tools:ptc" in calls
    assert len(SECOND_HARNESS_REQUIREMENTS) >= 5
