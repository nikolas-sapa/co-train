"""Real-SQLite regressions: no result set is not an empty query result.

No framework, model, network, or corpus download is needed. All database writes
are fixture setup under pytest's temporary directory.
"""

from __future__ import annotations

import dataclasses
import sqlite3

import pytest

from bench.score import (_connect, _run, execution_accuracy, extract_sql,
                         validate_golds)
from bench.task import SqlTask


EMPTY_SELECT = "SELECT value FROM items WHERE 0"
EMPTY_CTE = "WITH empty AS (SELECT value FROM items WHERE 0) SELECT * FROM empty"

COMMENT_AND_PRAGMA = [
    pytest.param("-- no answer\n", id="line-comment"),
    pytest.param("/* no answer */", id="block-comment"),
    pytest.param(" \n-- no answer; still a comment;\n ", id="line-semicolons"),
    pytest.param(" \t/* no answer; still a comment; */\n", id="block-semicolons"),
    pytest.param("PRAGMA query_only=ON", id="pragma-no-result"),
]
NO_RESULT = [
    pytest.param("", id="empty"),
    pytest.param(" \t\n ", id="whitespace"),
    *COMMENT_AND_PRAGMA,
]


@pytest.fixture
def query_task(tmp_path):
    # Flat fixture database layout.
    db_dir = tmp_path / "fixture"
    db_dir.mkdir()
    db = db_dir / "fixture.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE items (value INTEGER)")
        conn.executemany("INSERT INTO items VALUES (?)", [(1,), (1,), (2,)])
        conn.commit()
    finally:
        conn.close()
    return SqlTask(
        name="query-boundary", question="", evidence="", gold_sql=EMPTY_SELECT,
        db_id="fixture", db_path=str(db), tier="simple",
        tier_source="annotated", shape="", coarse_shape="", source="fixture",
    )


@pytest.mark.parametrize("sql", NO_RESULT)
def test_run_rejects_statements_without_result_metadata(query_task, sql):
    """Exercise the existing read-only connection, not a mocked cursor."""
    conn = _connect(query_task.db_path)
    try:
        assert conn.execute(sql).description is None
        outcome, rows, detail = _run(conn, sql, timeout_s=1.0, max_rows=10)
    finally:
        conn.close()
    assert outcome == "error"
    assert rows is None
    assert detail


@pytest.mark.parametrize("compare", ["set", "multiset"])
@pytest.mark.parametrize("sql", COMMENT_AND_PRAGMA)
def test_nonquery_prediction_is_pred_error_not_empty_match(query_task, sql, compare):
    result = execution_accuracy(sql, query_task, compare=compare)
    assert (result.score, result.status, result.valid) == (0.0, "pred_error", True)
    assert result.n_gold_rows == 0


@pytest.mark.parametrize("sql", NO_RESULT)
def test_nonquery_gold_is_invalid_gold_error(query_task, sql):
    task = dataclasses.replace(query_task, gold_sql=sql)
    result = execution_accuracy(EMPTY_SELECT, task)
    assert (result.score, result.status, result.valid) == (0.0, "gold_error", False)


def test_validate_golds_reports_every_nonquery_and_keeps_empty_queries(query_task):
    # Concrete inputs kept separate from pytest's parameter wrapper.
    sqls = ["", " \t\n ", "-- no answer\n", "/* no answer */",
            "-- no answer; still a comment;\n",
            "/* no answer; still a comment; */", "PRAGMA query_only=ON"]
    broken = [dataclasses.replace(query_task, name=f"bad-{i}", gold_sql=sql)
              for i, sql in enumerate(sqls)]
    valid_cte = dataclasses.replace(query_task, name="empty-cte", gold_sql=EMPTY_CTE)
    rejected = validate_golds([query_task, *broken, valid_cte])
    assert [task for task, _ in rejected] == broken
    assert all((result.score, result.status, result.valid)
               == (0.0, "gold_error", False) for _, result in rejected)


@pytest.mark.parametrize("sql", ["", " \t\n "], ids=["empty", "whitespace"])
def test_blank_prediction_keeps_existing_pred_empty_status(query_task, sql):
    result = execution_accuracy(sql, query_task)
    assert (result.score, result.status, result.valid) == (0.0, "pred_empty", True)


@pytest.mark.parametrize("compare", ["set", "multiset"])
@pytest.mark.parametrize("sql", [EMPTY_SELECT, EMPTY_CTE], ids=["select", "cte"])
def test_genuine_empty_query_and_fenced_extraction_still_match(query_task, sql, compare):
    task = dataclasses.replace(query_task, gold_sql=sql)
    conn = _connect(task.db_path)
    try:
        assert conn.execute(sql).description is not None
        assert _run(conn, sql, timeout_s=1.0, max_rows=0) == ("ok", [], "")
    finally:
        conn.close()
    extracted = extract_sql(f"```sql\n{sql};\n```")
    assert extracted == sql
    result = execution_accuracy(extracted, task, compare=compare, max_rows=0)
    assert (result.score, result.status, result.valid) == (1.0, "match", True)
    assert (result.n_pred_rows, result.n_gold_rows) == (0, 0)


