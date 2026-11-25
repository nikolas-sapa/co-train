"""Offline bridge contract. Real SDK imports precede call-phase API checks."""
from __future__ import annotations

import dataclasses
import importlib
import json
import math
from pathlib import Path

import pytest
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.episode import Episode
from verifiers.v1.task import TaskData, task_key
from verifiers.v1.trace import Trace
from verifiers.v1.types import SamplingConfig

from bench.paired_bird import ArmRequest
from bench.score import ExResult
from ptc.sql_arms import BASH_CHANNEL, PTC_CHANNEL, SQL_TOOL


def _field_plugin(tmp_path, monkeypatch, target, declaration):
    """Real named plugin, original SDK loaders; no framework/factory patches."""
    import inspect
    import sys
    from bench import test_bird_sdk_driver_integration as fixture
    from verifiers.v1.utils import loaders
    original = fixture.FixtureHarnessConfig if target == "harness" else fixture.FixtureEnvConfig
    field = "arm" if target == "harness" else "agent"
    default = '""' if target == "harness" else "AgentConfig()"
    source = inspect.getsource(original)
    needle = f'{field}: {"str" if target == "harness" else "AgentConfig"} = {default}'
    assert source.count(needle) == 1
    source = source.replace(needle, needle.rsplit(" = ", 1)[0] + " = " + declaration)
    if target == "harness":
        runtime = """
class FieldHarness(Harness[FixtureHarnessConfig]):
    NEEDS_CONTAINER = False
    APPENDS_SYSTEM_PROMPT = True
    SUPPORTS_MCP = False
    EXECUTES_CODE = True
    launch = FixtureSqlHarness.launch
__all__ = ['FieldHarness', 'FixtureSqlEnv', 'FixtureSqlTaskset']
"""
    else:
        runtime = """
class FieldEnv(Env[FixtureEnvConfig]):
    run = FixtureSqlEnv.run
    stop = FixtureSqlEnv.stop
__all__ = ['FixtureSqlHarness', 'FieldEnv', 'FixtureSqlTaskset']
"""
    plugin = tmp_path / "plugins" / f"{fixture.PLUGIN}.py"
    plugin.write_text("""
from __future__ import annotations
from pydantic import Field
from bench.test_bird_sdk_driver_integration import (
    AgentConfig, EnvConfig, PTCHarnessConfig, PLUGIN, Env, Harness,
    FixtureSqlEnv, FixtureSqlHarness, FixtureSqlTaskset)
def callback_state():
    gate = {'hide': False}
    def exclude(value):
        return gate['hide']
    return gate, exclude
gate, exclude = callback_state()
""" + source + runtime)
    monkeypatch.delitem(sys.modules, fixture.PLUGIN, raising=False)
    importlib.invalidate_caches()
    cls = (loaders.harness_config_type(fixture.PLUGIN) if target == "harness"
           else loaders.env_config_type(fixture.PLUGIN, fixture.PLUGIN))
    module = importlib.import_module(fixture.PLUGIN)
    assert cls is getattr(module, original.__name__) and cls.__bases__ == original.__bases__
    return cls, module, field


