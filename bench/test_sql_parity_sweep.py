"""A timed-out invocation must never replace another task's SQL wrapper."""

from __future__ import annotations

import sqlite3
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

from bench import sql_parity_sweep as sweep
from bench.task import SqlTask
from ptc.sql_arms import SQL_TOOL, install_wrapper


def _task(tmp_path: Path, number: int) -> SqlTask:
    database = tmp_path / f"task-{number}.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE fixture(value INTEGER)")
        connection.execute("INSERT INTO fixture VALUES (?)", (number,))
    return SqlTask(
        name=f"fixture-{number}", question="Read the value", evidence="",
        gold_sql="SELECT value FROM fixture", db_id=f"fixture-{number}",
        db_path=str(database), tier="simple", tier_source="annotated",
        shape="select", coarse_shape="select", source="fixture",
    )


def _result(agreed: bool = True):
    return SimpleNamespace(
        agreed=agreed, capped=False,
        bash=SimpleNamespace(outcome="rows", n_rows=1),
        ptc=SimpleNamespace(outcome="rows", n_rows=1),
        delivery_causes=() if agreed else ("wrong_database",),
        render_causes=(), note="",
    )


def test_late_timed_out_wrapper_cannot_replace_the_next_task(
        tmp_path, monkeypatch):
    first, second = _task(tmp_path, 1), _task(tmp_path, 2)
    started = threading.Event()
    release = threading.Event()
    installed = threading.Event()
    threads = []
    directories = {}
    observed = []
    original_deadline = sweep._with_deadline
    invocations = 0

    def bounded_deadline(fn, timeout):
        nonlocal invocations
        invocations += 1
        return original_deadline(fn, 0.01 if invocations == 1 else 5.0)

    def delayed_differential(task, *, bindir, compare, max_rows):
        threads.append(threading.current_thread())
        directories[task.name] = bindir
        if task.name == first.name:
            started.set()
            if not release.wait(2.0):
                raise TimeoutError("test did not release the delayed invocation")
            install_wrapper(bindir, task.db_path, max_rows)
            installed.set()
            return _result()
        install_wrapper(bindir, task.db_path, max_rows)
        release.set()
        if not installed.wait(2.0):
            raise TimeoutError("delayed invocation did not install its wrapper")
        result = subprocess.run(
            [str(bindir / SQL_TOOL), task.gold_sql],
            capture_output=True, text=True, timeout=2.0, check=False,
        )
        observed.append(result)
        return _result(result.returncode == 0 and
                       result.stdout.splitlines() == ["value", "2"])

    monkeypatch.setattr(sweep, "_with_deadline", bounded_deadline)
    monkeypatch.setattr(sweep, "differential", delayed_differential)
    parent = tmp_path / "worker"
    try:
        timeout_row = sweep._one(first, parent, "set", 10)
        assert timeout_row["delivery_causes"] == ["sweep_timeout"]
        assert started.wait(2.0)
        assert directories[first.name].exists()
        current_row = sweep._one(second, parent, "set", 10)
        assert current_row["agreed"], observed
        assert directories[first.name] != directories[second.name]
    finally:
        release.set()
        for thread in threads:
            thread.join(2.0)
        assert all(not thread.is_alive() for thread in threads)
    assert all(not directory.exists() for directory in directories.values())


def test_completed_invocations_use_distinct_cleaned_directories(
        tmp_path, monkeypatch):
    task = _task(tmp_path, 1)
    directories = []

    def differential(task, *, bindir, compare, max_rows):
        assert bindir.is_dir()
        directories.append(bindir)
        install_wrapper(bindir, task.db_path, max_rows)
        return _result()

    monkeypatch.setattr(sweep, "differential", differential)
    parent = tmp_path / "worker"
    for _ in range(2):
        assert sweep._one(task, parent, "set", 10)["agreed"]
    assert len(set(directories)) == 2
    assert all(directory.parent == parent for directory in directories)
    assert all(not directory.exists() for directory in directories)
    assert parent.is_dir()


def test_failed_invocation_cleans_only_its_private_directory(
        tmp_path, monkeypatch):
    task = _task(tmp_path, 1)
    directories = []
    parent = tmp_path / "worker"
    parent.mkdir()
    sentinel = parent / "unrelated"
    sentinel.write_text("preserve")

    def differential(task, *, bindir, compare, max_rows):
        directories.append(bindir)
        (bindir / "partial").write_text("partial wrapper")
        raise ValueError("fixture failure")

    monkeypatch.setattr(sweep, "differential", differential)
    row = sweep._one(task, parent, "multiset", 10)
    assert row["error"] == "ValueError: fixture failure"
    assert len(directories) == 1
    assert not directories[0].exists()
    assert sentinel.read_text() == "preserve"


def test_non_timeout_failure_is_not_labeled_as_a_sweep_timeout(
        tmp_path, monkeypatch):
    task = _task(tmp_path, 1)

    def differential(*args, **kwargs):
        raise ValueError("not a deadline")

    monkeypatch.setattr(sweep, "differential", differential)
    row = sweep._one(task, tmp_path / "worker", "set", 10)
    assert row["delivery_causes"] == ["sweep_error"]
    assert sweep.summarise([row], compare="set")["timeouts"] == []
