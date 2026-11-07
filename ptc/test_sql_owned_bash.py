"""Original owners with local synthetic actors, never native qualification."""

import asyncio
from dataclasses import replace
import hashlib

import pytest
from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.task import Task, TaskData

from bench.bird_bash_live import public_bash_prompt
from bench.task import SqlTask
from bench.test_bird_sql_broker_integration import assert_owned_settled
from bench.test_bird_sql_worker_controller_integration import rig, wait_log
from ptc.bird_sql_broker import SqlBrokerRetirementPending, TaskSqlBrokerConfig
from ptc.bird_sql_worker import QueryWorkerError, QueryWorkerResult
from ptc.bird_sql_worker_controller import QueryWorkerController
from ptc.sql_owned_bash import BashSqlBinding, BashSqlError, BashSqlCleanupPending
from train.sql_episodes import InstrumentSettings


def inputs(r, **updates):
    task = SqlTask("toy", "Return one", "EVIDENCE_CANARY", "GOLD_CANARY",
                   "toy", str(r.toy), "simple", "annotated", "select", "select", "fixture")
    instrument = InstrumentSettings(
        2, 3, 3, "set", 0.1, 5.0, 0.08, "synthetic", "synthetic",
        ("ptc/bird_sql_worker.py",), "a" * 64)
    data = TaskData(name="toy", prompt=public_bash_prompt(
        task.question, "CREATE TABLE t(n);"))
    values = dict(
        task=Task(data), sql_task=task, instrument=instrument,
        harness=BashHarness(BashHarnessConfig(id="bash", skills=[])),
        schema="CREATE TABLE t(n);",
        broker_config=TaskSqlBrokerConfig(r.config, 0, 2.0, 1.5),
        db_sha256=hashlib.sha256(r.toy.read_bytes()).hexdigest(),
        db_size_bytes=r.toy.stat().st_size)
    values.update(updates)
    return values


def binding(r, **updates):
    return BashSqlBinding(**inputs(r, **updates))


def creates(r):
    return [row for row in r.log() if row["command"] == "create"]


@pytest.mark.parametrize("field", ["task", "sql_task", "instrument", "harness", "broker_config"])
def test_impostors_zero_actions(rig, field):
    with pytest.raises(BashSqlError):
        binding(rig, **{field: object()})
    assert rig.log() == []


def test_direct_binding_rejects_private_public_data(rig):
    values = inputs(rig)
    values["task"].data = TaskData(name="toy", prompt="GOLD_CANARY")
    with pytest.raises(BashSqlError):
        BashSqlBinding(**values)
    assert rig.log() == []


def test_wrong_db_before_action(rig):
    leaf = binding(rig, db_sha256="f" * 64)
    rejected = False
    try:
        leaf.before_action("one")
    except BashSqlError:
        rejected = True
    assert rejected, "wrong DB must be rejected before shell action admission"
    assert creates(rig) == []
    asyncio.run(leaf.aclose())


def test_two_queries_one_action_original_owners(rig):
    original = rig.toy.read_bytes()
    async def scenario():
        leaf = binding(rig)
        leaf.before_action("one")
        for n in (1, 2):
            out = await leaf.execute_sql(query=f"SELECT n FROM t WHERE n={n}")
            assert type(out) is QueryWorkerResult and out.rows == ((n,),)
        leaf.after_action("one")
        leaf.before_action("two")
        leaf.after_action("two")
        with pytest.raises(BashSqlError):
            leaf.require_valid()
        await leaf.aclose()
        leaf.require_valid()
        close_task = leaf._close_task
        await leaf.aclose()
        assert leaf._close_task is close_task
        assert_owned_settled(leaf._broker, rig)
        assert len(creates(rig)) == 2
        assert len([r for r in rig.log() if r["command"] == "start"
                    and "child_pid" not in r]) == 2
        assert rig.toy.read_bytes() == original
    asyncio.run(scenario())


@pytest.mark.parametrize("query", [
    "SELECT * FROM missing",
    "SELECT n FROM t",
    "WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT sum(x) FROM r",
    "SELECT " + "1" * 5000,
    "DELETE FROM t",
])
def test_sql_failure_is_invalid_not_reward(rig, query):
    async def scenario():
        leaf = binding(rig)
        leaf.before_action("one")
        error = QueryWorkerError if len(query) > 4096 else BashSqlError
        with pytest.raises(error):
            await leaf.execute_sql(query=query)
        with pytest.raises(BashSqlError):
            leaf.require_valid()
        with pytest.raises(BashSqlError):
            leaf.before_action("two")
        if len(query) > 4096:
            assert creates(rig) == []
        await leaf.aclose()
        assert_owned_settled(leaf._broker, rig)
    asyncio.run(scenario())


