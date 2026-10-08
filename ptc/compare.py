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
             "max_turns": args.max_turns,
             "timeout": {"rollout": args.rollout_timeout, "scoring": 60}}
    if arm == "bash":
        # The bash arm's own extras are off: this compares action channels, not the
        # count of affordances one arm happens to ship with.
        agent["harness"]["edit"] = False
    if arm == "ptc":
        # `agent.max_turns` above does NOT reach this arm. `PTCHarness` runs its own
        # `for _ in range(self.config.max_turns)` loop (`harness.py:238`) over
        # `PTCHarnessConfig.max_turns`, which defaults to 8 and shadows the agent-level
        # budget entirely -- so the 2026-09-29 raise to 80 silently applied to `bash`
        # only, and 11 of 14 PTC rollouts in the first real run stopped at exactly 8
        # programs while `bash` spent up to 44 turns on the same tier. That is the turn
        # budget becoming the independent variable, which the comment on `--max-turns`
        # exists to forbid. `bash` needs no equivalent line: no bash harness config
        # declares `max_turns`, so it reads the agent-level value already.
        agent["harness"]["max_turns"] = args.max_turns
    config = {
        "env": {"taskset": {"id": args.taskset}, "agent": agent},
        "model": args.model, "num_tasks": args.num_tasks, "num_rollouts": 1,
        "max_concurrent": args.max_concurrent or args.num_tasks,
        "sampling": {"max_tokens": 512},
        "rich": None, "push": False,
        "output_dir": str(Path(args.output_dir).expanduser()),
        "run": {"dir": tag}, "clean": True,
    }
    if args.max_retries:
        # Whole-episode retry, restricted to `ProviderError` so that ONLY transport
        # faults are re-run. `verifiers` ships this off (`configs/retries.py`,
        # `max_retries=0`), which is the right default for a local provider and the wrong
        # one for a metered remote: an upstream 429 or 504 ends the rollout with
        # `stop_condition="error"` and a score of 0.0, and a 0.0 for a transport reason is
        # averaged into the primary outcome as if the arm had failed the task. That biases
        # whichever arm the endpoint happens to treat worse -- here the PTC arm, whose
        # longer catalog prompts drew 6 upstream 504s where `bash` drew none, which would
        # have handed the comparison a ~20 pp artefact in bash's favour. Deliberately NOT
        # a blanket retry: a harness or sandbox fault is a real result and must stay red.
        #
        # `HarnessError` is included for one specific, measured reason (defect 6,
        # `docs/deviations.md`): the two arms report the SAME transport fault under
        # different type names. PTC owns its HTTP client (`_stream_message`), so a relay
        # timeout arrives as `ProviderError` and is retried. The bash arm delegates to the
        # bundled runtime script, which raises `openai.APIError: The request timed out`
        # inside its own subprocess and the rig re-wraps it as `HarnessError` -- not in
        # `include`, so never retried. In run 2g that killed `richest-owner`, bash's
        # heaviest task (40 catalog calls, past the 600s read timeout that
        # `harnesses/utils/core.py:453` gives the bash arm and withholds from PTC), while a
        # 429 on `total-receipt` was retried and scored 1.0. Retryability was deciding the
        # comparison by which arm's code owned the socket.
        #
        # The original intent survives: a DETERMINISTIC harness fault exhausts all
        # retries and still ends red. Only a transient one is now survivable on both arms.
        config["env"]["retries"] = {"max_retries": args.max_retries,
                                    "include": ["ProviderError", "HarnessError"]}
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
                     args.price_cached, turn_budget=args.max_turns)


