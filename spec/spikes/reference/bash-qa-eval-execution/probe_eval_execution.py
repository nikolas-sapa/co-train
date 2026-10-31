"""PROVES real run_eval/child/tool receipt and SDK JSONL QA persistence.

Requires the qualified installed interpreter and --scratch ABSOLUTE_NEW_DIR.
No installations/downloads. Explicit fixture seams: delegated interception
construction/preseed client; existing owned runtime cache/drain helper; parent
socket/DNS loopback-only guard. SDK loader/Env/Agent/runner/writer stay real.
SHORTCUT: one synthetic success, no production admission or failure proof.
"""
import argparse
import asyncio
import ipaddress
import json
from pathlib import Path
import socket
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(ROOT)]

import pytest
from verifiers.v1 import env as env_mod
from verifiers.v1.cli.eval.runner import run_eval
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.interception.server import InterceptionServer
from ptc.sql_qa import REPORT_TOOL
from ptc.test_bash_qa_activation_integration import (
    ScriptedClient, _report_call, _text_step,
)
from ptc.test_bash_qa_integration import _patch_runtimes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    scratch = parser.parse_args().scratch
    if not scratch.is_absolute():
        raise ValueError("scratch must be absolute")
    scratch.mkdir()  # create-only, never delete/reuse a prior run
    output, runtime_root = scratch / "output", scratch / "runtimes"
    output.mkdir()
    runtime_root.mkdir()
    config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": "qa_eval_execution_probe",
            "taskset": {"id": "qa_eval_execution_taskset"},
            "interception": {"type": "server"},
            "agent": {
                "harness": {"id": "cotrain_bash_qa", "edit": False, "search": False},
                "runtime": {"type": "subprocess"},
                "max_turns": 3,
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "rich": None, "resume": False, "clean": False,
        "output_dir": str(output), "run": {"dir": "probe"},
    }))
    assert config.push is False and config.run.attach is None
    scripted = ScriptedClient([
        _report_call({"kind": "other", "detail": "real-eval-probe"}),
        _text_step("done"),
    ])
    servers, runtimes, blocked = [], [], []
    make_interception = env_mod.make_interception
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    resolve = socket.getaddrinfo

    def local(host):
        if host is None or host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            blocked.append("external connect")
            raise AssertionError("external network forbidden by fixture")

    def guarded_connect(sock, address):
        check(sock, address)
        return connect(sock, address)

    def guarded_connect_ex(sock, address):
        check(sock, address)
        return connect_ex(sock, address)

    def guarded_resolve(host, *args, **kwargs):
        if not local(host):
            blocked.append("external DNS")
            raise AssertionError("external DNS forbidden by fixture")
        return resolve(host, *args, **kwargs)

    def seeded(config_, *, requires_tunnel, state_service_secrets=()):
        assert requires_tunnel is False
        server = make_interception(
            config_, requires_tunnel=requires_tunnel,
            state_service_secrets=state_service_secrets,
        )
        assert type(server) is InterceptionServer
        server.clients[config.client.model_dump_json()] = scripted
        servers.append(server)
        return server

    with pytest.MonkeyPatch.context() as mp:
        _patch_runtimes(mp, runtime_root, runtimes)
        mp.setattr(env_mod, "make_interception", seeded)
        mp.setattr(socket.socket, "connect", guarded_connect)
        mp.setattr(socket.socket, "connect_ex", guarded_connect_ex)
        mp.setattr(socket, "getaddrinfo", guarded_resolve)
        episodes = asyncio.run(asyncio.wait_for(run_eval(config), 20.0))
    assert blocked == []
    episode, = episodes
    assert episode.ok, episode.errors
    trace, = episode.traces
    assert trace.ok, trace.last_error
    assert scripted.calls == 2 and scripted.receipt_at == [2]
    qa = trace.info["qa_eval_probe"]
    assert qa["arms"]["bash"]["reports"] == 1
    paths = list(output.rglob("*.jsonl"))
    assert len(paths) == 1, paths
    persisted, = [json.loads(line) for line in paths[0].read_text().splitlines()]
    assert persisted["traces"][0]["info"]["qa_eval_probe"] == qa
    assert persisted["task"]["hash"] == persisted["traces"][0]["task"]["hash"]
    assert len(servers) == len(runtimes) == 1
    assert servers[0].sessions == servers[0].state_sessions == {}
    assert list(runtime_root.rglob(REPORT_TOOL)) == []
    print("GREEN: actual run_eval -> _EpisodeAgent -> configured QA -> child/tool gate")
    print("1 episode, 1 channel/report; receipt at policy call2; SDK JSONL telemetry matches")
    print("0 external network attempts; real shared interception and runtime teardown")


if __name__ == "__main__":
    main()
