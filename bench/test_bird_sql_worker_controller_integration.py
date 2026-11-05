"""Real local CLI/pipes/payload fixtures, never real Docker qualification."""

import asyncio
from dataclasses import dataclass, replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time

import pytest

from bench.score import execution_accuracy
from bench.task import SqlTask
from ptc.bird_sql_worker import DockerQueryWorkerSpec, QueryWorkerLimits, query_worker_source


# Generated into pytest tmp, not another source file or a generic executor.
CLI_BODY = r'''
import hashlib, json, os, pathlib, subprocess, sys, threading, time
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
settings = json.loads((root / "settings.json").read_text())
args = sys.argv[1:]
assert args[:1] == ["--config"] and args[2:3] == ["--context"]
assert args[3] == "fixture-context"
args = args[4:]
command = "list" if args[:2] == ["container", "ls"] else args[0]
pid = os.getpid()
def log(**values):
    values.update(command=command, pid=pid, session=os.getsid(0), cwd_ok=os.getcwd()==str(root),
                  ambient_absent="CONTROLLER_AMBIENT_SECRET" not in os.environ)
    fd = os.open(root / "commands.jsonl", os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)
    try: os.write(fd, (json.dumps(values)+"\n").encode())
    finally: os.close(fd)
def load():
    path = root / "registry.json"
    return json.loads(path.read_text()) if path.exists() else {}
def save(reg):
    temp = root / ("registry-" + str(pid))
    temp.write_text(json.dumps(reg)); temp.replace(root / "registry.json")
def emit(value):
    sys.stdout.write(json.dumps(value)); sys.stdout.flush()
def flood(fd, count):
    while count:
        chunk = b"z" * min(count, 4096); os.write(fd, chunk); count -= len(chunk)
if command == "create":
    name = args[args.index("--name")+1]
    label = args[args.index("--label")+1]
    assert label.startswith("cotrain.sql-worker.owner=")
    owner = label.split("=",1)[1]
    assert args.count("--mount")==1 and args[args.index("--workdir")+1]=="/task"
    assert "--interactive" in args and args[-4:-1]==["-I","-B","-c"]
    assert args[args.index("--pull")+1]=="never"
    assert args[args.index("--network")+1]=="none"
    ident = hashlib.sha256((name+owner).encode()).hexdigest()
    source = args[-1]
    log(name=name, owner=owner, ident=ident, payload_sha=hashlib.sha256(source.encode()).hexdigest(),
        static_flags=[v for v in args[:-1] if v.startswith("--")])
    time.sleep(settings.get("create_delay",0))
    if settings.get("create_hang"): time.sleep(10)
    if settings.get("create_effect",True):
        reg = load()
        reg[ident] = dict(name=name, owner=owner, source=source, started=False, inspects=0, exit=0)
        save(reg)
    if settings.get("create_flood"):
        a=threading.Thread(target=flood,args=(1,100000)); b=threading.Thread(target=flood,args=(2,100000))
        a.start(); b.start(); a.join(); b.join()
    if settings.get("create_nonzero"):
        sys.stderr.write("synthetic not found\n"); sys.exit(9)
    print(settings.get("create_id",ident),flush=True)
elif command == "inspect":
    assert args[:3]==["inspect","--type","container"] and len(args)==4
    ident=args[3]; reg=load()
    if ident not in reg:
        log(ident=ident); sys.stderr.write("synthetic not found\n"); sys.exit(1)
    item=reg[ident]; item["inspects"]+=1; count=item["inspects"]; save(reg)
    log(ident=ident, number=count)
    if count==settings.get("inspect_delay_at"):
        time.sleep(settings.get("inspect_delay",0))
    state=dict(Status="exited" if item["started"] else "created", Running=False,
               OOMKilled=False, ExitCode=item["exit"], Pid=0, Error="", FinishedAt="")
    if item["started"]:
        mode=settings.get("guest_state")
        if mode=="nonzero": state["ExitCode"]=7
        if mode=="oom": state["OOMKilled"]=True
        if mode=="running": state.update(Status="running",Running=True)
        if mode=="bad_exit_type": state["ExitCode"]=False
    obj=dict(Id=ident,Name="/"+item["name"],Config=dict(Labels={
        "cotrain.sql-worker.owner":item["owner"],"fixture.extra":"allowed"},Image="fixture"),
        State=state,Mounts=[],HostConfig={},NetworkSettings={})
    fault=settings.get("inspect_fault") if count==settings.get("inspect_fault_at",1) else None
    if fault=="foreign": obj["Config"]["Labels"]["cotrain.sql-worker.owner"]="foreign"
    if fault=="name": obj["Name"]="/foreign"
    if fault=="id": obj["Id"]="f"*64
    if fault=="type": obj["State"]["Running"]=0
    if fault=="shape": emit(obj); sys.exit(0)
    if fault=="duplicate":
        sys.stdout.write('[{"Id":"'+ident+'","Id":"'+ident+'"}]'); sys.exit(0)
    if fault=="bad_json": sys.stdout.write("{"); sys.exit(0)
    if fault=="stderr_overflow": flood(2,100000)
    emit([obj])
elif command == "start":
    assert args[:3]==["start","--attach","--interactive"] and len(args)==4
    ident=args[3]; reg=load(); item=reg[ident]
    log(ident=ident)
    time.sleep(settings.get("start_delay",0))
    if settings.get("start_hang"): time.sleep(10)
    if settings.get("start_flood"):
        a=threading.Thread(target=flood,args=(1,100000)); b=threading.Thread(target=flood,args=(2,100000))
        a.start(); b.start(); a.join(); b.join()
    if settings.get("start_stderr"): flood(2,100000)
    child=subprocess.Popen([os.environ["FIXTURE_PYTHON"],"-I","-B","-c",item["source"]],
        cwd=root,env={"PYTHONDONTWRITEBYTECODE":"1"},
        stdin=sys.stdin.buffer,stdout=sys.stdout.buffer,stderr=sys.stderr.buffer)
    log(ident=ident, child_pid=child.pid)
    code=child.wait()
    item["started"]=True; item["exit"]=code; reg[ident]=item; save(reg)
    sys.exit(settings.get("client_exit",0))
elif command == "rm":
    assert args[:2]==["rm","--force"] and len(args)==3
    ident=args[2]; reg=load(); log(ident=ident)
    time.sleep(settings.get("remove_delay",0))
    if settings.get("remove_fail"):
        sys.stderr.write("synthetic not found\n"); sys.exit(1)
    if not settings.get("remove_keep"): reg.pop(ident,None)
    save(reg); print(ident,flush=True)
elif command == "list":
    assert args[:4]==["container","ls","--all","--no-trunc"]
    assert args[4]=="--filter" and args[6:]==["--format","{{json .}}"]
    owner=args[5].split("=",2)[2]; log(owner=owner)
    time.sleep(settings.get("list_delay",0))
    mode=settings.get("list_fault")
    if mode=="fail": sys.stderr.write("synthetic not found\n"); sys.exit(1)
    if mode=="json": sys.stdout.write("["); sys.exit(0)
    if mode=="array": sys.stdout.write("[]"); sys.exit(0)
    if mode=="duplicate": sys.stdout.write('{"ID":"a","ID":"b"}\n'); sys.exit(0)
    if mode=="overflow": flood(1,100000); sys.exit(0)
    for ident,item in load().items():
        if item["owner"]==owner:
            emit(dict(ID=ident,Names=item["name"],Labels="cotrain.sql-worker.owner="+owner,
                      State="exited",Status="Exited",Image="fixture",Command="python",Ports=""))
            sys.stdout.write("\n")
else:
    raise AssertionError("unexpected fixture vocabulary")
'''


