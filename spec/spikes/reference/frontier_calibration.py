"""Exact synthetic selection-bias reference, not a policy measurement."""

from __future__ import annotations

import itertools
import json
import sys
from fractions import Fraction

from bench.frontier.probe import dead_group_fraction


def main() -> None:
    # SHORTCUT: fixed hypothetical IID p/G; production takes validated parameters.
    p, g = Fraction(1, 10), 4
    accepted = Fraction(0)
    weighted = Fraction(0)
    for bits in itertools.product((0, 1), repeat=g):
        wins = sum(bits)
        mass = p**wins * (1-p)**(g-wins)
        estimate = dead_group_fraction(Fraction(wins, g), g)
        if estimate <= Fraction(3, 5):
            accepted += mass
            weighted += mass * estimate
    # PROVES: selection can produce a healthy plug-in estimate for a hypothetical
    # population whose next group still exceeds the existing default ceiling.
    assert accepted == Fraction(1719, 5000)
    assert dead_group_fraction(p, g) == Fraction(3281, 5000)
    populations = ((Fraction(1, 4), Fraction(3, 4)), (Fraction(0), Fraction(1)))
    if "--break-marginal" in sys.argv:
        values = tuple(dead_group_fraction(sum(rates) / len(rates), g)
                       for rates in populations)
    else:
        values = tuple(sum(dead_group_fraction(rate, g) for rate in rates)
                       / len(rates) for rates in populations)
    assert values == (Fraction(41, 128), Fraction(1)), values
    # MISSING: no real sampler, calibration uncertainty, provenance or manifest.
    print(json.dumps({"origin": "synthetic-iid-reference",
                      "true_dead_fraction": float(dead_group_fraction(p, g)),
                      "acceptance_probability": float(accepted),
                      "conditional_plugin_dead": float(weighted / accepted)}))


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("reference assertions require unoptimized Python")
    main()
