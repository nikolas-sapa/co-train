"""Mutation evidence must distinguish failed assertions from an invalid test run.

Only the three unmodified PTC/ledger/bench baselines run the repository's real suites.
Other subprocess checks use tiny offline fixtures, never historical mutants or
unbounded payloads. Exit-code aggregation tests replace only the runner's run().
"""

from __future__ import annotations

import importlib.util
import io
import itertools
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNERS = ("ptc", "step2", "train")
SOURCE = "VALUE = 1\n"
TEST_SOURCE = (
    "from .subject import VALUE\n\n"
    "def test_value():\n"
    "    assert VALUE == 1\n"
)


def _load_runner(name):
    spec = importlib.util.spec_from_file_location(
        f"mutation_harness_under_test_{name}", REPO / name / "mutate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registered_training_mutations_have_unique_anchors():
    module = _load_runner("train")
    invalid = []
    for label, filename, old, _ in module.MUTATIONS:
        count = (REPO / filename).read_text().count(old)
        if count != 1:
            invalid.append((label, filename, count))
    assert invalid == []


def _local_tempdirs(monkeypatch, module, tmp_path):
    """Keep the runners' real fresh copies inside pytest's temporary directory."""
    sequence = itertools.count()

    def mkdtemp(*, prefix):
        directory = tmp_path / f"{prefix}{next(sequence)}"
        directory.mkdir()
        return str(directory)

    monkeypatch.setattr(module.tempfile, "mkdtemp", mkdtemp)


@pytest.fixture(params=RUNNERS)
def runner(request, monkeypatch, tmp_path):
    module = _load_runner(request.param)
    _local_tempdirs(monkeypatch, module, tmp_path)
    if request.param != "ptc":
        monkeypatch.setattr(module, "PY", sys.executable)
    return request.param, module


def _configure_cli(name, module, monkeypatch, tmp_path, mutations,
                   *, target="subject.py", source=SOURCE):
    root = tmp_path / "source"
    for package in ("ptc", "ledger", "bench", "step2", "train"):
        directory = root / package
        directory.mkdir(parents=True)
        (directory / "__init__.py").write_text("")
    (root / "docs").mkdir()
    (root / "docs" / "pre-registration.md").write_text("# Offline fixture\n")
    shutil.copy(REPO / "process_watchdog.py", root / "process_watchdog.py")
    (root / name / "subject.py").write_text(SOURCE)
    (root / name / "test_subject.py").write_text(TEST_SOURCE)
    (root / name / target).write_text(source)
    monkeypatch.setattr(module, "REPO", root)
    if name == "train":
        monkeypatch.setattr(module, "MUTATIONS", [
            (label, f"train/{target}", old, new) for label, old, new in mutations
        ])
    else:
        argument = f"ptc/{target}" if name == "ptc" else target
        monkeypatch.setattr(sys, "argv", [str(module.__file__), argument])
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(mutations)))


def _result(code):
    if code == 0:
        stdout = "1 passed in 0.01s\n"
    elif code == 1:
        stdout = "FAILED test_subject.py::test_value - assert 2 == 1\n1 failed\n"
    elif code == 124:
        stdout = "HUNG: suite exceeded its deadline\nFAILED (hung)::timeout\n"
    else:
        # An invalid run can contain FAILED lines too. The process status must
        # take precedence over a flattering grep of its output.
        stdout = "FAILED test_subject.py::test_value - incomplete run\n"
    return subprocess.CompletedProcess(
        [], code, stdout, f"pytest infrastructure exit {code}\n" if code not in (0, 1) else ""
    )


def _fake_runs(monkeypatch, module, codes):
    remaining = iter(codes)
    observed = []

    def run(*args):
        result = _result(next(remaining))
        observed.append(result.returncode)
        return result

    monkeypatch.setattr(module, "run", run)
    return observed


def _row(output, label):
    return next(line for line in output.splitlines() if line.startswith(label + " "))


def _assert_invalid(row):
    assert "INVALID" in row.upper() or "ERROR" in row.upper(), row
    assert "died" not in row.lower() and "killed" not in row.lower(), row


