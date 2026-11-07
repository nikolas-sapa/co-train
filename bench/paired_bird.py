"""One-rollout paired BIRD coordination over an actually admitted retained draw.

The async-iterator driver is TRUSTED HOST code. Requests contain private tasks,
including oracle SQL and DB paths, not policy-safe model inputs. Instrument and
policy identities are declarations, not authentication or proof of enforcement.
No SDK, acquisition, retries, output writer, model selection or durable schema.
"""

from __future__ import annotations

import asyncio
import math
import threading
import uuid
import weakref
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from bench import prepare
from bench.prepare import DrawDatabase, DrawExclusion, ValidatedDraw
from bench.task import SqlTask
from ptc.paired import paired
from ptc.sql_arms import Budget


class PairedBirdError(ValueError):
    """Unsupported arguments, unadmitted plan or attempted plan reuse."""


@dataclass(frozen=True, eq=False)
class PairedBirdPlan:
    """Identity-scoped authority, issued only by prepare_paired_bird.

    Constructing/replacing/copying this record does not admit a plan. Admission
    and consumption live outside the frozen record and expire with its lifetime.
    This is an in-process host contract, not a hostile-Python security boundary.
    """

    plan_id: str
    draw: ValidatedDraw


@dataclass(frozen=True)
class Instrument:
    identity: str
    budget: Budget
    action_max_rows: int
    query_timeout_s: float
    sampling_identity: str


@dataclass(frozen=True)
class ArmRequest:
    plan_id: str
    arm: str
    tasks: tuple[SqlTask, ...]
    instrument: Instrument
    policy_identity: str
    num_rollouts: int


def _scalar(value):
    return type(value) in (str, int, float, bool, type(None))


@dataclass(frozen=True)
class Metric:
    name: str
    score: float

    def __post_init__(self):
        # Retain malformed scalar metrics for fail-closed adjudication, but
        # never allow a mutable payload inside an immutable diagnostic result.
        if not _scalar(self.name) or not _scalar(self.score):
            raise PairedBirdError("metric fields must be immutable scalars")


@dataclass(frozen=True)
class TaskOutcome:
    plan_id: str
    arm: str
    task_id: str
    completed: bool
    valid: bool
    status: str
    metrics: tuple[Metric, ...]
    output_ref: str | None

    def __post_init__(self):
        if (not all(_scalar(v) for v in (
                self.plan_id, self.arm, self.task_id, self.completed,
                self.valid, self.status, self.output_ref))
                or type(self.metrics) is not tuple
                or any(type(m) is not Metric for m in self.metrics)):
            raise PairedBirdError("outcome fields must be immutable records/scalars")


@dataclass(frozen=True)
class Comparison:
    n: int
    mean_a: float
    mean_b: float
    delta: float
    ci: tuple[float, float] | None
    a_only: int
    b_only: int
    ties: int
    p: float


@dataclass(frozen=True)
class Disclosure:
    planned: int
    eligible: int
    excluded: int
    measured_a: int
    measured_b: int
    exclusions: tuple[DrawExclusion, ...]
    databases: tuple[DrawDatabase, ...]
    shapes_planned: tuple[int, int]
    shapes_eligible: tuple[int, int]
    tier_limitation: str


@dataclass(frozen=True)
class PairedBirdResult:
    status: str
    comparison: Comparison | None
    arm_a: tuple[TaskOutcome, ...]
    arm_b: tuple[TaskOutcome, ...]
    diagnostics: tuple[str, ...]
    disclosure: Disclosure
    fixture: bool
    measurement: bool
    cost: None = None
    usage: None = None


# Weak, identity-keyed authority prevents copied/constructed draws or plans
# gaining authority, without retaining every old task/database forever.
# Values are (consumed, terminal diagnostics), accessed only under the lock.
_admissions: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_admission_lock = threading.Lock()


def prepare_paired_bird(
    root, draw_path, supplement_path, *,
    expected_draw_sha256, expected_supplement_sha256, fixture=False,
) -> PairedBirdPlan:
    draw = prepare.load_validated_draw(
        root, draw_path, supplement_path,
        expected_draw_sha256=expected_draw_sha256,
        expected_supplement_sha256=expected_supplement_sha256, fixture=fixture)
    plan = PairedBirdPlan(uuid.uuid4().hex, draw)
    with _admission_lock:
        _admissions[plan] = (False, ())
    return plan


def _require_plan(plan, *, consume=False):
    with _admission_lock:
        if type(plan) is not PairedBirdPlan or plan not in _admissions:
            raise PairedBirdError("plan requires actual retained-draw admission")
        consumed, terminal = _admissions[plan]
        if consume:
            if consumed:
                raise PairedBirdError("plan consumed: single-use dispatch only")
            _admissions[plan] = (True, terminal)
        return terminal


