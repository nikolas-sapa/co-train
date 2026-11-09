"""V172 finite source tests. UNRUN. No provider, process or network calls."""

import asyncio
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from train import qualification_modal_transport as t


def frame(body):
    return len(body).to_bytes(4, "big") + body


def response(op, body=b"", **changes):
    meta = dict(v=1, ok=True, op=op, size=len(body),
                sha256=hashlib.sha256(body).hexdigest())
    meta.update(changes)
    return frame(t._canonical_json(meta)) + (
        b"".join(frame(body[i:i + 65536]) for i in range(0, len(body), 65536))
    ) + frame(b"")


def envelope(body, nonce, stream, *, code=0, change=None):
    record = dict(v=1, nonce=nonce, stream=stream, size=len(body),
                  sha256=hashlib.sha256(body).hexdigest(), returncode=code)
    if change:
        record.update(change)
    return b"".join(b"D" + frame(body[i:i + 65536])
                    for i in range(0, len(body), 65536)) + b"T" + frame(t._canonical_json(record))


class Reader:
    def __init__(self, chunks=(), *, entered=None, peer=None):
        self.chunks = chunks
        self.entered = entered
        self.peer = peer

    async def __aiter__(self):
        if self.entered:
            self.entered.set()
            await self.peer.wait()
        for chunk in self.chunks:
            yield chunk


class Writer:
    def __init__(self):
        self.chunks = []
        self.drains = self.eofs = self.buffered = self.maximum = 0

    def write(self, data):
        assert type(data) is bytes and 0 < len(data) <= 65536
        assert self.eofs == 0
        self.chunks.append(data)
        self.buffered += len(data)
        self.maximum = max(self.maximum, self.buffered)

    def write_eof(self):
        self.eofs += 1

    async def drain(self):
        self.drains += 1
        self.buffered = 0


class Process:
    def __init__(self, out=(), err=(), code=0):
        self.stdout, self.stderr = Reader(out), Reader(err)
        self.stdin = Writer()
        self.code, self.waits = code, 0

    async def wait(self):
        self.waits += 1
        return self.code


class Sandbox:
    def __init__(self, stdout=b"", stderr=b"", *, code=0, mutate=None, quiet=False):
        self.stdout, self.stderr, self.code = stdout, stderr, code
        self.mutate, self.quiet = mutate, quiet
        self.calls = []

    async def exec(self, *argv, **kwargs):
        self.calls.append((argv, kwargs))
        # Nonce is fixed launcher data, never a caller-selected CLI argument.
        nonce = t._launcher_spec(argv)["nonce"]
        out = envelope(self.stdout, nonce, "stdout")
        err = envelope(self.stderr, nonce, "stderr")
        if self.mutate:
            out, err = self.mutate(out, err, nonce)
        self.process = Process([] if self.quiet else [out],
                               [] if self.quiet else [err], self.code)
        return self.process


def transport(sandbox):
    return t.ModalExecTransport(SimpleNamespace(resource=sandbox), clock=lambda: 100.0)


def execute(sandbox, *, chunks=(), limit=1048576, sink=None, deadline=102.0):
    return asyncio.run(transport(sandbox).exec_once(
        t.RPC_SERVE_ARGV, input_chunks=chunks, stdout_sink=sink,
        stdout_limit=limit, stderr_limit=limit, deadline=deadline))


def test_import_and_raw_resource_binding():
    sb = Sandbox()
    tr = transport(sb)
    assert tr.sandbox is sb and not hasattr(sb.exec, "aio")
    tr.sandbox = sb
    with pytest.raises(ValueError):
        tr.sandbox = Sandbox()
    unbound = t.ModalExecTransport(SimpleNamespace(resource=None), clock=lambda: 100.0)
    with pytest.raises(ValueError):
        unbound.sandbox = sb


def test_raw_exec_counts_timeout_two():
    sb = Sandbox(b"hello world", b"7bytes!")
    result = execute(sb)
    assert (result.returncode, result.stdout_bytes, result.stderr_bytes) == (0, 11, 7)
    assert result.stdout_complete and result.stderr_complete
    assert sb.calls[0][1] == dict(text=False, timeout=2, workdir="/")
    assert len(sb.calls) == sb.process.waits == sb.process.stdin.drains == sb.process.stdin.eofs == 1


def test_actual_rpc_frame_split_65540(tmp_path):
    from train import qualification_engineering_run as r
    tmp_path = tmp_path.resolve()
    body = b"x" * 65536
    path = tmp_path / "tiny"
    path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    item = t.PlannedUpload("source", "tiny", len(body), sha, path)
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        chunks = list(t.rpc_put_frames("source", "tiny", len(body), sha, frozen.items[0]))
    assert len(chunks[1]) == 65540
    sb = Sandbox()
    execute(sb, chunks=iter(chunks))
    assert b"".join(sb.process.stdin.chunks) == b"".join(chunks)
    assert max(map(len, sb.process.stdin.chunks)) <= 65536
    assert sb.process.stdin.eofs == 1


