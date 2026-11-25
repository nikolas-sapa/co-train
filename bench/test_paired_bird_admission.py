"""Actual retained-draw admission, never constructed-ValidatedDraw authority."""

import asyncio
import dataclasses
import hashlib
import json
import socket

import pytest

from bench import prepare
from bench.test_paired_bird import _api, _instrument, _outcome, _plan, _run
from bench.test_prepare import _sentries
from bench.test_validated_draw_databases import _artifacts


def test_b_admit8_actual_consumer_two_passes_original_objects(tmp_path, monkeypatch):
    api = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(
        tmp_path, excluded_only=True)
    assert draw_sha == hashlib.sha256(draw.read_bytes()).hexdigest()
    assert supp_sha == hashlib.sha256(supp.read_bytes()).hexdigest()
    original = prepare.load_validated_draw
    consumed = []

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        consumed.append(result)
        return result

    # Observe either a module-qualified call or a bound consumer import.
    with monkeypatch.context() as m:
        m.setattr(prepare, "load_validated_draw", observe)
        for name, value in list(vars(api).items()):
            if value is original:
                m.setattr(api, name, observe)
        with _sentries(m, prepare) as sentries:
            plan = api.prepare_paired_bird(
                root, draw, supp, expected_draw_sha256=draw_sha,
                expected_supplement_sha256=supp_sha, fixture=True)
    assert len(consumed) == 1 and plan.draw is consumed[0]
    assert sentries["loads"] == 2
    assert all(sentries[key] == 0 for key in ("connects", "selects", "golds", "ex"))
    assert (len(plan.draw.planned), len(plan.draw.eligible),
            len(plan.draw.exclusions), len(plan.draw.databases)) == (8, 7, 1, 2)
    assert tuple(t.name for t in plan.draw.planned) == tuple(
        entry["id"] for entry in json.loads(draw.read_bytes())["planned"])
    excluded = {entry.id for entry in plan.draw.exclusions}
    assert all(a is b for a, b in zip(
        plan.draw.eligible,
        (t for t in plan.draw.planned if t.name not in excluded), strict=True))
    assert "excluded-only" in {d.db_id for d in plan.draw.databases}
    assert "excluded-only" not in {t.db_id for t in plan.draw.eligible}


@pytest.mark.parametrize("bad", ["draw", "supplement"])
def test_b_bad_digest_before_parse_corpus_or_driver(tmp_path, monkeypatch, bad):
    api = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(1)
        pytest.fail("digest refusal reached parsing or corpus")

    monkeypatch.setattr(prepare, "_parse_draw", forbidden)
    monkeypatch.setattr(prepare, "_parse_supplement", forbidden)
    monkeypatch.setattr(prepare, "_corpus", forbidden)
    with pytest.raises(prepare.PreparationError, match="digest mismatch"):
        api.prepare_paired_bird(
            root, draw, supp,
            expected_draw_sha256="0" * 64 if bad == "draw" else draw_sha,
            expected_supplement_sha256="0" * 64 if bad == "supplement" else supp_sha,
            fixture=True)
    assert calls == []


def test_b_fixture_opt_in_exact_and_constructed_draw_has_no_authority(tmp_path):
    api = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    with pytest.raises(prepare.PreparationError, match="fixture"):
        api.prepare_paired_bird(
            root, draw, supp, expected_draw_sha256=draw_sha,
            expected_supplement_sha256=supp_sha, fixture=False)
    admitted = prepare.load_validated_draw(
        root, draw, supp, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha, fixture=True)
    constructed = dataclasses.replace(admitted)
    calls = []

    async def driver(request):
        calls.append(request)
        yield _outcome(api, request, request.tasks[0])

    with pytest.raises(api.PairedBirdError, match="plan|admi"):
        _run(api, constructed, driver)
    assert calls == []