@pytest.mark.parametrize("drift", [
    "data", "instrument", "config", "broker_config", "db", "executor",
])
def test_drift_zero_next_actions(rig, drift):
    leaf = binding(rig)
    if drift == "data":
        leaf._task.data = leaf._task.data.model_copy(update={"prompt": "changed"})
    elif drift == "instrument":
        leaf._instrument = replace(leaf._instrument, action_cap=3)
    elif drift == "config":
        leaf._harness.config = leaf._harness.config.model_copy(update={"edit": False})
    elif drift == "broker_config":
        leaf._broker_config = replace(leaf._broker_config, close_timeout_s=0.001)
    elif drift == "db":
        with rig.toy.open("ab") as stream:
            stream.write(b"drift")
    else:
        leaf._broker = object()
    with pytest.raises(BashSqlError):
        leaf.before_action("one")
    assert rig.log() == []
    asyncio.run(leaf.aclose())


def test_executor_bytes_drift_zero_action_admission(rig):
    leaf = binding(rig)
    rig.cli.write_bytes(rig.cli.read_bytes() + b"\n# executor drift\n")
    rejected = False
    try:
        leaf.before_action("one")
    except BashSqlError:
        rejected = True
    assert rejected, "current executor bytes must gate first action admission"
    assert leaf._ids == set() and leaf._active is None
    assert creates(rig) == []
    asyncio.run(leaf.aclose())


def test_executor_bytes_drift_after_action(rig):
    leaf = binding(rig)
    leaf.before_action("one")
    rig.cli.write_bytes(rig.cli.read_bytes() + b"\n# executor drift\n")
    rejected = False
    try:
        leaf.after_action("one")
    except BashSqlError:
        rejected = True
    assert rejected, "current executor bytes must gate no-SQL action completion"
    assert creates(rig) == []
    asyncio.run(leaf.aclose())


def test_executor_bytes_drift_final_validation(rig):
    async def scenario():
        leaf = binding(rig)
        leaf.before_action("one")
        leaf.after_action("one")
        await leaf.aclose()
        leaf.require_valid()
        rig.cli.write_bytes(rig.cli.read_bytes() + b"\n# executor drift\n")
        rejected = False
        try:
            leaf.require_valid()
        except BashSqlError:
            rejected = True
        assert rejected, "closed valid action must not hide later executor byte drift"
        assert creates(rig) == []
    asyncio.run(scenario())


@pytest.mark.parametrize("replay", [True, False])
def test_action_ids_and_cap_not_query_quota(rig, replay):
    leaf = binding(rig)
    leaf.before_action("one")
    leaf.after_action("one")
    if not replay:
        leaf.before_action("two")
        leaf.after_action("two")
    with pytest.raises(BashSqlError):
        leaf.before_action("one" if replay else "three")
    assert rig.log() == []
    asyncio.run(leaf.aclose())


