"""Real SQLite file boundaries for the provided SQL actions, not an OS sandbox.

All targets live in tmp_path. Native error wording is deliberately not a contract.
Count-probe attacks use WHERE: SQLite may elide a SELECT-list function in COUNT.
"""

from __future__ import annotations

import shlex
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from ptc import sql_arms
from ptc.runtime import ProgramRejected
from ptc.sqlite_safety import SQLiteSafetyError, protect_connection


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture
def database(tmp_path, monkeypatch):
    # An ordinary user's startup file must not leak into unrelated test cases.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    path = tmp_path / "task ?#%.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE marker (value INTEGER)")
        conn.execute("INSERT INTO marker VALUES (7)")
        conn.commit()
    return path


@pytest.fixture(params=["ptc", "bash"])
def arm(request):
    return request.param


def _action(arm, database, tmp_path, query, *, max_rows=100):
    """Return (accepted, rows/output) from the real public action."""
    if arm == "ptc":
        try:
            return True, sql_arms.make_execute_sql(
                str(database), max_rows=max_rows
            )(query=query)
        except ProgramRejected as exc:
            return False, str(exc)
    result = sql_arms.run_bash_sql(
        str(database), query, bindir=tmp_path / "bin", max_rows=max_rows
    )
    return result.returncode == 0, result.stdout


@pytest.mark.parametrize("kind", ["vacuum", "attach", "writefile", "where-writefile"])
@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_file_write_boundaries(arm, database, tmp_path, kind, existing):
    destination = tmp_path / "model's destination.sqlite"
    if existing:
        # ATTACH must be refused even when its target is a valid, existing DB.
        with closing(sqlite3.connect(destination)) as conn:
            conn.execute("CREATE TABLE sentinel (value TEXT)")
            conn.execute("INSERT INTO sentinel VALUES ('keep me')")
            conn.commit()
    before = destination.read_bytes() if existing else None
    source_before = database.read_bytes()
    path = _literal(destination)
    query = {
        "vacuum": f"VACUUM INTO {path}",
        "attach": f"ATTACH DATABASE {path} AS outside",
        "writefile": f"SELECT writefile({path}, 'overwrite') AS value",
        "where-writefile": (
            f"SELECT value FROM marker WHERE writefile({path}, 'overwrite') > 0"
        ),
    }[kind]

    accepted, observation = _action(arm, database, tmp_path, query)

    assert database.read_bytes() == source_before, observation
    if existing:
        assert destination.read_bytes() == before, observation
    else:
        assert not destination.exists(), observation
    assert not accepted, observation


@pytest.mark.parametrize("query, rows, output", [
    ("SELECT value FROM marker", [{"value": 7}], "value\n7\n"),
    ("SELECT COUNT(*) AS n FROM marker", [{"n": 1}], "n\n1\n"),
    ("SELECT value FROM marker WHERE 0", [], "\n"),
    ("PRAGMA user_version", [{"user_version": 0}], "user_version\n0\n"),
    ("PRAGMA query_only=OFF", [], "\n"),
])
def test_read_controls_remain_valid(arm, database, tmp_path, query, rows, output):
    before = database.read_bytes()
    accepted, result = _action(arm, database, tmp_path, query)
    assert accepted, result
    assert result == (rows if arm == "ptc" else output)
    assert database.read_bytes() == before


@pytest.mark.parametrize("query", [
    "UPDATE marker SET value=99",
    "CREATE TABLE forbidden (value INTEGER)",
])
def test_task_database_cannot_be_mutated(arm, database, tmp_path, query):
    before = database.read_bytes()
    accepted, observation = _action(arm, database, tmp_path, query)
    assert database.read_bytes() == before
    assert not accepted, observation


