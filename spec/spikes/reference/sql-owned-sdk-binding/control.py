"""Fresh-process scope-barrier sensitivity, MOCK native results only.

Runs the original registered SDK composition test and its original writer.
Each mutant wraps one production AST call site and hits once. Never edits
source or SDK hooks. Reward and Env writer barriers are separate mutations.
This proves neither decoded native results nor active owned cleanup/ACK.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[4]
ROOT = REPO / "cotrain_owned_sql.py"
TEST = REPO / "ptc/test_owned_sql_sdk_integration.py"
FAULT_TEST = REPO / "ptc/test_owned_sql_sdk_faults.py"
ASSOCIATION_TEST = REPO / "ptc/test_owned_sql_sdk_association.py"
CASES = {
    "invalid-to-zero": (
        TEST, "test_registered_sdk_mock_invalid_status_never_rewards[gold_error]",
        "INVALID_NATIVE_STATUS_PUBLISHED_EPISODE"),
    "score-close-reward": (
        FAULT_TEST, "test_registered_sdk_composition_score_close_reward_barrier",
        "SDK_SCORE_CLOSE_REWARD_BARRIER: reward before public close"),
    "env-writer": (
        FAULT_TEST, "test_registered_sdk_composition_env_writer_barrier",
        "SDK_WRITER_BARRIER: row before scope cleanup"),
    "association": (
        ASSOCIATION_TEST,
        "test_registered_sdk_composition_cross_scope_program_refuses_dispatch",
        "SDK_SCOPE_ASSOCIATION_DISPATCH: foreign scope reached owned dispatch"),
}
CHILD_SECONDS = 20.0
MAX_RECEIPT_BYTES = 8192
SOURCES = (
    ROOT, TEST, FAULT_TEST, ASSOCIATION_TEST, Path(__file__).resolve(),
    REPO / "ptc/harness.py",
    REPO / "ptc/sql_isolation.py",
    REPO / "ptc/sql_owned_program.py",
    REPO / "ptc/sql_owned_score.py",
    REPO / "ptc/test_bash_qa_eval_integration.py",
)


def _hashes():
    return {str(path.relative_to(REPO)): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in SOURCES}


class _Discard:
    encoding = "utf-8"

    def write(self, value):
        return len(value)

    def flush(self):
        pass

    def isatty(self):
        return False


class _BindingSite(ast.NodeTransformer):
    def __init__(self, case, mutate):
        self.case = case
        self.mutate = mutate
        self.owner = None
        self.method = None
        self.matches = 0
        self.candidates = 0

    def visit_ClassDef(self, node):
        previous = self.owner
        self.owner = node.name
        self.generic_visit(node)
        self.owner = previous
        return node

    def visit_AsyncFunctionDef(self, node):
        previous = self.method
        self.method = node.name
        self.generic_visit(node)
        self.method = previous
        return node

    visit_FunctionDef = visit_AsyncFunctionDef

    def visit_Compare(self, node):
        if (self.case == "association"
                and self.owner == "_Scope" and self.method == "check"
                and len(node.ops) == len(node.comparators) == 1
                and isinstance(node.ops[0], ast.IsNot)
                and isinstance(node.comparators[0], ast.Name)
                and node.comparators[0].id == "self"
                and ast.dump(node.left) == ast.dump(ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="_rollout", ctx=ast.Load()),
                        attr="get", ctx=ast.Load()),
                    args=[], keywords=[]))):
            self.candidates += 1
            self.matches += 1
            if self.mutate:
                return ast.copy_location(ast.Call(
                    func=ast.Name(id="_control_routing_mismatch", ctx=ast.Load()),
                    args=[ast.Name(id="self", ctx=ast.Load()), node.left],
                    keywords=[]), node)
        return node

    def visit_Assign(self, node):
        if (self.case == "invalid-to-zero"
                and self.owner == "OwnedSqlTask" and self.method == "score"
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "result"
                and isinstance(node.value, ast.Await)
                and isinstance(node.value.value, ast.Call)
                and isinstance(node.value.value.func, ast.Attribute)
                and node.value.value.func.attr == "score_sql"):
            self.candidates += 1
            self.matches += 1
            if self.mutate:
                node.value = ast.copy_location(ast.Call(
                    func=ast.Name(id="_control_invalid_to_zero", ctx=ast.Load()),
                    args=[node.value], keywords=[]), node.value)
        return node

    def visit_Await(self, node):
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            return node
        if (self.case == "score-close-reward"
                and self.owner == "OwnedSqlTask" and self.method == "score"
                and call.func.id == "_join_resource"
                and len(call.args) == 2
                and ast.dump(call.args[0]) == ast.dump(ast.Name(id="scope", ctx=ast.Load()))
                and ast.dump(call.args[1]) == ast.dump(ast.Attribute(
                    value=ast.Name(id="scope", ctx=ast.Load()),
                    attr="scorer", ctx=ast.Load()))):
            # There must be exactly two: pre-reward, then unchanged finally.
            self.candidates += 1
            if self.candidates != 1:
                return node
            replacement = "_control_score_close"
            args = call.args
        elif (self.case == "env-writer"
                and self.owner == "OwnedSqlEnv" and self.method == "run"
                and call.func.id == "_settle" and len(call.args) == 1
                and ast.dump(call.args[0]) == ast.dump(ast.Attribute(
                    value=ast.Name(id="scope", ctx=ast.Load()),
                    attr="cleanup_task", ctx=ast.Load()))):
            self.candidates += 1
            replacement = "_control_env_join"
            args = [ast.Name(id="scope", ctx=ast.Load()), call.args[0]]
        else:
            return node
        self.matches += 1
        if self.mutate:
            node.value = ast.copy_location(ast.Call(
                func=ast.Name(id=replacement, ctx=ast.Load()),
                args=args, keywords=[]), call)
        return node


def _install(case, mutate, state):
    # One module instance, same registry id/config types; no dependency patch.
    assert "cotrain_owned_sql" not in sys.modules
    spec = importlib.util.spec_from_file_location("cotrain_owned_sql", ROOT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    def convert(result):
        if state["fault_hits"] == 0:
            assert type(result) is module.ExResult and result.valid is False
            assert result.status == "gold_error"
            state["fault_hits"] += 1
            # Deliberate manufactured RESULT in negative mode only. Not an
            # owner completion, ACK or positive-path scoring result.
            return module.ExResult(
                0.0, "mismatch", True, "CONTROL invalid mock became zero", 1, 1)
        return result

    def first_scope(scope):
        return bool(scope.admission.scopes
                    and scope is scope.admission.scopes[0])

    def routing_mismatch(scope, current):
        mismatch = current is not scope
        if mismatch and state["fault_hits"] == 0:
            assert first_scope(scope) and type(current) is module._Scope
            assert current.admission is scope.admission
            assert scope.live and current.live
            state["fault_hits"] += 1
            return False  # Omit one routing refusal, preserve all other checks.
        return mismatch

    async def score_close(scope, resource):
        if first_scope(scope) and state["fault_hits"] == 0:
            assert resource is scope.scorer
            state["fault_hits"] += 1
            scope.closes.start(resource)  # Retain/start, omit only this await.
            return None
        return await module._join_resource(scope, resource)

    async def env_join(scope, task):
        if first_scope(scope) and state["fault_hits"] == 0:
            assert task is scope.cleanup_task and not task.done()
            state["fault_hits"] += 1
            return None  # Deliberate Env-only omission, no writer replacement.
        return await module._settle(task)

    tree = ast.parse(ROOT.read_text(), filename=str(ROOT))
    visitor = _BindingSite(case, mutate)
    tree = visitor.visit(tree)
    assert visitor.matches == 1, "CONTROL_TARGET_NOT_EXACT"
    assert visitor.candidates == (2 if case == "score-close-reward" else 1), (
        "CONTROL_CANDIDATES_CHANGED")
    state["ast_sites"] = visitor.matches
    module.__dict__["_control_invalid_to_zero"] = convert
    module.__dict__["_control_score_close"] = score_close
    module.__dict__["_control_env_join"] = env_join
    module.__dict__["_control_routing_mismatch"] = routing_mismatch
    sys.modules[spec.name] = module
    exec(compile(ast.fix_missing_locations(tree), str(ROOT), "exec"),
         module.__dict__)


def _gate_origin(test, gate):
    tree = ast.parse(test.read_text(), filename=str(test))
    origins = []

    class GateVisitor(ast.NodeVisitor):
        name = None

        def visit_FunctionDef(self, node):
            previous = self.name
            self.name = node.name
            self.generic_visit(node)
            self.name = previous

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Assert(self, node):
            if isinstance(node.msg, ast.Constant) and node.msg.value == gate:
                origins.append((node.lineno, self.name))

    GateVisitor().visit(tree)
    assert len(origins) == 1, "CONTROL_GATE_NOT_EXACT"
    return origins[0]


def _named_gate(call, test, gate, expected_origin):
    error = call.excinfo
    if error is None or type(error.value) is not AssertionError:
        return False
    # Rendered traceback source can contain an earlier gate that did NOT fail.
    # Require the actual exception message AND its originating assertion.
    origin = error.traceback[-1]
    return (
        str(error.value).split("\n", 1)[0] == gate
        and Path(str(origin.path)).resolve() == test.resolve()
        and (origin.lineno + 1, origin.name) == expected_origin
    )


def _worker(case, mutate):
    before = _hashes()
    sys.path.insert(0, str(REPO))
    state = {"fault_hits": 0, "ast_sites": 0}
    failures = []
    test, node, gate = CASES[case]
    expected_origin = _gate_origin(test, gate)
    import pytest

    class Reports:
        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(self, item, call):
            outcome = yield
            report = outcome.get_result()
            if report.failed:
                # Never retain/output exception text, prompts or paths.
                failures.append({
                    "call_phase": report.when == "call",
                    "named_gate": _named_gate(call, test, gate, expected_origin),
                    "target": report.nodeid.split("::")[-1] == node,
                })

    with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        _install(case, mutate, state)
        code = int(pytest.main([
            "-q", "-p", "no:cacheprovider", str(test) + "::" + node],
            plugins=[Reports()]))
    unchanged = _hashes() == before
    expected_failure = failures == [{
        "call_phase": True, "named_gate": True, "target": True}]
    qualified = (
        unchanged and state["ast_sites"] == 1
        and (code == 1 and state["fault_hits"] == 1 and expected_failure
             if mutate else
             code == 0 and state["fault_hits"] == 0 and not failures))
    receipt = {
        "mode": "mutant" if mutate else "restored",
        "mutation": case,
        **state, "pytest_exit": code, "failed_reports": len(failures),
        "named_gate": expected_failure, "source_unchanged": unchanged,
        "mock_native_results": True, "native_ack_proof": False,
        "qualified": qualified,
    }
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0 if qualified else 1


def _parent(case, output_dir):
    before = _hashes()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for label, mutate in (
            ("positive", False), ("mutant", True), ("restored", False)):
        with tempfile.TemporaryDirectory(
                prefix="owned-sdk-control-", dir=output_dir) as child_tmp:
            command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                       "--worker", "--case", case]
            if mutate:
                command.append("--mutant")
            child = subprocess.run(
                command, cwd=REPO, capture_output=True, timeout=CHILD_SECONDS,
                env={
                    "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                    "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1",
                    "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
                    "NO_PROXY": "127.0.0.1,localhost", "TMPDIR": child_tmp,
                }, check=False)
        assert child.returncode == 0, "CONTROL_CHILD_DID_NOT_QUALIFY"
        assert not child.stderr, "CONTROL_UNEXPECTED_CHILD_STDERR"
        assert len(child.stdout) <= MAX_RECEIPT_BYTES, "CONTROL_RECEIPT_TOO_LARGE"
        receipt = json.loads(child.stdout)
        assert receipt["qualified"] is True
        assert receipt["mode"] == ("mutant" if mutate else "restored")
        assert receipt["mutation"] == case
        assert receipt["mock_native_results"] is True
        assert receipt["native_ack_proof"] is False
        receipts.append({"case": label, **receipt})
    assert _hashes() == before, "CONTROL_SOURCE_CHANGED"
    result = {"case": case, "children": receipts,
              "source_unchanged": True, "native_ack_proof": False}
    with (output_dir / (case + ".json")).open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--mutant", action="store_true")
    parser.add_argument("--case", choices=tuple(CASES), default="invalid-to-zero")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.worker:
        return _worker(args.case, args.mutant)
    assert not args.mutant and args.output_dir is not None
    assert args.output_dir.is_absolute()
    _parent(args.case, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
