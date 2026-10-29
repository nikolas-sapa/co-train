"""Suite construction and the effective-n report.

Two jobs, kept together because both are about SHAPES WITHIN TIER and neither makes
sense without the other: `select()` builds a suite stratified over shapes, and `report()`
states what that suite's shape inventory can and cannot detect.

`report()` follows the convention `ledger/generate.py:report()` established, and for the
same reason. That report exists because "underpowered" is a vibe until it is a number.
Its structure -- shape count, replicate count, the `shapes / rho` ceiling, and what n
that ceiling can reach -- is reproduced here with one addition that the `ledger` report
did not need: the ratio of QUESTIONS to SHAPES, printed first, because BIRD's 1534
questions are the exact quantity a reader will mistake for n.

The arithmetic, stated once:

- A taskset's nominal n is its question count.
- Replicates of a shape are correlated, so they do not each carry a full task of
  information. With within-shape correlation `rho`, the effective n is bounded by
  `shapes / rho`, whatever the question count is.
- A required n for an effect comes from `ptc/paired.py:power_pairs`, the project's own
  power function -- imported, not reimplemented, so that a second implementation cannot
  disagree with the one that adjudicates runs.
- Therefore the decisive number is `rho_max = shapes / n_required`: **the largest
  within-shape correlation the tier survives.** Above it, no corpus size reaches the
  effect. For the dead `ledger` taskset that number was `9 / 61 = 0.1475`, and the
  asymptote is what killed it.
"""

from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from functools import lru_cache

from bench.task import TIERS, SqlTask

# `ptc/paired.py` is this project's power function and the tool that adjudicates runs.
# Imported rather than reimplemented: a second power calculation that disagreed with the
# adjudicator would be a defect that only showed up in a disagreement nobody could
# referee. `ptc/metrics.py` (its only dependency) is stdlib-only, so this import stays
# offline and needs no `verifiers`.
from ptc.paired import power_pairs


@lru_cache(maxsize=None)
def _need(delta: float, discordance: float) -> int | None:
    """Memoised `power_pairs`. The search walks n upward summing binomial terms and
    costs the better part of a second per call; `report()` makes twelve of them and the
    tests call `report()` four times, which was 80s of a 90s suite. Cached HERE rather
    than in `ptc/paired.py`, which this lane must not modify."""
    return power_pairs(delta, discordance)

# Each delta is a pre-registered quantity, cited rather than chosen here:
#   0.05  -- a round floor, below the project's own target, shown to bound the problem.
#   0.068 -- `docs/pre-registration.md` §3's APEX-end target, +6.8 pp.
#   0.10  -- a round figure between the two live targets.
#   0.25  -- A6/N1's predicted full-scan effect, ">= 25 pp".
DELTAS = (0.05, 0.068, 0.10, 0.25)

# Correlations the ceiling is tabulated at. `ledger/generate.py:report()` uses exactly
# these, and keeping them identical is what lets a reader compare the two instruments'
# ceilings without converting anything.
RHOS = (0.2, 0.3, 0.5, 0.8)

# The frontier band `docs/bench-taskset.md` argues this instrument sits in. A 0/1 reward
# needs tasks the policy SOMETIMES solves; outside this band the groups have no variance
# and so no advantage, which is both saturation (p->1) and uniform failure (p->0).
FRONTIER_BAND = (0.20, 0.80)


def _shape_of(task: SqlTask, granularity: str) -> str:
    if granularity == "fine":
        return task.shape
    if granularity == "coarse":
        return task.coarse_shape
    raise ValueError(f"granularity must be 'fine' or 'coarse', got {granularity!r}")


def discordance_from_band(p: float) -> float:
    """Discordance rate implied by two arms at marginal success rate `p`.

    `2 * p * (1 - p)`, the probability two INDEPENDENT Bernoulli(p) draws disagree.

    **This is the optimistic bound and it is reported as such.** Real paired arms are
    positively correlated -- both fail the genuinely hard tasks and both pass the easy
    ones -- which lowers the discordance rate, and a lower discordance rate means MORE
    paired tasks are needed, not fewer. So every `n` derived from this is a FLOOR on the
    requirement, never an estimate of it. `report()` prints a correlated case alongside
    it for that reason.
    """
    return 2 * p * (1 - p)


