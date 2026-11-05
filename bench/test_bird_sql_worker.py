"""Offline toy SQL acceptance, never Docker or native-policy qualification."""

import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import pytest

from bench.score import execution_accuracy
from bench.task import SqlTask
from ptc.runtime import ProgramRejected
from ptc.sql_arms import make_execute_sql
from ptc.sql_runtime import over_cap_message
from ptc.sqlite_safety import protect_connection


@pytest.fixture
def api():
    assert importlib.util.find_spec("ptc.bird_sql_worker") is not None, "worker API required"
    return importlib.import_module("ptc.bird_sql_worker")


@pytest.fixture
def limits(api):
    return api.QueryWorkerLimits(3, 0.08, 4096, 8192)


@pytest.fixture
def toy(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.executescript("CREATE TABLE t(n INTEGER, s TEXT);"
                           "INSERT INTO t VALUES(1,'a'),(2,'b'),(3,'c'),(4,'d');")
        conn.commit()
    finally:
        conn.close()
    return path


def payload(api, limits, toy, query=None, raw=None):
    source = api.query_worker_source(limits=limits)
    request = api.encode_query_request(query, limits=limits) if raw is None else raw
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-c", source.decode("utf-8")],
        input=request, cwd=toy.parent, capture_output=True, timeout=3, check=False)
    assert proc.stderr == b"", proc.stderr
    assert len(proc.stdout) <= limits.response_max_bytes
    return proc, time.monotonic() - started


def result(api, limits, toy, query):
    proc, _ = payload(api, limits, toy, query)
    assert proc.returncode == 0
    return api.decode_query_response(proc.stdout, limits=limits)


def test_01_real_payload_and_original_ex(api, limits, toy):
    task = SqlTask("toy", "one", "", "SELECT n FROM t WHERE n=1", "toy",
                   str(toy), "simple", "annotated", "select", "select", "fixture")
    for sql, score, outcome in [
        ("SELECT n FROM t WHERE n=1", 1.0, "match"),
        ("SELECT n FROM t WHERE n=2", 0.0, "mismatch"),
    ]:
        out = result(api, limits, toy, sql)
        assert out.status == "rows"
        assert out.rows == ((1 if score else 2,),)
        ex = execution_accuracy(sql, task, timeout_s=0.1, max_rows=3)
        assert (ex.score, ex.valid, ex.status) == (score, True, outcome)


def test_02_actual_guard_source_and_function_controls(api, limits, toy):
    source = api.query_worker_source(limits=limits).decode()
    tree = ast.parse(source)
    constants = {node.targets[0].id: ast.literal_eval(node.value)
                 for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in {"SAFETY_SOURCE", "SAFETY_SHA256"}}
    sibling = Path(api.__file__).with_name("sqlite_safety.py").read_bytes()
    assert constants["SAFETY_SOURCE"].encode() == sibling
    assert constants["SAFETY_SHA256"] == hashlib.sha256(sibling).hexdigest()
    namespace = {}
    exec(compile(constants["SAFETY_SOURCE"], "<sqlite-safety>", "exec"), namespace)
    for guard in (protect_connection, namespace["protect_connection"]):
        for name in ("writefile", "edit", "load_extension", "readfile"):
            conn = sqlite3.connect(toy)
            try:
                conn.create_function(name, 1, lambda x: x)
                assert conn.execute(f"SELECT {name}('toy')").fetchone() == ("toy",)
                guard(conn)
                with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                    conn.execute(f"SELECT {name}('toy')")
            finally:
                conn.close()
    denied = result(api, limits, toy, "ATTACH DATABASE ':memory:' AS escaped")
    assert denied.status == "sql_error", "actual worker must install guard"
    assert "not authorized" in denied.message
    assert denied.rows == denied.columns == ()


