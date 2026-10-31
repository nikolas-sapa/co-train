"""Unit tests for `cotrain_bash_qa_env` — the eval-level reporting Env.

`ptc/test_bash_qa_activation.py` proved the serialized-config activation
route; this file proves the evaluation wrapper contract
(`spec/bash-qa-eval.md`): the canonical `cotrain_bash_qa_env` Env plugin,
the `run_bash_qa_eval(config)` wrapper's preflight refusals (zero SDK
calls), the scoped ContextVar admission (constructor claim, revocation on
every exit, inherited-record refusals), the per-run fresh channel and the
fixed-key `trace.info["cotrain_bash_qa"]` attachment, and the seed
`build_bash_qa_task` contract through the REAL configured runner.

The product module is the flat root file `cotrain_bash_qa_env.py`, imported
inside test bodies: a missing or incomplete implementation fails, never
skips.

Declared seams/stubs (per the unit split; the real on-disk plugin, real
`run_eval` lifecycle and JSONL writer belong to the integration worker):

* SDK `run_eval` is stubbed at the real module
  `verifiers.v1.cli.eval.runner` AND at any product-module binding whose
  value IS the original SDK function (no import-alias guessing). The fake
  loads the real Env and seed Taskset through the real SDK loaders.
* `run_configured_bash_qa` is stubbed the same way ONLY for isolated
  Env/channel/telemetry/lifecycle tests. Where the seed callback shape,
  binding and close behaviour are under test, the REAL runner runs against
  a real configured `Agent` whose `agent.run` is stubbed per the existing
  unit boundary (a lifecycle driver or a never-reached sentinel).
* `BashHarness.launch` is delegated for the one real-channel lifecycle
  test — the existing unit boundary for the real subprocess program.
* The seed Taskset ships in a unit-only `ModuleType` + `ModuleSpec`
  registry entry (`qa_eval_unit_taskset`) so real
  `narrow_plugin_field`/`taskset_config_type`/`load_taskset` resolve it.

Never stubbed: `run_bash_qa` (the forwarding entry point), the private
`_permit`, the product ContextVar, or any SDK loader.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import json
import os
import subprocess
import sys
import warnings
from functools import partial
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Literal

import pytest

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cotrain_bash_qa as cotrain_qa  # noqa: E402
import ptc.bash_qa as bash_qa  # noqa: E402
import verifiers.v1.cli.eval.runner as eval_runner  # noqa: E402

from cotrain_bash_qa import (  # noqa: E402
    ReportingBashConfig,
    ReportingBashHarness,
)
from verifiers.v1.agent import Agent, Agents  # noqa: E402
from verifiers.v1.configs.agent import AgentConfig  # noqa: E402
from verifiers.v1.configs.cli.eval import EvalConfig  # noqa: E402
from verifiers.v1.configs.env import EnvConfig  # noqa: E402
from verifiers.v1.configs.retries import RetryConfig  # noqa: E402
from verifiers.v1.configs.task import TaskConfig  # noqa: E402
from verifiers.v1.configs.taskset import TasksetConfig  # noqa: E402
from verifiers.v1.env import Env  # noqa: E402
from verifiers.v1.envs.single_agent import (  # noqa: E402
    SingleAgentEnvConfig,
)
from verifiers.v1.episode import Episode, EnvInfo  # noqa: E402
from verifiers.v1.harnesses.bash.harness import (  # noqa: E402
    BashHarness,
    CompactionConfig,
)
from verifiers.v1.runtimes import PrimeConfig, ProgramResult  # noqa: E402
from verifiers.v1.task import Task, TaskData  # noqa: E402
from verifiers.v1.taskset import Taskset  # noqa: E402
from verifiers.v1.trace import TraceTask  # noqa: E402
from verifiers.v1.utils.loaders import (  # noqa: E402
    environment_class,
    env_config_type,
    import_environment,
    load_environment,
)

from ptc.sql_qa import (  # noqa: E402
    MAX_EXPORT_BYTES,
    MAX_REPORTS_PER_ARM,
    QaChannel,
    REPORT_TOOL,
    ReportRejected,
)
from ptc.test_bash_qa import (  # noqa: E402
    INTERCEPT_URL,
    _ctx,
    _report_request,
    _runtime,
    _trace,
)
from ptc.test_bash_qa_activation import _agent_config_dict  # noqa: E402
from ptc.test_harness import ENDPOINT, SECRET  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ENV_ID = "cotrain_bash_qa_env"
CANONICAL_HARNESS_ID = "cotrain_bash_qa"
QA_KEY = "cotrain_bash_qa"
UNIT_TASKSET_ID = "qa_eval_unit_taskset"
OUTER_TIMEOUT_S = 20.0
INNER_TIMEOUT_S = 10.0
UNSET = object()


# ---------------------------------------------------------------------------
# The unit-only seed/taskset pair and its in-memory plugin registry entry.
# ---------------------------------------------------------------------------


class UnitSeedTask(Task):
    """The supported seed shape: the builder returns a paired subclass
    preserving exact `data`/`config` identity and — crucially — the ACTUAL
    binding the runner hands in (a fresh `BashQaBinding()` here would make
    the wrong-binding refusal vacuous). `builder_calls` records each
    invocation so refused-before-invocation is distinguishable."""

    def __init__(self, *args, **kwargs):
        self.builder_calls = []
        super().__init__(*args, **kwargs)

    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return UnitPairedTask(self.data, self.config, qa_binding=binding)


class UnitPairedTask(bash_qa.BashQaTaskMixin, UnitSeedTask):
    """The explicit paired subclass: Task + mixin, `isinstance` of the seed."""


class _ForeignPaired(bash_qa.BashQaTaskMixin, Task):
    """A valid pairing on an UNRELATED Task class: fails `isinstance(result,
    type(seed))` while satisfying every other return-shape check."""


class UnitTasksetConfig(TasksetConfig):
    id: Literal[UNIT_TASKSET_ID] = UNIT_TASKSET_ID


_CLAIM_PROBE = None
"""Optional (env_config, sink) armed by the claim-order test: set inside
`UnitTaskset.__init__` — which runs during `Env.__init__` BEFORE the env's
taskset work finishes — to prove the admission claim already happened."""


class UnitTaskset(Taskset[UnitSeedTask, UnitTasksetConfig]):
    def __init__(self, config):
        global _CLAIM_PROBE
        probe, _CLAIM_PROBE = _CLAIM_PROBE, None  # disarm before recursing
        if probe is not None:
            env_cfg, sink = probe
            import cotrain_bash_qa_env as _prod_mod

            try:
                sink.append(("constructed", _prod_mod.ReportingBashEnv(env_cfg)))
            except Exception as exc:  # noqa: BLE001 - outcome is the oracle
                sink.append(("refused", exc))
        super().__init__(config)

    def load(self):
        yield UnitSeedTask(
            TaskData(prompt="Synthetic unit probe."), self.config.task)


def _register_unit_taskset() -> None:
    """Unit-only seam: a tiny `ModuleType`+`ModuleSpec` registry entry so the
    real SDK plugin path (`_import_plugin` -> sys.modules hit) resolves this
    file's taskset without an on-disk package."""
    module = ModuleType(UNIT_TASKSET_ID)
    module.__all__ = ["UnitTaskset"]
    module.UnitTaskset = UnitTaskset
    module.__spec__ = ModuleSpec(UNIT_TASKSET_ID, loader=None)
    sys.modules[UNIT_TASKSET_ID] = module


_register_unit_taskset()


def _prod():
    """Import the product module inside the test call: a missing or
    incomplete implementation is a failure, never a skip."""
    import cotrain_bash_qa_env

    return cotrain_bash_qa_env


