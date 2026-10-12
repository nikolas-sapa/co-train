"""Execution-accuracy (EX) scoring: run the predicted query and the gold query, compare
the rows they return.

Three properties this module is built around, each because its absence has a specific
failure mode this project has already paid for:

1. **A prediction can never crash the run.** A syntax error, a reference to a column
   that does not exist, a query that never terminates, a cartesian product that would
   exhaust memory -- every one of those is scored WRONG and returns normally. An
   exception escaping the scorer kills a rollout, and `ptc/paired.py:refuse_voids` then
   voids the entire comparison over one bad prediction, which is the most expensive
   possible way to score a zero.

2. **A broken GOLD is not a legitimate zero.** If the reference query itself fails, the
   task is defective and scoring the prediction 0 against it is meaningless -- the
   prediction might have been right. Those outcomes set `valid=False`, and the harness
   must propagate that into the rollout's `ok` field so `refuse_voids` fires. Scoring a
   defective task 0 is the single most flattering thing this scorer could do to whichever
   arm happened to also fail, which is exactly the asymmetry `refuse_voids` exists to
   refuse. `validate_golds()` below lets a run find these BEFORE it spends a model call.

3. **Read-only, bounded, one statement.** The prediction is generated text pointed at a
   sqlite file. The connection is opened `mode=ro` with `query_only` on, every query gets
   a wall-clock deadline, the row count is capped, and `sqlite3.Connection.execute` runs
   exactly one statement -- so `SELECT 1; DROP TABLE t` raises rather than executing the
   second half. The corpus is downloaded data and must survive being pointed at.

**A divergence from official BIRD, now decided.** BIRD's published `evaluation.py`
compares with `set(predicted) == set(ground_truth)`, which collapses duplicate rows: a
query returning one row and a query returning that same row ten times score equal. The
stricter multiset comparison is more defensible in isolation, but comparability to the
published sub-1B numbers that site this project's frontier band is the whole reason for
leaving a self-authored taskset, and a multiset number is not comparable to any of them.

**`compare="set"` is therefore the default and the headline; multiset is a disclosed
sensitivity check.** This reverses the lane brief, which called multiset "BIRD's
convention" -- it is not, and the correction is recorded rather than quietly applied. The
two differ on real queries, so a reported EX number must name which it used. Both are
implemented; neither is chosen silently. See `docs/bench-taskset.md`.
"""

from __future__ import annotations

import math
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bench.task import SqlTask

# Row ceiling for one result set. A judgement, not a measurement, and disclosed as one:
# it exists so a runaway gold cannot hold a training step open, not to decide which tasks
# are admissible. Measured over all 1534 BIRD dev golds at 100_000 it rejected four, and
# only TWO were genuine defects (never terminate, even at 60s) -- the other two
# legitimately return 228,765 and 278,230 rows in about a second, so the cap was
# penalising valid tasks, which is the same shape as the defect that invalidated run 1.
# Raised to 500_000 to clear both. The two non-terminating golds stay excluded, by their
# own behaviour rather than by this bound.
MAX_ROWS = 500_000

# Outcomes where the TASK is defective rather than the prediction being wrong. The
# harness must map these onto a void rollout, not onto a score of 0.
INVALID_STATUSES = frozenset({"gold_error", "gold_timeout", "gold_truncated",
                              "db_missing"})

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ExResult:
    """The outcome of scoring one prediction."""

    score: float
    """1.0 on a match, 0.0 otherwise. Meaningless when `valid` is False."""

    status: str
    """`match`, `mismatch`, `pred_error`, `pred_timeout`, `pred_truncated`,
    `pred_empty`, or one of `INVALID_STATUSES`."""

    valid: bool
    """False when the task itself is defective (`INVALID_STATUSES`). The harness must
    propagate this into the rollout's `ok` field; `ptc/paired.py:refuse_voids` then
    voids the comparison rather than crediting the other arm with a win."""

    detail: str = ""
    """Error text or row counts. For the trace, not for scoring."""

    n_pred_rows: int = 0
    n_gold_rows: int = 0


def extract_sql(text: str) -> str:
    """Pull a SQL statement out of model output.

    **The harness calls this; `execution_accuracy` deliberately does not.** Keeping
    extraction out of the scorer makes it an explicit, auditable step rather than a
    silent leniency inside the metric -- but it has to happen somewhere, because a
    prediction arriving as ```` ```sql ... ``` ```` would otherwise score a syntax error
    and understate the model, which looks exactly like a frontier-band problem and is
    not one.

    Takes the first fenced block if there is one, else the whole string, then strips a
    trailing semicolon.
    """
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    return body.strip().rstrip(";").strip()


def _normalise(value: object) -> object:
    """Make one cell comparable.

    `float('nan') != float('nan')`, so a NaN anywhere in either result set would make a
    query unequal to itself. Mapped to a sentinel so comparison is reflexive. Ints and
    floats are left alone: `1 == 1.0` and they hash equal, which is the behaviour wanted
    -- sqlite's choice of storage class for an integral value is not a wrong answer.
    """
    if isinstance(value, float) and math.isnan(value):
        return "<nan>"
    return value


