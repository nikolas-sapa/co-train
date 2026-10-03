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
import sys
from math import comb

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


def paired(a: dict[str, float], b: dict[str, float]) -> dict:
    shared = sorted(set(a) & set(b))
    if not shared:
        raise SystemExit("no shared task names -- are these the same taskset?")
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
    a, b = load(path_a), load(path_b)
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
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "demo":
        demo()
    else:
        raise SystemExit(main(sys.argv))
