"""Experimental original-SDK Bash bridge, deliberately not production admission."""

from __future__ import annotations

import asyncio
import base64
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import struct
import sys

from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.harnesses.utils.launch import CHAT_PROGRAM_SOURCE
from verifiers.v1.runtimes import ProgramResult
from verifiers.v1.runtimes.docker import DockerConfig, DockerRuntime
from verifiers.v1.types import Response

from ptc.bash_bridge_client import (
    FRAME_MAX, OUTPUT_MAX, SOCKET_TIMEOUT, BridgeProtocolError, decode, pack, sign,
    validate_command, verify,
)
from ptc.bird_sql_worker import _dump_json, _encode_cell, _envelope
from ptc.sql_owned_bash import BashSqlBinding, BashSqlError


class BashBridgeError(BashSqlError):
    pass


_DEADLINE = ContextVar("bash_bridge_deadline", default=None)


def _remaining(deadline=None):
    deadline = _DEADLINE.get() if deadline is None else deadline
    if deadline is None:
        raise BashBridgeError("operation deadline required")
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError("Bash bridge operation deadline expired")
    return remaining


class _Directory:
    def __init__(self, path: Path):
        self.path = Path(path)
        text = str(self.path)
        if (not self.path.is_absolute() or text.startswith("//")
                or any(c in text for c in ",:\0")
                or str(PurePosixPath(text)) != text
                or any(part in (".", "..") for part in self.path.parts)):
            raise BashBridgeError("canonical mount path required")
        self.links = []
        self.files = []
        self.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.links.append((None, "/", self.fd, os.fstat(self.fd)))
        sticky_parent = False
        try:
            for part in self.path.parts[1:]:
                parent = self.fd
                self.fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=parent)
                info = os.fstat(self.fd)
                self.links.append((parent, part, self.fd, info))
                private = info.st_uid == os.geteuid() and not info.st_mode & 0o077
                if (info.st_uid not in (0, os.geteuid())
                        or (sticky_parent and not private)):
                    raise BashBridgeError("untrusted directory custody")
                writable = bool(info.st_mode & 0o022)
                sticky_parent = writable and info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                if writable and not sticky_parent:
                    raise BashBridgeError("untrusted writable ancestry")
            if sticky_parent:
                raise BashBridgeError("owner-private scratch child required")
            self.check()
        except (OSError, ValueError) as error:
            self.close()
            raise BashBridgeError("canonical trusted scratch required") from error
        except BaseException:
            self.close()
            raise

    def check(self):
        for parent, name, fd, expected in self.links:
            actual = os.fstat(fd)
            linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (actual.st_dev, actual.st_ino, actual.st_mode, actual.st_uid,
                    actual.st_nlink) != (
                    linked.st_dev, linked.st_ino, linked.st_mode, linked.st_uid,
                    linked.st_nlink) or (actual.st_dev, actual.st_ino,
                    actual.st_mode, actual.st_uid) != (
                    expected.st_dev, expected.st_ino, expected.st_mode, expected.st_uid):
                raise BashBridgeError("directory link custody lost")
        for fd, name, expected in self.files:
            linked = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (linked.st_dev, linked.st_ino, linked.st_mode, linked.st_uid,
                    linked.st_gid, linked.st_nlink) != (
                    expected.st_dev, expected.st_ino, expected.st_mode,
                    expected.st_uid, expected.st_gid, 1):
                raise BashBridgeError("staged file link custody lost")

    def child(self, name, mode=0o755):
        self.check()
        os.mkdir(name, mode, dir_fd=self.fd)
        return _Directory(self.path / name)

    def stage(self, name, data, mode):
        self.check()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
            os.fchmod(fd, mode)
            self.files.append((self.fd, name, os.fstat(fd)))
        finally:
            os.close(fd)
        self.check()

    def stage_link(self, name, target):
        self.check()
        os.symlink(target, name, dir_fd=self.fd)
        self.files.append((self.fd, name, os.stat(
            name, dir_fd=self.fd, follow_symlinks=False)))

    def close(self):
        for _, _, fd, _ in reversed(self.links):
            os.close(fd)
        self.links.clear()


@dataclass(frozen=True)
class BridgeLimits:
    cpu: float = 1.0
    memory_bytes: int = 512 * 1024 * 1024
    pids: int = 64
    action_s: float = 60.0
    policy_s: float = 3600.0
    engine_s: float = 15.0
    protocol_s: float = 5.0
    output_bytes: int = OUTPUT_MAX
    pending_calls: int = 256
    workspace_bytes: int = 256 * 1024 * 1024
    workspace_inodes: int = 4096
    retirement_s: float = 25.0
    delivery_s: float = 10.0

    def __post_init__(self):
        for value in (self.cpu, self.action_s, self.policy_s,
                      self.engine_s, self.protocol_s, self.retirement_s, self.delivery_s):
            if type(value) not in (int, float) or not 0 < value < float("inf"):
                raise BashBridgeError("positive finite limit required")
        for value in (self.memory_bytes, self.pids, self.output_bytes,
                      self.pending_calls, self.workspace_bytes, self.workspace_inodes):
            if type(value) is not int or value <= 0:
                raise BashBridgeError("positive integer limit required")
        if (self.workspace_inodes > 65536 or self.output_bytes > OUTPUT_MAX
                or self.action_s + self.engine_s + self.retirement_s
                + self.delivery_s + self.protocol_s >= SOCKET_TIMEOUT
                or self.delivery_s < 2 * self.protocol_s):
            raise BashBridgeError("limits exceed fixed client bounds")


def require_bash_only(harness: BashHarness, mcp_urls: dict) -> None:
    if (type(harness) is not BashHarness
            or type(harness.config) is not BashHarnessConfig
            or harness.config.edit is not False or harness.config.search is not False
            or harness.config.skills or mcp_urls):
        raise BashBridgeError("explicit Bash-only edit=false/search=false/no-MCP required")


