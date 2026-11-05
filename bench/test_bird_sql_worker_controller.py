"""Controller preflight/construction and local spawn-boundary acceptance."""

import asyncio
from dataclasses import FrozenInstanceError, fields, replace
import importlib
import importlib.util
import inspect
import math
import json
import os
from pathlib import Path
import signal
import socket
import time

import pytest

from bench.test_bird_sql_worker_controller_integration import (
    assert_joined, controller_api, rescue, rig, wait_log,
)


def test_00_controller_api_required():
    assert importlib.util.find_spec("ptc.bird_sql_worker_controller") is not None, "controller API required"


@pytest.mark.parametrize("field,value", [
    ("control_stdout_max_bytes",0),("stderr_max_bytes",True),("pipe_chunk_bytes",1.5),
    ("process_join_timeout_s",0),("process_join_timeout_s",math.inf),
    ("process_join_timeout_s",True),("command_cwd",Path("relative")),
    ("docker_config_dir","/tmp"),("expected_cli_sha256","bad"),
    ("expected_payload_sha256","A"*64),("command_env",(("A","one"),("A","two"))),
    ("command_env",(("A=B","value"),)),("command_env",(("A","bad\0value"),)),
])
def test_11_invalid_config_no_spawn(rig, field, value):
    with pytest.raises(controller_api().QueryWorkerControllerError):
        replace(rig.config,**{field:value})
    assert rig.log()==[]


def test_11_fixed_source_closure_no_shrink(rig):
    api=controller_api()
    for values in (
        rig.config.expected_source_sha256[:-1],
        rig.config.expected_source_sha256 + (rig.config.expected_source_sha256[0],),
        (("../private","a"*64),) + rig.config.expected_source_sha256[1:],
    ):
        with pytest.raises(api.QueryWorkerControllerError):
            replace(rig.config,expected_source_sha256=values)
    assert rig.log()==[]


@pytest.mark.parametrize("mode", ["cli_digest","source_digest","payload_digest","request",
                                  "missing_cli","not_executable","missing_cwd","missing_config"])
def test_11_preflight_invalid_zero_processes(rig, mode):
    api=controller_api()
    config=rig.config
    query="SELECT 1"
    if mode=="cli_digest": config=replace(config,expected_cli_sha256="0"*64)
    if mode=="payload_digest": config=replace(config,expected_payload_sha256="0"*64)
    if mode=="source_digest":
        values=list(config.expected_source_sha256); values[0]=(values[0][0],"0"*64)
        config=replace(config,expected_source_sha256=tuple(values))
    if mode=="request": query="SELECT '"+ "x"*5000+"'"
    if mode=="missing_cli": rig.cli.unlink()
    if mode=="not_executable": rig.cli.chmod(0o600)
    if mode=="missing_cwd": config=replace(config,command_cwd=rig.root/"missing")
    if mode=="missing_config": config=replace(config,docker_config_dir=rig.root/"missing")
    async def scenario():
        c=rig.controller(config)
        with pytest.raises(api.QueryWorkerControllerError) as caught:
            await c.execute(query)
        assert rig.log()==[]
        assert c.state.phase=="CLOSED"
        assert str(rig.root) not in str(caught.value) and query not in str(caught.value)
        await c.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("phase",["prebody","spawn","reap"])