@pytest.mark.parametrize("sql", [
    "PRAGMA database_list", "PRAGMA table_info(t)",
    "SELECT * FROM pragma_table_info('t')",
    "SELECT * FROM pragma_database_list",
])
def test_03_pragmas_unchanged(api, limits, toy, sql):
    limits = replace(limits, action_max_rows=10)
    conn = protect_connection(sqlite3.connect(f"file:{toy}?mode=ro", uri=True))
    try:
        cursor = conn.execute(sql)
        expected = tuple(cursor.fetchall())
        columns = tuple(item[0] for item in cursor.description)
    finally:
        conn.close()
    # database_list reports the actual same physical file in toy cwd.
    out = result(api, limits, toy, sql)
    assert (out.status, out.columns, out.rows) == ("rows", columns, expected)


def test_04_row_boundary_duplicates_and_sql_errors(api, limits, toy):
    assert result(api, limits, toy, "SELECT n FROM t LIMIT 3").rows == ((1,), (2,), (3,))
    overflow = result(api, limits, toy, "SELECT n FROM t")
    assert (overflow.status, overflow.rows, overflow.columns, overflow.message) == (
        "row_refusal", (), (), over_cap_message(3))
    execute = make_execute_sql(str(toy), max_rows=3)
    with pytest.raises(ProgramRejected) as caught:
        execute(query="SELECT n FROM t")
    assert str(caught.value) == overflow.message
    duplicate = result(api, limits, toy, "SELECT 1 AS x, 2 AS x")
    assert (duplicate.columns, duplicate.rows) == (("x", "x"), ((1, 2),))
    with pytest.raises(ProgramRejected) as caught:
        execute(query="SELECT * FROM missing")
    error = result(api, limits, toy, "SELECT * FROM missing")
    assert (error.status, error.message) == ("sql_error", str(caught.value))


def test_05_nine_queries_no_quota(api, limits, toy):
    assert "max_turns" not in limits.__dataclass_fields__
    values = [result(api, limits, toy, f"SELECT {i}").rows[0][0] for i in range(9)]
    assert values == list(range(9))


def test_06_lossless_types(api, limits, toy):
    out = result(api, limits, toy,
                 "SELECT NULL, -9223372036854775808, 9223372036854775807,"
                 " -0.0, 1.5, 1e999, -1e999, 'a'||char(0)||'é', x'00ff80',"
                 " 4 AS x, 5 AS x")
    row = out.rows[0]
    assert row == (None, -(2**63), 2**63-1, -0.0, 1.5, math.inf, -math.inf,
                   "a\0é", b"\0\xff\x80", 4, 5)
    assert math.copysign(1, row[3]) == -1
    assert tuple(type(x) for x in row) == (
        type(None), int, int, float, float, float, float, str, bytes, int, int)
    with pytest.raises(FrozenInstanceError):
        out.status = "rows"


def test_07_cooperative_deadline(api, limits, toy):
    sql = ("WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r)"
           " SELECT sum(x) FROM r")
    proc, elapsed = payload(api, limits, toy, sql)
    out = api.decode_query_response(proc.stdout, limits=limits)
    assert out.status == "query_timeout"
    assert out.rows == out.columns == ()
    assert elapsed <= limits.query_timeout_s + 1.0
    assert result(api, limits, toy, "SELECT sum(n) FROM t").rows == ((10,),)