async def join_owned(task: asyncio.Task, deadline=None):
    cancellation = None
    while not task.done():
        try:
            if deadline is None:
                await asyncio.shield(task)
            else:
                done, _ = await asyncio.wait((task,), timeout=_remaining(deadline))
                if not done:
                    raise TimeoutError("owned join unresolved at deadline")
        except asyncio.CancelledError as error:
            cancellation = cancellation or error
        except TimeoutError as error:
            if cancellation is not None:
                raise cancellation from error
            raise
        except Exception:
            break
    try:
        result = task.result()
    except BaseException as error:
        if cancellation is not None:
            raise cancellation from error
        raise
    if cancellation is not None:
        raise cancellation
    return result


async def _receive(reader: asyncio.StreamReader, timeout: float):
    async with asyncio.timeout(timeout):
        size = struct.unpack("!I", await reader.readexactly(4))[0]
        if not 0 < size <= FRAME_MAX:
            raise BridgeProtocolError("invalid frame length")
        return decode(await reader.readexactly(size))


class _Capability:
    """One authority and one request at a time, never an actor stdout parser."""

    def __init__(self, owner, directory: Path, operation: str, execute):
        self.owner, self.directory = owner, directory
        self.operation, self.execute = operation, execute
        self.key = secrets.token_bytes(32)
        self.sequence = 0
        self.revoked = False
        self.busy = False
        self.server = None
        self.handlers: set[asyncio.Task] = set()
        self.finalizing_handlers: set[asyncio.Task] = set()
        self.writers: set[asyncio.StreamWriter] = set()
        self.unresolved_writers: set[asyncio.StreamWriter] = set()
        self.cleanup_errors: list[BaseException] = []
        self.primary_errors: list[BaseException] = []
        self.owned_children: set[asyncio.Task] = set()
        self._close_task = None
        self._close_deadline = None
        self.custody = None

    async def start(self):
        parent = _Directory(self.directory.parent)
        try:
            self.custody = parent.child(self.directory.name)
        finally:
            parent.close()
        self.custody.stage("key", self.key, 0o444)
        self.server = await asyncio.start_unix_server(
            self._handle, path=str(self.directory / "socket"), limit=FRAME_MAX + 4)
        (self.directory / "socket").chmod(0o666)
        self.custody.files.append((self.custody.fd, "socket", os.stat(
            "socket", dir_fd=self.custody.fd, follow_symlinks=False)))
        self.custody.check()

    async def _send(self, writer, value, deadline):
        remaining = min(self.owner.limits.protocol_s, _remaining(deadline))
        writer.write(pack(sign(value, self.key)))
        await asyncio.wait_for(writer.drain(), remaining)

    async def _join(self, awaitable, deadline):
        task = asyncio.create_task(awaitable)
        self.owned_children.add(task)
        try:
            return await join_owned(task, deadline)
        finally:
            if task.done():
                self.owned_children.discard(task)

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        self.writers.add(writer)
        acquired = False
        work = disconnect = None
        deadline = min(_DEADLINE.get() or float("inf"),
                       asyncio.get_running_loop().time() + SOCKET_TIMEOUT - 1)
        token = _DEADLINE.set(deadline)
        try:
            if self.revoked or self.busy:
                raise BridgeProtocolError("revoked or concurrent capability")
            self.busy = acquired = True
            hello = {"nonce": secrets.token_hex(32), "seq": self.sequence}
            await self._send(writer, hello, deadline)
            request = verify(
                await _receive(reader, min(
                    self.owner.limits.protocol_s, _remaining(deadline))), self.key)
            if (type(request) is not dict
                    or set(request) != {"nonce", "seq", "op", "value"}
                    or request["nonce"] != hello["nonce"]
                    or type(request["seq"]) is not int
                    or request["seq"] != self.sequence
                    or request["op"] != self.operation):
                raise BridgeProtocolError("invalid capability request")
            validate_command(request["value"])
            self.sequence += 1
            work = asyncio.create_task(self.execute(request["value"]))
            disconnect = asyncio.create_task(reader.read(1))
            self.owned_children.update((work, disconnect))
            done, _ = await asyncio.wait(
                (work, disconnect), timeout=_remaining(deadline),
                return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise TimeoutError("capability dispatch deadline expired")
            if disconnect in done:
                raise BridgeProtocolError("client lost or sent unexpected data")
            stdout, stderr, status = work.result()
            disconnect.cancel()
            await self._join(_gather_children([disconnect]), deadline)
            await self._send(writer, {
                **hello, "stdout": base64.b64encode(stdout).decode("ascii"),
                "stderr": base64.b64encode(stderr).decode("ascii"), "status": status},
                deadline)
            ack = verify(await _receive(reader, min(
                self.owner.limits.protocol_s, _remaining(deadline))), self.key)
            if (type(ack) is not dict or set(ack) != {"nonce", "seq", "received"}
                    or ack["nonce"] != hello["nonce"]
                    or type(ack["seq"]) is not int or ack["seq"] != hello["seq"]
                    or ack["received"] is not True):
                raise BridgeProtocolError("invalid delivery acknowledgment")
        except BaseException as error:
            self.primary_errors.append(error)
            self.owner.fail(error)
        finally:
            self.finalizing_handlers.add(task)
            try:
                for child in (work, disconnect):
                    if child is not None and not child.done():
                        child.cancel()
                children = [child for child in (work, disconnect) if child is not None]
                if children:
                    try:
                        outcomes = await self._join(_gather_children(children), deadline)
                        self.cleanup_errors.extend(
                            error for error in outcomes
                            if isinstance(error, BaseException)
                            and not isinstance(error, asyncio.CancelledError)
                            and not any(error is primary for primary in self.primary_errors))
                    except BaseException as error:
                        self.cleanup_errors.append(error)
                        self.owner.fail(error)
            finally:
                try:
                    writer.close()
                    await self._join(writer.wait_closed(), deadline)
                    self.unresolved_writers.discard(writer)
                except BaseException as error:
                    self.unresolved_writers.add(writer)
                    self.cleanup_errors.append(error)
                    self.owner.fail(error)
                finally:
                    if acquired:
                        self.busy = False
                    self.writers.discard(writer)
                    self.handlers.discard(task)
                    self.finalizing_handlers.discard(task)
                    self.owned_children.difference_update(
                        child for child in (work, disconnect)
                        if child is not None and child.done())
                    _DEADLINE.reset(token)

    async def _close(self, deadline):
        self.revoked = True
        if self.server is not None:
            self.server.close()
        for writer in tuple(self.writers | self.unresolved_writers):
            try:
                writer.close()
            except BaseException as error:
                self.unresolved_writers.add(writer)
                self.cleanup_errors.append(error)
        tasks = tuple(self.handlers)
        for task in tasks:
            if task not in self.finalizing_handlers:
                task.cancel()
        if tasks:
            await self._join(_gather_children(tasks), deadline)
        if self.owned_children:
            await self._join(_gather_children(tuple(self.owned_children)), deadline)
            self.owned_children = {task for task in self.owned_children if not task.done()}
        if self.server is not None:
            await self._join(self.server.wait_closed(), deadline)
        if self.cleanup_errors:
            raise BashBridgeError("capability cleanup fault") from self.cleanup_errors[0]
        if self.custody is not None:
            self.custody.close()
            self.custody = None

    async def close(self, deadline=None):
        self.revoked = True
        if self._close_task is None:
            deadline = deadline or _DEADLINE.get() or (
                asyncio.get_running_loop().time() + self.owner.limits.engine_s)
            self._close_deadline = deadline
            self._close_task = asyncio.create_task(self._close(deadline))
        await join_owned(self._close_task, self._close_deadline)


async def _gather_children(children):
    return await asyncio.gather(*children, return_exceptions=True)


class BashActionController:
    def __init__(self, *, binding: BashSqlBinding, runtime, root: Path,
                 limits: BridgeLimits):
        self.binding, self.runtime, self.root, self.limits = binding, runtime, root, limits
        self.pending = deque()
        self.ids: set[str] = set()
        self.fatal = asyncio.get_running_loop().create_future()
        self.control = _Capability(self, root / "control", "bash", self.dispatch)
        self.sql = None
        self.actor: str | None = None
        self.active: str | None = None
        self.closed = False
        self.cleanup_errors: list[BaseException] = []
        self._close_task = None
        self._close_deadline = None
        self._dispatch_watchdog = None
        self.operation_deadline = None
        self.owned_cleanup: set[asyncio.Task] = set()

    def fail(self, error: BaseException):
        self.binding._invalid = True
        if not self.fatal.done():
            self.fatal.set_result(
                error if isinstance(error, asyncio.CancelledError) else BashBridgeError(
                    f"Bash bridge invalid: {type(error).__name__}"))

    def check(self):
        if self.closed or self.fatal.done():
            raise BashBridgeError("Bash bridge closed or invalid")
        self.binding.check_binding()

    def register_response(self, response: Response) -> Response:
        try:
            self.check()
            if not isinstance(response, Response) or self.pending or self.active is not None:
                raise BashBridgeError("overlapping original response")
            calls = []
            for call in response.message.tool_calls or ():
                if (call.name != "bash" or call.type != "function"
                        or call.namespace is not None
                        or type(call.id) is not str or not 0 < len(call.id) <= 256
                        or call.id in self.ids or call.id in {item[0] for item in calls}):
                    raise BashBridgeError("unrecognized original tool call")
                args = decode(call.arguments.encode("utf-8"))
                if type(args) is not dict or set(args) != {"command"}:
                    raise BashBridgeError("invalid original Bash arguments")
                validate_command(args["command"])
                calls.append((call.id, args["command"]))
            if len(calls) + len(self.ids) > self.limits.pending_calls:
                raise BashBridgeError("too many original calls")
            self.pending.extend(calls)
            self.ids.update(item[0] for item in calls)
            if calls and (self._dispatch_watchdog is None or self._dispatch_watchdog.done()):
                self._dispatch_watchdog = asyncio.create_task(self._watch_dispatch())
            return response
        except BaseException as error:
            self.fail(error)
            raise

    async def _watch_dispatch(self):
        previous = None
        deadline = 0
        while not self.closed and not self.fatal.done() and (self.pending or self.active):
            current = self.pending[0][0] if self.pending and self.active is None else None
            if current != previous:
                previous = current
                deadline = asyncio.get_running_loop().time() + self.limits.protocol_s
            if current is not None and asyncio.get_running_loop().time() >= deadline:
                self.fail(BashBridgeError("original client never arrived"))
                return
            await asyncio.sleep(0.01)

    async def _execute_sql(self, query: str):
        self.check()
        if self.active is None:
            raise BashBridgeError("SQL outside original action")
        async with asyncio.timeout(_remaining()):
            result = await self.binding.execute_sql(query=query)
        wire = _dump_json(_envelope(
            "rows", columns=list(result.columns),
            rows=[[_encode_cell(cell) for cell in row] for row in result.rows]))
        if len(wire) > self.limits.output_bytes:
            raise BashBridgeError("SQL response overflow")
        return wire, b"", 0

    async def _finish_action(self, call_id: str, success: bool, deadline):
        errors = []
        if self.sql is not None:
            try:
                await self.sql.close(deadline)
            except BaseException as error:
                errors.append(error)
        if self.actor is not None:
            try:
                await self.runtime.retire_container(self.actor)
                self.actor = None
            except BaseException as error:
                errors.append(error)
        if errors:
            self.cleanup_errors.extend(errors)
            self.fail(errors[0])
            raise BashBridgeError("action retirement unresolved") from errors[0]
        self.sql = None
        if success and not self.fatal.done():
            _remaining(deadline)
            self.binding.after_action(call_id)
            self.active = None

    async def dispatch(self, command: str):
        self.check()
        validate_command(command)
        if self.active is not None or not self.pending or self.pending[0][1] != command:
            raise BashBridgeError("no matching next original dispatch")
        call_id, original = self.pending.popleft()
        self.binding.before_action(call_id)
        self.active = call_id
        complete = _DEADLINE.get() or (
            asyncio.get_running_loop().time() + SOCKET_TIMEOUT - 1)
        self.operation_deadline = complete
        retirement_deadline = complete - self.limits.delivery_s
        execution_deadline = retirement_deadline - self.limits.retirement_s
        token = _DEADLINE.set(execution_deadline)
        failure = None
        result = None
        try:
            self.sql = _Capability(
                self, self.root / f"sql-{secrets.token_hex(12)}", "sql",
                self._execute_sql)
            await self.sql.start()
            self.actor = f"cotrain-bash-action-{secrets.token_hex(16)}"
            self.runtime.owned_containers.add(self.actor)
            argv = self.runtime.actor_create_argv(
                self.actor, original, self.sql.directory)
            await self.runtime.engine_call(*argv)
            async with asyncio.timeout(self.limits.action_s):
                self.runtime.check_staging()
                attached = await self.runtime.engine_call(
                    "start", "--attach", self.actor, check=False,
                    timeout=self.limits.action_s)
                state = await self.runtime.inspect_container(self.actor)
                if (state["State"]["Status"] != "exited"
                        or state["State"].get("Error")
                        or state["State"].get("OOMKilled")
                        or type(state["State"]["ExitCode"]) is not int
                        or not 0 <= state["State"]["ExitCode"] <= 255
                        or attached[2] != state["State"]["ExitCode"]):
                    raise BashBridgeError("actor status unresolved")
                result = attached[0], attached[1], state["State"]["ExitCode"]
        except BaseException as error:
            failure = error
            self.fail(error)
        finally:
            _DEADLINE.reset(token)
        token = _DEADLINE.set(retirement_deadline)
        try:
            cleanup = asyncio.create_task(
                self._finish_action(call_id, failure is None, retirement_deadline))
            self.owned_cleanup.add(cleanup)
            await join_owned(cleanup, retirement_deadline)
        except BaseException as error:
            self.fail(error)
            if failure is None:
                failure = error
            else:
                self.cleanup_errors.append(error)
        finally:
            self.owned_cleanup = {task for task in self.owned_cleanup if not task.done()}
            _DEADLINE.reset(token)
        if failure is not None:
            raise failure
        return result

    async def race_policy(self, awaitable):
        policy = asyncio.create_task(awaitable)
        failure = None
        result = None
        try:
            done, _ = await asyncio.wait(
                (policy, self.fatal), return_when=asyncio.FIRST_COMPLETED)
            if self.fatal in done or self.fatal.done():
                raise self.fatal.result()
            result = policy.result()
            # Acknowledgments and action retirement must finish even if the SDK
            # swallowed a failed client and returned exit code zero.
            handlers = tuple(self.control.handlers)
            if handlers:
                deadline = self.operation_deadline or (
                    asyncio.get_running_loop().time() + self.limits.protocol_s)
                handlers_join = asyncio.create_task(_gather_children(handlers))
                self.owned_cleanup.add(handlers_join)
                try:
                    await join_owned(handlers_join, deadline)
                finally:
                    if handlers_join.done():
                        self.owned_cleanup.discard(handlers_join)
            self.check()
            if self.pending or self.active is not None or self.actor is not None:
                raise BashBridgeError("policy left unresolved original dispatches")
        except BaseException as error:
            failure = error
            self.fail(error)
        finally:
            if not policy.done():
                policy.cancel()
            cleanup = asyncio.create_task(_gather_children([policy]))
            self.owned_cleanup.add(cleanup)
            try:
                deadline = self.operation_deadline or (
                    asyncio.get_running_loop().time() + self.limits.engine_s)
                outcomes = await join_owned(cleanup, deadline)
                self.cleanup_errors.extend(
                    error for error in outcomes if isinstance(error, BaseException)
                    and error is not failure)
            except BaseException as secondary:
                self.cleanup_errors.append(secondary)
                self.fail(secondary)
                if failure is None:
                    failure = secondary
            finally:
                self.owned_cleanup = {
                    task for task in self.owned_cleanup if not task.done()}
        if failure is not None:
            raise failure
        return result

    async def _close(self, deadline):
        self.closed = True
        errors = []
        if self._dispatch_watchdog is not None:
            self._dispatch_watchdog.cancel()
            try:
                await join_owned(asyncio.create_task(
                    _gather_children([self._dispatch_watchdog])), deadline)
            except BaseException as error:
                errors.append(error)
        for capability in (self.control, self.sql):
            if capability is not None:
                try:
                    await capability.close(deadline)
                except BaseException as error:
                    errors.append(error)
        for name in tuple(self.runtime.owned_containers):
            try:
                async with asyncio.timeout(_remaining(deadline)):
                    await self.runtime.retire_container(name)
            except BaseException as error:
                self.cleanup_errors.append(error)
                self.fail(error)
                errors.append(error)
        try:
            async with asyncio.timeout(_remaining(deadline)):
                await self.binding.aclose()
        except BaseException as error:
            errors.append(error)
        if errors or self.runtime.owned_containers or self.owned_cleanup:
            if errors and isinstance(errors[0], asyncio.CancelledError):
                for secondary in errors[1:]:
                    errors[0].add_note(f"secondary cleanup: {type(secondary).__name__}")
                raise errors[0]
            raise BashBridgeError("owned cleanup remains unresolved") from (
                errors[0] if errors else None)

    async def aclose(self):
        if self._close_task is None:
            self._close_deadline = _DEADLINE.get() or (
                asyncio.get_running_loop().time() + self.limits.retirement_s)
            self._close_task = asyncio.create_task(self._close(self._close_deadline))
        try:
            await join_owned(self._close_task, self._close_deadline)
        except BaseException as error:
            self.fail(error)
            raise


class BashOwnedDockerRuntime(DockerRuntime):
    """Linux-local experimental owner; no isinstance-based qualification."""

    def __init__(self, config: DockerConfig, *, harness: BashHarness,
                 binding: BashSqlBinding, interpreter: str, scratch: Path,
                 engine_binary: str = "/usr/bin/docker",
                 limits: BridgeLimits = BridgeLimits(), mcp_urls: dict | None = None):
        if type(config) is not DockerConfig:
            raise BashBridgeError("original DockerConfig required")
        require_bash_only(harness, mcp_urls or {})
        if (type(binding) is not BashSqlBinding or binding._harness is not harness
                or type(limits) is not BridgeLimits):
            raise BashBridgeError("original task binding required")
        if (not re.fullmatch(r"/[A-Za-z0-9_./-]+", interpreter)
                or str(PurePosixPath(interpreter)) != interpreter
                or "\n" in interpreter):
            raise BashBridgeError("absolute offline interpreter required")
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", engine_binary):
            raise BashBridgeError("absolute Docker executable required")
        super().__init__(config)
        if self.network_restricted or config.gpu or config.disk:
            raise BashBridgeError("unsupported network/GPU/disk profile")
        self.binding, self.harness = binding, harness
        self.interpreter, self.engine_binary = interpreter, engine_binary
        self.scratch, self.limits = Path(scratch), limits
        self.owned_containers: set[str] = set()
        self.retirement_attempts: set[str] = set()
        self.workspace: str | None = None
        self.image_id: str | None = None
        self.root: Path | None = None
        self.controller: BashActionController | None = None
        self._policy_claimed = False
        self._teardown_task = None
        self._teardown_deadline = None
        self._started_once = False
        self.host_artifacts: list[Path] = []
        self.custodies: list[_Directory] = []
        self.cleanup_errors: list[BaseException] = []
        self.engine_tasks: set[asyncio.Task] = set()
        self.engine_processes: set = set()
        self.message_files: set[str] = set()
        self._policy_deadline = None

    def _close_engine_pipes(self, proc):
        errors = []
        for stream in (proc.stdout, proc.stderr):
            try:
                stream._transport.close()
            except BaseException as error:
                errors.append(error)
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except BaseException as error:
                errors.append(error)
        if errors:
            raise errors[0]

    async def engine_call(self, *argv, check=True, timeout=None, input=None,
                          _on_issued=None, _output_limit=None):
        deadline = _DEADLINE.get() or (
            asyncio.get_running_loop().time() + (timeout or self.limits.engine_s))
        duration = min(timeout or self.limits.engine_s, _remaining(deadline))
        if input is not None and (type(input) is not bytes
                                   or len(input) > self.limits.output_bytes):
            raise BashBridgeError("bounded engine input required")
        output_limit = self.limits.output_bytes if _output_limit is None else _output_limit
        if (type(output_limit) is not int
                or not 0 < output_limit <= self.limits.output_bytes + 1):
            raise BashBridgeError("bounded engine output required")

        async def launch():
            _remaining(deadline)
            if _on_issued is not None:
                _on_issued()
            return await asyncio.create_subprocess_exec(
                self.engine_binary, "--host", "unix:///var/run/docker.sock", *argv,
                stdin=(asyncio.subprocess.PIPE if input is not None
                       else asyncio.subprocess.DEVNULL), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env={"PATH": "/usr/bin:/bin"})

        spawning = asyncio.create_task(launch())
        self.engine_tasks.add(spawning)
        proc = None
        abandoned = False

        def spawned(task):
            if not task.cancelled() and task.exception() is None:
                process = task.result()
                self.engine_processes.add(process)
                if abandoned:
                    try:
                        if process.returncode is None:
                            process.kill()
                        self._close_engine_pipes(process)
                    except BaseException as error:
                        self.cleanup_errors.append(error)
                        if self.controller is not None:
                            self.controller.fail(error)

        spawning.add_done_callback(spawned)
        count = 0

        async def read(stream):
            nonlocal count
            chunks = []
            while True:
                data = await stream.read(16384)
                if not data:
                    return b"".join(chunks)
                count += len(data)
                if count > output_limit:
                    raise BashBridgeError("engine or actor output overflow")
                chunks.append(data)

        async def feed():
            proc.stdin.write(input)
            await proc.stdin.drain()
            proc.stdin.close()

        readers = []
        failure = None
        result = None
        try:
            async with asyncio.timeout(duration):
                proc = await asyncio.shield(spawning)
                readers = [asyncio.create_task(read(proc.stdout)),
                           asyncio.create_task(read(proc.stderr))]
                if input is not None:
                    readers.append(asyncio.create_task(feed()))
                self.engine_tasks.update(readers)
                values = await asyncio.gather(*readers)
                stdout, stderr = values[:2]
                code = await proc.wait()
            if check and code != 0:
                raise BashBridgeError("Docker operation failed")
            result = stdout, stderr, code
        except BaseException as error:
            failure = error
        finally:
            abandoned = True
            if proc is None and spawning.done() and not spawning.cancelled():
                try:
                    proc = spawning.result()
                except BaseException:
                    pass
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except BaseException as secondary:
                    self.cleanup_errors.append(secondary)
                    if failure is None:
                        failure = secondary
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            async def settle(child):
                nonlocal failure
                self.engine_tasks.add(child)
                cleanup = asyncio.create_task(_gather_children([child]))
                self.engine_tasks.add(cleanup)
                try:
                    outcomes = await join_owned(cleanup, deadline)
                    for secondary in outcomes:
                        if isinstance(secondary, BaseException) and secondary is not failure:
                            self.cleanup_errors.append(secondary)
                            if failure is None:
                                failure = secondary
                except BaseException as secondary:
                    self.cleanup_errors.append(secondary)
                    if failure is None:
                        failure = secondary
                return child.done() and not child.cancelled() and child.exception() is None

            for reader in readers:
                await settle(reader)
            reaped = False
            if proc is not None:
                pipes_closed = False
                try:
                    # Paused asyncio pipe transports can otherwise block wait after kill.
                    self._close_engine_pipes(proc)
                    pipes_closed = True
                except BaseException as secondary:
                    self.cleanup_errors.append(secondary)
                    if failure is None:
                        failure = secondary
                reaped = await settle(asyncio.create_task(proc.wait())) and pipes_closed
            elif not spawning.done():
                await settle(spawning)
            self.engine_tasks = {task for task in self.engine_tasks if not task.done()}
            if reaped:
                self.engine_processes.discard(proc)
            if failure is not None:
                try:
                    controller = self.controller
                    if controller is not None:
                        controller.fail(failure)
                except BaseException as secondary:
                    self.cleanup_errors.append(secondary)
        if failure is not None:
            raise failure
        return result

    async def inspect_container(self, name: str):
        stdout, _, _ = await self.engine_call("container", "inspect", name)
        value = decode(stdout)
        if (type(value) is not list or len(value) != 1
                or value[0].get("Name") != f"/{name}"
                or not re.fullmatch(r"[0-9a-f]{64}", value[0].get("Id", ""))):
            raise BashBridgeError("container identity unresolved")
        return value[0]

    async def retire_container(self, name: str):
        if name not in self.owned_containers or name in self.retirement_attempts:
            raise BashBridgeError("container not owned or retirement already attempted")
        def issued():
            if name in self.retirement_attempts:
                raise BashBridgeError("retirement already attempted")
            self.retirement_attempts.add(name)

        await self.engine_call("container", "rm", "--force", name, _on_issued=issued)
        stdout, _, _ = await self.engine_call(
            "container", "ls", "--all", "--quiet", "--no-trunc",
            "--filter", f"name=^/{name}$")
        if stdout.strip():
            raise BashBridgeError("container removal not observed")
        self.owned_containers.remove(name)

    def actor_create_argv(self, name: str, command: str, sql_directory: Path):
        validate_command(command)
        self.check_staging()
        if any(c in str(sql_directory) for c in ",:\0"):
            raise BashBridgeError("unsafe SQL mount path")
        if not self.workspace or not self.image_id or self.root is None:
            raise BashBridgeError("actor infrastructure unavailable")
        return (
            "create", "--pull=never", "--no-healthcheck", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "0:0",
            "--cpus", str(self.limits.cpu), "--memory", str(self.limits.memory_bytes),
            "--memory-swap", str(self.limits.memory_bytes),
            "--pids-limit", str(self.limits.pids), "--ulimit", "nofile=128:128",
            "--log-driver", "none", "--workdir", "/workspace",
            "--mount", f"type=volume,src={self.workspace},dst=/workspace",
            "--mount", f"type=bind,src={sql_directory},dst=/bridge-sql,readonly",
            "--mount", f"type=bind,src={self.root / 'sql-bin'},dst=/bridge-bin,readonly",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=67108864",
            "--entrypoint", "/usr/bin/env", self.image_id,
            "-i", "PATH=/bridge-bin:/usr/local/bin:/usr/bin:/bin",
            "HOME=/workspace", "/bin/bash", "-c", command)

    def check_staging(self):
        for custody in self.custodies:
            custody.check()
        if self.controller is not None:
            for capability in (self.controller.control, self.controller.sql):
                if capability is not None and capability.custody is not None:
                    capability.custody.check()

    def workspace_create_argv(self):
        return ("volume", "create", "--driver", "local",
                "--opt", "type=tmpfs", "--opt", "device=tmpfs", "--opt",
                f"o=size={self.limits.workspace_bytes},nr_inodes={self.limits.workspace_inodes},"
                "uid=0,gid=0,mode=0700",
                self.workspace)

    async def create_workspace(self):
        await self.engine_call(*self.workspace_create_argv())
        stdout, _, _ = await self.engine_call("volume", "inspect", self.workspace)
        value = decode(stdout)
        expected = {
            "type": "tmpfs", "device": "tmpfs",
            "o": f"size={self.limits.workspace_bytes},nr_inodes={self.limits.workspace_inodes},"
                 "uid=0,gid=0,mode=0700",
        }
        if (type(value) is not list or len(value) != 1
                or value[0].get("Name") != self.workspace
                or value[0].get("Driver") != "local"
                or value[0].get("Options") != expected):
            raise BashBridgeError("bounded local tmpfs workspace options required")

    async def start(self):
        if self._started_once:
            raise BashBridgeError("runtime start cannot be replayed")
        self._started_once = True
        if (sys.platform != "linux"
                or not stat.S_ISSOCK(os.stat("/var/run/docker.sock").st_mode)):
            raise BashBridgeError("local Linux Unix-engine transport required")
        scratch = _Directory(self.scratch)
        self.custodies.append(scratch)
        if (not re.fullmatch(r"/[A-Za-z0-9_/-]+", self.config.workdir)
                or str(PurePosixPath(self.config.workdir)) != self.config.workdir
                or self.config.workdir.startswith("//")
                or self.config.workdir in ("/", "/tmp")
                or self.config.workdir.startswith("/bridge-")):
            raise BashBridgeError("private scratch and plain workdir required")
        stdout, _, _ = await self.engine_call("image", "inspect", self.config.image)
        images = decode(stdout)
        if (type(images) is not list or len(images) != 1
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", images[0].get("Id", ""))
                or images[0].get("Config", {}).get("Volumes")):
            raise BashBridgeError("existing image without implicit volumes required")
        self.image_id = images[0]["Id"]
        root = scratch.child("bb-" + secrets.token_hex(6), 0o700)
        self.custodies.append(root)
        self.root = root.path
        if len(os.fsencode(self.root / ("sql-" + "a" * 24) / "socket")) > 100:
            raise BashBridgeError("short canonical private scratch required")
        self.host_artifacts.append(self.root)
        directories = {}
        for directory in ("policy-bin", "sql-bin", "program"):
            directories[directory] = root.child(directory)
            self.custodies.append(directories[directory])
        source = Path(__file__).with_name("bash_bridge_client.py").read_bytes()
        source = b"#!" + self.interpreter.encode("ascii") + b"\n" + source.split(b"\n", 1)[1]
        for directory, executable in (("policy-bin", "bash"), ("sql-bin", "sql")):
            directories[directory].stage(executable, source, 0o555)
            directories[directory].stage_link(
                "capability", "/bridge-control" if executable == "bash" else "/bridge-sql")
        directories["program"].stage("chat.py", CHAT_PROGRAM_SOURCE.encode("utf-8"), 0o444)
        self.controller = BashActionController(
            binding=self.binding, runtime=self, root=self.root, limits=self.limits)
        await self.controller.control.start()
        self.workspace = f"cotrain-bash-workspace-{secrets.token_hex(16)}"
        # Keep the name before the ambiguous engine await.
        await self.create_workspace()
        self._container = f"cotrain-bash-policy-{secrets.token_hex(16)}"
        self.owned_containers.add(self._container)
        self.check_staging()
        await self.engine_call(*self.policy_create_argv())
        state = await self.inspect_container(self._container)
        self.info.id = state["Id"][:12]
        self.check_staging()
        await self.engine_call("start", self._container)
        # Import only installed dependencies, no resolver or installer fallback.
        await self.engine_call(
            "exec", self._container, self.interpreter, "-I", "-c",
            "import openai, mcp, httpx, httpx2, tenacity")

    def policy_create_argv(self):
        self.check_staging()
        return (
            "create", "--pull=never", "--no-healthcheck", "--name", self._container,
            "--network", "host", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "0:0",
            "--cpus", str(self.config.cpu or self.limits.cpu),
            "--memory", str(int(self.config.memory * 1024**3)
                            if self.config.memory else self.limits.memory_bytes),
            "--pids-limit", str(self.limits.pids),
            "--log-driver", "none", "--workdir", self.config.workdir,
            "--tmpfs", f"{self.config.workdir}:rw,nosuid,size=134217728",
            "--tmpfs", "/tmp:rw,nosuid,size=134217728",
            "--mount", f"type=bind,src={self.root / 'policy-bin'},dst=/bridge-bin,readonly",
            "--mount", f"type=bind,src={self.root / 'program'},dst=/bridge-program,readonly",
            "--mount", f"type=bind,src={self.root / 'control'},dst=/bridge-control,readonly",
            "--mount", f"type=volume,src={self.workspace},dst=/bridge-workspace-keeper,readonly",
            "--entrypoint", self.interpreter, self.image_id,
            "-I", "-S", "-c", "import time; time.sleep(86400)")

    def host_url(self, url: str) -> str:
        return url

    async def expose(self, port: int) -> str:
        raise BashBridgeError("additional services not supported by Bash-only bridge")

    async def prepare_execution(self, routes: list[str] | None) -> None:
        if self.network_restricted:
            raise BashBridgeError("network policy unsupported, never silently bypassed")

    async def prepare_uv_script(self, script: str | bytes,
                                env: dict[str, str] | None = None, *,
                                activate: bool = True) -> list[str]:
        data = script.encode("utf-8") if isinstance(script, str) else script
        if data != CHAT_PROGRAM_SOURCE.encode("utf-8") or self.controller is None:
            raise BashBridgeError("only unchanged original bundled chat program supported")
        self.controller.check()
        self._begin_policy_operation()
        return [self.interpreter, "/bridge-program/chat.py"]

    def _begin_policy_operation(self):
        if self._policy_deadline is None:
            self._policy_deadline = asyncio.get_running_loop().time() + self.limits.policy_s
        _remaining(self._policy_deadline)
        return self._policy_deadline

    async def write(self, path: str, data: bytes) -> None:
        if (not re.fullmatch(r"\.vf-initial-messages-[A-Za-z0-9_-]+\.json", path)
                or path in self.message_files or self._policy_claimed
                or type(data) is not bytes or len(data) > self.limits.output_bytes):
            raise BashBridgeError("only bounded original message-file staging supported")
        token = _DEADLINE.set(self._begin_policy_operation())
        try:
            await self.engine_call(
                "exec", "-i", "--workdir", self.config.workdir, self._container,
                self.interpreter, "-I", "-c",
                "import os,sys; f=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|"
                "os.O_EXCL|os.O_NOFOLLOW,0o600); "
                "s=os.fdopen(f,'wb'); s.write(sys.stdin.buffer.read()); s.close()",
                path, input=data)
            self.message_files.add(path)
        finally:
            _DEADLINE.reset(token)

    async def _read(self, path: str, max_bytes: int | None = None) -> bytes:
        if (path not in self.message_files or (max_bytes is not None and (
                type(max_bytes) is not int or not 0 <= max_bytes <= self.limits.output_bytes + 1))):
            raise BashBridgeError("unsupported or unbounded file read")
        token = _DEADLINE.set(self._begin_policy_operation())
        try:
            stdout, _, _ = await self.engine_call(
                "exec", "--workdir", self.config.workdir, self._container,
                self.interpreter, "-I", "-c",
                "import os,sys; f=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW); "
                "s=os.fdopen(f,'rb'); sys.stdout.buffer.write(s.read(int(sys.argv[2]))); "
                "s.close()", path,
                str(self.limits.output_bytes + 1 if max_bytes is None else max_bytes),
                _output_limit=self.limits.output_bytes + 1)
            return stdout
        finally:
            _DEADLINE.reset(token)

    async def run(self, argv: list[str], env: dict[str, str]) -> ProgramResult:
        if self._container not in self.owned_containers:
            raise BashBridgeError("policy container unavailable")
        values = self.process_env(env)
        arguments = [arg for key, value in values.items()
                     for arg in ("--env", f"{key}={value}")]
        stdout, stderr, status = await self.engine_call(
            "exec", *arguments, "--workdir", self.config.workdir,
            self._container, *argv, check=False, timeout=self.limits.policy_s)
        return ProgramResult(status, stdout.decode("utf-8", errors="replace"),
                             stderr.decode("utf-8", errors="replace"))

    def _exec(self, env: dict[str, str], *, stdin: bool = False) -> list[str]:
        raise BashBridgeError("inherited unbounded container helpers refused")

    async def run_background(self, argv: list[str], env: dict[str, str], log: str) -> None:
        raise BashBridgeError("additional background services refused")

    async def open_process(self, argv: list[str], env: dict[str, str]):
        raise BashBridgeError("additional live processes refused")

    async def run_program(self, argv: list[str], env: dict[str, str]) -> ProgramResult:
        require_bash_only(self.harness, {})
        if (self._policy_claimed or self.controller is None
                or argv[:2] != [self.interpreter, "/bridge-program/chat.py"]
                or "--bash" not in argv
                or any(arg.split("=", 1)[0] in {
                    "--edit", "--search", "--mcp-config"
                } for arg in argv[2:])):
            raise BashBridgeError("one original Bash-only policy launch required")
        messages = [arg for arg in argv[2:] if arg.startswith("--initial-messages-file")]
        if messages and (len(messages) != 1 or messages[0] not in {
                f"--initial-messages-file={path}" for path in self.message_files}):
            raise BashBridgeError("original staged message file required")
        self._policy_claimed = True
        values = self.process_env(env)
        if any(key.startswith(("LD_", "DYLD_", "PYTHON"))
               or key in {"BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS"}
               for key in values):
            raise BashBridgeError("policy interpreter/shell injection environment refused")
        values["PATH"] = "/bridge-bin:/usr/local/bin:/usr/bin:/bin"
        controller = self.controller
        token = _DEADLINE.set(self._begin_policy_operation())
        try:
            result = await controller.race_policy(self.run(argv, values))
            await join_owned(asyncio.create_task(controller.control.close()))
            controller.check()
            return result
        except BaseException:
            try:
                await join_owned(asyncio.create_task(controller.aclose()))
            except BaseException as secondary:
                controller.cleanup_errors.append(secondary)
            raise
        finally:
            _DEADLINE.reset(token)

    async def _teardown_owned(self):
        errors = []
        deadline = _DEADLINE.get()
        for task in tuple(self.engine_tasks):
            try:
                await join_owned(task, deadline)
            except BaseException as error:
                errors.append(error)
            if task.done():
                self.engine_tasks.discard(task)
        for proc in tuple(self.engine_processes):
            try:
                if proc.returncode is None:
                    proc.kill()
                self._close_engine_pipes(proc)
                waiter = asyncio.create_task(proc.wait())
                self.engine_tasks.add(waiter)
                await join_owned(waiter, deadline)
                self.engine_tasks.discard(waiter)
                self.engine_processes.discard(proc)
            except BaseException as error:
                errors.append(error)
        controller = None
        try:
            controller = self.controller
            if controller is not None:
                await controller.aclose()
        except BaseException as error:
            errors.append(error)
        for name in tuple(self.owned_containers):
            if name in self.retirement_attempts:
                continue
            try:
                await self.retire_container(name)
            except BaseException as error:
                errors.append(error)
        if not self.owned_containers and self.workspace is not None:
            try:
                await self.engine_call("volume", "rm", self.workspace)
                stdout, _, _ = await self.engine_call(
                    "volume", "ls", "--quiet", "--filter", f"name=^{self.workspace}$")
                if stdout.strip():
                    raise BashBridgeError("workspace retirement not observed")
                self.workspace = None
            except BaseException as error:
                errors.append(error)
        if errors or self.owned_containers or self.engine_tasks or self.engine_processes:
            raise BashBridgeError("owned cleanup unresolved") from (errors[0] if errors else None)
        if controller is not None:
            for capability in (controller.control, controller.sql):
                if capability is not None and capability.custody is not None:
                    capability.custody.close()
                    capability.custody = None
        for custody in reversed(self.custodies):
            custody.close()
        self.custodies.clear()

    async def teardown(self) -> None:
        if self._teardown_task is None:
            self._teardown_deadline = asyncio.get_running_loop().time() + self.limits.retirement_s
            self._teardown_task = asyncio.create_task(
                self._teardown_with_deadline(self._teardown_deadline))
        await join_owned(self._teardown_task, self._teardown_deadline)

    async def _teardown_with_deadline(self, deadline):
        token = _DEADLINE.set(deadline)
        try:
            await self._teardown_owned()
        finally:
            _DEADLINE.reset(token)

    def cleanup(self) -> None:
        # Never invoke inherited best-effort cleanup that drops ambiguous names.
        # Explicit async owner teardown is mandatory for borrowed runtimes.
        if self.owned_containers or self.workspace is not None:
            raise BashBridgeError("explicit async Bash bridge teardown required")

    def require_valid(self) -> None:
        if (self._teardown_task is None or not self._teardown_task.done()
                or self.controller is None or self.controller.fatal.done()
                or self.owned_containers or self.workspace is not None
                or self.engine_tasks or self.engine_processes or self.cleanup_errors):
            raise BashBridgeError("experimental rollout not fully settled")
        self._teardown_task.result()
        self.binding.require_valid()