@pytest.mark.parametrize("kind", ["vacuum", "attach"])
def test_query_only_off_cannot_restore_file_writes(
    arm, database, tmp_path, monkeypatch, kind
):
    destination = tmp_path / "query-only-off.sqlite"
    before = database.read_bytes()
    attack = (
        f"VACUUM INTO {_literal(destination)}" if kind == "vacuum"
        else f"ATTACH DATABASE {_literal(destination)} AS outside"
    )
    if arm == "ptc":
        # Disable query_only on the SAME connection used by make_execute_sql.
        # This avoids relying on Python's unrelated multiple-statement rejection.
        real_connect = sqlite3.connect

        def query_only_off(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            conn.execute("PRAGMA query_only=OFF")
            return conn

        monkeypatch.setattr(sql_arms.sqlite3, "connect", query_only_off)
        query = attack
    else:
        query = f"PRAGMA query_only=OFF; {attack}"
    accepted, observation = _action(arm, database, tmp_path, query)
    assert database.read_bytes() == before
    assert not destination.exists(), observation
    assert not accepted, observation


@pytest.mark.parametrize("function", [
    "writefile", "WrItEfIlE", "edit", "load_extension", "readfile",
])
@pytest.mark.parametrize("placement", ["select", "where"])
@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_python_authorizer_prevents_registered_file_function_calls(
    database, tmp_path, monkeypatch, function, placement, existing
):
    """One real positive-control call, zero protected calls or filesystem writes."""
    destination = tmp_path / "function-target"
    if existing:
        destination.write_bytes(b"unchanged sentinel")
    before = destination.read_bytes() if existing else None
    source_before = database.read_bytes()
    calls = []
    real_connect = sqlite3.connect

    def instrumented_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)

        def external_file(path, data):
            calls.append(path)
            # Instrument native extension/edit hooks without loading any extension.
            Path(path).write_text(data)
            return 1

        conn.create_function(function, 2, external_file)
        return conn

    control = tmp_path / "positive-control"
    with closing(instrumented_connect(str(database))) as conn:
        assert conn.execute(
            f"SELECT {function}(?, ?)", (str(control), "positive")
        ).fetchall() == [(1,)]
    assert len(calls) == 1
    assert control.read_text() == "positive"
    calls.clear()
    monkeypatch.setattr(sql_arms.sqlite3, "connect", instrumented_connect)
    invocation = f"{function}({_literal(destination)}, 'overwrite')"
    query = (
        f"SELECT {invocation} AS value" if placement == "select"
        else f"SELECT value FROM marker WHERE {invocation} > 0"
    )

    accepted, observation = _action("ptc", database, tmp_path, query)

    assert calls == [], observation
    assert database.read_bytes() == source_before
    if existing:
        assert destination.read_bytes() == before
    else:
        assert not destination.exists()
    assert not accepted, observation


def test_authorizer_installation_failure_closes_connection(database, monkeypatch):
    """No usable connection escapes when the shared guard cannot be installed."""
    real_connect = sqlite3.connect
    connections = []

    class InstallationFailure(sqlite3.Connection):
        close_calls = 0

        def set_authorizer(self, callback):
            raise RuntimeError("injected authorizer installation failure")

        def close(self):
            self.close_calls += 1
            super().close()

    def failing_connect(*args, **kwargs):
        conn = real_connect(*args, factory=InstallationFailure, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sql_arms.sqlite3, "connect", failing_connect)
    try:
        with pytest.raises(SQLiteSafetyError) as failure:
            sql_arms.connect_readonly(str(database))
        assert type(failure.value.__cause__) is RuntimeError
        assert str(failure.value.__cause__) == "injected authorizer installation failure"
        assert not isinstance(failure.value, sqlite3.Error)
        assert len(connections) == 1
        assert connections[0].close_calls == 1
        with pytest.raises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")
    finally:
        # Clean up even against the unprotected baseline.
        for conn in connections:
            if not conn.close_calls:
                conn.close()


def test_shared_guard_returns_same_connection_without_changing_main_mode():
    with closing(sqlite3.connect(":memory:")) as conn:
        assert protect_connection(conn) is conn
        # The helper is not a substitute for the caller's mode=ro connection.
        conn.execute("CREATE TABLE writable_main (value INTEGER)")
        assert conn.execute("SELECT 7").fetchall() == [(7,)]


@pytest.mark.parametrize("missing", ["constant", "set_authorizer"])
def test_shared_guard_unsupported_closes_once(monkeypatch, missing):
    class TrackedConnection(sqlite3.Connection):
        close_calls = 0

        def close(self):
            self.close_calls += 1
            super().close()

    conn = sqlite3.connect(":memory:", factory=TrackedConnection)
    try:
        if missing == "constant":
            monkeypatch.delattr(sqlite3, "SQLITE_ATTACH")
        else:
            monkeypatch.setattr(TrackedConnection, "set_authorizer", None)
        with pytest.raises(SQLiteSafetyError) as failure:
            protect_connection(conn)
        assert failure.value.__cause__ is not None
        assert conn.close_calls == 1
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
    finally:
        if not conn.close_calls:
            conn.close()