# ---------------------------------------------------------------------------
# Config builders and the declared SDK/runner stubs.
# ---------------------------------------------------------------------------


def _eval_payload(tmp_path: Path, *, env_update=None, taskset_update=None,
                  **top) -> dict:
    env = {
        "id": CANONICAL_ENV_ID,
        "taskset": {"id": UNIT_TASKSET_ID, **(taskset_update or {})},
        "interception": {"type": "server"},
        "agent": {
            "harness": {
                "id": CANONICAL_HARNESS_ID,
                "edit": False,
                "search": False,
            },
            "runtime": {"type": "subprocess"},
            "max_turns": 3,
            "retries": {"max_retries": 0},
        },
        "retries": {"max_retries": 0},
    }
    env.update(env_update or {})
    data = {
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "UNIT_UNUSED_API_KEY"},
        "env": env,
        "num_tasks": 1,
        "num_rollouts": 1,
        "max_concurrent": 1,
        "push": False,
        "rich": None,
        "resume": False,
        "clean": False,
        "output_dir": str(tmp_path),
        "run": {"dir": "unit"},
    }
    data.update(top)
    return data


def _eval_config(tmp_path: Path, **kwargs) -> EvalConfig:
    """The individually-valid baseline: every refusal case mutates exactly
    one thing off this, so the refusal reason is the actual check, not an
    earlier binding/type error."""
    return EvalConfig.model_validate_json(
        json.dumps(_eval_payload(tmp_path, **kwargs)))


def _mutated(config: EvalConfig, *, env=UNSET, env_update=None,
             agent_update=None, harness=UNSET, run_update=None,
             **top) -> EvalConfig:
    """Unvalidated single-point mutations of a VALID config (model_copy
    bypasses re-validation — that is the forged-copy mechanism under test)."""
    if env is not UNSET:
        top["env"] = env
    else:
        env_update = dict(env_update or {})
        if agent_update is not None or harness is not UNSET:
            agent = dict(agent_update or {})
            if harness is not UNSET:
                agent["harness"] = (
                    config.env.agent.harness.model_copy(update=harness)
                    if isinstance(harness, dict)
                    else harness
                )
            env_update["agent"] = config.env.agent.model_copy(update=agent)
        if env_update:
            top["env"] = config.env.model_copy(update=env_update)
    if run_update is not None:
        top["run"] = config.run.model_copy(update=run_update)
    return config.model_copy(update=top)


def _patch_run_eval(monkeypatch, prod, fake):
    """Stub SDK `run_eval` at the real module plus every product binding
    whose value IS the original function — whichever import shape the
    product chose, the same fake answers."""
    original = eval_runner.run_eval
    monkeypatch.setattr(eval_runner, "run_eval", fake)
    for name, value in vars(prod).items():
        if value is original:
            monkeypatch.setattr(prod, name, fake)


def _patch_configured_runner(monkeypatch, prod, body):
    """Stub `run_configured_bash_qa` at `cotrain_bash_qa` plus every product
    binding of the original — the declared seam for isolated Env/channel/
    telemetry/lifecycle tests only. Returns the captured call list."""
    calls = []

    async def stub(agent, make_task, *args, qa_factory=None, **kwargs):
        factory = qa_factory if qa_factory is not None else (
            args[0] if args else None)
        calls.append({
            "agent": agent,
            "make_task": make_task,
            "qa_factory": factory,
        })
        return await body(agent, make_task, factory)

    original = cotrain_qa.run_configured_bash_qa
    monkeypatch.setattr(cotrain_qa, "run_configured_bash_qa", stub)
    for name, value in vars(prod).items():
        if value is original:
            monkeypatch.setattr(prod, name, stub)
    return calls


def _never_runner(agent, make_task, qa_factory):
    raise AssertionError("the configured runner must not be reached")


def _configured_qa_agent() -> Agent:
    """A real Agent through the real loader path: unbound
    `ReportingBashHarness`, canonical config on `agent.config.harness`.
    A dummy Agent would not survive the real runner's admission."""
    return Agent(AgentConfig.model_validate(_agent_config_dict()))


def _agents_for(config: EvalConfig, agent: Agent) -> Agents:
    """A real `Agents` value over the env config's `agent` seat."""
    return Agents(config.env, lambda name, spec: agent)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, OUTER_TIMEOUT_S))


def _seed(env, prompt="go"):
    return UnitSeedTask(TaskData(prompt=prompt), env.taskset.config.task)


class _Boom(Exception):
    pass


# ---------------------------------------------------------------------------
# Plugin surface: one Env export, explicit generic, config surface.
# ---------------------------------------------------------------------------


def test_flat_env_plugin_resolves_exactly_one_env():
    """The flat canonical ID resolves through the real `_import_plugin` /
    `_plugin_class` path to exactly one Env subclass; the explicit
    `Env[ReportingBashEnvConfig]` generic gives the narrowing
    `env_config_type`; the dotted ID dies at `find_spec`."""
    prod = _prod()
    assert prod.__all__ == ["ReportingBashEnv"]

    module = import_environment(CANONICAL_ENV_ID)
    assert module is prod
    exported = [
        obj for name in module.__all__
        if isinstance(obj := getattr(module, name, None), type)
        and issubclass(obj, Env) and obj is not Env
    ]
    assert exported == [prod.ReportingBashEnv]
    assert environment_class("", CANONICAL_ENV_ID) is prod.ReportingBashEnv
    assert env_config_type("", CANONICAL_ENV_ID) is prod.ReportingBashEnvConfig

    with pytest.raises(ModuleNotFoundError):
        import_environment("ptc.cotrain_bash_qa_env")


def test_env_config_overrides_only_the_id():
    """`ReportingBashEnvConfig` adds NO fields and changes NO inherited
    default: every model field except `id` equals `SingleAgentEnvConfig`'s,
    and the JSON schema's PROPERTY KEYS are identical — no serialized
    factory/binding/channel keys, asserted on keys not docstrings."""
    prod = _prod()
    config = prod.ReportingBashEnvConfig()
    base = SingleAgentEnvConfig()

    assert config.id == CANONICAL_ENV_ID
    assert set(prod.ReportingBashEnvConfig.model_fields) == set(
        SingleAgentEnvConfig.model_fields)
    for name in SingleAgentEnvConfig.model_fields:
        if name == "id":
            continue
        assert getattr(config, name) == getattr(base, name), name
    assert config.agent.model_dump(mode="json") == base.agent.model_dump(
        mode="json")
    assert isinstance(
        prod.ReportingBashEnvConfig.model_fields["agent"].default,
        AgentConfig)

    props = prod.ReportingBashEnvConfig.model_json_schema()["properties"]
    assert set(props) == set(
        SingleAgentEnvConfig.model_json_schema()["properties"])
    for key in ("qa_factory", "qa_binding", "binding", "factory",
                "channel", "_qa_required", "_permit"):
        assert key not in props
    assert CANONICAL_ENV_ID in json.dumps(props["id"])

    with pytest.raises(Exception):
        prod.ReportingBashEnvConfig.model_validate(
            {"id": "other_env", "taskset": {"id": UNIT_TASKSET_ID}})


def test_env_config_taskset_coercion_preserved():
    """The inherited `_resolve_taskset` narrowing still runs: a dict
    taskset id resolves to the unit taskset's own config type."""
    prod = _prod()
    config = prod.ReportingBashEnvConfig.model_validate(
        {"id": CANONICAL_ENV_ID, "taskset": {"id": UNIT_TASKSET_ID}})
    assert type(config.taskset) is UnitTasksetConfig


