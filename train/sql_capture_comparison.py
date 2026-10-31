"""Read-only quality comparison of caller-declared capture arms.

Recorded equality is not authenticated provenance, causal evidence or approved
reuse attribution. No databases, execution, rescore, providers or artifact writes.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal

from ptc.paired import paired
from train import sql_capture as captures
from train.sql_pilot_assets import read_file

__all__ = [
    "CaptureOutcome", "CaseComparison", "CaptureComparison", "PairedStatistics",
    "compare_capture_files", "format_comparison",
]

OutcomeState = Literal[
    "observed_success", "observed_failure", "missing_capture", "invalid_capture",
    "capture_read_blocked", "invalid_gold", "database_missing", "unscored_abort",
    "infrastructure_abort", "program_rejected",
]
Change = Literal["improvement", "regression", "tie", "unavailable"]
_PAIR_FIELDS = (
    "task_id", "task_fingerprint", "db_sha256", "schema", "prompt", "backend",
    "instrument", "schema_version", "execution_binding", "reporting",
)


@dataclass(frozen=True)
class CaptureOutcome:
    state: OutcomeState
    score: float | None = None
    scorer_status: str | None = None
    budget_refusals: int = 0
    abort_stage: str | None = None
    abort_reason: str | None = None


@dataclass(frozen=True)
class CaseComparison:
    case_id: str
    baseline: CaptureOutcome
    treatment: CaptureOutcome
    refusal_reasons: tuple[str, ...]
    change: Change


@dataclass(frozen=True)
class PairedStatistics:
    n: int
    baseline_successes: int
    treatment_successes: int
    baseline_accuracy: float
    treatment_accuracy: float
    delta: float
    ci: tuple[float, float] | None
    p: float
    treatment_only: int
    baseline_only: int
    ties: int


@dataclass(frozen=True)
class CaptureComparison:
    denominator: int
    cases: tuple[CaseComparison, ...]
    complete: bool
    admissible: bool
    refusal_reasons: tuple[str, ...]
    improvements: tuple[str, ...]
    regressions: tuple[str, ...]
    statistics: PairedStatistics | None


def _arguments(planned, baseline, treatment):
    try:
        if type(planned) is not tuple or not planned:
            raise ValueError
        if any(type(case_id) is not str or not case_id
               or len(case_id.encode("utf-8")) > 256 for case_id in planned):
            raise ValueError
        if len(set(planned)) != len(planned):
            raise ValueError
        for mapping in (baseline, treatment):
            if not isinstance(mapping, Mapping) or any(
                type(key) is not str or key not in planned
                or not isinstance(path, Path) or not path.is_absolute()
                for key, path in mapping.items()
            ):
                raise ValueError
    except (TypeError, ValueError, UnicodeError):
        # No path, case ID, raw artifact or chained exception text.
        raise ValueError("distinct planned IDs and declared absolute capture paths required") from None


def _outcome(capture: captures.SqlCapture) -> CaptureOutcome:
    refusals = len(capture.refusals)
    if capture.execution_abort is not None:
        return CaptureOutcome(
            "infrastructure_abort", budget_refusals=refusals,
            abort_stage=capture.execution_abort.stage,
            abort_reason=capture.execution_abort.reason,
        )
    if capture.terminal_label == "program_rejected":
        return CaptureOutcome("program_rejected", budget_refusals=refusals)
    if capture.terminal_label != "final_submitted" or capture.result is None:
        # V1 abort has no infrastructure/model-cause signal.
        return CaptureOutcome("unscored_abort", budget_refusals=refusals)
    result = capture.result
    if not result.valid:
        state = "database_missing" if result.status == "db_missing" else "invalid_gold"
        return CaptureOutcome(state, scorer_status=result.status,
                              budget_refusals=refusals)
    return CaptureOutcome(
        "observed_success" if result.score == 1 else "observed_failure",
        score=result.score, scorer_status=result.status, budget_refusals=refusals,
    )


def _load(path: Path | None):
    if path is None:
        return None, CaptureOutcome("missing_capture"), None
    try:
        try:
            raw = read_file(path)
        except FileNotFoundError:
            return None, CaptureOutcome("missing_capture"), None
        except OSError:
            # Permission/I/O failure is not evidence of invalid file content.
            return None, CaptureOutcome("capture_read_blocked"), None
        capture = captures.decode_capture(raw)
        if captures.encode_capture(capture) != raw:
            raise ValueError("canonical capture required")
    except (TypeError, ValueError, OverflowError, RecursionError):
        # Never expose artifact content, local paths or decoder exception detail.
        return None, CaptureOutcome("invalid_capture"), None
    return capture, _outcome(capture), hashlib.sha256(raw).digest()


def compare_capture_files(
    planned_case_ids: tuple[str, ...],
    baseline_paths: Mapping[str, Path],
    treatment_paths: Mapping[str, Path],
) -> CaptureComparison:
    """Compare all independently planned cases, never an observed intersection.

    Mappings declare arms only. Missing/invalid evidence retains its planned
    row and refuses ALL aggregate statistics. Reads only explicit capture files.
    """
    _arguments(planned_case_ids, baseline_paths, treatment_paths)
    planned = planned_case_ids
    loaded = {}
    reused = set()
    path_owners = {}
    digest_owners = {}
    for case_id in planned:
        for arm, paths in (("baseline", baseline_paths), ("treatment", treatment_paths)):
            path = paths.get(case_id)
            record = _load(path)
            loaded[case_id, arm] = record
            for key, owners in ((path, path_owners), (record[2], digest_owners)):
                if key is None:
                    continue
                owner = owners.setdefault(key, case_id)
                if owner != case_id:
                    reused.update((owner, case_id))

    rows = []
    for case_id in planned:
        baseline, before, _ = loaded[case_id, "baseline"]
        treatment, after, _ = loaded[case_id, "treatment"]
        reasons = []
        for arm, outcome in (("baseline", before), ("treatment", after)):
            if outcome.score is None:
                reasons.append(f"{arm}_{outcome.state}")
        if baseline is not None and treatment is not None:
            for field in _PAIR_FIELDS:
                if getattr(baseline, field) != getattr(treatment, field):
                    reasons.append(f"{field}_mismatch")
        if case_id in reused:
            reasons.append("capture_reused")
        change: Change = "unavailable"
        if not reasons:
            change = ("improvement" if after.score > before.score else
                      "regression" if after.score < before.score else "tie")
        rows.append(CaseComparison(case_id, before, after, tuple(reasons), change))

    complete = all(row.baseline.score is not None and row.treatment.score is not None
                   for row in rows)
    refusal_reasons = tuple(dict.fromkeys(reason for row in rows
                                         for reason in row.refusal_reasons))
    admissible = complete and not refusal_reasons
    statistics = None
    if admissible:
        baseline_scores = {row.case_id: row.baseline.score for row in rows}
        treatment_scores = {row.case_id: row.treatment.score for row in rows}
        # Existing estimator's delta is a-b: treatment MUST be argument a.
        result = paired(treatment_scores, baseline_scores)
        statistics = PairedStatistics(
            n=result["n"],
            baseline_successes=sum(value == 1 for value in baseline_scores.values()),
            treatment_successes=sum(value == 1 for value in treatment_scores.values()),
            baseline_accuracy=result["mean_b"], treatment_accuracy=result["mean_a"],
            delta=result["delta"], ci=result["ci"], p=result["p"],
            treatment_only=result["a_only"], baseline_only=result["b_only"],
            ties=result["ties"],
        )
    return CaptureComparison(
        len(planned), tuple(rows), complete, admissible, refusal_reasons,
        tuple(row.case_id for row in rows if row.change == "improvement"),
        tuple(row.case_id for row in rows if row.change == "regression"), statistics,
    )


def format_comparison(comparison: CaptureComparison) -> str:
    """Compact safe projection of a returned comparison, never raw captures.

    Caller-owned case IDs are escaped, not secret-redacted; callers must not
    put secrets/PII in those IDs. Not a serializer for arbitrary forged records.
    """
    lines = [
        f"Planned cases: {comparison.denominator}; complete: {comparison.complete}; "
        f"admissible: {comparison.admissible}",
    ]
    for row in comparison.cases:
        lines.append(
            f"{json.dumps(row.case_id, ensure_ascii=True)}: "
            f"baseline={row.baseline.state}; treatment={row.treatment.state}; "
            f"{row.change}"
            + (f"; refused={','.join(row.refusal_reasons)}" if row.refusal_reasons else "")
        )
    stats = comparison.statistics
    if stats is None:
        lines.append("Paired statistics: unavailable")
    else:
        lines.extend((
            f"Baseline EX: {stats.baseline_successes}/{stats.n}; "
            f"treatment EX: {stats.treatment_successes}/{stats.n}",
            f"Paired delta (treatment - baseline): {stats.delta:+.6f}; "
            f"CI: {stats.ci}; p: {stats.p:.6g}",
        ))
    lines.extend((
        "Billing: unavailable",
        "Token usage: unavailable",
        "Model-request latency: unavailable",
        "Approved-reuse attribution: unavailable",
        "Caller-declared arms; authenticated provenance and causal benefit unverified.",
    ))
    return "\n".join(lines)
