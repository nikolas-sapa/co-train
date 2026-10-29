"""Requested training length must survive the free preflight path."""

import json

import pytest

from train import grpo_ptc


@pytest.mark.parametrize("steps", [1, 17, 200])
def test_preflight_forwards_requested_steps(monkeypatch, steps):
    # Isolate config forwarding; real closed-gate ordering has separate tests.
    monkeypatch.setattr(grpo_ptc, "require_frontier_taskset", lambda *a, **kw: None)
    monkeypatch.setattr(grpo_ptc, "require_stack", lambda *a, **kw: None)
    assert grpo_ptc.preflight(steps=steps)["max_steps"] == steps


@pytest.mark.parametrize("arguments, expected", [([], 200), (["--steps", "17"], 17)])
def test_cli_preflight_only_forwards_steps(monkeypatch, capsys, arguments, expected):
    received = []

    def preflight(arms, **kwargs):
        received.append(kwargs.get("steps", 200))
        return {"max_steps": received[-1]}

    monkeypatch.setattr(grpo_ptc, "preflight", preflight)
    monkeypatch.setattr(grpo_ptc, "model_spec", lambda: {})
    monkeypatch.setattr(grpo_ptc, "resolved_versions", lambda: {})
    assert grpo_ptc.main(["--preflight-only", *arguments]) == 0
    assert received == [expected]
    assert json.loads(capsys.readouterr().out)["config"]["max_steps"] == expected


@pytest.mark.parametrize("steps", [0, -1, True, 1.5, "17", None, float("inf"), float("nan")])
def test_training_config_requires_positive_integral_steps(steps):
    with pytest.raises(ValueError, match="positive integer"):
        grpo_ptc.training_config(steps=steps)


def test_default_training_length_remains_200():
    assert grpo_ptc.build_parser().parse_args([]).steps == 200
    assert grpo_ptc.training_config()["max_steps"] == 200
