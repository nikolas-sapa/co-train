"""Real JSON admission; wrapper fault/infrastructure seams never launch SDK eval."""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from verifiers.v1.configs.cli.eval import EvalConfig

import cotrain_bash_qa_env as env_api
import cotrain_bash_qa_eval as cli


_TASKSET_SOURCE = '''
from typing import Literal
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.task import Task
from verifiers.v1.taskset import Taskset

__all__ = ["AdmissionTaskset"]

class Config(TasksetConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"

class AdmissionTaskset(Taskset[Task, Config]):
    def load(self):
        raise AssertionError("CLI admission must not execute a taskset")
'''


@pytest.fixture
def config_payload(monkeypatch, tmp_path):
    name = "bash_cli_admission_taskset_" + uuid.uuid4().hex
    (tmp_path / f"{name}.py").write_text(
        _TASKSET_SOURCE.replace("__PLUGIN__", name))
    monkeypatch.syspath_prepend(str(tmp_path))
    return {
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "UNUSED_FIXTURE_KEY"},
        "env": {
            "id": "cotrain_bash_qa_env", "taskset": {"id": name},
            "interception": {"type": "server"},
            "agent": {
                "harness": {"id": "cotrain_bash_qa", "edit": False, "search": False},
                "runtime": {"type": "subprocess"}, "max_turns": 4,
                "timeout": {"rollout": 15.0, "finalize": 5.0, "scoring": 5.0},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "rich": None, "output_dir": str(tmp_path / "output"),
        "run": {"dir": "run"},
    }


def _config_file(tmp_path, payload):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    return path


@pytest.mark.parametrize("kind", ["env", "taskset", "harness"])
def test_unknown_plugin_exit2_zero_delegations_no_leak(
        monkeypatch, tmp_path, capsys, config_payload, kind):
    sentinel = "bash_cli_private_sentinel_" + kind
    target = {
        "env": config_payload["env"],
        "taskset": config_payload["env"]["taskset"],
        "harness": config_payload["env"]["agent"]["harness"],
    }[kind]
    target["id"] = sentinel
    path = _config_file(tmp_path, config_payload)
    calls = []

    # Infrastructure boundary: record even an unawaited wrapper invocation.
    def forbidden(config):
        calls.append(config)
        raise AssertionError("invalid config reached evaluation wrapper")

    monkeypatch.setattr(env_api, "run_bash_qa_eval", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(path)])
    assert exc.value.code == 2
    assert calls == []
    output = capsys.readouterr()
    assert "invalid EvalConfig JSON" in output.err
    assert sentinel not in output.out + output.err
    assert "Traceback" not in output.out + output.err


@pytest.mark.parametrize("error", [
    ModuleNotFoundError("runtime module sentinel"),
    RuntimeError("runtime sentinel"),
    asyncio.CancelledError(),
])
def test_delegated_exception_identity(
        monkeypatch, tmp_path, capsys, config_payload, error):
    path = _config_file(tmp_path, config_payload)
    calls = []

    # Fault boundary: raise only after actual async delegation.
    async def fail(config):
        calls.append(config)
        raise error

    monkeypatch.setattr(env_api, "run_bash_qa_eval", fail)
    with pytest.raises(type(error)) as exc:
        cli.main(["--config", str(path)])
    assert exc.value is error
    assert len(calls) == 1
    assert type(calls[0]) is EvalConfig
    output = capsys.readouterr()
    assert output.out == output.err == ""


def _observe_admission(monkeypatch, path):
    validate = EvalConfig.model_validate_json
    validated, calls, snapshots = [], [], []

    def observe(cls, payload):
        result = validate(payload)
        validated.append(result)
        snapshots.append(result.model_dump_json())
        return result

    # Infrastructure boundary: no SDK evaluator, Agent or provider launch.
    async def record(config):
        calls.append(config)
        return []

    monkeypatch.setattr(EvalConfig, "model_validate_json", classmethod(observe))
    monkeypatch.setattr(env_api, "run_bash_qa_eval", record)
    assert cli.main(["--config", str(path)]) is None
    return validated, calls, snapshots


def _assert_admission(validated, calls):
    assert len(validated) == 1, "CLI config validation must run exactly once"
    assert len(calls) == 1, "CLI evaluation delegation missing"
    assert calls[0] is validated[0]


def test_real_json_admission_exact_object_once(monkeypatch, tmp_path, config_payload):
    path = _config_file(tmp_path, config_payload)
    validated, calls, snapshots = _observe_admission(monkeypatch, path)
    _assert_admission(validated, calls)
    assert type(validated[0]) is EvalConfig
    assert type(validated[0].env) is env_api.ReportingBashEnvConfig
    assert validated[0].env.taskset.id == config_payload["env"]["taskset"]["id"]
    assert calls[0].model_dump_json() == snapshots[0]


def test_delegation_loss_canary_fails_call_phase(
        monkeypatch, tmp_path, config_payload):
    path = _config_file(tmp_path, config_payload)

    # Fault boundary: suppress execution, closing the owned coroutine.
    def suppress(coro):
        coro.close()

    monkeypatch.setattr(asyncio, "run", suppress)
    validated, calls, _ = _observe_admission(monkeypatch, path)
    assert len(validated) == 1
    assert calls == []
    with pytest.raises(AssertionError) as exc:
        _assert_admission(validated, calls)
    assert str(exc.value).partition("\n")[0] == "CLI evaluation delegation missing"
