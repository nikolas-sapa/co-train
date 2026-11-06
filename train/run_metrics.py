"""Optional plain JSONL storage for observed RUN metrics, not training proof."""

from __future__ import annotations

import json
import os


class _RunMetricsWriter:
    def __init__(self, path: str) -> None:
        if not os.path.isabs(path):
            raise ValueError("RUN metrics retention requires an absolute path")
        # Unbuffered writes prevent close from replaying a failed buffered row.
        self._file = open(path, "xb", buffering=0)

    def ensure_open(self) -> None:
        if self._file.closed:
            raise RuntimeError("RUN metrics retention is closed")

    def write(self, row: dict) -> None:
        self.ensure_open()
        payload = (json.dumps(row) + "\n").encode("utf-8")
        if self._file.write(payload) != len(payload):
            raise OSError("Incomplete RUN metrics retention write")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()