def select(tasks: list[SqlTask], per_tier: dict[str, int] | int, *,
           seed: int = 0, granularity: str = "fine") -> list[SqlTask]:
    """Stratified seeded draw over shapes within tier.

    Follows `ledger/generate.py:select()`'s R7 convention, including the part that
    convention exists to prevent: **the seed decides order, not the alphabet.** Shapes
    are shuffled before the draw, because iterating them sorted made `ledger`'s first
    selector return 30 full-scan tasks and zero cheap ones -- every `agg:` shape sorts
    ahead of every `read:` shape, so a sorted walk exhausted one tier before reaching
    the other. The same hazard is live here: every `t1 ...` shape sorts ahead of every
    `t2 ...` shape, so a sorted draw would return a suite of single-table queries.

    Stratified twice over, and both halves matter:

    - **Within tier**, because `ptc/paired.py` splits on tier and the interaction A6
      names is the difference of the tiers' paired deltas. A draw that returns one tier
      has no interaction to compute.
    - **Within shape**, one task per shape before any shape gets a second, because
      replicates are correlated and raise nominal n without raising effective n. Drawing
      20 questions that happen to be 3 shapes is the replicate trap, committed by the
      selector instead of by the corpus.

    `per_tier` is a count per tier name, or one int applied to every tier. Asking for
    more tasks than a tier has shapes is allowed and is not silently capped -- it draws
    second and third replicates, which is sometimes what a run wants. The report is what
    says what that costs.

    Pure: touches no database. Run `bench.score.validate_golds()` on the result before
    measuring, so a defective gold is dropped with disclosure rather than voiding a run.
    """
    want = ({t: per_tier for t in TIERS} if isinstance(per_tier, int)
            else dict(per_tier))
    unknown = set(want) - set(TIERS)
    if unknown:
        raise ValueError(f"unknown tier(s) {sorted(unknown)}, expected {TIERS}")

    pool: dict[tuple[str, str], list[SqlTask]] = defaultdict(list)
    for t in tasks:
        pool[(t.tier, _shape_of(t, granularity))].append(t)
    rng = random.Random(seed)
    for key in sorted(pool):
        # Sorted first, so the shuffle is a pure function of the seed rather than of
        # whatever order the corpus file happened to use.
        pool[key].sort(key=lambda t: t.name)
        rng.shuffle(pool[key])

    chosen: list[SqlTask] = []
    for tier in TIERS:
        n = want.get(tier, 0)
        if n <= 0:
            continue
        shapes = sorted(s for (ti, s) in pool if ti == tier)
        if not shapes:
            continue
        rng.shuffle(shapes)              # seed decides order, not the alphabet
        got, depth = 0, 0
        while got < n:
            progressed = False
            for s in shapes:
                if got >= n:
                    break
                bucket = pool[(tier, s)]
                if len(bucket) > depth:
                    chosen.append(bucket[depth])
                    got += 1
                    progressed = True
            if not progressed:
                break                    # tier exhausted; the report says what that means
            depth += 1
    return chosen


def inventory(tasks: list[SqlTask], granularity: str = "fine") -> dict[str, dict]:
    """Per-tier shape inventory. The table `report()` prints and the tests derive from."""
    out: dict[str, dict] = {}
    for tier in TIERS:
        group = [t for t in tasks if t.tier == tier]
        if not group:
            continue
        counts = Counter(_shape_of(t, granularity) for t in group)
        out[tier] = {
            "questions": len(group),
            "shapes": len(counts),
            "replicates": counts,
            "max_replicates": max(counts.values()),
            "singletons": sum(1 for v in counts.values() if v == 1),
        }
    return out