def controller_api():
    return importlib.import_module("ptc.bird_sql_worker_controller")


def source_expectations():
    root = Path(__file__).resolve().parents[1]
    names = ("ptc/bird_sql_worker_controller.py", "ptc/bird_sql_worker.py",
             "ptc/bird_sql_worker_lifecycle.py", "ptc/sqlite_safety.py", "ptc/sql_runtime.py")
    return tuple((name, hashlib.sha256((root / name).read_bytes()).hexdigest()) for name in names)


@dataclass
class Rig:
    root: Path
    cli: Path
    toy: Path
    config: object

    def settings(self, **values):
        (self.root / "settings.json").write_text(json.dumps(values))

    def log(self):
        path = self.root / "commands.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def registry(self):
        path = self.root / "registry.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def controller(self, config=None):
        return controller_api().QueryWorkerController(config=config or self.config, host_db=self.toy)


@pytest.fixture
def rig(tmp_path):
    cli = tmp_path / "fixture-cli"
    cli.write_text("#!" + sys.executable + "\n" + CLI_BODY)
    cli.chmod(0o700)
    toy = tmp_path / "db.sqlite"
    conn = sqlite3.connect(toy)
    try:
        conn.executescript("CREATE TABLE t(n INTEGER);INSERT INTO t VALUES(1),(2),(3),(4);")
        conn.commit()
    finally:
        conn.close()
    config_dir = tmp_path / "cli-config"
    config_dir.mkdir()
    limits = QueryWorkerLimits(3, 0.08, 4096, 8192)
    worker = DockerQueryWorkerSpec(
        cli_path=str(cli), daemon_context="fixture-context",
        image="fixture/worker@sha256:" + "a"*64, guest_python="/usr/bin/python3",
        uid=1234, gid=1234, cpus=0.5, memory_bytes=67108864, pids_limit=16,
        tmpfs_bytes=1048576, limits=limits, setup_timeout_s=0.8, start_timeout_s=0.8,
        retirement_timeout_s=0.8)
    api = controller_api()
    config = api.WorkerControllerConfig(
        worker=worker, docker_config_dir=config_dir, command_cwd=tmp_path,
        command_env=(("FIXTURE_ROOT",str(tmp_path)),("FIXTURE_PYTHON",sys.executable),
                     ("PYTHONDONTWRITEBYTECODE","1")),
        control_stdout_max_bytes=8192, stderr_max_bytes=1024, pipe_chunk_bytes=256,
        process_join_timeout_s=0.3, expected_cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
        expected_payload_sha256=hashlib.sha256(query_worker_source(limits=limits)).hexdigest(),
        expected_source_sha256=source_expectations())
    obj = Rig(tmp_path, cli, toy, config)
    obj.settings()
    yield obj
    # Only session leaders recorded by this test-owned CLI, never host-wide kills.
    for pid in {row["pid"] for row in obj.log() if row["pid"] == row["session"]}:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


