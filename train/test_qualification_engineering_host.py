"""Named numeric tests for train.qualification_engineering_host (plan file A).

Finite ordinary pytest tests, no parametrization, no plugins, no processes,
no SDK, no network. UNRUN at delivery: the parent executes and reviews.
Every test name and numeric criterion comes from
docs/core-v159-host-plan.md (including the revision-3 durable-claim tests
24-28) before implementation.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import hashlib
import inspect
import json
import os
import pickle
import stat

import pytest

from train import native_qualification as native
from train import qualification_engineering_host as host
from train.engineering_budget import (
    AncillaryEstimates,
    BudgetTerms,
    EngineeringBudgetPlan,
    GpuWorkload,
    PreparationAccount,
    RateObservation,
    ResourceRates,
    plan_engineering_budget,
)
from train.qualification_image_plan import candidate_recipe, recipe_sha256


_NOW = 1_800_000_000
_APP_ID = "ap-" + "A1b2C3d4E5" * 2 + "F6"
_SANDBOX_ID = "sb-" + "B1c2D3e4F5a6"
_HEX64 = "a" * 64


def _request() -> native.QualificationRequest:
    return native.QualificationRequest(
        tasks=(), db_root=Path("/synthetic/data"),
        model_dir=Path("/synthetic/model"), output_dir=Path("/synthetic/output"),
        source_pins=(), database_pins=(),
        runtime_inventory=native.FilePin(Path("/synthetic/inventory.json"), 0, "0" * 64),
        image_digest="synthetic-not-admitted",
        bounds=native.AttemptBounds(
            Decimal("25"), Decimal("0"), Decimal("25"), 1800, 128, 1024, 60,
        ),
    )


def _terms() -> BudgetTerms:
    return BudgetTerms(Decimal("25"), Decimal("5"))


def _rates() -> ResourceRates:
    return ResourceRates(
        runtime_context="sandbox",
        gpu=RateObservation(Decimal("0.00001"), "USD/gpu-second", "pricing-page", _NOW - 100),
        cpu=RateObservation(
            Decimal("0.000001"), "USD/physical-core-second", "pricing-page", _NOW - 100,
        ),
        ram=RateObservation(
            Decimal("0.000001"), "USD/GiB-second", "pricing-page", _NOW - 100,
        ),
    )


def _workload(duration_seconds: int = 1200) -> GpuWorkload:
    return GpuWorkload(1, 4, Decimal("16"), duration_seconds)


def _preparation() -> PreparationAccount:
    return PreparationAccount(Decimal("1"), Decimal("0.5"), Decimal("2"))


def _ancillary() -> AncillaryEstimates:
    return AncillaryEstimates(Decimal("0.5"), Decimal("0.25"), Decimal("1"))


def _pin(**overrides) -> native.FilePin:
    values = {"path": Path("/synthetic/policy.json"), "size": 128, "sha256": _HEX64}
    values.update(overrides)
    return native.FilePin(**values)


def _policy(directory: Path, name: str = "policy.json",
            data: bytes = b"owner-approved-policy\n") -> native.FilePin:
    """REAL private policy file fixture with a matching FilePin (0o600)."""
    path = directory / name
    path.write_bytes(data)
    path.chmod(0o600)
    return native.FilePin(path, len(data), hashlib.sha256(data).hexdigest())


def _uploads() -> tuple[tuple[str, str, int, str], ...]:
    return (
        ("source", "train/worker.py", 1024, "b" * 64),
        ("wheels", "pkg-1.0.whl", 2048, "c" * 64),
    )


def _argv() -> tuple[str, ...]:
    return ("python", "-m", "pip", "install", "--no-index", "--find-links", "/wheels", "-r", "requirements.txt")


def _issue(**overrides) -> host.EngineeringAuthorization:
    recipe = candidate_recipe()
    kwargs = {
        "request": _request(),
        "policy_pin": _pin(),
        "terms": _terms(),
        "rates": _rates(),
        "workload": _workload(),
        "preparation": _preparation(),
        "ancillary": _ancillary(),
        "now_seconds": _NOW,
        "expires_at_seconds": _NOW + 3600,
        "preparation_seconds": 600,
        "image_base_reference": recipe.base_reference,
        "image_recipe_sha256": recipe_sha256(recipe),
        "gpu_label": "A100",
        "uploads": _uploads(),
        "setup_argv": _argv(),
    }
    kwargs.update(overrides)
    return host.issue_engineering_authorization(**kwargs)


def test_issue_binds_exact_request_digest() -> None:
    request = _request()
    authorization = _issue(request=request)
    expected = native._request_binding(request)
    assert len(expected) == 64
    assert authorization.request_binding == expected
    assert authorization.request is request


def test_issue_recomputes_plan_and_accepts_no_plan_label() -> None:
    parameters = inspect.signature(host.issue_engineering_authorization).parameters
    assert "plan" not in parameters
    assert "plan_label" not in parameters
    authorization = _issue()
    expected = plan_engineering_budget(
        _terms(), _rates(), _workload(), _preparation(), _ancillary(), _NOW,
    )
    actual = authorization.plan
    assert type(actual) is EngineeringBudgetPlan
    assert len(actual.breakdown) == 7
    assert actual == expected


def test_workload_duration_1800_accepted() -> None:
    authorization = _issue(workload=_workload(1800))
    assert authorization.workload.duration_seconds == 1800


def test_workload_duration_1801_rejected() -> None:
    with pytest.raises(ValueError):
        _issue(workload=_workload(1801))


def test_policy_pin_requires_exact_native_filepin() -> None:
    for substitute in (True, 1, "path", {"path": "/synthetic/policy.json"}):
        with pytest.raises(ValueError):
            _issue(policy_pin=substitute)
    assert type(_issue().policy_pin) is native.FilePin


def test_policy_pin_rejects_bad_shape() -> None:
    refusals = (
        _pin(path=Path("relative/policy.json")),
        _pin(path=Path("/synthetic/../policy.json")),
        _pin(size=0),
        _pin(sha256="a" * 63),
        _pin(sha256="a" * 65),
        _pin(sha256="A" * 64),
    )
    assert len(refusals) == 6
    for pin in refusals:
        with pytest.raises(ValueError):
            _issue(policy_pin=pin)


def test_expired_authority_refuses() -> None:
    authorization = _issue(now_seconds=_NOW, expires_at_seconds=_NOW + 100)
    authorization.require_valid(now_seconds=_NOW + 99)
    with pytest.raises(PermissionError):
        authorization.require_valid(now_seconds=_NOW + 100)
    with pytest.raises(PermissionError):
        authorization.require_valid(now_seconds=_NOW + 101)


def test_authority_expiry_window_bounds() -> None:
    for invalid in (0, -1, 86401):
        with pytest.raises(ValueError):
            _issue(now_seconds=_NOW, expires_at_seconds=_NOW + invalid)
    for valid in (1, 86400):
        authorization = _issue(now_seconds=_NOW, expires_at_seconds=_NOW + valid)
        assert authorization.expires_at_seconds - authorization.issued_at_seconds == valid


def test_clock_backwards_refuses() -> None:
    authorization = _issue()
    with pytest.raises(PermissionError):
        authorization.require_valid(now_seconds=_NOW - 1)


def test_authorization_single_use_binding() -> None:
    authorization = _issue()
    assert authorization.bound is False
    authorization._bind_once()
    assert authorization.bound is True
    with pytest.raises(PermissionError):
        authorization._bind_once()


def test_authorization_not_serializable() -> None:
    authorization = _issue()
    with pytest.raises(TypeError):
        pickle.dumps(authorization)
    with pytest.raises(TypeError):
        authorization.__reduce_ex__(4)


def test_budget_helper_alone_is_not_authority() -> None:
    plan = plan_engineering_budget(
        _terms(), _rates(), _workload(), _preparation(), _ancillary(), _NOW,
    )
    with pytest.raises(PermissionError):
        host.EngineeringAuthorization(
            plan,  # a budget plan as issuer token is not authority
            request=_request(), request_binding="0" * 64, policy_pin=_pin(),
            plan=plan, workload=_workload(), setup_argv=_argv(),
            uploads=_uploads(), preparation_seconds=600,
            issued_at_seconds=_NOW, expires_at_seconds=_NOW + 3600,
            image_base_reference=candidate_recipe().base_reference,
            image_recipe_sha256=recipe_sha256(candidate_recipe()),
            gpu_label="A100",
        )


def test_reservation_first_claim_creates_record(tmp_path: Path) -> None:
    pin = _policy(tmp_path)
    authorization = _issue(policy_pin=pin)
    record = host.sealed_claim_record_path(authorization)
    assert record == tmp_path / f".qualification-attempt-{pin.sha256}.jsonl"
    reservation = host.claim_attempt_reservation(authorization)
    assert reservation.record_path == record
    assert reservation.policy_sha256 == pin.sha256
    assert reservation.request_binding == authorization.request_binding
    assert record.exists()
    assert os.stat(record).st_mode & 0o777 == 0o600
    assert record.read_bytes() == (
        b'{"v":1,"event":"reserved","policy_sha256":"' + pin.sha256.encode("ascii")
        + b'","request_binding":"' + authorization.request_binding.encode("ascii")
        + b'"}\n'
    )
    assert reservation.consumed is False
    assert reservation.closed is False


def test_reservation_second_claim_refuses_without_reads(tmp_path: Path) -> None:
    pin = _policy(tmp_path)
    first = _issue(policy_pin=pin)
    host.claim_attempt_reservation(first)
    record = host.sealed_claim_record_path(first)
    before = record.read_bytes()
    # Reissued identical approved inputs (fresh clock/expiry, fresh objects):
    # the same policy pin forces the identical claim location, so the old
    # claim refuses the bypass with no reads/recovery.
    reissued = _issue(
        policy_pin=pin, now_seconds=_NOW + 10, expires_at_seconds=_NOW + 3610,
    )
    assert reissued is not first
    assert host.sealed_claim_record_path(reissued) == record
    with pytest.raises(FileExistsError):
        host.claim_attempt_reservation(reissued)
    assert record.exists()
    assert record.read_bytes() == before


def test_reservation_existing_symlink_refuses(tmp_path: Path) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    record = host.sealed_claim_record_path(authorization)
    target = tmp_path / "target.jsonl"
    target.write_bytes(b"prior-record\n")
    record.symlink_to(target)
    with pytest.raises(OSError):
        host.claim_attempt_reservation(authorization)
    assert target.read_bytes() == b"prior-record\n"


def test_reservation_consume_once(tmp_path: Path) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    reservation = host.claim_attempt_reservation(authorization)
    reservation.consume()
    assert reservation.consumed is True
    with pytest.raises(RuntimeError):
        reservation.consume()


def test_reservation_identity_appends_only(tmp_path: Path) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    reservation = host.claim_attempt_reservation(authorization)
    record = reservation.record_path
    prefix = record.read_bytes()
    reservation.record_identity("app", _APP_ID)
    after_app = record.read_bytes()
    assert after_app.startswith(prefix)
    appended = after_app[len(prefix):]
    assert appended.count(b"\n") == 1
    row = json.loads(appended)
    assert row == {"event": "identity", "kind": "app", "identity": _APP_ID}
    reservation.record_identity("sandbox", _SANDBOX_ID)
    after_sandbox = record.read_bytes()
    assert after_sandbox.startswith(after_app)
    assert after_sandbox[len(after_app):].count(b"\n") == 1
    for kind, identity in (
        ("database", _APP_ID),          # bad kind
        ("app", 42),                    # non-str identity
        ("app", "ap-short"),            # pattern mismatch
        ("sandbox", "xb-" + "b" * 22),  # wrong service prefix
    ):
        with pytest.raises(ValueError):
            reservation.record_identity(kind, identity)
    assert record.read_bytes() == after_sandbox


def test_reservation_close_idempotent(tmp_path: Path) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    reservation = host.claim_attempt_reservation(authorization)
    record = reservation.record_path
    prefix = record.read_bytes()
    reservation.close("stopped")
    after = record.read_bytes()
    assert after.startswith(prefix)
    assert json.loads(after[len(prefix):]) == {"event": "stopped"}
    assert reservation.closed is True
    reservation.close("stopped")
    assert record.read_bytes() == after
    with pytest.raises(ValueError):
        reservation.close("finished")


def test_reservation_not_serializable(tmp_path: Path) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    reservation = host.claim_attempt_reservation(authorization)
    with pytest.raises(TypeError):
        pickle.dumps(reservation)
    with pytest.raises(TypeError):
        reservation.__reduce_ex__(4)


def test_uploads_and_setup_argv_sealed_at_issuance() -> None:
    good = ("source", "train/worker.py", 1024, "b" * 64)
    upload_refusals = (
        (("other", "train/worker.py", 1024, "b" * 64),),       # root outside sealed set
        (("source", "../worker.py", 1024, "b" * 64),),         # traversal key
        (("source", "/abs/worker.py", 1024, "b" * 64),),       # absolute key
        (("source", "", 1024, "b" * 64),),                     # empty key
        (("source", "train/worker.py", -1, "b" * 64),),        # negative size
        (("source", "train/worker.py", 2**36 + 1, "b" * 64),), # oversized size
        (("source", "train/worker.py", 1024, "z" * 64),),      # non-hex sha
        (good, good),                                          # duplicate (root, key)
    )
    assert len(upload_refusals) == 8
    for uploads in upload_refusals:
        with pytest.raises(ValueError):
            _issue(uploads=uploads)
    argv_refusals = (
        (),                        # empty argv
        tuple(str(i) for i in range(65)),  # 65 items
        ("x" * 4097,),             # 4097-char item
        ("python", "a\0b"),        # embedded NUL
    )
    assert len(argv_refusals) == 4
    for argv in argv_refusals:
        with pytest.raises(ValueError):
            _issue(setup_argv=argv)
    authorization = _issue()
    assert authorization.uploads == _uploads()
    assert authorization.setup_argv == _argv()


def test_gpu_label_one_exact_gpu_only() -> None:
    accepted = _issue(gpu_label="A100")
    assert accepted.gpu_label == "A100"
    suffixed = _issue(gpu_label="A100:1")
    assert suffixed.gpu_label == "A100:1"
    refusals = (
        "A100:8",      # multi-GPU suffix escape
        "A100:2",      # suffix count != charged workload count (1)
        "A100:0",      # zero count suffix
        "any",         # fallback syntax
        "ANY",         # fallback syntax, any casing
        "any:1",       # fallback name even with count 1
        "A100,A10G",   # comma list syntax
        "A100;A10G",   # semicolon list syntax
        "A100 2",      # whitespace-separated list syntax
        "A100:",       # empty count suffix
        ":1",          # empty gpu name
        "A100:01",     # non-canonical leading-zero count
        "A100:1:2",    # repeated colons
        "",            # empty label
        42,            # non-str label
    )
    assert len(refusals) == 15
    for gpu_label in refusals:
        with pytest.raises(ValueError):
            _issue(gpu_label=gpu_label)
    # The parsed count binds to the charged workload: a workload carrying
    # any gpu_count other than 1 refuses the whole issuance (budget first),
    # so no label can ever allocate beyond the single charged GPU.
    with pytest.raises(ValueError):
        _issue(gpu_label="A100:2", workload=GpuWorkload(2, 4, Decimal("16"), 1200))


def test_claim_location_sealed_to_policy_identity(tmp_path: Path) -> None:
    pin = _policy(tmp_path)
    first = _issue(policy_pin=pin)
    signature = inspect.signature(host.claim_attempt_reservation)
    assert list(signature.parameters) == ["authorization"]
    with pytest.raises(TypeError):
        host.claim_attempt_reservation(first, record_path=tmp_path / "other.jsonl")
    reservation = host.claim_attempt_reservation(first)
    record = reservation.record_path
    assert record == tmp_path / f".qualification-attempt-{pin.sha256}.jsonl"
    row = json.loads(record.read_bytes())
    assert row["policy_sha256"] == pin.sha256
    assert row["request_binding"] == first.request_binding
    before = record.read_bytes()
    # A reissued authorization (fresh clock/expiry, fresh request object,
    # same approved policy pin) maps to the identical claim location, so a
    # single claim per exact approved policy holds across new objects.
    reissued = _issue(
        policy_pin=pin, now_seconds=_NOW + 10, expires_at_seconds=_NOW + 3610,
    )
    assert reissued is not first
    assert host.sealed_claim_record_path(reissued) == record
    with pytest.raises(FileExistsError):
        host.claim_attempt_reservation(reissued)
    assert record.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [pin.path.name, record.name]
    )


def test_claim_requires_sealed_authorization(tmp_path: Path) -> None:
    pin = _pin(path=tmp_path / "policy.json")
    for stand_in in (True, {"policy": "approved"}, pin, None):
        with pytest.raises(PermissionError):
            host.claim_attempt_reservation(stand_in)
        with pytest.raises(PermissionError):
            host.sealed_claim_record_path(stand_in)
    assert list(tmp_path.iterdir()) == []


def test_claim_validates_real_policy_bytes_and_ownership(tmp_path: Path) -> None:
    def _records() -> list:
        return sorted(p for p in tmp_path.iterdir()
                      if p.name.startswith(".qualification-attempt-"))

    pin = _policy(tmp_path)
    authorization = _issue(policy_pin=pin)
    reservation = host.claim_attempt_reservation(authorization)
    record = reservation.record_path
    assert record.read_bytes() == (
        b'{"v":1,"event":"reserved","policy_sha256":"' + pin.sha256.encode("ascii")
        + b'","request_binding":"' + authorization.request_binding.encode("ascii")
        + b'"}\n'
    )
    # Remove the accepted claim so every refusal below witnesses ZERO records.
    os.unlink(record)
    original = pin.path.read_bytes()
    drift = tmp_path / "drift.json"
    drifted = bytes([original[0] ^ 0xFF]) + original[1:]
    assert len(drifted) == len(original)
    drift.write_bytes(drifted)
    drift.chmod(0o600)
    symlink = tmp_path / "symlink-policy.json"
    os.symlink(pin.path, symlink)
    hardlink = tmp_path / "hardlink-policy.json"
    os.link(pin.path, hardlink)
    as_dir = tmp_path / "dir-policy.json"
    as_dir.mkdir()
    group_writable = tmp_path / "group-policy.json"
    group_writable.write_bytes(original)
    group_writable.chmod(0o660)
    other_writable = tmp_path / "other-policy.json"
    other_writable.write_bytes(original)
    other_writable.chmod(0o664)
    refusals = (
        # 1: missing policy file
        _pin(path=tmp_path / "missing.json", size=64,
             sha256=hashlib.sha256(b"x" * 64).hexdigest()),
        # 2: byte drift (same size, different bytes)
        native.FilePin(drift, len(drifted), pin.sha256),
        # 3: size drift (+1)
        native.FilePin(pin.path, pin.size + 1, pin.sha256),
        # 4: hash drift
        native.FilePin(pin.path, pin.size, "b" * 64),
        # 5: symlinked policy path
        native.FilePin(symlink, pin.size, pin.sha256),
        # 6: hardlinked policy (st_nlink 2)
        native.FilePin(hardlink, pin.size, pin.sha256),
        # 7: directory at the policy path (non-regular)
        native.FilePin(as_dir, os.stat(as_dir).st_size, "0" * 64),
        # 8: group-writable policy
        native.FilePin(group_writable, pin.size, pin.sha256),
        # 9: other-writable policy
        native.FilePin(other_writable, pin.size, pin.sha256),
    )
    assert len(refusals) == 9
    for bad_pin in refusals:
        with pytest.raises(OSError):
            host.claim_attempt_reservation(_issue(policy_pin=bad_pin))
        assert _records() == []


def test_claim_ancestor_chain_and_private_directory_validated(tmp_path: Path) -> None:
    def _records() -> list:
        return sorted(tmp_path.rglob(".qualification-attempt-*"))

    # 1: symlinked immediate parent refuses (nofollow traversal)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_pin = _policy(real_parent)
    linked_parent = tmp_path / "linked-parent"
    os.symlink(real_parent, linked_parent)
    symlink_pin = native.FilePin(
        linked_parent / real_pin.path.name, real_pin.size, real_pin.sha256,
    )
    with pytest.raises(OSError):
        host.claim_attempt_reservation(_issue(policy_pin=symlink_pin))
    assert _records() == []
    # 2: group-writable immediate parent (0o770) refuses
    group_parent = tmp_path / "group-parent"
    group_parent.mkdir()
    group_pin = _policy(group_parent)
    group_parent.chmod(0o770)
    with pytest.raises(OSError):
        host.claim_attempt_reservation(_issue(policy_pin=group_pin))
    assert _records() == []
    # 3+4: unsafe intermediate ancestors (0o777, 0o775) refuse
    for mode in (0o777, 0o775):
        mid = tmp_path / f"mid-{mode:o}"
        inner = mid / "inner"
        inner.mkdir(parents=True)
        inner_pin = _policy(inner)
        mid.chmod(mode)
        with pytest.raises(OSError):
            host.claim_attempt_reservation(_issue(policy_pin=inner_pin))
        assert _records() == []
    # positive control: identical layout with the intermediate at 0o755
    # claims successfully (the ancestry check can pass, not only fail)
    mid = tmp_path / "mid-0755"
    inner = mid / "inner"
    inner.mkdir(parents=True)
    inner_pin = _policy(inner)
    mid.chmod(0o755)
    reservation = host.claim_attempt_reservation(_issue(policy_pin=inner_pin))
    assert reservation.record_path.exists()
    assert len(_records()) == 1


def test_claim_symlinked_parent_switch_cannot_double_claim(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    pin = _policy(parent)
    data = pin.path.read_bytes()
    authorization = _issue(policy_pin=pin)
    reservation = host.claim_attempt_reservation(authorization)
    record = reservation.record_path
    marker = record.read_bytes()
    # Same-uid attacker renames the parent aside and switches a symlink in.
    os.rename(parent, tmp_path / "parent-old")
    other = tmp_path / "other"
    other.mkdir()
    os.symlink(other, parent)
    reissued = _issue(
        policy_pin=pin, now_seconds=_NOW + 10, expires_at_seconds=_NOW + 3610,
    )
    with pytest.raises(OSError):
        host.claim_attempt_reservation(reissued)
    assert list(other.iterdir()) == []
    # Even a copied policy inside the switched-to directory cannot claim.
    (other / pin.path.name).write_bytes(data)
    with pytest.raises(OSError):
        host.claim_attempt_reservation(reissued)
    assert sorted(p.name for p in other.iterdir()) == [pin.path.name]
    # The original marker stays unread/unrecovered/unmodified.
    assert (tmp_path / "parent-old" / record.name).read_bytes() == marker


def test_claim_failure_paths_close_all_fds(tmp_path: Path, monkeypatch) -> None:
    pin = _policy(tmp_path)
    authorization = _issue(policy_pin=pin)
    opened: list = []
    closed: list = []
    real_open = os.open
    real_close = os.close

    def counting_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def counting_close(fd, *args, **kwargs):
        closed.append(fd)
        return real_close(fd, *args, **kwargs)

    monkeypatch.setattr(os, "open", counting_open)
    monkeypatch.setattr(os, "close", counting_close)
    # Successful claim retains exactly 1 FD (the claim directory's).
    opened.clear()
    closed.clear()
    reservation = host.claim_attempt_reservation(authorization)
    assert len(opened) == len(closed) + 1
    # Every append is balanced (record FD closed after each append).
    opened.clear()
    closed.clear()
    reservation.record_identity("app", _APP_ID)
    assert sorted(opened) == sorted(closed)
    # Failure: reissued second claim closes every FD it opened.
    opened.clear()
    closed.clear()
    reissued = _issue(
        policy_pin=pin, now_seconds=_NOW + 10, expires_at_seconds=_NOW + 3610,
    )
    with pytest.raises(FileExistsError):
        host.claim_attempt_reservation(reissued)
    assert sorted(opened) == sorted(closed)
    # Failure: hash-drifted policy closes every FD it opened.
    opened.clear()
    closed.clear()
    drifted = _issue(policy_pin=native.FilePin(pin.path, pin.size, "b" * 64))
    with pytest.raises(OSError):
        host.claim_attempt_reservation(drifted)
    assert sorted(opened) == sorted(closed)
    # Failure: symlinked parent closes every FD it opened.
    sub = tmp_path / "sub"
    sub.mkdir()
    sub_pin = _policy(sub)
    alias = tmp_path / "alias"
    os.symlink(sub, alias)
    symlink_auth = _issue(policy_pin=native.FilePin(
        alias / sub_pin.path.name, sub_pin.size, sub_pin.sha256,
    ))
    opened.clear()
    closed.clear()
    with pytest.raises(OSError):
        host.claim_attempt_reservation(symlink_auth)
    assert sorted(opened) == sorted(closed)


def test_append_relative_to_retained_dir_fd_rejects_alias(tmp_path: Path) -> None:
    pin = _policy(tmp_path)
    authorization = _issue(policy_pin=pin)
    reservation = host.claim_attempt_reservation(authorization)
    record = reservation.record_path
    prefix = record.read_bytes()
    reservation.record_identity("app", _APP_ID)
    after = record.read_bytes()
    assert after.startswith(prefix)
    moved = tmp_path / "moved.jsonl"
    os.rename(record, moved)
    # Symlink alias at the record name: refuses; target and moved untouched.
    target = tmp_path / "target.jsonl"
    target.write_bytes(b"attacker\n")
    os.symlink(target, record)
    with pytest.raises(OSError):
        reservation.record_identity("sandbox", _SANDBOX_ID)
    assert target.read_bytes() == b"attacker\n"
    assert moved.read_bytes() == after
    os.unlink(record)
    # Fresh regular-file replacement: inode mismatch refuses with zero writes.
    replacement = (
        b'{"v":1,"event":"reserved","policy_sha256":"'
        + pin.sha256.encode("ascii") + b'"}\n'
    )
    record.write_bytes(replacement)
    with pytest.raises(OSError):
        reservation.record_identity("sandbox", _SANDBOX_ID)
    assert record.read_bytes() == replacement
    assert moved.read_bytes() == after
    os.unlink(record)
    # Nothing at the record name: ENOENT refuses; moved still untouched.
    with pytest.raises(OSError):
        reservation.record_identity("sandbox", _SANDBOX_ID)
    assert moved.read_bytes() == after


def _tracked_claim(tmp_path, monkeypatch):
    """Track real descriptors from before claim through failed/successful close."""
    authorization = _issue(policy_pin=_policy(tmp_path))
    real_open, real_close = os.open, os.close
    active = set()
    counts = {"opened": 0, "closed": 0}

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        active.add(fd)
        counts["opened"] += 1
        return fd

    def tracked_close(fd):
        real_close(fd)
        active.remove(fd)
        counts["closed"] += 1

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    reservation = host.claim_attempt_reservation(authorization)
    assert len(active) == 1
    return reservation, active, counts


def _assert_terminal_without_more_writes(reservation, monkeypatch):
    writes = []

    def forbidden_write(*args):
        writes.append(args)
        raise AssertionError("terminal reservation wrote again")

    monkeypatch.setattr(os, "write", forbidden_write)
    assert reservation.closed is True
    with pytest.raises(RuntimeError):
        reservation.consume()
    with pytest.raises(RuntimeError):
        reservation.record_identity("app", _APP_ID)
    reservation.close("failed")
    reservation.close("stopped")
    assert writes == []


def test_policy_fifo_open_requires_nonblocking(tmp_path, monkeypatch) -> None:
    policy = tmp_path / "policy-fifo"
    os.mkfifo(policy)
    authorization = _issue(policy_pin=native.FilePin(policy, 1, "a" * 64))
    real_open = os.open
    observed = []

    def guarded_open(path, flags, *args, **kwargs):
        if path == policy.name:
            assert flags & os.O_NONBLOCK, "refuse blocking FIFO open before syscall"
            assert flags & os.O_NOFOLLOW
            observed.append(path)
        return real_open(path, flags, *args, **kwargs)

    def forbidden_read(*args):
        raise AssertionError("nonregular policy must not be read")

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(os, "read", forbidden_read)
    with pytest.raises(OSError, match="regular"):
        host.claim_attempt_reservation(authorization)
    assert observed == [policy.name]
    assert not host.sealed_claim_record_path(authorization).exists()


def test_policy_replacement_during_read_refuses_claim(tmp_path, monkeypatch) -> None:
    pin = _policy(tmp_path)
    authorization = _issue(policy_pin=pin)
    original = pin.path.read_bytes()
    moved = tmp_path / "original-policy"
    real_open, real_close, real_read = os.open, os.close, os.read
    active = set()
    changed = []

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        active.add(fd)
        return fd

    def tracked_close(fd):
        real_close(fd)
        active.remove(fd)

    def replace_after_read(fd, count):
        data = real_read(fd, count)
        if data and not changed:
            changed.append(True)
            pin.path.rename(moved)
            pin.path.write_bytes(original)
            pin.path.chmod(0o600)
        return data

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(OSError, match="identity|changed"):
        host.claim_attempt_reservation(authorization)
    assert changed == [True]
    assert active == set()
    assert not host.sealed_claim_record_path(authorization).exists()
    assert pin.path.read_bytes() == moved.read_bytes() == original
    assert pin.path.stat().st_ino != moved.stat().st_ino


def test_append_fifo_open_requires_nonblocking(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    moved = tmp_path / "original-marker"
    record.rename(moved)
    original = moved.read_bytes()
    os.mkfifo(record)
    tracked_open = os.open
    observed = []
    writes = []

    def guarded_open(path, flags, *args, **kwargs):
        if path == record.name:
            assert flags & os.O_NONBLOCK, "refuse blocking FIFO open before syscall"
            assert flags & os.O_NOFOLLOW
            observed.append(path)
        return tracked_open(path, flags, *args, **kwargs)

    def forbidden_write(*args):
        writes.append(args)
        raise AssertionError("FIFO marker must not be written")

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(os, "write", forbidden_write)
    with pytest.raises(OSError):
        reservation.close("failed")
    assert observed == [record.name]
    assert writes == []
    assert moved.read_bytes() == original
    assert stat.S_ISFIFO(record.stat().st_mode)
    assert active == set()
    assert counts["opened"] == counts["closed"]
    _assert_terminal_without_more_writes(reservation, monkeypatch)


def test_claim_fsync_file_then_directory_before_return(tmp_path, monkeypatch) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    real_fsync = os.fsync
    events = []

    def ordered_fsync(fd):
        mode = os.fstat(fd).st_mode
        events.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fsync", ordered_fsync)
        reservation = host.claim_attempt_reservation(authorization)
        events.append("returned")
        reservation.consume()
    assert events == ["file", "directory", "returned"]
    assert reservation.consumed is True
    reservation.close("failed")


def test_claim_directory_fsync_failure(tmp_path, monkeypatch) -> None:
    authorization = _issue(policy_pin=_policy(tmp_path))
    real_open, real_close, real_fsync = os.open, os.close, os.fsync
    active = set()
    events = []
    primary = OSError("directory sync primary")

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        active.add(fd)
        return fd

    def tracked_close(fd):
        real_close(fd)
        active.remove(fd)

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            events.append("directory")
            raise primary
        events.append("file")
        real_fsync(fd)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(OSError) as info:
        host.claim_attempt_reservation(authorization)
    assert info.value is primary
    assert events == ["file", "directory"]
    assert active == set()
    record = host.sealed_claim_record_path(authorization)
    assert json.loads(record.read_bytes())["event"] == "reserved"


def test_close_short_write_releases_directory(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    original = record.read_bytes()
    real_write = os.write
    writes = []

    def short_write(fd, data):
        writes.append(fd)
        return real_write(fd, data[:-1])

    monkeypatch.setattr(os, "write", short_write)
    with pytest.raises(OSError, match="short reservation"):
        reservation.close("failed")
    assert len(writes) == 1
    assert record.read_bytes().startswith(original)
    assert active == set()
    assert counts["opened"] == counts["closed"]
    _assert_terminal_without_more_writes(reservation, monkeypatch)


def test_close_fsync_failure_retains_directory_after_unknown_child_close(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    original = record.read_bytes()
    primary = OSError("append fsync primary")
    secondary = OSError("secondary close failure")
    directory = reservation._dir_fd
    tracked_close = os.close

    def fail_sync(fd):
        raise primary

    def close_then_fail(fd):
        tracked_close(fd)
        raise secondary

    monkeypatch.setattr(os, "fsync", fail_sync)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(OSError) as info:
        reservation.close("failed")
    assert info.value is primary
    assert record.read_bytes().startswith(original)
    try:
        receipt = host._custody_for_reservation(reservation)
        assert receipt.primary is primary and any(error is secondary for error in receipt.secondary)
        assert receipt.has_unknown and reservation._dir_fd == directory
        assert active == {directory}
        assert counts["opened"] == counts["closed"] + 1
        _assert_terminal_without_more_writes(reservation, monkeypatch)
    finally:
        # Only the never-close-attempted, known-owned fixture anchor.
        tracked_close(directory)


def test_close_replacement_releases_directory(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    original = record.read_bytes()
    moved = tmp_path / "owned-marker"
    record.rename(moved)
    record.write_bytes(b"unknown replacement")
    record.chmod(0o600)
    writes = []

    def forbidden_write(*args):
        writes.append(args)
        raise AssertionError("unknown replacement was written")

    monkeypatch.setattr(os, "write", forbidden_write)
    with pytest.raises(OSError, match="replaced"):
        reservation.close("failed")
    assert writes == []
    assert record.read_bytes() == b"unknown replacement"
    assert moved.read_bytes() == original
    assert active == set()
    assert counts["opened"] == counts["closed"]
    _assert_terminal_without_more_writes(reservation, monkeypatch)


def test_append_mode_drift_refuses_before_write(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    reservation.record_identity("app", _APP_ID)  # Exact 0600 positive control.
    original = record.read_bytes()
    inode = record.stat().st_ino
    record.chmod(0o666)
    assert record.stat().st_ino == inode
    writes = []

    def forbidden_write(*args):
        writes.append(args)
        raise AssertionError("insecure marker mode was written")

    monkeypatch.setattr(os, "write", forbidden_write)
    with pytest.raises(OSError, match="private|mode"):
        reservation.close("failed")
    assert writes == []
    assert record.read_bytes() == original
    assert active == set()
    assert counts["opened"] == counts["closed"]


def test_append_owner_drift_refuses_before_write(tmp_path, monkeypatch) -> None:
    reservation, active, counts = _tracked_claim(tmp_path, monkeypatch)
    record = reservation.record_path
    original = record.read_bytes()
    real_fstat = os.fstat
    writes = []

    def foreign_owner(fd):
        info = real_fstat(fd)
        if stat.S_ISREG(info.st_mode):
            fields = list(info)
            fields[4] = os.geteuid() + 1
            return os.stat_result(fields)
        return info

    def forbidden_write(*args):
        writes.append(args)
        raise AssertionError("foreign-owned marker was written")

    monkeypatch.setattr(os, "fstat", foreign_owner)
    monkeypatch.setattr(os, "write", forbidden_write)
    with pytest.raises(OSError, match="owner|private"):
        reservation.close("failed")
    assert writes == []
    assert record.read_bytes() == original
    assert active == set()
    assert counts["opened"] == counts["closed"]
