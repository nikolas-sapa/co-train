"""Offline reset-bridge reporting contracts, not actual TRL training acceptance.

SQLite, SQL rewards, prompts, catalog callbacks and restricted execution are
real. Constructor/executor faults below are explicitly private seam doubles.
Only the disabled import check uses a fresh Python subprocess, never a model,
provider, SDK, container or training framework.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import gc
import importlib
import inspect
import pathlib
import sqlite3
import subprocess
import sys
import weakref

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

PROGRAM = 'print(execute_sql(query="SELECT amount FROM readings")[0]["amount"])'


@pytest.fixture(autouse=True)
def no_frameworks(monkeypatch):
    attempted = []
    original_import = builtins.__import__
    original_import_module = importlib.import_module
    forbidden = {
        "torch", "trl", "unsloth", "transformers", "vllm", "verifiers",
        "httpx", "pydantic", "datasets", "huggingface_hub",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"framework import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)

    def guarded_import_module(name, *args, **kwargs):
        check(name)
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    yield
    assert attempted == []


@pytest.fixture
def bridge():
    from train import sql_bridge

    return sql_bridge


@pytest.fixture
def reporting():
    from train import sql_reporting

    return sql_reporting


@pytest.fixture
def sql_tasks(tmp_path):
    from bench.task import SqlTask

    tasks = []
    for name, amount in (("first", 17), ("second", 29)):
        directory = tmp_path / name
        directory.mkdir()
        db = directory / f"{name}.sqlite"
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            conn.execute("INSERT INTO readings VALUES (?)", (amount,))
            conn.commit()
        finally:
            conn.close()
        tasks.append(SqlTask(
            name=name, question="What amount is recorded?",
            evidence="Use the readings table.",
            gold_sql=f"SELECT amount FROM readings /* GOLD_ONLY_{name} */",
            db_id=name, db_path=str(db), tier="simple", tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture",
        ))
    return tasks


@pytest.fixture
def inputs(bridge, reporting, sql_tasks, tmp_path):
    return bridge.prepare_sql_training(
        sql_tasks, tmp_path, reporting=reporting.ReportingConfig(),
    )


def _report(detail):
    return f'print(report_defect(kind="other", detail={detail!r}))'


def _doc(environment):
    from train.sql_reporting import snapshot_to_dict

    return snapshot_to_dict(environment.reporting_snapshot)


def _assert_enabled_report(environment, detail):
    from ptc.sql_qa import report_ack

    observed = environment.run_program(_report(detail))
    doc = _doc(environment)
    assert doc["arms"]["ptc"]["reports"] == 1, (
        "enabled report callback did not retain exactly one PTC report"
    )
    assert observed == report_ack()
    assert doc["total_events"] == 1
    assert doc["arms"]["bash"]["events"] == []
    (event,) = doc["arms"]["ptc"]["events"]
    assert event == {
        "arm": "ptc", "seq": 1, "type": "report",
        "provenance": "catalog_callback", "kind": "other", "detail": detail,
    }


def _track_real(monkeypatch, reporting):
    """Spies retain channels for identity checks; production retains no history."""
    from train import grpo_ptc, guards

    original_channel = reporting.make_channel
    original_environment = grpo_ptc.sql_environment
    channels, environments, dispatched = [], [], []

    def make_channel(config):
        channel = original_channel(config)
        channels.append(channel)
        return channel

    def sql_environment(task, root=guards.REPO_ROOT, **kwargs):
        prompt, environment = original_environment(task, root=root, **kwargs)
        executor = environment._executor

        def execute(code):
            dispatched.append((task.name, code))
            return executor(code)

        environment._executor = execute
        environments.append((environment, kwargs))
        return prompt, environment

    monkeypatch.setattr(reporting, "make_channel", make_channel)
    monkeypatch.setattr(grpo_ptc, "sql_environment", sql_environment)
    return channels, environments, dispatched


def test_two_tasks_four_resets_eight_channels_no_crossed_reports(
    bridge, reporting, sql_tasks, tmp_path, monkeypatch,
):
    channels, environments, _ = _track_real(monkeypatch, reporting)
    config = reporting.ReportingConfig(shortcut_ids=("fixture_shortcut",))
    prepared = bridge.prepare_sql_training(sql_tasks, tmp_path, reporting=config)
    assert len(channels) == len(environments) == 2
    preparation_channels = tuple(channels)
    assert all(not channel.events for channel in preparation_channels)
    adapters = [prepared.environment_factory() for _ in sql_tasks]
    assert len(channels) == 2  # Unbound factories do not allocate channels.
    reset_channels = []
    for index, (adapter, row) in enumerate(zip(adapters, prepared.dataset_rows, strict=True)):
        assert adapter.reporting_snapshot is None
        for rollout in range(4):
            assert adapter.reset(**row) is None
            assert adapter.turns_used == 0
            channel = channels[-1]
            reset_channels.append(channel)
            assert environments[-1][1] == {"qa": channel}
            assert channel.shortcut_ids == config.shortcut_ids
            assert _doc(adapter)["total_events"] == 0
            detail = f"task-{index}-rollout-{rollout}"
            _assert_enabled_report(adapter, detail)
            assert [event["detail"] for event in channel.events] == [detail]
    assert len(channels) == len(environments) == 10
    assert len(reset_channels) == len({id(channel) for channel in reset_channels}) == 8
    assert not set(map(id, preparation_channels)) & set(map(id, reset_channels))
    assert all(not channel.events for channel in preparation_channels)
    assert [channel.events[0]["detail"] for channel in reset_channels] == [
        f"task-{index}-rollout-{rollout}" for index in range(2) for rollout in range(4)
    ]


def test_enabled_prompt_rows_discovery_and_readonly_snapshot(
    bridge, reporting, inputs, sql_tasks,
):
    from ptc.sql_arms import build_sql_arms
    from ptc.sql_qa import REPORT_PROMPT

    assert inspect.signature(bridge.prepare_sql_training).parameters["reporting"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert inspect.signature(inputs.environment_factory).parameters == {}
    for task, row in zip(sql_tasks, inputs.dataset_rows, strict=True):
        assert set(row) == {"prompt", "task_id", "answer", "db_id"}
        expected = build_sql_arms(
            task, qa=reporting.make_channel(reporting.ReportingConfig()),
        ).prompt("ptc")
        assert row["prompt"] == [{"role": "user", "content": expected}]
        assert REPORT_PROMPT in expected
        assert task.gold_sql not in expected and "GOLD_ONLY" not in expected
    environment = inputs.environment_factory()
    assert isinstance(type(environment).reporting_snapshot, property)
    for row in (None, inputs.dataset_rows[0]):
        if row is not None:
            environment.reset(**row)
        tools = [
            name for name, _ in inspect.getmembers(environment, inspect.ismethod)
            if not name.startswith("_") and name not in ("reset", "get_reward")
        ]
        assert tools == ["run_program"]
        assert not callable(environment.reporting_snapshot)
        with pytest.raises(AttributeError):
            environment.reporting_snapshot = None
    _assert_enabled_report(environment, "real callback")


def test_sql_rewards_and_database_bytes_unchanged(
    bridge, reporting, sql_tasks, tmp_path,
):
    before = [pathlib.Path(task.db_path).read_bytes() for task in sql_tasks]
    disabled = bridge.prepare_sql_training(sql_tasks, tmp_path)
    enabled = bridge.prepare_sql_training(
        sql_tasks, tmp_path, reporting=reporting.ReportingConfig(),
    )
    for prepared in (disabled, enabled):
        for index, (task, row) in enumerate(zip(sql_tasks, prepared.dataset_rows, strict=True)):
            environment = prepared.environment_factory()
            environment.reset(**row)
            assert environment.run_program(PROGRAM) == ("17", "29")[index]
            if prepared is enabled:
                _assert_enabled_report(environment, f"unchanged-{index}")
            assert prepared.reward(
                ["SELECT amount FROM readings", "SELECT amount + 1 FROM readings"],
                answer=[task.gold_sql] * 2, db_id=[task.db_id] * 2,
            ) == [1.0, 0.0]
    assert [pathlib.Path(task.db_path).read_bytes() for task in sql_tasks] == before


def test_nine_report_attempts_accept_eight(inputs):
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    observed = environment.run_program("\n".join(_report(f"attempt-{i}") for i in range(9)))
    assert observed == "rejected: report limit reached for this arm"
    doc = _doc(environment)
    assert doc["arms"]["ptc"]["reports"] == 8
    events = doc["arms"]["ptc"]["events"]
    assert [event["detail"] for event in events if event["type"] == "report"] == [
        f"attempt-{i}" for i in range(8)
    ]
    assert len(events) == doc["total_events"] == 9
    assert events[-1]["type"] == "overflow"
    assert environment.turns_used == 1


def test_submission_cap_plus_one_dispatches_nothing(
    bridge, reporting, sql_tasks, tmp_path, monkeypatch,
):
    from train import guards

    _, _, dispatched = _track_real(monkeypatch, reporting)
    prepared = bridge.prepare_sql_training(
        sql_tasks, tmp_path, reporting=reporting.ReportingConfig(),
    )
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    _assert_enabled_report(environment, "early")
    assert prepared.max_tool_calling_iterations == guards.eval_max_turns() == 8
    for _ in range(7):
        assert environment.run_program(PROGRAM) == "17"
    before = environment.reporting_snapshot.data
    assert len(dispatched) == environment.turns_used == 8
    assert environment.run_program(_report("never dispatched")) == (
        guards.TurnBudget(max_turns=8).exhausted_message()
    )
    assert len(dispatched) == environment.turns_used == 8
    assert environment.reporting_snapshot.data == before


@pytest.mark.parametrize(
    "field,value",
    [("task_id", "unknown"), ("task_id", None), ("prompt", None),
     ("prompt", [{"role": "user", "content": "altered"}]),
     ("answer", "SELECT 999"), ("db_id", "second")],
)
def test_invalid_metadata_unbinds_before_channel_work(
    inputs, reporting, monkeypatch, field, value,
):
    environment = inputs.environment_factory()
    row = copy.deepcopy(inputs.dataset_rows[0])
    environment.reset(**row)
    _assert_enabled_report(environment, "before invalid reset")
    old = environment.reporting_snapshot

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid row allocated a reporting channel")

    with monkeypatch.context() as invalid:
        invalid.setattr(reporting, "make_channel", forbidden)
        row[field] = value
        with pytest.raises(ValueError):
            environment.reset(**row)
        assert environment.reporting_snapshot is None
        assert environment.turns_used == 0
        with pytest.raises(RuntimeError, match="reset"):
            environment.run_program(PROGRAM)
    assert old.data
    environment.reset(**inputs.dataset_rows[0])
    assert _doc(environment)["total_events"] == 0
    assert environment.run_program(PROGRAM) == "17"


@pytest.mark.parametrize("field", ["task_id", "prompt", "answer", "db_id"])
def test_missing_metadata_also_invalidates(inputs, field):
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    row = copy.deepcopy(inputs.dataset_rows[0])
    del row[field]
    with pytest.raises(ValueError):
        environment.reset(**row)
    assert environment.reporting_snapshot is None
    with pytest.raises(RuntimeError, match="reset"):
        environment.run_program(PROGRAM)


@pytest.mark.parametrize("fault", ["missing-db", "physical-mismatch", "schema-change"])
def test_real_database_reset_faults_unbind(
    inputs, reporting, sql_tasks, tmp_path, monkeypatch, fault,
):
    from train import ex_reward

    environment = inputs.environment_factory()
    row = inputs.dataset_rows[0]
    environment.reset(**row)
    _assert_enabled_report(environment, "before DB fault")
    original_channel = reporting.make_channel
    created = []

    def tracked(config):
        channel = original_channel(config)
        created.append(channel)
        return channel

    monkeypatch.setattr(reporting, "make_channel", tracked)
    db = pathlib.Path(sql_tasks[0].db_path)
    if fault == "missing-db":
        db.rename(tmp_path / "moved.sqlite")
        expected_error = FileNotFoundError
    elif fault == "physical-mismatch":
        other = tmp_path / "identical-copy.sqlite"
        other.write_bytes(db.read_bytes())
        monkeypatch.setattr(ex_reward, "db_path_for", lambda *args: str(other))
        expected_error = ValueError
    else:
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE changed_schema (extra INTEGER)")
            conn.commit()
        finally:
            conn.close()
        expected_error = ValueError
    with pytest.raises(expected_error):
        environment.reset(**row)
    assert len(created) == (1 if fault == "schema-change" else 0)
    assert environment.reporting_snapshot is None
    assert environment.turns_used == 0
    with pytest.raises(RuntimeError, match="reset"):
        environment.run_program(PROGRAM)


@pytest.mark.parametrize("fault", ["channel", "constructor", "prompt"])
def test_private_constructor_faults_never_commit_partial_state(
    inputs, reporting, monkeypatch, fault,
):
    """Private fault injection only, not an actual TRL lifecycle check."""
    from train import grpo_ptc

    environment = inputs.environment_factory()
    row = inputs.dataset_rows[0]
    environment.reset(**row)
    _assert_enabled_report(environment, "before constructor fault")
    failure = RuntimeError("constructor fault sentinel")
    original = grpo_ptc.sql_environment

    def failing(*args, **kwargs):
        raise failure

    def changed_prompt(*args, **kwargs):
        prompt, executor = original(*args, **kwargs)
        return prompt + "\nchanged", executor

    with monkeypatch.context() as broken:
        if fault == "channel":
            broken.setattr(reporting, "make_channel", failing)
        else:
            broken.setattr(
                grpo_ptc, "sql_environment",
                changed_prompt if fault == "prompt" else failing,
            )
        with pytest.raises(ValueError if fault == "prompt" else RuntimeError) as caught:
            environment.reset(**row)
        if fault != "prompt":
            assert caught.value is failure
        assert environment.reporting_snapshot is None
        with pytest.raises(RuntimeError, match="reset"):
            environment.run_program(PROGRAM)
    environment.reset(**row)
    assert _doc(environment)["total_events"] == 0


@pytest.mark.parametrize(
    "case",
    ["false", "class", "subclass", "lookalike", "version-bool", "version",
     "mode-type", "mode", "ids-list", "ids-duplicate", "ids-unsorted", "ids-invalid"],
)
def test_invalid_exact_config_precedes_all_database_schema_channel_work(
    bridge, reporting, sql_tasks, tmp_path, monkeypatch, case,
):
    from ptc import sql_arms
    from train import ex_reward, grpo_ptc, guards

    config = reporting.ReportingConfig()
    if case == "false":
        config = False
    elif case == "class":
        config = reporting.ReportingConfig
    elif case == "subclass":
        class Subclass(reporting.ReportingConfig):
            pass

        config = Subclass()
    elif case == "lookalike":
        config = {"version": 1, "mode": "defect_reports", "shortcut_ids": ()}
    else:
        field, value = {
            "version-bool": ("version", True), "version": ("version", 2),
            "mode-type": ("mode", 1), "mode": ("mode", "other"),
            "ids-list": ("shortcut_ids", []),
            "ids-duplicate": ("shortcut_ids", ("a", "a")),
            "ids-unsorted": ("shortcut_ids", ("z", "a")),
            "ids-invalid": ("shortcut_ids", ("not an identifier",)),
        }[case]
        object.__setattr__(config, field, value)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("malformed config reached DB/schema/channel work")

    for module, name in (
        (reporting, "make_channel"), (bridge, "_require_same_database"),
        (ex_reward, "db_path_for"), (grpo_ptc, "sql_environment"),
        (sql_arms, "build_sql_arms"), (sql_arms, "schema_text"),
        (sqlite3, "connect"), (guards, "eval_max_turns"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    with pytest.raises((TypeError, ValueError)):
        bridge.prepare_sql_training(sql_tasks, tmp_path, reporting=config)
    assert calls == []


def test_none_and_omitted_keep_original_calls_with_zero_channel_factories(
    bridge, reporting, sql_tasks, tmp_path, monkeypatch,
):
    from train import grpo_ptc, guards

    original = grpo_ptc.sql_environment
    calls = []

    def old_signature(task, root=guards.REPO_ROOT):
        calls.append(task.name)
        return original(task, root=root)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled path constructed a reporting channel")

    monkeypatch.setattr(grpo_ptc, "sql_environment", old_signature)
    monkeypatch.setattr(reporting, "make_channel", forbidden)
    omitted = bridge.prepare_sql_training(sql_tasks, tmp_path)
    explicit = bridge.prepare_sql_training(sql_tasks, tmp_path, reporting=None)
    assert omitted.dataset_rows == explicit.dataset_rows
    for prepared in (omitted, explicit):
        for index, row in enumerate(prepared.dataset_rows):
            environment = prepared.environment_factory()
            assert environment.reporting_snapshot is None
            environment.reset(**row)
            assert environment.run_program(PROGRAM) == ("17", "29")[index]
            assert environment.reporting_snapshot is None
    assert calls == ["first", "second"] * 4


def test_fresh_disabled_interpreter_has_zero_reporting_qa_imports(sql_tasks, tmp_path):
    repo = pathlib.Path(__file__).resolve().parents[1]
    task_dicts = [dataclasses.asdict(task) for task in sql_tasks]
    child = (
        "import builtins, sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "original_import = builtins.__import__\n"
        "attempted = []\n"
        "def guarded(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    names = {name} | {name + '.' + part for part in (fromlist or ())}\n"
        "    blocked = {'ptc.sql_qa', 'train.sql_reporting'}\n"
        "    frameworks = {'torch', 'trl', 'unsloth', 'transformers', 'vllm',\n"
        "                  'verifiers', 'httpx', 'pydantic', 'datasets', 'huggingface_hub'}\n"
        "    if names & blocked or name.split('.')[0] in frameworks or name == 'ptc.harness':\n"
        "        attempted.append(name)\n"
        "        raise AssertionError('disabled optional import: ' + name)\n"
        "    return original_import(name, globals, locals, fromlist, level)\n"
        "builtins.__import__ = guarded\n"
        "from bench.task import SqlTask\n"
        "from train import sql_bridge, grpo_ptc\n"
        f"tasks = [SqlTask(**row) for row in {task_dicts!r}]\n"
        "original_environment = grpo_ptc.sql_environment\n"
        "calls = []\n"
        "def old_signature(task, root=sql_bridge.guards.REPO_ROOT):\n"
        "    calls.append(task.name)\n"
        "    return original_environment(task, root=root)\n"
        "grpo_ptc.sql_environment = old_signature\n"
        "for kwargs in ({}, {'reporting': None}):\n"
        f"    prepared = sql_bridge.prepare_sql_training(tasks, {str(tmp_path)!r}, **kwargs)\n"
        "    for index, row in enumerate(prepared.dataset_rows):\n"
        "        env = prepared.environment_factory()\n"
        "        assert env.reporting_snapshot is None\n"
        "        env.reset(**row)\n"
        f"        assert env.run_program({PROGRAM!r}) == ('17', '29')[index]\n"
        "        assert env.reporting_snapshot is None\n"
        "        assert 'report_defect' not in row['prompt'][0]['content']\n"
        "assert calls == ['first', 'second'] * 4\n"
        "assert attempted == []\n"
        "assert not {'ptc.sql_qa', 'train.sql_reporting'} & set(sys.modules)\n"
        "print('DISABLED_BRIDGE_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "DISABLED_BRIDGE_OK"


def test_real_report_then_program_error_keeps_diagnostics_and_exact_return(
    inputs, reporting, sql_tasks,
):
    from train import grpo_ptc

    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    channel = reporting.make_channel(reporting.ReportingConfig())
    _, original = grpo_ptc.sql_environment(sql_tasks[0], qa=channel)
    program = _report("before arithmetic failure") + "\nprint(1 / 0)"
    expected = original.step(program)
    assert expected.startswith("error: ZeroDivisionError:")
    assert environment.run_program(program) == expected
    assert environment.turns_used == original.turns_used == 1
    snapshot = environment.reporting_snapshot
    assert snapshot.data == reporting.snapshot_channel(
        channel, reporting.ReportingConfig(), arm="ptc",
    ).data
    assert _doc(environment)["arms"]["ptc"]["reports"] == 1
    assert environment.run_program(PROGRAM) == "17"
    assert environment.reporting_snapshot.data == snapshot.data


def test_private_executor_exception_and_return_identity_without_snapshot_wrapping(
    inputs, monkeypatch,
):
    """Private constructor fault double, not actual TRL or runtime acceptance."""
    from train import grpo_ptc

    original = grpo_ptc.sql_environment
    failure = RuntimeError("exact executor exception")
    result = object()
    codes = []

    def constructor(*args, **kwargs):
        prompt, environment = original(*args, **kwargs)
        channel = kwargs["qa"]

        def execute(code):
            codes.append(code)
            channel.submit("ptc", kind="other", detail=code)
            if code == "fail":
                raise failure
            return result

        environment._executor = execute
        return prompt, environment

    monkeypatch.setattr(grpo_ptc, "sql_environment", constructor)
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    with pytest.raises(RuntimeError) as caught:
        environment.run_program("fail")
    assert caught.value is failure
    assert environment.turns_used == 1
    assert _doc(environment)["arms"]["ptc"]["reports"] == 1
    assert environment.run_program("return") is result
    assert environment.turns_used == 2
    assert codes == ["fail", "return"]
    assert _doc(environment)["arms"]["ptc"]["reports"] == 2


def test_snapshot_access_failure_is_loud_and_does_not_wrap_programs(
    inputs, reporting, monkeypatch,
):
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    _assert_enabled_report(environment, "before snapshot fault")
    failure = ValueError("snapshot fault sentinel")

    def failing(*args, **kwargs):
        raise failure

    monkeypatch.setattr(reporting, "snapshot_channel", failing)
    assert environment.run_program(PROGRAM) == "17"
    with pytest.raises(ValueError) as caught:
        environment.reporting_snapshot
    assert caught.value is failure


def test_prior_snapshots_immutable_across_reports_and_resets(inputs, reporting):
    environment = inputs.environment_factory()
    environment.reset(**inputs.dataset_rows[0])
    empty = environment.reporting_snapshot
    _assert_enabled_report(environment, "first")
    first = environment.reporting_snapshot
    first_bytes = first.data
    from ptc.sql_qa import report_ack

    assert environment.run_program(_report("second")) == report_ack()
    assert _doc(environment)["arms"]["ptc"]["reports"] == 2
    assert first.data == first_bytes
    assert reporting.snapshot_to_dict(first)["arms"]["ptc"]["reports"] == 1
    assert reporting.snapshot_to_dict(empty)["total_events"] == 0
    mutable_copy = reporting.snapshot_to_dict(first)
    mutable_copy["arms"]["ptc"]["events"].clear()
    assert first.data == first_bytes
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.data = b"changed"
    environment.reset(**inputs.dataset_rows[1])
    assert _doc(environment)["total_events"] == 0
    assert first.data == first_bytes
    assert environment.run_program(PROGRAM) == "29"


def test_preparation_channels_are_ephemeral_and_reset_releases_old_channel(
    bridge, reporting, sql_tasks, tmp_path, monkeypatch,
):
    original = reporting.make_channel
    references = []

    def tracked(config):
        channel = original(config)
        references.append(weakref.ref(channel))
        return channel

    monkeypatch.setattr(reporting, "make_channel", tracked)
    prepared = bridge.prepare_sql_training(
        sql_tasks, tmp_path, reporting=reporting.ReportingConfig(),
    )
    gc.collect()
    assert len(references) == 2
    assert all(reference() is None for reference in references)
    environment = prepared.environment_factory()
    environment.reset(**prepared.dataset_rows[0])
    assert references[-1]() is not None
    _assert_enabled_report(environment, "released after reset")
    old_snapshot = environment.reporting_snapshot
    environment.reset(**prepared.dataset_rows[1])
    gc.collect()
    assert references[-2]() is None
    assert references[-1]() is not None
    assert reporting.snapshot_to_dict(old_snapshot)["arms"]["ptc"]["reports"] == 1


def test_forwarding_suppression_canary_fails_at_report_assertion_then_restores(
    inputs, monkeypatch,
):
    from ptc import sql_arms

    original = sql_arms.sql_catalog
    environment = inputs.environment_factory()

    def suppress_reporting(db_path, max_rows, observe=None, *, qa=None):
        return original(db_path, max_rows, observe)

    with monkeypatch.context() as suppressed:
        suppressed.setattr(sql_arms, "sql_catalog", suppress_reporting)
        # Prompt/reset remain real and succeed. Only callback forwarding is broken.
        environment.reset(**inputs.dataset_rows[0])
        with pytest.raises(AssertionError) as caught:
            _assert_enabled_report(environment, "suppressed")
        assert str(caught.value).splitlines()[0] == (
            "enabled report callback did not retain exactly one PTC report"
        )
    environment.reset(**inputs.dataset_rows[0])
    _assert_enabled_report(environment, "restored")