def test_08_overflow_infrastructure(api, limits, toy):
    small = replace(limits, request_max_bytes=80, response_max_bytes=160)
    with pytest.raises(api.QueryWorkerError):
        api.encode_query_request("SELECT '" + "é"*80 + "'", limits=small)
    proc, _ = payload(api, small, toy, raw=b" "*81)
    out = api.decode_query_response(proc.stdout, limits=small)
    assert out.status == "infrastructure_failure", "request overflow is not SQL refusal"
    out = result(api, small, toy, "SELECT hex(zeroblob(500))")
    assert (out.status, out.columns, out.rows) == ("infrastructure_failure", (), ())
    tiny = replace(limits, response_max_bytes=1)
    proc, _ = payload(api, tiny, toy, "SELECT 1")
    assert (proc.returncode != 0, proc.stdout) == (True, b"")
    with pytest.raises(api.QueryWorkerError):
        api.decode_query_response(proc.stdout, limits=tiny)
    raw = api.encode_query_request("SELECT 'é'", limits=limits)
    exact = replace(limits, request_max_bytes=len(raw))
    assert result(api, exact, toy, "SELECT 'é'").rows == (("é",),)
    proc, _ = payload(api, limits, toy, "SELECT 1")
    exact = replace(limits, response_max_bytes=len(proc.stdout))
    assert api.decode_query_response(proc.stdout, limits=exact).rows == ((1,),)
    with pytest.raises(api.QueryWorkerError):
        api.decode_query_response(proc.stdout, limits=replace(exact, response_max_bytes=len(proc.stdout)-1))


@pytest.mark.parametrize("raw", [
    b"", b"\xff", b"{}", b'{"format":"cotrain_sql_query","version":true,"query":"SELECT 1"}',
    b'{"format":"cotrain_sql_query","version":1,"query":"SELECT 1","db":"other"}',
    b'{"format":"cotrain_sql_query","version":1,"query":"SELECT 1","query":"SELECT 2"}',
    b'{"format":"cotrain_sql_query","version":1,"query":"\\ud800"}',
    b'{"format":"cotrain_sql_query","version":NaN,"query":"SELECT 1"}',
])
def test_08_strict_request(api, limits, toy, raw):
    proc, _ = payload(api, limits, toy, raw=raw)
    out = api.decode_query_response(proc.stdout, limits=limits)
    assert (out.status, out.rows) == ("infrastructure_failure", ())


@pytest.mark.parametrize("change", [
    {"version": True}, {"extra": 1}, {"status": "EX0"},
    {"columns": ["x"], "rows": [] , "message": "partial"},
    {"rows": [[["integer", "01"]]]}, {"rows": [[["integer", str(2**63)]]]},
    {"rows": [[["real", "nan"]]]}, {"rows": [[["real", "1.5"]]]},
    {"rows": [[["blob", "AB=="]]]}, {"rows": [[["blob", "?"]]]},
    {"rows": [[["text", "\ud800"]]]}, {"rows": [[["null", 0]]]},
    {"rows": [[["integer", "1"], ["null"]]]},
    {"status": "sql_error", "message": "oops"},
    {"status": "sql_error", "columns": [], "rows": [], "message": None},
])
def test_08_strict_response(api, limits, change):
    obj = dict(format="cotrain_sql_result", version=1, status="rows",
               columns=["x"], rows=[[["integer", "1"]]], message=None)
    obj.update(change)
    with pytest.raises(api.QueryWorkerError):
        api.decode_query_response(json.dumps(obj).encode(), limits=limits)


def test_08_invalid_response_bytes(api, limits):
    for raw in (b"", b"\xff", b"{}", b'{"format":1,"format":2}', b"NaN",
                b"[" * 1500 + b"]" * 1500):
        with pytest.raises(api.QueryWorkerError):
            api.decode_query_response(raw, limits=limits)


@pytest.mark.parametrize("field,value", [
    ("action_max_rows", True), ("action_max_rows", 0), ("action_max_rows", 1.0),
    ("query_timeout_s", True), ("query_timeout_s", 0), ("query_timeout_s", math.inf),
    ("query_timeout_s", math.nan), ("request_max_bytes", -1),
    ("response_max_bytes", False), ("request_max_bytes", "100"),
])
def test_08_invalid_limits(api, limits, field, value):
    with pytest.raises(api.QueryWorkerError):
        replace(limits, **{field: value})


