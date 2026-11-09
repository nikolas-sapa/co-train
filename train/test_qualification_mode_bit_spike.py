"""V333 SOURCE ONLY, UNRUN: eight new cases for the narrow stat-mode-bit spike.

Parent stages the exact owned RED/GREEN source copy as
train/_qualification_mode_bit_spike.py and this file unchanged as
train/test_qualification_mode_bit_spike.py. Only GREEN measurements screen the
candidate. Test PASS is NOT speed approval. Actual tiny A/C validation is
reused unchanged; lifecycle observations remain synthetic.
"""
import json
import os
from pathlib import Path
from statistics import median
import stat
import time

import pytest

from train import test_qualification_lease_performance as perf
from train import _qualification_mode_bit_spike as candidate

api = perf.api
valid = perf.valid
case, owner = perf.case, perf.owner
prohibit_real_effects = perf.prohibit_real_effects


def _fields(info):
    # st_atime_ns deliberately excluded: the forwarded os.read between traced
    # calls may update atime without changing any identity semantics here.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _with_mode(info, mode):
    class ModeView:
        # Fault injection only. Preserve genuine nanoseconds and all other
        # metadata, unlike reconstructing stat_result from its 10-item tuple.
        def __getattr__(self, name):
            return getattr(info, name)
    result = ModeView()
    result.st_mode = mode
    assert result.st_mode == mode
    assert all(getattr(result, name) == getattr(info, name) for name in (
        "st_dev", "st_ino", "st_nlink", "st_uid", "st_gid", "st_size",
        "st_mtime_ns", "st_ctime_ns"))
    return result


def _owned_fixtures(label):
    root = Path(os.environ["HOME"]).parent
    base = root / ("spike-mode-bit-" + label + "-" + str(os.getpid())
                   + "-" + str(time.monotonic_ns()))
    os.mkdir(base, 0o700)
    directory = base / "dir"
    os.mkdir(directory, 0o700)
    fd = os.open(base / "regular.bin",
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, b"x")
    finally:
        os.close(fd)  # Exactly one close; the generation is experiment-owned.
    return (base, os.stat(directory, follow_symlinks=False),
            os.stat(base / "regular.bin", follow_symlinks=False))


def _install_tracers(events):
    """Forwarding wrappers only; every call still reaches the real function."""
    assert candidate.os is api.os is os, "shared os module wrapped exactly once"
    assert candidate.require is api.require, "same imported require shared once"
    saved = {}

    def wrap(obj, name, wrapper):
        saved[(obj, name)] = getattr(obj, name)
        setattr(obj, name, wrapper)

    real_fstat = os.fstat
    real_stat = os.stat
    real_getuid = os.getuid
    real_read = os.read

    def fstat(*args, **kwargs):
        actual = real_fstat(*args, **kwargs)
        events.append(("fstat", args, tuple(sorted(kwargs.items())),
                       _fields(actual)))
        return actual

    def named_stat(*args, **kwargs):
        actual = real_stat(*args, **kwargs)
        events.append(("stat", args, tuple(sorted(kwargs.items())),
                       _fields(actual)))
        return actual

    def getuid():
        actual = real_getuid()
        events.append(("getuid", actual))
        return actual

    def fd_read(fd, count):
        actual = real_read(fd, count)
        events.append(("osread", fd, count, len(actual)))
        return actual

    def require_forward(impl):
        def forwarded(condition, label):
            events.append(("policy", label, bool(condition)))
            return impl(condition, label)
        return forwarded

    def directory(impl):
        def forwarded(info, private):
            events.append(("directory", bool(private), _fields(info)))
            return impl(info, private)
        return forwarded

    def regular(impl):
        def forwarded(info, private):
            events.append(("regular", bool(private), _fields(info)))
            return impl(info, private)
        return forwarded

    def observe(impl):
        def forwarded(self):
            events.append(("observe", self.role))
            return impl(self)
        return forwarded

    def check_live(impl):
        def forwarded(self):
            events.append(("check_live", self._role))
            return impl(self)
        return forwarded

    def monitor(impl):
        def forwarded(self):
            events.append(("monitor",))
            return impl(self)
        return forwarded

    def lease_assert(impl):
        def forwarded(*args, **kwargs):
            events.append(("lease_assert",))
            return impl(*args, **kwargs)
        return forwarded

    wrap(os, "fstat", fstat)
    wrap(os, "stat", named_stat)
    wrap(os, "getuid", getuid)
    wrap(os, "read", fd_read)
    wrap(api, "require", require_forward(api.require))
    wrap(candidate, "require", require_forward(candidate.require))
    # Arm's currently installed policy functions are wrapped after each swap.
    wrap(api, "_directory", directory(getattr(api, "_directory")))
    wrap(api, "_regular", regular(getattr(api, "_regular")))
    wrap(api._Child, "observe", observe(api._Child.observe))
    wrap(api._ParentChannel, "check_live", check_live(api._ParentChannel.check_live))
    wrap(api.IsolatedOwner, "_monitor_armed",
         monitor(api.IsolatedOwner._monitor_armed))
    wrap(api.IsolatedOwner, "_assert_parent_read_lease",
         lease_assert(api.IsolatedOwner._assert_parent_read_lease))
    return saved


