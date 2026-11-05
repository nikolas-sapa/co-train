"""Unqualified single-query resource owner, deliberately not production-wired.

Hashes identify host-selected bytes, not Docker authenticity or permission.
Reducer states/fixture observations confer no real retirement or owned authority.
Pending local reclamation requires the bound event loop to remain alive until
spawn settlement and reaping finish; loop shutdown is not a cleanup guarantee.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
from uuid import uuid4

from ptc.bird_sql_worker import (
    DockerQueryWorkerSpec, QueryWorkerError, QueryWorkerResult,
    build_worker_create_argv, decode_query_response, encode_query_request, query_worker_source,
)
from ptc.bird_sql_worker_lifecycle import (
    EffectKind, EventKind, WorkerEvent, WorkerState, new_worker_state, transition_worker,
)


_SOURCE_MEMBERS = (
    "ptc/bird_sql_worker_controller.py", "ptc/bird_sql_worker.py",
    "ptc/bird_sql_worker_lifecycle.py", "ptc/sqlite_safety.py", "ptc/sql_runtime.py",
)
_OWNER_LABEL = "cotrain.sql-worker.owner"


class QueryWorkerControllerError(RuntimeError):
    """Infrastructure/lifecycle failure, never an execution-accuracy result."""


class QueryWorkerRetirementPending(QueryWorkerControllerError):
    """Retained identities/operations have not established safe completion."""


def _integer(value):
    if type(value) is not int or value <= 0:
        raise QueryWorkerControllerError("positive exact integer required")


def _seconds(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise QueryWorkerControllerError("positive finite deadline required")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QueryWorkerControllerError("exact SHA256 required")


def _absolute_path(value):
    if not isinstance(value, Path) or not value.is_absolute() or "\0" in str(value):
        raise QueryWorkerControllerError("absolute configured path required")


@dataclass(frozen=True)
class WorkerControllerConfig:
    worker: DockerQueryWorkerSpec
    docker_config_dir: Path
    command_cwd: Path
    command_env: tuple[tuple[str, str], ...]
    control_stdout_max_bytes: int
    stderr_max_bytes: int
    pipe_chunk_bytes: int
    process_join_timeout_s: float
    expected_cli_sha256: str
    expected_payload_sha256: str
    expected_source_sha256: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if type(self.worker) is not DockerQueryWorkerSpec:
            raise QueryWorkerControllerError("explicit worker specification required")
        try:
            self.worker.__post_init__()
        except (ValueError, TypeError):
            raise QueryWorkerControllerError("invalid worker specification") from None
        _absolute_path(self.docker_config_dir)
        _absolute_path(self.command_cwd)
        for value in (self.control_stdout_max_bytes, self.stderr_max_bytes, self.pipe_chunk_bytes):
            _integer(value)
        _seconds(self.process_join_timeout_s)
        _digest(self.expected_cli_sha256)
        _digest(self.expected_payload_sha256)
        if type(self.command_env) is not tuple:
            raise QueryWorkerControllerError("explicit environment tuple required")
        seen = set()
        for pair in self.command_env:
            if type(pair) is not tuple or len(pair) != 2:
                raise QueryWorkerControllerError("invalid environment entry")
            key, value = pair
            if (type(key) is not str or type(value) is not str or not key
                    or "=" in key or "\0" in key or "\0" in value or key in seen):
                raise QueryWorkerControllerError("invalid or duplicate environment entry")
            seen.add(key)
        if type(self.expected_source_sha256) is not tuple:
            raise QueryWorkerControllerError("fixed source closure required")
        names = []
        for pair in self.expected_source_sha256:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str:
                raise QueryWorkerControllerError("invalid source expectation")
            names.append(pair[0])
            _digest(pair[1])
        if len(names) != len(_SOURCE_MEMBERS) or set(names) != set(_SOURCE_MEMBERS):
            raise QueryWorkerControllerError("complete fixed source closure required")


@dataclass
class _LocalCommand:
    spawn: asyncio.Task
    tasks: list = field(default_factory=list)
    process: asyncio.subprocess.Process | None = None
    join_task: asyncio.Task | None = None
    readers: list = field(default_factory=list)
    reap: asyncio.Future | None = None
    reclaim_task: asyncio.Task | None = None
    reclaim_done: asyncio.Future | None = None
    reclaim_error: QueryWorkerRetirementPending | None = None
    local_incomplete: bool = False


@dataclass(frozen=True)
class _CommandOutput:
    stdout: bytes
    stderr: bytes
    returncode: int


@dataclass(frozen=True)
class _Outcome:
    value: QueryWorkerResult | None
    error: BaseException | None


class _Revoked(QueryWorkerControllerError):
    pass


def _json_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise QueryWorkerControllerError("duplicate control JSON field")
        obj[key] = value
    return obj


def _json_constant(value):
    raise QueryWorkerControllerError("nonfinite control JSON")


def _control_json(data):
    try:
        return json.loads(data.decode("utf-8", errors="strict"),
                          object_pairs_hook=_json_pairs, parse_constant=_json_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise QueryWorkerControllerError("invalid control JSON") from None


def _container_id(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QueryWorkerControllerError("invalid container identity")
    return value


class QueryWorkerController:
    """One loop, one retained owner, one query. Construction starts nothing."""

    def __init__(self, *, config: WorkerControllerConfig, host_db: Path):
        if type(config) is not WorkerControllerConfig:
            raise QueryWorkerControllerError("explicit controller configuration required")
        config.__post_init__()
        _absolute_path(host_db)
        self._config = config
        self._host_db = host_db
        token = uuid4().hex
        self._state = new_worker_state(owner_id=token, resource_name="cotrain-query-" + token)
        self._loop = None
        self._used = False
        self._revoked = False
        self._abort = None
        self._owner_task = None
        self._owner_done = None
        self._cleanup_task = None
        self._outcome = None
        self._caller_cancel = None
        self._owner_cancel = None
        self._records = []
        self._pins = None
        self._admitted_id = None
        self._local_uncertain = False

    @property
    def state(self) -> WorkerState:
        return self._state

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            self._abort = asyncio.Event()
            self._owner_done = asyncio.Event()
        elif loop is not self._loop:
            raise QueryWorkerControllerError("controller belongs to another event loop")

    def _event(self, kind, *, operation_id=None, success=None, absent=None):
        transition = transition_worker(self._state, WorkerEvent(
            self._state.owner_id, self._state.resource_name, kind,
            operation_id or uuid4().hex, success=success, absent=absent))
        self._state = transition.state
        return transition.effects

    def _observe(self, effect, success, *, absent=None):
        return self._event(EventKind.OBSERVATION, operation_id=effect.operation_id,
                           success=success, absent=absent)

    def _revoke(self):
        self._revoked = True
        if self._abort is not None:
            self._abort.set()
        self._event(EventKind.CANCEL)

    def _file_identity(self, path, expected):
        try:
            if path.is_symlink() or not path.is_file():
                raise QueryWorkerControllerError("identity input unavailable")
            before = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            after = path.stat()
            identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if before != after or digest != expected:
                raise QueryWorkerControllerError("identity input mismatch")
            return identity
        except OSError:
            raise QueryWorkerControllerError("identity input unavailable") from None

    def _identities(self):
        root = Path(__file__).resolve().parents[1]
        config = self._config
        pins = tuple((name, self._file_identity(root / name, digest))
                     for name, digest in config.expected_source_sha256)
        cli = Path(config.worker.cli_path)
        if not os.access(cli, os.X_OK):
            raise QueryWorkerControllerError("configured executable unavailable")
        return (self._file_identity(cli, config.expected_cli_sha256), pins)

    def _preflight(self, query):
        try:
            self._config.__post_init__()
            for directory in (self._config.command_cwd, self._config.docker_config_dir):
                if directory.is_symlink() or not directory.is_dir():
                    raise QueryWorkerControllerError("configured directory unavailable")
            request = encode_query_request(query, limits=self._config.worker.limits)
            self._pins = self._identities()
            payload = query_worker_source(limits=self._config.worker.limits)
            if hashlib.sha256(payload).hexdigest() != self._config.expected_payload_sha256:
                raise QueryWorkerControllerError("payload identity mismatch")
            base = build_worker_create_argv(
                self._config.worker, resource_name=self._state.resource_name, host_db=self._host_db)
            argv = (base[0], "--config", str(self._config.docker_config_dir), *base[1:4],
                    "--label", f"{_OWNER_LABEL}={self._state.owner_id}", *base[4:])
            return request, argv
        except (QueryWorkerError, OSError, ValueError, TypeError):
            raise QueryWorkerControllerError("controller preflight failed") from None

    def _check_identity(self):
        if self._pins is None or self._identities() != self._pins:
            raise QueryWorkerControllerError("retained executable/source identity changed")

    def _argv(self, *args):
        c = self._config
        return (c.worker.cli_path, "--config", str(c.docker_config_dir),
                "--context", c.worker.daemon_context, *args)

    def _remaining(self, deadline):
        remaining = deadline - self._loop.time()
        if remaining <= 0:
            raise QueryWorkerControllerError("command deadline exceeded")
        return remaining

    async def _pump(self, stream, capacity):
        data = bytearray()
        while True:
            chunk = await stream.read(min(self._config.pipe_chunk_bytes, capacity-len(data)+1))
            if not chunk:
                return bytes(data)
            if len(data) + len(chunk) > capacity:
                raise QueryWorkerControllerError("command wire overflow")
            data.extend(chunk)

    async def _write(self, proc, request):
        try:
            if request is not None:
                proc.stdin.write(request)
                await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()
        except (BrokenPipeError, ConnectionError):
            raise QueryWorkerControllerError("command input transport failed") from None

    async def _join_retained(self, task):
        # Never re-await an already terminal cancelled task in a busy loop.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                if asyncio.current_task().cancelling():
                    if self._owner_cancel is None:
                        self._owner_cancel = exc
                    self._revoke()
                elif task.done():
                    break
        return task.result()

    async def _join_local(self, record):
        deadline = self._loop.time() + self._config.process_join_timeout_s
        try:
            if record.process is None:
                record.process = await asyncio.wait_for(
                    asyncio.shield(record.spawn), self._remaining(deadline))
            joined = self._begin_local_reap(record)
            await asyncio.wait_for(
                asyncio.shield(joined), self._remaining(deadline))
            if record.process.returncode is None:
                raise QueryWorkerControllerError("local process join incomplete")
        except (Exception, asyncio.CancelledError):
            self._local_uncertain = True
            record.local_incomplete = True
            if record.process is None and record.reclaim_task is None:
                # Caller allowance is exhausted, NOT ownership. Never cancel
                # or forget a shielded spawn that may still return a process.
                # Register ownership BEFORE any collector task can be cancelled,
                # including before its coroutine has ever executed.
                record.reclaim_done = self._loop.create_future()
                record.spawn.add_done_callback(
                    lambda spawn: self._collect_late_spawn(record, spawn))
                record.reclaim_task = asyncio.create_task(self._reclaim_local(record))
            raise QueryWorkerRetirementPending("local command joining unresolved") from None

    def _begin_local_reap(self, record):
        if record.reap is None:
            proc = record.process
            try:
                # This PID came only from our fresh-session spawn handle.
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # No result retention during cleanup; exhausted-capacity reads
            # remain one byte each, including for a handle arriving late.
            for task, stream in record.readers:
                record.tasks.append(asyncio.create_task(self._discard_after(task, stream)))
            if not record.tasks:
                proc.stdin.close()
                record.tasks.extend((
                    asyncio.create_task(self._discard_after(None, proc.stdout)),
                    asyncio.create_task(self._discard_after(None, proc.stderr)),
                    asyncio.create_task(proc.stdin.wait_closed()),
                    asyncio.create_task(proc.wait()),
                ))
            record.reap = asyncio.gather(*record.tasks, return_exceptions=True)
            record.tasks.append(record.reap)
        return record.reap

    def _finish_reclamation(self, record, complete):
        record.local_incomplete = not complete
        if not complete:
            record.reclaim_error = QueryWorkerRetirementPending("late local reclamation unresolved")
        # No exceptional Future outcome left unobserved if the collector never
        # starts. The sanitized failure remains on the retained command record.
        if not record.reclaim_done.done():
            record.reclaim_done.set_result(None)

    def _collect_late_spawn(self, record, spawn):
        try:
            record.process = spawn.result()
            # This synchronous observer is the sole late-path reap initiator.
            # The collector only waits, so cancellation cannot duplicate kills.
            joined = self._begin_local_reap(record)
            joined.add_done_callback(
                lambda reap: self._settle_late_reap(record, reap))
        except BaseException:
            self._finish_reclamation(record, False)

    def _settle_late_reap(self, record, reap):
        try:
            outcomes = reap.result()
            complete = (not any(isinstance(value, BaseException) for value in outcomes)
                        and record.process.returncode is not None
                        and all(task.done() for task in record.tasks))
        except BaseException:
            complete = False
        self._finish_reclamation(record, complete)

    async def _await_reclamation(self, task):
        # Cleanup-task cancellation must not cancel its underlying spawn/reap.
        # This is not a caller wait and never changes caller/owner exception
        # identity. Explicit loop shutdown can still cancel underlying tasks.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if task.done():
                    break
        return task.result()

    async def _reclaim_local(self, record):
        try:
            await self._await_reclamation(record.spawn)
            await self._await_reclamation(record.reclaim_done)
        except BaseException:
            # Consume the retained subtask outcome, with no argv/env/path
            # diagnostics. Remote uncertainty and caller outcome stay intact.
            record.reclaim_error = QueryWorkerRetirementPending("late local reclamation unresolved")

    async def _discard_after(self, task, stream):
        if task is not None:
            try:
                await task
            except (Exception, asyncio.CancelledError):
                pass
        while await stream.read(1):
            pass

    async def _join_command(self, record):
        record.join_task = asyncio.create_task(self._join_local(record))
        await self._join_retained(record.join_task)

    async def _command(self, argv, *, deadline, capacity, request=None,
                       interrupt=False, start_effect=None):
        self._check_identity()
        self._remaining(deadline)
        if interrupt and self._revoked:
            if start_effect is not None:
                self._observe(start_effect, False)
            raise _Revoked("query revoked")
        record = _LocalCommand(asyncio.create_task(asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=str(self._config.command_cwd),
            env=dict(self._config.command_env), start_new_session=True,
            limit=self._config.pipe_chunk_bytes)))
        self._records.append(record)
        observed_start = False
        abort_task = None
        try:
            proc = await asyncio.wait_for(asyncio.shield(record.spawn), self._remaining(deadline))
            record.process = proc
            if start_effect is not None:
                self._observe(start_effect, True)
                observed_start = True
            record.tasks.extend((
                asyncio.create_task(self._pump(proc.stdout, capacity)),
                asyncio.create_task(self._pump(proc.stderr, self._config.stderr_max_bytes)),
                asyncio.create_task(self._write(proc, request)),
                asyncio.create_task(proc.wait()),
            ))
            record.readers.extend(((record.tasks[0], proc.stdout), (record.tasks[1], proc.stderr)))
            combined = asyncio.gather(*record.tasks)
            record.tasks.append(combined)
            watched = {combined}
            if interrupt:
                abort_task = asyncio.create_task(self._abort.wait())
                watched.add(abort_task)
            done, _ = await asyncio.wait(watched, timeout=self._remaining(deadline),
                                         return_when=asyncio.FIRST_COMPLETED)
            if abort_task is not None and abort_task in done:
                raise _Revoked("query revoked")
            if combined not in done:
                raise QueryWorkerControllerError("command deadline exceeded")
            stdout, stderr, _, code = combined.result()
            return _CommandOutput(stdout, stderr, code)
        except (OSError, asyncio.TimeoutError):
            raise QueryWorkerControllerError("command launch/deadline failed") from None
        except asyncio.CancelledError as exc:
            if self._owner_cancel is None:
                self._owner_cancel = exc
            self._revoke()
            raise
        finally:
            if abort_task is not None:
                abort_task.cancel()
                record.tasks.append(abort_task)
            await self._join_command(record)
            if start_effect is not None and not observed_start and record.spawn.done():
                self._observe(start_effect, record.process is not None)

    async def _inspect(self, ident, deadline):
        output = await self._command(self._argv("inspect", "--type", "container", ident),
                                     deadline=deadline, capacity=self._config.control_stdout_max_bytes)
        if output.returncode != 0:
            raise QueryWorkerControllerError("container inspection failed")
        obj = _control_json(output.stdout)
        try:
            if type(obj) is not list or len(obj) != 1 or type(obj[0]) is not dict:
                raise QueryWorkerControllerError("invalid inspection shape")
            obj = obj[0]
            if _container_id(obj["Id"]) != ident or obj["Name"] != "/" + self._state.resource_name:
                raise QueryWorkerControllerError("container identity mismatch")
            config, state = obj["Config"], obj["State"]
            if type(config) is not dict or type(state) is not dict:
                raise QueryWorkerControllerError("invalid inspection objects")
            labels = config["Labels"]
            if (type(labels) is not dict or labels.get(_OWNER_LABEL) != self._state.owner_id
                    or not all(type(k) is str and type(v) is str for k, v in labels.items())):
                raise QueryWorkerControllerError("container ownership mismatch")
            if (type(state["Status"]) is not str or type(state["Running"]) is not bool
                    or type(state["OOMKilled"]) is not bool or type(state["ExitCode"]) is not int):
                raise QueryWorkerControllerError("invalid guest state types")
            return state
        except (KeyError, TypeError):
            raise QueryWorkerControllerError("incomplete container inspection") from None

    def _guest_succeeded(self, state):
        return (state["Status"] == "exited" and state["Running"] is False
                and state["OOMKilled"] is False and state["ExitCode"] == 0)

    async def _inventory_absent(self, deadline):
        output = await self._command(self._argv(
            "container", "ls", "--all", "--no-trunc", "--filter",
            f"label={_OWNER_LABEL}={self._state.owner_id}", "--format", "{{json .}}"),
            deadline=deadline, capacity=self._config.control_stdout_max_bytes)
        if output.returncode != 0:
            raise QueryWorkerControllerError("owner inventory failed")
        if output.stdout == b"":
            return True
        seen = set()
        for line in output.stdout.splitlines():
            row = _control_json(line)
            try:
                if type(row) is not dict:
                    raise QueryWorkerControllerError("invalid inventory shape")
                ident = _container_id(row["ID"])
                if ident in seen or type(row["Names"]) is not str or type(row["Labels"]) is not str:
                    raise QueryWorkerControllerError("invalid inventory identity")
                seen.add(ident)
                labels = {}
                for item in row["Labels"].split(","):
                    key, separator, value = item.partition("=")
                    if not separator or not key or key in labels:
                        raise QueryWorkerControllerError("invalid inventory labels")
                    labels[key] = value
                if labels.get(_OWNER_LABEL) != self._state.owner_id:
                    raise QueryWorkerControllerError("foreign inventory ownership")
                if row["Names"] != self._state.resource_name or ident != self._admitted_id:
                    raise QueryWorkerControllerError("unexpected owner inventory")
                await self._inspect(ident, deadline)
            except (KeyError, TypeError):
                raise QueryWorkerControllerError("incomplete owner inventory") from None
        return False

    async def _retire(self):
        if self._local_uncertain:
            raise QueryWorkerRetirementPending("local command ownership unresolved")
        if self._state.phase == "CLOSED":
            return
        remove = next((p for p in self._state.pending if p.kind is EffectKind.REMOVE), None)
        if remove is None or self._admitted_id is None:
            raise QueryWorkerRetirementPending("resource creation/retirement unresolved")
        deadline = self._loop.time() + self._config.worker.retirement_timeout_s
        try:
            await self._inspect(self._admitted_id, deadline)
            removed = await self._command(self._argv("rm", "--force", self._admitted_id),
                deadline=deadline, capacity=self._config.control_stdout_max_bytes)
            if removed.returncode != 0:
                self._observe(remove, False)
                raise QueryWorkerRetirementPending("resource removal unresolved")
            effects = self._observe(remove, True)
            verify = next(p for p in effects if p.kind is EffectKind.VERIFY_ABSENT)
            absent = await self._inventory_absent(deadline)
            self._observe(verify, True, absent=absent)
            if not absent or self._state.phase != "CLOSED":
                raise QueryWorkerRetirementPending("resource absence unresolved")
        except (QueryWorkerControllerError, OSError):
            raise QueryWorkerRetirementPending("resource retirement unresolved") from None

    async def _run(self, query):
        result = None
        failure = None
        try:
            request, create_argv = self._preflight(query)
            if self._revoked:
                raise _Revoked("query revoked")
            create = self._event(EventKind.BEGIN)[0]
            setup_deadline = self._loop.time() + self._config.worker.setup_timeout_s
            output = await self._command(create_argv, deadline=setup_deadline,
                                         capacity=self._config.control_stdout_max_bytes)
            # Local completion/nonzero/stderr NEVER settles uncertain remote CREATE.
            if output.returncode != 0:
                raise QueryWorkerRetirementPending("resource creation unresolved")
            raw_id = output.stdout[:-1] if output.stdout.endswith(b"\n") else output.stdout
            try:
                ident = _container_id(raw_id.decode("ascii", errors="strict"))
            except (UnicodeError, QueryWorkerControllerError):
                raise QueryWorkerRetirementPending("resource creation identity unresolved") from None
            await self._inspect(ident, setup_deadline)
            self._admitted_id = ident
            self._observe(create, True)
            if self._revoked:
                raise _Revoked("query revoked")
            start, drain = self._event(EventKind.START)
            start_deadline = self._loop.time() + self._config.worker.start_timeout_s
            try:
                output = await self._command(
                    self._argv("start", "--attach", "--interactive", ident),
                    deadline=start_deadline, capacity=self._config.worker.limits.response_max_bytes,
                    request=request, interrupt=True, start_effect=start)
            finally:
                if not self._local_uncertain:
                    self._observe(drain, True)
            if output.returncode != 0:
                raise QueryWorkerControllerError("attached client failed")
            guest = await self._inspect(ident, start_deadline)
            if not self._guest_succeeded(guest):
                raise QueryWorkerControllerError("guest did not exit successfully")
            result = decode_query_response(output.stdout, limits=self._config.worker.limits)
            if result.status == "infrastructure_failure":
                raise QueryWorkerControllerError("worker reported infrastructure failure")
        except BaseException as exc:
            failure = exc
            if isinstance(exc, asyncio.CancelledError) and self._owner_cancel is None:
                self._owner_cancel = exc
        self._revoke()
        self._cleanup_task = asyncio.create_task(self._retire())
        cleanup_failed = False
        try:
            await self._join_retained(self._cleanup_task)
        except BaseException:
            cleanup_failed = True
        if self._owner_cancel is not None:
            raise self._owner_cancel
        if cleanup_failed or self._local_uncertain or self._state.phase != "CLOSED":
            raise QueryWorkerRetirementPending("resource completion unresolved")
        if failure is not None:
            if isinstance(failure, QueryWorkerControllerError):
                raise failure
            raise QueryWorkerControllerError("query controller failed") from None
        if result is None:
            raise QueryWorkerControllerError("query result unavailable")
        return result

    async def _owner_entry(self, query):
        try:
            self._outcome = _Outcome(await self._run(query), None)
        except BaseException as exc:
            self._outcome = _Outcome(None, exc)
        finally:
            self._owner_done.set()
        return self._outcome

    async def _wait_owner(self):
        caller_cancel = None
        while not self._owner_task.done():
            try:
                await asyncio.shield(self._owner_task)
            except asyncio.CancelledError as exc:
                if asyncio.current_task().cancelling():
                    if caller_cancel is None:
                        caller_cancel = exc
                    if self._caller_cancel is None:
                        self._caller_cancel = exc
                    self._revoke()
                elif self._owner_task.done():
                    break
        if self._outcome is None:
            try:
                self._outcome = self._owner_task.result()
            except asyncio.CancelledError as exc:
                # The owner body may never have run; do not fabricate its identity.
                self._outcome = _Outcome(None, exc)
                self._revoke()
                self._owner_done.set()
        if caller_cancel is not None:
            raise caller_cancel
        return self._outcome

    async def execute(self, query: str) -> QueryWorkerResult:
        self._bind_loop()
        if self._used:
            raise QueryWorkerControllerError("query controller is single use")
        self._used = True
        self._owner_task = asyncio.create_task(self._owner_entry(query))
        outcome = await self._wait_owner()
        if outcome.error is not None:
            raise outcome.error
        if self._state.phase != "CLOSED" or self._local_uncertain:
            raise QueryWorkerRetirementPending("resource completion unresolved")
        return outcome.value

    async def aclose(self) -> None:
        self._bind_loop()
        self._used = True
        self._revoke()
        if self._owner_task is not None:
            await self._wait_owner()
        if self._state.phase != "CLOSED" or self._local_uncertain:
            raise QueryWorkerRetirementPending("resource completion unresolved")

    async def _wait_local_observation(self, task, deadline):
        if task is None:
            return
        remaining = deadline - self._loop.time()
        if remaining <= 0 or task is asyncio.current_task():
            raise QueryWorkerRetirementPending("local settlement unresolved")
        if not task.done():
            # asyncio.wait cancels only its observer waiter, never the watched
            # owner. No shield-created replacement task or timeout reset.
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if not done:
                raise QueryWorkerRetirementPending("local settlement unresolved")
        try:
            task.result()
        except BaseException:
            pass  # Terminal failure is consumed, not remote success.

    async def wait_local_settlement(self, *, timeout_s: float) -> None:
        """Observe a stable local closure, without authorizing any cleanup.

        Local completion is independent of historical uncertainty and remote
        retirement. The existing bound loop must remain alive.
        """
        _seconds(timeout_s)
        if self._loop is not asyncio.get_running_loop() or not self._revoked:
            raise QueryWorkerControllerError("revoked bound controller required")
        deadline = self._loop.time() + timeout_s
        # These are the only command/record producers. Their termination closes
        # the record set; a snapshot taken while they run would be insufficient.
        await self._wait_local_observation(self._owner_task, deadline)
        await self._wait_local_observation(self._cleanup_task, deadline)
        for record in self._records:
            await self._wait_local_observation(record.join_task, deadline)
            await self._wait_local_observation(record.spawn, deadline)
            # Registered BEFORE any cancellable late collector. This normal
            # acknowledgement covers future handle -> readers -> reap callbacks.
            await self._wait_local_observation(record.reclaim_done, deadline)
            await self._wait_local_observation(record.reclaim_task, deadline)
            for task in (*record.tasks, *(t for t, _ in record.readers), record.reap):
                await self._wait_local_observation(task, deadline)
            try:
                proc = record.spawn.result()
            except BaseException:
                raise QueryWorkerRetirementPending("local ownership unknown") from None
            # Terminal tasks alone do not certify a joined process/transport.
            if (record.process is not proc or record.join_task is None
                    or record.reap is None or not record.reap.done()
                    or proc.returncode is None or not proc.stdin.is_closing()
                    or not proc.stdout.at_eof() or not proc.stderr.at_eof()):
                raise QueryWorkerRetirementPending("local ownership unresolved")
        if self._loop.time() >= deadline:
            raise QueryWorkerRetirementPending("local settlement allowance exhausted")