@pytest.mark.parametrize("target", ("harness", "env"))
def test_followup02_loader_field_callback_refused(tmp_path, monkeypatch, target):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    default = '""' if target == "harness" else "AgentConfig()"
    cls, module, field = _field_plugin(tmp_path, monkeypatch, target,
        f"Field(default={default}, exclude_if=exclude)")
    assert cls.model_fields[field].exclude_if.__closure__
    assert not cls.model_fields[field].metadata
    assert not cls.__pydantic_decorators__.model_serializers
    assert not cls.__pydantic_decorators__.field_serializers
    binding = c.bindings["bash"]
    config = binding.config.model_copy(deep=True)
    effective = binding.expected.effective_agent.model_copy(deep=True)
    original = config.env.agent.harness if target == "harness" else config.env
    replacement = cls(**{k: getattr(original, k) for k in type(original).model_fields})
    if target == "harness":
        config.env.agent.harness = replacement
        effective.harness = replacement.model_copy(deep=True)
    else:
        config.env = replacement
    expected = dataclasses.replace(binding.expected, config=config.model_copy(deep=True),
                                   effective_agent=effective)
    try:
        seal = a.admit_sdk_config(config, expected=expected,
                                 instrument=c.instrument, output_root=c.output_root)
    except a.BirdSdkBridgeError:
        c.assert_no_dispatch()
        return  # Required outcome: INITIAL refusal, not a new serializer authority.
    snapshot = a._snapshot(config)
    before = config.model_dump()
    before_json = config.model_dump_json()
    value = getattr(replacement, field)
    module.gate["hide"] = True
    assert config.model_dump() != before and config.model_dump_json() != before_json
    assert getattr(replacement, field) is value
    assert a._snapshot(config) == snapshot
    seal._check(fresh=True)  # Actual followup01 seal misses the actual wire delta.
    c.assert_no_dispatch()
    pytest.fail("FIELD_CALLBACK_ADMITTED_SERIALIZATION_DRIFT_UNSEALED")


@pytest.mark.parametrize("attribute, expression", (
    ("exclude", "True"),
    ("alias", "'renamed'"),
    ("serialization_alias", "'wire_name'"),
    ("validation_alias", "'input_name'"),
    ("alias_priority", "7"),
    ("field_title_generator", "lambda name, info: name"),
    ("discriminator", "'kind'"),
))
def test_followup02_field_serialization_contract(tmp_path, monkeypatch, attribute, expression):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    # Discriminators don't apply to this scalar; Pydantic normalizes standalone
    # alias_priority away. Set these on the resolved fixture FieldInfo for honest
    # structural-refusal unit controls, not real serializer-drift claims/SDK patches.
    structural = attribute in ("discriminator", "alias_priority")
    declaration = ('Field(default="")' if structural
                   else f'Field(default="", {attribute}={expression})')
    cls, _, field = _field_plugin(tmp_path, monkeypatch, "harness", declaration)
    if structural:
        setattr(cls.model_fields[field], attribute, "kind" if attribute == "discriminator" else 7)
    assert getattr(cls.model_fields[field], attribute) is not None
    with pytest.raises(a.BirdSdkBridgeError):
        a._snapshot(cls())
    c.assert_no_dispatch()


def test_followup01_stateful_serializer_refused(tmp_path, monkeypatch):
    """Actual private serializer delta, not a fictional serialized dictionary."""
    from pydantic import PrivateAttr, model_serializer
    a = _api()
    c = _case(tmp_path, monkeypatch)
    binding = c.bindings["bash"]

    class StatefulSampling(SamplingConfig):
        _wire_temperature: float = PrivateAttr(default=0.0)

        @model_serializer(mode="wrap")
        def serialize(self, handler):
            return {**handler(self), "temperature": self._wire_temperature}

    config = binding.config.model_copy(deep=True)
    config.sampling = StatefulSampling(temperature=0.2, top_p=0.8, max_tokens=128)
    sampling = StatefulSampling(temperature=0.0, top_p=0.8, max_tokens=128)
    expected = dataclasses.replace(binding.expected, config=config.model_copy(deep=True),
        effective_agent=binding.expected.effective_agent.model_copy(update={"sampling": sampling}))
    try:
        seal = a.admit_sdk_config(config, expected=expected,
                                 instrument=c.instrument, output_root=c.output_root)
    except a.BirdSdkBridgeError:
        c.assert_no_dispatch()
        return  # Parent-selected refusal of unsupported class is preferred.
    before = sampling.model_dump()
    sampling._wire_temperature = 0.95
    assert sampling.model_dump() != before, "STATEFUL_SERIALIZER_CONTROL_NOT_REAL"
    with pytest.raises(a.BirdSdkBridgeError):
        seal._check(fresh=True)
    c.assert_no_dispatch()


