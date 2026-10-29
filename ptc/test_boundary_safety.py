"""Literal SQLite targets and malformed tool arguments at the harness boundary.

Real disposable databases, scripted MockTransport policy, no external services.
VACUUM INTO enforcement is a separate, paired-arm policy decision.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest

from ptc.runtime import Catalog, ProgramRejected
from ptc.sql_arms import connect_readonly, make_execute_sql


@pytest.fixture(params=[
    ("ordinary.sqlite", "other.sqlite"),
    ("with space.sqlite", "other.sqlite"),
    ("target.sqlite?ignored", "target.sqlite"),
    ("target.sqlite#fragment", "target.sqlite"),
    ("target%2e.sqlite", "target..sqlite"),
    ("target%23.sqlite", "target#.sqlite"),
    ("target.sqlite?mode=rw#.sqlite", "target.sqlite"),
], ids=["ordinary", "space", "question", "hash", "percent", "encoded-hash",
        "mode-injection"])
def literal_databases(request, tmp_path):
    literal_name, decoy_name = request.param
    literal, decoy = tmp_path / literal_name, tmp_path / decoy_name
    for path, marker in ((literal, "literal"), (decoy, "decoy")):
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE marker (value TEXT)")
            conn.execute("INSERT INTO marker VALUES (?)", (marker,))
            conn.commit()
    return literal, decoy


@pytest.fixture(params=["absolute", "relative"])
def database_argument(request, literal_databases, monkeypatch):
    literal, _ = literal_databases
    if request.param == "relative":
        monkeypatch.chdir(literal.parent)
        return literal.name
    return str(literal)


def _assert_databases_unchanged(literal_databases):
    for path, expected in zip(literal_databases, ("literal", "decoy")):
        # uri=False is intentional: independently inspect the literal files.
        with closing(sqlite3.connect(path, uri=False)) as conn:
            assert conn.execute("SELECT value FROM marker").fetchall() == [(expected,)]
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'uri_probe'"
            ).fetchall() == []


def test_sql_literal_target_isolation(database_argument, literal_databases):
    with closing(connect_readonly(database_argument)) as conn:
        assert conn.execute("SELECT value FROM marker").fetchall() == [("literal",)]
    execute_sql = make_execute_sql(database_argument)
    assert execute_sql(query="SELECT value FROM marker") == [{"value": "literal"}]
    _assert_databases_unchanged(literal_databases)


def test_sql_literal_target_remains_readonly(database_argument, literal_databases):
    with closing(connect_readonly(database_argument)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE uri_probe (value TEXT)")
    execute_sql = make_execute_sql(database_argument)
    with pytest.raises(ProgramRejected, match="readonly"):
        execute_sql(query="CREATE TABLE uri_probe (value TEXT)")
    _assert_databases_unchanged(literal_databases)


def _argument_policy(raw_args):
    # Keep stdlib-only SQLite coverage collectible without optional verifiers.
    from ptc.test_harness import Policy, _assistant

    calls = []

    def note(*, text):
        calls.append(text)
        return text

    policy = Policy(
        _assistant(None, raw_args=raw_args),
        _assistant("print(note(text='fallback'))"),
        _assistant(None),
    )
    return policy, Catalog(tools={"note": note}), calls


def _tool_contents(body):
    return [message["content"] for message in body["messages"]
            if message.get("role") == "tool"]


@pytest.mark.parametrize("raw_args", [
    "[]", "null", "1", '"string"',
    json.dumps({"code": []}),
    json.dumps({"code": {}}),
    json.dumps({"code": 1}),
    json.dumps({"code": None}),
    json.dumps({"code": True}),
], ids=["array-args", "null-args", "number-args", "string-args",
        "array-code", "object-code", "number-code", "null-code", "bool-code"])
def test_harness_argument_shape_rejected_as_data_then_retry(raw_args):
    from ptc.test_harness import _run

    policy, catalog, calls = _argument_policy(raw_args)
    result = _run(policy, catalog, max_turns=3)

    assert result.exit_code == 0
    assert calls == ["fallback"]
    assert len(policy.requests) == 3
    rejection, = _tool_contents(policy.bodies[1])
    assert rejection.startswith("rejected:")
    assert rejection.removeprefix("rejected:").strip()
    assert _tool_contents(policy.bodies[2]) == [rejection, "fallback"]
    assert "error:" not in result.stdout


def test_harness_argument_shape_rejection_consumes_turn_budget():
    from ptc.test_harness import _run

    policy, catalog, calls = _argument_policy("[]")
    result = _run(policy, catalog, max_turns=1)

    assert result.exit_code == 0
    assert len(policy.requests) == 1
    assert calls == []
    assert result.stdout.startswith("rejected:")


def test_harness_malformed_json_syntax_behavior_preserved():
    from ptc.test_harness import _run

    policy, catalog, calls = _argument_policy("{not json")
    result = _run(policy, catalog, max_turns=3)

    assert result.exit_code == 0
    assert len(policy.requests) == 3
    assert calls == ["fallback"]
    # Existing syntax-error path substitutes the empty, valid no-op program.
    assert _tool_contents(policy.bodies[1]) == ["ok (the program printed nothing)"]
    assert _tool_contents(policy.bodies[2]) == [
        "ok (the program printed nothing)", "fallback",
    ]
    assert "error:" not in result.stdout