def _mark_terminal(plan, diagnostic):
    with _admission_lock:
        consumed, terminal = _admissions[plan]
        if diagnostic not in terminal:
            _admissions[plan] = (consumed, terminal + (diagnostic,))


def _positive_finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _identity(value):
    return type(value) is str and bool(value.strip())


def _check_instrument(instrument):
    if type(instrument) is not Instrument:
        raise PairedBirdError("instrument must be an immutable Instrument")
    budget = instrument.budget
    if (not _identity(instrument.identity)
            or not _identity(instrument.sampling_identity)
            or type(instrument.action_max_rows) is not int
            or instrument.action_max_rows <= 0
            or not _positive_finite(instrument.query_timeout_s)
            or type(budget) is not Budget
            or type(budget.max_turns) is not int or budget.max_turns <= 0
            or type(budget.max_retries) is not int or budget.max_retries != 0
            or type(budget.retry_on) is not tuple or budget.retry_on != ()
            or not _positive_finite(budget.rollout_timeout)
            or not _positive_finite(budget.program_timeout)):
        raise PairedBirdError(
            "instrument requires exact types, finite positive caps and zero retries")


def _score(row):
    if type(row.metrics) is not tuple or any(
            type(m) is not Metric or type(m.name) is not str
            for m in row.metrics):
        return None
    components = [m for m in row.metrics if m.name == "execution_accuracy"]
    if len(components) != 1:
        return None
    value = components[0].score
    if type(value) not in (int, float) or value not in (0, 1):
        return None
    return float(value)


def _row_problem(plan, arm, row):
    if type(row) is not TaskOutcome:
        return "outcome_type"
    if (type(row.plan_id) is not str or row.plan_id != plan.plan_id
            or type(row.arm) is not str or row.arm != arm
            or type(row.task_id) is not str):
        return "outcome_association"
    if row.completed is not True or row.valid is not True:
        return "incomplete_or_invalid"
    # These are the current real scorer's valid outcomes, not driver exit codes.
    if type(row.status) is not str or row.status not in (
            "match", "mismatch", "pred_empty", "pred_error",
            "pred_timeout", "pred_truncated"):
        return "unexpected_status"
    if not _identity(row.output_ref):
        return "missing_output"
    score = _score(row)
    if score is None:
        return "invalid_execution_accuracy"
    # A status cannot claim success while reporting wrong SQL, or vice versa.
    if (row.status == "match") != (score == 1.0):
        return "status_metric_conflict"
    return None


def _arm_scores(plan, arm, rows):
    scores, diagnostics = {}, []
    expected = {t.name for t in plan.draw.eligible}
    for index, row in enumerate(rows):
        problem = _row_problem(plan, arm, row)
        if problem is None and row.task_id not in expected:
            problem = "outcome_association"
        if problem is not None:
            # Never interpolate driver fields, exception text, SQL or paths.
            diagnostics.append(f"{arm}:row[{index}]:{problem}")
            continue
        if row.task_id in scores:
            diagnostics.append(f"{arm}:row[{index}]:duplicate_task")
            continue
        scores[row.task_id] = _score(row)
    if len(expected) != len(plan.draw.eligible):
        diagnostics.append("admitted_duplicate_task")
    if (tuple(scores) != tuple(t.name for t in plan.draw.eligible)
            or len(rows) != len(expected)):
        diagnostics.append(f"{arm}:eligible_coverage_mismatch")
    return scores, diagnostics


def _shapes(tasks):
    return len({t.shape for t in tasks}), len({t.coarse_shape for t in tasks})


def _result(plan, arm_a, arm_b):
    a, da = _arm_scores(plan, "bash", arm_a)
    b, db = _arm_scores(plan, "ptc", arm_b)
    diagnostics = _require_plan(plan) + tuple(da) + tuple(db)
    comparison = None
    if not diagnostics:
        estimate = paired(a, b)
        comparison = Comparison(**{key: estimate[key] for key in (
            "n", "mean_a", "mean_b", "delta", "ci", "a_only", "b_only", "ties", "p")})
    draw = plan.draw
    disclosure = Disclosure(
        len(draw.planned), len(draw.eligible), len(draw.exclusions),
        len(a), len(b), draw.exclusions, draw.databases,
        _shapes(draw.planned), _shapes(draw.eligible),
        "BIRD has three difficulty tiers; the existing tier helper collapses "
        "them into two buckets. This comparison is marginal, not a tier interaction.")
    return PairedBirdResult(
        "complete" if comparison is not None else "void", comparison,
        arm_a, arm_b, diagnostics, disclosure, draw.fixture, False)


