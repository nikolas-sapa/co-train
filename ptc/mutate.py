#!/usr/bin/env python3
"""Mutation harness for this repo's packages. Run with the interpreter that has
`verifiers`, naming the target file relative to the repo root:

    ~/scratch/verifiers-spike/.venv/bin/python ptc/mutate.py ptc/harness.py <<'JSON'
    [["name", "old text", "new text"], ...]
    JSON

    ~/scratch/verifiers-spike/.venv/bin/python ptc/mutate.py ledger/taskset.py < muts.json

The package is the first path segment; only that package is copied and only its tests
run. Parameterised rather than copied a third time -- `step2/mutate.py` already exists
as a sibling because step2 is another session's, and two copies is the limit.

Same discipline as `step2/mutate.py`, and deliberately a sibling rather than an
import: `step2/` is owned by another session and this one does not edit it.
The differences are the target directory and that the interpreter comes from
`sys.executable` instead of a hardcoded venv, because `verifiers` is not in
`.venv-tok` and a committed script must not point at a path under ~/scratch.

Fresh copy per mutation + PYTHONDONTWRITEBYTECODE=1: a byte-length-identical
mutation restored within the same second leaves identical mtime AND size, so
Python would keep executing the cached .pyc.
"""
import json, os, pathlib, shutil, signal, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def fresh(pkg: str) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix=f"mut.{pkg}."))
    shutil.copytree(REPO / pkg, d / pkg, ignore=shutil.ignore_patterns("__pycache__"))
    return d


SUITE_TIMEOUT = 300.0
"""Seconds one mutated suite may take before it is killed and counted as dead.

Required, not defensive. Mutating away an execution bound (`ptc/runtime.py`'s deadline
tracer) makes the suite's own `while True` test run forever, so an untimed harness
waits on the exact defect it was built to detect. A hung suite is a killed mutant --
it certainly did not pass -- but it has to be *recorded* as one rather than waited on.
"""


def run(d: pathlib.Path, pkg: str):
    """Run one mutated suite, killing the whole process TREE if it overruns.

    `subprocess.run(timeout=...)` kills the direct child only, and killing this script
    kills neither. Both gaps were real: interrupting a batch that had mutated away
    `ptc/runtime.py`'s deadline tracer left the suite's own `while True` test spinning,
    and four orphans were later found at 98% CPU, one of them 511 CPU-minutes in. A
    mutation harness for an execution bound must not be the thing that runs forever.

    So the child gets its own session and the whole group is signalled.
    """
    argv = [sys.executable, "-m", "pytest", f"{pkg}/", "-q", "--no-header",
            "-p", "no:cacheprovider"]
    process = subprocess.Popen(
        argv, cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**ENV, "PYTHONPATH": str(d)},
        start_new_session=True,      # its own process group, so killpg reaches pytest's children
    )
    try:
        stdout, stderr = process.communicate(timeout=SUITE_TIMEOUT)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        _terminate_tree(process)
        return subprocess.CompletedProcess(
            argv, 124,
            f"HUNG: suite exceeded {SUITE_TIMEOUT}s\nFAILED (hung)::timeout", "")
    except BaseException:
        # Ctrl-C included: leaving a runaway child behind is how the orphans happened.
        _terminate_tree(process)
        raise


def _terminate_tree(process: subprocess.Popen) -> None:
    """SIGTERM the group, then SIGKILL what ignores it. A spinning `while True` under a
    mutated-away tracer does ignore it."""
    for signum in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(process.pid), signum)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def main() -> int:
    target = sys.argv[1]
    if "/" not in target:
        sys.exit(f"name the target relative to the repo root, e.g. ptc/{target}")
    pkg, _, filename = target.partition("/")
    muts = json.load(sys.stdin)
    base = run(fresh(pkg), pkg)
    if base.returncode:
        print("FRESH BASELINE NOT GREEN:\n" + base.stdout[-2000:])
        return 2
    print("baseline:", base.stdout.strip().splitlines()[-1], "\n", flush=True)
    print(f"{'mutation':46} | verdict")
    print("-" * 82)
    survivors = []
    for name, old, new in muts:
        d = fresh(pkg)
        f = d / pkg / filename
        s = f.read_text()
        if s.count(old) != 1:
            print(f"{name:46} | ANCHOR x{s.count(old)} (not unique)", flush=True)
            survivors.append(name + " [unverified]")
            continue
        f.write_text(s.replace(old, new, 1))
        r = run(d, pkg)
        if r.returncode == 0:
            survivors.append(name)
        killed = [l.split("::")[-1].split()[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        n_failed = len(killed)
        print(f"{name:46} | {'died' if r.returncode else '*** SURVIVED ***':16} "
              f"{f'{n_failed} test(s), e.g. ' + killed[0] if killed else ''}")
    print("-" * 82)
    print("survivors:", survivors if survivors else "none")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
