"""Parent-run transport checks. No native Docker qualification."""

import asyncio
import os
from pathlib import Path
import selectors
import socket
import signal
import stat
import struct
import subprocess
import sys
import tempfile

import pytest
from verifiers.v1.harnesses.utils.core import run_bash

from ptc import bash_bridge_client as client
from ptc import bash_owned_runtime as owned
from ptc.bash_owned_runtime import BridgeLimits, _Capability, _receive, join_owned


_UNRESOLVED_SEAM_CHILDREN = []
_UNRESOLVED_SEAM_CAPABILITIES = []


@pytest.fixture
def tmp_path():
    raw = os.environ.get("TMPDIR")
    if not raw:
        raise owned.BashBridgeError("explicit parent TMPDIR required")
    root = Path(raw)
    if not root.is_absolute() or str(root.resolve(strict=True)) != raw:
        raise owned.BashBridgeError("canonical parent TMPDIR required")
    info = root.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise owned.BashBridgeError("owned 0700 parent TMPDIR required")
    custody = owned._Directory(root)
    try:
        path = Path(tempfile.mkdtemp(prefix="bc-", dir=root))
        path.chmod(0o700)
        custody.check()
        return path
    finally:
        custody.close()


class Owner:
    limits = BridgeLimits()

    def __init__(self):
        self.errors = []

    def fail(self, error):
        self.errors.append(error)


def test_duplicate_json_and_oversized_frames_refuse():
    with pytest.raises(client.BridgeProtocolError):
        client.decode(b'{"seq":1,"seq":2}')
    with pytest.raises(client.BridgeProtocolError):
        client.pack({"value": "x" * client.FRAME_MAX})
    left, right = socket.socketpair()
    try:
        left.sendall(struct.pack("!I", client.FRAME_MAX + 1))
        with pytest.raises(client.BridgeProtocolError):
            client.receive(right)
    finally:
        left.close()
        right.close()


def test_authentication_and_command_validation():
    key = b"k" * 32
    signed = client.sign({"seq": 0}, key)
    assert client.verify(signed, key) == {"seq": 0}
    signed["body"]["seq"] = 1
    with pytest.raises(client.BridgeProtocolError):
        client.verify(signed, key)
    for bad in ("x\0y", "x" * (client.COMMAND_MAX + 1), None):
        with pytest.raises(client.BridgeProtocolError):
            client.validate_command(bad)


def test_exact_separate_output_and_status(tmp_path):
    async def scenario():
        owner = Owner()
        seen = []
        command = "printf 'a\\n' | cat; printf 'err\\n' >&2; exit 7"

        async def execute(value):
            seen.append(os.fsencode(value))
            return b"a\n", b"err\n", 7

        capability = _Capability(owner, tmp_path / "capability", "bash", execute)
        await capability.start()
        try:
            result = await asyncio.to_thread(
                client.exchange, directory=capability.directory,
                operation="bash", value=command)
            assert result == (b"a\n", b"err\n", 7)
            assert seen == [os.fsencode(command)]
            await asyncio.sleep(0)
            assert owner.errors == []
        finally:
            await capability.close()
    asyncio.run(scenario())