def spec_for(api, limits):
    return api.DockerQueryWorkerSpec(
        cli_path="/opt/bin/docker", daemon_context="toy-context",
        image="toy/worker@sha256:" + "a"*64, guest_python="/usr/bin/python3",
        uid=1234, gid=1234, cpus=0.5, memory_bytes=67108864, pids_limit=16,
        tmpfs_bytes=1048576, limits=limits, setup_timeout_s=1,
        start_timeout_s=1, retirement_timeout_s=1)


def test_10_static_launch_only(api, limits, toy):
    spec = spec_for(api, limits)
    argv = api.build_worker_create_argv(spec, resource_name="toy-worker", host_db=toy)
    assert isinstance(argv, tuple)
    assert argv[:4] == ("/opt/bin/docker", "--context", "toy-context", "create")
    for flag, value in [
        ("--pull", "never"), ("--network", "none"), ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges:true"), ("--user", "1234:1234"),
        ("--cpus", "0.5"), ("--memory", "67108864"), ("--memory-swap", "67108864"),
        ("--pids-limit", "16"), ("--workdir", "/task"), ("--entrypoint", "/usr/bin/python3"),
    ]:
        assert argv[argv.index(flag)+1] == value
    assert "--read-only" in argv and "--interactive" in argv
    assert argv[argv.index("--mount")+1] == f"type=bind,src={toy},dst=/task/db.sqlite,readonly"
    assert argv.count("--mount") == 1
    assert argv[argv.index("--tmpfs")+1] == "/tmp:rw,noexec,nosuid,nodev,size=1048576"
    assert argv[-5:-1] == (spec.image, "-I", "-B", "-c")
    assert argv[-1].encode() == api.query_worker_source(limits=limits)
    assert str(toy) not in argv[-1]
    assert str(Path(api.__file__).parent) not in argv[-1]
    assert "docker.sock" not in " ".join(argv)
    assert "SELECT " not in " ".join(argv)
    with pytest.raises(FrozenInstanceError):
        spec.uid = 0


@pytest.mark.parametrize("name", ["bad,db", 'bad"db', "bad\ndb", "bad=db"])
def test_10_unsafe_mount_no_repair(api, limits, toy, name):
    unsafe = toy.parent / name
    unsafe.write_bytes(toy.read_bytes())
    with pytest.raises(api.QueryWorkerError):
        api.build_worker_create_argv(spec_for(api, limits), resource_name="toy", host_db=unsafe)
    assert sorted(p.name for p in toy.parent.iterdir()) == sorted(["db.sqlite", name])


def test_10_bad_resources_paths(api, limits, toy):
    spec = spec_for(api, limits)
    link = toy.parent / "link"
    link.symlink_to(toy)
    for path in (link, toy.parent, toy.parent / "missing", Path("relative.sqlite")):
        with pytest.raises(api.QueryWorkerError):
            api.build_worker_create_argv(spec, resource_name="toy", host_db=path)
    for name in ("--evil", "a,b", "a/b", "", "a\nb"):
        with pytest.raises(api.QueryWorkerError):
            api.build_worker_create_argv(spec, resource_name=name, host_db=toy)
    for field, value in [
        ("cli_path", "docker"), ("daemon_context", "--bad"), ("image", "toy:latest"),
        ("guest_python", "-c"), ("uid", 0), ("gid", True), ("cpus", math.inf),
        ("memory_bytes", 0), ("pids_limit", False), ("tmpfs_bytes", 0),
        ("setup_timeout_s", 0), ("start_timeout_s", math.nan),
        ("retirement_timeout_s", -1),
    ]:
        with pytest.raises(api.QueryWorkerError):
            replace(spec, **{field: value})


