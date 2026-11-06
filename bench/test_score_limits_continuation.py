"""Offline, real-SQLite regressions for direct scorer limit admission."""

from __future__ import annotations

import dataclasses
import sqlite3
import sys

import pytest

from bench import score
from bench.task import SqlTask


@pytest.fixture
def limits_task(tmp_path):
    db = tmp_path / "limits.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE items (value INTEGER)")
        conn.executemany("INSERT INTO items VALUES (?)", [(1,), (1,)])
        conn.commit()
    finally:
        conn.close()
    return SqlTask(
        name="limits-boundary", question="", evidence="",
        gold_sql="SELECT value FROM items", db_id="limits", db_path=str(db),
        tier="simple", tier_source="annotated", shape="", coarse_shape="",
        source="fixture",
    )


@pytest.mark.parametrize("parameter,value", [
    pytest.param("timeout_s", float("nan"), id="timeout-nan"),
    pytest.param("timeout_s", float("inf"), id="timeout-positive-infinity"),
    pytest.param("timeout_s", float("-inf"), id="timeout-negative-infinity"),
    pytest.param("timeout_s", 0, id="timeout-zero"),
    pytest.param("timeout_s", -1.0, id="timeout-negative"),
    pytest.param("timeout_s", True, id="timeout-bool"),
    pytest.param("timeout_s", "1", id="timeout-string"),
    pytest.param("timeout_s", None, id="timeout-none"),
    pytest.param("max_rows", -1, id="rows-negative"),
    pytest.param("max_rows", -2, id="rows-negative-fetch-size"),
    pytest.param("max_rows", 1.0, id="rows-integral-float"),
    pytest.param("max_rows", 1.5, id="rows-fractional-float"),
    pytest.param("max_rows", True, id="rows-bool"),
    pytest.param("max_rows", "2", id="rows-string"),
    pytest.param("max_rows", None, id="rows-none"),
    pytest.param("max_rows", sys.maxsize, id="rows-fetch-size-overflow"),
    pytest.param("max_rows", sys.maxsize + 1, id="rows-platform-overflow"),
])
def test_invalid_limits_refuse_before_database_open(
        limits_task, monkeypatch, parameter, value):
    original_connect = sqlite3.connect
    connections = []
    queries = []

    def tracked_connect(*args, **kwargs):
        connections.append((args, kwargs))
        conn = original_connect(*args, **kwargs)
        conn.set_trace_callback(queries.append)
        return conn

    monkeypatch.setattr(score.sqlite3, "connect", tracked_connect)
    try:
        with pytest.raises(ValueError, match=parameter):
            score.execution_accuracy("SELECT value FROM items", limits_task,
                                     **{parameter: value})
    finally:
        assert (len(connections), len(queries)) == (0, 0)


@pytest.mark.parametrize("compare", ["set", "multiset"])
def test_exact_row_cap_boundary(limits_task, compare):
    sql = "SELECT value FROM items"
    accepted = score.execution_accuracy(
        sql, limits_task, timeout_s=1.0, max_rows=2, compare=compare)
    assert (accepted.score, accepted.status, accepted.valid,
            accepted.n_pred_rows, accepted.n_gold_rows) == (
                1.0, "match", True, 2, 2)

    truncated = score.execution_accuracy(
        sql, limits_task, timeout_s=1.0, max_rows=1, compare=compare)
    assert (truncated.score, truncated.status, truncated.valid) == (
        0.0, "gold_truncated", False)

    one_row_gold = dataclasses.replace(limits_task, gold_sql=sql + " LIMIT 1")
    prediction_truncated = score.execution_accuracy(
        sql, one_row_gold, timeout_s=1.0, max_rows=1, compare=compare)
    assert (prediction_truncated.score, prediction_truncated.status,
            prediction_truncated.valid, prediction_truncated.n_gold_rows) == (
                0.0, "pred_truncated", True, 1)


@pytest.mark.parametrize("compare,expected_score,expected_status", [
    ("set", 1.0, "match"),
    ("multiset", 0.0, "mismatch"),
])
def test_finite_comparison_modes_preserved(
        limits_task, compare, expected_score, expected_status):
    result = score.execution_accuracy(
        "SELECT DISTINCT value FROM items", limits_task,
        timeout_s=1, max_rows=2, compare=compare)
    assert (result.score, result.status, result.valid,
            result.n_pred_rows, result.n_gold_rows) == (
                expected_score, expected_status, True, 1, 2)


@pytest.mark.parametrize("compare", ["set", "multiset"])
def test_zero_row_cap_preserved(limits_task, compare):
    empty_sql = "SELECT value FROM items WHERE 0"
    empty_task = dataclasses.replace(limits_task, gold_sql=empty_sql)
    result = score.execution_accuracy(
        empty_sql, empty_task, timeout_s=1.0, max_rows=0, compare=compare)
    assert (result.score, result.status, result.valid,
            result.n_pred_rows, result.n_gold_rows) == (
                1.0, "match", True, 0, 0)
    nonempty = score.execution_accuracy(
        empty_sql, limits_task, timeout_s=1.0, max_rows=0, compare=compare)
    assert (nonempty.score, nonempty.status, nonempty.valid) == (
        0.0, "gold_truncated", False)
