"""Private trusted-host orchestration, not a driver or scientific attestation.

ArmRequest contains private tasks. Supply original-compatible real drivers which
own policy-safe projection, request/action budget enforcement and SDK decoding.
Approval is a cooperative host callback, never a digest or billing watchdog.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from verifiers.v1.episode import Episode
from verifiers.v1.trace import Reward, Trace

from bench import paired_bird
from bench.bird_sdk_driver import SqlScoreReceipt
from bench.score import ExResult
from train import sql_capture as captures
from train import sql_capture_comparison as comparisons
from train import sql_episodes as episodes
from train import sql_pilot_assets as assets


class ExperimentAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class ScientificOperation:
    operation_id: str
    gross_budget_usd_micros: int


@dataclass(frozen=True)
class ScientificRequest:
    operation: ScientificOperation
    plan_id: str
    eligible_count: int
    instrument: paired_bird.Instrument
    policy_identity: str
    arms: tuple[str, str] = ("bash", "ptc")
    num_rollouts: int = 1


@dataclass(frozen=True, repr=False)
class CompletedEvidence:
    episode: Episode
    receipt: SqlScoreReceipt
    capture: captures.SqlCapture | None = None


@dataclass(frozen=True)
class ArchivedEvidence:
    arm: str
    ordinal: int
    episode_path: Path
    capture_path: Path | None


@dataclass(frozen=True)
class ExperimentResult:
    paired_result: paired_bird.PairedBirdResult
    archives: tuple[ArchivedEvidence, ...]
    archive_complete: bool
    observed_comparison: paired_bird.Comparison | None
    historical_comparison: comparisons.CaptureComparison | None
    diagnostics: tuple[str, ...]
    scientifically_qualified: bool = False
    scientific_limitations: tuple[str, ...] = (
        "independent_runtime_cohort_authority_unavailable",
        "independent_checkpoint_seed_authority_unavailable",
        "native_learning_qualification_not_established",
    )


def _require(condition):
    if not condition:
        raise ValueError("completed evidence join refused")


def _joined(actual, row, task, databases, policy_identity, seen):
    _require(type(actual) is CompletedEvidence)
    episode, receipt = actual.episode, actual.receipt
    _require(type(episode) is Episode and type(receipt) is SqlScoreReceipt)
    _require(episode.ok is True and episode.errors == []
             and len(episode.traces) == 1)
    trace = episode.traces[0]
    _require(type(trace) is Trace and receipt.trace is trace
             and trace.ok is True and trace.is_completed is True
             and trace.errors == [])
    for value, kind in ((episode.id, "episode"), (trace.id, "trace")):
        _require(type(value) is str and bool(value) and (kind, value) not in seen)
        seen.add((kind, value))
    _require(episode.task.data.name == row.task_id
             and trace.task == episode.task
             and type(row.output_ref) is str
             and row.output_ref.endswith(f"#episode={episode.id}"))
    result = receipt.result
    _require(type(result) is ExResult and result.valid is True
             and type(result.score) in (int, float) and result.score in (0, 1)
             and result.status == row.status
             and (result.status == "match") == (result.score == 1))
    _require(type(trace.rewards) is dict
             and set(trace.rewards) == {"execution_accuracy"})
    reward = trace.rewards["execution_accuracy"]
    _require(type(reward) is Reward and reward.weight == 1.0
             and reward.score == result.score
             and row.metrics == (paired_bird.Metric(
                 "execution_accuracy", result.score),))
    capture = actual.capture
    if row.arm == "ptc":
        _require(type(capture) is captures.SqlCapture)
        raw_capture = captures.encode_capture(capture)
        _require(capture.task_id == task.name and capture.result == result
                 and capture.terminal_label == "final_submitted"
                 and capture.execution_abort is None
                 and capture.ids.episode_id == episode.id
                 and capture.ids.policy_id == policy_identity
                 and capture.task_fingerprint == episodes._fingerprint(
                     episodes._task_payload(task))
                 and capture.db_sha256 == databases[task.db_id])
    else:
        _require(capture is None)
        raw_capture = None
    # These are original SDK/capture formats, not a new joined durable schema.
    raw_episode = assets.canonical_bytes(episode.to_record())
    return raw_episode, raw_capture


def _publish(path, raw):
    assets.write_new(path, raw)
    _require(assets.read_file(path) == raw)


async def run_sql_experiment(
    plan: paired_bird.PairedBirdPlan, *,
    instrument: paired_bird.Instrument,
    policy_identity: str,
    operation: ScientificOperation,
    approve: Callable[[ScientificRequest], bool] | None,
    run_arm: Callable[[paired_bird.ArmRequest],
                      AsyncIterator[paired_bird.TaskOutcome]],
    evidence_for: Callable[[paired_bird.TaskOutcome], CompletedEvidence],
    output_dir: Path,
    historical_baseline: Mapping[str, Path] | None = None,
) -> ExperimentResult:
    """Run once after scientific admission; preserve operational/scientific split.

    Real bindings belong to the SDK/Bash tracks: run_arm returns original decoded
    TaskOutcomes, evidence_for retains original Episode/Trace/EX custody and the
    actual PTC capture. No provider/model fallback, replay or rescore occurs here.
    Original coordinator owns actual supplied iterator finalization and propagates
    primary cancellation unchanged with its partial paired_bird_result attachment.
    """
    if (type(operation) is not ScientificOperation
            or type(operation.operation_id) is not str
            or not operation.operation_id.strip()
            or type(operation.gross_budget_usd_micros) is not int
            or operation.gross_budget_usd_micros <= 0
            or not callable(approve)
            or not callable(run_arm) or not callable(evidence_for)):
        raise ExperimentAdmissionError("explicit scientific operation/budget and host approval required")
    paired_bird._require_plan(plan)
    paired_bird._check_instrument(instrument)
    if type(policy_identity) is not str or not policy_identity.strip():
        raise ExperimentAdmissionError("explicit policy identity required")
    output_dir = assets.safe_path(output_dir)
    request = ScientificRequest(
        operation, plan.plan_id, len(plan.draw.eligible),
        instrument, policy_identity)
    try:
        approved = approve(request)
    except Exception:
        raise ExperimentAdmissionError("scientific admission refused") from None
    if approved is not True:
        raise ExperimentAdmissionError("scientific admission refused")

    try:
        output_dir.mkdir(mode=0o700)
        assets.fsync_dir(output_dir)
        assets.fsync_dir(output_dir.parent)
    except Exception:
        return ExperimentResult(
            paired_bird.adjudicate_paired_bird(plan, (), ()),
            (), False, None, None, ("archive_setup_refused",))

    paired_result = await paired_bird.run_paired_bird(
        plan, run_arm=run_arm, instrument=instrument,
        policy_identity=policy_identity, num_rollouts=1)
    archives, diagnostics, current = [], [], {}
    complete = paired_result.status == "complete"
    try:
        tasks = {task.name: task for task in plan.draw.eligible}
        databases = {database.db_id: database.sha256 for database in plan.draw.databases}
        seen = set()
        for arm, rows in (("bash", paired_result.arm_a), ("ptc", paired_result.arm_b)):
            for ordinal, row in enumerate(rows):
                _require(paired_bird._row_problem(plan, arm, row) is None)
                actual = evidence_for(row)
                raw_episode, raw_capture = _joined(
                    actual, row, tasks[row.task_id], databases, policy_identity, seen)
                episode_path = output_dir / f"{row.arm}-{ordinal:06d}.episode.json"
                _publish(episode_path, raw_episode)
                capture_path = None
                if raw_capture is not None:
                    capture_path = output_dir / f"{row.arm}-{ordinal:06d}.capture.json"
                    _publish(capture_path, raw_capture)
                    current[row.task_id] = capture_path
                archives.append(ArchivedEvidence(
                    row.arm, ordinal, episode_path, capture_path))
    except Exception:
        complete = False
        diagnostics.append("completed_evidence_archive_refused")
    complete = complete and len(archives) == 2 * len(plan.draw.eligible)
    history = None
    if complete and historical_baseline is not None:
        try:
            history = comparisons.compare_capture_files(
                tuple(task.name for task in plan.draw.eligible),
                historical_baseline, current)
        except Exception:
            diagnostics.append("historical_comparison_refused")
    return ExperimentResult(
        paired_result, tuple(archives), complete,
        paired_result.comparison if complete else None,
        history, tuple(diagnostics))


__all__ = [
    "ScientificOperation", "ScientificRequest", "CompletedEvidence",
    "ArchivedEvidence", "ExperimentResult", "ExperimentAdmissionError",
    "run_sql_experiment",
]
