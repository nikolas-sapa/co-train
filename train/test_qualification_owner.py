from dataclasses import replace
from decimal import Decimal
import importlib
import importlib.util
import json
from pathlib import Path
import pickle

import pytest


@pytest.fixture(autouse=True)
def _local_lifecycle_only(monkeypatch):
    """Stub unavailable external review only for these local lifecycle checks."""
    from train import qualification_launch_admission as admission

    monkeypatch.setattr(admission, "_require_provider_review", lambda request, quote: None)


def _quote(request, *, issued_at=100.0, expires_at=4000.0, provisioning=0, teardown=0):
    from train.qualification_costs import Charge, CostLedger
    from train.qualification_launch_admission import freeze_cost_quote

    zero = Decimal("0")
    charges = {
        name: Charge(zero, "item", zero, "USD/item", None)
        for name in ("preparation", "build", "provisioning", "teardown", "replay", "ancillary")
    }
    seconds = Decimal(request.bounds.lifetime_seconds + provisioning + teardown)
    charges.update({
        "gpu": Charge(Decimal("1"), "gpu", zero, "USD/gpu-second", seconds),
        "cpu": Charge(Decimal("1"), "physical-core", zero, "USD/physical-core-second", seconds),
        "ram": Charge(Decimal("1"), "GiB", zero, "USD/GiB-second", seconds),
        "storage": Charge(Decimal("1"), "GiB", zero, "USD/GiB-second", seconds),
        "retention": Charge(Decimal("1"), "GiB", zero, "USD/GiB-second",
                            Decimal(request.bounds.retention_seconds)),
        "egress": Charge(Decimal("1"), "GiB", zero, "USD/GiB", None),
    })
    ledger = CostLedger(request.bounds.prior_usage_usd, zero, provisioning, teardown, charges)
    return freeze_cost_quote(request.bounds, ledger, issued_at=issued_at, expires_at=expires_at)


def _api():
    assert importlib.util.find_spec("train.qualification_owner") is not None, (
        "host lifecycle controller packet missing"
    )
    module = importlib.import_module("train.qualification_owner")
    assert callable(getattr(module, "_QualificationOwner", None))
    return module


def _request():
    native = importlib.import_module("train.native_qualification")
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


class _Cancelled(BaseException):
    pass


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class _Operations:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.failure = {}
        self.advance = {}
        self.app = object()
        self.resource = object()
        self.handle = object()
        self.codes = (0, 0)
        self.publish_app = True
        self.publish_resource = True

    def _call(self, name, custody, deadline):
        self.calls.append((name, custody, deadline))
        self.clock.now += self.advance.get(name, 0)
        if name in self.failure:
            raise self.failure[name]

    def prepare(self, request, *, custody, deadline):
        if self.publish_app:
            custody.retain_app(self.app)
        self._call("prepare", custody, deadline)

    def create(self, request, *, custody, deadline):
        if self.publish_resource:
            custody.retain_resource(self.resource)
        self._call("create", custody, deadline)
        return self.handle

    def wait(self, handle, *, custody, deadline):
        assert handle is self.handle
        self._call("wait", custody, deadline)
        return self.codes

    def export(self, handle, destination, *, custody, deadline, max_bytes, expires_at):
        assert handle is self.handle
        self.export_args = (destination, max_bytes, expires_at)
        self._call("export", custody, deadline)
        return destination

    def teardown(self, *, custody, deadline):
        self._call("teardown", custody, deadline)


def _setup(approval=None):
    module = _api()
    clock = _Clock()
    operations = _Operations(clock)
    request = _request()
    identity = object()
    owner = module._QualificationOwner(
        operations=operations, operation_identity=identity,
        approve=approval if approval is not None else lambda request: True,
        clock=clock, quote=_quote(request),
    )
    return owner, operations, request, clock, identity


def _names(operations):
    return [call[0] for call in operations.calls]


def test_missing_packet_is_assertion_red():
    assert _api()._QualificationOwner is not None


