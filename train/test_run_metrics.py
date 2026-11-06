"""Scripted offline telemetry, real retention I/O, no training qualification."""

import errno
import importlib
import json
import math
import os

import pytest

from train import verdict as V


def _monitor(retained=False):
    module = importlib.import_module("train.run_monitor")
    monitor = module.RunMonitor()
    if retained:
        for name in ("attach_retention", "close"):
            assert callable(getattr(monitor, name, None)), (
                f"missing RUN metrics retention feature: RunMonitor.{name}"
            )
    return monitor


def _step(**extra):
    return {
        "loss": 0.1,
        V.ZERO_STD_KEY: 0.4,
        V.LOGP_DIFF_KEY: 1.0,
        **extra,
    }


def test_existing_monitor_and_verdict_file_control(tmp_path):
    monitor = _monitor()
    rows = [_step() for _ in range(10)]
    assert [monitor.observe(row) for row in rows] == [None] * 10
    path = tmp_path / "existing-path-control.jsonl"
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in monitor.rows),
        encoding="utf-8",
    )

    loaded = V.load(str(path))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 10
    assert loaded == monitor.rows == rows
    assert monitor.finalize() == V.run_verdict(loaded) == (True, [])


def test_retained_run_reloads_into_existing_verdict(tmp_path, monkeypatch):
    monitor = _monitor(retained=True)
    path = tmp_path / "run.jsonl"
    monitor.attach_retention(str(path))
    identity = (path.stat().st_dev, path.stat().st_ino)
    real_fsync = os.fsync
    synced = []

    def record_real_fsync(descriptor):
        stat = os.fstat(descriptor)
        result = real_fsync(descriptor)
        if (stat.st_dev, stat.st_ino) == identity:
            synced.append(descriptor)
        return result

    monkeypatch.setattr(os, "fsync", record_real_fsync)
    try:
        rows = [_step() for _ in range(10)]
        assert [monitor.observe(row) for row in rows] == [None] * 10
        loaded = V.load(str(path))
        assert len(path.read_text(encoding="utf-8").splitlines()) == 10
        assert loaded == monitor.rows == rows
        assert monitor.finalize() == V.run_verdict(loaded) == (True, [])
        assert len(synced) >= 10
        saved = path.read_bytes()
    finally:
        monitor.close()

    assert path.read_bytes() == saved
    for descriptor in set(synced):
        with pytest.raises(OSError) as error:
            os.fstat(descriptor)
        assert error.value.errno == errno.EBADF


def test_abort_row_is_retained(tmp_path):
    monitor = _monitor(retained=True)
    path = tmp_path / "aborted-run.jsonl"
    monitor.attach_retention(str(path))
    try:
        rows = [_step(**{V.ZERO_STD_KEY: 0.61}) for _ in range(10)]
        assert [monitor.observe(row) for row in rows[:9]] == [None] * 9
        reason = monitor.observe(rows[9])
        assert reason is not None
        assert "steps 0-9" in reason and "10 consecutive" in reason
        loaded = V.load(str(path))
        assert len(loaded) == 10
        assert loaded[-1] == rows[9]
        assert loaded == monitor.rows == rows
        assert reason in V.criterion_a_sustained(loaded)
        assert monitor.finalize() == V.run_verdict(loaded)
        assert monitor.finalize()[0] is False

        summary = {"train_loss": 0.1}
        assert monitor.observe(summary) == reason
        assert monitor.aborted == reason
        assert V.load(str(path)) == rows + [summary] == monitor.rows
        assert len(monitor.rows) == 11
    finally:
        monitor.close()


def test_retention_is_optional_and_create_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    default = _monitor()
    assert [default.observe(_step()) for _ in range(10)] == [None] * 10
    assert default.finalize() == (True, [])
    assert list(tmp_path.iterdir()) == []

    monitor = _monitor(retained=True)
    path = tmp_path / "caller-owned.jsonl"
    sentinel = b"existing caller data\n\x00not ours to truncate\n"
    path.write_bytes(sentinel)
    try:
        with pytest.raises(FileExistsError):
            monitor.attach_retention(str(path))
        assert path.read_bytes() == sentinel
        assert list(tmp_path.iterdir()) == [path]
    finally:
        monitor.close()


