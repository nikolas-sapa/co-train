"""Descriptive UNVERIFIED archive diagnostics from real, scripted SQLite capture."""

from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import importlib
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from bench.frontier.probe import ProbeResult, dead_group_fraction
from bench.frontier.sample_capture import CaptureSession
from bench.frontier.test_sample_capture import _limits, _stage
from train import frontier_transport as transport


def _api():
    name = "bench.frontier.archive_report"
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        pytest.fail("missing feature: bench.frontier.archive_report", pytrace=False)
    for export in ("read_archive_report", "render_archive_report"):
        assert callable(getattr(module, export, None)), f"missing feature: {export}"
    return module


@pytest.fixture(scope="module")
def archives(tmp_path_factory):
    directory = tmp_path_factory.mktemp("archive-report")
    staged = _stage(directory)
    captures, calls = [], []
    for split in (False, True):
        slots = {}
        wins = dict(zip(staged.plan.eligible_ids, (0, 0, 4, 4, 2, 2, 2)))

        def scripted_generate(task):
            slot = slots.get(task.name, 0)
            slots[task.name] = slot + 1
            calls.append((split, task.name, slot))
            success = slot < (wins[task.name] if split else 2)
            return f"```sql\n{task.gold_sql if success else 'SELECT -98765'}\n```"

        session = CaptureSession(staged.plan, b"inventory", limits=_limits())
        captured = session.run(
            staged.root, staged.draw, staged.supplement, scripted_generate,
            expected_draw_sha256=staged.plan.draw_sha256,
            expected_supplement_sha256=staged.plan.supplement_sha256, fixture=True)
        assert len(captured.batch.samples) == 28
        assert captured.report.all_samples_validly_scored
        captures.append(captured)
    path = directory / "retained.json"
    digest = transport.write_unverified_bindings(
        staged.plan, captures[0].retention_pins, captures[0].batch,
        path, limits=_limits())
    return SimpleNamespace(staged=staged, balanced=captures[0], split=captures[1],
                           path=path, digest=digest, calls=calls)


def _write(tmp_path, captured, batch=None):
    batch = captured.batch if batch is None else batch
    path = tmp_path / "retained.json"
    digest = transport.write_unverified_bindings(
        batch.plan, captured.retention_pins, batch, path, limits=_limits())
    return path, digest


def _read(api, path, digest, **changes):
    kwargs = dict(expected_archive_sha256=digest, limits=_limits(), dead_ceiling=0.6)
    kwargs.update(changes)
    return api.read_archive_report(path, **kwargs)


def _eligible_rows(report, plan):
    assert type(report.tasks) is tuple
    assert tuple(row.task_ordinal for row in report.tasks) == tuple(range(len(plan.tasks)))
    return {task.task_id: row for task, row in zip(plan.tasks, report.tasks, strict=True)
            if task.task_id in plan.eligible_ids}


def _unavailable(row, state):
    assert row.state == state
    assert row.solve_rate is None
    assert row.dead_fraction is None
    assert row.retained is None


def _counts(report, *, observed=28):
    binding = report.binding_report
    assert (binding.planned_tasks, binding.eligible_tasks, binding.excluded_tasks) == (8, 7, 1)
    assert (binding.scheduled_slots, binding.observed_slots) == (28, observed)


def test_existing_capture_archive_control(archives):
    captured = archives.balanced
    loaded = transport.load_unverified_bindings(
        archives.path, expected_archive_sha256=archives.digest, limits=_limits())
    assert loaded.report == captured.report
    assert loaded.report.total_issues == 0
    assert len(loaded.batch.samples) == loaded.report.valid_declared_scores == 28
    assert len(loaded.retention_pins) == len(loaded.batch.blobs) == 57
    assert (loaded.report.planned_tasks, loaded.report.eligible_tasks,
            loaded.report.excluded_tasks) == (8, 7, 1)
    assert captured.result.rates == dict.fromkeys(loaded.plan.eligible_ids, 0.5)
    assert len(archives.calls) == 56


