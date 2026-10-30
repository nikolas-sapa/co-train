"""Offline real-filesystem and subprocess gates; no provider-cost claim."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
LIMIT = 50_000_000


@pytest.fixture
def api():
    # Missing implementation must fail a collected test, not collection itself.
    assert importlib.util.find_spec("train.sql_pilot_budget") is not None, (
        "offline budget implementation missing"
    )
    return importlib.import_module("train.sql_pilot_budget")


@pytest.fixture
def work(tmp_path):
    return tmp_path.resolve()


def config(api, **changes):
    values = dict(run_id="run", approved_model="unverified-profile-model",
                  profile_sha256=SHA, authority_ref="reference-not-proof",
                  limit_usd_micros=LIMIT, request_limit=25)
    values.update(changes)
    return api.BudgetConfig(**values)


def ledger(api, work, **changes):
    cfg = config(api, **changes)
    directory = work / "ledger"
    created = api.BudgetLedger.create(directory, cfg)
    assert created.requests == ()
    return api.BudgetLedger.open(directory, cfg), directory, cfg


def finish(subject, request_id, maximum=1, actual=1):
    subject.reserve(request_id, maximum)
    subject.claim_dispatch(request_id)
    return subject.settle(request_id, actual, SHA)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def rewrite(directory, mutate):
    path = directory / "state.json"
    envelope = json.loads(path.read_bytes())
    mutate(envelope)
    envelope["sha256"] = hashlib.sha256(canonical(envelope["payload"])).hexdigest()
    path.write_bytes(canonical(envelope))


def test_exact_money_and_failed_admission_bytes(api, work):
    subject, directory, cfg = ledger(api, work)
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        subject.reserve("large", LIMIT + 1)
    assert (directory / "state.json").read_bytes() == before
    result = subject.reserve("large", LIMIT)
    assert result.maximum_charge_micros == LIMIT
    assert subject.snapshot().exposure_micros == LIMIT
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.request_id = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        subject.snapshot().requests[0].state = "settled"
    assert api.BudgetLedger.open(directory, cfg).snapshot() == subject.snapshot()


def test_25_requests_and_failed_admission_consumes_no_entry(api, work):
    subject, directory, _ = ledger(api, work)
    with pytest.raises(api.BudgetError):
        subject.reserve("first", LIMIT + 1)
    for number in range(25):
        finish(subject, "first" if number == 0 else str(number))
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        subject.reserve("26", 1)
    assert len(subject.snapshot().requests) == 25
    assert (directory / "state.json").read_bytes() == before


def test_cumulative_money_boundary_and_lower_actual_reclaims_headroom(api, work):
    subject, directory, _ = ledger(api, work)
    finish(subject, "first", 10, 7)
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        subject.reserve("remaining", LIMIT - 6)
    assert (directory / "state.json").read_bytes() == before
    subject.reserve("remaining", LIMIT - 7)
    assert subject.snapshot().exposure_micros == LIMIT


@pytest.mark.parametrize("claimed", [False, True])
def test_unknown_usage_retains_full_maximum_and_blocks(api, work, claimed):
    subject, directory, cfg = ledger(api, work)
    subject.reserve("unknown", LIMIT)
    if claimed:
        subject.claim_dispatch("unknown")
    before = (directory / "state.json").read_bytes()
    reopened = api.BudgetLedger.open(directory, cfg)
    assert reopened.snapshot().reserved_charge_micros == LIMIT
    with pytest.raises(api.BudgetError):
        reopened.reserve("next", 1)
    with pytest.raises(api.BudgetError):
        reopened.reserve("unknown", 1)
    if not claimed:
        with pytest.raises(api.BudgetError):
            reopened.settle("unknown", 1, SHA)
    assert not any(hasattr(reopened, name) for name in ("cancel", "refund", "release"))
    assert (directory / "state.json").read_bytes() == before


@pytest.mark.parametrize("actual", [4, 5, 6, (1 << 63) - 1])
def test_exact_settlement_and_permanent_overrun(api, work, actual):
    subject, directory, cfg = ledger(api, work)
    subject.reserve("one", 5)
    subject.claim_dispatch("one")
    result = subject.settle("one", actual, SHA)
    assert result.actual_charge_micros == actual
    assert result.halted is (actual > 5)
    reopened = api.BudgetLedger.open(directory, cfg)
    assert reopened.snapshot().settled_charge_micros == actual
    assert reopened.snapshot().status == ("halted_overrun" if actual > 5 else "active")
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        reopened.settle("one", actual, SHA)
    with pytest.raises(api.BudgetError):
        reopened.claim_dispatch("one")
    with pytest.raises(api.BudgetError):
        reopened.reserve("one", 1)
    if actual > 5:
        with pytest.raises(api.BudgetError):
            reopened.reserve("two", 1)
    assert (directory / "state.json").read_bytes() == before


@pytest.mark.parametrize("actual,evidence", [(None, SHA), (True, SHA), (1.0, SHA),
                                            (-1, SHA), (1 << 63, SHA), (0, SHA),
                                            (1, None), (1, "A" * 64), (1, "")])
def test_invalid_settlement_holds_reservation(api, work, actual, evidence):
    subject, directory, _ = ledger(api, work)
    subject.reserve("one", 5)
    subject.claim_dispatch("one")
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        subject.settle("one", actual, evidence)
    assert subject.snapshot().reserved_charge_micros == 5
    assert (directory / "state.json").read_bytes() == before


def test_zero_authorization_and_evidence(api, work):
    subject, directory, _ = ledger(api, work)
    with pytest.raises(api.BudgetError):
        subject.reserve("zero", 0)
    zero_dir = work / "zero"
    cfg = config(api, zero_charge_authorized=True)
    api.BudgetLedger.create(zero_dir, cfg)
    zero = api.BudgetLedger.open(zero_dir, cfg)
    zero.reserve("zero", 0)
    zero.claim_dispatch("zero")
    with pytest.raises(api.BudgetError):
        zero.settle("zero", 0, None)
    assert zero.settle("zero", 0, SHA).actual_charge_micros == 0
    assert zero.snapshot().requests[0].settlement_evidence_sha256 == SHA


@pytest.mark.parametrize("field,value", [
    ("run_id", ""), ("run_id", "x" * 129), ("run_id", "x\n"),
    ("run_id", "é"), ("approved_model", "x" * 257),
    ("authority_ref", ""), ("profile_sha256", "A" * 64),
    ("limit_usd_micros", True), ("limit_usd_micros", LIMIT + 1),
    ("limit_usd_micros", float(LIMIT)), ("request_limit", True),
    ("request_limit", 26), ("zero_charge_authorized", 1),
])
def test_strict_config_inputs(api, field, value):
    with pytest.raises(api.BudgetError):
        config(api, **{field: value})


@pytest.mark.parametrize("request_id,maximum", [
    ("", 1), ("x" * 129, 1), ("x\t", 1), ("é", 1), (None, 1),
    ("one", True), ("one", 1.0), ("one", -1), ("one", 1 << 63),
])
def test_strict_reservation_inputs(api, work, request_id, maximum):
    subject, directory, _ = ledger(api, work)
    before = (directory / "state.json").read_bytes()
    with pytest.raises(api.BudgetError):
        subject.reserve(request_id, maximum)
    assert (directory / "state.json").read_bytes() == before


def test_raw_envelope_boundary(api, work):
    _, directory, cfg = ledger(api, work)
    path = directory / "state.json"
    raw = path.read_bytes()
    padded = raw + b" " * (65536 - len(raw))
    path.write_bytes(padded)
    assert api.BudgetLedger.open(directory, cfg).snapshot().requests == ()
    path.write_bytes(padded + b" ")
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)


@pytest.mark.parametrize("bad", ["duplicate", "unknown", "nonfinite", "float",
                               "bool", "version", "deep", "hash", "bad_utf8",
                               "missing", "config_extra", "request_extra"])
def test_strict_envelope_rejections(api, work, bad):
    subject, directory, cfg = ledger(api, work)
    if bad == "request_extra":
        subject.reserve("one", 1)
    path = directory / "state.json"
    envelope = json.loads(path.read_bytes())
    if bad == "duplicate":
        raw = path.read_bytes().replace(b'"schema_version":1',
                                       b'"schema_version":1,"schema_version":1')
    elif bad == "nonfinite":
        raw = path.read_bytes().replace(b'"schema_version":1', b'"schema_version":NaN')
    elif bad == "float":
        raw = path.read_bytes().replace(b'"schema_version":1', b'"schema_version":1.0')
    elif bad == "deep":
        raw = b"[" * 10000 + b"0" + b"]" * 10000
    elif bad == "bad_utf8":
        raw = b"\xff"
    else:
        if bad == "unknown":
            envelope["extra"] = 1
        elif bad == "bool":
            envelope["schema_version"] = True
        elif bad == "version":
            envelope["schema_version"] = 2
        elif bad == "hash":
            envelope["sha256"] = "0" * 64
        elif bad == "missing":
            del envelope["format"]
        elif bad == "config_extra":
            envelope["payload"]["config"]["extra"] = 1
        elif bad == "request_extra":
            envelope["payload"]["requests"][0]["extra"] = 1
        if bad != "hash":
            envelope["sha256"] = hashlib.sha256(canonical(envelope["payload"])).hexdigest()
        raw = canonical(envelope)
    path.write_bytes(raw)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)


@pytest.mark.parametrize("bad", ["duplicate_id", "two_unsettled", "unsettled_not_last",
                               "false_halt", "hidden_overrun", "post_overrun",
                               "overexposed", "bad_actual", "null_evidence",
                               "unsettled_actual", "too_many", "bad_state", "int_bound"])
def test_historical_graph_rejected_even_with_valid_selfhash(api, work, bad):
    subject, directory, cfg = ledger(api, work)
    finish(subject, "first", 5, 4)
    subject.reserve("last", 5)
    def corrupt(envelope):
        payload = envelope["payload"]
        first, last = payload["requests"]
        if bad == "duplicate_id":
            last["request_id"] = first["request_id"]
        elif bad == "two_unsettled":
            first.update(state="reserved", actual_charge_micros=None,
                         settlement_evidence_sha256=None)
        elif bad == "unsettled_not_last":
            payload["requests"].reverse()
        elif bad == "false_halt":
            payload["status"] = "halted_overrun"
        elif bad == "hidden_overrun":
            payload["requests"] = [first]
            first["actual_charge_micros"] = 6
        elif bad == "post_overrun":
            first["actual_charge_micros"] = 6
            payload["status"] = "halted_overrun"
        elif bad == "overexposed":
            last["maximum_charge_micros"] = LIMIT
        elif bad == "bad_actual":
            first["actual_charge_micros"] = True
        elif bad == "null_evidence":
            first["settlement_evidence_sha256"] = None
        elif bad == "unsettled_actual":
            last["actual_charge_micros"] = 1
        elif bad == "too_many":
            payload["requests"] = [dict(first, request_id=str(n)) for n in range(26)]
        elif bad == "bad_state":
            last["state"] = "cancelled"
        elif bad == "int_bound":
            last["maximum_charge_micros"] = 1 << 63
    rewrite(directory, corrupt)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)


def test_configuration_binding(api, work):
    _, directory, cfg = ledger(api, work)
    for field, value in [("run_id", "other"), ("approved_model", "other"),
                         ("profile_sha256", "b" * 64), ("authority_ref", "other"),
                         ("zero_charge_authorized", True)]:
        with pytest.raises(api.BudgetError):
            api.BudgetLedger.open(directory, dataclasses.replace(cfg, **{field: value}))


@pytest.mark.parametrize("target", ["state.json", "guard"])
@pytest.mark.parametrize("bad", ["symlink", "hardlink", "mode", "owner", "fifo"])
def test_unsafe_storage_rejected(api, work, target, bad, monkeypatch):
    subject, directory, cfg = ledger(api, work)
    path = directory / target
    if bad == "symlink":
        moved = work / "moved"
        path.rename(moved)
        path.symlink_to(moved)
    elif bad == "hardlink":
        os.link(path, work / "linked")
    elif bad == "mode":
        path.chmod(0o644)
    elif bad == "owner":
        # Unprivileged tests cannot chown to a foreign UID. Only the selected
        # real file descriptor gets a fault-injected foreign-owner fstat result.
        identity = (path.stat().st_dev, path.stat().st_ino)
        real_fstat = api.os.fstat
        def foreign_owner(fd):
            info = real_fstat(fd)
            if (info.st_dev, info.st_ino) != identity:
                return info
            names = ("st_dev", "st_ino", "st_uid", "st_mode", "st_nlink",
                     "st_size", "st_mtime_ns", "st_ctime_ns")
            values = {name: getattr(info, name) for name in names}
            values["st_uid"] = os.geteuid() + 1
            return SimpleNamespace(**values)
        monkeypatch.setattr(api.os, "fstat", foreign_owner)
    elif bad == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)
    with pytest.raises(api.BudgetError):
        subject.snapshot()


def test_directory_and_missing_guard_fail_closed(api, work):
    subject, directory, cfg = ledger(api, work)
    directory.chmod(0o755)
    with pytest.raises(api.BudgetError):
        subject.snapshot()
    directory.chmod(0o700)
    alias = work / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(alias, cfg)
    before = (directory / "state.json").read_bytes()
    (directory / "guard").unlink()
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)
    assert not (directory / "guard").exists()
    assert (directory / "state.json").read_bytes() == before


def test_exclusive_initialization_and_guard_inode_stability(api, work):
    subject, directory, cfg = ledger(api, work)
    guard = (directory / "guard").stat()
    initial = (directory / "state.json").stat()
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.create(directory, cfg)
    subject.reserve("one", 1)
    current = (directory / "guard").stat()
    assert (current.st_dev, current.st_ino) == (guard.st_dev, guard.st_ino)
    assert current.st_size == 0
    assert (directory / "state.json").stat().st_ino != initial.st_ino
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in ("guard", "state.json"):
        assert stat.S_IMODE((directory / name).stat().st_mode) == 0o600
    old = directory / "old-guard"
    (directory / "guard").rename(old)
    (directory / "guard").write_bytes(b"")
    (directory / "guard").chmod(0o600)
    with pytest.raises(api.BudgetError):
        subject.snapshot()


def test_existing_directory_never_modified_and_guard_must_be_empty(api, work):
    existing = work / "existing"
    existing.mkdir(mode=0o755)
    marker = existing / "user.tmp"
    marker.write_bytes(b"untouched")
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.create(existing, config(api))
    assert marker.read_bytes() == b"untouched"
    assert stat.S_IMODE(existing.stat().st_mode) == 0o755
    assert list(existing.iterdir()) == [marker]
    subject, directory, cfg = ledger(api, work)
    (directory / "guard").write_bytes(b"not zero content")
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg)
    with pytest.raises(api.BudgetError):
        subject.snapshot()


@pytest.mark.parametrize("path", ["relative", "/bad/../path", "/bad/./path", "/", b"/bad"])
def test_untrusted_path_components_rejected_without_writes(api, path):
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.create(path, config(api))


def test_symlinked_ancestor_rejected(api, work):
    ancestor = work / "ancestor"
    ancestor.mkdir(mode=0o700)
    alias = work / "alias"
    alias.symlink_to(ancestor, target_is_directory=True)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.create(alias / "new", config(api))
    assert not list(ancestor.iterdir())


def child_code(action):
    return textwrap.dedent(f"""
        import json, sys, time
        from train.sql_pilot_budget import BudgetConfig, BudgetLedger, BudgetError
        cfg = BudgetConfig("run", "unverified-profile-model", "{SHA}",
                           "reference-not-proof", 50000000, 25)
        subject = BudgetLedger.open(sys.argv[1], cfg)
        {action}
    """)


def run_child(code, directory):
    result = subprocess.run([sys.executable, "-B", "-c", code, str(directory)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("stage", ["create", "reserve", "claim"])
def test_eight_real_processes_one_winner(api, work, stage):
    if stage == "create":
        subject, directory, cfg = None, work / "ledger", config(api)
    else:
        subject, directory, cfg = ledger(api, work)
    if stage == "claim":
        subject.reserve("contended", LIMIT)
    actions = {
        "create": "BudgetLedger.create(sys.argv[1], cfg)",
        "reserve": 'subject.reserve("contended", 50000000)',
        "claim": 'subject.claim_dispatch("contended")',
    }
    action = actions[stage]
    code = child_code("print('READY', flush=True)")
    if stage == "create":
        code = code.replace("subject = BudgetLedger.open(sys.argv[1], cfg)", "subject = None")
    code += "\nsys.stdin.readline()\ntry:\n    " + action
    code += "\nexcept BudgetError:\n    print('REJECT', flush=True)\nelse:\n    print('WIN', flush=True)\n"
    processes = []
    try:
        for _ in range(8):
            processes.append(subprocess.Popen(
                [sys.executable, "-B", "-c", code, str(directory)], cwd=ROOT,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True))
        for process in processes:
            assert select.select([process.stdout], [], [], 30)[0], "child readiness timeout"
            assert process.stdout.readline().strip() == "READY"
        for process in processes:
            process.stdin.write("go\n")
            process.stdin.flush()
        outputs = []
        for process in processes:
            output, error = process.communicate(timeout=30)
            assert process.returncode == 0, error
            outputs.append(output.strip())
        assert outputs.count("WIN") == 1
        assert outputs.count("REJECT") == 7
        snapshot = api.BudgetLedger.open(directory, cfg).snapshot()
        assert len(snapshot.requests) == (0 if stage == "create" else 1)
        assert snapshot.exposure_micros == (0 if stage == "create" else LIMIT)
        print("REAL_CONTENTION", stage, "processes=8 winners=1 rejected=7")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


def test_kill_after_durable_claim_ack_and_fresh_replay_rejection(api, work):
    subject, directory, _ = ledger(api, work)
    subject.reserve("crash", LIMIT)
    code = child_code('subject.claim_dispatch("crash")')
    # Claim returned only after durability. Hold its permanent guard again so
    # SIGKILL, rather than normal close, must release this real kernel flock.
    code += ("\nimport fcntl, os\n"
             "guard_fd = os.open(os.path.join(sys.argv[1], 'guard'), "
             "os.O_RDONLY | os.O_NOFOLLOW)\n"
             "fcntl.flock(guard_fd, fcntl.LOCK_EX)\n"
             "print('DURABLE_ACK_GUARD_HELD', flush=True)\ntime.sleep(120)\n")
    process = subprocess.Popen([sys.executable, "-B", "-c", code, str(directory)],
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    try:
        assert select.select([process.stdout], [], [], 30)[0], "claim ACK timeout"
        assert process.stdout.readline().strip() == "DURABLE_ACK_GUARD_HELD"
        before = (directory / "state.json").read_bytes()
        process.kill()
        process.communicate(timeout=10)
        assert process.returncode < 0
        probe = child_code("assert subject.snapshot().reserved_charge_micros == 50000000")
        probe += ("\ntry:\n    subject.claim_dispatch('crash')\nexcept BudgetError:\n"
                  "    print('REPLAY_REJECTED')\nelse:\n    raise AssertionError('replayed claim')\n")
        assert run_child(probe, directory) == "REPLAY_REJECTED"
        assert (directory / "state.json").read_bytes() == before
        print("REAL_CRASH", "owned_pid=" + str(process.pid),
              "exit=" + str(process.returncode), "kernel_guard_released replay_rejected",
              "durable_sha256=" + hashlib.sha256(before).hexdigest())
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


@pytest.mark.parametrize("phase", ["before", "after"])
def test_real_fsync_replace_order_and_uncertain_commit(api, work, monkeypatch, phase):
    subject, directory, cfg = ledger(api, work)
    events = []
    real_fsync, real_replace = api.os.fsync, api.os.replace
    def fsync(fd):
        events.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        return real_fsync(fd)
    def replace(*args, **kwargs):
        events.append("replace")
        return real_replace(*args, **kwargs)
    monkeypatch.setattr(api.os, "fsync", fsync)
    monkeypatch.setattr(api.os, "replace", replace)
    subject.reserve("one", 1)
    assert events == ["file", "replace", "dir"]
    def uncertain(fd):
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if is_directory and phase == "before":
            raise OSError("injected pre-directory-fsync uncertainty")
        real_fsync(fd)
        if is_directory:
            raise OSError("injected post-directory-fsync uncertainty")
    monkeypatch.setattr(api.os, "fsync", uncertain)
    with pytest.raises(api.BudgetError, match="uncertain"):
        subject.claim_dispatch("one")
    assert not list(directory.glob(".budget-*.tmp"))
    code = child_code("assert subject.snapshot().requests[0].state == 'dispatch_claimed'")
    assert run_child(code + "\nprint('REAL_COMMIT_OBSERVED')\n", directory) == "REAL_COMMIT_OBSERVED"
    monkeypatch.setattr(api.os, "fsync", real_fsync)
    with pytest.raises(api.BudgetError):
        api.BudgetLedger.open(directory, cfg).claim_dispatch("one")


def test_close_failure_is_uncertain_and_releases_remaining_descriptors(api, work, monkeypatch):
    subject, directory, _ = ledger(api, work)
    guard = (directory / "guard").stat()
    real_close = api.os.close
    injected = False
    def close(fd):
        nonlocal injected
        info = os.fstat(fd)
        real_close(fd)
        if not injected and (info.st_dev, info.st_ino) == (guard.st_dev, guard.st_ino):
            injected = True
            raise OSError("injected guard close failure after actual close")
    monkeypatch.setattr(api.os, "close", close)
    with pytest.raises(api.BudgetError, match="uncertain"):
        subject.reserve("one", 1)
    assert injected
    probe = child_code("assert subject.snapshot().requests[0].state == 'reserved'")
    assert run_child(probe + "\nprint('UNCERTAIN_RESERVATION_OBSERVED')\n", directory) == (
        "UNCERTAIN_RESERVATION_OBSERVED"
    )


@pytest.mark.parametrize("where", ["file_fsync", "replace"])
def test_pre_replace_failure_preserves_state_and_only_own_temp_cleanup(
        api, work, monkeypatch, where):
    subject, directory, _ = ledger(api, work)
    unrelated = directory / "unrelated.tmp"
    unrelated.write_bytes(b"preserve")
    before = (directory / "state.json").read_bytes()
    def fail(*args, **kwargs):
        raise OSError("injected commit failure")
    monkeypatch.setattr(api.os, "fsync" if where == "file_fsync" else "replace", fail)
    with pytest.raises(api.BudgetError, match="uncertain"):
        subject.reserve("one", 1)
    assert (directory / "state.json").read_bytes() == before
    assert unrelated.read_bytes() == b"preserve"
    assert not list(directory.glob(".budget-*.tmp"))


def _sentinel(name, api, directory):
    """Called in fresh processes against the actual public API."""
    cfg = config(api)
    api.BudgetLedger.create(directory, cfg)
    subject = api.BudgetLedger.open(directory, cfg)
    def rejected(call):
        try:
            call()
        except api.BudgetError:
            return True
        return False
    if name == "money":
        assert rejected(lambda: subject.reserve("one", LIMIT + 1)), "sentinel money"
    elif name == "count":
        for number in range(25):
            finish(subject, str(number))
        assert rejected(lambda: subject.reserve("26", 1)), "sentinel count"
    elif name == "retention":
        subject.reserve("unknown", LIMIT)
        subject = api.BudgetLedger.open(directory, cfg)
        assert subject.snapshot().reserved_charge_micros == LIMIT, "sentinel retention"
    elif name == "claim":
        subject.reserve("one", 1)
        subject.claim_dispatch("one")
        subject = api.BudgetLedger.open(directory, cfg)
        assert rejected(lambda: subject.claim_dispatch("one")), "sentinel claim"
    elif name == "binding":
        assert rejected(lambda: api.BudgetLedger.open(
            directory, dataclasses.replace(cfg, run_id="other"))), "sentinel binding"
    else:
        raise AssertionError("unknown sentinel")


MUTANTS = {
    "money": ("return exposure + maximum <= config.limit_usd_micros", "return True"),
    "count": ("return count <= config.request_limit", "return True"),
    "retention": ('return tuple(record for record in requests if record.state != "settled")',
                  "return ()"),
    "claim": ('return state == "reserved"', 'return state in ("reserved", "dispatch_claimed")'),
    "binding": ("return left == right", "return True"),
}


def sentinel_process(work, name, mutant):
    code = textwrap.dedent("""
        import pathlib, sys, types
        from train.test_sql_pilot_budget import MUTANTS, _sentinel
        path = pathlib.Path("train/sql_pilot_budget.py")
        source = path.read_text()
        if sys.argv[2] == "mutant":
            old, new = MUTANTS[sys.argv[1]]
            assert source.count(old) == 1, "mutation gate missing"
            source = source.replace(old, new)
        module = types.ModuleType("budget_subject")
        sys.modules[module.__name__] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        _sentinel(sys.argv[1], module, pathlib.Path(sys.argv[3]))
        print("SENTINEL_PASS", sys.argv[1])
    """)
    return subprocess.run(
        [sys.executable, "-B", "-c", code, name, "mutant" if mutant else "baseline",
         str(work / name)], cwd=ROOT, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("name", list(MUTANTS))
def test_fresh_process_baseline_sentinel(api, work, name):
    result = sentinel_process(work, name, False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "SENTINEL_PASS " + name
    print(result.stdout.strip())


@pytest.mark.parametrize("name", list(MUTANTS))
def test_independent_mutant_intended_assertion_red(api, work, name):
    result = sentinel_process(work, name, True)
    assert result.returncode == 1
    assert "AssertionError: sentinel " + name in result.stderr, result.stderr
    assert "SENTINEL_PASS" not in result.stdout
    print("MUTANT_INTENDED_RED", name, "exit=" + str(result.returncode))
    print(result.stderr, end="")
