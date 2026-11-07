"""Private host orchestration, not provider admission or hard containment."""

from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path
import time
from typing import TYPE_CHECKING, Protocol

from train import qualification_launch_admission as admission

if TYPE_CHECKING:
    from train.native_qualification import OwnedJobResult, QualificationRequest


class _Custody:
    __slots__ = ("_operation_identity", "_app_identity", "_resource_identity",
                 "_creation_ambiguous")

    def __init__(self, operation_identity: object) -> None:
        if operation_identity is None:
            raise ValueError("externally issued operation identity required")
        self._operation_identity = operation_identity
        self._app_identity: object | None = None
        self._resource_identity: object | None = None
        self._creation_ambiguous = False

    @property
    def operation_identity(self) -> object:
        return self._operation_identity

    @property
    def app_identity(self) -> object | None:
        return self._app_identity

    @property
    def resource_identity(self) -> object | None:
        return self._resource_identity

    @property
    def creation_ambiguous(self) -> bool:
        return self._creation_ambiguous

    def retain_app(self, identity: object) -> None:
        if identity is None:
            raise ValueError("service-issued App identity required")
        if self._app_identity is not None and self._app_identity is not identity:
            raise RuntimeError("App replacement refused")
        self._app_identity = identity

    def retain_resource(self, identity: object) -> None:
        if identity is None:
            raise ValueError("service-issued resource identity required")
        if self._resource_identity is not None and self._resource_identity is not identity:
            raise RuntimeError("resource replacement refused")
        self._resource_identity = identity

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("host custody cannot be serialized")


class _ServiceOperations(Protocol):
    """Host-only trusted operations; provider enforcement remains external."""

    def prepare(
        self, request: QualificationRequest, *, custody: _Custody, deadline: float,
    ) -> None: ...

    def create(
        self, request: QualificationRequest, *, custody: _Custody, deadline: float,
    ) -> object: ...

    def wait(
        self, handle: object, *, custody: _Custody, deadline: float,
    ) -> tuple[int, int]: ...

    def export(
        self, handle: object, destination: Path, *, custody: _Custody,
        deadline: float, max_bytes: int, expires_at: float,
    ) -> Path: ...

    def teardown(self, *, custody: _Custody, deadline: float) -> None: ...