def test_07_late_reclaimer_cancellation_owns_process(rig, monkeypatch, phase):
    rig.settings(create_hang=True,create_effect=False)
    config=replace(rig.config,worker=replace(rig.config.worker,setup_timeout_s=0.12))
    api=controller_api()
    spawn_original=asyncio.create_subprocess_exec
    task_original=asyncio.create_task
    kill_original=os.killpg
    await_original=api.QueryWorkerController._await_reclamation
    discard_original=api.QueryWorkerController._discard_after

    async def scenario():
        release=asyncio.Event()
        launched=asyncio.Event()
        reap_release=asyncio.Event()
        waiting_spawn=asyncio.Event()
        waiting_reap=asyncio.Event()
        created=[]
        entries=[]
        kills=[]
        process=None
        success=False
        c=rig.controller(config)
        observation=dict(phase=phase,setup_s=0.12,join_s=config.process_join_timeout_s)

        async def held_spawn(*args,**kwargs):
            nonlocal process
            process=await spawn_original(*args,**kwargs)
            launched.set()
            await release.wait()
            return process

        def controlled_task(coro,*args,**kwargs):
            target=getattr(coro,"cr_code",None)
            target=target is not None and target.co_name=="_reclaim_local"
            if target:
                assert inspect.getcoroutinestate(coro)==inspect.CORO_CREATED
            task=task_original(coro,*args,**kwargs)
            if target:
                created.append(task)
                if phase=="prebody":
                    assert task.cancel("reclaimer-before-body")
                    observation["prebody_injected"]=True
            return task

        async def tracked_await(self,future):
            if self is c:
                point="spawn" if future is c._records[0].spawn else "reap"
                entries.append(point)
                (waiting_spawn if point=="spawn" else waiting_reap).set()
            return await await_original(self,future)

        async def held_discard(self,task,stream):
            await discard_original(self,task,stream)
            if self is c and phase=="reap":
                await reap_release.wait()

        def recorded_kill(group,sig):
            if process is not None and group==process.pid:
                kills.append((group,sig))
            return kill_original(group,sig)

        started=time.monotonic()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(asyncio,"create_subprocess_exec",held_spawn)
                patch.setattr(asyncio,"create_task",controlled_task)
                patch.setattr(os,"killpg",recorded_kill)
                patch.setattr(api.QueryWorkerController,"_await_reclamation",tracked_await)
                patch.setattr(api.QueryWorkerController,"_discard_after",held_discard)
                execution=asyncio.create_task(c.execute("SELECT 1"))
                await asyncio.wait_for(launched.wait(),1.2)
                row=await wait_log(rig,"create")
                assert row["pid"]==row["session"]==process.pid
                with pytest.raises(api.QueryWorkerRetirementPending):
                    await execution
                elapsed=time.monotonic()-started
                assert 0.12+config.process_join_timeout_s<=elapsed<1.5
                record=c._records[0]
                assert len(created)==1 and record.reclaim_task is created[0]
                collector=created[0]
                assert not record.spawn.done() and not release.is_set()
                assert process.returncode is None
                os.kill(process.pid,0)
                for _ in range(2):
                    with pytest.raises(api.QueryWorkerRetirementPending):
                        await c.aclose()
                assert any(p.kind.value=="CREATE" for p in c.state.pending)
                observation.update(pid=process.pid,session=row["session"],caller_elapsed_s=elapsed)
                if phase=="prebody":
                    assert collector.cancelled() and entries==[]
                    assert observation["prebody_injected"] is True
                else:
                    await asyncio.wait_for(waiting_spawn.wait(),config.process_join_timeout_s)
                    assert not collector.done() and not record.spawn.done()
                    if phase=="spawn":
                        assert collector.cancel("reclaimer-awaiting-spawn")
                        await asyncio.sleep(0)
                        assert collector.cancelling()==1 and not collector.done()
                        assert not record.spawn.cancelled()
                        observation["spawn_cancel_injected"]=True
                released=time.monotonic()
                release.set()
                if phase=="reap":
                    await asyncio.wait_for(waiting_reap.wait(),config.process_join_timeout_s)
                    assert record.reap is not None and not record.reap.done()
                    assert not collector.done() and record.spawn.done()
                    assert collector.cancel("reclaimer-awaiting-reap")
                    await asyncio.sleep(0)
                    assert collector.cancelling()==1 and not collector.done()
                    assert not record.reap.cancelled()
                    observation["reap_cancel_injected"]=True
                    reap_release.set()
                deadline=time.monotonic()+config.process_join_timeout_s
                while process.returncode is None and time.monotonic()<deadline:
                    await asyncio.sleep(0.002)
                assert process.returncode is not None, "cancelled collector abandoned actual owned Process"
                # Assertions precede rescue. A never-started collector can stay
                # cancelled, but its independently owned spawn/reap must settle.
                if not collector.cancelled():
                    await asyncio.wait_for(asyncio.shield(collector),config.process_join_timeout_s)
                    assert collector.exception() is None
                for task in record.tasks:
                    await asyncio.wait_for(asyncio.shield(task),config.process_join_timeout_s)
                completion=getattr(record,"reclaim_done",None)
                if completion is not None:
                    await asyncio.wait_for(asyncio.shield(completion),config.process_join_timeout_s)
                    assert completion.exception() is None
                assert record.process is process and record.spawn.done()
                assert record.reclaim_error is None and record.local_incomplete is False
                assert_joined(c)
                assert kills==[(process.pid,signal.SIGKILL)], "owned reap must be initiated exactly once"
                assert len(created)==1, "cancelled collectors must not be endlessly recreated"
                assert c._owner_task.done() and c._cleanup_task.done()
                assert c._local_uncertain and c.state.phase!="CLOSED"
                assert any(p.kind.value=="CREATE" for p in c.state.pending)
                with pytest.raises(api.QueryWorkerRetirementPending):
                    await c.aclose()
                assert len(rig.log())==1 and rig.log()[0]["command"]=="create"
                observation.update(reclaimed=True,collector_cancelled=collector.cancelled(),
                                   collector_done=collector.done(),created_collectors=len(created),
                                   await_entries=entries,remote_create_pending=True,
                                   reclamation_elapsed_s=time.monotonic()-released,
                                   all_local_tasks_settled=True,no_extra_remote_ops=True)
                observation["owned_group_kills"]=len(kills)
                success=True
        finally:
            release.set()
            reap_release.set()
            observation["failure_rescue_used"]=not success
            if not success and process is not None:
                # Failure only: never let rescue satisfy the cleanup assertions.
                if process.returncode is None:
                    os.killpg(process.pid,signal.SIGKILL)
                process.stdin.close()
                if c._records and c._records[0].tasks:
                    await asyncio.wait_for(asyncio.gather(
                        *c._records[0].tasks,return_exceptions=True),0.5)
                else:
                    await asyncio.wait_for(asyncio.gather(
                        discard_original(c,None,process.stdout),
                        discard_original(c,None,process.stderr),
                        process.stdin.wait_closed(),process.wait(),return_exceptions=True),0.5)
                if c._records:
                    await asyncio.wait_for(asyncio.shield(c._records[0].spawn),0.5)
                for task in created:
                    if not task.cancelled():
                        await asyncio.wait_for(asyncio.shield(task),0.5)
            (rig.root/"reclaimer-cancel-observation.json").write_text(json.dumps(observation))
    asyncio.run(scenario())


