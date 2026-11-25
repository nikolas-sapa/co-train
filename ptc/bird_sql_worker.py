"""Bounded toy-query transport and static Docker argv, not an executor.

No production binding, scoring authority or runtime qualification is conferred.
SQL capabilities come from the unchanged sibling SQLite protector.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import stat

from ptc.sql_runtime import over_cap_message


class QueryWorkerError(ValueError):
    """Configuration or wire infrastructure failure, never a SQL score."""


def _positive_integer(value):
    if type(value) is not int or value <= 0:
        raise QueryWorkerError("expected an exact positive integer")


def _positive_number(value):
    if type(value) not in (int, float):
        raise QueryWorkerError("expected a finite positive number")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise QueryWorkerError("expected a finite positive number")


@dataclass(frozen=True)
class QueryWorkerLimits:
    action_max_rows: int
    query_timeout_s: float
    request_max_bytes: int
    response_max_bytes: int

    def __post_init__(self):
        for value in (self.action_max_rows, self.request_max_bytes, self.response_max_bytes):
            _positive_integer(value)
        _positive_number(self.query_timeout_s)


@dataclass(frozen=True)
class QueryWorkerResult:
    status: str
    columns: tuple[str, ...]
    rows: tuple[tuple[None | int | float | str | bytes, ...], ...]
    message: str | None


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise QueryWorkerError("duplicate JSON field")
        out[key] = value
    return out


def _bad_constant(value):
    raise QueryWorkerError("nonfinite JSON constant")


def _load_json(data):
    return json.loads(data.decode("utf-8", errors="strict"),
                      object_pairs_hook=_pairs, parse_constant=_bad_constant)


def _dump_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8", errors="strict")


def _valid_text(value):
    if type(value) is not str:
        raise QueryWorkerError("expected UTF8 text")
    value.encode("utf-8", errors="strict")
    return value


def _validate_request(obj):
    if type(obj) is not dict or set(obj) != {"format", "version", "query"}:
        raise QueryWorkerError("invalid request fields")
    if obj["format"] != "cotrain_sql_query" or type(obj["version"]) is not int or obj["version"] != 1:
        raise QueryWorkerError("invalid request version")
    return _valid_text(obj["query"])


def encode_query_request(query: str, *, limits: QueryWorkerLimits) -> bytes:
    if not isinstance(limits, QueryWorkerLimits):
        raise QueryWorkerError("worker limits required")
    try:
        data = _dump_json(dict(format="cotrain_sql_query", version=1, query=_valid_text(query)))
        if len(data) > limits.request_max_bytes:
            raise QueryWorkerError("request wire overflow")
        return data
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise QueryWorkerError("query request infrastructure failure") from exc


def _encode_cell(value):
    if value is None:
        return ["null"]
    if type(value) is int:
        return ["integer", str(value)]
    if type(value) is float:
        return ["real", value.hex()]
    if type(value) is str:
        return ["text", value]
    if type(value) is bytes:
        return ["blob", base64.b64encode(value).decode("ascii")]
    raise QueryWorkerError("unsupported SQLite cell")


def _decode_cell(cell):
    if type(cell) is not list or not cell:
        raise QueryWorkerError("invalid cell")
    if cell == ["null"]:
        return None
    if len(cell) != 2 or type(cell[1]) is not str:
        raise QueryWorkerError("invalid tagged cell")
    tag, value = cell
    if tag == "text":
        return _valid_text(value)
    if tag == "integer":
        number = int(value)
        if str(number) == value and -(2**63) <= number < 2**63:
            return number
    elif tag == "real":
        number = float.fromhex(value)
        if not math.isnan(number) and number.hex() == value:
            return number
    elif tag == "blob":
        decoded = base64.b64decode(value, validate=True)
        if base64.b64encode(decoded).decode("ascii") == value:
            return decoded
    raise QueryWorkerError("invalid cell representation")


def decode_query_response(data: bytes, *, limits: QueryWorkerLimits) -> QueryWorkerResult:
    if not isinstance(limits, QueryWorkerLimits):
        raise QueryWorkerError("worker limits required")
    try:
        if type(data) is not bytes or not data or len(data) > limits.response_max_bytes:
            raise QueryWorkerError("empty or oversized response")
        obj = _load_json(data)
        if type(obj) is not dict or set(obj) != {
            "format", "version", "status", "columns", "rows", "message",
        }:
            raise QueryWorkerError("invalid response fields")
        if obj["format"] != "cotrain_sql_result" or type(obj["version"]) is not int or obj["version"] != 1:
            raise QueryWorkerError("invalid response version")
        status, columns, rows, message = (
            obj["status"], obj["columns"], obj["rows"], obj["message"])
        if type(status) is not str or status not in {
            "rows", "sql_error", "row_refusal", "query_timeout", "infrastructure_failure",
        }:
            raise QueryWorkerError("invalid response status")
        if type(columns) is not list or type(rows) is not list:
            raise QueryWorkerError("invalid result vectors")
        if status != "rows":
            if columns or rows or type(message) is not str or not message:
                raise QueryWorkerError("partial or untyped failure response")
            return QueryWorkerResult(status, (), (), _valid_text(message))
        if message is not None or len(rows) > limits.action_max_rows:
            raise QueryWorkerError("invalid row result")
        names = tuple(_valid_text(name) for name in columns)
        decoded = []
        for row in rows:
            if type(row) is not list or len(row) != len(names):
                raise QueryWorkerError("row arity mismatch")
            decoded.append(tuple(_decode_cell(cell) for cell in row))
        return QueryWorkerResult(status, names, tuple(decoded), None)
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
        raise QueryWorkerError("query response infrastructure failure") from exc


def _envelope(status, columns=(), rows=(), message=None):
    return dict(format="cotrain_sql_result", version=1, status=status,
                columns=list(columns), rows=list(rows), message=message)


def _payload_main():
    # Imports here are included verbatim in the generated stdlib-only program.
    import sqlite3
    import sys
    import time

    def emit(envelope):
        try:
            data = _dump_json(envelope)
            if len(data) > RESPONSE_MAX_BYTES:
                raise QueryWorkerError("response wire overflow")
        except Exception:
            data = _dump_json(_envelope("infrastructure_failure", message="response wire overflow"))
        if len(data) > RESPONSE_MAX_BYTES:
            return 2
        try:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        except Exception:
            return 2
        return 0

    try:
        data = sys.stdin.buffer.read(REQUEST_MAX_BYTES + 1)
        if len(data) > REQUEST_MAX_BYTES:
            raise QueryWorkerError("request wire overflow")
        query = _validate_request(_load_json(data))
    except Exception:
        return emit(_envelope("infrastructure_failure", message="invalid request transport"))

    conn = None
    try:
        # Digest is carried beside the actual source; neither diagnostics nor the
        # fixed guest program expose the host's private source/DB filename.
        if hashlib.sha256(SAFETY_SOURCE.encode("utf-8")).hexdigest() != SAFETY_SHA256:
            raise QueryWorkerError("SQLite guard digest mismatch")
        safety = {}
        exec(compile(SAFETY_SOURCE, "<sqlite-safety>", "exec"), safety)
        conn = sqlite3.connect("file:db.sqlite?mode=ro", uri=True,
                               timeout=QUERY_TIMEOUT_S)
        safety["protect_connection"](conn)
        deadline = time.monotonic() + QUERY_TIMEOUT_S
        conn.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
    except Exception:
        if conn is not None:
            conn.close()
        return emit(_envelope("infrastructure_failure", message="database protection/open failure"))

    try:
        cursor = conn.execute(query)
        columns = [item[0] for item in cursor.description or ()]
        rows = cursor.fetchmany(ACTION_MAX_ROWS + 1)
        if time.monotonic() >= deadline:
            answer = _envelope("query_timeout", message="query deadline exceeded")
        elif len(rows) > ACTION_MAX_ROWS:
            answer = _envelope("row_refusal", message=ROW_REFUSAL)
        else:
            answer = _envelope("rows", columns, [
                [_encode_cell(cell) for cell in row] for row in rows])
    except sqlite3.Error as exc:
        if time.monotonic() >= deadline:
            answer = _envelope("query_timeout", message="query deadline exceeded")
        else:
            answer = _envelope("sql_error", message=f"{type(exc).__name__}: {exc}")
    except Exception:
        answer = _envelope("infrastructure_failure", message="query transport failure")
    finally:
        conn.close()
    return emit(answer)


def query_worker_source(*, limits: QueryWorkerLimits) -> bytes:
    """Bake immutable host bounds before the first stdin read or JSON parse."""
    if not isinstance(limits, QueryWorkerLimits):
        raise QueryWorkerError("worker limits required")
    try:
        safety = Path(__file__).with_name("sqlite_safety.py").read_bytes()
        safety_text = safety.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise QueryWorkerError("SQLite guard source unavailable") from exc
    prelude = (
        "import base64\nimport hashlib\nimport json\n"
        f"ACTION_MAX_ROWS = {limits.action_max_rows!r}\n"
        f"QUERY_TIMEOUT_S = {limits.query_timeout_s!r}\n"
        f"REQUEST_MAX_BYTES = {limits.request_max_bytes!r}\n"
        f"RESPONSE_MAX_BYTES = {limits.response_max_bytes!r}\n"
        f"ROW_REFUSAL = {over_cap_message(limits.action_max_rows)!r}\n"
        f"SAFETY_SOURCE = {safety_text!r}\n"
        f"SAFETY_SHA256 = {hashlib.sha256(safety).hexdigest()!r}\n"
    )
    helpers = (QueryWorkerError, _pairs, _bad_constant, _load_json, _dump_json,
               _valid_text, _validate_request, _encode_cell, _envelope, _payload_main)
    try:
        return (prelude + "\n".join(inspect.getsource(helper) for helper in helpers)
                + "\nraise SystemExit(_payload_main())\n").encode("utf-8")
    except (OSError, TypeError, UnicodeError) as exc:
        raise QueryWorkerError("worker source unavailable") from exc


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise QueryWorkerError("unsafe resource/context identifier")


def _executable(value):
    if type(value) is not str or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value):
        raise QueryWorkerError("absolute executable path required")
    if ".." in value.split("/"):
        raise QueryWorkerError("noncanonical executable path")


@dataclass(frozen=True)
class DockerQueryWorkerSpec:
    cli_path: str
    daemon_context: str
    image: str
    guest_python: str
    uid: int
    gid: int
    cpus: float
    memory_bytes: int
    pids_limit: int
    tmpfs_bytes: int
    limits: QueryWorkerLimits
    setup_timeout_s: float
    start_timeout_s: float
    retirement_timeout_s: float

    def __post_init__(self):
        _executable(self.cli_path)
        _executable(self.guest_python)
        _identifier(self.daemon_context)
        if type(self.image) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", self.image,
        ):
            raise QueryWorkerError("digest-pinned image required")
        for value in (self.uid, self.gid, self.memory_bytes, self.pids_limit, self.tmpfs_bytes):
            _positive_integer(value)
        for value in (self.cpus, self.setup_timeout_s, self.start_timeout_s,
                      self.retirement_timeout_s):
            _positive_number(value)
        if not isinstance(self.limits, QueryWorkerLimits):
            raise QueryWorkerError("explicit worker limits required")


def build_worker_create_argv(
    spec: DockerQueryWorkerSpec, *, resource_name: str, host_db: Path,
) -> tuple[str, ...]:
    """Plan only. No daemon call, DB copy, SQL argv or resource-absence claim."""
    if not isinstance(spec, DockerQueryWorkerSpec):
        raise QueryWorkerError("explicit worker spec required")
    _identifier(resource_name)
    if not isinstance(host_db, Path) or not host_db.is_absolute():
        raise QueryWorkerError("absolute original DB path required")
    value = str(host_db)
    if any(ord(char) < 32 or ord(char) == 127 or char in ',="\\' for char in value):
        raise QueryWorkerError("unsupported bind mount representation")
    try:
        if any(path.is_symlink() for path in (host_db, *host_db.parents)):
            raise QueryWorkerError("symlink DB paths refused")
        if not stat.S_ISREG(host_db.stat().st_mode):
            raise QueryWorkerError("regular original DB file required")
    except OSError as exc:
        raise QueryWorkerError("original DB unavailable") from exc
    return (
        spec.cli_path, "--context", spec.daemon_context, "create",
        "--name", resource_name, "--pull", "never", "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--user", f"{spec.uid}:{spec.gid}", "--cpus", str(spec.cpus),
        "--memory", str(spec.memory_bytes), "--memory-swap", str(spec.memory_bytes),
        "--pids-limit", str(spec.pids_limit),
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={spec.tmpfs_bytes}",
        "--mount", f"type=bind,src={value},dst=/task/db.sqlite,readonly",
        "--workdir", "/task", "--interactive", "--entrypoint", spec.guest_python,
        spec.image, "-I", "-B", "-c", query_worker_source(limits=spec.limits).decode("utf-8"),
    )
