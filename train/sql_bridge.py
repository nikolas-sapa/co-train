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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bench.score import ExResult
    from ptc.sql_qa import QaChannel
    from train.sql_capture import SqlCapture, _CaptureSession
    from train.sql_episodes import EpisodeIds
    from train.sql_reporting import ReportingConfig, ReportingSnapshot

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
        *,
        reporting: ReportingConfig | None = None,
        capture_ids: Callable[[str], EpisodeIds] | None = None,
        capture_sink: Callable[[SqlCapture], None] | None = None,
    ) -> None:
        self._bindings = bindings
        self._db_root = db_root
        self._root = root
        self._reporting = reporting
        self._environment: grpo_ptc.PTCEnvironment | None = None
        self._channel: QaChannel | None = None
        self._capture_ids = capture_ids
        self._capture_sink = capture_sink
        self._session: _CaptureSession | None = None
        self._binding: _PreparedTask | None = None
        self._published = False
        self._sink_failed = False
        self._reward_consumed = False

    @property
    def turns_used(self) -> int:
        if self._session is not None:
            return self._session._turns_used
        return 0 if self._environment is None else self._environment.turns_used

    @property
    def reporting_snapshot(self) -> ReportingSnapshot | None:
        """Current bounded allegations, not verified claims or scored success.

        Derive immutable bytes on access, including after a program failure.
        Keep no history and leave the original execution semantics untouched.
        """
        if self._session is not None:
            return self._session.reporting_snapshot
        if self._reporting is None or self._channel is None:
            return None
        from train.sql_reporting import snapshot_channel

        return snapshot_channel(self._channel, self._reporting, arm="ptc")

    def reset(
        self,
        task_id: str | None = None,
        prompt: Any = None,
        answer: str | None = None,
        db_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Validate one prepared row and bind a fresh per-rollout SQL environment."""
        if self._sink_failed:
            raise RuntimeError("capture sink failed; environment cannot be reused")
        if self._session is not None and not self._published:
            self._abort_rollout()
        # Defaults let missing row metadata reach this invalidation too, instead
        # of Python rejecting it before the previous executor can be cleared.
        self._environment = None
        self._channel = None
        self._session = None
        self._binding = None
        self._published = False
        self._reward_consumed = False
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
        if self._capture_ids is not None:
            from train.sql_capture import start_capture

            session = start_capture(
                binding.task, ids=self._capture_ids(task_id), allow_execution=True,
                reporting=self._reporting, root=self._root,
            )
            if session.prompt != binding.prompt:
                raise ValueError(f"database prompt changed for prepared task {task_id!r}")
            self._session = session
            self._binding = binding
            return None
        channel = None
        if self._reporting is None:
            current_prompt, environment = grpo_ptc.sql_environment(binding.task, root=self._root)
        else:
            from train.sql_reporting import make_channel

            channel = make_channel(self._reporting)
            current_prompt, environment = grpo_ptc.sql_environment(
                binding.task, root=self._root, qa=channel,
            )
        if current_prompt != binding.prompt:
            raise ValueError(f"database prompt changed for prepared task {task_id!r}")
        self._environment = environment
        self._channel = channel
        return None

    def run_program(self, code: str):
        """Execute a Python program against the typed catalog.

        Args:
            code: The program.
        """
        if self._session is not None:
            self._require_rollout()
            try:
                return self._session.step(code)
            except BaseException:
                # Keep the original tool exception if diagnostic retention fails.
                try:
                    self._abort_rollout()
                except BaseException:
                    pass
                raise
        if self._environment is None:
            raise RuntimeError("reset() must bind a prepared task before run_program()")
        return self._environment.step(code)

    def _require_rollout(self) -> None:
        if self._session is None or self._published or self._sink_failed:
            raise RuntimeError("no open capture rollout")

    def _publish(self, capture: SqlCapture) -> SqlCapture:
        self._require_rollout()
        # A failed caller sink is still an attempt: never retry or resume it.
        self._published = True
        try:
            self._capture_sink(capture)
        except BaseException:
            self._sink_failed = True
            raise
        return capture

    def _abort_rollout(self) -> SqlCapture:
        self._require_rollout()
        if self._session._state == "invalidated":
            capture = self._session.snapshot
        else:
            capture = self._session.abort()
        return self._publish(capture)

    def _finish_rollout(
        self, completion: Any, *, scored: tuple[str, ExResult] | None = None,
    ) -> SqlCapture:
        self._require_rollout()
        if not _has_final_text(completion) or self._session._state == "invalidated":
            return self._abort_rollout()
        try:
            text = _final_text(completion)
            if scored is None:
                capture = self._session.finish(text)
            else:
                extracted, result = scored
                capture = self._session._finish_scored(
                    text, extracted_sql=extracted, result=result,
                )
            return self._publish(capture)
        except BaseException:
            try:
                self._abort_rollout()
            except BaseException:
                pass
            raise


def _has_final_text(completion: Any) -> bool:
    if isinstance(completion, str):
        return True
    if not isinstance(completion, (list, tuple)) or not completion:
        return False
    final = completion[-1]
    if not isinstance(final, Mapping) or final.get("role") != "assistant":
        return False
    tool_calls = final.get("tool_calls")
    if tool_calls is not None and (not isinstance(tool_calls, list) or tool_calls):
        return False
    return isinstance(final.get("content"), str)


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


def _native_reward(
    db_root: pathlib.Path, *,
    capture_bindings: Mapping[str, _PreparedTask] | None = None,
) -> Callable[..., list[float]]:
    base_reward = ex_reward.make_execution_reward(db_root)

    def execution_reward(
        completions: Iterable[Any],
        answer: Sequence[str],
        db_id: Sequence[str],
        **kwargs: Any,
    ) -> list[float]:
        if capture_bindings is not None:
            completions = tuple(completions)
            answer, db_id = tuple(answer), tuple(db_id)
            try:
                environments = tuple(kwargs["environments"])
                task_ids = tuple(kwargs["task_id"])
                prompts = tuple(kwargs["prompts"])
            except (KeyError, TypeError) as exc:
                raise ValueError("capture reward requires aligned native associations") from exc
            count = len(completions)
            if any(len(values) != count for values in (
                answer, db_id, environments, task_ids, prompts,
            )):
                raise ValueError("capture reward row lengths differ")
            if len({id(environment) for environment in environments}) != count:
                raise ValueError("capture reward requires distinct environment instances")
            # Validate the entire positional association before the first score.
            # Task IDs alone cannot identify repeated-task pooled instances.
            for environment, task_id, prompt, gold, database in zip(
                environments, task_ids, prompts, answer, db_id, strict=True,
            ):
                if type(environment) is not _SQLEnvironment:
                    raise TypeError("capture reward requires the exact SQL adapter")
                if not isinstance(task_id, str) or task_id not in capture_bindings:
                    raise ValueError("capture reward task is not prepared")
                binding = capture_bindings[task_id]
                if (
                    environment._bindings is not capture_bindings
                    or environment._binding is not binding
                    or environment._session is None
                    or environment._sink_failed
                    or environment._reward_consumed
                    or environment._session._state not in ("active", "invalidated")
                    or (environment._published
                        and environment._session._state != "invalidated")
                ):
                    raise ValueError("capture reward environment/reset binding differs")
                if (
                    prompt != [{"role": "user", "content": binding.prompt}]
                    or gold != binding.task.gold_sql
                    or database != binding.task.db_id
                ):
                    raise ValueError("capture reward row metadata differs from reset")
            results = ex_reward._execution_results(
                (_final_text(completion) for completion in completions),
                answer, db_id, db_root=db_root,
            )
            out = []
            try:
                for completion, environment in zip(completions, environments, strict=True):
                    environment._reward_consumed = True
                    if (
                        environment._session._state == "active"
                        and _has_final_text(completion)
                    ):
                        environment._session._admit_scored_final(_final_text(completion))
                    _, extracted, result = next(results)
                    if not environment._published:
                        environment._finish_rollout(completion, scored=(extracted, result))
                    out.append(float(result.score) if result.valid else 0.0)
            except BaseException:
                # Earlier rows may already be retained. Failed/unprocessed rows
                # get diagnostics only; retention failure cannot mask the cause.
                if not any(environment._sink_failed for environment in environments):
                    for environment in environments:
                        if not environment._published:
                            try:
                                environment._abort_rollout()
                            except BaseException:
                                break
                raise
            return out
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
    reporting: ReportingConfig | None = None,
    capture_ids: Callable[[str], EpisodeIds] | None = None,
    capture_sink: Callable[[SqlCapture], None] | None = None,
) -> SQLTrainingInputs:
    """Prepare explicit tasks, optionally collecting per-reset defect allegations.

    Reporting uses the existing exact configuration and in-memory collector.
    Disabled calls neither import reporting nor change the SQL builder call.
    """
    if (capture_ids is None) != (capture_sink is None):
        raise ValueError("capture_ids and capture_sink must be supplied together")
    if capture_ids is not None:
        if not callable(capture_ids) or not callable(capture_sink):
            raise TypeError("capture_ids and capture_sink must be callable")
        if reporting is None:
            raise ValueError("capture requires reporting")
    if reporting is not None:
        from train.sql_reporting import make_channel, validate_config

        validate_config(reporting)
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
        if reporting is None:
            prompt, preparation_environment = grpo_ptc.sql_environment(task, root=root)
        else:
            # This temporary channel derives the real enabled prompt only.
            # Neither it nor its executor is retained as a rollout binding.
            prompt, preparation_environment = grpo_ptc.sql_environment(
                task, root=root, qa=make_channel(reporting),
            )
        del preparation_environment
        bindings[task.name] = _PreparedTask(task=task, prompt=prompt)
        rows.append({
            "prompt": [{"role": "user", "content": prompt}],
            "task_id": task.name,
            "answer": task.gold_sql,
            "db_id": task.db_id,
        })
    private_bindings = MappingProxyType(bindings)

    def environment_factory() -> _SQLEnvironment:
        return _SQLEnvironment(
            private_bindings, db_root, root, reporting=reporting,
            **({"capture_ids": capture_ids, "capture_sink": capture_sink}
               if capture_ids is not None else {}),
        )

    return SQLTrainingInputs(
        dataset_rows=rows,
        environment_factory=environment_factory,
        reward=_native_reward(
            db_root,
            **({"capture_bindings": private_bindings} if capture_ids is not None else {}),
        ),
        max_tool_calling_iterations=max_turns,
    )