def test_rejection_has_zero_service_calls():
    for approval in (lambda request: False, lambda request: "approved"):
        owner, operations, request, _, _ = _setup(approval)
        with pytest.raises(PermissionError):
            owner.require_approved(request)
        assert operations.calls == []
    error = RuntimeError("approval unavailable")

    def approval(request):
        raise error

    owner, operations, request, _, _ = _setup(approval)
    with pytest.raises(RuntimeError) as caught:
        owner.require_approved(request)
    assert caught.value is error
    assert operations.calls == []


def test_approval_precedes_all_operations():
    owner, operations, request, _, _ = _setup()

    def approve(candidate):
        assert candidate is request
        assert operations.calls == []
        assert owner.state == "approving"
        return True

    owner._approve = approve
    owner.require_approved(request)
    assert operations.calls == []
    owner.run_once(request)
    assert _names(operations) == ["prepare", "create", "wait", "export", "teardown"]
    assert len({id(call[1]) for call in operations.calls}) == 1


def test_success_retains_one_service_handle():
    owner, operations, request, _, identity = _setup()
    owner.require_approved(request)
    result = owner.run_once(request)
    assert result.service_handle is operations.handle
    assert result.phase_returncodes == (0, 0)
    assert result.exported_root == request.output_dir
    custody = operations.calls[-1][1]
    assert custody.operation_identity is identity
    assert custody.app_identity is operations.app
    assert custody.resource_identity is operations.resource
    assert owner.state == "termination_unknown"
    assert owner.remote_termination == owner.charged_end == "UNKNOWN"
    assert _names(operations).count("create") == 1


def test_ambiguous_prehandle_failure_never_resubmits():
    owner, operations, request, _, identity = _setup()
    error = TimeoutError("create may have reached service")
    operations.failure["create"] = error
    operations.publish_resource = False
    owner.require_approved(request)
    with pytest.raises(TimeoutError) as caught:
        owner.run_once(request)
    assert caught.value is error
    assert _names(operations) == ["prepare", "create", "teardown"]
    assert operations.calls[-1][1].operation_identity is identity
    assert operations.calls[-1][1].resource_identity is None
    assert operations.calls[-1][1].creation_ambiguous is True
    with pytest.raises(RuntimeError):
        owner.run_once(request)
    assert _names(operations).count("create") == 1


def test_failure_and_cancellation_always_teardown():
    for operation in ("prepare", "create", "wait", "export"):
        for exception in (RuntimeError(operation), _Cancelled(operation)):
            owner, operations, request, _, _ = _setup()
            operations.failure[operation] = exception
            if operation == "prepare":
                operations.publish_app = False
            owner.require_approved(request)
            with pytest.raises(type(exception)) as caught:
                owner.run_once(request)
            assert caught.value is exception
            assert _names(operations)[-1] == "teardown"
            assert _names(operations).count("teardown") == 1
            assert owner.state == "failed"


def test_phase_failure_has_zero_exports():
    for codes in ((1, 0), (0, 1), (False, 0)):
        owner, operations, request, _, _ = _setup()
        operations.codes = codes
        owner.require_approved(request)
        with pytest.raises(ValueError):
            owner.run_once(request)
        assert _names(operations) == ["prepare", "create", "wait", "teardown"]


def test_deadline_blocks_next_operation():
    for boundary in ("approval", "prepare", "create", "wait", "export"):
        owner, operations, request, clock, _ = _setup()
        owner.require_approved(request)
        if boundary == "approval":
            clock.now += 1800
        else:
            operations.advance[boundary] = 1800
        with pytest.raises(TimeoutError):
            owner.run_once(request)
        names = _names(operations)
        if boundary == "approval":
            assert names == []
        else:
            expected = ["prepare", "create", "wait", "export"]
            assert names == expected[:expected.index(boundary) + 1] + ["teardown"]
            assert operations.calls[-1][2] == 1900.0


