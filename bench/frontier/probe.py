"""The frontier probe: MEASURE a per-task solve-rate band and emit the TRAIN lane's
manifest. Nothing in this module invents a number.

**Why this file exists instead of a committed `manifest.json`.** The TRAIN lane's §344
gate (`train/guards.py:frontier_taskset_status`) reads `bench/frontier/manifest.json` and
refuses to let the GRPO pipeline run until it conforms. Two of its five fields,
`solve_rate_min` and `solve_rate_max`, are *measurements on the policy being trained*
(`unsloth/Qwen3-0.6B`). This lane is barred from running them: no GPU, no relay runs, no
paid API calls, and no measurement whose result would need the unsigned amendment.

Writing a plausible band into that file by hand would fabricate the exact measurement the
gate exists to verify, and would open the gate so the pipeline could spend money on
numbers nobody took. **So the manifest is absent, the gate stays shut, and that is the
correct state.** This module is the one authorized command that changes it.

**The quantity the gate needs is not the quantity the frontier-band argument supplies.**
`docs/bench-taskset.md` §2 estimates ~25% EX for an untrained 0.6B from a published
aggregate. That is a MARGINAL accuracy over a corpus. The gate reads a PER-TASK solve
rate `p_i = successes_i / G`, and the two come apart completely:

    composition at marginal EX 0.25           mean dead-group fraction (G=4)
    every task p=0.25                                      0.320
    p in {0.10, 0.25, 0.40}                                0.378
    25% of tasks p=1.0, 75% p=0.0                          1.000

All three are indistinguishable as a marginal; only the first is trainable. A bimodal
corpus produces a dead group on essentially every task while reporting a perfectly healthy
25%. **No amount of arithmetic on a published marginal can stand in for this probe.**

**What `solve_rate_min` / `solve_rate_max` mean here.** The raw min and max of per-task
rates over any real suite are 0.0 and 1.0 — some task is never solved, some always is —
which the gate's strict `(0, 1)` bounds refuse outright. So the manifest describes the
RETAINED FRONTIER SUBSET: tasks whose measured rate clears the dead-group ceiling, with
`n_tasks` as the count that survived. `probe()` also returns the pre-filter candidate count
and the retention rate, because those are the numbers that actually carry information once
the band is conformant by construction — see `docs/bench-taskset.md` §9.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bench.score import execution_accuracy, extract_sql
from bench.task import SqlTask

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# G and the ceiling are the TRAIN lane's, restated here only as defaults so this module
# is runnable; `probe()` takes both as arguments and the emitted manifest records what was
# actually used. The expression is the zero-advantage fraction p**G + (1-p)**G.
DEFAULT_G = 4
DEFAULT_DEAD_CEILING = 0.60


def dead_group_fraction(p: float, g: int = DEFAULT_G) -> float:
    """Fraction of GRPO groups with zero advantage at per-task solve rate `p`.

    `p**g + (1-p)**g`: a group gives no gradient when all `g` samples agree, which happens
    when all succeed or all fail. Maximal at both ends, minimal at `p = 0.5`.
    """
    return p ** g + (1 - p) ** g


def trainable_band(ceiling: float = DEFAULT_DEAD_CEILING,
                   g: int = DEFAULT_G) -> tuple[float, float]:
    """The `(lo, hi)` solve-rate interval whose dead-group fraction clears `ceiling`.

    Derived by bisection rather than stated, so changing `g` or the ceiling moves the band
    instead of silently disagreeing with a hardcoded pair. At the defaults this returns
    approximately `(0.1200, 0.8800)`, which matches the TRAIN lane's stated band.
    """
    if not 0.0 < ceiling < 1.0:
        raise ValueError(f"ceiling must be in (0, 1), got {ceiling}")
    lo, hi = 0.0, 0.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if dead_group_fraction(mid, g) > ceiling:
            lo = mid
        else:
            hi = mid
    return hi, 1.0 - hi


@dataclass
class ProbeResult:
    """What the probe measured. `manifest()` narrows this to the five gate keys."""

    policy: str
    g: int
    dead_ceiling: float
    band_lo: float
    band_hi: float
    rates: dict[str, float]
    """Per-task solve rate, task name -> successes / g. Every probed task, retained or
    not, so the discarded ones stay auditable."""
    retained: list[str] = field(default_factory=list)
    void: dict[str, str] = field(default_factory=dict)
    compare: str = "set"
    """The result-set comparison the rates were scored under, recorded in the manifest."""
    """Tasks excluded because the TASK was defective (a gold that will not run), keyed to
    the status that said so. Never counted as a solve rate of 0 -- a defective task is not
    the policy failing."""

    @property
    def n_candidates(self) -> int:
        return len(self.rates)

    @property
    def n_tasks(self) -> int:
        return len(self.retained)

    @property
    def retention(self) -> float:
        return self.n_tasks / self.n_candidates if self.n_candidates else 0.0

    @property
    def solve_rate_min(self) -> float | None:
        return min((self.rates[n] for n in self.retained), default=None)

    @property
    def solve_rate_max(self) -> float | None:
        return max((self.rates[n] for n in self.retained), default=None)

    @property
    def mean_dead_fraction(self) -> float:
        """Mean zero-advantage fraction over the RETAINED set -- the number that says how
        much of a training run's gradient signal actually survives."""
        if not self.retained:
            return 1.0
        return sum(dead_group_fraction(self.rates[n], self.g)
                   for n in self.retained) / self.n_tasks

    def report(self) -> dict:
        """Lossless diagnostic fields, separate from the gate's manifest."""
        return asdict(self)

    def manifest(self, amendment: str) -> dict:
        """The five keys the gate reads, plus the measurement context it does not.

        `amendment` is supplied by the caller and is NOT defaulted: it has to name a
        signed amendment in `docs/pre-registration.md`, and this module has no business
        guessing which one. The gate validates it; nothing here writes that file.
        """
        if self.solve_rate_min is None:
            raise ValueError(
                "no task's measured solve rate clears the dead-group ceiling "
                f"{self.dead_ceiling} at G={self.g} -- band "
                f"({self.band_lo:.4f}, {self.band_hi:.4f}). Refusing to emit a manifest: "
                "an empty frontier is a finding about the taskset, not a file to write.")
        return {
            # --- the five keys train/guards.py:frontier_taskset_status requires ---
            "policy": self.policy,
            "pre_registration_amendment": amendment,
            "n_tasks": self.n_tasks,
            "solve_rate_min": self.solve_rate_min,
            "solve_rate_max": self.solve_rate_max,
            # --- context the gate ignores and a reader needs ---
            "measurement": {
                "g": self.g,
                "dead_ceiling": self.dead_ceiling,
                "trainable_band": [self.band_lo, self.band_hi],
                "n_candidates": self.n_candidates,
                "retention": self.retention,
                "mean_dead_fraction": self.mean_dead_fraction,
                "n_void_tasks": len(self.void),
                "scorer": "bench.score.execution_accuracy",
                "compare": self.compare,
            },
        }


