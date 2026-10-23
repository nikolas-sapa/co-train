"""Reference for scripted evidence capture, not model or trainer execution."""

from __future__ import annotations

import json
import shlex
import sqlite3
import tempfile
from pathlib import Path

from bench.fixture import materialize
from bench.loader import load_bird
from ptc.sql_arms import build_sql_arms


def main() -> None:
    # SHORTCUT: committed fixtures and one task, not the frozen research corpus.
    with tempfile.TemporaryDirectory(prefix="cotrain-replay-") as directory:
        root = Path(directory)
        task = load_bird(materialize(root / "corpus"))[0]
        pair = build_sql_arms(task)
        actions = {
            "ptc": (
                f"print(execute_sql(query={task.gold_sql!r}))",
                "print(execute_sql(query='SELECT FROM nowhere'))",
                "print('before'); print(execute_sql(query='SELECT FROM nowhere'))",
            ),
            "bash": (
                "execute_sql " + shlex.quote(task.gold_sql),
                "execute_sql 'SELECT FROM nowhere'",
            ),
        }
        observations = {}
        for arm, programs in actions.items():
            repeated = []
            for repeat in range(2):
                bindir = root / f"{arm}-{repeat}"
                repeated.append(tuple(
                    pair.run(arm, action, bindir=bindir) for action in programs
                ))
            # PROVES: same-arm observations are stable across fresh wrapper dirs,
            # including query errors and PTC output followed by rejection.
            assert repeated[0] == repeated[1], (arm, repeated)
            observations[arm] = repeated[0]
        # MISSING: no artifact binding, digest, admission budget or serialization.
        # ArmPair itself does not enforce its Budget. No token/model evidence.
        print(json.dumps({
            "origin": "scripted-reference",
            "sqlite_python": sqlite3.sqlite_version,
            "task": task.name,
            "observations": observations,
            "model_calls": 0,
        }, indent=2))


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("reference assertions require unoptimized Python")
    main()