def test_read_pragma_with_result_metadata_is_still_a_query(query_task):
    task = dataclasses.replace(query_task, gold_sql="SELECT 1")
    result = execution_accuracy("PRAGMA query_only", task)
    assert (result.score, result.status, result.valid) == (1.0, "match", True)
    assert (result.n_pred_rows, result.n_gold_rows) == (1, 1)


@pytest.mark.parametrize("role", ["pred", "gold"])
@pytest.mark.parametrize("operation", [
    "attach-new", "vacuum-new", "vacuum-existing",
    "writefile-new", "writefile-existing",
])
def test_scorer_filesystem_statements_have_no_side_effects(
        query_task, tmp_path, monkeypatch, role, operation):
    """A later metadata error cannot undo a file created during execute().

    Python's SQLite normally lacks the shell's writefile extension. Register a
    real, temporary-file-only implementation to exercise SQLite's function
    authorization boundary even on that build; the scorer itself is not mocked.
    """
    from pathlib import Path

    from bench import score

    target = tmp_path / "side-effect.sqlite"
    sentinel = b"existing file must remain byte-for-byte unchanged"
    existing = operation.endswith("-existing")
    if existing:
        target.write_bytes(sentinel)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()
              if path.is_file()}
    function_calls = []

    if operation.startswith("writefile-"):
        original_connect = score._connect

        def writefile(filename, data):
            # Never permit this test extension to write outside its own target.
            assert Path(filename) == target
            function_calls.append(filename)
            payload = data.encode() if isinstance(data, str) else bytes(data)
            return target.write_bytes(payload)

        def connect_with_file_extension(db_path):
            conn = original_connect(db_path)
            conn.create_function("writefile", 2, writefile)
            return conn

        monkeypatch.setattr(score, "_connect", connect_with_file_extension)

    literal = "'" + str(target).replace("'", "''") + "'"
    if operation == "attach-new":
        sql = f"ATTACH DATABASE {literal} AS aux"
    elif operation.startswith("vacuum-"):
        sql = f"VACUUM INTO {literal}"
    else:
        # SQLite's function authorizer must also handle case-insensitive names.
        function = "WrItEfIlE" if existing else "writefile"
        sql = f"SELECT {function}({literal}, 'overwritten')"

    task = (dataclasses.replace(query_task, gold_sql=sql)
            if role == "gold" else query_task)
    prediction = EMPTY_SELECT if role == "gold" else sql
    result = execution_accuracy(prediction, task)

    after = {path.name: path.read_bytes() for path in tmp_path.iterdir()
             if path.is_file()}
    assert after == before, "SQL created or modified a filesystem target"
    assert function_calls == [], "file-writing function ran before rejection"
    assert (result.score, result.status, result.valid) == (
        0.0, f"{role}_error", role == "pred")


@pytest.mark.parametrize("failure", ["authorizer", "query-only"])
def test_scorer_setup_failure_propagates_and_closes_real_connection(
        query_task, monkeypatch, failure):
    from pathlib import Path

    from bench import score
    from ptc.sqlite_safety import SQLiteSafetyError

    original_connect = sqlite3.connect
    cause = sqlite3.OperationalError(f"injected {failure} setup failure")
    connections = []
    attempts = []
    executed = []
    close_calls = []

    class FailingSetupConnection(sqlite3.Connection):
        def set_authorizer(self, callback):
            if failure == "authorizer":
                raise cause
            return super().set_authorizer(callback)

        def execute(self, sql, *args, **kwargs):
            attempts.append(sql)
            if failure == "query-only" and sql == "PRAGMA query_only = ON":
                raise cause
            return super().execute(sql, *args, **kwargs)

        def close(self):
            close_calls.append(self)
            return super().close()

    def connect_with_setup_failure(*args, **kwargs):
        # Retain the scorer's real encoded read-only URI and connection timeout.
        assert args == (
            Path(query_task.db_path).resolve().as_uri() + "?mode=ro",
        )
        assert kwargs == {"uri": True, "timeout": 5.0}
        conn = original_connect(*args, **kwargs, factory=FailingSetupConnection)
        conn.set_trace_callback(executed.append)
        connections.append(conn)
        return conn

    monkeypatch.setattr(score.sqlite3, "connect", connect_with_setup_failure)
    with pytest.raises(SQLiteSafetyError) as raised:
        execution_accuracy(EMPTY_CTE, query_task)

    assert raised.value.__cause__ is cause
    assert len(connections) == 1
    assert close_calls == connections
    assert attempts == ([] if failure == "authorizer"
                        else ["PRAGMA query_only = ON"])
    assert executed == []  # Neither setup SQL nor gold/prediction reached SQLite.
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        sqlite3.Connection.execute(connections[0], "SELECT 1")
