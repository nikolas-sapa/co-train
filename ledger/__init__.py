"""The `ledger` taskset, loadable as a `verifiers` plugin from the repo root."""

import os
import sys
from pathlib import Path

from ledger.taskset import LedgerTaskset

__all__ = ["LedgerTaskset"]

REPO_ROOT = str(Path(__file__).resolve().parents[1])


def on_pythonpath() -> None:
    """Put the repo root on `sys.path` AND `PYTHONPATH`.

    `sys.path` alone is not enough. Verifiers launches each tool server as its own
    process -- `python -m ledger.servers.store` from the runtime's workdir
    (`mcp/launch.py:serve_in_runtime`) -- and a parent's `sys.path.insert` does not
    cross a process boundary, so the server died with `No module named 'ledger'` and
    the run hung until the port-file timeout. `glossary` does not hit this because it
    is installed in site-packages; `ledger` lives in the repo.

    `PYTHONPATH` is the channel that does cross: `runtimes/subprocess.py:101` copies
    `os.environ` into the child and `process_env` does not touch `PYTHONPATH`.

    ponytail: an env var rather than packaging `ledger` for pip. Installing it would
    mean a build config and a reinstall on every data edit, to solve a problem one
    variable solves. `pip install -e .` is the upgrade path if this is ever consumed
    from outside the repo.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    existing = os.environ.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    if REPO_ROOT not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([REPO_ROOT, *parts])