def test_11_import_construction_inert_frozen(rig, monkeypatch):
    api=controller_api()
    def forbidden(*args,**kwargs):
        pytest.fail("construction/import attempted execution or network")
    namespace=vars(api).copy()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(asyncio,"create_subprocess_exec",forbidden)
            patch.setattr(socket,"socket",forbidden)
            patch.setattr(Path,"mkdir",forbidden)
            importlib.reload(api)
            local=api.WorkerControllerConfig(**{f.name:getattr(rig.config,f.name)
                                               for f in fields(rig.config)})
            c=api.QueryWorkerController(config=local,host_db=rig.toy)
            assert c.state.phase=="NEW"
            with pytest.raises(FrozenInstanceError):
                rig.config.stderr_max_bytes=1
        assert rig.log()==[]
    finally:
        # Pre-imported classes retain this exact globals dictionary on reload.
        vars(api).clear()
        vars(api).update(namespace)


@pytest.mark.parametrize("operation",["create","start","inspect","rm","list"])
def test_07_cancel_during_actual_spawn_task(rig, monkeypatch, operation):
    original=asyncio.create_subprocess_exec
    entered=None
    async def delayed(*args,**kwargs):
        command="list" if args[5]=="container" else args[5]
        if command==operation:
            entered.set()
            await asyncio.sleep(0.04)
        return await original(*args,**kwargs)
    async def scenario():
        nonlocal entered
        entered=asyncio.Event()
        c=rig.controller()
        with monkeypatch.context() as patch:
            patch.setattr(asyncio,"create_subprocess_exec",delayed)
            task=asyncio.create_task(c.execute("SELECT 1"))
            await asyncio.wait_for(entered.wait(),1.2)
            task.cancel("spawn-first")
            with pytest.raises(asyncio.CancelledError):
                await task
        assert c.state.phase=="CLOSED"
        assert_joined(c)
    asyncio.run(scenario())


