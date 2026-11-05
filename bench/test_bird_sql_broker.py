"""Frozen U groups. Real aiohttp streams/router, no socket or HTTP parser proof."""

import asyncio
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import sys
import tracemalloc

import pytest
from aiohttp import StreamReader, web
from aiohttp.base_protocol import BaseProtocol
from aiohttp.test_utils import make_mocked_request
from multidict import CIMultiDict

from bench.test_bird_sql_worker_controller_integration import rig
from ptc.bird_sql_worker import QueryWorkerResult, decode_query_response, encode_query_request


def api():
    assert importlib.util.find_spec("ptc.bird_sql_broker") is not None, (
        "CALL: required task SQL broker API is absent")
    module = importlib.import_module("ptc.bird_sql_broker")
    for name in ("TaskSqlBrokerConfig", "TaskSqlBroker", "SqlBrokerError",
                 "SqlBrokerRetirementPending"):
        assert hasattr(module, name), f"CALL: required broker API {name} is absent"
    return module


def broker(rig, *, pending=2, timeout=2.0, close=1.5, config=None, toy=None):
    a = api()
    path = rig.toy if toy is None else toy
    return a.TaskSqlBroker(
        config=a.TaskSqlBrokerConfig(
            controller=rig.config if config is None else config,
            max_pending_requests=pending, request_timeout_s=timeout, close_timeout_s=close),
        task_identity="owned-toy-task", host_db=path,
        expected_db_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        expected_db_size_bytes=path.stat().st_size)


class _RequestProtocol(BaseProtocol):
    """Real BaseProtocol plus request-construction helper's writer attribute."""
    ssl_context = None
    peername = None
    sockname = None


async def request(b, data=b"", *, auth=None, eof=True, headers=None, app=None):
    """Only make_mocked_request's request/transport construction is artificial."""
    loop = asyncio.get_running_loop()
    protocol = _RequestProtocol(loop)
    stream = StreamReader(protocol, limit=4096, loop=loop)
    if data:
        stream.feed_data(data)
    if eof:
        stream.feed_eof()
    app = b.application() if app is None else app
    values = CIMultiDict(headers if headers is not None else [
        ("Authorization", b.authorization_header if auth is None else auth)])
    req = make_mocked_request("POST", "/query", values, app=app, payload=stream,
                              protocol=protocol, loop=loop)
    match = await app.router.resolve(req)
    req._match_info = match
    return req, stream, match.handler


async def http(b, data=b"", **kwargs):
    req, stream, handler = await request(b, data, **kwargs)
    return await handler(req), stream


async def observed(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0.001)
    pytest.fail("owned fixture condition not observed within 200 bounded yields")


async def settled(b):
    with pytest.raises(api().SqlBrokerError):
        await b.aclose()
    assert b.revoked and not b.closed
    assert all(t.done() for t in b._owned_tasks()), "broker-owned task not joined"


def cancel_before_body(monkeypatch, qualname):
    """Schedule the real coroutine/Task, then cancel before its first bytecode."""
    original = asyncio.create_task
    seen = []
    def create(coro, *args, **kwargs):
        task = original(coro, *args, **kwargs)
        if coro.cr_code.co_qualname == qualname:
            assert inspect.getcoroutinestate(coro) == "CORO_CREATED"
            seen.append(task)
            task.cancel("prebody-owned-task")
        return task
    monkeypatch.setattr(asyncio, "create_task", create)
    return seen


