"""Offline native-shaped reward dispatch, not TRL/runtime acceptance."""

from __future__ import annotations

import copy
from dataclasses import replace
from functools import wraps
from types import SimpleNamespace

import pytest

from train.test_native_training_reporting import (  # noqa: F401
    native_wiring,
    no_frameworks,
    sql_tasks,
)
from train.test_sql_training_run_reporting import callback_base  # noqa: F401


PROGRAM = 'print(execute_sql(query="SELECT amount FROM readings")[0]["amount"])'
SQL = "SELECT amount FROM readings"
REJECT = (TypeError, ValueError, RuntimeError)


def _declared_ids(count):
    from train.sql_episodes import EpisodeIds

    return [
        EpisodeIds(
            corpus_id="temporary-sql-fixture", split_id="engineering-only",
            run_id="native-shaped-reward", episode_id=f"declared-{index}",
            policy_id="scripted-policy", policy_revision="fixture-v1",
        )
        for index in range(count)
    ]


def _prepare(tasks, db_root, *, count, sink=None):
    from train import sql_bridge, sql_reporting

    declarations = _declared_ids(count)
    issued, captures = [], []

    def capture_ids(task_id):
        assert task_id in {task.name for task in tasks}
        ids = declarations[len(issued)]
        issued.append((task_id, ids))
        return ids

    capture_sink = captures.append if sink is None else sink
    inputs = sql_bridge.prepare_sql_training(
        tasks, db_root, reporting=sql_reporting.ReportingConfig(),
        capture_ids=capture_ids, capture_sink=capture_sink,
    )
    assert issued == captures == []
    return SimpleNamespace(
        inputs=inputs, captures=captures, issued=issued,
        declarations=declarations,
    )


def _completion(text=SQL):
    return [{"role": "assistant", "content": text}]


def _tool_ending():
    return [
        {"role": "assistant", "content": "", "tool_calls": [{
            "type": "function", "id": "scripted-call",
            "function": {"name": "run_program", "arguments": '{"code":"print(17)"}'},
        }]},
        {"role": "tool", "tool_call_id": "scripted-call", "content": SQL},
    ]


def _reward_kwargs(rows, environments, completions):
    return {
        "prompts": [copy.deepcopy(row["prompt"]) for row in rows],
        "completions": completions,
        "completion_ids": [[] for _ in rows],
        "task_id": [row["task_id"] for row in rows],
        "answer": [row["answer"] for row in rows],
        "db_id": [row["db_id"] for row in rows],
        "environments": environments,
    }


def _dispatch(inputs, rows, environments, completions):
    return inputs.reward(**_reward_kwargs(rows, environments, completions))


def _report(environment, detail, amount):
    from ptc.sql_qa import report_ack
    from train.sql_reporting import snapshot_to_dict

    code = PROGRAM + f'\nprint(report_defect(kind="other", detail={detail!r}))'
    observation = environment.run_program(code)
    assert observation.splitlines() == [str(amount), report_ack()]
    snapshot = snapshot_to_dict(environment.reporting_snapshot)
    assert snapshot["total_events"] == 1
    assert snapshot["arms"]["ptc"]["reports"] == 1
    assert snapshot["arms"]["bash"]["events"] == []
    assert snapshot["arms"]["ptc"]["events"] == [{
        "arm": "ptc", "seq": 1, "type": "report",
        "provenance": "catalog_callback", "kind": "other", "detail": detail,
    }]
    return code, observation


def _assert_capture(capture, *, ids, row, detail, action):
    from train import sql_capture, sql_reporting

    assert type(capture) is sql_capture.SqlCapture
    assert capture.schema_version == 3
    assert capture.origin == "incremental_execution"
    assert capture.arm == "ptc"
    assert capture.ids == ids
    assert capture.task_id == row["task_id"]
    assert capture.prompt == row["prompt"][0]["content"]
    assert [(step.action, step.observation) for step in capture.steps] == [action]
    document = sql_reporting.snapshot_to_dict(capture.telemetry)
    assert document["total_events"] == 1
    assert document["arms"]["ptc"]["reports"] == 1
    assert document["arms"]["ptc"]["events"][0]["detail"] == detail
    assert document["arms"]["bash"]["events"] == []
    encoded = sql_capture.encode_capture(capture)
    decoded = sql_capture.decode_capture(encoded)
    assert decoded == capture
    assert sql_capture.encode_capture(decoded) == encoded
    return encoded


