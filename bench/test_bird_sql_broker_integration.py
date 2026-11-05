"""Frozen E/O groups: original controller, reviewed CPU CLI, payload and EX."""

import asyncio
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import sys
import time

import pytest

from bench.score import execution_accuracy
from bench.task import SqlTask
from bench.test_bird_sql_worker_controller_integration import (
    CLI_BODY, Rig, assert_joined, rig, wait_log,
)
from bench.test_bird_sql_broker import (
    api, broker, cancel_before_body, http, observed, request, settled,
)
from ptc.bird_sql_worker import decode_query_response, encode_query_request
from ptc.bird_sql_worker_controller import QueryWorkerController


def assert_processes_joined(r):
    for row in r.log():
        for key in ("pid", "child_pid"):
            if key in row:
                with pytest.raises(ProcessLookupError):
                    os.kill(row[key], 0)


def assert_owned_settled(b, r, *, empty=True):
    assert all(task.done() for task in b._owned_tasks()), "broker task detached before teardown"
    if b._active is not None:
        assert_joined(b._active)
    assert_processes_joined(r)
    if empty:
        assert not r.registry(), "retirement must precede successful result"


@pytest.mark.parametrize("drift", [None, "bytes", "identity", "cli", "deadline_after_preflight"])
def test_06_task_bound_dispatch(rig, drift):
    async def scenario():
        if drift == "deadline_after_preflight":
            # Actual bounded-chunk hashing consumes the deadline. No clock or
            # controller/preflight replacement; this remains an owned CPU toy.
            with rig.toy.open("ab") as f:
                for _ in range(32):
                    f.write(b"\0"*1048576)
        b = broker(rig, timeout=0.003 if drift == "deadline_after_preflight" else 2)
        reads = []
        active = [drift == "deadline_after_preflight"]
        def audit(event, args):
            if active[0] and event == "open" and args[0] == str(rig.toy):
                reads.append(True)
        sys.addaudithook(audit)
        if drift == "bytes":
            with rig.toy.open("ab") as f:
                f.write(b"changed")
        elif drift == "identity":
            other = rig.toy.with_name("replacement")
            other.write_bytes(rig.toy.read_bytes())
            other.replace(rig.toy)
        elif drift == "cli":
            rig.cli.write_text(rig.cli.read_text()+"\n# drift\n")
        if drift is not None:
            with pytest.raises(api().SqlBrokerError):
                await b.query("SELECT 1")
            assert b.revoked and not b.closed and rig.log() == []
            with pytest.raises(api().SqlBrokerError):
                await b.aclose()
            if drift == "deadline_after_preflight":
                assert reads, "deadline test must actually enter DB preflight"
        else:
            rig.settings(start_delay=0.08)
            query = asyncio.create_task(b.query("SELECT n FROM t WHERE n=2"))
            await wait_log(rig, "start")
            c = b._active
            assert type(c) is QueryWorkerController
            assert c._host_db is rig.toy and c._config is rig.config
            early = query.done()
            if early:  # Failure-only PUBLIC cleanup, never rescue/private repair.
                try:
                    await b.aclose()
                except api().SqlBrokerError:
                    pass
                assert_owned_settled(b, rig)
            assert not early, "broker returned before original execute completion"
            out = await query
            assert out.rows == ((2,),) and out.status == "rows"
            assert_joined(c)
            assert c.state.phase == "CLOSED"
            assert b._active is None and not b._requests
            await b.aclose()
            assert b.closed
        assert_owned_settled(b, rig)
        active[0] = False
    asyncio.run(scenario())


