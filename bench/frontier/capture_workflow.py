"""Capture once, publish once, then reload for local byte agreement only."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bench.frontier.sample_capture import CapturedProbe, CaptureSession
from bench.task import SqlTask
from train import frontier_transport as transport
from train.frontier_bindings import BindingLimits, MeasurementPlan

__all__ = ["ArchivedCapture", "capture_to_archive"]


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class ArchivedCapture:
    """Frozen shell only; captured legacy ProbeResult remains mutable."""

    captured: CapturedProbe
    archive_sha256: str
    reloaded: transport.TransportedBindings


def capture_to_archive(
    *,
    plan: MeasurementPlan,
    checkpoint_inventory: bytes,
    limits: BindingLimits,
    root: Path | str,
    draw_path: Path | str,
    supplement_path: Path | str,
    expected_draw_sha256: str,
    expected_supplement_sha256: str,
    fixture: bool,
    generate: Callable[[SqlTask], str],
    output_path: Path | str,
) -> ArchivedCapture:
    # Observation, not a lease; the writer still owns create-only publication.
    transport._precheck_output(output_path)
    session = CaptureSession(plan, checkpoint_inventory, limits=limits)
    captured = session.run(
        root, draw_path, supplement_path, generate,
        expected_draw_sha256=expected_draw_sha256,
        expected_supplement_sha256=expected_supplement_sha256, fixture=fixture)
    archive_sha256 = transport.write_unverified_bindings(
        captured.batch.plan, captured.retention_pins, captured.batch,
        output_path, limits=limits)
    reloaded = transport.load_unverified_bindings(
        output_path, expected_archive_sha256=archive_sha256, limits=limits)
    return ArchivedCapture(captured, archive_sha256, reloaded)
