"""Explicit local-infrastructure acceptance. Missing infrastructure FAILS, never skips.

Not default-discovered. Run only against the approved preinstalled local image.
Fixture SQL is trusted first-party setup; no model Python or grading SQL runs here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import sqlite3
import sys
import time

import pytest

from ptc import sql_isolation as boundary


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(65536):
            digest.update(block)
    return digest.hexdigest()


def _inventory(daemon):
    items = daemon.call("GET", "/containers/json?all=1")
    assert type(items) is list
    return {boundary._digest(item["Id"]): item["State"] for item in items}


@pytest.fixture(scope="module")
def local(tmp_path_factory):
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    daemon_socket = (home / ".colima/default/docker.sock").resolve()
    binary = Path("/opt/homebrew/bin/colima")
    assert daemon_socket.is_socket(), "approved local UNIX daemon unavailable"
    assert binary.is_file(), "approved pinned VM observer unavailable"
    root = boundary.installed_source_root()
    pins = lambda paths: tuple(boundary.SourcePin(p, _sha(root / p)) for p in paths)
    profile = boundary.make_execution_profile(
        daemon_socket=daemon_socket,
        observer=boundary.MemoryObserver(binary=binary, binary_sha256=_sha(binary.resolve())),
        program_sources=pins(boundary._PROGRAM_PATHS),
        scorer_sources=pins(boundary._SCORER_PATHS),
        controller_sources=pins(("ptc/sql_isolation.py",)),
    )
    audit = {"unix_daemon_connects": 0, "external_network_attempts": 0}
    def hook(event, args):
        if event == "socket.connect":
            connection, target = args
            if connection.family == 1 and target == str(daemon_socket):
                audit["unix_daemon_connects"] += 1
            else:
                audit["external_network_attempts"] += 1
                raise PermissionError("acceptance permits only the explicit owned daemon socket")
        if event in ("socket.getaddrinfo", "socket.bind", "socket.sendto"):
            audit["external_network_attempts"] += 1
            raise PermissionError("external network disabled")
    sys.addaudithook(hook)
    state = tmp_path_factory.mktemp("actual-local-boundary")
    daemon = boundary._Daemon(profile)
    before = _inventory(daemon)
    assert len(before) == 10, "expected ten unchanged unrelated baseline containers"
    database = state / "fixture.sqlite"
    conn = sqlite3.connect(database)
    try:
        conn.executescript('CREATE TABLE "odd ""quoted table"(n INTEGER);'
                           'INSERT INTO "odd ""quoted table" VALUES(1),(2),(3);')
    finally:
        conn.close()
    from train.sql_episodes import InstrumentSettings, SOURCE_PATHS, _source_digest
    instrument = InstrumentSettings(
        action_cap=1, action_max_rows=200, scorer_max_rows=500000, compare="set",
        scorer_timeout_s=30.0, program_timeout_s=10.0, wrapper_timeout_s=10.0,
        python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version,
        source_paths=SOURCE_PATHS, source_sha256=_source_digest(),
    )
    context = {"profile": profile, "daemon": daemon, "state": state, "db": database,
               "db_sha": _sha(database), "instrument": instrument,
               "executor": boundary.PilotExecutor(profile, state_dir=state / "jobs")}
    (state / "profile.json").write_bytes(boundary.execution_profile_canonical_bytes(profile))
    (state / "baseline.json").write_text(json.dumps(before, sort_keys=True) + "\n")
    yield context
    after = _inventory(daemon)
    (state / "final-inventory.json").write_text(json.dumps(after, sort_keys=True) + "\n")
    (state / "audit.json").write_text(json.dumps(audit, sort_keys=True) + "\n")
    assert after == before, "owned absence/unrelated inventory changed"
    assert audit["external_network_attempts"] == 0
    for journal_path in (state / "jobs").glob("*/journal.json"):
        journal = json.loads(journal_path.read_text())
        assert journal["state"] == "CLOSED", str(journal_path)
        assert journal["cleanup_elapsed"] <= 12.0
        events = [json.loads(line) for line in journal_path.with_name("events.jsonl").read_text().splitlines()]
        kinds = [e["kind"] for e in events]
        assert kinds.index("GUARDIAN_ACK") < kinds.index("CREATE_ATTEMPT")
        if journal["cid"] is not None:
            assert kinds.index("STOPPED") < kinds.index("OBSERVER_JOIN_ACK") < kinds.index("DELETE") < kinds.index("ABSENCE")
        assert sum(k == "KILL_ATTEMPT" for k in kinds) <= 1
        for actor in journal["guardians"] + [e["pid"] for e in events if e["kind"] == "CLI_STARTED"]:
            with pytest.raises(ProcessLookupError):
                os.kill(actor, 0)


def _task(local, gold='SELECT COUNT(*) AS n FROM "odd ""quoted table"'):
    from bench.task import SqlTask
    return SqlTask("boundary-native", "count", "", gold, "owned-fixture", str(local["db"]),
                   "simple", "derived", "select", "select", "fixture")


def _assert_receipt(outcome, role):
    assert outcome.abort is None, outcome
    assert outcome.receipt.role == role
    assert outcome.receipt.python_version == "3.12.15"
    assert outcome.receipt.sqlite_version
    assert outcome.receipt.python_version != platform.python_version()


def test_actual_native_pair_full_six_field_result(local):
    program = ('rows = execute_sql(query=\'SELECT COUNT(*) AS n FROM "odd ""quoted table"\')\n'
               'print(rows[0]["n"])\n'
               'print(\'FINAL_SQL: SELECT COUNT(*) AS n FROM "odd ""quoted table"\')')
    outcome = local["executor"].run_program(program, db_path=str(local["db"]),
                                           db_sha256=local["db_sha"], max_rows=200)
    _assert_receipt(outcome, "program")
    assert outcome.rejected is False
    assert outcome.observation == '3\nFINAL_SQL: SELECT COUNT(*) AS n FROM "odd ""quoted table"'
    score = local["executor"].score_sql('SELECT COUNT(*) AS n FROM "odd ""quoted table"', _task(local),
                                       db_sha256=local["db_sha"], instrument=local["instrument"])
    _assert_receipt(score, "scorer")
    assert dataclasses.asdict(score.result) == {
        "score": 1.0, "status": "match", "valid": True, "detail": "",
        "n_pred_rows": 1, "n_gold_rows": 1,
    }


def test_actual_native_print_then_failure_returns_only_native_error_and_zero_score(local):
    before = list((local["state"] / "jobs").glob("*/journal.json"))
    outcome = local["executor"].run_program("print('FINAL_SQL: SELECT 1'); 1/0",
                                           db_path=str(local["db"]), db_sha256=local["db_sha"], max_rows=200)
    _assert_receipt(outcome, "program")
    assert outcome.rejected is True
    assert outcome.observation == "error: ZeroDivisionError: division by zero"
    assert "FINAL_SQL" not in outcome.observation  # Native discarded prints, not recovered.
    added = set((local["state"] / "jobs").glob("*/journal.json")) - set(before)
    assert len(added) == 1
    assert json.loads(next(iter(added)).read_text())["role"] == "program"
