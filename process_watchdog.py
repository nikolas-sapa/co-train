"""Bounded ownership of one POSIX subprocess session, not an OS sandbox."""

from __future__ import annotations

import math
import os
import signal
import subprocess
from collections.abc import Mapping, Sequence


class ProcessCleanupError(RuntimeError):
    """Cleanup did not establish a reaped leader, not an ordinary suite timeout."""


def _seconds(value: float, name: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be positive finite seconds")
    return float(value)


def _signal_group(process: subprocess.Popen[str], signum: int) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin reports EPERM for a group containing only an unreaped zombie.
        # Reap that leader, then retry the original ID. A real denial stays loud.
        if process.poll() is None:
            raise
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass


def _text(value: str | bytes | None, encoding: str) -> str:
    if isinstance(value, bytes):
        return value.decode(encoding, errors="replace")
    return value or ""


def _first_failure(
    first: BaseException | None, error: BaseException, context: str,
) -> BaseException:
    if first is None:
        return error
    first.add_note(f"{context}: {error!r}")
    return first


def _cleanup(
    process: subprocess.Popen[str], *, term_grace: float,
    drain_grace: float, reap_grace: float,
) -> tuple[str, str, bool]:
    """Escalation targets the saved session ID even after the leader is reaped."""
    error: BaseException | None = None
    stdout = stderr = ""
    incomplete_drain = False
    try:
        try:
            _signal_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=term_grace)
            except subprocess.TimeoutExpired:
                pass
        except BaseException as exc:
            error = exc
        finally:
            # A reaped leader is not evidence that its group is empty.
            try:
                _signal_group(process, signal.SIGKILL)
            except BaseException as exc:
                error = _first_failure(error, exc, "Group escalation also failed")
        if error is None:
            try:
                stdout, stderr = process.communicate(timeout=drain_grace)
            except subprocess.TimeoutExpired as exc:
                stdout = _text(exc.output, process.stdout.encoding)
                stderr = _text(exc.stderr, process.stderr.encoding)
                incomplete_drain = True
    except BaseException as exc:
        error = _first_failure(error, exc, "Output drainage also failed")
    finally:
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except BaseException as exc:
                error = _first_failure(error, exc, "Stream closure also failed")
        try:
            process.wait(timeout=reap_grace)
        except subprocess.TimeoutExpired as exc:
            failure = ProcessCleanupError("Failed to reap subprocess after SIGKILL")
            failure.__cause__ = exc
            error = _first_failure(error, failure, "Leader reap also failed")
        except BaseException as exc:
            error = _first_failure(error, exc, "Leader reap also failed")
    if error is not None:
        raise error
    return stdout, stderr, incomplete_drain


def run_bounded(
    args: Sequence[str], *, cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None, timeout: float = 300,
    term_grace: float = 0.2, drain_grace: float = 0.2, reap_grace: float = 0.2,
) -> subprocess.CompletedProcess[str]:
    """Capture a command and clean its original group on every exit path.

    A timeout raises only after bounded cleanup. Descendants that create a new
    session can escape signals; inherited pipes they retain still cannot make
    final drainage wait forever. Output volume is not limited.
    """
    timeout = _seconds(timeout, "timeout")
    term_grace = _seconds(term_grace, "term_grace")
    drain_grace = _seconds(drain_grace, "drain_grace")
    reap_grace = _seconds(reap_grace, "reap_grace")
    if os.name != "posix":
        raise NotImplementedError("process watchdog requires POSIX process groups")
    process = subprocess.Popen(
        args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    cleanup = dict(term_grace=term_grace, drain_grace=drain_grace, reap_grace=reap_grace)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stdout, stderr, incomplete = _cleanup(process, **cleanup)
        error = subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
        if incomplete:
            error.add_note(
                "Output pipes remained open after killing the original process group; "
                "escaped descendants are outside this watchdog."
            )
        raise error from None
    except BaseException as error:
        try:
            _cleanup(process, **cleanup)
        except BaseException as cleanup_error:
            details = tuple(getattr(cleanup_error, "__notes__", ()))
            error.add_note(f"Process cleanup also failed: {cleanup_error!r}")
            for note in details:
                error.add_note(f"Process cleanup detail: {note}")
        raise
    else:
        status = process.returncode
        _cleanup(process, **cleanup)
        return subprocess.CompletedProcess(args, status, stdout, stderr)
