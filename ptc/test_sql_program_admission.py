"""Non-native PROGRAM admission gates. Opaque bytes, never a SQLite database.

Installed pins are fresh only for these synthetic fixtures. No profile activation,
staging, actor, daemon, SDK evaluation or native execution is established here.
"""
from __future__ import annotations

import asyncio
import builtins
import dataclasses
import hashlib
import io
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
from types import SimpleNamespace

import pytest

from ptc import sql_isolation as core
from ptc.test_sql_owned_invocation import _profile


REFUSAL = (TypeError, ValueError, OSError, RuntimeError)
STAT_FIELDS = (
    "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
    "st_uid", "st_mode", "st_nlink",
)


def _api(executor):
    method = getattr(executor, "admit_program", None)
    assert callable(method), "PROGRAM admission contract missing: admit_program"
    return method


def _fixture(tmp_path):
    profile = _profile(tmp_path)
    path = tmp_path / "opaque-owned.db"
    raw = b"owned fixture bytes, deliberately not SQLite\n"
    path.write_bytes(raw)
    executor = core.PilotExecutor(profile, state_dir=tmp_path / "never-staged")
    return executor, path, hashlib.sha256(raw).hexdigest()


def _fd_count():
    for directory in (Path("/proc/self/fd"), Path("/dev/fd")):
        if directory.is_dir():
            return len(list(directory.iterdir()))
    return None


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    attempts = []

    def deny(label):
        def refused(*args, **kwargs):
            attempts.append(label)
            raise AssertionError("non-native admission reached " + label)
        return refused

    for name in ("_stage_sources", "_stage_database", "_secure_directory",
                 "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated"):
        monkeypatch.setattr(core, name, deny(name), raising=False)
    monkeypatch.setattr(sqlite3, "connect", deny("SQLite"))
    monkeypatch.setattr(subprocess, "Popen", deny("subprocess"))
    if hasattr(core, "_CreatorPopen"):
        monkeypatch.setattr(core._CreatorPopen, "__init__", deny("creator"))
    monkeypatch.setattr(core.threading.Thread, "start", deny("controller thread"))
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny("socket." + name))
    monkeypatch.setattr(socket, "getaddrinfo", deny("DNS"))
    monkeypatch.setattr(os, "kill", deny("PID signal"))
    monkeypatch.setattr(os, "killpg", deny("group signal"))
    yield attempts
    assert attempts == [], f"forbidden admission attempts: {attempts}"


