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

# The SQL-generation task. Separate template because the first real probe run proved
# the scalar one unanswerable: it carries the SCHEMA and asks for a data VALUE, with no
# rows in the prompt, so the solve rate was structurally 0 and `frac_reward_zero_std`
# read 1.000 at step 0. Writing SQL is also the task the ~25% frontier estimate in
# pre-registration A8 actually describes -- SLM-SQL measures SQL generation judged by
# execution -- so the estimate and the task finally match.
#
# **The question comes FIRST.** In the scalar prompts it sat at the tail, after the full
# schema, and the v3 run reported `Input IDs of shape (4, 2049) > max sequence length
# 2048 -- we shall truncate it ourselves`. Truncation from the right removes whatever is
# last, so the question and the output instruction were the first things lost. Roughly
# 10% of those prompts overflowed. Put the task up front and truncation costs schema
# detail rather than the question itself.
SQL_PROMPT_TEMPLATE = """\
Write one SQLite query that answers the question. Output only the query, in a ```sql
fenced block, with no explanation.

Question: {question}{evidence}

Schema:
{schema}
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


# BIRD dev databases small enough to ship as a Kaggle dataset: 82 MB for 922 tasks over
# 207 shapes, against 1.4 GB for all eleven. 60% of the corpus for 6% of the bytes. The
# four excluded (financial, card_games, codebase_community, european_football_2) are
# 69-572 MB each.
SHIPPABLE_DB_IDS = frozenset({
    "superhero", "student_club", "toxicology", "thrombosis_prediction",
    "california_schools", "formula_1", "debit_card_specializing",
})


def build_sql(bird_root: pathlib.Path, draw: int, seed: int,
              db_ids: frozenset[str] | None) -> tuple[list[dict], dict]:
    """SQL-generation prompts, scored later by execution rather than string match.

    No gold execution here: the answer is the gold QUERY, and whether a prediction is
    right is decided by `bench.score.execution_accuracy` at reward time. That is why
    this variant needs the databases shipped alongside the prompts, and why it does not
    need a scalar filter -- every task is usable.
    """
    tasks = load_bird(bird_root)
    if db_ids:
        tasks = [t for t in tasks if t.db_id in db_ids]
    drawn = select(tasks, draw, seed=seed)
    schemas: dict[str, str] = {}

    rows: list[dict] = []
    for task in drawn:
        if task.db_id not in schemas:
            schemas[task.db_id] = schema_for(task.db_path)
        evidence = f"\nHint: {task.evidence}" if task.evidence else ""
        rows.append({
            "prompt": SQL_PROMPT_TEMPLATE.format(
                question=task.question, evidence=evidence,
                schema=schemas[task.db_id]),
            "answer": task.gold_sql,
            "db_id": task.db_id,
            "task": task.name,
            "tier": task.tier,
            "shape": task.shape,
        })

    header = {
        "corpus": "BIRD-SQL dev",
        "task": "sql_generation, scored by execution accuracy (set comparison)",
        "why": (
            "the scalar-answer variant was unanswerable: schema in the prompt, a data "
            "value as the answer, no rows. Solve rate structurally 0, so "
            "frac_reward_zero_std read 1.000 at step 0 and the probe aborted on its own "
            "prompt design. SQL generation is also the task the ~25% frontier estimate "
            "describes (SLM-SQL measures generation judged by execution)."
        ),
        "question_position": "first, before the schema, so truncation costs schema "
                             "detail and never the question",
        "databases_required": True,
        "db_ids": sorted({r["db_id"] for r in rows}),
        "drawn": len(drawn),
        "kept": len(rows),
        "seed": seed,
        "tiers": {t: sum(1 for r in rows if r["tier"] == t)
                  for t in sorted({r["tier"] for r in rows})},
        "distinct_shapes": len({r["shape"] for r in rows}),
    }
    return rows, header


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
    p.add_argument("--task", choices=("sql", "scalar"), default="sql",
                   help="`sql` (default): write the query, scored by execution. "
                        "`scalar`: the original answer-the-question variant, kept "
                        "because its failure is on the record -- it is unanswerable "
                        "without rows in the prompt.")
    p.add_argument("--shippable-dbs-only", action="store_true",
                   help="Restrict to the 7 BIRD dev databases totalling 82 MB, which "
                        "carry 922 tasks over 207 shapes and can ship as a dataset.")
    args = p.parse_args(argv)

    if args.task == "sql":
        rows, header = build_sql(
            args.bird, args.draw, args.seed,
            SHIPPABLE_DB_IDS if args.shippable_dbs_only else None)
    else:
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