def test_07_multiple_queries_preserved(rig):
    async def scenario():
        b = broker(rig)
        async def two_in_one_action():
            return [await b.query("SELECT 0"), await b.query("SELECT 1")]
        results = await two_in_one_action()
        for number in range(2, 9):
            results.append(await b.query(f"SELECT {number}"))
        assert [r.rows for r in results] == [((n,),) for n in range(9)]
        rows = rig.log()
        creates = [r for r in rows if r["command"] == "create"]
        assert len(creates) == len({r["name"] for r in creates}) == 9
        assert len([r for r in rows if r["command"] == "rm"]) == 9
        assert len([r for r in rows if r["command"] == "start" and "child_pid" not in r]) == 9
        assert all(r["payload_sha"] == rig.config.expected_payload_sha256 for r in creates)
        assert b._active is None and not b._requests
        await b.aclose()
        assert b.closed
        assert_owned_settled(b, rig)
    asyncio.run(scenario())


@pytest.mark.parametrize("sql,status,expected", [
    ("SELECT n FROM t WHERE n=1", "rows", ((1,),)),
    ("SELECT n FROM t WHERE n=2", "rows", ((2,),)),
    ("SELECT * FROM missing", "sql_error", ()),
    ("SELECT n FROM t", "row_refusal", ()),
    ("WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r",
     "query_timeout", ()),
    ("SELECT NULL AS dup, -9223372036854775808 AS dup, 1.5, '秘密', X'00ff'", "rows",
     ((None, -(2**63), 1.5, "秘密", b"\x00\xff"),)),
])
def test_08_actual_payload_and_ex(rig, sql, status, expected):
    original = rig.toy.read_bytes()
    async def scenario():
        b = broker(rig)
        response, _ = await http(b, encode_query_request(sql, limits=rig.config.worker.limits))
        assert response.status == 200
        result = decode_query_response(response.body, limits=rig.config.worker.limits)
        assert result.status == status and result.rows == expected
        if "AS dup" in sql:
            assert result.columns[:2] == ("dup", "dup")
        if sql in ("SELECT n FROM t WHERE n=1", "SELECT n FROM t WHERE n=2"):
            task = SqlTask("toy", "one", "", "SELECT n FROM t WHERE n=1", "toy", str(rig.toy),
                           "simple", "annotated", "select", "select", "fixture")
            ex = execution_accuracy(sql, task, timeout_s=0.1, max_rows=3)
            assert (ex.score, ex.valid) == (1.0 if sql.endswith("=1") else 0.0, True)
        await b.aclose()
        assert b.closed
        assert_owned_settled(b, rig)
        assert rig.toy.read_bytes() == original
    asyncio.run(scenario())