def test_01_inert_config_and_capability(rig):
    events = []
    active = [True]
    forbidden = {"subprocess.Popen", "socket.bind", "socket.connect", "sqlite3.connect"}
    def audit(event, args):
        write = (event == "open" and (
            isinstance(args[1], str) and any(c in args[1] for c in "wax+")
            or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if active[0] and (event in forbidden or write):
            events.append(event)
            raise AssertionError("import/construction/application must be inert")
    sys.addaudithook(audit)
    try:
        a = api()
    finally:
        active[0] = False
    assert [f.name for f in fields(a.TaskSqlBrokerConfig)] == [
        "controller", "max_pending_requests", "request_timeout_s", "close_timeout_s"]
    with pytest.raises(TypeError):
        a.TaskSqlBrokerConfig()
    cfg = a.TaskSqlBrokerConfig(rig.config, 0, 1.0, 1.0)
    for key, values in {
        "controller": (None, object()),
        "max_pending_requests": (True, False, -1, 1.0),
        "request_timeout_s": (True, 0, -1, float("nan"), float("inf"), 10**400),
        "close_timeout_s": (False, 0, float("-inf")),
    }.items():
        for value in values:
            with pytest.raises(a.SqlBrokerError):
                replace(cfg, **{key: value})
    with pytest.raises(FrozenInstanceError):
        cfg.max_pending_requests = 8
    active[0] = True
    try:
        one, two = broker(rig), broker(rig)
        apps = one.application(), two.application()
    finally:
        active[0] = False
    assert events == [] and all(type(app) is web.Application for app in apps)
    assert rig.log() == [] and not rig.registry()
    assert not one.revoked and not one.closed
    assert re.fullmatch(r"Bearer [0-9a-f]{64}", one.authorization_header)
    assert one.authorization_header != two.authorization_header
    for obj in (one, two, cfg):
        assert one.authorization_header not in repr(obj)
        assert str(rig.toy) not in repr(obj)
    for key in ("authorization_header", "revoked", "closed"):
        with pytest.raises(AttributeError):
            setattr(one, key, "caller-selected")
    args = dict(config=cfg, task_identity="toy", host_db=rig.toy,
                expected_db_sha256="a"*64, expected_db_size_bytes=0)
    for key, value in (("expected_db_sha256", "A"*64),
                       ("expected_db_size_bytes", True), ("host_db", "db.sqlite")):
        with pytest.raises(a.SqlBrokerError):
            a.TaskSqlBroker(**dict(args, **{key: value}))
    async def close():
        await one.aclose()
        await two.aclose()
        assert one.closed and two.closed
    asyncio.run(close())


BAD = [
    b"{", b"\xff", b"[]", b'{"format":"cotrain_sql_query","version":1,"query":0}',
    b'{"format":"cotrain_sql_query","version":true,"query":"SELECT 1"}',
    b'{"format":"cotrain_sql_query","version":1.0,"query":"SELECT 1"}',
    b'{"format":"cotrain_sql_query","version":2,"query":"SELECT 1"}',
    b'{"format":"wrong","version":1,"query":"SELECT 1"}',
    b'{"format":"cotrain_sql_query","version":1,"query":"\\ud800"}',
    b'{"format":"cotrain_sql_query","version":1,"query":NaN}',
    b'{"format":"cotrain_sql_query","version":1,"query":"a","query":"b"}',
] + [json.dumps(dict(format="cotrain_sql_query", version=1, query="SELECT 1",
                     **{key: "override"})).encode()
     for key in ("task_identity", "host_db", "config", "timeout_s", "unknown")]


@pytest.mark.parametrize("body,status", [(b, 400) for b in BAD] + [
    (b"x"*4097, 413), (None, 400), ("direct-wire", 400)],
    ids=[f"invalid-{n:02}" for n in range(len(BAD))]+[
        "overflow", "direct-allocation", "direct-wire-boundaries"])
def test_02_request_boundary(rig, body, status):
    async def scenario():
        b = broker(rig, pending=0) if body is None or body == "direct-wire" else broker(rig)
        if body is None:
            a = api()
            query = "x"*(8*1024*1024)  # Construct BEFORE starting the trace.
            assert rig.config.worker.limits.request_max_bytes == 4096
            assert not tracemalloc.is_tracing()
            refused = False
            tracemalloc.start()
            try:
                baseline, _ = tracemalloc.get_traced_memory()
                tracemalloc.reset_peak()
                try:
                    await b.query(query)
                except a.SqlBrokerError:
                    refused = True
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()  # Recovery/process launch is NOT measured.
            metrics = dict(input_bytes=len(query), request_wire_cap_bytes=4096,
                           incremental_peak_bytes=peak-baseline, budget_bytes=256*1024,
                           refused=refused, controllers_after_refusal=len(rig.log()),
                           pending_after_refusal=len(b._requests), revoked_after_refusal=b.revoked)
            assert refused and rig.log() == [] and not rig.registry()
            assert b._active is None and not b._requests and not b.revoked
            result = await b.query("SELECT 1")
            assert result.status == "rows" and result.rows == ((1,),)
            await b.aclose()
            assert b.closed and not rig.registry()
            assert all(t.done() for t in b._owned_tasks())
            rows = rig.log()
            metrics["recovery_controllers"] = len([r for r in rows if r["command"] == "create"])
            assert metrics["recovery_controllers"] == 1
            assert len([r for r in rows if r["command"] == "start" and "child_pid" not in r]) == 1
            assert len([r for r in rows if r["command"] == "rm"]) == 1
            pids = {r[key] for r in rows for key in ("pid", "child_pid") if key in r}
            for pid in pids:
                with pytest.raises(ProcessLookupError):
                    os.kill(pid, 0)
            metrics.update(recovery_rows=result.rows, observed_pids_joined=len(pids), closed=b.closed)
            (rig.root/"allocation.json").write_text(json.dumps(metrics, indent=2)+"\n")
            assert metrics["incremental_peak_bytes"] <= metrics["budget_bytes"], (
                f"ALLOCATION: incremental peak {metrics['incremental_peak_bytes']} exceeds 262144")
            return
        if body == "direct-wire":
            a = api()
            class Unsupported(str):
                def __len__(self):
                    raise AssertionError("unsupported str subclass must not be inspected")
            for value in (None, True, 1, {}, ["SELECT 1"], Unsupported("SELECT 1"), "\ud800"):
                with pytest.raises(a.SqlBrokerError):
                    await b.query(value)
                assert not b._requests and not b.revoked and rig.log() == []
            limits = rig.config.worker.limits
            for count, value in enumerate(("plain", "é秘密😀", '\\"')):
                prefix = f"SELECT '{value}' /*"
                padding = limits.request_max_bytes-len(encode_query_request(prefix+"*/", limits=limits))
                sql = prefix+"x"*padding+"*/"
                assert len(encode_query_request(sql, limits=limits)) == 4096
                assert len(sql+" ") < 4096  # Must reach original FINAL wire-byte validation.
                with pytest.raises(a.SqlBrokerError):
                    await b.query(sql+" ")
                assert not b._requests and not b.revoked
                assert len([r for r in rig.log() if r["command"] == "create"]) == count
                assert (await b.query(sql)).rows == ((value,),)
            await b.aclose()
            assert b.closed and not rig.registry() and all(t.done() for t in b._owned_tasks())
            rows = rig.log()
            assert len([r for r in rows if r["command"] == "create"]) == 3
            for pid in {r[k] for r in rows for k in ("pid", "child_pid") if k in r}:
                with pytest.raises(ProcessLookupError):
                    os.kill(pid, 0)
            return
        response, _ = await http(b, body)
        assert response.status == status
        assert rig.log() == [] and not rig.registry()
        assert not b.revoked and b._active is None
        await b.aclose()
        assert b.closed
    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["rows", "sql_error", "row_refusal", "query_timeout"])
def test_03_response_roundtrip(rig, status):
    a = api()
    result = (QueryWorkerResult("rows", ("dup",)*8, (
        (None, -(2**63), 2**63-1, -0.0, float("inf"), "é\x00秘密", b"\x00\xff", 1.5),
        (None, 0, 1, 0.0, float("-inf"), "", b"", 2.0)), None)
        if status == "rows" else QueryWorkerResult(status, (), (), "unaltered é /private/data"))
    wire = a._encode_response(result, limits=rig.config.worker.limits)
    decoded = decode_query_response(wire, limits=rig.config.worker.limits)
    assert decoded == result
    if status == "rows":
        assert decoded.rows[0][3].hex() == "-0x0.0p+0"
        assert json.loads(wire)["rows"][0][7] == ["real", "0x1.8000000000000p+0"]
    for invalid in (QueryWorkerResult("infrastructure_failure", (), (), "not a result"),
                    QueryWorkerResult("rows", ("x",), ((True,),), None),
                    QueryWorkerResult("rows", ("x",), ((float("nan"),),), None)):
        with pytest.raises(a.SqlBrokerError):
            a._encode_response(invalid, limits=rig.config.worker.limits)


@pytest.mark.parametrize("pending", [0, 1, 2])
def test_04_admission_bound_includes_body_readers(rig, pending):
    async def scenario():
        b = broker(rig, pending=pending)
        readers = []
        for _ in range(pending+1):
            req, _, handler = await request(b, eof=False)
            readers.append(asyncio.create_task(handler(req)))
            await observed(lambda: len(b._requests) == len(readers))
        assert len(b._requests) == pending+1 and b._active is None
        overflow, stream = await http(b, b"x"*100)
        assert overflow.status == 503 and stream._cursor == 0
        assert all(response.status == 503 for response in await asyncio.gather(*readers))
        await settled(b)
        assert rig.log() == [] and not rig.registry()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["wrong_auth", "duplicate_auth", "transport", "deadline",
                                  "mixed_direct", "prebody_dispatcher", "direct_invalid",
                                  "prebody_body_reader"])
