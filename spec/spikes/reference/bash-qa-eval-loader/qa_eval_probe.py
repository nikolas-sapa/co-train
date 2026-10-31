"""PROVES: flat Env loader/config specialization, not reporting execution."""
from typing import Literal

from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent.env import SingleAgentEnv, SingleAgentEnvConfig

__all__ = ["ProbeEnv"]


class ProbeEnvConfig(SingleAgentEnvConfig):
    id: Literal["qa_eval_probe"] = "qa_eval_probe"


class ProbeEnv(SingleAgentEnv, Env[ProbeEnvConfig]):
    async def run(self, task, agents):
        # MISSING: actual execution/telemetry. Never fall back to ordinary runs.
        raise NotImplementedError("construction-only spike")