@pytest.mark.parametrize("package", ["ptc", "ledger"])
def test_ptc_fresh_copies_required_packages_exactly_once(package, monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    copytree = module.shutil.copytree
    copies = []

    def record_copy(source, destination, *args, **kwargs):
        copies.append((Path(source), Path(destination)))
        return copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(module.shutil, "copytree", record_copy)
    sandbox = module.fresh(package)
    top_level = Counter(
        destination.name for _, destination in copies if destination.parent == sandbox
    )
    assert top_level == Counter({"ptc": 1, "ledger": 1, "bench": 1})
    for dependency in ("ptc", "ledger", "bench"):
        assert (sandbox / dependency / "__init__.py").is_file()
    assert sandbox.parent == tmp_path


@pytest.mark.parametrize("package", ["ptc", "ledger", "bench"])
def test_ptc_real_isolated_baseline_collects_and_passes(package, monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh(package)
    result = module.run(sandbox, package)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert re.search(r"\b[1-9]\d* passed\b", result.stdout), result.stdout


@pytest.mark.parametrize("missing_helper", [False, True], ids=["bundled", "missing-control"])
def test_fresh_runner_import_uses_its_own_watchdog(runner, tmp_path, missing_helper):
    name, module = runner
    sandbox = module.fresh(name) if name == "ptc" else module.fresh()
    helper = sandbox / "process_watchdog.py"
    assert helper.read_bytes() == (REPO / "process_watchdog.py").read_bytes()
    if missing_helper:
        helper.unlink()  # Only this test's newly generated copy.
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         "import runpy,sys; "
         "assert callable(runpy.run_path(sys.argv[1], "
         "run_name='import_probe')['run_bounded'])",
         str(sandbox / name / "mutate.py")],
        cwd=tmp_path, capture_output=True, text=True, timeout=3, check=False,
    )
    if missing_helper:
        assert result.returncode == 1
        assert "ModuleNotFoundError" in result.stderr
        assert "process_watchdog" in result.stderr
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4, 5, 7, -9, -15, 124])
def test_mutation_cli_classifies_exit_codes_without_false_kills(
    runner, code, monkeypatch, tmp_path, capsys
):
    name, module = runner
    _configure_cli(name, module, monkeypatch, tmp_path,
                   [("probe-mutation", "VALUE = 1", "VALUE = 2")])
    observed = _fake_runs(monkeypatch, module, [0, code])
    status = module.main()
    output = capsys.readouterr().out
    row = _row(output, "probe-mutation")
    assert observed == [0, code]
    if code == 0:
        assert status == 1
        assert "SURVIV" in row.upper()
    elif code == 1:
        assert status == 0
        assert "died" in row.lower() or "killed" in row.lower()
    elif name == "ptc" and code == 124:
        # PTC explicitly defines its own watchdog expiry as a dead mutant.
        # Preserve that policy, but make the timeout visible rather than
        # confusing it with an assertion failure or a pytest infrastructure exit.
        assert status == 0
        assert "TIMEOUT" in row.upper() or "HUNG" in row.upper()
        assert "INVALID" not in row.upper() and "ERROR" not in row.upper()
    else:
        assert status == 2, output
        _assert_invalid(row)


def test_timeout_cleanup_notes_are_visible_in_each_cli(
    runner, monkeypatch, tmp_path, capsys,
):
    name, module = runner
    _configure_cli(name, module, monkeypatch, tmp_path,
                   [("timeout-probe", "VALUE = 1", "VALUE = 2")])
    note = "WATCHDOG: Output pipes remained open; escaped descendant fixture"
    results = iter([
        _result(0),
        subprocess.CompletedProcess([], 124, "HUNG\nFAILED (hung)::timeout\n", note),
    ])
    monkeypatch.setattr(module, "run", lambda *args: next(results))
    assert module.main() == (0 if name == "ptc" else 2)
    assert note in capsys.readouterr().out