def _execution_spies(monkeypatch, *, failure_at=None, failure=None):
    from bench import score
    from ptc import sql_arms
    from train import ex_reward, sql_bridge, sql_capture, sql_episodes

    original_score = score.execution_accuracy
    original_run = sql_arms.ArmPair.run
    scores, actions = [], []

    @wraps(original_score)
    def execute(*args, **kwargs):
        call = SimpleNamespace(args=args, kwargs=kwargs, result=None)
        scores.append(call)
        if len(scores) == failure_at:
            raise failure
        call.result = original_score(*args, **kwargs)
        return call.result

    @wraps(original_run)
    def run(pair, arm, action, *, bindir=None):
        actions.append((arm, action))
        return original_run(pair, arm, action, bindir=bindir)

    for module in (score, ex_reward, sql_bridge, sql_capture, sql_episodes):
        if getattr(module, "execution_accuracy", None) is original_score:
            monkeypatch.setattr(module, "execution_accuracy", execute)
    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    return scores, actions


def test_reward_dispatch_seals_real_rollouts(sql_tasks, tmp_path):
    state = _prepare(sql_tasks, tmp_path, count=2)
    rows = copy.deepcopy(state.inputs.dataset_rows)
    environments = [state.inputs.environment_factory() for _ in rows]
    actions = []
    for index, (environment, row) in enumerate(zip(environments, rows, strict=True)):
        assert environment.reset(**row) is None
        actions.append(_report(environment, f"rollout-{index}", (17, 29)[index]))
    assert state.captures == []

    rewards = _dispatch(
        state.inputs, rows, environments, [_completion("```sql\n" + SQL + "\n```")] * 2,
    )

    assert rewards == [1.0, 1.0]
    assert len(state.issued) == len(state.captures) == 2
    for index, capture in enumerate(state.captures):
        _assert_capture(
            capture, ids=state.declarations[index], row=rows[index],
            detail=f"rollout-{index}", action=actions[index],
        )
        assert capture.terminal_label == "final_submitted"
        assert capture.extracted_sql == SQL
        assert capture.result.valid is True and capture.result.score == 1.0


def test_repeated_tasks_and_pool_reuse(sql_tasks, tmp_path):
    from train.sql_capture import encode_capture

    state = _prepare(sql_tasks[:1], tmp_path, count=4)
    row = copy.deepcopy(state.inputs.dataset_rows[0])
    environments = [state.inputs.environment_factory() for _ in range(2)]
    assert environments[0] is not environments[1]
    expected = []
    for batch in range(2):
        actions = []
        for index, environment in enumerate(environments):
            environment.reset(**row)
            detail = f"batch-{batch}-instance-{index}"
            actions.append(_report(environment, detail, 17))
        order = [0, 1] if batch == 0 else [1, 0]
        assert _dispatch(
            state.inputs, [row, row], [environments[index] for index in order],
            [_completion(), _completion()],
        ) == [1.0, 1.0]
        for offset, index in enumerate(order):
            capture = state.captures[batch * 2 + offset]
            expected.append(_assert_capture(
                capture, ids=state.declarations[batch * 2 + index], row=row,
                detail=f"batch-{batch}-instance-{index}", action=actions[index],
            ))
            assert capture.terminal_label == "final_submitted"
            assert capture.result.valid is True and capture.result.score == 1.0
        assert [encode_capture(capture) for capture in state.captures] == expected
    assert len(state.issued) == len(state.captures) == 4
    assert len({capture.ids.episode_id for capture in state.captures}) == 4
    assert len({id(capture) for capture in state.captures}) == 4


