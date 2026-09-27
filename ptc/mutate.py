#!/usr/bin/env python3
"""Mutation harness for `ptc/`. Run with the interpreter that has `verifiers`:

    ~/scratch/verifiers-spike/.venv/bin/python ptc/mutate.py harness.py <<'JSON'
    [["name", "old text", "new text"], ...]
    JSON

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

DIR = pathlib.Path(__file__).resolve().parent
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def fresh() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="mutptc."))
    shutil.copytree(DIR, d / "ptc", ignore=shutil.ignore_patterns("__pycache__"))
    return d


def run(d: pathlib.Path):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "ptc/", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=d, capture_output=True, text=True, env={**ENV, "PYTHONPATH": str(d / "ptc")},
    )


def main() -> int:
    target = sys.argv[1]
    muts = json.load(sys.stdin)
    base = run(fresh())
    if base.returncode:
        print("FRESH BASELINE NOT GREEN:\n" + base.stdout[-2000:])
        return 2
    print("baseline:", base.stdout.strip().splitlines()[-1], "\n")
    print(f"{'mutation':46} | verdict")
    print("-" * 82)
    survivors = []
    for name, old, new in muts:
        d = fresh()
        f = d / "ptc" / target
        s = f.read_text()
        if s.count(old) != 1:
            print(f"{name:46} | ANCHOR x{s.count(old)} (not unique)")
            survivors.append(name + " [unverified]")
            continue
        f.write_text(s.replace(old, new, 1))
        r = run(d)
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