@pytest.mark.parametrize("state", ("nested_serializer", "nested_serializer_key",
                                  "private_state", "undeclared_state"))
def test_followup01_nested_model_state_refused(state):
    from pydantic import BaseModel, PrivateAttr, model_serializer
    class StatefulModel(BaseModel):
        model_config = {"frozen": True}
        _wire: int = PrivateAttr(default=1)
        @model_serializer
        def serialize(self):
            return {"wire": self._wire}
    value = SamplingConfig(temperature=0.0)
    if state == "nested_serializer":
        value = SamplingConfig(extra_body={"nested": StatefulModel()})
    elif state == "nested_serializer_key":
        value = SamplingConfig(extra_body={StatefulModel(): "nested key"})
    elif state == "private_state":
        object.__setattr__(value, "__pydantic_private__", {"hidden": 1})
    else:
        value.__dict__["hidden"] = 1
    with pytest.raises(_api().BirdSdkBridgeError):
        _api()._snapshot(value)


@pytest.mark.parametrize("rollouts", (True, 1.0), ids=("bool", "float"))
def test_followup01_exact_rollout_driver(tmp_path, monkeypatch, rollouts):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    with pytest.raises(a.BirdSdkBridgeError):
        c.consume(dataclasses.replace(c.request("bash"), num_rollouts=rollouts))
    c.assert_no_dispatch()


@pytest.mark.parametrize("rollouts", (True, 1.0), ids=("bool", "float"))
def test_followup01_exact_rollout_decoder(tmp_path, monkeypatch, rollouts):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    c.run_arm("bash")
    b = c.state
    calls = b.evaluator_calls, b.responses
    path = c.driver.seals["bash"].run_dir / "traces.jsonl"
    before = path.read_bytes()
    request = dataclasses.replace(c.request("bash"), num_rollouts=rollouts)
    with pytest.raises(a.BirdSdkBridgeError):
        a.decode_sdk_episodes(b.episodes, request=request, projection=c.driver.projection,
            scores=tuple(b.receipts), settings=c.driver.seals["bash"],
            task_type="FixtureSqlTask", run_dir=c.driver.seals["bash"].run_dir)
    assert calls == (b.evaluator_calls, b.responses) and path.read_bytes() == before


def _api():
    try:
        return importlib.import_module("bench.bird_sdk_driver")
    except ModuleNotFoundError as exc:
        if exc.name != "bench.bird_sdk_driver":
            raise
        pytest.fail("BIRD_SDK_API_ABSENT: shared bridge not implemented")


def _case(tmp_path, monkeypatch):
    from bench.test_bird_sdk_driver_integration import make_case
    return make_case(tmp_path, monkeypatch, _api())


def test_projection_seal(tmp_path, monkeypatch):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    assert (len(c.draw.planned), len(c.draw.eligible), len(c.draw.exclusions)) == (8, 7, 1)
    p = c.driver.projection
    assert p.task_ids == tuple(t.name for t in c.draw.eligible)
    assert len(p.bash + p.ptc) == 14
    for private, bash, ptc in zip(c.draw.eligible, p.bash, p.ptc, strict=True):
        for row in (bash, ptc):
            assert type(row) is TaskData
            assert row.model_dump() == TaskData(name=row.name, prompt=row.prompt).model_dump()
            text = row.model_dump_json()
            assert str(private.db_path) not in text, "PROJECTION_PRIVATE_PATH"
            assert private.gold_sql not in text, "PROJECTION_PRIVATE_GOLD"
            assert not any(key in text for key in ("gold_sql", "db_path", "qa_binding"))
        assert bash.prompt.replace(BASH_CHANNEL.format(tool=SQL_TOOL), "") == (
            ptc.prompt.replace(PTC_CHANNEL.format(tool=SQL_TOOL), ""))
    canary = dataclasses.replace(c.draw.eligible[0], gold_sql="SECRET_GOLD_CANARY",
                                db_path=Path("/HOST_PRIVATE_CANARY.sqlite"))
    safe = a.project_sql_tasks((canary,), schemas=("CREATE TABLE public(x)",),
                               action_max_rows=c.instrument.action_max_rows)
    assert "SECRET_GOLD_CANARY" not in safe.bash[0].model_dump_json(), "PROJECTION_GOLD_LEAK"
    assert "HOST_PRIVATE_CANARY" not in safe.ptc[0].model_dump_json()
    assert p.sha256 == a.project_sql_tasks(c.draw.eligible, schemas=c.schemas,
        action_max_rows=c.instrument.action_max_rows).sha256
    p.bash[0].skills.append("mutable-drift")
    with pytest.raises(a.BirdSdkBridgeError):
        c.run_arm("bash")
    c.assert_no_dispatch()