def test_b_no_experiment_output_or_external_attempts(tmp_path, monkeypatch):
    api = _api()
    plan = _plan(tmp_path, api)
    before = {p.relative_to(tmp_path): p.read_bytes()
              for p in tmp_path.rglob("*") if p.is_file()}
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(1)
        pytest.fail("offline paired coordinator attempted network")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)

    async def driver(request):
        for task in request.tasks:
            yield _outcome(api, request, task)

    result = _run(api, plan, driver)
    after = {p.relative_to(tmp_path): p.read_bytes()
             for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    assert attempts == []
    assert result.fixture is True and result.measurement is False


def test_b_identity_inputs_reject_mutable_settings_before_dispatch(tmp_path):
    api = _api()
    plan = _plan(tmp_path, api)
    calls = []

    async def driver(request):
        calls.append(request)
        yield _outcome(api, request, request.tasks[0])

    with pytest.raises(api.PairedBirdError, match="instrument"):
        asyncio.run(api.run_paired_bird(
            plan, run_arm=driver, instrument={"max_turns": 8},
            policy_identity="fixture", num_rollouts=1))
    with pytest.raises(api.PairedBirdError, match="policy"):
        asyncio.run(api.run_paired_bird(
            plan, run_arm=driver, instrument=_instrument(api),
            policy_identity=["fixture"], num_rollouts=1))
    assert calls == []


@pytest.mark.parametrize("bad", ["draw", "supplement"])
def test_b_retained_digest_required_without_sentries(tmp_path, bad):
    """Sensitivity target: admission must honor caller-retained, not fresh hashes."""
    api = _api()
    root, draw, draw_sha, supp, supp_sha = _artifacts(tmp_path)
    with pytest.raises(prepare.PreparationError, match="digest mismatch"):
        api.prepare_paired_bird(
            root, draw, supp,
            expected_draw_sha256="0" * 64 if bad == "draw" else draw_sha,
            expected_supplement_sha256="0" * 64 if bad == "supplement" else supp_sha,
            fixture=True)


@pytest.mark.parametrize("field,value", [
    ("identity", ""), ("identity", True), ("sampling_identity", []),
    ("action_max_rows", True), ("action_max_rows", 0),
    ("action_max_rows", 200.0), ("query_timeout_s", True),
    ("query_timeout_s", float("inf")), ("query_timeout_s", float("nan")),
    ("query_timeout_s", 0), ("budget", {}),
    ("max_turns", True), ("max_turns", 8.0), ("max_turns", 0),
    ("max_retries", True), ("max_retries", -1),
    ("retry_on", []), ("retry_on", (True,)),
    ("rollout_timeout", float("inf")), ("rollout_timeout", True),
    ("program_timeout", float("nan")), ("program_timeout", -1),
])
def test_b_instrument_exact_types_finite_caps_zero_dispatch(tmp_path, field, value):
    api = _api()
    plan = _plan(tmp_path, api)
    instrument = _instrument(api)
    if field in ("max_turns", "max_retries", "retry_on",
                 "rollout_timeout", "program_timeout"):
        instrument = dataclasses.replace(
            instrument, budget=dataclasses.replace(instrument.budget, **{field: value}))
    else:
        instrument = dataclasses.replace(instrument, **{field: value})
    calls = []

    async def driver(request):
        calls.append(request)
        for task in request.tasks:
            yield _outcome(api, request, task)

    with pytest.raises(api.PairedBirdError, match="instrument"):
        asyncio.run(api.run_paired_bird(
            plan, run_arm=driver, instrument=instrument,
            policy_identity="fixture", num_rollouts=1))
    assert calls == []
    # Invalid inputs must not consume an otherwise admitted plan.
    assert _run(api, plan, driver).status == "complete"


def test_b_copied_or_constructed_plan_has_no_authority(tmp_path):
    import copy

    api = _api()
    plan = _plan(tmp_path, api)
    calls = []

    async def driver(request):
        calls.append(request)
        for task in request.tasks:
            yield _outcome(api, request, task)

    for forged in (
        dataclasses.replace(plan), copy.copy(plan),
        api.PairedBirdPlan(plan.plan_id, plan.draw),
    ):
        with pytest.raises(api.PairedBirdError, match="admission"):
            _run(api, forged, driver)
        with pytest.raises(api.PairedBirdError, match="admission"):
            api.adjudicate_paired_bird(forged, (), ())
    assert calls == []
    assert _run(api, plan, driver).status == "complete"


@pytest.mark.parametrize("changes", [
    {"max_retries": 1}, {"retry_on": ("TransportError",)},
], ids=["retry-count", "retry-policy"])
def test_b_review_zero_retry_admission_does_not_consume_plan(tmp_path, changes):
    api = _api()
    plan = _plan(tmp_path, api)
    instrument = _instrument(api)
    unsupported = dataclasses.replace(
        instrument, budget=dataclasses.replace(instrument.budget, **changes))
    calls = []

    async def driver(request):
        calls.append(request.arm)
        for task in request.tasks:
            yield _outcome(api, request, task)

    with pytest.raises(api.PairedBirdError, match="instrument|retr"):
        asyncio.run(api.run_paired_bird(
            plan, run_arm=driver, instrument=unsupported,
            policy_identity="fixture", num_rollouts=1))
    assert calls == [], "UNSUPPORTED_RETRY_SETTINGS_DISPATCHED"
    assert _run(api, plan, driver).status == "complete"
    assert calls == ["bash", "ptc"]


@pytest.mark.parametrize("mode", ["complete", "failure", "cancellation", "direct"])
def test_b_review_nonfixture_host_results_never_measurements(tmp_path, monkeypatch, mode):
    from bench import fixture
    from bench.test_prepare import _freeze, _write_corpus

    api = _api()
    records = fixture.records()
    records[0]["SQL"] = "SELECT * FROM absent_nonfixture_test_table"
    root = _write_corpus(tmp_path / "temporary-synthetic-corpus", records)
    draw, supp = tmp_path / "draw.json", tmp_path / "supplement.json"
    draw_sha = _freeze(prepare, root, draw, fixture=False)
    supp_sha = prepare.validate_draw(root, draw, supp, expected_draw_sha256=draw_sha)
    original = prepare.load_validated_draw
    admitted = []

    def actual_consumer(*args, **kwargs):
        result = original(*args, **kwargs)
        admitted.append(result)
        assert kwargs["fixture"] is False
        return result

    monkeypatch.setattr(prepare, "load_validated_draw", actual_consumer)
    plan = api.prepare_paired_bird(
        root, draw, supp, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha, fixture=False)
    assert len(admitted) == 1 and plan.draw is admitted[0]
    assert len(plan.draw.eligible) == 7

    async def driver(request):
        for index, task in enumerate(request.tasks):
            if request.arm == "bash" and index == 1:
                if mode == "failure":
                    raise RuntimeError("PRIVATE_NONFIXTURE_SENTINEL")
                if mode == "cancellation":
                    raise asyncio.CancelledError("PRIVATE_NONFIXTURE_SENTINEL")
            yield _outcome(api, request, task)

    if mode == "direct":
        arms = []
        for arm in ("bash", "ptc"):
            request = api.ArmRequest(
                plan.plan_id, arm, plan.draw.eligible, _instrument(api), "fixture", 1)
            arms.append(tuple(_outcome(api, request, task) for task in request.tasks))
        result = api.adjudicate_paired_bird(plan, *arms)
    elif mode == "cancellation":
        with pytest.raises(asyncio.CancelledError) as caught:
            _run(api, plan, driver)
        result = caught.value.paired_bird_result
    else:
        result = _run(api, plan, driver)
    assert result.status == ("complete" if mode in ("complete", "direct") else "void")
    assert result.fixture is False
    assert result.measurement is False, "HOST_SEAM_MISLABELLED_AS_MEASUREMENT"
