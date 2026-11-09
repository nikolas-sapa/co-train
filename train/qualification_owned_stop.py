"""Concrete owned-App AppStop binding over the EXISTING bounded watchdog.

No custom process supervision is added here. This module only wires the two
existing reviewed mechanisms into one explicit binding used by
`train.qualification_modal_host.ModalOwnedHost`:

- `train.modal_app_stop_launcher.stage_trusted_teardown`: stages the
  exact-owned-ID stop executable (pinned official Modal 1.6.3 SDK, original
  AppStop route modal/cli/app.py:407-408 via train.modal_app_stop) as one
  argv `TrustedTeardown` command.
- `train.qualification_watchdog.arm`: arms the independent controller child
  with bounded local teardown, append-only evidence and per-process App
  reservation.

A local stop acknowledgement (including an AppStop ACK) is never
remote-termination or billing-end proof; those outcomes stay UNKNOWN in the
watchdog's own report vocabulary. The constructor validates its inputs and
performs no file IO; staging happens once per attempt, after the real App ID
exists and before any Sandbox creation. stdlib + first-party imports only,
no import-time work, no SDK import. The validated constructor facts are also
exposed read-only (`interpreter`, `source_root`, `sdk_root`, `sdk_pins`,
`timing_facts()` and the rest) so the V226 isolated owner can bind its worker
launch pins to this actual binding instead of to caller-supplied values.
"""

from __future__ import annotations

import math
from pathlib import Path
import re

from train import modal_app_stop_launcher as launcher
from train import qualification_watchdog as watchdog
from train.qualification_isolated_contract import StopTimingFacts, ceil_ns


_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_RPC_SECONDS = 30.0
_MAX_TEARDOWN_SECONDS = 30.0
_MAX_ARM_SECONDS = 5.0


