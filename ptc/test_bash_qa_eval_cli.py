"""Thin CLI tests; unit spies declared separately from the real entrypoint.

Real entrypoint reuses the unchanged framework fixture (actual SDK/Bash child/
loopback tool gate/JSONL). Only asyncio.run gets a delegated 20s outer timeout.
Help gets a separate isolated interpreter, not a polluted parent import oracle.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

import cotrain_bash_qa_env as env_api
import cotrain_bash_qa_eval as cli
from verifiers.v1.configs.cli.eval import EvalConfig
from ptc.test_bash_qa_eval_integration import (
    QA_KEY, _config, _policy, _rows, framework,
)

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)


def _file(monkeypatch, state, **flags):
    config, _ = _config(monkeypatch, state)
    # SDK serialization intentionally omits execution-only resume/clean.
    # Put those flags in the actual input, not an omitted model_copy field.
    payload = json.loads(config.model_dump_json())
    payload.update(flags)
    path = state.root / "explicit-config.json"
    path.write_text(json.dumps(payload))
    return path


def test_help_isolated_without_sdk_imports():
    script = (
        "import runpy, sys\n"
        f"sys.path.insert(0, {str(Path(cli.__file__).parent)!r})\n"
        "sys.argv = ['cotrain-bash-qa-eval', '--help']\n"
        "try:\n"
        "    runpy.run_module('cotrain_bash_qa_eval', run_name='__main__')\n"
        "except SystemExit as exc:\n"
        "    assert exc.code == 0\n"
        "else:\n"
        "    raise AssertionError('help must exit before evaluation')\n"
        "assert 'verifiers' not in sys.modules\n"
        "assert 'cotrain_bash_qa_env' not in sys.modules\n"
        "assert 'cotrain_bash_qa' not in sys.modules\n"
        "print('HELP-ONLY-OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True, text=True, timeout=20,
        cwd=Path(cli.__file__).parent,
    )
    assert result.returncode == 0, result.stderr
    assert "--config" in result.stdout and "HELP-ONLY-OK" in result.stdout


def test_missing_argument_refuses_before_wrapper(monkeypatch):
    calls = []
    monkeypatch.setattr(env_api, "run_bash_qa_eval", calls.append)
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2 and calls == []


def test_missing_file_refuses_before_wrapper(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(env_api, "run_bash_qa_eval", calls.append)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(tmp_path / "absent.json")])
    assert exc.value.code == 2 and calls == []
    assert "cannot read config file" in capsys.readouterr().err


@pytest.mark.parametrize("payload", ['{"private-sentinel":', '["private-sentinel"]'])
def test_invalid_config_does_not_dump_input(monkeypatch, tmp_path, capsys, payload):
    path = tmp_path / "invalid.json"
    path.write_text(payload)
    calls = []
    monkeypatch.setattr(env_api, "run_bash_qa_eval", calls.append)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(path)])
    assert exc.value.code == 2 and calls == []
    error = capsys.readouterr().err
    assert "invalid EvalConfig JSON" in error
    assert "private-sentinel" not in error


def test_valid_config_delegates_exact_validated_object_once(monkeypatch, framework):
    path = _file(monkeypatch, framework)
    validate = EvalConfig.model_validate_json
    validated, calls = [], []

    def observe(cls, payload):
        result = validate(payload)
        validated.append(result)
        return result

    async def record(config):
        calls.append(config)
        return []

    monkeypatch.setattr(EvalConfig, "model_validate_json", classmethod(observe))
    monkeypatch.setattr(env_api, "run_bash_qa_eval", record)
    assert cli.main(["--config", str(path)]) is None
    assert len(validated) == len(calls) == 1
    assert calls[0] is validated[0]
    assert json.loads(calls[0].model_dump_json()) == json.loads(path.read_text())


def test_execution_error_is_not_argparse_error(monkeypatch, framework):
    path = _file(monkeypatch, framework)
    boom = ValueError("execution error sentinel")

    async def fail(config):
        raise boom

    monkeypatch.setattr(env_api, "run_bash_qa_eval", fail)
    with pytest.raises(ValueError) as exc:
        cli.main(["--config", str(path)])
    assert exc.value is boom


@pytest.mark.parametrize("flag", ["push", "resume", "clean"])
def test_real_wrapper_preflight_still_precedes_sdk(monkeypatch, framework, flag):
    path = _file(monkeypatch, framework, **{flag: True})
    calls = []

    async def sdk(config):
        calls.append(config)
        return []

    monkeypatch.setattr(env_api, "run_eval", sdk)
    with pytest.raises(ValueError, match=flag):
        cli.main(["--config", str(path)])
    assert calls == []
    assert not Path(framework.config.output_dir).exists()


def test_real_cli_entrypoint_persists_sdk_qa(monkeypatch, framework):
    path = _file(monkeypatch, framework)
    framework.policy = policy = _policy("cli-report", ordinary_action=True)
    original_run = asyncio.run

    def bounded_run(coro, **kwargs):
        return original_run(asyncio.wait_for(coro, 20.0), **kwargs)

    monkeypatch.setattr(asyncio, "run", bounded_run)
    monkeypatch.setattr(sys, "argv", ["cotrain-bash-qa-eval", "--config", str(path)])
    namespace = runpy.run_module("cotrain_bash_qa_eval", run_name="__main__")
    assert namespace["__name__"] == "__main__"
    assert len(framework.channels) == 1, "CLI evaluation delegation missing"
    assert policy.calls == 3 and policy.receipt_at == [2]
    row, = _rows(framework.config)
    assert row["ok"] and len(row["traces"]) == 1
    doc = row["traces"][0]["info"][QA_KEY]
    assert doc["arms"]["bash"]["reports"] == 1
    assert doc["arms"]["bash"]["events"][0]["detail"] == "cli-report"
    assert doc == json.loads(framework.channels[0].export())