def test_09_two_task_isolation(rig):
    other = rig.root / "other-task"
    other.mkdir()
    toy = other / "db.sqlite"
    # A separately built original toy, not broker-created/copied model material.
    import sqlite3
    with sqlite3.connect(toy) as conn:
        conn.executescript("CREATE TABLE t(n); INSERT INTO t VALUES(91);")
    cli = other / "fixture-cli"
    cli.write_text("#!"+sys.executable+"\n"+CLI_BODY)
    cli.chmod(0o700)
    config_dir = other / "cli-config"
    config_dir.mkdir()
    worker = replace(rig.config.worker, cli_path=str(cli))
    config = replace(rig.config, worker=worker, command_cwd=other, docker_config_dir=config_dir,
                     expected_cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
                     command_env=(("FIXTURE_ROOT", str(other)), ("FIXTURE_PYTHON", sys.executable),
                                  ("PYTHONDONTWRITEBYTECODE", "1")))
    second = Rig(other, cli, toy, config)
    second.settings()
    async def scenario():
        first, two = broker(rig), broker(second)
        assert first.authorization_header != two.authorization_header
        wire = encode_query_request("SELECT n FROM t WHERE n=1", limits=rig.config.worker.limits)
        bad, stream = await http(first, wire, auth=two.authorization_header)
        if bad.status != 401:  # Failure-only public cleanup before assertion RED.
            await first.aclose()
            await two.aclose()
            assert_owned_settled(first, rig)
            assert_owned_settled(two, second)
        assert bad.status == 401 and stream._cursor == 0 and not first.revoked
        one, other_result = await asyncio.gather(
            first.query("SELECT n FROM t WHERE n=1"), two.query("SELECT n FROM t"))
        assert one.rows == ((1,),) and other_result.rows == ((91,),)
        assert len([r for r in rig.log() if r["command"] == "create"]) == 1
        assert len([r for r in second.log() if r["command"] == "create"]) == 1
        await first.aclose()
        await two.aclose()
        assert first.closed and two.closed
        assert_owned_settled(first, rig)
        assert_owned_settled(two, second)
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["fifo", "overload", "queue_deadline", "body_fifo"])
def test_10_serialization_and_backpressure(rig, mode):
    rig.settings(start_delay=0.35 if mode == "queue_deadline" else 0.10)
    async def scenario():
        # Six real serial starts take at least 2.1s even ignoring every CLI
        # overhead. First can complete within the unchanged 2s request bound,
        # but the queued tail cannot. No reset-at-dispatch can pass this case.
        b = broker(rig, pending=5 if mode == "queue_deadline" else 2)
        initial = asyncio.create_task(b.query("SELECT 10"))
        await wait_log(rig, "start")
        c = b._active
        second = asyncio.create_task(b.query("SELECT 11"))
        await observed(lambda: len(b._requests) == 2)
        if mode == "body_fifo":
            req, stream, handler = await request(b, eof=False)
            third = asyncio.create_task(handler(req))
            await observed(lambda: len(b._requests) == 3)
            stream.feed_data(encode_query_request("SELECT 12", limits=rig.config.worker.limits))
            stream.feed_eof()
        else:
            third = asyncio.create_task(b.query("SELECT 12"))
            await observed(lambda: len(b._requests) == 3)
        assert len([r for r in rig.log() if r["command"] == "create"]) == 1
        if mode == "overload":
            with pytest.raises(api().SqlBrokerError):
                await b.query("SELECT 13")
        tail = ([asyncio.create_task(b.query(f"SELECT {n}")) for n in (13, 14, 15)]
                if mode == "queue_deadline" else [])
        values = await asyncio.gather(initial, second, third, *tail, return_exceptions=True)
        if mode in ("fifo", "body_fifo"):
            assert values[0].rows == ((10,),) and values[1].rows == ((11,),)
            last = (decode_query_response(values[2].body, limits=rig.config.worker.limits)
                    if mode == "body_fifo" else values[2])
            assert last.rows == ((12,),)
            sequence = [r["command"] for r in rig.log() if r["command"] in ("create", "rm")]
            assert sequence == ["create", "rm"]*3, "concurrent original controllers"
            await b.aclose()
            assert b.closed
        else:
            assert any(isinstance(v, api().SqlBrokerError) for v in values)
            if mode == "queue_deadline":
                assert values[0].rows == ((10,),), "queue budget test requires first completion"
            await settled(b)
            assert len([r for r in rig.log() if r["command"] == "create"]) < (
                6 if mode == "queue_deadline" else 3)
        assert_joined(c)
        assert_owned_settled(b, rig)
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", [
    "active_close", "caller_cancel", "cancel_cleanup_failure", "prebody_dispatcher",
    "prebody_close_collector", "body_and_queue", "late_create", "close_allowance",
])
def test_11_close_and_cancel(rig, mode, monkeypatch):
    rig.settings(**({"create_delay": 0.12} if mode == "late_create" else
                    {"start_delay": 0.15, "remove_fail": mode == "cancel_cleanup_failure"}))
    async def scenario():
        b = broker(rig, close=0.02 if mode == "close_allowance" else 1.5)
        if mode == "prebody_dispatcher":
            seen = cancel_before_body(monkeypatch, "TaskSqlBroker._dispatch")
            entered = asyncio.create_task(b.query("SELECT 1"))
            with pytest.raises(api().SqlBrokerError):
                await entered
            await settled(b)
            assert seen == [b._dispatcher] and b._dispatcher.cancelled()
            assert rig.log() == []
            return
        task = asyncio.create_task(b.query("SELECT 1"))
        await wait_log(rig, "create" if mode == "late_create" else "start")
        c = b._active
        assert type(c) is QueryWorkerController and not task.done()
        queued = asyncio.create_task(b.query("SELECT 2"))
        await observed(lambda: len(b._requests) == 2)
        body = None
        if mode == "body_and_queue":
            req, _, handler = await request(b, eof=False)
            body = asyncio.create_task(handler(req))
            await observed(lambda: len(b._requests) == 3)
        if mode in ("caller_cancel", "cancel_cleanup_failure", "late_create"):
            task.cancel("original-caller")
            await asyncio.sleep(0.005)
            task.cancel("repeated-caller")
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert caught.value is b._caller_cancel, "first cancellation object must win"
            assert caught.value.args == ("original-caller",)
        else:
            seen = (cancel_before_body(monkeypatch, "TaskSqlBroker._collect_close")
                    if mode == "prebody_close_collector" else [])
            close = asyncio.create_task(b.aclose())
            await observed(lambda: b.revoked)
            deadline = b._close_deadline
            close.cancel("first-close-caller")
            await asyncio.sleep(0.005)
            close.cancel("second-close-caller")
            with pytest.raises(asyncio.CancelledError) as caught:
                await close
            assert caught.value.args == ("first-close-caller",)
            assert b._close_deadline == deadline, "repeated cancel reset close allowance"
            if mode == "prebody_close_collector":
                assert seen == [b._close_collector] and b._close_collector.cancelled()
            with pytest.raises(api().SqlBrokerError):
                await task
        with pytest.raises(api().SqlBrokerError):
            await queued
        if body is not None:
            assert (await body).status == 503
        with pytest.raises(api().SqlBrokerError):
            await b.aclose()
        assert b.revoked and not b.closed
        if mode == "close_allowance":
            # The allowance reports Pending, never drops the still-owned cleanup.
            assert b._active is c
            await observed(lambda: all(t.done() for t in b._owned_tasks()))
            with pytest.raises(api().SqlBrokerRetirementPending):
                await b.aclose()
        assert_joined(c)
        assert_owned_settled(b, rig, empty=mode != "cancel_cleanup_failure")
        assert len([r for r in rig.log() if r["command"] == "create"]) == 1
        if mode == "late_create":
            assert not any(r["command"] == "start" for r in rig.log())
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["create", "remove", "guest", "worker_infrastructure"])
def test_12_pending_retirement_propagates(rig, fault):
    rig.settings(**{
        "create": {"create_hang": True, "create_effect": False},
        "remove": {"remove_fail": True}, "guest": {"guest_state": "nonzero"},
        "worker_infrastructure": {},
    }[fault])
    config = (replace(rig.config, worker=replace(rig.config.worker, setup_timeout_s=0.08))
              if fault == "create" else rig.config)
    async def scenario():
        b = broker(rig, config=config)
        error = api().SqlBrokerRetirementPending if fault in ("create", "remove") else api().SqlBrokerError
        sql = "SELECT hex(zeroblob(5000))" if fault == "worker_infrastructure" else "SELECT 1"
        with pytest.raises(error):
            await b.query(sql)
        assert b.revoked and not b.closed, "uncertain/failed task must not become CLOSED"
        size = len(rig.log())
        failures = []
        for _ in range(2):
            with pytest.raises(error) as caught:
                await b.aclose()
            failures.append(caught.value)
            with pytest.raises(api().SqlBrokerError):
                await b.query("SELECT 2")
        assert len(rig.log()) == size, "no recovery retry or later dispatch"
        assert failures[0] is not failures[1], "do not retain accumulating caller tracebacks"
        if fault in ("create", "remove"):
            assert type(b._active) is QueryWorkerController, "unresolved controller forgotten"
        response, _ = await http(b, b"private request")
        assert response.status == 503 and response.text == "SQL service unavailable"
        assert str(rig.toy) not in response.text and b.authorization_header not in response.text
        assert_owned_settled(b, rig, empty=fault != "remove")
    asyncio.run(scenario())
