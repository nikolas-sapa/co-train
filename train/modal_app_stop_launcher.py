"""Explicit future staging only; never arms a watchdog or invokes a provider."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import shlex
import tempfile
import time

from .modal_app_stop import PinnedSDK, retained_source, trusted_path, validate_owner
from .qualification_watchdog import TrustedTeardown


def explicit_environment(environment: Mapping[str, str], interpreter: Path) -> dict[str, str]:
    copied = dict(environment)
    if (set(copied) - {"PATH", "HOME", "LANG", "LC_ALL"}
            or not {"PATH", "HOME"}.issubset(copied)
            or any(type(value) is not str or "\0" in value for value in copied.values())
            or copied["PATH"] != f"{interpreter.parent}:/usr/bin:/bin"
            or len(json.dumps(copied).encode("ascii")) > 2048):
        raise ValueError("explicit restricted environment required")
    trusted_path(Path(copied["HOME"]), directory=True, private=True)
    return copied


def stage_trusted_teardown(
    *, interpreter: Path, interpreter_sha256: str, source_root: Path,
    adapter_module: Path, adapter_sha256: str, sdk_root: Path,
    sdk_pins: Mapping[str, str], private_scratch: Path, expected_app_id: str,
    ownership_confirmed: bool, explicitly_trusted: bool, expires_at: float,
    rpc_seconds: float, environment: Mapping[str, str],
) -> TrustedTeardown:
    config = {
        "interpreter": str(interpreter), "interpreter_sha256": interpreter_sha256,
        "sdk_root": str(sdk_root), "sdk_pins": dict(sdk_pins),
        "expected_app_id": expected_app_id, "ownership_confirmed": ownership_confirmed,
        "explicitly_trusted": explicitly_trusted, "expires_at": expires_at,
        "rpc_seconds": rpc_seconds,
    }
    validate_owner(config)
    trusted_path(source_root, directory=True)
    if adapter_module != source_root / "modal_app_stop.py":
        raise ValueError("explicit adapter source module required")
    adapter = retained_source(adapter_module, adapter_sha256)
    retained_source(interpreter, interpreter_sha256, limit=128 * 1024 * 1024)
    if (not os.access(interpreter, os.X_OK)
            or any(character.isspace() for character in str(interpreter))):
        raise ValueError("explicit executable interpreter required")
    PinnedSDK(sdk_root, sdk_pins)
    trusted_path(private_scratch, directory=True, private=True)
    copied_environment = explicit_environment(environment, interpreter)
    if expires_at <= time.time():
        raise ValueError("expired ownership")
    directory = Path(tempfile.mkdtemp(prefix="owned-app-stop-", dir=private_scratch))
    config["claim_directory"] = str(directory)
    executable = directory / "stop-owned-app"
    # One argv executable for TrustedTeardown, with isolated Python and no site hooks.
    wrapper = (
        '#!/bin/sh\n""":"\n'
        f'exec {shlex.quote(str(interpreter))} -I -S -B "$0"\n'
        '":"""\n'
        'import sys\n'
        'try:\n'
        '    namespace = {"__name__": "_reviewed_stop_adapter"}\n'
        f'    source = {adapter!r}\n'
        f'    exec(compile(source, {str(adapter_module)!r}, "exec"), namespace)\n'
        f'    status = namespace["main"]({config!r})\n'
        'except BaseException:\n'
        '    status = 1\n'
        'raise SystemExit(status)\n'
    ).encode("ascii")
    fd = os.open(
        executable, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(wrapper)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o500)
    trusted_path(executable, private=True)
    return TrustedTeardown(executable, copied_environment, explicitly_trusted=True)
