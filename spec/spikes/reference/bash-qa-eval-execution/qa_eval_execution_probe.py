"""PROVES real episode-agent/QA/persistence bridge. NOT production admission."""
import json
from typing import Literal

from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent.env import SingleAgentEnv, SingleAgentEnvConfig
from cotrain_bash_qa import run_configured_bash_qa
from ptc.sql_qa import QaChannel

__all__ = ["ProbeEnv"]


class ProbeEnvConfig(SingleAgentEnvConfig):
    id: Literal["qa_eval_execution_probe"] = "qa_eval_execution_probe"


class ProbeEnv(SingleAgentEnv, Env[ProbeEnvConfig]):
    async def run(self, task, agents):
        captured = []

        def factory(data):
            channel = QaChannel()
            captured.append(channel)
            return channel

        agent = agents.agent
        assert type(agent).__name__ == "_EpisodeAgent"
        original = agent.harness
        trace = await run_configured_bash_qa(
            agent, task.build_bash_qa_task, qa_factory=factory
        )
        assert agent.harness is original
        assert trace.task.data is task.data
        assert len(captured) == 1
        trace.info["qa_eval_probe"] = json.loads(captured[0].export())
        # SHORTCUT/MISSING: no public fresh-evaluation admission, retry/resume
        # rejection, seed-contract or metadata-collision validation. Implement
        # those from the final contract, never copy this as production code.
