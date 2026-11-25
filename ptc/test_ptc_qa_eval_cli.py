"""Stdlib-first project JSON CLI. No stock CLI claim."""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
from verifiers.v1.configs.cli.eval import EvalConfig
from ptc.test_ptc_qa_eval import _config


def _cli():
    return importlib.import_module("cotrain_ptc_qa_eval")


def test_A_CLI_help_isolated_0_product_imports():
    root = Path(__file__).resolve().parents[1]
    script = (
        "import runpy,sys\n"
        f"sys.path.insert(0,{str(root)!r})\n"
        "sys.argv=['cotrain-ptc-qa-eval','--help']\n"
        "try: runpy.run_module('cotrain_ptc_qa_eval',run_name='__main__')\n"
        "except SystemExit as e: assert e.code == 0\n"
        "else: raise AssertionError('help did not exit')\n"
        "assert 'verifiers' not in sys.modules\n"
        "assert 'cotrain_ptc_qa' not in sys.modules\n"
        "assert 'cotrain_ptc_qa_env' not in sys.modules\n"
        "print('HELP-ONLY-OK')\n"
    )
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                            capture_output=True, text=True, timeout=20, cwd=root)
    assert result.returncode == 0, result.stderr
    assert "HELP-ONLY-OK" in result.stdout


@pytest.mark.parametrize("case", ["missing_argument", "missing_file", "json", "schema"])
def test_A_CLI_malformed_2_zero_calls_no_sentinel(monkeypatch, tmp_path, capsys, case):
    cli = _cli()
    api = importlib.import_module("cotrain_ptc_qa_env")
    calls = []
    monkeypatch.setattr(api, "run_ptc_qa_eval", calls.append)
    path = tmp_path / "bad.json"
    if case in ("json", "schema"):
        path.write_text('{"private-sentinel":' if case == "json"
                        else '["private-sentinel"]')
    argv = [] if case == "missing_argument" else ["--config", str(path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2 and calls == []
    assert "private-sentinel" not in capsys.readouterr().err


def test_A_CLI_exact_object_once_and_runtime_error_unchanged(monkeypatch, tmp_path):
    cli = _cli()
    api = importlib.import_module("cotrain_ptc_qa_env")
    path = tmp_path / "valid.json"
    path.write_text(_config(tmp_path).model_dump_json())
    validate = EvalConfig.model_validate_json
    objects, calls = [], []
    def observed(cls, payload):
        result = validate(payload)
        objects.append(result)
        return result
    async def delegate(config):
        calls.append(config)
        return []
    monkeypatch.setattr(EvalConfig, "model_validate_json", classmethod(observed))
    monkeypatch.setattr(api, "run_ptc_qa_eval", delegate)
    cli.main(["--config", str(path)])
    assert len(objects) == len(calls) == 1 and objects[0] is calls[0]
    boom = RuntimeError("runtime")
    async def fail(config):
        raise boom
    monkeypatch.setattr(api, "run_ptc_qa_eval", fail)
    with pytest.raises(RuntimeError) as exc:
        cli.main(["--config", str(path)])
    assert exc.value is boom


def test_A_CLI_real_original_writer(monkeypatch, framework):
    from ptc.test_ptc_qa_eval_integration import _config as real_config, _policy, _rows
    state = framework
    config, _ = real_config(monkeypatch, state)
    path = state.root / "config.json"
    path.write_text(config.model_dump_json())
    state.policy = policy = _policy("cli")
    original = asyncio.run
    monkeypatch.setattr(asyncio, "run", lambda coro: original(asyncio.wait_for(coro, 20)))
    _cli().main(["--config", str(path)])
    row, = _rows(config)
    assert row["ok"] and len(state.channels) == 1 and policy.receipt_at == [2]
    assert row["traces"][0]["info"]["cotrain_ptc_qa"] == json.loads(state.channels[0].export())


from ptc.test_bash_qa_eval_integration import framework  # noqa: E402,F401


@pytest.mark.parametrize("kind", ["env", "taskset", "harness"])
def test_followup01_CLI_unknown_plugin_exit2_no_leak(
        monkeypatch, tmp_path, capsys, kind):
    cli = _cli()
    api = importlib.import_module("cotrain_ptc_qa_env")
    payload = json.loads(_config(tmp_path).model_dump_json())
    sentinel = "followup01_private_sentinel_" + kind
    target = {
        "env": payload["env"],
        "taskset": payload["env"]["taskset"],
        "harness": payload["env"]["agent"]["harness"],
    }[kind]
    target["id"] = sentinel
    path = tmp_path / "unknown-plugin.json"
    path.write_text(json.dumps(payload))
    calls = []
    monkeypatch.setattr(api, "run_ptc_qa_eval", calls.append)
    try:
        cli.main(["--config", str(path)])
    except SystemExit as exc:
        assert exc.code == 2
    except ModuleNotFoundError:
        pytest.fail("followup01: plugin resolution escaped config validation")
    else:
        pytest.fail("followup01: unknown plugin accepted")
    error = capsys.readouterr().err
    assert "invalid EvalConfig JSON" in error
    assert sentinel not in error and "Traceback" not in error
    assert calls == []


@pytest.mark.parametrize("error", [
    ModuleNotFoundError("runtime module sentinel"),
    RuntimeError("runtime sentinel"),
    asyncio.CancelledError(),
])
def test_followup01_CLI_runtime_exception_identity(monkeypatch, tmp_path, error):
    api = importlib.import_module("cotrain_ptc_qa_env")
    path = tmp_path / "runtime.json"
    path.write_text(_config(tmp_path).model_dump_json())
    async def fail(config):
        raise error
    monkeypatch.setattr(api, "run_ptc_qa_eval", fail)
    with pytest.raises(type(error)) as exc:
        _cli().main(["--config", str(path)])
    assert exc.value is error


@pytest.mark.parametrize("error", [
    OSError("unrelated system failure"), RuntimeError("unrelated validator failure"),
])
def test_followup01_CLI_unrelated_validation_error_identity(
        monkeypatch, tmp_path, error):
    path = tmp_path / "unrelated.json"
    path.write_text(_config(tmp_path).model_dump_json())
    def fail(cls, payload):
        raise error
    monkeypatch.setattr(EvalConfig, "model_validate_json", classmethod(fail))
    with pytest.raises(type(error)) as exc:
        _cli().main(["--config", str(path)])
    assert exc.value is error