def test_reload_recovers_original_task_rates(archives):
    api = _api()
    report = _read(api, archives.path, archives.digest)
    plan, original = archives.staged.plan, archives.balanced.result
    _counts(report)
    assert report.binding_report == archives.balanced.report
    rows = _eligible_rows(report, plan)
    assert {name: row.solve_rate for name, row in rows.items()} == original.rates
    for name, row in rows.items():
        assert row.state == "complete"
        assert row.dead_fraction == dead_group_fraction(original.rates[name], 4)
        assert row.retained is (name in original.retained)
    excluded = set(range(8)) - {row.task_ordinal for row in rows.values()}
    assert len(excluded) == 1
    _unavailable(report.tasks[excluded.pop()], "excluded")
    assert report.g == 4 and report.dead_ceiling == 0.6
    assert (report.n_complete_tasks, report.n_retained_tasks, report.retention) == (7, 7, 1.0)
    stricter = _read(api, archives.path, archives.digest, dead_ceiling=0.1)
    assert stricter.dead_ceiling == 0.1
    assert (stricter.n_complete_tasks, stricter.n_retained_tasks, stricter.retention) == (7, 0, 0.0)
    assert all(row.retained is False for row in _eligible_rows(stricter, plan).values())


def _four_tasks(captured):
    batch = captured.batch
    ids = batch.plan.eligible_ids[:4]
    plan = replace(batch.plan, tasks=tuple(t for t in batch.plan.tasks if t.task_id in ids),
                   eligible_ids=ids, exclusions=())
    samples = tuple(s for s in batch.samples if s.task_id in ids)
    evidence = {reference for sample in samples
                for reference in (sample.generation_evidence_id, sample.scoring_evidence_id)}
    evidence.update(pin.evidence_id for pin in captured.retention_pins
                    if pin.purpose == "checkpoint")
    pins = tuple(pin for pin in captured.retention_pins if pin.evidence_id in evidence)
    blobs = tuple(blob for blob in batch.blobs if blob.evidence_id in evidence)
    return SimpleNamespace(batch=replace(batch, plan=plan, samples=samples, blobs=blobs),
                           retention_pins=pins)


def test_equal_marginals_preserve_different_retention(archives, tmp_path):
    api = _api()
    reports = []
    for name in ("balanced", "split"):
        captured = _four_tasks(getattr(archives, name))
        directory = tmp_path / name
        directory.mkdir()
        path, digest = _write(directory, captured)
        report = _read(api, path, digest)
        assert report.binding_report.all_samples_validly_scored
        assert report.binding_report.scheduled_slots == 16
        assert len(report.tasks) == report.n_complete_tasks == 4
        reports.append(report)
    balanced, split = reports
    assert tuple(row.solve_rate for row in balanced.tasks) == (0.5,) * 4
    assert tuple(row.solve_rate for row in split.tasks) == (0.0, 0.0, 1.0, 1.0)
    for report in reports:
        assert sum(row.solve_rate for row in report.tasks) / 4 == 0.5
        assert tuple(row.retained for row in report.tasks) == tuple(
            dead_group_fraction(row.solve_rate, 4) <= 0.6 for row in report.tasks)
    assert (balanced.n_retained_tasks, split.n_retained_tasks) == (4, 0)
    assert (balanced.retention, split.retention) == (1.0, 0.0)


def test_missing_slot_never_becomes_zero(archives, tmp_path):
    api = _api()
    captured = archives.balanced
    missing = captured.batch.samples[0]
    batch = replace(captured.batch, samples=captured.batch.samples[1:])
    path, digest = _write(tmp_path, captured, batch)
    report = _read(api, path, digest)
    _counts(report, observed=27)
    assert dict(report.binding_report.disposition_counts)["missing"] == 1
    rows = _eligible_rows(report, batch.plan)
    _unavailable(rows.pop(missing.task_id), "missing")
    assert len(rows) == report.n_complete_tasks == report.n_retained_tasks == 6
    assert all(row.state == "complete" and row.solve_rate == 0.5 for row in rows.values())
    assert report.retention is None


