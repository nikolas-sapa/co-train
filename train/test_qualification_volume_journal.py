"""V311 SOURCE-ONLY MUTATIONAL RED journal regressions. NOT RUN.

Tiny owned journal I/O only, never a training/throughput/input-reduction claim.
No huge test or historical successful test body is collected or called.
Parent alone stages, counts actual collection, runs, and reviews RED/GREEN.
"""
import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from train import test_qualification_ac_volume as volume

prohibit_real_effects = volume.prohibit_real_effects

# Exactly one UNKNOWN test keeps one bounded actual generation plus ancestry.
# Do not close, probe, recycle, or "dispose" its uncertain numeric descriptor.
_RETAINED_UNKNOWN = []


@pytest.fixture
def journal_root(tmp_path, monkeypatch):
    # Resolve/create all pytest paths BEFORE installing any syscall failure seam.
    path = tmp_path.resolve() / "journal-root"
    path.mkdir(mode=0o700)
    custody = volume._OwnedCustody()
    with monkeypatch.context() as patch:
        patch.setattr(volume, "_OWNED", custody)
        anchors = volume._Anchors()
        root_fd = anchors.root(str(path))
        context = SimpleNamespace(
            path=path, custody=custody, anchors=anchors, root_fd=root_fd,
            patch=patch, journal=None)
        try:
            yield context
        finally:
            unresolved = any(row["state"] in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")
                             for row in custody.records)
            if unresolved:
                _RETAINED_UNKNOWN.append(context)
            else:
                anchors.close()


def new_journal(context):
    journal = volume._ProgressJournal(context.root_fd, context.anchors)
    context.journal = journal
    return journal


def rows(context):
    raw = (context.path / "v311-progress.jsonl").read_bytes()
    return raw, [json.loads(line) for line in raw.splitlines()]


def owned_row(context, fd):
    return next(row for row in reversed(context.custody.records) if row["fd"] == fd)


def test_journal_actual_fd_canonical_visible_before_close_ordered(journal_root):
    j = new_journal(journal_root)
    j.record("install-enter")
    j.record("install-exit", bulk_bytes=19, key=volume.KEYS[0])
    raw, records = rows(journal_root)  # Actual pathname read while writer is OPEN.
    assert raw == b"".join(volume._canonical(row) + b"\n" for row in records)
    assert len(records) == j.record_count == 2
    assert j.byte_reserved == len(raw) <= 32768
    assert all(set(row) == {"seq", "stage", "wall_ns", "cpu_ns", "bulk_bytes", "key"}
               for row in records)
    assert [row["seq"] for row in records] == [0, 1]
    for name in ("wall_ns", "cpu_ns"):
        assert 0 <= records[0][name] <= records[1][name]
    assert all(len(line) + 1 <= 1024 for line in raw.splitlines())
    info = os.fstat(j.fd)
    assert info.st_mode & 0o777 == 0o600 and info.st_nlink == 1
    assert info.st_uid == os.getuid()
    assert owned_row(journal_root, j.fd)["state"] == "OPEN"


def test_journal_exclusive_leaf_never_reuses_existing(journal_root):
    j = new_journal(journal_root)
    j.record("install-enter")
    before = rows(journal_root)[0]
    with pytest.raises(FileExistsError):
        new_journal(journal_root)
    assert rows(journal_root)[0] == before
    assert journal_root.custody.records[-1]["state"] == "NO_FD"
    j.close()


def test_journal_reserves_and_attaches_actual_fd_before_fstat(journal_root, monkeypatch):
    actual_open, actual_fstat = os.open, os.fstat
    observations = []

    def opened(path, flags, mode=0o777, *, dir_fd=None):
        if path == "v311-progress.jsonl":
            row = journal_root.custody.records[-1]
            assert row["state"] == "RESERVED" and row["fd"] is None
            assert row["parent"] is owned_row(journal_root, journal_root.root_fd)
            assert flags & os.O_EXCL and flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
            assert mode == 0o600 and dir_fd == journal_root.root_fd
            fd = actual_open(path, flags, mode, dir_fd=dir_fd)
            observations.append(fd)
            return fd
        return actual_open(path, flags, mode, dir_fd=dir_fd)

    def fstat(fd):
        if observations and fd == observations[-1]:
            assert owned_row(journal_root, fd)["state"] == "OPEN"
        return actual_fstat(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opened)
        patch.setattr(os, "fstat", fstat)
        j = new_journal(journal_root)
    assert observations == [j.fd]