def test_primary_exception_survives_cleanup_failure():
    for error in (ValueError("primary"), _Cancelled("primary")):
        owner, operations, request, _, _ = _setup()
        cleanup = RuntimeError("cleanup")
        operations.failure.update(wait=error, teardown=cleanup)
        owner.require_approved(request)
        with pytest.raises(type(error)) as caught:
            owner.run_once(request)
        assert caught.value is error
        assert owner.cleanup_error is cleanup
        assert owner.state == "cleanup_failed"


def test_cleanup_failure_without_primary_propagates():
    owner, operations, request, _, _ = _setup()
    cleanup = _Cancelled("cleanup")
    operations.failure["teardown"] = cleanup
    owner.require_approved(request)
    with pytest.raises(_Cancelled) as caught:
        owner.run_once(request)
    assert caught.value is cleanup
    assert owner.cleanup_error is cleanup


def test_unapproved_or_different_request_is_refused():
    owner, operations, request, _, _ = _setup()
    with pytest.raises(RuntimeError):
        owner.run_once(request)
    owner.require_approved(request)
    with pytest.raises(RuntimeError):
        owner.run_once(replace(request))
    assert operations.calls == []
    owner.run_once(request)


def test_one_shot_and_reentrant_approval():
    owner, operations, request, _, _ = _setup()

    def approve(candidate):
        with pytest.raises(RuntimeError):
            owner.require_approved(candidate)
        with pytest.raises(RuntimeError):
            owner.run_once(candidate)
        return True

    owner._approve = approve
    owner.require_approved(request)
    with pytest.raises(RuntimeError):
        owner.require_approved(request)
    owner.run_once(request)
    with pytest.raises(RuntimeError):
        owner.run_once(request)
    assert _names(operations).count("create") == 1


def test_bounds_fail_before_approval():
    for change in (
        {"lifetime_seconds": 1801}, {"lifetime_seconds": True},
        {"artifact_bytes": 0}, {"retention_seconds": 0},
        {"remaining_worst_case_usd": Decimal("25.01")},
    ):
        approvals = []
        owner, operations, request, _, _ = _setup(lambda value: approvals.append(value))
        request = replace(request, bounds=replace(request.bounds, **change))
        with pytest.raises(ValueError):
            owner.require_approved(request)
        assert approvals == []
        assert operations.calls == []


def test_export_and_retention_share_deadline():
    for elapsed, expected_expiry in ((20, 180.0), (1790, 1900.0)):
        owner, operations, request, _, _ = _setup()
        operations.advance["wait"] = elapsed
        owner.require_approved(request)
        owner.run_once(request)
        assert operations.export_args == (request.output_dir, 1024, expected_expiry)
        assert {call[2] for call in operations.calls} == {1900.0}


def test_missing_or_replaced_identity_fails_closed():
    for missing in ("app", "resource"):
        owner, operations, request, _, _ = _setup()
        setattr(operations, f"publish_{missing}", False)
        owner.require_approved(request)
        with pytest.raises(ValueError):
            owner.run_once(request)
        assert _names(operations)[-1] == "teardown"
        assert "wait" not in _names(operations)
    owner, operations, request, _, _ = _setup()
    owner.require_approved(request)
    owner.run_once(request)
    custody = operations.calls[0][1]
    with pytest.raises(RuntimeError):
        custody.retain_app(object())
    with pytest.raises(RuntimeError):
        custody.retain_resource(object())
    with pytest.raises(AttributeError):
        custody.operation_identity = object()


def test_host_capabilities_are_not_serialized():
    secret = "synthetic-host-capability"

    class Approval:
        def __repr__(self):
            return secret

        def __call__(self, request):
            return True

    owner, operations, request, _, _ = _setup(Approval())
    operations.credential = secret
    assert secret not in repr(owner)
    owner.require_approved(request)
    owner.run_once(request)
    custody = operations.calls[0][1]
    for capability in (owner, custody):
        with pytest.raises(TypeError):
            pickle.dumps(capability)
        with pytest.raises(TypeError):
            json.dumps(capability)
    assert secret not in repr(custody)
    assert all(call[1] is custody for call in operations.calls)
    assert all(call[1] is not owner for call in operations.calls)