def adjudicate_paired_bird(plan, arm_a, arm_b) -> PairedBirdResult:
    """Re-adjudicate without dispatch authority or erasing terminal failures."""
    _require_plan(plan)
    if (type(arm_a) is not tuple or type(arm_b) is not tuple
            or any(type(row) is not TaskOutcome for row in arm_a + arm_b)):
        raise PairedBirdError("outcomes must be immutable TaskOutcome tuples")
    return _result(plan, arm_a, arm_b)


async def _run_arm(plan, request, run_arm, rows, closing):
    """One task/context owns driver creation, advancement and finalization."""
    iterator, cancellation = None, None
    arm = request.arm
    try:
        iterator = aiter(run_arm(request))
        async for row in iterator:
            if len(rows) == len(request.tasks):
                _mark_terminal(plan, f"{arm}:outcome_overflow")
                break
            if type(row) is not TaskOutcome:
                raise PairedBirdError("driver yielded a non-outcome")
            rows.append(row)
    except asyncio.CancelledError as exc:
        cancellation = exc
        _mark_terminal(plan, f"{arm}:cancelled")
    except Exception:
        _mark_terminal(plan, f"{arm}:driver_failure")
    finally:
        closing.set()
        if iterator is not None:
            try:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            except asyncio.CancelledError as exc:
                if cancellation is None:
                    cancellation = exc
                _mark_terminal(plan, f"{arm}:cancelled")
                _mark_terminal(plan, f"{arm}:cleanup_failure")
            except Exception:
                _mark_terminal(plan, f"{arm}:cleanup_failure")
    # Return, rather than raise, actual driver-owned cancellation so Task's
    # cancelled-state exception extraction cannot replace its identity.
    return cancellation


async def run_paired_bird(
    plan, *, run_arm: Callable[[ArmRequest], AsyncIterator[TaskOutcome]],
    instrument, policy_identity, num_rollouts,
) -> PairedBirdResult:
    """Consume once, bash then PTC, preserve yielded rows on later failure.

    Driver failure stops dispatch, produces a void result and never retries.
    Cancellation propagates with an immutable `paired_bird_result` attachment.
    Retain at most admitted N rows per arm; the N+1st yield voids the plan.
    One retained task per arm owns its complete iterator lifecycle. Join it
    through repeated cancellation before returning. Trusted drivers must finish
    cleanup and enforce their declared budgets; this is not hostile callback
    containment or a model measurement.
    """
    _require_plan(plan)
    _check_instrument(instrument)
    if not _identity(policy_identity):
        raise PairedBirdError("policy identity must be a nonempty exact str")
    if type(num_rollouts) is not int or num_rollouts != 1:
        raise PairedBirdError("exactly one rollout per task/arm is supported")
    if not callable(run_arm):
        raise PairedBirdError("run_arm must be a trusted async-iterator driver")
    _require_plan(plan, consume=True)
    arms = ([], [])
    for arm, rows in zip(("bash", "ptc"), arms, strict=True):
        request = ArmRequest(
            plan.plan_id, arm, plan.draw.eligible, instrument,
            policy_identity, num_rollouts)
        closing = asyncio.Event()
        settled = asyncio.get_running_loop().create_future()

        def owner_done(_owner, completion=settled):
            if not completion.done():
                completion.set_result(None)

        owner = asyncio.create_task(_run_arm(plan, request, run_arm, rows, closing))
        owner.add_done_callback(owner_done)
        cancellation = None
        while not owner.done():
            try:
                # Owner cancellation/failure completes this signal normally.
                # Only a real caller interruption raises here, including one
                # already pending on entry. No cancellation-count inference or
                # repeated await of a terminal cancelled Task is needed.
                await asyncio.shield(settled)
            except asyncio.CancelledError as exc:
                if cancellation is None:
                    cancellation = exc
                    # Deliver at most once. If finalization already started,
                    # join it without injecting cancellation into its awaits.
                    if not closing.is_set() and not owner.done():
                        owner.cancel(exc.args[0] if exc.args else None)
                _mark_terminal(plan, f"{arm}:cancelled")
        if owner.cancelled():
            _mark_terminal(plan, f"{arm}:cleanup_failure")
        else:
            try:
                owner_cancel = owner.result()
                if cancellation is None:
                    cancellation = owner_cancel
            except Exception:
                _mark_terminal(plan, f"{arm}:cleanup_failure")
        if cancellation is not None:
            cancellation.paired_bird_result = _result(
                plan, tuple(arms[0]), tuple(arms[1]))
            raise cancellation
        if _require_plan(plan):
            return _result(plan, tuple(arms[0]), tuple(arms[1]))
    return _result(plan, tuple(arms[0]), tuple(arms[1]))
