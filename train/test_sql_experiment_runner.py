"""Synthetic, offline fixtures. Parent owns all execution and RED controls."""
import asyncio
from dataclasses import replace

import pytest
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.episode import Episode
from verifiers.v1.task import TaskData, task_key
from verifiers.v1.trace import AgentInfo, Reward, Trace, TraceTask, VersionInfo

from bench import paired_bird
from bench.bird_sdk_driver import SqlScoreReceipt
from bench.score import ExResult
from bench.test_paired_bird import _instrument, _outcome, _plan
from train import sql_capture, sql_capture_comparison, sql_experiment_runner as runner
from train.sql_episodes import EpisodeIds


class SyntheticExperiment:
    def __init__(self, tmp_path):
        self.plan = _plan(tmp_path)
        self.instrument = _instrument(paired_bird)
        self.output = tmp_path.resolve() / "observed"
        self.calls, self.evidence_calls, self.approvals = [], [], []
        self.records = {}
        self.fault = None

    def approve(self, request):
        self.approvals.append(request)
        assert self.calls == []
        return True

    async def driver(self, request):
        self.calls.append(request)
        rows = []
        for index, task in enumerate(request.tasks):
            row = _outcome(paired_bird, request, task)
            data = TaskData(name=task.name, prompt="synthetic public question")
            key = task_key(data.model_dump(mode="json", exclude_none=True))
            public = TraceTask(type="SyntheticSqlTask", data=data, key=key, hash=key)
            trace = Trace(
                task=public, agent=AgentInfo(config=AgentConfig()),
                verifiers=VersionInfo(version="synthetic-offline"),
                ok=True, is_completed=True,
                rewards={"execution_accuracy": Reward(score=1.0)},
            )
            episode = Episode(task=public, traces=[trace], ok=True)
            row = replace(row, output_ref=f"memory:synthetic/{row.arm}#episode={episode.id}")
            receipt = SqlScoreReceipt(
                trace, ExResult(score=1.0, valid=True, status="match"))
            capture = None
            if request.arm == "ptc":
                ids = EpisodeIds("synthetic", "dev", "run", episode.id,
                                 request.policy_identity, "synthetic-revision")
                session = sql_capture.start_capture(
                    task, ids=ids, allow_execution=True)
                capture = session.finish(task.gold_sql)
                assert capture.result.score == 1.0
                receipt = SqlScoreReceipt(trace, capture.result)
            self.records[row.arm, row.task_id] = runner.CompletedEvidence(
                episode, receipt, capture)
            rows.append(row)
        if request.arm == "bash":
            if self.fault == "remove":
                rows.pop()
            elif self.fault == "duplicate":
                rows[1] = rows[0]
            elif self.fault == "reverse":
                rows.reverse()
        for row in rows:
            yield row

    def evidence(self, row):
        self.evidence_calls.append(row)
        return self.records[row.arm, row.task_id]

    def run(self, **changes):
        arguments = dict(
            plan=self.plan, instrument=self.instrument,
            policy_identity="synthetic-policy",
            operation=runner.ScientificOperation("synthetic-operation", 100),
            approve=self.approve, run_arm=self.driver,
            evidence_for=self.evidence, output_dir=self.output,
        )
        arguments.update(changes)
        return asyncio.run(runner.run_sql_experiment(**arguments))


def test_original_callpath_and_complete_archive(tmp_path, monkeypatch):
    case = SyntheticExperiment(tmp_path)
    original = paired_bird.run_paired_bird
    original_fsync = runner.assets.fsync_dir
    calls, synced = [], []

    def fsync(path):
        synced.append(path)
        return original_fsync(path)

    async def delegated(plan, **kwargs):
        assert case.output.is_dir()
        assert case.output.stat().st_mode & 0o777 == 0o700
        assert synced == [case.output, case.output.parent]
        calls.append(kwargs)
        return await original(plan, **kwargs)

    monkeypatch.setattr(runner.assets, "fsync_dir", fsync)
    monkeypatch.setattr(paired_bird, "run_paired_bird", delegated)
    result = case.run()
    assert len(calls) == 1 and calls[0]["run_arm"] == case.driver
    assert calls[0]["num_rollouts"] == 1
    assert [request.arm for request in case.calls] == ["bash", "ptc"]
    assert all(request.tasks is case.plan.draw.eligible for request in case.calls)
    assert len(case.evidence_calls) == len(result.archives) == 14
    assert result.archive_complete
    assert result.observed_comparison is result.paired_result.comparison
    assert result.observed_comparison.n == 7
    assert sum(item.capture_path is not None for item in result.archives) == 7
    for item in result.archives:
        assert item.episode_path.is_file()
        if item.capture_path is not None:
            actual = sql_capture.decode_capture(item.capture_path.read_bytes())
            assert actual.result.valid is True
    assert result.historical_comparison is None
    assert result.scientifically_qualified is False