def probe(tasks: Sequence[SqlTask],
          generate: Callable[[SqlTask], str],
          *, policy: str, g: int = DEFAULT_G,
          dead_ceiling: float = DEFAULT_DEAD_CEILING,
          compare: str = "set",
          timeout_s: float = 30.0) -> ProbeResult:
    """Sample each task `g` times and measure its solve rate.

    `generate(task) -> str` is the policy. It is injected rather than imported so this
    function is testable offline with a deterministic stand-in, and so that running it
    against a real model is an explicit, authorized act by the caller.

    Extraction is applied here (`bench.score.extract_sql`), per the integration rule in
    `docs/bench-taskset.md` §3.5: the scorer does not unwrap fenced output, and skipping
    extraction would score every fenced prediction a syntax error and understate the
    policy -- which would look exactly like a frontier-band problem while not being one,
    and would shut this gate for the wrong reason.

    `compare` defaults to `"set"`, the value `train/ex_reward.py` trains on. It read
    `"multiset"` until 2026-10-20, left behind when `bench/score.py`'s default moved to
    `"set"` on 2026-10-12: the frontier would have retained tasks by a stricter reward than
    the one the run optimises, so the manifest's band would describe a different reward.

    A task whose gold does not run is recorded in `void` and given NO solve rate. Scoring
    it 0 would push it below the band and discard it as "too hard for the policy", which
    is a lie about a defective task.
    """
    if g < 2:
        raise ValueError(f"g must be at least 2 for a group to have variance, got {g}")
    names: set[str] = set()
    for t in tasks:
        if t.name in names:
            raise ValueError(f"duplicate candidate name: {t.name!r}")
        names.add(t.name)
    lo, hi = trainable_band(dead_ceiling, g)
    res = ProbeResult(policy=policy, g=g, dead_ceiling=dead_ceiling,
                      band_lo=lo, band_hi=hi, rates={}, compare=compare)
    for t in tasks:
        wins = 0
        voided = ""
        for _ in range(g):
            r = execution_accuracy(extract_sql(generate(t)), t,
                                   compare=compare, timeout_s=timeout_s)
            if not r.valid:
                voided = r.status
                break
            wins += int(r.score == 1.0)
        if voided:
            res.void[t.name] = voided
            continue
        res.rates[t.name] = wins / g
    res.retained = [n for n, p in res.rates.items()
                    if dead_group_fraction(p, g) <= dead_ceiling]
    return res


