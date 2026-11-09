"""Owned-FD reservation receipt regressions, no processes/SDK/assets/stager."""
import copy
import os
import pickle
import stat
from types import SimpleNamespace

import pytest

from train import qualification_engineering_host as host
from train.test_qualification_engineering_host import _APP_ID, _SANDBOX_ID, _issue, _policy


@pytest.fixture
def owned(tmp_path, monkeypatch):
    auth = _issue(policy_pin=_policy(tmp_path))
    real_open, real_close = os.open, os.close
    active, labels, opened, closed, peaks = {}, {}, [], [], []
    def open_file(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        generation = object()
        active[fd] = generation
        peaks.append(len(active))
        labels[fd] = str(path)
        opened.append((fd, generation))
        return fd
    def close_file(fd):
        generation = active[fd]
        real_close(fd)
        del active[fd]
        closed.append((fd, generation))
    monkeypatch.setattr(host.os, "open", open_file)
    monkeypatch.setattr(host.os, "close", close_file)
    result = SimpleNamespace(
        auth=auth, active=active, labels=labels, opened=opened, closed=closed,
        open=open_file, close=close_file, raw_close=real_close, root=tmp_path, peaks=peaks)
    yield result
    # Explicit known-owned fixture disposal, not production retry/recovery.
    for fd in tuple(active):
        real_close(fd)
        del active[fd]


def failure_receipt(error, owned):
    receipt = host._custody_for_failure(error, authorization=owned.auth)
    assert receipt is not None and receipt.authorization is owned.auth
    assert receipt.primary is error
    generations = [r.generation for r in receipt.records]
    assert len({id(g) for g in generations}) == len(generations)
    return receipt


def test_healthy_receipt_one_retained_fd_and_zero_after_close(owned, monkeypatch):
    records = []
    reserve = host._ReservationCustody.reserve
    real_fstat = os.fstat
    def registered(custody, *args, **kwargs):
        record = reserve(custody, *args, **kwargs)
        records.append(record)
        return record
    def open_file(*args, **kwargs):
        assert any(r.state == "RESERVED" and r.fd is None for r in records)
        return owned.open(*args, **kwargs)
    def fstat(fd):
        assert any(r.fd == fd and r.state == "OPEN" for r in records), (
            "actual FD must be registered before validation")
        return real_fstat(fd)
    monkeypatch.setattr(host._ReservationCustody, "reserve", registered)
    monkeypatch.setattr(host.os, "open", open_file)
    monkeypatch.setattr(host.os, "fstat", fstat)
    reservation = host.claim_attempt_reservation(owned.auth)
    try:
        receipt = host._custody_for_reservation(reservation)
        assert receipt.reservation is reservation and receipt.authorization is owned.auth
        assert len(owned.active) == 1 and not receipt.has_unknown
        assert all(r.fd is not None for r in receipt.records if r.state == "OPEN")
        reservation.consume()
        reservation.record_identity("app", _APP_ID)
        assert len(owned.active) == 1
    finally:
        reservation.close("failed")
    receipt.require_released()
    assert not owned.active and len(owned.opened) == len(owned.closed)
    assert max(owned.peaks) <= 2


@pytest.mark.parametrize("boundary", ["root", "child", "predecessor"])
def test_traversal_failure_keeps_exact_primary_and_one_shot_generations(
        owned, monkeypatch, boundary):
    primary = OSError("owned traversal primary")
    real_validate = host._require_trusted_dir
    validates, attempts, failed = [], [], []
    def validate(info, *, immediate):
        validates.append(info)
        if boundary == ("root" if len(validates) == 1 else "child"):
            raise primary
        return real_validate(info, immediate=immediate)
    def close(fd):
        attempts.append((fd, owned.active[fd]))
        if boundary == "predecessor" and not failed:
            failed.append(fd)
            raise primary
        return owned.close(fd)
    monkeypatch.setattr(host, "_require_trusted_dir", validate)
    monkeypatch.setattr(host.os, "close", close)
    with pytest.raises(OSError) as caught:
        host.claim_attempt_reservation(owned.auth)
    assert caught.value is primary
    receipt = failure_receipt(primary, owned)
    assert len({id(g) for _, g in attempts}) == len(attempts)
    if boundary == "predecessor":
        assert receipt.has_unknown and len(owned.active) == 1
        unknown = [r for r in receipt.records if r.state == "UNKNOWN"]
        assert len(unknown) == 1 and unknown[0].close_error is primary
    else:
        assert not receipt.has_unknown and not owned.active
        receipt.require_released()


@pytest.mark.parametrize("role", ["policy", "claim", "app", "sandbox", "final"])
def test_primary_and_secondary_preserve_unknown_fd_and_required_anchor(
        owned, monkeypatch, role):
    reservation = None
    if role in {"app", "sandbox", "final"}:
        reservation = host.claim_attempt_reservation(owned.auth)
    primary, secondary = OSError("owned operation primary"), OSError("owned close secondary")
    original_read, original_write = os.read, os.write
    target, attempts = [], []
    def selected(fd):
        label = owned.labels.get(fd, "")
        return label == owned.auth.policy_pin.path.name if role == "policy" else label.startswith(
            ".qualification-attempt-")
    def read(fd, size):
        if role == "policy" and selected(fd):
            target.append(fd)
            raise primary
        return original_read(fd, size)
    def write(fd, raw):
        if role != "policy" and selected(fd):
            target.append(fd)
            raise primary
        return original_write(fd, raw)
    def close(fd):
        if fd in target:
            attempts.append(fd)
            raise secondary
        return owned.close(fd)
    monkeypatch.setattr(host.os, "read", read)
    monkeypatch.setattr(host.os, "write", write)
    monkeypatch.setattr(host.os, "close", close)
    with pytest.raises(OSError) as caught:
        if reservation is None:
            host.claim_attempt_reservation(owned.auth)
        elif role == "final":
            reservation.close("failed")
        else:
            reservation.record_identity(role, _APP_ID if role == "app" else _SANDBOX_ID)
    assert caught.value is primary and len(target) == 1 and attempts == target
    receipt = failure_receipt(primary, owned)
    assert any(e is secondary for e in receipt.secondary)
    unknown = [r for r in receipt.records if r.close_error is secondary]
    assert len(unknown) == 1 and unknown[0].state == "UNKNOWN"
    anchor = unknown[0].required_anchor
    assert anchor is not None and anchor.state == "OPEN"
    assert anchor.fd in owned.active and unknown[0].fd in owned.active
    before = (list(owned.opened), list(owned.closed), list(attempts))
    receipt.cleanup(primary)
    receipt.cleanup(primary)
    assert (owned.opened, owned.closed, attempts) == before
    with pytest.raises(RuntimeError):
        receipt.require_released()


@pytest.mark.parametrize("boundary", ["root", "child", "policy", "claim", "append"])
def test_known_open_failure_has_no_fd_and_balanced_cleanup(owned, monkeypatch, boundary):
    reservation = host.claim_attempt_reservation(owned.auth) if boundary == "append" else None
    primary = OSError("owned open failure")
    calls = []
    def open_file(path, flags, *args, **kwargs):
        name = str(path)
        chosen = (
            (boundary == "root" and name == "/")
            or (boundary == "child" and name not in {"/", owned.auth.policy_pin.path.name}
                and not name.startswith(".qualification-attempt-"))
            or (boundary == "policy" and name == owned.auth.policy_pin.path.name)
            or (boundary in {"claim", "append"} and name.startswith(".qualification-attempt-")))
        if chosen:
            calls.append(name)
            raise primary
        return owned.open(path, flags, *args, **kwargs)
    monkeypatch.setattr(host.os, "open", open_file)
    with pytest.raises(OSError) as caught:
        if reservation is None:
            host.claim_attempt_reservation(owned.auth)
        else:
            reservation.record_identity("app", _APP_ID)
    assert calls
    # Existing public claim deliberately normalizes a create-open OSError.
    # The custody accessor must publish the receipt on the propagated error.
    if boundary == "claim":
        assert not owned.active
        assert caught.value.__context__ is primary
    else:
        assert caught.value is primary
    receipt = failure_receipt(caught.value, owned)
    assert any(r.state == "NO_FD" for r in receipt.records) and not receipt.has_unknown
    if reservation is not None:
        reservation.close("failed")
    receipt.require_released()
    assert not owned.active


def test_unknown_final_anchor_close_does_not_clear_or_retry_actual_generation(owned, monkeypatch):
    reservation = host.claim_attempt_reservation(owned.auth)
    directory = reservation._dir_fd
    primary, attempts = OSError("owned anchor close failure"), []
    def close(fd):
        if fd == directory:
            attempts.append(fd)
            raise primary
        return owned.close(fd)
    monkeypatch.setattr(host.os, "close", close)
    with pytest.raises(OSError) as caught:
        reservation.close("failed")
    assert caught.value is primary and reservation.closed
    receipt = failure_receipt(primary, owned)
    assert reservation._dir_fd == directory and receipt.has_unknown
    for _ in range(2):
        reservation.close("failed")
    assert attempts == [directory] and directory in owned.active


def test_physically_closed_unknown_number_reuse_never_closes_replacement(owned, monkeypatch):
    reservation = host.claim_attempt_reservation(owned.auth)
    directory = reservation._dir_fd
    path = owned.root / "replacement"
    path.write_bytes(b"owned replacement")
    primary, attempts = OSError("owned post-close failure"), []
    def close(fd):
        if fd != directory:
            return owned.close(fd)
        attempts.append(fd)
        owned.close(fd)
        replacement = owned.open(path, os.O_RDONLY)
        if replacement != directory:
            os.dup2(replacement, directory)
            generation = owned.active.pop(replacement)
            owned.raw_close(replacement)
            owned.active[directory] = generation
        raise primary
    monkeypatch.setattr(host.os, "close", close)
    with pytest.raises(OSError):
        reservation.close("failed")
    receipt = failure_receipt(primary, owned)
    real_fstat = os.fstat
    def no_retired_inspection(fd):
        assert fd != directory, "retired descriptor number inspected"
        return real_fstat(fd)
    with monkeypatch.context() as m:
        m.setattr(host.os, "fstat", no_retired_inspection)
        reservation.close("failed")
        receipt.cleanup(primary)
    assert attempts == [directory] and stat.S_ISREG(os.fstat(directory).st_mode)
    assert receipt.has_unknown


def test_custom_exception_setattr_cannot_hide_failed_claim_receipt(owned, monkeypatch):
    class Primary(OSError):
        def __setattr__(self, name, value):
            raise AssertionError("custom exception setattr must not run")
    primary = Primary("owned validation error")
    monkeypatch.setattr(host, "_require_trusted_dir",
                        lambda *args, **kwargs: (_ for _ in ()).throw(primary))
    with pytest.raises(Primary) as caught:
        host.claim_attempt_reservation(owned.auth)
    assert caught.value is primary
    receipt = failure_receipt(primary, owned)
    receipt.require_released()
    assert not owned.active
    other = _issue(policy_pin=_policy(owned.root, name="foreign-policy"))
    assert host._custody_for_failure(primary, authorization=other) is None


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_receipt_noncopy_and_foreign_or_missing_association_refusal(owned, operation):
    reservation = host.claim_attempt_reservation(owned.auth)
    try:
        receipt = host._custody_for_reservation(reservation)
        with pytest.raises(TypeError):
            operation(receipt)
        other = _issue(policy_pin=_policy(owned.root, name="other-policy"))
        error = OSError("unpublished error")
        assert host._custody_for_failure(error, authorization=owned.auth) is None
        assert host._custody_for_failure(error, authorization=other) is None
    finally:
        reservation.close("failed")


def test_interrupted_acquisition_is_unknown_not_confirmed_no_fd(owned, monkeypatch):
    class Interrupted(BaseException):
        pass
    primary = Interrupted("owned interrupted policy acquisition")
    def open_file(path, *args, **kwargs):
        if str(path) == owned.auth.policy_pin.path.name:
            raise primary
        return owned.open(path, *args, **kwargs)
    monkeypatch.setattr(host.os, "open", open_file)
    with pytest.raises(Interrupted) as caught:
        host.claim_attempt_reservation(owned.auth)
    assert caught.value is primary
    receipt = failure_receipt(primary, owned)
    unresolved = [r for r in receipt.records if r.state == "UNKNOWN" and r.fd is None]
    assert len(unresolved) == 1 and receipt.has_unknown
    assert unresolved[0].required_anchor.fd in owned.active
    with pytest.raises(RuntimeError):
        receipt.require_released()