def hold_original_settlement(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    original = BashSqlBinding._close_owner

    async def held(leaf):
        try:
            await original(leaf)
        finally:
            entered.set()
            await release.wait()

    monkeypatch.setattr(BashSqlBinding, "_close_owner", held)
    return entered, release


@pytest.mark.parametrize("inventory_fault", [None, "fail"])
def test_cancellation_joins_original_owner(rig, monkeypatch, inventory_fault):
    rig.settings(start_delay=0.3, list_fault=inventory_fault)
    async def scenario():
        entered, release = hold_original_settlement(monkeypatch)
        leaf = binding(rig)
        leaf.before_action("one")
        operation = asyncio.create_task(leaf.execute_sql(query="SELECT 1"))
        await wait_log(rig, "start")
        controller = leaf._broker._active
        assert type(controller) is QueryWorkerController
        operation.cancel("caller-A")
        try:
            await asyncio.wait_for(entered.wait(), timeout=3.0)
            primary = leaf._broker._caller_cancel
            operation.cancel("caller-B")
            await asyncio.sleep(0)
            operation.cancel("caller-C")
            await asyncio.sleep(0)
            held = not operation.done() and not leaf._close_task.done()
        finally:
            release.set()
        try:
            await operation
        except BaseException as error:
            caught = error
        else:
            pytest.fail("cancelled SQL returned success")
        assert caught is primary, "joined cleanup must preserve original A identity"
        assert caught.args == ("caller-A",)
        assert held, "later cancellation must not detach the retained settlement join"
        failure = BashSqlCleanupPending if inventory_fault else BashSqlError
        assert isinstance(getattr(leaf, "cleanup_error", None), failure)
        assert getattr(leaf, "cleanup_cancellation", None) is not None
        assert leaf.cleanup_cancellation.args == ("caller-B",)
        with pytest.raises(BashSqlError):
            leaf.require_valid()
        try:
            await leaf.aclose()
        except BashSqlError:
            pass
        assert_owned_settled(leaf._broker, rig)
        assert len(creates(rig)) == 1
    asyncio.run(scenario())


def test_cancellation_ambiguous_create_preserves_primary(rig, monkeypatch):
    rig.settings(create_delay=0.3, create_nonzero=True, create_effect=False)
    async def scenario():
        entered, release = hold_original_settlement(monkeypatch)
        leaf = binding(rig)
        leaf.before_action("one")
        operation = asyncio.create_task(leaf.execute_sql(query="SELECT 1"))
        await wait_log(rig, "create")
        controller = leaf._broker._active
        assert type(controller) is QueryWorkerController
        operation.cancel("caller-A")
        try:
            await asyncio.wait_for(entered.wait(), timeout=3.0)
            primary = leaf._broker._caller_cancel
            operation.cancel("caller-B")
            await asyncio.sleep(0)
            operation.cancel("caller-C")
            await asyncio.sleep(0)
            held = not operation.done() and not leaf._close_task.done()
        finally:
            release.set()
        try:
            await operation
        except BaseException as error:
            caught = error
        else:
            pytest.fail("cancelled ambiguous create returned success")
        assert caught is primary, "unresolved retirement must preserve original A identity"
        assert caught.args == ("caller-A",)
        assert held, "later cancellation must not detach the retained settlement join"
        assert isinstance(leaf.cleanup_error, BashSqlCleanupPending)
        assert leaf.cleanup_cancellation.args == ("caller-B",)
        for _ in range(2):
            with pytest.raises(BashSqlCleanupPending):
                await leaf.aclose()
        assert not leaf._owner.closed
        with pytest.raises(BashSqlError):
            leaf.require_valid()
        assert len(creates(rig)) == 1
        assert not any(r["command"] in ("start", "rm", "list") for r in rig.log())
        assert_owned_settled(leaf._broker, rig)
    asyncio.run(scenario())


def test_ambiguous_create_stays_unresolved(rig):
    rig.settings(create_nonzero=True, create_effect=False)
    async def scenario():
        leaf = binding(rig)
        leaf.before_action("one")
        with pytest.raises(SqlBrokerRetirementPending):
            await leaf.execute_sql(query="SELECT 1")
        assert isinstance(leaf.cleanup_error, BashSqlCleanupPending)
        for _ in range(2):
            with pytest.raises(BashSqlCleanupPending):
                await leaf.aclose()
        assert not leaf._broker.closed
        assert not any(r["command"] in ("start", "rm", "list") for r in rig.log())
        assert_owned_settled(leaf._broker, rig)
    asyncio.run(scenario())


def test_concurrent_independent_task_bindings(rig, tmp_path):
    root = tmp_path / "second"
    root.mkdir()
    generator = globals()["rig"].__wrapped__(root)
    second = next(generator)
    async def scenario():
        one, two = binding(rig), binding(second)
        assert one._broker.authorization_header != two._broker.authorization_header
        assert one._broker._task_identity is not two._broker._task_identity
        one.before_action("one")
        two.before_action("one")
        try:
            results = await asyncio.gather(
                one.execute_sql(query="SELECT 11"), two.execute_sql(query="SELECT 22"))
            assert [r.rows for r in results] == [((11,),), ((22,),)]
            one.after_action("one")
            two.after_action("one")
        finally:
            await asyncio.gather(one.aclose(), two.aclose())
        assert len(creates(rig)) == len(creates(second)) == 1
        assert_owned_settled(one._broker, rig)
        assert_owned_settled(two._broker, second)
    try:
        asyncio.run(scenario())
    finally:
        with pytest.raises(StopIteration):
            next(generator)
