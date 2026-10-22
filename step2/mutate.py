#!/usr/bin/env python3
"""Mutation harness for Step 2. Run from the repo root:

    python step2/mutate.py verdict.py <<'JSON'
    [["name", "old text", "new text"], ...]
    JSON

Committed, unlike Step 1's copy under the ignored `.superpowers/sdd/`. The
README claims 46 mutants and zero survivors; a claim that cannot be re-run
from a clone is the kind of unfalsifiable green this project keeps finding.

Same discipline as Step 1's: fresh copy per mutation + PYTHONDONTWRITEBYTECODE=1.
A byte-length-identical mutation restored within the same second leaves
identical mtime AND size, so Python keeps executing the cached .pyc.
`-p no:cacheprovider` disables pytest's cache, not Python's.

"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]

# The repo-local venv, not an absolute path outside the clone. The previous
# value pointed at `~/.venv-tok/bin/python`, which does not exist here any
# more, so every invocation died in subprocess with FileNotFoundError before
# the baseline ran — the exact unfalsifiable green this file's docstring says
# it exists to prevent. Falls back to the current interpreter.
_VENV = REPO / ".venv-ptc" / "bin" / "python"
PY = str(_VENV) if _VENV.exists() else sys.executable
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1"}


def fresh() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="mut2."))
    shutil.copytree(REPO / "step2", d / "step2", ignore=shutil.ignore_patterns("__pycache__"))
    return d


def run(d: pathlib.Path):
    return subprocess.run(
        [PY, "-m", "pytest", "step2/", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=d, capture_output=True, text=True, env={**ENV, "PYTHONPATH": str(d / "step2")},
    )


def main() -> int:
    target = sys.argv[1]
    muts = json.load(sys.stdin)
    base = run(fresh())
    if base.returncode:
        print("FRESH BASELINE NOT GREEN:\n" + (base.stdout + base.stderr)[-1500:])
        return 2
    print("baseline:", base.stdout.strip().splitlines()[-1], "\n")
    print(f"{'mutation':38} | verdict")
    print("-" * 74)
    survivors = []
    invalid = []
    for name, old, new in muts:
        d = fresh()
        f = d / "step2" / target
        s = f.read_text()
        if s.count(old) != 1:
            print(f"{name:38} | ANCHOR x{s.count(old)} (not unique)")
            survivors.append(name + " [unverified]")
            continue
        f.write_text(s.replace(old, new, 1))
        r = run(d)
        if r.returncode == 0:
            survivors.append(name)
            verdict = "*** SURVIVED ***"
        elif r.returncode == 1:
            verdict = "died"
        else:
            invalid.append(name)
            print(f"{name:38} | INVALID pytest exit {r.returncode}")
            print((r.stdout + r.stderr)[-1500:])
            continue
        killed = [l.split("::")[-1].split()[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        print(f"{name:38} | {verdict:16} {killed[0] if killed else ''}")
    print("-" * 74)
    print("survivors:", survivors if survivors else "none")
    print("invalid:", invalid if invalid else "none")
    return 2 if invalid else (1 if survivors else 0)


if __name__ == "__main__":
    sys.exit(main())
