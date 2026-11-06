"""Scripted offline composition contracts, not model or training qualification."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
from types import SimpleNamespace

import pytest

from bench import prepare
from bench.frontier import sample_capture
from bench.frontier.test_sample_capture import _frames, _limits, _stage
from bench.score import extract_sql
from train import frontier_transport as transport
from train.test_frontier_transport import _canonical, _document, _shape


def _workflow():
    try:
        module = importlib.import_module("bench.frontier.capture_workflow")
    except ModuleNotFoundError as error:
        if error.name != "bench.frontier.capture_workflow":
            raise
        pytest.fail("missing feature: bench.frontier.capture_workflow", pytrace=False)
    function = getattr(module, "capture_to_archive", None)
    assert callable(function), "missing feature: capture_to_archive keyword API"
    return function


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    return _stage(tmp_path_factory.mktemp("capture-workflow"))


@pytest.fixture
def tracked(staged, monkeypatch):
    probe = importlib.import_module("bench.frontier.probe")
    real_score = probe.execution_accuracy
    real_run = sample_capture.CaptureSession.run
    state = SimpleNamespace(
        generated=[], score_calls=[], scored=[], completions=[], runs=[],
        captures=[], generator_failure=None, scorer_failure=None,
        publishing=False, on_generate=None)

    def generate(task):
        assert not state.publishing, "publication invoked generation"
        state.generated.append(task.name)
        if state.generator_failure is not None and len(state.generated) == 2:
            raise state.generator_failure
        if state.on_generate is not None:
            state.on_generate(task)
        sql = task.gold_sql if len(state.generated) % 2 else "SELECT -98765"
        completion = f"```sql\n{sql}\n```"
        state.completions.append(completion)
        return completion

    def score(*args, **kwargs):
        assert not state.publishing, "publication invoked probe scoring"
        state.score_calls.append((args, kwargs))
        if state.scorer_failure is not None and len(state.score_calls) == 2:
            raise state.scorer_failure
        result = real_score(*args, **kwargs)
        state.scored.append(result)
        return result

    def run(session, *args, **kwargs):
        state.runs.append((session, args, kwargs))
        captured = real_run(session, *args, **kwargs)
        state.captures.append(captured)
        return captured

    monkeypatch.setattr(probe, "execution_accuracy", score)
    monkeypatch.setattr(sample_capture.CaptureSession, "run", run)
    state.generate = generate
    return state


@pytest.fixture
def archived(tracked, monkeypatch):
    real_write = transport.write_unverified_bindings
    real_load = transport.load_unverified_bindings
    state = SimpleNamespace(
        writes=[], loads=[], digests=[], loaded=[], errors=[], on_write=None)

    def write(plan, retention_pins, batch, output_path, *, limits):
        state.writes.append(
            ((plan, retention_pins, batch, output_path), dict(limits=limits)))
        if state.on_write is not None:
            state.on_write()
        try:
            digest = real_write(
                plan, retention_pins, batch, output_path, limits=limits)
        except transport.TransportPublicationIndeterminateError as error:
            state.errors.append(error)
            raise
        state.digests.append(digest)
        return digest

    def load(path, *, expected_archive_sha256, limits):
        state.loads.append(
            ((path,), dict(expected_archive_sha256=expected_archive_sha256,
                           limits=limits)))
        assert len(state.digests) == 1
        assert expected_archive_sha256 is state.digests[0], (
            "reload must use trusted writer-returned pin, not candidate hashing")
        value = real_load(
            path, expected_archive_sha256=expected_archive_sha256, limits=limits)
        state.loaded.append(value)
        return value

    monkeypatch.setattr(transport, "write_unverified_bindings", write)
    monkeypatch.setattr(transport, "load_unverified_bindings", load)
    return state


def _arguments(staged, tracked, output):
    return dict(
        plan=staged.plan, checkpoint_inventory=b"inventory", limits=_limits(),
        root=staged.root, draw_path=staged.draw,
        supplement_path=staged.supplement,
        expected_draw_sha256=staged.plan.draw_sha256,
        expected_supplement_sha256=staged.plan.supplement_sha256,
        fixture=True, generate=tracked.generate, output_path=output)


def _authority(report):
    assert report.provenance == "unverified"
    assert report.attested_facts == ()
    assert report.genuine_measurement_accepted is False
    assert report.training_authorized is False


def _assert_real_capture(staged, tracked, captured):
    expected_order = [name for name in staged.plan.eligible_ids for _ in range(4)]
    assert len(staged.plan.tasks) == 8
    assert len(staged.plan.exclusions) == 1
    assert len(staged.plan.eligible_ids) == 7
    assert staged.plan.g == 4 and staged.plan.dead_ceiling == 0.6
    assert tracked.generated == expected_order
    assert [args[1].name for args, _ in tracked.score_calls] == expected_order
    assert len(tracked.scored) == len(tracked.score_calls) == 28
    assert len(tracked.runs) == len(tracked.captures) == 1
    assert tracked.captures[0] is captured
    assert _shape(captured.batch.plan) == _shape(staged.plan)
    assert tracked.runs[0][0].snapshot.state == "FINISHED"
    assert len(captured.batch.samples) == 28
    assert len(captured.batch.blobs) == len(captured.retention_pins) == 57
    assert [(s.task_id, s.slot_index) for s in captured.batch.samples] == [
        (name, slot) for name in staged.plan.eligible_ids for slot in range(4)]
    blobs = {blob.evidence_id: blob.payload for blob in captured.batch.blobs}
    for sample, completion, original, (_, bounds) in zip(
            captured.batch.samples, tracked.completions, tracked.scored,
            tracked.score_calls, strict=True):
        prediction = extract_sql(completion)
        assert blobs[sample.generation_evidence_id] == completion.encode("utf-8")
        assert _frames(blobs[sample.scoring_evidence_id]) == [
            prediction, hashlib.sha256(prediction.encode("utf-8")).hexdigest(),
            "f:" + original.score.hex(), original.status, "true", original.detail,
            str(original.n_pred_rows), str(original.n_gold_rows)]
        assert bounds == dict(
            compare=staged.plan.scorer.comparison,
            timeout_s=staged.plan.scorer.timeout_s,
            max_rows=staged.plan.scorer.max_rows)
    assert {sample.score for sample in captured.batch.samples} == {0.0, 1.0}
    assert captured.result.g == staged.plan.g
    assert captured.result.policy == staged.plan.policy_revision
    assert captured.result.dead_ceiling == staged.plan.dead_ceiling
    assert captured.report.schedule_complete
    assert captured.report.bindings_consistent
    assert captured.report.valid_declared_scores == 28
    _authority(captured.report)


def _assert_roundtrip(captured, digest, reloaded, output):
    data = SimpleNamespace(
        plan=captured.batch.plan, pins=captured.retention_pins, batch=captured.batch)
    raw = output.read_bytes()
    assert raw == _canonical(_document(data))
    assert digest == hashlib.sha256(raw).hexdigest()
    assert _shape(reloaded.plan) == _shape(captured.batch.plan)
    assert _shape(reloaded.batch) == _shape(captured.batch)
    assert _shape(reloaded.retention_pins) == _shape(captured.retention_pins)
    assert reloaded.report == captured.report
    assert reloaded.plan is not captured.batch.plan
    assert reloaded.batch is not captured.batch
    assert reloaded.retention_pins is not captured.retention_pins
    assert reloaded.batch.samples[0] is not captured.batch.samples[0]
    assert reloaded.batch.blobs[0] is not captured.batch.blobs[0]
    _authority(reloaded.report)


def test_existing_capture_transport_control(staged, tracked, tmp_path):
    session = sample_capture.CaptureSession(
        staged.plan, b"inventory", limits=_limits())
    captured = session.run(
        staged.root, staged.draw, staged.supplement, tracked.generate,
        expected_draw_sha256=staged.plan.draw_sha256,
        expected_supplement_sha256=staged.plan.supplement_sha256, fixture=True)
    output = tmp_path.resolve() / "control.json"
    digest = transport.write_unverified_bindings(
        captured.batch.plan, captured.retention_pins, captured.batch, output,
        limits=_limits())
    reloaded = transport.load_unverified_bindings(
        output, expected_archive_sha256=digest, limits=_limits())
    _assert_real_capture(staged, tracked, captured)
    _assert_roundtrip(captured, digest, reloaded, output)
    assert list(tmp_path.iterdir()) == [output]


def test_capture_archive_roundtrip_real_sqlite(staged, tracked, archived, tmp_path):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"
    arguments = _arguments(staged, tracked, output)
    result = workflow(**arguments)
    assert len(archived.writes) == len(archived.loads) == 1
    assert result.captured is tracked.captures[0]
    assert result.reloaded is archived.loaded[0]
    assert result.archive_sha256 is archived.digests[0]
    write_args, write_kwargs = archived.writes[0]
    assert write_args[0] is result.captured.batch.plan
    assert write_args[1] is result.captured.retention_pins
    assert write_args[2] is result.captured.batch
    assert write_args[3] == output
    assert write_kwargs["limits"] is arguments["limits"]
    assert archived.loads[0][0] == (output,)
    assert archived.loads[0][1]["limits"] is arguments["limits"]
    _assert_real_capture(staged, tracked, result.captured)
    _assert_roundtrip(
        result.captured, result.archive_sha256, result.reloaded, output)
    assert list(tmp_path.iterdir()) == [output]
    assert dataclasses.is_dataclass(result)
    assert not hasattr(result, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.archive_sha256 = "0" * 64
    before = _shape(result.reloaded.batch)
    result.captured.result.rates.clear()
    assert _shape(result.reloaded.batch) == before
    assert result.reloaded.report.observed_slots == 28


def test_publication_adds_no_execution(
        staged, tracked, archived, tmp_path, monkeypatch):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"

    def publishing():
        assert len(tracked.generated) == len(tracked.scored) == 28
        tracked.publishing = True

        def forbidden(*args, **kwargs):
            raise AssertionError("publication repeated draw admission")

        monkeypatch.setattr(prepare, "load_validated_draw", forbidden)

    archived.on_write = publishing
    result = workflow(**_arguments(staged, tracked, output))
    assert tracked.publishing
    assert len(tracked.generated) == len(tracked.score_calls) == 28
    assert len(tracked.scored) == 28
    assert len(archived.writes) == len(archived.loads) == 1
    assert result.archive_sha256 is archived.digests[0]
    assert result.reloaded is archived.loaded[0]


def test_generator_failure_does_not_publish_or_retry(
        staged, tracked, archived, tmp_path):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"
    failure = RuntimeError("scripted generator failure")
    tracked.generator_failure = failure
    with pytest.raises(RuntimeError) as caught:
        workflow(**_arguments(staged, tracked, output))
    assert caught.value is failure
    assert len(tracked.generated) == 2
    assert len(tracked.score_calls) == len(tracked.scored) == 1
    assert len(tracked.runs) == 1 and tracked.captures == []
    assert tracked.runs[0][0].snapshot.state == "QUARANTINED"
    assert archived.writes == archived.loads == []
    assert list(tmp_path.iterdir()) == []


def test_scorer_failure_does_not_publish_or_retry(
        staged, tracked, archived, tmp_path):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"
    failure = RuntimeError("scripted scorer failure")
    tracked.scorer_failure = failure
    with pytest.raises(RuntimeError) as caught:
        workflow(**_arguments(staged, tracked, output))
    assert caught.value is failure
    assert len(tracked.generated) == len(tracked.score_calls) == 2
    assert len(tracked.scored) == 1
    assert len(tracked.runs) == 1 and tracked.captures == []
    assert tracked.runs[0][0].snapshot.state == "QUARANTINED"
    assert archived.writes == archived.loads == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("destination", ["existing", "missing_parent", "file_parent"])
def test_destination_refused_before_generation(
        staged, tracked, archived, tmp_path, destination):
    workflow = _workflow()
    root = tmp_path.resolve()
    original = b"existing caller-owned bytes\n"
    protected = None
    if destination == "existing":
        output = root / "archive.json"
        output.write_bytes(original)
        protected = output
    elif destination == "missing_parent":
        output = root / "missing" / "archive.json"
    else:
        protected = root / "not-a-directory"
        protected.write_bytes(original)
        output = protected / "archive.json"
    before = tuple(root.iterdir())
    with pytest.raises(transport.TransportError):
        workflow(**_arguments(staged, tracked, output))
    assert tracked.generated == tracked.score_calls == tracked.scored == []
    assert tracked.captures == []
    assert archived.writes == archived.loads == []
    assert tuple(root.iterdir()) == before
    if protected is not None:
        assert protected.read_bytes() == original
    if destination == "missing_parent":
        assert not output.parent.exists()


def test_destination_race_keeps_create_only_publication(
        staged, tracked, archived, tmp_path):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"
    competitor = b"scripted competing destination\n"

    def race(task):
        if len(tracked.generated) == 1:
            assert not output.exists()
            output.write_bytes(competitor)

    tracked.on_generate = race
    with pytest.raises(transport.TransportError):
        workflow(**_arguments(staged, tracked, output))
    assert len(tracked.generated) == len(tracked.scored) == 28
    assert len(tracked.runs) == len(tracked.captures) == 1
    assert len(archived.writes) == 1
    assert archived.digests == archived.loads == []
    assert output.read_bytes() == competitor
    assert list(tmp_path.iterdir()) == [output]


def test_indeterminate_publication_propagates_without_retry(
        staged, tracked, archived, tmp_path, monkeypatch):
    workflow = _workflow()
    output = tmp_path.resolve() / "archive.json"
    syncs = []

    def sync(*args, **kwargs):
        syncs.append(1)
        assert output.is_file(), "fault must occur after real create-only link"
        raise OSError("scripted directory-sync failure")

    monkeypatch.setattr(prepare, "_sync_dir", sync)
    with pytest.raises(transport.TransportPublicationIndeterminateError) as caught:
        workflow(**_arguments(staged, tracked, output))
    assert len(archived.errors) == 1 and caught.value is archived.errors[0]
    assert syncs == [1]
    assert len(archived.writes) == 1
    assert archived.digests == archived.loads == []
    assert len(tracked.generated) == len(tracked.scored) == 28
    assert len(tracked.captures) == 1
    captured = tracked.captures[0]
    assert len(captured.batch.samples) == 28
    assert len(captured.batch.blobs) == 57
    data = SimpleNamespace(
        plan=captured.batch.plan, pins=captured.retention_pins, batch=captured.batch)
    assert output.read_bytes() == _canonical(_document(data))
    assert list(tmp_path.iterdir()) == [output]
