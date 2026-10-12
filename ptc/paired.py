"""Paired per-task comparison of two arms' traces.

`compare.py` reports each arm's score with its own unpaired CI. §3 of the
pre-registration decides on whether arms are separable, and with one rollout
per task on the *same* taskset the arms are paired -- so the interval that
matters is the interval on the per-task difference, not two marginal ones.
An unpaired CI here throws away the pairing and is wider than the data.

Usage: python -m ptc.paired <arm-a>/traces.jsonl <arm-b>/traces.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from fractions import Fraction
from math import comb, exp, inf, lgamma, log, log1p

from ptc.metrics import bootstrap_ci


def load(path: str) -> dict[str, float]:
    """Task name -> total reward. Reward lives at traces[i].rewards.<c>.score;
    there is no top-level reward field, which is where an earlier extraction
    silently produced nothing.
    """
    out: dict[str, float] = {}
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            name = d["task"]["data"]["name"]
            score = 0.0
            for tr in d["traces"]:
                for comp in tr["rewards"].values():
                    score += comp["score"] * comp.get("weight", 1.0)
            out[name] = score
    return out


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p from the discordant counts. Binomial sign test
    on b of b+c under p=0.5.

    ponytail: stdlib `comb`, no scipy. Exact is the correct test at these counts,
    and the chi-square approximation is the one that misleads when b+c < 25.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap_interaction(diffs_low: list[float], diffs_high: list[float],
                          iters: int = 2000, alpha: float = 0.05,
                          seed: int = 0) -> tuple[float, float] | None:
    """Percentile CI on `mean(diffs_high) - mean(diffs_low)`.

    Argument ORDER is the difference and the sign depends on it, so callers pass these by
    keyword. The interval is on the interaction as A6 defines it, `full-scan minus cheap`,
    which means `diffs_low` is the CHEAP tier.

    A6 pre-specifies the interaction as "the difference of those two paired deltas", so
    the interval that decides N1 is the interval on that difference -- not either tier's
    own CI, and not the two CI endpoints subtracted. Subtracting marginal endpoints is
    interval arithmetic on quantities that are not independent, and it is both wider than
    this and wrong: it answers "how far apart could these two be if each moved
    adversarially", which is not a confidence statement about their difference.

    The tiers are disjoint sets of tasks, so the two are resampled independently within
    each iteration. Seeded like `metrics.bootstrap_ci`, so a reported interval reproduces
    from the same traces.
    """
    if len(diffs_low) < 2 or len(diffs_high) < 2:
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(iters):
        low = sum(rng.choices(diffs_low, k=len(diffs_low))) / len(diffs_low)
        high = sum(rng.choices(diffs_high, k=len(diffs_high))) / len(diffs_high)
        draws.append(high - low)
    draws.sort()
    return (draws[int((alpha / 2) * iters)],
            draws[min(iters - 1, int((1 - alpha / 2) * iters))])


def _binom_cdf(crit: int, d: int, p: float) -> float:
    """`sum(comb(d, i) * p**(d-i) * (1-p)**i for i in range(crit+1))`, in log space.

    Computed directly, that sum raises `OverflowError: int too large to convert to
    float` for any `d` past ~1030: `comb(d, i)` is an exact big integer and
    multiplying it by a float converts it first, and `comb(10000, 5000)` is ~1e3008
    against a float ceiling of ~1.8e308. `power_pairs` reached that `d` for `delta`
    between 0.02 and 0.04 and crashed -- while `delta` of 0.01 returned None, because
    its lower `hi` bound stopped the search at `d` of 1000 and never got there. The
    band was invisible because every delta the project had ever asked for sat outside
    it (0.25 and 0.068 answer at `d` of 30 and 430).

    Term-by-term recurrence does not fix it: `p**d` underflows to exactly 0.0 at that
    `d`, and a recurrence from 0.0 stays 0.0. Log space with a max-shift is the one
    form that holds both ends. The shift is what keeps `exp` in range; without it the
    individual log-terms are around -700 and exponentiate to 0.
    """
    if p >= 1.0:
        # Every discordant pair favours one arm: only the i=0 term is non-zero and it
        # is 1. Not a degenerate input -- it is the easiest effect to detect, per the
        # docstring below.
        return 1.0
    lp, lq = log(p), log1p(-p)
    lg = lgamma(d + 1)
    terms = [lg - lgamma(i + 1) - lgamma(d - i + 1) + (d - i) * lp + i * lq
             for i in range(crit + 1)]
    top = max(terms, default=-inf)
    if top == -inf:
        return 0.0
    return exp(top) * sum(exp(t - top) for t in terms)


def power_pairs(delta: float, discordance: float, power: float = 0.8,
                alpha: float = 0.05) -> int | None:
    """Paired tasks needed to detect `delta` at `power`, given a discordance rate.

    This exists because "underpowered" is a vibe until it is a number, and the
    pre-registration's own target is numeric (+6.8 pp at the APEX end). Exact McNemar
    is a sign test on the discordant pairs only, so n enters just through how many
    discordant pairs it buys: `n * discordance`, split `p = 0.5 + delta / (2*discordance)`
    one way under the alternative. Searches n upward rather than inverting a normal
    approximation, which is wrong at exactly the counts that matter here.

    Returns None only for inputs that cannot occur: `|delta|` can never exceed the
    discordance rate, since both are computed from the same discordant pairs.

    The boundary `delta == discordance` is NOT such a case -- it means every discordant
    pair favours one arm, which is the *easiest* effect to detect, not an impossible one.
    Six unanimous pairs already give an exact two-sided p of 0.031. Guarding it with
    `p >= 1` reported run 2h's unanimous 2-of-2 as "not detectable at this discordance"
    when the answer was 42 paired tasks.
    """
    if not 0 < discordance <= 1 or delta <= 0:
        return None
    p = 0.5 + delta / (2 * discordance)
    if p > 1:
        return None
    # `crit` depends only on d, not on p, so it is computed once per d and cached. It
    # used to be recomputed inside the search, which for a small delta with moderate
    # discordance meant ~20,000 candidate n and a k-loop of big-integer `comb` calls each
    # -- minutes of work to return a number, during which a redirected stdout stayed at
    # 0 bytes and read as a silent failure. Cached, the same search is milliseconds.
    #
    # `hi` bounds the search: the required n grows as the effect shrinks (1571 at delta
    # 0.05 against 11 at delta 0.5, both at discordance 0.5), so a small delta with a
    # moderate discordance rate exceeds any sane run. When the bound is reached, None is
    # returned deliberately -- the honest answer is "not on a runnable n", and the caller
    # prints `n/a` rather than a number nobody could fund.
    # `crit` depends only on d, and it is monotone in k: growing k toward d/2 moves the
    # discordant split toward even, so the exact two-sided p only grows with k. That makes
    # the largest k clearing alpha a binary search (~13 evaluations) rather than a scan
    # (~d/2 of them, each summing k+1 binomial terms -- O(d^2) per candidate n, which is
    # what made this function take 115s to answer and left a redirected stdout at 0 bytes
    # long enough to read as a silent failure).
    #
    # `hi` bounds the search. The required n grows as the effect shrinks -- 1571 at delta
    # 0.05 against 11 at delta 0.5, both at discordance 0.5 -- so a small delta with a
    # moderate discordance rate exceeds any runnable n. Reaching the bound returns None
    # deliberately: "not on a runnable n" is the honest answer, and the caller prints n/a
    # rather than a number nobody could fund.
    def crit_for(d: int) -> int:
        if d < 2 or mcnemar_exact(0, d) > alpha:
            return -1
        lo, hi_ = 0, d // 2
        while lo < hi_:
            mid = (lo + hi_ + 1) // 2
            if mcnemar_exact(mid, d - mid) <= alpha:
                lo = mid
            else:
                hi_ = mid - 1
        return lo

    crit_cache: dict[int, int] = {}
    hi = 20001 if delta >= 0.02 else 2001
    for n in range(4, hi):
        d = round(n * discordance)
        if d < 2:
            continue
        if d not in crit_cache:
            crit_cache[d] = crit_for(d)
        crit = crit_cache[d]
        if crit < 0:
            continue
        got = _binom_cdf(crit, d, p)
        if got >= power:
            return n
    return None


def rollouts(path: str) -> dict[str, dict]:
    """Task name -> {score, ok, min_calls}.

    `load` above returns scores alone, and that is not enough to adjudicate: a rollout
    that errored has no `rewards`, so it sums to **0.0 and is indistinguishable from a
    genuine wrong answer**. Run 3b wrote all 29 task names on both arms with 10 of bash's
    errored, so the partial-arm guard below could not fire either -- the tool would have
    reported bash 14/29 against PTC 20/29 as a real comparison with ten crashes counted
    as failures. `compare.py` catches this and exits non-zero; this tool did not.

    `min_calls` is the tier key. `pre-registration.md` §8/A6 pre-specifies the comparison
    paired WITHIN tier, because the cheap and full-scan tiers answer opposite questions
    and the marginal score across both averages them away.
    """
    out: dict[str, dict] = {}
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            score = 0.0
            for tr in d["traces"]:
                for comp in tr["rewards"].values():
                    score += comp["score"] * comp.get("weight", 1.0)
            out[d["task"]["data"]["name"]] = {
                "score": score,
                "ok": bool(d.get("ok")),
                "min_calls": d["task"]["data"].get("min_calls"),
            }
    return out


def refuse_voids(name_a: str, ra: dict[str, dict],
                 name_b: str, rb: dict[str, dict]) -> None:
    """A void rollout voids the comparison, per A6. Nothing is salvageable by dropping
    it: the arm that crashed did not fail the task, and scoring it 0.0 is the single
    most flattering thing this tool could do to the other arm."""
    void = [(n, arm) for arm, r in ((name_a, ra), (name_b, rb))
            for n, v in r.items() if not v["ok"]]
    if void:
        per_arm: dict[str, list[str]] = {}
        for n, arm in void:
            per_arm.setdefault(arm, []).append(n)
        lines = [f"  {arm}: {len(ns)} void -- {', '.join(sorted(ns))}"
                 for arm, ns in sorted(per_arm.items())]
        raise SystemExit(
            f"{len(void)} rollout(s) errored, so this comparison is void.\n"
            + "\n".join(lines)
            + "\nAn errored rollout has no rewards and scores 0.0 here, which is NOT the "
              "arm failing the task. Re-run; do not read the table."
        )


def split_tiers(r: dict[str, dict]) -> dict[str, set[str]]:
    """Tier key is `min_calls`: the full-scan tier is the maximum (one call per record,
    `len(RECORDS)`), everything else is cheap. Derived from the data rather than
    hardcoding 40, so a taskset built on a different record count still splits."""
    seen = [v["min_calls"] for v in r.values() if v["min_calls"] is not None]
    if not seen:
        return {"all": set(r)}
    top = max(seen)
    return {
        "cheap": {n for n, v in r.items() if v["min_calls"] != top},
        "full-scan": {n for n, v in r.items() if v["min_calls"] == top},
    }


def paired(a: dict[str, float], b: dict[str, float]) -> dict:
    shared = sorted(set(a) & set(b))
    if not shared:
        raise SystemExit("no shared task names -- are these the same taskset?")
    # An intersection was silently narrowing the comparison. If one arm dies partway
    # through -- which 2g did, and run 1, and 2a-2e -- the surviving tasks still
    # intersect, so this reported `n (paired) 12` on a 29-task taskset and a BROKEN run
    # read as a clean underpowered one. The arms are paired by construction (one rollout
    # per task on a shared taskset, pre-reg §3); unequal sets mean the pairing is gone
    # and no delta computed from them is admissible. Fail closed and name what is
    # missing, rather than average what is left.
    missing_from_a = sorted(set(b) - set(a))
    missing_from_b = sorted(set(a) - set(b))
    if missing_from_a or missing_from_b:
        raise SystemExit(
            "the arms did not run the same tasks, so the pairing is broken and no "
            "paired delta from them is admissible.\n"
            f"  {len(shared)} shared, {len(missing_from_a)} missing from arm A, "
            f"{len(missing_from_b)} missing from arm B\n"
            f"  absent from A: {', '.join(missing_from_a) or 'none'}\n"
            f"  absent from B: {', '.join(missing_from_b) or 'none'}\n"
            "Re-run the arm that died. A partial arm is a void run, not a small one.")
    diffs = [a[t] - b[t] for t in shared]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    return {
        "tasks": shared,
        "diffs": diffs,
        "n": len(shared),
        "mean_a": sum(a[t] for t in shared) / len(shared),
        "mean_b": sum(b[t] for t in shared) / len(shared),
        "delta": sum(diffs) / len(diffs),
        "ci": bootstrap_ci(diffs),
        "a_only": wins,
        "b_only": losses,
        "ties": len(shared) - wins - losses,
        "p": mcnemar_exact(wins, losses),
    }




def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    path_a, path_b = argv[1], argv[2]
    name_a = path_a.split("/")[-2]
    name_b = path_b.split("/")[-2]
    ra, rb = rollouts(path_a), rollouts(path_b)
    refuse_voids(name_a, ra, name_b, rb)
    a = {n: v["score"] for n, v in ra.items()}
    b = {n: v["score"] for n, v in rb.items()}
    r = paired(a, b)

    print(f"{'task':<26}{name_a:>18}{name_b:>18}{'diff':>8}")
    print("-" * 70)
    for t in r["tasks"]:
        print(f"{t:<26}{a[t]:>18.3f}{b[t]:>18.3f}{a[t] - b[t]:>8.3f}")
    print("-" * 70)
    print(f"{'mean':<26}{r['mean_a']:>18.4f}{r['mean_b']:>18.4f}{r['delta']:>8.4f}")
    print()
    print(f"n (paired)                 {r['n']}")
    print(f"paired delta ({name_a} - {name_b})  {r['delta'] * 100:+.1f} pp")
    ci = r["ci"]
    print(f"95% CI on the difference   [{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}] pp"
          if ci else "95% CI on the difference   n/a")
    print(f"discordant pairs           {name_a}-only {r['a_only']}, "
          f"{name_b}-only {r['b_only']}, tied {r['ties']}")
    print(f"exact McNemar p            {r['p']:.4f}")
    print()
    print("Separable only if the CI on the difference excludes 0.")

    # A6 pre-specifies the comparison paired WITHIN tier and names the interaction as
    # the effect. The marginal delta above averages two opposite effects, so its value
    # depends on how many tasks of each tier the suite happens to hold -- A6 declines it
    # as the headline in advance, which is why it is not the last thing printed.
    tiers = split_tiers(ra)
    if len(tiers) > 1:
        print()
        print("paired WITHIN tier (pre-registration A6)")
        print("-" * 70)
        deltas, diffs = {}, {}
        for tier in ("cheap", "full-scan"):
            names = tiers.get(tier, set()) & set(r["tasks"])
            if not names:
                continue
            sub = paired({n: a[n] for n in names}, {n: b[n] for n in names})
            deltas[tier], diffs[tier] = sub["delta"], sub["diffs"]
            ci = sub["ci"]
            band = (f"[{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}]" if ci else "n/a")
            print(f"{tier:<12} n={sub['n']:<3} "
                  f"{name_a} {sub['mean_a']:.3f}  {name_b} {sub['mean_b']:.3f}  "
                  f"delta {sub['delta'] * 100:+.1f} pp  CI {band}  p={sub['p']:.4f}")
        if len(deltas) == 2:
            # The interval on the interaction is the one that decides N1. A point estimate
            # here would repeat this project's own recurring defect: reporting a number
            # whose interval nobody computed.
            inter = deltas["full-scan"] - deltas["cheap"]
            # Keyword arguments deliberately: this call site passed (full-scan, cheap)
            # positionally into a signature named (low, high) and printed the interval on
            # the REVERSE difference -- [-13.1, +64.1] for a point estimate of -23.7 pp,
            # an estimate sitting outside its own CI. Naming the sides here makes the
            # order unswappable.
            ici = bootstrap_interaction(diffs_low=diffs["cheap"],
                                        diffs_high=diffs["full-scan"])
            iband = (f"[{ici[0] * 100:+.1f}, {ici[1] * 100:+.1f}]" if ici else "n/a")
            print("-" * 70)
            print(f"interaction (full-scan delta - cheap delta)   {inter * 100:+.1f} pp"
                  f"  95% CI {iband}")
            print(f"A6/N1 predicted NEGATIVE by >= 25 pp "
                  f"({name_b} ahead on full-scan, not on cheap)")
            print(f"  point estimate: "
                  f"{'consistent' if inter <= -0.25 else 'NOT met'}")
            if ici:
                print(f"  interval:       "
                      f"{'EXCLUDES 0 -- negative direction supported' if ici[1] < 0 else 'INCLUDES 0 -- direction not separable'}")

    disc = (r["a_only"] + r["b_only"]) / r["n"]
    print()
    print(f"discordance rate           {disc:.3f}")
    for target, label in ((abs(r["delta"]), "the observed delta"), (0.068, "pre-reg's +6.8 pp")):
        need = power_pairs(target, disc) if disc else None
        got = f"{need} paired tasks" if need else "not detectable at this discordance"
        print(f"n for 80% power on {label:<20} {got}")
    return 0


def demo() -> None:
    """Self-check: the pairing, the sign of the delta, and the exact test."""
    a = {"t1": 1.0, "t2": 1.0, "t3": 0.0, "t4": 1.0}
    b = {"t1": 1.0, "t2": 0.0, "t3": 0.0, "t4": 0.0}
    r = paired(a, b)
    assert r["n"] == 4
    assert abs(r["delta"] - 0.5) < 1e-9, r["delta"]
    assert (r["a_only"], r["b_only"], r["ties"]) == (2, 0, 2), r
    # 2 discordant pairs, both one way: 2 * (1/4) = 0.5
    assert abs(r["p"] - 0.5) < 1e-9, r["p"]
    # a symmetric split cannot be significant
    assert mcnemar_exact(5, 5) == 1.0
    # the textbook case: 0 of 6 one way
    assert abs(mcnemar_exact(6, 0) - 2 * (1 / 64)) < 1e-9
    # unshared tasks are dropped, not treated as zeros
    assert paired({"t1": 1.0, "x": 1.0}, {"t1": 0.0})["n"] == 1

    # power: a bigger effect needs fewer pairs, and more discordance needs fewer
    big = power_pairs(0.30, 0.43)
    small = power_pairs(0.07, 0.43)
    assert big and small and big < small, (big, small)
    # an effect larger than the discordance rate cannot be produced at any n
    assert power_pairs(0.50, 0.30) is None
    # ...but delta == discordance is the UNANIMOUS case, the easiest to detect, not
    # impossible. Six one-sided discordant pairs already reach exact p=0.031.
    unanimous = power_pairs(0.1429, 0.1429)
    assert unanimous is not None, "unanimous discordance must be detectable"
    assert round(unanimous * 0.1429) >= 6, unanimous
    assert _attained(0.1429, 0.1429, unanimous) >= 0.8
    assert power_pairs(0.0, 0.5) is None and power_pairs(0.1, 0.0) is None
    # the returned n really does reach the requested power, and one step less does not
    assert _attained(0.30, 0.43, big) >= 0.8
    print("ok")


def _attained(delta: float, discordance: float, n: int, alpha: float = 0.05) -> float:
    """Power actually attained at n -- used by demo() so the search is checked against
    a direct computation rather than against itself."""
    p = 0.5 + delta / (2 * discordance)
    d = round(n * discordance)
    crit = -1
    for k in range(d // 2 + 1):
        if mcnemar_exact(k, d - k) <= alpha:
            crit = k
        else:
            break
    if crit < 0:
        return 0.0
    # Exact rationals, not `_binom_cdf`'s log space. The same int-to-float overflow
    # lives in this expression, but this function is demo()'s INDEPENDENT check on the
    # search -- routing it through the helper the search uses would make it agree with
    # `power_pairs` by construction, which is how a check stops being one. Fraction is
    # a third method, exact and slow, and demo()'s d stays small enough to afford it.
    pf = Fraction(p)
    total = sum(Fraction(comb(d, i)) * pf ** (d - i) * (1 - pf) ** i
                for i in range(crit + 1))
    return float(total)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "demo":
        demo()
    else:
        raise SystemExit(main(sys.argv))