def _arm_plan(mode: str, arms: str) -> list[tuple[str, bool]]:
    """Which rollout sets to run, in table order.

    **The no-tool control exists only in canned mode.** `_config` never receives
    `use_tool`: the harness, its tools, the turn budget and every other field are
    identical for a tool arm and its control, so in real mode a control rollout is
    its tool arm with a different label and a second invoice. Worse than the waste,
    it would print a `(control)` column scoring like the tool arm, which reads as
    parametric leakage or a broken grader when it is neither.

    `verifiers` offers nothing to build a real control from on the bash arm: `bash`
    is unconditional in `BashHarnessConfig` (only `edit` and `search` are toggles)
    and `disabled_tools` is honoured by seven bundled harnesses, of which `bash` is
    not one -- setting it there is silently ignored. Canned mode establishes that
    the grader requires tool use, on both tasksets, for free.
    """
    plan = []
    for arm in arms.split(","):
        plan.append((arm, True))
        if mode == "canned":
            plan.append((arm, False))
    return plan


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
    # THE TURN BUDGET MUST NOT BIND ON EITHER ARM, or it becomes the independent
    # variable. `ledger`'s aggregation tier needs 40 `ledger_get` calls: the PTC arm
    # spends ONE program on that, the bash arm spends ~42 turns. The old default of 4
    # therefore handed PTC the whole tier by construction — and it is the tier built to
    # be where PTC could win, so the rig would have manufactured its own result.
    # `session.py:98` counts sampled (assistant) nodes and stops with
    # stop_condition="max_turns", which scores 0.0 for a budget reason indistinguishable
    # from incapacity. Any rollout that hits it is reported loudly, not averaged in.
    parser.add_argument("--max-turns", type=int, default=80)
    # Rollout fan-out. Unset it and concurrency is `--num-tasks`, which is the old
    # behaviour and is wrong against a metered endpoint: it ties load to the size of the
    # measurement, so scaling the experiment up silently scales the request rate up with
    # it. A rate-limited provider then answers 429, `stop_condition` becomes "error", and
    # those rollouts score 0.0 for a transport reason that is indistinguishable from
    # incapacity in the score column. Observed for real on VyceAI's free tier, which
    # allows 4 simultaneous requests: at `--num-tasks 14` it errored 23 of 28 rollouts.
    # Set this to the provider's concurrency limit, minus headroom.
    parser.add_argument("--max-concurrent", type=int, default=None)
    # Off by default, matching `verifiers`. See `_config` for why a metered endpoint wants
    # it on, and why it is scoped to `ProviderError` rather than retrying everything.
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--rollout-timeout", type=int, default=900)
    args = parser.parse_args()

    if args.mode == "real" and not args.base_url:
        parser.error("real mode needs --base-url (the OpenAI-compatible endpoint)")

    if args.mode == "real" and args.max_retries == 0:
        # Runs 2d-2h all passed 7. The relay throws transient 429s and 504s, so a budget
        # of 0 lets one void the rollout it hits -- run 3a lost 27 of 58 that way, PTC 20
        # to bash's 7, which reads like an arm asymmetry and was not one. Warn rather
        # than raise the default: a retry budget also masks a FATAL fault, so 0 is the
        # honest default for anyone who reads this line and chooses it.
        print("WARNING: --max-retries 0 in real mode. Every admissible run (2d-2h) used "
              "7, because the relay throws transient 429s and 504s and a budget of 0 "
              "voids the rollout one hits. See docs/deviations.md, top.")

    if args.mode == "real":
        print("No control arm in real mode: `_config` ignores `use_tool`, so a control "
              "would be its tool arm relabelled -- double the bill, and a column that "
              "reads as leakage. Canned mode carries the grader's tool-dependence.")

    results = []
    for arm, use_tool in _arm_plan(args.mode, args.arms):
        results.append(await _run_arm(arm, args, use_tool))

    print()
    print(render(results))

    if args.mode == "canned":
        # What the canned check can and cannot establish.
        #
        # It CANNOT be "both arms reach 1.0". The canned policy is written to solve only
        # the one-call tier, because a scripted policy that solved the aggregation tier
        # would be measuring the script. On the full `ledger` suite it therefore scores
        # 4/14 by design, and demanding 1.0 made the rig report FAIL on a healthy run —
        # the same fail-closed defect this project already found once inside
        # `step2/verdict.py`.
        #
        # What it CAN establish, and each of these can genuinely fail:
        #   1. the control scores exactly 0.0 — nothing is answerable without the tool,
        #      which is the anti-cheat property the taskset was chosen for;
        #   2. the tool arms score above zero — the catalog is reachable at all;
        #   3. the two arms score IDENTICALLY — the same intent through two channels
        #      must land in the same place, so any gap here is the RIG favouring an arm
        #      rather than a finding about arms;
        #   4. nothing truncated — a budget limit invalidates the comparison.
        tool = {r.arm: r for r in results if "control" not in r.arm}
        controls = {r.arm: r for r in results if "control" in r.arm}
        scores = {name: r.score_mean for name, r in tool.items()}
        checks = {
            "controls score 0.0": bool(controls) and all(
                r.score_mean == 0.0 for r in controls.values()),
            "tool arms score above zero": bool(scores) and all(
                (v or 0) > 0 for v in scores.values()),
            "arms agree": len(set(scores.values())) == 1,
            "nothing truncated": all(
                r.n_truncated == 0 for r in results),
        }
        print()
        for name, passed in checks.items():
            print(f"  [{'ok' if passed else 'FAIL'}] {name}")
        if not checks["arms agree"]:
            print(f"  arms disagree under an identical scripted policy: {scores} — "
                  "that is a rig defect, not a result")
        ok = all(checks.values())
        print(f"\nRIG {'PASS' if ok else 'FAIL'} — "
              f"tool arms {sorted(set(scores.values()))}, controls 0.0")
        return 0 if ok else 1

    # A run where nothing reached the provider must not exit 0. `real` mode is the paid
    # path, so the failure to catch here is a wrong key or a dead endpoint producing a
    # full table of zeros that a reader takes for a finding.
    errored = sum(r.stop_conditions.get("error", 0) for r in results)
    if errored:
        print(f"\n{errored} rollout(s) ended in error — nothing was measured. Exiting "
              "non-zero so a broken run cannot be read as a result.")
        return 1

    print("\nRead these against the signed predictions in docs/pre-registration.md §4 "
          "(H1-H5). No verdict is printed here on purpose.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
