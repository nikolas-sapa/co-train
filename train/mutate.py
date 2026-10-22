#!/usr/bin/env python3
"""Mutation harness for the training lane. Run from the repo root:

    .venv-ptc/bin/python train/mutate.py

Breaks each guard and each abort criterion in a fresh copy of the tree, runs
`pytest train`, and reports whether any test died. A surviving mutant is a guard
nobody is checking.

**This exists because a green test proves nothing until it has been seen red.**
This repo has shipped a guard that passed because its target was unreachable, 56
mutants that missed a fail-closed defect, and 612 tests asserting a fictional
CLI. The table below is the record, re-runnable from a clone -- a claim that
cannot be re-run is the kind of unfalsifiable green the project keeps finding.

Same discipline as `step2/mutate.py`: fresh copy per mutation plus
`PYTHONDONTWRITEBYTECODE=1`, because a byte-length-identical mutation restored
within the same second leaves identical mtime *and* size, so Python keeps
executing the cached `.pyc`. `-p no:cacheprovider` disables pytest's cache, not
Python's.

The copy carries `ptc/`, `step2/` and `docs/pre-registration.md` as well as
`train/`, because the invariants deliberately read their values out of those
files instead of restating them.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
_VENV = REPO / ".venv-ptc" / "bin" / "python"
PY = str(_VENV) if _VENV.exists() else sys.executable
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
COPY_DIRS = ("train", "ptc", "step2", "bench")
"""Every package the target's tests import, not just the one under mutation.

