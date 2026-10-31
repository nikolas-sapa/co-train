"""Injected cleanup-boundary diagnostic only, no production fix or SDK proof."""
import json
import linecache
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ptc import sql_arms
from ptc.runtime import ProgramRejected

original = sql_arms.connect_readonly
connections = []


class ObservedConnection:
    def __init__(self, connection):
        self.connection, self.closed = connection, False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def close(self):
        self.connection.close()
        self.closed = True


def connect(path):
    result = ObservedConnection(original(path))
    connections.append(result)
    return result


with tempfile.TemporaryDirectory(prefix="ptc-trace-cleanup-") as folder:
    db = str(Path(folder) / "tiny.sqlite")
    sqlite3.connect(db).close()
    sql_arms.connect_readonly = connect
    action = sql_arms.make_execute_sql(db)
    last_line = max(line for _, _, line in action.__code__.co_lines() if line is not None)
    assert linecache.getline(action.__code__.co_filename, last_line).strip() == "conn.close()"
    hits = []

    def trace(frame, event, arg):
        if event == "line" and frame.f_code is action.__code__ and frame.f_lineno == last_line:
            hits.append(last_line)
            raise ProgramRejected("injected deadline at connection cleanup")
        return trace

    previous = sys.gettrace()
    try:
        sys.settrace(trace)
        try:
            action(query="SELECT 42 AS answer")
        except ProgramRejected as exc:
            assert str(exc) == "injected deadline at connection cleanup"
        else:
            raise AssertionError("cleanup-boundary injection missed")
    finally:
        sys.settrace(previous)
        sql_arms.connect_readonly = original
    try:
        assert len(hits) == 1 and len(connections) == 1
        assert not connections[0].closed
        assert connections[0].connection.in_transaction is False  # Open-handle metadata, no SQL.
        print(json.dumps({
            "injection_hits": 1, "canonical_close_skipped": True,
            "actual_connection_still_open": True,
            "scope": "injected trace boundary, not natural timing or SDK proof",
        }))
    finally:
        for connection in connections:
            connection.close()