@pytest.mark.parametrize("fault", [
    "missing_parent", "occupied_file", "occupied_directory", "file_parent",
    "permission", "directory_fsync", "parent_fsync",
])
def test_archive_setup_failure_zero_calls(tmp_path, monkeypatch, fault):
    case = SyntheticExperiment(tmp_path)
    if fault == "missing_parent":
        case.output = tmp_path.resolve() / "missing" / "observed"
    elif fault == "occupied_file":
        case.output.write_bytes(b"retained occupied archive")
    elif fault == "occupied_directory":
        case.output.mkdir()
    elif fault == "file_parent":
        parent = tmp_path.resolve() / "not-a-directory"
        parent.write_bytes(b"retained parent")
        case.output = parent / "observed"
    elif fault == "permission":
        original_mkdir = type(case.output).mkdir

        def mkdir(path, *args, **kwargs):
            if path == case.output:
                raise PermissionError("PRIVATE_SETUP_CANARY")
            return original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(type(case.output), "mkdir", mkdir)
    else:
        original_fsync = runner.assets.fsync_dir
        failed_path = (case.output if fault == "directory_fsync"
                       else case.output.parent)

        def fsync(path):
            if path == failed_path:
                raise OSError("PRIVATE_SETUP_CANARY")
            return original_fsync(path)

        monkeypatch.setattr(runner.assets, "fsync_dir", fsync)

    dispatches = []

    async def forbidden_dispatch(*args, **kwargs):
        dispatches.append(True)
        raise AssertionError("coordinator must not dispatch")

    monkeypatch.setattr(paired_bird, "run_paired_bird", forbidden_dispatch)
    result = case.run()
    assert dispatches == case.calls == case.evidence_calls == []
    assert len(case.approvals) == 1
    assert paired_bird._admissions[case.plan] == (False, ())
    assert result.archives == ()
    assert result.archive_complete is False
    assert result.observed_comparison is result.historical_comparison is None
    assert result.scientifically_qualified is False
    assert result.paired_result.status == "void"
    assert result.paired_result.comparison is None
    assert result.paired_result.arm_a == result.paired_result.arm_b == ()
    assert result.diagnostics == ("archive_setup_refused",)
    assert "PRIVATE_SETUP_CANARY" not in repr(result)
    if fault == "occupied_file":
        assert case.output.read_bytes() == b"retained occupied archive"
    elif fault in ("occupied_directory", "directory_fsync", "parent_fsync"):
        assert case.output.is_dir()
        assert list(case.output.iterdir()) == []
    else:
        assert not case.output.exists()
        if fault == "missing_parent":
            assert not case.output.parent.exists()
        elif fault == "file_parent":
            assert case.output.parent.read_bytes() == b"retained parent"


@pytest.mark.parametrize("approval", [None, False, 1, {"approved": True}])
def test_absent_refused_or_nonliteral_approval_zero_calls(tmp_path, approval):
    case = SyntheticExperiment(tmp_path)
    approve = None if approval is None else lambda request: approval
    with pytest.raises(runner.ExperimentAdmissionError):
        case.run(approve=approve)
    assert case.calls == case.evidence_calls == []
    assert not case.output.exists()


@pytest.mark.parametrize("budget", [None, 0, -1, True, 1.0])
def test_explicit_scientific_budget_required(tmp_path, budget):
    case = SyntheticExperiment(tmp_path)
    with pytest.raises(runner.ExperimentAdmissionError):
        case.run(operation=runner.ScientificOperation("synthetic", budget))
    assert case.calls == case.approvals == []


