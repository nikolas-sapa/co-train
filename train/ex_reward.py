"""Execution-accuracy reward for the dead-group probe.

Separate module because `dead_group_probe.exact_match_reward` is pinned by tests and
is the right reward for a self-contained task. This one exists because the probe's
first real run proved the task was not self-contained.

**What went wrong, so it is not repeated.** `bench/make_probe_prompts.py` built prompts
carrying the database SCHEMA and asked for a data VALUE -- "how many comments were added
to the post with the highest score?", answer 35 -- with no rows in the prompt. The model
could not obtain that answer at any skill level, so the solve rate was structurally 0,
and `frac_reward_zero_std` read **1.000** at step 0 and aborted. That is exactly what
p=0 predicts (`0**G + 1**G == 1`), so the probe measured the prompt design, not the
reward's geometry.

The deeper error was transplanting a number across tasks: the ~25% frontier estimate in
pre-registration A8 comes from SLM-SQL, which measures **SQL generation judged by
execution**. Applying it to "answer from a schema you cannot query" borrowed a figure
from a different task. This reward restores the task the figure describes: the model
writes SQL, the database executes it, and the answer is scored by whether the result set
matches the gold query's.

Still binary -- `execution_accuracy` returns 1.0 or 0.0 -- so the probe's
`assert_binary_reward` premise and `zero_advantage_fraction`'s `p**G + (1-p)**G` model
both still hold.
"""

from __future__ import annotations

import pathlib
from typing import Any, Iterable, Sequence

from bench.score import MAX_ROWS, execution_accuracy, extract_sql
from bench.task import SqlTask

# Where the shipped database subset lands. On Kaggle a dataset mounts read-only under
# /kaggle/input/<slug>/; locally it is the extracted BIRD dev root. Passed explicitly
# rather than read from the environment, so a run cannot silently score against a
# different corpus than the one its prompts were drawn from.
DB_DIRNAME = "dev_databases"


def db_path_for(db_root: str | pathlib.Path, db_id: str) -> str:
    """Resolve one database, accepting both layouts this corpus arrives in.

    BIRD's own archive nests them under `dev_databases/`. **A Kaggle dataset does
    not**: uploading with `--dir-mode zip` makes Kaggle extract the archive and mount
    the contents at the dataset root, so the same files land at
    `<root>/<db_id>/<db_id>.sqlite` with that segment gone. Measured, not assumed --
    `kaggle datasets files` lists `california_schools/california_schools.sqlite`.

    Hard-coding either layout means the reward raises on the other, and since a
    missing database is the one condition this reward refuses to score as a policy
    failure, that would turn a mount-path detail into an aborted run.
    """
    root = pathlib.Path(db_root)
    for candidate in (root / DB_DIRNAME / db_id / f"{db_id}.sqlite",
                      root / db_id / f"{db_id}.sqlite"):
        if candidate.is_file():
            return str(candidate)
    # Neither exists: return the canonical one so the caller's error names the layout
    # the corpus is supposed to have, and let that caller raise.
    return str(root / DB_DIRNAME / db_id / f"{db_id}.sqlite")


def make_execution_reward(db_root: str | pathlib.Path,
                          *, timeout_s: float = 30.0,
                          max_rows: int = MAX_ROWS,
                          compare: str = "set") -> Any:
    """Build the reward closure. `db_root` must hold every `db_id` the prompts name.

    `compare="set"` matches official BIRD `evaluation.py`, which is what keeps a number
    from this probe comparable to the published figures that site the frontier band.

    A missing database raises rather than scoring 0: a corpus that is not mounted would
    otherwise read as a policy that cannot answer, which is the same confound in a new
    costume.
    """
    root = pathlib.Path(db_root)

    def execution_reward(completions: Iterable[Any],
                         answer: Sequence[str],
                         db_id: Sequence[str],
                         **_: Any) -> list[float]:
        out: list[float] = []
        for completion, gold_sql, this_db in zip(completions, answer, db_id,
                                                 strict=True):
            text = (completion if isinstance(completion, str)
                    else completion[-1]["content"])
            db = db_path_for(root, this_db)
            if not pathlib.Path(db).is_file():
                raise FileNotFoundError(
                    f"database {db!r} is not mounted. Scoring 0 here would read as a "
                    "policy that cannot answer -- the confound this reward exists to "
                    "remove. Mount the dataset or fix --db-root."
                )
            task = SqlTask(
                name="probe", question="", evidence="", gold_sql=gold_sql,
                # "annotated" because BIRD labels its own difficulty; `SqlTask`
                # validates this field and rejects anything else. Neither tier nor
                # shape affects EX scoring -- the scorer reads db_path and gold_sql
                # only -- but the dataclass is the contract and it is not bypassed.
                db_id=this_db, db_path=db, tier="simple", tier_source="annotated",
                shape="", coarse_shape="", source="bird",
            )
            # `extract_sql` first: the scorer deliberately does not unwrap fences, and
            # a policy that answers in a ```sql block must not read as a failure.
            result = execution_accuracy(extract_sql(text), task,
                                        timeout_s=timeout_s, max_rows=max_rows,
                                        compare=compare)
            # A defective GOLD is not a wrong prediction. `valid is False` means the
            # task is broken; it must not be scored as the policy's failure, so it is
            # dropped to 0 only after being surfaced -- the probe's own void handling
            # is what should see these, and 2 of BIRD dev's 1534 golds never terminate.
            out.append(float(result.score) if result.valid else 0.0)
        return out

    execution_reward.__name__ = "execution_reward"
    return execution_reward
