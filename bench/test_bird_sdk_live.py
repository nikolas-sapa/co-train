"""Frozen fixture boundaries, not qualification of a production SDK composer."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
from pathlib import Path

import pytest


def _api():
    try:
        return importlib.import_module("bench.bird_sdk_driver")
    except ModuleNotFoundError as exc:
        if exc.name != "bench.bird_sdk_driver":
            raise
        pytest.fail("BIRD_SDK_BRIDGE_ABSENT")


@pytest.fixture
def case(tmp_path, monkeypatch):
    from bench.test_bird_sdk_driver_integration import make_case

    return make_case(tmp_path, monkeypatch, _api())


def _admit(case, config, effective):
    api = _api()
    expected = dataclasses.replace(case.bindings["bash"].expected,
        config=config.model_copy(deep=True), effective_agent=effective)
    return api.admit_sdk_config(config, expected=expected,
        instrument=case.instrument, output_root=case.output_root)


def test_equal_unregistered_env_is_not_registered_custody(case):
    from verifiers.v1.configs.agent import AgentConfig

    api = _api()
    binding = case.bindings["bash"]
    original = type(binding.config.env)
    impostor = type(original.__name__, original.__bases__, {
        "__module__": original.__module__,
        "__annotations__": {"agent": AgentConfig},
        "agent": AgentConfig(),
    })
    config = binding.config.model_copy(deep=True)
    config.env = impostor(**{
        name: getattr(config.env, name) for name in original.model_fields})
    assert impostor is not original
    assert api._plain_fixture_model(impostor)
    assert config.env.model_dump() == binding.config.env.model_dump()
    with pytest.raises(api.BirdSdkBridgeError, match="original fixture config classes"):
        _admit(case, config, binding.expected.effective_agent.model_copy(deep=True))
    case.assert_no_dispatch()


def test_equal_unregistered_harness_is_not_registered_custody(case):
    api = _api()
    binding = case.bindings["bash"]
    original = type(binding.config.env.agent.harness)
    impostor = type(original.__name__, original.__bases__, {
        "__module__": original.__module__,
        "__annotations__": dict(original.__annotations__),
        **{name: field.default for name, field in original.model_fields.items()
           if name in original.__annotations__},
    })
    config = binding.config.model_copy(deep=True)
    harness = config.env.agent.harness
    config.env.agent.harness = impostor(**{
        name: getattr(harness, name) for name in original.model_fields})
    effective = binding.expected.effective_agent.model_copy(deep=True)
    effective.harness = config.env.agent.harness.model_copy(deep=True)
    assert impostor is not original
    assert api._plain_fixture_model(impostor)
    assert effective.harness.model_dump() == binding.expected.effective_agent.harness.model_dump()
    with pytest.raises(api.BirdSdkBridgeError, match="original fixture harness config"):
        _admit(case, config, effective)
    case.assert_no_dispatch()


def test_nonfixture_plugin_name_cannot_reuse_fixture_admission(case):
    api = _api()
    binding = case.bindings["bash"]
    config = binding.config.model_copy(deep=True)
    config.env.id = config.env.taskset.id = "unadmitted_bird_sql"
    config.env.agent.harness.id = "unadmitted_bird_sql"
    effective = binding.expected.effective_agent.model_copy(deep=True)
    effective.harness.id = "unadmitted_bird_sql"
    with pytest.raises(api.BirdSdkBridgeError, match="named fixture plugins required"):
        _admit(case, config, effective)
    case.assert_no_dispatch()


def test_projection_keeps_gold_and_host_path_private(case):
    api = _api()
    task = dataclasses.replace(case.draw.eligible[0],
        question="PUBLIC_QUESTION_V25", evidence="",
        gold_sql="PRIVATE_GOLD_V25", db_path=Path("/PRIVATE_HOST_V25.sqlite"))
    projection = api.project_sql_tasks((task,),
        schemas=("CREATE TABLE public_v25(value INTEGER)",), action_max_rows=17)
    assert len(projection.bash + projection.ptc) == 2
    for data in projection.bash + projection.ptc:
        text = data.model_dump_json()
        assert "PUBLIC_QUESTION_V25" in text
        assert "CREATE TABLE public_v25(value INTEGER)" in text
        assert "PRIVATE_GOLD_V25" not in text
        assert "PRIVATE_HOST_V25" not in text
        assert "gold_sql" not in text and "db_path" not in text
    case.assert_no_dispatch()


def test_existing_projection_includes_evidence_not_question_schema_only(case):
    api = _api()
    task = dataclasses.replace(case.draw.eligible[0], evidence="EVIDENCE_BOUNDARY_V25")
    projection = api.project_sql_tasks((task,), schemas=("CREATE TABLE public_v25(x)",),
        action_max_rows=17)
    assert sum(data.prompt.count("EVIDENCE_BOUNDARY_V25")
               for data in projection.bash + projection.ptc) == 2
    case.assert_no_dispatch()


def test_selected_config_drift_refuses_before_dispatch(case):
    api = _api()
    case.bindings["bash"].config.push = True
    with pytest.raises(api.BirdSdkBridgeError, match="settings seal drift"):
        case.run_arm("bash")
    case.assert_no_dispatch()


def test_incomplete_episode_stream_is_not_a_partial_success(case):
    api = _api()
    rows = case.run_arm("bash")
    assert len(rows) == len(case.state.episodes) == 7
    calls = case.state.evaluator_calls
    with pytest.raises(api.BirdSdkBridgeError, match="episode coverage"):
        case.decode(episodes=case.state.episodes[:-1])
    assert case.state.evaluator_calls == calls == 1
    assert case.decode() == rows


def test_equal_copied_trace_cannot_replace_original_score_identity(case):
    api = _api()
    rows = case.run_arm("bash")
    receipts = tuple(case.state.receipts)
    assert len(receipts) == 7
    first = receipts[0]
    copied = first.trace.model_copy(deep=True)
    assert copied is not first.trace
    assert copied.model_dump() == first.trace.model_dump()
    detached = dataclasses.replace(first, trace=copied)
    assert detached.result is first.result
    with pytest.raises(api.BirdSdkBridgeError, match="missing original EX receipt"):
        case.decode(scores=(detached,) + receipts[1:])
    assert case.state.evaluator_calls == 1
    assert case.decode() == rows


def test_projection_refusal_diagnostics_do_not_echo_private_material(case):
    api = _api()
    canary = "PRIVATE_DIAGNOSTIC_V25"
    task = dataclasses.replace(case.draw.eligible[0],
        gold_sql=canary, db_path=Path("/" + canary + ".sqlite"))
    with pytest.raises(api.BirdSdkBridgeError) as error:
        api.project_sql_tasks((task, task),
            schemas=("CREATE TABLE public_v25(x)",) * 2, action_max_rows=17)
    assert str(error.value) == "projection membership"
    assert canary not in str(error.value)
    case.assert_no_dispatch()


def test_arm_cancellation_closes_iterator_before_return(case):
    from bench import paired_bird

    async def exercise():
        cancellation = asyncio.CancelledError("synthetic-owned-cancellation")
        closed = []

        class Iterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise cancellation

            async def aclose(self):
                closed.append(asyncio.current_task())

        rows = []
        closing = asyncio.Event()
        actual = await paired_bird._run_arm(case.plan, case.request("bash"), lambda _: Iterator(),
            rows, closing)
        assert actual is cancellation
        assert rows == []
        assert closing.is_set()
        assert closed == [asyncio.current_task()]
        assert paired_bird._require_plan(case.plan) == ("bash:cancelled",)

    asyncio.run(exercise())
    case.assert_no_dispatch()
