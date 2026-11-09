"""V294 tiny custody regressions only. Never call preparation or huge test."""
from types import SimpleNamespace
import os

import pytest

from train import test_qualification_ac_volume as volume
from train import _qualification_volume_preparer_fixture as preparer

prohibit_real_effects = volume.prohibit_real_effects


@pytest.fixture(params=(volume, preparer), ids=("volume", "preparer"))
def context(request, monkeypatch, tmp_path):
    module = request.param
    actual_open, actual_close = os.open, os.close
    live, acquired = set(), []

    def opened(*args, **kwargs):
        fd = actual_open(*args, **kwargs)
        live.add(fd)
        acquired.append(fd)
        return fd

    def closed(fd):
        actual_close(fd)
        live.remove(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opened)
        patch.setattr(os, "close", closed)
        try:
            yield SimpleNamespace(module=module, patch=patch, live=live,
                                  acquired=acquired, opened=opened, closed=closed)
        finally:
            # Known fixture generations tracked at each successful real syscall.
            # Disposal follows all retention/no-probe assertions, never infers
            # whether a production UNKNOWN close actually closed its number.
            for fd in tuple(live):
                actual_close(fd)
                live.remove(fd)


def fresh(context):
    custody = context.module._OwnedCustody()
    context.patch.setattr(context.module, "_OWNED", custody)
    return custody


def parents(context, tmp_path):
    custody = fresh(context)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    grandparent = custody.open(str(tmp_path), flags)
    os.mkdir("nested", 0o700, dir_fd=grandparent)
    parent = custody.open("nested", flags, dir_fd=grandparent)
    return custody, grandparent, parent


def parent_and_child(context, tmp_path):
    custody, grandparent, parent = parents(context, tmp_path)
    child = custody.open("child", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600, dir_fd=parent)
    return custody, grandparent, parent, child


def row_for(custody, fd):
    return next(row for row in custody.records if row["fd"] == fd)


def test_acquired_anchor_survives_fstat_failure(context, tmp_path, monkeypatch):
    custody = fresh(context)
    primary = OSError("owned fstat failure")
    actual_fstat = os.fstat

    def fail(fd):
        if len(context.acquired) == 3 and fd == context.acquired[-1]:
            raise primary
        return actual_fstat(fd)

    module = context.module
    anchors = (module._Anchors if module is volume else module.Anchors)()
    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", fail)
        with pytest.raises(OSError) as caught:
            (anchors.root if module is volume else anchors.open)(str(tmp_path))
    assert caught.value is primary
    assert len(context.acquired) == len(custody.records) == 3
    fd = context.acquired[-1]
    assert row_for(custody, fd)["state"] == "OPEN" and fd in context.live
    anchors.close()
    assert row_for(custody, fd)["state"] == "CLOSED"
    assert context.live == set()


def test_unknown_close_retains_ancestors(context, tmp_path, monkeypatch):
    custody, grandparent, parent, child = parent_and_child(context, tmp_path)
    primary, attempts, open_attempts = OSError("owned close failure"), [], []

    def fail(fd):
        attempts.append(fd)
        if fd == child:
            raise primary
        return context.closed(fd)

    def forbidden_open(*args, **kwargs):
        open_attempts.append((args, kwargs))
        raise AssertionError("open attempted after UNKNOWN")

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", fail)
        with pytest.raises(OSError) as caught:
            custody.close(child)
        assert caught.value is primary
        for _ in range(2):
            with pytest.raises(OSError) as caught:
                custody.close_all()
            assert caught.value is primary
        acquired, live = tuple(context.acquired), set(context.live)
        patch.setattr(os, "open", forbidden_open)
        with pytest.raises(RuntimeError, match="unresolved"):
            custody.open("never-created", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600, dir_fd=parent)
        assert tuple(context.acquired) == acquired and context.live == live
    row = row_for(custody, child)
    assert row["state"] == "UNKNOWN" and row["error"] is primary
    assert row["parent"] is row_for(custody, parent)
    assert row_for(custody, parent)["parent"] is row_for(custody, grandparent)
    assert attempts == [child] and open_attempts == []
    assert {grandparent, parent, child} == context.live
    assert row_for(custody, parent)["state"] == "OPEN"
    assert row_for(custody, grandparent)["state"] == "OPEN"