def test_eval_json_roundtrip_real_sdk_narrowing_and_one_env(tmp_path):
    """Canonical EvalConfig JSON narrows `env` to the real
    `ReportingBashEnvConfig` (and the seat harness to `ReportingBashConfig`)
    through the actual SDK path; dump -> revalidate is a fixed point;
    `load_environment` yields exactly one `ReportingBashEnv` whose
    `config is config.env`, with the seed taskset and the unbound
    canonical harness resolved."""
    prod = _prod()
    config = _eval_config(tmp_path)

    assert type(config.env) is prod.ReportingBashEnvConfig
    assert config.env.id == CANONICAL_ENV_ID
    assert type(config.env.taskset) is UnitTasksetConfig
    assert type(config.env.agent.harness) is ReportingBashConfig
    assert type(config.env.agent_harnesses()["agent"]) is ReportingBashConfig

    restored = EvalConfig.model_validate_json(config.model_dump_json())
    assert type(restored.env) is prod.ReportingBashEnvConfig
    assert type(restored.env.agent.harness) is ReportingBashConfig
    assert restored.model_dump(mode="json") == config.model_dump(mode="json")

    env = load_environment(restored.env)
    assert type(env) is prod.ReportingBashEnv
    assert env.config is restored.env
    assert type(env.taskset) is UnitTaskset
    # Loader-probe parity: the seat's resolved harness object.
    assert type(env._harnesses["agent"]) is ReportingBashHarness
    seed, = list(env.taskset)
    assert type(seed) is UnitSeedTask


def test_public_signature_is_one_eval_config():
    """`run_bash_qa_eval` is async and takes exactly one EvalConfig."""
    prod = _prod()
    assert inspect.iscoroutinefunction(prod.run_bash_qa_eval)
    params = list(
        inspect.signature(prod.run_bash_qa_eval).parameters.values())
    assert len(params) == 1
    assert params[0].annotation in (EvalConfig, "EvalConfig")


# ---------------------------------------------------------------------------
# Wrapper: delegation and the independent preflight refusals (0 SDK calls).
# ---------------------------------------------------------------------------


def test_wrapper_delegates_to_sdk_run_eval_once(monkeypatch, tmp_path):
    """A supported config delegates to the real `run_eval` exactly once,
    with the same config object, and returns its episodes untouched."""
    prod = _prod()
    config = _eval_config(tmp_path)
    episode = Episode(
        env=EnvInfo(id=CANONICAL_ENV_ID),
        task=TraceTask(type="UnitSeedTask", data=TaskData()),
    )
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        return [episode]

    _patch_run_eval(monkeypatch, prod, fake)
    result = _run(prod.run_bash_qa_eval(config))
    assert result == [episode]
    assert calls == [config]


def _sub_env_config(prod, config):
    sub = type("SubEnvConfig", (prod.ReportingBashEnvConfig,), {})
    return sub.model_validate(config.env.model_dump())


def _sub_harness_config(prod, config):
    sub = type("SubReportingConfig", (ReportingBashConfig,), {})
    return sub.model_validate(config.env.agent.harness.model_dump())


_PREFLIGHT_CASES = [
    (
        "resume_true",
        lambda prod, c: _mutated(c, resume=True),
        "resume",
    ),
    (
        "resume_truthy_int",
        lambda prod, c: _mutated(c, resume=1),
        "resume",
    ),
    (
        "clean_true",
        lambda prod, c: _mutated(c, clean=True),
        "clean",
    ),
    (
        "push_true",
        lambda prod, c: _mutated(c, push=True),
        "push",
    ),
    (
        "attach_set",
        lambda prod, c: _mutated(c, run_update={"attach": "eval-1"}),
        "attach",
    ),
    (
        "env_retries",
        lambda prod, c: _mutated(
            c, env_update={"retries": RetryConfig(max_retries=1)}),
        "retr",
    ),
    (
        "env_wrong_type",
        lambda prod, c: _mutated(
            c, env=SingleAgentEnvConfig.model_validate(c.env.model_dump())),
        "env",
    ),
    (
        "env_base_type",
        lambda prod, c: _mutated(
            c, env=EnvConfig.model_validate({
                "id": CANONICAL_ENV_ID,
                "taskset": c.env.taskset.model_dump(),
            })),
        "env",
    ),
    (
        "env_forged_id",
        lambda prod, c: _mutated(
            c, env=c.env.model_copy(update={"id": "other_env"})),
        "env",
    ),
    (
        "env_subclass",
        lambda prod, c: _mutated(c, env=_sub_env_config(prod, c)),
        "env",
    ),
    (
        "harness_wrong_id",
        lambda prod, c: _mutated(c, harness={"id": "bash"}),
        "harness|cotrain_bash_qa",
    ),
    (
        "harness_wrong_type",
        lambda prod, c: _mutated(
            c,
            harness=bash_qa.QaBashHarnessConfig(
                id=CANONICAL_HARNESS_ID, edit=False, search=False)),
        "harness",
    ),
    (
        "harness_forged_id",
        lambda prod, c: _mutated(
            c, harness=c.env.agent.harness.model_copy(
                update={"id": "bash"})),
        "cotrain_bash_qa|harness",
    ),
    (
        "harness_subclass",
        lambda prod, c: _mutated(c, harness=_sub_harness_config(prod, c)),
        "harness",
    ),
    (
        "harness_absent",
        lambda prod, c: _mutated(c, harness=None),
        "harness",
    ),
    (
        "runtime_not_subprocess",
        lambda prod, c: _mutated(
            c, agent_update={"runtime": PrimeConfig()}),
        "subprocess|runtime",
    ),
    (
        "turns_unbounded",
        lambda prod, c: _mutated(c, agent_update={"max_turns": None}),
        "turn",
    ),
    (
        "turns_zero",
        lambda prod, c: _mutated(c, agent_update={"max_turns": 0}),
        "turn",
    ),
    (
        "turns_negative",
        lambda prod, c: _mutated(c, agent_update={"max_turns": -2}),
        "turn",
    ),
    (
        "turns_infinite",
        lambda prod, c: _mutated(
            c, agent_update={"max_turns": float("inf")}),
        "turn",
    ),
    (
        "agent_retries",
        lambda prod, c: _mutated(
            c, agent_update={"retries": RetryConfig(max_retries=1)}),
        "retr",
    ),
    (
        "edit_enabled",
        lambda prod, c: _mutated(c, harness={"edit": True}),
        "edit",
    ),
    (
        "search_enabled",
        lambda prod, c: _mutated(c, harness={"search": True}),
        "search",
    ),
    (
        "skills_set",
        lambda prod, c: _mutated(
            c, harness={"skills": [{"runtime": "/s"}]}),
        "skill",
    ),
    (
        "compaction_set",
        lambda prod, c: _mutated(
            c, harness={"compaction": CompactionConfig()}),
        "compaction",
    ),
    (
        "model_missing",
        lambda prod, c: _mutated(c, model=""),
        "model",
    ),
    (
        "num_tasks_unbounded",
        lambda prod, c: _mutated(c, num_tasks=None),
        "num_tasks",
    ),
    (
        "num_tasks_zero",
        lambda prod, c: _mutated(c, num_tasks=0),
        "num_tasks",
    ),
    (
        "num_rollouts_zero",
        lambda prod, c: _mutated(c, num_rollouts=0),
        "num_rollouts",
    ),
    (
        "num_rollouts_unbounded",
        lambda prod, c: _mutated(c, num_rollouts=None),
        "num_rollouts",
    ),
    (
        "max_concurrent_unbounded",
        lambda prod, c: _mutated(c, max_concurrent=None),
        "max_concurrent",
    ),
    (
        "max_concurrent_zero",
        lambda prod, c: _mutated(c, max_concurrent=0),
        "max_concurrent",
    ),
]