def _restore(saved):
    for (obj, name), impl in saved.items():
        setattr(obj, name, impl)


async def _first_eof_experiment(reader, state, observed, monkeypatch):
    """Trace equivalence, then the repeated-EOF benchmark on ONE open reader."""
    baseline_directory, baseline_regular = api._directory, api._regular
    # Register undo before any direct arm swap, including failing traces.
    monkeypatch.setattr(api, "_directory", baseline_directory)
    monkeypatch.setattr(api, "_regular", baseline_regular)
    candidate_directory, candidate_regular = (
        candidate._directory, candidate._regular)

    def swap(use_candidate):
        api._directory = candidate_directory if use_candidate else baseline_directory
        api._regular = candidate_regular if use_candidate else baseline_regular

    bound = reader.read  # Saved actual bound method on this SAME open reader.
    pins = reader._file.parent.pins
    depth = len(pins)
    private_open = sum(1 for p, n, r, pin, private in pins if private)
    private_named = sum(
        1 for p, n, r, pin, private in pins if p is not None and private)

    traces = {}
    for use_candidate, label in ((False, "baseline"), (True, "candidate")):
        swap(use_candidate)
        events = []
        saved = _install_tracers(events)
        try:
            result = await bound(65536)
            assert result == b"", "repeated-EOF trace workload expected"
        finally:
            _restore(saved)
        traces[label] = events
    swap(False)
    assert api._directory is baseline_directory
    assert api._regular is baseline_regular
    # Every wrapper restored BEFORE the first timed call.
    assert traces["baseline"] == traces["candidate"], (
        "fresh-stat/policy/monitor trace changed")
    counts = {tag: sum(event[0] == tag for event in traces["baseline"])
              for tag in ("fstat", "stat", "getuid", "osread", "policy",
                          "directory", "regular", "observe", "check_live",
                          "monitor", "lease_assert")}
    expected = dict(
        fstat=2 * depth + 2, stat=2 * depth, directory=2 * (2 * depth - 1),
        regular=4,
        getuid=2 * (2 * depth - 1) + 2 * (private_open + private_named) + 4,
        osread=1, observe=12, check_live=12, monitor=6, lease_assert=6)
    assert {k: v for k, v in counts.items() if k != "policy"} == expected
    assert counts["policy"] > 0

    async def timed_call():
        cpu_start = time.process_time_ns()
        wall_start = time.monotonic_ns()
        result = await bound(65536)
        wall_ns = time.monotonic_ns() - wall_start
        cpu_ns = time.process_time_ns() - cpu_start
        assert result == b"" and cpu_ns > 0 and wall_ns > 0
        return dict(cpu_ns=cpu_ns, wall_ns=wall_ns, reads=1)

    async def timed_sample():
        cpu_start = time.process_time_ns()
        wall_start = time.monotonic_ns()
        for _ in range(400):
            result = await bound(65536)
            assert result == b""
        wall_ns = time.monotonic_ns() - wall_start
        cpu_ns = time.process_time_ns() - cpu_start
        assert cpu_ns > 0 and wall_ns > 0
        return dict(cpu_ns=cpu_ns, wall_ns=wall_ns, reads=400)

    first = {}
    for use_candidate, label in ((False, "baseline"), (True, "candidate")):
        swap(use_candidate)
        first[label] = await timed_call()
    for _ in range(20):  # Candidate warmups; still installed.
        assert await bound(65536) == b""
    swap(False)
    for _ in range(20):  # Baseline warmups.
        assert await bound(65536) == b""
    samples, pairs = [], []
    methods = ((False, "baseline"), (True, "candidate"))
    for pair_index in range(6):
        order = (0, 1) if pair_index % 2 == 0 else (1, 0)
        pair = {}
        for position, arm_index in enumerate(order):
            use_candidate, label = methods[arm_index]
            swap(use_candidate)
            sample = await timed_sample()
            sample.update(pair=pair_index, implementation=label,
                          position=position,
                          order="AB" if pair_index % 2 == 0 else "BA")
            samples.append(sample)
            pair[label] = sample
        pairs.append(dict(
            pair=pair_index, order=[methods[i][1] for i in order],
            cpu_ratio=pair["candidate"]["cpu_ns"] / pair["baseline"]["cpu_ns"],
            wall_ratio=pair["candidate"]["wall_ns"]
            / pair["baseline"]["wall_ns"]))
    assert len(samples) == 12 and len(pairs) == 6
    median_ratio = median(pair["cpu_ratio"] for pair in pairs)
    worst_ratio = max(pair["cpu_ratio"] for pair in pairs)
    gate_met = median_ratio <= 0.90 and worst_ratio <= 1.05
    observed.update(
        v=1, experiment="v333-stat-mode-bit-inline",
        workload=("repeated ordinary EOF reads on the SAME open first bulk "
                  "reader; fresh per-read checks only, NOT bulk copy/hash"),
        lifecycle="synthetic lifecycle observations; source/lifecycle mocks",
        production_owner_unchanged=True,
        reader_key=valid._BULK_KEYS[0],
        forwarded_positive_reads=state["positive_reads"],
        anchor_pin_count=depth,
        private_open_directory_calls=private_open,
        private_named_directory_calls=private_named,
        trace_events_baseline=traces["baseline"],
        trace_events_candidate=traces["candidate"],
        trace_counts=counts, trace_counts_expected=expected,
        first_timed_calls=first, warmup_reads_each=20,
        pair_count=6, reads_per_sample=400,
        samples=samples, pairs=pairs,
        median_paired_cpu_ratio=median_ratio,
        worst_paired_cpu_ratio=worst_ratio,
        median_cpu_ratio_limit=0.90, worst_cpu_ratio_limit=1.05,
        gate_met=gate_met,
        all_samples_retained=True, repeated_eof=True,
        decision=("SCREENING_GATE_MET_PENDING_ALL_EIGHT_GREEN_NOT_PROMOTED"
                  if gate_met else "REJECTED_EXPERIMENT_CANDIDATE"),
        full_volume_or_23s_claim=False)
    # Candidate comparison functions stay installed so the remaining actual
    # tiny C validation, closes, seal, publication and release exercise them.
    monkeypatch.setattr(api, "_directory", candidate_directory)
    monkeypatch.setattr(api, "_regular", candidate_regular)


