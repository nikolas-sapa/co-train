"""SCORER entry point. Entire unchanged protected EX executes in this process."""
from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.path.insert(0, "/bundle")

from ptc.sql_isolation import _native_call, _worker_handshake, encode_wire_message


def main():
    # Normal package initialization is intentional; no namespace-package bypass.
    from bench.score import execution_accuracy
    request, sha = _worker_handshake("scorer")
    native = _native_call(execution_accuracy, request.predicted_sql, request.task,
                                timeout_s=request.timeout_s, max_rows=request.max_rows,
                                compare=request.compare)
    result = encode_wire_message("scorer", "result", native, request_sha256=sha)
    sys.stdout.buffer.write(result); sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except MemoryError:
        raise SystemExit(70)
