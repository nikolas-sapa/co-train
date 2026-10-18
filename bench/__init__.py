"""`bench` -- the replacement eval instrument: BIRD-SQL (+Spider) with execution-accuracy
scoring and an honest power report.

**Why this package exists.** The `ledger` taskset is dead as a measuring instrument, and
the reason is structural rather than fixable. Its record schema
`{id, kind, amount, owner, link}` admits exactly 9 cheap shapes -- 3 field reads, 5
chain-walk statistics, 1 reverse-link -- and replicates of a shape are correlated, so
effective n is bounded by `shapes / rho` no matter how large the corpus grows. Against
the 61 effective paired tasks the project's own power function says it needs, that is a
vertical asymptote at `rho = 9 / 61 = 0.1475`. Going from 40 records to 400 multiplies
replicates and adds **zero shapes**. Run 3d then scored an exact 23/23 tie on both arms,
which is the same fact arriving as saturation: a 0/1 reward needs tasks the policy
*sometimes* solves, and both saturation (`p -> 1`) and uniform failure (`p -> 0`) produce
groups with no variance and therefore no advantage.

So the replacement has to clear two bars at once, and they pull against each other: many
more SHAPES, and a difficulty that lands inside the band where a 0.6B policy is neither
saturated nor uniformly failing. BIRD-SQL is the only candidate with a published sub-1B
number to site that band against -- see `docs/bench-taskset.md` for the argument and its
figures.

**Module map:**

- `bench.shapes`  -- SQL -> clause skeleton. The unit effective n is counted in, at two
  granularities, because a single granularity would hide how much the ceiling depends on
  the choice.
- `bench.task`    -- `SqlTask`, the whole interface the harness lane consumes.
- `bench.loader`  -- BIRD dev and Spider dev against their real layouts. Raises rather
  than returning an empty taskset.
- `bench.score`   -- execution accuracy. Read-only, timeout-bounded, and it distinguishes
  a wrong prediction from a defective task.
- `bench.suite`   -- stratified seeded selection over shapes within tier, and `report()`.
- `bench.fixture` -- a committed text-only corpus that runs the real loaders offline.

Nothing here imports `verifiers`, so the inventory, the scorer and the report all run in
a bare interpreter. The harness lane owns the `verifiers` wrapping in `ptc/sql_arms.py`.

**This instrument is not signed.** It requires a pre-registration amendment, drafted at
`docs/amendment-A7-bird-sql-draft.md` and unsigned. No measurement whose result would
need that amendment has been run.
"""

from bench.loader import CorpusMissing, load_bird, load_spider
from bench.score import ExResult, execution_accuracy, extract_sql, rows_match, validate_golds
from bench.shapes import Skeleton, shape, skeleton
from bench.suite import inventory, report, select
from bench.task import TIERS, SqlTask

__all__ = [
    "CorpusMissing",
    "ExResult",
    "Skeleton",
    "SqlTask",
    "TIERS",
    "execution_accuracy",
    "extract_sql",
    "inventory",
    "load_bird",
    "load_spider",
    "report",
    "rows_match",
    "select",
    "shape",
    "skeleton",
    "validate_golds",
]
