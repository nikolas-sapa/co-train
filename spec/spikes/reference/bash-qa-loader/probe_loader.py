"""Verify actual SDK loading and JSON construction, zero policy actions."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qa_activation_probe import ProbeConfig, ProbeHarness
from verifiers.v1.agent import Agent
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.utils.loaders import harness_class, harness_config_type

# PROVES: actual loader, no mocked class/config resolver.
assert harness_class("qa_activation_probe") is ProbeHarness
assert harness_config_type("qa_activation_probe") is ProbeConfig
# SHORTCUT: synthetic model label, never resolved or called.
config = AgentConfig.model_validate({
    "model": "fixture-model",
    "harness": {"id": "qa_activation_probe", "edit": False, "search": False},
    "runtime": {"type": "subprocess"},
    "max_turns": 3,
    "retries": {"max_retries": 0},
})
assert type(config.harness) is ProbeConfig
restored = AgentConfig.model_validate_json(config.model_dump_json())
assert type(restored.harness) is ProbeConfig
agent = Agent(restored)
assert type(agent.harness) is ProbeHarness
assert "_qa_required" not in config.model_dump_json()
# MISSING: binding, task construction, entry permit, refusal and real rollout.
# No agent.run call: loading is not proof of functioning reporting activation.
print(json.dumps({
    "plugin_class": type(agent.harness).__name__,
    "config_class": type(restored.harness).__name__,
    "json_roundtrip": True,
    "policy_actions": 0,
    "run_called": False,
}))
