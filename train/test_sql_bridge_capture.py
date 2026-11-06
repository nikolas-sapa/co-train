"""Scripted host lifecycle contracts, not native rollout or training evidence.

Positive paths use real temporary SQLite, PTC callbacks, capture and scoring.
Call-through spies count real work. Fault doubles target private seams only.
Future API access stays in test calls/assertions, never collection or setup.
"""

from __future__ import annotations

import builtins
import dataclasses
import importlib
import inspect
import pathlib
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

PROGRAM = 'print(execute_sql(query="SELECT amount FROM readings")[0]["amount"])'
FINAL_SQL = "```sql\nSELECT amount FROM readings;\n```"
SCRIPTED_FINAL = [{"role": "assistant", "content": FINAL_SQL}]


@pytest.fixture(autouse=True)
def no_model_stack(monkeypatch):
    original_import = builtins.__import__
    original_module = importlib.import_module
    attempted = []
    forbidden = {
        "torch", "trl", "unsloth", "unsloth_zoo", "transformers", "vllm",
        "verifiers", "datasets", "huggingface_hub", "httpx", "pydantic",
        "openai", "anthropic", "litellm", "modal",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"framework/provider import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    yield
    assert attempted == []


@pytest.fixture
def modules():
    from train import ex_reward, grpo_ptc, guards, sql_bridge, sql_capture, sql_episodes, sql_reporting

    return SimpleNamespace(
        bridge=sql_bridge, capture=sql_capture, evidence=sql_episodes,
        reporting=sql_reporting, ptc=grpo_ptc, guards=guards, reward=ex_reward,
    )


@pytest.fixture
def task(tmp_path):
    from bench.task import SqlTask

    directory = tmp_path / "fixture"
    directory.mkdir()
    database = directory / "fixture.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
        connection.execute("INSERT INTO readings VALUES (17)")
        connection.commit()
    finally:
        connection.close()
    return SqlTask(
        name="repeated-task", question="What amount is recorded?",
        evidence="Use the readings table.",
        gold_sql="SELECT amount FROM readings /* GOLD_ONLY_SCRIPTED_FIXTURE */",
        db_id="fixture", db_path=str(database), tier="simple",
        tier_source="derived", shape="fixture-select", coarse_shape="fixture-select",
        source="fixture",
    )


@pytest.fixture
def declarations(modules):
    ids = tuple(modules.evidence.EpisodeIds(
        corpus_id="temporary-sqlite", split_id="offline-host-contract",
        run_id="scripted-host-run", episode_id=episode_id,
        policy_id="declared-fixture-policy", policy_revision="fixture-v1",
    ) for episode_id in ("explicit-host-first", "explicit-host-second"))
    requested = []

    def capture_ids(task_id):
        declaration = ids[len(requested)]
        requested.append(task_id)
        return declaration

    return SimpleNamespace(ids=ids, requested=requested, callback=capture_ids)


@pytest.fixture
def calls(modules, monkeypatch):
    actual_start = modules.capture.start_capture
    actual_builder = modules.ptc.sql_environment
    actual_step = modules.capture._CaptureSession.step
    actual_score = modules.evidence._score
    observed = SimpleNamespace(
        sessions=[], environments=[], builder_kwargs=[], dispatches=[],
        steps=[], scores=[],
    )

    def builder(task, root=modules.guards.REPO_ROOT, **kwargs):
        prompt, environment = actual_builder(task, root=root, **kwargs)
        execute = environment._executor

        def dispatch(code):
            observed.dispatches.append((environment, code))
            return execute(code)

        environment._executor = dispatch
        observed.environments.append(environment)
        observed.builder_kwargs.append((root, kwargs))
        return prompt, environment

    def start(*args, **kwargs):
        session = actual_start(*args, **kwargs)
        observed.sessions.append(session)
        return session

    def step(session, code):
        observed.steps.append((session, code))
        return actual_step(session, code)

    def score(*args, **kwargs):
        observed.scores.append((args, kwargs))
        return actual_score(*args, **kwargs)

    monkeypatch.setattr(modules.ptc, "sql_environment", builder)
    monkeypatch.setattr(modules.capture, "start_capture", start)
    if getattr(modules.bridge, "start_capture", None) is actual_start:
        monkeypatch.setattr(modules.bridge, "start_capture", start)
    monkeypatch.setattr(modules.capture._CaptureSession, "step", step)
    monkeypatch.setattr(modules.evidence, "_score", score)
    return observed


def _prepare(modules, task, tmp_path, declarations, sink):
    return modules.bridge.prepare_sql_training(
        [task], tmp_path, reporting=modules.reporting.ReportingConfig(),
        capture_ids=declarations.callback, capture_sink=sink,
    )


def _report(detail):
    return f'print(report_defect(kind="other", detail={detail!r}))'


def _details(modules, snapshot):
    document = modules.reporting.snapshot_to_dict(snapshot)
    assert document["arms"]["bash"]["events"] == []
    events = document["arms"]["ptc"]["events"]
    assert document["arms"]["ptc"]["reports"] == len(events)
    assert document["total_events"] == len(events)
    assert all(event["type"] == "report" for event in events)
    assert all(event["provenance"] == "catalog_callback" for event in events)
    return [event["detail"] for event in events]


def _diagnostic(modules, capture, details):
    assert type(capture) is modules.capture.SqlCapture
    assert capture.schema_version == 3
    assert capture.terminal_label == "aborted"
    assert capture.final_answer is capture.extracted_sql is capture.result is None
    assert _details(modules, capture.telemetry) == details
    assert modules.capture.decode_capture(modules.capture.encode_capture(capture)) == capture


def _closed(environment):
    with pytest.raises(RuntimeError):
        environment.run_program(PROGRAM)
    with pytest.raises(RuntimeError):
        environment._finish_rollout(SCRIPTED_FINAL)


def _retain_diagnostic(environment, retained):
    if not retained:
        environment._abort_rollout()
    assert len(retained) == 1
    return retained[0]


def test_capture_backed_sql_rollout(
    modules, task, tmp_path, declarations, calls, monkeypatch,
):
    from ptc.sql_qa import report_ack

    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    assert calls.sessions == [] and declarations.requested == []
    assert len(calls.environments) == 1
    assert environment.reset(**prepared.dataset_rows[0]) is None
    assert len(calls.sessions) == 1 and len(calls.environments) == 2
    (session,) = calls.sessions
    assert session.prompt == prepared.dataset_rows[0]["prompt"][0]["content"]
    assert task.gold_sql not in session.prompt
    assert environment.run_program(PROGRAM) == "17"
    report = _report("scripted real callback")
    assert environment.run_program(report) == report_ack()
    assert calls.steps == [(session, PROGRAM), (session, report)]
    assert calls.dispatches == [(calls.environments[-1], PROGRAM),
                                (calls.environments[-1], report)]

    actual_snapshot = type(session).reporting_snapshot.fget
    reads = []

    def reporting_snapshot(current):
        reads.append(current)
        return actual_snapshot(current)

    monkeypatch.setattr(type(session), "reporting_snapshot", property(reporting_snapshot))
    assert _details(modules, environment.reporting_snapshot) == ["scripted real callback"]
    assert reads == [session]
    assert calls.scores == [] and retained == []
    reward = modules.reward.make_execution_reward(tmp_path)
    assert reward(
        [SCRIPTED_FINAL], answer=[task.gold_sql], db_id=[task.db_id],
    ) == [1.0]
    assert calls.scores == [] and retained == []
    capture = environment._finish_rollout(SCRIPTED_FINAL)
    assert retained == [capture] and retained[0] is capture
    assert capture.ids == declarations.ids[0]
    assert capture.schema_version == 3 and capture.origin == "incremental_execution"
    assert capture.terminal_label == "final_submitted" and capture.result.score == 1.0
    assert capture.final_answer == FINAL_SQL
    assert [(step.action, step.observation) for step in capture.steps] == [
        (PROGRAM, "17"), (report, report_ack()),
    ]
    assert _details(modules, capture.telemetry) == ["scripted real callback"]
    assert len(calls.scores) == 1 and len(calls.dispatches) == 2
    encoded = modules.capture.encode_capture(capture)
    assert modules.capture.decode_capture(encoded) == capture
    assert modules.capture.encode_capture(modules.capture.decode_capture(encoded)) == encoded
    with pytest.raises(dataclasses.FrozenInstanceError):
        capture.final_answer = "SELECT 0"
    assert reward(
        [SCRIPTED_FINAL], answer=[task.gold_sql], db_id=[task.db_id],
    ) == [1.0]
    assert len(calls.scores) == 1 and retained == [capture]
    assert len(calls.dispatches) == 2
    _closed(environment)


def test_reused_environment_retains_independent_rollouts(
    modules, task, tmp_path, declarations, calls,
):
    from ptc.sql_qa import report_ack

    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    assert declarations.requested == []
    first_bytes = None
    for index, detail in enumerate(("first-only", "second-only")):
        environment.reset(**prepared.dataset_rows[0])
        assert environment.turns_used == 0
        assert _details(modules, environment.reporting_snapshot) == []
        if index:
            assert modules.capture.encode_capture(retained[0]) == first_bytes
        assert environment.run_program(_report(detail)) == report_ack()
        capture = environment._finish_rollout(SCRIPTED_FINAL)
        assert capture.ids == declarations.ids[index]
        assert _details(modules, capture.telemetry) == [detail]
        if not index:
            first_bytes = modules.capture.encode_capture(capture)
    assert declarations.requested == [task.name, task.name]
    assert len(retained) == len(calls.sessions) == 2
    assert len(calls.environments) == 3
    assert calls.environments[-1] is not calls.environments[-2]
    assert retained[0].ids != retained[1].ids
    assert retained[0].task_id == retained[1].task_id == task.name
    assert modules.capture.encode_capture(retained[0]) == first_bytes
    assert _details(modules, retained[0].telemetry) == ["first-only"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        retained[0].ids.episode_id = "crossed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        retained[0].telemetry.data = b"crossed"


@pytest.mark.parametrize("failure_kind", ("execution", "binding", "finalization"))
def test_failure_cannot_seal_success(
    modules, task, tmp_path, declarations, calls, monkeypatch, failure_kind,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    environment.run_program(_report("before failure"))
    failure = RuntimeError(f"private {failure_kind} fault")
    expected_details = ["before failure"]
    if failure_kind == "execution":
        execute = calls.environments[-1]._executor

        def failing(code):
            execute(_report("during failure"))
            raise failure

        monkeypatch.setattr(calls.environments[-1], "_executor", failing)
        expected_details.append("during failure")
    elif failure_kind == "binding":
        connection = sqlite3.connect(task.db_path)
        try:
            connection.execute("UPDATE readings SET amount = 29")
            connection.commit()
        finally:
            connection.close()
    else:
        def failing(*args, **kwargs):
            raise failure

        monkeypatch.setattr(modules.evidence, "_score", failing)
    expected_error = ValueError if failure_kind == "binding" else RuntimeError
    with pytest.raises(expected_error) as caught:
        if failure_kind == "finalization":
            environment._finish_rollout(SCRIPTED_FINAL)
        else:
            environment.run_program(PROGRAM)
    if failure_kind != "binding":
        assert caught.value is failure
    assert _details(modules, environment.reporting_snapshot) == expected_details
    capture = _retain_diagnostic(environment, retained)
    _diagnostic(modules, capture, expected_details)
    _closed(environment)
    assert len(retained) == 1
    assert not any(record.terminal_label == "final_submitted" for record in retained)


def test_original_execution_contract(modules, task, tmp_path, declarations, calls):
    retained = []
    baseline = modules.bridge.prepare_sql_training(
        [task], tmp_path, reporting=modules.reporting.ReportingConfig(),
    )
    captured = _prepare(modules, task, tmp_path, declarations, retained.append)
    plain_environment = baseline.environment_factory()
    environment = captured.environment_factory()
    plain_environment.reset(**baseline.dataset_rows[0])
    environment.reset(**captured.dataset_rows[0])
    tools = [
        (name, method) for name, method in inspect.getmembers(environment, inspect.ismethod)
        if not name.startswith("_") and name not in ("reset", "get_reward")
    ]
    assert [name for name, _ in tools] == ["run_program"]
    assert environment.run_program.__func__ is plain_environment.run_program.__func__
    assert inspect.signature(environment.run_program) == inspect.signature(
        plain_environment.run_program,
    )
    signature = inspect.signature(environment.run_program)
    assert list(signature.parameters) == ["code"]
    assert signature.parameters["code"].annotation == "str"
    assert signature.return_annotation is inspect.Signature.empty
    assert inspect.getdoc(environment.run_program) == (
        "Execute a Python program against the typed catalog.\n\n"
        "Args:\n    code: The program."
    )
    assert calls.environments[-1].tools == (modules.ptc.THE_TOOL_SCHEMA,)
    assert modules.ptc.THE_TOOL_SCHEMA == {
        "type": "function",
        "function": {
            "name": "run_program",
            "description": "Execute a Python program against the typed catalog.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "The program."}},
                "required": ["code"],
            },
        },
    }
    assert captured.max_tool_calling_iterations == baseline.max_tool_calling_iterations == 8
    for turn in range(1, 9):
        assert environment.run_program(PROGRAM) == plain_environment.run_program(PROGRAM) == "17"
        assert environment.turns_used == plain_environment.turns_used == turn
    assert len(calls.dispatches) == 16
    refusal = modules.guards.TurnBudget(max_turns=8).exhausted_message()
    assert environment.run_program(PROGRAM) == plain_environment.run_program(PROGRAM) == refusal
    assert len(calls.dispatches) == 16
    capture = environment._finish_rollout(SCRIPTED_FINAL)
    assert len(capture.steps) == 8 and len(capture.refusals) == 1
    for reward in (baseline.reward, modules.reward.make_execution_reward(tmp_path)):
        assert reward(
            [SCRIPTED_FINAL], answer=[task.gold_sql], db_id=[task.db_id],
        ) == [1.0]
    assert len(calls.dispatches) == 16


@pytest.mark.parametrize("reporting_enabled", (False, True))
def test_disabled_path_unchanged(
    modules, task, tmp_path, calls, reporting_enabled, monkeypatch,
):
    def forbidden(*args, **kwargs):
        pytest.fail("capture-disabled bridge created a capture session")

    original = modules.capture.start_capture
    monkeypatch.setattr(modules.capture, "start_capture", forbidden)
    if getattr(modules.bridge, "start_capture", None) is original:
        monkeypatch.setattr(modules.bridge, "start_capture", forbidden)
    kwargs = ({"reporting": modules.reporting.ReportingConfig()} if reporting_enabled else {})
    prepared = modules.bridge.prepare_sql_training([task], tmp_path, **kwargs)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    assert len(calls.environments) == 2 and calls.sessions == []
    for root, builder_kwargs in calls.builder_kwargs:
        assert root == modules.guards.REPO_ROOT
        assert set(builder_kwargs) == ({"qa"} if reporting_enabled else set())
    assert environment.run_program(PROGRAM) == "17"
    assert prepared.reward(
        [SCRIPTED_FINAL], answer=[task.gold_sql], db_id=[task.db_id],
    ) == [1.0]
    assert calls.scores == []
    if reporting_enabled:
        from ptc.sql_qa import report_ack

        assert environment.run_program(_report("reporting-only")) == report_ack()
        assert _details(modules, environment.reporting_snapshot) == ["reporting-only"]
    else:
        assert environment.reporting_snapshot is None
    assert calls.sessions == []


@pytest.mark.parametrize("terminal", ("finish", "abort"))
def test_sink_ownership(modules, task, tmp_path, declarations, calls, terminal):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    environment.run_program(_report("caller owns retention"))
    operation = (lambda: environment._finish_rollout(SCRIPTED_FINAL)) if terminal == "finish" else (
        environment._abort_rollout
    )
    capture = operation()
    assert retained == [capture] and retained[0] is capture
    assert type(capture) is modules.capture.SqlCapture
    if terminal == "finish":
        assert capture.terminal_label == "final_submitted"
        assert capture.result.score == 1.0 and len(calls.scores) == 1
    else:
        _diagnostic(modules, capture, ["caller owns retention"])
        assert calls.scores == []
    before = modules.capture.encode_capture(capture)
    for repeated in (operation, environment._abort_rollout):
        try:
            repeated()
        except RuntimeError:
            pass
        assert retained == [capture]
    _closed(environment)
    assert modules.capture.encode_capture(retained[0]) == before
    assert len(calls.scores) == (1 if terminal == "finish" else 0)


@pytest.mark.parametrize("terminal", ("finish", "abort", "reset"))
def test_sink_failure_prevents_reuse(
    modules, task, tmp_path, declarations, calls, terminal,
):
    failure = RuntimeError("caller sink unavailable")
    attempted = []

    def sink(capture):
        attempted.append(capture)
        raise failure

    prepared = _prepare(modules, task, tmp_path, declarations, sink)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    environment.run_program(_report("not silently discarded"))
    with pytest.raises(RuntimeError) as caught:
        if terminal == "finish":
            environment._finish_rollout(SCRIPTED_FINAL)
        elif terminal == "abort":
            environment._abort_rollout()
        else:
            environment.reset(**prepared.dataset_rows[0])
    assert caught.value is failure and len(attempted) == 1
    assert type(attempted[0]) is modules.capture.SqlCapture
    assert _details(modules, attempted[0].telemetry) == ["not silently discarded"]
    if terminal != "finish":
        _diagnostic(modules, attempted[0], ["not silently discarded"])
    assert len(calls.sessions) == 1 and declarations.requested == [task.name]
    dispatch_count = len(calls.dispatches)
    _closed(environment)
    try:
        environment._abort_rollout()
    except RuntimeError:
        pass
    assert len(attempted) == 1 and len(calls.dispatches) == dispatch_count


def test_primary_execution_exception_survives_sink_failure(
    modules, task, tmp_path, declarations, calls, monkeypatch,
):
    primary = OSError("private execution failure")
    secondary = RuntimeError("diagnostic sink failure")
    attempted = []

    def sink(capture):
        attempted.append(capture)
        raise secondary

    prepared = _prepare(modules, task, tmp_path, declarations, sink)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    execute = calls.environments[-1]._executor

    def failing(code):
        execute(_report("real report before raised executor fault"))
        raise primary

    monkeypatch.setattr(calls.environments[-1], "_executor", failing)
    with pytest.raises(OSError) as caught:
        environment.run_program(PROGRAM)
    assert caught.value is primary
    assert len(attempted) == 1
    _diagnostic(modules, attempted[0], ["real report before raised executor fault"])
    _closed(environment)
    assert len(attempted) == 1


def test_snapshot_is_observation(modules, task, declarations, calls, monkeypatch):
    from ptc.sql_qa import report_ack

    session = modules.capture.start_capture(
        task, ids=declarations.ids[0], allow_execution=True,
        reporting=modules.reporting.ReportingConfig(),
    )
    assert isinstance(getattr(type(session), "snapshot", None), property), (
        "capture session lacks readonly SqlCapture snapshot"
    )
    assert session.step(_report("before snapshot")) == report_ack()
    dispatch_count = len(calls.dispatches)
    first = session.snapshot
    before = modules.capture.encode_capture(first)
    second = session.snapshot
    assert first == second
    _diagnostic(modules, first, ["before snapshot"])
    with pytest.raises(AttributeError):
        session.snapshot = first
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.steps = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.telemetry.data = b"changed"
    assert len(calls.dispatches) == dispatch_count and calls.scores == []

    execute = calls.environments[-1]._executor
    failure = OSError("private execution fault after real report")

    def failing(code):
        execute(_report("during invalidation"))
        raise failure

    monkeypatch.setattr(calls.environments[-1], "_executor", failing)
    with pytest.raises(OSError) as caught:
        session.step(PROGRAM)
    assert caught.value is failure
    dispatch_count = len(calls.dispatches)
    invalidated = session.snapshot
    _diagnostic(modules, invalidated, ["before snapshot", "during invalidation"])
    assert modules.capture.encode_capture(first) == before
    assert len(calls.dispatches) == dispatch_count and calls.scores == []
    assert len(invalidated.steps) == 1
    for operation in (
        lambda: session.step(PROGRAM), lambda: session.finish(FINAL_SQL), session.abort,
    ):
        with pytest.raises(RuntimeError):
            operation()
    assert calls.scores == [] and len(calls.dispatches) == dispatch_count


@pytest.mark.parametrize("configuration", ("ids-only", "sink-only", "no-reporting"))
def test_capture_configuration_requires_pair_and_reporting(
    modules, task, tmp_path, declarations, calls, configuration,
):
    parameters = inspect.signature(modules.bridge.prepare_sql_training).parameters
    for name in ("capture_ids", "capture_sink"):
        assert name in parameters, f"missing capture-backed bridge parameter: {name}"
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    retained = []
    kwargs = {
        "reporting": modules.reporting.ReportingConfig(),
        "capture_ids": declarations.callback,
        "capture_sink": retained.append,
    }
    if configuration == "ids-only":
        del kwargs["capture_sink"]
    elif configuration == "sink-only":
        del kwargs["capture_ids"]
    else:
        del kwargs["reporting"]
    with pytest.raises((TypeError, ValueError)):
        modules.bridge.prepare_sql_training([task], tmp_path, **kwargs)
    assert calls.sessions == [] and declarations.requested == [] and retained == []


def test_reset_publishes_abandoned_capture_before_invalid_row(
    modules, task, tmp_path, declarations, calls,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    environment.run_program(_report("unfinished rollout"))
    environment.reset(**prepared.dataset_rows[0])
    assert len(retained) == 1
    _diagnostic(modules, retained[0], ["unfinished rollout"])
    first_bytes = modules.capture.encode_capture(retained[0])
    assert retained[0].ids == declarations.ids[0]
    assert environment.turns_used == 0
    assert _details(modules, environment.reporting_snapshot) == []
    environment.run_program(_report("second unfinished rollout"))
    row = dict(prepared.dataset_rows[0], task_id="not-prepared")
    with pytest.raises(ValueError):
        environment.reset(**row)
    assert len(retained) == 2
    _diagnostic(modules, retained[1], ["second unfinished rollout"])
    assert retained[1].ids == declarations.ids[1]
    assert modules.capture.encode_capture(retained[0]) == first_bytes
    assert len(calls.sessions) == 2 and declarations.requested == [task.name, task.name]
    assert len(calls.environments) == 3
    assert environment.turns_used == 0 and environment.reporting_snapshot is None
    with pytest.raises(RuntimeError):
        environment.run_program(PROGRAM)
    assert calls.scores == []


@pytest.mark.parametrize("completion", (
    [{"role": "tool", "content": FINAL_SQL}],
    [{"role": "assistant", "content": FINAL_SQL, "tool_calls": [
        {"type": "function", "function": {"name": "run_program", "arguments": {}}},
    ]}],
    [],
), ids=("tool-tail", "assistant-tool-call", "no-messages"))
def test_missing_final_never_submits_tool_text(
    modules, task, tmp_path, declarations, calls, completion,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    environment.run_program(_report("before missing final"))
    try:
        result = environment._finish_rollout(completion)
    except (ValueError, RuntimeError):
        result = None
    if result is not None:
        _diagnostic(modules, result, ["before missing final"])
    capture = _retain_diagnostic(environment, retained)
    _diagnostic(modules, capture, ["before missing final"])
    assert calls.scores == []
    _closed(environment)
    assert len(retained) == 1


def test_genuine_empty_assistant_final_uses_existing_scorer(
    modules, task, tmp_path, declarations, calls,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    completion = [{"role": "assistant", "content": "", "tool_calls": []}]
    capture = environment._finish_rollout(completion)
    assert retained == [capture] and capture.terminal_label == "final_submitted"
    assert capture.final_answer == capture.extracted_sql == ""
    assert capture.result.score == 0.0
    assert len(calls.scores) == 1 and calls.dispatches == []
    reward = modules.reward.make_execution_reward(tmp_path)
    assert reward(
        [completion], answer=[task.gold_sql], db_id=[task.db_id],
    ) == [0.0]
    assert len(calls.scores) == 1 and retained == [capture]


def test_returned_program_error_is_not_execution_abort(
    modules, task, tmp_path, declarations, calls,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    config = modules.reporting.ReportingConfig()
    _, direct = modules.ptc.sql_environment(
        task, qa=modules.reporting.make_channel(config),
    )
    program = _report("before arithmetic error") + "\nprint(1 / 0)"
    expected = direct.step(program)
    assert expected.startswith("error: ZeroDivisionError:")
    assert environment.run_program(program) == expected
    assert environment.turns_used == 1
    assert _details(modules, environment.reporting_snapshot) == ["before arithmetic error"]
    assert retained == [] and calls.scores == []
    assert environment.run_program(PROGRAM) == "17"
    capture = environment._finish_rollout(SCRIPTED_FINAL)
    assert capture.terminal_label == "final_submitted" and capture.result.score == 1.0
    assert len(capture.steps) == 2 and capture.steps[0].observation == expected
    assert _details(modules, capture.telemetry) == ["before arithmetic error"]
    reward = modules.reward.make_execution_reward(tmp_path)
    assert reward(
        [SCRIPTED_FINAL], answer=[task.gold_sql], db_id=[task.db_id],
    ) == [1.0]


def test_start_capture_forwards_root_without_changing_defaults(
    modules, task, tmp_path, declarations, calls, monkeypatch,
):
    copied_root = tmp_path / "root"
    harness_directory = copied_root / "ptc"
    harness_directory.mkdir(parents=True)
    (harness_directory / "harness.py").write_bytes(
        (modules.guards.REPO_ROOT / "ptc" / "harness.py").read_bytes(),
    )
    original_cap = modules.guards.eval_max_turns
    roots = []

    def cap(root=modules.guards.REPO_ROOT):
        roots.append(root)
        return original_cap(root)

    monkeypatch.setattr(modules.guards, "eval_max_turns", cap)
    session = modules.capture.start_capture(
        task, ids=declarations.ids[0], allow_execution=True,
        reporting=modules.reporting.ReportingConfig(), root=copied_root,
    )
    assert roots == [copied_root]
    assert len(calls.environments) == 1 and calls.builder_kwargs[0][0] == copied_root
    assert calls.environments[0].max_turns == 8
    assert session.step(PROGRAM) == "17"
    explicit = session.abort()
    assert explicit.instrument.action_cap == 8
    default_session = modules.capture.start_capture(
        task, ids=declarations.ids[1], allow_execution=True,
        reporting=modules.reporting.ReportingConfig(),
    )
    assert calls.builder_kwargs[-1][0] == modules.guards.REPO_ROOT
    assert default_session.step(PROGRAM) == "17"
    assert default_session.abort().instrument.action_cap == 8
    assert calls.scores == []


def test_consumed_turns_survive_execution_invalidation(
    modules, task, tmp_path, declarations, calls, monkeypatch,
):
    retained = []
    prepared = _prepare(modules, task, tmp_path, declarations, retained.append)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    (session,) = calls.sessions
    actual_environment = calls.environments[-1]
    report = _report("before consumed-turn failure")
    observation = environment.run_program(report)
    completed = session.snapshot.steps
    assert len(completed) == 1
    assert completed[0].action == report and completed[0].observation == observation
    assert _details(modules, environment.reporting_snapshot) == ["before consumed-turn failure"]
    assert environment.turns_used == actual_environment.turns_used == 1
    assert calls.dispatches == [(actual_environment, report)]
    assert retained == []
    execute = actual_environment._executor
    failure = RuntimeError("post-execution consumed-turn sentinel")
    observations = []

    def failing(code):
        observations.append(execute(code))
        raise failure

    monkeypatch.setattr(actual_environment, "_executor", failing)
    with pytest.raises(RuntimeError) as caught:
        environment.run_program(PROGRAM)
    assert caught.value is failure
    assert observations == ["17"]
    assert calls.dispatches == [(actual_environment, report), (actual_environment, PROGRAM)]
    assert calls.steps == [(session, report), (session, PROGRAM)]
    assert len(retained) == 1
    capture = retained[0]
    _diagnostic(modules, capture, ["before consumed-turn failure"])
    assert capture.steps == completed and len(capture.steps) == 1
    assert session.snapshot.steps == completed
    assert capture.refusals == ()
    _closed(environment)
    with pytest.raises(RuntimeError):
        environment._abort_rollout()
    with pytest.raises(RuntimeError):
        session.step(PROGRAM)
    assert retained == [capture]
    assert calls.dispatches == [(actual_environment, report), (actual_environment, PROGRAM)]
    assert calls.steps == [(session, report), (session, PROGRAM), (session, PROGRAM)]
    assert observations == ["17"] and calls.scores == []
    assert actual_environment.turns_used == 2
    assert environment.turns_used == 2