`bench` was missing until 2026-10-19, and `train/ex_reward.py` imports
`bench.score` and `bench.task` at module scope, so four mutants died at
*collection* with `ModuleNotFoundError` -- counted as killed while testing
nothing. This is the defect `ptc/mutate.py` had on 2026-10-01 in the same shape:
a sandbox that copies only its own package turns every mutant green-dead. The
list is asserted against the import graph in `test_train.py` rather than
maintained by memory."""
COPY_FILES = ("docs/pre-registration.md",)

# name, file under train/ or elsewhere in the copy, unique anchor, replacement.
MUTATIONS: list[tuple[str, str, str, str]] = [
    # ---- the stack floor
    ("stack: floor never checked", "train/guards.py",
     "elif _parse_version(unsloth) < UNSLOTH_FLOOR:", "elif False:"),
    ("stack: floor compared as a string", "train/guards.py",
     "_parse_version(unsloth) < UNSLOTH_FLOOR", "unsloth < floor"),
    ("stack: trl pin not checked", "train/guards.py",
     "elif _parse_version(trl)[: len(TRL_PIN)] != TRL_PIN:", "elif False:"),
    ("stack: transformers ceiling not checked", "train/guards.py",
     "elif _parse_version(transformers)[:1] >= (TRANSFORMERS_MAJOR_CEILING,):", "elif False:"),
    ("stack: require_stack never raises", "train/guards.py",
     "        raise StackError(", "        pass; StackError("),
    # ---- invariant 1
    ("inv1: tool count not checked", "train/guards.py",
     "    if len(tools) != 1:", "    if False:"),
    ("inv1: tool name not checked", "train/guards.py",
     "    if name != THE_TOOL:", "    if False:"),
    ("inv1: trained arm offers a different tool", "train/grpo_ptc.py",
     '        "name": "run_program",', '        "name": "run_programs",'),
    # ---- invariant 2
    ("inv2: cap not bound to its arms", "train/guards.py",
     "    if cap.arms != trained:", "    if False:"),
    ("inv2: cap below the observed max allowed", "train/guards.py",
     "    if cap.value < binding:", "    if False:"),
    ("inv2: cross-arm cap need not be the global max", "train/guards.py",
     "    if len(trained) > 1 and cap.value != binding:", "    if False:"),
    ("inv2: unknown arm silently accepted", "train/guards.py",
     "    if unknown:", "    if False and unknown:"),
    ("inv2: cap granularity drifts", "train/guards.py",
     "_CAP_GRANULARITY = 1024", "_CAP_GRANULARITY = 2048"),
    ("inv2: observed max drifts", "train/guards.py",
     'OBSERVED_MAX = {"ptc": 2642, "bash": 4258}', 'OBSERVED_MAX = {"ptc": 2642, "bash": 4096}'),
    # ---- invariant 3
    ("inv3: max_turns mismatch allowed", "train/guards.py",
     "    if actual != expected:", "    if False:"),
    ("inv3: silent exhaustion allowed", "train/guards.py",
     "    if not isinstance(text, str) or not text.strip():", "    if False:"),
    ("inv3: refusal may be a tool failure", "train/guards.py",
     "    if hit:", "    if False:"),
    ("inv3: budget never runs out", "train/guards.py",
     "        if self.remaining() <= 0:", "        if False:"),
    ("inv3: refusal never reaches the model", "train/grpo_ptc.py",
     "        refusal = self.budget.consume()", "        refusal = None"),
    # ---- the §344 gate
    ("gate: never raises", "train/guards.py",
     "    if not status.ok:", "    if False:"),
    ("gate: saturated band accepted", "train/guards.py",
     "            if not hi < 1.0:", "            if False:"),
    ("gate: never-solved band accepted", "train/guards.py",
     "            if not 0.0 < lo:", "            if False:"),
    ("gate: off-frontier band accepted", "train/guards.py",
     "                    if frac > ABORT_CEILING:", "                    if False:"),
    ("gate: unsigned amendment accepted", "train/guards.py",
     "    elif not _amendment_is_signed(amendment, root):", "    elif False:"),
    ("gate: missing manifest keys ignored", "train/guards.py",
     "    missing = [k for k in MANIFEST_REQUIRED if k not in manifest]\n    if missing:",
     "    missing = [k for k in MANIFEST_REQUIRED if k not in manifest]\n    if False:"),
    ("gate: preflight skips the gate", "train/grpo_ptc.py",
     "    require_frontier_taskset(root)", "    pass"),
    ("gate: preflight skips the stack", "train/grpo_ptc.py",
     "    require_stack(versions)", "    pass"),
    # ---- criterion A
    ("A: any-step ceiling dead", "train/verdict.py",
     "        if value > ZERO_STD_CEILING:", "        if False:"),
    ("A: fails open on an absent metric", "train/verdict.py",
     "        if not _finite(value):", "        if False:"),
    ("A: short run passes vacuously", "train/verdict.py",
     "MIN_PROBE_STEPS = 5", "MIN_PROBE_STEPS = 0"),
    ("A: taskset_id not required", "train/verdict.py",
     "    if provenance is None or not str(provenance.get", "    if False and not str(provenance.get"),
    ("A: sustained window collapses to one step", "train/verdict.py",
     "            if i - run_start + 1 >= SUSTAINED_WINDOW:", "            if i - run_start + 1 >= 1:"),
    ("A: never-logged metric reads clean (sustained)", "train/verdict.py",
     "    if steps and not any(_finite(v) for _, v in values):", "    if False:"),
    # ---- criterion B
    ("B: monotonic-rise arm dead", "train/verdict.py",
     "and all(b > a for a, b in zip(window, window[1:]))", "and False"),
    ("B: ratio arm dead", "train/verdict.py",
     "        if worst > LOGP_RATIO_MULTIPLE * baseline:", "        if False:"),
    ("B: non-positive baseline not declared", "train/verdict.py",
     "    if baseline <= 0:", "    if False:"),
    ("B: absent metric fails open", "train/verdict.py",
     "telemetry_reasons = reasons if required else notes", "telemetry_reasons = notes"),
    ("B: short run reported as evaluable", "train/verdict.py",
     "    if len(values) < SUSTAINED_WINDOW:", "    if False:"),
    # ---- the step marker shared with step2
    ("marker: train_loss counted as a step", "train/verdict.py",
     '    return [r for r in logs if "loss" in r]', '    return [r for r in logs if "loss" in str(r)]'),
    # ---- the derivation
    ("derivation: only the all-correct tail", "train/dead_group_probe.py",
     "    return p**g + (1.0 - p) ** g", "    return p**g"),
    ("derivation: group of one accepted", "train/dead_group_probe.py",
     "    if g < 2:", "    if False:"),
    ("derivation: probability range unchecked", "train/dead_group_probe.py",
     "    if not 0.0 <= p <= 1.0:", "    if False:"),
    # ---- the probe
    ("probe: live ceiling dead", "train/dead_group_probe.py",
     "        elif value > self.ceiling:", "        elif False:"),
    ("probe: absent metric fails open", "train/dead_group_probe.py",
     "        if not isinstance(value, (int, float)) or isinstance(value, bool):", "        if False:"),
    ("probe: non-binary reward accepted", "train/dead_group_probe.py",
     "    bad = sorted({v for v in values if v not in (0.0, 1.0)})", "    bad = []"),
    ("probe: reward matches a substring", "train/dead_group_probe.py",
     "        out.append(float(given is not None and given == expected.lower()))",
     "        out.append(float(given is not None and expected.lower() in given.lower()))"),
    ("probe: becomes a study", "train/dead_group_probe.py",
     "    if not PROBE_STEPS_MIN <= steps <= PROBE_STEPS_MAX:", "    if False:"),
    ("probe: vllm_mode inherited", "train/dead_group_probe.py",
     '        "vllm_mode": "colocate",', '        "vllm_mode": "server",'),
    ("probe: bf16 instead of fp16", "train/dead_group_probe.py",
     '        "fp16": True,\n        "bf16": False,', '        "fp16": False,\n        "bf16": True,'),
    ("probe: prompts need no answer", "train/dead_group_probe.py",
     '        missing = [k for k in ("prompt", "answer")', '        missing = [k for k in ()'),
    # ---- the cheap step-0 check
    ("step0: floor artifact not flagged", "train/grpo_ptc.py",
     "    if tool_calls >= minimum and tool_failures == 0:", "    if False:"),
    ("step0: program execution stubbed to look fine", "train/grpo_ptc.py",
     '            raise NotImplementedError(\n                "program execution has no task-bound executor',
     '            return "42"\n            raise NotImplementedError(\n                "program execution has no task-bound executor'),
]


def fresh() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="mut-train."))
    for name in COPY_DIRS:
        shutil.copytree(REPO / name, d / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in COPY_FILES:
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, d / name)
    return d


def run(d: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "pytest", "train", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=d, capture_output=True, text=True, env={**ENV, "PYTHONPATH": str(d)},
    )


def main() -> int:
    base = run(fresh())
    if base.returncode:
        print("FRESH BASELINE NOT GREEN:\n" + (base.stdout + base.stderr)[-2000:])
        return 2
    print("baseline:", base.stdout.strip().splitlines()[-1], "\n")
    print(f"{'mutation':46} | verdict")
    print("-" * 96)
    survivors: list[str] = []
    invalid: list[str] = []
    for name, target, old, new in MUTATIONS:
        d = fresh()
        path = d / target
        source = path.read_text()
        if source.count(old) != 1:
            print(f"{name:46} | ANCHOR x{source.count(old)} (not unique)")
            survivors.append(f"{name} [unverified anchor]")
            continue
        path.write_text(source.replace(old, new, 1))
        result = run(d)
        if result.returncode == 0:
            survivors.append(name)
            verdict = "*** SURVIVED ***"
        elif result.returncode == 1:
            verdict = "died"
        else:
            invalid.append(name)
            print(f"{name:46} | INVALID pytest exit {result.returncode}")
            print((result.stdout + result.stderr)[-2000:])
            continue
        killed = [
            line.split("::")[-1].split()[0]
            for line in result.stdout.splitlines()
            if line.startswith("FAILED")
        ]
        print(f"{name:46} | {verdict:16} "
              f"{killed[0] if killed else ''}{f' (+{len(killed) - 1})' if len(killed) > 1 else ''}")
    print("-" * 96)
    print(f"{len(MUTATIONS)} mutants, survivors:", survivors if survivors else "none")
    print("invalid:", invalid if invalid else "none")
    return 2 if invalid else (1 if survivors else 0)


if __name__ == "__main__":
    raise SystemExit(main())
