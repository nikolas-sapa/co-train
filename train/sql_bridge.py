"""Plain SQL inputs and a task-reset adapter for native environment discovery.

Execution and budgets belong to ``grpo_ptc.sql_environment``; SQL scoring belongs
to ``ex_reward.make_execution_reward``. This module only binds their existing
contracts to explicit dataset rows. It does not select a taskset, import training
frameworks, relax preflight, or establish a compatible training stack.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from bench.task import SqlTask
from train import ex_reward, grpo_ptc, guards


@dataclass(frozen=True)
class SQLTrainingInputs:
    """Prepared plain rows, native environment factory, and existing SQL reward.

    ``dataset_rows`` is deliberately not a Hugging Face Dataset. Converting it
    and launching a trainer remain the caller's responsibility, behind the
    project's unchanged preflight and stack guards.
    """

    dataset_rows: list[dict[str, Any]]
    environment_factory: Callable[[], _SQLEnvironment]
    reward: Callable[..., list[float]]
    max_tool_calling_iterations: int


@dataclass(frozen=True)
class _PreparedTask:
    """Frozen SqlTask and immutable prompt, never the public mutable row."""

    task: SqlTask
    prompt: str


def _require_same_database(task: SqlTask, db_root: pathlib.Path) -> None:
    """Refuse missing files or different tool/reward corpora before schema work."""
    tool_db = pathlib.Path(task.db_path)
    reward_db = pathlib.Path(ex_reward.db_path_for(db_root, task.db_id))
    for db in (tool_db, reward_db):
        if not db.is_file():
            raise FileNotFoundError(
                f"database {str(db)!r} for task {task.name!r} is not mounted"
            )
    if not tool_db.samefile(reward_db):
        raise ValueError(
            f"task {task.name!r} tool database {str(tool_db)!r} and reward "
            f"database {str(reward_db)!r} are not the same physical file"
        )


class _SQLEnvironment:
    """Composition, not inheritance: native discovery must not export PTC helpers."""

    def __init__(
        self,
        bindings: Mapping[str, _PreparedTask],
        db_root: pathlib.Path,
        root: pathlib.Path,
    ) -> None:
        self._bindings = bindings
        self._db_root = db_root
        self._root = root
        self._environment: grpo_ptc.PTCEnvironment | None = None

    @property
    def turns_used(self) -> int:
        return 0 if self._environment is None else self._environment.turns_used

    def reset(
        self,
        task_id: str | None = None,
        prompt: Any = None,
        answer: str | None = None,
        db_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Validate one prepared row and bind a fresh per-rollout SQL environment."""
        # Defaults let missing row metadata reach this invalidation too, instead
        # of Python rejecting it before the previous executor can be cleared.
        self._environment = None
        if not isinstance(task_id, str) or task_id not in self._bindings:
            raise ValueError(f"unknown prepared task_id: {task_id!r}")
        binding = self._bindings[task_id]
        expected_prompt = [{"role": "user", "content": binding.prompt}]
        if prompt != expected_prompt:
            raise ValueError(f"prompt does not match prepared task {task_id!r}")
        if answer != binding.task.gold_sql:
            raise ValueError(f"answer does not match prepared task {task_id!r}")
        if db_id != binding.task.db_id:
            raise ValueError(f"db_id does not match prepared task {task_id!r}")

        _require_same_database(binding.task, self._db_root)
        current_prompt, environment = grpo_ptc.sql_environment(binding.task, root=self._root)
        if current_prompt != binding.prompt:
            raise ValueError(f"database prompt changed for prepared task {task_id!r}")
        self._environment = environment
        return None

    def run_program(self, code: str):
        """Execute a Python program against the typed catalog.

        Args:
            code: The program.
        """
        if self._environment is None:
            raise RuntimeError("reset() must bind a prepared task before run_program()")
        return self._environment.step(code)


def _final_text(completion: Any) -> str:
    """Only an actual last assistant answer can supply the SQL prediction."""
    if isinstance(completion, str):
        return completion
    if not isinstance(completion, (list, tuple)) or not completion:
        return ""
    final = completion[-1]
    if not isinstance(final, Mapping) or final.get("role") != "assistant":
        return ""
    tool_calls = final.get("tool_calls")
    if tool_calls is not None and (not isinstance(tool_calls, list) or tool_calls):
        return ""
    content = final.get("content")
    return content if isinstance(content, str) else ""


def _native_reward(db_root: pathlib.Path) -> Callable[..., list[float]]:
    base_reward = ex_reward.make_execution_reward(db_root)

    def execution_reward(
        completions: Iterable[Any],
        answer: Sequence[str],
        db_id: Sequence[str],
        **kwargs: Any,
    ) -> list[float]:
        # Keep the base reward's strict zip, missing-DB exception, comparison
        # policy, and invalid-gold mapping. Empty predictions still reach it.
        return base_reward(
            completions=(_final_text(completion) for completion in completions),
            answer=answer,
            db_id=db_id,
            **kwargs,
        )

    return execution_reward


def prepare_sql_training(
    tasks: Iterable[SqlTask],
    db_root: str | pathlib.Path,
    *,
    root: pathlib.Path = guards.REPO_ROOT,
) -> SQLTrainingInputs:
    """Prepare only caller-supplied tasks, without sampling or reading a manifest."""
    tasks = tuple(tasks)
    if not tasks:
        raise ValueError("SQL training requires at least one explicit task")
    seen = set()
    for task in tasks:
        if not isinstance(task.name, str) or not task.name:
            raise ValueError("SQL training task IDs must be nonempty strings")
        if task.name in seen:
            raise ValueError(f"duplicate SQL training task ID: {task.name!r}")
        seen.add(task.name)

    # Finish every ID check before resolving databases or building any schema.
    db_root = pathlib.Path(db_root).resolve()
    root = pathlib.Path(root).resolve()
    for task in tasks:
        _require_same_database(task, db_root)
    max_turns = guards.eval_max_turns(root)

    bindings = {}
    rows = []
    for task in tasks:
        prompt, _ = grpo_ptc.sql_environment(task, root=root)
        bindings[task.name] = _PreparedTask(task=task, prompt=prompt)
        rows.append({
            "prompt": [{"role": "user", "content": prompt}],
            "task_id": task.name,
            "answer": task.gold_sql,
            "db_id": task.db_id,
        })
    private_bindings = MappingProxyType(bindings)

    def environment_factory() -> _SQLEnvironment:
        return _SQLEnvironment(private_bindings, db_root, root)

    return SQLTrainingInputs(
        dataset_rows=rows,
        environment_factory=environment_factory,
        reward=_native_reward(db_root),
        max_tool_calling_iterations=max_turns,
    )