def test_retention_lifecycle_rejects_history_loss(tmp_path):
    late = _monitor(retained=True)
    assert late.observe(_step()) is None
    late_path = tmp_path / "late.jsonl"
    try:
        with pytest.raises((ValueError, RuntimeError)):
            late.attach_retention(str(late_path))
        assert not late_path.exists()
        assert late.rows == [_step()]
    finally:
        late.close()

    monitor = _monitor(retained=True)
    path = tmp_path / "once.jsonl"
    second_path = tmp_path / "second.jsonl"
    monitor.attach_retention(str(path))
    try:
        with pytest.raises((ValueError, RuntimeError)):
            monitor.attach_retention(str(second_path))
        assert not second_path.exists()
        assert monitor.observe(_step()) is None
        assert V.load(str(path)) == [_step()]
    finally:
        monitor.close()

    saved = path.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        monitor.observe(_step())
    with pytest.raises((ValueError, RuntimeError)):
        monitor.attach_retention(str(second_path))
    assert not second_path.exists()
    assert path.read_bytes() == saved
    assert monitor.rows == [_step()]


def test_retention_requires_absolute_destination(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monitor = _monitor(retained=True)
    try:
        with pytest.raises(ValueError):
            monitor.attach_retention("relative.jsonl")
        assert list(tmp_path.iterdir()) == []
    finally:
        monitor.close()


def test_retention_snapshots_nonstep_and_nested_rows(tmp_path):
    monitor = _monitor(retained=True)
    path = tmp_path / "snapshots.jsonl"
    monitor.attach_retention(str(path))
    row = _step(extra_telemetry=[{"note": "observed"}])
    try:
        assert monitor.observe({"eval_loss": 0.2}) is None
        assert monitor.observe(row) is None
        row["extra_telemetry"][0]["note"] = "caller mutation"
        snapshot = monitor.rows
        snapshot[1]["extra_telemetry"][0]["note"] = "snapshot mutation"
        assert monitor.observe({"train_loss": 0.1}) is None

        expected = [
            {"eval_loss": 0.2},
            _step(extra_telemetry=[{"note": "observed"}]),
            {"train_loss": 0.1},
        ]
        loaded = V.load(str(path))
        assert len(loaded) == 3
        assert len(V.training_steps(loaded)) == 1
        assert loaded == monitor.rows == expected
        assert monitor.finalize() == V.run_verdict(loaded)
        assert monitor.finalize()[0] is False
    finally:
        monitor.close()


def test_retention_preserves_nonfinite_diagnostics(tmp_path):
    monitor = _monitor(retained=True)
    path = tmp_path / "diagnostics.jsonl"
    monitor.attach_retention(str(path))
    rows = [_step() for _ in range(10)]
    rows[2][V.ZERO_STD_KEY] = float("nan")
    rows[2][V.LOGP_DIFF_KEY] = float("inf")
    try:
        results = [monitor.observe(row) for row in rows]
        assert results[:2] == [None] * 2
        reason = results[2]
        assert reason is not None and V.ZERO_STD_KEY in reason
        assert results[2:] == [reason] * 8
        loaded = V.load(str(path))
        assert len(loaded) == 10
        assert math.isnan(loaded[2][V.ZERO_STD_KEY])
        assert loaded[2][V.LOGP_DIFF_KEY] == float("inf")
        assert loaded[:2] == rows[:2]
        assert loaded[3:] == rows[3:]
        assert set(loaded[2]) == set(rows[2])
        assert loaded[2]["loss"] == rows[2]["loss"]
        assert monitor.aborted == reason
        assert monitor.finalize() == V.run_verdict(loaded)
        assert monitor.finalize()[0] is False
    finally:
        monitor.close()


def test_retention_fsync_failure_propagates(tmp_path, monkeypatch):
    monitor = _monitor(retained=True)
    path = tmp_path / "storage-failure.jsonl"
    monitor.attach_retention(str(path))
    attempts = []

    def fail_fsync(descriptor):
        attempts.append(descriptor)
        raise OSError(errno.EIO, "scripted retention fsync failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", fail_fsync)
            with pytest.raises(OSError) as error:
                monitor.observe(_step())
            assert error.value.errno == errno.EIO
            assert len(attempts) == 1
            with pytest.raises((OSError, RuntimeError, ValueError)):
                monitor.observe(_step())
        assert path.exists()
        assert list(tmp_path.iterdir()) == [path]
    finally:
        try:
            monitor.close()
        except OSError as error:
            assert error.errno == errno.EIO


def test_retention_close_preserves_active_fsync_failure(tmp_path, monkeypatch):
    monitor = _monitor(retained=True)
    path = tmp_path / "primary-and-close-failure.jsonl"
    assert path.is_absolute()
    monitor.attach_retention(str(path))
    writer = monitor._retainer
    real_file = writer._file
    descriptor = real_file.fileno()
    real_fsync = os.fsync
    real_close = type(writer).close
    primary = OSError(errno.EIO, "scripted primary retention fsync failure")
    secondary = OSError(errno.ENOSPC, "scripted secondary retention close failure")
    fsync_attempts = []
    close_attempts = []
    row = _step()

    def fail_after_real_fsync(actual_descriptor):
        assert actual_descriptor == descriptor
        fsync_attempts.append(actual_descriptor)
        real_fsync(actual_descriptor)
        raise primary

    def fail_after_real_close(actual_writer):
        assert actual_writer is writer
        close_attempts.append(descriptor)
        real_close(actual_writer)
        assert real_file.closed
        raise secondary

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_after_real_fsync)
        patch.setattr(type(writer), "close", fail_after_real_close)
        with pytest.raises(OSError) as propagated:
            try:
                monitor.observe(row)
            finally:
                monitor.close()

        assert fsync_attempts == [descriptor]
        assert close_attempts == [descriptor]
        assert real_file.closed
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF
        assert len(path.read_text(encoding="utf-8").splitlines()) == 1
        assert V.load(str(path)) == monitor.rows == [row]
        saved = path.read_bytes()
        with pytest.raises(RuntimeError) as observe_error:
            monitor.observe(_step())
        assert observe_error.value.__cause__ is primary
        with pytest.raises(RuntimeError) as finalize_error:
            monitor.finalize()
        assert finalize_error.value.__cause__ is primary
        assert monitor.rows == [row]
        assert path.read_bytes() == saved
        assert list(tmp_path.iterdir()) == [path]
        assert fsync_attempts == [descriptor]
        assert close_attempts == [descriptor]
        assert propagated.value is primary


