"""`SqlTask` -- the whole interface between this instrument and the arms that run on it.

Kept deliberately small, and kept free of any `verifiers` import. The HARNESS lane owns
`ptc/sql_arms.py` and wraps these into `vf.TaskData` subclasses the way
`ledger/taskset.py` does; this module is plain stdlib so the shape inventory, the scorer
and the power report all run in a bare interpreter with no model, no network and no
`verifiers` in the import path. `ledger/taskset.py` imports `verifiers.v1` at module
scope, which means nothing in it can be exercised without the full environment; that is
a cost this lane does not have to pay twice.

`tier_source` exists because BIRD and Spider do not label difficulty the same way, and
pooling them silently would be an undisclosed instrument change:

- BIRD dev ships a human `difficulty` field (`simple` / `moderate` / `challenging`).
  That is an ANNOTATION. `tier_source="annotated"`.
- Spider dev ships no difficulty field at all, so a tier has to be DERIVED from the
  query's own skeleton. `tier_source="derived"`.

A report that averaged a human annotation with a structural heuristic and printed one
"moderate" row would be reporting a quantity nobody defined. `bench/suite.py:report()`
therefore refuses to pool the two, and this field is how it tells them apart.
"""

from __future__ import annotations

from dataclasses import dataclass

# BIRD's own ordering, lowest difficulty first. The index into this tuple is what the
# harness turns into `min_calls` for `ptc/paired.py`'s tier split -- see
# `docs/bench-taskset.md` for why that split is lossy on a three-tier taskset.
TIERS = ("simple", "moderate", "challenging")


@dataclass(frozen=True)
class SqlTask:
    """One text-to-SQL task. Frozen, because a taskset that can be mutated after the
    shape inventory is computed is a taskset whose report describes something other than
    what ran."""

    name: str
    """Stable unique id, e.g. `bird-0042`. This is the key `ptc/paired.py` pairs arms
    on (`task.data.name`), so it must be identical across arms and stable across runs --
    not an enumeration index over a filtered list, which shifts when the filter does."""

    question: str
    """The natural-language question, verbatim from the corpus."""

    evidence: str
    """BIRD's external-knowledge hint. Empty string for Spider, which ships none.

    This is part of the task as BIRD defines it, not a prompt-engineering choice: the
    published 56.87% EX for a 0.5B model is measured WITH evidence supplied, so an arm
    that withholds it is not measuring against that number. Both arms must receive it
    identically, or the comparison is confounded by prompt content rather than channel.
    """

    gold_sql: str
    """The reference query, verbatim. Never normalised or rewritten -- the scorer
    executes it, and a rewritten gold is a second implementation that can disagree with
    the first (`ledger/taskset.py`'s own stated rule about hand-written answers)."""

    db_id: str

    db_path: str
    """Absolute path to the task's sqlite file. Absolute because the arms run with an
    unspecified cwd, and a relative path here is a corpus that resolves differently per
    arm."""

    tier: str
    """One of `TIERS`."""

    tier_source: str
    """`"annotated"` (BIRD's human label) or `"derived"` (structural, Spider). Never
    pooled across the two -- see the module docstring."""

    shape: str
    """The fine-granularity clause skeleton from `bench/shapes.py`. The unit the
    effective-n ceiling is computed in, and the stratum the selector draws over."""

    coarse_shape: str
    """The coarse structural family. Reported alongside `shape` so the ceiling's
    sensitivity to shape granularity is visible rather than taken on trust."""

    source: str
    """`"bird"`, `"spider"` or `"fixture"`."""

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"{self.name}: tier {self.tier!r} not in {TIERS}")
        if self.tier_source not in ("annotated", "derived"):
            raise ValueError(f"{self.name}: bad tier_source {self.tier_source!r}")

    @property
    def tier_index(self) -> int:
        """Position in `TIERS`. The harness maps this onto `min_calls` so that
        `ptc/paired.py:split_tiers` -- which keys on `min_calls` and buckets `max`
        against everything else -- puts `challenging` in its `full-scan` bucket."""
        return TIERS.index(self.tier)
