"""Memory-only admission checks. No provider contract or native-runtime proof."""

from dataclasses import replace
from decimal import Decimal
import pickle

import pytest

from train import qualification_launch_admission as admission
from train import qualification_owner as owner_api
from train import qualification_watchdog as watchdog
from train.qualification_costs import evaluate_costs
from train.test_qualification_owner import _Clock, _Operations, _quote, _request


def _fixture(*, quote=None, identity=None, approval=None):
    clock = _Clock()
    operations = _Operations(clock)
    request = _request()
    owner = owner_api._QualificationOwner(
        operations=operations, operation_identity=object() if identity is None else identity,
        approve=(lambda candidate: True) if approval is None else approval,
        clock=clock, quote=_quote(request) if quote is None else quote,
    )
    return owner, operations, request, clock


def _review_stub(monkeypatch):
    """Mechanics only: this is not an independently reviewed provider contract."""
    monkeypatch.setattr(admission, "_require_provider_review", lambda request, quote: None)


def _assert_refusal_has_zero_operations(owner, operations, request):
    try:
        owner.require_approved(request)
        owner.run_once(request)
    except PermissionError:
        pass
    assert operations.calls == [], "admission guard lost: actual owner reached service operations"
    assert owner.state == "rejected"


def test_missing_category_refuses_before_operations():
    for category in _quote(_request()).ledger().charges:
        for unknown in (False, True):
            owner, operations, request, _ = _fixture()
            rows = tuple(
                (name, None if unknown else charge) if name == category else (name, charge)
                for name, charge in owner._quote.charges if unknown or name != category
            )
            owner._quote = replace(owner._quote, charges=rows)
            with pytest.raises(ValueError):
                owner.require_approved(request)
            assert operations.calls == []


def test_unknown_result_category_is_not_zero():
    quote = _quote(_request())
    result = evaluate_costs(quote.bounds, quote.ledger())
    with pytest.raises(ValueError, match="unknown charge category"):
        result.charge_usd("not-a-category")


def test_credit_gross_quote():
    request = _request()
    request = replace(request, bounds=replace(
        request.bounds, prior_usage_usd=Decimal("5"), remaining_worst_case_usd=Decimal("20"),
    ))
    quote = _quote(request)
    ledger = replace(quote.ledger(), prior_cash_usd=Decimal("2"), prior_credits_usd=Decimal("3"))
    frozen = admission.freeze_cost_quote(request.bounds, ledger, issued_at=100, expires_at=200)
    assert admission.validate_quote(request, frozen, now=100).prior_gross_usd == Decimal("5")
    with pytest.raises(ValueError):
        admission.freeze_cost_quote(
            request.bounds, replace(ledger, prior_credits_usd=Decimal("0")),
            issued_at=100, expires_at=200,
        )


def test_exact_25_quote():
    request = _request()
    request = replace(request, bounds=replace(
        request.bounds, prior_usage_usd=Decimal("5"), remaining_worst_case_usd=Decimal("20"),
    ))
    ledger = _quote(request).ledger()
    charges = dict(ledger.charges)
    charges["build"] = replace(charges["build"], quantity=Decimal("1"), rate_usd=Decimal("20"))
    ledger = replace(ledger, charges=charges)
    quote = admission.freeze_cost_quote(request.bounds, ledger, issued_at=100, expires_at=200)
    assert admission.validate_quote(request, quote, now=100).total_gross_usd == Decimal("25")
    charges["ancillary"] = replace(
        charges["ancillary"], quantity=Decimal("1"), rate_usd=Decimal("1e-30"),
    )
    with pytest.raises(ValueError):
        admission.freeze_cost_quote(request.bounds, ledger, issued_at=100, expires_at=200)


def test_stale_quote_refuses_before_operations():
    for now in (99.0, 101.0, 102.0):
        request = _request()
        quote = _quote(request, issued_at=100, expires_at=101)
        owner, operations, request, clock = _fixture(quote=quote)
        clock.now = now
        _assert_refusal_has_zero_operations(owner, operations, request)


def test_quote_mapping_is_frozen():
    request = _request()
    ledger = _quote(request).ledger()
    frozen = admission.freeze_cost_quote(request.bounds, ledger, issued_at=100, expires_at=200)
    ledger.charges.clear()
    assert len(frozen.charges) == 12
    assert admission.validate_quote(request, frozen, now=100).total_gross_usd == 0