def test_preflight_refuses_drift(tmp_path, monkeypatch):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    request = c.request("bash")
    drifts = dict(plan_id="foreign", arm="other", tasks=request.tasks[:-1],
                  instrument=dataclasses.replace(c.instrument, identity="other"),
                  policy_identity="other", num_rollouts=2)
    for field, value in drifts.items():
        with pytest.raises(a.BirdSdkBridgeError):
            c.consume(dataclasses.replace(request, **{field: value}))
    c.assert_no_dispatch()
    binding = c.bindings["bash"]
    # Match independent expectations to each deliberately UNSAFE config:
    # these must fail hard admission rules, not merely an unequal JSON dump.
    cases = [
        ("push", True), ("resume", True), ("clean", True), ("dry_run", True),
        ("shuffle", True), ("run.attach", "existing-run"), ("num_tasks", 1),
        ("num_rollouts", 2), ("max_concurrent", None), ("max_concurrent", 3),
        ("env.max_concurrent_agents", None), ("env.max_concurrent_agents", 3),
        ("env.retries.max_retries", 1), ("env.retries.include", ["all"]),
        ("env.retries.exclude", ["all"]), ("env.timeout.episode", None),
        ("env.timeout.finalize", 0), ("env.taskset.system_prompt", Path("/unused")),
        ("env.taskset.task.judges", ["unexpected"]),
        ("env.taskset.task.rewards", {"report": 1}),
        ("env.taskset.task.stops", {"report": 1}),
        ("env.taskset.task.metrics", {"report": 1}),
        ("env.agent.retries.max_retries", 1), ("env.agent.retries.include", ["all"]),
        ("env.agent.retries.exclude", ["all"]), ("env.agent.timeout.setup", None),
        ("env.agent.timeout.rollout", 0), ("env.agent.timeout.finalize", math.inf),
        ("env.agent.timeout.scoring", math.nan), ("env.agent.max_turns", 4),
        ("env.agent.harness.max_turns", 4),
        ("env.agent.harness.program_timeout", 3),
        ("env.agent.harness.action_max_rows", 18),
        ("env.agent.harness.query_timeout_s", 4),
        ("env.agent.harness.instrument_identity", "different"),
        ("env.agent.harness.sampling_identity", "different"),
        ("env.agent.harness.arm", "unknown"),
        ("env.agent.harness.policy_identity", ""),
        ("env.agent.harness.skills", ["reporting"]),
        ("env.agent.harness.env", {"REPORTING": "on"}),
        ("env.agent.harness.forward_env", ["REPORTING"]),
        ("env.agent.harness.mcp_header_env", {"server": {"x-report": "REPORTING"}}),
        ("env.agent.harness.disabled_tools", ["execute_sql"]),
        ("env.agent.harness.tool_timeout", 0),
    ]
    def assign(obj, path, value):
        parts = path.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
    for path, value in cases:
        bad = binding.config.model_copy(deep=True)
        agent = binding.expected.effective_agent.model_copy(deep=True)
        assign(bad, path, value)
        if path.startswith("env.agent."):
            assign(agent, path.removeprefix("env.agent."), value)
        expected = dataclasses.replace(binding.expected, config=bad.model_copy(deep=True),
                                       effective_agent=agent)
        with pytest.raises(a.BirdSdkBridgeError):
            a.admit_sdk_config(bad, expected=expected, instrument=c.instrument,
                               output_root=c.output_root)
    c.assert_no_dispatch()
    config = c.bindings["bash"].config
    config.env.agent.harness.skills.append("reporting-drift")
    with pytest.raises(a.BirdSdkBridgeError):
        c.run_arm("bash")
    c.assert_no_dispatch()