def test_close_joins_successful_handler_finalization(tmp_path, monkeypatch):
    async def scenario():
        owner, seen = Owner(), []
        entered, release, close_join = asyncio.Event(), asyncio.Event(), asyncio.Event()
        handlers = []
        counts = {"cleanup": 0, "completed": 0}
        original_gather = owned._gather_children
        command = "printf 'a\\n' | cat; printf 'err\\n' >&2; exit 7"

        async def execute(value):
            seen.append(os.fsencode(value))
            return b"a\n", b"err\n", 7

        capability = _Capability(owner, tmp_path / "capability", "bash", execute)

        async def gather(children):
            children = tuple(children)
            if len(children) == 2:
                counts["cleanup"] += 1
                handlers.append(next(iter(capability.handlers)))
                assert all(child.done() for child in children)
                entered.set()
                await release.wait()
                result = await original_gather(children)
                counts["completed"] += 1
                return result
            if handlers and children == (handlers[0],):
                close_join.set()
            return await original_gather(children)

        monkeypatch.setattr(owned, "_gather_children", gather)
        await capability.start()
        closers = []
        try:
            result = await asyncio.to_thread(
                client.exchange, directory=capability.directory,
                operation="bash", value=command)
            assert result == (b"a\n", b"err\n", 7)
            assert seen == [os.fsencode(command)]
            await asyncio.wait_for(entered.wait(), 1)
            closers = [asyncio.create_task(capability.close()) for _ in range(2)]
            await asyncio.wait_for(close_join.wait(), 1)
            handler = handlers[0]
            assert handler.cancelling() == 0
            assert not handler.done() and all(not closer.done() for closer in closers)
            assert capability.revoked
            assert capability.handlers == capability.finalizing_handlers == {handler}
            assert counts == {"cleanup": 1, "completed": 0}
            assert owner.errors == capability.primary_errors == capability.cleanup_errors == []
        finally:
            release.set()
            if closers:
                await asyncio.wait_for(asyncio.gather(*closers), 2)
            else:
                await capability.close()
        assert counts == {"cleanup": 1, "completed": 1}
        assert owner.errors == capability.primary_errors == capability.cleanup_errors == []
        assert capability._close_task.done() and handler.done()
        assert capability.handlers == capability.finalizing_handlers == set()
        assert capability.writers == capability.unresolved_writers == set()
        assert capability.owned_children == set() and capability.busy is False
        assert capability.custody is None
    asyncio.run(scenario())


def test_unchanged_sdk_path_lookup_real_client(tmp_path):
    if os.environ.get("BASH_BRIDGE_PARENT_SEAM") != "approved-child-profile":
        pytest.skip("separate parent-supervised child seam profile only")

    async def scenario():
        owner = Owner()
        seen = []

        async def execute(command):
            seen.append(command)
            return b"SDK_CLIENT_REACHED\n", b"separate\n", 9

        capability = _Capability(owner, tmp_path / "capability", "bash", execute)
        process = None
        read_fd = write_fd = None
        observer = None
        failure, cleanup_errors = None, []
        try:
            await capability.start()
            executable = tmp_path / "bash"
            source = Path(client.__file__).read_bytes().split(b"\n", 1)[1]
            executable.write_bytes(b"#!" + os.fsencode(sys.executable) + b"\n" + source)
            executable.chmod(0o555)
            environment = {
                "PATH": str(tmp_path) + os.pathsep + "/usr/bin:/bin",
                "HOME": str(tmp_path), "TMPDIR": str(tmp_path), "LANG": "C", "LC_ALL": "C",
            }
            output_path, error_path = tmp_path / "child.stdout", tmp_path / "child.stderr"
            read_fd, write_fd = os.pipe()
            os.set_blocking(read_fd, False)
            observer = selectors.DefaultSelector()
            observer.register(read_fd, selectors.EVENT_READ)
            with output_path.open("xb") as output_file, error_path.open("xb") as error_file:
                process = subprocess.Popen(
                    [sys.executable, "-m", "ptc.test_bash_bridge_client",
                     "--sdk-seam-child", str(write_fd)],
                    env=environment, stdin=subprocess.DEVNULL, stdout=output_file,
                    stderr=error_file, start_new_session=True, close_fds=True,
                    pass_fds=(write_fd,), cwd=Path(__file__).resolve().parents[1])
                os.close(write_fd)
                write_fd = None
                deadline = asyncio.get_running_loop().time() + 5
                frames = bytearray()
                while bytes(frames) != b"READY\nDONE\n":
                    if asyncio.get_running_loop().time() >= deadline:
                        raise TimeoutError("isolated SDK child profile deadline")
                    if observer.select(0):
                        block = os.read(read_fd, 12)
                        if not block:
                            raise AssertionError("SDK child ended before terminal hold")
                        frames.extend(block)
                        if not b"READY\nDONE\n".startswith(frames):
                            raise AssertionError("invalid SDK child completion frame")
                    await asyncio.sleep(0.01)
            output = output_path.read_text()
            assert output == "SDK_CLIENT_REACHED\nseparate\n"
            assert error_path.read_bytes() == b""
            assert seen == ["printf untouched | cat"]
            await asyncio.sleep(0)
            assert owner.errors == []
        except BaseException as error:
            failure = error
        finally:
            try:
                if process is not None:
                    try:
                        # No poll/wait/communicate before signaling this unreaped owned leader.
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    except BaseException as error:
                        cleanup_errors.append(error)
                    finally:
                        try:
                            status = process.wait(timeout=1)
                            if failure is None:
                                assert status == -signal.SIGKILL
                        except BaseException as error:
                            cleanup_errors.append(error)
                            if process.returncode is None:
                                _UNRESOLVED_SEAM_CHILDREN.append(process)
            finally:
                try:
                    if observer is not None:
                        try:
                            observer.close()
                        except BaseException as error:
                            cleanup_errors.append(error)
                finally:
                    try:
                        for fd in (read_fd, write_fd):
                            if fd is not None:
                                try:
                                    os.close(fd)
                                except BaseException as error:
                                    cleanup_errors.append(error)
                    finally:
                        try:
                            await capability.close()
                        except BaseException as error:
                            cleanup_errors.append(error)
                            _UNRESOLVED_SEAM_CAPABILITIES.append(capability)
            if failure is not None:
                if cleanup_errors:
                    raise failure from cleanup_errors[0]
                raise failure
            if cleanup_errors:
                raise cleanup_errors[0]
    asyncio.run(scenario())