def _equivalence(production_function, candidate_function, base_info):
    mismatches = []
    for mode in range(65536):
        info = _with_mode(base_info, mode)
        for private in (False, True):
            try:
                expected = production_function(info, private)
            except ValueError as error:
                expected = ("raise", error.args)
            try:
                actual = candidate_function(info, private)
            except ValueError as error:
                actual = ("raise", error.args)
            if actual != expected and len(mismatches) < 8:
                mismatches.append(dict(mode=oct(mode), private=private,
                                       expected=repr(expected),
                                       actual=repr(actual)))
    return mismatches


def test_mode_bit_first_bulk_reader_eof_benchmark(case, owner, monkeypatch,
                                                  request,
                                                  prohibit_real_effects):
    observed = {}

    async def hook(lease):
        audit_open_export = api.ParentReadLease.open_export
        real_read = api.RegisteredReader.read
        state = dict(reader=None, eof_seen=False, positive_reads=0)

        def capture_open(self_lease, key):
            opened = audit_open_export(self_lease, key)
            if state["reader"] is None and key in valid._BULK_KEYS:
                state["reader"] = opened
            return opened

        async def read_spy(self, maximum):
            result = await real_read(self, maximum)
            if self is state["reader"] and not state["eof_seen"]:
                if result:
                    state["positive_reads"] += 1
                else:
                    state["eof_seen"] = True
                    api.RegisteredReader.read = real_read
                    await _first_eof_experiment(
                        self, state, observed, monkeypatch)
            return result

        monkeypatch.setattr(api.ParentReadLease, "open_export", capture_open)
        monkeypatch.setattr(api.RegisteredReader, "read", read_spy)

    perf.run_with_hook(case, owner, monkeypatch, hook)
    # run_with_hook has required the actual tiny C full validation: 8 readers,
    # 24 identities, 2 inventories, publication, second refusal, actual release.
    assert observed, "first bulk reader EOF experiment never ran"
    observed["tiny_actual_ac_publication_second_refusal_release_completed"] = True
    request.node.user_properties.append((
        "mode_bit_measurement",
        json.dumps(observed, sort_keys=True, ensure_ascii=True,
                   allow_nan=False, separators=(",", ":"))))
    # Intentionally NO performance assertion. gate_met=false is a retained
    # REJECTED experiment, not a measurement-validity/unit-test failure.