async def wait_log(rig, command, *, number=None, require_child=False):
    deadline = time.monotonic()+1.2
    while time.monotonic() < deadline:
        rows = [row for row in rig.log() if row["command"] == command
                and (number is None or row.get("number") == number)
                and (not require_child or "child_pid" in row)]
        if rows:
            return rows[-1]
        await asyncio.sleep(0.002)
    pytest.fail("fixture command observation exceeded 1.2s")


async def rescue(controller):
    # Failure/mutant teardown only: settle the same retained local handles.
    for record in controller._records:
        spawn = record.spawn
        if not spawn.done():
            await asyncio.wait_for(asyncio.shield(spawn), 0.5)
        if not spawn.cancelled() and spawn.exception() is None:
            proc = spawn.result()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if record.readers:
                await asyncio.wait_for(asyncio.gather(*(
                    controller._discard_after(task,stream) for task,stream in record.readers
                )),0.5)
            await asyncio.wait_for(proc.wait(), 0.5)
        for task in record.tasks:
            if not task.done():
                task.cancel()
        if record.tasks:
            await asyncio.gather(*record.tasks, return_exceptions=True)


def assert_joined(controller):
    for record in controller._records:
        assert record.spawn.done(), "spawn handle must be joined"
        if not record.spawn.cancelled() and record.spawn.exception() is None:
            assert record.spawn.result().returncode is not None, "fixture process still alive"
            try:
                os.kill(record.spawn.result().pid,0)
            except ProcessLookupError:
                pass
            else:
                pytest.fail("owned fixture leader was not reaped")
        assert all(task.done() for task in record.tasks), "fixture pump/task still detached"
    assert all(record.join_task is not None and record.join_task.done()
               for record in controller._records), "local join omitted"