def test_effective_settings(tmp_path, monkeypatch):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    binding = c.bindings["bash"]
    # Independent expected full config. Even excluded fields and field-set-only
    # sampling changes must refuse; admission is not just a serialized JSON hash.
    for field, value in (("resume", True), ("clean", True), ("dry_run", True),
                         ("push", True), ("shuffle", True), ("num_tasks", 1),
                         ("num_rollouts", 2), ("max_concurrent", 3)):
        bad = binding.config.model_copy(deep=True, update={field: value})
        with pytest.raises(a.BirdSdkBridgeError):
            a.admit_sdk_config(bad, expected=binding.expected,
                              instrument=c.instrument, output_root=c.output_root)
    for field, value in (("model", "wrong-model"), ("client", None),
                         ("sampling", SamplingConfig(temperature=0.99))):
        wrong = binding.expected.effective_agent.model_copy(update={field: value})
        expected = dataclasses.replace(binding.expected, effective_agent=wrong)
        with pytest.raises(a.BirdSdkBridgeError, match="effective"):
            a.admit_sdk_config(binding.config, expected=expected,
                              instrument=c.instrument, output_root=c.output_root)
    changed = binding.config.model_copy(deep=True)
    changed.sampling.model_fields_set.add("reasoning_effort")
    with pytest.raises(a.BirdSdkBridgeError):
        a.admit_sdk_config(changed, expected=binding.expected,
                          instrument=c.instrument, output_root=c.output_root)
    # Field-set drift also matters recursively inside sampling extras.
    left = SamplingConfig(extra_body={"nested": SamplingConfig(top_p=0.8)})
    right = left.model_copy(deep=True)
    right.extra_body["nested"].model_fields_set.add("temperature")
    assert left.model_dump() == right.model_dump()
    assert a._snapshot(left) != a._snapshot(right)
    c.assert_no_dispatch()
    rows = c.run_arm("bash")
    assert len(rows) == 7 and c.state.responses == 14
    for agent, trace in zip(c.state.agents, c.state.traces, strict=True):
        assert agent.config == binding.expected.effective_agent
        assert trace.agent.config == binding.expected.effective_agent
    assert len(c.state.checked_requests) == 14
    c.state.policy_rejections.clear()
    body, native = c.state.checked_requests[0]
    for bad in (dict(body, model="wrong"), dict(body, temperature=0.99),
                dict(body, unknown_envelope="wrong")):
        with pytest.raises(a.BirdSdkBridgeError):
            c.state.policy.validate("openai", bad, native)
    with pytest.raises(a.BirdSdkBridgeError):
        c.state.policy.validate("openai", body, SamplingConfig(temperature=0.99))
    assert c.state.responses == 14, "REJECTED_REQUEST_PRODUCED_RESPONSE"