def test_no_review_refuses_literal_bounds():
    owner, operations, request, _ = _fixture()
    with pytest.raises(PermissionError, match="provider admission CLOSED") as caught:
        owner.require_approved(request)
    assert all(proof in str(caught.value) for proof in admission.MISSING_PROVIDER_PROOFS)
    assert operations.calls == []
    assert owner.state == "rejected"


def test_missing_quote_true_bool_and_json_do_not_grant_authority():
    for quote in (None, True, {}, {"approved": True}):
        owner, operations, request, _ = _fixture()
        owner._quote = quote
        _assert_refusal_has_zero_operations(owner, operations, request)


def test_expiry_rechecked_after_approval(monkeypatch):
    _review_stub(monkeypatch)
    owner, operations, request, clock = _fixture(quote=_quote(_request(), expires_at=101))

    def approve(candidate):
        clock.now = 101
        return True

    owner._approve = approve
    _assert_refusal_has_zero_operations(owner, operations, request)


def test_expiry_rechecked_before_allocation(monkeypatch):
    _review_stub(monkeypatch)
    owner, operations, request, clock = _fixture(quote=_quote(_request(), expires_at=101))
    owner.require_approved(request)
    clock.now = 101
    with pytest.raises(PermissionError):
        owner.run_once(request)
    assert operations.calls == []
    assert owner.state == "failed"
    with pytest.raises(RuntimeError):
        owner.run_once(request)


def test_expiry_rechecked_before_create(monkeypatch):
    _review_stub(monkeypatch)
    owner, operations, request, _ = _fixture(quote=_quote(_request(), expires_at=101))
    operations.advance["prepare"] = 1
    owner.require_approved(request)
    with pytest.raises(PermissionError):
        owner.run_once(request)
    assert [row[0] for row in operations.calls] == ["prepare", "teardown"]


def test_duplicate_claim(monkeypatch):
    _review_stub(monkeypatch)
    identity = object()
    first, operations, request, _ = _fixture(identity=identity)
    second, other_operations, other_request, _ = _fixture(identity=identity)
    first.require_approved(request)
    with pytest.raises(PermissionError, match="already claimed"):
        second.require_approved(other_request)
    first.run_once(request)
    assert [row[0] for row in operations.calls].count("create") == 1
    assert other_operations.calls == []
    with pytest.raises(PermissionError):
        first._claim.consume(request, now=100)
    with pytest.raises(TypeError):
        pickle.dumps(first._claim)


def test_replaced_quote_cannot_reuse_reviewed_claim(monkeypatch):
    _review_stub(monkeypatch)
    owner, operations, request, _ = _fixture()
    owner.require_approved(request)
    owner._quote = replace(owner._quote)
    with pytest.raises(PermissionError, match="exact retained reviewed quote"):
        owner.run_once(request)
    assert operations.calls == []


def test_ambiguous_create_consumes_claim(monkeypatch):
    _review_stub(monkeypatch)
    identity = object()
    owner, operations, request, _ = _fixture(identity=identity)
    primary = TimeoutError("ambiguous create")
    cleanup = RuntimeError("stop failed")
    operations.failure = {"create": primary, "teardown": cleanup}
    operations.publish_resource = False
    owner.require_approved(request)
    with pytest.raises(TimeoutError) as caught:
        owner.run_once(request)
    assert caught.value is primary
    assert owner.cleanup_error is cleanup
    assert owner._custody.creation_ambiguous is True
    assert [row[0] for row in operations.calls] == ["prepare", "create", "teardown"]
    replacement, replacement_operations, replacement_request, _ = _fixture(identity=identity)
    with pytest.raises(PermissionError):
        replacement.require_approved(replacement_request)
    assert replacement_operations.calls == []


def test_stop_ack_not_charged_end(monkeypatch):
    _review_stub(monkeypatch)
    owner, operations, request, _ = _fixture()
    owner.require_approved(request)
    owner.run_once(request)
    assert owner.state == "termination_unknown"
    assert owner.remote_termination == owner.charged_end == "UNKNOWN"
    command = watchdog._command_result()
    command.update(attempted=True, returncode=0, leader_reaped=True)
    result = watchdog._result("finish", command)
    assert result["local_ok"] is True
    assert result["remote"] == result["billing"] == "UNKNOWN"


