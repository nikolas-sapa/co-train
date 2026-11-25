"""Task-local library composition, not a listener or runtime ownership authority.

Only the original controller owns subprocesses/resources. Cleanup observations
require the bound loop to stay alive. Filesystem races and real-time scheduling,
Docker mappings, HTTP parsing/TLS and production admission are not qualified.
"""

from __future__ import annotations

import asyncio
import base64
from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat

from aiohttp import web

from ptc.bird_sql_worker import (
    QueryWorkerError, QueryWorkerResult, decode_query_response, encode_query_request,
)
from ptc.bird_sql_worker_controller import (
    QueryWorkerController, QueryWorkerControllerError, QueryWorkerRetirementPending, WorkerControllerConfig,
)


class SqlBrokerError(RuntimeError):
    """Task infrastructure/admission failure, never a SQL result."""


class SqlBrokerRetirementPending(SqlBrokerError):
    """Retained cleanup/retirement is not known complete."""


class _Refusal(SqlBrokerError):
    def __init__(self, status=400):
        super().__init__("Invalid SQL request")
        self.status = status


def _seconds(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise SqlBrokerError("finite positive timeout required")


@dataclass(frozen=True, repr=False)
class TaskSqlBrokerConfig:
    controller: WorkerControllerConfig
    max_pending_requests: int
    request_timeout_s: float
    close_timeout_s: float

    def __post_init__(self):
        if type(self.controller) is not WorkerControllerConfig:
            raise SqlBrokerError("explicit controller configuration required")
        try:
            self.controller.__post_init__()
        except (ValueError, TypeError, RuntimeError):
            raise SqlBrokerError("invalid controller configuration") from None
        if type(self.max_pending_requests) is not int or self.max_pending_requests < 0:
            raise SqlBrokerError("nonnegative exact pending bound required")
        _seconds(self.request_timeout_s)
        _seconds(self.close_timeout_s)


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise _Refusal()
        obj[key] = value
    return obj


def _constant(value):
    raise _Refusal()


def _parse_request(data, limits):
    try:
        obj = json.loads(data.decode("utf-8", errors="strict"),
                         object_pairs_hook=_pairs, parse_constant=_constant)
        if (type(obj) is not dict or set(obj) != {"format", "version", "query"}
                or obj["format"] != "cotrain_sql_query"
                or type(obj["version"]) is not int or obj["version"] != 1):
            raise _Refusal()
        encode_query_request(obj["query"], limits=limits)
        return obj["query"]
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _Refusal() from None


def _encode_response(result, *, limits):
    """Minimal inverse of the unchanged public decoder; never sanitize SQL data."""
    def cell(value):
        if value is None:
            return ["null"]
        if type(value) is int:
            return ["integer", str(value)]
        if type(value) is float:
            return ["real", value.hex()]
        if type(value) is str:
            return ["text", value]
        if type(value) is bytes:
            return ["blob", base64.b64encode(value).decode("ascii")]
        raise SqlBrokerError("SQL response unavailable")
    try:
        if type(result) is not QueryWorkerResult or result.status not in {
            "rows", "sql_error", "row_refusal", "query_timeout",
        }:
            raise SqlBrokerError("SQL response unavailable")
        data = json.dumps(dict(
            format="cotrain_sql_result", version=1, status=result.status,
            columns=list(result.columns),
            rows=[[cell(value) for value in row] for row in result.rows],
            message=result.message), ensure_ascii=False, allow_nan=False,
            separators=(",", ":")).encode("utf-8", errors="strict")
        # Validate every field/cell with the original public decoder. Returning
        # original bytes, not a replacement result, preserves order and -0.0.
        if decode_query_response(data, limits=limits) != result:
            raise SqlBrokerError("SQL response unavailable")
        return data
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise SqlBrokerError("SQL response unavailable") from None


@dataclass(eq=False, repr=False)
class _Request:
    deadline: float
    ready: asyncio.Future
    done: asyncio.Future
    query: str | None = None
    error: SqlBrokerError | None = None
    body: asyncio.Task | None = None


class TaskSqlBroker:
    """One task association, one dispatcher, bounded admission, no query quota."""

    def __init__(self, *, config, task_identity, host_db: Path,
                 expected_db_sha256, expected_db_size_bytes):
        if type(config) is not TaskSqlBrokerConfig:
            raise SqlBrokerError("explicit broker configuration required")
        config.__post_init__()
        if (not isinstance(host_db, Path) or not host_db.is_absolute()
                or "\0" in str(host_db)):
            raise SqlBrokerError("absolute database path required")
        if (type(expected_db_sha256) is not str or
                re.fullmatch("[0-9a-f]{64}", expected_db_sha256) is None):
            raise SqlBrokerError("exact database SHA256 required")
        if type(expected_db_size_bytes) is not int or expected_db_size_bytes < 0:
            raise SqlBrokerError("nonnegative exact database size required")
        self._config = config
        self._task_identity = task_identity
        self._host_db = host_db
        self._db_sha256 = expected_db_sha256
        self._db_size = expected_db_size_bytes
        self._db_identity = self._identity()
        self._authorization = "Bearer " + secrets.token_hex(32)
        self._revoked = False
        self._closed = False
        self._failure = None
        self._loop = None
        self._wake = None
        self._settled = None
        self._collector_finished = None
        self._requests = deque()
        self._dispatcher = None
        self._active = None
        self._execution = None
        self._retirement = None
        self._closing_tasks = ()
        self._cleanup_join = None
        self._close_collector = None
        self._close_deadline = None
        self._caller_cancel = None

    @property
    def authorization_header(self):
        return self._authorization

    @property
    def revoked(self):
        return self._revoked

    @property
    def closed(self):
        return self._closed

    def _identity(self):
        try:
            if any(p.is_symlink() for p in (self._host_db, *self._host_db.parents)):
                raise SqlBrokerError("database identity unavailable")
            s = self._host_db.stat(follow_symlinks=False)
            if not stat.S_ISREG(s.st_mode):
                raise SqlBrokerError("database identity unavailable")
            return self._stat_identity(s)
        except OSError:
            raise SqlBrokerError("database identity unavailable") from None

    @staticmethod
    def _stat_identity(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

    def _check_database(self):
        fd = None
        try:
            if self._identity() != self._db_identity:
                raise SqlBrokerError("database association changed")
            fd = os.open(self._host_db, os.O_RDONLY | os.O_NOFOLLOW)
            before = os.fstat(fd)
            if (self._stat_identity(before) != self._db_identity
                    or before.st_size != self._db_size):
                raise SqlBrokerError("database association changed")
            digest = hashlib.sha256()
            remaining = self._db_size
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    raise SqlBrokerError("database association changed")
                digest.update(chunk)
                remaining -= len(chunk)
            if (os.read(fd, 1) or self._stat_identity(os.fstat(fd)) != self._db_identity
                    or self._identity() != self._db_identity
                    or digest.hexdigest() != self._db_sha256):
                raise SqlBrokerError("database association changed")
        except OSError:
            raise SqlBrokerError("database association unavailable") from None
        finally:
            if fd is not None:
                os.close(fd)

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            self._wake = asyncio.Event()
            self._settled = loop.create_future()
            self._collector_finished = loop.create_future()
        elif loop is not self._loop:
            raise SqlBrokerError("broker belongs to another event loop")

    def _remaining(self, deadline):
        remaining = deadline - self._loop.time()
        if remaining <= 0:
            raise SqlBrokerError("SQL request deadline exceeded")
        return remaining

    def _latch(self, error):
        self._closed = False
        if isinstance(error, (SqlBrokerRetirementPending, QueryWorkerRetirementPending)):
            self._failure = SqlBrokerRetirementPending
        elif self._failure is None:
            self._failure = SqlBrokerError

    def _error(self):
        # Retain classification, never an accumulating exception traceback with
        # prior request frames/data. Each caller receives a fresh neutral error.
        return (self._failure or SqlBrokerError)("SQL service unavailable")

    def _admit(self):
        if self._revoked:
            raise self._error()
        if len(self._requests) >= self._config.max_pending_requests + 1:
            self._start_close(SqlBrokerError("SQL admission exhausted"))
            raise self._error()
        r = _Request(self._loop.time()+self._config.request_timeout_s,
                     self._loop.create_future(), self._loop.create_future())
        self._requests.append(r)
        if self._dispatcher is None:
            self._dispatcher = asyncio.create_task(self._dispatch())
            # Synchronous observer owns failure even if the body never starts.
            self._dispatcher.add_done_callback(self._dispatch_done)
        self._wake.set()
        return r

    def _finish(self, r, value=None, error=None):
        if r in self._requests:
            self._requests.remove(r)
        if not r.done.done():
            r.done.set_result((value, error))

    def _dispatch_done(self, task):
        try:
            task.result()
        except BaseException:
            if not self._revoked:
                self._start_close(SqlBrokerError("SQL dispatcher unavailable"))

    def _execution_done(self, task):
        try:
            task.result()
        except QueryWorkerRetirementPending as error:
            self._latch(error)
        except BaseException:
            pass  # Dispatcher/cleanup join consumes it; no exceptional Future.

    def _retirement_done(self, task):
        try:
            task.result()
        except BaseException:
            self._latch(SqlBrokerRetirementPending("SQL retirement unresolved"))

    def _begin_retirement(self):
        if self._active is not None and self._retirement is None:
            self._retirement = asyncio.create_task(self._active.aclose())
            self._retirement.add_done_callback(self._retirement_done)

    async def _dispatch(self):
        try:
            while not self._revoked:
                if not self._requests:
                    self._wake.clear()
                    await self._wake.wait()
                    continue
                r = self._requests[0]
                await asyncio.wait_for(asyncio.shield(r.ready), self._remaining(r.deadline))
                if self._revoked:
                    break
                if r not in self._requests:
                    continue
                if r.error is not None:
                    self._finish(r, error=r.error)
                    continue
                self._remaining(r.deadline)
                self._check_database()
                self._remaining(r.deadline)  # Synchronous filesystem time counts.
                if self._revoked:
                    break
                self._active = QueryWorkerController(
                    config=self._config.controller, host_db=self._host_db)
                self._execution = asyncio.create_task(self._active.execute(r.query))
                self._execution.add_done_callback(self._execution_done)
                result = await asyncio.wait_for(
                    asyncio.shield(self._execution), self._remaining(r.deadline))
                self._begin_retirement()
                await asyncio.wait_for(
                    asyncio.shield(self._retirement), self._remaining(r.deadline))
                self._remaining(r.deadline)
                if self._revoked:
                    break
                self._active = self._execution = self._retirement = None
                self._finish(r, value=result)
        except BaseException as error:
            if not self._revoked:
                self._start_close(error)

    async def _read_body(self, r, content):
        limits = self._config.controller.worker.limits
        data = bytearray()
        while True:
            chunk = await asyncio.wait_for(content.read(
                min(256, limits.request_max_bytes-len(data)+1)), self._remaining(r.deadline))
            if not chunk:
                return _parse_request(bytes(data), limits)
            data.extend(chunk)
            if len(data) > limits.request_max_bytes:
                raise _Refusal(413)

    def _body_done(self, r, task):
        try:
            r.query = task.result()
        except _Refusal as error:
            r.error = error
            self._finish(r, error=error)
        except BaseException as error:
            self._start_close(error)
        finally:
            if not r.ready.done():
                r.ready.set_result(None)

    def _owned_tasks(self):
        tasks = [self._dispatcher, self._execution, self._retirement,
                 self._close_collector, self._cleanup_join,
                 *self._closing_tasks, *(r.body for r in self._requests)]
        return tuple(dict.fromkeys(t for t in tasks if t is not None))

    def _start_close(self, error=None):
        if error is not None:
            self._latch(error)
        if self._close_deadline is not None:
            return
        self._revoked = True  # Revoke before cancellation or scheduling cleanup.
        self._close_deadline = self._loop.time()+self._config.close_timeout_s
        if self._requests:
            self._latch(SqlBrokerError("SQL work interrupted"))
        bodies = tuple(r.body for r in self._requests if r.body is not None)
        for r in tuple(self._requests):
            if not r.ready.done():
                r.ready.set_result(None)
            self._finish(r, error=self._error())
        for task in bodies:
            if not task.done():
                task.cancel()
        if self._execution is not None and not self._execution.done():
            self._execution.cancel()
        if self._dispatcher is not None and not self._dispatcher.done():
            if self._dispatcher is not asyncio.current_task():
                self._dispatcher.cancel()
        self._wake.set()
        self._begin_retirement()
        self._closing_tasks = tuple(dict.fromkeys(
            task for task in (*bodies, self._execution, self._retirement, self._dispatcher)
            if task is not None))
        # Underlying public cleanup starts and its normal-result completion
        # observer is registered BEFORE creating a cancellable collector.
        self._cleanup_join = asyncio.gather(*self._closing_tasks, return_exceptions=True)
        self._cleanup_join.add_done_callback(self._cleanup_done)
        self._close_collector = asyncio.create_task(self._collect_close())
        self._close_collector.add_done_callback(self._collector_done)

    def _cleanup_done(self, joined):
        try:
            joined.result()
            if self._active is not None:
                if self._retirement is None or not self._retirement.done():
                    raise SqlBrokerRetirementPending("SQL retirement unresolved")
                self._retirement.result()
                self._active = None
        except BaseException:
            self._latch(SqlBrokerRetirementPending("SQL retirement unresolved"))
        if not self._settled.done():
            self._settled.set_result(None)
        self._closed = self._failure is None and self._collector_finished.done()

    async def _collect_close(self):
        await asyncio.shield(self._settled)

    def _collector_done(self, task):
        try:
            task.result()
        except BaseException:
            pass  # Observer, not collector cancellation, determines completion.
        self._collector_finished.set_result(None)
        self._closed = self._failure is None and self._settled.done()

    async def _join_close(self, caller_cancel=None):
        while not (self._settled.done() and self._collector_finished.done()):
            remaining = self._close_deadline-self._loop.time()
            if remaining <= 0:
                self._latch(SqlBrokerRetirementPending("SQL cleanup allowance exhausted"))
                break
            try:
                target = self._collector_finished if self._settled.done() else self._settled
                await asyncio.wait_for(asyncio.shield(target), remaining)
            except asyncio.CancelledError as error:
                if caller_cancel is None:
                    caller_cancel = error
                    if self._caller_cancel is None:
                        self._caller_cancel = error
            except asyncio.TimeoutError:
                self._latch(SqlBrokerRetirementPending("SQL cleanup allowance exhausted"))
                break
        if caller_cancel is not None:
            raise caller_cancel
        if self._failure is not None:
            raise self._error() from None

    async def _wait_request(self, r):
        try:
            result, error = await asyncio.shield(r.done)
        except asyncio.CancelledError as error:
            if self._caller_cancel is None:
                self._caller_cancel = error
            self._start_close(SqlBrokerError("SQL caller cancelled"))
            await self._join_close(error)
            raise
        if error is not None:
            if self._revoked:
                await self._join_close()
            raise error from None
        return result

    async def query(self, query: str) -> QueryWorkerResult:
        self._bind()
        try:
            r = self._admit()
        except SqlBrokerError:
            await self._join_close()
            raise
        try:
            if type(query) is not str or len(query) > self._config.controller.worker.limits.request_max_bytes:
                raise QueryWorkerError("query request infrastructure failure")
            encode_query_request(query, limits=self._config.controller.worker.limits)
        except QueryWorkerError:
            self._finish(r, error=_Refusal())
            if not r.ready.done():
                r.ready.set_result(None)
            raise _Refusal() from None
        r.query = query
        r.ready.set_result(None)
        return await self._wait_request(r)

    async def aclose(self) -> None:
        self._bind()
        self._start_close()
        await self._join_close()

    async def _wait_local_observation(self, task, deadline):
        if task is None:
            raise SqlBrokerRetirementPending("local closure unavailable")
        remaining = deadline - self._loop.time()
        if remaining <= 0 or task is asyncio.current_task():
            raise SqlBrokerRetirementPending("local settlement unresolved")
        if not task.done():
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if not done:
                raise SqlBrokerRetirementPending("local settlement unresolved")
        try:
            task.result()
        except BaseException:
            pass  # Observe terminal work, never erase sticky task failure.

    async def wait_local_settlement(self, *, timeout_s: float) -> None:
        """Observe broker closure and the public controller local barrier only."""
        _seconds(timeout_s)
        if self._loop is not asyncio.get_running_loop() or self._close_deadline is None:
            raise SqlBrokerError("closing bound broker required")
        deadline = self._loop.time() + timeout_s
        controller = self._active
        # Callback acknowledgements close the body/dispatcher/collector producer
        # graph. Only then enumerate its terminal owned work, not caller tasks.
        for task in (self._cleanup_join, self._settled, self._collector_finished):
            await self._wait_local_observation(task, deadline)
        for task in self._owned_tasks():
            await self._wait_local_observation(task, deadline)
        if self._requests:
            raise SqlBrokerRetirementPending("local admission closure unresolved")
        controllers = (controller,) if controller is not None else ()
        if self._active is not None and self._active is not controller:
            controllers += (self._active,)
        for retained in controllers:
            remaining = deadline - self._loop.time()
            if remaining <= 0:
                raise SqlBrokerRetirementPending("local settlement allowance exhausted")
            try:
                await retained.wait_local_settlement(timeout_s=remaining)
            except QueryWorkerControllerError:
                raise SqlBrokerRetirementPending("controller local settlement unresolved") from None
        if self._loop.time() >= deadline:
            raise SqlBrokerRetirementPending("local settlement allowance exhausted")

    def application(self) -> web.Application:
        app = web.Application(client_max_size=self._config.controller.worker.limits.request_max_bytes)
        app[_BROKER_KEY] = self
        app.router.add_post("/query", self._handle)
        return app

    async def _handle(self, request):
        values = request.headers.getall("Authorization", [])
        if (len(values) != 1 or len(values[0]) != len(self._authorization)
                or not values[0].isascii()
                or not hmac.compare_digest(values[0], self._authorization)):
            return web.Response(status=401, text="Unauthorized")
        try:
            self._bind()
            try:
                r = self._admit()
            except SqlBrokerError:
                await self._join_close()
                raise
            r.body = asyncio.create_task(self._read_body(r, request.content))
            r.body.add_done_callback(lambda task: self._body_done(r, task))
            result = await self._wait_request(r)
            try:
                data = _encode_response(result, limits=self._config.controller.worker.limits)
            except Exception:
                self._start_close(SqlBrokerError("SQL response unavailable"))
                await self._join_close()
                raise SqlBrokerError("SQL response unavailable") from None
            return web.Response(status=200, body=data, content_type="application/json")
        except _Refusal as error:
            return web.Response(status=error.status, text="Invalid SQL request")
        except SqlBrokerError:
            return web.Response(status=503, text="SQL service unavailable")


_BROKER_KEY = web.AppKey("task_sql_broker", TaskSqlBroker)