def test_05_http_application_without_listener(rig, mode, monkeypatch):
    async def scenario():
        b = broker(rig, pending=1, timeout=0.03 if mode == "deadline" else 2)
        app = b.application()
        assert type(app) is web.Application
        assert {(r.method, r.resource.canonical) for r in app.router.routes()} == {("POST", "/query")}
        if mode in ("wrong_auth", "duplicate_auth"):
            kwargs = (dict(auth="Bearer wrong") if mode == "wrong_auth" else
                      dict(headers=[("Authorization", b.authorization_header)]*2))
            response, stream = await http(b, b"x"*4097, **kwargs)
            assert response.status == 401 and stream._cursor == 0
            assert not b.revoked and b._dispatcher is None
            await b.aclose()
            assert b.closed
        elif mode == "direct_invalid":
            for value in (None, 1, True, "\ud800", "x"*4097):
                with pytest.raises(api().SqlBrokerError):
                    await b.query(value)
            assert not b.revoked
            await b.aclose()
            assert b.closed
        else:
            target = {"prebody_dispatcher": "TaskSqlBroker._dispatch",
                      "prebody_body_reader": "TaskSqlBroker._read_body"}.get(mode)
            cancelled = cancel_before_body(monkeypatch, target) if target else []
            req, stream, handler = await request(b, eof=False)
            read = asyncio.create_task(handler(req))
            if target is None:
                await observed(lambda: len(b._requests) == 1)
            if mode == "transport":
                stream.set_exception(ConnectionResetError(str(rig.toy)+" private transport detail"))
            elif mode == "mixed_direct":
                direct = asyncio.create_task(b.query("SELECT 1"))
                await observed(lambda: len(b._requests) == 2)
                response, extra = await http(b, b"x")
                assert response.status == 503 and extra._cursor == 0
                with pytest.raises(api().SqlBrokerError):
                    await direct
            response = await read
            assert response.status == 503
            assert str(rig.toy) not in response.text
            assert b.authorization_header not in response.text
            assert "private transport detail" not in response.text
            await settled(b)
            if mode == "prebody_dispatcher":
                assert cancelled == [b._dispatcher] and b._dispatcher.cancelled()
            elif mode == "prebody_body_reader":
                assert len(cancelled) == 1 and cancelled[0].cancelled()
        assert rig.log() == [] and not rig.registry()
    asyncio.run(scenario())