def test_approval_exception_zero_calls_and_private_detail_suppressed(tmp_path):
    case = SyntheticExperiment(tmp_path)

    def approve(request):
        raise ValueError("PRIVATE_APPROVAL_CANARY")

    with pytest.raises(runner.ExperimentAdmissionError) as caught:
        case.run(approve=approve)
    assert "PRIVATE_APPROVAL_CANARY" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert case.calls == case.evidence_calls == []


@pytest.mark.parametrize("fault", ["remove", "duplicate", "reverse"])
def test_coverage_rejected(tmp_path, fault):
    case = SyntheticExperiment(tmp_path)
    case.fault = fault
    result = case.run()
    assert result.paired_result.status == "void"
    assert result.paired_result.disclosure.eligible == 7
    assert result.observed_comparison is None
    assert not result.archive_complete


@pytest.mark.parametrize("fault", [
    "receipt_trace", "foreign_task", "duplicate_episode",
    "missing_capture", "wrong_output_reference",
])
def test_join_faults_rejected(tmp_path, fault):
    case = SyntheticExperiment(tmp_path)

    def evidence(row):
        actual = case.evidence(row)
        if fault == "receipt_trace":
            return replace(actual, receipt=SqlScoreReceipt(
                actual.receipt.trace.model_copy(deep=True), actual.receipt.result))
        if fault == "foreign_task":
            actual.episode.task = actual.episode.task.model_copy(
                update={"data": TaskData(name="foreign")})
        if fault == "wrong_output_reference":
            actual.episode.id = "different-episode"
        if fault == "duplicate_episode":
            return next(iter(case.records.values()))
        if fault == "missing_capture":
            return replace(actual, capture=None)
        return actual

    result = case.run(evidence_for=evidence)
    assert result.paired_result.status == "complete"
    assert not result.archive_complete
    assert result.observed_comparison is None
    assert not result.scientifically_qualified


@pytest.mark.parametrize("valid", [False, True], ids=["invalid", "valid"])
def test_ex_zero_validity(tmp_path, valid):
    case = SyntheticExperiment(tmp_path)

    async def driver(request):
        async for row in case.driver(request):
            if row.arm == "bash":
                row = replace(row, status="mismatch",
                              metrics=(paired_bird.Metric("execution_accuracy", 0.0),))
            yield row

    def evidence(row):
        actual = case.evidence(row)
        if row.arm == "bash":
            trace = actual.episode.traces[0]
            trace.rewards["execution_accuracy"] = Reward(score=0.0)
            return replace(actual, receipt=SqlScoreReceipt(
                trace, ExResult(score=0.0, valid=valid, status="mismatch")))
        return actual

    result = case.run(evidence_for=evidence, run_arm=driver)
    assert result.paired_result.status == "complete"
    assert result.archive_complete is valid
    assert result.scientifically_qualified is False
    if valid:
        assert len(result.archives) == len(case.evidence_calls) == 14
        assert result.observed_comparison is result.paired_result.comparison
        assert result.observed_comparison.n == 7
        assert result.observed_comparison.mean_a == 0.0
        assert result.observed_comparison.mean_b == 1.0
    else:
        assert result.archives == ()
        assert result.observed_comparison is None
        assert result.diagnostics == ("completed_evidence_archive_refused",)


def test_private_canary_not_in_diagnostics(tmp_path):
    case = SyntheticExperiment(tmp_path)
    private = "PRIVATE_PROMPT_ORACLE_PATH_CANARY"
    task = case.plan.draw.eligible[0]

    def evidence(row):
        raise ValueError(private + repr(task))

    result = case.run(evidence_for=evidence)
    for sensitive in (private, task.question, task.gold_sql, str(task.db_path)):
        assert sensitive not in repr(result)
    assert result.observed_comparison is None


