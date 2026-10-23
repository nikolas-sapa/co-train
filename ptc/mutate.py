#!/usr/bin/env python3
"""Mutation harness for this repo's packages. Run with the interpreter that has
`verifiers`, naming the target file relative to the repo root:

    ~/scratch/verifiers-spike/.venv/bin/python ptc/mutate.py ptc/harness.py <<'JSON'
    [["name", "old text", "new text"], ...]
    JSON

    ~/scratch/verifiers-spike/.venv/bin/python ptc/mutate.py ledger/taskset.py < muts.json

The package is the first path segment; it and its sibling dependencies are copied,
but only its tests run. Parameterised rather than copied a third time --
`step2/mutate.py` already exists as a sibling because step2 is another session's,
and two copies is the limit.

Same discipline as `step2/mutate.py`, and deliberately a sibling rather than an
import: `step2/` is owned by another session and this one does not edit it.
The differences are the target directory and that the interpreter comes from
`sys.executable` instead of a hardcoded venv, because `verifiers` is not in
`.venv-tok` and a committed script must not point at a path under ~/scratch.

Fresh copy per mutation + PYTHONDONTWRITEBYTECODE=1: a byte-length-identical
mutation restored within the same second leaves identical mtime AND size, so
Python would keep executing the cached .pyc.
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from process_watchdog import run_bounded
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


# Packages the targets and their tests import. `ptc/compare.py` needs `ledger`,
# and the SQL tests need `bench`. Missing either makes collection fail, not a
# mutant die. Include the target only once when it is one of these packages.
SIBLINGS = ("ptc", "ledger", "bench")


def fresh(pkg: str) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix=f"mut.{pkg}."))
    for name in dict.fromkeys((pkg, *SIBLINGS)):
        shutil.copytree(REPO / name, d / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(REPO / "process_watchdog.py", d / "process_watchdog.py")
    return d


SUITE_TIMEOUT = 300.0
"""Seconds one mutated suite may take before it is killed and counted as dead.

Required, not defensive. Mutating away an execution bound (`ptc/runtime.py`'s deadline
tracer) makes the suite's own `while True` test run forever, so an untimed harness
waits on the exact defect it was built to detect. A hung suite is a killed mutant --
it certainly did not pass -- but it has to be *recorded* as one rather than waited on.
"""


def run(d: pathlib.Path, pkg: str):
    """Bound the suite and its original process group, including after leader exit."""
    argv = [sys.executable, "-m", "pytest", f"{pkg}/", "-q", "--no-header",
            "-p", "no:cacheprovider"]
    try:
        return run_bounded(
            argv, cwd=d, timeout=SUITE_TIMEOUT, env={**ENV, "PYTHONPATH": str(d)},
        )
    except subprocess.TimeoutExpired as exc:
        notes = "".join(f"\nWATCHDOG: {note}\n" for note in getattr(exc, "__notes__", ()))
        return subprocess.CompletedProcess(
            argv, 124, (exc.stdout or "") +
            f"\nHUNG: suite exceeded {SUITE_TIMEOUT}s\nFAILED (hung)::timeout",
            (exc.stderr or "") + notes,
        )


def main() -> int:
    target = sys.argv[1]
    if "/" not in target:
        sys.exit(f"name the target relative to the repo root, e.g. ptc/{target}")
    pkg, _, filename = target.partition("/")
    muts = json.load(sys.stdin)
    base = run(fresh(pkg), pkg)
    if base.returncode:
        print("FRESH BASELINE NOT GREEN:\n" + (base.stdout + base.stderr)[-2000:])
        return 2
    print("baseline:", base.stdout.strip().splitlines()[-1], "\n", flush=True)
    print(f"{'mutation':46} | verdict")
    print("-" * 82)
    survivors = []
    invalid = []
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
            verdict = "*** SURVIVED ***"
        elif r.returncode == 1:
            verdict = "died"
        elif r.returncode == 124:
            verdict = "died (timeout)"
            for line in r.stderr.splitlines():
                if line.startswith("WATCHDOG: "):
                    print(line, flush=True)
        else:
            invalid.append(name)
            print(f"{name:46} | INVALID pytest exit {r.returncode}", flush=True)
            print((r.stdout + r.stderr)[-2000:])
            continue
        killed = [l.split("::")[-1].split()[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        n_failed = len(killed)
        print(f"{name:46} | {verdict:16} "
              f"{f'{n_failed} test(s), e.g. ' + killed[0] if killed else ''}")
    print("-" * 82)
    print("survivors:", survivors if survivors else "none")
    print("invalid:", invalid if invalid else "none")
    return 2 if invalid else (1 if survivors else 0)


if __name__ == "__main__":
    sys.exit(main())
