"""Regression: literal sqlite paths containing ?, #, % must not be URI-misparsed.

`schema_for`/`scalar_answer` interpolate `db_path` into `file:{path}?mode=ro`.
A `?` truncates the path at the query, `#` at the fragment, and `%XX` decodes --
each silently opening a neighboring file or failing outright. The scorer already
uses `Path(db_path).resolve().as_uri() + "?mode=ro"`; these helpers must match.
"""

import hashlib
import sqlite3

import pytest

from bench import make_probe_prompts as mpp
from bench.task import SqlTask

EXPECTED_SCHEMA = "CREATE TABLE original (value INTEGER)"
ORIGINAL_SCHEMA = "CREATE TABLE original (value INTEGER)"
DECOY_SCHEMA = "CREATE TABLE decoy (value INTEGER)"

PATH_CASES = ["probe?.sqlite", "probe#.sqlite", "probe%23.sqlite"]


def _make_db(path, statements, rows):
    con = sqlite3.connect(path)
    try:
        for stmt in statements:
            con.execute(stmt)
        con.executemany("INSERT INTO original VALUES (?)", rows)
        con.commit()
    finally:
        con.close()


def _snapshot(dirpath):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(dirpath.iterdir())
    }


def _task(db_path, gold_sql):
    return SqlTask(
        name="probe-1",
        question="q",
        evidence="",
        gold_sql=gold_sql,
        db_id="probe",
        db_path=str(db_path),
        tier="simple",
        tier_source="annotated",
        shape="s",
        coarse_shape="c",
        source="fixture",
    )


def _decoy_name(filename):
    # `file:probe?.sqlite?mode=ro` and `file:probe#.sqlite?mode=ro` both resolve to
    # `probe`; `file:probe%23.sqlite?mode=ro` decodes to `probe#.sqlite`.
    if "%" in filename:
        return "probe#.sqlite"
    return "probe"


@pytest.mark.parametrize("helper", ["schema", "scalar"])
@pytest.mark.parametrize("filename", PATH_CASES)
def test_schema_and_scalar_use_literal_database_path(tmp_path, filename, helper):
    db = tmp_path / filename
    _make_db(db, [ORIGINAL_SCHEMA], [(17,)])
    before = _snapshot(tmp_path)
    try:
        if helper == "schema":
            assert mpp.schema_for(str(db)) == EXPECTED_SCHEMA
        else:
            assert mpp.scalar_answer(_task(db, "SELECT value FROM original")) == "17"
    finally:
        assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("helper", ["schema", "scalar"])
@pytest.mark.parametrize("filename", PATH_CASES)
def test_uri_path_does_not_select_decoy_database(tmp_path, filename, helper):
    target = tmp_path / filename
    decoy = tmp_path / _decoy_name(filename)
    _make_db(decoy, [ORIGINAL_SCHEMA, DECOY_SCHEMA], [(29,)])
    _make_db(target, [ORIGINAL_SCHEMA], [(17,)])
    before = _snapshot(tmp_path)
    try:
        if helper == "schema":
            assert mpp.schema_for(str(target)) == EXPECTED_SCHEMA
        else:
            assert mpp.scalar_answer(_task(target, "SELECT value FROM original")) == "17"
    finally:
        assert _snapshot(tmp_path) == before


FINITE_CASES = [
    ("SELECT count(*) FROM t", "2"),
    ("SELECT a, b FROM t LIMIT 1", None),
    ("SELECT a FROM t", None),
    ("SELECT nope FROM t", None),
    ("SELECT NULL", None),
]


@pytest.mark.parametrize("sql,expected", FINITE_CASES)
def test_scalar_finite_behavior(tmp_path, sql, expected):
    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?)", [(1, "x"), (2, "y")])
        con.commit()
    finally:
        con.close()
    assert mpp.scalar_answer(_task(db, sql)) == expected


def test_scalar_database_remains_readonly(tmp_path):
    db = tmp_path / "t.sqlite"
    _make_db(db, [ORIGINAL_SCHEMA], [(17,)])
    before = _snapshot(tmp_path)
    try:
        assert mpp.scalar_answer(
            _task(db, "UPDATE original SET value = 99")) is None
    finally:
        assert _snapshot(tmp_path) == before
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT value FROM original").fetchone() == (17,)
    finally:
        con.close()
