"""Public BIRD projection, fixture SDK settings seal and whole-arm EX decoder.

No evaluator, driver factory, CLI, runtime selection or production authorization.
Seals detect accidental trusted-host drift, not malicious Python or filesystem races.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from verifiers.v1.configs.agent import AgentConfig, TimeoutConfig as AgentTimeout
from verifiers.v1.configs.cli.eval import EvalConfig, RunConfig
from verifiers.v1.configs.client import TrainClientConfig
from verifiers.v1.configs.env import EnvConfig, TimeoutConfig as EnvTimeout, _declared_agent_configs, default_agent_harness
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.configs.task import TaskConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.episode import Episode
from verifiers.v1.interception.server import InterceptionServerConfig
from verifiers.v1.interception.tunnel.prime import PrimeTunnelConfig
from verifiers.v1.runtimes.subprocess import SubprocessConfig
from verifiers.v1.task import TaskData, TaskResources, TaskTimeout, task_key
from verifiers.v1.trace import Reward, Trace
from verifiers.v1.types import SamplingConfig
from verifiers.v1.utils.generic import deep_merge
from verifiers.v1.utils.loaders import env_config_type, harness_config_type, taskset_config_type

from bench.paired_bird import ArmRequest, Instrument, Metric, TaskOutcome
from bench.score import ExResult
from bench.task import SqlTask
from ptc.sql_arms import adapt_task, prompt_for
from ptc.harness import PTCHarnessConfig

_PLUGIN = "cotrain_fixture_bird_sql"


class BirdSdkBridgeError(ValueError):
    """A refused fixture projection, configuration or incomplete/invalid arm."""


@dataclass(frozen=True)
class PublicSqlProjection:
    task_ids: tuple[str, ...]
    bash: tuple[TaskData, ...]
    ptc: tuple[TaskData, ...]
    sha256: str


@dataclass(frozen=True)
class SdkArmExpectation:
    config: EvalConfig
    effective_agent: AgentConfig
    request_model: str
    request_sampling: SamplingConfig


@dataclass(frozen=True)
class SqlScoreReceipt:
    trace: Trace
    result: ExResult


def _require(condition, message):
    if not condition:
        raise BirdSdkBridgeError(message)


_SDK_MODELS = frozenset((EvalConfig, RunConfig, AgentConfig, AgentTimeout,
    EnvTimeout, RetryConfig, TasksetConfig, TaskConfig, TrainClientConfig,
    SubprocessConfig, InterceptionServerConfig, PrimeTunnelConfig,
    SamplingConfig, TaskData, TaskTimeout, TaskResources))


def _plain_fixture_model(cls):
    """Only declarative direct fixture extensions, not arbitrary plugin hooks.

    Exact SDK identities anchor the contract. Neither names/module prefixes nor
    copying a model authorize custom behavior. Pydantic-generated class machinery
    is allowed; user-defined methods, resource hooks and serializer metadata aren't.
    """
    if cls.__bases__ == (EnvConfig,):
        base, fields = EnvConfig, {"agent": AgentConfig}
    elif cls.__bases__ == (PTCHarnessConfig,):
        base, fields = PTCHarnessConfig, {
            "id": str, "arm": str, "action_max_rows": int, "query_timeout_s": float,
            "instrument_identity": str, "sampling_identity": str, "policy_identity": str}
    else:
        return False
    generated = {
        "__module__", "__annotations__", "model_config", "__class_vars__",
        "__private_attributes__", "__doc__", "__abstractmethods__", "_abc_impl",
        "__pydantic_custom_init__", "__pydantic_setattr_handlers__",
        "__pydantic_decorators__", "__pydantic_generic_metadata__",
        "__pydantic_complete__", "__pydantic_parent_namespace__",
        "__pydantic_fields__", "__pydantic_extra_info__", "__pydantic_post_init__",
        "__pydantic_computed_fields__", "__pydantic_core_schema__",
        "__pydantic_validator__", "__pydantic_serializer__", "__signature__"}
    if (set(vars(cls)) - generated or set(cls.__annotations__) != set(fields)
            or cls.model_config != base.model_config
            or cls.__pydantic_custom_init__ or cls.__pydantic_post_init__ is not None):
        return False
    for kind in ("validators", "field_validators", "root_validators",
                 "field_serializers", "model_serializers", "model_validators", "computed_fields"):
        actual = getattr(cls.__pydantic_decorators__, kind)
        original = getattr(base.__pydantic_decorators__, kind)
        if set(actual) != set(original) or any(
                getattr(actual[k].func, "__func__", actual[k].func)
                is not getattr(original[k].func, "__func__", original[k].func) for k in actual):
            return False
    for name, annotation in fields.items():
        field = cls.model_fields[name]
        if (field.annotation is not annotation or field.metadata
                or field.default_factory is not None or field.json_schema_extra is not None
                # FieldInfo carries serializer controls outside metadata and
                # decorator registries. Even a closure with unchanged fields can
                # change the generated serializer; only inert declarations fit.
                or any(getattr(field, attr) is not None for attr in (
                    "exclude_if", "exclude", "alias", "validation_alias",
                    "serialization_alias", "alias_priority", "discriminator",
                    "field_title_generator"))):
            return False
    return True


def _check_model(value):
    cls = type(value)
    _require(cls in _SDK_MODELS or _plain_fixture_model(cls), "unsupported model class")
    decorators = cls.__pydantic_decorators__
    _require(not decorators.model_serializers and not decorators.field_serializers
             and not cls.model_computed_fields, "unsupported model serializer")
    _require(not (set(vars(value)) - set(cls.model_fields)), "undeclared model state")
    private = value.__pydantic_private__ or {}
    declared = cls.__private_attributes__
    if cls is RunConfig:
        # SDK-assigned provenance, deliberately mutable and NOT a config setting.
        _require(set(private) <= {"_id"} and set(declared) == {"_id"}
                 and type(private.get("_id")) in (str, type(None)), "unsupported run private state")
    else:
        _require(not private and not declared, "unsupported model private state")
    _require(cls is SamplingConfig or not value.model_extra, "unsupported model extra state")


def _snapshot(value):
    """Full materialized fields, not model_dump (which drops excluded fields).

    Concrete classes, extras and recursively nested sampling field-set semantics
    survive. Private SDK run._id is lifecycle bookkeeping, not a config field.
    """
    cls = type(value)
    if isinstance(value, BaseModel):
        _check_model(value)
        return (cls, tuple((k, _snapshot(getattr(value, k))) for k in cls.model_fields),
                _snapshot(value.model_extra),
                tuple(sorted(value.model_fields_set)) if isinstance(value, SamplingConfig) else None)
    if dataclasses.is_dataclass(value):
        return (cls, tuple((f.name, _snapshot(getattr(value, f.name)))
                           for f in dataclasses.fields(value)))
    if isinstance(value, Path):
        return (cls, str(value))
    if cls in (tuple, list):
        return (cls, tuple(_snapshot(v) for v in value))
    if cls is dict:
        _require(all(type(k) is str for k in value), "non-string config key")
        return (cls, tuple(sorted((k, _snapshot(v)) for k, v in value.items())))
    if cls in (set, frozenset):
        return (cls, frozenset(_snapshot(v) for v in value))
    _require(cls in (str, bool, int, float, type(None)), "unsupported config value")
    if cls is float:
        _require(math.isfinite(value), "nonfinite config")
    return (cls, value)


def _projection_hash(task_ids, bash, ptc):
    doc = {"task_ids": task_ids,
           "bash": [d.model_dump(mode="json") for d in bash],
           "ptc": [d.model_dump(mode="json") for d in ptc]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _check_projection(projection):
    _require(type(projection) is PublicSqlProjection, "projection type")
    p = projection
    _require(type(p.task_ids) is tuple and p.task_ids
             and all(type(k) is str and k for k in p.task_ids)
             and len(set(p.task_ids)) == len(p.task_ids), "projection membership")
    for rows in (p.bash, p.ptc):
        _require(type(rows) is tuple and len(rows) == len(p.task_ids), "projection coverage")
        for key, data in zip(p.task_ids, rows, strict=True):
            _require(type(data) is TaskData and data.name == key
                     and type(data.prompt) is str and data.prompt, "base public task")
            inert = TaskData(name=key, prompt=data.prompt)
            _require(_snapshot(data) == _snapshot(inert), "noninert public task fields")
    _require(p.sha256 == _projection_hash(p.task_ids, p.bash, p.ptc), "projection seal drift")


def project_sql_tasks(tasks: tuple[SqlTask, ...], *, schemas: tuple[str, ...],
                      action_max_rows: int) -> PublicSqlProjection:
    _require(type(tasks) is tuple and tasks and all(type(t) is SqlTask for t in tasks),
             "private task tuple")
    _require(type(schemas) is tuple and len(schemas) == len(tasks)
             and all(type(s) is str for s in schemas), "one schema per task")
    _require(type(action_max_rows) is int and action_max_rows > 0, "action max rows")
    ids = tuple(t.name for t in tasks)

    def render(arm):
        return tuple(TaskData(name=t.name, prompt=prompt_for(
            adapt_task(t), arm, schema=schema, max_rows=action_max_rows, reporting=False))
            for t, schema in zip(tasks, schemas, strict=True))

    bash, ptc = render("bash"), render("ptc")
    result = PublicSqlProjection(ids, bash, ptc, _projection_hash(ids, bash, ptc))
    _check_projection(result)
    return result


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _no_symlink(path):
    _require(path.is_absolute(), "explicit absolute output path")
    _require(not any(p.is_symlink() for p in (path, *path.parents)),
             "symlink output traversal")


def _destination(config, root, *, fresh):
    _require(isinstance(root, Path), "explicit test-owned output root")
    _no_symlink(root)
    _require(root.is_dir() and root.stat().st_uid == os.getuid(), "test-owned output root")
    root = root.resolve(strict=True)
    directory = config.run.dir
    _require(type(directory) is str and directory and not Path(directory).is_absolute()
             and ".." not in Path(directory).parts and str(Path(directory)) == directory,
             "explicit nonescaping run.dir")
    output = config.output_dir
    _require(isinstance(output, Path) and output.is_absolute(), "explicit output_dir")
    _no_symlink(output)
    target = output / directory
    _no_symlink(target)
    target = target.resolve()
    _require(root in target.parents, "destination outside output root")
    if fresh:
        _require(not target.exists(), "output destination already exists")
    return target


def _effective(config):
    roles = _declared_agent_configs(config.env)
    _require(len(roles) == 1, "exactly one agent role")
    role_name, spec = next(iter(roles.items()))
    sampling = config.sampling
    if spec.sampling is not None:
        sampling = sampling.model_copy(update=deep_merge(
            sampling.model_dump(exclude_unset=True),
            spec.sampling.model_dump(exclude_unset=True)))
    resolved = spec.model_copy(update={
        "harness": spec.harness if spec.harness is not None
        else default_agent_harness(config.env.taskset.id),
        "model": spec.model if spec.model is not None else config.model,
        "client": spec.client if spec.client is not None else config.client,
        "sampling": sampling})
    return role_name, resolved


def _validate_config(config, expected, instrument):
    _require(type(config) is EvalConfig and type(expected) is SdkArmExpectation
             and type(instrument) is Instrument, "config/expectation/instrument type")
    _require(_snapshot(config) == _snapshot(expected.config), "complete config drift")
    _require(all(getattr(config, k) is False for k in
                 ("push", "resume", "clean", "dry_run", "shuffle"))
             and config.run.attach is None and config.num_tasks is None
             and type(config.num_rollouts) is int and config.num_rollouts == 1,
             "offline one-rollout config required")
    _require(type(config.max_concurrent) is int and 0 < config.max_concurrent <= 2
             and type(config.env.max_concurrent_agents) is int
             and 0 < config.env.max_concurrent_agents <= 2, "finite fixture concurrency")
    env = config.env
    _require(env.id == env.taskset.id == _PLUGIN, "named fixture plugins required")
    _require(type(env) is env_config_type(env.taskset.id, env.id)
             and type(env.taskset) is taskset_config_type(env.taskset.id),
             "original fixture config classes required")
    _require(env.taskset.system_prompt is None, "system prompt override")
    task = env.taskset.task
    _require(not task.judges and not task.rewards and not task.stops and not task.metrics,
             "task scoring/reporting override")
    role, effective = _effective(config)
    _require(type(effective) is AgentConfig
             and type(effective.runtime) is SubprocessConfig
             and type(config.client) is TrainClientConfig
             and type(effective.client) is TrainClientConfig,
             "fixture-only runtime/client config classes required")
    _require(_snapshot(effective) == _snapshot(expected.effective_agent),
             "effective agent drift")
    _require(effective.model == expected.request_model
             and effective.sampling.wire_args() == expected.request_sampling.wire_args(),
             "effective request settings drift")
    for retries in (effective.retries, env.retries):
        _require(type(retries.max_retries) is int and retries.max_retries == 0
                 and not retries.include and not retries.exclude, "zero SDK retries")
    for timeout in (effective.timeout.setup, effective.timeout.rollout,
                    effective.timeout.finalize, effective.timeout.scoring,
                    env.timeout.episode, env.timeout.finalize):
        _require(_positive(timeout), "finite positive lifecycle bounds")
    budget = instrument.budget
    _require(type(budget.max_turns) is int and budget.max_turns > 0
             and type(budget.max_retries) is int and budget.max_retries == 0
             and budget.retry_on == () and _positive(budget.rollout_timeout)
             and _positive(budget.program_timeout), "bounded instrument")
    _require(type(instrument.action_max_rows) is int and instrument.action_max_rows > 0
             and _positive(instrument.query_timeout_s)
             and type(instrument.identity) is str and instrument.identity
             and type(instrument.sampling_identity) is str and instrument.sampling_identity,
             "instrument declarations")
    harness = effective.harness
    _require(harness is not None and harness.id == _PLUGIN, "fixture harness required")
    _require(type(harness) is harness_config_type(_PLUGIN), "original fixture harness config")
    _require(not harness.skills and not harness.env and not harness.forward_env
             and not harness.mcp_header_env and not harness.disabled_tools,
             "harness skills/reporting/environment override")
    _require(harness.max_turns == effective.max_turns == budget.max_turns
             and effective.timeout.rollout == budget.rollout_timeout
             and harness.program_timeout == budget.program_timeout
             and harness.action_max_rows == instrument.action_max_rows
             and harness.query_timeout_s == instrument.query_timeout_s
             and harness.instrument_identity == instrument.identity
             and harness.sampling_identity == instrument.sampling_identity
             and harness.arm in ("bash", "ptc")
             and type(harness.policy_identity) is str and harness.policy_identity,
             "instrument mapping drift")
    _require(_positive(harness.tool_timeout), "fixture tool timeout")
    return role


@dataclass(frozen=True, init=False)
class SdkConfigSeal:
    """Module-constructed snapshots. No execution or authorization authority."""
    _config: EvalConfig
    _expected: SdkArmExpectation
    _instrument: Instrument
    _snapshot: tuple
    _root: Path
    run_dir: Path
    _role: str

    def __init__(self):
        raise BirdSdkBridgeError("use admit_sdk_config")

    def _check(self, *, fresh):
        _require(type(self) is SdkConfigSeal, "settings seal type")
        _require(self._snapshot == _snapshot(
            (self._config, self._expected, self._instrument)), "settings seal drift")
        _validate_config(self._config, self._expected, self._instrument)
        _require(_destination(self._config, self._root, fresh=fresh) == self.run_dir,
                 "sealed output destination drift")


def admit_sdk_config(config: EvalConfig, *, expected: SdkArmExpectation,
                     instrument: Instrument, output_root: Path) -> SdkConfigSeal:
    role = _validate_config(config, expected, instrument)
    destination = _destination(config, output_root, fresh=True)
    seal = object.__new__(SdkConfigSeal)
    for key, value in dict(_config=config, _expected=expected, _instrument=instrument,
            _snapshot=_snapshot((config, expected, instrument)), _root=output_root,
            run_dir=destination, _role=role).items():
        object.__setattr__(seal, key, value)
    return seal


def _binary(score):
    return type(score) in (int, float) and math.isfinite(score) and score in (0, 1)


def decode_sdk_episodes(episodes: tuple[Episode, ...], *, request: ArmRequest,
                        projection: PublicSqlProjection, scores: tuple[SqlScoreReceipt, ...],
                        settings: SdkConfigSeal, task_type: str,
                        run_dir: Path) -> tuple[TaskOutcome, ...]:
    _require(type(settings) is SdkConfigSeal, "settings seal required")
    settings._check(fresh=False)
    _require(isinstance(run_dir, Path), "decoder output path")
    _no_symlink(run_dir)
    _require(run_dir.resolve() == settings.run_dir, "decoder destination mismatch")
    _require(type(request) is ArmRequest and request.arm in ("bash", "ptc")
             and type(request.num_rollouts) is int and request.num_rollouts == 1
             and _snapshot(request.instrument) == _snapshot(settings._instrument),
             "request settings mismatch")
    harness = settings._expected.effective_agent.harness
    _require(harness.arm == request.arm and harness.policy_identity == request.policy_identity,
             "request policy/arm mismatch")
    _check_projection(projection)
    _require(projection.task_ids == tuple(t.name for t in request.tasks),
             "eligible projection membership")
    _require(type(task_type) is str and task_type, "task type required")
    _require(type(episodes) is tuple and len(episodes) == len(projection.task_ids),
             "episode coverage")
    _require(type(scores) is tuple and len(scores) == len(episodes), "EX receipt coverage")
    receipts = {}
    for receipt in scores:
        _require(type(receipt) is SqlScoreReceipt and type(receipt.trace) is Trace,
                 "original trace receipt required")
        key = id(receipt.trace)
        _require(key not in receipts, "duplicate trace receipt")
        receipts[key] = receipt
    public = dict(zip(projection.task_ids, getattr(projection, request.arm), strict=True))
    seen_episodes, seen_traces, results = set(), set(), {}
    for episode in episodes:
        _require(type(episode) is Episode and type(episode.id) is str and episode.id
                 and episode.id not in seen_episodes, "original unique episode required")
        seen_episodes.add(episode.id)
        _require(episode.ok is True and episode.errors == [] and len(episode.traces) == 1,
                 "SDK episode failed/incomplete")
        trace = episode.traces[0]
        _require(type(trace) is Trace and type(trace.id) is str and trace.id
                 and trace.id not in seen_traces, "original unique trace required")
        seen_traces.add(trace.id)
        _require(trace.ok is True and trace.is_completed is True and trace.errors == [],
                 "SDK trace failed/incomplete")
        _require(trace.agent.name == settings._role
                 and _snapshot(trace.agent.config) == _snapshot(settings._expected.effective_agent),
                 "actual effective agent drift")
        name = episode.task.data.name
        _require(name in public and name not in results, "foreign/duplicate public task")
        data = public[name]
        digest = task_key(data.model_dump(mode="json", exclude_none=True))
        for task in (episode.task, trace.task):
            _require(task.type == task_type and type(task.data) is TaskData
                     and _snapshot(task.data) == _snapshot(data)
                     and task.hash == task.key == digest, "public task/hash/key drift")
        _require(type(trace.rewards) is dict
                 and set(trace.rewards) == {"execution_accuracy"}, "exactly one EX reward")
        reward = trace.rewards["execution_accuracy"]
        _require(type(reward) is Reward and _binary(reward.score)
                 and type(reward.weight) in (int, float) and reward.weight == 1.0,
                 "invalid EX reward")
        receipt = receipts.pop(id(trace), None)
        _require(receipt is not None and receipt.trace is trace, "missing original EX receipt")
        ex = receipt.result
        _require(type(ex) is ExResult and ex.valid is True and _binary(ex.score)
                 and ex.status in ("match", "mismatch", "pred_empty", "pred_error",
                                   "pred_timeout", "pred_truncated")
                 and (ex.status == "match") == (ex.score == 1)
                 and reward.score == ex.score, "invalid/mismatched actual EX")
        results[name] = TaskOutcome(request.plan_id, request.arm, name, True, True, ex.status,
            (Metric("execution_accuracy", float(reward.score)),),
            f"{settings.run_dir / 'traces.jsonl'}#episode={episode.id}")
    _require(set(results) == set(projection.task_ids) and not receipts, "whole-arm membership")
    return tuple(results[name] for name in projection.task_ids)