def test_score_once_preserves_order(sql_tasks, tmp_path, monkeypatch):
    from train import ex_reward

    task = sql_tasks[0]
    tasks = [
        replace(task, name="match"), replace(task, name="mismatch"),
        replace(task, name="invalid-gold", gold_sql="SELECT absent FROM readings"),
        replace(task, name="unfinished"),
    ]
    state = _prepare(tasks, tmp_path, count=4)
    rows = state.inputs.dataset_rows
    environments = [state.inputs.environment_factory() for _ in rows]
    for index, (environment, row) in enumerate(zip(environments, rows, strict=True)):
        environment.reset(**row)
        _report(environment, f"score-row-{index}", 17)
    texts = [SQL, "SELECT amount + 1 FROM readings", SQL, ""]
    expected = ex_reward.make_execution_reward(tmp_path)(
        completions=texts, answer=[row["answer"] for row in rows],
        db_id=[row["db_id"] for row in rows],
    )
    assert expected == [1.0, 0.0, 0.0, 0.0]
    scores, actions = _execution_spies(monkeypatch)

    assert _dispatch(
        state.inputs, rows, environments,
        [_completion(text) for text in texts[:3]] + [_tool_ending()],
    ) == expected

    assert len(scores) == 4
    assert [call.args[0] for call in scores] == texts
    assert [call.args[1].gold_sql for call in scores] == [row["answer"] for row in rows]
    assert actions == []
    assert len(state.captures) == 4
    for index, capture in enumerate(state.captures[:3]):
        assert capture.terminal_label == "final_submitted"
        assert capture.result is scores[index].result
    assert state.captures[2].result.valid is False
    assert state.captures[3].terminal_label == "aborted"
    assert state.captures[3].result is None
    assert state.captures[3].final_answer is None


@pytest.mark.parametrize(
    "case",
    ["foreign-adapter", "duplicate-instance", "wrong-row", "missing-association",
     "stale-reset", "wrong-binding"],
)
def test_native_binding_rejection(sql_tasks, tmp_path, monkeypatch, case):
    state = _prepare(sql_tasks, tmp_path, count=3)
    rows = copy.deepcopy(state.inputs.dataset_rows)
    environments = [state.inputs.environment_factory() for _ in rows]
    for index, (environment, row) in enumerate(zip(environments, rows, strict=True)):
        environment.reset(**row)
        _report(environment, f"binding-row-{index}", (17, 29)[index])
    kwargs = _reward_kwargs(rows, environments, [_completion(), _completion()])
    other = None
    if case == "foreign-adapter":
        kwargs["environments"] = [object(), environments[1]]
    elif case == "duplicate-instance":
        kwargs = _reward_kwargs(
            [rows[0], rows[0]], [environments[0], environments[0]],
            [_completion(), _completion()],
        )
    elif case == "wrong-row":
        kwargs = _reward_kwargs(
            rows[::-1], environments, [_completion(), _completion()],
        )
    elif case == "missing-association":
        del kwargs["environments"]
    elif case == "stale-reset":
        environments[0].reset(**rows[1])
    else:
        other = _prepare(sql_tasks, tmp_path, count=1)
        foreign = other.inputs.environment_factory()
        foreign.reset(**rows[0])
        _report(foreign, "other-preparation", 17)
        kwargs["environments"] = [foreign, environments[1]]
    scores, actions = _execution_spies(monkeypatch)

    with pytest.raises(REJECT):
        state.inputs.reward(**kwargs)

    assert scores == actions == []
    assert not any(
        capture.terminal_label == "final_submitted" for capture in state.captures
    )
    if other is not None:
        assert not any(
            capture.terminal_label == "final_submitted" for capture in other.captures
        )


@pytest.mark.parametrize("failure_kind", ["scorer", "sink"])
def test_partial_failure_publication(sql_tasks, tmp_path, monkeypatch, failure_kind):
    tasks = sql_tasks + [replace(sql_tasks[0], name="unprocessed")]
    sentinel = OSError(f"original {failure_kind} sentinel")
    offered = []

    def failing_sink(capture):
        offered.append(capture)
        raise sentinel

    state = _prepare(
        tasks, tmp_path, count=3,
        sink=failing_sink if failure_kind == "sink" else None,
    )
    rows = state.inputs.dataset_rows
    environments = [state.inputs.environment_factory() for _ in rows]
    for index, (environment, row) in enumerate(zip(environments, rows, strict=True)):
        environment.reset(**row)
        _report(environment, f"failure-row-{index}", (17, 29, 17)[index])
    scores, actions = _execution_spies(
        monkeypatch, failure_at=2 if failure_kind == "scorer" else None,
        failure=sentinel,
    )

    with pytest.raises(OSError) as caught:
        _dispatch(state.inputs, rows, environments, [_completion()] * 3)

    assert caught.value is sentinel
    assert actions == []
    if failure_kind == "scorer":
        assert len(scores) == 2
        assert scores[0].result.valid is True
        assert scores[1].result is None
        successful = [
            capture for capture in state.captures
            if capture.terminal_label == "final_submitted"
        ]
        assert len(successful) == 1
        assert successful[0].ids == state.declarations[0]
        assert successful[0].result is scores[0].result
        assert all(
            capture.terminal_label != "final_submitted"
            for capture in state.captures
            if capture.ids in state.declarations[1:]
        )
    else:
        assert len(scores) == len(offered) == 1
        assert state.captures == []
        assert offered[0].ids == state.declarations[0]
        with pytest.raises(REJECT):
            environments[0].run_program(PROGRAM)
        with pytest.raises(REJECT):
            _dispatch(state.inputs, rows[:1], environments[:1], [_completion()])
        assert len(scores) == len(offered) == 1
        assert actions == []