def test_stdin_8mib_bound():
    sb = Sandbox()
    execute(sb, chunks=(b"a" * 65536 for _ in range(272)))
    assert sb.process.stdin.maximum <= 8388608
    assert sb.process.stdin.drains == 3
    assert sum(map(len, sb.process.stdin.chunks)) == 17 * 1024**2
    sb = Sandbox()
    execute(sb, chunks=(b"a" * 65536 for _ in range(320)))
    assert sb.process.stdin.maximum <= 8388608 and sb.process.stdin.drains == 3
    assert sum(map(len, sb.process.stdin.chunks)) == 20 * 1024**2


def test_mutually_dependent_streams():
    class Dependent(Sandbox):
        async def exec(self, *argv, **kwargs):
            process = await super().exec(*argv, **kwargs)
            out, err = asyncio.Event(), asyncio.Event()
            process.stdout = Reader(process.stdout.chunks, entered=out, peer=err)
            process.stderr = Reader(process.stderr.chunks, entered=err, peer=out)
            return process
    sb = Dependent(b"o" * 100, b"e" * 100)
    result = execute(sb)
    assert result.stdout_bytes == result.stderr_bytes == 100


def test_caps_types_deadlines():
    assert execute(Sandbox(b"x" * 65536), limit=65536).stdout_bytes == 65536
    with pytest.raises(t.ExecOutputLimitExceeded):
        execute(Sandbox(b"x" * 65537), limit=65536)
    with pytest.raises(t.ExecOutputLimitExceeded):
        execute(Sandbox(stderr=b"xxx"), limit=2)
    sb = Sandbox()
    for argv, deadline in (((), 102.0), ((1,), 102.0),
                           (t.RPC_SERVE_ARGV, float("nan")), (t.RPC_SERVE_ARGV, 99.0)):
        with pytest.raises(ValueError):
            asyncio.run(transport(sb).exec_once(
                argv, stdout_limit=10, stderr_limit=10, deadline=deadline))
    assert len(sb.calls) == 0
    class Bad(Sandbox):
        async def exec(self, *args, **kwargs):
            process = await super().exec(*args, **kwargs)
            process.stdout = Reader(["not bytes"])
            return process
    with pytest.raises(ValueError):
        execute(Bad())


def test_actual_wait_minus_one_and_nonzero_refuse():
    for code in (-1, 3, True):
        with pytest.raises(ValueError):
            execute(Sandbox(code=code))


def test_ambiguous_start_never_reissued():
    class Ambiguous(Sandbox):
        async def exec(self, *argv, **kwargs):
            self.calls.append(argv)
            raise TimeoutError("controlled start ambiguity")
    sb = Ambiguous()
    tr = transport(sb)
    async def run():
        with pytest.raises(t.ExecStartAmbiguous):
            await tr.exec_once(t.RPC_SERVE_ARGV, stdout_limit=10, stderr_limit=10, deadline=102.0)
        with pytest.raises(ValueError, match="poisoned"):
            await tr.exec_once(t.RPC_SERVE_ARGV, stdout_limit=10, stderr_limit=10, deadline=102.0)
    asyncio.run(run())
    assert len(sb.calls) == 1


def test_quiet_iterator_end_not_completion():
    with pytest.raises(ValueError, match="terminal"):
        execute(Sandbox(quiet=True))


def test_envelope_invalid_records_accept_zero():
    changes = ({"nonce": "f" * 64}, {"stream": "stderr"}, {"size": 4},
               {"sha256": "0" * 64}, {"returncode": 2}, {"returncode": True},
               {"v": True}, {"extra": 1})
    for change in changes:
        def mutate(out, err, nonce):
            return envelope(b"abc", nonce, "stdout", change=change), err
        with pytest.raises(ValueError):
            execute(Sandbox(b"abc", mutate=mutate))
    for kind in ("missing", "truncated", "duplicate", "missing-stderr"):
        def mutate(out, err, nonce):
            if kind == "missing":
                return b"D" + frame(b"abc"), err
            if kind == "truncated":
                return out[:-1], err
            if kind == "missing-stderr":
                return out, b""
            return out + envelope(b"", nonce, "stdout"), err
        with pytest.raises(ValueError):
            execute(Sandbox(b"abc", mutate=mutate))


def test_envelope_valid_pair_exact_payload():
    body = bytes(range(256)) * 257
    seen = []
    sb = Sandbox(body)
    result = execute(sb, sink=seen.append)
    assert b"".join(seen) == body and result.stdout_bytes == 65792
    assert max(map(len, seen)) <= 65536


