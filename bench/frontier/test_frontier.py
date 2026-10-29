"""Tests for the frontier probe. Offline: the policy is a deterministic stand-in.

The probe's whole purpose is to stop a number being invented, so these tests check the
places where one could leak in: an empty frontier must refuse to emit a manifest, a void
task must not become a solve rate of 0, and the trainable band must be derived from the
ceiling rather than agreeing with a hardcoded pair by luck.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # noqa: E402

from bench import fixture  # noqa: E402
from bench.frontier.probe import (DEFAULT_DEAD_CEILING, DEFAULT_G,  # noqa: E402
                                  ProbeResult, dead_group_fraction, probe, render,
                                  trainable_band, write_manifest)
from bench.loader import load_bird  # noqa: E402
from bench.task import SqlTask  # noqa: E402


@pytest.fixture(scope="module")
def tasks(tmp_path_factory) -> list[SqlTask]:
    return load_bird(fixture.materialize(tmp_path_factory.mktemp("fr")))


def _cycler(pattern: dict[str, list[bool]]):
    """A stand-in policy: for each task, emit the gold query on the sampled attempts
    marked True and a deliberately wrong query otherwise. Lets a test dial any per-task
    solve rate exactly."""
    state: dict[str, int] = {}

    def generate(task: SqlTask) -> str:
        i = state.get(task.name, 0)
        state[task.name] = i + 1
        hits = pattern.get(task.name, [True] * 99)
        return task.gold_sql if hits[i % len(hits)] else "SELECT 'wrong' AS x"

    return generate


# --- the derivation --------------------------------------------------------------

def test_dead_group_fraction_is_maximal_at_both_ends():
    assert dead_group_fraction(0.0) == 1.0
    assert dead_group_fraction(1.0) == 1.0
    assert dead_group_fraction(0.5) == pytest.approx(0.125)
    assert dead_group_fraction(0.25) == pytest.approx(0.3203125)


def test_trainable_band_is_derived_not_stated():
    """Matches the TRAIN lane's stated (0.120, 0.880) at the defaults -- but by bisecting
    the ceiling, so changing G or the ceiling moves the band instead of silently
    disagreeing with a hardcoded pair."""
    lo, hi = trainable_band()
    assert dead_group_fraction(lo) == pytest.approx(DEFAULT_DEAD_CEILING, abs=1e-6)
    assert lo == pytest.approx(0.1200, abs=5e-4)
    assert hi == pytest.approx(0.8800, abs=5e-4)
    assert dead_group_fraction((lo + hi) / 2) < DEFAULT_DEAD_CEILING


def test_band_widens_with_more_generations():
    """More samples per group means fewer unanimous groups, so a wider band qualifies.
    A band that did not move with G would not be derived from it."""
    lo4, _ = trainable_band(g=4)
    lo8, _ = trainable_band(g=8)
    assert lo8 < lo4


def test_band_rejects_a_degenerate_ceiling():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="ceiling"):
            trainable_band(bad)


# --- measurement ------------------------------------------------------------------

def test_probe_measures_the_dialled_solve_rate(tasks):
    """2 of 4 sampled attempts succeed -> p = 0.5, for every task."""
    gen = _cycler({t.name: [True, False, True, False] for t in tasks})
    r = probe(tasks, gen, policy="stand-in", g=4)
    assert set(r.rates) == {t.name for t in tasks}
    assert all(p == 0.5 for p in r.rates.values())
    assert r.n_tasks == len(tasks)
    assert r.mean_dead_fraction == pytest.approx(0.125)


def test_probe_discards_saturated_and_uniformly_failing_tasks(tasks):
    """The §344 requirement, measured. A task solved every time and a task never solved
    both give zero-advantage groups and must not be retained."""
    always = tasks[0].name
    never = tasks[1].name
    gen = _cycler({always: [True], never: [False],
                   **{t.name: [True, False] for t in tasks[2:]}})
    r = probe(tasks, gen, policy="stand-in", g=4)
    assert r.rates[always] == 1.0 and r.rates[never] == 0.0
    assert always not in r.retained and never not in r.retained
    assert set(r.retained) == {t.name for t in tasks[2:]}
    assert r.retention == pytest.approx(len(tasks[2:]) / len(tasks))


def test_a_void_task_is_not_a_solve_rate_of_zero(tasks):
    """A defective gold scored 0 would push the task below the band and discard it as
    'too hard for the policy'. That is a lie about a broken task, and it is the same
    asymmetry `ptc/paired.py:refuse_voids` refuses."""
    broken = dataclasses.replace(tasks[0], gold_sql="SELECT FROM nowhere")
    probed = [broken] + list(tasks[1:])
    r = probe(probed, _cycler({t.name: [True, False] for t in probed}),
              policy="stand-in", g=4)
    assert broken.name in r.void
    assert broken.name not in r.rates
    assert broken.name not in r.retained
    assert r.n_candidates == len(probed) - 1


def test_probe_requires_a_group_big_enough_to_vary(tasks):
    with pytest.raises(ValueError, match="at least 2"):
        probe(tasks, _cycler({}), policy="stand-in", g=1)


def test_probe_applies_extraction(tasks):
    """Integration rule from `docs/bench-taskset.md` §3.5. A policy that fences its SQL
    must not read as uniformly failing -- that would shut the gate for the wrong reason."""
    def fenced(task: SqlTask) -> str:
        return f"```sql\n{task.gold_sql}\n```"
    r = probe(tasks, fenced, policy="stand-in", g=2)
    assert all(p == 1.0 for p in r.rates.values())


# --- lossless diagnostic reports --------------------------------------------------

@pytest.fixture
def mixed_probe(tasks) -> ProbeResult:
    measured = [dataclasses.replace(tasks[i], name=name) for i, name in enumerate(
        ('half/"quoted"', "never/δ", "always"))]
    broken = dataclasses.replace(tasks[0], name="void\nbad gold",
                                 gold_sql="SELECT FROM nowhere")
    return probe(measured + [broken],
                 _cycler({measured[0].name: [True, False],
                          measured[1].name: [False], measured[2].name: [True]}),
                 policy="offline/diagnostic-policy", g=4, dead_ceiling=0.55,
                 compare="multiset")


def test_probe_report_round_trips_all_existing_fields(mixed_probe):
    """Three measured rates, one void, one retained; identities survive JSON exactly."""
    r = mixed_probe
    assert r.rates == {'half/"quoted"': 0.5, "never/δ": 0.0, "always": 1.0}
    assert r.void == {"void\nbad gold": "gold_error"}
    assert r.retained == ['half/"quoted"']
    assert r.n_candidates == 3 and r.n_tasks == 1
    assert r.retention == 1 / 3
    loaded = json.loads(json.dumps(r.report()))
    assert loaded == dataclasses.asdict(r)
    restored = ProbeResult(**loaded)
    assert restored == r
    assert restored.retention == 1 / 3


def test_probe_report_distinguishes_ids_with_identical_aggregates(mixed_probe):
    r = mixed_probe
    renamed = dataclasses.replace(
        r, rates={f"other/{name}": rate for name, rate in r.rates.items()},
        retained=[f"other/{name}" for name in r.retained],
        void={f"other/{name}": reason for name, reason in r.void.items()})
    assert renamed.manifest("A8") == r.manifest("A8")
    assert json.dumps(renamed.report(), sort_keys=True) != json.dumps(
        r.report(), sort_keys=True)


def test_probe_rejects_duplicate_names_before_any_sampling(tasks):
    """A duplicate at the end must cause zero calls, not partial measurement."""
    calls = []

    def generate(task):
        calls.append(task.name)
        return task.gold_sql

    duplicate = dataclasses.replace(tasks[0], gold_sql="SELECT 'different gold'")
    with pytest.raises(ValueError, match="duplicate"):
        probe(list(tasks) + [duplicate], generate, policy="stand-in", g=4)
    assert calls == []


@pytest.mark.parametrize("empty", [False, True], ids=["retained", "empty"])
def test_write_probe_report_is_lossless_and_never_emits_manifest(
        mixed_probe, tmp_path, monkeypatch, empty):
    from bench.frontier.probe import MANIFEST_PATH, write_report

    r = dataclasses.replace(mixed_probe, retained=[]) if empty else mixed_probe

    def refuse_manifest(*args, **kwargs):
        pytest.fail("a diagnostic report must not call manifest()")

    monkeypatch.setattr(ProbeResult, "manifest", refuse_manifest)
    assert not MANIFEST_PATH.exists()
    target = tmp_path / "diagnostics" / "probe.json"
    assert write_report(r, target) == target
    assert json.loads(target.read_text()) == dataclasses.asdict(r)
    assert not MANIFEST_PATH.exists()


@pytest.mark.parametrize("alias", ["direct", "relative", "dotdot", "symlink"])
@pytest.mark.parametrize("existing", [False, True], ids=["absent", "existing"])
def test_write_probe_report_refuses_resolved_manifest_path(
        mixed_probe, tmp_path, monkeypatch, alias, existing):
    """Reject all four path spellings without creating or overwriting the gate file."""
    import importlib
    fp = importlib.import_module("bench.frontier.probe")
    from bench.frontier.probe import write_report

    canonical = tmp_path / "bench" / "frontier" / "manifest.json"
    canonical.parent.mkdir(parents=True)
    if existing:
        canonical.write_text("existing gate bytes\n")
    monkeypatch.setattr(fp, "MANIFEST_PATH", canonical)
    monkeypatch.chdir(tmp_path)
    target = canonical
    if alias == "relative":
        target = Path("bench/frontier/manifest.json")
    elif alias == "dotdot":
        child = canonical.parent / "child"
        child.mkdir()
        target = child / ".." / "manifest.json"
    elif alias == "symlink":
        target = tmp_path / "report.json"
        target.symlink_to(canonical)
    with pytest.raises(ValueError, match="manifest"):
        write_report(mixed_probe, target)
    if existing:
        assert canonical.read_text() == "existing gate bytes\n"
    else:
        assert not canonical.exists()


def test_write_probe_report_refuses_hardlink_manifest(
        mixed_probe, tmp_path, monkeypatch):
    import importlib
    fp = importlib.import_module("bench.frontier.probe")

    canonical = tmp_path / "manifest.json"
    canonical.write_text("existing gate bytes\n")
    target = tmp_path / "report.json"
    target.hardlink_to(canonical)
    monkeypatch.setattr(fp, "MANIFEST_PATH", canonical)

    with pytest.raises(ValueError, match="manifest"):
        fp.write_report(mixed_probe, target)
    assert canonical.read_text() == "existing gate bytes\n"
    assert target.read_text() == "existing gate bytes\n"


# --- the manifest -----------------------------------------------------------------

def test_manifest_carries_the_five_gate_keys(tasks):
    gen = _cycler({t.name: [True, False, True, False] for t in tasks})
    r = probe(tasks, gen, policy="unsloth/Qwen3-0.6B", g=4)
    m = r.manifest("A8")
    assert set(m) >= {"policy", "pre_registration_amendment", "n_tasks",
                      "solve_rate_min", "solve_rate_max"}
    assert m["policy"] == "unsloth/Qwen3-0.6B"
    assert m["pre_registration_amendment"] == "A8"
    assert isinstance(m["n_tasks"], int) and not isinstance(m["n_tasks"], bool)
    assert m["n_tasks"] > 0


def test_manifest_band_satisfies_the_gate_predicates(tasks):
    """The gate's own checks, re-run here against a measured manifest: strict (0,1) and
    the dead-group ceiling at both ends."""
    gen = _cycler({t.name: [True, False, True, False] for t in tasks})
    m = probe(tasks, gen, policy="p", g=4).manifest("A8")
    lo, hi = m["solve_rate_min"], m["solve_rate_max"]
    assert 0.0 < lo <= hi < 1.0
    assert dead_group_fraction(lo) <= DEFAULT_DEAD_CEILING
    assert dead_group_fraction(hi) <= DEFAULT_DEAD_CEILING


def test_an_empty_frontier_refuses_to_emit_a_manifest(tasks):
    """The most important test here. If nothing is trainable, that is a finding about the
    taskset -- writing a file anyway would open the gate on a measurement that found the
    opposite of what the gate requires."""
    gen = _cycler({t.name: [False] for t in tasks})     # never solved
    r = probe(tasks, gen, policy="p", g=4)
    assert r.retained == []
    with pytest.raises(ValueError, match="Refusing to emit"):
        r.manifest("A8")
    assert "NO task cleared the ceiling" in render(r)


def test_write_manifest_round_trips(tasks, tmp_path):
    gen = _cycler({t.name: [True, False, True, False] for t in tasks})
    r = probe(tasks, gen, policy="p", g=4)
    path = write_manifest(r, "A8", tmp_path / "frontier" / "manifest.json")
    loaded = json.loads(path.read_text())
    assert loaded["n_tasks"] == r.n_tasks
    assert loaded["measurement"]["g"] == 4
    assert loaded["measurement"]["n_candidates"] == r.n_candidates


def test_write_manifest_refuses_an_empty_frontier(tasks, tmp_path):
    r = probe(tasks, _cycler({t.name: [False] for t in tasks}), policy="p", g=4)
    target = tmp_path / "manifest.json"
    with pytest.raises(ValueError, match="Refusing to emit"):
        write_manifest(r, "A8", target)
    assert not target.exists()


def test_the_committed_manifest_is_absent():
    """The gate must stay shut. A manifest appearing in the repo without a measurement
    behind it is the failure this whole module exists to prevent, so its absence is
    asserted rather than assumed."""
    from bench.frontier.probe import MANIFEST_PATH
    assert not MANIFEST_PATH.exists(), (
        f"{MANIFEST_PATH} exists. If it was written by a real probe run, delete this "
        "test and record the measurement in docs/bench-taskset.md. If it was hand-"
        "written, it is a fabricated measurement and must be removed.")


def test_marginal_accuracy_cannot_substitute_for_the_band():
    """Three compositions with the SAME marginal accuracy and completely different
    trainability. This is why the ~25% EX estimate in `docs/bench-taskset.md` §2 cannot
    be written into the manifest in place of a probe."""
    compositions = {
        "homogeneous": [0.25] * 200,
        "mild spread": [0.10] * 67 + [0.25] * 66 + [0.40] * 67,
        "bimodal": [1.0] * 50 + [0.0] * 150,
    }
    marginals = {k: sum(v) / len(v) for k, v in compositions.items()}
    assert all(m == pytest.approx(0.25, abs=0.01) for m in marginals.values())
    live = {k: sum(1 for p in v if dead_group_fraction(p) <= DEFAULT_DEAD_CEILING)
            for k, v in compositions.items()}
    assert live["homogeneous"] == 200
    assert live["bimodal"] == 0
    assert live["mild spread"] < live["homogeneous"]


def test_render_reports_retention_not_just_the_band(tasks):
    """The band is conformant by construction once out-of-band tasks are discarded, so
    the summary has to lead with how many survived."""
    gen = _cycler({tasks[0].name: [True],
                   **{t.name: [True, False] for t in tasks[1:]}})
    text = render(probe(tasks, gen, policy="p", g=4))
    assert "retention" in text and "BY CONSTRUCTION" in text
