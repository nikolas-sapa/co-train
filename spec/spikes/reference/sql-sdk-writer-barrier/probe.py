"""SOURCE-ONLY feasibility evidence. Does not import or execute the SDK.

PROVES: exact installed source topology and empty-gather scheduling semantics.
SHORTCUT: source assertions, not Agent/eval/writer runtime qualification.
MISSING FROM THIS CLI: strong late-sibling race and all runtime/native proof.
Separate composition tests live in ptc/test_owned_sql_sdk_writer_barrier_probe.py.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sysconfig


ROOT = Path(__file__).resolve().parents[4]
SDK = Path(sysconfig.get_path("purelib")) / "verifiers/v1"


def _function(tree, name, owner=None):
    body = tree.body
    if owner is not None:
        cls, = [node for node in body
                if isinstance(node, ast.ClassDef) and node.name == owner]
        body = cls.body
    result, = [node for node in body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == name]
    return result


def _awaits(node):
    return [ast.unparse(child.value) for child in ast.walk(node)
            if isinstance(child, ast.Await)]


def _writer_edge(tree):
    run = _function(tree, "run", "OwnedSqlEnv")
    return _awaits(run).count("_settle(scope.cleanup_task)") == 1


async def empty_gather_semantics():
    """PROVES only stdlib empty gather returns without a scheduler turn."""
    observed = []
    loop = asyncio.get_running_loop()
    loop.call_soon(observed.append, "scheduled")
    future = asyncio.gather()
    assert future.done()
    assert await future == []
    assert observed == []
    await asyncio.sleep(0)
    assert observed == ["scheduled"]
    return {"done_before_await": True, "scheduler_turns_during_await": 0}


def audit():
    paths = {
        "root": ROOT / "cotrain_owned_sql.py",
        "harness": SDK / "harness.py",
        "decorators": SDK / "utils/decorators.py",
        "errors": SDK / "errors.py",
        "rollout": SDK / "rollout.py",
        "agent": SDK / "agent.py",
        "task": SDK / "task.py",
        "env": SDK / "env.py",
        "runner": SDK / "cli/eval/runner.py",
        "writer": SDK / "cli/output.py",
    }
    sources = {key: path.read_text() for key, path in paths.items()}
    trees = {key: ast.parse(source) for key, source in sources.items()}
    assert importlib.metadata.version("verifiers") == "0.3.2.dev137"
    harness = _function(trees["harness"], "score", "Harness")
    invoke_all = _function(trees["decorators"], "invoke_all")
    boundary = _function(trees["errors"], "boundary")
    owned_harness = _function(trees["root"], "score", "OwnedSqlHarness")
    task_score = _function(trees["root"], "score", "OwnedSqlTask")
    assert _awaits(harness) == ["invoke_all(fns, available)"]
    assert _awaits(invoke_all) == [
        "asyncio.gather(*(invoke(fn, available) for fn in fns))"]
    assert _awaits(boundary) == []
    assert _awaits(owned_harness) == ["super().score(trace, runtime)"]
    body, = [node for node in owned_harness.body if isinstance(node, ast.Try)]
    assert ast.unparse(body.body[1]) == (
        "scope.check(harness=self, trace=trace, runtime=runtime)")
    check_hooks = _function(trees["root"], "_check_hooks")
    forbidden = ast.parse(
        '("metric", "reward", "stop", "intercept")', mode="eval").body
    assert any(ast.dump(node) == ast.dump(forbidden)
               for node in ast.walk(check_hooks))
    assert _awaits(task_score)[:3] == [
        "scope.scorer.score_sql(predicted)",
        "_join_resource(scope, scope.scorer)",
        "scope.harness_done.wait()",
    ]
    assert _writer_edge(trees["root"])
    owned_env, = [node for node in trees["root"].body
                  if isinstance(node, ast.ClassDef) and node.name == "OwnedSqlEnv"]
    assert not any(getattr(node, "name", None) == "__aexit__"
                   for node in owned_env.body)
    run = _function(trees["root"], "run", "OwnedSqlEnv")
    assert "scope.closes.start_all()" in ast.unparse(run)
    assert "scope.cleanup_task = asyncio.create_task(_drain_scope(scope))" in ast.unparse(run)
    assert "if scope.cleanup_task.done():" in ast.unparse(run)
    run_slot = _function(trees["env"], "run_slot", "Env")
    assert "on_complete(episode)" in _awaits(run_slot)
    run_eval = _function(trees["runner"], "run_eval")
    assert "append_episode(out, episode, write_lock)" in _awaits(run_eval)
    writer = _function(trees["writer"], "append_episode")
    assert "asyncio.to_thread(write_episode, results_dir, episode)" in _awaits(writer)
    return {
        "kind": "SOURCE_ONLY_NOT_RUNTIME_QUALIFICATION",
        "late_sibling": "BLOCKED_NO_ALLOWED_ORIGINAL_HARNESS_SUSPENSION",
        "writer": "ORIGINAL_ENV_SETTLE_EDGE_EXISTS_RUNTIME_SENSITIVITY_UNMEASURED",
        "source_files": len(paths),
        "sources": {
            key: {"path": ("cotrain_owned_sql.py" if key == "root" else
                           "verifiers/v1/" + path.relative_to(SDK).as_posix()),
                  "sha256": hashlib.sha256(
                sources[key].encode()).hexdigest()}
            for key, path in paths.items()
        },
    }


def main():
    result = audit()
    result["stdlib_empty_gather"] = asyncio.run(empty_gather_semantics())
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
