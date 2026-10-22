"""PROVES: pinned native TRL tool execution masks a real SQL observation.

SHORTCUT: one fixed SQLite task; tokenizer suffix and generation are fixtures.
MISSING: trainer construction, Unsloth patches, real tokenization/log-probabilities,
model loading, gradients, checkpoints, CUDA and training. No model is run.
The supplied upstream source is parsed, and only the verified method is executed.
"""

import argparse
import ast
import hashlib
import inspect
import json
import sqlite3
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace

from bench.task import SqlTask
from train.grpo_ptc import THE_TOOL_SCHEMA, sql_environment
from transformers.utils.chat_template_utils import get_json_schema


NATIVE_LOOP_SHA256 = "3a513812b6988bb1bb4cc9cceee21ebf343b63f6810c7d12eb693af856027f79"
PROGRAM = 'rows = execute_sql(query="SELECT amount FROM readings")\nprint(rows[0]["amount"])'


class FixtureEnvironment:
    # SHORTCUT: bound to one known task, unlike the production task-id lookup.
    def __init__(self, task):
        self._task = task
        self._environment = None

    def reset(self, **kwargs):
        self._prompt, self._environment = sql_environment(self._task)
        return None

    def run_program(self, code: str):
        """Execute a Python program against the typed catalog.

        Args:
            code: The program.
        """
        return self._environment.step(code)


def main():
    if not __debug__:
        raise RuntimeError("This assertion-based reference check requires unoptimized Python")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trainer-source", required=True, type=Path)
    parser.add_argument("--break-mask", action="store_true")
    parser.add_argument("--production-bridge", action="store_true")
    args = parser.parse_args()
    source = args.trainer_source.read_text()
    trainer = next(node for node in ast.parse(source).body
                   if isinstance(node, ast.ClassDef) and node.name == "GRPOTrainer")
    method = next(node for node in trainer.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_tool_call_loop")
    body = textwrap.dedent(ast.get_source_segment(source, method, padded=True))
    if hashlib.sha256(body.encode()).hexdigest() != NATIVE_LOOP_SHA256:
        raise ValueError("The supplied native tool loop does not match pinned TRL 1.13.0")
    if args.break_mask:
        old = "tool_mask[idx_with_tool] += [0] * tool_length"
        assert body.count(old) == 1
        body = body.replace(old, "tool_mask[idx_with_tool] += [1] * tool_length")
    namespace = {
        # SHORTCUT: fixed parsed assistant response, not real tokenizer validation.
        "parse_response": lambda *a, **kw: {
            "role": "assistant", "content": "```sql\nSELECT amount FROM readings\n```",
        },
    }
    exec(compile(body, "<verified-trl-1.13-tool-loop>", "exec"), namespace)

    with tempfile.TemporaryDirectory(prefix="trl-sql-spike-") as directory:
        database = Path(directory) / "fixture" / "fixture.sqlite"
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE readings (amount INTEGER)")
            connection.execute("INSERT INTO readings VALUES (17)")
        task = SqlTask(
            name="fixture", question="What amount is recorded?", evidence="",
            gold_sql="SELECT amount FROM readings /* PRIVATE_GOLD */",
            db_id="fixture", db_path=str(database), tier="simple",
            tier_source="derived", shape="fixture", coarse_shape="fixture",
            source="fixture",
        )
        if args.production_bridge:
            from train.sql_bridge import prepare_sql_training

            prepared = prepare_sql_training([task], directory)
            environment = prepared.environment_factory()
            row = prepared.dataset_rows[0]
            assert environment.reset(**row) is None
            prompt = row["prompt"]
        else:
            environment = FixtureEnvironment(task)
            assert environment.reset(task_id=task.name) is None
            prompt = [{"role": "user", "content": environment._prompt}]
        methods = [member for name, member in inspect.getmembers(
            environment, predicate=inspect.ismethod,
        ) if name not in {"reset", "get_reward"} and not name.startswith("_")]
        assert [get_json_schema(method) for method in methods] == [THE_TOOL_SCHEMA]
        assert "PRIVATE_GOLD" not in json.dumps(prompt)
        native = SimpleNamespace(
            max_tool_calling_iterations=8, max_completion_length=3072,
            _sync_tool_dicts=[{"run_program": environment.run_program}],
            _async_tool_dicts=[{}], use_vllm=False, _is_vlm=False,
            model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=4096)),
            _tokenizer=None,
            # SHORTCUT: exact known external suffix and synthetic generated tokens.
            _get_tool_suffix_ids=lambda messages: [50, 51],
            _generate_single_turn=lambda *a, **kw: ([[7, 8]], [[-0.7, -0.8]]),
        )
        tool_call = {"type": "function", "function": {
            "name": "run_program", "arguments": {"code": PROGRAM},
        }}
        completion = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
        result = namespace["_tool_call_loop"](
            native, [prompt],
            [[101, 102]], [[1, 2]], [[completion]], [[-0.1, -0.2]], None, {},
        )
        mask, messages, ids, logprobs, calls, failures, images = result
        assert messages[0][1]["content"].strip() == "17"
        assert calls == 1
        if not args.production_bridge:
            assert environment._environment.turns_used == calls
        assert failures == 0
        assert ids == [[1, 2, 50, 51, 7, 8]]
        assert mask == [[1, 1, 0, 0, 1, 1]], mask
        assert logprobs == [[-0.1, -0.2, 0.0, 0.0, -0.7, -0.8]]
        reward = None
        if args.production_bridge:
            reward = prepared.reward(
                completions=messages, answer=[row["answer"]], db_id=[row["db_id"]],
            )
            assert reward == [1.0]
        print(json.dumps({
            "native_loop_sha256": NATIVE_LOOP_SHA256,
            "production_bridge": args.production_bridge,
            "discovered_tools": 1, "real_sql_value": 17, "executions": calls,
            "tool_mask": mask, "logprobs": logprobs,
            "execution_reward": reward,
            "models_loaded": 0, "training_steps": 0,
        }, indent=2))


if __name__ == "__main__":
    main()