def test_mode_bit_directory_policy_exhaustive_equivalence(prohibit_real_effects):
    _, dir_info, _ = _owned_fixtures("dir-exhaustive")
    mismatches = _equivalence(api._directory, candidate._directory, dir_info)
    assert not mismatches, "directory policy divergence: " + json.dumps(mismatches)


def test_mode_bit_regular_policy_exhaustive_equivalence(prohibit_real_effects):
    _, _, file_info = _owned_fixtures("regular-exhaustive")
    mismatches = _equivalence(api._regular, candidate._regular, file_info)
    assert not mismatches, "regular policy divergence: " + json.dumps(mismatches)


def test_mode_bit_dir_not_directory_refused(prohibit_real_effects):
    _, dir_info, _ = _owned_fixtures("dir-not-directory")
    mutated = _with_mode(
        dir_info, (dir_info.st_mode & ~0o170000) | stat.S_IFREG)
    with pytest.raises(ValueError, match="owned directory"):
        api._directory(mutated, False)
    with pytest.raises(ValueError, match="owned directory"):
        candidate._directory(mutated, False)
    for private in (False, True):
        assert candidate._directory(dir_info, private) == api._directory(
            dir_info, private)


def test_mode_bit_dir_world_writable_refused(prohibit_real_effects):
    _, dir_info, _ = _owned_fixtures("dir-world-writable")
    mutated = _with_mode(dir_info, dir_info.st_mode | 0o002)
    with pytest.raises(ValueError, match="unsafe writable directory"):
        api._directory(mutated, False)
    with pytest.raises(ValueError, match="unsafe writable directory"):
        candidate._directory(mutated, False)
    for private in (False, True):
        assert candidate._directory(dir_info, private) == api._directory(
            dir_info, private)


def test_mode_bit_dir_private0750_refused(prohibit_real_effects):
    _, dir_info, _ = _owned_fixtures("dir-private0750")
    mutated = _with_mode(
        dir_info, (dir_info.st_mode & ~0o7777) | 0o750)
    with pytest.raises(ValueError, match="private owner700 directory"):
        api._directory(mutated, True)
    with pytest.raises(ValueError, match="private owner700 directory"):
        candidate._directory(mutated, True)
    for private in (False, True):
        assert candidate._directory(dir_info, private) == api._directory(
            dir_info, private)


def test_mode_bit_regular_not_regular_refused(prohibit_real_effects):
    _, _, file_info = _owned_fixtures("regular-not-regular")
    mutated = _with_mode(
        file_info, (file_info.st_mode & ~0o170000) | stat.S_IFDIR)
    with pytest.raises(ValueError, match="owned single-link regular file"):
        api._regular(mutated, False)
    with pytest.raises(ValueError, match="owned single-link regular file"):
        candidate._regular(mutated, False)
    for private in (False, True):
        assert candidate._regular(file_info, private) == api._regular(
            file_info, private)


def test_mode_bit_regular_private0640_refused(prohibit_real_effects):
    _, _, file_info = _owned_fixtures("regular-private0640")
    mutated = _with_mode(
        file_info, (file_info.st_mode & ~0o7777) | 0o640)
    with pytest.raises(ValueError, match="private owner600 file"):
        api._regular(mutated, True)
    with pytest.raises(ValueError, match="private owner600 file"):
        candidate._regular(mutated, True)
    for private in (False, True):
        assert candidate._regular(file_info, private) == api._regular(
            file_info, private)