@pytest.mark.parametrize(
    "label,mutate,match",
    _PREFLIGHT_CASES,
    ids=[case[0] for case in _PREFLIGHT_CASES],
)
def test_wrapper_preflight_refuses_before_sdk(
        monkeypatch, tmp_path, label, mutate, match):
    """Each forbidden flag/config refuses independently — the refusal names
    its actual reason (not an earlier binding/type error) and SDK `run_eval`
    is never reached. A refused call leaves no residue: a subsequent valid
    call still delegates."""
    prod = _prod()
    bad = mutate(prod, _eval_config(tmp_path))
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception, match=match):
        _run(prod.run_bash_qa_eval(bad))
    assert calls == [], label

    good = _eval_config(tmp_path)
    assert _run(prod.run_bash_qa_eval(good)) == []
    assert calls == [good]


@pytest.mark.parametrize("field", [
    "num_tasks", "num_rollouts", "max_concurrent", "max_turns",
])
@pytest.mark.parametrize("value", [True, 1.0, float("inf"), float("nan")])
def test_numeric_bounds_require_actual_integers(
        monkeypatch, tmp_path, field, value):
    prod = _prod()
    config = _eval_config(tmp_path)
    bad = (
        _mutated(config, agent_update={field: value})
        if field == "max_turns" else _mutated(config, **{field: value})
    )
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(ValueError, match=field):
        _run(prod.run_bash_qa_eval(bad))
    assert calls == []
    assert _run(prod.run_bash_qa_eval(config)) == []
    assert calls == [config]


@pytest.mark.parametrize("seat", ["env", "agent"])
def test_retry_zero_must_not_be_boolean(monkeypatch, tmp_path, seat):
    prod = _prod()
    config = _eval_config(tmp_path)
    retries = config.env.retries.model_copy(update={"max_retries": False})
    bad = (
        _mutated(config, env_update={"retries": retries})
        if seat == "env" else _mutated(config, agent_update={"retries": retries})
    )
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(ValueError, match="retries"):
        _run(prod.run_bash_qa_eval(bad))
    assert calls == []


# ---------------------------------------------------------------------------
# Scoped admission: constructor claim, run requirements, revocation.
# ---------------------------------------------------------------------------


def test_bare_constructor_loads_but_run_refuses(monkeypatch, tmp_path):
    """Without any wrapper admission the constructor still works for
    loading (taskset + harness resolved), but `Env.run` refuses with zero
    runner calls — a bare stock path cannot run reported."""
    prod = _prod()
    config = _eval_config(tmp_path)
    env = load_environment(config.env)
    assert type(env) is prod.ReportingBashEnv
    assert type(env.taskset) is UnitTaskset

    runner_calls = _patch_configured_runner(monkeypatch, prod, _never_runner)
    agent = _configured_qa_agent()
    reached = []

    async def drive(task):
        reached.append(task)
        return _trace(task, agent)

    agent.run = drive
    seed = _seed(env)
    with pytest.raises(Exception):
        _run(env.run(seed, _agents_for(config, agent)))
    assert runner_calls == []
    assert reached == []

    direct = prod.ReportingBashEnv(config.env)
    with pytest.raises(Exception):
        _run(direct.run(seed, _agents_for(config, agent)))
    assert runner_calls == []


def test_env_claimed_at_constructor_before_taskset_work(
        monkeypatch, tmp_path):
    """Under an active admission the Env is claimed BEFORE its own taskset
    work: a second `ReportingBashEnv` attempted from inside taskset
    construction is refused. Bare construction (control) allows it."""
    prod = _prod()
    config = _eval_config(tmp_path)
    global _CLAIM_PROBE

    # Control: bare construction allows the inner second env.
    sink = []
    _CLAIM_PROBE = (config.env, sink)
    try:
        load_environment(config.env)
    finally:
        _CLAIM_PROBE = None
    outcome, inner = sink[0]
    assert outcome == "constructed"
    assert type(inner) is prod.ReportingBashEnv

    # Under admission: the first env claims itself before loading the
    # taskset, so the taskset's nested construction attempt refuses.
    sink = []
    captured = {}

    async def fake(cfg):
        captured["env"] = load_environment(cfg.env)
        return []

    _patch_run_eval(monkeypatch, prod, fake)

    async def armed():
        global _CLAIM_PROBE
        _CLAIM_PROBE = (config.env, sink)
        try:
            return await prod.run_bash_qa_eval(config)
        finally:
            _CLAIM_PROBE = None

    _run(armed())
    outcome, exc = sink[0]
    assert outcome == "refused"
    assert isinstance(exc, Exception)
    assert type(captured["env"]) is prod.ReportingBashEnv


def test_second_env_instance_under_one_admission_refuses(
        monkeypatch, tmp_path):
    """One admission claims exactly one Env: a second ReportingBashEnv —
    same config object or an equal other instance — refuses at
    construction or at run, never reaching the runner."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def body(agent, make_task, qa_factory):
        return _trace(box["seed"], agent)

    runner_calls = _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        box["env"], box["seed"] = env, seed
        agent = _configured_qa_agent()
        for make_env in (
            lambda: prod.ReportingBashEnv(cfg.env),
            lambda: prod.ReportingBashEnv(
                prod.ReportingBashEnvConfig.model_validate(
                    cfg.env.model_dump())),
        ):
            second = None
            try:
                second = make_env()
            except Exception:
                pass  # refusal at construction is a valid outcome
            if second is not None:
                with pytest.raises(Exception):
                    await second.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))
    assert runner_calls == []


def test_env_run_requires_same_config_association(monkeypatch, tmp_path):
    """The admitted Env must run under the exact admitted config: swapping
    `env.config` for a different object after the claim refuses the run —
    equal-valued copies are not authority either."""
    prod = _prod()
    config = _eval_config(tmp_path)
    runner_calls = _patch_configured_runner(monkeypatch, prod, _never_runner)
    errors = []

    async def fake(cfg):
        env = load_environment(cfg.env)
        agent = _configured_qa_agent()
        seed = _seed(env)
        for swapped in (
            env.config.model_copy(
                update={"retries": RetryConfig(max_retries=7)}),
            prod.ReportingBashEnvConfig.model_validate(
                env.config.model_dump()),
        ):
            original = env.config
            env.config = swapped
            try:
                await env.run(seed, _agents_for(cfg, agent))
            except Exception as exc:
                errors.append(exc)
            finally:
                env.config = original
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))
    assert len(errors) == 2
    assert all(isinstance(e, Exception) for e in errors)
    assert runner_calls == []


def test_foreign_env_instance_run_refuses(monkeypatch, tmp_path):
    """An Env constructed OUTSIDE the admission (bare-legal) is not the
    claimed one: its `run` refuses inside the wrapper while the claimed
    env's succeeds."""
    prod = _prod()
    config = _eval_config(tmp_path)
    foreign = prod.ReportingBashEnv(config.env)  # bare constructor: legal
    box = {}
    channels = []

    async def body(agent, make_task, qa_factory):
        channels.append(qa_factory(box["seed"].data))
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)
    refused = []

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        box.update(env=env, seed=seed, agent=agent,
                   trace=_trace(seed, agent))
        try:
            await foreign.run(seed, _agents_for(cfg, agent))
        except Exception as exc:
            refused.append(exc)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))
    assert len(refused) == 1
    assert len(channels) == 1
    assert QA_KEY in box["trace"].info