def test_exactly_two_success_statuses_required(monkeypatch):
    _review_stub(monkeypatch)
    for codes in ((0,), (0, 0, 0), (False, 0), (0, 1)):
        owner, operations, request, _ = _fixture()
        operations.codes = codes
        owner.require_approved(request)
        with pytest.raises(ValueError):
            owner.run_once(request)
        assert [row[0] for row in operations.calls] == ["prepare", "create", "wait", "teardown"]
    # Two zero statuses still do not prove fresh processes; provider/service
    # binding remains CLOSED without independent review.


def test_provisioning_teardown_tails():
    request = _request()
    request = replace(request, bounds=replace(request.bounds, lifetime_seconds=10))
    quote = _quote(request, provisioning=2, teardown=3)
    assert admission.validate_quote(request, quote, now=100).total_gross_usd == 0
    for resource in ("cpu", "gpu", "ram", "storage"):
        ledger = quote.ledger()
        ledger.charges[resource] = replace(ledger.charges[resource], seconds=Decimal("14"))
        with pytest.raises(ValueError):
            admission.freeze_cost_quote(request.bounds, ledger, issued_at=100, expires_at=200)


def test_aggregate_tail_limit():
    request = _request()
    request = replace(request, bounds=replace(request.bounds, lifetime_seconds=1795))
    quote = _quote(request, provisioning=2, teardown=3)
    assert evaluate_costs(request.bounds, quote.ledger()).total_gross_usd == 0
    with pytest.raises(ValueError, match="1800"):
        _quote(replace(request, bounds=replace(request.bounds, lifetime_seconds=1796)),
               provisioning=2, teardown=3)


def test_deadlines_reserve_teardown(monkeypatch):
    _review_stub(monkeypatch)
    request = _request()
    request = replace(request, bounds=replace(request.bounds, lifetime_seconds=10))
    quote = _quote(request, provisioning=2, teardown=3)
    clock = _Clock()
    operations = _Operations(clock)
    owner = owner_api._QualificationOwner(
        operations=operations, operation_identity=object(), approve=lambda candidate: True,
        clock=clock, quote=quote,
    )
    owner.require_approved(request)
    operations.advance["wait"] = 12
    with pytest.raises(TimeoutError):
        owner.run_once(request)
    assert [(name, deadline) for name, _, deadline in operations.calls] == [
        ("prepare", 112), ("create", 112), ("wait", 112), ("teardown", 115),
    ]


def test_guard_loss_missing_review_witness(monkeypatch):
    owner, operations, request, _ = _fixture()
    _assert_refusal_has_zero_operations(owner, operations, request)
    with monkeypatch.context() as patch:
        _review_stub(patch)
        owner, operations, request, _ = _fixture()
        with pytest.raises(AssertionError, match="guard lost"):
            _assert_refusal_has_zero_operations(owner, operations, request)
        assert [row[0] for row in operations.calls].count("create") == 1
    owner, operations, request, _ = _fixture()
    _assert_refusal_has_zero_operations(owner, operations, request)


def test_provider_review_expiry_does_not_issue_claim(monkeypatch):
    owner, operations, request, clock = _fixture(quote=_quote(_request(), expires_at=101))
    identity = owner._custody.operation_identity

    def review(candidate, quote):
        clock.now = 101

    monkeypatch.setattr(admission, "_require_provider_review", review)
    try:
        owner.require_approved(request)
    except PermissionError as error:
        assert "expired" in str(error)
    assert owner._claim is None, "expired provider review issued a claim"
    assert owner.state == "rejected"
    assert not any(item is identity for item in admission._CLAIMED_OPERATIONS)
    assert operations.calls == []


def test_guard_loss_expiry_witness(monkeypatch):
    _review_stub(monkeypatch)

    def stale():
        owner, operations, request, clock = _fixture(quote=_quote(_request(), expires_at=101))
        clock.now = 101
        return owner, operations, request

    _assert_refusal_has_zero_operations(*stale())
    with monkeypatch.context() as patch:
        patch.setattr(admission, "_require_fresh_quote", lambda quote, now: None)
        owner, operations, request = stale()
        with pytest.raises(AssertionError, match="guard lost"):
            _assert_refusal_has_zero_operations(owner, operations, request)
        assert [row[0] for row in operations.calls].count("create") == 1
    _assert_refusal_has_zero_operations(*stale())