def test_01_real_payload_original_ex_and_association(rig, monkeypatch):
    monkeypatch.setenv("CONTROLLER_AMBIENT_SECRET", "must-not-inherit")
    async def scenario():
        for sql, score, expected in [
            ("SELECT n FROM t WHERE n=1",1.0,((1,),)),
            ("SELECT n FROM t WHERE n=2",0.0,((2,),)),
        ]:
            c = rig.controller()
            result = await c.execute(sql)
            assert result.status == "rows" and result.rows == expected
            assert c.state.phase == "CLOSED"
            assert_joined(c)
            await c.aclose()
            with pytest.raises(controller_api().QueryWorkerControllerError):
                await c.execute(sql)
            task = SqlTask("toy","one","","SELECT n FROM t WHERE n=1","toy",str(rig.toy),
                           "simple","annotated","select","select","fixture")
            ex = execution_accuracy(sql,task,timeout_s=0.1,max_rows=3)
            assert (ex.score,ex.valid)==(score,True)
        rows = rig.log()
        creates = [r for r in rows if r["command"]=="create"]
        assert len(creates)==2 and len({r["name"] for r in creates})==2
        for create in creates:
            owned = [r for r in rows if r.get("ident")==create["ident"]]
            assert len([r for r in owned if r["command"]=="start" and "child_pid" not in r])==1
            assert len([r for r in owned if r["command"]=="rm"])==1
            assert create["payload_sha"]==rig.config.expected_payload_sha256
            assert all(r["cwd_ok"] and r["ambient_absent"] for r in rows)
            positions = [r["command"] for r in owned]
            assert positions.index("inspect") < positions.index("start") < positions.index("rm")
        assert not rig.registry()
    asyncio.run(scenario())


def test_03_nine_controllers_no_quota(rig):
    async def scenario():
        values=[]
        for i in range(9):
            c=rig.controller()
            values.append((await c.execute(f"SELECT {i}")).rows[0][0])
            assert c.state.phase=="CLOSED"
            assert_joined(c)
        assert values==list(range(9))
        assert len([r for r in rig.log() if r["command"]=="create"])==9
        assert len([r for r in rig.log() if r["command"]=="start" and "child_pid" not in r])==9
    asyncio.run(scenario())


def test_04_prestart_cancel_zero_spawn(rig):
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        task.cancel("prestart")
        with pytest.raises(asyncio.CancelledError):
            await task
        await c.aclose()
        assert c.state.phase=="CLOSED" and rig.log()==[]
    asyncio.run(scenario())