def _run(conn: sqlite3.Connection, sql: str, timeout_s: float,
         max_rows: int) -> tuple[str, list[tuple] | None, str]:
    """Execute one statement under a deadline and a row cap.

    Returns `(outcome, rows, detail)` where outcome is `ok`, `timeout`, `truncated` or
    `error`. Never raises.
    """
    deadline = time.monotonic() + timeout_s
    timed_out = False

    def _guard() -> int:
        # Returning non-zero from a progress handler aborts the operation, which is the
        # documented way to bound a query from inside sqlite. A thread-based timeout
        # cannot interrupt a long scan; this can.
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    conn.set_progress_handler(_guard, 2000)
    try:
        cur = conn.execute(sql)
        # One row more than the cap, so hitting the cap is distinguishable from
        # returning exactly `max_rows` legitimately.
        rows = cur.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            return "truncated", None, f"more than {max_rows} rows"
        return "ok", [tuple(_normalise(v) for v in r) for r in rows], ""
    except (sqlite3.Error, sqlite3.Warning, ValueError, OverflowError,
            MemoryError) as exc:
        if timed_out:
            return "timeout", None, f"exceeded {timeout_s}s"
        return "error", None, f"{type(exc).__name__}: {exc}"
    finally:
        conn.set_progress_handler(None, 0)


def _connect(db_path: str) -> sqlite3.Connection:
    """Read-only connection. `mode=ro` refuses writes at the VFS layer and
    `query_only` refuses them at the statement layer; either alone would do, and both
    cost nothing."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only = ON")
    return conn


def execution_accuracy(predicted_sql: str, task: SqlTask, *,
                       timeout_s: float = 30.0, max_rows: int = MAX_ROWS,
                       compare: str = "set") -> ExResult:
    """Score one prediction against one task. The function the harness's reward calls.

    `predicted_sql` must already be extracted from the model's output -- see
    `extract_sql`. `compare` is `"set"` (default, official BIRD `evaluation.py`
    behaviour, leaderboard-comparable) or `"multiset"` (stricter, a sensitivity check);
    see the module docstring.
    """
    if compare not in ("multiset", "set"):
        raise ValueError(f"compare must be 'multiset' or 'set', got {compare!r}")
    if not Path(task.db_path).is_file():
        return ExResult(0.0, "db_missing", False,
                        f"no sqlite file at {task.db_path}")

    conn = None
    try:
        conn = _connect(task.db_path)
    except sqlite3.Error as exc:
        return ExResult(0.0, "db_missing", False, f"{type(exc).__name__}: {exc}")

    try:
        # The GOLD runs first. If it is broken the task is defective and the prediction
        # is not worth executing: nothing it returns could be adjudicated against a
        # reference that does not run.
        g_out, gold_rows, g_detail = _run(conn, task.gold_sql, timeout_s, max_rows)
        if g_out != "ok":
            return ExResult(0.0, f"gold_{g_out}", False,
                            f"gold {g_out}: {g_detail}")

        stripped = (predicted_sql or "").strip()
        if not stripped:
            return ExResult(0.0, "pred_empty", True, "empty prediction",
                            n_gold_rows=len(gold_rows))

        p_out, pred_rows, p_detail = _run(conn, stripped, timeout_s, max_rows)
        if p_out != "ok":
            return ExResult(0.0, f"pred_{p_out}", True, p_detail,
                            n_gold_rows=len(gold_rows))

        if compare == "multiset":
            hit = Counter(pred_rows) == Counter(gold_rows)
        else:
            hit = set(pred_rows) == set(gold_rows)
        return ExResult(
            1.0 if hit else 0.0,
            "match" if hit else "mismatch",
            True,
            "" if hit else f"pred {len(pred_rows)} rows vs gold {len(gold_rows)}",
            n_pred_rows=len(pred_rows),
            n_gold_rows=len(gold_rows),
        )
    finally:
        if conn is not None:
            conn.close()


def validate_golds(tasks: list[SqlTask], *, timeout_s: float = 30.0,
                   max_rows: int = MAX_ROWS) -> list[tuple[SqlTask, ExResult]]:
    """Execute every gold query and return the tasks whose gold does not run.

    Run this before a measurement, not after. A defective task discovered mid-run voids
    the comparison (property 2 above); the same task discovered beforehand just gets
    dropped from the suite, with the drop disclosed. This is the cheap half of that
    choice -- it costs no model calls.
    """
    broken: list[tuple[SqlTask, ExResult]] = []
    for t in tasks:
        # An empty prediction cannot pass, so this exercises the gold path only.
        r = execution_accuracy("", t, timeout_s=timeout_s, max_rows=max_rows)
        if not r.valid:
            broken.append((t, r))
    return broken
