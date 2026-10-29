"""Caller-owned files around existing SQL skill authority, never self-approval.

Trusted evaluator/assets/storage and externally retained pins remain required.
Passing executor=None deliberately retains the existing in-process limitations.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from bench.task import SqlTask
from ptc.sql_isolation import PilotExecutor
from train import sql_capture as capture
from train import sql_episodes as evidence
from train import sql_pilot_assets as assets
from train import sql_skill_eval as evaluator
from train import sql_skills as skills

__all__ = [
    "QualificationFiles", "create_candidate_file", "qualify_candidate_files",
    "reuse_approved_files",
]

_Record = TypeVar("_Record")


@dataclass(frozen=True)
class QualificationFiles:
    """Written evidence and optional UNAPPROVED qualification receipt."""

    capture_paths: tuple[Path, ...]
    promotion_path: Path | None


def _load(path: Path, decode: Callable[[bytes], _Record],
          encode: Callable[[_Record], bytes]) -> _Record:
    raw = assets.read_file(path)
    record = decode(raw)
    if encode(record) != raw:
        raise ValueError("canonical artifact bytes required")
    return record


def _output_path(output_dir: Path) -> Path:
    assets.safe_path(output_dir)
    assets.safe_path(output_dir.parent, exists=True, directory=True)
    if output_dir.exists():
        raise FileExistsError("workflow requires a new output directory")
    return output_dir


def _new_directory(output_dir: Path) -> None:
    _output_path(output_dir)
    output_dir.mkdir(mode=0o700)
    assets.fsync_dir(output_dir.parent)


def _case_path(case: evaluator.SkillCase) -> None:
    evaluator._validate_case(case)
    assets.safe_path(Path(case.task.db_path), exists=True)


def _exception_capture(output_dir: Path, exc: capture.CaptureError) -> None:
    # Only real typed evidence. Never turn arbitrary exceptions into captures.
    assets.write_new(output_dir / "exception-capture.json",
                     capture.encode_capture(exc.capture))


def create_candidate_file(
    source_capture: capture.SqlCapture, *, source_task: SqlTask,
    source_ids: evidence.EpisodeIds, skill_id: str, program: str,
    output_dir: Path,
) -> Path:
    """Data-only candidate creation, not a source rescore or approval."""
    _output_path(output_dir)
    candidate = skills.create_candidate(
        source_capture, source_task=source_task, source_ids=source_ids,
        skill_id=skill_id, program=program,
    )
    raw = skills.encode_candidate(candidate)
    _new_directory(output_dir)
    path = output_dir / "candidate.json"
    assets.write_new(path, raw)
    return path


def qualify_candidate_files(
    candidate_path: Path, source_capture_path: Path, *,
    expected_source_capture_sha256: str, source_case: evaluator.SkillCase,
    qualification_cases: tuple[evaluator.SkillCase, ...], ids: evidence.EpisodeIds,
    output_dir: Path, allow_execution: bool = False,
    executor: PilotExecutor | None = None,
) -> QualificationFiles:
    """Persist qualification evidence; an emitted receipt is NOT approval."""
    evaluator._opt_in(allow_execution)
    _output_path(output_dir)
    candidate = _load(candidate_path, skills.decode_candidate, skills.encode_candidate)
    source = _load(source_capture_path, capture.decode_capture, capture.encode_capture)
    _case_path(source_case)
    if type(qualification_cases) is not tuple:
        raise TypeError("qualification_cases must be an external tuple")
    for case in qualification_cases:
        _case_path(case)
    # Reuse existing data/snapshot admission before even the source rescore.
    evaluator._admit_qualifications(candidate, qualification_cases)
    _new_directory(output_dir)
    try:
        promotion, actual = evaluator.promote_candidate(
            candidate, source_capture=source,
            expected_source_capture_sha256=expected_source_capture_sha256,
            source_case=source_case, qualification_cases=qualification_cases,
            ids=ids, allow_execution=allow_execution, executor=executor,
        )
    except capture.CaptureError as exc:
        _exception_capture(output_dir, exc)
        raise
    paths = []
    for n, item in enumerate(actual, 1):
        path = output_dir / f"qualification-{n}.json"
        assets.write_new(path, capture.encode_capture(item))
        paths.append(path)
    promotion_path = None
    if promotion is not None:
        # All captures must persist first. Pending files are never authority.
        pending = output_dir / ".promotion.pending"
        assets.write_new(pending, skills.encode_promotion(promotion))
        promotion_path = output_dir / "promotion.json"
        # This exclusively created, trusted directory has no other writers.
        os.rename(pending, promotion_path)
        assets.fsync_dir(output_dir)
    return QualificationFiles(tuple(paths), promotion_path)


def reuse_approved_files(
    candidate_path: Path, promotion_path: Path, case: evaluator.SkillCase, *,
    expected_promotion_sha256: str, ids: evidence.EpisodeIds, output_dir: Path,
    allow_execution: bool = False, executor: PilotExecutor | None = None,
) -> Path:
    """Use explicit external approval, without opening historical databases."""
    evaluator._opt_in(allow_execution)
    _output_path(output_dir)
    candidate = _load(candidate_path, skills.decode_candidate, skills.encode_candidate)
    promotion = _load(promotion_path, skills.decode_promotion, skills.encode_promotion)
    _case_path(case)
    _new_directory(output_dir)
    try:
        actual = evaluator.reuse_promoted(
            candidate, promotion, case,
            expected_promotion_sha256=expected_promotion_sha256,
            ids=ids, allow_execution=allow_execution, executor=executor,
        )
    except capture.CaptureError as exc:
        _exception_capture(output_dir, exc)
        raise
    path = output_dir / "reuse.json"
    assets.write_new(path, capture.encode_capture(actual))
    return path