def test_revoked_admission_after_wrapper_exit(monkeypatch, tmp_path):
    """After the wrapper returns, the claimed Env's `run` refuses — the
    record is revoked, not merely popped."""
    prod = _prod()
    config = _eval_config(tmp_path)
    runner_calls = _patch_configured_runner(monkeypatch, prod, _never_runner)
    captured = {}

    async def fake(cfg):
        captured["env"] = load_environment(cfg.env)
        captured["agent"] = _configured_qa_agent()
        captured["seed"] = _seed(captured["env"])
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    with pytest.raises(Exception):
        _run(captured["env"].run(
            captured["seed"], _agents_for(config, captured["agent"])))
    assert runner_calls == []


def test_nested_wrapper_call_refused_inherited_record(
        monkeypatch, tmp_path):
    """Inside one admitted wrapper, a nested `run_bash_qa_eval` sees the
    inherited admission record and refuses; the outer run completes and
    delegates exactly once."""
    prod = _prod()
    config = _eval_config(tmp_path)
    nested = []
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        try:
            await prod.run_bash_qa_eval(cfg)
        except Exception as exc:
            nested.append(exc)
        return ["outer"]

    _patch_run_eval(monkeypatch, prod, fake)
    result = _run(prod.run_bash_qa_eval(config))
    assert result == ["outer"]
    assert len(nested) == 1
    assert calls == [config]


def test_child_task_inherits_revoked_record(monkeypatch, tmp_path):
    """A child task spawned inside the wrapper inherits the admission
    record: while admitted, its nested wrapper call refuses; after the
    parent exits the record is revoked — inherited, never authority — and
    both `Env.run` and a wrapper call refuse."""
    prod = _prod()
    config = _eval_config(tmp_path)
    runner_calls = _patch_configured_runner(monkeypatch, prod, _never_runner)
    during_release = asyncio.Event()
    attempted = asyncio.Event()
    after_release = asyncio.Event()
    outcomes = {}

    async def probe(env, seed, agent, cfg):
        await asyncio.wait_for(during_release.wait(), INNER_TIMEOUT_S)
        try:
            await prod.run_bash_qa_eval(cfg)
        except Exception as exc:
            outcomes["during_wrap"] = exc
        attempted.set()
        await asyncio.wait_for(after_release.wait(), INNER_TIMEOUT_S)
        try:
            await env.run(seed, _agents_for(cfg, agent))
        except Exception as exc:
            outcomes["after_run"] = exc
        try:
            await prod.run_bash_qa_eval(cfg)
        except Exception as exc:
            outcomes["after_wrap"] = exc

    async def fake(cfg):
        env = load_environment(cfg.env)
        child = asyncio.create_task(
            probe(env, _seed(env), _configured_qa_agent(), cfg))
        during_release.set()
        await asyncio.wait_for(attempted.wait(), INNER_TIMEOUT_S)
        return child

    _patch_run_eval(monkeypatch, prod, fake)

    async def go():
        child = await prod.run_bash_qa_eval(config)
        after_release.set()
        await asyncio.wait_for(child, INNER_TIMEOUT_S)

    _run(go())
    assert isinstance(outcomes.get("during_wrap"), Exception)
    assert isinstance(outcomes.get("after_run"), Exception)
    assert isinstance(outcomes.get("after_wrap"), Exception)
    assert runner_calls == []


def test_sequential_fresh_wrappers_succeed(monkeypatch, tmp_path):
    """Revocation is per-call, not global: normal fresh wrapper calls after
    success, exception and cancellation each admit and delegate again."""
    prod = _prod()
    config = _eval_config(tmp_path)
    calls = []

    async def fake(cfg):
        calls.append(cfg)
        return [cfg]

    _patch_run_eval(monkeypatch, prod, fake)
    for _ in range(2):
        assert _run(prod.run_bash_qa_eval(config)) == [config]
    assert calls == [config, config]

    async def failing(cfg):
        raise _Boom("sdk failed")

    _patch_run_eval(monkeypatch, prod, failing)
    with pytest.raises(_Boom):
        _run(prod.run_bash_qa_eval(config))

    _patch_run_eval(monkeypatch, prod, fake)
    assert _run(prod.run_bash_qa_eval(config)) == [config]

    entered = asyncio.Event()

    async def parked(cfg):
        entered.set()
        await asyncio.Future()

    _patch_run_eval(monkeypatch, prod, parked)

    async def cancel_case():
        running = asyncio.create_task(prod.run_bash_qa_eval(config))
        await asyncio.wait_for(entered.wait(), INNER_TIMEOUT_S)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    _run(cancel_case())

    _patch_run_eval(monkeypatch, prod, fake)
    assert _run(prod.run_bash_qa_eval(config)) == [config]


def test_cancelled_wrapper_revokes_admission(monkeypatch, tmp_path):
    """Cancellation mid-run leaves zero usable admissions: the claimed
    env's `run` refuses afterwards and a fresh wrapper still works."""
    prod = _prod()
    config = _eval_config(tmp_path)
    runner_calls = _patch_configured_runner(monkeypatch, prod, _never_runner)
    captured = {}
    entered = asyncio.Event()

    async def parked(cfg):
        captured["env"] = load_environment(cfg.env)
        captured["seed"] = _seed(captured["env"])
        captured["agent"] = _configured_qa_agent()
        entered.set()
        await asyncio.Future()

    _patch_run_eval(monkeypatch, prod, parked)

    async def go():
        running = asyncio.create_task(prod.run_bash_qa_eval(config))
        await asyncio.wait_for(entered.wait(), INNER_TIMEOUT_S)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    _run(go())

    with pytest.raises(Exception):
        _run(captured["env"].run(
            captured["seed"],
            _agents_for(config, captured["agent"])))
    assert runner_calls == []

    async def fake(cfg):
        return ["fresh"]

    _patch_run_eval(monkeypatch, prod, fake)
    assert _run(prod.run_bash_qa_eval(config)) == ["fresh"]


def test_distinct_top_level_wrappers_overlap(monkeypatch, tmp_path):
    """Two top-level wrapper calls in separate task contexts carry separate
    admission records: barrier-proven overlap admits both."""
    prod = _prod()
    config = _eval_config(tmp_path)
    barrier = asyncio.Barrier(2)
    entered = []

    async def fake(cfg):
        entered.append(cfg)
        await asyncio.wait_for(barrier.wait(), INNER_TIMEOUT_S)
        return [cfg]

    _patch_run_eval(monkeypatch, prod, fake)

    async def go():
        return await asyncio.wait_for(asyncio.gather(
            prod.run_bash_qa_eval(config),
            prod.run_bash_qa_eval(config),
        ), OUTER_TIMEOUT_S)

    first, second = _run(go())
    assert first == [config] and second == [config]
    assert entered == [config, config]


# ---------------------------------------------------------------------------
# Per-run factory/channel + fixed-key attachment (stubbed configured runner).
# ---------------------------------------------------------------------------


