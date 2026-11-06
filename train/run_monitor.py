"""In-memory RUN metric health, not proof of training or checkpoint completion."""

from __future__ import annotations

from copy import deepcopy
from sys import exc_info

from train import verdict as V
from train.run_metrics import _RunMetricsWriter


class RunMonitor:
    """Latch the first RUN criterion or required-telemetry failure.

    Only rows containing the exact ``loss`` key count as logged steps. Healthy
    accumulation below ten steps is not an abort; final adjudication still
    refuses short histories. Optional retention requires explicit attachment.
    No trainer, callback or completion authority lives here.
    """

    __slots__ = ("_rows", "_aborted", "_retainer", "_retention_attempted",
                 "_attachment_locked", "_retention_error")

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._aborted: str | None = None
        self._retainer: _RunMetricsWriter | None = None
        self._retention_attempted = False
        self._attachment_locked = False
        self._retention_error: Exception | None = None

    def attach_retention(self, path: str) -> None:
        """Create caller's absolute JSONL destination once, before observation."""
        if self._attachment_locked or self._retention_attempted:
            raise RuntimeError("RUN retention must attach once before observe/finalize")
        self._retention_attempted = True
        try:
            self._retainer = _RunMetricsWriter(path)
        except Exception as error:
            self._retention_error = error
            raise

    def _check_retention(self) -> None:
        if self._retention_error is not None:
            raise RuntimeError("RUN metrics retention previously failed") from self._retention_error

    def close(self) -> None:
        """Release attached storage without retrying or resuming retention."""
        if self._retainer is not None:
            preserve_primary = (self._retention_error is not None
                                and exc_info()[1] is self._retention_error)
            try:
                self._retainer.close()
            except Exception as error:
                if self._retention_error is None:
                    self._retention_error = error
                if preserve_primary:
                    return
                raise

    @property
    def rows(self) -> list[dict]:
        """Defensive history snapshot, including non-step and post-abort rows."""
        return deepcopy(self._rows)

    @property
    def aborted(self) -> str | None:
        """First failure, read-only and stable after subsequent observations."""
        return self._aborted

    def observe(self, log: dict) -> str | None:
        """Snapshot one log row and return the latched abort reason, if any."""
        self._attachment_locked = True
        self._check_retention()
        if self._retainer is None:
            self._rows.append(deepcopy(log))
        else:
            self._retainer.ensure_open()
            try:
                self._rows.append(deepcopy(log))
                self._retainer.write(self._rows[-1])
            except Exception as error:
                self._retention_error = error
                raise
        if self._aborted is not None or "loss" not in log:
            return self._aborted

        reasons = V.criterion_a_sustained(self._rows)
        steps = V.training_steps(self._rows)
        # B's healthy shortness is expected live, but invalid B is never a
        # warm-up exemption. Evaluate required B on faults even before ten
        # steps, using the verdict's own finite policy and reason ordering.
        if (len(steps) >= V.SUSTAINED_WINDOW
                or any(not V._finite(row.get(V.LOGP_DIFF_KEY)) for row in steps)):
            reasons += V.criterion_b(self._rows, required=True)[0]
        if reasons:
            self._aborted = reasons[0]
        return self._aborted

    def finalize(self) -> tuple[bool, list[str]]:
        """Return existing run_verdict's (continue_ok, reasons), metrics only."""
        self._attachment_locked = True
        self._check_retention()
        return V.run_verdict(self._rows)