def test_04_late_create_cancel_no_start(rig):
    rig.settings(create_delay=0.12)
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        await wait_log(rig,"create")
        task.cancel("first")
        await asyncio.sleep(0.01)
        task.cancel("second")
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args==("first",)
        assert c.state.phase=="CLOSED"
        assert not any(r["command"]=="start" for r in rig.log())
        assert len([r for r in rig.log() if r["command"]=="rm"])==1
        assert_joined(c)
        await c.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("settings", [
    {"create_hang":True,"create_effect":False},
    {"create_nonzero":True,"create_effect":False},
    {"create_nonzero":True,"create_effect":True},
    {"create_id":"short"},
    {"create_id":"a"*64+"\nextra"},
    {"create_flood":True},
])
def test_05_uncertain_create_never_closed(rig, settings):
    rig.settings(**settings)
    worker=replace(rig.config.worker,setup_timeout_s=0.12)
    config=replace(rig.config,worker=worker)
    async def scenario():
        c=rig.controller(config)
        started=time.monotonic()
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.execute("SELECT 1")
        assert time.monotonic()-started < 1.5
        assert c.state.phase!="CLOSED"
        assert any(p.kind.value=="CREATE" for p in c.state.pending), "uncertain CREATE lost"
        assert not any(r["command"] in ("start","rm","list") for r in rig.log())
        assert_joined(c)
        for _ in range(2):
            with pytest.raises(controller_api().QueryWorkerRetirementPending):
                await c.aclose()
        assert len([r for r in rig.log() if r["command"]=="create"])<=1
        assert len(c._records)==1, "one retained CREATE spawn attempt, no retry"
    asyncio.run(scenario())


@pytest.mark.parametrize("settings,large", [
    ({"start_flood":True},False), ({"start_stderr":True},False),
    ({"start_hang":True},True),
])
def test_06_bounded_pipes_blocked_input_join(rig, settings, large):
    rig.settings(**settings)
    limits=replace(rig.config.worker.limits,request_max_bytes=600000)
    worker=replace(rig.config.worker,limits=limits,start_timeout_s=0.12)
    config=replace(rig.config,worker=worker,
                   expected_payload_sha256=hashlib.sha256(query_worker_source(limits=limits)).hexdigest())
    query="SELECT 1" + (" /*"+"x"*500000+"*/" if large else "")
    async def scenario():
        c=rig.controller(config)
        try:
            with pytest.raises(controller_api().QueryWorkerControllerError):
                await c.execute(query)
            assert_joined(c)
            assert c.state.phase=="CLOSED"
            assert not rig.registry()
        finally:
            await rescue(c)
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["start","inspect_admit","inspect_guest","rm","list"])
def test_07_cancel_during_commands_repeated_close(rig, stage):
    settings={
        "start":{"start_delay":0.15},
        "inspect_admit":{"inspect_delay_at":1,"inspect_delay":0.12},
        "inspect_guest":{"inspect_delay_at":2,"inspect_delay":0.12},
        "rm":{"remove_delay":0.12},
        "list":{"list_delay":0.12},
    }[stage]
    rig.settings(**settings)
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        await wait_log(rig,"inspect" if stage.startswith("inspect") else stage,
                       number=1 if stage=="inspect_admit" else 2 if stage=="inspect_guest" else None)
        task.cancel("first-caller")
        closes=[asyncio.create_task(c.aclose()) for _ in range(3)]
        await asyncio.sleep(0.005)
        task.cancel("second-caller")
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args==("first-caller",)
        await asyncio.gather(*closes)
        assert c.state.phase=="CLOSED"
        assert_joined(c)
        assert len([r for r in rig.log() if r["command"]=="create"])==1
        assert len([r for r in rig.log() if r["command"]=="rm"])==1
        assert len([r for r in rig.log() if r["command"]=="start" and "child_pid" not in r])<=1
    asyncio.run(scenario())


def test_07_caller_cancel_wins_cleanup_failure(rig):
    rig.settings(start_delay=0.15,remove_fail=True)
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        await wait_log(rig,"start")
        task.cancel("first-original")
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value is c._caller_cancel
        assert caught.value.args==("first-original",)
        assert_joined(c)
        assert c.state.phase!="CLOSED"
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("blocked", [True,False])
def test_07_cancel_input_or_actual_query(rig, blocked):
    rig.settings(**({"start_hang":True} if blocked else {}))
    limits=replace(rig.config.worker.limits,request_max_bytes=600000)
    worker=replace(rig.config.worker,limits=limits)
    config=replace(rig.config,worker=worker,
                   expected_payload_sha256=hashlib.sha256(query_worker_source(limits=limits)).hexdigest())
    query=("SELECT 1 /*"+"x"*500000+"*/" if blocked else
           "WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r")
    async def scenario():
        c=rig.controller(config)
        task=asyncio.create_task(c.execute(query))
        await wait_log(rig,"start",require_child=not blocked)
        task.cancel("input-query-first")
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args==("input-query-first",)
        assert c.state.phase=="CLOSED"
        assert_joined(c)
        await c.aclose()
    asyncio.run(scenario())


