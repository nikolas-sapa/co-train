"""PROGRAM entry point. Native observations and flags are forwarded unchanged."""
from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.path.insert(0, "/bundle")

from ptc.sql_isolation import ProgramResponse, _native_call, _worker_handshake, encode_wire_message


def _response_for(native):
    return ProgramResponse(native.observation, native.rejected)


def main():
    from ptc.sql_arms import run_ptc_program
    request, sha = _worker_handshake("program")
    native = _native_call(run_ptc_program, request.program, "/db.sqlite", max_rows=request.max_rows)
    result = encode_wire_message("program", "result", _response_for(native), request_sha256=sha)
    sys.stdout.buffer.write(result); sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except MemoryError:
        raise SystemExit(70)