def sdk_seam_child(frame_fd):
    os.write(frame_fd, b"READY\n")
    result = run_bash("printf untouched | cat")
    sys.stdout.write(result)
    sys.stdout.flush()
    os.write(frame_fd, b"DONE\n")
    while True:
        signal.pause()


@pytest.mark.parametrize("fault", ["replay", "overflow", "lost", "wrong-operation"])
def test_private_faults_no_extra_execution(tmp_path, fault):
    async def scenario():
        owner = Owner()
        executions = []

        async def execute(command):
            executions.append(command)
            return b"", b"", 0

        capability = _Capability(owner, tmp_path / "capability", "bash", execute)
        await capability.start()
        reader, writer = await asyncio.open_unix_connection(
            str(capability.directory / "socket"))
        try:
            hello = client.verify(await _receive(reader, 1), capability.key)
            request = {**hello, "op": "bash", "value": "printf exact"}
            if fault == "overflow":
                writer.write(struct.pack("!I", client.FRAME_MAX + 1))
            elif fault == "lost":
                writer.close()
            else:
                if fault == "replay":
                    request["seq"] += 1
                else:
                    request["op"] = "sql"
                writer.write(client.pack(client.sign(request, capability.key)))
            if not writer.is_closing():
                await writer.drain()
            for _ in range(100):
                if owner.errors:
                    break
                await asyncio.sleep(0.001)
            assert len(owner.errors) == 1
            assert executions == []
        finally:
            writer.close()
            await capability.close()
    asyncio.run(scenario())


def test_captured_authenticated_request_replay_zero_additional(tmp_path):
    async def scenario():
        owner, executions = Owner(), []

        async def execute(command):
            executions.append(command)
            return b"literal control-looking output", b"", 0

        capability = _Capability(owner, tmp_path / "capability", "bash", execute)
        await capability.start()
        reader, writer = await asyncio.open_unix_connection(
            str(capability.directory / "socket"))
        hello = client.verify(await _receive(reader, 1), capability.key)
        captured = client.pack(client.sign(
            {**hello, "op": "bash", "value": "printf once"}, capability.key))
        writer.write(captured)
        await writer.drain()
        result = client.verify(await _receive(reader, 1), capability.key)
        assert result["status"] == 0
        writer.write(client.pack(client.sign({**hello, "received": True}, capability.key)))
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        writer.close()
        await writer.wait_closed()
        reader, writer = await asyncio.open_unix_connection(
            str(capability.directory / "socket"))
        await _receive(reader, 1)
        writer.write(captured)
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        writer.close()
        await writer.wait_closed()
        await capability.close()
        assert executions == ["printf once"]
        assert len(owner.errors) == 1
    asyncio.run(scenario())


