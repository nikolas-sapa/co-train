"""In-memory RUN metric health, not proof of training or checkpoint completion."""

from __future__ import annotations

from copy import deepcopy

from train import verdict as V


class RunMonitor:
    """Latch the first RUN criterion or required-telemetry failure.

    Only rows containing the exact ``loss`` key count as logged steps. Healthy
    accumulation below ten steps is not an abort; final adjudication still
    refuses short histories. No trainer, callback, persistence or completion
    authority lives here.
    """

    __slots__ = ("_rows", "_aborted")

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._aborted: str | None = None

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
        self._rows.append(deepcopy(log))
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
        return V.run_verdict(self._rows)
