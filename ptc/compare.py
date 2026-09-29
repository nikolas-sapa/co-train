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

Two tasksets, and they are not interchangeable:

- `glossary` (shipped) is the rig check. One tool call, so both arms saturate at 1.0 —
  measured, not assumed. It proves the plumbing works and cannot show a gap.
- `ledger` (this repo) is the measurement. Same catalog for both arms, three difficulty
  tiers, deterministic grader. See `ledger/taskset.py` for why a self-authored suite was
  necessary and what that costs in validity.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import on_pythonpath  # noqa: E402
from ptc.metrics import render, summarize  # noqa: E402

# Unconditional, and before any run: the `ledger` taskset loads in-process here but its
# tool server is a separate process launched from a different cwd, which needs the repo
# root on PYTHONPATH rather than on sys.path. Harmless for `glossary`.
on_pythonpath()

ARMS = ("bash", "ptc")
TASKSETS = ("glossary", "ledger")

# The canned policy is scripted per taskset AND per arm, because the two arms speak
# different action languages and writing the script once would mean writing it in one
# arm's idiom. Neither script is allowed to be cleverer than the other: same tool, same
# number of round trips, same final answer.
_ID = __import__("re").compile(r"\br\d{2}\b")


def _canned_policy(arm: str, use_tool: bool, taskset: str):
    """A scripted policy that speaks each arm's own action language.

    Two arms, two interfaces, one intent -- that asymmetry is the experiment, so the
    canned policy has to be written twice or the comparison is rigged. `bash` gets a
    tool call; `ptc` gets a program.

    On `ledger` it solves only the one-call tier. The many-call tier is the part that
    needs a model, and a canned policy that solved it would be measuring the script.
    """
    from verifiers.v1.clients import Client

    def act(prompt: str) -> dict:
        """The one tool call this policy makes, in the calling arm's idiom."""
        if taskset == "glossary":
            entity = prompt.split('"')[1].lower() if '"' in prompt else ""
            if arm == "bash":
                return {"name": "facts_lookup", "arguments": json.dumps({"name": entity})}
            return {"name": "run_program",
                    "arguments": json.dumps({"code": f"print(facts_lookup(name={entity!r}))"})}
        found = _ID.search(prompt)
        record = found.group(0) if found else "r00"
        if arm == "bash":
            return {"name": "ledger_get", "arguments": json.dumps({"id": record})}
        return {"name": "run_program",
                "arguments": json.dumps({"code": f"print(ledger_get(id={record!r}))"})}

    def answer(prompt: str, observed: str) -> str:
        if taskset == "glossary":
            return observed
        # `ledger_get` returns the whole record; the prompt says which field is wanted.
        try:
            record = json.loads(observed)
        except json.JSONDecodeError:
            return ""
        return str(record.get("owner" if "owns" in prompt else "amount", ""))

    class Canned(Client):
        async def get_response(self, dialect, body, sampling, session_id=None,
                               turn=None, headers=None):
            messages = body.get("messages", [])
            tool_results = [m for m in messages if m.get("role") == "tool"]
            prompt = " ".join(str(m.get("content", "")) for m in messages
                              if m.get("role") == "user")

            if not use_tool:
                # The control. Answers without ever touching the tool channel, so the
                # grader must score it 0.0 in BOTH arms or it is not grading tool use.
                message = {"role": "assistant", "content": "<answer>0</answer>"}
                finish = "stop"
            elif not tool_results:
                message = {"role": "assistant", "content": None,
                           "tool_calls": [{"id": "c1", "type": "function",
                                           "function": act(prompt)}]}
                finish = "tool_calls"
            else:
                observed = str(tool_results[-1].get("content", "")).strip()
                message = {"role": "assistant",
                           "content": f"<answer>{answer(prompt, observed)}</answer>"}
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
        "env": {"taskset": {"id": args.taskset}, "agent": agent},
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


async def _run_arm(arm: str, args, use_tool: bool):
    from verifiers.v1.configs.cli.eval import EvalConfig
    from verifiers.v1.cli.eval.runner import run_eval

    tag = f"{args.taskset}-{arm}-{'tool' if use_tool else 'control'}"
    if args.mode == "canned":
        from verifiers.v1.interception import server as server_mod

        server_mod.resolve_client = lambda config: _canned_policy(arm, use_tool, args.taskset)

    records = await run_eval(EvalConfig.model_validate(_config(arm, args, tag)))
    label = arm if use_tool else f"{arm} (control)"
    return summarize(records, label, args.taskset, args.price_in, args.price_out,
                     args.price_cached)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("canned", "real"))
    parser.add_argument("--taskset", choices=TASKSETS, default="glossary")
    parser.add_argument("--model", default="canned-policy")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--key-var", default="OPENAI_API_KEY")
    parser.add_argument("--num-tasks", type=int, default=5)
    parser.add_argument("--output-dir", default="~/scratch/co-train-compare")
    parser.add_argument("--arms", default=",".join(ARMS))
    # Dollars per million tokens. Required for the cost co-primary, and deliberately
    # NOT defaulted to a guess: pre-reg section 2 cites -38.4% tokens against +6.8%
    # cost (r=0.15), so a cost inferred from tokens at an assumed price is the exact
    # error being avoided. Absent a price, cost prints as unknown.
    parser.add_argument("--price-in", type=float, default=0.0)
    parser.add_argument("--price-out", type=float, default=0.0)
    # Cache reads live outside `prompt_tokens` and are usually discounted. Without this
    # they are charged at the full input rate and the cost is flagged as an upper bound.
    parser.add_argument("--price-cached", type=float, default=None)
    args = parser.parse_args()

    if args.mode == "real" and not args.base_url:
        parser.error("real mode needs --base-url (the OpenAI-compatible endpoint)")

    results = []
    for arm in args.arms.split(","):
        for use_tool in (True, False):
            results.append(await _run_arm(arm, args, use_tool))

    print()
    print(render(results))

    if args.mode == "canned":
        # The rig is only trustworthy if the control goes red. A green control means
        # the grader is scoring something other than tool use, and every number above
        # it is then describing the wrong experiment.
        scored = {r.arm: r.score_mean for r in results if "control" not in r.arm}
        controls = {r.arm: r.score_mean for r in results if "control" in r.arm}
        ok = (scored and all(v == 1.0 for v in scored.values())
              and all(v == 0.0 for v in controls.values()))
        print(f"\nRIG {'PASS' if ok else 'FAIL'} — tool arms reach 1.0, controls fall to 0.0")
        return 0 if ok else 1

    print("\nRead these against the signed predictions in docs/pre-registration.md §4 "
          "(H1-H5). No verdict is printed here on purpose.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
