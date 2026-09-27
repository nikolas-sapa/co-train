#!/usr/bin/env python3
"""bash vs PTC on one taskset, same model, same tasks. The premise check.

`docs/pre-registration.md` §6: if the untrained bash-over-PTC gap does not reproduce,
the project is over and the output is a short negative report. This script is the
instrument for that measurement, and it runs in two modes:

    python ptc/compare.py canned                 # free, no model, no network
    python ptc/compare.py real --model <id> --base-url <url> --key-var <ENV>

**canned** drives both arms with a scripted non-LLM policy. It measures nothing about
models -- it proves the *rig* can tell the arms apart, including a negative control
that must score 0.0. A comparison whose no-tool control also scores 1.0 is measuring
the grader, not the harness.

**real** points `EvalClientConfig.base_url` at any OpenAI-compatible endpoint. That is
the seam `Harness.launch` names ("every model call goes through endpoint + secret") and
the one `docs/spike-verifiers.md` says to build on, rather than the `resolve_client`
monkeypatch the spike used -- that rebinds a name inside another module and breaks
silently if upstream inlines it. The canned mode still uses the monkeypatch, on purpose:
it is scaffolding for a policy that is not a server, and it is confined to this branch.

ponytail: `glossary` only. It is the one shipped environment that is deterministic,
offline, container-free, and whose reward is 1.0 only if the tool channel was used
(docs/spike-verifiers.md). A second taskset is worth adding when a result exists to
defend; adding it now would be two unrun rigs instead of one run one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ARMS = ("bash", "ptc")


def _canned_policy(arm: str, use_tool: bool):
    """A scripted policy that speaks each arm's own action language.

    Two arms, two interfaces, one intent -- that asymmetry is the experiment, so the
    canned policy has to be written twice or the comparison is rigged. `bash` gets a
    tool call; `ptc` gets a program. Neither is allowed to be cleverer than the other:
    both look up the entity and echo the result verbatim.
    """
    from verifiers.v1.clients import Client

    class Canned(Client):
        async def get_response(self, dialect, body, sampling, session_id=None,
                               turn=None, headers=None):
            messages = body.get("messages", [])
            tool_results = [m for m in messages if m.get("role") == "tool"]
            prompt = " ".join(str(m.get("content", "")) for m in messages
                              if m.get("role") == "user")
            entity = prompt.split('"')[1].lower() if '"' in prompt else ""

            if not use_tool:
                # The control. Answers without ever touching the tool channel, so the
                # grader must score it 0.0 in BOTH arms or it is not grading tool use.
                message = {"role": "assistant",
                           "content": f"<answer>{entity} is a famous person</answer>"}
                finish = "stop"
            elif not tool_results:
                call = (
                    {"name": "facts_lookup", "arguments": json.dumps({"name": entity})}
                    if arm == "bash" else
                    {"name": "run_program",
                     "arguments": json.dumps({"code": f"print(facts_lookup(name={entity!r}))"})}
                )
                message = {"role": "assistant", "content": None,
                           "tool_calls": [{"id": "c1", "type": "function", "function": call}]}
                finish = "tool_calls"
            else:
                message = {"role": "assistant",
                           "content": f"<answer>{tool_results[-1].get('content', '')}</answer>"}
                finish = "stop"

            raw = {"id": "canned", "object": "chat.completion", "created": int(time.time()),
                   "model": body.get("model", "canned"),
                   "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                   "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
            response = dialect.parse_response(dialect.validate_response(raw))
            # `raw` is mandatory: server.py frames SSE from it and a typed Response with
            # raw=None kills the harness program with APIConnectionError. Found by
            # running, recorded in docs/spike-verifiers.md.
            response.raw = raw
            return response

    return Canned()


def _config(arm: str, args, tag: str) -> dict:
    agent = {"harness": {"id": arm}, "runtime": {"type": "subprocess"},
             "max_turns": 4, "timeout": {"rollout": 300, "scoring": 60}}
    if arm == "bash":
        # The bash arm's own extras are off: this compares action channels, not the
        # count of affordances one arm happens to ship with.
        agent["harness"]["edit"] = False
    config = {
        "env": {"taskset": {"id": "glossary"}, "agent": agent},
        "model": args.model, "num_tasks": args.num_tasks, "num_rollouts": 1,
        "max_concurrent": args.num_tasks, "sampling": {"max_tokens": 512},
        "rich": None, "push": False,
        "output_dir": str(Path(args.output_dir).expanduser()),
        "run": {"dir": tag}, "clean": True,
    }
    if args.mode == "canned":
        # server.py:600 relays a streaming request straight upstream unless the client
        # is a train client, and the bundled chat program always streams -- so with an
        # eval client the canned policy is never called at all.
        config["client"] = {"type": "train"}
    else:
        config["client"] = {"type": "eval", "base_url": args.base_url,
                            "api_key_var": args.key_var}
    return config


async def _run_arm(arm: str, args, use_tool: bool) -> dict:
    from verifiers.v1.configs.cli.eval import EvalConfig
    from verifiers.v1.cli.eval.runner import run_eval

    tag = f"{arm}-{'tool' if use_tool else 'control'}"
    if args.mode == "canned":
        from verifiers.v1.interception import server as server_mod

        server_mod.resolve_client = lambda config: _canned_policy(arm, use_tool)

    records = await run_eval(EvalConfig.model_validate(_config(arm, args, tag)))
    traces = [t for r in records for t in r.traces]
    errors = [f"{e.type}: {e.message[:160]}" for r in records for e in r.errors]
    rewards = [t.reward for t in traces]
    return {"arm": arm, "control": not use_tool, "n": len(rewards),
            "rewards": rewards, "errors": errors,
            "mean": sum(rewards) / len(rewards) if rewards else None}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("canned", "real"))
    parser.add_argument("--model", default="canned-policy")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--key-var", default="OPENAI_API_KEY")
    parser.add_argument("--num-tasks", type=int, default=5)
    parser.add_argument("--output-dir", default="~/scratch/co-train-compare")
    parser.add_argument("--arms", default=",".join(ARMS))
    args = parser.parse_args()

    if args.mode == "real" and not args.base_url:
        parser.error("real mode needs --base-url (the OpenAI-compatible endpoint)")

    results = []
    for arm in args.arms.split(","):
        for use_tool in (True, False):
            results.append(await _run_arm(arm, args, use_tool))
            print(f"  {results[-1]['arm']:5} "
                  f"{'control' if results[-1]['control'] else 'tool   '} "
                  f"mean={results[-1]['mean']} rewards={results[-1]['rewards']}"
                  + (f" ERRORS={results[-1]['errors']}" if results[-1]["errors"] else ""))

    print()
    scored = {r["arm"]: r["mean"] for r in results if not r["control"]}
    controls = {r["arm"]: r["mean"] for r in results if r["control"]}
    for arm in scored:
        print(f"{arm:5} tool={scored[arm]} control={controls[arm]}")
    if len(scored) == 2:
        gap = scored.get("bash", 0) - scored.get("ptc", 0)
        print(f"\nbash - ptc = {gap:+.3f}")

    if args.mode == "canned":
        # The rig is only trustworthy if the control goes red. A green control means
        # the grader is scoring something other than tool use.
        ok = all(v == 1.0 for v in scored.values()) and all(v == 0.0 for v in controls.values())
        print(f"\nRIG {'PASS' if ok else 'FAIL'} — "
              f"both arms reach 1.0 with the tool, both fall to 0.0 without it")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