def test_11_changed_cleanup_executable_refuses_pending(rig):
    rig.settings(start_delay=0.12)
    async def scenario():
        c=rig.controller()
        task=asyncio.create_task(c.execute("SELECT 1"))
        await wait_log(rig,"start")
        rig.cli.write_text(rig.cli.read_text()+"\n# changed fixture identity\n")
        with pytest.raises(controller_api().QueryWorkerRetirementPending) as caught:
            await task
        assert c.state.phase!="CLOSED"
        assert not any(r["command"]=="rm" for r in rig.log())
        assert "fixture-cli" not in str(caught.value)
        assert_joined(c)
    asyncio.run(scenario())


def test_07_prebody_owner_cancel_no_terminal_busyloop(rig, monkeypatch):
    api=controller_api()
    original=asyncio.create_task
    async def scenario():
        c=rig.controller()
        def cancel_owner(coro,*args,**kwargs):
            task=original(coro,*args,**kwargs)
            if getattr(coro,"cr_code",None) and coro.cr_code.co_name=="_owner_entry":
                task.cancel("owner-before-body")
            return task
        with monkeypatch.context() as patch:
            patch.setattr(asyncio,"create_task",cancel_owner)
            before=time.monotonic()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(c.execute("SELECT 1"),0.5)
            assert time.monotonic()-before<0.5
            await asyncio.wait_for(c.aclose(),0.2)
        assert rig.log()==[]
    asyncio.run(scenario())


def test_07_late_spawn_after_both_deadlines_reclaimed(rig, monkeypatch):
    # Actually launch the owned CLI, then withhold its handle beyond BOTH
    # deadlines. An unresolved task/reference alone must not count as cleanup.
    rig.settings(create_hang=True,create_effect=False)
    worker=replace(rig.config.worker,setup_timeout_s=0.12)
    config=replace(rig.config,worker=worker)
    original=asyncio.create_subprocess_exec
    async def scenario():
        release=asyncio.Event()
        launched=asyncio.Event()
        process=None
        observation={"setup_s":worker.setup_timeout_s,
                     "join_s":config.process_join_timeout_s}
        async def hold_actual_handle(*args,**kwargs):
            nonlocal process
            process=await original(*args,**kwargs)
            launched.set()
            await release.wait()
            return process
        c=rig.controller(config)
        started=time.monotonic()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(asyncio,"create_subprocess_exec",hold_actual_handle)
                execution=asyncio.create_task(c.execute("SELECT 1"))
                await asyncio.wait_for(launched.wait(),1.2)
                row=await wait_log(rig,"create")
                assert row["pid"]==row["session"]==process.pid
                with pytest.raises(controller_api().QueryWorkerRetirementPending):
                    await execution
                elapsed=time.monotonic()-started
                observation.update(pid=process.pid,session=row["session"],
                                   caller_elapsed_s=elapsed)
                assert worker.setup_timeout_s+config.process_join_timeout_s <= elapsed < 1.5
                assert not release.is_set() and process.returncode is None
                os.kill(process.pid,0)
                record=c._records[0]
                assert not record.spawn.done()
                assert any(p.kind.value=="CREATE" for p in c.state.pending)
                assert c.state.phase!="CLOSED"
                for _ in range(2):
                    with pytest.raises(controller_api().QueryWorkerRetirementPending):
                        await c.aclose()
                released=time.monotonic()
                release.set()
                deadline=released+config.process_join_timeout_s
                while process.returncode is None and time.monotonic()<deadline:
                    await asyncio.sleep(0.002)
                assert process.returncode is not None, "late owned CLI process was not reclaimed"
                reclaim=getattr(record,"reclaim_task",None)
                assert reclaim is not None, "late spawn needs a retained reclamation task"
                await asyncio.wait_for(asyncio.shield(reclaim),config.process_join_timeout_s)
                assert record.spawn.done() and record.process is process
                assert reclaim.done() and not reclaim.cancelled() and reclaim.exception() is None
                assert record.reclaim_error is None and record.local_incomplete is False
                assert_joined(c)
                assert all(task.done() for task in record.tasks)
                assert c._owner_task.done() and c._cleanup_task.done()
                assert c._local_uncertain and c.state.phase!="CLOSED"
                before=len(rig.log())
                with pytest.raises(controller_api().QueryWorkerRetirementPending):
                    await c.aclose()
                assert len(rig.log())==before==1
                observation.update(reclaimed=True,local_incomplete=record.local_incomplete,
                                   remote_create_pending=True,reclaim_task_done=reclaim.done(),
                                   reclamation_elapsed_s=time.monotonic()-released,
                                   no_new_remote_commands=True)
        finally:
            # Old-source RED must be a leak assertion, not a leaked-process or
            # ResourceWarning artifact. Rescue only this actually launched PID.
            release.set()
            if c._records:
                await asyncio.wait_for(asyncio.shield(c._records[0].spawn),0.5)
                record=c._records[0]
                reclaim=getattr(record,"reclaim_task",None)
                if reclaim is not None:
                    await asyncio.wait_for(asyncio.shield(reclaim),0.5)
                if process is not None and process.returncode is None:
                    os.killpg(process.pid,signal.SIGKILL)
                if process is not None and not record.tasks:
                    process.stdin.close()
                    await asyncio.wait_for(asyncio.gather(
                        c._discard_after(None,process.stdout),
                        c._discard_after(None,process.stderr),
                        process.stdin.wait_closed(),process.wait(),
                        return_exceptions=True),0.5)
                await rescue(c)
            (rig.root/"late-spawn-observation.json").write_text(json.dumps(observation))
    asyncio.run(scenario())


