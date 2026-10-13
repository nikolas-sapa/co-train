"""Build the dead-group probe's prompts file from a BIRD draw.

The probe's reward is `exact_match_reward`: binary, case-insensitive, whitespace-
normalised string equality against a `<answer>...</answer>` block. That is deliberate --
the probe exists to measure *that* reward's group geometry -- and it decides what the
`answer` field can be.

**It cannot be the gold SQL.** Many different queries are correct for one question, so
string-matching a model's SQL against one reference query would read as near-uniform
failure, drive `frac_reward_zero_std` toward 1.0, and abort the probe over the
comparison rather than over the reward. The probe would spend a free session answering a
question nobody asked.

So the `answer` is the gold query's **result**, and the draw is restricted to tasks whose
gold returns exactly one row and one column. On a 1x1 result, exact string match IS
execution accuracy, so the probe measures the real reward's geometry rather than a proxy
for it -- and the prompts file carries no database, which is what makes it a 30 KB
upload instead of a 2.1 GB one.

**The restriction is an instrument choice and is disclosed, not hidden.** A scalar-answer
subset is not BIRD, and a solve rate measured on it is not BIRD's solve rate. What the
probe answers is still the thing it was built to answer -- whether a binary reward
produces usable groups for a 0.6B policy -- but `--out`'s header records the subset, the
filter, and the counts, so a manifest written from it cannot quietly claim to describe
the whole corpus.

Usage:

    .venv-ptc/bin/python -m bench.make_probe_prompts \\
        --bird ~/scratch/bird-sql/bird-dev-extracted/dev_20240627 \\
        --out /tmp/probe_prompts.jsonl --draw 400 --seed 0
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import time

from bench.loader import load_bird
from bench.score import MAX_ROWS
from bench.suite import select
from bench.task import SqlTask

# A scalar answer the reward can compare. Longer than this and an exact-match reward is
# measuring transcription rather than retrieval -- a 300-character answer disagrees on a
# stray space, which is the reward's problem and not the policy's.
MAX_ANSWER_CHARS = 60

GOLD_TIMEOUT_S = 10.0

PROMPT_TEMPLATE = """\
{schema}

Question: {question}{evidence}

Answer the question from the database above. Put only the final answer between
<answer> and </answer> tags, with no explanation inside them.
"""


def schema_for(db_path: str) -> str:
    """The CREATE statements, which is what the model needs and all it needs."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
    finally:
        con.close()
    return "\n".join(r[0] for r in rows)


def scalar_answer(task: SqlTask) -> str | None:
    """The gold result, if it is one row by one column and short. Otherwise None.

    A gold that errors or never terminates returns None too: it is a defective task,
    and scoring it would hand the probe a prompt no policy can solve, which reads as
    "too hard" instead of "broken". Two of BIRD dev's 1534 golds never terminate.
    """
    try:
        con = sqlite3.connect(f"file:{task.db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        # A real deadline. The first version of this handler closed over a flag nothing
        # ever set, so it returned 0 forever and the two BIRD golds that never terminate
        # hung the whole draw -- a timeout that cannot fire is this repo's signature
        # defect, committed here while writing the tool that avoids it.
        start = time.monotonic()

        def _interrupt() -> int:
            return 1 if time.monotonic() - start > GOLD_TIMEOUT_S else 0

        con.set_progress_handler(_interrupt, 10_000)
        cur = con.execute(task.gold_sql)
        rows = cur.fetchmany(2)
        if len(rows) != 1 or len(rows[0]) != 1:
            return None
        value = rows[0][0]
        if value is None:
            return None
        text = " ".join(str(value).split())
        if not text or len(text) > MAX_ANSWER_CHARS:
            return None
        return text
    except (sqlite3.Error, OverflowError, ValueError):
        return None
    finally:
        con.close()


def build(bird_root: pathlib.Path, draw: int, seed: int) -> tuple[list[dict], dict]:
    tasks = load_bird(bird_root)
    drawn = select(tasks, draw, seed=seed)
    schemas: dict[str, str] = {}

    rows: list[dict] = []
    rejected = {"not_scalar_or_broken": 0}
    for task in drawn:
        answer = scalar_answer(task)
        if answer is None:
            rejected["not_scalar_or_broken"] += 1
            continue
        if task.db_id not in schemas:
            schemas[task.db_id] = schema_for(task.db_path)
        evidence = f"\nHint: {task.evidence}" if task.evidence else ""
        rows.append({
            "prompt": PROMPT_TEMPLATE.format(
                schema=schemas[task.db_id], question=task.question, evidence=evidence
            ),
            "answer": answer,
            # provenance, ignored by the probe's loader, kept so a row can be traced
            "task": task.name,
            "tier": task.tier,
            "shape": task.shape,
        })

    header = {
        "corpus": "BIRD-SQL dev",
        "subset": "scalar-answer only: gold returns exactly 1 row x 1 column",
        "why_subset": (
            "the probe's reward is exact string match on a tagged answer, so a gold "
            "SQL reference would read as near-uniform failure and abort the probe over "
            "the comparison rather than the reward. On a 1x1 result exact match IS "
            "execution accuracy."
        ),
        "not_bird_solve_rate": (
            "a solve rate measured on this subset is NOT BIRD's solve rate, and a "
            "frontier manifest written from it must say so"
        ),
        "drawn": len(drawn),
        "kept": len(rows),
        "rejected": rejected,
        "seed": seed,
        "max_answer_chars": MAX_ANSWER_CHARS,
        "max_rows_bound": MAX_ROWS,
        "tiers": {t: sum(1 for r in rows if r["tier"] == t) for t in sorted({r["tier"] for r in rows})},
        "distinct_shapes": len({r["shape"] for r in rows}),
    }
    return rows, header


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bird", type=pathlib.Path, required=True,
                   help="BIRD dev root: the directory holding dev.json and dev_databases/")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--draw", type=int, default=400,
                   help="candidates to draw before the scalar filter (default 400)")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    rows, header = build(args.bird, args.draw, args.seed)
    if not rows:
        print("no scalar-answer tasks survived the draw", file=sys.stderr)
        return 1

    args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    args.out.with_suffix(".header.json").write_text(json.dumps(header, indent=2) + "\n")

    print(json.dumps(header, indent=2))
    print(f"\nwrote {len(rows)} prompts to {args.out}")
    print(f"wrote provenance to {args.out.with_suffix('.header.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
