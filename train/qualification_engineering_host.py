"""Sealed host-local engineering authority and durable attempt reservation.

Authority is never worker JSON, a bool, a budget plan label or a callback:
it is issued only through `issue_engineering_authorization`, a trusted-host
API that binds the exact original request digest, the operator-policy
FilePin, frozen candidate image identity, the approved upload manifest, the
fixed offline setup argv, complete explicit budget inputs and a fresh
clock/expiry, recomputing the planning estimate itself. A budget plan alone
is NOT authority and no plan label is ever accepted. Nothing here implies a
provider cap, a guaranteed total cost or billing proof; the plan remains an
estimate and every remote/charged end stays UNKNOWN.

The durable reservation is claimed only from a sealed authorization at a
deterministic location derived from the exact owner-approved policy FilePin
(never a caller-chosen path, filename or operation nonce), exclusively,
before any billable API. The claim validates the ACTUAL bounded policy
bytes against the approved pin and traverses the parent chain with nofollow
directory FDs (owner-controlled ancestry, private claim directory), so a
missing, drifted, aliased or unsafe policy location, or a symlinked or
unsafe parent, refuses without any record. An existing or ambiguous record
refuses with no reads, no recovery, no deletion and no signals; afterwards
the record is append-only relative to the retained directory FD, never
reopened by pathname, and replacement/alias refuses with zero writes. The
claim retains the sealed approval identity so a host can refuse a
reservation claimed under a different authorization. The original strict
owner (train.qualification_owner) is untouched. stdlib-only, no import-time
work, no SDK import, no side effects.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import weakref

from train.engineering_budget import (
    AncillaryEstimates,
    BudgetTerms,
    EngineeringBudgetPlan,
    GpuWorkload,
    PreparationAccount,
    ResourceRates,
    plan_engineering_budget,
)
from train.qualification_image_plan import candidate_recipe, recipe_sha256


_SHA256 = re.compile(r"[0-9a-f]{64}")
APP_ID = re.compile(r"ap-[A-Za-z0-9]{22}")
RESOURCE_ID = re.compile(r"sb-[A-Za-z0-9]+")
_GPU_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_GPU_COUNT = re.compile(r"[1-9][0-9]{0,3}")
_CLAIM_PREFIX = ".qualification-attempt-"
_MAX_POLICY_BYTES = 2**26
_POLICY_READ_CHUNK_BYTES = 65536
_UPLOAD_KEY = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
UPLOAD_ROOTS = ("source", "model", "data", "wheels")
MAX_GPU_WINDOW_SECONDS = 1800
MAX_PREPARATION_SECONDS = 1800
_MAX_AUTHORITY_SECONDS = 86400
_MAX_UPLOAD_ITEMS = 4096
_MAX_UPLOAD_BYTES = 2**36
_MAX_ARGV_ITEMS = 64
_MAX_ARGV_ITEM_CHARS = 4096

# Module-private issuance tokens: construction outside the explicit
# trusted-host APIs below is structurally refused.
_ISSUE_TOKEN = object()
_CLAIM_TOKEN = object()
_CUSTODY_TOKEN = object()


def _int(value: object, name: str) -> int:
    if type(value) is not int or value.bit_length() > 63:
        raise ValueError(f"{name} requires a bounded integer, UNKNOWN blocks")
    return value


def _file_pin(value: object, name: str, native) -> None:
    # Exact-type check: bools, dicts, JSON strings and subclasses grant nothing.
    if type(value) is not native.FilePin:
        raise ValueError(
            f"{name} requires the exact original native FilePin; "
            "worker JSON/bools/dicts cannot carry approval"
        )
    if (not isinstance(value.path, Path) or not value.path.is_absolute()
            or ".." in value.path.parts):
        raise ValueError(f"{name}.path requires an absolute resolved path")
    if type(value.size) is not int or value.size <= 0 or value.size.bit_length() > 63:
        raise ValueError(f"{name}.size requires a positive bounded integer")
    if type(value.sha256) is not str or _SHA256.fullmatch(value.sha256) is None:
        raise ValueError(f"{name}.sha256 requires lowercase 64-hex SHA256")


def _upload_entry(value: object) -> tuple[str, str, int, str]:
    if type(value) is not tuple or len(value) != 4:
        raise ValueError("upload entries require exact (root, key, size, sha256) tuples")
    root, key, size, sha256 = value
    if type(root) is not str or root not in UPLOAD_ROOTS:
        raise ValueError(f"upload root must be one of {UPLOAD_ROOTS}")
    if (type(key) is not str or len(key) > 1024
            or _UPLOAD_KEY.fullmatch(key) is None
            or any(part in ("", ".", "..") for part in key.split("/"))):
        raise ValueError("upload key requires a bounded relative safe path")
    if type(size) is not int or size < 0 or size > _MAX_UPLOAD_BYTES:
        raise ValueError("upload size requires a bounded nonnegative integer")
    if type(sha256) is not str or _SHA256.fullmatch(sha256) is None:
        raise ValueError("upload sha256 requires lowercase 64-hex SHA256")
    return (root, key, size, sha256)


def _setup_argv(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= _MAX_ARGV_ITEMS:
        raise ValueError(f"setup argv requires 1..{_MAX_ARGV_ITEMS} exact string tuple")
    for item in value:
        if (type(item) is not str or not item
                or len(item) > _MAX_ARGV_ITEM_CHARS or "\0" in item):
            raise ValueError("setup argv items require bounded nonempty NUL-free strings")
    return value


def _gpu_label(value: object, gpu_count: int) -> str:
    """Parse to exactly one charged GPU; refuse fallback/list/count escapes.

    A suffix count (``name:count``) must equal the charged
    ``workload.gpu_count`` (the budget independently refuses any count other
    than 1). Fallback syntax (``any``, any casing), list/multi-label syntax
    (commas, semicolons, whitespace) and malformed names/counts refuse the
    whole issuance, so a label like ``A100:8`` can never allocate beyond the
    single charged GPU.
    """
    if type(value) is not str or not value:
        raise ValueError("explicit bounded gpu label required")
    if any(character.isspace() or character in ",;" for character in value):
        raise ValueError(
            "gpu fallback/list syntax refused; exactly one explicit GPU label required"
        )
    name, separator, count_text = value.partition(":")
    if _GPU_NAME.fullmatch(name) is None or name.lower() == "any":
        raise ValueError("malformed gpu label or refused fallback gpu name")
    if separator:
        if _GPU_COUNT.fullmatch(count_text) is None:
            raise ValueError("gpu count suffix requires canonical decimal digits")
        count = int(count_text)
    else:
        count = 1
    if count != gpu_count:
        raise ValueError(
            "gpu label count must equal the charged workload gpu_count; "
            "exactly one GPU is issuable"
        )
    return value


class EngineeringAuthorization:
    """Host-local sealed one-use authorization; never deserialized approval.

    Constructible only through `issue_engineering_authorization`. Instances
    bind the original request object and digest, the operator-policy FilePin,
    the recomputed budget plan, image/gpu/setup/upload identity and a fresh
    wall-clock expiry window. `require_valid` gates every later use.
    """

    __slots__ = (
        "_request", "_request_binding", "_policy_pin", "_plan", "_workload",
        "_setup_argv", "_uploads", "_preparation_seconds", "_issued_at_seconds",
        "_expires_at_seconds", "_image_base_reference", "_image_recipe_sha256",
        "_gpu_label", "_bound",
    )

    def __init__(
        self, issuer: object, *, request, request_binding: str, policy_pin,
        plan: EngineeringBudgetPlan, workload: GpuWorkload,
        setup_argv: tuple[str, ...],
        uploads: tuple[tuple[str, str, int, str], ...],
        preparation_seconds: int, issued_at_seconds: int, expires_at_seconds: int,
        image_base_reference: str, image_recipe_sha256: str, gpu_label: str,
    ) -> None:
        if issuer is not _ISSUE_TOKEN:
            raise PermissionError(
                "authorization issues only through the explicit trusted-host API; "
                "a budget plan, JSON, bools or callbacks cannot manufacture it"
            )
        self._request = request
        self._request_binding = request_binding
        self._policy_pin = policy_pin
        self._plan = plan
        self._workload = workload
        self._setup_argv = setup_argv
        self._uploads = uploads
        self._preparation_seconds = preparation_seconds
        self._issued_at_seconds = issued_at_seconds
        self._expires_at_seconds = expires_at_seconds
        self._image_base_reference = image_base_reference
        self._image_recipe_sha256 = image_recipe_sha256
        self._gpu_label = gpu_label
        self._bound = False

    @property
    def request(self):
        return self._request

    @property
    def request_binding(self) -> str:
        return self._request_binding

    @property
    def policy_pin(self):
        return self._policy_pin

    @property
    def plan(self) -> EngineeringBudgetPlan:
        return self._plan

    @property
    def workload(self) -> GpuWorkload:
        # The exact planning inputs the recomputed plan charged for,
        # never an arbitrary plan label.
        return self._workload

    @property
    def setup_argv(self) -> tuple[str, ...]:
        return self._setup_argv

    @property
    def uploads(self) -> tuple[tuple[str, str, int, str], ...]:
        return self._uploads

    @property
    def preparation_seconds(self) -> int:
        return self._preparation_seconds

    @property
    def issued_at_seconds(self) -> int:
        return self._issued_at_seconds

    @property
    def expires_at_seconds(self) -> int:
        return self._expires_at_seconds

    @property
    def image_base_reference(self) -> str:
        return self._image_base_reference

    @property
    def image_recipe_sha256(self) -> str:
        return self._image_recipe_sha256

    @property
    def gpu_label(self) -> str:
        return self._gpu_label

    @property
    def bound(self) -> bool:
        return self._bound

    def require_valid(self, *, now_seconds: int) -> None:
        _int(now_seconds, "now_seconds")
        if now_seconds < self._issued_at_seconds:
            raise PermissionError("authorization clock moved backwards; authority UNKNOWN")
        if now_seconds >= self._expires_at_seconds:
            raise PermissionError("authorization expired; authority refused")

    def _bind_once(self) -> None:
        if self._bound:
            raise PermissionError("authorization is one-use and already bound to a host")
        self._bound = True

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("sealed host-local authorization cannot be serialized")


def issue_engineering_authorization(
    *, request, policy_pin, terms: BudgetTerms, rates: ResourceRates,
    workload: GpuWorkload, preparation: PreparationAccount,
    ancillary: AncillaryEstimates, now_seconds: int, expires_at_seconds: int,
    preparation_seconds: int, image_base_reference: str,
    image_recipe_sha256: str, gpu_label: str,
    uploads: tuple[tuple[str, str, int, str], ...], setup_argv: tuple[str, ...],
) -> EngineeringAuthorization:
    """Trusted-host issuance API; not a remote/job-wire API.

    Binds the original request digest, the exact operator-policy FilePin,
    frozen candidate image identity, one exact charged GPU label (suffix
    counts other than the charged workload count, fallback and list syntax
    refuse), sealed upload manifest and
    fixed offline setup argv to a recomputed budget plan and a fresh
    clock/expiry. The plan is an estimate only: no provider cap, guaranteed
    total or billing proof is created here. Any invalid input refuses the
    whole issuance; nothing partial is returned.
    """
    from train import native_qualification as native

    if type(request) is not native.QualificationRequest:
        raise ValueError("exact original QualificationRequest object required")
    request_binding = native._request_binding(request)
    _file_pin(policy_pin, "policy_pin", native)
    # Recompute the plan from complete explicit inputs; a supplied plan label
    # is never accepted and a budget helper alone is not authority.
    plan = plan_engineering_budget(
        terms, rates, workload, preparation, ancillary, now_seconds,
    )
    _int(now_seconds, "now_seconds")
    _int(expires_at_seconds, "expires_at_seconds")
    if not 0 < expires_at_seconds - now_seconds <= _MAX_AUTHORITY_SECONDS:
        raise ValueError(
            f"fresh expiry required within (0,{_MAX_AUTHORITY_SECONDS}] seconds"
        )
    _int(preparation_seconds, "preparation_seconds")
    if not 0 < preparation_seconds <= MAX_PREPARATION_SECONDS:
        raise ValueError(
            f"preparation_seconds required within (0,{MAX_PREPARATION_SECONDS}]"
        )
    recipe = candidate_recipe()
    if (type(image_base_reference) is not str
            or image_base_reference != recipe.base_reference):
        raise ValueError("exact frozen candidate base reference required")
    if (type(image_recipe_sha256) is not str
            or image_recipe_sha256 != recipe_sha256(recipe)):
        raise ValueError("exact frozen candidate recipe SHA256 required")
    gpu_label = _gpu_label(gpu_label, workload.gpu_count)
    if type(uploads) is not tuple or len(uploads) > _MAX_UPLOAD_ITEMS:
        raise ValueError(f"bounded upload manifest tuple of <= {_MAX_UPLOAD_ITEMS} entries required")
    entries = tuple(_upload_entry(item) for item in uploads)
    seen: set[tuple[str, str]] = set()
    for root, key, _size, _sha in entries:
        if (root, key) in seen:
            raise ValueError("duplicate upload (root, key) refused")
        seen.add((root, key))
    argv = _setup_argv(setup_argv)
    return EngineeringAuthorization(
        _ISSUE_TOKEN,
        request=request, request_binding=request_binding, policy_pin=policy_pin,
        plan=plan, workload=workload, setup_argv=argv, uploads=entries,
        preparation_seconds=preparation_seconds, issued_at_seconds=now_seconds,
        expires_at_seconds=expires_at_seconds,
        image_base_reference=image_base_reference,
        image_recipe_sha256=image_recipe_sha256, gpu_label=gpu_label,
    )


_ISSUED_CUSTODY = weakref.WeakValueDictionary()
_RETAINED_CUSTODY = {}
_CUSTODY_ERRORS_ATTRIBUTE = "_qualification_reservation_custody"


class _ReservationFD:
    """One acquisition generation, never authority to retry a numeric FD."""

    __slots__ = (
        "custody", "generation", "role", "parent", "required_anchor",
        "fd", "opened_identity", "state", "close_error",
    )

    def __init__(self, custody, role, parent, required_anchor):
        self.custody = custody
        self.generation = object()
        self.role = role
        self.parent = parent
        self.required_anchor = required_anchor
        self.fd = None
        self.opened_identity = None
        self.state = "RESERVED"
        self.close_error = None

    def close(self, primary=None):
        if self.state != "OPEN":
            return
        if self.custody._required(self):
            return
        # The number is retired BEFORE the syscall, even if it physically
        # closes and then raises. Neither retry nor fstat can disambiguate it.
        self.state = "CLOSE_ATTEMPTED"
        try:
            os.close(self.fd)
        except BaseException as error:
            self.state = "UNKNOWN"
            self.close_error = error
            if primary is not None:
                self.custody.secondary.append(error)
            else:
                raise
        else:
            self.state = "CLOSED"
            reservation = self.custody.reservation
            if (reservation is not None
                    and reservation._anchor_record is self):
                reservation._dir_fd = -1
        finally:
            self.custody._release_retention()

    def __reduce_ex__(self, protocol):
        raise TypeError("reservation FD custody cannot be copied or serialized")


class _ReservationCustody:
    """Helper-issued evidence of actual acquisitions and observed releases."""

    __slots__ = (
        "_authorization", "_reservation", "records", "primary", "secondary",
        "_failures", "__weakref__",
    )

    def __init__(self, issuer, authorization):
        if issuer is not _CUSTODY_TOKEN:
            raise PermissionError("reservation custody is issued only by the helper")
        self._authorization = authorization
        self._reservation = None
        self.records = []
        self.primary = None
        self.secondary = []
        self._failures = []
        _ISSUED_CUSTODY[id(self)] = self
        _RETAINED_CUSTODY[id(self)] = self

    @property
    def authorization(self):
        return self._authorization

    @property
    def reservation(self):
        return self._reservation

    def reserve(self, role, *, parent=None, required_anchor=None):
        record = _ReservationFD(self, role, parent, required_anchor)
        self.records.append(record)
        _RETAINED_CUSTODY[id(self)] = self
        return record

    @property
    def has_unknown(self):
        return any(record.state in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")
                   for record in self.records)

    def _required(self, anchor):
        return any(record.required_anchor is anchor
                   and record.state not in ("CLOSED", "NO_FD")
                   for record in self.records)

    def _release_retention(self):
        if all(record.state in ("CLOSED", "NO_FD") for record in self.records):
            _RETAINED_CUSTODY.pop(id(self), None)

    def _publish(self, error):
        if self.primary is None:
            self.primary = error
        if not any(previous is error for previous in self._failures):
            self._failures.append(error)
        # Bypass an exception subclass's attribute hooks, and preserve any
        # earlier receipt associated with the very same exception object.
        attributes = BaseException.__getattribute__(error, "__dict__")
        previous = attributes.get(_CUSTODY_ERRORS_ATTRIBUTE, ())
        if type(previous) is not tuple:
            previous = (previous,)
        if not any(receipt is self for receipt in previous):
            BaseException.__setattr__(
                error, _CUSTODY_ERRORS_ATTRIBUTE, previous + (self,),
            )

    def cleanup(self, primary=None):
        # Dependencies point to earlier acquisitions. Reverse order closes
        # known leaves while UNKNOWN children continue to hold their anchors.
        for record in reversed(self.records):
            try:
                record.close(primary)
            except BaseException as error:
                # Preserve this exact first error and traceback while any
                # remaining safe releases record only secondary failures.
                self.cleanup(error)
                raise
        self._release_retention()
        if primary is not None:
            self._publish(primary)

    def require_released(self):
        if any(record.state not in ("CLOSED", "NO_FD") for record in self.records):
            raise RuntimeError("reservation descriptor custody remains unresolved")

    def __reduce_ex__(self, protocol):
        raise TypeError("reservation custody cannot be copied or serialized")


def _custody_for_reservation(reservation):
    if type(reservation) is not AttemptReservation:
        return None
    receipt = getattr(reservation, "_custody", None)
    if (type(receipt) is not _ReservationCustody
            or _ISSUED_CUSTODY.get(id(receipt)) is not receipt
            or receipt.reservation is not reservation
            or type(receipt.authorization) is not EngineeringAuthorization
            or receipt.authorization.policy_pin is not reservation._policy_pin
            or receipt.authorization.request_binding != reservation._request_binding):
        return None
    return receipt


def _custody_for_failure(error, *, authorization):
    if (not isinstance(error, BaseException)
            or type(authorization) is not EngineeringAuthorization):
        return None
    attributes = BaseException.__getattribute__(error, "__dict__")
    associations = attributes.get(_CUSTODY_ERRORS_ATTRIBUTE, ())
    if type(associations) is not tuple:
        return None
    matches = []
    for receipt in associations:
        if (type(receipt) is _ReservationCustody
                and _ISSUED_CUSTODY.get(id(receipt)) is receipt
                and receipt.authorization is authorization
                and any(previous is error for previous in receipt._failures)
                and (receipt.reservation is None
                     or _custody_for_reservation(receipt.reservation) is receipt)
                and not any(previous is receipt for previous in matches)):
            matches.append(receipt)
    return matches[0] if len(matches) == 1 else None


def _open_reserved(record, *args, **kwargs):
    try:
        fd = os.open(*args, **kwargs)
    except OSError:
        record.state = "NO_FD"
        raise
    except BaseException:
        record.state = "UNKNOWN"
        raise
    record.fd = fd
    record.state = "OPEN"
    return fd


def _file_state(info: os.stat_result) -> tuple:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_gid, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _check_record_at(dir_fd: int, name: str, fd: int, identity: tuple):
    """Validate both opened inode and nofollow name before any record write."""
    opened = os.fstat(fd)
    named = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    for info in (opened, named):
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != identity):
            raise OSError(
                "reservation record replaced or aliased; operation refused"
            )
        if (info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise OSError("reservation record must remain owner-owned and private mode 0600")
    if _file_state(opened) != _file_state(named):
        raise OSError("reservation record changed between handle and path checks")
    return opened


class AttemptReservation:
    """Private owner-only exclusive durable reservation; one-use latch.

    Created by `claim_attempt_reservation` before any billable API. The
    claim retains this reservation's sealed approval identity
    (complete `policy_pin`, plus `request_binding`) so a host can refuse a
    reservation claimed under a different authorization. Existing or
    ambiguous records refuse without recovery/reads/signals. Afterwards
    the record is append-only: every append opens the record NAME
    relative to the retained directory FD (never re-resolving the
    pathname, never following a symlink) and compares (st_dev, st_ino)
    with the identity observed at claim time, so a replacement or alias
    refuses with zero writes. The module never opens the record for
    reading. Exactly one directory FD stays retained per live reservation
    and is released at `close(event)` only when its dependent acquisitions
    are known released. Failed release retains custody, never retries an
    ambiguous number, and never replaces the primary append error.
    """

    __slots__ = (
        "_dir_fd", "_name", "_record_path", "_identity",
        "_policy_pin", "_request_binding", "_consumed", "_closed",
        "_custody", "_anchor_record", "_operation_error",
    )

    def __init__(
        self, claimer: object, dir_fd: int, name: str, record_path: Path,
        identity: tuple, policy_pin, request_binding: str,
    ) -> None:
        if claimer is not _CLAIM_TOKEN:
            raise PermissionError(
                "reservations claim only through the explicit trusted-host API"
            )
        self._dir_fd = dir_fd
        self._name = name
        self._record_path = record_path
        self._identity = identity
        self._policy_pin = policy_pin
        self._request_binding = request_binding
        self._consumed = False
        self._closed = False
        self._custody = None
        self._anchor_record = None
        self._operation_error = None

    @property
    def record_path(self) -> Path:
        return self._record_path

    @property
    def policy_pin(self):
        """Complete sealed approval FilePin: path, size and SHA256."""
        return self._policy_pin

    @property
    def policy_sha256(self) -> str:
        """Sealed approval identity retained at claim: policy FilePin SHA256."""
        return self._policy_pin.sha256

    @property
    def request_binding(self) -> str:
        """Sealed approval identity retained at claim: exact request binding."""
        return self._request_binding

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def closed(self) -> bool:
        return self._closed

    def consume(self) -> None:
        if self._consumed or self._closed:
            raise RuntimeError("durable attempt reservation is one-use")
        if self._operation_error is not None:
            raise self._operation_error
        self._consumed = True

    def record_identity(self, kind: str, identity: str) -> None:
        if self._closed:
            raise RuntimeError("reservation record already closed")
        if self._operation_error is not None:
            raise self._operation_error
        if kind == "app":
            pattern = APP_ID
        elif kind == "sandbox":
            pattern = RESOURCE_ID
        else:
            raise ValueError("identity kind must be app or sandbox")
        if type(identity) is not str or pattern.fullmatch(identity) is None:
            raise ValueError(f"{kind} identity requires the exact service-issued ID")
        try:
            self._append({"event": "identity", "kind": kind, "identity": identity})
        except BaseException as error:
            self._operation_error = error
            self._custody._publish(error)
            raise

    def close(self, event: str) -> None:
        if event not in ("stopped", "failed"):
            raise ValueError("close event must be stopped or failed")
        if self._closed:
            return
        # Logical finality precedes the first final append. Physical custody
        # is tracked separately, including a physically closed then raised FD.
        self._closed = True
        try:
            if self._operation_error is None:
                self._append({"event": event}, _final=True)
            else:
                self._custody.cleanup(self._operation_error)
                if any(record.state not in ("CLOSED", "NO_FD")
                       for record in self._custody.records):
                    raise self._operation_error
                return
        except BaseException as error:
            self._custody.cleanup(error)
            self._custody._publish(error)
            raise
        self._custody.cleanup()
        self._custody.require_released()

    def _append(self, record: dict, *, _final=False) -> None:
        if ((self._closed and not _final) or self._dir_fd < 0
                or self._anchor_record.state != "OPEN"):
            raise RuntimeError("reservation record already closed")
        if self._operation_error is not None:
            raise self._operation_error
        wire = (
            json.dumps(record, separators=(",", ":"), allow_nan=False).encode("ascii")
            + b"\n"
        )
        acquired = self._custody.reserve(
            "append", parent=self._anchor_record,
            required_anchor=self._anchor_record,
        )
        fd = _open_reserved(
            acquired,
            self._name,
            os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self._dir_fd,
        )
        primary = None
        try:
            info = os.fstat(fd)
            acquired.opened_identity = (info.st_dev, info.st_ino)
            opened = _check_record_at(self._dir_fd, self._name, fd, self._identity)
            if os.write(fd, wire) != len(wire):
                raise OSError("short reservation record write")
            os.fsync(fd)
            after = _check_record_at(self._dir_fd, self._name, fd, self._identity)
            if after.st_size != opened.st_size + len(wire):
                raise OSError("reservation record size changed during append")
        except BaseException as error:
            primary = error
            raise
        finally:
            acquired.close(primary)

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("durable reservation cannot be serialized")


def sealed_claim_record_path(authorization: EngineeringAuthorization) -> Path:
    """Deterministic private claim location sealed to the approved policy.

    Derived only from the exact owner-approved policy FilePin (its
    owner-controlled directory plus its SHA256), never from an operation
    nonce, a request variant or a caller-chosen filename: the same approval
    always maps to the same record, so reissuing identical approved inputs
    cannot bypass the old claim. Changing the claim location requires a new
    explicit owner approval, i.e. a different policy FilePin at issuance.
    """
    if type(authorization) is not EngineeringAuthorization:
        raise PermissionError(
            "sealed engineering authorization required to derive the claim location"
        )
    pin = authorization.policy_pin
    return pin.path.parent / f"{_CLAIM_PREFIX}{pin.sha256}.jsonl"


def _require_trusted_dir(st: os.stat_result, *, immediate: bool) -> None:
    """Owner-controlled ancestry check; root-owned non-writable OS dirs trusted.

    A directory is trusted when owned by the effective uid, or owned by
    root and not group/other-writable (root-owned sticky directories such
    as /tmp are the OS-managed temp roots and stay trusted: no blind
    require-all-ancestors-same-UID). Any group/other-writable location
    outside that exception is unsafe (entries can be swapped) and refuses.
    The immediate claim directory must additionally be owner-controlled.
    """
    euid = os.geteuid()
    group_or_other_writable = st.st_mode & 0o022 != 0
    sticky_root = st.st_uid == 0 and st.st_mode & stat.S_ISVTX != 0
    if st.st_uid != euid and st.st_uid != 0:
        raise OSError("claim ancestry must be owner- or root-owned")
    if st.st_uid == 0 and group_or_other_writable and not sticky_root:
        raise OSError("unsafe writable root-owned ancestor refused")
    if st.st_uid == euid and group_or_other_writable:
        raise OSError("unsafe writable owner ancestor/claim directory refused")
    if immediate and st.st_uid != euid:
        raise OSError("private claim directory must be owner-controlled")


def _anchor_dir_fd(parent: Path, custody: _ReservationCustody) -> _ReservationFD:
    """Anchor at "/" and nofollow-traverse to `parent`; retain its generation.

    Each step opens the next path component relative to the retained
    directory FD with O_DIRECTORY|O_NOFOLLOW, so a symlinked parent (or
    any symlinked ancestor) refuses instead of being followed and a
    parent switched to a symlink between claims cannot relocate the
    claim. Validated traversal children become independent anchors before
    predecessor release. Unknown acquisitions retain their required anchor.
    """
    if not parent.is_absolute() or ".." in parent.parts:
        raise ValueError("absolute traversal-safe claim directory required")
    current = custody.reserve("directory")
    _open_reserved(current, "/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    parts = parent.parts[1:]
    info = os.fstat(current.fd)
    current.opened_identity = (info.st_dev, info.st_ino)
    _require_trusted_dir(info, immediate=not parts)
    for index, part in enumerate(parts):
        nxt = custody.reserve(
            "directory", parent=current, required_anchor=current,
        )
        _open_reserved(
            nxt, part,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
            dir_fd=current.fd,
        )
        info = os.fstat(nxt.fd)
        nxt.opened_identity = (info.st_dev, info.st_ino)
        _require_trusted_dir(info, immediate=(index == len(parts) - 1))
        nxt.required_anchor = None
        current.close()
        current = nxt
    return current


def _validate_policy_at(anchor: _ReservationFD, pin: object) -> None:
    """Validate the ACTUAL bounded policy bytes at the approved FilePin.

    Opens the final policy name relative to the retained directory FD
    with O_NOFOLLOW|O_NONBLOCK (symlink refuses; FIFO cannot block), then
    compares the nofollow name and opened handle before/after reading:
    regular file, single link (hardlink/alias
    refuses), owner- or root-owned, not group/other-writable, exact
    approved size, and exact approved SHA256 over the bounded bytes.
    Release is attempted once here; unknown policy custody holds the anchor.
    The policy itself is the only file this module reads.
    """
    if pin.size > _MAX_POLICY_BYTES:
        raise ValueError("approved policy pin size exceeds the claim bound")
    dir_fd = anchor.fd
    before = os.stat(pin.path.name, dir_fd=dir_fd, follow_symlinks=False)
    acquired = anchor.custody.reserve("policy", parent=anchor, required_anchor=anchor)
    fd = _open_reserved(
        acquired,
        pin.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=dir_fd,
    )
    primary = None
    try:
        st = os.fstat(fd)
        acquired.opened_identity = (st.st_dev, st.st_ino)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("approved policy pin must be a regular file")
        if st.st_nlink != 1:
            raise OSError("hardlinked/aliased policy file refused")
        euid = os.geteuid()
        if st.st_uid not in (euid, 0):
            raise OSError("policy file must be owner- or root-owned")
        if st.st_mode & 0o022 != 0:
            raise OSError("unsafe writable policy file refused")
        if st.st_size != pin.size:
            raise OSError("policy file size drifted from the approved FilePin")
        if (_file_state(before) != _file_state(st)
                or _file_state(os.stat(
                    pin.path.name, dir_fd=dir_fd, follow_symlinks=False,
                )) != _file_state(st)):
            raise OSError("approved policy identity changed before read")
        digest = hashlib.sha256()
        remaining = pin.size
        while remaining > 0:
            chunk = os.read(fd, min(_POLICY_READ_CHUNK_BYTES, remaining))
            if not chunk:
                raise OSError("policy file truncated below the approved size")
            digest.update(chunk)
            remaining -= len(chunk)
        if digest.hexdigest() != pin.sha256:
            raise OSError("policy bytes drifted from the approved FilePin hash")
        if (_file_state(os.fstat(fd)) != _file_state(st)
                or _file_state(os.stat(
                    pin.path.name, dir_fd=dir_fd, follow_symlinks=False,
                )) != _file_state(st)):
            raise OSError("approved policy identity or content changed during read")
    except BaseException as error:
        primary = error
        raise
    finally:
        acquired.close(primary)


def claim_attempt_reservation(authorization: EngineeringAuthorization) -> AttemptReservation:
    """Exclusive durable claim; refuses any existing/ambiguous record.

    The only parameter is the sealed authorization; the record path is
    derived deterministically by `sealed_claim_record_path` (no caller-
    selectable root, path, filename or nonce). The claim anchors at "/"
    and nofollow-traverses to the approved policy directory, validating
    the trusted ownership/ancestor chain and the private claim directory,
    validates the ACTUAL bounded policy bytes against the approved
    FilePin, and retains the claim directory FD: the record is created
    and every later append happens relative to that FD, so switching a
    symlinked parent or aliasing the record name cannot relocate or
    double-claim. Opened and final identities are compared by fstat-after-
    open (regular, single link, owner-owned, mode 0600, empty); the
    anchored nofollow opens leave no discovery TOCTOU window. Never reads,
    recovers, deletes or
    signals a previous record: a second use under the same approval is
    refused structurally by O_CREAT|O_EXCL, and ambiguity (any other
    OSError) refuses the same way. The reserved line and the returned
    reservation retain both approval identities (complete policy FilePin and
    request binding), so hosts refuse reservations claimed under a
    different authorization. Failure publishes actual generation custody;
    ambiguous releases retain required anchors without numeric-FD retries.
    """
    if type(authorization) is not EngineeringAuthorization:
        raise PermissionError(
            "sealed engineering authorization required to derive the claim location"
        )
    custody = _ReservationCustody(_CUSTODY_TOKEN, authorization)
    try:
        pin = authorization.policy_pin
        if not isinstance(pin.path, Path) or not pin.path.is_absolute():
            raise ValueError("absolute policy pin path required")
        if ".." in pin.path.parts:
            raise ValueError("traversal-free policy pin path required")
        record_path = sealed_claim_record_path(authorization)
        record_name = f"{_CLAIM_PREFIX}{pin.sha256}.jsonl"
        anchor = _anchor_dir_fd(pin.path.parent, custody)
        dir_fd = anchor.fd
        _validate_policy_at(anchor, pin)
        acquired = custody.reserve("claim", parent=anchor, required_anchor=anchor)
        try:
            fd = _open_reserved(
                acquired,
                record_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=dir_fd,
            )
        except FileExistsError:
            raise FileExistsError(
                "existing attempt record refuses a second reservation without recovery"
            ) from None
        except OSError:
            raise OSError(
                "ambiguous reservation state; refuses without reads/recovery/signals"
            ) from None
        primary = None
        try:
            created = os.fstat(fd)
            identity = (created.st_dev, created.st_ino)
            acquired.opened_identity = identity
            created = _check_record_at(dir_fd, record_name, fd, identity)
            if created.st_size != 0:
                raise OSError(
                    "opened record is not the fresh private record; "
                    "refuses without reads/recovery/signals"
                )
            wire = (
                json.dumps(
                    {
                        "v": 1,
                        "event": "reserved",
                        "policy_sha256": pin.sha256,
                        "request_binding": authorization.request_binding,
                    },
                    separators=(",", ":"),
                ).encode("ascii")
                + b"\n"
            )
            if os.write(fd, wire) != len(wire):
                raise OSError("short reservation record write")
            os.fsync(fd)
            after = _check_record_at(dir_fd, record_name, fd, identity)
            if after.st_size != len(wire):
                raise OSError("reservation record changed during claim")
            # Sync the retained directory after the file, before any usable
            # reservation is returned. Failure preserves the exclusive marker.
            os.fsync(dir_fd)
            _check_record_at(dir_fd, record_name, fd, identity)
        except BaseException as error:
            primary = error
            raise
        finally:
            acquired.close(primary)
        reservation = AttemptReservation(
            _CLAIM_TOKEN, dir_fd, record_name, record_path,
            (created.st_dev, created.st_ino),
            pin, authorization.request_binding,
        )
        reservation._custody = custody
        reservation._anchor_record = anchor
        custody._reservation = reservation
        return reservation
    except BaseException as error:
        custody.cleanup(error)
        custody._publish(error)
        raise