class _QualificationOwner:
    """One-shot structural QualificationController; service trust is external."""

    __slots__ = (
        "_operations", "_custody", "_approve", "_clock", "_state", "_request",
        "_deadline", "_charged_deadline", "_last_time", "_cleanup_error", "_quote",
        "_claim",
    )

    def __init__(
        self, *, operations: _ServiceOperations, operation_identity: object,
        approve: Callable[[QualificationRequest], bool],
        clock: Callable[[], float] = time.monotonic,
        quote: admission.FrozenCostQuote | None = None,
    ) -> None:
        if operations is None or not callable(approve) or not callable(clock):
            raise ValueError("trusted service operations and host approval/clock required")
        self._operations = operations
        self._custody = _Custody(operation_identity)
        self._approve = approve
        self._clock = clock
        self._state = "new"
        self._request: QualificationRequest | None = None
        self._deadline = 0.0
        self._charged_deadline = 0.0
        self._quote = quote
        self._claim: admission._LocalClaim | None = None
        self._last_time: float | None = None
        self._cleanup_error: BaseException | None = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def cleanup_error(self) -> BaseException | None:
        return self._cleanup_error

    @property
    def remote_termination(self) -> str:
        return "UNKNOWN"

    @property
    def charged_end(self) -> str:
        return "UNKNOWN"

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("host controller cannot be serialized")

    def _now(self) -> float:
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("finite monotonic clock required")
        if self._last_time is not None and now < self._last_time:
            raise ValueError("monotonic clock moved backwards")
        self._last_time = now
        return now

    def _check_deadline(self) -> float:
        now = self._now()
        if now >= self._deadline:
            raise TimeoutError("shared qualification lifetime exhausted")
        return now

    def require_approved(self, request: QualificationRequest) -> None:
        from train.native_qualification import _validate_bounds

        if self._state != "new":
            raise RuntimeError("approval is one-shot")
        self._state = "approving"
        try:
            _validate_bounds(request.bounds)
            started = self._now()
            admission.validate_quote(request, self._quote, now=started)
            if self._approve(request) is not True:
                raise PermissionError("host operation approval denied")
            # A callback, literal numeric bounds, JSON or arithmetic cannot issue
            # provider authority. The independent review leaf is currently CLOSED.
            self._claim = admission._claim_reviewed_operation(
                self._custody.operation_identity, request, self._quote, clock=self._now,
            )
            self._deadline = self._claim.work_deadline
            self._charged_deadline = self._claim.charged_deadline
            self._check_deadline()
            self._request = request
            self._state = "approved"
        except BaseException:
            self._state = "rejected"
            raise

    def run_once(self, request: QualificationRequest) -> OwnedJobResult:
        from train.native_qualification import OwnedJobResult

        if self._state != "approved" or request is not self._request:
            raise RuntimeError("exact host-approved request required, once")
        self._state = "starting"
        try:
            now = self._check_deadline()
            if self._claim is None:
                raise PermissionError("retained reviewed one-use claim required")
            if self._quote is not self._claim.quote:
                raise PermissionError("exact retained reviewed quote required")
            # Fail before entering allocation/cleanup region: refusal must not
            # prepare, create, or stop any resource.
            self._claim.consume(request, now=now)
        except BaseException:
            self._state = "failed"
            raise

        primary_failed = False
        try:
            self._state = "preparing"
            self._operations.prepare(
                request, custody=self._custody, deadline=self._deadline,
            )
            self._check_deadline()
            if self._custody.app_identity is None:
                raise ValueError("preparation did not retain service-issued App identity")

            admission.validate_quote(request, self._claim.quote, now=self._check_deadline())
            self._state = "creating"
            # Set before submission. Exceptions, lost responses, missing handles
            # and overruns keep ownership ambiguous, even if an identity arrived.
            self._custody._creation_ambiguous = True
            handle = self._operations.create(
                request, custody=self._custody, deadline=self._deadline,
            )
            self._check_deadline()
            if handle is None or self._custody.resource_identity is None:
                raise ValueError("creation did not retain service-issued resource identity/handle")
            self._custody._creation_ambiguous = False

            self._state = "running"
            codes = self._operations.wait(
                handle, custody=self._custody, deadline=self._deadline,
            )
            now = self._check_deadline()
            if (type(codes) is not tuple or len(codes) != 2
                    or any(type(code) is not int or code != 0 for code in codes)):
                raise ValueError("both native worker phases must succeed before export")

            self._state = "exporting"
            exported = self._operations.export(
                handle, request.output_dir, custody=self._custody,
                deadline=self._deadline, max_bytes=request.bounds.artifact_bytes,
                expires_at=min(self._deadline, now + request.bounds.retention_seconds),
            )
            self._check_deadline()
            if exported != request.output_dir:
                raise ValueError("export destination differs from approved request")
            return OwnedJobResult(handle, exported, codes)
        except BaseException:
            primary_failed = True
            raise
        finally:
            self._state = "tearing_down"
            try:
                # Do not deadline-gate cleanup: partial allocation still needs reconciliation.
                self._operations.teardown(custody=self._custody, deadline=self._charged_deadline)
                if not primary_failed and self._now() >= self._charged_deadline:
                    raise TimeoutError("declared charged envelope exhausted; billing UNKNOWN")
            except BaseException as error:
                self._cleanup_error = error
                self._state = "cleanup_failed"
                if not primary_failed:
                    raise
            else:
                # A returned stop request (including AppStop ACK) is not remote
                # termination or charged-end proof. Do not label it "closed".
                self._state = "failed" if primary_failed else "termination_unknown"