@pytest.mark.parametrize("ending", ["invalidated-program", "tool-ending"])
def test_failure_and_unfinished_completion(sql_tasks, tmp_path, monkeypatch, ending):
    from ptc import sql_arms
    from train import ex_reward, sql_reporting

    state = _prepare(sql_tasks[:1], tmp_path, count=1)
    row = state.inputs.dataset_rows[0]
    environment = state.inputs.environment_factory()
    environment.reset(**row)
    action = _report(environment, "retained-before-ending", 17)
    if ending == "invalidated-program":
        original = sql_arms.ArmPair.run
        sentinel = OSError("after real program execution")
        executed = []

        def execute_then_fail(pair, arm, code, *, bindir=None):
            observed = original(pair, arm, code, bindir=bindir)
            executed.append((arm, code, observed))
            raise sentinel

        with monkeypatch.context() as fault:
            fault.setattr(sql_arms.ArmPair, "run", execute_then_fail)
            with pytest.raises(OSError) as caught:
                environment.run_program("print('executed-before-fault')")
        assert caught.value is sentinel
        assert executed == [("ptc", "print('executed-before-fault')", "executed-before-fault")]
        completion, text = _completion(), SQL
    else:
        completion, text = _tool_ending(), ""
    expected = ex_reward.make_execution_reward(tmp_path)(
        completions=[text], answer=[row["answer"]], db_id=[row["db_id"]],
    )
    assert expected == ([1.0] if ending == "invalidated-program" else [0.0])
    scores, actions = _execution_spies(monkeypatch)

    assert _dispatch(state.inputs, [row], [environment], [completion]) == expected

    assert len(scores) == 1
    assert scores[0].args[0] == text
    assert actions == []
    assert len(state.captures) == 1
    capture = state.captures[0]
    _assert_capture(
        capture, ids=state.declarations[0], row=row,
        detail="retained-before-ending", action=action,
    )
    assert capture.terminal_label == "aborted"
    assert capture.final_answer is capture.extracted_sql is capture.result is None
    diagnostic = sql_reporting.snapshot_to_dict(environment.reporting_snapshot)
    assert diagnostic == sql_reporting.snapshot_to_dict(capture.telemetry)


@pytest.mark.parametrize("constructor", ["native", "monitored"])
@pytest.mark.parametrize("enabled", [False, True])
def test_constructor_forwarding(
    native_wiring, callback_base, constructor, enabled,
):
    from train import sql_reporting, sql_training_run

    state = native_wiring
    declarations = _declared_ids(1)
    captures = []

    def capture_ids(task_id):
        return declarations[0]

    sink = captures.append
    reporting = sql_reporting.ReportingConfig()
    options = (
        dict(reporting=reporting, capture_ids=capture_ids, capture_sink=sink)
        if enabled else {}
    )
    if constructor == "native":
        trainer = state.build(**options)
    else:
        result = sql_training_run.build_monitored_sql_trainer(
            state.tasks, state.db_root, **state.kwargs, **options,
        )
        trainer = result.trainer
        assert len(state.callbacks) == len(callback_base.created) == 1
    assert len(state.prepare_calls) == 1
    tasks, db_root, forwarded = state.prepare_calls[0]
    assert tasks is state.tasks
    assert db_root is state.db_root
    assert trainer.kwargs["reward_funcs"] == [state.prepared[0].reward]
    assert trainer.kwargs["environment_factory"] is state.prepared[0].environment_factory
    if enabled:
        assert forwarded["capture_ids"] is capture_ids
        assert forwarded["capture_sink"] is sink
        assert forwarded["reporting"] is reporting
    else:
        assert "capture_ids" not in forwarded
        assert "capture_sink" not in forwarded
        assert "reporting" not in forwarded
    assert captures == []


