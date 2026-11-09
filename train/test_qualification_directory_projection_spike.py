"""V327 SOURCE ONLY, UNRUN: six new cases, no production repair.

Parent stages the exact owned RED/GREEN source copy as
train/_qualification_directory_projection_spike.py, this test as
train/test_qualification_directory_projection_spike.py.
Only GREEN measurements screen the candidate. Test PASS is NOT speed approval.
Actual tiny A/C validation is reused; lifecycle observations remain synthetic.
"""
import json
import os
from pathlib import Path
from statistics import median
import stat
import time
from types import SimpleNamespace

import pytest

from train import test_qualification_lease_performance as perf
from train import _qualification_directory_projection_spike as candidate

api = perf.api
case, owner = perf.case, perf.owner
prohibit_real_effects = perf.prohibit_real_effects

# Keep any UNKNOWN experiment-owned generations reachable. Never retry a close.
_RETAINED_SPIKE_REGISTRIES = []


def _projection(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _observed_stat(info):
    # Complete forwarded tuple plus platform stat extensions. Trace only, never
    # the timed path, and never a substitute for the actual observed result.
    extensions = (
        "st_atime_ns", "st_mtime_ns", "st_ctime_ns", "st_blocks", "st_blksize",
        "st_flags", "st_gen", "st_birthtime", "st_birthtime_ns", "st_rdev",
    )
    return (tuple(info), tuple((name, getattr(info, name, None)) for name in extensions))


def _forwarded_traces(anchor, baseline_check, candidate_check, baseline_directory,
                      candidate_directory, monkeypatch):
    assert candidate.os is api.os is os, "shared OS functions must be wrapped only once"
    expected_calls = []
    for parent, name, record, pin, private in anchor.pins:
        expected_calls.append((pin, private))
        if parent is not None:
            expected_calls.append((pin, private))
    assert len(anchor.pins) == 9 and len(expected_calls) == 17
    state = dict(events=None, index=0, returns=None)
    real_fstat, real_stat, real_getuid = os.fstat, os.stat, os.getuid
    baseline_require, candidate_require = api.require, candidate.require

    def fstat(*args, **kwargs):
        actual = real_fstat(*args, **kwargs)
        if state["events"] is not None:
            state["events"].append(("fstat", args, tuple(sorted(kwargs.items())),
                                    _observed_stat(actual)))
        return actual

    def named_stat(*args, **kwargs):
        actual = real_stat(*args, **kwargs)
        if state["events"] is not None:
            state["events"].append(("stat", args, tuple(sorted(kwargs.items())),
                                    _observed_stat(actual)))
        return actual

    def getuid():
        actual = real_getuid()
        if state["events"] is not None:
            state["events"].append(("getuid", actual))
        return actual

    def policy(function):
        def forwarded(condition, label):
            state["events"].append(("policy", label, bool(condition)))
            return function(condition, label)
        return forwarded

    def directory(function, *, boolean):
        def forwarded(info, private, expected=None):
            index = state["index"]
            pin, expected_private = expected_calls[index]
            assert private is expected_private
            if boolean:
                assert expected is pin, "candidate must receive this actual retained pin"
            else:
                assert expected is None
            state["index"] += 1
            state["events"].append(("directory", index, private, pin, _projection(info)))
            result = (function(info, private, expected=expected) if boolean
                      else function(info, private))
            if boolean:
                assert type(result) is bool
                state["returns"]["bool"] += 1
                normalized = result
            else:
                assert type(result) is tuple and len(result) == 5
                state["returns"]["tuple"] += 1
                normalized = result == pin
            state["events"].append(("directory-result", normalized))
            return result  # Forward the real representation, not normalized truth.
        return forwarded

    traces, returns = {}, {}
    # Both modules' function globals instrumented. Shared os functions patched
    # ONCE each; no monkeypatch stacking/double-counting the shared module.
    with monkeypatch.context() as trace_patch:
        trace_patch.setattr(os, "fstat", fstat)
        trace_patch.setattr(os, "stat", named_stat)
        trace_patch.setattr(os, "getuid", getuid)
        trace_patch.setattr(api, "require", policy(baseline_require))
        trace_patch.setattr(candidate, "require", policy(candidate_require))
        trace_patch.setattr(api, "_directory", directory(baseline_directory, boolean=False))
        trace_patch.setattr(candidate, "_directory", directory(candidate_directory, boolean=True))
        for label, check in (("baseline", baseline_check), ("candidate", candidate_check)):
            state.update(events=[], index=0, returns=dict(tuple=0, bool=0))
            try:
                check(anchor)
                assert state["index"] == 17
                traces[label] = state["events"]
                returns[label] = state["returns"]
            finally:
                state["events"] = None
    # Every wrapper is restored BEFORE the first timed call.
    assert api._directory is baseline_directory and candidate._directory is candidate_directory
    assert api.require is baseline_require and candidate.require is candidate_require
    assert os.fstat is real_fstat and os.stat is real_stat and os.getuid is real_getuid
    assert traces["baseline"] == traces["candidate"], "fresh-stat/policy trace changed"
    assert returns == {
        "baseline": {"tuple": 17, "bool": 0},
        "candidate": {"tuple": 0, "bool": 17},
    }
    counts = {}
    for label, events in traces.items():
        counts[label] = {kind: sum(event[0] == kind for event in events)
                         for kind in ("fstat", "stat", "getuid", "policy", "directory",
                                      "directory-result")}
        private_calls = sum(private for pin, private in expected_calls)
        assert counts[label] == dict(
            fstat=9, stat=8, getuid=17 + private_calls,
            policy=9 + 2 * 17 + private_calls + 17 + 1,
            directory=17, **{"directory-result": 17})
    return dict(events=traces, counts=counts, returns=returns)


def _first_timed_call(check, anchor):
    cpu_start = time.process_time_ns()
    wall_start = time.monotonic_ns()
    check(anchor)
    wall_ns = time.monotonic_ns() - wall_start
    cpu_ns = time.process_time_ns() - cpu_start
    assert cpu_ns > 0 and wall_ns > 0
    return dict(cpu_ns=cpu_ns, wall_ns=wall_ns, checks=1)


def _timed_sample(check, anchor):
    cpu_start = time.process_time_ns()
    wall_start = time.monotonic_ns()
    for _ in range(400):
        check(anchor)
        check(anchor)
    wall_ns = time.monotonic_ns() - wall_start
    cpu_ns = time.process_time_ns() - cpu_start
    assert cpu_ns > 0 and wall_ns > 0
    return dict(cpu_ns=cpu_ns, wall_ns=wall_ns, iterations=400, checks_per_iteration=2)


def test_directory_projection_spike_actual_tiny_ac(case, owner, monkeypatch, request,
                                                  prohibit_real_effects):
    observed = {}
    baseline_check = api._Anchor.check
    baseline_directory = api._directory
    candidate_check = candidate._Anchor.check
    candidate_directory = candidate._directory

    async def hook(lease):
        root = Path(os.environ["HOME"]).parent
        path = root
        for component in ("spike-case", "export", "run", "checkpoint-1"):
            path = path / component
            os.mkdir(path, 0o700)  # Fresh exclusive owned experiment directories.
            actual = os.stat(path, follow_symlinks=False)
            assert stat.S_ISDIR(actual.st_mode)
            assert stat.S_IMODE(actual.st_mode) == 0o700 and actual.st_uid == os.getuid()
        registry = api._Registry()  # Actual production signature, no arguments.
        primary = None
        try:
            anchor = api._Anchor.absolute(registry, path, private=True)
            assert len(anchor.pins) == 9 and anchor.path == path
            traces = _forwarded_traces(
                anchor, baseline_check, candidate_check, baseline_directory,
                candidate_directory, monkeypatch)
            # First TIMED calls, after trace equivalence, before explicit warmup.
            # Not a claim of cold code/filesystem/cache or first-ever invocation.
            first = dict(baseline=_first_timed_call(baseline_check, anchor),
                         candidate=_first_timed_call(candidate_check, anchor))
            for _ in range(20):
                baseline_check(anchor)
            for _ in range(20):
                candidate_check(anchor)
            samples, pairs = [], []
            methods = {"baseline": baseline_check, "candidate": candidate_check}
            for pair_index in range(6):
                order = ("baseline", "candidate") if pair_index % 2 == 0 else (
                    "candidate", "baseline")
                pair = {}
                for label in order:
                    sample = _timed_sample(methods[label], anchor)
                    sample.update(pair=pair_index, implementation=label,
                                  position=len(pair), order="AB" if pair_index % 2 == 0 else "BA")
                    samples.append(sample)
                    pair[label] = sample
                pairs.append(dict(
                    pair=pair_index, order=list(order),
                    cpu_ratio=pair["candidate"]["cpu_ns"] / pair["baseline"]["cpu_ns"],
                    wall_ratio=pair["candidate"]["wall_ns"] / pair["baseline"]["wall_ns"]))
            assert len(samples) == 12 and len(pairs) == 6
            median_ratio = median(pair["cpu_ratio"] for pair in pairs)
            worst_ratio = max(pair["cpu_ratio"] for pair in pairs)
            gate_met = median_ratio <= 0.90 and worst_ratio <= 1.05
            observed.update(
                v=1, experiment="v327-directory-projection", lifecycle="synthetic observations",
                workload="real nine-pin anchor, two fresh checks per iteration",
                production_owner_unchanged=True, traces=traces, first_timed_calls=first,
                warmup_checks_each=20, pair_count=6, iterations_per_sample=400,
                checks_per_iteration=2, samples=samples, pairs=pairs,
                median_paired_cpu_ratio=median_ratio, worst_paired_cpu_ratio=worst_ratio,
                median_cpu_ratio_limit=0.90, worst_cpu_ratio_limit=1.05,
                gate_met=gate_met,
                screening_requires_all_six_green_cases=True,
                decision=("SCREENING_GATE_MET_PENDING_ALL_SIX_GREEN_NOT_PROMOTED" if gate_met
                          else "REJECTED_EXPERIMENT_CANDIDATE"),
                full_volume_or_23s_claim=False, all_samples_retained=True)
        except BaseException as error:
            primary = error
            registry.primary = error
            raise
        finally:
            try:
                registry.close_all()  # Exactly ONE sweep, never retry uncertainty.
            except BaseException as secondary:
                _RETAINED_SPIKE_REGISTRIES.append(registry)
                if primary is None:
                    raise
                primary.add_note("spike registry close failed: " + type(secondary).__name__)
        assert all(record.closed or record.handle is None for record in registry.records)
        # Patch ONLY the actual comparison functions. No candidate DTO, registry,
        # owner, reader, lease or C classes are installed into the actual API.
        monkeypatch.setattr(api, "_directory", candidate_directory)
        monkeypatch.setattr(api._Anchor, "check", candidate_check)

    perf.run_with_hook(case, owner, monkeypatch, hook)
    # run_with_hook has now required the actual tiny C full validation, 8 closes,
    # 24 identities, inventories, publication, second refusal and actual release.
    assert observed, "measurement must exist, never default the gate to success"
    observed["tiny_actual_ac_publication_second_refusal_release_completed"] = True
    request.node.user_properties.append((
        "directory_projection_measurement",
        json.dumps(observed, sort_keys=True, ensure_ascii=True, allow_nan=False,
                   separators=(",", ":"))))
    # Intentionally NO performance assertion. gate_met=false is a retained
    # REJECTED experiment, not a measurement-validity/unit-test failure.


@pytest.mark.parametrize("field", ("dev", "ino", "mode", "uid", "gid"))
def test_directory_projection_refuses_each_fresh_field(field, prohibit_real_effects):
    path = Path(os.environ["HOME"]).parent / ("spike-projection-" + field)
    os.mkdir(path, 0o700)
    actual = os.stat(path, follow_symlinks=False)  # Real observation first.
    pin = _projection(actual)
    assert candidate._directory(actual, False) == pin
    assert candidate._directory(actual, False, expected=pin) is True
    changed = SimpleNamespace(
        st_dev=actual.st_dev, st_ino=actual.st_ino, st_mode=actual.st_mode,
        st_uid=actual.st_uid, st_gid=actual.st_gid)
    if field == "dev":
        changed.st_dev += 1
    elif field == "ino":
        changed.st_ino += 1
    elif field == "mode":
        changed.st_mode |= stat.S_ISVTX
        assert changed.st_mode != actual.st_mode
    elif field == "uid":
        assert actual.st_uid != 0, "owned non-root H191 fixture required for uid mutation"
        changed.st_uid = 0  # Still admissible to the unchanged nonprivate policy.
    else:
        changed.st_gid += 1
    # Fault injection changes exactly one field AFTER a genuine directory stat.
    # No fake stat success or cached live fact grants any authority.
    changed_pin = _projection(changed)
    assert sum(a != b for a, b in zip(pin, changed_pin)) == 1
    assert candidate._directory(changed, False, expected=pin) is False, (
        "fresh " + field + " comparison guard missing")
