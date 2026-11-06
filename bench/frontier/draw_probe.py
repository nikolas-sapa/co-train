"""Read-only retained-draw integration for an explicitly supplied generator."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from bench.frontier.probe import ProbeResult, SampleObservation, probe
from bench.prepare import load_validated_draw
from bench.task import SqlTask


def probe_validated_draw(
    root: Path | str,
    draw_path: Path | str,
    supplement_path: Path | str,
    generate: Callable[[SqlTask], str],
    *,
    expected_draw_sha256: str,
    expected_supplement_sha256: str,
    fixture: bool = False,
    policy: str,
    g: int,
    dead_ceiling: float,
    sample_observer: Callable[[SampleObservation], None] | None = None,
) -> ProbeResult:
    """Probe only admitted eligible tasks, refusing drift before returning.

    The callback is trusted caller code. Policy is a caller-supplied label,
    not authenticated checkpoint identity. Fixture callbacks establish wiring,
    not a measured model frontier. This helper never publishes output.
    """
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("policy must be a nonempty string")
    if type(g) is not int or g < 2:
        raise ValueError("g must be an exact int at least 2")
    if (type(dead_ceiling) not in (int, float)
            or not 0.0 < dead_ceiling < 1.0
            or not math.isfinite(dead_ceiling)):
        raise ValueError("dead_ceiling must be finite and in (0, 1)")

    admitted = load_validated_draw(
        root, draw_path, supplement_path,
        expected_draw_sha256=expected_draw_sha256,
        expected_supplement_sha256=expected_supplement_sha256,
        fixture=fixture,
    )
    observation_kwargs = {}
    if sample_observer is not None:
        observation_kwargs["sample_observer"] = sample_observer
    result = probe(
        admitted.eligible, generate, policy=policy, g=g,
        dead_ceiling=dead_ceiling, compare=admitted.comparison,
        timeout_s=admitted.timeout_s, max_rows=admitted.max_rows,
        **observation_kwargs,
    )
    load_validated_draw(
        root, draw_path, supplement_path,
        expected_draw_sha256=expected_draw_sha256,
        expected_supplement_sha256=expected_supplement_sha256,
        fixture=fixture,
    )
    return result