def test_fixed_launcher_invoked_with_controlled_child():
    events = []
    class Child:
        stdout = io.BytesIO(b"actual stdout")
        stderr = io.BytesIO(b"actual stderr")
        def wait(self):
            assert self.stdout.tell() == 13 and self.stderr.tell() == 13
            events.append("wait")
            return 0
    def popen(argv, **kwargs):
        assert tuple(argv) == t.RPC_SERVE_ARGV
        assert kwargs["shell"] is False and kwargs["cwd"] == "/"
        events.append("start")
        return Child()
    out, err = io.BytesIO(), io.BytesIO()
    assert t._launch_enveloped(t.RPC_SERVE_ARGV, "a" * 64, 100, 100,
                               _popen=popen, _stdout=out, _stderr=err) == 0
    decoded = []
    parser = t._EnvelopeDecoder("a" * 64, "stdout", 100, decoded.append)
    parser(out.getvalue())
    assert parser.finish() == 0
    assert b"".join(decoded) == b"actual stdout" and events == ["start", "wait"]
    other = t._EnvelopeDecoder("a" * 64, "stderr", 100, None)
    other(err.getvalue())
    assert other.finish() == 0


def test_rpc_exact_metadata_types_and_pins():
    good = response("get", b"abc")
    assert t.parse_rpc_response(good, op="get")[1] == b"abc"
    for change in (dict(v=True), dict(size=True), dict(size=2),
                   dict(sha256="A" * 64), dict(sha256="g" * 64),
                   dict(sha256="0" * 64), dict(extra=0), dict(ok=1)):
        with pytest.raises(ValueError):
            t.parse_rpc_response(response("get", b"abc", **change), op="get")
    for kwargs in (dict(expected_size=2), dict(expected_sha256="0" * 64)):
        with pytest.raises(ValueError):
            t.parse_rpc_response(good, op="get", **kwargs)


def test_rpc_duplicate_nonfinite_trailing_truncation():
    for meta in (b'{"v":1,"v":1}', b'{"v":NaN}', b'{"v":1e999}'):
        with pytest.raises(ValueError):
            t.parse_rpc_response(frame(meta) + frame(b""), op="get")
    good = response("put")
    assert good.endswith(b"\0\0\0\0")
    t.parse_put_ack(good)
    for bad in (good + b"\0\0\0\0", good[:-1], response("get", b"abc")[:-5]):
        with pytest.raises(ValueError):
            t.parse_rpc_response(bad, op="put" if bad.startswith(good[:20]) else "get")
    for size in (0, 1048577):
        with pytest.raises(ValueError):
            t.parse_rpc_response(size.to_bytes(4, "big"), op="get")
    metadata = t._canonical_json(dict(v=1, ok=True, op="get", size=0,
                                      sha256=hashlib.sha256(b"").hexdigest()))
    maximum = metadata + b" " * (1048576 - len(metadata))
    assert t.parse_rpc_response(frame(maximum) + frame(b""), op="get")[1] == b""
    with pytest.raises(ValueError, match="frame length"):
        t.parse_rpc_response(frame(metadata) + (65537).to_bytes(4, "big"), op="get")
    for key in ("a/./b", "a//b", "../b", "a\\b", "/a"):
        with pytest.raises(ValueError):
            list(t.rpc_put_frames("source", key, 1, "0" * 64, io.BytesIO(b"x")))


def test_manifest_canonical_bounds():
    entry = dict(key="a/b", size=3, sha256=hashlib.sha256(b"abc").hexdigest())
    body = t._canonical_json([entry])
    assert len(t.parse_manifest_body(body, max_bytes=3, max_members=1, max_depth=1)) == 1
    for kwargs in (dict(max_bytes=2), dict(max_members=0), dict(max_depth=0),
                   dict(json_limit=len(body) - 1)):
        with pytest.raises(ValueError):
            t.parse_manifest_body(body, **kwargs)
    for key in (".", "..", "a/./b", "a//b", "a\\b", "a/../b"):
        with pytest.raises(ValueError):
            t.parse_manifest_body(t._canonical_json([dict(entry, key=key)]))
    with pytest.raises(ValueError):
        t.parse_manifest_body(t._canonical_json([entry, entry]))
    with pytest.raises(ValueError, match="alias"):
        t.parse_manifest_body(t._canonical_json([
            dict(entry, key="a"), dict(entry, key="a/b")]))
    with pytest.raises(ValueError):
        t.rpc_manifest_metadata("evidence", max_bytes=3, max_members=1, max_depth=1)
    assert list(t.rpc_request_frames(t.rpc_get_metadata("output", "a", 0,
                                                       hashlib.sha256(b"").hexdigest())))[-1] == frame(b"")