def test_cancellation_preserves_original_and_closes_driver(tmp_path):
    case = SyntheticExperiment(tmp_path)
    cancellation = asyncio.CancelledError("synthetic-primary")
    closed = []

    async def driver(request):
        case.calls.append(request)
        try:
            raise cancellation
            yield
        finally:
            closed.append(request.arm)

    with pytest.raises(asyncio.CancelledError) as caught:
        case.run(run_arm=driver)
    assert caught.value is cancellation
    assert closed == ["bash"]
    assert [r.arm for r in case.calls] == ["bash"]
    assert caught.value.paired_bird_result.status == "void"
    assert case.output.is_dir()
    assert list(case.output.iterdir()) == []


def test_cancellation_cleanup_failure_keeps_primary(tmp_path):
    case = SyntheticExperiment(tmp_path)
    cancellation = asyncio.CancelledError("synthetic-primary")
    closed = []

    class SyntheticIterator:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise cancellation

        async def aclose(self):
            closed.append(True)
            raise OSError("PRIVATE_CLEANUP_CANARY")

    with pytest.raises(asyncio.CancelledError) as caught:
        case.run(run_arm=lambda request: SyntheticIterator())
    assert caught.value is cancellation
    assert closed == [True]
    result = caught.value.paired_bird_result
    assert result.status == "void"
    assert "bash:cleanup_failure" in result.diagnostics
    assert "PRIVATE_CLEANUP_CANARY" not in repr(result)


def test_partial_archive_not_complete(tmp_path, monkeypatch):
    case = SyntheticExperiment(tmp_path)
    original = runner.assets.write_new
    writes = []

    def fail_second(path, raw):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("synthetic partial archive")
        return original(path, raw)

    monkeypatch.setattr(runner.assets, "write_new", fail_second)
    result = case.run()
    assert writes[0].is_file()
    assert len(writes) == 2
    assert not result.archive_complete
    assert result.paired_result.status == "complete"
    assert result.observed_comparison is None


@pytest.mark.parametrize("declarations", [
    {}, {"checkpoint": None, "seed": []},
    {"checkpoint": "same-checkpoint", "seed": 123, "cohort": "same-cohort"},
])
def test_checkpoint_declarations_never_qualify(tmp_path, declarations):
    case = SyntheticExperiment(tmp_path)

    def evidence(row):
        actual = case.evidence(row)
        actual.episode.traces[0].info.update(declarations)
        return actual

    result = case.run(evidence_for=evidence)
    assert result.archive_complete
    assert result.observed_comparison is not None
    assert not result.scientifically_qualified
    assert "independent_checkpoint_seed_authority_unavailable" in result.scientific_limitations


def test_missing_historical_baseline_is_none(tmp_path):
    case = SyntheticExperiment(tmp_path)
    result = case.run()
    assert result.historical_comparison is None
    second_root = tmp_path / "second"
    second_root.mkdir()
    second = SyntheticExperiment(second_root)
    result = second.run(historical_baseline={})
    assert result.historical_comparison.statistics is None
    assert not result.historical_comparison.complete
    assert all(row.baseline.score is None for row in result.historical_comparison.cases)


def test_historical_uses_existing_comparator(tmp_path, monkeypatch):
    case = SyntheticExperiment(tmp_path)
    original = sql_capture_comparison.compare_capture_files
    calls = []

    def delegated(planned, baseline, treatment):
        calls.append((planned, baseline, treatment))
        return original(planned, baseline, treatment)

    monkeypatch.setattr(sql_capture_comparison, "compare_capture_files", delegated)
    result = case.run(historical_baseline={})
    assert len(calls) == 1
    assert calls[0][0] == tuple(t.name for t in case.plan.draw.eligible)
    assert len(calls[0][2]) == 7
    assert result.historical_comparison.statistics is None


def test_actual_public_task_canary_not_reprojected(tmp_path):
    case = SyntheticExperiment(tmp_path)
    seen = []

    def evidence(row):
        actual = case.evidence(row)
        seen.append(actual.episode.task.data.model_dump_json())
        return actual

    result = case.run(evidence_for=evidence)
    assert result.archive_complete
    assert len(seen) == 14
    for private in case.plan.draw.eligible:
        assert all(str(private.db_path) not in public for public in seen)
        assert all(private.gold_sql not in public for public in seen)
