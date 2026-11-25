"""Mutation evidence must distinguish failed assertions from an invalid test run.

Only the three unmodified PTC/ledger/bench baselines run the repository's real suites.
Other subprocess checks use tiny offline fixtures, never historical mutants or
unbounded payloads. Exit-code aggregation tests replace only the runner's run().
"""

from __future__ import annotations

import ast
import importlib.util
import io
import itertools
import json
import os
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
EXPECTED_PTC_CONTEXT = (
    "process_watchdog.py",
    "pytest.ini",
    "cotrain_bash_qa.py",
    "cotrain_bash_qa_env.py",
    "cotrain_bash_qa_eval.py",
    "cotrain_ptc_qa.py",
    "cotrain_owned_sql.py",
    "train/__init__.py",
    "train/guards.py",
    "train/sql_episodes.py",
    "train/sql_reporting.py",
    "spec/spikes/reference/sql-sdk-writer-barrier/probe.py",
)
CONTEXT_IMPORTS = (
    "cotrain_bash_qa", "cotrain_bash_qa_env", "cotrain_bash_qa_eval",
    "cotrain_ptc_qa", "cotrain_owned_sql",
    "train", "train.guards", "train.sql_episodes", "train.sql_reporting",
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


@pytest.mark.parametrize("label, target", [
    ("gate: preflight skips the gate", "preflight"),
    ("gate: native SQL preflight skips the gate", "native_sql_preflight"),
])
def test_registered_gate_mutations_affect_only_the_named_lane(label, target):
    module = _load_runner("train")
    _, filename, old, replacement = next(row for row in module.MUTATIONS if row[0] == label)
    source = (REPO / filename).read_text()
    assert source.count(old) == 1
    tree = ast.parse(source.replace(old, replacement, 1))
    for name in ("preflight", "native_sql_preflight"):
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        calls = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "require_frontier_taskset"
        ]
        assert len(calls) == int(name != target)


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
    for relative in EXPECTED_PTC_CONTEXT:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / relative, destination)
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


def _assert_ptc_context(sandbox):
    missing = [relative for relative in EXPECTED_PTC_CONTEXT
               if not (sandbox / relative).is_file()]
    assert not missing, f"missing declared package context: {missing}"