def test_admit_streams_opaque_bytes_and_returns_exact_frozen_identity(
        tmp_path, monkeypatch):
    executor, path, digest = _fixture(tmp_path)
    admit = _api(executor)
    before = path.stat()
    entries = set(tmp_path.rglob("*"))
    baseline = _fd_count()
    opened = []
    original = os.open

    def observed(file, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        fd = original(file, flags, *args, **kwargs)
        if os.fstat(fd).st_ino == before.st_ino:
            opened.append(flags)
        return fd

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", observed)
        identity = admit(db_path=str(path), db_sha256=digest)
    identity_type = getattr(core, "ProgramDatabaseIdentity", None)
    assert identity_type is not None, "PROGRAM database identity record missing"
    assert type(identity) is identity_type and dataclasses.is_dataclass(identity)
    assert type(identity.path) is str and identity.path == str(path)
    assert identity.sha256 == digest
    assert {field.name for field in dataclasses.fields(identity)} == {
        "path", "sha256", *STAT_FIELDS,
    }
    assert all(getattr(identity, name) == getattr(before, name)
               for name in STAT_FIELDS)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        identity.sha256 = "0" * 64
    assert opened, "admission did not inspect the actual database descriptor"
    assert all(flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
               for flags in opened)
    assert set(tmp_path.rglob("*")) == entries
    assert not executor.state_dir.exists()
    assert not executor.profile.shared_state_dir.exists()
    if baseline is not None:
        assert _fd_count() == baseline, "admission leaked descriptors"


def test_database_is_not_subject_to_host_data_or_artifact_byte_cap(tmp_path):
    executor, path, _ = _fixture(tmp_path)
    admit = _api(executor)
    raw = b"x" * 8_388_609
    path.write_bytes(raw)
    identity = admit(db_path=str(path), db_sha256=hashlib.sha256(raw).hexdigest())
    assert identity.st_size == 8_388_609


def test_inert_profile_digest_matches_validated_canonical_envelope(
        tmp_path, monkeypatch):
    profile = _profile(tmp_path)
    expected = hashlib.sha256(
        core.execution_profile_canonical_bytes(profile)).hexdigest()

    def deny(*args, **kwargs):
        raise AssertionError("profile digest attempted filesystem IO")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", deny)
        patch.setattr(io, "open", deny)
        patch.setattr(os, "open", deny)
        assert core.execution_profile_sha256(profile) == expected


@pytest.mark.parametrize("fault", (
    "parent-symlink", "final-symlink", "hardlink", "wrong-uid",
    "wal", "shm", "journal", "digest",
))
def test_database_admission_refuses_unsafe_identity_without_fd_leak(
        tmp_path, monkeypatch, fault):
    executor, path, digest = _fixture(tmp_path)
    admit = _api(executor)
    initial = path.stat()
    hits = []
    if fault == "parent-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        path = alias / path.name
    elif fault == "final-symlink":
        alias = tmp_path / "alias.db"
        alias.symlink_to(path)
        path = alias
    elif fault == "hardlink":
        os.link(path, tmp_path / "second-link.db")
    elif fault in {"wal", "shm", "journal"}:
        Path(str(path) + "-" + fault).write_bytes(b"sidecar")
    elif fault == "digest":
        digest = "0" * 64
    elif fault == "wrong-uid":
        real_fstat = os.fstat

        def changed_uid(fd):
            actual = real_fstat(fd)
            if (actual.st_dev, actual.st_ino) == (initial.st_dev, initial.st_ino):
                hits.append(fd)
                fields = {name: getattr(actual, name)
                          for name in dir(actual) if name.startswith("st_")}
                return SimpleNamespace(**{**fields, "st_uid": os.getuid() + 1})
            return actual

        monkeypatch.setattr(os, "fstat", changed_uid)
    baseline = _fd_count()
    with pytest.raises(REFUSAL):
        admit(db_path=str(path), db_sha256=digest)
    if fault == "wrong-uid":
        assert hits, "wrong-UID probe never observed the database descriptor"
    if baseline is not None:
        assert _fd_count() == baseline, "refused admission leaked descriptors"
    assert not executor.state_dir.exists()


def test_fifo_refuses_within_one_second_without_a_blocking_open(
        tmp_path, monkeypatch):
    executor, _, digest = _fixture(tmp_path)
    admit = _api(executor)
    fifo = tmp_path / "fifo.db"
    os.mkfifo(fifo, 0o600)
    original_open, original_fstat = os.open, os.fstat
    original_builtin, original_io = builtins.open, io.open
    fifo_stat = fifo.stat()

    def guarded_open(file, flags, *args, **kwargs):
        # Assert BEFORE calling the real open. A broken implementation cannot
        # hang the test, leak a retained thread, or leave a FIFO reader behind.
        if os.path.basename(os.fsdecode(file)) == fifo.name:
            assert flags & os.O_NONBLOCK, "FIFO admission used blocking os.open"
        fd = original_open(file, flags, *args, **kwargs)
        actual = original_fstat(fd)
        if (actual.st_dev, actual.st_ino) == (fifo_stat.st_dev, fifo_stat.st_ino):
            assert flags & os.O_NONBLOCK
        return fd

    def guarded_stream(original):
        def opened(file, *args, **kwargs):
            if not isinstance(file, int):
                assert os.path.basename(os.fsdecode(file)) != fifo.name, (
                    "FIFO admission used potentially blocking stream open")
            return original(file, *args, **kwargs)
        return opened

    baseline = _fd_count()
    with monkeypatch.context() as patch:
        patch.setattr(os, "open", guarded_open)
        patch.setattr(builtins, "open", guarded_stream(original_builtin))
        patch.setattr(io, "open", guarded_stream(original_io))
        start = time.monotonic()
        with pytest.raises(REFUSAL):
            admit(db_path=str(fifo), db_sha256=digest)
        assert time.monotonic() - start < 1.0, "FIFO refusal exceeded 1s"
    if baseline is not None:
        assert _fd_count() == baseline


@pytest.mark.parametrize("fault", ("replace", "inplace", "late-sidecar"))
def test_streaming_admission_detects_changes_during_actual_descriptor_read(
        tmp_path, monkeypatch, fault):
    executor, path, digest = _fixture(tmp_path)
    admit = _api(executor)
    initial = path.stat()
    replacement = tmp_path / "replacement.db"
    replacement.write_bytes(path.read_bytes())
    original_read, original_fstat = os.read, os.fstat
    hits = []

    def observed(fd, size):
        chunk = original_read(fd, size)
        actual = original_fstat(fd)
        if chunk and not hits and (actual.st_dev, actual.st_ino) == (
                initial.st_dev, initial.st_ino):
            hits.append(1)
            if fault == "replace":
                os.replace(replacement, path)
            elif fault == "inplace":
                with path.open("r+b") as stream:
                    stream.write(b"CHANGED")
                os.utime(path, ns=(initial.st_atime_ns,
                                  initial.st_mtime_ns + 1_000_000))
            else:
                Path(str(path) + "-wal").write_bytes(b"late sidecar")
        return chunk

    baseline = _fd_count()
    monkeypatch.setattr(os, "read", observed)
    with pytest.raises(REFUSAL):
        admit(db_path=str(path), db_sha256=digest)
    assert hits == [1], "race probe did not intercept the actual DB read"
    if baseline is not None:
        assert _fd_count() == baseline, "racing admission leaked descriptors"


def _bad_profile(profile, fault):
    binding = profile.binding
    if fault in {"program-missing", "program-extra",
                 "scorer-missing", "scorer-extra", "source-pin"}:
        role = "scorer" if fault.startswith("scorer") else "program"
        record = getattr(binding, role)
        pins = record.sources
        if fault.endswith("missing"):
            pins = pins[1:]
        elif fault.endswith("extra"):
            name = "bench/task.py" if role == "program" else "ptc/sql_arms.py"
            pins = tuple(sorted((*pins, core.SourcePin(
                name, hashlib.sha256(
                    (core.installed_source_root() / name).read_bytes()
                ).hexdigest())), key=lambda pin: pin.path))
        else:
            pins = (dataclasses.replace(pins[0], sha256="0" * 64), *pins[1:])
        binding = dataclasses.replace(
            binding, **{role: dataclasses.replace(record, sources=pins)})
        return dataclasses.replace(profile, binding=binding)
    if fault == "controller-missing":
        name = "ptc/runtime.py"
        replacement = core.SourcePin(name, hashlib.sha256(
            (core.installed_source_root() / name).read_bytes()).hexdigest())
        return dataclasses.replace(profile, binding=dataclasses.replace(
            binding, controller_sources=(replacement,)))
    # Change only inert fixture bytes. Keep expected observer/policy pins
    # untouched; replacing observer inside a profile would invalidate its
    # policy fingerprint during fixture construction, before the API gate.
    profile.observer.binary.write_bytes(b"modified inert observer fixture\n")
    return profile


@pytest.mark.parametrize("fault", (
    "program-missing", "program-extra", "scorer-missing", "scorer-extra",
    "controller-missing", "source-pin", "observer-pin",
))
def test_same_fresh_source_closure_is_required_by_preflight_and_public_execute(
        tmp_path, fault):
    executor, path, digest = _fixture(tmp_path)
    profile = _bad_profile(executor.profile, fault)
    executor = core.PilotExecutor(profile, state_dir=executor.state_dir)
    admit = _api(executor)
    expected = profile.binding
    with pytest.raises(REFUSAL):
        admit(db_path=str(path), db_sha256=digest)
    assert executor.profile.binding is expected, "preflight repinned expected closure"
    owner = executor.owned_program(
        "print(1)", db_path=str(path), db_sha256=digest, max_rows=1)

    async def case():
        try:
            completion = await owner.execute()
            assert completion.outcome is None
            assert completion.abort.kind == "infrastructure"
            assert completion.abort.detail_code == "binding"
            ack = completion.cleanup_ack
            snapshot = owner.snapshot()
            assert ack.not_started is True and ack.released is True
            assert ack.invocation_id == snapshot.invocation_id
            assert ack.request_sha256 == snapshot.request_sha256
            assert ack.profile_sha256 == snapshot.profile_sha256
            assert await owner.aclose() is ack
        finally:
            # Real public owner cleanup, not a replacement completion/capability.
            if owner.snapshot().state != "HOST_SEALED":
                await owner.aclose()

    asyncio.run(asyncio.wait_for(case(), 1.0))
    assert executor.profile.binding is expected
    assert not executor.state_dir.exists()


@pytest.mark.parametrize("digest", ("", "G" * 64, "a" * 63))
def test_admission_inherits_strict_digest_validation(tmp_path, digest):
    executor, path, _ = _fixture(tmp_path)
    admit = _api(executor)
    with pytest.raises((TypeError, ValueError)):
        admit(db_path=str(path), db_sha256=digest)