def report(tasks: list[SqlTask], out=sys.stdout) -> None:
    """Print the shape inventory and the effective-n ceiling per difficulty tier.

    Refuses to pool annotated and derived tiers: BIRD's `difficulty` is a human label and
    Spider's tier is a structural heuristic, so one table row covering both would report
    a quantity nobody defined. Mixed input gets one block per source.
    """
    def w(line: str = "") -> None:
        print(line, file=out)

    by_source: dict[str, list[SqlTask]] = defaultdict(list)
    for t in tasks:
        by_source[t.tier_source].append(t)

    for tier_source in sorted(by_source):
        group = by_source[tier_source]
        corpora = ", ".join(sorted({t.source for t in group}))
        fine = inventory(group, "fine")
        coarse = inventory(group, "coarse")
        n_fine = len({t.shape for t in group})
        n_coarse = len({t.coarse_shape for t in group})

        w(f"=== {corpora}  ({len(group)} questions, tiers {tier_source}) ===")
        w()
        w(f"{len(group)} questions over {n_fine} fine shapes "
          f"({len(group) / n_fine:.1f} replicates per shape) and {n_coarse} coarse "
          f"shapes ({len(group) / n_coarse:.1f} per shape)")
        w("A QUESTION COUNT IS NOT AN n. Replicates of a shape are correlated, so the")
        w("question count above is the quantity most likely to be mistaken for this")
        w("instrument's n -- it is not. Only the shape counts bound effective n; a")
        w("larger corpus of the same shapes raises replicates and nothing else.")
        w()

        hdr = f"{'tier':<14}{'questions':>10}{'fine':>7}{'coarse':>8}{'reps/fine':>11}{'1-off':>7}"
        w(hdr)
        w("-" * len(hdr))
        for tier in TIERS:
            if tier not in fine:
                continue
            f, c = fine[tier], coarse[tier]
            w(f"{tier:<14}{f['questions']:>10}{f['shapes']:>7}{c['shapes']:>8}"
              f"{f['questions'] / f['shapes']:>11.1f}{f['singletons']:>7}")
        w("-" * len(hdr))
        w(f"{'TOTAL':<14}{len(group):>10}{n_fine:>7}{n_coarse:>8}"
          f"{len(group) / n_fine:>11.1f}"
          f"{sum(f['singletons'] for f in fine.values()):>7}")
        w("  `1-off` counts shapes with exactly one question: those carry a full task of")
        w("  information each, and they are the part of the corpus that is not replicated.")
        w()

        w("effective-n ceiling per tier -- shapes / rho, the limit no corpus size")
        w("or question count can pass, because replicates of a shape are correlated:")
        w()
        tiers_present = [t for t in TIERS if t in fine]
        w(f"  {'rho':>6}" + "".join(f"{t:>14}" for t in tiers_present)
          + "   (fine shapes)")
        for rho in RHOS:
            w(f"  {rho:>6.1f}"
              + "".join(f"{fine[t]['shapes'] / rho:>14.0f}" for t in tiers_present))
        w(f"  {'rho':>6}" + "".join(f"{t:>14}" for t in tiers_present)
          + "   (coarse shapes)")
        for rho in RHOS:
            w(f"  {rho:>6.1f}"
              + "".join(f"{coarse[t]['shapes'] / rho:>14.0f}" for t in tiers_present))
        w("  The true ceiling lies between the two granularities. Fine splits on every")
        w("  clause difference and so overstates shapes; coarse splits on structural")
        w("  family only and so understates them.")
        w()

        lo, hi = FRONTIER_BAND
        mid = (lo + hi) / 2
        w(f"what that n can detect, at 80% power and alpha 0.05. Discordance is derived")
        w(f"from the frontier band ({lo:.0%}-{hi:.0%}) as 2p(1-p), the rate two")
        w(f"INDEPENDENT arms at marginal p disagree:")
        w()
        for label, p, factor in (
            (f"p={lo:.2f} (band floor)", lo, 1.0),
            (f"p={mid:.2f} (band centre)", mid, 1.0),
            ("correlated arms, half that discordance", mid, 0.5),
        ):
            disc = discordance_from_band(p) * factor
            w(f"  discordance {disc:.3f}  -- {label}")
            for delta in DELTAS:
                need = _need(delta, disc)
                need_s = f"{need:>5} paired tasks" if need else "   not on a runnable n"
                verdicts = []
                for tier in tiers_present:
                    s = fine[tier]["shapes"]
                    if need is None:
                        verdicts.append(f"{tier}: n/a")
                    else:
                        rho_max = s / need
                        verdicts.append(
                            f"{tier}: rho<{min(rho_max, 1.0):.3f}"
                            + ("" if rho_max < 1.0 else " (any rho)"))
                w(f"    delta {delta:+.3f}  {need_s}   "
                  + "  ".join(verdicts))
            w()
        w("  `rho<X` is the DECISIVE number: the largest within-shape correlation that")
        w("  tier survives for that effect. Above it the required n exceeds shapes/rho")
        w("  and no corpus size reaches the effect -- the vertical asymptote that killed")
        w("  `ledger`, whose cheap tier had 9 shapes against 61 needed, so rho < 0.148.")
        w("  Every n here is a FLOOR: the independence assumption behind 2p(1-p) is the")
        w("  optimistic direction, and positively correlated arms need more, not fewer.")
        w()

        w("replicate distribution over fine shapes -- how much of the corpus is")
        w("correlated with something else in it:")
        buckets = [(1, 1, "1"), (2, 2, "2"), (3, 5, "3-5"), (6, 10, "6-10"),
                   (11, 10 ** 9, "11+")]
        reps = Counter(_shape_of(t, "fine") for t in group)
        w(f"  {'replicates':<12}{'shapes':>8}{'questions':>11}")
        for lo_b, hi_b, label in buckets:
            shp = [s for s, v in reps.items() if lo_b <= v <= hi_b]
            w(f"  {label:<12}{len(shp):>8}{sum(reps[s] for s in shp):>11}")
        w()

        w(f"{'most replicated fine shapes':<52}{'questions':>10}")
        w("-" * 62)
        for s, v in reps.most_common(12):
            w(f"{s[:51]:<52}{v:>10}")
        w("-" * 62)
        w(f"{'shapes not shown':<52}{len(reps) - min(12, len(reps)):>10}")
        w()


def main(argv: list[str]) -> int:
    """`python -m bench.suite <corpus-root> [spider-root]`, or no argument for the
    committed offline fixture."""
    from bench.loader import load_bird, load_spider

    if len(argv) > 1:
        tasks = load_bird(argv[1])
        if len(argv) > 2:
            tasks = tasks + load_spider(argv[2])
    else:
        import tempfile

        from bench import fixture
        tmp = tempfile.mkdtemp()
        tasks = load_bird(fixture.materialize(tmp))
        print("(no corpus path given -- reporting on the committed offline fixture)\n")
    report(tasks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