def test_capability_close_single_owner(tmp_path):
    async def scenario():
        owner = Owner()
        counts = {"server-close": 0, "server-wait": 0, "writer-close": 0, "cancel": 0}
        capability = _Capability(owner, tmp_path / "cap", "sql", None)

        class Writer:
            def close(self):
                counts["writer-close"] += 1

        async def handler():
            try:
                await asyncio.Event().wait()
            finally:
                counts["cancel"] += 1
                capability.handlers.discard(asyncio.current_task())

        task = asyncio.create_task(handler())
        capability.handlers.add(task)
        capability.writers.add(Writer())

        class Server:
            def close(self):
                counts["server-close"] += 1

            async def wait_closed(self):
                counts["server-wait"] += 1
                assert task.done()
                assert counts["writer-close"] == 1

        capability.server = Server()
        await asyncio.sleep(0)
        await asyncio.gather(capability.close(), capability.close())
        assert capability.revoked and capability._close_task.done()
        assert counts == {"server-close": 1, "server-wait": 1, "writer-close": 1, "cancel": 1}
        assert owner.errors == [] and capability.owned_children == set()
    asyncio.run(scenario())


def test_handler_cleanup_cancel_keeps_bookkeeping(tmp_path, monkeypatch):
    async def scenario():
        owner, reader = Owner(), asyncio.StreamReader()
        secondary = asyncio.CancelledError("cleanup join")
        counts = {"close": 0, "join": 0, "writes": 0}

        async def execute(command):
            await asyncio.Event().wait()

        capability = _Capability(owner, tmp_path / "cap", "bash", execute)

        class Writer:
            def write(self, data):
                counts["writes"] += 1
                hello = client.verify(client.decode(data[4:]), capability.key)
                request = {**hello, "op": "bash", "value": "true"}
                reader.feed_data(client.pack(client.sign(request, capability.key)) + b"x")

            async def drain(self):
                pass

            def close(self):
                counts["close"] += 1

            async def wait_closed(self):
                pass

        async def join(task, deadline=None):
            counts["join"] += 1
            result = await join_owned(task, deadline)
            if counts["join"] == 1:
                raise secondary
            return result

        monkeypatch.setattr(owned, "join_owned", join)
        writer = Writer()
        await capability._handle(reader, writer)
        assert len(capability.primary_errors) == 1
        assert isinstance(capability.primary_errors[0], client.BridgeProtocolError)
        assert capability.cleanup_errors == [secondary]
        assert owner.errors == [capability.primary_errors[0], secondary]
        assert counts == {"close": 1, "join": 2, "writes": 1}
        assert capability.handlers == capability.writers == capability.owned_children == set()
        assert capability.busy is False
    asyncio.run(scenario())


def test_client_total_deadline(tmp_path, monkeypatch):
    key = b"k" * 32
    (tmp_path / "key").write_bytes(key)
    clock = [0.0]
    calls = {"recv": 0, "send": 0, "deliver": 0}
    hello = client.pack(client.sign({"nonce": "a" * 64, "seq": 0}, key))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, timeout):
            assert 0 < timeout <= client.SOCKET_TIMEOUT

        def connect(self, path):
            pass

        def recv(self, count):
            calls["recv"] += 1
            clock[0] += client.SOCKET_TIMEOUT - 1
            return hello[:1]

        def sendall(self, data):
            calls["send"] += 1

    def deliver(stdout, stderr):
        calls["deliver"] += 1

    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(client.socket, "socket", lambda *args: Connection())
    with pytest.raises(TimeoutError, match="total deadline"):
        client.exchange(directory=tmp_path, operation="bash", value="true", deliver=deliver)
    assert calls == {"recv": 2, "send": 0, "deliver": 0}


def test_auth_guard_loss_target():
    key = b"g" * 32
    packet = client.sign({"nonce": "a" * 64, "seq": 0, "op": "bash", "value": "true"}, key)
    packet["body"]["value"] = "false"
    with pytest.raises(client.BridgeProtocolError, match="authentication failed"):
        client.verify(packet, key)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--sdk-seam-child":
        raise SystemExit("explicit isolated SDK child profile required")
    sdk_seam_child(int(sys.argv[2]))
