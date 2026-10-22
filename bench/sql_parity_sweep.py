"""Full-corpus differential parity sweep: every BIRD dev gold, through both arms.

`ptc/sql_diff.py` is the comparison; this is the runnable sweep over a real corpus. It
exists because the in-suite differential runs over the eight fixture golds, which is
enough to prove the check can see a divergence and not enough to say anything about the
task class. The sentence `docs/harness-parity.md` §6 needs is a statement about BIRD's
1534 dev golds, and this is what measures it.

    .venv-ptc/bin/python -m bench.sql_parity_sweep \\
        --bird ~/scratch/bird-sql/bird-dev-extracted/dev_20240627 \\
        --out ~/scratch/cotrain-diffparity/sweep.json

Per query it records whether the arms agreed (delivery + answer), which causes were
found, whether both arms refused at the row cap, and both row counts. It reports the
totals, the causes as counts, and `--compare multiset` as the sensitivity line.

**Deadline, stated.** Both arms get the same 30s per query, which is the bash arm's real
per-query deadline (`sql_arms.WRAPPER_TIMEOUT`) and deliberately NOT the PTC arm's 5s
program budget: §2 records that those two numbers differ on purpose, so a sweep that
imposed 5s on PTC and 30s on bash would report the declared budget asymmetry as an
answer divergence on every slow gold. The PTC side is bounded by a watchdog thread,
because `make_execute_sql` has no per-query deadline of its own; a sweep timeout is
recorded as `sweep_timeout` and is the sweep's bound, not the arm's.

A gold that exceeds the cap is refused by BOTH arms -- agreement, but not a row
comparison -- so those are counted separately as `capped`.

Offline, $0, no model.
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bench.loader import load_bird
from bench.task import SqlTask
from ptc.sql_diff import differential
from ptc.sql_runtime import MAX_ROWS

QUERY_TIMEOUT = 30.0
"""Seconds one gold gets on either arm. See the module docstring."""


def _with_deadline(fn, timeout: float):
    """Run `fn` in a daemon thread and give up after `timeout` seconds.

    A watchdog rather than the arm's own machinery: `make_execute_sql` opens and closes
    its own connection and exposes no handle, so there is nothing to interrupt, and a
    long sqlite step does not return to the interpreter's signal handlers. The leaked
    daemon thread dies with the process. Two BIRD dev golds never terminate
    (`bench/score.py`), so this path is known to fire rather than hypothetical.
    """
    box: dict[str, object] = {}

    def work() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 -- recorded, not raised
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None, TimeoutError(f"exceeded {timeout}s")
    if "error" in box:
        return None, box["error"]
    return box.get("value"), None


def _one(task: SqlTask, worker_bindir: Path, compare: str, max_rows: int) -> dict:
    """One gold, both arms, recorded as a JSON-able row.

    Each invocation owns a private directory under `worker_bindir`. A watchdog can
    return while its daemon thread is still running, so a per-worker directory alone
    lets that abandoned invocation replace the next task's database-bound wrapper.
    Allocate and clean the private directory inside the watched thread: it must
    remain available until that invocation actually finishes, including after timeout.
    """
    start = time.monotonic()
    worker_bindir.mkdir(parents=True, exist_ok=True)
    def compare_task():
        with tempfile.TemporaryDirectory(prefix="query-", dir=worker_bindir) as directory:
            return differential(task, bindir=Path(directory), compare=compare,
                                max_rows=max_rows)

    result, error = _with_deadline(compare_task, QUERY_TIMEOUT + 15.0)
    elapsed = round(time.monotonic() - start, 3)
    row: dict = {"name": task.name, "db_id": task.db_id, "elapsed_s": elapsed}
    try:
        row["question_id"] = int(task.name.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        row["question_id"] = None
    if error is not None:
        cause = "sweep_timeout" if isinstance(error, TimeoutError) else "sweep_error"
        row.update(agreed=False, error=f"{type(error).__name__}: {error}",
                   delivery_causes=[cause], render_causes=[])
        return row
    row.update(
        agreed=result.agreed,
        capped=result.capped,
        bash_outcome=result.bash.outcome,
        ptc_outcome=result.ptc.outcome,
        bash_rows=result.bash.n_rows,
        ptc_rows=result.ptc.n_rows,
        delivery_causes=list(result.delivery_causes),
        render_causes=list(result.render_causes),
        note=result.note,
    )
    return row


def summarise(rows: list[dict], *, compare: str) -> dict:
    """The numbers the doc paragraph quotes, derived from the rows rather than typed."""
    causes = Counter(c for r in rows for c in r.get("delivery_causes", []))
    render = Counter(c for r in rows for c in r.get("render_causes", []))
    agreed = [r for r in rows if r.get("agreed")]
    capped = [r for r in rows if r.get("capped")]
    clean = [r for r in agreed if not r.get("render_causes")]
    return {
        "compare": compare,
        "n_total": len(rows),
        "n_agreed": len(agreed),
        "n_diverged": len(rows) - len(agreed),
        "n_capped_both": len(capped),
        "n_compared_rowwise": len(agreed) - len(capped),
        "n_agreed_with_render_cause": len(agreed) - len(clean),
        "delivery_causes": dict(causes),
        "render_causes": dict(render),
        "divergent_ids": sorted(r["question_id"] for r in rows
                                if not r.get("agreed") and r["question_id"] is not None),
        "render_ids": sorted(r["question_id"] for r in rows
                             if r.get("render_causes") and r["question_id"] is not None),
        "timeouts": sorted(r["question_id"] for r in rows
                           if "sweep_timeout" in r.get("delivery_causes", [])
                           and r["question_id"] is not None),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Differential parity over BIRD dev golds.")
    p.add_argument("--bird", type=Path,
                   default=Path("~/scratch/bird-sql/bird-dev-extracted/dev_20240627"),
                   help="BIRD dev corpus root, or its parent")
    p.add_argument("--out", type=Path,
                   default=Path("~/scratch/cotrain-diffparity/sweep.json"))
    p.add_argument("--compare", default="set", choices=("set", "multiset"))
    p.add_argument("--max-rows", type=int, default=MAX_ROWS,
                   help="the channel's row cap; default sql_runtime.MAX_ROWS")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--limit", type=int, default=0, help="0 = every task")
    args = p.parse_args(argv)

    args.out = args.out.expanduser()
    tasks = load_bird(args.bird.expanduser())
    if args.limit:
        tasks = tasks[:args.limit]
    if not tasks:  # load_bird raises, so this only guards a future filtering change
        raise SystemExit("no tasks loaded; a sweep over nothing is not a result")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    bindir_root = args.out.parent / "bin"
    bindir_root.mkdir(parents=True, exist_ok=True)
    # Thread-local parent directories. _one gives each watched invocation its own
    # child, since a timed-out daemon may outlive this worker's current task.
    local = threading.local()

    def _worker(task: SqlTask) -> dict:
        bindir = getattr(local, "bindir", None)
        if bindir is None:
            bindir = local.bindir = Path(tempfile.mkdtemp(prefix="diffparity-"))
        return _one(task, bindir, args.compare, args.max_rows)

    started = time.monotonic()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(_worker, t) for t in tasks]
        for done, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if done % 100 == 0:
                print(f"  {done}/{len(tasks)}  ({time.monotonic() - started:.0f}s)",
                      file=sys.stderr, flush=True)

    rows.sort(key=lambda r: (r.get("question_id") is None, r.get("question_id") or 0))
    summary = summarise(rows, compare=args.compare)
    payload = {
        "generated_by": "bench/sql_parity_sweep.py",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.monotonic() - started, 1),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "max_rows": args.max_rows,
        "summary": summary,
        "rows": rows,
    }
    args.out.write_text(json.dumps(payload, indent=1))
    print(json.dumps(summary, indent=2))
    print(f"\n{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
