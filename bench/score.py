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

# Any fenced block, tag or no tag. Used for the content-based tier below.
_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# A fence the model explicitly tagged as SQL. `\b` after the tag so a ```sqlite
# block is not read as a ```sql one with "ite" as its first line of SQL -- it falls
# through to the content-based tier instead, which is the safer place for it.
_SQL_FENCE = re.compile(r"```sql\b\s*(.*?)```", re.DOTALL | re.IGNORECASE)


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


# A SQL statement's leading keyword, at a word boundary. WITH covers CTEs, which BIRD
# uses heavily; VALUES and SELECT cover the rest of what a text-to-SQL policy emits.
# Anchored with \b so a column named "selection" does not start a statement.
_SQL_LEAD = re.compile(r"\b(?:select|with|values)\b", re.IGNORECASE)

# `<answer>...</answer>` from the sibling exact-match reward, which a confused policy
# mixes into a SQL task.
_ANSWER_TAGS = re.compile(r"<answer>(.*?)</answer>", re.IGNORECASE | re.DOTALL)

# The same keywords anchored at the START of a string: a fenced block whose content
# OPENS with a statement is a query, whereas one that merely mentions "select"
# somewhere in a paragraph is reasoning about one.
_SQL_START = re.compile(r"\A(?:select|with|values)\b", re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Pull a SQL statement out of model output.

    **The harness calls this; `execution_accuracy` deliberately does not.** Keeping
    extraction out of the scorer makes it an explicit, auditable step rather than a
    silent leniency inside the metric -- but it has to happen somewhere, because a
    prediction arriving as ```` ```sql ... ``` ```` would otherwise score a syntax error
    and understate the model, which looks exactly like a frontier-band problem and is
    not one.

    Order, strongest signal of the model's intent first:

    1. The **last** ```` ```sql ````-tagged fence. A reasoning model concludes with its
       answer, and an explicit language tag is the clearest available statement that this
       block is the query rather than a quotation, an echo, or a discarded candidate.
    2. Else the last fenced block whose content OPENS with `SELECT`/`WITH`/`VALUES`.
       Untagged fences are common, so content is the only signal left; the last one is
       still the conclusion.
    3. Else the text from the first SQL leading keyword onward, which handles bare and
       prose-wrapped SQL with no fence at all.
    4. Else the text unchanged, so a completion containing no SQL scores 0 by failing to
       execute rather than being mangled into something that parses.

    Then a trailing semicolon and anything after it is dropped, because
    `execution_accuracy` runs exactly one statement.

    **Correction, recorded so it is not reintroduced: this took the FIRST fence until
    2026-10-14, and that was wrong.** The probe's prompt instructs the model to answer
    "in a ```sql fenced block", so the instruction itself carries an unterminated fence
    marker, and the schema it ships is fenced too. A model that echoes that schema back
    and closes it leaves an ODD number of markers before its real answer, after which
    every pairing is off by one: the first match then spans from the echo's CLOSING fence
    to the OPENING fence of the actual answer, capturing whatever prose sits between
    them. Four completions sampled from the dead-group probe's seventh run went through
    the old path and three came back as text the model never proposed as a query --
    `Answer:`, and two paragraphs of reasoning. Taking the LAST fence also stops a first
    fence from being preferred over a conclusion when the model writes several candidate
    queries while thinking. The failure biases the measured solve rate LOW, and
    `train/guards.py`'s frontier gate consumes that rate, so it is not a cosmetic bug.

    **Known limit, stated rather than fixed:** prose AFTER the query on a new line is
    still included when no semicolon closes the statement. Cutting at the first newline
    would break multi-line SQL, which is both common and correct, so the trade goes the
    other way. Such a completion scores 0, and the sampled completions in the probe's
    metrics are how that case is spotted rather than inferred.

    **Residual bias, surfaced rather than patched:** tier 1 trusts the tag over the
    content, so a final ```` ```sql ```` block holding prose still comes back as prose.
    Letting content override an explicit declaration of intent is the kind of heuristic
    that produced the first-fence bug, so it is not added. Separately, the odd-marker
    shape above is only recovered when the model's answer fence is TAGGED; with an
    untagged answer fence the pairing stays shifted and tier 3 returns the query with a
    trailing ```` ``` ```` attached. Both score 0 and both show up in sampled
    completions. See `test_extract_sql_cannot_repair_an_untagged_fence_after_an_echo`.
    """
    text = _ANSWER_TAGS.sub(r"\1", text)

    tagged = _SQL_FENCE.findall(text)
    if tagged:
        body = tagged[-1]
    else:
        sql_like = [b for b in (f.strip() for f in _FENCE.findall(text))
                    if _SQL_START.match(b)]
        if sql_like:
            body = sql_like[-1]
        else:
            lead = _SQL_LEAD.search(text)
            body = text[lead.start():] if lead else text
    body = body.strip()
    # Drop a trailing semicolon AND whatever follows it: the statement ended there, and
    # `execution_accuracy` runs exactly one statement.
    head, sep, _ = body.partition(";")
    return (head if sep else body).strip().rstrip(";").strip()


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


def rows_match(pred_rows: list[tuple], gold_rows: list[tuple], *,
               compare: str = "set") -> bool:
    """Do two result sets count as the same answer? BIRD's one comparison, in one place.

    Factored out of `execution_accuracy` for the differential parity check
    (`ptc/sql_diff.py`), which compares one arm's delivery against the other's. That
    check exists because the two arms can disagree about a query NOBODY WROTE A
    CAPABILITY FOR (`docs/harness-parity.md` §6), and a differential that re-implemented
    the comparison could disagree with the scorer about what agreement means -- a second
    implementation of the adjudicator is exactly the drift this project keeps finding.
    `execution_accuracy` calls this function, so there is one definition.

    `compare="set"` (default) is official BIRD `evaluation.py`'s
    `set(predicted) == set(ground_truth)`; `"multiset"` is the stricter sensitivity
    check. Raises on any other value, as the scorer always has.
    """
    if compare not in ("multiset", "set"):
        raise ValueError(f"compare must be 'multiset' or 'set', got {compare!r}")
    if compare == "multiset":
        return Counter(pred_rows) == Counter(gold_rows)
    return set(pred_rows) == set(gold_rows)


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

        hit = rows_match(pred_rows, gold_rows, compare=compare)
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
