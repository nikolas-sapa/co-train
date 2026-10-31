"""Pure startup-fence checks, no controller/process/native execution."""
import ast
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest


def _fence():
    path = Path(__file__).with_name("test_sql_lifecycle_process.py")
    module = ast.parse(path.read_bytes())
    assignment = next(node for node in module.body
                      if isinstance(node, ast.Assign) and any(
                          isinstance(target, ast.Name)
                          and target.id == "_OWNED_GUEST_PROBE"
                          for target in node.targets))
    script = ast.parse(ast.literal_eval(assignment.value))
    definition = next((node for node in script.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "_fence_owned_start"), None)
    assert definition is not None, "fixture controller startup fence missing"
    namespace = {}
    exec(compile(ast.Module(body=[definition], type_ignores=[]),
                 "fixture-start-fence", "exec"), namespace)
    return namespace["_fence_owned_start"]


def test_stopped_inert_owner_cannot_start_after_teardown():
    fence = _fence()
    calls, stopping = [], threading.Event()
    owner = SimpleNamespace(_start=lambda: calls.append(1), _thread=None)
    fence(owner, threading.RLock(), stopping)
    stopping.set()
    with pytest.raises(RuntimeError, match="retired"):
        owner._start()
    assert calls == [] and owner._thread is None


def test_admitted_start_holds_the_teardown_lock_until_published():
    fence = _fence()
    lock, stopping = threading.RLock(), threading.Event()
    entered, release = threading.Event(), threading.Event()
    owner = SimpleNamespace(_thread=None)

    def start():
        entered.set()
        assert release.wait(1), "test failed to release inert startup"
        owner._thread = "published-controller-marker"

    owner._start = start
    fence(owner, lock, stopping)
    worker = threading.Thread(target=owner._start)
    worker.start()
    try:
        assert entered.wait(1)
        acquired = lock.acquire(blocking=False)
        if acquired:
            lock.release()
        assert not acquired, "teardown can snapshot an admitted unpublished start"
    finally:
        release.set()
        worker.join(1)
    assert not worker.is_alive()
    with lock:
        stopping.set()
        assert owner._thread == "published-controller-marker"