@pytest.mark.parametrize("order", [
    ("bench.score", "ptc.sql_arms"),
    ("ptc.sql_arms", "bench.score"),
], ids=["scorer-first", "arms-first"])
def test_shared_guard_import_order_is_framework_free(order):
    code = "\n".join([
        "import importlib, sys",
        "blocked = {'torch', 'trl', 'unsloth', 'transformers', 'vllm', 'verifiers'}",
        "class BlockFrameworks:",
        "    def find_spec(self, fullname, path=None, target=None):",
        "        if fullname.split('.')[0] in blocked:",
        "            raise AssertionError('framework import: ' + fullname)",
        "sys.meta_path.insert(0, BlockFrameworks())",
        f"for name in {order!r}:",
        "    importlib.import_module(name)",
        "from ptc.sqlite_safety import protect_connection",
        "import sqlite3",
        "conn = sqlite3.connect(':memory:')",
        "assert protect_connection(conn) is conn",
        "assert conn.execute('SELECT 7').fetchall() == [(7,)]",
        "conn.close()",
        "assert not (blocked & {name.split('.')[0] for name in sys.modules})",
    ])
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("dotcommand", ["output", "once", "backup"])
@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_cli_dotcommands_cannot_write(database, tmp_path, dotcommand, existing):
    destination = tmp_path / "dotcommand-target"
    if existing:
        # A valid DB also lets .backup demonstrate overwrite prevention.
        with closing(sqlite3.connect(destination)) as conn:
            conn.execute("CREATE TABLE sentinel (value TEXT)")
            conn.commit()
    before = destination.read_bytes() if existing else None
    source_before = database.read_bytes()
    # A standalone command is important: a multiline dotcommand argument can
    # fail its own argument parser before exercising any safety protection.
    query = f'.{dotcommand} "{destination}"'
    accepted, observation = _action("bash", database, tmp_path, query)
    assert database.read_bytes() == source_before
    if existing:
        assert destination.read_bytes() == before, observation
    else:
        assert not destination.exists(), observation
    assert not accepted, observation


def test_cli_safe_unsupported_fails_closed_for_valid_select(
    database, tmp_path, monkeypatch
):
    # First prove the real CLI and action work, then simulate an older CLI.
    accepted, output = _action("bash", database, tmp_path, "SELECT value FROM marker")
    assert accepted and output == "value\n7\n"
    real_cli = shutil.which("sqlite3")
    assert real_cli is not None
    shim_dir = tmp_path / "old-cli"
    shim_dir.mkdir()
    log = tmp_path / "cli-arguments"
    shim = shim_dir / "sqlite3"
    shim.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "-safe" ]; then\n'
        "    echo 'sqlite3: unknown option: -safe' >&2; exit 1\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(real_cli)} "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", str(shim_dir) + ":" + sql_arms.os.environ["PATH"])

    accepted, observation = _action("bash", database, tmp_path, "SELECT value FROM marker")

    assert not accepted, observation
    invocations = log.read_text().splitlines()
    assert invocations
    assert all("-safe" in line.split() for line in invocations)


@pytest.mark.parametrize("startup", ["writefile", "renderer"])
def test_cli_hostile_home_compatibility(database, tmp_path, monkeypatch, startup):
    """Compatibility control, not an attack expected to fail before protection."""
    home = tmp_path / "hostile-home"
    home.mkdir()
    destination = tmp_path / "startup-output"
    if startup == "writefile":
        rc = f"SELECT writefile({_literal(destination)}, 'startup');\n"
    else:
        rc = ".mode json\n.headers off\n"
    (home / ".sqliterc").write_text(rc)
    monkeypatch.setenv("HOME", str(home))
    # Prove the rc contents can write/change rendering using explicit loading.
    # Some host CLIs ignore implicit startup files for noninteractive commands.
    control = subprocess.run(
        ["sqlite3", "-init", str(home / ".sqliterc"),
         "-readonly", str(database),
         "SELECT value FROM marker"],
        capture_output=True, text=True, check=False,
    )
    assert control.returncode == 0, control.stderr
    if startup == "writefile":
        assert destination.read_text() == "startup"
        destination.unlink()
    else:
        assert control.stdout.strip() == '[{"value":7}]'
    before = database.read_bytes()

    accepted, observation = _action("bash", database, tmp_path, "SELECT value FROM marker")

    assert not destination.exists(), observation
    assert database.read_bytes() == before
    assert accepted, observation
    assert observation == "value\n7\n"