@pytest.mark.parametrize("case", ("invalid_gold", "missing_scoring_blob"))
def test_invalid_scoring_remains_unavailable(archives, tmp_path, case):
    api = _api()
    captured = archives.balanced
    first = captured.batch.samples[0]
    if case == "invalid_gold":
        sample = replace(first, status="invalid_gold", score=None)
        batch = replace(captured.batch, samples=(sample,) + captured.batch.samples[1:])
    else:
        batch = replace(captured.batch, blobs=tuple(
            blob for blob in captured.batch.blobs if blob.evidence_id != first.scoring_evidence_id))
    path, digest = _write(tmp_path, captured, batch)
    report = _read(api, path, digest)
    _counts(report)
    assert report.binding_report.valid_declared_scores == 27
    rows = _eligible_rows(report, batch.plan)
    _unavailable(rows.pop(first.task_id), "invalid")
    assert len(rows) == report.n_complete_tasks == report.n_retained_tasks == 6
    assert all(row.state == "complete" and row.solve_rate == 0.5 for row in rows.values())
    assert report.retention is None


def _frozen_tree(value):
    assert not isinstance(value, (dict, list, set, bytearray))
    if is_dataclass(value):
        assert value.__dataclass_params__.frozen
        for field in fields(value):
            _frozen_tree(getattr(value, field.name))
    elif type(value) is tuple:
        for item in value:
            _frozen_tree(item)


def test_report_is_immutable_and_unverified(archives):
    api = _api()
    report = _read(api, archives.path, archives.digest)
    assert is_dataclass(report) and len(report.tasks) == 8
    _frozen_tree(report)
    with pytest.raises(FrozenInstanceError):
        report.retention = 0.0
    for row in report.tasks:
        assert is_dataclass(row)
        with pytest.raises(FrozenInstanceError):
            row.solve_rate = 0.0
    assert report.provenance == "unverified" and report.attested_facts == ()
    assert report.genuine_measurement_accepted is False
    assert report.training_authorized is False
    assert not isinstance(report, ProbeResult)
    assert not hasattr(report, "manifest") and not hasattr(report, "result")


def test_reader_uses_pin_limits_without_execution_or_writes(archives, monkeypatch):
    api = _api()
    raw, calls = archives.path.read_bytes(), tuple(archives.calls)
    real_open, real_os_open = builtins.open, os.open

    def forbidden(*args, **kwargs):
        pytest.fail("archive reader attempted execution or write")

    def read_only_open(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        return real_open(file, mode, *args, **kwargs)

    def read_only_os_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return real_os_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(sqlite3.dbapi2, "connect", forbidden)
        patch.setattr(importlib.import_module("bench.score"), "execution_accuracy", forbidden)
        patch.setattr(importlib.import_module("bench.frontier.probe"), "execution_accuracy", forbidden)
        patch.setattr(builtins, "open", read_only_open)
        patch.setattr(os, "open", read_only_os_open)
        for method in ("write_bytes", "write_text", "touch", "mkdir"):
            patch.setattr(Path, method, forbidden)
        for method in ("write", "link", "rename", "replace", "mkdir"):
            patch.setattr(os, method, forbidden)
        report = _read(api, archives.path, archives.digest)
        rendered = api.render_archive_report(report)
        bad_pin = ("0" if archives.digest[0] != "0" else "1") + archives.digest[1:]
        with pytest.raises(transport.TransportError):
            _read(api, archives.path, bad_pin)
        with pytest.raises(transport.TransportError):
            _read(api, archives.path, archives.digest, limits=_limits(max_planned_tasks=7))
    assert archives.path.read_bytes() == raw and tuple(archives.calls) == calls
    assert "UNVERIFIED" in rendered and "descriptive" in rendered.lower()
    public = rendered + repr(report) + repr(report.tasks)
    sensitive = [str(archives.path), str(archives.staged.root), "absent_capture_table",
                 "SELECT -98765", "private generator exception"]
    sensitive.extend(task.question for task in archives.staged.admitted.planned)
    sensitive.extend(task.gold_sql for task in archives.staged.admitted.planned)
    assert all(text not in public for text in sensitive if text)
