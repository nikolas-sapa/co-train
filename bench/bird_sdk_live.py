"""Private question/schema-only SQL plugin using original SDK execution."""
from __future__ import annotations

import asyncio
from typing import Literal

from verifiers.v1.agent import _EpisodeAgent
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.utils.decorators import reward

from bench.bird_sdk_driver import SqlScoreReceipt
from bench.score import extract_sql
from ptc import sql_owned_program
from ptc.harness import PTCHarness, PTCHarnessConfig, _close_program_runner
from ptc.sql_arms import TaskView, prompt_for
from train.sql_live_reuse import (
    _ACTIVE_ASSOCIATION, _Association, _require, _scope, _valid_result,
)

__all__ = ["PTCHarness", "BirdSqlTaskset", "BirdSqlEnv"]


class BirdSqlTask(Task[TaskData]):
    async def setup(self, trace, runtime):
        association = _ACTIVE_ASSOCIATION.get()
        _require(type(association) is _Association and association.task is self
                 and association.trace is None, "original SQL setup association required")
        association.check()
        association.trace = trace
        association.original_trace = trace
        association.check_trace(trace)

    @reward
    async def execution_accuracy(self, trace):
        association = _ACTIVE_ASSOCIATION.get()
        _require(type(association) is _Association and association.task is self,
                 "original SQL scoring association required")
        association.check()
        association.check_trace(trace)
        _require(association.receipt is None and association.result is None,
                 "original SQL scoring already consumed")
        association.scorer.admit()
        result = await association.scorer.score_sql(extract_sql(trace.last_reply or ""))
        association.check()
        association.check_trace(trace)
        _valid_result(result)
        association.result = result
        association.receipt = SqlScoreReceipt(trace, result)
        return result.score


class BirdSqlTaskset(Taskset[BirdSqlTask, TasksetConfig]):
    def __init__(self, config):
        scope = _scope()
        _require(config is scope.config.env.taskset and scope.taskset is None,
                 "original SQL taskset configuration required")
        super().__init__(config)
        scope.taskset = self
        self._scope = scope
        self._tasks = None

    def head(self, num_tasks):
        scope = _scope()
        _require(type(self) is BirdSqlTaskset and scope is self._scope
                 and scope.taskset is self and self.config is scope.config.env.taskset
                 and self.transform is None and self.system_prompt is None
                 and self.INFINITE is False
                 and type(num_tasks) is int and num_tasks == len(scope.private),
                 "canonical full SQL taskset selection required")
        return self

    def load(self):
        scope = _scope()
        _require(scope is self._scope and scope.taskset is self,
                 "original SQL taskset association differs")
        if self._tasks is None:
            tasks = []
            for row in scope.plan.inputs:
                view = TaskView(
                    name=row.task.name, question=row.task.question,
                    db_path="", gold_sql="", evidence="")
                data = TaskData(
                    name=view.name, prompt=prompt_for(
                        view, "ptc", schema=row.schema,
                        max_rows=scope.instrument.action_max_rows))
                task = BirdSqlTask(data, self.config.task)
                scope.register(task)
                tasks.append(task)
            self._tasks = tuple(tasks)
        for task in self._tasks:
            scope.check_task(task)
        return self._tasks


class BirdSqlEnvConfig(SingleAgentEnvConfig):
    id: Literal["cotrain_bird_sql_live"] = "cotrain_bird_sql_live"
    agent: AgentConfig = AgentConfig(
        harness=PTCHarnessConfig(id="cotrain_bird_sql_harness"))


class BirdSqlEnv(Env[BirdSqlEnvConfig]):
    def __init__(self, config):
        scope = _scope()
        _require(config is scope.config.env, "original SQL environment configuration required")
        super().__init__(config)
        self._scope = scope

    async def run(self, task, agents):
        scope = _scope()
        _require(scope is self._scope and type(agents.agent) is _EpisodeAgent,
                 "original SQL episode agent required")
        scope.check_task(task)
        _require(task.data.name not in scope.associations, "SQL task rollout already consumed")
        association = _Association(scope, task, agents.agent)
        scope.associations[task.data.name] = association
        token = _ACTIVE_ASSOCIATION.set(association)
        body_cancel = None
        try:
            sql_owned_program.build_owned_sql_program_harness(
                association.harness.config, data=task.data, task=association.row.task,
                executor=scope.executor, db_sha256=association.row.db_sha256,
                max_rows=scope.instrument.action_max_rows,
                approved_skill=scope.approved_skill, reuse_case=association.row.reuse_case,
                original_scorer_instrument=(
                    scope.instrument if scope.approved_skill is not None else None),
                existing_harness=association.harness, host_authority=association.callback)
            association.check()
            trace = await agents.agent.run(task)
            association.check()
            association.check_trace(trace)
            _require(trace.ok and association.receipt is not None
                     and association.receipt.trace is trace,
                     "original SQL rollout did not produce a valid score")
        except asyncio.CancelledError as exc:
            body_cancel = exc
            raise
        finally:
            association.live = False
            try:
                try:
                    await _close_program_runner(association.scorer)
                except asyncio.CancelledError:
                    if body_cancel is not None:
                        raise body_cancel
                    raise
            finally:
                _ACTIVE_ASSOCIATION.reset(token)

    async def finalize(self, task, episode):
        scope = _scope()
        _require(scope is self._scope, "original SQL environment scope differs")
        scope.check_task(task)
        association = scope.associations[task.data.name]
        association.check(retired=True)
        _require(task.data.name not in scope.completed
                 and episode.task.data is task.data and len(episode.traces) == 1
                 and episode.traces[0] is association.trace,
                 "original SQL episode join differs")
        scope.completed[task.data.name] = episode