def test_streaming_response_decoder():
    body = b"x" * 65536
    pieces = []
    decoder = t.RPCResponseDecoder("get", pieces.append, expected_size=len(body),
                                   expected_sha256=hashlib.sha256(body).hexdigest())
    raw = response("get", body)
    for offset in range(0, len(raw), 13):
        decoder(raw[offset:offset + 13])
    decoder.finish()
    assert b"".join(pieces) == body and max(map(len, pieces)) <= 65536
    assert decoder.buffered_bytes <= 1048576
    with pytest.raises(ValueError, match="8MiB"):
        t._ResponseAccumulator(8 * 1024**2 + 1)
    for raw in (response("get", body, size=65535), response("get", body, sha256="0" * 64)):
        bad = t.RPCResponseDecoder("get", lambda part: None)
        with pytest.raises(ValueError):
            bad(raw)
            bad.finish()


def test_caller_deadline_without_pipe_completion():
    import time
    class Hanging(Sandbox):
        async def exec(self, *argv, **kwargs):
            process = await super().exec(*argv, **kwargs)
            class Quiet:
                async def __aiter__(self):
                    await asyncio.Event().wait()
                    yield b"unreachable"
            process.stdout = Quiet()
            return process
    sb = Hanging()
    async def run():
        tr = t.ModalExecTransport(SimpleNamespace(resource=sb), clock=time.monotonic)
        with pytest.raises(t.ExecAmbiguous):
            await tr.exec_once(t.RPC_SERVE_ARGV, stdout_limit=10, stderr_limit=10,
                               deadline=time.monotonic() + 0.03)
        assert tr.poisoned is not None and len(sb.calls) == 1
    asyncio.run(run())


def test_envelope_fragmentation_and_framing_cap():
    nonce = "a" * 64
    seen = []
    decoder = t._EnvelopeDecoder(nonce, "stdout", 100, seen.append)
    raw = envelope(b"exact", nonce, "stdout")
    for byte in raw:
        decoder(bytes([byte]))
    assert decoder.finish() == 0 and b"".join(seen) == b"exact"
    decoder = t._EnvelopeDecoder(nonce, "stdout", 100, None)
    with pytest.raises(t.ExecOutputLimitExceeded, match="framing"):
        decoder((b"D" + frame(b"x")) * 3)


def test_unvalidated_caller_stream_refused_before_first_wire_byte():
    source = io.BytesIO(b"tiny")
    with pytest.raises(ValueError, match="snapshot"):
        next(t.rpc_put_frames("source", "tiny", 4, hashlib.sha256(b"tiny").hexdigest(), source))
    assert source.tell() == 0


def test_manifest_global_worst_case_numeric_gates():
    empty = hashlib.sha256(b"").hexdigest()
    entries = [dict(key=f"f{index:05}", size=0, sha256=empty) for index in range(10000)]
    assert len(t.parse_manifest_body(t._canonical_json(entries))) == 10000
    entries.append(dict(key="f10000", size=0, sha256=empty))
    with pytest.raises(ValueError, match="member"):
        t.parse_manifest_body(t._canonical_json(entries))
    deep = dict(key="/".join(["a"] * 33), size=0, sha256=empty)
    assert len(t.parse_manifest_body(t._canonical_json([deep]))) == 1
    deep["key"] += "/a"
    with pytest.raises(ValueError, match="depth"):
        t.parse_manifest_body(t._canonical_json([deep]))
    aggregate = [dict(key=str(index), size=2 * 1024**3, sha256=empty) for index in range(4)]
    assert len(t.parse_manifest_body(t._canonical_json(aggregate))) == 4
    aggregate.append(dict(key="4", size=1, sha256=empty))
    with pytest.raises(ValueError, match="aggregate"):
        t.parse_manifest_body(t._canonical_json(aggregate))
    # Exact canonical 8MiB JSON, without making any artifact or asset file.
    maximum = []
    for index in range(2048):
        parts = [f"{index:04x}" + "a" * 245] + ["a" * 249] * 15
        if index != 2047:
            parts[-1] += "a"
        maximum.append(dict(key="/".join(parts), size=0, sha256=empty))
    body = t._canonical_json(maximum)
    assert len(body) == 8 * 1024**2
    assert len(t.parse_manifest_body(body)) == 2048
    with pytest.raises(ValueError, match="JSON bound"):
        t.parse_manifest_body(body + b" ")


def test_put_100000_exact_two_frames_and_one_terminator(tmp_path):
    from train import qualification_engineering_run as r
    tmp_path = tmp_path.resolve()
    body = b"x" * 100000
    path = tmp_path / "tiny"
    path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    item = t.PlannedUpload("source", "tiny", 100000, sha, path)
    with r._SnapshotSet((item,), tmp_path, deadline=200.0, clock=lambda: 100.0) as frozen:
        frames = list(t.rpc_put_frames("source", "tiny", 100000, sha, frozen.items[0]))
    assert [len(part) for part in frames[1:]] == [65540, 34468, 4]
    assert frames[-1] == frame(b"")