def test_07_owner_cancel_identity_and_terminal_no_busyloop(rig):
    rig.settings(start_delay=0.15)
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        await wait_log(rig,"start")
        c._owner_task.cancel("owner-original")
        with pytest.raises(asyncio.CancelledError) as caught:
            await asyncio.wait_for(task,1.5)
        assert caught.value is c._outcome.error
        assert caught.value.args==("owner-original",)
        assert_joined(c)
        await asyncio.wait_for(c.aclose(),0.2)
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["nonzero","oom","running","bad_exit_type"])
def test_08_client_zero_not_guest_success(rig, mode):
    rig.settings(guest_state=mode)
    async def scenario():
        c=rig.controller()
        with pytest.raises(controller_api().QueryWorkerControllerError):
            await c.execute("SELECT 1")
        if mode=="bad_exit_type":
            assert c.state.phase!="CLOSED"
            with pytest.raises(controller_api().QueryWorkerRetirementPending):
                await c.aclose()
        else:
            assert c.state.phase=="CLOSED"
        assert_joined(c)
    asyncio.run(scenario())


@pytest.mark.parametrize("settings", [
    {"remove_fail":True},{"remove_keep":True},{"list_fault":"fail"},
    {"list_fault":"json"},{"list_fault":"array"},{"list_fault":"duplicate"},
    {"list_fault":"overflow"},
])
def test_09_retirement_uncertainty_never_success(rig, settings):
    rig.settings(**settings)
    async def scenario():
        c=rig.controller()
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.execute("SELECT 1")
        assert c.state.phase!="CLOSED"
        assert_joined(c)
        count=len(rig.log())
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.aclose()
        assert len(rig.log())==count, "no implicit recovery/retry"
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["foreign","name","id","type","shape","duplicate",
                                  "bad_json","stderr_overflow"])
def test_10_admission_strict_no_foreign_deletion(rig, fault):
    rig.settings(inspect_fault=fault)
    async def scenario():
        c=rig.controller()
        with pytest.raises(controller_api().QueryWorkerRetirementPending):
            await c.execute("SELECT 1")
        assert not any(r["command"] in ("start","rm") for r in rig.log())
        assert c.state.phase!="CLOSED"
        assert_joined(c)
    asyncio.run(scenario())


@pytest.mark.parametrize("query,status", [
    ("SELECT * FROM missing","sql_error"),("SELECT n FROM t","row_refusal"),
    ("WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r",
     "query_timeout"),
])
def test_01_worker_domain_results_preserved(rig, query, status):
    async def scenario():
        c=rig.controller()
        out=await c.execute(query)
        assert out.status==status and c.state.phase=="CLOSED"
        assert_joined(c)
    asyncio.run(scenario())


def test_01_infrastructure_envelope_not_result(rig):
    limits=replace(rig.config.worker.limits,response_max_bytes=160)
    worker=replace(rig.config.worker,limits=limits)
    config=replace(rig.config,worker=worker,
                   expected_payload_sha256=hashlib.sha256(query_worker_source(limits=limits)).hexdigest())
    async def scenario():
        c=rig.controller(config)
        with pytest.raises(controller_api().QueryWorkerControllerError):
            await c.execute("SELECT hex(zeroblob(500))")
        assert c.state.phase=="CLOSED"
    asyncio.run(scenario())