def _absolute(value: object, name: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute() or ".." in value.parts:
        raise ValueError(f"{name} requires an absolute resolved path")
    return value


def _digest(value: object, name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} requires an independent lowercase 64-hex SHA256")
    return value


def _seconds(value: object, name: str, maximum: float) -> float:
    if (type(value) not in (int, float) or isinstance(value, bool)
            or not math.isfinite(value) or not 0 < value <= maximum):
        raise ValueError(f"{name} must be finite within (0,{maximum}] seconds")
    return float(value)


class OwnedAppStopBinding:
    """Staging/arm inputs for one owned attempt; delegates, never supervises.

    `stage` produces the TrustedTeardown executable bound to the exact
    retained App ID and a wall-clock expiry; `arm` hands custody, the exact
    retained App object and its ID to the existing bounded watchdog. All
    forwarding is by identity/value without clamping: the launcher's and the
    watchdog's own checks (freshness <=1800s, ID patterns, deadline reserve)
    stay authoritative.
    """

    def __init__(
        self, *, interpreter: Path, interpreter_sha256: str, adapter_sha256: str,
        source_root: Path, sdk_root: Path, sdk_pins: dict[str, str],
        private_scratch: Path, environment: dict[str, str],
        rpc_seconds: float, teardown_seconds: float = 1.0, arm_seconds: float = 1.0,
        ownership_confirmed: bool,
    ) -> None:
        # Explicit ownership confirmation; True only, never truthy substitutes.
        if ownership_confirmed is not True:
            raise ValueError("explicit independent ownership confirmation required")
        self._interpreter = _absolute(interpreter, "interpreter")
        self._interpreter_sha256 = _digest(interpreter_sha256, "interpreter_sha256")
        self._adapter_sha256 = _digest(adapter_sha256, "adapter_sha256")
        self._source_root = _absolute(source_root, "source_root")
        self._sdk_root = _absolute(sdk_root, "sdk_root")
        if type(sdk_pins) is not dict or not sdk_pins:
            raise ValueError("complete reviewed SDK source pins required")
        self._sdk_pins = dict(sdk_pins)
        self._private_scratch = _absolute(private_scratch, "private_scratch")
        if type(environment) is not dict or not environment:
            raise ValueError("explicit restricted teardown environment required")
        self._environment = dict(environment)
        self._rpc_seconds = _seconds(rpc_seconds, "rpc_seconds", _MAX_RPC_SECONDS)
        self._teardown_seconds = _seconds(
            teardown_seconds, "teardown_seconds", _MAX_TEARDOWN_SECONDS,
        )
        self._arm_seconds = _seconds(arm_seconds, "arm_seconds", _MAX_ARM_SECONDS)

    # Read-only views of the already-validated constructor facts. The V226
    # isolated owner binds its worker launch pins (interpreter, source root,
    # SDK root and complete SDK pins) from THIS actual binding rather than from
    # caller-supplied values, so no separate pin source can drift. Mappings are
    # copied; no default, limit or existing behaviour changes.

    @property
    def interpreter(self) -> Path:
        return self._interpreter

    @property
    def interpreter_sha256(self) -> str:
        return self._interpreter_sha256

    @property
    def adapter_sha256(self) -> str:
        return self._adapter_sha256

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def sdk_root(self) -> Path:
        return self._sdk_root

    @property
    def sdk_pins(self) -> dict[str, str]:
        return dict(self._sdk_pins)

    @property
    def private_scratch(self) -> Path:
        return self._private_scratch

    @property
    def environment(self) -> dict[str, str]:
        return dict(self._environment)

    @property
    def rpc_seconds(self) -> float:
        return self._rpc_seconds

    @property
    def teardown_seconds(self) -> float:
        return self._teardown_seconds

    @property
    def arm_seconds(self) -> float:
        return self._arm_seconds

    def timing_facts(self) -> StopTimingFacts:
        """Exact frozen shutdown timing facts for the isolated owner route.

        Uses the shared exact binary-ratio ceiling, so a reviewed float can
        never round down into an infeasible reserve. ``StopTimingFacts`` itself
        refuses `rpc > teardown` and `teardown + 9.5s > 30s`; the isolated owner
        checks that refusal before bind/claim/journal/spawn.
        """
        return StopTimingFacts(
            ceil_ns(self._rpc_seconds),
            ceil_ns(self._teardown_seconds),
            ceil_ns(self._arm_seconds),
        )

    def stage(
        self, *, expected_app_id: str, expires_at: float,
    ) -> watchdog.TrustedTeardown:
        """Stage the exact-owned-ID stop executable for one attempt."""
        if type(expected_app_id) is not str or not expected_app_id:
            raise ValueError("exact retained App ID required for staging")
        if (type(expires_at) not in (int, float) or isinstance(expires_at, bool)
                or not math.isfinite(expires_at)):
            raise ValueError("finite wall-clock staging expiry required")
        return launcher.stage_trusted_teardown(
            interpreter=self._interpreter,
            interpreter_sha256=self._interpreter_sha256,
            source_root=self._source_root,
            adapter_module=self._source_root / "modal_app_stop.py",
            adapter_sha256=self._adapter_sha256,
            sdk_root=self._sdk_root,
            sdk_pins=self._sdk_pins,
            private_scratch=self._private_scratch,
            expected_app_id=expected_app_id,
            ownership_confirmed=True,
            explicitly_trusted=True,
            expires_at=expires_at,
            rpc_seconds=self._rpc_seconds,
            environment=self._environment,
        )

    def arm(
        self, *, custody: object, app_identity: object, app_id: str,
        teardown: watchdog.TrustedTeardown, deadline: float, evidence_path: Path,
    ) -> watchdog.Watchdog:
        """Arm the existing independent bounded watchdog for the owned App."""
        return watchdog.arm(
            custody=custody,
            app_identity=app_identity,
            app_id=app_id,
            teardown=teardown,
            deadline=deadline,
            evidence_path=evidence_path,
            teardown_seconds=self._teardown_seconds,
            arm_seconds=self._arm_seconds,
        )

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("trusted-host stop binding cannot be serialized")