def test_mutation_cli_invalid_run_dominates_survivor_and_genuine_kill(
    runner, monkeypatch, tmp_path, capsys
):
    name, module = runner
    mutations = [(label, "VALUE = 1", "VALUE = 2")
                 for label in ("survivor-probe", "killed-probe", "invalid-probe")]
    _configure_cli(name, module, monkeypatch, tmp_path, mutations)
    observed = _fake_runs(monkeypatch, module, [0, 0, 1, 2])
    status = module.main()
    output = capsys.readouterr().out
    assert observed == [0, 0, 1, 2]
    assert status == 2, output
    assert "SURVIV" in _row(output, "survivor-probe").upper()
    killed = _row(output, "killed-probe").lower()
    assert "died" in killed or "killed" in killed
    _assert_invalid(_row(output, "invalid-probe"))


@pytest.mark.parametrize("count, anchor", [(0, "ABSENT"), (2, "1")])
def test_mutation_cli_bad_anchor_is_unverified_not_a_kill(
    runner, count, anchor, monkeypatch, tmp_path, capsys
):
    name, module = runner
    _configure_cli(name, module, monkeypatch, tmp_path,
                   [("anchor-probe", anchor, "2")],
                   source="VALUE = 1\nOTHER = 1\n")
    observed = _fake_runs(monkeypatch, module, [0])
    status = module.main()
    output = capsys.readouterr().out
    assert observed == [0]  # Never launch a mutant whose anchor was not unique.
    assert status == 1
    row = _row(output, "anchor-probe")
    assert f"ANCHOR x{count}" in row
    assert "unverified" in output.lower()
    assert "died" not in row.lower() and "killed" not in row.lower()


@pytest.mark.parametrize("code", [1, 2, 5, 124])
def test_mutation_cli_non_green_baseline_never_counts_a_mutant(
    runner, code, monkeypatch, tmp_path, capsys
):
    name, module = runner
    _configure_cli(name, module, monkeypatch, tmp_path,
                   [("must-not-run", "VALUE = 1", "VALUE = 2")])
    observed = _fake_runs(monkeypatch, module, [code])
    status = module.main()
    output = capsys.readouterr().out
    assert status == 2
    assert observed == [code]
    assert "BASELINE NOT GREEN" in output
    assert "must-not-run" not in output


@pytest.mark.parametrize("outcome, pytest_code, status", [
    ("healthy", 0, 1),
    ("assertion-broken", 1, 0),
    ("collection-broken", 2, 2),
    ("no-tests", 5, 2),
])
def test_mutation_cli_real_pytest_fixture_outcomes(
    runner, outcome, pytest_code, status, monkeypatch, tmp_path, capsys
):
    """Real fresh copies and real pytest, not fabricated CompletedProcess objects."""
    name, module = runner
    target, source, anchor = "subject.py", SOURCE, "VALUE = 1"
    if outcome == "no-tests":
        target, source, anchor = "test_subject.py", TEST_SOURCE, TEST_SOURCE
        replacement = "# No test functions remain.\n"
    elif outcome == "collection-broken":
        replacement = "raise ImportError('fixture collection failure')"
    else:
        replacement = "VALUE = 1  # survivor" if outcome == "healthy" else "VALUE = 2"
    _configure_cli(name, module, monkeypatch, tmp_path,
                   [("real-probe", anchor, replacement)], target=target, source=source)
    # Check the real subprocess status separately, then run the full CLI with
    # neither run() nor fresh() replaced. No fabricated process result can make
    # these integration checks pass.
    sandbox = module.fresh(name) if name == "ptc" else module.fresh()
    path = sandbox / name / target
    path.write_text(path.read_text().replace(anchor, replacement, 1))
    result = module.run(sandbox, name) if name == "ptc" else module.run(sandbox)
    assert result.returncode == pytest_code, \
        (result.returncode, result.stdout, result.stderr)
    actual = module.main()
    output = capsys.readouterr().out
    assert actual == status, output
    row = _row(output, "real-probe")
    if pytest_code in (2, 5):
        _assert_invalid(row)
    elif pytest_code == 0:
        assert "SURVIV" in row.upper()
    else:
        assert "died" in row.lower() or "killed" in row.lower()