def test_retention_standalone_close_failure_propagates(tmp_path, monkeypatch):
    monitor = _monitor(retained=True)
    path = tmp_path / "standalone-close-failure.jsonl"
    assert path.is_absolute()
    monitor.attach_retention(str(path))
    writer = monitor._retainer
    real_file = writer._file
    descriptor = real_file.fileno()
    real_fsync = os.fsync
    real_close = type(writer).close
    failure = OSError(errno.EIO, "scripted first retention close failure")
    fsync_attempts = []
    close_attempts = []
    row = _step()

    def record_real_fsync(actual_descriptor):
        assert actual_descriptor == descriptor
        fsync_attempts.append(actual_descriptor)
        return real_fsync(actual_descriptor)

    def fail_after_real_close(actual_writer):
        assert actual_writer is writer
        close_attempts.append(descriptor)
        real_close(actual_writer)
        assert real_file.closed
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", record_real_fsync)
        try:
            assert monitor.observe(row) is None
            assert fsync_attempts == [descriptor]
            assert len(path.read_text(encoding="utf-8").splitlines()) == 1
            assert V.load(str(path)) == monitor.rows == [row]
            saved = path.read_bytes()
        finally:
            patch.setattr(type(writer), "close", fail_after_real_close)
            with pytest.raises(OSError) as propagated:
                monitor.close()

        assert propagated.value is failure
        assert close_attempts == [descriptor]
        assert real_file.closed
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF
        with pytest.raises(RuntimeError) as observe_error:
            monitor.observe(_step())
        assert observe_error.value.__cause__ is failure
        with pytest.raises(RuntimeError) as finalize_error:
            monitor.finalize()
        assert finalize_error.value.__cause__ is failure
        assert monitor.rows == [row]
        assert path.read_bytes() == saved
        assert list(tmp_path.iterdir()) == [path]
        assert fsync_attempts == [descriptor]
        assert close_attempts == [descriptor]
