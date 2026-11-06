"""Continuation tests for `bench/prepare.py` -- precommit cleanup must not mask
the primary publication failure, and postcommit cleanup failure stays
indeterminate.

Spec: `spec/bench-preparation.md` T12/T13 (create-only commit, no clobber on
link refusal, indeterminate outcome after commit) plus the task requirement
that the original exception/cancellation identity is preserved.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402


def _prep():
    return importlib.import_module("bench.prepare")


class _Cancel(BaseException):
    """Cancellation-like failure that is not an Exception subclass, so pytest
    does not treat it as an interruption and `except Exception` cannot see it."""


class _CleanupCancel(BaseException):
    """Cleanup-time failure outside the OSError hierarchy."""


def _tracking_unlink(monkeypatch, real_unlink, secondary, attempts):
    def unlink(path):
        if ".prepare-" in os.fspath(path):
            attempts.append(os.fspath(path))
            raise secondary
        return real_unlink(path)

    monkeypatch.setattr(os, "unlink", unlink)


@pytest.mark.parametrize("phase", ["fsync", "link"])
@pytest.mark.parametrize("primary_kind", ["ordinary", "cancel"])
@pytest.mark.parametrize("secondary", [RuntimeError("cleanup failed"), _CleanupCancel("cleanup cancelled")])
def test_precommit_cleanup_preserves_original_failure(
    monkeypatch, tmp_path, phase, primary_kind, secondary
):
    prep = _prep()
    doc = {"alpha": 1, "beta": [2, 3]}
    out = tmp_path / "final.json"

    attempts = []
    _tracking_unlink(monkeypatch, os.unlink, secondary, attempts)

    captured = []
    if phase == "fsync":
        primary = (
            RuntimeError("fsync failed")
            if primary_kind == "ordinary"
            else _Cancel("write cancelled")
        )

        def fsync(fd):
            raise primary

        monkeypatch.setattr(os, "fsync", fsync)
    else:
        out.write_bytes(b"sentinel")
        if primary_kind == "ordinary":
            real_link = os.link

            def link(src, dst):
                try:
                    return real_link(src, dst)
                except FileExistsError as exc:
                    captured.append(exc)
                    raise

            monkeypatch.setattr(os, "link", link)
            primary = None  # resolved from captured after the call
        else:
            primary = _Cancel("link cancelled")

            def link(src, dst):
                raise primary

            monkeypatch.setattr(os, "link", link)

    with pytest.raises(BaseException) as caught:
        prep._publish(doc, out)

    if phase == "link" and primary_kind == "ordinary":
        assert len(captured) == 1
        primary = captured[0]

    assert caught.value is primary
    assert len(attempts) == 1
    if phase == "fsync":
        assert not out.exists()
    else:
        assert out.read_bytes() == b"sentinel"


def test_postcommit_cleanup_failure_remains_indeterminate(monkeypatch, tmp_path):
    prep = _prep()
    doc = {"alpha": 1, "beta": [2, 3]}
    out = tmp_path / "final.json"

    secondary = RuntimeError("postcommit unlink failed")
    attempts = []
    _tracking_unlink(monkeypatch, os.unlink, secondary, attempts)

    with pytest.raises(prep.PublicationIndeterminateError) as caught:
        prep._publish(doc, out)

    assert caught.value.__cause__ is secondary
    assert len(attempts) == 1
    canonical = out.read_bytes()
    assert hashlib.sha256(canonical).hexdigest() == hashlib.sha256(
        prep._canonical_bytes(doc)
    ).hexdigest()