def test_env_run_attaches_actual_export_under_fixed_key(
        monkeypatch, tmp_path):
    """One factory call -> one fresh real QaChannel -> the trace gains
    `info["cotrain_bash_qa"] == json.loads(channel.export())`; the runner
    receives a validated wrapper of the seed's own builder; nothing else on the
    trace mutates and no channel is retained on seed or Env."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    channels = []

    async def body(agent, make_task, qa_factory):
        binding = bash_qa.BashQaBinding()
        box.update(binding=binding, paired=make_task(binding))
        channels.append(qa_factory(box["seed"].data))
        return box["trace"]

    runner_calls = _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        trace = _trace(seed, agent)
        trace.ok = True
        trace.is_completed = True
        trace.record_reward("unit_reward", 0.5)
        trace.record_metric("unit_metric", 1.0)
        box.update(env=env, seed=seed, agent=agent, trace=trace)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    trace, channel = box["trace"], channels[0]
    assert trace.info[QA_KEY] == json.loads(channel.export())
    assert len(channels) == 1
    call, = runner_calls
    assert call["agent"] is box["agent"]
    assert box["seed"].builder_calls == [box["binding"]]
    assert type(box["paired"]) is UnitPairedTask
    assert box["paired"].data is box["seed"].data
    assert box["paired"].config is box["seed"].config
    assert box["paired"]._qa_binding is box["binding"]
    # Rewards/metrics untouched: attachment adds the info key only.
    assert trace.reward == 0.5
    assert trace.metrics == {"unit_metric": 1.0}
    assert set(trace.info) == {QA_KEY}
    # No channel retained on seed, Env, or returned calls.
    assert not any(
        isinstance(v, QaChannel) for v in vars(box["env"]).values())
    assert not any(
        isinstance(v, QaChannel) for v in vars(box["seed"]).values())


def test_env_run_without_factory_call_attaches_nothing(
        monkeypatch, tmp_path):
    """A returned FAILED trace whose launch never claimed a channel gets no
    fabricated key: zero factory calls means zero telemetry, not an empty
    channel's export."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def body(agent, make_task, qa_factory):
        return box["trace"]  # factory never invoked

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        trace = _trace(seed, agent)
        trace.record_error(ValueError("rollout failed prelaunch"))
        box.update(env=env, seed=seed, agent=agent, trace=trace)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    assert QA_KEY not in box["trace"].info


def test_env_run_failed_trace_with_factory_still_attaches(
        monkeypatch, tmp_path):
    """Factory called once + a failed trace: the actual export still
    attaches — telemetry records the run, it does not bless it."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    channels = []

    async def body(agent, make_task, qa_factory):
        channels.append(qa_factory(box["seed"].data))
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        trace = _trace(seed, agent)
        trace.record_error(ValueError("rollout failed"))
        box.update(env=env, seed=seed, agent=agent, trace=trace)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    assert box["trace"].ok is False
    assert box["trace"].info[QA_KEY] == json.loads(channels[0].export())


def test_second_factory_invocation_is_loud(monkeypatch, tmp_path):
    """More than one factory call per Env.run is a loud error — the run
    fails rather than attaching a second channel."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def body(agent, make_task, qa_factory):
        qa_factory(box["seed"].data)
        qa_factory(box["seed"].data)
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        box.update(env=env, seed=seed,
                   trace=_trace(seed, _configured_qa_agent()))
        await env.run(seed, _agents_for(cfg, _configured_qa_agent()))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception):
        _run(prod.run_bash_qa_eval(config))


@pytest.mark.parametrize("mode", ["different", "equal", "empty", "none"])
def test_existing_info_key_collision_refuses_never_overwrites(
        monkeypatch, tmp_path, mode):
    """A pre-existing `trace.info["cotrain_bash_qa"]` refuses the attach —
    even when equal to the would-be value — and is never overwritten."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    channels = []

    async def body(agent, make_task, qa_factory):
        channel = qa_factory(box["seed"].data)
        channels.append(channel)
        if mode == "equal":
            box["trace"].info[QA_KEY] = json.loads(channel.export())
        elif mode == "empty":
            box["trace"].info[QA_KEY] = {}
        elif mode == "none":
            box["trace"].info[QA_KEY] = None
        else:
            box["trace"].info[QA_KEY] = {"preexisting": True}
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        box.update(env=env, seed=seed,
                   trace=_trace(seed, _configured_qa_agent()))
        await env.run(seed, _agents_for(cfg, _configured_qa_agent()))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception):
        _run(prod.run_bash_qa_eval(config))
    if mode == "equal":
        assert box["trace"].info[QA_KEY] == json.loads(
            channels[0].export())
    elif mode == "empty":
        assert box["trace"].info[QA_KEY] == {}
    elif mode == "none":
        assert box["trace"].info[QA_KEY] is None
    else:
        assert box["trace"].info[QA_KEY] == {"preexisting": True}


@pytest.mark.parametrize("failure", ["export", "attachment"])
def test_export_failure_propagates_without_attachment(
        monkeypatch, tmp_path, failure):
    """Export/attachment errors propagate, with no fabricated fallback."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    boom = _Boom("export blew up")

    async def body(agent, make_task, qa_factory):
        channel = qa_factory(box["seed"].data)

        def broken():
            raise boom

        if failure == "export":
            channel.export = broken
        else:
            class RefusingInfo(dict):
                def __setitem__(self, key, value):
                    raise boom

            box["trace"].info = RefusingInfo()
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        box.update(env=env, seed=seed,
                   trace=_trace(seed, _configured_qa_agent()))
        await env.run(seed, _agents_for(cfg, _configured_qa_agent()))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception) as excinfo:
        _run(prod.run_bash_qa_eval(config))
    assert excinfo.value is boom
    assert QA_KEY not in box["trace"].info


def test_runner_raising_without_trace_propagates(monkeypatch, tmp_path):
    """A runner that raises without returning a Trace propagates exactly —
    no invented writer, no partial telemetry."""
    prod = _prod()
    config = _eval_config(tmp_path)
    boom = _Boom("runner failed")

    async def body(agent, make_task, qa_factory):
        raise boom

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        await env.run(_seed(env), _agents_for(cfg, _configured_qa_agent()))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception) as excinfo:
        _run(prod.run_bash_qa_eval(config))
    assert excinfo.value is boom


def test_export_bound_uses_existing_collector_limits(
        monkeypatch, tmp_path):
    """The attachment stays inside the collector's own bound: a channel at
    `MAX_REPORTS_PER_ARM` (+1 refused by the real API) still exports within
    `MAX_EXPORT_BYTES` — the source bound, not a fictional wire limit."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    channels = []

    async def body(agent, make_task, qa_factory):
        channel = qa_factory(box["seed"].data)
        for i in range(MAX_REPORTS_PER_ARM):
            channel.submit("bash", kind="other", detail=f"report-{i}")
        with pytest.raises(ReportRejected):
            channel.submit("bash", kind="other", detail="one-too-many")
        assert len(channel.export()) <= MAX_EXPORT_BYTES
        channels.append(channel)
        return box["trace"]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        box.update(env=env, seed=seed,
                   trace=_trace(seed, _configured_qa_agent()))
        await env.run(seed, _agents_for(cfg, _configured_qa_agent()))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    doc = box["trace"].info[QA_KEY]
    assert doc["arms"]["bash"]["reports"] == MAX_REPORTS_PER_ARM
    assert doc == json.loads(channels[0].export())


def test_sequential_env_runs_get_fresh_channels(monkeypatch, tmp_path):
    """Each `Env.run` under one admission builds its own factory: two
    sequential runs produce two distinct channels and two independent
    attachments — re-activation works and nothing routes cross-run."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {"traces": []}
    channels = []

    async def body(agent, make_task, qa_factory):
        channels.append(qa_factory(box["seed"].data))
        return box["traces"][len(channels) - 1]

    _patch_configured_runner(monkeypatch, prod, body)

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        box.update(env=env, seed=seed,
                   traces=[_trace(seed, agent), _trace(seed, agent)])
        await env.run(seed, _agents_for(cfg, agent))
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    first, second = box["traces"]
    assert len(channels) == 2 and channels[0] is not channels[1]
    assert first.info[QA_KEY] == json.loads(channels[0].export())
    assert second.info[QA_KEY] == json.loads(channels[1].export())


