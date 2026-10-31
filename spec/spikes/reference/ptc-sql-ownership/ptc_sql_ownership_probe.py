"""Bounded fixture spike, NOT a production fix. Parent executes; never auto-run.

TEST PLAN (numeric gates, before implementation):
1. Negative no-progress SQL + real runtime timeout=.1: native execute-entry marker, then
   parent safety timeout at 2s. Kill owned process group and drain on every exit.
2. Fixture progress callback/1000 VM steps: real runtime rejection <1s for .1s
   budget; standalone explicit .2s query deadline rejection <1s. Typed 42 unchanged.
3. Cancel at real SQLite progress callback, using a bounded scheduling-only gate:
   join worker before cancellation escapes, zero post-query commits, fresh success.
4. Normal return and ProgramRejected preserved; cancellation during normal cleanup
   propagates. Each child has a 2s cap, including asyncio executor shutdown.

PROVES, if gates pass: old C-call budget gap; callback/tracer hypothesis on this
Python/SQLite build; fixture-owned thread joining and typed-row compatibility.
SHORTCUT: fixture callable/helper only, tiny local DB, no SDK/model/scorer.
Scheduling gates are NOT query-timeout evidence. Native-entry marker precedes
SQLite initialization; only the progress callback confirms SQLite VM activity.
MISSING: ordinary PTCHarness/SDK integration, canonical bugfix, campaign limits.
Non-goals: production changes, alternate SQL backend, Gold/additional statements.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from ptc.runtime import Catalog, ProgramRejected, run as run_program
from ptc.sql_arms import MAX_ROWS, connect_readonly, make_execute_sql, rows_from_cursor

LONG_SQL = (
    "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL "
    "SELECT x+1 FROM n WHERE x<1000000000) SELECT COUNT(*) AS answer FROM n"
)
NORMAL_SQL = "SELECT 42 AS answer, 1.5 AS fraction, NULL AS absent, x'41' AS blob"
MARKER = "OLD_SQL_NATIVE_EXECUTE_ENTRY"


def program(query):
    return f"rows = execute_sql(query={query!r})"


def fixture_sql(db, *, query_seconds=None, entered=None, release=None):
    """Canonical SQL shape plus progress only; no runtime API/global patch."""
    def execute_sql(*, query):
        conn = connect_readonly(db)
        deadline = None if query_seconds is None else time.monotonic() + query_seconds

        def progress():
            if entered is not None and not entered.is_set():
                entered.set()  # Real SQLite VM activity, not wrapper entry.
                # BOUNDED SCHEDULING GATE ONLY, not evidence of SQL interruption.
                if release is not None:
                    release.wait(.4)
            if deadline is not None:
                return int(time.monotonic() >= deadline)
            return 0  # Hypothesis: Python callback reactivates runtime line tracer.

        try:
            conn.set_progress_handler(progress, 1000)
            try:
                cursor = conn.execute(query)
            except sqlite3.Error as exc:
                raise ProgramRejected(f"{type(exc).__name__}: {exc}") from None
            return rows_from_cursor(cursor, MAX_ROWS)
        finally:
            conn.close()

    return execute_sql


async def owned_program(code, catalog, timeout, *, finished=None, cleanup=None):
    """Fixture intended await pattern, NOT PTCHarness execution."""
    def invoke():
        try:
            return run_program(code, catalog, timeout)
        finally:
            if finished is not None:
                finished.set()

    worker = asyncio.create_task(asyncio.to_thread(invoke))
    try:
        return await asyncio.shield(worker)
    finally:
        new_cancel = None
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as exc:
                new_cancel = exc  # Also own repeated cancellation during join.
            except BaseException:
                break
        try:
            worker.result()  # Retrieve worker error; original outcome stays above.
        except BaseException:
            pass
        if cleanup is not None:
            await cleanup()  # Never swallow a NEW cancellation on normal cleanup.
        if new_cancel is not None:
            raise new_cancel


async def wait_event(event):
    limit = time.monotonic() + .6
    while not event.is_set():
        assert time.monotonic() < limit, "event did not arrive in .6s"
        await asyncio.sleep(.001)


async def ownership_case(db):
    entered, release, finished = (threading.Event() for _ in range(3))
    commits = []
    catalog = Catalog(tools={
        "execute_sql": fixture_sql(db, entered=entered, release=release),
        "commit": lambda *, value: commits.append(value),
    })
    task = asyncio.create_task(owned_program(
        program(LONG_SQL) + "\ncommit(value=rows)", catalog, .1, finished=finished))
    try:
        await wait_event(entered)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not finished.is_set(), "join detached worker"
        # Keep ownership until actual runtime budget expires, then release gate.
        await asyncio.sleep(.12)
        task.cancel()  # Repeated cancellation while joining must not detach.
    finally:
        release.set()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation was lost")
    assert finished.is_set() and commits == [], "worker escaped or committed late"
    # Same catalog, ordinary real runtime, no shared stale query state.
    fresh = await owned_program(program("SELECT 42 AS answer"), catalog, .5)
    assert fresh["rows"] == [{"answer": 42}] and commits == []


async def normal_cleanup_case(db):
    catalog = Catalog(tools={"execute_sql": fixture_sql(db)})
    result = await owned_program(program("SELECT 42 AS answer"), catalog, .5)
    assert result["rows"] == [{"answer": 42}]
    try:
        await owned_program(program("SELECT * FROM missing"), catalog, .5)
    except ProgramRejected as exc:
        assert str(exc).startswith("OperationalError: ")
    else:
        raise AssertionError("ProgramRejected class lost")
    entered, release = asyncio.Event(), asyncio.Event()
    finished = threading.Event()

    async def cleanup():
        entered.set()  # Scheduling-only await after successful real runtime run.
        await asyncio.wait_for(release.wait(), .5)

    task = asyncio.create_task(owned_program(
        program("SELECT 42 AS answer"), catalog, .5,
        finished=finished, cleanup=cleanup))
    await asyncio.wait_for(entered.wait(), .6)
    assert finished.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("new cancellation during normal cleanup swallowed")
    finally:
        release.set()


def child(mode, db):
    if mode == "old":
        # NEGATIVE DIAGNOSTIC ONLY: suppress progress registration. Before the
        # canonical fix no registration existed; afterward this recreates its gap.
        from ptc import sql_arms as canonical
        original_connect = canonical.connect_readonly

        class NoProgress:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def set_progress_handler(self, callback, instructions):
                pass

        canonical.connect_readonly = lambda path: NoProgress(original_connect(path))
        old = make_execute_sql(db)

        def native_entry(frame, event, arg):
            if (event == "c_call" and getattr(arg, "__name__", "") == "execute"
                    and isinstance(getattr(arg, "__self__", None), sqlite3.Connection)):
                print(MARKER, flush=True)  # Inside real old callable, pre-C entry.

        sys.setprofile(native_entry)  # Negative diagnostic only; no SQL patch.
        try:
            run_program(program(LONG_SQL), Catalog(tools={"execute_sql": old}), .1)
        finally:
            sys.setprofile(None)
        raise AssertionError("old long query unexpectedly returned")
    if mode in ("trace", "deadline"):
        progress_seen = threading.Event()
        action = fixture_sql(
            db, query_seconds=.2 if mode == "deadline" else None,
            entered=progress_seen)
        started = time.monotonic()
        try:
            if mode == "trace":
                run_program(program(LONG_SQL), Catalog(tools={"execute_sql": action}), .1)
            else:
                action(query=LONG_SQL)  # Explicit per-query budget outside runtime.
        except ProgramRejected as exc:
            elapsed = time.monotonic() - started
            assert progress_seen.is_set(), "rejected before real SQLite VM activity"
            assert (.15 if mode == "deadline" else .075) <= elapsed < 1, elapsed
            if mode == "deadline":
                assert str(exc).startswith("OperationalError: interrupted")
        else:
            raise AssertionError("long query was not rejected")
    elif mode == "types":
        old, fixed = make_execute_sql(db), fixture_sql(db)
        expected = [{"answer": 42, "fraction": 1.5, "absent": None, "blob": b"A"}]
        for action in (old, fixed):
            rows = run_program(program(NORMAL_SQL), Catalog(tools={"execute_sql": action}), .5)["rows"]
            assert rows == expected and type(rows[0]["answer"]) is int
            assert type(rows[0]["fraction"]) is float and type(rows[0]["blob"]) is bytes
            try:
                run_program(program("SELECT * FROM missing"), Catalog(tools={"execute_sql": action}), .5)
            except ProgramRejected as exc:
                assert str(exc) == "OperationalError: no such table: missing"
            else:
                raise AssertionError("invalid SQL accepted")
    elif mode == "owned":
        asyncio.run(ownership_case(db))
    elif mode == "cleanup":
        asyncio.run(normal_cleanup_case(db))
    elif mode not in ("trace", "deadline"):
        raise AssertionError(mode)
    print(json.dumps({"case": mode, "fixture_gate": "passed"}), flush=True)


def controlled_child(mode, db):
    """Own Popen handle, never accept PID wire authority; bounded kill + drain."""
    proc = subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--child", mode, db],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True, cwd=REPO)
    timed_out = False
    stdout = stderr = ""
    try:
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        # Session/process group belongs only to this Popen. No spawned jobs in child.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=.5)
        finally:
            proc.stdout.close()
            proc.stderr.close()
    if mode == "old":
        assert timed_out and MARKER in stdout, (mode, timed_out, stdout, stderr)
    else:
        assert not timed_out and proc.returncode == 0, (mode, stdout, stderr)
        assert json.loads(stdout)["fixture_gate"] == "passed"
    return {"case": mode, "safety_timeout": timed_out, "fixture_gate": "passed"}


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3])
    else:
        with tempfile.TemporaryDirectory(prefix="ptc-sql-probe-") as temporary:
            db = str(Path(temporary) / "tiny.sqlite")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE tiny(answer INTEGER)")
            conn.commit()
            conn.close()
            for case in ("old", "trace", "deadline", "types", "owned", "cleanup"):
                print(json.dumps(controlled_child(case, db)), flush=True)
        print("MISSING: production SQL fix and ordinary PTCHarness/SDK proof", flush=True)