@pytest.mark.parametrize("inbody_failure",[False,True],ids=["success","failure"])
def test_11_reload_restores_preimported_controller_identities(rig, monkeypatch, inbody_failure):
    api=controller_api()
    dictionary=vars(api)
    namespace=dictionary.copy()
    config_alias=api.WorkerControllerConfig
    controller_alias=api.QueryWorkerController
    config=rig.config
    existing=controller_alias(config=config,host_db=rig.toy)
    config.__post_init__()
    assert type(config) is config_alias and type(existing) is controller_alias
    assert existing.state.phase=="NEW" and rig.log()==[]
    original_reload=importlib.reload
    observed=[]
    constructed=[]
    sentinel=RuntimeError("intentional post-construction failure")

    def tracked_reload(module):
        reloaded=original_reload(module)
        assert reloaded is api
        assert reloaded.WorkerControllerConfig is not config_alias
        assert reloaded.QueryWorkerController is not controller_alias
        real_constructor=reloaded.QueryWorkerController
        observed.append((reloaded.WorkerControllerConfig,real_constructor))
        reloaded._test_reload_namespace_probe=object()

        def tracked_constructor(*args,**kwargs):
            controller=real_constructor(*args,**kwargs)
            assert type(controller) is real_constructor and controller.state.phase=="NEW"
            constructed.append(controller)
            if inbody_failure:
                raise sentinel
            return controller

        reloaded.QueryWorkerController=tracked_constructor
        return reloaded

    try:
        with monkeypatch.context() as patch:
            patch.setattr(importlib,"reload",tracked_reload)
            if inbody_failure:
                with pytest.raises(RuntimeError) as caught:
                    test_11_import_construction_inert_frozen(rig,monkeypatch)
                assert caught.value is sentinel
            else:
                test_11_import_construction_inert_frozen(rig,monkeypatch)
        assert len(observed)==len(constructed)==1
        assert api.WorkerControllerConfig is config_alias, "pre-imported controller config identity changed"
        assert api.QueryWorkerController is controller_alias, "pre-imported controller class identity changed"
        assert vars(api) is dictionary and dictionary.keys()==namespace.keys()
        assert all(dictionary[key] is value for key,value in namespace.items())
        assert controller_api() is api
        assert type(config) is config_alias and type(existing) is controller_alias
        config.__post_init__()
        assert type(replace(config)) is config_alias
        assert existing._config is config and existing.state.phase=="NEW"
        assert existing._owner_task is None and existing._loop is None
        fresh=controller_alias(config=config,host_db=rig.toy)
        assert type(fresh) is controller_alias and fresh._config is config
        assert fresh.state.phase=="NEW" and fresh._owner_task is None and fresh._loop is None
        assert rig.log()==[]
    finally:
        # Failure-safe teardown cannot satisfy the preceding identity assertions.
        dictionary.clear()
        dictionary.update(namespace)