# ---------------------------------------------------------------------------
# Seed `build_bash_qa_task` contract through the REAL configured runner.
# ---------------------------------------------------------------------------


class _DifferentDataSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return _DifferentDataPair(
            TaskData(prompt="different"), self.config, qa_binding=binding)


class _DifferentDataPair(bash_qa.BashQaTaskMixin, _DifferentDataSeed):
    pass


class _DifferentConfigSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return _DifferentConfigPair(
            self.data, TaskConfig(), qa_binding=binding)


class _DifferentConfigPair(bash_qa.BashQaTaskMixin, _DifferentConfigSeed):
    pass


class _ForeignTaskSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return _ForeignPaired(self.data, self.config, qa_binding=binding)


class _WrongBindingSeed(UnitSeedTask):
    """The prior review finding: a builder that ignores the supplied binding
    must surface the runner's wrong-binding refusal — never a fresh one."""
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return _WrongBindingPair(
            self.data, self.config, qa_binding=bash_qa.BashQaBinding())


class _WrongBindingPair(bash_qa.BashQaTaskMixin, _WrongBindingSeed):
    pass


class _PlainTaskSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        return _PlainTaskSeed(self.data, self.config)


class _CoroSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)

        async def _body():
            return None

        return _body()


class _AgenSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)

        async def _gen():
            yield binding

        return _gen()


class _AwaitableSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)

        class _Aw:
            def __await__(self):
                return iter(())

        return _Aw()


class _RaisingSeed(UnitSeedTask):
    def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        raise _Boom("builder exploded")


class _AsyncDefSeed(UnitSeedTask):
    async def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)


class _AsyncGenSeed(UnitSeedTask):
    async def build_bash_qa_task(self, binding):
        self.builder_calls.append(binding)
        yield binding


class _AsyncCallable:
    def __init__(self, calls):
        self._calls = calls

    async def __call__(self, binding):
        self._calls.append(binding)


