"""Read-only descriptive arithmetic on UNVERIFIED numeric declarations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Literal

from bench.frontier.probe import dead_group_fraction
from train.frontier_bindings import BindingLimits, BindingReport
from train.frontier_transport import load_unverified_bindings

__all__ = [
    "ArchiveTaskReport", "ArchiveReport", "read_archive_report",
    "render_archive_report",
]


@dataclass(frozen=True, slots=True, repr=False)
class ArchiveTaskReport:
    task_ordinal: int
    state: Literal["complete", "excluded", "missing", "invalid"]
    solve_rate: float | None
    dead_fraction: float | None
    retained: bool | None


@dataclass(frozen=True, slots=True, repr=False)
class ArchiveReport:
    tasks: tuple[ArchiveTaskReport, ...]
    binding_report: BindingReport
    g: int
    dead_ceiling: float | int
    n_complete_tasks: int
    n_retained_tasks: int
    retention: float | None

    @property
    def provenance(self) -> str:
        return "unverified"

    @property
    def attested_facts(self) -> tuple:
        return ()

    @property
    def genuine_measurement_accepted(self) -> bool:
        return False

    @property
    def training_authorized(self) -> bool:
        return False


def read_archive_report(
    path: Path | str,
    *,
    expected_archive_sha256: str,
    limits: BindingLimits,
    dead_ceiling: float | int,
) -> ArchiveReport:
    if (type(dead_ceiling) not in (int, float)
            or not 0 < dead_ceiling < 1 or not math.isfinite(dead_ceiling)):
        raise ValueError("dead_ceiling must be a finite number in (0, 1)")
    loaded = load_unverified_bindings(
        path, expected_archive_sha256=expected_archive_sha256, limits=limits)
    plan, binding = loaded.plan, loaded.report
    samples = {(sample.task_id, sample.slot_index): sample
               for sample in loaded.batch.samples}
    slots = {(slot.task_ordinal, slot.slot_index): slot for slot in binding.slots}
    eligible = set(plan.eligible_ids)
    rows = []
    complete = retained = 0
    for ordinal, task in enumerate(plan.tasks):
        if task.task_id not in eligible:
            rows.append(ArchiveTaskReport(ordinal, "excluded", None, None, None))
            continue
        group = tuple(slots.get((ordinal, index)) for index in range(plan.g))
        # Present invalid declarations outrank absence; neither supplies a rate.
        invalid = any(
            slot is not None and slot.disposition != "missing"
            and (not slot.bindings_consistent or not slot.validly_scored)
            for slot in group)
        missing = any(slot is None or slot.disposition == "missing" for slot in group)
        if invalid:
            rows.append(ArchiveTaskReport(ordinal, "invalid", None, None, None))
        elif missing:
            rows.append(ArchiveTaskReport(ordinal, "missing", None, None, None))
        else:
            successes = sum(samples[(task.task_id, index)].score == 1
                            for index in range(plan.g))
            rate = successes / plan.g
            fraction = dead_group_fraction(rate, plan.g)
            keep = fraction <= dead_ceiling
            rows.append(ArchiveTaskReport(ordinal, "complete", rate, fraction, keep))
            complete += 1
            retained += int(keep)
    retention = (retained / binding.eligible_tasks
                 if binding.eligible_tasks and complete == binding.eligible_tasks
                 else None)
    return ArchiveReport(
        tuple(rows), binding, plan.g, dead_ceiling, complete, retained, retention)


def _rate_text(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.6g}"


def render_archive_report(report: ArchiveReport) -> str:
    binding = report.binding_report
    lines = [
        "UNVERIFIED descriptive archive report, declarations-only.",
        "Numeric declarations are not authenticated against opaque scoring payloads.",
        "Not authentic measurement, scientific qualification or training authorization.",
        f"planned_tasks={binding.planned_tasks:d} eligible_tasks={binding.eligible_tasks:d} "
        f"excluded_tasks={binding.excluded_tasks:d}",
        f"scheduled_slots={binding.scheduled_slots:d} observed_slots={binding.observed_slots:d} "
        f"binding_issues={binding.total_issues:d}",
        f"g={report.g:d} dead_ceiling={report.dead_ceiling:.6g} "
        f"complete_tasks={report.n_complete_tasks:d} "
        f"retained_tasks={report.n_retained_tasks:d} retention={_rate_text(report.retention)}",
    ]
    states = {
        "complete": "complete", "excluded": "excluded",
        "missing": "missing", "invalid": "invalid",
    }
    for row in report.tasks:
        decision = ("unavailable" if row.retained is None
                    else "true" if row.retained else "false")
        lines.append(
            f"task_ordinal={row.task_ordinal:d} state={states[row.state]} "
            f"solve_rate={_rate_text(row.solve_rate)} "
            f"dead_fraction={_rate_text(row.dead_fraction)} retained={decision}")
    return "\n".join(lines)
