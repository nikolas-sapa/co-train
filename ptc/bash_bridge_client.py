#!/usr/bin/env python3
"""Private bridge client. Staged read-only as bash or sql in separate containers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import struct
import sys
import time

FRAME_MAX = 4 * 1024 * 1024
COMMAND_MAX = 65536
OUTPUT_MAX = 1024 * 1024
SOCKET_TIMEOUT = 120


class BridgeProtocolError(RuntimeError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeProtocolError("duplicate field")
        result[key] = value
    return result


def _constant(value):
    raise BridgeProtocolError("nonfinite number")


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("ascii")


def decode(data: bytes):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise BridgeProtocolError("invalid JSON") from error


def pack(value) -> bytes:
    body = encode(value)
    if not body or len(body) > FRAME_MAX:
        raise BridgeProtocolError("frame overflow")
    return struct.pack("!I", len(body)) + body


def sign(value, key: bytes):
    return {"body": value, "mac": hmac.new(key, encode(value), hashlib.sha256).hexdigest()}


def verify(packet, key: bytes):
    if (type(packet) is not dict or set(packet) != {"body", "mac"}
            or type(packet["mac"]) is not str
            or not hmac.compare_digest(
                packet["mac"], sign(packet["body"], key)["mac"])):
        raise BridgeProtocolError("authentication failed")
    return packet["body"]


def validate_command(command: str) -> None:
    if (type(command) is not str or "\0" in command
            or len(os.fsencode(command)) > COMMAND_MAX):
        raise BridgeProtocolError("invalid command")


def _budget(connection, deadline):
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("private bridge total deadline expired")
        connection.settimeout(remaining)


def _recv_exact(connection, count, deadline=None):
    chunks = bytearray()
    while len(chunks) < count:
        _budget(connection, deadline)
        block = connection.recv(count - len(chunks))
        if not block:
            raise BridgeProtocolError("lost peer")
        chunks.extend(block)
    return bytes(chunks)


def receive(connection, deadline=None):
    size = struct.unpack("!I", _recv_exact(connection, 4, deadline))[0]
    if not 0 < size <= FRAME_MAX:
        raise BridgeProtocolError("invalid frame length")
    return decode(_recv_exact(connection, size, deadline))


def _output(value):
    if type(value) is not str:
        raise BridgeProtocolError("invalid output")
    try:
        data = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise BridgeProtocolError("invalid output encoding") from error
    if len(data) > OUTPUT_MAX:
        raise BridgeProtocolError("output overflow")
    return data


def exchange(*, directory: Path, operation: str, value: str, deliver=None):
    deadline = time.monotonic() + SOCKET_TIMEOUT
    validate_command(value)
    key = (directory / "key").read_bytes()
    if len(key) != 32:
        raise BridgeProtocolError("invalid capability")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        _budget(connection, deadline)
        connection.connect(str(directory / "socket"))
        hello = verify(receive(connection, deadline), key)
        if (type(hello) is not dict or set(hello) != {"nonce", "seq"}
                or type(hello["nonce"]) is not str or len(hello["nonce"]) != 64
                or type(hello["seq"]) is not int or hello["seq"] < 0):
            raise BridgeProtocolError("invalid challenge")
        request = {**hello, "op": operation, "value": value}
        _budget(connection, deadline)
        connection.sendall(pack(sign(request, key)))
        result = verify(receive(connection, deadline), key)
        if (type(result) is not dict
                or set(result) != {"nonce", "seq", "stdout", "stderr", "status"}
                or result["nonce"] != hello["nonce"]
                or type(result["seq"]) is not int or result["seq"] != hello["seq"]
                or type(result["status"]) is not int or not 0 <= result["status"] <= 255):
            raise BridgeProtocolError("invalid result")
        stdout, stderr = _output(result["stdout"]), _output(result["stderr"])
        if len(stdout) + len(stderr) > OUTPUT_MAX:
            raise BridgeProtocolError("combined output overflow")
        if deliver is not None:
            _budget(connection, deadline)
            deliver(stdout, stderr)
        # Delivery acknowledgment is private, never taken from actor output.
        _budget(connection, deadline)
        connection.sendall(pack(sign({**hello, "received": True}, key)))
        return stdout, stderr, result["status"]


def _deliver(stdout, stderr):
    sys.stdout.buffer.write(stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr)
    sys.stderr.buffer.flush()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sql = Path(sys.argv[0]).name == "sql"
    expected = "--query" if sql else "-c"
    try:
        if len(args) != 2 or args[0] != expected:
            raise BridgeProtocolError("only exact command forwarding supported")
        directory = Path(__file__).absolute().parent / "capability"
        _, _, status = exchange(
            directory=directory, operation="sql" if sql else "bash",
            value=args[1], deliver=_deliver)
        return status
    except (OSError, ValueError, BridgeProtocolError):
        sys.stderr.write("private Bash bridge failed\n")
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