@pytest.mark.parametrize("package", ["ptc", "ledger", "bench"])
def test_ptc_fresh_copies_explicit_context(package, monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh(package)
    _assert_ptc_context(sandbox)
    assert module.CONTEXT_FILES == EXPECTED_PTC_CONTEXT
    context_files = {
        path.relative_to(sandbox).as_posix()
        for path in sandbox.rglob("*") if path.is_file()
        and path.relative_to(sandbox).parts[0] not in ("ptc", "ledger", "bench")
    }
    assert len(EXPECTED_PTC_CONTEXT) == 12
    assert context_files == set(EXPECTED_PTC_CONTEXT)
    for relative in EXPECTED_PTC_CONTEXT:
        destination = sandbox / relative
        assert destination.read_bytes() == (REPO / relative).read_bytes()
        assert destination.resolve().is_relative_to(sandbox.resolve())
        assert not any(path.is_symlink()
                       for path in (destination, *destination.parents)
                       if path.is_relative_to(sandbox))


def _probe_ptc_context(module, sandbox, code, *arguments):
    return module.run_bounded(
        [sys.executable, "-I", "-B", "-c",
         "import pathlib,sys; "
         "sandbox=pathlib.Path(sys.argv[1]).resolve(); "
         "sys.path.insert(0,str(sandbox)); " + code,
         str(sandbox), *arguments],
        cwd=sandbox.parent, timeout=10,
        env={**os.environ, "PYTHONPATH": str(sandbox),
             "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_ptc_fresh_context_imports_only_sandbox_sources(monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh("ptc")
    _assert_ptc_context(sandbox)
    result = _probe_ptc_context(
        module, sandbox,
        "import importlib,json; "
        "names=json.loads(sys.argv[2]); "
        "origins={name:str(pathlib.Path(importlib.import_module(name).__file__).resolve()) "
        "for name in names}; "
        "reference=sandbox / sys.argv[3]; "
        "assert reference.read_bytes(); "
        "source=pathlib.Path(sys.argv[4]).resolve(); "
        "borrowed={name:str(pathlib.Path(mod.__file__).resolve()) "
        "for name,mod in tuple(sys.modules.items()) "
        "if getattr(mod,'__file__',None) "
        "and pathlib.Path(mod.__file__).resolve().is_relative_to(source)}; "
        "print(json.dumps({'origins':origins,'borrowed':borrowed,"
        "'reference':str(reference.resolve())}))",
        json.dumps(CONTEXT_IMPORTS), EXPECTED_PTC_CONTEXT[-1], str(REPO),
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    report = json.loads(result.stdout)
    assert set(report["origins"]) == set(CONTEXT_IMPORTS)
    for name, origin in report["origins"].items():
        relative = "train/__init__.py" if name == "train" else name.replace(".", "/") + ".py"
        assert Path(origin) == (sandbox / relative).resolve()
    assert report["borrowed"] == {}
    assert Path(report["reference"]) == (sandbox / EXPECTED_PTC_CONTEXT[-1]).resolve()


@pytest.mark.parametrize("missing", [
    "cotrain_owned_sql.py", "spec/spikes/reference/sql-sdk-writer-barrier/probe.py",
])
def test_ptc_fresh_context_missing_dependency_is_not_borrowed(
    missing, monkeypatch, tmp_path,
):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh("ptc")
    _assert_ptc_context(sandbox)
    assert (REPO / missing).is_file()
    (sandbox / missing).unlink()  # Only this test's newly generated copy.
    code = ("import cotrain_owned_sql" if missing == "cotrain_owned_sql.py"
            else "(sandbox / sys.argv[2]).read_bytes()")
    result = _probe_ptc_context(module, sandbox, code, missing)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    if missing == "cotrain_owned_sql.py":
        assert "ModuleNotFoundError: No module named 'cotrain_owned_sql'" in result.stderr
    else:
        assert "FileNotFoundError" in result.stderr
        assert str(sandbox / missing) in result.stderr
    assert str(REPO) not in result.stderr


@pytest.mark.parametrize("package", ["ptc", "ledger", "bench"])
def test_ptc_run_selects_only_requested_package(package, monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    _configure_cli("ptc", module, monkeypatch, tmp_path, [])
    for sibling in ("ptc", "ledger", "bench"):
        (module.REPO / sibling / "test_subject.py").write_text(
            "def test_selected_package():\n"
            f"    assert {sibling == package!r}, 'unselected sibling collected: {sibling}'\n"
        )
    sandbox = module.fresh(package)
    result = module.run(sandbox, package)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert re.search(r"\b1 passed\b", result.stdout), result.stdout
    assert "unselected sibling collected" not in result.stdout + result.stderr
    assert result.args == [
        sys.executable, "-m", "pytest", f"{package}/", "-q", "--no-header",
        "-p", "no:cacheprovider",
    ]


@pytest.mark.parametrize("package", ["ptc", "ledger", "bench"])
def test_ptc_real_isolated_baseline_collects_and_passes(package, monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh(package)
    result = module.run(sandbox, package)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert re.search(r"\b[1-9]\d* passed\b", result.stdout), result.stdout


def test_ptc_fresh_preserves_default_tokenizer_exclusion(monkeypatch, tmp_path):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    sandbox = module.fresh("bench")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "bench/test_contamination.py",
         "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=sandbox, env={**os.environ, "PYTHONPATH": str(sandbox),
                          "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "test_v2_control_is_well_formed_and_matches_v1_shape" in result.stdout
    for control in ("test_long_positive_control_is_longer_and_still_canonical",
                    "test_v2_control_is_length_matched_to_bird"):
        assert f"::{control}" not in result.stdout, result.stdout
    assert "2 deselected" in result.stdout
    assert (sandbox / "pytest.ini").read_bytes() == (REPO / "pytest.ini").read_bytes()


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


def _diagnostic_sandbox(monkeypatch, tmp_path, source):
    """Declare tiny offline packages, never run the repository's PTC suite."""
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    _configure_cli("ptc", module, monkeypatch, tmp_path, [])
    (module.REPO / "ptc" / "test_subject.py").write_text(source)
    for sibling in ("ledger", "bench"):
        (module.REPO / sibling / "test_sibling.py").write_text(
            "from pathlib import Path\n\n"
            "def test_unselected_sibling():\n"
            "    Path('sibling-ran').write_text('unexpected')\n"
            "    assert False, 'unselected sibling collected'\n"
        )
    return module, module.fresh("ptc")


def test_ptc_diagnostic_default_argv_unchanged(monkeypatch, tmp_path):
    module = _load_runner("ptc")
    calls = []

    def bounded(argv, **kwargs):
        calls.append((argv, kwargs))
        return _result(0)

    monkeypatch.setattr(module, "run_bounded", bounded)
    module.run(tmp_path, "ledger")
    module.run(tmp_path, "ledger", diagnostic=False)
    module.run(tmp_path, "ledger", diagnostic=True)
    expected = [
        sys.executable, "-m", "pytest", "ledger/", "-q", "--no-header",
        "-p", "no:cacheprovider",
    ]
    assert [argv for argv, _ in calls] == [
        expected, expected, expected + ["--maxfail=1"],
    ]
    assert module.SUITE_TIMEOUT == 300.0
    assert [kwargs for _, kwargs in calls] == [{
        "cwd": tmp_path, "timeout": 300.0,
        "env": {**module.ENV, "PYTHONPATH": str(tmp_path)},
    }] * 3


def test_ptc_diagnostic_green_runs_all_selected_tests(monkeypatch, tmp_path):
    module, sandbox = _diagnostic_sandbox(
        monkeypatch, tmp_path,
        "from pathlib import Path\n\n"
        "def test_one():\n"
        "    Path('one-ran').write_text('1')\n\n"
        "def test_two():\n"
        "    Path('two-ran').write_text('2')\n\n"
        "def test_three():\n"
        "    Path('three-ran').write_text('3')\n",
    )
    result = module.run(sandbox, "ptc", diagnostic=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert re.search(r"\b3 passed\b", result.stdout), result.stdout
    assert {p.name for p in sandbox.glob("*-ran")} == {
        "one-ran", "two-ran", "three-ran",
    }
    assert "unselected sibling collected" not in result.stdout + result.stderr
    assert result.args[-1] == "--maxfail=1"


def test_ptc_diagnostic_stops_after_real_first_failure(monkeypatch, tmp_path):
    module, sandbox = _diagnostic_sandbox(
        monkeypatch, tmp_path,
        "from pathlib import Path\n\n"
        "def test_first_failure():\n"
        "    Path('first-ran').write_text('1')\n"
        "    assert False, 'diagnostic first assertion'\n\n"
        "def test_later_infrastructure_error():\n"
        "    Path('second-ran').write_text('2')\n"
        "    raise RuntimeError('later infrastructure-like exception')\n",
    )
    result = module.run(sandbox, "ptc", diagnostic=True)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert {p.name for p in sandbox.glob("*-ran")} == {"first-ran"}
    assert "AssertionError: diagnostic first assertion" in result.stdout
    assert "ptc/test_subject.py:" in result.stdout
    assert "stopping after 1 failures" in result.stdout
    assert re.search(r"\b1 failed\b", result.stdout), result.stdout
    assert "later infrastructure-like exception" not in result.stdout + result.stderr


def test_ptc_diagnostic_collection_error_preserves_exit_two(monkeypatch, tmp_path):
    module, sandbox = _diagnostic_sandbox(
        monkeypatch, tmp_path,
        "from pathlib import Path\n"
        "raise ImportError('diagnostic collection failure')\n\n"
        "def test_never_runs():\n"
        "    Path('body-ran').write_text('unexpected')\n",
    )
    result = module.run(sandbox, "ptc", diagnostic=True)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert not list(sandbox.glob("*-ran"))
    assert "ImportError: diagnostic collection failure" in result.stdout
    assert "ptc/test_subject.py:" in result.stdout
    assert re.search(r"\b1 error\b", result.stdout), result.stdout


def test_ptc_diagnostic_preserves_nonstandard_session_exit(monkeypatch, tmp_path):
    module, sandbox = _diagnostic_sandbox(
        monkeypatch, tmp_path,
        "from pathlib import Path\n\n"
        "def test_unit():\n"
        "    Path('unit-ran').write_text('1')\n",
    )
    (sandbox / "ptc" / "conftest.py").write_text(
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    session.exitstatus = 3\n"
    )
    result = module.run(sandbox, "ptc", diagnostic=True)
    assert result.returncode == 3, (result.stdout, result.stderr)
    assert {p.name for p in sandbox.glob("*-ran")} == {"unit-ran"}
    assert re.search(r"\b1 passed\b", result.stdout), result.stdout
    assert "FAILED" not in result.stdout + result.stderr


def test_ptc_diagnostic_timeout_preserves_existing_contract(monkeypatch, tmp_path):
    module = _load_runner("ptc")
    calls = []

    def timeout(argv, **kwargs):
        calls.append((argv, kwargs))
        exc = subprocess.TimeoutExpired(
            argv, kwargs["timeout"], output="original stdout",
            stderr="original stderr",
        )
        exc.add_note("original cleanup note")
        raise exc

    monkeypatch.setattr(module, "run_bounded", timeout)
    result = module.run(tmp_path, "ptc", diagnostic=True)
    assert len(calls) == 1
    assert calls[0][1] == {
        "cwd": tmp_path, "timeout": 300.0,
        "env": {**module.ENV, "PYTHONPATH": str(tmp_path)},
    }
    assert result.args == calls[0][0]
    assert result.args[-1] == "--maxfail=1"
    assert result.returncode == 124
    assert result.stdout == (
        "original stdout\nHUNG: suite exceeded 300.0s\nFAILED (hung)::timeout"
    )
    assert result.stderr == "original stderr\nWATCHDOG: original cleanup note\n"


def test_ptc_mutation_cli_never_enables_diagnostic_mode(
    monkeypatch, tmp_path, capsys,
):
    module = _load_runner("ptc")
    _local_tempdirs(monkeypatch, module, tmp_path)
    mutations = [(label, "VALUE = 1", "VALUE = 2")
                 for label in ("survivor-probe", "killed-probe", "invalid-probe")]
    _configure_cli("ptc", module, monkeypatch, tmp_path, mutations)
    codes = iter([0, 0, 1, 2])
    calls = []

    def run(*args, **kwargs):
        code = next(codes)
        calls.append((args, kwargs, code))
        return _result(code)

    monkeypatch.setattr(module, "run", run)
    assert module.main() == 2
    output = capsys.readouterr().out
    assert [code for _, _, code in calls] == [0, 0, 1, 2]
    assert all(len(args) == 2 and args[1] == "ptc" and kwargs == {}
               for args, kwargs, _ in calls)
    assert len({args[0] for args, _, _ in calls}) == 4
    assert "SURVIV" in _row(output, "survivor-probe").upper()
    assert "died" in _row(output, "killed-probe")
    _assert_invalid(_row(output, "invalid-probe"))