def test_11_import_and_planning_inert(api, limits, toy, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("import/planning attempted a process, network, mkdir or DB open")
    namespace = vars(api).copy()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "Popen", forbidden)
            patch.setattr(socket, "socket", forbidden)
            patch.setattr(Path, "mkdir", forbidden)
            patch.setattr(sqlite3, "connect", forbidden)
            importlib.reload(api)
            local = api.QueryWorkerLimits(3, 0.08, 4096, 8192)
            source = api.query_worker_source(limits=local)
            api.build_worker_create_argv(spec_for(api, local), resource_name="toy", host_db=toy)
            assert source
    finally:
        # Old class methods retain this exact globals dictionary across reload.
        vars(api).clear()
        vars(api).update(namespace)


def test_08_open_failure_is_infrastructure(api, limits, toy):
    toy.unlink()
    out = result(api, limits, toy, "SELECT 1")
    assert out.status == "infrastructure_failure"
    assert not toy.exists(), "read-only open must not create a replacement DB"


def test_08_required_typed_limits_and_query(api, limits):
    for bad in (None, True, {}, "limits"):
        with pytest.raises(api.QueryWorkerError):
            api.query_worker_source(limits=bad)
        with pytest.raises(api.QueryWorkerError):
            api.encode_query_request("SELECT 1", limits=bad)
        with pytest.raises(api.QueryWorkerError):
            api.decode_query_response(b"{}", limits=bad)
    for bad in (None, True, 1, [], "\ud800"):
        with pytest.raises(api.QueryWorkerError):
            api.encode_query_request(bad, limits=limits)


@pytest.mark.parametrize("inbody_failure", [False, True], ids=["success", "failure"])
def test_11_reload_restores_preimported_identities(api, limits, toy, monkeypatch, inbody_failure):
    namespace = vars(api).copy()
    limits_class = api.QueryWorkerLimits
    spec_class = api.DockerQueryWorkerSpec
    encode_alias = api.encode_query_request
    planning_alias = api.build_worker_create_argv
    spec = spec_for(api, limits)
    spec.__post_init__()
    request = encode_alias("SELECT 1", limits=limits)
    planned = planning_alias(spec, resource_name="toy", host_db=toy)
    original_reload = importlib.reload
    observed = []
    planning_calls = []
    sentinel = RuntimeError("intentional in-body planning failure")

    def tracked_reload(module):
        reloaded = original_reload(module)
        assert reloaded is api
        assert reloaded.QueryWorkerLimits is not limits_class
        assert reloaded.DockerQueryWorkerSpec is not spec_class
        observed.append(reloaded)
        # A new namespace key must be removed too, not just the class aliases.
        reloaded._test_reload_namespace_probe = object()
        real_plan = reloaded.build_worker_create_argv

        def tracked_plan(*args, **kwargs):
            argv = real_plan(*args, **kwargs)
            planning_calls.append(argv)
            if inbody_failure:
                raise sentinel
            return argv

        reloaded.build_worker_create_argv = tracked_plan
        return reloaded

    try:
        with monkeypatch.context() as patch:
            patch.setattr(importlib, "reload", tracked_reload)
            if inbody_failure:
                with pytest.raises(RuntimeError) as caught:
                    test_11_import_and_planning_inert(api, limits, toy, monkeypatch)
                assert caught.value is sentinel
            else:
                test_11_import_and_planning_inert(api, limits, toy, monkeypatch)
        assert observed == [api] and len(planning_calls) == 1
        assert api.QueryWorkerLimits is limits_class, "pre-imported limits class identity changed"
        assert api.DockerQueryWorkerSpec is spec_class, "pre-imported spec class identity changed"
        assert vars(api).keys() == namespace.keys(), "reload leaked module namespace keys"
        assert all(vars(api)[key] is value for key, value in namespace.items())
        assert sys.modules[api.__name__] is api
        assert type(limits) is limits_class and type(spec) is spec_class and spec.limits is limits
        spec.__post_init__()
        assert encode_alias("SELECT 1", limits=limits) == request
        assert planning_alias(spec, resource_name="toy", host_db=toy) == planned
    finally:
        # Failure-safe control teardown cannot satisfy the preceding assertions.
        vars(api).clear()
        vars(api).update(namespace)