def test_journal_fstat_failure_keeps_acquired_generation_for_cleanup(journal_root, monkeypatch):
    actual_fstat = os.fstat
    primary = OSError("journal initial fstat")
    acquired = []

    def fstat(fd):
        row = journal_root.custody.records[-1]
        if row["fd"] == fd and row["parent"] is owned_row(journal_root, journal_root.root_fd):
            acquired.append(fd)
            assert row["state"] == "OPEN"
            raise primary
        return actual_fstat(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", fstat)
        with pytest.raises(OSError) as caught:
            new_journal(journal_root)
    assert caught.value is primary and len(acquired) == 1
    row = owned_row(journal_root, acquired[0])
    assert row["state"] == "OPEN"
    journal_root.anchors.close()
    assert row["state"] == "CLOSED"


def test_journal_record_129_refused_before_any_write(journal_root, monkeypatch):
    j = new_journal(journal_root)
    for _ in range(128):
        j.record("progress")
    calls = []
    actual_write = os.write

    def write(fd, raw):
        if fd == j.fd:
            calls.append(bytes(raw))
        return actual_write(fd, raw)

    before = rows(journal_root)[0]
    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        with pytest.raises(ValueError, match="^journal record budget$"):
            j.record("progress")
    assert calls == [] and rows(journal_root)[0] == before
    assert j.record_count == 128  # INITIAL RED must fail at the raises assertion.


def test_journal_byte_cap_refused_before_any_write(journal_root, monkeypatch):
    j = new_journal(journal_root)
    j.record("progress")
    # Explicit reserved-accounting seam: budget is already fully committed.
    # Keeps this guard independent of the 128-record guard and record length.
    j.byte_reserved = 32768
    actual_write, calls = os.write, []

    def write(fd, raw):
        if fd == j.fd:
            calls.append(bytes(raw))
        return actual_write(fd, raw)

    before = rows(journal_root)[0]
    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        with pytest.raises(ValueError, match="^journal byte budget$"):
            j.record("progress")
    assert calls == [] and rows(journal_root)[0] == before
    assert j.byte_reserved == 32768 and j.record_count == 1


@pytest.mark.parametrize("bad", ("arbitrary-payload", 1, {"payload": "private"}))
def test_journal_invalid_stage_refused_without_write(journal_root, bad):
    j = new_journal(journal_root)
    with pytest.raises(ValueError, match="^journal stage$"):
        j.record(bad)
    assert j.record_count == j.byte_reserved == 0 and rows(journal_root)[0] == b""


@pytest.mark.parametrize("bad", ("../payload", 1, {"key": "private"}))
def test_journal_invalid_key_refused_without_write(journal_root, bad):
    j = new_journal(journal_root)
    with pytest.raises(ValueError, match="^journal key$"):
        j.record("progress", key=bad)
    assert j.record_count == j.byte_reserved == 0 and rows(journal_root)[0] == b""


@pytest.mark.parametrize("bad", (-1, volume.TOTAL_BYTES + 1, True, 1.0, b"payload"))
def test_journal_invalid_bulk_count_refused_without_write(journal_root, bad):
    j = new_journal(journal_root)
    with pytest.raises(ValueError, match="^journal bulk byte count$"):
        j.record("progress", bulk_bytes=bad)
    assert j.record_count == j.byte_reserved == 0 and rows(journal_root)[0] == b""


def test_journal_extra_payload_keyword_refused(journal_root):
    j = new_journal(journal_root)
    with pytest.raises(TypeError):
        j.record("progress", payload=b"never-log")
    assert j.record_count == j.byte_reserved == 0 and rows(journal_root)[0] == b""


def test_journal_1024_byte_record_limit_precedes_write(journal_root, monkeypatch):
    j = new_journal(journal_root)
    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(volume, "_canonical", lambda value: b"x" * 1024)
        patch.setattr(os, "write", lambda *args: calls.append(args))
        with pytest.raises(ValueError, match="^journal record size$"):
            j.record("progress")
    assert calls == [] and j.record_count == j.byte_reserved == 0


def test_journal_short_writes_only_remaining_suffix_no_duplicate_clock(journal_root, monkeypatch):
    j = new_journal(journal_root)
    actual_write = os.write
    passed, counts, clocks = [], [], []

    def write(fd, raw):
        if fd != j.fd:
            return actual_write(fd, raw)
        passed.append(bytes(raw))
        count = actual_write(fd, raw[:7])
        counts.append(count)
        return count

    def wall():
        clocks.append("wall")
        return 123

    def cpu():
        clocks.append("cpu")
        return 45

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        patch.setattr(volume.time, "monotonic_ns", wall)
        patch.setattr(volume.time, "process_time_ns", cpu)
        patch.setattr(os, "fsync", lambda fd: pytest.fail("journal fsync forbidden"))
        j.record("progress", bulk_bytes=7, key=volume.KEYS[0])
        j.close()
    raw, records = rows(journal_root)
    assert len(passed) > 1
    offset = 0
    for supplied, count in zip(passed, counts):
        assert supplied == raw[offset:]
        offset += count
    assert offset == len(raw) == j.byte_reserved
    assert records[0]["wall_ns"] == 123 and records[0]["cpu_ns"] == 45
    assert clocks == ["wall", "cpu"]


@pytest.mark.parametrize("fault", ("zero", "error", "partial-then-error"))
def test_journal_write_uncertainty_terminal_actual_error_retained(journal_root, monkeypatch, fault):
    j = new_journal(journal_root)
    primary = OSError("journal actual injected write error")
    actual_write, calls = os.write, []

    def write(fd, raw):
        if fd != j.fd:
            return actual_write(fd, raw)
        calls.append(bytes(raw))
        # Budget reservation precedes even the first uncertain syscall.
        assert j.record_count == 1 and j.byte_reserved >= len(raw)
        if fault == "zero":
            return 0
        if fault == "partial-then-error" and len(calls) == 1:
            return actual_write(fd, raw[:5])
        raise primary

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        with pytest.raises((OSError, ValueError)) as caught:
            j.record("progress")
        actual_error = caught.value
        if fault != "zero":
            assert actual_error is primary
        assert j.error is actual_error and j.errors == [actual_error]
        count = len(calls)
        with pytest.raises(type(actual_error)) as again:
            j.record("eof")
        assert again.value is actual_error
        volume._journal_observe(j, "release-enter")
        assert len(calls) == count
    raw = (journal_root.path / "v311-progress.jsonl").read_bytes()
    assert raw == (calls[0][:5] if fault == "partial-then-error" else b"")
    assert len(calls) == (2 if fault == "partial-then-error" else 1)


@pytest.mark.parametrize("count", (-1, 2000))
def test_journal_invalid_write_count_terminal(journal_root, monkeypatch, count):
    j = new_journal(journal_root)
    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(os, "write", lambda fd, raw: calls.append(bytes(raw)) or count)
        with pytest.raises(ValueError, match="journal write made invalid progress") as caught:
            j.record("progress")
        volume._journal_observe(j, "release-enter")
    assert len(calls) == 1 and j.error is caught.value


def test_journal_healthy_close_once_through_same_custody(journal_root, monkeypatch):
    j = new_journal(journal_root)
    actual_close, calls = os.close, []

    def close(fd):
        calls.append(fd)
        return actual_close(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", close)
        j.close()
        j.close()
    assert calls == [j.fd] and owned_row(journal_root, j.fd)["state"] == "CLOSED"
    assert j.close_attempted and j.close_error is None
    with pytest.raises(ValueError, match="journal already closed"):
        j.record("progress")


def test_journal_unknown_close_preserves_primary_ancestors_no_retry_probe(journal_root, monkeypatch):
    j = new_journal(journal_root)
    j.record("progress")
    primary, secondary = ValueError("actual primary"), OSError("actual close failure")
    actual_close, actual_fstat, actual_open = os.close, os.fstat, os.open
    close_calls, probes, opens = [], [], []
    attempted = [False]

    def close(fd):
        close_calls.append(fd)
        if fd == j.fd:
            attempted[0] = True
            raise secondary  # One bounded genuinely-open UNKNOWN generation.
        return actual_close(fd)

    def fstat(fd):
        if attempted[0]:
            probes.append(fd)
            raise AssertionError("no probing after UNKNOWN")
        return actual_fstat(fd)

    def opened(*args, **kwargs):
        if attempted[0]:
            opens.append((args, kwargs))
            raise AssertionError("no open after UNKNOWN")
        return actual_open(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", close)
        patch.setattr(os, "fstat", fstat)
        patch.setattr(os, "open", opened)
        try:
            raise primary
        except ValueError as original_error:
            j.close()  # Preserve active primary even without an explicit argument.
            assert original_error is primary
        j.close(primary)
        for _ in range(2):
            with pytest.raises(OSError) as caught:
                journal_root.anchors.close()
            assert caught.value is secondary
        with pytest.raises(RuntimeError, match="unresolved"):
            journal_root.custody.open("never-opened", os.O_RDONLY,
                                     dir_fd=journal_root.root_fd)
    row = owned_row(journal_root, j.fd)
    assert row["state"] == "UNKNOWN" and row["error"] is secondary
    assert j.close_error is j.error is secondary and j.errors == [secondary]
    assert any("journal close failed" in note for note in primary.__notes__)
    parent = row["parent"]
    assert parent is owned_row(journal_root, journal_root.root_fd)
    while parent is not None:
        assert parent["state"] == "OPEN"
        parent = parent["parent"]
    assert close_calls == [j.fd] and probes == opens == []
    # The fixture retains this context in _RETAINED_UNKNOWN, no numeric-FD cleanup.


@pytest.mark.parametrize("enabled", (False, True))
def test_journal_sync_forwards_all_arguments_return_identity(journal_root, enabled):
    j = new_journal(journal_root) if enabled else None
    sentinel, argument, calls = object(), object(), []
    keywords = dict(journal=argument, key=argument, stage=argument, observer=argument)

    def actual(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    result = volume._journal_sync(j, "install", None, actual, argument, **keywords)
    assert result is sentinel and calls == [((argument,), keywords)]
    if enabled:
        assert [row["stage"] for row in rows(journal_root)[1]] == [
            "install-enter", "install-exit"]


@pytest.mark.parametrize("enabled", (False, True))
def test_journal_async_forwards_all_arguments_exception_identity(journal_root, enabled):
    j = new_journal(journal_root) if enabled else None
    primary, argument, calls = RuntimeError("actual async failure"), object(), []
    keywords = dict(journal=argument, key=argument, stage=argument, observer=argument)

    async def actual(*args, **kwargs):
        calls.append((args, kwargs))
        raise primary

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(volume._journal_async(j, "c", None, actual, argument, **keywords))
    assert caught.value is primary and calls == [((argument,), keywords)]
    if enabled:
        assert j.operation_errors == [("c", primary)]
        assert [row["stage"] for row in rows(journal_root)[1]] == ["c-enter", "c-error"]


def test_journal_write_failure_cannot_replace_original_operation_error(journal_root, monkeypatch):
    j = new_journal(journal_root)
    primary, diagnostic = RuntimeError("actual original error"), OSError("journal write")
    writes = []

    def write(fd, raw):
        writes.append(fd)
        raise diagnostic

    def actual():
        raise primary

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        with pytest.raises(RuntimeError) as caught:
            volume._journal_sync(j, "release", None, actual)
    assert caught.value is primary and j.error is diagnostic
    assert j.errors == [diagnostic] and j.operation_errors == [("release", primary)]
    assert writes == [j.fd]


def test_journal_installed_hooks_keep_original_calls_and_32_progress_records(journal_root, monkeypatch):
    """Namespace-only installer seams. Integer cadence, NOT an 8GiB read."""
    j = new_journal(journal_root)
    sentinel, prepared = object(), object()
    record = SimpleNamespace(kind="descriptor", handle=object(), closed=False)
    reader = SimpleNamespace(_file=SimpleNamespace(record=record))
    registry = SimpleNamespace(records=[record])
    calls = []
    c = SimpleNamespace(request=object())
    o = SimpleNamespace(
        _registry=registry, _allocate_worker=lambda: sentinel, _lease=object(),
        _close_validation=lambda: calls.append(("close-validation",)) or sentinel,
        _validated=None, _validation_closed=True,
        take_validated_original=lambda **kwargs: calls.append(("publication", kwargs)) or sentinel)
    record.anchor = o._lease
    fake_anchors = SimpleNamespace(child=lambda *args, **kwargs: object())
    data = SimpleNamespace(evidence={}, outcome=b"tiny")
    read_result = [b"x"]
    identity_failure = [None]

    async def validate(validator, lease):
        calls.append(("validate", validator, lease))
        return sentinel

    validate.__module__ = volume.adapter.__name__

    def receipt(*args, **kwargs):
        calls.append(("receipt", args, kwargs))
        return sentinel

    def open_export(lease, key):
        calls.append(("open", lease, key))
        return reader

    async def read(actual_reader, maximum):
        calls.append(("read", actual_reader, maximum))
        return read_result[0]

    async def inventory(lease):
        calls.append(("inventory", lease))
        return ()

    async def identity(actual_reader):
        calls.append(("identity", actual_reader))
        if identity_failure[0] is not None:
            raise identity_failure[0]
        return sentinel

    with monkeypatch.context() as patch:
        patch.setattr(volume.base, "register", lambda *args: (prepared, None))
        patch.setattr(volume.base, "install_mocked_lifecycle", lambda *args: ([], {}, {}))
        patch.setattr(volume, "_documents", lambda *args: data)
        patch.setattr(volume, "_move_inputs", lambda *args: [])
        patch.setattr(volume.adapter._ParentValidator, "validate", validate)
        patch.setattr(volume.original, "_validate_receipt", receipt)
        patch.setattr(volume.api.ParentReadLease, "open_export", open_export)
        patch.setattr(volume.api.RegisteredReader, "read", read)
        patch.setattr(volume.api.ParentReadLease, "export_inventory", inventory)
        patch.setattr(volume.api.RegisteredReader, "check_identity", identity)
        audit = volume._install(c, o, {}, object(), object(), fake_anchors, patch, journal=j)
        assert audit.prepared is prepared
        assert asyncio.run(volume.adapter._ParentValidator.validate(sentinel, o._lease)) is sentinel
        assert volume.original._validate_receipt("argument", key="forward-me") is sentinel
        assert volume.api.ParentReadLease.open_export(o._lease, volume.KEYS[0]) is reader
        before = j.record_count
        assert asyncio.run(volume.api.RegisteredReader.read(reader, 65536)) == b"x"
        assert j.record_count == before  # No per-chunk journal record.
        # Existing positive-read counters use actual tiny one-byte return values.
        # Seed only diagnostic totals to cover all 32 fixed threshold crossings.
        for number in range(1, 33):
            j.bulk_bytes = number * 256 * 1024**2 - 1
            assert asyncio.run(volume.api.RegisteredReader.read(reader, 65536)) == b"x"
        read_result[0] = b""
        assert asyncio.run(volume.api.RegisteredReader.read(reader, 65536)) == b""
        assert asyncio.run(volume.api.ParentReadLease.export_inventory(o._lease)) == ()
        assert asyncio.run(volume.api.RegisteredReader.check_identity(reader)) is sentinel
        record.closed = True
        assert asyncio.run(volume.api.RegisteredReader.check_identity(reader)) is sentinel
        assert o._close_validation() is sentinel
        assert o.take_validated_original(key="forward-me") is sentinel
        try:
            for closed, stage in ((True, "final-sweep-error"), (False, "identity-error")):
                record.closed = closed
                error = OSError("actual identity stage failure")
                identity_failure[0] = error
                with pytest.raises(OSError) as caught:
                    asyncio.run(volume.api.RegisteredReader.check_identity(reader))
                assert caught.value is error
                assert rows(journal_root)[1][-1]["stage"] == stage, (
                    "pre-sweep identity failure mislabeled as final sweep")
        finally:
            identity_failure[0] = None
            record.closed = True
    actual_row = audit.counters[id(reader)]
    assert actual_row["bytes"] == actual_row["positive_reads"] == 33
    assert actual_row["eof_reads"] == 1
    assert actual_row["maximum_positive_bytes"] == 1
    assert actual_row["requested_maximum"] == 65536
    assert actual_row["closed_identity_checks"] == 1
    assert audit.receipt_calls == len(audit.receipt_accepted) == 1
    assert audit.export_attempts == [(volume.KEYS[0], 1)]
    assert audit.inventories == [()]
    assert audit.published == [sentinel]
    assert [entry for entry in calls if entry[0] == "validate"] == [
        ("validate", sentinel, o._lease)]
    assert [entry for entry in calls if entry[0] == "receipt"] == [
        ("receipt", ("argument",), {"key": "forward-me"})]
    assert [entry for entry in calls if entry[0] == "open"] == [
        ("open", o._lease, volume.KEYS[0])]
    assert [entry for entry in calls if entry[0] == "read"] == [
        ("read", reader, 65536)] * 34
    assert [entry for entry in calls if entry[0] == "inventory"] == [
        ("inventory", o._lease)]
    assert [entry for entry in calls if entry[0] == "identity"] == [
        ("identity", reader)] * 4
    assert [entry for entry in calls if entry[0] == "close-validation"] == [
        ("close-validation",)]
    assert [entry for entry in calls if entry[0] == "publication"] == [
        ("publication", {"key": "forward-me"})]
    records = rows(journal_root)[1]
    progress = [row for row in records if row["stage"] == "progress"]
    assert len(progress) == 32
    assert [row["bulk_bytes"] for row in progress] == [
        number * 256 * 1024**2 for number in range(1, 33)]
    assert all(row["key"] == volume.KEYS[0] for row in progress)
    stages = [row["stage"] for row in records]
    assert stages.index("receipt-exit") < stages.index("bulk-enter")
    assert stages.count("eof") == stages.count("bulk-exit") == 1
    assert "final-sweep-enter" in stages and "final-sweep-exit" in stages
    assert audit.registry_records_peak == audit.registry_live_descriptor_peak == 1
    assert all(row is not record for row in journal_root.custody.records)