def test_close_then_raise_never_touches_recycled_number(context, tmp_path, monkeypatch):
    custody, grandparent, parent, child = parent_and_child(context, tmp_path)
    primary, attempts, probes = OSError("owned close then raise"), [], []
    actual_fstat = os.fstat
    retired = [False]

    def fail(fd):
        attempts.append(fd)
        if fd == child:
            context.closed(fd)
            retired[0] = True
            raise primary
        return context.closed(fd)

    def no_probe(fd):
        if retired[0] and fd == child:
            probes.append(fd)
            raise AssertionError("retired number probed")
        return actual_fstat(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "close", fail)
        patch.setattr(os, "fstat", no_probe)
        with pytest.raises(OSError) as caught:
            custody.close(child)
        assert caught.value is primary and child not in context.live
        replacement = context.opened("replacement", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                     0o600, dir_fd=parent)
        assert replacement == child
        for _ in range(2):
            with pytest.raises(OSError) as caught:
                custody.close_all()
            assert caught.value is primary
    assert attempts == [child] and probes == []
    assert {replacement, parent, grandparent} == context.live
    assert row_for(custody, child)["state"] == "UNKNOWN"
    assert row_for(custody, parent)["state"] == "OPEN"
    assert row_for(custody, grandparent)["state"] == "OPEN"
    assert row_for(custody, parent)["parent"] is row_for(custody, grandparent)


def test_interrupted_open_retains_parent_without_fd(context, tmp_path, monkeypatch):
    custody, grandparent, parent = parents(context, tmp_path)
    primary = KeyboardInterrupt("owned interrupted acquisition")
    close_attempts, open_attempts = [], []

    def interrupted(path, *args, **kwargs):
        if path == "child":
            raise primary
        return context.opened(path, *args, **kwargs)

    def no_close(fd):
        close_attempts.append(fd)
        return context.closed(fd)

    def forbidden_open(*args, **kwargs):
        open_attempts.append((args, kwargs))
        raise AssertionError("open attempted after UNKNOWN without FD")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", interrupted)
        patch.setattr(os, "close", no_close)
        with pytest.raises(KeyboardInterrupt) as caught:
            custody.open("child", os.O_RDONLY, dir_fd=parent)
        assert caught.value is primary
        for _ in range(2):
            with pytest.raises(KeyboardInterrupt) as caught:
                custody.close_all()
            assert caught.value is primary
        acquired, live = tuple(context.acquired), set(context.live)
        patch.setattr(os, "open", forbidden_open)
        with pytest.raises(RuntimeError, match="unresolved"):
            custody.open("never-created", os.O_RDONLY, dir_fd=parent)
        assert tuple(context.acquired) == acquired and context.live == live
    row = custody.records[-1]
    assert row["fd"] is None and row["state"] == "UNKNOWN" and row["error"] is primary
    assert row["parent"] is row_for(custody, parent)
    assert {grandparent, parent} == context.live
    assert row_for(custody, parent)["state"] == "OPEN"
    assert row_for(custody, grandparent)["state"] == "OPEN"
    assert row_for(custody, parent)["parent"] is row_for(custody, grandparent)
    assert close_attempts == open_attempts == []


def test_confirmed_open_oserror_allows_known_clean_parent_close(context, tmp_path, monkeypatch):
    custody, grandparent, parent = parents(context, tmp_path)
    primary = OSError("owned confirmed acquisition failure")

    def failed(path, *args, **kwargs):
        if path == "child":
            raise primary
        return context.opened(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", failed)
        with pytest.raises(OSError) as caught:
            custody.open("child", os.O_RDONLY, dir_fd=parent)
    assert caught.value is primary
    row = custody.records[-1]
    assert row["fd"] is None and row["state"] == "NO_FD" and row["error"] is primary
    custody.close_all()
    assert row_for(custody, parent)["state"] == "CLOSED" and context.live == set()
    assert row_for(custody, grandparent)["state"] == "CLOSED"
