"""Actual synthetic samples, never reconstructed from aggregate probe rates."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench import fixture, prepare
from bench.score import ExResult, extract_sql
from train import frontier_bindings as core


def _api():
    return importlib.import_module("bench.frontier.sample_capture")


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


@dataclasses.dataclass(frozen=True)
class Staged:
    root: Path
    draw: Path
    supplement: Path
    plan: core.MeasurementPlan
    admitted: prepare.ValidatedDraw


def _stage(path):
    root = fixture.materialize(path / "corpus")
    records = json.loads((root / "dev.json").read_text())
    records[0]["SQL"] = "SELECT * FROM absent_capture_table"
    (root / "dev.json").write_text(json.dumps(records))
    draw, supplement = path / "draw.json", path / "supplement.json"
    draw_sha = prepare.freeze_draw(
        root, draw, seed=0, per_tier={"simple": 2, "moderate": 3, "challenging": 3},
        fixture=True)
    supplement_sha = prepare.validate_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha)
    admitted = prepare.load_validated_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supplement_sha, fixture=True)
    sources = prepare._source_sha256()
    dbs = {d.db_id: d.sha256 for d in admitted.databases}
    pin = "a" * 64
    plan = core.MeasurementPlan(
        "plan", "execution", "b" * 40, _sha(b"inventory"), None,
        "runtime", "provider-declaration", "route", pin, pin, pin, pin, pin,
        _sha(prepare._canonical_bytes(sources)), draw_sha, supplement_sha,
        tuple(core.TaskBinding(t.name, prepare._task_sha256(t), dbs[t.db_id])
              for t in admitted.planned),
        tuple(t.name for t in admitted.eligible),
        tuple(core.PreparationExclusion(e.id, e.status) for e in admitted.exclusions),
        4, 0.6,
        core.ScorerBinding(sources["bench/score.py"], sources["bench/score.py"],
                           admitted.comparison, admitted.timeout_s, admitted.max_rows),
        "resource-declaration", "grant-declaration")
    return Staged(root, draw, supplement, plan, admitted)


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    return _stage(tmp_path_factory.mktemp("capture"))


def _limits(**changes):
    return dataclasses.replace(core.BindingLimits(
        1024, 4096, 12289, 12289, 1 << 20, 16 << 20, 256, 10), **changes)


def _run(staged, session, generate=None, **changes):
    kwargs = dict(expected_draw_sha256=staged.plan.draw_sha256,
                  expected_supplement_sha256=staged.plan.supplement_sha256,
                  fixture=True)
    kwargs.update(changes)
    return session.run(staged.root, staged.draw, staged.supplement,
                       generate or (lambda t: t.gold_sql), **kwargs)


def _session(staged, **kwargs):
    return _api().CaptureSession(staged.plan, b"inventory",
                                 limits=kwargs.pop("limits", _limits()), **kwargs)


def _fast_score(monkeypatch):
    module = importlib.import_module("bench.frontier.probe")
    monkeypatch.setattr(module, "execution_accuracy",
                        lambda *a, **k: ExResult(1.0, "match", True, "", 1, 1))


def _frames(payload):
    prefix = b"frontier-score-v1;"
    assert payload.startswith(prefix)
    fields, rest = [], payload[len(prefix):]
    while rest:
        size, rest = rest.split(b":", 1)
        n = int(size)
        fields.append(rest[:n].decode("utf-8"))
        rest = rest[n:]
    assert len(fields) == 8
    return fields


def _representation_size(value):
    if type(value) in (str, bytes):
        return len(value.encode("utf-8")) if type(value) is str else len(value)
    if type(value) is tuple:
        return sum(_representation_size(item) for item in value)
    if dataclasses.is_dataclass(value):
        return sum(_representation_size(getattr(value, f.name))
                   for f in dataclasses.fields(value))
    return 0


def _scoring_bytes(sql, result):
    fields = [sql, _sha(sql.encode("utf-8")), "f:" + result.score.hex(),
              result.status, "true" if result.valid else "false", result.detail,
              str(result.n_pred_rows), str(result.n_gold_rows)]
    raw = [value.encode("utf-8") for value in fields]
    return b"frontier-score-v1;" + b"".join(
        str(len(value)).encode("ascii") + b":" + value for value in raw)


def test_capture_complete_draw(staged, monkeypatch):
    module = importlib.import_module("bench.frontier.probe")
    real_score = module.execution_accuracy
    scores, calls, completions = [], [], []

    def score(*args, **kwargs):
        value = real_score(*args, **kwargs)
        scores.append((args, kwargs, value))
        return value

    def generate(task):
        calls.append(task.name)
        text = f"```sql\n{task.gold_sql if len(calls) % 2 else 'SELECT -98765'}\n```"
        completions.append(text)
        return text

    monkeypatch.setattr(module, "execution_accuracy", score)
    session = _session(staged)
    assert session.snapshot.state == "READY"
    assert session.snapshot.observations == session.snapshot.callback_invocations == 0
    captured = _run(staged, session, generate)
    expected_order = [t.name for t in staged.admitted.eligible for _ in range(4)]
    assert len(staged.plan.tasks) == 8 and len(staged.plan.exclusions) == 1
    assert len(expected_order) == 28
    assert calls == [args[1].name for args, _, _ in scores] == expected_order
    assert len(scores) == 28
    assert len(captured.batch.blobs) == len(captured.retention_pins) == 57
    assert [(s.task_id, s.slot_index) for s in captured.batch.samples] == [
        (t, i) for t in staged.plan.eligible_ids for i in range(4)]
    blobs = {b.evidence_id: b.payload for b in captured.batch.blobs}
    for sample, completion, (_, bounds, original) in zip(
            captured.batch.samples, completions, scores):
        assert blobs[sample.generation_evidence_id] == completion.encode("utf-8")
        prediction = extract_sql(completion)
        assert sample.prediction_sha256 == _sha(prediction.encode("utf-8"))
        fields = _frames(blobs[sample.scoring_evidence_id])
        assert fields == [
            prediction, sample.prediction_sha256, "f:" + original.score.hex(),
            original.status, "true", original.detail,
            str(original.n_pred_rows), str(original.n_gold_rows)]
        assert bounds == dict(compare="set", timeout_s=30.0, max_rows=500_000)
    assert {s.score for s in captured.batch.samples} == {0.0, 1.0}
    report = captured.report
    assert report.bindings_consistent and report.schedule_complete
    assert report.valid_declared_scores == report.observed_slots == 28
    assert report.all_samples_validly_scored
    assert report.provenance == "unverified" and report.attested_facts == ()
    assert not report.genuine_measurement_accepted and not report.training_authorized
    assert session.snapshot.state == "FINISHED"
    assert session.snapshot.observations == session.snapshot.retained_completions == 28
    before = tuple((b.evidence_id, b.payload) for b in captured.batch.blobs)
    pins = tuple(tuple(getattr(p, f.name) for f in dataclasses.fields(p))
                 for p in captured.retention_pins)
    captured.result.rates.clear()
    captured.result.void["mutable legacy result"] = "not evidence"
    assert before == tuple((b.evidence_id, b.payload) for b in captured.batch.blobs)
    assert pins == tuple(tuple(getattr(p, f.name) for f in dataclasses.fields(p))
                         for p in captured.retention_pins)
    checked = core.validate_frontier_bindings(
        staged.plan, captured.retention_pins, captured.batch, limits=_limits())
    assert checked == captured.report
    for value in (captured, captured.batch, captured.retention_pins[0]):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, None)


@pytest.mark.parametrize("at", [1, 2])
def test_failures(staged, monkeypatch, at):
    _fast_score(monkeypatch)
    session, calls = _session(staged), []
    failure = KeyboardInterrupt("private generator exception")

    def generate(task):
        calls.append(task.name)
        assert session.snapshot.state == "RUNNING"
        if len(calls) == at:
            raise failure
        return task.gold_sql

    with pytest.raises(KeyboardInterrupt) as caught:
        _run(staged, session, generate)
    assert caught.value is failure and len(calls) == at
    snap = session.snapshot
    assert snap.state == "QUARANTINED"
    assert snap.reason == "unknown_operational_outcome"
    assert snap.observations == at - 1 and snap.callback_invocations == at
    with pytest.raises(_api().CaptureError):
        _run(staged, session, generate)
    assert session.snapshot == snap and len(calls) == at


@pytest.mark.parametrize("phase", ["extract", "score", "observe"])
def test_phase_exception_identity(staged, monkeypatch, phase):
    module, api = importlib.import_module("bench.frontier.probe"), _api()
    session, calls = _session(staged), []
    failure = SystemExit("private phase exception")

    def fail(*a, **k):
        raise failure

    if phase == "extract":
        monkeypatch.setattr(module, "extract_sql", fail)
    elif phase == "score":
        monkeypatch.setattr(module, "execution_accuracy", fail)
    else:
        monkeypatch.setattr(api, "_encode_score", fail)

    def generate(task):
        calls.append(task.name)
        return task.gold_sql

    with pytest.raises(SystemExit) as caught:
        _run(staged, session, generate)
    assert caught.value is failure and len(calls) == 1
    assert session.snapshot.state == "QUARANTINED"


@pytest.mark.parametrize("status", ["gold_error", "gold_timeout", "gold_truncated"])
def test_gold_void_suffixes(staged, monkeypatch, status):
    module = importlib.import_module("bench.frontier.probe")
    calls = []

    def score(sql, task, **kwargs):
        return ExResult(0.0, status, False, "raw private detail", 2, 5)

    monkeypatch.setattr(module, "execution_accuracy", score)

    def generate(task):
        calls.append(task.name)
        return task.gold_sql

    session = _session(staged)
    result = _run(staged, session, generate)
    assert calls == list(staged.plan.eligible_ids)
    assert [s.slot_index for s in result.batch.samples] == [0] * 7
    assert all(s.status == "invalid_gold" and s.score is None
               for s in result.batch.samples)
    assert result.result.void == dict.fromkeys(calls, status)
    assert len(result.batch.blobs) == 15
    assert session.snapshot.state == "FINISHED"
    assert not result.report.schedule_complete and not result.report.bindings_consistent
    assert result.report.valid_declared_scores == 0
    assert dict(result.report.disposition_counts)["missing"] == 21
    assert result.report.total_issues == 28 and result.report.diagnostics_truncated
    assert all(_frames(b.payload)[3:6] == [status, "false", "raw private detail"]
               for b in result.batch.blobs if b.payload.startswith(b"frontier-score-v1;"))


def test_db_missing_quarantines(staged, monkeypatch):
    module = importlib.import_module("bench.frontier.probe")
    monkeypatch.setattr(module, "execution_accuracy",
                        lambda *a, **k: ExResult(0.0, "db_missing", False, "private"))
    session = _session(staged)
    with pytest.raises(_api().CaptureError):
        _run(staged, session)
    assert session.snapshot.state == "QUARANTINED"
    assert session.snapshot.reason == "database_unavailable"
    assert session.snapshot.callback_invocations == 1


@pytest.mark.parametrize("at", [0, 1, 3])
def test_one_void_suffix_never_reindexes_later_tasks(staged, monkeypatch, at):
    module = importlib.import_module("bench.frontier.probe")
    counts = {}
    first = staged.plan.eligible_ids[0]

    def score(sql, task, **kwargs):
        slot = counts.get(task.name, 0)
        counts[task.name] = slot + 1
        if task.name == first and slot == at:
            return ExResult(0.0, "gold_error", False, "original invalid score zero")
        return ExResult(1.0, "match", True)

    monkeypatch.setattr(module, "execution_accuracy", score)
    session = _session(staged)
    captured = _run(staged, session)
    assert [(s.task_id, s.slot_index) for s in captured.batch.samples] == (
        [(first, i) for i in range(at + 1)]
        + [(t, i) for t in staged.plan.eligible_ids[1:] for i in range(4)])
    assert session.snapshot.observations == 25 + at
    assert captured.report.valid_declared_scores == 24 + at
    assert captured.report.schedule_complete is (at == 3)
    assert captured.report.bindings_consistent is (at == 3)
    assert not captured.report.all_samples_validly_scored
    assert captured.batch.samples[at].status == "invalid_gold"
    assert captured.batch.samples[at].score is None
    assert captured.result.void == {first: "gold_error"}
    assert len(captured.result.rates) == 6


def test_lifecycle_reentry(staged, monkeypatch):
    _fast_score(monkeypatch)
    session = _session(staged)
    checked = []

    def generate(task):
        before = session.snapshot
        assert before.state == "RUNNING"
        with pytest.raises(_api().CaptureError):
            _run(staged, session)
        assert session.snapshot == before
        checked.append(1)
        return task.gold_sql

    _run(staged, session, generate)
    assert len(checked) == 28 and session.snapshot.state == "FINISHED"
    before = session.snapshot
    with pytest.raises(_api().CaptureError):
        _run(staged, session)
    assert session.snapshot == before
    with pytest.raises(AttributeError):
        session.snapshot = None


@pytest.mark.parametrize("mode", ["missing", "last_missing", "duplicate", "task",
                                  "slot", "completion", "reordered", "missing_fields"])
def test_observation_association(staged, monkeypatch, mode):
    _fast_score(monkeypatch)
    api = _api()
    original = api.probe_validated_draw

    def substituted(*args, sample_observer, **kwargs):
        previous, count = None, 0

        def observe(value):
            nonlocal previous, count
            count += 1
            if mode == "missing" or mode == "last_missing" and count == 28:
                return
            if mode == "last_missing":
                sample_observer(value)
                return
            if mode == "missing_fields":
                sample_observer(object.__new__(type(value)))
                return
            if mode == "reordered":
                if previous is None:
                    previous = value
                    sample_observer(value)
                else:
                    sample_observer(previous)
                return
            if mode == "duplicate":
                sample_observer(value)
                sample_observer(value)
                return
            change = {"task": {"task_id": staged.plan.eligible_ids[1]},
                      "slot": {"slot_index": 1},
                      "completion": {"completion": "SELECT private substitution"}}[mode]
            sample_observer(dataclasses.replace(value, **change))
        return original(*args, sample_observer=observe, **kwargs)

    monkeypatch.setattr(api, "probe_validated_draw", substituted)
    session = _session(staged)
    with pytest.raises(api.CaptureError):
        _run(staged, session)
    assert session.snapshot.state == "QUARANTINED"
    assert session.snapshot.callback_invocations == {
        "last_missing": 28, "reordered": 2}.get(mode, 1)


@pytest.mark.parametrize("field,value", [
    ("g", 2), ("dead_ceiling", 0.4),
    ("draw_sha256", "0" * 64), ("source_sha256", "0" * 64),
])
def test_plan_admission_drift(staged, monkeypatch, field, value):
    # G/ceiling are explicitly caller-owned and must instead forward, not drift-refuse.
    api = _api()
    plan = dataclasses.replace(staged.plan, **{field: value})
    session, calls = api.CaptureSession(plan, b"inventory", limits=_limits()), []

    def generate(task):
        calls.append(task.name)
        return task.gold_sql

    if field in ("g", "dead_ceiling"):
        _fast_score(monkeypatch)
        captured = _run(staged, session, generate)
        assert captured.result.g == plan.g
        assert captured.result.dead_ceiling == plan.dead_ceiling
        assert len(calls) == len(plan.eligible_ids) * plan.g
    else:
        with pytest.raises(api.CaptureError):
            _run(staged, session, generate)
        assert calls == [] and session.snapshot.state == "QUARANTINED"


@pytest.mark.parametrize("target", ["task", "database", "exclusion", "settings"])
def test_bound_admitted_projection(staged, target):
    api, p = _api(), staged.plan
    if target == "task":
        p = dataclasses.replace(p, tasks=(dataclasses.replace(
            p.tasks[0], task_sha256="0" * 64),) + p.tasks[1:])
    elif target == "database":
        p = dataclasses.replace(p, tasks=(dataclasses.replace(
            p.tasks[0], database_sha256="0" * 64),) + p.tasks[1:])
    elif target == "exclusion":
        p = dataclasses.replace(p, exclusions=(dataclasses.replace(
            p.exclusions[0], reason="other"),))
    else:
        p = dataclasses.replace(p, scorer=dataclasses.replace(p.scorer, max_rows=2))
    session, calls = api.CaptureSession(p, b"inventory", limits=_limits()), []
    with pytest.raises(api.CaptureError):
        _run(staged, session, lambda t: calls.append(t) or t.gold_sql)
    assert calls == []


@pytest.mark.parametrize("target", ["database", "corpus", "draw", "supplement", "source"])
def test_post_admission_drift(tmp_path, monkeypatch, target):
    staged = _stage(tmp_path)
    session, calls = _session(staged), []

    def generate(task):
        calls.append(task.name)
        if len(calls) == 28:
            if target == "database":
                with sqlite3.connect(task.db_path) as connection:
                    connection.execute("CREATE TABLE capture_drift (n INTEGER)")
            elif target == "corpus":
                path = staged.root / "dev.json"
                records = json.loads(path.read_text())
                records[1]["question"] += " synthetic drift"
                path.write_text(json.dumps(records))
            elif target in ("draw", "supplement"):
                path = getattr(staged, target)
                path.write_bytes(path.read_bytes() + b"\n")
            else:
                sources = prepare._source_sha256()
                sources["bench/score.py"] = "0" * 64
                monkeypatch.setattr(prepare, "_source_sha256", lambda: sources)
        return task.gold_sql

    with pytest.raises(prepare.PreparationError):
        _run(staged, session, generate)
    assert len(calls) == 28 and session.snapshot.state == "QUARANTINED"


def test_constructor_pure_and_reserves(staged, monkeypatch):
    api = _api()

    def forbidden(*args, **kwargs):
        raise AssertionError("constructor touched corpus or scorer")

    monkeypatch.setattr(api.prepare, "load_validated_draw", forbidden)
    monkeypatch.setattr(importlib.import_module("bench.frontier.probe"),
                        "execution_accuracy", forbidden)
    session = _session(staged)
    assert session.snapshot.callback_invocations == session.snapshot.observations == 0
    assert session.snapshot.evidence_items == 1
    for limits in (_limits(max_expected_evidence=56), _limits(max_raw_evidence=56),
                   _limits(max_identifier_bytes=10)):
        with pytest.raises(api.CaptureError):
            _session(staged, limits=limits)
    with pytest.raises(api.CaptureError):
        api.CaptureSession(staged.plan, b"wrong inventory", limits=_limits())


def test_actual_aggregate_boundary(staged, monkeypatch):
    api = _api()
    _fast_score(monkeypatch)
    initial = _session(staged)
    captured = _run(staged, initial, lambda t: "SELECT 1")
    # Independently count the actual core representation, including both plans.
    actual = (_representation_size(staged.plan)
              + _representation_size(captured.batch)
              + _representation_size(captured.retention_pins))
    assert actual == (initial._reserved_bytes - 6 * 28
                      + sum(len(b.payload) for b in captured.batch.blobs[1:]))
    exact = _session(staged, limits=_limits(max_aggregate_bytes=actual))
    _run(staged, exact, lambda t: "SELECT 1")
    one_less = _session(staged, limits=_limits(max_aggregate_bytes=actual - 1))
    with pytest.raises(api.CaptureError):
        _run(staged, one_less, lambda t: "SELECT 1")
    assert one_less.snapshot.state == "QUARANTINED"


def test_item_utf8_before_extraction(staged, monkeypatch):
    api, module = _api(), importlib.import_module("bench.frontier.probe")
    calls = []

    def extraction(text):
        calls.append(1)
        return text

    monkeypatch.setattr(module, "extract_sql", extraction)
    session = _session(staged, limits=_limits(max_item_bytes=512))
    with pytest.raises(api.CaptureError):
        _run(staged, session, lambda t: "é" * 257)
    assert calls == [] and session.snapshot.retained_completions == 0
    _fast_score(monkeypatch)
    exact = _session(staged, limits=_limits(max_item_bytes=512))
    # B completion accepted, then bounded score encoding can independently refuse.
    with pytest.raises(api.CaptureError):
        _run(staged, exact, lambda t: "é" * 256)
    assert calls == [1] and exact.snapshot.retained_completions == 1


@pytest.mark.parametrize("bad", ["\ud800", b"SELECT 1", object(), "x" * ((1 << 20) + 1)])
def test_completion_shape(staged, bad):
    session = _session(staged)
    with pytest.raises(_api().CaptureError) as caught:
        _run(staged, session, lambda t: bad)
    assert str(caught.value) == "frontier capture refused"
    assert session.snapshot.state == "QUARANTINED"


def test_privacy(staged, monkeypatch):
    _fast_score(monkeypatch)
    session = _session(staged)
    secret = "private-completion-SELECT-sensitive"
    _run(staged, session, lambda t: secret)
    text = repr(session.snapshot)
    assert secret not in text
    assert staged.plan.plan_id not in text
    assert not hasattr(session, "batch") and not hasattr(session, "result")
    assert not hasattr(session, "samples") and not hasattr(session, "blobs")


def test_actual_item_boundary(staged, monkeypatch):
    api, module = _api(), importlib.import_module("bench.frontier.probe")
    detail_size = next(n for n in range(512)
                       if len(_scoring_bytes("SELECT 1", ExResult(
                           1.0, "match", True, "x" * n, 1, 1))) == 512)
    original = ExResult(1.0, "match", True, "x" * detail_size, 1, 1)
    monkeypatch.setattr(module, "execution_accuracy", lambda *a, **k: original)
    exact = _session(staged, limits=_limits(max_item_bytes=512))
    result = _run(staged, exact, lambda t: "SELECT 1")
    assert {len(b.payload) for b in result.batch.blobs[2::2]} == {512}
    assert result.batch.blobs[2].payload == _scoring_bytes("SELECT 1", original)
    monkeypatch.setattr(module, "execution_accuracy", lambda *a, **k:
                        dataclasses.replace(original, detail=original.detail + "x"))
    over = _session(staged, limits=_limits(max_item_bytes=512))
    with pytest.raises(api.CaptureError):
        _run(staged, over, lambda t: "SELECT 1")
    assert over.snapshot.observations == 0 and over.snapshot.callback_invocations == 1


def test_exact_multibyte_completion_accepts(staged, monkeypatch):
    module = importlib.import_module("bench.frontier.probe")
    _fast_score(monkeypatch)
    monkeypatch.setattr(module, "extract_sql", lambda text: "SELECT 1")
    session = _session(staged, limits=_limits(max_item_bytes=512))
    result = _run(staged, session, lambda t: "é" * 256)
    assert all(b.payload == ("é" * 256).encode("utf-8")
               for b in result.batch.blobs[1::2])
    assert session.snapshot.observations == 28


def test_text_frames_are_not_escaped(staged, monkeypatch):
    module = importlib.import_module("bench.frontier.probe")
    sql, detail = 'SELECT "\\n☃:7:;\\\\\\""', '\n":secret:☃\\'
    original = ExResult(0.0, "pred_error", True, detail, 0, 9)
    monkeypatch.setattr(module, "extract_sql", lambda text: sql)
    monkeypatch.setattr(module, "execution_accuracy", lambda *a, **k: original)
    captured = _run(staged, _session(staged), lambda t: "completion ☃")
    assert captured.batch.blobs[2].payload == _scoring_bytes(sql, original)
    assert _frames(captured.batch.blobs[2].payload)[0] == sql
    assert _frames(captured.batch.blobs[2].payload)[5] == detail


@pytest.mark.parametrize("which", ["sql", "detail", "combined"])
def test_score_bounds_before_hash_or_serialization(monkeypatch, which):
    api, limits = _api(), _limits(max_item_bytes=512)
    sql = "x" * (513 if which == "sql" else 300 if which == "combined" else 1)
    detail = "x" * (513 if which == "detail" else 300 if which == "combined" else 1)
    budget = core._Budget(limits)

    def forbidden(*args, **kwargs):
        raise AssertionError("oversized scoring text reached hashing")

    monkeypatch.setattr(api, "_sha", forbidden)
    with pytest.raises(api.CaptureError):
        api._encode_score(sql, ExResult(1.0, "match", True, detail), budget, limits)
    assert budget.used == 0


@pytest.mark.parametrize("changes", [
    {"score": True}, {"score": float("nan")}, {"score": 1 << 10000},
    {"valid": 1}, {"status": "unknown"}, {"detail": "\ud800"},
    {"n_pred_rows": True}, {"n_gold_rows": -1}, {"n_gold_rows": 1 << 10000},
    {"score": 0.0}, {"valid": False, "status": "match"},
])
def test_malformed_scorer_fields(staged, monkeypatch, changes):
    module = importlib.import_module("bench.frontier.probe")
    original = dataclasses.replace(ExResult(1.0, "match", True), **changes)
    monkeypatch.setattr(module, "execution_accuracy", lambda *a, **k: original)
    session = _session(staged)
    with pytest.raises(_api().CaptureError):
        _run(staged, session)
    assert session.snapshot.observations == 0
    assert session.snapshot.state == "QUARANTINED"


def test_reservations_before_generation(staged):
    api = _api()
    good = _session(staged)
    before = good.snapshot
    assert before.observations == before.callback_invocations == 0
    assert before.evidence_items == 1
    with pytest.raises(api.CaptureError):
        _session(staged, limits=_limits(max_aggregate_bytes=good._reserved_bytes - 1))
    exact = _session(staged, limits=_limits(max_aggregate_bytes=good._reserved_bytes))
    assert exact.snapshot == before
    with pytest.raises(api.CaptureError):
        api.CaptureSession(dataclasses.replace(
            staged.plan, plan_id="p" * 200, execution_id="e" * 200),
            b"inventory", limits=_limits())


def test_ids_deterministic_unambiguous(staged, monkeypatch):
    _fast_score(monkeypatch)
    a = _run(staged, _session(staged))
    b = _run(staged, _session(staged))
    assert [p.evidence_id for p in a.retention_pins] == [
        p.evidence_id for p in b.retention_pins]
    assert len({p.evidence_id for p in a.retention_pins}) == 57
    api = _api()
    one = dataclasses.replace(staged.plan, plan_id="a:b", execution_id="c")
    two = dataclasses.replace(staged.plan, plan_id="a", execution_id="b:c")
    assert api._namespace(one, "t", 0, "g", 256) != api._namespace(two, "t", 0, "g", 256)
    assert api._namespace(one, "é", 0, "g", 256).endswith("2:é1:01:g")
    assert a.report.provenance == b.report.provenance == "unverified"


def test_running_precedes_admission_and_final_check(staged, monkeypatch):
    api = _api()
    _fast_score(monkeypatch)
    session = _session(staged)
    real_load, real_check = prepare.load_validated_draw, api._core_check
    phases = []

    def load(*args, **kwargs):
        phases.append(("admit", session.snapshot.state,
                       session.snapshot.callback_invocations))
        return real_load(*args, **kwargs)

    def check(*args, **kwargs):
        phases.append(("core", session.snapshot.state,
                       session.snapshot.callback_invocations))
        return real_check(*args, **kwargs)

    monkeypatch.setattr(prepare, "load_validated_draw", load)
    monkeypatch.setattr(importlib.import_module("bench.frontier.draw_probe"),
                        "load_validated_draw", load)
    monkeypatch.setattr(api, "_core_check", check)
    _run(staged, session)
    assert phases == [("admit", "RUNNING", 0), ("admit", "RUNNING", 0),
                      ("admit", "RUNNING", 28), ("core", "RUNNING", 28)]
    assert session.snapshot.state == "FINISHED"


@pytest.mark.parametrize("target", ["prediction", "bytes", "missing", "unexpected_issue"])
def test_final_join_never_returns_inconsistent_capture(staged, monkeypatch, target):
    api = _api()
    _fast_score(monkeypatch)
    session = _session(staged)
    original = api._core_check

    def check(plan, pins, batch, limits):
        if target == "prediction":
            batch = dataclasses.replace(batch, samples=(dataclasses.replace(
                batch.samples[0], prediction_sha256="0" * 64),) + batch.samples[1:])
        elif target == "bytes":
            batch = dataclasses.replace(batch, blobs=(batch.blobs[0],
                dataclasses.replace(batch.blobs[1], payload=b"substituted")) + batch.blobs[2:])
        elif target == "missing":
            batch = dataclasses.replace(batch, samples=batch.samples[1:])
        report = original(plan, pins, batch, limits)
        if target == "unexpected_issue":
            report = dataclasses.replace(report, total_issues=report.total_issues + 1)
        return report

    monkeypatch.setattr(api, "_core_check", check)
    with pytest.raises(api.CaptureError):
        _run(staged, session)
    assert session.snapshot.callback_invocations == 28
    assert session.snapshot.state == "QUARANTINED"


@pytest.mark.parametrize("mutation", ["private", "missing", "claimed_database_failure"])
def test_mutated_callback_exception_code_does_not_leak(staged, mutation):
    api, session = _api(), _session(staged)
    failure = api.CaptureError()
    if mutation == "private":
        failure.code = "SELECT private raw exception code"
    elif mutation == "missing":
        del failure.code
    else:
        failure.code = "database_unavailable"

    def generate(task):
        raise failure

    with pytest.raises(api.CaptureError) as caught:
        _run(staged, session, generate)
    assert caught.value is failure
    assert session.snapshot.reason == "unknown_operational_outcome"
    assert "SELECT" not in repr(session.snapshot)


def test_forwarding_loss_control(staged, monkeypatch):
    api = _api()
    _fast_score(monkeypatch)
    original = api.probe_validated_draw

    def oracle():
        try:
            result = _run(staged, _session(staged))
        except api.CaptureError:
            raise AssertionError("forwarding oracle") from None
        assert result.report.observed_slots == 28, "forwarding oracle"

    oracle()

    def dropped(*args, sample_observer, **kwargs):
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(api, "probe_validated_draw", dropped)
        with pytest.raises(AssertionError) as caught:
            oracle()
        assert str(caught.value).splitlines()[0] == "forwarding oracle"
    oracle()


def test_association_loss_control(staged, monkeypatch):
    api = _api()
    _fast_score(monkeypatch)
    original = api.probe_validated_draw

    def altered(*args, sample_observer, **kwargs):
        def observe(o):
            sample_observer(dataclasses.replace(o, task_id=staged.plan.eligible_ids[1]))
        return original(*args, sample_observer=observe, **kwargs)

    def oracle():
        with monkeypatch.context() as patch:
            patch.setattr(api, "probe_validated_draw", altered)
            try:
                _run(staged, _session(staged))
            except api.CaptureError:
                return
            raise AssertionError("association oracle")

    oracle()
    with monkeypatch.context() as patch:
        patch.setattr(api, "_observation_matches", lambda *a: True)
        with pytest.raises(AssertionError) as caught:
            oracle()
        assert str(caught.value).splitlines()[0] == "association oracle"
    oracle()
    assert _run(staged, _session(staged)).report.observed_slots == 28
