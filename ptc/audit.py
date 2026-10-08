"""Does the arm *compute*, or does it guess in context? Read from traces alone.

`pre-registration.md` §8/A6 asks whether forcing the action to be expressed as a program
makes a model compute where a free-text channel lets it guess. N3 predicts the bash arm's
shell-call share stays under 0.10 on the full-scan tier -- the tier where a shell is
exactly what the task needs -- and calls that prediction "the one most worth being wrong
about": if bash's share rises and its score rises with it, the mechanism is tool
availability and the framing is wrong.

`compare.py` reports `shell-call share` as one number for the whole suite, which cannot
answer this. It is an average across tiers that ask opposite questions, and it counts a
shell call as a shell call whether the command did arithmetic or just listed ids. This
reads the per-rollout call sequence instead.

Usage: python -m ptc.audit <run-dir> [...]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# A command computes if it does arithmetic rather than merely retrieving or printing.
# Deliberately literal: this decides a pre-registered claim, so it matches operators and
# known tools instead of guessing at intent. `sort`/`wc`/`head` are retrieval and do NOT
# count -- the point of N3 is whether the arm computes, not whether it touches a shell.
ARITHMETIC = re.compile(
    r"(\bsum\b|\bawk\b|\bjq\b|\bbc\b|\bpython3?\b|\+ *[0-9$]|[0-9$] *\+|"
    r"\badd\b|\breduce\b|\btotal\b)", re.IGNORECASE)


def calls_of(rollout: dict) -> list[dict]:
    """Every tool call in the rollout, in order, with name and raw arguments."""
    out = []
    for node in rollout["traces"][0].get("nodes") or []:
        for tc in (node.get("message") or {}).get("tool_calls") or []:
            out.append({"name": tc.get("name"), "arguments": tc.get("arguments") or ""})
    return out


def final_answer(rollout: dict) -> str:
    """The text of the last assistant message, which is where `correct` reads the answer."""
    for node in reversed(rollout["traces"][0].get("nodes") or []):
        msg = node.get("message") or {}
        if msg.get("role") == "assistant" and msg.get("content"):
            return str(msg["content"])
    return ""


def audit_rollout(rollout: dict) -> dict:
    calls = calls_of(rollout)
    names = Counter(c["name"] for c in calls)
    shell = [c for c in calls if c["name"] == "bash"]
    arithmetic = [c for c in shell if ARITHMETIC.search(c["arguments"])]
    score = 0.0
    for tr in rollout["traces"]:
        for comp in tr["rewards"].values():
            score += comp["score"] * comp.get("weight", 1.0)
    return {
        "task": rollout["task"]["data"]["name"],
        "tier": ("full-scan" if rollout["task"]["data"].get("min_calls") == 40
                 else "cheap"),
        "ok": bool(rollout.get("ok")),
        "score": score,
        "n_calls": len(calls),
        "catalog_calls": sum(n for k, n in names.items() if k and k.startswith("ledger")),
        "shell_calls": len(shell),
        "arithmetic_calls": len(arithmetic),
        "shell_share": (len(shell) / len(calls)) if calls else 0.0,
        "answer": final_answer(rollout)[:80],
    }


def summarise(rows: list[dict]) -> list[dict]:
    """One line per (arm, tier), which is the unit A6 adjudicates on."""
    out = []
    for arm in sorted({r["arm"] for r in rows}):
        for tier in ("cheap", "full-scan"):
            grp = [r for r in rows if r["arm"] == arm and r["tier"] == tier]
            if not grp:
                continue
            void = [r for r in grp if not r["ok"]]
            live = [r for r in grp if r["ok"]]
            out.append({
                "arm": arm, "tier": tier, "n": len(grp), "void": len(void),
                "solved": sum(1 for r in live if r["score"] == 1.0),
                "shell_share": (sum(r["shell_share"] for r in live) / len(live)
                                if live else 0.0),
                "arithmetic_rollouts": sum(1 for r in live if r["arithmetic_calls"]),
            })
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows: list[dict] = []
    for run_dir in argv[1:]:
        for arm_dir in sorted(Path(run_dir).glob("ledger-*")):
            path = arm_dir / "traces.jsonl"
            if not path.exists():
                continue
            with open(path) as fh:
                for line in fh:
                    if line.strip():
                        r = audit_rollout(json.loads(line))
                        r["arm"] = arm_dir.name
                        rows.append(r)

    print(f"{'arm':<20}{'tier':<11}{'n':>4}{'void':>6}{'solved':>8}"
          f"{'shell share':>13}{'arith rollouts':>16}")
    print("-" * 78)
    for s in summarise(rows):
        print(f"{s['arm']:<20}{s['tier']:<11}{s['n']:>4}{s['void']:>6}{s['solved']:>8}"
              f"{s['shell_share']:>13.4f}{s['arithmetic_rollouts']:>16}")

    print()
    full = [s for s in summarise(rows) if s["tier"] == "full-scan"]
    for s in full:
        verdict = ("N3 HOLDS" if s["shell_share"] < 0.10
                   else "N3 FALSIFIED -- mechanism is availability, not channel")
        print(f"{s['arm']:<20} full-scan shell share {s['shell_share']:.4f}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
