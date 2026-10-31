"""PROVES real PTC SDK Agent/HTTP/collector/receipt bridge, not product API."""
import asyncio
import json

from verifiers.v1.agent import Agent
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.interception.server import InterceptionServer
from verifiers.v1.task import Task, TaskData
from ptc.sql_qa import QaChannel
from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
from ptc.test_bash_qa_eval_integration import framework
from ptc_qa_probe import ProbeConfig, ProbeHarness


def test_real_ptc_reporting_bridge(framework):
    config = AgentConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "harness": {"id": "ptc_qa_probe", "max_turns": 4, "program_timeout": 2.0},
        "runtime": {"type": "subprocess"}, "max_turns": 4,
        "retries": {"max_retries": 0},
        "timeout": {"rollout": 15.0, "finalize": 5.0, "scoring": 5.0},
    }))
    policy = ScriptedClient([
        {"call_id": "report", "name": "run_program", "arguments": {
            "code": "print(report_defect(kind='other', detail='ptc-sdk-probe'))",
        }},
        _text_step("done"),
    ])
    channels, received = [], []
    task = Task(TaskData(prompt="Synthetic PTC report."))

    def factory(data):
        received.append(data)
        channel = QaChannel()
        channels.append(channel)
        return channel

    async def scenario():
        server = InterceptionServer()
        framework.servers.append(server)
        server.clients[config.client.model_dump_json()] = policy
        agent = Agent(config, interception=server)
        original = agent.harness
        assert type(original) is ProbeHarness
        assert type(original.config) is ProbeConfig
        # SHORTCUT: deliberate manual binding only to prove SDK feasibility.
        # MISSING: configured API ownership/snapshot/fresh-mode refusals.
        agent.harness = ProbeHarness(original.config, qa_factory=factory)
        try:
            async with server:
                assert server.base_url.startswith("http://127.0.0.1:")
                trace = await agent.run(task)
        finally:
            agent.harness = original
        assert agent.harness is original
        return trace

    trace = asyncio.run(asyncio.wait_for(scenario(), 20.0))
    assert trace.ok, trace.last_error
    assert received == [task.data] and received[0] is task.data
    assert trace.task.data is task.data and trace.task.hash == task.hash
    assert policy.calls == 2 and policy.receipt_at == [2]
    channel, = channels
    arm = json.loads(channel.export())["arms"]["ptc"]
    assert arm["reports"] == 1
    event, = arm["events"]
    assert event["provenance"] == "catalog_callback"
    assert event["detail"] == "ptc-sdk-probe"
    assert framework.external == []