def write_report(result: ProbeResult, path: Path | str) -> Path:
    """Write diagnostics to an explicit destination, never the canonical manifest."""
    path = Path(path)
    if (path.resolve() == MANIFEST_PATH.resolve()
            or (path.exists() and MANIFEST_PATH.exists()
                and path.samefile(MANIFEST_PATH))):
        raise ValueError("a diagnostic report cannot overwrite the canonical manifest")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.report(), indent=2) + "\n")
    return path


def write_manifest(result: ProbeResult, amendment: str,
                   path: Path | str = MANIFEST_PATH) -> Path:
    """Write the manifest the gate reads. Fails rather than writing an empty frontier."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.manifest(amendment), indent=2) + "\n")
    return path


def render(result: ProbeResult) -> str:
    """Human-readable probe summary, for the report that accompanies a measurement."""
    lines = [
        f"frontier probe -- policy {result.policy}, G={result.g}, "
        f"dead-group ceiling {result.dead_ceiling}",
        f"trainable band ({result.band_lo:.4f}, {result.band_hi:.4f}) "
        f"-- derived from the ceiling at this G, not stated",
        "",
        f"  probed            {result.n_candidates + len(result.void):>5}",
        f"  void (bad gold)   {len(result.void):>5}",
        f"  measured          {result.n_candidates:>5}",
        f"  retained          {result.n_tasks:>5}   retention "
        f"{result.retention:.1%}",
    ]
    if result.n_tasks:
        lines += [
            f"  band              [{result.solve_rate_min:.3f}, "
            f"{result.solve_rate_max:.3f}]",
            f"  mean dead-group   {result.mean_dead_fraction:.3f}",
            "",
            "The band is conformant BY CONSTRUCTION -- tasks outside it were discarded.",
            "The numbers that carry information are `retained` and `retention`: they say",
            "how much of the drawn suite is trainable at all. A high retention means the",
            "taskset sits on the policy's frontier; a low one means most of it is",
            "saturated or uniformly failing and the suite needs redrawing, not retrying.",
        ]
    else:
        lines += ["", "NO task cleared the ceiling. The taskset is not on this policy's",
                  "frontier; no manifest will be written."]
    return "\n".join(lines)