class _AsyncObjectSeed(UnitSeedTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.build_bash_qa_task = _AsyncCallable(self.builder_calls)


class _PartialAsyncFnSeed(UnitSeedTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        async def _fn(binding):
            self.builder_calls.append(binding)

        self.build_bash_qa_task = partial(_fn)


class _PartialAsyncObjSeed(UnitSeedTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.build_bash_qa_task = partial(
            _AsyncCallable(self.builder_calls))


def test_seed_builder_happy_path_real_runner(monkeypatch, tmp_path):
    """Real runner, real Agent: the seed's bound builder is invoked exactly
    once with a fresh `BashQaBinding`; the paired task reaching `agent.run`
    is Task + mixin + `isinstance` of the seed + identical data/config; the
    bound harness during the run is `ReportingBashHarness` paired to that
    binding; the original unbound harness is restored; no factory ran so
    no telemetry key is fabricated."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    reached = []
    harness_seen = []

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        original = agent.harness

        async def drive(task):
            reached.append(task)
            harness_seen.append(agent.harness)
            return _trace(task, agent)

        agent.run = drive
        box.update(env=env, seed=seed, agent=agent, original=original)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    seed, agent, original = box["seed"], box["agent"], box["original"]
    paired, = reached
    binding, = seed.builder_calls
    assert type(binding) is bash_qa.BashQaBinding
    assert type(paired) is UnitPairedTask
    assert isinstance(paired, Task)
    assert isinstance(paired, bash_qa.BashQaTaskMixin)
    assert isinstance(paired, type(seed))
    assert paired.data is seed.data
    assert paired.config is seed.config
    assert paired._qa_binding is binding
    bound, = harness_seen
    assert type(bound) is ReportingBashHarness
    assert bound is not original
    assert bound._qa_binding is binding
    assert getattr(bound.config, "_qa_required", False) is True
    assert agent.harness is original


_REFUSAL_SEEDS = [
    (_DifferentDataSeed, ValueError, "seed's own data and config"),
    (_DifferentConfigSeed, ValueError, "seed's own data and config"),
    (_ForeignTaskSeed, TypeError, "must return a _ForeignTaskSeed"),
    (_WrongBindingSeed, ValueError, "different BashQaBinding"),
    (_PlainTaskSeed, TypeError, "mixing in BashQaTaskMixin"),
    (_CoroSeed, TypeError, "returned a coroutine"),
    (_AgenSeed, TypeError, "Task synchronously"),
    (_AwaitableSeed, TypeError, "Task synchronously"),
    (_RaisingSeed, _Boom, "builder exploded"),
]


@pytest.mark.parametrize(
    "seed_cls,error,reason", _REFUSAL_SEEDS,
    ids=[case[0].__name__ for case in _REFUSAL_SEEDS])
def test_seed_builder_return_shape_refusals(
        monkeypatch, tmp_path, seed_cls, error, reason):
    """Every invalid builder product refuses through the REAL runner —
    different data, different config, unrelated paired task, wrong binding,
    plain Task, native coroutine, async generator, custom awaitable,
    raising builder — with one builder call, zero `agent.run` and the
    original harness restored."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    reached = []

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = seed_cls(TaskData(prompt="go"), env.taskset.config.task)
        agent = _configured_qa_agent()
        original = agent.harness

        async def drive(task):
            reached.append(task)
            return _trace(task, agent)

        agent.run = drive
        box.update(env=env, seed=seed, agent=agent, original=original)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(error, match=reason):
        _run(prod.run_bash_qa_eval(config))
    assert reached == [], "policy ran for a refused task"
    binding, = box["seed"].builder_calls
    assert type(binding) is bash_qa.BashQaBinding
    assert box["agent"].harness is box["original"], (
        "original harness not restored")


def _never_reached(box):
    async def drive(task):
        box.setdefault("reached", []).append(task)
        raise AssertionError("agent.run must not be reached")

    return drive


def test_seed_builder_returning_coroutine_is_closed(
        monkeypatch, tmp_path):
    """The owned native coroutine a bad builder returns is CLOSED before
    refusal: zero `never awaited` RuntimeWarnings survives gc inside the
    catch block — a leak here is a defect, not a nicety."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _CoroSeed(TaskData(prompt="go"), env.taskset.config.task)
        agent = _configured_qa_agent()
        agent.run = _never_reached(box)
        box.update(env=env, seed=seed, agent=agent)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with pytest.raises(Exception):
            _run(prod.run_bash_qa_eval(config))
        gc.collect()
    leaked = [
        w for w in seen
        if issubclass(w.category, RuntimeWarning)
        and "await" in str(w.message).lower()
    ]
    assert leaked == []
    assert len(box["seed"].builder_calls) == 1
    assert box.get("reached") is None


_ASYNC_SEEDS = [
    _AsyncDefSeed,
    _AsyncGenSeed,
    _AsyncObjectSeed,
    _PartialAsyncFnSeed,
    _PartialAsyncObjSeed,
]


@pytest.mark.parametrize(
    "seed_cls", _ASYNC_SEEDS,
    ids=[cls.__name__ for cls in _ASYNC_SEEDS])
def test_async_seed_builder_shapes_refuse_before_invocation(
        monkeypatch, tmp_path, seed_cls):
    """`build_bash_qa_task` itself must be a synchronous callable —
    `_check_sync_callable` rejects async def, async generator, async
    `__call__` objects and partial-wrapped asyncs with ZERO builder
    invocations, zero policy, restored harness."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = seed_cls(TaskData(prompt="go"), env.taskset.config.task)
        agent = _configured_qa_agent()
        original = agent.harness
        agent.run = _never_reached(box)
        box.update(env=env, seed=seed, agent=agent, original=original)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception) as excinfo:
        _run(prod.run_bash_qa_eval(config))
    assert "synchronous" in str(excinfo.value)
    assert box["seed"].builder_calls == []
    assert box.get("reached") is None
    assert box["agent"].harness is box["original"]


def test_task_without_builder_refuses(monkeypatch, tmp_path):
    """A plain Task lacking `build_bash_qa_task` is not a supported seed:
    refusal before builder, factory or policy."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}

    async def fake(cfg):
        env = load_environment(cfg.env)
        task = Task(TaskData(prompt="go"), env.taskset.config.task)
        agent = _configured_qa_agent()
        agent.run = _never_reached(box)
        box.update(agent=agent)
        await env.run(task, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    with pytest.raises(Exception):
        _run(prod.run_bash_qa_eval(config))
    assert box.get("reached") is None


def test_system_prompt_clone_preserves_builder_contract(
        monkeypatch, tmp_path):
    """The taskset's system-prompt copy precedes the explicit builder:
    `task.with_system_prompt` clone still builds a paired task with
    `result.data is clone.data` (the clone's copied TaskData) and the
    runner accepts it — overrides survive evaluation traversal."""
    prod = _prod()
    prompt_file = tmp_path / "system_prompt.txt"
    prompt_file.write_text("CLONED-SYSTEM-PROMPT")
    config = _eval_config(
        tmp_path, taskset_update={"system_prompt": str(prompt_file)})
    box = {}
    reached = []

    async def fake(cfg):
        env = load_environment(cfg.env)
        clone = next(iter(env.taskset))
        assert clone.data.system_prompt == "CLONED-SYSTEM-PROMPT"
        agent = _configured_qa_agent()

        async def drive(task):
            reached.append(task)
            return _trace(task, agent)

        agent.run = drive
        box.update(env=env, clone=clone, agent=agent)
        await env.run(clone, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    clone = box["clone"]
    paired, = reached
    binding, = clone.builder_calls
    assert type(clone) is UnitSeedTask
    assert isinstance(paired, type(clone))
    assert paired.data is clone.data
    assert paired.data.system_prompt == "CLONED-SYSTEM-PROMPT"
    assert paired.config is clone.config
    assert paired._qa_binding is binding


# ---------------------------------------------------------------------------
# Real runner + real channel lifecycle (delegate launch only).
# ---------------------------------------------------------------------------


def test_real_runner_channel_lifecycle_and_cleanup(
        monkeypatch, tmp_path):
    """End of the real unit path: admission -> real `run_configured_bash_qa`
    -> real `run_bash_qa` -> setup/launch/finalize with a real claimed
    channel, one real report rewrite inside the delegate, export attached
    under the fixed key, original harness restored, zero owned routes, PATH
    and wrapper dir cleaned."""
    prod = _prod()
    config = _eval_config(tmp_path)
    box = {}
    host_path = os.environ.get("PATH")

    async def fake(cfg):
        env = load_environment(cfg.env)
        seed = _seed(env)
        agent = _configured_qa_agent()
        original = agent.harness
        runtime = _runtime(tmp_path / "rt")
        state = {}

        async def delegate(self, ctx, trace, runtime, endpoint, secret,
                           mcp_urls, data, tool_interception_url=None):
            route = self._qa_binding._lookup(trace)
            state["channel"] = route.channel
            state["task_data"] = route.task_data
            state["env_path"] = runtime.env.get("PATH")
            result = state["task"]._qa_rewrite(
                _report_request("one"), trace)
            assert result is not None
            return ProgramResult(exit_code=0, stdout="", stderr="")

        monkeypatch.setattr(BashHarness, "launch", delegate)

        async def drive(task):
            state["task"] = task
            trace = _trace(task, agent)
            await task.setup(trace, runtime)
            await agent.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
            await task.finalize(trace, runtime)
            state["trace"] = trace
            return trace

        agent.run = drive
        box.update(env=env, seed=seed, agent=agent, original=original,
                   state=state, runtime=runtime)
        await env.run(seed, _agents_for(cfg, agent))
        return []

    _patch_run_eval(monkeypatch, prod, fake)
    _run(prod.run_bash_qa_eval(config))

    seed, agent, original = box["seed"], box["agent"], box["original"]
    state, runtime, trace = box["state"], box["runtime"], box["state"]["trace"]
    paired = state["task"]

    # Pairing: the task that ran is the explicit paired subclass on the
    # fresh binding, preserving exact data/config identity and hash.
    binding, = seed.builder_calls
    assert type(paired) is UnitPairedTask
    assert paired.data is seed.data
    assert paired.config is seed.config
    assert paired._qa_binding is binding
    assert trace.task.hash == paired.hash == seed.hash

    # Factory: exactly once, on the exact seed TaskData captured at setup.
    channel = state["channel"]
    assert type(channel) is QaChannel
    assert state["task_data"] is seed.data

    # Telemetry: the real report landed on the real channel and exported
    # under the fixed key — allegation telemetry, not a score.
    doc = trace.info[QA_KEY]
    assert doc == json.loads(channel.export())
    assert doc["arms"]["bash"]["reports"] == 1
    event, = doc["arms"]["bash"]["events"]
    assert event["type"] == "report"
    assert event["provenance"] == "agent_output"
    assert event["detail"] == "one"
    assert trace.rewards == {} and trace.metrics == {}

    # Cleanup: unbound harness restored, zero owned routes, channel spent,
    # PATH presence restored, owned wrapper dir removed, host env intact.
    assert agent.harness is original
    assert paired._qa_binding._routes == {}
    with pytest.raises(ValueError):
        channel._claim_launch()
    assert "PATH" not in runtime.env
    assert os.environ.get("PATH") == host_path
    assert list(tmp_path.rglob(REPORT_TOOL)) == []

    # During launch the owned wrapper dir led the runtime PATH.
    first_path_dir = Path(state["env_path"].split(os.pathsep)[0])
    assert first_path_dir.parent == runtime.workdir
    assert first_path_dir.name.startswith(".qa-report-")

    # A fresh run on the same env would re-activate cleanly (revocation is
    # wrapper-scoped, not env-poisoning): covered by sequential wrappers.


# ---------------------------------------------------------------------------
# Ordinary evaluation: no QA plugin, standard env — proven in a child.
# ---------------------------------------------------------------------------


def test_ordinary_eval_resolves_single_agent_env_without_qa_imports():
    """A fresh isolated interpreter (`-I -B`; PYTHONDONTWRITEBYTECODE set but
    ignored under -I, so `-B` carries the no-bytecode guarantee) loading an
    ordinary EvalConfig resolves the standard SingleAgentEnv and imports
    neither QA plugin module."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import json\n"
        "from verifiers.v1.configs.cli.eval import EvalConfig\n"
        "from verifiers.v1.utils.loaders import load_environment\n"
        "from verifiers.v1.envs.single_agent import SingleAgentEnv\n"
        "cfg = EvalConfig.model_validate_json(json.dumps({\n"
        "    'model': 'fixture-model',\n"
        "    'client': {'type': 'train', 'api_key_var': 'UNUSED'},\n"
        "    'env': {'taskset': {'id': 'glossary'}},\n"
        "    'num_tasks': 1, 'num_rollouts': 1, 'max_concurrent': 1,\n"
        "    'push': False, 'rich': None,\n"
        "}))\n"
        "env = load_environment(cfg.env)\n"
        "assert type(env) is SingleAgentEnv, type(env).__name__\n"
        "for name in ('cotrain_bash_qa_env', 'cotrain_bash_qa'):\n"
        "    assert name not in sys.modules, (\n"
        "        f'{name} leaked into an ordinary eval')\n"
        "print('ORDINARY-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "ORDINARY-OK" in proc.stdout