def test_original_ex_decoder(tmp_path, monkeypatch):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    rows = c.run_arm("bash")
    assert {r.metrics[0].score for r in rows} == {0.0, 1.0}
    episodes, receipts = c.state.episodes, c.state.receipts
    assert all(type(e) is Episode for e in episodes)
    assert all(type(r.trace) is Trace and type(r.result) is ExResult for r in receipts)
    assert {r.result.status for r in receipts} == {"match", "mismatch"}
    with pytest.raises(a.BirdSdkBridgeError):
        c.decode(scores=())
    first = receipts[0]
    from bench.score import execution_accuracy
    invalid_gold = execution_accuracy("SELECT 1", dataclasses.replace(
        c.draw.eligible[0], gold_sql="SELECT * FROM absent_bridge_gold_table"),
        timeout_s=c.draw.timeout_s, max_rows=c.draw.max_rows, compare=c.draw.comparison)
    assert invalid_gold.valid is False
    for result in (None, invalid_gold):
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode(scores=(a.SqlScoreReceipt(first.trace, result),) + receipts[1:])
    for score in (None, True, 0.5, float("nan"), float("inf")):
        bad = a.SqlScoreReceipt(first.trace, dataclasses.replace(first.result, score=score))
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode(scores=(bad,) + receipts[1:])
    for result in (dataclasses.replace(first.result, valid=False),
                   dataclasses.replace(first.result, status="gold_error"),
                   dataclasses.replace(first.result, status="db_missing"),
                   dataclasses.replace(first.result, status="mismatch", score=1.0)):
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode(scores=(a.SqlScoreReceipt(first.trace, result),) + receipts[1:])
    trace = first.trace
    saved = trace.rewards.copy()
    for rewards in ({}, {**saved, "extra": next(iter(saved.values()))}):
        trace.rewards = rewards
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode()
    trace.rewards = saved
    reward = trace.rewards["execution_accuracy"]
    for field, value in (("weight", 0.5), ("weight", True), ("score", True),
                         ("score", math.nan), ("score", 0.25)):
        old = getattr(reward, field)
        setattr(reward, field, value)
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode()
        setattr(reward, field, old)
    for obj, field, value in ((episodes[0], "ok", False), (trace, "ok", False),
                              (trace, "is_completed", False)):
        old = getattr(obj, field)
        setattr(obj, field, value)
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode()
        setattr(obj, field, old)
    assert c.decode() == rows


def test_membership_and_hash(tmp_path, monkeypatch):
    a = _api()
    c = _case(tmp_path, monkeypatch)
    original = c.run_arm("bash")
    episodes, scores = c.state.episodes, c.state.receipts
    assert c.decode(episodes=episodes[::-1], scores=scores[::-1]) == original
    for wrong in (episodes[:-1], episodes + episodes[:1], (episodes[0],) * 7,
                  tuple(e.model_dump() for e in episodes)):
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode(episodes=wrong)
    for e in episodes:
        assert len(e.traces) == 1
        for task in (e.task, e.traces[0].task):
            assert task.key == task.hash == task_key(task.data.model_dump(mode="json", exclude_none=True))
    e = episodes[0]
    for obj, field, value in ((e, "id", episodes[1].id),
                              (e.task, "type", "foreign"),
                              (e.task, "hash", "foreign"),
                              (e.task, "key", "foreign"),
                              (e.traces[0].task, "hash", "foreign"),
                              (e.traces[0].task, "key", "foreign"),
                              (e.traces[0].task, "type", "foreign"),
                              (e.traces[0], "id", episodes[1].traces[0].id),
                              (e, "traces", e.traces * 2),
                              (e.task, "data", TaskData(name="foreign", prompt="foreign"))):
        old = getattr(obj, field)
        setattr(obj, field, value)
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode()
        setattr(obj, field, old)
    substituted = a.SqlScoreReceipt(scores[0].trace.model_copy(deep=True), scores[0].result)
    with pytest.raises(a.BirdSdkBridgeError):
        c.decode(scores=(substituted,) + scores[1:])
    with pytest.raises(a.BirdSdkBridgeError):
        c.decode(scores=scores + scores[:1])
    # Both arms omitting the same task still fails independently.
    for arm in ("bash", "ptc"):
        with pytest.raises(a.BirdSdkBridgeError):
            c.decode(episodes=episodes[:-1], arm=arm)