@pytest.mark.parametrize("reporting_only", [False, True])
def test_disabled_reward_positive_control(sql_tasks, tmp_path, reporting_only):
    from train import ex_reward, sql_bridge, sql_reporting

    options = (
        {"reporting": sql_reporting.ReportingConfig()} if reporting_only else {}
    )
    inputs = sql_bridge.prepare_sql_training(sql_tasks, tmp_path, **options)
    rows = inputs.dataset_rows
    environments = [inputs.environment_factory() for _ in rows]
    for index, (environment, row) in enumerate(zip(environments, rows, strict=True)):
        environment.reset(**row)
        if reporting_only:
            _report(environment, f"disabled-control-{index}", (17, 29)[index])
        else:
            assert environment.run_program(PROGRAM) == str((17, 29)[index])
    expected = ex_reward.make_execution_reward(tmp_path)(
        completions=[SQL, SQL], answer=[row["answer"] for row in rows],
        db_id=[row["db_id"] for row in rows],
    )
    assert expected == [1.0, 1.0]
    assert _dispatch(inputs, rows, environments, [_completion()] * 2) == expected


def test_over_budget_final_refuses_before_extraction_or_scoring(
    sql_tasks, tmp_path, monkeypatch,
):
    from bench import score
    from train import ex_reward, sql_capture, sql_episodes, sql_reporting

    state = _prepare(sql_tasks[:1], tmp_path, count=1)
    row = state.inputs.dataset_rows[0]
    environment = state.inputs.environment_factory()
    assert environment.reset(**row) is None
    action = _report(environment, "retained-before-over-budget-final", 17)
    assert state.captures == []
    text = ";" * 12000
    assert len(text.encode("utf-8")) == 12000 < 8 * 1024 * 1024
    assert 12000 + 12000 * 12001 // 2 > 64 * 1024 * 1024
    scores, actions = _execution_spies(monkeypatch)
    original_extract = score.extract_sql
    extractions = []

    # Fault/sentry only: never invoke the quadratic extractor on this payload.
    def extract_sentry(value):
        extractions.append(value)
        return SQL

    for module in (score, ex_reward, sql_capture, sql_episodes):
        if getattr(module, "extract_sql", None) is original_extract:
            monkeypatch.setattr(module, "extract_sql", extract_sentry)

    with pytest.raises(ValueError, match="SQL extraction work exceeds 64 MiB"):
        _dispatch(state.inputs, [row], [environment], [_completion(text)])

    assert len(state.captures) == 1
    capture = state.captures[0]
    _assert_capture(
        capture, ids=state.declarations[0], row=row,
        detail="retained-before-over-budget-final", action=action,
    )
    assert capture.terminal_label == "aborted"
    assert capture.final_answer is capture.extracted_sql is capture.result is None
    assert sql_reporting.snapshot_to_dict(environment.reporting_snapshot) == (
        sql_reporting.snapshot_to_dict(capture.telemetry)
    )
    assert extractions == []
    assert scores == actions == []


def test_database_drift_refuses_before_scoring(sql_tasks, tmp_path, monkeypatch):
    import sqlite3

    from train import sql_reporting

    state = _prepare(sql_tasks[:1], tmp_path, count=1)
    row = state.inputs.dataset_rows[0]
    environment = state.inputs.environment_factory()
    assert environment.reset(**row) is None
    action = _report(environment, "retained-before-database-drift", 17)
    assert state.captures == []
    connection = sqlite3.connect(sql_tasks[0].db_path)
    try:
        assert connection.execute("SELECT amount FROM readings").fetchall() == [(17,)]
        connection.execute("UPDATE readings SET amount = 18")
        connection.commit()
        assert connection.execute("SELECT amount FROM readings").fetchall() == [(18,)]
    finally:
        connection.close()
    scores, actions = _execution_spies(monkeypatch)

    with pytest.raises(ValueError, match="(?i)database"):
        _dispatch(state.inputs, [row], [environment], [_completion()])

    assert len(state.captures) == 1
    capture = state.captures[0]
    _assert_capture(
        capture, ids=state.declarations[0], row=row,
        detail="retained-before-database-drift", action=action,
    )
    assert capture.terminal_label == "aborted"
    assert capture.final_answer is capture.extracted_sql is capture.result is None
    assert sql_reporting.snapshot_to_dict(environment.reporting_snapshot) == (
        sql_reporting.snapshot_to_dict(capture.telemetry)
    )
    assert scores == actions == []
