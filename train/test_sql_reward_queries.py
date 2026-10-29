"""Real training-reward integration, kept outside isolated bench test suites.

All database writes are fixture setup under pytest's temporary directory.
No model, network, corpus download, or scorer mock is needed.
"""

from __future__ import annotations

import sqlite3

import pytest

from train.ex_reward import make_execution_reward


EMPTY_SELECT = "SELECT value FROM items WHERE 0"
EMPTY_CTE = "WITH empty AS (SELECT value FROM items WHERE 0) SELECT * FROM empty"


@pytest.fixture
def reward_db(tmp_path):
    db_id = "fixture"
    db_dir = tmp_path / db_id
    db_dir.mkdir()
    conn = sqlite3.connect(db_dir / f"{db_id}.sqlite")
    try:
        conn.execute("CREATE TABLE items (value INTEGER)")
        conn.executemany("INSERT INTO items VALUES (?)", [(1,), (1,), (2,)])
        conn.commit()
    finally:
        conn.close()
    return tmp_path, db_id


@pytest.mark.parametrize("chat", [False, True], ids=["text", "chat"])
def test_real_training_reward_rejects_comment_only_prediction(reward_db, chat):
    root, db_id = reward_db
    reward = make_execution_reward(root)
    comment = "/* no answer; just a comment; */"
    completion = [{"role": "assistant", "content": comment}] if chat else comment
    # The matching control proves the actual DB resolved and empty queries work.
    control = f"```sql\n{EMPTY_CTE};\n```"
    assert reward(
        completions=[control, completion],
        answer=[EMPTY_SELECT, EMPTY_SELECT],
        db_id=[db_id, db_id],
    ) == [1.0, 0.0]


def test_the_frontier_scores_with_the_comparison_the_reward_trains_on():
    """Selected under multiset and trained under set, the retained band would describe a
    reward the run never optimises."""
    import importlib
    import inspect

    from train import ex_reward

    frontier = importlib.import_module("bench.frontier.probe")
    want = inspect.signature(ex_reward.make_execution_reward).parameters["compare"].default
    assert inspect.signature(frontier.probe).parameters["compare"].default == want
