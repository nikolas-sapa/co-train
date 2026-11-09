"""Real owned Modal SDK lifecycle behind sealed host-only authority.

Inspected actual Modal 1.6.3 async API (read-only named sources, no
guessing): `modal/app.py:196-264` `_App.__init__` is a lazy local
constructor accepting `include_source=False`; `modal/app.py:434-500`
`run()` is decorated with `synchronicity.async_wrap.asynccontextmanager`,
which is plain contextlib async-context-manager semantics
(`synchronicity/async_wrap.py:67-92`), delegating to `modal/runner.py:370-
427` `_run_app` (`AppCreateRequest`, `APP_STATE_EPHEMERAL` when
`detach=False`, heartbeats, no deploy); `modal/app.py:423-432` sets the real
`_app_id` on entry; `modal/app.py:1625-1644` `async App.stop()` sends
`AppStopRequest`; `modal/sandbox/_sandbox.py:179-359` `_Sandbox.create` is a
`@staticmethod` coroutine; `modal/sandbox/_sandbox.py:1014-1034`
`async terminate()`; `modal/_object.py:304` `object_id`;
`modal/_image.py:2281-2364` `Image.from_registry(...)` is a lazy local
constructor. The host therefore requires the exact raw async classes
(`modal.app._App`, `modal.sandbox._sandbox._Sandbox`, `modal._image._Image`)
and awaits their plain coroutines; no `.aio` wrapper syntax is assumed. The
class-label/coroutine-shape checks are structural binding only, not genuine
source-compatibility proof; the parent separately performs the real SDK
compatibility check. `host.resource` is the actual retained Sandbox object
(None before creation); the sealed caps are exposed separately as
`host.resource_config`.

Authority defaults to refusal: only the sealed
`train.qualification_engineering_host.EngineeringAuthorization` plus the
durable `AttemptReservation` configure a host. One-resource latch: at most
one active owned host per process, and one durable attempt record overall.
The latch itself lives in `acquire_common_latch`/`release_common_latch`, which
the V226 isolated owner also uses so both routes compete for exactly one slot.
A stop acknowledgement (including an AppStop ACK) never proves billing
ceased; remote termination and charged end are recorded UNKNOWN. The host
constructs the sealed base-only lazy Image internally through the
owner-controlled factory `sealed_candidate_image` (exact frozen base
reference; no layers, mounts, installs or builds); no caller `image`
parameter exists and supplying one refuses before any allocation. When
`watchdog.arm` fails after the controller child exists, its
`ArmError.controller` is retained, the arm is marked ambiguous (zero
rearm/create afterwards) and `stop_owned` finishes the retained controller
exactly once. No image
build/staging API is exposed. No import-time work, no SDK import at module load.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import math
from pathlib import Path
import re
import threading
import time
from typing import Callable

from train.qualification_engineering_host import (
    APP_ID,
    MAX_GPU_WINDOW_SECONDS,
    RESOURCE_ID,
    AttemptReservation,
    EngineeringAuthorization,
)
from train.qualification_image_plan import candidate_recipe
from train.qualification_owned_stop import OwnedAppStopBinding


_SDK_CLASSES = (
    ("App", "modal.app", "_App"),
    ("Sandbox", "modal.sandbox._sandbox", "_Sandbox"),
    ("Image", "modal._image", "_Image"),
)
_LATCH_LOCK = threading.Lock()
_ACTIVE_HOST: object | None = None
# Bounded per-step cleanup floor in stop_owned: small, finite and fixed, so
# an exhausted caller deadline still drives real bounded cleanup attempts.
_MIN_STOP_STEP_SECONDS = 0.25


def acquire_common_latch(holder: object) -> None:
    """Take the single process-wide owned-resource slot for ``holder``.

    Shared by ``ModalOwnedHost`` and the V226 isolated owner so both routes
    compete for exactly one latch implementation and at most one active owned
    resource exists per process. Refuses while any holder is active; the caller
    keeps its own ambiguity and durable-record bookkeeping.
    """
    global _ACTIVE_HOST
    with _LATCH_LOCK:
        if _ACTIVE_HOST is not None:
            raise RuntimeError(
                "one owned resource at a time; an active host holds the latch"
            )
        _ACTIVE_HOST = holder


def release_common_latch(holder: object) -> bool:
    """Release the slot only for the identical holder; ``True`` when released."""
    global _ACTIVE_HOST
    with _LATCH_LOCK:
        if _ACTIVE_HOST is not holder:
            return False
        _ACTIVE_HOST = None
        return True


@dataclass(frozen=True)
class ResourceConfig:
    """Exact charged resource configuration; caps equal planning inputs."""

    gpu: str
    cpu: tuple[float, float]
    memory: tuple[int, int]


@dataclass(frozen=True)
class OwnedStopOutcome:
    """Bounded stop evidence only; never remote or billing-end proof."""

    app_id: str | None
    sandbox_id: str | None
    sandbox_terminate: str
    app_stop: str
    context_closed: bool
    watchdog_report: dict | None
    error_labels: tuple[str, ...] = ()
    remote_termination: str = "UNKNOWN"
    charged_end: str = "UNKNOWN"


class _HostCustody:
    """Retains actual service identities; refuses any replacement."""

    __slots__ = ("_app_identity", "_resource_identity")

    def __init__(self) -> None:
        self._app_identity: object | None = None
        self._resource_identity: object | None = None

    @property
    def app_identity(self) -> object | None:
        return self._app_identity

    @property
    def resource_identity(self) -> object | None:
        return self._resource_identity

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


def _finite(value: object, name: str) -> float:
    if (type(value) not in (int, float) or isinstance(value, bool)
            or not math.isfinite(value)):
        raise ValueError(f"{name} requires a finite number")
    return float(value)


def _require_sdk(sdk: object) -> None:
    # Structural binding only: class labels and coroutine-export shape bind
    # the host to the named raw async implementation classes. This is NOT
    # genuine source-compatibility proof; the parent separately performs the
    # real SDK compatibility check against the installed Modal 1.6.3.
    for attribute, module, name in _SDK_CLASSES:
        cls = getattr(sdk, attribute, None)
        if (not isinstance(cls, type) or cls.__module__ != module
                or cls.__name__ != name):
            raise ValueError(
                f"sdk.{attribute} must carry the {module}.{name} class labels"
            )
    if not asyncio.iscoroutinefunction(sdk.Sandbox.create):
        raise ValueError("Sandbox.create must be the original coroutine")
    if not asyncio.iscoroutinefunction(sdk.App.stop):
        raise ValueError("App.stop must be the original coroutine")
    if not callable(sdk.Image.from_registry):
        raise ValueError("Image.from_registry must be the original lazy constructor")


def sealed_candidate_image(sdk: object, authorization: EngineeringAuthorization) -> object:
    """Owner-controlled factory: the exact approved base-only lazy Image.

    Constructs from the sealed immutable base reference bound at issuance
    (re-checked here against the frozen candidate recipe), through exactly
    the base-only lazy constructor: no layers, mounts, installs, builds or
    registry overrides are expressible. The returned object is the only
    image a host ever allocates with; class labels remain structural binding
    only and prove no SDK integrity.
    """
    if type(authorization) is not EngineeringAuthorization:
        raise PermissionError(
            "sealed EngineeringAuthorization required to construct the sealed image"
        )
    _require_sdk(sdk)
    base = authorization.image_base_reference
    if type(base) is not str or base != candidate_recipe().base_reference:
        raise ValueError(
            "sealed base reference drifted from the frozen candidate recipe"
        )
    image = sdk.Image.from_registry(
        base, secret=None, setup_dockerfile_commands=[],
        force_build=False, add_python=None,
    )
    if image is None or type(image) is not sdk.Image:
        raise ValueError("sealed lazy Image construction returned a foreign object")
    return image


class ModalOwnedHost:
    """Fully configured owned host handed to the runner; no authority, no host.

    Lifecycle: `open_app` (real empty ephemeral App under the preparation
    deadline) -> `begin_gpu_window` (arm the independent owned-App stop
    watchdog, single global end <=1800s including cleanup) -> `create_once`
    (one real Sandbox.create) -> C's approved upload/offline install/exec ->
    `stop_owned` (bounded terminate + retained App.stop + context close +
    watchdog fallback). Every step re-checks the sealed authority; ambiguity
    always refuses retry instead of replacing a resource. The reservation
    must be claimed under the exact presented authorization (its retained
    complete `policy_pin` path/size/hash and `request_binding` must equal
    the authorization's):
    a claim under approval B can never construct a host for approval A or
    reissued A, and the refusal happens before the image factory, the App
    and any create.
    """

    def __init__(
        self, *, authorization: EngineeringAuthorization,
        reservation: AttemptReservation, sdk: object,
        resource_config: ResourceConfig, stop_binding: OwnedAppStopBinding,
        evidence_path: Path, clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if type(authorization) is not EngineeringAuthorization:
            raise PermissionError(
                "sealed EngineeringAuthorization required; plans, JSON, bools or "
                "callbacks grant no authority"
            )
        if type(reservation) is not AttemptReservation:
            raise PermissionError(
                "durable AttemptReservation required before any billable API"
            )
        if reservation.consumed or reservation.closed:
            raise PermissionError("reservation already used or closed")
        claimed_pin, approved_pin = reservation.policy_pin, authorization.policy_pin
        if ((claimed_pin.path, claimed_pin.size, claimed_pin.sha256)
                != (approved_pin.path, approved_pin.size, approved_pin.sha256)
                or reservation.request_binding != authorization.request_binding):
            raise PermissionError(
                "reservation was claimed under a different sealed approval; "
                "cross-approval host construction refused before the image "
                "factory, the App and any create"
            )
        _require_sdk(sdk)
        if type(resource_config) is not ResourceConfig:
            raise ValueError("exact ResourceConfig required")
        workload = authorization.workload
        if (type(resource_config.gpu) is not str
                or resource_config.gpu != authorization.gpu_label):
            raise ValueError("resource gpu must equal the sealed gpu label")
        if (type(resource_config.cpu) is not tuple or len(resource_config.cpu) != 2
                or any(type(value) is not float or not math.isfinite(value)
                       or value <= 0 for value in resource_config.cpu)
                or resource_config.cpu[0] > resource_config.cpu[1]
                or Decimal(str(resource_config.cpu[1])) != Decimal(workload.cpu_cores)):
            raise ValueError(
                "cpu (request, limit) tuple must cap exactly at the charged planning cores"
            )
        memory_cap = Decimal(workload.ram_gib) * 1024
        if (memory_cap != memory_cap.to_integral_value()
                or type(resource_config.memory) is not tuple
                or len(resource_config.memory) != 2
                or any(type(value) is not int or value <= 0
                       for value in resource_config.memory)
                or resource_config.memory[0] > resource_config.memory[1]
                or Decimal(resource_config.memory[1]) != memory_cap):
            raise ValueError(
                "memory (request, limit) MiB tuple must cap exactly at the charged "
                "planning GiB"
            )
        if type(stop_binding) is not OwnedAppStopBinding:
            raise ValueError("concrete OwnedAppStopBinding required")
        if (not isinstance(evidence_path, Path) or not evidence_path.is_absolute()
                or ".." in evidence_path.parts):
            raise ValueError("absolute watchdog evidence path required")
        if not callable(clock) or not callable(wall_clock):
            raise ValueError("finite monotonic and wall clocks required")
        # Owner-controlled sealed base-only image, constructed internally:
        # caller-supplied image objects are structurally impossible (no
        # parameter exists) and a supplied keyword refuses before allocation.
        image = sealed_candidate_image(sdk, authorization)
        # Bind the one-use authorization only after every validation passed:
        # a refused construction must not burn the sealed authority.
        authorization._bind_once()
        self._authorization = authorization
        self._reservation = reservation
        self._sdk = sdk
        self._image = image
        self._resource_config = resource_config
        self._stop_binding = stop_binding
        self._evidence_path = evidence_path
        self._clock = clock
        self._wall_clock = wall_clock
        self._custody = _HostCustody()
        self._preparation_deadline = self._now() + authorization.preparation_seconds
        self._app: object | None = None
        self._run_context: object | None = None
        self._app_id: str | None = None
        self._app_calls = 0
        self._open_ambiguous = False
        self._sandbox: object | None = None
        self._sandbox_id: str | None = None
        self._create_calls = 0
        self._creation_ambiguous = False
        self._window_end: float | None = None
        self._controller: object | None = None
        self._arm_ambiguous = False
        self._stop_outcome: OwnedStopOutcome | None = None
        self._latch_held = False

    @property
    def preparation_deadline(self) -> float:
        return self._preparation_deadline

    @property
    def app_id(self) -> str | None:
        return self._app_id

    @property
    def sandbox_id(self) -> str | None:
        return self._sandbox_id

    @property
    def resource(self) -> object | None:
        # The actual retained Sandbox object; None before creation. Never a
        # config stand-in: cleanup and evidence use this real handle.
        return self._sandbox

    @property
    def resource_config(self) -> ResourceConfig:
        return self._resource_config

    @property
    def image(self) -> object:
        # The internally constructed sealed base-only lazy Image; the only
        # image object this host ever allocates with.
        return self._image

    @property
    def arm_ambiguous(self) -> bool:
        return self._arm_ambiguous

    @property
    def open_ambiguous(self) -> bool:
        return self._open_ambiguous

    @property
    def creation_ambiguous(self) -> bool:
        return self._creation_ambiguous

    @property
    def gpu_window_end(self) -> float | None:
        return self._window_end

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("owned host cannot be serialized")

    def _now(self) -> float:
        return _finite(self._clock(), "clock()")

    def _wall_now(self) -> float:
        return _finite(self._wall_clock(), "wall_clock()")

    def _require_authority(self) -> None:
        if self._stop_outcome is not None:
            raise RuntimeError("attempt already closed")
        if self._reservation.closed:
            raise RuntimeError("durable reservation already closed")
        self._authorization.require_valid(now_seconds=int(self._wall_now()))

    def require_active(self, request) -> None:
        """Exact provenance/request binding; raises on any invalid state."""
        from train import native_qualification as native

        self._require_authority()
        if request is not self._authorization.request:
            raise PermissionError("exact sealed original request object required")
        if type(request) is not native.QualificationRequest:
            raise PermissionError("exact original QualificationRequest type required")
        if native._request_binding(request) != self._authorization.request_binding:
            raise PermissionError("request digest drift; authority refused")

    def require_uploads(self, items) -> None:
        """Bind `(root, key, size, sha256)` DTOs to the sealed manifest."""
        self._require_authority()
        if type(items) not in (tuple, list):
            raise ValueError("upload DTO sequence required")
        entries = []
        for item in items:
            try:
                entries.append((item.root, item.key, item.size, item.sha256))
            except AttributeError:
                raise ValueError(
                    "upload DTO must expose root/key/size/sha256 attributes"
                ) from None
        if tuple(sorted(entries)) != tuple(sorted(self._authorization.uploads)):
            raise PermissionError("upload manifest drift from the sealed approval")

    def require_setup_argv(self, argv) -> None:
        """Bind the fixed offline installation argv to the sealed approval."""
        self._require_authority()
        if (type(argv) not in (tuple, list)
                or any(type(item) is not str for item in argv)):
            raise ValueError("explicit argv sequence of strings required")
        if tuple(argv) != self._authorization.setup_argv:
            raise PermissionError("setup argv drift from the sealed approval")

    async def open_app(self, *, deadline: float) -> None:
        """Real empty ephemeral App; retains/persists the actual App ID."""
        self._require_authority()
        end = _finite(deadline, "deadline")
        now = self._now()
        if now >= end or end > self._preparation_deadline:
            raise ValueError(
                "open_app deadline must lie within (now, preparation_deadline]"
            )
        if self._app is not None or self._open_ambiguous or self._app_calls > 0:
            raise RuntimeError("App open is one-shot; ambiguity refuses retry")
        # Durable exclusive consumption before the first billable cloud API.
        self._reservation.consume()
        acquire_common_latch(self)
        self._latch_held = True
        self._app_calls += 1
        self._open_ambiguous = True
        # From here a cloud App may exist even on failure: the ambiguity, the
        # latch and the durable record stay; only the parent may reconcile.
        app = self._sdk.App(None, include_source=False)
        run_context = app.run(detach=False)
        # Retain the real handles BEFORE awaiting entry: a failed, lost or
        # overrun enter still leaves stop_owned with the actual App object
        # and run context to clean up, never a discarded live resource.
        self._app = app
        self._run_context = run_context
        self._custody.retain_app(app)
        await asyncio.wait_for(
            run_context.__aenter__(), timeout=max(0.001, end - self._now()),
        )
        app_id = app.app_id
        if type(app_id) is not str or APP_ID.fullmatch(app_id) is None:
            raise ValueError("service-issued ap- App ID required")
        self._app_id = app_id
        self._reservation.record_identity("app", app_id)
        self._open_ambiguous = False

    def begin_gpu_window(self) -> float:
        """Arm the independent owned-App stop watchdog; single global end.

        Returns the monotonic end (now + sealed duration <=1800 seconds) that
        includes verification, export and cleanup. Must be called after
        open_app and before create_once.
        """
        self._require_authority()
        if self._arm_ambiguous:
            raise RuntimeError(
                "arm ambiguity refuses any rearm; zero rearm/create after ambiguity"
            )
        if self._window_end is not None:
            raise RuntimeError("single global GPU window already established")
        if self._app is None or self._open_ambiguous:
            raise RuntimeError("retained open App required before the GPU window")
        seconds = self._authorization.workload.duration_seconds
        if (type(seconds) is not int
                or not 0 < seconds <= MAX_GPU_WINDOW_SECONDS):
            raise ValueError(
                f"sealed workload duration must lie within (0,{MAX_GPU_WINDOW_SECONDS}]"
            )
        end = self._now() + seconds
        try:
            teardown = self._stop_binding.stage(
                expected_app_id=self._app_id,
                expires_at=self._wall_now() + seconds,
            )
            self._controller = self._stop_binding.arm(
                custody=self._custody, app_identity=self._app, app_id=self._app_id,
                teardown=teardown, deadline=end, evidence_path=self._evidence_path,
            )
        except BaseException as error:
            # The existing watchdog.arm raises ArmError(controller) after the
            # controller child exists (train/qualification_watchdog.py:193-198,
            # raised at 348-355 `from primary`): retain the live controller
            # for stop_owned, mark the ambiguity and rethrow the error
            # unchanged so the primary error and its cause survive. Zero
            # rearm and zero create calls are allowed afterwards.
            controller = getattr(error, "controller", None)
            if controller is not None and self._controller is None:
                self._controller = controller
            self._arm_ambiguous = True
            raise
        self._window_end = end
        return end

    async def create_once(self, *, deadline: float) -> object:
        """One real Sandbox.create; no replacements, no reissue after ambiguity."""
        self._require_authority()
        end = _finite(deadline, "deadline")
        now = self._now()
        if self._arm_ambiguous:
            raise RuntimeError(
                "arm ambiguity refuses create; zero resources after ambiguity"
            )
        if self._window_end is None or self._controller is None:
            raise RuntimeError("armed GPU window required before create")
        if now >= end or end > self._window_end:
            raise ValueError("create deadline must lie within (now, gpu_window_end]")
        if self._sandbox is not None or self._creation_ambiguous or self._create_calls > 0:
            raise RuntimeError(
                "Sandbox.create is one-shot; ambiguity refuses any replacement"
            )
        self._create_calls += 1
        # Set before submission: lost responses, exceptions and overruns keep
        # ownership ambiguous even if an identity later arrives.
        self._creation_ambiguous = True
        timeout = min(MAX_GPU_WINDOW_SECONDS, max(1, math.ceil(self._window_end - now)))
        sandbox = await asyncio.wait_for(
            self._sdk.Sandbox.create(
                app=self._app,
                image=self._image,
                gpu=self._resource_config.gpu,
                cpu=self._resource_config.cpu,
                memory=self._resource_config.memory,
                timeout=timeout,
                block_network=True,
                secrets=None,
                network_file_systems={},
                volumes={},
                encrypted_ports=(),
                h2_ports=(),
                unencrypted_ports=(),
                custom_domain=None,
                proxy=None,
                include_oidc_identity_token=False,
                readiness_probe=None,
                pty=False,
                pty_info=None,
                cidr_allowlist=None,
                outbound_cidr_allowlist=None,
                outbound_domain_allowlist=None,
                _experimental_outbound_policy=None,
                _experimental_enable_snapshot=False,
                _experimental_persistent=False,
            ),
            timeout=max(0.001, end - self._now()),
        )
        if sandbox is None:
            raise ValueError("Sandbox.create returned no object")
        # Retain the real resource immediately after the create response,
        # BEFORE ID validation or persistence: an invalid or lost identity
        # keeps the ambiguity but never loses the terminable handle.
        self._sandbox = sandbox
        self._custody.retain_resource(sandbox)
        sandbox_id = sandbox.object_id
        if type(sandbox_id) is not str or RESOURCE_ID.fullmatch(sandbox_id) is None:
            raise ValueError("service-issued sb- Sandbox ID required")
        self._sandbox_id = sandbox_id
        self._reservation.record_identity("sandbox", sandbox_id)
        self._creation_ambiguous = False
        return sandbox

    async def stop_owned(self, *, deadline: float) -> OwnedStopOutcome:
        """Bounded terminate + retained App.stop + context close + watchdog.

        Always attempts the full bounded cleanup sequence, including when
        the caller deadline is already exhausted (each step keeps a small
        bounded floor so an expired ordinary-work deadline can never bypass
        all cleanup, and the outcome is labelled). Preserves the actual
        App/Sandbox identities whatever fails, and never fabricates a
        billing end: `remote_termination` and `charged_end` are UNKNOWN in
        every outcome, including full local success. Idempotent.
        """
        if self._stop_outcome is not None:
            return self._stop_outcome
        end = _finite(deadline, "deadline")
        sandbox_state = "NOT_CREATED" if self._sandbox is None else "UNKNOWN"
        app_state = "NOT_OPENED" if self._app is None else "UNKNOWN"
        context_closed = False
        errors: list[str] = []
        if self._now() >= end:
            errors.append("deadline_exhausted")

        def _budget() -> float:
            # Remaining caller budget, never below the bounded per-step
            # floor: cleanup attempts stay bounded but always happen.
            return max(_MIN_STOP_STEP_SECONDS, end - self._now())

        if self._sandbox is not None:
            try:
                await asyncio.wait_for(self._sandbox.terminate(), timeout=_budget())
                sandbox_state = "ACK"
            except BaseException:
                # Cancellation or timeout is not termination evidence.
                errors.append("sandbox_terminate_failed")
        if self._app is not None:
            try:
                await asyncio.wait_for(self._app.stop(), timeout=_budget())
                app_state = "ACK"
            except BaseException:
                errors.append("app_stop_failed")
        if self._app is not None and self._run_context is not None:
            try:
                await asyncio.wait_for(
                    self._run_context.__aexit__(None, None, None), timeout=_budget(),
                )
                context_closed = True
            except BaseException:
                errors.append("context_close_failed")
        report = None
        if self._controller is not None:
            try:
                # Independent bounded owned-App stop fallback; its own report
                # keeps remote/billing UNKNOWN.
                report = self._controller.finish()
            except BaseException:
                errors.append("watchdog_finish_failed")
        try:
            self._reservation.close("failed" if errors else "stopped")
        except BaseException:
            errors.append("reservation_close_failed")
        if self._latch_held:
            release_common_latch(self)
            self._latch_held = False
        self._stop_outcome = OwnedStopOutcome(
            app_id=self._app_id,
            sandbox_id=self._sandbox_id,
            sandbox_terminate=sandbox_state,
            app_stop=app_state,
            context_closed=context_closed,
            watchdog_report=report,
            error_labels=tuple(errors),
        )
        return self._stop_outcome
