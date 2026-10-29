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
answer divergence on every slow gold. Each differential runs in a fresh interpreter
whose original process group is bounded and cleaned; a sweep timeout is
recorded as `sweep_timeout` and is the sweep's bound, not the arm's.

A gold that exceeds the cap is refused by BOTH arms -- agreement, but not a row
comparison -- so those are counted separately as `capped`.

Offline, $0, no model.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from bench.loader import load_bird
from bench.task import SqlTask
from process_watchdog import run_bounded
from ptc.sql_diff import DELIVERY_CAUSES, DELIVERY_OUTCOMES, RENDER_CAUSES, differential
from ptc.sql_runtime import MAX_ROWS

QUERY_TIMEOUT = 30.0
"""Seconds one gold gets on either arm. See the module docstring."""


def _worker_command(request_path: Path, result_path: Path) -> list[str]:
    """Isolated imports from this checkout, with only JSON paths in diagnostic argv."""
    bootstrap = (
        "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));"
        "runpy.run_module('bench.sql_parity_sweep',run_name='__main__')"
    )
    return [sys.executable, "-I", "-B", "-c", bootstrap,
            str(Path(__file__).resolve().parents[1]), "--worker",
            str(request_path), str(result_path)]


def _project(result) -> dict:
    return {
        "agreed": result.agreed, "capped": result.capped,
        "bash_outcome": result.bash.outcome, "ptc_outcome": result.ptc.outcome,
        "bash_rows": result.bash.n_rows, "ptc_rows": result.ptc.n_rows,
        "delivery_causes": list(result.delivery_causes),
        "render_causes": list(result.render_causes), "note": result.note,
    }


def _worker_main(request_path: Path, result_path: Path) -> int:
    """Run unchanged comparison; no arbitrary objects cross the JSON boundary."""
    try:
        request = json.loads(request_path.read_text())
        task = SqlTask(**request["task"])
        result = differential(task, bindir=request_path.parent,
                              compare=request["compare"], max_rows=request["max_rows"])
        payload = {"result": _project(result)}
    except Exception as error:  # noqa: BLE001 -- child computation, not ownership
        payload = {"error": f"{type(error).__name__}: {error}"}
    result_path.write_text(json.dumps(payload, allow_nan=False))
    return 0


def _read_result(result_path: Path) -> dict:
    payload = json.loads(result_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("worker output must be an object")
    if set(payload) == {"error"} and isinstance(payload["error"], str) and payload["error"]:
        return payload
    if set(payload) != {"result"} or not isinstance(payload["result"], dict):
        raise ValueError("worker output must contain result or error")
    result = payload["result"]
    fields = {"agreed", "capped", "bash_outcome", "ptc_outcome", "bash_rows",
              "ptc_rows", "delivery_causes", "render_causes", "note"}
    if set(result) != fields:
        raise ValueError("worker result fields differ from projection")
    for field in ("agreed", "capped"):
        if type(result[field]) is not bool:
            raise ValueError(f"worker {field} must be boolean")
    for arm in ("bash", "ptc"):
        outcome, count = result[f"{arm}_outcome"], result[f"{arm}_rows"]
        if not isinstance(outcome, str) or outcome not in DELIVERY_OUTCOMES:
            raise ValueError(f"worker {arm}_outcome is invalid")
        if type(count) is not int or count < 0 or (outcome != "ok" and count != 0):
            raise ValueError(f"worker {arm}_rows is invalid")
    for field, allowed in (("delivery_causes", DELIVERY_CAUSES),
                           ("render_causes", RENDER_CAUSES)):
        causes = result[field]
        if not isinstance(causes, list) or any(
                not isinstance(cause, str) or cause not in allowed for cause in causes):
            raise ValueError(f"worker {field} is invalid")
    if not isinstance(result["note"], str):
        raise ValueError("worker note must be text")
    if result["agreed"] != (not result["delivery_causes"]):
        raise ValueError("worker agreement contradicts delivery causes")
    if result["agreed"] and result["bash_outcome"] != result["ptc_outcome"]:
        raise ValueError("worker agreement contradicts arm outcomes")
    if result["capped"] != (result["bash_outcome"] == result["ptc_outcome"] == "refused"):
        raise ValueError("worker cap contradicts arm outcomes")
    return payload


def _one(task: SqlTask, worker_bindir: Path, compare: str, max_rows: int) -> dict:
    """One gold, both arms, recorded as a JSON-able row.

    The parent removes its private directory only after successful owned cleanup.
    Unexpected watchdog/cleanup errors propagate and preserve it for diagnosis.
    """
    start = time.monotonic()
    worker_bindir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="query-", dir=worker_bindir)).resolve()
    request_path, result_path = directory / "request.json", directory / "result.json"
    cleanup_safe = True
    error = None
    payload = None
    try:
        request_path.write_text(json.dumps(
            {"task": asdict(task), "compare": compare, "max_rows": max_rows},
            allow_nan=False))
        command = _worker_command(request_path, result_path)
        cleanup_safe = False
        try:
            completed = run_bounded(command, timeout=QUERY_TIMEOUT + 15.0)
        except subprocess.TimeoutExpired:
            # run_bounded raises this only AFTER successful original-group cleanup.
            cleanup_safe = True
            error = TimeoutError(f"exceeded {QUERY_TIMEOUT + 15.0}s")
        else:
            cleanup_safe = True
            if completed.returncode != 0:
                error = RuntimeError(f"worker exited {completed.returncode}")
            else:
                try:
                    payload = _read_result(result_path)
                except (OSError, ValueError, TypeError) as exc:
                    error = exc
    finally:
        if cleanup_safe:
            shutil.rmtree(directory)
    row: dict = {"name": task.name, "db_id": task.db_id,
                 "elapsed_s": round(time.monotonic() - start, 3)}
    try:
        row["question_id"] = int(task.name.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        row["question_id"] = None
    if error is not None or "error" in payload:
        cause = "sweep_timeout" if isinstance(error, TimeoutError) else "sweep_error"
        message = f"{type(error).__name__}: {error}" if error is not None else payload["error"]
        row.update(agreed=False, error=message,
                   delivery_causes=[cause], render_causes=[])
        return row
    row.update(payload["result"])
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
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--worker":
        if len(argv) != 3:
            raise SystemExit("worker requires request and result JSON paths")
        return _worker_main(Path(argv[1]), Path(argv[2]))
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

    def _worker(task: SqlTask) -> dict:
        return _one(task, bindir_root, args.compare, args.max_rows)

    started = time.monotonic()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(_worker, t) for t in tasks]
        try:
            for done, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                if done % 100 == 0:
                    print(f"  {done}/{len(tasks)}  ({time.monotonic() - started:.0f}s)",
                          file=sys.stderr, flush=True)
        except BaseException:
            # Already-running jobs retain their own bounded ownership. Do not start
            # queued work or write a partial success summary after an ownership error.
            for future in futures:
                future.cancel()
            raise

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
