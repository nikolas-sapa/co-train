"""Task-local SQL leaf for original Bash composition, not a shell runtime.

The original broker/controller remain unqualified. This leaf adds binding and
invalidity fences, not native authority, a listener, scoring or a policy loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.task import Task, TaskData

from bench.task import SqlTask
from ptc.bird_sql_broker import (
    SqlBrokerError, SqlBrokerRetirementPending, TaskSqlBroker, TaskSqlBrokerConfig,
)
from ptc.bird_sql_worker import QueryWorkerResult, encode_query_request
from ptc.bird_sql_worker_controller import QueryWorkerController
from ptc.sql_isolation import canonical_json_bytes
from train.sql_episodes import InstrumentSettings, _validate_instrument

__all__ = [
    "BashSqlBinding", "BashSqlError", "BashSqlCleanupPending", "public_bash_prompt",
]

_BROKER_QUERY = TaskSqlBroker.query
_BROKER_CLOSE = TaskSqlBroker.aclose
_BROKER_SETTLE = TaskSqlBroker.wait_local_settlement


class BashSqlError(RuntimeError):
    """Invalid infrastructure/action, never an execution-accuracy reward."""


class BashSqlCleanupPending(BashSqlError):
    """Original owner retirement remains unresolved."""


def _digest(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def public_bash_prompt(question: str, schema: str) -> str:
    if type(question) is not str or type(schema) is not str:
        raise BashSqlError("public question and schema required")
    return f"Question:\n{question}\n\nSchema:\n{schema}"


class BashSqlBinding:
    """Host-only association; no serialization into TaskData or model tools.

    Action scopes count original tool dispatches, not SQL queries. The shared
    host must scope ALL tools, including edit, and must not expose the raw broker.
    """

    def __init__(
        self, *, task: Task, sql_task: SqlTask, instrument: InstrumentSettings,
        harness: BashHarness, broker_config: TaskSqlBrokerConfig,
        db_sha256: str, db_size_bytes: int, schema: str,
    ):
        try:
            if (not isinstance(task, Task) or type(task.data) is not TaskData
                    or type(sql_task) is not SqlTask
                    or type(harness) is not BashHarness
                    or type(harness.config) is not BashHarnessConfig
                    or type(broker_config) is not TaskSqlBrokerConfig):
                raise ValueError("concrete task binding required")
            _validate_instrument(instrument)
            broker_config.__post_init__()
            limits = broker_config.controller.worker.limits
            if (task.data.name != sql_task.name or not sql_task.name
                    or task.data.skills or harness.config.skills
                    or limits.action_max_rows != instrument.action_max_rows
                    or limits.query_timeout_s != instrument.wrapper_timeout_s
                    or type(sql_task.db_path) is not str
                    or not os.path.isabs(sql_task.db_path)
                    or os.path.normpath(sql_task.db_path) != sql_task.db_path):
                raise ValueError("binding bounds differ")
            public = task.data.model_dump(mode="python")
            expected = TaskData(
                idx=task.data.idx, name=sql_task.name,
                prompt=public_bash_prompt(sql_task.question, schema))
            if (public != expected.model_dump(mode="python")
                    or len(canonical_json_bytes(public)) > 65536):
                raise ValueError("public data exceeds bound")
            seal = _digest((public, sql_task, instrument,
                            harness.config.model_dump(mode="python"), broker_config))
            owner = TaskSqlBroker(
                config=broker_config, task_identity=task,
                host_db=Path(sql_task.db_path), expected_db_sha256=db_sha256,
                expected_db_size_bytes=db_size_bytes)
            executor_validator = QueryWorkerController(
                config=broker_config.controller, host_db=owner._host_db)
            executor_validator._pins = executor_validator._identities()
        except Exception:
            raise BashSqlError("invalid Bash SQL binding") from None
        self._task = self._task_owner = task
        self._data = task.data
        self._sql_task = self._sql_owner = sql_task
        self._instrument = self._instrument_owner = instrument
        self._harness = self._harness_owner = harness
        self._config = harness.config
        self._broker_config = broker_config
        self._settlement_timeout = broker_config.close_timeout_s
        self._broker = self._owner = owner
        self._executor_validator = executor_validator
        self._db = (owner._host_db, db_sha256, db_size_bytes)
        self._seal = seal
        self._ids: set[str] = set()
        self._active: str | None = None
        self._queries = 0
        self._invalid = False
        self._closed = False
        self._close_task: asyncio.Task | None = None
        self._cleanup_error: BaseException | None = None
        self._cleanup_cancellation: asyncio.CancelledError | None = None

    @property
    def cleanup_error(self) -> BaseException | None:
        return self._cleanup_error

    @property
    def cleanup_cancellation(self) -> asyncio.CancelledError | None:
        return self._cleanup_cancellation

    def _fail(self):
        self._invalid = True
        raise BashSqlError("Bash SQL binding or action invalid") from None

    def check_binding(self) -> None:
        self._check_binding(allow_closed=False)

    def _check_binding(self, *, allow_closed: bool) -> None:
        try:
            if (self._invalid or (self._closed and not allow_closed)
                    or self._task is not self._task_owner
                    or self._task.data is not self._data
                    or type(self._data) is not TaskData
                    or self._sql_task is not self._sql_owner
                    or self._instrument is not self._instrument_owner
                    or self._harness is not self._harness_owner
                    or self._harness.config is not self._config
                    or self._broker is not self._owner
                    or type(self._broker) is not TaskSqlBroker
                    or self._broker._config is not self._broker_config
                    or self._broker._task_identity is not self._task
                    or (self._broker._host_db, self._broker._db_sha256,
                        self._broker._db_size) != self._db
                    or (self._broker.revoked
                        and not (allow_closed and self._broker.closed))
                    or TaskSqlBroker.query is not _BROKER_QUERY
                    or TaskSqlBroker.aclose is not _BROKER_CLOSE
                    or TaskSqlBroker.wait_local_settlement is not _BROKER_SETTLE
                    or "query" in self._broker.__dict__
                    or "aclose" in self._broker.__dict__
                    or "wait_local_settlement" in self._broker.__dict__
                    or _digest((
                        self._data.model_dump(mode="python"), self._sql_task,
                        self._instrument, self._config.model_dump(mode="python"),
                        self._broker_config)) != self._seal):
                raise ValueError("binding changed")
            _validate_instrument(self._instrument)
            self._executor_validator._check_identity()
        except Exception:
            self._fail()

    def before_action(self, call_id: str) -> None:
        self.check_binding()
        try:
            self._broker._check_database()
            if (type(call_id) is not str or not call_id or len(call_id) > 256
                    or self._active is not None or call_id in self._ids
                    or len(self._ids) >= self._instrument.action_cap):
                raise ValueError("action rejected")
        except Exception:
            self._fail()
        self._ids.add(call_id)
        self._active = call_id

    def after_action(self, call_id: str) -> None:
        self.check_binding()
        try:
            self._broker._check_database()
            if self._active != call_id or self._queries:
                raise ValueError("action has not joined")
        except Exception:
            self._fail()
        self._active = None

    async def execute_sql(self, *, query: str) -> QueryWorkerResult:
        try:
            self.check_binding()
            if self._active is None:
                self._fail()
            encode_query_request(query, limits=self._broker_config.controller.worker.limits)
            self._queries += 1
            try:
                result = await self._broker.query(query)
            finally:
                self._queries -= 1
            self.check_binding()
            if type(result) is not QueryWorkerResult or result.status != "rows":
                self._fail()
            return result
        except BaseException:
            self._invalid = True
            try:
                await self.aclose()
            except BaseException as secondary:
                if isinstance(secondary, asyncio.CancelledError):
                    if self._cleanup_cancellation is None:
                        self._cleanup_cancellation = secondary
                else:
                    self._cleanup_error = secondary
            raise

    def require_valid(self) -> None:
        if (not self._closed or self._close_task is None
                or not self._close_task.done()):
            raise BashSqlError("Bash SQL cleanup not joined")
        self._check_binding(allow_closed=True)
        if self._active is not None or self._queries:
            self._fail()
        try:
            self._close_task.result()
            if not self._owner.closed:
                raise ValueError("cleanup incomplete")
            self._broker._check_database()
        except (Exception, asyncio.CancelledError):
            self._fail()

    async def _close_owner(self) -> None:
        failure = None
        try:
            await _BROKER_CLOSE(self._owner)
        except (SqlBrokerError, asyncio.CancelledError) as error:
            failure = error
        await _BROKER_SETTLE(
            self._owner, timeout_s=self._settlement_timeout)
        if failure is not None:
            raise failure

    async def aclose(self) -> None:
        self._closed = True
        if self._close_task is None:
            # Keep original owner even if a live reference was replaced.
            self._close_task = asyncio.create_task(self._close_owner())
        cancelled = None
        while not self._close_task.done():
            try:
                await asyncio.shield(self._close_task)
            except asyncio.CancelledError as error:
                cancelled = cancelled or error
                self._invalid = True
                if self._cleanup_cancellation is None:
                    self._cleanup_cancellation = error
            except Exception:
                break
        try:
            self._close_task.result()
            if not self._owner.closed:
                raise SqlBrokerRetirementPending("retirement unresolved")
        except SqlBrokerRetirementPending:
            self._invalid = True
            self._cleanup_error = BashSqlCleanupPending("Bash SQL cleanup unresolved")
            raise self._cleanup_error from None
        except BaseException:
            self._invalid = True
            self._cleanup_error = BashSqlError("Bash SQL cleanup failed")
            raise self._cleanup_error from None
        if cancelled is not None:
            raise cancelled
